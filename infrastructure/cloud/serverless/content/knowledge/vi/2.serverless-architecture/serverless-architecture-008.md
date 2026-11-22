# Đánh giá độ phức tạp, vendor lock-in và khả năng chuyển nền tảng

Trong chương **Thiết kế kiến trúc serverless**, việc chọn FaaS không chỉ là chọn nơi chạy một Java function. Một ứng dụng có thể dùng nhiều trigger, hàng đợi, event bus, cơ sở dữ liệu, dịch vụ định danh và công cụ quan sát của cloud. Những lựa chọn này ảnh hưởng đến độ phức tạp khi vận hành, mức phụ thuộc vào nhà cung cấp và công sức cần thiết nếu muốn chuyển sang nền tảng khác.

Bài học này cung cấp cách đánh giá ba vấn đề đó trước khi quyết định kiến trúc. Mục tiêu không phải loại bỏ mọi phụ thuộc vào cloud. Mục tiêu là hiểu rõ giá trị mà dịch vụ được quản lý mang lại, nhận diện chi phí rời bỏ và chọn mức độ linh hoạt phù hợp với vòng đời của hệ thống.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân tích những nguồn tạo ra độ phức tạp trong một kiến trúc serverless.
- Nhận diện vendor lock-in ở mã nguồn, runtime, event, dữ liệu, bảo mật, vận hành và chi phí.
- Phân biệt khả năng chuyển mã nguồn với khả năng chuyển toàn bộ hệ thống.
- Chọn ranh giới trừu tượng hóa phù hợp cho ứng dụng Java.
- Lập bảng đánh giá rủi ro và xây dựng lộ trình chuyển nền tảng có kiểm soát.

## 1. Ba câu hỏi cần đánh giá riêng

Độ phức tạp, vendor lock-in và khả năng chuyển nền tảng có liên quan, nhưng không phải cùng một khái niệm.

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| Độ phức tạp kiến trúc | Cần bao nhiêu thành phần, quy tắc và công sức để phát triển, kiểm thử, vận hành hệ thống? | Một luồng đơn hàng đi qua API gateway, queue, nhiều function, workflow và database |
| Vendor lock-in | Những phần nào của hệ thống phụ thuộc vào API, dịch vụ, định dạng hoặc cách vận hành riêng của nhà cung cấp? | Function gọi trực tiếp SDK của dịch vụ database hoặc workflow độc quyền |
| Khả năng chuyển nền tảng | Có thể chuyển workload sang cloud khác hoặc môi trường khác với mức thay đổi và gián đoạn nào? | Chuyển function Java cùng queue, dữ liệu, quyền, dashboard và quy trình triển khai |

Một kiến trúc có thể có độ phức tạp thấp nhưng lock-in cao: một function nhỏ gọi trực tiếp một API độc quyền. Ngược lại, một hệ thống dùng chuẩn mở vẫn có thể rất phức tạp vì có nhiều bước bất đồng bộ và nhiều trạng thái phân tán.

Cũng cần phân biệt hai mục tiêu:

- **Portability của mã:** mã nguồn hoặc artifact có thể biên dịch và chạy trên runtime khác.
- **Portability của workload:** cả luồng xử lý, dữ liệu, bảo mật, triển khai, giám sát, khôi phục và vận hành có thể chuyển sang môi trường khác.

Việc Java function biên dịch được trên hai nền tảng chưa chứng minh workload đã portable. Trigger, IAM, queue, database, retry policy, secret và cảnh báo vẫn có thể phải thiết kế lại.

## 2. Độ phức tạp của kiến trúc serverless đến từ đâu?

Serverless giảm công việc quản lý máy chủ, nhưng hệ thống vẫn phải xử lý các vấn đề của ứng dụng phân tán. Khi chức năng được chia thành nhiều function và dịch vụ quản lý, một thao tác nghiệp vụ có thể đi qua nhiều ranh giới mạng và nhiều cơ chế giao nhận.

### 2.1. Độ phức tạp của luồng nghiệp vụ

Mỗi trigger tạo ra một cách vào hệ thống khác nhau. HTTP thường cần trả response theo thời hạn của client; message có thể được giao lại; event có thể đến trễ hoặc không theo thứ tự mong muốn. Khi một quy trình có nhiều bước, đội phát triển phải xác định bước nào chạy trước, trạng thái được lưu ở đâu và lỗi ở giữa quy trình được khôi phục như thế nào.

Một function càng nhỏ không đồng nghĩa toàn hệ thống càng đơn giản. Chia một quy trình thành nhiều function có thể làm rõ trách nhiệm từng bước, nhưng cũng tạo thêm hợp đồng giữa các bước, cấu hình trigger, quyền gọi và điểm cần quan sát.

### 2.2. Độ phức tạp của trạng thái và tính nhất quán

Function thường không giữ trạng thái lâu dài trong bộ nhớ. Trạng thái nghiệp vụ phải nằm ở database, object storage hoặc một dịch vụ lưu trữ phù hợp. Nhiều function có thể cùng đọc và ghi dữ liệu, vì vậy cần xem xét:

- Giao dịch có thể bao phủ những thao tác nào?
- Dữ liệu có nhất quán ngay lập tức hay nhất quán sau một khoảng thời gian?
- Hai invocation đồng thời có thể cập nhật cùng một bản ghi không?
- Nếu quy trình dừng giữa chừng, trạng thái nào cho biết bước đã hoàn tất?
- Có thể phát lại event mà không tạo tác dụng phụ trùng lặp không?

Khi một giao dịch nghiệp vụ trải qua nhiều dịch vụ độc lập, không thể mặc định có một transaction ACID bao trùm tất cả. Có thể cần state machine, saga, outbox hoặc cơ chế bù trừ nghiệp vụ.

### 2.3. Độ phức tạp của lỗi và retry

Lỗi mạng, timeout, throttling và lỗi tạm thời từ dịch vụ phụ thuộc có thể khiến cùng một công việc được thử lại. Đội phát triển cần hiểu ngữ nghĩa giao nhận của từng nguồn event, thời hạn visibility hoặc acknowledgment, số lần retry, DLQ và cách phát lại message.

Retry không được thiết kế đúng có thể làm tăng tải khi hệ thống đang quá tải, hoặc lặp lại thao tác thanh toán và gửi thông báo. Do đó, idempotency và giới hạn retry là một phần của kiến trúc, không chỉ là chi tiết triển khai trong handler.

### 2.4. Độ phức tạp của kiểm thử và quan sát

Một function có thể chạy tốt trong unit test nhưng thất bại khi tích hợp với IAM, event source, mạng riêng hoặc database thật. Local emulator không phải lúc nào cũng mô phỏng đầy đủ hành vi dịch vụ cloud.

Khi một request đi qua nhiều function, log riêng lẻ khó thể hiện toàn bộ hành trình. Cần mã tương quan, distributed tracing, metric nghiệp vụ và dashboard cho hàng đợi, độ trễ, tỷ lệ lỗi, retry, throttling và chi phí.

### 2.5. Độ phức tạp của bảo mật và vận hành

Mỗi function có thể có danh tính và quyền khác nhau. Số lượng function tăng có thể làm số policy, secret, cấu hình mạng, cảnh báo và quy trình triển khai tăng theo. Nếu các quyền được sao chép rộng rãi hoặc cấu hình bằng tay, việc kiểm tra và kiểm soát thay đổi sẽ khó hơn.

Nhà cung cấp quản lý hạ tầng không có nghĩa đội phát triển không cần vận hành. Đội vẫn cần theo dõi quota, giới hạn concurrency, runtime hết hỗ trợ, backup, khôi phục và sự cố ở các dịch vụ phụ thuộc.

## 3. Vendor lock-in xuất hiện ở những lớp nào?

Vendor lock-in là mức độ khó khăn, chi phí hoặc rủi ro khi thay thế một nhà cung cấp. Nó không chỉ nằm trong mã nguồn gọi SDK. Một workload serverless có thể phụ thuộc vào nhà cung cấp ở nhiều lớp:

| Lớp phụ thuộc | Biểu hiện thường gặp | Tác động khi chuyển |
|---|---|---|
| API và runtime | Handler signature, context object, extension hoặc SDK riêng | Phải sửa adapter, cấu hình build và cách khởi chạy |
| Trigger và event | Event envelope, filter, retry, acknowledgment, ordering hoặc batch behavior riêng | Phải chuyển đổi schema và kiểm thử lại ngữ nghĩa giao nhận |
| Dịch vụ backend | Database, queue, workflow, object storage hoặc API quản lý độc quyền | Phải thay dịch vụ, chuyển dữ liệu và viết lại tích hợp |
| Dữ liệu | Định dạng, index, query, transaction, partition key hoặc tính năng riêng | Có thể phải biến đổi schema, dữ liệu và cách truy vấn |
| IAM và bảo mật | Policy, role, service identity, secret manager, key management và network policy riêng | Phải ánh xạ lại danh tính, quyền, khóa và kết nối |
| Quan sát | Log format, metric, tracing, alert và dashboard gắn với sản phẩm | Phải tái tạo khả năng quan sát và quy trình ứng phó |
| Triển khai và cấu hình | Template, resource definition, pipeline hoặc deployment command riêng | Phải chuyển IaC, pipeline, phân quyền và quy trình release |
| Vận hành và thương mại | Quota, SLA, support plan, region, giá và điều khoản hợp đồng | Phải đánh giá lại năng lực, chi phí, cam kết và quy trình vận hành |

Mức lock-in không giống nhau ở mọi lớp. Một API HTTP theo OpenAPI có thể dễ thay thế hơn một workflow gắn chặt với state machine độc quyền. Một object storage có giao thức tương tự S3 vẫn có thể khác về IAM, consistency, lifecycle, event notification và cách tính phí. Tương thích một API không đồng nghĩa tương đương toàn bộ hành vi dịch vụ.

### Lock-in không phải lúc nào cũng xấu

Dịch vụ cloud chuyên biệt có thể giúp đội phát triển rút ngắn thời gian xây dựng, giảm công sức vận hành và tận dụng năng lực mà tự triển khai sẽ tốn kém. Chọn một database được quản lý hoặc workflow service có thể là quyết định hợp lý nếu giá trị đó lớn hơn chi phí phụ thuộc.

Rủi ro xuất hiện khi tổ chức không biết mình đang phụ thuộc ở đâu, không có dữ liệu hoặc hợp đồng có thể xuất ra, hoặc không thể ước lượng công sức rời nền tảng. Một quyết định lock-in có chủ đích có thể chấp nhận được; một quyết định lock-in vô tình thường gây bất ngờ khi cần mở rộng, thay đổi chi phí hoặc đáp ứng yêu cầu pháp lý.

## 4. Các mức độ portability

Không cần đặt mục tiêu chuyển mọi thành phần trong mọi dự án. Hãy xác định mức portability mà hệ thống thực sự cần.

| Mức | Phạm vi có thể chuyển | Điều cần chứng minh |
|---|---|---|
| 1. Mã nguồn | Logic nghiệp vụ và thư viện dùng chung | Có thể build và kiểm thử độc lập với SDK của cloud |
| 2. Runtime và package | Artifact hoặc container có thể chạy trên runtime mục tiêu | Runtime, kiến trúc CPU, biến môi trường, filesystem và giới hạn tài nguyên tương thích |
| 3. Hợp đồng tích hợp | HTTP API, message schema và event contract | Payload, versioning, acknowledgment, retry và ordering đã được mô tả và kiểm thử |
| 4. Dữ liệu | Database, object và lịch sử nghiệp vụ | Có cách export/import, chuyển đổi schema, kiểm tra tính toàn vẹn và đồng bộ thay đổi |
| 5. Vận hành | IAM, secret, log, metric, tracing, alert, backup và deployment | Có cấu hình tương đương và runbook để đội vận hành làm việc trên môi trường mới |
| 6. Workload hoàn chỉnh | Toàn bộ luồng nghiệp vụ và các phụ thuộc | Có thể cutover, kiểm chứng kết quả, khôi phục hoặc rollback trong giới hạn đã thống nhất |

Portability càng cao thường đòi hỏi nhiều công sức thiết kế, kiểm thử và duy trì lớp tương thích. Nếu tổ chức chỉ cần có phương án khôi phục ở một region khác cùng nhà cung cấp, mục tiêu đó khác với việc chuyển toàn bộ hệ thống sang một cloud khác. Hãy ghi rõ phạm vi, thời gian gián đoạn cho phép và mức mất dữ liệu chấp nhận được.

## 5. Thiết kế Java để giảm phụ thuộc không cần thiết

Một cách thực tế là tách **logic nghiệp vụ** khỏi **adapter của nền tảng**. Logic nghiệp vụ nhận dữ liệu theo mô hình của ứng dụng và gọi các interface do ứng dụng định nghĩa. Adapter chuyển event của cloud thành mô hình nội bộ, gọi logic nghiệp vụ và ánh xạ kết quả về cơ chế acknowledgment hoặc response của trigger.

Sơ đồ khái quát:

~~~mermaid
flowchart LR
    A["HTTP / Queue / Event"] --> B["Adapter của cloud"]
    B --> C["Mô hình event nội bộ"]
    C --> D["Java application service"]
    D --> E["Các interface do ứng dụng định nghĩa"]
    E --> F["Adapter database / payment / storage"]
    F --> G["Dịch vụ cloud được chọn"]
~~~

Ví dụ, service nghiệp vụ không cần biết event đến từ queue nào hoặc database thuộc nhà cung cấp nào:

~~~java
public record OrderCreated(
        String orderId,
        long amountCents,
        String currency) {
}

public interface OrderStore {
    boolean tryClaim(String orderId);
    void markPaid(String orderId, String paymentReference);
}

public interface PaymentPort {
    PaymentResult charge(
            String idempotencyKey,
            long amountCents,
            String currency);
}

public record PaymentResult(
        boolean successful,
        String reference) {
}

public final class ProcessOrder {
    private final OrderStore orders;
    private final PaymentPort payments;

    public ProcessOrder(OrderStore orders, PaymentPort payments) {
        this.orders = orders;
        this.payments = payments;
    }

    public void handle(OrderCreated event) {
        if (!orders.tryClaim(event.orderId())) {
            return; // Đã được xử lý hoặc đang được xử lý theo chính sách lưu trữ.
        }

        PaymentResult result = payments.charge(
                event.orderId(),
                event.amountCents(),
                event.currency());

        if (result.successful()) {
            orders.markPaid(event.orderId(), result.reference());
        }
    }
}
~~~

Đây là ví dụ minh họa ranh giới phụ thuộc, không phải một triển khai thanh toán hoàn chỉnh. Trong hệ thống thực, tryClaim cần được thực hiện nguyên tử và có quy tắc lease hoặc trạng thái lỗi phù hợp. PaymentPort phải truyền idempotency key đến nhà cung cấp thanh toán nếu dịch vụ đó hỗ trợ. Cũng cần xử lý trường hợp thanh toán thành công nhưng function dừng trước khi lưu kết quả; chỉ có interface không tự tạo ra bảo đảm exactly-once.

Adapter riêng của cloud chịu trách nhiệm:

- Giải mã event envelope của trigger thành OrderCreated.
- Kiểm tra dữ liệu, phiên bản schema và trường bắt buộc.
- Chuyển lỗi nghiệp vụ hoặc lỗi hạ tầng thành response, retry hoặc acknowledgment phù hợp với nguồn event.
- Cấu hình IAM, timeout, concurrency, network và các giới hạn của function.
- Ghi log, trace và metric theo quy ước chung của ứng dụng.

Khi chuyển nền tảng, có thể thay adapter và các thành phần phụ thuộc trước, trong khi giữ lại phần lớn logic nghiệp vụ. Tuy nhiên, nếu semantics của queue, transaction hoặc database khác nhau, adapter mới vẫn cần kiểm thử tích hợp và có thể cần thay đổi thiết kế.

### Dùng chuẩn mở ở ranh giới có ích

Một số chuẩn và giao thức có thể giảm phụ thuộc khi dùng đúng chỗ:

- **HTTP và OpenAPI:** mô tả hợp đồng API đồng bộ, giúp client và service tích hợp theo một đặc tả rõ ràng.
- **CloudEvents:** cung cấp cấu trúc chung cho metadata của event, hỗ trợ chuẩn hóa event envelope giữa các hệ thống.
- **AsyncAPI:** mô tả API bất đồng bộ, channel, message và cách các thành phần trao đổi event.
- **OCI container image:** chuẩn hóa cách đóng gói ứng dụng trong container, hữu ích khi nền tảng đích hỗ trợ chạy container.
- **OpenTelemetry:** chuẩn hóa cách phát telemetry cho traces, metrics và logs ở nhiều hệ thống quan sát.

Chuẩn hóa payload không tự chuẩn hóa semantics. Hai queue đều nhận JSON vẫn có thể khác về thứ tự message, thời gian lưu, visibility timeout, batch, retry và dead-letter behavior. Hai nền tảng đều chạy container vẫn có thể khác về networking, identity, autoscaling và chi phí.

### Tránh tạo một lớp trừu tượng quá rộng

Không nên xây một interface chung chỉ để che mọi khác biệt giữa các cloud nếu ứng dụng không có nhu cầu chuyển đổi thực tế. Interface quá tổng quát có thể làm mất tính năng hữu ích, tạo nhiều cấu hình và khiến việc debug khó hơn.

Hãy trừu tượng hóa tại ranh giới có khả năng thay đổi hoặc cần kiểm thử độc lập, chẳng hạn cổng thanh toán, kho dữ liệu hoặc bộ phát event. Với tính năng cloud đặc thù mang lại lợi ích rõ ràng, có thể dùng trực tiếp nhưng ghi nhận vị trí phụ thuộc, lý do chọn và phương án thay thế.

## 6. Các chiến lược kiến trúc và trade-off

| Chiến lược | Cách làm | Lợi ích | Chi phí hoặc giới hạn |
|---|---|---|---|
| Cloud-native | Dùng sâu các dịch vụ được quản lý của một nhà cung cấp | Phát triển nhanh, ít phải tự vận hành một số năng lực | Lock-in cao hơn; chuyển dịch vụ và dữ liệu có thể tốn kém |
| Portable core | Giữ logic nghiệp vụ độc lập, dùng adapter cho trigger và dịch vụ ngoài | Dễ kiểm thử và thay một số tích hợp | Cần duy trì interface, adapter và kiểm thử tương thích |
| Container-first | Đóng gói workload trong OCI image khi nền tảng đích hỗ trợ | Tăng lựa chọn runtime và nơi triển khai | Vẫn phụ thuộc nền tảng điều phối, IAM, mạng, storage và autoscaling |
| Multi-cloud ngay từ đầu | Thiết kế và vận hành trên nhiều cloud song song | Giảm phụ thuộc vào một nền tảng trong một số tình huống | Tăng mạnh chi phí kỹ thuật, kiểm thử, bảo mật và vận hành |
| Exit-ready | Chọn một cloud chính nhưng chuẩn bị dữ liệu, hợp đồng, IaC và runbook để rời đi | Giữ khả năng thương lượng và giảm bất ngờ khi cần chuyển | Cần đầu tư định kỳ vào tài liệu, diễn tập và kiểm tra khả năng export |

**Multi-cloud không tự động giảm tổng rủi ro.** Nó có thể tạo thêm nhiều bản sao cấu hình, đường truyền, danh tính, quy trình release và khác biệt dịch vụ. Chỉ nên vận hành nhiều cloud khi có yêu cầu rõ ràng như phân vùng rủi ro, quy định, độ sẵn sàng hoặc khả năng thương lượng đủ lớn để bù chi phí.

Với nhiều hệ thống, chiến lược exit-ready là điểm cân bằng: chọn một nền tảng chính để khai thác dịch vụ được quản lý, nhưng giữ hợp đồng nghiệp vụ, dữ liệu và quy trình chuyển đổi đủ rõ để có thể rời nền tảng khi điều kiện thay đổi.

## 7. Bảng đánh giá kiến trúc trước khi chọn nền tảng

Có thể dùng bảng chấm điểm sau trong buổi architecture review. Chấm từng tiêu chí từ 1 đến 5, trong đó **1 là rủi ro hoặc công sức thấp, 5 là rủi ro hoặc công sức cao**. Trọng số là gợi ý; hãy điều chỉnh theo mục tiêu của dự án.

| Tiêu chí | Trọng số gợi ý | Điểm 1 thường có nghĩa | Điểm 5 thường có nghĩa |
|---|---:|---|---|
| Độ phức tạp luồng nghiệp vụ | 20% | Ít bước, ít trạng thái, hợp đồng rõ | Nhiều bước bất đồng bộ, saga và phụ thuộc chéo |
| Phụ thuộc dịch vụ riêng của cloud | 20% | API chuẩn, adapter tách biệt | Logic gọi trực tiếp nhiều dịch vụ độc quyền |
| Khả năng chuyển dữ liệu | 15% | Export được, schema rõ, có kiểm tra | Dữ liệu lớn, định dạng riêng, khó đồng bộ hoặc chuyển đổi |
| Portability của runtime và tích hợp | 15% | Runtime phổ biến, event contract rõ | Trigger và runtime gắn chặt vào nền tảng |
| Độ phức tạp vận hành và bảo mật | 15% | Quyền, quan sát và triển khai được chuẩn hóa | Nhiều policy, công cụ và quy trình đặc thù |
| Chi phí và thời gian rời nền tảng | 15% | Có ước lượng, phương án thay thế và runbook | Chi phí khó dự báo, không có phương án chuyển khả thi |

Tính điểm tổng có trọng số:

S = Σ(wᵢ × sᵢ) / Σwᵢ

Trong đó, (s_i) là điểm từ 1 đến 5 và (w_i) là trọng số của tiêu chí. Điểm càng cao cho thấy tổng rủi ro hoặc công sức càng lớn. Có thể dùng ngưỡng tham khảo: 1,0–2,0 là thấp; trên 2,0–3,5 là trung bình; trên 3,5–5,0 là cao. Các ngưỡng này chỉ hỗ trợ thảo luận, không thay thế phân tích từng rủi ro nghiêm trọng.

Đừng chỉ nhìn điểm tổng. Một điểm 5 ở khả năng export dữ liệu có thể là rủi ro không thể chấp nhận dù các tiêu chí khác đều thấp. Hãy ghi thêm bằng chứng, người chịu trách nhiệm, biện pháp giảm thiểu và điều kiện cần xem xét lại quyết định.

## 8. Ví dụ đánh giá hai kiến trúc

### Phương án A: HTTP function mỏng

Một Java function nhận HTTP request, xác thực đầu vào, gọi một service nghiệp vụ độc lập và trả response. API được mô tả bằng OpenAPI; dữ liệu lưu trong database có quy trình export rõ; logic nghiệp vụ không phụ thuộc SDK của cloud.

Kiến trúc này có thể đạt portability tương đối tốt ở mã nguồn và hợp đồng HTTP. Khi chuyển nền tảng vẫn cần thay cấu hình gateway, IAM, secret, logging, deployment và kiểm thử lại timeout, concurrency. Đây không phải chuyển đổi bằng cách chỉ sao chép file JAR, nhưng phạm vi thay đổi có thể được khoanh vùng.

### Phương án B: Quy trình xử lý đơn hàng dùng nhiều dịch vụ đặc thù

Một event kích hoạt function, sau đó function gọi workflow engine riêng của cloud, ghi vào database chuyên biệt, phát notification qua event bus và dùng IAM cùng tracing theo cách riêng của nền tảng. Logic nghiệp vụ nằm xen trong các handler và các bước workflow.

Phương án này có thể mang lại tốc độ phát triển và khả năng tích hợp tốt trong hệ sinh thái đã chọn. Tuy nhiên, khi chuyển nền tảng, đội ngũ phải ánh xạ lại workflow, event delivery, database, IAM, notification và tracing. Phần khó nhất có thể là bảo toàn trạng thái quy trình đang chạy và đảm bảo không xử lý trùng khi chuyển luồng event.

Bài học từ hai ví dụ: hãy đánh giá cả lợi ích hiện tại và chi phí thay đổi tương lai. Không thể kết luận một kiến trúc tốt chỉ dựa trên số lượng function hoặc việc mã nguồn có dùng Java hay không.

## 9. Lộ trình chuẩn bị chuyển nền tảng

Nếu khả năng chuyển đổi là yêu cầu thực tế, hãy chuẩn bị từ lúc thiết kế thay vì chờ đến khi hợp đồng, giá hoặc giới hạn kỹ thuật buộc phải chuyển.

1. **Lập danh mục phụ thuộc:** ghi lại function, trigger, queue, workflow, database, object storage, IAM, secret, mạng, logging, monitoring, IaC và pipeline.
2. **Phân loại mức độ phụ thuộc:** đánh dấu thành phần dùng chuẩn chung, thành phần có adapter, thành phần độc quyền và thành phần không thể thay thế trực tiếp.
3. **Chốt hợp đồng nghiệp vụ:** định nghĩa HTTP API, event schema, versioning, idempotency key, acknowledgment và hành vi retry.
4. **Làm rõ quyền sở hữu dữ liệu:** xác định nguồn dữ liệu chuẩn, định dạng export, cách chuyển schema, lịch sử cần giữ và cách đồng bộ thay đổi trong thời gian cutover.
5. **Tách phần có thể thay thế:** đưa logic nghiệp vụ ra khỏi handler, SDK và cấu hình đặc thù ở những ranh giới có lợi.
6. **Tạo môi trường đích thử nghiệm:** triển khai một luồng đại diện, kiểm tra tải, lỗi, bảo mật, quan sát và chi phí trên nền tảng đích.
7. **Diễn tập cutover và rollback:** xác định thời điểm dừng ghi, đồng bộ dữ liệu cuối, chuyển traffic hoặc event, kiểm tra kết quả và điều kiện quay lại.
8. **Theo dõi sau chuyển đổi:** đối chiếu số lượng bản ghi, trạng thái nghiệp vụ, message tồn, lỗi, độ trễ và chi phí trước khi kết thúc giai đoạn chuyển tiếp.

Một số hệ thống có thể dùng **strangler pattern**: chuyển dần từng capability hoặc luồng nghiệp vụ sang nền tảng mới, định tuyến request theo ranh giới rõ ràng rồi thu hẹp hệ thống cũ. Cách này giảm phạm vi chuyển đổi mỗi lần nhưng yêu cầu quản lý dữ liệu, routing và trạng thái giữa hai môi trường trong thời gian chuyển tiếp.

Không nên chạy song song hai consumer cùng xử lý một queue mà không có cơ chế phân vùng hoặc idempotency. Khi chuyển nguồn event, phải xác định rõ ai sở hữu message, cách xử lý message đang nằm trong queue cũ và cách tránh bỏ sót hoặc xử lý trùng.

## 10. Checklist cho buổi architecture review

- [ ] Đã mô tả các luồng HTTP, message và event quan trọng cùng thứ tự xử lý.
- [ ] Đã nhận diện nơi lưu trạng thái và cách khôi phục quy trình bị gián đoạn.
- [ ] Đã ghi rõ retry, DLQ, idempotency, timeout và semantics của từng trigger.
- [ ] Đã lập danh mục dịch vụ cloud và API đặc thù đang được sử dụng.
- [ ] Logic nghiệp vụ có thể kiểm thử độc lập với adapter của nhà cung cấp ở các ranh giới quan trọng.
- [ ] Event schema và API contract có versioning, ví dụ và quy tắc tương thích.
- [ ] Đã kiểm tra khả năng export dữ liệu, schema migration và tính toàn vẹn sau chuyển đổi.
- [ ] Đã xác định cách chuyển IAM, secret, khóa, network policy và quyền tối thiểu.
- [ ] Đã có phương án thay thế cho logging, metrics, tracing, alert và runbook.
- [ ] Đã ước lượng chi phí chuyển đổi, thời gian gián đoạn và mức mất dữ liệu cho phép.
- [ ] Đã có thử nghiệm đại diện và tiêu chí chấp nhận trên nền tảng đích.
- [ ] Có người chịu trách nhiệm và thời điểm xem xét lại quyết định kiến trúc.

## Tự kiểm tra

1. Vì sao khả năng biên dịch cùng một Java function trên hai cloud chưa chứng minh toàn bộ workload có thể chuyển nền tảng?
2. Hãy nêu ít nhất bốn lớp vendor lock-in có thể tồn tại ngoài SDK trong mã nguồn.
3. Việc dùng CloudEvents có giải quyết được khác biệt về retry, ordering và acknowledgment giữa các queue không? Vì sao?
4. Khi nào nên chấp nhận dùng một dịch vụ cloud độc quyền thay vì cố tạo một abstraction portable?
5. Nếu cần chuyển một quy trình đơn hàng đang chạy sang cloud khác, dữ liệu và message đang xử lý cần được kiểm soát như thế nào để tránh mất hoặc xử lý trùng?
6. Multi-cloud có thể làm tăng độ phức tạp ở những khu vực nào?

Một kiến trúc serverless tốt cần cân bằng tốc độ phát triển, độ tin cậy, công sức vận hành và quyền lựa chọn trong tương lai. Khi đã biết mình phụ thuộc vào đâu, vì sao chấp nhận phụ thuộc đó và cách kiểm chứng phương án rời nền tảng, đội phát triển có thể chọn mức portability phù hợp thay vì theo đuổi một mục tiêu đa nền tảng chung chung.

