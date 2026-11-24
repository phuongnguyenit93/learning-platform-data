# Instrumentation ở đúng boundary

Instrumentation là việc đặt điểm ghi nhận observability vào ứng dụng để đo thời gian, kết quả và ngữ cảnh của một hoạt động. Trong Spring Boot, Micrometer Observation cung cấp API chung để một hoạt động có thể được chuyển thành metrics, tracing và các tín hiệu liên quan thông qua những handler đã cấu hình.

Chất lượng telemetry phụ thuộc nhiều vào vị trí đặt instrumentation. Nếu đo ở mọi method, trace sẽ có quá nhiều span nhỏ, metrics tăng cardinality và dữ liệu khó đọc. Nếu chỉ đo ở một điểm quá rộng, ta biết toàn bộ request chậm nhưng khó xác định phần việc nào gây ra độ trễ. Vì vậy, cần chọn boundary phản ánh một hoạt động có ý nghĩa với người vận hành, đồng thời tận dụng instrumentation tự động của Spring Boot và Micrometer ở những lớp đã được hỗ trợ.

Bài học này thuộc chương **Thiết kế kiến trúc** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; nội dung tập trung vào cách chọn đúng ranh giới để liên kết tín hiệu, điều tra lỗi và độ trễ trong ứng dụng thực tế.

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích instrumentation boundary và vai trò của nó trong kiến trúc observability.
- Chọn vị trí đo ở ranh giới HTTP, use case, dependency và messaging.
- Phân biệt instrumentation tự động với Observation do ứng dụng tạo.
- Dùng `ObservationRegistry` và Observation API để bao quanh một thao tác nghiệp vụ.
- Tránh đo trùng, tạo span quá nhỏ hoặc đưa dữ liệu không phù hợp vào tag.
- Xử lý scope, transaction và luồng bất đồng bộ đúng vòng đời.

## Instrumentation boundary là gì?

Boundary là ranh giới bắt đầu và kết thúc của một hoạt động mà ta muốn quan sát độc lập. Một boundary tốt có tên ổn định, có ý nghĩa nghiệp vụ hoặc kỹ thuật rõ ràng, có thời gian thực thi xác định và cung cấp dữ liệu giúp trả lời một câu hỏi vận hành.

Ví dụ, khi người dùng gửi yêu cầu checkout, ứng dụng có thể ghi nhận các hoạt động:

1. HTTP server nhận request và chuyển nó tới controller.
2. Use case `checkout.submit` điều phối kiểm tra giỏ hàng, giữ hàng và thanh toán.
3. HTTP client gọi dịch vụ thanh toán.
4. Repository lưu đơn hàng.
5. Kết quả được trả về cho client.

Mỗi hoạt động có một ranh giới khác nhau. HTTP server boundary trả lời request mất bao lâu và kết thúc với trạng thái nào. Use-case boundary trả lời nghiệp vụ checkout mất bao lâu và kết quả ra sao. HTTP client boundary trả lời dịch vụ thanh toán phản hồi thế nào. Khi các boundary này được liên kết đúng, trace thể hiện được đường đi từ request vào ứng dụng qua các dependency.

Không phải mọi method đều là một boundary hữu ích. Một getter, hàm chuyển đổi DTO hoặc method nội bộ chỉ gọi một dòng code thường không tạo thêm thông tin vận hành. Hãy đo một hoạt động có ý nghĩa thay vì đo từng bước triển khai nhỏ.

## Chọn boundary theo lớp kiến trúc

Một ứng dụng Spring Boot thường có các lớp và điểm tích hợp sau:

| Vị trí | Câu hỏi cần trả lời | Cách instrumentation phù hợp |
|---|---|---|
| HTTP ingress | Request nào chậm, lỗi hoặc trả status nào? | Ưu tiên instrumentation HTTP server có sẵn của Spring Boot/Micrometer |
| Application service hoặc use case | Một nghiệp vụ như checkout hay reserve inventory mất bao lâu và có kết quả gì? | Tạo Observation thủ công ở điểm vào của use case khi tín hiệu mặc định chưa diễn đạt được nghiệp vụ |
| Domain object và hàm thuần | Quy tắc tính toán hoặc chuyển đổi dữ liệu có hoạt động độc lập cần theo dõi không? | Thường không instrument từng method; chỉ đo một phép tính lớn nếu có lý do vận hành rõ ràng |
| HTTP/RPC client | Dependency bên ngoài phản hồi chậm hoặc lỗi ở đâu? | Dùng instrumentation tự động của client khi được hỗ trợ; tạo Observation cho client/protocol tự viết |
| Database và repository | Truy vấn hoặc thao tác lưu trữ nào chậm? | Tận dụng JDBC/R2DBC instrumentation; thêm boundary nghiệp vụ khi cần biết use case nào thực hiện truy vấn |
| Messaging producer/consumer | Gửi hoặc xử lý message mất bao lâu, lỗi ở đâu? | Instrument ở ranh giới publish và consume; bảo đảm propagation context qua message khi hệ thống hỗ trợ |
| Scheduled job hoặc batch | Một lần chạy job/batch thành công, thất bại hay mất bao lâu? | Tạo boundary cho một lần chạy hoặc một chunk có ý nghĩa, tránh tạo observation cho từng bản ghi nếu không cần |

Spring Boot và Micrometer có thể tự động instrument một số thành phần như HTTP server, HTTP client, JDBC hoặc messaging tùy dependency, phiên bản và cấu hình. Phạm vi cụ thể phụ thuộc stack ứng dụng. Trước khi tự thêm Observation, hãy kiểm tra xem thành phần đó đã được instrument chưa để tránh tạo hai span hoặc hai metric cho cùng một hoạt động.

### Ingress: ranh giới nhận request

HTTP server instrumentation thường là điểm bắt đầu của trace. Nó ghi nhận request đến ứng dụng, route, method, status và thời gian xử lý theo convention của thư viện. Với Spring MVC hoặc WebFlux, nên giữ route template đã chuẩn hóa để request như `/orders/1001` và `/orders/1002` được nhóm vào cùng endpoint `/orders/{orderId}`.

Controller thường là adapter chuyển giao thức HTTP thành lời gọi application service. Nếu HTTP server instrumentation đã ghi nhận request, không cần tạo thêm một Observation chỉ để bao quanh toàn bộ method controller với cùng thông tin. Hãy tạo Observation ở use case nếu muốn một góc nhìn nghiệp vụ độc lập với giao thức.

### Application boundary: ranh giới use case

Đây thường là vị trí phù hợp để tạo Observation thủ công. Application service điều phối một hoạt động mà người dùng hoặc hệ thống quan tâm, chẳng hạn `checkout.submit`, `inventory.reserve` hoặc `invoice.issue`. Boundary này có thể bao gồm nhiều thao tác domain và lời gọi dependency, nhưng không cần tạo span thủ công cho từng method nội bộ.

Tên Observation nên mô tả hành động ổn định, không chứa ID hoặc dữ liệu đầu vào. Các tag low-cardinality nên thể hiện nhóm phân loại có ích như `channel`, `operation` hoặc `outcome`, với tập giá trị hữu hạn.

### Outbound boundary: ranh giới gọi dependency

Lời gọi sang payment gateway, inventory service hoặc hệ thống khác thường là nơi phát sinh độ trễ và lỗi. Nếu dùng `RestClient`, `WebClient`, HTTP client hoặc thư viện có instrumentation được Micrometer hỗ trợ, hãy ưu tiên instrumentation tích hợp để giữ đúng propagation và convention.

Nếu ứng dụng dùng client tự viết hoặc giao thức riêng, có thể bao quanh lời gọi bằng Observation thủ công. Chỉ tạo một Observation cho một lần gọi dependency có ý nghĩa. Không thêm một lớp span khác bao quanh client đã tự instrument nếu nó không bổ sung thông tin mới.

### Persistence boundary: ranh giới truy cập dữ liệu

Instrumentation JDBC hoặc R2DBC có thể cho biết truy vấn mất bao lâu và có lỗi hay không. Use-case Observation ở application service bổ sung bối cảnh nghiệp vụ: truy vấn đó xảy ra trong thao tác nào. Hai góc nhìn có mục đích khác nhau và có thể cùng tồn tại.

Tránh instrument mọi method repository theo cách thủ công nếu driver hoặc framework đã tạo span/metric tương ứng. Nếu một truy vấn nghiệp vụ đặc biệt cần đo riêng, hãy chọn tên ổn định và chỉ thêm tag phân loại có giới hạn; không đưa câu SQL đã nội suy, ID bản ghi hoặc tham số tùy ý vào metric tags.

## Ví dụ: instrument ở use-case boundary bằng Micrometer Observation

Giả sử ứng dụng có `CheckoutApplicationService`, một lớp điều phối quy trình checkout. Các lời gọi HTTP client và database bên trong đã được instrumentation tự động theo cấu hình của ứng dụng. Ta muốn có thêm một góc nhìn cho toàn bộ use case `checkout.submit` để biết thời gian xử lý và kết quả nghiệp vụ.

Ví dụ sau inject `ObservationRegistry` do Spring Boot cấu hình. `channel` được chuẩn hóa thành một tập giá trị nhỏ. `outcome` mô tả kết quả của use case. `orderId` vẫn được dùng cho nghiệp vụ nhưng không được thêm làm metric tag.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class CheckoutApplicationService {
    private final CheckoutWorkflow checkoutWorkflow;
    private final ObservationRegistry observationRegistry;

    public CheckoutApplicationService(
            CheckoutWorkflow checkoutWorkflow,
            ObservationRegistry observationRegistry) {
        this.checkoutWorkflow = checkoutWorkflow;
        this.observationRegistry = observationRegistry;
    }

    public CheckoutResult submit(CheckoutCommand command) {
        Observation observation = Observation
                .createNotStarted("checkout.submit", observationRegistry)
                .lowCardinalityKeyValue(
                        "channel", normalizeChannel(command.channel()));

        observation.start();
        try (Observation.Scope scope = observation.openScope()) {
            CheckoutResult result = checkoutWorkflow.execute(command);
            observation.lowCardinalityKeyValue(
                    "outcome", result.accepted() ? "accepted" : "rejected");
            return result;
        } catch (RuntimeException exception) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(exception);
            throw exception;
        } finally {
            observation.stop();
        }
    }

    private static String normalizeChannel(String rawChannel) {
        if (rawChannel == null || rawChannel.isBlank()) {
            return "unknown";
        }

        return switch (rawChannel.trim().toLowerCase(Locale.ROOT)) {
            case "web" -> "web";
            case "mobile" -> "mobile";
            case "partner" -> "partner";
            default -> "other";
        };
    }
}
```

Trong ví dụ:

- `checkout.submit` là tên ổn định của hoạt động nghiệp vụ, không phụ thuộc URL hay ID đơn hàng.
- `channel` chỉ có `web`, `mobile`, `partner`, `other` hoặc `unknown`.
- `outcome` chỉ có `accepted`, `rejected` hoặc `error`.
- `checkoutWorkflow.execute` điều phối nghiệp vụ; các dependency bên trong có thể tạo span con thông qua instrumentation đã cấu hình.
- `observation.error(exception)` ghi nhận exception cho Observation. Nội dung exception không được đưa vào low-cardinality tag.
- `observation.stop()` luôn chạy để kết thúc Observation, kể cả khi use case ném exception.

`Observation.Scope` đặt Observation hiện tại vào context trong lúc use case thực thi. Các thành phần hỗ trợ Micrometer Context Propagation có thể dùng context này để liên kết tín hiệu. Scope phải được đóng trước khi Observation dừng; try-with-resources trong ví dụ bảo đảm điều đó.

Nếu một kết quả từ chối là tình huống nghiệp vụ bình thường, hãy biểu diễn bằng `outcome=rejected` thay vì tự tạo exception chỉ để đánh dấu thất bại. Dùng `observation.error(...)` cho lỗi thực thi cần được ghi nhận là exception. Điều này giúp phân biệt tỷ lệ từ chối hợp lệ với tỷ lệ lỗi kỹ thuật.

## Kết hợp instrumentation tự động và thủ công

Instrumentation tự động và Observation do ứng dụng tạo phục vụ các góc nhìn khác nhau:

| Instrumentation | Ví dụ tên hoạt động | Giá trị mang lại |
|---|---|---|
| HTTP server tự động | `http.server.requests` hoặc span server theo convention của thư viện | Đo request ở biên ứng dụng, route, method, status và thời gian |
| Use case thủ công | `checkout.submit` | Đo một nghiệp vụ xuyên qua nhiều bước nội bộ |
| HTTP client tự động | Span/metric của client request | Đo từng lời gọi dependency và propagation trace |
| JDBC/R2DBC tự động | Span/metric của thao tác database | Tìm truy vấn hoặc thao tác persistence chậm |
| Custom Observation | `partner.message.publish` | Đo thành phần tự viết chưa có instrumentation tích hợp |

Một trace có thể có server span, use-case span và các client/database span con. Cấu trúc này giúp thu hẹp vị trí gây chậm. Tuy nhiên, nếu mỗi lớp đều tạo span cho cùng một hoạt động mà không có ý nghĩa riêng, trace sẽ dài và khó đọc. Hãy xem trace thực tế để xác nhận quan hệ cha-con và loại bỏ instrumentation trùng lặp.

Với metrics, cần chú ý rằng một Observation có thể được chuyển thành meter tùy handler và convention. Chỉ thêm Observation thủ công khi metric nghiệp vụ đó trả lời câu hỏi riêng. Tránh tạo metric cho mọi method vì số lượng meter và tổ hợp tag sẽ tăng mà không tạo thêm thông tin hữu ích.

## Chọn phạm vi thời gian cần đo

Boundary xác định đồng hồ bắt đầu và kết thúc, vì vậy cần quyết định rõ hoạt động nào nằm bên trong nó.

- Nếu đo toàn bộ use case, bắt đầu trước bước điều phối đầu tiên và kết thúc sau khi nghiệp vụ hoàn tất.
- Nếu đo riêng dependency, bao quanh đúng lời gọi dependency hoặc dùng instrumentation tự động.
- Nếu đo batch, chọn một lần chạy hoặc một chunk làm đơn vị đo; không mặc định tạo một Observation cho mỗi bản ghi.
- Nếu cần đo cả commit transaction, hãy đặt Observation bên ngoài lời gọi qua transactional proxy hoặc cấu hình thứ tự interceptor có chủ đích.

Điểm cuối của method được gắn `@Transactional` có thể xảy ra trước khi transaction interceptor hoàn tất commit, tùy thứ tự proxy/interceptor. Vì vậy, Observation được tạo bên trong method có thể không bao gồm thời gian commit. Nếu commit nằm trong phạm vi cần đo, hãy instrument ở lớp gọi bên ngoài transactional bean hoặc kiểm soát rõ thứ tự thực thi.

Đừng kéo dài Observation chỉ để đo một khoảng thời gian không thuộc cùng một hoạt động. Ví dụ, thời gian người dùng chờ giữa hai request không nên được đo bằng cách giữ một Observation mở trong suốt phiên làm việc. Hãy đo từng request hoặc job thực tế.

## Context và luồng bất đồng bộ

Trong luồng đồng bộ, mở scope quanh lời gọi giúp Observation hiện tại có mặt trong quá trình thực thi. Khi công việc chuyển sang thread khác, executor, `@Async` hoặc callback, context không phải lúc nào cũng tự truyền theo mọi cách triển khai.

Không giữ `Observation.Scope` đang mở qua một ranh giới bất đồng bộ rồi đóng nó từ thread khác. Thay vào đó, dùng cơ chế context propagation được hỗ trợ trong stack Spring/Micrometer, cấu hình executor phù hợp và kiểm tra trace sau khi chạy. Với message broker, context thường cần được truyền qua message headers theo convention của instrumentation tương ứng.

Nếu một thao tác bất đồng bộ có vòng đời riêng, hãy xác định boundary của việc gửi message và boundary của việc consume message. Producer kết thúc khi publish hoàn tất; consumer bắt đầu khi message được nhận và xử lý. Liên kết hai phía bằng trace context giúp điều tra xuyên dịch vụ mà không phải giữ một scope đồng bộ tồn tại trong thời gian chờ message.

## Thiết kế tên và tag cho Observation

Tên Observation nên mô tả hành động, ổn định qua các phiên bản và độc lập với dữ liệu cụ thể. Ví dụ:

| Nên dùng | Tránh dùng |
|---|---|
| `checkout.submit` | `checkout.order-93821` |
| `inventory.reserve` | `reserve.product-ABC` |
| `invoice.issue` | `invoice.issue.customer@example.com` |
| `partner.message.publish` | `partner.message.<random-id>` |

Tag low-cardinality nên được chọn theo câu hỏi vận hành: `channel`, `outcome`, `payment.type` hoặc `region` từ tập cấu hình giới hạn. Không dùng `orderId`, `customerId`, `requestId`, email, raw URL hoặc exception message làm metric tag. Nếu trace cần một định danh để điều tra một giao dịch cụ thể, hãy cân nhắc high-cardinality attribute theo chính sách dữ liệu và khả năng của tracing backend.

Giữ key nhất quán giữa các use case. Nếu cùng một khái niệm lúc được gọi là `channel`, lúc là `source`, lúc là `clientType`, việc tổng hợp dashboard và so sánh giữa các operation sẽ khó hơn. Định nghĩa từ vựng chung giúp instrumentation trở thành một phần nhất quán của kiến trúc.

## Những lỗi thường gặp khi chọn boundary

### Instrument từng method nhỏ

Tạo span cho getter, mapper hoặc helper làm trace có nhiều node nhưng không giải thích được hành vi hệ thống. Chọn use case hoặc lời gọi dependency có ý nghĩa thay vì từng method nội bộ.

### Chỉ instrument controller

HTTP server metrics cho biết request tổng thể nhưng chưa chỉ ra use case nào hoặc dependency nào chiếm thời gian. Bổ sung application boundary và dùng instrumentation client/database để tạo phân cấp cần thiết.

### Tạo Observation thủ công quanh thành phần đã tự instrument

Đo trùng HTTP client hoặc JDBC có thể tạo span lặp và metric khó hiểu. Kiểm tra instrumentation đang bật trước khi thêm lớp đo thủ công.

### Đo boundary quá rộng

Gộp nhiều job độc lập hoặc toàn bộ vòng đời ứng dụng vào một Observation khiến thời gian và lỗi khó quy về một đơn vị hành động. Chia theo request, use case, lần chạy job hoặc message.

### Đo boundary quá hẹp

Đo riêng từng câu lệnh nhưng không có Observation của use case khiến người vận hành khó biết câu lệnh đó phục vụ nghiệp vụ nào. Kết hợp một boundary nghiệp vụ với span kỹ thuật khi cả hai cung cấp thông tin riêng.

### Đưa dữ liệu đầu vào vào tên hoặc tag

Tên và tag chứa ID làm cardinality tăng, gây tốn tài nguyên và có thể lộ dữ liệu. Giữ tên ổn định và chuẩn hóa tag theo allowlist.

### Bỏ quên transaction hoặc async context

Observation có thể kết thúc trước commit hoặc mất liên kết khi chuyển thread. Xác định phạm vi thời gian mong muốn và kiểm thử propagation qua các ranh giới thực tế.

## Kiểm chứng instrumentation

Sau khi đặt boundary, hãy xác nhận cả ý nghĩa và hành vi kỹ thuật của telemetry:

1. Gọi một use case thành công và kiểm tra Observation/trace có tên ổn định, thời gian hợp lý và `outcome` đúng.
2. Tạo tình huống từ chối nghiệp vụ và xác nhận nó được phân loại là `rejected`, không bị tính nhầm thành exception nếu đó là kết quả bình thường.
3. Tạo lỗi kỹ thuật và xác nhận exception được gắn vào Observation, đồng thời tag vẫn thuộc tập giá trị đã định nghĩa.
4. Gọi dependency chậm hoặc giả lập lỗi để kiểm tra span client xuất hiện dưới use-case span khi instrumentation được hỗ trợ.
5. Kiểm tra một truy vấn database để xác nhận instrumentation tự động không bị tạo trùng.
6. Gửi nhiều request với ID khác nhau và xác nhận số lượng metric series không tăng theo từng ID.
7. Với luồng bất đồng bộ hoặc messaging, kiểm tra trace context có được truyền và liên kết đúng qua thread hoặc message boundary.
8. Nếu thời gian đo phải bao gồm commit transaction, xác nhận span kết thúc sau khi commit hoàn tất.

Có thể dùng test handler của Micrometer Observation hoặc meter registry trong test để kiểm tra tên, tag và trạng thái Observation. Ở môi trường chạy, kiểm tra endpoint metrics, trace backend và log có correlation context. Chỉ đánh giá instrumentation là hoàn tất khi trace thể hiện đúng ranh giới và dữ liệu giúp trả lời câu hỏi vận hành đã đặt ra.

## Checklist trước khi phát hành

- [ ] Mỗi Observation tương ứng với một hoạt động nghiệp vụ hoặc kỹ thuật có ý nghĩa.
- [ ] Boundary có điểm bắt đầu, điểm kết thúc và đơn vị đo rõ ràng.
- [ ] Đã kiểm tra instrumentation tự động trước khi thêm Observation thủ công.
- [ ] Use-case boundary bổ sung bối cảnh mà HTTP/client/database instrumentation chưa thể hiện.
- [ ] Tên Observation ổn định, không chứa ID hoặc dữ liệu request.
- [ ] Low-cardinality tags có tập giá trị hữu hạn và được chuẩn hóa.
- [ ] Kết quả nghiệp vụ bình thường được phân biệt với exception kỹ thuật.
- [ ] Scope được đóng trước khi Observation dừng.
- [ ] Transaction và async/message context được xử lý đúng phạm vi.
- [ ] Trace không có span trùng hoặc quá nhỏ; metrics không có cardinality bất thường.

## Kết luận

Đặt instrumentation ở đúng boundary giúp telemetry phản ánh cấu trúc thực của ứng dụng. Hãy tận dụng instrumentation tự động ở HTTP, client, database và messaging khi có hỗ trợ; bổ sung Observation thủ công ở application/use-case boundary để thể hiện nghiệp vụ. Giữ tên và tag ổn định, xác định chính xác phạm vi thời gian, đồng thời kiểm tra transaction và context propagation để trace, metrics và logs hỗ trợ điều tra một cách nhất quán.
