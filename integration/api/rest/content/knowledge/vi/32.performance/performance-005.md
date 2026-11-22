# Tối ưu serialization, cấp phát đối tượng và bộ đệm

Một REST API có thể truy vấn database trong 20 ms nhưng vẫn mất vài trăm millisecond để trả kết quả. Nguyên nhân đôi khi nằm ở việc tạo hàng nghìn entity/DTO trung gian, chuyển JSON thành `String` rồi lại chuyển sang `byte[]`, hoặc tích lũy toàn bộ response trong bộ nhớ trước khi gửi. Với payload lớn, áp lực cấp phát khiến garbage collector hoạt động nhiều hơn, tăng độ trễ p95/p99 ngay cả khi CPU trung bình chưa quá cao.

Trong mô-đun **INTEGRATION_API_REST**, hợp đồng resource, URI, phương thức, mã trạng thái HTTP, phân trang, cache và xử lý lỗi quyết định dữ liệu nào client được nhận. Chương **Hiệu năng** bổ sung câu hỏi: làm thế nào chuyển đúng dữ liệu đó thành byte để gửi qua HTTP với ít CPU, cấp phát và bộ nhớ đệm hơn **mà không phá hợp đồng API, bảo mật và khả năng vận hành**? Bài này tập trung vào Java 17+, Spring Boot 3/Spring MVC, Jackson, và các lưu ý tương ứng cho WebFlux.

## 1. Mục tiêu và nguyên tắc

Sau bài này, người học có thể:

1. Phân tách chi phí **lấy dữ liệu → ánh xạ DTO → serialization → buffering → compression → gửi HTTP**.
2. Sử dụng Jackson/ObjectMapper/ObjectReader/ObjectWriter đúng vòng đời; tránh tạo bộ cấu hình và bản sao dữ liệu không cần thiết.
3. Giảm payload và số đối tượng trung gian bằng projection, DTO, phân trang, lựa chọn trường và cấu trúc JSON có chủ đích.
4. Phân biệt heap object, `String`, `byte[]`, buffer trực tiếp, buffer pool và nguy cơ giữ bộ nhớ quá lâu.
5. Chọn khi nào dùng response thông thường, streaming JSON, compression hoặc cache; nêu được giới hạn của từng cách.
6. Đo CPU, allocation rate, GC pause, latency và throughput bằng JFR/Micrometer/JMH/load test trước và sau thay đổi.
7. Viết kiểm thử bảo toàn dữ liệu, HTTP contract, giới hạn tài nguyên, quyền truy cập và các tình huống client ngắt kết nối.

**Quy tắc tối ưu đầu tiên:** xác định bottleneck bằng số liệu; đừng viết serializer thủ công, bật buffer pool hoặc đổi định dạng chỉ vì cho rằng chúng “nhanh hơn”. Tối ưu tốt phải duy trì cùng kết quả nghiệp vụ và có số đo được tái hiện.

## 2. Dữ liệu đi từ REST resource tới socket như thế nào?

Xét endpoint `GET /api/v1/orders?limit=100` trả một trang đơn hàng:

~~~mermaid
flowchart LR
    R["HTTP GET /orders"] --> A["Controller / Authorization"]
    A --> Q["Repository / DB query"]
    Q --> P["Projection / DTO"]
    P --> J["Jackson JSON encoder"]
    J --> B["HTTP output buffer"]
    B --> C["Compression nếu cần"]
    C --> N["Socket / Proxy / Client"]
    M["JFR + Metrics + Trace"] -.-> Q
    M -.-> P
    M -.-> J
    M -.-> B
    M -.-> C
~~~

Một số chi phí cần nhận diện:

| Công đoạn | Chi phí điển hình | Dấu hiệu quan sát |
| --- | --- | --- |
| SQL/query | Scan, join, lock, network DB, tải quá nhiều hàng | Slow queries, DB time, số rows, connection usage |
| Entity materialization | Khởi tạo object graph, lazy loading, N+1 | Allocation rate cao, nhiều SQL, heap tăng |
| Ánh xạ DTO | Copy field, tạo list/map/format date | CPU profile ở mapper, nhiều object tạm |
| Serialization | Duyệt object, reflection/metadata lookup, escaping UTF-8, xử lý ngày/số | CPU tại Jackson, allocation B/op, JSON encode duration |
| Buffering | Tạo `String`/`byte[]`/`ByteArrayOutputStream`, copy, buffer growth | Allocation spike theo response size, GC pause |
| Compression | CPU nén, buffer nén; giảm byte trên mạng | CPU tăng nhưng network bytes giảm |
| Network/client | Backpressure, socket write, proxy buffering, client chậm | Response write time, active connections, outbound bytes |

Một span HTTP 200 ms **không có nghĩa** serialization mất 200 ms. Với Spring MVC, thời gian encode/ghi response có thể diễn ra sau khi phương thức controller trả về; vì vậy timer đặt xung quanh code controller thường không bao phủ toàn bộ network write. Cần kết hợp HTTP server metrics, sampling profile và instrumentation ở đúng ranh giới.

### 2.1. Ba loại bộ nhớ dễ bị đánh đồng

1. **Dữ liệu nghiệp vụ:** entity, DTO, collection và cache đang cần dùng; có thể tồn tại nhiều request hoặc lâu hơn request.
2. **Đối tượng tạm:** `StringBuilder`, map, iterator, chuỗi trung gian, `byte[]`, wrapper và các object phục vụ serialization; thường tồn tại ngắn nhưng gây allocation/GC khi tạo với tốc độ lớn.
3. **Buffer I/O:** vùng nhớ heap hoặc direct được dùng khi ghi/đọc byte, có thể nằm trong pool; được tái sử dụng nhưng có nguy cơ chiếm bộ nhớ nếu giữ lâu hoặc quên giải phóng.

Không chỉ đo heap used. Một direct buffer pool có thể giảm heap allocations nhưng tăng **off-heap memory**, và một cache lớn có thể giảm CPU nhưng tăng live set khiến GC chậm hơn.

## 3. Xây baseline trước khi tối ưu

Đo ít nhất ba lớp:

| Lớp đo | Metric/đại lượng | Cần hiểu |
| --- | --- | --- |
| Người dùng | p50/p95/p99 HTTP latency, request/s, error rate, response bytes | API có thực sự nhanh hơn với cùng tải và payload? |
| JVM | Allocation bytes/s, allocated bytes/request, heap occupancy, GC pause, CPU, live threads | Đã giảm object churn hay chỉ chuyển sang bộ nhớ lâu sống? |
| Thành phần | DB time, DTO mapping time, JSON encode time, compression/write time | Bottleneck thay đổi ở đâu? |

Ghi lại **tải kiểm thử**, số lượng resource, kích thước response, tỷ lệ cache hit, codec, JDK version, server/container, heap size và cấu hình HTTP compression. So sánh cùng một phân phối payload: nếu lần thử A trả 10 order còn B trả 100 order, kết luận về serializer không có ý nghĩa.

### 3.1. Ví dụ tính chi phí từ số đo

Giả sử một endpoint trung bình trả 256 KiB JSON, phục vụ 500 request/giây. Chỉ riêng **byte response chưa nén** đã xấp xỉ 125 MiB/giây (256 KiB × 500); nếu ứng dụng tạo ba bản sao hoàn chỉnh của payload trong quá trình xử lý, áp lực bộ nhớ tạm có thể lớn hơn đáng kể. Đây là phép ước lượng để tìm thứ tự ưu tiên, không phải dự báo chính xác heap allocation: cơ chế converter, compression, network stack và pooling ảnh hưởng số bản sao thực tế.

Một phép đo ý nghĩa:

~~~text
Endpoint: GET /api/v1/orders?limit=100
Payload: p50 120 KiB; p95 310 KiB
Load: 150 RPS trong 10 phút, dữ liệu cố định
Trước: p95 180 ms; allocation 0.8 MiB/request; 5xx = 0
Sau:   p95 145 ms; allocation 0.5 MiB/request; 5xx = 0
~~~

Số liệu trên **chỉ minh họa cách ghi báo cáo**, không phải benchmark của Spring hay Jackson. Khi tối ưu, đặt tiêu chí dừng: chẳng hạn giảm p95 mà không tăng lỗi, không thay đổi JSON contract, không làm rò buffer và không tạo payload bị cache sai tenant.

## 4. Bảo toàn HTTP contract trước khi rút ngắn JSON

Serialization là một phần của **hợp đồng công khai**. Việc xóa field, đổi cách biểu diễn `null`, đổi định dạng ngày, thay tên thuộc tính hoặc chuyển số tiền thành floating-point có thể làm hỏng client dù benchmark đẹp hơn.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-cache

{
  "items": [
    {
      "id": "8c9b4ca4-2211-4cd0-a949-d176bcb8e35f",
      "status": "PENDING",
      "totalMinor": 259000,
      "currency": "VND",
      "createdAt": "2026-11-18T10:30:00Z"
    }
  ],
  "nextCursor": null
}
~~~

Đây là ví dụ tài nguyên collection có cursor, không phải cam kết mọi field phải luôn có `null`. Nếu client phân biệt “field vắng” và “field có `null`”, cấu hình `@JsonInclude(NON_NULL)` có thể là **breaking change**. Nếu client dùng JavaScript, các số nguyên rất lớn vượt miền số nguyên an toàn của JavaScript có thể cần biểu diễn bằng chuỗi theo hợp đồng. Với tiền tệ, nên chọn biểu diễn nguyên đơn vị nhỏ hoặc decimal string tùy nghiệp vụ; không chuyển `BigDecimal` sang `double` chỉ để giảm thời gian encode.

### 4.1. Tối ưu lượng dữ liệu trước tối ưu encoder

Thứ tự thường đáng làm:

1. **Giới hạn kết quả:** phân trang/cursor; không trả hàng chục nghìn record không giới hạn khi client chỉ cần 20–100 record.
2. **Trả đúng field:** resource summary dùng projection/DTO nhỏ, detail endpoint trả mô hình đầy đủ khi cần.
3. **Tránh dữ liệu lặp:** không nhúng toàn bộ customer/product trong mỗi order item nếu chỉ cần ID và vài trường hiển thị.
4. **Chọn truy vấn tương ứng:** fetch đúng cột và association, tránh N+1 hoặc hydrate toàn bộ entity graph để rồi bỏ phần lớn.
5. **Kiểm soát media type và representation:** JSON phù hợp trình duyệt/Java client; định dạng nhị phân chỉ nên dùng khi hợp đồng và hệ sinh thái hỗ trợ.
6. **Đo trước khi nén:** payload nhỏ hoặc đã nén có thể không hưởng lợi từ gzip/br; CPU nén có thể đắt hơn byte tiết kiệm.

Lượng JSON giảm thường kéo theo ít allocation, giảm CPU encode, giảm network và giảm công việc ở client. Đây là tối ưu **thiết kế API**, không chỉ là tối ưu Jackson.

## 5. Jackson: tái sử dụng đúng cách, không tạo cấu hình theo request

Spring MVC thường dùng `MappingJackson2HttpMessageConverter` để chuyển object trả từ controller thành JSON; Spring Boot cấu hình `ObjectMapper` cùng các module thích hợp. Ở WebFlux, encoder/decoder tương ứng thực hiện công việc tương tự theo mô hình reactive.

**Sai lầm phổ biến:** mỗi lần xử lý request lại tạo `new ObjectMapper()`, đăng ký module, đặt naming strategy rồi gọi `writeValueAsString(...)`. Việc này bỏ phí cache metadata/serializer, phát sinh đối tượng tạm và dễ làm cấu hình khác converter mặc định của Spring.

### 5.1. Dùng một ObjectMapper được cấu hình trước khi dùng

~~~java
@Configuration
public class JsonConfig {
    @Bean
    Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
        return builder -> builder
            .featuresToDisable(
                SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    }
}
~~~

Đoạn này minh họa tùy biến mapper do Spring Boot quản lý, không tạo mapper mới trong controller. Import thuộc Spring Boot Jackson và Jackson `SerializationFeature`. Khi kết hợp với configuration của dự án, cần kiểm tra các module như Java Time và naming strategy để tránh khác biệt giữa service, test và OpenAPI.

`ObjectMapper` được thiết kế để chia sẻ giữa các thread **sau khi đã hoàn tất cấu hình, trước lần sử dụng đầu tiên**. Đừng gọi `registerModule`, bật/tắt feature hay thay serializer động khi nhiều request đang serialize. Một số operation đọc/ghi tạo đối tượng trung gian dù mapper được dùng chung, nhưng caching class metadata giúp tránh phần việc không cần thiết.

### 5.2. ObjectWriter/ObjectReader là cấu hình bất biến có thể tái sử dụng

~~~java
@Component
public final class OrderJsonCodec {
    private final ObjectWriter writer;
    private final ObjectReader reader;

    public OrderJsonCodec(ObjectMapper mapper) {
        this.writer = mapper.writerFor(OrderSummaryDto.class);
        this.reader = mapper.readerFor(OrderSummaryDto.class);
    }

    public byte[] encode(OrderSummaryDto dto)
            throws JsonProcessingException {
        return writer.writeValueAsBytes(dto);
    }

    public OrderSummaryDto decode(byte[] json)
            throws IOException {
        return reader.readValue(json);
    }
}
~~~

`ObjectWriter` và `ObjectReader` là các đối tượng bất biến/định hướng cấu hình, thích hợp tái sử dụng và an toàn khi nhiều thread đọc đồng thời. `writeValueAsBytes` vẫn tạo mảng byte trả về; ví dụ minh họa codec, **không khuyến nghị controller bình thường luôn tự serialize ra byte[]**. Khi controller trả DTO, hãy để converter Spring ghi trực tiếp ra HTTP response để tránh một bản sao không cần thiết.

### 5.3. Controller trả DTO thay vì chuỗi JSON thủ công

~~~java
public record OrderSummaryDto(
    UUID id,
    String status,
    long totalMinor,
    String currency,
    Instant createdAt) {}

@RestController
@RequestMapping("/api/v1/orders")
public class OrderQueryController {
    private final OrderQueryService query;

    public OrderQueryController(OrderQueryService query) {
        this.query = query;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderSummaryDto> getOne(
            @PathVariable UUID id,
            Authentication authentication) {
        OrderSummaryDto dto =
            query.findVisibleOrder(authentication.getName(), id);
        return ResponseEntity.ok(dto);
    }
}
~~~

`OrderQueryService` là thành phần nghiệp vụ giả định phải kiểm tra quyền đọc đối tượng và tenant. Spring trả `Content-Type: application/json` qua converter khi cấu hình JSON phù hợp. Nếu `totalMinor` đại diện đơn vị nhỏ, contract phải nói rõ đơn vị. `Instant` nên được serialize theo một quy ước UTC/ISO 8601 ổn định và có test xác nhận. Tối ưu performance không được làm mất BOLA/IDOR protection hoặc field-level authorization.

**Không trả trực tiếp entity JPA** chỉ vì muốn tiết kiệm phép ánh xạ: entity có thể kéo theo lazy loading/N+1, quan hệ vòng, trường nội bộ, secret, hoặc khởi tạo proxy sau khi transaction đã đóng. Một DTO/projection được định nghĩa rõ vừa giảm dữ liệu vừa làm hợp đồng an toàn hơn.

## 6. Giảm cấp phát trong ánh xạ dữ liệu

### 6.1. Dùng projection vừa đủ thay vì nạp cả aggregate

Giả sử trang danh sách chỉ hiển thị ID, trạng thái và tổng tiền. Có thể dùng Spring Data projection hoặc DTO query:

~~~java
public interface OrderSummaryProjection {
    UUID getId();
    String getStatus();
    long getTotalMinor();
}

public interface OrderRepository extends JpaRepository<OrderEntity, UUID> {
    @Query("""
        select o.id as id,
               o.status as status,
               o.totalMinor as totalMinor
          from OrderEntity o
         where o.tenantId = :tenantId
         order by o.createdAt desc, o.id desc
        """)
    List<OrderSummaryProjection> findSummaries(
        @Param("tenantId") String tenantId,
        Pageable pageable);
}
~~~

Đây là ví dụ JPQL/projection, giả định tên field entity thực tế phù hợp. Khi dùng interface projection, framework vẫn tạo wrapper/proxy cho từng dòng và có thể tạo tuple trung gian; **đây không phải zero-allocation**. Lợi ích chính là tránh tải/khởi tạo những cột và quan hệ không cần thiết. Đo SQL sinh ra và kiểm tra explain plan; paging cần thứ tự ổn định và điều kiện truy vấn đúng tenant. `Pageable` giới hạn trang nhưng offset pagination sâu có thể tốn chi phí; keyset/cursor có thể phù hợp cho collection lớn.

Với hàng nghìn dòng, dùng primitive thích hợp ở nội bộ khi có ý nghĩa, nhưng đừng biến tất cả object thành array index khó hiểu. Một record DTO có contract rõ vẫn đáng giá hơn vài byte allocation tiết kiệm được mà làm mất tính bảo trì.

### 6.2. Tránh chuỗi thao tác tạo nhiều bản sao

Ví dụ không nên làm khi chỉ định trả JSON ra HTTP:

~~~java
// Không khuyến nghị trong controller trả JSON bình thường.
String json = mapper.writeValueAsString(orderDtos);
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
return ResponseEntity.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .body(bytes);
~~~

Ở đây tạo ít nhất chuỗi JSON và mảng UTF-8 tạm, chưa tính buffer của HTTP server/converter. Nếu hệ thống còn `new String(bytes, UTF_8)` ở bước sau, số lần encode/decode càng tăng. Nên:

~~~java
return ResponseEntity.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .body(orderDtos);
~~~

Để converter serialize DTO và ghi ra HTTP. **Không cam kết zero-copy**: Jackson, servlet output stream, TLS và proxy vẫn dùng buffer; mục tiêu là tránh các bản sao do ứng dụng tự tạo mà không cần thiết.

### 6.3. Collection và object tạm

Các lỗi hay gặp:

- Ánh xạ `entity → Map<String,Object> → JSON tree → String → byte[]` khi một DTO định kiểu có thể đủ.
- Chuyển `List` sang `Stream` rồi qua nhiều `map/filter/collect` lồng nhau trên hot path khi có thể xử lý một lần mà vẫn rõ ràng.
- Dùng regex hoặc `String.format` nhiều lần trong serializer/custom mapper cho một giá trị đơn giản.
- Tạo `DateTimeFormatter` hoặc các formatter khác theo từng record, trong khi một cấu hình immutable có thể dùng lại.
- Tạo nhiều `BigDecimal`/date representation từ string qua mỗi lớp nếu nghiệp vụ đã có kiểu phù hợp.
- Giữ lại toàn bộ DTO/raw JSON trong cache “để dùng sau” không có TTL/size budget.

Nhưng cũng không nên viết vòng lặp khó đọc thay toàn bộ Stream API dựa trên cảm tính. JIT có thể tối ưu nhiều allocation ngắn hạn; hãy xác minh bằng **JFR allocation samples, JMH có GC profiler hoặc benchmark dưới tải**. Mục tiêu không phải đếm dòng code mà là giảm công việc và memory churn có ý nghĩa.

## 7. Buffer: chọn giới hạn, vòng đời và chủ sở hữu rõ ràng

**Buffer** là nơi gom byte để tăng hiệu quả I/O và giảm số lần gọi nhỏ lẻ. Buffer quá nhỏ làm tăng syscall/flush và overhead; buffer quá lớn làm tăng bộ nhớ giữ lại cho mỗi request. Không có kích thước “chuẩn” áp dụng cho tất cả response.

| Loại buffer | Ở đâu | Lợi ích | Rủi ro |
| --- | --- | --- | --- |
| `byte[]` trên heap | Serialize toàn bộ payload, stream wrapper | Dễ dùng, GC quản lý | Mảng lớn, nhiều bản sao, tăng allocation |
| `ByteArrayOutputStream` | Ghi vào RAM trước khi trả response | Thuận tiện khi bắt buộc cần toàn bộ bytes | Resize/copy và giữ toàn payload, `toByteArray()` thường copy |
| `BufferedOutputStream` | Ghi tuần tự sang output stream | Gom write nhỏ; có thể giảm overhead | Flush quá thường xuyên, thêm buffer nếu phía dưới đã buffer |
| Direct `ByteBuffer` | NIO/HTTP transport, native I/O | Có thể giảm copy tại một số ranh giới | Off-heap footprint, cấp phát đắt, khó quản lý |
| Pooled Netty `ByteBuf`/Spring `DataBuffer` | Reactive I/O hoặc network stack | Tái sử dụng vùng nhớ, giảm churn | Rò reference-count, use-after-release, retention |
| Compression buffer | Gzip/br encoder | Giảm network byte | CPU, memory, chậm first byte |

### 7.1. Không chia sẻ buffer có thể thay đổi giữa request

Ví dụ **sai**:

~~~java
@Component
class UnsafeJsonBuffer {
    private final ByteArrayOutputStream shared =
        new ByteArrayOutputStream();

    byte[] serialize(Object dto, ObjectMapper mapper)
            throws IOException {
        shared.reset();
        mapper.writeValue(shared, dto);
        return shared.toByteArray();
    }
}
~~~

Nhiều request cùng ghi vào `shared` có thể làm trộn JSON, lộ dữ liệu giữa người dùng hoặc tạo response hỏng. `synchronized` có thể tránh data race nhưng biến serialize thành nút nghẽn; một `ThreadLocal` buffer dùng vô hạn cũng có thể giữ mảng rất lớn gắn với thread pool lâu sống. Cần cân nhắc lifetime, kích thước tối đa và cách giải phóng.

Thông thường, để Jackson/converter và HTTP server quản lý buffer là lựa chọn an toàn. Chỉ thiết kế buffer pool tùy biến nếu profile chứng minh bottleneck và có **giới hạn bộ nhớ, quyền sở hữu, reset và kiểm thử cạnh tranh**.

### 7.2. Một buffer per-request lớn không miễn phí

Nếu mỗi request đồng thời giữ một buffer 1 MiB, 200 request có thể giữ gần 200 MiB cho vùng đệm đó (chưa tính DTO, stack, socket, các bản sao, overhead và GC). Một giới hạn payload và số request đồng thời phải được cân nhắc chung. Với REST API public, cần phân trang/giới hạn `limit`, timeout và rate limit, không chỉ tăng heap.

### 7.3. Compression thay đổi chi phí, không làm payload miễn phí

Spring Boot (với embedded server hỗ trợ) có thể bật HTTP response compression:

~~~yaml
server:
  compression:
    enabled: true
    min-response-size: 2KB
    mime-types:
      - application/json
      - application/problem+json
      - text/plain
~~~

Đây là cấu hình ví dụ cần xác minh ở phiên bản Spring Boot/server thực tế. Trình duyệt/client có thể gửi `Accept-Encoding: gzip` và server chọn trả `Content-Encoding: gzip` khi áp dụng. Proxy/CDN có thể tự nén, bỏ nén hoặc nén lại; phải đo **từ ngoài đường truy cập thật**. Response có biến thể encoding cần được cache phân biệt đúng; `Vary: Accept-Encoding` thường do tầng nén quản lý, nhưng không nên mặc định mọi gateway đã cấu hình chính xác.

Compression giúp tiết kiệm bandwidth cho JSON đủ lớn, đặc biệt qua mạng chậm, nhưng có thể tăng CPU/latency và gây buffering. Một phản hồi nhỏ vài trăm byte có thể không đáng nén. Với response chứa secret đồng thời phản chiếu dữ liệu do kẻ tấn công kiểm soát, cần đánh giá rủi ro **compression side channel** trong bối cảnh trình duyệt/TLS; không áp dụng nén mù cho mọi phản hồi nhạy cảm.

`Content-Length` của JSON chưa nén không còn là độ dài bản nén, nên khi nén/streaming container có thể dùng transfer encoding phù hợp. Không tự đặt `Content-Length` trên một body chưa biết số byte thực cuối cùng.

## 8. Khi nào nên streaming JSON?

Với danh sách nhỏ, trả DTO/`Page<T>` hoặc collection qua converter thông thường là đủ đơn giản. Khi payload rất lớn (export hàng trăm nghìn dòng), nếu buộc phải trả toàn bộ thì streaming có thể giảm **peak heap** và cải thiện **time-to-first-byte**. Tuy nhiên nó không loại bỏ chi phí truy vấn, encode hay network; nó cũng tạo rủi ro riêng.

### 8.1. StreamingResponseBody trong Spring MVC

Ví dụ xuất dữ liệu dạng JSON array, mỗi lần lấy một trang giới hạn bằng keyset, không tích toàn bộ danh sách trong RAM:

~~~java
@RestController
@RequestMapping("/api/v1/order-exports")
class OrderExportController {
    private final OrderQueryService service;
    private final ObjectMapper mapper;

    OrderExportController(OrderQueryService service, ObjectMapper mapper) {
        this.service = service;
        this.mapper = mapper;
    }

    @GetMapping(value = "/json", produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<StreamingResponseBody> export(
            Authentication authentication) {
        String principal = authentication.getName();
        // Xác thực, giới hạn quyền export và xác định tenant trước khi stream.

        StreamingResponseBody body = output -> {
            ObjectWriter writer = mapper.writerFor(OrderSummaryDto.class);
            try (JsonGenerator json = mapper.getFactory()
                    .createGenerator(output, JsonEncoding.UTF8)) {
                json.writeStartArray();
                UUID afterId = null;
                while (true) {
                    List<OrderSummaryDto> page =
                        service.nextExportPage(principal, afterId, 100);
                    if (page.isEmpty()) break;
                    for (OrderSummaryDto item : page) {
                        writer.writeValue(json, item);
                        afterId = item.id();
                    }
                    // Trong thực tế cần giới hạn tối đa và deadline.
                }
                json.writeEndArray();
            }
        };

        return ResponseEntity.ok()
            .header(HttpHeaders.CACHE_CONTROL, "no-store")
            .body(body);
    }
}
~~~

Ví dụ cần import Spring MVC/HTTP, Jackson `JsonGenerator`, `JsonEncoding`, `ObjectWriter` và Java collection/UUID; `OrderQueryService.nextExportPage(...)` là thành phần giả định có **keyset ordering ổn định và kiểm soát quyền/tenant trên mỗi truy vấn**. Câu query phải có điều kiện sau cursor đúng với cột sort; nếu sort theo timestamp + ID, cần cursor gồm cả hai, không chỉ ID. `principal` chỉ là minh họa danh tính đã xác thực; production nên truyền tenant/principal/permission đã được kiểm tra thay vì tin raw identifier từ client.

**Những giới hạn quan trọng của code trên:**

- `StreamingResponseBody` có thể được thực thi bất đồng bộ sau khi controller trả về; **không** bọc transaction vào controller và tin rằng nó vẫn mở khi callback chạy. Mỗi lần lấy trang nên dùng một transaction đọc ngắn hoặc repository query với vòng đời rõ ràng.
- Nếu client ngắt kết nối hoặc serializer lỗi **sau khi headers/body đã được gửi**, server không thể đổi status từ `200` thành `500` hoặc thay JSON dở dang bằng Problem Details. Client phải phát hiện stream kết thúc bất thường; với export quan trọng cân nhắc tạo file/job bất đồng bộ.
- Streaming cần một executor phù hợp; nếu tác vụ chậm chiếm hết thread/connection, nó có thể làm suy giảm API chính. Theo dõi active streams, bytes, duration, cancellation và giới hạn concurrency.
- Nếu dữ liệu thay đổi giữa các trang, export có thể không phản ánh một snapshot nhất quán. Cần thiết kế snapshot, watermark hoặc semantics eventual phù hợp; mở transaction DB nhiều phút để giữ snapshot có thể làm tăng áp lực tài nguyên.
- Không flush mỗi record nếu không cần: quá nhiều flush làm giảm lợi ích buffering. Nhưng nếu gateway/CDN buffer toàn bộ body, streaming từ ứng dụng chưa chắc cải thiện time-to-first-byte của client.
- Một API phải giới hạn kích thước, thời gian và quyền export; streaming không miễn trừ yêu cầu chống data exfiltration, rate limit và audit.

### 8.2. NDJSON hoặc CSV cho export

Đối với export lớn, một định dạng như **NDJSON** (mỗi dòng là một JSON object) có thể giúp client xử lý dần và nhận diện record đã hoàn thành; media type thường là `application/x-ndjson` khi contract quy định. CSV cũng thường phù hợp cho import/export, nhưng cần escaping đúng, chống CSV formula injection khi mở bằng bảng tính và xác định encoding/line endings.

Không tự ý đổi `application/json` array thành NDJSON chỉ vì tốc độ: đó là **thay đổi hợp đồng**, yêu cầu client biết định dạng và cơ chế lỗi khi stream bị cắt. Nếu dữ liệu lớn cần tạo báo cáo, cân nhắc:

~~~http
POST /api/v1/exports HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{"resource":"orders","format":"ndjson"}

HTTP/1.1 202 Accepted
Location: /api/v1/exports/jobs/7f9b
~~~

Khi job hoàn tất, client tải file theo URL có kiểm soát quyền và thời hạn. `202` chỉ nghĩa hệ thống đã nhận yêu cầu xử lý theo thiết kế, không có nghĩa file đã sẵn sàng. Job phải được lưu bền vững và có trạng thái/expiration rõ ràng.

## 9. WebFlux, DataBuffer và backpressure

Với Spring WebFlux/Reactor Netty, publisher của DTO có thể được encode thành stream bằng Jackson encoder, nhưng **backpressure không bảo đảm toàn bộ dữ liệu nguồn luôn dùng bộ nhớ hữu hạn**. Nếu trước đó code đã gọi `findAll()` và materialize một list khổng lồ, chuyển list thành `Flux` không xóa allocation đó. Ngoài ra JSON array streaming, flush behavior và codec aggregation có semantics riêng theo encoder và media type.

Ví dụ hướng tiếp cận:

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.APPLICATION_NDJSON_VALUE)
Flux<OrderEventDto> events(Authentication authentication) {
    return eventQuery.streamVisibleEvents(authentication.getName())
        .limitRate(64);
}
~~~

Đây là ví dụ kiến trúc dùng reactive repository/publisher thực. `limitRate(64)` thay đổi cách request upstream của Reactor nhưng **không phải** giới hạn cứng 64 object trong toàn hệ thống hoặc bảo đảm downstream luôn nhận được dữ liệu; cần kiểm tra chiến lược prefetch và operator ở pipeline thật. Không gọi JDBC blocking trực tiếp trên Netty event loop; nếu phải tích hợp blocking source, tách scheduler đúng cách và đặt concurrency/resource budget.

### 9.1. Pooled DataBuffer và trách nhiệm release

Khi ứng dụng xử lý `DataBuffer`/Netty `ByteBuf` thủ công, buffer có thể được **reference-counted**. Nếu nhận ownership mà không release, direct memory có thể bị giữ lâu; nếu release sớm rồi tiếp tục đọc, sẽ phát sinh lỗi hoặc dữ liệu sai. Spring codec thường quản lý việc giải phóng trong flow chuẩn; chỉ gọi `DataBufferUtils.release(buffer)` ở nhánh xử lý **tự quản lý buffer** khi contract ownership thực sự yêu cầu, đặc biệt trên error/cancel path.

Không thêm `doOnNext(DataBufferUtils::release)` bừa vào một pipeline đang trả chính buffer đó cho framework ghi ra socket: release trước khi write hoàn tất có thể làm hỏng output. Khi dùng `DataBufferUtils.join`, cần hiểu nó gom buffer và có thể tích lũy bộ nhớ; đặt `maxInMemorySize` hoặc giới hạn response/request cho codec phù hợp.

Nếu buộc dùng direct buffer pool tùy biến, cần test cả slow consumer, cancellation, decode failure, backpressure và shutdown. Nên quan sát heap, direct memory usage, connection pool và active streams thay vì chỉ nhìn allocation bytes trên heap.

## 10. Cache, ETag và serialization

**Không serialize lại một representation không đổi nếu có thể tránh bằng HTTP caching đúng nghĩa.** Đối với dữ liệu công khai/ít thay đổi, response có thể dùng `ETag` hoặc `Last-Modified` cùng chính sách `Cache-Control` có chủ đích:

~~~http
GET /api/v1/catalog/42 HTTP/1.1
If-None-Match: "catalog-v17"

HTTP/1.1 304 Not Modified
ETag: "catalog-v17"
Cache-Control: public, max-age=60
~~~

`304 Not Modified` không có response body, giúp tránh gửi lại representation khi điều kiện hợp lệ. Nhưng một implementation có thể vẫn chạy DB/query/serialization để tính ETag; muốn giảm CPU thật sự, cần thiết kế **version/validator hiệu quả** và xác nhận benchmark. Nếu ETag dựa trên hash byte cuối cùng, hệ thống có thể phải serialize toàn bộ payload trước rồi mới biết hash, làm mất lợi ích CPU mong muốn.

Với API cá nhân/tenant-specific, không được dùng shared cache công khai một cách thiếu kiểm soát. Dữ liệu nhạy cảm có thể yêu cầu `Cache-Control: no-store`. Nếu representation thay đổi theo `Accept-Encoding` hoặc header có ý nghĩa khác, cache key và `Vary` phải chính xác. Không lưu một `byte[]` JSON rồi tái sử dụng qua người dùng khác nếu field-level permissions hoặc localization khác nhau.

### 10.1. Cache các phần đắt đỏ, không mặc nhiên cache raw response

Có thể cache dữ liệu domain/projection, kết quả truy vấn hoặc representation đã serialize. Mỗi cách có trade-off:

| Cấp cache | Giảm chi phí | Cần kiểm soát |
| --- | --- | --- |
| Query/domain | DB query và materialization | Invalidation, transaction consistency, tenant key |
| DTO/projection | Mapping và query | TTL, quyền, version schema |
| Raw JSON/byte response | Mapping + serialization | Content negotiation, cache key, dữ liệu cá nhân, charset/encoding |
| CDN/HTTP cache | Lưu lượng và CPU ở API origin | `Cache-Control`, `Vary`, `ETag`, auth, purge |

Cache quá lớn có thể biến CPU optimization thành heap pressure. Theo dõi hit/miss rate, eviction, weight/bytes và live heap. Không lấy “cache hit cao” làm thước đo thành công duy nhất nếu dữ liệu sai hoặc stale vượt hợp đồng.

## 11. Bảo mật khi tối ưu encode/decode

Tối ưu hiệu năng không được bỏ qua validation và giới hạn dữ liệu:

1. **Giới hạn request body:** không deserialize JSON không giới hạn kích thước, số phần tử hoặc mức lồng nhau. Đặt limit ở ingress/HTTP server, codec, và ở parser khi có khả năng.
2. **Giới hạn JSON nesting/string/number:** với Jackson hỗ trợ cấu hình `StreamReadConstraints`, có thể áp dụng giới hạn độ sâu, độ dài chuỗi, số chữ số phù hợp với phiên bản và nhu cầu; kiểm tra hành vi thực tế qua test.
3. **Không bật polymorphic default typing không kiểm soát:** deserialize kiểu do client tùy ý chỉ định có thể mở rủi ro object gadget. Dùng DTO cụ thể hoặc whitelist kiểu theo contract.
4. **Không serialize entity nội bộ:** có thể lộ password hash, API key, thông tin cross-tenant hoặc đối tượng lazy/proxy. Dùng response DTO/field allowlist.
5. **Không tái sử dụng buffer chứa secret giữa tenant:** đặc biệt với buffer mutable/pool viết thủ công. Reset/overwrite theo yêu cầu dữ liệu nhạy cảm và không cho buffer bị lộ qua response khác.
6. **Không log raw body/token theo mặc định:** profiling, dump, exception message và benchmark fixture cũng có thể chứa PII.
7. **Compression và cache:** kiểm soát header, user-specific data và nguy cơ phản chiếu input gần secret; không đánh đổi bảo mật để lấy một tỷ lệ nén đẹp.

Ví dụ cấu hình giới hạn parser bằng API Jackson (phụ thuộc phiên bản):

~~~java
JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(StreamReadConstraints.builder()
        .maxNestingDepth(100)
        .maxStringLength(100_000)
        .build())
    .build();

ObjectMapper restrictedMapper = new ObjectMapper(factory);
~~~

Đoạn mã minh họa một mapper **riêng** được cấu hình trước khi sử dụng, không phải lời khuyên thay mapper Spring Boot trong production mà không đăng ký các module/conventions cần thiết. Một số giới hạn mặc định và builder option thay đổi theo Jackson version; ứng dụng nên cấu hình phù hợp **hợp đồng request thực tế**, kiểm tra parser đã từ chối payload xấu và bảo đảm mọi đường deserialize dùng cấu hình hạn chế đúng.

Một payload hợp lệ có thể rất sâu hoặc chứa string dài theo nghiệp vụ; giới hạn quá thấp gây lỗi tương thích. Nhưng để vô hạn có thể biến endpoint thành mục tiêu CPU/memory exhaustion. Cần phối hợp **HTTP max request size**, validation, phân quyền, rate limiting và timeout, không trông chờ một Jackson setting đơn lẻ.

## 12. Đo allocation/CPU bằng JFR, JMH và load test

### 12.1. JFR để xác định hot path thật

Java Flight Recorder (JFR) hỗ trợ lấy mẫu CPU, allocation, GC và nhiều sự kiện JVM với overhead phù hợp để profiling có kiểm soát. Ví dụ chạy trong môi trường test:

~~~bash
java -XX:StartFlightRecording=filename=orders-api.jfr,settings=profile \
     -jar orders-api.jar
~~~

Đây là **lệnh minh họa**, không cần chạy khi tạo nội dung bài học. `settings=profile` có thể tăng overhead so với `default`; trước khi bật ở production, cần đánh giá chính sách ghi file, dung lượng, quyền truy cập và chi phí thu thập. Allocation samples cho biết nơi phát sinh nhiều cấp phát, nhưng **không nhất thiết là tổng số byte chính xác trên mọi object**. Kết hợp với `jvm.gc.pause`, CPU profile, heap/live-set, số lượng request và response size.

Một vòng điều tra:

1. Chạy workload đã định nghĩa, lưu response size/latency/error rate trước.
2. Thu JFR cho khoảng thời gian có tải ổn định; tìm class/object allocation có tỷ lệ lớn và stack trace tạo ra.
3. Xác định phần thuộc SQL/materialization/DTO/Jackson/buffer/compression; tránh quy tất cả allocation cho serializer.
4. Thay **một giả thuyết** rồi chạy lại cùng workload, cùng version JDK và cấu hình.
5. Kiểm tra hiệu ứng phụ: payload, GC, throughput, p99, direct memory, leak và số lỗi.

### 12.2. JMH cho microbenchmark serialization

Đối với hai cách encode một DTO như `writeValueAsString` và `writeValueAsBytes`, dùng **JMH**, không đo một lần bằng `System.nanoTime()` quanh method rồi kết luận. Ví dụ phác thảo benchmark:

~~~java
@State(Scope.Thread)
public class OrderJsonBenchmark {
    private ObjectWriter writer;
    private OrderSummaryDto dto;

    @Setup(Level.Trial)
    public void setup() {
        ObjectMapper mapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();
        writer = mapper.writerFor(OrderSummaryDto.class);
        dto = new OrderSummaryDto(
            UUID.fromString("8c9b4ca4-2211-4cd0-a949-d176bcb8e35f"),
            "PENDING", 259000L, "VND",
            Instant.parse("2026-11-18T10:30:00Z"));
    }

    @Benchmark
    public byte[] serializeToBytes()
            throws JsonProcessingException {
        return writer.writeValueAsBytes(dto);
    }
}
~~~

Đây là khung benchmark với JMH annotations, Jackson và Java Time module; cần phụ thuộc `jmh-core`, annotation processor, build/run configuration và import phù hợp. JMH xử lý warmup/forks để giảm sai lệch do JIT, nhưng vẫn cần chọn workload thực tế, đo `-prof gc` hoặc allocation/op, thử nhiều payload và bảo đảm kết quả không bị tối ưu bỏ. Trả byte[] từ benchmark làm giá trị có thể quan sát, nhưng chạy benchmark đơn lẻ **không mô phỏng HTTP, network, database, TLS, GC dưới concurrency**.

Kết quả JMH chỉ trả lời “đoạn encode nào nhanh/cấp phát ít hơn trong điều kiện này”. Muốn kết luận API tốt hơn, chạy **load test** qua HTTP với concurrency, response size và client behavior thực, quan sát p95/p99 và các tài nguyên đi kèm. Một serializer nhanh hơn 20% có thể chỉ cải thiện HTTP latency 1% nếu 95% thời gian nằm ở database.

### 12.3. Micrometer và chỉ số end-to-end

Với Spring Boot Actuator/Micrometer, có thể quan sát timer HTTP `http.server.requests` và JVM metrics. Các tên Prometheus phổ biến, tùy version/exporter, gồm:

~~~promql
# Request/s theo URI template đã chuẩn hóa.
sum(rate(http_server_requests_seconds_count{
  uri="/api/v1/orders"
}[5m]))

# P95 HTTP latency khi histogram đã được bật.
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri="/api/v1/orders"
    }[5m])
  )
)

# Tổng allocation bytes/giây khi JVM metric được exporter phát hành.
sum(rate(jvm_gc_memory_allocated_bytes_total[5m]))
~~~

Không phải mọi JVM/GC/binder đều cung cấp series `jvm_gc_memory_allocated_bytes_total`; cần xác minh metric thực tế tại `/actuator/metrics` hoặc `/actuator/prometheus`. Metric này cũng có thể không phải đo allocation chính xác cho mỗi request. Nếu bổ sung timer encode JSON tùy biến, chỉ đo đoạn thực sự encode; tránh dùng request ID/order ID làm metric label.

## 13. Kiểm thử thay đổi tối ưu nhưng không phá REST API

Tối ưu hóa phải có **bộ test tương đương hành vi**. Một benchmark tăng throughput nhưng response mất field, đổi error status hoặc vô tình lộ data là thất bại.

### 13.1. Kiểm tra JSON contract bằng MockMvc

~~~java
@WebMvcTest(OrderQueryController.class)
class OrderSerializationContractTest {
    @Autowired MockMvc mvc;
    @MockitoBean OrderQueryService query;

    @Test
    void writesExpectedJsonAndContentType() throws Exception {
        UUID id = UUID.fromString(
            "8c9b4ca4-2211-4cd0-a949-d176bcb8e35f");
        when(query.findVisibleOrder("alice", id))
            .thenReturn(new OrderSummaryDto(
                id, "PENDING", 259000L, "VND",
                Instant.parse("2026-11-18T10:30:00Z")));

        mvc.perform(get("/api/v1/orders/" + id)
                .with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.status").value("PENDING"))
            .andExpect(jsonPath("$.totalMinor").value(259000))
            .andExpect(jsonPath("$.createdAt")
                .value("2026-11-18T10:30:00Z"));
    }
}
~~~

Ví dụ dùng Spring Security Test, JUnit, Mockito và MockMvc; `@MockitoBean` có ở Spring Framework 6.2/Spring Boot 3.4+, còn dự án Boot 3 cũ hơn thường dùng `@MockBean`. Cần cấu hình security slice đúng để `with(user("alice"))` được nhận. Test này kiểm tra JSON contract ở MVC, **không chứng minh** hiệu năng dưới tải hoặc quyền dữ liệu ở repository; các test đó cần tầng riêng.

### 13.2. Ma trận kiểm thử hiệu năng và correctness

| Trường hợp | Loại kiểm thử chính | Điều cần khẳng định |
| --- | --- | --- |
| JSON field, ngày giờ, null, số lớn | Controller/contract | Không breaking change, đúng content type |
| Quyền đọc field và cross-tenant | Integration/security | Không serialize trường cấm hoặc dữ liệu tenant khác |
| Payload 0/1/100/1000 items | Unit/serialization + integration | Bộ nhớ/độ trễ tăng hợp lý, không thiếu/trùng |
| Collection rất lớn | Load test + profiler | Bounded memory hoặc endpoint từ chối có chủ đích |
| Database projection và N+1 | Integration với DB thật | SQL/query count và dữ liệu đúng |
| Trùng request/concurrency | Integration/load | Không trộn JSON/buffer giữa request |
| Client đọc chậm/ngắt kết nối | HTTP integration/E2E | Hủy/release tài nguyên, không treo thread vô hạn |
| Streaming lỗi sau byte đầu | HTTP integration | Client thấy stream thất bại; không giả 200 hoàn tất |
| gzip qua proxy | E2E/network | `Content-Encoding`, `Vary`, payload giải nén đúng |
| Cache/ETag/304 | Controller + integration/CDN | Không trả sai representation hoặc lộ data khác principal |
| WebFlux cancel và DataBuffer | Reactive integration/leak test | Không rò pooled buffer hoặc block event loop |
| p95/p99, allocation/GC | JFR + load test | Cải thiện có ý nghĩa ở cùng workload |

### 13.3. Kiểm tra codec trực tiếp khi cần

Với bộ encode dùng ObjectWriter riêng:

~~~java
@Test
void codecRoundTripPreservesFields() throws Exception {
    OrderSummaryDto original = new OrderSummaryDto(
        UUID.fromString("8c9b4ca4-2211-4cd0-a949-d176bcb8e35f"),
        "PENDING", 259000L, "VND",
        Instant.parse("2026-11-18T10:30:00Z"));

    byte[] json = codec.encode(original);
    OrderSummaryDto restored = codec.decode(json);

    assertThat(restored).isEqualTo(original);
}
~~~

Test này hữu ích khi team thực sự có codec tùy biến, nhưng **round-trip không đủ cho API contract**: serializer và deserializer có thể cùng sai một định dạng mà test vẫn pass. Cần thêm assertions cho JSON field hoặc snapshot hợp đồng. Đối với lỗi input, test JSON vượt max nesting/string length và kiểm tra trả `400`/`413` theo chính sách, không để ứng dụng trả stack trace hoặc hết bộ nhớ.

## 14. Các lỗi tối ưu hóa thường gặp

1. **Tối ưu Jackson khi DB vẫn chiếm 90% latency:** giảm vài microsecond encode nhưng bỏ qua query N+1.
2. **Tạo `new ObjectMapper()` mỗi request:** mất lợi ích cache cấu hình, dễ khác JavaTimeModule với Spring.
3. **Trả entity JPA trực tiếp:** lazy load, quan hệ vòng, dữ liệu nội bộ và độ dài JSON khó kiểm soát.
4. **Serialize thành String rồi thành byte[]:** thêm copy và tăng short-lived allocations dù converter đã có sẵn.
5. **Dùng `ByteArrayOutputStream` chung toàn ứng dụng:** data race, trộn dữ liệu giữa request; khóa lại thì trở thành điểm nghẽn.
6. **Dùng ThreadLocal buffer không có cap:** thread sống lâu giữ mảng lớn sau một request bất thường.
7. **Dùng buffer direct/pool mà không quản lý ownership:** off-heap leak không luôn hiện rõ trong heap graph.
8. **Streaming với list đã nạp hết:** không giảm peak memory ở tầng query/materialization.
9. **Giữ `@Transactional` quá lâu khi streaming:** chiếm connection/lock nhiều phút, gây bão hòa pool.
10. **Flush từng record:** tạo nhiều write nhỏ, giảm throughput và làm tăng CPU.
11. **Bật nén mọi response:** CPU và độ trễ có thể tăng với response nhỏ, đã nén hoặc nhạy cảm.
12. **Cache byte[] theo URL mà bỏ principal/tenant/headers:** lộ dữ liệu hoặc trả representation sai.
13. **Chỉ xem `jvm.memory.used`:** bỏ qua allocation rate, direct memory, GC pause và buffer pool.
14. **Tin benchmark micro là kết quả production:** tải đồng thời, network và database có thể thay đổi hoàn toàn kết luận.
15. **Bỏ validation để giảm CPU:** malformed JSON sâu/lớn có thể gây DoS; security và tính đúng đắn quan trọng hơn tối ưu cục bộ.

## 15. Bài tập thực hành

**Bài tập 1 — Tìm bản sao thừa.** Endpoint đang làm `entity → Map → String(JSON) → byte[] → ResponseEntity<byte[]>`. Hãy lập sơ đồ bộ nhớ tạm và thay bằng projection/DTO được Spring serialize trực tiếp. Đo response size, JSON contract, allocation bytes/request và p95 latency trước/sau. Giải thích vì sao không thể hứa “zero-copy” với JSON qua HTTP.

**Bài tập 2 — Quản lý Jackson đúng vòng đời.** Refactor service tạo `new ObjectMapper()` theo từng request thành mapper do Spring quản lý và `ObjectWriter` dành cho DTO ổn định. Viết test cạnh tranh với nhiều request đồng thời và test JSON ngày giờ/null/decimal; nêu vì sao thay cấu hình mapper sau lần dùng đầu là không an toàn.

**Bài tập 3 — Phân trang thay vì streaming vô hạn.** API trả tất cả order của một tenant (hàng trăm nghìn record). Hãy thiết kế `GET /orders?limit=...&cursor=...` với page-size max, thứ tự ổn định và projection. So sánh với một endpoint export bất đồng bộ trả `202`, file NDJSON và status resource. Xác định trường hợp nào cần snapshot nhất quán và cách kiểm soát quyền tải file.

**Bài tập 4 — StreamingResponseBody.** Tạo endpoint export JSON array, fetch 100 record mỗi lần, sử dụng Jackson `JsonGenerator`. Thử client ngắt kết nối khi đã gửi một phần body, thử truy vấn lỗi ở trang thứ hai và kiểm tra transaction/resource cleanup. Chỉ ra vì sao server không thể sửa status thành `500` sau khi byte đầu đã được gửi.

**Bài tập 5 — Buffer và compression.** So sánh output thông thường, output có `ByteArrayOutputStream` trung gian và output nén gzip trên ba loại payload: 300 B, 30 KiB và 3 MiB. Đo CPU/GC, kích thước truyền thực, time-to-first-byte và p95 dưới concurrency. Kiểm tra `Content-Encoding`/`Vary` và không dùng dữ liệu nhạy cảm trong fixture.

**Bài tập 6 — Profiling và benchmark.** Dùng JFR tìm allocation hotspot của `GET /api/v1/orders`. Viết JMH benchmark cho Jackson `writeValueAsString` và `writeValueAsBytes` trên một DTO nhỏ và một trang 100 DTO, đo allocation/op và throughput. Chạy HTTP load test để xác minh hiệu ứng end-to-end, báo cả kết quả không cải thiện.

**Bài tập 7 — Giới hạn JSON và dữ liệu nhạy cảm.** Tạo payload JSON lồng sâu, chuỗi quá dài và array cực lớn trong môi trường test. Đặt giới hạn request body và parser theo hợp đồng, kiểm tra API trả lỗi ổn định không lộ stack trace. Với hai tenant khác nhau, chứng minh serialization không bao giờ xuất field hoặc object không thuộc quyền truy cập.

### Tiêu chí đánh giá

Lời giải đạt yêu cầu khi (1) chỉ ra bottleneck có số đo; (2) giữ hợp đồng HTTP/JSON không thay đổi trái chủ đích; (3) giảm payload và object/copy không cần thiết; (4) dùng Jackson và buffer đúng ownership/lifetime; (5) streaming, cache và compression được chọn theo đặc điểm payload và rủi ro; (6) có test concurrency/slow client/error/security; và (7) báo benchmark có workload, JDK, response size, GC, CPU, p95/p99 cùng giới hạn của kết luận.

## 16. Checklist review hiệu năng serialization

- [ ] Đã có baseline p95/p99, throughput, response bytes, allocation/GC và phần DB/DTO/encode/network.
- [ ] Resource list có pagination/field projection; entity graph/SQL không làm phát sinh N+1 và tải dữ liệu thừa.
- [ ] JSON contract có test cho field, null, enum, ngày giờ, số và Content-Type; OpenAPI phản ánh representation.
- [ ] Spring-managed Jackson mapper được cấu hình trước sử dụng, không tạo lại/đổi config theo request.
- [ ] Không chuyển qua String/byte[]/JSON tree trung gian nếu không có yêu cầu nghiệp vụ rõ ràng.
- [ ] Buffer không chia sẻ mutable state giữa request, không giữ ThreadLocal mảng khổng lồ, không có direct memory leak.
- [ ] Compression được đo và kiểm tra qua gateway, xử lý `Vary`/cache key và dữ liệu nhạy cảm đúng.
- [ ] Streaming có bounded paging/limit/deadline, xử lý client cancel/partial response và lifecycle transaction.
- [ ] WebFlux không block event loop; pooled DataBuffer được xử lý theo đúng ownership.
- [ ] Không cache representation riêng tư sai principal/tenant; ETag/304 đúng phiên bản và hợp đồng.
- [ ] Parser/request-body limit, input validation, field-level authorization và log redaction vẫn được duy trì.
- [ ] Kết quả tối ưu đã được kiểm chứng bởi JFR/JMH phù hợp cùng HTTP load test; không đánh đổi lỗi hoặc bảo mật lấy một benchmark đẹp.

**Điểm cốt lõi:** tối ưu serialization có hiệu quả nhất khi bắt đầu từ **dữ liệu thực sự cần trả**, tiếp đến giảm công việc ánh xạ, tránh bản sao JSON trung gian và quản lý buffer theo đúng vòng đời. Jackson, streaming, pooling, compression và caching đều có trade-off; chỉ chấp nhận thay đổi khi có số đo cải thiện ở workload phù hợp **và** kiểm thử chứng minh REST contract, quyền truy cập, giới hạn tài nguyên và dữ liệu vẫn chính xác.
