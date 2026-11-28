# Data minimization – Tối thiểu hóa dữ liệu trong thiết kế và security assurance

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **data minimization (tối thiểu hóa dữ liệu)** và phân biệt với purpose limitation, retention, masking, pseudonymization, anonymization, access control và mã hóa.
- Xác định **mục đích xử lý rõ ràng** rồi chứng minh vì sao mỗi trường dữ liệu, tập bản ghi, độ chi tiết, khoảng thời gian và điểm sao chép là cần thiết.
- Nhận diện dữ liệu bị thu thập hoặc lan truyền quá mức trong form, API, database, message queue, log/trace, analytics, export, backup và tích hợp bên thứ ba.
- Thiết kế **security controls có thể kiểm tra** cho Java/Spring Boot, phân tách DTO, giới hạn truy vấn, dữ liệu trong log và thông điệp bất đồng bộ.
- Đánh giá rủi ro khi tối thiểu hóa không đúng: lộ bí mật, vượt ranh giới tenant, tăng blast radius, sử dụng sai mục đích hoặc xóa nhầm thông tin còn cần thiết.
- Xây dựng **chuỗi bằng chứng** từ mục tiêu bảo mật và risk scenario đến requirements, control implementation, test, runtime evidence, finding và remediation/retest.
- Duy trì data minimization trong thay đổi schema, triển khai tính năng mới, dữ liệu phục vụ vận hành, kiểm toán và vòng đời phát triển liên tục.

## 1. Data minimization là gì?

**Data minimization** là nguyên tắc và thực hành **giới hạn dữ liệu được thu thập, tạo ra, sử dụng, truy cập, chia sẻ và giữ lại ở mức phù hợp, liên quan và cần thiết cho mục đích xử lý đã xác định**. Tối thiểu hóa không đồng nghĩa luôn chọn ít trường nhất bằng mọi giá; điều quan trọng là **có thể giải thích và kiểm chứng nhu cầu sử dụng dữ liệu**.

Ví dụ: một khách hàng yêu cầu tra cứu trạng thái giao hàng. API hỗ trợ chỉ cần xác định **đơn hàng được quyền truy cập** và trả về trạng thái, thời điểm cập nhật. Nếu API lấy cả số thẻ thanh toán, địa chỉ thanh toán đầy đủ, lịch sử truy cập và số điện thoại rồi gửi sang ứng dụng hỗ trợ, đó có thể là **dữ liệu thừa** cho chức năng tra cứu trạng thái.

Trong module **SECURITY_SECURITY_ASSURANCE**, câu hỏi không dừng ở “chúng tôi tuân thủ minimization”. Phải đánh giá **có bằng chứng** hệ thống đáp ứng mục tiêu bảo mật bằng cách nối:
**risk assessment → data requirements → security controls → tests → audit/evidence → findings → remediation và retest**. Một tài liệu kiến trúc ghi “chỉ sử dụng dữ liệu cần thiết” không chứng minh response production, queue message hoặc log thật đang làm đúng.

### Tối thiểu hóa trên nhiều chiều

| Chiều cần giảm | Câu hỏi đúng | Ví dụ |
| --- | --- | --- |
| **Thuộc tính/trường** | Có cần từng trường dữ liệu này không? | API chỉ trả `orderId` và `status`, không trả số điện thoại |
| **Số lượng bản ghi** | Có cần tất cả khách hàng hay chỉ tập liên quan? | Truy vấn một đơn được ủy quyền, không xuất toàn bảng |
| **Độ chi tiết** | Có thể dùng giá trị tổng hợp/phân nhóm thay dữ liệu gốc không? | Thống kê theo ngày thay từng giao dịch cá nhân |
| **Độ chính xác** | Có cần ngày giờ/địa chỉ tới mức chi tiết nào? | Tháng sinh thay ngày sinh đầy đủ nếu mục tiêu chỉ cần nhóm tuổi |
| **Tần suất** | Mỗi request phải gửi lại dữ liệu hay chỉ khi cần? | Không đính kèm profile vào mọi event trạng thái |
| **Khoảng thời gian** | Dữ liệu cần tồn tại bao lâu tại mỗi nơi? | Xóa file export tạm theo lịch riêng |
| **Số bản sao/điểm nhận** | Hệ thống nào thực sự cần một bản sao? | Không chép toàn bộ hồ sơ vào queue/log |
| **Số chủ thể được tiếp cận** | Những dịch vụ/nhân sự nào phải thấy dữ liệu? | Chỉ service có nhiệm vụ được đọc trường nhạy cảm |
| **Dữ liệu phái sinh** | Derived data có thể tái liên kết hoặc tái nhận dạng không? | Embeddings, hash, feature vector cũng cần phân loại |
| **Khả năng liên kết** | Có cần một ID toàn cục trên mọi hệ thống không? | Dùng ID cục bộ/phạm vi mục đích khi thích hợp |

Vì dữ liệu đi qua nhiều ranh giới, **minimization không chỉ là thiết kế giao diện form**. Một ứng dụng không yêu cầu số điện thoại ở form mới nhưng lại ghi nguyên payload cũ vào log cũng chưa đạt mục tiêu.

## 2. Phân biệt với những biện pháp bảo vệ dữ liệu khác

| Khái niệm | Mục tiêu chính | Quan hệ với minimization |
| --- | --- | --- |
| **Purpose limitation** | Sử dụng dữ liệu cho mục đích đã xác định, hợp lệ trong bối cảnh áp dụng | Mục đích là cơ sở để quyết định dữ liệu nào thực sự cần |
| **Data minimization** | Giảm loại, lượng, mức chi tiết, đường lan truyền và phạm vi xử lý | Phải áp dụng trong toàn vòng đời |
| **Retention limitation** | Không giữ dữ liệu lâu hơn điều kiện/mục đích/nghĩa vụ được phê duyệt | Một phần liên quan tới chiều **thời gian**, không thay giảm dữ liệu khi thu |
| **Encryption** | Bảo vệ tính bí mật của dữ liệu khi lưu hoặc truyền | Dữ liệu được mã hóa vẫn có thể là dữ liệu thu thập thừa |
| **Access control** | Giới hạn ai có thể sử dụng dữ liệu và hành động nào | Không hợp thức hóa việc thu thập/lan truyền không cần thiết |
| **Masking/redaction** | Che/bỏ giá trị nhạy cảm tại một đầu ra hoặc bản sao | Cần kiểm tra nguồn gốc và nơi khác còn dữ liệu nguyên |
| **Pseudonymization** | Thay định danh trực tiếp nhưng còn khả năng liên kết lại | Dữ liệu có thể vẫn nhạy cảm và thuộc nghĩa vụ bảo vệ |
| **Anonymization** | Làm dữ liệu không còn nhận dạng được theo tiêu chí/khả năng thực tế | Cần đánh giá rủi ro tái nhận dạng; không mặc định chỉ đổi tên là ẩn danh |
| **Aggregation** | Tổng hợp nhiều bản ghi thành số liệu | Có thể giảm chi tiết, nhưng nhóm quá nhỏ hoặc kết hợp dữ liệu khác vẫn gây lộ |
| **Data loss prevention** | Phát hiện/ngăn dữ liệu rời phạm vi không cho phép | Hỗ trợ phát hiện nhưng không thay quyết định có nên thu dữ liệu ngay từ đầu |
| **Deletion/purge** | Xóa khi không còn lý do giữ và đúng điều kiện | Bước kết thúc; không bù được thiệt hại do đã chia sẻ dữ liệu thừa |

**Mã hóa toàn bộ payload không làm payload trở thành tối thiểu.** Nếu một microservice chỉ cần trạng thái đơn hàng mà nhận cả hồ sơ khách hàng, TLS chỉ bảo vệ đường truyền; dữ liệu vẫn bị lan truyền đến một bên nhận không cần thiết.

**Tối thiểu hóa cũng không thay xác thực/phân quyền.** Một API chỉ trả hai trường vẫn có thể gây lộ thông tin nếu người dùng tenant A đọc được đơn hàng tenant B.

### Nguyên tắc “cần thiết” có điều kiện

Có những dữ liệu ít được dùng nhưng có lý do phải giữ, như bằng chứng giao dịch theo nghĩa vụ áp dụng, thông tin đối soát hoặc log bảo mật phục vụ điều tra. Không nên xóa hoặc cắt trường theo cảm tính nếu sẽ phá hỏng tính toàn vẹn chứng cứ hoặc khả năng khôi phục. Việc quyết định phải xét **nghĩa vụ, mục đích, rủi ro và quyền của người có thẩm quyền**.

Bài học không quy định một thời hạn hoặc căn cứ pháp lý chung cho mọi hệ thống. Khi áp dụng quy định quyền riêng tư hoặc nghĩa vụ ngành, cần đối chiếu văn bản, phạm vi và tư vấn của người phụ trách Legal/Privacy/Compliance thích hợp.

## 3. Bắt đầu bằng mục đích, không bắt đầu bằng schema

Một bảng `customers` có 35 cột không có nghĩa mọi service xử lý khách hàng đều cần 35 cột. Quy trình đúng nên đi từ **business use case và mục đích** tới tập dữ liệu tối thiểu.

### Các câu hỏi phải trả lời cho từng trường

1. **Mục đích rõ ràng là gì?** Ví dụ hiển thị trạng thái vận chuyển, không phải “phục vụ phân tích tương lai”.
2. **Tác vụ nào dùng trường này?** Cần ở bước xử lý nào? Có dùng thật trong code không?
3. **Không có trường này, tác vụ có còn hoàn thành đúng không?** Có đường thay thế ít dữ liệu hơn không?
4. **Có thể dùng dữ liệu ít chi tiết hơn?** Nhóm tuổi, tổng giá trị hoặc cờ đúng/sai thay giá trị gốc?
5. **Ai cần xem và trong bao lâu?** Backend có quyền không đồng nghĩa UI, log, nhà cung cấp đều cần.
6. **Dữ liệu đến từ đâu và được cập nhật thế nào?** Có thể lấy từ nguồn đáng tin khi thật sự cần, thay vì lưu thêm bản sao?
7. **Rủi ro nếu bị lộ hoặc sai?** Tài sản, tenant, hành vi gian lận, độ nhạy cảm, khả năng kết hợp.
8. **Có ràng buộc phải lưu hoặc kiểm tra không?** Chỉ giữ đúng trường/hồ sơ cần cho nghĩa vụ đó.
9. **Ai xác nhận nhu cầu?** Data Owner, Product Owner, Security, Legal/Privacy tùy phạm vi.
10. **Bằng chứng nào chứng minh quy tắc đang đúng?** Contract, query, test, schema, runtime sampling đã làm sạch.

### Purpose–Data Matrix

Giả sử chức năng chăm sóc khách hàng có ba use case:

| Trường dữ liệu | Kiểm tra trạng thái đơn | Xác minh khi thay địa chỉ giao | Điều tra gian lận được phê duyệt |
| --- | --- | --- | --- |
| `orderId` | Cần | Cần | Có thể cần |
| `orderStatus` | Cần | Có thể cần | Tùy kịch bản |
| `deliveryAddress` | Không cần để chỉ hiển thị trạng thái | Cần theo quy trình bảo vệ phù hợp | Chỉ nếu nằm trong phạm vi điều tra |
| `customerPhone` | Không cần mặc định | Có thể cần cho kênh giao nhận cụ thể | Chỉ theo phạm vi được phê duyệt |
| `paymentCardNumber` | Không cần | Không cần | Không mặc định; cần giải pháp/nguồn dữ liệu có căn cứ đặc biệt |
| `createdAt` | Có thể cần bản rút gọn | Tùy workflow | Theo câu hỏi điều tra |
| `internalFraudScore` | Không cần gửi ra UI | Không mặc định | Chỉ người/hệ thống được cấp quyền và mục đích phù hợp |

**“Cần” không tự cho phép chia sẻ**: mỗi trường vẫn phải được kiểm tra theo quyền của người gọi, mục đích cụ thể và chính sách dữ liệu. Mục đích mới hoặc dữ liệu mới cần review, không tự dựa vào chấp thuận cũ.

### Kết quả mong muốn

Mỗi field cần có **decision record**: giữ, bỏ, giảm chi tiết, chuyển tính toán vào nơi khác, chỉ truy cập khi được ủy quyền, hoặc đánh giá thêm. Ghi rationale và người có trách nhiệm, tránh quyết định dựa hoàn toàn vào cảm giác “trường này có lẽ hữu ích”.

## 4. Data inventory và data flow: tìm dữ liệu bị nhân bản

Muốn tối thiểu hóa, trước tiên phải biết dữ liệu tồn tại ở đâu và **đi qua những nơi nào**. Chỉ nhìn database chính thường bỏ sót log, tracing, cache, event bus, data lake, backup, file export và tích hợp.

### DFD cho use case “xem trạng thái đơn hàng”

~~~mermaid
flowchart TD
    U["Người dùng tenant A/B"] --> GW["API Gateway"]
    GW --> API["Spring Boot orders-api"]
    API --> DB[("Orders Database")]
    API --> CACHE[("Cache trạng thái")]
    API --> LOG["Log / Trace / Metrics"]
    API --> EVENT["Event Bus"]
    EVENT --> ANALYTICS["Analytics / Warehouse"]
    API --> VENDOR["Đối tác giao nhận"]
    DB --> BACKUP[("Backup / Replica")]
    API --> U
~~~

**Đánh dấu ranh giới tin cậy**: client–API, tenant A–tenant B, ứng dụng–database, ứng dụng–đối tác, production–analytics, production–log collector, dữ liệu sống–backup/DR. Với mỗi mũi tên, hỏi:

- Payload **thực tế** là gì? Chỉ `orderId/status` hay toàn bộ `Customer`?
- Bên nhận làm **hành động gì** với trường đó? Có căn cứ cho mọi field không?
- Có cache/retry/dead-letter queue/replay/backup chứa bản gốc không?
- Bản sao có vòng đời, owner và quyền khác nguồn chính không?
- Có dùng dữ liệu thật ở non-prod hoặc công cụ quan sát bên thứ ba không?
- Có đủ bằng chứng về luồng ở **phiên bản production hiện chạy** hay chỉ tài liệu thiết kế?

### Inventory cấp luồng

| Flow ID | Nguồn → đích | Mục đích | Dữ liệu cần thiết | Dữ liệu thừa cần kiểm tra |
| --- | --- | --- | --- | --- |
| FLOW-01 | Browser → orders-api | Xem trạng thái | ID đơn từ route; identity từ session hợp lệ | Số điện thoại/địa chỉ do client gửi không cần |
| FLOW-02 | orders-api → database | Tra cứu đơn được phép | ID, tenant/owner và trạng thái | `SELECT *` kéo cả payment, address, notes |
| FLOW-03 | orders-api → browser | Trả trạng thái | ID, status, timestamp cần thiết | Trả nguyên Entity/Customer profile |
| FLOW-04 | orders-api → logs | Truy vết vận hành | Correlation ID, action, outcome, tối thiểu metadata | JSON body, Authorization header, PII |
| FLOW-05 | orders-api → analytics | Số liệu hiệu suất | Event/aggregate cần cho chỉ số đã duyệt | Toàn bộ địa chỉ và hồ sơ khách |
| FLOW-06 | orders-api → vendor | Yêu cầu giao nhận | Chỉ dữ liệu cần hoàn tất vận chuyển | Lịch sử mua, scoring nội bộ, token user |
| FLOW-07 | production → backup | Khôi phục theo chính sách | Tập dữ liệu trong phạm vi backup đã duyệt | Các dump/test copy không owner và không hạn |

Đây là bảng **đề xuất mô hình**. Khi đánh giá, cần đối chiếu code, database query, message schema, middleware, storage lifecycle và **payload đã làm sạch** từ luồng thực tế được phép quan sát.

## 5. Thiết kế theo “minimum necessary”, không chỉ theo “minimum technically possible”

### 5.1. Chỉ thu thập khi có nhu cầu đã được xác định

Không đặt trường bổ sung trong form chỉ vì “có thể cần cho tương lai”. Nếu chức năng tra cứu đơn dùng định danh người dùng đã có từ phiên đăng nhập, không yêu cầu nhập lại email, ngày sinh hoặc số giấy tờ nếu không có mục đích độc lập được phê duyệt.

**Progressive collection** có thể giúp: thu dữ liệu ở đúng thời điểm thực hiện tác vụ cần nó, thay vì thu mọi thứ khi đăng ký. Nhưng không dùng “thu sau” để né yêu cầu phải có mục đích/điều kiện áp dụng.

### 5.2. Không sao chép dữ liệu chỉ để tránh thiết kế API

Một worker cần biết **job ID, loại công việc, tài nguyên đã được cấp quyền và thông tin xử lý tối thiểu**. Nó thường không cần nhận nguyên customer profile trong queue. Nếu phải tra cứu thêm, cần đánh giá rủi ro phát sinh vì request liên dịch vụ và thiết kế authorization hợp lệ.

Không có một cách đúng tuyệt đối giữa **mang dữ liệu trong message** và **tham chiếu dữ liệu bằng ID**. Tham chiếu có thể giảm lượng dữ liệu ở queue nhưng tạo yêu cầu về tính sẵn sàng, consistency và quyền đọc ở downstream. Phải đánh giá mục tiêu nghiệp vụ và rủi ro chứ không tự tuyên bố pattern nào luôn an toàn.

### 5.3. Chỉ hiển thị dữ liệu cần cho vai trò hiện tại

Một API sử dụng cùng Entity cho nhân viên hỗ trợ, khách hàng và admin dễ trả thừa trường. Thiết kế **response DTO riêng theo use case/actor** giúp làm rõ hợp đồng dữ liệu. Tuy nhiên, DTO có ít field vẫn cần kiểm tra **được phép xem bản ghi nào**.

### 5.4. Giảm độ chính xác khi phù hợp

Nếu một biểu đồ chỉ cần số lượng khách theo vùng rộng, có thể dùng vùng thay địa chỉ chính xác. Nếu đo mức hoạt động theo ngày, không cần timestamp tới millisecond cho mọi bản ghi chuyển sang analytics. Nhưng giảm độ chính xác phải được kiểm tra có làm sai nghiệp vụ hoặc gây bias không.

### 5.5. Cảnh giác với dữ liệu dễ tái liên kết

Thay email bằng một hash lặp lại ở mọi service có thể vẫn cho phép **liên kết hành vi của cùng một người** và có nguy cơ bị suy đoán nếu không có bảo vệ phù hợp. ID giả danh nhưng dùng chung ở logs, analytics và CRM cũng có thể hình thành hồ sơ chi tiết.

Một thiết kế minimization cần xét cả **join keys, metadata, thời gian và dữ liệu ngoại lai**, không chỉ các cột dễ nhận biết như `fullName`, `email`.

## 6. Kiểm soát dữ liệu ở API Java/Spring Boot

Một anti-pattern phổ biến là cho framework deserialize trực tiếp toàn bộ JSON vào JPA entity, sau đó serialize entity trở lại. Điều đó gây nguy cơ **over-posting/mass assignment**, trả thừa field và làm luồng dữ liệu khó audit.

### 6.1. Thiết kế hợp đồng API tối thiểu

Use case: khách hàng đã đăng nhập tạo yêu cầu hỗ trợ về đơn hàng. Chỉ cần `orderId`, loại vấn đề và mô tả rút gọn. Identity khách được lấy từ **security context đã được xác thực**, không lấy từ `userId` do client tự khai.

Request được duyệt:

~~~json
{
  "orderId": "ORD-132",
  "category": "DELIVERY_DELAY",
  "message": "Đơn chưa được giao theo lịch"
}
~~~

Response được duyệt:

~~~json
{
  "ticketId": "TCK-883",
  "status": "OPEN"
}
~~~

Không cần trả nguyên customer entity, địa chỉ giao hàng, token, phương thức thanh toán hoặc ghi payload vào log để hoàn thành tác vụ.

### 6.2. Ví dụ DTO với validation và boundary rõ ràng

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record NewSupportTicketRequest(
        @NotBlank String orderId,
        @NotBlank String category,
        @NotBlank @Size(max = 2000) String message) {}

public record NewSupportTicketResponse(
        String ticketId,
        String status) {}
~~~

Controller minh họa:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/support/tickets")
public class SupportTicketController {
    private final SupportTicketService tickets;

    public SupportTicketController(SupportTicketService tickets) {
        this.tickets = tickets;
    }

    @PostMapping
    public ResponseEntity<NewSupportTicketResponse> create(
            @Valid @RequestBody NewSupportTicketRequest request,
            Authentication authenticatedActor) {

        // Subject lấy từ Authentication đã được Spring Security xác minh;
        // không dùng trường userId do client đưa trong request.
        String actorId = authenticatedActor.getName();
        String ticketId = tickets.createForAuthorizedOrder(
                actorId,
                request.orderId(),
                request.category(),
                request.message());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new NewSupportTicketResponse(ticketId, "OPEN"));
    }
}
~~~

Ví dụ giả định **`SupportTicketService` có phương thức và logic authorization phù hợp**, Spring Validation được cấu hình và endpoint đã được bảo vệ bởi Spring Security. Đoạn code này là **mảnh thiết kế minh họa**, không phải ứng dụng độc lập có thể chạy ngay.

**Điểm mạnh của DTO:** API contract công khai chỉ chứa các trường được lựa chọn. **Giới hạn cần nhớ:** một field `message` dạng tự do vẫn có thể chứa dữ liệu cá nhân hoặc bí mật do người dùng chủ động điền. Cần kiểm soát UI guidance, kích thước, quyền truy cập, xử lý nội dung và thời hạn phù hợp; không khẳng định hệ thống đã tối thiểu tuyệt đối chỉ vì DTO có ba field.

### 6.3. Tránh mass assignment và field ngoài hợp đồng

Nếu client gửi thêm `isAdmin`, `customerPhone`, `paymentToken`, chương trình cần có **chính sách xử lý field ngoài hợp đồng** rõ. DTO giới hạn các giá trị service chủ động dùng, nhưng việc request chứa trường lạ được **im lặng bỏ qua hay bị từ chối** còn phụ thuộc cấu hình JSON.

Trong ứng dụng Spring Boot sử dụng Jackson, một lựa chọn để **từ chối thuộc tính không biết** là bật tính năng thích hợp trong phạm vi được kiểm thử:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JsonContractConfiguration {
    @Bean
    Jackson2ObjectMapperBuilderCustomizer strictInputFields() {
        return builder -> builder.featuresToEnable(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
    }
}
~~~

Cấu hình ở ví dụ tác động đến các mapper do builder tương ứng tạo ra; nếu ứng dụng có custom mapper, nhiều client hoặc API tương thích cũ, phải **xác minh phạm vi thực** và đánh giá ảnh hưởng. Chính sách có thể thay bằng schema validation phù hợp; điều quan trọng là **field được client đưa không âm thầm trở thành quyền hay dữ liệu lưu thêm**.

### 6.4. Dùng response DTO, không serialize Entity

Không trả trực tiếp `Customer` hoặc `OrderEntity` chỉ vì framework có thể chuyển chúng thành JSON. Một Entity có thể chứa:
- Các trường quản trị như `fraudFlag`, `internalNote`.
- Quan hệ JPA được lazy/eager load.
- Địa chỉ, email, số điện thoại, token đã băm hoặc metadata kỹ thuật.
- Trường mới được thêm trong tương lai mà API contract không dự định công bố.

Response DTO phải có **allowlist trường công khai** theo mục đích và test chống phát tán dữ liệu khi Entity được mở rộng.

## 7. Query-level minimization: lấy đúng hàng và đúng cột

Ngay cả khi API response tối thiểu, backend có thể **đọc quá nhiều** từ database, đưa dữ liệu nhạy cảm vào memory, ORM cache hoặc log khi debug. Cần giảm dữ liệu **trên đường truy vấn** nếu phù hợp.

### 7.1. So sánh truy vấn

Cách dễ gây over-fetch:

~~~sql
-- Minh họa anti-pattern: lấy toàn bộ cột/hàng không cần thiết
SELECT *
FROM orders;
~~~

Cách gần mục đích “xem trạng thái một đơn” hơn:

~~~sql
-- tenantId phải xuất phát từ trusted authorization context.
-- orderId được parameter binding, không nối chuỗi SQL tùy ý.
SELECT o.id, o.status, o.last_updated_at
FROM orders o
WHERE o.id = :orderId
  AND o.tenant_id = :tenantId;
~~~

**Chưa đủ để kết luận an toàn:** `tenantId` nếu lấy trực tiếp từ header client không được kiểm chứng thì bộ lọc này có thể bị bypass theo nghiệp vụ. Cần dùng danh tính đã xác thực và policy xác định actor thuộc tenant nào, và kiểm tra object ownership/role theo yêu cầu.

### 7.2. Projection DTO trong Spring Data JPA

Giả sử domain model và repository đã được định nghĩa:

~~~java
public record OrderStatusView(
        String id,
        String status,
        java.time.Instant lastUpdatedAt) {}
~~~

Một repository có thể sử dụng query projection dựa trên mapping cụ thể:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface OrderRepository extends JpaRepository<OrderEntity, String> {
    @Query("""
        select new com.example.orders.OrderStatusView(
            o.id, o.status, o.lastUpdatedAt)
        from OrderEntity o
        where o.id = :orderId and o.tenantId = :tenantId
        """)
    Optional<OrderStatusView> findStatusForTenant(
        @Param("orderId") String orderId,
        @Param("tenantId") String tenantId);
}
~~~

Tên package, Entity, kiểu của `status` và các property trong code là **giả định**. Khi triển khai thật phải đồng bộ mapping/query với JPA model. **Không dùng ví dụ để cho phép client tự quyết định tenantId**; service gọi repository cần có bước authorization từ trusted context.

Projection là cách minh bạch hóa các cột được đọc, không tự chứng minh truy vấn giới hạn đủ hàng, không bảo vệ được toàn bộ database qua các đường truy vấn khác và không thay cơ chế phân quyền.

### 7.3. Đừng nhầm “không trả” với “không xử lý”

Một API có thể load Entity lớn rồi map sang DTO nhỏ. Điều này giảm trường truyền ra client, nhưng backend vẫn có thể truy cập các cột không cần thiết. Với dữ liệu nhạy cảm, nên xem **data access patterns, query projections, lưu cache, ORM dirty tracking, query logs và các đường xuất khác**. Tối ưu hóa hiệu năng có thể đồng thời giúp minimization, nhưng phải đánh giá trade-off nếu thêm truy vấn làm tăng quyền hay tải hệ thống.

## 8. Minimization trong message, queue và event-driven architecture

Một message thường đi qua broker, retry storage, dead-letter queue (DLQ), consumer logs và nhiều subscriber. Do đó một field nhạy cảm đưa vào event có thể được **nhân bản rộng hơn dự kiến**.

### 8.1. Anti-pattern và thiết kế phù hợp mục đích

Event quá rộng:

~~~json
{
  "eventType": "OrderStatusChanged",
  "order": {
    "id": "ORD-132",
    "status": "SHIPPED",
    "customerName": "Example Customer",
    "customerEmail": "example@invalid.test",
    "phone": "000000",
    "billingAddress": "example only",
    "paymentDetails": "not-for-this-event"
  }
}
~~~

Event tối thiểu cho mục đích cập nhật trạng thái:

~~~json
{
  "eventType": "OrderStatusChanged",
  "eventId": "EVT-923",
  "orderId": "ORD-132",
  "newStatus": "SHIPPED",
  "occurredAt": "2026-11-28T00:00:00Z"
}
~~~

Đây là mẫu về **trường dữ liệu**, không phải khẳng định ai nhận event đều được phép nhìn `orderId`. Nếu người nhận cần biết tenant/ownership, phải thiết kế context đã được bảo vệ và kiểm tra quyền tại mỗi trust boundary.

### 8.2. Event schema không nên là toàn bộ entity

Một schema event cần có:
- **Business purpose và consumer được phê duyệt**.
- Danh sách field allowlist; phân loại nhạy cảm và rationale.
- Versioning và review khi thêm trường.
- Owner và time-to-live cho message, retry, DLQ, replay.
- Quyền consumer theo topic/queue, không chỉ producer.
- Cách xử lý schema evolution, log, tracing và bản sao phân tích.
- Bằng chứng về dữ liệu thật ở đường production được quan sát có kiểm soát.

Không nên gửi dữ liệu cá nhân chỉ để **“consumer nào đó có thể cần”**. Nếu consumer mới cần dữ liệu, thực hiện review mục đích và cách cấp quyền, cân nhắc API truy xuất có kiểm soát hoặc topic/chế độ phân phối riêng.

### 8.3. Message reference cũng cần bảo vệ

Nếu event chỉ gửi `orderId` để downstream tra cứu, identity của consumer phải có quyền **đọc đúng đơn**. Không dùng service account wildcard rồi nói minimization đã đạt vì message ngắn. Giảm dữ liệu ở queue và phân quyền tại API/database là **hai control khác nhau**.

## 9. Logs, tracing, metrics và hỗ trợ vận hành

Hệ thống quan sát thường là nguồn dữ liệu sao chép ít được kiểm soát hơn database nguồn, đặc biệt nếu nhiều đội được xem hoặc có tích hợp SaaS.

### 9.1. Những gì nên tránh đưa vào log

- Raw `Authorization` header, access token, refresh token, API key, password, cookie phiên.
- JSON request/response chứa thông tin định danh, địa chỉ, dữ liệu giao dịch hoặc nội dung tin nhắn không cần cho điều tra.
- Tham số query chứa dữ liệu nhạy cảm; URL có token.
- Stack trace chứa payload/SQL parameters hoặc thông tin ngoài mục tiêu giám sát.
- Full object dump qua `toString()`, log ORM, debug middleware và trace attributes tự động.
- Nội dung file import/export hoặc dữ liệu đưa vào AI/analytics phục vụ debug khi không có căn cứ.

Không phải mọi log có `userId` đều bị cấm; cần xác định **mục đích an ninh/khả năng truy vết**, dữ liệu tối thiểu, quyền, hạn lưu và giải pháp giảm khả năng liên kết khi phù hợp.

### 9.2. Ví dụ logging có chủ đích

Tránh:

~~~java
// Anti-pattern: object có thể chứa thông tin cá nhân hoặc bí mật.
log.info("Create ticket request: {}", request);
~~~

Ưu tiên log **sự kiện và kết quả** với metadata cần thiết:

~~~java
// Giá trị traceId cần được lấy từ tracing context được kiểm soát.
// Không đưa message hoặc token vào event.
log.info("support_ticket_created traceId={} category={} result={}",
        traceId, validatedCategory, "success");
~~~

Trong code thật, `traceId` và `validatedCategory` phải được định nghĩa và bảo đảm không chứa dữ liệu nhạy cảm không cần thiết. Nếu `category` là trường do client đưa, cần kiểm tra/chuẩn hóa thành tập giá trị được duyệt. Không được coi log ví dụ là “bảo mật” chỉ vì không có email trong format string.

### 9.3. “Redaction” có giới hạn

Log pipeline redaction là một lớp bảo vệ hữu ích, nhưng:
- Request có thể đã được ghi ở agent, proxy, queue hoặc debug file **trước khi** vào collector.
- Mẫu regex có thể bỏ sót định dạng mới, value đã mã hóa hoặc trường lồng nhau.
- Một số trường ít nhạy cảm riêng lẻ trở nên nhạy cảm khi kết hợp.
- Để lại payload thừa ở nguồn rồi trông chờ collector che là **bảo vệ ở bước muộn**.

Ưu tiên **không thu thập** ngay tại nguồn; dùng redaction làm lớp bổ sung, kiểm thử theo schema và đường vận hành thực tế.

## 10. Data minimization cho analytics, machine learning và báo cáo

Analytics có thể cần dữ liệu phục vụ KPI, phát hiện gian lận hoặc vận hành. Mục tiêu cần nêu **dữ liệu nào, tần suất, độ chi tiết, nhóm người dùng, thời hạn và quyền liên kết**.

### 10.1. Từ raw events tới aggregate

Ví dụ nhóm sản phẩm muốn biết tỷ lệ giao hàng đúng hạn theo ngày và khu vực. Họ có thể chỉ cần:
- Ngày hoặc bucket thời gian.
- Khu vực ở mức đã phê duyệt.
- Số đơn giao đúng hạn/tổng số đơn.
- Các bộ lọc nghiệp vụ tối thiểu.

Không mặc định cần tên, số điện thoại, địa chỉ cụ thể, giá trị thanh toán từng cá nhân hoặc raw payload lịch sử.

### 10.2. Rủi ro tái nhận dạng

**Aggregate không tự bảo đảm ẩn danh.** Một ô tổng hợp có đúng một khách hàng hoặc kết hợp với dữ liệu khác có thể lộ hành vi của người đó. Có thể cần:
- Ngưỡng kích thước nhóm, gộp vùng/thời gian hoặc ẩn nhóm quá nhỏ.
- Giới hạn truy vấn lặp/chồng chéo cho dữ liệu nhạy cảm.
- Pseudonymization có quản trị khóa/ánh xạ và giới hạn liên kết.
- Đánh giá nguy cơ tái nhận dạng theo dữ liệu thực và threat model.
- Kỹ thuật thống kê/bảo vệ riêng tư phù hợp nếu yêu cầu, được review tính hữu dụng và rủi ro.

Không nên tuyên bố “đã dùng hash nên dữ liệu không còn nhạy cảm”, cũng không hứa bảo đảm tuyệt đối khi chỉ thấy bảng aggregate.

### 10.3. Dữ liệu phái sinh, embedding và feature store

Vector embedding, feature profile, score hay metadata có thể **lưu dấu thông tin người dùng hoặc cho phép suy luận ngược/kết hợp**. Cần có inventory, classification, purpose, access control, hạn lưu và cơ chế xử lý yêu cầu xóa phù hợp. Minimization áp dụng cả **dữ liệu tạo ra trong xử lý**, không chỉ dữ liệu gốc thu ở form.

### 10.4. Sampling có chủ đích

Có thể dùng sampling để giảm dữ liệu quan sát và phân tích, nhưng sampling cũng có rủi ro **bỏ sót sự kiện an ninh trọng yếu**. Ví dụ audit event cho thao tác quản trị có thể cần giữ theo yêu cầu, trong khi debug tracing mức chi tiết cao có thể được lấy mẫu. Phân biệt **business analytics telemetry**, **performance traces** và **security audit logs** trước khi giảm số lượng.

## 11. Minimization trong hệ thống đa tenant

Một vấn đề đặc biệt nguy hiểm là **thu thập, xử lý hoặc trả dữ liệu của tenant khác**. Đó vừa là lỗi phân quyền, vừa mở rộng population dữ liệu ngoài mục đích.

### Các đường gây hại cần kiểm tra

| Đường | Ví dụ lỗi | Control phối hợp |
| --- | --- | --- |
| Query database | Truy vấn theo order ID nhưng không giới hạn tenant | Trusted tenant scope, data access policy, query tests |
| API response | DTO trả danh sách đơn của nhiều tenant | Object-level authorization, response contract |
| Export | Worker tạo CSV từ toàn bộ bảng thay vì bộ lọc được duyệt | Verified job ownership và export scope |
| Cache | Cache key chỉ dùng order ID, không gắn context cần thiết | Cache isolation, access checks trước khi trả |
| Queue | Message chứa toàn bộ customer profile nhiều tenant | Minimal event schema, producer/consumer policy |
| Logs | Một tenant được phép tải debug trace tenant khác | Log segregation/authorization và content minimization |
| Analytics | Dashboard aggregate nhưng drill-down tới record ngoài quyền | Dataset/row/column scope và query controls |
| Support tooling | Operator thấy mọi trường hồ sơ mặc dù chỉ cần status | Role/field-level access và review business purpose |

**Minimization không sửa được authorization**, và authorization đúng cũng không tự chứng minh dữ liệu được thu tối thiểu. Hai mục tiêu cần kiểm chứng độc lập trong cùng một luồng.

### Ví dụ risk scenario

**RISK-DM-01:** một API `GET /orders/{orderId}/status` trả thêm email, địa chỉ và lịch sử thanh toán qua một DTO dùng lại cho nhiều use case; một client hợp lệ hoặc log proxy có thể thu được dữ liệu không cần cho chức năng, làm tăng tác động nếu client/token/log bị lộ.

- **Asset:** dữ liệu khách hàng và thông tin đơn hàng.
- **Actor:** client được phép xem trạng thái, hoặc actor truy cập log ngoài mục đích.
- **Trust boundary:** backend → client; API → log collector.
- **Primary objective:** chỉ trả các trường cần thiết cho truy vấn trạng thái và chỉ cho actor được ủy quyền.
- **Control:** response DTO allowlist, entity projection, logging policy, authentication/authorization.
- **Test:** contract response, cross-tenant negative test, log sampling đã làm sạch, query review.
- **Residual risk:** có thể còn bản sao cache, trace, analytics hoặc endpoint cũ chưa được kiểm chứng.

## 12. Xây dựng requirements và controls cho data minimization

Mỗi requirement nên có **điểm đo được**, không chỉ “thu thập hợp lý”. Bảng dưới đây là bộ yêu cầu minh họa, cần điều chỉnh theo risk assessment và chính sách của tổ chức.

| Requirement ID | Yêu cầu có thể kiểm chứng | Control | Test/evidence chính |
| --- | --- | --- | --- |
| **DM-REQ-01** | Mỗi field dữ liệu nhạy cảm trong luồng trọng yếu có mục đích và owner được ghi nhận | Purpose–Data Matrix, data inventory, approval | Review field catalog và schema diff |
| **DM-REQ-02** | API xem trạng thái chỉ chấp nhận và trả các trường thuộc hợp đồng đã phê duyệt | Request/response DTO, schema validation | API contract tests, unexpected-field negative tests |
| **DM-REQ-03** | Query chỉ đọc hàng/thuộc tính cần thiết ở use case và tenant được phép | Projection, query scope, authorization | SQL/JPA review, integration tests |
| **DM-REQ-04** | Queue/event không truyền field ngoài schema/consumer purpose đã duyệt | Event schema allowlist và compatibility checks | Contract tests, sample message đã làm sạch |
| **DM-REQ-05** | Logs/traces không chứa secret hoặc trường PII ngoài phạm vi được duyệt | Structured events, logging redaction at source | Synthetic event, collector sampling, field scan |
| **DM-REQ-06** | Export chỉ tạo đúng population/cột được cấp quyền; bản tạm có vòng đời | Export policy, job ownership, storage lifecycle | Positive/negative export test, object checks |
| **DM-REQ-07** | Tích hợp bên thứ ba chỉ nhận dữ liệu đã duyệt cho mục đích cụ thể | Vendor contract mapping, outbound schema | Contract, API payload test, data-flow review |
| **DM-REQ-08** | Analytics dùng mức tổng hợp/chi tiết phù hợp mục tiêu và quản lý join keys | Dataset governance, aggregation rules | Data product review, query/data tests |
| **DM-REQ-09** | Dữ liệu đã bị loại khỏi use case được xử lý ở bản sao và pipeline liên quan theo policy | Inventory, retention/purge, reconciliation | Copy inventory, deletion/retention evidence |
| **DM-REQ-10** | Thêm field hoặc consumer kích hoạt review mục đích, risk và control | Schema change gate, owner review | PR, approval, updated DFD, runtime retest |
| **DM-REQ-11** | Không có đường truy cập cross-tenant làm mở rộng dữ liệu ngoài mục đích | Authorization theo actor/resource/tenant | Negative access tests, deployment evidence |
| **DM-REQ-12** | Bằng chứng có môi trường/phiên bản/phạm vi, thiếu dữ liệu được ghi thành gap | Evidence register và assurance review | Assessment record, source completeness, finding |

**Điểm cốt lõi:** không thể kết luận DM-REQ-05 đạt chỉ vì API response DTO đã rút gọn; log ở gateway, worker hoặc connector có thể vẫn ghi nguyên payload.

## 13. Kiểm thử tối thiểu hóa: không chỉ đếm số trường

Một phép kiểm tra đơn giản có thể xác minh output contract. Tuy nhiên, rủi ro còn ở **dataflow và bản sao**, nên cần nhiều lớp kiểm thử.

### 13.1. Unit/contract tests cho response

Với `OrderStatusView` và Jackson `ObjectMapper` được cấu hình phù hợp:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;
import org.junit.jupiter.api.Test;

class OrderStatusViewContractTest {
    private final ObjectMapper mapper =
            new ObjectMapper().findAndRegisterModules();

    @Test
    void responseContainsOnlyApprovedFields() throws Exception {
        var view = new OrderStatusView(
                "ORD-132", "SHIPPED",
                Instant.parse("2026-11-28T00:00:00Z"));

        JsonNode json = mapper.readTree(
                mapper.writeValueAsString(view));

        Set<String> fields = StreamSupport.stream(
                ((Iterable<String>) () -> json.fieldNames()).spliterator(),
                false).collect(Collectors.toSet());

        assertEquals(Set.of("id", "status", "lastUpdatedAt"), fields);
        assertFalse(json.has("email"));
        assertFalse(json.has("billingAddress"));
        assertFalse(json.has("paymentDetails"));
    }
}
~~~

Ví dụ kiểm tra trường JSON do record xuất ra; trong dự án thật phải có dependency Jackson JavaTimeModule phù hợp và **test response qua HTTP** theo cấu hình mapper đang dùng. Test này không chứng minh code đã không đọc dữ liệu thừa từ database hoặc không ghi dữ liệu vào log.

### 13.2. Test API, database, queue và logging

| Test ID | Thử nghiệm | Kết quả mong đợi |
| --- | --- | --- |
| **DM-T01** | Gọi status API với user hợp lệ | Response chỉ có các trường được phép |
| **DM-T02** | Cố gửi thêm `isAdmin`, `customerEmail` trong request không hỗ trợ | Bị từ chối hoặc bỏ qua an toàn theo chính sách đã duyệt; không thay đổi quyền/dữ liệu lưu |
| **DM-T03** | Đọc trạng thái đơn tenant B từ user tenant A | Không trả dữ liệu trái quyền |
| **DM-T04** | Review query/projection và đo kết quả lấy từ database | Không đọc hàng/cột nhạy cảm ngoài scope cần thiết theo tiêu chí đã đặt |
| **DM-T05** | Publish event với schema mới/thêm field nhạy cảm | CI schema/purpose review phát hiện field ngoài hợp đồng |
| **DM-T06** | Tạo synthetic request có marker test nhạy cảm an toàn | Marker không xuất hiện trái quy định trong API logs/traces/collector |
| **DM-T07** | Chạy export từ một tenant với bộ lọc được cấp | CSV chỉ chứa cột/record được duyệt |
| **DM-T08** | Hết hạn file export hoặc DLQ có payload | Bản sao được xử lý theo lifecycle và hold phù hợp |
| **DM-T09** | Đưa một trường mới vào JPA Entity | Public API contract không tự mở rộng |
| **DM-T10** | Đổi cấu hình APM/logging trong deployment | Không bật lại raw body/header logging trái policy |
| **DM-T11** | API gọi vendor với order cần giao | Vendor chỉ nhận trường được duyệt, không có token user hoặc scoring nội bộ |
| **DM-T12** | Dùng một aggregate với nhóm rất nhỏ | Chính sách bảo vệ kết quả nhạy cảm được áp dụng, đánh giá khả năng tái nhận dạng |
| **DM-T13** | Collector/scan mất quyền đọc một số nguồn | Không kết luận PASS từ dữ liệu trống, báo INCONCLUSIVE và finding |
| **DM-T14** | Tái triển khai bản cũ hoặc đường API legacy | Không còn đường response/queue ngoài scope đã duyệt |

### 13.3. Dữ liệu test cho minimization cũng phải được tối thiểu hóa

Không lấy bảng khách hàng thật để test “API có lộ thông tin không” khi có thể dùng **dữ liệu giả hoặc bộ fixture đã được phê duyệt**. Tránh đưa dữ liệu cá nhân vào báo cáo CI, screenshot hoặc ticket. Nếu một test cần kiểm tra công cụ redaction, dùng **marker được tạo để thử nghiệm**, không dùng secret đang hoạt động.

### 13.4. Negative tests và quyền

Một response gồm đúng ba trường có thể vẫn rò trạng thái của đơn hàng khác tenant. Test cần gồm **điều kiện được phép và không được phép**, đặc biệt khi xử lý export, support access và worker async. Minimization là một thuộc tính của **payload và population**; authorization là thuộc tính của **quyền actor**. Cần xác minh đồng thời nhưng báo cáo riêng.

## 14. Chỉ số đo tối thiểu hóa và điều dễ gây hiểu nhầm

| Chỉ số | Hữu ích để theo dõi | Giới hạn |
| --- | --- | --- |
| Tỷ lệ field có purpose/owner | Mức kiểm kê và khả năng giải thích dữ liệu | Field có owner không chứng minh nó cần thiết |
| Số field nhạy cảm ở API/queue contract | Diện dữ liệu có thể đi qua ranh giới | Đếm field không biểu thị mức nhạy cảm hoặc số record |
| Số data stores/consumer có bản sao | Độ lan truyền của dữ liệu | Một nguồn ít bản sao nhưng quyền rộng vẫn có rủi ro lớn |
| Tỷ lệ API dùng response allowlist DTO | Mức thực hành contract minimization | DTO vẫn có thể bao gồm trường thừa hoặc query over-fetch |
| Số flow chưa xác nhận purpose | Khoảng trống cần xử lý | Giảm số lượng bằng cách loại khỏi inventory là sai |
| Tỷ lệ logging checks không có trường nhạy cảm | Mức quan sát mẫu log | Không bảo đảm mọi đường hoặc chế độ debug được kiểm tra |
| Tỷ lệ change thêm field được review | Tính bền của kiểm soát qua release | Approve hình thức không chứng minh quyết định đúng |
| Data retention/deletion backlog | Khả năng xử lý bản sao đến hạn | Xóa nhiều không đồng nghĩa minimize đúng hoặc không xóa nhầm |
| Rủi ro tái liên kết ở analytics | Tín hiệu nguy cơ từ datasets được ghép | Không thể quy về một con số chung dễ hiểu mà thiếu phương pháp |

Một KPI như “giảm 50% trường dữ liệu” **không trực tiếp chứng minh giảm 50% rủi ro**. Một trường chứa tài khoản thanh toán có thể quan trọng hơn nhiều trường trạng thái. Cần ưu tiên theo **tài sản, mục đích, độ nhạy, số người có quyền và đường tác động**.

### Đo coverage thay vì chỉ đếm lỗi

Cần tách:
- **Total flows in scope:** bao nhiêu API/queue/logging/export/vendor/data product cần kiểm tra?
- **Flows assessed:** bao nhiêu luồng đã có design + runtime evidence?
- **Flows PASS/FAIL/INCONCLUSIVE:** kết quả đánh giá.
- **Known exclusions:** ngoại lệ được phê duyệt và giới hạn.
- **Last verified:** bằng chứng có còn phản ánh version và môi trường hiện tại không?

Không đưa một flow vào trạng thái PASS khi connector trả danh sách rỗng do mất quyền hoặc vì lần kiểm tra mới chỉ dựa trên OpenAPI chưa đối chiếu actual routes.

## 15. Hồ sơ evidence cho security assurance

Một kết luận tốt cần nêu rõ **claim** thay vì khẳng định chung rằng “chúng tôi thu thập tối thiểu”.

### Ví dụ assurance case

| Mắt xích | Nội dung |
| --- | --- |
| **RISK-DM-01** | Status API truyền dữ liệu khách hàng không cần thiết, làm tăng nguy cơ lộ qua client/log. |
| **OBJ-CONF-01** | Chỉ tiết lộ và xử lý thuộc tính liên quan chức năng xem trạng thái cho actor được cấp quyền. |
| **DM-REQ-02** | Request/response của status API tuân theo allowlist đã duyệt. |
| **DM-REQ-03** | Data access chỉ lấy hàng/cột cần thiết cho use case và tenant hợp lệ. |
| **CTRL-DM-01** | Response DTO, JPA projection, authorization và schema review. |
| **CTRL-DM-02** | Structured logging không chứa payload, logging policy tại gateway/APM. |
| **TEST-DM-01** | Contract tests + negative cross-tenant + payload/log inspection. |
| **EV-DM-01** | OpenAPI/schema, PR, CI run, deployment, test report, sanitized runtime evidence. |
| **FIND-DM-01** | Nếu gateway vẫn log raw response hoặc API cũ trả entity thừa. |
| **RETEST-DM-01** | Xác minh cả API/gateway/collector trên đúng bản triển khai sau sửa. |

Nếu DM-REQ-02 PASS nhưng DM-REQ-03 chưa kiểm tra, không ghi “toàn bộ xử lý dữ liệu của status use case đã tối thiểu”. Cần tách claim theo lớp rồi kết luận phạm vi hợp lý.

### Mẫu evidence record

Dữ liệu trong dấu `<...>` là placeholder; bản ghi này **chưa phải bằng chứng thực tế**:

~~~yaml
assessment_id: DM-ASSURANCE-001
module: SECURITY_SECURITY_ASSURANCE
service: orders-api
environment: production
risk_id: RISK-DM-01
control_ids: [CTRL-DM-01, CTRL-DM-02]
requirement_ids: [DM-REQ-01, DM-REQ-02, DM-REQ-03, DM-REQ-05]
claim: "Status flow exposes only approved fields and authorized orders"
scope:
  endpoint: "GET /orders/{orderId}/status"
  data_class: "customer-order-status"
  actors: ["authorized-order-viewer"]
  destinations: ["browser-client", "gateway-log", "application-log"]
  excluded_flows: "<KNOWN_UNASSESSED_FLOW_LIST>"
purpose:
  id: "<APPROVED_PURPOSE_ID>"
  data_owner: "<AUTHORIZED_DATA_OWNER>"
  field_allowlist: ["id", "status", "lastUpdatedAt"]
  field_decision_ref: "<PURPOSE_DATA_MATRIX_VERSION>"
implementation:
  api_contract_ref: "<OPENAPI_OR_SCHEMA_VERSION>"
  source_commit: "<COMMIT_ID>"
  artifact_digest: "<IMAGE_OR_ARTIFACT_DIGEST>"
  deployment_id: "<RUNTIME_DEPLOYMENT_ID>"
  query_ref: "<DB_PROJECTION_REVIEW>"
verification:
  observed_at: "<ISO_8601_UTC>"
  contract_test_ref: "<CI_TEST_RUN>"
  cross_tenant_test_ref: "<NEGATIVE_AUTHZ_TEST>"
  log_trace_test_ref: "<SANITIZED_PIPELINE_CHECK>"
  result: "<PASS_FAIL_INCONCLUSIVE>"
  reviewer: "<ASSESSOR>"
findings: ["<FINDING_IDS_IF_ANY>"]
residual_risk: "<RISK_ASSESSMENT_AND_DECISION>"
limitations: "<UNTESTED_CACHES_LEGACY_ROUTES_OR_VENDORS>"
reassessment_triggers:
  - "Field/DTO/entity schema change"
  - "New consumer, logger, trace exporter or data store"
  - "Tenant policy, ingress, incident or finding change"
~~~

**Giữ dữ liệu minh chứng không được làm mất mục tiêu minimization.** Bằng chứng có thể dùng **field names, schema hashes, số lượng, marker giả, kết quả query đã làm sạch và version/config references** thay vì lưu full payload khách hàng. Kho evidence phải có quyền, retention, integrity và owner.

### Ba lớp bằng chứng

| Lớp | Cần chứng minh | Không thể tự suy ra |
| --- | --- | --- |
| **Design** | Mục đích, danh mục field, data flow, phân loại và policy được duyệt | Code/run-time đang áp dụng |
| **Implementation/test** | DTO/schema/query, CI tests, review và image build | Production không có đường legacy hoặc drift |
| **Operational effectiveness** | Response thực tế, queue/log/vendored fields trong phạm vi, quyền, version | Mọi bản sao, mọi ngày và đường chưa kiểm tra đều an toàn |

Chỉ có kết quả **unit test DTO** không chứng minh CDN, gateway hoặc tracing library không ghi toàn bộ response sau khi serialize. Assessor phải gắn bằng chứng với **bản triển khai và ranh giới thật**.

## 16. Cách quản trị thay đổi schema và dữ liệu

Một feature mới thường thêm field theo nhu cầu trước mắt; qua nhiều release, một Entity/DTO/event có thể trở thành tập dữ liệu tích lũy mà không còn ai xác nhận mục đích của từng trường.

### Gate trước khi thêm field

Một Pull Request thêm thuộc tính `customerBirthDate` vào service nên trả lời:

1. User story/tác vụ nào đòi hỏi giá trị này? **Bằng chứng về nhu cầu** là gì?
2. Field là dữ liệu cá nhân hoặc nhạy cảm tới mức nào?
3. Có thể tính hoặc lấy ít chi tiết hơn, chỉ khi cần không?
4. Ai nhận dữ liệu qua API, event, log, export, analytics và nhà cung cấp?
5. Có thay đổi quyền/tenant/retention hoặc hệ thống lưu mới không?
6. Có cần di chuyển/xóa data cũ hoặc xử lý bản sao đã phát sinh?
7. Có tăng khả năng liên kết tập dữ liệu hoặc nguy cơ tái nhận dạng không?
8. Những positive/negative tests và bằng chứng runtime nào cần cập nhật?
9. Data Owner, Security, Legal/Privacy hoặc owner hệ thống nào cần review?
10. Nếu trường bị bỏ sau thử nghiệm, **cách xóa hoặc dừng thu** là gì?

Một schema change approval có ý nghĩa khi **đã đọc field semantics, consumer list và risk**; không phải chỉ check code style.

### CI/CD và policy-as-code

Có thể tự động kiểm tra:
- So sánh OpenAPI/JSON schema để phát hiện field mới ở endpoint nhạy cảm.
- Phát hiện JPA Entity được serialize trực tiếp ở controller.
- Quét code/log pattern có nguy cơ ghi secret hoặc raw body.
- Kiểm tra event schema/contract so với allowlist được duyệt.
- Test JSON output và regression khi model thay đổi.
- Tạo report thay đổi data flows và bắt buộc review khi có consumer/vendor mới.

Automation hỗ trợ khám phá nhưng **không tự quyết định tính cần thiết của dữ liệu**: chỉ Business/Data Owner mới có ngữ cảnh mục đích, và Security/Privacy đánh giá các rủi ro/bắt buộc tương ứng.

### Tình huống drift

IaC có thể quy định “không log request body” nhưng một debug flag production, APM agent hoặc proxy cấu hình ngoài pipeline vẫn ghi. Cần so **desired state với actual state**, thu event thử, kiểm tra điểm tiếp nhận và đánh dấu gap nếu chưa đủ bằng chứng.

## 17. Retention và xóa dữ liệu thừa đã tồn tại

Giảm thu thập hôm nay không xử lý được mọi bản sao của dữ liệu đã thu hôm qua. Nếu quyết định một trường không còn cần thiết:

- Ngừng thu và truyền trường đó ở nguồn, bao gồm API cũ.
- Xác định những nơi đã lưu/truyền: database, search, analytics, cache, log, object storage, queue, DLQ, backup và vendor.
- Xác định nghĩa vụ/hold và retention áp dụng trước khi xóa; **không xóa mù** bằng chứng hoặc hồ sơ cần giữ.
- Lập kế hoạch xóa, ẩn danh hoặc giảm độ chi tiết ở từng store/consumer, bảo vệ tính toàn vẹn dữ liệu và khả năng khôi phục.
- Với bản sao bất biến/backup, mô tả lifecycle và giới hạn xóa đúng theo cơ chế thực; xem xét nguy cơ dữ liệu đã xóa xuất hiện lại khi restore.
- Đối chiếu kết quả và lưu bằng chứng **không sao chép lại toàn bộ thông tin nhạy cảm**.

Nếu chỉ thay response DTO mà data lake/warehouse và log chứa dữ liệu cũ vẫn được mọi người truy cập, minimization ở tầng giao diện có thể đã cải thiện nhưng **chưa đủ để kết luận xử lý dữ liệu toàn vòng đời đạt**.

### Tách ba kết luận

- **Collection minimized:** dữ liệu mới được thu ở mức đã duyệt.
- **Processing/sharing minimized:** từng luồng và bên nhận chỉ xử lý dữ liệu cần.
- **Retention/removal verified:** dữ liệu trong các store/bản sao được giữ và xử lý cuối vòng đời theo chính sách.

Một claim có thể PASS trong một phần và INCONCLUSIVE/FAIL ở phần khác. Không gộp lại chỉ vì cùng thuộc “data protection”.

## 18. Phân vai và quyền ra quyết định

| Vai trò | Trách nhiệm | Bằng chứng/đầu ra |
| --- | --- | --- |
| **Business/Product Owner** | Xác định chức năng/mục đích, tiêu chí dữ liệu cần cho nghiệp vụ | Use case, acceptance criteria, purpose decision |
| **Data Owner / Steward** | Phân loại dữ liệu, quyết định trường/tập dữ liệu phục vụ mục đích và owner các bản sao | Data catalog, Purpose–Data Matrix, approval |
| **Developer / Tech Lead** | Thiết kế DTO, query projection, event schema, logging và test | Source/PR, contract tests, integration results |
| **Ops/SRE/Platform** | Quản lý gateway, APM, queue, data stores, backup, runtime config và evidence | Actual state, pipeline config, deployment, monitoring |
| **Security/AppSec** | Threat model, risk scenario, control objective, test âm/dương, remediation | Risk assessment, control/test plan, findings |
| **Legal/Privacy/Compliance** | Đánh giá căn cứ, nghĩa vụ, quyền dữ liệu, điều kiện dùng/giữ/chia sẻ | Review ý kiến và yêu cầu phù hợp |
| **Risk/Service Owner** | Quyết định ưu tiên xử lý hoặc residual risk trong thẩm quyền | Risk treatment, exception và deadline |
| **Assessor/Audit** | Xác minh claim, phạm vi, nguồn chứng cứ, finding và retest | Assessment và audit trail |

**Người viết DTO không tự có quyền quyết định trường dữ liệu nào được phép giữ**, đặc biệt khi liên quan dữ liệu cá nhân, nghĩa vụ hoặc mục đích thứ cấp. Ngược lại, Data Owner xác định nhu cầu nhưng cần Developer/Ops chứng minh hệ thống thực sự thực hiện.

## 19. Case study: Một endpoint hỗ trợ làm phình dữ liệu

### Bối cảnh

Nền tảng thương mại điện tử dùng `orders-api` (Spring Boot), `support-service`, event bus và data warehouse. Nhóm chăm sóc khách hàng cần tra cứu trạng thái giao hàng. Để phát triển nhanh, team tạo endpoint `GET /support/orders/{id}` trả nguyên `OrderEntity`, trong đó có địa chỉ, email, số điện thoại, điểm đánh giá gian lận và trường nội bộ. Support UI chỉ hiển thị trạng thái và địa chỉ rút gọn; gateway có access log lưu response body khi debug. Một consumer analytics sử dụng lại event `OrderUpdated` chứa toàn bộ customer profile.

Các kiểm tra bảo mật ban đầu đều “PASS” vì API có authentication và đường truyền TLS.

### Phân tích rủi ro

| Phát hiện | Tại sao liên quan minimization? | Điều cần xác minh |
| --- | --- | --- |
| **F-DM-01:** API trả nguyên Entity | Backend tiết lộ nhiều trường không cần cho trạng thái đơn | Response schema, actor/tenant, field classification |
| **F-DM-02:** gateway ghi response body | Bản sao dữ liệu nhạy cảm xuất hiện trong kho log | Runtime logging config, log sample an toàn, quyền và retention |
| **F-DM-03:** event chứa customer profile | Consumer nhận dữ liệu vượt mục đích, nhiều bản sao | Event schema, subscriber inventory, DLQ/replay |
| **F-DM-04:** query load toàn bộ Entity | Backend xử lý nhiều cột ngoài nhu cầu | SQL/JPA path, logs và cache |
| **F-DM-05:** access tests chỉ kiểm tra HTTP 200 | Không chứng minh data minimization và tenant boundary | Negative tests, response allowlist và scope |
| **F-DM-06:** dữ liệu đã lan sang warehouse | Sửa endpoint không xóa dữ liệu cũ | Data catalog, purpose, lifecycle và access controls |

### Phương án cải tiến

1. **Khoanh vùng mục đích:** Product/Data Owner xác định trường cần cho “hiển thị trạng thái giao hàng” theo từng vai trò.
2. **Lập data flow thực tế:** liệt kê endpoint, query, cache, gateway/APM, event subscribers, warehouse, backup và owner.
3. **Tạo response DTO riêng:** chỉ `orderId/status/lastUpdatedAt` (và trường nào khác có lý do được duyệt), không trả nguyên Entity.
4. **Thu hẹp truy vấn:** chọn đúng cột, hàng thuộc tenant và đối tượng đã được phép; kiểm tra query/authorization riêng.
5. **Giảm event:** chia thành schema có mục đích, cập nhật consumer và loại bỏ customer profile không cần.
6. **Điều chỉnh logging:** tắt raw response body ở những đường không có căn cứ; dùng structured security events và test collector.
7. **Xử lý bản sao cũ:** theo policy retention và nghĩa vụ, lập kế hoạch xóa/giảm chi tiết trong warehouse, DLQ và cache; quản lý backup riêng.
8. **Triển khai và retest:** CI contract/negative tests, kiểm tra actual gateway, deployment ID, dataset và log với marker test.
9. **Audit/đóng finding:** assessor đối chiếu phạm vi đã sửa; nếu warehouse chưa thể xử lý, ghi finding/residual risk và thời hạn riêng.

### Vì sao authentication và TLS không đủ?

AuthN chứng minh danh tính của client, TLS bảo vệ đường truyền; cả hai **không trả lời field nào cần hiển thị** và **có bao nhiêu nơi nhận dữ liệu**. Một client hoàn toàn hợp lệ vẫn có thể nhận dữ liệu thừa hoặc một log processor được ủy quyền nhưng không có nhu cầu nghiệp vụ lại nhận toàn bộ response.

### Một claim có thể kiểm chứng

> **CLAIM-DM-01:** Ở bản triển khai production đã đánh giá, endpoint xem trạng thái đơn cho actor được phép chỉ trả những trường trong allowlist được Data Owner duyệt, không ghi body vào các log pipeline nằm trong phạm vi đã kiểm tra, và truy vấn chỉ lấy hàng/cột cần thiết. Những data stores và consumer ngoài phạm vi được liệt kê riêng.

Đây là cách viết **đúng phạm vi**, không khẳng định toàn bộ dữ liệu production đã được tối thiểu khi một số bản sao chưa được kiểm tra.

## 20. Bài tập thực hành

**Tình huống:** một team bổ sung tính năng “theo dõi hành trình đơn hàng” cho ứng dụng Java/Spring Boot. Yêu cầu người dùng chỉ cần xem trạng thái và thời gian dự kiến. Dữ liệu hiện đang chảy qua:
- Form nhập `orderId`, email, số điện thoại và ngày sinh.
- API gọi `SELECT *` trên database đơn hàng.
- API trả nguyên `OrderEntity` chứa địa chỉ, lịch sử thanh toán, ghi chú hỗ trợ và `riskScore`.
- Event `TrackingUpdated` gửi toàn bộ thông tin khách hàng tới năm consumers.
- Gateway/tracing lưu raw request/response cho “debug”.
- Analytics lưu mã định danh dùng chung và vị trí giao nhận chi tiết.
- Worker export có quyền đọc toàn bộ đơn hàng đa tenant.
- Backup và DLQ có dữ liệu tích lũy từ nhiều năm.

### Yêu cầu

1. Viết **mục đích xử lý** và tạo Purpose–Data Matrix cho tối thiểu sáu field.
2. Chỉ ra ít nhất **sáu điểm dữ liệu thừa/đường lan truyền** và rủi ro tương ứng.
3. Thiết kế input/output DTO và query projection phù hợp với chức năng theo dõi; giải thích vì sao vẫn cần authorization.
4. Đề xuất schema event **chỉ chứa thông tin cần cho consumer cụ thể**; nêu phương án nếu một consumer cần thêm dữ liệu có quyền.
5. Thiết kế **năm security controls** và **tám tests**, trong đó có request field injection, cross-tenant, log/trace, queue/DLQ, export và data warehouse.
6. Lập evidence record gồm mục đích, owner, approved fields, build/deployment, sources, test run, reviewer và giới hạn chưa kiểm tra.
7. Trình bày cách xử lý dữ liệu cũ ở backups và warehouse mà không xóa nhầm dữ liệu chịu nghĩa vụ lưu giữ.
8. Nêu ai được quyết định thêm trường `customerBirthDate` vào feature sau này; những thay đổi nào kích hoạt review lại?

### Hướng giải mẫu

| Vấn đề | Hướng xử lý | Evidence cần có |
| --- | --- | --- |
| Form thu ngày sinh/số điện thoại | Bỏ nếu không có nhu cầu độc lập, dùng identity/`orderId` theo quy trình | Form contract, API request validation, field decision |
| `SELECT *` | Query projection đúng cột/hàng, giới hạn tenant từ authenticated context | SQL/JPA review, integration query test |
| Trả Entity | Tạo DTO status tối thiểu, schema allowlist và negative tests | JSON contract tests, deployment evidence |
| Event quá rộng | Phân loại consumer, schema theo mục đích, tránh profile mặc định | Event schema, queue/payload sampling đã làm sạch |
| Logs/traces raw body | Tắt tại nguồn, structured events, kiểm tra gateway/APM | Synthetic marker, collector/trace inspection |
| Analytics có vị trí chi tiết | Đánh giá mục đích và aggregation, mức độ chi tiết/tái nhận dạng | Data product review, query/dataset assessment |
| Worker toàn quyền | Thu hẹp IAM và job scope, kiểm tra tenant/resource | Effective policy, allowed/denied tests |
| Backup/DLQ dữ liệu cũ | Inventory, retention/hold và lifecycle riêng, reconciliation | Backup policy, purge/restore test, gap record |

**Câu hỏi nâng cao:** Nếu nhóm đã đổi API thành DTO chỉ có hai field nhưng backend vẫn lưu nguyên request vào log và gửi thông tin khách qua event, liệu có được ghi `DATA_MINIMIZATION=PASS` không?

**Định hướng:** chỉ có thể đánh giá **response contract** đã cải thiện; **flow end-to-end** chưa đạt hoặc chưa đủ bằng chứng. Phải sửa log, event, data access/bản sao và test lại theo scope rồi mới kết luận mức độ đáp ứng.

## 21. Những sai lầm thường gặp

| Nhận định thiếu căn cứ | Vì sao nguy hiểm? | Cách làm tốt hơn |
| --- | --- | --- |
| “Đã mã hóa dữ liệu nên thu bao nhiêu cũng được.” | Encryption không chứng minh cần thu hoặc chia sẻ | Purpose–Data Matrix, giới hạn trường và bản sao |
| “Đã có authentication nên trả Entity không sao.” | Actor hợp lệ vẫn có thể nhận dữ liệu vượt mục đích | Response allowlist và quyền cấp tài nguyên |
| “Chỉ bỏ trường trên UI là đã tối thiểu.” | API, logs, storage, queue vẫn có dữ liệu | Kiểm tra toàn data flow, không chỉ màn hình |
| “Trả DTO nhỏ nên backend không xử lý thừa.” | Entity có thể đã load toàn bộ và ghi vào memory/log | Query projection, data access review |
| “Hash email nghĩa là dữ liệu đã ẩn danh.” | Hash cố định có thể hỗ trợ suy đoán/liên kết | Đánh giá khả năng tái nhận dạng, governance của join keys |
| “Dùng aggregate thì không còn rủi ro riêng tư.” | Nhóm nhỏ/truy vấn chồng chéo có thể lộ dữ liệu | Aggregation policy và rủi ro tái nhận dạng |
| “Tất cả event consumers đều đáng tin.” | Trusted transport không có nghĩa bên nhận cần toàn bộ field | Consumer purpose và topic/schema separation |
| “Redaction ở collector xử lý mọi lộ log.” | Dữ liệu có thể đã lưu ở nguồn/proxy trước đó | Không ghi dữ liệu thừa từ nguồn, test end-to-end |
| “Trường mới trong Entity không ảnh hưởng API.” | Serialize Entity hoặc generic mapper có thể tự thêm field | Explicit DTO, contract regression tests |
| “Không thấy dữ liệu nhạy cảm trong scan tức là không có.” | Nguồn scan thiếu quyền, sample không bao phủ | Kiểm tra health/completeness, dùng INCONCLUSIVE |
| “Dữ liệu giả danh hoàn toàn vô hại.” | Có thể tái liên kết qua nhiều tập dữ liệu | Hạn chế linkability, permission và retention |
| “Chỉ cần xóa database row để hoàn thành minimization.” | Backup, log, cache, warehouse, DLQ vẫn có bản sao | Copy inventory, retention/purge và đối soát |
| “Đã có exception thì yêu cầu đã PASS.” | Risk acceptance không thay đổi control kỹ thuật | Tách status, residual risk, reviewer và hạn |
| “Giảm số trường đồng nghĩa giảm rủi ro theo cùng tỷ lệ.” | Rủi ro phụ thuộc dữ liệu/actor/đường gây hại | Đánh giá theo asset, sensitivity và threat scenarios |
| “Không được giảm security logs vì phục vụ audit.” | Log vẫn có thể và nên giảm payload nhạy cảm không cần | Phân loại event, giữ metadata đủ chứng minh, retention đúng |
| “Review schema một lần là đủ.” | Feature, consumer, APM, policy và data store thay đổi | Trigger theo change, runtime verification và retest |

## Ghi nhớ

- **Data minimization** là giới hạn dữ liệu theo **mục đích, trường, tập bản ghi, độ chi tiết, thời gian, số bản sao, khả năng liên kết và đối tượng nhận** trong toàn vòng đời.
- **Mục đích xử lý phải được xác định trước**, sau đó mới quyết định field nào cần thiết; một trường không có rationale không tự có quyền tồn tại vì đã nằm trong database.
- **Encryption, access control, pseudonymization và retention** hỗ trợ bảo vệ dữ liệu nhưng không thay thế quyết định có cần thu/lan truyền dữ liệu hay không.
- API Java/Spring Boot nên dùng **request/response DTO rõ ràng, giới hạn dữ liệu được query**, kiểm tra authorization và quản lý schema/event/log; không serialize nguyên Entity mặc định.
- **Log, trace, queue, analytics, export, backup và vendor** đều có thể tạo bản sao ngoài mục đích; sửa API response là chưa đủ để chứng minh flow đã tối thiểu.
- Bằng chứng cần nối **risk → requirement → control → positive/negative tests → runtime evidence → finding → remediation/retest**, có owner, version, môi trường, thời điểm và giới hạn rõ.
- **Security assurance phải diễn ra liên tục** khi thêm field, API, consumer, role, data store hoặc đổi logging/config; control có thể drift và kết luận PASS cũ có thể không còn hiệu lực.
