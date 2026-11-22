# SSRF, injection, parser và deserialization test

Kiểm thử bảo mật API cần xác minh cách server xử lý dữ liệu không đáng tin cậy ở nhiều ranh giới: URL mà server sẽ truy cập, câu truy vấn được tạo từ input, nội dung parser phải đọc và object được dựng từ payload. Những lỗi như Server-Side Request Forgery (SSRF), injection, parser abuse và unsafe deserialization thường không xuất hiện trong happy-path test vì request vẫn có thể hợp lệ về mặt cú pháp nhưng làm server truy cập sai tài nguyên, thực thi sai ngữ cảnh hoặc tiêu thụ tài nguyên quá mức.

Mục tiêu của nhóm kiểm thử này là chứng minh dữ liệu từ client không thể điều khiển ngoài ý muốn hành vi của server. Test cần đi qua endpoint và cấu hình thực tế, dùng dependency giả lập có kiểm soát, xác minh cả response lẫn side effect, và tạo regression test cho từng lỗi đã phát hiện. Không chạy payload thử nghiệm lên hệ thống bên ngoài hoặc tài nguyên production không thuộc phạm vi được phép.

## 1. Phạm vi và cách tổ chức kiểm thử

Chia nhóm test theo điểm mà dữ liệu không đáng tin cậy đi vào:

| Nhóm | Dữ liệu đầu vào | Rủi ro cần phát hiện |
|---|---|---|
| SSRF | URL, hostname, redirect, webhook destination, image/import URL | Server kết nối tới loopback, private network, metadata service hoặc destination ngoài allowlist |
| SQL/NoSQL injection | Query parameter, path, JSON field, filter, sort, search expression | Input thay đổi cấu trúc truy vấn hoặc predicate ngoài ý muốn |
| OS/LDAP/template injection | Tên file, command option, search filter, template variable | Input bị diễn giải như cú pháp thực thi hoặc biểu thức |
| Parser abuse | JSON, XML, YAML, multipart, archive, CSV, image/document | Parser truy cập tài nguyên ngoài ý muốn, vượt giới hạn hoặc xử lý cấu trúc mơ hồ |
| Unsafe deserialization | Object payload, polymorphic type metadata, native serialized data | Payload điều khiển kiểu object được tạo hoặc kích hoạt hành vi không an toàn |
| Resource exhaustion | Payload lớn, nesting sâu, nhiều phần tử, archive expansion, regex phức tạp | CPU, memory, thread, disk hoặc connection bị tiêu hao quá mức |

Mỗi test case nên mô tả: endpoint, actor/tenant, loại input, precondition, expected status, expected side effect, metric/log cần quan sát và bằng chứng regression. Với API nhạy cảm, chạy test qua authentication filter, gateway policy và service layer theo đúng đường request production.

## 2. Nguyên tắc xây dựng security test an toàn

- Dùng staging hoặc môi trường test cô lập, dữ liệu giả lập và credential thử nghiệm.
- Chỉ kiểm tra host, network, database và provider nằm trong phạm vi đã được cho phép.
- Với SSRF, dùng mock server hoặc sink nội bộ do nhóm kiểm thử kiểm soát; không dò metadata endpoint hoặc mạng production.
- Với injection, dùng payload vô hại để chứng minh input không thay đổi cấu trúc truy vấn; không xóa dữ liệu hoặc chạy lệnh hệ thống.
- Với parser/deserialization, dùng fixture nhỏ và có kiểm soát; không dùng payload gây treo, tạo file hoặc thực thi lệnh.
- Đặt timeout, body size, concurrency và ngưỡng dừng cho test fuzzing.
- Xác minh cả kết quả âm tính lẫn dương tính: input hợp lệ vẫn hoạt động, input bị cấm bị từ chối.
- Không ghi token, secret, raw payload nhạy cảm hoặc dữ liệu cá nhân vào artifact test.

Một test chỉ nhận được `400` chưa đủ chứng minh an toàn. Cần kiểm tra server không gọi dependency, không truy vấn ngoài tenant, không thay đổi database, không phát event và không tạo file ngoài vùng lưu trữ cho phép.

## 3. SSRF test: xác minh server chỉ truy cập destination được phép

SSRF xảy ra khi server thực hiện request tới URL do caller kiểm soát mà không kiểm tra destination đầy đủ. Các chức năng dễ gặp gồm webhook registration, URL preview, import từ URL, fetch avatar, document conversion, callback tester và image proxy.

### Lập test matrix cho URL

Test URL theo nhiều lớp:

| Nhóm URL | Ví dụ trong môi trường test | Kết quả mong đợi |
|---|---|---|
| HTTPS public allowlist | `https://receiver.test.example/health` | Chỉ cho phép nếu domain đã được đăng ký/allowlist và TLS hợp lệ |
| HTTP không mã hóa | `http://receiver.test.example/` | Từ chối nếu policy yêu cầu HTTPS |
| Loopback | `http://127.0.0.1/`, `http://[::1]/` | Từ chối trước khi kết nối |
| Private IPv4 | Địa chỉ trong `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | Từ chối nếu destination không thuộc mạng được phê duyệt |
| Link-local | Địa chỉ `169.254.0.0/16` hoặc IPv6 link-local | Từ chối |
| Hostname nội bộ | `db.internal.test`, `metadata.internal.test` | Từ chối nếu không phải destination được phê duyệt |
| DNS trả nhiều địa chỉ | Một hostname có cả public và private address | Từ chối hoặc chỉ kết nối địa chỉ public đã được kiểm tra theo policy |
| DNS thay đổi sau validation | Hostname resolve public rồi chuyển sang private trong lần resolve tiếp theo | Kết nối vẫn bị chặn; kiểm tra phải gắn với địa chỉ thực tế được dùng |
| Redirect | URL allowlist trả `302` tới destination không cho phép | Không follow hoặc revalidate toàn bộ redirect chain và từ chối |
| Port không được phép | Port quản trị hoặc port không nằm trong allowlist | Từ chối |
| URL có user info | `https://user:pass@receiver.test.example/` | Từ chối nếu user info không thuộc contract |
| Scheme khác HTTP(S) | `file:`, `ftp:`, `gopher:` hoặc custom scheme | Từ chối |

Các dải địa chỉ và quy tắc cụ thể phải được kiểm tra bằng thư viện IP/network chuẩn, bao gồm IPv4-mapped IPv6, địa chỉ biểu diễn không chuẩn và vùng địa chỉ đặc biệt. Không chỉ so sánh chuỗi hostname hoặc dùng regex đơn giản.

### Kiểm tra DNS rebinding và redirect

Một lỗi thường gặp là ứng dụng resolve hostname để kiểm tra IP, sau đó HTTP client resolve hostname lần nữa khi kết nối. Kết quả thứ hai có thể khác kết quả đã kiểm tra. Test cần xác minh destination được dùng để kết nối chính là destination đã qua policy, hoặc outbound proxy/egress firewall thực thi cùng policy.

Với redirect, kiểm tra từng hop:

- Scheme vẫn nằm trong allowlist.
- Hostname và IP đích được resolve và kiểm tra lại.
- Port vẫn được phép.
- Không chuyển Authorization, cookie, webhook signing secret hoặc header nội bộ sang origin khác.
- Số lần redirect và tổng thời gian bị giới hạn.

Tắt redirect tự động thường là lựa chọn đơn giản nhất cho webhook hoặc URL fetcher. Nếu nghiệp vụ cần redirect, test riêng từng hop và không giả định redirect từ domain tin cậy luôn an toàn.

### Ví dụ kiểm thử SSRF bằng mock destination

Giả sử ứng dụng có `UrlFetchService` chỉ được gọi tới host `receiver.test.example`. Test dùng mock HTTP server do test khởi tạo và một resolver giả lập:

```java
@SpringBootTest
class UrlFetchSecurityIT {
    @Autowired
    MockMvc mockMvc;

    @MockBean
    DestinationPolicy destinationPolicy;

    @MockBean
    UrlFetchClient urlFetchClient;

    @Test
    void rejectsLoopbackBeforeOpeningConnection() throws Exception {
        given(destinationPolicy.validate("http://127.0.0.1/health"))
                .willThrow(new ForbiddenDestinationException());

        mockMvc.perform(post("/api/imports/from-url")
                        .with(jwt().jwt(token -> token
                                .subject("test-user")
                                .claim("tenant_id", "tenant-test")))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"url":"http://127.0.0.1/health"}
                                """))
                .andExpect(status().isUnprocessableEntity());

        verifyNoInteractions(urlFetchClient);
    }
}
```

Đây là ví dụ khung; thay status, route và dependency bằng implementation của ứng dụng. Test unit/mock xác minh thứ tự policy, nhưng cần thêm integration test với mock DNS/HTTP server hoặc egress proxy để chứng minh kết nối thực tế không thể đi tới IP bị cấm. Không dùng request tới địa chỉ metadata thật làm test.

## 4. SQL injection test

SQL injection xuất hiện khi dữ liệu đầu vào được nối trực tiếp vào câu SQL hoặc làm thay đổi cấu trúc query. Kiểm thử nên tập trung vào những input được dùng trong filter, search, sort, report, export và dynamic query.

Các điểm cần thử:

- Search text, tên, email và mã tham chiếu.
- `sort`, `orderBy`, field selection và filter expression.
- ID trong path/query/body.
- Danh sách ID trong bulk request.
- Bộ lọc báo cáo, ngày tháng, numeric range và nested filter.
- Query được xây dựng bởi native SQL, stored procedure hoặc query builder.

Test với chuỗi có dấu nháy, dấu phân cách và ký tự cú pháp SQL vô hại; xác minh nó được coi là dữ liệu, không làm thay đổi số dòng hoặc predicate ngoài ý muốn. Không chỉ kiểm tra response `500`: lỗi SQL có thể bị che nhưng query vẫn bị thay đổi.

Ví dụ kiểm thử hành vi:

```java
@Test
void searchTreatsSqlSyntaxAsLiteralText() throws Exception {
    mockMvc.perform(get("/api/customers")
                    .param("q", "O'Reilly"))
            .andExpect(status().isOk());

    // Verify through repository/test database that only literal matches
    // are returned and the query structure is unchanged.
}
```

Đối với `ORDER BY`, tên cột và hướng sort thường không thể bind như một value parameter. Hãy dùng allowlist field và enum hướng sort, rồi test mọi giá trị ngoài allowlist bị từ chối. Không nối trực tiếp chuỗi `sort` do client gửi vào SQL.

### NoSQL injection

Với MongoDB hoặc document database, test input có kiểu khác dự kiến: object/array thay cho string, toán tử filter, nested key và field ngoài schema. Ví dụ nếu API mong `email` là string, request gửi object thay cho string phải bị validation từ chối thay vì được chuyển thành query operator.

Không chuyển nguyên JSON filter do client gửi vào database query. Map các field/filter được phép sang query object phía server. Kiểm tra cả `$where`, expression, regex và aggregation pipeline nếu hệ thống có hỗ trợ những khả năng đó.

## 5. OS command, LDAP và template injection test

### OS command injection

Nếu API gọi chương trình bên ngoài, test tên file, archive entry, search term và option có ký tự đặc biệt. Ưu tiên API/library trực tiếp thay vì shell. Nếu phải gọi process, truyền executable và từng argument riêng, không nối chuỗi command để shell diễn giải.

Test cần xác minh:

- Input không thể tạo thêm argument ngoài danh sách cho phép.
- Không thể thay executable hoặc working directory.
- Tên file được xử lý như dữ liệu, không phải option của chương trình.
- Timeout, output size và process count được giới hạn.
- Process chạy bằng user ít quyền, thư mục tạm riêng và không có secret không cần thiết.
- Request bị từ chối không khởi chạy process.

Không dùng payload thực thi lệnh trong production. Trong test, dùng executable giả lập chỉ ghi nhận argument vào test log hoặc trả marker vô hại.

### LDAP injection

Với API tìm người dùng hoặc group qua LDAP, kiểm tra các ký tự đặc biệt trong filter và DN được escape theo đúng ngữ cảnh. Escape filter value và DN value là hai thao tác khác nhau; không dùng một hàm escape chung cho cả hai. Test xác minh input không thể mở rộng kết quả tìm kiếm hoặc thay đổi base DN.

### Template injection

Nếu API render template do người dùng cung cấp hoặc cho phép placeholder, kiểm tra input được coi là dữ liệu thay vì biểu thức thực thi. Không cho template truy cập filesystem, environment, network hoặc object nội bộ nếu không có sandbox được thiết kế rõ. Giới hạn thời gian, memory và số vòng lặp. Dùng template engine với auto-escaping phù hợp và tránh bật expression language không cần thiết.

## 6. JSON parser test

JSON là định dạng phổ biến nhưng parser vẫn có thể bị khai thác qua kích thước, độ sâu, duplicate key hoặc kiểu dữ liệu không mong đợi.

Các trường hợp cần kiểm tra:

- Body rỗng, JSON sai cú pháp và encoding không hợp lệ.
- Body lớn hơn giới hạn.
- Object/array lồng nhau quá sâu.
- Array có quá nhiều phần tử.
- String hoặc numeric literal vượt giới hạn.
- Duplicate property name.
- Unknown property hoặc property không được phép cập nhật.
- Kiểu dữ liệu không đúng schema, ví dụ object thay cho string hoặc số âm ngoài miền hợp lệ.
- Trường polymorphic/type metadata nếu ứng dụng hỗ trợ.
- JSON parser behavior khi có `null`, thiếu field, field lặp hoặc field có tên gần giống.

Contract cần quy định duplicate key được từ chối hay cách xử lý. Tránh để gateway, parser và business layer diễn giải cùng một payload theo cách khác nhau. Nếu một lớp lấy giá trị đầu tiên còn lớp khác lấy giá trị cuối cùng, attacker có thể tạo request mơ hồ.

Giới hạn body size ở gateway/server trước khi parse, và giới hạn nesting depth, string length, number length, collection size trong parser/schema. Validation ở DTO không thay thế giới hạn tài nguyên của parser vì parser phải đọc cấu trúc trước khi Bean Validation chạy.

## 7. XML parser và XXE test

XML External Entity (XXE) xảy ra khi parser cho phép document khai báo external entity và truy cập URI/file ngoài ý muốn. Nếu API không cần DTD hoặc external entity, tắt chúng.

Test trong môi trường cô lập với fixture XML có DOCTYPE/entity tham chiếu tới một file marker giả hoặc mock HTTP sink. Kết quả mong đợi:

- Parser từ chối DOCTYPE hoặc không resolve external entity theo policy.
- Không có file được đọc.
- Không có outbound request tới mock sink.
- Không trả nội dung file hoặc lỗi parser chi tiết cho caller.
- Payload không làm parser tiêu tốn CPU/memory vượt giới hạn.

Ví dụ cấu hình JAXP cần được kiểm tra theo parser thực tế:

```java
DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
factory.setXIncludeAware(false);
factory.setExpandEntityReferences(false);
```

Các feature có thể khác nhau giữa parser implementation. Nếu cấu hình feature không được hỗ trợ, không âm thầm bỏ qua rồi tiếp tục parse không an toàn. Fail startup hoặc chọn parser/configuration đã được xác minh. Test phải chạy với đúng thư viện và phiên bản trong production.

## 8. YAML parser test

YAML có thể hỗ trợ tag và object construction tùy thư viện. Không dùng constructor không an toàn để tạo arbitrary object từ dữ liệu bên ngoài.

Với SnakeYAML, cân nhắc `SafeConstructor` hoặc API safe loading của phiên bản đang dùng. Test:

- Tag/type không nằm trong schema bị từ chối.
- Alias/anchor quá nhiều hoặc lồng nhau không gây resource exhaustion.
- Payload quá sâu hoặc quá lớn bị giới hạn.
- Unknown field và kiểu dữ liệu sai bị từ chối.
- Không tạo class tùy ý từ tag do client cung cấp.
- Không gọi constructor có side effect khi parse.

API nhận cấu hình YAML nên chuyển dữ liệu sang DTO/schema allowlist rõ ràng. Không deserialize trực tiếp thành class tùy ý dựa trên tag trong input.

## 9. Unsafe deserialization test

Deserialization là quá trình biến bytes hoặc structured payload thành object. Rủi ro tăng khi client có thể điều khiển class/type được khởi tạo, đặc biệt với native Java serialization hoặc polymorphic deserialization quá rộng.

Ưu tiên DTO/schema rõ ràng cho JSON/XML và không nhận native Java serialized object từ client. Nếu phải hỗ trợ định dạng serialized đặc biệt, giới hạn class/type, kích thước, độ sâu, số reference và thời gian xử lý.

### Java native serialization

Java `ObjectInputStream` có thể được giới hạn bằng `ObjectInputFilter`. Ví dụ minh họa allowlist một số kiểu cần thiết:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=8;maxrefs=1000;maxbytes=1048576;"
        + "com.example.api.dto.*;java.base/java.lang.String;!*");

try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(filter);
    Object value = input.readObject();
    // Validate exact expected DTO type and fields after reading.
}
```

Ví dụ filter phải được điều chỉnh và kiểm tra theo graph object thật; allowlist package quá rộng vẫn có thể chứa class không mong muốn. `ObjectInputFilter` giảm bề mặt rủi ro nhưng không biến native Java serialization thành lựa chọn tốt cho public API. Tốt nhất là không nhận Java serialization từ client.

### Jackson polymorphic deserialization

Với Jackson, tránh bật default typing rộng cho dữ liệu không tin cậy. Nếu polymorphism là yêu cầu nghiệp vụ, dùng subtype allowlist rõ ràng, ví dụ `@JsonTypeInfo` kết hợp `@JsonSubTypes` trên hierarchy hẹp, hoặc custom `PolymorphicTypeValidator` giới hạn đúng package/type đã kiểm tra.

Test cần gửi type ID không được đăng ký, type ID ngoài package cho phép, nested polymorphic value và type metadata ở field không hỗ trợ. Kết quả phải là lỗi validation/deserialization được xử lý an toàn, không khởi tạo class ngoài allowlist và không lộ stack trace.

Không chấp nhận type/class name tùy ý từ client rồi gọi `Class.forName` hoặc dùng làm target type. Kiểu object cần được quyết định từ schema/contract phía server.

## 10. Parser differential và request smuggling ở ranh giới API

Gateway, reverse proxy và backend có thể diễn giải request khác nhau. Các trường hợp cần test trong môi trường được phép gồm:

- `Content-Length` và `Transfer-Encoding` mâu thuẫn.
- Header trùng lặp hoặc khác chữ hoa/thường.
- Duplicate JSON key.
- Path encoding, duplicate slash và dot segment.
- Khác biệt charset hoặc content type.
- Multipart boundary sai hoặc lặp.
- Compression/decompression khác nhau giữa proxy và application.

Mục tiêu là bảo đảm các lớp thống nhất cách parse và không có request thứ hai bị backend hiểu khác với gateway. Với HTTP request smuggling, dùng test harness và scanner được phê duyệt trong staging; không tự gửi payload làm lệch framing tới hệ thống production. Chuẩn hóa request ở edge, từ chối framing mơ hồ và cập nhật proxy/server theo khuyến nghị nhà cung cấp.

## 11. Resource limit cho parser và payload

Parser có thể bị lạm dụng mà không cần injection. Một payload hợp lệ về cú pháp nhưng quá lớn hoặc quá sâu vẫn có thể làm cạn tài nguyên.

Đặt giới hạn phù hợp cho:

- Tổng request body bytes và decompressed bytes.
- JSON/XML/YAML nesting depth.
- Số object/array element và số field.
- Độ dài string, numeric token và property name.
- Multipart part count, file size và tổng request size.
- Archive entry count, nested archive depth và tổng expanded size.
- Parser timeout, CPU budget và memory/worker concurrency.
- Regex length/complexity nếu API cho phép search pattern.

Đặc biệt với archive, kiểm tra tổng kích thước sau giải nén và tỷ lệ nén. Không chỉ giới hạn kích thước file nén. Từ chối path traversal trong archive entry và chỉ ghi file trong thư mục staging riêng.

## 12. Kết hợp parser test với authentication và authorization

Security test không nên chỉ chạy bằng anonymous request. Hãy thử nhiều trạng thái principal:

- Anonymous: không được parse hoặc xử lý payload nhạy cảm nếu endpoint yêu cầu authentication.
- Authenticated nhưng thiếu function permission: bị từ chối trước khi gọi parser/expensive operation khi có thể.
- Có permission nhưng khác tenant: không thể dùng payload để tham chiếu dữ liệu tenant khác.
- Có quyền trên object: input vẫn phải qua validation và parser hardening.
- Service account: chỉ được gửi schema/event/type thuộc scope của service.

Đối với file upload/import, xác minh object authorization trước khi gắn file vào object đích, và xác minh lại khi tải xuống. Không để một parser job được tạo bởi tenant A đọc file hoặc ghi kết quả vào namespace của tenant B.

## 13. Kiểm thử injection qua repository và service thật

Unit test cho validator hữu ích nhưng chưa chứng minh query thực tế an toàn. Hãy chạy integration test với database test tương đương và kiểm tra:

- Repository dùng parameterized query hoặc query builder an toàn.
- Sort/filter chỉ nhận field allowlist.
- Input có cú pháp SQL/NoSQL không làm thay đổi số row ngoài dự kiến.
- Tenant predicate luôn được áp dụng.
- Không có query hoặc command ngoài ý muốn.
- Request bị từ chối không ghi database, phát event hoặc gọi dependency.

Có thể dùng datasource proxy hoặc query logging trong test để quan sát query shape, nhưng phải redact giá trị nhạy cảm. Không đưa raw user input vào log production chỉ để phát hiện injection.

Với OS process, inject một fake executable vào PATH riêng của test hoặc mock process launcher. Assert đúng executable và argument list, không chỉ assert response. Với LDAP/template engine, dùng test server/sandbox cô lập để quan sát filter hoặc capability thực tế.

## 14. Fuzzing và property-based testing

Fuzzing giúp tìm input bất thường mà test case viết tay có thể bỏ sót. Nên tập trung vào parser và validation boundary với giới hạn rõ.

Các hướng phù hợp:

- Property-based test sinh chuỗi Unicode, ký tự điều khiển, dấu phân cách và chuỗi rỗng.
- Fuzz JSON/XML/YAML parser với giới hạn kích thước và timeout.
- Sinh path/query encoding khác nhau để kiểm tra gateway/backend normalization.
- Sinh nested arrays/objects và field trùng để kiểm tra schema validation.
- Fuzz archive metadata, filename và MIME/content mismatch bằng fixture vô hại.
- Fuzz URL parser với IPv4/IPv6, IDN, port, user info, percent-encoding và redirect.

Khi tìm được crash hoặc input làm vi phạm invariant, lưu seed tối thiểu, loại bỏ dữ liệu nhạy cảm và thêm regression test xác định. Đặt memory/CPU/time limit cho fuzz worker để test không làm ảnh hưởng CI runner.

Không dùng fuzzing không giới hạn trên production endpoint. Nếu cần production monitoring, chỉ dùng passive telemetry và canary có kiểm soát.

## 15. Ví dụ kiểm thử JSON depth và body size

Với Spring MVC, có thể kiểm tra body quá lớn bị từ chối ở gateway/container trước khi controller xử lý. Ở application, parser/schema cũng cần giới hạn depth. Test minh họa:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ImportPayloadLimitsIT {
    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsPayloadExceedingContractLimit() throws Exception {
        String oversized = "x".repeat(2_000_000);

        mockMvc.perform(post("/api/imports")
                        .with(jwt().jwt(token -> token
                                .subject("test-user")
                                .claim("tenant_id", "tenant-test")))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"data\":\"" + oversized + "\"}"))
                .andExpect(status().isPayloadTooLarge());
    }
}
```

Đây là ví dụ cần điều chỉnh theo body limit thực tế và nơi giới hạn được thực thi. MockMvc có thể chạy sau một số giới hạn của reverse proxy/container nên cần test riêng ở ingress/gateway. Đừng chỉ giới hạn sau khi toàn bộ body đã được đọc vào heap.

## 16. Regression test cho lỗi đã phát hiện

Mỗi finding nên trở thành test có thể chạy lại. Ghi nhận tối thiểu:

- Endpoint và method bị ảnh hưởng.
- Trust boundary và loại input gây lỗi.
- Principal, tenant và permission fixture.
- Payload tối thiểu tái hiện, đã loại bỏ secret/dữ liệu thật.
- Kết quả trước khi sửa và expected behavior sau khi sửa.
- Side effect cần được chứng minh là không xảy ra.
- Phiên bản parser/library/configuration liên quan.
- CI suite chạy test và owner chịu trách nhiệm.

Regression test cần có cả trường hợp hợp lệ để tránh fix quá chặt. Ví dụ SSRF allowlist phải vẫn cho phép URL hợp lệ đã đăng ký; SQL injection defense vẫn phải cho phép search text có dấu nháy bình thường; XML parser vẫn phải đọc được XML hợp lệ không cần DTD.

## 17. Tích hợp vào CI/CD và môi trường kiểm thử

Có thể chia test theo thời gian và mức độ tác động:

| Tầng | Nội dung | Khi chạy |
|---|---|---|
| Unit | URL policy, input validator, type allowlist, query builder | Mỗi commit |
| Integration | Endpoint thật, database test, mock DNS/HTTP, parser thực tế | Pull request hoặc build chính |
| Contract | Schema, content type, body limits, method và error contract | Mỗi thay đổi API |
| Security regression | Finding SSRF/injection/XXE/deserialization đã sửa | Mỗi commit/release |
| Fuzz/property | Parser, URL normalization, nested payload với budget cố định | Nightly hoặc lịch phù hợp |
| Staging security scan | Discovery và active test trong scope được duyệt | Trước release hoặc theo lịch |

Pin phiên bản parser và dependency; bật cảnh báo dependency vulnerability. Khi nâng version Jackson, SnakeYAML, XML parser, archive library hoặc HTTP client, chạy lại security regression vì behavior và default có thể thay đổi.

## 18. Bằng chứng và tiêu chí pass/fail

Một test security nên có tiêu chí pass rõ ràng:

- Input không hợp lệ bị từ chối bằng response ổn định, không lộ stack trace.
- Input bị cấm không tạo outbound connection, process, query ngoài phạm vi hoặc file ngoài staging directory.
- Không có database mutation, event, notification hoặc job khi authorization/validation thất bại.
- Parser dừng trong resource budget đã định.
- Tenant/object scope không bị thay đổi bởi payload.
- Input hợp lệ vẫn hoạt động theo contract.
- Log/audit có đủ metadata điều tra nhưng không chứa token, secret hoặc raw payload nhạy cảm.

Lưu test name, build ID, dependency/parser version, environment, kết quả, timing/resource metrics và correlation ID. Không lưu credential hoặc dữ liệu production trong artifact. Nếu test bị skip do dependency không sẵn sàng, ghi rõ skipped; không tính skipped là passed.

## 19. Checklist SSRF, injection, parser và deserialization test

- [ ] Inventory mọi endpoint nhận URL hoặc khiến server fetch tài nguyên.
- [ ] Test loopback, private, link-local, IPv6, hostname nội bộ, port và scheme.
- [ ] Test DNS rebinding, nhiều DNS answer và redirect từng hop bằng mock/sandbox.
- [ ] Xác minh không có outbound call tới destination bị cấm.
- [ ] Test SQL/NoSQL input ở search, sort, filter, report và bulk.
- [ ] Dùng parameterized query và allowlist cho field/operator không thể bind.
- [ ] Test OS/LDAP/template input như dữ liệu; không cho input tạo command/filter/expression ngoài contract.
- [ ] Test JSON duplicate key, type mismatch, nesting, field count và body size.
- [ ] Test XML DOCTYPE/external entity; xác minh không đọc file hoặc gọi network.
- [ ] Test YAML tag/type/alias và safe constructor theo thư viện thực tế.
- [ ] Không nhận native Java serialization từ public client; nếu bắt buộc, có ObjectInputFilter allowlist và resource limit.
- [ ] Jackson polymorphic type chỉ dùng subtype/type allowlist hẹp; không bật default typing rộng cho input không tin cậy.
- [ ] Test archive expansion, nested archive, entry count và path traversal nếu API nhận file nén.
- [ ] Xác minh request bị từ chối không tạo side effect và không vượt tenant/object scope.
- [ ] Có test input hợp lệ, regression, fuzz budget và CI evidence.

## Kết luận

SSRF, injection, parser abuse và unsafe deserialization đều khai thác việc server diễn giải dữ liệu không đáng tin cậy vượt khỏi contract. Kiểm thử cần đi qua endpoint và parser thực tế, dùng sink/dependency giả lập, xác minh destination và cấu trúc query, giới hạn parser/resource, đồng thời kiểm tra không có side effect khi request bị từ chối. Kết hợp test URL/DNS/redirect, query builder, XML/YAML/JSON, deserialization allowlist, fuzzing có giới hạn và regression test trong CI giúp phát hiện lỗi ở ranh giới dữ liệu trước khi chúng ảnh hưởng môi trường thật.
