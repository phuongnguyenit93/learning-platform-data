# Vai trò của `Persistence`, `EntityManagerFactory` và `EntityManager` trong kiến trúc JPA

## 1. Ba thành phần nằm ở đâu trong JPA?

**Jakarta Persistence (JPA)** là đặc tả cho việc ánh xạ đối tượng Java sang dữ liệu quan hệ và quản lý vòng đời của các đối tượng được ánh xạ (entity). Khi lập trình với JPA, ta không trực tiếp viết mã JDBC cho mọi thao tác thêm, đọc, sửa, xóa: ứng dụng thao tác trên entity, còn **JPA provider** (chẳng hạn Hibernate ORM hoặc EclipseLink) thực hiện phần lớn công việc ánh xạ và tương tác với cơ sở dữ liệu.

Ba API thường gặp có nhiệm vụ khác nhau:

- **`Persistence`**: điểm khởi tạo JPA theo cách thủ công, chủ yếu trong ứng dụng Java SE. Nó tìm provider thích hợp và tạo `EntityManagerFactory` từ cấu hình của một *persistence unit*.
- **`EntityManagerFactory`**: nhà máy tạo các `EntityManager`, gắn với cấu hình của một persistence unit. Đây là thành phần tương đối nặng, thường được tạo một lần và dùng lại trong thời gian ứng dụng hoạt động.
- **`EntityManager`**: giao diện mà mã nghiệp vụ sử dụng để làm việc với entity: `persist`, `find`, `merge`, `remove`, truy vấn và `flush`. Mỗi `EntityManager` gắn với một **persistence context** — vùng quản lý các entity đang ở trạng thái *managed*.

Luồng điển hình khi ứng dụng tự khởi tạo JPA:

```text
Ứng dụng Java SE
    |
    | Persistence.createEntityManagerFactory("catalogPU")
    v
EntityManagerFactory  (một factory dùng chung cho persistence unit)
    |
    | createEntityManager()
    v
EntityManager         (một phiên làm việc / đơn vị công việc)
    |
    +-- Persistence Context (quản lý các entity và thay đổi)
    |
    v
JPA Provider  -->  JDBC / DataSource  -->  Cơ sở dữ liệu quan hệ
```

**Phân biệt:** JPA là đặc tả API và hành vi; `Persistence`, `EntityManagerFactory`, `EntityManager` nằm trong API `jakarta.persistence`; Hibernate/EclipseLink là các *provider* triển khai đặc tả đó. Tài liệu JPA cũ có thể dùng tên gói `javax.persistence`, còn các phiên bản Jakarta Persistence hiện đại dùng `jakarta.persistence`.

## 2. `Persistence`: điểm khởi tạo từ cấu hình

`jakarta.persistence.Persistence` là lớp tiện ích cung cấp phương thức tĩnh:

```java
EntityManagerFactory emf =
        Persistence.createEntityManagerFactory("catalogPU");
```

Tham số `"catalogPU"` là **tên persistence unit** đã khai báo trong `META-INF/persistence.xml`. Một persistence unit mô tả tập hợp entity cùng các thiết lập dùng để quản lý chúng, chẳng hạn provider, cách quản lý transaction, nguồn kết nối và các thuộc tính JDBC.

Ví dụ cấu hình đơn giản cho ứng dụng Java SE, dùng cơ sở dữ liệu H2 để thực hành:

```xml
<!-- src/main/resources/META-INF/persistence.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.0">
    <persistence-unit name="catalogPU" transaction-type="RESOURCE_LOCAL">
        <class>com.example.Product</class>
        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:catalog;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>
            <property name="jakarta.persistence.schema-generation.database.action"
                      value="drop-and-create"/>
        </properties>
    </persistence-unit>
</persistence>
```

Trong ví dụ này:

1. `catalogPU` là tên mà ứng dụng truyền vào `createEntityManagerFactory`.
2. `RESOURCE_LOCAL` cho phép ứng dụng tự điều khiển transaction bằng `EntityTransaction`.
3. `com.example.Product` là lớp entity thuộc persistence unit.
4. Các thuộc tính JDBC trỏ đến một H2 database trong bộ nhớ. Để chạy ví dụ, project cần thư viện Jakarta Persistence API, **một provider JPA** và **JDBC driver H2** tương thích.
5. Giá trị `drop-and-create` tạo lại schema, đồng thời xóa dữ liệu cũ nếu có; chỉ thích hợp cho ví dụ hoặc môi trường thử nghiệm, không dùng tùy tiện trên database thực tế.

`Persistence` **không lưu entity, không tạo transaction và không thực thi truy vấn**. Nó chỉ tham gia giai đoạn bootstrap để có `EntityManagerFactory`. Trong ứng dụng Jakarta EE hoặc Spring, framework/container thường cấu hình và cung cấp factory hoặc entity manager; mã nghiệp vụ không cần tự gọi `Persistence.createEntityManagerFactory()`.

## 3. `EntityManagerFactory`: nhà máy dùng chung

Một `EntityManagerFactory` (EMF) đại diện cho cấu hình JPA đã được khởi tạo của một persistence unit. Provider có thể phải phân tích metadata ánh xạ, chuẩn bị hạ tầng truy cập dữ liệu và khởi tạo các tài nguyên liên quan khi tạo factory. Vì vậy, tạo factory liên tục cho từng truy vấn hoặc từng request là tốn kém.

```java
EntityManagerFactory emf =
        Persistence.createEntityManagerFactory("catalogPU");

EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();

// em1 và em2 có persistence context riêng.
em1.close();
em2.close();
emf.close(); // Khi ứng dụng không còn cần factory.
```

Các đặc điểm quan trọng:

| Khía cạnh | `EntityManagerFactory` |
|---|---|
| Trách nhiệm chính | Tạo `EntityManager`; cung cấp metadata và dịch vụ ở cấp persistence unit. |
| Chi phí tạo | Tương đối lớn, nên khởi tạo ít lần và tái sử dụng. |
| Phạm vi sử dụng | Thường một factory cho một persistence unit trong suốt vòng đời ứng dụng. |
| An toàn luồng | Theo thiết kế có thể được chia sẻ giữa nhiều luồng. |
| Kết thúc | `close()` khi đóng ứng dụng hoặc khi factory không còn được sử dụng. |

**Một factory không đồng nghĩa với một phiên làm việc duy nhất.** Factory được chia sẻ, nhưng những `EntityManager` sinh ra từ đó có thể phục vụ các transaction, request hoặc tác vụ khác nhau. Đóng một `EntityManager` không đóng factory. Ngược lại, sau khi `EntityManagerFactory` bị đóng, ứng dụng không thể tiếp tục dùng nó để tạo entity manager mới.

Trong ứng dụng do container quản lý, vòng đời factory thường do container/framework chịu trách nhiệm; lập trình viên không tự đóng tài nguyên đã được container quản lý.

## 4. `EntityManager`: thao tác dữ liệu và persistence context

`EntityManager` (EM) là đối tượng làm việc trực tiếp với các entity. Một số thao tác điển hình:

| API | Ý nghĩa |
|---|---|
| `persist(entity)` | Đưa một entity mới vào trạng thái managed để được chèn vào database khi đồng bộ phù hợp. |
| `find(EntityClass.class, id)` | Tìm entity theo khóa chính; trả `null` nếu không tìm thấy. |
| `createQuery(...)` | Tạo truy vấn JPQL hoặc truy vấn kiểu khác được API hỗ trợ. |
| `merge(detached)` | Sao chép trạng thái của entity detached sang một entity managed và trả về đối tượng managed đó. |
| `remove(managed)` | Đánh dấu một entity managed để xóa khi đồng bộ. |
| `flush()` | Đồng bộ các thay đổi đang chờ trong persistence context xuống database, trong phạm vi transaction hiện tại. |
| `clear()` / `detach(entity)` | Ngừng quản lý toàn bộ / một entity trong persistence context. |
| `close()` | Kết thúc entity manager do ứng dụng tự tạo và giải phóng tài nguyên liên quan. |

### 4.1. Persistence context giữ danh tính và theo dõi thay đổi

**Persistence context** là tập hợp các entity đang được một `EntityManager` quản lý. Trong cùng context, với cùng kiểu entity và khóa chính, JPA duy trì một thể hiện Java được quản lý. Vì thế, hai lần tìm cùng bản ghi thường trả về chính **cùng một object**:

```java
Product first = em.find(Product.class, 10L);
Product second = em.find(Product.class, 10L);
System.out.println(first == second); // true nếu entity tồn tại và cùng context
```

Đây là cơ chế nhận diện entity và bộ nhớ đệm cấp một (*first-level cache*) gắn với persistence context, **không phải** cache chung cho mọi `EntityManager`. Khi entity đang managed thay đổi, provider theo dõi sự thay đổi đó (*dirty checking*) và có thể phát sinh câu lệnh `UPDATE` lúc flush/commit mà không cần gọi một phương thức `update()` riêng:

```java
Product product = em.find(Product.class, 10L);
product.changeName("Bút gel xanh"); // Nếu product đang managed.
// Với transaction phù hợp, thay đổi sẽ được đồng bộ khi flush/commit.
```

### 4.2. Các trạng thái entity cần biết

```text
new/transient -- persist() --> managed -- remove() --> removed
      ^                        |
      |                        | detach(), clear() hoặc đóng context
      |                        v
      +                    detached
                             |
                             | merge() trả về một bản managed
                             v
                          managed
```

- **New/transient**: object vừa tạo bằng `new`, chưa được persistence context quản lý.
- **Managed**: entity thuộc một persistence context đang hoạt động; các thay đổi hợp lệ có thể được đồng bộ xuống database.
- **Detached**: từng được quản lý nhưng không còn gắn với context đó; sửa object detached tự nó **không** tự động cập nhật database.
- **Removed**: entity managed được đánh dấu để xóa; thao tác xóa được đồng bộ theo quy tắc của transaction.

Lưu ý với `merge`: giá trị trả về mới là entity managed. Object đầu vào detached **không trở thành managed chỉ nhờ việc gọi `merge`**:

```java
Product managedCopy = em.merge(detachedProduct);
// Tiếp tục thay đổi managedCopy nếu muốn JPA theo dõi các chỉnh sửa kế tiếp.
```

### 4.3. `flush()` và `commit()` khác nhau

`flush()` yêu cầu provider đồng bộ các thao tác đang chờ của persistence context thành SQL trong transaction hiện tại. `commit()` xác nhận transaction; với chế độ phù hợp, commit cũng làm cho các thay đổi đang chờ được flush. **Flush không có nghĩa là dữ liệu đã commit**: transaction vẫn có thể rollback. Thời điểm provider gửi SQL còn chịu ảnh hưởng của chiến lược sinh khóa, flush mode và nhu cầu truy vấn, nên không nên giả định mọi lệnh SQL chỉ xuất hiện đúng tại commit.

## 5. Ví dụ hoàn chỉnh trong Java SE

Giả sử có entity `Product` dùng bảng `products`:

```java
package com.example;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Product() { } // JPA yêu cầu constructor không tham số.

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void changeName(String name) {
        this.name = name;
    }
}
```

Với file `persistence.xml` ở phần 2 và các dependency tương ứng, ứng dụng có thể tạo factory, mở entity manager, chạy transaction rồi đóng tài nguyên:

```java
package com.example;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

public class JpaDemo {
    public static void main(String[] args) {
        // 1. Khởi tạo một lần từ persistence unit "catalogPU".
        EntityManagerFactory emf =
                Persistence.createEntityManagerFactory("catalogPU");

        try {
            // 2. Mỗi đơn vị công việc sử dụng EntityManager riêng.
            EntityManager em = emf.createEntityManager();
            try {
                EntityTransaction tx = em.getTransaction();
                try {
                    tx.begin();

                    // 3. Entity ban đầu ở trạng thái new.
                    Product product = new Product("Bút bi");
                    em.persist(product); // Chuyển sang managed.

                    // 4. Đồng bộ để bảo đảm khóa sinh ra đã có thể sử dụng.
                    em.flush();
                    Long id = product.getId();

                    // Cùng persistence context: cùng object managed.
                    Product sameProduct = em.find(Product.class, id);
                    System.out.println(product == sameProduct); // true

                    // Dirty checking: không cần câu lệnh UPDATE thủ công.
                    sameProduct.changeName("Bút gel");

                    // 5. Xác nhận transaction (và flush thay đổi còn chờ).
                    tx.commit();
                } catch (RuntimeException ex) {
                    if (tx.isActive()) {
                        tx.rollback();
                    }
                    throw ex;
                }
            } finally {
                // 6. Giải phóng context của đơn vị công việc.
                em.close();
            }
        } finally {
            // 7. Đóng factory khi kết thúc ứng dụng.
            emf.close();
        }
    }
}
```

Đọc ví dụ theo ba vai trò: `Persistence` khởi tạo `emf`; `emf` tạo `em`; `em` quản lý `Product` và làm việc bên trong transaction. Sau `em.close()`, các object từng managed trong context này không còn được quản lý bởi context đó. Khi cần xử lý một yêu cầu khác, ứng dụng có thể tạo `EntityManager` mới từ **cùng `EntityManagerFactory`**.

Ví dụ dùng `RESOURCE_LOCAL`, nên mã chủ động gọi `tx.begin()`, `tx.commit()` và `tx.rollback()`. Trong môi trường transaction do container quản lý (`JTA`), cách viết này không còn phù hợp; transaction thường được container/framework điều phối.

## 6. Trong Jakarta EE hoặc Spring, ai tạo và đóng các thành phần?

Ở ứng dụng Java SE thuần, ta thường trực tiếp gọi `Persistence.createEntityManagerFactory()`, `emf.createEntityManager()` và `close()` như trên. Với ứng dụng sử dụng dependency injection, việc khởi tạo và quản lý các đối tượng này thường do container/framework đảm nhiệm.

Ví dụ dịch vụ trong Jakarta EE dùng entity manager được container cấp:

```java
import jakarta.ejb.Stateless;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@Stateless
public class ProductService {
    @PersistenceContext(unitName = "catalogPU")
    private EntityManager em;

    public Product findById(Long id) {
        return em.find(Product.class, id);
    }

    public void rename(Long id, String newName) {
        Product product = em.find(Product.class, id);
        if (product != null) {
            product.changeName(newName);
        }
    }
}
```

Ở ví dụ này, một transaction mặc định của EJB session bean có thể bao quanh lời gọi phương thức nghiệp vụ; entity manager được container quản lý nên ứng dụng không gọi `em.close()` hay `em.getTransaction()` trong các phương thức đó. Persistence unit tương ứng cần được cấu hình phù hợp với cơ chế JTA/container thay vì dùng nguyên cấu hình `RESOURCE_LOCAL` phía trên. Với Spring, thường gặp cách tiêm `EntityManager` bằng `@PersistenceContext` cùng việc quản lý transaction bằng `@Transactional` của Spring.

Điểm cần giữ nguyên dù dùng framework nào: factory là tài nguyên có phạm vi rộng và dùng chung; entity manager và persistence context phục vụ công việc có phạm vi hẹp, theo transaction hoặc phạm vi mà container quy định.

## 7. Vòng đời, luồng và transaction: các lỗi dễ gặp

| Tình huống | Vấn đề và cách hiểu đúng |
|---|---|
| Tạo `EntityManagerFactory` cho mỗi request | Chi phí khởi tạo lớn và có thể làm cạn tài nguyên; dùng lại factory trong phạm vi ứng dụng. |
| Lưu một `EntityManager` dùng chung cho nhiều luồng | `EntityManager` không được bảo đảm thread-safe; mỗi tác vụ cần phạm vi quản lý riêng hoặc entity manager do framework cung cấp đúng cách. |
| Gọi `persist()` nhưng không commit một transaction ghi | Trong chế độ `RESOURCE_LOCAL`, không thể xem thay đổi là đã được lưu bền vững nếu transaction chưa commit thành công. |
| Gọi `flush()` rồi cho rằng transaction đã hoàn tất | Flush đồng bộ SQL trong transaction nhưng không thay thế commit; rollback vẫn có thể hủy thay đổi. |
| Đổi thuộc tính entity đã detached rồi mong database tự cập nhật | Dirty checking chỉ theo dõi entity managed; cần xử lý trong context thích hợp, có thể dùng `merge()` và làm việc với object nó trả về. |
| Gọi `remove()` trực tiếp với object detached | `remove()` yêu cầu entity managed; tìm lại entity hoặc đưa trạng thái vào context phù hợp trước khi xóa. |
| Đóng `EntityManager` quá sớm khi còn cần dữ liệu lazy | Quan hệ hoặc thuộc tính chưa tải có thể không truy cập được sau khi context đóng; thiết kế phạm vi transaction và cách fetch theo nhu cầu. |
| Tự đóng `EntityManager` được container inject | Vòng đời entity manager đó thuộc container; việc đóng và quản lý transaction phải theo cơ chế của container. |
| Nhầm tên persistence unit khi bootstrap | `createEntityManagerFactory("...")` phải khớp `name` trong cấu hình; đồng thời classpath phải có provider và các dependency cần thiết. |

## 8. Đặt các thành phần cạnh nhau

| Câu hỏi | `Persistence` | `EntityManagerFactory` | `EntityManager` |
|---|---|---|---|
| Được dùng để làm gì? | Khởi động JPA từ tên persistence unit. | Tạo các entity manager. | Thao tác với entity và persistence context. |
| Khi nào cần? | Chủ yếu lúc bootstrap Java SE. | Khi ứng dụng cần tạo entity manager. | Trong từng đơn vị công việc/truy cập dữ liệu. |
| Thời gian sống? | Gọi phương thức tiện ích lúc khởi tạo. | Thường kéo dài đến khi ứng dụng dừng. | Tương đối ngắn; do ứng dụng hoặc container quản lý. |
| Có chia sẻ giữa các luồng? | Lời gọi phương thức tĩnh lúc bootstrap. | Có thể chia sẻ. | Không chia sẻ một instance tùy tiện giữa các luồng. |
| Ai phụ trách đóng? | Không có tài nguyên instance cần đóng. | Ứng dụng nếu tự tạo; container nếu được quản lý. | Ứng dụng nếu tự tạo; container nếu được quản lý. |

**Mối quan hệ cốt lõi:** `Persistence` giúp khởi tạo một `EntityManagerFactory`; factory cung cấp những `EntityManager`; mỗi entity manager quản lý một persistence context để làm việc với entity. Nhờ phân chia này, JPA vừa tái sử dụng được hạ tầng truy cập dữ liệu ở cấp ứng dụng, vừa giữ các thay đổi của từng đơn vị công việc trong phạm vi quản lý riêng.
