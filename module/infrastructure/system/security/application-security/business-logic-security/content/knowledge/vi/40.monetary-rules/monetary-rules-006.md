# Money movement audit: truy vết và kiểm chứng mọi dịch chuyển tiền

## 1. Audit tiền phải trả lời được điều gì?

Một màn hình hiển thị “hoàn tiền thành công” chưa chứng minh tiền đã được hoàn đúng. Backend có thể đã ghi trạng thái trước khi gọi cổng thanh toán, xử lý webhook hai lần, bỏ sót phí hoặc chấp nhận số tiền do client sửa. Nếu chỉ có dòng log `refund success`, đội vận hành khó xác định điều gì thực sự xảy ra.

*Money movement audit* là khả năng tái dựng và kiểm chứng một dịch chuyển tiền từ yêu cầu ban đầu đến kết quả có bằng chứng: ai khởi tạo, ai được phép duyệt, tiền lấy từ đâu, đến đâu, tính theo quy tắc nào, đã ghi nhận bao nhiêu lần và đối chiếu với hệ thống bên ngoài ra sao.

Trong bảo mật logic nghiệp vụ, audit phục vụ cả phát hiện lạm dụng lẫn chứng minh invariant được giữ. Nó giúp nhận ra các trường hợp như sửa giá, đổi người nhận sau phê duyệt, tự duyệt khoản chi, hoàn tiền vượt số đã thu hoặc gửi lại một yêu cầu để nhận tiền nhiều lần.

Một thiết kế tốt cần trả lời được các câu hỏi sau mà không phải suy đoán từ log rời rạc:

- Ai yêu cầu, ai phê duyệt và thành phần nào thực thi?
- Những đối tượng nào thuộc phạm vi tenant và quyền của người gọi?
- Số tiền, tiền tệ, phí và người nhận được xác định từ nguồn nào?
- Đã có hiệu lực tài chính hay mới chỉ được tiếp nhận xử lý?
- Mỗi bút toán liên quan đến yêu cầu, lần phê duyệt và tham chiếu bên ngoài nào?
- Retry, webhook trùng và hoàn tiền được nhận diện thế nào?
- Nếu có sai lệch, bằng chứng nào giúp phát hiện và điều chỉnh mà vẫn giữ lịch sử?

Audit không thay thế kiểm soát quyền, kiểm tra số dư, state machine hoặc idempotency. Một giao dịch trái phép được ghi log đầy đủ vẫn là giao dịch trái phép.

## 2. Phân biệt sổ cái, audit trail và log vận hành

Ba loại dữ liệu thường bị gom chung nhưng có mục đích khác nhau:

| Loại dữ liệu | Câu hỏi chính | Nội dung điển hình |
|---|---|---|
| Sổ cái tài chính, hay ledger | Tiền hoặc nghĩa vụ tài chính đã tăng giảm thế nào? | Nhóm bút toán, tài khoản, số tiền, tiền tệ, tham chiếu nghiệp vụ |
| Audit trail nghiệp vụ | Ai làm gì, theo quyền nào, thay đổi nào được chấp nhận hoặc từ chối? | Người khởi tạo, người duyệt, chính sách, trạng thái trước/sau, lý do |
| Log vận hành | Vì sao hệ thống chậm hoặc lỗi? | Timeout, retry, lỗi kết nối, mã tương quan, thời gian xử lý |

Ledger là cơ sở cho các số dư đã ghi sổ theo mô hình tài chính đã chọn. Audit trail giải thích hành động và thẩm quyền dẫn đến việc ghi sổ. Log vận hành hỗ trợ chẩn đoán. Một trường `balance` hiện tại hoặc một chuỗi log HTTP không đủ thay thế hai loại dữ liệu đầu.

Không phải mọi audit event đều có bút toán. Yêu cầu bị từ chối do sai quyền phải được nhận diện là bị từ chối, không phải một khoản chuyển tiền. Ngược lại, mỗi hiệu lực tài chính cần có liên kết tới hồ sơ nghiệp vụ và audit tương ứng.

Trong hệ thống phân tán, nội bộ đã ghi sổ cũng chưa tự chứng minh ngân hàng đã quyết toán. Phải định nghĩa rõ tầng nào xác nhận sự kiện nào và đối chiếu với bằng chứng bên ngoài.

## 3. Xác định invariant cho dịch chuyển tiền

Giả sử dịch vụ hỗ trợ chuyển tiền giữa các ví trong cùng tenant, thu phí và hoàn tiền. Những invariant quan trọng gồm:

| Invariant | Điều cần bảo vệ |
|---|---|
| Phạm vi và quyền | Người gọi có quyền với nguồn tiền và hành động; các đối tượng liên quan thuộc phạm vi hợp lệ |
| Dữ liệu tiền chính xác | Số tiền dương, có giới hạn, đúng đơn vị và tiền tệ; không dùng sai số dấu phẩy động |
| Nội dung được duyệt không bị đổi | Người nhận, số tiền và phí khi thực thi khớp phiên bản đã được phép thực hiện |
| Không chi vượt khả dụng | Kiểm tra và giữ chỗ hoặc ghi nợ không bị cuộc đua làm vượt số dư |
| Không ghi hiệu lực trùng | Một dịch chuyển nghiệp vụ chỉ có nhóm bút toán tương ứng theo quy tắc đã định |
| Ghi sổ cân bằng | Tổng bên Nợ bằng tổng bên Có trong từng nhóm bút toán, cho từng tiền tệ theo mô hình sổ cái |
| Không mất bằng chứng khi ghi tiền | Bút toán, thay đổi nghiệp vụ và audit bắt buộc được ghi nhất quán |
| Hoàn tiền có giới hạn | Khoản đã hoàn và khoản còn có thể hoàn không vượt chính sách của giao dịch gốc |
| Điều chỉnh có lịch sử | Sửa sai bằng bút toán điều chỉnh hoặc đảo, giữ được liên kết đến bản gốc |

Các invariant này cần cơ chế thực thi khác nhau. `UNIQUE` có thể ngăn ghi trùng một loại bút toán; nó không chứng minh người gọi có quyền. Sổ cái cân bằng cũng không chứng minh người nhận là đúng: một khoản chuyển nhầm vẫn có thể cân bằng hoàn hảo.

### 3.1. Xác định số tiền từ nguồn có thẩm quyền

Client có thể gửi lựa chọn sản phẩm, số lượng hoặc khoản muốn hoàn, nhưng không được tự quyết định giá cuối cùng, phí, quyền chi hay tổng có thể hoàn. Backend phải tính hoặc xác minh các giá trị đó từ dữ liệu nghiệp vụ đáng tin cậy.

Với ví dụ chuyển có phí:

```text
Số tiền người nhận được:       250.000 VND
Phí do người gửi chịu:           2.000 VND
Tổng giảm nghĩa vụ ví người gửi: 252.000 VND
```

Audit cần lưu kết quả tính đã áp dụng và tham chiếu phiên bản quy tắc phí. Chỉ lưu `policy_id` trỏ đến một hàng có thể bị sửa sẽ không đủ tái dựng phép tính cũ.

### 3.2. Đơn vị tiền và làm tròn

Ví dụ trong bài dùng VND với đơn vị nguyên theo chính sách của hệ thống. Nếu dùng số nguyên đơn vị nhỏ nhất, cần lưu cả tiền tệ và định nghĩa đơn vị; không mặc định mọi tiền tệ đều có hai chữ số thập phân.

Trong Java, có thể dùng số nguyên có kiểm tra tràn cho đơn vị nhỏ nhất hoặc `BigDecimal` với scale và cách làm tròn được quy định. Không dùng `double` để tính tiền. Với đầu vào thập phân, tạo giá trị từ chuỗi chính xác; `new BigDecimal(double)` có thể mang theo sai số nhị phân đã có.

Nếu tiền đi qua JSON, cần chọn hợp đồng biểu diễn không làm mất chính xác ở các thành phần trung gian. Chuỗi số nguyên có schema rõ ràng là một lựa chọn, đặc biệt khi giá trị có thể vượt miền số nguyên an toàn của bên nhận.

Audit phép tính nên có giá trị đầu vào nghiệp vụ, kết quả cuối, tiền tệ, cách làm tròn và phiên bản chính sách đủ để tái hiện. Không âm thầm làm tròn lại số tiền đã được phê duyệt bằng cấu hình mới.

## 4. Thiết kế hồ sơ dịch chuyển tiền

### 4.1. Các định danh phải có ý nghĩa khác nhau

Một request có thể sinh nhiều lần thử mạng nhưng chỉ tạo một hiệu lực tài chính. Vì vậy, cần tách các định danh:

| Định danh | Ý nghĩa |
|---|---|
| `movement_id` | Một dịch chuyển tiền nghiệp vụ |
| `journal_id` | Một nhóm bút toán ghi sổ |
| `audit_event_id` | Một sự kiện audit cụ thể |
| `request_id` hoặc `trace_id` | Một lần xử lý request hoặc một chuỗi xử lý để chẩn đoán |
| `idempotency_key` | Nhận diện việc gửi lại cùng một yêu cầu theo hợp đồng API |
| `provider_transaction_id` | Giao dịch trong phạm vi nhà cung cấp và tài khoản tích hợp tương ứng |
| `original_movement_id` | Dịch chuyển gốc của một khoản hoàn hoặc điều chỉnh |

Không dùng `request_id` mới cho mỗi lần retry làm khóa chống trùng tài chính. Không coi ID sự kiện webhook là ID duy nhất của hiệu lực tiền: nhà cung cấp có thể phát nhiều sự kiện cho cùng giao dịch.

Các khóa duy nhất phải có phạm vi rõ ràng. Ví dụ, ID giao dịch của nhà cung cấp có thể cần đi kèm `provider` và `provider_account_id`, thay vì được giả định là duy nhất trên mọi tích hợp.

### 4.2. Những nhóm dữ liệu cần lưu

Một hồ sơ có thể được tách thành các bảng hoặc collection liên kết:

| Thành phần | Dữ liệu trọng tâm |
|---|---|
| Movement | Tenant, loại hành động, nguồn/đích, số tiền, tiền tệ, tham chiếu gốc, trạng thái và phiên bản |
| Authorization/approval | Người yêu cầu, người duyệt, kết quả kiểm tra quyền, phiên bản chính sách và nội dung được duyệt |
| Journal và journal lines | Tài khoản, bên Nợ/Có, số tiền, tiền tệ, liên kết movement |
| Audit events | Hành động, kết quả, actor, trạng thái trước/sau, thời gian, tham chiếu bằng chứng |
| Outbox/inbox | Sự kiện cần phát hoặc thông điệp bên ngoài đã tiếp nhận và xử lý |

Không nhất thiết nhét tất cả vào một JSON lớn. Các trường cần constraint, join và đối chiếu nên có cấu trúc ổn định. Metadata mở rộng cần schema version, giới hạn dung lượng và quy tắc dữ liệu nhạy cảm.

### 4.3. Một audit event minh họa

Ví dụ dưới đây là sự kiện ghi sổ cho chuyển ví nội bộ không thu phí. Các ID là định danh minh họa; số tiền được biểu diễn bằng chuỗi số nguyên theo hợp đồng dữ liệu.

```json
{
  "audit_event_id": "AE-0081",
  "schema_version": 1,
  "tenant_id": "TENANT-A",
  "movement_id": "MV-1007",
  "aggregate_version": 4,
  "event_type": "INTERNAL_TRANSFER_POSTED",
  "actor": {
    "type": "SERVICE",
    "id": "money-service"
  },
  "initiator_ref": "USER-17",
  "approval_ref": "APPROVAL-93",
  "source_account_ref": "WALLET-11",
  "destination_account_ref": "WALLET-22",
  "money": {
    "amount_minor": "250000",
    "currency": "VND",
    "minor_unit_scale": 0
  },
  "state_before": "EXECUTING",
  "state_after": "SUCCEEDED",
  "outcome": "SUCCESS",
  "journal_id": "JR-5401",
  "policy_version": "wallet-transfer-v3",
  "request_id": "REQ-734",
  "occurred_at": "2026-11-22T03:14:15.123Z",
  "recorded_at": "2026-11-22T03:14:15.130Z"
}
```

`actor` thực thi là dịch vụ, còn `initiator_ref` chỉ người yêu cầu ban đầu. Nếu có bước duyệt, `approval_ref` phải dẫn đến bằng chứng duyệt hợp lệ, không phải một chuỗi do client tự khai báo.

Event này chứng minh hiệu lực ghi sổ nội bộ theo định nghĩa của hệ thống. Nó không được dùng để khẳng định ngân hàng đã nhận tiền, vì đây không phải giao dịch ra ngân hàng.

### 4.4. Thời gian không thay thế thứ tự nghiệp vụ

`occurred_at` mô tả thời điểm sự kiện xảy ra theo nguồn được định nghĩa; `recorded_at` mô tả thời điểm hệ thống ghi nhận. Với webhook đến muộn, hai mốc có thể cách xa nhau. Không lấy thời gian do client gửi làm bằng chứng tin cậy về lúc phê duyệt.

Dùng UTC cho lưu trữ và chuyển múi giờ ở lớp hiển thị. Đồng thời cần phiên bản hoặc thứ tự sự kiện trong từng movement. Đồng hồ lệch, thông điệp đến muộn và xử lý song song làm cho việc sắp xếp theo timestamp đơn thuần không đủ.

Một ID tăng dần được cấp trước commit cũng không tự chứng minh thứ tự commit toàn cục. Nếu cần thứ tự chuyển trạng thái theo movement, phải cấp phiên bản trong cơ chế khóa hoặc kiểm soát đồng thời tương ứng.

## 5. Liên kết audit với sổ cái cân bằng

### 5.1. Ví dụ bút toán cho ví nội bộ

Giả sử số dư ví khách hàng được mô hình hóa là khoản nợ phải trả của nền tảng đối với khách hàng. Khi U1 chuyển 250.000 VND cho U2 và không có phí:

| Tài khoản | Bên Nợ | Bên Có | Diễn giải |
|---|---:|---:|---|
| Nợ phải trả ví U1 | 250.000 VND | 0 | Giảm nghĩa vụ với U1 |
| Nợ phải trả ví U2 | 0 | 250.000 VND | Tăng nghĩa vụ với U2 |
| Tổng | 250.000 VND | 250.000 VND | Nhóm bút toán cân bằng |

Trong mô hình này, ghi Nợ tài khoản nợ phải trả làm giảm nghĩa vụ; ghi Có làm tăng nghĩa vụ. Không được đồng nhất “Nợ” với “số dư ví tăng” cho mọi loại tài khoản. Quy tắc tính số dư phụ thuộc loại tài khoản và hệ thống kế toán đã chọn.

Nếu U1 chịu thêm 2.000 VND phí, một cách biểu diễn trong mô hình ví dụ là:

| Tài khoản | Bên Nợ | Bên Có |
|---|---:|---:|
| Nợ phải trả ví U1 | 252.000 VND | 0 |
| Nợ phải trả ví U2 | 0 | 250.000 VND |
| Doanh thu phí | 0 | 2.000 VND |
| Tổng | 252.000 VND | 252.000 VND |

Đây là minh họa kỹ thuật cho mô hình ví nội bộ, không mô tả đầy đủ hạch toán thanh toán qua ngân hàng, thuế hay quy tắc ghi nhận doanh thu của mọi sản phẩm. Khi áp dụng cần dùng hệ thống tài khoản đã được xác định cho nghiệp vụ thực tế.

### 5.2. Constraint cần bảo vệ cả nhóm bút toán

Các ràng buộc thường cần có:

- Số tiền của từng dòng dương, nằm trong miền cho phép; bên Nợ/Có là giá trị hợp lệ.
- Mỗi dòng thuộc tài khoản có thật, đúng tenant và đúng tiền tệ.
- Nhóm bút toán chỉ được ghi một lần cho một hiệu lực nghiệp vụ.
- Tổng Nợ bằng tổng Có cho mỗi tiền tệ trong nhóm được ghi sổ.
- Movement, journal và audit event liên kết đúng phạm vi dữ liệu.

`CHECK (amount_minor > 0)` bảo vệ một dòng, không tự kiểm tra được tổng nhiều dòng trong PostgreSQL bằng một biểu thức `CHECK` thông thường. Muốn bảo vệ điều kiện cân bằng tại database, cần cơ chế phù hợp như thủ tục ghi sổ với quyền ghi bị giới hạn và kiểm tra ở điểm hoàn tất, hoặc constraint trigger được thiết kế đúng theo transaction.

Chỉ kiểm tra tổng ở Java rồi để các đường import khác ghi trực tiếp vào ledger sẽ tạo đường bỏ qua invariant. Phải kiểm soát mọi đường ghi được phép vào vùng dữ liệu tài chính.

Nếu có nhiều tiền tệ, không bù 100 USD bên Nợ bằng một số VND bên Có rồi gọi là cân bằng. Chuyển đổi tiền tệ cần mô hình tài khoản, các nhóm dòng và bằng chứng tỷ giá phù hợp; kiểm tra cân bằng theo từng tiền tệ không được bỏ qua vì tổng số học tình cờ bằng nhau.

### 5.3. Số dư hiện tại là dữ liệu dẫn xuất có kiểm soát

Một bảng số dư có thể được duy trì để xử lý nhanh, nhưng cần cập nhật nhất quán với journal và có khả năng đối chiếu lại từ các bút toán đã ghi sổ. Không cho phép sửa số dư bằng endpoint quản trị mà không có dịch chuyển hoặc điều chỉnh tương ứng.

Nếu có giữ chỗ tiền, phải phân biệt số dư đã ghi sổ và khả dụng. Ví dụ một mô hình là:

```text
available_balance = posted_balance - active_reservations
```

Công thức này giả định khoản giữ chỗ chưa bị trừ lần nữa vào `posted_balance`. Khi thành công, hệ thống ghi sổ khoản chi và kết thúc reservation nhất quán. Nếu đã hạch toán giữ chỗ bằng tài khoản ledger riêng thì cần công thức khả dụng tương ứng, không áp dụng thêm phép trừ để trừ tiền hai lần.

## 6. Ghi tiền và bằng chứng trong cùng transaction

### 6.1. Luồng chuyển ví nội bộ

Với dữ liệu cùng nằm trong một database có transaction, có thể tổ chức luồng như sau:

```text
BEGIN
  1. Xác minh tenant, actor và quyền với nguồn tiền.
  2. Nhận diện yêu cầu theo idempotency key bằng khóa duy nhất.
  3. Nếu đã tồn tại, kiểm tra payload và quyền xem kết quả rồi trả kết quả cũ.
  4. Khóa các hàng số dư liên quan theo thứ tự thống nhất.
  5. Kiểm tra trạng thái, nội dung được duyệt và số tiền khả dụng.
  6. Tạo movement và các dòng journal cân bằng.
  7. Cập nhật số dư hoặc projection đồng bộ theo thiết kế.
  8. Ghi audit event mô tả đúng hiệu lực tài chính.
  9. Ghi outbox event nếu cần phát thông điệp sau commit.
COMMIT
```

Các bước là mô hình điều khiển, không phải SQL có thể chạy trực tiếp. Cách xử lý xung đột khóa duy nhất và thứ tự khóa phải phù hợp với database, tránh nuốt lỗi transaction rồi tiếp tục ghi.

Nếu ghi audit bắt buộc thất bại, transaction tài chính cũng phải rollback. Không thực hiện kiểu “chuyển tiền trước, cố ghi audit sau” đối với bằng chứng bắt buộc của cùng hiệu lực tài chính.

Khóa các tài khoản theo thứ tự ổn định giúp giảm deadlock khi hai giao dịch chuyển ngược chiều. Vẫn cần xử lý deadlock hoặc lỗi đồng thời bằng cơ chế retry có idempotency; không biến một lần retry transaction thành dịch chuyển mới.

### 6.2. Tại sao cần outbox?

Ghi journal rồi gọi trực tiếp message broker tạo ra khoảng hở: database đã commit nhưng gửi sự kiện thất bại, hoặc sự kiện được gửi rồi transaction lại rollback.

Outbox ghi thông điệp cần phát trong cùng transaction với journal và audit. Worker đọc outbox và phát sau commit. Nếu worker crash sau khi gửi nhưng trước khi đánh dấu đã gửi, thông điệp có thể được gửi lại.

Do đó, outbox thường tạo luồng giao nhận có thể lặp; consumer cần chống trùng bằng `event_id` hoặc khóa hiệu lực phù hợp. Không gọi thiết kế này là bảo đảm “mỗi thông điệp chỉ được giao đúng một lần”. Mục tiêu là không làm mất sự kiện đã commit và không tạo thêm hiệu lực tài chính khi giao lặp.

### 6.3. Yêu cầu thất bại vẫn cần audit đúng loại

Nếu transaction bị rollback, audit event nằm trong transaction đó cũng bị rollback. Muốn ghi nhận việc thử chuyển tiền bị từ chối, cần một cơ chế ghi nhận riêng phù hợp sau rollback hoặc tại lớp kiểm soát truy cập.

Event phải thể hiện `DENIED` hoặc `FAILED` cùng lý do đã chuẩn hóa, không dùng tên như `TRANSFER_POSTED` cho một lần thử chưa có bút toán. Log vận hành cũng không được tuyên bố thành công trước khi commit.

Không thể đạt tính nguyên tử giữa database và một hệ thống audit độc lập chỉ bằng hai lệnh ghi nối tiếp. Cần thiết kế ranh giới đảm bảo rõ ràng và cơ chế phục hồi; với sự kiện thành công, có thể dùng bản ghi audit cục bộ cùng outbox để chuyển sang kho lưu giữ riêng.

## 7. State machine và bằng chứng từ cổng thanh toán

### 7.1. Tiếp nhận không đồng nghĩa thành công

Một luồng ra bên ngoài có thể dùng các trạng thái sau:

```text
REQUESTED -> AUTHORIZED -> EXECUTING -> SUCCEEDED
                                    -> FAILED
                                    -> UNKNOWN

UNKNOWN -> SUCCEEDED hoặc FAILED sau khi có bằng chứng đáng tin cậy
```

Đây là state machine minh họa. Sản phẩm có thể cần thêm bước phê duyệt, hủy, giữ chỗ hoặc quyết toán. Mỗi chuyển trạng thái phải có điều kiện và nguồn bằng chứng được xác định.

- `AUTHORIZED`: quyền và điều kiện nghiệp vụ đã được chấp nhận theo chính sách; chưa chứng minh tiền đã chuyển.
- `EXECUTING`: lệnh đang được xử lý; chưa có kết quả cuối cùng.
- `SUCCEEDED`: đã đạt tiêu chí thành công được định nghĩa cho loại movement đó.
- `FAILED`: có bằng chứng đủ tin cậy rằng thao tác không tạo hiệu lực thành công theo tiêu chí.
- `UNKNOWN`: chưa đủ bằng chứng kết luận, thường gặp khi timeout hoặc mất kết nối.

Không dùng một trạng thái thành công mơ hồ cho cả ghi sổ nội bộ, nhà cung cấp chấp nhận và quyết toán ngân hàng. Có thể tách trạng thái xử lý với trạng thái settlement nếu nghiệp vụ cần theo dõi cả hai.

### 7.2. Timeout là kết quả chưa biết

Khi gọi API chuyển tiền bị timeout, nhà cung cấp có thể đã thực hiện giao dịch. Đánh dấu `FAILED`, giải phóng tiền giữ chỗ và gửi một lệnh mới bằng ID khác có thể khiến tiền bị chi hai lần.

Hướng xử lý cần kết hợp:

1. Một mã lệnh ổn định cho movement khi gửi lại, theo hợp đồng idempotency của nhà cung cấp.
2. Trạng thái chưa biết và cơ chế truy vấn, nhận callback hoặc đối soát để làm rõ.
3. Quy tắc giữ chỗ tiền khi kết quả còn có thể thành công.
4. Audit cho từng lần thử mạng, tách khỏi một hiệu lực tài chính duy nhất.

Không mặc định mọi nhà cung cấp hỗ trợ idempotency vô thời hạn. Phải biết phạm vi, thời hạn và điều kiện sử dụng lại khóa. Không retry mù một lệnh có thể đã thành công sau khi hết thời hạn chống trùng.

Transaction của database nội bộ không bao trùm API bên ngoài. Cần lưu ý định gửi lệnh trước, thực thi có khả năng phục hồi và ghi kết quả có kiểm tra trùng; không giữ transaction khóa số dư trong suốt một cuộc gọi mạng dài rồi coi đó là tính nguyên tử phân tán.

### 7.3. Webhook phải được xác minh và áp dụng có điều kiện

Không lấy `movement_id`, số tiền hoặc trạng thái trong một request HTTP bất kỳ làm bằng chứng. Cần xác minh nguồn gửi theo cơ chế của nhà cung cấp, phạm vi tài khoản tích hợp và điều kiện chống phát lại tương ứng.

Sau khi xác minh:

- Ghi nhận thông điệp trong inbox hoặc kho tiếp nhận bền vững.
- Liên kết giao dịch bên ngoài với movement đúng tenant và đúng tài khoản tích hợp.
- So khớp số tiền, tiền tệ và tham chiếu cần thiết.
- Kiểm tra chuyển trạng thái hợp lệ trong transaction.
- Ghi hiệu lực tài chính tối đa theo khóa nghiệp vụ đã định, dù có nhiều webhook khác ID.

Một sự kiện `PENDING` đến muộn không được hạ giao dịch đã xác nhận thành công về đang xử lý. Nếu có sự kiện đảo giao dịch hoặc chargeback, phải xử lý theo loại nghiệp vụ tương ứng, không coi mọi cập nhật khác thành công là lỗi cần ghi đè lịch sử.

Audit cần phân biệt “đã nhận webhook”, “đã xác minh webhook” và “đã áp dụng hiệu lực”. Nhận thông điệp chưa đủ chứng minh tiền đã được ghi sổ.

## 8. Idempotency, phê duyệt và hoàn tiền

### 8.1. Chống trùng cần gắn với nội dung yêu cầu

Một bản ghi idempotency nên ràng buộc khóa với tenant, loại thao tác và nội dung nghiệp vụ chuẩn hóa. Các trường thường gồm nguồn tiền, người nhận, số tiền, tiền tệ và giao dịch gốc nếu có.

```text
Cùng key + cùng nội dung:
  Trả kết quả hoặc trạng thái hiện có của cùng movement.

Cùng key + nội dung khác:
  Từ chối do xung đột; không âm thầm dùng lại kết quả cho yêu cầu mới.
```

Phải có constraint duy nhất ở nơi chịu trách nhiệm chống trùng. Cách “SELECT chưa thấy rồi INSERT” không đủ khi hai request đồng thời cùng chạy.

Hash payload chỉ có ý nghĩa nếu quy tắc chuẩn hóa được định nghĩa: `250000`, `250000.0`, thứ tự trường JSON và các trường mặc định có thể khác biểu diễn nhưng cùng hoặc khác ý nghĩa theo hợp đồng. Không hash toàn bộ request tùy tiện rồi dùng làm định nghĩa nghiệp vụ.

Idempotency key không phải bằng chứng quyền. Người có key của người khác không được tự động đọc kết quả hoặc tạo lại hành động. Việc hết hạn bản ghi idempotency cũng không được làm mất các khóa duy nhất dài hạn dùng để ngăn ghi sổ lại cùng một hiệu lực.

### 8.2. Giữ nguyên nội dung đã duyệt

Nếu khoản chi cần phê duyệt, cần ràng buộc quyết định duyệt với phiên bản của nội dung: nguồn, người nhận, số tiền, tiền tệ, phí và các trường nhạy cảm khác.

Kẻ tấn công có thể xin duyệt 100.000 VND rồi đổi số tiền thành 10.000.000 VND trước khi thực thi. Audit chỉ lưu `approved = true` sẽ không giúp chứng minh việc thực thi có đúng nội dung được duyệt hay không.

Có thể dùng phiên bản bất biến hoặc digest nội dung chuẩn hóa được lưu cùng quyết định duyệt. Trước khi thực thi phải so khớp nội dung; thay đổi trường nhạy cảm cần quy trình duyệt lại theo chính sách. Nếu yêu cầu tách người tạo và người duyệt, kiểm tra điều đó trước khi chấp nhận bước duyệt, không chỉ ghi hai tên vào audit sau khi đã chi tiền.

### 8.3. Hoàn tiền là dịch chuyển mới liên kết giao dịch gốc

Không sửa số tiền giao dịch gốc về 0 hoặc xóa các dòng journal để biểu diễn hoàn tiền. Tạo movement mới có liên kết đến movement gốc, quyết định hoàn, bút toán và tham chiếu bên ngoài riêng.

Với hoàn từng phần, cần ngăn hai request đồng thời cùng thấy đủ hạn mức rồi tổng cộng hoàn vượt số đã thu. Một invariant có thể là:

```text
Tổng đã hoàn thành công
+ tổng đang giữ hạn mức cho các yêu cầu còn có thể thành công
<= số tiền được phép hoàn theo chính sách giao dịch gốc
```

Số tiền được phép hoàn phải xét đúng thành phần nghiệp vụ: tiền hàng, phí, thuế hoặc các khoản đã điều chỉnh theo chính sách. Không mặc định mọi phí đều được hoàn.

Kiểm tra và giữ hạn mức hoàn phải phối hợp trong transaction, chẳng hạn khóa hồ sơ giao dịch gốc hoặc dùng phép cập nhật có điều kiện. Request ở trạng thái `UNKNOWN` không được tự động bỏ khỏi hạn mức nếu nhà cung cấp vẫn có thể hoàn thành nó.

### 8.4. Điều chỉnh giữ nguyên lịch sử

Nếu ghi sai bút toán, tạo bút toán đảo hoặc điều chỉnh có liên kết và lý do, theo quy trình được cấp quyền. Không dùng câu lệnh sửa trực tiếp giá trị trong journal cũ để làm lịch sử trông như chưa có sai sót.

Việc đảo một chuyển ví nội bộ còn phải xét tiền khả dụng và các nghiệp vụ đã xảy ra sau đó. Nếu người nhận đã rút tiền, không thể giả định ghi bút toán ngược là đủ để thu hồi; có thể cần quy trình công nợ, tranh chấp hoặc xử lý ngoại lệ theo mô hình sản phẩm.

## 9. Chống sửa dấu vết và giới hạn dữ liệu nhạy cảm

### 9.1. Append-only là một lớp bảo vệ

Audit trail và journal đã ghi sổ nên có quy tắc không cập nhật hoặc xóa qua đường ứng dụng thông thường. Các biện pháp có thể gồm:

- Tách quyền đọc, tạo bản ghi và quyền quản trị schema.
- Chỉ cho ghi journal qua luồng hoặc thủ tục đã kiểm soát.
- Dùng tài khoản migration riêng với tài khoản runtime.
- Lưu bản sao audit tại nơi có quyền quản trị và chính sách lưu giữ tách biệt.
- Theo dõi việc truy cập, xuất dữ liệu và thao tác quản trị trên kho audit.

Nếu cùng một tài khoản có toàn quyền sửa journal, audit và bản sao, kẻ chiếm tài khoản đó có thể sửa cả hành vi lẫn dấu vết. Từ “append-only” trong tài liệu không tự tạo khả năng chống sửa ở database.

### 9.2. Hash chain có giá trị và giới hạn

Có thể nối sự kiện bằng hash:

```text
hash_i = H(hash_trước || nội_dung_sự_kiện_đã_chuẩn_hóa)
```

Chuỗi hash giúp phát hiện nội dung hoặc thứ tự bị thay đổi khi có mốc kiểm chứng đáng tin cậy. Nó không tự chứng minh sự kiện ban đầu là đúng và không tự ngăn việc ghi một giao dịch trái phép.

Nếu kẻ tấn công sửa được toàn bộ chuỗi và mốc cuối, họ có thể tính lại hash. Để tăng giá trị bằng chứng, có thể lưu mốc kiểm chứng ngoài miền quản trị của hệ thống ghi, hoặc dùng chữ ký với quản lý khóa phù hợp. Vẫn cần bảo vệ khóa và kiểm chứng định kỳ.

Cần quy định chuẩn hóa nội dung, thuật toán, phiên bản, phạm vi chuỗi và thứ tự cấp số khi ghi đồng thời. Một chuỗi toàn hệ thống có thể trở thành điểm tranh chấp ghi; phân vùng theo phạm vi rõ ràng cần giữ được quy tắc kiểm chứng từng chuỗi.

Hash chain cũng không tự phát hiện việc cắt bỏ phần cuối nếu không có mốc bên ngoài cho biết chuỗi từng dài hơn. Vì thế, không hứa “audit không thể bị sửa” chỉ vì mỗi hàng có một trường hash.

### 9.3. Lưu đủ bằng chứng, tránh lưu bí mật

Không đưa mật khẩu, access token, API secret, mã xác thực thanh toán hoặc dữ liệu thẻ nhạy cảm vào audit payload. Với tài khoản nhận tiền và thông tin cá nhân, ưu tiên tham chiếu nội bộ hoặc dữ liệu đã che phù hợp với nhu cầu truy vết.

Nếu phải lưu chứng từ hoặc payload nhà cung cấp để điều tra, cần vùng lưu riêng có giới hạn truy cập, mã hóa và thời hạn lưu phù hợp. Không coi toàn bộ request/response là dữ liệu được phép sao chép vô điều kiện vào log tập trung.

Hash một giá trị ít khả năng, như số điện thoại hoặc định danh có miền đoán nhỏ, không tự làm dữ liệu trở nên ẩn danh. Cần đánh giá mục đích tra cứu, phạm vi truy cập và cách bảo vệ tương ứng.

## 10. Đối soát để tìm điều không xuất hiện trong log

Audit event thành công có thể đầy đủ trong khi bảng số dư sai, hoặc có giao dịch thành công ở nhà cung cấp nhưng nội bộ chưa ghi nhận. Đối soát phải so sánh các nguồn độc lập, không chỉ đếm các dòng log `SUCCESS`.

### 10.1. Đối soát nội bộ

Các kiểm tra quan trọng gồm:

- Mỗi movement đã ghi hiệu lực có nhóm journal mong đợi và audit event tương ứng.
- Không có journal không liên kết được về nghiệp vụ hợp lệ.
- Mỗi nhóm bút toán cân bằng theo tiền tệ.
- Số dư dẫn xuất khớp ledger theo quy tắc tài khoản.
- Reservation đang hoạt động liên kết đúng movement và trạng thái.
- Không có nhiều nhóm ghi sổ cho cùng một hiệu lực mà chính sách chỉ cho phép một.
- Tổng hoàn và giữ hạn mức hoàn không vượt giới hạn của giao dịch gốc.

Một movement có hai nhóm bút toán cân bằng vẫn có thể là lỗi chuyển tiền hai lần. Vì vậy, kiểm tra cân bằng và kiểm tra duy nhất phải độc lập.

### 10.2. Đối soát bên ngoài

So khớp movement với dữ liệu đáng tin cậy từ nhà cung cấp, báo cáo settlement hoặc sao kê theo mô hình tích hợp. Cần xét mã giao dịch, tài khoản nhà cung cấp, tiền tệ, số tiền, phí và thời điểm chốt.

Không mặc định một dòng sao kê luôn tương ứng một movement. Nhà cung cấp có thể gộp nhiều giao dịch thành khoản quyết toán ròng, trừ phí hoặc có độ trễ giữa ngày xử lý và ngày quyết toán. Quy tắc đối soát phải biểu diễn được các quan hệ này.

Phân loại sai lệch để xử lý đúng:

| Sai lệch | Hướng điều tra |
|---|---|
| Bên ngoài thành công, nội bộ còn `UNKNOWN` | Xác minh bằng chứng rồi áp dụng kết quả có chống trùng |
| Nội bộ thành công, chưa có kết quả bên ngoài | Kiểm tra định nghĩa thành công, độ trễ và trạng thái nhà cung cấp |
| Số tiền hoặc tiền tệ không khớp | Kiểm tra payload, mapping, phí và nguy cơ giả mạo |
| Một giao dịch bên ngoài gắn nhiều movement | Điều tra khóa duy nhất, retry và liên kết sai |
| Sai lệch tổng settlement | Kiểm tra gộp lô, phí, cut-off, đảo giao dịch và dữ liệu thiếu |

Không tự động tạo thêm khoản chuyển tiền chỉ vì một báo cáo chưa khớp. Công cụ xử lý ngoại lệ phải giữ bằng chứng, có quyền phù hợp và tạo audit cho quyết định điều chỉnh.

### 10.3. Truy vấn phát hiện bút toán không cân bằng

Ví dụ dưới đây giả định `journal_lines` có các cột `tenant_id`, `journal_id`, `currency`, `side` và `amount_minor`; `side` chỉ nhận `DEBIT` hoặc `CREDIT`, số tiền dương. Đây là truy vấn giám sát, không thay thế constraint ghi sổ.

```sql
SELECT
    tenant_id,
    journal_id,
    currency,
    SUM(CASE WHEN side = 'DEBIT' THEN amount_minor ELSE 0 END)
        AS debit_total,
    SUM(CASE WHEN side = 'CREDIT' THEN amount_minor ELSE 0 END)
        AS credit_total
FROM journal_lines
GROUP BY tenant_id, journal_id, currency
HAVING
    SUM(CASE WHEN side = 'DEBIT' THEN amount_minor ELSE 0 END)
    <>
    SUM(CASE WHEN side = 'CREDIT' THEN amount_minor ELSE 0 END);
```

Không có hàng trả về chỉ chứng minh điều kiện tổng trên các dòng đã được truy vấn. Nó không chứng minh không có journal rỗng, thiếu cả nhóm bút toán, sai tài khoản, sai người nhận hoặc ghi trùng hai nhóm đều cân bằng.

## 11. Kiểm thử các tình huống lạm dụng logic

### 11.1. Ma trận kiểm thử

| Tình huống | Điều cần chứng minh |
|---|---|
| Client sửa giá hoặc phí | Backend dùng kết quả tính có thẩm quyền; audit thể hiện kết quả và chính sách đã áp dụng |
| Người dùng thay tài khoản nguồn sang người khác | Bị từ chối trước hiệu lực tài chính; có sự kiện từ chối đúng loại |
| Thay tenant hoặc người nhận ngoài phạm vi | Không thể tạo liên kết và thao tác trái quyền |
| Đổi số tiền sau khi duyệt | Không thực thi bằng quyết định duyệt của phiên bản cũ |
| Tự duyệt khoản chi bị cấm | Không vượt qua điều kiện tách vai trò |
| Hai request đồng thời cùng idempotency key | Một movement và một hiệu lực; phản hồi còn lại quy chiếu về kết quả hiện có |
| Cùng key nhưng khác số tiền hoặc người nhận | Từ chối xung đột, không trả kết quả thành công sai ngữ nghĩa |
| Hai yêu cầu chi cùng tranh số dư | Không làm số dư khả dụng vượt giới hạn cho phép |
| Hai yêu cầu hoàn từng phần đồng thời | Không vượt tổng hạn mức hoàn |
| Webhook bị giả mạo | Không được dùng làm bằng chứng thành công |
| Webhook lặp, kể cả event ID khác nhau cho cùng hiệu lực | Không ghi journal lần thứ hai |
| Webhook cũ đến sau sự kiện cuối | Không làm trạng thái lùi trái state machine |
| Tài khoản runtime thử sửa hoặc xóa journal đã ghi | Bị chặn theo mô hình quyền và bất biến đã thiết kế |
| Số tiền quá lớn, âm hoặc sai scale | Bị từ chối; không tràn số hay làm tròn ngầm |

### 11.2. Kiểm thử crash và kết quả chưa biết

Các điểm ngắt cần mô phỏng có chủ đích:

1. **Trước commit nội bộ:** không được có bút toán hoặc số dư thay đổi dở; lần thử thất bại không được mô tả là đã chuyển tiền.
2. **Sau commit nhưng trước trả HTTP:** retry phải trả về cùng movement; không tạo hiệu lực mới.
3. **Sau khi nhà cung cấp nhận lệnh nhưng trước khi có phản hồi:** giữ kết quả chưa biết và xác minh bằng mã lệnh ổn định; không tự kết luận thất bại.
4. **Sau khi gửi outbox nhưng trước đánh dấu đã gửi:** consumer nhận lặp vẫn không tạo hiệu lực tài chính trùng.
5. **Sau khi nhận webhook nhưng trước áp dụng:** cơ chế inbox hoặc tiếp nhận bền vững cho phép xử lý lại mà không mất thông điệp.
6. **Khi ghi audit bắt buộc thất bại:** hiệu lực tài chính trong cùng transaction phải rollback.

Với race condition, dùng hai kết nối và điểm đồng bộ rõ ràng để điều khiển thứ tự, thay vì chỉ thêm thời gian ngủ. Thử cả thứ tự commit thuận và ngược ở các tình huống tranh số dư, hoàn tiền và đổi quyền.

### 11.3. Kiểm tra trạng thái cuối, không chỉ mã phản hồi

Sau mỗi ca, cần kiểm tra movement, journal, audit, số dư, reservation và thông điệp liên quan. Một API trả lỗi vẫn có thể đã chi tiền; một API trả thành công vẫn có thể chưa ghi đủ dữ liệu.

Những khẳng định có giá trị gồm:

- Đúng một hiệu lực tài chính cho hành động được chấp nhận.
- Không có hiệu lực cho hành động bị từ chối.
- Số dư, hạn mức và bút toán khớp mô hình.
- Mọi chuyển trạng thái thành công có bằng chứng tương ứng.
- Lịch sử đủ để nối từ người yêu cầu đến quyết định quyền, bút toán và kết quả bên ngoài.
- Dữ liệu audit không lộ bí mật hoặc tài nguyên ngoài quyền.

## 12. Ví dụ điều tra: hoàn tiền hai lần sau timeout

Giả sử khách hàng được hoàn 300.000 VND. Request đầu gọi cổng thanh toán bị timeout. Backend trả lỗi nhưng không lưu mã movement ổn định. Người dùng gửi lại, tạo yêu cầu mới; cả hai lần gọi cuối cùng đều thành công.

Nếu chỉ có hai log lỗi HTTP và một log `refund success`, hệ thống có thể không nhận ra đã hoàn 600.000 VND. Một thiết kế truy vết đầy đủ sẽ cho thấy:

```text
Giao dịch gốc: PAY-42, hạn mức hoàn còn lại 300.000 VND.

REF-1: yêu cầu hoàn 300.000 VND.
  - Giữ hạn mức hoàn.
  - Gửi lệnh với mã ổn định REF-1.
  - Timeout -> UNKNOWN, chưa giải phóng hạn mức.

Client gửi lại cùng hành động.
  - Cùng idempotency key -> tiếp tục theo dõi REF-1.
  - Không tạo REF-2 để thay thế một kết quả chưa rõ.

Nhận bằng chứng thành công từ nhà cung cấp.
  - Liên kết về REF-1.
  - Ghi bút toán, audit và kết thúc giữ hạn mức nhất quán.

Webhook hoặc kết quả truy vấn đến lặp.
  - Nhận diện đã áp dụng hiệu lực.
  - Không ghi bút toán lần nữa.
```

Ngay cả khi client cố ý đổi idempotency key để tạo một yêu cầu hoàn mới, invariant hạn mức hoàn vẫn phải chặn khoản vượt. Idempotency xử lý gửi lại cùng hành động; kiểm tra tổng hạn mức bảo vệ quy tắc nghiệp vụ khi có nhiều hành động khác nhau.

Nếu hệ thống cũ đã hoàn trùng, không xóa một bản ghi để làm báo cáo trông đúng. Cần giữ lịch sử, ghi nhận sai lệch, xác minh tiền thực tế và thực hiện điều chỉnh có thẩm quyền. Audit tốt giúp giải thích sai sót và kiểm chứng cách khắc phục, đồng thời các invariant phải được sửa để ngăn tái diễn.

## 13. Những câu hỏi cần chốt trước khi triển khai

- “Thành công” đang chỉ ghi sổ nội bộ, được nhà cung cấp xác nhận hay đã quyết toán?
- Nội dung nào bất biến sau phê duyệt và bằng chứng duyệt gắn với phiên bản nào?
- Điểm nào bảo vệ quyền, tenant, số tiền, số dư, chống trùng và tổng có thể hoàn?
- Journal, số dư, audit và outbox có cùng commit hoặc cơ chế phục hồi nào?
- Trạng thái chưa biết được giữ và giải quyết ra sao để không chi lại hoặc giải phóng tiền quá sớm?
- Mọi số tiền đã ghi sổ có thể nối về hành động, người có thẩm quyền và tham chiếu bên ngoài tương ứng không?
- Ai có thể sửa dữ liệu tài chính hoặc dấu vết, và việc đó được kiểm soát, phát hiện thế nào?
- Đối soát nào phát hiện được dữ liệu thiếu, ghi trùng, sai số tiền và lệch quyết toán?

Khi các câu hỏi này có câu trả lời kiểm chứng được, money movement audit trở thành một phần của cơ chế bảo vệ logic nghiệp vụ: mỗi hiệu lực tiền có nguồn gốc, có thẩm quyền, có bằng chứng và có đường đối chiếu để phát hiện sai lệch.
