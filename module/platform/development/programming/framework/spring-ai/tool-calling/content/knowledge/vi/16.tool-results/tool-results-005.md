# Giới hạn kích thước, phân trang và rút gọn dữ liệu trả về

Kết quả một tool được serialize thành chuỗi và thường được gửi trở lại mô hình trong cùng lịch sử hội thoại. Nếu tool trả quá nhiều bản ghi, trường dài hoặc payload lớn, request tiếp theo có thể tốn nhiều token, tăng độ trễ, vượt giới hạn context window hoặc làm mô hình bỏ qua dữ liệu quan trọng. Vì vậy, giới hạn kích thước phải được áp dụng ngay ở truy vấn nghiệp vụ và DTO kết quả; không nên đợi đến lúc serialize xong mới cắt chuỗi JSON.

Bài học này xây dựng chiến lược trả dữ liệu vừa đủ: đặt giới hạn cứng ở server, chọn đúng trường bằng projection, phân trang theo cursor ổn định, dùng top-K và summary khi phù hợp, chia nhỏ dữ liệu lớn theo chunk có kiểm soát, và biểu diễn rõ khi kết quả đã bị giới hạn. Mục tiêu là để mô hình nhận được dữ liệu đủ trả lời câu hỏi mà vẫn giữ được khả năng truy xuất phần còn lại khi cần.

## 1. Vì sao phải giới hạn tool result?

Trong vòng tool calling, callback trả một object Java. Spring AI chuyển object đó thành `String` bằng `ToolCallResultConverter` (mặc định dùng Jackson), rồi tool response được đưa vào lịch sử để mô hình tiếp tục xử lý. Vì vậy, payload của tool result tiêu thụ token trong context window giống như các message khác.

Kết quả quá lớn gây ra nhiều vấn đề:

- Tăng token đầu vào ở lượt mô hình tiếp theo, làm tăng chi phí và độ trễ.
- Chiếm chỗ của system prompt, câu hỏi người dùng, lịch sử hội thoại và các kết quả tool khác.
- Dữ liệu quan trọng có thể bị mô hình chú ý kém khi lẫn trong nhiều bản ghi lặp lại.
- JSON lớn làm tăng bộ nhớ, thời gian serialize/parse và tải lên service phụ thuộc.
- Có thể vượt giới hạn request/context của model hoặc giới hạn response của provider.
- Tăng nguy cơ trả thừa PII, dữ liệu nội bộ hoặc thông tin không cần thiết.

Không có một con số byte hay token dùng được cho mọi model. Context window, tokenizer, output budget và cách provider tính tool messages khác nhau. Ứng dụng cần đặt budget riêng dựa trên model đang dùng, prompt thực tế và mức an toàn cần chừa cho câu trả lời cuối.

## 2. Đặt budget trước khi truy vấn

Giới hạn nên được thiết kế theo nhiều lớp, thay vì chỉ có một giới hạn `limit` trong câu SQL:

| Lớp giới hạn | Ví dụ | Mục đích |
| --- | --- | --- |
| Số phần tử | Tối đa 20 khách hàng/trang | Không trả quá nhiều bản ghi |
| Kích thước từng trường | Tối đa 500 ký tự cho mô tả | Chặn trường văn bản dài bất thường |
| Tổng payload | Ví dụ 32 KB JSON cho một tool result | Giới hạn chi phí serialize/truyền |
| Ngân sách token | Ví dụ mục tiêu 4.000 token cho tool result | Chừa chỗ cho prompt và câu trả lời |
| Thời gian truy vấn | Timeout theo SLA của tool | Không để tool chặn vòng hội thoại quá lâu |
| Số vòng gọi | Giới hạn số trang/chunk mỗi lượt | Ngăn mô hình lặp gọi vô hạn |

Các con số trong bảng chỉ là ví dụ khởi đầu, không phải giới hạn mặc định của Spring AI hay provider. Hãy đo trên dữ liệu thật và cấu hình theo model/context window thực tế.

Có thể tính budget khả dụng theo nguyên tắc:

\[B_{tool} = W_{context} - T_{system} - T_{user} - T_{history} - B_{answer} - B_{safety}\]

Trong đó `W_context` là context window của model; các thành phần còn lại là token dành cho system prompt, câu hỏi, lịch sử, câu trả lời dự kiến và phần dự phòng. Tổng tool results của một lượt phải nằm trong budget còn lại. Nếu có nhiều tool call trong cùng lượt, không cấp toàn bộ budget cho từng tool một cách độc lập.

Đếm byte JSON là kiểm tra kỹ thuật hữu ích nhưng không tương đương số token. Token phụ thuộc tokenizer và nội dung; tiếng Việt, mã định danh, JSON key và chuỗi dài có thể có tỷ lệ byte/token khác nhau. Với dữ liệu quan trọng, hãy dùng tokenizer phù hợp với model hoặc đặt giới hạn byte bảo thủ rồi theo dõi token usage từ response metadata.

## 3. Thiết kế DTO nhỏ và chọn trường có chủ đích

Đừng trả entity database hoặc toàn bộ DTO nội bộ chỉ vì chúng có sẵn. Hãy tạo projection dành riêng cho câu hỏi mà tool giải quyết:

```java
public record CustomerSummary(
        String customerId,
        String displayName,
        String status,
        String city) {
}
```

Nếu câu hỏi chỉ cần tên và trạng thái khách hàng, không trả địa chỉ đầy đủ, số điện thoại, ghi chú nội bộ, lịch sử giao dịch hay các quan hệ ORM. Một DTO gọn giảm payload, giảm nguy cơ lộ dữ liệu và giúp mô hình tập trung vào các trường cần thiết.

Có thể giới hạn chuỗi ngay khi ánh xạ:

```java
static String abbreviate(String value, int maxChars) {
    if (value == null || value.length() <= maxChars) {
        return value;
    }
    return value.substring(0, maxChars);
}

CustomerSummary toSummary(Customer customer) {
    return new CustomerSummary(
            customer.getCode(),
            abbreviate(customer.getDisplayName(), 120),
            customer.getStatus().name(),
            customer.getCity());
}
```

Rút gọn chuỗi cần có quy tắc rõ ràng. Nếu phần bị cắt có thể làm thay đổi ý nghĩa, trả cờ `descriptionTruncated` hoặc một trường `contentPreview` kèm thông tin có thể lấy bản đầy đủ qua trang/chunk tiếp theo. Không âm thầm cắt một trường quan trọng rồi để mô hình tưởng đó là nội dung đầy đủ.

## 4. Giới hạn ở tầng truy vấn, không chỉ ở DTO

Giới hạn DTO sau khi query không ngăn database đọc hàng trăm nghìn dòng. Đặt `LIMIT`, `Pageable`, projection hoặc truy vấn top-K ngay trong repository/service để giới hạn công việc từ đầu.

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;
import com.example.Customer;
import com.example.CustomerSummary;
public interface CustomerRepository extends Repository<Customer, Long> {

    @Query("""
        select new com.example.CustomerSummary(
            c.code, c.displayName, c.status, c.city)
        from Customer c
        where c.tenantId = :tenantId
          and c.status = :status
        order by c.displayName asc, c.id asc
        """)
    Slice<CustomerSummary> findSummaries(
            @Param("tenantId") String tenantId,
            @Param("status") String status,
            Pageable pageable);
}
```

Ở tầng service, ép giới hạn server-side kể cả khi mô hình yêu cầu page size lớn:

```java
private static final int DEFAULT_PAGE_SIZE = 10;
private static final int MAX_PAGE_SIZE = 25;

int effectiveSize(int requestedSize) {
    if (requestedSize <= 0) {
        return DEFAULT_PAGE_SIZE;
    }
    return Math.min(requestedSize, MAX_PAGE_SIZE);
}
```

Không để mô hình tự quyết định `MAX_PAGE_SIZE`, timeout hoặc tổng số bản ghi được trả. Arguments do mô hình sinh chỉ là yêu cầu; server luôn áp dụng giới hạn cứng.

## 5. Phân trang offset và cursor

Khi có nhiều kết quả phù hợp, trả một trang nhỏ cùng metadata để mô hình quyết định có cần trang tiếp theo hay không.

### Offset pagination

Offset pagination dùng `page`/`size` hoặc `offset`/`limit`. Nó dễ hiểu và phù hợp với tập dữ liệu nhỏ, có thứ tự ổn định:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
Slice<CustomerSummary> slice = customerService.search(
        tenantId,
        status,
        PageRequest.of(pageNumber, effectiveSize(requestedSize),
                Sort.by("displayName").ascending().and(Sort.by("id").ascending())));
```

Nhược điểm: offset lớn có thể tốn kém; khi dữ liệu được thêm/xóa giữa hai lần gọi, bản ghi có thể bị lặp hoặc bỏ sót. Không dùng thứ tự không ổn định như chỉ sort theo tên nếu tên có thể trùng; hãy thêm khóa duy nhất làm tie-breaker.

Trong Spring Data, `Page` thường cần count để biết tổng số phần tử, còn `Slice` chỉ cần biết có trang tiếp theo. Nếu tool chỉ cần `hasMore` và không cần `totalElements`, ưu tiên `Slice` để tránh count query. Với truy vấn lớn, cân nhắc keyset scrolling.

### Cursor/keyset pagination

Cursor pagination phù hợp hơn với tập dữ liệu lớn hoặc thay đổi liên tục. Cursor chứa vị trí cuối cùng của trang trước, ví dụ `(displayName, id)`, và trang sau truy vấn các bản ghi đứng sau vị trí đó:

```sql
SELECT id, code, display_name, status
FROM customer
WHERE tenant_id = :tenantId
  AND status = :status
  AND (display_name, id) > (:lastName, :lastId)
ORDER BY display_name ASC, id ASC
LIMIT :pageSizePlusOne;
```

Cú pháp tuple comparison tùy database; có thể viết thành điều kiện tương đương với `display_name > :lastName OR (display_name = :lastName AND id > :lastId)`. Lấy `pageSize + 1` phần tử để biết còn trang tiếp theo hay không mà không cần count toàn bộ bảng.

Cursor nên là token opaque với mô hình. Ứng dụng có thể encode và ký số cursor hoặc lưu cursor state phía server. Không cho phép client/model sửa tenant, filter hoặc sort trong cursor. Khi nhận cursor, xác minh nó thuộc subject/tenant, query filter và phiên bản tìm kiếm hiện tại; đặt thời hạn nếu cursor có thể tồn tại lâu.

## 6. DTO cho trang kết quả

Một page DTO nên cho biết có bao nhiêu item được trả, còn trang tiếp theo hay không và cách yêu cầu trang tiếp theo:

```java
public record PageInfo(
        int pageSize,
        boolean hasMore,
        String nextCursor) {
}

public record CustomerSearchResult(
        List<CustomerSummary> items,
        PageInfo page) {
}

public record CustomerSearchRequest(
        String keyword,
        Integer pageSize,
        String cursor) {
}
```

Ví dụ tool nhận request có cursor:

```java
@Tool(description = "Tìm khách hàng theo từ khóa. Mỗi lần trả tối đa 25 kết quả; dùng nextCursor để lấy trang tiếp theo khi cần.")
public ToolResult<CustomerSearchResult> searchCustomers(
        @ToolParam(description = "Từ khóa tìm kiếm") String keyword,
        @ToolParam(description = "Cursor từ trang trước; bỏ trống ở trang đầu", required = false) String cursor,
        @ToolParam(description = "Số kết quả mong muốn, server giới hạn tối đa 25", required = false) Integer pageSize,
        ToolContext toolContext) {

    CallerContext caller = requireCaller(toolContext);
    int size = effectiveSize(pageSize == null ? DEFAULT_PAGE_SIZE : pageSize);
    return customerSearchService.search(caller, keyword, cursor, size);
}
```

`ToolContext` không phải một trường trong input schema. `CallerContext` lấy từ context chứa tenant/user đã xác thực; service phải kiểm tra quyền trước khi truy vấn. Cursor và keyword là arguments do mô hình đề xuất nên cần validate và ràng buộc với tenant hiện tại.

JSON kết quả ví dụ:

```json
{
  "status": "SUCCESS",
  "code": "CUSTOMERS_PAGE",
  "data": {
    "items": [
      {"customerId":"C-100","displayName":"Nguyen An","status":"ACTIVE","city":"HCMC"},
      {"customerId":"C-101","displayName":"Tran Binh","status":"ACTIVE","city":"HCMC"}
    ],
    "page": {
      "pageSize": 2,
      "hasMore": true,
      "nextCursor": "cursor_v1_7f31a9c2.signature"
    }
  },
  "meta": {
    "returnedCount": 2,
    "truncated": false
  }
}
```

Đừng dùng `totalElements` nếu count chính xác tốn kém và không cần thiết. `hasMore` cùng `nextCursor` thường đủ để điều phối trang tiếp theo.

## 7. Cursor phải ràng buộc với truy vấn và người gọi

Cursor không phải quyền truy cập. Một cursor hợp lệ về cú pháp vẫn có thể được dùng sai tenant hoặc với filter khác. Khi tạo cursor, gắn các thông tin cần thiết ở phía server:

- `tenantId` và phạm vi người gọi được phép truy cập.
- Filter chuẩn hóa, ví dụ keyword/status.
- Sort key và khóa tie-breaker.
- Vị trí cuối trang hoặc snapshot/version.
- Thời điểm hết hạn và phiên bản định dạng cursor.

Khi nhận cursor, so khớp các trường với request hiện tại và kiểm tra authorization lại. Nếu cursor được ký HMAC, chữ ký chỉ đảm bảo nội dung không bị sửa; nó không thay thế việc xác thực người gọi hoặc kiểm tra quyền.

Không đưa dữ liệu cá nhân hoặc thông tin bí mật vào cursor dạng base64 rồi xem nó là mã hóa. Base64 chỉ là encoding. Nếu cursor cần chứa dữ liệu nhạy cảm, dùng token ngẫu nhiên tham chiếu state phía server hoặc cơ chế mã hóa đã được kiểm chứng.

## 8. Top-K và xếp hạng thay cho trả toàn bộ

Với câu hỏi như “5 sản phẩm bán chạy nhất” hoặc “khách hàng có số dư lớn nhất”, mô hình thường chỉ cần top-K. Hãy đẩy ranking và aggregation xuống database/search engine thay vì tải tất cả rồi sort trong Java:

```sql
SELECT product_code, SUM(quantity) AS sold_quantity
FROM order_line
WHERE tenant_id = :tenantId
  AND created_at >= :fromDate
GROUP BY product_code
ORDER BY sold_quantity DESC, product_code ASC
LIMIT :topK;
```

Giới hạn `topK` bằng giá trị tối đa phía server. Kết quả nên ghi rõ tiêu chí và khoảng thời gian xếp hạng:

```json
{
  "status": "SUCCESS",
  "code": "TOP_PRODUCTS",
  "data": {
    "rankingMetric": "soldQuantity",
    "period": {"from":"2026-11-01","to":"2026-11-27"},
    "items": [
      {"rank":1,"productCode":"P-01","soldQuantity":920},
      {"rank":2,"productCode":"P-07","soldQuantity":810}
    ]
  },
  "meta": {"returnedCount":2,"limit":10,"hasMore":false}
}
```

Khi trả top-K, mô tả đây là danh sách đứng đầu theo tiêu chí và thời gian đã nêu, không phải toàn bộ tập dữ liệu. Nếu người dùng muốn xem các kết quả tiếp theo, cung cấp cursor hoặc một tool truy vấn trang kế tiếp.

## 9. Rút gọn bằng aggregation và summary

Không phải câu hỏi nào cũng cần từng bản ghi. Với câu hỏi tổng quan, trả aggregation thường hữu ích hơn:

| Câu hỏi | Kết quả nên ưu tiên |
| --- | --- |
| Tổng doanh thu tháng này? | Tổng, tiền tệ, khoảng thời gian và nguồn |
| Có bao nhiêu đơn theo trạng thái? | Count theo từng status |
| Xu hướng tồn kho? | Tổng hợp theo ngày/tuần, không phải mọi giao dịch |
| Có vấn đề nào đáng chú ý? | Top anomaly kèm metric và ngưỡng |
| So sánh hai chi nhánh? | Bảng so sánh các chỉ số liên quan |

Ví dụ DTO summary:

```java
public record StatusCount(String status, long count) {
}

public record OrderSummaryData(
        long totalOrders,
        List<StatusCount> countsByStatus,
        Instant dataAsOf) {
}
```

Aggregation nên được tính từ dữ liệu nguồn hoặc query chuyên biệt. Không để mô hình tự cộng hàng nghìn bản ghi nếu database có thể trả tổng chính xác. Nếu trả summary do một thuật toán tạo ra, ghi rõ phương pháp/định nghĩa metric để tránh diễn giải nhầm.

## 10. Chunking cho nội dung lớn

Có những tool phải đọc nội dung dài như tài liệu, log hoặc bản ghi hội thoại. Thay vì trả toàn bộ, chia nội dung thành chunk có giới hạn và cung cấp định danh để lấy tiếp:

```java
public record TextChunk(
        String documentId,
        int chunkIndex,
        int totalChunks,
        String content,
        String nextCursor) {
}
```

Kích thước chunk nên được đo theo token hoặc giới hạn ký tự bảo thủ, không chỉ theo số dòng. Giữ metadata về tài liệu, vị trí và thứ tự để mô hình biết chunk thuộc phần nào. Không chia giữa một cấu trúc JSON hoặc câu/đoạn nếu có thể tránh; ưu tiên ranh giới heading, paragraph, record hoặc event.

Với log, có thể trả các dòng gần thời điểm/sự kiện liên quan cùng một khoảng ngữ cảnh trước/sau. Với tài liệu, có thể trả các đoạn liên quan nhất theo truy vấn. Nếu người dùng yêu cầu toàn bộ nội dung, mô hình có thể gọi tool tiếp theo bằng cursor; giới hạn số chunk mỗi lượt và dừng khi đủ bằng chứng.

## 11. Truncation phải tường minh

Có thể cần cắt một trường dài hoặc dừng kết quả khi đạt budget. Khi đó, response phải nói rõ phần nào đã bị lược bỏ:

```json
{
  "status": "PARTIAL",
  "code": "RESULT_TRUNCATED",
  "message": "Kết quả đã được giới hạn; có thể lấy thêm dữ liệu bằng cursor.",
  "data": {
    "items": [
      {"id":"R-1","summary":"..."},
      {"id":"R-2","summary":"..."}
    ]
  },
  "meta": {
    "returnedCount": 2,
    "truncated": true,
    "truncationReason": "PAGE_LIMIT",
    "nextCursor": "opaque-token"
  }
}
```

Phân biệt các lý do:

- `PAGE_LIMIT`: còn kết quả ở trang sau.
- `FIELD_LIMIT`: một hoặc nhiều trường văn bản đã được rút ngắn.
- `BYTE_BUDGET`: dừng thêm item vì tổng payload đạt ngưỡng.
- `TOKEN_BUDGET`: dừng theo ngân sách token ước lượng/đo được.
- `TIME_BUDGET`: dừng do thời gian truy vấn hoặc xử lý.

Không cắt chuỗi JSON đã serialize bằng `substring`. Việc đó có thể tạo JSON không hợp lệ, cắt giữa Unicode surrogate pair hoặc loại bỏ metadata cần thiết. Hãy giới hạn dữ liệu trước khi serialize, sau đó serialize DTO hoàn chỉnh. Nếu vẫn vượt byte budget, bỏ bớt item theo quy tắc xác định, cập nhật `truncated` và `nextCursor`, rồi serialize lại.

Nếu một trường văn bản được cắt, hãy đánh dấu riêng trường đó, ví dụ `descriptionTruncated=true`, thay vì chỉ đặt cờ truncation chung cho cả trang.

## 12. Đặt giới hạn byte trước khi trả về

Có thể đo kích thước JSON sau serialize để xác nhận DTO nằm trong giới hạn kỹ thuật. Ví dụ đơn giản:

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import java.nio.charset.StandardCharsets;
import com.fasterxml.jackson.databind.ObjectMapper;
public String serializeWithinLimit(
        Object result,
        ObjectMapper objectMapper,
        int maxBytes) throws JsonProcessingException {

    String json = objectMapper.writeValueAsString(result);
    if (json.getBytes(StandardCharsets.UTF_8).length > maxBytes) {
        throw new ResultTooLargeException("Tool result vượt giới hạn.");
    }
    return json;
}
```

Đoạn này chỉ phát hiện payload quá lớn; nó chưa tự rút gọn kết quả. Nếu cần cắt giảm, hãy thực hiện trên DTO/list trước khi serialize, không cắt chuỗi JSON. Với danh sách, có thể giảm số item theo thứ tự ưu tiên rồi tính lại `returnedCount`, `hasMore` và cursor. Với một object đơn quá lớn, phải giảm trường hoặc trả preview kèm tool lấy nội dung đầy đủ.

Byte budget cần tính cả JSON key, dấu ngoặc, escape, metadata và encoding UTF-8. Đặt một phần dự phòng cho payload thay đổi theo dữ liệu. Cũng cần giới hạn ở tầng HTTP/provider nếu response có thể bị từ chối trước khi đến model.

## 13. Giữ tính nhất quán giữa các trang

Khi dữ liệu thay đổi giữa lần lấy trang đầu và trang tiếp theo, kết quả có thể bị trùng hoặc thiếu. Chọn chiến lược consistency phù hợp:

- **Keyset pagination:** ổn định hơn offset khi thêm bản ghi mới trước vị trí hiện tại, nhưng vẫn cần xử lý update/delete trên sort key.
- **Snapshot/version:** gắn cursor với snapshot hoặc thời điểm truy vấn nếu database hỗ trợ và yêu cầu cần nhất quán mạnh.
- **Watermark:** giới hạn truy vấn ở một mốc `createdAt`/version để các trang tiếp theo không nhận dữ liệu mới ngoài phạm vi ban đầu.
- **Best-effort:** chấp nhận dữ liệu thay đổi, nhưng mô tả rõ trong metadata khi nghiệp vụ cho phép.

Với báo cáo hoặc dữ liệu tài chính, thường cần snapshot hoặc transaction phù hợp. Với tìm kiếm khách hàng thông thường, keyset pagination và thứ tự ổn định có thể đủ. Không giữ transaction database mở xuyên suốt nhiều lượt hội thoại chỉ để duy trì pagination; dùng snapshot token, version hoặc truy vấn theo watermark.

## 14. Điều phối việc lấy thêm dữ liệu

Tool result nhỏ nên cung cấp thông tin để mô hình quyết định bước tiếp theo. Ví dụ:

1. Tool tìm kiếm trả 10 kết quả và `hasMore=true` cùng `nextCursor`.
2. Mô hình xem các kết quả đầu tiên và xác định chúng đã đủ trả lời chưa.
3. Nếu cần, mô hình yêu cầu tool gọi trang tiếp theo với cursor.
4. Ứng dụng xác thực cursor, tenant, quyền và giới hạn số trang.
5. Khi đủ dữ liệu hoặc đạt budget, mô hình trả lời người dùng.

Không để mô hình gọi trang tiếp theo vô hạn. Đặt giới hạn tổng số trang/chunk, số vòng tool call và deadline cho cả tác vụ. Nếu đạt giới hạn, trả kết quả `PARTIAL` với lý do và thông tin trang tiếp theo nếu vẫn có thể tiếp tục.

Với tool gọi nhiều nguồn, mỗi nguồn nên có budget riêng và một budget tổng cho toàn lượt. Tránh trường hợp ba tool độc lập mỗi tool trả 20 KB khiến tổng tool result vượt context budget.

## 15. Bảo mật khi phân trang và rút gọn

Giới hạn kích thước không thay thế authorization. Mọi trang tiếp theo phải kiểm tra lại tenant và quyền; cursor không phải credential.

- Áp dụng tenant filter ngay trong query, không chỉ lọc sau khi lấy dữ liệu.
- Kiểm tra quyền trên từng tài nguyên hoặc tập kết quả.
- Ràng buộc cursor với tenant, filter và sort đã được xác thực.
- Không đưa PII/secret vào cursor nếu token chỉ được encode.
- Không trả thêm trường nhạy cảm trong summary hoặc preview.
- Không cho phép model tăng `pageSize`, `topK`, chunk size hoặc max bytes vượt trần server.
- Giới hạn query cost, timeout, số trang và tổng payload.

Khi rút gọn, ưu tiên giữ lại bằng chứng có liên quan, trạng thái, đơn vị, thời điểm và nguồn. Không loại bỏ metadata khiến mô hình không còn biết dữ liệu thuộc tenant, thời gian hoặc metric nào; đồng thời không đưa định danh nội bộ không cần thiết vào kết quả.

## 16. Kiểm thử kích thước và phân trang

Kiểm thử cần bao phủ cả nội dung JSON và hành vi query:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Yêu cầu page size âm/0/rất lớn | Server dùng default hoặc ép về max |
| Dataset rỗng | Trả `items=[]`, `hasMore=false` |
| Đúng một trang | Cursor null, `hasMore=false` |
| Có trang kế tiếp | `hasMore=true`, cursor hợp lệ |
| Cursor sai/chữ ký sai/hết hạn | Từ chối an toàn |
| Cursor thuộc tenant khác | Không trả dữ liệu tenant khác |
| Sort key trùng | Tie-breaker tạo thứ tự ổn định |
| Dữ liệu thay đổi giữa trang | Hành vi consistency đúng với hợp đồng |
| Trường text quá dài | Có giới hạn và cờ truncation |
| Tổng JSON vượt byte budget | Rút item/field trước serialize; JSON vẫn hợp lệ |
| Tool result vượt token budget | Giảm page/chunk hoặc trả partial rõ ràng |
| Nhiều tool trong cùng lượt | Tổng payload không vượt budget tổng |
| Payload có PII/secret | Trường nhạy cảm không xuất hiện trong JSON |

Ví dụ kiểm thử page size server-side:

```java
@ParameterizedTest
@CsvSource({
        "-5, 10",
        "0, 10",
        "1, 1",
        "25, 25",
        "500, 25"
})
void shouldEnforcePageSizeLimit(int requested, int expected) {
    assertThat(customerSearchService.effectiveSize(requested))
            .isEqualTo(expected);
}
```

Ví dụ kiểm tra byte budget:

```java
String json = objectMapper.writeValueAsString(result);
int bytes = json.getBytes(StandardCharsets.UTF_8).length;

assertThat(bytes).isLessThanOrEqualTo(MAX_TOOL_RESULT_BYTES);
assertThat(objectMapper.readTree(json).isObject()).isTrue();
```

Ngoài unit test, hãy đo token thực tế trên các model mục tiêu bằng tokenizer tương ứng hoặc usage metadata. Theo dõi phân vị p50/p95/p99 của tool result size và token count để điều chỉnh budget theo dữ liệu production.

## 17. Checklist thiết kế tool result có giới hạn

- [ ] Đặt budget tổng cho tool results trong một lượt hội thoại.
- [ ] Giới hạn server-side số item, độ dài field, bytes, token và thời gian.
- [ ] Dùng DTO/projection chuyên biệt, không serialize entity nội bộ.
- [ ] Áp dụng limit ngay trong query/repository.
- [ ] Chọn offset hay cursor theo kích thước và độ biến động dữ liệu.
- [ ] Cursor opaque, có chữ ký/expiry và ràng buộc tenant/filter/sort.
- [ ] Dùng top-K hoặc aggregation khi câu hỏi không cần toàn bộ bản ghi.
- [ ] Chia chunk theo ranh giới nội dung có ý nghĩa.
- [ ] Đánh dấu `truncated`, lý do và cách lấy phần tiếp theo.
- [ ] Không cắt chuỗi JSON sau serialize.
- [ ] Giữ metadata về đơn vị, thời điểm, nguồn và tính nhất quán.
- [ ] Kiểm tra authorization lại ở mọi trang/chunk.
- [ ] Giới hạn số trang, số vòng gọi và tổng thời gian.
- [ ] Kiểm thử payload bytes, token usage, cursor, concurrency và dữ liệu nhạy cảm.

## Tài liệu tham khảo

- [Spring AI 2.1 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1 — ToolCallResultConverter API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/execution/ToolCallResultConverter.html)
- [Spring AI 2.1 — DefaultToolCallResultConverter API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/execution/DefaultToolCallResultConverter.html)
- [Spring Data — Scrolling and Keyset Filtering](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)

Tool result tốt không phải là kết quả chứa nhiều dữ liệu nhất. Nó là kết quả đủ nhỏ để mô hình xử lý, đủ rõ để không hiểu sai và đủ thông tin để lấy tiếp khi cần. Hãy giới hạn từ truy vấn đến DTO, dùng pagination hoặc aggregation theo mục tiêu, biểu diễn truncation minh bạch và kiểm tra lại quyền trên mỗi lần lấy dữ liệu.
