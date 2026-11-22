# Một thực thể theo một định danh trong cùng Persistence Context

Một trong những bảo đảm quan trọng nhất của Hibernate ORM là: **trong cùng một persistence context, mỗi định danh entity được quản lý tương ứng với một đối tượng entity managed duy nhất**. Nếu tải cùng một cuốn sách nhiều lần bằng cùng `EntityManager`/`Session`, Hibernate không tạo thêm một bản sao managed độc lập cho cuốn sách đó. Những phần mã khác nhau nhận được cùng trạng thái entity đang được theo dõi.

Đặc tính này thường được gọi là **identity guarantee** hoặc **identity map** của persistence context, đồng thời là nền tảng của **first-level cache**, dirty checking và việc quản lý quan hệ entity. Hiểu đúng phạm vi của nó giúp giải thích vì sao `find()` nhiều lần có thể trả cùng tham chiếu Java, vì sao `merge()` trả đối tượng khác đối tượng truyền vào, và vì sao hai transaction khác nhau vẫn có thể cập nhật xung đột một hàng database.

Bài này dùng Jakarta Persistence (`jakarta.persistence.*`) và Hibernate ORM 6.x. Thuật ngữ `EntityManager` của JPA và `Session` của Hibernate được nhắc song song khi cùng nói về persistence context thông thường; hai API có những khác biệt về phương thức, cách bootstrap và tích hợp transaction.

## 1. Persistence Context là gì?

**Persistence context** là phạm vi Hibernate theo dõi tập hợp entity **managed**. Nó không chỉ chứa object được cache mà còn có các thông tin giúp ORM quản lý công việc:

- **Định danh entity và identity map:** biết instance nào đại diện cho một entity identity.
- **Trạng thái managed:** snapshot, thông tin định danh, version, trạng thái nạp và thay đổi chưa đồng bộ.
- **Quan hệ và collection:** liên kết giữa các entity managed, trạng thái collection, khả năng lazy loading.
- **Dirty checking và flush:** so sánh hoặc theo dõi thay đổi để quyết định DML cần gửi xuống database.
- **Đơn vị công việc:** phối hợp đối tượng được tải, tạo mới, xóa và thao tác liên quan trong phạm vi session.

Persistence context của `EntityManager` ứng với first-level cache của Hibernate `Session` thông thường. Tên gọi “cache” có thể gây nhầm lẫn: **nó là một cấu trúc quản lý danh tính và trạng thái**, không phải một bộ cache kết quả truy vấn dùng chung toàn hệ thống.

~~~mermaid
flowchart TD
    DB[(books: id 101, 102)]
    EM1[EntityManager A / Session A]
    PC1[Persistence Context A]
    E1["Book#101 → Java object A1"]
    E2["Book#102 → Java object A2"]
    EM2[EntityManager B / Session B]
    PC2[Persistence Context B]
    E3["Book#101 → Java object B1"]
    EM1 --> PC1
    EM2 --> PC2
    PC1 --> E1
    PC1 --> E2
    PC2 --> E3
    PC1 <--> DB
    PC2 <--> DB
~~~

Cùng một hàng `books.id = 101` có thể tồn tại dưới dạng **A1** trong context A và **B1** trong context B. A1 và B1 là hai object Java khác nhau, nhưng mỗi context chỉ quản lý một entity instance cho identity đó.

### 1.1. “Một định danh” cần hiểu chính xác

Khóa của identity map là **định danh entity theo metadata ánh xạ**, không chỉ là giá trị số ID đứng riêng. Ở mức khái niệm, cần biết:

1. **Kiểu/mapping entity**: một `Book` ID 101 và một `Customer` ID 101 là hai entity identity khác nhau.
2. **Giá trị primary key**: đơn giản như `Long 101` hoặc khóa ghép `OrderLineId`.
3. **Phạm vi tenant và mô hình persistence** nếu ứng dụng có multitenancy: cùng ID ở tenant khác có thể chỉ đến bản ghi khác; cần cấu hình và scope đúng.

Trong một hierarchy kế thừa, root/subclass cùng có chung identity của entity thực tế. Hibernate dùng metadata để đảm bảo không quản lý hai phiên bản entity mâu thuẫn của cùng một entity identity trong cùng context.

Điểm cốt lõi **không phải** “toàn ứng dụng chỉ có một object cho ID 101”, mà là **mỗi persistence context có một đại diện managed cho một entity identity**.

## 2. Ví dụ entity để quan sát identity guarantee

Giả sử bảng `books`:

~~~sql
create table books (
    id bigint primary key,
    title varchar(200) not null,
    version bigint not null
);

insert into books (id, title, version)
values (101, 'Hibernate Basics', 0);
~~~

Entity tương ứng:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "books")
public class Book {

    @Id
    private Long id;

    @Column(name = "title", nullable = false, length = 200)
    private String title;

    @Version
    private long version;

    protected Book() {
        // Constructor dành cho JPA.
    }

    public Book(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Title is required");
        }
        this.title = newTitle;
    }

    public long getVersion() {
        return version;
    }
}
~~~

Ví dụ dùng ID **được ứng dụng gán** để dễ quan sát. `@Version` được dùng về sau để phân biệt identity trong bộ nhớ với optimistic locking giữa các transaction. Cấu hình database và `EntityManagerFactory` được giả định đã có.

## 3. Gọi `find()` hai lần trong cùng context

~~~java
EntityManager em = entityManagerFactory.createEntityManager();

try {
    em.getTransaction().begin();

    Book first = em.find(Book.class, 101L);
    Book second = em.find(Book.class, 101L);

    System.out.println(first == second); // true nếu entity tồn tại.
    System.out.println(em.contains(first)); // true

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Khi cả hai lần `find()` dùng **cùng một `EntityManager` đang mở**, Hibernate quản lý một instance `Book` có identity `(Book, 101)`. Kết quả `first == second` là `true` (giả sử hàng tồn tại và không bị detach/clear giữa hai lời gọi).

Một cách hình dung:

~~~text
Persistence Context A
  Entity identity (Book, 101)
               │
               └── Book instance X
                    ↑         ↑
                  first     second
~~~

Hai biến `first` và `second` **không phải hai bản sao**. Nếu thay đổi thuộc tính qua biến thứ nhất, biến thứ hai nhìn thấy trạng thái cùng object:

~~~java
first.rename("Hibernate in Practice");
System.out.println(second.getTitle());
// Hibernate in Practice
~~~

Không cần gọi `merge(first)` vì `first` đã là entity managed. Trong transaction có thể ghi, Hibernate có thể flush thay đổi khi commit theo flush mode và cấu hình, kết hợp `@Version` để bảo vệ cập nhật cạnh tranh.

### 3.1. Vì sao bảo đảm này quan trọng?

Nếu ORM tạo hai bản sao managed khác nhau cho cùng hàng ID 101, mã xử lý có thể:

- Thay `title` trên bản sao thứ nhất.
- Thay `title` theo giá trị khác trên bản sao thứ hai.
- Không biết bản nào phản ánh trạng thái cuối cùng khi flush.

Identity map khiến Hibernate theo dõi **một đại diện** cho entity identity trong một đơn vị công việc; những tham chiếu tới entity đó cùng thấy thay đổi trong bộ nhớ. Điều này giúp dirty checking và mối quan hệ giữa các entity có ý nghĩa nhất quán.

Bảo đảm identity **không đồng nghĩa** entity được khóa trước mọi transaction khác; nó chỉ nói về trạng thái trong một persistence context.

## 4. First-level cache khác query cache và second-level cache

| Cơ chế | Phạm vi | Giữ gì? | Ý nghĩa của “cùng instance” |
| --- | --- | --- | --- |
| **First-level cache/persistence context** | Một `Session`/`EntityManager` | Entity managed và trạng thái phục vụ unit of work | Có identity guarantee trong cùng context |
| **Second-level cache (L2)** | Thường gắn với `SessionFactory` và cache region/provider | Dữ liệu/cache entry của entity, collection… theo cấu hình | Các session khác nhau vẫn dựng các **instance managed riêng** |
| **Query cache** | Theo cấu hình Hibernate/cache provider | Thông tin kết quả query/cache keys, phối hợp với entity cache | Không có cam kết chia sẻ cùng object instance giữa session |
| **Application cache** | Do ứng dụng định nghĩa | DTO/object tùy thiết kế | Không tự có semantics persistence context |

**First-level cache tồn tại mặc định** với một Hibernate `Session` thông thường và không cần bật L2 cache. Hibernate có thể lấy dữ liệu entity từ L2 cache nếu cấu hình phù hợp, nhưng session A và session B vẫn có hai context khác nhau.

### 4.1. `find()` lặp lại khác query HQL lặp lại

~~~java
Book book = em.find(Book.class, 101L);

Book fromQuery = em.createQuery(
        "select b from Book b where b.id = :id",
        Book.class
    )
    .setParameter("id", 101L)
    .getSingleResult();

System.out.println(book == fromQuery); // true trong cùng context.
~~~

HQL có thể vẫn thực thi SQL để xác định **bản ghi nào khớp điều kiện**; first-level cache **không phải cache toàn bộ tập kết quả của mọi truy vấn**. Nhưng khi dòng kết quả đại diện cho identity đã managed, Hibernate trả về **đối tượng managed tương ứng**, chứ không tạo bản thứ hai.

Đừng suy ra: “đã `find` một lần nên mọi HQL sau đó chắc chắn không phát SELECT”. Muốn tối ưu query, phải xem SQL thực tế và cân nhắc query cache/projection/query plan theo nhu cầu.

### 4.2. Nhiều dòng SQL không đồng nghĩa nhiều entity instance

Một truy vấn có join tới collection có thể tạo nhiều dòng SQL đại diện cho cùng root entity:

~~~sql
-- Ví dụ dạng SQL khái niệm:
select b.id, b.title, c.id
from books b
left join book_chapters c on c.book_id = b.id;
~~~

Một sách có ba chương có thể xuất hiện trong ba dòng result set. Hibernate cần gom các dòng liên quan vào object graph. **Identity map không cho phép ba managed Book instance khác nhau cùng identity trong một context**.

Số phần tử lặp trong **List kết quả truy vấn** phụ thuộc HQL, `distinct`, kiểu join và Hibernate version; Hibernate 6 có cơ chế loại trùng kết quả root trong các trường hợp fetch join. Không đánh đồng **số row JDBC**, **số phần tử result list** và **số entity instance managed**.

## 5. `getReference()`, lazy proxy và identity

`EntityManager.getReference(Book.class, 101L)` trả về một reference tới entity identity được yêu cầu. Hibernate thường có thể tạo proxy hoặc reference chưa cần truy vấn DB ngay, tùy mapping, proxy support và bytecode enhancement.

~~~java
Book reference = em.getReference(Book.class, 101L);

// Không nên xem getReference là bằng chứng hàng đã tồn tại.
Book loaded = em.find(Book.class, 101L);

System.out.println(loaded.getId());
~~~

Với cùng context, Hibernate duy trì identity và biết reference nào đại diện cho entity đó. Tuy nhiên, **không nên phụ thuộc vào việc mọi thao tác với proxy luôn có cùng hình thức Java hoặc cùng kiểu runtime concrete**. Các lớp proxy có thể không trùng `entity.getClass()` với class thực, và thời điểm truy vấn được phát tùy cách khởi tạo.

Nếu gọi `getReference()` cho ID không tồn tại, lời gọi này **không bắt buộc kiểm tra tồn tại ngay**; lỗi có thể xuất hiện khi proxy cần được khởi tạo. Để kiểm tra bản ghi thực sự có tồn tại trong nghiệp vụ, dùng `find()`/query thích hợp và vẫn duy trì DB constraint nếu tạo association có FK.

### 5.1. Tại sao không nên dùng `new Book(101, ...)` làm “reference”?

~~~java
Book managed = em.find(Book.class, 101L);
Book another = new Book(101L, "Different title");
~~~

`another` không tự trở thành managed chỉ vì nó có cùng ID. Đây là **đối tượng Java khác** ngoài persistence context. Một object mới được tạo không được xem là “đại diện thứ hai managed” khi Hibernate chưa hề nhận quản lý nó.

Nếu muốn gán một reference mà không tải đầy đủ object, dùng API `getReference()` phù hợp. Nếu muốn cập nhật một managed entity, sửa object do `find()`/query trả về hoặc xử lý trạng thái detached bằng cơ chế rõ ràng.

## 6. `persist()` và xung đột entity có cùng identifier

Giả sử context đang quản lý `Book` 101:

~~~java
Book managed = em.find(Book.class, 101L);

Book duplicate = new Book(101L, "Other copy");

// Không làm như sau để cập nhật cùng ID:
em.persist(duplicate);
~~~

`persist()` có ý nghĩa chuyển một **entity mới** vào trạng thái managed để lưu, không phải “thay thế managed entity đang tồn tại có ID giống nhau”. Nếu persistence context đã chứa một instance khác cho entity identity tương ứng, Hibernate/JPA có thể báo lỗi như `EntityExistsException`, `NonUniqueObjectException` (trong những API/tình huống nhất định) hoặc một `PersistenceException` khi thực thi/flush.

Loại exception và thời điểm báo lỗi tùy API, trạng thái entity, identifier strategy và thời điểm SQL được thực hiện. **Không dùng `persist()` để update một bản sao đã có ID.**

### 6.1. Hai loại trùng lặp cần phân biệt

**Trùng instance trong một persistence context:** ứng dụng đưa hai object Java riêng cùng identity vào một context. Đây là xung đột identity ở tầng ORM; Hibernate không thể cùng quản lý cả hai.

**Trùng primary key ở database:** ứng dụng đưa một ID đã tồn tại trong DB vào một transaction khác, nhưng context chưa nạp hàng đó. Lỗi có thể chỉ xuất hiện ở `INSERT` khi DB từ chối PK duplicate. Không phải mọi lỗi PK duplicate đều có nguyên nhân từ identity map.

Tương tự, một `unique constraint` trên `email` có thể bị vi phạm bởi **hai entity có ID khác nhau**. Identity map theo **entity primary key**, không tự bảo đảm tính duy nhất của mọi business field.

## 7. `merge()` và hai object cùng ID: điểm dễ nhầm nhất

Một đối tượng được đọc trước đó có thể trở thành **detached** khi `EntityManager` đóng hoặc entity được detach. Nó vẫn có ID và dữ liệu Java, nhưng không còn được context cũ theo dõi.

Ví dụ:

~~~java
Book detached;

EntityManager firstEm = entityManagerFactory.createEntityManager();
try {
    detached = firstEm.find(Book.class, 101L);
} finally {
    firstEm.close();
}

// detached là object Java vẫn tồn tại,
// nhưng không còn managed ở EntityManager đã đóng.
detached.rename("Edited outside session");
~~~

Giả sử mở context mới:

~~~java
EntityManager secondEm = entityManagerFactory.createEntityManager();
try {
    secondEm.getTransaction().begin();

    Book managed = secondEm.merge(detached);

    System.out.println(managed == detached); // false trong ví dụ này.

    secondEm.getTransaction().commit();
} catch (RuntimeException ex) {
    if (secondEm.getTransaction().isActive()) {
        secondEm.getTransaction().rollback();
    }
    throw ex;
} finally {
    secondEm.close();
}
~~~

**`merge(detached)` trả về một instance managed** nhận trạng thái được copy theo quy tắc merge. Tham số `detached` **vẫn là detached**, không được chuyển nguyên object sang context mới. Nếu context mới đã có `Book` 101, merge có thể copy trạng thái vào managed instance hiện có và trả về chính instance đó.

~~~text
Ngoài Persistence Context B:
  detachedBook (Book, ID 101)
        │
        │ merge (copy state)
        v
Persistence Context B:
  managedBook (Book, ID 101)  ← duy nhất ở B
~~~

Sự xuất hiện đồng thời của `detachedBook` và `managedBook` **không phá vỡ identity guarantee**: chỉ một trong chúng nằm trong context B với trạng thái managed.

### 7.1. Không tiếp tục thay đổi object detached sau `merge()` rồi mong tự flush

~~~java
Book managed = em.merge(detachedBook);

// Đúng: tiếp tục làm việc với managed trong transaction.
managed.rename("Final title");

// Không nên chỉ sửa detachedBook rồi kỳ vọng Hibernate theo dõi:
detachedBook.rename("Untracked title");
~~~

Hibernate theo dõi `managed`, không theo dõi `detachedBook`. Nếu muốn đồng bộ thay đổi tiếp theo của detached object, phải có thao tác có chủ đích và hiểu khả năng ghi đè trạng thái.

### 7.2. `merge()` không phải giải pháp vô điều kiện cho payload API

Giả sử client gửi một object detached được xây từ JSON chỉ chứa `id` và `title`, nhưng entity còn các trường khác mà client không gửi. `merge()` có thể copy trạng thái các trường được coi là có trong object, làm ghi đè dữ liệu không mong muốn.

Một cách thường an toàn hơn cho PATCH/update nghiệp vụ:

~~~java
Book managed = em.find(Book.class, request.bookId());

if (managed == null) {
    throw new IllegalArgumentException("Book not found");
}

managed.rename(request.title());
// Chỉ thay đổi trường được phép trong transaction hiện tại.
~~~

`request` ở ví dụ là một DTO/command đã được validate và không phải managed entity. Khi nghiệp vụ cần kiểm soát concurrency, phải kết hợp version check và policy phù hợp. Identity map giúp duy nhất instance trong context, **không tự giải quyết việc client gửi trạng thái quá cũ**.

### 7.3. Merge nhiều bản sao detached trong một graph

Nếu một object graph truyền vào `merge()` chứa **nhiều object khác nhau có cùng entity identity**, Hibernate có thể phát hiện các **entity copies**. Tùy cấu hình, Hibernate có thể từ chối hoặc có cách xử lý riêng (`hibernate.event.merge.entity_copy_observer`). Không nên bật chế độ cho phép tùy tiện để “chữa” dữ liệu graph trùng: nếu hai bản sao mang hai trạng thái khác nhau, việc chọn giá trị cuối có thể không dự đoán được theo nghiệp vụ.

Nên khử trùng lặp DTO/graph theo ID trước khi xây entity hoặc xử lý thay đổi trên một managed instance đã được tải.

## 8. Entity lifecycle và ranh giới identity

| Trạng thái / thao tác | Đối tượng có đang được context quản lý? | Tác động tới quy tắc identity |
| --- | --- | --- |
| `new Book(...)` | **Transient/new**, chưa managed | Object cùng ID ở heap chưa phải xung đột managed |
| `persist(newEntity)` | Entity được đưa vào managed theo quy tắc JPA | Context quản lý một đại diện theo identity; có thể báo lỗi nếu xung đột |
| `find(Entity.class, id)` | Trả managed entity nếu tồn tại | Nếu đã có identity đó, sử dụng managed instance tương ứng |
| `getReference(...)` | Trả reference gắn với context, có thể là proxy | Việc khởi tạo reference và kiểu runtime cần xem semantics Hibernate |
| `detach(entity)` / `Session.evict(entity)` | Object không còn managed trong context đó | Có thể tải/attach một managed instance khác cùng ID sau đó |
| `clear()` | Detach **toàn bộ** entity managed khỏi context | Identity map bị làm rỗng; các tham chiếu Java cũ vẫn tồn tại detached |
| `close()` | Kết thúc `EntityManager`/`Session` | Không còn persistence context hoạt động; object bên ngoài trở thành detached |
| `merge(detached)` | Trả về một managed instance, tham số không tự được quản lý | Bảo đảm chỉ có một đại diện managed trong context đích |
| `remove(managed)` | Chuyển trạng thái entity sang removed trong vòng đời JPA | Có quy tắc quản lý/xóa riêng; không nên dùng remove để “đổi instance” |
| `refresh(managed)` | Managed tiếp tục được theo dõi | Nạp lại trạng thái từ DB; không tạo bản sao mới thay cho managed object |

### 8.1. `clear()` tạo ranh giới identity mới ngay trong một EntityManager

~~~java
Book beforeClear = em.find(Book.class, 101L);

em.clear(); // beforeClear bị detached.

Book afterClear = em.find(Book.class, 101L);

System.out.println(beforeClear == afterClear); // false, thường vậy.
System.out.println(em.contains(beforeClear));   // false
System.out.println(em.contains(afterClear));    // true
~~~

Đây không mâu thuẫn với quy tắc một managed instance cho một identity: **ở thời điểm `afterClear` managed, `beforeClear` đã detached**.

Cảnh báo: `clear()` có thể loại bỏ thay đổi pending chưa flush. Nếu đã sửa entity và muốn lưu, cần flush/commit theo transaction phù hợp trước khi clear, hoặc chủ động bỏ thay đổi. Gọi `clear()` để “giải quyết xung đột identity” mà chưa hiểu dữ liệu sẽ mất là rủi ro.

### 8.2. Transaction commit không nhất thiết tự đóng Session

`EntityManager` dạng application-managed có thể tiếp tục mở sau `commit()`; persistence context không bắt buộc biến mất chỉ vì transaction kết thúc. Một extended persistence context còn có thể sống qua nhiều transaction theo cấu hình/phạm vi riêng.

Trong mô hình Spring `@Transactional` thường dùng transaction-scoped persistence context, framework giải phóng context theo ranh giới thích hợp. Vì vậy nên nói chính xác **“trong cùng persistence context”**, thay vì mặc định “trong cùng transaction” hay “trong cùng HTTP request” trong mọi trường hợp.

## 9. Cùng ID qua hai Persistence Context khác nhau

~~~java
EntityManager emA = entityManagerFactory.createEntityManager();
EntityManager emB = entityManagerFactory.createEntityManager();

try {
    Book bookA = emA.find(Book.class, 101L);
    Book bookB = emB.find(Book.class, 101L);

    System.out.println(bookA == bookB); // false trong mô hình thông thường.
    System.out.println(bookA.getId().equals(bookB.getId())); // true
} finally {
    emA.close();
    emB.close();
}
~~~

Mỗi `EntityManager` có persistence context riêng, nên cùng một hàng DB được biểu diễn bằng **hai instance managed độc lập**. Việc so sánh ID giúp biết chúng tham chiếu cùng logical entity identity theo cùng persistence unit và tenant, nhưng không làm chúng trở thành cùng object Java.

Không truyền `bookA` vào `emB.persist(bookA)` để “đồng bộ” hai context. Nếu cần cập nhật ở B, tải và thay đổi instance managed của B hoặc dùng `merge()` với hiểu biết về copy state và version.

### 9.1. Hai persistence context, hai trạng thái có thể khác nhau

~~~text
T0: DB Book#101 title = "Original", version = 0

Context A: Book#101 title = "Original"
Context B: Book#101 title = "Original"

A đổi title thành "From A" rồi commit.

Context B có thể vẫn giữ "Original".
~~~

Context B không tự động cập nhật khi A commit. First-level cache bảo đảm **identity trong B**, không phải luôn tươi mới với DB. Muốn đồng bộ phải dùng transaction scope phù hợp, `refresh()` hoặc một cách nạp lại có chủ đích.

Nếu B cũng sửa cùng entity và commit, `@Version` có thể giúp phát hiện xung đột update thay vì ghi đè âm thầm.

## 10. Identity map không phải cơ chế khóa concurrency

~~~mermaid
sequenceDiagram
    participant A as Context A / Tx A
    participant DB as Database
    participant B as Context B / Tx B
    A->>DB: SELECT Book#101, version=0
    B->>DB: SELECT Book#101, version=0
    A->>A: rename("A")
    B->>B: rename("B")
    A->>DB: UPDATE ... version=1 WHERE version=0
    DB-->>A: Thành công
    B->>DB: UPDATE ... version=1 WHERE version=0
    DB-->>B: Không còn hàng khớp version=0
    B-->>B: Optimistic-lock conflict
~~~

Mỗi context **đều** có đúng một managed instance của `Book#101`, nhưng hai transaction vẫn có thể xung đột. Đây là hai vấn đề khác nhau:

| Vấn đề | Phạm vi | Giải pháp phù hợp |
| --- | --- | --- |
| Trùng instance managed cho một identity | **Nội bộ một persistence context** | Identity map và lifecycle API của Hibernate |
| Concurrent updates/lost update | **Giữa các transaction** | `@Version`, locking, isolation, conflict policy |
| Stale managed entity | **Context tồn tại trong khi DB đổi** | Context ngắn, `refresh`/clear/reload có chủ đích |
| Cùng ID ở hai tenant | **Phạm vi tenant và schema** | Thiết kế tenant key, scoping và constraint phù hợp |
| Hai Java object có ID bằng nhau | **Bộ nhớ ứng dụng** | Định nghĩa `equals`/`hashCode` theo mục đích nghiệp vụ |

Quy tắc identity của Hibernate không cho phép dùng `Session` đồng thời ở nhiều thread. `Session` và `EntityManager` thông thường **không thread-safe**. Một context cần một owner/đơn vị công việc có ranh giới rõ, ngay cả khi nó luôn quản lý một instance cho mỗi identity.

## 11. `equals()`, `hashCode()` và phép so sánh `==`

Identity guarantee thường khiến người học lẫn lộn ba khái niệm:

1. **Java reference identity (`a == b`):** hai biến cùng trỏ tới một object Java.
2. **Business/entity equality (`a.equals(b)`):** do phương thức `equals` định nghĩa; có thể dựa vào ID hoặc business key.
3. **Persistence identity:** cùng entity mapping và primary key trong phạm vi persistence unit/tenant tương ứng, được Hibernate quản lý duy nhất trong một context.

**Hibernate không tự viết `equals`/`hashCode` cho entity của bạn.** Nếu entity không override, chúng thường thừa kế `Object.equals` và so sánh reference identity. Trong **một context**, điều này thường đủ khi so sánh cùng managed entity; giữa hai context, không đủ để diễn đạt “cùng hàng DB”.

### 11.1. Ví dụ so sánh hai instance khác context

~~~java
Book bookA = emA.find(Book.class, 101L);
Book bookB = emB.find(Book.class, 101L);

boolean sameObject = bookA == bookB; // false
boolean sameIdentifier =
        bookA.getId().equals(bookB.getId()); // true
~~~

Phép so sánh ID chỉ phù hợp sau khi ID đã được gán/biết. Nó **không có nghĩa** hai object đang cùng managed trong một context. Trong ứng dụng multitenant, phải xét thêm tenant và chính sách định danh nếu các tenant dùng không gian ID riêng.

### 11.2. Nguy cơ khi `equals()`/`hashCode()` dùng ID được sinh

Nếu dùng `@GeneratedValue` và entity mới chưa có ID, hai object transient có thể đều có `id == null`. Nếu `equals` chỉ so sánh ID mà không xử lý null, chúng có thể bị coi là bằng nhau sai. Nếu `hashCode` thay đổi từ lúc ID null sang lúc DB sinh ID, object đang ở `HashSet`/`HashMap` có thể mất khả năng được tìm đúng bucket.

Vì vậy một chiến lược equals/hashCode cho entity cần xử lý:

- Entity mới chưa có ID.
- ID được gán sau `persist`/flush.
- Proxy runtime type và subclass trong inheritance.
- So sánh giữa detached instance với managed instance.
- Tính ổn định của hash code khi object nằm trong hashed collection.

Không có một triển khai equals/hashCode áp dụng tối ưu cho mọi entity. Khi domain có **business key bất biến và duy nhất**, có thể cân nhắc dùng nó với quy tắc đầy đủ; nếu dùng generated ID, phải thiết kế xử lý transient và proxy cẩn thận. Một cách khác là so sánh **ID tường minh tại lớp service** khi mục tiêu chỉ là kiểm tra tham chiếu hàng.

### 11.3. `getClass()` và Hibernate proxies

Một entity lazy proxy có thể là class proxy kế thừa entity class. Vì vậy code `a.getClass() == b.getClass()` không phải lúc nào phù hợp để so entity identity qua proxies. Nếu viết equals có phân biệt type, cần chọn cách lấy entity class phù hợp với phiên bản Hibernate và xem tác động của việc khởi tạo proxy. Đừng dùng `instanceof` hoặc `getClass()` máy móc khi hierarchy kế thừa có nhiều subclass và business rules phức tạp.

## 12. Quan hệ giữa các entity và identity map

Giả sử có `Author` và nhiều `Book` cùng thuộc một tác giả:

~~~java
@Entity
class Author {
    @Id
    Long id;

    String name;
}

@Entity
class Book {
    @Id
    Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    Author author;
}
~~~

(Đây là **một mapping độc lập** chỉ dùng để minh họa association; không ghép nguyên văn với `Book` ở phần 2 mà không thống nhất các field.)

Khi tải các cuốn sách có `author_id = 5` trong cùng context, Hibernate không cần tạo một managed `Author` mới cho mỗi cuốn. Chúng có thể tham chiếu cùng managed target hoặc reference/proxy tương ứng với identity `(Author, 5)`. Điều này làm object graph thống nhất hơn: khi thay đổi một managed `Author` trong context, các đường tham chiếu tới cùng entity phản ánh cùng trạng thái managed.

Đừng suy ra rằng mỗi lần truy cập `book.getAuthor()` chắc chắn không phát SQL: có thể cần tải target lần đầu hoặc khởi tạo proxy. Identity guarantee nói về **object được quản lý**, không cam kết mọi association đã được fetch.

### 12.1. Join result trùng hàng và thống nhất object graph

Với query `join fetch` từ `Author` sang nhiều `Book`, cùng một tác giả có thể xuất hiện trên nhiều dòng SQL. Hibernate cần tập hợp collection thành những managed child objects và giữ root author identity duy nhất trong context. Mỗi quan hệ nhất quán được xây trên identity map và collection state của ORM, không phải do kết quả SQL đã tự là một object graph.

## 13. Khóa ghép, natural ID và ID theo tenant

### 13.1. Khóa ghép

Không phải mọi entity dùng `Long id`. Ví dụ entity `OrderLine` có khóa ghép `(orderId, lineNumber)`:

~~~java
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineId implements Serializable {
    private Long orderId;
    private int lineNumber;

    protected OrderLineId() {}

    public OrderLineId(Long orderId, int lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineId that)) return false;
        return lineNumber == that.lineNumber
                && Objects.equals(orderId, that.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}

@Entity
public class OrderLine {
    @EmbeddedId
    private OrderLineId id;

    @Column(nullable = false)
    private String sku;
}
~~~

Đoạn này dùng các import `jakarta.persistence.Embeddable`, `Entity`, `EmbeddedId`, `Column`. Ở đây `OrderLine` có persistence identity theo **hai giá trị khóa**. Hai instance `OrderLineId` riêng biệt nhưng cùng `orderId` và `lineNumber` phải thể hiện cùng **giá trị khóa** theo equals/hashCode; Hibernate dùng mapping ID để định vị entity.

Quy tắc “một entity theo một định danh” vẫn áp dụng, nhưng **định danh là một tuple**, không phải một số đơn.

### 13.2. Natural ID

Giả sử `Book` còn có mã ISBN duy nhất. Hibernate hỗ trợ metadata natural ID như `@NaturalId`, nhưng natural ID **không tự thay thế primary key** của entity identity map. Nếu ISBN có thể đổi, Hibernate có cơ chế quản lý natural ID mutable theo cấu hình; còn identity managed căn bản vẫn dựa trên entity identifier.

Hai cuốn sách có ISBN trùng do dữ liệu lỗi nhưng ID khác nhau không tự trở thành cùng object. Cần unique constraint và quy tắc nghiệp vụ để ngăn trùng natural key.

### 13.3. Multitenancy

Nếu hai tenant cùng có book ID 101 nhưng đó là hai sách khác nhau, hệ thống phải định nghĩa cách tách dữ liệu và session theo tenant. Hibernate multitenancy có cơ chế chọn tenant ở session/factory/mapping tùy mô hình. Một context không phải nơi trộn tùy tiện entity của nhiều tenant; identity guarantee không làm biến mất nhu cầu đảm bảo **tenant isolation** bằng cấu hình và schema phù hợp.

## 14. Persistence Context tồn tại bao lâu?

Phạm vi context quyết định **thời gian identity guarantee có hiệu lực** và chi phí giữ managed state.

| Mô hình | Đặc điểm | Tác động |
| --- | --- | --- |
| Session/transaction theo unit of work | Mở context cho một nghiệp vụ, flush/commit và kết thúc | Dễ hiểu, giảm stale state và memory growth |
| Session theo HTTP request / Open Session in View | Context có thể sống đến lúc response hoàn tất | Lazy loading trong tầng view có thể phát SQL bất ngờ |
| Extended persistence context | Context sống qua nhiều transaction theo workflow stateful | Identity kéo dài nhưng stale state/concurrency khó kiểm soát |
| Batch processing theo chunk | Context và transaction quản lý một lượng entity có giới hạn | Giữ identity trong chunk, giảm áp lực bộ nhớ |
| Một context duy nhất cho toàn ứng dụng | Session sống rất lâu, bị dùng nhiều request/luồng | **Không phù hợp**: stale state, memory, thread safety, resource leaks |

Với web service dùng Spring Data JPA, một phương thức `@Transactional` thường đóng vai trò ranh giới để một EntityManager/persistence context tham gia transaction hiện hành. Không nên lưu một `Session` thực ở singleton rồi dùng cho tất cả request.

### 14.1. Spring `@PersistenceContext` và proxy

~~~java
@Service
public class BookService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void renameBook(long id, String title) {
        Book book = em.find(Book.class, id);
        if (book == null) {
            throw new IllegalArgumentException("Book not found: " + id);
        }

        book.rename(title);
    }
}
~~~

Các import tương ứng: `jakarta.persistence.EntityManager`, `jakarta.persistence.PersistenceContext`, `org.springframework.stereotype.Service` và `org.springframework.transaction.annotation.Transactional`.

Trong cách tích hợp Spring JPA thông thường, field được tiêm qua `@PersistenceContext` có thể là **shared EntityManager proxy** chuyển lời gọi tới EntityManager gắn với transaction hiện tại. Điều này **không** có nghĩa cùng một persistence context thật được chia sẻ giữa mọi request. Identity guarantee vẫn xét theo EntityManager/context thực được dùng để xử lý từng unit of work.

Nếu method `@Transactional` được gọi nội bộ trong cùng bean (self-invocation), proxy transaction có thể không intercept như kỳ vọng. Cần hiểu ranh giới AOP/transaction của framework, không dựa vào tên annotation như một bảo đảm tuyệt đối.

## 15. First-level cache và stale state

Giả sử Context A tải `Book#101`, sau đó một transaction B dùng native SQL hoặc session khác đổi title. Nếu Context A gọi lại:

~~~java
Book again = emA.find(Book.class, 101L);
~~~

nó có thể nhận cùng managed object đang giữ state cũ, vì identity map đã có entity đó. **Không tự đọc lại DB chỉ vì `find` được gọi lần nữa.**

### 15.1. Chủ động `refresh()`

~~~java
Book book = em.find(Book.class, 101L);

// Khi thật sự cần đồng bộ từ DB:
em.refresh(book);
~~~

`refresh` yêu cầu tải lại trạng thái tương ứng theo ngữ nghĩa JPA/Hibernate, nhưng cần cân nhắc transaction, lock, cascading refresh và việc ghi đè các thay đổi chưa flush. Không gọi refresh mọi entity như một thói quen: nó tăng DB round trip và có thể làm mất trạng thái local cần xử lý.

### 15.2. Bulk update và native SQL đi ngoài identity map

~~~java
em.createMutationQuery(
        "update Book b set b.title = :title where b.id = :id"
    )
    .setParameter("title", "Bulk title")
    .setParameter("id", 101L)
    .executeUpdate();
~~~

Bulk HQL DML đi trực tiếp xuống database theo semantics của bulk query. Một entity `Book#101` đã managed trong context có thể vẫn giữ title cũ. Native SQL và các đường ghi ngoài Hibernate cũng có thể gây stale state.

Khi phải dùng bulk operation, hãy quyết định ranh giới transaction, flush trước thao tác, sau đó `clear()` hoặc `refresh()` các entity liên quan theo trường hợp. Đừng tự động tiếp tục dựa vào managed object cũ sau bulk DML mà không hiểu trạng thái.

### 15.3. `flush()` không làm mới dữ liệu đã cache

`flush()` đồng bộ thay đổi từ persistence context **xuống** DB trong transaction; nó không có nghĩa tải lại mọi row mới nhất **từ** DB. `clear()` detaches mọi entity và xóa trạng thái đang quản lý; `refresh()` tải lại entity cụ thể. Ba thao tác khác trách nhiệm.

## 16. Memory và vòng đời dài

Identity map giữ managed entity khi context tồn tại. Nếu import 200.000 bản ghi trong một session thông thường, Hibernate có thể phải giữ nhiều entry, snapshot và action queue, dẫn đến bộ nhớ tăng đáng kể.

Một kỹ thuật batch cơ bản:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try {
        int count = 0;
        for (ImportRow row : inputRows) {
            session.persist(toBook(row));

            if (++count % 50 == 0) {
                session.flush();
                session.clear();
            }
        }

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
~~~

`ImportRow`, `inputRows`, `toBook` và các Hibernate imports là thành phần minh họa. `flush/clear` định kỳ giúp giới hạn số entity managed nhưng **không tự chia một transaction thành nhiều transaction**: tất cả vẫn có thể rollback cùng nhau. Với công việc dài, chia thành nhiều chunk có transaction riêng nếu yêu cầu nghiệp vụ cho phép; mỗi chunk có identity map riêng.

Trong Hibernate, `StatelessSession` cung cấp API không có persistence context/first-level cache theo semantics của `Session` thông thường; phù hợp một số workload batch nhưng có sự khác biệt về dirty checking, cascade và collection management. Không dùng `StatelessSession` khi ứng dụng cần dựa vào quy tắc “mỗi identity một managed entity trong persistence context”, vì nó không quản lý context theo cách đó.

## 17. Các lỗi thường gặp liên quan entity identity

| Dấu hiệu | Nguyên nhân có thể | Điều nên xem xét |
| --- | --- | --- |
| `find(Book.class, id)` trả cùng reference cũ | Identity map đang giữ managed Book | Context scope, refresh/clear/reload |
| Truy vấn HQL lại vẫn chạy SQL | First-level cache không phải query result cache | SQL query, projection, query cache riêng |
| `NonUniqueObjectException` / `EntityExistsException` | Hai object Java khác nhau đang được attach/persist với cùng identity | `persist`, Hibernate `update`/`saveOrUpdate` (nếu API/version hỗ trợ), ID assignment |
| `merge()` không thay đổi object tham số thành managed | Merge copy state và trả managed result | Sử dụng biến trả về từ `merge` |
| Cập nhật trên object detached không được flush | Entity đã detach/clear/close hoặc do context khác tải | `contains`, boundary transaction, merge/load-and-patch |
| Sau `clear()`, tải lại được object khác | Managed trước đó đã bị detach | Ranh giới identity thay đổi hợp lệ |
| Hai request tải cùng ID nhưng không cùng reference | Hai context độc lập | Identity guarantee chỉ trong từng context |
| Entity stale sau native SQL/bulk update | Persistence context không tự đồng bộ với DML ngoài lifecycle | Flush/refresh/clear theo nhu cầu |
| `equals/hashCode` gây mất phần tử trong `HashSet` | Hash code thay đổi khi generated ID từ null thành giá trị | Thiết kế equality cho transient/managed/detached |
| Lỗi mất cập nhật dù context không trùng instance | Hai transaction cùng sửa hàng DB | `@Version`, locking, isolation |
| Bộ nhớ tăng khi batch lâu | Persistence context giữ quá nhiều managed entity | Chunk, `flush/clear`, scope ngắn |
| Proxy có class khác entity class | Hibernate tạo lazy proxy | Hành vi `getClass`, equals, lazy initialization |

**Sau exception JDBC/ORM khi flush/commit**, rollback transaction và bỏ `Session`/`EntityManager` đã gặp lỗi. Không cố sửa vài object rồi tiếp tục sử dụng context lỗi như thể state và action queue vẫn an toàn.

## 18. Ba tình huống thiết kế thường gặp

### 18.1. Controller đọc lại cùng entity qua nhiều repository

Một application service trong một transaction có thể gọi `BookRepository.findById(101)`, sau đó một method khác trong cùng persistence context lại tải `Book#101`. Cả hai thao tác có thể nhận cùng managed instance; nếu method đầu sửa title, method sau có thể thấy title đã sửa dù chưa flush SQL.

Đây là hành vi hợp lý cho một unit of work. Nhưng nếu hai repository tự mở hai `EntityManager` khác nhau, identity guarantee **không nối qua hai context**. Thiết kế transaction boundary tại service để giữ ý nghĩa thống nhất.

### 18.2. Một REST request gửi Book cùng ID ở hai vị trí JSON

Giả sử payload chứa cùng ID 101 trong hai nested object nhưng title khác nhau. Việc deserialize JSON tạo hai Java objects **không có nghĩa cả hai sẽ trở thành managed**. Nếu merge cả graph, ứng dụng có thể gặp xung đột entity copies hoặc giá trị ghi đè.

Tốt hơn: deserialize vào command DTO, kiểm tra ID xuất hiện trùng hay có dữ liệu mâu thuẫn, sau đó load **một managed Book#101** trong transaction và áp dụng thay đổi đã được nghiệp vụ chấp nhận.

### 18.3. Hai worker xử lý Book#101 song song

Mỗi worker nên có session/transaction riêng. Chúng không chia sẻ cùng managed instance, dù cùng ID. Concurrency ở DB được xử lý bằng version, unique constraint, locking và retry có giới hạn. Không chuyển một `Session` hoặc entity mutable đang managed qua các thread như cách đồng bộ công việc.

## 19. Bài tập tự kiểm tra

**Bài 1.** Trong một `EntityManager` đang mở, gọi `find(Book.class, 101L)` hai lần, không `clear/detach`. Nếu hàng tồn tại, `a == b` là gì? Vì sao?

**Bài 2.** Gọi `em.clear()`, rồi tải lại ID 101. Object trước đó còn tham gia dirty checking không?

**Bài 3.** Hai `EntityManager` cùng tải ID 101. Vì sao `a != b` vẫn không vi phạm quy tắc identity map? Hai transaction cùng rename thì cần thêm cơ chế nào?

**Bài 4.** `Book detached` được truyền vào `merge()`. Đối tượng nào được Hibernate quản lý tiếp theo: tham số hay giá trị trả về?

**Bài 5.** Sau một truy vấn bulk update `Book#101`, EntityManager vẫn giữ managed Book với title cũ. Vì sao `find` lại có thể trả title cũ và thao tác nào phù hợp để tải lại?

**Bài 6.** Một entity có natural key ISBN và primary key `id`. Nếu ISBN trùng mà `id` khác nhau, Hibernate identity map có coi chúng là một entity không?

**Bài 7.** Vì sao `equals()` dựa vào generated ID có thể phá vỡ `HashSet` nếu hash code thay đổi sau `persist`?

Gợi ý: (1) cùng managed instance, `true`; (2) object cũ detached, không tiếp tục dirty checking; (3) context riêng, cần optimistic/pessimistic locking hoặc policy concurrency; (4) giá trị trả về; (5) bulk DML không đồng bộ managed state, dùng `refresh/clear` có kiểm soát; (6) không, identity căn bản dựa vào entity identifier; (7) hashed collection cần hash code ổn định theo thời gian object nằm trong collection.

## 20. Ghi nhớ và tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): các phần về persistence context, entity states, flushing, working with detached entities và caching.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): hợp đồng `EntityManager`, entity identity, `find`, `getReference`, `persist`, `merge`, `detach`, `clear`, `refresh` và transaction-scoped/extended persistence contexts.
- [Hibernate ORM Documentation](https://hibernate.org/orm/documentation/): chọn user guide và migration guide cho đúng phiên bản Hibernate đang chạy.

**Quy tắc cần nắm:** Hibernate quản lý **một đại diện managed cho một entity identity trong mỗi persistence context**. Nó cho phép nhiều đoạn mã trong cùng unit of work làm việc với trạng thái entity nhất quán và là nền tảng cho dirty checking. Khi context bị đóng hoặc entity bị detach, object Java vẫn tồn tại nhưng không còn managed; context khác có thể tạo một đại diện mới. Quy tắc này **không thay thế** optimistic locking giữa transaction, cũng không bảo đảm query nào cũng không phát SQL hay dữ liệu trong context tự cập nhật theo DB.
