# Kiểm tra giả thiết khi phụ thuộc vào hệ thống bên ngoài

Một đoạn mã có thể hoạt động hoàn hảo trong kiểm thử cục bộ nhưng thất bại khi kết nối đến cơ sở dữ liệu, dịch vụ thanh toán, API đối tác hoặc hệ thống hàng đợi. Nguyên nhân thường không chỉ là “mạng không ổn định” mà còn nằm ở **các giả thiết ngầm**: dịch vụ luôn phản hồi nhanh, kết quả luôn đúng định dạng, thông tin không bao giờ cũ, lời gọi lại không tạo tác dụng phụ, hoặc trạng thái lỗi có nghĩa giống nhau ở mọi hệ thống.

Trong chương **Độ tin cậy** của **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là hiểu cách tạo mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Bài này tập trung vào việc nhận diện, kiểm tra và ghi lại giả thiết khi mã phụ thuộc vào những thành phần mà nhóm không kiểm soát hoàn toàn.

## 1. “Hệ thống bên ngoài” bao gồm những gì?

Một phụ thuộc bên ngoài là thành phần mà mã của ta phải tương tác qua một ranh giới riêng, chẳng hạn ranh giới tiến trình, mạng, tổ chức, quyền truy cập hoặc vòng đời triển khai:

- API của đối tác như thanh toán, vận chuyển, định danh, gửi thông báo.
- Dịch vụ khác trong cùng tổ chức, kể cả cùng repository nhưng triển khai độc lập.
- Cơ sở dữ liệu, cache dùng chung, object storage và hệ thống tìm kiếm.
- Message broker, hàng đợi, hệ thống xử lý sự kiện.
- Nhà cung cấp xác thực, DNS, hệ thống quản lý bí mật và nền tảng đám mây.
- Tệp đầu vào từ hệ thống khác hoặc gói thư viện có giao diện, phiên bản và vòng đời phát hành độc lập.

“Bên ngoài” **không nhất thiết là bên thứ ba**. Một microservice do cùng công ty quản lý vẫn có thể chậm, đổi schema, mất kết nối hoặc triển khai phiên bản khác mà bên gọi chưa biết.

Độ tin cậy của toàn luồng bị giới hạn bởi cách **các phụ thuộc phối hợp**. Một API trả HTTP 200 nhưng chứa giá sai hoặc dữ liệu thuộc phiên bản cũ có thể gây vấn đề nghiêm trọng không kém timeout.

## 2. Các nhóm giả thiết cần kiểm tra

| Nhóm | Giả thiết thường bị bỏ qua | Câu hỏi cần xác minh |
| --- | --- | --- |
| **Tính sẵn sàng** | Phụ thuộc luôn hoạt động | Khi bảo trì, lỗi từng vùng hoặc mất kết nối, luồng xử lý sẽ thế nào? |
| **Độ trễ** | Lời gọi luôn trả nhanh | Có timeout và ngân sách thời gian chung cho toàn yêu cầu không? |
| **Hợp đồng giao tiếp** | Mọi phản hồi đều có cấu trúc mong đợi | Phiên bản API, status, field bắt buộc và cách xử lý giá trị lạ đã rõ chưa? |
| **Ngữ nghĩa nghiệp vụ** | Phản hồi “thành công” có nghĩa là nghiệp vụ đã hoàn tất | Trạng thái “được chấp nhận”, “đang xử lý” và “hoàn tất” khác nhau ra sao? |
| **Tính nhất quán, độ tươi** | Dữ liệu luôn là mới nhất | Cache, đồng bộ bất đồng bộ và độ trễ cập nhật có được phép không? |
| **Thứ tự và trùng lặp** | Sự kiện đến đúng một lần, theo thứ tự | Có thể nhận trùng, nhận muộn hoặc đảo thứ tự không? |
| **Thử lại** | Gửi lại yêu cầu luôn an toàn | Lời gọi có tác dụng phụ? Có idempotency key hoặc cơ chế chống trùng? |
| **Quyền truy cập** | Token, quyền và cấu hình luôn hợp lệ | Khi token hết hạn, quyền đổi hoặc chứng chỉ luân chuyển thì sao? |
| **Giới hạn tài nguyên** | Không bị giới hạn tần suất và dung lượng | Có rate limit, quota, giới hạn payload và kiểm soát tải không? |
| **Thời gian** | Đồng hồ và múi giờ thống nhất | Timestamp, TTL, thời hạn hiệu lực hoặc độ lệch đồng hồ ảnh hưởng thế nào? |
| **Khả năng quan sát** | Khi lỗi, luôn xác định được nguyên nhân | Có correlation ID, metric và mã lỗi để đối soát không? |

Chỉ cần **một giả thiết sai** cũng có thể làm xuất hiện lỗi ở thành phần gọi. Mục đích của việc kiểm tra không phải dự đoán mọi sự cố, mà là nhận diện những giả thiết quan trọng, tìm bằng chứng và xác định hành vi an toàn khi chúng không còn đúng.

## 3. Phân biệt điều đã biết và điều đang giả định

Xét yêu cầu: “Gọi dịch vụ kho để xác định sản phẩm còn hàng trước khi tiếp tục đặt hàng”.

Có ít nhất bốn câu khác nhau:

1. **Yêu cầu:** không được xác nhận việc giữ hàng nếu chưa thực hiện thao tác dự trữ hợp lệ.
2. **Thông tin trong hợp đồng:** API kiểm tra kho trả trạng thái **IN_STOCK** hoặc **OUT_OF_STOCK** ở trường hợp thành công.
3. **Giả thiết cần kiểm tra:** dữ liệu kiểm tra kho phản ánh trạng thái đủ mới để hiển thị cho khách.
4. **Giả thiết không an toàn:** trả **IN_STOCK** đồng nghĩa đơn hàng đã được dự trữ và sẽ không bị bán cho người khác.

Câu thứ tư sai trong nhiều thiết kế: **kiểm tra tồn kho** và **dự trữ tồn kho** là hai thao tác khác nhau. Ngay sau khi kiểm tra còn hàng, một đơn khác có thể dự trữ trước. Cần giao thức đặt giữ hàng hoặc thao tác cập nhật có điều kiện tương ứng để bảo đảm bất biến nghiệp vụ.

Một mẫu diễn đạt giả thiết có thể kiểm chứng:

> Trong [môi trường và thời gian], chúng ta giả định [điều kiện cụ thể], dựa trên [hợp đồng hoặc số đo]. Nếu [tín hiệu thay đổi], cần xem lại [cách xử lý] vì [rủi ro].

Ví dụ: “Dịch vụ kho được kỳ vọng phản hồi trong 2 giây ở 99% yêu cầu trong giờ làm việc theo SLO đã thống nhất. Nếu tỷ lệ timeout vượt ngưỡng cảnh báo trong 15 phút, cần đánh giá khả năng đáp ứng và áp dụng cơ chế giảm tải.” Các số liệu này chỉ mang tính minh họa; ngưỡng thật phải dựa trên thỏa thuận và đo đạc của hệ thống.

## 4. Kiểm tra hợp đồng: không chỉ kiểm tra HTTP status

Giả sử API tồn kho minh họa có hợp đồng:

- `GET /v1/availability?sku=...` trả **200** kèm body `IN_STOCK` hoặc `OUT_OF_STOCK`.
- **429** báo giới hạn tốc độ; có thể kèm `Retry-After`.
- **503** thể hiện dịch vụ tạm không sẵn sàng.
- **401/403** liên quan đến xác thực hoặc phân quyền.
- Timeout hay lỗi kết nối không cung cấp câu trả lời đáng tin về trạng thái sản phẩm.

Dưới đây là **hợp đồng giả định cho bài học**, không phải chuẩn chung cho mọi API. Khi tích hợp thật, phải đọc tài liệu và xác nhận hành vi từ nhà cung cấp, nhất là với **404**, **202** hoặc cấu trúc body.

### Những điều nên kiểm tra cho mỗi endpoint

- **Đầu vào:** kiểu dữ liệu, mã hóa ký tự, trường bắt buộc, độ dài, điều kiện hợp lệ.
- **Đầu ra:** kiểu dữ liệu, trường tùy chọn, giá trị mới, ràng buộc giữa các trường.
- **Mã trạng thái:** thành công, lỗi người gọi, giới hạn tốc độ, lỗi tạm thời và lỗi không thể thử lại.
- **Phiên bản:** cách nâng cấp, trường bị bỏ, khả năng tương thích ngược, thời gian chuyển đổi.
- **Độ tươi:** dữ liệu đại diện cho thời điểm nào, có cache hoặc bất đồng bộ không.
- **Tác dụng phụ:** gọi lại có ghi dữ liệu, trừ tiền, tạo đơn hoặc gửi thông báo lặp không.
- **Giới hạn:** timeout, rate limit, dung lượng phản hồi, quota và giới hạn đồng thời.
- **Bảo mật:** cách cấp quyền, thay đổi khóa, xác minh TLS, dữ liệu nào được phép ghi log.

Không được coi “phản hồi hợp lệ về cú pháp” là “đúng về ngữ nghĩa”. Chuỗi `IN_STOCK` có thể parse thành công nhưng chưa xác nhận được hàng đã được giữ.

## 5. Ví dụ Java: biến phụ thuộc thành ranh giới có hành vi rõ ràng

Mục tiêu là không đánh đồng “không có hàng” với “không biết có hàng hay không”. Nếu gọi dịch vụ thất bại, hệ thống nên biểu diễn trạng thái **UNKNOWN**, sau đó áp dụng chính sách nghiệp vụ phù hợp.

Ví dụ dưới đây dùng Java 11+ và API minh họa ở phần trước. Endpoint được truyền từ cấu hình, có đường dẫn hoàn chỉnh và **không có query hoặc fragment**.

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Objects;

enum Availability {
    IN_STOCK,
    OUT_OF_STOCK,
    UNKNOWN
}

final class InventoryClient {
    private final HttpClient httpClient;
    private final URI endpoint;

    InventoryClient(URI endpoint) {
        this.endpoint = Objects.requireNonNull(endpoint, "endpoint");
        if (!endpoint.isAbsolute() || endpoint.getRawQuery() != null
                || endpoint.getRawFragment() != null) {
            throw new IllegalArgumentException(
                    "endpoint must be an absolute URI without query or fragment");
        }

        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(1))
                .build();
    }

    Availability lookup(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }

        String encodedSku =
                URLEncoder.encode(sku, StandardCharsets.UTF_8);
        URI uri = URI.create(endpoint + "?sku=" + encodedSku);

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(2))
                .header("Accept", "text/plain")
                .GET()
                .build();

        try {
            HttpResponse<String> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            return decode(response.statusCode(), response.body());
        } catch (IOException e) {
            // Không suy ra OUT_OF_STOCK từ lỗi kết nối.
            // Triển khai thực tế cần phát metric/log phù hợp.
            return Availability.UNKNOWN;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            // Ngừng luồng đang bị hủy thay vì tiếp tục quy trình.
            throw new IllegalStateException(
                    "Inventory lookup was interrupted", e);
        }
    }

    static Availability decode(int statusCode, String body) {
        if (statusCode != 200 || body == null) {
            return Availability.UNKNOWN;
        }

        switch (body.trim()) {
            case "IN_STOCK":
                return Availability.IN_STOCK;
            case "OUT_OF_STOCK":
                return Availability.OUT_OF_STOCK;
            default:
                // 200 với dữ liệu lạ vẫn là phản hồi không đáng tin.
                return Availability.UNKNOWN;
        }
    }
}
~~~

Lưu ý các lựa chọn trong ví dụ:

- **Connect timeout** giới hạn thời gian thiết lập kết nối; **request timeout** giới hạn thời gian cho một yêu cầu theo API Java. Cả hai không tự thiết lập ngân sách thời gian cho toàn bộ chuỗi thao tác nghiệp vụ.
- **UNKNOWN** là kết quả khi chưa có bằng chứng đáng tin; nó khác **OUT_OF_STOCK**, là kết luận nghiệp vụ xác định.
- **200 với body lạ** vẫn là bất thường về hợp đồng. Hệ thống thật cần log có kiểm soát, metric và cảnh báo nếu xảy ra nhiều.
- **401/403, 429 và 503** đều được biểu diễn là UNKNOWN ở ranh giới đơn giản này, nhưng **nguyên nhân cần được phân loại riêng ở lớp quan sát và điều phối**. Lỗi cấu hình quyền thường không nên thử lại giống lỗi mạng tạm thời.
- Ví dụ chưa bao gồm giới hạn kích thước response, quản lý kết nối nâng cao, giám sát và retry. Khi áp dụng thật, cần bổ sung các kiểm soát phù hợp theo rủi ro.

### Tại sao không tự biến UNKNOWN thành OUT_OF_STOCK hoặc IN_STOCK?

Nếu trả **OUT_OF_STOCK** khi timeout, hệ thống thông báo sai rằng sản phẩm đã hết. Nếu trả **IN_STOCK** khi timeout, hệ thống có thể tiến tới thao tác không có đủ bằng chứng. Một giao diện có thể hiển thị “Chưa kiểm tra được tồn kho, vui lòng thử lại” hoặc giữ luồng đặt hàng ở trạng thái chờ. Quy tắc cụ thể thuộc về nghiệp vụ; điểm quan trọng là **giữ nguyên sự không chắc chắn** tới nơi có quyền quyết định.

Ngay cả kết quả **IN_STOCK** cũng chỉ dùng để thông báo khả năng còn hàng, không thay cho thao tác **dự trữ** được kiểm soát đồng thời khi chốt đơn.

## 6. Kiểm thử giả thiết bằng các trường hợp lỗi có chủ đích

Chỉ thử “API trả 200 và dữ liệu đúng” sẽ bỏ qua phần lớn tình huống ảnh hưởng đến độ tin cậy.

| Tình huống mô phỏng | Giả thiết được thử | Hành vi mong đợi |
| --- | --- | --- |
| **200, IN_STOCK** | Hợp đồng phản hồi hợp lệ | Trả IN_STOCK |
| **200, OUT_OF_STOCK** | Giá trị nghiệp vụ đầy đủ | Trả OUT_OF_STOCK |
| **200, body rỗng/không biết** | Mã có chịu được schema sai hoặc phiên bản mới? | Trả UNKNOWN, ghi nhận vi phạm hợp đồng |
| **429, có Retry-After** | Hệ thống có tôn trọng rate limit? | Không gọi dồn dập; điều phối thử lại theo chính sách |
| **503, 502** | Hệ thống có chịu được lỗi tạm thời? | Phản hồi có kiểm soát; thử lại chỉ khi an toàn |
| **401, 403** | Quyền và thông tin xác thực có luôn hợp lệ? | Phân loại lỗi cấu hình/quyền; không retry vô hạn |
| **Timeout / DNS / TLS lỗi** | Kết nối có thực sự luôn thành công? | UNKNOWN hoặc lỗi có kiểm soát, không treo vô hạn |
| **Phản hồi quá lớn** | Dung lượng đầu vào có giới hạn? | Giới hạn đọc/bộ nhớ và từ chối theo chính sách |
| **Giá trị dữ liệu cũ** | Có thể tin vào tính tức thời của dữ liệu? | Hiển thị thời điểm/phiên bản hoặc làm mới theo hợp đồng |
| **Nhiều yêu cầu đồng thời** | Có tranh chấp tài nguyên hoặc giới hạn tải? | Vẫn đúng nghiệp vụ, không đè dữ liệu hoặc quá tải |
| **Gửi lại lệnh ghi sau timeout** | Retry có tạo tác dụng phụ trùng? | Chống trùng hoặc đối soát trước khi quyết định |
| **Sự kiện trùng và đảo thứ tự** | Hàng đợi có đảm bảo đúng một lần, đúng thứ tự? | Xử lý idempotent, có phiên bản hoặc thứ tự phù hợp |

### Ví dụ kiểm thử đơn vị cho phần hợp đồng

Có thể kiểm tra bộ giải mã mà không cần gọi mạng. Các test sau dùng JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class InventoryClientTest {
    @Test
    void acceptsKnownBusinessResponses() {
        assertEquals(
                Availability.IN_STOCK,
                InventoryClient.decode(200, "IN_STOCK"));

        assertEquals(
                Availability.OUT_OF_STOCK,
                InventoryClient.decode(200, "OUT_OF_STOCK"));
    }

    @Test
    void doesNotTreatUnknownPayloadAsStock() {
        assertEquals(
                Availability.UNKNOWN,
                InventoryClient.decode(200, "MAYBE"));
        assertEquals(
                Availability.UNKNOWN,
                InventoryClient.decode(200, ""));
    }

    @Test
    void doesNotTurnHttpFailuresIntoBusinessFacts() {
        assertEquals(
                Availability.UNKNOWN,
                InventoryClient.decode(429, "IN_STOCK"));
        assertEquals(
                Availability.UNKNOWN,
                InventoryClient.decode(503, "OUT_OF_STOCK"));
    }
}
~~~

Bộ test này chỉ kiểm tra **giải mã phản hồi**, chưa chứng minh timeout, TLS, DNS hoặc hành vi của `HttpClient`. Để kiểm tra phần tích hợp, có thể dùng máy chủ HTTP giả lập (stub/mock server) để chủ động trả mã lỗi, trì hoãn phản hồi hoặc ngắt kết nối. Các kiểm thử contract với nhà cung cấp giúp phát hiện thay đổi schema; kiểm thử trong môi trường gần sản xuất giúp phát hiện giới hạn và cấu hình khác biệt.

Nên kiểm tra cả **hành vi của thành phần gọi**: khi tồn kho UNKNOWN, luồng đặt hàng có ngừng đúng chỗ không, giao diện thông báo thế nào, dữ liệu có bị ghi một phần không, có phát metric hữu ích không?

## 7. Đặc biệt thận trọng với retry và tác dụng phụ

Một giả thiết phổ biến nhưng nguy hiểm là: “Nếu không nhận được phản hồi thì yêu cầu chắc chưa được xử lý.”

Đối với thao tác **ghi**, timeout có thể xảy ra **sau khi máy chủ đã hoàn tất tác dụng phụ** nhưng trước khi phản hồi về đến phía gọi. Ví dụ:

1. Dịch vụ đơn hàng gửi yêu cầu tạo giao dịch thanh toán.
2. Hệ thống thanh toán ghi nhận giao dịch thành công.
3. Mạng mất kết nối trước khi phía đơn hàng nhận kết quả.
4. Dịch vụ đơn hàng retry bằng một yêu cầu mới không có cơ chế chống trùng.
5. Có nguy cơ tạo thêm giao dịch nếu API không đảm bảo idempotency.

Vì thế, phải phân biệt:

- **Thành công:** có bằng chứng đáng tin rằng thao tác hoàn tất.
- **Thất bại xác định:** có bằng chứng rằng thao tác bị từ chối và không phát sinh tác dụng phụ theo hợp đồng.
- **Kết quả chưa xác định:** không đủ thông tin để nói thao tác thành công hay thất bại.

Đối với tác vụ có tác dụng phụ, cần kiểm tra **hợp đồng idempotency**, khóa yêu cầu duy nhất, chính sách retry, cách truy vấn trạng thái giao dịch và cơ chế đối soát. Không được tự giả định mọi POST đều có thể retry an toàn. Đối với GET chỉ đọc, retry thường dễ chấp nhận hơn nhưng vẫn phải xét tải, quota, timeout và tình trạng quá tải của phía cung cấp.

### Một chính sách retry cần trả lời được

- **Lỗi nào được retry?** Timeout, 503 hoặc 429 có thể phù hợp tùy API; 400 do dữ liệu sai thường không.
- **Tối đa bao nhiêu lần?** Tránh vòng lặp vô hạn và bão retry.
- **Chờ bao lâu?** Có thể dùng exponential backoff kèm jitter; tôn trọng `Retry-After` khi hợp đồng yêu cầu.
- **Deadline chung là gì?** Nhiều lần retry không được làm vượt quá thời gian chấp nhận của luồng gọi.
- **Tác dụng phụ có được chống trùng?** Với thanh toán, tạo đơn hoặc gửi thông báo, cần cơ chế cụ thể.
- **Khi hết lượt thì sao?** Trả kết quả chưa xác định, chuyển sang đối soát, hoặc xử lý thất bại theo hợp đồng.

Sơ đồ quyết định minh họa:

~~~mermaid
flowchart TD
    A[Gọi phụ thuộc bên ngoài] --> B{Có phản hồi đáng tin?}
    B -- Có --> C{Đúng hợp đồng và ngữ nghĩa?}
    C -- Có --> D[Áp dụng kết quả nghiệp vụ]
    C -- Không --> E[Ghi lỗi hợp đồng và xử lý an toàn]
    B -- Không --> F{Lời gọi có tác dụng phụ?}
    F -- Có --> G[Kiểm tra idempotency hoặc đối soát]
    F -- Không --> H{Lỗi tạm thời và còn deadline?}
    G --> I{Thử lại được xác nhận an toàn?}
    I -- Có --> H
    I -- Không --> J[Giữ trạng thái chưa xác định]
    H -- Có --> K[Backoff, giới hạn retry rồi gọi lại]
    H -- Không --> J
    K --> A
~~~

Sơ đồ chỉ là hướng suy nghĩ; với lỗi không thể sửa bằng retry, chẳng hạn schema không tương thích hoặc quyền bị từ chối, cần điều tra nguyên nhân thay vì tiếp tục gửi lại.

## 8. Kiểm tra giả thiết về dữ liệu và thời gian

Dịch vụ ngoài có thể trả dữ liệu **hợp lệ nhưng chưa phải dữ liệu mong muốn**.

### 8.1. Độ tươi và tính nhất quán

Nếu API dùng cache, một bản ghi “đang còn hàng” có thể phản ánh ảnh chụp vài giây trước. Hãy xác định:

- Độ trễ cập nhật tối đa được chấp nhận là bao lâu?
- Phản hồi có timestamp, version hoặc ETag để phân biệt dữ liệu cũ?
- Có yêu cầu `read-your-writes`, đọc nhất quán hoặc giao dịch không?
- Một quyết định nghiệp vụ có bắt buộc kiểm tra lại ở thời điểm commit không?

Nếu độ tươi chỉ phục vụ hiển thị, “cập nhật chậm tối đa 30 giây” có thể được chấp nhận. Nếu dùng để hoàn tất thanh toán hay giữ hàng, tính đúng đắn có thể đòi hỏi giao thức chặt chẽ hơn.

### 8.2. Đồng hồ, múi giờ và thứ tự

Timestamp từ hai hệ thống khác nhau có thể dùng múi giờ hoặc đồng hồ lệch nhau. Không nên dùng thời gian nhận sự kiện như bằng chứng chắc chắn rằng sự kiện xảy ra sau sự kiện khác. Nếu thứ tự nghiệp vụ quan trọng, cần xác định sequence number, version hoặc cơ chế đồng bộ phù hợp.

Một message broker có thể bảo đảm thứ tự **trong từng partition**, nhưng không nhất thiết giữa tất cả partition. Các đảm bảo như “at least once” và “at most once” thay đổi cách xử lý trùng, mất thông điệp và retry. Phải đọc đúng hợp đồng của broker đang sử dụng.

### 8.3. Dữ liệu thiếu, giá trị lạ và phiên bản mới

Dịch vụ có thể thêm trạng thái nghiệp vụ mới, chuyển field sang optional hoặc thay đổi đơn vị đo. Chương trình không nên mặc định mọi giá trị lạ là một giá trị hợp lệ đã biết.

Ví dụ, khi API thêm trạng thái `RESERVED`, phiên bản client cũ không thể tự xem đó là `IN_STOCK` nếu hợp đồng chưa xác định. Có thể cần từ chối có kiểm soát, nâng phiên bản hoặc bổ sung cách xử lý theo quy tắc nghiệp vụ được xác nhận.

## 9. Giảm phạm vi hỏng khi phụ thuộc gặp sự cố

Không thể kiểm soát độ sẵn sàng của mọi dịch vụ ngoài, nhưng có thể kiểm soát **mức độ lan truyền của sự cố**:

| Biện pháp | Mục đích | Cần chú ý |
| --- | --- | --- |
| Timeout ở từng lời gọi và deadline toàn luồng | Không chờ vô hạn | Timeout quá ngắn có thể gây thất bại giả; quá dài gây nghẽn |
| Retry có giới hạn và backoff | Vượt qua lỗi tạm thời | Không làm quá tải thêm phía phụ thuộc; bảo vệ tác dụng phụ |
| Bulkhead / giới hạn đồng thời | Ngăn một phụ thuộc chiếm hết luồng/kết nối | Giới hạn phải có bằng chứng về tải |
| Circuit breaker | Dừng gửi thêm khi lỗi lặp lại vượt ngưỡng | Cần quy tắc đóng/mở lại và quan sát |
| Cache hoặc fallback có điều kiện | Duy trì một phần chức năng khi lỗi | Không trả dữ liệu cũ ở nghiệp vụ yêu cầu tính đúng tức thời |
| Queue và xử lý bất đồng bộ | Tách thời điểm chấp nhận và thực thi công việc | Cần theo dõi trạng thái, trùng lặp và dead-letter |
| Idempotency / đối soát | Hạn chế tác dụng phụ trùng và kết quả mơ hồ | Phải gắn với khóa, phạm vi và chính sách lưu trạng thái phù hợp |
| Kiểm soát cấu hình, chứng chỉ, quyền | Tránh lỗi do thay đổi môi trường | Cần có cơ chế luân chuyển và rà soát trước khi hết hạn |

**Fallback phải phù hợp ngữ nghĩa.** Khi dịch vụ gợi ý sản phẩm lỗi, có thể tạm ẩn gợi ý. Khi dịch vụ kiểm tra hạn mức hoặc xác thực lỗi, không được mặc định cho phép thao tác chỉ để giữ giao diện “chạy được”.

Sử dụng nhiều cơ chế cùng lúc cũng tạo độ phức tạp. Ví dụ, retry ở ba tầng khác nhau có thể nhân số lượt gọi, gây bão tải dù mỗi tầng đều có “tối đa ba lần”. Cần xác định **điểm điều phối duy nhất** hoặc phối hợp retry rõ ràng giữa các tầng.

## 10. Bằng chứng cần thu thập khi kiểm tra giả thiết

Không nên chỉ dựa vào câu “đối tác cam kết ổn định”. Một giả thiết có thể được kiểm tra bằng nhiều nguồn:

1. **Hợp đồng chính thức:** tài liệu endpoint, SLA/SLO, chính sách rate limit, phiên bản và quy tắc trạng thái.
2. **Kiểm thử contract và tích hợp:** phản hồi hợp lệ, giá trị mới, dữ liệu thiếu, lỗi 4xx/5xx, timeout.
3. **Số đo vận hành:** tỷ lệ thành công, độ trễ p95/p99, tần suất timeout, số lần retry và các lỗi hợp đồng.
4. **Thử nghiệm lỗi có kiểm soát:** ngắt kết nối, mô phỏng chậm, giảm quota, gửi thông điệp trùng hoặc đảo thứ tự.
5. **Thông tin thay đổi:** thông báo từ nhà cung cấp, lịch nâng phiên bản, luân chuyển chứng chỉ và quy trình quản lý API.
6. **Bằng chứng nghiệp vụ:** đối soát đơn hàng, thanh toán, trạng thái kho và sai lệch thực tế.

Khi đo, nên phân biệt:

- **Tỷ lệ lỗi ứng dụng** với **tỷ lệ lỗi phụ thuộc**.
- **Lỗi kỹ thuật** với **từ chối nghiệp vụ hợp lệ** (ví dụ hết hàng).
- **Độ trễ của một lời gọi** với **độ trễ toàn luồng**.
- **Tình trạng phát hiện được lỗi** với **khả năng khôi phục nghiệp vụ**.

Một metric như `external_inventory_unknown_total` có thể giúp phát hiện xu hướng; cần phân loại lý do như timeout, HTTP status và dữ liệu không hợp lệ mà không đưa thông tin nhạy cảm vào nhãn metric. Với lỗi giao dịch, log có correlation ID phù hợp và bảng đối soát thường giá trị hơn việc ghi toàn bộ request chứa dữ liệu cá nhân.

## 11. Mẫu ghi nhận giả thiết và điều kiện xem lại

Một bản ghi ngắn giúp kỹ sư mới biết điều gì đã được xác minh, điều gì còn chưa chắc và khi nào phải kiểm tra lại.

~~~markdown
### Phụ thuộc: <tên API/hệ thống>
- Mục đích và luồng nghiệp vụ sử dụng:
- Người hoặc nhóm sở hữu ở phía gọi:
- Hợp đồng/phiên bản đang áp dụng:
- Giả thiết A1: <nội dung, phạm vi, mốc thời gian>
- Bằng chứng: <tài liệu, test, số đo, ngày xác minh>
- Độ tin cậy: <đã kiểm chứng / ước lượng / chưa xác nhận>
- Hậu quả nếu A1 sai:
- Hành vi khi timeout, lỗi hợp đồng, không đủ dữ liệu:
- Retry: <điều kiện, giới hạn, deadline, idempotency>
- Khả năng giảm tác động và khôi phục:
- Tín hiệu xem lại: <metric/ngưỡng/sự kiện>
- Người theo dõi và mốc rà soát:
- Quyết định cần thay đổi khi điều kiện xuất hiện:
~~~

Ví dụ áp dụng vào API kho:

> **Giả thiết:** endpoint đọc trạng thái kho trả về một trong hai giá trị `IN_STOCK` hoặc `OUT_OF_STOCK` khi HTTP 200. **Bằng chứng:** hợp đồng API phiên bản đang dùng và kiểm thử contract. **Hậu quả nếu sai:** client có thể hiểu sai trạng thái, dẫn đến thông báo sai cho khách. **Hành vi:** giá trị không biết được biểu diễn `UNKNOWN`, không được chốt dự trữ dựa trên kết quả này. **Điều kiện xem lại:** đối tác thêm giá trị trạng thái, cập nhật phiên bản API hoặc metric phản hồi không hợp lệ tăng lên. **Hành động:** xác nhận hợp đồng mới, bổ sung mô hình trạng thái và kiểm thử trước khi thay đổi luồng đặt hàng.

Khi giả thiết thay đổi, hãy **cập nhật nguồn chính** và liên kết quyết định cũ với quyết định mới; tránh chỉ thay một nhánh code mà không ghi rõ sự thay đổi ngữ nghĩa.

## 12. Những sai lầm dễ gặp

**“Thấy HTTP 200 là đủ tin cậy.”** Sai. Phải kiểm tra định dạng, ý nghĩa nghiệp vụ, độ tươi và điều kiện nhất quán khi cần.

**“Nếu timeout thì thao tác chưa xảy ra.”** Không thể kết luận như vậy đối với yêu cầu có tác dụng phụ; có thể cần truy vấn trạng thái hoặc đối soát.

**“Retry nhiều hơn sẽ luôn tăng độ tin cậy.”** Không đúng. Retry thiếu giới hạn có thể gây bão tải và tạo tác dụng phụ trùng; có những lỗi hoàn toàn không thể sửa bằng thử lại.

**“Mock trả đúng dữ liệu tức là tích hợp an toàn.”** Mock kiểm tra logic theo dữ liệu mô phỏng. Nó không chứng minh hợp đồng thật, TLS, quyền, quota, độ trễ hay thay đổi phiên bản hoạt động như mong đợi.

**“Dùng cache giúp hệ thống tiếp tục hoạt động nên chắc chắn tốt.”** Cache có thể hỗ trợ sẵn sàng, nhưng dữ liệu cũ có thể vi phạm tính đúng đắn. Fallback phải có điều kiện chấp nhận rõ ràng.

**“Một dependency thuộc công ty mình thì không cần contract.”** Khi hai thành phần triển khai độc lập, thay đổi ở một bên vẫn có thể phá vỡ bên kia. Cần hợp đồng, phiên bản và kiểm thử tương thích phù hợp.

**“Có metric là đã xử lý lỗi.”** Metric giúp phát hiện, nhưng nếu không có ngưỡng, người phụ trách và cơ chế xử lý thì sự cố vẫn có thể kéo dài.

**“UNKNOWN cũng giống OUT_OF_STOCK.”** Không đúng. Một bên là kết luận nghiệp vụ; bên kia là thiếu bằng chứng. Gộp hai trạng thái làm mất thông tin quan trọng khi xử lý lỗi.

## 13. Bài tập vận dụng

Một dịch vụ đặt hàng gọi API thanh toán. Sau 2 giây không có phản hồi, phần mềm đang tạo yêu cầu thanh toán mới bằng mã giao dịch khác. Nhóm nói: “Không nhận kết quả thì coi như lần trước thất bại”.

Hãy phân tích:

1. Giả thiết nào đang được dùng mà chưa chứng minh?
2. Hậu quả tệ nhất khi giả thiết sai là gì?
3. Nên bổ sung bằng chứng và cơ chế nào?
4. Nên trả trạng thái gì cho nghiệp vụ trong lúc chưa biết kết quả?

**Gợi ý:**

- Giả thiết “timeout đồng nghĩa giao dịch không được ghi nhận” **chưa được chứng minh**.
- Có nguy cơ thu tiền hai lần hoặc phát sinh hai giao dịch cùng mục đích.
- Cần kiểm tra hợp đồng idempotency của phía thanh toán, dùng khóa giao dịch ổn định theo ý định thanh toán, truy vấn trạng thái hoặc đối soát; retry theo chính sách an toàn đã xác nhận.
- Khi không biết kết quả, giữ trạng thái **đang xác minh/chưa xác định** thay vì tự khẳng định thất bại rồi tạo giao dịch mới. Cách hoàn tất cụ thể phụ thuộc hợp đồng cổng thanh toán và yêu cầu nghiệp vụ.

## 14. Danh sách câu hỏi trước khi đưa vào vận hành

Trước mỗi tích hợp phụ thuộc bên ngoài, hãy trả lời:

- **Hợp đồng:** đầu vào, đầu ra, mã trạng thái, phiên bản và ý nghĩa nghiệp vụ đã rõ chưa?
- **Thời gian:** timeout từng lời gọi và deadline toàn luồng có phù hợp với người dùng?
- **Thất bại:** khi 429, 503, timeout, dữ liệu sai hoặc mất quyền, hệ thống làm gì?
- **Retry:** thao tác có tác dụng phụ không, có idempotency và giới hạn retry?
- **Dữ liệu:** yêu cầu về độ tươi, trùng lặp, thứ tự và nhất quán đã xác nhận?
- **An toàn:** fallback có làm sai kết quả, lộ dữ liệu hoặc bỏ qua phân quyền?
- **Bằng chứng:** đã có test contract, kiểm thử lỗi và đo đạc mức cần thiết?
- **Vận hành:** có metric, log, người phụ trách và phương án đối soát/phục hồi?
- **Tương lai:** điều kiện nào sẽ kích hoạt xem xét lại giả thiết hoặc nâng cấp hợp đồng?

Độ tin cậy không đến từ niềm tin rằng hệ thống bên ngoài **sẽ luôn hoạt động đúng**. Nó đến từ việc biết **ta đang dựa vào điều gì, có bằng chứng nào, giới hạn nằm ở đâu và sẽ phản ứng thế nào khi giả thiết sai**. Đó cũng là cách làm cho mã trong **CODE_QUALITY_FUNDAMENTALS** vừa đáng tin cậy khi chạy, vừa dễ hiểu khi đọc, vừa dễ thay đổi khi phụ thuộc hoặc bối cảnh nghiệp vụ biến đổi.
