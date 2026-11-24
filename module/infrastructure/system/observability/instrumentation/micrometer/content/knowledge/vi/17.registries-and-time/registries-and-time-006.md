# Đọc số đếm, tổng thời gian hoặc max khi bước thời gian vừa thay đổi

Timer của Micrometer thường cung cấp ít nhất ba thống kê quan trọng: **count** (số lần ghi nhận), **totalTime** (tổng thời lượng) và **max** (thời lượng lớn nhất). Khi dùng registry tích lũy, count và totalTime thường tăng trong vòng đời tiến trình. Với step registry, hai giá trị này được gom theo từng khoảng xuất bản (publishing step), còn max được duy trì theo cửa sổ thống kê riêng. Vì vậy, ngay sau khi một step vừa đổi, ba giá trị không nhất thiết cùng phản ánh một khoảng thời gian.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, việc hiểu khác biệt này giúp đọc dashboard đúng cách, tránh kết luận nhầm rằng dữ liệu bị mất khi count hoặc totalTime đổi về 0, hoặc cho rằng max luôn là độ trễ lớn nhất của đúng step vừa hoàn tất. Bài này giải thích cách step registry luân chuyển dữ liệu, cách tính count và totalTime của một interval, vòng đời time-window max, và cách đối chiếu với cumulative registry như Prometheus.

## 1. Step registry và cumulative registry có cách báo cáo khác nhau

Micrometer cung cấp API meter thống nhất, nhưng mỗi backend có thể mong đợi kiểu dữ liệu khác nhau. Một số hệ thống nhận giá trị tích lũy và tự tính rate ở phía truy vấn; một số hệ thống nhận dữ liệu đã được chuẩn hóa theo publishing interval.

### Cumulative registry

Với registry tích lũy, count và totalTime thường tăng liên tục từ khi meter được tạo trong tiến trình. Ví dụ, sau 100 request, Timer có count 100; sau 150 request, count là 150. Khi tiến trình khởi động lại, bộ đếm của tiến trình mới thường bắt đầu lại.

Prometheus là ví dụ phổ biến: Prometheus scrape các giá trị tích lũy, sau đó PromQL dùng rate() hoặc increase() để tính tốc độ hoặc lượng tăng trong một khoảng thời gian.

### Step registry

Step registry gom dữ liệu trong một publishing interval. Trong interval hiện tại, meter tích lũy các lần ghi nhận. Khi interval kết thúc và registry poll/rollover, dữ liệu của interval vừa hoàn tất chuyển sang trạng thái previous để được báo cáo trong interval kế tiếp. Dữ liệu của interval mới tiếp tục được ghi vào trạng thái current.

Giá trị step được báo cáo tương ứng với lượng đo trong interval hoàn tất. Về mặt rate aggregation, Micrometer giữ dữ liệu cho interval hiện tại và khi poll chuyển dữ liệu đó sang previous; giá trị previous được báo cáo cho đến lần rollover tiếp theo.

Điều này có nghĩa là ở step registry, count và totalTime thường mô tả **interval vừa hoàn tất**, không phải tổng từ lúc tiến trình khởi động.

## 2. Một step được luân chuyển như thế nào?

Giả sử registry xuất dữ liệu mỗi 10 giây. Có thể hình dung hai vùng dữ liệu:

- **current**: nhận các lần ghi nhận trong step đang chạy.
- **previous**: giữ dữ liệu của step vừa hoàn tất để registry xuất bản.

~~~text
Thời gian       0s                 10s                20s
                |------------------|------------------|
Step            A                  B                  C

Ghi nhận        current = A        current = B        current = C
Tại rollover                       A -> previous       B -> previous
Giá trị publish                    dữ liệu A           dữ liệu B
~~~

Khi step A kết thúc, registry poll giá trị step và chuyển dữ liệu A sang previous. Trong step B, backend nhận dữ liệu của A cho đến khi dữ liệu B được rollover ở ranh giới kế tiếp.

Nếu step B không có sự kiện, khi B hoàn tất, giá trị của B có thể là count = 0 và totalTime = 0. Khi đó dữ liệu được báo cáo cho interval B là 0, thay thế dữ liệu của A trong trạng thái previous.

Việc poll và publish được điều phối bởi registry. Thời điểm chính xác tại ranh giới phụ thuộc scheduler và clock của registry; không nên giả định một lệnh đọc dashboard đúng tại mili giây chuyển step sẽ luôn thấy dữ liệu đã rollover xong.

## 3. Đọc count và totalTime của interval vừa hoàn tất

Timer ghi nhận thời lượng của từng thao tác. Với step registry, count là số lần ghi nhận trong interval và totalTime là tổng thời lượng của các lần ghi nhận trong interval đó.

Giả sử step dài 10 giây và trong step A có 20 request, mỗi request mất 100 ms:

\[
\text{count} = 20
\]

\[
\text{totalTime} = 20 \times 100\text{ ms} = 2\text{ s}
\]

Từ hai giá trị này có thể tính độ trễ trung bình:

\[
\text{mean} = \frac{\text{totalTime}}{\text{count}}
= \frac{2\text{ s}}{20}
= 100\text{ ms}
\]

Thông lượng trung bình trong step:

\[
\text{throughput} = \frac{\text{count}}{\text{step}}
= \frac{20}{10\text{ s}}
= 2\text{ requests/s}
\]

Ví dụ này cho thấy count là số sự kiện của interval, totalTime là tổng thời lượng trong interval, còn totalTime/count là latency trung bình. totalTime không phải latency của một request đơn lẻ.

| Thống kê | Giá trị trong step A | Ý nghĩa |
|---|---:|---|
| count | 20 | 20 request được ghi nhận |
| totalTime | 2 giây | Tổng thời gian của 20 request |
| mean | 100 ms | Thời gian trung bình mỗi request |
| throughput | 2 request/giây | Tốc độ request trung bình của step 10 giây |

Với step registry, Micrometer chuẩn hóa số đo theo publishing interval để backend có thể cộng các interval hoặc biểu diễn rate theo khả năng của hệ thống giám sát. Giá trị được poll tương ứng với rate trên giây nhân với độ dài interval, nên ví dụ 10 giây ở trên vẫn cho count 20 và totalTime 2 giây.

## 4. Điều gì xảy ra ngay sau khi step thay đổi?

Hãy tiếp tục ví dụ step 10 giây:

| Khoảng đo | Request | count được báo cáo | totalTime được báo cáo | Mean |
|---|---:|---:|---:|---:|
| Step A: 0–10s | 20 × 100 ms | 20 | 2 giây | 100 ms |
| Step B: 10–20s | 12 × 200 ms | 12 | 2,4 giây | 200 ms |
| Step C: 20–30s | Không có | 0 | 0 | Không xác định |

Sau rollover của step A, registry báo cáo dữ liệu A trong step B. Sau rollover của step B, dữ liệu B thay thế dữ liệu A. Sau rollover của step C, count và totalTime được báo cáo là 0 vì step C không có request.

Không nên đọc count = 0 ở một step rỗng như thể toàn bộ dịch vụ chưa từng xử lý request. Nó chỉ có nghĩa interval vừa hoàn tất không ghi nhận request. Nếu muốn tổng số request trong một giờ, cần tổng hợp các interval hoặc dùng hệ thống cumulative và truy vấn increase/rate phù hợp.

Cũng không nên tính mean khi count bằng 0. Khi đó totalTime/count không có ý nghĩa; dashboard nên hiển thị khoảng trống hoặc trạng thái không có mẫu, thay vì tự diễn giải thành latency bằng 0.

## 5. max có cửa sổ thời gian riêng

Max của Timer cơ bản trong Micrometer là **time-window maximum**. Nó thể hiện thời lượng lớn nhất trong một cửa sổ thống kê, không nhất thiết là giá trị lớn nhất của đúng publishing step vừa hoàn tất.

Cửa sổ max được xác định bởi:

\[
\text{window size} = \text{expiry} \times \text{bufferLength}
\]

Với step registry, expiry mặc định thường bằng step size nếu không được cấu hình khác. bufferLength mặc định là 3. Ví dụ step 10 giây và bufferLength 3 tạo cửa sổ max xấp xỉ 30 giây.

Điều này khiến max có thể giữ lại một đỉnh latency từ step trước trong nhiều step tiếp theo. Khi không có mẫu mới trong toàn bộ cửa sổ và dữ liệu cũ đã hết hạn, max mới trở về 0.

Ví dụ:

- Step A ghi nhận một request mất 2,5 giây; max trở thành 2,5 giây.
- Step B chỉ có request tối đa 300 ms; max có thể vẫn là 2,5 giây vì mẫu cũ còn trong cửa sổ.
- Step C không có request; max vẫn có thể giữ 2,5 giây nếu mẫu cũ chưa hết hạn hoàn toàn.
- Sau khi toàn bộ cửa sổ tính từ mẫu lớn đã trôi qua mà không có mẫu lớn hơn, max có thể trở về 0.

Do đó, max không phải lúc nào cũng đổi đồng thời với count và totalTime. Đây là hành vi có chủ đích để giữ dấu vết của một spike latency trong một khoảng thời gian sau khi sự cố tài nguyên đã xảy ra.

## 6. Đọc ba thống kê cùng nhau

Khi step vừa thay đổi, hãy đọc count, totalTime và max theo đúng ý nghĩa:

| Quan sát | Cách diễn giải |
|---|---|
| count > 0, totalTime > 0, max > 0 | Interval có request; max có thể thuộc cửa sổ dài hơn interval |
| count = 0, totalTime = 0, max > 0 | Interval vừa hoàn tất không có request, nhưng cửa sổ max vẫn còn mẫu cũ |
| count > 0, totalTime > 0, max = 0 | Cần kiểm tra cấu hình/export hoặc cách backend xử lý max; với dữ liệu Timer hợp lệ, thường có mẫu duration dương |
| count = 0, totalTime = 0, max = 0 | Interval không có request và cửa sổ max cũng không còn mẫu |
| count tăng theo tổng vòng đời thay vì từng step | Có thể đang dùng cumulative registry, hoặc đang xem phép tổng hợp ở backend |

Một ví dụ thực tế: dịch vụ nhận một đợt tải lớn trong step A, trong đó có một request bị chậm 2,5 giây. Sang step B, tải giảm và các request chỉ mất 100–300 ms. count và totalTime của B phản ánh riêng B; max có thể vẫn hiển thị 2,5 giây để người vận hành thấy spike vừa xảy ra.

Nếu dashboard đặt cả ba đường biểu diễn trên cùng một trục thời gian mà không giải thích semantics, người xem có thể nghĩ max của B phải nhỏ hơn hoặc bằng latency lớn nhất của B. Thực tế max có thể đang đại diện cho cửa sổ gồm nhiều step.

## 7. So sánh với Prometheus cumulative registry

Prometheus registry thường xuất count và total time theo dạng tích lũy. Ví dụ sau 20 request, count là 20; sau 12 request tiếp theo, count là 32. totalTime cũng tiếp tục tăng theo tổng thời lượng.

Có thể dùng PromQL để tính tốc độ request:

~~~promql
sum(rate(checkout_request_seconds_count[5m]))
~~~

Tính latency trung bình trong cửa sổ năm phút:

~~~promql
sum(rate(checkout_request_seconds_sum[5m]))
/
sum(rate(checkout_request_seconds_count[5m]))
~~~

rate() xử lý counter reset do tiến trình khởi động lại. Đây là phép tính ở phía backend, khác với step registry vốn chuẩn hóa số đo theo publishing interval ở phía ứng dụng.

Đối với max, Prometheus vẫn có thể nhận một series max từ Timer, nhưng đó là giá trị max theo cửa sổ của Micrometer. Nếu dùng max_over_time() trong PromQL, đó lại là phép lấy max trên các mẫu lịch sử mà Prometheus đã scrape. Hai cửa sổ này khác nhau:

- Micrometer time-window max: cửa sổ của các mẫu duration trong ứng dụng.
- PromQL max_over_time: cửa sổ của các điểm dữ liệu đã được Prometheus lưu.

Không dùng max_over_time() như thể nó thay thế hoàn toàn cấu hình expiry và bufferLength trong Micrometer.

## 8. Đọc giá trị trực tiếp từ Timer

Trong code, Timer cung cấp các phép đọc count, totalTime và max:

~~~java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Timer;

public void inspect(Timer timer) {
    long count = timer.count();
    double totalSeconds = timer.totalTime(TimeUnit.SECONDS);
    double maxSeconds = timer.max(TimeUnit.SECONDS);

    double meanSeconds = count == 0
            ? Double.NaN
            : totalSeconds / count;
}
~~~

Ý nghĩa của những giá trị này phụ thuộc loại Timer và registry:

- Với cumulative Timer, count và totalTime là tích lũy.
- Với step Timer, count và totalTime đại diện cho step đã hoàn tất theo cơ chế rollover của registry.
- max là time-window max, chịu ảnh hưởng của expiry và bufferLength.

Không nên dùng các phép đọc này để tự xây dựng logic nghiệp vụ phụ thuộc vào ranh giới step. Step registry chủ yếu điều khiển cách xuất metrics; thời điểm scheduler poll và publish có thể không trùng tuyệt đối với thời điểm một thread khác đọc Timer.

Nếu cần đếm chính xác sự kiện nghiệp vụ hoặc tổng hợp lịch sử lâu dài, hãy dùng dữ liệu nghiệp vụ hoặc backend metrics với truy vấn thích hợp thay vì coi giá trị step hiện tại là tổng tích lũy.

## 9. Những nguyên nhân khiến số liệu có vẻ không khớp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| count giảm về một số nhỏ sau mỗi step | Step registry báo cáo dữ liệu của interval hoàn tất | Xác nhận registry có step semantics và xem publishing interval |
| totalTime giảm hoặc về 0 | Interval mới có ít hoặc không có request | So sánh count cùng interval |
| max vẫn cao sau khi count đã thay đổi | max còn giữ mẫu trong time window | Tính expiry × bufferLength và kiểm tra thời điểm mẫu lớn được ghi |
| max về 0 sau một khoảng không có traffic | Toàn bộ cửa sổ max đã hết mẫu | Kiểm tra expiry, bufferLength và lần record cuối |
| Dashboard chỉ thấy dữ liệu trễ một nhịp | Rollover/poll và publish diễn ra theo lịch | Đối chiếu step boundary, poll và thời điểm nhận dữ liệu |
| Giá trị Prometheus tăng liên tục | Prometheus registry xuất cumulative series | Dùng rate() hoặc increase() để xem thay đổi theo khoảng |
| count và totalTime có vẻ thuộc khoảng khác max | Hai nhóm statistic có semantics cửa sổ khác nhau | Kiểm tra loại registry và cấu hình distribution statistic |

Một bước quan trọng là xác định chính xác registry đang dùng. Không suy ra semantics chỉ từ tên meter hoặc dashboard. Kiểm tra loại registry, step size, cấu hình expiry, bufferLength và kiểu series mà backend nhận được.

## 10. Kiểm thử hành vi tại ranh giới step

Để kiểm tra step registry, nên dùng clock giả hoặc cơ chế test của registry để điều khiển thời gian. Không dùng Thread.sleep() dài trong unit test vì test dễ chậm và không ổn định theo scheduler của máy chạy.

Một kiểm thử tích hợp nên xác minh các điểm sau:

1. Ghi nhận một số request trong step A.
2. Poll/rollover qua ranh giới step.
3. Xác nhận count và totalTime của step A được chuyển sang trạng thái báo cáo.
4. Ghi nhận request trong step B và xác nhận chúng không cộng lẫn vào dữ liệu step A đã hoàn tất.
5. Để một step không có request và xác nhận count/totalTime của step rỗng bằng 0 sau rollover tương ứng.
6. Ghi một latency lớn rồi ghi các latency nhỏ ở step sau; xác nhận max có thể còn giữ đỉnh cũ.
7. Tiến clock qua toàn bộ expiry × bufferLength mà không ghi thêm mẫu; xác nhận max hết hạn theo cấu hình.
8. Kiểm tra dữ liệu thực sự được exporter gửi đi, không chỉ đọc meter trong bộ nhớ.

API kiểm thử cụ thể phụ thuộc loại StepMeterRegistry và phiên bản Micrometer. Với registry của nhà cung cấp, có thể cần fake publisher hoặc kiểm tra request gửi đến endpoint test. Không nên dùng SimpleMeterRegistry để kết luận về step rollover vì SimpleMeterRegistry không có publishing step như StepMeterRegistry.

## 11. Quy trình đọc dashboard khi step vừa đổi

Khi thấy count, totalTime hoặc max thay đổi ở ranh giới step, hãy làm theo thứ tự:

1. Xác định backend đang dùng step registry hay cumulative registry.
2. Xác định độ dài step và thời điểm registry poll/rollover.
3. Đọc count và totalTime như dữ liệu của interval đã hoàn tất nếu registry dùng step semantics.
4. Tính mean bằng totalTime/count chỉ khi count lớn hơn 0.
5. Đọc max như giá trị lớn nhất trong cửa sổ expiry × bufferLength, không mặc định là max của một step.
6. Đối chiếu timestamp nhận dữ liệu ở backend để phát hiện độ trễ publish.
7. Nếu dùng Prometheus cumulative registry, dùng rate()/increase() thay vì mong count tự reset theo step.
8. Ghi rõ đơn vị thời gian và cửa sổ trên panel dashboard.

Một dashboard tốt nên đặt tên panel và mô tả rõ: "request count per step", "total request time per step", "mean latency per step" và "time-window max latency". Cách đặt tên này giúp người vận hành hiểu được mỗi đường biểu diễn đang nói về interval nào.

## 12. Checklist diễn giải count, totalTime và max

Trước khi kết luận từ dữ liệu Timer, xác nhận:

- Đã biết registry là step-based hay cumulative.
- Đã biết step size và cách poll/rollover của registry.
- Count và totalTime được hiểu theo đúng interval hoặc vòng đời tiến trình.
- Mean chỉ được tính khi count lớn hơn 0.
- Max được hiểu là time-window max, không tự động là max của step vừa kết thúc.
- Đã biết expiry và bufferLength thực tế.
- Đã phân biệt cửa sổ Micrometer với query range và retention của backend.
- Đã đối chiếu thời điểm publish với thời điểm dashboard nhận mẫu.
- Đã kiểm thử ranh giới step bằng clock hoặc registry test phù hợp.

Khi step vừa thay đổi, count và totalTime của step registry chuyển sang biểu diễn interval đã hoàn tất, trong khi max có thể tiếp tục phản ánh một cửa sổ gồm nhiều step. Cumulative registry như Prometheus lại giữ count và totalTime tích lũy để backend tính rate hoặc increase. Nắm rõ ba semantics này giúp đọc latency và throughput chính xác, đặc biệt khi dashboard có số liệu thay đổi ngay sau ranh giới publishing interval.

## Tài liệu tham khảo

- [Micrometer - Rate Aggregation](https://docs.micrometer.io/micrometer/reference/concepts/rate-aggregation.html)
- [Micrometer - Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer - StepMeterRegistry source](https://github.com/micrometer-metrics/micrometer/blob/main/micrometer-core/src/main/java/io/micrometer/core/instrument/step/StepMeterRegistry.java)
