# Tổ chức truy vấn trong META-INF/orm.xml

Trong JPA, truy vấn có tên (named query) có thể được khai báo bằng annotation trên entity hoặc trong file XML mapping. Khi số lượng truy vấn tăng, việc đặt tất cả câu truy vấn trong annotation của entity hoặc rải rác trong repository có thể làm mã nguồn khó đọc và khó quản lý.

File **META-INF/orm.xml** cho phép tập trung metadata JPA, bao gồm named JPQL query, named native query và result-set mapping. Nhờ đó, lớp entity có thể giữ phần mô hình dữ liệu, còn các truy vấn dùng lại nhiều nơi được tổ chức trong XML.

Bài này trình bày cấu trúc file orm.xml, cách khai báo và gọi named query, cách Spring Data JPA tìm named query theo quy ước tên, ánh xạ kết quả native SQL, đăng ký file XML bổ sung trong Spring Boot và các lỗi thường gặp.

**Điều kiện của ví dụ:** các đoạn mã dùng Spring Boot 3.x, Java 17 trở lên, Jakarta Persistence và Spring Data JPA. Ứng dụng cần **spring-boot-starter-data-jpa**, JDBC driver, DataSource và schema phù hợp. Đây là các phần của ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng **javac**.

## 1. Named query là gì và khi nào nên dùng?

Named query là câu truy vấn được khai báo trước với một tên duy nhất trong persistence unit. Ứng dụng gọi truy vấn bằng tên đó thay vì viết lại JPQL hoặc SQL ở từng vị trí.

JPA có hai loại phổ biến:

- **Named JPQL query**: truy vấn theo entity và thuộc tính Java.
- **Named native query**: truy vấn SQL trực tiếp trên bảng và cột database.

Ví dụ JPQL:

~~~sql
select b
from Book b
where b.isbn = :isbn
~~~

Ví dụ native SQL:

~~~sql
SELECT b.id, b.title, b.isbn, b.price
FROM books b
WHERE b.isbn = ?
~~~

Có thể khai báo hai truy vấn này bằng annotation **@NamedQuery**/**@NamedNativeQuery**, hoặc đặt trong XML mapping. Bài này tập trung vào cách tổ chức bằng orm.xml.

Named query hữu ích khi:

- Một truy vấn được dùng ở nhiều nơi.
- Muốn tập trung truy vấn và metadata persistence.
- Muốn tách câu SQL dài khỏi code Java.
- Cần khai báo native SQL hoặc result-set mapping.
- Muốn quản lý query definition cùng với mapping XML của persistence unit.

Không nhất thiết phải đưa mọi query method vào orm.xml. Truy vấn đơn giản, chỉ dùng một lần có thể phù hợp với derived query hoặc **@Query** ngay trên repository. Chọn cách khai báo dựa trên khả năng tái sử dụng và cách nhóm code của dự án.

## 2. Vị trí và vai trò của META-INF/orm.xml

Theo quy ước JPA, file mapping mặc định có tên:

~~~text
src/main/resources/
└── META-INF/
    └── orm.xml
~~~

Sau khi build, file thường được đặt tại **META-INF/orm.xml** trên classpath của ứng dụng. Persistence provider đọc file này như một phần metadata của persistence unit.

Trong cấu hình JPA chuẩn, **META-INF/orm.xml** là tên mapping file mặc định. Nếu dùng file XML khác hoặc nhiều mapping file, cần đăng ký chúng với persistence unit. Trong Spring Boot, thuộc tính **spring.jpa.mapping-resources** cho phép chỉ định mapping resources bổ sung hoặc khai báo tường minh.

Ví dụ cấu trúc nhiều file:

~~~text
src/main/resources/
└── META-INF/
    ├── orm.xml
    └── queries.xml
~~~

Cả hai file đều dùng cấu trúc XML mapping JPA với root **entity-mappings**. Việc chia file có thể giúp tách entity mapping và query definitions theo module, nhưng đừng chia quá nhỏ nếu làm khó tìm kiếm và kiểm tra.

### orm.xml làm được gì?

File mapping có thể khai báo:

- Entity mapping và tên bảng.
- Mapping field/property, column và relationship.
- Named JPQL query.
- Named native query.
- SQL result-set mapping.
- Một số metadata persistence khác được định nghĩa trong schema ORM XML.

**orm.xml không thay thế entity scanning, DataSource hay repository scanning.** Lớp entity vẫn phải thuộc persistence unit phù hợp; database vẫn phải được cấu hình; repository interface vẫn cần được Spring Data JPA phát hiện.

## 3. Cấu trúc XML cơ bản của orm.xml

Với Jakarta Persistence 3.1, root element thường có dạng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence/orm
        https://jakarta.ee/xml/ns/persistence/orm/orm_3_1.xsd"
    version="3.1">

    <!-- Mapping và named query đặt tại đây -->

</entity-mappings>
~~~

Ý nghĩa:

- **entity-mappings** là root element của file ORM mapping.
- **xmlns** xác định namespace Jakarta Persistence ORM.
- **xsi:schemaLocation** liên kết namespace với XML schema tương ứng.
- **version** cho biết phiên bản schema ORM được dùng.

Với Spring Boot 3.x, hãy dùng namespace **jakarta** và schema tương thích với phiên bản Jakarta Persistence của stack đang chạy. Không sao chép namespace cũ của Java EE/JPA 2.x nếu ứng dụng đã chuyển sang Jakarta Persistence.

## 4. Khai báo named JPQL query bằng named-query

Giả sử entity Book:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String title;

    @Column(nullable = false, length = 20)
    private String isbn;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Book() {
    }

    public Book(String title, String isbn, BigDecimal price) {
        this.title = title;
        this.isbn = isbn;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getIsbn() {
        return isbn;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Khai báo truy vấn trong **META-INF/orm.xml**:

~~~xml
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence/orm
        https://jakarta.ee/xml/ns/persistence/orm/orm_3_1.xsd"
    version="3.1">

    <named-query name="Book.findByIsbn">
        <query>
            <![CDATA[
                select b
                from Book b
                where b.isbn = :isbn
            ]]>
        </query>
    </named-query>

</entity-mappings>
~~~

Các điểm cần chú ý:

- **name** là tên duy nhất của named query trong persistence unit.
- JPQL dùng entity name **Book**, không dùng tên bảng **books**.
- JPQL dùng thuộc tính Java **isbn**, không dùng tên cột vật lý nếu tên cột khác.
- **:isbn** là named parameter.
- CDATA giúp chứa ký tự đặc biệt của truy vấn trong XML mà không phải escape thủ công.

Có thể khai báo nhiều **named-query** trong cùng file:

~~~xml
<named-query name="Book.findAllOrderByTitle">
    <query>
        select b from Book b order by b.title
    </query>
</named-query>

<named-query name="Book.findExpensive">
    <query>
        select b from Book b where b.price >= :minimumPrice
    </query>
</named-query>
~~~

Không khai báo hai named query trùng tên trong cùng persistence unit. Tên truy vấn là định danh dùng lúc runtime; hãy chọn quy ước dễ tìm, chẳng hạn **EntityName.methodName**.

## 5. Gọi named JPQL query bằng EntityManager

Có thể gọi query theo tên bằng EntityManager:

~~~java
List<Book> books = entityManager
    .createNamedQuery("Book.findByIsbn", Book.class)
    .setParameter("isbn", isbn)
    .getResultList();
~~~

Ví dụ trong service:

~~~java
@Service
public class BookQueryService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public List<Book> findByIsbn(String isbn) {
        return entityManager
            .createNamedQuery("Book.findByIsbn", Book.class)
            .setParameter("isbn", isbn)
            .getResultList();
    }
}
~~~

**createNamedQuery(name, resultClass)** tạo typed query, giúp kiểm tra kiểu kết quả ở mức compile-time. Nếu query không trả về Book như khai báo, lỗi có thể xuất hiện khi thực thi hoặc chuyển đổi kết quả.

Nếu mong đợi tối đa một dòng, có thể dùng **getSingleResult()** hoặc API tương ứng. Hãy xử lý **NoResultException** và **NonUniqueResultException** phù hợp. Với truy vấn có thể không có kết quả, **getResultList()** rồi kiểm tra danh sách rỗng thường dễ kiểm soát hơn.

## 6. Spring Data JPA tìm named query theo quy ước tên

Spring Data JPA có thể tự tìm named query theo quy ước:

~~~text
<EntitySimpleName>.<repositoryMethodName>
~~~

Ví dụ repository:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface BookRepository extends JpaRepository<Book, Long> {

    List<Book> findByIsbn(String isbn);
}
~~~

Spring Data JPA tìm named query có tên:

~~~text
Book.findByIsbn
~~~

Nếu query này được khai báo trong **orm.xml**, repository method có thể sử dụng nó mà không cần đặt **@Query** trên method.

Nếu không tìm thấy named query phù hợp, Spring Data có thể chuyển sang cơ chế tạo query từ tên method, nếu method name là một derived query hợp lệ.

### @Query và named query: cách nào được ưu tiên?

Khi repository method có **@Query**, câu truy vấn khai báo trực tiếp trên annotation được ưu tiên so với named query theo quy ước. Vì vậy, nếu muốn dùng định nghĩa trong orm.xml, không đặt một @Query khác trên cùng method.

Có thể dùng tên method theo domain class và tên truy vấn để việc tìm kiếm rõ ràng. Với query method có tên phức tạp hoặc trùng quy ước, hãy kiểm tra log khởi động và integration test để chắc chắn Spring Data đã chọn đúng query.

## 7. Khai báo named native query trong orm.xml

Native query dùng SQL trực tiếp. Trong XML, khai báo bằng **named-native-query**:

~~~xml
<named-native-query
    name="Book.findByIsbnNative"
    result-class="com.example.catalog.domain.Book">

    <query>
        <![CDATA[
            SELECT
                b.id,
                b.title,
                b.isbn,
                b.price
            FROM books b
            WHERE b.isbn = ?
        ]]>
    </query>

</named-native-query>
~~~

Ở đây:

- **name** là tên named native query.
- **result-class** chỉ định kiểu entity dùng để ánh xạ mỗi dòng.
- SQL sử dụng tên bảng và cột vật lý.
- Dấu **?** là positional parameter của native query.

Với native SQL, chỉ dùng positional parameter là cách portable theo Jakarta Persistence. Một số provider hỗ trợ named parameter trong native query, nhưng không nên dựa vào khả năng đó nếu muốn truy vấn tương thích giữa các provider.

Gọi bằng EntityManager:

~~~java
Book book = entityManager
    .createNamedQuery("Book.findByIsbnNative", Book.class)
    .setParameter(1, isbn)
    .getSingleResult();
~~~

Lưu ý: native query ánh xạ về entity cần cung cấp đủ dữ liệu cột theo mapping của entity. Nếu chỉ lấy một phần field, hãy dùng DTO hoặc scalar result mapping thay vì khai báo result-class là Book.

## 8. Dùng sql-result-set-mapping khi tên cột khác mapping entity

Khi SQL có alias riêng hoặc join nhiều bảng, có thể khai báo **sql-result-set-mapping** và **entity-result**:

~~~xml
<sql-result-set-mapping name="BookEntityMapping">
    <entity-result entity-class="com.example.catalog.domain.Book">
        <field-result name="id" column="book_id"/>
        <field-result name="title" column="book_title"/>
        <field-result name="isbn" column="book_isbn"/>
        <field-result name="price" column="book_price"/>
    </entity-result>
</sql-result-set-mapping>
~~~

Named native query tham chiếu mapping:

~~~xml
<named-native-query
    name="Book.findByIsbnMapped"
    result-set-mapping="BookEntityMapping">

    <query>
        <![CDATA[
            SELECT
                b.id AS book_id,
                b.title AS book_title,
                b.isbn AS book_isbn,
                b.price AS book_price
            FROM books b
            WHERE b.isbn = ?
        ]]>
    </query>

</named-native-query>
~~~

Trong **field-result**:

- **name** là thuộc tính persistent của entity.
- **column** là tên cột hoặc alias được trả về từ SQL.

Nếu entity có thêm field persistent như version, discriminator, embedded ID, secondary table hoặc quan hệ phức tạp, result set mapping phải đáp ứng đầy đủ yêu cầu của mapping đó. Ví dụ rút gọn ở trên giả định entity chỉ có các field đã liệt kê.

## 9. Đăng ký XML mapping bổ sung trong Spring Boot

Với cấu hình JPA chuẩn, **META-INF/orm.xml** là mapping file mặc định. Nếu ứng dụng có file mapping bổ sung, chẳng hạn **META-INF/queries.xml**, có thể khai báo trong Spring Boot:

~~~yaml
spring:
  jpa:
    mapping-resources:
      - META-INF/queries.xml
~~~

Thuộc tính **spring.jpa.mapping-resources** tương ứng với các mapping-file resources của persistence unit. Mỗi file được liệt kê cần nằm trên classpath và có cấu trúc ORM XML hợp lệ.

Nếu khai báo nhiều file:

~~~yaml
spring:
  jpa:
    mapping-resources:
      - META-INF/catalog-mappings.xml
      - META-INF/report-queries.xml
~~~

Không tạo hai file cùng khai báo một named query name. Hãy quản lý query name duy nhất trong toàn persistence unit.

Trong ứng dụng Spring Boot thông thường, không cần tạo **persistence.xml** chỉ để khai báo named query nếu auto-configuration đã quản lý EntityManagerFactory. Nếu dự án tự cấu hình persistence unit hoặc có nhiều EntityManagerFactory, hãy đăng ký mapping resources cho đúng factory/persistence unit mà repository sử dụng.

## 10. Tổ chức file khi dự án có nhiều module

Có thể tổ chức theo domain:

~~~text
src/main/resources/
└── META-INF/
    ├── orm.xml
    ├── catalog-queries.xml
    └── reporting-queries.xml
~~~

Một cách phân chia:

- **orm.xml**: mapping mặc định hoặc named query dùng chung.
- **catalog-queries.xml**: truy vấn phục vụ catalog.
- **reporting-queries.xml**: truy vấn tổng hợp và báo cáo.

Khi thêm file riêng, khai báo trong **spring.jpa.mapping-resources**. Đặt tên query theo namespace logic, ví dụ:

~~~text
Book.findByIsbn
Book.findExpensive
Customer.findActive
PurchaseOrder.revenueByMonth
~~~

Tên truy vấn không phải tên package bắt buộc. Quy ước này chỉ nhằm tránh trùng và giúp người đọc nhận ra entity/use case liên quan.

Không nên tạo một file XML rất lớn chứa mọi query của toàn ứng dụng nếu nhiều nhóm phát triển độc lập. Ngược lại, cũng không cần một file cho mỗi query nhỏ. Chọn ranh giới theo domain và trách nhiệm bảo trì.

## 11. XML mapping và annotation cùng tồn tại thế nào?

JPA cho phép dùng annotation và XML mapping cùng nhau. XML có thể bổ sung hoặc ghi đè một số metadata annotation theo quy tắc mapping của JPA. Tuy nhiên, không nên khai báo cùng một metadata ở nhiều nơi nếu không có lý do rõ ràng.

Một số nguyên tắc:

- Entity vẫn có thể được đánh dấu **@Entity** trong Java trong khi named query được đặt ở orm.xml.
- Có thể giữ **@Table**, **@Column** trong annotation và tập trung named query trong XML.
- Nếu XML khai báo mapping field/relationship trùng với annotation, hãy hiểu precedence và metadata-complete trước khi triển khai.
- Không giả định mọi khai báo XML đều chỉ bổ sung; một số cấu hình XML có thể override annotation.
- Dùng một nguồn làm nơi quản lý chính cho mỗi nhóm metadata để giảm xung đột.

Một lựa chọn dễ bảo trì là: mapping entity cơ bản trong annotation, named query và native result mapping trong XML. Cách này không bắt buộc, nhưng giúp tránh làm entity class quá dài khi query nhiều.

## 12. Kiểm tra named query khi khởi động và khi chạy

JPA provider thường đăng ký và kiểm tra named JPQL query trong quá trình khởi tạo persistence unit. Vì vậy, lỗi cú pháp JPQL hoặc tên entity/property sai có thể làm ứng dụng khởi động thất bại.

Với named native query, database-specific SQL có thể chỉ được kiểm tra đầy đủ khi query thực thi, tùy provider và database. Không nên dựa vào việc ứng dụng khởi động thành công để kết luận native SQL đúng.

Một integration test có thể xác nhận named query trong orm.xml:

~~~java
@DataJpaTest
class BookNamedQueryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void findsBookByNamedJpqlQuery() {
        Book book = new Book(
            "Spring Data JPA",
            "9780000000001",
            new BigDecimal("250.00")
        );
        entityManager.persist(book);
        entityManager.flush();

        List<Book> result = entityManager
            .getEntityManager()
            .createNamedQuery("Book.findByIsbn", Book.class)
            .setParameter("isbn", "9780000000001")
            .getResultList();

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getTitle()).isEqualTo("Spring Data JPA");
    }
}
~~~

Test giả định entity Book có constructor tương ứng với ví dụ. Nếu test slice không tải mapping resource do cấu hình riêng của dự án, hãy kiểm tra cấu hình EntityManagerFactory và đăng ký mapping resource cho test.

Nên có test riêng cho:

- Named JPQL query.
- Named native query trên database đích.
- Entity result mapping đủ cột.
- Count query hoặc pagination nếu có.
- Parameter binding và kiểu kết quả.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Named query không được tìm thấy | File XML không được persistence unit nạp hoặc sai tên | Kiểm tra vị trí META-INF, mapping-resources và query name |
| Lỗi XML schema/namespace | Dùng namespace JPA cũ hoặc version không tương thích | Dùng namespace Jakarta và schema đúng phiên bản |
| JPQL báo không tìm thấy entity | Dùng tên bảng thay cho entity name hoặc entity chưa được quản lý | Dùng entity name và kiểm tra entity scanning |
| JPQL báo không tìm thấy thuộc tính | Dùng tên cột SQL thay vì thuộc tính Java | Dùng property name trong entity |
| Native query không map được entity | Thiếu cột persistent hoặc alias không đúng | SELECT đủ cột hoặc dùng result-set mapping |
| Native named query bind sai tham số | Dùng named parameter không portable | Dùng positional placeholder và setParameter theo vị trí |
| Hai query bị trùng tên | Định nghĩa lặp trong annotation/XML hoặc nhiều mapping file | Đặt tên duy nhất trong persistence unit |
| Repository dùng query khác mong đợi | @Query trên method ưu tiên named query theo quy ước | Kiểm tra annotation và named-query lookup |
| Ứng dụng khởi động lỗi sau khi thêm orm.xml | JPQL sai, entity/property không tồn tại hoặc XML không hợp lệ | Xem lỗi bootstrap và kiểm tra mapping |
| Native SQL chỉ lỗi khi chạy | SQL phụ thuộc database hoặc alias sai | Integration test trên database thực tế |

## 14. Checklist tổ chức truy vấn trong orm.xml

- [ ] Đặt file mặc định đúng vị trí **src/main/resources/META-INF/orm.xml**.
- [ ] Dùng namespace Jakarta ORM và schema tương thích phiên bản.
- [ ] Đặt tên named query duy nhất trong persistence unit.
- [ ] Dùng **named-query** cho JPQL và **named-native-query** cho SQL trực tiếp.
- [ ] Dùng entity name/property name trong JPQL.
- [ ] Dùng table/column name trong native SQL.
- [ ] Dùng positional parameter cho native query nếu cần tính portable.
- [ ] Dùng **result-class** hoặc **sql-result-set-mapping** phù hợp.
- [ ] Trả đủ cột khi ánh xạ native result về entity.
- [ ] Đăng ký XML mapping bổ sung bằng **spring.jpa.mapping-resources**.
- [ ] Kiểm tra precedence khi annotation và XML cùng khai báo metadata.
- [ ] Tránh query name trùng nhau giữa các file.
- [ ] Viết integration test cho cả named JPQL và named native query.

## 15. Kết luận

**META-INF/orm.xml** cho phép tổ chức metadata JPA và named query ngoài source code entity. Dùng **named-query** cho JPQL, **named-native-query** cho SQL trực tiếp, và **sql-result-set-mapping** khi cần ánh xạ cột/alias về entity.

Spring Data JPA có thể tìm named query theo quy ước **EntityName.methodName**, còn EntityManager có thể gọi trực tiếp bằng **createNamedQuery**. Với Spring Boot, hãy bảo đảm mapping resource được persistence unit nạp, đặc biệt khi dùng file XML bổ sung. Kiểm thử query trên database thực tế để xác nhận cú pháp, parameter binding và result mapping.