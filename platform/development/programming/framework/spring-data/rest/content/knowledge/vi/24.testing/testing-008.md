# Kiểm tra search, chuyển đổi tham số, phân trang và sắp xếp trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể:

- Khám phá search resource và gọi query method được Spring Data REST export.
- Kiểm tra việc chuyển query parameter từ chuỗi URL sang kiểu Java.
- Kiểm tra phân trang bằng page, size và metadata của Page.
- Kiểm tra sắp xếp một hoặc nhiều thuộc tính bằng sort.
- Viết integration test dùng MockMvc để xác nhận contract HTTP thực tế của repository resource.
- Phân biệt lỗi của query, conversion, paging và sorting để tìm đúng nguyên nhân.

## 1. Phạm vi kiểm thử

Spring Data REST xuất bản repository thành các HTTP resource. Bên cạnh collection và item resource, repository có query method được export sẽ có search resource:

- Collection: GET /people
- Search index: GET /people/search
- Query method: GET /people/search/by-status

Search index trả về các liên kết đến query method resource. Query method resource thực thi method tương ứng trên repository và trả kết quả. Search và query method resources là resource chỉ đọc, vì vậy kiểm thử chủ yếu dùng GET.

Một query method có thể nhận tham số thông thường, ví dụ String, Long, Boolean, enum hoặc LocalDate. Spring chuyển giá trị chuỗi trong query string sang kiểu Java phù hợp trước khi gọi repository method. Nếu method nhận Pageable hoặc Sort, Spring Data REST còn chuyển các query parameter page, size và sort thành thông tin phân trang/sắp xếp.

Nên kiểm tra từng lớp hành vi riêng:
1. Search index có công bố liên kết đúng không?
2. Query parameter có được bind và convert đúng không?
3. Repository trả đúng tập kết quả không?
4. Page metadata và các liên kết điều hướng có đúng không?
5. Thứ tự kết quả có khớp sort directives không?

## 2. Chuẩn bị repository có query method

Giả sử ứng dụng quản lý Order. Entity có state và priority; repository cần hỗ trợ truy vấn theo state, phân trang và sắp xếp.

    public enum OrderState {
        OPEN,
        IN_PROGRESS,
        CLOSED
    }

Repository minh họa:

    import org.springframework.data.domain.Page;
    import org.springframework.data.domain.Pageable;
    import org.springframework.data.jpa.repository.JpaRepository;
    import org.springframework.data.repository.query.Param;
    import org.springframework.data.rest.core.annotation.RepositoryRestResource;
    import org.springframework.data.rest.core.annotation.RestResource;

    @RepositoryRestResource(
        path = "orders",
        collectionResourceRel = "orders"
    )
    public interface OrderRepository
            extends JpaRepository<Order, Long> {

        @RestResource(path = "by-state", rel = "by-state")
        Page<Order> findByState(
            @Param("state") OrderState state,
            Pageable pageable
        );
    }

Với cấu hình trên, Spring Data REST có thể công bố query resource tại:

    GET /orders/search/by-state?state=IN_PROGRESS

@RepositoryRestResource đặt collection path và relation. @RestResource đặt path/relation cho query method. @Param xác định tên query parameter mà client phải gửi.

JpaRepository cung cấp các thao tác CRUD, paging và sorting. Nếu dùng repository interface khác, hãy bảo đảm nó có các method cần thiết. Với query method cần phân trang, tham số Pageable phải có mặt và kiểu kết quả nên là Page hoặc Slice để framework có thể trả metadata phân trang tương ứng.

## 3. Kiểm tra search resource

Trước khi gọi một query cụ thể, hãy kiểm tra search index có công bố query method hay không.

Ví dụ:

    curl -i       -H "Accept: application/hal+json"       http://localhost:8080/orders/search

Response HAL sẽ chứa _links. Tìm relation by-state và kiểm tra href hoặc URI template của nó. Nếu query method nhận tham số, link có thể biểu diễn tham số đó như một biến template.

Với MockMvc:

    @Test
    void searchIndexExposesByStateQuery() throws Exception {
        mockMvc.perform(get("/orders/search")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.by-state").exists());
    }

Nếu liên kết không xuất hiện, hãy kiểm tra:
- Repository có được Spring Data REST export không.
- Query method có được Spring Data nhận diện không.
- @RestResource(exported = false) có đang ẩn method không.
- Repository detection strategy hoặc @RepositoryRestResource có giới hạn exposure không.
- Path và rel có đúng với cấu hình thực tế không.

Search index có link là bằng chứng method được công bố. Nó chưa chứng minh query chạy đúng; cần gọi query method resource và kiểm tra dữ liệu trả về.

## 4. Kiểm tra chuyển đổi query parameter

Query parameter trong URL luôn được truyền dưới dạng text. Spring MVC và Spring Data REST dùng ConversionService để chuyển text thành kiểu Java của tham số repository.

Các kiểu thường gặp:

| Query parameter | Kiểu Java | Ví dụ |
|---|---|---|
| page | int | page=0 |
| size | int | size=10 |
| enabled | boolean | enabled=true |
| id | Long | id=42 |
| createdAfter | LocalDate | createdAfter=2026-01-01 |
| state | enum | state=IN_PROGRESS |

Ví dụ query method:

    Page<Order> findByState(
        @Param("state") OrderState state,
        Pageable pageable
    );

Request:

    GET /orders/search/by-state?state=IN_PROGRESS

Spring chuyển chuỗi IN_PROGRESS thành OrderState.IN_PROGRESS trước khi thực thi method.

### Đăng ký converter tùy chỉnh

Khi contract URL dùng giá trị thân thiện với client nhưng không trùng tên enum, có thể đăng ký Converter. Ví dụ client muốn gửi state=in-progress, trong khi enum có hằng IN_PROGRESS.

    import java.util.Locale;

    import org.springframework.core.convert.converter.Converter;

    public final class StringToOrderStateConverter
            implements Converter<String, OrderState> {

        @Override
        public OrderState convert(String source) {
            if (source == null || source.isBlank()) {
                throw new IllegalArgumentException(
                    "state must not be blank");
            }

            String normalized = source.trim()
                .replace('-', '_')
                .toUpperCase(Locale.ROOT);

            return OrderState.valueOf(normalized);
        }
    }

Đăng ký converter với Spring Data REST:

    import org.springframework.context.annotation.Configuration;
    import org.springframework.core.convert.support.ConfigurableConversionService;
    import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

    @Configuration
    public class RepositoryRestConfiguration
            implements RepositoryRestConfigurer {

        @Override
        public void configureConversionService(
                ConfigurableConversionService conversionService) {
            conversionService.addConverter(
                new StringToOrderStateConverter());
        }
    }

Khi đó request sau có thể được convert thành OrderState.IN_PROGRESS:

    GET /orders/search/by-state?state=in-progress

Chỉ thêm converter vào ConversionService được Spring Data REST cấu hình. Không tạo một ConversionService riêng rồi kỳ vọng framework tự dùng nó. Converter nên từ chối giá trị không hợp lệ với thông báo rõ ràng; không âm thầm trả về một enum mặc định vì điều đó có thể khiến query trả kết quả sai.

### Kiểm tra conversion bằng HTTP

Một unit test cho converter chỉ chứng minh logic chuyển đổi của class. Integration test qua endpoint mới chứng minh Spring Data REST đã đăng ký và thực sự sử dụng converter đó.

    @Test
    void convertsFriendlyStateParameter() throws Exception {
        mockMvc.perform(get("/orders/search/by-state")
                .param("state", "in-progress")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.totalElements").value(3));
    }

Giả sử dữ liệu kiểm thử có đúng ba Order với state IN_PROGRESS. Nếu converter không được đăng ký, query string có thể không chuyển được sang enum và request sẽ thất bại thay vì trả đúng ba kết quả.

Cũng nên kiểm tra giá trị không hợp lệ:

    @Test
    void rejectsUnknownStateParameter() throws Exception {
        mockMvc.perform(get("/orders/search/by-state")
                .param("state", "unknown-state")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isBadRequest());
    }

Status thực tế có thể chịu ảnh hưởng của exception handling tùy cấu hình ứng dụng. Điều cần xác nhận là giá trị sai bị từ chối và không bị biến thành một trạng thái hợp lệ khác.

## 5. Kiểm tra phân trang

Spring Data REST nhận các query parameter phổ biến:

- page: số thứ tự trang, bắt đầu từ 0; mặc định là 0.
- size: số phần tử tối đa trên một trang; mặc định thường là 20.
- sort: chỉ dẫn sắp xếp.

Ví dụ:

    GET /orders/search/by-state?state=in-progress&page=1&size=2

Với page=1 và size=2, server trả trang thứ hai, gồm tối đa hai phần tử. Nếu repository query trả Page, response HAL có thể chứa metadata:

    {
      "page": {
        "size": 2,
        "totalElements": 5,
        "totalPages": 3,
        "number": 1
      }
    }

Giải thích:
- size là kích thước trang được yêu cầu.
- totalElements là tổng số phần tử phù hợp với query.
- totalPages là tổng số trang.
- number là số trang hiện tại, bắt đầu từ 0.

Spring Data REST cũng cung cấp các liên kết first, prev, self và next phù hợp với vị trí trang hiện tại. Client nên theo các liên kết HAL này thay vì tự ghép URL cho trang kế tiếp.

### Kiểm thử page metadata

Chuẩn bị năm Order có cùng state IN_PROGRESS, sau đó gọi:

    GET /orders/search/by-state?state=in-progress&page=1&size=2

Test:

    @Test
    void returnsRequestedPageAndMetadata() throws Exception {
        mockMvc.perform(get("/orders/search/by-state")
                .param("state", "in-progress")
                .param("page", "1")
                .param("size", "2")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.number").value(1))
            .andExpect(jsonPath("$.page.size").value(2))
            .andExpect(jsonPath("$.page.totalElements").value(5))
            .andExpect(jsonPath("$.page.totalPages").value(3))
            .andExpect(jsonPath("$._links.self").exists());
    }

Các giá trị mong đợi phải khớp dữ liệu fixture. Nếu dữ liệu có thể bị thay đổi bởi test khác, hãy chuẩn bị và dọn dữ liệu trong mỗi test để kết quả xác định.

### Page và Slice khác nhau

- Page cung cấp thông tin tổng số phần tử và tổng số trang; thường cần truy vấn đếm bổ sung tùy repository/datastore.
- Slice cho biết còn trang tiếp theo hay không mà không cần cung cấp đầy đủ tổng số phần tử/trang.
- List không mang metadata phân trang như Page. Nếu query method chỉ trả List, việc có Pageable trong method không đồng nghĩa response sẽ có toàn bộ metadata của Page.

Hãy chọn kiểu trả về theo nhu cầu của client và chi phí truy vấn. Nếu client cần tổng số trang để hiển thị điều hướng, Page phù hợp hơn. Nếu chỉ cần biết còn dữ liệu tiếp theo hay không, Slice có thể tiết kiệm chi phí đếm.

## 6. Kiểm tra sắp xếp

Tham số sort dùng tên property và hướng sắp xếp:

    sort=priority,desc

- priority là tên property của domain model.
- desc là giảm dần.
- asc là tăng dần.

Ví dụ:

    GET /orders/search/by-state?state=in-progress&sort=priority,desc

Để sắp xếp theo nhiều tiêu chí, gửi nhiều tham số sort:

    GET /orders/search/by-state?state=in-progress&sort=priority,desc&sort=id,asc

Trong ví dụ này, priority giảm dần là tiêu chí chính. Nếu nhiều Order có cùng priority, id tăng dần được dùng để phân định thứ tự. Sắp xếp phụ giúp kết quả ổn định khi có các giá trị trùng nhau.

Có thể dùng property path cho thuộc tính lồng nhau, tùy khả năng của datastore và mapping. Không nên giả định có thể sort theo một association chỉ được biểu diễn bằng liên kết resource. Hãy kiểm tra property path thực tế và khả năng sort của repository.

### Kiểm thử thứ tự kết quả

Giả sử năm Order IN_PROGRESS có priority lần lượt 1, 2, 3, 4, 5. Request sort priority giảm dần và id tăng dần:

    GET /orders/search/by-state?state=in-progress&sort=priority,desc&sort=id,asc

Test có thể kiểm tra phần tử đầu tiên:

    @Test
    void sortsByPriorityDescendingThenIdAscending() throws Exception {
        mockMvc.perform(get("/orders/search/by-state")
                .param("state", "in-progress")
                .param("sort", "priority,desc")
                .param("sort", "id,asc")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._embedded.orders[0].priority")
                .value(5));
    }

Để kiểm tra tiêu chí phụ, hãy tạo ít nhất hai bản ghi có cùng priority và xác nhận id của chúng theo thứ tự tăng dần. Chỉ kiểm tra phần tử đầu tiên chưa đủ chứng minh toàn bộ thứ tự khi dữ liệu có giá trị trùng nhau.

## 7. Dùng MockMvc để kiểm thử tích hợp

Để xác nhận search resource, ConversionService, Pageable và Sort phối hợp đúng, hãy kiểm thử ứng dụng Spring Data REST thật trong Spring test context.

Ví dụ cấu hình:

    import org.springframework.beans.factory.annotation.Autowired;
    import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
    import org.springframework.boot.test.context.SpringBootTest;
    import org.springframework.test.web.servlet.MockMvc;

    @SpringBootTest
    @AutoConfigureMockMvc
    class OrderRepositoryRestTests {

        @Autowired
        MockMvc mockMvc;

        @Autowired
        OrderRepository repository;

        // Prepare deterministic repository data before each test.
    }

MockMvc thực thi luồng xử lý Spring MVC mà không cần mở cổng HTTP thật. @SpringBootTest nạp application context để Spring Data REST auto-configuration, repository và RepositoryRestConfigurer được áp dụng. @AutoConfigureMockMvc cung cấp MockMvc để gửi request.

Không nên mặc định dùng @WebMvcTest cho bài kiểm thử này. Đây là slice test tập trung vào Spring MVC controller; nó có thể không nạp đầy đủ repository và Spring Data REST auto-configuration mà endpoint cần. Nếu cố tình dùng slice test, phải import đúng cấu hình và thành phần liên quan; với contract của repository REST, integration test thường dễ đánh giá hơn.

### Chuẩn bị dữ liệu kiểm thử

Ví dụ ý tưởng fixture:

    @BeforeEach
    void prepareData() {
        repository.deleteAll();

        repository.saveAll(List.of(
            new Order(OrderState.IN_PROGRESS, 1),
            new Order(OrderState.IN_PROGRESS, 2),
            new Order(OrderState.IN_PROGRESS, 3),
            new Order(OrderState.IN_PROGRESS, 4),
            new Order(OrderState.IN_PROGRESS, 5),
            new Order(OrderState.CLOSED, 6)
        ));
    }

Constructor trong ví dụ cần được điều chỉnh theo entity thực tế. Điều quan trọng là dữ liệu test phải xác định được số bản ghi theo state và thứ tự priority.

Nếu test dùng database thật hoặc test chạy song song, cần cô lập dữ liệu. Không dựa vào ID cố định nếu chiến lược sinh ID không đảm bảo giá trị giống nhau giữa các lần chạy.

## 8. Kết hợp các hành vi trong một test

Một request có thể kiểm tra chuyển đổi tham số, phân trang và sắp xếp cùng lúc:

    @Test
    void searchesConvertsPaginatesAndSorts() throws Exception {
        mockMvc.perform(get("/orders/search/by-state")
                .param("state", "in-progress")
                .param("page", "1")
                .param("size", "2")
                .param("sort", "priority,desc")
                .param("sort", "id,asc")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.number").value(1))
            .andExpect(jsonPath("$.page.size").value(2))
            .andExpect(jsonPath("$.page.totalElements").value(5))
            .andExpect(jsonPath("$.page.totalPages").value(3))
            .andExpect(jsonPath("$._embedded.orders").isArray())
            .andExpect(jsonPath("$._embedded.orders.length()").value(2));
    }

Test tổng hợp này hữu ích để xác nhận toàn bộ luồng. Tuy nhiên, khi nó thất bại, hãy giữ các test nhỏ riêng cho search link, conversion, paging và sorting. Nhờ vậy ta biết chính xác lớp hành vi nào bị lỗi.

## 9. Kiểm tra HAL links và media type

Spring Data REST thường trả HAL JSON khi client yêu cầu:

    Accept: application/hal+json

Với collection/query result có phân trang, response có thể bao gồm:
- _embedded: các phần tử của trang.
- _links.self: URI của trang hiện tại.
- _links.next: trang tiếp theo nếu còn dữ liệu.
- _links.prev: trang trước nếu đang ở sau trang đầu.
- _links.first và _links.last: liên kết đầu/cuối khi có thể xác định.
- page: metadata của Page.

Không nên kiểm tra cứng toàn bộ JSON response nếu thứ tự property hoặc link có thể thay đổi. Hãy assert các phần tử contract quan trọng: status, content type, page metadata, relation và một vài giá trị đại diện.

Client nên ưu tiên theo link next/prev do server trả về. Điều này giúp client ít phụ thuộc vào cách server tạo URI và các tên query parameter đã cấu hình.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| /search không có link query | Query method không được export hoặc bị ẩn | Kiểm tra repository, @RestResource và exported |
| Query trả 400 | Query parameter không convert được hoặc giá trị không hợp lệ | Kiểm tra @Param, kiểu Java và Converter |
| Query trả kết quả rỗng | Conversion thành công nhưng giá trị không khớp dữ liệu | Kiểm tra enum mapping, fixture và điều kiện query |
| page luôn là 0 | Test không gửi page hoặc tham số bị đổi tên trong RepositoryRestConfiguration | Kiểm tra query string và cấu hình tên parameter |
| size không có tác dụng | Query method không nhận Pageable hoặc repository method không hỗ trợ paging | Dùng Pageable và kiểu trả về Page/Slice phù hợp |
| Không có page metadata | Query method trả List hoặc response không phải paged result | Dùng Page hoặc Slice và kiểm tra response |
| Sort không đổi thứ tự | Sai tên property, sai hướng hoặc sort property không được hỗ trợ | Dùng tên property của domain model và kiểm tra dữ liệu có thứ tự phân biệt |
| Sort nhiều tiêu chí không ổn định | Thiếu tiêu chí phụ khi giá trị tiêu chí chính bị trùng | Thêm sort theo ID hoặc thuộc tính duy nhất |
| Test endpoint trả 404 | Sai base path hoặc repository không được export | Kiểm tra application properties, repository detection và path |
| MockMvc test không thấy Spring Data REST | Test slice không nạp cấu hình repository REST | Dùng @SpringBootTest và @AutoConfigureMockMvc hoặc import đầy đủ cấu hình cần thiết |

## 11. Checklist kiểm thử

- [ ] Search index trả liên kết đến query method được export.
- [ ] Query method dùng đúng path, rel và @Param.
- [ ] Tham số chuỗi được chuyển thành kiểu Java mong muốn.
- [ ] Converter tùy chỉnh được đăng ký trong ConversionService của Spring Data REST.
- [ ] Giá trị query parameter không hợp lệ bị từ chối rõ ràng.
- [ ] page bắt đầu từ 0 và size giới hạn số phần tử trả về.
- [ ] Page metadata phản ánh đúng fixture.
- [ ] Liên kết next/prev xuất hiện đúng theo vị trí trang.
- [ ] Sort asc/desc trả đúng thứ tự.
- [ ] Nhiều sort directives được áp dụng đúng thứ tự ưu tiên.
- [ ] Test kiểm tra response HAL mà không phụ thuộc vào thứ tự JSON không có ý nghĩa.
- [ ] Dữ liệu test được chuẩn bị và cô lập để kết quả lặp lại ổn định.

## Kết luận

Kiểm thử Spring Data REST cần đi qua HTTP resource thực tế. Hãy xác nhận search index công bố query method, query parameter được convert thành kiểu Java đúng, Pageable tạo ra page metadata và các liên kết điều hướng phù hợp, còn Sort tạo ra thứ tự kết quả theo contract. MockMvc kết hợp @SpringBootTest và @AutoConfigureMockMvc là cách thực tế để kiểm tra toàn bộ luồng mà không cần chạy HTTP server riêng.

Giữ các test nhỏ theo từng hành vi và thêm một test tích hợp tổng hợp. Khi test thất bại, có thể phân biệt lỗi export, conversion, query, paging hoặc sorting thay vì chỉ nhìn thấy một response JSON không như mong đợi.

## Tài liệu tham khảo

- Spring Data REST — Repository resources and search/query method resources: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST — Paging and Sorting: https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html
- Spring Data REST — RepositoryRestConfigurer API: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html
- Spring Boot 3.3 — Testing Spring Boot Applications and MockMvc: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Framework — MockMvc: https://docs.spring.io/spring/reference/testing/mockmvc.html
