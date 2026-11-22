# Khi nào JPA provider có thể thực thi SQL trước commit?

## 1. Vấn đề: gọi persist() chưa phải commit(), nhưng SQL có thể đã chạy

Trong ứng dụng Jakarta Persistence (JPA), lập trình viên thường gọi **EntityManager.persist()**, sửa một entity đang được quản lý, hoặc gọi **EntityManager.remove()** trong một transaction. JPA lưu lại các thay đổi trong **persistence context** và đồng bộ chúng với cơ sở dữ liệu ở những thời điểm thích hợp.

Một cách hiểu sai phổ biến:

> “Provider chỉ thực hiện INSERT, UPDATE hoặc DELETE khi gọi commit().”

Thực tế, **JPA provider có thể gửi SQL tới database từ trước lúc commit**. Chẳng hạn:

- Ứng dụng chủ động gọi **EntityManager.flush()**.
- Provider cần bảo đảm một truy vấn JPQL thấy được những thay đổi có thể ảnh hưởng kết quả trong chế độ **FlushModeType.AUTO**.
- Chiến lược sinh khóa **IDENTITY** có thể buộc provider INSERT sớm để lấy khóa chính do database tạo.
- Provider quyết định đồng bộ sớm trong giới hạn ngữ nghĩa flush, hoặc một API/framework phát sinh yêu cầu đồng bộ.
- Ứng dụng tự thực hiện native SQL trong transaction, dù transaction chưa commit.

Điều then chốt là **thực thi SQL không đồng nghĩa commit transaction**. Một lệnh INSERT có thể đã đến database, được kiểm tra constraint và giữ lock, nhưng **chưa trở thành thay đổi được commit**. Nếu transaction rollback, các thay đổi DML mang tính giao dịch sẽ được hoàn tác theo ngữ nghĩa của DB.

Bài học này giúp phân biệt các thời điểm **thay đổi entity trong bộ nhớ**, **flush**, **SQL được gửi đi**, **commit** và **rollback**, cũng như nhận diện những trường hợp provider có quyền chọn thời điểm thực thi cụ thể.

## 2. Năm khái niệm phải phân biệt

### 2.1. Persistence context

**Persistence context** là tập các entity được EntityManager quản lý theo định danh JPA và trạng thái tương ứng. Với entity **managed**, provider theo dõi trạng thái để đồng bộ những thay đổi cần thiết xuống database.

Ví dụ:

~~~java
Product product = em.find(Product.class, productId);
product.setPrice(new BigDecimal("125.00"));
~~~

Sau khi gán giá mới, object Java đã thay đổi. Nhưng chưa thể kết luận database đã nhận UPDATE. Provider có thể phát hiện thay đổi trong quá trình dirty checking rồi gửi UPDATE tại một điểm flush phù hợp.

### 2.2. Flush

**Flush** là thao tác đồng bộ những thay đổi đang chờ trong persistence context với database. Khi flush cần thiết, provider thực hiện SQL phù hợp để phản ánh các entity/collection được quản lý vào trạng thái database trong transaction hiện tại.

~~~java
em.flush();
~~~

Flush có thể thực hiện INSERT, UPDATE, DELETE, cập nhật bảng liên kết, thao tác version hoặc các SQL khác tùy mapping/provider. Một lần flush cũng có thể không phát SQL nếu không có thay đổi nào cần đồng bộ.

### 2.3. Commit

**Commit** kết thúc một transaction thành công theo cơ chế quản lý giao dịch đang sử dụng. Provider cần bảo đảm các thay đổi persistence context phải đồng bộ phù hợp trước khi transaction commit hoàn tất, nhưng việc đồng bộ có thể đã xảy ra ở những điểm trước đó.

~~~java
tx.commit();
~~~

Với một transaction chứa DML, sau commit thành công, dữ liệu trở thành dữ liệu đã commit theo khả năng của database. Commit không nhất thiết tạo một lần flush mới có SQL nếu mọi thay đổi đã được đồng bộ và không có thay đổi mới.

### 2.4. Rollback

**Rollback** hủy các tác động database của transaction chưa commit theo cơ chế giao dịch SQL tương ứng. Một entity trong bộ nhớ có thể vẫn giữ ID và giá trị đã gán, nên không được coi object Java sau rollback là biểu diễn chắc chắn của dữ liệu đã lưu.

~~~java
tx.rollback();
~~~

Một lệnh INSERT đã chạy trước rollback có thể tiêu hao giá trị sequence/identity hoặc kích hoạt cơ chế bên ngoài transaction. **Rollback không đồng nghĩa mọi tác động phụ được đảo ngược hoàn toàn.**

### 2.5. SQL execution

**SQL execution** là lúc database nhận và xử lý câu lệnh như INSERT, UPDATE, DELETE, SELECT, hoặc câu lệnh cấp ID. Nó có thể xảy ra:

~~~text
Thay đổi object Java
      |
      v
Persistence context ghi nhận trạng thái
      |
      v
SQL được thực thi khi cần thiết
      |
      v
Transaction tiếp tục hoạt động
      |
      +---- commit  -> xác nhận thay đổi
      |
      +---- rollback -> hoàn tác DML chưa commit
~~~

Trong tài liệu này, **“SQL chạy trước commit”** là câu lệnh đã được gửi tới DB trong khi transaction vẫn đang hoạt động; không hàm ý một transaction tự động khác đã commit.

## 3. Mô hình vòng đời: persist, update và remove

JPA quản lý những dạng thay đổi chính:

| Thao tác ứng dụng | Ý nghĩa ở persistence context | SQL có thể xảy ra khi nào? |
|---|---|---|
| **em.persist(entity)** | Đăng ký entity mới thành managed | Có thể ngay khi cần sinh ID; tại flush trước query; tại flush tường minh; khi commit |
| **Sửa field entity managed** | Thay đổi trạng thái được theo dõi | Khi dirty checking/flush cần đồng bộ |
| **em.remove(entity)** | Đánh dấu entity managed để xóa | Thường tại flush; có thể trước commit |
| **Thay collection managed** | Ghi nhận thay đổi quan hệ hoặc element collection | Khi flush và provider tạo DML cho join/collection table |
| **em.merge(detached)** | Sao chép trạng thái từ detached vào managed entity | Có thể cần SELECT khi merge và UPDATE/INSERT khi đồng bộ; không đồng nghĩa commit |
| **em.find()** | Tìm entity theo ID, có thể từ context/cache/DB | SELECT có thể chạy ngay, trừ khi đã có entity phù hợp trong context/cache |
| **Query.getResultList()** | Thực thi query | SELECT được chạy; AUTO có thể flush trước để bảo đảm kết quả |
| **em.flush()** | Yêu cầu đồng bộ | Có thể phát DML trước commit |
| **tx.commit()** | Xác nhận transaction | Có thể gây flush còn thiếu rồi commit |

Bảng chỉ mô tả **khả năng và thời điểm điển hình**, không cam kết provider phát đúng một SQL theo mỗi lời gọi Java. ORM có thể trì hoãn, gom batch, sắp xếp lại DML hoặc tránh UPDATE không cần thiết.

### 3.1. persist() không nhất thiết là INSERT tức thì

~~~java
tx.begin();

Product product = new Product("Keyboard", new BigDecimal("90.00"));
em.persist(product);

// Chưa thể khẳng định INSERT đã thực thi tại dòng trên.

tx.commit();
~~~

Nếu ID được cấp bởi sequence trước khi INSERT, provider có thể lấy ID trước, rồi trì hoãn INSERT đến lúc flush/commit. Nếu ID do cột IDENTITY của DB tạo, provider có thể cần INSERT sớm để nhận ID. Cấu hình generator, lifecycle và provider quyết định diễn biến thực tế.

### 3.2. Dirty checking không nhất thiết xảy ra tại setter

~~~java
tx.begin();

Product managed = em.find(Product.class, 10L);
managed.setPrice(new BigDecimal("95.00"));

// Trong nhiều implementation, chưa có UPDATE tại setter.
em.flush();

// UPDATE có thể đã chạy ở đây, nhưng transaction chưa commit.
tx.commit();
~~~

Provider theo dõi giá trị của managed entity bằng các cơ chế dirty checking thích hợp. **Setter chỉ thay đổi object Java**; không phải một API yêu cầu DB thực thi UPDATE ngay tại thời điểm đó.

## 4. Ví dụ nền: entity Product có version và ràng buộc

Ta sử dụng một entity nhỏ để minh họa:

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 40)
    private String sku;

    @Column(name = "price", nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected Product() {}

    public Product(String sku, BigDecimal price) {
        this.sku = Objects.requireNonNull(sku);
        this.price = Objects.requireNonNull(price);
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = Objects.requireNonNull(price);
    }

    public long getVersion() {
        return version;
    }
}
~~~

Một schema PostgreSQL tương thích về ý tưởng:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    price NUMERIC(12, 2) NOT NULL,
    version BIGINT NOT NULL
);
~~~

**Lưu ý:** đây là một mapping minh họa với IDENTITY. Các câu Java sau giả định đã có EntityManagerFactory, EntityManager, kết nối DB và giao dịch đúng cách. DDL, kiểu numeric, quy tắc ID và thời điểm INSERT có thể khác giữa PostgreSQL, MySQL, Oracle, SQL Server và các JPA provider.

## 5. Trường hợp 1: gọi EntityManager.flush() tường minh

Đây là trường hợp rõ ràng nhất để yêu cầu provider đồng bộ trước commit:

~~~java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = new Product(
        "MOUSE-01",
        new BigDecimal("25.00")
    );
    em.persist(product);

    em.flush();

    // Những DML cần thiết để đồng bộ có thể đã được thực thi.
    // Transaction vẫn hoạt động: chưa commit.
    System.out.println("id=" + product.getId());

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

**em.flush() không phải commit()**. Nếu sau flush, một câu lệnh khác trong transaction thất bại và transaction rollback, INSERT/UPDATE/DELETE do flush đã thực hiện vẫn bị hoàn tác theo ngữ nghĩa transaction của DB.

### 5.1. Khi nào cần flush tường minh?

Một số mục đích thực tế:

- Muốn database **kiểm tra những ràng buộc thực thi ngay khi statement chạy** trước khi thực hiện bước nghiệp vụ tiếp theo.
- Muốn phát hiện lỗi FK/UNIQUE/NOT NULL sớm trong transaction, dù một số constraint có thể được trì hoãn đến commit.
- Muốn những thay đổi JPA đã được đồng bộ trước khi chạy một native SQL phụ thuộc vào các thay đổi đó.
- Muốn biết optimistic-locking conflict sớm hơn trong một số mapping, nếu kiểm tra được thực hiện cùng DML tại flush.
- Muốn thực hiện xử lý theo từng batch có kiểm soát trước khi clear persistence context.

Không nên gọi flush liên tục chỉ vì muốn “chắc chắn dữ liệu đã lưu”. Mỗi flush có thể làm provider phải kiểm tra trạng thái entity, tạo thêm SQL round-trip, phá khả năng gom batch hoặc tăng thời gian giữ lock. Nếu không có nhu cầu đồng bộ sớm, thường để transaction/provider xác định thời điểm phù hợp sẽ đơn giản hơn.

### 5.2. Flush tường minh không chắc tạo SQL

~~~java
tx.begin();

Product product = em.find(Product.class, 10L);
em.flush(); // Không có thay đổi thì có thể không phát UPDATE nào.

tx.commit();
~~~

Flush là yêu cầu **đồng bộ trạng thái**, không phải yêu cầu “thực hiện ít nhất một SQL”. Nếu persistence context đang sạch, có thể không có DML cần gửi.

### 5.3. Flush không bảo đảm constraint luôn được báo trước commit

Nhiều constraint như NOT NULL hoặc UNIQUE thông thường được kiểm tra khi statement chạy. Nhưng một số DB hỗ trợ **deferrable constraints**, cho phép trì hoãn kiểm tra đến cuối transaction. Khi đó, **em.flush() có thể thành công nhưng commit() vẫn thất bại**. Ngoài ra, trigger, cơ chế locking và quy tắc DBMS cũng có thể khiến lỗi xuất hiện ở thời điểm khác.

Vì vậy, **flush giúp phát hiện một nhóm lỗi sớm**, không phải cam kết toàn bộ transaction sau đó chắc chắn commit thành công.

## 6. Trường hợp 2: FlushModeType.AUTO trước truy vấn

JPA có hai chế độ flush chuẩn trên EntityManager/Query:

- **FlushModeType.AUTO**: provider phải bảo đảm những thay đổi trong persistence context có thể ảnh hưởng kết quả truy vấn được phản ánh phù hợp để truy vấn có kết quả đúng trong ngữ nghĩa được đặc tả. Một cách làm là flush trước query.
- **FlushModeType.COMMIT**: provider trì hoãn đồng bộ theo hướng commit; ảnh hưởng của những thay đổi chưa flush lên kết quả query trong cùng transaction **không được đặc tả đầy đủ**.

**AUTO là mặc định** trong các ngữ cảnh thông thường của JPA, nhưng phải hiểu **AUTO không cam kết mọi truy vấn đều flush**.

### 6.1. Ví dụ: thêm mới rồi truy vấn

Giả sử dùng một entity với chiến lược SEQUENCE để provider có thể nhận ID mà chưa cần INSERT ngay:

~~~java
@Entity
@Table(name = "invoices")
public class Invoice {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "invoice_id_generator"
    )
    @SequenceGenerator(
        name = "invoice_id_generator",
        sequenceName = "invoice_id_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "reference_code", nullable = false)
    private String referenceCode;

    protected Invoice() {}

    public Invoice(String referenceCode) {
        this.referenceCode = referenceCode;
    }
}
~~~

Chạy trong transaction:

~~~java
tx.begin();

em.setFlushMode(FlushModeType.AUTO);
Invoice invoice = new Invoice("INV-2026-001");
em.persist(invoice);

Long matching = em.createQuery(
    "select count(i) from Invoice i " +
    "where i.referenceCode = :code",
    Long.class
).setParameter("code", "INV-2026-001")
 .getSingleResult();

// Với AUTO, kết quả query phải phản ánh đúng các thay đổi
// có thể ảnh hưởng đến query theo contract JPA.

tx.commit();
~~~

Một cách triển khai phổ biến:

~~~text
BEGIN
SELECT nextval('invoice_id_seq')    -- provider cấp ID từ sequence
INSERT INTO invoices (...) VALUES (...)  -- auto flush trước query
SELECT count(*) FROM invoices WHERE reference_code = ...
COMMIT
~~~

Trình tự trên chỉ là ví dụ SQL có thể gặp trên PostgreSQL. Provider có thể áp dụng cơ chế khác để bảo đảm kết quả query trong AUTO; **không bắt buộc phát INSERT trước mỗi SELECT** nếu vẫn đáp ứng ngữ nghĩa JPA.

### 6.2. Vì sao query có thể khiến flush?

Giả sử persistence context có một Invoice mới và JPQL hỏi số Invoice trùng referenceCode. Nếu provider chạy SELECT trên database mà chưa tính đến Invoice mới, kết quả có thể thiếu một dòng. AUTO cho phép và trong những trường hợp cần thiết buộc provider phải **bảo đảm truy vấn phản ánh các thay đổi liên quan**.

Thực tế, ORM có thể:

1. Kiểm tra những bảng hoặc “query spaces” mà query sẽ đọc.
2. So sánh với những loại DML đang chờ.
3. Đồng bộ nếu query có thể bị ảnh hưởng.
4. Thực hiện SELECT và tạo kết quả.

Đây là một hướng triển khai phổ biến, **không phải thuật toán bắt buộc giống nhau ở mọi provider**.

### 6.3. Query không liên quan có thể không gây flush

~~~java
tx.begin();

Invoice invoice = new Invoice("INV-2026-002");
em.persist(invoice);

List<Country> countries = em.createQuery(
    "select c from Country c order by c.code",
    Country.class
).getResultList();

tx.commit();
~~~

Nếu pending INSERT Invoice không ảnh hưởng query Country, một provider có thể không cần flush trước SELECT Country. Nhưng **không được lấy kết quả log của một lần chạy để suy ra AUTO luôn chỉ flush khi các bảng giao nhau**. Provider có thể đồng bộ rộng hơn mức tối thiểu và hành vi có thể thay đổi theo phiên bản.

### 6.4. Query trả managed entity đã có trong context

Khi **em.find()** hoặc JPQL lấy lại một entity đã managed, provider phải duy trì ngữ nghĩa identity và trạng thái của persistence context. Có những truy vấn không cần UPDATE trước vì query không phụ thuộc vào giá trị đang đổi. Có những truy vấn lọc theo trường đang sửa lại cần bảo đảm kết quả phù hợp.

Ví dụ:

~~~java
tx.begin();

Product product = em.find(Product.class, 10L);
product.setPrice(new BigDecimal("100.00"));

List<Product> expensive = em.createQuery(
    "select p from Product p where p.price >= :min",
    Product.class
).setParameter("min", new BigDecimal("90.00"))
 .getResultList();

tx.commit();
~~~

Nếu query lọc theo price vừa đổi, provider phải xem xét tác động của trạng thái managed lên tập kết quả trong AUTO. Trong thực tế, có thể thấy một UPDATE trước SELECT. Không nên mặc định getter hoặc setter trên managed entity là đủ để mọi SQL query đều thấy cùng giá trị nếu không có cơ chế flush/query synchronization phù hợp.

## 7. Trường hợp 3: FlushModeType.COMMIT và giới hạn cần nhớ

Có thể cấu hình trên EntityManager:

~~~java
em.setFlushMode(FlushModeType.COMMIT);
~~~

Hoặc trên riêng Query:

~~~java
TypedQuery<Long> query = em.createQuery(
    "select count(i) from Invoice i",
    Long.class
);
query.setFlushMode(FlushModeType.COMMIT);
Long count = query.getSingleResult();
~~~

Với **COMMIT**, hiệu ứng của những thay đổi chưa flush lên kết quả các query trong transaction là **unspecified** theo đặc tả. Không được viết logic nghiệp vụ phụ thuộc vào việc query chắc chắn **thấy** hay chắc chắn **không thấy** pending INSERT/UPDATE.

### 7.1. COMMIT không đồng nghĩa “không SQL cho đến commit”

Một số trường hợp vẫn có SQL trước commit:

- **em.flush()** được gọi tường minh.
- **GenerationType.IDENTITY** có thể cần INSERT sớm để lấy ID.
- **em.find()** hoặc query vẫn phải chạy SELECT để đọc dữ liệu.
- Native query ứng dụng gọi có thể thực thi trực tiếp, kể cả khi chưa commit.
- Các cơ chế provider, mapping hoặc API khác có thể đòi hỏi thao tác SQL trước cuối transaction.

Do đó, **FlushModeType.COMMIT không phải khóa an toàn nhằm cấm mọi SQL trước commit**, cũng không phải isolation level hoặc chế độ autocommit của JDBC.

### 7.2. Khi nào dùng COMMIT?

Nó có thể phù hợp khi:

- Ứng dụng thực hiện nhiều thay đổi nhưng không cần query trong transaction phụ thuộc trạng thái chưa flush.
- Muốn giảm những điểm đồng bộ không cần thiết trước các query, sau khi đã hiểu contract query.
- Một quy trình xử lý write-heavy được kiểm chứng trên đúng provider.

Nếu một query trong transaction cần nhìn thấy những thay đổi đang chờ theo một quy tắc chắc chắn, dùng AUTO hoặc **em.flush()** tường minh trước query là lựa chọn dễ giải thích hơn. Nhưng chỉ dùng flush để xử lý đồng bộ, không dùng nó để thay transaction commit.

## 8. Trường hợp 4: IDENTITY có thể kích hoạt INSERT sớm

**GenerationType.IDENTITY** thường dựa vào database tạo khóa sau INSERT:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Để có giá trị ID do database cấp, provider có thể phải **gửi INSERT trong transaction trước commit**.

~~~java
tx.begin();

Product product = new Product(
    "KEYBOARD-01",
    new BigDecimal("120.00")
);
em.persist(product);

Long id = product.getId();

// Một số tổ hợp provider/DB sẽ đã thực thi INSERT để nhận id.
// Nhưng có id không chứng minh transaction đã commit.

tx.rollback();
~~~

Nếu provider đã INSERT tại persist(), rollback vẫn có thể hủy hàng dữ liệu đó. Giá trị identity bị cấp có thể **không được tái sử dụng** tùy cơ chế DBMS, nên dãy ID có thể có khoảng trống.

### 8.1. So sánh IDENTITY và SEQUENCE

| Khía cạnh | IDENTITY | SEQUENCE |
|---|---|---|
| Nguồn cấp ID | Cột tự sinh khi INSERT | Sequence/database generator |
| Có thể cần INSERT để có ID? | Thường có | Không nhất thiết; có thể lấy next value trước |
| SQL cấp ID trước commit | INSERT có thể chạy sớm | SELECT nextval hoặc lệnh sequence có thể chạy sớm |
| Có thể trì hoãn INSERT tới flush? | Phụ thuộc provider và ngữ cảnh | Thường thuận lợi hơn |
| JDBC batching INSERT | Có thể bị hạn chế bởi nhu cầu lấy generated key | Thường thuận lợi hơn với cơ chế cấp phát phù hợp |
| Giá trị ID sau rollback | Có thể đã cấp và bị “bỏ phí” | Sequence value có thể đã tăng dù rollback |

**Số SQL và thời điểm cụ thể không giống nhau giữa Hibernate, EclipseLink, dialect và phiên bản.** Ví dụ, một provider có thể trì hoãn INSERT IDENTITY trong những ngữ cảnh nhất định hoặc chọn giải pháp nhận key khác. Điều cần nhớ là **IDENTITY có thể khiến SQL ghi đến DB sớm hơn thời điểm commit**, chứ không phải quy tắc rằng *mọi* persist(IDENTITY) luôn phải thực thi INSERT tại đúng dòng Java đó.

### 8.2. ID có giá trị không nói gì về độ bền transaction

~~~text
persist()  -> provider có ID = 501
flush()    -> DML được đồng bộ nếu cần
rollback() -> hàng được ghi trong transaction bị hoàn tác

Object Java vẫn có thể chứa id = 501.
~~~

Nếu code dùng ID để gửi email, phát event hoặc thông báo “đã lưu thành công” **trước commit**, hệ thống ngoài có thể nhìn thấy một ID mà bản ghi tương ứng không tồn tại sau rollback.

### 8.3. TABLE và UUID generator

Với **TABLE generator**, provider có thể thực thi SELECT/UPDATE trên bảng cấp số khi cần cấp ID, thậm chí trước khi INSERT entity. Hành vi đồng bộ và transaction của các thao tác cấp phát phụ thuộc provider và DB.

Với **UUID**, một provider có thể tạo ID trong JVM mà không cần gọi DB để cấp ID; tuy nhiên, **INSERT entity vẫn có thể được flush trước commit** vì query hoặc yêu cầu đồng bộ. “Không cần SQL để cấp ID” khác với “không bao giờ có SQL trước commit”.

## 9. Trường hợp 5: query native và các API ngoài JPQL

**Native SQL query** do ứng dụng tạo ra thực sự chạy SQL khi API query được thực thi:

~~~java
Object count = em.createNativeQuery(
    "select count(*) from products"
).getSingleResult();
~~~

Câu hỏi phức tạp hơn là **những thay đổi JPA đang chờ có được flush trước native query hay không**. Điều này có thể phụ thuộc JPA API, flush mode, nhà cung cấp, khả năng xác định bảng liên quan và cấu hình.

### 9.1. Đừng đồng nhất native SQL với JPQL

JPQL truy vấn qua tên entity và thuộc tính Java; provider hiểu mapping nên có thể biết những bảng nào liên quan. Với native SQL phức tạp, provider có thể không phân tích đầy đủ câu lệnh để xác định quan hệ giữa query và pending changes.

Vì vậy:

- Trong **AUTO**, một số provider có thể flush trước native query khi dùng API **EntityManager** để bảo đảm sự đồng bộ.
- Khi dùng API riêng như **Hibernate Session**, hành vi tự động flush với native query có thể khác API EntityManager và còn phụ thuộc cấu hình đồng bộ bảng.
- Một native query dùng để UPDATE/DELETE là thao tác SQL riêng, không phải một phép cập nhật managed entity bình thường.

Không nên dựa vào lời khẳng định “native query luôn flush” hoặc “native query không bao giờ flush” cho mọi provider và mọi API.

### 9.2. Khi native SQL cần thấy dữ liệu mới ghi bằng JPA

Nếu nghiệp vụ cần một câu native SQL đọc được các INSERT/UPDATE JPA vừa được thực hiện trong cùng transaction, có thể đồng bộ tường minh:

~~~java
tx.begin();

Product product = new Product(
    "MOUSE-02",
    new BigDecimal("30.00")
);
em.persist(product);

em.flush();

Object count = em.createNativeQuery(
    "select count(*) from products where sku = :sku"
).setParameter("sku", "MOUSE-02")
 .getSingleResult();

tx.commit();
~~~

Đây là trường hợp **flush trước khi phụ thuộc vào native query**. Chú ý native query chạy trong cùng transaction và kết nối do provider quản lý theo cấu hình. Nếu native SQL chạy qua một **DataSource hoặc connection khác**, nó có thể thuộc transaction khác và không nhìn thấy dữ liệu chưa commit vì isolation, dù EntityManager trước đó đã flush.

### 9.3. Bulk JPQL UPDATE/DELETE có hành vi riêng

~~~java
int changed = em.createQuery(
    "update Product p set p.price = :newPrice " +
    "where p.sku = :sku"
).setParameter("newPrice", new BigDecimal("40.00"))
 .setParameter("sku", "MOUSE-02")
 .executeUpdate();
~~~

Bulk DML được thực thi qua query và tác động trực tiếp tới database trong transaction. Nó **không tự cập nhật trạng thái của những managed entity đã có trong persistence context**. Nếu Product đã được find() trước đó, object trong bộ nhớ có thể còn price cũ. Khi dùng bulk update:

1. Xác định pending changes nào cần flush trước bulk DML.
2. Thực hiện bulk DML trong transaction.
3. Làm mới hoặc clear những managed entity bị ảnh hưởng theo nhu cầu.
4. Không giả định mọi callback, version check và dirty checking của từng entity được áp dụng như khi sửa managed entity thông thường.

Chẳng hạn:

~~~java
tx.begin();

Product product = em.find(Product.class, 10L);
BigDecimal before = product.getPrice();

em.createQuery(
    "update Product p set p.price = :price " +
    "where p.id = :id"
).setParameter("price", new BigDecimal("50.00"))
 .setParameter("id", 10L)
 .executeUpdate();

// product trong persistence context có thể vẫn giữ price cũ.
em.refresh(product); // Tải lại từ DB trong transaction phù hợp.

tx.commit();
~~~

Trong môi trường có thay đổi JPA chưa flush trên cùng entity, cần đặc biệt cẩn thận với thứ tự flush/bulk DML để tránh ghi đè lẫn nhau. Một cách phổ biến là flush rồi bulk update, sau đó clear/refresh có kiểm soát.

## 10. Trường hợp 6: commit tự gây flush nếu còn thay đổi

Khi transaction sắp commit, những thay đổi cần được đồng bộ để dữ liệu persist được ghi và commit như mong đợi:

~~~java
tx.begin();

Product product = em.find(Product.class, 10L);
product.setPrice(new BigDecimal("77.00"));

tx.commit();
~~~

Nếu UPDATE chưa chạy trước đó, quá trình commit sẽ cần xử lý những thay đổi pending phù hợp. Provider có thể phát UPDATE trong giai đoạn flush trước khi JDBC/JTA commit DB transaction.

Một trình tự thường thấy:

~~~text
BEGIN
SELECT ... FROM products WHERE id = 10
(setPrice trong JVM)
UPDATE products SET price = 77.00, version = ... WHERE id = 10 AND version = ...
COMMIT
~~~

Đây chỉ là ví dụ SQL, không bảo đảm câu UPDATE chứa đúng những cột hay thứ tự như trên. Cơ chế optimistic locking, dynamic update và batching tùy provider.

### 10.1. Flush trước commit, commit sau flush

Ở tầng khái niệm:

~~~text
Application
  tx.begin()
  em.persist()
  em.flush()     --- SQL INSERT có thể thực thi
  thay đổi tiếp
  tx.commit()    --- có thể flush phần mới rồi DB COMMIT
~~~

Một transaction có thể có **nhiều điểm flush**. SQL được thực thi ở flush đầu tiên nhưng transaction tiếp tục và còn có DML mới ở flush/commit sau. Vì vậy commit không có nghĩa “mọi SQL lần đầu mới được gửi”.

### 10.2. Transaction không có thay đổi

Nếu chỉ đọc dữ liệu rồi commit, provider không cần sinh một UPDATE/INSERT không cần thiết. Nếu entity được sửa rồi trả lại giá trị cũ trước flush, provider cũng có thể nhận thấy không còn dirty change và không phát UPDATE. SQL thực tế phụ thuộc dirty checking và mapping.

## 11. Tác động của SQL sớm: DB constraint và lock

Một INSERT/UPDATE/DELETE được gửi trước commit có thể đã tương tác với database:

- Kiểm tra **NOT NULL, UNIQUE, CHECK, FOREIGN KEY** tại thời điểm thực thi thích hợp.
- Giữ row lock hoặc index/key lock.
- Cập nhật dữ liệu chưa commit trong transaction.
- Viết redo/undo/WAL hoặc log tương đương.
- Gọi trigger hoặc cơ chế DB đã cấu hình.
- Tạo/tiêu hao sequence, identity hoặc giá trị generator.

### 11.1. Phát hiện UNIQUE conflict tại flush

Giả sử products.sku có UNIQUE và đã có một sản phẩm với sku "MOUSE-01":

~~~java
tx.begin();

em.persist(new Product(
    "MOUSE-01",
    new BigDecimal("20.00")
));

em.flush(); // Có thể ném exception do UNIQUE.

tx.commit();
~~~

Nếu constraint được kiểm tra ngay ở statement, provider sẽ nhận SQLException hoặc lỗi ràng buộc và chuyển thành exception ở tầng JPA/provider. Khi transaction bị đánh dấu rollback-only hoặc lỗi khiến transaction không còn an toàn, phải rollback và xử lý; không tiếp tục cố commit sau lỗi một cách mù quáng.

Không nên bắt exception từ flush rồi giả định persistence context trở lại sạch. Khi xảy ra PersistenceException nghiêm trọng trong flush, cách tiếp cận an toàn thường là rollback, kết thúc EntityManager/transaction theo cơ chế tương ứng và thử lại trong một context mới nếu nghiệp vụ cho phép.

### 11.2. FK có thể được kiểm tra trước commit

Nếu OrderLine tham chiếu Order chưa tồn tại, một INSERT OrderLine có thể vi phạm foreign key ngay khi SQL chạy. Trong cùng transaction, provider có thể phải sắp xếp INSERT Order trước OrderLine hoặc sử dụng cơ chế key/constraint phù hợp.

Nếu FK là deferrable và đang được trì hoãn theo cơ chế DB, vi phạm có thể chỉ xuất hiện khi commit. **Thời điểm exception phản ánh cả flush timing và constraint timing**, không chỉ một phía.

### 11.3. Lock có thể kéo dài sau flush

Một UPDATE chạy ở flush có thể giữ lock tới cuối transaction:

~~~text
T1: BEGIN
T1: UPDATE products SET price = ... WHERE id = 10   <-- flush
T1: thực hiện thêm tính toán / gọi API / thao tác khác
T2: UPDATE products SET price = ... WHERE id = 10   <-- có thể chờ
T1: COMMIT
T2: tiếp tục theo isolation/locking của DB
~~~

Nếu flush sớm rồi transaction còn làm việc lâu, lock có thể bị giữ lâu hơn, tăng tranh chấp và deadlock risk. Không nên “flush cho chắc” tại mỗi bước nếu mục tiêu đơn giản là lưu dữ liệu ở cuối transaction.

### 11.4. Dữ liệu chưa commit có nhìn thấy từ transaction khác không?

Sau flush, **transaction hiện tại** thường có thể đọc lại những thay đổi của chính nó thông qua kết nối/giao dịch phù hợp. **Transaction khác** có nhìn thấy dữ liệu đó hay không phụ thuộc isolation level và DBMS.

Ví dụ với isolation phổ biến **READ COMMITTED**, transaction khác không được đọc dữ liệu chưa commit chỉ vì transaction thứ nhất đã flush. Với READ UNCOMMITTED trên DBMS thực sự cho phép dirty reads, ngữ nghĩa có thể khác.

Flush **không** phải một cơ chế công bố dữ liệu cho mọi người đọc. Để ghi trở thành committed và được quan sát theo quy tắc isolation, cần commit thành công.

## 12. Rollback sau flush: điều gì còn, điều gì mất?

~~~java
tx.begin();

Product p = new Product("ROLLBACK-01", new BigDecimal("15.00"));
em.persist(p);
em.flush();

Long allocatedId = p.getId();
tx.rollback();
~~~

Sau rollback:

- INSERT do flush thực hiện **không còn là hàng đã commit**, theo transaction semantics của DB.
- **allocatedId** có thể vẫn được giữ trong object p ở JVM.
- Sequence/identity generator có thể đã tăng và **không lùi lại**; dãy ID có thể có khoảng trống.
- Persistence context và trạng thái object sau rollback cần được xử lý theo vòng đời JPA; không giả định p vẫn là managed entity được DB lưu.
- Những tác động ngoài transaction DB, ví dụ HTTP call, email hoặc message được gửi không qua outbox, **không tự được rollback**.

### 12.1. Đừng phát sự kiện bên ngoài trước commit chỉ vì flush đã thành công

Một lỗi thiết kế:

~~~java
tx.begin();

Product p = new Product("EVENT-01", new BigDecimal("60.00"));
em.persist(p);
em.flush();

externalPublisher.publish("PRODUCT_CREATED", p.getId());

tx.rollback(); // Bản ghi không được commit, event đã được gửi.
~~~

Nếu message broker hoặc dịch vụ bên ngoài không thuộc cùng transaction phân tán có bảo đảm, event có thể thoát ra trước khi dữ liệu có thật. Phương án phổ biến là **transactional outbox**: ghi event vào bảng outbox trong cùng DB transaction, rồi publish sau khi commit theo quy trình riêng. Một số framework có callback afterCommit; dùng callback vẫn cần cân nhắc khả năng gửi thất bại sau commit và cơ chế retry.

**Flush không đủ để kích hoạt nghiệp vụ phải xảy ra “sau khi dữ liệu đã lưu chắc chắn”.**

## 13. @Version và optimistic locking: có thể kiểm tra ở flush

Entity có **@Version** để hỗ trợ optimistic locking. Khi một managed entity được sửa, provider có thể phát SQL dạng:

~~~sql
UPDATE products
SET price = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Nếu phiên bản ở DB không còn phù hợp, câu UPDATE có thể ảnh hưởng 0 hàng và provider phát hiện xung đột optimistic locking. Kiểm tra có thể xảy ra **khi flush**, hoặc muộn hơn trong vòng đời transaction tùy mapping/provider.

~~~java
tx.begin();

Product product = em.find(Product.class, 10L);
product.setPrice(new BigDecimal("99.00"));

em.flush(); // Có thể phát hiện optimistic locking conflict.

tx.commit();
~~~

Điểm cần nhớ:

- **@Version** không khiến mọi setter lập tức chạy UPDATE.
- Nếu provider trì hoãn UPDATE, xung đột có thể chưa xuất hiện tại setter.
- Nếu flush phát UPDATE sớm, xung đột có thể xuất hiện trước commit.
- Một flush thành công không loại trừ lỗi transaction ở những bước sau.
- Bulk JPQL UPDATE/DELETE không tự áp dụng đầy đủ optimistic locking giống việc update từng managed entity; phải thiết kế explicit version handling nếu cần.

### 13.1. LockModeType.OPTIMISTIC_FORCE_INCREMENT

Một số API khóa JPA có thể yêu cầu tăng version hoặc kiểm tra version. Provider có thể thực hiện SQL theo thời điểm do đặc tả và implementation cho phép, có thể liên quan flush hoặc commit.

Không nên dùng một lock mode như thủ thuật để “ép tất cả SQL chạy ngay”. Nếu cần đồng bộ trạng thái, **em.flush()** mới là API chủ đích; nếu cần đảm bảo nhất quán tranh chấp, dùng lock mode/transaction isolation phù hợp.

## 14. Cascade và các collection có thể làm phát nhiều DML

Một entity có quan hệ:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi persist Order hoặc remove OrderLine, provider có thể cần thêm INSERT/DELETE hoặc UPDATE bảng liên quan. Một lần **flush** có thể khiến **nhiều statement** chứ không chỉ một:

~~~text
INSERT orders ...
INSERT order_lines ...
INSERT order_lines ...
DELETE order_line_discounts ...
DELETE order_lines ...
...
~~~

Số statement phụ thuộc cascade, phía sở hữu quan hệ, orphanRemoval, collection mapping, ID generator, batching và trạng thái managed. Không thể dự đoán số INSERT/DELETE chỉ từ số lần gọi em.persist().

### 14.1. Thứ tự gọi Java không phải thứ tự SQL

~~~java
em.persist(parent);
em.persist(childA);
em.persist(childB);
~~~

Provider có thể gom nhóm theo entity type, phụ thuộc khóa ngoại, thứ tự insert/update và khả năng batch. Nếu child FK trỏ đến parent mới, provider phải lập kế hoạch để DB thỏa constraint hoặc dùng cơ chế phù hợp. Thứ tự DML thực tế có thể khác thứ tự lời gọi Java.

Điều này quan trọng khi bạn dựa vào **trigger**, **unique constraint**, hoặc dùng DELETE rồi INSERT với cùng natural key trong một transaction. Một số provider có thể thực hiện INSERT trước DELETE khi flush, khiến xung đột UNIQUE dù code Java gọi remove trước persist.

Khi gặp trường hợp như vậy, cần thiết kế nghiệp vụ và lộ trình DML rõ (chẳng hạn flush phần xóa trước khi thêm giá trị trùng nếu phù hợp), hoặc thay vì xóa/tạo mới thì cập nhật entity hiện có. Không nên biến việc thêm nhiều flush thành mặc định cho toàn bộ ứng dụng.

### 14.2. JDBC batching và nhiều lần flush

Provider có thể gom nhiều DML tương tự vào batch để giảm round-trip. Khi flush thường xuyên:

- Batch có thể bị thực thi sớm trước khi đủ số statement.
- ORM phải chạy dirty checking nhiều lần hơn.
- Thời gian giữ khóa DB có thể tăng nếu transaction vẫn kéo dài.
- Một số chiến lược sinh khóa như IDENTITY có thể hạn chế batching INSERT của provider.

Với hàng nghìn entity, có thể chủ động flush/clear theo lô, nhưng phải hiểu EntityManager state và giới hạn bộ nhớ. Bài toán batch processing khác với việc “flush ngay sau mỗi persist để dữ liệu an toàn”.

## 15. Khi nào flush bị giới hạn bởi transaction?

### 15.1. RESOURCE_LOCAL

Với EntityManager dạng RESOURCE_LOCAL trong Java SE:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();
    Product product = new Product(
        "RESOURCE-01", new BigDecimal("33.00")
    );
    em.persist(product);
    em.flush();
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

**em.flush()** yêu cầu transaction hợp lệ khi thực hiện đồng bộ thay đổi. Nếu gọi flush trong ngữ cảnh không có transaction được tham gia phù hợp, JPA có thể ném **TransactionRequiredException**. Provider không được tự coi một flush ngoài transaction là một COMMIT ứng dụng không mong đợi.

### 15.2. JTA và transaction được quản lý bởi framework

Trong Jakarta EE hoặc Spring dùng JTA/container-managed transaction, ứng dụng thường không tự gọi EntityTransaction.commit(). Ranh giới transaction có thể được khai báo bằng annotation hoặc do container/framework kiểm soát:

~~~java
@Transactional
public void adjustPrice(Long id, BigDecimal price) {
    Product product = em.find(Product.class, id);
    product.setPrice(price);
    em.flush();
    // Transaction manager sẽ commit hoặc rollback khi kết thúc scope.
}
~~~

Đoạn này giả định annotation **@Transactional** được import từ cơ chế đang dùng (ví dụ jakarta.transaction.Transactional hoặc Spring). **flush bên trong method không thay thế commit do transaction manager thực hiện**.

Nếu dùng persistence context **unsynchronized** với JTA, nó có thể chưa tham gia transaction hiện tại cho tới khi ứng dụng yêu cầu join thích hợp. Cần hiểu **SynchronizationType.UNSYNCHRONIZED** và **EntityManager.joinTransaction()** trong môi trường phù hợp; không giả định có một JTA transaction đang chạy là mọi EntityManager đều đã sẵn sàng flush vào transaction đó.

### 15.3. Giao dịch read-only không phải quy tắc SQL JPA chung

Một số framework hỗ trợ **readOnly=true** và có thể điều chỉnh flush mode hoặc quyền ghi để tối ưu. Đây không phải một kiểu FlushModeType chuẩn thứ ba của JPA. Tác dụng phụ thuộc transaction manager/provider và cấu hình.

Không nên dựa vào readOnly=true như cơ chế an toàn ngăn mọi thay đổi DB. Nếu nghiệp vụ cấm ghi, cần phân quyền, transaction policy và bảo vệ database thích hợp.

## 16. Callback của entity có chạy trước commit không?

JPA có những lifecycle callbacks như **@PrePersist**, **@PostPersist**, **@PreUpdate**, **@PostUpdate**, **@PreRemove**, **@PostRemove**. Một số callback có thể được kích hoạt trong quá trình provider thực hiện thao tác persistence/flush trước commit.

Ví dụ:

~~~java
@Entity
public class AuditExample {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @PreUpdate
    public void beforeUpdate() {
        // Được gọi trước thao tác cập nhật tương ứng,
        // nhưng không có nghĩa transaction đã commit.
    }

    @PostUpdate
    public void afterUpdate() {
        // Có thể được gọi trong flush, trước commit.
    }
}
~~~

Một số chi tiết:

- Thời điểm chính xác của callback phụ thuộc loại thao tác và quy tắc vòng đời JPA/provider.
- **@PostPersist** có thể xảy ra sau INSERT được provider thực thi, nhưng vẫn trong transaction chưa commit.
- **@PreUpdate/@PostUpdate** phụ thuộc có UPDATE thực sự được ghi nhận theo ngữ nghĩa lifecycle; sửa rồi khôi phục giá trị cũ có thể không tạo UPDATE.
- Không phát email, event hoặc gọi dịch vụ ngoài với giả định callback “Post” chắc chắn có nghĩa database đã commit.

Nếu nghiệp vụ cần hành động sau commit, nên dùng cơ chế transaction-aware thích hợp hoặc outbox, không đánh đồng **@PostPersist** với **afterCommit**.

## 17. Flush không phải refresh, clear, detach hay commit

Những API này dễ bị nhầm:

| API | Ý nghĩa | Có tự commit không? |
|---|---|---|
| **em.flush()** | Đồng bộ pending changes tới DB transaction | Không |
| **em.refresh(entity)** | Đọc lại trạng thái entity từ DB, theo semantics JPA | Không |
| **em.clear()** | Detach mọi managed entity khỏi persistence context | Không |
| **em.detach(entity)** | Cho một entity rời khỏi persistence context | Không |
| **em.persist(entity)** | Đưa entity mới vào managed state | Không |
| **em.merge(entity)** | Sao chép trạng thái sang managed entity | Không |
| **tx.commit()** | Xác nhận transaction RESOURCE_LOCAL | Có, đây là commit transaction |
| **tx.rollback()** | Hủy transaction RESOURCE_LOCAL | Không; là rollback |

### 17.1. Cẩn thận với clear() khi chưa flush

~~~java
tx.begin();

Product p = em.find(Product.class, 10L);
p.setPrice(new BigDecimal("88.00"));

em.clear();

tx.commit();
~~~

Nếu UPDATE chỉ mới tồn tại trong persistence context và chưa được đồng bộ, **clear()** sẽ detach entity; thay đổi chưa flush có thể không được ghi xuống DB. Không nên dùng clear() như một cách “tiết kiệm bộ nhớ” mà không hiểu thay đổi nào đang pending.

Trong xử lý batch theo lô có chủ đích:

~~~java
for (int i = 0; i < products.size(); i++) {
    em.persist(products.get(i));

    if ((i + 1) % 50 == 0) {
        em.flush();
        em.clear();
    }
}

em.flush();
em.clear();
~~~

Đây là khung ý tưởng trong **một transaction đang hoạt động**. Khi clear, những object đã persist trước đó trở thành detached; nếu tiếp tục cần tham chiếu/quan hệ với chúng phải xử lý lại. Đối với IDENTITY, persist có thể đã gây INSERT sớm và batching có thể hạn chế. Không nên dùng đoạn này nguyên xi cho mọi mô hình entity có cascading relationships phức tạp.

### 17.2. Refresh sau flush

Nếu cần đọc giá trị database tạo ra qua trigger hoặc generated column, đôi khi ứng dụng cần flush rồi refresh:

~~~java
tx.begin();

Product p = new Product("REFRESH-01", new BigDecimal("10.00"));
em.persist(p);
em.flush();
em.refresh(p);

tx.commit();
~~~

Tuy nhiên, **không phải mọi cơ sở dữ liệu/provider đều yêu cầu refresh** để đọc các cột được tạo bởi database; mapping và cơ chế retrieving generated values có thể khác nhau. Refresh cũng không có nghĩa commit. Nếu trigger chỉ hoàn thành công việc khi commit hoặc một dịch vụ ngoài bất đồng bộ, refresh trước commit không đảm bảo thấy tác động đó.

## 18. Ghi log để biết SQL thật sự chạy lúc nào

Không nên suy đoán thời điểm SQL chỉ từ dòng Java. Cần ghi nhận **SQL do provider phát** và **ranh giới transaction**.

Ví dụ các thuộc tính riêng Hibernate trong môi trường dev/test:

~~~properties
hibernate.show_sql=true
hibernate.format_sql=true
~~~

Trong Spring Boot, thường cấu hình logging cho các category SQL của phiên bản Hibernate tương ứng; tên category bind parameter có thể thay đổi giữa major versions. Với EclipseLink, dùng SQL logging và cấu hình session/database platform riêng của EclipseLink.

Không bật log nhạy cảm tại production chỉ để quan sát flush: SQL/bind logging có thể làm lộ dữ liệu hoặc tốn tài nguyên.

### 18.1. Một timeline minh họa

~~~text
[10:00:00.100] tx.begin()
[10:00:00.110] em.persist(Invoice)
[10:00:00.112] SQL: select nextval('invoice_id_seq')
[10:00:00.150] JPQL count(Invoice) được yêu cầu
[10:00:00.151] SQL: insert into invoices ...
[10:00:00.154] SQL: select count(*) from invoices ...
[10:00:00.180] em.flush()
[10:00:00.200] tx.commit()
~~~

Trong ví dụ này:

- **SELECT nextval** là SQL cấp ID; chưa phải INSERT Invoice.
- **INSERT** đã chạy trước commit do nhu cầu đồng bộ trước query.
- **em.flush()** sau đó có thể không phát DML nếu không có pending changes mới.
- **tx.commit()** hoàn thành transaction; trong log SQL thuần, thông điệp COMMIT có thể không hiện theo cùng cơ chế với log ORM statement, nên cần kết hợp transaction logging/JDBC observability phù hợp.

### 18.2. Gắn nhãn mốc trong code thử nghiệm

~~~java
System.out.println("A: before persist");
em.persist(invoice);

System.out.println("B: after persist, before query");
em.createQuery("select count(i) from Invoice i", Long.class)
  .getSingleResult();

System.out.println("C: after query, before flush");
em.flush();

System.out.println("D: after flush, before commit");
tx.commit();

System.out.println("E: after commit");
~~~

Ghép mốc log Java với SQL log và transaction tracing sẽ giúp phân biệt SQL phát tại persist, query, flush hay commit. Kết quả là **quan sát của một tổ hợp provider/dialect/config cụ thể**, không phải cam kết hành vi trên mọi môi trường.

## 19. Thử nghiệm có kiểm soát: SQL đã chạy nhưng chưa commit

Một bài thử có thể dùng **hai transaction độc lập** trên một PostgreSQL database ở isolation READ COMMITTED.

**Transaction T1:**

~~~java
EntityManager em1 = emf.createEntityManager();
EntityTransaction tx1 = em1.getTransaction();

tx1.begin();
Product product = new Product(
    "VISIBLE-AFTER-COMMIT",
    new BigDecimal("10.00")
);
em1.persist(product);
em1.flush();

// Chưa gọi tx1.commit() hoặc tx1.rollback().
~~~

**Transaction T2 trên EntityManager khác**, với transaction độc lập:

~~~java
EntityManager em2 = emf.createEntityManager();
EntityTransaction tx2 = em2.getTransaction();

tx2.begin();
Long visible = em2.createQuery(
    "select count(p) from Product p where p.sku = :sku",
    Long.class
).setParameter("sku", "VISIBLE-AFTER-COMMIT")
 .getSingleResult();

// Với PostgreSQL READ COMMITTED, T2 không được thấy INSERT
// chưa commit của T1; count thường là 0 nếu dữ liệu chưa tồn tại.
tx2.commit();
~~~

Sau khi T2 hoàn thành, **T1 commit**:

~~~java
tx1.commit();
~~~

Một T2 mới bắt đầu sau commit có thể thấy hàng vừa tạo theo READ COMMITTED. Nếu thay vì commit, T1 rollback, dữ liệu T1 đã flush không trở thành hàng đã commit.

**Điều kiện thử nghiệm:**

- Hai EntityManager sử dụng hai transaction thực sự độc lập, không vô tình chia cùng một transaction do framework propagate.
- DBMS/isolation level được xác định; không suy diễn hành vi PostgreSQL cho mọi DB.
- Với UNIQUE conflict hoặc lock, một số query ở T2 có thể chờ hoặc bị chặn; test cần tránh bế tắc và có timeout.
- Cleanup transaction và đóng EntityManager trong finally sau khi chạy test; không để T1 mở lâu trên môi trường chung.
- Với các DB khác, kiểm tra cách đọc dữ liệu chưa commit, MVCC và isolation cụ thể.

Bài thử này làm rõ sự khác biệt giữa **SQL INSERT đã được thực thi trong T1** và **dữ liệu đã commit mà T2 được phép thấy**.

## 20. Những câu hiểu sai thường gặp

### 20.1. “em.persist() chắc chắn chưa gửi SQL”

Sai. Với IDENTITY, provider có thể cần INSERT sớm để lấy generated key. Với các mapping/generator khác, SQL cấp ID hoặc DML cũng có thể xảy ra trước commit.

### 20.2. “em.persist() chắc chắn đã ghi DB”

Cũng sai. Nếu INSERT được trì hoãn, persist chỉ đăng ký managed entity mới và SQL có thể chờ flush/commit.

### 20.3. “em.flush() tương đương commit()”

Sai. Flush đồng bộ pending state; commit xác nhận transaction. Sau flush vẫn có thể rollback và DML chưa commit bị hoàn tác.

### 20.4. “flush xong thì transaction khác đọc được dữ liệu”

Không đúng một cách tổng quát. Visibility phụ thuộc isolation và transaction. Với READ COMMITTED thông thường, transaction khác không thấy thay đổi chưa commit.

### 20.5. “FlushModeType.AUTO flush trước mọi SELECT”

Không nhất thiết. Provider phải bảo đảm ngữ nghĩa truy vấn; nó có thể tránh flush khi pending changes không ảnh hưởng query hoặc dùng cách đồng bộ khác.

### 20.6. “FlushModeType.COMMIT cấm SQL trước commit”

Sai. COMMIT tác động chính sách flush khi query, không cấm SELECT, native SQL, INSERT để lấy IDENTITY hay explicit flush.

### 20.7. “Có ID nghĩa là insert đã commit”

Sai. ID có thể được sinh từ sequence/JVM trước INSERT hoặc lấy từ INSERT chưa commit. Rollback có thể khiến row không tồn tại dù object vẫn giữ ID.

### 20.8. “flush() trả về thành công thì commit chắc thành công”

Sai. Constraint trì hoãn, lỗi kết nối, optimistic conflict ở thao tác khác hoặc những thay đổi mới sau flush vẫn có thể khiến commit thất bại.

### 20.9. “SELECT trong transaction chỉ đọc database đã commit”

Không đơn giản. Trong cùng transaction, read-your-writes có thể áp dụng với dữ liệu SQL đã flush; JPA AUTO còn có nghĩa vụ phản ánh pending changes ảnh hưởng query. Với transaction khác, visibility do isolation quyết định.

### 20.10. “Setter của entity managed lập tức chạy UPDATE”

Thông thường setter chỉ thay object Java. Provider quyết định khi nào dirty checking và SQL synchronization xảy ra. Với bytecode enhancement, provider có thể ghi nhận dirty state sớm nhưng điều đó không đồng nghĩa tự gửi UPDATE ngay.

### 20.11. “SQL từ flush luôn chạy theo đúng thứ tự em.persist()/em.remove()”

Không bảo đảm. ORM có thể sắp xếp DML theo FK, batch, mapping và provider. Khi cần kiểm soát một chuỗi phụ thuộc vào constraint, phải thiết kế transaction và điểm đồng bộ rõ ràng.

### 20.12. “Native SQL update sẽ làm mọi managed entity thay đổi theo”

Sai. Bulk/native DML có thể bỏ qua persistence context; cần flush/refresh/clear phù hợp khi trộn với entity đang managed.

### 20.13. “@PostPersist là callback sau khi commit”

Sai. Callback có thể được gọi khi INSERT thực hiện trong flush, vẫn trước commit. Dùng afterCommit hoặc outbox nếu cần side effect sau khi dữ liệu đã được xác nhận.

### 20.14. “Rollback sẽ trả lại sequence/identity value”

Không phải quy tắc chung. Nhiều DB cố ý không rollback sequence increment. Khoảng trống trong ID không chứng minh ứng dụng làm mất bản ghi.

## 21. Hướng dẫn chọn thời điểm flush trong service

| Tình huống | Hướng tiếp cận |
|---|---|
| Chỉ tạo/sửa vài entity rồi kết thúc transaction | Để provider/commit đồng bộ khi phù hợp |
| Cần database kiểm tra lỗi constraint ngay trước một bước quan trọng | Cân nhắc flush tường minh, vẫn chuẩn bị cho lỗi ở commit |
| JPQL query cần phản ánh pending state | AUTO hoặc flush trước query khi cần chắc chắn |
| Native SQL cần đọc dữ liệu JPA vừa thay đổi | Flush tường minh trong cùng transaction trước native query |
| Dùng IDENTITY và thấy INSERT trước commit | Đây có thể là hành vi bình thường, không phải tự commit |
| Trộn bulk update với managed entity | Kiểm soát flush trước DML và refresh/clear sau DML |
| Xử lý nhiều nghìn entity | Cân nhắc flush/clear theo batch và benchmark |
| Gọi API bên ngoài sau khi lưu | Không phát event chỉ vì flush thành công; dùng afterCommit/outbox thích hợp |
| Muốn rút ngắn thời gian giữ lock | Tránh flush quá sớm nếu không cần |
| Muốn log/đo chính xác timing SQL | Quan sát SQL + transaction logs trên đúng provider |

Một quy tắc thiết kế hữu ích: **chỉ flush tường minh khi có lý do cụ thể mà chương trình cần cơ sở dữ liệu được đồng bộ tại thời điểm đó**. Nếu lý do là “muốn dữ liệu tồn tại vĩnh viễn”, API phù hợp vẫn là commit transaction.

## 22. Bài tập tự thực hành

### Bài 1: persist rồi rollback

~~~java
tx.begin();
Product p = new Product("A-01", new BigDecimal("12.00"));
em.persist(p);
em.flush();
tx.rollback();
~~~

**Câu hỏi:** Có chắc bảng products chứa hàng A-01 sau rollback không? Nếu p.getId() không null thì sao?

**Đáp án:** Không. INSERT nếu đã thực thi vẫn nằm trong transaction bị rollback. p có thể giữ ID đã được cấp, nhưng ID không chứng minh hàng đã commit. Sequence/identity có thể đã tiêu hao giá trị.

### Bài 2: AUTO và truy vấn có liên quan

Trong transaction, ứng dụng persist một Invoice mới, sau đó chạy:

~~~java
em.setFlushMode(FlushModeType.AUTO);
Long count = em.createQuery(
    "select count(i) from Invoice i " +
    "where i.referenceCode = :code",
    Long.class
).setParameter("code", "INV-001")
 .getSingleResult();
~~~

**Câu hỏi:** Vì sao provider có thể INSERT Invoice trước SELECT?

**Đáp án:** Để query phản ánh pending changes có thể ảnh hưởng kết quả theo AUTO. Nhưng đặc tả không buộc mọi provider luôn tạo cùng một lệnh INSERT trước mỗi query; chỉ cần bảo đảm ngữ nghĩa truy vấn phù hợp.

### Bài 3: COMMIT có cấm SQL không?

Một service thiết lập em.setFlushMode(COMMIT), rồi persist entity dùng IDENTITY và gọi find() trên entity khác.

**Câu hỏi:** Có thể nhìn thấy INSERT hoặc SELECT trước commit không?

**Đáp án:** Có. COMMIT không cấm truy cập DB trước commit. IDENTITY có thể cần INSERT để lấy ID, find() có thể chạy SELECT. Ảnh hưởng của pending changes lên query khi chưa flush không được đặc tả đầy đủ.

### Bài 4: Lỗi unique lúc flush

Transaction persist một Product có SKU đã tồn tại rồi gọi flush(). DB báo UNIQUE violation.

**Câu hỏi:** Có nên catch exception và tiếp tục commit?

**Đáp án:** Không nên mặc định như vậy. Transaction có thể bị rollback-only và persistence context có thể không còn trạng thái hợp lệ để tiếp tục. Thường rollback, kết thúc scope và trả lỗi nghiệp vụ hoặc xử lý lại trong transaction mới.

### Bài 5: Bulk update và managed entity

~~~java
Product p = em.find(Product.class, 10L);
em.createQuery(
    "update Product x set x.price = 100 where x.id = 10"
).executeUpdate();
System.out.println(p.getPrice());
~~~

**Câu hỏi:** p.getPrice() chắc chắn bằng 100 không?

**Đáp án:** Không. Bulk DML không tự đồng bộ object managed đang có trong persistence context. Cần refresh/clear và quản lý pending changes trước/sau bulk DML phù hợp.

### Bài 6: Hai EntityManager

T1 persist rồi flush Product mới nhưng chưa commit. T2 là transaction độc lập ở PostgreSQL READ COMMITTED và query theo SKU.

**Câu hỏi:** T2 có bắt buộc thấy Product mới không?

**Đáp án:** Không. READ COMMITTED không cho phép T2 thấy dữ liệu chưa commit của T1. Nếu T1 commit và T2 chạy một statement mới sau đó, T2 có thể đọc hàng đã commit theo quy tắc isolation.

### Bài 7: @PostPersist và phát email

Một entity listener gửi email ở @PostPersist. Transaction sau đó rollback do lỗi ở entity khác.

**Câu hỏi:** Email có tự bị thu hồi không?

**Đáp án:** Không. Callback có thể chạy trước commit và tác động ngoài DB không tự rollback. Nên chuyển side effect sang cơ chế afterCommit/outbox phù hợp.

### Bài 8: Đếm SQL trong batch

Ứng dụng persist 500 entity rồi gọi flush() một lần. Với IDENTITY, provider cần lấy generated key sau INSERT; với SEQUENCE và allocation phù hợp, có thể cấp ID trước rồi batch INSERT.

**Câu hỏi:** Có chắc cả hai cách phát cùng số round-trip hoặc cùng thời điểm INSERT không?

**Đáp án:** Không. ID generation và khả năng batching phụ thuộc provider, dialect, JDBC driver và cấu hình. Cần log SQL và đo tải trên môi trường thực.

### Bài 9: DELETE rồi INSERT cùng mã

Trong transaction, ứng dụng remove sản phẩm có SKU "OLD" rồi persist sản phẩm mới cũng dùng "OLD". Provider flush và DB báo UNIQUE violation.

**Câu hỏi:** Vì sao code Java gọi remove trước mà DB vẫn báo trùng?

**Đáp án:** Provider có thể sắp xếp INSERT trước DELETE khi đồng bộ. Khi cần bảo đảm không đụng UNIQUE, phải thiết kế trình tự DML/flush hoặc thay đổi mô hình theo ngữ nghĩa nghiệp vụ. Không giả định SQL có cùng thứ tự với lời gọi Java.

### Bài 10: Constraint trì hoãn

Database hỗ trợ một foreign key deferrable được đặt chế độ kiểm tra khi commit. Ứng dụng insert dữ liệu không thỏa FK rồi gọi flush() thành công.

**Câu hỏi:** Có thể kết luận dữ liệu hợp lệ chưa?

**Đáp án:** Chưa. Constraint có thể được kiểm tra khi commit. Flush thành công chỉ chứng minh những kiểm tra đã đến thời điểm thực hiện không thất bại; commit vẫn có thể ném lỗi.

## 23. Bảng ghi nhớ

| Sự kiện | SQL trước commit có thể xảy ra? | Điểm quan trọng |
|---|---|---|
| persist() | Có, tùy mapping/generator | Đặc biệt IDENTITY |
| Sửa entity managed | Có, tại điểm đồng bộ | Setter không tự đồng nghĩa UPDATE ngay |
| remove() | Có, khi đồng bộ DELETE | Cần FK/constraint phù hợp |
| em.flush() | Có, nếu có thay đổi cần ghi | Không commit |
| JPQL trong AUTO | Có thể flush trước query | Đảm bảo ngữ nghĩa kết quả liên quan |
| JPQL trong COMMIT | Query vẫn chạy, pending-state visibility không được đặc tả đầy đủ | Không phải SQL ban |
| Native SQL query | SQL query chạy khi gọi thực thi | Auto flush trước nó phụ thuộc API/provider |
| Bulk JPQL UPDATE/DELETE | Có | Bỏ qua đồng bộ thông thường của entity managed |
| SEQUENCE generator | Có thể chạy SQL cấp ID | Không chứng minh INSERT hay commit |
| IDENTITY generator | Có thể INSERT sớm để lấy ID | Không chứng minh commit |
| em.refresh() | Có thể SELECT DB | Không commit |
| @PostPersist/@PostUpdate | Callback có thể xảy ra trước commit | Không phải afterCommit |
| Transaction commit | Có thể flush phần pending cuối cùng rồi commit | Bảo đảm ranh giới xác nhận transaction |
| Transaction rollback sau flush | DML giao dịch bị hoàn tác | ID/side effects ngoài DB có thể không quay lại |

## 24. Kết luận

**JPA provider có thể thực thi SQL trước commit mỗi khi cần đồng bộ persistence context, thực hiện query hoặc đáp ứng yêu cầu của mapping và chiến lược sinh khóa.** Những điểm dễ gặp nhất là **em.flush()**, **query trong FlushModeType.AUTO**, **INSERT sớm cho IDENTITY**, **native/bulk SQL**, và **flush được thực hiện khi transaction chuẩn bị commit**.

Hãy tách bạch:

- **persist/sửa object:** thao tác trên trạng thái Java và persistence context;
- **flush:** đồng bộ trạng thái xuống database bằng SQL khi cần;
- **SQL execution:** database đã xử lý câu lệnh trong transaction;
- **commit:** xác nhận transaction để thay đổi trở thành dữ liệu đã commit;
- **rollback:** hoàn tác DML chưa commit, không bảo đảm khôi phục ID đã cấp hay tác động ngoài DB.

Muốn biết SQL thật sự chạy ở thời điểm nào, hãy quan sát **SQL log và transaction log trên đúng provider, dialect và DBMS**. Muốn biết dữ liệu đã được xác nhận bền vững hay chưa, hãy dựa vào **kết quả commit**, không dựa vào việc đã gọi flush, có ID, hoặc thấy INSERT xuất hiện trong log.
