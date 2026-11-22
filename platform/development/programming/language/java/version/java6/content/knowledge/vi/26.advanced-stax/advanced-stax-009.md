# Giới hạn dữ liệu đầu vào và kiểm thử XML độc hại với StAX (Java 17+)

## 1. Vì sao một XML parser nhanh vẫn cần giới hạn?

**StAX (Streaming API for XML)** của Java cho phép xử lý XML tuần tự bằng `XMLStreamReader` hoặc `XMLEventReader`, thường không phải dựng toàn bộ DOM. Tuy nhiên, **streaming không đồng nghĩa XML đầu vào luôn an toàn**. Một request chứa XML quá lớn, quá sâu, có hàng triệu attributes/phần tử, một text field khổng lồ hoặc khai báo external entity vẫn có thể làm ứng dụng chậm, hết heap, chiếm connection hoặc truy cập tài nguyên ngoài nếu parser cấu hình sai.

Chủ đề này tập trung vào hai việc bổ sung cho nhau:

1. **Giới hạn dữ liệu đầu vào theo nhiều lớp:** giới hạn bytes từ nguồn; số element, depth, attributes, text units và số business records ngay trong StAX event loop; timeout/concurrency và ngân sách nguồn lực từ HTTP/JDBC/file.
2. **Kiểm thử XML độc hại có kiểm soát:** xây dựng bộ mẫu XML hợp lệ và bất hợp lệ để chứng minh từng giới hạn phát huy tác dụng, phát hiện cấu hình XXE/DTD yếu, xác minh cleanup và tránh công bố kết luận sai chỉ dựa vào một test.

Điểm quan trọng: **Không có một cờ duy nhất giải quyết tất cả XML attacks.** `XMLInputFactory.SUPPORT_DTD=false` và `IS_SUPPORTING_EXTERNAL_ENTITIES=false` giúp chặn nhiều rủi ro liên quan DTD/entities, nhưng **không** thay thế giới hạn kích thước, độ sâu, thuộc tính, text hoặc thời gian. Ngược lại, chỉ giới hạn bytes **không** bảo đảm XXE không truy cập file/network khi DTD được bật.

Ví dụ luồng bảo vệ:

```text
HTTP / file / JDBC / import
           |
  [1] Authentication + source allowlist
           |
  [2] Transfer/compressed-size policy
           |
  [3] Bounded InputStream: max decoded XML bytes
           |
  [4] XMLInputFactory: block DTD/external entities
           |         + external DTD protocols = ""
           |         + deny XMLResolver
           |
  [5] XMLStreamReader / XMLEventReader
           |
  [6] Element/depth/attributes/text counters
           |
  [7] Validate namespaces / structure / business data
           |
  [8] Bounded sink + deadlines + backpressure
           |
  [9] Close parser, close input, rollback/cleanup if needed
```

**Special Note:** tất cả hướng dẫn dùng API đang được hỗ trợ trên Java 17 trở lên, với lưu ý triển khai JAXP/StAX provider và JDK hiện đại. Không dùng code XML parser legacy thiếu chống XXE.

### 1.1. Phạm vi và các API chính

| Thành phần | API | Tác dụng |
| --- | --- | --- |
| Parser factory | `javax.xml.stream.XMLInputFactory` | Tạo parser, tắt DTD/external entities, đặt security limits do provider hỗ trợ. |
| Cursor parser | `javax.xml.stream.XMLStreamReader` | Duyệt `START_ELEMENT`, `CHARACTERS`, `END_ELEMENT` và đếm giới hạn. |
| Event parser | `javax.xml.stream.XMLEventReader` | Nhận `XMLEvent` objects; tương tự cần giới hạn và hardening. |
| XML security constants | `javax.xml.XMLConstants` | Đặt `ACCESS_EXTERNAL_DTD` khi provider hỗ trợ. |
| I/O | `java.io.InputStream` / `FilterInputStream` / `Reader` | Giới hạn dữ liệu thực sự được đọc, đóng nguồn đúng cách. |
| JDK XML processing limits | `jdk.xml.maxElementDepth`, `jdk.xml.elementAttributeLimit`… | Các tùy chọn **JDK-specific**, không phải tên property portable cho mọi StAX provider. |
| Runtime budgets | Deadline, thread/connection pool, bounded queue | Hạn chế CPU, thời gian, đồng thời và downstream memory. |

Các package `javax.xml.stream` vẫn nằm trong module **`java.xml`** trên JDK hiện đại; tên package có `javax` **không** có nghĩa là StAX đã bị loại bỏ.

## 2. Threat model: những đầu vào XML xấu cần chuẩn bị

Một hệ thống nhận XML từ ngoài trust boundary có thể gặp:

| Loại đầu vào | Ví dụ ngắn | Rủi ro chính | Lớp kiểm soát |
| --- | --- | --- | --- |
| Tài liệu quá nhiều bytes | Một element chứa MB/GB text. | Tốn băng thông, heap, thời gian. | Giới hạn **decoded bytes** trên InputStream + ingress controls. |
| XML lồng sâu | `<a><a><a>...</a></a></a>` | Tốn parser stack/state, CPU, code dùng recursion có thể overflow. | `maxElementDepth` hoặc đếm depth trong event loop. |
| Quá nhiều elements | Hàng triệu `<item/>`. | CPU, object allocations, logic tạo records quá nhiều. | Element count/record count, time budget. |
| Quá nhiều attributes | Một element có hàng nghìn attributes. | Parsing/memory overhead, validation complexity. | Attribute count JDK/provider và per-event business limit. |
| Text field cực dài | `<comment>...rất dài...</comment>` | Heap nếu `getElementText()`/StringBuilder không giới hạn. | Cộng text units theo event và giới hạn field/total. |
| Entity expansion | DTD tạo entities lồng nhau / “billion laughs”. | CPU/memory exhaustion. | Disable DTD/entity expansion; provider limits nếu bắt buộc dùng DTD. |
| XXE / SSRF | Entity tham chiếu `file://` hoặc `http://`. | Lộ file/metadata, outbound requests. | Disable external entities, deny resolver và external DTD access. |
| Malformed XML | Tags không đóng, attributes sai escaping. | Exception, partial processing, log spam. | Parser errors + rollback/cleanup; không retry y nguyên. |
| Encoding không hợp lệ | UTF-8 bytes bị cắt hoặc XML prolog sai. | Parse error, dữ liệu lỗi, validation bypass. | Decode theo contract, test BOM/prolog, byte limit. |
| Namespace/schema lạ | Trùng local name nhưng khác namespace URI. | Xử lý nhầm records, logic bypass. | QName URI + local name, validate root/structure. |
| XML sinh lỗi từ nguồn nén | ZIP/gzip nhỏ nhưng giải nén rất lớn. | Decompression bomb. | Giới hạn **sau giải nén** và cả compressed input, ratio/cpu budget. |
| Dữ liệu bên ngoài trong XSLT/XSD | `xsl:include` / `xs:import` / `document()`. | Tải network/file bằng API khác StAX. | Harden riêng `TransformerFactory`/`SchemaFactory`. |

**Không chỉ kiểm thử XXE.** Tài liệu không chứa DTD vẫn có thể gây DoS bằng số lượng nodes, độ sâu hay field size. Tài liệu nhỏ vẫn có thể nguy hiểm khi parser cho tải external entity. Các biện pháp kiểm soát phải **bổ sung nhau**.

### 2.1. Không dùng “đã lưu DB” làm tín hiệu tin cậy

XML trong database vẫn có thể xuất phát từ upload, một service khác, file đối tác hoặc dữ liệu cũ được chèn trước khi parser được harden. `SQLXML.getCharacterStream()` chỉ là một cách lấy dữ liệu JDBC; nó **không thực hiện sanitization** và không bảo đảm parser phía ứng dụng từ chối external DTD. Áp cùng policy cho XML không tin cậy bất kể nguồn là DB, HTTP hay file.

### 2.2. Giới hạn nào dùng đơn vị nào?

Cần phân biệt:
- **Bytes**: `InputStream` / payload sau giải nén; UTF-8 emoji thường nhiều bytes.
- **Java `char` units**: `Reader`, `String.length()`, `XMLStreamReader.getTextLength()`; Unicode ngoài BMP (ví dụ `🌏`) thường chiếm **hai** UTF-16 units.
- **Unicode code points**: `String.codePointCount(...)`; khác char units.
- **Grapheme clusters**: ký tự người dùng nhìn thấy; dấu kết hợp có thể tạo nhiều code points.
- **Element count/depth**: cấu trúc XML, không phụ thuộc bytes.
- **Attribute count**: số thuộc tính trên **mỗi** START_ELEMENT; khác tổng thuộc tính toàn tài liệu.
- **Business record count**: số `<order>` hợp lệ ở vị trí/schema mong đợi, không đồng nghĩa số XML elements.

Ví dụ một XML có emoji và dấu tiếng Việt có thể vượt budget byte nhưng chưa vượt budget char, hoặc ngược lại tùy dữ liệu/encoding. **Không thay byte limit bằng String.length()**.

## 3. Bảy lớp giới hạn hợp lý

### 3.1. Lớp 1 — Nguồn và quyền truy cập

Trước khi parse:
- Chỉ chấp nhận content types/nguồn theo policy ứng dụng; không biến `Content-Type` thành tín hiệu an toàn tuyệt đối.
- Dùng TLS, xác thực, authorization và host/path allowlist cho HTTP/file.
- Không chuyển trực tiếp URL/file path từ người dùng vào một parser có quyền tự mở tài nguyên; XXE controls **không hạn chế việc ứng dụng tự mở nguồn ban đầu**.
- Với upload, giới hạn dung lượng **khi nhận** trước khi ghi tạm; không dựa hoàn toàn vào HTTP `Content-Length` vì request có thể chunked hoặc header khai sai.
- Với file nén, giới hạn cả compressed size, decompressed size, số entries và tỷ lệ/CPU giải nén.
- Với JDBC, giới hạn kích thước lấy từ database nếu schema/vendor hỗ trợ; chú ý connection/transaction có thể bị giữ suốt quá trình parse.

### 3.2. Lớp 2 — InputStream có giới hạn byte thật

**Đừng chỉ kiểm tra `Content-Length` rồi tin rằng payload không thể dài hơn.** Khi nhận streaming source, cần một wrapper đếm số bytes đã đọc và **từ chối trước khi ứng dụng tiêu thụ lượng vượt budget**.

Cách tưởng như đúng nhưng thực chất không an toàn:

```java
// SAI: giới hạn này chỉ cắt input, không báo lỗi khi input bị dài hơn.
InputStream silentlyTruncated =
        new java.io.ByteArrayInputStream(allBytes, 0, allowedBytes);
```

Đây là snippet sai có chủ ý. Cắt XML âm thầm có thể tạo file thiếu hoặc làm parser chỉ thấy một XML ngắn nhưng nguồn thật có dữ liệu ngoài budget. **Phải reject, không truncate.** Ngoài ra, `InputStream.available()` không cho biết tổng kích thước dữ liệu còn lại trên network stream, nên không dùng để quyết định “payload nhỏ”.

Một wrapper đúng hướng:
- Theo dõi byte counter khi `read()` hoặc `read(byte[],off,len)` được gọi.
- Cho đọc **tối đa phần budget còn lại cộng một byte kiểm tra** để phát hiện vượt ngưỡng.
- Ném `IOException` hoặc typed limit exception ngay khi tổng số bytes đã đọc vượt ngưỡng.
- Không cho `skip()/reset()` đi vòng qua bộ đếm nếu wrapper được dùng như một security boundary.
- Đóng underlying InputStream trong `try-with-resources`.
- Trong production còn phải có **deadline/timeout**, không chỉ byte counter.

Ví dụ hoàn chỉnh `BoundedInputStream` ở mục 7 thực hiện những điều trên. Trong bản demo, đầu vào được tạo từ `byte[]` để dễ chạy độc lập; **đó không phải cách ingest file lớn trong production**. Với ứng dụng thực, wrap trực tiếp `InputStream` từ HTTP/file/JDBC phù hợp, không materialize toàn bộ XML trước.

### 3.3. Lớp 3 — Parser được harden trước createXMLStreamReader()

Dùng `XMLInputFactory.newDefaultFactory()` khi muốn built-in JDK provider; nếu dùng `newFactory()` qua JAXP provider discovery, phải kiểm tra implementation và security settings thực tế.

```java
XMLInputFactory factory =
        XMLInputFactory.newDefaultFactory();

factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");

factory.setXMLResolver(
        (publicId, systemId, baseURI, namespace) -> {
            throw new XMLStreamException("EXTERNAL_REFERENCE");
        });
```

Đây là **snippet**; cần imports `javax.xml.XMLConstants`, `XMLInputFactory`, `XMLStreamException`. Các thiết lập phải thực hiện **trước** khi gọi `createXMLStreamReader(...)` hoặc `createXMLEventReader(...)`.

**Mục đích riêng từng lựa chọn:**
1. `SUPPORT_DTD=false`: không cần xử lý DTD cho tài liệu dữ liệu thông thường.
2. `IS_SUPPORTING_EXTERNAL_ENTITIES=false`: không cho resolve external parsed entities.
3. `ACCESS_EXTERNAL_DTD=""`: không có protocol external DTD/entity nào được phép.
4. `XMLResolver` ném lỗi: không fallback tới file/network resource.
5. `IS_NAMESPACE_AWARE=true`: code kiểm tra được URI/local name thay vì coi prefix là định danh.
6. Event loop có thể từ chối thêm sự kiện `DTD` và `ENTITY_REFERENCE`.

**Giới hạn của thuộc tính:** `SUPPORT_DTD=false` **không bảo đảm mọi StAX provider ném exception khi thấy `<!DOCTYPE>`**. Có implementation bỏ qua DTD. Vì vậy, nếu policy **cấm mọi DOCTYPE**, phải kiểm thử và enforce với parser/provider có khả năng reject hoàn toàn; không tự viết regex đơn giản rồi gọi đó là parser an toàn. Trong demo, các payload DTD/entity được kiểm thử và bị từ chối trên JDK sử dụng, nhưng kết quả đó **không chứng minh tính chất tương tự trên tất cả provider**.

**Fail closed:** nếu một security setting bắt buộc không được provider hỗ trợ và `setProperty()` ném `IllegalArgumentException`, hãy **ngừng xử lý XML không tin cậy**. Không catch rồi tiếp tục parse bằng cấu hình yếu hơn.

**Không áp `XMLConstants.FEATURE_SECURE_PROCESSING` cho StAX như DOM/SAX**: StAX không hỗ trợ directive đó theo cùng contract; sử dụng chính các StAX controls và JAXP/JDK-specific processing limits. <escape>Không</escape> bật lại DTD chỉ để parser chấp nhận một XML test có DOCTYPE.

### 3.4. Lớp 4 — JDK/provider processing limits

Trên built-in JDK parser, tài liệu bảo mật JAXP nêu các processing limit properties như:

| Property (JDK-specific) | Giới hạn |
| --- | --- |
| `jdk.xml.maxElementDepth` | Độ sâu XML element tối đa. |
| `jdk.xml.elementAttributeLimit` | Số attributes tối đa trên mỗi element. |
| `jdk.xml.entityExpansionLimit` | Số lần entity expansion. |
| `jdk.xml.totalEntitySizeLimit` | Tổng kích thước entities. |
| `jdk.xml.maxGeneralEntitySizeLimit` | Kích thước một general entity. |
| `jdk.xml.maxParameterEntitySizeLimit` | Kích thước parameter entities. |
| `jdk.xml.maxXMLNameLimit` | Độ dài các XML names. |
| `jdk.xml.entityReplacementLimit` | Tổng nodes do entity replacement tạo ra. |

Các giá trị là **cấu hình phụ thuộc JDK implementation và version**. Với một số giới hạn, giá trị `0` hoặc âm có thể mang nghĩa **không giới hạn**, nên không đặt 0 để “tắt nguy cơ”. Đặt **mức dương phù hợp workload** và test error behavior. Giá trị default thay đổi theo release và có thể khác tài liệu của nhà cung cấp JDK; không hard-code kỳ vọng bảo mật vào default.

Ví dụ trên built-in JDK StAX:

```java
XMLInputFactory factory =
        XMLInputFactory.newDefaultFactory();

factory.setProperty("jdk.xml.maxElementDepth", "16");
factory.setProperty("jdk.xml.elementAttributeLimit", "32");
factory.setProperty("jdk.xml.entityExpansionLimit", "256");
```

Đây là **snippet tùy chọn phụ thuộc JDK**, không phải chuẩn StAX portable cho Woodstox/Aalto hoặc mọi provider. Đặt thêm các cấu hình DTD/external-entity protection như mục 3.3; **không dùng entityExpansionLimit thay cho tắt DTD**. Ví dụ runnable ở mục 8 kiểm chứng một số JDK-specific properties trên môi trường JDK thử nghiệm. Không suy việc `setProperty` thành công nghĩa mọi XML bombs đã được chặn.

### 3.5. Lớp 5 — Giới hạn trong event loop

Ngay cả khi parser có native limits, application nên áp **business budgets**:
- `maxDepth`: tăng ở START_ELEMENT, giảm ở END_ELEMENT, từ chối nếu vượt.
- `maxElements`: tăng tại mỗi START_ELEMENT, không chỉ khi có record.
- `maxAttributes`: kiểm tra `xml.getAttributeCount()` ở START_ELEMENT.
- `maxTextUnits`: cộng `xml.getTextLength()` trên CHARACTERS/CDATA/SPACE events.
- `maxRecords`: đếm đúng `<order>` ở depth/namespace hợp lệ.
- `maxFieldLength`: giới hạn text của **một** field, không chỉ tổng text.
- Kiểm tra root, namespace URI, local name, attribute whitelist, numeric precision và cấu trúc parent-child.

**Tại sao kiểm tra “trước khi làm việc”?** Nếu đã tạo một `StringBuilder` lớn hoặc insert record vào DB rồi mới phát hiện limit ở cuối document, ứng dụng đã tiêu thụ tài nguyên hoặc gây side effects. Khi có thể, increment + compare trước khi append/allocate/output.

`getElementText()` của `XMLStreamReader`/`XMLEventReader` thuận tiện với text-only field nhỏ, nhưng **có thể materialize text quá lớn** nếu input độc hại. Với field không được tin cậy, xử lý `CHARACTERS` events theo chunks và áp giới hạn trước khi tích lũy vào String.

**Không nhầm whitespace với không có dữ liệu:** việc một phần text là whitespace còn phụ thuộc XML schema/mixed content; muốn bảo toàn document semantics thì đừng tự xóa whitespace ngoài contract.

### 3.6. Lớp 6 — Timeout, concurrency và backpressure

Byte/depth/text limits là **nguồn lực hữu hạn**, không phải deadline. InputStream có thể gửi một byte mỗi 30 giây hoặc downstream có thể chặn khi ghi DB/network. Hãy có:
- Read/connect/request timeouts ở HTTP client/server.
- Deadline cho job, cancellation và đóng source khi hủy.
- JDBC query/network/socket timeouts tùy driver, giới hạn thời gian giữ connection.
- Concurrency limit và queue bounded; không cho mỗi request XML giữ một thread/connection vô thời hạn.
- Batch size và idempotency khi đã ghi một phần records trước khi bị từ chối.
- CPU budget/worker isolation cho untrusted XML nếu có nguy cơ DoS cao.

**Không dùng `Thread.stop()`, `Runtime.exec()` hay cơ chế lỗi thời** để hủy parser. Điều khiển cancellation/timeout ở tầng I/O và execution, đảm bảo cleanup.

### 3.7. Lớp 7 — Validation và output policy

“XML well-formed” **không** có nghĩa “đúng XML schema nghiệp vụ”. Cần:
- Validate root + namespace, child ordering, required attributes/fields.
- Validate numeric/date/text lengths và các business invariants.
- Nếu cần XSD, dùng `SchemaFactory`/`Validator` được harden riêng, khóa external DTD/schema access, dùng trusted schemas.
- Nếu dùng XSLT/Transformer, khóa external stylesheet/DTD access ở `TransformerFactory`.
- Nếu deserialize XML sang domain objects, bảo đảm parser mà framework dùng đã được kiểm soát. Không pass raw XML cho framework có thể tự khởi tạo parser yếu.

Một parser đã tắt XXE **không tự làm input trở nên an toàn** với mọi downstream transformations. Nếu XML có các embedded URLs/path được business logic sử dụng, còn phải validate/authorize ở cấp ứng dụng.

## 4. Quy tắc dữ liệu StAX khi xây bộ giới hạn

### 4.1. Event model cho việc đếm

| StAX event | Counter/check | Ghi chú |
| --- | --- | --- |
| `START_ELEMENT` | ++depth, ++elements, attribute count, namespace/root. | Kiểm tra giới hạn trước khi xử lý record. |
| `END_ELEMENT` | --depth. | Dùng khi kết thúc scope; XML parser bảo đảm matching tags nếu input well-formed. |
| `CHARACTERS` | +`getTextLength()`. | Một element có thể có nhiều CHARACTERS events. |
| `CDATA` | +`getTextLength()`. | Tùy `IS_COALESCING`, CDATA có thể xuất hiện như CHARACTERS. |
| `SPACE` | +`getTextLength()` nếu budget tính cả whitespace. | Đừng bỏ qua whitespace nếu có ý nghĩa. |
| `DTD` | Reject nếu policy cấm. | Một số provider chỉ bỏ qua DTD khi SUPPORT_DTD=false. |
| `ENTITY_REFERENCE` | Reject theo policy. | Không thay việc disable external entities. |
| `COMMENT`, `PROCESSING_INSTRUCTION` | Tùy policy và budget. | Comments/PI cũng có thể lớn; byte budget vẫn bao phủ. |

**`XMLStreamReader.getTextCharacters()`** trả mảng ký tự gắn với **event hiện tại**, không nên giữ mảng qua `next()`. Với text rất dài, hãy xử lý chunks hiện tại (hoặc `getTextCharacters(int,char[],...)`), hạn chế tổng và field length. Đừng sao chép toàn bộ vào List trước khi kiểm tra limit.

### 4.2. Tên và namespace không được bỏ qua

Dữ liệu độc hại có thể đặt tag `<other:order>` với local name `order` nhưng namespace không được phép. Vì vậy, trong ứng dụng cần kiểm tra **QName/namespace URI + local name**, không chỉ `getLocalName()`. Cũng phải giới hạn độ dài element/attribute names và số namespace declarations (đây là metadata có chi phí).

Trong bài chạy được ở mục 7, XML test được cố ý giữ schema đơn giản, chưa có namespace; phần production cần bổ sung allowlist namespace khi XML contract yêu cầu. Đừng xem demo là XML schema validator toàn diện.

### 4.3. Không dùng regex DOCTYPE đơn giản làm giải pháp chính

Kiểm tra `xml.contains("<!DOCTYPE")` trước khi parse có vẻ dễ nhưng:
- Có thể đọc không hết tài liệu nếu đầu vào streaming.
- Có thể xử lý sai XML encoding/BOM, whitespace, ký tự kết hợp, comments/CDATA.
- Có thể cho kết quả giả hoặc bỏ sót theo cách XML parser phân tích.
- Không tự giới hạn external resources của parser nếu kiểm tra sai.

**Hãy chặn DTD/entity ở parser và enforce parser/provider policy**, đồng thời kiểm thử DOCTYPE có và không có references. Nếu cần reject mọi DOCTYPE trên Java 17 với guarantee theo provider, chọn parser có cơ chế reject thực sự, hoặc một tầng validation được kiểm soát, thay vì dựa vào regex trên XML thô.

## 5. Thiết kế bộ kiểm thử: positive + negative + observability

Một bộ test tốt cần cả XML hợp lệ lẫn XML xấu. Nếu mọi input đều bị từ chối do cấu hình sai, security test “không nhận XXE” vẫn có thể báo pass giả. **Bắt buộc có positive control**.

### 5.1. Test matrix tối thiểu

| Test | Dữ liệu | Kỳ vọng |
| --- | --- | --- |
| Valid document | `<orders>` có 2 order và tiếng Việt/emoji. | ACCEPT; đúng số records và dữ liệu. |
| Over bytes | XML có text 500 bytes/ký tự, byte cap thấp hơn. | REJECT bởi bộ giới hạn nguồn. |
| Over depth | Các phần tử lồng nhau vượt depth budget. | REJECT trước khi tạo domain records sâu hơn. |
| Over elements | Nhiều empty elements/records hơn element budget. | REJECT dù XML well-formed. |
| Over attributes | Một element có nhiều attributes. | REJECT trước khi dùng attributes. |
| Over text | Text hợp lệ nhưng vượt tổng text budget. | REJECT mà không build String dài. |
| Malformed XML | Thiếu end tag. | REJECT qua `XMLStreamException`. |
| External entity | DTD có `SYSTEM "file:///not-for-reading"` được tham chiếu. | REJECT và không cho file/network access. |
| Internal DTD/entity | DTD khai báo entity nội bộ. | REJECT theo strict policy của bài test/provider. |
| Empty/simple DOCTYPE | `<!DOCTYPE orders><orders/>`. | Nếu yêu cầu cấm mọi DOCTYPE, phải REJECT (test riêng provider). |
| Very long name | XML tag/attribute name cực dài. | REJECT theo provider name-size policy hoặc application schema. |
| Wrong namespace/root | Root khác schema hoặc namespace giả. | REJECT ở application validation. |
| Invalid UTF-8 | Byte sequence bị cắt. | REJECT hoặc báo decode error, không “sửa âm thầm”. |
| Nested compression | Input nén nhỏ, output XML rất lớn. | REJECT ở decompressed-stream byte limit. |
| Many slow requests | Nhiều clients gửi chậm. | Không chiếm hết threads/connection pool; timeout/cancel. |

Bảng có kết quả kỳ vọng **theo chính sách bài học**, không tự nhận mọi StAX provider đều ném cùng exception class/message. Thực thi test ở JDK/provider thật và kiểm tra đúng causal path.

### 5.2. “REJECTED” chưa đủ chứng minh không có XXE

Một parser có thể đã đọc file/đã gửi HTTP request rồi mới ném lỗi ở bước khác. Vì vậy test XXE production phải:
- Cấu hình external access deny ngay từ factory.
- Có **deny resolver** phát hiện/đếm mọi yêu cầu resolve.
- Trong integration test được kiểm soát, dùng file canary hoặc local HTTP sink an toàn và kiểm tra **không có side effect**.
- Không chạy payload trỏ tới credential files, metadata endpoints hoặc internet thực.
- Kiểm tra parser provider và security configuration trong CI.
- Thêm positive control XML hợp lệ để không có false positive do mọi parse đều fail.

Ví dụ mục 7 in `externalEntity=REJECTED` vì input độc hại không được chấp nhận. **Nó không độc lập chứng minh parser chưa từng cố thực hiện file/network I/O** trên mọi provider; việc đó phải kết hợp cấu hình deny và integration instrumentation.

### 5.3. Test error handling không được che mất nguyên nhân

Tránh:

```java
// SAI: catch mọi lỗi và âm thầm coi đây là XML hợp lệ rỗng.
try {
    parseXml(input);
} catch (Exception ignored) {
    return Collections.emptyList();
}
```

Đây là **pseudocode sai có chủ ý**, thiếu khai báo `parseXml`/`input`. Hệ thống thật phải trả lỗi phân loại được hoặc dừng job/rollback, không biến XML độc hại thành dữ liệu “không có order”.

Trong test, có thể catch `XMLStreamException`, `IOException` và validation exception để assert reject, nhưng **production cần phân biệt lý do** (bytes, depth, XXE, syntax, business schema) và chính sách response/log/metrics. Đừng phơi bày payload XML hoặc secrets trong client errors.

## 6. Mẫu bảo vệ nhiều lớp trong Java 17+

Ví dụ chính dùng:
- **`BoundedInputStream`**: bảo đảm ứng dụng phát hiện vượt budget số bytes đã đọc.
- **`secureFactory()`**: tắt DTD, external entities và deny external access.
- **`parse(...)`**: đọc `XMLStreamReader` với các counters depth, elements, attributes và text units.
- **`parseText(...)`**: helper tạo bytes UTF-8 từ một string **chỉ để test độc lập**; production nên truyền trực tiếp HTTP/file InputStream.
- **`expectReject(...)`**: chạy negative tests với assertion; nếu tài liệu xấu bị accept, test **thất bại**, không in thành công giả.
- **Positive test**: XML hợp lệ có 2 orders với giá trị thập phân, tiếng Việt và emoji.

### 6.1. Lựa chọn budget cho demo

Đây là giá trị nhỏ chỉ dùng trong unit demo:

```java
new Limits(
    240, // maxBytes: số bytes UTF-8 đọc được
    3,   // maxDepth: độ sâu element
    4,   // maxElements: tổng số start elements
    2,   // maxAttributes: attributes/element
    60   // maxTextUnits: tổng Java char units trong text events
);
```

Đừng sử dụng các ngưỡng này làm policy production mặc định. Production budgets phải dựa trên độ lớn file hợp lệ, schema và threat model thực tế. Một file XML 241 bytes không “độc hại” về bản chất; nó bị từ chối vì **vượt ngân sách của demo**.

### 6.2. Vì sao phải kiểm tra đếm trước khi tích lũy?

Ở `START_ELEMENT`, tăng depth/elements và so sánh với limit trước khi tạo record. Với `CHARACTERS`, cộng `getTextLength()` rồi dừng nếu vượt tổng budget. Khi xử lý giá trị tiền, validate format/độ dài trước khi `new BigDecimal(...)`. Không dùng `double` để cộng số thập phân tiền tệ.

**Giới hạn trong bài** chỉ bao phủ một phần resource exhaustion: chưa có timeout đa luồng, max XML names/namespace declarations, decompression ratio, per-field text, actual HTTP size và quotas phía DB. Những lớp đó phải được bổ sung cho deployment thật.

## 7. Chương trình hoàn chỉnh: StaxAdversarialTests.java

Ví dụ Java 17+ dưới đây **tự chạy được**, dùng đúng JDK APIs, không cần Maven/JDBC driver/database. Nó có một positive test và **8 negative tests** nhằm vào các lớp bảo vệ khác nhau.

### 7.1. Toàn bộ mã nguồn

Lưu file **`StaxAdversarialTests.java`** bằng UTF-8:

```java
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import javax.xml.XMLConstants;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

public final class StaxAdversarialTests {
    record Limits(long maxBytes, int maxDepth, int maxElements,
                  int maxAttributes, long maxTextUnits) {}

    record Summary(int orders, BigDecimal total, long textUnits) {}

    static final class BoundedInputStream extends FilterInputStream {
        private final long maxBytes;
        private long count;

        BoundedInputStream(InputStream input, long maxBytes) {
            super(input);
            if (maxBytes < 1 || maxBytes == Long.MAX_VALUE) {
                throw new IllegalArgumentException(
                        "Invalid byte budget");
            }
            this.maxBytes = maxBytes;
        }

        private void add(long n) throws IOException {
            count += n;
            if (count > maxBytes) {
                throw new IOException("BYTE_LIMIT");
            }
        }

        @Override
        public int read() throws IOException {
            int ch = in.read();
            if (ch >= 0) add(1);
            return ch;
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            if (len == 0) return 0;
            long remainWithProbe = maxBytes - count + 1;
            if (remainWithProbe <= 0) {
                throw new IOException("BYTE_LIMIT");
            }
            int take = (int) Math.min(
                    (long) len, remainWithProbe);
            int n = in.read(b, off, take);
            if (n > 0) add(n);
            return n;
        }

        @Override
        public long skip(long n) throws IOException {
            throw new IOException(
                    "Skipping bounded input is forbidden");
        }

        @Override
        public boolean markSupported() {
            return false;
        }

        @Override
        public synchronized void reset() throws IOException {
            throw new IOException(
                    "Resetting bounded input is forbidden");
        }
    }

    static XMLInputFactory secureFactory() {
        XMLInputFactory factory =
                XMLInputFactory.newDefaultFactory();
        factory.setProperty(
                XMLInputFactory.IS_NAMESPACE_AWARE, true);
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(
                XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setXMLResolver(
                (publicId, systemId, baseURI, namespace) -> {
                    throw new XMLStreamException(
                            "EXTERNAL_REFERENCE");
                });
        return factory;
    }

    static Summary parse(InputStream original, Limits limits)
            throws Exception {

        try (InputStream source =
                     new BoundedInputStream(
                             original, limits.maxBytes())) {

            XMLStreamReader xml =
                    secureFactory().createXMLStreamReader(source);

            try {
                int depth = 0;
                int elements = 0;
                int orders = 0;
                long textUnits = 0;
                boolean sawRoot = false;
                BigDecimal total = BigDecimal.ZERO;

                while (xml.hasNext()) {
                    int event = xml.next();

                    if (event == XMLStreamConstants.DTD
                            || event
                                == XMLStreamConstants.ENTITY_REFERENCE) {
                        throw new XMLStreamException(
                                "DTD_OR_ENTITY_FORBIDDEN");
                    }

                    if (event == XMLStreamConstants.START_ELEMENT) {
                        ++depth;

                        if (depth > limits.maxDepth()) {
                            throw new XMLStreamException(
                                    "DEPTH_LIMIT");
                        }
                        if (++elements > limits.maxElements()) {
                            throw new XMLStreamException(
                                    "ELEMENT_LIMIT");
                        }
                        if (xml.getAttributeCount()
                                > limits.maxAttributes()) {
                            throw new XMLStreamException(
                                    "ATTRIBUTE_LIMIT");
                        }

                        if (depth == 1) {
                            if (sawRoot
                                    || !"orders".equals(
                                            xml.getLocalName())) {
                                throw new XMLStreamException(
                                        "INVALID_ROOT");
                            }
                            sawRoot = true;

                        } else if (depth == 2) {
                            if (!"order".equals(
                                    xml.getLocalName())) {
                                throw new XMLStreamException(
                                        "INVALID_ORDER");
                            }
                            ++orders;

                            String amount = xml.getAttributeValue(
                                    null, "amount");

                            if (amount == null
                                    || !amount.matches(
                                        "[0-9]{1,6}(\\.[0-9]{1,2})?")) {
                                throw new XMLStreamException(
                                        "INVALID_AMOUNT");
                            }
                            total = total.add(new BigDecimal(amount));
                        }

                    } else if (event == XMLStreamConstants.END_ELEMENT) {
                        --depth;

                    } else if (event == XMLStreamConstants.CHARACTERS
                            || event == XMLStreamConstants.CDATA
                            || event == XMLStreamConstants.SPACE) {
                        textUnits += xml.getTextLength();

                        if (textUnits > limits.maxTextUnits()) {
                            throw new XMLStreamException(
                                    "TEXT_LIMIT");
                        }
                    }
                }

                if (!sawRoot || depth != 0) {
                    throw new XMLStreamException(
                            "INVALID_DOCUMENT");
                }

                return new Summary(orders, total, textUnits);
            } finally {
                xml.close();
            }
        }
    }

    static Summary parseText(String xml, Limits limits)
            throws Exception {
        byte[] bytes =
                xml.getBytes(StandardCharsets.UTF_8);
        return parse(new ByteArrayInputStream(bytes), limits);
    }

    static void expectReject(String name, String xml, Limits limits)
            throws Exception {

        boolean rejected;
        try {
            parseText(xml, limits);
            rejected = false;
        } catch (XMLStreamException
                | IOException
                | IllegalArgumentException ex) {
            rejected = true;
        }

        if (!rejected) {
            throw new AssertionError(
                    "Unexpected accept: " + name);
        }

        System.out.println(name + "=REJECTED");
    }

    public static void main(String[] args) throws Exception {
        Limits limits = new Limits(240, 3, 4, 2, 60);

        String valid = """
                <?xml version="1.0" encoding="UTF-8"?>
                <orders><order amount="12.50">Hà Nội 🌏</order><order amount="7.25">Đà Nẵng &amp; XML</order></orders>
                """;

        Summary result = parseText(valid, limits);

        System.out.println("validOrders=" + result.orders());
        System.out.println("validTotal=" + result.total());
        System.out.println("validTextUnits=" + result.textUnits());

        expectReject(
                "overBytes",
                "<orders><order amount=\"1\">"
                        + "x".repeat(500)
                        + "</order></orders>",
                limits);

        expectReject(
                "overDepth",
                "<orders><order amount=\"1\"><a><b/></a></order></orders>",
                limits);

        expectReject(
                "overElements",
                "<orders><order amount=\"1\"/><order amount=\"1\"/>"
                        + "<order amount=\"1\"/><order amount=\"1\"/></orders>",
                limits);

        expectReject(
                "overAttributes",
                "<orders><order amount=\"1\" a=\"1\" b=\"2\"/></orders>",
                limits);

        expectReject(
                "overText",
                "<orders><order amount=\"1\">"
                        + "x".repeat(80)
                        + "</order></orders>",
                limits);

        expectReject(
                "badSyntax",
                "<orders><order amount=\"1\"></orders>",
                limits);

        expectReject(
                "externalEntity",
                "<!DOCTYPE orders [<!ENTITY leak SYSTEM "
                        + "\"file:///not-for-reading\">]>"
                        + "<orders>&leak;</orders>",
                limits);

        expectReject(
                "internalEntity",
                "<!DOCTYPE orders [<!ENTITY a \"ha\">]>"
                        + "<orders>&a;</orders>",
                limits);
    }
}
```

### 7.2. Biên dịch và chạy

Lưu UTF-8, mở terminal ở thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 StaxAdversarialTests.java
java StaxAdversarialTests
```

Chương trình dùng `record` và `String.repeat()`, đều đã ổn định trước Java 17; không cần `--enable-preview`, thư viện ngoài hay công cụ legacy. Nó dùng `XMLInputFactory.newDefaultFactory()` và `XMLStreamReader` trong module `java.xml`.

**Đã thực thi chương trình trên OpenJDK 24 với các Java APIs có từ Java 17**, nhận stdout:

```text
validOrders=2
validTotal=19.75
validTextUnits=22
overBytes=REJECTED
overDepth=REJECTED
overElements=REJECTED
overAttributes=REJECTED
overText=REJECTED
badSyntax=REJECTED
externalEntity=REJECTED
internalEntity=REJECTED
```

Đây là **stdout đã kiểm chứng** của chương trình trong môi trường thử nghiệm, không phải cam kết mọi vendor StAX provider đều phân loại exceptions y hệt. Những nhãn REJECTED do `expectReject` in khi gặp `XMLStreamException`, `IOException` hoặc validation error; nếu input bị accept, method ném `AssertionError` làm test thất bại.

### 7.3. Đọc kết quả theo từng phòng tuyến

- **`validOrders=2`:** positive control có hai `<order>` hợp lệ.
- **`validTotal=19.75`:** tổng `12.50 + 7.25` bằng `BigDecimal`, không dùng `double`.
- **`validTextUnits=22`:** tổng đơn vị Java `char` mà parser báo qua text events, không phải UTF-8 bytes; emoji chiếm 2 UTF-16 units.
- **`overBytes=REJECTED`:** nguồn lớn hơn `maxBytes=240`, `BoundedInputStream` phát hiện và dừng.
- **`overDepth=REJECTED`:** XML lồng sâu hơn `maxDepth=3`; event loop từ chối.
- **`overElements=REJECTED`:** tổng start elements lớn hơn `maxElements=4`.
- **`overAttributes=REJECTED`:** element có ba attributes trong khi budget tối đa hai.
- **`overText=REJECTED`:** số text units vượt `maxTextUnits=60`.
- **`badSyntax=REJECTED`:** mismatched closing tag gây lỗi well-formedness.
- **`externalEntity=REJECTED`:** XML khai báo external entity tham chiếu đường dẫn giả bị parser/policy từ chối.
- **`internalEntity=REJECTED`:** XML khai báo internal DTD entity bị từ chối theo policy trong môi trường thử nghiệm.

**Giới hạn cần nói rõ:** hai tests DTD/entity chỉ xác minh **hai payload cụ thể** trên provider/JDK đã chạy, không chứng minh mọi DOCTYPE đều bị từ chối. Test vẫn phải theo dõi không có truy cập file/network nếu đánh giá XXE ở production. Việc dùng `ByteArrayInputStream` là để test lặp lại được, không chứng minh input ingress ở ứng dụng thật không materialize data.

### 7.4. Vì sao byte limit không thể thay XML event limit?

Một tài liệu nhỏ 200 bytes vẫn có thể khai báo DTD/entity độc hại nếu parser mở external resource. Một tài liệu 100 KB có thể chứa 50.000 elements tự đóng hoặc một element với 10.000 attributes. Vì vậy, byte limit chỉ ngăn một lớp tấn công và không thay thế depth/element/attribute limits hay policy DTD. Mặt khác, một tài liệu chứa một text element duy nhất có thể vượt text budget ngay cả khi element/depth rất thấp.

### 7.5. Code có thể được phát triển thêm như thế nào?

`BoundedInputStream` ở demo cố tình **không hỗ trợ `skip` hoặc `reset`**, để không bỏ qua bộ đếm. Production có thể cung cấp wrapper đa năng hơn nhưng vẫn phải bảo đảm mọi đường tiêu thụ dữ liệu đều tính budget. Một số XML parsers có thể read-ahead; wrapper có thể phát hiện vượt limit **trước khi event loop đụng field tương ứng**. Đây là hành vi bình thường và an toàn, không phải bug.

**Sau khi `IOException`/`XMLStreamException` xảy ra:** kết thúc parse, đóng parser và source, không cố “đọc nốt XML” hoặc gửi partial results như thành công. Nếu đã ghi sang DB, cần rollback/idempotency policy. Đừng reuse một InputStream đã tiêu thụ để retry; mở nguồn mới và đánh giá lại an toàn.

## 8. JDK-specific processing limits: ví dụ chạy độc lập thứ hai

Khi ứng dụng triển khai bằng **built-in JDK StAX provider**, có thể thêm các giới hạn parser implementation cụ thể, bổ trợ cho application counters.

### 8.1. File JdkStaxLimitsDemo.java

```java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

public final class JdkStaxLimitsDemo {

    private static XMLInputFactory factory() {
        XMLInputFactory f = XMLInputFactory.newDefaultFactory();

        f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        f.setProperty(
                XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        f.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setXMLResolver(
                (publicId, systemId, baseURI, namespace) -> {
                    throw new XMLStreamException(
                            "External reference denied");
                });

        f.setProperty("jdk.xml.maxElementDepth", "2");
        f.setProperty("jdk.xml.elementAttributeLimit", "2");
        f.setProperty("jdk.xml.entityExpansionLimit", "32");

        return f;
    }

    private static boolean rejected(
            XMLInputFactory f, String xml) throws Exception {
        XMLStreamReader r =
                f.createXMLStreamReader(new StringReader(xml));

        try {
            while (r.hasNext()) {
                r.next();
            }
            return false;
        } catch (XMLStreamException e) {
            return true;
        } finally {
            r.close();
        }
    }

    public static void main(String[] args) throws Exception {
        XMLInputFactory f = factory();

        System.out.println("depthRejected="
                + rejected(f, "<a><b><c/></b></a>"));

        System.out.println("attributesRejected="
                + rejected(f, "<a p=\"1\" q=\"2\" r=\"3\"/>"));

        System.out.println("normalAccepted="
                + !rejected(f, "<a><b/></a>"));
    }
}
```

### 8.2. Biên dịch, kết quả và giới hạn portability

```bash
javac --release 17 -encoding UTF-8 JdkStaxLimitsDemo.java
java JdkStaxLimitsDemo
```

**Đã biên dịch với `--release 17` và chạy kiểm chứng trên OpenJDK 24:**

```text
depthRejected=true
attributesRejected=true
normalAccepted=true
```

Đây là **test về JDK provider** chứ không phải một quy tắc portable cho mọi `XMLInputFactory` của bên thứ ba. Các tên property bắt đầu bằng `jdk.xml.` là implementation-specific; nếu môi trường thực không chấp nhận property bắt buộc, **không bỏ qua lỗi rồi tiếp tục parse untrusted XML**. Chọn provider và cơ chế có thể bảo đảm policy, hoặc fail closed.

**Ứng dụng production vẫn cần app limits:** `jdk.xml.maxElementDepth` không có nghĩa bạn đã giới hạn số business records; `jdk.xml.elementAttributeLimit` không kiểm tra numeric ranges hoặc schema logic; `entityExpansionLimit` không thay thế việc tắt DTD và external entities.

## 9. Kiểm thử strict DOCTYPE và provider differences

### 9.1. DOCTYPE là một phần cú pháp XML, không chỉ external entity

Các trường hợp khác nhau:

```xml
<!DOCTYPE orders>
<orders/>
```

```xml
<!DOCTYPE orders [<!ENTITY name "Alice">]>
<orders>&name;</orders>
```

```xml
<!DOCTYPE orders [<!ENTITY file SYSTEM "file:///not-for-reading">]>
<orders>&file;</orders>
```

Đây là **ba tài liệu XML riêng biệt** để kiểm thử; khi lưu file phải xử lý khai báo DOCTYPE/root theo đúng XML specification. Chúng có mức nguy cơ khác nhau, nhưng nếu policy của ứng dụng cấm toàn bộ DOCTYPE thì **cả ba** đều phải bị từ chối. Không chỉ test payload có external entity rồi kết luận “DOCTYPE policy pass”.

Với `SUPPORT_DTD=false`, có provider bỏ qua DTD mà không báo lỗi ngay. Khi có `DTD` event, event loop có thể reject, nhưng một provider có thể không phát event đó. Trong một môi trường cần **cam kết cấm tất cả DOCTYPE**, cân nhắc parser/provider có tùy chọn reject DTD được tài liệu hóa hoặc **tầng kiểm tra cú pháp XML được kiểm chứng**. Không tự khẳng định một vòng StAX event loop đã enforce strict DOCTYPE nếu test đơn giản cho thấy provider bỏ qua.

### 9.2. Provider-specific configuration phải được test khi nâng cấp

`XMLInputFactory.newDefaultFactory()` chọn built-in JDK provider; `XMLInputFactory.newFactory()` dùng cơ chế service-provider discovery và có thể chọn implementation khác. Những điều có thể thay đổi:
- Có hỗ trợ `XMLConstants.ACCESS_EXTERNAL_DTD` không.
- Có phát `DTD` event khi DTD bị tắt không.
- Giới hạn native `jdk.xml.*` có được hỗ trợ không.
- Cách chia text events, coalescing, comments và whitespace.
- Cơ chế error location/cause, exception messages.
- Hiệu năng, buffering và memory.
- Hành vi khi XML encoding declaration không khớp bytes.

**Không fallback âm thầm từ “secure parser” sang “insecure parser”** khi thay dependency. Dùng canary tests ở CI/CD và fail deployment nếu không thỏa chính sách.

### 9.3. Negative test phải có causal assertions

Từ một nhãn `overDepth=REJECTED`, ta biết input bị từ chối; nhưng có thể bị từ chối do một nguyên nhân khác trước (ví dụ sai schema). Trong production test suite, nên kiểm tra:
- Tên lỗi do chính application sinh (`DEPTH_LIMIT`, `ELEMENT_LIMIT`…).
- Thứ tự check và input hợp lệ ở những chiều không muốn test.
- Với XXE, không có outbound network/file access, không chỉ exception.
- Với byte limit, số bytes thực đã đọc không vượt quá ngân sách + 1 probe.
- Resource cleanup sau khi từ chối, không leak file descriptor/connection.
- Negative cases đi kèm positive controls và các test sát ngưỡng `limit`/`limit+1`.

Ví dụ runnable là bài học tự chứa; có thể tăng mức assert chi tiết bằng JUnit 5 (dependency hiện đại), hoặc property-based/fuzz tests trên dữ liệu có giới hạn. Không chạy fuzz vô hạn trực tiếp trên production DB.

## 10. Fuzz testing XML: mở rộng cẩn trọng

Fuzzing tìm các trường hợp input mà người lập trình chưa lường trước. Với StAX, nên bắt đầu bằng một **corpus nhỏ được duyệt**:

1. XML hợp lệ tối thiểu `<orders/>`.
2. XML với Unicode, emoji, dấu kết hợp, CDATA và `&amp;`.
3. XML với comments, processing instructions, namespace aliases.
4. Missing end tags, duplicate attributes, unescaped ampersands.
5. XML quá sâu/rộng, text cực dài, nhiều namespaces/attributes.
6. DTD chỉ khai báo, DTD internal entities, external entity file/HTTP.
7. XML với BOM/declaration và encoding sai, byte sequence bị cắt.
8. XML với application-schema violations: sai amount, thiếu id, sai root/depth.

Sau đó áp mutation có kiểm soát:
- Thêm/bớt closing tag.
- Nhân bản depth/number of elements theo budget test.
- Thêm attributes/namespace declarations, kéo dài element names.
- Chèn whitespace/CDATA/comments ở mọi vị trí hợp lệ.
- Thay đổi encoding/BOM/byte lengths.
- Thay DOI/XML entity references trong sandbox, không trỏ tới dữ liệu thật.

**Đặt upper bounds cho chính fuzzer:** giới hạn số test cases, bytes/case, thời gian chạy, heap, CPU và file/network permissions. Kẻ tấn công không phải là người duy nhất có thể gây DoS; một fuzzer không giới hạn cũng có thể làm cạn tài nguyên CI runner.

### 10.1. Differential testing

Nếu ứng dụng dùng nhiều StAX providers, cho cùng corpus chạy qua cả `XMLInputFactory.newDefaultFactory()` và provider được triển khai, rồi so sánh **policy outcomes**:
- XML hợp lệ đều được nhận và tạo dữ liệu business tương đương.
- External entities đều bị chặn.
- Limits đều được enforce hoặc provider không được phép khởi tạo.
- DOCTYPE policy khớp yêu cầu.
- Parser close/IO cleanup không bị ảnh hưởng.

**Không so sánh tuyệt đối số `CHARACTERS` events** giữa hai parser: cách chia chunks/coalescing có thể khác mà vẫn hợp lệ. So sánh semantics/sum/count và security outcomes phù hợp.

## 11. Timeout và cleanup: test thường bị bỏ sót

### 11.1. Slow input attack

Byte limit 240 MB không giúp khi client gửi 1 byte/giây và giữ 240 triệu giây. Các biện pháp bổ sung:
- Request/read timeout.
- Reverse proxy rate and body size limits.
- Network idle timeout và deadline cho toàn job.
- Connection pooling và worker concurrency quotas.
- Hủy/đóng source khi hết thời gian.

**Đừng viết một busy-loop retry quanh `XMLStreamException`**; XML malformed hoặc bị security policy chặn không tự biến thành XML hợp lệ khi gửi lại y nguyên.

### 11.2. Close đúng thứ tự

`XMLStreamReader.close()` **không mặc nhiên đóng underlying `InputStream`/`Reader`**. Với cursor:
1. Mở nguồn dưới quyền sở hữu của request/job.
2. Tạo factory đã harden.
3. Tạo reader từ nguồn.
4. Duyệt events, kiểm tra limits và validation.
5. Đóng XMLStreamReader trong `finally`.
6. Đóng nguồn qua try-with-resources.
7. Với JDBC `SQLXML`, còn `free()` và transaction/connection lifetime.

Chương trình ở mục 7 đặt `BoundedInputStream` trong try-with-resources và `xml.close()` trong finally. Nếu parse ném lỗi, nguồn vẫn được đóng. Nếu ứng dụng dùng `XMLEventReader`, contract đóng nguồn cũng cần được quản lý riêng.

### 11.3. Lỗi khi dọn tài nguyên

Một parser có thể ném `XMLStreamException` rồi underlying stream close cũng ném `IOException`. Trong code production, nên bảo toàn lỗi gốc và thêm lỗi cleanup vào suppressed exceptions khi phù hợp, thay vì biến lỗi hết quota thành “close failed” khó chẩn đoán. Try-with-resources giúp quản lý suppressed errors cho resource triển khai `AutoCloseable` như InputStream.

**Không trả về partial record set như dữ liệu thành công** khi XML bị từ chối giữa chừng. Nếu đã gọi downstream side effects, cần transaction/compensation/idempotency có chủ đích.

## 12. Cấu hình limits ở hạ tầng khác

### 12.1. HTTP

Kiểm soát body size tại reverse proxy/server và tại ứng dụng, bao gồm chunked requests. Nếu request được giải nén tự động, phải đảm bảo budget áp dụng trên **decoded XML stream**, không chỉ compressed bytes. Với request multipart, limits cho từng part và tổng request cần được định nghĩa riêng.

`Content-Length` giúp reject nhanh nhưng **không thay cho bounded read**. Một nguồn có thể không có Content-Length hoặc khai không chính xác; có thể có middleware đã decode/transform input trước khi parser xử lý.

### 12.2. File và ZIP

`Files.size(path)` chỉ đo kích thước file tại một thời điểm, không phản ánh data qua symlink/TOCTOU/race hoặc giải nén. Với file upload:
- Validate storage path, tránh path traversal.
- Không follow arbitrary symlink nếu policy không cho.
- Giới hạn bytes **khi đọc**, không chỉ pre-check size.
- Với `ZipInputStream`/`GZIPInputStream`, giới hạn **dữ liệu đã giải nén**.
- Đặt giới hạn số entries/nesting và compression ratio trước khi xử lý từng XML file.
- Không mở URL trong XML do path/namespace giả chỉ định.

### 12.3. Database/JDBC

Khi đọc XML từ SQLXML:
- Kiểm tra `ResultSet.getSQLXML` trả SQL NULL hay không.
- Gọi **một** getter như `getBinaryStream` hoặc `getCharacterStream` trên mỗi SQLXML instance.
- Với `getBinaryStream`, có thể đặt byte counter; chú ý XML encoding và driver buffering.
- Với `getCharacterStream`, cần **character counter**/byte budget ở tầng DB/driver vì ký tự đã được decode; không thể suy số bytes network từ Reader.
- Giữ ResultSet, SQLXML, transaction hợp lệ đến lúc parse xong; đóng stream, gọi `SQLXML.free()` và đóng statement/connection.
- Không coi JDBC SQLXML + StAX luôn streaming qua network; driver có thể buffer.
- Đặt DB query timeout, connection pool limits và overall processing deadline.

Các ví dụ mục 7/8 **không yêu cầu DB**; các điều kiện JDBC trên cần kiểm chứng riêng với driver thực tế.

## 13. Không để “bảo mật parser” bị phá ở bước khác

### 13.1. DOM/XPath

Nếu hệ thống cần XPath:
- Parse bằng `DocumentBuilderFactory` được harden, không bật external entities/DTD.
- Không dùng `XPath.evaluate(InputSource, ...)` của provider mà không kiểm soát parser nội bộ.
- Xác minh XSD/namespace handling nếu được dùng.
- Với untrusted XPath expressions, bảo vệ khỏi XPath injection và expensive queries.

### 13.2. XSLT

Một XML document không có DTD vẫn có thể tham gia transformer dùng XSLT với `xsl:import`/`xsl:include`/`document()`. Cần cấu hình `TransformerFactory` riêng:
- `XMLConstants.ACCESS_EXTERNAL_DTD=""`.
- `XMLConstants.ACCESS_EXTERNAL_STYLESHEET=""`.
- `FEATURE_SECURE_PROCESSING` nơi factory hỗ trợ.
- Chỉ cho stylesheet do ứng dụng tin cậy hoặc đã được allowlist.
- Không nhận URL stylesheet tự do từ input nếu ứng dụng có network/file access.

### 13.3. XSD validation

`SchemaFactory`/`Validator` có thể tải external `schemaLocation`, `xs:include` hoặc `xs:import`. Dùng `ACCESS_EXTERNAL_SCHEMA=""`/`ACCESS_EXTERNAL_DTD=""`, trusted schema sources và giới hạn tài nguyên. StAX parser hardening **không tự động áp dụng** lên XML Schema validation pipeline khác.

### 13.4. JAXB/deserialization

Nếu có Jakarta XML Binding hoặc framework XML data binding (dependency tách biệt khỏi JDK hiện đại), ưu tiên đưa một `XMLStreamReader`/`XMLEventReader` đã harden vào unmarshaller API phù hợp, thay vì đưa raw InputStream cho framework tự tạo parser mà security settings không được kiểm soát. Kiểm tra framework/provider thực tế và giới hạn số records/object graph.

## 14. Logging và observability cho XML bị từ chối

Một error handler tốt cần hữu ích nhưng không rò dữ liệu. Nên log:
- **Error category** đã chuẩn hóa: `BYTE_LIMIT`, `DEPTH_LIMIT`, `ATTRIBUTE_LIMIT`, `MALFORMED_XML`, `DTD_BLOCKED`…
- Operation ID / correlation ID theo policy.
- Kích thước input đã đọc (capped), số elements/depth/text units tới lúc lỗi.
- Parser/JDK/provider version khi cần hỗ trợ điều tra.
- Line/column từ `XMLStreamException.getLocation()` nếu có, chỉ như **best effort**.
- Thời gian xử lý, tỉ lệ rejected/accepted, số timed-out requests.

**Không log:**
- Toàn bộ raw XML chứa PII, credentials hoặc data nhạy cảm.
- Giá trị entity expansion, file contents hoặc URL có secrets.
- File system path/network access từ payload nếu logs có thể tới môi trường không tin cậy.
- XML stack trace/exception message chưa scrub nếu driver/parser có thể phản ánh dữ liệu input.
- Một metrics label độc nhất cho mỗi XML filename/ID, gây cardinality bùng nổ.

Phân biệt lỗi người dùng (XML không hợp lệ, vượt quota) với lỗi cấu hình server (parser không hỗ trợ security property), lỗi hạ tầng (I/O timeout) và lỗi lập trình. **Không fallback sang parser yếu hơn** nếu configuration fail.

## 15. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Chỉ check `Content-Length` | Chunked request hoặc header sai có thể bypass. | Bounded read thực sự và proxy/app limits. |
| Dùng `available()` làm tổng byte count | Available không phải kích cỡ stream. | Counter trong `read()`/`read(byte[])`. |
| Cắt InputStream bằng `limit` nhưng không báo lỗi | Silent truncation, partial semantics. | Reject khi có byte thứ max+1. |
| Chỉ giới hạn bytes | XML nhỏ có XXE hoặc cấu trúc sâu/nhiều nodes. | Kết hợp parser hardening + event counters. |
| Chỉ đặt `SUPPORT_DTD=false` | External resource policy chưa được xác thực đầy đủ. | Tắt external entities, ACCESS_EXTERNAL_DTD, deny resolver và tests. |
| Tin StAX luôn reject mọi DOCTYPE | Có provider bỏ qua DTD mà không throw. | Test strict DOCTYPE riêng; dùng cơ chế reject đúng provider. |
| Chỉ bắt exception từ malicious XML để kết luận không XXE | Parser có thể đã truy cập resource trước khi throw. | Instrument file/network canaries và deny resolver. |
| Bật lại DTD khi XML test bị reject | Mở lại nguy cơ entity expansion/XXE. | Sửa nguồn và policy thay vì tắt bảo mật. |
| `getElementText()` trên field vô hạn | Materialize String cực lớn. | CHARACTERS chunks + per-field budget. |
| Lưu `List<XMLEvent>` toàn bộ tài liệu | Heap tăng dù dùng parser streaming. | Bounded state/consumer, không giữ toàn bộ events. |
| `IS_COALESCING=true` rồi cho rằng text được chia nhỏ | Parser có thể coalesce thành chunks lớn. | Limit/measure text và kiểm soát buffering. |
| Đếm `String.length()` như số bytes UTF-8 | Sai Unicode semantics. | Phân biệt byte/char/codepoints. |
| Không check QName/namespace | Parser nhận tên tương tự ở namespace khác. | Validate namespace URI + local name. |
| Retry cùng XML malformed/XXE | Không sửa nguyên nhân, thêm tải. | Fail fast và báo loại lỗi hợp lý. |
| Tiếp tục ghi DB sau parse đã fail | Partial/invalid data có thể được commit. | Transaction/rollback và idempotency. |
| Đóng parser nhưng không đóng InputStream | Leaks file/network/DB resources. | Close cả parser và source. |
| Chỉ test một JVM/provider | Thay provider có thể đổi security behavior. | Regression tests theo JDK/driver/provider. |
| Dùng mặc định `jdk.xml.*` như bảo đảm | Defaults/implementation có thể thay đổi. | Đặt limits rõ theo provider, test thật. |
| Mẫu XML test trỏ tới file thật có secrets | Rủi ro không cần thiết. | Chỉ dùng canary sandbox/tên file giả không có dữ liệu. |

## 16. Checklist triển khai trước production

1. Xác định **trust boundary** và quyền truy cập XML source; không mở path/URL tùy ý.
2. Đặt body limits ở proxy, app và giải nén; kiểm tra **actual bytes** khi đọc.
3. Dùng `XMLInputFactory.newDefaultFactory()` hoặc provider đã audit; cấu hình trước khi tạo parser.
4. Tắt DTD và external entities; đặt `ACCESS_EXTERNAL_DTD=""`, resolver deny; fail closed nếu không được hỗ trợ.
5. Nếu cấm mọi DOCTYPE, test riêng empty/simple DOCTYPE và enforce theo provider, đừng chỉ tin `SUPPORT_DTD=false`.
6. Đặt JDK/provider-specific limits dương phù hợp (depth, attributes, names, entities) khi triển khai có hỗ trợ.
7. Trong event loop, giới hạn depth, elements, records, attributes và text units; validate namespace/root/domain schema.
8. Dùng `getElementText()` chỉ cho text-only bounded fields; tránh gom XML/records/events không giới hạn.
9. Giữ nguồn và parser trong cùng ownership scope; close parser và input trên mọi đường lỗi.
10. Đặt deadline/read timeout, concurrency cap, connection pool quota và bounded queues.
11. Có positive controls cho XML hợp lệ/Unicode và negative tests cho bytes/depth/attrs/text/DTD/malformed.
12. Với XXE, kiểm tra **không có file/network side effects**, không chỉ exception.
13. Kiểm thử cả `limit` và `limit+1`; đọc rõ error category, không bỏ qua lỗi.
14. Kiểm thử parser khi thay JDK/provider/JDBC driver/schema validator/transformer.
15. Quan sát error categories/latency/CPU/memory/GC, không log payload XML nhạy cảm.
16. Nếu có database writes, rollback/compensation và retry idempotent theo business policy.
17. Đặt các giới hạn phù hợp loại XML hợp lệ của ứng dụng; không dùng nguyên ngân sách cực nhỏ trong demo.
18. Sử dụng Java 17+ cùng API `java.xml` hiện hành, không hướng dẫn cấu hình parser legacy.

## 17. Câu hỏi ôn tập

**Câu 1. Vì sao streaming StAX chưa đủ chống XML DoS?**

Vì XML vẫn có thể quá lớn, quá sâu, rất nhiều attributes/nodes/text; parser, nguồn, downstream và application state đều có thể tiêu thụ tài nguyên. Cần giới hạn nhiều tầng.

**Câu 2. `Content-Length` có đủ để bảo vệ max bytes không?**

Không. Header có thể vắng mặt/sai, HTTP chunked hoặc source được giải nén. Phải enforce byte budget ngay trên stream thực được parse.

**Câu 3. `XMLInputFactory.SUPPORT_DTD=false` có chứng minh mọi DOCTYPE bị reject không?**

Không. Có provider bỏ qua DTD mà vẫn tiếp tục. Cần test/enforce strict DOCTYPE policy riêng nếu yêu cầu cấm mọi khai báo.

**Câu 4. Giới hạn `jdk.xml.maxElementDepth` có portable trên mọi StAX implementation không?**

Không. Đây là JDK-specific property; một provider bên thứ ba có thể không hỗ trợ. Phải kiểm tra và fail closed khi cần.

**Câu 5. Vì sao cần giới hạn attributes riêng?**

Một element đơn lẻ có thể có rất nhiều attributes dù số element/depth nhỏ. Parser và domain logic vẫn tiêu thụ CPU/memory.

**Câu 6. Vì sao `getElementText()` nguy hiểm với field không giới hạn?**

Vì method tích lũy nội dung text thành `String`, có thể gây pressure/OutOfMemoryError. Xử lý CHARACTERS events theo chunks và giới hạn tổng/per-field.

**Câu 7. `getTextLength()` đo bytes UTF-8 hay Java char?**

Java `char` units của text event, không phải bytes UTF-8 hoặc số codepoints; emoji ngoài BMP thường là hai UTF-16 units.

**Câu 8. Trong negative tests, chỉ nhìn exception có đủ chứng minh XXE không truy cập network không?**

Không. Có thể đã có side effect trước khi exception; cần instrument resolver/file/network sandbox và deny external resource access.

**Câu 9. Vì sao cần positive XML test?**

Để chắc parser nhận được XML hợp lệ; nếu mọi input đều thất bại do config lỗi, negative tests sẽ pass giả.

**Câu 10. Bộ đếm byte phải xử lý gì ngoài `read()` đơn byte?**

Cả `read(byte[],off,len)`, và không cho `skip/reset` bypass chính sách; dừng khi phát hiện vượt limit chứ không truncate âm thầm.

**Câu 11. Có thể coi SQLXML trong DB là sanitized XML không?**

Không. Giá trị có thể bắt nguồn từ nguồn không tin cậy và driver không chịu trách nhiệm XML parser security phía ứng dụng.

**Câu 12. Nếu XML vượt limit giữa quá trình ghi DB thì sao?**

Không trả về kết quả “thành công một phần” trừ khi contract cho phép. Cần rollback/compensation và idempotency policy.

**Câu 13. Tại sao giới hạn bytes cần tính cả sau giải nén?**

Một payload nén nhỏ có thể phình thành XML rất lớn khi parse. Chỉ giới hạn kích thước compressed bytes không ngăn decompression bombs.

**Câu 14. Kiểm thử chỉ trên JDK 24 có bảo đảm mọi Java 17 runtime behavior giống nhau không?**

Không. Ngôn ngữ/API Java 17 cho phép code biên dịch, nhưng JAXP provider/runtime version ảnh hưởng lỗi và security behavior. Chạy compatibility tests trên JDK mục tiêu thật.

## 18. Tham khảo chính thức và khuyến nghị bảo mật

- [Java SE 17 — XMLInputFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): cấu hình properties và tạo cursor/event reader.
- [Java SE 17 — XMLStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): `next`, event types, `getAttributeCount`, `getTextLength` và vòng đời parser.
- [Java SE 17 — XMLEventReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLEventReader.html): iterator model và đóng reader.
- [Java SE 17 — XMLStreamConstants](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLStreamConstants.html): `DTD`, `ENTITY_REFERENCE`, `START_ELEMENT`, `CHARACTERS`.
- [Java SE 17 — XMLConstants](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/XMLConstants.html): external-access property.
- [Java SE 17 — FilterInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FilterInputStream.html): cách wrap InputStream/override methods.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): xử lý số thập phân chính xác.
- [Oracle — JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): JDK-specific processing limits, `jdk.xml.maxElementDepth`, `jdk.xml.elementAttributeLimit`, entity limits, factory scoping và StAX.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): chống XXE trên StAX/DOM/SAX/Transformer, cảnh báo `SUPPORT_DTD=false` có thể không reject toàn bộ DOCTYPE.
- [OWASP — Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html): các chiến lược hạn chế tài nguyên và DoS.
- [Java SE 25 — XMLStreamReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): đối chiếu API đang được hỗ trợ trên JDK hiện đại.
