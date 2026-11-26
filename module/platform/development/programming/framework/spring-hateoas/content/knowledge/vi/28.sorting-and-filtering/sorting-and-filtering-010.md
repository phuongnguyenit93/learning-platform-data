# Kiểm thử sort và filter trong Spring HATEOAS

API phân trang thường cho phép client sắp xếp và lọc collection bằng query parameter. Ví dụ, client có thể yêu cầu các đơn hàng đang chờ xử lý, thuộc một khách hàng cụ thể, được sắp xếp theo ngày tạo mới nhất. Để hợp đồng hypermedia đáng tin cậy, cần kiểm tra cả kết quả dữ liệu lẫn các link mà Spring HATEOAS công bố trong response.

Một kiểm thử chỉ xác nhận HTTP `200 OK` chưa đủ. Response có thể trả đúng status nhưng thứ tự item sai, filter bị bỏ qua, page metadata không khớp hoặc link `next` làm mất query parameter. Bài học này trình bày cách kiểm thử từ tầng repository tới controller và HAL response, đồng thời kiểm tra sort ổn định, filter kết hợp, đầu vào không hợp lệ và khả năng điều hướng giữa các trang.

## 1. Hợp đồng sort và filter của endpoint

Giả sử API cung cấp endpoint `GET /orders` với các tham số:

```http
GET /orders?status=PENDING&customerId=7&page=0&size=2&sort=createdAt,desc
Accept: application/hal+json
```

Các tham số có ý nghĩa:

| Tham số | Vai trò | Ví dụ |
| --- | --- | --- |
| `status` | Lọc theo trạng thái đơn hàng. | `PENDING` |
| `customerId` | Lọc theo khách hàng sở hữu đơn. | `7` |
| `page` | Chỉ số trang, mặc định bắt đầu từ `0`. | `0` |
| `size` | Số item tối đa trong một trang. | `2` |
| `sort` | Thuộc tính và hướng sắp xếp. | `createdAt,desc` |

Kết quả là một `PagedModel` chứa các item, page metadata và các link như `self`, `next`, `prev`. Kiểm thử cần xác nhận các tham số lọc và sắp xếp thực sự ảnh hưởng tới dữ liệu, đồng thời được giữ trong những link dùng để chuyển trang.

## 2. Kiểm thử ở nhiều tầng

Mỗi tầng kiểm tra một phần trách nhiệm khác nhau:

| Tầng | Công cụ phù hợp | Điều cần xác nhận |
| --- | --- | --- |
| Repository/query | `@DataJpaTest`, Testcontainers hoặc database test | Predicate lọc, sort thực tế và page content đúng. |
| Service | JUnit, Mockito | Kết hợp filter, chuẩn hóa Pageable và áp dụng chính sách sort. |
| Controller binding | MockMvc hoặc WebTestClient | Query parameter được bind đúng thành filter và `Pageable`. |
| Hypermedia response | MockMvc/WebTestClient với HAL | `_embedded`, `_links`, `page` và URI điều hướng đúng. |
| Client traversal | HTTP client hoặc test tích hợp | Theo link `next` vẫn giữ filter, sort và page size. |

Không cần đặt mọi assertion vào một test lớn. Unit test giúp xác định lỗi ở logic; integration test xác nhận các tầng Spring MVC, Spring Data và Spring HATEOAS phối hợp đúng.

## 3. Tạo bộ dữ liệu kiểm thử có thể phân biệt thứ tự

Test sort chỉ có ý nghĩa khi fixture có giá trị khác nhau ở thuộc tính sắp xếp. Ví dụ, tạo ba đơn hàng:

| ID | Status | Customer | Created at |
| --- | --- | --- | --- |
| `o-101` | `PENDING` | `c-7` | `2026-03-10T10:00:00Z` |
| `o-102` | `PENDING` | `c-7` | `2026-03-12T10:00:00Z` |
| `o-103` | `SHIPPED` | `c-7` | `2026-03-11T10:00:00Z` |

Với filter `status=PENDING` và sort `createdAt,desc`, thứ tự mong đợi là `o-102`, sau đó `o-101`. Đơn `o-103` không được xuất hiện vì trạng thái không phù hợp.

Fixture nên chứa thêm trường hợp biên: nhiều đơn có cùng `createdAt`, đơn thuộc khách hàng khác, collection rỗng và trang cuối có ít item hơn `size`. Dữ liệu kiểm thử càng phân biệt rõ các trường hợp, assertion càng có khả năng phát hiện lỗi thực.

## 4. Kiểm thử filtering và sorting ở repository

Nếu dùng Spring Data JPA, có thể kiểm tra truy vấn thực tế bằng `@DataJpaTest`. Ví dụ repository hỗ trợ `Specification`:

```java
interface OrderRepository extends
        JpaRepository<Order, UUID>,
        JpaSpecificationExecutor<Order> {
}
```

Specification có thể ghép các điều kiện tùy chọn:

```java
static Specification<Order> matching(
        OrderStatus status,
        UUID customerId) {

    return (root, query, builder) -> {
        List<Predicate> predicates = new ArrayList<>();

        if (status != null) {
            predicates.add(builder.equal(root.get("status"), status));
        }

        if (customerId != null) {
            predicates.add(builder.equal(
                    root.get("customer").get("id"), customerId));
        }

        return builder.and(predicates.toArray(Predicate[]::new));
    };
}
```

Test repository:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Autowired
    TestEntityManager entityManager;

    @Test
    void filtersByStatusAndCustomerAndSortsNewestFirst() {
        UUID customerId = persistCustomer();
        persistOrder("o-101", customerId, PENDING, "2026-03-10T10:00:00Z");
        persistOrder("o-102", customerId, PENDING, "2026-03-12T10:00:00Z");
        persistOrder("o-103", customerId, SHIPPED, "2026-03-11T10:00:00Z");
        entityManager.flush();
        entityManager.clear();

        Pageable pageable = PageRequest.of(
                0, 10, Sort.by(Sort.Direction.DESC, "createdAt"));

        Page<Order> result = repository.findAll(
                matching(PENDING, customerId), pageable);

        assertThat(result.getContent())
                .extracting(Order::getBusinessKey)
                .containsExactly("o-102", "o-101");
        assertThat(result.getTotalElements()).isEqualTo(2);
    }
}
```

Các hàm `persistCustomer`, `persistOrder` và tên thuộc tính `businessKey` đại diện cho fixture cùng model của dự án. Điều chỉnh chúng theo entity thực tế. Việc `flush()` và `clear()` giúp test đọc lại dữ liệu từ database thay vì chỉ dựa vào persistence context đang giữ entity.

Test repository cần xác nhận cả content và `totalElements`. Nếu filter sai, có thể content của trang đầu vẫn trông hợp lý nhưng tổng số kết quả bị sai.

## 5. Kiểm thử sort tăng dần và giảm dần

Spring Data nhận sort từ `Pageable`. Một test nên xác nhận từng hướng sắp xếp:

```java
@Test
void sortsOrdersByCreatedAtAscending() {
    Page<Order> result = repository.findAll(
            matching(PENDING, customerId),
            PageRequest.of(0, 10,
                    Sort.by(Sort.Direction.ASC, "createdAt")));

    assertThat(result.getContent())
            .extracting(Order::getBusinessKey)
            .containsExactly("o-101", "o-102");
}

@Test
void sortsOrdersByCreatedAtDescending() {
    Page<Order> result = repository.findAll(
            matching(PENDING, customerId),
            PageRequest.of(0, 10,
                    Sort.by(Sort.Direction.DESC, "createdAt")));

    assertThat(result.getContent())
            .extracting(Order::getBusinessKey)
            .containsExactly("o-102", "o-101");
}
```

Không nên chỉ kiểm tra `page.getSort()` chứa đúng thuộc tính. Điều đó xác nhận đối tượng Pageable được tạo đúng, nhưng chưa chứng minh database trả dữ liệu đúng thứ tự. Repository integration test cần kiểm tra thứ tự thực tế của content.

## 6. Kiểm thử sort ổn định khi có giá trị trùng

Nếu nhiều bản ghi có cùng giá trị `createdAt`, database không bảo đảm thứ tự tương đối giữa chúng nếu truy vấn không có tiêu chí phụ. Điều này có thể khiến một item xuất hiện ở hai trang hoặc bị bỏ qua khi dữ liệu thay đổi giữa các request.

Để phân trang ổn định, hãy bổ sung một khóa duy nhất làm tiêu chí sắp xếp phụ, ví dụ `id`:

```java
Sort stableSort = Sort.by(Sort.Order.desc("createdAt"))
        .and(Sort.by(Sort.Order.desc("id")));

Pageable pageable = PageRequest.of(0, 2, stableSort);
```

Test nên tạo ít nhất hai đơn có cùng timestamp và xác nhận thứ tự theo khóa phụ. Nếu API tự thêm khóa phụ vào sort của client, test cần xác nhận chính sách đó. Nếu client được quyền chỉ định sort hoàn toàn, hãy ghi rõ quy tắc ổn định trong hợp đồng.

Với keyset pagination, tiêu chí sort phải có thể dùng để xác định vị trí tiếp tục. Sort ổn định đặc biệt quan trọng khi collection được cập nhật thường xuyên.

## 7. Kiểm thử kết hợp nhiều filter

Các filter thường có thể được dùng độc lập hoặc kết hợp. Hãy kiểm tra từng điều kiện và phép kết hợp AND/OR theo hợp đồng.

Ví dụ ma trận test:

| Request filter | Kết quả mong đợi |
| --- | --- |
| Không có filter | Tất cả đơn hàng mà người dùng được phép xem. |
| `status=PENDING` | Chỉ đơn đang chờ xử lý. |
| `customerId=c-7` | Chỉ đơn của khách hàng `c-7`. |
| Cả `status=PENDING` và `customerId=c-7` | Đơn thỏa mãn đồng thời hai điều kiện. |
| Filter không khớp dữ liệu | Collection rỗng và metadata nhất quán. |

Nếu API hỗ trợ khoảng ngày, kiểm thử cả hai biên và quy tắc inclusive/exclusive. Ví dụ `from` có thể bao gồm thời điểm bắt đầu, còn `to` có thể được định nghĩa là trước thời điểm kết thúc. Hãy cố định timezone và cách parse ngày giờ để test không phụ thuộc múi giờ máy chạy.

## 8. Kiểm thử controller bind query parameter thành Pageable

Controller có thể nhận filter tường minh cùng `Pageable`:

```java
@GetMapping
PagedModel<EntityModel<OrderView>> all(
        @RequestParam(required = false) OrderStatus status,
        @RequestParam(required = false) UUID customerId,
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.search(status, customerId, pageable);
    return pagedAssembler.toModel(page, assembler);
}
```

MockMvc test có thể gửi query parameter và xác nhận service nhận đúng giá trị:

```java
mockMvc.perform(get("/orders")
        .param("status", "PENDING")
        .param("customerId", customerId.toString())
        .param("page", "1")
        .param("size", "2")
        .param("sort", "createdAt,desc")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk());

ArgumentCaptor<Pageable> pageableCaptor =
        ArgumentCaptor.forClass(Pageable.class);

verify(orderService).search(
        eq(PENDING),
        eq(customerId),
        pageableCaptor.capture());

Pageable actual = pageableCaptor.getValue();
assertThat(actual.getPageNumber()).isEqualTo(1);
assertThat(actual.getPageSize()).isEqualTo(2);
assertThat(actual.getSort().getOrderFor("createdAt").getDirection())
        .isEqualTo(Sort.Direction.DESC);
```

Ví dụ giả định service được mock trong test và controller dùng Spring Data Pageable resolver. Nếu muốn kiểm tra toàn bộ response HAL, cần cung cấp page fixture cho service và kiểm tra JSON ở các phần tiếp theo.

## 9. Kiểm thử HAL response phản ánh đúng kết quả sort và filter

Với một page có dữ liệu xác định, kiểm tra thứ tự item trong `_embedded` và metadata `page`:

```java
mockMvc.perform(get("/orders")
        .param("status", "PENDING")
        .param("page", "0")
        .param("size", "2")
        .param("sort", "createdAt,desc")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders[0].id").value("o-102"))
    .andExpect(jsonPath("$._embedded.orders[1].id").value("o-101"))
    .andExpect(jsonPath("$.page.size").value(2))
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$.page.totalElements").value(2));
```

`orders` là relation collection minh họa; tên thực tế phụ thuộc relation provider hoặc `@Relation` của ứng dụng. Nếu controller trả `PagedModel`, response HAL cần có `_embedded`, `_links` và `page` theo cấu hình media type.

Kiểm thử JSON ở đây xác nhận cả pipeline: query parameter được bind, service trả đúng trang, assembler tạo item representation và Jackson serialize theo HAL. Nếu chỉ test service, các lỗi relation hoặc serialization có thể bị bỏ sót.

## 10. Kiểm thử pagination links giữ filter và sort

Một lỗi thường gặp là trang đầu được lọc đúng nhưng link `next` chỉ giữ `page`, `size`, làm mất `status` hoặc `sort`. Khi client theo link đó, kết quả có thể chuyển sang tập dữ liệu khác.

Ví dụ response mong muốn có link tương tự:

```json
{
  "_links": {
    "self": {
      "href": "/orders?status=PENDING&page=0&size=2&sort=createdAt,desc"
    },
    "next": {
      "href": "/orders?status=PENDING&page=1&size=2&sort=createdAt,desc"
    }
  }
}
```

Kiểm thử nên parse URI của link `next` rồi xác nhận các query parameter cần thiết:

```java
JsonNode response = objectMapper.readTree(responseBody);
String nextHref = response.at("/_links/next/href").asText();

UriComponents next = UriComponentsBuilder.fromUriString(nextHref).build();

assertThat(next.getQueryParams().getFirst("status")).isEqualTo("PENDING");
assertThat(next.getQueryParams().getFirst("page")).isEqualTo("1");
assertThat(next.getQueryParams().getFirst("size")).isEqualTo("2");
assertThat(next.getQueryParams().getFirst("sort"))
        .isEqualTo("createdAt,desc");
```

Đoạn trích dùng `responseBody` là nội dung JSON đã nhận từ MockMvc và có thể đọc bằng `ObjectMapper` hoặc `JsonPath`. Cách parse URI đáng tin cậy hơn so sánh chuỗi `href` đầy đủ vì thứ tự query parameter và cách encode có thể thay đổi.

Nếu custom filter không được giữ tự động bởi cơ chế tạo pagination link trong ứng dụng, hãy tạo link collection có tham số filter tường minh bằng `linkTo(methodOn(...))` hoặc một URI builder phù hợp. Điều quan trọng là test xác nhận hành vi cuối cùng của response, không giả định framework tự giữ mọi query parameter tùy chỉnh.

## 11. Kiểm thử bằng cách thực sự theo link next

Kiểm tra chuỗi `href` chưa chứng minh endpoint trang tiếp theo hoạt động. Một integration test có thể lấy link từ response đầu tiên rồi gửi request tiếp theo.

Quy trình:

1. Gửi request đầu tiên với `status=PENDING`, `size=2`, `sort=createdAt,desc`.
2. Parse `_links.next.href` từ HAL response.
3. Gửi GET tới URI vừa nhận.
4. Xác nhận page number tăng lên 1.
5. Xác nhận filter `PENDING` và sort vẫn được áp dụng.
6. Xác nhận item ở trang hai không lặp item của trang một trong fixture ổn định.

Ví dụ pseudo-code với MockMvc:

```java
MvcResult first = mockMvc.perform(get("/orders")
        .param("status", "PENDING")
        .param("page", "0")
        .param("size", "2")
        .param("sort", "createdAt,desc")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andReturn();

String nextHref = objectMapper.readTree(
        first.getResponse().getContentAsString())
        .path("_links").path("next").path("href").asText();

UriComponents next = UriComponentsBuilder.fromUriString(nextHref).build();

mockMvc.perform(get(next.getPath())
        .queryParams(next.getQueryParams())
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.number").value(1))
    .andExpect(jsonPath("$._embedded.orders[0].status").value("PENDING"));
```

Ví dụ tách path và query từ `href` để tạo request MockMvc cục bộ. Nếu muốn xác minh host, scheme và proxy trong URI tuyệt đối, hãy dùng HTTP client gọi ứng dụng đang chạy trên server tích hợp.

## 12. Kiểm thử sort field được phép

Spring Data cho phép client truyền tên thuộc tính qua `sort`. Không nên mặc định mọi thuộc tính entity đều được phép sort. Một API có thể chỉ cho phép `createdAt`, `status` và `total`.

Có thể kiểm tra sort theo whitelist trước khi tạo truy vấn:

```java
private static final Set<String> ALLOWED_SORTS =
        Set.of("createdAt", "status", "total");

void validateSort(Sort sort) {
    for (Sort.Order order : sort) {
        if (!ALLOWED_SORTS.contains(order.getProperty())) {
            throw new InvalidSortPropertyException(order.getProperty());
        }
    }
}
```

Test cần xác nhận:

- Sort field hợp lệ được chấp nhận.
- Sort field không được phép bị từ chối theo hợp đồng, thường ánh xạ thành `400 Bad Request`.
- Sort direction `asc` và `desc` được bind đúng.
- Nhiều tiêu chí sort được giữ đúng thứ tự ưu tiên.

Không nên để client điều khiển trực tiếp tên cột SQL bằng cách nối chuỗi. Dùng Spring Data `Sort` và whitelist thuộc tính ở tầng API/service. Cần ánh xạ lỗi sort rõ ràng để response không lộ stack trace hoặc chi tiết nội bộ database.

## 13. Kiểm thử filter không hợp lệ và collection rỗng

Filter có thể không hợp lệ do enum không tồn tại, UUID sai định dạng, ngày giờ không parse được hoặc khoảng ngày bị đảo. Xác định rõ API sẽ trả `400 Bad Request` hay chuẩn hóa giá trị theo chính sách.

Ví dụ các trường hợp:

| Request | Điều cần xác nhận |
| --- | --- |
| `status=UNKNOWN` | Lỗi binding được trả theo hợp đồng. |
| `customerId=abc` | UUID không hợp lệ không làm truy vấn chạy sai. |
| `from` lớn hơn `to` | Khoảng thời gian không hợp lệ được từ chối hoặc xử lý theo quy tắc rõ ràng. |
| Filter hợp lệ nhưng không có kết quả | Trả collection rỗng với metadata nhất quán. |
| Không truyền filter | Trả dữ liệu trong phạm vi người dùng được phép xem. |

Với collection rỗng, kiểm tra `page.totalElements` bằng `0`, embedded collection theo hợp đồng và self link vẫn trỏ tới truy vấn hiện tại. Không giả định link `next` luôn tồn tại.

## 14. Kiểm thử phân quyền kết hợp với filter

Filter không được phép mở rộng phạm vi dữ liệu mà người dùng có thể truy cập. Ví dụ người dùng chỉ được xem đơn hàng thuộc tenant của mình; truyền `customerId` khác không được làm lộ đơn hàng ngoài tenant.

Test bảo mật nên xác nhận:

- Mọi truy vấn đều kết hợp tenant/user scope với filter do client gửi.
- Sort không thể làm lộ thuộc tính nhạy cảm qua response hoặc lỗi.
- Pagination link không bỏ mất filter phạm vi dữ liệu hoặc tenant context cần thiết.
- Request trang tiếp theo vẫn chịu cùng quy tắc authorization.
- Việc client tự sửa query parameter không vượt qua kiểm tra ở server.

Không dùng việc link chỉ hiển thị các tài nguyên được phép làm cơ chế bảo mật duy nhất. Service/repository query và authorization phải áp dụng phạm vi dữ liệu trên mỗi request.

## 15. Kiểm thử hiệu năng và số truy vấn

Sort/filter có thể đúng về logic nhưng chậm khi collection lớn. Integration test hoặc performance test nên kiểm tra các truy vấn phổ biến với dữ liệu đại diện:

- Filter trên cột có index phù hợp.
- Sort theo thuộc tính thường dùng và khóa phụ ổn định.
- Kết hợp filter với sort.
- Trang đầu và trang sâu.
- Assembler tạo link cho item mà không phát sinh N+1 query.

Nếu assembler truy cập quan hệ lazy của từng item, số truy vấn có thể tăng theo số phần tử trong page. Dùng projection, fetch strategy hoặc query theo lô khi cần. Page size nhỏ giúp giới hạn lượng item, nhưng không tự đảm bảo query rẻ.

## 16. Các lỗi thường gặp khi kiểm thử sort và filter

**Chỉ kiểm tra status code.** `200 OK` không chứng minh dữ liệu đã được lọc hoặc sắp xếp đúng. Kiểm tra ID và thứ tự item.

**Chỉ kiểm tra Pageable.getSort().** Đối tượng Pageable đúng chưa chứng minh database trả thứ tự đúng. Cần repository integration test.

**Fixture không phân biệt được thứ tự.** Nếu mọi bản ghi có cùng giá trị sort, test có thể không phát hiện sort bị bỏ qua. Tạo dữ liệu có thứ tự mong đợi rõ ràng.

**Không có tiêu chí sort phụ.** Các item trùng giá trị sort chính có thể đổi thứ tự giữa các trang. Bổ sung khóa duy nhất để sort ổn định.

**Link next làm mất filter hoặc sort.** Kiểm tra query parameter trong link và thực sự theo link để gọi trang kế tiếp.

**Không kiểm tra nhiều filter cùng lúc.** Từng filter riêng có thể đúng nhưng khi ghép lại, predicate AND/OR có thể sai.

**Cho phép sort field tùy ý.** Dùng whitelist và trả lỗi có cấu trúc cho thuộc tính không được hỗ trợ.

**Bỏ qua phân quyền trong truy vấn.** Filter do client gửi phải luôn kết hợp với tenant/user scope ở server.

**Chỉ unit test mà không test HAL.** Cần ít nhất một integration test xác nhận `_embedded`, `_links`, `page` và link traversal.

## 17. Bài tập thực hành và tiêu chí hoàn thành

Hãy xây dựng bộ kiểm thử cho `GET /orders` hỗ trợ filter và sort:

1. Tạo fixture với nhiều trạng thái, khách hàng và thời điểm tạo khác nhau.
2. Viết repository test cho filter `status` và `customerId`.
3. Kiểm tra sort tăng dần, giảm dần và nhiều tiêu chí sort.
4. Tạo hai đơn có cùng `createdAt` và xác nhận khóa phụ giúp thứ tự ổn định.
5. Kiểm tra controller bind `status`, `customerId`, `page`, `size` và `sort` đúng.
6. Xác nhận HAL response có item theo đúng thứ tự, `page` metadata đúng và self link đúng.
7. Kiểm tra link `next` giữ filter, sort và size.
8. Theo link `next` rồi xác nhận trang kế tiếp vẫn áp dụng cùng điều kiện truy vấn.
9. Kiểm tra sort field không hợp lệ, filter sai định dạng và collection rỗng.
10. Kiểm tra phạm vi tenant/user và số truy vấn khi page chứa nhiều item.

Bạn đã nắm được cách kiểm thử sort và filter khi có thể xác minh kết quả ở repository, xác nhận query parameter được bind đúng, kiểm tra HAL response và pagination links, theo link để kiểm tra traversal, đồng thời bảo đảm sort ổn định và filter không vượt phạm vi dữ liệu được phép. Những kiểm thử này giúp client nhận đúng tập kết quả và tiếp tục điều hướng mà không mất ngữ cảnh truy vấn.

## Tài liệu tham khảo chính thức

- [Spring Data Commons – Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [Spring Data JPA – Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring HATEOAS – Paged resources](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.paged-resources)
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
