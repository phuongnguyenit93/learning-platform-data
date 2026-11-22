# Kiểm thử tải tranh chấp cao với dữ liệu có điểm nóng

Một hệ thống có thể chạy tốt khi dữ liệu được phân bố đều nhưng chậm rõ rệt khi nhiều request cùng truy cập một vài bản ghi. Một sản phẩm bán chạy, một tài khoản tổng, một mã khuyến mãi, một sự kiện mở bán vé hoặc một dòng đếm lượt xem có thể trở thành **điểm nóng (hot spot)**. Khi nhiều transaction cùng đọc hoặc cập nhật một tài nguyên như vậy, chúng tranh chấp khóa, phải chờ nhau hoặc liên tục retry.

Kiểm thử tải tranh chấp cao cần tạo ra đúng kiểu phân bố dữ liệu và lịch thao tác gây ra điểm nóng. Chỉ tăng số virtual user (VU) hoặc số request mỗi giây chưa đủ. Nếu mỗi request cập nhật một khóa khác nhau, bài test có thể tạo tải lớn nhưng không kiểm tra được điểm nghẽn mà production đang gặp.

Một bài test hữu ích phải trả lời được bốn câu hỏi:

1. Tải có thực sự tập trung vào cùng key, row, index range hoặc tài nguyên nghiệp vụ không?
2. Khi mức tranh chấp tăng, throughput, latency, blocking và retry thay đổi ra sao?
3. Dù nhiều transaction cùng chạy, invariant dữ liệu có còn đúng không?
4. Sau khi áp dụng một cách giảm tranh chấp, hiệu năng và tính đúng đắn thay đổi như thế nào?

## 1. Điểm nóng là gì?

Điểm nóng xuất hiện khi một phần nhỏ dữ liệu nhận tỷ lệ truy cập hoặc cập nhật lớn hơn nhiều so với phần còn lại. Điểm nóng có thể là:

- Một dòng inventory của sản phẩm đang bán chạy.
- Một dòng counter lưu tổng số lượt truy cập.
- Một tài khoản ví điện tử nhận nhiều giao dịch.
- Một mã coupon có số lượt sử dụng giới hạn.
- Một resource hoặc event có lượng request đặt chỗ tăng đột biến.
- Một index page hoặc key range bị nhiều transaction cùng quét và khóa.
- Một dòng trạng thái chung mà mọi worker đều cập nhật để báo tiến độ.

Điểm nóng không nhất thiết là một bảng lớn hoặc truy vấn phức tạp. Một câu UPDATE rất ngắn trên cùng một dòng cũng có thể giới hạn throughput, vì các transaction phải lần lượt giành quyền cập nhật dòng đó.

### 1.1. Phân bố đều và phân bố lệch

Giả sử có 100.000 sản phẩm và 10.000 request mỗi giây.

**Phân bố đều:** request được chia tương đối đều trên 100.000 sản phẩm. Xác suất hai transaction cùng cập nhật một dòng trong cùng thời điểm thấp.

**Phân bố lệch:** 80% request nhắm vào 10 sản phẩm phổ biến nhất, 20% còn lại trải trên 99.990 sản phẩm. Một vài dòng inventory có thể nhận hàng nghìn request đồng thời.

Hai workload có cùng tổng request mỗi giây nhưng mức tranh chấp rất khác nhau.

~~~text
Phân bố đều
Product 1       1% request
Product 2       1% request
Product 3       1% request
...
Product 100000  1 phần rất nhỏ

Phân bố lệch
Hot product A   45% request
Hot product B   25% request
Hot product C   10% request
Các sản phẩm còn lại 20% request
~~~

Một workload kiểm thử chỉ tạo nhiều request mà không mô phỏng phân bố lệch có thể bỏ lỡ hot row, hot key hoặc lock convoy.

### 1.2. Các loại điểm nóng

| Loại điểm nóng | Ví dụ | Tài nguyên thường tranh chấp |
|---|---|---|
| Hot row | Một dòng tồn kho hoặc số dư | Row lock, write lock, version conflict |
| Hot key | Một customerId hoặc eventId nhận nhiều request | Index lookup, cùng partition, cùng aggregate |
| Hot index range | Nhiều insert vào một khoảng khóa | Page latch, key-range/gap lock tùy DBMS |
| Hot counter | Một dòng tăng lượt xem hoặc số đơn | Cùng một dòng UPDATE |
| Hot page | Các bản ghi mới tập trung trên một page/index page | Page latch, page split, I/O |
| Hot partition | Nhiều request cùng route vào một shard | CPU, connection, queue và storage của partition |
| Hot tenant | Một khách hàng lớn chiếm phần lớn workload | Tenant-specific rows, indexes và worker |

Cần xác định đúng loại điểm nóng trước khi chọn cách khắc phục. Tăng số connection không giải quyết được một dòng chỉ có thể được cập nhật tuần tự; nó thậm chí có thể làm hàng đợi khóa dài hơn.

## 2. Phân biệt tải cao với tranh chấp cao

Tải cao mô tả số lượng công việc hệ thống phải xử lý. Tranh chấp cao mô tả mức độ các công việc cạnh tranh cùng tài nguyên.

Có thể gặp bốn tình huống:

| Tải | Tranh chấp | Ví dụ |
|---|---|---|
| Thấp | Thấp | Ít request, mỗi request thao tác key riêng |
| Cao | Thấp | Nhiều request nhưng phân bố trên nhiều row độc lập |
| Thấp | Cao | Vài request cùng chờ một khóa bị transaction giữ lâu |
| Cao | Cao | Hàng nghìn request đồng thời cập nhật cùng sản phẩm bán chạy |

Kiểm thử hot spot tập trung vào hai tình huống cuối, đặc biệt là tải cao và tranh chấp cao. Tuy nhiên, cần đo riêng throughput và contention. Nếu chỉ xem CPU, ta có thể kết luận sai rằng database còn rảnh trong khi phần lớn request đang chờ một khóa.

### 2.1. Một ví dụ đơn giản

Giả sử câu lệnh đặt hàng:

~~~sql
UPDATE Inventory
SET AvailableQuantity = AvailableQuantity - @quantity
WHERE ProductId = @productId
  AND AvailableQuantity >= @quantity;
~~~

Khi mỗi request dùng ProductId khác nhau, nhiều UPDATE có thể tiến hành song song.

Khi 500 request cùng dùng ProductId = 42, chúng phải phối hợp trên cùng dòng inventory. Database vẫn bảo đảm cập nhật đúng, nhưng các thao tác ghi trên dòng đó sẽ được tuần tự hóa theo cơ chế khóa hoặc concurrency control của DBMS.

Nếu một transaction giữ khóa dòng trong 300 ms vì còn cập nhật thêm nhiều bảng, các request sau có thể xếp hàng dù câu UPDATE chỉ mất vài mili giây khi chạy riêng lẻ.

## 3. Xây dựng workload có phân bố lệch

Một workload thực tế cần mô tả không chỉ số request mà cả cách chọn dữ liệu. Các phân bố thường dùng:

### 3.1. Phân bố đồng đều

Mỗi key có xác suất được chọn gần như bằng nhau. Đây là baseline để đo hiệu năng khi không có điểm nóng rõ rệt.

~~~text
key = random(1..100000)
~~~

### 3.2. Phân bố hot-key cố định

Một tỷ lệ lớn request nhắm vào cùng một key:

~~~text
Nếu random() < 0.80:
    key = HOT_KEY
Ngược lại:
    key = random(COLD_KEY_RANGE)
~~~

Đây là cách đơn giản để mô phỏng một sự kiện mở bán hoặc sản phẩm viral. Có thể thay tỷ lệ hot-key lần lượt bằng 10%, 30%, 60%, 80%, 95% để tìm ngưỡng hệ thống bắt đầu suy giảm.

### 3.3. Phân bố Zipf hoặc long-tail

Trong hệ thống thật, key phổ biến thường không chỉ có một key duy nhất. Một số ít key nhận nhiều request, còn phần lớn key nhận ít request. Phân bố Zipf là mô hình thường dùng để mô phỏng dạng lệch này.

Không nhất thiết phải tạo chính xác một phân bố Zipf để bắt đầu. Có thể chia key thành nhóm:

| Nhóm | Tỷ lệ key | Tỷ lệ request minh họa |
|---|---:|---:|
| Top 1 | 0,01% | 20% |
| Top 2–10 | 0,09% | 30% |
| Top 11–100 | 0,9% | 25% |
| Phần còn lại | 99% | 25% |

Mục đích là làm cho một nhóm nhỏ key nhận phần lớn thao tác, gần với hành vi truy cập lệch trong thực tế.

### 3.4. Hot-key thay đổi theo thời gian

Một sự kiện có thể nóng trong vài phút rồi giảm. Một chương trình khuyến mãi có thể tạo nhiều hot key cùng lúc. Bài test nên mô phỏng chuyển động đó:

- Giai đoạn đầu: traffic phân bố đều.
- Giai đoạn mở bán: một eventId nhận phần lớn request.
- Giai đoạn sau: request chuyển sang eventId khác.
- Giai đoạn cuối: traffic giảm nhưng worker vẫn xử lý backlog.

Cách này phát hiện vấn đề khi hệ thống phải chuyển tải giữa các partition, cache hoặc worker.

## 4. Xác định mục tiêu và invariant trước khi chạy

Trước khi tạo tải, hãy viết rõ hệ thống cần bảo đảm điều gì.

Ví dụ với inventory:

- AvailableQuantity không bao giờ âm.
- Tổng quantity đã đặt thành công không vượt lượng hàng ban đầu.
- Mỗi idempotency key chỉ tạo tối đa một đơn hàng.
- Request bị từ chối không làm giảm tồn kho.
- Sau khi toàn bộ request kết thúc, counter phải khớp với tổng chi tiết đơn hàng.

Ví dụ với đặt vé:

- Số reservation HELD còn hạn cộng số CONFIRMED không vượt capacity.
- Một seat không có hai reservation hoạt động.
- Reservation hết hạn chỉ giải phóng capacity một lần.
- Callback thanh toán trùng không xác nhận hoặc thu tiền hai lần.

Hiệu năng cao nhưng invariant sai là kết quả thất bại. Một test chỉ kiểm tra HTTP status hoặc thời gian phản hồi mà không đối chiếu dữ liệu cuối có thể bỏ qua overselling, duplicate order hoặc counter drift.

### 4.1. Chỉ số tính đúng đắn

| Chỉ số | Cách xác định |
|---|---|
| Oversell count | Số tài nguyên được phân bổ vượt capacity |
| Negative inventory | Số row có quantity nhỏ hơn 0 |
| Duplicate operation | Số idempotency key tạo nhiều kết quả nghiệp vụ |
| Counter drift | Chênh lệch counter lưu trữ với tổng dữ liệu chi tiết |
| Lost operation | Request được báo thành công nhưng không có kết quả đã commit |
| Double release | Một reservation được giải phóng capacity nhiều hơn một lần |
| Invalid transition | Số lần trạng thái chuyển không theo state machine |
| Unexplained outcome | Request timeout nhưng không xác định được kết quả commit |

Tính các chỉ số này sau khi workload đã dừng và backlog được xử lý xong. Nếu kiểm tra ngay khi worker còn chạy, có thể nhầm độ trễ nhất quán tạm thời với dữ liệu bị mất.

## 5. Chuẩn bị dữ liệu và môi trường thử nghiệm

### 5.1. Dùng dữ liệu riêng cho mỗi lượt test

Tạo một tập dữ liệu có thể reset được:

- Một số lượng nhỏ hot keys có tên hoặc ID xác định.
- Một tập cold keys đủ lớn để tránh vô tình tạo thêm điểm nóng.
- Số lượng row đủ lớn để không toàn bộ dữ liệu nằm trong cache nếu cần thử I/O.
- Dữ liệu liên quan và index giống cấu trúc production.
- Counter, reservation, ledger và trạng thái được khởi tạo theo kịch bản.

Không dùng dữ liệu production thật để thử ghi. Một môi trường staging có schema, index, cấu hình và kích thước dữ liệu gần production sẽ cho kết quả hữu ích hơn một bảng nhỏ chỉ có vài dòng.

### 5.2. Kiểm tra cấu hình trước khi chạy

Ghi lại:

- Phiên bản DBMS và cấu hình isolation.
- CPU, RAM, storage và IOPS.
- Connection pool size và giới hạn connection database.
- Số instance ứng dụng và worker.
- Số partition/shard và cách phân phối key.
- Index liên quan đến hot key.
- Cache, retry policy và timeout.
- Cấu hình transaction log/WAL và replication nếu có.
- Các job nền có thể cập nhật cùng bảng.

Nếu thay đổi cấu hình giữa hai lượt benchmark, ghi lại chính xác thay đổi đó. Không so sánh kết quả của hai môi trường có cấu hình khác nhau rồi quy toàn bộ chênh lệch cho một thay đổi code.

### 5.3. Đồng bộ đồng hồ và ghi dấu lượt test

Mỗi lượt test nên có một RunId. Ghi RunId vào log ứng dụng và metric để nối được request, transaction, DB wait và kết quả kiểm tra dữ liệu.

Ghi lại thời gian bắt đầu/kết thúc, commit window, số request, phân bố key, seed random, phiên bản code và cấu hình. Nếu không lưu seed hoặc danh sách key, khó tái hiện chính xác một workload lệch.

## 6. Thiết kế các pha tải

Không bắt đầu bằng mức tải tối đa. Chạy theo các pha để xác định đường cong hiệu năng và ngưỡng suy giảm.

~~~text
Throughput
   ^
   |                         ______
   |                    ____/
   |               ____/
   |          ____/
   |     ____/
   |____/____________________________> Offered load
        ổn định       bão hòa

Latency và thời gian chờ khóa thường tăng nhanh
khi hệ thống tiến gần hoặc vượt ngưỡng bão hòa.
~~~

### 6.1. Baseline

Chạy workload nhẹ với key phân bố đều. Mục tiêu là biết latency và throughput bình thường trước khi tạo contention.

Ghi p50, p95, p99, error rate, CPU, connection usage và database waits. Baseline là mốc so sánh cho các pha sau.

### 6.2. Ramp-up

Tăng tải theo từng bậc, ví dụ 10%, 25%, 50%, 75%, 100% tải mục tiêu. Mỗi bậc giữ đủ lâu để hệ thống ổn định và metric có ý nghĩa.

Tăng tải từ từ giúp tìm điểm mà latency bắt đầu tăng nhanh, lock waits tích lũy hoặc connection pool chạm giới hạn.

### 6.3. Steady-state

Giữ một mức tải ổn định trong một khoảng thời gian. Đây là pha đo throughput bền vững, không chỉ tốc độ đạt được trong vài giây đầu.

Theo dõi backlog, số transaction đang hoạt động, thời gian chờ khóa và tốc độ giải phóng reservation. Nếu queue tăng liên tục, hệ thống không xử lý kịp offered load dù response ban đầu vẫn nhanh.

### 6.4. Spike test

Tăng traffic đột ngột lên nhiều lần baseline trong thời gian ngắn. Mô phỏng mở bán vé, thông báo push hoặc chương trình khuyến mãi.

Quan sát:

- Request bị từ chối hay timeout.
- Connection pool có cạn không.
- Lock wait queue tăng nhanh đến mức nào.
- Retry có tạo thêm traffic hay không.
- Hệ thống mất bao lâu để trở về trạng thái ổn định.

### 6.5. Soak test

Giữ tải trung bình hoặc cao trong thời gian dài. Mục tiêu là phát hiện vấn đề không xuất hiện trong test ngắn:

- Transaction mở lâu.
- Dead tuple hoặc version store tăng.
- Connection leak.
- Queue backlog tăng dần.
- Cache eviction và I/O tăng.
- Retry storm sau một giai đoạn contention.
- Worker xử lý reservation hết hạn chậm dần.

### 6.6. Recovery test

Sau spike, giảm traffic về mức thấp và quan sát hệ thống hồi phục. Đo thời gian backlog trở về bình thường, số connection được giải phóng và thời gian lock wait giảm.

Một hệ thống có thể chịu được spike nhưng phục hồi chậm, làm request mới tiếp tục bị ảnh hưởng trong nhiều phút.

## 7. Chọn mô hình tải phù hợp

### 7.1. Closed workload

Mỗi virtual user gửi request, chờ phản hồi rồi mới gửi request tiếp theo. Số user đồng thời được giữ tương đối cố định.

Mô hình này phù hợp để mô phỏng số người dùng đang thao tác và dễ triển khai. Tuy nhiên, khi server chậm, tốc độ gửi request tự giảm. Điều đó có thể che giấu mức offered load mà hệ thống đáng lẽ phải chịu.

### 7.2. Open workload

Load generator đặt tốc độ bắt đầu request độc lập với thời gian phản hồi trước đó. Ví dụ, gửi 500 request mỗi giây dù request trước đang chậm.

Mô hình này phù hợp với event-driven traffic hoặc API nhận request liên tục. Nó cho thấy hệ thống có thể xử lý bao nhiêu công việc trước khi backlog và latency tăng.

Với open workload, cần đủ virtual users và tài nguyên ở load generator. Nếu generator không tạo kịp request đã định, kết quả không phản ánh offered load mong muốn.

### 7.3. Coordinated omission

Nếu công cụ chỉ gửi request tiếp theo sau khi request trước hoàn tất, lúc server bị chậm thì nó cũng gửi ít request hơn. Latency histogram có thể bỏ qua những request lẽ ra đã được gửi trong khoảng server đang nghẽn. Đây là coordinated omission.

Để tránh diễn giải sai:

- Dùng arrival-rate/open model khi cần giữ offered load.
- Theo dõi dropped iterations hoặc request không được tạo đúng lịch.
- Ghi cả số request dự kiến và số request thực tế.
- Không chỉ nhìn p95 mà bỏ qua backlog và throughput.
- Nếu dùng closed model, ghi rõ giới hạn và cách nó phản ứng khi server chậm.

## 8. Mô phỏng hot key bằng k6

Có thể dùng k6 để gửi tải qua API ứng dụng. Cách này kiểm tra cả HTTP layer, service logic, connection pool và database. Script dưới đây là khung minh họa cho API đặt reservation:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    hot_key_workload: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 30,
      maxVUs: 300,
      stages: [
        { target: 30, duration: '2m' },
        { target: 60, duration: '3m' },
        { target: 100, duration: '3m' },
        { target: 0, duration: '1m' },
      ],
    },
  },
  thresholds: {
    checks: ['rate>0.99'],
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
  },
};

const hotResource = 'hot-event-42';
const coldKeyCount = Number(__ENV.COLD_KEY_COUNT || 10000);

function chooseResourceKey() {
  if (Math.random() < 0.90) {
    return hotResource;
  }

  const n = Math.floor(Math.random() * coldKeyCount);
  return 'cold-event-' + n;
}

export default function () {
  const resourceId = chooseResourceKey();
  const idempotencyKey = 'vu-' + __VU + '-iteration-' + __ITER;

  const response = http.post(
    __ENV.BASE_URL + '/reservations',
    JSON.stringify({
      resourceId: resourceId,
      quantity: 1,
    }),
    {
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey,
      },
    }
  );

  check(response, {
    'business response is accepted or sold out': (r) =>
      r.status === 201 || r.status === 409,
  });
}
~~~

Script này đưa 90% request vào một resource và 10% vào nhóm cold resources. Điều chỉnh tỷ lệ 90% để tăng hoặc giảm mức skew. Trong thực tế, có thể thay hàm chooseResourceKey bằng phân bố Zipf, danh sách hot keys hoặc một lịch key thay đổi theo thời gian.

Các giá trị URL, status code và payload cần khớp API thật. Ví dụ dùng 201 cho reservation thành công và 409 cho hết chỗ; hệ thống khác có thể dùng status hoặc response body khác.

Trong k6, HTTP 409 thường được tính vào metric http_req_failed theo bộ status mặc định, dù đây có thể là kết quả nghiệp vụ hợp lệ. Script dùng check để phân biệt response hợp lệ với lỗi kỹ thuật. Khi đặt threshold, hãy diễn giải http_req_failed riêng hoặc cấu hình expected status phù hợp với phiên bản k6; không coi mọi 409 là lỗi server.

Idempotency key trong ví dụ duy nhất cho mỗi iteration. Nếu muốn kiểm tra retry của cùng một ý định nghiệp vụ, phải gửi lại đúng key đó qua các lần retry, không tạo key mới.

### 8.1. Tách tỷ lệ thành công nghiệp vụ khỏi lỗi kỹ thuật

Một response 409 "hết chỗ" có thể là kết quả đúng khi resource đã đầy. Một response 500 hoặc timeout thường là lỗi kỹ thuật. Hai loại không nên bị gộp thành một chỉ số "request failed".

Nên đo riêng:

- Request nhận được reservation.
- Request bị từ chối vì hết capacity.
- Request trùng idempotency key và nhận lại kết quả cũ.
- Request lỗi validation.
- Request timeout hoặc lỗi server.
- Request bị retry do deadlock/serialization failure.

Nếu chỉ đo HTTP 2xx, test có thể báo thất bại dù database đã bảo vệ capacity đúng và từ chối request dư. Ngược lại, nếu chỉ đo response 2xx/4xx hợp lệ, test có thể bỏ qua việc có quá nhiều request timeout.

## 9. Các kịch bản hot spot nên chạy

Không chỉ có một loại hot key. Hãy tạo một ma trận kịch bản để biết thiết kế chịu được dạng tranh chấp nào.

| Kịch bản | Workload | Điều cần tìm |
|---|---|---|
| Uniform baseline | Key phân bố đều | Mức hiệu năng khi ít tranh chấp |
| Single hot row | 90–100% ghi vào một row | Giới hạn throughput do tuần tự hóa |
| Few hot keys | 80% request vào top 10 keys | Tranh chấp theo nhóm key |
| Long-tail | Phân bố Zipf hoặc lệch mạnh | Hiệu năng gần workload thực tế |
| Hot-key migration | Điểm nóng chuyển từ key A sang B | Cache, routing và partition rebalance |
| Read-heavy hot key | Nhiều read, ít write trên một key | MVCC, cache và read contention |
| Write-heavy hot key | Nhiều UPDATE cùng row | Lock waits, log flush, serialization |
| Mixed read/write | Đọc trạng thái rồi cập nhật | Snapshot, stale decision, lost update |
| Long transaction | Một transaction giữ khóa lâu | Lock convoy và tail latency |
| Retry storm | Cố tình tạo conflict rồi retry | Offered load bị khuếch đại |
| Burst + recovery | Tăng đột ngột rồi hạ tải | Thời gian hồi phục và backlog |

### 9.1. Hot row đơn

Tất cả request cập nhật cùng một dòng. Đây là kịch bản đơn giản nhất để nhìn rõ chi phí tuần tự hóa.

Ví dụ tăng lượt xem:

~~~sql
UPDATE dbo.ArticleCounter
SET ViewCount = ViewCount + 1
WHERE ArticleId = 42;
~~~

Khi lượng request lớn, dòng ArticleId = 42 trở thành điểm nóng. Dù phép tăng nguyên tử bảo đảm không mất cập nhật, nó không loại bỏ việc các writer phải phối hợp trên cùng row.

### 9.2. Hot key trong inventory

Nhiều request cùng mua một sản phẩm đang hot:

~~~sql
UPDATE dbo.Inventory
SET AvailableQuantity = AvailableQuantity - @quantity
WHERE ProductId = @productId
  AND @quantity > 0
  AND AvailableQuantity >= @quantity;
~~~

Kịch bản này kiểm tra cả contention lẫn invariant AvailableQuantity không âm. Sau test, đối chiếu số đơn thành công với số lượng đã trừ.

### 9.3. Hot range khi insert

Một luồng ghi có thể tập trung vào cùng index range hoặc page, ví dụ ID tăng dần, timestamp hiện tại hoặc cùng tenant. Dù row khác nhau, các insert có thể tranh chấp page latch, index page split hoặc khóa range tùy DBMS và truy vấn.

Hãy đo page latch waits, page splits, log throughput và thời gian insert. Nếu chỉ nhìn row lock, có thể bỏ lỡ điểm nghẽn ở tầng page/index.

### 9.4. Hot tenant

Nếu một tenant chiếm 70% request, các bảng có TenantId làm prefix của index có thể nhận nhiều hoạt động trên cùng range. Tạo test với một tenant lớn và nhiều tenant nhỏ để đánh giá mức cô lập tài nguyên, fairness và tác động đến tenant khác.

## 10. Đo lường ở ứng dụng và database

### 10.1. Chỉ số ở load generator

- Offered request rate: số request được lên lịch gửi.
- Actual request rate: số request thực sự gửi được.
- Throughput: số request hoặc nghiệp vụ hoàn tất mỗi giây.
- p50, p95, p99 latency.
- Error rate theo loại response.
- Số VU đang hoạt động và số iteration bị dropped.
- CPU và network của máy load generator.

Nếu máy load generator đạt 100% CPU hoặc không mở được đủ socket, benchmark không còn đo đúng giới hạn của ứng dụng/database.

### 10.2. Chỉ số ở ứng dụng

- HTTP request latency theo endpoint và resource key.
- Thread pool active/queued/rejected.
- Connection pool active, idle, pending và timeout.
- Transaction duration.
- Retry count theo nguyên nhân.
- Queue depth và tuổi message lâu nhất.
- Cache hit/miss và invalidation.
- Tỷ lệ business success, sold-out, duplicate và timeout.

Một endpoint có thể trả nhanh vì đẩy việc vào queue, trong khi queue tăng mãi. Cần đo cả response latency lẫn thời gian từ lúc nhận request đến khi nghiệp vụ thực sự hoàn tất.

### 10.3. Chỉ số ở database

| Nhóm | Metric cần quan sát |
|---|---|
| CPU và I/O | CPU utilization, read/write IOPS, latency |
| Locking | Lock wait count, wait duration, blocked sessions, deadlocks |
| Transaction | Active transactions, transaction age, rollback rate |
| Log | Transaction log/WAL flush latency, bytes written, log waits |
| Connection | Active sessions, max connections, pool wait |
| Query | Execution count, mean/p95 duration, rows scanned |
| Versioning | Version store, dead tuples, vacuum lag tùy DBMS |
| Index/page | Page latch waits, page splits, buffer hit |
| Replication | Replication lag, retained WAL/log backlog |
| Contention | Số request cùng key, cùng row hoặc cùng partition |

Không chỉ ghi tổng số lock waits. Hãy gắn query fingerprint, resource key hoặc transaction type để biết workload nào gây tranh chấp. Tránh log toàn bộ key nhạy cảm; có thể hash hoặc gom theo nhóm key.

## 11. Quan sát contention trong SQL Server

Có thể xem các request đang bị block:

~~~sql
SELECT
    session_id,
    blocking_session_id,
    status,
    wait_type,
    wait_time,
    wait_resource,
    command
FROM sys.dm_exec_requests
WHERE blocking_session_id <> 0;
~~~

Xem các khóa hiện tại:

~~~sql
SELECT
    request_session_id,
    resource_type,
    request_mode,
    request_status,
    resource_description
FROM sys.dm_tran_locks
WHERE resource_database_id = DB_ID();
~~~

Xem các wait statistics nổi bật:

~~~sql
SELECT TOP (20)
    wait_type,
    waiting_tasks_count,
    wait_time_ms,
    signal_wait_time_ms
FROM sys.dm_os_wait_stats
WHERE wait_type NOT LIKE 'SLEEP%'
ORDER BY wait_time_ms DESC;
~~~

Wait statistics là số liệu tích lũy kể từ lần reset hoặc khởi động phù hợp, không chỉ thuộc lượt test vừa chạy. Hãy chụp baseline trước và sau test hoặc dùng công cụ thu thập theo khoảng thời gian. Không kết luận từ một ảnh chụp đơn lẻ.

Với deadlock, dùng Extended Events để thu deadlock graph, xác định statement và thứ tự khóa. DMV giúp thấy blocking hiện tại; deadlock graph giúp hiểu chu trình chờ đã xảy ra và transaction nào bị chọn làm victim.

## 12. Quan sát contention trong PostgreSQL

Xem session đang chờ và truy vấn:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY xact_start NULLS LAST;
~~~

Xem quan hệ blocking:

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocker.pid AS blocker_pid,
    blocked.wait_event_type,
    blocked.wait_event,
    blocked.query AS blocked_query,
    blocker.query AS blocker_query
FROM pg_stat_activity AS blocked
JOIN pg_stat_activity AS blocker
  ON blocker.pid = ANY(pg_blocking_pids(blocked.pid));
~~~

Xem lock đang tồn tại:

~~~sql
SELECT
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name,
    page,
    tuple,
    pid
FROM pg_locks
WHERE NOT granted
   OR locktype IN ('relation', 'tuple')
ORDER BY granted, pid;
~~~

pg_stat_activity và pg_locks hữu ích để quan sát blocking, nhưng không phải mọi contention đều xuất hiện như row lock chưa được cấp. Cũng cần xem pg_stat_statements, CPU, I/O, WAL, buffer activity và serialization failure SQLSTATE 40001.

Với PostgreSQL SERIALIZABLE, transaction có thể bị hủy do SSI mà không phải chờ một lock thông thường. Ghi nhận số lỗi 40001 riêng với deadlock 40P01.

## 13. Quan sát contention trong MySQL InnoDB

Có thể dùng Performance Schema để xem lock wait:

~~~sql
SELECT
    REQUESTING_ENGINE_TRANSACTION_ID,
    BLOCKING_ENGINE_TRANSACTION_ID,
    REQUESTING_THREAD_ID,
    BLOCKING_THREAD_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE
FROM performance_schema.data_lock_waits;
~~~

Xem các lock đang được ghi nhận:

~~~sql
SELECT
    ENGINE_TRANSACTION_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS
FROM performance_schema.data_locks;
~~~

SHOW ENGINE INNODB STATUS cũng cung cấp thông tin về deadlock gần nhất và trạng thái engine. Cần bật và cấp quyền Performance Schema phù hợp với môi trường.

Với InnoDB, phân biệt consistent read với locking read. Gap lock và next-key lock có thể mở rộng phạm vi tranh chấp khi truy vấn range. Index và isolation level ảnh hưởng đáng kể đến khóa được lấy.

## 14. Đọc đường cong latency và throughput

Khi tăng offered load, throughput ban đầu thường tăng gần tuyến tính. Đến một ngưỡng, tài nguyên nóng bão hòa: transaction bắt đầu xếp hàng, lock wait tăng và p95/p99 latency tăng nhanh.

Một dạng thường thấy:

~~~text
Latency
   ^
   |                               /
   |                            __/
   |                         __/
   |________________________/____________> Offered load
                           ngưỡng bão hòa
~~~

Dấu hiệu điểm nóng:

- Throughput gần như không tăng dù offered load tiếp tục tăng.
- p95/p99 tăng nhanh hơn p50.
- Lock wait hoặc row version conflict tăng.
- Một nhóm key có latency cao hơn rõ rệt các key khác.
- Connection pool pending tăng trong khi CPU database chưa bão hòa.
- Retry count tăng và làm offered load thực tế vào database cao hơn tải người dùng.
- Một transaction dài làm nhiều request cùng key bị chờ phía sau.

Nếu throughput giảm khi tăng tải, kiểm tra retry storm, connection pool starvation, lock convoy, log bottleneck và giới hạn của load generator.

### 14.1. Tail latency quan trọng hơn trung bình

Giả sử 95% request hoàn tất trong 30 ms nhưng 5% request trên hot key mất 3 giây. Average có thể vẫn trông ổn, trong khi người dùng mua sản phẩm hot thường xuyên gặp timeout.

Luôn xem latency theo:

- Endpoint.
- Loại thao tác đọc/ghi.
- Hot key so với cold key.
- Thành công so với từ chối.
- Lần thử đầu so với request đã retry.
- Tenant hoặc partition.

Một histogram tổng hợp có thể che giấu điểm nóng nhỏ nhưng gây ảnh hưởng lớn.

## 15. So sánh các cách giảm tranh chấp

Sau khi có baseline, thay đổi một thiết kế tại một thời điểm và chạy lại cùng workload.

### 15.1. Atomic update

Đưa điều kiện và phép thay đổi vào cùng câu UPDATE:

~~~sql
UPDATE Inventory
SET AvailableQuantity = AvailableQuantity - @quantity
WHERE ProductId = @productId
  AND AvailableQuantity >= @quantity;
~~~

Ưu điểm:

- Ngắn gọn và dễ bảo vệ invariant trên một dòng.
- Tránh khoảng trống giữa SELECT và UPDATE.
- Database thực hiện phép tính trên trạng thái được phối hợp.

Giới hạn:

- Mọi writer trên cùng dòng vẫn phải phối hợp.
- Không giải quyết tự động invariant trải qua nhiều dòng.
- Hot row vẫn có giới hạn throughput.

### 15.2. Pessimistic locking

Khóa row hoặc guard row trước khi kiểm tra và cập nhật.

Ưu điểm:

- Quy tắc tuần tự hóa rõ ràng.
- Phù hợp khi cần đọc nhiều giá trị rồi mới quyết định ghi.
- Dễ bảo vệ invariant có một guard row.

Giới hạn:

- Request sau phải chờ.
- Transaction dài làm hàng đợi khóa dài hơn.
- Khóa nhiều dòng sai thứ tự có thể tạo deadlock.

### 15.3. Optimistic concurrency

Dùng Version hoặc concurrency token để phát hiện một request ghi từ dữ liệu cũ.

~~~sql
UPDATE Inventory
SET AvailableQuantity = @newQuantity,
    Version = Version + 1
WHERE ProductId = @productId
  AND Version = @versionRead;
~~~

Ưu điểm:

- Ít giữ khóa trong lúc ứng dụng tính toán.
- Phù hợp khi xung đột hiếm.
- Phát hiện được stale write.

Giới hạn:

- Khi hot key có nhiều writer, nhiều transaction thất bại và retry.
- Retry lặp lại có thể khuếch đại tải.
- Phải đọc lại và tính toán lại trên dữ liệu mới.

### 15.4. Sharded hoặc striped counter

Thay một counter nóng bằng nhiều bucket:

~~~text
Counter tổng
  |
  +-- Bucket 1
  +-- Bucket 2
  +-- Bucket 3
  +-- ...
  +-- Bucket N

Mỗi request cập nhật một bucket được chọn.
Tổng = SUM(Bucket)
~~~

Ưu điểm:

- Giảm số transaction cùng cập nhật một dòng.
- Có thể tăng throughput khi phép ghi độc lập theo bucket.

Giới hạn:

- Đọc tổng phải cộng nhiều bucket.
- Phân phối không đều có thể tạo bucket nóng mới.
- Giới hạn capacity toàn cục khó bảo vệ hơn.
- Nếu cần từ chối khi tổng đạt ngưỡng, phải có một giao thức phân bổ quota hoặc bước phối hợp cuối.

Một cách là cấp quota cho từng bucket. Tổng quota được phân bổ không vượt capacity; mỗi bucket chỉ tiêu thụ quota của nó. Đổi lại, có thể có bucket hết quota trong khi bucket khác còn dư, nên cần quy trình tái cân bằng.

### 15.5. Queue hoặc partition theo key

Đưa request vào hàng đợi và xử lý tuần tự theo resource key. Các request cùng key đi cùng một partition; các key khác nhau có thể xử lý song song.

Ưu điểm:

- Điều tiết concurrency cho hot key.
- Hạn chế số transaction cùng tranh chấp một row.
- Có thể kiểm soát thứ tự xử lý theo key.

Giới hạn:

- Tăng latency do phải chờ queue.
- Queue có thể trở thành backlog nếu tốc độ vào cao hơn tốc độ xử lý.
- Message có thể được giao lại; consumer phải idempotent.
- Không tự tạo thứ tự toàn cục giữa các key khác nhau.

### 15.6. Cache

Cache giúp giảm tải đọc, nhưng không phải nguồn sự thật cho cập nhật tồn kho, số dư hoặc capacity. Cache có thể stale và nhiều instance có thể cùng ghi giá trị khác nhau.

Có thể dùng cache cho dữ liệu hiển thị hoặc giảm số lần đọc. Quyết định phân bổ tài nguyên vẫn cần được bảo vệ bằng database, một atomic primitive hoặc hệ thống điều phối có semantics rõ.

## 16. Kiểm tra tính đúng đắn sau khi tải kết thúc

Sau khi dừng load generator, đợi worker và queue xử lý hết công việc đã nhận. Sau đó chạy các truy vấn đối chiếu.

### 16.1. Inventory không âm

~~~sql
SELECT ProductId, AvailableQuantity
FROM dbo.Inventory
WHERE AvailableQuantity < 0;
~~~

Kết quả phải rỗng nếu invariant là không cho tồn kho âm.

### 16.2. Đối chiếu số lượng đã đặt

~~~sql
SELECT
    i.ProductId,
    i.InitialQuantity,
    i.AvailableQuantity,
    COALESCE(SUM(
        CASE WHEN o.Status IN ('PAID', 'CONFIRMED')
             THEN oi.Quantity ELSE 0 END
    ), 0) AS CommittedOrderQuantity
FROM dbo.Inventory AS i
LEFT JOIN dbo.OrderItem AS oi
    ON oi.ProductId = i.ProductId
LEFT JOIN dbo.Orders AS o
    ON o.OrderId = oi.OrderId
GROUP BY
    i.ProductId,
    i.InitialQuantity,
    i.AvailableQuantity;
~~~

Đây là truy vấn minh họa; cần điều chỉnh theo schema, trạng thái đơn hàng và cách tính hàng hoàn/hủy. Không so sánh counter với tổng đơn hàng chưa phân biệt trạng thái.

### 16.3. Tìm idempotency key bị trùng

~~~sql
SELECT IdempotencyKey, COUNT(*) AS OperationCount
FROM dbo.Reservation
GROUP BY IdempotencyKey
HAVING COUNT(*) > 1;
~~~

Nếu idempotency key được thiết kế unique ở database, truy vấn này phải không trả dòng nào. Nếu key được lưu ở bảng operation riêng, hãy đối chiếu đúng bảng đó.

### 16.4. Kiểm tra reservation hoạt động vượt capacity

~~~sql
SELECT
    rc.ResourceId,
    rc.Capacity,
    SUM(r.Quantity) AS ActiveReserved
FROM dbo.ResourceCapacity AS rc
JOIN dbo.Reservation AS r
    ON r.ResourceId = rc.ResourceId
WHERE r.Status = 'CONFIRMED'
   OR (r.Status = 'HELD' AND r.ExpiresAt > SYSUTCDATETIME())
GROUP BY rc.ResourceId, rc.Capacity
HAVING SUM(r.Quantity) > rc.Capacity;
~~~

Điều kiện thời gian và trạng thái cần khớp quy tắc nghiệp vụ thực tế. Nếu query kiểm tra sau khi test vẫn trả dòng, hãy lưu RunId và truy vết những operation đã làm vượt invariant.

## 17. Đọc kết quả và xác định bottleneck

Khi test chậm, đừng mặc định database cần thêm CPU hoặc connection. Hãy xác định nơi request đang đợi.

| Quan sát | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| CPU cao, lock wait thấp | Query hoặc xử lý tính toán tốn CPU | Execution plan, index, code path |
| CPU thấp, lock wait cao | Hot row, transaction dài, lock convoy | Blocking chain, transaction scope, key distribution |
| Connection pool pending cao | Connection bị giữ lâu hoặc pool quá nhỏ | Pool metrics, transaction duration, query latency |
| Throughput không tăng, p99 tăng | Hot resource bão hòa | Hot-key share, lock wait theo key, queue |
| Deadlock tăng theo tải | Thứ tự khóa không nhất quán | Deadlock graph, thứ tự cập nhật bảng |
| Retry tăng mạnh | Optimistic conflict hoặc serialization failure | Retry reason, backoff, transaction boundary |
| Log/WAL flush latency cao | Ghi log là bottleneck | Commit rate, batch, storage latency |
| Page latch/page split tăng | Hot index page hoặc insert pattern | Index design, key pattern, fill factor |
| Queue depth tăng mãi | Consumer throughput thấp hơn producer | Partitioning, worker count, processing time |
| Chỉ một tenant chậm | Hot tenant hoặc partition lệch | Tenant distribution, shard routing, quota |

Đôi khi một thay đổi làm lock wait giảm nhưng p99 vẫn cao vì request phải đợi queue. Đôi khi sharding tăng throughput ghi nhưng làm truy vấn đọc tổng chậm hơn. Cần đánh giá toàn bộ hành trình nghiệp vụ, không chỉ một metric.

## 18. Quy trình benchmark có thể tái hiện

Một lượt benchmark nên có các bước rõ ràng:

1. **Định nghĩa workload:** số request, tỷ lệ đọc/ghi, key distribution, transaction length và offered rate.
2. **Reset dữ liệu:** khôi phục capacity, inventory, counters và trạng thái nghiệp vụ.
3. **Kiểm tra môi trường:** phiên bản code, DBMS, index, pool, worker, cache và tài nguyên.
4. **Chạy warm-up:** làm nóng connection pool, JIT và cache nếu đó là điều kiện của bài test.
5. **Chạy baseline:** workload đều để biết mức tham chiếu.
6. **Chạy hot-key test:** tăng tỷ lệ request tập trung theo từng bậc.
7. **Chạy spike/soak:** kiểm tra burst, độ bền và recovery.
8. **Thu thập metrics:** generator, app, DB, queue và lock waits.
9. **Đối chiếu invariant:** kiểm tra dữ liệu sau khi mọi công việc đã hoàn tất.
10. **Lưu kết quả:** RunId, seed, config, throughput, latency, error, retry và kết quả đối chiếu.
11. **Thay một thiết kế:** áp dụng atomic update, guard row, sharding hoặc queue.
12. **Chạy lại cùng workload:** so sánh trên cùng môi trường và cùng dữ liệu ban đầu.

Không thay đồng thời nhiều yếu tố như index, connection pool, transaction isolation và key distribution. Nếu thay tất cả cùng lúc, bạn không biết cải thiện đến từ đâu.

## 19. Các lỗi thường gặp khi kiểm thử hot spot

| Lỗi | Vì sao làm sai kết quả | Cách khắc phục |
|---|---|---|
| Dùng key phân bố đều | Không tạo được hot row thật | Tạo hot-key share và long-tail |
| Chỉ tăng VU | Có thể tăng tải nhưng không tăng tranh chấp | Kiểm soát key distribution và cùng tài nguyên |
| Load generator bị nghẽn | Offered rate thấp hơn mục tiêu | Theo dõi CPU, socket, dropped iteration và chạy generator riêng |
| Chỉ xem average latency | Che giấu tail latency trên hot key | Xem p50/p95/p99 theo key group |
| Không đo retry | Retry có thể khuếch đại tải | Ghi retry count và nguyên nhân |
| Chỉ kiểm tra HTTP status | Không phát hiện oversell hoặc lost update | Đối chiếu invariant trong database |
| Dùng dữ liệu quá nhỏ | Cache và index không giống production | Dùng kích thước dữ liệu gần thực tế |
| Transaction test quá ngắn | Không tái hiện lock convoy | Thử nhiều transaction duration và thời gian giữ khóa |
| Bỏ qua queue backlog | Response nhanh nhưng công việc chưa hoàn tất | Đo queue depth và end-to-end completion |
| Chạy nhiều test song song | Các test làm nhiễu metric của nhau | Cô lập workload và ghi nhận tài nguyên dùng chung |
| Không reset state | Mỗi lần test có điều kiện đầu khác nhau | Reset hoặc tạo namespace dữ liệu mới |
| Chạy test ghi trên production tùy tiện | Có thể làm thay đổi dữ liệu thật và ảnh hưởng người dùng | Dùng môi trường cô lập, dữ liệu tổng hợp và kế hoạch kiểm soát được phê duyệt |

## 20. Tiêu chí kết thúc một bài kiểm thử

Một lượt test chỉ có thể xem là đạt khi đồng thời thỏa yêu cầu hiệu năng và tính đúng đắn đã đặt ra.

Ví dụ tiêu chí:

- Duy trì offered rate mục tiêu trong khoảng test.
- p95 và p99 nằm trong SLO đã thống nhất.
- Error rate kỹ thuật dưới ngưỡng.
- Tỷ lệ request bị dropped bởi load generator bằng 0 hoặc được giải thích.
- Throughput nghiệp vụ ổn định, queue không tăng không giới hạn.
- Lock wait và retry không vượt ngân sách vận hành.
- Inventory/capacity/counter không vi phạm invariant.
- Idempotency không tạo duplicate operation.
- Sau spike, hệ thống phục hồi trong thời gian mục tiêu.
- Kết quả có thể tái hiện bằng cùng code, seed và cấu hình.

Ngưỡng cụ thể phải đến từ yêu cầu của hệ thống. Không có một con số p95, số VU hoặc tỷ lệ retry chung phù hợp với mọi ứng dụng.

## 21. Những nguyên tắc cần ghi nhớ

- Hot spot là key, row, range, page, partition hoặc tenant nhận lượng truy cập/ghi vượt trội so với phần còn lại.
- Tải cao không đồng nghĩa tranh chấp cao; workload phải mô phỏng phân bố key lệch.
- Dùng uniform baseline rồi tăng tỷ lệ hot-key để xác định ngưỡng suy giảm.
- Kết hợp ramp-up, steady-state, spike, soak và recovery để thấy cả bão hòa lẫn khả năng hồi phục.
- Open workload giữ offered rate độc lập với response time; closed workload có thể che giấu tải khi server chậm.
- Theo dõi dropped iteration và coordinated omission để biết load generator có gửi đủ tải không.
- Đo p50/p95/p99, throughput, retry, blocking, connection pool, queue và database waits theo loại key.
- Kiểm tra invariant sau khi backlog đã xử lý xong; HTTP response hợp lệ không chứng minh dữ liệu không bị oversell.
- Atomic update bảo vệ tốt phép thay đổi trên một dòng nhưng hot row vẫn phải tuần tự hóa writer.
- Optimistic retry, sharded counter và queue có trade-off về retry, read aggregation, latency và thứ tự xử lý.
- Cache giảm đọc nhưng không thay thế nguồn sự thật cho inventory, số dư hoặc capacity.
- Mỗi benchmark cần RunId, seed, dữ liệu ban đầu, cấu hình và kết quả có thể tái hiện.
- Thay một biến mỗi lần để biết thiết kế nào thực sự cải thiện bottleneck.
- Đánh giá cả hiệu năng, tính đúng đắn và thời gian phục hồi sau tải đột biến.

Kiểm thử tranh chấp cao phải làm cho nhiều request cùng chạm vào đúng tài nguyên đang nóng, đồng thời giữ được một cách đo có thể lặp lại. Khi kết hợp phân bố key thực tế, lịch tải có kiểm soát, metric ở cả ứng dụng và database, cùng việc đối chiếu invariant sau test, bạn sẽ biết hệ thống đang bão hòa ở đâu và giải pháp nào cải thiện throughput mà vẫn bảo toàn dữ liệu.

