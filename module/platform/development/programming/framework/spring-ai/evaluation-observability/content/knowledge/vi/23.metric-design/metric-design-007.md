# Phân biệt không có dữ liệu với giá trị bằng không

Một dashboard Spring AI hiển thị **0 lỗi** có thể mang hai ý nghĩa hoàn toàn khác nhau: hệ thống đã quan sát request và không có request nào lỗi; hoặc hệ thống không thu thập được metric lỗi, Prometheus chưa scrape được target, hay meter chưa từng được đăng ký. Cả hai trường hợp đều có thể nhìn giống một con số 0 nếu dashboard tự điền giá trị mặc định. Khi đó, một sự cố telemetry có thể bị hiểu nhầm là hệ thống đang khỏe.

Ngược lại, một panel trống cũng không tự động chứng minh ứng dụng bị lỗi. Có thể chưa có traffic, chưa có ca evaluation, metric chỉ được tạo khi có sự kiện đầu tiên, hoặc bộ lọc label đang loại hết dữ liệu. **Không có dữ liệu** và **giá trị bằng 0** là hai trạng thái khác nhau về ngữ nghĩa.

Bài học này thuộc chương **Thiết kế metric** trong module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline. Phân biệt missing với zero là điều kiện để dashboard, SLO và báo cáo hồi quy không đưa ra kết luận sai.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **zero**, **empty result**, **missing series**, **no sample**, **NaN**, **stale series** và **scrape failure**.
2. Giải thích vì sao Counter chưa từng được đăng ký khác với Counter đã đăng ký nhưng có giá trị 0.
3. Đọc hành vi Prometheus khi selector không khớp series, khi rate thiếu mẫu và khi target không scrape được.
4. Dùng absent(), absent_over_time(), up, or vector(0) và các phép toán PromQL có chủ đích.
5. Thiết kế dashboard phân biệt **No traffic**, **No data**, **Zero events** và **Telemetry unavailable**.
6. Áp dụng cùng nguyên tắc cho evaluation: relevance score bằng 0 khác với chưa chấm, không có tài liệu, evaluator timeout hoặc case bị bỏ qua.
7. Dùng Micrometer để khởi tạo meter, ghi Gauge/Counter đúng vòng đời và kiểm tra dữ liệu ở registry/exporter.
8. Thiết kế metric completeness, freshness và coverage để nhận biết dữ liệu quan sát bị thiếu.
9. Viết cảnh báo và kiểm thử bảo vệ khỏi false green/false zero trong ứng dụng Spring AI.

## 2. Bốn trạng thái không được đánh đồng

Hãy bắt đầu bằng bốn câu hỏi:

- **Có sự kiện được quan sát không?**
- **Có sample được thu thập không?**
- **Sample có giá trị bao nhiêu?**
- **Nếu không có sample, ta có biết lý do không?**

Ví dụ metric số tool timeout:

| Trạng thái | Ý nghĩa | Có thể kết luận |
| --- | --- | --- |
| Sample tồn tại, giá trị 0 | Metric được ghi/thu thập và hiện không có timeout tích lũy (hoặc Gauge đang bằng 0) | Có dữ liệu quan sát với giá trị 0 |
| Series không tồn tại | Chưa đăng ký, không có label combination, bị filter hoặc exporter không xuất | Chưa biết số timeout |
| Query trả empty vector | Selector không tìm thấy series/sample hợp lệ trong phạm vi truy vấn | Không có kết quả phù hợp, không phải số 0 |
| Query trả NaN | Phép tính không xác định hoặc dữ liệu đầu vào đặc biệt | Không thể diễn giải như zero |

### 2.1. Zero là một quan sát có ý nghĩa

Giá trị 0 có thể có nghĩa:

- Không có request nào đang in-flight tại thời điểm scrape.
- Counter đã được tạo và chưa ghi sự kiện nào.
- Có 100 evaluation cases, không có case nào FAIL.
- Retrieval được thực hiện hợp lệ nhưng trả về 0 documents.
- Có 50 request được kiểm tra limiter và 0 request bị từ chối.

Trong mỗi ví dụ, số 0 có ý nghĩa vì **đã có phép đo hoặc mẫu số/điều kiện quan sát phù hợp**.

### 2.2. Missing là chưa có bằng chứng

Một series có thể không xuất hiện vì:

- Meter chưa được tạo do code path chưa chạy.
- Không có sự kiện nào khiến meter lazy được đăng ký.
- Label combination chưa từng xuất hiện.
- Meter bị MeterFilter deny hoặc bị registry filter.
- Endpoint không expose metric đó.
- Prometheus target chưa scrape hoặc scrape thất bại.
- Selector dùng sai tên/labels.
- rate() không đủ số samples trong cửa sổ.
- Series đã trở nên stale sau khi không còn được scrape.

Không thể suy ra số sự kiện bằng 0 chỉ từ việc không thấy series.

### 2.3. Bảng quyết định ngắn

| Quan sát | Cách gọi đúng | Cách gọi sai |
| --- | --- | --- |
| Counter sample = 0 | Zero events observed | Không có dữ liệu |
| Gauge sample = 0 | Current value is zero | Chưa từng scrape |
| Selector trả rỗng | No matching series/sample | Metric bằng 0 |
| up = 0 | Target scrape thất bại | Ứng dụng chắc chắn không chạy |
| up không tồn tại | Không có series up trong query range | Target đang khỏe |
| Evaluation chưa chạy | No evaluation data | PASS rate = 100% |
| Evaluator trả score 0 | Score thực sự bằng 0 theo rubric | Missing score |
| Retrieval trả danh sách rỗng hợp lệ | Zero documents retrieved | Retriever không hoạt động |

## 3. Ví dụ trong Spring AI: 0 lỗi khác với không có metric lỗi

Giả sử ứng dụng có Counter logic:

~~~text
app.ai.tool.execution.failed
~~~

Hai trạng thái:

**Trường hợp A — đã khởi tạo và không có lỗi**

~~~text
app_ai_tool_execution_failed_total{
  tool_family="retrieval"
} 0
~~~

**Trường hợp B — không có series**

~~~text
# Không có sample nào phù hợp trong scrape.
~~~

Ở trường hợp A, ta có một series và giá trị 0. Ở trường hợp B, có thể meter chưa được đăng ký, label chưa từng xuất hiện hoặc dữ liệu bị mất. Dashboard không nên tự biến B thành cùng một kết luận như A nếu không có thêm bằng chứng.

### 3.1. Một tình huống thực tế

Một deployment mới được rollout nhưng chưa có request nào gọi tool payment. Nếu instrumentation chỉ tạo Counter trong nhánh bắt lỗi, metric tool.execution.failed với tool_family=payment chưa tồn tại. Panel lỗi payment sẽ trống. Người vận hành không thể kết luận payment chưa lỗi; cũng không thể kết luận tool payment đã được kiểm tra và không lỗi.

Nếu ứng dụng đăng ký trước những Counter quan trọng cho từng nhóm tool được hỗ trợ, series có thể xuất giá trị 0 ngay cả khi chưa có lỗi. Tuy vậy, số lần execution vẫn là 0; cần xem thêm request count để biết tool đã được gọi hay chưa.

### 3.2. Hai metric có thể cùng cần thiết

Để phân biệt “không có lỗi” với “chưa có lần thực thi”, có thể theo dõi:

| Metric | Ý nghĩa |
| --- | --- |
| app.ai.tool.execution.completed | Số tool executions đã kết thúc |
| app.ai.tool.execution.failed | Số tool executions kết thúc lỗi |

Nếu completed = 0 và failed = 0, chưa có lần thực thi nào. Nếu completed = 100 và failed = 0, đã có 100 executions và không có lỗi được ghi nhận. Nếu completed không có series nhưng failed = 0, instrumentation có thể chưa đủ để kết luận.

Trong nhiều trường hợp, một Timer có thể cung cấp count và outcome tag thay cho Counter trùng nghĩa. Điều quan trọng là hợp đồng metric xác định rõ **đơn vị quan sát** và cách tạo series.

## 4. Missing data có nhiều nguyên nhân

Không có dữ liệu là một triệu chứng; muốn hiểu nó, cần xác định missing ở tầng nào.

| Tầng | Nguyên nhân | Ví dụ |
| --- | --- | --- |
| Application | Code path chưa chạy hoặc meter lazy chưa đăng ký | Chưa có tool invocation |
| Instrumentation | Meter bị filter hoặc sai registry | MeterFilter.deny() |
| Actuator/exporter | Endpoint chưa expose hoặc sai base path | Không thấy /actuator/prometheus |
| Scrape | Target DOWN, auth/path/network lỗi | Prometheus không lấy được metrics |
| Storage | Retention, ingestion failure hoặc stale series | Không còn sample trong query range |
| Query | Sai metric name/label/range | Filter outcome=ok nhưng value là success |
| Dashboard | Null được đổi thành 0 | Panel hiện false green |
| Evaluation pipeline | Batch chưa chạy, evaluator lỗi hoặc case bị skip | Không có verdict |

### 4.1. Kiểm tra theo thứ tự

~~~mermaid
flowchart TD
    A["Panel trống hoặc query rỗng"] --> B{"Target có được scrape?"}
    B -->|Không| C["Kiểm tra up, target health, path, auth, network"]
    B -->|Có| D{"Metric có trong scrape output?"}
    D -->|Không| E["Kiểm tra MeterRegistry, lazy registration, filters, labels"]
    D -->|Có| F{"Selector có khớp series?"}
    F -->|Không| G["Sửa metric name, label matchers, range"]
    F -->|Có| H{"Hàm truy vấn có đủ sample?"}
    H -->|Không| I["Kiểm tra rate window, scrape interval, staleness"]
    H -->|Có| J["Đọc giá trị và đơn vị; phân biệt zero/NaN"]
~~~

Không nên bắt đầu bằng cách thêm or vector(0) vào mọi truy vấn. Trước hết phải biết **vì sao series bị thiếu**.

## 5. Prometheus data model: empty vector không phải zero

PromQL trả về một trong các dạng kết quả:

- **Instant vector:** tập các time series có sample tại thời điểm đánh giá.
- **Range vector:** tập các dải sample trong một khoảng thời gian.
- **Scalar:** một giá trị số đơn.
- **String:** chuỗi (hiếm dùng trong dashboard thông thường).

Một selector:

~~~promql
app_ai_tool_execution_failed_total
~~~

nếu không tìm thấy series sẽ trả **empty instant vector**. Nó không tự tạo một series với giá trị 0.

### 5.1. sum() trên dữ liệu rỗng

Một hiểu lầm thường gặp là:

~~~promql
sum(app_ai_tool_execution_failed_total)
~~~

sẽ trả 0 nếu không có series. Thực tế, phép tổng hợp trên empty vector trả về **empty vector**, không tự tạo scalar 0. Nếu dashboard muốn hiển thị 0, phải định nghĩa rõ fallback và điều kiện đảm bảo rằng missing thực sự có nghĩa zero.

### 5.2. Phép so sánh cũng không tự tạo series

~~~promql
app_ai_tool_execution_failed_total == 0
~~~

Chỉ lọc các series tồn tại và có giá trị 0. Nếu series không tồn tại, kết quả vẫn rỗng. Không thể dùng biểu thức này để phát hiện đồng thời cả zero và missing.

### 5.3. NaN không phải zero

Ví dụ:

~~~promql
0 / 0
~~~

Phép chia 0/0 cho NaN; phép chia một số dương cho 0 có thể cho +Inf theo số học IEEE 754. NaN biểu thị **Not a Number**, không có nghĩa metric bằng 0. Cần kiểm tra mẫu số, selector và cách hiển thị của dashboard.

Một số panel có thể ẩn NaN, hiển thị null hoặc để trống tùy frontend. Đừng dựa vào màu sắc hoặc nhãn hiển thị để suy luận; xem query result và raw value.

## 6. up: target scrape thành công hay thất bại

Prometheus tạo metric up cho mỗi target được scrape:

- up = 1: lần scrape gần nhất của target thành công.
- up = 0: lần scrape gần nhất thất bại.
- Không có series up: target không có trong phạm vi discovery/query hoặc series không còn hiện diện trong thời gian tra cứu.

Ví dụ:

~~~promql
up{job="spring-ai"}
~~~

Kiểm tra target nào đang scrape:

~~~promql
up{job="spring-ai"} == 0
~~~

Biểu thức thứ hai chỉ trả về các series up hiện có với giá trị 0; target không còn series up sẽ không xuất hiện trong kết quả.

### 6.1. Target DOWN khác metric ứng dụng bằng 0

Nếu up=0, Prometheus không lấy được scrape thành công. Một Counter ứng dụng không được cập nhật trong lần scrape đó không có nghĩa Counter bằng 0. Giá trị cũ có thể còn trong storage theo quy tắc staleness/lookback, hoặc query range có thể chứa những sample trước khi target lỗi.

Không diễn giải một biểu đồ phẳng trong lúc target DOWN như hệ thống không phát sinh lỗi.

### 6.2. Target không tồn tại trong discovery

Nếu target bị xóa khỏi service discovery hoặc relabeling loại bỏ, up có thể biến mất sau khi Prometheus xử lý stale marker. Cần theo dõi cả **target inventory/expected targets** nếu muốn cảnh báo target biến mất; up đơn lẻ không thể phát hiện mọi target lẽ ra phải tồn tại nhưng chưa bao giờ được discovery.

## 7. Staleness và lookback: vì sao series có thể biến mất

Prometheus lưu samples theo timestamp. Khi một series không còn được scrape hoặc không còn xuất hiện trong exposition, hệ thống có thể đánh dấu series là **stale**. Instant query chỉ chọn sample phù hợp với quy tắc lookback và staleness.

### 7.1. Lookback delta

Prometheus instant selector thường tìm sample mới nhất trong lookback window (mặc định phổ biến là 5 phút, có thể cấu hình khác). Nếu không có sample đủ mới, series không xuất hiện trong instant vector.

Điều này có nghĩa:

- Một metric từng có giá trị 5 phút trước có thể không còn xuất hiện trong instant query sau khi stale/lookback hết hiệu lực.
- Một series không có sample mới không thể được xem là zero.
- Range query có thể vẫn hiển thị lịch sử trước thời điểm series stale.

### 7.2. absent() và absent_over_time()

absent() trả về một series giá trị 1 nếu biểu thức đầu vào không có series; nếu có ít nhất một series, nó không trả về kết quả.

~~~promql
absent(app_ai_request_completed_total)
~~~

Truy vấn này có thể giúp cảnh báo metric family không tồn tại, nhưng không phân biệt metric chưa đăng ký với scrape failure hoặc query sai tên. Phải kết hợp với up và expected target.

absent_over_time() kiểm tra không có sample trong một khoảng thời gian:

~~~promql
absent_over_time(app_ai_request_completed_total[10m])
~~~

Điều này hữu ích khi muốn phát hiện metric không xuất hiện trong 10 phút. Tuy nhiên, nếu service thật sự không có traffic hoặc meter chỉ đăng ký theo nhu cầu, cảnh báo có thể false positive. Cần thiết kế metric heartbeat/registration hoặc điều kiện traffic tương ứng.

## 8. Phát hiện missing theo từng nhóm

absent() thường được dùng để phát hiện **toàn bộ selector không có kết quả**. Nhưng nếu một metric có nhiều label values, chỉ một nhóm bị thiếu trong khi các nhóm khác vẫn tồn tại thì absent() không báo missing cho nhóm riêng đó.

Ví dụ có retrieval và order nhưng payment chưa có series:

~~~text
app_ai_tool_execution_completed_total{tool_family="retrieval"} 10
app_ai_tool_execution_completed_total{tool_family="order"} 7
~~~

Truy vấn:

~~~promql
absent(app_ai_tool_execution_completed_total)
~~~

trả về empty vector vì metric family vẫn có ít nhất một series. Nó không chỉ ra payment bị thiếu.

### 8.1. Dùng metric info làm tập dimension kỳ vọng

Nếu ứng dụng phát metric info cho các tool families đã cấu hình:

~~~text
app_ai_tool_family_info{tool_family="retrieval"} 1
app_ai_tool_family_info{tool_family="order"} 1
app_ai_tool_family_info{tool_family="payment"} 1
~~~

có thể so sánh dimension kỳ vọng với dimension thực tế:

~~~promql
app_ai_tool_family_info
unless on (tool_family)
group by (tool_family) (
  app_ai_tool_execution_completed_total
)
~~~

Kết quả là các tool families có trong danh mục nhưng chưa có series execution. Đây là **chưa thấy execution series**, không tự động là lỗi; có thể tool chưa được gọi. Dashboard nên ghi nhãn rõ “chưa có execution sample”.

Nếu muốn hiển thị zero executions, có thể dùng tập info để dựng giá trị 0:

~~~promql
sum by (tool_family) (
  app_ai_tool_execution_completed_total
)
or on (tool_family)
(
  0 * max by (tool_family) (app_ai_tool_family_info)
)
~~~

max by (tool_family) loại bỏ các bản sao của cùng một family nếu info metric được scrape từ nhiều instance. Truy vấn giả định info metric được đăng ký cho đúng tập tool families và execution Counter được khởi tạo/được export phù hợp. Nếu mục tiêu là rate trong cửa sổ, cần áp dụng rate() trước khi tổng hợp và bảo đảm đủ samples; không thay một rate rỗng do thiếu scrape thành zero một cách mù quáng.

### 8.2. Missing label combination có thể là hợp lệ

Không phải mọi tổ hợp outcome × tool_family đều phải tồn tại. Nếu payment chưa từng timeout, series payment/timeout có thể chưa được tạo. Để khẳng định **0 timeout**, cần một trong các cách:

- Pre-initialize Counter cho mọi tổ hợp hợp lệ và exporter xuất chúng.
- Dùng metric info cho tập tổ hợp kỳ vọng và fallback zero có điều kiện.
- Dùng event store/aggregation job tạo báo cáo có mẫu số đầy đủ.

Không tạo tất cả tổ hợp nếu taxonomy quá lớn; việc pre-initialize cũng làm tăng cardinality. Chỉ khởi tạo những dimension thực sự cần cho vận hành.

### 8.3. absent_over_time không chứng minh service không chạy

absent_over_time(metric[10m]) chỉ chứng minh không có sample phù hợp trong cửa sổ đó. Nguyên nhân có thể là không có event, meter lazy, scrape lỗi hoặc metric bị đổi tên. Kết hợp với up, metric heartbeat/application info, request counter và expected target inventory.

## 9. Thiết kế metric để biểu diễn completeness và freshness

Nếu dashboard cần phân biệt no traffic với telemetry failure, hãy đo **tình trạng quan sát** như một phần của hệ thống.

### 9.1. Application heartbeat

Một Gauge hoặc Info metric có thể được đăng ký khi ứng dụng khởi động:

~~~java
Gauge.builder("app.ai.telemetry.ready",
                telemetryState, state -> state.isReady() ? 1 : 0)
        .description("Application telemetry initialization state")
        .register(registry);
~~~

Nguồn telemetryState phải được giữ sống và cập nhật đúng vòng đời. Giá trị 1 cho biết instrumentation đã khởi tạo theo contract; nó không chứng minh mọi meter đều hoạt động hoặc mọi sự kiện đều được ghi.

Một metric info tĩnh như service build metadata có thể giúp xác định service/version đã được scrape. Đừng dùng timestamp làm label; nếu cần thời gian heartbeat, dùng Gauge numeric với epoch seconds hoặc timestamp metric theo quy ước đã chọn.

### 9.2. Heartbeat khác traffic

Một service có thể healthy nhưng không có request. Vì vậy:

- Heartbeat/target health trả lời **service có được quan sát và telemetry sẵn sàng không?**
- Request counter trả lời **có traffic không?**
- Error counter trả lời **đã quan sát bao nhiêu lỗi?**
- Evaluation batch counter trả lời **đã chạy bao nhiêu ca?**

Không dùng một metric thay cho cả bốn câu hỏi.

### 9.3. Freshness của dữ liệu

Một panel có thể có sample cũ nhưng không có sample mới. Cần theo dõi thời điểm quan sát gần nhất hoặc heartbeat. Với một Gauge timestamp do ứng dụng cập nhật:

~~~promql
time() - app_ai_telemetry_last_successful_observation_timestamp_seconds
~~~

Kết quả là tuổi của lần quan sát thành công gần nhất tính bằng giây, nếu metric timestamp có mặt. Nếu selector rỗng, kết quả vẫn rỗng; cần một alert missing riêng. Timestamp phải là giá trị sample theo epoch seconds, không phải label.

### 9.4. Completeness và coverage cho evaluation

Một batch có 100 cases:

~~~text
cases_expected = 100
cases_started = 100
cases_completed = 96
cases_pass = 80
cases_fail = 12
cases_inconclusive = 4
~~~

Ta có:

- **Completion coverage** = 96/100 = 96%.
- **Pass rate trên ca có kết luận** = 80/(80+12) ≈ 86,96%.
- **Inconclusive rate trên ca hoàn tất** = 4/96 ≈ 4,17%.
- **Pass yield trên toàn bộ ca kỳ vọng** = 80/100 = 80%.

Không thể chỉ báo một tỷ lệ mà không nêu mẫu số. Bốn ca INCONCLUSIVE và bốn ca chưa hoàn tất là hai nhóm khác nhau; cả hai đều cần được thể hiện riêng.

Một batch chưa chạy không có pass rate bằng 0% hay 100%. Nó có **No evaluation data**.

## 10. Dashboard: thể hiện rõ No data, No traffic và Zero

Dashboard là nơi missing data dễ bị biến thành false green nhất. Cần quy định trạng thái hiển thị cho từng panel.

### 10.1. Bốn trạng thái panel

| Trạng thái | Điều kiện | Cách hiển thị đề xuất |
| --- | --- | --- |
| **Zero** | Có sample hợp lệ và giá trị bằng 0 | Hiển thị 0 cùng đơn vị |
| **No traffic** | Telemetry hoạt động nhưng không có request trong cửa sổ | Hiển thị “No traffic” |
| **No data** | Không có sample hoặc query rỗng, chưa xác định nguyên nhân | Hiển thị “No data” |
| **Telemetry unavailable** | Target down, scrape lỗi hoặc heartbeat mất | Cảnh báo riêng, không tô xanh |

Nếu một panel chỉ hỗ trợ số, có thể dùng null/NaN/no value state và thêm panel trạng thái scrape/heartbeat. Đừng ép mọi trạng thái về số 0 chỉ để đồ thị liên tục.

### 10.2. Grafana No Data và Null handling

Grafana có các lựa chọn xử lý No Data/Null ở cấp panel hoặc alert rule tùy phiên bản và loại datasource. Cần kiểm tra cấu hình thực tế:

- No Data có thể được hiển thị là N/A hoặc chuyển thành trạng thái alert.
- Null có thể bị nối đường, bỏ qua hoặc thay thế tùy chế độ hiển thị.
- Alert rule có thể phân biệt Normal, Pending, Alerting, No Data và Error.

Không mặc định Grafana luôn chuyển empty query thành zero. Xem query inspector, raw data và alert state của phiên bản đang dùng.

### 10.3. Ví dụ bố cục dashboard

~~~text
┌───────────────────────────────┬───────────────────────────────┐
│ Scrape / heartbeat            │ Request traffic                │
│ up = 1, telemetry_ready = 1    │ 0 requests/s -> No traffic     │
├───────────────────────────────┼───────────────────────────────┤
│ Tool failures                 │ Tool execution count           │
│ 0 observed failures            │ 0 executions                   │
├───────────────────────────────┼───────────────────────────────┤
│ Evaluation coverage           │ Evaluation pass rate           │
│ 96 / 100 cases completed      │ 80 / 92 decided cases          │
└───────────────────────────────┴───────────────────────────────┘
~~~

Ví dụ cho thấy **zero failures** chỉ có thể diễn giải cùng với traffic/execution count và health. Evaluation pass rate cần mẫu số decided cases và coverage riêng.

## 11. Alerting: cảnh báo zero, missing và stale khác nhau

Một alert nên nêu rõ trạng thái đang phát hiện:

### 11.1. Cảnh báo target scrape failure

~~~promql
up{job="spring-ai"} == 0
~~~

Đây là target có series up nhưng scrape gần nhất thất bại. Cần xử lý up missing riêng.

### 11.2. Cảnh báo metric family không có sample

~~~promql
absent_over_time(app_ai_request_completed_total[10m])
~~~

Alert này cần điều kiện traffic/expected target phù hợp; nếu service không có request trong 10 phút, nó có thể là false positive nếu metric chỉ phát sinh khi request chạy.

### 11.3. Cảnh báo application heartbeat mất

~~~promql
absent_over_time(app_ai_telemetry_ready[5m])
~~~

Có thể dùng nếu metric được đăng ký ngay khi ứng dụng khởi động và được scrape định kỳ. Kết hợp với up để phân biệt target down với instrumentation không xuất heartbeat.

### 11.4. Cảnh báo có traffic nhưng không có execution metric

Giả sử request counter được pre-initialize và tool executions chỉ phát khi được gọi:

~~~promql
sum(rate(app_ai_request_completed_total[5m])) > 0
and
absent_over_time(app_ai_tool_execution_completed_total[5m])
~~~

Đây chỉ là tín hiệu cần điều tra nếu hợp đồng ứng dụng kỳ vọng request có tool executions. Nếu nhiều request là chat-only, không thể coi thiếu tool execution là lỗi. Cần thêm route/case type hoặc một expected component metric.

### 11.5. Không cảnh báo “zero errors” như sự cố

Điều kiện:

~~~promql
app_ai_tool_execution_failed_total == 0
~~~

thường không phải alert; đó là trạng thái tốt nếu series tồn tại, traffic và telemetry đều hợp lệ. Alert nên tập trung vào error rate tăng, missing series, scrape failure hoặc heartbeat mất. **Zero không phải sự cố; zero không có bằng chứng mới là vấn đề.**

## 12. or vector(0) và nguy cơ tạo false zero

PromQL có thể dùng phép toán set **or** để cung cấp fallback khi biểu thức bên trái không có series:

~~~promql
sum(rate(app_ai_tool_execution_failed_total[5m])) or vector(0)
~~~

Nếu vế trái có kết quả, nó được giữ. Nếu vế trái rỗng, vector(0) tạo một instant vector có giá trị 0 và không có labels. Điều này có thể hữu ích cho **một tổng số toàn cục** khi nhóm đã xác minh rằng không có series đồng nghĩa với không có sự kiện trong phạm vi đo.

Nhưng nó cũng có thể che giấu target không scrape được, metric name bị đổi sau deploy, meter bị filter/chưa đăng ký, selector viết sai, hoặc không có traffic. Vì vậy, fallback zero chỉ nên dùng khi có tín hiệu độc lập chứng minh **nguồn dữ liệu đang hoạt động và phạm vi quan sát đã được đăng ký**.

### 12.1. vector(0) không tự giữ labels

Giả sử panel muốn hiển thị số tool failures theo tool_family. Truy vấn:

~~~promql
sum by (tool_family) (
  rate(app_ai_tool_execution_failed_total[5m])
) or vector(0)
~~~

vector(0) không biết những tool_family nào cần hiển thị. Khi dữ liệu bên trái rỗng, nó chỉ tạo một series không có label tool_family. Khi vế trái có các series mang label tool_family, label set rỗng của vector(0) cũng không khớp với chúng nên có thể xuất thêm một series zero không nhãn bên cạnh các nhóm. Vì vậy, không dùng fallback này cho panel phân nhóm; hãy dùng metric info/pre-initialization nếu cần zero theo từng family.

### 12.2. Tạo fallback theo một tập nhóm đã biết

Nếu ứng dụng có một metric info được khởi tạo cho danh sách tool families được hỗ trợ:

~~~text
app_ai_tool_family_info{tool_family="retrieval"} 1
app_ai_tool_family_info{tool_family="order"} 1
app_ai_tool_family_info{tool_family="payment"} 1
~~~

có thể dùng nó làm tập giá trị chuẩn để tạo zero cho các nhóm không có failure:

~~~promql
sum by (tool_family) (
  rate(app_ai_tool_execution_failed_total[5m])
)
or on (tool_family)
(
  0 * max by (tool_family) (app_ai_tool_family_info)
)
~~~

Vế phải tạo giá trị 0 nhưng giữ label tool_family từ metric info; max by loại bỏ bản sao cùng family từ nhiều instance. Đây là kỹ thuật phù hợp khi **danh sách nhóm kỳ vọng đã biết và được đăng ký ổn định**. Metric info phải được khởi tạo đúng, có cardinality thấp và được giám sát độc lập; nếu chính nó cũng missing, fallback không thể tạo các nhóm mong đợi.

### 12.3. Pre-initialize series thường rõ ràng hơn fallback

Với một tập outcome/tool family hữu hạn, có thể đăng ký Counter ngay khi ứng dụng khởi tạo:

~~~java
for (ToolFamily family : ToolFamily.values()) {
    Counter.builder("app.ai.tool.execution.failed")
            .tag("tool_family", family.value())
            .register(registry);
}
~~~

Khi registry/exporter hỗ trợ và meter đã được đăng ký, series có thể xuất với giá trị ban đầu 0. Nếu dùng lazy instrumentation chỉ tạo meter khi có lỗi, series sẽ không tồn tại cho nhóm chưa từng lỗi.

**Pre-initialize chỉ giải quyết missing do meter chưa được đăng ký trong tập dimensions đã biết.** Nó không giải quyết scrape failure, exporter filter, sai query hoặc target biến mất.

## 13. Counter, Gauge và vòng đời meter trong Micrometer

Micrometer phân biệt giá trị tích lũy với giá trị tức thời. Việc khởi tạo meter và giữ nguồn dữ liệu sống ảnh hưởng tới việc series có xuất hiện hay không.

### 13.1. Counter đăng ký trước và Counter đăng ký khi có lỗi

Đăng ký trước:

~~~java
Counter failures = Counter.builder("app.ai.tool.execution.failed")
        .description("Failed tool executions")
        .tag("tool_family", "retrieval")
        .register(registry);

// Chưa increment; counter đã được đăng ký với giá trị ban đầu 0.
~~~

Đăng ký lazy trong nhánh lỗi:

~~~java
if (toolFailed) {
    Counter.builder("app.ai.tool.execution.failed")
            .tag("tool_family", family)
            .register(registry)
            .increment();
}
~~~

Trong ví dụ thứ hai, nếu tool chưa từng lỗi thì meter có thể chưa được đăng ký và series không xuất hiện. Đây là khác biệt quan trọng khi thiết kế dashboard theo outcome.

### 13.2. Counter chỉ tăng, không dùng để biểu diễn trạng thái hiện tại

Counter biểu diễn tổng sự kiện tích lũy từ khi process/meter bắt đầu. Nếu Counter được đăng ký và chưa có event, giá trị 0 là hợp lệ. Khi process restart, Counter có thể reset; PromQL rate/increase được thiết kế để xử lý counter resets trong điều kiện scrape phù hợp.

Không dùng Counter để biểu diễn số request đang chạy. Dùng Gauge cho trạng thái tức thời.

### 13.3. Gauge bằng 0 khác Gauge không tồn tại

~~~java
AtomicInteger inFlight = new AtomicInteger(0);

Gauge.builder("app.ai.request.inflight",
                inFlight, AtomicInteger::get)
        .register(registry);
~~~

Nếu Gauge được đăng ký và source object còn sống, sample 0 nghĩa là **hiện không có request nào in-flight**. Nếu Gauge chưa được đăng ký, query có thể rỗng. Nếu source object bị thu gom bởi garbage collector, Gauge có thể không còn đo được giá trị mong đợi; cần giữ tham chiếu mạnh đến object trong suốt vòng đời.

### 13.4. FunctionCounter và Gauge dựa trên object

Một số meter đọc giá trị từ object được theo dõi. Nếu object không còn tồn tại, meter có thể ngừng cung cấp giá trị hoặc trả trạng thái không hợp lệ tùy loại và implementation. Không nên đăng ký Gauge với một object tạm thời rồi bỏ tham chiếu ngay sau đó.

Giữ nguồn state sống, kiểm tra scrape và kiểm tra lifecycle của bean/registry.

### 13.5. Không increment một Counter chỉ để tạo zero

Không tăng rồi trừ Counter để cố tạo sample zero; Counter không được thiết kế để giảm. Đăng ký meter mà không increment, hoặc khởi tạo một metric info/gauge phù hợp. Nếu exporter không xuất meter zero theo cấu hình đang dùng, xác minh bằng scrape thay vì giả định.

## 14. Đọc rate() và increase() khi thiếu sample

rate() và increase() cần đủ samples trong range vector để tính biến thiên. Nếu range có ít hơn hai samples, biểu thức thường không tạo kết quả cho series đó.

Ví dụ:

~~~promql
rate(app_ai_tool_execution_failed_total[5m])
~~~

Nếu target chỉ mới scrape một lần trong 5 phút hoặc metric vừa xuất hiện ở cuối cửa sổ, kết quả có thể rỗng. Điều đó **không có nghĩa rate bằng 0**.

### 14.1. Chọn range dựa trên scrape interval và traffic

Nếu scrape interval là 30 giây, range 1 phút thường chỉ có khoảng hai hoặc ba samples khi scrape đều. Nếu có scrape delay, target restart hoặc metric mới xuất hiện, dữ liệu có thể không đủ. Range dài hơn thường tăng khả năng có đủ mẫu nhưng phản ứng chậm hơn.

Chọn cửa sổ phù hợp với scrape interval, lưu lượng thực tế, độ trễ ingestion, mục tiêu alert/dashboard và độ dài của evaluation batch. Không dùng cùng một range cho mọi metric chỉ vì đó là mẫu copy từ dashboard khác.

### 14.2. increase() trả số sự kiện ước lượng trong range

~~~promql
increase(app_ai_tool_execution_failed_total[15m])
~~~

Đây là số tăng Counter ước lượng trong 15 phút, có thể được nội suy theo thời điểm samples ở hai đầu range. Nó không phải lúc nào cũng là số nguyên chính xác nếu scrape không khớp biên thời gian.

Nếu không đủ samples, kết quả vẫn có thể rỗng. Không thêm fallback zero trước khi xác định có traffic và scrape hoạt động.

### 14.3. Tổng hợp không làm dữ liệu thiếu biến thành zero

~~~promql
sum by (tool_family) (
  rate(app_ai_tool_execution_failed_total[5m])
)
~~~

Nếu một tool_family không có series đầu vào, nhóm đó không xuất hiện trong kết quả. sum không tự tạo mọi nhóm trong taxonomy. Cần metric info/pre-initialization nếu dashboard bắt buộc hiển thị tất cả nhóm với zero.

## 15. Evaluation: score bằng 0 khác với chưa có kết quả

Nguyên tắc zero/missing không chỉ áp dụng cho Prometheus. Trong hệ thống đánh giá Spring AI, một giá trị score bằng 0 có thể là kết quả hợp lệ theo rubric; một score không tồn tại có thể là evaluator chưa chạy, evaluator lỗi hoặc case chưa được chấm.

### 15.1. Relevance score

| Trạng thái | Ý nghĩa | Cách báo cáo |
| --- | --- | --- |
| Score = 0.0 | Evaluator đã chấm và đánh giá không liên quan theo rubric | Giữ sample score 0 |
| Score = 0.7 | Evaluator đã chấm, điểm trung bình theo rubric | Giữ sample score 0.7 |
| Score missing | Không có kết quả score | UNKNOWN/NOT_EVALUATED |
| Evaluator timeout | Judge không trả kết quả đúng deadline | EVALUATOR_ERROR hoặc INCONCLUSIVE |
| Case skipped | Case bị bỏ qua theo policy | SKIPPED, không tính như score 0 |

Nếu lấy missing score và tự thay bằng 0, relevance trung bình sẽ thấp giả. Nếu bỏ tất cả missing score khỏi báo cáo mà không công bố coverage, relevance trung bình có thể cao giả do chỉ giữ những ca dễ chấm.

### 15.2. RAG retrieval trả 0 documents

Ba trạng thái khác nhau:

1. **Retrieval executed, valid empty result:** truy vấn thành công nhưng không có tài liệu đủ điều kiện. Số documents retrieved = 0.
2. **Retrieval not executed:** pipeline không gọi retriever, ví dụ route không cần RAG. Đây là NOT_APPLICABLE hoặc NOT_RUN.
3. **Retrieval failed:** vector store timeout hoặc lỗi kết nối; không biết kết quả lẽ ra có bao nhiêu documents.

Không gộp ba trạng thái thành documents=0. Nếu retrieval failed mà ghi 0 documents, dashboard có thể khiến nhóm nghĩ retriever hoạt động tốt nhưng không tìm thấy nguồn.

### 15.3. Fact checking và groundedness

Một claim được chấm:

- SUPPORTED: có bằng chứng hỗ trợ.
- UNSUPPORTED: đã kiểm tra và không tìm thấy bằng chứng đủ.
- CONTRADICTED: nguồn đáng tin mâu thuẫn với claim.
- INCONCLUSIVE: không đủ evidence hoặc evaluator không kết luận.
- NOT_CHECKED: policy không yêu cầu chấm claim này.

Không dùng score 0 cho mọi trạng thái ngoài SUPPORTED. Nếu rubric định nghĩa score 0 cho UNSUPPORTED, phải giữ INCONCLUSIVE/NOT_CHECKED riêng để không biến missing evidence thành kết luận sai.

### 15.4. Token usage bằng 0 khác usage không có

Một model request có thể thực sự dùng 0 output tokens trong trường hợp bị từ chối trước khi generation bắt đầu, nhưng nếu provider không trả usage metadata thì đó là **unknown/missing**, không phải 0 tokens.

Nếu hệ thống tự ước lượng token từ prompt, phải phân biệt provider-reported input/output tokens, application-estimated tokens và usage unavailable. Không ghi estimated=0 khi tokenizer chưa chạy hoặc không có metadata. Không trộn estimated và reported trong cùng một series mà không có chiều source/estimation method rõ ràng.

### 15.5. Cost bằng 0 khác cost chưa biết

Chi phí bằng 0 có thể đúng nếu request được miễn phí theo chính sách, chạy local model không tính phí hoặc chưa phát sinh billable usage. Nhưng nếu không biết giá model, usage hoặc currency, cost là **unknown**, không phải 0 USD.

Không tự tạo cost=0 khi bảng giá thiếu. Báo known estimated cost, provider billed cost nếu có, usage known but price unavailable và usage unavailable. Đồng thời giữ đơn vị tiền tệ và phân biệt estimated với billed.

## 16. PromQL thực hành: phân biệt zero, missing và no traffic

Các tên metric trong ví dụ là custom names do ứng dụng định nghĩa. Phải xác minh scrape thực tế và labels của registry trước khi dùng.

### 16.1. Có traffic hay không?

~~~promql
sum(rate(app_ai_request_started_total[5m]))
~~~

Nếu kết quả là 0 và series tồn tại, có sample quan sát nhưng tốc độ request bằng 0 trong cửa sổ. Nếu query rỗng, chưa có series hoặc không đủ sample. Cần xem thêm up/heartbeat.

### 16.2. Có lỗi hay không?

~~~promql
sum(increase(app_ai_tool_execution_failed_total[15m]))
~~~

Giá trị 0 có nghĩa Counter không tăng trong cửa sổ nếu có đủ sample và series hợp lệ. Empty result không có nghĩa zero failure.

### 16.3. Kiểm tra target health

~~~promql
up{job="spring-ai"}
~~~

Kết hợp với:

~~~promql
absent(up{job="spring-ai"})
~~~

Biểu thức thứ hai phát hiện không có series up khớp selector. Nó không tự biết target kỳ vọng là bao nhiêu; cần expected target inventory hoặc service discovery monitoring.

### 16.4. Kiểm tra metric freshness

~~~promql
time() - app_ai_telemetry_last_successful_observation_timestamp_seconds
~~~

Nếu metric có mặt, giá trị lớn cho biết observation đã cũ. Nếu metric mất hoàn toàn, truy vấn này rỗng; kết hợp absent_over_time để phát hiện missing.

### 16.5. Tính tỷ lệ PASS nhưng không biến thiếu thành 100%

~~~promql
sum(rate(app_ai_eval_case_completed_total{verdict="pass"}[15m]))
/
sum(rate(app_ai_eval_case_completed_total{verdict=~"pass|fail"}[15m]))
~~~

Nếu không có ca PASS/FAIL nào, mẫu số bằng 0 hoặc không có series, tỷ lệ không xác định. Dashboard phải hiển thị N/A/no evaluated cases, không điền 100%.

### 16.6. Coverage của evaluation

Nếu có Counter cases expected và completed theo cùng run scope:

~~~promql
sum(app_ai_eval_case_completed_total)
/
sum(app_ai_eval_case_expected_total)
~~~

Đây chỉ là ví dụ cho một batch hiện tại nếu các metric biểu diễn cùng phạm vi và được reset/version hóa phù hợp. Trong production, Counter tích lũy qua nhiều run không thể chia trực tiếp nếu expected/completed không cùng lifecycle. Có thể dùng Gauge cho batch hiện tại hoặc lưu evaluation run summary ở store chuyên dụng.

### 16.7. Không traffic nhưng telemetry vẫn khỏe

Một panel trạng thái có thể kết hợp:

~~~promql
up{job="spring-ai"} == 1
~~~

và:

~~~promql
sum(rate(app_ai_request_started_total[5m])) or vector(0)
~~~

Truy vấn traffic fallback chỉ có thể được diễn giải là zero khi up=1 và metric request được pre-initialize/được xuất ổn định. Nếu target down hoặc series missing, panel health phải báo riêng. Không dùng một biểu thức fallback duy nhất để đại diện cho cả traffic lẫn health.

### 16.8. clamp_min không sửa missing data

~~~promql
clamp_min(
  sum(rate(app_ai_tool_execution_failed_total[5m])),
  0
)
~~~

clamp_min chỉ giới hạn giá trị của những series có kết quả; nó không tạo series nếu đầu vào empty. Không dùng nó như cách biến missing thành zero.

## 17. Ví dụ Java Micrometer: pre-initialize và theo dõi telemetry

Ví dụ dưới đây minh họa một component đăng ký sẵn Counter cho danh sách tool family hữu hạn, một Counter request, và Gauge trạng thái telemetry. Các tên là custom metrics của ứng dụng.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public final class AiMetricBootstrap {

    public enum ToolFamily {
        RETRIEVAL("retrieval"),
        ORDER("order"),
        PAYMENT("payment"),
        OTHER("other");

        private final String value;

        ToolFamily(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    private final MeterRegistry registry;
    private final AtomicInteger inFlight = new AtomicInteger();
    private final AtomicInteger telemetryReady = new AtomicInteger(0);

    public AiMetricBootstrap(MeterRegistry registry) {
        this.registry = registry;
    }

    public void initialize() {
        // Tạo trước series cho nhóm tool đã biết.
        for (ToolFamily family : ToolFamily.values()) {
            Counter.builder("app.ai.tool.execution.failed")
                    .description("Failed tool executions")
                    .tag("tool_family", family.value())
                    .register(registry);

            Counter.builder("app.ai.tool.execution.completed")
                    .description("Completed tool executions")
                    .tag("tool_family", family.value())
                    .register(registry);
        }

        registry.counter("app.ai.request.started");

        Gauge.builder("app.ai.request.inflight",
                        inFlight, AtomicInteger::get)
                .description("Requests currently in flight")
                .register(registry);

        Gauge.builder("app.ai.telemetry.ready",
                        telemetryReady, AtomicInteger::get)
                .description("Telemetry initialization state")
                .register(registry);

        telemetryReady.set(1);
    }

    public void requestStarted() {
        registry.counter("app.ai.request.started").increment();
        inFlight.incrementAndGet();
    }

    public void requestFinished() {
        inFlight.decrementAndGet();
    }

    public void recordToolFailure(ToolFamily family) {
        registry.counter(
                "app.ai.tool.execution.failed",
                "tool_family", family.value())
                .increment();
    }

    public void recordToolCompleted(ToolFamily family) {
        registry.counter(
                "app.ai.tool.execution.completed",
                "tool_family", family.value())
                .increment();
    }
}
~~~

### 17.1. Điều ví dụ này chứng minh và không chứng minh

Nó chứng minh rằng ứng dụng có thể **đăng ký trước một tập meter hữu hạn** để series zero có cơ hội xuất hiện sau khi registry được scrape. Nó không chứng minh Prometheus đã scrape thành công, endpoint đã được expose, tất cả instance dùng cùng taxonomy, metric không bị filter hoặc một request không bị mất event.

Vì vậy, dashboard vẫn cần up, heartbeat và metric completeness. Đừng coi pre-initialization là bảo đảm end-to-end.

### 17.2. Quản lý Gauge trong finally

Khi cập nhật in-flight, dùng try/finally để không làm Gauge bị kẹt nếu request ném exception:

~~~java
metrics.requestStarted();
try {
    return handleAssistantRequest();
} finally {
    metrics.requestFinished();
}
~~~

Với asynchronous work, chỉ decrement khi Future/Publisher thực sự kết thúc hoặc bị cancel theo contract. Không decrement ngay khi trả về một handle đại diện cho công việc còn đang chạy.

## 18. Kiểm thử phân biệt zero và missing

Một bộ kiểm thử metric nên xác minh không chỉ giá trị mà cả **sự hiện diện của series, điều kiện khởi tạo, coverage và trạng thái scrape**.

### 18.1. Test registry: meter được đăng ký với zero

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class ZeroVersusMissingTest {

    @Test
    void registeredCounterExistsAtZeroBeforeAnyFailure() {
        var registry = new SimpleMeterRegistry();

        Counter.builder("app.ai.tool.execution.failed")
                .tag("tool_family", "retrieval")
                .register(registry);

        var found = registry.find("app.ai.tool.execution.failed")
                .tag("tool_family", "retrieval")
                .counter();

        assertNotNull(found);
        assertEquals(0.0, found.count());
    }

    @Test
    void lazyCounterIsAbsentUntilFailurePathRuns() {
        var registry = new SimpleMeterRegistry();

        var before = registry.find("app.ai.tool.execution.failed")
                .tag("tool_family", "payment")
                .counter();

        // Chưa đăng ký meter cho payment.
        assertNull(before);

        Counter.builder("app.ai.tool.execution.failed")
                .tag("tool_family", "payment")
                .register(registry)
                .increment();

        var after = registry.find("app.ai.tool.execution.failed")
                .tag("tool_family", "payment")
                .counter();

        assertNotNull(after);
        assertEquals(1.0, after.count());
    }
}
~~~

Ví dụ dùng SimpleMeterRegistry để kiểm tra logic đăng ký của Micrometer. Để xác nhận tên series và giá trị trong Prometheus exposition, cần integration test bằng Prometheus registry tương ứng.

### 18.2. Test query và scrape

Trong môi trường tích hợp:

1. Khởi động ứng dụng với registry/exporter được cấu hình.
2. Xác minh endpoint metrics và Prometheus scrape thành công.
3. Xác minh meter đã đăng ký xuất sample zero nếu contract yêu cầu.
4. Không gọi code path lazy và xác nhận series chưa xuất hiện.
5. Kích hoạt event đầu tiên và xác nhận series xuất hiện với giá trị đúng.
6. Làm target scrape thất bại có kiểm soát trong test môi trường; xác nhận dashboard/alert không chuyển lỗi scrape thành zero.
7. Kiểm tra query rate với range có ít hơn hai samples và xác nhận dashboard thể hiện No data.

### 18.3. Test evaluation coverage

Với batch fixture:

- 100 cases expected.
- 96 completed.
- 80 PASS.
- 12 FAIL.
- 4 INCONCLUSIVE.
- 4 not completed.

Kiểm tra báo cáo giữ riêng completion coverage, pass rate trên decided cases, inconclusive rate và not completed. Không thay missing verdict bằng score 0.

### 18.4. Test retrieval empty và retrieval failure

Tạo hai ca:

1. Retriever chạy thành công, trả empty list.
2. Retriever ném timeout exception.

Ca thứ nhất ghi retrieval execution success và documents count bằng 0. Ca thứ hai ghi outcome timeout/error; documents count không được tự động ghi 0 như thể truy vấn đã hoàn tất. Nếu có metric documents count, phải có trạng thái hoặc outcome đi kèm để diễn giải.

## 19. Bài thực hành

**Bối cảnh:** một ứng dụng Spring AI có ChatClient, tool tra cứu đơn, retriever chính sách và evaluation runner. Dashboard hiện 0 tool failures nhưng nhóm không biết liệu tool chưa được gọi hay đã chạy mà không lỗi.

### Phần A — Phân loại trạng thái

Với mỗi tình huống, quyết định đó là zero, missing, no traffic, no evaluation data hay telemetry unavailable:

1. Counter tool failure đã được đăng ký và có giá trị 0.
2. Counter tool failure chỉ được tạo khi có exception; chưa có tool nào lỗi.
3. Prometheus target có up=0.
4. Prometheus query trả empty vector vì filter tool_family không khớp.
5. Có 20 retrieval executions thành công, mỗi lần trả 0 documents.
6. Retriever không được gọi vì route là chat-only.
7. Evaluator timeout nên không có relevance score.
8. Evaluator chấm relevance score đúng bằng 0.
9. Evaluation batch chưa được chạy.
10. Evaluation batch có 100 expected cases, chỉ 80 completed.

### Phần B — Viết PromQL

1. Query kiểm tra target scrape health.
2. Query phát hiện metric family không có sample trong 10 phút.
3. Query tính số lỗi trong 15 phút khi series tồn tại.
4. Query phân biệt không có traffic với target down.
5. Query dùng metric info để tạo zero theo tool_family đã biết.
6. Query tính pass rate nhưng không trả 100% khi chưa có ca được chấm.
7. Query kiểm tra tuổi của lần telemetry observation gần nhất.

### Phần C — Thiết kế instrumentation

1. Đăng ký trước Counter cho retrieval, order và payment.
2. Tạo Gauge in-flight với source object được giữ sống.
3. Tạo heartbeat/telemetry ready metric.
4. Quy định metric nào lazy và metric nào pre-initialize.
5. Viết test chứng minh series zero khác series missing.
6. Xác minh scrape output và dashboard No Data behavior.

### Phần D — Phân tích báo cáo evaluation

Một batch có 100 cases expected: 80 PASS, 12 FAIL, 4 INCONCLUSIVE, 4 chưa hoàn tất.

1. Tính completion coverage.
2. Tính pass rate trên decided cases.
3. Tính pass yield trên toàn bộ cases expected.
4. Giải thích vì sao không được thay bốn ca INCONCLUSIVE hoặc bốn ca chưa hoàn tất bằng score 0.
5. Nếu relevance score trung bình của 92 ca có kết luận là 0,82, cần công bố coverage và phạm vi mẫu như thế nào?

### Câu hỏi tự kiểm tra

- Vì sao query trả empty vector không có nghĩa là metric bằng 0?
- sum() trên empty vector có tự trả scalar 0 không?
- or vector(0) có giữ label values của các nhóm không?
- Khi nào nên pre-initialize Counter?
- Vì sao Gauge bằng 0 khác Gauge không tồn tại?
- Target up=0 có chứng minh ứng dụng không chạy không?
- absent() có phát hiện một label combination bị thiếu khi các nhóm khác vẫn tồn tại không?
- Vì sao rate() có thể rỗng khi series mới chỉ có một sample?
- Vì sao một batch evaluation chưa chạy không có pass rate 0% hoặc 100%?
- Relevance score 0 khác missing score ở đâu?
- Retrieval trả empty list khác retrieval timeout thế nào?
- Làm sao dashboard phân biệt No traffic với Telemetry unavailable?

## 20. Những điều cần ghi nhớ

1. **Zero là một giá trị được quan sát; missing là thiếu bằng chứng.** Không chuyển empty query thành zero một cách tự động.
2. **Empty vector, NaN và stale series không phải số 0.** Kiểm tra raw query result, sample timestamps và scrape health.
3. **up=0 khác up missing.** Một target scrape thất bại khác với target không có trong discovery hoặc không còn series.
4. **Meter lifecycle quyết định series có xuất hiện hay không.** Pre-initialize meter cho các dimension hữu hạn khi cần zero rõ ràng.
5. **or vector(0) không giữ labels và có thể che scrape/query failure.** Chỉ dùng fallback khi có expected dimensions và tín hiệu health độc lập.
6. **rate()/increase() cần đủ samples.** Query rỗng vì thiếu mẫu không đồng nghĩa rate bằng 0.
7. **No traffic khác No data.** Heartbeat, target health và request counters cần được quan sát riêng.
8. **Evaluation score 0 khác chưa chấm.** Giữ INCONCLUSIVE, SKIPPED, evaluator error và missing evidence riêng.
9. **Retrieval empty result khác retrieval failure.** Chỉ ghi documents=0 khi truy vấn đã chạy và trả kết quả hợp lệ.
10. **Dashboard và alert phải thể hiện completeness/freshness.** Tránh false green do null handling hoặc fallback zero.

## Tài liệu tham khảo

- [Prometheus — Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/): instant vector, range vector, selector và lookback.
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): absent, absent_over_time, rate, increase và time.
- [Prometheus — Operators](https://prometheus.io/docs/prometheus/latest/querying/operators/): set operators, or, unless và vector matching.
- [Prometheus — Jobs and Instances](https://prometheus.io/docs/concepts/jobs_instances/): metric up và target scrape status.
- [Prometheus — Staleness](https://prometheus.io/docs/prometheus/latest/querying/basics/#staleness): hành vi series stale và instant selectors.
- [Micrometer Reference — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): Counter registration và semantics.
- [Micrometer Reference — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html): Gauge, object lifecycle và giá trị tức thời.
- [Micrometer Reference — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): lọc meter và giới hạn tag values.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): registry, endpoint và metric export.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): observability cho ChatClient, model và tool.
- [Grafana Documentation — Alert rule evaluation](https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rule-evaluation/): trạng thái No Data và Error trong alert evaluation.

**Lưu ý phiên bản:** hành vi export meter zero, endpoint Actuator, Prometheus lookback/staleness và Grafana No Data phụ thuộc cấu hình, phiên bản và loại datasource. Các tên app.ai trong bài là metric ví dụ do ứng dụng tự định nghĩa. Trước khi triển khai, xác minh registry, scrape output, query result và dashboard behavior của chính môi trường đang chạy.

