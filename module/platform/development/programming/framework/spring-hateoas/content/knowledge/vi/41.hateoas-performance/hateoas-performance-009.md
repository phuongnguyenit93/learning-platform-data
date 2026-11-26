# Tối ưu response lớn trong Spring HATEOAS

Một response hypermedia lớn có thể chậm dù câu truy vấn chính không phức tạp. Server phải tải dữ liệu, chuyển từng entity thành representation, tạo link cho collection và từng item, áp dụng policy cho affordance, serialize HAL rồi gửi payload qua mạng. Nếu assembler truy cập lazy association hoặc gọi service riêng cho từng item, chi phí còn tăng theo số phần tử.

Tối ưu response lớn cần nhìn toàn bộ đường đi từ database đến client. Mục tiêu là giữ đúng hợp đồng hypermedia trong khi giảm số truy vấn, số lần gọi service, lượng dữ liệu serialize và kích thước truyền tải. Bài này trình bày cách đo lường, giới hạn collection, chọn pagination, dùng DTO projection, tránh N+1, kiểm soát embedded resource và link, tận dụng compression/cache và kiểm thử hiệu năng cho API Spring HATEOAS.

## 1. Response lớn tốn chi phí ở đâu?

Một request GET collection có thể đi qua các bước:

1. Parse query parameter và xác định pageable/filter.
2. Truy vấn database để lấy item và có thể chạy thêm count query.
3. Load association cần thiết cho DTO và link.
4. Chuyển từng item thành EntityModel hoặc representation riêng.
5. Tạo self link, association link và affordance.
6. Đóng gói CollectionModel hoặc PagedModel.
7. Jackson serialize payload, _links, _embedded và page metadata.
8. Nén response nếu server/proxy bật compression.
9. Gửi bytes qua mạng và để client parse representation.

Chỉ giảm thời gian SQL chưa chắc làm response nhanh hơn nếu serializer tạo hàng nghìn link hoặc assembler gây N+1 query. Ngược lại, giảm payload bằng cách bỏ link cần thiết có thể làm client mất khả năng điều hướng. Tối ưu phải dựa trên hợp đồng và số liệu đo.

## 2. Đo trước khi tối ưu

Thu thập ít nhất các số liệu sau cho từng endpoint:

| Số liệu | Điều cần biết |
| --- | --- |
| Response time p50/p95/p99 | Độ trễ điển hình và ở tải cao. |
| Response bytes | Kích thước body trước và sau compression. |
| Số database query | Có truy vấn tăng theo số item không? |
| Database time | Thời gian SQL, count query và thời gian chờ connection. |
| Serialization time | Chi phí chuyển representation thành JSON. |
| CPU và allocation | Chi phí tạo DTO, link, object graph và JSON buffer. |
| Cache hit ratio | Bao nhiêu request được phục vụ từ cache? |
| Error/timeout rate | Có request vượt giới hạn hoặc thất bại không? |

Đo ở cùng điều kiện dữ liệu và tải. Một lần chạy local với vài item không đại diện cho collection có hàng nghìn bản ghi. Ghi rõ số item, kích thước page, filter, sort, media type, compression và trạng thái cache khi so sánh.

Một baseline hữu ích có thể là: 50 item, 500 item và kích thước page tối đa được API cho phép. Nếu thời gian tăng gần tuyến tính với số item, hãy kiểm tra công việc lặp trong assembler. Nếu số query tăng theo item, hãy tìm N+1. Nếu SQL ổn định nhưng response bytes và CPU tăng mạnh, kiểm tra embedded payload, link và serialization.

## 3. Không trả collection không giới hạn

Endpoint trả toàn bộ collection có thể trở thành response rất lớn khi dữ liệu tăng theo thời gian. Giới hạn page size ở server để client không yêu cầu hàng trăm nghìn item trong một request.

Ví dụ controller nhận Pageable:

~~~java
@GetMapping
PagedModel<EntityModel<OrderSummary>> list(
        @PageableDefault(size = 20, sort = "createdAt",
                direction = Sort.Direction.DESC) Pageable pageable) {

    Pageable bounded = PageRequest.of(
            pageable.getPageNumber(),
            Math.min(pageable.getPageSize(), 100),
            pageable.getSort()
    );

    Page<OrderSummary> page = orderQueryService.findPage(bounded);
    return pagedResourcesAssembler.toModel(page, orderAssembler);
}
~~~

Ví dụ minh họa giới hạn size tối đa là 100. Trong ứng dụng thực tế, cần xử lý cả page number âm, sort field không được phép và filter không hợp lệ. Có thể chuẩn hóa pageable ở một resolver/service dùng chung để mọi endpoint tuân thủ cùng chính sách.

Không đặt giới hạn chỉ ở giao diện client. Server phải thực thi giới hạn để bảo vệ database, heap và băng thông.

## 4. Dùng PagedModel để client điều hướng theo trang

PagedModel mang theo page metadata và các relation như self, first, prev, next, last tùy vị trí trang. Client có thể theo link do server công bố thay vì tự ghép URL hoặc đoán số trang.

~~~java
Page<OrderSummary> page =
        orderQueryService.findPage(pageable);

return pagedResourcesAssembler.toModel(page, orderAssembler);
~~~

Với response HAL, cấu trúc thường có dạng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "o-101",
        "status": "PENDING",
        "_links": {
          "self": { "href": "/orders/o-101" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/orders?page=0&size=20" },
    "next": { "href": "/orders?page=1&size=20" }
  },
  "page": {
    "size": 20,
    "totalElements": 245,
    "totalPages": 13,
    "number": 0
  }
}
~~~

Tên relation orders nên được cấu hình ổn định bằng @Relation nếu client phụ thuộc vào tên đó. PagedModel giữ hợp đồng điều hướng rõ ràng và tránh response collection không có giới hạn.

## 5. Cân nhắc count query khi tổng số phần tử rất lớn

Page<T> thường cần tổng số phần tử để tạo totalElements và totalPages. Spring Data có thể chạy count query ngoài query lấy nội dung trang. Với filter phức tạp hoặc bảng lớn, count query đôi khi đắt hơn query lấy page.

Nếu client chỉ cần biết có trang tiếp theo hay không, cân nhắc Slice<T> hoặc cursor/keyset pagination. Slice thường tải thêm một phần tử để xác định có phần tiếp theo mà không cần tính tổng toàn bộ collection.

Không công bố totalPages nếu server không có số tổng chính xác. Chọn representation và page metadata phản ánh đúng thông tin có sẵn. Nếu dùng PagedModel, hãy xác định rõ nguồn total và chi phí count; nếu chỉ cần next/prev, có thể tạo model collection có links phù hợp từ Slice.

## 6. Dùng DTO projection thay vì serialize entity

Không nên đưa JPA entity trực tiếp vào representation rồi để Jackson truy cập toàn bộ object graph. Entity có thể có association lazy, vòng tham chiếu hai chiều và field nội bộ không thuộc API contract.

DTO projection chỉ lấy trường client cần:

~~~java
public record OrderSummary(
        UUID id,
        String orderNumber,
        OrderStatus status,
        String customerName,
        Instant createdAt,
        BigDecimal total
) {}
~~~

Repository có thể dùng constructor projection:

~~~java
@Query("""
    select new com.example.orders.OrderSummary(
        o.id, o.orderNumber, o.status, c.name, o.createdAt, o.total
    )
    from Order o
    join o.customer c
    where o.tenantId = :tenantId
    """)
Page<OrderSummary> findSummaries(
        UUID tenantId,
        Pageable pageable);
~~~

DTO projection giảm số cột được đọc, tránh vô tình serialize association và giúp representation ổn định khi domain model thay đổi. Với Spring Data JPA, kiểm tra SQL thực tế được sinh ra vì projection, sort và provider có thể ảnh hưởng query cuối cùng.

## 7. Tránh N+1 query trong assembler

Một lỗi phổ biến là assembler truy cập lazy association cho từng item:

~~~java
EntityModel<OrderView> toModel(Order order) {
    OrderView view = new OrderView(
            order.getId(),
            order.getCustomer().getName()
    );
    return EntityModel.of(view);
}
~~~

Nếu collection có 100 đơn hàng và customer chưa được load, code trên có thể tạo một query lấy orders và thêm nhiều query lấy customer. Số query tăng theo số item là dấu hiệu N+1.

Giải pháp là lấy dữ liệu cần thiết theo batch hoặc projection trong query:

~~~java
@Query("""
    select new com.example.orders.OrderSummary(
        o.id, o.orderNumber, o.status, c.name, o.createdAt, o.total
    )
    from Order o
    join o.customer c
    where o.tenantId = :tenantId
    """)
Page<OrderSummary> findSummariesWithCustomer(
        UUID tenantId,
        Pageable pageable);
~~~

Assembler chỉ đọc DTO đã có đủ dữ liệu, không kích hoạt thêm truy vấn. Pageable có thể cung cấp sort theo yêu cầu; nếu API cần thứ tự cố định, hãy thêm tiêu chí sort phụ ổn định như ID. Với association to-one, có thể cân nhắc @EntityGraph hoặc fetch join nếu phù hợp. Với collection association và pagination, không fetch join collection một cách tùy tiện vì join có thể nhân bản row, phá ranh giới page hoặc khiến provider phải phân trang trong memory.

## 8. Batch load dữ liệu phục vụ link và affordance

Link có thể phụ thuộc vào trạng thái hoặc quyền thao tác. Nếu assembler gọi service hoặc repository cho từng item để kiểm tra khả năng cancel, một page 100 item có thể tạo thêm 100 lượt truy vấn.

Tránh kiểu xử lý lặp:

~~~java
for (OrderSummary order : orders) {
    boolean canCancel = authorizationService.canCancel(order.id());
    // Thêm hoặc bỏ link theo kết quả.
}
~~~

Thay vào đó, lấy trạng thái cần thiết cho toàn bộ ID trong một truy vấn batch hoặc dùng dữ liệu policy đã được tải cùng projection:

~~~java
Set<UUID> cancellableOrderIds =
        orderPolicyQuery.findCancellableIds(principal, orderIds);

for (OrderSummary order : orders) {
    if (cancellableOrderIds.contains(order.id())) {
        addCancelLink(order);
    }
}
~~~

Đây là phác thảo về batch policy lookup. Quyết định quyền vẫn phải được kiểm tra lại ở endpoint khi client thực hiện thao tác. Batch lookup chỉ tối ưu việc dựng representation, không thay thế authorization lúc ghi.

## 9. Giữ assembler nhẹ và không gọi dịch vụ từ xa

Assembler nên tập trung chuyển dữ liệu đã chuẩn bị thành representation và link. Không gọi payment service, inventory service hoặc HTTP API khác cho từng item trong toModel.

Nếu cần dữ liệu từ service khác, hãy:

- Lấy theo batch nếu service hỗ trợ bulk endpoint.
- Dùng read model hoặc projection đã đồng bộ nếu nghiệp vụ cho phép.
- Đặt timeout và giới hạn số dependency call.
- Cache dữ liệu tham chiếu phù hợp với độ mới cần thiết.
- Tách trạng thái chưa biết khỏi trạng thái được phép; không tạo link theo giả định khi dependency timeout.

Không che giấu lỗi dependency bằng cách công bố affordance sai. Khi không xác định được hành động có khả dụng hay không, API cần có chính sách rõ ràng, ví dụ bỏ link và ghi nhận lỗi quan sát được.

## 10. Chỉ nhúng dữ liệu client thực sự cần

_embedded giúp client giảm số request, nhưng embedded payload lớn có thể làm response phình nhanh. Một đơn hàng có thể có hàng trăm dòng sản phẩm, lịch sử thay đổi, thanh toán và địa chỉ. Nhúng toàn bộ các quan hệ đó vào collection orders thường tạo response quá lớn.

Chọn mức embedded theo use case:

| Mức representation | Nội dung | Khi phù hợp |
| --- | --- | --- |
| Summary | ID, trạng thái, tổng tiền và self link | Danh sách hoặc màn hình tổng quan. |
| Detail | Thông tin đơn và một số association cần thiết | Trang chi tiết một đơn. |
| Expanded | Nhiều association, lịch sử hoặc dữ liệu liên quan | Client yêu cầu rõ và có giới hạn. |

Không mặc định nhúng sâu nhiều tầng. Có thể trả link items, customer hoặc payments để client chỉ tải phần cần thiết. Nếu API hỗ trợ query parameter embed/projection, hãy whitelist các expansion được phép và giới hạn độ sâu, số item cùng kích thước tối đa.

## 11. Kiểm soát số lượng link trên mỗi item

Mỗi link có thêm object và chuỗi href trong JSON. Một page 100 item, mỗi item có 10 link, có thể tạo hàng nghìn link. Chỉ công bố những relation cần cho client điều hướng trong use case hiện tại.

Ví dụ summary representation có thể chỉ cần:

- self để mở chi tiết.
- Một relation thao tác như cancel nếu policy cho phép.
- Một relation tới association thường dùng nếu client cần.

Không thêm link chỉ để phản ánh mọi method của controller. Hypermedia mô tả khả năng và quan hệ có ý nghĩa với client; nó không phải danh sách API nội bộ.

Không xóa relation bắt buộc chỉ để giảm vài byte. Hãy đo payload và xác định relation nào thực sự không được client dùng trước khi thay đổi contract.

## 12. Tạo link hiệu quả trong assembler

Dùng RepresentationModelAssembler để thống nhất cách tạo item model:

~~~java
@Component
class OrderAssembler
        implements RepresentationModelAssembler<OrderSummary,
                EntityModel<OrderSummary>> {

    @Override
    public EntityModel<OrderSummary> toModel(OrderSummary order) {
        return EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                        .one(order.id()))
                        .withSelfRel()
        );
    }
}
~~~

Assembler nhận DTO đã có dữ liệu cần thiết và chỉ xây representation. Không truy cập repository trong toModel, không gọi findById cho mỗi item và không thực hiện remote call trong quá trình tạo link.

methodOn tạo controller method invocation proxy để Spring HATEOAS suy ra mapping; nó không phải lời gọi HTTP tới controller. Dù vậy, method dùng để dựng link nên là method mapping thuần, không chứa logic nghiệp vụ có side effect.

## 13. Affordance chỉ nên xuất hiện khi có ích

Affordance có thể mô tả method, input và output của hành động. Nó hữu ích khi client cần khám phá form hoặc thao tác tiếp theo, nhưng metadata affordance làm representation lớn hơn và có thể cần thêm công việc xây dựng.

Chỉ thêm affordance cho hành động mà client của representation đó có thể cần. Ví dụ collection summary có thể công bố link tới chi tiết và affordance tạo đơn ở cấp collection; từng item chỉ có affordance hủy nếu trạng thái và quyền cho phép.

Không thêm cùng một metadata lớn vào mọi item nếu client chỉ cần một entry point chung. Đưa action ở cấp collection khi semantics là thao tác trên collection, và ở cấp item khi thao tác áp dụng cho item cụ thể.

## 14. Không serialize entity graph sâu

Serialize trực tiếp entity graph có thể gây:

- Lazy loading ngoài dự kiến.
- N+1 query.
- Vòng tham chiếu giữa hai chiều association.
- Payload chứa field nội bộ hoặc dữ liệu không dành cho client.
- Bộ nhớ tăng do toàn bộ graph được giữ trong lúc serialize.

DTO projection và assembler giúp kiểm soát chính xác dữ liệu đi vào response. Không dùng JsonIgnore để che mọi vấn đề entity graph nếu API cần một contract rõ ràng; hãy tạo model response riêng.

## 15. Giảm kích thước payload JSON

Một số cách giảm bytes mà vẫn giữ semantics:

- Dùng tên field và payload summary phù hợp, không lặp thông tin đã có trong relation.
- Không nhúng association lớn nếu client có thể theo link.
- Không đưa null/default field nếu contract cho phép bỏ qua.
- Không lặp metadata giống nhau trong từng item nếu có thể đặt ở cấp collection.
- Giới hạn page size và độ sâu embedded.
- Tránh mô tả affordance lặp lại khi relation cấp cha đã đủ.

Không rút gọn tên relation hoặc đổi cấu trúc JSON chỉ để tiết kiệm payload nếu việc đó làm client khó hiểu hoặc phá vỡ hợp đồng. Đo kích thước response trước và sau mỗi thay đổi.

## 16. Bật HTTP compression

HAL JSON thường chứa nhiều key lặp lại như _links, self, href, _embedded và tên field. gzip hoặc Brotli ở server/proxy có thể giảm đáng kể bytes truyền tải.

Ví dụ cấu hình Spring Boot:

~~~yaml
server:
  compression:
    enabled: true
    mime-types: application/json,application/hal+json,application/problem+json
    min-response-size: 2KB
~~~

Kiểm tra phiên bản Spring Boot và cấu hình server thực tế vì compression có thể được thực hiện ở embedded server hoặc reverse proxy. Client gửi Accept-Encoding: gzip (hoặc encoding được hỗ trợ), server trả Content-Encoding tương ứng. Đo cả bytes nén và thời gian CPU để tránh nén response rất nhỏ hoặc làm CPU trở thành bottleneck.

## 17. Dùng cache cho collection ít thay đổi

Nếu cùng một truy vấn pagination được gọi lặp lại, cache có thể giảm truy vấn và serialize. Cache key cần gồm page, size, sort, filter và phạm vi tenant/security nếu dữ liệu khác nhau theo ngữ cảnh.

Với response hypermedia, cân nhắc cache page DTO rồi dựng link theo request hiện tại. Nếu cache nguyên PagedModel, phải tính cả host/context path, media type, locale và affordance theo quyền vào cache key hoặc dùng chính sách private/no-store phù hợp.

Mutation tạo, sửa hoặc xóa item có thể làm thay đổi nhiều trang, tổng số phần tử và next/prev links. Invalidate hoặc version hóa cache sau khi transaction commit. Không dùng cache chung cho representation chứa action link theo quyền người dùng.

## 18. Streaming có phù hợp với HAL collection không?

HAL là một JSON document có cấu trúc: object ngoài chứa _links, _embedded, page metadata và các member khác. Để trả một document hợp lệ, serializer phải tạo đúng cấu trúc và client phải parse document tương ứng. Streaming từng item không tự động làm response HAL nhỏ hơn hoặc cho phép client xử lý từng record như NDJSON.

Nếu cần export hàng trăm nghìn bản ghi, hãy cân nhắc một endpoint export riêng dùng định dạng phù hợp như CSV, NDJSON hoặc file bất đồng bộ. Endpoint hypermedia có thể công bố link export để client khởi tạo job, theo dõi trạng thái và tải file khi sẵn sàng. Không biến một HAL collection khổng lồ thành cơ chế export dữ liệu.

## 19. Quan sát chi phí serialize và link generation

Đặt metric hoặc tracing span quanh các giai đoạn quan trọng:

- Query page và count.
- Load association/batch policy.
- Assembler mapping.
- Link/affordance generation nếu chi phí đáng kể.
- JSON serialization.
- Response bytes.

Không log toàn bộ response body ở production chỉ để đo hiệu năng. Log payload lớn có thể tăng chi phí I/O, lưu PII và làm méo số liệu. Dùng metric về byte count, số item, số link và thời gian xử lý.

Nếu số link tăng đột biến sau một lần thay đổi assembler, metric số relation trên response giúp phát hiện. Nếu response bytes tăng nhưng số item không đổi, hãy kiểm tra field mới hoặc embedded association vừa được thêm.

## 20. Kiểm thử không có N+1 query

Một integration test có thể tạo page gồm nhiều item, gọi endpoint rồi kiểm tra số query không tăng tuyến tính theo item count. Có thể dùng Hibernate statistics trong test profile hoặc datasource proxy để đếm query.

Ví dụ ý tưởng:

~~~java
Statistics statistics = entityManagerFactory
        .unwrap(SessionFactory.class)
        .getStatistics();
statistics.clear();

mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "50")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk());

assertThat(statistics.getPrepareStatementCount())
        .isLessThanOrEqualTo(3);
~~~

Ngưỡng 3 chỉ là ví dụ cho một query page, một count query và một query bổ sung đã biết. Hãy xác định ngưỡng dựa trên implementation và test data của dự án. Tắt hoặc kiểm soát query khởi tạo fixture trước khi reset statistics; không dùng assertion quá cứng nếu framework thêm query nền không liên quan.

Quan trọng là chạy cùng test với page size nhỏ và lớn để xác nhận số query gần như không tăng theo số item. Nếu query count tăng từ 3 lên 53 khi page tăng từ 10 lên 50, hãy tìm lazy association hoặc policy lookup trong vòng lặp.

## 21. Kiểm thử payload size và link count

MockMvc có thể đo body size:

~~~java
MvcResult result = mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "50")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andReturn();

byte[] body = result.getResponse().getContentAsByteArray();
assertThat(body.length).isLessThan(250_000);
~~~

Giới hạn 250 KB chỉ là ngưỡng ví dụ. Chọn budget theo loại client, mạng và payload nghiệp vụ. Với response compressed, đo thêm kích thước truyền tải ở tầng HTTP/proxy vì MockMvc có thể không đi qua compression filter giống production.

Có thể parse JSON để đếm item trong _embedded.orders, số relation ở cấp collection và số link trung bình trên mỗi item. Test không nên phụ thuộc thứ tự JSON object, nhưng có thể kiểm tra các relation bắt buộc và giới hạn số lượng expansion.

## 22. Kiểm thử pagination links và giới hạn page size

Đảm bảo page size lớn bị giới hạn ở server và links phản ánh size hiệu lực:

~~~java
mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "10000")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.size").value(100))
    .andExpect(jsonPath("$._links.self.href",
            containsString("size=100")));
~~~

Test giả định API giới hạn tối đa 100 và link self giữ query parameter đã chuẩn hóa. Nếu contract của ứng dụng trả lỗi cho size vượt giới hạn thay vì clamp, hãy kiểm thử status và error representation theo chính sách đó.

Theo link next từ response và xác nhận page tiếp theo có đúng filter/sort. Không tự ghép URL trong client test vì mục tiêu là xác minh hypermedia navigation.

## 23. Kiểm thử embedded expansion có giới hạn

Nếu API hỗ trợ embed=items,customer, hãy test:

- Chỉ relation nằm trong allowlist được nhúng.
- Expansion không hợp lệ trả lỗi hoặc bị bỏ qua theo contract.
- Số tầng embedded không vượt quá giới hạn.
- Số item của embedded collection có giới hạn hoặc có pagination riêng.
- Authorization được áp dụng cho dữ liệu embedded giống như endpoint độc lập.
- Kích thước response nằm trong budget khi expansion được bật.

Không cho client truyền tên class, property path tùy ý hoặc biểu thức query để quyết định dữ liệu serialize. Expansion phải được ánh xạ qua danh sách quan hệ được API công bố.

## 24. Các lỗi thường gặp khi tối ưu response lớn

**Chỉ đo SQL.** Đo cả assembler, link generation, serialization, payload bytes và network.

**Trả collection không giới hạn.** Đặt page size tối đa ở server và cung cấp pagination links.

**Assembler truy cập lazy association.** Dùng DTO projection, EntityGraph phù hợp hoặc batch loading.

**Gọi service cho từng item.** Gom dữ liệu theo batch và tránh remote call trong toModel.

**Fetch join collection cùng pagination.** Có thể làm nhân bản row hoặc phân trang trong memory; kiểm tra query plan và dùng chiến lược phù hợp.

**Nhúng mọi association.** Chỉ embed dữ liệu cần cho use case; cung cấp relation để tải phần còn lại.

**Tạo quá nhiều link và affordance.** Chỉ công bố khả năng hữu ích và đúng policy.

**Cache PagedModel cá nhân hóa dùng chung.** Tách security scope hoặc dựng controls theo request; không để lộ action link.

**Dùng streaming cho HAL collection khổng lồ.** Tạo export endpoint với định dạng phù hợp và link theo dõi/tải kết quả.

**Đặt ngưỡng performance test tùy tiện.** Dựa trên baseline, page size và điều kiện test ổn định.

## 25. Bài tập thực hành và tiêu chí hoàn thành

Hãy tối ưu endpoint GET /orders có collection lớn:

1. Đo baseline với page size 20, 50 và 100: p95, response bytes, query count và thời gian serialize.
2. Thêm giới hạn page size tối đa ở server.
3. Dùng PagedModel và xác nhận self/next/prev links giữ filter/sort.
4. Chuyển entity response sang DTO projection chỉ lấy trường cần thiết.
5. Kiểm tra SQL và loại bỏ N+1 trong assembler.
6. Batch load dữ liệu phục vụ security-sensitive link hoặc affordance.
7. Giảm embedded depth và chỉ công bố relation cần thiết.
8. Kiểm soát số link và affordance trên collection/item.
9. Bật compression và so sánh bytes truyền tải cùng CPU cost.
10. Cân nhắc cache DTO page, ETag và invalidation theo collection mutation.
11. Viết integration test xác nhận query count không tăng tuyến tính theo item count.
12. Đặt budget response size và test pagination/embedded expansion.
13. Nếu cần export khối lượng lớn, công bố export workflow riêng thay vì trả một HAL collection không giới hạn.

Bạn đã nắm được cách tối ưu response lớn khi có thể đo đúng bottleneck, giới hạn kích thước trang, tránh N+1 và remote call trong assembler, chỉ nhúng dữ liệu cần thiết, tạo link theo use case, giảm bytes truyền tải và kiểm thử query count/payload budget. Một response nhanh vẫn phải giữ nguyên semantics của relation, affordance, pagination và authorization mà client dựa vào.

## Tài liệu tham khảo chính thức

- [Spring HATEOAS Reference Documentation – Server support and paged resources](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.paged-resources)
- [Spring Data Commons – Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [Spring Data JPA – Query Methods and Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Hibernate ORM – Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Spring Boot – HTTP Response Compression](https://docs.spring.io/spring-boot/reference/how-to/webserver.html#howto.webserver.configure-response-compression)
