# Hibernate ORM là gì và giải quyết độ lệch giữa đối tượng Java với dữ liệu quan hệ như thế nào?

Trong ứng dụng Java, lập trình viên làm việc với **đối tượng**: một đơn hàng có khách hàng, danh sách sản phẩm, trạng thái và các phương thức nghiệp vụ. Trong cơ sở dữ liệu quan hệ, cùng thông tin ấy được biểu diễn bằng **bảng, hàng, cột, khóa chính và khóa ngoại**. Hai cách tổ chức dữ liệu không trùng khớp tự nhiên.

**Hibernate ORM** là framework giúp ánh xạ hai mô hình đó, đồng thời quản lý việc đọc, ghi và đồng bộ trạng thái đối tượng Java với dữ liệu trong cơ sở dữ liệu quan hệ. Để hiểu vai trò của Hibernate, cần nhìn rõ nó giải quyết phần nào của sự khác biệt này và phần nào vẫn là trách nhiệm của người thiết kế ứng dụng.

## 1. Vì sao đối tượng Java và dữ liệu quan hệ có “độ lệch”?

Giả sử ứng dụng thương mại có các đối tượng sau:

§§§java
public class Customer {
    private Long id;
    private String name;
}

public class PurchaseOrder {
    private Long id;
    private Customer customer;
    private BigDecimal total;
}
§§§

Trong Java, §PurchaseOrder§ tham chiếu trực tiếp đến một §Customer§:

§§§java
Customer customer = order.getCustomer();
String name = customer.getName();
§§§

Trong cơ sở dữ liệu quan hệ, mối quan hệ thường được lưu bằng **khóa ngoại**, chẳng hạn:

§§§sql
-- customers
-- id | name
--  7 | An

-- purchase_orders
-- id | customer_id | total
-- 42 |           7 | 249.90
§§§

Không có một “con trỏ đối tượng Customer” trong hàng của §purchase_orders§; chỉ có giá trị §customer_id = 7§. Muốn lấy tên khách hàng, chương trình cần truy vấn và kết hợp dữ liệu từ hai bảng.

Nếu chỉ dùng JDBC, lập trình viên tự viết SQL, đặt tham số, đọc §ResultSet§, tạo đối tượng, gán thuộc tính và quản lý kết nối, giao dịch. Ví dụ rút gọn:

§§§java
String sql = """
    SELECT o.id, o.total, c.id AS customer_id, c.name
    FROM purchase_orders o
    JOIN customers c ON c.id = o.customer_id
    WHERE o.id = ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, orderId);
    try (ResultSet rs = statement.executeQuery()) {
        if (rs.next()) {
            Long id = rs.getLong("id");
            BigDecimal total = rs.getBigDecimal("total");
            // Còn phải dựng Customer, PurchaseOrder và nối chúng với nhau.
        }
    }
}
§§§

JDBC là nền tảng truy cập dữ liệu hữu ích, nhưng với nhiều entity và quan hệ, mã chuyển đổi giữa hàng dữ liệu và object graph dễ lặp lại và khó bảo trì.

### Những dạng độ lệch thường gặp

| Khía cạnh | Mô hình hướng đối tượng | Mô hình quan hệ | Vấn đề cần xử lý |
|---|---|---|---|
| Cấu trúc | Lớp, đối tượng, thuộc tính | Bảng, hàng, cột | Quy tắc lớp nào gắn với bảng nào, thuộc tính nào gắn với cột nào |
| Định danh | Tham chiếu và định danh đối tượng trong bộ nhớ | Khóa chính ổn định | Ghép một hàng với đúng entity trong một phiên làm việc |
| Quan hệ | Tham chiếu, tập hợp đối tượng | Khóa ngoại, bảng liên kết, §JOIN§ | Biểu diễn và nạp quan hệ mà không truy vấn thừa |
| Kế thừa | §extends§, đa hình | Không có kế thừa lớp trực tiếp | Chọn cách lưu cây phân cấp lớp vào bảng |
| Kiểu dữ liệu | §enum§, §LocalDate§, §BigDecimal§, value object | §VARCHAR§, §DATE§, §DECIMAL§, ... | Chuyển đổi kiểu và xác định quy tắc null/độ chính xác |
| Trạng thái | Đối tượng có thể thay đổi trong bộ nhớ | Dữ liệu thay đổi bằng §INSERT§, §UPDATE§, §DELETE§ | Phát hiện thay đổi, sắp xếp lệnh SQL, đồng bộ theo giao dịch |
| Truy cập | Đi theo tham chiếu §order.getCustomer()§ | Truy vấn theo tập hợp với §SELECT§ và §JOIN§ | Quyết định lấy dữ liệu lúc nào, với bao nhiêu câu SQL |

Sự khác biệt này thường được gọi là **object–relational impedance mismatch** (độ lệch giữa mô hình đối tượng và mô hình quan hệ). Hibernate giảm công sức “bắc cầu”, nhưng không làm hai mô hình trở thành một.

## 2. Hibernate ORM là gì?

**ORM** là viết tắt của *Object–Relational Mapping*: ánh xạ đối tượng sang dữ liệu quan hệ và ngược lại. **Hibernate ORM** là một triển khai ORM phổ biến trong hệ sinh thái Java, có các trách nhiệm chính:

1. Đọc **metadata ánh xạ** từ annotation hoặc cấu hình để biết entity, bảng, cột, khóa và quan hệ tương ứng.
2. Sinh và thực thi SQL phục vụ các thao tác thông thường như tạo, tìm, cập nhật, xóa entity và truy vấn.
3. Chuyển hàng kết quả thành đối tượng Java, quản lý định danh và vòng đời của các đối tượng đang được quản lý.
4. Phát hiện thay đổi trên entity (*dirty checking*) và đồng bộ về database vào thời điểm thích hợp.
5. Hỗ trợ nạp quan hệ theo nhu cầu (*lazy loading*), khóa phiên bản, batching và các cơ chế tối ưu truy cập dữ liệu.

Hibernate không phải cơ sở dữ liệu và không thay thế SQL. Nó vẫn truy cập hệ quản trị cơ sở dữ liệu qua JDBC cùng các driver tương ứng. SQL, chỉ mục, ràng buộc, transaction và thiết kế lược đồ vẫn quyết định tính đúng đắn cũng như hiệu năng.

### Hibernate và Jakarta Persistence (JPA) liên hệ ra sao?

**Jakarta Persistence** (trước đây thường được gọi là JPA) là **đặc tả API và hành vi chuẩn** cho persistence trong Java. Nó định nghĩa các annotation như §@Entity§, §@Id§, §@ManyToOne§, API §EntityManager§ và ngôn ngữ truy vấn JPQL.

Hibernate ORM là **một provider triển khai** đặc tả đó. Hibernate cũng có API riêng như §Session§ và các khả năng mở rộng ngoài chuẩn Jakarta Persistence. Trong ứng dụng thông thường, viết code theo API chuẩn giúp giảm phụ thuộc trực tiếp vào một provider; dùng tính năng riêng của Hibernate khi có lý do cụ thể.

Luồng đơn giản:

§§§text
Mã Java / Service
       |
       v
EntityManager (Jakarta Persistence) hoặc Session (Hibernate)
       |
       v
Hibernate ORM
  | metadata ánh xạ
  | persistence context + dirty checking
  | tạo SQL, binding tham số
       |
       v
JDBC driver -> Cơ sở dữ liệu quan hệ
§§§

## 3. Ánh xạ một entity vào bảng

Xét hai bảng minh họa, cú pháp identity cụ thể có thể khác nhau giữa các hệ quản trị:

§§§sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    total DECIMAL(12, 2) NOT NULL,
    version BIGINT NOT NULL
);
§§§

Một entity Java tương ứng với §customers§:

§§§java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() {
        // Constructor không tham số dành cho persistence provider.
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
§§§

Và entity tương ứng với §purchase_orders§:

§§§java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal total;

    @Version
    private long version;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer, BigDecimal total) {
        this.customer = customer;
        this.total = total;
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void changeTotal(BigDecimal newTotal) {
        this.total = newTotal;
    }
}
§§§

Các annotation có ý nghĩa:

- §@Entity§: đánh dấu lớp là entity được persistence provider quản lý.
- §@Table(name = "...")§: chỉ định bảng; §@Column§: mô tả ánh xạ cột và một phần ràng buộc.
- §@Id§: định danh entity bằng khóa chính; §@GeneratedValue§: khai báo chiến lược sinh khóa.
- §@ManyToOne§: thuộc tính §customer§ là quan hệ nhiều đơn hàng thuộc một khách hàng.
- §@JoinColumn(name = "customer_id")§: nối quan hệ thông qua cột khóa ngoại.
- §@Version§: đánh dấu thuộc tính phiên bản dùng cho **optimistic locking**, giúp phát hiện một số tình huống cập nhật cạnh tranh.

Trong ví dụ này, một §PurchaseOrder§ **không chứa toàn bộ các cột của Customer**. Hibernate biết §customer_id§ là khóa ngoại và có thể biến nó thành tham chiếu §Customer§ khi truy cập.

> Annotation mô tả ánh xạ; nó không bảo đảm database hiện có đúng schema. Ứng dụng thực tế cần quản lý thay đổi schema một cách có kiểm soát, thường bằng công cụ migration như Flyway hoặc Liquibase.

## 4. Hibernate giải quyết các độ lệch cụ thể như thế nào?

### 4.1. Lớp/thuộc tính ↔ bảng/cột

Hibernate đọc metadata ánh xạ, chuyển giá trị của thuộc tính Java thành giá trị cột tương ứng và khởi tạo entity khi đọc kết quả SQL. §@Column§ kiểm soát tên cột, độ dài, nullable, precision/scale; cách ánh xạ có thể mở rộng bằng §@Embedded§, §@Embeddable§ hoặc §AttributeConverter§.

Ví dụ, §BigDecimal§ thích hợp để lưu số tiền dưới dạng §DECIMAL(12,2)§. Với kiểu nghiệp vụ tự định nghĩa, một §AttributeConverter§ có thể chuyển đổi giữa value object và kiểu cột cơ bản.

Tuy vậy, vẫn phải hiểu semantics của database: §NULL§ khác chuỗi rỗng; §DECIMAL§ có precision/scale; độ dài cột, múi giờ, collation và cách so sánh dữ liệu phụ thuộc hệ quản trị và schema.

### 4.2. Tham chiếu Java ↔ khóa ngoại và bảng liên kết

Hibernate ánh xạ các quan hệ phổ biến:

- §@ManyToOne§: nhiều entity con tham chiếu một entity cha, thường bằng khóa ngoại.
- §@OneToOne§: quan hệ một–một dựa trên khóa ngoại/khóa duy nhất hoặc khóa dùng chung.
- §@OneToMany§: một entity có tập hợp các entity khác; thường được biểu diễn bằng khóa ngoại ở phía “many”.
- §@ManyToMany§: hai tập hợp liên hệ qua **bảng trung gian**.

Ví dụ §order.getCustomer()§ được biểu diễn trên database bằng §purchase_orders.customer_id§. Hibernate có thể truy vấn bảng §customers§ để dựng entity tương ứng. Ở quan hệ hai chiều, cả hai phía Java phải được cập nhật nhất quán trong code nghiệp vụ; không nên kỳ vọng thay đổi một collection tự làm mọi tham chiếu ngược trong bộ nhớ đúng ngay lập tức.

**Lưu ý về ownership:** phía giữ khóa ngoại thường là phía quản lý quan hệ trong JPA. Ví dụ quan hệ §PurchaseOrder.customer§ nắm cột §customer_id§; nếu thêm §Customer.orders§ với §@OneToMany(mappedBy = "customer")§, phía tập hợp là phía tham chiếu ngược.

### 4.3. Định danh đối tượng ↔ khóa chính

Một hàng được xác định bằng khóa chính (§id = 42§), trong khi Java có cả tham chiếu đối tượng (toán tử §==§), trạng thái và phương thức §equals§.

Trong **cùng một persistence context**, Hibernate duy trì identity map: khi tải cùng kiểu entity và cùng khóa chính, các lần truy xuất thường trả về **cùng một instance Java đang được quản lý**. Nhờ vậy, các phần của object graph không tự ý tạo nhiều bản managed khác nhau của cùng một hàng.

Phạm vi bảo đảm này **không kéo dài qua mọi phiên hoặc mọi request**. Hai entity lấy từ hai §EntityManager§ khác nhau có thể biểu diễn cùng một hàng nhưng là hai instance. Vì vậy, cách triển khai §equals§/§hashCode§ của entity, nhất là khi ID được sinh sau khi §persist§, cần được thiết kế cẩn thận. Không nên mặc định đồng nhất §==§ với “cùng dữ liệu trong database”.

### 4.4. Thay đổi đối tượng ↔ UPDATE, INSERT, DELETE

Hibernate quản lý trạng thái và thực hiện **dirty checking** với entity đang được quản lý.

Ví dụ:

§§§java
EntityManager em = entityManagerFactory.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
    order.changeTotal(new BigDecimal("299.90"));

    tx.commit(); // Hibernate flush các thay đổi trước khi commit.
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
§§§

Không có lệnh §UPDATE§ viết tay trong ví dụ. Nếu §order§ đang ở trạng thái **managed** và thay đổi hợp lệ, Hibernate so sánh trạng thái và đồng bộ vào database trong quá trình flush. Với §@Version§, cập nhật thường có điều kiện trên phiên bản hiện tại và tăng phiên bản khi thành công, qua đó phát hiện xung đột cập nhật.

Hai khái niệm dễ nhầm:

- **§flush§**: đồng bộ các thao tác đang chờ trong persistence context thành SQL gửi xuống database. Flush **không đồng nghĩa commit**.
- **§commit§**: hoàn tất transaction; thay đổi được xác nhận theo cơ chế giao dịch của database. Nếu transaction rollback, các lệnh SQL đã flush trong transaction cũng bị rollback theo quy tắc của database.

Hibernate không tự đảm bảo giao dịch xuyên suốt mọi thao tác. Ứng dụng phải xác lập ranh giới transaction đúng cách. Ví dụ dùng §EntityTransaction§ ở trên giả định cấu hình resource-local; với Spring hoặc môi trường container, transaction thường được quản lý bởi §@Transactional§/JTA.

### 4.5. Kế thừa và value object ↔ schema quan hệ

Hệ quan hệ không có lớp §extends§ giống Java. Hibernate/JPA hỗ trợ các chiến lược như:

| Chiến lược | Cách lưu | Đánh đổi chính |
|---|---|---|
| §SINGLE_TABLE§ | Cả phân cấp entity vào một bảng, thường có discriminator | Ít join nhưng nhiều cột nullable và ràng buộc khó diễn đạt |
| §JOINED§ | Bảng gốc và bảng từng lớp con, liên kết bằng khóa | Schema chuẩn hóa hơn nhưng đọc lớp con thường cần join |
| §TABLE_PER_CLASS§ | Mỗi lớp entity cụ thể có bảng riêng | Truy vấn đa hình có thể phức tạp và tốn kém |

Với dữ liệu không có identity độc lập (ví dụ §Address§ gồm đường, thành phố), §@Embeddable§/§@Embedded§ thường phù hợp hơn việc tạo entity và bảng riêng. **Không phải lớp Java nào cũng cần một bảng**; quyết định ánh xạ phụ thuộc vào semantics nghiệp vụ và cách truy vấn.

### 4.6. Đi theo object graph ↔ chi phí truy vấn SQL

Trong Java, §order.getCustomer().getName()§ trông như một lần truy cập thuộc tính. Nhưng nếu §customer§ được cấu hình §LAZY§ và chưa được tải, việc truy cập có thể phát sinh một câu §SELECT§ bổ sung.

§LAZY§ cho phép trì hoãn nạp dữ liệu đến khi cần, thường giúp tránh tải cả đồ thị đối tượng không liên quan. Tuy nhiên, nó có hai hệ quả cần hiểu:

1. Truy cập quan hệ chưa nạp sau khi persistence context đã đóng có thể gây lỗi như §LazyInitializationException§.
2. Lặp qua danh sách §N§ đơn hàng rồi truy cập quan hệ ở từng phần tử có thể tạo **N+1 queries**: một truy vấn danh sách và nhiều truy vấn bổ sung.

Ví dụ khi màn hình *cần* thông tin khách hàng cho các đơn hàng, có thể chỉ định tải quan hệ ngay trong truy vấn:

§§§java
List<PurchaseOrder> orders = em.createQuery("""
    SELECT o
    FROM PurchaseOrder o
    JOIN FETCH o.customer
    WHERE o.total >= :minimum
    """, PurchaseOrder.class)
    .setParameter("minimum", new BigDecimal("100.00"))
    .getResultList();
§§§

§JOIN FETCH§ là cú pháp JPQL dùng để nạp quan hệ đã chỉ định cùng truy vấn. Nó là một công cụ, không phải quy tắc “càng fetch nhiều càng tốt”. Với collection, join fetch có thể nhân số hàng kết quả và làm việc phân trang khó khăn; đôi khi projection DTO, entity graph hoặc batch fetching là lựa chọn hợp lý hơn.

## 5. Entity được quản lý có những trạng thái nào?

Hiểu vòng đời entity giúp tránh nhầm “đã sửa object” với “đã ghi dữ liệu”:

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| **Transient / new** | Đối tượng Java mới, chưa được một persistence context quản lý | §new Customer("An")§ |
| **Managed / persistent** | Entity gắn với persistence context; thay đổi được theo dõi | §em.find(...)§ hoặc §em.persist(...)§ |
| **Detached** | Entity từng được quản lý nhưng hiện tách khỏi context | Sau §em.close()§ hoặc §em.detach(entity)§ |
| **Removed** | Entity được đánh dấu xóa trong context; thao tác xóa sẽ đồng bộ | §em.remove(entity)§ |

Ví dụ tạo hai entity trong một transaction:

§§§java
EntityManager em = entityManagerFactory.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Customer customer = new Customer("An");
    em.persist(customer);

    PurchaseOrder order = new PurchaseOrder(
        customer,
        new BigDecimal("249.90")
    );
    em.persist(order);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
§§§

Ở đây §em.persist(customer)§ đưa khách hàng mới vào trạng thái managed; §em.persist(order)§ đưa đơn hàng mới vào trạng thái managed. Hibernate dùng mapping để thực hiện §INSERT§ với khóa ngoại thích hợp. Với chiến lược IDENTITY, việc lấy khóa được sinh có thể khiến Hibernate cần thực hiện insert sớm hơn thời điểm flush thông thường.

**Sửa detached entity** không tự phát sinh §UPDATE§. Có thể dùng §merge§ khi cần hợp nhất dữ liệu vào một entity managed, nhưng §merge§ trả về **instance managed**; đối tượng truyền vào vẫn là detached. Trong nhiều luồng nghiệp vụ, cách rõ ràng hơn là tải entity trong transaction hiện tại rồi áp dụng thay đổi có kiểm soát.

## 6. Persistence context, Session và transaction: ba khái niệm khác nhau

- **Persistence context**: phạm vi mà Hibernate theo dõi các entity managed, giữ identity map và thay đổi chưa đồng bộ. Nó cũng đóng vai trò cache cấp một.
- **§EntityManager§ / §Session§**: API để tương tác với persistence context và thực hiện các thao tác persistence. §EntityManager§ là API chuẩn; §Session§ là API gốc của Hibernate.
- **Transaction**: đơn vị công việc có tính nguyên tử theo cơ chế giao dịch của database, ví dụ “tạo đơn hàng và các dòng hàng cùng thành công hoặc cùng rollback”.

Chúng liên quan chặt chẽ nhưng không đồng nghĩa. Một persistence context có thể chứa thay đổi đang chờ; transaction quyết định tính nguyên tử và thời điểm commit. Ứng dụng thường mở một transaction cho một thao tác nghiệp vụ và đóng tài nguyên đúng hạn. §EntityManager§/§Session§ thông thường **không được chia sẻ tùy tiện giữa các luồng**.

Hibernate có cache cấp một gắn với persistence context theo mặc định; **cache cấp hai** là cơ chế riêng, có cấu hình và không mặc nhiên làm mọi truy vấn tránh truy cập database.

## 7. Hibernate có thay thế hoàn toàn SQL và thiết kế database không?

**Không.** Hibernate chuyển phần lớn công việc ánh xạ và SQL thông dụng vào framework, nhưng hiệu quả sử dụng vẫn phụ thuộc vào:

- **Schema hợp lý:** khóa chính, khóa ngoại, unique constraint, index, nullable và ràng buộc miền dữ liệu.
- **Truy vấn phù hợp:** lọc và phân trang ở database; dùng projection/DTO khi chỉ cần một số cột; tránh tải toàn bộ entity graph.
- **Số lần đi database:** kiểm tra N+1, batching, chiến lược fetch và SQL thực tế.
- **Ranh giới transaction:** giữ transaction đủ ngắn, xử lý rollback đúng cách, cân nhắc isolation/locking theo yêu cầu đồng thời.
- **Quản lý thay đổi schema:** theo dõi migration và tương thích giữa phiên bản ứng dụng với cơ sở dữ liệu.

Một số trường hợp nên dùng trực tiếp SQL hoặc công cụ khác: báo cáo tổng hợp phức tạp, truy vấn tối ưu riêng cho hệ quản trị, cập nhật hàng loạt hoặc xử lý dữ liệu theo tập hợp. Hibernate hỗ trợ native SQL khi cần. ORM và SQL không loại trừ nhau.

### Một số hiểu nhầm hay gặp

| Hiểu nhầm | Thực tế |
|---|---|
| “Mỗi object sẽ thành một bảng.” | Entity, embedded value và quan hệ có cách ánh xạ khác nhau; thiết kế không nhất thiết một lớp một bảng. |
| “Gọi getter không thể truy vấn database.” | Với quan hệ lazy, getter có thể khiến Hibernate nạp dữ liệu bổ sung. |
| “Sửa mọi object là tự lưu.” | Dirty checking áp dụng cho **managed entity** trong persistence context phù hợp. |
| “§flush()§ tức là đã commit.” | Flush đồng bộ SQL; commit mới kết thúc transaction thành công. |
| “Bật §EAGER§ cho mọi quan hệ sẽ nhanh hơn.” | Tải thừa dữ liệu và truy vấn phức tạp có thể làm hiệu năng tệ hơn. |
| “Hibernate tự giải quyết xung đột đồng thời.” | Cần thiết kế transaction, isolation, khóa lạc quan/bi quan và xử lý xung đột phù hợp. |

## 8. Khi nào Hibernate ORM phù hợp?

Hibernate thường phù hợp khi ứng dụng Java có **mô hình domain tương đối rõ**, nhiều entity có quan hệ, cần thực hiện thao tác CRUD và nghiệp vụ qua transaction, muốn giảm mã JDBC lặp lại và tận dụng chuẩn Jakarta Persistence. Khi truy vấn là trọng tâm hơn object graph, cần kiểm soát SQL tuyệt đối hoặc xử lý dữ liệu khối lượng lớn, hãy đánh giá thêm JDBC, truy vấn native, jOOQ hoặc giải pháp truy cập dữ liệu phù hợp khác.

Một quy trình tư duy thực tế khi thiết kế chức năng persistence:

1. Xác định **dữ liệu và ràng buộc** cần tồn tại trong database, cùng ranh giới transaction nghiệp vụ.
2. Quyết định **entity nào có identity**, dữ liệu nào nên là embedded/value object.
3. Ánh xạ khóa chính, khóa ngoại, kiểu dữ liệu và quan hệ bằng annotation/cấu hình.
4. Thiết kế truy vấn và fetch theo **nhu cầu của từng use case**, đo số lượng và chi phí SQL thực tế.
5. Dùng migration, test tích hợp và kiểm tra cạnh tranh dữ liệu để xác nhận hành vi của cả Java lẫn database.

## 9. Ghi nhớ qua một ví dụ tổng hợp

Ở phía Java, lập trình viên làm việc với:

§§§java
PurchaseOrder order = em.find(PurchaseOrder.class, 42L);
Customer customer = order.getCustomer();
order.changeTotal(new BigDecimal("299.90"));
§§§

Ở phía quan hệ, thông tin là hàng §purchase_orders(id=42, customer_id=7, total=...)§ cùng hàng §customers(id=7, name=...)§. Hibernate dùng mapping để biết §customer_id§ tương ứng với §PurchaseOrder.customer§, dùng persistence context để quản lý định danh/trạng thái của entity, và đồng bộ thay đổi bằng SQL trong transaction khi thích hợp.

**Ý chính:** Hibernate ORM giải quyết “độ lệch” bằng một **lớp ánh xạ và quản lý trạng thái** giữa object graph Java với bảng quan hệ. Nó giúp code nghiệp vụ thao tác trên entity tự nhiên hơn, trong khi lập trình viên vẫn phải chủ động hiểu khóa, join, transaction, cách nạp dữ liệu và chi phí truy vấn để ứng dụng đúng và hiệu quả.
