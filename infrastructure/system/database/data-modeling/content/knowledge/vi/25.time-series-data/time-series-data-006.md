# Dữ liệu đến trễ, trùng thời điểm và điều chỉnh phép đo

## 1. Vì sao dữ liệu chuỗi thời gian không luôn đến theo thứ tự?

Trong hệ thống giám sát kho lạnh, một cảm biến đo nhiệt độ tại **10:01:00** nhưng mất kết nối; đến **10:36:00** thiết bị mới gửi dữ liệu về máy chủ. Một gateway khác có thể gửi lại cùng bản đo ba lần sau timeout. Sau khi hiệu chuẩn, kỹ thuật viên còn xác nhận rằng giá trị cũ **7,0 °C** phải được điều chỉnh thành **6,5 °C**. Nếu bảng chỉ có hai cột `measured_at` và `value`, ứng dụng rất dễ:

- Bỏ bản đo đến trễ vì nó “cũ hơn bản ghi gần nhất”.
- Gộp nhầm hai mẫu **cùng timestamp** dù chúng thực sự là hai phép đo khác nhau.
- Cộng một mẫu nhiều lần vào trung bình/tổng khi nhận message lặp.
- Ghi đè correction bằng một message cũ đến sau.
- Giữ bảng tổng hợp 15 phút sai dù bảng đo chi tiết đã được sửa.
- Không giải thích được **hệ thống đã biết điều gì trước khi hiệu chuẩn**.

Bài toán là **mô hình hóa danh tính bản đo, thứ tự phiên bản và các chiều thời gian** trước khi chọn database hoặc viết phép tổng hợp. Dữ liệu chuỗi thời gian có thể nằm trong bảng quan hệ, hệ quản trị time-series, document hay kho phân tích; dù lưu ở đâu, các quy tắc về khóa, đo lường, đến trễ và điều chỉnh vẫn phải rõ.

Ví dụ xuyên suốt dùng cảm biến nhiệt độ `SEN-A` trong một kho. Giá trị và mốc thời gian dưới đây chỉ phục vụ minh họa:

| Bản tin nhận | Phép đo gốc | Thời điểm đo (UTC) | Giá trị | Thời điểm máy chủ nhận (UTC) | Ý nghĩa |
| --- | --- | --- | ---: | --- | --- |
| E1 | M-101, rev 1 | 10:01:00 | 7,0 °C | 10:01:05 | Bản đo ban đầu. |
| E2 | M-102, rev 1 | 10:01:00 | 9,0 °C | 10:03:00 | **Bản đo khác**, trùng timestamp với M-101. |
| E3 | M-101, rev 1 | 10:01:00 | 7,0 °C | 10:04:00 | Gửi lại cùng revision. |
| E4 | M-101, rev 2 | 10:01:00 | 6,5 °C | 11:50:00 | Điều chỉnh có căn cứ. |
| E5 | M-099, rev 1 | 09:59:00 | 5,0 °C | 10:30:00 | Bản đo **đến trễ** của cửa sổ trước. |

Nếu hai bản đo M-101 và M-102 đều được chấp nhận để tính trung bình mẫu trong cửa sổ 10:00–10:15, sau correction phải có **hai mẫu**, tổng **15,5 °C** và trung bình **7,75 °C**. E3 không làm số mẫu tăng. E5 phải được tính cho cửa sổ **09:45–10:00**, chứ không phải cửa sổ của lúc nhận 10:30.

## 2. Bốn thời điểm và hai loại thứ tự cần tách biệt

Một mô hình chuỗi thời gian thường cần nhiều hơn một timestamp.

| Thuộc tính | Ý nghĩa | Dùng để làm gì? |
| --- | --- | --- |
| `measured_at` / `event_time` | Lúc phép đo hoặc sự việc được thiết bị/nguồn xác nhận xảy ra. | Đặt mẫu vào đúng trục thời gian và cửa sổ phân tích. |
| `source_emitted_at` | Lúc nguồn đóng gói hoặc gửi bản tin, nếu nguồn cung cấp đáng tin. | Phân tích độ trễ thiết bị/gateway. |
| `received_at` | Lúc hệ thống tiếp nhận bản tin tại ranh giới ingest. | Theo dõi độ trễ mạng và hàng đợi. |
| `recorded_at` / `ingested_at` | Lúc bản ghi được lưu vào kho xử lý. | Audit quá trình ingest, xử lý retry. |
| `correction_decided_at` (nếu có) | Lúc nguồn có thẩm quyền xác nhận điều chỉnh. | Giải thích lúc nào giá trị mới được công nhận. |
| `source_revision` | Thứ tự sửa đổi **của cùng một phép đo** theo nguồn có thẩm quyền. | Chọn revision hiệu lực, chống message cũ ghi đè. |
| `device_sequence` (nếu có) | Số thứ tự bản đo theo phiên làm việc/thiết bị, theo hợp đồng nguồn. | Phát hiện khoảng thiếu và thứ tự phát sinh. |

**Không đồng nhất các trục sau:**

- Thứ tự **nhận message** khác thứ tự **đo**.
- Thứ tự **revision của một phép đo** khác thứ tự **các phép đo của cảm biến**.
- `recorded_at` mới hơn không chứng minh giá trị đo đúng hơn.
- Hai nguồn có đồng hồ không đồng bộ; so sánh timestamp cần xét độ tin cậy và khả năng lệch đồng hồ.
- Event có `measured_at` trong quá khứ nhưng revision mới được xác nhận hôm nay vẫn là một **điều chỉnh mới**, không phải một event phải chen lại vào lịch sử phiên bản cũ.

~~~mermaid
sequenceDiagram
    participant S as Cảm biến
    participant G as Gateway
    participant DB as Kho dữ liệu
    S->>G: M-101 rev1: đo lúc 10:01
    G->>DB: Gửi M-101 rev1 lúc 10:01:05
    G->>DB: Retry M-101 rev1 lúc 10:04
    Note over DB: Không tạo mẫu thứ hai
    S->>G: M-099 rev1 đo lúc 09:59 (offline)
    G->>DB: Nhận M-099 lúc 10:30
    Note over DB: Đưa về bucket 09:45
    G->>DB: M-101 rev2 đã hiệu chuẩn lúc 11:50
    Note over DB: Thay đóng góp M-101 rev1
~~~

Sơ đồ nhằm phân biệt các mốc, không ngụ ý cảm biến có thể tự phát bản revision được phê duyệt. Trong thực tế, revision có thể do thiết bị, dịch vụ hiệu chuẩn hoặc bộ phận vận hành có thẩm quyền phát hành; cần ghi rõ ai được phép điều chỉnh.

## 3. Phân biệt duplicate, collision, update và correction

Những hiện tượng sau không thể xử lý bằng cùng một câu lệnh `ON CONFLICT DO NOTHING`.

| Hiện tượng | Cách nhận diện | Hành vi mong đợi |
| --- | --- | --- |
| **Message lặp** | Cùng định danh sự kiện/phiên bản nguồn, payload tương đương. | Idempotent: không nhân mẫu hay aggregate. |
| **Hai phép đo hợp lệ trùng thời điểm** | `measured_at` giống nhau, **measurement_id khác nhau** theo hợp đồng nguồn. | Lưu cả hai nếu grain cho phép nhiều mẫu tại cùng timestamp. |
| **Hai payload mâu thuẫn cùng ID và revision** | Cùng measurement key/revision nhưng giá trị hoặc thời điểm khác nhau. | Cách ly/điều tra; không tùy chọn bản đến sau. |
| **Correction** | Cùng measurement key, revision cao hơn với giá trị hoặc timestamp được sửa. | Lưu lịch sử điều chỉnh; thay bản hiệu lực và cập nhật aggregate. |
| **Retraction / vô hiệu phép đo** | Revision mới yêu cầu loại phép đo không hợp lệ. | Giữ tombstone/version mới để dữ liệu cũ không sống lại. |
| **Mẫu mới đến trễ** | Measurement key mới, `measured_at` cũ hơn thời điểm nhận. | Ghi mẫu vào đúng cửa sổ thời gian nghiệp vụ. |
| **Một cảm biến gửi hai bản đo không có ID riêng** | Chỉ có `sensor_id + timestamp` và giá trị khác nhau. | Không đủ bằng chứng tự phân biệt duplicate và hai mẫu thật; cần bổ sung hợp đồng hoặc quy tắc có phê duyệt. |

**“Trùng thời điểm” không tương đương “trùng bản đo”.** Một thiết bị có thể đo hai kênh nhiệt độ, hai mẫu ở độ phân giải timestamp chỉ đến giây, hoặc hai lần đo lại đúng cùng giây. Unique trên `(sensor_id, measured_at)` sẽ làm mất các phép đo hợp lệ trừ khi nghiệp vụ cam kết đúng **một** phép đo cho mỗi khóa này.

Với hệ thực sự lấy đúng một mẫu nhiệt độ mỗi phút từ mỗi kênh, có thể định nghĩa grain `(sensor_id, channel_id, sample_slot)`. Nhưng phải làm rõ slot là lịch đo đã hoạch định, không phải timestamp đã làm tròn tùy ý. Việc gộp hai mẫu vào một slot theo trung bình hay “lấy mẫu cuối” là **quy tắc nghiệp vụ**, không phải một phép dedup tự nhiên.

## 4. Đầu tiên phải hiểu loại phép đo: gauge, counter, delta hay event

Cách xử lý đến trễ và điều chỉnh phụ thuộc vào **ý nghĩa của số đo**.

| Loại phép đo | Ví dụ | Có thể SUM trực tiếp theo thời gian? | Khi correction/retraction |
| --- | --- | --- | --- |
| **Gauge / giá trị tại mốc** | Nhiệt độ, áp suất, độ ẩm, mức pin. | Thường không; SUM các mẫu ít có nghĩa nghiệp vụ. | Thay giá trị mẫu; AVG/MIN/MAX cửa sổ bị ảnh hưởng. |
| **Cumulative counter** | Tổng điện năng công tơ, tổng byte đã gửi. | Không SUM các mốc counter như số tiêu thụ. | Tính lại chênh lệch giữa các mốc và xử lý reset/wrap. |
| **Delta/increment** | Số kiện tăng thêm trong một chu kỳ, lượng nước tăng trong 5 phút. | Có thể nếu khoảng thời gian/đơn vị/nguồn phù hợp và không chồng lặp. | Trừ đóng góp cũ, cộng đóng góp mới vào kỳ tương ứng. |
| **Occurrence/event** | Báo động kích hoạt, thiết bị khởi động lại. | Thường COUNT số sự việc duy nhất, không AVG giá trị. | Hủy/sửa sự việc phải có tham chiếu đúng ID và logic đếm. |
| **State transition** | Máy từ RUNNING sang STOPPED. | Không SUM trạng thái; có thể tính thời lượng mỗi trạng thái. | Correction có thể ảnh hưởng cả khoảng thời gian trước/sau. |

Đối với **gauge lấy mẫu không đều**, trung bình cộng các mẫu không đồng nghĩa **trung bình theo thời gian**. Ví dụ một lần đo 30 °C và 100 lần đo 20 °C trong một khoảng ngắn sẽ làm trung bình theo số mẫu gần 20 °C, nhưng không chứng minh môi trường ở 20 °C trong phần lớn thời gian. Nếu yêu cầu trung bình thời gian, cần chính sách nội suy/giữ giá trị, khoảng mất dữ liệu và ranh giới tính toán rõ.

Đối với **cumulative counter**, một bản đo đến trễ nằm giữa hai mốc có thể làm thay đổi **hai delta kề nhau**; sửa trực tiếp “cộng thêm giá trị counter” chắc chắn sai. Đối với tài chính hoặc thanh toán, không mặc định giá trị đo là amount có thể ghi đè; giao dịch đã xác nhận thường cần correction/reversal theo nghiệp vụ riêng.

## 5. Định nghĩa grain và khóa trước khi tạo bảng

Một thiết kế hợp lý cho ví dụ nhiệt độ:

> **Một phép đo nghiệp vụ** được định danh bởi `(tenant_id, source_system, sensor_id, measurement_id)`. Mỗi lần xác nhận hoặc điều chỉnh cùng phép đo có `source_revision` tăng theo hợp đồng nguồn.

Trong đó:

- `tenant_id`: ranh giới sở hữu dữ liệu và cách ly giữa khách hàng.
- `source_system`: namespace của nhà cung cấp/đường nguồn; không coi ID của hai nguồn là cùng một bản đo.
- `sensor_id`: định danh cảm biến/kênh đo theo hợp đồng đã chuẩn hóa.
- `measurement_id`: định danh **bền vững cho một lần đo**, giữ nguyên qua correction.
- `source_revision`: thứ tự logic của các phiên bản được nguồn có thẩm quyền xác nhận; dùng để chọn trạng thái hiệu lực.

**Không đặt `measured_at` làm khóa duy nhất mặc định.** Timestamp phục vụ sắp xếp và gom cửa sổ. Nó có thể được sửa trong revision mới nếu trước đó đồng hồ thiết bị sai; business key phải giữ ổn định để trace.

### Nếu thiết bị không có measurement_id thì sao?

Có vài hướng, nhưng phải có hợp đồng:

1. Tạo ID ổn định từ `device_id + channel + boot_session + sequence` nếu các trường này **duy nhất, không tái sử dụng, và replay cho cùng ID**.
2. Nếu chỉ có `measured_at` với cam kết một mẫu mỗi slot, tạo key từ sensor/slot *sau khi* xác nhận quy tắc slot.
3. Nếu gateway gán ID khi nhận lần đầu, phải lưu bảng ánh xạ hoặc dedup token từ nguồn; nếu retry mỗi lần bị cấp ID mới thì không chống lặp được.
4. Nếu nguồn không có bất kỳ định danh và quy tắc nào phân biệt hai mẫu cùng timestamp, **không thể bảo đảm** vừa không bỏ mất mẫu thật vừa không nhân duplicate. Cần bổ sung giao thức hoặc chấp nhận giới hạn công khai.

### Phân biệt ID phép đo với ID bản tin

Một revision có thể đi qua broker nhiều lần. `measurement_id` nói “đo nào”; `source_revision` nói “bản sửa nào”; `source_event_id` hoặc `message_id` nói “bản tin nguồn nào”, nếu hệ nguồn có ID ổn định. Không dùng `message_id` thay `measurement_id` nếu mỗi lần retry có message ID mới.

## 6. Hợp đồng sự kiện đo lường và bản điều chỉnh

Một bản tin có cấu trúc đủ rõ giúp kiểm chứng đơn vị, thời điểm, nguồn và quan hệ điều chỉnh.

~~~json
{
  "tenant_id": "00000000-0000-4000-8000-000000000001",
  "source_system": "cold-room-gateway",
  "sensor_id": "SEN-A",
  "measurement_id": "M-101",
  "source_revision": 2,
  "source_event_id": "GW-REV-101-2",
  "operation": "UPSERT",
  "measured_at": "2026-11-20T10:01:00Z",
  "source_emitted_at": "2026-11-20T11:49:30Z",
  "correction_decided_at": "2026-11-20T11:49:00Z",
  "value": 6.5,
  "unit_code": "CELSIUS",
  "quality_code": "ACCEPTED",
  "reason_code": "CALIBRATION_CORRECTION",
  "calibration_reference": "CAL-2026-119",
  "supersedes_revision": 1
}
~~~

Hợp đồng minh họa có những bất biến:

1. `measurement_id` giữ nguyên qua revision; `source_revision = 2` là một cập nhật của M-101, không phải phép đo thứ hai.
2. `measured_at` là mốc của phép đo, **không** đổi sang 11:49 chỉ vì correction được quyết định lúc 11:49.
3. `correction_decided_at` nói khi nào việc sửa được chấp thuận, không phải khi cửa sổ đo kết thúc.
4. `operation = UPSERT` cung cấp giá trị hiệu lực mới; `RETRACT` biểu diễn phép đo bị vô hiệu. Với `RETRACT`, payload nên nói rõ ID, revision, lý do, nhưng không phát giá trị số mới giả tạo như 0.
5. `unit_code` và `quality_code` phải có định nghĩa; °C không thể SUM với °F nếu chưa chuyển đổi theo công thức/đơn vị đã quản trị.
6. `source_event_id` ổn định qua retry cùng revision nếu nguồn cam kết; nếu không, dựa vào khóa measurement + revision và kiểm tra payload.

Một bản điều chỉnh không nhất thiết sửa **chính giá trị**. Nó có thể sửa `measured_at` do đồng hồ lệch, thay `quality_code` từ `ACCEPTED` sang `INVALID`, hoặc rút bản đo hoàn toàn. Những thay đổi này có thể ảnh hưởng bucket, count và báo cáo an toàn môi trường.

**Đừng tự chuyển mọi giá trị không bình thường thành lỗi.** Nhiệt độ 45 °C có thể là báo động thật, không phải duplicate. Quy tắc kiểm tra hợp lệ cần tách giới hạn đo của thiết bị, mã chất lượng nguồn và điều kiện bất thường nghiệp vụ.

## 7. Lược đồ PostgreSQL: lịch sử revision và bản hiện hành

Một cách thiết kế là giữ **revision history** như nguồn tham chiếu có thể kiểm tra và **current measurement** như cấu trúc đọc nhanh. Đây không buộc toàn hệ thống phải dùng event sourcing; nó chỉ thể hiện đúng vòng đời của phép đo.

### Khóa ổn định để tuần tự hóa thao tác trên một phép đo

~~~sql
CREATE TABLE measurement_key (
    tenant_id       UUID NOT NULL,
    source_system   VARCHAR(64) NOT NULL,
    sensor_id       VARCHAR(100) NOT NULL,
    measurement_id  VARCHAR(120) NOT NULL,
    PRIMARY KEY (
        tenant_id, source_system, sensor_id, measurement_id
    )
);
~~~

Bảng khóa nhỏ này cho phép tạo dòng định danh trước, rồi `SELECT ... FOR UPDATE` để bảo vệ cả trường hợp **chưa có measurement_current**. Chỉ khóa current row khi nó tồn tại không giải quyết cuộc đua hai worker cùng tạo hàng mới.

### Lưu mọi revision được nguồn gửi và chấp nhận

~~~sql
CREATE TABLE measurement_revision (
    tenant_id           UUID NOT NULL,
    source_system       VARCHAR(64) NOT NULL,
    sensor_id           VARCHAR(100) NOT NULL,
    measurement_id      VARCHAR(120) NOT NULL,
    source_revision     BIGINT NOT NULL CHECK (source_revision > 0),
    source_event_id     VARCHAR(160),
    measured_at         TIMESTAMPTZ NOT NULL,
    source_emitted_at   TIMESTAMPTZ,
    received_at         TIMESTAMPTZ NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    correction_decided_at TIMESTAMPTZ,
    operation           VARCHAR(8) NOT NULL
                        CHECK (operation IN ('UPSERT', 'RETRACT')),
    value_num           NUMERIC(18, 6),
    unit_code           VARCHAR(24),
    quality_code        VARCHAR(24) NOT NULL,
    reason_code         VARCHAR(80),
    PRIMARY KEY (
        tenant_id, source_system, sensor_id,
        measurement_id, source_revision
    ),
    FOREIGN KEY (
        tenant_id, source_system, sensor_id, measurement_id
    )
    REFERENCES measurement_key (
        tenant_id, source_system, sensor_id, measurement_id
    ),
    CHECK (
        (operation = 'UPSERT'
            AND value_num IS NOT NULL AND unit_code IS NOT NULL)
        OR
        (operation = 'RETRACT' AND value_num IS NULL)
    )
);
~~~

Với `operation = RETRACT`, vẫn ghi `measured_at` để truy vết mốc mà bản đo bị loại; phép tính aggregate không xem dòng đó là một sample giá trị 0.

### Bản hiệu lực mới nhất theo measurement key

~~~sql
CREATE TABLE measurement_current (
    tenant_id        UUID NOT NULL,
    source_system    VARCHAR(64) NOT NULL,
    sensor_id        VARCHAR(100) NOT NULL,
    measurement_id   VARCHAR(120) NOT NULL,
    source_revision  BIGINT NOT NULL CHECK (source_revision > 0),
    measured_at      TIMESTAMPTZ NOT NULL,
    operation        VARCHAR(8) NOT NULL
                     CHECK (operation IN ('UPSERT', 'RETRACT')),
    value_num        NUMERIC(18, 6),
    unit_code        VARCHAR(24),
    quality_code     VARCHAR(24) NOT NULL,
    applied_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        tenant_id, source_system, sensor_id, measurement_id
    ),
    FOREIGN KEY (
        tenant_id, source_system, sensor_id, measurement_id,
        source_revision
    )
    REFERENCES measurement_revision (
        tenant_id, source_system, sensor_id,
        measurement_id, source_revision
    ),
    CHECK (
        (operation = 'UPSERT'
            AND value_num IS NOT NULL AND unit_code IS NOT NULL)
        OR
        (operation = 'RETRACT' AND value_num IS NULL)
    )
);

CREATE INDEX ix_measurement_current_time
    ON measurement_current
        (tenant_id, sensor_id, measured_at DESC, measurement_id)
    WHERE operation = 'UPSERT';

CREATE INDEX ix_measurement_revision_received
    ON measurement_revision
        (tenant_id, received_at DESC);
~~~

**Giới hạn và giả định của DDL:**

- Khóa composite bao gồm namespace nguồn để tránh gộp hai bản đo của hai hệ khác nhau. Ví dụ giả định mỗi phép đo có revision tăng nghiêm ngặt **trong chính measurement key đó**.
- `measurement_revision` giữ bản đã từng nhận theo từng revision; `measurement_current` là bản dẫn xuất có thể dựng lại khi lịch sử revision đủ.
- **Không xóa current row khi RETRACT**. Tombstone với revision cao ngăn một event UPSERT cũ đến sau làm sống lại phép đo đã bị vô hiệu.
- `recorded_at` thuộc thời gian ghi nhận của kho dữ liệu; không thay `measured_at`. PostgreSQL `now()` là mốc bắt đầu transaction, có thể khác thời điểm commit; nếu cần commit order phải dùng cơ chế nguồn đáng tin, không dựa vào timestamp này.
- Chỉ mục theo thời gian phục vụ truy vấn một số phép đo hiện hành. Nếu có rất nhiều sensor trong một tenant, cần đánh giá predicate/selectivity, partition và kiểu thiết bị trước khi thêm chỉ mục.
- `NUMERIC(18,6)` giúp phép tính thập phân minh họa ổn định, nhưng có chi phí so với kiểu float. Chọn độ chính xác theo đặc tính cảm biến và sai số cho phép; không coi số thập phân nhiều chữ số là tăng độ chính xác vật lý của thiết bị.
- CHECK chỉ bảo vệ hình thức cơ bản. Cần validation schema, tenant, quyền hiệu chỉnh, đơn vị, giá trị hợp lệ và quan hệ thời gian tại lớp ingest.

Nếu `source_event_id` được nguồn cam kết duy nhất theo namespace, có thể bổ sung unique tương ứng và quy trình đối chiếu. Không thêm unique toàn cục khi ID này có thể tái sử dụng giữa gateway hoặc có lúc không tồn tại.

## 8. Ingest an toàn: khóa, revision, idempotency và correction

Giả sử có hai worker cùng nhận M-101 revision 2. Nếu chỉ kiểm tra “chưa thấy revision 2” rồi đồng thời ghi, hai worker có thể cùng sửa aggregate. Cần serial hóa quyết định ở **đúng measurement key** và commit nguyên tử những dữ liệu liên quan.

### Quy trình transaction đề xuất

1. Kiểm tra nguồn, chữ ký/chứng thực nếu có, schema, tenant và đơn vị. Tính representation chuẩn của các trường nghiệp vụ để kiểm tra conflict **cùng ID/revision**.
2. `BEGIN`. Đảm bảo khóa `measurement_key` tồn tại; khóa hàng này để một writer xử lý key đó mỗi lần.
3. Đọc revision cũ cùng `(tenant, source, sensor, measurement_id, source_revision)` nếu đã có. Nếu payload giống nhau: xử lý **retry idempotent**; nếu khác: **conflict**, rollback/cách ly và không tự chọn bản đến sau.
4. Nếu revision chưa có, chèn vào `measurement_revision`. Giá trị `source_revision` thấp hơn current vẫn có thể được lưu để đối chiếu lịch sử, nhưng **không được ghi đè current**.
5. Đọc `measurement_current`. Chỉ khi incoming revision **lớn hơn** current revision mới xác lập bản hiệu lực.
6. Nếu thay đổi bản hiệu lực, tính ảnh hưởng aggregate của **bản cũ** và **bản mới**, cập nhật current và aggregate cùng transaction khi ở cùng DB. Nếu projection ở hệ khác, lưu outbox/offset và bảo đảm xử lý idempotent tại đích.
7. Ghi receipt/checkpoint nguồn khi cần với cơ chế bảo đảm không bỏ qua các record chưa commit. `COMMIT`.
8. Sau commit mới trả kết quả/ack phù hợp với broker; nếu worker chết trước ack, retry phải cho kết quả như một lần xử lý.

Phần khóa trọng yếu có thể viết:

~~~sql
BEGIN;

INSERT INTO measurement_key (
    tenant_id, source_system, sensor_id, measurement_id
)
VALUES (
    :tenant_id, :source_system, :sensor_id, :measurement_id
)
ON CONFLICT DO NOTHING;

SELECT 1
FROM measurement_key
WHERE tenant_id = :tenant_id
  AND source_system = :source_system
  AND sensor_id = :sensor_id
  AND measurement_id = :measurement_id
FOR UPDATE;

-- Trong cùng transaction:
-- 1. kiểm tra revision/payload và lưu revision nếu chưa có;
-- 2. đọc current và so thứ tự revision;
-- 3. cập nhật current + các aggregate bị ảnh hưởng;
-- 4. lưu checkpoint/outbox liên quan nếu cùng biên giao dịch.

COMMIT;
~~~

Khối SQL này **minh họa phần khóa**, không phải thủ tục ingest hoàn chỉnh có thể chạy mà bỏ các bước trong comment. Khi triển khai, ứng dụng hoặc stored procedure phải thực hiện đầy đủ việc so sánh revision và rollback trên conflict. Khóa `measurement_key` ngăn hai transaction cùng key thay current/aggregate đồng thời; các tổng hợp chung giữa nhiều key vẫn cần atomic update/row lock ở hàng aggregate.

### Những trường hợp đặc biệt

| Trường hợp | Revision trong history | Current | Aggregate |
| --- | --- | --- | --- |
| Bản M-101 rev 1 nhận lần đầu | Insert rev 1. | Gắn rev 1. | Cộng 1 mẫu. |
| Rev 1 được gửi lại nguyên nội dung | Không chèn thêm. | Giữ rev 1. | Không thay đổi. |
| Cùng rev 1 nhưng payload khác | Cách ly conflict. | Không thay đổi. | Không thay đổi. |
| Rev 3 đến trước rev 2 | Có thể chấp nhận rev 3 theo policy. | Gắn rev 3 nếu nguồn bảo đảm revision thứ tự. | Áp đóng góp rev 3. |
| Rev 2 đến sau rev 3 | Có thể lưu rev 2 để audit. | **Giữ rev 3**. | Không thay đổi. |
| Rev 4 = RETRACT | Insert rev 4. | Giữ tombstone rev 4. | Loại đóng góp rev 3 nếu đang có. |

**Thận trọng với revision bị thiếu:** đối với phép đo có revision là **toàn trạng thái**, rev 3 có thể tự mang giá trị hiệu lực đầy đủ nên không cần rev 2 để cập nhật current. Nhưng nếu revision chỉ là **delta/patch** phụ thuộc bản trước, không thể áp rev 3 khi chưa có rev 2; phải giữ đợi/lấy lại hoặc materialize full-state đáng tin. Hai hợp đồng này phải phân biệt từ đầu.

Nếu hệ nguồn **không cung cấp revision tin cậy**, không thể coi “message nhận sau luôn thắng”. Có thể dựa vào vị trí CDC commit theo từng key, hoặc thiết lập quy trình phê duyệt correction với phiên bản do dịch vụ sở hữu dữ liệu cấp. Nếu không có một thứ tự có thẩm quyền, cần phân loại bản mâu thuẫn để xử lý thay vì tùy tiện dùng timestamp.

## 9. Ví dụ tính đúng khi trùng thời điểm, gửi lặp và correction

Giả sử chính sách aggregate chấp nhận mọi phép đo `operation = UPSERT` và `quality_code = ACCEPTED`, tính **trung bình theo số mẫu** cho cửa sổ 15 phút của cùng cảm biến. Hai bản đo M-101 và M-102 thuộc cùng cửa sổ.

Trước correction:

| measurement_id | revision hiệu lực | measured_at | value |
| --- | ---: | --- | ---: |
| M-101 | 1 | 10:01:00 | 7,0 |
| M-102 | 1 | 10:01:00 | 9,0 |

`count = 2`, `sum = 16,0`, `avg = 8,0`. Message lặp E3 của M-101 rev 1 không thay đổi.

Sau correction M-101 rev 2 = 6,5:

| measurement_id | revision hiệu lực | measured_at | value |
| --- | ---: | --- | ---: |
| M-101 | 2 | 10:01:00 | 6,5 |
| M-102 | 1 | 10:01:00 | 9,0 |

Khi đó `count = 2`, `sum = 15,5`, `avg = 7,75`. Không được chỉ **cộng thêm 6,5**, vì revision 2 **thay thế** giá trị 7,0 của cùng bản đo M-101.

Nếu rev 3 sửa thời điểm M-101 từ 10:01 sang 09:59, bản hiệu lực này phải:

1. **Trừ** đóng góp M-101 ra khỏi cửa sổ 10:00–10:15.
2. **Cộng** đóng góp M-101 vào cửa sổ 09:45–10:00.
3. Giữ nguyên danh tính M-101 và revision mới trong current.
4. Ghi nhận lịch sử thay đổi thời điểm trong revision history.

Như vậy timestamp là **thuộc tính có thể bị điều chỉnh**, không phải khóa duy nhất bất biến của phép đo.

## 10. Cửa sổ thời gian, watermark và mức trễ được chấp nhận

Một cửa sổ `[10:00, 10:15)` bao gồm mẫu đo lúc 10:00:00 nhưng **không** gồm mẫu đúng 10:15:00. Cách đặt khoảng nửa mở tránh trùng ở ranh giới.

Trong xử lý stream, **watermark** thường biểu diễn ước lượng về tiến độ theo **event time**: những bản ghi có thời gian trước một mốc nào đó *được kỳ vọng* phần lớn đã tới. Đây không phải bằng chứng tuyệt đối rằng không còn dữ liệu đến muộn. Mức bảo đảm phụ thuộc hệ thống, chính sách phát watermark, tính đầy đủ của nguồn và độ trễ cho phép.

Ví dụ:

- Đến 10:25, hệ thống phát watermark 10:20, nghĩa là đã tiến đến mốc kỳ vọng này theo logic nguồn.
- Mẫu đo lúc 10:08 đến lúc 10:30 là **late event** đối với watermark đó.
- Nếu policy giữ cửa sổ 10:00–10:15 ở trạng thái có thể sửa trong 1 giờ, có thể cập nhật lại aggregate.
- Nếu cửa sổ đã **finalized**, cần quyết định cho phép restatement, phát bản điều chỉnh riêng hoặc ghi vào danh sách late exceptions để đối soát. **Không âm thầm bỏ** nếu báo cáo đã cam kết đầy đủ.

Phân biệt những trạng thái có ích:

| Trạng thái cửa sổ | Ý nghĩa | Dữ liệu muộn/correction |
| --- | --- | --- |
| **OPEN** | Đang nhận và tích lũy mẫu. | Cập nhật bình thường, có chống lặp. |
| **PROVISIONAL** | Đã qua thời gian cuối cửa sổ nhưng còn cho phép dữ liệu muộn. | Cập nhật số đo, công bố revision nếu đã báo cáo. |
| **FINALIZED** | Đã chốt theo SLA/policy. | Có quy trình điều chỉnh hoặc ngoại lệ minh bạch; không biến chốt thành “sự thật tuyệt đối”. |
| **RESTATED** | Số liệu đã công bố được tính lại vì bằng chứng mới. | Lưu version/mốc công bố và tác động downstream. |

Cần quyết định **event-time window** hay **processing-time window**. Kho lạnh muốn biết “nhiệt độ ở 10:00” thường cần event time. Một bảng giám sát “số message máy chủ nhận trong 5 phút gần đây” lại có thể dùng received/processing time. Không dùng cùng một chỉ số cho cả hai.

### Cách tạo bucket ổn định trong PostgreSQL

Với PostgreSQL phiên bản hỗ trợ `date_bin`, có thể nhóm các phép đo theo khoảng 15 phút có gốc UTC cố định:

~~~sql
SELECT
    sensor_id,
    date_bin(
        INTERVAL '15 minutes',
        measured_at,
        TIMESTAMPTZ '2000-01-01 00:00:00+00'
    ) AS bucket_start_utc,
    unit_code,
    COUNT(*) AS sample_count,
    SUM(value_num) AS sample_sum,
    AVG(value_num) AS sample_average
FROM measurement_current
WHERE tenant_id = :tenant_id
  AND operation = 'UPSERT'
  AND quality_code = 'ACCEPTED'
  AND sensor_id = :sensor_id
  AND measured_at >= :from_utc
  AND measured_at < :to_utc
GROUP BY sensor_id, bucket_start_utc, unit_code
ORDER BY bucket_start_utc;
~~~

Đây là trung bình **theo số mẫu**, không phải trung bình theo thời lượng. Điều kiện `unit_code` ngăn trộn đơn vị khác nhau; khi một sensor thay đơn vị, cần chuyển đổi theo quy tắc được phê duyệt trước khi gộp. Múi giờ hiển thị có thể khác UTC, nhưng bucket phải có quy tắc gốc và timezone rõ. `date_bin` không dùng khoảng tháng biến thiên như một stride cố định.

### Ngày nghiệp vụ không luôn trùng ngày UTC

Nếu báo cáo theo ngày địa phương của kho, lưu timestamp tuyệt đối và xác định múi giờ của kho/tenant. Ngày có chuyển đổi giờ mùa hè ở một số khu vực có thể dài 23 hoặc 25 giờ; không cứ lấy `24 * 60` phút rồi gọi là một ngày địa phương. Khi tính tuần/tháng, cần chính sách calendar/timezone chứ không chỉ quy đổi timestamp nhận dữ liệu.

## 11. Điều chỉnh aggregate mà không đếm hai lần

Một bảng tổng hợp ví dụ cho **gauge theo số mẫu**:

~~~sql
CREATE TABLE sensor_15m_summary (
    tenant_id         UUID NOT NULL,
    sensor_id         VARCHAR(100) NOT NULL,
    unit_code         VARCHAR(24) NOT NULL,
    bucket_start_utc  TIMESTAMPTZ NOT NULL,
    sample_count      BIGINT NOT NULL DEFAULT 0
                      CHECK (sample_count >= 0),
    sample_sum        NUMERIC(24, 6) NOT NULL DEFAULT 0,
    revised_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        tenant_id, sensor_id, unit_code, bucket_start_utc
    )
);
~~~

Nếu mỗi sample được **đóng góp đúng một lần**, có thể tính:

~~~text
average = sample_sum / sample_count, nếu sample_count > 0
~~~

Khi bản hiện hành của một measurement key thay đổi từ `old` sang `new`, **đừng lấy giá trị nhận mới rồi cộng trực tiếp**. Tính phép chênh lệch:

~~~text
Nếu old.operation = UPSERT và old.quality = ACCEPTED:
    old_bucket = bucket(old.measured_at)
    apply_delta(old_bucket, count = -1, sum = -old.value_num)

Nếu new.operation = UPSERT và new.quality = ACCEPTED:
    new_bucket = bucket(new.measured_at)
    apply_delta(new_bucket, count = +1, sum = +new.value_num)

Ghi new thành current; commit các delta và current cùng transaction.
~~~

**Tại sao đúng?**

- **Update value cùng bucket:** count -1 rồi +1 nên không đổi, sum thay bằng `new - old`.
- **Thay timestamp sang bucket khác:** bucket cũ giảm một mẫu, bucket mới tăng một mẫu.
- **RETRACT:** chỉ trừ đóng góp cũ, không cộng một giá trị 0 giả.
- **Đổi quality thành INVALID:** loại đóng góp theo quy tắc lọc; giữ revision cho audit.
- **Correction đến muộn nhưng revision mới hơn:** vẫn cập nhật các bucket lịch sử liên quan theo policy.
- **Retry cùng revision:** không áp dụng delta lần thứ hai.

Với nhiều worker, hàng aggregate cũng cần **UPDATE nguyên tử hoặc khóa hàng**, không để hai transaction cùng tính sum từ snapshot cũ rồi ghi đè nhau. Việc khóa đúng measurement key chỉ tránh hai thao tác cạnh tranh trên **cùng bản đo**, không tự bảo vệ aggregate chia sẻ của nhiều bản đo khác nhau.

### Một mẫu cập nhật delta nguyên tử

Với **đóng góp mới** (`count = +1`), có thể tạo bucket nếu chưa có hoặc cộng vào bucket đã tồn tại. Với **loại đóng góp cũ** (`count = -1`), chỉ cập nhật bucket **đã tồn tại**; không thử `INSERT` một hàng có `sample_count = -1` vì ràng buộc không âm sẽ chặn ngay cả khi đang xử lý xung đột.

~~~sql
-- Thêm một mẫu mới hợp lệ vào bucket (delta_count = +1).
INSERT INTO sensor_15m_summary (
    tenant_id, sensor_id, unit_code,
    bucket_start_utc, sample_count, sample_sum
)
VALUES (
    :tenant_id, :sensor_id, :unit_code,
    :bucket_start_utc, 1, :new_value
)
ON CONFLICT (
    tenant_id, sensor_id, unit_code, bucket_start_utc
)
DO UPDATE SET
    sample_count = sensor_15m_summary.sample_count + 1,
    sample_sum = sensor_15m_summary.sample_sum + EXCLUDED.sample_sum,
    revised_at = now();

-- Loại đóng góp của một mẫu cũ; 0 hàng trả về = cần điều tra.
UPDATE sensor_15m_summary
SET sample_count = sample_count - 1,
    sample_sum = sample_sum - :old_value,
    revised_at = now()
WHERE tenant_id = :tenant_id
  AND sensor_id = :sensor_id
  AND unit_code = :unit_code
  AND bucket_start_utc = :old_bucket_start_utc
  AND sample_count >= 1
RETURNING sample_count;
~~~

Hai câu SQL là **những nhánh minh họa**, không phải luôn chạy cả hai cho mọi event. Một correction có old và new hợp lệ phải trừ đóng góp cũ rồi cộng mới **trong cùng transaction** với cập nhật `measurement_current`; phép đo mới chỉ cộng, còn retraction chỉ trừ. Nếu nhánh loại mẫu trả 0 hàng hoặc gặp dữ liệu sai lệch, rollback và điều tra/rebuild thay vì âm thầm bỏ qua. Khi một correction chạm **hai bucket**, cần thống nhất thứ tự khóa để giảm deadlock. Phép cộng ở nhánh `ON CONFLICT DO UPDATE` là atomic trên hàng summary nhưng không thay thế kiểm soát revision/idempotency theo measurement key.

### AVG, MIN/MAX và các phép đo khó “trừ”

- `SUM` và `COUNT` dễ áp delta vì có phép toán đảo thích hợp.
- `AVG` tính từ sum/count, không cộng trung bình của các nhóm nếu số mẫu khác nhau.
- `MIN`, `MAX` có thể cần **tính lại** khi chính mẫu đang giữ cực trị bị sửa hoặc loại.
- `MEDIAN`, percentile và quantile sketch không phải lúc nào hỗ trợ xóa một đóng góp chính xác; cần thuật toán cụ thể hoặc recompute.
- **Time-weighted average** của gauge và **delta của counter** có thể phụ thuộc mẫu **lân cận**, nên correction một điểm ảnh hưởng nhiều khoảng. Không dùng cùng một hàm delta cho mọi metric.

Ở nhiều hệ thống, cách an toàn hơn là **recompute một bucket bị ảnh hưởng từ measurement_current** rồi ghi phiên bản summary mới, nhất là khi không có thao tác đảo dễ chứng minh đúng. Đổi lại là chi phí đọc lại tập mẫu; chọn theo tải, SLA và yêu cầu chính xác.

## 12. Bảng đọc hiện hành, lịch sử điều chỉnh và truy vấn "as-of"

Trong một hệ có correction, ít nhất hai câu hỏi có thể khác nhau:

1. **Hiện nay phép đo M-101 được công nhận có giá trị bao nhiêu?** Cần revision hiệu lực mới nhất.
2. **Lúc 10:15 trước khi hiệu chuẩn, hệ thống đã biết và báo cáo giá trị nào?** Cần lịch sử *when known/recorded*, không chỉ event-time.

`measurement_current` trả lời câu đầu. `measurement_revision` với `recorded_at` giúp điều tra quá trình nhận dữ liệu, nhưng để tái dựng chính xác “hệ thống biết gì tại thời điểm T” còn phải:

- Có thứ tự commit/hợp đồng nhất quán khi các revision được ghi gần nhau.
- Biết quy tắc chấp nhận bản correction, xử lý conflict và cách chốt watermark.
- Lưu được version của projection/KPI đã công bố, nếu báo cáo có nhiều bản restatement.
- Phân biệt `recorded_at` và thời điểm correction **được phê duyệt/hiệu lực** theo nghiệp vụ.

Một cách dựng current từ bảng revision để đối chiếu:

~~~sql
WITH latest AS (
    SELECT DISTINCT ON (
        tenant_id, source_system, sensor_id, measurement_id
    )
        tenant_id, source_system, sensor_id,
        measurement_id, source_revision,
        measured_at, operation, value_num,
        unit_code, quality_code
    FROM measurement_revision
    WHERE tenant_id = :tenant_id
    ORDER BY
        tenant_id, source_system, sensor_id,
        measurement_id, source_revision DESC
)
SELECT *
FROM latest
WHERE operation = 'UPSERT'
  AND quality_code = 'ACCEPTED';
~~~

Truy vấn này chọn **revision cao nhất đã được lưu** theo mỗi measurement key, giả định các revision có thứ tự toàn trạng thái đáng tin và không có revision đang tranh chấp chưa được hợp thức hóa. Nó không phải chứng minh tự động rằng revision đó đã được nguồn có thẩm quyền xác nhận.

### Lịch sử “đã biết” và lịch sử “có hiệu lực”

Giả sử lúc 10:15 dashboard công bố trung bình 8,0 °C. Đến 11:50 một correction cập nhật M-101, làm kết quả mới cho cùng cửa sổ là 7,75 °C.

- **Báo cáo đã công bố lúc 10:15:** 8,0 °C theo thông tin khi đó.
- **Báo cáo restated theo correction:** 7,75 °C.
- **Công tác đánh giá cảm biến:** cần biết correction được quyết định khi nào, nguyên nhân và độ lệch.

Nếu yêu cầu kiểm toán nghiêm ngặt, có thể cần lưu **published_at**, **report_version**, **source_cutoff/watermark**, **metric_definition_version** cho mỗi lần công bố. Một hàng summary bị ghi đè không tự cho biết số cũ đã từng hiển thị.

## 13. Dữ liệu đến trễ trong batch, CDC và pipeline phân tích

Không chỉ streaming mới gặp đến trễ. Một job ETL hằng ngày có thể nhận file đo của ngày hôm qua vào hôm nay, hoặc cần backfill dữ liệu khi thiết bị kết nối lại sau vài ngày.

Một pipeline có thể gồm:

~~~mermaid
flowchart LR
    S["Cảm biến / gateway"] --> L["Landing + metadata nguồn"]
    L --> V["Validate, identity, revision, dedup"]
    V --> H[("Measurement revision history")]
    V --> C[("Measurement current")]
    C --> B["Aggregate/rollup theo event-time"]
    B --> D[("Dashboard / kho phân tích")]
    H --> R["Recompute / đối soát lịch sử"]
    R --> B
~~~

Các bước cần hợp đồng nhất quán:

1. **Landing:** lưu nguồn, batch/message ID, thời gian nhận và thông tin format; loại bản lỗi schema vào khu vực cách ly có giới hạn quyền.
2. **Dedup:** sử dụng danh tính bản đo + revision, không dùng việc hai hàng có cùng timestamp để gộp.
3. **Upsert hiệu lực:** cập nhật current theo thứ tự có thẩm quyền.
4. **Aggregate:** cập nhật/recompute bucket thuộc `measured_at`, kể cả bucket cũ được chấp nhận sửa.
5. **Checkpoint:** đánh dấu điểm ingest hoàn tất **sau khi commit dữ liệu đích** hoặc trong transaction phù hợp. Nếu dựa broker/CDC, dùng offset/cursor có bảo đảm không mất record.
6. **Đối soát:** so số measurement keys, revision mới nhất, retract count và tổng hợp từ current với báo cáo.
7. **Công bố:** nếu số liệu đã chốt bị sửa, xác định chính sách restatement, downstream notification, cache invalidation.

### Không dùng “MAX(id)” thiếu bảo đảm commit làm watermark

Trong một database có sequence cấp trước commit, transaction A có thể nhận ID 101 nhưng commit sau B đã nhận và commit ID 102. Nếu ingestion đọc xong “tất cả ID ≤ 102” rồi tiếp tục `ID > 102`, event 101 có thể bị bỏ sót. Cần nguồn cursor có hợp đồng theo **thứ tự commit** hoặc một quy trình snapshot + change stream an toàn, không suy ra từ thứ tự cấp sequence/đồng hồ.

### Trường hợp nguồn chỉ gửi snapshot

Nếu gateway gửi toàn bộ 100 phép đo gần nhất theo chu kỳ và lần sau chỉ còn 90, **không** được tự coi 10 ID mất khỏi snapshot là 10 phép đo bị xóa khi chưa biết đó là snapshot **đầy đủ, cùng phạm vi và được nguồn xác nhận**. Trong nhiều giao thức, snapshot chỉ là “100 bản gần đây nhất”, không phản ánh trạng thái tồn tại của toàn lịch sử.

## 14. Tối ưu vật lý: partition, chỉ mục, retention và tái tạo

Hệ chuỗi thời gian có thể chứa hàng tỷ phép đo. Thêm revision history và current table sẽ tăng dung lượng, nên phải tối ưu theo truy vấn thật.

| Bài toán truy vấn | Cấu trúc gợi ý | Đánh đổi |
| --- | --- | --- |
| Tìm lịch sử correction của một measurement | Khóa `tenant, source, sensor, measurement_id, revision`. | PK composite có thể dài; cần chuẩn hóa ID. |
| Đọc nhiệt độ hiện hành theo sensor/thời gian | Index `tenant, sensor, measured_at` có lọc bản hợp lệ. | Ingest/correction cập nhật index; phải đo độ chọn lọc. |
| Tổng hợp theo phút/giờ/ngày | Aggregate materialized hoặc time-series rollup. | Cần tính lại khi late/correction, có version/lag. |
| Scan hàng tháng dữ liệu nhiều cảm biến | Partition/time-series chunks theo `measured_at`. | Sửa timestamp có thể chuyển partition; unique cross-partition có giới hạn tùy hệ quản trị. |
| Audit dữ liệu nhận ở một kỳ | Lưu `received_at`/`recorded_at` và lineage. | Phải xác định có cần giữ mọi lần truyền lại không. |
| Phục vụ BI dài hạn | Kho phân tích columnar, dữ liệu theo grain/metric rõ. | Backfill, retention, schema evolution và xác nhận số liệu. |

### Phân vùng cần xét khóa duy nhất

PostgreSQL có quy tắc ràng buộc unique/primary key trên bảng partitioned: một khóa unique trên bảng phân vùng thông thường phải bao gồm các cột partition key phù hợp. Nếu phân vùng `measurement_revision` theo `measured_at` mà vẫn muốn **ID phép đo + revision duy nhất không phụ thuộc thời gian**, có thể không tạo được unique toàn cục theo ý muốn bằng một constraint partition đơn giản.

Một giải pháp là **giữ bảng danh tính/receipt riêng** với unique toàn phạm vi, sau đó partition lịch sử theo thời gian; hoặc chọn công nghệ và chiến lược phân vùng khác với bảo đảm phù hợp. Đừng “chữa” bằng cách thêm `measured_at` vào khóa unique rồi vô tình cho phép cùng measurement/revision bị ghi nhiều lần ở hai mốc khác nhau.

### Retention của lịch sử và aggregate

- **Current** có thể giữ bản hiệu lực/tombstone cần thiết để không tái sinh revision cũ.
- **Revision history** có thời hạn lưu theo nhu cầu audit và sửa sai; nếu xóa revision cũ, việc replay/giải thích correction có thể bị giới hạn.
- **Landing raw** và bản tin retry có thể có thời hạn ngắn hơn history đã chuẩn hóa, tùy policy và yêu cầu đối soát.
- **Rollup** có thể giữ lâu hơn dữ liệu thô, nhưng không thể tái tạo một metric mới nếu dữ liệu chi tiết đã bị loại.
- **Snapshot/backup** phải nằm trong chính sách lưu giữ và quyền riêng tư; không coi dữ liệu đã xóa ở current là đã biến mất khỏi mọi bản sao.

Nếu một bản correction đến sau khi dữ liệu gốc đã vượt thời hạn giữ, chính sách phải nêu: có còn cho phép sửa? Có lưu tombstone/receipt và đối chiếu nguồn không? Có phải đánh dấu giới hạn tính chính xác của báo cáo cũ? Không được tự tuyên bố có thể rebuild toàn bộ khi không còn chi tiết cần thiết.

## 15. Chất lượng dữ liệu, an ninh và trách nhiệm nguồn

Một bản đo có vẻ hợp lệ về JSON không đảm bảo đúng về vật lý.

### Kiểm tra lúc ingest

- **Identity:** measurement key đầy đủ, không gộp hai sensor/tenant/nguồn khác nhau.
- **Clock drift:** `measured_at` nằm quá xa tương lai/quá khứ so với chính sách, có thể cách ly để hiệu chỉnh; không tự sửa timestamp rồi mất dấu nguồn.
- **Unit/scale:** giá trị `6,5 CELSIUS` khác `6,5 FAHRENHEIT`; việc đổi đơn vị phải được ghi bằng hợp đồng chuyển đổi.
- **Range:** đánh giá giá trị nằm ngoài giới hạn cảm biến; phân biệt dữ liệu sai với sự cố nhiệt độ thực tế.
- **Revision:** monotonic theo key, quyền hiệu chỉnh và lý do; payload xung đột cùng revision phải báo lỗi.
- **Sequence gaps:** phát hiện số thứ tự thiếu nếu giao thức có device sequence; không suy ra có mẫu thiếu chỉ vì khoảng thời gian không đều với thiết bị đo theo yêu cầu.
- **Tenant isolation:** mọi lookup, khóa, truy vấn và báo cáo phải có tenant/source scope phù hợp.
- **Không bỏ dấu correction:** có nguồn và actor/thiết bị xác nhận; dữ liệu sửa phải giải thích được.

### Quyền riêng tư

Time series không luôn là dữ liệu “không nhạy cảm”. Dữ liệu vị trí GPS, hành vi sử dụng thiết bị, đồng hồ thông minh hoặc lịch hoạt động có thể suy ra thông tin cá nhân. Cần phân quyền theo chủ thể, hạn chế metadata trực tiếp định danh, quản lý retention, xóa/ẩn danh có kiểm soát và đánh giá mọi bản sao trong raw/history/rollup/search/backup.

Không coi `hash(sensor_id)` hoặc bỏ tên người dùng là đủ ẩn danh khi chuỗi thời gian vẫn có thể liên kết với thiết bị/người. Mọi exception về xóa dữ liệu để giữ audit phải có căn cứ và chính sách riêng.

## 16. Quan sát hệ thống: đo chất lượng và độ trễ thực tế

Bộ chỉ số nên phản ánh cả **pipeline** lẫn **độ tin cậy của dữ liệu**:

| Metric | Ý nghĩa | Cần cảnh giác |
| --- | --- | --- |
| `ingest_lag = received_at - measured_at` | Độ trễ từ đo đến nhận. | Âm bất thường có thể do clock skew; không tự dùng timestamp không tin cậy để đo SLA. |
| `processing_lag` | Độ trễ từ nhận đến projection sẵn sàng. | Trung bình che mất đuôi P95/P99. |
| `duplicate_rate` | Tỷ lệ message lặp theo ID/revision. | Không tính hai mẫu trùng timestamp là duplicate. |
| `revision_conflict_count` | Số trường hợp cùng ID/revision khác payload. | Cần phân nhóm theo nguồn/thiết bị và điều tra. |
| `late_event_rate` | Tỷ lệ sự kiện có event-time nằm trước watermark/cửa sổ đã chốt. | Phụ thuộc policy watermark, không phải tỷ lệ sai đo. |
| `correction_rate` | Bao nhiêu measurement key có revision mới/correction. | Phân biệt hiệu chuẩn, sửa timestamp, xóa invalid. |
| `retraction_rate` | Số mẫu bị vô hiệu hóa có căn cứ. | Không tự coi retraction là giá trị 0. |
| `bucket_drift` | Sai lệch giữa rollup và recompute từ current. | Cần kiểm chứng ở một mốc dữ liệu nhất quán. |
| `missing_sequence_count` | Số gaps theo device sequence được bảo đảm. | Không áp dụng cho thiết bị không có sequence liên tục. |

### Phép kiểm chứng dữ liệu

Truy vấn tìm những measurement key có revision lớn hơn một:

~~~sql
SELECT tenant_id, source_system, sensor_id, measurement_id,
       COUNT(*) AS revisions_received,
       MAX(source_revision) AS latest_revision
FROM measurement_revision
WHERE tenant_id = :tenant_id
GROUP BY tenant_id, source_system, sensor_id, measurement_id
HAVING COUNT(*) > 1;
~~~

Truy vấn tìm bản current sai version so với history **tại một mốc dữ liệu đã được đồng bộ**:

~~~sql
WITH latest AS (
    SELECT tenant_id, source_system, sensor_id,
           measurement_id,
           MAX(source_revision) AS max_revision
    FROM measurement_revision
    WHERE tenant_id = :tenant_id
    GROUP BY tenant_id, source_system, sensor_id, measurement_id
)
SELECT l.*
FROM latest l
LEFT JOIN measurement_current c
  ON c.tenant_id = l.tenant_id
 AND c.source_system = l.source_system
 AND c.sensor_id = l.sensor_id
 AND c.measurement_id = l.measurement_id
WHERE c.source_revision IS DISTINCT FROM l.max_revision;
~~~

Nếu pipeline cho phép lưu **revision chờ xác minh** trước khi cập nhật current, truy vấn thứ hai sẽ xuất hiện sai khác hợp lệ. Khi đó cần thêm trạng thái `accepted/pending/rejected` trong revision history và chỉ so với revision **đã được chấp nhận**; ví dụ schema ở đây giả định mọi revision đã ghi là hợp lệ, không có vùng chờ.

Ngoài version, nên đối chiếu tập sample trong current với aggregate recompute theo bucket, unit, quality; kiểm tra `SUM`, `COUNT` và các ca chuyển bucket/retract. Những so sánh này cần dùng **cùng mốc chốt dữ liệu**, không so hai bảng đang cập nhật ở hai thời điểm rồi kết luận drift.

## 17. Những lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `UNIQUE(sensor_id, measured_at)` cho mọi time series | Mất hai phép đo hợp lệ có cùng timestamp. | Xác định grain và measurement ID/slot chính xác. |
| Coi hai payload giống nhau nhưng khác ID là duplicate chắc chắn | Có thể xóa phép đo độc lập. | Dedupe bằng định danh nguồn/contract, không đoán chỉ từ value/time. |
| Chọn “bản nhận sau thắng” | Message cũ đến trễ ghi đè correction mới. | Revision/cursor nguồn có thẩm quyền. |
| Không lưu tombstone sau retraction | Revision cũ đến trễ có thể phục hồi mẫu đã hủy. | Current lưu trạng thái RETRACT và revision mới nhất. |
| Nhận retry rồi cộng vào SUM/COUNT lần nữa | Trung bình và số sự kiện bị sai. | Idempotency theo key+revision, commit aggregate cùng current. |
| Correction được xem như phép đo mới | Nhân mẫu, không thay đóng góp cũ. | Trừ old contribution, cộng new contribution. |
| Điều chỉnh timestamp mà chỉ sửa bucket mới | Bucket cũ còn dữ liệu thừa. | Recompute hoặc cập nhật cả bucket cũ và mới. |
| Dùng `received_at` để nhóm nhiệt độ theo thời gian thực tế | Dữ liệu offline bị chuyển sang sai giờ. | Event-time window theo `measured_at`. |
| Coi watermark là không còn late data | Bỏ dữ liệu hợp lệ sau khi chốt. | Allowed lateness và chính sách restatement/exception. |
| Dùng `SUM(counter_value)` làm tổng tiêu thụ | Đếm lặp số tích lũy. | Chênh lệch counter, kiểm tra reset/wrap và thứ tự. |
| Dùng `AVG(AVG(...))` khi nhóm có số mẫu khác nhau | Trung bình toàn kỳ sai. | Tính từ total sum/count hoặc trọng số đúng. |
| Gộp °C với °F trong aggregate | KPI vô nghĩa. | Chuẩn hóa đơn vị và version quy tắc. |
| Chỉ cập nhật current, bỏ quên rollup đã materialize | Báo cáo cũ sai sau correction. | Delta/recompute + đối soát và invalidation. |
| Partition theo timestamp rồi mất unique ID logic | Hai revision cùng danh tính có thể xuất hiện ở partition khác nhau. | Thiết kế constraint/receipt ngoài partition. |
| Giữ mỗi rollup rồi hứa có thể replay mọi metric | Không đủ dữ liệu lịch sử cho công thức mới. | Retention và cam kết khả năng tái tạo rõ ràng. |

## 18. Bài tập thực hành: số đo kho lạnh đến trễ và hiệu chuẩn hồi tố

**Bối cảnh:** hai cảm biến `SEN-A` và `SEN-B` trong kho lạnh gửi số đo có timestamp UTC độ phân giải giây. Gateway có thể offline và gửi lại batch. Một đội hiệu chuẩn được phép phát revision mới hoặc retraction. Dashboard hiển thị trung bình nhiệt độ theo cửa sổ 15 phút, số mẫu hợp lệ và các lần vượt ngưỡng.

Dữ liệu nhận theo **thứ tự đến máy chủ**:

| Thứ tự nhận | Sensor | measurement_id | Revision | measured_at | Giá trị | Operation |
| ---: | --- | --- | ---: | --- | ---: | --- |
| 1 | SEN-A | A-01 | 1 | 10:01:00 | 7,0 | UPSERT |
| 2 | SEN-A | A-02 | 1 | 10:01:00 | 9,0 | UPSERT |
| 3 | SEN-A | A-01 | 1 | 10:01:00 | 7,0 | UPSERT (retry) |
| 4 | SEN-A | A-01 | 3 | 10:01:00 | 6,5 | UPSERT (calibrated) |
| 5 | SEN-A | A-01 | 2 | 10:01:00 | 6,8 | UPSERT (late revision) |
| 6 | SEN-A | A-03 | 1 | 09:59:00 | 5,0 | UPSERT (late sample) |
| 7 | SEN-B | B-01 | 1 | 10:01:00 | 4,0 | UPSERT |
| 8 | SEN-A | A-02 | 2 | 10:01:00 | Không có | RETRACT |

Giả định mọi mẫu UPSERT có `quality_code = ACCEPTED`, cùng đơn vị `CELSIUS`; revision là **full-state** và tăng theo measurement key. Dữ liệu là tình huống kỹ thuật, không phải chỉ dẫn mức nhiệt độ an toàn.

### Yêu cầu

1. **Định nghĩa grain:** nêu khóa `(tenant, source, sensor, measurement_id)`. Vì sao hai mẫu A-01/A-02 có cùng measured_at vẫn phải lưu riêng?
2. **Phân biệt hai trục thời gian:** với A-03, thời điểm đo 09:59 và nhận sau 10:01. Nó thuộc bucket nào? Truy vấn đo độ trễ dùng mốc nào?
3. **Xác định current:** sau cả tám message, revision hiệu lực và trạng thái của A-01, A-02, A-03 và B-01 là gì?
4. **Tính aggregate theo sensor:** SEN-A bucket `[10:00, 10:15)` còn bao nhiêu mẫu hợp lệ, sum và average bao nhiêu? SEN-A bucket `[09:45, 10:00)` có gì? Không trộn SEN-B vào SEN-A.
5. **Retry và out-of-order:** vì sao nhận lần 3 không tạo mẫu mới; revision 2 đến sau revision 3 không được ghi đè 3?
6. **Retraction:** vì sao A-02 vẫn cần một hàng tombstone rev 2 trong current mà không nên xóa hoàn toàn key?
7. **Lược đồ:** thiết kế `measurement_revision` và `measurement_current` cùng ràng buộc unique, FK và index thời gian; không dùng timestamp làm PK.
8. **SQL:** viết truy vấn lấy latest revision trên mỗi key, nhóm các current UPSERT/ACCEPTED theo `date_bin` 15 phút, phân tách đơn vị.
9. **Worker concurrency:** hai worker đồng thời nhận correction A-01 rev 4. Đề xuất khóa hoặc CAS, xử lý conflicting payload và commit delta aggregate.
10. **Chuyển timestamp:** rev 4 của A-01 sửa measured_at từ 10:01 thành 09:59. Những bucket nào phải thay, kiểm tra kết quả thế nào?
11. **Watermark:** khi A-03 đến sau khi cửa sổ 09:45 đã finalized, đề xuất quy trình restatement/exception có chủ đích.
12. **Thiết bị counter:** một đồng hồ điện năng tích lũy có giá trị 100, 110, 125 rồi reset về 3. Giải thích vì sao `SUM(values)` không là điện năng tiêu thụ, và correction/late event ảnh hưởng delta thế nào.
13. **Báo cáo phiên bản:** nếu dashboard từng công bố trung bình trước correction, bạn sẽ lưu metadata gì để sau này giải thích sự thay đổi?
14. **Vận hành/retention:** chọn chỉ số lag, duplicate rate, conflict rate, bucket drift; nêu ảnh hưởng khi dữ liệu thô đã hết hạn lưu nhưng có correction.

### Gợi ý kiểm chứng định lượng

Với các giả định trên, sau khi xử lý toàn bộ dữ liệu:

- `SEN-A`, cửa sổ **10:00–10:15** chỉ còn A-01 rev 3 = **6,5 °C** vì A-02 đã bị rút; **count = 1, sum = 6,5, average = 6,5 °C**.
- `SEN-A`, cửa sổ **09:45–10:00** có A-03 = **5,0 °C**; **count = 1**.
- `SEN-B`, cửa sổ **10:00–10:15** có B-01 = **4,0 °C**; **count = 1**.
- A-01 rev 2 đến muộn vẫn có thể được lưu trong revision history, nhưng **current giữ rev 3**, không có phép tính nào cộng lại giá trị 6,8.
- A-02 current giữ `operation = RETRACT`, không đóng góp số mẫu hay tổng. Mọi bản A-02 revision 1 đến lại sau đó đều bị từ chối làm bản hiệu lực.

### Bảng kiểm tự đánh giá

| Tiêu chí | Kết quả đạt |
| --- | --- |
| **Grain** | Không gộp hai phép đo độc lập chỉ vì trùng thời gian. |
| **Dedup** | Retry cùng revision không thêm mẫu, không cập nhật aggregate lần hai. |
| **Thứ tự** | Bản revision cũ không ghi đè current mới hơn; conflict cùng revision được phát hiện. |
| **Correction** | Đúng cả việc sửa value, measured_at, quality và RETRACT. |
| **Thời gian** | Event-time bucket khác processing-time; có chính sách watermark/late data. |
| **Toán học** | SUM/COUNT/AVG dùng đúng grain và loại metric; không cộng counter hoặc nhiều đơn vị bừa bãi. |
| **Nhất quán** | Revision history, current, summary và checkpoint có biên transaction/idempotency rõ. |
| **Tái tạo** | Có thể đối chiếu summary từ current ở một mốc nhất quán; mô tả giới hạn retention. |
| **Bảo mật** | Tenant/source namespace, quyền hiệu chỉnh, dữ liệu nhạy cảm và lịch sử sửa được quản trị. |

**Kết luận:** xử lý dữ liệu chuỗi thời gian đáng tin bắt đầu bằng việc **tách danh tính phép đo khỏi timestamp**, tách **thời gian đo khỏi thời gian nhận**, và phân biệt **message lặp, hai phép đo trùng mốc, revision sửa sai và retraction**. Dữ liệu đến trễ phải được gắn đúng cửa sổ nghiệp vụ; correction phải thay đóng góp cũ chứ không sinh thêm mẫu; tổng hợp đã công bố cần chính sách restatement có thể kiểm chứng. Dù chọn cơ sở dữ liệu quan hệ, time-series, document hay kho phân tích, những quy tắc này mới là nền tảng để dữ liệu dễ tiến hóa, kiểm toán và sử dụng đúng.
