# Bước học tiếp theo

Hoàn thành Spring HATEOAS giúp bạn thiết kế REST API mà client có thể khám phá và điều hướng qua hypermedia. Bạn đã biết cách biểu diễn resource, tạo link, tổ chức collection và pagination, dùng HAL, công bố affordance, tích hợp controller/assembler và kiểm thử hợp đồng link. Bước tiếp theo là đưa những kỹ năng đó vào một API có bảo mật, có hợp đồng được quản lý, có thể quan sát khi chạy và có khả năng vận hành ổn định.

Spring HATEOAS là một phần trong thiết kế API. Nó hỗ trợ server mô tả resource và hành động có thể khám phá; nó không tự thay thế xác thực, phân quyền, validation, quản lý phiên bản, xử lý lỗi, cache hay vận hành. Hãy học tiếp các chủ đề này theo thứ tự dựa trên rủi ro và nhu cầu thực tế của API.

## Những năng lực bạn đã xây dựng

Trong module Spring HATEOAS, bạn đã đi qua các nhóm kỹ năng sau:

| Nhóm năng lực | Điều bạn đã học | Kết quả có thể tạo ra |
| --- | --- | --- |
| Nền tảng REST và hypermedia | Resource, representation, uniform interface và vai trò của link | API cho phép client khám phá đường đi tiếp theo |
| Mô hình representation | RepresentationModel, EntityModel, CollectionModel và PagedModel | Response có body cùng metadata điều hướng |
| Quan hệ link | Relation, self link, URI template, controller link và custom relation | Link có ngữ nghĩa ổn định và ít phụ thuộc URI hardcode |
| Assembly | RepresentationModelAssembler, model processor và entity link | Logic dựng representation có thể tái sử dụng |
| HAL và media type | _links, _embedded, CURIE, HAL-FORMS và content negotiation | Response hypermedia theo định dạng đã công bố |
| Collection và tìm kiếm | Pagination, sorting, filtering và search links | Client duyệt tập dữ liệu lớn có kiểm soát |
| Tích hợp Spring | Spring MVC, WebFlux và Spring Data REST | Hypermedia hoạt động trong các kiểu endpoint khác nhau |
| Hợp đồng và chất lượng | Link tests, security links, caching, performance và error documentation | API có thể được kiểm tra và giải thích cho client |
| Thiết kế thực tế | Embedded có giới hạn, anti-pattern và dự án API root | Có khả năng chọn link/embedded theo nhu cầu sử dụng |

Hãy dùng các năng lực này như nền tảng. Không cần ghi nhớ mọi class của framework; điều quan trọng là biết chọn mô hình phù hợp, tìm đúng tài liệu API và chứng minh response hoạt động qua test.

## Lộ trình học tiếp theo

Thứ tự bên dưới đi từ bảo vệ hành động tới quản lý hợp đồng và vận hành. Bạn có thể điều chỉnh độ sâu theo vai trò backend, platform hoặc API integration.

### 1. Spring Security và authorization theo hành động

Đây là bước tiếp theo có giá trị cao vì hypermedia thường công bố những hành động client có thể thực hiện.

Hãy học:

- Authentication, principal, authorities, scopes và role mapping.
- Method security với các quy tắc authorization ở service/controller.
- Phân quyền theo resource, tenant và quyền sở hữu.
- Cách response thay đổi link hoặc affordance theo principal.
- Khác biệt giữa không công bố một action link và từ chối request tại endpoint.
- Kiểm tra lại quyền khi nhận request vì link có thể cũ hoặc được lưu trong cache.

Thực hành với workflow đơn hàng:

| Trạng thái / quyền | Representation mong đợi |
| --- | --- |
| PENDING và caller có quyền hủy | Có action link cancel |
| PENDING nhưng caller không có quyền hủy | Không công bố cancel |
| SHIPPED | Không công bố cancel |
| Caller không được đọc đơn hàng | Endpoint trả status theo chính sách bảo mật; không rò rỉ dữ liệu đơn |

Đừng xem việc ẩn link là một cơ chế bảo mật. Client có thể tự tạo URI hoặc dùng lại link đã nhận; server vẫn phải xác minh principal, quyền, tenant và trạng thái nghiệp vụ ở mỗi request.

**Sản phẩm cần hoàn thành:** một endpoint có action link thay đổi theo quyền và trạng thái, cùng test cho cả trường hợp được phép và bị từ chối.

### 2. Quản lý hợp đồng API và khả năng tương thích

Hypermedia giúp giảm phụ thuộc vào URI cụ thể, nhưng client vẫn phụ thuộc vào semantics của relation, schema representation, media type và quy tắc nghiệp vụ.

Hãy học:

- Thiết kế OpenAPI để mô tả request, response, media type và error schema.
- Quy ước đặt tên relation và quản lý relation URI.
- Profile link và tài liệu mô tả semantics của representation.
- Quy tắc thêm, bỏ hoặc đổi trường trong response.
- Chính sách tương thích ngược và deprecation.
- Phân biệt thay đổi URI nội bộ với thay đổi hợp đồng mà client quan sát được.

Một thay đổi mapping controller thường có thể được link builder phản ánh tự động. Nhưng đổi relation từ cancel thành revoke hoặc đổi ý nghĩa của status là thay đổi hợp đồng; client có thể phải điều chỉnh.

Khi review một thay đổi API, hãy hỏi:

1. Client cũ có còn đọc được representation không?
2. Relation cũ có còn mang cùng ngữ nghĩa không?
3. Hành động được công bố có thay đổi điều kiện thực hiện không?
4. Media type và profile có còn đúng không?
5. Error response và HTTP status có thay đổi cách client phục hồi không?

**Sản phẩm cần hoàn thành:** một OpenAPI document có schema HAL/Problem Details phù hợp, relation catalog và quy tắc deprecation cho ít nhất một endpoint.

### 3. Contract testing và kiểm thử client điều hướng

Unit test assembler chỉ chứng minh một model được tạo đúng trong isolation. Integration test cần chứng minh server serialize đúng media type, phát ra relation dự kiến và các href thực sự gọi được.

Hãy học:

- MockMvc hoặc WebTestClient cho endpoint HTTP.
- Test theo luồng khám phá: lấy href từ response rồi gọi href đó.
- Kiểm tra relation, embedded relation, media type và pagination links.
- Consumer-driven contract testing khi nhiều client tích hợp với một API.
- Kiểm tra compatibility giữa phiên bản server và client.
- Test security theo principal, tenant và trạng thái resource.

Ưu tiên test semantics thay vì khóa cứng toàn bộ URL. Nếu mapping thay đổi nhưng relation vẫn đúng và href mới hoạt động, client hypermedia nên tiếp tục chạy.

**Sản phẩm cần hoàn thành:** bộ integration test đi từ API root tới collection, item, resource liên quan và action endpoint; test không tự ghép URI con.

### 4. Error handling và khả năng phục hồi

Client cần biết vì sao hành động thất bại và nên làm gì tiếp theo. Hãy tiếp tục đào sâu:

- RFC 9457 Problem Details và application/problem+json.
- Phân biệt 400, 401, 403, 404, 409, 412, 422, 429, 500 và 503.
- Error type URI ổn định và extension members có schema.
- Retry, backoff, jitter, Retry-After và idempotency.
- Trace ID để liên kết response lỗi với log.
- Cách client làm mới resource và khám phá lại action links sau 409 hoặc 412.

Một link cancel có thể xuất hiện khi đơn hàng đang PENDING. Trước lúc client gửi request, một tiến trình khác có thể đã chuyển đơn sang SHIPPED. Server cần trả lỗi xung đột có thể hiểu được; client tải lại resource và đọc các action link mới.

**Sản phẩm cần hoàn thành:** một error catalog có type URI, status, code, ví dụ response, retry semantics và test cho các lỗi nghiệp vụ chính.

### 5. Observability và vận hành API

Khi API được triển khai, bạn cần biết request đi qua đâu, link nào được sử dụng, lỗi xuất hiện ở bước nào và response chậm do tầng nào.

Hãy học:

- Structured logging và correlation/trace ID.
- Metrics cho request count, latency, error rate và saturation.
- Distributed tracing qua gateway, controller, service và database.
- Spring Boot Actuator và Micrometer.
- OpenTelemetry và cách truyền trace context.
- Dashboard, alert và SLO cho API.

Không đưa order ID, user ID hoặc tenant ID có cardinality cao vào metric tag. Dùng log/tracing có kiểm soát để điều tra một request cụ thể; metric nên dùng dimension có tập giá trị giới hạn.

Với API HATEOAS, có thể quan sát thêm loại relation/action được gọi và kết quả của action, nhưng tránh ghi payload nhạy cảm hoặc token vào log.

**Sản phẩm cần hoàn thành:** dashboard thể hiện latency p50/p95/p99, throughput, tỷ lệ lỗi và trace của một request đi qua nhiều thành phần.

### 6. Cache, hiệu năng và khả năng mở rộng

Link và embedded data là một phần representation. Vì vậy, cache và hiệu năng phải tính đến cả dữ liệu lẫn hypermedia.

Hãy củng cố:

- Cache-Control, ETag, Last-Modified và conditional GET.
- Vary và content negotiation.
- Cache key cho response phụ thuộc principal, tenant hoặc query parameter.
- Invalidation khi resource liên quan thay đổi.
- DTO projection, batch fetching và phòng tránh N+1.
- Pagination giới hạn, payload size và số lượng link.
- Profiling CPU, allocation, serialization và database query.

Nếu response có action link tùy theo quyền, không cache chung representation của nhiều principal. Nếu response embed customer preview, validator phải phản ánh thay đổi của preview đó chứ không chỉ version của order.

**Sản phẩm cần hoàn thành:** endpoint collection có pagination, query count ổn định theo page size, ETag đúng với representation và cache policy không làm lộ link cá nhân hóa.

### 7. Media type và trải nghiệm thao tác của client

Khi client cần biết cách gửi dữ liệu để thực hiện action, hãy tìm hiểu sâu hơn về:

- HAL-FORMS và affordance metadata.
- Form template, method, content type và input properties.
- Content negotiation cho nhiều media type.
- Profile và tài liệu semantics.
- Khi nào dùng HAL link đơn giản, khi nào cần affordance hoặc form.

HAL link cho biết client có thể điều hướng tới một URI. HAL-FORMS có thể mô tả thêm cách gửi dữ liệu cho một thao tác. Không cần dùng form metadata cho mọi endpoint; chọn theo mức độ client cần khám phá input contract.

**Sản phẩm cần hoàn thành:** một action có form metadata để client biết method, target và các trường input cần gửi, cùng test serialization và content negotiation.

### 8. Triển khai sau reverse proxy và API gateway

Link tuyệt đối được tạo theo request context. Trong môi trường production, gateway hoặc reverse proxy có thể thay đổi host, scheme, port và context path.

Hãy học:

- Forwarded và X-Forwarded-* headers.
- Cấu hình trusted proxy và cách tránh tin header từ nguồn không đáng tin.
- Context path và base path khi deploy nhiều service.
- API gateway routing và authentication propagation.
- CORS, TLS termination và public URL.
- Kiểm thử link khi ứng dụng chạy dưới prefix hoặc host khác.

Một API hoạt động ở localhost nhưng phát href nội bộ khi đi qua gateway vẫn chưa sẵn sàng cho client bên ngoài. Hãy test public URL trong môi trường gần production.

**Sản phẩm cần hoàn thành:** chạy API qua gateway hoặc reverse proxy và xác nhận tất cả href dùng public scheme, host và base path đúng.

## Capstone: nâng cấp API quản lý đơn hàng

Dùng project API root đã xây dựng làm nền tảng. Mở rộng theo một luồng nghiệp vụ hoàn chỉnh thay vì thêm link rời rạc.

Luồng mục tiêu:

1. Client gọi API root và khám phá orders, customers, search.
2. Client theo link tới collection, sử dụng pagination và filter.
3. Client mở order và đọc trạng thái, customer link, action links.
4. Action links thay đổi theo trạng thái đơn và quyền của principal.
5. Client gửi action request theo affordance hoặc form contract.
6. Server xác minh lại quyền và trạng thái; trả success hoặc Problem Details.
7. Client làm mới resource sau conflict và khám phá action links mới.
8. Metrics, trace, cache validator và contract tests bảo vệ vận hành.

### Yêu cầu chức năng

| Khu vực | Yêu cầu |
| --- | --- |
| API root | Có self, orders, customers và search |
| Collection | Có pagination, sorting/filter links và up |
| Order | Có self, customer và relation tới items |
| Action | cancel chỉ xuất hiện khi trạng thái và quyền cho phép |
| Security | Phân quyền theo principal và tenant |
| Error | Dùng Problem Details với type URI và code ổn định |
| Documentation | OpenAPI mô tả media type, relation và lỗi |
| Testing | Test theo href, security, action và error contract |
| Operations | Có trace, metrics, cache policy và query-count guard |

### Thứ tự triển khai

1. Giữ API root và collection links hoạt động.
2. Thêm authentication và authorization cho resource.
3. Thêm action links theo state machine của order.
4. Xây action endpoint và Problem Details.
5. Bổ sung pagination, search và giới hạn payload.
6. Mô tả hợp đồng bằng OpenAPI và tài liệu relation.
7. Viết integration/contract tests theo luồng client.
8. Bổ sung metrics, tracing, cache và kiểm thử qua gateway.

Mỗi bước nên có một thay đổi nhỏ, một test chứng minh hành vi và một ví dụ response cập nhật. Cách làm này giúp bạn phát hiện sớm khi relation, quyền hoặc trạng thái không còn nhất quán.

## Chọn chủ đề tiếp theo theo mục tiêu nghề nghiệp

| Mục tiêu | Nên học tiếp |
| --- | --- |
| Backend API developer | Spring Security, Spring Data JPA, validation, transaction và contract testing |
| API/platform engineer | OpenAPI governance, gateway, observability, caching và SLO |
| Integration engineer | HAL/HAL-FORMS, client navigation, media type negotiation và consumer contracts |
| Technical lead/architect | API evolution, relation semantics, security model, compatibility và architecture decision records |
| Performance engineer | Query planning, batch fetching, profiling, serialization và load testing |

Bạn không cần học tất cả các nhánh cùng lúc. Chọn một API thật hoặc capstone làm trung tâm, sau đó bổ sung chủ đề giải quyết rủi ro lớn nhất của nó.

## Tự đánh giá mức độ sẵn sàng

Hãy tự trả lời các câu hỏi sau bằng cách chỉ ra code, response hoặc test chứng minh:

1. Client có thể bắt đầu từ một URI duy nhất và khám phá collection mà không hardcode URI con không?
2. Relation names có ổn định và được mô tả rõ không?
3. Assembler có tách khỏi truy vấn database và nghiệp vụ không?
4. Embedded resource có giới hạn kích thước, độ sâu và quyền truy cập không?
5. Action links có phản ánh quyền và trạng thái hiện tại không?
6. Endpoint có kiểm tra lại quyền khi nhận request không?
7. Client có thể phân loại lỗi bằng type/code thay vì phân tích detail không?
8. Test có follow href thực tế và kiểm tra media type không?
9. Cache có tính đến principal, tenant, embedded data và link không?
10. Metrics và trace có đủ để tìm nguyên nhân request chậm hoặc thất bại không?
11. API có thể thay đổi mapping mà client vẫn điều hướng được không?
12. OpenAPI và tài liệu relation có phản ánh đúng response đang chạy không?

Nếu chưa trả lời được một câu hỏi bằng bằng chứng, hãy biến nó thành một task nhỏ trong capstone.

## Dấu hiệu bạn đã sẵn sàng dùng Spring HATEOAS trong dự án

Bạn có thể đưa kỹ năng vào dự án khi:

- Bạn giải thích được vì sao một resource cần link hoặc embedded preview.
- Bạn tạo link từ controller mapping hoặc URI template phù hợp.
- Bạn tổ chức representation và collection bằng model/assembler phù hợp.
- Bạn không coi link là cơ chế phân quyền.
- Bạn có thể kiểm tra relation và điều hướng bằng integration test.
- Bạn biết xử lý lỗi, cache, content negotiation và URL sau gateway.
- Bạn có thể giải thích trade-off của HAL, HAL-FORMS và response thuần JSON.

Một API tốt không cần có thật nhiều link. Nó cần công bố đúng những quan hệ giúp client hoàn thành tác vụ, giữ hợp đồng có thể tiến hóa và bảo vệ mọi hành động ở phía server.

## Tài liệu nên dùng khi học tiếp

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/)
- [Spring Boot Reference](https://docs.spring.io/spring-boot/reference/)
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/)
- [Spring Framework Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)

## Kết luận

Spring HATEOAS cung cấp công cụ để biểu diễn resource và khả năng điều hướng qua hypermedia. Sau module này, hướng phát triển tự nhiên là kết hợp hypermedia với authorization, quản lý hợp đồng, kiểm thử client, xử lý lỗi, observability, cache và triển khai thực tế. Hãy tiếp tục bằng một API nghiệp vụ có trạng thái và nhiều vai trò người dùng; dùng capstone để kiểm chứng từng quyết định bằng response, test và số liệu vận hành. Khi client có thể khám phá hành động đúng, server bảo vệ hành động đó và team có thể quan sát, kiểm thử, tiến hóa hợp đồng, bạn đã chuyển kiến thức Spring HATEOAS thành năng lực thiết kế API có thể vận hành.
