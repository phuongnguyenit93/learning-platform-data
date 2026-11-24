# Giám sát hạn ngạch, đặt ngân sách và phát hiện tăng chi phí

Ứng dụng Spring Boot có thể hoạt động ổn định trong lúc mức sử dụng dịch vụ cloud tiến gần giới hạn hoặc hóa đơn tăng nhanh hơn dự kiến. Một queue sắp chạm giới hạn throughput có thể làm request bị throttling; một project có thể hết quota tạo địa chỉ IP hoặc CPU; một tác vụ đồng bộ lỗi có thể retry liên tục và tạo thêm request, log cùng lưu lượng mạng. Nếu chỉ xem hóa đơn cuối tháng, nhóm thường phát hiện vấn đề sau khi người dùng đã bị ảnh hưởng.

Quản lý hiệu năng và chi phí vì vậy cần hai vòng quan sát liên tục. Vòng thứ nhất theo dõi **hạn ngạch và năng lực** để biết workload còn bao nhiêu headroom trước giới hạn của dịch vụ. Vòng thứ hai theo dõi **ngân sách và mức chi tiêu** để phát hiện sai lệch so với kế hoạch. Phát hiện bất thường bổ sung một góc nhìn khác: hệ thống có thể chưa vượt ngân sách nhưng mức tăng đột ngột vẫn cần điều tra.

Bài học này trình bày cách lập danh mục quota, thiết kế cảnh báo, xây dựng ngân sách theo workload, phát hiện tăng chi phí và phản ứng an toàn. Các ví dụ áp dụng cho AWS, Microsoft Azure, Google Cloud và ứng dụng Spring Boot. Tên metric, phạm vi quota, độ trễ dữ liệu billing và khả năng tự động hóa phụ thuộc dịch vụ, region, subscription/account/project và cấu hình hiện hành.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt quota, service limit, capacity, budget và anomaly alert.
- Xác định quota theo dịch vụ, region, account, subscription, project và loại tài nguyên.
- Tính mức sử dụng, headroom, tốc độ tiêu thụ và thời gian dự kiến chạm giới hạn.
- Thiết kế ngân sách theo môi trường, dịch vụ, team hoặc tính năng với cảnh báo actual và forecast.
- Cấu hình các cơ chế theo dõi của AWS, Azure và Google Cloud.
- Dùng metric Spring Boot để quan sát request, retry, throttling, dung lượng và chi phí ước lượng.
- Điều tra một đợt tăng chi phí và áp dụng biện pháp giảm thiểu có kiểm soát.

## 1. Phân biệt quota, budget và anomaly

Ba khái niệm này trả lời ba câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Quota / service limit | Dịch vụ cho phép tạo hoặc sử dụng tối đa bao nhiêu tài nguyên? | Số VM vCPU trong một region, số request mỗi giây, số queue hoặc số IP. |
| Budget | Nhóm dự kiến chi bao nhiêu trong một kỳ? | Môi trường production có ngân sách 8.000 USD mỗi tháng. |
| Cost anomaly | Mức chi tiêu có lệch bất thường so với hành vi thông thường không? | Chi phí egress tăng gấp ba lần so với baseline dù traffic chỉ tăng nhẹ. |

Quota thường giới hạn năng lực hoặc số lượng tài nguyên. Budget theo dõi chi phí so với mục tiêu tài chính. Anomaly detection tìm ra thay đổi khác thường trong dữ liệu chi tiêu. Một dịch vụ có thể còn quota nhưng đã vượt budget; một dịch vụ có thể vượt quota dù chi tiêu còn thấp; một anomaly có thể xuất hiện trước khi cả hai ngưỡng bị chạm.

### 1.1. Các dạng quota thường gặp

- **Quota tài nguyên:** số instance, vCPU, volume, IP address, database, cluster, bucket hoặc secret được phép tạo.
- **Quota tốc độ:** request mỗi giây, message mỗi giây, transaction mỗi phút hoặc số lần gọi API trong một cửa sổ.
- **Quota đồng thời:** số kết nối, execution, job, consumer, session hoặc function invocation đồng thời.
- **Quota dung lượng:** số GB, số item, số partition, số topic hoặc kích thước payload.
- **Quota theo vùng:** giới hạn áp dụng riêng cho từng region hoặc zone.
- **Quota theo tài khoản/dự án:** giới hạn dùng chung ở cấp account, subscription, project hoặc organization.
- **Quota động theo dịch vụ:** giới hạn có thể thay đổi theo lịch sử sử dụng, loại tài khoản, hợp đồng hoặc quyết định của nhà cung cấp.

Quota có thể là giới hạn cứng, giới hạn mềm có thể xin tăng, hoặc mức khuyến nghị do dịch vụ áp dụng. Một số dịch vụ có nhiều lớp giới hạn đồng thời: giới hạn tài khoản, giới hạn region và giới hạn riêng cho một API. Khi điều tra lỗi throttling, cần xác định đúng lớp giới hạn đã bị chạm.

### 1.2. Budget không phải công tắc ngắt chi tiêu

Budget thường gửi thông báo khi chi phí thực tế hoặc dự báo đạt một tỷ lệ đã đặt. Cảnh báo giúp người phụ trách can thiệp, nhưng không mặc nhiên dừng tài nguyên hoặc chặn mọi request. Một số nền tảng có hành động tự động hoặc cho phép nối thông báo với workflow; hành động đó cần được cấu hình, kiểm thử và giới hạn phạm vi riêng.

Không nên xem budget alert như một hard spending cap. Dữ liệu billing có thể đến trễ, chi phí có thể tiếp tục phát sinh trong lúc cảnh báo được xử lý, và một số khoản đã tiêu thụ chỉ được ghi nhận sau. Muốn giới hạn chi phí, cần phối hợp budget với quota, policy, giới hạn concurrency, rate limiting, kiểm soát triển khai và quy trình vận hành.

## 2. Lập danh mục quota và tính headroom

Bước đầu tiên là biết workload đang phụ thuộc vào quota nào. Danh mục nên gắn quota với tài nguyên và luồng nghiệp vụ cụ thể, để cảnh báo có người chịu trách nhiệm xử lý.

### 2.1. Xác định phạm vi của quota

Với mỗi quota, ghi lại:

- Nhà cung cấp, account/subscription/project và môi trường.
- Dịch vụ, API hoặc loại tài nguyên bị giới hạn.
- Phạm vi global, regional hay zonal.
- Đơn vị, giới hạn hiện tại và cách nhà cung cấp tính mức sử dụng.
- Giá trị sử dụng hiện tại, đỉnh trong giờ/ngày và tốc độ tăng.
- Có thể xin tăng hay không, quy trình và thời gian xử lý dự kiến.
- Workload nào sẽ bị ảnh hưởng khi chạm giới hạn.
- Dashboard, metric, log hoặc API dùng để kiểm tra.

Ví dụ một queue có thể có giới hạn số message đang chờ, throughput publish, throughput receive và số kết nối. Chỉ ghi “quota queue” là chưa đủ; phải xác định chính xác loại giới hạn và metric tương ứng.

### 2.2. Tính utilization và headroom

Với quota dạng số lượng hoặc dung lượng:

```text
Utilization (%) = Current usage / Quota limit × 100
Headroom         = Quota limit - Current usage
```

Ví dụ quota là 200 instance, hiện dùng 150:

```text
Utilization = 150 / 200 × 100 = 75%
Headroom    = 200 - 150 = 50 instance
```

Với quota dạng tốc độ, phải so sánh cùng cửa sổ thời gian và đơn vị:

```text
Rate utilization = Observed requests per second / Allowed requests per second
```

Không lấy tổng request trong một ngày chia cho quota mỗi giây. Với giới hạn burst hoặc token bucket, cần quan sát cả tốc độ trung bình, burst và thời gian phục hồi token.

### 2.3. Ước lượng thời gian chạm quota

Khi usage tăng tương đối đều, có thể ước lượng:

```text
Thời gian tới giới hạn
  = Headroom / Tốc độ tăng usage
```

Ví dụ còn 50 instance headroom và trung bình tăng 5 instance mỗi tuần, thời gian ước lượng tới quota là 10 tuần. Nếu workload tăng theo đợt hoặc có mùa vụ, dùng tốc độ tăng ở giờ/ngày đỉnh và mô hình tăng trưởng phù hợp thay vì trung bình dài hạn.

Đối với quota tốc độ, cảnh báo cần phản ứng nhanh hơn thời gian xin tăng quota. Nếu dịch vụ có burst ngắn, quan sát mức tiêu thụ trong cửa sổ tương ứng với cơ chế giới hạn của dịch vụ.

### 2.4. Thiết kế ngưỡng cảnh báo

Không có một ngưỡng phần trăm đúng cho mọi quota. Ngưỡng phải dựa trên thời gian cần để phát hiện, điều tra và xin tăng giới hạn. Một ví dụ để bắt đầu:

| Mức | Ví dụ ngưỡng | Ý nghĩa |
|---|---:|---|
| Theo dõi | 60–70% | Xác nhận xu hướng và dự báo headroom. |
| Cảnh báo | 80% | Owner kiểm tra tăng trưởng, kế hoạch scale và khả năng xin quota. |
| Khẩn cấp | 90–95% | Ưu tiên hành động trước khi workload bị throttling hoặc không tạo được tài nguyên. |

Đây là ngưỡng minh họa. Với quota có thể tăng trong vài phút, có thể đặt ngưỡng khác với quota cần nhiều ngày để phê duyệt. Với giới hạn tốc độ, dùng cảnh báo theo rate, burst, throttling và error rate thay vì chỉ dựa vào utilization phần trăm.

## 3. Đo quota và throttling trong ứng dụng Spring Boot

Cloud console cho biết usage ở cấp dịch vụ hoặc tài khoản. Metric ở ứng dụng cho biết request nào đang tiêu thụ tài nguyên, lỗi nào phát sinh và người dùng nào bị ảnh hưởng ở mức nghiệp vụ. Hai nguồn bổ trợ nhau.

### 3.1. Các tín hiệu nên theo dõi

- Số request theo dịch vụ và operation.
- Số response throttling hoặc quota exceeded, chẳng hạn HTTP 429 hoặc lỗi tương đương của SDK.
- Timeout, retry, số lần thử trên một thao tác và thời gian backoff.
- Số kết nối, số message, queue depth, consumer lag và concurrency.
- Byte đọc/ghi, dung lượng tạo mới và tốc độ tăng.
- Thời gian xử lý p50/p95/p99 cùng error rate.
- Region, account/project và phiên bản ứng dụng để khoanh vùng thay đổi.

Không phải mọi dịch vụ trả quota error bằng HTTP 429; SDK có thể chuyển lỗi thành exception riêng hoặc dùng mã dịch vụ khác. Hãy phân loại theo exception code và response metadata của client cụ thể.

### 3.2. Metric cho request và throttling

Ví dụ sau dùng Micrometer để đếm request và phản hồi throttling tại adapter. `service` và `operation` phải lấy từ tập giá trị cấu hình hữu hạn, không lấy từ user input hoặc resource ID.

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class CloudRequestMetrics {
    private final MeterRegistry registry;

    public CloudRequestMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordCall(String service, String operation, String outcome) {
        registry.counter("cloud.requests",
                "service", service,
                "operation", operation,
                "outcome", outcome).increment();
    }

    public void recordThrottled(String service, String operation) {
        registry.counter("cloud.throttled",
                "service", service,
                "operation", operation).increment();
    }
}
```

Ở lớp gọi SDK, tăng `cloud.throttled` khi nhận được mã throttling/quota tương ứng; ghi `cloud.requests` cho từng kết quả success, error hoặc throttled. Nếu cần đếm số HTTP attempt thực tế, đặt instrumentation ở HTTP transport hoặc SDK interceptor vì một lần gọi logic có thể tự retry nhiều lần.

### 3.3. Retry có kiểm soát

Khi dịch vụ trả throttling, retry có thể giúp vượt qua giới hạn tạm thời. Tuy nhiên, retry không giới hạn có thể làm tình trạng nặng hơn: request mới tiếp tục tới dịch vụ đang quá tải, queue tăng, thời gian xử lý kéo dài và chi phí thao tác tăng.

Áp dụng các nguyên tắc:

- Chỉ retry lỗi có khả năng tạm thời; không retry lỗi xác thực, quyền hoặc dữ liệu không hợp lệ.
- Dùng exponential backoff và jitter để các client không retry đồng loạt.
- Tôn trọng `Retry-After` hoặc metadata retry của SDK khi dịch vụ cung cấp.
- Đặt giới hạn số lần thử và tổng thời gian retry trong ngân sách timeout của request.
- Dùng circuit breaker hoặc load shedding khi phụ thuộc liên tục không đáp ứng.
- Đảm bảo thao tác có tính idempotent hoặc dùng idempotency key trước khi retry ghi dữ liệu.
- Ghi metric số attempt, số retry, thời gian chờ và kết quả cuối.

Không tăng retry count chỉ để giảm lỗi hiển thị. Nếu tỷ lệ throttling tăng, kiểm tra quota, burst, concurrency, hot partition, batch size và tốc độ producer.

### 3.4. Phân biệt giới hạn ứng dụng và quota nhà cung cấp

Có thể đặt rate limiter trong Spring Boot để giới hạn tốc độ theo tenant hoặc endpoint. Đây là giới hạn do ứng dụng quản lý, giúp bảo vệ downstream và phân bổ công bằng. Nó không thay thế quota của cloud: các workload khác trong cùng account có thể dùng chung quota, và dịch vụ vẫn có thể throttle ở mức thấp hơn.

Đối với một hệ thống nhiều replica, rate limit cục bộ trong từng JVM không phải giới hạn toàn cục. Nếu cần tổng tốc độ ổn định qua nhiều instance, dùng bộ điều phối phân tán hoặc giới hạn ở gateway/broker, đồng thời giữ headroom cho traffic nền và tác vụ vận hành.

## 4. Đặt ngân sách cloud

Ngân sách nên phản ánh cách tổ chức workload và trách nhiệm chi tiêu. Một budget toàn account giúp kiểm soát tổng, nhưng khó xác định team hoặc dịch vụ nào gây tăng chi phí. Nên có các budget tổng và budget theo nhóm quan trọng khi nền tảng hỗ trợ.

### 4.1. Chọn phạm vi ngân sách

Các phạm vi thường hữu ích:

- **Account/subscription/project:** tổng chi phí của môi trường hoặc đơn vị quản lý.
- **Environment:** production, staging, development hoặc sandbox.
- **Service:** compute, database, object storage, messaging, logging hoặc network.
- **Team/product:** nhóm sở hữu workload hoặc sản phẩm.
- **Cost center/tag/label:** phân bổ theo mã chi phí, ứng dụng, tenant hoặc tính năng.
- **Region:** nhận diện chi phí tăng ở một khu vực triển khai.

Không tạo quá nhiều budget nhỏ nếu dữ liệu billing chưa đủ chi tiết hoặc owner không có quyền hành động. Mỗi budget cần có người nhận cảnh báo, cách xử lý và thời gian phản hồi.

### 4.2. Xác định mức ngân sách

Có thể bắt đầu từ usage thực tế của các kỳ trước, loại bỏ khoản bất thường đã giải thích, rồi điều chỉnh theo kế hoạch traffic và thay đổi kiến trúc:

```text
Budget kỳ tới
  = Baseline chi phí
  + Chi phí tăng trưởng dự kiến
  + Chi phí thay đổi kiến trúc đã duyệt
  + Dự phòng có chủ đích
```

Baseline nên bao gồm chi phí cố định, tải nền và workload thường xuyên. Chi phí dự án ngắn hạn, migration hoặc thử tải nên được theo dõi bằng budget riêng để không làm sai baseline production.

Ghi rõ currency, kỳ ngân sách, ngày bắt đầu/kết thúc, phạm vi resource và cách xử lý discount, credit, tax hoặc support. Đối chiếu cùng một cách hiển thị cost (actual, amortized hoặc net) giữa dashboard và báo cáo.

### 4.3. Actual, forecast và burn rate

- **Actual cost:** chi phí đã được ghi nhận trong kỳ. Dữ liệu có thể đến trễ so với thời điểm request phát sinh.
- **Forecast cost:** ước lượng tổng chi phí cuối kỳ dựa trên dữ liệu và mô hình dự báo của nhà cung cấp.
- **Budget variance:** chênh lệch giữa actual hoặc forecast với ngân sách.
- **Burn rate:** tốc độ tiêu thụ ngân sách theo thời gian.

Với mô hình tuyến tính đơn giản:

```text
Forecast cuối kỳ ≈ Actual đến hiện tại / Phần thời gian đã trôi qua
                 × Tổng thời gian của kỳ
```

Công thức này chỉ là phép chiếu thô. Nó không phù hợp với workload có mùa vụ, lịch batch, chiến dịch, chu kỳ thanh toán hoặc chi phí một lần. Dùng forecast của nền tảng và dữ liệu lịch sử theo ngày/tuần khi cần mô hình chính xác hơn.

### 4.4. Cấu hình cảnh báo budget

Có thể bắt đầu với các mức cảnh báo actual và forecast, ví dụ 50%, 80% và 100% ngân sách. Mức 50% dùng để kiểm tra xu hướng, 80% yêu cầu owner xác nhận phần chi tiêu còn lại, 100% kích hoạt quy trình xử lý theo chính sách. Cảnh báo forecast ở mức thấp hơn có thể giúp hành động trước khi actual chạm ngưỡng.

Đây là cấu hình mẫu; mức phù hợp phụ thuộc vào độ trễ billing, độ lớn workload, khả năng dừng tài nguyên và mức độ chấp nhận rủi ro. Nếu dữ liệu cập nhật theo ngày, cảnh báo ở mức 100% có thể đến sau khi đã vượt budget. Dùng forecast, quota và metric vận hành để tạo thời gian phản ứng.

### 4.5. Ngân sách không thay thế kiểm soát kỹ thuật

Khi budget alert kích hoạt, cần biết hành động nào an toàn:

- Dừng môi trường thử nghiệm hoặc job không thiết yếu.
- Giảm concurrency hoặc tốc độ producer nếu downstream đang bị quá tải.
- Tạm hoãn scale hoặc tạo tài nguyên không thuộc kế hoạch đã duyệt.
- Điều tra egress, logging, retry, query hoặc replication tăng bất thường.
- Yêu cầu owner phê duyệt trước khi tăng quota hoặc mở rộng tài nguyên.

Không tự động dừng database, queue hoặc dịch vụ production chỉ vì một ngưỡng budget đã chạm nếu chưa đánh giá tác động tới dữ liệu, giao dịch và khả năng khôi phục. Nếu dùng automation, phải giới hạn scope, có điều kiện loại trừ, audit trail và cách rollback.

## 5. Phát hiện tăng chi phí bất thường

Anomaly detection tìm những thay đổi khác với hành vi thông thường. Ví dụ, chi phí storage tăng dần theo tăng trưởng dữ liệu có thể là bình thường; egress tăng đột ngột vào ban đêm trong khi traffic không đổi có thể là dấu hiệu cấu hình sai, vòng lặp đồng bộ hoặc dữ liệu bị truy xuất hàng loạt.

### 5.1. Các kiểu bất thường

- **Spike:** chi phí tăng nhanh trong thời gian ngắn.
- **Drift:** baseline tăng đều qua nhiều kỳ mà không có thay đổi workload tương ứng.
- **Unexpected service:** xuất hiện dịch vụ hoặc SKU chưa có trong kế hoạch.
- **Unexpected region:** tài nguyên hoặc data transfer xuất hiện ở region mới.
- **Retry storm:** request, message delivery và log tăng cùng lúc với lỗi downstream.
- **Storage leak:** dung lượng tăng nhưng số object nghiệp vụ không tăng tương ứng do versioning, backup hoặc dữ liệu tạm.
- **Egress anomaly:** byte outbound tăng do cache miss, replication, tải dữ liệu hoặc truy cập ngoài dự kiến.
- **Idle resource:** compute, database hoặc IP vẫn chạy sau khi workload đã kết thúc.

### 5.2. Thiết lập baseline

Baseline tốt cần có ngữ cảnh:

- Theo dõi theo ngày và giờ để nhận diện mùa vụ, lịch batch và ngày làm việc.
- Tách môi trường, service, SKU, region và cost center.
- Ghi nhận ngày release, migration, campaign và thay đổi cấu hình.
- So sánh chi phí với driver workload như request, user active, GB lưu, message và byte egress.
- Dùng khoảng thời gian đủ dài để nhận ra chu kỳ, nhưng đủ mới để phản ánh kiến trúc hiện tại.

Không chỉ theo dõi tổng tiền. Có thể dùng chỉ số unit economics như chi phí trên 1.000 request, mỗi đơn hàng, mỗi GB được xử lý hoặc mỗi tenant hoạt động. Nếu tổng chi phí tăng 20% nhưng request tăng 40%, chi phí trên request có thể đã cải thiện. Ngược lại, tổng tiền chưa vượt budget nhưng chi phí trên một giao dịch tăng mạnh vẫn đáng điều tra.

### 5.3. Ngưỡng tuyệt đối và ngưỡng tương đối

Có thể kết hợp hai kiểu điều kiện:

- **Ngưỡng tuyệt đối:** cảnh báo khi chi phí hoặc byte vượt một mức cụ thể. Hữu ích với khoản nhỏ nhưng nhạy cảm hoặc dịch vụ mới.
- **Ngưỡng tương đối:** cảnh báo khi chi phí lệch một tỷ lệ so với baseline. Hữu ích khi workload có quy mô khác nhau theo thời gian.

Ví dụ một khoản tăng từ 1 lên 10 USD là tăng 900% nhưng tác động tài chính nhỏ; một khoản tăng từ 10.000 lên 12.000 USD là tăng 20% nhưng có thể đáng quan tâm. Kết hợp delta tiền tuyệt đối, tỷ lệ thay đổi và ảnh hưởng tới budget để giảm cảnh báo nhiễu.

### 5.4. Xác nhận bất thường bằng tín hiệu ứng dụng

Khi nhận cảnh báo chi phí, so sánh với:

- Request rate, active user và số giao dịch.
- Retry, throttling, timeout, error rate và queue depth.
- Byte upload/download, cache hit ratio và số lần đọc object.
- Storage growth, số object/version và retention.
- Số instance, CPU, memory, autoscaling event và thời gian chạy.
- Release, thay đổi region, job mới và thay đổi cấu hình.

Nếu cost tăng cùng request rate, có thể là tăng trưởng dự kiến. Nếu cost tăng nhưng traffic không đổi, tìm operation hoặc đơn giá hiệu dụng thay đổi. Nếu request tăng cùng retry và lỗi, kiểm tra vòng lặp retry hoặc downstream throttle. Nếu storage tăng cùng version count, xem lại versioning và lifecycle.

## 6. Theo dõi hạn ngạch và chi phí trên AWS

### 6.1. Quota và usage

- Dùng **AWS Service Quotas** để xem quota của dịch vụ, mức sử dụng được hỗ trợ và gửi yêu cầu tăng quota khi phù hợp.
- Kiểm tra phạm vi quota: một số giới hạn áp dụng theo region, một số theo account hoặc dịch vụ; không suy ra tất cả quota có cùng phạm vi.
- Dùng metric và alarm của **Amazon CloudWatch** cho usage, throttling, request rate, queue depth, errors và capacity khi dịch vụ xuất metric tương ứng.
- Với những quota được hỗ trợ, kiểm tra metric usage/quota hoặc tích hợp Service Quotas với CloudWatch để cảnh báo trước khi chạm giới hạn.
- Kiểm tra thêm quota ở các thành phần liên quan như EC2, VPC, load balancer, Lambda concurrency, API Gateway, SQS và database.

Không phải mọi quota đều có metric utilization sẵn. Nếu dịch vụ không cung cấp metric, cần lấy usage qua API, log hoặc báo cáo phù hợp và duy trì kiểm tra định kỳ. Thời điểm cập nhật metric cũng có thể khác nhau.

### 6.2. Budget và anomaly

- Dùng **AWS Budgets** để đặt ngân sách theo account, service, tag hoặc các dimension được hỗ trợ; cấu hình cảnh báo theo actual và forecast.
- Gửi thông báo tới Amazon SNS hoặc kênh vận hành đã được tích hợp để owner nhận và xử lý.
- Dùng **AWS Cost Anomaly Detection** để phát hiện thay đổi chi tiêu bất thường theo monitor và dimension phù hợp.
- Dùng báo cáo chi phí và usage để xác định service, usage type, region và tài nguyên đóng góp vào thay đổi.
- Nếu dùng Budgets Actions, xác định rõ loại hành động được hỗ trợ, scope và quyền IAM; thử nghiệm trong môi trường an toàn trước khi áp dụng.

AWS Budgets và Cost Anomaly Detection có mục đích khác nhau. Budget so sánh chi phí với mục tiêu; anomaly monitor tìm thay đổi bất thường. Budgets Actions có thể tự động thực hiện một số hành động được hỗ trợ, nhưng không tạo ra hard cap phổ quát cho mọi chi phí.

## 7. Theo dõi hạn ngạch và chi phí trên Microsoft Azure

### 7.1. Quota và usage

- Kiểm tra quota theo subscription, region và dịch vụ trong **Azure Quotas** hoặc trang quản lý quota của dịch vụ cụ thể.
- Theo dõi quota của VM vCPU, networking, public IP, storage, AKS và các dịch vụ có giới hạn riêng.
- Dùng **Azure Monitor** để quan sát metric, log, throttling, capacity và tạo alert rule khi dịch vụ phát metric phù hợp.
- Dùng Activity Log và resource diagnostics để liên hệ thay đổi tài nguyên với thời điểm quota hoặc chi phí tăng.
- Kiểm tra quota theo SKU và region; một quota tổng có thể không bảo đảm còn capacity của SKU cụ thể.

Quota và capacity có thể khác nhau: quota cho phép subscription yêu cầu hoặc tạo tới một giới hạn, còn capacity phản ánh khả năng cung cấp tài nguyên ở thời điểm đó. Việc còn quota không đảm bảo mọi SKU hoặc zone đều có tài nguyên sẵn sàng.

### 7.2. Budget và anomaly

- Dùng **Microsoft Cost Management budgets** để đặt ngân sách theo subscription, resource group, service hoặc scope được hỗ trợ.
- Cấu hình cảnh báo actual và forecast, chọn người nhận và chu kỳ ngân sách phù hợp.
- Kết nối cảnh báo với **Azure Monitor Action Groups** hoặc workflow được quản trị khi cần chuyển tiếp tới hệ thống vận hành.
- Dùng Cost Analysis và exports để phân tích service, resource group, tag, region và meter.
- Dùng công cụ phân tích chi phí và khuyến nghị liên quan để tìm resource idle, tăng trưởng hoặc thay đổi bất thường.

Budget alert có thể kích hoạt Action Group khi cấu hình phù hợp, nhưng bản thân budget không tự động ngăn chi phí tiếp tục phát sinh. Nếu tạo automation để dừng hoặc scale resource, cần kiểm tra dependency và bảo đảm không ảnh hưởng dữ liệu production.

## 8. Theo dõi hạn ngạch và chi phí trên Google Cloud

### 8.1. Quota và usage

- Dùng trang **Quotas & System Limits** trong Google Cloud Console để xem giới hạn theo project, service, region hoặc dimension tương ứng.
- Kiểm tra quota metric và usage metric của dịch vụ; một số quota có thể được theo dõi qua **Cloud Monitoring**.
- Tạo alert policy cho mức sử dụng quota, tốc độ request, lỗi RESOURCE_EXHAUSTED, latency và các metric vận hành liên quan.
- Dùng Service Usage API hoặc công cụ quản trị phù hợp khi cần kiểm tra quota có thể tự động hóa.
- Kiểm tra giới hạn theo project và region; tăng quota ở một project không làm tăng quota của project khác.

Google Cloud có cả quota và system limit. Một số system limit không thể tăng theo yêu cầu. Cần đọc mô tả từng quota để biết có thể yêu cầu điều chỉnh, phạm vi áp dụng và thời gian xử lý.

### 8.2. Budget và anomaly

- Dùng **Cloud Billing budgets and alerts** để đặt ngân sách theo billing account và scope như project, service hoặc label được hỗ trợ.
- Cấu hình cảnh báo theo actual cost và forecasted cost; gửi notification tới người phụ trách.
- Có thể dùng thông báo Pub/Sub của budget để nối với workflow xử lý hoặc hệ thống cảnh báo nội bộ.
- Dùng Cloud Billing export sang BigQuery để phân tích chi phí theo SKU, project, service, location, label và thời gian.
- Dùng các tính năng phân tích chi phí và phát hiện bất thường hiện có trong Cloud Billing/FinOps để tìm thay đổi cần điều tra.

Thông báo budget qua Pub/Sub là tín hiệu cho hệ thống khác xử lý; nó không tự dừng tài nguyên. Nếu xây dựng automation, hãy xác thực message, chống xử lý lặp, ghi audit và chỉ thực hiện hành động đã được phê duyệt.

## 9. So sánh cách triển khai giữa các nhà cung cấp

| Mục tiêu | AWS | Microsoft Azure | Google Cloud |
|---|---|---|---|
| Tra quota | AWS Service Quotas | Azure Quotas và trang quota dịch vụ | Quotas & System Limits |
| Theo dõi metric | Amazon CloudWatch | Azure Monitor | Cloud Monitoring |
| Budget | AWS Budgets | Cost Management budgets | Cloud Billing budgets |
| Cảnh báo chi phí bất thường | Cost Anomaly Detection | Cost Analysis và công cụ phân tích chi phí liên quan | Cloud Billing/FinOps anomaly capabilities |
| Xuất dữ liệu billing | Cost and Usage Report / billing data export | Cost Management exports | Cloud Billing export |
| Chuyển cảnh báo sang workflow | SNS, Budgets Actions và tích hợp khác | Action Groups, Logic Apps hoặc workflow khác | Pub/Sub và workflow được xây dựng |

Các sản phẩm có phạm vi và độ trễ khác nhau. Không nên coi tên tính năng tương tự là tương đương hoàn toàn. Trước khi triển khai, kiểm tra dịch vụ có hỗ trợ quota metric, forecast, dimension lọc, export và action cần thiết trong tài khoản/region của mình hay không.

## 10. Thiết kế quy trình xử lý cảnh báo

Một cảnh báo chỉ hữu ích khi người nhận biết phải làm gì. Tạo runbook ngắn cho từng loại cảnh báo, ghi owner, dashboard, lệnh hoặc trang kiểm tra, mức độ ảnh hưởng và hành động được phép.

### 10.1. Khi quota utilization tăng

1. Xác nhận metric, phạm vi quota, đơn vị và cửa sổ thời gian.
2. Xác định workload, region và resource đang tiêu thụ quota.
3. So sánh usage với traffic, autoscaling, release và job nền.
4. Ước lượng headroom và thời gian tới giới hạn ở tải đỉnh.
5. Nếu tăng trưởng hợp lệ, xin tăng quota sớm hoặc điều chỉnh kế hoạch triển khai.
6. Nếu tăng trưởng bất thường, giảm tốc độ producer, concurrency hoặc tài nguyên không thiết yếu.
7. Theo dõi throttling, latency, error rate và xác nhận headroom được phục hồi.

### 10.2. Khi budget hoặc forecast vượt ngưỡng

1. Xác nhận kỳ ngân sách, scope, currency và loại cost đang hiển thị.
2. Xem chi phí theo service, SKU, region, project/resource group và tag.
3. So sánh với request, byte, storage, compute và thay đổi gần nhất.
4. Xác định chi phí cố định, chi phí tăng theo tải và khoản một lần.
5. Thông báo owner; tạm hoãn workload thử nghiệm hoặc job không thiết yếu nếu cần.
6. Đưa ra phương án giảm chi phí kèm tác động tới latency, reliability và dữ liệu.
7. Ghi nhận nguyên nhân, hành động và thay đổi budget nếu kế hoạch đã được phê duyệt.

### 10.3. Khi phát hiện anomaly

1. Kiểm tra anomaly có phải thay đổi thật hay do độ trễ, điều chỉnh hoặc phân loại billing.
2. Tìm service/SKU/region có delta lớn nhất và xác định thời điểm bắt đầu.
3. So sánh với deployment, thay đổi cấu hình, traffic, retry, replication và log volume.
4. Nếu đang phát sinh chi phí nhanh, giới hạn hoặc dừng nguồn tạo tải theo runbook đã duyệt.
5. Bảo toàn log, metric, trace và billing export để điều tra.
6. Xác minh chi phí trở về baseline và thêm cảnh báo hoặc kiểm soát ngăn tái diễn.

## 11. Ví dụ: phát hiện retry làm tăng chi phí và chạm quota

Giả sử một dịch vụ Spring Boot nhận 2.000 request nghiệp vụ mỗi phút. Mỗi request gọi một API inventory. Sau một lần triển khai, downstream bắt đầu trả throttling; client retry tối đa ba lần nhưng không có jitter. Số request tới downstream tăng, latency tăng và log ghi lại nhiều exception.

Trước thay đổi, mỗi phút có khoảng 2.000 lần gọi downstream. Khi mỗi thao tác có trung bình 2,4 attempt, downstream nhận khoảng:

```text
2.000 × 2,4 = 4.800 attempts/phút
```

Nếu quota cho phép 4.000 request/phút trong cửa sổ tương ứng, workload đã vượt mức này dù traffic nghiệp vụ không tăng. Retry tiếp tục làm tăng áp lực và có thể kéo dài sự cố.

Các bước xử lý:

1. Dùng metric `cloud.throttled`, `cloud.requests` và retry count để xác nhận số attempt tăng.
2. Đối chiếu với metric quota/throttling ở nhà cung cấp và kiểm tra quota scope.
3. Giảm retry, thêm exponential backoff với jitter, giới hạn tổng thời gian và áp dụng circuit breaker.
4. Hạ concurrency hoặc tốc độ gọi inventory tạm thời; ưu tiên request quan trọng.
5. Kiểm tra cache hoặc batch để giảm số lần đọc lặp nếu dữ liệu và nghiệp vụ cho phép.
6. Khi tải ổn định, đánh giá có cần xin tăng quota hoặc thay đổi kiến trúc hay không.
7. So sánh số operation, log volume và chi phí sau xử lý với baseline.

Trong ví dụ này, xin tăng quota có thể cần thiết nếu tải hợp lệ đã vượt năng lực được cấp. Tuy nhiên, tăng quota trong lúc retry storm chưa được xử lý có thể chỉ làm sự cố lan rộng hơn. Cần khôi phục hành vi client trước, sau đó mới đánh giá headroom dài hạn.

## 12. Checklist vận hành

- [ ] Có danh mục quota quan trọng theo account/subscription/project, region và service.
- [ ] Mỗi quota có owner, metric nguồn, giới hạn hiện tại và quy trình xin tăng.
- [ ] Có cảnh báo utilization, tốc độ tiêu thụ và throttling phù hợp với thời gian phản ứng.
- [ ] Có metric ở Spring Boot cho request, retry, lỗi quota, latency và byte theo dependency.
- [ ] Có budget tổng và budget theo workload hoặc team quan trọng.
- [ ] Budget theo dõi actual và forecast, với currency, kỳ và scope rõ ràng.
- [ ] Có anomaly detection và quy trình xác nhận thay đổi bất thường.
- [ ] Có billing export hoặc báo cáo usage để phân tích theo service, SKU, region và nhãn.
- [ ] Cảnh báo có người nhận, runbook, mức độ ưu tiên và hành động được phép.
- [ ] Automation có scope giới hạn, audit trail, chống lặp và phương án rollback.
- [ ] Định kỳ diễn tập cảnh báo quota, budget và anomaly để xác nhận đường đi từ phát hiện tới xử lý.

## Kết luận

Quota cho biết workload còn bao nhiêu năng lực trước giới hạn dịch vụ; budget cho biết chi tiêu có đi đúng kế hoạch; anomaly detection giúp tìm thay đổi bất thường trước khi chúng trở thành sự cố tài chính. Kết hợp metric ở Spring Boot với công cụ quota, monitoring và billing của AWS, Azure hoặc Google Cloud để nối hành vi ứng dụng với mức sử dụng và chi phí. Cảnh báo cần có owner và runbook, còn automation phải được giới hạn và kiểm thử để bảo vệ dịch vụ production. Khi theo dõi headroom, forecast và unit cost thường xuyên, nhóm có thể xử lý sớm cả nguy cơ cạn quota lẫn tăng chi phí ngoài dự kiến.
