# Checklist kiểm thử Spring HATEOAS

## Mục tiêu

Checklist này giúp bạn kiểm tra một REST API dùng Spring HATEOAS từ response HTTP đến khả năng điều hướng của client. Nó có thể được dùng khi viết test mới, rà soát endpoint hiện có hoặc chuẩn bị phát hành phiên bản API.

Một endpoint HATEOAS được kiểm thử đầy đủ cần đáp ứng ba điều:

1. Dữ liệu và quy tắc nghiệp vụ trả về đúng.
2. Representation công bố đúng relation, href, URI template và affordance theo hợp đồng.
3. Các link dẫn đến endpoint có thể truy cập và tuân theo chính sách xác thực, phân quyền.

Kiểm thử chỉ xác nhận 200 OK chưa đủ để bảo vệ hợp đồng hypermedia.

## 1. Xác định phạm vi trước khi viết test

Trước tiên, lập danh sách endpoint và khả năng điều hướng mà mỗi endpoint phải công bố. Không phải endpoint nào cũng cần mọi loại link.

| Loại endpoint | Những nội dung cần kiểm tra |
|---|---|
| Chi tiết tài nguyên | Dữ liệu, self, relation đến tài nguyên liên quan, link hành động nếu có |
| Collection | Các phần tử, relation của từng phần tử, link collection |
| Collection phân trang | Metadata trang, link first, prev, self, next, last theo trạng thái |
| Search | URI template, biến tìm kiếm, filter và sort được hỗ trợ |
| Search suggestion | Link gợi ý, giới hạn kết quả, link search trên từng gợi ý |
| Hành động nghiệp vụ | Affordance hoặc action link theo trạng thái, quyền và điều kiện nghiệp vụ |

Với mỗi endpoint, ghi lại media type, relation bắt buộc, biến URI template, trạng thái HTTP dự kiến và các điều kiện khiến link xuất hiện hoặc biến mất. Đây là cơ sở để kiểm thử nhất quán giữa controller, assembler và client.

## 2. Kiểm tra HTTP và media type

Bắt đầu bằng những thuộc tính cơ bản của response:

- [ ] Endpoint trả về đúng status HTTP cho trường hợp thành công.
- [ ] Content-Type tương thích với media type đã công bố, ví dụ application/hal+json.
- [ ] Request có header Accept phù hợp nhận được representation mong muốn.
- [ ] Request có media type không được hỗ trợ nhận phản hồi theo chính sách API, thường là 406 Not Acceptable.
- [ ] Lỗi validation, không tìm thấy tài nguyên và lỗi nghiệp vụ có status cùng cấu trúc lỗi nhất quán.
- [ ] Response không vô tình để lộ stack trace, thông tin nội bộ hoặc dữ liệu không thuộc hợp đồng.

Ví dụ kiểm tra response HAL bằng MockMvc:

~~~java
mockMvc.perform(
        get("/api/orders/{id}", orderId)
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists());
~~~

Test này kiểm tra media type và sự hiện diện của link self. Hãy bổ sung assertion cho dữ liệu nghiệp vụ và các relation bắt buộc của endpoint.

## 3. Kiểm tra cấu trúc representation

Chọn kiểu representation phù hợp với dữ liệu trả về và xác minh cấu trúc JSON sau tuần tự hóa.

- [ ] Tài nguyên đơn được biểu diễn đúng, thường qua EntityModel.
- [ ] Collection được biểu diễn đúng, thường qua CollectionModel hoặc PagedModel.
- [ ] Dữ liệu nghiệp vụ có các trường cần thiết và kiểu dữ liệu đúng.
- [ ] Các link nằm trong _links.
- [ ] Các tài nguyên nhúng, nếu có, nằm trong _embedded và dùng relation đúng.
- [ ] Collection rỗng vẫn có cấu trúc hợp lệ và không gây lỗi tuần tự hóa.
- [ ] Không có trường nội bộ, dữ liệu nhạy cảm hoặc thuộc tính không được phép xuất hiện trong response.
- [ ] Tên relation của phần tử nhúng ổn định theo cấu hình của API.

Tên key trong _embedded có thể phụ thuộc relation provider hoặc cấu hình của ứng dụng. Test nên xác nhận tên relation mà API thực sự công bố, thay vì giả định mọi collection đều có cùng một key.

## 4. Kiểm tra relation và href

Với từng link bắt buộc, kiểm tra cả relation và URI đích.

- [ ] Link self trỏ đến đúng tài nguyên hiện tại.
- [ ] Link đến tài nguyên liên quan chứa đúng định danh.
- [ ] Relation chuẩn dùng đúng tên theo hợp đồng, chẳng hạn self, search hoặc relation điều hướng trang.
- [ ] Relation mở rộng dùng đúng URI đã công bố.
- [ ] Relation không đổi ý nghĩa giữa các endpoint.
- [ ] Href không chứa ID rỗng, ID của tài nguyên khác hoặc query parameter sai.
- [ ] Link không bị trùng lặp ngoài chủ đích.
- [ ] Href phản ánh đúng context path, scheme và host theo cấu hình triển khai.
- [ ] Không có link trỏ đến route đã bị xóa hoặc chưa được triển khai.

Đối với relation mở rộng bằng URI, hãy đọc JSON bằng JsonNode để truy cập key relation đầy đủ. Cách này tránh nhầm relation URI với một thuộc tính JSON thông thường.

~~~java
MvcResult result = mockMvc.perform(
        get("/api/orders/{id}", orderId)
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andReturn();

JsonNode root = objectMapper.readTree(
    result.getResponse().getContentAsString()
);
JsonNode links = root.path("_links");

String customerRelation =
    "https://api.example.com/rels/customer";

assertThat(links.has(customerRelation)).isTrue();

String customerHref = links.path(customerRelation)
    .path("href")
    .asText();

assertThat(customerHref).isNotBlank();
assertThat(customerHref).contains("/api/customers/");
~~~

Ví dụ trên xác nhận relation và href của khách hàng. Hãy thay URI relation bằng định danh mà API của bạn đã công bố.

Không nên hard-code host hoặc port tuyệt đối trong assertion nếu chúng thay đổi theo môi trường test. Có thể kiểm tra path, query parameter và relation; với kiểm thử tích hợp, hãy dùng href nhận được từ response để thực hiện bước điều hướng tiếp theo.

## 5. Kiểm tra URI template

Link có tham số chưa biết trước phải được đánh dấu là template. Hãy xác nhận biến được công bố khớp với tham số mà endpoint thực sự hỗ trợ.

- [ ] Link template có templated: true.
- [ ] Href chứa đúng tên biến, ví dụ q, page, size, sort hoặc category.
- [ ] Không công bố biến mà endpoint không xử lý.
- [ ] Giá trị mặc định và giới hạn của tham số được áp dụng đúng.
- [ ] Giá trị có dấu cách, Unicode, dấu &, dấu + hoặc ký tự đặc biệt được mã hóa đúng khi mở rộng template.
- [ ] Client có thể mở rộng template bằng thư viện URI template phù hợp.
- [ ] Đổi tên query parameter được xem là thay đổi hợp đồng và có test bảo vệ.

Ví dụ kiểm tra link search:

~~~java
mockMvc.perform(
        get("/api/products")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
        .value(containsString("{?q")));
~~~

Nếu endpoint hỗ trợ thêm category, page và size, hãy xác nhận các biến đó cũng xuất hiện trong template. Khi có thể, kiểm thử mở rộng URI bằng một URI template processor thực tế và gọi endpoint bằng URI đã mở rộng.

## 6. Kiểm tra collection và pagination

Với collection phân trang, link điều hướng phụ thuộc vị trí của trang hiện tại.

| Trường hợp | Điều cần xác nhận |
|---|---|
| Trang đầu, còn trang sau | Có self, first, next, last; không có prev |
| Trang giữa | Có self, first, prev, next, last |
| Trang cuối | Có self, first, prev, last; không có next |
| Chỉ có một trang | Link điều hướng phản ánh đúng quy tắc API |
| Collection rỗng | Metadata trang và link được biểu diễn nhất quán |
| Page size thay đổi | Metadata và href phản ánh page size đã yêu cầu |

Các điểm kiểm tra bổ sung:

- [ ] page.number, page.size, page.totalElements và page.totalPages khớp dữ liệu.
- [ ] Link next và prev thay đổi đúng theo trang hiện tại.
- [ ] Link giữ lại filter và sort đang áp dụng.
- [ ] Page size được giới hạn theo chính sách.
- [ ] Trang vượt phạm vi được xử lý theo hợp đồng, ví dụ trả collection rỗng hoặc lỗi đã định nghĩa.
- [ ] Các phần tử trong _embedded có relation và link riêng theo yêu cầu.

Không nên yêu cầu next luôn tồn tại. Sự hiện diện của link phải phản ánh khả năng điều hướng thực tế tại trang hiện tại.

## 7. Kiểm tra sorting, filtering và search suggestion

Với endpoint search và filter:

- [ ] Template chỉ công bố các tham số được hỗ trợ.
- [ ] Giá trị sort hợp lệ tạo thứ tự kết quả đúng.
- [ ] Sort field không hợp lệ được từ chối hoặc chuẩn hóa theo hợp đồng.
- [ ] Filter được giữ lại khi chuyển trang.
- [ ] Kết quả search phù hợp với từ khóa và phạm vi truy cập.
- [ ] Không có kết quả trả về collection hợp lệ.
- [ ] Kết quả suggestion có giới hạn số lượng theo yêu cầu.
- [ ] Từng suggestion có link search với từ khóa đã được điền đúng.
- [ ] Ký tự đặc biệt trong từ khóa không làm hỏng href.
- [ ] Từ khóa quá ngắn, rỗng hoặc quá dài được xử lý theo chính sách API.

Search và suggestions là hai khả năng khác nhau. Hãy kiểm tra relation tương ứng riêng biệt, đồng thời xác nhận link search trên một suggestion dẫn đến truy vấn có giá trị được chọn.

## 8. Kiểm tra affordance và link hành động

Affordance có thể mô tả phương thức HTTP và dữ liệu đầu vào cho hành động. Kiểm thử phải gắn với trạng thái nghiệp vụ và media type mà API sử dụng.

- [ ] Hành động chỉ xuất hiện khi tài nguyên đủ điều kiện.
- [ ] Hành động biến mất khi trạng thái không còn cho phép.
- [ ] Metadata mô tả đúng phương thức HTTP.
- [ ] Kiểu dữ liệu và các trường đầu vào phản ánh endpoint thực tế.
- [ ] Media type được dùng để biểu diễn affordance đúng với cấu hình, ví dụ HAL-FORMS khi API sử dụng định dạng đó.
- [ ] Request thực hiện hành động vẫn được kiểm tra quyền và trạng thái ở server.
- [ ] Client không thể thực hiện hành động trái phép chỉ bằng cách tự tạo request đến href.

Ví dụ, đơn hàng PENDING có thể công bố khả năng hủy. Đơn hàng SHIPPED hoặc CANCELLED không nên công bố affordance hủy nếu nghiệp vụ không cho phép. Dù link bị ẩn, endpoint vẫn phải tự kiểm tra điều kiện khi nhận request.

Với HAL-FORMS, hãy kiểm tra cấu trúc template theo media type đã chọn. Không áp dụng assertion về _templates cho response HAL JSON thông thường nếu API không công bố affordance ở định dạng đó.

## 9. Kiểm tra khả năng theo link đến endpoint đích

Một href hợp lệ về cú pháp vẫn có thể trỏ đến endpoint không hoạt động. Hãy kiểm tra điều hướng ở mức integration test:

- [ ] Link self mở đúng tài nguyên.
- [ ] Link quan hệ mở đúng tài nguyên liên quan.
- [ ] Link collection mở được collection.
- [ ] Link search sau khi mở rộng template trả kết quả đúng.
- [ ] Link hành động dẫn đến endpoint đúng và tạo kết quả nghiệp vụ dự kiến.
- [ ] Link không dẫn đến redirect ngoài dự kiến hoặc route lỗi.
- [ ] Các endpoint đích áp dụng đúng xác thực, phân quyền và validation.

Một cách kiểm thử tốt là lấy href trực tiếp từ response rồi dùng nó cho request tiếp theo trong test. Như vậy, test xác minh chính luồng điều hướng mà client sẽ thực hiện thay vì tự dựng URL từ một quy ước bên ngoài.

## 10. Kiểm tra bảo mật và quyền truy cập

- [ ] Người dùng chưa xác thực không truy cập được tài nguyên cần bảo vệ.
- [ ] Người dùng không có quyền không nhìn thấy hoặc không thể thực hiện hành động trái phép theo chính sách API.
- [ ] Href không làm lộ dữ liệu nhạy cảm qua query parameter.
- [ ] Link theo tenant hoặc người dùng phản ánh đúng phạm vi dữ liệu.
- [ ] Cache không trả representation riêng tư cho người dùng khác.
- [ ] Endpoint đích kiểm tra quyền độc lập với việc link có xuất hiện hay không.
- [ ] Thông báo lỗi không tiết lộ dữ liệu hoặc thông tin nội bộ không cần thiết.

Hãy viết test cho ít nhất một người dùng có quyền và một người dùng không có quyền ở các endpoint quan trọng. Nếu API ẩn relation theo quyền, kiểm tra cả nội dung _links lẫn phản hồi khi người dùng gọi trực tiếp endpoint đích.

## 11. Kiểm tra tiến hóa hợp đồng

Relation và URI template là một phần hợp đồng mà client có thể phụ thuộc. Khi thay đổi API:

- [ ] Relation hiện có giữ nguyên ý nghĩa.
- [ ] Relation mở rộng giữ nguyên URI định danh.
- [ ] Relation mới được bổ sung theo cách client cũ có thể bỏ qua.
- [ ] Không xóa relation mà client hiện tại đang sử dụng nếu chưa có lộ trình chuyển đổi.
- [ ] Thay đổi path mapping không làm href sai.
- [ ] Thay đổi tên query parameter có test và tài liệu cập nhật.
- [ ] Thay đổi media type hoặc cấu trúc embedded có test hợp đồng tương ứng.
- [ ] Client vẫn có thể đi theo các relation quan trọng sau khi nâng cấp server.

Một test hợp đồng có thể lưu lại các relation bắt buộc và cấu trúc quan trọng của response. Khi triển khai thay đổi, test sẽ phát hiện relation bị xóa, đổi tên hoặc trỏ đến URI sai.

## 12. Chọn cấp độ kiểm thử

Không cần dùng một loại test cho mọi vấn đề. Hãy phân bổ theo mục tiêu:

| Cấp độ | Phạm vi phù hợp | Ví dụ |
|---|---|---|
| Unit test assembler | Quy tắc tạo representation và điều kiện thêm link | self, customer, cancel |
| Web layer test | Mapping, status, media type và JSON hypermedia | @WebMvcTest với MockMvc |
| Integration test | Service, repository, serializer và endpoint đích | @SpringBootTest và MockMvc |
| Contract test | Quan hệ và cấu trúc client phụ thuộc | Relation, template, HAL shape |
| Security test | Quyền xem tài nguyên và thực hiện hành động | Người dùng có quyền/không có quyền |

Unit test assembler hữu ích khi logic tạo link có nhiều nhánh. Tuy nhiên, link phụ thuộc mapping Spring MVC nên cần ít nhất một test ở web layer để xác nhận href thực tế. Integration test cần thiết khi muốn chứng minh client có thể đi hết luồng từ link này đến link tiếp theo.

## 13. Checklist trước khi phát hành

Dùng danh sách này như cổng rà soát cuối cùng. Chỉ đánh dấu mục đã được xác nhận bằng test hoặc bằng kiểm tra response thực tế.

- [ ] Status HTTP và media type đúng.
- [ ] Dữ liệu representation đúng và không lộ trường ngoài hợp đồng.
- [ ] Link self trỏ đúng tài nguyên.
- [ ] Tất cả relation bắt buộc xuất hiện đúng tên.
- [ ] Relation mở rộng dùng URI ổn định.
- [ ] Href có ID, path và query parameter chính xác.
- [ ] URI template có templated: true và đủ biến.
- [ ] Collection và pagination có link điều hướng đúng theo trạng thái trang.
- [ ] Search, filter, sort và suggestion được kiểm tra với đầu vào biên.
- [ ] Affordance chỉ xuất hiện khi hành động khả dụng.
- [ ] Endpoint đích của các link có thể truy cập.
- [ ] Xác thực và phân quyền được kiểm tra ở endpoint đích.
- [ ] Cache và dữ liệu riêng tư được xử lý đúng.
- [ ] Hợp đồng relation và media type có test bảo vệ.
- [ ] Các test quan trọng chạy thành công trong pipeline phát hành.

## 14. Bài tập tự đánh giá

Một endpoint GET /api/orders/{id} trả về đơn hàng với link self, customer, items và cancel. Link cancel chỉ có khi đơn hàng đang ở trạng thái PENDING. Endpoint danh sách có phân trang và link search dạng URI template.

Hãy lập bộ test bao gồm:

1. Kiểm tra status và HAL media type của endpoint chi tiết.
2. Kiểm tra relation và href của self, customer, items.
3. Kiểm tra cancel xuất hiện với đơn hàng PENDING và biến mất khi trạng thái không cho phép.
4. Kiểm tra endpoint hủy vẫn từ chối request không đủ quyền hoặc không đủ điều kiện.
5. Kiểm tra link next và prev ở trang đầu, trang giữa và trang cuối.
6. Kiểm tra URI template search có đủ biến và mở rộng được với từ khóa chứa ký tự đặc biệt.
7. Lấy href từ response và theo link để xác nhận endpoint đích hoạt động.

Bài làm đạt yêu cầu khi test bảo vệ cả dữ liệu nghiệp vụ lẫn hợp đồng hypermedia, đồng thời chứng minh các link được công bố có thể sử dụng an toàn.

## Kết luận

Kiểm thử Spring HATEOAS cần xác nhận response đúng về dữ liệu, media type và khả năng điều hướng. Relation phải có ý nghĩa ổn định, href phải trỏ đến endpoint hợp lệ, URI template phải công bố đúng biến, pagination phải phản ánh vị trí trang và affordance phải khớp điều kiện nghiệp vụ.

Hãy kết hợp unit test assembler, MockMvc, integration test, contract test và security test theo rủi ro của từng endpoint. Khi các kiểm tra này được duy trì trong pipeline, nhóm phát triển có thể thay đổi controller và cấu trúc triển khai mà vẫn bảo vệ được hợp đồng hypermedia mà client đang sử dụng.

