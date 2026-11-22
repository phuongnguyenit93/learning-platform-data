# Tải nhiều tập hợp, tích Descartes và giới hạn của bag

Trong Hibernate, việc tải một entity cùng các quan hệ của nó bằng `JOIN FETCH` có thể giúp giảm số lần truy vấn. Tuy nhiên, khi một entity có **nhiều tập hợp quan hệ nhiều dòng** như `@OneToMany` hoặc `@ManyToMany`, việc fetch join tất cả trong một câu SQL có thể tạo ra **tích Descartes (Cartesian product)**: mỗi phần tử của tập hợp thứ nhất kết hợp với mỗi phần tử của tập hợp thứ hai trong kết quả SQL.

Ngoài chi phí dữ liệu bị nhân lên, Hibernate còn có một giới hạn cụ thể với collection mang ngữ nghĩa **bag**. Nếu một truy vấn cố gắng fetch đồng thời nhiều bag, Hibernate có thể ném `MultipleBagFetchException` vì không thể tái dựng các bag một cách an toàn từ các hàng kết quả đã nhân chéo.

Cần hiểu ba vấn đề riêng:

- **Cartesian product** là hệ quả của cấu trúc JOIN ở SQL, làm số hàng kết quả tăng theo tích số phần tử của các collection.
- **Duplicate root rows** là việc cùng một entity gốc xuất hiện trong nhiều hàng SQL vì mỗi hàng mô tả một tổ hợp phần tử liên quan.
- **MultipleBagFetchException** là giới hạn của Hibernate khi đồng thời fetch nhiều collection có bag semantics; nó không đơn thuần là lỗi cú pháp SQL hay lỗi dữ liệu.

Bài học này giải thích cách Hibernate tải nhiều tập hợp, vì sao số hàng tăng nhanh, bag khác List/Set ra sao, khi nào lỗi xuất hiện và cách tổ chức fetch plan bằng nhiều truy vấn, batch fetching, subselect, entity graph hoặc projection.

## 1. Ví dụ: một Order có nhiều collection

Giả sử hệ thống bán hàng có `Order`, mỗi đơn hàng có nhiều dòng hàng và nhiều nhãn vận chuyển:

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
        name = "order_tags",
        joinColumns = @JoinColumn(name = "order_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private List<Tag> tags = new ArrayList<>();

    // Các thuộc tính và phương thức khác.
}
~~~

Một Order có thể có 3 OrderLine và 2 Tag. Hai collection có vòng đời độc lập, nhưng cùng được truy cập qua entity gốc.

Nếu ứng dụng cần đọc Order, tất cả lines và tất cả tags, một truy vấn dễ nghĩ tới là:

~~~java
List<Order> orders = em.createQuery("""
    SELECT o
    FROM Order o
    LEFT JOIN FETCH o.lines
    LEFT JOIN FETCH o.tags
    WHERE o.id = :id
    """, Order.class)
    .setParameter("id", orderId)
    .getResultList();
~~~

Về mặt ý tưởng, câu truy vấn muốn lấy mọi thứ trong một lần đi tới database. Nhưng khi cả hai quan hệ đều là to-many, kết quả SQL không có một hàng duy nhất cho Order.

Nếu Order có:

- 3 dòng hàng: L1, L2, L3.
- 2 tag: T1, T2.

JOIN tạo các tổ hợp:

| Order | OrderLine | Tag |
| --- | --- | --- |
| O1 | L1 | T1 |
| O1 | L1 | T2 |
| O1 | L2 | T1 |
| O1 | L2 | T2 |
| O1 | L3 | T1 |
| O1 | L3 | T2 |

Chỉ một Order nhưng có **3 × 2 = 6 hàng SQL**. Nếu có 10 Order, mỗi Order có 5 lines và 4 tags, kết quả có thể chứa tới 10 × 5 × 4 = 200 hàng, trước khi tính các collection rỗng và các điều kiện JOIN khác.

## 2. Vì sao xuất hiện tích Descartes?

Một SQL tương đương về ý nghĩa:

~~~sql
SELECT
    o.id,
    l.id AS line_id,
    t.id AS tag_id
FROM orders o
LEFT JOIN order_lines l
    ON l.order_id = o.id
LEFT JOIN order_tags ot
    ON ot.order_id = o.id
LEFT JOIN tags t
    ON t.id = ot.tag_id
WHERE o.id = ?;
~~~

Mỗi OrderLine của một Order kết hợp với mỗi association tag của chính Order đó. Nếu số phần tử của collection thứ nhất là m, collection thứ hai là n, số tổ hợp có thể lên tới:

\[
m \times n
\]

Với k collection to-many có kích thước tương ứng n1, n2, ..., nk, số tổ hợp trong trường hợp đầy đủ có thể tăng gần:

\[
n_1 \times n_2 \times \cdots \times n_k
\]

Với LEFT JOIN, nếu một collection rỗng, phần đóng góp của collection đó thường là một hàng null-extended cho root; có thể hình dung số hàng theo từng root là:

\[
\prod_{i=1}^{k} \max(1, n_i)
\]

Đây là mô hình ước lượng để hiểu độ tăng, không phải công thức thay thế phân tích execution plan của mọi SQL.

### 2.1. Nhiều hàng SQL không có nghĩa có nhiều Order entity

Kết quả SQL lặp lại cột của Order vì mỗi hàng mô tả một tổ hợp line/tag. Hibernate dùng các cột định danh và mapping để lắp ráp object graph.

Ví dụ, sáu hàng trên vẫn đại diện cho **một Order**, ba OrderLine và hai Tag. Tuy nhiên, database vẫn phải tạo và truyền sáu hàng; Hibernate vẫn phải đọc và xử lý dữ liệu lặp.

### 2.2. Dữ liệu lặp làm tăng chi phí

Khi fetch nhiều collection trong một query, chi phí không chỉ là số lượng hàng:

- Các cột của Order bị lặp lại trên từng tổ hợp.
- Các cột của từng OrderLine bị lặp theo số Tag.
- Các cột của từng Tag bị lặp theo số OrderLine.
- Database phải thực hiện join và tạo result set lớn.
- JDBC phải truyền nhiều dữ liệu qua mạng.
- Hibernate phải phân tích hàng và lắp ráp collection.
- Bộ nhớ và thời gian xử lý tăng dù số entity thực sự không tăng tương ứng.

Vì vậy, “một query” không đồng nghĩa với “ít dữ liệu” hoặc “nhanh hơn”. Một truy vấn lớn có thể đắt hơn hai hoặc ba truy vấn nhỏ có kết quả gọn.

### 2.3. Collection càng lớn, tích càng nguy hiểm

Ví dụ một Order có 40 lines và 15 tags:

\[
40 \times 15 = 600
\]

Một Order có thể tạo 600 hàng SQL. Nếu 100 Order có kích thước tương tự, số hàng có thể lên đến 60.000. Số entity gốc vẫn chỉ là 100; phần lớn result set là dữ liệu lặp để biểu diễn các tổ hợp.

Khi có thêm collection thứ ba, chẳng hạn audit events với 12 phần tử, số tổ hợp có thể tăng lên:

\[
40 \times 15 \times 12 = 7\,200
\]

Đây là lý do cần thiết kế fetch plan theo use case thay vì fetch mọi quan hệ chỉ vì có thể.

## 3. Duplicate root và DISTINCT

Một câu fetch join to-many có thể trả nhiều hàng SQL cho cùng root:

~~~java
SELECT o
FROM Order o
JOIN FETCH o.lines
~~~

Ở mức quan hệ SQL, mỗi Order xuất hiện lặp lại theo số line. Cần phân biệt:

1. **SQL rows**: các hàng vật lý mà database trả.
2. **Entity identity**: một Order có một persistent identity.
3. **Java result list**: danh sách entity mà JPA provider trả cho ứng dụng.

Hibernate có thể hợp nhất các hàng theo entity identity khi lắp ráp kết quả. Hành vi loại bỏ duplicate root trong danh sách kết quả cũng phụ thuộc phiên bản Hibernate.

### 3.1. DISTINCT trong JPQL

Có thể viết:

~~~java
List<Order> orders = em.createQuery("""
    SELECT DISTINCT o
    FROM Order o
    LEFT JOIN FETCH o.lines
    WHERE o.id = :id
    """, Order.class)
    .setParameter("id", orderId)
    .getResultList();
~~~

`DISTINCT` biểu đạt rằng ứng dụng muốn các root entity không lặp trong kết quả logic. Với các phiên bản Hibernate trước 6, nó thường được dùng trong JPQL fetch join để loại duplicate root result.

Từ Hibernate 6, các duplicate root entity phát sinh do join fetch được tự động loại khỏi kết quả entity trong nhiều trường hợp, nên `DISTINCT` không còn luôn cần chỉ để loại root duplicate. Cần đối chiếu đúng Hibernate version và loại query của dự án.

### 3.2. DISTINCT không xóa Cartesian product

Ngay cả khi dùng:

~~~sql
SELECT DISTINCT o.id, l.id, t.id
...
~~~

các tổ hợp (o.id, l.id, t.id) vẫn khác nhau. Database không thể gộp chúng thành một hàng vì mỗi hàng chứa một line hoặc tag khác nhau.

Do đó:

- DISTINCT có thể giúp kết quả root không lặp theo semantics query/provider.
- Nó **không biến hai collection thành hai cột độc lập**.
- Nó không loại bỏ số tổ hợp line/tag cần thiết trong result set.
- Nó không giải quyết `MultipleBagFetchException`.

Không dùng DISTINCT như cách chữa gốc cho Cartesian product.

## 4. Bag là gì trong Hibernate?

Trong Hibernate, **bag** là một loại collection semantics: tập hợp không có thứ tự được bảo đảm và có thể chứa phần tử trùng lặp. Một `List` được ánh xạ mà không có cột lưu vị trí thường được Hibernate xử lý như bag.

Ví dụ:

~~~java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines = new ArrayList<>();
~~~

Nếu không có `@OrderColumn`, Hibernate không có cột vị trí persistent để biết thứ tự phần tử trong List. Collection có thể được xử lý với bag semantics.

Một bag khác với:

- **Set**: không cho phép phần tử trùng theo hợp đồng equals/hashCode.
- **Indexed List**: có thứ tự/vị trí được lưu bằng cột `@OrderColumn`.
- **Sorted collection**: có thể được sắp xếp theo comparator hoặc thuộc tính, tùy mapping.

### 4.1. List không tự động có thứ tự persistent

~~~java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
~~~

Khai báo kiểu Java `List` không có nghĩa thứ tự phần tử được lưu bền vững trong database. Nếu không có `@OrderColumn`, không thể dựa vào thứ tự vị trí persistent.

Có thể dùng `@OrderBy`:

~~~java
@OneToMany(mappedBy = "order")
@OrderBy("createdAt ASC")
private List<OrderLine> lines;
~~~

`@OrderBy` yêu cầu sắp xếp kết quả khi tải theo thuộc tính. Nó **không lưu vị trí index** của từng phần tử như `@OrderColumn`; collection vẫn có thể có bag semantics trong Hibernate.

### 4.2. Indexed List với @OrderColumn

Nếu thứ tự vị trí là dữ liệu nghiệp vụ cần lưu:

~~~java
@OneToMany(mappedBy = "order")
@OrderColumn(name = "line_position")
private List<OrderLine> lines = new ArrayList<>();
~~~

Hibernate có thể lưu index của phần tử trong cột `line_position`. Đây là semantics khác bag thuần; việc thêm/xóa/di chuyển phần tử có thể làm Hibernate cập nhật các giá trị vị trí.

`@OrderColumn` có thể tránh việc collection được phân loại là bag trong một số mapping, nhưng **không xóa Cartesian product** khi fetch join nhiều collection. Nó cũng không nên được thêm chỉ để né exception nếu thứ tự không có ý nghĩa nghiệp vụ.

### 4.3. Set có ngữ nghĩa khác

~~~java
@ManyToMany
private Set<Tag> tags = new HashSet<>();
~~~

Set biểu đạt rằng mỗi phần tử chỉ xuất hiện một lần theo `equals()`/`hashCode()`. Hibernate có thể dùng semantics của Set để lắp ráp collection khi các hàng join bị lặp.

Nhưng thay List thành Set có hệ quả:

- Mất khả năng biểu diễn phần tử trùng.
- Không đảm bảo thứ tự như List.
- `equals()`/`hashCode()` của entity phải được thiết kế cẩn thận, nhất là với generated ID và proxy.
- Không tự giải quyết số hàng Cartesian trong SQL.

**Không đổi List thành Set chỉ để làm mất exception** nếu domain thực sự cần thứ tự hoặc cho phép phần tử lặp.

## 5. MultipleBagFetchException là gì?

Hibernate có exception:

~~~java
org.hibernate.loader.MultipleBagFetchException
~~~

Exception có thể xuất hiện khi một query cố gắng đồng thời fetch nhiều collection được Hibernate phân loại là bag, thường qua nhiều `JOIN FETCH` cho các quan hệ to-many.

Ví dụ:

~~~java
@Entity
public class Order {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    @ManyToMany
    private List<Tag> tags = new ArrayList<>();
}
~~~

Truy vấn:

~~~java
List<Order> result = em.createQuery("""
    SELECT o
    FROM Order o
    LEFT JOIN FETCH o.lines
    LEFT JOIN FETCH o.tags
    WHERE o.id = :id
    """, Order.class)
    .setParameter("id", id)
    .getResultList();
~~~

Nếu cả `lines` và `tags` là bag, Hibernate có thể ném `MultipleBagFetchException`.

### 5.1. Vì sao Hibernate không thể đơn giản lắp ráp hai bag?

Một bag cho phép phần tử lặp và không có index persistent. Khi hai bag được join cùng lúc, một hàng SQL chứa một tổ hợp phần tử từ mỗi bag.

Ví dụ một line L1 kết hợp với hai tag T1 và T2 tạo hai hàng:

| Order | Line | Tag |
| --- | --- | --- |
| O1 | L1 | T1 |
| O1 | L1 | T2 |

Nếu chỉ nhìn các hàng này, một bag có thể chứa phần tử trùng lặp hợp lệ theo semantics. Hibernate không thể luôn suy ra chắc chắn rằng L1 chỉ là một phần tử của bag hay các lần xuất hiện phải được giữ như các bản sao độc lập. Tương tự, tag có thể lặp theo từng line.

Hibernate từ chối một số kế hoạch fetch nhiều bag thay vì lắp ráp collection có nguy cơ sai semantics. Exception là **giới hạn ở tầng Hibernate mapping/query plan**, không phải lỗi do database không hỗ trợ JOIN.

### 5.2. Lỗi không có nghĩa mọi fetch nhiều collection đều bị cấm

Cần phân biệt:

- Fetch một bag: thường hợp lệ.
- Fetch nhiều collection nhưng chỉ một collection là bag, collection còn lại có semantics khác: có thể được Hibernate chấp nhận, tùy mapping/query/version.
- Fetch đồng thời nhiều bag: có thể gây `MultipleBagFetchException`.
- Fetch nhiều Set hoặc indexed List: có thể không gặp exception này nhưng vẫn có Cartesian product và chi phí lớn.

Vì vậy, né được exception **không chứng minh fetch plan tốt**.

### 5.3. Đây là exception của Hibernate

`MultipleBagFetchException` không phải exception chuẩn Jakarta Persistence. Khi ứng dụng dùng provider khác, behavior có thể khác. Nhưng nếu dự án dùng Hibernate, đây là giới hạn cần thiết kế query để tránh.

Không nên dựa vào một workaround chỉ tình cờ chạy với một phiên bản provider mà chưa hiểu semantics collection và chi phí SQL.

## 6. Workaround không nên chọn máy móc: đổi List thành Set

Một gợi ý thường gặp khi gặp exception là đổi:

~~~java
private List<OrderLine> lines;
private List<Tag> tags;
~~~

thành:

~~~java
private Set<OrderLine> lines = new HashSet<>();
private Set<Tag> tags = new HashSet<>();
~~~

Cách này có thể làm mapping không còn là hai bag và Hibernate chấp nhận fetch join. Tuy nhiên, nó không phải lời giải chung.

### 6.1. Set thay đổi mô hình dữ liệu trong Java

Nếu nghiệp vụ cho phép hai association giống nhau hoặc cần thứ tự, Set không còn biểu đạt đúng dữ liệu. Một số collection có thể chứa duplicate association hợp lệ hoặc cần thứ tự do người dùng sắp xếp.

### 6.2. Set yêu cầu equals/hashCode ổn định

Nếu entity dùng generated ID và đưa vào HashSet trước khi ID được gán, việc hash code thay đổi sau persist có thể làm collection hoạt động sai. Equality với Hibernate proxy cũng cần được thiết kế cẩn thận.

Không nên thay đổi equals/hashCode vội vàng chỉ để một query fetch join chạy được.

### 6.3. Cartesian product vẫn tồn tại

Ngay cả khi Hibernate không ném `MultipleBagFetchException`, SQL vẫn kết hợp các collection:

\[
\text{rows per root} \approx |lines| \times |tags|
\]

Khi collection lớn, result set có thể rất tốn kém. Thay Set chỉ giải quyết một giới hạn lắp ráp bag, không giải quyết nguyên nhân tăng dữ liệu.

## 7. @OrderColumn cũng không phải thuốc chữa chung

Một cách khác là thêm:

~~~java
@OneToMany(mappedBy = "order")
@OrderColumn(name = "line_position")
private List<OrderLine> lines;

@ManyToMany
@OrderColumn(name = "tag_position")
private List<Tag> tags;
~~~

Cột index khiến collection có semantics theo vị trí thay vì bag thuần trong những mapping phù hợp. Tuy nhiên, cần xem lại tính hợp lệ của mapping cụ thể, DDL và khả năng hỗ trợ của Hibernate version.

Các hệ quả:

- Database cần lưu vị trí.
- Reorder collection có thể phát sinh nhiều UPDATE.
- Thêm/xóa ở giữa danh sách có thể phải dịch chuyển index.
- Thứ tự trở thành một phần state persistent.
- Join fetch nhiều collection vẫn tạo tích Descartes.

Chỉ dùng `@OrderColumn` khi thứ tự thực sự là dữ liệu domain, ví dụ thứ tự các bước trong workflow hoặc vị trí các dòng do người dùng sắp xếp.

## 8. Chiến lược tốt: chia thành nhiều truy vấn fetch

Một cách phổ biến và dễ kiểm soát là **fetch từng collection trong một query riêng**, trong cùng persistence context.

Ví dụ đầu tiên tải Order và lines:

~~~java
List<Order> orders = em.createQuery("""
    SELECT DISTINCT o
    FROM Order o
    LEFT JOIN FETCH o.lines
    WHERE o.id IN :ids
    """, Order.class)
    .setParameter("ids", orderIds)
    .getResultList();
~~~

Sau đó tải tags cho các Order tương ứng:

~~~java
em.createQuery("""
    SELECT DISTINCT o
    FROM Order o
    LEFT JOIN FETCH o.tags
    WHERE o.id IN :ids
    """, Order.class)
    .setParameter("ids", orderIds)
    .getResultList();
~~~

Vì cả hai query chạy trong **cùng persistence context**, Hibernate dùng identity map để trả cùng managed Order instances. Query thứ hai có thể khởi tạo collection `tags` trên những Order đã được query thứ nhất tải; `lines` đã được khởi tạo vẫn ở trong persistence context.

Cần giữ transaction/context đủ lâu cho cả hai query. Không tách thành hai EntityManager độc lập rồi kỳ vọng object graph tự được hợp nhất.

### 8.1. Tại sao hai query có thể ít dữ liệu hơn?

Với một Order có 40 lines và 15 tags:

- Một query join cả hai: khoảng 40 × 15 = 600 hàng.
- Query fetch lines: khoảng 40 hàng.
- Query fetch tags: khoảng 15 hàng.
- Tổng hai query: khoảng 55 hàng, chưa tính root/null rows và overhead.

Số round-trip tăng từ một lên hai, nhưng tổng số hàng và cột lặp có thể giảm mạnh. Với mạng nội bộ nhanh và collection tương đối lớn, hai query thường hiệu quả hơn một result set Cartesian rất rộng.

### 8.2. Cẩn thận với danh sách ID lớn

`WHERE o.id IN :ids` phù hợp khi danh sách ID vừa phải. Với hàng nghìn hoặc hàng chục nghìn ID, có thể gặp giới hạn bind parameter của database, SQL quá dài hoặc chi phí parse cao.

Giải pháp gồm chia chunk, query theo page root IDs, batch fetching hoặc thiết kế truy vấn khác. Đừng gom một danh sách ID vô hạn vào một câu IN.

### 8.3. DISTINCT và Hibernate 6

Trong ví dụ, `DISTINCT` làm ý định root unique rõ ràng và tương thích với các phiên bản Hibernate cũ hơn. Hibernate 6 đã tự loại duplicate root entity do fetch join khỏi kết quả entity trong nhiều trường hợp; tùy version và query, `DISTINCT` có thể không cần chỉ vì mục đích này. Dù có hay không, hai truy vấn riêng vẫn tránh join chéo hai collection.

## 9. Batch fetching: tải collection theo nhóm

Hibernate có thể tải các collection lazy theo batch thay vì một query cho mỗi owner.

Dùng annotation Hibernate:

~~~java
import org.hibernate.annotations.BatchSize;

@Entity
public class Order {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    @BatchSize(size = 32)
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

Hoặc cấu hình mặc định:

~~~properties
hibernate.default_batch_fetch_size=32
~~~

Khi ứng dụng truy cập collection của một số Order trong persistence context, Hibernate có thể gom nhiều owner ID vào một câu SELECT với điều kiện IN để khởi tạo collection theo batch.

### 9.1. Batch fetching khác join fetching

- Join fetch thường lấy root và collection trong cùng SQL.
- Batch fetching tải collection bằng một hoặc một số SELECT riêng.
- Batch fetching tránh việc kết hợp nhiều collection to-many vào cùng một tích Cartesian.
- Batch fetching vẫn tạo thêm round-trip, nhưng thường giảm số query N+1.

Ví dụ có 100 Order, mỗi Order có lines. Nếu không batch, việc truy cập `order.getLines()` có thể tạo một query riêng cho từng Order. Batch size 32 có thể giảm số truy vấn tải lines xuống một vài nhóm, tùy cách collection được truy cập và số owner đang chờ.

### 9.2. Batch không có nghĩa luôn đúng một query

Batch size là giới hạn nhóm, không phải cam kết tất cả collection luôn được nạp bằng một SQL. Kết quả phụ thuộc số owner, collection đã initialized, loại association, dialect, parameter limits và cách ứng dụng truy cập.

### 9.3. Batch fetching không tự tải collection

Nếu collection vẫn lazy và ứng dụng không truy cập nó, Hibernate không cần tải chỉ vì `@BatchSize` tồn tại. Batch fetching là chiến lược khi cần khởi tạo association, không phải EAGER toàn bộ.

## 10. Subselect fetching

Hibernate còn hỗ trợ chiến lược `FetchMode.SUBSELECT` cho collection:

~~~java
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi một nhóm owner được tải trong persistence context và một collection cùng vai trò được khởi tạo, Hibernate có thể sử dụng subselect dựa trên truy vấn owner ban đầu để tải collections cho nhóm đó.

### 10.1. Subselect khác batch

| Chiến lược | Cách tải | Đặc điểm |
| --- | --- | --- |
| JOIN FETCH | JOIN root và collection trong một SQL | Có thể nhân hàng theo kích thước collection |
| Batch fetching | SELECT collection cho một nhóm owner IDs | Gom nhiều owner vào các batch |
| SUBSELECT | SELECT collection cho nhóm owner dựa trên truy vấn owner trước đó | Có thể tải collection cho cả nhóm trong một query phụ |
| Lazy từng owner | SELECT riêng khi mỗi collection được truy cập | Có nguy cơ N+1 |

`FetchMode.SUBSELECT` là extension của Hibernate, không phải annotation chuẩn JPA. Cần đo query thực tế và hiểu phạm vi owner được tải để tránh một subselect quá rộng.

### 10.2. Không bật SUBSELECT cho mọi collection

Một truy vấn owner ban đầu có thể trả nhiều entity. Khi collection được truy cập, subselect có thể tải dữ liệu cho cả nhóm đó, dù màn hình chỉ cần một phần. Chọn chiến lược theo use case và kích thước tập dữ liệu.

## 11. EntityGraph không phải cam kết tránh Cartesian product

JPA EntityGraph cho phép mô tả association cần được fetch:

~~~java
@EntityGraph(attributePaths = {"lines", "tags"})
@Query("select o from Order o where o.id = :id")
Optional<Order> findDetailedById(@Param("id") Long id);
~~~

EntityGraph hữu ích vì tách fetch plan khỏi câu JPQL. Tuy nhiên, **nó không cam kết provider sẽ tải các association bằng nhiều SELECT riêng**. Hibernate có thể chọn JOIN hoặc các chiến lược khác theo mapping, query và version.

Nếu EntityGraph yêu cầu nhiều to-many cùng lúc, vẫn phải kiểm tra SQL và xem xét `MultipleBagFetchException`/Cartesian product. EntityGraph không phải cách tự động né mọi giới hạn bag.

### 11.1. Dùng graph theo từng màn hình/use case

Thay vì một graph khổng lồ chứa mọi association:

- Màn hình danh sách chỉ tải Order và customer.
- Màn hình chi tiết tải lines.
- Màn hình phân loại tải tags.
- Báo cáo chỉ lấy các cột cần thiết bằng projection.

Fetch plan càng gần nhu cầu thực tế, càng dễ kiểm soát lượng dữ liệu.

## 12. DTO projection khi không cần entity graph

Nếu ứng dụng chỉ cần hiển thị dữ liệu, có thể query DTO:

~~~java
public record OrderLineView(
    Long orderId,
    String sku,
    int quantity
) {}
~~~

~~~java
List<OrderLineView> lines = em.createQuery("""
    SELECT new com.example.OrderLineView(
        o.id, l.sku, l.quantity
    )
    FROM Order o
    JOIN o.lines l
    WHERE o.id = :id
    """, OrderLineView.class)
    .setParameter("id", orderId)
    .getResultList();
~~~

Projection chỉ lấy dữ liệu cần thiết và không buộc Hibernate dựng toàn bộ object graph. Nếu cần lines và tags, có thể query hai DTO result riêng rồi ghép trong service theo `orderId`.

### 12.1. Projection không phù hợp mọi use case

Nếu cần sửa entity, cascade lifecycle, dirty checking hoặc domain methods, managed entities vẫn phù hợp. DTO projection phù hợp cho read model, trang danh sách, báo cáo hoặc API không cần entity state.

Không nên tạo entity graph đầy đủ chỉ để trả vài trường JSON.

## 13. Pagination và collection fetch join

Một vấn đề lớn khác là kết hợp:

~~~java
query.setFirstResult(0);
query.setMaxResults(20);
~~~

với fetch join collection:

~~~java
SELECT o
FROM Order o
LEFT JOIN FETCH o.lines
ORDER BY o.createdAt DESC
~~~

Pagination theo hàng SQL có thể cắt collection giữa chừng. Để bảo đảm collection được nạp đầy đủ, Hibernate có thể phải tải toàn bộ kết quả phù hợp rồi áp dụng giới hạn root ở bộ nhớ. Điều này có thể rất tốn kém.

Hibernate thường cảnh báo khi áp dụng pagination với collection fetch join; cấu hình:

~~~properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

có thể yêu cầu Hibernate ném lỗi thay vì âm thầm thực hiện in-memory pagination. Tên property và behavior cần đối chiếu đúng phiên bản Hibernate.

### 13.1. Hai bước pagination an toàn hơn

Bước 1: phân trang root IDs:

~~~java
List<Long> ids = em.createQuery("""
    SELECT o.id
    FROM Order o
    WHERE o.status = :status
    ORDER BY o.createdAt DESC
    """, Long.class)
    .setParameter("status", OrderStatus.OPEN)
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
~~~

Bước 2: fetch collection cho các root IDs vừa lấy:

~~~java
List<Order> page = em.createQuery("""
    SELECT DISTINCT o
    FROM Order o
    LEFT JOIN FETCH o.lines
    WHERE o.id IN :ids
    """, Order.class)
    .setParameter("ids", ids)
    .getResultList();
~~~

Nếu cần tags, chạy query thứ ba riêng trong cùng persistence context:

~~~java
em.createQuery("""
    SELECT DISTINCT o
    FROM Order o
    LEFT JOIN FETCH o.tags
    WHERE o.id IN :ids
    """, Order.class)
    .setParameter("ids", ids)
    .getResultList();
~~~

Cần xử lý trường hợp `ids` rỗng trước khi chạy query IN. Ngoài ra, SQL IN không đảm bảo thứ tự giống danh sách IDs ban đầu; nếu thứ tự page quan trọng, hãy sắp xếp lại kết quả theo thứ tự ID đã lấy hoặc áp dụng thứ tự rõ ràng trong query phù hợp.

### 13.2. Count query cần tách riêng

Query phân trang thường có count query:

~~~jpql
SELECT COUNT(o)
FROM Order o
WHERE o.status = :status
~~~

Nếu join collection để đếm, một Order có nhiều lines có thể bị đếm nhiều lần. Khi cần join to-many, có thể phải dùng:

~~~jpql
SELECT COUNT(DISTINCT o.id)
FROM Order o
JOIN o.lines l
WHERE ...
~~~

Không dùng fetch join trong count query; count query chỉ cần tính số root phù hợp.

## 14. EAGER mapping không phải giải pháp cho MultipleBagFetchException

Một số người thử chuyển:

~~~java
@OneToMany(fetch = FetchType.LAZY)
private List<OrderLine> lines;
~~~

thành:

~~~java
@OneToMany(fetch = FetchType.EAGER)
private List<OrderLine> lines;
~~~

với hy vọng collection luôn có sẵn. Điều này không giải quyết triệt để vấn đề. EAGER chỉ thể hiện yêu cầu fetch theo mapping; provider vẫn có thể dùng JOIN hoặc SELECT riêng, và việc nhiều collection EAGER có thể làm phát sinh query thừa, N+1 hoặc Cartesian product tùy cách tải.

Nên ưu tiên LAZY cho các association to-many và định nghĩa fetch plan theo use case. Khi cần chi tiết, chọn query/EntityGraph/batch cụ thể thay vì đặt tất cả collection thành EAGER.

## 15. Fetch một collection bằng JOIN FETCH vẫn có thể hợp lý

Không phải mọi JOIN FETCH to-many đều xấu. Nếu một trang chi tiết chỉ cần một collection có kích thước vừa phải:

~~~java
Order order = em.createQuery("""
    SELECT o
    FROM Order o
    LEFT JOIN FETCH o.lines
    WHERE o.id = :id
    """, Order.class)
    .setParameter("id", orderId)
    .getSingleResult();
~~~

một query có thể rất hiệu quả. Vấn đề thường xuất hiện khi **join nhiều collection độc lập cùng lúc**, hoặc join một collection rất lớn với pagination.

Cần đánh giá:

- Collection có kích thước trung bình/tối đa bao nhiêu?
- Có cần toàn bộ phần tử cho use case hiện tại không?
- Root query trả bao nhiêu entity?
- Có thêm collection to-many nào khác được fetch không?
- SQL result set có bị nhân chéo không?
- Query có giới hạn/page không?

## 16. Chọn chiến lược theo tình huống

| Tình huống | Chiến lược nên cân nhắc |
| --- | --- |
| Chi tiết một Order, chỉ cần lines | JOIN FETCH một collection |
| Chi tiết Order cần lines và tags, cả hai là bag | Hai query fetch riêng trong cùng persistence context |
| Danh sách nhiều Order, chỉ một số collection được truy cập | LAZY + `@BatchSize`/default batch size |
| Tải collection cho nhóm owner từ query ban đầu | Hibernate `FetchMode.SUBSELECT` |
| Fetch plan thay đổi theo màn hình | JPA EntityGraph, nhưng kiểm tra SQL |
| API chỉ cần vài trường | DTO projection |
| Phân trang root có to-many | Page root IDs trước, fetch association sau |
| Quan hệ có thứ tự persistent | `@OrderColumn` nếu domain cần thứ tự |
| Collection không có duplicate và không cần thứ tự | Set có thể phù hợp về domain, không chỉ để né exception |
| Nhiều collection rất lớn | Query riêng, batch/subselect hoặc API phân trang collection |

## 17. Ví dụ service tải Order theo hai truy vấn

Một service minh họa:

~~~java
@Service
public class OrderQueryService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public List<Order> findOrdersWithLinesAndTags(List<Long> ids) {
        if (ids.isEmpty()) {
            return List.of();
        }

        List<Order> orders = em.createQuery("""
            SELECT DISTINCT o
            FROM Order o
            LEFT JOIN FETCH o.lines
            WHERE o.id IN :ids
            """, Order.class)
            .setParameter("ids", ids)
            .getResultList();

        em.createQuery("""
            SELECT DISTINCT o
            FROM Order o
            LEFT JOIN FETCH o.tags
            WHERE o.id IN :ids
            """, Order.class)
            .setParameter("ids", ids)
            .getResultList();

        return orders;
    }
}
~~~

Vì cả hai truy vấn nằm trong một transaction và persistence context, query thứ hai tải tags trên các managed Order đã được query trước. Không cần tạo và merge một object graph mới.

Ví dụ này giả định danh sách ID đủ nhỏ cho một câu IN và service chỉ đọc. Nếu `ids` rất lớn, chia batch hoặc phân trang. Nếu cần dữ liệu mới nhất theo isolation khác, transaction boundary cũng phải được thiết kế phù hợp.

### 17.1. Không dựa vào thứ tự của query thứ hai

Query thứ hai chỉ dùng để khởi tạo collection tags; không cần thay thế danh sách `orders` đã lấy ở query đầu. Nếu cần sắp xếp page theo thứ tự IDs hoặc một tiêu chí nghiệp vụ, giữ và áp dụng thứ tự rõ ràng.

### 17.2. Không trả entity ra ngoài transaction rồi truy cập lazy tùy tiện

Service `@Transactional(readOnly = true)` có thể kết thúc persistence context sau khi trả kết quả. Nếu controller/serializer tiếp tục truy cập association lazy chưa được tải, có thể gặp `LazyInitializationException` hoặc phát sinh query ngoài ý định nếu Open Session in View bật.

Hãy tải đúng dữ liệu cần trả hoặc chuyển sang DTO trước khi transaction kết thúc. Hai collection trong ví dụ đã được fetch, nhưng các association khác vẫn có thể lazy.

## 18. Cách quan sát Cartesian product trong SQL

Bật log SQL Hibernate 6 trong môi trường phát triển:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Logger bind có thể chứa dữ liệu nhạy cảm; chỉ bật trong môi trường an toàn.

Khi đọc SQL, kiểm tra:

- Có bao nhiêu JOIN tới bảng collection?
- Có bao nhiêu bảng association/join table?
- Một root ID xuất hiện bao nhiêu lần trong result set?
- Kích thước các collection có làm số hàng nhân lên không?
- Có ORDER BY lớn hoặc DISTINCT làm tăng chi phí sort/hash không?
- Có LIMIT/OFFSET bị đẩy xuống SQL hay pagination xử lý trong bộ nhớ?
- Hibernate có cảnh báo pagination over collection fetch hoặc `MultipleBagFetchException` không?

Có thể kiểm tra execution plan của database để xem join strategy, estimated/actual rows, sort và memory spill. Một query log ngắn không nói đủ về hiệu năng nếu không biết số hàng thực tế.

## 19. Các lỗi và hiểu lầm thường gặp

| Tình huống | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Fetch join hai bag cùng lúc | `MultipleBagFetchException` | Tách query hoặc đổi fetch strategy phù hợp domain |
| Đổi List thành Set chỉ để hết exception | Thay đổi semantics và vẫn có Cartesian product | Chỉ dùng Set khi domain thật sự là tập hợp không thứ tự, không trùng |
| Thêm `@OrderColumn` chỉ để né lỗi | Thêm dữ liệu index và chi phí reorder | Chỉ dùng khi thứ tự là state nghiệp vụ |
| Dùng DISTINCT để mong giảm tích | SQL rows khác child combinations vẫn còn | Tách query/batch |
| Fetch mọi collection trong một câu | Result set tăng theo tích kích thước | Fetch theo use case |
| Dùng pagination với collection fetch join | In-memory pagination hoặc cảnh báo/lỗi | Page root IDs trước |
| Đặt mọi collection EAGER | Query thừa, N+1 hoặc join lớn | LAZY và fetch plan rõ |
| EntityGraph nhiều collection và nghĩ chắc chắn không JOIN | Provider vẫn có thể chọn JOIN | Quan sát SQL và giới hạn graph |
| Fetch hai collection trong hai EntityManager khác nhau | Hai object graph không cùng managed identity | Dùng cùng persistence context hoặc DTO |
| Bulk query rồi dùng collection đã load | Persistence context stale | Clear/refresh hoặc kết thúc context |
| Dùng ManyToMany cho quan hệ có trạng thái | Khó lưu ngày gán, audit, status | Mô hình association entity |

## 20. Quy trình thiết kế fetch plan

Trước khi viết query tải nhiều collection:

1. **Xác định dữ liệu màn hình/use case thực sự cần.** Không tải mọi association chỉ vì entity có chúng.
2. **Liệt kê các quan hệ to-many.** Đặc biệt chú ý `List` không có `@OrderColumn`, có thể mang bag semantics.
3. **Ước lượng kích thước collection.** Tính gần đúng tích số khi join nhiều collection.
4. **Kiểm tra bag semantics.** Nếu nhiều bag cùng được fetch, dự đoán `MultipleBagFetchException`.
5. **Không đổi collection type tùy tiện.** Giữ đúng duplicate/order semantics của domain.
6. **Chọn cách tải.** Một join fetch, nhiều query, batch, subselect, entity graph hoặc projection.
7. **Kiểm tra pagination.** Không phân trang trực tiếp một root query fetch join to-many nếu Hibernate phải in-memory paginate.
8. **Đặt transaction/context hợp lý.** Nhiều query fetch riêng cần cùng persistence context nếu muốn lắp ráp cùng managed graph.
9. **Quan sát SQL và số hàng.** Kiểm tra actual rows, bind parameters và execution plan.
10. **Kiểm thử với dữ liệu đại diện.** Một Order có 2 lines không đại diện cho production nếu thực tế có hàng trăm lines và tags.

## 21. Bài tập thực hành

### Bài 1 — Tính số hàng

Một Order có 8 OrderLine và 5 Tag. Nếu fetch join đồng thời cả hai collection, có thể tạo bao nhiêu tổ hợp hàng SQL cho Order đó? Nếu thêm collection thứ ba có 4 phần tử thì con số thay đổi thế nào?

### Bài 2 — MultipleBagFetchException

Entity Order có hai thuộc tính List:

~~~java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;

@ManyToMany
private List<Tag> tags;
~~~

Một query JOIN FETCH cả hai gây `MultipleBagFetchException`. Hãy giải thích vai trò của bag semantics và vì sao đây không đơn thuần là lỗi cú pháp SQL.

### Bài 3 — List, @OrderBy và @OrderColumn

Giải thích sự khác nhau giữa:

~~~java
private List<OrderLine> lines;
~~~

~~~java
@OrderBy("createdAt ASC")
private List<OrderLine> lines;
~~~

~~~java
@OrderColumn(name = "line_position")
private List<OrderLine> lines;
~~~

Cách nào lưu vị trí phần tử trong database? Cách nào vẫn có thể mang bag semantics?

### Bài 4 — Đổi sang Set

Một developer đổi cả hai List thành Set và query chạy được. Vì sao chưa thể kết luận giải pháp tốt? Nêu ảnh hưởng đến duplicate/order, equals/hashCode và Cartesian product.

### Bài 5 — Tách thành hai query

Viết hai JPQL query: query đầu fetch `Order.lines`, query sau fetch `Order.tags`, dùng cùng persistence context. Vì sao các query có thể cùng khởi tạo một managed Order graph mà không cần một câu JOIN chéo?

### Bài 6 — Pagination

Một repository dùng Pageable cùng `JOIN FETCH o.lines`. Vì sao có thể xảy ra in-memory pagination? Hãy đề xuất cách page IDs trước rồi fetch lines theo IDs.

### Bài 7 — Batch fetching và subselect

Phân biệt `@BatchSize`/`hibernate.default_batch_fetch_size` với Hibernate `FetchMode.SUBSELECT`. Mỗi cách giảm N+1 ra sao và có trade-off nào?

### Bài 8 — EntityGraph

Một EntityGraph chứa cả `lines` và `tags`. Vì sao không thể giả định EntityGraph tự tránh `MultipleBagFetchException` hoặc Cartesian product? Cần quan sát điều gì?

### Gợi ý trả lời

- **Bài 1:** 8 × 5 = 40 hàng; thêm collection 4 phần tử thì 8 × 5 × 4 = 160 tổ hợp.
- **Bài 2:** Hai List không có `@OrderColumn` có thể được Hibernate ánh xạ như hai bag; các tổ hợp JOIN làm mơ hồ việc tái dựng phần tử lặp, nên Hibernate có thể từ chối.
- **Bài 3:** List thường không lưu vị trí nếu không có index; `@OrderBy` sắp xếp khi đọc; `@OrderColumn` lưu index persistent.
- **Bài 4:** Set đổi semantics, yêu cầu equals/hashCode đúng và không loại bỏ tích Cartesian trong SQL.
- **Bài 5:** Query thứ hai chạy cùng persistence context nên tìm lại managed root hiện có và khởi tạo collection còn lại.
- **Bài 6:** Pagination theo SQL rows có thể cắt collection; Hibernate có thể lấy toàn bộ rồi phân trang trong bộ nhớ. Page IDs trước tránh vấn đề.
- **Bài 7:** Batch gom owner IDs vào các SELECT theo nhóm; subselect dùng truy vấn owner ban đầu làm cơ sở tải collection cho nhóm.
- **Bài 8:** EntityGraph mô tả association cần fetch, không đảm bảo provider dùng nhiều SELECT; kiểm tra SQL, bag semantics, số hàng và pagination.

---

**Ghi nhớ:** Fetch join nhiều collection to-many có thể tạo tích Descartes, khiến số hàng SQL tăng theo tích kích thước các collection. Khi nhiều collection mang bag semantics, Hibernate có thể ném `MultipleBagFetchException`. **Tách truy vấn, batch fetching, subselect hoặc DTO projection** thường là những cách kiểm soát dữ liệu tốt hơn. Chỉ đổi List thành Set hoặc thêm `@OrderColumn` khi semantics của domain thực sự yêu cầu thay đổi; các workaround đó không tự loại bỏ Cartesian product.
