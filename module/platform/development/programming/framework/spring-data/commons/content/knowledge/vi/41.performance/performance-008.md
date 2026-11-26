# Giới hạn truy vấn lặp do quan hệ hoặc projection theo store

## 1. Nhìn toàn bộ đường đọc, không chỉ lời gọi repository

Trong chương **Hiệu năng** của module **SPRING_DATA_COMMONS**, một lời gọi repository có thể kéo theo nhiều thao tác đọc khác khi ứng dụng truy cập quan hệ, getter projection, mapper hoặc serializer.

Ví dụ màn hình liệt kê 50 đơn hàng cần tên khách hàng. Ứng dụng đọc danh sách đơn bằng một query, sau đó duyệt từng đơn và đọc khách tương ứng. Nếu mỗi đơn trỏ đến một khách chưa được tải, có thể xuất hiện thêm nhiều query nhỏ.

Đây thường được gọi là vấn đề **N+1**: một truy vấn ban đầu và các truy vấn phụ phát sinh theo số đối tượng cần đọc thêm. Con số thực tế không luôn bằng đúng N+1 vì còn cache, khách dùng chung, batch loading và chiến lược của store.

Mục tiêu là giới hạn lượng công việc phát sinh cho một ca sử dụng:

- Số query hoặc command trong phạm vi được đo.
- Số dòng/document và field được tải.
- Số vòng trao đổi với backend.
- Thời gian, bộ nhớ và áp lực lên connection pool.

Một API trả về projection nhỏ chưa tự bảo đảm truy vấn ít. Một câu join duy nhất cũng chưa tự bảo đảm tổng chi phí thấp.

Bài dùng **Java 17, Spring Data JPA 3.5 và Hibernate 6.6** cho ví dụ SQL; sau đó đối chiếu MongoDB, JDBC và R2DBC theo khả năng riêng.

## 2. Tách nguồn truy vấn lặp và đơn vị đo

### 2.1. Một mô hình đếm đơn giản

Gọi:

- N: số đơn hàng được trả về.
- K: số khách khác nhau cần đọc nhưng chưa có trong phạm vi cache đang xét.
- B: số ID trong mỗi đợt lookup tường minh.
- Q: số truy vấn logic của đường đọc đang phân tích.

Trong một mô hình đơn giản:

~~~text
Lookup từng khách:       Q ≈ Q_gốc + K
Lookup theo từng đợt:    Q ≈ Q_gốc + ceil(K / B)
DTO join phù hợp:        Q có thể không tăng theo K
~~~

Đây là mô hình giải thích, không phải công thức bắt buộc của mọi implementation. COUNT cho Page, truy vấn lồng thêm cấp quan hệ hoặc cơ chế đọc cursor có thể tạo công việc khác.

Ví dụ giả định Q_gốc = 1 và lookup tường minh tối đa 20 ID mỗi đợt:

| N | K | Lookup từng khách | Lookup theo đợt 20 ID |
| --- | --- | --- | --- |
| 10 | 10 | 11 | 2 |
| 100 | 100 | 101 | 6 |
| 100 | 3 | 4 | 2 |

Các số chỉ minh họa mô hình, chưa phải kết quả benchmark.

### 2.2. Những nơi có thể làm phát sinh đọc thêm

| Điểm phát sinh | Ví dụ |
| --- | --- |
| Quan hệ entity | Đọc customer.name cho từng order |
| Getter projection | Getter lồng truy cập quan hệ chưa được nạp |
| Biểu thức tính toán | SpEL sử dụng thuộc tính khác của target |
| Mapper | Sau khi query xong, mapper gọi repository cho từng dòng |
| Serializer hoặc logging | Duyệt getter quan hệ khi tạo response hoặc toString |
| Callback, fragment tùy chỉnh | Thực hiện lookup riêng trong từng phần tử |
| Pipeline reactive | Mỗi phần tử gọi một publisher truy vấn khác |

Tối ưu query gốc sẽ không loại được lookup nằm trong mapper nếu đường gọi đó vẫn giữ nguyên.

### 2.3. Query khác với round trip

Một query trả nhiều dữ liệu có thể cần nhiều lần vận chuyển kết quả. Với MongoDB, command đọc cursor tiếp theo cũng cần được phân biệt với những lookup riêng cho quan hệ.

Vì vậy, phải ghi rõ đang đếm SQL statement, query logic, command của driver hay số lần trao đổi mạng. Không so sánh hai chỉ số khác định nghĩa như thể chúng là một.

## 3. Ví dụ JPA: danh sách đơn hàng và tên khách

Các public type được đặt trong các file Java riêng, cùng package `example.orders`. Ứng dụng đã cấu hình JPA, repository và backend phù hợp.

### 3.1. Entity tối thiểu

~~~java
package example.orders;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_record")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

~~~java
package example.orders;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    private String status;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String status, Customer customer) {
        this.status = status;
        this.customer = customer;
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }
}
~~~

### 3.2. DTO phục vụ màn hình

~~~java
package example.orders;

public record OrderCard(Long id, String customerName) {
}
~~~

### 3.3. Repository có các đường đọc để đối chiếu

~~~java
package example.orders;

import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatusOrderByIdAsc(
            String status);

    @EntityGraph(attributePaths = "customer")
    List<PurchaseOrder>
    findWithCustomerByStatusOrderByIdAsc(String status);

    @Query(
            value = """
                    select new example.orders.OrderCard(
                        o.id, c.name)
                      from PurchaseOrder o
                      join o.customer c
                     where o.status = :status
                     order by o.id asc
                    """,
            countQuery = """
                    select count(o)
                      from PurchaseOrder o
                      join o.customer c
                     where o.status = :status
                    """)
    Page<OrderCard> findCardsByStatus(
            @Param("status") String status,
            Pageable pageable);
}
~~~

Hai method trả List giúp minh họa khác biệt fetch plan; với dữ liệu lớn, caller vẫn cần giới hạn số root được đọc. Đường DTO phía dưới có phân trang ngay tại query.

### 3.4. Cách đọc có thể tạo truy vấn lặp

~~~java
package example.orders;

import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderLookup {

    private final OrderRepository repository;

    public OrderLookup(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<OrderCard> listNaively(String status) {
        return repository.findByStatusOrderByIdAsc(status)
                .stream()
                .map(order -> new OrderCard(
                        order.getId(),
                        order.getCustomer().getName()))
                .toList();
    }
}
~~~

Transaction bao quanh cả query và mapping cho phép việc đọc lazy xảy ra trong phạm vi được quản lý. Nó không tự làm các lần đọc đó được gộp lại.

Trong fixture lạnh với khách khác nhau, getter customer.name có thể kéo theo query phụ. Nếu tất cả đơn cùng một khách, cache trong persistence context có thể làm số query nhỏ hơn; fixture đó không đủ để bộc lộ trường hợp xấu.

Đổi quan hệ thành EAGER không phải giải pháp chung bảo đảm một query. Fetch strategy thực tế còn tùy đường query và provider. Xem [Fetching trong Hibernate ORM 6.6](https://docs.hibernate.org/orm/6.6/userguide/html_single/#fetching).

## 4. Chọn biện pháp JPA theo dữ liệu cần dùng

### 4.1. Entity graph khi cần entity cùng quan hệ

Method `findWithCustomerByStatusOrderByIdAsc` khai báo customer là thuộc tính cần fetch cho đường đọc đó.

Đây là cách thể hiện fetch plan tại một ca truy vấn thay vì đổi mọi nơi sử dụng entity. Spring Data JPA hỗ trợ graph được đặt tên và graph khai báo bằng `attributePaths`. Xem [Configuring Fetch- and LoadGraphs](https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/query-methods.html#jpa.entity-graph).

Graph không phải cam kết portable rằng mọi provider luôn tạo đúng một SQL. Cần quan sát SQL và dữ liệu được tải trong cấu hình thực tế.

Khi dùng entity, vẫn cần cân nhắc độ rộng của Customer được nạp. Màn hình chỉ dùng name có thể không cần toàn bộ trạng thái khách.

### 4.2. DTO phẳng khi chỉ cần một read model nhỏ

Method `findCardsByStatus` chọn trực tiếp ID đơn và tên khách. Nó không cần dựng từng PurchaseOrder rồi gọi getter customer để tạo card.

Một service giới hạn kích thước trang:

~~~java
package example.orders;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCardService {

    private final OrderRepository repository;

    public OrderCardService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<OrderCard> list(
            String status,
            int page,
            int size) {

        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "Trang không hợp lệ hoặc vượt giới hạn");
        }

        return repository.findCardsByStatus(
                status,
                PageRequest.of(page, size));
    }
}
~~~

Giới hạn 100 là chính sách minh họa của ứng dụng, cần chọn theo kích thước mỗi dòng và mục tiêu vận hành.

`Page` có thể cần thêm query tính total. Nếu caller chỉ cần biết còn trang tiếp theo, cân nhắc `Slice` khi module và query tương ứng hỗ trợ. Không xóa total khỏi hợp đồng của caller chỉ để giảm một query. Các lựa chọn kết quả được mô tả trong [Query Methods Details của Commons](https://docs.spring.io/spring-data/commons/reference/3.5/repositories/query-methods-details.html).

### 4.3. Batch fetching khi vẫn cần đi qua entity

Hibernate hỗ trợ batch fetching cho entity hoặc collection, chẳng hạn:

~~~java
@org.hibernate.annotations.BatchSize(size = 32)
~~~

Annotation được đặt trên entity hoặc vị trí collection thích hợp theo cấu hình. Nó cho phép tải nhiều proxy/collection chưa nạp trong một đợt, dựa vào các đối tượng liên quan đến session. Xem [API BatchSize](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/BatchSize.html).

Đây là tối ưu của Hibernate, không phải khả năng chung bắt buộc của Commons. Nó giảm số lookup trong nhiều tình huống, nhưng không có nghĩa mọi đường đọc trở thành một query.

Cần chọn batch size theo giới hạn tham số, độ rộng dữ liệu và lượng đối tượng thực sự được dùng; không tăng vô hạn chỉ để làm số statement nhỏ đi.

## 5. Không dùng join collection một cách máy móc

Quan hệ to-one của ví dụ khác việc lấy đồng thời nhiều collection.

Nếu một đơn có nhiều dòng hàng và nhiều nhãn, join cả hai có thể nhân số dòng SQL. Ứng dụng nhận ít entity root sau khử trùng nhưng database và mạng vẫn phải xử lý tập dòng lớn.

Với phân trang root, fetch join collection còn có thể làm việc giới hạn ở backend không tương ứng với số root mong muốn. Không coi `distinct` là cách tự động sửa mọi vấn đề về phân trang hoặc lượng dữ liệu join.

Một hướng đọc hai giai đoạn:

~~~text
1. Query trang ID root với filter và thứ tự ổn định.
2. Query dữ liệu/quan hệ cần thiết cho tập ID đó.
3. Ghép kết quả theo thứ tự của trang root.
~~~

Query thứ hai cần giữ phạm vi dữ liệu phù hợp, chẳng hạn tenant. Danh sách IN không tự giữ thứ tự của query thứ nhất.

Hai giai đoạn cũng cần chính sách nhất quán dữ liệu nếu có cập nhật giữa các lần đọc. Số query có thể được giới hạn rõ hơn, nhưng không nên đổi hành vi nghiệp vụ một cách ngầm định.

## 6. Projection không tự ngăn truy vấn lặp

### 6.1. Getter lồng cần được đánh giá theo store

Ví dụ hình dạng view:

~~~java
public interface OrderView {

    Long getId();

    CustomerView getCustomer();

    interface CustomerView {

        String getName();
    }
}
~~~

Interface nhỏ không tự chứng minh query chỉ chọn một vài cột hoặc không có đọc thêm. Cách backing object được tạo và cách store xử lý quan hệ mới quyết định đường đọc.

Spring Data JPA giới hạn projection ở thuộc tính cấp trên cùng; property lồng cần join có thể làm phần quan hệ được materialize rộng hơn. Xem [Projections của Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/3.5/repositories/projections.html).

### 6.2. Getter tính toán có thể chạm dữ liệu khác

Một open projection dùng biểu thức như target.customer.name có thể cần truy cập quan hệ của target. Một mapper gọi customerRepository.findById cho từng order cũng tạo lookup riêng dù DTO cuối cùng chỉ có hai field.

Tương tự, Query by Example giúp mô tả điều kiện tìm kiếm; nó không phải tuyên bố về việc các quan hệ được fetch bằng một query.

Nếu projection chỉ nhằm phục vụ đọc, thường dễ kiểm soát hơn khi chọn read model phẳng cùng query rõ ràng cho những field cần thiết. Nếu cần view lồng, hãy đo cả lúc consumer truy cập nó.

### 6.3. Phạm vi đo phải bao gồm sử dụng kết quả

~~~text
Bắt đầu đo
    -> repository
    -> truy cập getter cần dùng
    -> mapper / serializer thực tế
Kết thúc đo
~~~

Chỉ đếm đến thời điểm repository trả về có thể bỏ sót query phát sinh khi render response. Logging và công cụ debug gọi getter cũng có thể làm thay đổi thời điểm tải dữ liệu.

Không dùng việc mở rộng thời gian sống của session để che lỗi đọc ngoài transaction như một bằng chứng rằng N+1 đã được giải quyết.

## 7. MongoDB: xem cách tham chiếu được resolve

### 7.1. Embedded data khác reference

Dữ liệu được embed trong document gốc có thể được đọc cùng document đó. Reference trỏ sang document khác cần được đánh giá theo cơ chế resolve và query thực tế.

Với DBRef, Spring Data MongoDB hỗ trợ eager/lazy resolution. Tài liệu khuyến nghị các reference trong collection cùng trỏ đến một MongoDB collection để có thể bulk load; reference đến collection khác nhau có thể phải resolve riêng.

Lazy chỉ trì hoãn thời điểm đọc đến lúc property được truy cập. Nó không tự gộp mọi reference của mọi root trong một request thành một lookup chung. Xem [Using DBRefs và Document References](https://docs.spring.io/spring-data/mongodb/reference/4.5/mongodb/mapping/document-references.html).

`@DocumentReference` có cơ chế lookup riêng. Không chuyển nguyên dự đoán số query của JPA hoặc DBRef sang document reference mà chưa quan sát.

### 7.2. Lookup tường minh theo tập ID

Một hướng kiểm soát dễ thấy là đọc trang order chứa customerId, gom các ID khác nhau rồi lấy tên khách theo từng đợt.

DTO dùng cho nhánh MongoDB, ở package riêng:

~~~java
package example.mongo;

import org.springframework.data.annotation.Id;

public record CustomerName(@Id String id, String name) {
}
~~~

Adapter minh họa một đợt tối đa 100 ID:

~~~java
package example.mongo;

import java.util.Collection;
import java.util.List;
import java.util.Set;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class CustomerNameLookup {

    private final MongoTemplate template;

    public CustomerNameLookup(MongoTemplate template) {
        this.template = template;
    }

    public List<CustomerName> load(
            String tenantId,
            Collection<String> customerIds) {

        Set<String> ids = Set.copyOf(customerIds);

        if (ids.isEmpty()) {
            return List.of();
        }

        if (ids.size() > 100) {
            throw new IllegalArgumentException(
                    "Mỗi đợt chỉ nhận tối đa 100 ID");
        }

        Query query = Query.query(
                Criteria.where("_id").in(ids)
                        .and("tenantId").is(tenantId));

        query.fields().include("_id").include("name");

        return template.find(
                query,
                CustomerName.class,
                "customers");
    }
}
~~~

Ví dụ giả định collection customers lưu ID chuỗi và tenantId theo mapping trên. Con số 100 là giới hạn minh họa, không phải giới hạn chung của MongoDB.

Caller tạo Map từ ID sang tên rồi ghép lại theo thứ tự danh sách order ban đầu. Không dựa vào thứ tự kết quả của truy vấn IN. Cũng cần quyết định rõ khi reference không còn tồn tại: bỏ dòng, để giá trị thiếu hoặc trả lỗi theo hợp đồng nghiệp vụ.

Nếu số ID vượt một đợt, chia thành các đợt có giới hạn. Số lookup khi đó phụ thuộc số đợt và số ID khác nhau, thay vì một query riêng cho mỗi order.

### 7.3. Aggregation hoặc read model khi phù hợp

MongoDB có `$lookup` để kết hợp dữ liệu từ collection khác trong aggregation. Nó có thể thay các lookup phía ứng dụng bằng xử lý phía server, nhưng vẫn cần đánh giá điều kiện lọc, index, lượng document và kết quả trung gian.

Xem [tài liệu $lookup của MongoDB](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/). Một aggregation command không đồng nghĩa chi phí backend luôn thấp hơn mọi phương án khác.

Một lựa chọn khác là lưu thông tin hiển thị ngay trên order/read model. Khi đó phải xác định tên khách là snapshot lúc tạo đơn hay phải phản ánh tên hiện tại. Nếu cần dữ liệu hiện tại, còn có chi phí và độ trễ đồng bộ.

Không thay đổi ý nghĩa dữ liệu chỉ để loại một lookup khỏi đường đọc.

## 8. JDBC và R2DBC cần cách phân tích riêng

### 8.1. Spring Data JDBC tải aggregate theo mô hình của nó

Không dùng giả định lazy session của JPA để phân tích mọi repository JDBC. Trong cách tải truyền thống, root có entity được tham chiếu trong aggregate có thể cần các statement riêng để tải đầy đủ.

Spring Data JDBC có Single Query Loading, nhưng khả năng này phụ thuộc phiên bản, cấu trúc aggregate, dialect, loại find method và việc bật cấu hình. Với dòng 3.5, không được suy rằng mọi derived query hoặc annotated query đều sử dụng nó.

Khi điều kiện không phù hợp, có thể quay về cơ chế tải mặc định. Xem [Loading Aggregates của Spring Data JDBC](https://docs.spring.io/spring-data/relational/reference/3.5/jdbc/entity-persistence.html).

Với màn hình chỉ cần một phần dữ liệu, một query/read model rõ ràng có thể phù hợp hơn việc tải aggregate đầy đủ rồi bỏ phần lớn dữ liệu.

### 8.2. R2DBC: bất đồng bộ không tự giảm số query

Một pipeline gọi customerRepository.findById cho mỗi order vẫn tạo các thao tác lookup tương ứng khi được thực thi.

Giới hạn concurrency giúp kiểm soát số lookup đồng thời; nó không tự đổi các lookup đó thành một câu IN. Tăng concurrency có thể làm tổng thời gian giảm trong một phép đo nhỏ nhưng tăng tải backend hoặc connection pool.

Khi cần gom theo đợt, lựa chọn gồm query join/projection phù hợp, gom ID theo cửa sổ có giới hạn rồi lookup, hoặc read model đã có dữ liệu cần đọc.

Cần kiểm soát cả kích thước buffer và số đợt đồng thời. Gom toàn bộ một luồng không giới hạn vào bộ nhớ để “batch một lần” tạo ra một vấn đề khác.

R2DBC thực thi các thao tác được mô tả bởi publisher khi có subscription. Phạm vi đo phải bao gồm việc tiêu thụ kết quả. Xem [Persisting Entities của Spring Data R2DBC](https://docs.spring.io/spring-data/relational/reference/3.5/r2dbc/entity-persistence.html).

## 9. Đặt ngân sách theo một ca sử dụng có giới hạn

Một ngân sách hữu ích phải chỉ rõ đầu vào và phạm vi đo.

Ví dụ thiết kế:

| Đường đọc | Giới hạn dữ liệu | Ngân sách cần xác minh |
| --- | --- | --- |
| DTO JPA của ví dụ | Tối đa 100 order/trang | Query nội dung và query total nếu cần, không lookup customer theo từng dòng |
| Entity JPA có batch | Số root và số quan hệ được giới hạn | Số đợt fetch phù hợp, không tăng như lookup riêng từng ID |
| MongoDB lookup tường minh | Root page và tối đa 100 ID/đợt | Query root cộng các đợt lookup, có tính đến cursor/command theo cách đo |
| JDBC read model | Tập field và số dòng giới hạn | Statement được quan sát tương ứng thiết kế query |
| R2DBC theo cửa sổ | Window size và concurrency xác định | Số lookup theo đợt, buffer và tải đồng thời có giới hạn |

Đây là các tiêu chí thiết kế, không phải kết quả đã đo.

Ngoài số query, nên ghi nhận:

- Số dòng/document và lượng dữ liệu trả về.
- Độ rộng kết quả join và bộ nhớ trong ứng dụng.
- Thời gian thực thi backend và thời gian toàn bộ request.
- Mức sử dụng connection pool, CPU và tần suất gọi backend.

Index giúp một truy vấn lookup chạy hiệu quả hơn nhưng không tự loại các lần gọi lookup lặp. Ngược lại, giảm số query bằng một join quá rộng có thể làm tổng công việc tăng lên.

Nếu caller không cần total, cân nhắc hợp đồng không đếm tổng. Nếu caller cần total, hãy đo và tối ưu query tính tổng thay vì bỏ nó ngầm.

## 10. Kiểm tra ngân sách query bằng integration test

### 10.1. Tạo fixture có khả năng bộc lộ N+1

Cần ít nhất hai kiểu fixture:

1. Nhiều order trỏ đến các customer khác nhau.
2. Nhiều order dùng chung một số customer.

Kiểu thứ nhất giúp phát hiện số lookup tăng theo N. Kiểu thứ hai giúp hiểu tác động của K và cache. Với collection, còn cần dữ liệu có số phần tử con khác nhau để phát hiện join làm nhân dòng.

Flush fixture, clear persistence context rồi mới bắt đầu đo. Nếu tạo entity và đọc tiếp trong cùng context mà không clear, cache có thể làm vấn đề bị che khuất.

Nên kiểm tra trạng thái lạnh và trạng thái cache ấm riêng. Cache ấm là một tình huống vận hành, không phải bằng chứng rằng trường hợp lạnh đã được giới hạn.

### 10.2. Ví dụ kiểm tra DTO JPA của bài

Với Hibernate 6.6, `Statistics` có thể cung cấp số prepared statement được tạo. Bộ đếm thuộc toàn bộ SessionFactory, nên ví dụ cần môi trường test cô lập, không có công việc khác chạy đồng thời trên cùng factory.

~~~java
package example.orders;

import jakarta.persistence.EntityManagerFactory;

import org.hibernate.SessionFactory;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.PageRequest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = {
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "spring.jpa.properties.hibernate.generate_statistics=true",
        "spring.jpa.properties.hibernate.cache.use_second_level_cache=false",
        "spring.jpa.properties.hibernate.cache.use_query_cache=false"
})
class OrderCardQueryBudgetTest {

    @Autowired
    private OrderRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @ParameterizedTest
    @ValueSource(ints = {10, 50})
    void dtoReadDoesNotLookupCustomerPerOrder(int count) {
        for (int index = 0; index < count; index++) {
            Customer customer = entityManager.persist(
                    new Customer("Customer " + index));

            entityManager.persist(
                    new PurchaseOrder("OPEN", customer));
        }

        entityManager.flush();
        entityManager.clear();

        var statistics = entityManagerFactory
                .unwrap(SessionFactory.class)
                .getStatistics();

        statistics.clear();

        var page = repository.findCardsByStatus(
                "OPEN",
                PageRequest.of(0, count));

        assertThat(page.getContent()).hasSize(count);
        assertThat(page.getTotalElements()).isEqualTo(count);

        assertThat(page.getContent()).allSatisfy(card -> {
            assertThat(card.id()).isNotNull();
            assertThat(card.customerName()).isNotBlank();
        });

        assertThat(statistics.getPrepareStatementCount())
                .isBetween(1L, 2L);
    }
}
~~~

Ví dụ giả định database test riêng, không có seed hoặc callback thêm query ngoài mô hình tối thiểu.

Budget 1–2 statement dành riêng cho query DTO đơn giản và countQuery đã khai báo, sau khi fixture được flush. Nó không phải budget chung cho mọi method trả Page.

Assertion yêu cầu có statement thật, tránh thành công vô nghĩa khi không quan sát được truy vấn. Các giá trị DTO cũng được kiểm tra để không đạt budget bằng cách trả thiếu dữ liệu.

API và phạm vi thống kê được mô tả trong [Statistics của Hibernate](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/stat/Statistics.html).

### 10.3. Hiểu giới hạn phép đo

Prepared statement count không phải số byte đọc, số dòng join hoặc tổng số vòng TCP. Nó có thể bao gồm các statement khác nếu phạm vi đo không được cô lập.

Không dùng bộ đếm toàn cục để gán chi phí cho từng request trong một phép đo có nhiều request chạy đồng thời. Khi đó cần tracing hoặc công cụ ghi nhận theo phạm vi phù hợp.

Với MongoDB, dùng quan sát command/driver hoặc công cụ backend tương ứng, phân biệt query quan hệ với getMore và command ngoài ca đọc. Với R2DBC, dùng công cụ của driver/backend và chờ pipeline hoàn tất trước khi kết luận.

Một unit test dùng mock repository không thể chứng minh số query của đường persistence thật.

## 11. Những cách sửa dễ làm vấn đề chuyển chỗ

| Cách sửa | Điều cần kiểm tra lại |
| --- | --- |
| Đổi mọi quan hệ sang EAGER | Có query phụ hoặc tải nhiều dữ liệu không cần thiết không |
| Thêm fetch graph | Query thực tế, độ rộng entity và số root được đọc |
| Join nhiều collection | Số dòng trung gian, trùng root và phân trang |
| Đổi sang nested projection | Getter có kéo dữ liệu quan hệ hoặc join rộng không |
| Thêm cache | Trường hợp cache lạnh, invalidation và độ mới dữ liệu |
| Tăng reactive concurrency | Số query tổng, pool và tải backend |
| Gom tất cả ID thành một batch | Giới hạn tham số, kích thước request và bộ nhớ |
| Chuyển lookup vào serializer | Query có bị đẩy ra ngoài phạm vi đo không |
| Thay Page bằng List | Caller có mất thông tin hoặc giới hạn kết quả không |
| Embed/denormalize dữ liệu | Ngữ nghĩa snapshot và cơ chế đồng bộ |
| Thêm index cho từng lookup | Chi phí từng query giảm nhưng số lần gọi có còn tăng theo N không |

Một callback auditing hoặc fragment cũng có thể đọc thêm dữ liệu theo từng đối tượng. Nếu log cho thấy query bất ngờ không khớp quan hệ đang xem, cần kiểm tra những đường đó thay vì chỉ sửa annotation fetch.

## 12. Quy trình giới hạn truy vấn lặp

1. Xác định chính xác dữ liệu caller cần và số root tối đa cho một lần đọc.
2. Đo từ repository đến hết phần sử dụng kết quả, nhận diện các lookup lặp cùng tham số khác nhau.
3. Tách chi phí đọc root, metadata trang, quan hệ và logic bổ sung.
4. Chọn DTO/query phẳng, fetch plan, batch lookup, aggregation hoặc read model theo khả năng của store.
5. Kiểm tra lại số query, số dòng/document, kích thước dữ liệu và hành vi phân trang.
6. Giữ integration test với nhiều customer khác nhau và kích thước dữ liệu đủ phân biệt cách đọc tuyến tính với cách đọc theo đợt.

Với JPA, biện pháp có thể nằm ở query, entity graph hoặc batch fetching. Với MongoDB, cần xem reference resolution, lookup theo tập ID, aggregation hoặc mô hình document. Với JDBC/R2DBC, cần dựa vào cách tải aggregate, query và pipeline của module đang dùng.

Abstraction repository và projection giúp biểu đạt đường đọc, nhưng giới hạn truy vấn lặp chỉ được xác nhận bằng hành vi thực tế của store trong ca sử dụng đã xác định.
