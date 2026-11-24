# Price override approval: phê duyệt thay đổi giá có kiểm soát

## 1. Phê duyệt giá phải bảo vệ điều gì?

Nhân viên bán hàng cần chào một mức giá ngoại lệ để xử lý thương lượng hoặc sửa sai báo giá. Nếu hệ thống cho sửa trực tiếp `unit_price`, người có quyền thao tác đơn có thể giảm giá vượt thẩm quyền. Nếu chỉ thêm một cờ `approved = true`, họ có thể xin duyệt một mức giảm nhỏ rồi đổi số lượng, người mua hoặc mức giá trước khi áp dụng.

*Price override approval* là quy trình cho phép thay đổi giá thông thường bằng một quyết định có thẩm quyền, gắn với nội dung cụ thể và được kiểm tra lại tại thời điểm thực thi.

Trong bảo mật logic nghiệp vụ, mục tiêu không chỉ là lưu tên người duyệt. Cần giữ các invariant:

- Đúng người được đề xuất, đúng người được duyệt và đúng phạm vi dữ liệu.
- Quyết định áp dụng cho chính nội dung đã được xem xét.
- Tổng lợi ích tài chính nằm trong thẩm quyền thực sự của cấp duyệt.
- Những ràng buộc không được phép vượt vẫn có hiệu lực sau phê duyệt.
- Một quyết định không bị phát lại, áp hai lần hoặc áp sang đơn khác.
- Lịch sử đủ để giải thích ai yêu cầu, ai duyệt, giá nào thay đổi và hiệu lực nào đã xảy ra.

Bài học dùng ví dụ ghi đè đơn giá trên một đơn hàng chưa bắt đầu thanh toán. Các ngưỡng và vai trò là chính sách minh họa của sản phẩm, không phải quy tắc chung cho mọi doanh nghiệp.

## 2. Phân biệt quyền đề xuất, quyền duyệt và quyền thực thi

### 2.1. Ba hành động khác nhau

| Hành động | Trách nhiệm | Điều không được suy ra |
|---|---|---|
| Đề xuất giá | Chọn đơn, các dòng cần đổi, mức giá mong muốn và lý do | Có quyền đề xuất không có nghĩa được tự áp dụng |
| Phê duyệt | Đánh giá nội dung, phạm vi và mức rủi ro trong thẩm quyền | Có quyền duyệt một mức không có nghĩa được duyệt mọi mức |
| Áp dụng | Kiểm tra quyết định và cập nhật trạng thái tài chính theo giao thức | Tài khoản dịch vụ thực thi không trở thành người duyệt nghiệp vụ |

Giao diện ẩn nút sửa giá không phải một cơ chế cấp quyền. Backend phải kiểm tra từng hành động theo actor, tenant, đối tượng đơn hàng, vai trò và chính sách.

Không bind toàn bộ JSON vào entity rồi để client ghi `approved_by`, `approval_level`, `status`, `discount_limit` hoặc `effective_price`. Những trường này phải được xác định từ danh tính và quy trình phía server.

### 2.2. Tách người yêu cầu và người duyệt

Nếu chính sách yêu cầu kiểm soát hai người, người tạo yêu cầu không được duyệt yêu cầu đó. Người có hai vai trò cũng không được tính thành hai người duyệt độc lập khi chính sách yêu cầu hai cá nhân.

Nên so sánh định danh người có thẩm quyền đã được chuẩn hóa từ hệ thống danh tính, không chỉ tên hiển thị hoặc email trong request. Nếu một nhân sự có nhiều tài khoản, việc nhận diện cùng cá nhân cần dựa vào mô hình danh tính của tổ chức; so hai account ID khác nhau chưa đủ chứng minh độc lập.

Luồng đại diện hoặc ủy quyền phải ghi được cả người thực hiện và chủ thể được đại diện. Không cho phép dùng tài khoản dịch vụ làm trung gian để che việc người yêu cầu tự duyệt qua một đường khác.

### 2.3. Phạm vi quan trọng không kém tên vai trò

Một trưởng nhóm có thể chỉ được duyệt đơn của chi nhánh mình hoặc bảng giá mình quản lý. Vai trò `MANAGER` tồn tại không chứng minh quyền với mọi tenant, khách hàng và sản phẩm.

Quyết định cấp quyền cần xét đối tượng cụ thể. Biết một approval ID hoặc order ID, dù là UUID, không tạo ra quyền xem, duyệt hoặc áp dụng đối tượng đó.

## 3. Tính đúng mức rủi ro trước khi chọn cấp duyệt

### 3.1. Định nghĩa rõ điểm ghi đè giá

Trong ví dụ, nhân viên đề xuất **đơn giá trước khuyến mãi tự động**. Sau đó hệ thống vẫn tính các ưu đãi được phép cộng dồn để xác định khoản phải trả cuối cùng.

Một sản phẩm khác có thể cho ghi đè giá cuối sau mọi ưu đãi. Hai cách có ý nghĩa khác nhau và phải được phân biệt trong schema, giao diện phê duyệt và phép tính. Không dùng một trường `new_price` nhưng để các service hiểu khác nhau.

Backend phải xác định giá tham chiếu, số lượng, tiền tệ và các điều chỉnh từ dữ liệu có thẩm quyền. Tỷ lệ giảm hoặc mức chênh do client tính chỉ có thể là thông tin hiển thị, không quyết định cấp duyệt.

### 3.2. Ví dụ ưu đãi cộng dồn làm vượt ngưỡng

Giả sử có một dòng gồm 5 sản phẩm:

| Thành phần | Giá trị |
|---|---:|
| Đơn giá tham chiếu | 100.000 VND |
| Số lượng | 5 |
| Tổng tham chiếu | 500.000 VND |
| Đơn giá ngoại lệ đề xuất | 85.000 VND |
| Tổng sau ghi đè đơn giá | 425.000 VND |
| Khuyến mãi 10% được phép áp tiếp | 42.500 VND |
| Tiền hàng cuối sau các ưu đãi | 382.500 VND |
| Tổng lợi ích so với giá tham chiếu | 117.500 VND, tương đương 23,5% |

Nếu chỉ nhìn đơn giá từ 100.000 xuống 85.000, mức giảm là 15%. Nhưng chính sách trong ví dụ xét tổng nhượng bộ so với giá tham chiếu, nên cấp duyệt phải dựa trên 23,5% và 117.500 VND.

Nếu trước khi ghi đè khách vốn đã được giảm 10%, tiền hàng thông thường là 450.000 VND. Mức giảm thêm do ngoại lệ là 67.500 VND. Đây là một thước đo khác với tổng lợi ích 117.500 VND; hệ thống phải chọn đúng đại lượng theo chính sách, không dùng lẫn hai số.

Thuế, phí và vận chuyển được lược khỏi phép tính ví dụ. Trong sản phẩm thực tế, thành phần nào được tính là lợi ích, trợ giá hoặc chi phí phải được mô hình hóa rõ.

### 3.3. Ngưỡng duyệt minh họa

Giả sử chính sách chọn tổng lợi ích so với giá tham chiếu, dùng đồng thời ngưỡng phần trăm và số tiền:

| Cấp | Điều kiện | Phê duyệt cần có |
|---|---|---|
| Cấp 1 | Không quá 5% **và** không quá 50.000 VND | Một giám sát bán hàng đủ quyền, khác người yêu cầu |
| Cấp 2 | Không thuộc cấp 1; không quá 20% **và** không quá 500.000 VND | Một quản lý tài chính đủ quyền, khác người yêu cầu |
| Cấp 3 | Các trường hợp còn lại nhưng vẫn thỏa giới hạn cứng | Một quản lý tài chính và một người phụ trách thương mại, là hai cá nhân độc lập và đều khác người yêu cầu |

Ví dụ 23,5% thuộc cấp 3 dù số tiền tuyệt đối chưa đến 500.000 VND. Dùng sai toán tử `OR` thay cho `AND` ở điều kiện ngưỡng có thể khiến yêu cầu rủi ro cao đi qua cấp thấp.

Khi so phần trăm ở ngưỡng, không làm tròn một tỷ lệ 20,004% thành 20,00% rồi cho qua giới hạn 20% nếu chính sách xét giá trị chính xác. Có thể so bằng nhân chéo trên số nguyên có kiểm tra tràn hoặc `BigInteger`, thay vì dùng `double`.

### 3.4. Giới hạn cứng vẫn phải có hiệu lực

Giới hạn cứng có thể gồm giá hiệu dụng tối thiểu theo dòng, sản phẩm không cho ghi đè, tiền tệ bắt buộc, số tiền không âm hoặc mức giảm tối đa tuyệt đối của sản phẩm.

Nếu giá sàn được định nghĩa sau mọi ưu đãi, kiểm tra đơn giá trước khuyến mãi là chưa đủ. Cần xét kết quả cuối và phân bổ theo đúng phạm vi của giá sàn.

Phê duyệt cấp cao không tự mở quyền vượt mọi giới hạn. Nếu có quy trình ngoại lệ khác cho giới hạn cứng, đó phải là một loại quyền và hành động được định nghĩa riêng; không suy ra từ cờ `approved` của quy trình này.

## 4. Nội dung được duyệt phải bất biến và có phiên bản

### 4.1. Một quyết định cần ràng buộc những gì?

Một revision yêu cầu ghi đè nên chứa hoặc tham chiếu đến:

| Nhóm dữ liệu | Nội dung cần giữ |
|---|---|
| Phạm vi | Tenant, đơn, người mua và các dòng cụ thể |
| Giá gốc | Snapshot giá cơ sở, phiên bản giá của đơn, giá tham chiếu để xét rủi ro |
| Giá đề xuất | Đơn giá hoặc giá cuối được đề xuất, tiền tệ và đơn vị |
| Nội dung hàng | Sản phẩm, biến thể, số lượng và các thuộc tính ảnh hưởng giá |
| Tổng tác động | Khoản phải trả mới, lợi ích theo các thước đo chính sách, ưu đãi cộng dồn |
| Chính sách | Phiên bản tính giá, làm tròn, giới hạn và quy tắc phê duyệt |
| Lý do | Mã lý do, giải thích và tham chiếu bằng chứng phù hợp |
| Quy trình | Người yêu cầu, thời hạn, số revision và các điều kiện cần khi áp dụng |

Thay người mua có thể làm thay đổi bảng giá hoặc điều kiện ưu đãi. Thay số lượng có thể làm vượt ngưỡng số tiền. Thay biến thể có thể làm cho mức giá cũ không còn hợp lệ. Những thay đổi này không được mặc nhiên dùng lại quyết định cũ.

### 4.2. Payload đề xuất khác dữ liệu quyết định

Client có thể gửi lựa chọn giá mong muốn như sau; số tiền là chuỗi số nguyên theo đơn vị VND trong ví dụ:

```json
{
  "lines": [
    {
      "line_id": "L1",
      "requested_unit_price_minor": "85000"
    }
  ],
  "reason_code": "NEGOTIATED_PRICE",
  "comment": "Đề xuất giá theo nội dung thương lượng đã lưu.",
  "supporting_evidence_ref": "EVIDENCE-82"
}
```

Backend phải xác minh quyền với đơn và bằng chứng, lấy số lượng, giá tham chiếu, ưu đãi, tiền tệ từ nguồn đáng tin, rồi tạo revision có kết quả tính và cấp duyệt cần thiết.

Nội dung tự do trong `comment` không phải lệnh thay đổi chính sách. Một dòng “đã được giám đốc đồng ý” không thay thế bản ghi phê duyệt được xác thực.

### 4.3. Sửa nội dung tạo revision mới

Khi thay giá đề xuất hoặc một dữ kiện quan trọng, tạo revision mới và làm mất khả năng dùng các quyết định của revision cũ. Không cập nhật giá trong cùng revision đã có phê duyệt.

Có thể dùng digest của nội dung chuẩn hóa để hỗ trợ so khớp, nhưng digest phải được server tạo và kiểm tra. Cần quy tắc chuẩn hóa về thứ tự dòng, số tiền, tiền tệ và schema version. Client gửi một hash của payload đã sửa không chứng minh payload đúng.

Lưu revision hoặc tham chiếu bất biến là điều thiết yếu. Hash không thay thế dữ liệu đủ để giải thích người duyệt đã nhìn thấy gì.

### 4.4. Phân biệt giá cơ sở áp dụng với giá tham chiếu rủi ro

Phiên bản giá hiện tại của đơn dùng để phát hiện việc dữ liệu thay đổi trước lúc áp dụng. Giá tham chiếu rủi ro dùng để xét tổng nhượng bộ có thể là giá ban đầu hoặc một cơ sở khác do chính sách xác định.

Không tự đặt lại giá tham chiếu về giá đã bị giảm sau mỗi lần ghi đè. Nếu mỗi lần giảm thêm đều được so với một cơ sở mới, nhiều điều chỉnh nhỏ có thể che tổng giảm lớn so với cơ sở đáng lẽ phải xét.

Snapshot và lịch sử cần giữ được cả mối liên hệ phiên bản lẫn cơ sở rủi ro để lần đề xuất sau tính đúng tổng tác động.

## 5. State machine cho yêu cầu phê duyệt

Một state machine minh họa:

```text
DRAFT -> SUBMITTED -> APPROVED -> APPLIED
                   -> REJECTED
                   -> CANCELLED
                   -> EXPIRED

APPROVED -> REVOKED
APPROVED -> EXPIRED
APPROVED -> STALE
```

Ý nghĩa các trạng thái:

- `DRAFT`: chưa gửi xét duyệt; có thể thay nội dung theo quyền.
- `SUBMITTED`: revision đã được chốt để xét; có thể đã có một phần quyết định nhưng chưa đủ điều kiện.
- `APPROVED`: đủ các quyết định cần thiết cho revision, chưa tạo hiệu lực giá.
- `APPLIED`: đã tạo thay đổi giá nghiệp vụ và liên kết kết quả.
- `REJECTED`, `CANCELLED`, `REVOKED`, `EXPIRED`: không còn được áp dụng theo lý do tương ứng.
- `STALE`: nội dung hoặc điều kiện bắt buộc không còn khớp; cần một lần đánh giá hoặc revision mới.

Không cho client chuyển trạng thái bằng một endpoint cập nhật entity tổng quát. Mỗi hành động phải có điều kiện chuyển trạng thái riêng.

Nếu cần hai người duyệt, người thứ nhất đồng ý không được chuyển thẳng sang `APPROVED`. Backend phải kiểm tra đủ vai trò, đủ cá nhân độc lập và tất cả quyết định cùng revision.

Trạng thái có thể cần thêm nhánh ở sản phẩm thực tế. Điều cốt lõi là phân biệt “đủ quyết định phê duyệt” với “đã áp dụng thay đổi tài chính”.

## 6. Ghi quyết định với đúng thẩm quyền

### 6.1. Quyết định không lấy danh tính từ request

Một endpoint duyệt có thể nhận revision mong đợi và lựa chọn:

```json
{
  "revision": 2,
  "decision": "APPROVE"
}
```

Actor và vai trò phải đến từ quá trình xác thực và phân quyền. Request không được tự chọn `approver_id`, tự khai cấp duyệt hoặc giảm yêu cầu hai người xuống một người.

Trước khi ghi quyết định, backend cần kiểm tra:

1. Yêu cầu thuộc đúng tenant, đơn và phạm vi người duyệt được quản lý.
2. Revision vẫn là revision được phép xét, còn thời hạn và ở trạng thái phù hợp.
3. Người duyệt khác người yêu cầu theo chính sách tách vai trò.
4. Người duyệt có vai trò, hạn mức và quyền theo đối tượng cho tác động giá thực tế.
5. Không tính lặp một cá nhân thành nhiều quyết định độc lập.
6. Nội dung hiển thị để duyệt khớp nội dung đang ghi nhận quyết định.

Nếu giao diện đã hiển thị revision 2 nhưng server chuyển sang revision 3, phải từ chối hoặc yêu cầu tải lại. Không áp một nút “đồng ý” cũ cho nội dung mới.

### 6.2. Quyết định bất biến và chống đếm trùng

Có thể lưu một quyết định bất biến của mỗi cá nhân trên mỗi revision, kèm vai trò được xác minh, phạm vi, chính sách và thời gian. Một khóa duy nhất theo `(tenant_id, request_id, revision, approver_person_id)` giúp ngăn retry bị tính như người duyệt bổ sung.

Khóa duy nhất không tự chứng minh cấp quyền hoặc sự độc lập danh tính. Những điều kiện đó vẫn cần được kiểm tra trước khi ghi.

Nếu cần rút lại quyết định, dùng sự kiện hoặc hành động thu hồi có audit và cập nhật trạng thái theo chính sách; không sửa xóa âm thầm quyết định cũ. Một quy trình duyệt lại có thể tạo revision hoặc vòng xét mới được định danh rõ ràng.

### 6.3. Quyền có thể thay đổi trước lúc áp dụng

Cần xác định có bắt buộc người duyệt còn quyền tại lúc áp dụng hay chỉ cần hợp lệ tại lúc quyết định. Trong ví dụ, hệ thống yêu cầu quyền và các điều kiện bắt buộc còn hợp lệ khi áp dụng; nếu bị thu hồi, phải đánh giá lại thay vì sử dụng quyết định cũ.

Để xử lý thay đổi đồng thời, cần giao thức đồng bộ phù hợp: khóa dữ liệu quyền có liên quan, kiểm tra phiên bản quyền hoặc cơ chế phân quyền có điểm quyết định rõ ràng. Một transaction trên bảng đơn hàng không tự khóa mọi nguồn quyền ở dịch vụ danh tính bên ngoài.

Nếu chính sách phê duyệt đã siết chặt, không âm thầm áp quy tắc cũ chỉ vì revision có ghi một version. Ví dụ có thể yêu cầu version chính sách phê duyệt còn được server cho phép; khi không khớp, chuyển yêu cầu sang cần đánh giá lại. Cách tiếp tục chấp nhận version cũ, nếu có, phải là quyết định chính sách rõ ràng.

## 7. Áp dụng giá trong transaction có kiểm soát

### 7.1. Các điều kiện phải kiểm tra lại

Trước khi áp dụng một revision đã duyệt, backend cần xác minh:

- Đúng actor hoặc dịch vụ được phép thực hiện bước áp dụng.
- Yêu cầu ở `APPROVED`, đúng revision, còn hạn, chưa bị thu hồi hoặc áp dụng.
- Đơn và người mua vẫn khớp phạm vi, phiên bản giá và fingerprint được duyệt.
- Đơn còn ở trạng thái cho phép đổi giá.
- Kết quả tính cuối, giới hạn cứng và cấp duyệt vẫn thỏa chính sách.
- Không có thay đổi ưu đãi, số lượng hoặc bối cảnh làm biến đổi nội dung đã duyệt.
- Các giữ chỗ hoặc quyền lợi dùng chung có thể được cập nhật nhất quán.

Không chỉ kiểm tra cờ `APPROVED` rồi ghi bất kỳ giá nào đang nằm trong entity đơn.

### 7.2. Không sửa giá bên dưới một thanh toán đang chạy

Trong ví dụ, đơn chỉ được áp dụng ngoại lệ ở `DRAFT` hoặc `QUOTED`, trước khi có lệnh thanh toán đang hoạt động. Một khoản thanh toán timeout có thể vẫn thành công bên ngoài, nên không coi timeout là bằng chứng an toàn để đổi giá.

Nếu đã có authorization, capture, hóa đơn hoặc giao dịch tiền, cần luồng sửa đổi riêng: xác minh kết quả, hủy theo hợp đồng khi được phép, phụ thu hoặc hoàn tiền tương ứng. Không thay tổng đơn rồi đối chiếu callback cũ với số mới.

Kiểm tra trạng thái đơn và trạng thái xử lý thanh toán phải phối hợp với các đường khởi tạo thanh toán. Nếu hai luồng không cùng giao thức khóa hoặc phiên bản, vẫn có thể vừa đổi giá vừa phát lệnh thu giá cũ.

### 7.3. Luồng điều khiển minh họa

```text
BEGIN
  Nhận diện idempotency và kiểm tra quyền đối với kết quả nếu đã có.
  Khóa đơn và yêu cầu theo thứ tự thống nhất toàn hệ thống.
  Nạp đúng revision bất biến và các quyết định liên quan.
  Kiểm tra trạng thái, thời hạn, phiên bản, thẩm quyền và nội dung.
  Tính hoặc xác minh lại kết quả bằng các nguồn và chính sách đã định.
  Kiểm tra giới hạn cứng, tổng tác động và đủ cấp duyệt.
  Tạo snapshot giá mới có liên kết tới revision được duyệt.
  Cập nhật đơn sang snapshot mới và tăng phiên bản giá.
  Vô hiệu hóa các quote cũ theo chính sách.
  Ghi hiệu lực áp dụng duy nhất và chuyển yêu cầu sang APPLIED.
  Ghi audit và outbox nếu có thông điệp cần phát sau commit.
COMMIT
```

Đây là mô hình điều khiển, không phải mã có thể chạy nguyên văn. Nếu dữ liệu nguồn nằm ngoài transaction, cần cơ chế version, cam kết dữ liệu hoặc phát hiện thay đổi phù hợp; không gọi nhiều dịch vụ chậm trong khi giữ khóa dài rồi mặc định đã đạt tính nguyên tử phân tán.

### 7.4. Cập nhật có điều kiện

Ví dụ PostgreSQL dưới đây minh họa một phần bảo vệ cạnh tranh. Giả định các bước kiểm tra và tạo snapshot đã được thực hiện trong cùng transaction, mọi giá trị tiền đến từ server, các khóa và constraint liên quan đã được thiết kế.

```sql
UPDATE orders
SET price_snapshot_id = :new_price_snapshot_id,
    total_minor = :server_computed_total_minor,
    price_version = price_version + 1
WHERE tenant_id = :verified_tenant_id
  AND id = :verified_order_id
  AND price_version = :approved_base_price_version
  AND status IN ('DRAFT', 'QUOTED');

-- Backend yêu cầu đúng một hàng được cập nhật.
-- Không có hàng: rollback toàn bộ lần áp dụng.

UPDATE price_override_requests
SET status = 'APPLIED',
    applied_snapshot_id = :new_price_snapshot_id,
    applied_at = statement_timestamp()
WHERE tenant_id = :verified_tenant_id
  AND id = :verified_request_id
  AND order_id = :verified_order_id
  AND revision = :approved_revision
  AND status = 'APPROVED'
  AND expires_at > statement_timestamp();

-- Backend cũng yêu cầu đúng một hàng; nếu không, rollback cả thay đổi đơn.
```

Hai câu `UPDATE` phải thuộc cùng transaction với hiệu lực áp dụng và dữ liệu bắt buộc. Chạy chúng ở hai transaction riêng sẽ có nguy cơ đơn đã đổi giá nhưng yêu cầu chưa được đánh dấu hoặc ngược lại.

SQL này không tự kiểm tra đủ người duyệt, quyền, thanh toán đang chạy hay sự khớp toàn bộ nội dung. Những điều kiện đó phải có trong giao thức đầy đủ. Điều kiện thời gian ở ví dụ xét theo thời điểm bắt đầu câu lệnh; sản phẩm cần định nghĩa rõ thời điểm chấp nhận, đặc biệt khi có chờ khóa.

### 7.5. Idempotency và một hiệu lực áp dụng

Nên có khóa duy nhất cho hiệu lực áp dụng theo phạm vi như `(tenant_id, request_id, revision)`. Request retry sau khi commit nhưng mất phản hồi phải trả về hiệu lực đã tạo, sau khi xác minh quyền, thay vì tạo một snapshot áp dụng mới lần nữa.

Đổi idempotency key không được áp lại cùng revision. Idempotency nhận diện cùng hành động gửi lại; khóa hiệu lực và state machine bảo vệ revision trước nhiều hành động khác nhau.

Nếu bước ghi audit bắt buộc hoặc cập nhật liên quan thất bại, rollback phải giữ đơn ở giá trước và không để yêu cầu thành `APPLIED` dở dang. Nếu cần ghi nhận lần thử bị từ chối, dùng sự kiện đúng loại qua cơ chế phù hợp, không ghi thành công cho transaction đã rollback.

## 8. Ngăn chia nhỏ thay đổi để né ngưỡng

### 8.1. Chia dòng hoặc chia revision

Kẻ tấn công có thể giảm mỗi dòng một khoản nhỏ để từng dòng nằm dưới ngưỡng, trong khi tổng đơn vượt thẩm quyền. Nếu chính sách xét tổng đơn, cấp duyệt phải dựa trên tổng tác động các dòng liên quan.

Họ cũng có thể xin giảm 25.000 VND nhiều lần trên cùng đơn. Nếu hệ thống chỉ xét chênh lệch so với giá ngay trước lần sửa, mỗi lần có vẻ nhỏ dù tổng giảm so với giá tham chiếu đã lớn.

Cần lưu cơ sở rủi ro theo chính sách và tính cả các điều chỉnh đã có. Version mới giúp phát hiện dữ liệu thay đổi; nó không tự ngăn việc đặt lại cơ sở để lách ngưỡng.

### 8.2. Chia đơn hoặc đổi người thao tác

Nếu giới hạn là theo khách hàng trong kỳ, chia thành nhiều đơn hoặc nhờ nhiều nhân viên tạo yêu cầu không được tự mở thêm hạn mức. Cần cơ chế tổng hợp và giữ ngân sách theo đúng phạm vi.

Không phải sản phẩm nào cũng có trần liên đơn. Điều cần thiết là định nghĩa rõ ngưỡng thuộc dòng, đơn, khách hàng, hợp đồng hay kỳ; kiểm soát đúng phạm vi đó thay vì dùng một hàm kiểm tra chung cho mọi trường hợp.

### 8.3. Cộng ưu đãi sau khi đã duyệt

Một revision được duyệt khi tổng lợi ích là 15% có thể trở thành 23,5% nếu thêm khuyến mãi sau đó. Luồng thay đổi ưu đãi phải kiểm tra lại binding và thẩm quyền, không coi phê duyệt giá là quyền cộng thêm mọi ưu đãi.

Nếu chương trình cho phép cộng dồn trong một khoảng đã duyệt, khoảng và điều kiện đó phải được mô hình hóa rõ. Bài này dùng phê duyệt cho nội dung cụ thể; một quyền đặt giá linh hoạt theo hợp đồng là mô hình khác và cần giới hạn riêng.

## 9. Snapshot giá, thanh toán và điều chỉnh sau áp dụng

### 9.1. Giữ cả trước và sau

Snapshot trước áp dụng cần được giữ để giải thích cơ sở và tác động. Snapshot sau áp dụng cần chỉ rõ nguồn thay đổi là request và revision nào, cùng các quyết định đã cho phép.

Không sửa giá trong snapshot cũ. Nếu có báo giá cũ, cần vô hiệu hóa hoặc xử lý theo chính sách để không tạo hai đường thanh toán với nội dung khác nhau cho cùng đơn.

### 9.2. Thanh toán dùng giá đã chốt

Lệnh thanh toán lấy số tiền và tiền tệ từ nội dung đơn đã được chấp nhận, không từ trường `requested_price` trong một request bất kỳ. Khi nhận callback, đối chiếu với đúng lệnh và phiên bản nội dung tài chính liên quan.

Nếu đề xuất hoặc quyết định hết hạn sau khi đã áp dụng thành công, không tự sửa lại giá đơn. Thời hạn cho phép áp dụng và vòng đời của đơn sau áp dụng là hai vấn đề khác nhau.

### 9.3. Hoàn và thu hồi ngoại lệ

Hoàn tiền dựa trên khoản thực thu, phân bổ và chính sách của đơn đã chốt. Không hoàn theo giá tham chiếu cao hơn chỉ vì đó là giá catalog trước ngoại lệ.

Thu hồi một phê duyệt chưa áp dụng có thể ngăn việc áp dụng. Với giá đã có hiệu lực, không chỉ đổi status thành `REVOKED` rồi coi số tiền đã thu tự thay đổi. Cần một nghiệp vụ điều chỉnh riêng, có quyền, bằng chứng và hiệu lực tiền tương ứng.

Snapshot và audit phải giữ được lịch sử quyết định, thay đổi giá, thanh toán và điều chỉnh, thay vì sửa dữ liệu cũ để làm chúng trông như chưa từng xảy ra.

## 10. Dữ liệu, constraint và audit

### 10.1. Mô hình liên kết tối thiểu

| Thành phần | Trách nhiệm |
|---|---|
| Request | Định danh quy trình, tenant, đơn, người yêu cầu, trạng thái và thời hạn |
| Revision | Nội dung đề xuất bất biến, cơ sở và kết quả tính, các phiên bản |
| Decision | Người duyệt, vai trò/phạm vi được xác minh, revision, kết quả và thời gian |
| Application | Hiệu lực áp dụng duy nhất, snapshot trước/sau, phiên bản đơn và mã idempotency liên quan |
| Audit events | Lịch sử gửi, duyệt, từ chối, thu hồi, hết hạn, áp dụng và các lần thử đáng chú ý |

Các khóa ngoại ghép hoặc quan hệ tương đương cần giữ đúng tenant, đơn và revision. Chỉ có khóa ngoại riêng cho request ID và snapshot ID chưa chứng minh snapshot thuộc đúng yêu cầu đang áp dụng.

Các constraint cục bộ có thể bảo vệ số tiền không âm, miền trạng thái và khóa duy nhất. Điều kiện đủ hai người có vai trò hợp lệ là quy tắc liên quan nhiều dữ liệu; không tự được bảo vệ bằng một `CHECK` trên dòng request.

### 10.2. Audit phải giải thích quyết định

Audit nên cho biết:

- Ai đề xuất, ai duyệt, ai thực thi; có đại diện hoặc ủy quyền nào.
- Giá tham chiếu, giá trước, giá đề xuất và kết quả cuối.
- Số lượng, tiền tệ, ưu đãi và tác động dùng để xét ngưỡng.
- Chính sách, cấp duyệt, revision và nội dung được chấp nhận.
- Lý do, bằng chứng và thời gian theo nguồn tin cậy.
- Snapshot, đơn, hiệu lực áp dụng và giao dịch tiền liên quan.

Không chỉ ghi `override approved` hoặc tên người quản lý. Những dòng đó không đủ chứng minh quyền với đơn cụ thể và mức giá cụ thể.

Giới hạn quyền sửa hoặc xóa dữ liệu phê duyệt, giữ bản ghi điều chỉnh và theo dõi thao tác quản trị. Hash nội dung không ngăn người có quyền sửa cả dữ liệu và hash; cần mô hình quyền và lưu giữ phù hợp.

Không ghi token xác thực, bí mật thanh toán hoặc dữ liệu cá nhân không cần thiết vào audit. Bằng chứng thương lượng và giá nội bộ cũng cần quyền truy cập riêng.

### 10.3. Đối soát tìm đường bỏ qua quy trình

Các kiểm tra định kỳ có thể phát hiện:

- Đơn có giá ngoại lệ nhưng không có application hợp lệ.
- Application không có đủ decision cho đúng revision.
- Người yêu cầu đồng thời được tính là người duyệt trái chính sách.
- Hai vai trò bắt buộc do cùng một cá nhân đáp ứng khi cần hai người độc lập.
- Mức tác động thực tế vượt ngưỡng của quyết định đã lưu.
- Snapshot sau áp dụng không khớp nội dung revision.
- Một revision tạo nhiều hiệu lực hoặc nhiều đơn không được phép.

Đối soát hỗ trợ phát hiện dữ liệu lịch sử và đường ghi bỏ sót. Nó không thay thế kiểm soát tại thời điểm duyệt và áp dụng.

## 11. Xử lý lỗi và quy trình ngoại lệ

Không đủ quyền, revision đã thay đổi, yêu cầu hết hạn và đơn đã vào thanh toán là các nguyên nhân khác nhau ở nội bộ. Phản hồi cho người dùng cần rõ hành động tiếp theo nhưng không tiết lộ đơn hoặc bằng chứng ngoài quyền.

Ví dụ lỗi khi nội dung không còn khớp:

```json
{
  "code": "PRICE_OVERRIDE_STALE",
  "message": "Nội dung giá đã thay đổi. Cần gửi lại yêu cầu phê duyệt."
}
```

Không tự hạ cấp yêu cầu từ hai người duyệt xuống một người vì người thứ hai chưa sẵn sàng. Có thể chuyển tuyến cho người khác cùng thẩm quyền hoặc dùng luồng ủy quyền được phép, đồng thời giữ sự độc lập và bằng chứng.

Tài khoản quản trị cũng phải theo chính sách của hành động. Nếu sản phẩm có cơ chế khẩn cấp, cần quyền riêng, phạm vi, lý do, thời hạn và kiểm soát bù được định nghĩa; không tạo một điều kiện `isAdmin` bỏ qua toàn bộ quy trình này.

Khi nguồn quyền hoặc dữ liệu bắt buộc không xác minh được, không mặc định cho áp dụng vì request từng được duyệt. Cần trạng thái chờ hoặc phản hồi lỗi để xử lý lại theo thiết kế.

## 12. Kiểm thử theo tình huống tấn công logic

### 12.1. Ma trận quyền và nội dung

| Tình huống | Điều cần chứng minh |
|---|---|
| Người yêu cầu tự duyệt | Bị chặn theo định danh có thẩm quyền |
| Cùng cá nhân dùng hai tài khoản hoặc hai vai trò | Không được tính thành hai người độc lập theo mô hình danh tính |
| Người duyệt đúng vai trò nhưng sai chi nhánh/tenant | Bị kiểm tra phạm vi đối tượng |
| Client tự gửi `approved_by` hoặc `APPROVED` | Không điều khiển danh tính và state machine |
| Thay giá hoặc số lượng sau quyết định | Không dùng lại phê duyệt của nội dung cũ |
| Dùng quyết định sang đơn hoặc người mua khác | Bị binding phạm vi chặn |
| Một phần hai người đã duyệt | Chưa đủ chuyển sang có thể áp dụng |
| Giá trước ưu đãi giảm 15%, tổng lợi ích 23,5% | Chọn cấp theo chính sách tổng tác động, không chỉ tỷ lệ thủ công |
| Giá cuối dưới sàn sau cộng ưu đãi | Giới hạn cứng tiếp tục chặn |
| Tỷ lệ sát ngưỡng, như hơn 20% một lượng nhỏ | Không bị làm tròn xuống để vượt thẩm quyền |
| Quyền người duyệt bị thu hồi trước áp dụng | Xử lý đúng chính sách hiệu lực quyền đã chọn |
| Chính sách yêu cầu cấp cao hơn sau khi duyệt | Không âm thầm áp version không còn được phép |

### 12.2. Kiểm thử né ngưỡng và state machine

- Chia một thay đổi lớn thành nhiều dòng hoặc nhiều lần sửa trên cùng đơn.
- Thử đặt lại giá tham chiếu về giá đã giảm để mỗi lần trông như một ngoại lệ nhỏ.
- Chia sang nhiều đơn hoặc nhiều người yêu cầu khi chính sách có hạn mức dùng chung.
- Thêm coupon, đổi biến thể hoặc thay bối cảnh sau bước duyệt.
- Gọi trực tiếp API áp dụng từ trạng thái chưa đủ phê duyệt.
- Dùng yêu cầu đã hết hạn, bị thu hồi hoặc đã áp dụng.
- Thử cập nhật giá bằng endpoint quản trị, import hoặc job nền để bỏ qua application.

Kỳ vọng không chỉ là mã lỗi. Không được có snapshot mới có hiệu lực, tổng đơn thay đổi hoặc thông điệp thanh toán sai phát ra sau một lần bị từ chối.

### 12.3. Kiểm thử đồng thời và crash

| Lịch thực thi | Kết quả cần giữ |
|---|---|
| Hai request áp dụng cùng revision | Tối đa một hiệu lực commit |
| Retry sau commit nhưng mất phản hồi | Trả lại hiệu lực cũ theo idempotency và quyền |
| Duyệt revision cũ đồng thời với tạo revision mới | Không gắn quyết định cũ vào nội dung mới |
| Thu hồi quyết định đồng thời với áp dụng | Tuân theo giao thức khóa, phiên bản và thời điểm quyền đã định |
| Đổi giỏ đồng thời với áp dụng | Không ghép phê duyệt cũ với nội dung mới |
| Khởi tạo thanh toán đồng thời với đổi giá | Không phát lệnh giá cũ trên đơn đã đổi mà không có xử lý nhất quán |
| Hết hạn gần lúc áp dụng hoặc trong lúc chờ khóa | Đúng định nghĩa thời điểm chấp nhận của chính sách |
| Lỗi sau cập nhật đơn nhưng trước ghi application/audit | Rollback không để giá thay đổi dở |

Dùng hai kết nối và điểm đồng bộ có chủ đích để tạo cuộc đua. Kiểm tra trạng thái sau commit, hiệu lực áp dụng, snapshot, quote cũ, audit và outbox, không chỉ phản hồi HTTP.

### 12.4. Các thuộc tính cần luôn đúng

```text
APPLIED -> có application duy nhất cho request và revision.

Application -> đúng đơn, tenant, revision và snapshot được duyệt.

Snapshot sau áp dụng -> khớp nội dung và kết quả tính được phép.

Cấp duyệt -> đáp ứng tổng tác động theo chính sách.

Giới hạn cứng -> vẫn đúng sau mọi ưu đãi và phân bổ liên quan.

Hành động bị từ chối -> không có hiệu lực giá hoặc tiền.
```

Nếu sản phẩm có mô hình quyền khác, thuộc tính cần điều chỉnh tương ứng. Không đặt giả định một người luôn được phép duyệt chỉ vì họ từng có vai trò ở một thời điểm khác.

## 13. Những quyết định cần chốt khi triển khai

- Ghi đè đơn giá trước ưu đãi hay giá cuối, và thước đo rủi ro là gì?
- Ngưỡng xét theo dòng, đơn, khách hàng hay phạm vi tổng hợp nào?
- Giá tham chiếu có bị đặt lại sau mỗi lần giảm hay được giữ theo chính sách?
- Ai được đề xuất, ai được duyệt và bao nhiêu cá nhân độc lập là đủ?
- Quyết định gắn với nội dung và revision bất biến nào?
- Quyền, thời hạn và phiên bản chính sách được kiểm tra tại lúc duyệt và lúc áp dụng thế nào?
- Luồng đổi giá có phối hợp với thanh toán, quote và các quyền lợi dùng chung không?
- Retry, rollback và điều chỉnh sau áp dụng có giữ một lịch sử tài chính giải thích được không?

Một phê duyệt giá có giá trị khi nó cho phép đúng hành động, trên đúng nội dung, trong đúng thẩm quyền và chỉ tạo hiệu lực theo quy trình đã định. Khi các điều kiện đó được kiểm chứng tại backend và lúc ghi dữ liệu, cờ phê duyệt không còn là đường tắt để bỏ qua quy tắc giá.
