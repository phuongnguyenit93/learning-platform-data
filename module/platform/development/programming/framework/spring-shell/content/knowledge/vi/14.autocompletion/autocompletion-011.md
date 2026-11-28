# Giới hạn thời gian, số kết quả và dữ liệu nhạy cảm trong gợi ý

Tự hoàn thành giúp người dùng khám phá command và giá trị option nhanh hơn, nhưng mỗi lần nhấn Tab có thể kích hoạt việc tìm kiếm dữ liệu. Nếu provider gọi database hoặc dịch vụ từ xa, một truy vấn chậm có thể làm terminal đứng lại; trả về quá nhiều kết quả khiến danh sách khó dùng; và đưa dữ liệu nhạy cảm vào gợi ý có thể làm lộ thông tin ngay trên màn hình hoặc trong command buffer.

Trong Spring Shell 4.x, `CompletionProvider` nhận `CompletionContext` và trả về danh sách `CompletionProposal`. API này tập trung vào việc tạo gợi ý; nó không tự đặt timeout cho truy vấn, không giới hạn số proposal và không tự lọc dữ liệu theo quyền của người dùng. Các giới hạn đó cần được thiết kế trong provider và dịch vụ cung cấp dữ liệu. Bài viết trình bày cách đặt ngân sách thời gian, giới hạn số kết quả, bảo vệ dữ liệu và kiểm thử hành vi autocomplete.

## 1. Hiểu đường đi của một lần nhấn Tab

Trong JLine-based Shell, người dùng có thể nhấn Tab khi đang nhập command để yêu cầu Spring Shell đề xuất phần còn thiếu. Spring Shell dùng completion provider mặc định cho command và option; ứng dụng có thể đăng ký `CompletionProvider` tùy chỉnh ở cấp command.

Luồng xử lý khái quát:

```text
Người dùng nhấn Tab
        |
        v
JLine lấy input buffer và vị trí con trỏ
        |
        v
Spring Shell tạo CompletionContext
        |
        v
CompletionProvider đọc ngữ cảnh và prefix
        |
        v
Tra cứu dữ liệu / lọc theo người dùng / giới hạn kết quả
        |
        v
Trả List<CompletionProposal>
        |
        v
JLine hiển thị danh sách gợi ý
```

`CompletionProvider` là functional interface mở rộng `Function<CompletionContext, List<CompletionProposal>>`. Do đó, lời gọi provider là đồng bộ: nó phải trả về danh sách proposal. Không có tham số timeout hoặc `maxResults` được Spring Shell tự áp dụng trong interface này. Nếu provider gọi I/O chậm, thao tác hoàn thành có thể bị chậm theo.

Autocomplete chủ yếu phục vụ shell tương tác dựa trên JLine. Khi ứng dụng chạy non-interactive hoặc qua script, không nên giả định người dùng có thể nhấn Tab trong cùng cách thức; cần kiểm thử riêng luồng chạy và tích hợp completion ở shell hệ điều hành nếu có yêu cầu.

## 2. Đặt ngân sách thời gian cho mỗi lần hoàn thành

Người dùng thường nhấn Tab nhiều lần liên tiếp khi gõ. Provider nên trả lời nhanh và có giới hạn thời gian rõ ràng. Một truy vấn autocomplete không nên chờ vô hạn để lấy dữ liệu hoàn hảo.

Các nguyên tắc nên áp dụng:

- **Đặt timeout ở nơi thực hiện I/O:** cấu hình connect timeout và request/read timeout cho HTTP client; cấu hình timeout truy vấn hoặc statement timeout cho database.
- **Dùng ngân sách nhỏ:** chọn timeout theo trải nghiệm terminal và độ trễ hệ thống. Ví dụ, một ứng dụng có thể đặt mục tiêu khoảng 100–200 ms cho một lần tra cứu nhanh; đây là ngân sách thiết kế cần đo thực tế, không phải giá trị mặc định của Spring Shell.
- **Không chờ retry nhiều lần:** retry có thể nhân thời gian chờ và khiến mỗi lần nhấn Tab làm nghẽn shell. Nếu cần retry, giới hạn rất chặt hoặc bỏ retry trong đường autocomplete.
- **Fallback an toàn:** khi timeout hoặc dịch vụ gợi ý tạm thời không sẵn sàng, trả danh sách rỗng hoặc dữ liệu cache còn hợp lệ. Người dùng vẫn có thể nhập giá trị đầy đủ bằng tay.
- **Giữ provider nhẹ:** không chạy tác vụ nghiệp vụ, không tải toàn bộ entity graph và không thực hiện thao tác có side effect.

Timeout phải được áp dụng ở client hoặc repository thực hiện truy vấn. Chỉ đo thời gian bằng `System.nanoTime()` sau khi lời gọi đã hoàn tất không ngăn được provider treo lâu; đó chỉ là đo lường, không phải timeout.

### Ví dụ hợp đồng dịch vụ có timeout

Có thể định nghĩa một dịch vụ tra cứu gợi ý với giới hạn kết quả và thời gian rõ ràng:

```java
public interface DocumentSuggestionService {

    List<DocumentSuggestion> findVisibleSuggestions(
            String principalId,
            String prefix,
            int limit,
            Duration timeout);
}
```

Hợp đồng này yêu cầu implementation:

1. Chỉ tìm tài liệu mà `principalId` được phép nhìn thấy.
2. Lọc theo `prefix` ngay tại nguồn dữ liệu.
3. Áp dụng `limit` trong câu truy vấn, không tải toàn bộ rồi mới cắt danh sách.
4. Thiết lập deadline thực tế cho truy vấn hoặc lời gọi HTTP.
5. Ném exception timeout có kiểu rõ ràng hoặc trả kết quả rỗng theo quy ước thống nhất.

`Duration timeout` trong ví dụ là tham số của abstraction do ứng dụng tự định nghĩa; Spring Shell không tự đọc tham số này. Implementation cần chuyển nó thành timeout mà driver hoặc HTTP client thực sự hỗ trợ.

## 3. Chỉ truy vấn khi prefix đủ dài

Một prefix quá ngắn thường khớp với rất nhiều bản ghi. Nếu tìm kiếm từ một ký tự, provider có thể phải đọc một tập kết quả lớn và tạo danh sách ít hữu ích.

Hãy đặt ngưỡng tối thiểu phù hợp với dữ liệu:

- Với mã định danh có cấu trúc, có thể yêu cầu 2–3 ký tự đầu.
- Với enum hoặc tập lựa chọn nhỏ cố định, không cần ngưỡng prefix vì dữ liệu đã giới hạn.
- Với tên người dùng, email hoặc dữ liệu riêng tư, không nên bật gợi ý rộng chỉ vì prefix đủ dài; phải xét quyền và chính sách riêng tư trước.
- Nếu người dùng xóa prefix về rỗng, trả danh sách rỗng thay vì truy vấn toàn bộ tài nguyên.

Ví dụ:

```java
private static final int MIN_PREFIX_LENGTH = 2;

if (prefix == null || prefix.strip().length() < MIN_PREFIX_LENGTH) {
    return List.of();
}
```

Ngưỡng này giúp giảm tải và hạn chế việc lộ danh sách tài nguyên khi người dùng chưa cung cấp đủ ngữ cảnh. Không xem nó là cơ chế bảo mật: mọi truy vấn vẫn phải được giới hạn theo principal, tenant và quyền truy cập.

## 4. Giới hạn số proposal ở cả truy vấn và provider

Một completion list quá dài khó điều hướng và tốn thời gian truy vấn, chuyển đổi, sắp xếp và hiển thị. Hãy đặt một giới hạn nhỏ, ổn định, ví dụ 10–20 kết quả cho danh sách tên tài nguyên.

Giới hạn cần được áp dụng ở hai nơi:

1. **Nguồn dữ liệu:** database dùng `LIMIT`/`FETCH FIRST`, `Pageable` hoặc cơ chế tương ứng; API từ xa nhận tham số page size hoặc limit.
2. **Provider:** giới hạn lần cuối trước khi trả về `List<CompletionProposal>` để bảo vệ shell nếu service trả quá nhiều kết quả do lỗi hoặc thay đổi implementation.

Ví dụ truy vấn database theo ý tưởng:

```sql
SELECT public_id, display_name
FROM documents
WHERE tenant_id = :tenantId
  AND owner_id = :principalId
  AND normalized_name LIKE :prefixPattern
ORDER BY normalized_name, public_id
FETCH FIRST :limit ROWS ONLY
```

Tên cột và cú pháp phân trang tùy hệ quản trị dữ liệu. Điểm quan trọng là lọc quyền, prefix, thứ tự và số lượng ngay trong truy vấn. `stream().limit(20)` sau khi tải hàng trăm nghìn bản ghi không giải quyết được chi phí ở database hoặc mạng.

Nên sắp xếp ổn định, chẳng hạn theo tên chuẩn hóa rồi theo ID công khai. Kết quả ổn định giúp người dùng dự đoán lựa chọn và tránh danh sách thay đổi tùy thứ tự trả về ngẫu nhiên.

## 5. Triển khai `CompletionProvider` có timeout và giới hạn

Ví dụ sau dùng một service abstraction có trách nhiệm áp dụng timeout và giới hạn truy vấn. `CurrentUserProvider` là thành phần của ứng dụng, cung cấp principal hiện tại sau khi xác thực.

```java
import java.time.Duration;
import java.util.List;

import org.springframework.stereotype.Component;
import org.springframework.shell.core.command.completion.CompletionContext;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;

@Component("documentCompletionProvider")
public class DocumentCompletionProvider implements CompletionProvider {

    private static final int MIN_PREFIX_LENGTH = 2;
    private static final int MAX_RESULTS = 20;
    private static final Duration LOOKUP_TIMEOUT = Duration.ofMillis(150);

    private final DocumentSuggestionService suggestionService;
    private final CurrentUserProvider currentUser;

    public DocumentCompletionProvider(
            DocumentSuggestionService suggestionService,
            CurrentUserProvider currentUser) {
        this.suggestionService = suggestionService;
        this.currentUser = currentUser;
    }

    @Override
    public List<CompletionProposal> apply(CompletionContext context) {
        String currentWord = context.currentWordUpToCursor();
        if (currentWord == null) {
            return List.of();
        }

        String prefix = extractDocumentIdPrefix(currentWord).strip();
        if (prefix.length() < MIN_PREFIX_LENGTH) {
            return List.of();
        }

        try {
            String principalId = currentUser.principalId();
            return suggestionService.findVisibleSuggestions(
                            principalId, prefix, MAX_RESULTS, LOOKUP_TIMEOUT)
                    .stream()
                    .limit(MAX_RESULTS)
                    .map(document -> new CompletionProposal(
                                    "--document-id=" + document.publicId())
                            .displayText(document.safeDisplayName())
                            .description("Accessible document"))
                    .toList();
        }
        catch (CompletionLookupTimeoutException
                | CompletionLookupUnavailableException ex) {
            return List.of();
        }
    }

    private String extractDocumentIdPrefix(String currentWord) {
        int separator = currentWord.indexOf('=');
        return separator >= 0
                ? currentWord.substring(separator + 1)
                : currentWord;
    }
}
```

Gắn provider vào command:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class DocumentCommands {

    private final DocumentService documentService;

    public DocumentCommands(DocumentService documentService) {
        this.documentService = documentService;
    }

    @Command(
            name = "document-show",
            description = "Show an accessible document",
            completionProvider = "documentCompletionProvider")
    public String show(@Option(longName = "document-id") String documentId) {
        return documentService.show(documentId);
    }
}
```

Các kiểu `DocumentSuggestionService`, `DocumentSuggestion`, `CurrentUserProvider`, `CompletionLookupTimeoutException` và `CompletionLookupUnavailableException` là abstraction/kiểu của ứng dụng trong ví dụ. Implementation của `DocumentSuggestionService` phải bảo đảm timeout và truy vấn có giới hạn như hợp đồng ở phần trước. Tên option và cách trích prefix cần được điều chỉnh theo command context thực tế; `CompletionContext` cung cấp current word, vị trí con trỏ, option và command đang được hoàn thành.

Ví dụ proposal ở trên giả định người dùng hoàn thành option theo dạng `--document-id=prefix`. Nếu CLI cho phép cú pháp tách token `--document-id prefix`, provider cần dùng `CompletionContext.getCommandOption()` cùng vị trí từ hiện tại để chỉ trả giá trị ID, không chèn lại tên option vào vị trí value. Với command có nhiều option cần gợi ý khác nhau, hãy phân nhánh theo option trong context thay vì chỉ dựa vào nội dung chuỗi hiện tại.

`CompletionProposal` tách riêng:

- `value`: chuỗi sẽ được chèn vào input khi người dùng chọn proposal.
- `displayText`: nội dung hiển thị trong danh sách.
- `description`: mô tả bổ sung.
- `category`: nhóm của proposal nếu cần.

Không nhầm `displayText` đã được che với `value` đã an toàn. `value` vẫn được chèn vào command buffer và có thể được lưu trong history hoặc log tùy cấu hình terminal.

## 6. Giới hạn thời gian khi gọi HTTP hoặc database

Nếu suggestion service gọi một API từ xa, hãy cấu hình timeout trên HTTP client thay vì dựa vào timeout giả định ở provider. Ví dụ với Java `HttpClient`:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(80))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofMillis(150))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
```

`connectTimeout` giới hạn thời gian thiết lập kết nối; `HttpRequest.timeout` giới hạn thời gian chờ phản hồi cho request. Khi timeout, implementation cần chuyển lỗi tương ứng thành `CompletionLookupTimeoutException` hoặc kết quả rỗng theo hợp đồng của ứng dụng. Không ghi URL chứa query nhạy cảm hoặc response body chứa dữ liệu cá nhân vào log autocomplete.

Với database, cấu hình query timeout hoặc statement timeout qua JDBC/ORM/driver phù hợp. Timeout ở tầng connection pool chỉ giới hạn việc chờ lấy connection; nó không nhất thiết giới hạn thời gian thực thi SQL. Hãy xác định rõ timeout nào đang bảo vệ từng đoạn của đường gọi.

Nếu dùng `Future.get(timeout, unit)` để giới hạn một tác vụ đồng bộ, cần dùng executor có số thread và queue hữu hạn, hủy tác vụ khi hết hạn và bảo đảm client bên dưới cũng có timeout. `Future.cancel(true)` chỉ gửi tín hiệu interrupt; nó không bảo đảm một truy vấn I/O sẽ dừng nếu driver không hỗ trợ hủy.

## 7. Dùng cache có phạm vi và thời hạn rõ ràng

Cache giúp giảm truy vấn lặp lại khi người dùng nhấn Tab liên tục với cùng prefix. Tuy nhiên, cache autocomplete có thể làm lộ dữ liệu nếu key không bao gồm danh tính hoặc tenant.

Một cache key phù hợp thường bao gồm:

- Principal hoặc subject đã xác thực.
- Tenant/workspace hiện tại.
- Loại tài nguyên và quyền lọc liên quan.
- Prefix đã chuẩn hóa.
- Phiên bản quyền hoặc scope nếu quyền có thể thay đổi trong thời gian cache.

Các nguyên tắc:

1. Đặt TTL ngắn theo độ mới cần thiết, ví dụ vài giây đến vài chục giây cho dữ liệu thường thay đổi.
2. Giới hạn số entry và kích thước cache để tránh tăng bộ nhớ theo số prefix.
3. Không dùng chung cache giữa người dùng hoặc tenant nếu kết quả phụ thuộc quyền.
4. Xóa hoặc làm mất hiệu lực cache khi logout, đổi tenant, đổi role hoặc quyền tài nguyên bị thu hồi nếu hệ thống yêu cầu phản ánh ngay.
5. Không cache secret, token, mật khẩu hoặc giá trị credential.
6. Không coi cache là nguồn quyết định authorization; khi người dùng chọn giá trị, service phải kiểm tra quyền lại.

Cache chỉ là tối ưu hiệu năng. Nếu cache miss, provider vẫn phải tuân theo timeout và result limit. Nếu cache entry hết hạn, fallback không nên làm lộ dữ liệu cũ của principal khác.

## 8. Không đưa dữ liệu nhạy cảm vào proposal

Completion list có thể xuất hiện trên màn hình, trong command buffer, shell history, log, bản ghi terminal hoặc ảnh chụp màn hình. Do đó, không được dùng autocomplete làm kênh phân phối secret.

Không gợi ý các giá trị như:

- Mật khẩu, API key, access token, refresh token, session ID hoặc private key.
- Connection string có username/password.
- Mã khôi phục, mã OTP hoặc credential tạm thời.
- Giá trị bí mật trong environment variable hoặc file cấu hình.
- Thông tin cá nhân hoặc dữ liệu khách hàng mà principal hiện tại không được phép xem.

Với dữ liệu tài nguyên, hãy chỉ gợi ý bản ghi mà người dùng có quyền truy cập. Tốt nhất, áp dụng điều kiện tenant, owner, ACL và trạng thái bản ghi ngay trong truy vấn. Không lấy toàn bộ tên tài liệu rồi mới lọc quyền trong bộ nhớ; cách đó vừa tốn tài nguyên vừa có thể tạo side channel qua số lượng hoặc thời gian phản hồi.

Nếu cần hiển thị tài nguyên, dùng `publicId` hoặc identifier không nhạy cảm làm `value`, và một nhãn an toàn làm `displayText`. `description` và `category` cũng phải được rà soát vì chúng có thể chứa tên khách hàng, email, đường dẫn nội bộ hoặc trạng thái riêng tư.

Ví dụ:

```java
new CompletionProposal(document.publicId())
        .displayText(document.safeDisplayName())
        .description("Accessible document");
```

Không nên viết:

```java
new CompletionProposal(document.apiToken())
        .displayText(document.ownerEmail())
        .description(document.connectionString());
```

Che một phần `displayText` không bảo vệ được nếu `value` vẫn chứa secret. Nếu một giá trị cần được giữ bí mật, đừng đưa nó vào proposal ở bất kỳ trường nào.

## 9. Lọc theo quyền trước khi giới hạn kết quả

Thứ tự lọc quan trọng. Truy vấn nên áp dụng principal/tenant/ACL trước, sau đó lọc prefix, sắp xếp và giới hạn kết quả. Nếu lấy top 20 bản ghi toàn hệ thống rồi mới lọc quyền, người dùng có thể nhận ít hơn 20 gợi ý dù còn tài nguyên hợp lệ; nghiêm trọng hơn, logic phân trang và cache có thể vô tình tiết lộ thông tin về bản ghi không được phép xem.

Thứ tự đề xuất:

```text
Principal + tenant + authorization scope
                 |
                 v
          Prefix matching
                 |
                 v
          Stable ordering
                 |
                 v
          Query limit (N)
                 |
                 v
     Safe CompletionProposal mapping
                 |
                 v
      Final defensive limit (N)
```

Ngay cả khi suggestion đã được lọc, command thực thi vẫn phải kiểm tra quyền trên ID được gửi. Người dùng có thể sửa command buffer bằng tay, gọi một ID không nằm trong danh sách hoặc dùng giá trị cũ sau khi quyền bị thu hồi. Autocomplete chỉ hỗ trợ khám phá; nó không phải cơ chế authorization.

## 10. Tránh log và telemetry làm lộ dữ liệu

Provider có thể được gọi rất thường xuyên. Log toàn bộ `CompletionContext`, prefix hoặc danh sách proposal sẽ tạo nhiều dữ liệu và có thể vô tình lưu thông tin nhạy cảm.

Nên ghi các số liệu tổng hợp:

- Tên provider/command.
- Thời gian xử lý theo bucket hoặc histogram.
- Số proposal trả về.
- Tỷ lệ timeout, lỗi dịch vụ và cache hit/miss.
- Kết quả có bị cắt bởi giới hạn hay không.

Tránh ghi:

- Raw input buffer hoặc toàn bộ `CompletionContext`.
- Prefix chứa email, mã khách hàng, token hoặc dữ liệu người dùng.
- Toàn bộ `CompletionProposal.value`, `displayText` hoặc `description`.
- Response body từ dịch vụ gợi ý.

Nếu cần correlation ID để điều tra, dùng ID ngẫu nhiên không mang thông tin nhận dạng và tuân theo chính sách lưu log của ứng dụng. Telemetry nên cho biết provider chậm ở đâu mà không cần thu thập nội dung người dùng đang gõ.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Provider gọi API không timeout | Nhấn Tab có thể treo terminal | Đặt connect/request timeout ở HTTP client |
| Chỉ đo thời gian sau khi query hoàn tất | Không giới hạn được thời gian chờ | Dùng timeout thật ở client/driver |
| Tải tất cả bản ghi rồi dùng `limit()` | Tốn database, mạng và bộ nhớ | Đưa limit vào câu truy vấn |
| Trả hàng trăm proposal | Danh sách khó sử dụng và chậm | Chọn giới hạn nhỏ, ổn định như 10–20 |
| Truy vấn khi prefix rỗng | Có thể trả toàn bộ tài nguyên | Yêu cầu prefix tối thiểu hoặc trả rỗng |
| Cache chỉ theo prefix | Dữ liệu người dùng A có thể xuất hiện cho B | Đưa principal, tenant và scope vào cache key |
| Chỉ che `displayText` | `value` hoặc description vẫn có thể lộ secret | Không đưa secret vào bất kỳ trường proposal nào |
| Lấy dữ liệu trước rồi mới lọc ACL | Có nguy cơ rò rỉ qua kết quả hoặc timing | Lọc quyền ngay trong truy vấn nguồn |
| Tin rằng gợi ý đồng nghĩa với được phép | Người dùng có thể gọi ID khác bằng tay | Kiểm tra quyền lại trong command/service |
| Log toàn bộ context và proposals | Log lưu prefix và dữ liệu riêng tư | Chỉ log metric tổng hợp, không log giá trị |
| Retry nhiều lần trong mỗi lần Tab | Tăng độ trễ và tải dịch vụ | Bỏ retry hoặc giới hạn nghiêm ngặt |

## 12. Kiểm thử giới hạn và bảo vệ dữ liệu

Nên kiểm thử provider độc lập với terminal, sau đó kiểm thử tích hợp JLine để xác nhận trải nghiệm Tab.

| Trường hợp | Điều kiện | Kỳ vọng |
|---|---|---|
| Prefix quá ngắn | Ít hơn `MIN_PREFIX_LENGTH` | Không gọi dịch vụ; trả danh sách rỗng |
| Nhiều kết quả | Service trả nhiều hơn giới hạn | Provider chỉ trả tối đa `MAX_RESULTS` |
| Truy vấn chậm | Service vượt deadline | Provider trả fallback trong ngân sách đã đặt |
| Dịch vụ lỗi | API/database unavailable | Không làm shell treo; trả rỗng hoặc cache hợp lệ |
| Hai principal | Cùng prefix, khác tenant/ACL | Không có proposal của principal kia |
| Secret trong dữ liệu nguồn | Bản ghi chứa token hoặc credential | Không có secret trong value/displayText/description/category |
| Quyền bị thu hồi | Cache cũ còn tồn tại | Cache bị vô hiệu hóa theo chính sách; command vẫn từ chối khi thực thi |
| Prefix chứa dữ liệu riêng tư | Email hoặc mã khách hàng | Không ghi raw prefix vào log/telemetry |
| Kết quả trùng | Nhiều bản ghi tạo cùng proposal | Loại trùng theo identifier ổn định |
| Không có kết quả | Prefix không khớp | Trả danh sách rỗng, không ném lỗi |

Các kiểm thử nên xác nhận cả số lần gọi dịch vụ và dữ liệu trả về. Ví dụ, prefix quá ngắn phải không gọi repository; timeout phải kết thúc trong ngân sách đã chọn; giới hạn được áp dụng ở truy vấn và ở provider; dữ liệu ngoài tenant không xuất hiện trong proposal.

Với kiểm thử bảo mật, đừng chỉ kiểm tra `displayText`. Hãy kiểm tra toàn bộ `value`, `displayText`, `description` và `category`, đồng thời kiểm tra log nếu provider có ghi log. Sau khi chọn một proposal, gọi command bằng một ID ngoài danh sách để xác nhận service vẫn thực hiện authorization.

## 13. Checklist trước khi đưa completion vào sử dụng

- [ ] Provider chỉ thực hiện công việc cần thiết cho gợi ý.
- [ ] Đã đặt timeout thực tế cho mọi HTTP/database I/O.
- [ ] Đã chọn ngân sách thời gian dựa trên số đo thực tế của terminal.
- [ ] Prefix rỗng hoặc quá ngắn không kích hoạt truy vấn rộng.
- [ ] Database/API giới hạn số bản ghi ngay tại nguồn.
- [ ] Provider áp dụng thêm giới hạn cuối trước khi trả proposal.
- [ ] Kết quả có thứ tự ổn định và không trùng lặp.
- [ ] Dữ liệu được lọc theo principal, tenant và quyền trước khi trả về.
- [ ] Cache có TTL, giới hạn kích thước và key theo principal/tenant/scope.
- [ ] Không đưa password, token, key hoặc credential vào bất kỳ trường proposal nào.
- [ ] `value`, `displayText`, `description` và `category` đều đã được rà soát.
- [ ] Command/service kiểm tra quyền lại khi thực thi giá trị được chọn.
- [ ] Log và telemetry không ghi raw input hoặc proposal nhạy cảm.
- [ ] Có test timeout, result cap, prefix ngắn, cache isolation và quyền truy cập.
- [ ] Đã thử autocomplete bằng JLine trên môi trường chạy thực tế.

## Tài liệu tham khảo

1. [Spring Shell 4 – Command Completion](https://docs.spring.io/spring-shell/reference/commands/completion.html) – custom `CompletionProvider`, provider mặc định, enum, file và composite provider.
2. [Spring Shell 4 – `CompletionProvider` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProvider.html) – hợp đồng `CompletionContext` sang `List<CompletionProposal>`.
3. [Spring Shell 4 – `CompletionContext` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionContext.html) – từ hiện tại, vị trí con trỏ, command và option context.
4. [Spring Shell 4 – `CompletionProposal` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProposal.html) – phân biệt value, display text, description, category và quoting flags.
5. [Spring Shell – v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) – completion được tập trung ở cấp command bằng `CompletionProvider`, hỗ trợ ngữ cảnh giữa các option.

Một completion provider tốt trả lời nhanh, đưa ra một tập lựa chọn nhỏ và chỉ tiết lộ những giá trị mà người dùng hiện tại được phép nhìn thấy. Hãy đặt timeout ở tầng truy vấn, giới hạn dữ liệu ngay từ nguồn, giữ proposal không chứa secret và luôn xác thực lại giá trị khi command thực sự chạy.
