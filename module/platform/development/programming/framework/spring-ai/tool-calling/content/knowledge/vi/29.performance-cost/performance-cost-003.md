# Giới hạn kích thước kết quả và lịch sử gửi lại mô hình

Trong Spring AI Tool Calling, một tool có thể trả vài trường JSON hoặc hàng megabyte dữ liệu: danh sách đơn hàng, log, nội dung tài liệu, lịch sử giao dịch hay kết quả từ MCP server. Kết quả đó thường được gửi **trở lại mô hình** để mô hình quyết định bước tiếp theo. Khi có nhiều lượt model–tool, các kết quả trước còn có thể tiếp tục nằm trong lịch sử gửi lại. Không kiểm soát kích thước sẽ làm tăng token, độ trễ, chi phí, nguy cơ vượt context window và cả rủi ro lộ dữ liệu không cần thiết.

**Giới hạn từng tool result và giới hạn lịch sử là hai vấn đề khác nhau.** Một kết quả tool quá lớn có thể làm prompt kế tiếp thất bại ngay trong cùng request; lịch sử nhiều lượt dù mỗi result nhỏ vẫn tích lũy token theo thời gian. Hai lớp giới hạn phải phối hợp nhưng không thay thế nhau.

Bài học thuộc module `SPRING_AI_TOOL_CALLING`, tập trung `@Tool`, `ToolCallback`, `ToolCallResultConverter`, `ToolCallingAdvisor`, `ToolContext` và session memory. Ví dụ nhắm **Spring AI 2.1.0**; tên API và kiến trúc memory có khác biệt với 1.x/2.0.x.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt số item, số ký tự UTF-16, UTF-8 byte và số token.
- Đặt ngân sách output cho mỗi tool, tổng nhiều tool, toàn request và lịch sử.
- Giảm dữ liệu ở source bằng projection, pagination, aggregate và field preview.
- Thiết kế envelope JSON nhỏ nhưng có `status`, `hasMore`, `nextCursor`, thời điểm/nguồn và trạng thái không đầy đủ.
- Giới hạn kết quả **sau serialization** bằng `ToolCallResultConverter` mà không cắt hỏng JSON.
- Giải thích lịch sử nội bộ trong vòng `ToolCallingAdvisor` và sự lặp lại token qua nhiều model rounds.
- Cấu hình `SessionAdvisors`, `EventFilter`, `TokenCountTrigger` và compaction trong 2.1.0.
- Bảo vệ tính toàn vẹn cặp assistant tool call – tool response.
- Hiểu `returnDirect` và streaming không tự tạo ra giới hạn tool result.
- Kiểm thử byte cap, budget, pagination, tenant isolation và sự đúng đắn của câu trả lời.

## Tool result ảnh hưởng prompt như thế nào?

Spring AI 2.x dùng `ToolCallingAdvisor` quản lý vòng gọi: model yêu cầu tool, `ToolCallingManager` thực thi callback, result được chuyển thành message, rồi lịch sử cập nhật được gửi vào model tiếp theo cho đến khi không còn tool call. Với cấu hình mặc định, history nội bộ của vòng này được giữ qua các iterations.

~~~mermaid
flowchart TD
    U[Câu hỏi user] --> M1[Model round 1]
    M1 --> T1[Tool A: kết quả dài]
    T1 --> H1[History: user + call A + result A]
    H1 --> M2[Model round 2]
    M2 --> T2[Tool B: kết quả khác]
    T2 --> H2[History có A và B]
    H2 --> M3[Model round 3]
    M3 --> ANS[Câu trả lời cuối]
    T1 -. Giảm trước khi đưa vào history .-> P[Projection / page / cap]
    P -. Ít token hơn .-> H1
~~~

Nếu A trả khoảng 12.000 token và model gọi thêm hai vòng, phần A có thể bị gửi lại nhiều lần. Tổng token tiêu thụ một workflow xấp xỉ **tổng các prompt của từng model round**, không phải chỉ kích thước kết quả cuối. Spring AI 2.1.0 báo usage tích lũy trong vòng tool calling; đo tổng workflow thay vì chỉ đếm token của vòng cuối.

Những nguồn tăng trưởng cần phân biệt:

| Nguồn | Vị trí | Cơ chế giới hạn |
|---|---|---|
| Một result chứa quá nhiều bản ghi | Service và converter | Query LIMIT, DTO, hard byte/token cap |
| Nhiều tool cùng được yêu cầu | Một round | Budget tổng các tool, số call |
| Nhiều model–tool iterations | Một user turn | Tool-call limit, deadline, cost budget |
| Lịch sử qua nhiều user turns | Session/memory | Active view, window, compaction |
| Audit event log | Repository | Retention, TTL, ACL, storage quota |
| Model viết quá dài | Output model | Output-token config, template trả lời |

Không nhầm tham số **max output tokens** của model với giới hạn dữ liệu **tool trả vào prompt**. Output-token config không tự rút gọn JSON của callback.

## Ký tự, byte và token khác nhau

| Đơn vị | Đo lường | Nhược điểm |
|---|---|---|
| Số item | Bản ghi trả về | Một item vẫn có thể rất dài |
| `String.length()` | UTF-16 code units | Không bằng UTF-8 bytes, token |
| Unicode code point | Mã điểm Unicode | Một ký tự hiển thị có thể gồm nhiều code point |
| UTF-8 byte | Kích thước chuỗi sau encode | Không tính chính xác token của model |
| Token estimate | Ước tính context | Phụ thuộc tokenizer, metadata và provider |
| Usage thực tế | Thống kê từ provider | Thường chỉ có sau request |

Tiếng Việt có dấu, emoji, chuỗi JSON chứa nhiều dấu ngoặc và key lặp lại có thể có byte/token ratio rất khác nhau. Đừng dùng quy tắc bất biến như “4 ký tự = 1 token” để làm hard safety gate.

Một cấu hình phù hợp thường phối hợp:

1. **Hard cap**: số item, độ dài field, UTF-8 bytes của serialized result.
2. **Soft cap**: token ước tính của result và tổng prompt bằng tokenizer phù hợp.
3. **Safety margin**: chừa overhead tool schema, system messages, provider wrapper và output.
4. **Post-call usage**: quan sát provider usage để chỉnh budget và đo cost.

## Chia ngân sách cho toàn request

Ví dụ giả định model có context **32.000 token**:

| Thành phần | Ngân sách minh họa |
|---|---:|
| System/developer instructions | 2.000 |
| Tool definitions | 3.000 |
| Lịch sử/summary | 8.000 |
| Kết quả tool trong lượt đang xử lý | 10.000 |
| Dự phòng model output | 4.000 |
| Safety margin và overhead | 5.000 |
| **Tổng** | **32.000** |

Đây chỉ là phương án phân bổ của ứng dụng, không phải cấu hình mặc định Spring AI. Đọc giới hạn input/output và tokenizer từ model/provider thực tế. Chừa buffer vì tool arguments, tool response IDs và framing cũng tốn token.

Một policy minh họa:

~~~text
perToolHardBytes          = 16384
perToolEstimatedTokensCap = 3000
perTurnToolTokensCap      = 10000
maxPageItems              = 8
maxPreviewCodepoints      = 120
reservedModelOutputTokens = 4000
~~~

Nếu một vòng gọi ba tool, `perTurnToolTokensCap` là budget **dùng chung**, không phải mỗi tool được phép tiêu toàn bộ mức đó. Khi hết budget, từ chối mở rộng dữ liệu hoặc yêu cầu lọc hẹp hơn, không tự bỏ message đang cần khớp tool call ID. Đặt counter theo request/turn; với tool chạy đồng thời, việc trừ budget phải có kiểm soát đồng thời.

## Giảm kích thước từ nguồn trước khi serialize

Cách hiệu quả nhất là **đừng truy vấn thông tin không cần thiết**:

- SQL hoặc repository chỉ select cột thực sự cần; không đưa toàn bộ entity graph vào DTO.
- Lọc theo tenant, quyền xem, ngày tháng và điều kiện nghiệp vụ ngay tại query.
- Dùng `LIMIT`, keyset pagination và stable sort.
- Với câu hỏi tổng hợp, trả `COUNT`, `SUM`, grouping từ database thay vì hàng nghìn raw rows.
- Với văn bản dài, trả đoạn có liên quan, preview ngắn, trích dẫn và handle được phân quyền.
- Không đưa blob, toàn bộ PDF, stack trace hoặc raw HTTP headers vào result.

Tránh result thừa dữ liệu:

~~~json
{
  "orders": [
    {
      "orderId": "DH-1024",
      "customer": {"address": "...", "phone": "..."},
      "auditTrail": ["thousands of events"],
      "internalNotes": "sensitive content",
      "items": ["many nested objects"]
    }
  ]
}
~~~

Kết quả gọn và có ngữ nghĩa:

~~~json
{
  "status": "OK",
  "source": "orders-db",
  "asOf": "2026-11-27T13:00:00Z",
  "items": [
    {"orderId": "DH-1024", "status": "SHIPPED"}
  ],
  "returnedCount": 1,
  "hasMore": true,
  "nextCursor": "opaque-signed-cursor",
  "truncated": false
}
~~~

`hasMore=true` cho biết **chưa phải toàn bộ kết quả**. `truncated=false` chỉ nghĩa là không cắt nội dung các item đã trả, không phải đã gửi tất cả bản ghi. Chỉ công bố `totalCount` nếu upstream tính được chính xác và chi phí cho phép.

### Cursor và handle phải giữ phạm vi

Cursor phải do backend phát hành và kiểm tra; không nhận một điều kiện SQL do model tùy ý lắp ráp:

- Cursor opaque, ký MAC hoặc lưu server side, có TTL.
- Gắn với tenant, user/permission scope, query filter, sort key và snapshot/version nếu cần.
- Tái kiểm tra authorization ở **mỗi** lần lấy trang tiếp theo.
- Nếu dữ liệu thay đổi giữa các trang, quy định consistency và dedupe.
- Nếu cắt item **sau** khi query, phải phát cursor dựa trên **item cuối thực gửi**, không dựa trên cuối trang đã fetch; nếu không có thể bỏ sót.

## DTO nhỏ và pagination cho local @Tool

Các kiểu dữ liệu dưới đây là record của **ứng dụng minh họa**, không phải lớp có sẵn của Spring AI:

~~~java
import java.time.LocalDate;
import java.util.List;

record OrderSummary(
        String orderId,
        String status,
        LocalDate updatedOn,
        String shortDescription
) {}

record OrderPage(
        String status,
        List<OrderSummary> items,
        int returnedCount,
        boolean hasMore,
        String nextCursor,
        boolean truncated
) {}

record OrderRow(
        String id,
        String status,
        LocalDate updatedOn,
        String description
) {}

record OrderSlice(
        List<OrderRow> items,
        boolean hasMore,
        String nextCursor
) {}
~~~

Tool chỉ đọc và rút gọn dữ liệu:

~~~java
import java.util.List;

import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

@Component
public class OrderSearchTools {

    private static final int MAX_PAGE_SIZE = 8;
    private static final int PREVIEW_CODEPOINTS = 120;

    private final OrderSearchService orderSearchService;

    public OrderSearchTools(OrderSearchService orderSearchService) {
        this.orderSearchService = orderSearchService;
    }

    @Tool(description = "Tìm đơn hàng, trả một trang thông tin rút gọn")
    public OrderPage searchOrders(
            @ToolParam(description = "Từ khóa") String keyword,
            @ToolParam(description = "Số bản ghi, tối đa 8",
                       required = false) Integer pageSize,
            @ToolParam(description = "Cursor trang sau",
                       required = false) String cursor,
            ToolContext toolContext) {

        if (keyword == null || keyword.isBlank()) {
            throw new IllegalArgumentException("keyword is required");
        }
        if (keyword.codePointCount(0, keyword.length()) > 120) {
            throw new IllegalArgumentException("keyword is too long");
        }

        int requested = pageSize == null ? 5 : pageSize;
        if (requested < 1) {
            throw new IllegalArgumentException("pageSize must be positive");
        }
        int limit = Math.min(requested, MAX_PAGE_SIZE);

        String tenantId =
                (String) toolContext.getContext().get("tenantId");
        String userId =
                (String) toolContext.getContext().get("userId");

        // Service xác thực quyền, cursor và LIMIT trước khi truy vấn.
        OrderSlice slice = orderSearchService.searchVisible(
                tenantId, userId, keyword, limit, cursor
        );

        List<OrderSummary> items = slice.items().stream()
                .map(row -> new OrderSummary(
                        row.id(),
                        row.status(),
                        row.updatedOn(),
                        abbreviate(row.description(), PREVIEW_CODEPOINTS)
                ))
                .toList();

        boolean anyPreviewCut = slice.items().stream()
                .anyMatch(row -> row.description() != null
                        && row.description().codePointCount(
                                0, row.description().length()
                        ) > PREVIEW_CODEPOINTS);

        return new OrderPage(
                "OK", items, items.size(),
                slice.hasMore(), slice.nextCursor(), anyPreviewCut
        );
    }

    static String abbreviate(String value, int maxCodepoints) {
        if (value == null) {
            return "";
        }
        if (value.codePointCount(0, value.length())
                <= maxCodepoints) {
            return value;
        }
        int end = value.offsetByCodePoints(0, maxCodepoints);
        return value.substring(0, end) + "…";
    }
}
~~~

`abbreviate` cắt theo Unicode code points, không cắt giữa cặp surrogate. Nó chưa phải byte/token cap. `searchVisible` phải có authorization/filter/sort/LIMIT trong service. `tenantId` và `userId` phải đến từ backend `ToolContext`, không để model tự khai trong JSON arguments.

Trong ví dụ này, `truncated` cho biết một hay nhiều **mô tả của item** đã được rút gọn; `hasMore` độc lập cho biết **còn bản ghi khác**. Khi có yêu cầu provenance, nên bổ sung `source` và `asOf` được trả từ service thực tế, không để model tự đoán thời điểm đọc dữ liệu.

Đối với tool ghi, không dùng quy tắc “giảm dữ liệu bằng mọi giá” đến mức mất trạng thái commit, operation ID, amount/currency hoặc mã lỗi quan trọng.

## Hard cap tại ToolCallResultConverter

Spring AI dùng `ToolCallResultConverter` chuyển object do tool trả thành `String` gửi lại model; `DefaultToolCallResultConverter` dùng Jackson. Nếu DTO vẫn có field bất thường dài, sau khi serialize cần **giới hạn cuối cùng**.

Ví dụ converter dành cho **tool tra cứu chỉ đọc**:

~~~java
import java.lang.reflect.Type;
import java.nio.charset.StandardCharsets;

import org.springframework.ai.tool.execution.DefaultToolCallResultConverter;
import org.springframework.ai.tool.execution.ToolCallResultConverter;

public final class BoundedOrderResultConverter
        implements ToolCallResultConverter {

    private static final int MAX_UTF8_BYTES = 16 * 1024;

    private final ToolCallResultConverter delegate =
            new DefaultToolCallResultConverter();

    @Override
    public String convert(Object result, Type returnType) {
        String json = delegate.convert(result, returnType);

        if (json.getBytes(StandardCharsets.UTF_8).length
                <= MAX_UTF8_BYTES) {
            return json;
        }

        // Còn là JSON hợp lệ, không cắt thô phần giữa object.
        return """
            {
              "status": "RESULT_TOO_LARGE",
              "items": [],
              "hasMore": true,
              "truncated": true,
              "message": "Narrow query or reduce page size"
            }
            """;
    }
}
~~~

Để dùng converter này, **đổi annotation của cùng method `searchOrders`** đã trình bày ở ví dụ trên, không thêm method trùng tên:

~~~java
@Tool(
    description = "Tìm đơn hàng theo từ khóa, trả dữ liệu có giới hạn",
    resultConverter = BoundedOrderResultConverter.class
)
public OrderPage searchOrders(
        String keyword,
        Integer pageSize,
        String cursor,
        ToolContext toolContext) {
    // Giữ logic phân trang và kiểm tra quyền ở ví dụ trước.
}
~~~

Cần phân biệt:

- Converter thấy **chuỗi JSON cuối** sau khi default converter serialize; đây là vị trí phù hợp để kiểm tra byte.
- JSON error envelope nhỏ cho biết cần thu hẹp query, không giả vờ trả đầy đủ.
- Nếu overflow, gọi lại với **cursor đầu vào cũ** và page size nhỏ hơn; không phát cursor cuối trang giả vì trang đó chưa được trả.
- Giới hạn byte chỉ giảm kích thước transport; số token còn tùy tokenizer/model.
- Nếu một record đơn lẻ đã vượt, phải cắt field hoặc thay bằng handle có quyền, không chỉ giảm số trang.
- Với tool có **side effect**, không dùng fallback khiến model hiểu nhầm “chưa thực hiện”. Kết quả phải giữ operation ID và trạng thái đã commit.

Giới hạn `16 KiB` ở đây là **ví dụ của ứng dụng**, Spring AI không tự có hard cap mặc định cho kích thước từng tool result. Kết quả từ MCP server hoặc custom `ToolCallback` khác có thể không qua converter này; cần bọc callback hoặc giới hạn tại boundary tương ứng.

### Vì sao không dùng substring trên JSON?

Đoạn code sai:

~~~java
String json = converter.convert(result, resultType);
return json.substring(0, Math.min(json.length(), 8000));
~~~

Nó có thể cắt ngang string, để lại ngoặc chưa đóng, làm mất `hasMore`/`nextCursor`, cắt Unicode hoặc bỏ mất trạng thái source. Model có thể hiểu nhầm 8 item đầu là toàn bộ kết quả.

**Quy tắc:** giới hạn số item/độ dài field ở DTO **trước serialization**; nếu đã serialize mà vượt mức, trả một object lỗi nhỏ **vẫn là JSON hợp lệ**. Không tự ghép các phần JSON đã cắt hoặc giả mạo total count.

## Ngân sách token và byte phải kết hợp

Khi tính soft budget, cần dùng tokenizer gần với model/provider hoặc `TokenCountEstimator` được cấu hình cho session compaction. Ví dụ pseudo-interface của ứng dụng:

~~~java
public interface ResultTokenEstimator {
    int estimateTokens(String text);
}
~~~

Tầng điều phối có thể kiểm tra:

~~~java
String payload = toolResultConverter.convert(result, resultType);
int bytes = payload.getBytes(StandardCharsets.UTF_8).length;
int tokens = estimator.estimateTokens(payload);

if (bytes > maxResultBytes
        || tokens > remainingToolTokens) {
    return toolResultBudgetError();
}
return payload;
~~~

`toolResultBudgetError()` là hàm minh họa, phải tạo JSON hợp lệ hoặc status nghiệp vụ phù hợp. Nếu các tool chạy song song, việc trừ `remainingToolTokens` phải nguyên tử và theo phạm vi **turn hiện tại**, không dùng một static counter cho mọi request.

Token estimator chỉ là ước lượng. Provider có thể thêm wrapper message, tool-call ID, role và metadata; tính thêm safety margin. Nếu model context đã sát giới hạn, đừng gửi request rồi hy vọng provider tự cắt.

### Độ chính xác quan trọng hơn tối đa số item

Giảm dữ liệu không được làm mất:

- `source`, `asOf` và snapshot/version khi cần kiểm chứng.
- `status` cuối như `COMPLETED`, `QUEUED`, `UNKNOWN`, `PARTIAL`.
- Operation ID, payment ID, amount/currency trong thao tác ghi.
- `hasMore`, `nextCursor` để model biết dữ liệu chưa đầy đủ.
- `matchedCount` và `totalCount` chỉ khi tính thật, không được model tự đoán.
- Mã lỗi ổn định khi query bị thu hẹp hoặc tài nguyên bị từ chối.

Khi cần câu trả lời tổng hợp, database/service nên tính aggregate đáng tin (count/sum/group by) thay vì gửi hàng nghìn records để model tự đếm.

## Khi nào dùng summary, top-K, aggregate hoặc handle?

| Yêu cầu | Kết quả phù hợp |
|---|---|
| “Hôm nay có bao nhiêu đơn đang giao?” | `COUNT` từ database, kèm scope/thời điểm |
| “Đơn DH-1024 đang ở đâu?” | DTO một đơn và nguồn cập nhật |
| “Những đơn chậm nhất?” | Top-K theo thời gian và tiêu chí rõ |
| “Liệt kê toàn bộ đơn có vấn đề” | Trang đầu + cursor + filter |
| “Tổng hợp lỗi 7 ngày” | Group/count/snapshot + drill-down |
| “Đọc báo cáo PDF 200 trang” | Search chunks/snippets có page refs |
| “Tải CSV 100 MB” | URL/job download có ACL, TTL; không nhúng CSV trong prompt |

Khi tóm tắt bằng code/query, số liệu có thể được kiểm chứng. Với LLM-based summarization, hãy ghi lại refs, timestamp và kiểm thử tình huống bỏ sót hoặc suy diễn. Summary dài vài câu không thay thế bản ghi authoritative về tiền, authorization hoặc trạng thái tác vụ.

Handle không phải security token tự động. API dereference phải kiểm tra quyền và hạn dùng tại thời điểm người dùng/model muốn đọc lại.

## Return Direct giúp giảm vòng model khi nào?

Trong Spring AI, `@Tool(returnDirect = true)` cho phép trả kết quả trực tiếp tới caller thay vì gửi lại model để diễn giải:

~~~java
@Tool(
    description = "Trả trạng thái đã định dạng cho người dùng",
    returnDirect = true
)
public PublicOrderStatus getPublicStatus(String orderId) {
    return orderService.getPublicStatus(orderId);
}
~~~

Lợi ích là tránh một model round và tránh gửi payload cuối đó lại model. Tuy nhiên:

- Nếu model yêu cầu nhiều tool trong **cùng một response**, return-direct chỉ được áp dụng khi **tất cả** tool calls của response đều có `returnDirect=true`.
- Return-direct không giảm kích thước dữ liệu **gửi cho người dùng**: vẫn cần giới hạn bytes và phân quyền.
- Không dùng nếu model cần tổng hợp từ nhiều sources hoặc trả lời dựa trên kết quả.
- Với side effects, kết quả phải thể hiện trạng thái xác thực, không hứa “thành công” trước commit.

### Streaming không tự chia nhỏ tool result

`ChatClient.stream().content()` phát các chunk **câu trả lời model** cho UI; nó không biến return type của `@Tool` thành publisher mà mô hình tự xử lý qua các chunk. Nếu callback trả 100 KiB JSON, model round tiếp theo có thể vẫn nhận 100 KiB. Streaming giúp trải nghiệm hiển thị, không thay hard cap của tool result.

## Ba loại lịch sử khác nhau

| Loại lịch sử | Được quản lý bởi | Rủi ro tăng trưởng |
|---|---|---|
| **Trong tool loop** | `ToolCallingAdvisor` | Kết quả trước được gửi lại qua các model rounds |
| **Qua nhiều user turns** | Memory/session advisor | Những nội dung cũ tiếp tục nằm trong prompt |
| **Audit log/storage** | Repository, event store, logging | Dữ liệu lưu dài hạn không nhất thiết gửi lại model |

`ToolCallingAdvisor` 2.1.0 mặc định `conversationHistoryEnabled(true)` khi tự quản lý loop. Nó giữ user message, model tool-call messages và tool responses trong cùng turn rồi dùng lịch sử đó cho những lần gọi model tiếp theo.

Khi `MemoryAdvisor` nằm **bên trong** loop, advisor mặc định có thể tắt internal history để memory phụ trách xây prompt. Chỉ tắt `conversationHistoryEnabled` khi có cơ chế khác tiếp quản. Nếu không model mất kết quả tool trước và có thể gọi lại hoặc trả lời không đủ căn cứ.

### Các nhánh phiên bản

| Spring AI | Cơ chế chính |
|---|---|
| Spring AI 1.x | Vòng thực thi tool gắn với `ChatModel` trong nhiều ví dụ cũ |
| Spring AI 2.0.x | `ToolCallingAdvisor` qua `ChatClient`, memory advisor có thể nằm ngoài loop |
| Spring AI 2.1.0 | `Session Memory` và session advisors được khuyến nghị; `ChatMemory`/`MessageChatMemoryAdvisor` deprecated |

Không dùng mặc định `MessageWindowChatMemory` của hướng dẫn 1.x làm chiến lược dài hạn cho dự án đã nâng 2.1.0. Nếu đang ở 2.1.0, hãy phân biệt **log được lưu** và **active view được gửi cho model**.

## Session Memory trong Spring AI 2.1.0

`SessionAdvisors` gồm:

- `SessionTurnAdvisor` ở ngoài loop: quản lý một user turn, persist thông điệp kết thúc và kích hoạt compaction **sau** request.
- `SessionMemoryAdvisor` ở trong loop: nạp active view, lưu messages/tool results và xây lại prompt từng model round.

Session có append-only event log; model chỉ nhận active view do filter/compaction chọn. Như vậy có thể giảm chi phí prompt mà không tự động xóa dữ liệu nguồn khỏi audit log.

### Ví dụ: EventFilter + token-based compaction

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.session.advisor.SessionAdvisors;
import org.springframework.ai.session.compaction.TokenCountTrigger;
import org.springframework.ai.session.compaction.WindowCompactionStrategy;
import org.springframework.ai.session.EventFilter;

// sessionService là SessionService đã cấu hình storage.
ChatClient client = ChatClient.builder(chatModel)
        .defaultAdvisors(
                SessionAdvisors.builder(sessionService)
                        .compaction(
                                TokenCountTrigger.builder()
                                        .threshold(8000)
                                        .build(),
                                WindowCompactionStrategy.builder()
                                        .tokenBudget(5000)
                                        .build()
                        )
                        .memory(memory -> memory.eventFilter(
                                EventFilter.lastN(30)
                        ))
                        .build()
        )
        .defaultTools(orderSearchTools)
        .build();

String answer = client.prompt()
        .user("Có đơn hàng nào đang giao?")
        .advisors(SessionAdvisors.session(sessionId))
        .call()
        .content();
~~~

`sessionService`, `orderSearchTools` và `sessionId` là bean/giá trị ứng dụng cung cấp. `sessionId` phải gắn với người dùng/tenant đã xác thực, không dùng một ID chung cho mọi khách hàng.

Ý nghĩa:

- `EventFilter.lastN(30)` chọn những sự kiện gần đây, nhưng **không bảo đảm đúng 30**.
- `TokenCountTrigger.threshold(8000)` quyết định khi nào compact active view theo token ước tính.
- `WindowCompactionStrategy.tokenBudget(5000)` chọn cửa sổ sau compaction.
- `5.000 token` **không phải** hard cap cho toàn prompt: system prompt, tool definitions, user input, kết quả mới, overhead vẫn tính riêng.

**Giới hạn quan trọng:** compaction mặc định diễn ra **sau khi turn hoàn tất**. Nó cũng cố giữ nguyên newest turn, kể cả turn đó quá budget. Vì vậy, một tool result khổng lồ ở turn hiện tại vẫn có thể làm vượt context trước khi compaction chạy. **Per-tool limit phải thực hiện trước vòng model kế tiếp**.

### Window không được cắt giữa cặp tool call/response

`EventFilter.lastN(n)` trong 2.1.0 là turn-aware: nếu cắt tại một event nằm giữa turn, view được mở rộng tới đầu turn liên quan. Điều này giúp không giữ tool response mà mất assistant tool call tương ứng.

Do đó `lastN(30)` có thể trả hơn 30 events nếu newest turn dài. Đây là lựa chọn giữ tính toàn vẹn thông điệp. Đừng tự sửa lịch sử bằng cách xóa “mọi message cũ” nếu có nguy cơ phá tool call IDs hoặc thứ tự provider yêu cầu.

### Compaction không tự xóa audit log

`SessionService.compact(...)` ghi boundary, summary và active view mới; event log cũ vẫn tồn tại. Vì vậy:

- Giảm active history **không đồng nghĩa** giảm dung lượng lưu trữ.
- Cần retention, TTL, ACL riêng cho session repository/audit.
- Summary cần giữ operation ID và trạng thái đã xác minh; model-generated summary không phải bằng chứng commit.
- Nếu compaction lỗi, bị bỏ qua hoặc newest turn quá lớn, view có thể còn dài. Guard phía trước model vẫn cần thiết.

## Tóm tắt lịch sử mà không làm mất trạng thái nghiệp vụ

Khi cuộc trò chuyện kéo dài, chỉ giữ N turns gần đây có thể làm model quên ràng buộc quan trọng. Có thể kết hợp window với **structured summary** hoặc retrieval:

- Mục tiêu người dùng hiện tại.
- Entity/operation IDs còn liên quan.
- Quyền và approval hiện hành **do backend xác minh lại**.
- Tool nào đã tạo side effect, trạng thái đã đối soát.
- Bước chưa xong, lỗi chưa được xử lý và hành động hợp lệ tiếp theo.
- Source refs, timestamp, chính sách kiểm chứng của dữ liệu.
- Thông tin nào đã quá hạn hoặc bị thu hồi quyền.

Trong 2.1.0, compaction có thể dùng summarizer để biến phần lịch sử rời active view thành một summary turn. Cần đo chất lượng, vì mô hình tóm tắt có thể bỏ mất chi tiết. **Không** để một summary model tự viết thay database/ledger cho xác nhận thanh toán hay idempotency.

Nếu muốn truy hồi một nội dung cũ, hãy dùng tool đọc đúng nguồn có ACL thay vì luôn mang toàn bộ lịch sử qua mọi vòng. Tóm tắt không được tự biến một quyền user có từ trước thành quyền hiện tại.

## Giữ lịch sử tool call và tool response hợp lệ

Một số provider yêu cầu thông điệp assistant có tool call ID phải đi cùng các tool response tương ứng trong đúng cấu trúc. Xóa tùy ý một nửa trong pair có thể gây lỗi request hoặc khiến model nhầm lẫn.

Các nguyên tắc:

- Không cắt chuỗi lịch sử giữa một assistant tool call và tool response thuộc call đó.
- Không tự thay tool call ID khi rút gọn content.
- Khi có nhiều tool call trong cùng response, giữ ánh xạ mỗi ID tới đúng result.
- Không đổi thứ tự message nếu provider đòi hỏi tool results liền sau lời gọi.
- Dùng turn-aware `EventFilter`/session compaction hoặc tự kiểm tra sequence khi chủ động điều khiển loop.
- Nếu rút gọn result, giữ **cùng ID** và trả một nội dung kết quả có cấu trúc, không để thiếu response.

Một vòng tool calling đã diễn ra có thể có response `RESULT_TOO_LARGE`; đó vẫn là một **tool response** hợp lệ được gắn với call ID. Việc model dùng response để chọn query hẹp hơn là khác với việc backend bỏ luôn thông điệp response.

## Bảo mật và giảm dữ liệu nhạy cảm

Giới hạn output là cơ hội làm **data minimization**, nhưng không thay thế authorization:

- Chỉ truy vấn những cột user được phép nhìn thấy, không trả nguyên entity JPA.
- Loại bỏ PII, access token, internal notes, mật khẩu, stack trace, SQL chi tiết và header nhạy cảm trước converter.
- Cung cấp `tenantId`/`userId` qua `ToolContext` đáng tin; từng trang/query phải re-authorize.
- Nếu dùng handle/URL tải nội dung, gắn thời hạn và quyền; không đưa local path thô cho model.
- Result từ MCP hoặc API ngoài là dữ liệu **không đáng tin**; một result dài có thể chứa prompt injection, không được tự đổi system policy.
- Không log raw arguments hoặc raw result chỉ để tính metric; metric nên dùng bytes, token estimate, tên tool, status code và duration.
- Với `returnDirect`, dữ liệu vẫn tới caller nên giới hạn response và ACL còn nguyên.

Nếu tool có side effect đã commit, converter phải giữ được trạng thái đã xác minh. Không được tạo một error envelope khiến model hiểu “đã hủy thao tác” trong khi provider đã hoàn tiền thành công.

## Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `context_length_exceeded` | Tool result/historical prompt quá dài | Giới hạn source, result, active history |
| Token bill tăng theo số vòng | Cùng result bị gửi lại ở nhiều iterations | Rút gọn DTO, giảm vòng, đo usage tích lũy |
| Model nói “chỉ có 8 đơn” | Không có `hasMore` | Giữ pagination metadata |
| JSON parse error | Cắt raw serialized JSON | Truncation theo cấu trúc |
| Missing tool response/tool call ID | Cắt giữa cặp message | Turn-aware filter, giữ ID |
| Compaction xong vẫn quá token | Newest turn quá lớn | Per-tool guard trước vòng model |
| Model lặp lại query quá lớn | Result không hướng dẫn cách thu hẹp | Trả status `RESULT_TOO_LARGE` và hướng dẫn rõ |
| Lộ PII dù DTO nhỏ | Projection không dựa quyền | Filter ở DB/service, test tenant |
| Cursor bỏ sót bản ghi | Lấy cursor cuối trang trước khi giảm item | Cursor theo item cuối thực trả |
| Câu trả lời thiếu dẫn chứng | Summary bỏ source/time | Giữ provenance và truy hồi theo source |
| Tool ghi bị báo thất bại sau overflow | Đánh đồng output size với business outcome | Đối soát và trả trạng thái authoritative |
| `stream()` vẫn lỗi context | Streaming không làm nhỏ input model | Limit tool result/history thực sự |

## Kiểm thử giới hạn ở ba tầng

### 1. Converter trả JSON hợp lệ, byte không vượt ngưỡng

~~~java
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.List;

@Test
void converterShouldBoundUtf8Bytes() {
    var converter = new BoundedOrderResultConverter();

    String huge = "Đơn hàng 📦 ".repeat(3000);
    OrderPage result = new OrderPage(
            "OK",
            List.of(new OrderSummary(
                    "DH-1024", "SHIPPED",
                    LocalDate.of(2026, 11, 27), huge
            )),
            1, false, null, false
    );

    String serialized = converter.convert(result, OrderPage.class);

    assertThat(
            serialized.getBytes(StandardCharsets.UTF_8).length
    ).isLessThanOrEqualTo(16 * 1024);

    JsonNode parsed = jsonMapper.readTree(serialized);
    assertThat(parsed.path("status").asString())
            .isEqualTo("RESULT_TOO_LARGE");
}
~~~

`jsonMapper` là fixture Jackson 3 `tools.jackson.databind.ObjectMapper` của test Spring AI 2.1.0/Spring Boot 4. Với Jackson 2 cần đổi import và getter API tương ứng. Không chỉ test `String.length()` vì Unicode có độ dài UTF-8 khác.

### 2. Tool trả đúng page size và quyền người dùng

~~~java
@Test
void searchToolShouldReturnAuthorizedBoundedPage() {
    ToolContext context = new ToolContext(Map.of(
            "tenantId", "tenant-A",
            "userId", "user-7"
    ));

    OrderPage result = tools.searchOrders(
            "đang giao", 1000, null, context
    );

    assertThat(result.items()).hasSizeLessThanOrEqualTo(8);
    assertThat(result.returnedCount())
            .isEqualTo(result.items().size());

    assertThat(result.items()).allSatisfy(item -> {
        String description = item.shortDescription();
        assertThat(description.codePointCount(0, description.length()))
                .isLessThanOrEqualTo(121);
    });

    verify(orderSearchService).searchVisible(
            "tenant-A", "user-7", "đang giao", 8, null
    );
}
~~~

Đây là test contract khi mock `OrderSearchService` đã được cấu hình trả một `OrderSlice` hợp lệ. Tách test cho cursor giả, tenant khác, query rỗng, `pageSize=0`, Unicode dài và kết quả một item quá lớn.

### 3. Test callback thật và tool-result history

Lấy callback từ `ToolCallbacks.from(orderSearchTools)` và gọi `callback.call(jsonArgs, toolContext)` để đi qua schema, conversion và result converter. Xác minh:

- Chuỗi output là JSON parse được, kích thước thực không vượt hard cap.
- Với truy vấn nhiều dữ liệu, trạng thái `RESULT_TOO_LARGE` được xử lý an toàn.
- Model không nhận field nhạy cảm hoặc raw SQL.
- Result trả `hasMore` đúng và cursor hợp lệ.
- Các message assistant tool call và tool response khớp ID.
- Trong vòng model thứ hai, result cũ được giới hạn, không vô tình trở về payload raw.
- Có test riêng cho `.call()` và `.stream()` nếu ứng dụng hỗ trợ cả hai.

Không chỉ gọi trực tiếp `tools.searchOrders(...)` rồi cho rằng callback converter đã được test; direct method invocation bỏ qua bước Spring AI serialize.

## Test session view và compaction

Với `SessionService` dùng repository test:

1. Thêm nhiều turns, trong đó một turn có assistant tool call và tool response.
2. Áp dụng `EventFilter.lastN(2)` và xác minh view vẫn không bị cắt giữa cặp tool call–response.
3. Chạy compaction bằng `TokenCountTrigger` và `WindowCompactionStrategy`.
4. Xác minh active view giảm khi có những turns được phép cover.
5. Xác minh original event log vẫn còn theo retention của repository.
6. Tạo newest turn dài hơn budget và chứng minh compaction **không đảm bảo** làm nó nhỏ hơn ngưỡng.
7. Xác minh tool result guard chặn oversize trước lượt model kế tiếp.
8. Dùng session ID của tenant khác và xác minh không thể đọc lịch sử trái quyền.

Vì `EventFilter.lastN(n)` giữ turn boundaries, số event trả về có thể lớn hơn `n`. Test không nên assertion cứng `size() == n`. Với token budget, cần đo thêm system prompt/pinned messages và các thành phần context nằm ngoài session.

## Metrics hiệu năng và chi phí

| Metric | Công dụng |
|---|---|
| `tool_result_bytes_raw` | Kích thước data từ source trước projection |
| `tool_result_bytes_sent` | Kích thước JSON sau converter |
| `tool_result_tokens_estimated` | Ước tính số token result |
| `tool_result_reduction_ratio` | Tỷ lệ giảm raw → sent |
| `tool_result_overflow_count` | Số lần không thể trả đủ result |
| `tool_pages_fetched` | Số trang model yêu cầu |
| `tool_calls_per_turn` | Tool calls mỗi turn |
| `prompt_tokens_cumulative` | Tổng input tokens nhiều vòng |
| `completion_tokens_cumulative` | Tổng output tokens nhiều vòng |
| `session_active_view_tokens` | Token estimate của view gửi model |
| `compaction_count` | Số lần compaction |
| `compaction_tokens_estimated_saved` | Token dự kiến tiết kiệm |
| `p95_workflow_latency` | Độ trễ end-to-end |
| `answer_grounded_rate` | Mức đúng/supported của câu trả lời |
| `tool_result_miss_rate` | Case không đủ kết quả sau rút gọn |

Một result rất ngắn vẫn có thể khiến model phải gọi thêm tool, làm tổng chi phí cao hơn. Vì vậy phải đo **quality, số vòng, token, latency và business outcome** cùng nhau.

### So sánh A/B

Chạy cùng bộ câu hỏi trên môi trường test:

- **A:** policy hiện tại.
- **B:** source projection, page size nhỏ, converter hard cap và session compaction.

Báo trung bình/P95 token, số tool calls, completion rate, tỉ lệ `RESULT_TOO_LARGE`, accuracy và latency. Với model không hoàn toàn tất định, chạy nhiều lần và phân loại tác vụ. Không tối ưu chỉ từ một testcase.

## Checklist trước khi triển khai

- [ ] Biết context window, input/output token giới hạn và tokenizer thực của model.
- [ ] Tách ngân sách cho system, tool definitions, history, tool results và model output.
- [ ] Tool đọc dùng filter, projection, stable order và LIMIT ở source.
- [ ] Có page size cap, signed cursor, TTL và authorization theo từng trang.
- [ ] Không trả raw entity chứa PII/secret.
- [ ] Có giới hạn số item và độ dài từng field trước serialization.
- [ ] Có hard cap UTF-8 bytes **sau** serialization và token estimate.
- [ ] Không cắt raw JSON bằng substring.
- [ ] `status`/`hasMore`/`nextCursor` phản ánh đúng phần đã trả và phần chưa trả.
- [ ] Với tool ghi, trạng thái commit và operation ID không bị mất bởi rút gọn output.
- [ ] Có tổng ngân sách cho nhiều tool calls và deadline toàn request.
- [ ] Session memory/compaction đúng version và scope theo user/tenant.
- [ ] Không cắt giữa tool call và tool response.
- [ ] Hiểu compaction sau turn không thay per-tool guard.
- [ ] Có test Unicode, byte cap, JSON hợp lệ, tenant, cursor, memory và multi-round.
- [ ] Đo usage tích lũy, cost, latency và chất lượng trả lời trước khi phát hành.

## Ghi nhớ

Để giới hạn chi phí Tool Calling, hãy **giảm kết quả ở source**, dùng **DTO nhỏ và pagination**, rồi kiểm tra serialized result trước khi đưa nó cho model. Giữ trạng thái, nguồn, thời điểm, thông tin phân trang và các giá trị nghiệp vụ cần kiểm chứng. Không cắt raw JSON và không trình bày một trang như toàn bộ dữ liệu.

`ToolCallingAdvisor` có thể gửi lại tool results cũ trong nhiều vòng, khiến chi phí tăng nhanh. Spring AI 2.1.0 có `SessionAdvisors`, `EventFilter` và compaction để quản lý active history giữa các turns. Nhưng chúng **không thể thay thế** byte/token cap ngay tại tool result của turn hiện tại. Cần kết hợp nhiều lớp giới hạn, quyền truy cập và kiểm thử chất lượng.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling: Result Conversion, Limits, Return Direct](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — ToolCallingAdvisor: Conversation History](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1.0 — ChatClient Session Integration](https://docs.spring.io/spring-ai/reference/api/session/chat-client.html)
- [Spring AI 2.1.0 — Event Filtering](https://docs.spring.io/spring-ai/reference/api/session/event-filter.html)
- [Spring AI 2.1.0 — Session Compaction](https://docs.spring.io/spring-ai/reference/api/session/compaction.html)
- [Spring AI 2.1.0 — Chat Memory Deprecated API](https://docs.spring.io/spring-ai/reference/api/chat-memory.html)
- [Spring AI 2.1.x Javadoc — DefaultToolCallResultConverter](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/execution/DefaultToolCallResultConverter.html)





