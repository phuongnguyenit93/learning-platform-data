# Ranh giới trách nhiệm giữa JPA và cơ sở dữ liệu

Trong ứng dụng Java sử dụng ORM, lập trình viên thao tác với đối tượng, nhưng dữ liệu cuối cùng thường nằm trong các bảng của cơ sở dữ liệu quan hệ. **JPA (Jakarta Persistence) chuẩn hóa cách ứng dụng ánh xạ, truy vấn và quản lý các đối tượng được lưu trữ; cơ sở dữ liệu chịu trách nhiệm lưu dữ liệu, thực thi SQL, áp dụng các ràng buộc và bảo đảm các thuộc tính giao dịch mà hệ quản trị hỗ trợ.** Phân biệt đúng hai phạm vi này là nền tảng để thiết kế hệ thống có tính nhất quán, dễ bảo trì và hiệu năng tốt.

Ví dụ, gọi \`entityManager.persist(customer)\` không có nghĩa bản ghi đã được ghi bền vững. Tại thời điểm đó, đối tượng có thể mới được đưa vào *persistence context*. Nhà cung cấp JPA sẽ quyết định thời điểm phát SQL phù hợp với chuẩn và cấu hình; cơ sở dữ liệu tiếp nhận SQL, kiểm tra ràng buộc, xử lý transaction và chỉ xác nhận commit khi giao dịch hoàn thành.

## 1. Nhìn toàn cảnh: ranh giới giữa các tầng

Trước khi phân chia trách nhiệm, cần phân biệt **đặc tả JPA** với **nhà cung cấp triển khai JPA** (*persistence provider*):

- **JPA / Jakarta Persistence** là đặc tả và bộ API, annotation chuẩn, chẳng hạn \`@Entity\`, \`@Id\`, \`EntityManager\`, JPQL và \`@Version\`.
- **Persistence provider** như Hibernate ORM hoặc EclipseLink thực thi hợp đồng JPA: theo dõi entity, quản lý persistence context, tạo câu SQL, đọc kết quả và ánh xạ thành đối tượng.
- **JDBC và driver** cung cấp kênh giao tiếp SQL với cơ sở dữ liệu trong nhiều mô hình triển khai JPA.
- **Hệ quản trị cơ sở dữ liệu (DBMS)** như PostgreSQL, MySQL hoặc Oracle thực thi câu SQL, lưu dữ liệu, quản lý khóa, transaction, ràng buộc và tối ưu truy vấn.
- **Ứng dụng Java** quyết định quy tắc nghiệp vụ, đơn vị công việc, thời điểm gọi API, chính sách xử lý lỗi và cách sử dụng kết quả.

~~~text
      ỨNG DỤNG JAVA
  Nghiệp vụ, use case, transaction boundary
                  |
                  v
      JPA: HỢP ĐỒNG CHUẨN
      @Entity, EntityManager, JPQL
                  |
                  v
    PERSISTENCE PROVIDER
    Mapping, trạng thái managed,
    dirty checking, SQL generation
                  |
                  v
         JDBC / DRIVER
                  |
                  v
           DATABASE
    SQL execution, data pages, index,
    constraint, isolation, commit
~~~

Đây là sơ đồ **luồng trách nhiệm**, không phải khẳng định bản thân đặc tả JPA là một tiến trình chạy riêng. Ứng dụng gọi API được chuẩn hóa; provider hiện thực API đó và trao đổi với database.

Một quyết định thiết kế thường liên quan đồng thời nhiều lớp. Chẳng hạn, \`@Version\` mô tả chiến lược khóa lạc quan ở tầng JPA; provider sử dụng giá trị version trong câu UPDATE có điều kiện; database thực thi câu UPDATE nguyên tử; ứng dụng chọn trả lỗi xung đột hay thử lại.

## 2. Bảng phân định trách nhiệm

| Vấn đề | JPA và provider chịu trách nhiệm | Cơ sở dữ liệu chịu trách nhiệm |
| --- | --- | --- |
| Ánh xạ dữ liệu | Mô tả entity, thuộc tính, quan hệ, kiểu dữ liệu và chuyển đổi giá trị | Chứa bảng, cột, khóa, kiểu dữ liệu vật lý |
| Định danh | Gắn giá trị \`@Id\` với danh tính entity trong persistence context; phối hợp sinh khóa | Bảo đảm khóa chính/unique theo schema; có thể sinh identity hoặc sequence |
| Truy vấn | Cung cấp JPQL/Criteria, tạo SQL, truyền tham số, ánh xạ kết quả | Phân tích, tối ưu, thực thi SQL, sử dụng index và trả dữ liệu |
| Theo dõi thay đổi | Quản lý trạng thái managed, dirty checking, phát INSERT/UPDATE/DELETE khi cần | Thực hiện thao tác ghi thực tế lên dữ liệu |
| Tính hợp lệ dữ liệu | Metadata ánh xạ và có thể phối hợp với Bean Validation hoặc kiểm tra nghiệp vụ | Thực thi NOT NULL, UNIQUE, FOREIGN KEY, CHECK, loại dữ liệu theo schema |
| Transaction | Cung cấp API/tích hợp transaction, xác định lúc flush và gọi commit/rollback qua hạ tầng | Bảo đảm nguyên tử, cô lập, độ bền và cơ chế khóa theo khả năng DBMS |
| Truy cập đồng thời | Cung cấp \`@Version\`, lock mode và API yêu cầu khóa | Thực thi điều kiện SQL, row lock, mức isolation, phát hiện deadlock/xung đột |
| Cache | Persistence context là cache cấp một theo phạm vi quản lý; cache cấp hai là tùy chọn provider | Buffer cache, page cache và khả năng tối ưu truy cập dữ liệu của DBMS |
| Schema | Có metadata và khả năng sinh DDL nếu cấu hình | Sở hữu schema thực tế và thực thi DDL, constraint, index |
| Phục hồi và sao lưu | Không phải nhiệm vụ của JPA | Cơ chế backup, recovery, WAL/redo log, replication tùy DBMS |
| Tính nhất quán giữa dịch vụ | Ứng dụng tổ chức workflow và transaction trong phạm vi hỗ trợ | Một transaction database quản lý tài nguyên thuộc phạm vi của nó; giao dịch phân tán cần thêm hạ tầng |

**Quy tắc thiết kế:** tính năng nào được JPA mô tả không nhất thiết đã tồn tại ở cơ sở dữ liệu. Annotation là một phần của mô hình ánh xạ; **schema đang vận hành** mới quyết định các ràng buộc vật lý thực tế.

## 3. Từ phương thức Java đến bản ghi: một lệnh ghi đi qua những gì?

Giả sử có đối tượng \`Customer\` đã được ánh xạ tới bảng \`customers\`. Một thao tác thêm khách hàng có thể diễn ra theo trình tự:

~~~text
Ứng dụng                JPA provider                    Database
    |                         |                             |
    | begin transaction       |                             |
    |------------------------>|-------- BEGIN (logic) ------>|
    | persist(customer)       |                             |
    |------------------------>| đánh dấu managed            |
    |                         | lên lịch INSERT              |
    |                         |                             |
    | flush / trước commit    |                             |
    |------------------------>| INSERT INTO customers ...  |
    |                         |---------------------------->|
    |                         |                     kiểm tra constraint
    |                         |<---------- kết quả ---------|
    | commit                  |                             |
    |------------------------>|----------- COMMIT --------->|
    |                         |<--------- kết quả ----------|
    |<----- thành công/lỗi ---|                             |
~~~

Đây là diễn tiến điển hình, **không phải lịch phát SQL cố định**. Tùy chiến lược sinh khóa, flush mode, nhà cung cấp JPA và hoàn cảnh, INSERT có thể được gửi xuống DB ngay trong \`persist\`, trong \`flush\`, khi thực hiện truy vấn hoặc trước \`commit\`.

Ba thời điểm phải phân biệt:

1. **\`persist(entity)\`:** chuyển một entity mới sang trạng thái được quản lý; provider sẽ sắp xếp công việc ghi cần thiết. Chưa thể suy ra transaction đã commit.
2. **\`flush()\`:** yêu cầu provider đồng bộ các thay đổi đang chờ của persistence context với database. SQL có thể được thực thi, lỗi constraint có thể phát sinh, nhưng transaction vẫn chưa chắc hoàn tất.
3. **\`commit()\`:** yêu cầu kết thúc transaction với kết quả thành công. Database xác nhận kết quả commit; nếu phát sinh lỗi, giao dịch không được xem là thành công. Một số ràng buộc trì hoãn chỉ được kiểm tra ở cuối transaction.

Ví dụ:

~~~java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();
    em.persist(customer);
    em.flush();  // Có thể phát SQL và ném lỗi ngay tại đây.
    tx.commit(); // Mới là bước kết thúc transaction.
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

Ví dụ sử dụng **EntityManager với RESOURCE_LOCAL transaction**. Trong Jakarta EE hay Spring, transaction thường do container/transaction manager điều phối nên mã ứng dụng có thể không gọi \`EntityTransaction\` trực tiếp.

Một điểm đặc biệt quan trọng: **flush thành công không đồng nghĩa commit thành công**. SQL đã chạy vẫn có thể bị rollback; xung đột hoặc lỗi kết nối cũng có thể xuất hiện ở giai đoạn commit.

## 4. Persistence context không phải cơ sở dữ liệu

Persistence context là tập các thực thể đang được quản lý trong một đơn vị công việc. Provider duy trì danh tính entity trong context và theo dõi thay đổi, ví dụ:

~~~java
Customer a = em.find(Customer.class, 10L);
Customer b = em.find(Customer.class, 10L);

System.out.println(a == b); // Cùng instance managed trong cùng context.
a.setDisplayName("Nguyen An");
// Nếu transaction phù hợp đang hoạt động, provider có thể phát UPDATE khi flush.
~~~

Điều này giúp lập trình theo đối tượng, nhưng cần hiểu giới hạn:

- **Context lưu trạng thái Java**, không phải bản sao đầy đủ hay trạng thái cập nhật liên tục của toàn bộ database.
- Khi một entity đang managed, \`find\` theo cùng khóa có thể trả về instance trong context mà không cần đọc lại bảng.
- Một transaction, ứng dụng khác hoặc stored procedure có thể thay đổi dữ liệu ngoài context hiện tại. Provider không nhất thiết tự biết thay đổi đó.
- \`refresh(entity)\` có thể được dùng để yêu cầu tải lại trạng thái từ database trong những tình huống thích hợp, nhưng cần hiểu ảnh hưởng đến các thay đổi chưa flush.
- Entity bị \`detach\`, \`clear\` hoặc đóng context sẽ không còn được tự động theo dõi thay đổi.

Không nên sử dụng persistence context như nguồn chân lý toàn hệ thống. **Database mới là nơi lưu dữ liệu được chia sẻ qua nhiều phiên làm việc và nhiều instance ứng dụng**, chịu chi phối bởi transaction và isolation.

### Trường hợp dễ nhầm: truy vấn lại nhưng vẫn thấy dữ liệu cũ

Giả sử:

1. Transaction A đọc \`Customer(id=10)\` vào persistence context.
2. Transaction B cập nhật bản ghi đó và commit.
3. Transaction A gọi \`find(Customer.class, 10L)\` lần nữa.

Transaction A có thể nhận lại instance managed có giá trị cũ. Kết quả phụ thuộc cả cache ở tầng JPA lẫn isolation của database. \`EntityManager.find\` **không phải lệnh bắt buộc đọc dữ liệu mới nhất từ database**.

Do đó cần thiết kế phạm vi persistence context phù hợp, dùng locking/version khi cập nhật đồng thời, và tránh dựa vào một lần \`find\` như bằng chứng rằng dữ liệu chưa thay đổi.

## 5. Ràng buộc dữ liệu: ai là người chốt cuối cùng?

Hãy xét yêu cầu: **email của khách hàng không được trùng**, và mỗi khách hàng phải có email.

### 5.1. JPA mô tả ánh xạ

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 320)
    private String email;

    @Column(name = "display_name", nullable = false, length = 150)
    private String displayName;

    @Version
    private long version;

    protected Customer() {
        // Dành cho JPA.
    }

    public Customer(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

\`@Column(nullable = false, unique = true)\` cung cấp metadata cho ánh xạ và có thể được provider dùng khi **sinh schema**. Không nên suy luận rằng chỉ cần annotation này là bảng đang chạy chắc chắn có ràng buộc \`NOT NULL\` và \`UNIQUE\`. Đặc biệt nếu schema được tạo từ migration hoặc có trước, cần khai báo và kiểm tra các ràng buộc tại database.

### 5.2. Database thực thi ràng buộc

Ví dụ DDL cho **PostgreSQL**:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    display_name VARCHAR(150) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
~~~

Trên bảng này, DBMS kiểm tra \`NOT NULL\`, \`UNIQUE\` và \`PRIMARY KEY\` bất kể SQL đến từ JPA, JDBC, công cụ quản trị hay một ứng dụng khác.

Nếu hai request đồng thời kiểm tra "email này có tồn tại không?", cả hai đều có thể thấy **chưa tồn tại** rồi cùng cố INSERT. Kiểm tra trước tại tầng ứng dụng giúp phản hồi thân thiện nhưng **không loại bỏ race condition**. Ràng buộc \`UNIQUE\` ở database sẽ từ chối một thao tác xung đột theo ngữ nghĩa transaction và cơ chế xử lý của DBMS.

~~~text
Request A: SELECT email='a@example.com' -> chưa có
Request B: SELECT email='a@example.com' -> chưa có
Request A: INSERT email='a@example.com' -> có thể thành công
Request B: INSERT email='a@example.com' -> bị chặn/từ chối do UNIQUE
~~~

Ứng dụng cần **bắt lỗi phù hợp, rollback transaction và chuyển thành kết quả nghiệp vụ có ý nghĩa** (chẳng hạn "Email đã được sử dụng"). Tên và cấp exception cụ thể phụ thuộc provider, transaction manager và driver; không nên ràng buộc toàn bộ thiết kế vào chuỗi thông báo lỗi từ một DBMS.

### 5.3. Validation và constraint có mục tiêu khác nhau

| Cơ chế | Mục đích | Giới hạn |
| --- | --- | --- |
| Kiểm tra nghiệp vụ trong ứng dụng | Thông báo sớm, quy tắc phụ thuộc ngữ cảnh | Dễ bị race condition; không bao phủ mọi client |
| Bean Validation, ví dụ \`@NotNull\`, \`@Email\` | Kiểm tra dữ liệu đầu vào/đối tượng khi được tích hợp | Không thay thế ràng buộc vật lý và transaction |
| Metadata JPA \`@Column\` / \`@Table\` | Mô tả ánh xạ, hỗ trợ sinh schema | Không chứng minh schema đang chạy có constraint |
| Constraint tại database | Chốt tính hợp lệ cho tất cả lệnh ghi đi qua database | Không diễn đạt đầy đủ mọi quy tắc nghiệp vụ hoặc UX |

**Khuyến nghị:** kiểm tra điều kiện để cung cấp trải nghiệm tốt ở tầng ứng dụng, và đặt các bất biến dữ liệu mang tính hệ thống tại cơ sở dữ liệu khi có thể biểu đạt bằng constraint.

## 6. Transaction: JPA điều phối thao tác, database thực thi tính nguyên tử

Transaction là nơi ranh giới trách nhiệm dễ bị hiểu sai nhất.

**Ở phía JPA**, ứng dụng hoặc container thiết lập phạm vi transaction. Provider kết nối thao tác trên các entity với transaction đó, quyết định flush và chuyển lệnh ghi thành SQL.

**Ở phía database**, DBMS thực thi transaction với các thuộc tính ACID trong phạm vi cam kết của hệ quản trị và cấu hình:

- **Atomicity:** các thay đổi thuộc transaction hoặc được commit hoặc bị rollback.
- **Consistency:** dữ liệu chuyển từ một trạng thái hợp lệ sang trạng thái hợp lệ theo các ràng buộc được DBMS thực thi; quy tắc nghiệp vụ ngoài schema vẫn do ứng dụng đảm nhiệm.
- **Isolation:** các transaction đồng thời nhìn thấy và ảnh hưởng lẫn nhau theo mức isolation cùng cơ chế khóa/MVCC của DBMS.
- **Durability:** dữ liệu đã commit được bảo vệ theo cơ chế độ bền mà DBMS và hạ tầng lưu trữ bảo đảm.

JPA **không tự tạo ra ACID bằng cách giữ entity trong bộ nhớ**. Những tính chất này dựa trên database và transaction infrastructure.

### 6.1. Ranh giới transaction cần bám theo một đơn vị công việc

Ví dụ use case đặt hàng gồm:

1. Tạo đơn hàng.
2. Tạo các dòng hàng.
3. Cập nhật số lượng tồn kho trong cùng database.

Nếu các bước cần thành công hoặc thất bại cùng nhau, ứng dụng thường đặt chúng trong **một transaction database phù hợp**. Các hàm \`persist\` riêng lẻ không mặc nhiên tạo một commit chung nếu chương trình đã tách chúng vào các transaction khác nhau.

Ngược lại, **gửi email, gọi HTTP API hoặc ghi sang database độc lập** không tự động tham gia transaction chỉ vì các lệnh đó nằm trong cùng phương thức Java có sử dụng JPA. Các hệ thống cần tính nhất quán xuyên ranh giới thường phải dùng cơ chế phù hợp như outbox pattern, thông điệp đáng tin cậy, saga hoặc hạ tầng transaction phân tán khi thực sự cần.

### 6.2. Isolation không phải thuộc tính của persistence context

Ví dụ hai transaction cùng đọc số lượng hàng còn lại là 1 rồi đều đặt mua 1 sản phẩm. Chỉ dùng \`find\` và sửa thuộc tính Java không tự giải quyết tranh chấp. Cần kết hợp chiến lược cập nhật, locking hoặc SQL có điều kiện với mức isolation được chọn và quy tắc nghiệp vụ.

Mức isolation thực tế, hiện tượng *non-repeatable read*, *phantom*, *deadlock* và cách DB xử lý tranh chấp phụ thuộc hệ quản trị cùng cấu hình. JPA cung cấp API để yêu cầu những cơ chế nhất định; **DBMS là nơi thực thi chúng**.

## 7. Đồng thời: \`@Version\` và kiểm tra tại database

JPA cung cấp **optimistic locking** để phát hiện khi nhiều transaction cố cập nhật cùng entity. Ví dụ entity \`Customer\` ở trên có:

~~~java
@Version
private long version;
~~~

Giả sử cả transaction A và B đọc khách hàng có \`version = 7\`:

~~~text
A đọc: id=10, version=7
B đọc: id=10, version=7
A cập nhật -> điều kiện version=7 khớp -> version lên 8
B cập nhật -> điều kiện version=7 không còn khớp -> xung đột
~~~

Provider có thể phát câu SQL mang ý nghĩa tương tự:

~~~sql
UPDATE customers
SET display_name = ?, version = 8
WHERE id = 10 AND version = 7;
~~~

Đây là **minh họa cơ chế**, không bảo đảm SQL thực tế của mọi provider có đúng cú pháp hoặc cách gán version như trên. DB thực thi phép cập nhật có điều kiện. Khi không có hàng phù hợp, provider phát hiện xung đột và báo lỗi khóa lạc quan, thường thông qua \`OptimisticLockException\` hoặc lớp exception do framework bọc lại.

Phân vai tại đây:

- JPA quy định ý nghĩa của \`@Version\` và ngữ nghĩa optimistic locking.
- Provider tạo lệnh cập nhật/kiểm tra version phù hợp.
- Database bảo đảm câu lệnh điều kiện chạy theo cơ chế đồng thời của nó.
- Ứng dụng quyết định hiển thị xung đột, yêu cầu người dùng tải lại hay thử transaction mới theo một chính sách có kiểm soát.

**Lưu ý:** nếu một công cụ khác cập nhật trực tiếp bảng nhưng không tuân thủ quy tắc tăng version, optimistic locking của JPA có thể không nhận ra cập nhật đó. Việc chia sẻ bảng giữa nhiều hệ thống đòi hỏi quy ước cập nhật thống nhất.

### Pessimistic locking là gì?

Khi cần khóa dữ liệu ngay lúc đọc hoặc trước khi cập nhật, JPA có các chế độ như \`LockModeType.PESSIMISTIC_WRITE\`:

~~~java
Customer customer = em.find(
        Customer.class,
        10L,
        jakarta.persistence.LockModeType.PESSIMISTIC_WRITE);
~~~

Provider yêu cầu khóa theo khả năng DBMS. Thời gian chờ khóa, phạm vi khóa, nguy cơ deadlock và cách xử lý lỗi là các đặc điểm chịu ảnh hưởng mạnh bởi database và transaction. Khóa bi quan cần transaction thích hợp và thường làm giảm mức độ đồng thời nếu dùng quá rộng.

## 8. Quan hệ trong Java và khóa ngoại trong database

Giả sử mỗi \`OrderItem\` tham chiếu một \`Order\`:

~~~java
// Trong entity OrderItem, giả sử Order đã là một entity hợp lệ.
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "order_id", nullable = false)
private Order order;
~~~

Đây là **mô tả quan hệ trong mô hình JPA**. Provider dùng nó để ánh xạ đối tượng, thiết lập join, lưu giá trị khóa ngoại và quyết định khi tải quan hệ. Trong schema, ta vẫn mong đợi ràng buộc tương ứng:

~~~sql
ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_order
FOREIGN KEY (order_id) REFERENCES orders(id);
~~~

Ràng buộc FOREIGN KEY của database bảo vệ tính tham chiếu ngay cả khi dữ liệu được ghi ngoài JPA. Không nên dựa chỉ vào \`@ManyToOne(optional = false)\` hoặc \`@JoinColumn(nullable = false)\` để khẳng định cơ sở dữ liệu đã có khóa ngoại và \`NOT NULL\`.

### Hai loại cascade có thể bị nhầm

| Cơ chế | Ai thực hiện? | Ý nghĩa |
| --- | --- | --- |
| \`cascade = CascadeType.REMOVE\` | JPA provider | Khi xóa entity cha qua JPA, thao tác remove có thể lan sang các entity liên quan theo mapping |
| \`ON DELETE CASCADE\` | Database | Khi một hàng cha bị xóa, DBMS tự động xóa các hàng con theo constraint |

Hai cơ chế này có tác dụng liên quan nhưng **không hoán đổi tuyệt đối**. Chúng có thể khác về vòng đời entity, callback, SQL được phát và trạng thái của entity đang nằm trong persistence context. Nếu sử dụng cả hai, phải hiểu sự tương tác và kiểm tra behavior theo provider/DBMS đang chạy.

## 9. JPA tạo truy vấn; database quyết định kế hoạch thực thi

JPQL tập trung vào mô hình entity:

~~~java
List<Customer> customers = em.createQuery(
        "SELECT c FROM Customer c "
        + "WHERE c.email LIKE :pattern ORDER BY c.id",
        Customer.class)
    .setParameter("pattern", "%@example.com")
    .getResultList();
~~~

Provider phân tích JPQL và phát SQL tương ứng. Nhưng **độ nhanh của truy vấn không được JPA bảo đảm**. Database quyết định dùng index hay quét bảng, cách join, sắp xếp và xử lý bộ nhớ dựa trên thống kê dữ liệu, cấu trúc index, SQL thực tế và các điều kiện khác.

Khi truy vấn chậm, cần quan sát cả hai phía:

1. **JPA/provider:** JPQL, chiến lược fetch, SQL đã phát, số lượng truy vấn, batch size, cache, pagination.
2. **Database:** execution plan (\`EXPLAIN\`/công cụ tương đương), index, thống kê, lượng dữ liệu, khóa và tài nguyên.

### Vấn đề N+1: phần giao nhau của hai trách nhiệm

Giả sử ứng dụng lấy danh sách 100 đơn hàng, sau đó vòng lặp truy cập \`order.getCustomer().getName()\`. Nếu quan hệ customer chưa được tải và provider dùng lazy load riêng cho từng tham chiếu, có thể xảy ra **1 truy vấn lấy đơn hàng + nhiều truy vấn lấy customer**.

~~~java
List<Order> orders = em.createQuery(
        "SELECT o FROM Order o JOIN FETCH o.customer",
        Order.class).getResultList();
~~~

Ví dụ dùng \`JOIN FETCH\` để yêu cầu tải quan hệ customer cùng lúc với order, trong mô hình mà \`Order\` có quan hệ \`customer\`. Nó chỉ là **một lựa chọn**: với quan hệ collection, phân trang hay tập dữ liệu lớn cần cân nhắc cách truy vấn khác. Provider quyết định SQL được tạo; DBMS quyết định kế hoạch và chi phí của SQL đó.

Vì vậy, không thể đánh giá hiệu năng JPA chỉ dựa vào số dòng Java ít đi. **Mã ORM ngắn có thể tạo nhiều lệnh SQL**, và một câu JPQL đơn giản có thể trở nên đắt nếu thiếu index hoặc chứa join bất hợp lý.

## 10. Schema generation khác với schema migration

JPA có khả năng mô tả schema từ entity và hỗ trợ cấu hình sinh bảng/cột trong một số tình huống. Nhà cung cấp JPA cũng thường có công cụ cập nhật schema riêng. Tuy vậy, hai công việc cần phân biệt:

- **Schema generation:** tạo một schema từ mô hình ánh xạ, hữu ích cho demo, thử nghiệm hoặc môi trường kiểm soát chặt.
- **Schema migration:** quản lý các thay đổi từ phiên bản schema đang vận hành sang phiên bản mới, có lịch sử, cơ chế kiểm soát triển khai và khả năng xử lý dữ liệu đang tồn tại.

Ví dụ thay \`Customer.email\` từ \`VARCHAR(100)\` sang \`VARCHAR(320)\` có thể kéo theo kiểm tra dữ liệu hiện có, thời gian khóa bảng và tương thích với các phiên bản ứng dụng đang chạy. JPA không tự quyết định chiến lược triển khai an toàn cho thay đổi này.

Trong hệ thống thực tế, thường dùng Flyway, Liquibase hoặc quy trình migration do đội vận hành quản lý. Provider ánh xạ entity với schema đã được tạo; khi entity và schema không khớp, có thể phát sinh lỗi truy vấn, chuyển đổi kiểu hoặc ràng buộc. **Thay annotation không tự bảo đảm database được nâng cấp tương ứng.**

## 11. Những ranh giới khác dễ bỏ sót

### 11.1. Kiểu dữ liệu và tính di động

JPA cung cấp hệ thống ánh xạ các kiểu Java thường gặp, có thể kết hợp \`AttributeConverter\` để chuyển đổi giá trị. Tuy nhiên, kiểu cột vật lý, giới hạn precision/scale, múi giờ, collation, quy tắc so sánh chuỗi và chức năng JSON/array tùy database.

Ví dụ, \`BigDecimal\` trong Java nên được ánh xạ sang cột số có precision/scale phù hợp cho tiền tệ. Chỉ dùng \`BigDecimal\` không bảo đảm cơ sở dữ liệu sẽ lưu mọi giá trị mà không cắt hoặc làm tròn nếu schema không khớp.

### 11.2. Cache tầng JPA và cache database

Persistence context cung cấp quản lý danh tính và cache cấp một; cache cấp hai của provider là tính năng cấu hình tùy chọn. Database có bộ nhớ đệm cho trang dữ liệu và kế hoạch truy vấn. Các loại cache có phạm vi và chính sách làm mới khác nhau.

Nếu dữ liệu thường xuyên bị chỉnh sửa ngoài JPA, cache cấp hai có thể cần cơ chế invalidation hoặc chiến lược sử dụng riêng. **Độ mới của dữ liệu không thể suy ra chỉ từ việc JPA đã gọi SELECT hay chưa.**

### 11.3. Trigger, default và generated column

Database có thể tự sửa cột nhờ trigger hoặc sinh giá trị mặc định. Sau khi INSERT/UPDATE, entity managed có thể chưa phản ánh ngay những thay đổi do database tạo ra nếu provider không được cấu hình để đọc lại. Trong trường hợp cần trạng thái mới nhất, phải chọn cơ chế đồng bộ hoặc gọi \`refresh\` theo ngữ cảnh.

### 11.4. Vòng đời tài nguyên

Provider thường quản lý các JDBC statement và ánh xạ ResultSet, nhưng kết nối thật có thể được lấy từ connection pool do framework/container quản lý. EntityManager không nên được chia sẻ tùy ý giữa các thread. Transaction, connection và persistence context có thể có vòng đời khác nhau, dù framework thường gắn chúng lại trong phạm vi một request hoặc đơn vị công việc.

### 11.5. Quyền truy cập và bảo mật

JPA cho phép truy vấn bằng API và truyền tham số an toàn khi dùng đúng cách; nó không thay thế cơ chế quyền truy cập tại database, chính sách phân quyền nghiệp vụ của ứng dụng, bảo vệ thông tin nhạy cảm hoặc cấu hình kết nối. DBMS vẫn thực thi quyền của tài khoản kết nối.

## 12. Phân vai theo một tình huống đặt hàng

Giả sử hệ thống có yêu cầu: khi người dùng đặt 3 sản phẩm, phải tạo đơn hàng, bảo đảm số tồn kho không âm và tránh việc hai đơn đồng thời lấy cùng một đơn vị tồn kho.

| Quyết định hoặc hành động | Trách nhiệm chính |
| --- | --- |
| Kiểm tra người dùng được phép đặt hàng, xác định giá/khuyến mại | Ứng dụng, tầng nghiệp vụ |
| Ánh xạ \`Order\`, \`OrderItem\`, \`Inventory\` sang bảng | JPA metadata và provider |
| Gom thao tác thành một đơn vị transaction | Ứng dụng/transaction manager |
| Sinh câu SQL chèn đơn hàng và cập nhật tồn kho | Persistence provider hoặc SQL do ứng dụng cung cấp |
| Bảo vệ khóa ngoại giữa order và order_items | Database FOREIGN KEY |
| Bảo vệ \`quantity >= 0\` cho mọi đường ghi | Database CHECK constraint (nếu mô hình phù hợp) |
| Tránh cập nhật đồng thời làm mất dữ liệu | Kết hợp chiến lược ứng dụng, JPA locking/SQL có điều kiện và cơ chế transaction database |
| Quyết định khóa, isolation, thứ tự thực thi SQL | Database theo câu lệnh và cấu hình nhận được |
| Khi DB báo constraint/lock conflict | Ứng dụng xử lý rollback, phản hồi và thử lại khi an toàn |
| Gửi thông báo sang hệ thống khác sau khi đặt hàng | Ứng dụng và hạ tầng tích hợp, không phải tự động nhờ JPA |

Ví dụ, constraint ở DB có thể là:

~~~sql
ALTER TABLE inventory
ADD CONSTRAINT ck_inventory_nonnegative
CHECK (quantity >= 0);
~~~

Ràng buộc này giúp chặn dữ liệu âm ở mọi đường ghi, nhưng không thay thế chính sách nghiệp vụ "hết hàng thì báo gì" và không tự quyết định cách tránh giữ khóa quá lâu. Khi cần kiểm soát cạnh tranh chặt chẽ, một câu UPDATE có điều kiện hoặc cơ chế khóa phù hợp có thể được cân nhắc:

~~~sql
UPDATE inventory
SET quantity = quantity - 3
WHERE product_id = 42 AND quantity >= 3;
~~~

Ứng dụng phải kiểm tra số hàng bị cập nhật và đặt thao tác trong transaction phù hợp. Đây là ví dụ SQL nhằm minh họa trách nhiệm của database; có thể thực hiện qua native query, JDBC hoặc cách khác tùy kiến trúc. Việc dùng SQL chuyên biệt này **không mâu thuẫn** với việc dùng JPA để quản lý phần còn lại của mô hình.

## 13. Những ngộ nhận phổ biến

| Ngộ nhận | Cách hiểu chính xác |
| --- | --- |
| “\`persist\` chạy xong nghĩa là dữ liệu đã bền vững.” | Entity có thể mới đang managed; cần transaction thành công và database commit |
| “Gọi \`flush\` cũng như \`commit\`.” | Flush đồng bộ SQL đang chờ; commit kết thúc transaction |
| “Có \`@Column(unique=true)\` thì dữ liệu chắc chắn không bao giờ trùng.” | Cần xác nhận database thực tế có unique constraint phù hợp |
| “JPA tự xử lý mọi vấn đề đồng thời.” | Cần chọn transaction/locking; DBMS là nơi thực thi và ứng dụng phải xử lý xung đột |
| “Cứ dùng LAZY thì sẽ nhanh hơn.” | LAZY có thể gây N+1, lỗi truy cập ngoài context hoặc tải dữ liệu thiếu chủ đích |
| “JPQL tốt thì database luôn chạy nhanh.” | Cần SQL phù hợp, index, thống kê và execution plan |
| “Đổi entity nghĩa là schema tự đổi theo.” | Migration và schema thật cần được quản lý riêng |
| “Cache của EntityManager chính là dữ liệu mới nhất.” | Context có thể chứa trạng thái đã đọc trước đó và không tự nhận biết cập nhật ngoài context |
| “Dùng JPA thì không cần SQL hay kiến thức database.” | Hiểu SQL, ràng buộc, isolation và index vẫn thiết yếu |

## 14. Câu hỏi thực hành

**Câu 1.** Một ứng dụng có \`@Column(nullable=false)\` nhưng bảng thực tế cho phép NULL. Người dùng chạy SQL trực tiếp và chèn NULL thành công. Vấn đề nằm ở đâu?

**Gợi ý:** annotation là metadata của JPA, còn database chỉ thực thi constraint tồn tại trong schema. Cần migration thêm \`NOT NULL\` sau khi xử lý dữ liệu không hợp lệ.

**Câu 2.** Trong một transaction, \`em.flush()\` thành công. Ngay sau đó ứng dụng rollback. Có thể kỳ vọng bản ghi mới vẫn tồn tại không?

**Gợi ý:** không. Flush khác commit; thay đổi chưa commit bị rollback trong transaction database.

**Câu 3.** Hai transaction cùng sửa entity có \`@Version\`. Ai tạo cơ chế phát hiện xung đột?

**Gợi ý:** JPA quy định ngữ nghĩa; provider dựng thao tác có kiểm tra version; database thực thi phép cập nhật; ứng dụng quyết định xử lý xung đột.

**Câu 4.** Một API chậm vì khi hiển thị 100 đơn hàng, provider chạy hơn 100 câu SELECT. Nên điều tra lớp nào?

**Gợi ý:** phía JPA xem fetch strategy và số câu SQL, phía database xem thời gian và kế hoạch thực thi. Có thể chọn \`JOIN FETCH\`, entity graph, projection hoặc truy vấn theo lô phù hợp.

**Câu 5.** Cần đảm bảo \`email\` duy nhất kể cả khi có tác vụ nhập liệu chạy bằng JDBC ngoài ứng dụng JPA. Nên đặt quy tắc ở đâu?

**Gợi ý:** database phải có UNIQUE constraint; ứng dụng và JPA có thể kiểm tra trước để phản hồi tốt hơn nhưng không thay thế constraint.

## Kết luận

**JPA là hợp đồng chuẩn để thao tác với dữ liệu quan hệ ở mức đối tượng; provider hiện thực hợp đồng đó; database là hệ thống thực thi SQL và lưu dữ liệu.** Trách nhiệm của chúng liên kết chặt chẽ nhưng có ranh giới rõ: JPA quản lý ánh xạ, entity và cách yêu cầu thao tác; DBMS thực thi constraint, transaction, locking, index, truy vấn và lưu trữ thực tế; ứng dụng quyết định nghiệp vụ, phạm vi transaction và cách phản ứng với lỗi.

Khi thiết kế hay gỡ lỗi ORM, hãy tự hỏi ba điều: **JPA/provider đang quản lý trạng thái và sinh SQL thế nào? Database thực sự nhận và bảo đảm điều gì? Ứng dụng cần quyết định chính sách nào?** Trả lời được ba câu hỏi này giúp tránh nhầm lẫn giữa object state và dữ liệu đã commit, giữa annotation và constraint, cũng như giữa truy vấn Java gọn gàng và hiệu năng SQL thực tế.
