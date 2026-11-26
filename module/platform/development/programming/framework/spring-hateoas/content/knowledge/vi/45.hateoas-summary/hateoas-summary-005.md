# Checklist tương thích client cho API Spring HATEOAS

Một API HATEOAS tương thích khi client hiện tại vẫn có thể đọc representation, khám phá relation và thực hiện các luồng nghiệp vụ đã cam kết sau khi server được cập nhật. Việc giữ nguyên URL chưa đủ để bảo đảm tương thích: đổi media type, relation name, cấu trúc embedded resource, kiểu dữ liệu, affordance hoặc điều kiện xuất hiện của link đều có thể làm client cũ hỏng.

Checklist này dùng trước khi phát hành một thay đổi Spring HATEOAS. Nó giúp đội phát triển xác định phần nào của contract đang thay đổi, client nào có thể bị ảnh hưởng, test nào cần chạy và cách triển khai chuyển đổi an toàn. Trọng tâm là hành vi quan sát được qua HTTP: status, headers, media type, payload và hypermedia controls.

## 1. Xác định contract mà client đang sử dụng

Trước khi đánh giá một thay đổi, hãy lập danh sách những điều client thực sự phụ thuộc:

- Entry point và cách client lấy URI bắt đầu.
- Media type trong Accept và Content-Type.
- Payload fields, kiểu dữ liệu và quy tắc null/omitted.
- Relation names trong _links và _embedded.
- Ý nghĩa của từng relation và điều kiện xuất hiện.
- URI template, biến, default và quy tắc encoding.
- Pagination, sorting và filtering.
- Affordance hoặc form template, nếu API có công bố.
- HTTP status, Problem Details và error codes.
- Authentication, authorization và link visibility.
- Cache validators, cache directives và các header khác.

Không nên chỉ đọc controller mapping để kết luận contract. Một client hypermedia có thể không gọi trực tiếp mọi endpoint; nó có thể bắt đầu từ một link rồi theo nhiều relation qua các resource. Hãy kiểm tra các response thực tế và luồng traversal mà consumer đang chạy.

## 2. Phân loại mức độ tương thích

Có thể dùng các mức sau để đánh giá thay đổi:

| Mức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Tương thích bổ sung | Client cũ tiếp tục hoạt động nếu bỏ qua thông tin chưa biết. | Thêm một relation tùy chọn mới hoặc field optional mới. |
| Có điều kiện | An toàn nếu client tuân thủ contract và không giả định điều chưa cam kết. | Thêm embedded relation hoặc thay đổi thứ tự field JSON. |
| Phá vỡ tương thích | Client đang dựa vào contract cũ có thể không hoạt động. | Xóa relation bắt buộc, đổi tên field, đổi media type hoặc đổi semantics relation. |
| Chưa xác định | Chưa có bằng chứng về hành vi consumer. | Thay đổi serializer hoặc thư viện hypermedia mà chưa có contract test. |

Một thay đổi chỉ được coi là tương thích bổ sung khi consumer được thiết kế để chịu được thông tin mới. Client dùng schema đóng, so sánh toàn bộ JSON hoặc từ chối relation lạ có thể bị ảnh hưởng ngay cả khi server chỉ thêm một field.

## 3. Checklist media type và content negotiation

Media type là một phần của contract. Kiểm tra các điểm sau:

- [ ] Client gửi đúng Accept header đã được tài liệu hóa.
- [ ] Response dùng Content-Type phù hợp với representation thực tế.
- [ ] HAL JSON được công bố là application/hal+json.
- [ ] Nếu API hỗ trợ nhiều media type, mỗi media type có schema và semantics riêng.
- [ ] Hành vi khi Accept không được hỗ trợ đã rõ, thường là 406 Not Acceptable.
- [ ] Không vô tình đổi hành vi application/json nhận HAL do thay cấu hình Spring Boot.
- [ ] Client không suy luận media type chỉ từ việc body có field _links.
- [ ] Test bao phủ từng media type mà API cam kết.

Spring Boot có thể cấu hình application/json như media type mặc định để trả HAL trong một số cấu hình Spring HATEOAS. Nếu thay đổi thuộc tính use-hal-as-default-json-media-type hoặc HypermediaMappingInformation, cần đánh giá lại negotiation và kiểm tra consumer. Đừng đổi property chỉ để làm test pass mà không xác định hành vi trước và sau.

Ví dụ test xác nhận HAL:

~~~java
mockMvc.perform(get("/api/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON));
~~~

Nếu API chỉ hỗ trợ HAL, thêm test với một media type không được hỗ trợ để khóa hành vi 406. Nếu application/json vẫn được hỗ trợ, test phải ghi nhận hành vi đó thay vì giả định luôn bị từ chối.

## 4. Checklist payload fields và schema

Đối với phần dữ liệu resource:

- [ ] Field bắt buộc vẫn tồn tại.
- [ ] Field không bị đổi tên hoặc chuyển vị trí ngoài kế hoạch.
- [ ] Kiểu dữ liệu không thay đổi âm thầm, ví dụ number thành string.
- [ ] Đơn vị và ý nghĩa của số liệu không thay đổi.
- [ ] Quy tắc null, omitted và default được giữ ổn định.
- [ ] Field mới là optional hoặc có default tương thích.
- [ ] Không xóa field mà client đã sử dụng.
- [ ] Không đưa field nội bộ, PII hoặc dữ liệu nhạy cảm vào response.
- [ ] Field không bị đổi semantics trong khi vẫn giữ nguyên tên.

Thêm một field thường có thể tương thích với client linh hoạt, nhưng có thể phá client dùng generated model nghiêm ngặt hoặc schema đóng. Xóa field, đổi kiểu, đổi đơn vị hoặc đổi ý nghĩa thường là breaking change.

Không dùng ví dụ JSON làm schema duy nhất. Tài liệu cần mô tả kiểu, required/optional, giá trị có thể có và ý nghĩa nghiệp vụ. Nếu API dùng OpenAPI, cập nhật schema và kiểm tra response thực tế so với schema.

## 5. Checklist relation names và semantics

Relation là vocabulary điều hướng mà client dùng để khám phá API. Kiểm tra:

- [ ] Relation bắt buộc vẫn xuất hiện ở đúng resource/collection.
- [ ] Relation giữ nguyên spelling và URI identity.
- [ ] Relation vẫn trỏ tới cùng loại target và giữ semantics đã công bố.
- [ ] Relation tùy chọn có điều kiện xuất hiện rõ ràng.
- [ ] Relation không bị đổi nghĩa chỉ vì endpoint được refactor.
- [ ] Relation extension dùng URI ổn định hoặc CURIE đã tài liệu hóa.
- [ ] IANA relation được dùng đúng semantics đã đăng ký.
- [ ] Client xử lý được relation chưa biết.

Đổi relation name là breaking change với client đang tìm relation cũ. Thêm relation mới thường là thay đổi bổ sung nếu client bỏ qua relation không biết. Tái sử dụng relation cũ cho mục đích khác còn nguy hiểm hơn đổi tên vì client có thể tiếp tục theo link nhưng thực hiện sai hành động.

Ví dụ contract test cho relation:

~~~java
mockMvc.perform(get("/api")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.orders.href").exists());
~~~

Nếu API đổi từ orders sang purchases, không nên sửa test để chấp nhận thay đổi mà chưa có migration plan cho consumer.

## 6. Checklist HAL links

Đối với từng relation trong _links:

- [ ] href hợp lệ và có thể truy cập trong môi trường tương ứng.
- [ ] Target trả về media type được tài liệu hóa.
- [ ] self trỏ tới resource/representation hiện tại.
- [ ] Link không phụ thuộc hostname hard-code của môi trường phát triển.
- [ ] Link được tạo theo request context và forwarded headers đúng cách.
- [ ] Relation có nhiều link được client xử lý đúng nếu contract cho phép.
- [ ] Thuộc tính templated phản ánh chính xác URI template.
- [ ] type, title, hreflang, profile hoặc deprecation có ý nghĩa đúng nếu được sử dụng.
- [ ] Link không chứa token, secret hoặc dữ liệu cá nhân trong query string.
- [ ] Client theo href được server công bố, không tự ghép URL theo route nội bộ.

Đổi host hoặc base path không nhất thiết là breaking change nếu client theo href. Nhưng link sai scheme, thiếu context path hoặc trỏ tới route cũ là lỗi runtime. Test nên kiểm tra target theo cách phù hợp với môi trường, tránh hard-code localhost hoặc hostname production.

## 7. Checklist URI template

Nếu API công bố link templated:

- [ ] Link có templated = true.
- [ ] Cú pháp URI template hợp lệ.
- [ ] Tên biến và semantics không đổi.
- [ ] Kiểu dữ liệu, default và giới hạn được tài liệu hóa.
- [ ] Quy tắc encoding được kiểm tra với ký tự đặc biệt.
- [ ] Biến optional có thể bỏ qua đúng cách.
- [ ] Server xử lý giá trị thiếu, sai định dạng và ngoài giới hạn nhất quán.
- [ ] Client dùng URI Template expansion thay vì nối query string thủ công.

Đổi tên biến template có thể làm client không mở rộng được URI. Đổi default cũng có thể thay đổi kết quả tìm kiếm mà không làm request thất bại. Vì vậy, default, sort order và filter semantics đều là phần contract cần version hoặc migration khi thay đổi.

## 8. Checklist embedded resources và collection relation

HAL phân biệt link và embedded resource. Với mỗi collection:

- [ ] Tên relation trong _embedded ổn định.
- [ ] Mỗi item có payload schema được tài liệu hóa.
- [ ] Embedded item có links cần thiết nếu contract yêu cầu.
- [ ] Quan hệ chỉ được embed khi API công bố hỗ trợ.
- [ ] Không chuyển association link thành embedded payload mà không đánh giá payload size và privacy.
- [ ] Không xóa embedded resource mà client đang dùng.
- [ ] Embedded collection lớn có giới hạn hoặc pagination riêng.
- [ ] Authorization áp dụng cho embedded data như với resource độc lập.

Tên collection relation có thể được cấu hình qua @Relation(itemRelation, collectionRelation). Đổi collectionRelation có thể phá client đang đọc _embedded.orders dù URL collection vẫn không đổi.

Thêm embedded data có thể làm tăng payload và lộ dữ liệu mà consumer trước đó không nhận. Vì vậy, một thay đổi additive về schema vẫn cần security review và payload budget check.

## 9. Checklist pagination, sorting và filtering

Đối với paged resource:

- [ ] Relation self, first, prev, next và last xuất hiện đúng vị trí.
- [ ] Client không giả định prev luôn có mặt ở trang đầu.
- [ ] Client không giả định next luôn có mặt ở trang cuối.
- [ ] Page index và default page size được giữ ổn định.
- [ ] Maximum page size không bị giảm bất ngờ.
- [ ] Sort fields và hướng mặc định được tài liệu hóa.
- [ ] Filter parameters được giữ trong pagination links.
- [ ] totalElements và totalPages có semantics nhất quán.
- [ ] Nếu chuyển từ Page sang Slice/cursor, client được thông báo về thay đổi metadata.

Không yêu cầu mọi response đều phải có đủ first/prev/next/last. Relation điều hướng phụ thuộc vị trí trang và khả năng của server. Client nên kiểm tra link trước khi hiển thị hoặc theo nó.

Nếu server đổi thứ tự mặc định hoặc cách tính total, client có thể vẫn parse JSON nhưng kết quả nghiệp vụ thay đổi. Đây là behavioral compatibility cần kiểm thử bằng fixture dữ liệu có thứ tự và filter rõ ràng.

## 10. Checklist affordances và action contracts

Nếu API công bố affordance hoặc HAL-FORMS:

- [ ] Action relation/template name ổn định.
- [ ] HTTP method không đổi ngoài kế hoạch.
- [ ] Target URI và request Content-Type chính xác.
- [ ] Property names, types và required flags giữ contract.
- [ ] Validation constraints được tài liệu hóa.
- [ ] Response status và body của action được mô tả.
- [ ] Điều kiện xuất hiện action theo state/authorization rõ ràng.
- [ ] Client hiểu action có thể vắng mặt.
- [ ] Server vẫn kiểm tra quyền và trạng thái khi nhận request.

Một affordance mới thường là bổ sung, nhưng nếu client thấy affordance đó rồi gửi request không tương thích, contract action chưa hoàn chỉnh. Đổi method POST thành DELETE, đổi property hoặc đổi target có thể phá consumer dù relation name vẫn giữ nguyên.

HAL và HAL-FORMS có media type khác nhau. Không thêm _templates vào HAL JSON rồi giả định mọi client HAL đều hiểu form metadata. Tài liệu hóa chính xác media type và cấu trúc được dùng.

## 11. Checklist error representation

Lỗi là một phần của API contract:

- [ ] HTTP status phản ánh đúng semantics.
- [ ] Content-Type là application/problem+json nếu dùng RFC 9457.
- [ ] type URI ổn định cho từng problem type.
- [ ] code extension giữ spelling và ý nghĩa.
- [ ] status trong body khớp HTTP status.
- [ ] instance phân biệt occurrence khi được cung cấp.
- [ ] title/detail không được client dùng làm khóa logic.
- [ ] Validation errors có schema và pointer ổn định.
- [ ] help/describedby links trỏ tới tài liệu đúng.
- [ ] Không lộ stack trace, SQL, secret hoặc PII.

Đổi mã lỗi hoặc type URI có thể phá client đang phân nhánh theo các giá trị đó. Thay đổi câu chữ title/detail thường ít ảnh hưởng hơn nếu client tuân thủ contract và không parse văn bản.

Ví dụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-already-shipped",
  "title": "Cannot cancel a shipped order",
  "status": 409,
  "code": "ORDER_ALREADY_SHIPPED",
  "detail": "The order has already been shipped."
}
~~~

## 12. Checklist authorization và link visibility

Hypermedia có thể giúp client biết action nào đang được công bố, nhưng link visibility không phải cơ chế bảo vệ duy nhất:

- [ ] Resource chỉ hiển thị cho principal được phép đọc.
- [ ] Action link chỉ xuất hiện theo policy công khai.
- [ ] Quyền được kiểm tra lại khi client gọi action URI.
- [ ] Không dựa vào việc client không thấy link để bỏ qua server-side authorization.
- [ ] Embedded resource không tiết lộ dữ liệu vượt quyền.
- [ ] Response theo người dùng không bị chia sẻ qua public cache.
- [ ] Link và error response không tiết lộ resource existence trái chính sách.
- [ ] Test có principal khác nhau để kiểm tra relation visibility.

Ví dụ, người dùng A có thể thấy relation cancel cho order của mình, còn người dùng B không thấy. Nếu cả hai response bị dùng chung cache key, người dùng B có thể nhận representation chứa action link của A. Cache policy phải tính tới authorization context.

## 13. Checklist cache và HTTP headers

Khi representation chứa link động, cache cần được đánh giá cẩn thận:

- [ ] Vary header phản ánh các request headers làm thay đổi representation, ví dụ Accept hoặc Accept-Language.
- [ ] Cache-Control phù hợp với dữ liệu công khai hay cá nhân hóa.
- [ ] ETag/Last-Modified thay đổi khi representation thay đổi theo contract.
- [ ] Link theo quyền không lọt vào shared cache.
- [ ] Host/context path trong link được xử lý đúng qua proxy.
- [ ] Cache invalidation xảy ra khi resource state hoặc collection membership thay đổi.
- [ ] Response 304 vẫn được client xử lý đúng theo HTTP semantics.

Nếu affordance thay đổi theo trạng thái hoặc quyền, representation có thể khác dù payload business fields giống nhau. ETag phải phản ánh biến thể được cache. Không tạo một ETag chỉ dựa trên database row nếu hypermedia controls có thể khác theo principal.

## 14. Checklist versioning và deprecation

Trước khi loại bỏ relation, field hoặc action:

- [ ] Xác định consumer đang dùng phần tử cũ.
- [ ] Có replacement relation/field/action rõ ràng.
- [ ] Công bố deprecation và migration guidance.
- [ ] Có thời gian chuyển đổi phù hợp với vòng đời client.
- [ ] Nếu cần, cung cấp cả relation cũ và mới trong giai đoạn chuyển tiếp.
- [ ] Có telemetry hoặc feedback để biết client còn dùng contract cũ không.
- [ ] Xóa phần tử cũ sau khi hết thời gian hỗ trợ đã cam kết.

Không phải mọi thay đổi đều cần tăng major version. Nhưng một thay đổi phá vỡ semantics cần có versioning hoặc migration strategy rõ ràng. Version có thể nằm trong URI, media type/profile hoặc cơ chế khác của API; điều quan trọng là client biết contract nào đang được áp dụng.

Thuộc tính deprecation trên HAL link có thể trỏ tới tài liệu giải thích việc deprecated. Nó không tự thay thế kế hoạch truyền thông và migration.

## 15. Kiểm thử producer contract với MockMvc

Producer test kiểm tra server đang phát hành đúng contract. Ví dụ:

~~~java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.id").value(orderId.toString()))
    .andExpect(jsonPath("$.status").exists())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.orders.href").exists());
~~~

Test này xác nhận field và relation bắt buộc. Với relation tùy chọn, tạo fixture cho cả trường hợp link có mặt và vắng mặt. Không chỉ kiểm tra JSON path tồn tại; khi quan trọng, hãy theo href và xác nhận target trả status/media type đúng.

## 16. Kiểm thử client traversal thay vì chỉ kiểm tra JSON snapshot

Một consumer hypermedia nên được kiểm tra bằng hành trình:

1. Gọi entry point.
2. Tìm relation orders.
3. Lấy href từ link.
4. Gọi collection bằng href đó.
5. Tìm item trong _embedded.orders.
6. Lấy self href của item.
7. Gọi resource detail.
8. Nếu cancel xuất hiện, đọc action contract và thực hiện request hợp lệ.

Test như vậy chứng minh relation và target hoạt động cùng nhau. Snapshot toàn bộ JSON dễ bị nhiễu bởi host, ID, timestamp hoặc thứ tự field, và thường không chứng minh client có thể điều hướng.

Client nên bỏ qua relation và extension field chưa biết. Một test consumer có thể thêm một relation lạ vào fixture rồi xác nhận client vẫn đọc được orders và self. Đây là cách kiểm tra khả năng mở rộng của hypermedia parser.

## 17. Ma trận tương thích cho thay đổi thường gặp

| Thay đổi | Rủi ro mặc định | Hành động trước release |
| --- | --- | --- |
| Thêm field optional | Thấp đến trung bình | Kiểm tra client chịu unknown field và schema không đóng. |
| Xóa/đổi tên field | Cao | Version hoặc migration; tìm consumer sử dụng. |
| Đổi kiểu/đơn vị field | Cao | Tạo field mới hoặc version contract. |
| Thêm relation optional | Thấp | Kiểm tra client bỏ qua relation chưa biết. |
| Xóa relation đang dùng | Cao | Thêm replacement và giai đoạn deprecation. |
| Đổi relation semantics | Rất cao | Tạo relation mới; không tái sử dụng tên cũ. |
| Đổi host/base path | Trung bình | Kiểm tra href và forwarded headers; client phải theo link. |
| Đổi URI template variable | Cao | Giữ biến cũ hoặc version/migrate template. |
| Thay Page bằng Slice | Cao nếu client cần totals | Công bố thay đổi page metadata và navigation. |
| Thêm embedded resource | Trung bình | Kiểm tra payload size, authorization và schema. |
| Đổi action method/input | Cao | Version action contract và kiểm thử consumer. |
| Đổi error code/type | Cao | Giữ mapping cũ hoặc công bố migration. |
| Đổi Content-Type | Rất cao | Kiểm tra Accept negotiation và client parser. |
| Thay điều kiện xuất hiện link | Trung bình đến cao | Đánh giá workflow client và policy; test theo state. |

Mức rủi ro chỉ là mặc định. Một consumer cụ thể có thể nhạy hơn nhiều nếu nó giả định field, relation hoặc link luôn có mặt. Dùng telemetry và contract tests để xác định rủi ro thực tế.

## 18. Quy trình review trước khi phát hành

Có thể áp dụng trình tự:

1. Mô tả thay đổi ở cấp contract: field, relation, media type, action, error hoặc header.
2. So sánh response trước/sau bằng fixture đại diện.
3. Phân loại thay đổi additive, conditional, breaking hoặc unknown.
4. Xác định consumer và luồng traversal bị ảnh hưởng.
5. Cập nhật relation catalog, OpenAPI và ví dụ response.
6. Chạy producer contract tests và consumer traversal tests.
7. Kiểm tra authorization, cache, payload size và error handling.
8. Chuẩn bị migration/deprecation nếu có breaking change.
9. Phát hành theo chiến lược rollout phù hợp.
10. Theo dõi lỗi client và tỷ lệ sử dụng relation cũ sau release.

Review không kết thúc khi JSON vẫn parse được. Cần xác nhận client vẫn khám phá đúng khả năng và thực hiện được các use case đã cam kết.

## 19. Checklist release dạng ngắn

### Contract

- [ ] Entry point và media type không thay đổi ngoài kế hoạch.
- [ ] Payload fields bắt buộc giữ tên, kiểu và semantics.
- [ ] Relation names và URI identity ổn định.
- [ ] URI templates, pagination và affordances giữ contract.
- [ ] Error types/codes và status mapping được kiểm tra.

### Runtime

- [ ] Link href hoạt động trong môi trường triển khai.
- [ ] Link visibility đúng theo state và authorization.
- [ ] Embedded resources không vượt quyền hoặc payload budget.
- [ ] Cache/ETag/Vary phù hợp với representation thực tế.
- [ ] Client không cần hard-code route nội bộ để traversal.

### Verification

- [ ] MockMvc producer tests pass.
- [ ] Consumer traversal tests pass.
- [ ] Schema/OpenAPI validation pass.
- [ ] Unknown relation/field không làm client cũ lỗi.
- [ ] Migration/deprecation đã được công bố nếu cần.

## 20. Bài tập tổng kết

Giả sử một release thay đổi API đơn hàng như sau: thêm relation invoice, đổi embedded relation orders thành purchases, bỏ field total khỏi collection summary, thêm action refund và đổi error code ORDER_ALREADY_SHIPPED thành ORDER_CANNOT_CANCEL.

Hãy:

1. Phân loại từng thay đổi theo mức tương thích.
2. Xác định client nào có thể bị ảnh hưởng.
3. Đề xuất thay đổi additive hoặc migration để giữ consumer cũ hoạt động.
4. Viết producer tests cho relation invoice, collection relation và error code.
5. Viết consumer traversal test để client cũ bỏ qua invoice nếu chưa hỗ trợ.
6. Kiểm tra refund chỉ xuất hiện khi policy và trạng thái đơn cho phép.
7. Cập nhật relation catalog, OpenAPI và response examples.
8. Đề xuất thời điểm deprecate relation/field/error code cũ.

## Tiêu chí hoàn thành

Bạn đã sẵn sàng review tương thích client khi có thể xác định contract runtime mà client đang dùng; phân biệt thay đổi bổ sung với thay đổi phá vỡ; kiểm tra media type, payload, relation, URI template, pagination, affordance và error contract; xác nhận authorization/cache không làm rò rỉ link; và chạy được producer lẫn consumer tests theo các luồng traversal thực tế.

Một API HATEOAS tương thích không yêu cầu client biết trước toàn bộ URL. Nó yêu cầu server giữ semantics đã công bố, cung cấp relation nhất quán và cho phép client khám phá khả năng mới mà không bị hỏng khi gặp thông tin chưa biết.

## Tài liệu tham khảo chính thức

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring Boot – Spring HATEOAS support](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [IANA – Link Relation Types](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
