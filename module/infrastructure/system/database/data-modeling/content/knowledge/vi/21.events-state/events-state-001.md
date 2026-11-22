# Mô hình sự kiện cho sự việc đã xảy ra thay vì chỉ lưu trạng thái cuối

## 1. Vì sao trạng thái cuối chưa đủ để mô tả nghiệp vụ?

Trong thiết kế dữ liệu, cách làm quen thuộc là lưu **trạng thái hiện tại** của một đối tượng: đơn hàng đang ở trạng thái nào, tài khoản còn bao nhiêu tiền, gói dịch vụ có hiệu lực hay không. Cách này hiệu quả khi câu hỏi chính là “bây giờ đối tượng trông như thế nào?”. Tuy nhiên, nhiều quyết định nghiệp vụ còn cần biết **điều gì đã xảy ra, theo thứ tự nào, vào thời điểm nào và vì nguyên nhân gì**.

Giả sử bảng **orders** chỉ có một bản ghi:

| order_id | order_status | payment_status | total_minor | currency |
| --- | --- | --- | ---: | --- |
| ORD-731 | CANCELLED | REFUNDED | 125000 | VND |

Bản ghi cho biết đơn đã hủy và tiền đã hoàn. Nó không trả lời chính xác: khách hủy trước hay sau khi thanh toán, đã hoàn tiền mấy lần, thời gian từ yêu cầu hủy đến khi hoàn tất là bao lâu, hoặc có thao tác bị gửi lặp không.

Thay vì chỉ ghi đè giá trị cũ, ta có thể lưu chuỗi **sự kiện đã thực sự xảy ra**:

| Thứ tự trong đơn | Sự kiện | Ý nghĩa |
| ---: | --- | --- |
| 1 | **OrderPlaced** | Đơn hàng được tạo hợp lệ. |
| 2 | **PaymentCaptured** | Khoản thanh toán được ghi nhận thành công. |
| 3 | **OrderCancelled** | Đơn hàng được hủy theo quy tắc nghiệp vụ. |
| 4 | **RefundIssued** | Khoản hoàn tiền đã được thực hiện. |

Từ chuỗi này, hệ thống có thể **suy ra trạng thái hiện tại**, đồng thời trả lời các câu hỏi về lịch sử và diễn tiến. Thứ tự sự kiện trong ví dụ là thứ tự được hệ thống chấp nhận cho **chính đơn ORD-731**, không mặc nhiên là thứ tự toàn cục giữa mọi đơn hàng.

**Ý tưởng cốt lõi:** trạng thái là một kết quả tại thời điểm quan sát; sự kiện là một sự thật nghiệp vụ đã xảy ra. Khi mô hình cần giữ lại lịch sử diễn tiến, trạng thái có thể được tạo thành một **hình chiếu (projection)** từ các sự kiện.

## 2. Phân biệt command, event và state

Ba khái niệm này liên quan nhưng có ngữ nghĩa khác nhau:

| Khái niệm | Câu hỏi mà dữ liệu trả lời | Ví dụ | Có thể bị từ chối? |
| --- | --- | --- | --- |
| **Command (lệnh/yêu cầu)** | Muốn hệ thống làm gì? | **CancelOrder** | Có. Đơn đã giao có thể không được hủy theo quy trình thông thường. |
| **Domain event (sự kiện miền nghiệp vụ)** | Điều gì đã thực sự xảy ra? | **OrderCancelled** | Bản thân sự kiện đã được chấp nhận là một sự thật; yêu cầu tạo sự kiện có thể bị từ chối. |
| **State (trạng thái)** | Hiện đối tượng đang ở tình trạng nào? | **order_status = CANCELLED** | Là kết quả được tính hoặc cập nhật sau những thay đổi hợp lệ. |

Tên sự kiện nên diễn đạt **sự việc đã hoàn tất** (thường ở thì quá khứ trong tiếng Anh), chẳng hạn **PaymentCaptured**, **ShipmentDispatched**, **SubscriptionRenewed**. Tránh đặt tên mơ hồ như **UpdateOrder**, vì nó không cho biết điều gì đã xảy ra hay có ý nghĩa gì với nghiệp vụ.

Phân biệt “người dùng bấm nút thanh toán”, “hệ thống gửi yêu cầu thu tiền”, và “đơn vị thanh toán xác nhận đã thu thành công”. Chỉ sự việc cuối mới phù hợp với sự kiện **PaymentCaptured**. Nếu cần lưu lần thanh toán thất bại, hãy định nghĩa một sự kiện riêng với ngữ nghĩa rõ ràng, ví dụ **PaymentAttemptFailed**, thay vì coi mọi yêu cầu là giao dịch thành công.

Một số thuật ngữ thiết kế thường gặp:

- **Aggregate:** ranh giới nhất quán của đối tượng nghiệp vụ, ví dụ một **Order** và các quy tắc phải đúng khi thay đổi đơn đó.
- **Event stream:** dãy sự kiện của một aggregate, được đọc theo một thứ tự xác định, thường bằng **sequence_no** tăng dần trong từng aggregate.
- **Projection/read model:** cấu trúc được tính từ sự kiện để phục vụ truy vấn, chẳng hạn bảng trạng thái đơn hiện tại hoặc báo cáo thời gian hoàn tiền.
- **Event sourcing:** cách thiết kế lấy chuỗi sự kiện đã lưu làm **nguồn sự thật chính** để khôi phục trạng thái. Một hệ thống có domain event nhưng vẫn lấy bảng trạng thái làm nguồn sự thật thì chưa nhất thiết là event sourced.

## 3. Chọn sự kiện phù hợp với bài toán

Khi đọc yêu cầu nghiệp vụ, hãy tìm những **chuyển biến có ý nghĩa** thay vì lập danh sách mọi lần gán thuộc tính. Với miền đơn hàng, ta có thể hỏi:

1. Nghiệp vụ muốn biết những mốc nào đã xảy ra? Ví dụ đặt hàng, xác nhận thu tiền, giao hàng, hủy đơn, hoàn tiền.
2. Sự kiện nào phải có bằng chứng từ hệ thống bên ngoài? Ví dụ thu tiền chỉ được coi là thành công khi có xác nhận đáng tin cậy.
3. Quy tắc nào cấm một diễn tiến? Ví dụ không thể hoàn nhiều hơn tổng tiền đã thu; không thể tạo hai lần cùng một đơn từ cùng yêu cầu.
4. Những câu hỏi nào cần truy ngược lịch sử? Ví dụ “bao nhiêu đơn bị hủy sau khi thu tiền?” hoặc “bao lâu sau khi hủy thì được hoàn?”.
5. Phạm vi nhất quán của một thao tác nằm trong một aggregate hay trải qua nhiều aggregate/dịch vụ?

Sơ đồ sau mô tả luồng logic, không quy định bắt buộc cách triển khai đồng bộ hay bất đồng bộ:

~~~mermaid
flowchart LR
    C["Command: CancelOrder"] --> V{"Kiểm tra quy tắc"}
    V -->|Không hợp lệ| R["Từ chối và trả lý do"]
    V -->|Hợp lệ| E["Ghi OrderCancelled"]
    E --> L["Event stream của Order"]
    L --> P["Projection: trạng thái hiện tại"]
    L --> A["Projection: lịch sử / phân tích"]
~~~

Trong ví dụ, **OrderCancelled** chỉ làm thay đổi trạng thái đơn hàng. Nếu đơn đã thu tiền, **payment_status** vẫn là **PAID** cho đến khi có **RefundIssued**. Không nên gộp trạng thái vận hành của đơn và trạng thái tài chính vào một trường **status** không đủ biểu đạt.

## 4. Thiết kế cấu trúc của một event

Một event cần đủ thông tin để xác định **nó là sự việc gì**, **thuộc đối tượng nào**, **xảy ra theo thứ tự nào**, **mang dữ liệu nghiệp vụ gì** và **có thể được xử lý an toàn khi lặp lại hay không**.

| Trường | Vai trò | Lưu ý thiết kế |
| --- | --- | --- |
| **event_id** | Định danh duy nhất của sự kiện. | Dùng UUID hoặc định danh có bảo đảm duy nhất; thuận tiện cho truy vết và khử lặp. |
| **aggregate_type**, **aggregate_id** | Định vị đối tượng sở hữu luồng sự kiện. | Ví dụ **Order** và **ORD-731**; cần định nghĩa ranh giới aggregate rõ. |
| **sequence_no** | Thứ tự logic trong một aggregate. | Duy nhất theo cặp (**aggregate_id**, **sequence_no**) nếu bảng chỉ lưu một loại aggregate; không suy ra thứ tự toàn hệ thống. |
| **event_type** | Loại sự việc nghiệp vụ. | Đặt tên mang nghĩa cụ thể và ổn định. |
| **event_version** | Phiên bản cấu trúc payload của loại event. | Hỗ trợ đọc sự kiện cũ khi schema tiến hóa. |
| **occurred_at** | Thời điểm sự việc thực sự xảy ra theo nguồn dữ liệu. | Có thể đến muộn hoặc chứa sai lệch đồng hồ. |
| **recorded_at** | Thời điểm hệ thống ghi nhận sự kiện. | Thường do máy chủ lưu trữ gán; khác với **occurred_at**. |
| **payload** | Dữ liệu cần thiết để hiểu hoặc xử lý sự kiện. | Quy định schema theo từng event_type/version; tránh payload tùy tiện. |
| **producer**, **idempotency_key** | Nguồn phát và khóa chống xử lý yêu cầu lặp. | Khóa idempotency có phạm vi cụ thể, ví dụ duy nhất theo producer. |
| **correlation_id**, **causation_id** | Nối sự kiện với một tiến trình và hành động gây ra nó. | Hữu ích khi cần truy dấu luồng xử lý qua nhiều dịch vụ. |

Ví dụ một sự kiện ở định dạng JSON:

~~~json
{
  "event_id": "a9f7c928-0196-40db-bbb8-f7fe87961dd7",
  "aggregate_type": "Order",
  "aggregate_id": "ORD-731",
  "sequence_no": 2,
  "event_type": "PaymentCaptured",
  "event_version": 1,
  "occurred_at": "2026-11-20T09:15:00Z",
  "recorded_at": "2026-11-20T09:15:02Z",
  "producer": "payment-service",
  "idempotency_key": "capture-PAY-904",
  "correlation_id": "92ed0fd4-9729-4a3e-8b1e-d3c6ae9021ca",
  "causation_id": "719f6535-0b65-4097-a64f-324fc8803acf",
  "payload": {
    "payment_id": "PAY-904",
    "amount_minor": 125000,
    "currency": "VND",
    "provider_reference": "PROVIDER-522"
  }
}
~~~

Ở đây **amount_minor** là số nguyên theo đơn vị tiền nhỏ nhất đã được quy ước cùng mã tiền tệ, tránh sai số của số thực nhị phân. Với hệ thống hỗ trợ nhiều loại tiền, phải xác định rõ cách đổi đơn vị theo từng mã tiền tệ. Các ID và thời gian trong ví dụ chỉ là dữ liệu minh họa.

**Hai loại thời gian cần giữ tách biệt.** Một xác nhận thanh toán có thể xảy ra lúc 09:15 nhưng được tiếp nhận lúc 09:17 do mạng chậm. Nếu báo cáo tính theo thời điểm nghiệp vụ xảy ra, dùng **occurred_at** theo quy tắc nguồn tin cậy; nếu báo cáo độ trễ đồng bộ, dùng chênh lệch giữa **recorded_at** và **occurred_at** với sự thận trọng về đồng hồ. Không dùng thời gian để thay thế thứ tự logic trong event stream.

## 5. Từ event đến trạng thái: quy tắc áp dụng sự kiện

Trạng thái hiện tại là kết quả của một hàm áp dụng lần lượt các sự kiện theo thứ tự xác định:

~~~text
state = initial_state
for event in events_of_order_sorted_by_sequence_no:
    state = apply(state, interpret_event_version(event))
return state
~~~

Với ví dụ ORD-731, một mô hình trạng thái có thể gồm **order_status**, **payment_status**, **total_minor**, **currency**, **captured_minor** và **refunded_minor**. Diễn tiến minh họa:

| Sự kiện | order_status | payment_status | captured_minor | refunded_minor |
| --- | --- | --- | ---: | ---: |
| OrderPlaced | PLACED | UNPAID | 0 | 0 |
| PaymentCaptured | PLACED | PAID | 125000 | 0 |
| OrderCancelled | CANCELLED | PAID | 125000 | 0 |
| RefundIssued | CANCELLED | REFUNDED | 125000 | 125000 |

Hàm **apply** phải có ngữ nghĩa xác định: cùng một trạng thái khởi đầu và cùng một dãy sự kiện hợp lệ phải sinh ra cùng kết quả. Khi tái phát (replay), tránh phụ thuộc vào “thời gian hiện tại”, gọi API bên ngoài hoặc tạo số ngẫu nhiên không nằm trong dữ liệu sự kiện. Nếu một giá trị quyết định trạng thái, sự kiện hoặc dữ liệu tham chiếu được phiên bản hóa phải chứa đủ thông tin để tái tạo nó.

**Kiểm tra bất biến trước khi chấp nhận event:**

| Bất biến | Ví dụ cách thực thi |
| --- | --- |
| Một đơn chỉ được khởi tạo một lần. | Từ chối **OrderPlaced** thứ hai trên cùng aggregate. |
| Không ghi nhận trùng một lần thu tiền. | Kiểm tra **payment_id** và **idempotency_key** trong phạm vi phù hợp. |
| Số tiền đã hoàn không vượt số tiền đã thu. | Tổng **refunded_minor** sau sự kiện phải nhỏ hơn hoặc bằng **captured_minor**. |
| Không chuyển trạng thái trái quy trình. | Sau khi đã giao hàng, yêu cầu hủy có thể phải chuyển thành quy trình trả hàng. |
| Phiên bản diễn tiến không bị ghi đè bởi cập nhật đồng thời. | Dùng khóa dòng hoặc kiểm soát phiên bản lạc quan trên aggregate. |

Event log tự nó **không bảo đảm** các bất biến này. Hệ thống nhận command phải kiểm tra điều kiện nghiệp vụ và ghi sự kiện trong một giao dịch có kiểm soát cạnh tranh. Với quy tắc trải rộng nhiều aggregate hoặc dịch vụ, cần thiết kế phối hợp quy trình, bù trừ và điểm nhất quán thích hợp; không giả định một giao dịch cục bộ bảo đảm mọi hệ thống đều đồng bộ.

## 6. Ánh xạ thành lược đồ quan hệ

Sự kiện là một kiểu mô hình logic; không bắt buộc phải dùng một cơ sở dữ liệu riêng. Trong PostgreSQL, có thể lưu event trong bảng quan hệ với payload JSONB. Dưới đây là thiết kế minh họa cho **một loại aggregate Order**, kết hợp cột cố định có ràng buộc chặt với payload linh hoạt theo loại event.

~~~sql
CREATE TABLE order_stream (
    order_id       VARCHAR(64) PRIMARY KEY,
    last_sequence  BIGINT NOT NULL DEFAULT 0
                   CHECK (last_sequence >= 0)
);

CREATE TABLE order_event (
    event_id         UUID PRIMARY KEY,
    order_id         VARCHAR(64) NOT NULL
                     REFERENCES order_stream(order_id),
    sequence_no      BIGINT NOT NULL CHECK (sequence_no > 0),
    event_type       VARCHAR(80) NOT NULL,
    event_version    SMALLINT NOT NULL CHECK (event_version > 0),
    occurred_at      TIMESTAMPTZ NOT NULL,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    producer         VARCHAR(80) NOT NULL,
    idempotency_key  VARCHAR(160),
    correlation_id   UUID,
    causation_id     UUID,
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    UNIQUE (order_id, sequence_no)
);

CREATE UNIQUE INDEX ux_order_event_idempotency
    ON order_event (producer, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX ix_order_event_type_occurred
    ON order_event (event_type, occurred_at);
~~~

**Vai trò của khóa và chỉ mục:**

- **event_id** bảo đảm mỗi event có một định danh riêng; **UNIQUE(order_id, sequence_no)** chặn hai sự kiện cùng vị trí trong một luồng.
- **order_stream.last_sequence** có thể được khóa khi thêm sự kiện để tuần tự hóa việc cập nhật cùng một đơn. Nếu dùng cập nhật phiên bản lạc quan, thao tác ghi phải chỉ thành công khi phiên bản kỳ vọng còn đúng.
- Chỉ mục **(producer, idempotency_key)** ngăn một yêu cầu có cùng khóa được ghi hai lần; ứng dụng phải trả kết quả cũ hoặc xử lý xung đột đúng cách. Khóa này cần được gắn với nội dung command ổn định, tránh dùng chung cho hai yêu cầu khác nhau.
- Chỉ mục **(event_type, occurred_at)** chỉ hữu ích khi truy vấn theo loại sự kiện và khoảng thời gian đủ thường xuyên. Hãy kiểm chứng bằng truy vấn thực tế, lượng dữ liệu và kế hoạch thực thi trước khi thêm nhiều chỉ mục.
- **CHECK** trên JSONB chỉ xác nhận payload là đối tượng JSON; nó **chưa** kiểm tra cấu trúc theo **event_type** và **event_version**. Cần thêm kiểm tra schema ở tầng ứng dụng hoặc cơ chế kiểm tra tương đương.

Một giao dịch ghi sự kiện có thể thực hiện theo trình tự:

1. Bắt đầu transaction; bảo đảm tồn tại dòng **order_stream** của đơn, sau đó khóa dòng đó bằng **SELECT ... FOR UPDATE**.
2. Kiểm tra idempotency; đọc trạng thái hoặc các sự kiện cần thiết và đánh giá quy tắc của command.
3. Nếu hợp lệ, thêm event với **sequence_no = last_sequence + 1**; cập nhật **last_sequence** tương ứng.
4. Nếu cập nhật đồng bộ projection hoặc outbox cùng cơ sở dữ liệu thì thực hiện ngay trong transaction; **COMMIT** khi mọi ghi cần thiết thành công. Nếu xảy ra lỗi, **ROLLBACK** toàn bộ.

Khóa dòng tồn tại giúp tránh hai command cùng ghi vào một vị trí. Với đơn mới, thao tác tạo dòng **order_stream** cần được bảo vệ bằng khóa chính và xử lý xung đột khi tạo đồng thời. Khi nhận lại command có cùng idempotency key, phải đọc kết quả trước đó thay vì tăng sequence và tạo event mới.

Để truy vấn nhanh trạng thái hiện hành, có thể lưu thêm projection:

~~~sql
CREATE TABLE order_current (
    order_id        VARCHAR(64) PRIMARY KEY,
    order_status    VARCHAR(24) NOT NULL,
    payment_status  VARCHAR(24) NOT NULL,
    total_minor     BIGINT NOT NULL CHECK (total_minor >= 0),
    currency        CHAR(3) NOT NULL,
    captured_minor  BIGINT NOT NULL DEFAULT 0
                    CHECK (captured_minor >= 0),
    refunded_minor  BIGINT NOT NULL DEFAULT 0
                    CHECK (refunded_minor >= 0),
    last_sequence   BIGINT NOT NULL CHECK (last_sequence > 0),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (refunded_minor <= captured_minor)
);
~~~

Đây là **bảng dẫn xuất**, không phải một nguồn sự thật độc lập trong thiết kế event sourcing. Nếu nghiệp vụ chỉ cần trạng thái hiện hành, có thể dùng bảng trạng thái làm nguồn sự thật và chỉ lưu thêm event chọn lọc cho lịch sử. Quyết định phụ thuộc vào nhu cầu kiểm toán, truy vết, tái dựng và mức phức tạp vận hành chấp nhận được.

## 7. Truy vấn lịch sử và dựng lại read model

Với dữ liệu sự kiện, câu hỏi “đơn nào bị hủy **sau khi** đã thu tiền?” trở thành phép so sánh thứ tự:

~~~sql
SELECT DISTINCT c.order_id
FROM order_event AS c
JOIN order_event AS p
  ON p.order_id = c.order_id
WHERE c.event_type = 'OrderCancelled'
  AND p.event_type = 'PaymentCaptured'
  AND p.sequence_no < c.sequence_no;
~~~

Truy vấn minh họa giả định các event của đơn đều nằm trên một stream và **sequence_no** thể hiện thứ tự nghiệp vụ đã chấp nhận. Nó trả lời câu hỏi “đã từng có một lần thu tiền trước một lần hủy”, **không** tự chứng minh số dư còn phải hoàn hay tính hợp lệ của mọi diễn tiến. Những kết luận đó cần quy tắc và event tương ứng.

Để dựng projection từ đầu, đọc từng stream theo **sequence_no**, chuyển đổi phiên bản event nếu cần và áp dụng hàm **apply**. Có thể tạo nhiều projection từ cùng nguồn: bảng trạng thái hiện tại để hiển thị, bảng thời gian xử lý theo các giai đoạn, hoặc bảng phân tích tỷ lệ hủy sau thanh toán.

Khi projection được cập nhật bất đồng bộ, có ba tình huống cần xử lý tường minh:

- **Event lặp lại:** nếu **sequence_no** đã áp dụng, bỏ qua hoặc xác nhận kết quả cũ; không cộng tiền hai lần.
- **Event bị thiếu hoặc đến lệch thứ tự:** nếu sự kiện tiếp theo có **sequence_no** lớn hơn **last_sequence + 1**, tạm dừng stream đó và lấy lại khoảng thiếu trước khi áp dụng.
- **Projection chậm:** người đọc có thể thấy trạng thái cũ trong một khoảng thời gian. Khi nghiệp vụ yêu cầu phản hồi ngay sau command, có thể cập nhật projection cùng transaction hoặc đọc từ nguồn có bảo đảm nhất quán phù hợp.

Với stream dài, **snapshot** lưu trạng thái tại một sequence xác định để replay từ mốc gần hơn. Snapshot là dữ liệu dẫn xuất có thể xây lại; nó không thay thế event và không nên trở thành nơi che giấu thiếu sót trong event history.

## 8. Những vấn đề khó khi đưa vào hệ thống thật

### Cập nhật đồng thời và xử lý lặp

Hai tác vụ có thể cùng đọc trạng thái “chưa hủy” rồi đều yêu cầu hủy. Nếu cả hai tự chọn cùng **sequence_no**, một thao tác phải bị chặn và được kiểm tra lại; nếu không, sẽ có lịch sử sai. Khóa aggregate, so sánh phiên bản kỳ vọng và ràng buộc duy nhất là những cơ chế thường dùng. Chống lặp cần có ở cả **đầu vào command** lẫn **bên tiêu thụ event**, vì nhiều hệ thống truyền thông điệp theo cơ chế ít nhất một lần (*at least once*).

### Ghi dữ liệu và phát thông điệp

Nếu lưu event vào cơ sở dữ liệu rồi phát trực tiếp lên broker, hệ thống có thể lỗi giữa hai bước: đã ghi nhưng chưa phát, hoặc phát nhưng giao dịch ghi bị hủy. **Transactional outbox** lưu bản ghi cần phát trong **cùng giao dịch** với event hoặc thay đổi nguồn; một bộ phát riêng chuyển thông điệp đi và có thể thử lại. Bên nhận vẫn cần xử lý idempotent. Outbox giải quyết bài toán giao tin đáng tin cậy; nó không tự biến một hệ thống dùng bảng trạng thái thành event sourcing.

### Thay đổi schema sự kiện

Event đã ghi có thể tồn tại lâu hơn phiên bản mã hiện tại. Khi đổi cấu trúc **PaymentCaptured** từ phiên bản 1 sang 2, hãy giữ **event_version**, định nghĩa quy tắc đọc bản cũ (ví dụ **upcaster** chuyển biểu diễn cũ sang dạng chuẩn trong bộ nhớ) và kiểm tra replay trên dữ liệu cũ. Không âm thầm đổi ý nghĩa của cùng một tên sự kiện; nếu ý nghĩa nghiệp vụ thay đổi thực sự, cân nhắc loại event mới.

### Sự kiện đến muộn và sửa sai lịch sử

Một sự kiện từ hệ thống bên ngoài có thể có **occurred_at** cũ nhưng được ghi nhận sau các sự kiện khác. Hệ thống phải chỉ rõ liệu nó thay đổi trạng thái theo thứ tự **ghi nhận vào stream**, hay cần một quy trình điều chỉnh nghiệp vụ có chủ đích. Không đơn giản sắp xếp lại các event đã xác nhận bằng timestamp. Khi đã ghi nhầm một sự kiện, thường tạo sự kiện **điều chỉnh/bù trừ** mang ý nghĩa nghiệp vụ, thay vì sửa thầm payload cũ; ngoại lệ về sửa/xóa dữ liệu phải theo chính sách và yêu cầu pháp lý.

### Lưu trữ, quyền riêng tư và vận hành

Lưu lịch sử tăng dung lượng, chi phí chỉ mục, độ khó phục hồi và công việc giám sát projection. Hạn chế dữ liệu cá nhân trong payload; cân nhắc tham chiếu tới nơi lưu dữ liệu nhạy cảm có chính sách xóa và ẩn danh riêng. “Append-only” là nguyên tắc thiết kế để không ghi đè sự thật nghiệp vụ, **không phải** lý do để bỏ qua thời hạn lưu trữ, yêu cầu xóa dữ liệu hoặc quy định bảo mật. Bảo vệ quyền ghi để tránh UPDATE/DELETE tùy tiện, kiểm soát truy cập và quy trình xử lý thay đổi theo quy định.

## 9. So sánh các lựa chọn mô hình hóa lịch sử

| Phương án | Nguồn sự thật | Phù hợp khi | Đổi lại |
| --- | --- | --- | --- |
| **Chỉ lưu trạng thái hiện tại** | Bản ghi state mới nhất. | Chủ yếu cần CRUD và truy vấn hiện hành. | Mất diễn tiến nếu không có nguồn lịch sử khác. |
| **State + nhật ký nghiệp vụ chọn lọc** | State vẫn là nguồn sự thật. | Cần tra cứu một số mốc lịch sử, không cần dựng lại toàn bộ state. | Phải xác định rõ nhật ký bao phủ những trường hợp nào và bảo đảm ghi nhất quán. |
| **Event sourcing + projections** | Event stream là nguồn sự thật. | Lịch sử diễn tiến, replay, phân tích nguyên nhân và nhiều góc nhìn dữ liệu là yêu cầu trọng tâm. | Tăng phức tạp về schema evolution, phiên bản, đồng bộ, khử lặp và vận hành. |

Đừng đồng nhất các khái niệm thường xuất hiện cùng nhau:

- **Audit log** thường ghi ai thao tác, thời điểm và giá trị trước/sau để kiểm tra thay đổi; không nhất thiết đủ thông tin để dựng lại state một cách có ngữ nghĩa.
- **Change Data Capture (CDC)** ghi nhận thay đổi ở mức hàng/cột của database; một lần cập nhật cột **status** không tự cho biết lý do nghiệp vụ tương đương **OrderCancelled**.
- **Integration event** là hợp đồng thông tin công bố cho hệ thống khác; có thể là bản đã chọn lọc hoặc chuyển đổi từ domain event, và cần quản lý tương thích riêng.
- **CQRS** tách cách ghi và cách đọc; có thể dùng với hoặc không dùng event sourcing. **Kafka** hay message broker có thể truyền sự kiện, nhưng chỉ dùng broker không mặc nhiên tạo ra một event store đủ khả năng replay lâu dài.

Mô hình sự kiện cũng không đồng nghĩa một loại database cụ thể. Có thể lưu stream trong bảng quan hệ, document có mảng/sự kiện riêng hoặc kho lưu trữ chuyên dụng; dữ liệu sau đó có thể được chiếu sang **đồ thị** để xem quan hệ nhân quả hoặc sang **kho phân tích** để tính chỉ số theo thời gian. Hãy chọn cấu trúc vật lý theo yêu cầu nhất quán, truy vấn, dung lượng, thời hạn lưu và khả năng vận hành.

## 10. Bài tập thiết kế và cách tự kiểm chứng

**Tình huống:** một hệ thống cho thuê thiết bị hiện chỉ lưu **rental_status = CLOSED**. Bộ phận vận hành muốn biết đơn nào đóng sau khi khách trả trễ, nhân viên nào xác nhận nhận lại thiết bị và bao lâu sau đó mới hoàn tiền đặt cọc.

Hãy thử thiết kế:

1. Các sự kiện diễn đạt hành động đã hoàn tất, chẳng hạn **RentalStarted**, **ReturnDueDateChanged**, **EquipmentReturned**, **LateFeeAssessed**, **DepositRefunded**. Phân biệt việc “khách gửi yêu cầu trả” với “thiết bị đã được nhân viên xác nhận nhận lại”.
2. Một stream trên aggregate **Rental** với thứ tự logic và định danh chống lặp. Ghi **occurred_at** và **recorded_at**, kèm actor phù hợp cho các xác nhận nghiệp vụ.
3. Projection hiện hành có trạng thái thuê, thời hạn trả, thời điểm nhận thực tế và số tiền cọc đã hoàn; projection phân tích đo độ trễ giữa **EquipmentReturned** và **DepositRefunded**.
4. Các bất biến: không hoàn quá tiền cọc còn lại, không xác nhận cùng lần trả hai lần, không đóng hợp đồng khi còn bước bắt buộc chưa hoàn tất.

Một mô hình được coi là kiểm chứng tốt khi có thể thực hiện các phép thử sau:

- **Replay:** từ cùng lịch sử sự kiện và cùng phiên bản diễn giải, dựng lại đúng trạng thái được kỳ vọng.
- **Khử lặp:** gửi lại cùng command hoặc cùng event không làm tiền hay số lượng thay đổi thêm.
- **Cạnh tranh:** hai command cùng sửa một aggregate không tạo số thứ tự trùng hoặc làm mất sự kiện.
- **Tính hợp lệ:** các chuyển đổi trái quy tắc bị từ chối trước khi ghi nhận như sự kiện đã thành công.
- **Tương thích:** mã mới vẫn đọc được event phiên bản cũ; rebuild projection cho kết quả thống nhất.
- **Truy vấn:** những câu hỏi lịch sử đã nêu được trả lời từ dữ liệu thực tế, với thứ tự và thời điểm được định nghĩa rõ.

**Kết luận thiết kế:** chỉ lưu trạng thái cuối là đủ cho nhiều nghiệp vụ đơn giản. Khi bản thân **diễn tiến** mang giá trị nghiệp vụ, hãy mô hình hóa những sự việc đã xảy ra thành event có ý nghĩa, ràng buộc và thứ tự rõ ràng. Từ đó lựa chọn mức độ lưu lịch sử, cơ chế projection và mô hình vật lý phù hợp, thay vì mặc định mọi hệ thống đều phải áp dụng event sourcing.
