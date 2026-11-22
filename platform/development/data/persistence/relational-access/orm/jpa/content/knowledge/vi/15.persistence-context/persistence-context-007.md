# Tách một entity bằng detach và tách toàn bộ bằng clear

Trong JPA, việc một đối tượng Java được gán `@Entity` không có nghĩa rằng mọi thay đổi đối với đối tượng đó luôn được lưu xuống cơ sở dữ liệu. JPA chỉ tự theo dõi những entity đang được quản lý bởi một **persistence context** cụ thể. Khi entity chuyển sang trạng thái **detached**, nó vẫn là đối tượng Java mang dữ liệu và định danh cũ, nhưng persistence context đó **không còn tự phát hiện và ghi nhận thay đổi của nó**.

Hai thao tác tiêu chuẩn để chủ động ngừng quản lý là:

- **`EntityManager.detach(entity)`:** tách một entity cụ thể khỏi persistence context hiện tại. Có thể ảnh hưởng tới các entity liên quan nếu quan hệ được cấu hình cascade `DETACH` hoặc `ALL`.
- **`EntityManager.clear()`:** xóa toàn bộ nội dung của persistence context hiện tại, khiến **tất cả entity đang managed trong context này trở thành detached**.

Bài học thuộc chương **Persistence Context** tập trung vào ranh giới quản lý này: khi nào nên dùng `detach` hoặc `clear`, điều gì xảy ra với dirty checking và transaction, cách tránh mất thay đổi chưa được flush, và cách làm việc lại với entity bằng `find` hoặc `merge`.

## 1. Persistence context quản lý điều gì?

Một **persistence context** là tập các entity instance được JPA quản lý trong một đơn vị làm việc. Với cùng một entity type và primary key, persistence context duy trì tính nhất quán định danh trong phạm vi của nó. Nó thường được xem như **first-level cache** gắn với `EntityManager`.

Ví dụ:

```java
Product first = em.find(Product.class, 10L);
Product second = em.find(Product.class, 10L);

System.out.println(first == second); // true khi cùng context, cùng identity
```

Ở đây, hai lần `find` cho cùng một identity trong **cùng persistence context** thường trả lại **chính cùng một managed instance**. Tuy nhiên, không nên suy diễn rằng hai lần truy vấn ở hai `EntityManager` khác nhau sẽ trả cùng một object reference.

Với entity managed, các thay đổi thường được đồng bộ bằng cơ chế **dirty checking**:

```java
Product product = em.find(Product.class, 10L);
product.rename("Tên mới");

// Không bắt buộc gọi em.persist(product) hoặc em.merge(product)
// nếu product vẫn managed và transaction phù hợp.
```

Ở thời điểm flush, JPA provider so sánh/tracking trạng thái để phát hiện thay đổi rồi tạo SQL tương ứng. Cách provider tổ chức snapshot hoặc bytecode enhancement là chi tiết triển khai; điều cần ghi nhớ là **dirty checking gắn với entity managed**.

### Bốn trạng thái thường gặp của entity

| Trạng thái | Mô tả | Tự được JPA theo dõi thay đổi? |
|---|---|---|
| **New / transient** | Object vừa tạo, chưa được đưa vào persistence context | Không |
| **Managed / persistent** | Object đang thuộc persistence context | Có |
| **Detached** | Object từng được quản lý hoặc được tách ra, nhưng không còn thuộc context hiện tại | Không |
| **Removed** | Entity managed đã được đánh dấu xóa; thao tác xóa sẽ được đồng bộ theo quy tắc transaction | Không dùng để cập nhật như entity thông thường |

Một entity có `id != null` không tự động chứng minh nó đang managed; nó có thể là **detached**, hoặc là đối tượng mới được ứng dụng cấp ID trước khi lưu. Kiểm tra trạng thái với `em.contains(entity)` trên **EntityManager cụ thể** thay vì chỉ xét giá trị `id`.

```mermaid
flowchart TD
    N["new Product(...)"] -->|persist| M["Managed trong persistence context"]
    M -->|detach(entity)| D["Detached: một entity"]
    M -->|clear()| A["Detached: mọi managed entity trong context"]
    M -->|close()| C["Context đóng; entity không còn managed ở context đó"]
    D -->|merge(entity)| X["Trả về một instance managed"]
    A -->|merge(entity)| X
    M -->|remove(entity)| R["Removed: chờ đồng bộ DELETE"]
```

Lưu ý: sơ đồ minh họa các chuyển trạng thái thường gặp, không mô tả mọi điều kiện ngoại lệ và toàn bộ quy tắc cascade. `merge` **không làm chính object đối số trở thành managed**; nó trả về một instance managed khác hoặc instance đã managed tương ứng.

## 2. detach(entity): tách đúng một entity

Phương thức tiêu chuẩn:

```java
em.detach(product);
```

Nếu `product` đang managed trong persistence context của `em`, lời gọi yêu cầu provider **ngừng quản lý instance đó**.

Có thể quan sát bằng `contains`:

```java
Product product = em.find(Product.class, productId);

System.out.println(em.contains(product)); // true
em.detach(product);
System.out.println(em.contains(product)); // false
```

Sau `detach`:

- `product` vẫn là object Java bình thường; `getId()` và các field đã tải vẫn có thể được sử dụng.
- `product` vẫn giữ primary key; `detach` **không xóa hàng trong database**.
- JPA không tiếp tục dirty-check thay đổi trên `product` trong persistence context đó.
- Những entity khác đang managed trong cùng context **vẫn được quản lý**, trừ khi có cascade detach hoặc tác động liên quan.
- Lần tải lại cùng identity có thể trả về **một instance managed mới**, khác reference với `product` đã detach.

### Ví dụ phân biệt hai reference

```java
Product original = em.find(Product.class, productId);

em.detach(original);

Product reloaded = em.find(Product.class, productId);

System.out.println(original == reloaded);       // false
System.out.println(em.contains(original));       // false
System.out.println(em.contains(reloaded));       // true
System.out.println(
    original.getId().equals(reloaded.getId()));  // true
```

Hai object có cùng khóa DB nhưng khác trạng thái quản lý. Kết quả identity reference trong ví dụ giả định `original` là entity managed trước khi detach và không có cơ chế đặc biệt trả lại cùng instance đã bị tách; đây chính là cách JPA diễn đạt ranh giới persistence context.

**Không nhầm equality của ID với việc một object còn managed.** Dù `equals` của entity có trả về true theo ID, `em.contains(original)` vẫn false sau khi detach.

## 3. clear(): tách toàn bộ managed entity trong context

`EntityManager.clear()` không nhận đối số:

```java
em.clear();
```

Nó làm **trống persistence context**. Mọi managed entity của context đó chuyển sang detached, kể cả object không liên quan trực tiếp đến nghiệp vụ hiện tại.

```java
Product first = em.find(Product.class, firstId);
Product second = em.find(Product.class, secondId);

System.out.println(em.contains(first));  // true
System.out.println(em.contains(second)); // true

em.clear();

System.out.println(em.contains(first));  // false
System.out.println(em.contains(second)); // false
```

Khi ứng dụng dùng một `EntityManager` lâu và cần giải phóng số lượng lớn entity đã tải, `clear` là công cụ để cắt toàn bộ quan hệ quản lý với các entity đó. Nhưng nó là một **thao tác rộng**: các biến Java còn trỏ tới những object cũ sẽ không còn là managed.

### Cần phân biệt clear với close

- `clear()`: context được làm trống, nhưng **EntityManager vẫn mở và còn dùng được**, trừ các giới hạn trạng thái khác.
- `close()`: kết thúc vòng đời EntityManager application-managed; không tiếp tục dùng manager đã đóng.
- `clear()` không tự đóng connection pool, không hủy `EntityManagerFactory` và không đồng nghĩa commit/rollback transaction.
- `clear()` không phải lệnh làm sạch **second-level cache** ở cấp `EntityManagerFactory`. First-level cache gắn với persistence context và cache cấp 2 là hai khái niệm khác nhau.

Ví dụ:

```java
em.clear();

Product managedAgain = em.find(Product.class, productId);
// EntityManager vẫn hoạt động; managedAgain thuộc context
// hiện tại sau khi nó đã được làm trống.
```

## 4. Bảng so sánh detach, clear và các thao tác liên quan

| Thao tác | Phạm vi | Entity còn được quản lý? | Ảnh hưởng thường gặp tới DB |
|---|---|---|---|
| `em.detach(p)` | Một entity `p`, cộng các entity liên quan được cascade DETACH | `p` không còn managed | Không phải lệnh DELETE; thay đổi chưa flush trên p có thể không được lưu |
| `em.clear()` | Toàn bộ persistence context | Không còn managed entity cũ | Bỏ các thay đổi chưa flush đang chờ đồng bộ của context |
| `em.flush()` | Đồng bộ các thay đổi đang chờ của persistence context | Vẫn managed | Phát SQL trong transaction; **chưa commit** |
| `em.refresh(p)` | Đọc lại trạng thái của entity managed từ DB, theo quy tắc refresh | `p` vẫn managed | Có thể ghi đè thay đổi chưa flush trên p bằng dữ liệu từ DB |
| `em.remove(p)` | Đánh dấu xóa entity managed và cascade phù hợp | Chuyển sang trạng thái removed | Yêu cầu DELETE khi đồng bộ transaction |
| `em.close()` | Đóng EntityManager application-managed | Các instance không còn được quản lý bởi EM đã đóng | Giải phóng tài nguyên context; không thay thế commit |
| `emf.getCache().evict(...)` | Cache cấp 2 theo API `Cache` nếu provider hỗ trợ | Không làm detached entity đang managed ở cấp 1 | Không trực tiếp thay đổi DB |
| `em.merge(detached)` | Hợp nhất trạng thái vào managed instance | **Object trả về** managed; object đối số vẫn detached | Thay đổi có thể được ghi khi flush/commit |

**Điểm khác biệt mấu chốt:** `detach` và `clear` đều cắt dirty checking, nhưng một thao tác nhắm vào entity cụ thể, còn thao tác kia nhắm tới toàn bộ context.

## 5. Nguy cơ lớn nhất: thay đổi chưa flush có thể bị mất

Đây là tình huống cần nhớ trước khi dùng `detach` hoặc `clear`.

Giả sử transaction đang hoạt động:

```java
Product product = em.find(Product.class, id);
product.rename("Tên đang sửa");

// Thay đổi mới nằm trong managed entity.
em.detach(product);

em.getTransaction().commit();
```

Không nên kỳ vọng tên mới được lưu. Khi entity đã detached trước khi provider đồng bộ thay đổi, **thay đổi chưa flush trên entity đó có thể bị bỏ qua**. Mức độ SQL đã được gửi trước đó còn tùy thao tác và chế độ flush, nên không dùng detach như một cơ chế rollback riêng lẻ.

Tương tự:

```java
Product one = em.find(Product.class, firstId);
Product two = em.find(Product.class, secondId);

one.rename("A mới");
two.rename("B mới");

em.clear();  // Hai managed instance đều bị tách.
em.getTransaction().commit();
```

Nếu chưa flush, những thay đổi đang chờ của cả `one` và `two` **có thể không được ghi**. Quy tắc thao tác an toàn là **đồng bộ trước khi tách** nếu thực sự muốn giữ thay đổi.

### Quy trình: flush rồi detach

```java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = em.find(Product.class, id);
    product.rename("Tên sẽ được lưu");

    em.flush();          // Đồng bộ SQL trong transaction.
    em.detach(product);  // Từ đây không còn dirty checking.

    tx.commit();         // Commit transaction.
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

`flush()` đảm bảo provider gửi các thay đổi đang chờ xuống DB theo ngữ nghĩa JPA, **không đảm bảo transaction cuối cùng sẽ commit thành công**. Nếu xảy ra lỗi sau flush và transaction rollback, các thay đổi đó bị rollback cùng transaction.

### Quy trình: flush rồi clear

```java
tx.begin();

try {
    Product a = em.find(Product.class, firstId);
    Product b = em.find(Product.class, secondId);

    a.rename("A mới");
    b.rename("B mới");

    em.flush(); // Đồng bộ cả hai thay đổi.
    em.clear(); // Tách tất cả entity; còn có thể dùng em.

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Với mô hình dùng EntityManager application-managed và transaction `RESOURCE_LOCAL`, gọi flush khi transaction đang hoạt động là cách rõ ràng nhất. Trong môi trường dùng transaction manager/JTA, hãy tuân thủ ranh giới transaction do môi trường cung cấp.

**Không coi flush là phép lưu chỉ một entity.** `em.flush()` có thể đồng bộ **nhiều managed entity** và association thay đổi trong persistence context, không chỉ object bạn sắp detach.

## 6. Ví dụ Java SE hoàn chỉnh: EntityManager, detach và clear

Ta dùng một entity `Product` với giá, tên và khóa `Long` để quan sát từng trạng thái.

### 6.1. Cấu trúc ví dụ

```text
detach-clear-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── Product.java
    │   └── Main.java
    └── resources/
        └── META-INF/
            └── persistence.xml
```

Ví dụ minh họa Java 17, Jakarta Persistence API 3.1, Hibernate ORM 6.x và cơ sở dữ liệu H2. Các phiên bản dependency bên dưới là tập mẫu có tính đồng nhất về thế hệ API, không phải tuyên bố bản mới nhất.

```xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>detach-clear-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>jakarta.persistence</groupId>
            <artifactId>jakarta.persistence-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.hibernate.orm</groupId>
            <artifactId>hibernate-core</artifactId>
            <version>6.6.4.Final</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. Entity Product

Tệp `src/main/java/demo/Product.java`:

```java
package demo;

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

    @Column(name = "name", nullable = false, length = 200)
    private String name;

    @Column(name = "price", nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Version
    private Long version;

    protected Product() {
        // JPA constructor.
    }

    public Product(String name, BigDecimal price) {
        rename(name);
        changePrice(price);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void rename(String value) {
        Objects.requireNonNull(value, "name");
        if (value.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        this.name = value;
    }

    public void changePrice(BigDecimal value) {
        Objects.requireNonNull(value, "price");
        if (value.signum() < 0) {
            throw new IllegalArgumentException("price must not be negative");
        }
        this.price = value;
    }
}
```

`@Version` phục vụ optimistic locking khi entity được cập nhật theo đường JPA thông thường; nó **không thay đổi** định nghĩa managed/detached. Ngay cả entity có version vẫn không tự lưu các chỉnh sửa khi đã detached.

### 6.3. Persistence unit

Tệp `src/main/resources/META-INF/persistence.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="
                 https://jakarta.ee/xml/ns/persistence
                 https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
             version="3.1">
    <persistence-unit name="productsPU" transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>demo.Product</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:productsdb;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="sa"/>
            <property name="jakarta.persistence.jdbc.password"
                      value=""/>
            <property name="jakarta.persistence.schema-generation.database.action"
                      value="drop-and-create"/>
        </properties>
    </persistence-unit>
</persistence>
```

Cấu hình `drop-and-create` chỉ dùng cho demo/test vì có thể **xóa schema và dữ liệu hiện hữu**. Với database production, sử dụng migration thích hợp và không tự xóa bảng khi ứng dụng khởi động.

### 6.4. Chạy hai thao tác trong cùng EntityManager

Tệp `src/main/java/demo/Main.java`:

```java
package demo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

import java.math.BigDecimal;

public class Main {

    public static void main(String[] args) {
        EntityManagerFactory emf =
                Persistence.createEntityManagerFactory("productsPU");

        try {
            Long[] ids = seed(emf);
            demonstrateDetach(emf, ids[0], ids[1]);
            demonstrateClear(emf, ids[0], ids[1]);
        } finally {
            emf.close();
        }
    }

    private static Long[] seed(EntityManagerFactory emf) {
        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();
            try {
                tx.begin();

                Product keyboard = new Product(
                    "Keyboard", new BigDecimal("250000"));
                Product mouse = new Product(
                    "Mouse", new BigDecimal("150000"));

                em.persist(keyboard);
                em.persist(mouse);
                tx.commit();

                return new Long[]{keyboard.getId(), mouse.getId()};
            } catch (RuntimeException ex) {
                if (tx.isActive()) tx.rollback();
                throw ex;
            }
        } finally {
            em.close();
        }
    }

    private static void demonstrateDetach(
            EntityManagerFactory emf, Long firstId, Long secondId) {

        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();
            try {
                tx.begin();

                Product keyboard = em.find(Product.class, firstId);
                Product mouse = em.find(Product.class, secondId);

                System.out.println("Before detach: "
                    + em.contains(keyboard) + ", "
                    + em.contains(mouse));

                em.detach(keyboard);

                System.out.println("After detach: "
                    + em.contains(keyboard) + ", "
                    + em.contains(mouse));

                // Sửa keyboard đã detached: không còn dirty checking.
                keyboard.rename("Keyboard - detached change");

                // Sửa mouse vẫn managed: provider có thể ghi UPDATE.
                mouse.rename("Mouse - managed change");

                tx.commit();

            } catch (RuntimeException ex) {
                if (tx.isActive()) tx.rollback();
                throw ex;
            }
        } finally {
            em.close();
        }

        EntityManager verify = emf.createEntityManager();
        try {
            System.out.println("After detach commit:");
            System.out.println("  " + verify.find(Product.class, firstId)
                .getName());
            System.out.println("  " + verify.find(Product.class, secondId)
                .getName());
        } finally {
            verify.close();
        }
    }

    private static void demonstrateClear(
            EntityManagerFactory emf, Long firstId, Long secondId) {

        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();
            try {
                tx.begin();

                Product keyboard = em.find(Product.class, firstId);
                Product mouse = em.find(Product.class, secondId);

                // Cố ý không thay đổi trước clear để làm rõ ranh giới.
                em.clear();

                System.out.println("After clear: "
                    + em.contains(keyboard) + ", "
                    + em.contains(mouse));

                // Những thay đổi sau clear không tự được lưu.
                keyboard.rename("Ignored keyboard change");
                mouse.rename("Ignored mouse change");

                Product loadedAgain =
                        em.find(Product.class, firstId);

                System.out.println("Loaded new managed reference: "
                        + (loadedAgain != keyboard));
                System.out.println("Loaded is managed: "
                        + em.contains(loadedAgain));

                tx.commit();
            } catch (RuntimeException ex) {
                if (tx.isActive()) tx.rollback();
                throw ex;
            }
        } finally {
            em.close();
        }
    }
}
```

Chạy:

```bash
mvn compile exec:java
```

Kết quả minh họa (bỏ qua log của provider):

```text
Before detach: true, true
After detach: false, true
After detach commit:
  Keyboard
  Mouse - managed change
After clear: false, false
Loaded new managed reference: true
Loaded is managed: true
```

Những dòng trên làm rõ:

1. `detach(keyboard)` chỉ làm `keyboard` ngừng managed, còn `mouse` vẫn managed.
2. Sau khi `keyboard` đã detached, đổi tên nó không tự ghi SQL `UPDATE`.
3. `mouse` vẫn managed nên thay đổi của nó có thể được ghi lúc transaction commit.
4. `clear()` làm cả hai đối tượng đã tải ngừng managed.
5. Sau clear, `em.find(...)` tạo hoặc nhận một managed instance cho identity tương ứng trong context mới làm trống; object cũ không tự trở lại managed.

**Chú ý:** Đây là ví dụ quản lý vòng đời theo trình tự rõ ràng; thời điểm phát SQL, các câu log bổ sung và thao tác cache phụ thuộc provider/dialect. Khi phân tích hiệu năng, xem SQL thật thay vì suy ra mỗi method Java đều tương ứng một query.

## 7. Chỉ thay đổi managed entity mới được dirty checking

Giả sử hai sản phẩm được tải trong cùng transaction:

```java
Product a = em.find(Product.class, firstId);
Product b = em.find(Product.class, secondId);

a.rename("A cập nhật");
b.rename("B cập nhật");

em.detach(a);

em.getTransaction().commit();
```

Nếu hai entity chưa được flush trước `detach(a)`, có thể chỉ thay đổi trên `b` được ghi. `a` đã rời persistence context, còn trạng thái trong bộ nhớ của `a` không tự đồng nghĩa trạng thái DB.

Ngược lại:

```java
Product a = em.find(Product.class, firstId);
Product b = em.find(Product.class, secondId);

a.rename("A cập nhật");
b.rename("B cập nhật");

em.flush();
em.detach(a);

b.rename("B đổi thêm");
em.getTransaction().commit();
```

- Flush đầu tiên đồng bộ các thay đổi trên cả `a` và `b` vào transaction.
- Detach `a` kết thúc việc tracking thay đổi mới của `a`.
- `b` vẫn managed, nên thay đổi tiếp theo của `b` có thể được đồng bộ ở commit.
- Nếu transaction cuối cùng rollback, ngay cả SQL đã được flush cũng không được commit.

Điểm này phân biệt **detach để ngừng tracking trong tương lai** với **rollback để hủy thay đổi của transaction**.

## 8. Tải lại sau detach hoặc clear

Một entity detached không tự được JPA theo dõi chỉ vì một entity mới có cùng ID đã được tải.

### 8.1. find sau detach

```java
Product stale = em.find(Product.class, id);

em.detach(stale);

// Bây giờ stale không còn managed.
Product managed = em.find(Product.class, id);

// managed được quản lý; stale vẫn detached.
```

Nếu sửa `stale` sau đó:

```java
stale.rename("Tên trên detached object");
```

thay đổi này không tự xuất hiện trên `managed`. Hai object có thể mang nội dung khác nhau dù cùng ID.

### 8.2. find sau clear

```java
Product oldA = em.find(Product.class, idA);
Product oldB = em.find(Product.class, idB);

em.clear();

Product newA = em.find(Product.class, idA);

// oldA và oldB đều detached.
// newA managed trong context hiện tại.
```

Nếu ứng dụng giữ các reference cũ để trả dữ liệu ra API, cần nhớ rằng chúng có thể lỗi thời. `clear` không tự tải lại dữ liệu vào object cũ.

### 8.3. refresh không phải là thay thế cho merge

`em.refresh(entity)` áp dụng cho entity managed và yêu cầu đọc lại trạng thái DB, có thể làm mất thay đổi chưa flush trên entity đó. Nếu gọi `refresh` trực tiếp với object detached, JPA có thể từ chối vì entity không còn managed.

Muốn tải dữ liệu DB mới nhất vào một instance managed, một hướng là `find` lại sau detach/clear hoặc `refresh` trên managed instance tương ứng. Muốn đưa thay đổi của object detached trở lại persistence context, dùng `merge` theo ngữ nghĩa phù hợp.

## 9. merge(): cách tiếp tục làm việc với detached entity

Sau khi detach, có thể chỉnh sửa object ngoài persistence context, rồi gắn lại **trạng thái** của nó thông qua `merge`:

```java
Product detached = em.find(Product.class, id);
em.detach(detached);

detached.rename("Tên được chỉnh sửa ngoài context");

EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product managed = em.merge(detached);

    // managed là instance cần tiếp tục sử dụng trong context.
    System.out.println(em.contains(detached)); // false
    System.out.println(em.contains(managed));  // true

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) tx.rollback();
    throw ex;
}
```

**Ngữ nghĩa quan trọng:**

- `merge(detached)` **sao chép trạng thái persistent** của đối số sang một entity managed tương ứng.
- Phương thức trả về managed instance. Đối số `detached` **vẫn là detached**.
- Provider có thể phải truy vấn DB để lấy managed target hoặc trạng thái phục vụ hợp nhất.
- Thay đổi được gửi xuống DB khi flush/commit, không phải cứ gọi `merge` là transaction đã lưu.
- `@Version` có thể giúp phát hiện xung đột do một transaction khác cập nhật entity sau khi detached object được tải; cách và thời điểm exception cụ thể phụ thuộc provider và transaction.

### Không bỏ qua đối tượng trả về

Ví dụ dễ nhầm:

```java
em.merge(detached);
detached.rename("Sửa tiếp sau merge"); // Không tự được theo dõi.
```

Cách làm phù hợp:

```java
Product managed = em.merge(detached);
managed.rename("Sửa tiếp trên managed instance");
```

### Không dùng merge để thay thế một cách mù quáng

`merge` trên toàn bộ object detached có thể ghi đè trạng thái mới hơn nếu concurrency policy không đủ. Đặc biệt khi API nhận DTO chỉ có vài field, không nên dựng một entity “thiếu thuộc tính” rồi `merge` tất cả trường như thể nó là bản snapshot đầy đủ. Cách an toàn hơn là tải entity managed trong transaction, kiểm tra quyền và version, sau đó chỉ cập nhật các field được cho phép.

`persist` thường dành cho entity mới; gọi `persist` trên một entity đã detached có thể bị provider từ chối hoặc phát sinh lỗi khi flush. Khi cần cập nhật dữ liệu của một object detached, `merge` hoặc sửa entity managed đã tải lại là những hướng JPA phù hợp hơn.

## 10. Cascade DETACH: detach một entity có thể kéo theo entity khác

Tên phương thức `detach(entity)` dễ khiến người học hiểu là **luôn chỉ có đúng một object** bị ảnh hưởng. Điều đó không hoàn toàn đúng khi quan hệ khai báo **`CascadeType.DETACH`** hoặc **`CascadeType.ALL`**.

Ví dụ:

```java
@Entity
public class Project {

    @Id
    private Long id;

    @OneToMany(mappedBy = "project", cascade = CascadeType.DETACH)
    private List<TaskItem> tasks = new ArrayList<>();

    // Các thành phần còn lại lược bớt.
}
```

`TaskItem` là một entity có quan hệ ngược:

```java
@Entity
public class TaskItem {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "project_id")
    private Project project;

    // Các thành phần còn lại lược bớt.
}
```

Khi `Project` và các `TaskItem` liên quan đang managed, một lời gọi:

```java
em.detach(project);
```

có thể cascade thao tác detach theo metadata quan hệ được cấu hình, làm các entity liên quan cũng không còn managed. Đoạn mã trên là trích đoạn để giải thích annotation, chưa phải entity hoàn chỉnh có constructor và mapping nghiệp vụ.

### Cần phân biệt cascade với detach all

- `detach(project)` kết hợp cascade `DETACH`: chỉ theo **đồ thị quan hệ và quy tắc cascade phù hợp**.
- `clear()`: tách **toàn bộ entity managed** trong context, không cần traversal theo một root cụ thể.
- Không nên giả định `detach(project)` luôn chỉ tách project, cũng không nên giả định nó tách toàn bộ database graph bất kể cascade.

Trong mô hình domain, có thể chọn **không** cascade detach, vì một object con thường có lý do để tiếp tục managed độc lập. Cần kiểm tra chính sách cascade theo vòng đời và nhu cầu thao tác, không thêm `CascadeType.ALL` cho mọi quan hệ chỉ để tiết kiệm cấu hình.

### detach không cắt liên kết Java

Nếu `project.getTasks()` đã chứa các `TaskItem`, gọi `em.detach(project)` **không tự xóa các phần tử khỏi list**, không tự đặt `task.project = null` và không xóa foreign key trên DB. Nó chỉ thay đổi trạng thái quản lý của các entity tương ứng.

Vì vậy, detach hoàn toàn khác với thao tác domain như `project.removeTask(task)` hoặc `em.remove(task)`.

## 11. Lazy loading sau khi detach hoặc clear

Một entity detached vẫn giữ được các thuộc tính **đã được tải**. Nhưng những quan hệ `LAZY` chưa được khởi tạo có thể không truy cập được khi entity không còn kết nối với persistence context phù hợp.

Ví dụ:

```java
Order order = em.find(Order.class, orderId);
em.detach(order);

for (OrderLine line : order.getLines()) {
    // Nếu order.lines chưa được khởi tạo:
    // Hibernate có thể ném LazyInitializationException.
}
```

`Order` và `OrderLine` là entity minh họa, không thuộc demo `Product` ở phần trước. Bản chất vấn đề không phải “entity detached không đọc được dữ liệu nào”, mà là **dữ liệu lazy chưa có trong object** và không còn session/context sẵn sàng tải nó.

### Cách đáp ứng đúng nhu cầu đọc

- Nếu chỉ cần vài trường để trả API: dùng JPQL DTO projection.
- Nếu cần quan hệ cụ thể: truy vấn fetch join hoặc `EntityGraph` có chủ đích khi persistence context còn mở.
- Nếu collection có thể rất lớn: phân trang collection bằng query riêng; không tải toàn bộ chỉ để tránh lazy exception.
- Nếu cần truyền dữ liệu qua một ranh giới không có EntityManager: biến đổi thành DTO trong transaction thay vì đưa entity detached ra ngoài và cho tầng sau gọi getter lazy.

Ví dụ DTO lấy thông tin gọn:

```java
public record ProductView(Long id, String name, BigDecimal price) {}
```

```java
List<ProductView> page = em.createQuery(
    """
    SELECT new demo.ProductView(p.id, p.name, p.price)
    FROM Product p
    ORDER BY p.id
    """,
    ProductView.class
)
.setMaxResults(30)
.getResultList();
```

`ProductView` là record đặt ở package `demo`; cần import `java.math.BigDecimal` và `java.util.List` trong file tương ứng. Với projection, dữ liệu được lấy rõ ràng và không cần giữ cả entity graph managed cho mục đích hiển thị.

## 12. clear trong xử lý dữ liệu theo lô (batch)

Một ứng dụng import 100.000 sản phẩm có thể tạo nhiều entity trong cùng transaction. Nếu cứ `persist` liên tục mà không quản lý persistence context, số lượng managed entity tăng, chiếm bộ nhớ và khiến thao tác flush/dirty checking nặng hơn.

Mẫu thông dụng:

```java
int batchSize = 100;
int processed = 0;

EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    for (ProductInput input : inputs) {
        Product product = new Product(
            input.name(),
            input.price()
        );
        em.persist(product);
        processed++;

        if (processed % batchSize == 0) {
            em.flush();  // Gửi SQL đang chờ.
            em.clear();  // Bỏ các managed entity đã xử lý.
        }
    }

    em.flush(); // Phần cuối không đủ một batch.
    em.clear();

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) tx.rollback();
    throw ex;
}
```

`ProductInput` là DTO giả định có `name()` và `price()`. Đoạn code chỉ mô tả **một transaction lớn với persistence context được dọn theo từng batch**; không tự giải quyết các giới hạn database transaction, bộ nhớ của nguồn dữ liệu, retry hoặc lỗi dữ liệu ở giữa quá trình.

### Vì sao flush trước clear?

Nếu gọi:

```java
em.clear(); // Bỏ các entity đang managed trước khi SQL được đồng bộ.
```

thì những thay đổi/chèn mới chưa được flush có thể bị mất khỏi công việc persistence. `em.flush()` trước giúp provider gửi chúng xuống DB trong transaction hiện tại.

### Tại sao không chỉ clear mà không flush?

`clear` cắt quan hệ quản lý; nó không có nghĩa “ghi mọi thứ rồi làm trống”. Lời gọi `flush` cung cấp ranh giới đồng bộ rõ ràng, còn `clear` giải phóng trạng thái theo dõi.

### Tại sao batch size không có một giá trị tối ưu cố định?

Kích thước lô như 50, 100 hoặc 500 phụ thuộc workload, provider, driver, constraint, index và lượng memory. Ngoài ra, chiến lược sinh ID `IDENTITY` có thể hạn chế khả năng JDBC batching của một số provider. Đừng đánh đồng “flush/clear mỗi 100 entity” với “database nhận đúng một lệnh batch cho 100 INSERT”.

### Flush/clear không chia một transaction thành nhiều transaction

Trong ví dụ trên, nếu transaction duy nhất rollback sau lô cuối, các SQL đã flush trong các lô trước **vẫn có thể bị rollback**. Muốn commit theo lô độc lập để giảm transaction dài hoặc dễ tiếp tục sau lỗi, cần thiết kế **nhiều transaction có checkpoint**, idempotency và quy tắc xử lý partial success. `flush/clear` chỉ xử lý persistence context và SQL synchronization, không tự tạo commit.

## 13. clear sau bulk JPQL/native SQL

Một vấn đề khác là **bulk update/delete**: chúng tác động trực tiếp tới dữ liệu DB mà không đồng bộ từng managed entity đang trong context.

Ví dụ:

```java
Product product = em.find(Product.class, id);
System.out.println(product.getPrice()); // Giá cũ.

int changed = em.createQuery(
        """
        UPDATE Product p
        SET p.price = :newPrice
        WHERE p.id = :id
        """
    )
    .setParameter("newPrice", new BigDecimal("300000"))
    .setParameter("id", id)
    .executeUpdate();
```

Ngay sau lệnh bulk update, `product.getPrice()` có thể vẫn là giá cũ trong bộ nhớ. Bulk JPQL không tự đồng bộ state của tất cả entity managed; còn lifecycle callback và optimistic locking của entity thông thường có thể bị bỏ qua.

Một mẫu có chủ đích:

```java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    // Đồng bộ các thay đổi JPA đang chờ trước khi chạy bulk DML.
    em.flush();

    int updated = em.createQuery(
            "UPDATE Product p SET p.price = :price WHERE p.id = :id"
        )
        .setParameter("price", new BigDecimal("300000"))
        .setParameter("id", id)
        .executeUpdate();

    // Bỏ các managed snapshot có thể lỗi thời.
    em.clear();

    Product reloaded = em.find(Product.class, id);
    System.out.println(reloaded.getPrice());

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) tx.rollback();
    throw ex;
}
```

`clear` làm trạng thái đã tải cũ không còn managed; việc `find` sau đó sẽ có một managed instance tương ứng với dữ liệu hiện có, theo ngữ nghĩa truy cập/cache của provider. Nếu có second-level cache hoặc chiến lược caching ngoài JPA, cần xem cách provider vô hiệu hóa cache sau bulk operation.

**Ranh giới quan trọng:** `clear` không phải lệnh rollback, và không tự sửa các tham chiếu Java đang được giữ ở những nơi khác. Sau clear, các biến object cũ vẫn có thể chứa dữ liệu cũ và phải được xem như detached.

Nếu có nhiều entity không liên quan đang được sửa trong cùng context, `clear` có thể khiến chúng ngừng được tracking. Vì vậy chỉ clear sau khi bảo đảm những thay đổi cần thiết đã được flush và kế hoạch thao tác tiếp theo không dựa vào các managed reference cũ.

## 14. Khi nào nên dùng detach thay vì clear?

### Tình huống A: giữ một số entity managed, tách một entity lớn

Giả sử một transaction đang xử lý:

- Một `Customer` là entity chính cần tiếp tục sửa.
- Một `ReportSnapshot` vừa được tải để đọc nhiều dữ liệu, nhưng từ đây không cần dirty checking.

Khi đó có thể dùng:

```java
Customer customer = em.find(Customer.class, customerId);
ReportSnapshot report = em.find(ReportSnapshot.class, reportId);

// Đọc dữ liệu report mà ứng dụng cần.
em.detach(report);

// customer vẫn có thể được quản lý trong context.
customer.updateLastViewedReport(reportId);
```

Hai class chỉ minh họa. Nếu quan hệ của `report` có cascade detach, cần tính đến các entity liên quan. Mẫu này hữu ích khi **chỉ muốn loại một phần khỏi persistence context**, không tác động tất cả entity đang quản lý.

### Tình huống B: xử lý số lượng lớn entity trong một vòng lặp

Sau mỗi lô import hoặc xử lý hàng loạt đã flush, `clear` phù hợp vì **mọi entity vừa xử lý đều không cần giữ managed**:

```java
for (ProductInput input : inputs) {
    em.persist(new Product(input.name(), input.price()));
    // Cứ đến batch boundary: em.flush(); em.clear();
}
```

Nếu vẫn cần một số entity managed xuyên suốt các lô, `clear` sẽ detach cả chúng. Có thể tách đơn vị công việc thành nhiều EntityManager/transaction, hoặc tổ chức dữ liệu thành ID/DTO để tải lại khi cần thay vì cố giữ một managed graph khổng lồ.

### Tình huống C: muốn bỏ toàn bộ snapshot sau bulk update

`clear` là thao tác rõ ràng khi bulk SQL làm một phần lớn persistence context có thể lỗi thời. Nếu chỉ một entity cần đồng bộ lại, `refresh` trên managed entity hoặc `detach` rồi `find` lại có thể phạm vi hẹp hơn.

**Nguyên tắc lựa chọn:** dùng thao tác hẹp nhất đáp ứng mục tiêu, và xác định rõ các thay đổi chưa flush trước khi tách.

## 15. Trong ứng dụng Spring/Spring Data JPA

Với Spring, `EntityManager` thường được quản lý theo transaction/context qua `@PersistenceContext`. Các phương thức chuẩn vẫn có cùng ý nghĩa:

```java
@Service
public class ProductService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void readThenDetach(Long id) {
        Product product = entityManager.find(Product.class, id);

        // Đọc và xử lý theo nhu cầu.
        entityManager.detach(product);

        // product không còn managed trong context hiện tại.
    }

    @Transactional
    public void bulkRaisePrice(BigDecimal price) {
        entityManager.flush();

        entityManager.createQuery(
                "UPDATE Product p SET p.price = :price"
            )
            .setParameter("price", price)
            .executeUpdate();

        entityManager.clear();
    }
}
```

Đây là code trong môi trường Spring; cần dependency Jakarta Persistence, Spring Framework và các import tương ứng. `@Transactional` do transaction manager xử lý; không gọi `em.getTransaction().begin()` hoặc `commit()` thủ công trong một Spring-managed transaction như ví dụ Java SE.

### EntityManager ở Spring khác gì?

Khi Spring inject một EntityManager proxy, phương thức được chuyển tới context phù hợp với transaction hiện tại. Gọi `clear()` có thể làm **toàn bộ entity đang managed trong cùng transaction/context** trở thành detached, kể cả những entity service khác đã tải trong call stack. Vì vậy `clear` trong một repository helper dùng chung có thể gây tác dụng phụ khó nhận thấy.

### Spring Data JPA save sau clear

Sau:

```java
Product product = repository.findById(id).orElseThrow();
entityManager.clear();

product.rename("Tên mới");
```

đối tượng `product` không còn managed. Tùy cơ chế nhận diện trạng thái mới của Spring Data JPA, `repository.save(product)` có thể gọi `merge`, nhưng không nên dựa vào điều này để che giấu việc đang sửa detached entity. Nếu mục tiêu là cập nhật có kiểm soát, tải managed entity trong transaction phù hợp rồi sửa field; nếu thật sự cần merge, dùng **đối tượng do save/merge trả về** khi tiếp tục làm việc.

### Không dùng clear để “đảm bảo dữ liệu mới nhất” vô điều kiện

Trong Spring, có thể có transaction isolation, second-level cache, query cache hoặc môi trường nhiều request. `clear()` chỉ bỏ snapshot first-level của context hiện tại, **không cam kết** truy vấn lại sẽ nhìn thấy commit của transaction khác dưới mọi isolation level, và không tự vô hiệu hóa mọi tầng cache.

## 16. detach và clear khác gì với một transaction mới?

Persistence context và transaction là hai khái niệm có quan hệ nhưng không đồng nhất:

- Transaction quyết định nhóm thay đổi nào commit/rollback.
- Persistence context quản lý Java entity instances và tiến trình đồng bộ.
- `detach`/`clear` quyết định instance nào còn managed, **không kết thúc transaction**.
- `flush` gửi SQL theo transaction, **không kết thúc transaction**.
- `commit` kết thúc transaction; hành vi vòng đời persistence context phụ thuộc kiểu manager và môi trường.

Với EntityManager application-managed kiểu `RESOURCE_LOCAL` trong Java SE, có thể dùng **cùng EntityManager cho nhiều transaction** theo vòng đời có kiểm soát. Còn với container-managed transaction-scoped context, khi kết thúc transaction, những entity liên quan không nhất thiết tiếp tục managed ngoài context đó. Vì vậy đừng viết code giả định `@Transactional` kết thúc nhưng entity vẫn managed trong mọi cấu hình.

### clear không hủy connection/lock

Nếu transaction đã thực thi SQL và giữ lock, `em.clear()` không phải là câu lệnh giải phóng transaction hoặc commit. Lock còn phụ thuộc DB, isolation và transaction. Nếu muốn giải phóng các khóa transaction, cần kết thúc transaction đúng cách; detach/clear không thay thế thao tác đó.

### detach không phải cơ chế isolation

Một object detached là snapshot Java có thể trở nên cũ khi DB thay đổi. Nó không phải bản sao nhất quán vĩnh viễn hay một lock chống cập nhật đồng thời. Nếu muốn ghi lại dữ liệu detached sau một thời gian, dùng versioning/optimistic locking và xác định cách xử lý xung đột.

## 17. Trường hợp có cascade, association và entity mới

### 17.1. Entity đang có quan hệ chưa flush

Giả sử:

```java
Order order = em.find(Order.class, orderId);
order.addLine(new OrderLine("SKU-01", 2));

em.clear();
```

Nếu việc thêm child tạo ra thay đổi đang chờ flush, clear có thể làm chúng không được đồng bộ. Nếu dùng `cascade = PERSIST`, child mới có thể được provider quản lý tùy cách liên kết và flush; dù vậy, **không dùng clear ngay sau thay đổi chưa flush** nếu muốn lưu child.

Phương án rõ ràng:

```java
order.addLine(new OrderLine("SKU-01", 2));
em.flush();
em.clear();
```

Phần này giả định `Order.addLine` đồng bộ cả hai phía và mapping cascade/owning side được thiết kế phù hợp. Với entity graph phức tạp, cần hiểu các tác động cascade và transaction trước khi gọi clear.

### 17.2. detach một child có làm parent collection mất child không?

Không. Detach chỉ đổi trạng thái quản lý; nó **không mang ý nghĩa xóa liên kết** khỏi collection của parent.

```java
Order order = em.find(Order.class, orderId);
OrderLine line = order.getLines().get(0);

em.detach(line);

// order.getLines() không tự xóa line chỉ vì detach.
```

Nếu business logic muốn bỏ một dòng khỏi đơn, phải dùng helper trên domain và cấu hình orphan removal/cascade thích hợp. Đó là một **nghiệp vụ thay đổi quan hệ**, không phải một thao tác quản lý persistence context.

### 17.3. detach một entity mới vừa persist

Một đối tượng vừa `persist` có thể đang chờ INSERT. Nếu tách nó trước flush, đừng kỳ vọng hàng mới nhất định được chèn. Cần chủ động xác định điểm flush/commit khi nghiệp vụ yêu cầu lưu thành công, và không cố dùng detach như một cách để “lưu rồi ngừng theo dõi”.

## 18. Những lỗi thường gặp

### Lỗi 1: Tưởng detach đồng nghĩa DELETE

```java
em.detach(product); // Không xóa hàng product khỏi database.
```

Muốn xóa entity managed, dùng `em.remove(product)` trong transaction phù hợp. Muốn ngừng tracking mà không xóa, dùng detach.

### Lỗi 2: Sửa detached entity rồi đợi dirty checking

```java
em.detach(product);
product.changePrice(new BigDecimal("999000"));
// Không tự phát sinh UPDATE cho giá mới chỉ vì transaction commit.
```

Hãy sửa một managed instance hoặc `merge` trạng thái theo đúng quy trình nếu muốn lưu thay đổi.

### Lỗi 3: Gọi clear trước flush trong batch

```java
for (ProductInput p : inputs) {
    em.persist(new Product(p.name(), p.price()));
}
em.clear(); // Có thể bỏ những INSERT chưa được đồng bộ.
```

Khi muốn lưu, đồng bộ bằng `flush` trước rồi mới clear; cuối cùng vẫn cần transaction commit.

### Lỗi 4: Dùng clear trong một service và vô tình detach entity của service khác

`clear` áp dụng cho **toàn bộ context hiện tại**. Trong transaction bao gồm nhiều service, việc một phương thức helper gọi clear có thể khiến những object do service khác giữ không còn managed. Cần thỏa thuận ownership và ranh giới context; không gọi clear ngầm ở tầng tiện ích nếu caller không biết.

### Lỗi 5: Quên xử lý object do merge trả về

```java
em.merge(detached);
detached.rename("Tên sửa tiếp"); // Vẫn detached.
```

Sửa thành:

```java
Product managed = em.merge(detached);
managed.rename("Tên sửa tiếp");
```

### Lỗi 6: Tưởng clear vô hiệu hóa toàn bộ cache

JPA first-level cache thuộc persistence context, còn second-level cache có scope khác. `clear` không có nghĩa đã xóa cache cấp 2, cache HTTP hay cache ứng dụng. Cần đánh giá từng cơ chế cache riêng.

### Lỗi 7: Gọi getter lazy sau detach

```java
em.detach(order);
order.getLines().size(); // Có thể lỗi nếu lazy collection chưa load.
```

Chuẩn bị dữ liệu cần dùng trong context bằng DTO/projection/fetch phù hợp; không bật EAGER toàn hệ thống để chữa một endpoint.

### Lỗi 8: Gọi refresh trên detached object

`em.refresh(detached)` thường không hợp lệ vì refresh yêu cầu entity managed. Dùng `em.find` lại hoặc `merge` phù hợp với mục tiêu.

### Lỗi 9: Nhầm clear là rollback

`em.flush(); em.clear(); em.getTransaction().commit()` có thể **commit những thay đổi đã flush**. `clear` không hoàn nguyên SQL. Muốn hủy transaction, dùng `rollback`; mọi thay đổi đã flush trong transaction vẫn bị hủy theo ngữ nghĩa DB.

### Lỗi 10: Tái sử dụng reference cũ sau clear và tưởng nó managed

`Product old = ...; em.clear();` không khiến biến `old` được cập nhật khi `find` trả instance mới. Nếu tiếp tục làm việc với context, hãy dùng object managed trả về từ `find` hoặc `merge`, không giả định reference cũ được tự gắn lại.

## 19. Phân biệt mục tiêu thường gặp

| Mục tiêu của ứng dụng | Lựa chọn phù hợp | Ghi chú |
|---|---|---|
| Ngừng tracking đúng một entity | `em.detach(entity)` | Xem cascade DETACH |
| Dọn toàn bộ managed entity trong context | `em.clear()` | Mọi reference cũ trở thành detached |
| Lưu thay đổi đang chờ trước khi tách | `em.flush()` rồi detach/clear | Flush không phải commit |
| Cập nhật DB từ một detached object | `em.merge(...)` hoặc tải managed rồi sửa | Đối tượng trả về từ merge mới là managed |
| Cần dữ liệu DB mới trên managed entity | `em.refresh(entity)` | Có thể bỏ thay đổi chưa flush |
| Xóa hẳn hàng dữ liệu | `em.remove(entity)` | Cần entity managed và transaction phù hợp |
| Giải phóng EntityManager | `em.close()` | Không tiếp tục dùng EM đã đóng |
| Bỏ trạng thái cũ sau bulk SQL | `em.flush()` (nếu cần), bulk DML, `em.clear()` | Không bỏ sót thay đổi khác chưa đồng bộ |
| Trả danh sách nhiều dòng cho API | DTO projection và phân trang | Tránh phải quản lý rồi detach graph khổng lồ |

Một nguyên tắc xuyên suốt: trước khi cắt liên kết với persistence context, hãy quyết định **trạng thái managed hiện tại đã được phép bỏ hay phải được lưu**. Đó là quyết định nghiệp vụ và transaction, không phải chi tiết nhỏ của API.

## 20. Bài tập thực hành

### Bài 1 — Quan sát contains

Tải hai `Product` trong cùng `EntityManager`. In `contains` trước và sau `em.detach(first)`, rồi trước và sau `em.clear()`. Giải thích vì sao detach không ảnh hưởng trực tiếp tới entity còn lại, còn clear thì có.

### Bài 2 — Thay đổi trước và sau detach

Trong transaction, tải một product, sửa tên, detach, sau đó commit và tải lại trong `EntityManager` mới. Làm lại thí nghiệm nhưng gọi `em.flush()` trước detach. So sánh giá trị database sau commit.

### Bài 3 — Giữ một managed instance

Tải `Product` A và B. Detach A, đổi tên cả hai rồi commit. Giải thích vì sao B có thể được dirty-check, còn A thì không; kiểm tra kết quả thực tế.

### Bài 4 — Clear không phải close

Gọi `clear()`, sau đó dùng cùng `EntityManager` để `find` lại một product. So sánh với việc gọi `close()` rồi cố dùng lại manager. Nêu sự khác biệt về vòng đời.

### Bài 5 — Merge object detached

Tải `Product`, detach nó, đổi giá, gọi `merge` trong transaction và in `contains` cho cả object đối số lẫn kết quả trả về. Tiếp tục sửa object returned, commit và đọc lại.

### Bài 6 — Flush/clear trong batch

Tạo 5.000 sản phẩm với hai cách:

1. `persist` tất cả trong một transaction.
2. `persist` rồi `flush()/clear()` sau mỗi 100 sản phẩm.

Theo dõi lượng managed object, heap, thời gian và số SQL. Giải thích vì sao flush/clear làm giảm persistence context nhưng không tự chia transaction.

### Bài 7 — Bulk update rồi clear

Tải một product, chạy bulk JPQL `UPDATE Product p SET p.price = ...`, đọc lại giá trên reference cũ, clear rồi find lại. Ghi nhận sự khác nhau giữa snapshot Java và DB, đồng thời giải thích tại sao cần chú ý các thay đổi chưa flush của entity khác.

### Bài 8 — Quan hệ cascade DETACH

Tạo `Project` có `TaskItem`, cấu hình `cascade = DETACH` trên association thích hợp. Tải parent và child, gọi `detach(parent)` rồi dùng `contains` quan sát những entity nào còn managed. So sánh với trường hợp không cấu hình cascade.

### Bài 9 — Lazy collection và DTO

Một entity `Order` có `@OneToMany(fetch = LAZY)` tới `OrderLine`. Detach order trước khi đọc collection, quan sát hành vi khi lazy chưa load. Thiết kế một truy vấn DTO hoặc fetch có giới hạn để trả dữ liệu phù hợp ngoài persistence context.

## 21. Tự kiểm tra kiến thức

1. **`detach(entity)` làm gì?** Ngừng quản lý entity đó trong persistence context hiện tại; quan hệ được cascade DETACH có thể khiến entity liên quan cũng bị tách.
2. **`clear()` khác gì?** Nó làm trống toàn bộ context, detach mọi managed entity trong context.
3. **Sau detach, entity có mất ID không?** Không. Object vẫn giữ ID và những field đã được tải.
4. **Sửa entity detached rồi commit có tự UPDATE không?** Không. Dirty checking theo dõi managed entity.
5. **`flush` có đồng nghĩa commit không?** Không. SQL đã flush vẫn thuộc transaction và có thể bị rollback.
6. **Vì sao nên flush trước clear trong batch?** Để các thay đổi đang chờ được đồng bộ trước khi context bỏ trạng thái theo dõi.
7. **`merge(detached)` làm object đối số managed trở lại không?** Không; instance trả về là managed.
8. **`clear()` có đóng EntityManager không?** Không. Vẫn có thể dùng `em.find` và tạo giao dịch khác theo vòng đời EM thích hợp.
9. **`detach` có xóa quan hệ trong database không?** Không. Nó không phải thao tác thay đổi FK hay DELETE.
10. **Sau clear, gọi find cùng ID có tự cập nhật object cũ không?** Không. Object cũ vẫn detached; find trả một managed instance khác.
11. **clear có xóa second-level cache không?** Không; phạm vi của nó là persistence context hiện tại.
12. **Có thể dùng clear thay rollback để hủy SQL đã flush không?** Không. Chỉ transaction rollback mới mang ý nghĩa hủy thay đổi transaction.
13. **Tại sao một lazy association có thể lỗi sau detach?** Vì dữ liệu chưa tải không còn gắn với context đủ điều kiện để khởi tạo.
14. **Khi dùng Spring, vì sao clear ở một helper nguy hiểm?** Nó có thể detach cả những entity khác đang được managed trong cùng transaction.

**Ghi nhớ:** **`detach(entity)` tách một entity khỏi persistence context (và những entity liên quan khi có cascade phù hợp); `clear()` tách toàn bộ entity đang được quản lý.** Cả hai không xóa dữ liệu, không rollback và không commit. Sau khi tách, thay đổi trên object cũ không còn được dirty-check. Nếu muốn giữ thay đổi đang chờ, hãy **`flush` trước khi detach/clear**, sau đó commit transaction khi thành công; nếu cần tiếp tục cập nhật detached data, hãy dùng một **managed instance** qua `find` hoặc kết quả trả về từ `merge`.
