# Lạm dụng tính năng hợp lệ — Abuse of valid features

## 1. Vì sao một tính năng hoạt động đúng vẫn có thể bị lạm dụng?

Trong chương **Business Logic Foundations** của học phần **Business Logic Security**, ta cần phân biệt hai câu hỏi: “Yêu cầu này có hợp lệ về kỹ thuật không?” và “Hệ thống có được phép tạo ra kết quả nghiệp vụ này không?”. Một yêu cầu có thể vượt qua xác thực, kiểm tra dữ liệu đầu vào và kiểm tra quyền cơ bản, nhưng vẫn góp phần tạo ra kết quả mà doanh nghiệp không chấp nhận.

**Abuse of valid features** là việc sử dụng tính năng có thật, với dữ liệu hoặc thao tác được hệ thống chấp nhận, để đạt lợi ích trái với quy tắc, mục đích hoặc giới hạn nghiệp vụ. Người thực hiện có thể lặp lại một thao tác, phối hợp nhiều tính năng, dùng nhiều tài khoản hoặc chọn thời điểm có lợi. Không nhất thiết có SQL injection, mã độc hay dữ liệu sai định dạng.

Ví dụ, một cửa hàng cho phép áp mã giảm giá, thanh toán và trả hàng từng phần. Cả ba tính năng đều cần thiết. Nếu dịch vụ hoàn tiền trả lại giá niêm yết của món hàng thay vì phần tiền đã phân bổ cho món đó sau giảm giá, người mua có thể giữ lại hàng với số tiền thực trả thấp hơn chính sách cho phép. Từng API trả về thành công, nhưng toàn bộ quy trình vi phạm quy tắc tài chính.

Sau bài này, bạn cần có khả năng:

- Nhận diện việc lạm dụng một tính năng hợp lệ theo đối tượng, chuỗi thao tác, số lượng, thời gian và tác động kinh tế.
- Chuyển mô tả như “không cho gian lận hoàn tiền” thành các điều kiện có thể kiểm tra ở phía máy chủ.
- Phân biệt quyền theo đối tượng, state machine, transaction và idempotency trong cùng một phương án bảo vệ.
- Thiết kế kiểm thử chứng minh rằng nhiều thao tác hợp lệ không thể tạo ra trạng thái nghiệp vụ bị cấm.

## 2. Hợp lệ ở tầng nào?

Một API không thể kết luận an toàn chỉ từ mã HTTP 200 hoặc việc người gọi đã đăng nhập.

| Tầng kiểm tra | Câu hỏi cần trả lời | Điều vẫn có thể bị bỏ sót |
| --- | --- | --- |
| Cú pháp | JSON có đúng cấu trúc, số tiền có đúng định dạng? | Số tiền đúng định dạng nhưng sai chính sách hoàn tiền |
| Xác thực | Người gọi là ai? | Tài khoản thật vẫn có thể lạm dụng chương trình giới thiệu |
| Quyền theo chức năng | Người gọi có vai trò được tạo yêu cầu hoàn tiền? | Nhân viên có quyền tiếp nhận nhưng không có quyền tự duyệt |
| Quyền theo đối tượng | Người gọi có được thao tác trên đơn, tenant và khoản thanh toán cụ thể này? | Chủ đơn vẫn có thể gửi nhiều yêu cầu vượt tổng tiền được hoàn |
| Quy tắc nghiệp vụ | Tổng kết quả có tuân thủ giới hạn tài chính, số lượt, thời hạn và quy trình? | Quy tắc đúng trong một request nhưng bị phá khi có request đồng thời |
| Thực thi nhất quán | Điều kiện có được giữ khi retry, chạy song song và gọi dịch vụ ngoài? | Hai worker cùng thực hiện một tác động đã được duyệt |

Các tầng này bổ sung cho nhau. Kiểm tra quyền theo đối tượng là bắt buộc, nhưng chủ sở hữu hợp lệ vẫn phải tuân thủ hạn mức và trạng thái. Tương tự, một giao dịch cơ sở dữ liệu không tự hiểu quy tắc “không được hoàn nhiều hơn số tiền còn được hoàn”. Lập trình viên phải biểu diễn và thực thi quy tắc đó.

Không nên đồng nhất mọi hành vi gây thiệt hại với một lỗ hổng đã xác nhận. Nếu chính sách cho phép một người nhận thưởng không giới hạn thì trước hết cần làm rõ chính sách. Nếu chính sách đã quy định một lần nhưng hệ thống cho nhận nhiều lần thì đó là khoảng cách giữa quy tắc và cách thực thi. Kiểm soát rủi ro cũng có thể được bổ sung cho hành vi chưa bị cấm rõ ràng, với tiêu chí và quy trình xử lý minh bạch.

## 3. Nhìn theo tính năng, chuỗi thao tác và tác động

Một cách phân tích hữu ích là bắt đầu từ câu hỏi: **Người dùng có thể kết hợp những quyền sẵn có nào để tạo ra kết quả vượt giới hạn?**

| Tính năng hợp lệ | Cách có thể bị lạm dụng | Quy tắc cần xác định |
| --- | --- | --- |
| Giảm giá cho khách mới | Tạo nhiều tài khoản để hưởng lại ưu đãi | “Khách mới” được xác định theo chủ thể nào và xử lý nhầm lẫn ra sao? |
| Hoàn tiền từng phần | Gửi nhiều yêu cầu riêng, mỗi yêu cầu nhỏ hơn giá trị đơn | Tổng tiền đã hoàn và đang giữ chỗ không vượt ngân sách hoàn tiền |
| Giữ chỗ khi đặt hàng | Liên tục gia hạn hoặc tạo lại giữ chỗ để chiếm hàng | Thời hạn, tổng số lượng và ngân sách giữ chỗ theo chủ thể |
| Xuất báo cáo | Tạo nhiều tác vụ xuất dữ liệu lớn bằng tài khoản có quyền | Phạm vi dữ liệu và ngân sách tài nguyên phù hợp với quyền sử dụng |
| Giới thiệu bạn bè | Tự giới thiệu qua các tài khoản liên quan rồi rút thưởng | Điều kiện người được giới thiệu đủ tư cách và thời điểm thưởng có hiệu lực |
| Đề nghị và phê duyệt | Người đề nghị dùng quyền khác để tự duyệt hồ sơ của mình | Tách biệt người đề nghị với người duyệt nếu quy trình yêu cầu |
| Hủy đơn hoặc trả hàng | Nhận thưởng từ giao dịch rồi đảo ngược giao dịch gốc | Thưởng chỉ được quyết toán hoặc thu hồi theo trạng thái giao dịch gốc |

Không phải bảng nào cũng cần một lệnh cấm tuyệt đối. Một khách hàng có thể mua số lượng lớn hợp pháp; một công ty có thể có nhiều nhân viên chung địa chỉ IP. Mục tiêu là xác định chính xác quyền lợi, chi phí, phạm vi và điều kiện, sau đó chọn kiểm soát tương ứng.

### 3.1. Lạm dụng không nhất thiết phải bỏ qua bước

Có ít nhất ba dạng khác nhau:

1. **Bỏ qua hoặc đảo thứ tự:** quyết toán trước khi duyệt, giao hàng trước khi xác nhận thanh toán.
2. **Đi đúng các bước nhưng phối hợp sai lợi ích:** mua, nhận thưởng, trả hàng, giữ thưởng dù chính sách yêu cầu thu hồi.
3. **Lặp lại hoặc tăng quy mô:** từng tác vụ xuất báo cáo đều được phép nhưng tổng tải làm cạn tài nguyên dùng chung.

State machine đặc biệt hữu ích cho dạng thứ nhất. Dạng thứ hai cần thêm quan hệ giữa các thực thể và sổ ghi nhận quyền lợi. Dạng thứ ba cần ngân sách, hạn mức và kiểm soát tài nguyên. Một sơ đồ trạng thái đúng cho từng đơn hàng chưa đủ để chặn việc một người tạo quá nhiều đơn giữ chỗ.

### 3.2. Các chiều cần thay đổi khi phân tích

- **Chủ thể:** một tài khoản, nhiều tài khoản, nhân viên và khách hàng, các tenant khác nhau.
- **Đối tượng:** một món hàng, nhiều dòng hàng, cùng khoản thanh toán, nhiều đơn cùng chương trình khuyến mãi.
- **Thời gian:** trước hoặc sau thanh toán, trước khi ghi sổ, sát thời điểm hết hạn, trước khi xử lý trả hàng xong.
- **Tần suất và đồng thời:** retry, gửi tuần tự, nhiều request chạy cùng lúc, nhiều worker xử lý lại.
- **Giá trị:** số tiền, số lượng tồn kho, số điểm thưởng, số phút tính toán, dung lượng dữ liệu xuất.

Những chiều này giúp tìm phần quy tắc còn thiếu mà không cần bắt đầu từ danh sách payload tấn công kỹ thuật.

## 4. Ví dụ xuyên suốt: trả hàng sau khi dùng mã giảm giá

Xét chính sách minh họa sau:

- Đơn hàng có hai món A giá 200.000 đồng và B giá 800.000 đồng.
- Mã giảm giá giảm 200.000 đồng cho cả đơn, được phân bổ theo tỷ lệ giá của các món đủ điều kiện.
- Khách thực trả 800.000 đồng; bỏ qua thuế và phí vận chuyển trong ví dụ này.
- Khi trả một món, khách được hoàn phần tiền đã trả phân bổ cho món đó, trừ phần đã hoàn trước đó.
- Chính sách ví dụ không tính lại ngưỡng hưởng mã khi khách trả hàng. Nếu sản phẩm thực tế có quy định thu hồi ưu đãi vì không còn đạt ngưỡng, đó phải là một quy tắc bổ sung được xác định rõ.

| Dòng hàng | Giá gốc | Giảm giá phân bổ | Phần tiền đã trả |
| --- | ---: | ---: | ---: |
| A | 200.000 | 40.000 | 160.000 |
| B | 800.000 | 160.000 | 640.000 |
| Tổng | 1.000.000 | 200.000 | 800.000 |

Nếu khách trả B nhưng hệ thống hoàn 800.000 đồng theo giá gốc, khách lấy lại toàn bộ số tiền đã trả và vẫn giữ A. Theo chính sách đã nêu, số tiền được hoàn cho B chỉ là 640.000 đồng.

Điểm sai nằm ở quan hệ giữa giá, giảm giá, thanh toán và hoàn tiền. Việc ẩn nút sửa giá trên giao diện không sửa được lỗi này. Từ chối số tiền âm cũng không sửa được lỗi vì 800.000 là một số dương hợp lệ.

### 4.1. Các đại lượng cần được máy chủ quyết định

Máy chủ cần lưu hoặc có khả năng tái dựng một cách xác định:

- Giá đã chốt tại thời điểm đặt hàng, số lượng và đơn vị tiền tệ.
- Khoản giảm giá phân bổ cho mỗi dòng hàng và phiên bản chính sách đã áp dụng.
- Số tiền thực thu theo từng khoản thanh toán và phần đã hoàn.
- Số lượng đủ điều kiện trả, số lượng đang xử lý trả và số lượng đã trả.
- Quyết định duyệt trả hàng và quyền của người thực hiện quyết định đó.

Không tính lại giá của giao dịch cũ bằng bảng giá hiện tại. Không lấy trường `unitPrice`, `discount` hoặc `refundableAmount` từ phía khách làm nguồn quyết định. Khách có thể gửi dòng hàng và số lượng muốn trả; máy chủ xác định quyền lợi tương ứng. Nếu API cho nhập số tiền theo nghiệp vụ của nhân viên hỗ trợ, số tiền đó vẫn phải được kiểm tra theo quyền và hạn mức phía máy chủ.

Khi có nhiều đơn vị hàng trong một dòng, việc làm tròn giảm giá phải nhất quán với đơn vị tiền tệ. Tổng các phần phân bổ phải khớp tổng tiền đã chốt. Không dùng phép chia làm tròn độc lập khiến tổng tiền hoàn của các lần trả nhỏ lớn hơn tiền thực trả ban đầu.

## 5. Chuyển mục đích kinh doanh thành invariant

**Business invariant** là điều kiện phải được giữ trong mọi trạng thái nghiệp vụ được chấp nhận. Câu “không cho hoàn tiền gian lận” chưa đủ cụ thể để lập trình hoặc kiểm thử.

Với mỗi khoản thanh toán và cùng một đơn vị tiền tệ, đặt:

- `C`: số tiền đã thực thu có thể dùng làm ngân sách hoàn tiền.
- `S`: số tiền hoàn đã được xác nhận thành công.
- `P`: số tiền đang được giữ cho các yêu cầu hoàn chưa có kết quả cuối cùng.
- `R`: số tiền muốn giữ cho yêu cầu hoàn mới.

Điều kiện chấp nhận yêu cầu mới là:

~~~text
R > 0
S >= 0
P >= 0
S + P + R <= C
~~~

Đây mới là giới hạn trên ở cấp thanh toán. Một yêu cầu còn phải thỏa ngân sách của dòng hàng, số lượng được phép trả và chính sách đã chốt. Việc ngân sách thanh toán còn dư không cho phép hoàn thêm cho một dòng hàng đã hoàn đủ.

| Phạm vi | Invariant minh họa | Thời điểm thực thi |
| --- | --- | --- |
| Đối tượng | Đơn, dòng hàng, hồ sơ trả và thanh toán thuộc cùng tenant, cùng giao dịch hợp lệ | Khi tải và trước khi thay đổi dữ liệu |
| Số lượng | Đã trả + đang giữ để trả + lượng mới không vượt lượng đã mua đủ điều kiện | Khi chấp nhận yêu cầu trả |
| Giá trị | Đã hoàn + đang giữ + yêu cầu mới không vượt ngân sách tương ứng | Khi giữ ngân sách hoàn |
| Trạng thái | Chỉ hồ sơ đã được duyệt mới được tạo tác động hoàn tiền | Khi chuyển trạng thái và tạo lệnh hoàn |
| Tách biệt nhiệm vụ | Người đề nghị không tự duyệt nếu chính sách quy định | Trong thao tác phê duyệt |
| Tính duy nhất | Một quyết định hoàn cụ thể chỉ tạo một lệnh tài chính | Trong cơ sở dữ liệu và khi gọi nhà cung cấp |

Mỗi invariant nên có chủ sở hữu nghiệp vụ, nguồn dữ liệu và nơi thực thi. Các ràng buộc quan trọng cần được kiểm tra tại nơi ghi dữ liệu có thẩm quyền, thay vì chỉ có trong controller hoặc giao diện.

## 6. Bốn cơ chế bảo vệ và giới hạn của chúng

### 6.1. Quyền theo đối tượng và quan hệ giữa đối tượng

Không chỉ kiểm tra rằng người gọi sở hữu `orderId`. Cần kiểm tra `lineItemId` thuộc đúng đơn, `returnCaseId` thuộc đúng dòng hàng và `paymentId` là khoản thanh toán liên quan. Nếu không, một người có thể ghép các mã định danh riêng lẻ hợp lệ thành một tổ hợp không được phép.

Tenant và danh tính người gọi phải đến từ ngữ cảnh xác thực đáng tin cậy. Không coi `tenantId` hoặc `userId` trong JSON là bằng chứng quyền sở hữu. Với nhân viên hỗ trợ, quyền còn có thể bị giới hạn theo chi nhánh, giá trị tiền, loại hồ sơ và trạng thái phê duyệt.

Khi thực thi một lần retry, vẫn phải kiểm tra quyền truy cập kết quả. Một khóa idempotency không được trở thành cách đọc phản hồi của người dùng khác.

### 6.2. State machine và điều kiện chuyển trạng thái

Một luồng minh họa cho hồ sơ hoàn tiền:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> APPROVED: Duyệt đúng quyền và đủ điều kiện
    REQUESTED --> REJECTED: Từ chối
    APPROVED --> REFUND_PENDING: Giữ ngân sách và ghi lệnh hoàn
    REFUND_PENDING --> REFUNDED: Nhà cung cấp xác nhận thành công
    REFUND_PENDING --> REFUND_FAILED: Nhà cung cấp xác nhận thất bại cuối cùng
    REFUND_FAILED --> APPROVED: Giải phóng khoản giữ và duyệt thử lại theo chính sách
~~~

Mỗi mũi tên cần điều kiện cụ thể. Không cho phía khách gửi một trạng thái đích bất kỳ rồi gán trực tiếp vào bản ghi. Hành động “duyệt” và “thực hiện hoàn” phải kiểm tra quyền, trạng thái nguồn, ngân sách và điều kiện liên quan.

Timeout khi gọi nhà cung cấp không chứng minh giao dịch hoàn đã thất bại. Khi chưa biết kết quả, giữ trạng thái chờ xác minh và tiếp tục giữ ngân sách. Nếu giải phóng ngân sách ngay rồi tạo lệnh khác, cả hai lệnh có thể cùng thành công.

### 6.3. Transaction và kiểm soát tranh chấp

Giả sử ngân sách còn lại là 640.000 đồng. Hai request đồng thời, mỗi request 400.000 đồng, đều có thể đọc thấy đủ tiền nếu kiểm tra và ghi nhận tách rời. Cuối cùng hệ thống chấp nhận tổng cộng 800.000 đồng.

Đưa mã vào transaction chưa đủ nếu các transaction vẫn đọc cùng số dư cũ mà không có cơ chế phát hiện hoặc ngăn tranh chấp. Tùy hệ quản trị và thiết kế, có thể dùng khóa hàng, cập nhật có điều kiện, optimistic locking với phiên bản hoặc mức cô lập thích hợp kèm xử lý retry.

Ví dụ sau minh họa **cập nhật có điều kiện trong PostgreSQL**, dùng số nguyên theo đơn vị tiền nhỏ nhất của đồng tiền đang xử lý:

~~~sql
UPDATE refund_budget
SET pending_minor = pending_minor + :amount_minor
WHERE tenant_id = :tenant_id
  AND payment_id = :payment_id
  AND currency = :currency
  AND :amount_minor > 0
  AND :amount_minor <= captured_minor - refunded_minor - pending_minor;
~~~

Chỉ khi số hàng bị cập nhật bằng 1 mới tiếp tục. Giá trị 0 có thể là ngân sách không đủ hoặc không có bản ghi phù hợp; lớp ứng dụng xử lý mà không tiết lộ dữ liệu trái quyền. Các placeholder ở đây biểu diễn tham số bind, không phải ghép chuỗi SQL.

Bảng ngân sách cần có khóa duy nhất theo tenant, khoản thanh toán và tiền tệ, cùng ràng buộc miền giá trị phù hợp. Việc giữ ngân sách, giữ quyền lợi theo dòng hàng, ghi bản ghi hoàn tiền và tạo lệnh cần cùng thành công hoặc cùng rollback trong transaction cục bộ. Các luồng khác thay đổi cùng ngân sách cũng phải tuân thủ cùng cơ chế nhất quán.

Nếu dùng khóa, cần có thứ tự khóa thống nhất khi một yêu cầu chạm nhiều dòng hàng và khoản thanh toán. Deadlock hoặc xung đột phiên bản có thể xảy ra; retry có giới hạn phải giữ nguyên ý nghĩa thao tác và không tạo thêm tác động tài chính.

### 6.4. Idempotency và tính duy nhất nghiệp vụ

**Idempotency** giúp một thao tác được gửi lại nhiều lần vẫn chỉ tạo một tác động nghiệp vụ dự kiến. Ví dụ, trình duyệt timeout rồi gửi lại cùng yêu cầu hoàn tiền với cùng khóa thì máy chủ trả lại cùng mã yêu cầu đã tạo.

Thiết kế khóa cần làm rõ:

- Phạm vi khóa gồm tenant, chủ thể được xác thực và loại thao tác.
- Khóa được gắn với fingerprint của nội dung nghiệp vụ đã chuẩn hóa, như hồ sơ trả hàng, số lượng và tiền tệ.
- Cùng khóa, cùng nội dung: trả kết quả đã lưu hoặc báo thao tác đang xử lý theo hợp đồng API.
- Cùng khóa, khác nội dung: từ chối xung đột, không âm thầm dùng kết quả cũ cho yêu cầu mới.
- Có ràng buộc duy nhất trong cơ sở dữ liệu để hai request cùng khóa không cùng thắng.

Idempotency không thay thế invariant. Người dùng có thể tạo hai khóa khác nhau cho hai yêu cầu hoàn cùng một món. Hệ thống vẫn phải bảo vệ tổng tiền, tổng số lượng và tính duy nhất của quyết định hoàn.

Thời gian lưu khóa cần phù hợp với cửa sổ retry. Khi khóa hết hạn, ràng buộc nghiệp vụ và sổ giao dịch vẫn phải ngăn tạo thêm quyền lợi. Chỉ lưu khóa vào cache ngắn hạn không đủ để bảo vệ một tác động tài chính tồn tại lâu hơn.

## 7. Minh họa tổ chức mã Java tại ranh giới nghiệp vụ

Đoạn mã sau là **mã khung minh họa**, chưa phải ứng dụng chạy độc lập. Các thành phần repository, phân quyền, idempotency và transaction phải được hiện thực theo hợp đồng mô tả bên dưới. Ví dụ chỉ nhận hồ sơ trả đã được duyệt với số tiền do máy chủ tính, không hỗ trợ phía khách tự đặt số tiền hoàn.

~~~java
record RefundCommand(String returnCaseId, String idempotencyKey) {}

record RefundAccepted(String refundId, String status) {}

public RefundAccepted requestRefund(Actor actor, RefundCommand command) {
    validateCommand(command);

    return transactions.required(() -> {
        var returnCase = returns.lockByTenantAndId(
                actor.tenantId(), command.returnCaseId());
        permissions.requireCanRequestRefund(actor, returnCase);

        var scope = new IdempotencyScope(
                actor.tenantId(), actor.subjectId(), "REQUEST_REFUND");
        var fingerprint = fingerprints.forReturnCase(command.returnCaseId());
        var replay = idempotency.claimOrReplay(
                scope, command.idempotencyKey(), fingerprint);
        if (replay.isPresent()) {
            return replay.get();
        }

        returnCase.requireApprovedAndNotSubmitted();
        var allocation = pricing.approvedRefundAllocation(returnCase);
        allocation.requirePositiveAmountsAndConsistentCurrency();

        // Atomic conditional updates; a failed reservation aborts the transaction.
        refundRights.reserveApprovedQuantities(returnCase, allocation);
        refundBudgets.reserveOrThrow(
                actor.tenantId(), returnCase.paymentId(), allocation);

        var refund = refunds.createPendingUniqueForDecision(
                returnCase.approvalDecisionId(), allocation);
        returns.markRefundPending(returnCase, refund.id());
        outbox.appendRefundRequested(refund.id());

        var result = new RefundAccepted(refund.id(), "REFUND_PENDING");
        idempotency.complete(scope, command.idempotencyKey(), result);
        return result;
    });
}
~~~

Các hợp đồng quan trọng của mã khung:

1. `lockByTenantAndId` tải đúng tenant và bảo vệ hồ sơ khỏi thay đổi cạnh tranh trong transaction. Kiểm tra quyền diễn ra trước khi trả kết quả replay.
2. `claimOrReplay` dùng lưu trữ có ràng buộc duy nhất, phân biệt nội dung khác nhau và xử lý trường hợp request khác đang giữ cùng khóa. Tạo dấu nhận khóa và hoàn tất kết quả phải gắn với transaction cục bộ. Nếu có tranh chấp làm transaction bị hủy, tầng ngoài phải kết thúc transaction đó trước khi đọc lại hoặc retry.
3. `approvedRefundAllocation` đọc snapshot hoặc sổ phân bổ đáng tin cậy. Nếu chính sách có thể thay đổi sau phê duyệt thì phải có phiên bản hoặc điều kiện tái phê duyệt rõ ràng.
4. Giữ số lượng và ngân sách phải nguyên tử trên các bản ghi dùng chung. Khóa một hồ sơ trả không tự khóa các hồ sơ khác cùng sử dụng một khoản thanh toán.
5. `createPendingUniqueForDecision` có ràng buộc duy nhất cho quyết định hoàn, nên đổi khóa idempotency cũng không tạo được lệnh thứ hai cho cùng quyết định. Chính sách ví dụ coi một quyết định duyệt là bất biến.
6. Transaction bao gồm cả bản ghi outbox và kết quả nhận yêu cầu. Khi một bước thất bại, các khoản giữ và bản ghi liên quan được rollback cùng nhau.

Trong triển khai Java, tiền nên dùng số nguyên theo đơn vị nhỏ nhất với kiểm tra tràn số, hoặc `BigDecimal` với scale và quy tắc làm tròn rõ ràng. Không dùng `double` để quyết định số tiền được hoàn. Không cộng trực tiếp các khoản khác tiền tệ.

## 8. Tác động bên ngoài: tránh hoàn hai lần khi worker xử lý lại

Transaction cơ sở dữ liệu cục bộ không bao trùm lời gọi tới nhà cung cấp thanh toán. Vì vậy, không thể suy luận rằng rollback cơ sở dữ liệu sẽ thu hồi một lệnh hoàn đã thành công bên ngoài.

Một luồng thực hiện phù hợp với ví dụ:

1. Transaction cục bộ giữ ngân sách, tạo `refundId`, chuyển hồ sơ sang chờ hoàn và ghi sự kiện outbox.
2. Worker đọc outbox sau commit và gửi lệnh tới nhà cung cấp với khóa ổn định suy ra từ `refundId`, nếu nhà cung cấp hỗ trợ idempotency với ngữ nghĩa phù hợp.
3. Worker có thể nhận lại cùng sự kiện. Mỗi lần xử lý vẫn dùng cùng mã giao dịch và cùng khóa, không sinh khóa mới.
4. Khi thành công được xác nhận, transaction cục bộ chuyển khoản giữ từ `pending` sang `refunded`, ghi sổ và đánh dấu kết quả đúng một lần.
5. Khi thất bại cuối cùng được xác nhận, transaction cục bộ giải phóng khoản giữ đúng một lần và cập nhật trạng thái theo chính sách.
6. Nếu kết quả chưa rõ, tiếp tục đối soát bằng mã giao dịch ổn định. Không giải phóng ngân sách chỉ vì timeout.

Outbox giúp không bỏ mất ý định xử lý sau commit; nó không tự bảo đảm tác động bên ngoài xảy ra đúng một lần. Cần kết hợp tính duy nhất của lệnh nghiệp vụ, khả năng idempotency hoặc truy vấn giao dịch của nhà cung cấp và đối soát. Nếu hệ thống bên ngoài không hỗ trợ các khả năng đó, phải thiết kế cơ chế xử lý trạng thái chưa rõ; không được giả định retry là an toàn.

Webhook cũng có thể được gửi nhiều lần hoặc đến lệch thứ tự. Ngoài kiểm tra nguồn gửi, trình xử lý cần bỏ qua sự kiện đã áp dụng và chỉ chấp nhận chuyển trạng thái hợp lệ. Một webhook “thất bại” đến muộn không được tự động giải phóng ngân sách của lệnh đã xác nhận thành công.

## 9. Hạn mức phải gắn với tài sản đang bảo vệ

Không phải mọi lạm dụng đều được giải quyết bằng tiền hoặc trạng thái của một giao dịch. Với giữ chỗ và xuất báo cáo, cần xác định ngân sách tài nguyên.

| Tài sản | Kiểm soát phù hợp để cân nhắc | Vì sao giới hạn request đơn thuần chưa đủ? |
| --- | --- | --- |
| Tồn kho | Giới hạn số đơn vị đang giữ, thời gian giữ, tổng thời gian gia hạn; thu hồi giữ chỗ hết hạn nhất quán | Một request có thể giữ số lượng rất lớn |
| CPU và bộ nhớ xuất báo cáo | Giới hạn số tác vụ đang chạy, kích thước dữ liệu, chi phí truy vấn và ngân sách theo tenant | Một báo cáo có thể đắt hơn hàng nghìn truy vấn nhỏ |
| Ưu đãi | Hạn mức theo điều kiện đủ tư cách, chiến dịch và sổ cấp quyền lợi | Một tài khoản hoặc khóa request mới không nhất thiết là một khách hàng mới |
| Điểm thưởng | Trạng thái chờ quyết toán, liên kết giao dịch gốc, điều chỉnh khi đảo giao dịch | Phát điểm thành công không chứng minh quyền rút điểm đã có hiệu lực |

Giới hạn theo tài khoản vẫn hữu ích nhưng không đồng nghĩa với giới hạn theo con người. Các dấu hiệu tài khoản liên quan có thể hỗ trợ đánh giá rủi ro; địa chỉ IP chung không đủ để khẳng định cùng người. Chỉ thu thập dữ liệu cần thiết và có cách xử lý khi chặn nhầm.

Rate limiting bảo vệ tần suất ở một phạm vi cụ thể. Nó không chứng minh đúng giá, đúng quyền, đúng ngân sách hoặc đúng thứ tự. CAPTCHA có thể tăng chi phí tự động hóa nhưng cũng không thay thế các điều kiện nghiệp vụ phía máy chủ.

## 10. Kiểm thử theo kết quả bị cấm

Kiểm thử logic cần bắt đầu từ invariant rồi xây dựng chuỗi thao tác có thể phá nó. Một bài kiểm thử có giá trị phải kiểm tra trạng thái cuối, sổ ghi nhận và tác động tài chính, thay vì chỉ xem request thứ hai có bị trả lỗi hay không.

| Tình huống | Thao tác trong môi trường kiểm thử | Kết quả cần chứng minh |
| --- | --- | --- |
| Trả một phần sau giảm giá | Mua A và B theo ví dụ, trả B sau khi được duyệt | Tổng quyền hoàn của B là 640.000 đồng |
| Chia nhỏ lần trả | Trả các đơn vị của cùng dòng bằng nhiều hồ sơ | Tổng hoàn không vượt phân bổ, kể cả phần làm tròn |
| Retry cùng yêu cầu | Gửi lại cùng khóa và cùng nội dung | Cùng mã yêu cầu, không thêm khoản giữ hoặc lệnh hoàn |
| Tái sử dụng khóa sai nội dung | Dùng khóa cũ cho hồ sơ khác trong cùng phạm vi | Xung đột được xử lý, không tạo tác động mới |
| Đổi khóa | Gửi nhiều khóa cho cùng quyết định đã duyệt | Chỉ một lệnh tài chính cho quyết định đó |
| Cạnh tranh ngân sách | Đồng bộ hai request cùng bắt đầu khi chỉ đủ ngân sách cho một | Tổng đã hoàn và đang giữ luôn nằm trong ngân sách |
| Ghép sai đối tượng | Dùng hồ sơ, dòng hàng hoặc payment không thuộc cùng quan hệ | Không phát sinh ghi nhận hoặc tiết lộ dữ liệu trái quyền |
| Sai trạng thái hoặc quyền | Gửi yêu cầu trước duyệt; thử tự duyệt nếu bị cấm | Không tạo outbox, không giữ ngân sách |
| Worker xử lý lại | Phát lại cùng sự kiện outbox hoặc chạy lại sau khi worker dừng | Không tạo thêm tác động tại nhà cung cấp |
| Mất phản hồi từ bên ngoài | Nhà cung cấp thành công nhưng phản hồi bị mất | Khoản giữ còn được bảo toàn và kết quả được đối soát |
| Webhook trùng hoặc lệch thứ tự | Gửi lại sự kiện đã xử lý, sau đó gửi sự kiện cũ | Không cộng tiền hai lần, không quay lùi trạng thái cuối |
| Đảo giao dịch có thưởng | Hủy hoặc trả hàng của giao dịch đã phát thưởng | Quyền lợi được giữ, thu hồi hoặc điều chỉnh đúng chính sách |

Với kiểm thử đồng thời, dùng cơ chế đồng bộ để các request thực sự tranh chấp trên cùng ngân sách. Gửi hai request tuần tự không chứng minh được tính an toàn khi chạy song song. Kiểm thử cần chạy với cơ sở dữ liệu thật hoặc môi trường có ngữ nghĩa khóa tương ứng; mock repository không chứng minh hành vi transaction.

Có thể bổ sung kiểm thử sinh chuỗi thao tác như duyệt, hoàn, retry, nhận webhook và đối soát. Sau mỗi transaction đã commit, kiểm tra rằng ngân sách không âm, không có hai lệnh cho cùng quyết định và các quan hệ giữa đối tượng còn hợp lệ. Đây là cách tìm lỗi ở tổ hợp thao tác mà các ca đơn lẻ dễ bỏ sót.

## 11. Quan sát để phát hiện lạm dụng và sai lệch

Một hệ thống vẫn cần phát hiện dấu hiệu bất thường sau khi triển khai. Log phục vụ điều tra nên cho phép nối chuỗi giữa chủ thể, đối tượng và tác động:

- Tenant, actor, đơn hàng, hồ sơ trả, quyết định duyệt, `refundId` và mã giao dịch ngoài.
- Trạng thái trước và sau, số tiền, tiền tệ, phiên bản chính sách và lý do quyết định.
- Mã tương quan và tham chiếu idempotency phù hợp; tránh ghi toàn bộ token hoặc bí mật thanh toán.
- Quyết định từ chối do ngân sách, sai trạng thái, sai quyền hoặc trùng thao tác.

Các tín hiệu hữu ích gồm tỷ lệ hoàn sau nhận thưởng, nhiều khóa cho cùng quyết định, nhiều tài khoản cùng tiêu thụ một loại ưu đãi và lượng giữ chỗ hết hạn bất thường. Đây là tín hiệu để đánh giá, không tự nó là bằng chứng gian lận.

Đối soát cần so sánh sổ nội bộ với kết quả bên ngoài. Ví dụ, lệnh chờ quá lâu cần được truy vấn lại hoặc chuyển người xử lý. Cảnh báo không thay thế ràng buộc: phát hiện tiền hoàn vượt mức sau khi đã trả tiền không giữ được invariant ở thời điểm quyết định.

## 12. Những cách sửa thường để lại lỗ hổng

| Cách sửa | Phần còn thiếu | Hướng hoàn thiện |
| --- | --- | --- |
| Ẩn nút hoàn tiền hoặc bước duyệt trên giao diện | Người dùng vẫn gọi được API trực tiếp | Kiểm tra quyền và trạng thái tại máy chủ |
| Chỉ kiểm tra số tiền không vượt giá trị toàn đơn | Bỏ qua dòng hàng, phần đã hoàn và phần đang giữ | Bảo vệ ngân sách ở từng phạm vi liên quan |
| Đọc tổng tiền rồi ghi request trong transaction mặc định | Hai transaction có thể cùng đọc một số dư | Cập nhật có điều kiện hoặc cơ chế tranh chấp phù hợp |
| Dùng idempotency key cho mọi yêu cầu | Khóa mới vẫn có thể nhận lại cùng quyền lợi | Thêm tính duy nhất theo quyết định và invariant tổng |
| Dùng một khóa trong bộ nhớ tiến trình | Nhiều instance và việc khởi động lại vượt qua được | Dùng lưu trữ và ràng buộc có thẩm quyền dùng chung |
| Kiểm tra quyền sở hữu đơn nhưng tin mọi ID con | Có thể ghép đối tượng không cùng quan hệ | Kiểm tra tenant và quan hệ giữa toàn bộ đối tượng |
| Coi timeout là thất bại cuối cùng | Có thể giải phóng tiền trong khi bên ngoài đã hoàn | Giữ trạng thái chưa rõ và đối soát trước khi quyết định |
| Chỉ thêm rate limit | Từng lần gọi vẫn có thể tạo sai lợi ích | Sửa quy tắc giá trị, trạng thái, quyền và tính duy nhất |

## 13. Cách áp dụng khi nhận một tính năng mới

Trước khi triển khai, hãy viết ra câu trả lời cụ thể cho các câu sau:

1. Tính năng cấp quyền lợi hoặc tiêu thụ tài sản nào: tiền, hàng, điểm, dữ liệu hay tài nguyên tính toán?
2. Quyền lợi thuộc chủ thể và đối tượng nào? Hạn mức tính theo tài khoản, giao dịch, chiến dịch hay quan hệ khác?
3. Người dùng có thể thực hiện lặp, chia nhỏ, đảo thứ tự hoặc kết hợp tính năng này với hủy, trả, chuyển nhượng hay giới thiệu không?
4. Điều kiện nào phải đúng trước và sau thao tác? Dữ liệu nào được máy chủ quyết định?
5. Hai yêu cầu cùng hợp lệ khi đứng riêng có thể cùng vượt một giới hạn chung không?
6. Khi retry hoặc dịch vụ ngoài mất phản hồi, hệ thống nhận ra cùng một ý định nghiệp vụ bằng cách nào?
7. Kiểm thử nào chứng minh kết quả bị cấm không xuất hiện, kể cả khi các bước riêng lẻ đều hợp lệ?

Nếu chưa trả lời được, cần làm rõ mô hình nghiệp vụ cùng người sở hữu tính năng. Những câu như “frontend sẽ không cho bấm hai lần” hoặc “người dùng bình thường sẽ không làm vậy” không phải điều kiện bảo vệ.

## 14. Bài tập tự kiểm tra

### Bài 1: hạn mức theo request có đủ không?

Một API cho phép hoàn tối đa 300.000 đồng mỗi request. Đơn hàng đã thanh toán 500.000 đồng. Khách gửi hai yêu cầu khác khóa, mỗi yêu cầu 300.000 đồng.

**Gợi ý trả lời:** giới hạn theo request không bảo vệ tổng quyền lợi. Cần kiểm tra tổng đã hoàn, đang giữ và yêu cầu mới so với ngân sách thanh toán, đồng thời kiểm tra ngân sách dòng hàng. Điều kiện phải được thực thi nguyên tử khi hai request chạy song song. Khóa idempotency khác nhau không làm hai yêu cầu trở thành cùng một thao tác retry.

### Bài 2: đủ quyền sử dụng có đồng nghĩa được xuất vô hạn?

Nhân viên có quyền xem và xuất dữ liệu của tenant mình. Người đó tạo liên tiếp nhiều báo cáo lớn làm chậm hệ thống.

**Gợi ý trả lời:** quyền dữ liệu và ngân sách xử lý là hai điều kiện khác nhau. Cần đánh giá phạm vi dữ liệu, giới hạn số tác vụ đồng thời, chi phí và thời gian chạy, cùng khả năng hủy tác vụ. Không cần giả định việc người đó nhìn thấy dữ liệu là trái quyền mới có thể áp dụng ngân sách tài nguyên.

### Bài 3: mất phản hồi sau khi hoàn tiền

Worker gửi lệnh hoàn cho nhà cung cấp, sau đó timeout. Một worker khác sắp xử lý lại sự kiện.

**Gợi ý trả lời:** giữ nguyên mã yêu cầu và khóa cho lệnh tài chính, bảo toàn khoản giữ, kiểm tra trạng thái nội bộ và truy vấn hoặc retry theo hợp đồng của nhà cung cấp. Không tạo một lệnh nghiệp vụ mới chỉ vì phản hồi của lệnh cũ bị mất.

## 15. Các điểm cần ghi nhớ

Tính năng hợp lệ có thể trở thành công cụ lạm dụng khi các giới hạn chỉ tồn tại trong ý định của người thiết kế. Muốn bảo vệ được, cần biến ý định đó thành quyền theo đối tượng, invariant về giá trị và số lượng, cùng điều kiện chuyển trạng thái có thể thực thi.

Transaction bảo vệ nhóm thay đổi dữ liệu khi đi kèm cơ chế xử lý tranh chấp phù hợp. Idempotency xử lý việc gửi lại cùng ý định. Ràng buộc tính duy nhất và ngân sách nghiệp vụ ngăn việc nhận lại quyền lợi bằng ý định hoặc khóa khác. Đối soát xử lý khoảng trống giữa dữ liệu cục bộ và tác động bên ngoài.

Tiêu chí quan trọng nhất khi kiểm thử là: **sau một chuỗi thao tác được hệ thống chấp nhận, quyền lợi và tài sản có còn nằm trong các quy tắc đã xác định hay không?**
