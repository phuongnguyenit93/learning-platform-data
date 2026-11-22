# Cấu hình @SequenceGenerator và phân bổ giá trị khóa trong Spring Data JPA

## 1. Khóa chính được sinh bằng sequence là gì?

Trong cơ sở dữ liệu quan hệ, khóa chính (primary key) dùng để định danh duy nhất một hàng. Ứng dụng Java thường ánh xạ khóa chính đó vào thuộc tính của entity, chẳng hạn `Long id`.

Một số hệ quản trị cơ sở dữ liệu hỗ trợ **sequence**: một đối tượng độc lập trong database có khả năng cấp ra các giá trị số theo thứ tự tăng. Sequence có thể được gọi để lấy giá trị kế tiếp mà không cần chèn hàng vào bảng trước. Nhiều bảng thậm chí có thể dùng chung một sequence nếu thiết kế yêu cầu.

JPA hỗ trợ sequence thông qua `GenerationType.SEQUENCE` và annotation `@SequenceGenerator`. Trong Spring Data JPA, cấu hình này nằm trên entity; repository vẫn sử dụng bình thường. Khi lưu entity mới, Spring Data JPA chuyển thao tác xuống JPA `EntityManager`, còn JPA provider (ví dụ Hibernate) lấy giá trị khóa theo cấu hình mapping.

Cần phân biệt:

- **Tên generator trong Java** là tên logic mà `@GeneratedValue` tham chiếu.
- **Tên sequence trong database** là tên đối tượng sequence thực tế mà provider gọi.
- **Giá trị khóa được cấp** là số mà sequence trả về hoặc số do provider phân bổ từ vùng giá trị đã lấy trước.

Ba khái niệm này có liên quan nhưng không nhất thiết có cùng tên hay cùng cách hoạt động.

## 2. Vai trò của @SequenceGenerator và @GeneratedValue

`@SequenceGenerator` khai báo cấu hình cho một sequence generator. `@GeneratedValue` nói rằng thuộc tính khóa chính sẽ được sinh tự động và chỉ rõ generator nào cần dùng.

Ví dụ tối giản:

~~~java
@Entity
@SequenceGenerator(
    name = "customer_seq_gen",
    sequenceName = "customer_seq",
    allocationSize = 1
)
public class Customer {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "customer_seq_gen"
    )
    private Long id;
}
~~~

Trong ví dụ:

- `name = "customer_seq_gen"` là tên generator logic trong metadata JPA.
- `sequenceName = "customer_seq"` là tên sequence vật lý trong database.
- `strategy = GenerationType.SEQUENCE` yêu cầu JPA sử dụng sequence.
- `generator = "customer_seq_gen"` liên kết `@GeneratedValue` với generator đã khai báo.
- `allocationSize = 1` yêu cầu cấp phát theo từng giá trị một.

Nếu bỏ `generator` khỏi `@GeneratedValue`, provider có thể chọn generator mặc định thay vì generator vừa khai báo. Vì vậy, khi muốn dùng một sequence cụ thể, hai annotation phải tham chiếu đúng tên nhau.

### Các thuộc tính quan trọng của @SequenceGenerator

| Thuộc tính | Ý nghĩa | Giá trị mặc định |
|---|---|---|
| `name` | Tên generator logic được `@GeneratedValue` tham chiếu; là thuộc tính bắt buộc | Không có |
| `sequenceName` | Tên sequence trong database | Để provider chọn tên mặc định |
| `allocationSize` | Số lượng giá trị mà provider dự kiến phân bổ trong một lần lấy sequence | `50` |
| `initialValue` | Giá trị bắt đầu khi sequence được tạo bởi cơ chế tạo schema | `1` |
| `schema` | Schema chứa sequence | Schema mặc định |
| `catalog` | Catalog chứa sequence | Catalog mặc định |

Tên `name` của generator phải duy nhất trong phạm vi persistence unit. Không nên khai báo nhiều generator khác nhau trùng tên vì provider có thể không biết cấu hình nào cần áp dụng.

Có thể đặt `@SequenceGenerator` trên entity class hoặc trên thuộc tính khóa. Đặt ở cấp class thường giúp người đọc thấy cấu hình ID ngay gần khai báo entity. Nếu generator được khai báo tại một vị trí, hãy dùng đúng tên logic đó trong `@GeneratedValue`.

## 3. Ví dụ entity và repository hoàn chỉnh

Giả sử ứng dụng quản lý đơn mua hàng. Entity `PurchaseOrder` có khóa chính `id` được sinh từ sequence `purchase_order_seq`.

~~~java
package com.example.shop.order.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_order")
@SequenceGenerator(
    name = "purchase_order_seq_gen",
    sequenceName = "purchase_order_seq",
    initialValue = 1,
    allocationSize = 50
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_seq_gen"
    )
    private Long id;

    private String description;

    protected PurchaseOrder() {
        // Constructor không tham số phục vụ JPA.
    }

    public PurchaseOrder(String description) {
        this.description = description;
    }

    public Long getId() {
        return id;
    }

    public String getDescription() {
        return description;
    }
}
~~~

Repository không cần tự viết logic sinh khóa:

~~~java
package com.example.shop.order.persistence;

import com.example.shop.order.domain.PurchaseOrder;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

`JpaRepository<PurchaseOrder, Long>` cho biết entity được quản lý là `PurchaseOrder` và kiểu khóa chính là `Long`. Khi gọi `save`, Spring Data JPA sử dụng mapping JPA trên entity để lưu dữ liệu. Không cần tự gọi sequence trong service và cũng không cần viết một repository implementation riêng chỉ để lấy ID.

Ví dụ sử dụng trong service:

~~~java
@Service
public class PurchaseOrderService {
    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long create(String description) {
        PurchaseOrder order = new PurchaseOrder(description);
        PurchaseOrder saved = repository.save(order);
        return saved.getId();
    }
}
~~~

Đây là các đoạn mã trong ứng dụng Spring Boot có dependency Spring Data JPA và cấu hình datasource phù hợp, không phải chương trình Java độc lập có thể biên dịch chỉ bằng `javac`. Ví dụ dùng namespace `jakarta.persistence` của Spring Boot 3 trở lên. Dự án Spring Boot 2 cũ thường dùng `javax.persistence`; không trộn hai namespace trong cùng một ứng dụng.

## 4. Cấu hình sequence trong database

Annotation mô tả mapping cho JPA, nhưng sequence thực tế vẫn là đối tượng trong database. Nếu dùng migration hoặc quản lý schema thủ công, cần tạo sequence phù hợp với cấu hình entity.

Với ví dụ `allocationSize = 50`, DDL minh họa cho PostgreSQL khi sử dụng Hibernate với pooled optimizer có thể là:

~~~sql
CREATE SEQUENCE purchase_order_seq
    START WITH 1
    INCREMENT BY 50;

CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    description VARCHAR(255)
);
~~~

Trong cấu hình Hibernate pooled thông dụng, `allocationSize` và bước tăng vật lý của sequence cần tương thích. Khi `allocationSize = 50`, Hibernate thường mong sequence tăng theo bước 50 để mỗi lần lấy giá trị có thể đại diện cho một vùng ID được phân bổ. Nếu database sequence chỉ tăng 1 trong khi mapping và optimizer mong bước 50, Hibernate có thể báo lỗi không khớp increment khi khởi động hoặc khi kiểm tra schema.

Nếu chọn `allocationSize = 1`, DDL tương ứng thường dùng bước tăng 1:

~~~java
@SequenceGenerator(
    name = "purchase_order_seq_gen",
    sequenceName = "purchase_order_seq",
    initialValue = 1,
    allocationSize = 1
)
~~~

~~~sql
CREATE SEQUENCE purchase_order_seq
    START WITH 1
    INCREMENT BY 1;
~~~

**Lưu ý:** cách Hibernate sử dụng sequence còn phụ thuộc optimizer và cấu hình provider. JPA quy định ý nghĩa của `allocationSize`, còn cách provider lấy trước và sử dụng các vùng ID là chi tiết triển khai. Vì vậy, hãy kiểm tra tài liệu đúng phiên bản Hibernate/provider và cấu hình schema tương ứng; không áp dụng DDL của một optimizer cho mọi provider.

Trong môi trường production, nên quản lý sequence bằng migration như Flyway hoặc Liquibase. Không nên mặc định rằng việc thay đổi annotation sẽ tự sửa một sequence đã tồn tại trong database.

## 5. allocationSize hoạt động như thế nào?

`allocationSize` là tham số quan trọng ảnh hưởng đến số lần ứng dụng phải gọi database để lấy giá trị sequence.

### allocationSize = 1

Với `allocationSize = 1`, provider lấy một giá trị sequence cho mỗi lần cần ID mới. Cách này dễ hiểu và thường phù hợp khi cần cấu hình đơn giản hoặc khi sequence được dùng với bước tăng 1.

Ưu điểm:

- Mapping và DDL dễ đối chiếu.
- Mỗi lần cấp ID lấy giá trị trực tiếp từ sequence.
- Ít phải suy nghĩ về vùng ID được cấp trước.

Hạn chế:

- Tần suất gọi database để lấy sequence cao hơn khi insert nhiều bản ghi.
- Có thể tăng round trip và ảnh hưởng throughput nếu thao tác ghi diễn ra thường xuyên.

### allocationSize lớn hơn 1

Với `allocationSize = 50`, provider có thể lấy trước một nhóm giá trị từ sequence rồi cấp các ID trong nhóm đó cho entity mới mà không cần gọi database cho từng entity.

Có thể hình dung luồng ở mức khái niệm:

~~~text
Ứng dụng cần ID
      |
      v
Provider yêu cầu database cấp sequence
      |
      v
Provider nhận thông tin vùng ID
      |
      v
Các entity tiếp theo dùng ID trong vùng đã được phân bổ
      |
      v
Khi vùng dùng hết, provider lấy vùng tiếp theo
~~~

Lợi ích chính là giảm số lần gọi sequence tới database. Điều này có thể hữu ích khi ứng dụng ghi nhiều entity và chi phí round trip đáng kể.

Đổi lại:

- Có thể có khoảng trống trong dãy ID khi ứng dụng khởi động lại mà chưa dùng hết vùng đã lấy.
- Transaction rollback không có nghĩa là giá trị sequence đã lấy sẽ được trả lại.
- Nhiều instance ứng dụng có thể giữ các vùng ID khác nhau, nên ID nhìn thấy không nhất thiết tăng liên tục theo thứ tự insert.
- Cần cấu hình nhất quán giữa các instance và giữa mapping với sequence vật lý.

Ví dụ, ứng dụng lấy trước một vùng 50 ID nhưng chỉ sử dụng một phần rồi bị dừng. Những giá trị còn lại có thể không được sử dụng nữa. Đây là hành vi bình thường của chiến lược cấp phát trước, không phải lỗi mất dữ liệu.

### Chọn allocationSize bao nhiêu?

Không có một con số tối ưu cho mọi hệ thống. Có thể bắt đầu với:

- `1` nếu muốn cấu hình trực tiếp, dễ kiểm soát và lưu lượng ghi nhỏ.
- Một giá trị như `50` nếu provider dùng chiến lược pooling tương ứng và ứng dụng có nhiều thao tác insert.
- Giá trị lớn hơn chỉ khi đo đạc cho thấy việc giảm round trip mang lại lợi ích và nhóm vận hành hiểu rõ hệ quả của cấp phát trước.

Đừng chọn một giá trị lớn chỉ vì nghĩ ID sẽ được sinh nhanh hơn. Hãy đo hiệu năng với tải ghi thực tế, kiểm tra optimizer của provider và đồng bộ DDL của sequence.

## 6. initialValue có tác dụng gì?

`initialValue` khai báo giá trị bắt đầu của sequence khi schema được tạo bởi công cụ/provider hỗ trợ sinh DDL. Giá trị mặc định là `1`.

Ví dụ:

~~~java
@SequenceGenerator(
    name = "invoice_seq_gen",
    sequenceName = "invoice_seq",
    initialValue = 1000,
    allocationSize = 1
)
~~~

Khi provider tạo sequence mới theo metadata này, sequence được cấu hình bắt đầu từ giá trị 1000 theo khả năng của provider và database.

Điểm quan trọng là `initialValue` không nên được xem như lệnh tự động đặt lại một sequence đang tồn tại. Nếu database đã có sequence, việc cập nhật annotation không bảo đảm sequence hiện tại sẽ được reset. Với schema được quản lý bằng migration, hãy sửa DDL hoặc migration một cách tường minh.

Nếu thêm sequence vào bảng đã có dữ liệu, cần bảo đảm giá trị sequence kế tiếp không đụng vào khóa chính đang tồn tại. Việc đồng bộ sequence với `MAX(id)` phải được thực hiện bằng câu lệnh migration phù hợp với database, optimizer và `allocationSize` đang sử dụng.

Ví dụ PostgreSQL đơn giản cho trường hợp `allocationSize = 1`:

~~~sql
SELECT setval(
    'purchase_order_seq',
    COALESCE((SELECT MAX(id) FROM purchase_order), 0) + 1,
    false
);
~~~

Với tham số `false`, lần gọi `nextval` tiếp theo trả về đúng giá trị đã đặt. Câu lệnh này là ví dụ riêng cho PostgreSQL và sequence tăng 1; không dùng nguyên xi cho mọi database hoặc cho cấu hình pooled với bước tăng lớn hơn.

## 7. Quan hệ giữa @SequenceGenerator, database sequence và Hibernate

Có ba tầng cần hiểu:

1. **JPA mapping:** `@GeneratedValue` và `@SequenceGenerator` mô tả chiến lược và thông tin generator cho entity.
2. **JPA provider:** Hibernate hoặc provider khác đọc mapping, quyết định thời điểm gọi sequence và cách phân bổ ID theo optimizer.
3. **Database:** sequence vật lý lưu trạng thái và cấp giá trị theo cú pháp, quy tắc của hệ quản trị cơ sở dữ liệu.

Vì vậy, lỗi phát sinh ở một tầng không phải lúc nào cũng sửa được bằng cách đổi annotation ở tầng khác.

Với Hibernate, các optimizer phổ biến có thể sử dụng sequence theo cách pooled hoặc pooled-lo. Cách tính vùng ID, cách diễn giải giá trị database trả về và yêu cầu về increment có thể khác nhau. Hãy tránh giả định rằng `allocationSize` luôn có nghĩa là database trả về một ID đơn giản rồi ứng dụng cộng 1 cho mỗi entity; chi tiết phụ thuộc optimizer.

Nếu nhiều service hoặc nhiều instance cùng ghi vào một bảng, mọi bên sử dụng sequence phải thống nhất về sequence name, increment và allocation strategy. Nếu một ứng dụng cấu hình `allocationSize = 50`, ứng dụng khác lại cấu hình `allocationSize = 1` trên cùng sequence, có thể xuất hiện xung đột hoặc lỗi xác thực tùy provider và optimizer.

## 8. So sánh SEQUENCE với IDENTITY và AUTO

| Chiến lược | Cách cấp ID | Đặc điểm |
|---|---|---|
| `SEQUENCE` | Lấy giá trị từ sequence độc lập trong database | Có thể lấy trước ID và phân bổ theo nhóm; phụ thuộc database hỗ trợ sequence |
| `IDENTITY` | Database sinh ID khi insert hàng | Thường cần thực hiện insert để biết ID; có thể hạn chế một số cách batching insert |
| `AUTO` | Provider chọn chiến lược phù hợp với kiểu ID và database | Ít phải chỉ định chi tiết, nhưng chiến lược thực tế phụ thuộc provider/database |

`SEQUENCE` thường hữu ích khi database hỗ trợ sequence và ứng dụng muốn tận dụng cơ chế cấp phát trước. `IDENTITY` phù hợp với cột tự tăng của database. `AUTO` tiện cho trường hợp muốn provider quyết định, nhưng nếu yêu cầu vận hành cần chiến lược rõ ràng thì nên khai báo tường minh.

Không nên chọn `SEQUENCE` chỉ vì nó có vẻ hiện đại hơn. Hãy dựa trên khả năng database, yêu cầu hiệu năng, cách migration quản lý schema và đặc điểm provider đang dùng.

## 9. Các lỗi thường gặp

### 9.1. Không tìm thấy sequence

Database có thể báo lỗi kiểu sequence không tồn tại, ví dụ PostgreSQL báo relation của sequence không tồn tại.

Nguyên nhân thường gặp:

- `sequenceName` không khớp với tên sequence thật.
- Sequence nằm trong schema khác nhưng mapping không khai báo `schema`.
- Migration tạo bảng nhưng quên tạo sequence.
- Tài khoản kết nối không có quyền sử dụng sequence.

Cách xử lý: kiểm tra tên, schema, migration và quyền database. Không đổi `generator` name để sửa lỗi tên sequence vật lý; hai tên này thuộc hai tầng khác nhau.

### 9.2. Không khớp increment size

Hibernate có thể báo sequence increment trong database không khớp với increment size trong mapping. Ví dụ mapping đặt `allocationSize = 50` nhưng sequence vật lý lại tăng 1, trong khi optimizer hiện tại yêu cầu bước tăng 50.

Cách xử lý:

1. Xác định `allocationSize` trên entity.
2. Kiểm tra DDL hoặc metadata của sequence trong database.
3. Xác định optimizer và cấu hình Hibernate đang dùng.
4. Chọn một cấu hình tương thích rồi sửa migration/schema.
5. Khởi động lại ứng dụng và kiểm tra schema validation.

Không nên tắt schema validation chỉ để che lỗi mismatch nếu chưa hiểu nguy cơ cấp phát ID.

### 9.3. Trùng khóa chính sau khi thêm sequence vào bảng cũ

Nếu sequence bắt đầu từ giá trị nhỏ hơn hoặc bằng ID đã tồn tại trong bảng, lần insert mới có thể vi phạm unique constraint hoặc primary key.

Cách xử lý là đồng bộ trạng thái sequence với dữ liệu hiện có bằng migration phù hợp. Cần tính đến `allocationSize`, optimizer, sequence increment và việc có nhiều instance đang chạy hay không. Việc chỉnh sequence phải được lên lịch an toàn để không xảy ra cấp phát đồng thời trong lúc thay đổi.

### 9.4. generator name không khớp

Ví dụ khai báo:

~~~java
@SequenceGenerator(
    name = "order_seq_gen",
    sequenceName = "order_seq"
)
~~~

nhưng lại tham chiếu:

~~~java
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "orders_seq_gen"
)
~~~

Hai chuỗi `order_seq_gen` và `orders_seq_gen` khác nhau. Cần bảo đảm `generator` trong `@GeneratedValue` trùng chính xác với `name` trong `@SequenceGenerator`.

### 9.5. Database không hỗ trợ sequence

Không phải mọi hệ quản trị cơ sở dữ liệu đều hỗ trợ sequence theo cùng cách. Nếu database không hỗ trợ hoặc dialect/provider không triển khai chiến lược này, hãy cân nhắc `IDENTITY`, `AUTO` hoặc chiến lược phù hợp với hệ quản trị đang dùng.

## 10. Quy trình cấu hình và kiểm tra thực tế

Khi thêm sequence cho một entity, có thể thực hiện theo thứ tự:

1. Chọn tên sequence rõ ràng, ví dụ `purchase_order_seq`.
2. Khai báo `@SequenceGenerator` với tên logic duy nhất trong persistence unit.
3. Khai báo `@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "...")` và kiểm tra tên tham chiếu chính xác.
4. Chọn `allocationSize` dựa trên provider, optimizer và tải ghi.
5. Tạo hoặc cập nhật sequence trong migration với increment tương thích.
6. Nếu bảng đã có dữ liệu, đồng bộ giá trị sequence để không sinh ID trùng.
7. Khởi động ứng dụng với schema validation phù hợp để phát hiện sai lệch mapping.
8. Lưu thử một entity qua repository và kiểm tra ID được gán.
9. Thử nhiều lần lưu, rollback và khởi động lại để hiểu khoảng trống ID là hành vi cấp phát bình thường.
10. Với nhiều instance, kiểm tra chúng dùng chung cấu hình generator và sequence một cách nhất quán.

Không cần viết code gọi `nextval` trong service cho luồng CRUD thông thường. Hãy để JPA provider quản lý generator theo mapping, trừ khi ứng dụng có yêu cầu đặc biệt cần truy cập sequence trực tiếp.

## 11. Ghi nhớ

- `@SequenceGenerator.name` là tên logic của generator trong JPA.
- `sequenceName` là tên sequence thực tế trong database.
- `@GeneratedValue(generator = "...")` phải tham chiếu đúng `name`.
- `allocationSize` mặc định là `50`; nó ảnh hưởng đến cách provider phân bổ ID và số lần lấy sequence.
- `initialValue` mặc định là `1`, chủ yếu có ý nghĩa khi tạo sequence mới từ metadata.
- Sequence vật lý và cấu hình optimizer của provider phải tương thích.
- ID không nhất thiết liên tục; khoảng trống do rollback, cấp phát trước hoặc restart là bình thường.
- Với Spring Data JPA, khai báo mapping trên entity là đủ để repository sử dụng chiến lược sinh khóa; không cần tự viết logic cấp ID trong repository.

Hiểu rõ quan hệ giữa mapping JPA, optimizer của Hibernate và sequence trong database sẽ giúp cấu hình `@SequenceGenerator` đúng, tránh lỗi increment mismatch và bảo đảm các instance ứng dụng cấp phát khóa an toàn.