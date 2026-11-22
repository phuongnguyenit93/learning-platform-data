# Ảnh chụp trạng thái để hỗ trợ đọc lại lịch sử dài

## 1. Bài toán: lịch sử càng dài, nạp lại trạng thái càng tốn kém

Trong mô hình **event sourcing**, trạng thái hiện tại của một đối tượng thường được dựng bằng cách đọc các sự kiện đã chấp nhận của đối tượng ấy theo đúng thứ tự rồi áp dụng một hàm chuyển trạng thái. Đối với hợp đồng thuê thiết bị, luồng sự kiện có thể bắt đầu với `RentalStarted` và tiếp tục qua hàng nghìn lần gia hạn, tính phí, thanh toán, điều chỉnh và nghiệm thu.

Nếu mỗi lần xử lý một command, hệ thống luôn đọc lại toàn bộ luồng từ sự kiện đầu tiên, chi phí sẽ tăng theo chiều dài lịch sử:

~~~text
Không có snapshot:
initial_state
  + event 1 + event 2 + ... + event 9.998 + event 9.999 + event 10.000
  = current_state@version 10.000
~~~

Điều này có thể chấp nhận được với vài chục sự kiện, nhưng dễ làm tăng độ trễ đọc, lượng I/O và số thao tác chuyển trạng thái khi mỗi aggregate có lịch sử rất dài.

**Snapshot (ảnh chụp trạng thái)** là **bản trạng thái dẫn xuất tại một phiên bản xác định của event stream**. Khi cần nạp lại trạng thái, hệ thống đọc snapshot tương thích gần nhất và chỉ replay các sự kiện phát sinh sau phiên bản đó:

~~~text
Có snapshot tại version 9.500:
snapshot(state@9.500)
  + event 9.501 + ... + event 10.000
  = current_state@version 10.000
~~~

Snapshot là một lựa chọn **tối ưu hóa hiệu năng đọc lại lịch sử**, không phải sự kiện mới và không tự tạo ra một nguồn sự thật thứ hai. Để hiểu và sử dụng đúng, phải xác định ranh giới aggregate, phiên bản stream, nội dung state, tính tương thích của định dạng, điều kiện ghi đồng thời và cách khôi phục khi snapshot không dùng được.

## 2. Phân biệt snapshot, event, projection và backup

Các thuật ngữ “ảnh chụp” và “trạng thái” dễ bị dùng lẫn trong thiết kế dữ liệu:

| Khái niệm | Dữ liệu biểu diễn | Vai trò | Có thể xây lại từ event? |
| --- | --- | --- | --- |
| **Domain event** | Một sự thật nghiệp vụ đã được chấp nhận, ví dụ `DepositCaptured`. | Nguồn sự thật trong event sourcing. | Không coi là dữ liệu dẫn xuất tùy ý; phải bảo vệ lịch sử gốc. |
| **Aggregate snapshot** | State của **một aggregate tại stream version N**. | Giảm lượng sự kiện cần replay khi nạp aggregate. | Có, nếu sự kiện lịch sử và logic diễn giải còn đầy đủ. |
| **Projection/read model** | Bảng hoặc document phục vụ truy vấn như `rental_current`. | Đọc nhanh theo nhu cầu màn hình/báo cáo. | Có, nếu nguồn event và quy tắc chiếu còn đầy đủ. |
| **Projection checkpoint** | Vị trí mà một projector đã xử lý đến. | Tiếp tục xử lý sau lỗi, tránh áp dụng lặp. | Là metadata tiến trình; cần phối hợp với trạng thái dẫn xuất để phục hồi an toàn. |
| **Database backup/snapshot** | Bản sao dữ liệu hoặc trạng thái lưu trữ ở một mốc kỹ thuật. | Khôi phục hạ tầng, bảo vệ dữ liệu trước sự cố. | Không thể thay bằng aggregate snapshot, vì mục đích và phạm vi khác nhau. |
| **CDC initial snapshot** | Các hàng hiện có được đọc để khởi tạo một luồng đồng bộ thay đổi. | Nạp dữ liệu hiện hữu cho downstream. | Không có nghĩa các sự kiện nghiệp vụ vừa xảy ra lúc tạo bản chụp. |

Một bảng `rental_current` có thể chứa đúng các trường như aggregate snapshot, nhưng vòng đời và mục đích thường khác: bảng hiện hành được cập nhật khi nhận event mới để trả lời truy vấn; snapshot được giữ tại **một version bất biến về nội dung logic** và dùng như điểm khởi đầu cho replay sau này.

Trong hệ thống chỉ lưu **state + audit log**, có thể định kỳ lưu state để sao lưu hoặc kiểm toán. Tuy nhiên, không mặc nhiên gọi đó là event-sourcing snapshot: nếu audit log không đủ nghĩa để dựng state, thì không có bảo đảm replay độc lập từ log.

## 3. Ví dụ xuyên suốt: snapshot cho hợp đồng thuê thiết bị

Xét aggregate `Rental` với mã `RENT-204`. Một lịch sử đơn giản:

| stream_version | Sự kiện | Thay đổi được chấp nhận |
| ---: | --- | --- |
| 1 | `RentalStarted` | Thuê thiết bị, hạn trả 10:00, tiền cọc 200.000 VND. |
| 2 | `DepositCaptured` | Đã thu thành công 200.000 VND. |
| 3 | `RentalDueDateExtended` | Hạn trả hợp lệ được gia hạn đến 11:00. |
| 4 | `EquipmentDroppedOff` | Khách đã bàn giao thiết bị tại kiosk. |
| 5 | `EquipmentReturnAccepted` | Nhân viên xác nhận nghiệm thu đạt. |
| 6 | `DepositRefundRequested` | Yêu cầu hoàn cọc đã được ghi; **chưa** tính là đã hoàn. |
| 7 | `DepositRefundConfirmed` | Nguồn thanh toán xác nhận đã hoàn 200.000 VND. |
| 8 | `RentalClosed` | Hợp đồng đóng khi các nghĩa vụ đã hoàn tất. |

Giả sử sau khi áp dụng event version 5, hệ thống tạo snapshot:

~~~json
{
  "snapshot_schema_version": 2,
  "reducer_version": "rental-state-v2",
  "aggregate_type": "Rental",
  "aggregate_id": "RENT-204",
  "stream_version": 5,
  "state": {
    "rental_status": "RETURN_ACCEPTED",
    "payment_status": "PAID",
    "currency": "VND",
    "deposit_captured_minor": 200000,
    "deposit_refunded_minor": 0,
    "due_at": "2026-11-20T04:00:00Z",
    "equipment_return_accepted": true
  }
}
~~~

Snapshot này **chỉ bao gồm các sự kiện 1–5** và phản ánh đúng trạng thái tại version 5. Khi nạp trạng thái ở version 8:

1. Đọc snapshot version 5, kiểm tra định dạng và nguồn.
2. Áp dụng `DepositRefundRequested` version 6; số tiền đã hoàn vẫn là 0.
3. Áp dụng `DepositRefundConfirmed` version 7; số tiền đã hoàn thành 200.000.
4. Áp dụng `RentalClosed` version 8; trạng thái hợp đồng chuyển thành `CLOSED`.

Kết quả cuối đúng như replay toàn bộ 8 event, nhưng chỉ cần áp dụng ba event sau snapshot. Nếu muốn xem **state tại version 4**, không thể dùng snapshot version 5 rồi “quay ngược” bằng cách trừ một event tùy ý; phải chọn snapshot có version **nhỏ hơn hoặc bằng 4**, hoặc replay từ đầu.

**Lưu ý về tiền:** `deposit_captured_minor` và `deposit_refunded_minor` dùng số nguyên theo quy tắc đơn vị tiền của `currency`. `DepositRefundRequested` không được cộng vào `deposit_refunded_minor` vì yêu cầu hoàn chưa chứng minh dòng tiền thực tế đã hoàn.

## 4. Những trường nào phải có trong một snapshot?

Một bản snapshot đáng tin cần trả lời “đây là trạng thái của ai, sau sự kiện nào, theo cách diễn giải nào?”. Thiết kế tối thiểu nên gồm:

| Trường | Ý nghĩa và yêu cầu |
| --- | --- |
| `tenant_id` (nếu đa tenant) | Phạm vi sở hữu và cách ly dữ liệu, nhất là khi ID trùng giữa tenant. |
| `aggregate_type`, `aggregate_id` | Định danh đúng stream. |
| `stream_version` | Version **cuối cùng đã áp dụng** để tạo state này; không phải version mới nhất tại thời điểm lưu ảnh. |
| `snapshot_schema_version` | Cách đọc/giải mã cấu trúc state đã lưu. |
| `reducer_version` hoặc `state_model_version` | Phiên bản ngữ nghĩa của logic tạo state; giúp phát hiện snapshot không còn tương thích với cách replay hiện tại. |
| `state` | Toàn bộ trạng thái cần thiết để tiếp tục áp dụng event trong phạm vi aggregate. |
| `created_at` | Khi snapshot được ghi nhận vào kho lưu trữ; dùng vận hành, không thay thế version stream. |
| `checksum`/digest (tùy chọn) | Hỗ trợ phát hiện dữ liệu hoặc biểu diễn snapshot bị hỏng; cần quy định chuẩn serialization/hàm băm. |
| `last_event_id` (tùy chọn) | Dùng đối chiếu snapshot được tạo từ event nào tại version đã nêu. |

Với snapshot cho **hàm dựng state**, dữ liệu phải đủ để những event tiếp theo được diễn giải đúng. Nếu quy tắc sau version 5 cần biết danh sách `payment_id` đã thu để ngăn trùng, snapshot chỉ lưu tổng tiền có thể không đủ; cần giữ thêm ID liên quan hoặc bảo đảm writer có cơ chế chống trùng riêng được truy xuất nhất quán. Tương tự, snapshot tổng `100` không thay được lịch sử chi tiết nếu logic kế tiếp cần xác định **khoản phí nào** đã bị đảo.

Một số trường thường bị dùng sai:

- `created_at` **không** cho biết trạng thái này bao gồm event mới nhất; snapshot version 80 có thể ghi xuống đĩa sau snapshot version 100 do tác vụ bất đồng bộ hoàn thành chậm.
- `stream_version` **không** phải `schema_version`: version 10.000 của luồng có thể chứa event schema v1, v2 và v3.
- `recorded_at` của event không phải thứ tự áp dụng; replay theo **thứ tự logic mà store cam kết trong stream**.
- `reducer_version` chỉ hữu ích khi có chính sách tương thích được định nghĩa. Đổi tên code mà không đổi ngữ nghĩa không nhất thiết làm snapshot vô hiệu; thay đổi quy tắc tính state có thể làm snapshot cũ vô hiệu dù JSON vẫn parse thành công.

## 5. Thuật toán nạp trạng thái từ snapshot và phần đuôi sự kiện

Mục tiêu là nạp state của aggregate tại **target version T** với cùng kết quả như replay từ event đầu tiên. Một thuật toán minh họa:

~~~text
load_state(stream_key, target_version=T, expected_reducer):
    snapshot = find_latest_compatible_snapshot(
        stream_key=stream_key,
        reducer=expected_reducer,
        snapshot_version <= T
    )

    if snapshot is valid:
        state = deserialize_and_validate(snapshot.state)
        v = snapshot.stream_version
    else:
        state = initial_state()
        v = 0

    events = load_events(
        stream_key=stream_key,
        version > v AND version <= T,
        order_by=stream_version
    )

    for event in events:
        require event.stream_version == v + 1
        state = apply(state, upcast_event_if_needed(event))
        v = event.stream_version

    require v == T
    return (state, version=T)
~~~

**Bốn điều kiện không thể thiếu:**

1. **Chọn snapshot đúng stream** và tương thích với logic xử lý hiện tại; không dùng snapshot của tenant hay aggregate khác.
2. **Chỉ chọn snapshot có version ≤ T.** Muốn dựng state tại version 50, snapshot version 80 là dữ liệu “đến từ tương lai”.
3. **Đọc đầy đủ event sau snapshot, theo version liên tiếp.** Không được bỏ qua version 51 rồi áp dụng 52; thiếu event phải dừng và phục hồi.
4. **Hàm `apply` tất định.** Không gọi API hoàn tiền, gửi email, đọc ngày giờ hiện tại hoặc lấy bảng giá đã thay đổi để quyết định lại lịch sử.

Nếu snapshot mới nhất không hợp lệ, có thể thử snapshot cũ hơn **cũng tương thích** hoặc replay từ đầu. Nếu phần lịch sử gốc đã bị xóa, việc “fallback replay từ đầu” có thể không khả thi; cần công bố giới hạn và thiết kế khôi phục riêng.

### Đọc trong khi stream vẫn nhận event mới

Giả sử hệ thống cần xử lý command mới và stream đang ở version 200. Trong lúc nạp snapshot 180 và event 181–200, writer khác có thể append 201. Cách làm an toàn là:

- Lấy **target version 200** từ nguồn đã commit, với hợp đồng rằng event 1–200 được append atomically theo stream.
- Đọc snapshot ≤ 200 và các event đến đúng 200, không vô tình trộn 201 vào cùng phiên dựng state.
- Khi append event mới, dùng **expected version 200** trong transaction. Nếu writer khác đã đưa stream lên 201, command gặp xung đột và phải đánh giá lại trên state mới.

Việc chỉ dùng snapshot để tăng tốc không được bỏ cơ chế concurrency control đã có. Snapshot tạo ra state dựa trên lịch sử; **expected-version check** mới bảo vệ quyết định được đưa ra khi có writer đồng thời.

## 6. Tạo snapshot đúng khi hệ thống vẫn đang ghi

**Thời điểm tạo snapshot** có thể là sau mỗi N sự kiện, khi nạp state vượt một ngưỡng thời gian, hoặc theo lịch. Bất kể trigger nào, snapshot phải biểu diễn **state chính xác tại version được gắn trên bản ghi**.

### Cách A: tạo đồng bộ cùng transaction append

Khi xử lý command, hệ thống đã có state mới và biết version cuối vừa append. Có thể tuần tự hóa việc ghi event và snapshot phù hợp trong cùng transaction của event store.

Ưu điểm: dễ gắn state và version đã xác nhận. Đánh đổi: serialization/compression snapshot có thể làm transaction lâu hơn, tăng tranh chấp và độ trễ ghi. Chỉ nên làm khi snapshot đủ nhẹ và tần suất hợp lý.

### Cách B: tạo bất đồng bộ sau commit

Một worker độc lập:

1. Nhận nhiệm vụ chụp stream `Rental/RENT-204` tại version **N = 500**.
2. Dựng state từ snapshot cũ và các event **chỉ đến N**, hoặc từ state có version N được chứng minh.
3. Serialize/kiểm tra state với version của reducer, gắn `stream_version = 500`.
4. Lưu bản chụp có khóa duy nhất theo stream, reducer và version.
5. Nếu lúc ghi xong stream đã ở version 530, bản snapshot **vẫn là version 500**. Nó có thể dùng tốt để replay tiếp 501–530.

~~~mermaid
flowchart LR
    E[("Event stream ở version 500")] --> T["Yêu cầu snapshot@500"]
    T --> R["Replay đúng tới version 500"]
    R --> S["Serialize state + reducer version"]
    S --> W[("Lưu snapshot@500")]
    E --> N["Writer append 501..530"]
    W --> L["Lần đọc sau chọn snapshot phù hợp rồi replay đuôi"]
    N --> L
~~~

**Lỗi phổ biến:** worker tải state version 500, sau khi tính toán xong lại đọc `current_version = 530` và gắn snapshot đó thành `snapshot@530`. Khi nạp, hệ thống sẽ bỏ qua event 501–530 dù state chưa áp dụng chúng. Đó là **mất dữ liệu về mặt logic** dù event store vẫn còn đầy đủ.

### Nhiều worker chụp cùng luồng

Có thể có hai worker tạo snapshot ở version 500 và 600, nhưng worker version 500 hoàn thành sau. Nếu hệ thống chỉ có một ô `latest_snapshot` và cập nhật không có điều kiện, snapshot cũ có thể ghi đè bản mới. Thiết kế lưu theo **khóa stream + version**, rồi chọn `MAX(stream_version)` thỏa điều kiện tương thích sẽ tránh chọn nhầm theo thời gian hoàn thành. Nếu chỉ lưu một snapshot, cần phép cập nhật có điều kiện “chỉ thay khi version mới lớn hơn bản hiện có”, cùng cơ chế xử lý trường hợp reducer version thay đổi.

**Snapshot là dữ liệu dẫn xuất:** có thể xóa ảnh cũ khi có chiến lược lưu phù hợp, miễn lịch sử gốc còn đủ để khôi phục và không làm hỏng quy trình đọc đang hoạt động.

## 7. Ví dụ lược đồ PostgreSQL cho event và snapshot

Thiết kế dưới đây dùng một schema chung cho nhiều loại aggregate và có khóa tenant. Phần quản lý stream giữ version cuối được chấp nhận; event store giữ lịch sử; snapshot giữ state dẫn xuất. Đây là ví dụ cấu trúc, chưa phải đầy đủ toàn bộ quy tắc nghiệp vụ và phân quyền.

~~~sql
CREATE TABLE event_stream (
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    current_version  BIGINT NOT NULL DEFAULT 0
                     CHECK (current_version >= 0),
    PRIMARY KEY (tenant_id, aggregate_type, aggregate_id)
);

CREATE TABLE event_store (
    event_id         UUID PRIMARY KEY,
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    stream_version   BIGINT NOT NULL CHECK (stream_version > 0),
    event_type       VARCHAR(100) NOT NULL,
    event_schema_version SMALLINT NOT NULL
                         CHECK (event_schema_version > 0),
    occurred_at      TIMESTAMPTZ NOT NULL,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    FOREIGN KEY (tenant_id, aggregate_type, aggregate_id)
        REFERENCES event_stream
        (tenant_id, aggregate_type, aggregate_id),
    UNIQUE (tenant_id, aggregate_type, aggregate_id, stream_version)
);

CREATE TABLE aggregate_snapshot (
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    reducer_version  VARCHAR(80) NOT NULL,
    stream_version   BIGINT NOT NULL CHECK (stream_version > 0),
    snapshot_schema_version SMALLINT NOT NULL
                            CHECK (snapshot_schema_version > 0),
    state            JSONB NOT NULL
                     CHECK (jsonb_typeof(state) = 'object'),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        tenant_id, aggregate_type, aggregate_id,
        reducer_version, stream_version
    ),
    FOREIGN KEY (tenant_id, aggregate_type, aggregate_id)
        REFERENCES event_stream
        (tenant_id, aggregate_type, aggregate_id)
);
~~~

**Ràng buộc và giới hạn của schema:**

- Khóa snapshot bảo đảm có nhiều ảnh theo version nhưng không có hai ảnh cùng **stream + reducer + version**. Thứ tự các cột khóa phù hợp với truy vấn tìm snapshot tương thích gần nhất.
- **`event_store.stream_version`** có unique per stream; việc tăng liên tục và đồng bộ với `current_version` phải do transaction append bảo vệ.
- Foreign key từ snapshot sang stream bảo đảm stream tồn tại, **chưa** chứng minh snapshot version N thực sự được dựng từ mọi event 1–N. Đó là trách nhiệm của quy trình chụp và kiểm chứng.
- Lược đồ không dùng `created_at` để quyết định ảnh nào “mới nhất về trạng thái”. Trong cùng reducer, chỉ số `stream_version` quyết định.
- Nếu state lớn hoặc chứa dữ liệu nhạy cảm, có thể cân nhắc lưu snapshot đã nén/mã hóa ở kho khác, còn bảng chỉ giữ metadata và checksum. Cần xác định cơ chế đồng bộ, quyền truy cập và xử lý file ảnh bị mất hoặc không giải mã được.
- Không mặc định thêm chỉ mục cho mọi trường trong `state JSONB`, vì mục tiêu chính của bảng này là **nạp theo stream + version**, không phải truy vấn nghiệp vụ tùy ý. Các truy vấn màn hình nên dùng read model chuyên biệt.

### Truy vấn tìm snapshot tương thích gần nhất

~~~sql
SELECT stream_version, snapshot_schema_version,
       reducer_version, state
FROM aggregate_snapshot
WHERE tenant_id = :tenant_id
  AND aggregate_type = 'Rental'
  AND aggregate_id = :rental_id
  AND reducer_version = :reducer_version
  AND stream_version <= :target_version
ORDER BY stream_version DESC
LIMIT 1;
~~~

Trình xử lý phải biết `snapshot_schema_version` nào có thể đọc và có thể thêm điều kiện lọc schema version tương thích trước khi chọn ảnh. Nếu ảnh vừa chọn bị lỗi giải mã hoặc vi phạm cấu trúc, thử ảnh tương thích ở version nhỏ hơn hoặc quay về replay từ event đầu.

Sau đó nạp phần đuôi:

~~~sql
SELECT event_id, stream_version, event_type,
       event_schema_version, payload
FROM event_store
WHERE tenant_id = :tenant_id
  AND aggregate_type = 'Rental'
  AND aggregate_id = :rental_id
  AND stream_version > :snapshot_version
  AND stream_version <= :target_version
ORDER BY stream_version;
~~~

Với luồng chưa có snapshot, đặt `:snapshot_version = 0`. Các dấu `:` biểu thị tham số do tầng truy vấn cung cấp; đây là SQL có tham số minh họa. Trong một lượt đọc nhằm dựng state, `:target_version` nên được xác định theo quy tắc nhất quán nguồn, ví dụ đọc `current_version` đã commit và không đọc vượt giá trị đó.

### Ghi snapshot từ worker

Worker dựng state tại version N, kiểm tra các event liền nhau, ghi vào `aggregate_snapshot` với `reducer_version` và `snapshot_schema_version` tương ứng. Nếu hai worker ghi cùng khóa, dùng xử lý xung đột có chủ đích: so sánh checksum/state và điều tra nếu khác biệt, thay vì cho bản ghi cuối cùng âm thầm thắng. Snapshot tạo lại bằng cùng reducer trên cùng lịch sử phải cho cùng state.

Việc tạo snapshot **không** làm tăng `event_stream.current_version`, vì đó là dữ liệu tối ưu hóa, không phải một domain event được append vào stream.

## 8. Chọn tần suất snapshot dựa trên hiệu năng và chi phí

Không có quy tắc bắt buộc “cứ 100 sự kiện phải chụp một lần”. Có thể bắt đầu bằng một ngưỡng, sau đó đo tải thực tế.

Một cách nhìn gần đúng:

~~~text
Chi phí nạp state với snapshot
    ≈ chi phí tìm snapshot
    + chi phí đọc và deserialize snapshot
    + số event đuôi × chi phí apply một event
~~~

Nếu một stream có 10.000 event và chụp mỗi 500 event, phần đuôi từ snapshot gần nhất thường có tối đa khoảng 499 event khi snapshot đã kịp tạo và mọi version đều liên tiếp. Đây **không phải bảo đảm độ trễ**: kích thước snapshot, tốc độ đọc lưu trữ, độ phức tạp apply, tốc độ tạo ảnh bất đồng bộ và mạng đều ảnh hưởng.

| Chiến lược | Phù hợp khi | Đổi lại |
| --- | --- | --- |
| **Theo số event** | Chi phí apply trung bình khá ổn định; dễ triển khai. | Một số event nặng hơn nhiều event khác. |
| **Theo thời gian** | Muốn snapshot định kỳ cho stream thường hoạt động. | Stream có rất ít event có thể bị chụp không cần thiết. |
| **Theo dung lượng/chi phí replay** | Event có kích thước và độ phức tạp rất khác nhau. | Cần đo và chính sách trigger phức tạp hơn. |
| **Theo độ trễ nạp state** | Có SLO đọc/ghi rõ, tối ưu theo kết quả thực tế. | Phải có telemetry và cơ chế điều chỉnh ngưỡng. |
| **Kết hợp ngưỡng và lịch** | Tải không đều, cần kiểm soát cả spike và thời gian kể từ ảnh cuối. | Nhiều điều kiện cần quản trị và tránh chụp lặp. |

**Càng chụp thường xuyên không nhất thiết càng nhanh**: chụp mỗi event có thể làm tăng CPU serialization, I/O, dung lượng, contention và chi phí lưu trữ. Ngược lại, snapshot quá thưa gây replay dài. Nên đo tối thiểu:

- P50/P95/P99 thời gian nạp aggregate; số event replay kể từ snapshot.
- Thời gian và tài nguyên tạo snapshot; số lần chụp thất bại.
- Kích thước state và xu hướng tăng trưởng theo version.
- Số lần đọc phải fallback vì snapshot cũ hoặc không tương thích.
- Tác động lên latency của command và chi phí vận hành event store.

Có thể chỉ snapshot những aggregate **lịch sử dài hoặc được truy cập thường xuyên**, thay vì chụp toàn bộ các stream. Một đơn hàng chỉ có 4 event có thể không cần snapshot; một hợp đồng chỉnh sửa hàng nghìn lần có thể hưởng lợi rõ rệt.

## 9. Snapshot và thay đổi schema, logic diễn giải

Snapshot chứa **state đã tính**, vì vậy có ít nhất hai trục phiên bản độc lập:

1. **Phiên bản schema của snapshot**: cách serialize và deserialize state; ví dụ từ `status` một chuỗi sang nhiều trạng thái vận hành, thanh toán.
2. **Phiên bản reducer/diễn giải**: ý nghĩa của các con số hoặc trạng thái; ví dụ cách tính khoản hoàn ròng thay đổi theo quy tắc mới.

Đừng nhầm hai trục này với `event_schema_version` của sự kiện nguồn hay `stream_version` của aggregate.

Giả sử snapshot cũ lưu:

~~~json
{
  "snapshot_schema_version": 1,
  "state": {
    "status": "CLOSED",
    "refund_amount": 200000
  }
}
~~~

Sau đó mô hình mới phân tách `rental_status`, `payment_status`, `deposit_captured_minor`, `deposit_refunded_minor`, `currency`. Có hai hướng:

- **Migrator snapshot có chứng minh tương đương:** chuyển state cũ sang schema mới nếu đủ thông tin và nghĩa của trường cũ không mơ hồ. Phải kiểm chứng việc tiếp tục replay event sau snapshot.
- **Bỏ snapshot cũ, replay event gốc:** thường đáng tin hơn nếu thay đổi logic có tác động ngữ nghĩa hoặc snapshot cũ thiếu dữ kiện. Sau replay, tạo snapshot mới theo reducer version mới.

Nếu những event đầu đã bị xóa và snapshot không đủ dữ liệu để diễn giải quy tắc mới, **không thể khẳng định rebuild đầy đủ**. Cần đánh giá thiết kế retention, lịch sử lưu trữ, quy tắc migration và giới hạn có thể kiểm chứng trước khi xóa event.

### Replay đúng kết quả cũ và replay theo quy tắc mới

Có hai nhu cầu khác nhau:

- **Tái hiện state từng được hệ thống tính ở version N**: cần logic lịch sử hoặc định nghĩa tương thích của reducer tại thời điểm đó.
- **Xây lại một projection mới theo định nghĩa hiện tại**: có thể dùng logic mới được phê duyệt, nhưng phải chỉ rõ sự thay đổi ngữ nghĩa và kiểm tra kết quả với dữ liệu nguồn.

Snapshot cũ không phải bằng chứng rằng một projection mới có cùng nghĩa. Việc đọc được JSON không chứng minh **tương thích nghiệp vụ**.

## 10. Snapshot có giới hạn gì khi cần truy vấn lịch sử?

Snapshot tại version N trả lời câu hỏi “**state sau N event là gì?**”. Nó không nhất thiết trả lời:

- Đã có bao nhiêu lần điều chỉnh phí trước N?
- Từ lúc yêu cầu hoàn đến lúc nhà thanh toán xác nhận mất bao lâu?
- Ai từng phê duyệt mỗi lần gia hạn?
- Điều gì đã khiến trạng thái thay đổi qua từng bước?
- Cần dựng lại báo cáo phân tích theo một định nghĩa mới với dữ kiện chi tiết nào?

Nếu snapshot chỉ có `current_due_at` và `current_balance`, những câu hỏi này vẫn cần **event history** hoặc một read model lịch sử được duy trì riêng. Xóa event cũ vì “đã có snapshot” có thể làm mất năng lực audit, phân tích theo thời gian và sửa logic trong tương lai.

### Trạng thái “tại một thời điểm” không đơn giản là chọn snapshot theo ngày

Muốn dựng state **theo version T**, chọn snapshot ≤ T và replay đến T. Nhưng muốn biết “**trạng thái có hiệu lực vào 10:00 ngày X**” có thể cần quy tắc về:

- `occurred_at`: lúc sự việc được xác nhận đã xảy ra.
- `recorded_at`: lúc hệ thống biết và ghi nhận.
- `effective_at`: lúc giá trị bắt đầu có hiệu lực theo nghiệp vụ.
- Event điều chỉnh hồi tố có `effective_at` cũ nhưng version mới.

Một event điều chỉnh tại version 200 có thể sửa thời hạn có hiệu lực từ phiên bản trước. Để trả lời “hệ thống đã biết gì vào lúc 10:00” và “theo thông tin hiện nay, điều gì có hiệu lực lúc 10:00”, cần mô hình thời gian và truy vấn **bitemporal** nếu bài toán yêu cầu. Snapshot@version chỉ hỗ trợ rút ngắn replay đến một mốc diễn tiến đã xác định, không tự giải quyết hai cách nhìn thời gian này.

### Snapshot của nhiều aggregate không tự nhất quán toàn cục

Nếu chụp `Order` ở version 10 và `Payment` ở version 8 vào hai thời điểm khác nhau, hai snapshot không tự tạo một “ảnh toàn hệ thống tại cùng thời điểm”. Một báo cáo nhiều dịch vụ cần điểm đồng bộ, cursor/watermark có bảo đảm hoặc phương pháp phối hợp theo nguồn. Không được dùng thời gian tạo ảnh của từng aggregate để tuyên bố có một snapshot giao dịch phân tán nhất quán.

## 11. Khôi phục khi snapshot hỏng hoặc thiếu

Snapshot là dữ liệu tối ưu hóa nên cần có phương án xử lý khi không đọc được.

~~~mermaid
flowchart TD
    A["Yêu cầu nạp state tại version T"] --> B["Tìm snapshot tương thích ≤ T"]
    B --> C{"Giải mã và kiểm chứng hợp lệ?"}
    C -->|"Có"| D["Replay event sau snapshot đến T"]
    C -->|"Không"| E["Thử snapshot cũ hơn hoặc initial state"]
    E --> D
    D --> F{"Event liền version và state hợp lệ?"}
    F -->|"Có"| G["Trả state@T"]
    F -->|"Không"| H["Dừng và báo lỗi toàn vẹn/thiếu dữ liệu"]
~~~

**Các bước kiểm chứng có ích:**

- Đúng `stream_key` (bao gồm tenant khi có), reducer và snapshot schema version tương thích.
- `snapshot.stream_version <= target_version`; không âm thầm gắn ảnh cũ thành version mới.
- State có cấu trúc hợp lệ, giá trị không mâu thuẫn các bất biến cơ bản.
- Nếu có checksum, tính lại bằng quy tắc serialization chuẩn và so sánh; checksum chỉ phát hiện sai hỏng theo giả định, không bảo đảm đúng nghiệp vụ.
- Khi replay, mọi event sau snapshot phải liên tiếp; kiểm tra kết quả với state mong đợi và đối chiếu định kỳ bằng replay toàn phần trên tập mẫu.

Một snapshot lệch số tiền nhưng JSON hợp lệ có thể gây hậu quả lớn hơn ảnh bị lỗi parse, vì nó làm kết quả sai một cách im lặng. Do đó nên có kiểm chứng theo mẫu: chọn một số stream, dựng state **từ đầu** và so sánh với kết quả **snapshot + tail** theo cùng reducer version. Đây là kiểm chứng vận hành; vòng QA học thuật chuyên sâu có thể tiến hành ở giai đoạn khác của quy trình đào tạo.

### Snapshot không thay thế backup

Nếu event store mất dữ liệu, snapshot của từng aggregate chưa chắc chứa đủ chứng cứ hoặc trình tự để phục hồi tất cả nghiệp vụ. Cần backup/restore cho **nguồn sự thật**, diễn tập khôi phục, chính sách lưu trữ và cơ chế giám sát. Nếu snapshot nằm ở kho khác, cần quản lý thêm vòng đời khóa mã hóa, khả năng truy cập và tham chiếu.

## 12. Các lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Lấy snapshot có `created_at` lớn nhất | Có thể chọn ảnh version cũ tạo muộn. | Chọn version lớn nhất **≤ target**, đúng stream và reducer tương thích. |
| Gắn snapshot state@500 thành snapshot@530 | Bỏ qua event 501–530 khi replay. | Ghi đúng version đã áp dụng vào state. |
| Giả định snapshot luôn đồng bộ với stream hiện tại | Command quyết định trên state cũ. | Replay tail tới version mục tiêu và kiểm tra expected-version khi append. |
| Dùng snapshot version 100 để dựng state@80 | Trả dữ liệu tương lai sai yêu cầu. | Chỉ chọn snapshot ≤ target, hoặc replay từ đầu. |
| Áp dụng event đuôi theo `occurred_at` | Dữ liệu đến muộn gây thứ tự sai. | Replay theo `stream_version`. |
| Snapshot bỏ mất state cần cho event kế tiếp | Replay sau snapshot khác replay toàn phần. | Định nghĩa state đầy đủ và kiểm tra bất biến theo aggregate. |
| Nâng version schema mà không kiểm tra ngữ nghĩa | State cũ được giải mã nhưng áp dụng sai quy tắc mới. | Version reducer/migrator hoặc replay từ event gốc. |
| Tạo snapshot mỗi event | Tăng chi phí ghi, CPU, dung lượng. | Chọn ngưỡng dựa vào độ trễ, kích thước và workload. |
| Xóa toàn bộ event trước snapshot | Mất lịch sử, kiểm toán và khả năng rebuild projection mới. | Giữ event theo yêu cầu hoặc có chiến lược lưu trữ được chấp thuận, nêu rõ giới hạn. |
| Coi snapshot các aggregate khác nhau là ảnh hệ thống cùng thời điểm | Báo cáo xuyên aggregate có thể bất nhất. | Dùng mô hình đồng bộ/watermark nguồn phù hợp. |
| Không có fallback khi ảnh hỏng | Một snapshot lỗi làm aggregate không nạp được. | Thử snapshot trước hoặc replay gốc; báo lỗi nếu thiếu lịch sử. |
| Dùng snapshot để gửi lại side effect khi replay | Có thể hoàn tiền/gửi email lần hai. | Hàm apply thuần, side effect tách khỏi replay. |

## 13. Bài tập: chọn vị trí snapshot và kiểm chứng replay

**Bối cảnh:** một nền tảng khóa học trực tuyến quản lý quyền truy cập theo `Enrollment`. Mỗi lần học viên đăng ký, gia hạn, tạm dừng, đổi gói hoặc khôi phục quyền học đều tạo event đã được chấp nhận. Một số enrollment có hơn 12.000 event sau nhiều năm. Khi học viên mở trang, hệ thống cần nạp trạng thái quyền học, ngày hết hạn và lịch sử thanh toán liên quan trong thời gian chấp nhận được.

### Yêu cầu thực hành

1. **Chọn stream:** định nghĩa khóa luồng của `Enrollment`, xác định khi nào quyền học thuộc một aggregate và khi nào thanh toán thuộc `Payment` riêng. Giải thích vì sao hai stream không có chung version.
2. **Xác định state snapshot:** chọn các trường cần giữ để áp dụng event tiếp theo; phân biệt thông tin dẫn xuất từ event với dữ liệu cá nhân hoặc thanh toán không cần nhúng.
3. **Tính số lượng replay:** với stream 12.340 event và snapshot tương thích tại version 12.000, phải áp dụng bao nhiêu event đuôi? Nếu cần state@11.500, có dùng được snapshot@12.000 không? Giải thích.
4. **Cạnh tranh:** worker bắt đầu chụp state@12.000, trong lúc đó 15 event mới commit. Snapshot được gắn version nào? Command mới cần kiểm tra phiên bản bằng cơ chế gì?
5. **Thiết kế schema:** đề xuất bảng `enrollment_snapshot` với ID luồng, version, reducer version, snapshot schema, state và ngày tạo; thêm khóa/unique phù hợp.
6. **Thay logic:** khi chuyển từ ngày hết hạn dạng date sang thời điểm UTC và chính sách gia hạn mới, snapshot cũ có được dùng trực tiếp không? Khi nào cần migrator, khi nào phải replay từ đầu?
7. **Sự cố:** snapshot mới nhất bị hỏng. Mô tả lộ trình phục hồi và điều kiện khiến không thể rebuild đầy đủ.
8. **Phân tích:** đội vận hành muốn biết số lần tạm dừng trong năm trước. Snapshot chỉ chứa `current_access_status` có đủ không? Đề xuất read model phù hợp.
9. **Hiệu năng:** nêu số liệu đo để quyết định chụp mỗi 100, 500 hoặc 1.000 event; giải thích vì sao không chọn dựa trên một con số cố định không có dữ liệu.

### Tự kiểm chứng

| Điều kiện | Cách xác nhận |
| --- | --- |
| Tính tương đương | Replay từ đầu và snapshot + tail cho cùng state ở cùng version/reducer. |
| Chọn ảnh đúng | Snapshot thuộc đúng stream, đúng phiên bản logic, `snapshot_version <= target_version`. |
| Không thiếu event | Tail chứa mọi version liên tiếp cho tới target. |
| Chống ghi đồng thời | Command append có expected-version hoặc khóa bảo vệ trạng thái đã đọc. |
| Có thể phục hồi | Snapshot lỗi có fallback; event gốc còn đủ hoặc giới hạn được công bố. |
| Không phát side effect | Replay không gọi API thanh toán, không gửi email hay phát command mới. |
| Thực sự cải thiện | Số event replay và độ trễ nạp state giảm theo đo đạc, trong khi chi phí tạo/lưu snapshot hợp lý. |

**Kết luận thiết kế:** snapshot là một **điểm bắt đầu đã tính sẵn** của phép replay, được gắn với stream, version, định dạng state và cách diễn giải xác định. Nó giúp hệ thống đọc nhanh những lịch sử dài, nhưng tính đúng đắn chỉ được giữ nếu snapshot phản ánh chính xác mọi event đến version của nó, phần đuôi được đọc đủ và đúng thứ tự, logic tương thích và command vẫn bảo vệ cập nhật đồng thời. Event history tiếp tục giữ vai trò nguồn sự thật; việc lưu bao nhiêu snapshot, trong mô hình quan hệ hay document, phải dựa trên nhu cầu truy vấn và dữ liệu vận hành đã đo.
