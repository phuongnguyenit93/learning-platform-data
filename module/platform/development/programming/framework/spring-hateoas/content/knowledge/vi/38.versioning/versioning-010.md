# Kiểm thử tương thích cho API Spring HATEOAS

API hypermedia thường tiến hóa theo thời gian: server thêm trường dữ liệu, đổi đường dẫn, bổ sung relation, mở rộng trạng thái nghiệp vụ hoặc công bố affordance mới. Một thay đổi có thể không ảnh hưởng client đang theo link và chỉ đọc các trường đã biết, nhưng lại làm hỏng client đang ghép URI thủ công hoặc giả định response luôn có một cấu trúc cố định. Vì vậy, kiểm thử tương thích cần đánh giá hợp đồng mà client thực sự tiêu thụ, bao gồm dữ liệu, media type, relation, URI template và hành động được công bố.

Với Spring HATEOAS, hợp đồng không chỉ là JSON payload. Client khám phá tài nguyên qua link relation, đọc embedded resource, theo pagination links và có thể dùng affordance để biết cách gửi request. Kiểm thử tương thích phải xác nhận các semantics này được giữ ổn định khi server thay đổi, đồng thời xác định rõ thay đổi nào cần một phiên bản API mới hoặc giai đoạn chuyển tiếp.

## 1. Tương thích API có nghĩa gì?

Tương thích là khả năng một phiên bản client tiếp tục hoạt động với phiên bản server mới trong phạm vi hợp đồng đã cam kết. Cần phân biệt hai hướng:

- Backward compatibility: client cũ tiếp tục làm việc với server mới.
- Forward compatibility: client mới có thể làm việc với server cũ trong phạm vi các khả năng mà server cũ hỗ trợ.

Trong thực tế, không phải mọi client đều cần hỗ trợ mọi phiên bản server. Hãy xác định rõ ma trận client/server mà sản phẩm cam kết, ví dụ client hiện tại phải hoạt động với server mới nhất và server phải duy trì endpoint v1 trong thời gian chuyển đổi.

Một thay đổi được xem là an toàn hay phá vỡ tương thích còn phụ thuộc cách client tiêu thụ API. Thêm một trường tùy chọn thường an toàn với client bỏ qua trường chưa biết, nhưng có thể gây lỗi cho client dùng schema strict. Đổi relation có thể không ảnh hưởng client chỉ theo self link, nhưng làm hỏng client đang tìm relation cũ.

## 2. Hợp đồng hypermedia gồm những phần nào?

Khi kiểm thử API Spring HATEOAS, hãy xem các thành phần sau là một phần hợp đồng:

| Thành phần | Ví dụ | Điều cần giữ tương thích |
| --- | --- | --- |
| Media type | application/hal+json | Client vẫn thương lượng được representation được hỗ trợ. |
| Link relation | self, orders, customer, next | Ngữ nghĩa và tên relation mà client dùng vẫn tồn tại. |
| Link target | href của self hoặc customer | URI trỏ tới đúng resource và có thể được theo. |
| URI template | {?page,size,sort} | Tên biến, kiểu giá trị và ý nghĩa tham số được giữ. |
| Payload field | id, status, total | Tên, kiểu, nullability và semantics không thay đổi ngoài cam kết. |
| Embedded relation | _embedded.orders | Tên relation và cấu trúc item được giữ. |
| Page metadata | number, size, totalElements | Ý nghĩa và cách đánh số trang không thay đổi bất ngờ. |
| Affordance | cancel dùng POST | Method, input và điều kiện thao tác phản ánh đúng hợp đồng. |
| HTTP behavior | status code, error body | Client tiếp tục xử lý được thành công và lỗi. |
| Security behavior | link chỉ xuất hiện khi được phép | Quyền và khả năng thao tác không bị mở rộng ngoài ý muốn. |

Không nên chỉ so sánh toàn bộ JSON response byte-for-byte. Host, port, thứ tự thuộc tính hoặc một link bổ sung có thể thay đổi mà không phá vỡ hợp đồng. Kiểm tra từng semantics quan trọng sẽ bền vững hơn snapshot tuyệt đối.

## 3. Phân loại thay đổi an toàn và thay đổi phá vỡ

Các ví dụ sau là hướng dẫn chung; cần đối chiếu với cách client sử dụng API:

| Thay đổi | Đánh giá thường gặp | Lý do |
| --- | --- | --- |
| Thêm relation mới | Tương thích nếu client bỏ qua relation chưa biết | Client cũ vẫn có thể theo các relation đã biết. |
| Thêm trường tùy chọn | Thường tương thích | Client cũ không cần đọc trường mới. |
| Thêm embedded relation mới | Thường tương thích với client bỏ qua relation lạ | Client vẫn đọc relation cũ. |
| Đổi tên relation đang dùng | Phá vỡ tương thích | Client không tìm thấy relation cũ. |
| Xóa relation đang dùng | Phá vỡ tương thích | Khả năng điều hướng bị mất. |
| Đổi kiểu field | Phá vỡ tương thích | Client deserialize hoặc xử lý giá trị sai. |
| Làm field bắt buộc thành null | Có thể phá vỡ | Client có thể giả định field luôn có giá trị. |
| Thêm giá trị enum | Có thể phá vỡ | Client strict có thể từ chối giá trị chưa biết. |
| Đổi HTTP method của affordance | Phá vỡ tương thích | Client gửi request theo method cũ. |
| Thay đổi ý nghĩa của relation | Phá vỡ tương thích | Client theo link nhưng nhận tài nguyên khác semantics. |
| Đổi URI đích nhưng giữ relation | Thường tương thích với client hypermedia | Client theo href do server cung cấp. |

Đừng mặc định thêm trường hoặc relation luôn an toàn. Client có thể dùng JSON schema strict, exhaustive switch cho enum hoặc kiểm tra chính xác số lượng link. Hợp đồng consumer và kiểm thử thực tế mới xác định được mức tương thích.

## 4. Giữ ổn định relation khi URI thay đổi

Một lợi ích quan trọng của hypermedia là client tìm tài nguyên theo relation và dùng href được server cung cấp. Server có thể chuyển mapping từ /orders/{id} sang /api/order-records/{id} mà vẫn giữ relation self hoặc orders.

Ví dụ response trước khi đổi route:

~~~json
{
  "_links": {
    "self": { "href": "https://api.example.test/orders/o-42" },
    "orders": { "href": "https://api.example.test/orders" }
  }
}
~~~

Response sau khi đổi route:

~~~json
{
  "_links": {
    "self": { "href": "https://api.example.test/api/order-records/o-42" },
    "orders": { "href": "https://api.example.test/api/order-records" }
  }
}
~~~

Client tuân thủ hypermedia vẫn hoạt động nếu nó bắt đầu từ entry point, tìm relation orders và theo self link. Client ghép /orders/{id} từ một ID trong payload sẽ bị ảnh hưởng vì đã phụ thuộc vào routing nội bộ.

Kiểm thử tương thích nên xác nhận relation vẫn được công bố và href mới thực sự truy cập đúng tài nguyên. Không nên yêu cầu URI phải giữ nguyên nếu hợp đồng chỉ cam kết relation và semantics của target.

## 5. Kiểm thử relation và semantics thay vì chuỗi URL cố định

Một test provider-side có thể xác nhận self và customer relation tồn tại:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderCompatibilityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void keepsRequiredRelationsInOrderRepresentation() throws Exception {
        mockMvc.perform(get("/orders/{id}", "o-42")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.customer.href").exists());
    }
}
~~~

Test trên không cố định host, port hoặc toàn bộ path của href. Nếu contract yêu cầu link customer phải trỏ tới customer resource, hãy lấy href từ response, theo nó bằng HTTP client và xác nhận response đích có self link cùng định danh khách hàng mong đợi.

Khi relation là extension relation có URI tuyệt đối hoặc CURIE, kiểm tra đúng relation đã công bố theo dạng serialize thực tế. Đừng đổi semantics của relation cũ chỉ vì muốn đặt tên khác cho dễ đọc.

## 6. Kiểm thử client thực sự theo link

Kiểm tra href tồn tại chưa đủ. Link có thể trỏ tới route không còn hoạt động hoặc route trả sai resource. Một contract test nên theo link:

1. GET entry point hoặc resource cha.
2. Đọc relation cần dùng từ HAL response.
3. Lấy href từ link object.
4. Gửi request tới href đó.
5. Xác nhận status, media type và semantics của resource đích.

Ví dụ với MockMvc, có thể parse response body thành JsonNode, lấy _links.customer.href, chuyển URI thành path và query của ứng dụng test rồi gửi request tiếp theo. Cách làm này xác nhận client có thể điều hướng theo link mà server cung cấp.

Với link tuyệt đối, MockMvc cần request path cục bộ; nếu cần kiểm tra scheme, host, gateway hoặc reverse proxy, hãy chạy test tích hợp qua HTTP client tới ứng dụng trong môi trường test tương ứng.

## 7. Kiểm thử khả năng bỏ qua relation và field chưa biết

Một client hypermedia có khả năng mở rộng nên bỏ qua relation mà nó không hiểu, đồng thời tiếp tục dùng relation đã biết. Tương tự, DTO client có thể bỏ qua field mới nếu hợp đồng cho phép.

Ví dụ response v2 có thêm relation reports:

~~~json
{
  "_links": {
    "self": { "href": "/api/orders" },
    "next": { "href": "/api/orders?page=1" },
    "reports": { "href": "/api/reports/orders" }
  }
}
~~~

Client cũ chỉ cần orders và next vẫn nên điều hướng được. Trong consumer test, kiểm tra client tìm relation cần thiết và không thất bại chỉ vì response có relation bổ sung.

Với payload, có thể cấu hình DTO Jackson bỏ qua field không biết nếu đó là chính sách tương thích của client:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderSummary(
        String id,
        String status
) {}
~~~

Hãy xác nhận cấu hình Jackson thực tế của ứng dụng; annotation hoặc cấu hình ObjectMapper có thể khác nhau giữa client. Không nên buộc server giữ nguyên mọi field chỉ vì một client deserialize quá strict, trừ khi đó là hợp đồng đã cam kết.

## 8. Kiểm thử field, kiểu dữ liệu và nullability

Các thay đổi payload có thể làm client cũ hỏng dù link vẫn đúng. Kiểm thử cần xác nhận:

- Field bắt buộc vẫn có mặt.
- Kiểu JSON vẫn tương thích, ví dụ number không bị đổi thành string.
- Field không đột ngột chuyển từ non-null sang null.
- Đơn vị và semantics của giá trị không thay đổi, ví dụ total vẫn là số tiền cùng currency.
- Field mới là tùy chọn nếu client cũ không thể cung cấp hoặc hiểu nó.
- Field bị deprecated vẫn được giữ trong giai đoạn chuyển tiếp đã công bố.

Ví dụ JSONPath:

~~~java
mockMvc.perform(get("/orders/{id}", "o-42")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").isString())
    .andExpect(jsonPath("$.status").isString())
    .andExpect(jsonPath("$.total").isNumber())
    .andExpect(jsonPath("$.currency").isString());
~~~

Nếu contract yêu cầu total luôn có giá trị, hãy kiểm tra nó không null và nằm trong miền hợp lệ. Đừng chỉ kiểm tra field tồn tại vì JSON null vẫn thỏa điều kiện exists trong một số cách assertion.

## 9. Kiểm thử enum và trạng thái mới

Thêm trạng thái enum có thể phá vỡ client dùng switch exhaustive hoặc deserialize enum strict. Ví dụ server thêm ON_HOLD vào OrderStatus. Client cũ có thể không biết cách hiển thị trạng thái đó.

Hãy xác định chính sách:

- Client phải bỏ qua hoặc hiển thị fallback cho trạng thái chưa biết.
- Server phải giữ giá trị cũ trong thời gian tương thích.
- Nếu client không thể hỗ trợ giá trị mới, server có thể cần phiên bản representation mới hoặc một field phân loại ổn định hơn.

Consumer test nên đưa một payload có giá trị enum mới vào bộ giải mã client và xác nhận hành vi fallback theo hợp đồng. Provider test cần xác nhận các trạng thái hiện có không bị đổi nghĩa.

Không đổi một trạng thái cũ thành trạng thái mới chỉ để làm rõ tên gọi nếu client đang dựa vào semantics cũ. Hãy dùng migration/versioning có kiểm soát.

## 10. Kiểm thử embedded relation và collection naming

Tên relation của embedded resource cũng là hợp đồng. Nếu client đọc _embedded.orders, đổi collection relation thành orderRecords có thể phá vỡ client dù các item vẫn giống nhau.

Ví dụ assertion:

~~~java
mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
~~~

Nếu đổi tên DTO hoặc entity, dùng @Relation để giữ itemRelation và collectionRelation ổn định. Khi thay đổi relation là bắt buộc, hãy có giai đoạn công bố relation mới đồng thời duy trì relation cũ nếu serializer và semantics cho phép; sau đó mới loại bỏ theo lịch deprecation.

Kiểm thử cần phân biệt embedded data với association link. Đổi một association từ embedded sang chỉ còn link làm client cũ mất dữ liệu có sẵn trong response, dù URI đích vẫn tồn tại.

## 11. Kiểm thử pagination semantics

Client phân trang có thể phụ thuộc vào nhiều semantics ngoài relation next:

- Page number bắt đầu từ 0 hay 1.
- Size có phải số item tối đa trong trang không.
- Sort mặc định có ổn định không.
- Filter và sort có được giữ trong next/prev links không.
- totalElements và totalPages có ý nghĩa như thế nào.
- Trang cuối hoặc collection rỗng được biểu diễn ra sao.

Nếu server thay đổi page indexing từ 0 sang 1 mà không version hóa, client có thể bỏ qua hoặc lặp trang. Nếu default sort đổi, item có thể đổi thứ tự giữa các request.

Contract test nên xác nhận page metadata và theo link next từ response. Không tự tạo URL page tiếp theo trong test client; hãy dùng relation next và xác nhận query context được giữ.

## 12. Kiểm thử URI template và tên tham số

URI template có thể thay đổi đường dẫn mà không phá vỡ client nếu relation và các biến template vẫn giữ đúng semantics. Tuy nhiên, đổi tên biến từ name sang familyName có thể phá vỡ client đã truyền name.

Ví dụ contract:

~~~json
{
  "_links": {
    "search": {
      "href": "/people/search{?name,page,size}",
      "templated": true
    }
  }
}
~~~

Test cần xác nhận:

- Relation search vẫn có mặt.
- Link vẫn là templated khi contract yêu cầu template.
- Các biến name, page và size vẫn được hỗ trợ.
- Giá trị có ký tự đặc biệt được encode đúng khi mở rộng template.
- Tham số mới được thêm theo cách không làm thay đổi semantics cũ.

Nếu cần đổi tên tham số, có thể duy trì biến cũ trong giai đoạn chuyển tiếp hoặc tạo relation/search template mới. Không đổi tên âm thầm.

## 13. Kiểm thử affordance và hành động

Affordance mô tả thao tác khả dụng, method và metadata input/output. Đây là một phần hợp đồng quan trọng khi client dựa vào affordance để tạo request.

Ví dụ hành động cancel có thể được công bố với method POST. Các thay đổi sau có thể phá vỡ client:

- POST đổi thành DELETE.
- Template input mới trở thành bắt buộc.
- Tên property hoặc kiểu dữ liệu thay đổi.
- Relation cancel bị đổi hoặc biến mất.
- Hành động được công bố khi trạng thái tài nguyên không cho phép.

Test cần xác nhận relation và method vẫn đúng, các property bắt buộc có tên/kiểu phù hợp, và affordance chỉ xuất hiện khi policy cho phép. Với HAL-FORMS, kiểm tra _templates theo template name thực tế của API; với affordance được serialize theo media type khác, dùng assertion phù hợp với media type đó.

Thêm affordance mới thường có thể tương thích với client bỏ qua thao tác chưa biết. Đổi semantics của affordance cũ cần versioning hoặc giai đoạn chuyển tiếp.

## 14. Kiểm thử content negotiation và media type

Client có thể yêu cầu HAL bằng Accept: application/hal+json. Nếu server thay đổi media type hoặc không còn trả HAL, client có thể không đọc được links dù JSON payload vẫn có vẻ tương tự.

Kiểm thử:

- Request với media type được hỗ trợ trả đúng Content-Type.
- Request với media type không hỗ trợ trả status phù hợp như 406 Not Acceptable.
- HAL response vẫn chứa _links và _embedded theo hợp đồng.
- Nếu nhiều representation được trả theo Accept, cache header Vary: Accept được thiết lập phù hợp.
- Vendor-specific media type hoặc profile được tài liệu hóa và được test riêng.

Media type versioning có thể dùng một vendor media type riêng, nhưng Spring HATEOAS không tự định nghĩa chiến lược version cho ứng dụng. Cần cấu hình message converter/content negotiation và test rằng mỗi Accept header đi tới representation đúng.

## 15. Chọn chiến lược versioning

Không có một cách versioning duy nhất phù hợp mọi API. Các lựa chọn thường gặp:

| Chiến lược | Ví dụ | Ưu điểm | Điểm cần kiểm thử |
| --- | --- | --- | --- |
| URI versioning | /v1/orders, /v2/orders | Dễ nhìn và dễ định tuyến. | Link trong từng version phải đi đúng namespace; v1 được giữ trong thời gian cam kết. |
| Media type versioning | Accept: application/vnd.example.orders-v2+json | Tách version khỏi URI tài nguyên. | Content negotiation, Vary và converter. |
| Header versioning | X-API-Version: 2 | URI không đổi. | Header phải được gửi ở mọi request và cache phải phân biệt version. |
| Profile | profile URI mô tả semantics | Mô tả profile của representation. | Profile cần được công bố và hiểu đúng; profile tự nó không tự động định tuyến phiên bản. |

Với hypermedia, entry point có thể được version hóa, nhưng các link được trả về phải tuân theo cùng chính sách version. Không để response v1 bất ngờ dẫn tới endpoint v2 có semantics khác mà không công bố rõ.

## 16. Kiểm thử song song v1 và v2

Khi có thay đổi phá vỡ, có thể duy trì hai contract trong giai đoạn chuyển đổi. Ví dụ v1 dùng status field cũ, v2 bổ sung representation mới. Provider test nên kiểm tra từng version riêng:

~~~java
@Test
void v1KeepsLegacyOrderContract() throws Exception {
    mockMvc.perform(get("/v1/orders/{id}", "o-42")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("PENDING"))
        .andExpect(jsonPath("$._links.self.href").exists());
}

@Test
void v2PublishesNewOrderContract() throws Exception {
    mockMvc.perform(get("/v2/orders/{id}", "o-42")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.state").value("PENDING"))
        .andExpect(jsonPath("$._links.self.href").exists());
}
~~~

Ví dụ minh họa hai URI version riêng. Trong ứng dụng thực tế, v2 có thể giữ cả field status trong giai đoạn chuyển tiếp hoặc dùng DTO/assembler riêng. Không giả định hai version chỉ khác tên field; hãy ghi rõ semantics và link relations của từng version.

Test cần xác nhận v1 không bị thay đổi khi triển khai v2, v2 có contract mới đúng, và root/version entry point dẫn client tới đúng phiên bản.

## 17. Consumer-driven contract testing

Provider test xác nhận server trả response theo contract đã định. Tuy nhiên, chỉ provider biết những gì server dự định công bố; nó không biết mọi giả định của client. Consumer-driven contract testing giúp client mô tả những relation, field, media type và status mà nó thực sự cần.

Quy trình tổng quát:

1. Consumer test mô tả request và phần response client phụ thuộc.
2. Contract được lưu hoặc xuất bản cho provider build.
3. Provider verification chạy contract đó với server implementation.
4. Build thất bại nếu provider không còn đáp ứng contract consumer.
5. Thay đổi contract được review trước khi release.

Có thể dùng Spring Cloud Contract hoặc Pact tùy hệ sinh thái. Đây là công cụ bổ sung, không phải tính năng tự động của Spring HATEOAS. Khi viết contract hypermedia, nên kiểm tra relation và semantics của href thay vì buộc mọi host/path giống hệt fixture.

## 18. Dùng fixture và snapshot một cách có chọn lọc

Lưu một HAL response mẫu có thể giúp phát hiện thay đổi không mong muốn. Tuy nhiên, snapshot toàn bộ response dễ gây nhiễu khi host, port, timestamp, thứ tự link hoặc trường bổ sung thay đổi.

Nếu dùng fixture:

- Chuẩn hóa giá trị động như host, ID ngẫu nhiên và timestamp.
- Kiểm tra các relation bắt buộc thay vì so sánh mọi byte.
- Giữ lại field, type và semantics quan trọng.
- Có test traversal để xác nhận link hoạt động.
- Review thay đổi fixture như một thay đổi hợp đồng, không tự động chấp nhận mọi snapshot mới.

Snapshot phù hợp làm bằng chứng bổ sung; JSONPath assertions và consumer contract thường diễn đạt rõ hơn các yêu cầu tương thích.

## 19. Deprecation và giai đoạn chuyển đổi

Khi cần loại bỏ relation, field hoặc endpoint, hãy có quy trình deprecation:

1. Công bố phần tử sắp bị loại bỏ và replacement relation/field/endpoint.
2. Duy trì phần tử cũ trong khoảng thời gian đã cam kết.
3. Bổ sung telemetry để biết client nào còn sử dụng phần tử cũ nếu có thể.
4. Cập nhật client và contract tests để dùng phần tử mới.
5. Sau thời hạn, loại bỏ phần tử cũ trong version hoặc release đã thông báo.

Link có thể chứa metadata deprecation hoặc trỏ tới tài liệu giải thích thay đổi. Nếu API dùng deprecation link metadata, kiểm thử nó có mặt và trỏ tới tài liệu phù hợp. Đừng chỉ xóa link cũ ngay khi đã thêm link mới; client cũ có thể chưa được cập nhật.

## 20. Ma trận kiểm thử tương thích

Một bộ test thực tế nên bao phủ các chiều sau:

| Chiều kiểm thử | Client cũ với server mới | Client mới với server cũ |
| --- | --- | --- |
| Relation đã biết | Relation cũ vẫn tồn tại hoặc có migration. | Client xử lý trường hợp relation mới chưa có. |
| Field payload | Field cũ giữ tên, kiểu và semantics. | Field mới có fallback hoặc optional. |
| Embedded relation | Relation cũ và cấu trúc item được giữ. | Client chấp nhận thiếu relation mới. |
| URI | Client theo href mới do server trả. | Client không giả định route mới tồn tại. |
| Template | Biến cũ tiếp tục hoạt động. | Client chỉ dùng biến được server công bố. |
| Pagination | next/prev giữ filter và sort. | Client xử lý khi relation next hoặc metadata mới vắng mặt. |
| Affordance | Method và input cũ còn hợp lệ. | Client không gọi affordance chưa được server hỗ trợ. |
| Media type | Server tiếp tục trả media type được cam kết. | Client thương lượng fallback phù hợp. |
| Error contract | Status và error shape cũ không đổi ngoài cam kết. | Client xử lý status mới hoặc lỗi chưa biết. |

Không phải dự án nào cũng cần test mọi ô. Hãy ưu tiên các luồng quan trọng, client đang được hỗ trợ và thay đổi có nguy cơ phá vỡ cao.

## 21. Các lỗi thường gặp

**Chỉ snapshot toàn bộ JSON.** Snapshot có thể quá nhạy với thay đổi không liên quan. Kiểm tra semantics relation, payload và traversal.

**Kiểm tra href cố định thay vì theo link.** Client hypermedia nên dùng href server công bố. Test URI đích bằng traversal.

**Đổi relation cùng lúc refactor tên class.** Giữ relation công khai ổn định bằng cấu hình tường minh và contract test.

**Cho rằng thêm enum value luôn an toàn.** Client strict có thể không xử lý được giá trị mới. Test fallback hoặc version hóa.

**Bỏ qua URI template variable.** Đổi tên biến template có thể làm client không mở rộng được link. Kiểm tra biến và encoding.

**Thay media type mà không kiểm tra converter.** Content negotiation có thể trả 406 hoặc JSON không có hypermedia links.

**Đổi method hoặc input của affordance mà không version hóa.** Client có thể gửi sai request. Test method và template properties.

**Duy trì v1 nhưng để link v1 trỏ sang v2 không tương thích.** Kiểm tra toàn bộ traversal chain trong từng version.

**Xóa phần tử deprecated quá sớm.** Duy trì thời gian chuyển đổi và xác nhận client đã di chuyển.

**Chỉ chạy provider tests.** Bổ sung consumer-driven contracts để phát hiện giả định thực tế của client.

## 22. Bài tập thực hành và tiêu chí hoàn thành

Hãy xây dựng bộ kiểm thử tương thích cho API đơn hàng:

1. Ghi lại contract v1 gồm media type, relation, field, embedded collection, pagination và affordance.
2. Tạo MockMvc provider tests cho các relation và field bắt buộc.
3. Thay đổi URI mapping nhưng giữ relation; xác nhận client theo href mới vẫn truy cập được tài nguyên.
4. Thêm một relation và field mới; xác nhận client cũ vẫn đọc được các phần đã biết.
5. Kiểm thử kiểu dữ liệu, nullability và enum mới theo chính sách client.
6. Kiểm tra embedded relation và self link của từng item.
7. Kiểm tra pagination metadata, sort/filter và URI template variables.
8. Kiểm tra method và input của affordance/HAL-FORMS.
9. Nếu có thay đổi phá vỡ, triển khai v1/v2 song song và kiểm thử cả hai contract.
10. Thêm consumer-driven contract verification bằng Spring Cloud Contract hoặc Pact nếu hệ thống có nhiều client độc lập.
11. Thực hiện deprecation test và xác nhận relation/field cũ được giữ trong giai đoạn chuyển đổi.

Bạn đã nắm được cách kiểm thử tương thích khi có thể xác định đầy đủ hợp đồng hypermedia, phân biệt thay đổi cộng thêm với thay đổi phá vỡ, xác nhận client theo relation thay vì ghép URI, kiểm thử payload và affordance, duy trì version cũ trong giai đoạn chuyển đổi và xác minh contract từ cả phía provider lẫn consumer. Những kiểm thử này giúp server và client tiến hóa độc lập mà vẫn giữ được các luồng tích hợp đã cam kết.

## Tài liệu tham khảo chính thức

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS – Links and link relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.links)
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/)
- [Pact Documentation](https://docs.pact.io/)
