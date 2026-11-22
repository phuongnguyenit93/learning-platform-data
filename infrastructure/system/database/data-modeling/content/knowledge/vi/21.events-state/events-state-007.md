# Chiếu sự kiện thành mô hình đọc và khả năng tái tạo

## 1. Từ lịch sử sự kiện đến dữ liệu mà người dùng cần đọc

Trong một hệ thống ghi nhận sự kiện, chuỗi **OrderPlaced**, **PaymentCaptured**, **OrderCancelled**, **RefundConfirmed** giải thích những gì đã xảy ra với đơn hàng. Nhưng màn hình chăm sóc khách hàng thường chỉ cần thấy ngay **trạng thái hiện tại**, **số tiền đã thu**, **số tiền đã hoàn** và **thời điểm cập nhật gần nhất**; đội phân tích lại cần **tổng số đơn hủy theo ngày**, **thời gian hoàn tiền** hoặc **tỷ lệ hoàn sau thanh toán**.

**Projection (phép chiếu sự kiện)** là quy tắc biến một hoặc nhiều sự kiện thành cấu trúc đọc phù hợp với câu hỏi cụ thể. **Read model (mô hình đọc)** là kết quả của projection: một bảng quan hệ, document, chỉ mục tìm kiếm, dữ liệu đồ thị hoặc bảng tổng hợp phân tích. Trong hệ thống **event sourcing**, event stream là nguồn sự thật, còn các read model là dữ liệu dẫn xuất, có thể tái tạo khi dữ liệu sự kiện và quy tắc diễn giải vẫn đầy đủ.

Ví dụ với đơn hàng `ORD-842`:

| Thứ tự trong luồng | Sự kiện được chấp nhận | Thông tin quan trọng |
| ---: | --- | --- |
| 1 | `OrderPlaced` | Tổng đơn 850.000 VND; thời điểm đặt. |
| 2 | `PaymentCaptured` | Đã thu 850.000 VND từ giao dịch `PAY-41`. |
| 3 | `OrderCancelled` | Đơn được hủy trước khi giao. |
| 4 | `RefundConfirmed` | Đã hoàn 850.000 VND, có mã xác nhận từ nhà thanh toán. |

Một projection cho màn hình đơn hàng tạo ra:

~~~json
{
  "order_id": "ORD-842",
  "order_status": "CANCELLED",
  "payment_status": "REFUNDED",
  "total_minor": 850000,
  "captured_minor": 850000,
  "refunded_minor": 850000,
  "currency": "VND",
  "last_applied_version": 4
}
~~~

Một projection khác có thể tạo **dòng thời gian** bốn sự kiện cho đội hỗ trợ. Một projection thứ ba cập nhật **tổng hoàn tiền theo ngày và tiền tệ** cho bộ phận tài chính. Ba cấu trúc có thể khác nhau, nhưng đều phải có **nguồn dữ liệu, quy tắc tính và phiên bản xử lý** xác định.

**Điểm cần phân biệt:** event sourcing không yêu cầu người dùng đọc trực tiếp event log. Ngược lại, thiết kế read model tốt giúp tránh biến mọi truy vấn thành một lần replay toàn bộ lịch sử. Cũng có thể chiếu sự kiện trong hệ dùng state làm nguồn sự thật; trường hợp đó phải xác định rõ nguồn nào được ưu tiên khi trạng thái và event log không khớp.

## 2. Chọn projection từ câu hỏi nghiệp vụ, không từ cấu trúc event

Một event có thể phục vụ nhiều nhu cầu đọc. Bắt đầu từ **câu hỏi và độ trễ chấp nhận**, sau đó mới chọn bảng, khóa, chỉ mục hoặc cách cập nhật.

| Người sử dụng | Câu hỏi | Read model gợi ý | Yêu cầu nhất quán |
| --- | --- | --- | --- |
| Khách hàng | Đơn đã hủy chưa, tiền đã hoàn chưa? | `order_current` theo `order_id`. | Có thể cần thấy kết quả ngay sau command. |
| Chăm sóc khách hàng | Sự việc nào xảy ra trước, ai xác nhận? | `order_timeline` có thứ tự trong stream. | Lịch sử phải chính xác, độ trễ ngắn. |
| Kế toán | Theo ngày nghiệp vụ, đã thu/hoàn bao nhiêu tiền? | `daily_payment_summary` theo ngày, tiền tệ. | Có thể trễ có giới hạn nhưng phải đối soát. |
| Quản lý giao vận | Đơn nào chờ bàn giao quá thời hạn? | `fulfillment_queue` theo trạng thái và hạn. | Cần lọc/sắp xếp nhanh. |
| Phân tích quan hệ | Những đơn nào phụ thuộc cùng giao dịch hoặc lô giao? | Projection đồ thị quan hệ nghiệp vụ. | Đòi hỏi định danh và nguồn liên kết đáng tin. |

Một read model **không nên gom mọi nhu cầu** vào một bảng rộng chỉ vì tất cả cùng xuất phát từ event. Cấu trúc đọc tốt thường được **phi chuẩn hóa có chủ đích**, miễn có quy tắc nguồn và cách tái tạo. Ví dụ `order_current` lưu dư một số tổng để không phải JOIN khi hiển thị; `daily_payment_summary` lưu con số đã tổng hợp để tránh quét mọi giao dịch.

### Một hay nhiều stream?

- Projection **theo một aggregate** như `order_current` thường dễ bảo đảm thứ tự: `order_id + stream_version`.
- Projection **kết hợp nhiều aggregate** như tổng doanh thu phải xác định cách khử lặp từng event và quy tắc tổng hợp có giao hoán hay không.
- Projection **kết hợp nhiều dịch vụ** có thể gặp dữ liệu thiếu/đến muộn: event xác nhận thanh toán xuất hiện trước khi dịch vụ báo cáo thấy `OrderPlaced`. Cần cơ chế giữ tạm, bổ sung, đối soát và định nghĩa nhất quán rõ ràng.

## 3. Hàm chiếu phải tất định và có hợp đồng riêng

Một projector đơn giản áp dụng hàm:

~~~text
state_0 = initial_state
state_1 = apply(state_0, event_1)
state_2 = apply(state_1, event_2)
...
state_n = apply(state_(n-1), event_n)
~~~

Để **rebuild** cho cùng kết quả, hàm `apply` phải có tính **tất định**: cùng trạng thái đầu và cùng dãy sự kiện hợp lệ phải tạo cùng trạng thái cuối khi dùng cùng phiên bản quy tắc.

Các thực hành cần thiết:

1. **Chỉ lấy dữ kiện từ event hoặc dữ liệu tham chiếu có phiên bản bất biến.** Không đọc biểu phí *hiện tại* để diễn giải một hóa đơn đã lập năm trước.
2. **Không gây side effect khi replay.** Hàm `apply` không gọi API thu/hoàn tiền, gửi email, tạo đơn hàng mới hay phát integration event.
3. **Không dùng đồng hồ hiện tại làm một phần phép tính lịch sử.** Thời gian nghiệp vụ cần nằm trong event, hoặc được cấp làm tham số truy vấn/phiên bản định nghĩa.
4. **Định nghĩa rõ cách xử lý loại event chưa hỗ trợ.** Bỏ qua chỉ khi hợp đồng projection cho phép; nếu event làm thay đổi state liên quan, phải dừng và xử lý lỗi.
5. **Quản lý version.** Cùng tên event có thể có payload version khác nhau; dùng reader phiên bản tương ứng hoặc upcaster đã được kiểm chứng.
6. **Bảo vệ bất biến.** Projector phát hiện lịch sử không hợp lệ và báo lỗi; nguồn ghi event chịu trách nhiệm chính về kiểm tra nghiệp vụ trước commit.

Ví dụ logic giản lược cho `order_current`:

~~~text
apply(state, event):
  switch event.type:
    OrderPlaced:
      require state chưa tồn tại
      return OrderState(
          order_status=PLACED,
          payment_status=UNPAID,
          total_minor=event.total_minor,
          captured_minor=0,
          refunded_minor=0,
          currency=event.currency
      )

    PaymentCaptured:
      require event.currency == state.currency
      require chưa xử lý cùng payment_id
      state.captured_minor += event.amount_minor
      state.payment_status = PAID
      return state

    OrderCancelled:
      state.order_status = CANCELLED
      return state

    RefundConfirmed:
      require event.currency == state.currency
      require state.refunded_minor + event.amount_minor
              <= state.captured_minor
      require chưa xử lý cùng refund_id
      state.refunded_minor += event.amount_minor
      state.payment_status =
          (state.refunded_minor == state.captured_minor)
          ? REFUNDED : PARTIALLY_REFUNDED
      return state
~~~

Đây là **mã giả** với tập event minh họa, không phải một state machine hoàn chỉnh cho mọi đơn hàng. Nếu một đơn có nhiều lần thu, nhiều lần hoàn hoặc nhiều loại tiền, phải mô hình hóa đủ khóa giao dịch, loại tiền và các trạng thái trung gian; không dựa chỉ vào `payment_status` một giá trị. Quy tắc khử lặp `payment_id`/`refund_id` có thể được thực thi ở command writer hoặc trong projection lưu định danh đã áp dụng, thay vì giữ toàn bộ tập ID trong mọi hàng tổng hợp.

### Version của projection cũng quan trọng

Khi thay định nghĩa “doanh thu” từ **tổng tiền thu** sang **tiền thu trừ hoàn**, đó là thay đổi **ngữ nghĩa chỉ số**, không chỉ đổi SQL. Nên đặt định danh/version cho projection, ví dụ `daily_cashflow_v1` và `daily_net_cashflow_v2`, ghi quy tắc tính, phạm vi event, đơn vị và chính sách thời gian. Nếu không, một rebuild với logic mới có thể âm thầm đổi ý nghĩa số liệu đã công bố.

## 4. Mô hình vật lý: event stream, read model và checkpoint

Ví dụ PostgreSQL dưới đây minh họa một hệ lưu các domain event của **Order** và tạo projection đọc. Hệ thực tế có thể dùng event store riêng hoặc broker, nhưng các ràng buộc logic vẫn tương tự.

~~~sql
CREATE TABLE order_event (
    event_id        UUID PRIMARY KEY,
    order_id        VARCHAR(64) NOT NULL,
    stream_version  BIGINT NOT NULL CHECK (stream_version > 0),
    event_type      VARCHAR(100) NOT NULL,
    schema_version  SMALLINT NOT NULL CHECK (schema_version > 0),
    occurred_at     TIMESTAMPTZ NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload         JSONB NOT NULL
                    CHECK (jsonb_typeof(payload) = 'object'),
    UNIQUE (order_id, stream_version)
);

CREATE TABLE order_current (
    order_id              VARCHAR(64) PRIMARY KEY,
    order_status          VARCHAR(24) NOT NULL,
    payment_status        VARCHAR(24) NOT NULL,
    total_minor           BIGINT NOT NULL CHECK (total_minor >= 0),
    captured_minor        BIGINT NOT NULL DEFAULT 0
                          CHECK (captured_minor >= 0),
    refunded_minor        BIGINT NOT NULL DEFAULT 0
                          CHECK (refunded_minor >= 0),
    currency              CHAR(3) NOT NULL,
    last_applied_version  BIGINT NOT NULL
                          CHECK (last_applied_version > 0),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (refunded_minor <= captured_minor)
);

CREATE INDEX ix_order_current_status
    ON order_current (order_status, payment_status);

CREATE TABLE order_timeline (
    event_id         UUID PRIMARY KEY
                     REFERENCES order_event (event_id),
    order_id         VARCHAR(64) NOT NULL,
    stream_version   BIGINT NOT NULL,
    event_type       VARCHAR(100) NOT NULL,
    occurred_at      TIMESTAMPTZ NOT NULL,
    display_summary  TEXT NOT NULL,
    UNIQUE (order_id, stream_version)
);
~~~

**Ý nghĩa các khóa và chỉ mục:**

- `order_event.event_id` phân biệt sự kiện; `UNIQUE(order_id, stream_version)` xác định duy nhất thứ tự trong mỗi luồng, đồng thời hỗ trợ đọc theo version.
- `order_current.order_id` là khóa tra cứu một trạng thái hiện tại; `last_applied_version` là **checkpoint theo stream** của projection này.
- `order_timeline` giữ dữ liệu hiển thị mà không phải phân tích JSON mỗi lần mở màn hình; cặp `order_id + stream_version` giữ thứ tự dòng thời gian.
- Chỉ mục `ix_order_current_status` chỉ phù hợp nếu có truy vấn lọc theo hai trạng thái. Nếu thường truy vấn theo ngày và trạng thái, hãy đo workload rồi thiết kế chỉ mục cho điều kiện thực tế.
- `CHECK` về tiền chỉ bảo vệ bất biến **trên hàng projection**; nó không bảo đảm event nguồn đúng. Lớp ghi sự kiện phải kiểm tra schema, quyền hạn, tổng tiền và giao dịch trùng.

Lược đồ đơn giản này giả định `order_id` là duy nhất trong phạm vi hệ thống. Với nhiều tenant, thêm `tenant_id` vào khóa, quan hệ và bộ lọc truy vấn theo quy tắc cách ly. Các khóa ngoại từ timeline sang event phù hợp khi ở cùng database; với read store tách biệt, phải dùng định danh nguồn và cơ chế đối chiếu thích hợp.

## 5. Cập nhật projection đồng bộ hay bất đồng bộ?

Không phải mọi read model đều cần cùng mức nhất quán.

### Cập nhật đồng bộ trong transaction nguồn

Khi event store và read model nằm trong cùng database, một hệ thống có thể **append event và cập nhật projection trọng yếu trong một transaction**. Nhờ đó sau commit, trạng thái hiện hành đã phản ánh event mới.

Ưu điểm là dễ đạt *read-your-writes* khi đọc cùng nguồn nhất quán. Đổi lại, mỗi command phải chịu thời gian cập nhật các projection đồng bộ. Nếu cập nhật một báo cáo tổng hợp rất lớn trong transaction ghi đơn, hệ thống có thể tạo điểm nóng và tăng nguy cơ tranh chấp.

### Cập nhật bất đồng bộ

Một worker đọc event đã commit, rồi cập nhật read model. Mô hình này phù hợp với bảng phân tích, tìm kiếm và những góc nhìn có thể trễ. Nhưng phải định nghĩa **độ trễ có thể chấp nhận** và cách người dùng biết kết quả command:

- Trả về `event_id` và `stream_version` sau khi ghi thành công.
- Với giao diện cần cập nhật ngay, có thể hiển thị kết quả dựa trên state mà command đã chấp nhận, hoặc đọc nguồn có bảo đảm nhất quán phù hợp.
- Nếu cần chờ projection, kiểm tra `last_applied_version >= accepted_version` **cho đúng order**, và có timeout/xử lý trường hợp worker gặp sự cố.
- Không giả định mọi projection đều đạt cùng version tại một thời điểm; mỗi projection có checkpoint và độ trễ riêng.

~~~mermaid
flowchart LR
    C["Command hợp lệ"] --> E["Append event nguồn"]
    E --> S[("Event store")]
    S --> P1["Projector order_current"]
    S --> P2["Projector order_timeline"]
    S --> P3["Projector daily_payment_summary"]
    P1 --> R1[("Bảng trạng thái đơn")]
    P2 --> R2[("Dòng thời gian")]
    P3 --> R3[("Tổng hợp ngày")]
~~~

Sơ đồ minh họa ba phép chiếu độc lập. Nếu dựa vào message broker, cần bảo đảm event được truyền đáng tin cậy từ nguồn, ví dụ transactional outbox hoặc cơ chế theo log đã được thiết kế đúng. **Gửi ít nhất một lần** thường có nghĩa consumer phải chấp nhận event lặp.

## 6. Thứ tự, khử lặp và checkpoint là trách nhiệm của projector

Giả sử `order_current` của `ORD-842` đã áp dụng đến version 2. Broker có thể gửi:

~~~text
Nhận: version 2 (lặp)
Nhận: version 4 (version 3 chưa đến)
Nhận: version 3
Nhận: version 4 (lặp lại)
~~~

Một projector đúng phải xử lý:

| Event nhận được | last_applied_version | Hành động |
| --- | ---: | --- |
| 2 | 2 | Bỏ qua hoặc kiểm tra kết quả đã ghi. |
| 4 | 2 | Phát hiện thiếu version 3; tạm giữ hoặc lấy lại khoảng thiếu. |
| 3 | 2 | Áp dụng và cập nhật checkpoint thành 3. |
| 4 | 3 | Áp dụng, cập nhật checkpoint thành 4. |
| 4 lặp | 4 | Không áp dụng lại. |

Với stream có version liên tiếp, quy tắc xử lý là:

~~~text
if incoming_version <= last_applied_version:
    ignore_or_verify_duplicate()
elif incoming_version == last_applied_version + 1:
    apply_event_and_advance_checkpoint_atomically()
else:
    recover_missing_versions_before_continuing()
~~~

**Bảo đảm nguyên tử:** nếu event `PaymentCaptured` làm tăng `captured_minor` và cập nhật `last_applied_version`, hai thay đổi phải commit cùng nhau. Nếu worker chết giữa bước cộng tiền và ghi checkpoint, lần xử lý lại có thể cộng tiền lần hai. Cần transaction và/hoặc câu lệnh `UPDATE` có điều kiện trên version để tránh lỗi.

### Với nhiều stream: checkpoint theo từng luồng chưa chắc đủ

Một bảng tổng hợp theo ngày nhận sự kiện của hàng nghìn đơn. Không thể dùng một `last_applied_version = 20` chung vì mỗi order có thể có version 20 riêng. Có thể dùng **bảng dedup theo event_id** cho từng projection:

~~~sql
CREATE TABLE projection_applied_event (
    projection_name VARCHAR(100) NOT NULL,
    event_id        UUID NOT NULL,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (projection_name, event_id)
);

CREATE TABLE daily_payment_summary (
    business_day     DATE NOT NULL,
    currency         CHAR(3) NOT NULL,
    captured_minor   BIGINT NOT NULL DEFAULT 0,
    refunded_minor   BIGINT NOT NULL DEFAULT 0,
    capture_count    BIGINT NOT NULL DEFAULT 0,
    refund_count     BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (business_day, currency)
);
~~~

Một consumer có thể làm việc **trong cùng transaction của read database**:

1. `INSERT` cặp `(projection_name, event_id)` vào `projection_applied_event` bằng cơ chế chống xung đột. Nếu event đã ghi nhận, dừng xử lý.
2. Nếu vừa ghi nhận một event mới, tính phần đóng góp theo loại event và business day, rồi `INSERT ... ON CONFLICT DO UPDATE` vào tổng hợp.
3. Commit cả dấu đã xử lý và bản cập nhật số liệu. Nếu transaction rollback, dấu event cũng không được giữ.

Ví dụ sau chỉ xử lý riêng một **PaymentCaptured**, với tham số đã được kiểm tra bằng schema và policy:

~~~sql
BEGIN;

INSERT INTO projection_applied_event (projection_name, event_id)
VALUES ('daily_payment_summary_v1', :event_id)
ON CONFLICT DO NOTHING
RETURNING event_id;

-- Chỉ chạy phần cộng bên dưới khi INSERT ở trên trả về 1 hàng.
INSERT INTO daily_payment_summary
    (business_day, currency, captured_minor, capture_count)
VALUES
    (:business_day, :currency, :amount_minor, 1)
ON CONFLICT (business_day, currency)
DO UPDATE SET
    captured_minor =
        daily_payment_summary.captured_minor + EXCLUDED.captured_minor,
    capture_count =
        daily_payment_summary.capture_count + EXCLUDED.capture_count;

COMMIT;
~~~

**Lưu ý:** đoạn SQL là một chuỗi bước được ứng dụng điều phối; không được luôn chạy `INSERT ... ON CONFLICT DO UPDATE` khi bước ghi dedup trả về 0 hàng. Nếu không, event đến lặp vẫn làm tổng tăng. Phần `RefundConfirmed` được thực hiện tương tự cho `refunded_minor` và `refund_count`; số tiền ròng có thể tính bằng `captured_minor - refunded_minor`.

Dùng **khóa ngày và tiền tệ** để không cộng trực tiếp VND với USD. Nếu cần báo cáo trên nhiều loại tiền quy đổi, phải quản lý tỷ giá và thời điểm/phiên bản áp dụng như dữ kiện riêng.

### Khi phép tổng hợp không giao hoán

Cộng số tiền theo ngày thường giao hoán nếu event có đóng góp cố định và không bị tính lặp. Nhưng **trạng thái cuối**, **thời gian giữa hai mốc** hoặc **quy tắc đổi trạng thái** có thể phụ thuộc thứ tự. Đối với các phép đó, projector cần nạp event theo stream version và đối chiếu các bước còn thiếu; dedup bằng event ID **không thay thế** kiểm soát thứ tự.

## 7. Sự kiện đến muộn, điều chỉnh và dữ liệu theo thời gian

`occurred_at` là thời điểm nghiệp vụ xảy ra theo nguồn tin cậy; `recorded_at` là thời điểm hệ thống ghi nhận; `processed_at` là lúc projector xử lý. Ba thời điểm này có thể khác nhau:

| Mốc | Ví dụ |
| --- | --- |
| Thanh toán được xác nhận tại nhà cung cấp | 10:05, thuộc `occurred_at`. |
| Hệ thống nhận callback và lưu event | 10:12, thuộc `recorded_at`. |
| Báo cáo hằng ngày áp dụng event | 10:14, thuộc thời điểm xử lý projection. |

Nếu nghiệp vụ muốn báo cáo **theo thời điểm thanh toán thực tế**, nhóm dữ liệu theo `occurred_at` đã được xác nhận. Nếu đo **độ trễ đồng bộ**, dùng sự khác biệt giữa thời điểm ghi/nhận và xử lý, có xét độ tin cậy đồng hồ. Không tự thay thế `occurred_at` bằng thời điểm nhận khi thiết bị/đối tác gửi muộn.

Với ngày nghiệp vụ, chọn múi giờ có chủ đích:

~~~sql
SELECT (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS business_day
FROM order_event
WHERE event_type = 'PaymentCaptured';
~~~

Đây là một ví dụ nhóm ngày Việt Nam, không mặc định mọi nghiệp vụ đều dùng múi giờ này. Hệ thống hoạt động nhiều quốc gia có thể cần ngày theo nơi giao dịch, tenant hoặc hợp đồng, và những quy tắc đó phải được lưu/phiên bản hóa đủ để rebuild.

### Correction và reversal cần quy tắc riêng

Nếu một khoản phí hoặc số tiền đã được đánh giá rồi bị đảo, chỉ số cần quyết định rõ:

- **Gross**: tổng giá trị từng được xác nhận.
- **Adjustment/reversal**: tổng phần điều chỉnh đã được công nhận.
- **Net**: tổng sau điều chỉnh theo chính sách báo cáo.

Với `FeeAssessed` và `FeeAssessmentReversed`, projection có thể ghi tổng đánh giá và tổng đã đảo, còn `net_fee = assessed - reversed`. Nếu phép đảo liên quan một sự kiện cụ thể, event đảo cần chứa ID mục tiêu hoặc định danh nghiệp vụ tương đương, để không đảo hai lần cùng khoản. Tránh xóa âm thầm đóng góp cũ của một event khi chính nghiệp vụ yêu cầu giữ dấu vết.

Nếu chính sách phân loại một giao dịch theo **ngày có hiệu lực hồi tố**, projection cần quy định cách tái phân bổ số liệu giữa hai ngày và mức ảnh hưởng khi sự kiện đến muộn. Thời gian nguồn, thời gian ghi và thời gian hiệu lực không tự tương đương.

## 8. Rebuild: tái tạo read model từ event đã lưu

Một trong những lợi ích quan trọng của event sourcing là khả năng **xây lại read model** khi logic thay đổi hoặc khi dữ liệu dẫn xuất bị lỗi. Nhưng rebuild an toàn trong môi trường đang hoạt động cần nhiều hơn một lệnh `TRUNCATE` rồi replay.

### Điều kiện tiên quyết

- **Event history đủ và đáng tin:** các event cần thiết chưa bị mất, xóa hoặc biến đổi làm sai ý nghĩa.
- **Reader tương thích:** mã mới có thể đọc đúng `event_type + schema_version` cũ, xử lý upcaster khi cần.
- **Thứ tự được bảo đảm trong phạm vi cần thiết:** thường là theo `aggregate_id + stream_version`; nếu projection phụ thuộc nhiều stream, cần quy tắc ghép dữ liệu cụ thể.
- **Ngữ nghĩa được công bố:** projection v2 tính gì, dùng ngày nào, đơn vị nào, và khác v1 ở đâu.
- **Có đủ tài nguyên và kế hoạch vận hành:** đọc lượng event lớn, ghi bảng mới, theo kịp event trực tiếp và đối chiếu kết quả.

### Quy trình rebuild an toàn

Ví dụ cần thay đổi logic `order_current_v1` thành `order_current_v2`:

1. **Tạo read model mới riêng biệt** với schema và tên/version rõ ràng. Cho `v1` tiếp tục phục vụ người dùng.
2. **Xác lập vị trí bắt đầu và cơ chế bắt kịp event mới.** Hệ thống cần một phương tiện đọc lịch sử nhất quán và theo tiếp những event commit sau đó, ví dụ snapshot + change stream có checkpoint đáng tin, hoặc nguồn event store cung cấp cursor theo thứ tự commit.
3. **Replay lịch sử** vào `v2` với projector mới, phát hiện khoảng thiếu và bỏ qua event lặp. Lưu checkpoint đủ cho phép dừng rồi tiếp tục.
4. **Theo kịp phần cập nhật đang phát sinh**, bảo đảm không bỏ sót event xảy ra trong thời gian replay. Không dùng đơn thuần `MAX(id)` từ một sequence được cấp trước commit làm “mốc đã commit” nếu nguồn không bảo đảm tính chất đó.
5. **Đối chiếu dữ liệu v2** với sự thật nguồn bằng những kiểm tra độc lập: số stream đã xử lý, version cuối mỗi stream, tổng tiền theo tập event, mẫu đơn có hủy/hoàn/correction, số dòng bị lỗi và độ trễ.
6. **Chuyển luồng đọc sang v2** bằng một cơ chế chuyển phiên bản có kiểm soát, ví dụ view/route hoặc cấu hình được thay atomically tại nơi phục vụ đọc. Giữ khả năng quay lại v1 nếu phát hiện sai lệch.
7. **Theo dõi sau chuyển**, rồi chỉ ngừng v1 khi đã xác minh nhu cầu rollback, khả năng tái tạo và chính sách dữ liệu.

~~~mermaid
flowchart TD
    ES[("Event store đang ghi tiếp")] --> V1["Projector v1"]
    ES --> B["Replay lịch sử vào v2"]
    ES --> T["Theo dõi event mới cho v2"]
    B --> V2[("Read model v2")]
    T --> V2
    V1 --> OLD[("Read model v1 đang phục vụ")]
    V2 --> CHECK{"Đối chiếu đủ và bắt kịp?"}
    CHECK -->|"Chưa"| FIX["Điều tra lỗi / tiếp tục theo kịp"]
    CHECK -->|"Đạt"| CUT["Chuyển tuyến đọc sang v2"]
~~~

Sơ đồ nhấn mạnh việc **xây song song, kiểm chứng rồi chuyển**. Không xem một bảng vừa rebuild “đọc hết lịch sử tại thời điểm bắt đầu” là đã cập nhật với dữ liệu phát sinh sau đó.

### Vì sao chọn watermark không đơn giản?

Giả sử hai transaction cùng append event:

- Transaction A lấy ID dạng sequence 101 nhưng chưa commit.
- Transaction B lấy ID 102 và commit trước.
- Worker đọc “tất cả event có ID ≤ 102”, thấy 102 nhưng chưa thấy 101; ghi checkpoint 102.
- Transaction A commit sau. Nếu worker chỉ tiếp tục với ID > 102 thì **event 101 bị bỏ sót**.

Một giá trị sequence/identity được **cấp** trước commit không tự là thứ tự commit. Để bảo đảm rebuild không mất event, cần dùng cơ chế nguồn có hợp đồng cursor/checkpoint an toàn với giao dịch, ví dụ transaction log/CDC có vị trí commit đáng tin, hoặc phối hợp snapshot nhất quán với luồng thay đổi. Cách cụ thể phụ thuộc DB và kiến trúc truyền sự kiện.

## 9. Kiểm chứng một projection đã tái tạo

“Script rebuild chạy không lỗi” chưa đủ để kết luận dữ liệu đúng. Nên kiểm chứng theo nhiều tầng:

| Tầng kiểm chứng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Độ phủ** | Đã đọc đủ stream/event trong phạm vi chưa? | Số stream, số event nguồn và checkpoint tương ứng. |
| **Thứ tự** | Có lỗ hổng phiên bản hay duplicate chưa xử lý? | `last_applied_version` đúng với version cuối của từng order tại mốc đối chiếu. |
| **Tính số học** | Số tiền được tổng hợp đúng? | Tổng hoàn ≤ tổng thu theo ràng buộc áp dụng; đối chiếu gross/refund/net theo tiền tệ. |
| **Đúng nghiệp vụ** | Các trạng thái khó có đúng? | Hủy trước giao, hoàn một phần, nhiều capture, correction hồi tố. |
| **Tương thích** | Event lịch sử có được đọc đúng? | Kiểm thử event `v1` và `v2` với reader/upcaster phù hợp. |
| **Tính mới** | Projection đã bắt kịp nguồn? | Độ trễ và vị trí stream/cursor tại mốc chuyển đổi. |
| **Khả năng phục hồi** | Có thể dừng/tiếp tục sau lỗi? | Crash giữa transaction không gây cộng tiền lặp hoặc mất checkpoint. |

Có thể chạy **shadow projection** v2 cùng v1 trong một khoảng đủ bao phủ workload thực tế, so sánh sự khác biệt và phân loại nguyên nhân. Nếu v1 chứa bug mà v2 nhằm sửa, **không lấy “v2 giống v1” làm tiêu chí duy nhất**. Cần đối chiếu độc lập với event gốc và kết quả nghiệp vụ mong đợi.

Nếu logic v2 cố ý thay đổi KPI, so sánh cả **định nghĩa số liệu**: ví dụ `gross_captured` và `net_revenue` không thể được yêu cầu bằng nhau. Cần công bố mốc chuyển version cho dashboard và bên dùng dữ liệu.

### Snapshot không giải quyết mọi rebuild

Snapshot của aggregate tại version N hữu ích để **nạp trạng thái hiện tại nhanh**, nhưng một projection mới cần lịch sử chi tiết (ví dụ thời gian từ thanh toán đến hủy) có thể cần đọc **những event trước N**. Không thể suy ra thông tin từng mốc chỉ từ state cuối của snapshot.

Nếu hệ thống đã xóa event cũ theo retention, một số projection có thể không tái tạo đầy đủ. Khi đó phải nói rõ hạn chế, dựa vào dữ liệu được giữ có phiên bản và chính sách khôi phục thích hợp; không gọi đó là “rebuild từ đầu” nếu nguồn lịch sử không còn.

## 10. Lỗi thường gặp khi chiếu và xây lại dữ liệu

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cộng tiền mỗi khi nhận message | Retry làm tổng tăng hai lần. | Dedupe event và ghi dấu xử lý cùng transaction với cập nhật tổng. |
| Chỉ có một `last_version` chung cho mọi order | Các stream có version riêng gây mất hoặc bỏ nhầm event. | Checkpoint theo stream; hoặc cursor nguồn được cam kết rõ. |
| Áp dụng version 6 khi version 5 chưa có | State không nhất quán, có thể bỏ mất điều kiện chuyển trạng thái. | Phát hiện gap, chờ/lấy lại event, rồi áp dụng theo thứ tự. |
| Replay trực tiếp gọi API thanh toán | Có thể tạo giao dịch thực thật lần hai. | Hàm apply thuần, side effect trong workflow riêng. |
| Rebuild bằng cách xóa bảng đang phục vụ | Người dùng thấy dữ liệu rỗng hoặc một phần. | Xây bảng v2 song song, kiểm chứng và chuyển nguồn đọc. |
| Dùng timestamp hoặc ID được cấp để đo thứ tự commit | Bỏ sót event commit muộn. | Chọn cursor/change stream có bảo đảm commit đúng. |
| Tính doanh thu bằng cách cộng mọi `PaymentCaptured` mà không xét hoàn | Số liệu doanh thu ròng sai. | Định nghĩa gross/refund/net, lưu adjustment theo quy tắc. |
| Thay mã projector mà không version hóa định nghĩa KPI | Báo cáo lịch sử âm thầm đổi nghĩa. | Projection contract, version và ghi chú migration. |
| Chỉ đối chiếu v2 với projection cũ vốn có lỗi | Rebuild không được xác minh độc lập. | Đối chiếu event nguồn, mẫu nghiệp vụ và bất biến. |
| Cho rằng mọi read model cùng thời điểm là nhất quán | Người dùng thấy trạng thái và báo cáo khác nhau nhất thời. | Công bố lag, sử dụng checkpoint và mốc đối chiếu rõ. |

## 11. Chọn mô hình lưu trữ đích theo truy vấn

Một nguồn event có thể nuôi nhiều kiểu read model:

| Công nghệ/mô hình đọc | Ví dụ projection | Ưu thế | Cần cân nhắc |
| --- | --- | --- | --- |
| **Quan hệ** | `order_current`, `daily_payment_summary`. | JOIN, khóa/constraint, truy vấn lọc và tổng hợp định nghĩa rõ. | Chọn index và cập nhật row nóng khi nhiều event cùng cộng vào một tổng. |
| **Document** | `order_detail_document` chứa trạng thái và timeline ngắn. | Đọc một hồ sơ với ít round-trip. | Kích thước document, đồng thời cập nhật, giới hạn lịch sử nhúng. |
| **Search index** | Tìm đơn theo tên sản phẩm, trạng thái, đoạn mô tả. | Tìm kiếm văn bản, lọc linh hoạt. | Eventual consistency, mapping/index rebuild, dedup. |
| **Graph** | Liên kết đơn, giao dịch, tài khoản và chuỗi nguyên nhân. | Truy vấn quan hệ và đường đi. | Phải giữ định danh/link tin cậy, quản lý update/delete cạnh. |
| **Kho phân tích** | Fact event, bảng tổng hợp theo ngày/nhóm. | Quét và tổng hợp dữ liệu lớn. | Thời gian ingest, data late-arrival, định nghĩa KPI, chi phí tính lại. |

Lựa chọn không chỉ dựa vào tốc độ đọc. Cần hỏi **khi nào data có hiệu lực**, **một lỗi projector được phát hiện và sửa ra sao**, **có thể rebuild bao xa**, **quy tắc retention**, **quyền riêng tư** và **nguồn nào có thẩm quyền**. Nếu read model không thể tái tạo bởi thiếu event hoặc thiếu code tương thích, nó không còn là dữ liệu dẫn xuất hoàn toàn theo giả định ban đầu.

## 12. Bài tập thực hành: thiết kế hai projection và quy trình rebuild

**Tình huống:** nền tảng bán khóa học trực tuyến lưu các event `EnrollmentCreated`, `PaymentCaptured`, `AccessActivated`, `RefundConfirmed`, `AccessRevoked`. Có thể có thanh toán thất bại rồi thử lại, hoàn một phần, callback đến trễ và người học được cấp quyền học từ một chương trình khuyến mại không mất phí.

Nhu cầu:

- Người học muốn thấy **khóa đang có quyền học** và thời điểm kích hoạt.
- Kế toán muốn biết **tiền đã thu, hoàn và tiền ròng theo ngày**.
- Sau một lỗi tính tiền hoàn, nhóm dữ liệu muốn xây lại báo cáo mà không gián đoạn màn hình học viên.

**Yêu cầu thiết kế:**

1. **Xác định nguồn và khóa:** `Enrollment` và `Payment` có thể là hai aggregate; nêu `aggregate_id`, `event_id`, `stream_version`, `payment_id` và quan hệ giữa hai nguồn.
2. **Projection A:** thiết kế `enrollment_access_current` theo `enrollment_id`, gồm `access_status`, `activated_at`, `last_applied_version`. Phân biệt sự kiện thanh toán với sự kiện thực sự cấp quyền.
3. **Projection B:** thiết kế `daily_cashflow` với khóa `(business_day, currency)`; định nghĩa gross, refunded, net; cách dedup event và ngày dùng để nhóm.
4. **Sự kiện lặp:** giả lập `PaymentCaptured` được gửi ba lần. Nêu transaction để chỉ cộng tiền một lần.
5. **Sự kiện lệch thứ tự:** `AccessRevoked` version 5 đến trước `AccessActivated` version 4 trong cùng stream. Trình bày cách projector phát hiện và phục hồi.
6. **Rebuild v2:** đề xuất quy trình xây song song, theo kịp event mới, đối chiếu số liệu và chuyển read model mà không làm trống báo cáo đang phục vụ.
7. **Cursor an toàn:** giải thích vì sao `MAX(event_id)` hoặc một `BIGSERIAL` cấp trước commit không đương nhiên là watermark an toàn.
8. **Giới hạn:** nếu event thanh toán của năm đầu đã bị xóa, projection nào không thể dựng lại và cần giải pháp lưu trữ/thỏa thuận dữ liệu nào?
9. **Kiểm chứng:** đề xuất ít nhất ba ca đối chiếu độc lập từ event nguồn, bao gồm hoàn một phần và cấp quyền không cần thanh toán.

**Tiêu chí đạt:** các read model có khóa và quy tắc cập nhật rõ, theo dõi đủ phiên bản/ID đã xử lý, không lặp side effect, đúng thời gian nghiệp vụ, đối chiếu được với event gốc và có chiến lược rebuild khi hệ thống vẫn đang phục vụ.

**Kết luận:** chiếu sự kiện là quá trình **biến dữ liệu diễn tiến thành cấu trúc đọc theo mục đích**; khả năng tái tạo chỉ có ý nghĩa khi nguồn sự kiện đủ, quy tắc diễn giải ổn định/phiên bản hóa, thứ tự và chống lặp được xử lý đúng, checkpoint không làm mất event, và việc chuyển read model có thể kiểm chứng. Đó là cách kết nối mô hình sự kiện với thiết kế quan hệ, document, đồ thị và phân tích để dữ liệu vừa dễ đọc vừa dễ tiến hóa.
