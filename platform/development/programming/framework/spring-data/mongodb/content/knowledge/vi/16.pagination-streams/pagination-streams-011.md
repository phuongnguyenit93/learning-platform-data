# Phân trang reactive bằng Flux và phép đếm riêng khi cần

## 1. Vì sao phân trang reactive không chỉ là đổi List thành Flux?

Trong ứng dụng Spring Data MongoDB, một API có thể phải liệt kê hàng chục nghìn đơn hàng nhưng chỉ trả 20–50 bản ghi mỗi lần. Truy vấn toàn bộ collection rồi chia thành các trang trong Java không phù hợp: mạng, bộ nhớ, thời gian phản hồi và tải database đều tăng theo lượng dữ liệu.

Với lập trình reactive, **Flux<T>** là một publisher có thể phát nhiều phần tử theo thời gian; **Mono<T>** phát tối đa một phần tử. Tuy nhiên, **Flux tự nó không mang thông tin tổng số trang hay tổng số document**. Để phân trang đúng, ứng dụng vẫn phải gửi **skip/limit/sort hoặc điều kiện con trỏ** tới MongoDB, đồng thời quyết định có thật sự cần đếm tổng số kết quả không.

Đó là trọng tâm của bài **Phân trang reactive bằng Flux và phép đếm riêng khi cần**, thuộc chương **Phân trang và luồng** trong module **SPRING_DATA_MONGODB**. Kiến thức này kết nối giữa Spring Data MongoDB, reactive repository, ReactiveMongoTemplate, truy vấn, index, kiểm thử và chẩn đoán hiệu năng.

Sau bài này, bạn sẽ biết cách:

1. Khai báo repository trả **Flux<Entity>** nhận **Pageable**.
2. Phân biệt **dữ liệu một trang**, **cửa sổ có hasNext** và **Page cần totalElements**.
3. Viết **Mono<Long> count...** riêng, chỉ gọi khi giao diện hoặc nghiệp vụ cần.
4. Dùng **ReactiveMongoTemplate** để đọc thêm một bản ghi, xác định hasNext mà không count.
5. Thiết kế **sort ổn định**, index và **seek/keyset pagination** cho dữ liệu lớn.
6. Tránh block(), collectList() vô hạn, N+1 query và các sai lệch khi dữ liệu thay đổi đồng thời.
7. Kiểm thử phân trang reactive bằng Reactor Test/StepVerifier và MongoDB test.

**Quy tắc chính:** Trả **Flux** khi muốn stream dữ liệu của trang; dùng **Mono<Long>** cho phép đếm riêng; chỉ kết hợp cả hai thành **Mono<Page<T>>** nếu thực sự cần metadata tổng số.

## 2. Mô hình đơn hàng dùng xuyên suốt

Giả sử collection **orders** có các document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  orderNumber: "ORD-1001",
  status: "PAID",
  createdAt: ISODate("2025-06-01T10:00:00Z"),
  totalMinor: NumberLong("159000")
}
~~~

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-a",
  orderNumber: "ORD-1002",
  status: "PAID",
  createdAt: ISODate("2025-06-01T09:00:00Z"),
  totalMinor: NumberLong("89000")
}
~~~

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439013"),
  tenantId: "shop-b",
  orderNumber: "ORD-2001",
  status: "PAID",
  createdAt: ISODate("2025-06-01T08:00:00Z"),
  totalMinor: NumberLong("49000")
}
~~~

**tenantId** thể hiện phạm vi dữ liệu. Một API dành cho shop-a không được trả đơn của shop-b. **createdAt** là BSON Date và **_id** là ObjectId; cả hai được dùng để tạo thứ tự phân trang xác định.

Entity Java:

~~~java
package com.example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id ObjectId id,
    String tenantId,
    String orderNumber,
    String status,
    Instant createdAt,
    long totalMinor
) {}
~~~

Trong các ví dụ, hệ thống sử dụng Spring Data MongoDB reactive và driver reactive tương ứng. Các phương thức reactive chỉ thật sự chạy khi publisher được **subscribe**; việc xây dựng một Mono/Flux không đồng nghĩa câu lệnh đã được gửi tới MongoDB.

## 3. Khác biệt giữa Flux, Mono, Page và Slice

| Kiểu | Ý nghĩa | Có biết tổng số kết quả? |
| --- | --- | --- |
| **Flux<OrderDocument>** | Luồng nhiều Order, có thể là một trang đã giới hạn | Không, trừ khi gọi truy vấn khác. |
| **Mono<List<OrderDocument>>** | Toàn bộ dữ liệu đã collect của **một trang** | Chỉ biết số bản ghi trong trang. |
| **Mono<Long>** | Kết quả một truy vấn đếm | Có số document khớp filter tại thời điểm đếm. |
| **Mono<Page<OrderDocument>>** | Một trang dữ liệu cùng page metadata và total | Có total nếu đã tính/được cung cấp. |
| **Mono<Slice<OrderDocument>>** | Một cửa sổ có thể xác định hasNext | Không cần total. |

Một cách hình dung:

~~~mermaid
flowchart TD
    A["Client yêu cầu danh sách đơn hàng"] --> B{"Cần metadata nào?"}
    B -->|"Chỉ dữ liệu"| C["Flux<Order> + Pageable"]
    B -->|"Cần hasNext"| D["Đọc size + 1 → Mono<Slice<Order>>"]
    B -->|"Cần tổng số"| E["Đọc trang + count riêng"]
    E --> F["Mono<Page<Order>> hoặc DTO có totalElements"]
~~~

**Quan trọng:** Pageable là cách mô tả page number, page size và Sort. Nó không phải publisher, cũng không tự khiến Flux có tổng số trang.

Trong Spring Data repository reactive, một phương thức có thể nhận Pageable nhưng trả Flux; đây là lựa chọn có chủ đích để tránh phải chạy thêm count query mỗi lần chỉ muốn danh sách.

## 4. Khai báo ReactiveMongoRepository có Pageable

Repository cho Order:

~~~java
package com.example.orders;

import org.bson.types.ObjectId;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface OrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {

    Flux<OrderDocument> findByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );

    Mono<Long> countByTenantIdAndStatus(
        String tenantId,
        String status
    );
}
~~~

Giải thích:

- **findByTenantIdAndStatus** là derived query: Spring Data xây filter theo hai property tenantId và status.
- **Pageable** là tham số đặc biệt cho giới hạn, offset và sort; nó không được bind như một field BSON.
- **Flux<OrderDocument>** phát lần lượt các document khớp trang; không phải Page với total có sẵn.
- **countByTenantIdAndStatus** là **truy vấn đếm riêng** và trả Mono<Long>.

Hai method có cùng điều kiện tenant/status nhưng **không tự động chạy cùng lúc**. Nếu caller chỉ subscribe Flux dữ liệu, count không cần được gọi.

### 4.1. Sort cần ổn định

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable firstPage = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

Trong Spring Data, id là property Java được ánh xạ thành MongoDB **_id**. Sắp xếp theo createdAt giảm dần và dùng id giảm dần làm khóa phụ giúp có thứ tự xác định khi nhiều Order có cùng thời điểm.

**Không nên phân trang mà thiếu sort tường minh.** Thứ tự tự nhiên của MongoDB không phải hợp đồng ổn định cho phân trang API.

## 5. Phân trang đơn giản: chỉ trả Flux

Một service có thể expose đúng Flux của trang:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import reactor.core.publisher.Flux;

public class OrderReadService {
    private final OrderRepository repository;

    public OrderReadService(OrderRepository repository) {
        this.repository = repository;
    }

    public Flux<OrderDocument> page(
            String tenantId, String status, int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            return Flux.error(
                new IllegalArgumentException("Invalid page or size")
            );
        }

        Pageable pageable = PageRequest.of(
            page, size,
            Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            )
        );

        return repository.findByTenantIdAndStatus(
            tenantId, status, pageable
        );
    }
}
~~~

Ví dụ này áp dụng giới hạn **1–100 bản ghi** mỗi trang. Ngay cả khi client nhập size = 1.000.000, service không chấp nhận tải toàn bộ dữ liệu. Trong hệ thống thật, hãy xác minh tenantId từ ngữ cảnh đã xác thực; không cho phép người dùng tự chọn bất kỳ tenantId nào ngoài quyền của họ.

Một lời gọi:

~~~java
Flux<OrderDocument> first =
    service.page("shop-a", "PAID", 0, 20);
~~~

Publisher mô tả một truy vấn có filter, offset, limit, sort. Nó chỉ phát dữ liệu khi được subscribe (ví dụ bởi WebFlux), và **không tự phát số trang hoặc tổng số Order**.

### 5.1. Không tự chia trang trên Flux không giới hạn

Tránh:

~~~java
// Không nên: đọc một tập rất lớn rồi mới bỏ qua phần tử trên client.
Flux<OrderDocument> all = repository.findAll();

Flux<OrderDocument> page =
    all.skip((long) pageNumber * size).take(size);
~~~

Đoạn code trên có thể khiến MongoDB vẫn truyền/duyệt nhiều kết quả mà ứng dụng chỉ bỏ đi ở Reactor. **Pageable hoặc Query.skip/limit phải được gửi xuống MongoDB** để server tham gia phân trang.

Tương tự, không dùng **repository.findAll().collectList()** rồi List.subList cho collection lớn: collectList sẽ giữ toàn bộ kết quả trong bộ nhớ trước khi cắt trang.

### 5.2. Flux có phải luồng vô hạn?

Không. Flux từ một truy vấn find có Pageable thường **hữu hạn**: phát tối đa size bản ghi của trang rồi hoàn thành. Nó không phải tailable cursor, MongoDB Change Stream hay cơ chế nhận cập nhật mới liên tục.

Backpressure cho phép phía nhận điều tiết yêu cầu phần tử, nhưng không thay thế skip/limit, index hoặc việc đóng cursor khi stream bị hủy.

## 6. Đếm riêng chỉ khi cần tổng số

Một màn hình cần hiển thị “Có 12.345 đơn hàng phù hợp” hoặc “Trang 3/618” thì phải biết **totalElements**. Flux trang không cung cấp metadata này.

Với repository:

~~~java
Mono<Long> totalPublisher =
    repository.countByTenantIdAndStatus("shop-a", "PAID");
~~~

**Mono<Long>** phát tổng số document khớp điều kiện tenantId và status tại thời điểm đếm. Nếu UI chỉ có nút “Xem thêm”, count có thể không cần thiết.

### 6.1. Vì sao không đếm ở mọi request?

Count là một câu truy vấn khác. Với dữ liệu lớn hoặc filter phức tạp, nó có thể tốn thêm tài nguyên, đặc biệt khi query không có index phù hợp.

| Use case | Có nhất thiết cần count? | Phương án |
| --- | --- | --- |
| Danh sách cuộn liên tục | Không | Flux trang hoặc Slice có hasNext. |
| Nút “Tải thêm” | Thường không | Đọc size + 1 để xác định hasNext. |
| Hiển thị “Trang 3/100” | Có | Count riêng và tính totalPages. |
| Báo cáo tổng số đơn khớp filter | Có | Mono<Long> riêng. |
| Streaming export nhiều lô | Không cần cho mỗi lô | Duyệt lô bằng keyset/cursor và chỉ đếm nếu báo cáo yêu cầu. |
| Dashboard nhiều widget thống kê | Tùy yêu cầu | Cân nhắc batch/aggregation, cache hoặc số ước lượng có nhãn rõ. |

**Không dùng số lượng phần tử Flux trả về như total toàn collection.** Nếu page size là 20, trang nhận đủ 20 phần tử chỉ chứng minh có ít nhất 20 phần tử trong phạm vi trang đó; nó không cho biết có hay không trang tiếp theo.

## 7. Kết hợp Flux với count thành Mono<Page<T>>

Khi API thực sự cần total, có thể chạy hai publisher và kết hợp kết quả:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import reactor.core.publisher.Mono;

public Mono<Page<OrderDocument>> pageWithTotal(
        String tenantId, String status, Pageable pageable) {

    Mono<java.util.List<OrderDocument>> rows =
        repository.findByTenantIdAndStatus(
            tenantId, status, pageable
        ).collectList();

    Mono<Long> total =
        repository.countByTenantIdAndStatus(tenantId, status);

    return Mono.zip(rows, total)
        .map(tuple -> new PageImpl<>(
            tuple.getT1(),
            pageable,
            tuple.getT2()
        ));
}
~~~

Trong ví dụ, repository là dependency được inject sẵn. **collectList() an toàn hơn khi Flux đã bị giới hạn bởi Pageable**, bởi bộ nhớ được dùng để giữ tối đa kích thước trang thông thường, không phải toàn bộ collection.

**Mono.zip** subscribe hai publisher khi kết quả được subscribe. Count là một thao tác database độc lập và có thể chạy đồng thời với query lấy trang. Không có bảo đảm hai kết quả quan sát cùng một snapshot dữ liệu khi có ghi/xóa đồng thời.

### 7.1. Tính số trang

Một Page thường có:

- **getContent()**: danh sách document của trang hiện tại.
- **getNumber()**: số trang hiện tại (bắt đầu từ 0).
- **getSize()**: kích thước trang yêu cầu.
- **getTotalElements()**: tổng số document khớp filter theo count.
- **getTotalPages()**: số trang suy ra từ totalElements và size.

PageImpl là implementation của Page và có thể điều chỉnh metadata total trong một số trường hợp cuối trang để giảm bất nhất do dữ liệu thay đổi. **Đừng dùng PageImpl làm cơ chế bảo đảm snapshot nhất quán** giữa hai query.

### 7.2. Chi phí của việc dùng Page

Để dựng Page với total, thường phải có:

1. Một truy vấn tìm document cho trang.
2. Một truy vấn đếm cùng filter.
3. Chi phí collect các phần tử của trang trước khi phát Page.

Đó là lý do trả về **Mono<Page<T>>** chỉ hợp lý khi UI hoặc hợp đồng nghiệp vụ cần total. Không buộc mọi endpoint reactive phải dựng Page.

## 8. Thiết kế response có total tùy chọn

Nhiều API muốn vừa hỗ trợ danh sách nhẹ, vừa cho phép client yêu cầu total qua **includeTotal=true**. Khi đó không cần trả kiểu Page có total bắt buộc ở mọi request.

DTO minh họa:

~~~java
import java.util.List;

public record OrderWindow(
    List<OrderRow> items,
    int page,
    int size,
    boolean hasNext,
    Long totalElements
) {}
~~~

Ở đây **totalElements == null** có nghĩa **không yêu cầu hoặc chưa tính tổng**, không phải tổng bằng 0. Nếu xuất JSON, có thể thiết kế serializer ẩn field null theo quy ước API; cần ghi rõ hợp đồng này cho client.

**Có một điểm cần sửa ngay trong thiết kế dữ liệu:** Nếu chỉ tải đúng size bản ghi, ta **không thể biết chính xác hasNext** từ kích thước danh sách. Muốn có hasNext mà không count, cần đọc thêm **một bản ghi** và chỉ trả size bản ghi đầu. Phần tiếp theo trình bày cách làm đó.

## 9. Slice: đọc size + 1 để biết hasNext

Chiến lược:

1. Client yêu cầu size = 20.
2. Truy vấn MongoDB tối đa **21** bản ghi theo cùng sort.
3. Nếu có 21 bản ghi, **hasNext = true**; trả 20 bản ghi đầu.
4. Nếu có không quá 20 bản ghi, **hasNext = false** ở thời điểm query.

~~~mermaid
flowchart LR
    A["Yêu cầu page=2, size=20"] --> B["MongoDB skip=40, limit=21"]
    B --> C["Flux tối đa 21 document"]
    C --> D["collectList tối đa 21"]
    D --> E["Trả 20 items + hasNext"]
~~~

**Lưu ý quan trọng về offset:** Nếu tính Pageable bằng **PageRequest.of(2, 21)**, offset sẽ là **42**, không phải **40**. Vì vậy, khi đọc dư một bản ghi, phải giữ offset theo **size client yêu cầu**, rồi chỉ tăng limit thành **size + 1**.

### 9.1. ReactiveMongoTemplate: giới hạn dư một phần tử

~~~java
import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.SliceImpl;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Mono;

public class OrderSliceService {
    private final ReactiveMongoTemplate template;

    public OrderSliceService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<Slice<OrderDocument>> findSlice(
            String tenantId, String status, int page, int size) {

        if (page < 0 || size < 1 || size > 100) {
            return Mono.error(
                new IllegalArgumentException("Invalid page or size")
            );
        }

        Pageable pageable = PageRequest.of(
            page, size,
            Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            )
        );

        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
                .and("status").is(status)
        );
        query.with(pageable);        // Giữ offset = page * size.
        query.limit(size + 1);       // Chỉ tăng limit.

        return template.find(query, OrderDocument.class)
            .collectList()
            .map(rows -> {
                boolean hasNext = rows.size() > size;
                List<OrderDocument> content = rows.subList(
                    0, Math.min(size, rows.size())
                );
                return new SliceImpl<>(
                    content, pageable, hasNext
                );
            });
    }
}
~~~

Với **Query.with(pageable)**, Spring Data áp dụng skip/limit/sort theo page được yêu cầu. **query.limit(size + 1)** ghi đè limit của query nhưng không thay đổi offset vừa thiết lập. Cách này tránh lỗi tăng offset khi tự tạo PageRequest với kích thước 21.

**Slice không cần count**. Nó cung cấp nội dung của cửa sổ và hasNext theo kết quả query vừa thực thi.

### 9.2. Không biến hasNext thành số lượng tuyệt đối

Nếu hasNext = true, chỉ có nghĩa đã nhìn thấy ít nhất một bản ghi ngoài page trong truy vấn này. Nó không cho biết còn chính xác bao nhiêu trang hoặc bao nhiêu document. Nếu một writer xóa bản ghi ngay sau đó, trang kế tiếp vẫn có thể rỗng; đây là giới hạn của phân trang trên dữ liệu đang thay đổi.

### 9.3. Trả DTO nhẹ thay vì nguyên entity

Nếu client chỉ cần orderNumber, createdAt và totalMinor, sử dụng projection hoặc map sang DTO:

~~~java
public record OrderRow(
    String id,
    String orderNumber,
    java.time.Instant createdAt,
    long totalMinor
) {}
~~~

~~~java
public OrderRow toRow(OrderDocument document) {
    return new OrderRow(
        document.id().toHexString(),
        document.orderNumber(),
        document.createdAt(),
        document.totalMinor()
    );
}
~~~

Projection giúp giảm dữ liệu truyền và chuyển đổi, nhưng không tự giải quyết offset sâu hoặc đảm bảo query được index bao phủ. Hãy kết hợp cả ba: filter đúng, sort/index phù hợp và chỉ lấy các field cần dùng.

## 10. Khi client yêu cầu total: kết hợp Slice và count

Nếu API luôn trả hasNext nhưng chỉ có **totalElements** khi được yêu cầu, có thể tái sử dụng phương thức findSlice:

~~~java
public Mono<OrderWindow> findWindow(
        String tenantId,
        String status,
        int page,
        int size,
        boolean includeTotal) {

    Mono<org.springframework.data.domain.Slice<OrderDocument>> sliceMono =
        findSlice(tenantId, status, page, size);

    if (!includeTotal) {
        return sliceMono.map(slice -> new OrderWindow(
            slice.getContent().stream().map(this::toRow).toList(),
            page,
            size,
            slice.hasNext(),
            null
        ));
    }

    Mono<Long> countMono =
        repository.countByTenantIdAndStatus(tenantId, status);

    return Mono.zip(sliceMono, countMono)
        .map(pair -> new OrderWindow(
            pair.getT1().getContent().stream().map(this::toRow).toList(),
            page,
            size,
            pair.getT1().hasNext(),
            pair.getT2()
        ));
}
~~~

Ví dụ trên là phương thức service minh họa, giả định **findSlice** và **repository** đã được cung cấp như ở những phần trước. Nếu includeTotal=false, nhánh này **không tạo hoặc subscribe countMono**. Nếu includeTotal=true, nó lấy thêm total qua một query riêng, và hai query có thể được subscribe đồng thời.

Phương thức **toRow(OrderDocument)** đã minh họa ở phần trước được sử dụng để chuyển entity thành DTO cho response. Cách này giữ ID chuỗi hex và chỉ công bố những field cần thiết; OrderWindow vì thế chứa **List<OrderRow>** thay vì entity đầy đủ.

Đây là một thiết kế hữu ích khi có hai kiểu client:

- **Mobile infinite scroll** chỉ cần items và hasNext.
- **Web quản trị** cần thêm totalElements để vẽ số trang hoặc thống kê.

Đừng trả **totalElements = 0** khi chưa đếm, bởi client có thể hiểu nhầm rằng không có bản ghi nào.

## 11. Vì sao offset pagination trở nên chậm ở trang sâu?

Với offset pagination, MongoDB phải xét các bản ghi trước vị trí skip để tìm đến trang hiện tại. Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(100000)
.limit(20);
~~~

Dù chỉ trả 20 document, MongoDB có thể phải đi qua rất nhiều index key trước khi đến offset 100.000. Projection nhỏ không tự loại chi phí skip sâu.

| Kiểu phân trang | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Offset + Pageable | Đơn giản, có thể yêu cầu trang số N | Skip lớn tốn chi phí; dễ lệch khi dữ liệu thay đổi. |
| Slice với size+1 | Biết hasNext không cần count | Vẫn chịu chi phí skip nếu dùng offset. |
| Keyset/seek | Tốt hơn cho “xem tiếp” trên tập lớn | Không nhảy trực tiếp đến trang số bất kỳ; cần cursor ổn định. |
| Stream/cursor batch | Phù hợp xử lý tuần tự nhiều record | Phải quản lý giới hạn, hủy, thời gian truy cập và thay đổi dữ liệu. |

Vì vậy, với API duyệt tuần tự dữ liệu rất lớn, hãy cân nhắc **keyset pagination** thay vì chỉ tối ưu projection.

## 12. Keyset pagination: tìm các bản ghi sau con trỏ

Giả sử sort theo **createdAt giảm dần**, sau đó **_id giảm dần**. Client đã nhận bản ghi cuối của cửa sổ trước có:

~~~text
lastCreatedAt = 2025-06-01T09:00:00Z
lastId = 507f1f77bcf86cd799439012
~~~

Cửa sổ tiếp theo phải lấy document:

- Có createdAt **nhỏ hơn** lastCreatedAt; **hoặc**
- Có createdAt **bằng** lastCreatedAt và _id **nhỏ hơn** lastId.

Trong mongosh:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  $or: [
    { createdAt: { $lt: ISODate("2025-06-01T09:00:00Z") } },
    {
      createdAt: ISODate("2025-06-01T09:00:00Z"),
      _id: { $lt: ObjectId("507f1f77bcf86cd799439012") }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(21);
~~~

Nếu size = 20, limit 21 vẫn giúp xác định hasNext. **Không sử dụng skip**, vì con trỏ đã xác định ranh giới của cửa sổ tiếp theo.

### 12.1. Viết bằng ReactiveMongoTemplate

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<OrderDocument> findAfter(
        ReactiveMongoTemplate template,
        String tenantId,
        String status,
        Instant lastCreatedAt,
        ObjectId lastId,
        int size) {

    if (size < 1 || size > 100) {
        return Flux.error(new IllegalArgumentException("Invalid size"));
    }

    Criteria after = new Criteria().orOperator(
        Criteria.where("createdAt").lt(lastCreatedAt),
        new Criteria().andOperator(
            Criteria.where("createdAt").is(lastCreatedAt),
            Criteria.where("_id").lt(lastId)
        )
    );

    Criteria filter = new Criteria().andOperator(
        Criteria.where("tenantId").is(tenantId),
        Criteria.where("status").is(status),
        after
    );

    Query query = Query.query(filter)
        .with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ))
        .limit(size + 1);

    return template.find(query, OrderDocument.class);
}
~~~

Đoạn code trả Flux tối đa size+1 phần tử. Caller có thể collectList rồi cắt size phần tử đầu để tạo next cursor và hasNext như phần Slice. Lần đầu chưa có cursor thì dùng filter tenant/status và cùng sort/limit, không dùng nhánh điều kiện **after**.

### 12.2. Vì sao cần khóa phụ _id?

Nếu hai Order có cùng createdAt và chỉ dùng createdAt làm cursor, điều kiện createdAt < lastTime có thể bỏ sót những document khác có cùng timestamp. Thêm _id làm khóa phụ giúp định nghĩa thứ tự tổng hợp và điều kiện seek nhất quán.

### 12.3. Hợp đồng cursor

Client nên coi cursor là một token không cần hiểu chi tiết. Server có thể encode:

- lastCreatedAt;
- lastId;
- phạm vi tenant và filter/sort được phép;
- phiên bản định dạng cursor.

Token cần được validate khi nhận lại; nếu có yêu cầu chống chỉnh sửa, có thể ký hoặc bảo vệ bằng cơ chế phù hợp. **Không tin tenantId tự khai trong cursor** khi chưa đối chiếu với ngữ cảnh xác thực.

Keyset pagination cần các trường sort ổn định. Nếu createdAt bị sửa hoặc document bị xóa/thêm giữa hai lần đọc, kết quả vẫn có thể thay đổi. Nó giảm nhiều vấn đề của offset sâu nhưng **không phải snapshot bất biến của toàn collection**.

## 13. Index cho filter và sort

Mẫu truy vấn phổ biến:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Một index đáng đánh giá:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Hai field tenantId và status là điều kiện bằng; createdAt và _id hỗ trợ thứ tự giảm dần. Index là **ứng viên phù hợp với query cụ thể**, không phải yêu cầu tạo tất cả index cho mọi truy vấn.

### 13.1. Dùng explain để kiểm chứng

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Khi chẩn đoán, quan sát:

| Chỉ số/thành phần | Cần hiểu |
| --- | --- |
| winningPlan | Có dùng index dự kiến không? |
| totalKeysExamined | Đã duyệt bao nhiêu index key? |
| totalDocsExamined | Đã phải fetch bao nhiêu document? |
| nReturned | Trả bao nhiêu bản ghi? |
| SORT stage | Có sắp xếp ngoài index không? |
| executionTimeMillis | Thời gian quan sát trong điều kiện test |

Với offset sâu, totalKeysExamined có thể lớn hơn nhiều so với nReturned dù query đã dùng index. Keyset giúp thu hẹp khoảng scan dựa trên điều kiện cursor, nhưng vẫn phải kiểm chứng bằng explain trên dữ liệu thực.

### 13.2. Count cũng cần filter và index phù hợp

Truy vấn đếm tương ứng:

~~~javascript
db.orders.countDocuments({
  tenantId: "shop-a",
  status: "PAID"
});
~~~

Count cần cùng phạm vi tenant, status và mọi filter business khác của truy vấn trang. Nếu thêm điều kiện soft-delete, khoảng thời gian hoặc phân quyền vào danh sách mà quên đưa vào count, **totalElements sẽ không còn đại diện cho danh sách**.

Đừng mặc định rằng countDocuments luôn rẻ vì kết quả chỉ là một số. Nó vẫn phải thực hiện một truy vấn; chi phí phụ thuộc điều kiện, index, dữ liệu và kế hoạch thực thi.

## 14. Dữ liệu thay đổi trong lúc phân trang

Giả sử trang đầu đã trả 20 Order mới nhất. Sau đó, một Order mới được insert với createdAt mới hơn tất cả. Khi client yêu cầu trang thứ hai bằng **skip(20)**, vị trí của các document đã thay đổi. Kết quả có thể **trùng một phần tử từ trang trước hoặc bỏ sót một phần tử**.

~~~mermaid
flowchart TD
    A["Trang 1: 20 đơn mới nhất"] --> B["Writer insert đơn mới vào đầu danh sách"]
    B --> C["Trang 2 dùng skip=20"]
    C --> D["Vị trí thay đổi → có thể trùng/bỏ sót"]
    B --> E["Trang 2 dùng keyset từ bản ghi cuối"]
    E --> F["Duyệt theo ranh giới sort đã nhận"]
~~~

Keyset dùng cursor của phần tử cuối giúp tránh việc một insert mới phía trước cursor làm dịch offset. Tuy nhiên, nó không ngăn document trong tập cũ bị cập nhật/xóa, cũng không tự đóng băng dữ liệu ở thời điểm trang đầu.

### 14.1. Count và items có thể không cùng thời điểm

Khi dùng:

~~~java
Mono.zip(
    repository.findByTenantIdAndStatus(
        tenantId, status, pageable
    ).collectList(),
    repository.countByTenantIdAndStatus(tenantId, status)
);
~~~

Hai publisher có thể quan sát trạng thái database khác nhau nếu có các giao dịch ghi đồng thời. **totalElements và items không nhất thiết khớp tuyệt đối**.

Đối với API thông thường, tính nhất quán gần đúng tại thời điểm đọc thường được chấp nhận. Nếu nghiệp vụ cần một ảnh chụp nhất quán chặt, phải thiết kế cách đọc có ngữ nghĩa snapshot/transaction phù hợp với MongoDB deployment và Spring Data reactive transaction manager. Chỉ gọi Mono.zip không tạo transaction.

### 14.2. Không coi count là bằng chứng tồn tại khi update

Một UI thấy totalElements = 10 không có nghĩa mười document đó vẫn tồn tại khi người dùng bấm “Xóa”. Các thao tác update/delete phải kiểm tra filter/ID, optimistic locking hoặc matchedCount theo nghiệp vụ, không dựa vào count của trang trước.

## 15. Reactive: subscription, backpressure, timeout và lỗi

### 15.1. Không gọi block() trên event loop

Không nên viết:

~~~java
// Tránh trong WebFlux/reactive service.
long total = repository.countByTenantIdAndStatus(
    tenantId, status
).block();
~~~

block() phá mô hình non-blocking và có thể gây tắc nghẽn event loop. Nếu cần total, giữ nó trong Mono và kết hợp bằng zip/flatMap.

### 15.2. Không collect toàn bộ collection

~~~java
// Không phù hợp khi collection lớn.
Mono<java.util.List<OrderDocument>> everything =
    repository.findAll().collectList();
~~~

**collectList() giữ tất cả phần tử trong bộ nhớ.** Chỉ nên dùng sau khi đã có limit chặt như Pageable size <= 100 hoặc size+1, hoặc khi biết chắc luồng đầu vào có kích thước nhỏ.

### 15.3. Giới hạn thời gian và xử lý lỗi

Một thao tác reactive có thể thất bại do mạng, server, lỗi ánh xạ, không đủ quyền hoặc timeout. Tầng API cần ánh xạ exception sang lỗi phù hợp, đồng thời giữ log/metrics hữu ích. Khi đặt timeout ở Reactor, cần hiểu nó ảnh hưởng tới subscription/cancellation và không thay thế cấu hình server-side query timeout.

Không tự động retry mọi truy vấn nặng với tần suất cao. Với các thao tác **chỉ đọc**, retry có thể phù hợp trong một số lỗi tạm thời nhưng phải có giới hạn và quan sát tải. Khi retry các luồng vừa đọc vừa ghi, cần có cơ chế idempotency độc lập.

### 15.4. Flux không phải stream dữ liệu vô hạn

Một Flux từ repository find có thể dùng cursor và phản hồi theo từng batch của driver. Nhưng khi caller yêu cầu một trang, nó vẫn là **truy vấn hữu hạn**. Hủy subscription nên giải phóng tài nguyên cursor theo cơ chế driver; đừng giữ các subscription không cần thiết hoặc subscribe nhiều lần chỉ để “kiểm tra” dữ liệu.

Mỗi subscription mới có thể thực hiện lại query. Vì vậy, nếu một request cần cả items và metadata, hãy tổ chức publisher một cách rõ ràng thay vì vô ý subscribe cùng Flux hai lần.

## 16. Count có những ngữ nghĩa nào?

Người phát triển thường nhầm ba câu hỏi:

1. **Có bao nhiêu document khớp filter?** — dùng count với filter (ví dụ countByTenantIdAndStatus).
2. **Có bao nhiêu phần tử trong trang vừa nhận?** — dùng kích thước content sau khi đọc trang.
3. **Có trang kế tiếp không?** — đọc size+1 rồi kiểm tra phần tử dư, hoặc dùng total khi nó đã được tính.

Chúng không đồng nhất.

Ví dụ với 105 đơn khớp filter, size = 20, page = 5 (trang thứ sáu, bắt đầu từ 0):

| Giá trị | Kết quả |
| --- | --- |
| totalElements | 105 |
| totalPages | 6 |
| Offset trang 5 | 100 |
| Số item ở trang 5 | 5 |
| hasNext ở trang 5 | false |

Nếu client chỉ muốn cuộn thêm, **hasNext** thường đã đủ. Nếu cần ghi “105 đơn hàng”, phải chạy truy vấn count hoặc có một nguồn số liệu được quản lý riêng và ghi rõ mức độ chính xác.

### 16.1. Count chính xác và số ước lượng

**countDocuments(filter)** đếm theo điều kiện trên dữ liệu mà query nhìn thấy, nhưng vẫn chịu ảnh hưởng của thời điểm chạy và transaction/write concurrency. Những kỹ thuật đếm ước lượng hoặc cache count có thể nhanh hơn ở một số workload nhưng không nên được gọi là “total chính xác” nếu có độ trễ cập nhật.

Không thay thế count có filter bằng **estimatedDocumentCount** của toàn collection: nó không trả tổng số riêng cho tenant/status cụ thể.

### 16.2. Khi nào cache count?

Nếu dashboard chấp nhận số cập nhật chậm một khoảng thời gian, có thể cache hoặc duy trì thống kê riêng. Cần quy định:

- Khóa cache bao gồm các filter/tenant cần thiết.
- TTL hoặc cơ chế invalidation rõ ràng.
- API nêu rõ số liệu là gần đúng hay gần thời gian thực.
- Số liệu không được dùng thay thế bất biến nghiệp vụ hoặc điều kiện phân quyền.

## 17. Dùng @Query với Flux và Pageable

Derived query không phải lựa chọn duy nhất. Có thể khai báo filter BSON tường minh:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.Query;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface OrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {

    @Query("{ 'tenantId': ?0, 'status': ?1 }")
    Flux<OrderDocument> findForTenantAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );

    @Query(
        value = "{ 'tenantId': ?0, 'status': ?1 }",
        count = true
    )
    Mono<Long> countForTenantAndStatus(
        String tenantId,
        String status
    );
}
~~~

Trong ví dụ, **?0** và **?1** được bind theo thứ tự, còn Pageable là tham số đặc biệt để áp dụng phân trang. Không cần bind Pageable như một giá trị field trong JSON.

**Phải giữ hai filter tương đương**. Nếu truy vấn dữ liệu có điều kiện khoảng thời gian, trạng thái soft-delete hoặc quyền tenant, count cũng phải áp dụng những điều kiện đó. Với logic filter linh hoạt rất nhiều nhánh, có thể dùng ReactiveMongoTemplate hoặc một query builder để tránh hai nơi định nghĩa filter bị lệch nhau.

## 18. DTO kết quả và API WebFlux

API nên quyết định rõ có trả total hay không. Ví dụ response cho chế độ “xem thêm”:

~~~json
{
  "items": [
    {
      "id": "507f1f77bcf86cd799439011",
      "orderNumber": "ORD-1001",
      "createdAt": "2025-06-01T10:00:00Z",
      "totalMinor": 159000
    }
  ],
  "page": 0,
  "size": 20,
  "hasNext": true
}
~~~

Khi client yêu cầu total, có thể thêm:

~~~json
{
  "items": [],
  "page": 6,
  "size": 20,
  "hasNext": false,
  "totalElements": 105
}
~~~

Hai JSON chỉ minh họa cấu trúc response ở các tình huống riêng, không mô tả cùng một snapshot dữ liệu. Ví dụ thứ hai cố ý yêu cầu **page=6**, vượt quá trang cuối của tập 105 phần tử (các trang hợp lệ là 0–5), nên mảng items rỗng dù totalElements vẫn là 105. Với contract API, cần nhất quán về việc **totalElements vắng mặt** hay **null** khi không tính.

### 18.1. Controller không cần block()

Một controller WebFlux có thể trả trực tiếp Mono:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrderController {
    private final OrderWindowService service;

    public OrderController(OrderWindowService service) {
        this.service = service;
    }

    @GetMapping("/orders")
    public Mono<OrderWindow> getOrders(
            @RequestParam String status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(defaultValue = "false") boolean includeTotal) {

        // tenantId cần lấy từ ngữ cảnh xác thực của request.
        String tenantId = authenticatedTenantId();

        return service.findWindow(
            tenantId, status, page, size, includeTotal
        );
    }
}
~~~

Ví dụ trên minh họa **chữ ký controller và cách trả publisher**, không phải một controller copy-paste hoàn chỉnh: authenticatedTenantId() là một hàm giả định cần được triển khai bằng cơ chế xác thực của hệ thống, và OrderWindowService phải cung cấp findWindow như phần trước. Không lấy tenantId trực tiếp từ query parameter rồi tin đó là phạm vi dữ liệu của người dùng.

Trong WebFlux, framework subscribe publisher và serialize response sau khi Mono phát ra kết quả; controller không nên tự gọi subscribe() hoặc block().

## 19. Kiểm thử phân trang reactive

Kiểm thử đơn vị chỉ mock repository có thể xác minh cách gọi Pageable và count, nhưng **không xác minh filter, sort, skip/limit hoặc BSON mapping trên MongoDB thực**. Với module này, nên có kiểm thử tích hợp dùng MongoDB test instance riêng, chẳng hạn Testcontainers.

Các hành vi cần kiểm tra:

| Kịch bản | Kỳ vọng |
| --- | --- |
| size=2, có 5 bản ghi khớp | Trang 0 trả tối đa 2, trang 1 trả tối đa 2, trang 2 trả 1. |
| Hai Order có createdAt trùng nhau | Sort bổ sung id tạo thứ tự xác định. |
| Có dữ liệu của shop-a và shop-b | shop-a không thấy Order của shop-b. |
| Chỉ subscribe Flux trang | Không tự kích hoạt count query. |
| includeTotal=false | Response không có totalElements hoặc total null theo contract. |
| includeTotal=true | Count được gọi riêng và phản ánh cùng filter. |
| Đọc size+1 | Trả tối đa size items, hasNext đúng tại thời điểm query. |
| Trang vượt cuối danh sách | Flux hoàn thành rỗng, Slice hasNext=false. |
| page âm hoặc size > max | Báo lỗi validation. |
| Client hủy subscription | Không tự tạo truy vấn bổ sung ngoài đường đã subscribe. |
| Offset lớn | Được đo/giới hạn; cân nhắc keyset. |
| Count và page dưới concurrent writes | Không kỳ vọng snapshot tuyệt đối nếu chưa có cơ chế nhất quán riêng. |

### 19.1. Dùng StepVerifier

Ví dụ kiểm thử giới hạn một Flux có sắp xếp:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import reactor.test.StepVerifier;

@SpringBootTest
class ReactiveOrderPaginationTest {

    @Autowired
    OrderRepository repository;

    @Test
    void returnsAtMostRequestedPageSize() {
        var pageable = PageRequest.of(
            0, 2,
            Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            )
        );

        StepVerifier.create(
            repository.findByTenantIdAndStatus(
                "test-tenant", "PAID", pageable
            ).collectList()
        )
        .assertNext(rows -> {
            assertThat(rows).hasSizeLessThanOrEqualTo(2);
        })
        .verifyComplete();
    }
}
~~~

Test trên là **minh họa giới hạn**; để kiểm tra phân trang thực sự, phải seed các document test có tenantId riêng và timestamp/ID kiểm soát được. Nếu không seed dữ liệu, kết quả rỗng vẫn vượt qua assert size <= 2 và test chưa chứng minh đúng dữ liệu.

### 19.2. Fixture đầy đủ và thử thứ tự

Một test tích hợp đáng tin cậy nên:

1. Sinh tenantId ngẫu nhiên cho riêng test.
2. Insert ít nhất 5 Order có trạng thái PAID, gồm hai bản ghi có cùng createdAt.
3. Insert ít nhất một Order của tenant khác và một Order trạng thái khác.
4. Yêu cầu page=0,size=2 rồi page=1,size=2.
5. So sánh thứ tự createdAt DESC và id DESC, không chỉ đếm số phần tử.
6. Kiểm tra countByTenantIdAndStatus trả đúng số Order đã seed.
7. Kiểm tra Slice đọc size+1 trả hasNext=true/false đúng.
8. Dọn dữ liệu theo tenantId sau test, **chỉ trên database test**.

### 19.3. Test xác nhận count chỉ chạy khi cần

Có thể unit test service bằng mock repository:

~~~java
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void pageOnlyDoesNotInvokeCount() {
    when(repository.findByTenantIdAndStatus(
        eq("shop-a"), eq("PAID"), any()
    )).thenReturn(Flux.empty());

    StepVerifier.create(
        service.page("shop-a", "PAID", 0, 20)
    ).verifyComplete();

    verify(repository, never())
        .countByTenantIdAndStatus(anyString(), anyString());
}
~~~

Ví dụ giả định repository và service là mock/SUT đã được khởi tạo trong lớp test; các import Mockito và Reactor Test được cấu hình trong dự án. Unit test này xác minh service chỉ dùng Flux, còn kiểm thử tích hợp mới chứng minh MongoDB áp dụng Pageable đúng.

### 19.4. Kiểm tra bằng mongosh

Đối chiếu truy vấn thực:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(40)
.limit(21);

db.orders.countDocuments({
  tenantId: "shop-a",
  status: "PAID"
});
~~~

Hai lệnh trên cho phép chẩn đoán sự khác nhau giữa dữ liệu cửa sổ và tổng số document. Chúng không có bảo đảm chạy trên cùng snapshot khi được gọi riêng lẻ.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Flux trả một trang nhưng không có total | Flux không mang Page metadata | Gọi count riêng nếu UI cần. |
| Trang nào cũng chạy count chậm | Dùng Page mặc định dù chỉ cần nút “Xem thêm” | Trả Flux/Slice, count theo yêu cầu. |
| hasNext=true dù đây là trang cuối | Dựa vào rows.size()==size | Đọc size+1 hoặc dùng total đã tính. |
| Trang 2 bắt đầu sai vị trí | Dùng PageRequest.of(page,size+1) | Giữ offset từ size gốc rồi tăng limit. |
| Một Order lặp ở hai trang | Thiếu sort ổn định hoặc concurrent writes | Sort có khóa phụ _id; xem keyset. |
| Trang sâu phản hồi rất chậm | MongoDB phải skip lượng lớn | Đo explain và dùng seek/keyset khi phù hợp. |
| totalElements khác số items mong đợi | Count filter thiếu điều kiện hoặc dữ liệu thay đổi đồng thời | Đồng bộ filter, hiểu giới hạn snapshot. |
| API trả đơn tenant khác | Thiếu filter tenant / tin tenant đầu vào | Lấy tenant từ auth, kiểm soát mọi truy vấn. |
| Ứng dụng tăng bộ nhớ mạnh | collectList trên Flux chưa giới hạn | Limit ở server trước khi collect. |
| WebFlux bị block | Gọi .block() trong service/controller | Kết hợp Mono/Flux bằng Reactor operators. |
| Count ra số đúng nhưng trang rỗng | Page index vượt cuối hoặc dữ liệu mới bị xóa | Kiểm tra offset, số trang bắt đầu từ 0. |
| Query chậm dù có index | Index không phù hợp filter/sort, offset sâu | Xem winningPlan/keysExamined/docsExamined. |
| Test luôn pass dù paging sai | Không seed dữ liệu hoặc chỉ assert số lượng <= size | Seed fixture, assert đúng thứ tự và hasNext. |
| Flux bị query lại hai lần | Có hai subscription độc lập | Thiết kế composition rõ, tránh subscribe lặp. |

## 21. Bài tập thực hành

### Bài tập 1: repository Flux và count

Viết hai method để tìm Order trạng thái PAID của một tenant theo Pageable và đếm các Order cùng filter.

**Gợi ý đáp án:**

~~~java
Flux<OrderDocument> findByTenantIdAndStatus(
    String tenantId, String status, Pageable pageable
);

Mono<Long> countByTenantIdAndStatus(
    String tenantId, String status
);
~~~

### Bài tập 2: biết hasNext mà không count

Client yêu cầu page=3,size=25. Truy vấn đọc bao nhiêu bản ghi và skip bao nhiêu?

**Đáp án:** offset **3 * 25 = 75**, limit **26**; chỉ trả tối đa 25 items. Nếu query trả 26 bản ghi thì hasNext=true. Không dùng PageRequest.of(3,26) vì nó sẽ tạo offset 78.

### Bài tập 3: có cần total không?

API mobile chỉ hiển thị danh sách và nút “Xem thêm”. Có cần gọi countByTenantIdAndStatus ở mỗi request?

**Đáp án:** không. Dùng Slice/size+1 hoặc keyset với một bản ghi dư để biết còn trang tiếp theo.

### Bài tập 4: vì sao sort cần _id?

Hai Order có cùng createdAt, cả hai thuộc status PAID. Nếu chỉ sort theo createdAt, có thể xảy ra điều gì?

**Đáp án:** thứ tự giữa các bản ghi có cùng createdAt không được xác định ổn định. Bổ sung _id làm khóa phụ và dùng cùng thứ tự trong mọi truy vấn/cursor.

### Bài tập 5: concurrent writes và total

Mono.zip ghép Flux trang và Mono<Long> count. Có phải hai kết quả luôn đến từ cùng snapshot không?

**Đáp án:** không. Đây là hai truy vấn riêng, có thể quan sát dữ liệu ở những thời điểm khác nhau. Cần transaction/snapshot read phù hợp nếu hợp đồng đòi hỏi tính nhất quán mạnh.

### Bài tập 6: phân trang sâu

Một trang ở offset 500.000 chạy rất chậm dù chỉ trả 20 bản ghi. Đề xuất giải pháp?

**Gợi ý đáp án:** đo explain, tối ưu index theo filter và sort, cân nhắc keyset/seek pagination với createdAt và _id thay vì skip lớn; giới hạn page quá sâu nếu API không cần nhảy trang tùy ý.

### Bài tập 7: reactive anti-pattern

~~~java
List<OrderDocument> all =
    repository.findAll().collectList().block();
~~~

**Câu hỏi:** vì sao đây không phải phân trang reactive phù hợp?

**Đáp án:** nó tải toàn bộ dữ liệu vào bộ nhớ, chặn luồng bằng block và không áp dụng limit ở MongoDB. Dùng Flux có Pageable hoặc Query với sort/limit, xử lý Mono/Flux không blocking.

### Bài tập 8: count sai filter

Danh sách lọc tenantId, status và deleted=false, nhưng count chỉ lọc tenantId và status. totalElements có đáng tin không?

**Đáp án:** không, vì count đang thống kê tập rộng hơn dữ liệu trang. Phải áp dụng cùng mọi điều kiện phân quyền và nghiệp vụ.

### Bài tập 9: keyset cursor

Sort createdAt DESC và _id DESC. Cursor cuối có createdAt=T, _id=I. Viết điều kiện lấy trang tiếp theo.

**Đáp án:** lấy document có **createdAt < T** hoặc **createdAt = T và _id < I**, đồng thời giữ nguyên filter tenant/status, sort và limit size+1.

## 22. Nguyên tắc cần ghi nhớ

1. **Flux là luồng phần tử, không phải Page** và không có totalElements tự động.
2. **Pageable/skip/limit/sort phải được đẩy xuống MongoDB**, không tải toàn bộ Flux rồi mới cắt ở Java.
3. **Đếm là một truy vấn riêng**; Mono<Long> chỉ cần được subscribe khi client thật sự cần total.
4. **Mono.zip(data.collectList(), count)** có thể tạo Page, nhưng hai query không tự chia sẻ snapshot.
5. **Slice đọc size+1** giúp biết hasNext mà không count; giữ offset theo page * size, không theo size+1.
6. **Sort cần khóa phụ ổn định** như _id để giảm rủi ro trùng/bỏ sót giữa các trang.
7. **Offset sâu có chi phí**, keyset/seek thường phù hợp hơn với thao tác “tải tiếp” trên dữ liệu lớn.
8. **Index phải khớp filter và sort**; dùng explain("executionStats") để xác nhận thay vì phỏng đoán.
9. **Không block() trong luồng WebFlux**, không collectList một query không giới hạn và không subscribe trùng vô tình.
10. **Filter của count phải giống filter của dữ liệu trang**, nhất là tenant, trạng thái, soft-delete và quyền truy cập.
11. **Kiểm thử bằng StepVerifier và MongoDB test** để xác nhận thứ tự, giới hạn, hasNext, count và phản ứng khi dữ liệu thay đổi.

Nắm chắc cách **phân trang reactive bằng Flux và phép đếm riêng khi cần** giúp dịch vụ **SPRING_DATA_MONGODB** xây dựng API phản hồi gọn, không blocking, tối ưu chi phí truy vấn và chủ động lựa chọn giữa danh sách trang, Slice có hasNext và Page có tổng số theo đúng yêu cầu nghiệp vụ.
