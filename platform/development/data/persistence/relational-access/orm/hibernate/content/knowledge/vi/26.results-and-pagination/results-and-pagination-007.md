# Tách truy vấn đếm khỏi truy vấn dữ liệu khi hình dạng join khác nhau

Khi phân trang một danh sách entity bằng Hibernate, giao diện thường cần hai loại kết quả: **những bản ghi trên trang hiện tại** và **tổng số bản ghi phù hợp với bộ lọc**. Vì thế, ứng dụng hay chạy hai câu truy vấn:

1. **Data query:** chọn dữ liệu để hiển thị, có thứ tự và có giới hạn trang.
2. **Count query:** đếm tổng số *đối tượng logic* khớp bộ lọc, không bị giới hạn trang.

Tưởng như có thể lấy data query, thay `select b` bằng `select count(b)` và bỏ `order by`. Tuy nhiên, khi data query có `JOIN` — đặc biệt `JOIN FETCH` hoặc join tới collection `@OneToMany`/`@ManyToMany` — phép biến đổi cơ học này rất dễ sai. Một entity có thể xuất hiện trên **nhiều dòng SQL**; một join chỉ phục vụ tải dữ liệu không nhất thiết cần xuất hiện trong count query; còn một join phục vụ **lọc** thì không thể bỏ nếu làm thay đổi tập entity đủ điều kiện.

**Nguyên tắc:** count query phải giữ **cùng ý nghĩa bộ lọc** với data query, nhưng **không bắt buộc có cùng hình dạng SQL hay cùng tập JOIN**. Tối ưu truy vấn đếm bắt đầu bằng câu hỏi “đếm cái gì?” chứ không phải “copy câu SQL nào?”.

Bài học thuộc chương **Kết quả và phân trang**, dùng Hibernate ORM 6.x, HQL/JPQL, Criteria API và ví dụ Spring Data JPA. Những đoạn SQL nhằm minh họa cơ chế quan hệ, không cam kết Hibernate render giống hệt trên mọi `Dialect`.

## 1. Hai truy vấn phục vụ hai hợp đồng khác nhau

Giả sử một trang danh sách sách hiển thị tối đa 20 cuốn, sắp xếp theo ngày tạo. API cần trả:

~~~json
{
  "content": [
    {"id": 101, "title": "Hibernate Basics"},
    {"id": 102, "title": "JPA in Practice"}
  ],
  "page": 0,
  "size": 20,
  "totalElements": 137,
  "totalPages": 7
}
~~~

`content` là những cuốn trên trang hiện tại; `totalElements` là **số cuốn sách phù hợp với tất cả điều kiện tìm kiếm trước khi phân trang**. Tổng số 137 không phải số dòng SQL nhận được từ truy vấn hiển thị trang 0 và cũng không phải số phần tử trong `content`.

### 1.1. Data query

Một data query có thể phải:

- Chọn entity hoặc DTO cần hiển thị.
- Lọc theo trạng thái, từ khóa, tác giả, tenant, quyền truy cập.
- JOIN bảng liên quan để lọc hoặc lấy dữ liệu.
- FETCH association mà UI thật sự cần.
- Sắp xếp ổn định bằng `ORDER BY`.
- Áp `setFirstResult` và `setMaxResults` hoặc một cơ chế keyset/cursor tương ứng.

Ví dụ HQL:

~~~java
List<Book> books = em.createQuery(
        "select b from Book b " +
        "where b.status = :status " +
        "order by b.createdAt desc, b.id desc",
        Book.class
    )
    .setParameter("status", BookStatus.PUBLISHED)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

### 1.2. Count query

Một count query chỉ cần xác định số root entities phù hợp với bộ lọc:

~~~java
Long total = em.createQuery(
        "select count(b) from Book b " +
        "where b.status = :status",
        Long.class
    )
    .setParameter("status", BookStatus.PUBLISHED)
    .getSingleResult();
~~~

Không cần `ORDER BY`, `JOIN FETCH` hay load entity graph cho phép đếm này. `count(...)` trả `Long` trong JPA, kể cả khi bảng nhỏ.

### 1.3. Hai câu hỏi riêng

| Câu hỏi | Data query | Count query |
| --- | --- | --- |
| Kết quả đại diện cho gì? | Entity/DTO trên trang | Tổng số phần tử logic đủ điều kiện |
| Có chọn dữ liệu UI cần hiển thị không? | Có | Không |
| Có `ORDER BY` không? | Có, cần thứ tự ổn định | Thường không |
| Có limit/offset không? | Có nếu dùng offset pagination | Không |
| Có fetch association không? | Có thể | Không |
| JOIN chỉ để fetch có cần không? | Có thể | Không |
| JOIN dùng để lọc có cần không? | Có thể | Giữ semantics lọc, có thể viết lại bằng `EXISTS` |
| Có thể dùng `count(b)` trực tiếp? | Không phải mục đích | Chỉ khi mỗi root được đếm đúng một lần |

## 2. Mô hình dữ liệu minh họa

Một nhà xuất bản có nhiều sách, mỗi sách có nhiều tag. Màn hình cần lọc theo trạng thái và tiền tố tag, đồng thời hiển thị nhà xuất bản.

~~~java
import jakarta.persistence.*;
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "books")
public class Book {
    @Id
    private Long id;

    @Column(nullable = false)
    private String title;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private BookStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "publisher_id")
    private Publisher publisher;

    @ElementCollection
    @CollectionTable(
        name = "book_tags",
        joinColumns = @JoinColumn(name = "book_id")
    )
    @Column(name = "tag", nullable = false)
    private Set<String> tags = new HashSet<>();

    protected Book() {}

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public Instant getCreatedAt() { return createdAt; }
    public Publisher getPublisher() { return publisher; }
    public Set<String> getTags() { return tags; }
}

@Entity
@Table(name = "publishers")
public class Publisher {
    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Publisher() {}
    public String getName() { return name; }
}

public enum BookStatus {
    DRAFT, PUBLISHED, ARCHIVED
}
~~~

Mỗi public type được đặt trong file Java riêng. Để tập trung vào phân trang, ví dụ không trình bày constructor nghiệp vụ, setters và cấu hình tạo schema.

Các bảng quan hệ tương ứng về mặt khái niệm:

~~~sql
create table publishers (
    id bigint primary key,
    name varchar(255) not null
);

create table books (
    id bigint primary key,
    title varchar(255) not null,
    status varchar(20) not null,
    created_at timestamp not null,
    publisher_id bigint references publishers(id)
);

create table book_tags (
    book_id bigint not null references books(id),
    tag varchar(255) not null,
    primary key (book_id, tag)
);
~~~

Ý nghĩa quan trọng:

- `books` có **một dòng cho mỗi Book**.
- `publishers` là quan hệ **to-one** từ Book.
- `book_tags` là quan hệ **to-many** từ Book; một Book có thể tạo ra nhiều dòng khi join tag.

## 3. Một join to-many có thể nhân số dòng

Giả sử ba cuốn sách cùng trạng thái PUBLISHED:

| Book ID | Title | Tags phù hợp với tiền tố `java%` |
| --- | --- | --- |
| 10 | Java ORM | `java-jpa`, `java-hibernate` |
| 11 | Java Concurrency | `java-threads` |
| 12 | Java Testing | `java-junit` |

Truy vấn SQL:

~~~sql
select b.id, b.title, t.tag
from books b
join book_tags t on t.book_id = b.id
where b.status = 'PUBLISHED'
  and t.tag like 'java%';
~~~

Trả về:

| b.id | b.title | t.tag |
| --- | --- | --- |
| 10 | Java ORM | java-jpa |
| 10 | Java ORM | java-hibernate |
| 11 | Java Concurrency | java-threads |
| 12 | Java Testing | java-junit |

Đây là **4 dòng SQL nhưng chỉ có 3 Book**.

Nếu viết:

~~~sql
select count(*)
from books b
join book_tags t on t.book_id = b.id
where b.status = 'PUBLISHED'
  and t.tag like 'java%';
~~~

kết quả là `4`: nó đếm **số dòng join**, không đếm số Book.

Trong HQL, `count(b)` sau một join tương đương về vấn đề ngữ nghĩa: mỗi dòng quan hệ sau join đóng góp một lần vào phép đếm.

~~~java
// SAI nếu mục tiêu là số Book duy nhất.
Long total = em.createQuery(
        "select count(b) from Book b " +
        "join b.tags tag " +
        "where b.status = :status " +
        "and tag like :prefix",
        Long.class
    )
    .setParameter("status", BookStatus.PUBLISHED)
    .setParameter("prefix", "java%")
    .getSingleResult();
~~~

### 3.1. Điều cần đếm là root entity duy nhất

Nếu hợp đồng API là “danh sách Book”, `totalElements` phải là **số Book khác nhau** thỏa bộ lọc, không phải số `(Book, Tag)` pairs.

Có hai hướng chính:

1. Giữ join và dùng `COUNT(DISTINCT root.id)`.
2. Viết lại điều kiện liên quan collection thành `EXISTS` để mỗi Book chỉ được đếm một lần.

Cách thứ hai còn có lợi vì không cần tạo tập dòng join ở outer query để đếm.

## 4. Cách A — COUNT(DISTINCT root.id)

Giữ điều kiện join như data query nhưng đếm định danh duy nhất:

~~~java
Long total = em.createQuery(
        "select count(distinct b.id) from Book b " +
        "join b.tags tag " +
        "where b.status = :status " +
        "and tag like :prefix",
        Long.class
    )
    .setParameter("status", BookStatus.PUBLISHED)
    .setParameter("prefix", "java%")
    .getSingleResult();
~~~

SQL minh họa:

~~~sql
select count(distinct b.id)
from books b
join book_tags t on t.book_id = b.id
where b.status = 'PUBLISHED'
  and t.tag like 'java%';
~~~

Kết quả là `3` trong bộ dữ liệu ví dụ.

### 4.1. DISTINCT phải áp dụng lên đúng định danh

`count(distinct b.id)` đếm các Book IDs duy nhất. Nó không giống:

~~~sql
count(distinct t.tag)
~~~

vì truy vấn thứ hai đếm số **giá trị tag** khác nhau, không phải số Book. Chỉ cần chọn sai biểu thức bên trong `DISTINCT` là tổng số đã mang ý nghĩa khác.

Với root có khóa chính ghép, cú pháp `COUNT(DISTINCT tuple)` có khả năng portable hạn chế và khác nhau giữa DBMS. Khi khó biểu diễn composite identifier bằng phép distinct đơn giản, có thể ưu tiên `EXISTS` hoặc đếm từ một derived relation có đúng một dòng cho mỗi root theo khả năng DBMS.

### 4.2. Count distinct có luôn tối ưu nhất?

Không. `COUNT(DISTINCT ...)` có thể yêu cầu DBMS hash/sort/deduplicate một lượng lớn dòng join. Chi phí phụ thuộc index, độ chọn lọc của predicate và query planner.

Trong truy vấn lọc bằng sự tồn tại của phần tử con, `EXISTS` nhiều khi mô tả bài toán tự nhiên hơn và cho phép optimizer dùng semi-join. Không khẳng định `EXISTS` luôn nhanh hơn; cần xem execution plan trên DBMS thật.

### 4.3. SELECT DISTINCT và COUNT DISTINCT không phải cùng thao tác

Data query:

~~~java
List<Book> page = em.createQuery(
        "select distinct b from Book b " +
        "join b.tags tag " +
        "where b.status = :status and tag like :prefix " +
        "order by b.createdAt desc, b.id desc",
        Book.class
    )
    .setParameter("status", BookStatus.PUBLISHED)
    .setParameter("prefix", "java%")
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
~~~

Ở đây `select distinct b` diễn đạt kết quả là những Book không trùng. Count query phải chọn `count(distinct b.id)` (hoặc phép đếm tương đương), **không** phải `count(b)`.

Dù Hibernate có cơ chế de-duplicate entity instances trong một số tình huống fetch join, việc xử lý duplicate ở ORM **không thay thế** phép đếm đúng tại database. Đồng thời, SQL phân trang phải giới hạn trên các root phù hợp chứ không chỉ cắt các dòng join bị nhân lên.

## 5. Cách B — EXISTS để giữ một dòng cho mỗi Book

Với câu hỏi “Book có ít nhất một tag bắt đầu bằng java không?”, có thể dùng correlated subquery:

~~~sql
select b.id, b.title
from books b
where b.status = 'PUBLISHED'
  and exists (
      select 1
      from book_tags t
      where t.book_id = b.id
        and t.tag like 'java%'
  );
~~~

Ở outer query, mỗi Book được xét **một lần**. Subquery kiểm tra sự tồn tại, không biến một Book thành nhiều rows.

HQL tương ứng:

~~~java
Long total = em.createQuery(
        """
        select count(b)
        from Book b
        where b.status = :status
          and exists (
              select 1
              from Book candidate
              join candidate.tags tag
              where candidate.id = b.id
                and tag like :prefix
          )
        """,
        Long.class
    )
    .setParameter("status", BookStatus.PUBLISHED)
    .setParameter("prefix", "java%")
    .getSingleResult();
~~~

Không cần `DISTINCT` trong outer count: mỗi Book thỏa điều kiện tồn tại được đếm một lần.

### 5.1. Data query có thể dùng cùng predicate EXISTS

~~~java
List<Book> page = em.createQuery(
        """
        select b
        from Book b
        left join fetch b.publisher
        where b.status = :status
          and exists (
              select 1
              from Book candidate
              join candidate.tags tag
              where candidate.id = b.id
                and tag like :prefix
          )
        order by b.createdAt desc, b.id desc
        """,
        Book.class
    )
    .setParameter("status", BookStatus.PUBLISHED)
    .setParameter("prefix", "java%")
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
~~~

Data query có `left join fetch b.publisher` để giao diện có tên nhà xuất bản mà không phải tải từng Publisher sau đó. Count query **không cần fetch publisher**, vì tên nhà xuất bản không ảnh hưởng điều kiện đủ tiêu chuẩn trong ví dụ.

Hai query có SQL shape khác nhau nhưng cùng logic lọc:

~~~mermaid
flowchart TD
    F["Bộ lọc chung: status + tồn tại tag phù hợp"] --> D["Data query"]
    F --> C["Count query"]
    D --> DF["LEFT JOIN FETCH Publisher (to-one)"]
    DF --> DP["ORDER BY + limit/offset"]
    DP --> R["List<Book> cho trang"]
    C --> CC["COUNT(Book), không FETCH, không ORDER BY"]
    CC --> T["Long totalElements"]
~~~

### 5.2. EXISTS thay đổi semantics khi nào?

Chỉ được thay một join thành `EXISTS` nếu nghiệp vụ là **tồn tại ít nhất một bản ghi liên quan**.

Ví dụ:

- “Book có ít nhất một tag bắt đầu bằng java”: `EXISTS` phù hợp.
- “Book có ít nhất một review được duyệt”: `EXISTS` phù hợp.
- “Đếm số review từng Book”: không thể chỉ dùng EXISTS rồi cho rằng đã tính số review.
- “Book phải có ít nhất hai tag java”: cần aggregate, subquery khác hoặc điều kiện nhóm thích hợp.
- “Book phải có tất cả các tag được yêu cầu”: một `EXISTS` đơn lẻ chỉ đảm bảo có ít nhất một tag, không đảm bảo tất cả.

Tách hình dạng query không có nghĩa được phép thay đổi điều kiện nghiệp vụ.

## 6. JOIN FETCH trong data query không được copy sang count query

Fetch join dùng để **khởi tạo association**, không phải để xác định số root entities phù hợp.

Ví dụ data query:

~~~java
List<Book> books = em.createQuery(
        "select b from Book b left join fetch b.publisher " +
        "where b.status = :status",
        Book.class
    )
    .setParameter("status", BookStatus.PUBLISHED)
    .getResultList();
~~~

Count query **không nên** là:

~~~java
// SAI: fetch join không có ý nghĩa cho scalar count.
Long total = em.createQuery(
        "select count(b) from Book b " +
        "left join fetch b.publisher " +
        "where b.status = :status",
        Long.class
    )
    .setParameter("status", BookStatus.PUBLISHED)
    .getSingleResult();
~~~

Trong Hibernate, fetch join yêu cầu owner entity được chọn trong kết quả để có đối tượng nhận association. Khi selection chỉ là `count(b)`, không có Book entity nào cần hydrate Publisher. Một query như vậy có thể bị Hibernate từ chối vì owner của fetch join không nằm trong select list.

Count đúng trong trường hợp này:

~~~java
Long total = em.createQuery(
        "select count(b) from Book b where b.status = :status",
        Long.class
    )
    .setParameter("status", BookStatus.PUBLISHED)
    .getSingleResult();
~~~

### 6.1. Phân biệt JOIN để lọc và JOIN để fetch

| Hình thức join | Công dụng | Có cần trong count query? |
| --- | --- | --- |
| `left join fetch b.publisher` | Tải Publisher cùng Book | Không, nếu không ảnh hưởng điều kiện lọc |
| `join b.publisher p where p.country = :x` | Lọc Book theo Publisher | Phải giữ semantics lọc, có thể dùng join/path/subquery |
| `join b.tags tag where tag like :x` | Lọc Book theo phần tử collection | Phải giữ semantics; `COUNT DISTINCT` hoặc `EXISTS` |
| `left join b.tags tag` không lọc, không dùng trong select | Có thể là join thừa | Nên bỏ khỏi count query nếu không làm đổi tập root |
| `join fetch b.tags` | Tải collection Book.tags | Không được dùng để count; data pagination còn có rủi ro riêng |

Một `INNER JOIN` dù “chỉ để fetch” cũng có thể loại root không có association tương ứng. Ví dụ `join fetch b.publisher` bỏ Book không có Publisher trong nhiều mapping/cấu hình. Nếu data query thật sự loại các root đó, count query cần phản ánh tập đủ điều kiện tương ứng hoặc data query nên dùng `LEFT JOIN FETCH` nếu nghiệp vụ không muốn loại root.

**Lấy cùng tập Book làm tiêu chuẩn**, không dựa đơn giản vào nhãn “fetch” để bỏ/giữ join.

## 7. To-one join và to-many join có chi phí đếm khác nhau

### 7.1. To-one join

Mỗi Book có nhiều nhất một Publisher. Một join qua association to-one hợp lệ thường không tạo nhiều dòng cho mỗi Book:

~~~java
Long total = em.createQuery(
        """
        select count(b)
        from Book b
        join b.publisher p
        where p.name like :publisherName
        """,
        Long.class
    )
    .setParameter("publisherName", "Open%")
    .getSingleResult();
~~~

`count(b)` phù hợp nếu mỗi Book tạo tối đa một result row trong query đó. Nhưng `INNER JOIN` loại những Book không có Publisher; muốn đếm cả Book không có Publisher, logic join/filter phải thay đổi theo nghiệp vụ.

### 7.2. To-many join

Một Book có nhiều tags; join có thể nhân dòng:

~~~java
Long total = em.createQuery(
        """
        select count(distinct b.id)
        from Book b join b.tags tag
        where tag like :prefix
        """,
        Long.class
    )
    .setParameter("prefix", "java%")
    .getSingleResult();
~~~

Không suy luận rằng `count(b)` luôn đúng chỉ vì Book dùng khóa chính duy nhất. Khóa chính của Book duy nhất trong bảng `books`; join tới `book_tags` có thể lặp Book nhiều lần trong result relation.

### 7.3. Nhiều joins to-many làm vấn đề nghiêm trọng hơn

Nếu Book có 4 tags phù hợp và 3 reviews phù hợp, join cả hai có thể tạo 4 × 3 = 12 SQL rows cho cùng một Book:

~~~sql
select b.id
from books b
join book_tags t on t.book_id = b.id
join reviews r on r.book_id = b.id
where t.tag like 'java%'
  and r.approved = true;
~~~

`count(*)` hoặc `count(b)` có thể bị thổi phồng mạnh. `count(distinct b.id)` sửa ý nghĩa đếm root nhưng DB vẫn có thể phải xử lý tích số joins. Hai predicate `EXISTS` riêng thường diễn đạt ý định “có tag phù hợp” **và** “có review được duyệt” rõ hơn:

~~~sql
select count(*)
from books b
where exists (
    select 1
    from book_tags t
    where t.book_id = b.id
      and t.tag like 'java%'
)
and exists (
    select 1
    from reviews r
    where r.book_id = b.id
      and r.approved = true
);
~~~

Kết quả logic vẫn là một lần cho mỗi Book. Cần chỉ số phù hợp trên foreign key/predicate columns để điều kiện tồn tại được thực thi hiệu quả.

## 8. COUNT DISTINCT không chữa được mọi lỗi phân trang

Giả sử count query đã đúng:

~~~sql
select count(distinct b.id)
from books b
join book_tags t on t.book_id = b.id
where t.tag like 'java%';
~~~

Nhưng data query lại fetch join toàn bộ collection:

~~~java
List<Book> books = em.createQuery(
        """
        select distinct b
        from Book b
        left join fetch b.tags
        where b.status = :status
        order by b.id
        """,
        Book.class
    )
    .setParameter("status", BookStatus.PUBLISHED)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

**Vấn đề khác xuất hiện:** SQL join collection có nhiều dòng cho cùng root; database `LIMIT 20` theo raw join rows có thể cắt ngang một collection hoặc trả ít hơn 20 Book duy nhất. Hibernate có thể xử lý pagination trên collection fetch join trong bộ nhớ, khiến truy vấn tải toàn bộ tập kết quả rồi mới cắt trang, gây ảnh hưởng lớn tới hiệu năng.

Trong Hibernate có tùy chọn như `hibernate.query.fail_on_pagination_over_collection_fetch=true` để báo lỗi thay vì âm thầm phân trang trong bộ nhớ với kiểu query này. Tên cấu hình/behavior cần đối chiếu đúng phiên bản đang chạy.

**Count đúng không làm data query đúng.** Hai vấn đề phải được giải quyết riêng:

1. Count tính đúng số root đủ điều kiện.
2. Data query phân trang đúng root, không làm nổ số dòng hoặc tải quá nhiều collection.

### 8.1. Với to-one fetch join, rủi ro khác

Fetch join một association to-one thường không nhân số root theo cách collection join làm. Ví dụ `left join fetch b.publisher` thường có thể kết hợp với offset/limit mà không gặp vấn đề pagination-over-collection-fetch. Tuy nhiên vẫn cần xem SQL, optional association, filter và query plan thực tế.

## 9. Chiến lược hai bước khi cần fetch collection cho trang

Nếu UI cần hiển thị toàn bộ tags của mỗi Book, thường không nên dùng một query vừa phân trang vừa collection fetch join. Một cách khác là **phân trang ID trước**, sau đó tải graph cho đúng các ID.

### 9.1. Bước 1: lấy IDs theo filter và order

~~~java
List<Long> ids = em.createQuery(
        """
        select b.id
        from Book b
        where b.status = :status
          and exists (
              select 1
              from Book candidate
              join candidate.tags tag
              where candidate.id = b.id
                and tag like :prefix
          )
        order by b.createdAt desc, b.id desc
        """,
        Long.class
    )
    .setParameter("status", BookStatus.PUBLISHED)
    .setParameter("prefix", "java%")
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
~~~

Bước này chọn **một ID cho mỗi Book**, không fetch collection, nên offset/limit áp lên tập root đúng hình dạng mong đợi.

### 9.2. Bước 2: fetch graph cho các IDs của trang

~~~java
if (ids.isEmpty()) {
    return List.of();
}

List<Book> fetched = em.createQuery(
        """
        select distinct b
        from Book b
        left join fetch b.publisher
        left join fetch b.tags
        where b.id in :ids
        """,
        Book.class
    )
    .setParameter("ids", ids)
    .getResultList();
~~~

Không áp `setFirstResult`/`setMaxResults` ở **bước 2**: số Book đã được giới hạn bởi ID page. `select distinct b` giúp diễn đạt rằng output root không được lặp do collection join; Hibernate 6 cũng có cơ chế loại duplicate entity result cho fetch joins.

### 9.3. Bảo toàn thứ tự trang

`IN (:ids)` không bảo đảm DB trả kết quả theo thứ tự IDs ban đầu. Reorder trong Java:

~~~java
Map<Long, Book> byId = fetched.stream()
        .collect(Collectors.toMap(
                Book::getId,
                Function.identity(),
                (first, ignored) -> first
        ));

List<Book> ordered = ids.stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .toList();
~~~

Đoạn code yêu cầu imports `java.util.*`, `java.util.function.Function` và `java.util.stream.Collectors`. Nếu có Book bị xóa hoặc thay đổi giữa hai query dưới mức isolation cho phép snapshot thay đổi, `byId.get(id)` có thể null; ứng dụng phải quyết định cách xử lý theo hợp đồng nhất quán của trang.

### 9.4. Bước 3: chạy count query riêng

~~~java
Long total = em.createQuery(
        """
        select count(b)
        from Book b
        where b.status = :status
          and exists (
              select 1
              from Book candidate
              join candidate.tags tag
              where candidate.id = b.id
                and tag like :prefix
          )
        """,
        Long.class
    )
    .setParameter("status", BookStatus.PUBLISHED)
    .setParameter("prefix", "java%")
    .getSingleResult();
~~~

Đây là ba truy vấn có mục đích khác nhau:

~~~text
1. ID page query       -> [101, 105, 109, ...]
2. Entity graph query  -> Book + publisher + tags cho các IDs
3. Count query         -> tổng Book thỏa cùng bộ lọc
~~~

Ba query không nhất thiết chạy trên ba transaction. Với đọc theo use case, thường đặt chúng trong một transaction đọc để kiểm soát vòng đời persistence context. Nhưng một transaction `READ COMMITTED` không tự cam kết ba query nhìn thấy cùng snapshot dữ liệu tại mọi DBMS; xem phần nhất quán bên dưới.

## 10. Vì sao không tạo count query từ data query bằng replace?

Một cách xử lý nguy hiểm:

~~~java
String dataHql =
        "select distinct b from Book b " +
        "left join fetch b.publisher " +
        "join b.tags t " +
        "where t like :prefix " +
        "order by b.createdAt desc";

String countHql = dataHql
        .replace("select distinct b", "select count(b)")
        .replace("order by b.createdAt desc", "");
~~~

Nó có hàng loạt lỗi:

- `left join fetch b.publisher` vẫn tồn tại, không hợp với scalar count.
- `count(b)` có thể đếm trùng vì join tags.
- Query phức tạp có thể có subquery/`ORDER BY` ở mức khác, khiến replace sai.
- Alias hoặc đoạn select có thể xuất hiện nhiều lần.
- Khi thêm `GROUP BY`, `HAVING`, union hoặc constructor expression, phép replace càng thiếu tin cậy.
- Một chỉnh sửa nhỏ trong data query có thể làm count sai mà không lộ trong test ít dữ liệu.

**Cách đúng:** định nghĩa count query riêng theo semantics hoặc dùng cơ chế xây query có cấu trúc để tạo hai Criteria trees độc lập.

Nếu framework tự sinh count query, vẫn phải hiểu giới hạn của công cụ với fetch join, to-many join, distinct, group by và constructor projection.

## 11. Dùng HQL riêng cho data và count query

Có thể viết hai query tường minh, cùng danh sách tham số:

~~~java
public record BookPage(
        List<Book> content,
        long totalElements,
        int page,
        int size
) {}

public BookPage findPage(
        EntityManager em,
        BookStatus status,
        String tagPrefix,
        int page,
        int size
) {
    if (page < 0 || size < 1 || size > 100) {
        throw new IllegalArgumentException(
                "Invalid page or page size"
        );
    }

    long offset = (long) page * size;
    if (offset > Integer.MAX_VALUE) {
        throw new IllegalArgumentException("Offset is too large");
    }

    String predicate = """
        b.status = :status
        and exists (
            select 1 from Book candidate
            join candidate.tags tag
            where candidate.id = b.id
              and tag like :prefix
        )
        """;

    List<Book> content = em.createQuery(
            "select b from Book b " +
            "left join fetch b.publisher " +
            "where " + predicate +
            " order by b.createdAt desc, b.id desc",
            Book.class
        )
        .setParameter("status", status)
        .setParameter("prefix", tagPrefix)
        .setFirstResult((int) offset)
        .setMaxResults(size)
        .getResultList();

    Long total = em.createQuery(
            "select count(b) from Book b where " + predicate,
            Long.class
        )
        .setParameter("status", status)
        .setParameter("prefix", tagPrefix)
        .getSingleResult();

    return new BookPage(content, total, page, size);
}
~~~

Trong ví dụ trên, `predicate` là một template **cố định do developer viết**, không phải HQL fragment do client gửi. Giá trị `status` và `tagPrefix` vẫn được bind. Khi tìm chuỗi literal thay vì wildcard, cần escape `%` và `_` theo hợp đồng LIKE; parameter binding không tự escape wildcard semantics.

Ưu điểm của việc chia sẻ template WHERE có kiểm soát:

- Hạn chế quên điều kiện khi sửa filter.
- Data query và count query có cấu trúc SELECT/FETCH/ORDER khác nhau.
- Không phải parse/replace HQL bằng string hacks.
- Giữ các tham số nghiệp vụ giống nhau.

Nhược điểm: template string vẫn không được Java compiler kiểm tra property paths; với điều kiện động nhiều nhánh, Criteria API hoặc Specification có thể phù hợp hơn.

## 12. Criteria API: hai cây truy vấn, cùng logic predicate

Với Criteria API, cần tạo **hai `CriteriaQuery` và hai `Root` riêng**: một cho Book, một cho Long count.

### 12.1. Không tái sử dụng cùng đối tượng Predicate/Root

Một lỗi dễ gặp:

~~~java
CriteriaQuery<Book> dataCq = cb.createQuery(Book.class);
Root<Book> dataRoot = dataCq.from(Book.class);

Predicate statusPredicate =
        cb.equal(dataRoot.get("status"), status);

// SAI VỀ PHẠM VI: predicate gắn với dataRoot.
CriteriaQuery<Long> countCq = cb.createQuery(Long.class);
Root<Book> countRoot = countCq.from(Book.class);
countCq.where(statusPredicate);
~~~

`statusPredicate` thuộc query tree của `dataRoot`. Không chuyển nguyên Predicate/Join/Path sang một Criteria query khác rồi mong Hibernate tự “đổi root”. Trong các phiên bản Hibernate, điều này có thể gây lỗi semantic/SQM tree reuse hoặc tạo SQL không hợp lệ.

Thay vào đó, tạo **hàm xây predicate** nhận root và query hiện tại, rồi gọi **hai lần** để nhận các Criteria nodes riêng.

### 12.2. Một helper tạo bộ lọc đúng theo từng query tree

~~~java
public record BookFilter(
        BookStatus status,
        String tagPrefix
) {}

private static Predicate buildWhere(
        CriteriaBuilder cb,
        CriteriaQuery<?> query,
        Root<Book> book,
        BookFilter filter
) {
    List<Predicate> conditions = new ArrayList<>();

    if (filter.status() != null) {
        conditions.add(
                cb.equal(book.get("status"), filter.status())
        );
    }

    if (filter.tagPrefix() != null
            && !filter.tagPrefix().isBlank()) {
        Subquery<Long> existsTag = query.subquery(Long.class);
        Root<Book> candidate = existsTag.from(Book.class);
        SetJoin<Book, String> tag =
                candidate.joinSet("tags");

        existsTag.select(cb.literal(1L))
                .where(
                    cb.equal(
                        candidate.get("id"),
                        book.get("id")
                    ),
                    cb.like(
                        cb.lower(tag),
                        filter.tagPrefix().toLowerCase(Locale.ROOT) + "%"
                    )
                );

        conditions.add(cb.exists(existsTag));
    }

    return cb.and(conditions.toArray(Predicate[]::new));
}
~~~

Imports liên quan: `jakarta.persistence.criteria.*`, `java.util.*`. Trong code production, validate length của `tagPrefix` và escape wildcard nếu ý nghĩa nghiệp vụ là tìm literal prefix; ví dụ này chấp nhận `%`/`_` theo semantics LIKE.

Helper tạo một subquery `EXISTS` khác nhau cho mỗi CriteriaQuery, nên không nhân số dòng root. Query trees hoàn toàn tách biệt nhưng dựa trên cùng định nghĩa lọc.

### 12.3. Data CriteriaQuery

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Book> dataCq = cb.createQuery(Book.class);
Root<Book> book = dataCq.from(Book.class);

book.fetch("publisher", JoinType.LEFT);

dataCq.select(book)
      .where(buildWhere(cb, dataCq, book, filter))
      .orderBy(
          cb.desc(book.get("createdAt")),
          cb.desc(book.get("id"))
      );

List<Book> content = em.createQuery(dataCq)
        .setFirstResult(offset)
        .setMaxResults(size)
        .getResultList();
~~~

Ở đây `fetch("publisher", LEFT)` chỉ xuất hiện trong data query. Vì Publisher là to-one, việc fetch trong query phân trang thường không tạo row multiplication như collection fetch join.

### 12.4. Count CriteriaQuery

~~~java
CriteriaQuery<Long> countCq = cb.createQuery(Long.class);
Root<Book> countBook = countCq.from(Book.class);

countCq.select(cb.count(countBook))
       .where(buildWhere(cb, countCq, countBook, filter));

Long total = em.createQuery(countCq).getSingleResult();
~~~

Không fetch publisher, không order, không pagination. Vì bộ lọc dùng `EXISTS` và mỗi Book root xuất hiện một lần, `cb.count(countBook)` có đúng ý nghĩa.

Nếu count query dùng join to-many trực tiếp thay vì EXISTS, phải xem xét:

~~~java
countCq.select(cb.countDistinct(countBook.get("id")));
~~~

Không thêm `countDistinct` máy móc nếu query đã tạo một root row duy nhất; nó có thể tốn chi phí dư thừa.

### 12.5. Khi nào `cb.countDistinct(root)` phù hợp?

`cb.countDistinct(root)` là một lựa chọn Criteria khi cần đếm distinct root, nhưng cách Hibernate/DBMS ánh xạ `DISTINCT` trên entity/composite key có thể khác nhau. Với root có identifier đơn, `cb.countDistinct(root.get("id"))` thường minh bạch hơn.

Criteria API không tự quyết định đúng semantics. Developer vẫn phải hiểu join cardinality và mục tiêu đếm.

## 13. Spring Data JPA: khai báo countQuery riêng

Spring Data JPA thường cung cấp `Page<T>` với nội dung trang và tổng phần tử. Với JPQL có join phức tạp, khai báo `countQuery` tường minh thay vì chỉ trông chờ framework suy diễn count từ query chính.

~~~java
public interface BookRepository
        extends JpaRepository<Book, Long> {

    @Query(
        value = """
            select distinct b
            from Book b
            join b.tags tag
            left join fetch b.publisher
            where b.status = :status
              and tag like :tagPattern
            """,
        countQuery = """
            select count(distinct b.id)
            from Book b
            join b.tags tag
            where b.status = :status
              and tag like :tagPattern
            """
    )
    Page<Book> findPublishedByTagPattern(
            @Param("status") BookStatus status,
            @Param("tagPattern") String tagPattern,
            Pageable pageable
    );
}
~~~

Các import Spring Data tương ứng: `org.springframework.data.jpa.repository.JpaRepository`, `Query`, `org.springframework.data.repository.query.Param`, `org.springframework.data.domain.Page` và `Pageable`.

Ở đây:

- Data query chọn Book và fetch Publisher.
- Join tags dùng để **lọc** Book.
- Count query giữ điều kiện tag, bỏ fetch Publisher và đếm distinct Book ID.
- Cả hai nhận cùng các tham số bind.
- `Pageable` cung cấp offset/limit và có thể bổ sung sort theo cơ chế framework; cần kiểm soát các sort paths được chấp nhận.

### 13.1. Vì sao khai báo explicit countQuery?

Không phải mọi data query đều có thể chuyển thành count query bằng máy:

- `JOIN FETCH` không có ý nghĩa trong count selection.
- Join to-many có thể làm `COUNT` bị nhân.
- `DISTINCT` của data result cần chuyển thành semantics đếm distinct root.
- Query có `GROUP BY`/`HAVING` không thể đếm root bằng cách đơn giản.
- Native query có cú pháp đặc thù hoặc CTE/window function có thể cần count SQL riêng.
- Constructor projection không phải thứ cần xây trong count.

Spring Data có cơ chế tự suy diễn/đơn giản hóa count query trong một số trường hợp, và một số execution path có thể tối ưu bỏ count khi đủ điều kiện. Nhưng khi join/fetch/grouping phức tạp, **định nghĩa count tường minh giúp kiểm soát semantics**. Đừng coi nội dung `Page.getTotalElements()` đúng chỉ vì framework đã trả một đối tượng Page.

### 13.2. Một lựa chọn khác: query lọc bằng EXISTS

Có thể đưa `EXISTS` vào data và count query để tránh join tags ở outer query:

~~~java
@Query(
    value = """
        select b
        from Book b
        left join fetch b.publisher
        where b.status = :status
          and exists (
              select 1
              from Book candidate join candidate.tags tag
              where candidate.id = b.id
                and tag like :pattern
          )
        """,
    countQuery = """
        select count(b)
        from Book b
        where b.status = :status
          and exists (
              select 1
              from Book candidate join candidate.tags tag
              where candidate.id = b.id
                and tag like :pattern
          )
        """
)
Page<Book> findUsingExists(
        @Param("status") BookStatus status,
        @Param("pattern") String pattern,
        Pageable pageable
);
~~~

Query dạng này không fetch collection; to-one fetch và `EXISTS` có thể phối hợp với phân trang. Vẫn cần quy ước sort ổn định và xác nhận SQL theo phiên bản Spring Data/Hibernate đang dùng.

## 14. Khi data query có GROUP BY hoặc HAVING

Một trường hợp khó hơn: màn hình **không hiển thị mỗi Book**, mà mỗi **nhóm** theo Publisher.

Data query:

~~~sql
select
    b.publisher_id,
    count(*) as book_count
from books b
where b.status = 'PUBLISHED'
group by b.publisher_id
having count(*) >= 5
order by book_count desc, b.publisher_id;
~~~

Mỗi dòng kết quả đại diện cho **một nhóm nhà xuất bản**, không phải một Book. Nếu có 800 sách thuộc 20 nhóm và chỉ 12 nhóm đạt điều kiện HAVING, `totalElements` của màn hình phân trang theo nhóm phải là **12**, không phải 800 hay 20.

### 14.1. Count root là sai hợp đồng

~~~sql
-- Đếm số Book, không đếm số nhóm đủ điều kiện.
select count(*)
from books b
where b.status = 'PUBLISHED';
~~~

Query này không phản ánh `GROUP BY` và `HAVING`.

### 14.2. Đếm số nhóm từ relation đã nhóm

Trong native SQL, nhiều DBMS hỗ trợ derived table:

~~~sql
select count(*)
from (
    select b.publisher_id
    from books b
    where b.status = :status
    group by b.publisher_id
    having count(*) >= :minimumBooks
) grouped_publishers;
~~~

Đây là **một count query khác hình dạng rõ rệt** so với data query: nó đếm các rows của derived relation sau `GROUP BY/HAVING`. Cú pháp subquery-in-FROM là SQL phổ biến; khả năng dùng chính xác trong JPQL portable bị giới hạn vì JPQL chuẩn không hỗ trợ mọi dạng derived table như SQL. Nếu sử dụng HQL mở rộng hoặc native query, cần đối chiếu phiên bản và Dialect.

### 14.3. COUNT DISTINCT không luôn thay thế GROUP BY

Nếu không có HAVING và chỉ muốn đếm publisher ID khác null:

~~~sql
select count(distinct b.publisher_id)
from books b
where b.status = 'PUBLISHED';
~~~

có thể tương ứng số nhóm publisher khác null. Nhưng cần chú ý:

- `COUNT(DISTINCT column)` thường **không đếm NULL**, còn `GROUP BY column` có thể tạo một nhóm NULL.
- Nếu `HAVING count(*) >= 5`, count distinct publisher IDs **không áp điều kiện HAVING**.
- Nếu group key là nhiều cột, cú pháp distinct tuple và null handling có thể khác theo DBMS.
- Nếu output có nhiều cấp nhóm hoặc rollup, ý nghĩa total phải được thiết kế lại.

**Trước khi viết count query, xác định đơn vị trang là root entity, nhóm, cặp khóa hay một report row.**

## 15. Count query cho projection/DTO

Một trang có thể hiển thị DTO:

~~~java
public record BookRow(
        Long id,
        String title,
        String publisherName
) {}
~~~

HQL:

~~~java
List<BookRow> content = em.createQuery(
        """
        select new com.example.api.BookRow(
            b.id, b.title, p.name
        )
        from Book b
        left join b.publisher p
        where b.status = :status
        order by b.createdAt desc, b.id desc
        """,
        BookRow.class
    )
    .setParameter("status", status)
    .setFirstResult(offset)
    .setMaxResults(size)
    .getResultList();
~~~

Count query:

~~~java
Long total = em.createQuery(
        "select count(b) from Book b where b.status = :status",
        Long.class
    )
    .setParameter("status", status)
    .getSingleResult();
~~~

`BookRow` là DTO; package `com.example.api` chỉ là ví dụ và phải khớp class thật. `LEFT JOIN publisher` trong data query dùng để lấy tên nhà xuất bản, không ảnh hưởng bộ lọc; count query có thể bỏ nó.

Nếu DTO query chọn một dòng cho **mỗi combination** giữa Book và Tag thay vì một dòng cho mỗi Book, count query phải đếm combinations theo đúng hợp đồng — không tự áp `DISTINCT Book` nếu UI thực sự phân trang các pairs. Chính **đơn vị của row hiển thị** quyết định cách count.

## 16. Dùng COUNT hay không cần COUNT?

Có hai kiểu phân trang thường gặp:

### 16.1. Page: cần tổng phần tử

Một `Page<T>` thường có:

- Danh sách content.
- Số trang, kích thước trang.
- Tổng số phần tử trước phân trang.
- Tổng số trang, dựa trên total và page size.

Nếu UI hiển thị “Trang 3/25” hoặc cần đi tới trang cuối, count thường là một phần của hợp đồng. Nhưng query count có thể rất tốn kém với nhiều join, filter, `DISTINCT` hoặc dữ liệu lớn.

### 16.2. Slice: chỉ cần biết có trang tiếp theo

Nếu UI chỉ có nút “Tải thêm”, thường không cần tổng số chính xác. Có thể yêu cầu `pageSize + 1` root results:

~~~java
List<Book> candidates = em.createQuery(
        """
        select b from Book b
        where b.status = :status
        order by b.createdAt desc, b.id desc
        """,
        Book.class
    )
    .setParameter("status", status)
    .setFirstResult(offset)
    .setMaxResults(size + 1)
    .getResultList();

boolean hasNext = candidates.size() > size;

List<Book> content = candidates.size() > size
        ? candidates.subList(0, size)
        : candidates;
~~~

Cách này chỉ đúng nếu query đã có **một dòng logic cho mỗi Book** trước pagination. Với join to-many trả duplicate root, lấy thêm một SQL row không bảo đảm có thêm một Book. Hãy dùng `EXISTS` hoặc paging IDs/`DISTINCT` đúng để phân trang root.

Spring Data cung cấp kiểu `Slice<T>` cho trường hợp không cần total count, tùy method/query mechanism.

### 16.3. Keyset/cursor pagination

Với bảng lớn, `OFFSET` cao có thể chậm hoặc tạo trải nghiệm không ổn định khi dữ liệu thay đổi. Keyset pagination dùng giá trị của khóa sắp xếp cuối trang trước để lấy trang tiếp theo:

~~~sql
select b.id, b.title, b.created_at
from books b
where b.status = :status
  and (
      b.created_at < :lastCreatedAt
      or (
          b.created_at = :lastCreatedAt
          and b.id < :lastId
      )
  )
order by b.created_at desc, b.id desc;
~~~

`lastCreatedAt` và `lastId` là cursor values. Cần xử lý null sort keys, uniqueness, database collation và sort direction tương ứng. Keyset không tự cho biết tổng phần tử; nếu UI vẫn cần total count, count là một yêu cầu riêng.

## 17. Nhất quán giữa data query và count query khi có ghi đồng thời

Ngay cả hai query **đúng về mặt logic** vẫn có thể phản ánh hai thời điểm khác nhau:

~~~mermaid
sequenceDiagram
    participant A as Request đọc trang
    participant DB as Database
    participant B as Request khác
    A->>DB: SELECT page Book IDs
    DB-->>A: 20 IDs
    B->>DB: INSERT/DELETE Book và COMMIT
    A->>DB: SELECT count(Book)
    DB-->>A: Total mới
    Note over A: Content và total có thể không cùng snapshot
~~~

Nếu chạy theo `READ COMMITTED`, DBMS có thể cho mỗi statement nhìn thấy một snapshot dữ liệu đã commit mới. Vì vậy total có thể tăng hoặc giảm giữa data query và count query.

### 17.1. Chọn mức nhất quán phù hợp nghiệp vụ

- **Danh sách thông thường:** chấp nhận total gần đúng theo thời điểm query. Giải thích rằng số lượng có thể thay đổi do thao tác đồng thời.
- **Màn hình yêu cầu snapshot nhất quán:** dùng transaction/isolation phù hợp semantics của DBMS (ví dụ snapshot/repeatable-read khi được hỗ trợ), hoặc cơ chế snapshot/report đã được thiết kế.
- **Báo cáo chính xác tại thời điểm chốt:** cân nhắc dữ liệu snapshot/materialized report và một phiên bản dữ liệu cố định.

`@Transactional(readOnly = true)` **không tự đảm bảo** hai SELECT nhận cùng snapshot trên mọi DBMS. Nó tạo ranh giới transaction theo framework và cấu hình; isolation mới là yếu tố quan trọng.

### 17.2. Tập IDs có thể thay đổi trong truy vấn hai bước

Với ID page + entity graph fetch, Book có thể bị xóa hoặc đổi bộ lọc giữa hai statement. Khi đó:

- Một ID đã chọn có thể không tìm được trong query thứ hai.
- Entity được tải có thể đã thay đổi trạng thái so với lúc lọc.
- Total count có thể khác số root của thời điểm page query.

Nếu nghiệp vụ yêu cầu nhất quán mạnh, hãy thiết kế transaction snapshot/locking thích hợp. Không cố sửa bằng cách “fill đủ 20 Book bất kỳ” sau một query khác vì như vậy có thể phá thứ tự và điều kiện trang.

## 18. Dùng cùng điều kiện nghiệp vụ nhưng không copy mọi JOIN

Khi có nhiều filter tùy chọn, lỗi phổ biến nhất là **data query và count query lệch predicate**:

- Data lọc `status=PUBLISHED`, count quên status.
- Data có điều kiện tenant, count thiếu tenant.
- Data lọc tag prefix, count chỉ đếm tất cả Book.
- Data loại soft-deleted rows, count quên soft-delete.
- Data lọc quyền xem theo owner, count đếm mọi owner.
- Data dùng effective date/time, count dùng điều kiện khác.
- Data có HAVING, count không áp logic nhóm.

### 18.1. Bảng quyết định giữ/bỏ

| Thành phần của data query | Count query nên xử lý |
| --- | --- |
| `WHERE b.status = :status` | Giữ |
| Tenant/ACL/soft-delete predicate | Giữ semantics quyền và phạm vi dữ liệu |
| `EXISTS` lọc Book theo tags | Giữ |
| `INNER JOIN publisher` để kiểm tra điều kiện Publisher | Giữ predicate bằng join/exists/path tương đương |
| `LEFT JOIN FETCH publisher` chỉ phục vụ hiển thị | Bỏ |
| `LEFT JOIN FETCH tags` chỉ phục vụ tải collection | Bỏ; xử lý pagination dữ liệu riêng |
| `ORDER BY b.createdAt DESC` | Bỏ |
| `OFFSET`/`LIMIT` | Bỏ |
| `SELECT NEW BookDto(...)` | Đổi thành phép đếm đơn vị row thích hợp |
| `DISTINCT b` do join to-many | Dùng distinct ID hoặc EXISTS nếu cần đếm root |
| `GROUP BY/HAVING` | Đếm số nhóm đã qua HAVING, không count root |
| Projection aggregate/window | Đếm đúng các report rows nếu UI phân trang report |
| Join thừa, không lọc/không chọn | Bỏ nếu không thay đổi tập kết quả |

Bảng này mô tả cách suy nghĩ, không phải thuật toán chuyển đổi SQL tự động. Đặc biệt, join có thể ảnh hưởng tập root nếu chuyển từ LEFT sang INNER hoặc nếu WHERE/HAVING dùng cột của bảng join.

### 18.2. Tập logic chung tốt hơn chuỗi SQL chung

Có thể xây một `BookFilter` chứa các điều kiện nghiệp vụ, rồi có hai query builders:

- `buildDataQuery(filter, sort, fetchPlan)`.
- `buildCountQuery(filter)`.

Cả hai gọi cùng helper xây predicates nhưng tạo `Root` và `Predicate` mới cho từng Criteria tree. Nhờ đó không ép count query phải mang fetch joins, projection hay order của data query.

## 19. Tối ưu count query không làm sai kết quả

### 19.1. Bỏ ORDER BY

`ORDER BY` không thay đổi tổng số bản ghi logic. Nó chỉ cần cho thứ tự dữ liệu, không cần trong phép đếm; trong nhiều DBMS, ORDER BY trong count context còn gây lỗi hoặc chi phí không cần thiết.

### 19.2. Bỏ JOIN chỉ để tải dữ liệu

Join Publisher cho DTO hoặc fetch có thể không cần trong count. Nhưng nếu dùng INNER JOIN để lọc những Book có Publisher và data result thật sự loại Book không có Publisher, count cần giữ hiệu ứng loại trừ đó.

### 19.3. Ưu tiên EXISTS khi hỏi về sự tồn tại

Với filter dựa trên “có ít nhất một child”, EXISTS có thể tránh row multiplication. Tuy nhiên optimizer có thể chọn execution plan khác nhau; đo trên DBMS thật.

### 19.4. Index hỗ trợ count

Một số index đáng xem xét theo workload:

~~~sql
create index idx_books_status_created_id
    on books(status, created_at, id);

create index idx_book_tags_book_id
    on book_tags(book_id);

create index idx_book_tags_tag_book_id
    on book_tags(tag, book_id);
~~~

Đây là ví dụ logic index, không phải lời khuyên áp dụng đồng loạt: với `LIKE 'java%'`, khả năng dùng index phụ thuộc collation, case normalization, pattern và DBMS operator classes. Index cũng có chi phí ghi và storage; cần đọc `EXPLAIN`/execution plan và thống kê truy vấn production.

### 19.5. Đừng thêm DISTINCT không cần thiết

Nếu count query chỉ đọc `books` và không có join nhân dòng, `count(distinct b.id)` thường không mang lại lợi ích so với `count(b)`. DISTINCT có thể tạo chi phí extra deduplication. Chỉ dùng khi semantics yêu cầu.

### 19.6. Khi đếm quá đắt

Tùy nghiệp vụ, có thể:

- Trả `Slice`/cursor thay vì total count.
- Đếm theo yêu cầu thay vì mỗi request.
- Cache total với thời hạn/cơ chế invalidation rõ ràng nếu chấp nhận dữ liệu trễ.
- Dùng counters/materialized aggregates có đồng bộ nhất quán phù hợp.
- Đưa báo cáo lớn sang dữ liệu đã tổng hợp trước.

Không dùng approximate count cho một API hứa `totalElements` chính xác mà không đổi hợp đồng rõ ràng.

## 20. Tránh lỗi khi dynamic sort và filter

Nếu người dùng chọn sort field, không ghép raw request vào HQL:

~~~java
// KHÔNG AN TOÀN nếu sortBy đến trực tiếp từ client.
String hql = "select b from Book b order by " + sortBy;
~~~

Dùng allowlist:

~~~java
public enum BookSort {
    CREATED_AT,
    TITLE
}

String sortExpression = switch (sortBy) {
    case CREATED_AT -> "b.createdAt";
    case TITLE -> "b.title";
};

String hql = "select b from Book b " +
        "where b.status = :status " +
        "order by " + sortExpression + ", b.id";
~~~

Count query **không cần** `sortExpression`. Tuy nhiên data và count phải cùng tenant/filter predicates đã được bind.

Đừng cho client cung cấp HQL fragment `whereClause`/`joinClause` rồi dùng chung cho hai query. Đây vừa là vấn đề bảo mật, vừa khiến việc kiểm soát count semantics khó hơn.

## 21. Các tình huống dễ chọn sai phép đếm

### 21.1. Many-to-many với filter nhiều nhãn

Book có ba tags khớp điều kiện. Count sau `JOIN b.tags` đếm ba rows. Giải pháp: `count(distinct b.id)` hoặc `EXISTS`.

### 21.2. LEFT JOIN nhưng predicate nằm ở WHERE

~~~sql
select b.id
from books b
left join publishers p on p.id = b.publisher_id
where p.name like 'A%';
~~~

Dù join có từ khóa LEFT, predicate `p.name LIKE...` trong WHERE loại Book không có Publisher, vì p.name là NULL. Count bỏ join và predicate sẽ đếm thêm các Book không phù hợp. Phải giữ semantics lọc.

### 21.3. LEFT JOIN với predicate nằm ở ON

~~~sql
select b.id, p.name
from books b
left join publishers p
  on p.id = b.publisher_id
 and p.name like 'A%';
~~~

Trong truy vấn này, điều kiện ở ON quyết định Publisher nào được ghép, nhưng **không loại Book root**. Nếu ứng dụng chọn tất cả Book, count có thể bỏ left join và vẫn đếm đúng số Book (giả sử quan hệ to-one không nhân root). Hai cách đặt predicate không tương đương.

### 21.4. Hai collection cùng join

Nếu Book có nhiều reviews và tags, có thể tạo tích số dòng. `count(b)` sai; `count(distinct b.id)` sửa tổng root, nhưng `EXISTS` riêng cho từng điều kiện có thể dễ hiểu hơn.

### 21.5. Group by báo cáo

Một trang hiển thị một dòng cho mỗi Publisher. Count phải đếm Publisher groups sau HAVING, không phải số sách trong các nhóm đó.

### 21.6. FETCH collection với pagination

Count query có thể đúng, nhưng data query vẫn tải quá nhiều SQL rows hoặc bị Hibernate cảnh báo phân trang trong bộ nhớ. Dùng ID-first pagination hoặc tách query collection.

### 21.7. Query chỉ lấy DTO

Nếu DTO có một dòng cho mỗi Book, count Book. Nếu DTO có một dòng cho mỗi cặp Book–Tag, count pairs. Không thể suy ra đơn vị đếm chỉ từ tên entity root.

### 21.8. Nested conditions và soft delete

Data query có điều kiện `archivedAt is null`, count query thiếu nó thì tổng bị cao hơn. Định nghĩa predicate ở một nơi, tạo hai query riêng để tránh lệch.

## 22. Kiểm thử hành vi phân trang và phép đếm

Khi viết integration tests cho persistence layer, dữ liệu thử nghiệm cần phơi bày sự khác biệt giữa số root và số joined rows:

- Book A có **hai** tag khớp.
- Book B có **một** tag khớp.
- Book C có tag không khớp.
- Book D không có Publisher nhưng vẫn phải xuất hiện nếu data query dùng LEFT JOIN FETCH.
- Có ít nhất một Book DRAFT không được đếm.
- Có Book ở tenant khác hoặc bị soft-delete nếu ứng dụng có những bộ lọc đó.

Những assertions cốt lõi:

~~~java
// Mô tả mong đợi nghiệp vụ; setup data được lược bỏ.
assertEquals(2, page.content().size());
assertEquals(2L, page.totalElements());
assertEquals(
        List.of(bookAId, bookBId),
        page.content().stream().map(Book::getId).toList()
);
~~~

Để phân trang nhiều trang, kiểm tra:

1. Root IDs không trùng trong một trang.
2. Thứ tự ổn định và có tie-breaker duy nhất.
3. Gộp tất cả các trang không mất hoặc lặp Book khi dữ liệu snapshot ổn định.
4. Total đúng với số Book phù hợp, không phải số tag rows.
5. Data filter và count filter cùng xử lý tenant/ACL/soft delete.
6. Một Book không có association optional vẫn được xử lý theo hợp đồng LEFT/INNER.
7. Khi lọc thành tập rỗng, content rỗng và total bằng 0.
8. Query có `GROUP BY/HAVING` đếm số nhóm, không số bản ghi nguồn.
9. Không xảy ra pagination-over-collection-fetch ở query cần limit/offset.
10. Khi dùng ID-first page, truy vấn fetch graph bảo toàn thứ tự ID ban đầu sau bước reorder.

Những test này giúp phát hiện lỗi logic mà thử nghiệm chỉ có một tag mỗi Book sẽ không nhìn thấy.

## 23. Quan sát SQL và số dòng thực tế

Khi điều tra tổng phân trang không đúng, nên xem **SQL được chạy và dữ liệu trả về**.

Hibernate 6 có logger `org.hibernate.SQL`; logger `org.hibernate.orm.jdbc.bind` có thể hiển thị bind values nếu bật TRACE trong môi trường thích hợp. Không bật bind parameter trace rộng rãi ở production nếu dữ liệu có secrets hoặc thông tin cá nhân.

Có thể dùng Hibernate statistics trong môi trường kiểm thử:

~~~properties
hibernate.generate_statistics=true
~~~

Các chỉ số cần đối chiếu:

| Chỉ số | Lý do |
| --- | --- |
| Số entity root duy nhất | Đơn vị nghiệp vụ của trang |
| Số rows SQL sau join | Phát hiện row multiplication |
| Kết quả count query | Phải bằng tổng root logic phù hợp |
| Query plan và index | Đo chi phí DISTINCT/EXISTS |
| Số round trips và latency | Hai query có thể vẫn rẻ hơn một query join nặng |
| Collection fetch sizes | Phát hiện tải collection quá rộng |
| Page size thực tế | Xem pagination cắt đúng root chưa |
| Cache/persistence context state | Tránh hiểu sai vì entity đã managed |

Một `count(distinct ...)` đúng số nhưng có execution plan đắt vẫn cần được cân nhắc tối ưu. Ngược lại, một `count(*)` rất nhanh nhưng đếm sai đơn vị nghiệp vụ không phải lời giải.

## 24. Checklist quyết định count query

Trước khi viết count query, trả lời theo thứ tự:

1. **Một item trong trang là gì?** Book, DTO, group hay một cặp Book–Tag?
2. **Mỗi root có xuất hiện nhiều lần trong outer result relation không?** Có join to-many hay Cartesian product không?
3. **JOIN nào chỉ để fetch/hiển thị?** Bỏ khỏi count nếu không thay đổi tập đủ điều kiện.
4. **JOIN nào dùng để filter?** Giữ ý nghĩa lọc; có thể chuyển sang EXISTS.
5. **Có DISTINCT trong data query không?** Xác định DISTINCT nhằm loại duplicate root hay duplicate projection values.
6. **Có GROUP BY/HAVING không?** Count số groups sau HAVING, không chỉ count root.
7. **Có pagination trên collection fetch join không?** Nếu có, sửa data query, không chỉ count query.
8. **Có cùng quyền truy cập/tenant/soft-delete conditions không?** Không bỏ sót bất kỳ điều kiện nghiệp vụ nào.
9. **Có ORDER BY trong count không?** Thường bỏ.
10. **COUNT có cần chính xác không?** Nếu không, cân nhắc Slice/cursor và bỏ phép đếm.
11. **Các câu query có cần cùng snapshot không?** Chọn transaction isolation phù hợp yêu cầu.
12. **Đã kiểm chứng với dữ liệu nhiều child và pagination nhiều trang chưa?** Đây là trường hợp làm lộ sai số.

## 25. Bài tập thực hành

### Bài 1 — Sửa total bị nhân bởi tags

Cho truy vấn:

~~~java
select b
from Book b join b.tags tag
where tag like :prefix
~~~

Một Book có ba tag khớp. Hãy viết hai count queries bảo đảm tổng là số Book, bằng `COUNT DISTINCT` và bằng `EXISTS`.

### Bài 2 — Tách fetch join

Data query:

~~~java
select b
from Book b left join fetch b.publisher
where b.status = :status
~~~

Hãy viết count query tương ứng, giải thích vì sao không cần `LEFT JOIN FETCH`.

### Bài 3 — Giữ semantics khi lọc association

Data query:

~~~java
select b
from Book b join b.publisher p
where p.name like :name
~~~

Count query có thể bỏ join Publisher không? Giải thích dựa trên tập Book đủ điều kiện, không chỉ dựa trên việc Publisher là quan hệ to-one.

### Bài 4 — Hai collection

Book có `tags` và `reviews`. Hãy viết count query cho các Book có ít nhất một tag `java%` và ít nhất một review đã được duyệt, nhưng tránh Cartesian multiplication của hai joins.

### Bài 5 — Phân trang collection

UI cần mỗi Book cùng tất cả tags. Hãy thiết kế quy trình ID-page query, graph-fetch query và count query; giải thích vì sao bước fetch tags không áp limit/offset và vì sao cần reorder theo danh sách IDs.

### Bài 6 — Phân trang theo nhóm

Data query group books theo Publisher và HAVING ít nhất năm sách. Hãy giải thích vì sao `count(b)` không trả số nhóm trên UI, rồi viết native SQL đếm số nhóm đã vượt HAVING.

### Bài 7 — Tính nhất quán

Một request chọn page trước, một request khác xóa Book, rồi request đầu chạy count. `totalElements` có thể khác số lượng item theo snapshot trước đó không? `@Transactional(readOnly=true)` có đủ để ngăn khác biệt ở mọi DBMS không?

**Gợi ý:** (1) `count(distinct b.id)` hoặc outer `count(b)` với correlated EXISTS; (2) `select count(b) from Book b where b.status=:status`; (3) không nếu predicate `p.name` quyết định tập Book; (4) hai EXISTS; (5) trang theo IDs, fetch collections không phân trang, reorder; (6) đếm derived grouped rows; (7) có thể khác, isolation/snapshot mới quyết định.

## 26. Tài liệu tham khảo

- [Hibernate ORM 6.6 — HQL Query Language](https://docs.hibernate.org/orm/6.6/querylanguage/html_single/Hibernate_Query_Language.html): joins, fetch joins, distinct, aggregates, subqueries và pagination.
- [Hibernate ORM 6.6 — User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): Criteria, querying, fetch strategies, pagination và transaction behavior.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): `COUNT`, `DISTINCT`, `GROUP BY`, `HAVING`, Criteria API và query result semantics.
- [Spring Data JPA — Reference Documentation](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): `@Query`, `countQuery`, phân trang và cách tạo truy vấn repository.
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): `Page`, `Slice` và phân trang repository.

**Kết luận:** không nên sao chép nguyên data query để đếm. Truy vấn dữ liệu có thể dùng fetch join, projection, ordering hoặc join cho bộ lọc; truy vấn đếm phải trả **số đơn vị logic của trang** theo **cùng các predicate nghiệp vụ** nhưng có thể bỏ fetch/sort và thay joins bằng `COUNT DISTINCT` hoặc `EXISTS`. Với collection fetch, còn phải sửa cách phân trang dữ liệu bằng ID-first loading hoặc một chiến lược tương đương. Hai truy vấn khác SQL shape vẫn hoàn toàn đúng — miễn chúng nói về cùng tập kết quả logic, đúng quyền truy cập và đúng mức nhất quán mà ứng dụng yêu cầu.
