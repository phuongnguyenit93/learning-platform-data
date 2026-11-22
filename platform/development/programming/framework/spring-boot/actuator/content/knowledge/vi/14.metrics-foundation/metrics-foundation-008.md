# Hiểu số lượng tổ hợp tag (cardinality) và tác động đến bộ nhớ

## 1. Vì sao một metric có thể tạo ra rất nhiều đối tượng?

Giả sử ứng dụng muốn đếm yêu cầu đọc đơn hàng. Cách gắn tag tưởng như hữu ích là dùng nguyên đường dẫn: `/orders/1001`, `/orders/1002`, rồi tiếp tục với mỗi mã đơn mới. Tên metric vẫn chỉ là `app.http.requests`, nhưng ứng dụng đang tạo thêm các danh tính meter khác nhau.

Trong Micrometer, meter được nhận diện bằng **tên và tập cặp khóa–giá trị của tags** trong một registry. Cùng tên nhưng một giá trị tag thay đổi có thể là một meter khác. Vì registry giữ các meter để tiếp tục ghi và đọc, việc tạo danh tính không giới hạn có thể làm bộ nhớ tăng dần theo thời gian.

**Cardinality** trong ngữ cảnh này là số lượng giá trị hoặc tổ hợp giá trị phân biệt mà một tập dữ liệu đo tạo ra. Cần nói rõ đang xét cardinality của một tag, của các tổ hợp tags cho một tên metric, hay số chuỗi thời gian ở hệ thống giám sát. Ba con số đó có liên hệ nhưng không đồng nhất.

Bài dùng Micrometer **1.13.0**, phù hợp với dòng Spring Boot 3.3, để kiểm chứng bằng Java 17+. Mục tiêu là hiểu nguồn tăng bộ nhớ và thiết kế các chiều phân loại hữu hạn; không cố tìm một số byte cố định áp dụng cho mọi meter.

## 2. Phân biệt số khóa tag, số giá trị và số tổ hợp

### 2.1. Ít khóa tag vẫn có thể có cardinality rất lớn

| Tags được ghi | Số khóa | Cardinality cần chú ý |
| --- | --- | --- |
| `result=success` hoặc `result=failure` | 1 | 2 giá trị nếu chỉ có hai kết quả này |
| `order.id` nhận một mã mới cho mỗi đơn hàng | 1 | Có thể tăng theo tổng số đơn từng được xử lý |
| `method`, `route`, `status` đều là các tập hữu hạn | 3 | Số tổ hợp phụ thuộc số giá trị từng khóa và những tổ hợp thực sự xuất hiện |

Một tag `request.id` có thể nguy hiểm hơn nhiều tag có tập giá trị nhỏ và ổn định. Ngược lại, rất nhiều tag nhị phân cũng có thể tạo không gian tổ hợp lớn: 20 chiều, mỗi chiều có 2 giá trị, có tới `2^20 = 1.048.576` tổ hợp lý thuyết nếu mọi kết hợp đều có thể xuất hiện.

### 2.2. Tích là ước lượng không gian tổ hợp, không phải lúc nào cũng là số đang có

Với cùng một tên metric, giả sử có 2 phương thức, 3 mẫu đường dẫn và 2 mã trạng thái:

```text
Số tổ hợp tối đa theo các tập giá trị đã giả định
  = 2 phương thức × 3 mẫu đường dẫn × 2 trạng thái
  = 12
```

Nếu mọi tổ hợp được ghi ít nhất một lần thì có 12 meter tương ứng. Nếu chỉ 5 tổ hợp thực sự xảy ra, có thể mới có 5 meter. Các chiều có thể tương quan: một đường dẫn chỉ chấp nhận GET, một kết quả không thể xảy ra ở một thao tác nhất định. Vì vậy không lấy tích rồi khẳng định đó là số meter thực đo.

Cách mô tả chính xác hơn là số phần tử của tập các danh tính đã được đăng ký:

```text
ID = (tên metric, tập tags cuối cùng)

N_meter = số ID phân biệt đã được đăng ký trong phạm vi đang xét
```

Các filters và tags chung có thể làm thay đổi ID trước khi registry lưu meter; exporter còn có quy tắc chuyển tên/nhãn riêng. Khi điều tra, cần kiểm tra danh tính ở đúng tầng chứ không chỉ đếm các chuỗi tag trong mã nguồn.

### 2.3. Số sự kiện không phải số meter

Một counter có thể được tăng một triệu lần mà vẫn chỉ là một meter nếu tên và tags không đổi. Ngược lại, một triệu lần ghi, mỗi lần dùng UUID khác nhau làm tag, có thể tạo một triệu danh tính.

Do đó cần tách hai câu hỏi: “đã có bao nhiêu sự kiện?” và “đã đăng ký bao nhiêu cách phân loại?”. Đưa mỗi sự kiện vào một ID riêng làm mất lợi ích tổng hợp của metrics, đồng thời tăng chi phí lưu trạng thái.

## 3. Các giá trị nguy hiểm thường đi vào tag như thế nào?

| Nguồn giá trị | Vì sao dễ tăng cardinality | Hướng biểu diễn phù hợp hơn |
| --- | --- | --- |
| Mã đơn hàng, ID người dùng, request ID | Mỗi đối tượng/lượt gọi có thể tạo một giá trị mới | Metrics dùng nhóm hữu hạn; chi tiết từng đối tượng dùng log/trace phù hợp |
| URL chứa mã hoặc query string | Không gian URL tăng theo dữ liệu và đầu vào | Mẫu route đã được định tuyến, không phải nguyên URL |
| Thông điệp ngoại lệ nguyên văn | Chứa tham số, dữ liệu thay đổi hoặc cả stack trace | Một mã/loại lỗi đã chuẩn hóa và có giới hạn |
| Thời gian hiện tại | Gần như mỗi lần ghi có một giá trị mới | Dùng timestamp của phép đo; không gắn thời gian sự kiện thành tag |
| Tên tệp, từ khóa tìm kiếm, nội dung tự do | Do dữ liệu hoặc người dùng quyết định | Các nhóm nghiệp vụ có danh sách giá trị hữu hạn |
| Tên metric ghép mã đối tượng | Tạo tên mới thay vì tag mới | Tên ổn định; không chuyển vấn đề từ tag sang tên |

Ví dụ cần thay:

```text
app.http.requests{route="/orders/1001", status="200"}
app.http.requests{route="/orders/1002", status="200"}
```

bằng một chiều tổng hợp ổn định như:

```text
app.http.requests{route="/orders/{id}", status="200"}
```

Trong ứng dụng web thực tế, ưu tiên mẫu đường dẫn đã được framework định tuyến, thay vì tự viết một biểu thức thay thế mọi chuỗi số. Chẳng hạn `/v2/reports/2026` có thể chứa phần phiên bản hoặc nhóm nghiệp vụ hợp lệ; tự xóa số một cách mù quáng có thể gộp các thao tác khác nhau.

Yêu cầu không khớp route cũng cần nhãn hữu hạn như `NOT_FOUND` theo thiết kế đo lường. Nếu lấy nguyên đường dẫn của mọi 404, người gửi chỉ cần tạo URL mới liên tục là đã tạo thêm giá trị tag. [Hướng dẫn Micrometer về chuẩn hóa giá trị tag và URI](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

Hash mã người dùng không giải quyết số lượng giá trị phân biệt: một triệu ID khác nhau vẫn thường tạo gần một triệu hash khác nhau. Rút ngắn chuỗi có thể giảm độ dài từng nhãn nhưng không bảo đảm cardinality đủ nhỏ; việc gây va chạm còn làm ý nghĩa nhóm dữ liệu không rõ.

## 4. Cardinality tác động đến bộ nhớ ở những tầng nào?

### 4.1. Ngay trong tiến trình Java

Khi chấp nhận một ID mới, registry cần giữ meter và cấu trúc phục vụ tìm kiếm/đăng ký. Những dữ liệu liên quan có thể gồm tên, tags, ID, phần tử trong map, trạng thái counter/timer/gauge và dữ liệu thống kê bổ sung.

Trong Micrometer 1.13.0, `MeterRegistry` có map theo ID sau khi ánh xạ và cấu trúc liên quan tới ID trước filter. Registry giữ tham chiếu tới các đối tượng cần dùng; việc biến cục bộ trong phương thức hết phạm vi không làm meter tự mất đi. [Mã nguồn đăng ký và lưu meter của Micrometer 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/MeterRegistry.java).

```text
ID mới được chấp nhận
  -> thêm trạng thái đo và cấu trúc tra cứu
  -> registry vẫn còn giữ tham chiếu
  -> các đối tượng đó vẫn còn sống trong heap
```

Bộ thu gom rác (GC) chỉ thu hồi đối tượng không còn được tham chiếu theo các quy tắc của JVM. Nó không tự biết rằng một mã đơn cũ “không còn cần được đo nữa”. Vì vậy tăng tần suất GC hoặc tăng heap không sửa được nguyên nhân tạo ID mới không giới hạn.

Không nên gọi mọi trường hợp này là rò rỉ do lỗi thư viện. Có thể chính mã đo lường đã yêu cầu registry giữ một tập danh tính ngày càng lớn. Cần xác minh ai giữ tham chiếu và vì sao tập đó tiếp tục tăng.

### 4.2. Loại meter và cấu hình phân phối làm chi phí mỗi ID khác nhau

Counter đơn giản và timer có histogram/percentile không có cùng lượng trạng thái. Timer hoặc `DistributionSummary` có thể giữ thêm bộ đếm bucket, các vùng thống kê theo thời gian hoặc dữ liệu để xấp xỉ percentile. Bật các chức năng này trên hàng chục nghìn tổ hợp tags có thể làm chi phí cao hơn nhiều so với một counter ít chiều.

Có thể dùng mô hình định tính:

```text
bộ nhớ liên quan metrics
  ≈ tổng chi phí ID + trạng thái đo + thống kê phân phối của từng meter
    + cấu trúc registry / exporter
    + các bộ nhớ đệm do ứng dụng tự giữ
```

Đây không phải công thức đo byte chính xác. Chi phí phụ thuộc loại registry, phiên bản, cấu hình histogram, số bucket, độ dài chuỗi, cách chia sẻ đối tượng và cấu hình JVM. Không được suy “1.000 meter dùng đúng gấp 500 lần bộ nhớ của 2 meter” chỉ từ tỉ lệ số lượng.

Thời gian hết hạn của MAX hoặc histogram theo cửa sổ không đồng nghĩa ID của timer có TTL. Một mẫu cực đại có thể hết hiệu lực trong khi meter mang bộ tags đó vẫn còn được đăng ký.

### 4.3. Registry tổng hợp và mã ứng dụng có thể giữ thêm trạng thái

Với `CompositeMeterRegistry`, một meter logic có thể được gắn vào nhiều registry con. Các con có trạng thái/cách xuất riêng, nên phải tính chi phí theo những registry thực sự tham gia. Không có một hệ số nhân cố định cho mọi cấu hình, nhưng thêm đích xuất không làm cardinality ở nguồn tự nhỏ đi.

Một `Map<userId, Counter>` trong ứng dụng cũng có thể tăng không giới hạn. Dù dùng bộ nhớ đệm của ứng dụng để bớt tra cứu registry, các ID vẫn tồn tại; xóa một entry trong map đó cũng không tự xóa meter trong registry. Giữ counter trong trường là hữu ích cho các nhóm ổn định, không phải lý do để tạo một trường/cache cho mọi người dùng.

Gauge theo dõi đối tượng bằng tham chiếu yếu cũng không phải chính sách loại bỏ toàn bộ ID theo thời gian. Đừng coi việc đối tượng trạng thái gauge có thể bị thu gom là cách quản lý cardinality của mọi meter.

### 4.4. Hệ thống giám sát còn có chi phí riêng

Mỗi tập nhãn phân biệt có thể trở thành chuỗi thời gian riêng tại hệ thống đích. Ngoài bộ nhớ ứng dụng, còn có chi phí truyền dữ liệu, lưu trữ chuỗi, chỉ mục, truy vấn, biểu đồ và quy tắc cảnh báo. Truy vấn cộng tất cả người dùng lại sau đó không xóa chi phí đã bỏ ra để tạo/lưu từng chuỗi.

Timer có thể xuất nhiều thống kê; histogram còn có các bucket. Ví dụ **giả định** một classic histogram xuất 20 chuỗi bucket, cộng 2 chuỗi count/sum cho mỗi tổ hợp, thì 1.000 tổ hợp tạo khoảng 22.000 chuỗi ở tầng đó. Số 20 trong ví dụ đã bao gồm toàn bộ bucket được tính; chưa cộng các thống kê khác hoặc nhãn hạ tầng. Không dùng con số này thay cho cấu hình exporter thực tế.

Giới hạn phạm vi và số bucket có ảnh hưởng tới dữ liệu phân phối và chi phí, nhưng không thay thế việc giới hạn tags. [Histogram, percentile và tác động cấu hình trong Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html).

## 5. Cardinality còn có chiều thời gian

Giả sử mỗi phút chỉ có 100 người dùng hoạt động, nhưng mỗi phút là 100 người khác. “100 đang hoạt động” không chứng minh rằng registry chỉ giữ 100 meter nếu ứng dụng tạo ID theo người dùng và không có chính sách vòng đời phù hợp.

Trong một tiến trình chạy lâu, cần xem các tổ hợp đã được đăng ký qua thời gian, không chỉ những tổ hợp đang có lưu lượng ngay lúc nhìn dashboard. Ở hệ thống giám sát, việc thay đổi liên tục các giá trị nhãn còn tạo nhiều chuỗi mới qua thời gian, thường được gọi là series churn.

Tags hạ tầng cũng cần xem ở đúng phạm vi. Một `region` cố định chỉ có một giá trị trong mỗi instance có thể không nhân số meter bên trong instance đó, nhưng toàn hệ thống có nhiều vùng/instance thì số chuỗi ở hệ thống đích tăng theo những tổ hợp thực sự tồn tại. Không lấy cardinality của một JVM để thay cho toàn cụm.

Tương tự, một nhóm “top khách hàng” thay đổi liên tục theo thời gian có thể vẫn tạo nhiều nhãn trong lịch sử. Nếu cần nhóm hữu hạn, hãy định nghĩa tập giá trị, quy tắc đưa vào nhóm còn lại và vòng đời rõ ràng; chỉ đặt tên giải pháp là “top N” chưa bảo đảm có giới hạn.

## 6. Thiết kế giới hạn ngay tại điểm ghi

### 6.1. Dùng câu hỏi giám sát để chọn chiều phân loại

Trước khi thêm tag, hãy nêu câu hỏi nó giúp trả lời. “Tỉ lệ lỗi theo kênh web/mobile” phù hợp với một chiều `channel` hữu hạn. “Theo dõi riêng mỗi đơn hàng” thường là yêu cầu xem chi tiết từng sự kiện, phù hợp hơn với log hoặc trace có chính sách dữ liệu tương ứng.

| Yêu cầu | Thiết kế metrics có thể dùng |
| --- | --- |
| Phân biệt kết quả | `result=success|failure|timeout|other` theo danh sách đã định nghĩa |
| Phân biệt nhóm thao tác | `operation=create|read|cancel` |
| Phân biệt loại khách hàng | `tier=free|standard|premium|unknown`, nếu đúng mô hình nghiệp vụ |
| Phân biệt API | Mẫu route ổn định như `/orders/{id}` |
| Điều tra một request cụ thể | Giữ chi tiết/correlation trong log hoặc trace, không thêm request ID vào mọi meter |

Không nhất thiết xóa mọi tag để đạt cardinality thấp nhất. Mục tiêu là có đủ khả năng phân tích với chi phí có thể kiểm soát. Gộp tất cả lỗi thành “khác” có thể làm mất tín hiệu cần điều tra; giữ nguyên toàn bộ thông điệp lỗi lại có thể tạo tập giá trị không giới hạn. Cần một bảng phân loại lỗi có chủ đích.

### 6.2. Chuẩn hóa trước khi đưa giá trị vào API đăng ký meter

```java
String result = switch (resultCode) {
    case "OK" -> "success";
    case "TIMEOUT" -> "timeout";
    case "DECLINED" -> "failure";
    default -> "other";
};

registry.counter("app.orders.completed",
    "operation", "create",
    "result", result).increment();
```

Đoạn trên minh họa trong phương thức có `registry` và `resultCode` không null. Tập giá trị đầu vào có thể rộng, nhưng tag `result` chỉ nhận một trong bốn giá trị đã quy định. Không đưa kèm `resultCode` nguyên văn vào một tag khác rồi kỳ vọng cardinality đã được giới hạn.

Chuẩn hóa trước điểm đăng ký giúp tránh tạo tên/tag thô và các bộ nhớ đệm theo dữ liệu thô do ứng dụng tự quản lý. Filter ánh xạ như `ignoreTags` hoặc `replaceTagValues` vẫn hữu ích khi cần xử lý instrumentation dùng chung, nhưng cần kiểm tra phiên bản, cấu hình và cấu trúc giữ dữ liệu; không mặc định một phép biến đổi tag là cam kết giới hạn toàn bộ heap.

Đặc biệt, một filter tự giữ `Set`/`Map` của **mọi giá trị gốc từng gặp** để rồi ánh xạ sang một vài nhóm vẫn có thể tăng bộ nhớ trong chính filter đó. Nếu thuật toán ánh xạ có thể tính trực tiếp từ dữ liệu và một tập quy tắc hữu hạn, không cần ghi nhớ không giới hạn các đầu vào cũ.

### 6.3. Lập ngân sách cho cả tổ hợp và loại thống kê

Với mỗi tên metric, ghi lại ý nghĩa, các khóa tag, tập giá trị dự kiến, số tổ hợp có thể xảy ra, loại meter và việc có bật histogram/percentile hay không. Sau đó ước lượng số ID trên một instance và số chuỗi toàn hệ thống, bao gồm các nhãn triển khai liên quan.

Ví dụ 20 route × 4 phương thức × 6 nhóm trạng thái cho tối đa 480 tổ hợp theo giả định độc lập. Thêm `tenant` có 10.000 giá trị nâng không gian lý thuyết lên 4.800.000. Một tag bổ sung có thể thay đổi quy mô nhiều hơn toàn bộ các tag trước đó.

Sử dụng giá trị hợp lệ đã biết, đồng thời thử đầu vào lạ, nhiều 404, thông điệp lỗi mới và chuỗi thao tác lặp với ID mới. Chỉ thử lặp đi lặp lại cùng một khách hàng không kiểm tra được nguy cơ cardinality tăng.

## 7. MeterFilter là lớp bảo vệ, không thay thế thiết kế

### 7.1. Giới hạn số giá trị của một tag

Micrometer cung cấp `maximumAllowableTags(prefix, tagKey, limit, onMaxReached)`. Với `MeterFilter.deny()` khi chạm ngưỡng, việc đăng ký những giá trị tag mới vượt giới hạn bị từ chối; mã ứng dụng nhận meter không ghi nhận dữ liệu (NOOP). Các thao tác trên nó không tự tạo nhóm tổng hợp thay thế. [MeterFilter và ý nghĩa DENY](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).

```java
registry.config().meterFilter(
    MeterFilter.maximumAllowableTags(
        "app.http.requests", "route", 100, MeterFilter.deny()));
```

Đây là cấu hình minh họa áp dụng trước khi đăng ký meter. Ngưỡng 100 là ví dụ ngân sách, không phải giá trị chuẩn áp dụng cho mọi ứng dụng.

Các điểm cần hiểu:

- `prefix` là tiền tố tên, không phải một phép chọn chính xác duy nhất nếu có nhiều tên cùng tiền tố.
- Ngưỡng này đếm các **giá trị phân biệt của khóa đang chọn** trong phạm vi filter, không đếm số khóa tag, không trực tiếp giới hạn tích mọi chiều.
- Các tag khác như status, method, tenant vẫn có thể làm nhiều tổ hợp được tạo ra.
- Giá trị đã được chấp nhận vẫn có thể được ghi tiếp; các giá trị mới bị chặn không tự đổi thành `OTHER`.
- Filter này không phải cửa sổ “100 giá trị mỗi phút” hay bộ đệm LRU. Trong triển khai 1.13.0 nó giữ tập giá trị đã quan sát; gỡ meter không đồng nghĩa quota giá trị tự được hoàn lại.
- Các giá trị được giữ có thể phụ thuộc thứ tự xuất hiện, không phải danh sách khách hàng/route quan trọng nhất.

Đây là đặc tính cần xét theo phiên bản và môi trường đồng thời, không phải cam kết giới hạn byte bộ nhớ tuyệt đối. [Triển khai maximumAllowableTags 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/config/MeterFilter.java).

### 7.2. Giới hạn số meter và thứ tự filter

`maximumAllowableMetrics(...)` có thể được dùng như một lớp giới hạn rộng hơn tại registry. Nó liên quan các ID đăng ký theo cơ chế filter, không phải giới hạn byte hoặc số series histogram ở hệ thống đích. Ngân sách cần dành chỗ cho cả meter có sẵn như JVM/HTTP nếu cùng chịu phạm vi giới hạn; không giả định xóa một meter lập tức hoàn lại mọi trạng thái quota của filter.

Các filter có thứ tự. Một filter trả `ACCEPT` có thể làm các quyết định `accept(...)` của filter phía sau không được xét; đặt một quy tắc chấp nhận rộng trước lớp giới hạn có thể vô hiệu hóa điều bạn định bảo vệ. Hãy kiểm chứng với chuỗi filter thực tế thay vì chỉ nhìn một bean riêng lẻ.

Trong ứng dụng Boot có Actuator, có thể khai báo một bean `MeterFilter` để áp dụng qua hạ tầng metrics. Ví dụ bảo vệ chiều `uri` của metric HTTP chuẩn:

```java
package example.metrics;

import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CardinalityConfiguration {
    @Bean
    MeterFilter httpUriBudget() {
        return MeterFilter.maximumAllowableTags(
            "http.server.requests", "uri", 100, MeterFilter.deny());
    }
}
```

Đây là component cấu hình bổ sung cho ứng dụng Boot, không phải chương trình độc lập. Cần xác minh tên metric/tag thực tế, thứ tự và các registry được quản lý. Trong dự án Boot, để Boot quản lý phiên bản Micrometer tương thích. [Tùy chỉnh và filters của metrics trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 7.3. Khi chặn phải hiểu dữ liệu đã thiếu

NOOP cho phép mã nghiệp vụ tiếp tục chạy, nhưng không có nghĩa số liệu vẫn đầy đủ. Nếu có 5 sự kiện và 2 sự kiện dùng nhãn bị từ chối, tổng counter của các meter còn lại có thể chỉ là 3. Không dùng tổng này để kết luận chỉ có 3 yêu cầu thật sự.

Nên có cách phát hiện tình trạng vượt ngân sách bằng dữ liệu ít chiều hoặc công cụ chẩn đoán thích hợp. Nếu tạo thêm một tag chứa nguyên giá trị bị chặn để đếm các lần bị chặn, bạn lại đưa nguy cơ cũ vào một metric mới.

## 8. Thí nghiệm Java: đếm ID thay vì đoán bộ nhớ

Chương trình dưới đây dùng một lượng dữ liệu nhỏ, cố định để quan sát số meter. Nó không cố gây cạn heap và không dùng chênh lệch `Runtime.freeMemory()` sau một lần GC để tuyên bố số byte trên mỗi meter.

Tạo dự án Gradle có wrapper và JDK 17 khả dụng:

```text
tag-cardinality-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat và gradle/wrapper/
  src/main/java/TagCardinalityDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'tag-cardinality-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'TagCardinalityDemo'
}
```

Phiên bản được cố định để tái hiện hành vi đã kiểm chứng; đây không phải khuyến nghị chọn bản vá triển khai.

`src/main/java/TagCardinalityDemo.java`:

```java
import java.util.List;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class TagCardinalityDemo {

    public static void main(String[] args) {
        combinations();
        rawAndNormalizedPaths();
        tagLimit();
    }

    private static void combinations() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            List<String> methods = List.of("GET", "POST");
            List<String> routes = List.of("/orders", "/cart", "/checkout");
            List<String> statuses = List.of("200", "500");

            for (int repeat = 0; repeat < 100; repeat++) {
                for (String method : methods) {
                    for (String route : routes) {
                        for (String status : statuses) {
                            registry.counter("demo.http.requests",
                                "method", method, "route", route, "status", status)
                                .increment();
                        }
                    }
                }
            }
            System.out.println("combinations.meters=" + registry.getMeters().size());
            System.out.println("combinations.events=" + total(registry));
        }
        finally {
            registry.close();
        }
    }

    private static void rawAndNormalizedPaths() {
        SimpleMeterRegistry raw = new SimpleMeterRegistry();
        SimpleMeterRegistry normalized = new SimpleMeterRegistry();
        try {
            for (int i = 0; i < 1000; i++) {
                String path = "/orders/" + i;
                String status = i % 2 == 0 ? "200" : "500";
                record(raw, path, status);
                record(normalized, routeLabel(path), status);
            }
            System.out.println("raw.meters=" + raw.getMeters().size());
            System.out.println("normalized.meters=" + normalized.getMeters().size());

            for (int i = 0; i < 1000; i++) {
                String path = "/orders/" + i;
                String status = i % 2 == 0 ? "200" : "500";
                record(raw, path, status);
                record(normalized, routeLabel(path), status);
            }
            System.out.println("raw.repeatMeters=" + raw.getMeters().size());
            System.out.println("normalized.repeatMeters="
                + normalized.getMeters().size());
            System.out.println("raw.events=" + total(raw));
            System.out.println("normalized.events=" + total(normalized));
        }
        finally {
            raw.close();
            normalized.close();
        }
    }

    private static String routeLabel(String path) {
        return path.matches("/orders/[0-9]+") ? "/orders/{id}" : "NOT_FOUND";
    }

    private static void record(MeterRegistry registry, String route, String status) {
        registry.counter("demo.http.requests", "route", route, "status", status)
            .increment();
    }

    private static void tagLimit() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            registry.config().meterFilter(MeterFilter.maximumAllowableTags(
                "demo.limited.requests", "tenant", 2, MeterFilter.deny()));

            for (String tenant : List.of("alpha", "beta", "gamma", "alpha", "delta")) {
                registry.counter("demo.limited.requests", "tenant", tenant)
                    .increment();
            }

            System.out.println("limited.meters=" + registry.getMeters().size());
            System.out.println("limited.recordedEvents=" + total(registry));
            System.out.println("limited.gammaAbsent="
                + (registry.find("demo.limited.requests")
                    .tag("tenant", "gamma").counter() == null));

            Counter rejected = registry.counter(
                "demo.limited.requests", "tenant", "gamma");
            rejected.increment();
            System.out.println("limited.rejectedCount=" + rejected.count());
        }
        finally {
            registry.close();
        }
    }

    private static double total(MeterRegistry registry) {
        return registry.getMeters().stream()
            .filter(Counter.class::isInstance)
            .map(Counter.class::cast)
            .mapToDouble(Counter::count)
            .sum();
    }
}
```

Chạy tại thư mục dự án:

```bash
./gradlew -q run --console=plain
```

Trên Windows PowerShell dùng `.\gradlew.bat -q run --console=plain`. Gradle giải quyết phụ thuộc rồi biên dịch/chạy `main`. Nếu dùng `javac`/`java` trực tiếp, phải có classpath gồm các JAR Micrometer và phụ thuộc đã giải quyết ở cả hai bước.

Đầu ra của chương trình:

```text
combinations.meters=12
combinations.events=1200.0
raw.meters=1000
normalized.meters=2
raw.repeatMeters=1000
normalized.repeatMeters=2
raw.events=2000.0
normalized.events=2000.0
limited.meters=2
limited.recordedEvents=3.0
limited.gammaAbsent=true
limited.rejectedCount=0.0
```

### 8.1. Tổ hợp hữu hạn được dùng lại

Vòng lặp đầu ghi đủ 2 phương thức × 3 route × 2 trạng thái, lặp 100 lần. Kết quả là 1.200 sự kiện nhưng chỉ 12 meter. Việc tăng số lần ghi trên cùng các ID không tạo thêm 1.188 meter.

### 8.2. Dùng đường dẫn thô và mẫu route cho cùng dữ liệu

Trong lượt đầu, 1.000 đường dẫn có mã đơn khác nhau tạo 1.000 meter ở registry `raw`. Mỗi đường dẫn trong tập này chỉ đi kèm một trạng thái đã chọn, nên số tổ hợp thực có là 1.000, không tự động là 1.000 × 2.

Ở registry `normalized`, tất cả đường dẫn hợp lệ về một mẫu `/orders/{id}` và có hai trạng thái, nên có 2 meter. Lặp đúng tập đường dẫn lần nữa không đổi số meter của cả hai bên; tổng sự kiện đều tăng lên 2.000.

Như vậy chuẩn hóa giữ được tổng số lượt và phân loại theo trạng thái, đồng thời bỏ khả năng chia metrics theo mã đơn. Đây là sự lựa chọn độ chi tiết có chủ đích; nếu phải tìm riêng một đơn, cần nguồn dữ liệu chi tiết phù hợp.

`routeLabel()` chỉ minh họa cho đúng mẫu đầu vào của thí nghiệm. Nó không phải bộ chuẩn hóa URI dùng chung cho ứng dụng Spring; ngoài thực tế nên dùng thông tin route đã định tuyến để giữ đúng ngữ nghĩa.

### 8.3. Bộ giới hạn không gom dữ liệu bị chặn vào nhóm khác

Filter chấp nhận hai giá trị tenant đầu tiên là `alpha`, `beta`. Lượt `alpha` xuất hiện lần nữa vẫn được đếm. `gamma`, `delta` không được tạo thành meter, nên có 2 meter với tổng ghi nhận là 3.

Biến `rejected` vẫn là một `Counter` có thể gọi `increment()`, nhưng count đọc lại bằng 0 vì nó là meter không ghi nhận. Không có meter `tenant=OTHER` được tạo. Thí nghiệm đơn luồng cố định thứ tự để có đầu ra lặp lại; không suy từ đó rằng trong hệ thống đồng thời luôn giữ đúng một nhóm tenant nào đó.

Chương trình tự sở hữu các registry nên đóng chúng trong `finally`. Service nghiệp vụ được Spring tiêm registry dùng chung không tự đóng registry sau mỗi yêu cầu.

## 9. Kiểm tra tác động bộ nhớ trong ứng dụng thực

### 9.1. Chứng minh tốc độ tạo danh tính

Đầu tiên tách số request khỏi số meter. Theo dõi số ID của các tên nghi vấn ở đúng registry trong một khoảng tải có kiểm soát, đồng thời đếm số giá trị phân biệt của các tag như URI, tenant hoặc mã lỗi. Nếu request chỉ dùng lại các nhóm đã biết mà số ID vẫn tăng, hãy xem tags/names nào thực sự thay đổi.

`registry.getMeters().size()` phản ánh số meter mà registry đó công bố ở lúc đọc; nó không đo byte heap, không đếm toàn bộ series ở hệ thống giám sát và không tự bao quát mọi registry trong tiến trình. Nếu thêm một gauge để công bố chính số lượng này, tránh cho gauge đó tags biến thiên theo từng meter.

Endpoint `/actuator/metrics` có thể hỗ trợ tìm tên và tags khi đã được cấu hình, nhưng đọc một phản hồi gộp theo tên không chứng minh chỉ có một ID. Một counter mang hàng nghìn bộ tags vẫn có thể nằm dưới một tên metric.

### 9.2. Xác minh ai giữ bộ nhớ

Đối chiếu biến động số ID với dữ liệu heap/GC trong cùng khoảng tải. Nếu cần phân tích heap, tìm các cấu trúc registry, meter, tags, histogram và cache của ứng dụng, rồi xem đường tham chiếu giữ chúng còn sống và retained size bằng công cụ phù hợp.

Cần cùng phiên bản, cấu hình thống kê và điều kiện tải để so sánh có ý nghĩa. Cấp phát tạm thời khi tạo chuỗi/tag khác với bộ nhớ còn được giữ lâu; một số đo heap tức thời hoặc tổng lượng cấp phát không thay thế việc phân tích các đối tượng còn sống.

Không tạo thêm một `Set` không giới hạn chứa mọi ID chỉ để điều tra một vấn đề cardinality rồi giữ nó trong ứng dụng mãi mãi. Bản thân công cụ đếm độc nhất cũng cần phạm vi và vòng đời.

### 9.3. Kiểm tra cả hệ thống đích

Ở hệ thống giám sát, kiểm tra số series theo họ metric, các nhãn có nhiều giá trị và tốc độ tạo series mới. Chẳng hạn Prometheus có thể dùng truy vấn `count by (__name__) ({job="checkout"})` để xem số chuỗi hiện có theo tên trong phạm vi job ví dụ; đây không phải phép đo số meter Java và cũng không bao quát mọi chuỗi từng xuất hiện trong lịch sử.

Histogram, các nhãn instance và các lần triển khai thay đổi có thể làm số series lớn hơn nhiều số ID bạn đếm trong một JVM. [Thực hành instrumentation và chi phí các chiều nhãn của Prometheus](https://prometheus.io/docs/practices/instrumentation/).

### 9.4. Sửa nguồn tạo trước khi tìm cách dọn dữ liệu

Ưu tiên sửa tên/tag không giới hạn, chuẩn hóa theo miền hữu hạn và kiểm chứng dữ liệu vẫn trả lời được câu hỏi giám sát. Có thể bổ sung giới hạn như lớp bảo vệ và thu hẹp thống kê phân phối về những metric cần thiết.

Không coi tắt histogram, tăng heap, tăng GC hoặc khởi động lại định kỳ là lời giải cho ID mới vẫn xuất hiện không giới hạn. Xóa meter còn có thể làm mất liên tục số đếm, trong khi mã ứng dụng giữ tham chiếu cũ hoặc tạo lại meter ngay sau đó. Dữ liệu đã được xuất ở hệ thống đích còn có vòng đời riêng.

Khi thực sự cần meter có vòng đời động, phải thiết kế quyền sở hữu, điểm loại bỏ, tham chiếu trong cache và tác động tới truy vấn; không mặc định registry thông thường tự thực hiện LRU/TTL cho mọi danh tính.

## 10. Các nhầm lẫn cần tránh

| Nhận định | Điều cần phân biệt |
| --- | --- |
| Chỉ có một tag nên an toàn | Một tag nhận UUID mới mỗi lần vẫn có cardinality không giới hạn |
| Chỉ có một tên metric nên chỉ có một meter | Mỗi bộ tags phân biệt có thể tạo ID khác |
| Nhiều request thì phải có nhiều meter | Cùng ID có thể được ghi lại nhiều lần |
| Tích số giá trị từng tag luôn là số thực tế | Tích là ước lượng không gian; cần xem các tổ hợp thực xuất hiện |
| Hash hoặc rút ngắn ID đã giải quyết cardinality | Độ dài chuỗi và số giá trị phân biệt là hai yếu tố khác nhau |
| Dashboard đã sum nên không còn tốn tài nguyên theo tag | Chi phí đăng ký/xuất/lưu chuỗi đã phát sinh trước truy vấn tổng hợp |
| GC sẽ xóa meter không có request gần đây | Registry/caches còn có thể giữ tham chiếu; không có TTL chung mặc định |
| MAX hết cửa sổ nghĩa là meter hết hạn | Trạng thái thống kê hết hạn khác vòng đời của ID |
| Gauge tham chiếu yếu nên không cần giới hạn ID | Vòng đời trạng thái gauge không thay thế ngân sách danh tính |
| `maximumAllowableTags` giới hạn toàn bộ tổ hợp | Nó giới hạn một khóa trong phạm vi filter; các chiều khác vẫn nhân lên |
| Bị từ chối thì dữ liệu tự về OTHER | DENY trả NOOP; dữ liệu bị bỏ nếu không có thiết kế khác |
| Một meter luôn xuất một series | Loại meter, histogram và exporter có thể tạo nhiều series |

## 11. Tự kiểm tra

1. Một metric có `method` 2 giá trị, `route` 10 giá trị và `status.group` 5 giá trị. Tính số tổ hợp tối đa theo giả định độc lập và nêu lý do số thực có thể thấp hơn.
2. Có 100.000 request dùng cùng một bộ tags. So sánh số meter với 100.000 request, mỗi request dùng `request.id` riêng.
3. Trong ví dụ Java, giải thích vì sao 1.000 đường dẫn thô tạo 1.000 meter nhưng mẫu route chỉ tạo 2, và vì sao tổng sự kiện hai bên vẫn bằng nhau.
4. Giữ 20 route nhưng thêm `tenant` có 50.000 giá trị. Nêu các câu hỏi cần trả lời trước khi chấp nhận chiều này và ảnh hưởng khi bật histogram.
5. Một filter giới hạn 2 giá trị nhưng có 5 sự kiện theo thứ tự alpha, beta, gamma, alpha, delta. Dự đoán tổng counter và giải thích dữ liệu nào không còn được giữ.
6. Heap vẫn tăng sau khi biến counter trong phương thức đã hết phạm vi. Chỉ ra những nơi có thể còn giữ tham chiếu và vì sao gọi GC không tự giải quyết.
7. Đề xuất nhóm tag hữu hạn cho một thông điệp lỗi chứa mã đơn, thời gian và nguyên nhân; nêu chi tiết nào nên chuyển sang log/trace thay vì metrics.

Cardinality cần được thiết kế cùng ý nghĩa phép đo: **giữ các chiều phân tích có ích, chặn không gian danh tính không giới hạn và kiểm chứng chi phí ở cả JVM lẫn hệ thống giám sát**.
