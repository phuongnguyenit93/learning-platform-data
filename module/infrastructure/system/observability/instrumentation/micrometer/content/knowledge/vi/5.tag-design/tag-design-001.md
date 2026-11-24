# Chọn tag theo câu hỏi cần phân tích và nhóm chịu trách nhiệm

Tag quyết định cách một metric có thể được phân nhóm, lọc và so sánh. Một metric đếm số request có thể trả lời nhiều câu hỏi khác nhau tùy theo tag: request đến từ route nào, dùng HTTP method nào, thành công hay thất bại, hoặc thuộc dịch vụ nào. Nếu chọn tag tùy tiện, dashboard khó trả lời câu hỏi vận hành và số lượng time series có thể tăng nhanh.

Thiết kế tag nên bắt đầu từ câu hỏi mà người vận hành hoặc nhóm sản phẩm cần trả lời. Sau đó xác định chiều phân tích thực sự cần thiết, miền giá trị hợp lệ, nguồn dữ liệu và nhóm chịu trách nhiệm duy trì chiều đó. Cách làm này giúp metric có ý nghĩa ổn định trong suốt vòng đời dịch vụ.

## 1. Tag trả lời câu hỏi phân tích nào?

Trong Micrometer, meter thường được xác định bởi tên, loại meter và tập tag. Cùng một tên metric nhưng khác tổ hợp tag sẽ tạo ra các meter riêng. Khi xuất sang Prometheus, mỗi tổ hợp tên metric và label-value tương ứng với một time series.

Ví dụ, metric **orders.completed** có thể được phân nhóm theo **channel**:

| Metric | Tag | Câu hỏi có thể trả lời |
| --- | --- | --- |
| orders.completed | channel=web | Có bao nhiêu đơn hàng hoàn tất qua web? |
| orders.completed | channel=mobile | Có bao nhiêu đơn hàng hoàn tất qua ứng dụng di động? |
| orders.completed | channel=partner | Kênh đối tác đóng góp bao nhiêu đơn hàng? |

Tag có ích khi nó tạo ra một góc nhìn có hành động tiếp theo. Chẳng hạn, phân biệt channel giúp nhóm sản phẩm so sánh các kênh; phân biệt outcome giúp nhóm vận hành phát hiện lỗi; phân biệt region có thể giúp khoanh vùng sự cố theo khu vực triển khai.

Một tag không có câu hỏi cụ thể thường chỉ làm tăng số chuỗi thời gian và tạo thêm lựa chọn lọc khó hiểu. Trước khi thêm tag, hãy diễn đạt câu hỏi bằng một câu rõ ràng, ví dụ:

- Tỷ lệ checkout thất bại thay đổi ra sao theo kênh bán hàng?
- Độ trễ p95 của API nào đang tăng?
- Hàng đợi nào thường xuyên vượt ngưỡng?
- Lỗi đang tập trung ở dịch vụ hoặc khu vực triển khai nào?
- Nhóm nào chịu trách nhiệm xử lý cảnh báo của metric này?

Nếu không có ai cần phân tích hoặc hành động dựa trên một chiều dữ liệu, hãy cân nhắc giữ chiều đó trong log, trace hoặc metadata catalog thay vì biến nó thành tag metrics.

## 2. Chuyển câu hỏi thành các chiều tag

Một câu hỏi thường chứa một phép đo và một vài chiều phân nhóm. Tách chúng ra trước khi viết code:

| Câu hỏi | Phép đo | Chiều tag có thể cần | Ghi chú thiết kế |
| --- | --- | --- | --- |
| Có bao nhiêu request lỗi theo API? | Số request hoặc tỷ lệ lỗi | route, method, status | Dùng route template và tập status có giới hạn. |
| Checkout thất bại ở kênh nào? | Số checkout hoặc tỷ lệ thất bại | channel, outcome | Dùng enum hoặc danh mục kênh được quản lý. |
| API nào chậm? | Timer của request | route, có thể thêm method | Tránh URL thô có ID hoặc query string. |
| Hàng đợi nào đang bị dồn? | Gauge độ dài hàng đợi | queue hoặc queue_group | Chỉ dùng tên hàng đợi được cấu hình trước. |
| Sự cố thuộc khu vực nào? | Counter lỗi hoặc Timer | region, service | Chỉ dùng mã khu vực và tên service ổn định. |
| Ai nhận cảnh báo? | Không nhất thiết là một phép đo | Metadata owner; tùy nhu cầu có thể thêm team | Không thêm tag team chỉ để lưu danh bạ nếu không cần truy vấn theo team. |

Không cần đưa mọi chiều vào mọi metric. Ví dụ, nếu một metric thanh toán chỉ cần so sánh kết quả theo phương thức thanh toán, channel và outcome có thể đủ. Thêm region, service, host, version, customer và các chiều khác chỉ vì chúng có sẵn sẽ làm metric khó quản lý.

Một nguyên tắc hữu ích là chọn số chiều nhỏ nhất vẫn trả lời được câu hỏi vận hành. Nếu một chiều chỉ có ý nghĩa với một metric cụ thể, hãy giới hạn nó ở metric đó thay vì biến thành tag chung toàn ứng dụng.

## 3. Chọn miền giá trị có giới hạn

Tag an toàn cho metrics thường có tập giá trị nhỏ, ổn định và có thể liệt kê. Đây là thuộc tính quan trọng để kiểm soát cardinality.

Ví dụ miền giá trị tốt:

- method: GET, POST, PUT, DELETE.
- outcome: success, failure, timeout.
- channel: web, mobile, partner.
- region: ap-southeast-1, ap-northeast-1, nếu đó là danh sách khu vực triển khai được quản lý.
- payment_method: card, bank_transfer, wallet.
- status: nhóm mã HTTP hoặc mã trạng thái đã được chuẩn hóa.

Ví dụ giá trị rủi ro cao:

- user_id, customer_id, order_id, request_id hoặc session_id.
- Email, số điện thoại, địa chỉ, token hoặc nội dung tìm kiếm.
- URL đầy đủ có UUID, slug động, query string hoặc mã tài nguyên.
- Exception message, SQL statement hoặc chuỗi lỗi tự do.
- Tên pod/container hoặc hostname thay đổi liên tục khi autoscaling, nếu câu hỏi phân tích không cần đến từng instance.

Với HTTP route, hãy dùng mẫu route như **/orders/{id}** hoặc tên operation ổn định thay vì **/orders/829471**. Với lỗi, hãy dùng nhóm lỗi hoặc mã lỗi đã chuẩn hóa thay vì message chứa dữ liệu biến thiên.

Nếu cần điều tra một request hoặc một đơn hàng cụ thể, log và trace phù hợp hơn metrics. Metrics giúp tổng hợp và so sánh ở quy mô lớn; log/trace có thể giữ định danh chi tiết theo chính sách lưu trữ và quyền truy cập phù hợp.

## 4. Ước lượng cardinality trước khi thêm tag

Cardinality là số lượng tổ hợp label-value tạo thành time series cho một metric. Nếu một metric có các chiều tag với số giá trị khác nhau, số tổ hợp tối đa có thể tăng theo tích của số giá trị từng chiều.

Ví dụ metric request có:

- 5 HTTP method;
- 8 nhóm status;
- 40 route template;
- 3 region.

Số tổ hợp lý thuyết tối đa là:

\[
5 \times 8 \times 40 \times 3 = 4{,}800
\]

Đây là mức trần theo tích các miền giá trị; số chuỗi thực tế còn phụ thuộc những tổ hợp nào xuất hiện. Nếu thêm user_id với 100.000 giá trị, mức trần có thể tăng lên hàng trăm triệu tổ hợp. Nhiều metric cùng mang những chiều đó sẽ làm chi phí bộ nhớ, lưu trữ, scrape và truy vấn tăng đáng kể.

Khi ước lượng cardinality, cần tính cả:

1. Số giá trị hợp lệ của từng tag.
2. Số tổ hợp có thể xuất hiện trong thực tế.
3. Số metric dùng chung các tag đó.
4. Số instance hoặc target đang scrape.
5. Các bucket histogram nếu metric là Timer hoặc DistributionSummary được xuất dưới dạng histogram.

Histogram tạo thêm chuỗi cho các bucket, vì vậy một Timer có histogram có thể tốn nhiều series hơn một counter đơn giản. Khi đánh giá ngân sách cardinality, đừng chỉ đếm số meter trong code.

Không có một ngưỡng cardinality chung phù hợp cho mọi hệ thống. Hãy thống nhất ngân sách với nhóm vận hành dựa trên năng lực Prometheus hoặc backend đang dùng, tần suất scrape, số target, retention và khối lượng truy vấn. Khi một tag có thể tăng không giới hạn theo thời gian, cần loại bỏ hoặc thay bằng nhóm giá trị đã chuẩn hóa.

## 5. Gắn trách nhiệm sở hữu cho từng tag

Tag phản ánh khái niệm của một miền nghiệp vụ hoặc một phần hạ tầng. Nếu không có nhóm chịu trách nhiệm, định nghĩa tag dễ bị thay đổi tùy tiện: cùng một ý nghĩa nhưng nhiều tên, cùng một tag nhưng nhiều cách viết, hoặc một giá trị mới được thêm mà không đánh giá cardinality.

Nên xác định owner theo nguồn sự thật của chiều dữ liệu:

| Loại tag | Nhóm chịu trách nhiệm chính | Trách nhiệm |
| --- | --- | --- |
| route, method, status | Nhóm sở hữu service/API | Duy trì route template, quy ước method và cách nhóm status. |
| channel, payment_method, outcome | Nhóm nghiệp vụ sở hữu quy trình | Định nghĩa ý nghĩa nghiệp vụ và danh mục giá trị hợp lệ. |
| region, cluster, environment | Platform/SRE hoặc nhóm hạ tầng | Chuẩn hóa mã môi trường và khu vực triển khai. |
| queue, consumer_group | Nhóm sở hữu pipeline hoặc dịch vụ xử lý nền | Quản lý tên hàng đợi, consumer group và vòng đời cấu hình. |
| team hoặc owner_team | Nhóm quản trị service catalog/observability | Duy trì ánh xạ service với nhóm chịu trách nhiệm. |

Owner có trách nhiệm quyết định ngữ nghĩa và miền giá trị; nhóm triển khai instrumentation có trách nhiệm dùng đúng hợp đồng tag; nhóm platform/observability có trách nhiệm đặt quy tắc cardinality, kiểm tra và hướng dẫn dùng chung.

### Owner có nhất thiết phải là tag không?

Không phải lúc nào cũng vậy. Nếu mục đích chỉ là biết ai bảo trì một service, trường owner trong service catalog hoặc metadata của alert thường phù hợp hơn. Khi đó, thay đổi cơ cấu nhóm không làm phát sinh một loạt time series mới.

Chỉ thêm team làm tag khi người vận hành thực sự cần lọc, nhóm hoặc so sánh metrics theo team và danh sách team có giới hạn. Giá trị phải lấy từ danh mục chính thức, không lấy từ chuỗi tự do trong cấu hình tùy ý. Cần cân nhắc rằng đổi owner có thể làm thay đổi label set và tạo series mới.

## 6. Tạo hợp đồng tag trước khi viết instrumentation

Một tag contract ngắn nên có các trường:

| Trường | Ý nghĩa |
| --- | --- |
| Metric | Tên meter áp dụng tag. |
| Tag key | Tên chiều phân tích, thống nhất cách đặt tên. |
| Câu hỏi | Lý do cần chiều dữ liệu này. |
| Owner | Nhóm quyết định ngữ nghĩa và miền giá trị. |
| Source | Nơi lấy giá trị, ví dụ enum nghiệp vụ, route template hoặc cấu hình triển khai. |
| Allowed values | Danh sách hoặc quy tắc giới hạn giá trị. |
| Cardinality estimate | Số giá trị dự kiến và tác động lên số series. |
| Data classification | Xác nhận không chứa dữ liệu cá nhân, bí mật hoặc định danh nhạy cảm. |
| Change policy | Cách thêm, đổi tên hoặc loại bỏ giá trị. |

Ví dụ hợp đồng cho metric checkout:

| Thuộc tính | Giá trị |
| --- | --- |
| Metric | checkout.completed |
| Câu hỏi | Kênh nào có số checkout hoàn tất giảm bất thường? |
| Owner metric | Nhóm Checkout |
| Tag channel | web, mobile, partner |
| Owner tag channel | Nhóm Product/Checkout |
| Tag outcome | success, failure |
| Owner tag outcome | Nhóm Checkout |
| Cardinality dự kiến | 3 × 2 = 6 tổ hợp cho mỗi service/instance label khác |
| Nguồn | Enum và mapping trong mã nghiệp vụ |
| Dữ liệu nhạy cảm | Không chứa user ID hoặc order ID |

Hợp đồng này giúp reviewer xác định một tag mới có thực sự cần thiết, ai có quyền thay đổi danh mục và tác động của thay đổi lên backend metrics.

## 7. Chuẩn hóa tên tag và giá trị

Tag cần có tên và cách biểu diễn nhất quán trên các service. Một số quy tắc thực tế:

- Dùng tên ngắn, mô tả đúng ý nghĩa và thống nhất cách viết, ví dụ payment_method thay vì service này dùng payType, service khác dùng paymentType.
- Chọn một kiểu chữ cho value, ví dụ web, mobile, partner; tránh lúc dùng WEB, lúc dùng Web.
- Dùng mã chuẩn cho region, environment hoặc status thay vì tên hiển thị có thể đổi theo ngôn ngữ.
- Chuẩn hóa giá trị chưa xác định thành một giá trị hữu hạn như unknown khi điều đó có ý nghĩa; không tạo value mới từ nội dung đầu vào.
- Không đưa chuỗi rỗng, null được chuyển thành chuỗi hoặc giá trị lỗi thô vào tag.
- Giữ ổn định ngữ nghĩa tag; nếu ý nghĩa thay đổi, xem xét tên metric hoặc key mới và lập kế hoạch chuyển đổi.

Không nên tạo tag chung chỉ vì các service có cùng tên trường. Ví dụ type quá mơ hồ; payment_method, queue_type hoặc request_outcome giúp người đọc hiểu rõ miền dữ liệu hơn.

## 8. Ví dụ triển khai tag có kiểm soát trong Micrometer

Giả sử nhóm Checkout cần trả lời câu hỏi: số checkout hoàn tất và thất bại thay đổi ra sao theo kênh? Hãy ánh xạ dữ liệu đầu vào về enum có tập giá trị hữu hạn trước khi đăng ký meter.

~~~java
public enum CheckoutChannel {
    WEB("web"),
    MOBILE("mobile"),
    PARTNER("partner");

    private final String tagValue;

    CheckoutChannel(String tagValue) {
        this.tagValue = tagValue;
    }

    public String tagValue() {
        return tagValue;
    }
}
~~~

Meter có thể được đăng ký như sau:

~~~java
import java.util.Collections;
import java.util.EnumMap;
import java.util.Map;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {

    private final Map<CheckoutChannel, Counter> completedByChannel;

    public CheckoutMetrics(MeterRegistry registry) {
        Map<CheckoutChannel, Counter> counters = new EnumMap<>(CheckoutChannel.class);
        for (CheckoutChannel channel : CheckoutChannel.values()) {
            Counter counter = Counter.builder("checkout.completed")
                    .description("Number of completed checkouts")
                    .tag("channel", channel.tagValue())
                    .register(registry);
            counters.put(channel, counter);
        }
        this.completedByChannel = Collections.unmodifiableMap(counters);
    }

    public void recordCompleted(CheckoutChannel channel) {
        completedByChannel.get(channel).increment();
    }
}
~~~

Ví dụ đăng ký trước một Counter cho mỗi giá trị enum và giữ chúng trong EnumMap. Khi xử lý checkout, mã chỉ tra cứu meter đã tạo rồi tăng counter. Số meter được giới hạn bởi ba giá trị của CheckoutChannel; tên/tag không phụ thuộc dữ liệu tự do từ request.

Nếu cần phân biệt kết quả, có thể thêm outcome với miền giá trị cố định. Chỉ thêm chiều này nếu dashboard hoặc alert thực sự cần phân tích riêng success và failure.

## 9. Áp dụng giới hạn ở tầng registry

Hợp đồng tag và mapping trong mã là lớp kiểm soát đầu tiên. Có thể bổ sung MeterFilter như một lớp bảo vệ để từ chối meter khi một tag vượt quá số lượng giá trị cho phép.

Ví dụ cấu hình Spring:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> metricsFilter() {
        return registry -> registry.config().meterFilter(
                MeterFilter.maximumAllowableTags(
                        "checkout.completed",
                        "channel",
                        3,
                        MeterFilter.deny()
                )
        );
    }
}
~~~

Ví dụ dùng MeterRegistryCustomizer của Spring Boot Actuator để cài filter vào registry. Filter trên giới hạn số giá trị channel cho meter có tên bắt đầu bằng checkout.completed. Nếu vượt giới hạn, filter cuối cùng từ chối meter mới.

Giới hạn filter là hàng rào bảo vệ, không thay thế thiết kế tag. Nếu filter từ chối một meter, dữ liệu của tổ hợp đó sẽ không được ghi nhận như mong muốn; vì vậy cần theo dõi log/diagnostic và xử lý nguồn tạo value bất thường. Hãy chọn ngưỡng theo hợp đồng tag và kiểm tra hành vi của filter với phiên bản Micrometer đang dùng.

## 10. Review thay đổi tag như một thay đổi hợp đồng

Thêm, đổi tên hoặc xóa tag làm thay đổi chuỗi thời gian và có thể ảnh hưởng dashboard, alert, recording rule và truy vấn của nhóm khác. Trước khi merge thay đổi instrumentation, reviewer nên xác minh:

1. Câu hỏi phân tích cụ thể mà tag mới giải quyết là gì?
2. Tag có tập giá trị hữu hạn và có nguồn dữ liệu đáng tin cậy không?
3. Nhóm nào sở hữu ý nghĩa và miền giá trị?
4. Cardinality ước lượng là bao nhiêu trên mỗi metric, target và histogram?
5. Có nguy cơ chứa định danh cá nhân, bí mật hoặc dữ liệu tự do không?
6. Dashboard, alert và truy vấn hiện có cần cập nhật không?
7. Nếu giá trị hoặc ngữ nghĩa thay đổi, cách chuyển đổi và thời điểm loại bỏ tag cũ là gì?

Đối với tag dùng chung như service, environment hoặc region, nhóm platform/observability nên công bố quy ước và kiểm tra tự động để các service không tự tạo biến thể. Với tag nghiệp vụ, nhóm domain owner cần phê duyệt danh mục và ngữ nghĩa.

Không nên đổi cách viết hoặc ý nghĩa của tag một cách âm thầm. Nếu cần đổi channel từ web/mobile sang một danh mục khác, cần xác định ảnh hưởng đến biểu đồ lịch sử và truy vấn so sánh trước/sau. Label set mới thường được backend xem là series mới; dữ liệu lịch sử của series cũ không tự động chuyển sang series mới.

## 11. Các mẫu thiết kế nên tránh

| Mẫu không nên dùng | Vấn đề | Cách thay thế |
| --- | --- | --- |
| user_id hoặc order_id làm tag | Cardinality gần như tăng theo số thực thể. | Dùng log/trace để tra cứu định danh; metrics chỉ giữ nhóm tổng hợp. |
| URL đầy đủ làm tag | Mỗi ID hoặc query string tạo value mới. | Dùng route template hoặc operation name. |
| Exception message làm tag | Nội dung lỗi tự do và có thể chứa dữ liệu nhạy cảm. | Chuẩn hóa thành error_type hoặc error_code hữu hạn. |
| Tên pod làm tag cho mọi metric | Pod thay đổi khi rollout/autoscaling, tạo series churn. | Chỉ dùng instance-level label khi câu hỏi cần chẩn đoán từng instance; nếu không, nhóm theo service/cluster. |
| team tự do nhập trong cấu hình | Nhiều cách viết cho cùng nhóm, thay đổi theo tổ chức. | Dùng service catalog làm nguồn owner; chỉ phát tag khi có nhu cầu truy vấn và dùng danh mục chính thức. |
| Thêm mọi tag chung vào mọi meter | Tăng số chiều và làm dashboard khó hiểu. | Áp dụng tag theo từng câu hỏi và metric cụ thể. |
| Dùng cùng key type cho nhiều ý nghĩa | Người đọc không biết miền dữ liệu đang biểu diễn gì. | Đặt key cụ thể như payment_method, queue_type. |

## 12. Quy trình thực tế để chọn tag

Một quy trình ngắn có thể áp dụng trong code review:

1. **Viết câu hỏi:** nêu điều người dùng dashboard hoặc người trực vận hành cần biết.
2. **Chọn phép đo:** xác định Counter, Gauge, Timer hay DistributionSummary phù hợp.
3. **Chọn chiều phân tích:** chỉ giữ các tag thực sự cần để trả lời câu hỏi.
4. **Định nghĩa miền giá trị:** liệt kê enum, route template hoặc danh mục cấu hình có giới hạn.
5. **Gán owner:** xác định nhóm sở hữu ngữ nghĩa, nguồn dữ liệu và thay đổi danh mục.
6. **Ước lượng cardinality:** tính số tổ hợp và tính thêm target, metric, histogram.
7. **Kiểm tra dữ liệu nhạy cảm:** loại định danh cá nhân, bí mật và chuỗi tự do.
8. **Triển khai và quan sát:** thêm meter, kiểm tra series được tạo và theo dõi tác động lên backend.
9. **Quản lý thay đổi:** cập nhật dashboard, alert, catalog và tài liệu khi hợp đồng tag đổi.

Thiết kế tag tốt giúp metrics trả lời câu hỏi vận hành một cách nhất quán, đồng thời giữ số lượng time series trong giới hạn mà hệ thống giám sát có thể phục vụ. Mỗi chiều dữ liệu cần có lý do sử dụng, miền giá trị rõ ràng và nhóm chịu trách nhiệm duy trì.
