# Mô hình tải mở, tải đóng và sai lệch do bỏ sót thời gian chờ

Trong chương **Kiểm thử hiệu năng** của module **DATABASE_PERFORMANCE**, mô hình tải quyết định cách công cụ tạo request trong khi hệ thống đang xử lý. Hai mô hình phổ biến là **tải đóng** (*closed workload model*) và **tải mở** (*open workload model*). Tải đóng giữ số người dùng hoặc client đồng thời ở một mức nhất định; mỗi client thường chờ request hiện tại hoàn tất rồi mới gửi request tiếp theo. Tải mở tạo request theo tốc độ đến đã định trước, độc lập với thời gian hoàn tất của request trước.

Chọn sai mô hình có thể làm kết quả benchmark không phản ánh production. Đặc biệt, tải đóng có thể tạo ra **coordinated omission**: khi hệ thống chậm, chính load generator cũng chậm phát request, khiến những khoảng thời gian mà request đáng lẽ phải chờ không được ghi nhận đầy đủ. Báo cáo latency khi đó có thể đẹp hơn trải nghiệm thực tế dưới một tốc độ đến cố định.

Để đánh giá đúng năng lực database, cần xác định production có hành vi đến theo số client đồng thời hay theo tốc độ request độc lập; đo cả tải được yêu cầu, tải thực sự phát ra, tải hoàn tất, queue và latency; đồng thời kiểm soát năng lực của chính load generator. Mục tiêu là kiểm tra hệ thống dưới một mô hình đến phù hợp với workload, phát hiện điểm bão hòa và hiểu rõ khi nào độ trễ tăng do database, ứng dụng hay bộ tạo tải.

## 1. Hai cách tạo tải khác nhau

### 1.1. Tải đóng: giữ số client đồng thời

Trong mô hình tải đóng, công cụ tạo một số lượng client hoặc virtual user cố định. Mỗi client thực hiện một chu trình:

1. Gửi request.
2. Chờ response hoàn tất.
3. Có thể nghỉ một khoảng think time.
4. Gửi request tiếp theo.

Nếu một request mất nhiều thời gian hơn, client đó chưa thể bắt đầu request tiếp theo. Số client đang hoạt động vẫn cố định, nhưng tốc độ phát request giảm theo độ trễ của hệ thống.

Ví dụ: 100 virtual user liên tục xem danh sách đơn hàng. Mỗi user chờ response, đọc kết quả trong 1 giây rồi mới gửi request tiếp. Khi API tăng từ 100 ms lên 1 giây, mỗi user gửi request ít thường xuyên hơn. Tải đưa vào database vì vậy có thể giảm ngay khi database chậm.

Tải đóng phù hợp với workload mà số người dùng đồng thời hoặc số worker cố định là đặc trưng chính, chẳng hạn ứng dụng tương tác có think time, worker pool hữu hạn hoặc một nhóm client giữ kết nối và gửi request tuần tự.

### 1.2. Tải mở: giữ tốc độ request đến

Trong mô hình tải mở, công cụ lên lịch request theo một arrival rate đã chọn, ví dụ 200 request/giây. Lịch phát request không phụ thuộc vào việc request trước đã hoàn tất hay chưa.

Ví dụ: một hệ thống nhận sự kiện từ nhiều thiết bị với tốc độ trung bình 200 sự kiện/giây. Dù một số request mất 2 giây, hệ thống vẫn tiếp tục nhận sự kiện mới theo tốc độ đến đã định. Số request đang chờ hoặc đang xử lý có thể tăng khi năng lực phục vụ không đủ.

Tải mở phù hợp khi nguồn request độc lập với response time của database, ví dụ:

- API nhận webhook hoặc sự kiện từ hệ thống bên ngoài.
- Luồng telemetry gửi dữ liệu theo lịch.
- Hệ thống đặt hàng nhận traffic đến theo tốc độ của người dùng và chiến dịch.
- Queue consumer nhận message theo tốc độ producer đưa vào.
- Workload nền có lịch chạy cố định hoặc batch được phát theo tốc độ mục tiêu.

Trong tải mở, cần phân biệt tốc độ **được lên lịch**, tốc độ **thực sự bắt đầu**, tốc độ **được server chấp nhận** và tốc độ **hoàn tất**. Nếu load generator không đủ VU, connection hoặc CPU để phát request đúng lịch, công cụ có thể bỏ lỡ iteration; khi đó phép thử không còn tạo đúng arrival rate đã khai báo.

### 1.3. So sánh nhanh

| Đặc điểm | Tải đóng | Tải mở |
|---|---|---|
| Điều được giữ cố định | Số client/virtual user đồng thời | Tốc độ request đến hoặc lịch arrival |
| Khi response chậm | Client chờ, request tiếp theo bị trì hoãn | Request mới vẫn được lên lịch |
| Concurrency | Thường biến thiên theo response time và think time | Tăng/giảm theo arrival rate và thời gian xử lý |
| Queue khi quá tải | Có thể bị che vì client tự giảm tốc | Thường thể hiện rõ bằng queue tăng, latency tăng hoặc request bị drop |
| Phù hợp | Người dùng tương tác, worker cố định, client tuần tự | Event stream, webhook, traffic đến độc lập, tốc độ ingest |
| Rủi ro đo lường | Coordinated omission khi hệ thống chậm | Generator không theo kịp lịch hoặc tạo queue không giới hạn |

Không có mô hình nào luôn đúng hơn. Cần chọn theo cơ chế phát sinh request của hệ thống thật; với nhiều ứng dụng, nên kiểm thử cả hai để trả lời hai câu hỏi khác nhau.

## 2. Quan hệ giữa concurrency, throughput và response time

### 2.1. Tải đóng và công thức interactive response time

Với mô hình closed-loop đơn giản, số client đồng thời là (N), thời gian response trung bình là (R), think time trung bình là (Z). Throughput xấp xỉ:

\[
X = \frac{N}{R + Z}
\]

Trong đó (X) là số chu trình hoàn tất mỗi giây. Công thức giả định mỗi client chỉ có một request đang chờ tại một thời điểm và các chu trình có thể được mô tả bằng thời gian trung bình.

Ví dụ có 100 client, mỗi request mất 0,2 giây và think time là 0,8 giây:

\[
X = \frac{100}{0.2 + 0.8} = 100\ requests/s
\]

Nếu response time tăng lên 1,2 giây, trong khi think time không đổi:

\[
X = \frac{100}{1.2 + 0.8} = 50\ requests/s
\]

Tải phát ra giảm một nửa dù số client vẫn là 100. Đây là hành vi tự điều tiết tự nhiên của mô hình đóng.

### 2.2. Tải mở và tốc độ đến

Trong mô hình open-loop, arrival rate λ được cấu hình độc lập với response time. Nếu hệ thống có năng lực phục vụ μ request/giây và λ thấp hơn μ trong điều kiện ổn định, hệ thống có thể xử lý tải mà không làm queue tăng liên tục.

Nếu tốc độ đến duy trì cao hơn năng lực phục vụ, backlog sẽ tăng. Với queue không giới hạn, thời gian chờ và số request đang tồn tại có thể tăng mãi; với queue có giới hạn, hệ thống cuối cùng phải reject, timeout, drop hoặc backpressure request.

Ví dụ, producer gửi 900 request/giây nhưng hệ thống chỉ hoàn tất bền vững 750 request/giây. Mỗi giây backlog tăng trung bình khoảng 150 request trong khi điều kiện tải giữ nguyên. Một bài test chỉ kéo dài 10 giây có thể chưa bộc lộ hết hậu quả; soak test lâu hơn sẽ cho thấy queue và latency tiếp tục tăng.

### 2.3. Định luật Little

Định luật Little mô tả quan hệ giữa số request trung bình trong hệ thống, throughput hoàn tất và thời gian trung bình một request ở trong hệ thống:

\[
L = \lambda W
\]

Trong đó:

- (L): số request trung bình đang ở trong phạm vi đo, gồm cả đang chờ và đang xử lý nếu phạm vi được định nghĩa như vậy.
- λ: throughput hoàn tất trung bình trong trạng thái ổn định.
- (W): thời gian trung bình request ở trong phạm vi đo.

Ví dụ, hệ thống hoàn tất 500 request/giây và mỗi request ở trong hệ thống trung bình 0,1 giây thì số request trung bình đang tồn tại xấp xỉ 50.

Trong hệ thống ổn định, arrival rate và completion rate dài hạn phải cân bằng nếu backlog không tăng. Khi đang quá tải, không được lấy offered arrival rate thay cho throughput hoàn tất trong công thức Little mà bỏ qua backlog tăng. Cần xác định rõ phạm vi đo và dùng cùng một định nghĩa cho các đại lượng.

## 3. Coordinated omission là gì?

Coordinated omission là sai lệch đo lường xảy ra khi load generator chỉ ghi latency cho những request nó thực sự gửi, trong khi việc gửi request tiếp theo lại phụ thuộc vào response trước. Khi hệ thống bị pause hoặc chậm kéo dài, generator cũng ngừng phát request trong khoảng đó. Những request đáng lẽ đã đến trong thời gian hệ thống bị chậm không xuất hiện trong histogram, khiến tail latency bị đánh giá thấp.

### 3.1. Ví dụ một hệ thống bị pause

Giả sử production có tốc độ đến 100 request/giây, tương đương một request mỗi 10 ms. Database hoặc ứng dụng bị pause 2 giây do GC, I/O stall hoặc một sự kiện khác.

Trong 2 giây đó, theo mô hình tải mở sẽ có khoảng 200 request mới đến. Những request này phải chờ trong queue, bị reject hoặc hết timeout. Nếu đo từ thời điểm đến dự kiến tới lúc hoàn tất, latency của chúng bao gồm cả khoảng chờ trong 2 giây pause.

Nhưng với một load generator closed-loop có 100 client:

1. Các client gửi request.
2. Request đang chạy bị chậm hoặc không nhận response trong 2 giây.
3. Các client chờ response và không gửi request tiếp theo.
4. Trong khoảng pause, generator không tạo đủ request mới theo tốc độ 100 request/giây.
5. Histogram chỉ ghi những request đã được gửi, nên phần lớn thời gian mà một arrival rate cố định phải chờ không được phản ánh.

Kết quả có thể cho thấy số request thấp hơn nhiều, nhưng latency ghi nhận của các request đã phát ra không phản ánh đầy đủ độ trễ mà traffic đến liên tục phải chịu.

### 3.2. Minh họa timeline

```text
Thời gian:       0 ms        100 ms                 2.100 ms
                  |------------|------------------------|
Arrival cố định:  x x x x x x x x x x x x x x x x x ...
System:           xử lý bình thường | PAUSE 2 giây | phục hồi
Open generator:   vẫn lên lịch request; queue/timeout tăng
Closed generator: client đang chờ response; request mới giảm hoặc dừng
```

Đây không chỉ là vấn đề của cách tính percentile. Các request không được phát ra đã không có sample latency để đưa vào histogram. Nếu generator ghi thời điểm bắt đầu thực tế thay cho thời điểm đến dự kiến, thời gian chờ trước khi gửi cũng bị bỏ qua.

### 3.3. Vì sao percentile có thể đẹp giả tạo?

Giả sử 10.000 request đã gửi có latency chủ yếu từ 20–80 ms, nhưng một pause khiến nhiều arrival dự kiến phải chờ 2 giây. Nếu các arrival đó không được tạo hoặc không được tính từ thời điểm đến dự kiến, p99 của tập sample thực tế có thể vẫn dưới 100 ms. Người vận hành có thể kết luận hệ thống đạt SLO dù người dùng hoặc producer thực tế phải chờ lâu hơn.

Coordinated omission đặc biệt nguy hiểm khi:

- Hệ thống có pause dài hoặc latency spike.
- Load test dùng số virtual user cố định và mỗi user chờ response.
- Công cụ chỉ đo từ lúc gửi request thực tế, không tính thời gian chờ theo lịch arrival.
- Mục tiêu production là tốc độ đến cố định nhưng test lại tự giảm tốc khi server chậm.
- Đánh giá p99/p99.9 dựa trên histogram thiếu sample trong khoảng quá tải.

## 4. Phân biệt response time và thời gian chờ trước khi gửi

Để tránh sai lệch, cần phân biệt các mốc thời gian:

1. **Scheduled arrival time:** thời điểm request đáng lẽ phải được tạo theo lịch tải.
2. **Actual start/dispatch time:** thời điểm load generator thực sự bắt đầu gửi request.
3. **Server receive time:** thời điểm server nhận request.
4. **Service completion time:** thời điểm server hoàn tất xử lý.
5. **Client completion time:** thời điểm client nhận đủ response.

Có thể định nghĩa hai loại latency:

\[
L_{service} = t_{client\ completion} - t_{actual\ dispatch}
\]

\[
L_{end-to-end} = t_{client\ completion} - t_{scheduled\ arrival}
\]

`L_service` đo thời gian từ lúc gửi thực tế tới khi nhận xong response. `L_end-to-end` còn tính thời gian request phải chờ trong load generator trước khi được gửi đúng lịch. Nếu generator không bao giờ tạo request bị trễ mà bỏ luôn iteration, cần ghi nhận dropped/missed arrival riêng; không thể suy ra latency của request đã bị bỏ chỉ từ các request còn lại.

Đối với API, thời gian từ lúc server nhận request tới lúc response hoàn tất có thể giúp phân tích service time. Đối với trải nghiệm người dùng hoặc hệ thống event có arrival rate cố định, end-to-end latency từ thời điểm đến dự kiến thường phản ánh đầy đủ hơn.

## 5. Cách giảm coordinated omission

### 5.1. Dùng mô hình tải mở khi arrival rate độc lập

Nếu production nhận request theo tốc độ độc lập với response time, hãy dùng open workload generator. Lên lịch arrival theo tốc độ mục tiêu và tiếp tục tạo request trong khi request trước còn đang chạy, trong giới hạn concurrency đã đặt.

Điều này làm lộ queue và latency tăng khi hệ thống không theo kịp. Tuy nhiên, phải theo dõi dropped arrival và bảo đảm load generator đủ CPU, network, connection và VU để phát đúng lịch.

### 5.2. Đo từ thời điểm arrival dự kiến

Với mỗi request, giữ timestamp dự kiến và timestamp thực tế. Nếu request được dispatch trễ, latency end-to-end phải bao gồm phần chờ đó. Nếu request bị bỏ, ghi nhận là missed/dropped arrival và đưa vào chỉ số availability hoặc load-generator capacity; không loại âm thầm khỏi báo cáo.

Không cộng một giá trị latency giả cho mọi request bị drop mà không nêu quy tắc. Hãy báo riêng:

- Offered arrivals.
- Started requests.
- Completed requests.
- Rejected/failed requests.
- Dropped/missed iterations tại generator.
- Queue delay trước dispatch.
- Service latency và end-to-end latency.

### 5.3. Hiệu chỉnh histogram khi chỉ có closed-loop data

Một số thư viện histogram, ví dụ HDR Histogram, hỗ trợ coordinated-omission correction bằng cách bổ sung các giá trị giả định theo một expected interval. Cách này có thể giúp ước lượng tác động của các request bị bỏ lỡ khi biết chu kỳ phát request dự kiến.

Ví dụ, nếu một request mất 100 ms trong workload dự kiến một request mỗi 10 ms, hiệu chỉnh có thể thêm các sample đại diện cho những arrival bị bỏ qua trong khoảng đó. Nhưng đây là phép hiệu chỉnh dựa trên giả định, không tái tạo hoàn toàn queue, concurrency, timeout và hành vi server thực tế. Nó không thay thế một bài test open-loop phù hợp.

### 5.4. Đừng nhầm hiệu chỉnh với giảm latency

Coordinated-omission correction làm histogram phản ánh tốt hơn các khoảng chờ có thể đã bị bỏ qua; nó không làm hệ thống nhanh hơn. Nếu percentile sau hiệu chỉnh xấu đi, đó là thông tin về độ trễ mà mô hình đo ban đầu đã che khuất.

Không tự ý trừ think time, thời gian nghỉ hoặc một hằng số khỏi response time để làm đẹp kết quả. Chỉ loại thời gian khi định nghĩa metric và mục tiêu đo thực sự yêu cầu, đồng thời phải báo rõ metric đã loại phần nào.

## 6. Ví dụ tải đóng và tải mở bằng k6

k6 cung cấp các executor khác nhau để mô phỏng hai mô hình. Các ví dụ sau dùng endpoint minh họa; thay bằng endpoint của môi trường kiểm thử và dùng dữ liệu thử an toàn.

### 6.1. Tải đóng với số virtual user cố định

```javascript
import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  scenarios: {
    closed_workload: {
      executor: 'constant-vus',
      vus: 50,
      duration: '5m',
    },
  },
};

export default function () {
  http.get('https://test.example.internal/orders');
  sleep(1); // think time sau response
}
```

Mỗi virtual user thực hiện một iteration, chờ response, nghỉ một giây rồi mới bắt đầu iteration tiếp theo. Khi endpoint chậm, tốc độ iteration giảm. Đây là hành vi phù hợp để mô phỏng 50 user tương tác có think time, nhưng không bảo đảm giữ một arrival rate cố định.

### 6.2. Tải mở với tốc độ arrival cố định

```javascript
import http from 'k6/http';

export const options = {
  scenarios: {
    open_workload: {
      executor: 'constant-arrival-rate',
      rate: 100,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<250', 'p(99)<500'],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  http.get('https://test.example.internal/orders');
}
```

Executor này lên lịch 100 iteration mỗi giây trong 5 phút, độc lập với thời gian hoàn tất iteration trước. Mỗi iteration trong ví dụ chỉ gửi một HTTP request; nếu một iteration chứa nhiều request, số HTTP request/giây sẽ lớn hơn arrival rate của iteration.

`preAllocatedVUs` cấp trước số VU để giảm việc cấp phát trong lúc chạy; `maxVUs` giới hạn mở rộng. Nếu không có VU sẵn sàng khi arrival tới, k6 có thể ghi nhận `dropped_iterations`. Ngưỡng `count==0` yêu cầu không có iteration bị bỏ. Nếu metric này khác 0, cần xem generator có đủ năng lực hay không trước khi kết luận database không đáp ứng tải.

### 6.3. So sánh kết quả hai mô hình

Giả sử cùng endpoint:

| Chỉ số | Tải đóng | Tải mở |
|---|---|---|
| Cấu hình chính | 50 VU, think time 1 giây | 100 iteration/giây |
| Khi response tăng từ 100 ms lên 1 giây | Throughput giảm do VU chờ | Arrival tiếp tục được lên lịch |
| Concurrency đang xử lý | Xấp xỉ bị giới hạn bởi số VU | Có thể tăng khi response kéo dài |
| Queue phía server | Có thể không tăng nhiều vì client tự giảm tốc | Tăng nếu arrival vượt service capacity |
| Chỉ số cần chú ý | VU, iteration rate, response time | Scheduled/started/completed, dropped iterations, queue và latency |

Hai kết quả trả lời hai câu hỏi khác nhau. Không so sánh latency của hai bài như thể chúng dùng cùng một workload model.

## 7. Ví dụ tải mở bằng mô hình arrival rate trong JMeter

JMeter Thread Group thông thường hoạt động gần với mô hình đóng: mỗi thread chạy sampler, chờ sampler hoàn tất, thực hiện timer nếu có rồi mới chạy vòng tiếp theo. Khi server chậm, thread tạo request mới chậm theo.

Nếu cần giữ tốc độ arrival độc lập, có thể dùng Open Model Thread Group hoặc plugin/element hỗ trợ arrival rate trong phiên bản JMeter đang triển khai. Cấu hình cần nêu rõ:

- Arrival rate mục tiêu và đơn vị thời gian.
- Ramp-up và thời lượng giữ tải.
- Số thread/worker tối đa.
- Hành vi khi không đủ thread để phát request đúng lịch.
- Queue hoặc dropped sample nếu có.
- Cách đo thời điểm dự kiến và thời điểm thực sự bắt đầu.

Constant Throughput Timer trong JMeter có thể điều tiết throughput của sampler theo cách cấu hình, nhưng không nên mặc định rằng nó tạo ra một mô hình open-loop hoàn chỉnh. Cần kiểm tra semantics của timer, thread group, scheduler và khả năng tạo request khi sampler trước còn chạy. Đọc tài liệu đúng phiên bản/plugin và xác nhận bằng timestamp thực tế.

## 8. Chọn mô hình theo loại workload

| Workload | Mô hình nên ưu tiên | Lý do |
|---|---|---|
| Người dùng web gửi request, chờ kết quả rồi thao tác tiếp | Closed | Số user đồng thời và think time là đặc trưng |
| API nhận webhook theo tốc độ đối tác gửi | Open | Arrival không chờ response của request trước |
| Ingest telemetry theo chu kỳ thiết bị | Open | Tốc độ sự kiện đến tương đối độc lập |
| Consumer xử lý queue với số worker cố định | Closed cho từng worker, kết hợp open ở producer/queue | Worker chờ message hoàn tất; producer có thể tiếp tục đưa message vào queue |
| Batch ETL chạy theo lịch | Open hoặc workload theo lịch/batch | Cần mô phỏng thời điểm và tốc độ nạp dữ liệu |
| Pool worker xử lý tác vụ nền | Closed ở worker pool; open ở hàng đợi đầu vào | Số worker hữu hạn nhưng backlog có thể tăng |
| Hệ thống báo cáo có người dùng tương tác | Closed cho người dùng, có thể thêm open cho scheduled reports | Hai nguồn tải có hành vi khác nhau |
| Traffic chiến dịch có burst | Open với arrival profile theo thời gian | Cần kiểm tra queue và khả năng hấp thụ burst |

Trong thực tế, hệ thống có thể là hỗn hợp. Ví dụ API nhận order theo tốc độ mở, sau đó đưa event vào queue; worker xử lý với số lượng concurrency đóng. Kiểm thử nên mô hình hóa cả producer arrival, queue depth và consumer throughput để thấy backlog đầu-cuối.

## 9. Tác động của mô hình tải tới database

### 9.1. Connection pool và số request đồng thời

Trong tải đóng, số client cố định có thể tạo số connection tương đối ổn định nếu mỗi VU giữ một connection hoặc pool được cấu hình tương ứng. Trong tải mở, khi response time tăng, số request đang chờ có thể tăng nhanh; nếu mỗi request giữ connection trong suốt thời gian chờ, pool có thể cạn và tạo queue ở ứng dụng.

Không nhất thiết một HTTP request tương ứng một database connection. Connection pool, transaction boundary, async processing và cache có thể thay đổi quan hệ này. Hãy đo riêng:

- HTTP request đang hoạt động.
- Request chờ application worker.
- Request chờ connection pool.
- Database session đang chạy và đang idle.
- Transaction đang mở và lock đang giữ.

### 9.2. Queue có thể xuất hiện ở nhiều tầng

Khi tải tăng, request có thể chờ ở:

1. Load generator trước khi dispatch.
2. Network hoặc load balancer.
3. Web server/application worker pool.
4. Application connection pool.
5. Database admission control hoặc worker queue.
6. Lock manager, I/O queue hoặc log flush.

Chỉ nhìn database CPU sẽ không xác định được toàn bộ độ trễ. Cần trace request và metric queue theo từng tầng để biết thời gian bị tiêu thụ ở đâu.

### 9.3. Database bão hòa và backlog

Nếu open arrival rate vượt sustainable capacity, queue tăng. Khi request chờ lâu, transaction có thể giữ connection, memory hoặc lock lâu hơn; retry từ client có thể làm arrival rate tăng thêm. Đây là vòng lặp khuếch đại quá tải.

Đặt timeout, queue limit, admission control và backpressure theo thiết kế. Nếu queue đã vượt giới hạn, reject sớm có thể bảo vệ hệ thống và giữ latency cho request được nhận. Một bài load test cần ghi nhận rejection và timeout, không chỉ tính latency của request thành công.

## 10. Thiết kế profile tải cho bài kiểm thử

Không nên chỉ chạy một tốc độ cố định. Một profile đầy đủ có thể gồm nhiều giai đoạn:

### 10.1. Warm-up

Tăng tải nhẹ để khởi tạo connection pool, JIT, cache, prepared statement và các cấu trúc cần thiết. Tách warm-up khỏi cửa sổ đo chính để không trộn startup overhead với steady-state.

### 10.2. Ramp-up

Tăng arrival rate hoặc số VU theo bậc. Mục tiêu là quan sát khi nào throughput bắt đầu không theo kịp tải, p95/p99 tăng và queue hình thành. Với open model, ramp arrival rate; với closed model, ramp số VU.

### 10.3. Steady-state

Giữ tải mục tiêu đủ lâu để đo throughput, latency, CPU, I/O, log, memory và replication. Không chọn thời gian quá ngắn khiến cache hoặc storage burst che giấu vấn đề.

### 10.4. Spike/burst

Tăng tải nhanh trong thời gian ngắn để kiểm tra khả năng hấp thụ burst, queue limit và thời gian phục hồi. Ghi cả thời gian backlog trở về mức bình thường sau khi burst kết thúc.

### 10.5. Soak

Giữ tải trong thời gian dài để phát hiện memory leak, connection leak, cache churn, autovacuum/purge backlog, checkpoint, log growth và storage thermal/GC behavior.

### 10.6. Overload và recovery

Trong môi trường kiểm thử được kiểm soát, tăng tải vượt capacity để quan sát cách hệ thống bảo vệ chính nó: reject, timeout, backpressure, queue cap, circuit breaker và recovery. Không chạy overload test trên production nếu chưa có phạm vi, ngưỡng dừng và kế hoạch bảo vệ được phê duyệt.

## 11. Đo offered load, achieved load và latency đầy đủ

Một báo cáo benchmark nên tách các đại lượng sau:

| Đại lượng | Ý nghĩa |
|---|---|
| Offered arrival rate | Tốc độ request được lên lịch hoặc đưa vào hệ thống |
| Started/dispatch rate | Tốc độ generator thực sự bắt đầu gửi request |
| Accepted rate | Tốc độ server hoặc queue chấp nhận request |
| Completion throughput | Tốc độ request hoàn tất thành công hoặc kết thúc xử lý |
| Error/reject rate | Request thất bại, bị từ chối hoặc timeout |
| Dropped/missed arrival | Arrival không được phát đúng lịch do generator hoặc giới hạn tải |
| Queue delay | Thời gian chờ trước khi được xử lý ở một tầng |
| Service latency | Thời gian từ lúc bắt đầu xử lý tới hoàn tất theo định nghĩa đo |
| End-to-end latency | Thời gian từ arrival dự kiến hoặc thời điểm người dùng bắt đầu tới kết quả |

Không gộp error, reject và dropped arrival thành một loại. Server reject do quá tải là kết quả của hệ thống; generator bỏ iteration do thiếu VU là giới hạn của phép thử. Hai trường hợp cần cách xử lý khác nhau.

### 11.1. Histogram và percentile

Ghi histogram latency thay vì chỉ lấy average. Với mỗi cửa sổ thời gian, báo p50, p90, p95, p99 và số sample. Khi so sánh nhiều instance hoặc nhiều worker, cần merge histogram theo cách giữ phân phối và count; không lấy trung bình các p99 riêng lẻ.

Percentile ở sample nhỏ có thể không ổn định. Ví dụ p99 trên 100 sample chỉ gần tương ứng một sample ở phần đuôi. Cần đủ số request và cửa sổ đo phù hợp để kết luận về tail latency.

### 11.2. Tách latency của generator và server

Đo CPU, memory, network, socket và event loop của load generator. Nếu generator bão hòa, request có thể được phát chậm hoặc histogram bị méo. Chạy nhiều generator node khi cần, nhưng phải đồng bộ thời gian và cộng offered load chính xác.

Nếu dùng timestamp từ nhiều máy, đồng hồ cần đồng bộ đủ tốt; sai lệch clock có thể làm end-to-end latency âm hoặc sai. Có thể đo khoảng thời gian bằng monotonic clock trong cùng process và chỉ dùng wall-clock để liên kết trace giữa máy.

## 12. Nhận diện coordinated omission trong kết quả

Các dấu hiệu cảnh báo:

- Test khai báo số VU cố định nhưng production có arrival rate độc lập.
- Khi server chậm, request/second của generator giảm mạnh mà không có queue tương ứng.
- Histogram chỉ tính thời gian từ lúc request thực sự được gửi.
- Có khoảng trống trong timestamp request trong lúc server có latency spike.
- Throughput giảm cùng lúc latency tăng nhưng báo cáo không ghi số arrival bị bỏ lỡ.
- p99 của load test thấp bất thường so với trải nghiệm production trong các sự kiện pause.
- Load generator dùng mô hình “gửi request rồi chờ xong mới gửi tiếp” nhưng kết quả được diễn giải như tải liên tục.

Hãy đối chiếu arrival schedule, dispatch timestamps, completion timestamps và số request bị drop. Nếu có thể, chạy lại cùng mức arrival bằng open model và so sánh queue, throughput, error rate cùng latency end-to-end.

## 13. Các giới hạn của open workload

Open model tránh việc tốc độ đến tự giảm khi server chậm, nhưng cũng có thể tạo tải rất lớn nếu arrival rate cao hơn năng lực. Một load generator không được giới hạn có thể làm queue và memory tăng vô hạn, gây timeout dây chuyền hoặc ảnh hưởng môi trường thử.

### 13.1. Giới hạn concurrency và queue

Đặt giới hạn số request đang chạy, số VU, queue length và thời gian chờ. Khi đạt giới hạn, ghi nhận dropped arrival hoặc reject rõ ràng. Đây là một kết quả quan trọng: hệ thống không thể phục vụ toàn bộ offered load trong giới hạn đã đặt.

### 13.2. Chọn arrival distribution

Traffic production không phải lúc nào cũng đến đều. Có thể có Poisson-like arrivals, burst theo chiến dịch, batch theo phút hoặc periodic event từ thiết bị. Một lịch đều 100 request/giây khác với 100 request dồn vào đầu mỗi giây dù average giống nhau.

Hãy dùng phân phối hoặc profile thời gian phù hợp với dữ liệu quan sát. Nếu chưa biết distribution, thử nhiều dạng: đều, ngẫu nhiên có trung bình tương đương, burst và peak. Ghi seed hoặc cách sinh traffic để test có thể lặp lại.

### 13.3. Không biến test thành DDoS ngoài ý muốn

Chỉ chạy trên môi trường và endpoint được phép kiểm thử. Đặt giới hạn arrival, duration, concurrency và điều kiện dừng. Theo dõi free space, log, connection và queue. Với hệ thống có downstream thật, cần dùng dữ liệu giả hoặc sandbox để không tạo đơn hàng, thanh toán hay sự kiện ngoài ý muốn.

## 14. Kết hợp tải mở và tải đóng trong một kịch bản

Một hệ thống có thể nhận request theo mô hình mở ở biên ngoài nhưng xử lý bằng worker pool đóng bên trong. Ví dụ:

```text
Producer arrival (open, 500 events/s)
              |
              v
         Ingress API
              |
              v
         Message queue ----> backlog/queue age
              |
              v
     40 database workers (closed)
              |
              v
       Primary database
```

Producer tiếp tục đưa event theo arrival rate. Worker lấy message, xử lý transaction rồi mới lấy message tiếp theo. Nếu database chậm, worker throughput giảm, queue backlog tăng. Một bài test chỉ mô phỏng 40 worker có thể cho thấy throughput của consumer nhưng không thể đánh giá backlog do producer tiếp tục gửi.

Kịch bản nên đo:

- Producer offered rate và accepted rate.
- Queue depth và tuổi message cũ nhất.
- Worker concurrency và processing rate.
- Database transaction throughput, p95/p99 và lock wait.
- Consumer error/retry và dead-letter.
- Thời gian queue drain sau khi giảm hoặc dừng producer.

## 15. Quy trình thực hiện một bài test có kiểm soát

1. **Mô tả production:** xác định nguồn request, arrival pattern, số client, think time và query mix.
2. **Chọn model:** closed, open hoặc hybrid theo cơ chế thực tế.
3. **Đặt SLO:** throughput, p95/p99, error/reject rate, replication lag và queue age.
4. **Chuẩn bị dữ liệu:** kích thước, skew, index, cache state và trạng thái database gần production.
5. **Kiểm tra generator:** đủ CPU, memory, network, VU, connection và thời gian; tránh generator thành bottleneck.
6. **Đo baseline:** chạy workload chính ở mức tải thấp và xác nhận metric/trace hoạt động.
7. **Warm-up:** khởi tạo cache, connection và runtime trước cửa sổ đo.
8. **Ramp tải:** tăng VU với closed model hoặc arrival rate với open model.
9. **Steady-state:** giữ tải đủ lâu và ghi throughput, latency, queue, errors và tài nguyên.
10. **Spike/soak/overload:** kiểm tra burst, trạng thái dài hạn và cách hệ thống phục hồi trong môi trường an toàn.
11. **Đối chiếu các mốc thời gian:** scheduled arrival, dispatch, server receive và completion.
12. **Kiểm tra coordinated omission:** xem model, khoảng trống request, dropped arrival và cách histogram được tạo.
13. **Phân tích database:** execution plan, logical/physical reads, CPU, memory, I/O, log flush, lock và connection pool.
14. **Lặp lại sau thay đổi:** giữ cùng model, data, arrival profile và điều kiện để so sánh công bằng.
15. **Lưu báo cáo:** cấu hình generator, version, seed, query mix, số sample, percentile, errors và giới hạn test.

## 16. Ví dụ phân tích kết quả

Một API ghi nhận tải production khoảng 300 request/giây trong giờ cao điểm. Nhóm thử hai mô hình trên cùng môi trường.

| Chỉ số | Closed: 100 VU | Open: 300 arrival/s |
|---|---:|---:|
| Throughput hoàn tất | 260 request/s | 275 request/s |
| p95 service latency | 180 ms | 420 ms |
| p99 service latency | 350 ms | 1.400 ms |
| End-to-end p99 từ lịch arrival | Không có lịch arrival độc lập | 1.650 ms |
| Dropped/missed arrival | Không đo theo arrival cố định | 0 trong giai đoạn này |
| Queue chờ connection | Thấp | Tăng rõ |
| Database CPU | 62% | 88% |

Hai kết quả không mâu thuẫn. Closed model tự giảm tốc khi response chậm nên tạo ít áp lực hơn; open model tiếp tục đưa 300 arrival/giây và bộc lộ queue/latency cao hơn. Nếu production thật sự nhận 300 request/giây bất kể response, kết quả open model phù hợp hơn để đánh giá capacity.

Tiếp theo cần phân tích queue connection, query plan và database wait. Nếu database CPU cao và top query tiêu thụ CPU lớn, tối ưu SQL hoặc tăng CPU có thể cần thiết. Nếu thời gian chủ yếu nằm ở connection pool hoặc lock wait, tăng vCPU không giải quyết nguyên nhân. Sau khi sửa, chạy lại cùng arrival profile và xác nhận p95/p99, throughput, errors cùng queue đều cải thiện.

## 17. Những sai lầm thường gặp

- **Dùng fixed VU để mô phỏng traffic arrival cố định:** khi server chậm, VU tự giảm tốc và có thể che quá tải.
- **Cho rằng open model luôn đúng:** nếu production là nhóm user tương tác có think time, closed model có thể phản ánh hành vi tốt hơn.
- **Chỉ báo cáo average latency:** che p95/p99 và pause hiếm nhưng nghiêm trọng.
- **Chỉ tính request đã hoàn tất thành công:** bỏ qua reject, timeout và dropped arrival.
- **Đo từ actual dispatch nhưng gọi là end-to-end:** bỏ qua thời gian request đáng lẽ phải chờ theo lịch.
- **Hiệu chỉnh histogram mà không nêu expected interval:** kết quả không thể diễn giải hoặc so sánh.
- **Coi HDR correction là thay thế open workload:** phép hiệu chỉnh dựa trên giả định, không tái tạo đầy đủ hệ thống queue.
- **Đặt arrival rate cao hơn capacity rồi không giới hạn queue:** có thể làm test generator hoặc môi trường thử sụp đổ.
- **Không kiểm tra dropped iterations:** generator có thể không phát đủ tải đã khai báo.
- **Không đo generator:** CPU, socket hoặc network của load generator có thể là bottleneck.
- **Trộn request rate với iteration rate:** một iteration có thể gửi nhiều HTTP/SQL request.
- **Không tính think time trong closed model:** làm tải mô phỏng khác hành vi người dùng.
- **So sánh hai model như cùng một workload:** concurrency, arrival và queue khác nhau nên latency không thể so trực tiếp.
- **Không kiểm tra recovery sau overload:** hệ thống có thể tiếp tục chậm do backlog dù offered load đã giảm.

## 18. Checklist mô hình tải và coordinated omission

- [ ] Đã xác định nguồn request trong production là user concurrency hay arrival rate độc lập.
- [ ] Đã chọn closed, open hoặc hybrid model phù hợp.
- [ ] Với closed model, đã ghi số VU, think time và cách mỗi VU lặp request.
- [ ] Với open model, đã ghi arrival rate, distribution, ramp, duration và giới hạn concurrency.
- [ ] Đã phân biệt scheduled arrival, actual dispatch, accepted và completion.
- [ ] Đã đo dropped/missed arrival và không âm thầm loại khỏi báo cáo.
- [ ] Đã kiểm tra coordinated omission khi dùng closed-loop generator.
- [ ] Đã đo queue delay và end-to-end latency nếu request có thể chờ trước dispatch.
- [ ] Đã ghi p50/p95/p99 cùng sample count, throughput và error/reject rate.
- [ ] Đã kiểm tra load generator không bị CPU, memory, network hoặc VU giới hạn.
- [ ] Đã đặt queue limit, timeout, backpressure và điều kiện dừng an toàn.
- [ ] Đã chạy warm-up, ramp-up, steady-state và soak phù hợp.
- [ ] Đã kiểm tra burst, overload và thời gian queue drain trong môi trường cho phép.
- [ ] Đã đo connection pool, worker, database wait, I/O, log và replication cùng lúc.
- [ ] Đã giữ cùng workload model và điều kiện khi so sánh trước/sau tối ưu.

Tải đóng trả lời câu hỏi hệ thống phục vụ được bao nhiêu client đồng thời với think time nhất định; tải mở trả lời câu hỏi hệ thống chịu được tốc độ request đến độc lập bao nhiêu trước khi queue và latency vượt giới hạn. Coordinated omission xuất hiện khi generator ngừng tạo request trong lúc hệ thống chậm và bỏ qua thời gian chờ mà arrival liên tục phải chịu. Chọn mô hình sát production, đo offered load cùng completion, ghi nhận request bị bỏ và kiểm soát load generator sẽ giúp benchmark phản ánh đúng điểm bão hòa và trải nghiệm thực tế.
