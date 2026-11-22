# Sự kiện bất biến, sửa sai và hành động bù trừ

## 1. Vì sao lưu sự kiện bất biến vẫn phải có cơ chế sửa sai?

Trong mô hình sự kiện, một bản ghi như **PaymentCaptured** hoặc **EquipmentReturned** thường biểu diễn một sự việc đã được hệ thống chấp nhận. Nếu bản ghi đó được dùng làm nguồn dữ liệu để dựng lại trạng thái, việc sửa hoặc xóa âm thầm sẽ khiến cùng một lịch sử cho ra những cách giải thích khác nhau, làm mất khả năng đối chiếu với thông báo, báo cáo hoặc quyết định đã phát sinh trước đó.

Tuy nhiên, thế giới nghiệp vụ không hoàn hảo. Nhân viên có thể nhập sai thời hạn trả, cảm biến gửi thông tin sai, chính sách được áp dụng nhầm hoặc một giao dịch bên ngoài đã thực sự thực hiện nhưng cần hoàn lại. Thiết kế dữ liệu phải giải quyết đồng thời hai yêu cầu:

- **Giữ nguyên dấu vết** về những gì hệ thống đã từng ghi nhận và dùng để ra quyết định.
- **Cho phép diễn tiến tiến tới trạng thái đúng** bằng những sự kiện điều chỉnh và hành động bù trừ được xác nhận, có quyền hạn, bằng chứng và thời điểm rõ ràng.

Giả sử hệ thống cho thuê thiết bị ghi nhận:

| Thứ tự | Sự kiện | Ý nghĩa tại thời điểm ghi |
| ---: | --- | --- |
| 1 | **RentalStarted** | Hợp đồng bắt đầu, hạn trả lúc 10:00. |
| 2 | **EquipmentDroppedOff** | Kiosk tiếp nhận thiết bị lúc 10:30. |
| 3 | **LateFeeAssessed** | Hệ thống tính phí trả trễ 100.000 VND. |
| 4 | **RentalDueDateCorrectionApproved** | Quản lý xác nhận hạn đúng phải là 11:00, dựa vào chứng từ gia hạn. |
| 5 | **LateFeeAssessmentReversed** | Khoản phí 100.000 VND được đảo/miễn theo quyết định mới. |

Trạng thái cuối cùng là **không còn phí trễ phải thu**. Nhưng sự kiện số 3 vẫn có ý nghĩa: hệ thống đã từng tính phí và có thể đã thông báo cho khách. Xóa số 3 sẽ làm mất nguyên nhân của việc đảo phí ở số 5. Nếu phí đã được thu bằng tiền, còn cần một quy trình **hoàn tiền thật** và sự kiện xác nhận tương ứng.

**Câu hỏi cốt lõi của bài học:** khi dữ liệu cũ sai hoặc kết quả nghiệp vụ cần đảo ngược, ta nên **điều chỉnh thông tin**, **ghi diễn tiến nghiệp vụ mới**, hay **thực hiện hành động bù trừ**? Quyết định phải xuất phát từ ý nghĩa nghiệp vụ, không chỉ từ khả năng UPDATE/DELETE của database.

## 2. Hiểu đúng về tính bất biến của sự kiện

Trong event sourcing, chuỗi sự kiện đã chấp nhận thường được thiết kế theo nguyên tắc **append-only**: mỗi thay đổi mới được ghi bằng event mới, và các event trước đó không bị sửa tùy tiện. Tính bất biến này giúp:

1. **Replay:** áp dụng lại các sự kiện theo thứ tự để dựng trạng thái.
2. **Truy vết:** giải thích tại sao trạng thái từng chuyển từ A sang B.
3. **Đối chiếu:** so sánh dữ liệu với thông điệp đã công bố, quyết định đã phê duyệt và chứng từ bên ngoài.
4. **Tái tạo projection:** sửa lỗi trong logic tổng hợp mà vẫn có dữ liệu lịch sử cần thiết.
5. **Phân tích theo thời gian:** tính thời gian xử lý, tỷ lệ điều chỉnh, nguyên nhân bù trừ và các chỉ số vận hành.

Nhưng cần nêu rõ **phạm vi bất biến**. Một record event có thể là nguồn sự thật của *việc hệ thống đã ghi nhận/ra quyết định*, còn dữ liệu bên trong có thể về sau được chứng minh là không phản ánh đúng thế giới. Vì vậy:

- **Bất biến của bản ghi** không có nghĩa **mọi thông tin trong bản ghi đều đúng vĩnh viễn**.
- **Sự thật lịch sử về quyết định** khác với **sự thật sau khi được điều chỉnh**.
- **Append-only ở tầng ứng dụng** không tự bảo đảm chống sửa bởi quản trị viên, sự cố lưu trữ hay người có quyền trực tiếp.
- **Bất biến kỹ thuật** không có nghĩa được phép giữ mọi dữ liệu cá nhân vô thời hạn. Quy định về lưu trữ, xóa, ẩn danh và truy cập vẫn áp dụng.

Ví dụ **FeeAssessed** có thể là sự thật “hệ thống đã áp mức phí này” ngay cả khi mức phí bị áp sai. Event **FeeAssessmentReversed** tạo ra diễn tiến hợp lệ để không còn khoản phải thu. Ngược lại, nếu dữ liệu của event đã bị hỏng khi ghi xuống đĩa, đó là **sự cố toàn vẹn dữ liệu**, không nên xử lý như thể khách vừa thực hiện một giao dịch bù trừ.

## 3. Phân biệt ba loại thay đổi: sửa sự thật, đảo quyết định và bù trừ tác động

Ba hoạt động gần nhau nhưng không hoàn toàn trùng nghĩa:

| Tình huống | Điều cần ghi nhận | Ví dụ | Kết quả mong đợi |
| --- | --- | --- | --- |
| **Thông tin nguồn được xác minh lại** | **Correction event** nêu giá trị đúng, nguồn bằng chứng, thời điểm hiệu lực. | **RentalDueDateCorrectionApproved** sửa hạn trả từ 10:00 thành 11:00. | Projection diễn giải hạn trả theo thông tin mới nhưng vẫn thấy lịch sử sửa. |
| **Quyết định nghiệp vụ đã ghi cần vô hiệu/điều chỉnh** | **Reversal/adjustment event** tham chiếu quyết định cũ và nêu số lượng hoặc phạm vi điều chỉnh. | **LateFeeAssessmentReversed** hủy khoản phí trễ đã đánh giá. | Nghĩa vụ tài chính đang hiệu lực được tính lại. |
| **Một hiệu ứng thực tế đã xảy ra và cần hành động ngược lại** | **Compensating action** được thực thi; sau xác nhận, phát event về kết quả. | Nhà thanh toán đã thu 100.000 VND; thực hiện hoàn và ghi **RefundConfirmed**. | Dòng tiền thực tế được điều chỉnh, có chứng từ riêng. |

Một sự kiện nghiệp vụ như **OrderCancelled** chỉ thể hiện trạng thái đơn bị hủy. Nó không chứng minh một khoản tiền đã được hoàn, kiện hàng đã quay lại kho hay email đã được thu hồi. Các tác động đó có điều kiện, người chịu trách nhiệm và bằng chứng riêng.

### Sửa sai dữ liệu không đồng nghĩa xóa dấu vết

Nếu nhân viên nhập sai ngày hẹn và đã có các quyết định phụ thuộc vào nó, **DueDateCorrected** nên thể hiện cả giá trị cũ, giá trị mới, lý do và chứng từ. Cần tránh chỉ cập nhật cột `due_at` hiện hành rồi bỏ qua việc báo cáo, phí phạt và thông báo trước đó đã sử dụng giá trị sai.

### Bù trừ không nhất thiết “hoàn nguyên” thế giới

Trong giao dịch phân tán, **compensation** là một hành động nghiệp vụ nhằm xử lý hậu quả của bước đã thành công khi quy trình chung gặp vấn đề. Nó không bảo đảm đưa thế giới trở về trạng thái ban đầu theo nghĩa toán học.

Ví dụ:

- Có thể **hoàn một khoản tiền đã thu**, nhưng hai giao dịch thu và hoàn vẫn tồn tại; phí xử lý của nhà cung cấp có thể không được hoàn.
- Có thể **tạo lệnh thu hồi hàng đã giao**, nhưng không thể làm như chưa từng vận chuyển.
- Có thể **gửi email đính chính**, nhưng không thể bảo đảm người nhận chưa đọc email đầu.
- Có thể **giải phóng ghế đã giữ**, nhưng thời gian ghế từng bị khóa vẫn có thể ảnh hưởng trải nghiệm khách.

Đặt tên event theo kết quả thực tế: **RefundRequested**, **RefundApproved**, **RefundConfirmed**, **RefundFailed** là các mốc khác nhau. Tránh ghi **RefundConfirmed** ngay lúc mới gọi API hoàn tiền.

## 4. Thiết kế sự kiện sửa sai như một hợp đồng nghiệp vụ

Một event điều chỉnh phải đủ rõ để người đọc sau này xác định **điều gì bị sửa**, **sửa đến mức nào**, **ai có quyền làm** và **từ khi nào áp dụng**.

Các nhóm thông tin thường cần:

| Nhóm | Trường ví dụ | Lý do |
| --- | --- | --- |
| Định danh event | `event_id`, `event_type`, `schema_version` | Phân biệt sự kiện và diễn giải đúng cấu trúc. |
| Đối tượng và thứ tự | `tenant_id`, `aggregate_type`, `aggregate_id`, `stream_version` | Gắn điều chỉnh với stream và thứ tự được chấp nhận. |
| Tham chiếu điều chỉnh | `corrects_event_id`, `reverses_event_id` hoặc ID quyết định/chứng từ | Biết chính xác sự kiện hay nghĩa vụ nào bị tác động. |
| Dữ liệu được chấp nhận | `old_due_at`, `new_due_at`, `reversed_amount_minor`, `currency` | Có thể áp dụng deterministic và đối chiếu giá trị. |
| Lý do và bằng chứng | `reason_code`, `evidence_id`, `policy_version` | Tránh một trường lý do tự do không thể kiểm chứng. |
| Chủ thể ra quyết định | `actor_type`, `actor_id`, `approved_by` | Truy vết quyền hạn; không nhầm người yêu cầu với người phê duyệt. |
| Thời gian | `occurred_at`, `recorded_at`, `effective_at` | Phân biệt khi chấp thuận, khi lưu và khi có hiệu lực. |
| Đối chiếu quy trình | `correlation_id`, `causation_id`, `idempotency_key` | Nối quy trình và tránh gửi lặp. |

Một payload JSON minh họa:

~~~json
{
  "event_id": "4e2c0ccf-805a-4ee4-9487-13094ba5c21d",
  "event_type": "RentalDueDateCorrectionApproved",
  "schema_version": 1,
  "tenant_id": "t-hcm",
  "aggregate_type": "Rental",
  "aggregate_id": "RENT-204",
  "stream_version": 4,
  "occurred_at": "2026-11-20T05:00:00Z",
  "recorded_at": "2026-11-20T05:00:02Z",
  "effective_at": "2026-11-19T10:00:00Z",
  "actor": {
    "type": "STAFF",
    "id": "MGR-18"
  },
  "payload": {
    "old_due_at": "2026-11-20T03:00:00Z",
    "new_due_at": "2026-11-20T04:00:00Z",
    "reason_code": "APPROVED_EXTENSION_OMITTED",
    "evidence_id": "EXT-559",
    "corrects_business_fact": "rental_due_at"
  }
}
~~~

Ở đây `occurred_at` là lúc **quản lý xác nhận điều chỉnh**, `recorded_at` là lúc event được ghi, còn `effective_at` là thời điểm **quyết định gia hạn trước đó đáng lẽ có hiệu lực** theo bằng chứng. Ba giá trị có ngữ nghĩa khác nhau. Các ID và thời gian chỉ để minh họa.

Điều chỉnh có hiệu lực hồi tố **không nên làm lại thứ tự stream**: event phiên bản 4 vẫn được append ở vị trí 4, dù `effective_at` sớm hơn một số event trước đó. Nếu chỉ muốn dựng trạng thái theo thứ tự ghi nhận, replay theo `stream_version`; nếu cần lịch sử “có hiệu lực tại thời điểm X” hoặc “hệ thống biết gì vào thời điểm Y”, phải định nghĩa quy tắc truy vấn thời gian rõ ràng.

### Cần kiểm tra gì trước khi chấp nhận correction?

1. **Nguồn/căn cứ:** có chứng từ hoặc chính sách cho phép điều chỉnh không?
2. **Quyền hạn:** actor có quyền sửa dữ kiện này và mức sửa này không?
3. **Đối tượng:** ID hợp đồng, sự kiện hoặc quyết định tham chiếu có tồn tại và thuộc phạm vi được phép không?
4. **Trạng thái hiện tại:** điều chỉnh đã được áp dụng chưa, đã bị thay bằng một điều chỉnh khác chưa?
5. **Hệ quả:** sửa ngày trả có làm phí hoặc chỉ số khác phải tính lại không? Những điều chỉnh đó có cần event riêng không?
6. **Tính nhất quán:** command có dựa trên version mới nhất của aggregate và có khóa chống gửi lặp không?

Hãy xác định policy khi **một sự kiện bị sửa nhiều lần**. Chẳng hạn, chỉ chấp nhận correction kế tiếp nếu tham chiếu đến phiên bản quyết định đang có hiệu lực; hoặc sử dụng một quy trình phê duyệt điều chỉnh nhiều bước với trạng thái rõ.

## 5. Thiết kế riêng sự kiện bù trừ và kết quả của tác động bên ngoài

Giả sử một cổng thanh toán đã thực hiện **hai giao dịch thu tiền độc lập** cho cùng nghĩa vụ. Hai giao dịch có mã xác nhận thực tế khác nhau: `CAP-201` và `CAP-202`. Đây là hai sự kiện có thật ở bên thanh toán, dù giao dịch thứ hai không được mong đợi.

Không nên xóa **PaymentCaptured** thứ hai khỏi lịch sử, vì tiền đã bị thu. Luồng xử lý hợp lý hơn:

~~~mermaid
flowchart TD
    A["PaymentCaptured: CAP-201"] --> B["PaymentCaptured: CAP-202"]
    B --> C["Phát hiện thu thừa; kiểm tra và phê duyệt"]
    C --> D["RefundRequested: bù trừ CAP-202"]
    D --> E{"Nhà thanh toán trả kết quả"}
    E -->|"Đã xác nhận hoàn"| F["RefundConfirmed"]
    E -->|"Thất bại rõ ràng"| G["RefundFailed / xử lý lại theo chính sách"]
    E -->|"Chưa rõ kết quả"| H["Đối soát, không phát thành công"]
~~~

Từng bước có ý nghĩa khác nhau:

- **PaymentCaptured**: phản ánh việc nguồn tin cậy đã xác nhận thu tiền. Với callback trùng của **cùng một** giao dịch, hệ thống phải khử lặp; không tạo sự kiện thu tiền thứ hai.
- **RefundRequested**: đã tạo yêu cầu hoàn cho khoản thu thừa, chưa có bằng chứng tiền đã hoàn.
- **RefundConfirmed**: nhà thanh toán xác nhận một lần hoàn có định danh và số tiền rõ ràng.
- **RefundFailed**: yêu cầu hoàn thất bại theo kết quả được biết; có thể cần thao tác mới sau khi kiểm tra.
- **Pending/unknown**: timeout hoặc lỗi mạng không phải bằng chứng thất bại hay thành công; cần truy vấn trạng thái/đối soát trước khi quyết định.

Nếu bên thanh toán đã thu 2 × 100.000 VND và xác nhận hoàn 100.000 VND cho giao dịch thứ hai, **tổng thu gộp** là 200.000 VND, **tổng hoàn** là 100.000 VND và **dòng tiền ròng** là 100.000 VND. Lịch sử vẫn cho thấy cả ba chuyển động tiền thật.

Trong một hệ thống tính phí, có thể phải đồng thời ghi **đảo khoản phải thu** trong mô hình kế toán và thực hiện **hoàn khoản đã thu**. Hai việc có hệ quả khác nhau: đảo nghĩa vụ trong sổ không tự tạo ra giao dịch ngân hàng.

### Hợp đồng tối thiểu của một sự kiện hoàn tiền được xác nhận

~~~json
{
  "event_id": "5fd039dc-57b3-43bf-91f2-14e8be88ff8c",
  "event_type": "RefundConfirmed",
  "schema_version": 1,
  "aggregate_type": "Payment",
  "aggregate_id": "PAY-992",
  "stream_version": 5,
  "occurred_at": "2026-11-20T06:30:00Z",
  "recorded_at": "2026-11-20T06:30:03Z",
  "payload": {
    "refund_id": "REF-778",
    "compensates_capture_id": "CAP-202",
    "amount_minor": 100000,
    "currency": "VND",
    "provider_confirmation_id": "GW-REF-559"
  }
}
~~~

`amount_minor` là số nguyên theo **đơn vị tiền nhỏ nhất** của đơn vị tiền tệ được công bố. Không dùng số thực nhị phân cho giá trị tiền. `refund_id` và `provider_confirmation_id` cần được khử lặp trong phạm vi nhà cung cấp tương ứng; `compensates_capture_id` chỉ ra khoản thu cụ thể được bù trừ.

Nếu nghĩa vụ thuộc aggregate **Invoice** còn giao dịch thực tế thuộc **Payment**, cần xác định ranh giới giao dịch và thông điệp tích hợp giữa hai nguồn. Không giả định một transaction ở event store của Payment sẽ tự cập nhật mọi read model của Invoice.

## 6. Ví dụ đầy đủ: từ phí trễ sai đến số dư đúng

Xét lại hợp đồng thuê `RENT-204`:

- Hạn trả được nhập ban đầu: 10:00, nhưng chứng từ gia hạn hợp lệ cho phép đến 11:00.
- Khách bàn giao thiết bị lúc 10:30.
- Hệ thống tính phí trễ 100.000 VND vì dùng hạn cũ.
- Sau kiểm tra, quản lý chấp nhận ngày giờ đúng và xóa nghĩa vụ phí trễ.
- Nếu phí đã được thanh toán, hệ thống phải hoàn lại số tiền tương ứng và xác nhận kết quả.

Một lịch sử ví dụ:

| Version | Event | Trạng thái nghiệp vụ diễn giải |
| ---: | --- | --- |
| 1 | **RentalStarted** | Hạn trả đang được ghi là 10:00. |
| 2 | **EquipmentDroppedOff** | Ghi nhận thực tế bàn giao lúc 10:30. |
| 3 | **LateFeeAssessed** | Hình thành khoản phải thu 100.000 VND. |
| 4 | **RentalDueDateCorrectionApproved** | Hạn trả đúng được công nhận là 11:00. |
| 5 | **LateFeeAssessmentReversed** | Đảo khoản phải thu 100.000 VND của event 3. |
| 6* | **RefundConfirmed** | Chỉ có nếu đã thu và sau đó hoàn thành hoàn tiền thật. |

*Event 6 chỉ là một nhánh tình huống. Nếu chưa thu tiền, không được tạo một sự kiện hoàn tiền hư cấu. Nếu việc hoàn được quản lý trong Payment aggregate riêng, nó sẽ có **version của luồng Payment**, không phải bắt buộc là version 6 trong Rental. Read model của Rental có thể tiếp nhận thông tin này qua integration event với quy tắc nhất quán đã được xác định.*

### Phân biệt số dư kế toán với dòng tiền

Giả sử projection có bốn đại lượng cùng loại tiền:

| Đại lượng | Cách tính | Sau đảo phí, chưa thu tiền | Sau khi đã thu 100.000 rồi hoàn 100.000 |
| --- | --- | ---: | ---: |
| Phí đã đánh giá gộp | Tổng **LateFeeAssessed** | 100.000 | 100.000 |
| Phí đã đảo | Tổng **LateFeeAssessmentReversed** | 100.000 | 100.000 |
| Phí ròng còn hiệu lực | Phí đánh giá gộp − phí đã đảo | 0 | 0 |
| Tiền ròng đã nhận | Tổng thu tiền xác nhận − tổng hoàn xác nhận | 0 | 0 |

Chỉ số “phí đã áp sai” và “số giao dịch cần bù trừ” vẫn có giá trị quản trị; nếu chỉ ghi đè phí thành 0 mà không lưu correction/reversal, hai câu hỏi này khó được trả lời tin cậy.

**Không được trộn hai trục tiền:**

- **Nghĩa vụ/phải thu** do policy quyết định; đảo phí làm thay đổi nghĩa vụ.
- **Dòng tiền thực tế** do payment provider hoặc sổ cái có thẩm quyền xác nhận; hoàn tiền làm thay đổi dòng tiền.

Trong thời gian chờ refund, hai trục có thể tạm khác nhau. Chính sự khác biệt này giúp phát hiện khoản cần đối soát.

## 7. Lược đồ quan hệ: lưu dấu vết điều chỉnh và quan hệ tham chiếu

Có thể cài đặt event store bằng PostgreSQL với khóa luồng và version cùng các trường hỗ trợ kiểm tra correction/compensation. Đây là **lược đồ minh họa**, cần điều chỉnh theo kiểu aggregate và chính sách tenant.

~~~sql
CREATE TABLE event_stream (
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    current_version  BIGINT NOT NULL DEFAULT 0
                     CHECK (current_version >= 0),
    PRIMARY KEY (tenant_id, aggregate_type, aggregate_id)
);

CREATE TABLE domain_event (
    event_id            UUID PRIMARY KEY,
    tenant_id           UUID NOT NULL,
    aggregate_type      VARCHAR(80) NOT NULL,
    aggregate_id        VARCHAR(100) NOT NULL,
    stream_version      BIGINT NOT NULL CHECK (stream_version > 0),
    event_type          VARCHAR(120) NOT NULL,
    schema_version      SMALLINT NOT NULL CHECK (schema_version > 0),
    occurred_at         TIMESTAMPTZ NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_at        TIMESTAMPTZ,
    actor_type          VARCHAR(40) NOT NULL,
    actor_id            VARCHAR(100),
    reason_code         VARCHAR(80),
    evidence_id         VARCHAR(160),
    corrects_event_id   UUID REFERENCES domain_event(event_id),
    compensates_event_id UUID REFERENCES domain_event(event_id),
    payload             JSONB NOT NULL
                        CHECK (jsonb_typeof(payload) = 'object'),
    FOREIGN KEY (tenant_id, aggregate_type, aggregate_id)
        REFERENCES event_stream(tenant_id, aggregate_type, aggregate_id),
    UNIQUE (tenant_id, aggregate_type, aggregate_id, stream_version)
);

CREATE INDEX ix_domain_event_type_recorded
    ON domain_event (event_type, recorded_at);

CREATE INDEX ix_domain_event_corrects
    ON domain_event (corrects_event_id)
    WHERE corrects_event_id IS NOT NULL;
~~~

### Từng ràng buộc bảo vệ điều gì?

- **`event_id` duy nhất**: định danh một lần ghi sự kiện, tránh hai record trùng ID.
- **`UNIQUE(tenant_id, aggregate_type, aggregate_id, stream_version)`**: bảo vệ thứ tự riêng của mỗi stream. Quy tắc tăng version liên tục vẫn phải do thao tác append thực hiện trong transaction.
- **`corrects_event_id` và `compensates_event_id`**: giúp truy vết trực tiếp sự kiện được sửa/bù trừ. Một foreign key chỉ bảo đảm event được tham chiếu có tồn tại; **chưa** chứng minh cùng tenant, đúng loại, đúng quyền hạn, đúng số tiền hay một lần đảo duy nhất.
- **`reason_code`, `evidence_id`, `actor_type`**: tạo điểm nối với chính sách và bằng chứng; hệ thống vẫn cần xác minh quyền của actor và tính hợp lệ của chứng từ.
- **`payload`**: giữ dữ liệu theo hợp đồng của từng event type/version. Ràng buộc JSON ở đây chưa kiểm tra schema cụ thể.
- **Chỉ mục**: phục vụ truy vấn theo loại/thời điểm và tìm lịch sử điều chỉnh của một event. Cần đo workload trước khi thêm quá nhiều chỉ mục làm tăng chi phí append.

Với hệ thống đa tenant, việc tham chiếu `event_id` toàn cục không tự ràng buộc cùng tenant; tầng ghi cần kiểm tra điều này hoặc thiết kế khóa tham chiếu kết hợp nếu chính sách yêu cầu. Nếu correction thuộc luồng khác và event ở hệ lưu trữ khác, có thể dùng định danh tham chiếu nghiệp vụ/correlation thay vì foreign key cục bộ.

### Một command điều chỉnh phải ghi atomically

Quy trình đề xuất:

1. Tiếp nhận command `CorrectRentalDueDate` với `idempotency_key`, chứng từ, người yêu cầu và phiên bản aggregate kỳ vọng.
2. Bắt đầu transaction; khóa stream hoặc kiểm tra phiên bản theo cơ chế optimistic concurrency.
3. Nạp state **mới nhất**; xác minh event/giá trị được điều chỉnh, quyền hạn, chứng từ và việc correction chưa được xử lý trùng.
4. Quyết định những event nào cần ghi: ví dụ **RentalDueDateCorrectionApproved** và **LateFeeAssessmentReversed**.
5. Append sự kiện với các `stream_version` liên tiếp; cập nhật `current_version`; lưu receipt chống lặp và bản ghi outbox cần thiết **trong cùng transaction**.
6. Commit; trả kết quả đã ghi. Nếu phải hoàn tiền bên ngoài, quy trình thực hiện bất đồng bộ với khóa chống lặp riêng, rồi tiếp nhận xác nhận để ghi event hoàn tiền.

Nếu một command tạo hai event, **không dùng ràng buộc duy nhất trên command ID ở từng hàng event** vì sẽ chặn hàng thứ hai. Thay vào đó dùng command receipt với một khóa yêu cầu duy nhất, lưu dải event/version đã tạo; consumer sử dụng event ID để chống xử lý lặp.

### Quyền cập nhật record không đồng nghĩa quyền append

Trong thiết kế append-only, tài khoản ứng dụng ghi event nên được cấp quyền **INSERT** qua đường ghi được kiểm soát, và hạn chế trực tiếp **UPDATE/DELETE** với event đã chấp nhận. Tuy nhiên, các quyền database đơn thuần không thể kiểm chứng tất cả bất biến; cần kết hợp transaction, quản trị quyền, log truy cập, backup/restore và chính sách xử lý dữ liệu nhạy cảm.

Nếu phải sửa hoặc xóa dữ liệu đã lưu vì lý do an toàn, pháp lý hay lỗi hệ thống, phải có một quy trình quản trị riêng kèm chứng từ, đánh giá ảnh hưởng đến replay, projection và downstream. Không tùy tiện biến trường hợp ngoại lệ hạ tầng thành một “hành động nghiệp vụ” giả.

## 8. Replay và projection: sửa state mà không sửa lịch sử

Trong event sourcing, read model có thể tính từ chuỗi event theo version:

~~~text
state = initial_state
for event in events_of_stream_ordered_by_stream_version:
    state = apply(state, upcast_if_required(event))
return state
~~~

Hàm `apply` phải **tất định**: cùng event và cùng quy tắc diễn giải cho cùng kết quả. Nó không được tự gọi cổng thanh toán, gửi email, tạo refund mới hoặc đọc thời gian hiện tại trong lúc replay. Các side effect chỉ diễn ra trong workflow có kiểm soát, khi event hợp lệ được chấp nhận hoặc một quy trình bù trừ được khởi tạo.

Ví dụ hàm projector tổng hợp phí:

~~~text
on LateFeeAssessed(event):
    assessed_minor += event.amount_minor

on LateFeeAssessmentReversed(event):
    require not already_reversed(event.reverses_event_id)
    require event.currency matches target fee
    reversed_minor += event.amount_minor
    mark target as reversed

net_fee_minor = assessed_minor - reversed_minor
~~~

Phép kiểm tra `require` ở đây cho thấy dữ liệu **phải được hợp thức hóa trước khi ghi** và projector cần cơ chế phát hiện lịch sử không nhất quán. Khi replay một lịch sử đã được chấp nhận, projector thường báo lỗi và dừng ở event bất hợp lệ để điều tra, thay vì âm thầm “sửa cho hợp lý”.

### Event đảo phí phải tham chiếu khoản phí nào?

Nếu một hợp đồng có hai lần đánh giá phí, mỗi event đảo cần chỉ đến **fee_assessment_id** hoặc **event_id** mục tiêu. Nếu chỉ ghi `LateFeeAssessmentReversed { amount: 100000 }`, hệ thống không thể luôn xác định khoản nào đã được đảo, có đảo một phần hay không, và có bị đảo lặp không.

Mô hình có thể cho phép **partial reversal** (đảo một phần), khi đó ràng buộc nên là tổng số tiền đảo cho từng khoản đánh giá không vượt số tiền đã đánh giá. Không nên ép unique một lần đảo trên target nếu nghiệp vụ cần nhiều lần điều chỉnh một phần. Với mô hình chỉ cho đảo toàn bộ đúng một lần, unique theo target có thể phù hợp.

### Xử lý event đến lặp hoặc sai thứ tự

Read model bất đồng bộ nên lưu `last_applied_version` theo stream, hoặc tập event ID đã xử lý nếu logic nhận dữ liệu đa luồng. Quy tắc cơ bản:

- Version đã áp dụng: bỏ qua hoặc đối chiếu nếu cần.
- Version tiếp theo: áp dụng event và cập nhật checkpoint trong **cùng transaction** với dữ liệu dẫn xuất.
- Version lớn hơn phiên bản kỳ vọng: tìm event còn thiếu rồi mới tiếp tục, thay vì tính sai số dư.

Các projection cần truy vấn trạng thái **đã biết ở một thời điểm** có thể tách thời điểm ghi nhận và thời điểm hiệu lực; không chỉ sort lại toàn bộ event theo `effective_at` khi replay.

## 9. Bù trừ trong quy trình phân tán: saga và trạng thái trung gian

Một nghiệp vụ gồm nhiều dịch vụ không thể được hoàn nguyên bằng một lệnh rollback của database đơn lẻ.

Ví dụ đặt phòng:

~~~mermaid
flowchart LR
    A["ReservationConfirmed"] --> B["PaymentCaptured"]
    B --> C{"Phòng vẫn được bảo đảm?"}
    C -->|"Có"| D["BookingCompleted"]
    C -->|"Không"| E["CancelReservationRequested"]
    E --> F["ReservationCancelled"]
    F --> G["RefundRequested"]
    G --> H{"Xác nhận từ cổng thanh toán"}
    H -->|"Đã hoàn"| I["RefundConfirmed"]
    H -->|"Chưa rõ / lỗi"| J["Đối soát hoặc xử lý tiếp"]
~~~

Đây chỉ là **một thứ tự bù trừ minh họa**. Tùy chính sách, việc hủy chỗ và hoàn tiền có thể diễn ra theo thứ tự khác, song mỗi bước cần điều kiện, idempotency và trạng thái chờ riêng. **ReservationCancelled** không có nghĩa đã hoàn tiền. **RefundRequested** không có nghĩa refund thành công.

Một saga hoặc process manager nên theo dõi:

| Trường | Vai trò |
| --- | --- |
| `process_id` | Định danh một tiến trình bù trừ. |
| `step_id`, `step_status` | Bước nào đang chờ, đã thành công, thất bại hoặc chưa rõ kết quả. |
| `original_action_id` | Hành động/transaction gốc cần bù trừ. |
| `compensation_request_id` | Khóa idempotency khi gọi hệ ngoài. |
| `attempt_count`, `last_error` | Phục vụ retry và giám sát; không quyết định kết quả chỉ theo số lần thử. |
| `correlation_id` | Nối event ở các dịch vụ với cùng quá trình nghiệp vụ. |

Đừng tự động lặp lại bước có **kết quả chưa rõ** nếu lặp có thể gây thu hoặc hoàn tiền lần hai. Cần hỏi nguồn có thẩm quyền qua `provider_reference`/`idempotency_key` và chỉ đánh dấu kết quả sau đối soát.

**Mục tiêu compensation là phục hồi bất biến và nghĩa vụ nghiệp vụ**, không phải bảo đảm thế giới bên ngoài quay về đúng trạng thái ban đầu. Email đã gửi, kiện hàng đã vận chuyển hoặc khoản phí ngân hàng đã phát sinh có thể cần biện pháp bổ sung và vẫn lưu dấu vết.

## 10. Sửa logic xử lý, sửa sự thật nguồn và sửa dữ liệu hỏng là ba quy trình khác nhau

Phải xác định nguyên nhân trước khi “sửa event”:

| Nguyên nhân | Hành động phù hợp | Có cần event mới không? |
| --- | --- | --- |
| **Lỗi trong phép tính projection** nhưng event nguồn đúng | Sửa mã projector, dựng lại projection, đối chiếu state. | Thường không cần event nghiệp vụ mới, vì không có sự việc nghiệp vụ mới. |
| **Thông tin nghiệp vụ đã được chấp nhận nhưng về sau được đính chính** | Ghi correction event với bằng chứng, quyền hạn và thời điểm. | Thường có, để lưu diễn tiến điều chỉnh. |
| **Quyết định phí/phân bổ cần đảo** | Ghi reversal/adjustment event; bảo vệ số tiền và target. | Có nếu đó là một thay đổi nghiệp vụ được phê duyệt. |
| **Tiền đã thu, hàng đã giao, dịch vụ ngoài đã hoàn thành** | Thực thi compensating action; ghi event khi có kết quả thực. | Có event thể hiện từng mốc cần truy vết. |
| **Record event bị hỏng do lỗi lưu trữ hoặc migration** | Quy trình khôi phục/chữa dữ liệu theo kiểm soát hạ tầng và kiểm toán. | Không nên tự tạo event nghiệp vụ giả để che dấu sai hỏng. |
| **Lệnh gửi trùng/callback trùng của cùng giao dịch** | Khử lặp theo khóa nguồn và idempotency. | Không phát thêm event thành công giống hệt nếu không có sự việc mới. |

Ví dụ projector từng tính nhầm tổng phí vì cộng cả event `LateFeeAssessmentReversed` như phí mới. Khi sửa hàm projector và rebuild, không phát một event mới `RentalFeeFixed` cho từng hợp đồng nếu bản thân event nguồn đã đúng. Làm như vậy sẽ đưa lỗi của tầng đọc vào lịch sử nghiệp vụ.

Ngược lại, nếu mức phí **thực sự được phê duyệt sai** rồi gửi cho khách, cần một thay đổi có nghĩa nghiệp vụ, ngay cả khi có thể tính lại bằng thuật toán đúng. Chính thời điểm phê duyệt/đảo quyết định có giá trị truy vết.

## 11. Thời gian, lịch sử hồi tố và báo cáo sau điều chỉnh

Khi sự kiện cũ được điều chỉnh, thường có ít nhất hai câu hỏi lịch sử:

1. **Tại thời điểm X, hệ thống biết/ghi nhận điều gì?** Chẳng hạn 11:00, hệ thống tin khách đã trả trễ.
2. **Sau khi nhận bằng chứng mới, dữ kiện nào được công nhận có hiệu lực ở thời điểm X?** Chẳng hạn hạn trả hợp lệ là 11:00, nên lần bàn giao 10:30 không trễ.

Hai kết quả có thể khác nhau mà không mâu thuẫn. Một correction event được ghi lúc 12:00 có thể điều chỉnh thông tin **có hiệu lực** từ trước đó. Vì vậy cần tách:

- **`occurred_at`**: lúc quyết định sửa/hoạt động bù trừ thực sự xảy ra theo nguồn xác nhận.
- **`recorded_at`**: lúc hệ thống lưu event.
- **`effective_at`**: lúc giá trị được sửa hoặc chính sách mới có hiệu lực, nếu khác thời điểm ghi.
- **`stream_version`**: thứ tự chấp nhận event trong aggregate; vẫn tăng theo luồng, kể cả correction hồi tố.

Nếu cần truy vấn đồng thời “sự thật có hiệu lực khi nào” và “hệ thống biết điều gì khi nào”, mô hình **bitemporal** có thể phù hợp. Chỉ có `occurred_at` và `recorded_at` chưa đủ để tự động giải quyết mọi truy vấn hồi tố; cần định nghĩa quan hệ điều chỉnh, cách tạo khoảng hiệu lực và cách chọn phiên bản dữ liệu.

### Tác động lên thống kê

Giả sử dashboard đếm số lượt trả trễ:

- **Báo cáo theo thông tin từng được ghi nhận:** tính số lượt mà hệ thống *đã đánh giá* là trễ ở thời điểm đó. Sự kiện phí trễ phiên bản 3 vẫn được tính vào chỉ số này.
- **Báo cáo theo tình trạng hiệu lực sau điều chỉnh:** loại phần phí đã đảo và căn cứ hạn trả mới. Hợp đồng không còn trễ theo chính sách được xác nhận.
- **Báo cáo chất lượng vận hành:** tính số lần phải điều chỉnh, nguyên nhân, thời gian từ phát hiện đến sửa và phần tiền cần hoàn.

Nếu báo cáo chỉ đọc trạng thái cuối mà không biết correction, nó không trả lời được chỉ số thứ nhất hoặc thứ ba. Nếu báo cáo cộng mọi `LateFeeAssessed` mà bỏ qua `LateFeeAssessmentReversed`, nó sẽ phóng đại số tiền còn phải thu.

## 12. Giới hạn bất biến: bảo mật, thời hạn lưu và kiểm chứng toàn vẹn

Event log là dữ liệu có giá trị cao nên cần được bảo vệ, nhưng **append-only không phải một giải pháp bảo mật hoàn chỉnh**. Những việc cần thiết kế:

- **Phân quyền:** ứng dụng chỉ append qua kênh được kiểm soát; vai trò đọc/ghi, quản trị và audit được phân tách theo nhu cầu.
- **Toàn vẹn:** backup có kiểm chứng, kiểm tra khôi phục, giám sát sửa đổi bất thường và đối soát với chứng từ/nguồn có thẩm quyền. Hash chain/chữ ký có thể giúp phát hiện sửa đổi nếu quản lý khóa và anchor tin cậy; chúng không tự chứng minh nội dung sự kiện là đúng.
- **Riêng tư:** hạn chế email, số điện thoại, thông tin thanh toán trong payload; ưu tiên ID và dữ liệu tham chiếu được quản lý quyền truy cập khi có thể.
- **Retention và yêu cầu xóa:** cần chính sách lưu giữ, ẩn danh, mã hóa hoặc xóa có kiểm soát tùy loại dữ liệu và quy định liên quan. Sự kiện được lưu lâu dài có thể xung đột với nghĩa vụ xóa dữ liệu nếu thiết kế từ đầu không tính đến.
- **Event schema evolution:** code mới phải đọc được event cũ theo `event_type` và `schema_version`. Không thay đổi ý nghĩa trường cũ âm thầm; kiểm thử replay dữ liệu lịch sử.
- **Giới hạn của stream:** không thể mặc định một transaction trong aggregate xử lý atomically mọi hệ thống bên ngoài. Muốn phát thông điệp đáng tin cậy, dùng transactional outbox hoặc cơ chế tương đương; consumer vẫn cần chống lặp.

Có thể lưu correction, reversal và compensation trong **bảng quan hệ** với ràng buộc tham chiếu và unique; các projection đọc nhanh có thể được hiện thực ở **document store**; các quan hệ “event nào dẫn đến event nào” có thể được chiếu sang **đồ thị**; các thống kê điều chỉnh được tổng hợp vào **kho phân tích**. Cách chọn cấu trúc vật lý phụ thuộc vào truy vấn, tính nhất quán, chi phí ghi, quyền riêng tư và khả năng vận hành, chứ không phụ thuộc tên pattern.

## 13. Bài tập thực hành: giao dịch thu phí sai và hoàn tiền

**Bối cảnh:** dịch vụ đăng ký học trực tuyến thu phí 500.000 VND cho một khóa học. Sau khi xác nhận thanh toán, phát hiện voucher hợp lệ đã được duyệt trước giao dịch nhưng chưa áp dụng; số tiền đúng là 400.000 VND. Hệ thống đã cấp quyền học và gửi hóa đơn. Cổng thanh toán cho phép hoàn một phần giao dịch.

Hãy thiết kế:

1. **Các sự việc riêng biệt:** thanh toán đã thu, voucher được xác minh, hóa đơn/giá đã được điều chỉnh, yêu cầu hoàn 100.000 VND, xác nhận hoàn tiền. Phân biệt sự kiện nội bộ và kết quả xác nhận của cổng thanh toán.
2. **Tên event:** đề xuất `PaymentCaptured`, `DiscountCorrectionApproved`, `InvoiceAdjustmentPosted`, `PartialRefundRequested`, `PartialRefundConfirmed` hoặc tên phù hợp hơn theo ranh giới miền. Mỗi tên phải có định nghĩa về thời điểm thành công.
3. **Đối tượng và khóa:** xác định `Enrollment`, `Invoice` và `Payment` có phải các aggregate độc lập hay không; thiết kế `event_id`, `aggregate_id`, `stream_version`, `provider_payment_id`, `refund_id` và correlation cho quy trình điều chỉnh.
4. **Payload:** lưu số tiền gốc, điều chỉnh, đơn vị tiền tệ, mã voucher/chính sách, căn cứ phê duyệt và tham chiếu giao dịch. Không nhúng dữ liệu cá nhân không cần thiết.
5. **Cạnh tranh và lặp:** hai nhân viên cùng phê duyệt một điều chỉnh; callback refund gửi hai lần. Nêu khóa, transaction và điều kiện để chỉ có một điều chỉnh/hoàn tiền cho đúng khoản.
6. **Projection:** tính **giá trị hóa đơn ròng**, **tiền đã thu**, **tiền đã hoàn**, **số tiền chênh lệch còn phải xử lý**; chứng minh trạng thái khi refund đang chờ và khi đã xác nhận.
7. **Báo cáo thời gian:** phân biệt báo cáo lúc hóa đơn ban đầu phát hành với báo cáo sau điều chỉnh; lưu thời gian hiệu lực của voucher và thời gian hoàn tiền thực tế.
8. **Kịch bản lỗi:** provider timeout ngay khi yêu cầu hoàn; giải thích tại sao không được tự phát `PartialRefundConfirmed` và cách đối soát trước khi retry.

**Bảng kiểm tự đánh giá:**

| Kiểm tra | Kết quả cần đạt |
| --- | --- |
| **Dấu vết** | Event thanh toán và hóa đơn đã từng được phát hành không biến mất sau điều chỉnh. |
| **Ngữ nghĩa** | Tách sửa giá/hóa đơn khỏi hoàn dòng tiền bên ngoài. |
| **Nguồn xác nhận** | Event hoàn tiền thành công chỉ phát khi có bằng chứng đáng tin cậy. |
| **Idempotency** | Retry command và callback không tạo hai lần hoàn hoặc hai lần chỉnh hóa đơn. |
| **Replay** | Dựng đúng giá trị ròng từ event, không tái gọi thanh toán hay gửi email. |
| **Thời gian** | Phân biệt ngày được duyệt, ngày có hiệu lực và ngày hệ thống ghi nhận. |
| **Nhất quán** | Mỗi aggregate bảo vệ được bất biến cục bộ; quy trình nhiều dịch vụ có cơ chế điều phối rõ. |
| **Dữ liệu** | Event có ID, version, tham chiếu, chứng từ, quyền hạn và chính sách lưu phù hợp. |

**Điểm cần nhớ:** sự kiện bất biến giúp giữ lại diễn tiến đã từng được hệ thống xác nhận; **correction** ghi nhận sự thật hoặc quyết định được sửa; **reversal/adjustment** thay đổi nghĩa vụ đang có hiệu lực; **compensating action** xử lý tác động thực tế đã xảy ra. Mô hình dữ liệu tốt cần làm rõ từng loại, lưu đủ mối liên hệ và bảo đảm cập nhật đồng thời, chống lặp, đối soát cùng quyền hạn, để trạng thái cuối đúng mà lịch sử vẫn giải thích được.
