# Windows, watermarks, triggers và late data trong Dataflow

Một hệ thống bán lẻ nhận sự kiện `order.paid` từ **Cloud Run**, chuyển qua **Pub/Sub** rồi dùng **Dataflow** tổng hợp doanh thu theo sản phẩm mỗi 5 phút để hiển thị trong **BigQuery**. Một điện thoại mất kết nối lúc 10:02, đến 10:14 mới gửi sự kiện phát sinh lúc 10:02. Nếu tính theo thời gian nhận, đơn hàng bị đưa vào kỳ 10:10–10:15; nếu tính theo thời gian phát sinh, nó thuộc kỳ 10:00–10:05. Khi báo cáo 10:00–10:05 đã được xuất bản thì cần làm gì với sự kiện đến trễ?

**Apache Beam** là mô hình lập trình pipeline; **Dataflow** là dịch vụ Google Cloud thực thi pipeline Beam. Bốn khái niệm phối hợp để giải quyết bài toán streaming không có điểm kết thúc:

- **Window**: chia dữ liệu theo các khoảng thời gian hoặc phiên hoạt động.
- **Watermark**: ước lượng tiến độ xử lý theo *event time*, cho biết hệ thống tin rằng phần lớn sự kiện cũ đã tới.
- **Trigger**: quyết định lúc nào xuất kết quả của một window.
- **Late data**: sự kiện tới sau khi watermark đã đi qua mốc đóng window; cách xử lý phụ thuộc `allowed_lateness` và trigger.

Bài học thuộc chương **Pipeline và xử lý dữ liệu**, mô-đun **CLOUD_PROVIDERS_GCP**, gắn với Pub/Sub, Cloud Run, GKE, BigQuery, IAM, tự động hóa phát hành, quan sát độ tin cậy và chi phí. Ví dụ dùng Python Apache Beam và dữ liệu giả; mục tiêu là hiểu đúng ngữ nghĩa chứ không chỉ chạy được một lệnh Dataflow.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **event time**, **processing time**, **Pub/Sub publish time** và **window timestamp**.
2. Chọn **fixed**, **sliding** hoặc **session windows** cho từng loại báo cáo.
3. Giải thích watermark là **ước lượng**, không phải lời hứa không còn sự kiện cũ.
4. Thiết kế trigger **early/on-time/late** và chọn **accumulating** hay **discarding panes**.
5. Cấu hình `allowed_lateness`, xác định khi dữ liệu không còn được giữ trong state của window.
6. Thử nghiệm bằng `TestStream`, thiết kế Pub/Sub ingestion, Dataflow monitoring và sink BigQuery chống ghi trùng.
7. Đánh đổi giữa **độ mới dữ liệu, độ hoàn chỉnh, state, chi phí** và yêu cầu SLO nghiệp vụ.

## 2. Bốn trục thời gian và kiến trúc tổng quan

### 2.1. Event time không phải processing time

| Thời gian | Định nghĩa | Ví dụ của sự kiện thanh toán |
| --- | --- | --- |
| **Event time** | Thời điểm sự kiện **thực sự xảy ra** theo nguồn dữ liệu. | `10:02:10`, do hệ thống thanh toán phát sinh. |
| **Pub/Sub publish time** | Thời điểm Pub/Sub nhận/publish message. | `10:14:00` sau khi thiết bị kết nối lại. |
| **Processing time** | Thời điểm worker Dataflow xử lý message tại một step. | `10:14:03`. |
| **Window interval** | Khoảng event-time mà Beam gán phần tử vào. | `[10:00, 10:05)` nếu dùng fixed window 5 phút. |

Không mặc nhiên lấy thời gian HTTP server nhận request làm event time. Nguồn phát có thể sai đồng hồ hoặc replay sự kiện rất cũ: cần xác định **nguồn thời gian được tin cậy**, chuẩn hóa UTC, kiểm tra clock skew và lưu cả `event_time` lẫn `ingested_at` khi cần kiểm toán.

~~~mermaid
flowchart LR
    SRC["Cloud Run / IoT: sự kiện + event_time"] --> PS["Pub/Sub"]
    PS --> BEAM["Dataflow: gán timestamp"]
    BEAM --> WIN["WindowInto: 5 phút"]
    WIN --> AGG["Group/Combine theo SKU"]
    AGG --> TR["Trigger: early, on-time, late"]
    TR --> SINK["BigQuery: pane/revision"]
    MON["Cloud Monitoring"] -. "Watermark, lag, lỗi, chi phí" .-> BEAM
~~~

Một event có thể đến muộn do thiết bị offline, network retry, Pub/Sub backlog hoặc một stage chậm; không phải mọi sự kiện có timestamp cũ đều là duplicate. **Deduplication** và **late-data handling** là hai bài toán khác nhau.

### 2.2. Unbounded collection cần window để tổng hợp

Pub/Sub là nguồn **không giới hạn** (*unbounded*), nên không thể đợi “nhận hết mọi đơn hàng” trước khi `GroupByKey`/`CombinePerKey`. Beam chia dữ liệu thành các window hữu hạn hoặc dùng trigger phù hợp với `GlobalWindow`. Ngược lại, file/batch hữu hạn có thể hoàn tất toàn bộ job rồi tổng hợp mà không cần thời gian thực.

**Ví dụ phân biệt:**

- Đếm tổng đơn hàng của **một ngày đã kết thúc** từ Cloud Storage là batch.
- Đếm số đơn **trong mỗi 5 phút, cập nhật liên tục** từ Pub/Sub là streaming.
- Cùng một SQL `GROUP BY sku` chưa nói được cách xử lý cửa sổ, watermark và event muộn; những quy tắc này nằm trong semantics của pipeline.

## 3. Chọn window: fixed, sliding và session

### 3.1. Fixed (tumbling) windows

**Fixed window dài 5 phút** chia trục event-time thành các khoảng không chồng lấn:

~~~text
10:00           10:05           10:10           10:15
|------- W1 -------|------- W2 -------|------- W3 -------|
      10:02 → W1        10:06 → W2        10:14 → W3
~~~

Window thường dùng khoảng **nửa mở** `[start, end)`: sự kiện lúc **10:05:00** thuộc W2, không thuộc W1. Với Beam Python:

~~~python
import apache_beam as beam
from apache_beam.transforms.window import FixedWindows

# Dùng sau PCollection có timestamps đúng.
windowed = events | "FiveMinuteWindows" >> beam.WindowInto(
    FixedWindows(5 * 60))
~~~

Phù hợp báo cáo theo các kỳ rời rạc: số đơn/5 phút, doanh thu/ngày, SLA/giờ. Nếu cần ranh giới theo **múi giờ địa phương** hoặc lịch kinh doanh, phải kiểm tra loại window và timezone; fixed windows theo seconds không tự hiểu daylight saving hoặc “ngày theo Việt Nam”.

### 3.2. Sliding windows

**Sliding window dài 10 phút, trượt mỗi 5 phút** cho báo cáo “10 phút gần đây, cập nhật 5 phút/lần”. Các windows **chồng lấn**, nên **một event có thể thuộc nhiều windows**:

~~~text
Window A: [10:00, 10:10)
Window B:       [10:05, 10:15)
Event 10:07 → thuộc A và B.
~~~

~~~python
from apache_beam.transforms.window import SlidingWindows

windowed = events | "RollingTenMinutes" >> beam.WindowInto(
    SlidingWindows(size=10 * 60, period=5 * 60))
~~~

**Không cộng trực tiếp totals của A và B** để tính tổng 10:00–10:15: event 10:07 đã xuất hiện hai lần. Các tổ hợp window dài/chu kỳ ngắn có thể làm **state, số panes và chi phí** tăng mạnh; cần benchmark.

### 3.3. Session windows

**Session window** nhóm những events có cùng **key** khi khoảng cách giữa các events không vượt ngưỡng nhàn rỗi (*gap*). Phù hợp clickstream theo `session_id`/`customer_id`, hành vi thiết bị hoặc tương tác giỏ hàng.

~~~python
from apache_beam.transforms.window import Sessions

# Group theo key ở bước sau WindowInto.
windowed = events_by_customer | "SessionsFiveMinutes" >> beam.WindowInto(
    Sessions(gap_size=5 * 60))
~~~

Nếu khách A tương tác lúc 10:00, 10:03 và 10:07, các events có thể nối thành một session; một event đến trễ có thể **nối hai sessions từng được xem là riêng**. Session windows là **merging windows**; thiết kế output/upsert và event-time correctness khó hơn fixed windows, đặc biệt khi đã phát early results. Không sử dụng session gap như timeout đăng nhập bảo mật trừ khi nghiệp vụ đã định nghĩa riêng.

| Loại | Event thuộc bao nhiêu windows? | Khi dùng | Cạm bẫy |
| --- | --- | --- | --- |
| Fixed | Một window cho một bộ tham số windowing. | Báo cáo kỳ 5 phút. | Trễ đến sau watermark, dữ liệu bù. |
| Sliding | Có thể nhiều windows. | Rolling metrics. | Đếm trùng khi cộng các windows chồng nhau. |
| Session | Window theo key, có thể merge. | Hành vi người dùng/thiết bị. | Window boundaries thay đổi khi late events tới. |

## 4. Watermark: ước lượng tiến độ event time

### 4.1. Watermark mang nghĩa gì?

Watermark `W = 10:05` là ước lượng của pipeline/source rằng những events có event-time **trước mốc đó** phần lớn đã đi qua phần xử lý liên quan. Watermark **không phải** một tập cam kết rằng *mọi* sự kiện cũ đã xuất hiện. Một message với event-time 10:02 đến khi watermark đã vượt 10:05 sẽ là **late** đối với fixed window `[10:00,10:05)`.

~~~text
Event time ──────────────────────────────────────────>
10:00             10:05             10:10
|---- Window A ----|---- Window B ----|
                   ^
                 watermark

Message (event_time 10:02) tới sau mốc này ⇒ late đối với A.
~~~

Watermark của **một step** chịu ảnh hưởng nguồn và các bước phía trước; stage chậm, backlog, timer/state hoặc nguồn ít traffic có thể giữ watermark không tiến. Một pipeline có nhiều Pub/Sub sources có thể bị ảnh hưởng bởi **nguồn rất ít message hoặc idle**. Đọc `data watermark lag`, `system lag` và traffic cùng nhau để xác định nguyên nhân.

### 4.2. Watermark không phải allowed lateness

| Cơ chế | Trả lời câu hỏi |
| --- | --- |
| Watermark | “Hệ thống **ước lượng** dữ liệu cũ đã tới đến đâu?” |
| Trigger | “Khi nào xuất một **pane kết quả**?” |
| Allowed lateness | “Sau mốc cuối window, **giữ state và chấp nhận late events** tới ngưỡng watermark nào?” |
| Pub/Sub retention | “Message còn tồn tại ở nguồn bao lâu trước khi bị xóa theo policy?” |

**Allowed lateness không phải số phút tính từ lúc worker nhận message**, cũng không phải thời gian lưu ở Pub/Sub. Một ví dụ: window `[10:00,10:05)` với `allowed_lateness=10 phút` có thể nhận late data đến khi **watermark đi qua khoảng 10:15**. Nếu processing time bây giờ là 10:20 nhưng watermark vẫn dừng ở 10:06, event-time window chưa hết hạn theo ngưỡng đó.

### 4.3. Nguồn Pub/Sub quyết định event timestamp

Theo cấu hình mặc định, `ReadFromPubSub` thường dùng **Pub/Sub publish time** làm timestamp phần tử. Khi dùng `timestamp_attribute="event_time"`, connector đọc timestamp do publisher gắn trong attribute, thay vì publish time. Format hỗ trợ gồm **RFC 3339 UTC** hoặc **milliseconds từ Unix epoch**. Ví dụ:

~~~json
{
  "data": {"event_id": "evt-123", "sku": "SKU-A", "amount_vnd": 120000},
  "attributes": {"event_time": "2026-11-19T10:02:10Z", "event_id": "evt-123"}
}
~~~

Đoạn trên là **biểu diễn khái niệm** của Pub/Sub message, không phải một payload JSON duy nhất gửi nguyên cho Pub/Sub API: `data` và `attributes` là hai thành phần riêng. Với event time từ thiết bị, cần xác thực timestamp/clock skew; attribute sai format hoặc quá cũ có thể làm pipeline lỗi hoặc trì hoãn watermark.

Khi Dataflow sử dụng timestamp attribute, connector có thể tạo **tracking subscription** để ước lượng event-time backlog. Vì vậy service account của Dataflow có thể cần thêm quyền quản lý tracking subscription và gắn vào topic, ngoài quyền consume dữ liệu. Tham khảo [Read from Pub/Sub to Dataflow](https://cloud.google.com/dataflow/docs/concepts/streaming-with-cloud-pubsub).

## 5. Triggers: xuất kết quả trước và sau watermark

### 5.1. Trigger tạo một hoặc nhiều panes

Mặc định, Beam chờ watermark đi qua **cuối window** rồi xuất kết quả tổng hợp. Nhưng dashboard muốn ước lượng trong lúc window chưa kết thúc có thể chọn **early firing**. Sự kiện đến muộn được chấp nhận có thể phát **late firing** để cập nhật báo cáo. Mỗi lần trigger phát ra một **pane**: một phiên bản hoặc phần cập nhật của kết quả cho cặp `(key, window)`.

| Loại firing | Điều kiện minh họa | Ý nghĩa cho dashboard |
| --- | --- | --- |
| **EARLY** | 20 giây processing time từ phần tử đầu trong pane. | Số liệu **tạm**, chưa đủ mọi event. |
| **ON_TIME** | Watermark đi qua window end. | Kết quả tại thời điểm hệ thống **ước lượng đã đủ**. |
| **LATE** | Event muộn tới trong thời hạn cho phép. | Điều chỉnh số liệu từng xuất bản. |

**ON_TIME không đồng nghĩa final tuyệt đối** nếu có allowed lateness hoặc nguồn replay về sau. Pane có thể có metadata như **`PaneInfo.timing`**, `index`, `is_first`, `is_last`; chúng hữu ích cho logs và sink, nhưng **không phải transaction ID bất biến xuyên các lần chạy lại toàn pipeline**.

### 5.2. Những loại trigger chính

| Trigger Beam | Theo thời gian/sự kiện nào? | Khi dùng |
| --- | --- | --- |
| `AfterWatermark` | Event time/watermark. | Bản kết quả on-time. |
| `AfterProcessingTime(delay=...)` | Đồng hồ xử lý, tính từ lúc pane nhận phần tử đầu tiên. | Cập nhật tạm sớm dù event-time window chưa kết thúc. |
| `AfterCount(n)` | Số phần tử. | Xuất pane sau N messages. |
| `AfterAny`, `AfterAll`, `Repeatedly` | Kết hợp điều kiện. | Cân bằng ngưỡng số lượng và thời gian, theo runner hỗ trợ. |

Một thiết kế thường gặp:

~~~python
from apache_beam.transforms.trigger import (
    AfterWatermark, AfterProcessingTime, AfterCount, AccumulationMode)
from apache_beam.transforms.window import FixedWindows
import apache_beam as beam

windowed = events | "WindowsWithEarlyLateUpdates" >> beam.WindowInto(
    FixedWindows(5 * 60),
    trigger=AfterWatermark(
        early=AfterProcessingTime(delay=30),
        late=AfterCount(1)),
    allowed_lateness=10 * 60,
    accumulation_mode=AccumulationMode.ACCUMULATING)
~~~

Diễn giải: khi có dữ liệu, Beam có thể xuất **early pane** sau 30 giây processing time, xuất **on-time pane** khi watermark qua cuối window, rồi phát lại kết quả khi late element đến trong giới hạn 10 phút. Không dự đoán chính xác số early panes chỉ bằng công thức: xử lý song song, thời điểm có phần tử đầu, trigger kết hợp và đặc điểm runner ảnh hưởng tới panes thực tế. Khi chỉ cần kết quả sau watermark, **cấu hình mặc định đơn giản hơn** và thường ít chi phí state/output hơn.

### 5.3. Trigger khác timeout và lịch cron

- `AfterProcessingTime(30)` không phải “chạy đúng giây thứ 30 của mỗi phút”; nó dựa trên thời điểm processing của phần tử ở pane.
- `AfterCount(100)` không đảm bảo có kết quả nếu pane mới có 99 phần tử mà không có trigger khác; cần composite trigger nếu phải giới hạn thời gian chờ.
- Cloud Scheduler tạo **cron job**; không thay thế Beam trigger cho window streaming.
- Trigger có thể phát **nhiều outputs cho cùng key/window**, nên downstream phải biết output nào là tạm, output nào bù.

## 6. Accumulating và discarding: kết quả là tổng hay phần tăng?

### 6.1. Ví dụ minh họa một window

Giả sử `SKU-A` ở window `[10:00,10:05)` có:

| Lúc tới pipeline | Event time | Giá trị đơn (nghìn VND) | Trạng thái |
| --- | --- | ---: | --- |
| 10:01 | 10:00:30 | 100 | Đến sớm. |
| 10:02 | 10:01:10 | 50 | Đến sớm. |
| 10:06 | 10:03:40 | 50 | Đến trước on-time firing theo watermark giả định. |
| 10:09 | 10:02:00 | 20 | Đến sau watermark qua 10:05: **late**. |

Giả sử có ba firings được chọn để minh họa: **early** sau hai events đầu, **on-time** sau event thứ ba và **late** sau event thứ tư. Kết quả:

| Pane | `ACCUMULATING` | `DISCARDING` |
| --- | ---: | ---: |
| EARLY | 150 | 150 |
| ON_TIME | **200** (150 + 50) | **50** mới từ pane trước |
| LATE | **220** (200 + 20) | **20** mới từ pane trước |

Đơn vị là nghìn VND. Với **accumulating**, mỗi firing thể hiện số liệu **tổng tích lũy** cho key/window tới thời điểm đó; với **discarding**, pane sau chỉ có phần tử **chưa từng được đưa vào pane trước**. Trong ví dụ, cộng `150 + 200 + 220 = 570` là **sai** nếu mục tiêu là tổng doanh thu cuối: tổng đúng theo bốn events là **220**.

### 6.2. Chọn theo hợp đồng sink

| Chế độ | Khi phù hợp | Trách nhiệm downstream |
| --- | --- | --- |
| `ACCUMULATING` | Dashboard muốn bản **total mới nhất** theo `(window, key)`. | Upsert/replace phiên bản cũ; không cộng tất cả panes. |
| `DISCARDING` | Sink cần **delta** cho mỗi firing. | Cộng có idempotency, chống ghi trùng pane/delivery. |
| `ACCUMULATING_AND_RETRACTING` | Một số runner/SDK hỗ trợ retraction để sửa phiên bản trước. | Cần xác minh tính năng/khả năng sink theo SDK; không mặc định Dataflow Python dùng được. |

Không xem việc Dataflow xử lý một input message một lần là bảo đảm BigQuery ghi **một aggregate row**: trigger tự có thể phát nhiều panes. **Exactly-once processing, output semantics và exactly-once side effects là ba lớp khác nhau**.

## 7. Allowed lateness, dữ liệu quá hạn và giữ state

### 7.1. Hạn chấp nhận theo watermark

Với window `[10:00,10:05)` và `allowed_lateness=10 phút`, runner có thể giữ state của key/window để xử lý late data cho tới khi **watermark tiến qua mốc `10:15`**. Sau giới hạn đó, dữ liệu đến quá muộn **không thể kỳ vọng cập nhật kết quả window cũ** trong transform tương ứng.

~~~text
Window A: [10:00, 10:05)
                          watermark = 10:05 → on-time có thể fire
             [10:05, 10:15] → thời gian event-time cho late data
                          watermark > 10:15 → window state đủ điều kiện GC
~~~

Trong thực tế, watermark có thể tiến không đều; thời gian mà state tồn tại theo **wall clock** có thể dài hơn 10 phút. **Allowed lateness tăng chi phí giữ state**, làm sink nhận nhiều bản hiệu chỉnh và tăng thời gian trước khi coi một window đã ổn định. `allowed_lateness=0` thường là mặc định: late events không được tổng hợp lại vào window đó.

### 7.2. Retention ở Pub/Sub độc lập với window state

Một subscription Pub/Sub có thể giữ message chưa ack nhiều ngày, nhưng Beam window có thể chỉ chấp nhận late events 10 phút **theo watermark**. Một message được replay sau vài ngày có thể vẫn được Pub/Sub phát, nhưng **không còn hợp lệ để cập nhật aggregate window cũ**. Ngược lại, tăng `allowed_lateness` lên nhiều ngày không giữ lại Pub/Sub messages đã hết retention.

Khi dữ liệu muộn có giá trị tài chính/pháp lý, nên:

1. **Lưu raw events bất biến** với business `event_id`, event-time, ingest-time và schema version vào BigQuery/Cloud Storage theo policy.
2. Tách realtime dashboard (có lateness budget) khỏi **reconciliation/backfill** dựa trên dữ liệu gốc.
3. Dùng **window key + business ID** để ghi kết quả idempotent; kiểm tra chênh lệch với báo cáo batch cuối ngày.
4. Xây quarantine/DLQ cho **payload sai schema**, clock skew vô lý hoặc event quá cũ theo quy tắc nghiệp vụ; không nhầm đây là tính năng tự động của `allowed_lateness`.

### 7.3. Mở rộng thời hạn không chữa được watermark bị kẹt

Watermark đứng yên có thể do Pub/Sub backlog, một nguồn idle, hot key, transform/stateful timer chậm hoặc downstream không nhận đủ tải. Giải pháp là **đọc lag theo step, thông lượng, lỗi và capacity**, không phải chỉ đổi `allowed_lateness`. Giữ state lâu hơn khi bottleneck chưa giải quyết thường chỉ làm memory/disk và chi phí tăng.

## 8. Ví dụ kiểm thử bằng Beam `TestStream`

### 8.1. Tại sao cần TestStream?

Trong một `beam.Create(...)` batch thông thường, watermark có thể tiến đến vô cực khi source hoàn tất; điều đó **không mô phỏng có kiểm soát** việc event đến trước/sau watermark. **`TestStream`** cho phép đặt event timestamps, thay đổi processing time và tự tiến watermark trong môi trường thử nghiệm.

Đoạn Python sau là demo **DirectRunner/Beam**, không tạo tài nguyên Google Cloud. Cài `apache-beam` trong môi trường thực hành được phép, giữ version nhất quán với runner được sử dụng. Các timestamps **5, 20, 35... là số giây từ Unix epoch trong môi trường mô phỏng**, không phải giờ giao dịch thật.

~~~python
import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.testing.test_stream import TestStream
from apache_beam.transforms.trigger import (
    AfterWatermark, AfterProcessingTime, AfterCount, AccumulationMode)
from apache_beam.transforms.window import FixedWindows, TimestampedValue


class InspectPane(beam.DoFn):
    def process(
        self, item,
        window=beam.DoFn.WindowParam,
        pane_info=beam.DoFn.PaneInfoParam
    ):
        sku, total = item
        print(
            f"sku={sku}, total={total}, "
            f"window=[{float(window.start)},{float(window.end)}), "
            f"timing={pane_info.timing}, index={pane_info.index}")
        yield item


def main():
    source = (
        TestStream()
        .advance_watermark_to(0)
        .add_elements([
            TimestampedValue(("SKU-A", 100), 5),
            TimestampedValue(("SKU-A", 50), 20),
        ])
        .advance_processing_time(12)  # Cho early firing có cơ hội xảy ra.
        .add_elements([TimestampedValue(("SKU-A", 50), 35)])
        .advance_watermark_to(60)     # Qua cuối window [0,60).
        .add_elements([TimestampedValue(("SKU-A", 20), 40)])  # Late.
        .advance_watermark_to(181)    # Qua end + allowed lateness.
        .add_elements([TimestampedValue(("SKU-A", 900), 45)])  # Too late.
        .advance_watermark_to_infinity()
    )

    options = PipelineOptions(streaming=True)
    with beam.Pipeline(options=options) as p:
        (
            p
            | "SyntheticEvents" >> source
            | "OneMinuteWindow" >> beam.WindowInto(
                FixedWindows(60),
                trigger=AfterWatermark(
                    early=AfterProcessingTime(delay=10),
                    late=AfterCount(1)),
                accumulation_mode=AccumulationMode.ACCUMULATING,
                allowed_lateness=120)
            | "SumPerSku" >> beam.CombinePerKey(sum)
            | "InspectOutputPanes" >> beam.ParDo(InspectPane())
        )


if __name__ == "__main__":
    main()
~~~

**Quan sát mong muốn:** các panes minh họa tích lũy có totals **150 → 200 → 220**; phần tử giá trị **900** đến khi watermark đã qua thời hạn cho window nên không được đưa vào aggregate đó. Số/thứ tự logging và thời điểm fire cụ thể **có thể khác theo SDK/DirectRunner và cách xử lý timers**, vì vậy viết assertions trong test tự động và kiểm tra `PaneInfo` thay vì phụ thuộc thứ tự các dòng `print`.

### 8.2. Thử thay đổi một cấu hình

Tự sửa demo:

- Đổi `ACCUMULATING` thành `DISCARDING` và giải thích pane nào là delta.
- Thử `allowed_lateness=0`: quan sát sự kiện giá trị 20 có còn tạo late pane không.
- Đổi `FixedWindows(60)` thành `SlidingWindows(120, 60)` và mô tả vì sao cùng một element xuất hiện ở nhiều windows.
- Chậm watermark tới trước khi phát event 35 để xem **late phụ thuộc watermark**, không phụ thuộc thời gian đồng hồ.
- Thêm key `SKU-B` và xác nhận aggregation theo key **và** window chứ không chỉ theo window.

## 9. Áp dụng trong kiến trúc Pub/Sub → Dataflow → BigQuery

### 9.1. Đặt event-time đúng từ nguồn

Giả sử producer gửi từng message Pub/Sub có JSON `{"event_id":"evt-123","sku":"SKU-A","amount_vnd":120000}` và **attributes** `event_time=2026-11-19T10:02:10Z`, `event_id=evt-123`. Trong Python Beam, phần đọc và chuyển thành cặp key/value có thể viết:

~~~python
import json
import apache_beam as beam

SUBSCRIPTION = (
    "projects/REPLACE_PROJECT/subscriptions/REPLACE_SUBSCRIPTION"
)

def parse_order(raw: bytes):
    event = json.loads(raw.decode("utf-8"))
    # Demo: ứng dụng thật cần schema validation, quarantine và currency rules.
    return event["sku"], int(event["amount_vnd"])

# Trích đoạn đặt BÊN TRONG một Beam Pipeline được cấu hình.
events = (
    p
    | "ReadOrders" >> beam.io.ReadFromPubSub(
        subscription=SUBSCRIPTION,
        timestamp_attribute="event_time",
        id_label="event_id")
    | "ParseOrders" >> beam.Map(parse_order)
)
~~~

`p` là một **Beam Pipeline** được tạo bên ngoài đoạn mã, không phải biến có sẵn khi copy snippet vào Python REPL. `ReadFromPubSub` dùng `subscription` **hoặc** `topic` (không truyền cả hai). Nếu bỏ `timestamp_attribute`, source dùng Pub/Sub publish time; khi đó thiết bị gửi trễ có thể bị phân vào **window sai về nghiệp vụ**.

`id_label="event_id"` giúp connector dùng một identifier ổn định khi thuộc tính đó tồn tại, hỗ trợ deduplication theo cơ chế nguồn. Nó **không thay business idempotency** khi cùng giao dịch được publish dưới **hai event IDs khác nhau**, hoặc khi output có nhiều early/late panes. Với dữ liệu có thể sai schema, production nên dùng `ParDo` tách **valid** và **invalid** ra hai outputs; quarantine metadata an toàn, không log thô PII/tokens. Với nguồn Pub/Sub, **mỗi Dataflow pipeline nên dùng subscription riêng** để tránh chia ngẫu nhiên message giữa các pipeline.

### 9.2. Windowed aggregation và bản ghi output

Sau khi parse:

~~~python
from apache_beam.transforms.trigger import (
    AfterWatermark, AfterProcessingTime, AfterCount, AccumulationMode)
from apache_beam.transforms.window import FixedWindows

totals = (
    events
    | "Window5m" >> beam.WindowInto(
        FixedWindows(300),
        trigger=AfterWatermark(
            early=AfterProcessingTime(30),
            late=AfterCount(1)),
        allowed_lateness=600,
        accumulation_mode=AccumulationMode.ACCUMULATING)
    | "SumBySkuAndWindow" >> beam.CombinePerKey(sum)
)
~~~

Mỗi output phải mang theo **window_start, window_end, SKU, total, pane timing, thời điểm xuất bản và định danh lần chạy** để downstream biết đó là **phiên bản số liệu** hay **dòng sự kiện gốc**. Trong Beam, `DoFn.WindowParam` và `DoFn.PaneInfoParam` cho phép truy cập metadata này. Với production, phải đặt **deadline, retry policy, quota và schema** cho sink; demo trên chưa thực hiện ghi BigQuery.

### 9.3. Bẫy rất phổ biến: mỗi pane là một row BigQuery

Giả sử dùng `ACCUMULATING` và ghi append:

~~~text
window_start | sku   | pane_timing | total_vnd
10:00        | SKU-A | EARLY       | 150000
10:00        | SKU-A | ON_TIME     | 200000
10:00        | SKU-A | LATE        | 220000
~~~

`SELECT SUM(total_vnd)` trên cả ba rows cho ra **570000** thay vì **220000**. Ba rows mô tả **ba phiên bản của cùng window+SKU**, không phải ba giao dịch độc lập.

Ba hướng triển khai tùy yêu cầu:

| Sink pattern | Cách dùng | Cần kiểm soát |
| --- | --- | --- |
| **Append all panes vào staging** | Phục vụ audit, hiển thị kết quả mới nhất qua view/aggregation. | Dùng revision/order metadata và idempotency; không cộng mọi pane. |
| **Upsert bảng kết quả hiện tại** | Mỗi `(window_start, sku)` chỉ có một giá trị mới nhất. | `MERGE`/transaction hoặc sink hỗ trợ upsert; giải quyết race, duplicate và out-of-order revisions. |
| **Raw events + batch reconciliation** | Lưu event ID/raw, tính lại báo cáo cuối ngày bằng BigQuery. | Dedupe business events và kiểm tra source-of-truth; có latency cao hơn. |

**BigQuery Storage Write API** có các chế độ ghi khác nhau về **exactly-once/at-least-once**; dù chọn chế độ exactly-once cho từng record, **early/on-time/late panes vẫn là các outputs nghiệp vụ khác nhau**. Không nhầm bảo đảm vận chuyển một row với bảo đảm tổng hợp không bị nhân ba. Với dashboard tài chính, ưu tiên raw event ledger và **bản số liệu được xác nhận cuối** hoặc quy trình recompute/upsert có version.

### 9.4. SQL reconciliation từ raw event table

Giả sử `retail-lab.raw_events.order_payments` chứa `event_id`, `event_time TIMESTAMP`, `ingested_at TIMESTAMP`, `sku`, `amount_vnd INT64`, và `source_message_id`. Truy vấn minh họa sau chọn **bản ghi đầu tiên cho từng business event ID** rồi tính fixed 5-minute windows:

~~~sql
WITH deduplicated AS (
  SELECT
    event_id, event_time, sku, amount_vnd
  FROM `retail-lab.raw_events.order_payments`
  WHERE event_time >= TIMESTAMP('2026-11-19 00:00:00+00')
    AND event_time < TIMESTAMP('2026-11-20 00:00:00+00')
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY event_id
    ORDER BY ingested_at, source_message_id
  ) = 1
)
SELECT
  TIMESTAMP_SECONDS(DIV(UNIX_SECONDS(event_time), 300) * 300)
    AS window_start_utc,
  sku,
  SUM(amount_vnd) AS total_vnd
FROM deduplicated
GROUP BY window_start_utc, sku
ORDER BY window_start_utc, sku;
~~~

Đây là **truy vấn đối soát**, không phải thiết kế exactly-once tự động. Cần quy tắc khi **hai records cùng `event_id` nhưng payload khác nhau**, xử lý negative/reversal events và điều kiện partition pruning trên bảng thật. Phần tử timestamp tại đúng ranh giới 5 phút thuộc window **bắt đầu tại ranh giới đó**. Nếu dùng timestamp theo thời điểm địa phương, phải thống nhất cách chuyển UTC và lịch giờ mùa hè.

## 10. Giám sát watermark, lag, throughput và state

### 10.1. Những tín hiệu dễ bị nhầm

| Tín hiệu Dataflow | Ý nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Data watermark** theo step | Mốc event-time đã được xử lý/ước lượng hoàn tất. | Step nào đang giữ watermark? |
| **Data watermark lag** | Khoảng cách giữa event time mới nhất và watermark của step. | Có dữ liệu cũ chưa được giải phóng không? |
| **System lag** | Khoảng thời gian dữ liệu đang đợi hoặc được xử lý trong hệ thống. | Có nghẽn throughput/CPU/hot key không? |
| **Data freshness** | Độ chênh lệch event time so với thời gian hiện tại của dữ liệu tại pipeline. | Dashboard có đang ngày càng cũ không? |
| **Element counts / throughput** | Số lượng nhận/xử lý/xuất và tỉ lệ theo thời gian. | Có stage nào ít output vì lọc hoặc lỗi không? |
| **User counters** | Số events malformed, duplicates, late, rejected theo logic ứng dụng. | Có mất chất lượng dữ liệu không? |
| **Sink metrics** | BigQuery load/write failures, backlog, commit latency. | Số liệu đến destination có kịp không? |

Dataflow Console có **job metrics**, **per-step metrics**, job graph, logs, worker CPU/Memory và các trạng thái/lag. Cloud Monitoring có thể tạo alerts cho system lag và các metrics liên quan; metric có sampling delay nên **không xem một điểm tăng ngắn là incident ngay lập tức**. Với event-time timestamps, hãy ghi cả `ingested_at` để tách **nguồn chậm** khỏi **pipeline chậm**.

### 10.2. Đặt cảnh báo theo nhu cầu kinh doanh

Giả sử SLO dashboard là **95% đơn hàng hiển thị trong 2 phút**, đối soát cuối ngày sai lệch bằng 0 theo business rules (đều là mục tiêu **giả định**):

1. Alert **system lag** nếu dữ liệu đang chờ xử lý liên tục vượt mức chấp nhận.
2. Alert **watermark lag** nếu on-time panes chậm bất thường, dù CPU/throughput có vẻ bình thường.
3. Alert **no input** nếu publisher/source đang ngừng gửi (tránh diễn giải empty output như thành công).
4. Alert **late/invalid rates** nếu số sự kiện chậm/không hợp lệ tăng bất thường.
5. Alert **sink failures** và chênh lệch giữa raw-event count, processed count, BigQuery rows.

Không tự tăng worker count khi watermark bị một nguồn **idle** giữ hoặc một **hot key** chặn processing: cần xem topology step, source watermark behavior, key skew và state/timers trước. Watermark có thể đi chậm dù số worker còn dư.

### 10.3. Lệnh `gcloud` chỉ đọc trạng thái job

~~~bash
PROJECT_ID="retail-lab"
REGION="asia-southeast1"

# READ-ONLY: liệt kê các jobs Dataflow theo project/region.
gcloud dataflow jobs list --project="$PROJECT_ID" --region="$REGION"

# READ-ONLY: chọn đúng JOB_ID có trong kết quả ở trên.
gcloud dataflow jobs describe "REPLACE_WITH_JOB_ID" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

**Không dùng `gcloud dataflow jobs drain/cancel` để “sửa” watermark chậm khi chưa có runbook**: drain có semantics hoàn tất state/window khác cancel; replay/khởi động lại pipeline có thể tác động đến số liệu và sink. Tránh dùng một lệnh terminate mà không biết checkpoint, Pub/Sub subscription và downstream state.

## 11. Thiết kế production: correctness, bảo mật và chi phí

### 11.1. Event ID, replay và exactly-once

Một event có thể tới lại do publisher retry hoặc Pub/Sub redelivery. Trong một trường hợp khác, **một lần mua thật sự** được publisher phát lại dưới event ID mới. Vì vậy:

| Lớp | Điều cần giải quyết |
| --- | --- |
| **Producer** | Business ID ổn định, event ID, timestamp có nguồn tin cậy và schema version. |
| **Pub/Sub/Dataflow source** | Dedupe IDs theo connector và xử lý retry; không coi publish time là event time nếu sai nghiệp vụ. |
| **Window/trigger** | Nhận late events tới allowed lateness, định nghĩa pane dạng total hay delta. |
| **BigQuery sink** | Chọn Storage Write API mode thích hợp, xử lý nhiều panes, upsert và idempotent commits. |
| **Reconciliation** | Có raw immutable history/backfill và công thức đối soát tài chính. |

Dataflow có **exactly-once streaming processing mode** và chế độ at-least-once với đánh đổi throughput/chi phí, nhưng không thể ngăn một producer tạo **hai sự kiện nghiệp vụ khác IDs**, cũng không làm các thao tác trên hệ thống ngoài giao dịch Dataflow thành exactly-once. **Seek một Pub/Sub subscription đang được pipeline Dataflow đọc không được khuyến nghị**: seek ngược có thể phá giả định watermark/state và gây duplicate hoặc drop. Muốn replay, xem quy trình **snapshot/new subscription + drain hoặc cancel job và chạy job mới**, có kiểm soát sink và IDs.

### 11.2. Chọn lateness budget theo phân phối thực

Không chọn `allowed_lateness=24h` chỉ vì “an toàn hơn”. Thu thập histogram của:

~~~text
arrival_delay = Pub/Sub publish_time - event_time
pipeline_delay = output_emit_time - Pub/Sub publish_time
end_to_end_delay = output_emit_time - event_time
~~~

Sau đó đánh giá **p50/p95/p99/p99.9 và outliers** theo thiết bị/region/đường mạng. Quyết định:

- **Dashboard realtime:** trả early results nhanh, chấp nhận hiệu chỉnh có giới hạn.
- **Báo cáo vận hành:** on-time plus late pane, giữ state trong thời gian outage thường gặp.
- **Kế toán/chốt sổ:** raw ledger + đối soát theo thời điểm chốt; sự kiện quá muộn đi qua quy trình sửa/bù riêng.

Nếu 99,9% events tới trong 8 phút, chọn 10 phút lateness có thể là **giả thuyết ban đầu**, nhưng phải tính watermarks, outages kéo dài, size state và business impact. **Không có một giá trị chuẩn cho mọi pipeline**.

### 11.3. IAM và mạng từng chặng

| Thành phần | Danh tính | Quyền cần cân nhắc |
| --- | --- | --- |
| Cloud Run publisher | Runtime service account | `roles/pubsub.publisher` trên đúng topic. |
| Dataflow worker | Dedicated Dataflow worker SA | `roles/dataflow.worker`, `roles/pubsub.subscriber`, IAM tạo/đọc tracking subscription khi dùng timestamp attribute, quyền GCS/BigQuery cần thiết. |
| BigQuery sink | Dataflow worker SA hoặc identity theo connector | BigQuery write permissions ở bảng/dataset và quyền tạo jobs nếu connector cần; không mặc định cấp BigQuery Admin toàn project. |
| CI/deployer | Identity phát hành | Quyền tạo/cập nhật Dataflow job và `iam.serviceAccounts.actAs` khi chạy bằng worker SA. |
| SRE/auditor | Read-only operations identity | Monitoring/Logging/Dataflow Viewer theo phạm vi, quyền drain/cancel tách riêng. |

Đường đến **Pub/Sub, BigQuery, Cloud Storage, Google APIs** phải có DNS/egress/VPC Service Controls phù hợp. Nếu workers không có public IP, xem Private Google Access/Private Service Connect và NAT/proxy theo topology. **`PERMISSION_DENIED` không chữa bằng tăng `max_num_workers`**, còn lỗi DNS không tự giải quyết bằng cấp quyền project Owner.

### 11.4. Chi phí của “realtime cập nhật liên tục”

~~~text
Tổng chi phí ≈
  Dataflow worker compute + Streaming Engine / state / shuffle
  + Pub/Sub message throughput và retention
  + BigQuery writes, queries, storage / upserts
  + Cloud Storage staging/raw archival
  + network transfer và Cloud Logging/Monitoring
~~~

Chọn early firing mỗi vài giây, sliding windows chồng rất nhiều và allowed lateness nhiều ngày có thể tăng **số panes, state, writes và BigQuery query cost** đáng kể. So sánh hai cấu hình theo **độ trễ p95/p99, correctness và chi phí trên một sự kiện hoặc một cửa sổ hoàn tất**; đừng tối ưu latency nhưng phá budget hoặc tăng duplicate aggregates.

## 12. Troubleshooting và runbook

| Triệu chứng | Nguyên nhân có thể | Hành động đầu tiên |
| --- | --- | --- |
| Event 10:02 được tính vào 10:10–10:15 | Source dùng Pub/Sub publish time thay vì event time. | Xem `timestamp_attribute`, payload/attributes và timezone. |
| Window không phát on-time pane | Watermark chưa qua window end, idle source, backlog hoặc slow stage. | Per-step watermark/data lag, logs, source metrics. |
| Dashboard có số liệu nhưng cuối kỳ còn đổi | Có early/late triggers hoặc accumulating panes. | Xem `PaneInfo.timing`, allowed lateness, sink revision. |
| Doanh thu cao gấp 2–3 lần | Append nhiều **accumulating panes** rồi `SUM`. | Dùng upsert/latest version, không cộng totals tích lũy. |
| Event đến muộn không được tính | Watermark đã vượt `window_end + allowed_lateness`. | Event timestamp, late policy, raw store/reconciliation. |
| Tăng allowed lateness nhưng vẫn mất event | Message bị nguồn loại trước khi đọc, retention hết hoặc parse fail. | Pub/Sub retention/backlog, invalid payload logs. |
| Watermark đứng lâu, CPU chưa cao | Nguồn idle, state/timers hoặc một key rất nóng. | Watermark per stage, hottest keys, parallelism và source behavior. |
| Session windows hợp nhất bất ngờ | Late event nối các phiên hoạt động đã tách. | Session gap, merging semantics, downstream corrections. |
| Truy vấn BigQuery có nhiều hàng trùng window+key | Early/on-time/late panes hoặc sink write retry. | `window_start`, `key`, `pane_timing`, run ID, write semantics. |
| Streaming job retry mãi cùng message | Poison event làm DoFn throw, streaming bundle retry lặp. | Schema validation, quarantine/DLQ, lỗi chính xác trong worker logs. |
| Dataflow không đọc được Pub/Sub | SA thiếu subscribe/permission tracking sub. | Effective IAM và Pub/Sub source config. |
| `PERMISSION_DENIED` ghi BigQuery | Dataflow SA thiếu quyền ghi dataset/table hoặc job permission. | IAM/resource policy, location, logs. |
| Replay làm watermark/aggregates sai | Seek trực tiếp subscription của job đang chạy. | Dừng quy trình replay, áp dụng runbook snapshot/job mới. |
| Chi phí tăng mạnh | Early frequency, sliding overlap, retention/state và sink writes. | So panes per window, shuffle/state, Billing SKUs. |

**Runbook 7 bước khi late data làm báo cáo sai:**

1. Khoanh vùng **business event IDs** và khoảng event time bị ảnh hưởng; không sửa bằng cách xóa tất cả số liệu.
2. Đọc **source timestamp configuration** và mẫu event có clock skew.
3. Xác định **watermark của stage aggregation**, `allowed_lateness`, trigger, accumulation mode và panes đã emit.
4. Kiểm tra **Pub/Sub backlog/retention**, số invalid events, sink failures và trạng thái BigQuery.
5. Tính lại báo cáo từ **raw events đã dedupe** trong một khoảng có kiểm soát.
6. Sửa timestamp/trigger/sink semantics trong staging, chạy TestStream và kiểm thử so sánh với raw ledger.
7. Phát hành có approval, theo dõi lag, correctness, cost và kế hoạch rollback. **Không seek trực tiếp trên job streaming còn chạy** nếu chưa theo quy trình replay được hỗ trợ.

## 13. Bài tập

### Bài 1 — Phân biệt các loại thời gian

Một sự kiện có `event_time=10:02:10`, được Pub/Sub publish lúc 10:14:00 và Dataflow xử lý lúc 10:14:03. Với fixed window 5 phút theo UTC, sự kiện thuộc window nào khi dùng `event_time`? Nếu dùng publish time? Từ ví dụ này suy ra hậu quả của việc quên `timestamp_attribute`.

### Bài 2 — Ranh giới fixed và sliding

Cho events lúc 10:04:59, 10:05:00 và 10:07:00. Hãy gán chúng vào fixed windows dài 5 phút; sau đó xác định các sliding windows dài 10 phút, trượt 5 phút, có chứa event 10:07. Vì sao không được cộng tổng hai sliding windows chồng nhau?

### Bài 3 — Watermark có phải lời hứa?

Window `[10:00,10:05)` đã có watermark vượt 10:05; tiếp đó tới event timestamp 10:02. Nó có phải “late” không? Nếu event này đến muộn, điều đó có chứng minh Dataflow bị lỗi hay không? Nêu vai trò của watermark như một **ước lượng**.

### Bài 4 — Allowed lateness

Window kết thúc lúc 10:05, `allowed_lateness=10 phút`. Khi watermark đang ở 10:10, một event 10:03 có còn khả năng được tổng hợp không? Khi watermark đã vượt 10:15 thì sao? Kể một trường hợp processing time hiện tại 11:00 nhưng state vẫn chưa được GC.

### Bài 5 — Early, on-time, late panes

Window có ba firings: `EARLY=150`, `ON_TIME=200`, `LATE=220` (nghìn VND) ở **accumulating mode**. Tổng giá trị hiện tại là bao nhiêu? Nếu sink cộng cả ba rows sẽ ra bao nhiêu? Với discarding mode, các panes tương ứng cần mang giá trị nào?

**Gợi ý:** accumulating total cuối **220**, cộng sai thành **570**; discarding delta tương ứng **150, 50, 20**.

### Bài 6 — Thực hành `TestStream`

Thay demo ở mục 8 bằng hai keys `SKU-A`, `SKU-B`. Di chuyển watermark qua cuối window, thêm một phần tử muộn ở mỗi key, rồi đổi `ACCUMULATING` sang `DISCARDING`. Ghi lại `PaneInfo.timing`, `index` và totals; giải thích vì sao thứ tự dòng `print` không phải API contract.

### Bài 7 — Chọn windows cho sản phẩm

Đề xuất fixed, sliding hoặc session windows cho ba nhu cầu: (a) doanh thu theo kỳ 5 phút; (b) số lượt xem trong 30 phút gần nhất, cập nhật mỗi 5 phút; (c) phiên tương tác của một thiết bị với gap 10 phút. Nếu một sự kiện đến muộn nối hai sessions, downstream cần xử lý gì?

### Bài 8 — Pub/Sub ingestion

Một publisher phát message JSON lúc 14:00 với event-time 13:20; Dataflow lại xếp vào window 14:00. Hãy nêu cách sửa attributes, format RFC3339, `ReadFromPubSub(timestamp_attribute=...)` và quyền có thể cần cho tracking subscription. Vì sao thay đổi timestamp không tự giải quyết duplicate business events?

### Bài 9 — BigQuery đúng grain

Thiết kế schema cho **raw events** và bảng **window aggregates**. Chọn một trong ba chiến lược: append panes có version, upsert latest hoặc reconcile raw events. Trình bày cách khóa `(window_start, sku)`, xử lý late correction và tránh `SUM` các accumulating panes.

### Bài 10 — Incident và tối ưu chi phí

Dashboard trễ 25 phút, watermark lag tăng, worker CPU chỉ 30%, số late events tăng mạnh; Dataflow có hai Pub/Sub sources, một source rất ít message. Lập runbook phân biệt **idle source, backlog, hot key, timestamp sai và sink chậm**. Nêu vì sao tăng `allowed_lateness` hoặc số workers chưa chắc giải quyết vấn đề, và dự toán tác động của trigger sớm mỗi 5 giây so với 30 giây.

## 14. Checklist production và tài liệu chính thức

| Hạng mục | Điều cần xác minh |
| --- | --- |
| **Event-time contract** | Có nguồn thời gian tin cậy, UTC, schema version, clock-skew policy, `event_id` ổn định. |
| **Window type** | Fixed/sliding/session phù hợp grain, boundary và timezone; biết session có thể merge. |
| **Watermark** | Source/step watermark và idle sources được giám sát; không xem watermark là bảo đảm tuyệt đối. |
| **Trigger** | Early/on-time/late semantics rõ; biết số panes có thể lớn hơn số windows. |
| **Accumulation** | `ACCUMULATING` (total) hay `DISCARDING` (delta) được sink hiểu chính xác. |
| **Allowed lateness** | Đặt theo phân phối trễ và SLO, state/cost được đo; có đường xử lý sự kiện quá hạn. |
| **Testing** | `TestStream` cover on-time, late, too-late, empty/no events, multiple keys và session merge. |
| **Pub/Sub** | Dedicated subscription, timestamp attribute, tracking-sub IAM, retention và replay runbook. |
| **BigQuery** | Raw ledger/dedup, pane schema, write semantics, revision/upsert/reconciliation. |
| **IAM/network** | Dataflow worker SA tối thiểu, Pub/Sub/BigQuery/GCS permissions, Google APIs egress. |
| **Observability** | Watermark lag, system lag, data freshness, bad/late event counters, sink errors. |
| **Performance/cost** | Window overlap, trigger frequency, state size, Streaming Engine, BigQuery writes và Billing. |
| **Release/recovery** | Beam version pin/test, staging load tests, drain/cancel strategy, replay và rollback có phê duyệt. |

Nguồn tham khảo chính thức (kiểm tra lại SDK/runner support trước khi áp dụng vào production):

- [Google Cloud — Dataflow streaming pipelines](https://cloud.google.com/dataflow/docs/concepts/streaming-pipelines)
- [Apache Beam — Programming Guide: Windowing](https://beam.apache.org/documentation/programming-guide/#windowing)
- [Apache Beam — Programming Guide: Triggers](https://beam.apache.org/documentation/programming-guide/#triggers)
- [Apache Beam — TestStream Python API](https://beam.apache.org/releases/pydoc/current/apache_beam.testing.test_stream.html)
- [Apache Beam — Pub/Sub Python I/O](https://beam.apache.org/releases/pydoc/current/apache_beam.io.gcp.pubsub.html)
- [Google Cloud — Read from Pub/Sub to Dataflow](https://cloud.google.com/dataflow/docs/concepts/streaming-with-cloud-pubsub)
- [Google Cloud — Dataflow job metrics](https://cloud.google.com/dataflow/docs/guides/using-monitoring-intf)
- [Google Cloud — Monitor Dataflow with Cloud Monitoring](https://cloud.google.com/dataflow/docs/guides/using-cloud-monitoring)
- [Google Cloud — Write from Dataflow to BigQuery](https://cloud.google.com/dataflow/docs/guides/write-to-bigquery)
- [Google Cloud — Troubleshoot Dataflow errors](https://cloud.google.com/dataflow/docs/guides/common-errors)
- [Google Cloud — Dataflow pricing](https://cloud.google.com/dataflow/pricing)

**Ghi nhớ:** **Window** xác định *event thuộc nhóm thời gian nào*; **watermark** ước lượng *đã tiến tới đâu theo event time*; **trigger** chọn *khi nào phát từng pane*; **allowed lateness** quyết định *có thể sửa window cũ đến mốc watermark nào*. Khi xuất nhiều accumulating panes, **mỗi pane là một phiên bản của tổng**, không phải một doanh thu mới để cộng thêm. Pipeline đáng tin cậy cần vừa xử lý dữ liệu muộn, vừa giữ bản ghi gốc để đối soát, đo lag và kiểm soát đúng chi phí.




