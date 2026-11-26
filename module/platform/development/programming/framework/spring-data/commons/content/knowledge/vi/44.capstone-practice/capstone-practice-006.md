# Tạo projection đóng, DTO và projection động

## 1. Mục tiêu thực hành

Trong chương **Thực hành tổng hợp** của **SPRING_DATA_COMMONS**, bài này xây ba cách đọc một phần dữ liệu đơn hàng:

1. Projection đóng bằng interface.
2. Projection dạng DTO.
3. Projection động được chọn bằng Class<T>.

Mục tiêu là diễn đạt rõ dữ liệu mà use case cần, giữ đúng filter và metadata phân trang, đồng thời kiểm chứng cách module store thực hiện query và mapping.

Projection không phải một aggregate mới và không thay thế entity dùng cho các thao tác nghiệp vụ. Nó là hợp đồng đọc có hình dạng phù hợp với mục đích sử dụng.

Các ví dụ dùng Java 17 và một module hỗ trợ những dạng projection/query được minh họa. Phần query tường minh sẽ chọn JPA để trình bày cụ thể; không coi cú pháp JPA là API dùng chung cho mọi store.

## 2. Mô hình dữ liệu dùng trong bài

Giả sử aggregate PurchaseOrder có các property:

| Property | Kiểu | Vai trò |
| --- | --- | --- |
| id | UUID | Identifier đơn |
| customerId | UUID | Khách hàng của đơn |
| customerNameSnapshot | String | Tên khách hàng được chụp khi tạo đơn |
| status | OrderStatus | DRAFT, CONFIRMED hoặc CANCELLED |
| totalAmount | BigDecimal | Tổng tiền được lưu theo chính sách đã chọn |
| currency | String | Tiền tệ |
| createdAt | Instant | Thời điểm tạo |
| internalNote | String | Ghi chú không cần cho danh sách |
| lines | Collection<OrderLine> | Chi tiết thuộc aggregate |

Bài giả định totalAmount được lưu và cập nhật nhất quán với các dòng đơn. Nếu hệ thống chỉ có một getter Java tính tổng từ lines, không được mặc định projection sẽ biến getter đó thành phép tổng hợp ở store.

Để dùng giá trị tổng hợp trong danh sách, phải chọn một trường tổng đã được duy trì, query/aggregation cụ thể hoặc read model phù hợp.

Màn hình danh sách chỉ cần:

~~~text
id, status, totalAmount, currency, createdAt.
~~~

Chi tiết dòng và internalNote không thuộc nhu cầu của màn hình này.

## 3. Phân biệt ba cách projection

| Cách | Cấu trúc | Cách dùng chính |
| --- | --- | --- |
| Projection đóng | Interface có accessor cho các property cần đọc | Hợp đồng đọc nhỏ, được framework tạo implementation/proxy phù hợp |
| DTO | Class hoặc record với constructor thể hiện dữ liệu đầu ra | Giá trị cụ thể, dễ chuyển qua các tầng ứng dụng |
| Projection động | Method generic nhận Class<T> | Cùng điều kiện truy vấn nhưng chọn hình dạng kết quả lúc gọi |

Projection động không phải một loại dữ liệu thứ tư. Nó là cách chọn kiểu kết quả, chẳng hạn một interface đóng hoặc một DTO đã hỗ trợ.

Không nên hiểu “đóng” là immutable theo mọi nghĩa hoặc là cơ chế kiểm soát quyền truy cập. Thuật ngữ này liên quan đến việc các property cần đọc được xác định qua projection, thay vì biểu thức tùy ý truy cập target.

## 4. Tạo projection đóng

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public interface OrderCard {

    UUID getId();

    OrderStatus getStatus();

    BigDecimal getTotalAmount();

    String getCurrency();

    Instant getCreatedAt();

    default String displayTotal() {
        return getTotalAmount().toPlainString() + " " + getCurrency();
    }
}
~~~

Các accessor khớp với property của PurchaseOrder. displayTotal là phép tính từ những accessor đã có, không yêu cầu đọc lines hoặc một field ngoài hợp đồng.

Framework có thể tận dụng tập property được xác định để tối ưu query khi module hỗ trợ. Cần xem query/command thật để xác nhận field nào được lấy.

Không giả định mọi projection interface đều chỉ truyền đúng số field hiển thị. Cách tạo query, mapping và các quan hệ lồng nhau còn ảnh hưởng lượng dữ liệu.

### Tên accessor là một phần hợp đồng

getTotalAmount khớp với totalAmount ở domain. Không tự đổi thành getTotal_amount chỉ vì tên cột vật lý là total_amount.

Alias của query tường minh, tên field lưu trữ và tên property Java cần được phân biệt theo loại query.

### Không cần gắn annotation entity lên projection

OrderCard không phải entity, không có repository ghi riêng và không được dùng để bỏ qua các invariant khi cập nhật đơn.

Muốn xác nhận hoặc hủy đơn, service cần tải aggregate phù hợp rồi thực hiện hành vi nghiệp vụ, thay vì sửa một projection đọc.

## 5. Khai báo query trả projection đóng

Có thể khai báo một method có tên thể hiện query riêng:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderReadRepository
        extends Repository<PurchaseOrder, UUID> {

    Page<OrderCard> findCardByCustomerIdAndStatus(
            UUID customerId,
            OrderStatus status,
            Pageable pageable);

    Optional<OrderCard> findCardById(UUID id);
}
~~~

Card là phần mô tả trong subject của tên method. Điều kiện được phân tích từ phần sau By.

Không cố đổi return type của một method CRUD kế thừa thành projection nếu signature đó không tương thích hoặc method có ngữ nghĩa dành riêng. Một derived query riêng như findCardById giúp thể hiện rõ nhu cầu đọc.

### Chọn Page hay Slice theo sản phẩm

Page phù hợp khi client cần tổng số. Slice phù hợp khi chỉ cần biết còn phần tiếp theo.

Projection và phân trang là hai quyết định khác nhau:

~~~text
Projection: mỗi phần tử chứa gì?
Page/Slice: một lần đọc trả phạm vi và metadata nào?
~~~

Không chọn Page chỉ vì muốn dùng projection. Cũng không điền totalElements giả vào response khi query chỉ cung cấp Slice.

## 6. Tạo DTO bằng record

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderCardDto(
        UUID id,
        OrderStatus status,
        BigDecimal totalAmount,
        String currency,
        Instant createdAt) {
}
~~~

Record thể hiện một cấu trúc giá trị cụ thể. Các thành phần constructor khớp dữ liệu cần đọc.

Với derived DTO projection, module cần xác định được constructor và các property đầu vào theo cơ chế được hỗ trợ. Record có canonical constructor rõ, nhưng vẫn phải dùng kiểu dữ liệu và module phù hợp.

Nếu dùng class có nhiều constructor, cần làm rõ creator mà hạ tầng projection/mapping sử dụng. Annotation hoặc metadata hỗ trợ tùy module không tự sửa được thứ tự hay kiểu đối số sai.

Có thể thêm method repository:

~~~java
Page<OrderCardDto> findDtoByCustomerIdAndStatus(
        UUID customerId,
        OrderStatus status,
        Pageable pageable);
~~~

Tên Dto trong subject không phải yêu cầu phải có property dto trên domain. Predicate vẫn là customerId và status.

### DTO không có nested projection proxy tự động như interface

Nếu DTO cần thêm dữ liệu liên quan, phải định nghĩa rõ constructor, query hoặc bước mapping. Không giả định mọi object lồng đều được framework dựng theo cùng cơ chế projection interface.

Cũng không thêm annotation persistence cho DTO chỉ để làm constructor projection hoạt động. Trước hết xác định module đang cần kiểu kết quả nào.

## 7. Tạo projection động

Bổ sung method generic:

~~~java
<T> Page<T> findByCustomerIdAndStatus(
        UUID customerId,
        OrderStatus status,
        Pageable pageable,
        Class<T> projectionType);
~~~

Ví dụ gọi cùng query với hai kiểu:

~~~java
Page<OrderCard> interfacePage =
        repository.findByCustomerIdAndStatus(
                customerId,
                OrderStatus.CONFIRMED,
                request,
                OrderCard.class);

Page<OrderCardDto> dtoPage =
        repository.findByCustomerIdAndStatus(
                customerId,
                OrderStatus.CONFIRMED,
                request,
                OrderCardDto.class);
~~~

Class<T> cho framework biết kiểu cần tạo cho T. Nó không mặc định trở thành điều kiện lọc dữ liệu.

Khi một Class parameter được nhận diện là tham số chọn projection, không dùng nó như thể đó vẫn là một query argument thông thường trong biểu thức hoặc điều kiện. Nếu cần một Class làm tham số nghiệp vụ, phải thiết kế signature riêng theo cơ chế module hỗ trợ, thay vì nhầm hai vai trò.

Projection động không có nghĩa mọi Class bất kỳ đều hợp lệ. Kiểu được chọn phải có cấu trúc mà query và module có thể cung cấp.

### Đặt lựa chọn kiểu ở tầng ứng dụng

Một service có thể chọn OrderCard cho xử lý nội bộ hoặc OrderCardDto cho một response đã quy định.

Nếu HTTP cho phép lựa chọn view, nên nhận một mã view có hợp đồng rồi ánh xạ sang các kiểu hỗ trợ. Không để client phụ thuộc vào tên class Java.

Không thay một response đã cam kết bằng entity đầy đủ chỉ vì method generic cũng có thể nhận một kiểu khác.

## 8. Hợp đồng repository hoàn chỉnh cho bài

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderReadRepository
        extends Repository<PurchaseOrder, UUID> {

    Optional<OrderCard> findCardById(UUID id);

    Page<OrderCard> findCardByCustomerIdAndStatus(
            UUID customerId,
            OrderStatus status,
            Pageable pageable);

    Page<OrderCardDto> findDtoByCustomerIdAndStatus(
            UUID customerId,
            OrderStatus status,
            Pageable pageable);

    <T> Page<T> findByCustomerIdAndStatus(
            UUID customerId,
            OrderStatus status,
            Pageable pageable,
            Class<T> projectionType);
}
~~~

Repository này phục vụ đọc. Có thể ghép hoặc tách khỏi repository ghi tùy kiến trúc, nhưng cần giữ rõ vai trò của projection và aggregate.

Các method cố định và method động ở đây dùng để thực hành ba cách. Trong một API sản phẩm, không bắt buộc giữ mọi method trùng khả năng nếu chỉ một hợp đồng là cần thiết.

## 9. Với JPA: query tường minh cho interface và DTO

Khi cần kiểm soát select list, có thể dùng query tường minh của module.

### Interface projection với alias

Ví dụ bổ sung trong repository JPA:

~~~java
@org.springframework.data.jpa.repository.Query(
        value = """
                select o.id as id,
                       o.status as status,
                       o.totalAmount as totalAmount,
                       o.currency as currency,
                       o.createdAt as createdAt
                from PurchaseOrder o
                where o.customerId = :customerId
                  and o.status = :status
                """,
        countQuery = """
                select count(o)
                from PurchaseOrder o
                where o.customerId = :customerId
                  and o.status = :status
                """)
Page<OrderCard> loadCards(
        @org.springframework.data.repository.query.Param("customerId")
        UUID customerId,
        @org.springframework.data.repository.query.Param("status")
        OrderStatus status,
        Pageable pageable);
~~~

Các alias khớp accessor của OrderCard. Cú pháp dùng entity name và property JPA, không phải mặc định tên bảng/cột.

Count query cần giữ cùng điều kiện nghiệp vụ với content query. Không bỏ filter status ở count rồi trả tổng của một tập khác.

### DTO projection với constructor expression

~~~java
@org.springframework.data.jpa.repository.Query(
        value = """
                select new com.example.orders.api.OrderCardDto(
                    o.id,
                    o.status,
                    o.totalAmount,
                    o.currency,
                    o.createdAt)
                from PurchaseOrder o
                where o.customerId = :customerId
                  and o.status = :status
                """,
        countQuery = """
                select count(o)
                from PurchaseOrder o
                where o.customerId = :customerId
                  and o.status = :status
                """)
Page<OrderCardDto> loadCardDtos(
        @org.springframework.data.repository.query.Param("customerId")
        UUID customerId,
        @org.springframework.data.repository.query.Param("status")
        OrderStatus status,
        Pageable pageable);
~~~

Tên class đầy đủ phải khớp package thực tế của DTO. Thứ tự và kiểu đối số phải khớp constructor.

Không sao chép alias như as totalAmount vào bên trong constructor expression rồi coi nó giống select list cho interface.

Một số môi trường có hỗ trợ viết lại query cho DTO trong các trường hợp cụ thể. Ví dụ ở đây dùng constructor expression tường minh để ý định rõ; không phụ thuộc vào việc mọi query đều được tự viết lại.

### Native query và module khác

Native query có thể cần alias, kiểu kết quả và result mapping riêng. Một số kiểu số hoặc thời gian từ driver không tự khớp constructor DTO.

Với document hoặc store khác, dùng query/projection mechanism tương ứng. Không chuyển JPQL thành chuỗi query của module khác chỉ bằng cách đổi annotation import.

## 10. Chuyển projection thành DTO bằng Page.map

Có thể muốn giữ projection làm hợp đồng persistence, còn DTO do tầng API sở hữu.

~~~java
Page<OrderCard> source =
        repository.findCardByCustomerIdAndStatus(
                customerId,
                OrderStatus.CONFIRMED,
                request);

Page<OrderCardDto> result = source.map(card ->
        new OrderCardDto(
                card.getId(),
                card.getStatus(),
                card.getTotalAmount(),
                card.getCurrency(),
                card.getCreatedAt()));
~~~

Page.map chuyển nội dung và giữ metadata phân trang theo hợp đồng của Page.

Không chỉ lấy content rồi tạo một PageImpl mới mà bỏ mất Pageable hoặc totalElements. Khi đó dữ liệu từng phần có thể đúng nhưng metadata bị sai.

Phép map này không tự yêu cầu một query mới, nhưng getter được gọi có thể có hành vi phụ thuộc projection/mapping. Với projection phẳng chỉ đọc các field đã chọn, cần kiểm chứng rằng không phát sinh tải quan hệ ngoài nhu cầu.

Projection DTO của repository và DTO response phân trang là hai lớp khác nhau:

~~~text
OrderCardDto: hình dạng của một phần tử.
PageResponse<OrderCardDto>: envelope HTTP do ứng dụng quy định.
~~~

Không dựa vào việc phần tử đã là DTO để kết luận JSON của đối tượng Page ngoài cùng có schema cố định.

## 11. Nullability và giá trị dẫn xuất

Nếu một property thực sự cho phép thiếu, projection interface có thể sử dụng wrapper được Spring Data hỗ trợ.

Ví dụ một view khác:

~~~java
import java.util.Optional;
import java.util.UUID;

public interface OrderCustomerLabel {
    UUID getId();
    Optional<String> getCustomerNameSnapshot();
}
~~~

Nếu hợp đồng nghiệp vụ bắt buộc tên snapshot, không đổi sang Optional chỉ để che dữ liệu sai. Cần xử lý dữ liệu hoặc mapping theo chính sách.

Với DTO, kiểu như Integer biểu đạt null khác với int. Với record có invariant trong canonical constructor, dữ liệu không hợp lệ vẫn có thể bị từ chối khi materialize.

### Default method và open projection

Một default method chỉ tính từ accessor đã chọn có nhu cầu dữ liệu rõ.

Nếu dùng biểu thức như Value truy cập target tùy ý, hạ tầng có thể không xác định được đầy đủ property cần lấy để tối ưu như projection đóng. Đừng coi mọi interface có vài getter đều có cùng đặc điểm tối ưu.

Đối với giá trị phức tạp như tổng tiền từ collection, query aggregation hoặc một trường tổng được duy trì rõ ràng thường dễ kiểm chứng hơn việc trông chờ biểu thức tự giải quyết hiệu năng.

## 12. Projection lồng và quan hệ cần được đo riêng

Nếu thêm một accessor lấy Customer hoặc lines, hình dạng query có thể đổi:

- Join thêm dữ liệu.
- Materialize đối tượng liên quan rộng hơn dự kiến.
- Trả nhiều hàng rồi hợp nhất.
- Hoặc phát sinh truy vấn khi đọc dữ liệu liên quan, tùy module.

Không giả định nested projection tự bảo đảm chỉ đọc một field nhỏ của quan hệ.

Trong bài, dùng customerNameSnapshot có sẵn trên đơn tránh phải đọc Customer chỉ để hiển thị tên lịch sử. Đây là quyết định mô hình, không chỉ là mẹo chọn cột.

Nếu use case cần tên khách hàng hiện tại, phải khai báo đó là nhu cầu khác và thiết kế query tương ứng, thay vì âm thầm thay ý nghĩa snapshot.

## 13. Fixture có dữ liệu đối chứng

Chọn các nhãn O1–O4 và C1–C2 để mô tả, rồi gán UUID cụ thể khi triển khai.

| Đơn | Khách hàng | Trạng thái | Tổng | Thời điểm |
| --- | --- | --- | --- | --- |
| O1 | C1 | CONFIRMED | 100.00 USD | T0 |
| O2 | C1 | CONFIRMED | 200.00 USD | T0 |
| O3 | C1 | DRAFT | 300.00 USD | T1 |
| O4 | C2 | CONFIRMED | 400.00 USD | T0 |

T1 sau T0. Mỗi đơn còn có internalNote và một số lines để kiểm tra chúng không thuộc nhu cầu card.

Truy vấn C1, CONFIRMED phải chỉ trả O1 và O2.

Hai đơn cùng T0 giúp kiểm tra sort có khóa phân định. Ví dụ:

~~~java
PageRequest request = PageRequest.of(
        0,
        1,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")));
~~~

Cần chọn UUID của O1 đứng trước O2 theo cách so sánh mà mapping/store sử dụng và xác nhận điều đó trong fixture. Không giả định nhãn O1 tự tạo một thứ tự UUID.

Có thể dùng ID theo chiến lược khác nếu store không có thứ tự UUID phù hợp với yêu cầu bài, nhưng phải giữ kiểu và thứ tự nhất quán trong hợp đồng.

## 14. Kiểm thử ba cách đọc trên repository thật

Ví dụ test giả định fixture và các UUID C1, O1, O2 đã được thiết lập trong database thử nghiệm. Repository là bean thật của module.

~~~java
@Test
void readsTheSameCardThroughFixedAndDynamicProjections() {
    PageRequest request = PageRequest.of(
            0, 1,
            Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.asc("id")));

    Page<OrderCard> closed =
            repository.findCardByCustomerIdAndStatus(
                    C1, OrderStatus.CONFIRMED, request);

    Page<OrderCardDto> dto =
            repository.findDtoByCustomerIdAndStatus(
                    C1, OrderStatus.CONFIRMED, request);

    Page<OrderCard> dynamicClosed =
            repository.findByCustomerIdAndStatus(
                    C1, OrderStatus.CONFIRMED, request, OrderCard.class);

    Page<OrderCardDto> dynamicDto =
            repository.findByCustomerIdAndStatus(
                    C1, OrderStatus.CONFIRMED, request, OrderCardDto.class);

    assertThat(closed.getContent()).hasSize(1);
    assertThat(closed.getContent().get(0).getId()).isEqualTo(O1);
    assertThat(closed.getContent().get(0).getTotalAmount())
            .isEqualByComparingTo("100.00");

    assertThat(dto.getContent()).containsExactly(
            new OrderCardDto(
                    O1,
                    OrderStatus.CONFIRMED,
                    new BigDecimal("100.00"),
                    "USD",
                    T0));

    assertThat(dynamicClosed.getContent().get(0).getId())
            .isEqualTo(O1);

    assertThat(dynamicDto.getContent()).isEqualTo(dto.getContent());

    assertThat(closed.getTotalElements()).isEqualTo(2);
    assertThat(closed.getTotalPages()).isEqualTo(2);
    assertThat(dto.getTotalElements()).isEqualTo(2);
    assertThat(dynamicDto.getTotalElements()).isEqualTo(2);

    Page<OrderCardDto> next = repository.findByCustomerIdAndStatus(
            C1,
            OrderStatus.CONFIRMED,
            request.next(),
            OrderCardDto.class);

    assertThat(next.getContent())
            .extracting(OrderCardDto::id)
            .containsExactly(O2);
}
~~~

Đoạn test dùng JUnit Jupiter và AssertJ. Việc so sánh record bằng equals giả định scale và biểu diễn dữ liệu trong fixture được kiểm soát; khi chỉ cần so sánh giá trị số, dùng assertion BigDecimal phù hợp.

Cần thêm các ca:

- Không có kết quả.
- Chỉ có dữ liệu của khách hàng khác.
- Có trạng thái khác trong cùng khách hàng.
- Trang cuối chưa đầy.
- Null ở field được phép.
- Projection thiếu hoặc sai tên property.
- Constructor DTO sai kiểu theo một trường hợp thử lỗi riêng.
- Dynamic type không nằm trong tập kiểu mà ứng dụng hỗ trợ.

Không khóa assertion vào tên class proxy do framework tạo. Cần kiểm tra hợp đồng accessor và dữ liệu.

## 15. Kiểm chứng query và chi phí thực tế

Test kết quả đúng chưa chứng minh projection đã giảm dữ liệu tải.

Nên quan sát:

| Điểm đo | Điều cần xác nhận |
| --- | --- |
| Query/command | Có chọn field cần thiết theo khả năng module không? |
| Query count | Có count hoặc tải quan hệ phát sinh không? |
| Số hàng/document | Có join làm nhân kết quả không? |
| Dung lượng | InternalNote hoặc payload lines có bị tải ngoài nhu cầu không? |
| Mapping | Có materialize entity đầy đủ rồi mới chuyển view không? |
| DTO mapping | Có conversion hoặc constructor tốn kém ngoài dự kiến không? |

Page có thể cần count query, nhưng không mặc định mọi lần gọi luôn chạy cùng một số query cố định. Phép so sánh phải dùng cùng hợp đồng metadata.

Chạy với dữ liệu đủ rộng và nhiều bản ghi để lợi ích có thể quan sát. Đo cùng điều kiện cache, sort, page size và workload.

Mock repository trả một OrderCardDto được tạo sẵn không xác minh alias, constructor projection hoặc select list của query thật.

## 16. Các lỗi thực hành thường gặp

| Lỗi | Nguyên nhân cần kiểm tra | Cách sửa |
| --- | --- | --- |
| Accessor trả null ngoài dự kiến | Sai property/alias hoặc field thực sự null | Đối chiếu domain, query và raw data |
| DTO không được tạo | Constructor, kiểu đối số hoặc hỗ trợ module | Sửa hợp đồng DTO/query |
| Lỗi PropertyReferenceException | Tên method hoặc property không khớp | Kiểm tra predicate và domain gốc |
| Projection động chọn sai kiểu | Caller truyền Class không phù hợp | Chọn kiểu ở service theo hợp đồng |
| Không dùng được Class trong query như mong đợi | Nó đã là tham số chọn projection | Tách vai trò tham số |
| Metadata Page sai | Mapping thủ công làm mất Pageable/total | Dùng Page.map hoặc tạo đủ metadata |
| Hết exception nhưng kết quả sai | Fixture không phân biệt filter/property | Thêm dữ liệu đối chứng |
| Projection không giảm payload | Query hoặc nested mapping tải rộng | Đọc query thật và điều chỉnh |
| Danh sách chậm do tính total | Query count hoặc aggregation đắt | Đánh giá đúng nhu cầu metadata |
| DTO đọc bị dùng để ghi | Nhầm view với aggregate | Tách hợp đồng đọc và hành vi nghiệp vụ |

Nếu query hợp lệ nhưng DTO thiếu field cần cho client, đó là lỗi thiết kế hợp đồng đọc. Không tự thêm mọi field entity vào DTO cho đến khi chúng giống nhau.

## 17. Tiêu chí hoàn thành và sản phẩm bàn giao

Người học cần trình bày được:

1. Một OrderCard đóng với accessor khớp property domain.
2. Một OrderCardDto có constructor rõ và kiểu dữ liệu phù hợp.
3. Các method cố định và một method động dùng Class<T>.
4. Lời gọi có kiểu an toàn cho cả interface và DTO.
5. Fixture kiểm tra đúng customer, status, sort và paging.
6. Bằng chứng mapping/query hoạt động trên module store đã chọn.
7. Cách chuyển phần tử sang DTO mà giữ metadata.
8. Những giới hạn của projection lồng, nullability và query tùy biến.

Sản phẩm bàn giao gồm mã projection, hợp đồng repository, lựa chọn mapping/query và các kết quả kiểm chứng liên quan. Không cần mở rộng thành toàn bộ API bán hàng để hoàn thành mục tiêu này.

Projection hiệu quả bắt đầu từ dữ liệu use case thực sự cần. Interface đóng, DTO và lựa chọn động là ba cách tổ chức hợp đồng đọc; tính đúng đắn và lợi ích thực tế vẫn phải được xác nhận trên query cùng store cụ thể.
