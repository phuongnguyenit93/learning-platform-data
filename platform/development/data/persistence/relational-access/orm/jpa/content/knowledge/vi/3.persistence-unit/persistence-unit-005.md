# Tạo và đóng EntityManager do ứng dụng quản lý

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Persistence Unit

Một `EntityManager` là điểm truy cập chính của ứng dụng vào cơ chế persistence của JPA: tìm, thêm, cập nhật, xóa và truy vấn entity. Khi **ứng dụng tự tạo `EntityManager` từ `EntityManagerFactory`**, ứng dụng cũng phải **quyết định phạm vi sử dụng và tự đóng nó đúng lúc**. Đây được gọi là *application-managed EntityManager*.

Bài học tập trung vào ba việc liên kết chặt chẽ với nhau: tạo `EntityManagerFactory` từ một persistence unit, lấy và sử dụng `EntityManager` trong một đơn vị công việc, rồi đóng tài nguyên và xử lý transaction ngay cả khi xảy ra ngoại lệ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt `EntityManagerFactory`, `EntityManager`, persistence unit, persistence context và transaction.
- Tạo một application-managed `EntityManager` bằng `EntityManagerFactory#createEntityManager()`.
- Chọn thời điểm mở/đóng `EntityManager` thích hợp cho một tác vụ, request hoặc unit of work.
- Dùng `EntityTransaction` trong persistence unit kiểu `RESOURCE_LOCAL`; đảm bảo commit hoặc rollback trước khi đóng `EntityManager`.
- Phân biệt `em.close()` và `emf.close()`, cũng như tác động của chúng lên entity đã tải.
- Tránh dùng chung `EntityManager` giữa nhiều thread, giữ entity manager quá lâu hoặc tự đóng container-managed `EntityManager`.
- Nhận biết trường hợp JTA/container quản lý transaction để không áp dụng nhầm mã resource-local.

## 2. Cần phân biệt những đối tượng nào?

```text
persistence.xml / cấu hình persistence unit
                    |
                    | Persistence.createEntityManagerFactory("demoPU")
                    v
         EntityManagerFactory (EMF)
         sống lâu, chia sẻ được
                    |
                    | emf.createEntityManager()
                    v
              EntityManager (EM)
              sống ngắn, theo một luồng thực thi
                    |
                    v
             Persistence Context
       quản lý các entity đang ở trạng thái managed
                    |
                    | flush khi cần / khi commit
                    v
           Provider JPA -> JDBC -> Database
```

| Khái niệm | Vai trò | Ai chịu trách nhiệm vòng đời trong ví dụ application-managed? |
|---|---|---|
| **Persistence unit** | Đơn vị cấu hình JPA: tên, danh sách entity, provider, kiểu transaction và thuộc tính kết nối | Ứng dụng/đơn vị triển khai khai báo cấu hình |
| **EntityManagerFactory (EMF)** | Tạo các `EntityManager` theo cấu hình persistence unit | Ứng dụng tạo một lần hoặc số ít lần, đóng khi kết thúc vòng đời ứng dụng |
| **EntityManager (EM)** | Giao diện làm việc với entity, query và persistence context | Ứng dụng tạo khi cần và **phải đóng** khi hoàn thành |
| **Persistence context (PC)** | Tập hợp managed entity cùng cơ chế định danh và theo dõi thay đổi | Gắn với EM application-managed; được giải phóng khi EM đóng theo quy tắc lifecycle |
| **Transaction** | Ranh giới các thay đổi được commit hoặc rollback | Với `RESOURCE_LOCAL`, ứng dụng điều khiển qua `EntityTransaction`; với JTA, transaction manager điều khiển |
| **Database connection** | Kết nối vật lý/logic để provider gửi SQL | Provider và connection pool điều phối; không đồng nhất một-một với EM |

**Hai nguyên tắc quan trọng:**

1. `EntityManagerFactory` được thiết kế để dùng đồng thời và thường được tái sử dụng; khởi tạo EMF có thể tốn công cấu hình provider, metadata và nguồn kết nối.
2. `EntityManager` **không thread-safe**. Mỗi luồng tác vụ cần phạm vi EM riêng; không đặt một EM dùng chung trong biến `static`, singleton service hay servlet field.

Đóng EM có nghĩa **kết thúc việc sử dụng persistence context đó**, không có nghĩa tắt cơ sở dữ liệu hay đóng toàn bộ EMF. Nhà cung cấp JPA có thể thuê/trả kết nối qua pool vào những thời điểm khác nhau.

## 3. Application-managed khác container-managed ở đâu?

Có hai cách thường gặp để có một `EntityManager`:

### 3.1. Ứng dụng tự quản lý

```java
EntityManager em = emf.createEntityManager();
try {
    // Làm việc với entity và query.
} finally {
    em.close(); // Bên tạo EM chịu trách nhiệm đóng.
}
```

Áp dụng phổ biến trong Java SE, công cụ chạy dòng lệnh, tác vụ độc lập, hoặc trường hợp ứng dụng chủ động dùng `EntityManagerFactory` dù đang chạy trong môi trường Jakarta EE.

### 3.2. Container/framework quản lý

```java
@PersistenceContext
private EntityManager em;
```

Với kiểu injection này, container quản lý lifecycle của entity manager được cung cấp. Mã nghiệp vụ **không gọi `em.close()`**. Trong ứng dụng Spring, `@PersistenceContext` thường đưa vào một proxy EntityManager do framework quản lý; transaction và tài nguyên thực tế được điều phối theo cơ chế Spring.

| Câu hỏi | Application-managed EM | Container-managed EM |
|---|---|---|
| Tạo EM ở đâu? | Gọi `emf.createEntityManager()` | Container/framework cấp qua injection/proxy |
| Ai đóng EM? | **Ứng dụng tự đóng** | Container/framework quản lý |
| Ai quản lý transaction? | Tùy cấu hình `RESOURCE_LOCAL` hay `JTA` | Thường transaction manager của container/framework |
| EM có thể dùng chung giữa thread không? | Không | Không suy ra underlying EM dùng chung; proxy/container áp dụng cơ chế riêng |
| Nên dùng khi nào? | Muốn tự xác định lifecycle, tác vụ Java SE, batch độc lập | Ứng dụng dùng quản lý transaction/injection của framework |

**Lưu ý:** “Application-managed EntityManager” mô tả **ai tạo và đóng EntityManager**, trong khi “resource-local/JTA” mô tả **ai quản lý transaction**. Hai trục này liên quan nhưng **không phải hai cặp đồng nghĩa**. Một application-managed EM cũng có thể tham gia transaction JTA.

## 4. Cấu hình một persistence unit để tự tạo EntityManager

Để ví dụ có ngữ cảnh cụ thể, ta xây ứng dụng Java SE lưu một ghi chú đơn giản. Mã dùng API `jakarta.persistence` tương ứng dòng Jakarta Persistence hiện đại và một JPA provider như Hibernate ORM. Cần có thư viện API Jakarta Persistence, provider tương thích và JDBC driver trên classpath; chỉ chép mã Java mà thiếu các dependency này thì ứng dụng chưa chạy được.

### 4.1. Khai báo `META-INF/persistence.xml`

Đặt file dưới `src/main/resources/META-INF/persistence.xml` nếu dự án dùng bố cục Maven/Gradle thông dụng.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="
               https://jakarta.ee/xml/ns/persistence
               https://jakarta.ee/xml/ns/persistence/persistence_3_0.xsd"
             version="3.0">
    <persistence-unit name="demoPU" transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>demo.Note</class>
        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:jpa_demo;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>

            <!-- Chỉ dành cho môi trường học tập với database tạm. -->
            <property name="hibernate.hbm2ddl.auto" value="create-drop"/>
            <property name="hibernate.show_sql" value="true"/>
            <property name="hibernate.format_sql" value="true"/>
        </properties>
    </persistence-unit>
</persistence>
```

Giải thích:

- `name="demoPU"`: định danh persistence unit, phải trùng tên truyền cho `Persistence.createEntityManagerFactory("demoPU")`.
- `transaction-type="RESOURCE_LOCAL"`: transaction được quản lý cục bộ qua `em.getTransaction()`.
- `provider`: chỉ định Hibernate làm implementation JPA; các thuộc tính có tiền tố `hibernate.` là tính năng provider, không phải API chung.
- `jakarta.persistence.jdbc.*`: cấu hình JDBC trong mô hình Java SE mẫu.
- `create-drop`: chỉ tiện cho database H2 tạm dùng khi học; **không dùng cho môi trường có dữ liệu cần giữ**. Hệ thống thật nên có migration và chiến lược quản lý schema rõ ràng.

Ví dụ sử dụng H2 in-memory. Với PostgreSQL, MySQL hoặc Oracle, cần đổi driver, URL, thông tin đăng nhập và bảo đảm schema tương thích. Các thông số kết nối thực tế không nên hard-code bí mật vào mã nguồn chia sẻ.

### 4.2. Entity tối giản

```java
package demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "notes")
public class Note {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String content;

    protected Note() {
        // Constructor không tham số để provider khởi tạo entity.
    }

    public Note(String content) {
        this.content = content;
    }

    public Long getId() {
        return id;
    }

    public String getContent() {
        return content;
    }

    public void changeContent(String newContent) {
        this.content = newContent;
    }
}
```

Khi viết `new Note("...")`, đối tượng chỉ là entity mới (transient), chưa được đăng ký với persistence context. Gọi `em.persist(note)` trong một transaction phù hợp sẽ khiến entity được quản lý và được lên lịch lưu vào database.

## 5. Tạo EntityManagerFactory rồi tạo EntityManager

### 5.1. Đoạn mã khởi tạo

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

EntityManagerFactory emf =
        Persistence.createEntityManagerFactory("demoPU");

try {
    EntityManager em = emf.createEntityManager();

    try {
        System.out.println("EM open = " + em.isOpen());
        // Tác vụ sử dụng em ở đây.
    } finally {
        em.close();
    }
} finally {
    emf.close();
}
```

Cách đọc đoạn mã:

1. `Persistence.createEntityManagerFactory("demoPU")` tìm persistence unit theo tên, tải provider và tạo EMF. Đây thường là hoạt động khởi động ứng dụng, không phải thao tác chạy lại cho mỗi query.
2. `emf.createEntityManager()` tạo **một EM mới** với persistence context gắn với nó.
3. Thực hiện các thao tác JPA trong phạm vi `try`.
4. Khối `finally` bảo đảm ứng dụng có cơ hội đóng EM kể cả khi thao tác phát sinh ngoại lệ.
5. EMF chỉ được đóng khi ứng dụng hoàn tất việc sử dụng tất cả EM do nó tạo ra.

Mô hình vòng đời phổ biến:

```text
Ứng dụng bắt đầu
  |
  +-- tạo EMF -----------------------+
  |                                 |
  |   Tác vụ A: tạo EM A            |
  |      tìm / ghi / truy vấn       |
  |      commit hoặc rollback       |
  |      close EM A                 |
  |                                 |
  |   Tác vụ B: tạo EM B            |
  |      tìm / ghi / truy vấn       |
  |      commit hoặc rollback       |
  |      close EM B                 |
  |                                 |
  +-- ứng dụng dừng: close EMF -----+
```

**Không mở một EM mới cho từng entity hoặc từng lệnh `find` trong cùng đơn vị nghiệp vụ cần transaction thống nhất.** Thay vào đó, xác định ranh giới unit of work rồi sử dụng một EM/transaction trong phạm vi đó. Ngược lại, không giữ EM sống suốt toàn bộ vòng đời ứng dụng chỉ vì EMF cũng sống lâu.

### 5.2. EMF thường được tạo một lần

Trong một service tự quản lý, có thể nhận EMF qua constructor và mở một EM trong từng public operation:

```java
public final class NoteService {
    private final EntityManagerFactory emf;

    public NoteService(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public Note findById(Long id) {
        EntityManager em = emf.createEntityManager();
        try {
            return em.find(Note.class, id);
        } finally {
            em.close();
        }
    }
}
```

Đây là minh họa lifecycle. Entity trả về đã ra khỏi persistence context khi method kết thúc và sẽ ở trạng thái detached theo trường hợp thông thường; nó không thích hợp để dựa vào lazy loading ngoài phương thức. Với API/service thực tế, trả một DTO chỉ chứa dữ liệu cần dùng thường rõ ràng hơn.

Service ở trên **không tự đóng EMF** vì EMF được truyền vào và thuộc quyền sở hữu của phần khởi tạo ứng dụng. Quy tắc sở hữu tài nguyên nên rõ ràng: **bên tạo EMF ở bootstrap quản lý `emf.close()`; bên tạo EM quản lý `em.close()`**.

## 6. Ví dụ hoàn chỉnh: ghi dữ liệu và đóng tài nguyên an toàn

Với `RESOURCE_LOCAL`, ứng dụng dùng `EntityTransaction` lấy từ chính EM. Cần kết thúc transaction bằng commit hoặc rollback **trước khi đóng EM**.

Tạo class `demo.App`:

```java
package demo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

public class App {

    public static void main(String[] args) {
        EntityManagerFactory emf =
                Persistence.createEntityManagerFactory("demoPU");

        try {
            Long noteId = createNote(emf, "Hoc EntityManager");
            readNote(emf, noteId);
            updateNote(emf, noteId, "Da hieu lifecycle");
            readNote(emf, noteId);
        } finally {
            if (emf.isOpen()) {
                emf.close();
            }
        }
    }

    private static Long createNote(EntityManagerFactory emf,
                                   String content) {
        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                Note note = new Note(content);
                em.persist(note);

                tx.commit();
                return note.getId();
            } catch (RuntimeException failure) {
                rollbackIfActive(tx, failure);
                throw failure;
            }
        } finally {
            if (em.isOpen()) {
                em.close();
            }
        }
    }

    private static void updateNote(EntityManagerFactory emf,
                                   Long id,
                                   String content) {
        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                Note note = em.find(Note.class, id);
                if (note == null) {
                    throw new IllegalArgumentException(
                            "Note does not exist: " + id);
                }

                note.changeContent(content);
                // Managed entity: JPA theo dõi thay đổi.
                tx.commit();
            } catch (RuntimeException failure) {
                rollbackIfActive(tx, failure);
                throw failure;
            }
        } finally {
            if (em.isOpen()) {
                em.close();
            }
        }
    }

    private static void readNote(EntityManagerFactory emf, Long id) {
        EntityManager em = emf.createEntityManager();

        try {
            Note note = em.find(Note.class, id);
            if (note != null) {
                System.out.println(
                        note.getId() + " -> " + note.getContent());
            }
        } finally {
            if (em.isOpen()) {
                em.close();
            }
        }
    }

    private static void rollbackIfActive(EntityTransaction tx,
                                         RuntimeException original) {
        try {
            if (tx.isActive()) {
                tx.rollback();
            }
        } catch (RuntimeException rollbackFailure) {
            original.addSuppressed(rollbackFailure);
        }
    }
}
```

Điểm đáng chú ý trong ví dụ:

- **Một EMF** phục vụ toàn bộ chương trình; ba method sử dụng EM riêng cho các unit of work.
- `createNote` có transaction để lưu entity mới; `updateNote` có transaction để áp dụng dirty checking.
- `readNote` sử dụng `find` cho tác vụ đọc đơn giản ngoài transaction tường minh. JPA cho phép nhiều thao tác đọc kiểu này, nhưng nếu cần ảnh chụp dữ liệu nhất quán qua nhiều truy vấn, khóa hoặc chính sách truy cập cụ thể, nên định nghĩa transaction đọc phù hợp.
- Nếu bất kỳ thao tác trong transaction thất bại, chương trình kiểm tra transaction có còn active không trước khi rollback, rồi ném tiếp lỗi ban đầu. Ngoại lệ khi rollback được thêm dưới dạng suppressed exception.
- Mỗi `EntityManager` được đóng trong `finally`, kể cả khi có lỗi ở khối xử lý; EMF được đóng ở cuối `main`.
- Trong `updateNote`, entity lấy qua `em.find` đang managed nên thay đổi `content` được provider theo dõi; không cần gọi một API `update()` riêng.
- Mã dùng `getTransaction()` vì persistence unit là `RESOURCE_LOCAL`; **không sao chép cách quản lý này nguyên xi sang application-managed EM tham gia JTA**.

SQL sinh ra, thời điểm `INSERT` thực hiện và chiến lược lấy khóa phụ thuộc provider, database, mapping và flush. Với `GenerationType.IDENTITY`, provider có thể phải chèn hàng sớm để lấy ID, trước khi ứng dụng gọi `commit()`. Dù SQL đã chạy thì transaction vẫn có thể rollback.

## 7. `close()` thực sự làm gì?

Khi gọi:

```java
em.close();
```

JPA kết thúc quyền sử dụng EM đó và giải phóng các tài nguyên liên quan theo cơ chế provider. Đối với một application-managed persistence context thông thường, các entity đã được quản lý không còn tiếp tục được EM cũ theo dõi sau khi context kết thúc.

### 7.1. Trước và sau `close()`

```java
EntityManager em = emf.createEntityManager();
Note detachedNote;

try {
    detachedNote = em.find(Note.class, existingId);

    System.out.println(em.contains(detachedNote)); // true nếu tìm thấy
    System.out.println(em.isOpen());                 // true
} finally {
    em.close();
}

System.out.println(em.isOpen()); // false

// Nếu detachedNote khác null, object Java vẫn tồn tại,
// nhưng thay đổi tiếp theo không được EM cũ theo dõi.
```

`existingId` trong ví dụ là ID một `Note` đã tồn tại. Phép `contains` cần object hợp lệ; nếu `find` trả `null`, phải kiểm tra trước khi gọi.

**Sau khi đóng EM:**

- `em.isOpen()` trả về `false`.
- Không dùng tiếp EM đã đóng để `find`, `persist`, query hoặc thao tác persistence khác; các thao tác không hợp lệ có thể ném `IllegalStateException`.
- Object Java đã tải vẫn có thể được giữ và đọc **những thuộc tính đã sẵn có trong bộ nhớ**.
- Nếu object có association lazy chưa được nạp, truy cập sau khi context đóng có thể gây ngoại lệ do provider không thể tải tiếp.
- Thay đổi trên object detached không tự được EM cũ flush. Muốn cập nhật trong unit of work mới phải dùng cơ chế phù hợp như tìm lại entity theo ID rồi sửa, hoặc `merge` và thao tác trên giá trị trả về.

`em.close()` **không** tự đồng nghĩa với `tx.commit()` hoặc `tx.rollback()`. Luồng xử lý phải tự kết thúc transaction trước khi close, không dựa vào hành vi dọn dẹp bất định khi vẫn còn transaction đang hoạt động.

### 7.2. `em.close()` và `emf.close()` không thay thế nhau

| Lệnh | Phạm vi kết thúc | Thời điểm thường dùng |
|---|---|---|
| `em.close()` | Một EntityManager và persistence context do ứng dụng quản lý | Sau khi unit of work kết thúc |
| `emf.close()` | EntityManagerFactory, metadata và tài nguyên thuộc factory theo cơ chế provider | Khi ứng dụng/module ngừng sử dụng persistence unit |
| `tx.commit()` | Xác nhận transaction | Khi toàn bộ thay đổi thành công |
| `tx.rollback()` | Hủy transaction chưa commit | Khi unit of work thất bại |
| `em.clear()` | Gỡ các managed entity khỏi persistence context nhưng EM vẫn mở | Khi chủ động giải phóng theo dõi entity, ví dụ batch có kiểm soát |
| `em.detach(entity)` | Gỡ một entity khỏi persistence context | Khi không muốn tiếp tục theo dõi một object cụ thể |

`clear()` và `detach()` **không đóng EM**. `flush()` gửi các thay đổi đang chờ xuống database nhưng **không cam kết transaction**; nó cũng không thay thế `close()`.

## 8. Chọn phạm vi sống của EntityManager

`EntityManager` nên có **phạm vi được định nghĩa và ngắn nhất đủ cho một đơn vị nghiệp vụ**.

### 8.1. Mỗi unit of work một EntityManager

Ví dụ tác vụ “tạo đơn hàng và ghi chi tiết đơn” gồm nhiều lệnh `persist`. Nếu các lệnh phải thành công hoặc thất bại cùng nhau, nên dùng **cùng EM và transaction**:

```text
Bắt đầu xử lý use case
  |
  +-- createEntityManager()
  |
  +-- tx.begin()
  |       +-- persist(Order)
  |       +-- persist(OrderLine 1)
  |       +-- persist(OrderLine 2)
  |       +-- kiểm tra dữ liệu / flush nếu cần
  |
  +-- tx.commit() hoặc tx.rollback()
  |
  +-- em.close()
  |
Kết thúc use case
```

Mở nhiều EM độc lập cho từng thao tác của cùng use case sẽ làm khó việc giữ một ranh giới transaction thống nhất và khiến entity ở các context khác nhau không còn cùng trạng thái quản lý.

### 8.2. Trong ứng dụng web

Nếu tự quản lý EM, có thể mở lúc bắt đầu một yêu cầu nghiệp vụ và đóng trong `finally` sau khi công việc kết thúc. Tuy nhiên, transaction chỉ nên bao quanh phần cần bảo đảm nhất quán; không nên để transaction mở trong lúc chờ người dùng, gọi mạng chậm hoặc xử lý ngoài phạm vi database.

Không đặt EM trong singleton controller/service như một field dùng chung cho tất cả HTTP request. Mỗi request/luồng độc lập cần EM scope phù hợp.

### 8.3. Trong batch

Khi xử lý hàng chục nghìn bản ghi, một EM có thể tích lũy quá nhiều managed entity trong first-level cache. Tùy yêu cầu transaction, thường cần xử lý theo lô nhỏ, `flush()` và `clear()` có kiểm soát hoặc tạo EM mới cho mỗi chunk. Nhưng `clear()` sẽ detach các entity hiện tại; nếu còn thao tác tiếp trên chúng, cần hiểu trạng thái trước khi làm.

**Không có một kích thước scope mặc định tốt cho mọi hệ thống.** Ranh giới transaction, số entity, concurrency và lượng dữ liệu thực tế sẽ quyết định cách chia.

## 9. Các lỗi và tình huống dễ gặp

### 9.1. Quên đóng EM

```java
public Note find(Long id) {
    EntityManager em = emf.createEntityManager();
    return em.find(Note.class, id); // Không có em.close().
}
```

Code trên tạo EM mới mỗi lần gọi nhưng bỏ quên đóng. Về lâu dài có thể tích lũy persistence context và tài nguyên provider, làm tăng bộ nhớ hoặc gây cạn kết nối tùy cách quản lý kết nối. Sửa bằng `try/finally`:

```java
public Note find(Long id) {
    EntityManager em = emf.createEntityManager();
    try {
        return em.find(Note.class, id);
    } finally {
        em.close();
    }
}
```

### 9.2. Đóng EM trước khi transaction kết thúc

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

tx.begin();
em.persist(new Note("Chua commit"));
em.close(); // Sai thiết kế: chưa commit hoặc rollback.
```

Lệnh `close` không phải công cụ hoàn thành giao dịch. Cần xử lý commit/rollback rõ ràng, rồi đóng EM trong `finally`. Với transaction JTA, thời điểm đóng khi giao dịch còn active có quy định riêng về kết thúc context, nhưng không nên dựa vào nó để thay thế quản lý transaction.

### 9.3. Dùng lại EM sau khi đã đóng

```java
em.close();
// em.find(Note.class, 10L); // Không dùng EM đã đóng.
```

Muốn thực hiện tác vụ mới, tạo EM mới từ EMF vẫn còn mở:

```java
EntityManager another = emf.createEntityManager();
try {
    Note note = another.find(Note.class, 10L);
} finally {
    another.close();
}
```

### 9.4. Đóng EMF mỗi lần gọi repository

```java
EntityManagerFactory emf =
        Persistence.createEntityManagerFactory("demoPU");

EntityManager em = emf.createEntityManager();
// ...
em.close();
emf.close(); // Hợp lý nếu ứng dụng thực sự kết thúc ở đây.
```

Nếu đoạn mã nằm trong một method được gọi liên tục, tạo và đóng EMF ở mỗi lần gọi sẽ gây khởi tạo lặp không cần thiết. Đặt vòng đời EMF tại bootstrap/shutdown hoặc cấu hình dependency injection phù hợp; EM mới là thứ thường xuyên được tạo và đóng theo unit of work.

### 9.5. Dùng cùng EM trong nhiều thread

```java
// Tránh: singleton giữ một EntityManager dùng chung.
class UnsafeNoteService {
    private final EntityManager em;

    UnsafeNoteService(EntityManagerFactory emf) {
        this.em = emf.createEntityManager();
    }
}
```

EM gắn với persistence context có trạng thái thay đổi và không an toàn cho truy cập đồng thời. Dùng chung EM giữa các request có thể gây dữ liệu stale, va chạm transaction hoặc lỗi khó tái hiện. EMF mới là tài nguyên được phép chia sẻ; từng thread/tác vụ tạo EM riêng và tự đóng.

### 9.6. Truy cập lazy attribute sau khi đóng EM

```java
EntityManager em = emf.createEntityManager();
Order order;
try {
    order = em.find(Order.class, orderId);
} finally {
    em.close();
}

// Nếu order.customer là lazy và chưa được nạp,
// order.getCustomer().getName() có thể thất bại.
```

`Order` và `orderId` ở đây tượng trưng cho entity quan hệ trong dự án có mapping sẵn. Cách giải quyết thường là tải đúng association trong use case còn mở context (fetch join, entity graph, projection/DTO) rồi trả dữ liệu cần dùng; không kéo dài EM chỉ để tránh lỗi lazy loading.

### 9.7. Hiểu nhầm `merge` là “mở lại” entity đã detached

```java
EntityManager em = emf.createEntityManager();
try {
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    Note managed = em.merge(detachedNote);
    managed.changeContent("Noi dung moi");

    tx.commit();
} finally {
    em.close();
}
```

Ví dụ giả sử `detachedNote` hợp lệ và được cung cấp từ trước. `merge` sao chép trạng thái vào **managed instance được trả về**; không khiến tham chiếu `detachedNote` ban đầu tự trở thành managed. Trong mã thật, cần rollback khi có lỗi theo mẫu tại phần 6. Với quy trình cập nhật bình thường, tìm entity theo ID rồi thay đổi các field cho phép là phương án rõ quyền sửa hơn.

## 10. Một số điểm nâng cao cần đặt đúng ngữ cảnh

### 10.1. Application-managed EM với JTA

Nếu persistence unit khai báo `transaction-type="JTA"` hoặc EMF được cấu hình theo JTA, ứng dụng **không quản lý transaction qua `em.getTransaction()` như ví dụ `RESOURCE_LOCAL`**. Giao dịch được điều phối bởi JTA transaction manager. EM do ứng dụng tạo vẫn phải được ứng dụng đóng; tùy cách tạo, trạng thái đồng bộ và thời điểm transaction bắt đầu, có thể cần `em.joinTransaction()` để EM tham gia giao dịch hiện tại.

Như vậy:

```text
Ai quản lý EntityManager?          Ứng dụng / Container
Ai quản lý transaction?            RESOURCE_LOCAL / JTA
```

Hai quyết định phải được xem độc lập. Không sao chép transaction code của Java SE resource-local vào một Jakarta EE/Spring JTA transaction nếu chưa hiểu transaction manager hiện tại.

### 10.2. Application-managed không mặc nhiên có transaction dài

Persistence context của một application-managed EM có thể tồn tại qua nhiều transaction nếu ứng dụng giữ EM mở. Điều này **không có nghĩa nên giữ một EM qua nhiều request**, cũng không có nghĩa những thay đổi ở transaction trước mặc nhiên được commit. Giữ context lâu làm tăng nguy cơ entity stale và tài nguyên khó quản lý. Khi muốn tạo unit of work mới, tạo EM mới thường đơn giản và dễ dự đoán hơn.

### 10.3. `EntityManager` không nhất thiết giữ một JDBC connection liên tục

Tạo EM không nhất thiết ngay lập tức lấy một kết nối vật lý từ pool; provider có thể chỉ cần connection lúc phát SQL và có thể trả connection theo chiến lược quản lý của provider. Ngược lại, quên đóng EM vẫn là lỗi quản lý tài nguyên dù tại thời điểm đó chưa quan sát được một connection đang bị giữ. Vì vậy **không dùng số connection nhìn thấy làm thước đo duy nhất** cho việc EM đã được đóng đúng hay chưa.

### 10.4. `try-with-resources` có dùng được không?

Không nên mặc định giả định mọi phiên bản `EntityManager` đang dùng đều thực thi `AutoCloseable` theo cùng API. Mẫu `try/finally` là cách minh họa tương thích và rõ ràng về quyền sở hữu tài nguyên. Nếu ứng dụng tự tạo một wrapper triển khai `AutoCloseable`, có thể dùng `try-with-resources` cho wrapper đó, nhưng wrapper vẫn phải gọi `em.close()` và xử lý transaction đúng.

### 10.5. Tránh nhầm connection pool với EMF

Ứng dụng có thể dùng `DataSource`/connection pool được container quản lý hoặc do provider tích hợp. `emf.close()` dọn tài nguyên **thuộc quyền sở hữu của EMF/provider**; không thể suy ra nó sẽ đóng mọi `DataSource` bên ngoài được cấp cho provider. Vòng đời của EM, EMF, pool và database là bốn vấn đề riêng.

## 11. Bài thực hành: quan sát lifecycle từng bước

Sử dụng cấu hình và `Note` ở phần 4–6. Trong môi trường học tập, bật SQL logging của provider và thực hiện các thao tác sau:

1. Khởi động `EntityManagerFactory` một lần; tạo EM A, quan sát `emA.isOpen()`.
2. Mở transaction A, `persist(new Note("Ban dau"))`, commit, ghi nhận ID.
3. Trong EM A, gọi `find` hai lần cùng ID và quan sát hai tham chiếu object có giống nhau không.
4. Đóng EM A; kiểm tra `emA.isOpen()`; giữ một tham chiếu tới entity đã được tìm.
5. Đổi nội dung trên object sau khi EM A đóng, nhưng **không gọi `merge`**.
6. Tạo EM B, `find` theo cùng ID; quan sát giá trị trong database có đổi theo bước 5 không.
7. Trong EM B, mở transaction, đổi nội dung managed entity rồi rollback; mở EM C để kiểm tra dữ liệu.
8. Thực hiện lại cập nhật trong transaction mới và commit; mở EM D để xác nhận dữ liệu.
9. Đóng từng EM bằng `finally`; chỉ đóng EMF sau khi tất cả thao tác hoàn thành.

Ghi lại bảng quan sát:

| Thời điểm | EM đang mở? | Entity đang managed trong EM đó? | Transaction đã commit? | Dữ liệu sau khi mở EM mới |
|---|---|---|---|---|
| Mới `persist` trong transaction | Có | Có | Chưa | Chưa kết luận từ transaction khác |
| Sau commit, trước `close` | Có | Thường vẫn managed | Có | Thấy dữ liệu đã commit theo isolation |
| Sau `em.close()` | Không | Không còn managed trong EM đó | Không thay đổi bởi close | Theo dữ liệu đã commit |
| Đổi object detached | EM cũ đã đóng | Không | Không có commit mới | Không tự cập nhật |
| Sửa managed entity rồi rollback | Có trong transaction | Có tại thời điểm sửa | Không | Thay đổi bị rollback |
| Sửa managed entity rồi commit | Có trong transaction | Có tại thời điểm sửa | Có | Giá trị mới được lưu |

Mục đích của thí nghiệm là **phân biệt object Java còn tồn tại, entity còn được quản lý và dữ liệu đã commit**. Chúng là ba trạng thái khác nhau.

## 12. Khi nào chọn cách ứng dụng tự quản lý EM?

**Phù hợp** khi bạn cần kiểm soát trực tiếp vòng đời của persistence context, ví dụ một chương trình Java SE nhỏ, một công cụ import dữ liệu hoặc một batch job chủ động chia transaction và chunk. Cách này giúp quan sát rõ create → transaction → commit/rollback → close.

**Nên cân nhắc framework/container quản lý** khi ứng dụng đã có Spring/Jakarta EE transaction manager và dependency injection: framework có thể điều phối persistence context theo request/transaction nhất quán hơn. Việc tự mở EM trong service đã dùng `@Transactional` có thể tạo ra một context khác với context framework đang điều phối, làm hành vi khó hiểu nếu thiếu chủ đích thiết kế.

Để quyết định, hãy trả lời trước ba câu hỏi:

- Ai tạo `EntityManagerFactory`, và ai đóng nó khi ứng dụng dừng?
- Transaction hiện tại do `EntityTransaction`, JTA hay Spring transaction manager kiểm soát?
- Mỗi `EntityManager` sẽ phục vụ đúng unit of work nào, và đường xử lý lỗi nào đảm bảo nó được đóng?

Nếu ba câu hỏi này có câu trả lời rõ ràng, cách thiết kế vòng đời sẽ dễ kiểm soát hơn.

## 13. Ghi nhớ nhanh

| Việc cần làm | Nguyên tắc |
|---|---|
| Khởi động JPA | Tạo `EntityManagerFactory` theo tên persistence unit |
| Bắt đầu một unit of work tự quản lý | Tạo `EntityManager` qua `emf.createEntityManager()` |
| Ghi dữ liệu với `RESOURCE_LOCAL` | `tx.begin()` → thao tác → `tx.commit()`, hoặc `tx.rollback()` nếu lỗi |
| Kết thúc unit of work | Đóng EM trong `finally`, sau khi transaction hoàn tất |
| Mở unit of work mới | Tạo EM mới; không tái sử dụng EM đã đóng |
| Chạy nhiều request/luồng | Chia sẻ EMF, **không chia sẻ cùng một EM** |
| Dừng ứng dụng | Đóng EMF sau khi các EM và công việc liên quan đã kết thúc |
| Sử dụng `@PersistenceContext` | Để container/framework quản lý EM; không tự gọi `close()` |
| Dùng JTA | Quản lý transaction qua JTA/container; không áp dụng `getTransaction()` resource-local |

**Quy tắc nền tảng:** *Tạo `EntityManagerFactory` theo vòng đời ứng dụng; tạo `EntityManager` theo đơn vị công việc; kết thúc transaction trước; sau đó luôn đóng `EntityManager` do chính ứng dụng tạo.*
