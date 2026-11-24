# Business logic audit checklist

## 1. Mục tiêu và cách sử dụng

Một API có thể xác thực người dùng thành công, kiểm tra kiểu dữ liệu đầy đủ và không có lỗi injection nhưng vẫn cho phép một người nhận tiền hoàn hai lần, tự duyệt yêu cầu của mình hoặc mua hàng với giá do trình duyệt gửi lên. Đây là các lỗi bảo mật logic nghiệp vụ: hệ thống thực hiện thao tác hợp lệ về mặt kỹ thuật nhưng vi phạm quy tắc của sản phẩm.

Bài học này thuộc chương **Security Checklists** của module **Bảo mật logic nghiệp vụ** (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`). Mục tiêu là cung cấp checklist để rà soát cách hệ thống bảo vệ business invariants, state machine, quyền theo đối tượng, transaction và idempotency trước hành vi lạm dụng. Checklist đi từ quy tắc cần bảo vệ đến bằng chứng thực thi và tình huống tấn công, thay vì chỉ đánh dấu rằng dự án có middleware bảo mật.

Checklist phù hợp cho người phát triển, người kiểm thử và người rà soát thiết kế. Hãy dùng nó trên một luồng cụ thể, chẳng hạn mua hàng, duyệt hoàn tiền hoặc cấp hạn mức, rồi mở rộng sang các điểm vào cùng thay đổi dữ liệu của luồng đó.

### Quy ước đánh giá

| Kết quả | Cách sử dụng |
| --- | --- |
| Đạt | Có quy tắc được chủ nghiệp vụ xác nhận, có cơ chế cưỡng chế tại nơi thay đổi dữ liệu và có bằng chứng kiểm thử phù hợp. |
| Không đạt | Có đường đi làm vi phạm quy tắc, hoặc cơ chế hiện tại chưa bảo vệ được tình huống đã xác định. |
| Chưa đủ bằng chứng | Chưa quan sát được lỗi nhưng thiếu quyền truy cập, dữ liệu, đặc tả hoặc kết quả kiểm thử để kết luận. |
| Không áp dụng | Nêu rõ vì sao chức năng không có trong phạm vi; ghi người xác nhận và điều kiện phải xem xét lại. |

Không đánh dấu “Đạt” chỉ vì giao diện ẩn nút, một yêu cầu trả về `403`, mã nguồn có `@Transactional`, hoặc endpoint nhận `Idempotency-Key`. Điều cần chứng minh là kết quả nghiệp vụ vẫn đúng khi đổi đối tượng, bỏ bước, gửi lại yêu cầu hoặc thực hiện đồng thời.

Mỗi dòng checklist nên được gắn với một mã quy tắc và một bộ bằng chứng có thể tìm lại. Ví dụ: `INV-REFUND-01`, vị trí xử lý hoàn tiền, ràng buộc dữ liệu, mã kiểm thử và ảnh chụp kết quả đã loại bỏ thông tin nhạy cảm.

## 2. Chuẩn bị phạm vi và hồ sơ audit

### 2.1. Chọn tài sản và hành động có giá trị

- [ ] Liệt kê tài sản cần bảo vệ: số dư, hàng tồn, hạn mức, dữ liệu thuộc tenant, quyền truy cập, coupon và trạng thái phê duyệt.
- [ ] Liệt kê hành động làm chuyển dịch giá trị: tạo đơn, đổi giá, giữ hàng, thu tiền, hoàn tiền, duyệt yêu cầu, xuất dữ liệu hoặc cấp quyền.
- [ ] Xác định chủ thể thực hiện: khách, chủ đối tượng, người vận hành, người duyệt, quản trị tenant, tài khoản dịch vụ và hệ thống đối tác.
- [ ] Định nghĩa thiệt hại khi mỗi quy tắc bị phá: thất thoát tiền, vượt hạn mức, chiếm tài nguyên, rò dữ liệu hoặc phê duyệt trái thẩm quyền.
- [ ] Chọn phiên bản ứng dụng, cấu hình và môi trường được phép kiểm thử; ghi rõ các đường đi chưa nằm trong phạm vi.
- [ ] Dùng dữ liệu và tài khoản kiểm thử được cấp phép; với thanh toán và email, sử dụng môi trường giả lập hoặc đích kiểm thử đã thống nhất.

Một bộ tài khoản tối thiểu thường gồm: hai người dùng khác nhau trong cùng tenant, một người ở tenant khác, người tạo yêu cầu, người có quyền duyệt và tài khoản dịch vụ. Chỉ có một tài khoản quản trị sẽ che khuất nhiều lỗi quyền theo đối tượng và phân tách nhiệm vụ.

### 2.2. Vẽ bản đồ điểm vào

- [ ] Ghi lại API công khai, API nội bộ, giao diện quản trị, ứng dụng di động, GraphQL mutation và thao tác hàng loạt có liên quan.
- [ ] Liệt kê webhook, consumer của hàng đợi, tác vụ định kỳ, công cụ nhập dữ liệu và thao tác khôi phục thủ công.
- [ ] Xác định nơi thực sự ghi dữ liệu và nơi chỉ chuyển tiếp yêu cầu.
- [ ] Xác định ranh giới tin cậy: trình duyệt, dịch vụ khác, đối tác, broker và kho dữ liệu.
- [ ] Kiểm tra liệu một luồng phụ hoặc phiên bản API cũ có bỏ qua kiểm tra mà luồng chính đang dùng hay không.
- [ ] Xác định dữ liệu quyết định được lấy từ đâu: giá ở máy chủ, tenant từ danh tính đã xác thực, trạng thái hiện hành từ kho dữ liệu có thẩm quyền.

**Bằng chứng cần có:** sơ đồ luồng hoặc bảng điểm vào, danh sách vai trò, danh mục đối tượng và nơi cưỡng chế quy tắc. Nếu một job có thể thay đổi đơn hàng nhưng không xuất hiện trong hồ sơ, kết luận của audit chưa bao phủ đầy đủ luồng đó.

### 2.3. Mẫu ghi nhận cho từng mục

| Trường | Nội dung cần ghi |
| --- | --- |
| Mã kiểm tra | Ví dụ `AUD-REFUND-03`. |
| Quy tắc | Phát biểu cụ thể điều không được vi phạm. |
| Phạm vi | Điểm vào, vai trò, tenant, loại đối tượng và trạng thái. |
| Cơ chế bảo vệ | Kiểm tra quyền, điều kiện cập nhật, constraint, khóa hoặc giao thức xử lý. |
| Tình huống lạm dụng | Yêu cầu thay đổi gì, theo thứ tự nào, có đồng thời hay không. |
| Kết quả mong đợi | Cả phản hồi lẫn trạng thái, số lượng bản ghi và tác dụng phụ. |
| Bằng chứng | Mã kiểm thử, truy vấn đối soát, trace đã làm sạch, vị trí mã nguồn và phiên bản. |
| Kết luận | Đạt, không đạt, chưa đủ bằng chứng hoặc không áp dụng. |
| Theo dõi | Người phụ trách, mức ưu tiên và điều kiện xác nhận sửa xong. |

## 3. Checklist business invariants

Business invariant là điều kiện phải luôn đúng tại ranh giới quan sát đã quy định. Nó có thể áp dụng trong một transaction, trên một vòng đời đối tượng hoặc sau một khoảng thời gian đối soát. Cần nói rõ ranh giới này: quy tắc “mọi thanh toán thành công đều được ghi nhận nội bộ trong vòng thời hạn X” khác với quy tắc “số dư khả dụng không bao giờ âm”.

### 3.1. Chuyển mô tả thành điều kiện kiểm chứng được

- [ ] Mỗi quy tắc ghi rõ đối tượng, phạm vi tính toán, đơn vị, thời điểm và ngoại lệ được phép.
- [ ] Các quy tắc được chủ nghiệp vụ xác nhận, đặc biệt với hoàn tiền, khuyến mại, tín dụng và xử lý thủ công.
- [ ] Phân biệt dữ kiện lịch sử bất biến với dữ liệu có thể thay đổi; không tính lại giá của đơn đã xác nhận từ bảng giá mới nếu hợp đồng nghiệp vụ yêu cầu giữ giá.
- [ ] Với dữ liệu suy ra như số dư hay tổng tiền đã hoàn, xác định nguồn có thẩm quyền và cách đối soát với dữ liệu chi tiết.
- [ ] Các ngoại lệ có điều kiện, quyền và audit trail riêng; không dùng một cờ `force=true` để bỏ mọi quy tắc.
- [ ] Tất cả đường ghi dữ liệu đều giữ cùng invariant, bao gồm cả công cụ vận hành và job sửa dữ liệu.

Ví dụ quy tắc trong miền hoàn tiền:

```text
INV-REFUND-01:
  successful_refund_amount + reserved_refund_amount <= captured_amount
  Phạm vi: một payment, một currency.
  reserved_refund_amount chỉ bao gồm phần đang giữ cho các refund chưa kết thúc.
  Khi refund thành công, chuyển phần tương ứng từ reserved sang successful.

INV-APPROVAL-01:
  người quyết định duyệt khác người tạo yêu cầu,
  và người duyệt có thẩm quyền đối với tenant, đối tượng, số tiền hiện tại.

INV-APPROVAL-02:
  quyền thực thi chỉ có hiệu lực cho đúng revision đã được duyệt.

INV-IDEM-01:
  một command_id tạo tối đa một refund logic,
  dù yêu cầu bị retry, đổi endpoint tương đương hoặc được giao lại qua hàng đợi.
```

Trong ví dụ này, `captured_amount` là tiền đã thu thành công, không phải tiền mới được ủy quyền. Nếu doanh nghiệp có phí hoặc điều chỉnh khiến giới hạn khác đi, phải viết lại quy tắc tương ứng; không âm thầm dùng công thức không còn đúng.

### 3.2. Kiểm tra vị trí cưỡng chế

- [ ] Điều kiện quan trọng được kiểm tra ở phía máy chủ tại lúc thực thi hành động.
- [ ] Dữ liệu có thể bị thay đổi giữa lúc đọc và ghi được bảo vệ bằng cơ chế đồng thời phù hợp.
- [ ] Có ràng buộc dữ liệu cho các quy tắc cục bộ phù hợp: khóa ngoại, `NOT NULL`, `CHECK`, unique hoặc điều kiện cập nhật.
- [ ] Quy tắc liên quan nhiều hàng hoặc nhiều bảng có giao thức bảo vệ rõ ràng; không giả định một `CHECK` đơn hàng có thể kiểm soát tổng của mọi hàng khác.
- [ ] Khi cập nhật có điều kiện không thay đổi hàng nào, chương trình nhận biết xung đột và không tiếp tục phát sinh tác dụng phụ.
- [ ] Lỗi giữa các bước không để lại giá trị đã cộng hoặc trừ một nửa.

**Dấu hiệu cần điều tra:** mã kiểm tra `remaining >= amount`, sau đó ghi một bản ghi hoàn tiền độc lập mà không khóa, không cập nhật có điều kiện và không có cơ chế tuần tự hóa theo payment. Hai yêu cầu có thể cùng thấy đủ hạn mức rồi cùng vượt qua.

## 4. Checklist state machine và quy trình phê duyệt

Một state machine hữu ích phải mô tả được ai có quyền chuyển trạng thái, điều kiện nào phải đúng và dữ liệu nào bị khóa sau chuyển đổi. Chỉ liệt kê tên trạng thái trong enum chưa thể hiện quy trình an toàn.

### 4.1. Lập bảng chuyển trạng thái

Ví dụ rút gọn cho yêu cầu hoàn tiền:

| Từ trạng thái | Hành động | Sang trạng thái | Điều kiện chính |
| --- | --- | --- | --- |
| `DRAFT` | Gửi yêu cầu | `SUBMITTED` | Dữ liệu hợp lệ, người gửi được thao tác trên payment. |
| `SUBMITTED` | Duyệt | `APPROVED` | Người duyệt đủ quyền, khác người tạo; ghi revision được duyệt. |
| `SUBMITTED` | Từ chối | `REJECTED` | Có quyền từ chối, lý do và dấu vết quyết định. |
| `APPROVED` | Đặt lệnh thực thi | `EXECUTION_PENDING` | Revision khớp, giữ được hạn mức hoàn và tạo lệnh bền vững. |
| `EXECUTION_PENDING` | Ghi nhận kết quả | `SUCCEEDED` | Đối tác xác nhận thành công, đúng refund và số tiền. |
| `EXECUTION_PENDING` | Ghi nhận từ chối dứt khoát | `FAILED` | Có bằng chứng đối tác không thực hiện; hoàn trả phần giữ đúng một lần. |
| `EXECUTION_PENDING` | Chưa rõ kết quả | `RECONCILING` | Timeout hoặc dữ liệu mâu thuẫn; giữ thông tin để tra cứu và đối soát. |
| `RECONCILING` | Xác minh kết quả | `SUCCEEDED` hoặc `FAILED` | Kết quả có thẩm quyền, xử lý phần giữ nhất quán. |

Đây là một mô hình minh họa, không phải danh sách trạng thái bắt buộc. Điểm cốt lõi là timeout không chứng minh bên ngoài chưa thực hiện. Nếu cần hủy khi lệnh đã gửi đi, phải định nghĩa thêm quy trình; đổi trạng thái nội bộ sang `CANCELLED` không tự hủy được tác dụng phụ tại đối tác.

### 4.2. Checklist chuyển trạng thái

- [ ] Mọi chuyển trạng thái có nguồn, đích, chủ thể, điều kiện và tác dụng phụ được mô tả.
- [ ] Máy chủ tự quyết định trạng thái đích từ hành động hợp lệ; không tin trường `status` do client gửi.
- [ ] Endpoint thực thi kiểm tra trạng thái hiện hành; không suy rằng người dùng đã đi qua màn hình phê duyệt.
- [ ] Có kiểm tra bỏ bước, đảo thứ tự, gọi thẳng bước cuối, lặp lại bước và quay về bước trước.
- [ ] Trạng thái kết thúc không bị mở lại bởi API sửa chung, import, sự kiện cũ hoặc công cụ quản trị thiếu kiểm soát.
- [ ] Quyết định duyệt ràng buộc với dữ liệu được duyệt: revision, số tiền, người nhận, phạm vi và thời hạn cần thiết.
- [ ] Thay đổi dữ liệu quan trọng sau phê duyệt làm mất hiệu lực phê duyệt cũ hoặc bị từ chối.
- [ ] Hai lệnh chuyển trạng thái cạnh tranh không cùng thành công khi nghiệp vụ chỉ cho phép một nhánh.
- [ ] Cập nhật trạng thái và ghi quyết định, phần giữ hạn mức hoặc lệnh xử lý tiếp theo có ranh giới transaction nhất quán.
- [ ] Các quyết định phê duyệt nhiều cấp được đếm theo đúng chủ thể và thứ tự; một người không thể tạo nhiều phiếu để đủ ngưỡng.
- [ ] Quyền khẩn cấp hoặc quyền ghi đè có lý do, phạm vi và dấu vết riêng; các invariant không được phép phá vẫn được giữ.

### 4.3. Tình huống kiểm tra trọng tâm

Tạo yêu cầu hoàn 100.000 VND, gửi và được duyệt ở revision 3. Sau đó sửa thành 1.000.000 VND ở revision 4 và gọi endpoint thực thi với quyết định duyệt cũ. Kết quả mong đợi là không tạo lệnh hoàn tiền cho revision 4; yêu cầu phải được duyệt lại hoặc thay đổi bị từ chối. Chỉ thấy trạng thái `APPROVED` là chưa đủ bằng chứng rằng số tiền hiện tại đã được duyệt.

Với một giao diện đọc từ cache hoặc replica, cần kiểm tra đường ghi có kiểm tra lại điều kiện trên nguồn dữ liệu có thẩm quyền. Một ảnh chụp trạng thái cũ không nên cấp quyền cho thao tác mới.

## 5. Checklist quyền theo đối tượng, tenant và nhiệm vụ

Quyền cần được xét trên bộ thông tin **chủ thể + hành động + đối tượng + trạng thái + ngữ cảnh**. Role `APPROVER` chỉ là một thành phần: người duyệt có thể chỉ được duyệt yêu cầu của một tenant, một đơn vị hoặc dưới một ngưỡng tiền.

### 5.1. Quyền truy cập và hành động

- [ ] Mỗi điểm vào kiểm tra quyền đọc và quyền thay đổi trên đối tượng cụ thể.
- [ ] Tenant hiệu lực được suy ra từ ngữ cảnh danh tính và tư cách thành viên đã xác thực; mọi tenant do client chọn đều được kiểm tra lại.
- [ ] Thử thay ID bằng đối tượng của người khác trong cùng tenant và của tenant khác.
- [ ] Đối tượng con phải thuộc đúng đối tượng cha: `refundId` thuộc `paymentId`, `itemId` thuộc `orderId`, tài khoản nhận tiền thuộc hồ sơ được phép.
- [ ] Batch kiểm tra từng phần tử theo cùng chính sách; định nghĩa rõ toàn bộ thành công hoặc có kết quả từng phần, tránh thay đổi trái quyền trước khi phát hiện lỗi.
- [ ] Các endpoint tìm kiếm, xuất dữ liệu và tải tệp áp dụng cùng phạm vi truy cập với endpoint đọc một đối tượng.
- [ ] GraphQL, API nội bộ và endpoint cũ không có đường bỏ qua kiểm tra quyền.
- [ ] Tài khoản dịch vụ có phạm vi nghiệp vụ cụ thể; việc “gọi từ mạng nội bộ” không thay thế quyết định quyền.
- [ ] Lỗi trả về và dữ liệu phản hồi không vô tình tiết lộ trường nhạy cảm hoặc nội dung đối tượng ngoài phạm vi.

### 5.2. Quyền ở mức trường và phân tách nhiệm vụ

- [ ] DTO đầu vào dùng danh sách trường được phép thay đổi; loại trừ hoặc từ chối các trường như `ownerId`, `tenantId`, `approvedBy`, `paidAmount` và `role` nếu người gọi không có quyền.
- [ ] Đổi người nhận, tài khoản thanh toán hoặc chủ sở hữu có quy trình riêng nếu việc đó làm thay đổi rủi ro nghiệp vụ.
- [ ] Người tạo không thể tự duyệt thông qua endpoint khác, quyền kế thừa hoặc thao tác giả danh thiếu kiểm soát.
- [ ] Kiểm tra quyền phản ánh các yếu tố cần hiệu lực tại thời điểm quyết định; quy định rõ thời hạn hiệu lực của quyết định với job bất đồng bộ.
- [ ] Nếu quyền bị thu hồi hoặc thành viên chuyển đơn vị, hành động mới tuân theo chính sách hiện hành và quyết định đã xếp hàng được xử lý theo quy tắc đã công bố.
- [ ] Quyền quản trị không mặc nhiên cho phép sửa lịch sử giao dịch hoặc bỏ giới hạn tổng tiền đã hoàn.
- [ ] Kiểm tra cả ủy quyền tạm thời và thao tác thay mặt; ghi được người thật thực hiện và chủ thể được đại diện.

**Bằng chứng cần có:** ma trận vai trò–hành động–đối tượng, mã quyết định quyền và kết quả kiểm thử đổi ID. UUID khó đoán chỉ giảm khả năng đoán ID; nó không chứng minh người gọi có quyền đối với ID đã biết.

## 6. Checklist giá, số lượng và chuyển dịch giá trị

### 6.1. Dữ liệu quyết định giá

- [ ] Giá, phí, thuế, chiết khấu và tổng tiền được tính hoặc xác nhận ở máy chủ từ nguồn được phép.
- [ ] Trường tổng tiền từ client chỉ dùng theo hợp đồng đã định, chẳng hạn đối chiếu thay đổi giá; không trở thành giá trị được thu hoặc hoàn một cách mặc định.
- [ ] Báo giá có danh tính, phạm vi sử dụng, nội dung, thời hạn và revision cần thiết; việc chấp nhận báo giá kiểm tra đủ các điều kiện đó.
- [ ] Đơn vị tiền và currency được lưu, kiểm tra và đối chiếu xuyên suốt; không so sánh các số thuộc hai currency khác nhau.
- [ ] Sử dụng kiểu số chính xác phù hợp: số nguyên theo đơn vị nhỏ nhất hoặc số thập phân có quy tắc scale và làm tròn rõ ràng.
- [ ] Từ chối số âm, số không khi không hợp lệ, số quá lớn, vượt độ chính xác và các biểu diễn không hợp lệ trước khi tạo hiệu ứng nghiệp vụ.
- [ ] Phép cộng và phép nhân có xử lý tràn số, giới hạn độ lớn và làm tròn nhất quán; không để lỗi kỹ thuật biến thành giá âm hoặc giá rẻ bất thường.
- [ ] Snapshot giá tại thời điểm cam kết được lưu nếu nghiệp vụ yêu cầu; thay đổi bảng giá sau đó không viết lại ý nghĩa giao dịch lịch sử.

### 6.2. Khuyến mại, hạn mức và tài nguyên

- [ ] Coupon được kiểm tra chủ thể, sản phẩm, thời gian, số lần dùng và khả năng kết hợp với ưu đãi khác.
- [ ] Giới hạn dùng coupon, mua hàng hoặc nhận thưởng được cập nhật nguyên tử dưới tải đồng thời.
- [ ] Các ngưỡng theo ngày, tài khoản, khách hàng hoặc nhóm liên quan có định nghĩa múi giờ và danh tính tính hạn mức.
- [ ] Chia một thao tác lớn thành nhiều thao tác nhỏ không né được ngưỡng phê duyệt hoặc hạn mức tích lũy mà nghiệp vụ yêu cầu.
- [ ] Giữ hàng, giải phóng hàng và xác nhận mua không khiến một đơn vị tồn kho được cấp cho hai đơn.
- [ ] Hủy đơn, hoàn tiền và rollback không cộng lại ưu đãi, điểm thưởng hoặc hàng tồn nhiều lần.
- [ ] Cơ chế khách hàng mới, dùng thử và giới thiệu có mô hình lạm dụng phù hợp; ghi nhận giới hạn của việc nhận diện nhiều tài khoản cùng một người.
- [ ] Các thao tác miễn phí nhưng tốn tài nguyên, như giữ chỗ hoặc tạo bản xuất, có quota và cơ chế hết hạn phù hợp.

**Tình huống mẫu:** tạo giỏ có hai mặt hàng, thay `unitPrice`, `discount`, `currency` và số lượng trong request rồi xác nhận. Đánh giá cả số tiền gửi tới cổng thanh toán và dữ liệu cuối cùng; một response hiển thị tổng đúng không đủ nếu payload gửi đối tác vẫn dùng tổng do client cung cấp.

## 7. Checklist transaction, tính đồng thời và TOCTOU

TOCTOU là khoảng hở giữa lúc kiểm tra và lúc sử dụng dữ liệu. Ví dụ: hai worker cùng thấy còn 100.000 VND có thể hoàn, rồi mỗi worker tạo một refund 80.000 VND. Từng lần kiểm tra đều đúng trên dữ liệu đã đọc, nhưng tổng kết quả sai.

### 7.1. Ranh giới nguyên tử

- [ ] Mỗi invariant được gắn với tập dữ liệu cần cập nhật nguyên tử hoặc giao thức nhất quán đã chọn.
- [ ] Xác định rõ mức cô lập và hành vi thực tế của cơ sở dữ liệu đang dùng; không suy rằng `@Transactional` tự ngăn mọi race condition.
- [ ] Kiểm tra và ghi cùng dựa trên một cơ chế bảo vệ: khóa hàng, cập nhật có điều kiện, kiểm tra version hoặc cơ chế tuần tự hóa tương đương.
- [ ] Các đường ghi cạnh tranh cùng tuân thủ cơ chế; khóa payment ở một endpoint không bảo vệ endpoint khác ghi refund mà không khóa payment.
- [ ] Kiểm tra `affected rows` hoặc kết quả version; xung đột không được coi như thành công.
- [ ] Các unique constraint cần thiết được tạo ở cơ sở dữ liệu; thao tác “tìm trước, rồi insert” không thay thế tính duy nhất khi có cạnh tranh.
- [ ] Deadlock và lỗi tuần tự hóa có chính sách retry hữu hạn; retry không nhân đôi hiệu ứng bên ngoài.
- [ ] Thứ tự lấy khóa được thống nhất khi một nghiệp vụ chạm nhiều đối tượng.
- [ ] Dữ liệu chỉ có trong cache hoặc replica trễ không được dùng như quyết định cuối cùng cho hạn mức cứng.
- [ ] Công việc bên ngoài kéo dài không giữ transaction mở nếu có thể tổ chức thành lệnh bền vững và xử lý bất đồng bộ.

### 7.2. Ví dụ giữ hạn mức hoàn bằng cập nhật có điều kiện

Đoạn SQL sau minh họa một phần cơ chế, không phải triển khai hoàn chỉnh:

```sql
UPDATE payment_balance
SET reserved_refund_minor = reserved_refund_minor + :amount_minor,
    version = version + 1
WHERE payment_id = :payment_id
  AND tenant_id = :tenant_id
  AND currency = :currency
  AND :amount_minor > 0
  AND captured_minor - successful_refund_minor - reserved_refund_minor
      >= :amount_minor;
```

Chỉ được tiếp tục khi cập nhật đúng một hàng. `payment_id` cần có tính duy nhất phù hợp; quyền trên payment, trạng thái thanh toán và revision phê duyệt vẫn phải được kiểm tra bằng cơ chế nhất quán trong cùng nghiệp vụ. Kiểu dữ liệu và giới hạn giá trị phải ngăn tràn số.

Trong cùng transaction cục bộ, hệ thống cần ghi refund ở trạng thái chờ, gắn `command_id` có ràng buộc duy nhất, chuyển trạng thái yêu cầu hợp lệ và ghi lệnh gửi đi. Nếu tạo refund hoặc ghi lệnh thất bại, phần giữ phải rollback theo. Không được commit phần giữ rồi hy vọng bước tạo refund luôn thành công.

Khi nhận kết quả thành công, chuyển số tiền tương ứng từ `reserved_refund_minor` sang `successful_refund_minor` trong cùng transaction với việc kết thúc refund. Khi thất bại dứt khoát, giải phóng phần giữ. Cả hai đường phải có điều kiện trạng thái để xử lý lặp lại không cộng hoặc trừ thêm lần nữa. Khi chưa rõ kết quả phía đối tác, duy trì trạng thái đối soát theo thiết kế thay vì tự động giải phóng và phát lệnh mới.

### 7.3. Kiểm thử đồng thời có kiểm soát

- [ ] Chuẩn bị nhiều request cùng vượt điều kiện ban đầu nhưng tổng giá trị vượt giới hạn nếu tất cả cùng thành công.
- [ ] Đồng bộ thời điểm bắt đầu bằng barrier hoặc cơ chế kiểm thử tương đương; kiểm thử tuần tự không chứng minh xử lý race đúng.
- [ ] Thử hai hành động khác nhau cạnh tranh trên cùng đối tượng, chẳng hạn hủy và thực thi, hoặc hai mức hoàn tiền.
- [ ] Sau khi mọi worker và tác vụ liên quan kết thúc, đọc trạng thái từ nguồn có thẩm quyền và tính lại invariant.
- [ ] Kiểm tra số lệnh, bản ghi, thông báo và lời gọi đối tác; không chỉ đếm response thành công.
- [ ] Nếu không tái hiện được cạnh tranh hoặc không quan sát được kết quả cuối, ghi “Chưa đủ bằng chứng”.

Không đặt mặc định rằng mọi request thua cuộc đều phải trả cùng một mã HTTP. Một số có thể nhận xung đột, một số nhận kết quả đã có và một số cần retry có kiểm soát. Tiêu chí bất biến là tổng kết quả nghiệp vụ không vượt quyền và giới hạn đã định.

## 8. Checklist idempotency, retry và yêu cầu trùng

Idempotency bảo đảm lặp lại một thao tác logic không làm tăng thêm hiệu ứng nghiệp vụ ngoài hợp đồng. Nó không tự làm mọi lời gọi mạng trở thành “đúng một lần”. Khi có nhiều dịch vụ, hệ thống vẫn cần danh tính lệnh, deduplication, quản lý trạng thái và đối soát.

### 8.1. Hợp đồng khóa idempotency

- [ ] Xác định điểm vào nào cần khóa: thanh toán, hoàn tiền, đặt lệnh hoặc hành động khác có giá trị.
- [ ] Định nghĩa phạm vi khóa bằng tenant, chủ thể hoặc client nghiệp vụ thích hợp và loại thao tác; khóa của người khác không được trả về dữ liệu trái quyền.
- [ ] Xác thực và kiểm tra quyền trước khi tiết lộ kết quả đã lưu; việc cache phản hồi không trở thành đường bỏ qua quyền truy cập.
- [ ] Khóa gắn với fingerprint của dữ liệu có ý nghĩa nghiệp vụ: đối tượng, số tiền, currency, người nhận và revision thích hợp.
- [ ] Cùng khóa nhưng payload khác bị từ chối theo hợp đồng; không trả “thành công cũ” cho một lệnh khác.
- [ ] Fingerprint được tạo từ biểu diễn chuẩn hóa ổn định, có phân biệt các giá trị mang ý nghĩa khác nhau; không phụ thuộc thứ tự trường JSON tùy ý.
- [ ] Việc nhận quyền xử lý khóa đầu tiên là nguyên tử và có unique constraint phù hợp.
- [ ] Hai request cùng khóa khi đang xử lý có hành vi được quy định: chờ có giới hạn, trả trạng thái đang xử lý hoặc xung đột có thể retry.
- [ ] Kết quả và trạng thái idempotency được lưu bền vững theo ranh giới commit; không chỉ nằm trong bộ nhớ của một instance.
- [ ] Quy định rõ khi nào lỗi được lưu, khi nào được retry và cách tra cứu trường hợp kết quả chưa rõ.
- [ ] Thời hạn lưu khóa dựa trên cửa sổ retry, giao lại sự kiện và nghĩa vụ lưu vết; có cơ chế bảo vệ nghiệp vụ sau khi khóa hết hạn.
- [ ] Có giới hạn độ dài khóa, số khóa và dữ liệu phản hồi được lưu để tránh lạm dụng tài nguyên.

Một khóa do client tự tạo chỉ nhận diện lần thử. Nếu client cố tình đổi khóa cho cùng một lệnh hoàn tiền, khóa idempotency ở HTTP không đủ ngăn trùng. Cần thêm danh tính nghiệp vụ như `refund_request_id` hoặc `command_id`, trạng thái yêu cầu và ràng buộc duy nhất phù hợp. Ngược lại, hai refund hợp lệ cho cùng payment không nhất thiết là trùng; quy tắc duy nhất phải phân biệt lệnh với đối tượng cha.

### 8.2. Các cửa sổ lỗi phải kiểm tra

| Thời điểm lỗi hoặc retry | Điều phải chứng minh |
| --- | --- |
| Hai request cùng đến trước khi lưu khóa | Chỉ một request sở hữu quyền thực thi cùng lệnh logic. |
| Client timeout sau khi server đã commit | Retry tìm được kết quả hoặc trạng thái của lệnh cũ. |
| Commit xong nhưng chưa trả response | Không tạo thêm refund, giữ hàng hoặc thu tiền ở lần thử sau. |
| Worker chết sau khi gửi lệnh đối tác | Worker mới tra cứu hoặc retry bằng cùng danh tính lệnh theo hợp đồng đối tác. |
| Cùng khóa, thay số tiền hoặc người nhận | Lệnh mới không được thực thi dưới kết quả của lệnh cũ. |
| Đổi khóa nhưng giữ cùng yêu cầu nghiệp vụ | Cơ chế chống trùng nghiệp vụ vẫn chặn hiệu ứng lần hai. |
| Khóa hết hạn hoặc dữ liệu dedup bị dọn | Quy tắc nghiệp vụ dài hạn vẫn giữ; không mở lại hành động đã kết thúc. |

**Bằng chứng cần có:** hợp đồng idempotency, schema lưu khóa, ràng buộc duy nhất, chính sách dọn dữ liệu và kiểm thử lỗi tại các ranh giới commit. Việc nhìn thấy header trong request chưa phải bằng chứng.

## 9. Checklist tích hợp ngoài, webhook và tác vụ bất đồng bộ

### 9.1. Xác thực nguồn và liên kết nghiệp vụ

- [ ] Webhook được xác thực theo hợp đồng đối tác; chữ ký được kiểm tra trên đúng dữ liệu yêu cầu mà cơ chế ký quy định.
- [ ] Bí mật ký, tài khoản đối tác và môi trường được phân tách phù hợp; webhook test không thể cập nhật thanh toán thật.
- [ ] Có chính sách chống replay theo khả năng của giao thức; chỉ kiểm tra chữ ký không ngăn phát lại một sự kiện hợp lệ.
- [ ] Đối chiếu mã giao dịch, tài khoản nhận, tenant, đối tượng, số tiền và currency cần thiết trước khi ghi nhận kết quả.
- [ ] Không tin trang chuyển hướng từ trình duyệt như bằng chứng duy nhất rằng thanh toán đã thành công.
- [ ] Mỗi sự kiện có danh tính được dedup trong đúng phạm vi đối tác, tài khoản và môi trường.
- [ ] Sự kiện cũ hoặc sai thứ tự không làm lùi trạng thái hoặc thực hiện lại tác dụng phụ đã kết thúc.
- [ ] Khi dữ liệu mâu thuẫn, xử lý theo nguồn có thẩm quyền và quy tắc đối soát, không tự chọn sự kiện đến sau cùng chỉ vì thời điểm nhận muộn hơn.

### 9.2. Giao nhận và hiệu ứng ngoài transaction

- [ ] Lệnh cần gửi được lưu bền vững cùng transaction với thay đổi nghiệp vụ, chẳng hạn qua transactional outbox hoặc cơ chế tương đương.
- [ ] Worker có thể giao lại lệnh; phía nhận dùng danh tính ổn định và cơ chế xử lý lặp phù hợp.
- [ ] Dedup sự kiện và thay đổi dữ liệu cục bộ được commit nhất quán để không tạo khoảng hở mất xử lý hoặc xử lý hai lần.
- [ ] Xác nhận đã nhận webhook được gửi sau khi đã ghi nhận bền vững dữ liệu cần xử lý; nếu chưa xử lý xong phải có hàng đợi và đường phục hồi rõ ràng.
- [ ] Retry có giới hạn, backoff và phân loại lỗi; một retry không được đổi danh tính lệnh khiến đối tác coi là thao tác mới.
- [ ] Tác vụ thất bại cuối cùng có nơi theo dõi và cơ chế xử lý lại; xử lý thủ công vẫn giữ quyền, invariant và dấu vết.
- [ ] Bước bù trừ cũng idempotent, có giới hạn nghiệp vụ và có thể theo dõi đến kết quả cuối.
- [ ] Có đối soát cho trạng thái không rõ: phía đối tác đã làm nhưng nội bộ chưa biết, hoặc nội bộ ghi nhận trước khi nhận đủ bằng chứng.

Transactional outbox bảo vệ việc không làm mất ý định gửi sau khi transaction cục bộ commit. Nó vẫn có thể gửi nhiều lần, nên không thay thế dedup hoặc idempotency ở phía nhận. Tương tự, rollback cơ sở dữ liệu không thu hồi được email đã gửi hoặc lệnh chuyển tiền đã thành công ở một hệ thống khác.

### 9.3. Tình huống mẫu

Gửi lại webhook hoàn tiền thành công ba lần, rồi gửi một sự kiện `pending` cũ của cùng giao dịch. Kết quả mong đợi: refund vẫn kết thúc đúng, tổng tiền đã hoàn tăng một lần, phần giữ giảm một lần và không tạo thêm lệnh hoàn. Nếu có thông báo hoặc bút toán liên quan, chúng phải tuân theo hợp đồng chống trùng đã định.

Một webhook có chữ ký hợp lệ nhưng số tiền hoặc tài khoản đối tác không khớp phải được đưa vào đường xử lý mâu thuẫn phù hợp; không ghi thành công chỉ dựa vào trường `status`.

## 10. Checklist lạm dụng luồng hợp lệ và khả năng phát hiện

Không phải hành vi có hại nào cũng cần sửa payload. Kẻ lạm dụng có thể gửi nhiều yêu cầu hợp lệ, chia nhỏ giao dịch, giữ tài nguyên không sử dụng hoặc kết hợp các tính năng theo cách chưa được dự kiến.

- [ ] Xác định giới hạn nghiệp vụ riêng cho thao tác nhạy cảm: số lần tạo yêu cầu, số tiền tích lũy, số chỗ giữ, số lần nhận ưu đãi hoặc số tác vụ nặng.
- [ ] Hạn mức dựa trên danh tính phù hợp với quy tắc, không chỉ địa chỉ IP; cân nhắc nhiều tài khoản khi nghiệp vụ yêu cầu nhưng không giả định hệ thống luôn xác định được cùng một người.
- [ ] Rate limit và quota có phạm vi nhất quán giữa các instance và điểm vào có thể thay thế nhau.
- [ ] Kiểm tra cách chia nhỏ hoặc kết hợp thao tác có thể vượt ngưỡng phê duyệt, phí tối thiểu hoặc hạn mức cộng dồn.
- [ ] Tài nguyên được giữ có thời hạn và đường giải phóng an toàn; job dọn dữ liệu không giải phóng nhầm tài nguyên đã được sử dụng.
- [ ] Audit trail ghi được ai làm gì, trên đối tượng nào, tenant nào, trước và sau ra sao, lý do và mã liên kết yêu cầu.
- [ ] Tác vụ bất đồng bộ giữ được nguồn gốc của lệnh và người khởi tạo để điều tra, thay vì chỉ còn tên worker.
- [ ] Log tránh chứa token, bí mật, dữ liệu thanh toán hoặc payload nhạy cảm không cần thiết; quyền xem và thời hạn lưu được kiểm soát.
- [ ] Có tín hiệu phát hiện các mẫu quan trọng: từ chối quyền hàng loạt, xung đột idempotency, nhiều lệnh trên cùng đối tượng, trạng thái đối soát kéo dài và chênh lệch tổng giá trị.
- [ ] Cảnh báo gắn với người xử lý, truy vấn đối soát và hành động khắc phục cụ thể; log đơn thuần không bảo vệ invariant.

Rate limit có thể giảm tốc độ khai thác nhưng không sửa được quy tắc sai. Nếu một người có thể tự duyệt yêu cầu, chỉ cho họ gọi một lần mỗi phút vẫn cho phép một lần phê duyệt trái quyền mỗi phút.

## 11. Ma trận kiểm thử tình huống tấn công logic

Sử dụng dữ liệu có thể khôi phục và chỉ chạy trên phạm vi được cấp phép. Mỗi tình huống phải ghi rõ tiền điều kiện, các bước, kết quả mong đợi và truy vấn quan sát hậu quả. Những kiểm tra dưới đây tập trung vào thuộc tính nghiệp vụ; mã HTTP chỉ là một phần bằng chứng.

| Mã | Tình huống | Kết quả cần chứng minh |
| --- | --- | --- |
| `BL-01` | Gọi thẳng thực thi khi yêu cầu còn `DRAFT` hoặc `SUBMITTED`. | Không có lệnh ngoài, phần giữ hay chuyển trạng thái trái quy trình. |
| `BL-02` | Người tạo gọi endpoint duyệt yêu cầu của chính mình. | Chính sách phân tách nhiệm vụ được giữ ở mọi điểm vào. |
| `BL-03` | Duyệt rồi thay số tiền, người nhận hoặc revision trước khi thực thi. | Quyết định cũ không cấp quyền cho dữ liệu mới. |
| `BL-04` | Thay ID bằng đối tượng của người khác cùng tenant. | Không đọc, sửa hoặc tạo tác dụng phụ vượt quyền đối tượng. |
| `BL-05` | Thay tenant và ID bằng đối tượng ở tenant khác. | Không có dữ liệu hoặc hiệu ứng chéo tenant. |
| `BL-06` | Gửi `ownerId`, `approvedBy`, `status` hoặc giá tự chọn vào API sửa chung. | Chỉ các trường được phép có hiệu lực; quy tắc quyền và giá vẫn đúng. |
| `BL-07` | Hoàn 80.000 VND và 80.000 VND đồng thời khi chỉ còn 100.000 VND. | Tổng thành công cộng phần giữ không vượt 100.000 VND. |
| `BL-08` | Gửi đồng thời nhiều request cùng khóa và payload. | Một lệnh logic, phản hồi hoặc trạng thái theo hợp đồng idempotency. |
| `BL-09` | Giữ nguyên khóa nhưng đổi số tiền hoặc người nhận. | Phát hiện xung đột payload, không phát lệnh khác. |
| `BL-10` | Đổi khóa nhưng giữ cùng `refund_request_id`. | Không có refund thứ hai cho cùng lệnh nghiệp vụ. |
| `BL-11` | Ngắt kết nối sau commit rồi retry. | Kết quả tìm lại được, số lần chuyển dịch giá trị không tăng. |
| `BL-12` | Gửi webhook trùng, sai thứ tự và có dữ liệu không khớp. | Không cộng tiền lặp, không lùi trạng thái; mâu thuẫn được xử lý rõ ràng. |
| `BL-13` | Hủy và thực thi cùng lúc. | Chỉ nhánh hợp lệ thắng; trạng thái và tác dụng phụ không mâu thuẫn. |
| `BL-14` | Đổi quyền người dùng trước một hành động mới hoặc khi lệnh đang chờ. | Quyết định phù hợp chính sách hiệu lực quyền đã quy định. |
| `BL-15` | Chia giao dịch để né ngưỡng hoặc dùng coupon từ nhiều request song song. | Giới hạn cộng dồn và số lần dùng được giữ. |
| `BL-16` | Cho khóa idempotency hết hạn rồi gửi lại lệnh đã kết thúc. | Cơ chế dài hạn vẫn ngăn hiệu ứng trùng không được phép. |
| `BL-17` | Gọi cùng thao tác qua API cũ, batch hoặc công cụ vận hành. | Không có đường ghi bỏ qua invariant hay quyền. |
| `BL-18` | Dừng worker giữa khi đối tác thành công và nội bộ ghi nhận. | Có thể phục hồi, tra cứu hoặc đối soát mà không tạo giao dịch mới. |

### Mẫu kịch bản Given–When–Then

```text
Given:
  Payment P thuộc tenant T, đã thu 100.000 VND.
  Tổng hoàn thành công = 0, phần giữ cho hoàn tiền = 0.
  Hai yêu cầu R1 và R2 khác nhau, mỗi yêu cầu 80.000 VND,
  đã được duyệt hợp lệ bởi người đủ quyền.

When:
  Hai worker bắt đầu thực thi R1 và R2 đồng thời từ cùng một barrier.
  Thu thập kết quả sau khi xử lý và các tác vụ liên quan ổn định.

Then:
  successful_refund + reserved_refund <= 100.000 VND.
  Tối đa một trong hai yêu cầu được giữ đủ tiền để thực thi.
  Không phát hai lệnh hoàn 80.000 VND thành công ra đối tác.
  Yêu cầu thua cuộc có trạng thái và lý do phù hợp để người vận hành hiểu.
  Bản ghi refund, phần giữ, outbox và audit trail không mâu thuẫn.
```

Để kiểm thử có giá trị, phải quan sát dữ liệu thực và hiệu ứng bên ngoài bằng công cụ thử nghiệm phù hợp. Một test mock mọi kho dữ liệu trả về “đủ tiền” không thể chứng minh cơ chế cạnh tranh của cơ sở dữ liệu. Một test chỉ kiểm tra response cũng có thể bỏ sót việc server đã gửi tiền trước khi trả lỗi.

## 12. Ví dụ audit xuyên suốt: phê duyệt và thực thi hoàn tiền

### 12.1. Mô hình giả định

Hệ thống có `refund_request`, `approval_decision`, `refund`, bảng tổng hợp số tiền của payment và outbox. Người hỗ trợ tạo yêu cầu, người quản lý duyệt trong hạn mức của mình, worker gửi lệnh tới đối tác. Một quyết định duyệt chỉ có hiệu lực với revision được duyệt. Yêu cầu đã đưa vào thực thi không được sửa trực tiếp các trường giá trị.

Hồ sơ audit cho luồng này cần liên kết được:

1. `refund_request_id`, tenant và payment nguồn.
2. Revision chứa số tiền, currency, người nhận hoặc thông tin đích được phép.
3. Danh tính người tạo, người duyệt và thẩm quyền tại lúc quyết định.
4. `command_id` ổn định cùng bản ghi refund và lệnh outbox.
5. Mã giao dịch đối tác, sự kiện nhận về và kết quả đối soát.

### 12.2. Trình tự thực thi để đối chiếu thiết kế

Đây là giả mã phục vụ audit, không phải mã Java có thể chạy trực tiếp. Hàm “khóa” có nghĩa là thiết kế đã chọn một cơ chế đồng thời thực sự bảo vệ đối tượng; việc đặt tên hàm không tự tạo ra tính nguyên tử.

```text
executeRefund(actor, requestId, idempotencyKey, payload):
  xác thực actor, kiểm tra cấu trúc và giới hạn đầu vào

  bắt đầu transaction cục bộ
    tải yêu cầu theo tenant và khóa/phối hợp phiên bản theo thiết kế
    kiểm tra actor có quyền thực thi trên yêu cầu này

    nhận khóa idempotency trong phạm vi thích hợp
    nếu là khóa cũ:
      đối chiếu fingerprint và quyền truy cập kết quả
      trả kết quả/trạng thái đã có theo hợp đồng, không tạo hiệu ứng mới

    nếu command nghiệp vụ này đã tồn tại:
      liên kết lần thử với command cũ và trả trạng thái phù hợp
    ngược lại:
      kiểm tra trạng thái cho phép thực thi
      kiểm tra quyết định duyệt khớp revision và điều kiện hiệu lực
      kiểm tra dữ liệu tiền và currency từ nguồn máy chủ
      giữ hạn mức hoàn một cách nguyên tử
      tạo refund với command_id duy nhất
      chuyển yêu cầu sang EXECUTION_PENDING có điều kiện
      ghi outbox với cùng command_id

    ghi kết quả tiếp nhận lệnh và liên kết vào bản ghi idempotency
  commit

  trả mã lệnh và trạng thái đã commit

worker gửi outbox:
  dùng cùng command_id khi gọi hoặc tra cứu ở đối tác
  ghi nhận thành công/thất bại dứt khoát bằng chuyển trạng thái có điều kiện
  với timeout chưa rõ: chuyển sang đường tra cứu/đối soát
```

Ở đây kết quả tiếp nhận lệnh không đồng nghĩa hoàn tiền đã thành công. API cần thể hiện sự khác nhau đó. Nếu xử lý idempotency bằng transaction hoặc kho riêng, audit phải xem thêm các khoảng hở giữa hai lần commit, cơ chế tranh quyền, quyền sở hữu worker và phục hồi sau crash. Không thể coi các bước trên là nguyên tử chỉ vì chúng nằm gần nhau trong mã.

### 12.3. Ví dụ phát hiện và đề xuất sửa

**Hiện trạng:** endpoint thực thi đọc `APPROVED`, cộng tổng các refund hiện có để kiểm tra số tiền còn lại, sau đó gọi đối tác và mới lưu refund. Không có khóa theo payment, không có `command_id` duy nhất và không lưu ý định gửi trước khi gọi đối tác.

**Kịch bản:** hai yêu cầu đã được duyệt đều thấy còn đủ tiền. Chúng cùng gọi đối tác. Hoặc một yêu cầu được đối tác thực hiện thành công nhưng tiến trình chết trước khi lưu, khiến lần thử tiếp theo gửi một giao dịch mới.

**Hậu quả:** vượt tổng tiền được phép hoàn, thiếu dấu vết nội bộ hoặc hoàn lặp sau timeout.

**Hướng sửa:** giữ hạn mức nguyên tử trước khi phát lệnh; lưu refund, chuyển trạng thái và outbox trong transaction; định danh lệnh ổn định; xử lý lặp theo hợp đồng đối tác; bổ sung đường đối soát khi kết quả chưa rõ. Cần giữ cả quy tắc revision phê duyệt và quyền theo payment, thay vì chỉ giải quyết race condition.

**Điều kiện xác nhận sửa xong:** kịch bản đồng thời giữ đúng invariant; retry sau commit không tạo thêm lệnh; lỗi sau khi đối tác thực hiện được phục hồi bằng tra cứu hoặc retry có cùng danh tính; dữ liệu cuối và audit trail đối chiếu được.

## 13. Ghi nhận phát hiện và xác định mức ưu tiên

Mỗi phát hiện cần mô tả một quy tắc bị vi phạm và đường tái hiện cụ thể. “Thiếu validate” hoặc “nên thêm lock” quá chung để người phát triển biết điều cần bảo vệ.

```text
Mã: BL-AUD-017
Quy tắc: INV-REFUND-01
Phạm vi: thực thi hoàn tiền qua API và worker
Tiền điều kiện: hai yêu cầu hợp lệ trên cùng payment đã được duyệt
Bước tái hiện: chạy hai lệnh cùng lúc với tổng vượt số tiền còn lại
Kỳ vọng: chỉ giữ hạn mức trong giới hạn; không phát lệnh vượt tổng
Quan sát: hai lệnh được gửi; tổng hoàn thành công vượt captured_amount
Bằng chứng: dữ liệu thử, command_id, trace, bản ghi cuối, phiên bản ứng dụng
Tác động: mất tiền; có thể lặp lại trên các payment thỏa tiền điều kiện
Hướng sửa: bảo vệ invariant tại transaction và đường gửi lệnh
Xác nhận sửa: lặp lại tình huống và kiểm tra dữ liệu, lệnh ngoài, audit trail
```

Ưu tiên dựa trên tác động, khả năng khai thác, phạm vi đối tượng và khả năng phục hồi. Một lỗi chỉ cần tài khoản thường và gây chuyển tiền trái phép thường cần xử lý khẩn cấp. Một thiếu sót log có tác động khác, nhưng có thể tăng mức rủi ro nếu khiến việc phát hiện và đối soát thất thoát không thực hiện được. Không dùng độ dễ sửa để thay cho đánh giá mức nghiêm trọng.

Khi thiếu bằng chứng về cơ chế của đối tác hoặc chưa thể chạy kiểm thử đồng thời, ghi rõ phần chưa được xác minh. Không suy từ việc chưa thấy lỗi rằng quy tắc đã được bảo vệ.

## 14. Cổng kết luận cho checklist

Trước khi kết luận về luồng đã chọn, người thực hiện audit cần trả lời được các câu sau:

- [ ] Phạm vi và các đường ghi dữ liệu đã được liệt kê; ngoại lệ và phần chưa kiểm tra được ghi rõ.
- [ ] Mỗi invariant quan trọng có chủ sở hữu, định nghĩa chính xác, cơ chế cưỡng chế và bằng chứng.
- [ ] State machine ngăn bỏ bước, tái sử dụng phê duyệt cũ và chuyển trạng thái trái phép.
- [ ] Quyền được kiểm tra trên đối tượng, tenant, trường dữ liệu và nhiệm vụ thực tế.
- [ ] Dữ liệu giá, hạn mức và chuyển dịch giá trị có nguồn có thẩm quyền và quy tắc tính nhất quán.
- [ ] Có bằng chứng dưới cạnh tranh cho những invariant không thể chỉ chứng minh bằng kiểm thử tuần tự.
- [ ] Retry, request trùng, sự kiện trùng và lỗi giữa các hệ thống không tạo hiệu ứng nghiệp vụ lần hai trái phép.
- [ ] Timeout và trạng thái không rõ có đường phục hồi, đối soát và người chịu trách nhiệm.
- [ ] Phát hiện có bằng chứng tái hiện, mức ưu tiên và tiêu chí xác nhận khắc phục.
- [ ] Kết luận phân biệt rõ “Đạt”, “Không đạt”, “Chưa đủ bằng chứng” và “Không áp dụng”; không lấy tỷ lệ ô đã đánh dấu để che một invariant quan trọng đang sai.

Checklist chỉ có giá trị khi câu trả lời đi kèm bằng chứng. Đối tượng cần bảo vệ cuối cùng là quy tắc nghiệp vụ và kết quả mà người dùng, hệ thống và đối tác có thể quan sát sau mọi đường đi đã xem xét.
