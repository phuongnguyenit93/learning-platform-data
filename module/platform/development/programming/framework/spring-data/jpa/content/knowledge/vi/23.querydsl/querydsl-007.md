# Phân trang, sắp xếp và kiểm soát count query với Querydsl

Querydsl cho phép xây dựng truy vấn động có sắp xếp và phân trang mà vẫn giữ được kiểu dữ liệu của thuộc tính Entity. Trong Spring Data JPA, có hai mức sử dụng chính:

- **QuerydslPredicateExecutor:** cung cấp các phương thức tiện lợi như findAll(predicate, pageable). Spring Data quản lý truy vấn nội dung và count query.
- **Custom repository với JPAQueryFactory:** cho phép kiểm soát SELECT, JOIN, ORDER BY, LIMIT/OFFSET và count query riêng.

Lựa chọn phụ thuộc vào độ phức tạp của truy vấn. Predicate đơn giản thường dùng được QuerydslPredicateExecutor. Khi JOIN collection, DISTINCT, GROUP BY/HAVING, projection hoặc tối ưu chi phí đếm trở nên quan trọng, custom repository giúp kiểm soát rõ hơn cách lấy dữ liệu và cách tính tổng số.

## 1. Phân trang trong Querydsl là gì?

Phân trang chia tập kết quả thành các phần nhỏ. Ví dụ một màn hình chỉ hiển thị 20 khách hàng mỗi lần, thay vì tải toàn bộ khách hàng về bộ nhớ.

Spring Data biểu diễn yêu cầu phân trang bằng Pageable. Pageable chứa:
- Số trang, bắt đầu từ 0.
- Kích thước trang.
- Thông tin sắp xếp.
- Offset được tính từ số trang và kích thước trang.

Ví dụ:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("name"),
                Sort.Order.asc("id")
        )
);
~~~

Đây là trang đầu tiên, tối đa 20 phần tử, sắp xếp theo name rồi id. Việc thêm id làm tiêu chí phụ giúp thứ tự xác định khi nhiều khách hàng có cùng tên.

Với Querydsl, Spring Data có thể chuyển Pageable thành giới hạn và sắp xếp cho truy vấn. Nếu trả về Page<T>, framework còn phải cung cấp totalElements và totalPages, nên có thể cần truy vấn đếm riêng.

## 2. Dùng QuerydslPredicateExecutor với Pageable

Repository có thể kế thừa QuerydslPredicateExecutor:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
~~~

Ví dụ tạo predicate và gọi findAll:

~~~java
QCustomer customer = QCustomer.customer;

BooleanBuilder predicate = new BooleanBuilder()
        .and(customer.active.isTrue());

if (keyword != null && !keyword.isBlank()) {
    predicate.and(customer.name.containsIgnoreCase(keyword));
}

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("name"),
                Sort.Order.asc("id")
        )
);

Page<Customer> page =
        customerRepository.findAll(predicate, pageable);
~~~

Spring Data thực hiện truy vấn phù hợp với predicate và pageable, đồng thời cung cấp tổng số phần tử cho Page. Ứng dụng có thể dùng:

~~~java
List<Customer> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
~~~

Ưu điểm của cách này là ít mã và phù hợp với bộ lọc động thông thường. Đổi lại, ta ít kiểm soát trực tiếp cấu trúc count query. Nếu cần DISTINCT, truy vấn nhóm hoặc count đặc biệt, nên chuyển sang custom repository.

## 3. Page, Slice và List khác nhau thế nào?

| Kiểu trả về | Dữ liệu trang | Tổng số chính xác | Count query |
|---|---|---|---|
| Page<T> | Có | Có | Có thể cần |
| Slice<T> | Có | Không | Không cần đếm toàn bộ |
| List<T> với Pageable | Có giới hạn | Không | Không cần đếm toàn bộ |

Page phù hợp khi giao diện cần hiển thị tổng số bản ghi hoặc tổng số trang. Slice phù hợp với nút “Tải thêm” hoặc chuyển trang tiếp theo mà không cần biết tổng số. List với Pageable chỉ trả nội dung giới hạn.

QuerydslPredicateExecutor cung cấp findAll(predicate, pageable) trả Page. Nếu cần Slice hoặc muốn tự quyết định cách lấy thêm một dòng để kiểm tra hasNext, có thể viết custom query với JPAQueryFactory.

Đừng chọn Page chỉ vì muốn dùng Pageable. Nếu giao diện chỉ cần nội dung và biết còn dữ liệu hay không, việc đếm toàn bộ kết quả có thể là chi phí không cần thiết.

## 4. Sắp xếp bằng Sort

Với QuerydslPredicateExecutor, có thể truyền Sort trực tiếp:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);

Iterable<Customer> customers =
        customerRepository.findAll(predicate, sort);
~~~

Tên thuộc tính trong Sort là tên thuộc tính Java của Entity, không phải tên cột SQL. Ví dụ dùng createdAt nếu Entity khai báo createdAt, dù cột database có thể tên created_at.

Khi dùng Pageable, Sort có thể nằm ngay trong PageRequest:

~~~java
Pageable pageable = PageRequest.of(
        1,
        25,
        Sort.by("createdAt").descending()
                .and(Sort.by("id").ascending())
);
~~~

Chỉ dùng các thuộc tính được phép sắp xếp. Nếu Sort đến từ request của người dùng, hãy whitelist tên thuộc tính hợp lệ; không chuyển nguyên chuỗi tùy ý thành biểu thức query.

## 5. Vì sao cần thứ tự sắp xếp ổn định?

Phân trang dựa trên một thứ tự không xác định có thể gây ra bản ghi lặp hoặc bị bỏ qua giữa các lần gọi.

Giả sử nhiều khách hàng có cùng name và truy vấn chỉ ORDER BY name. Database không bắt buộc giữ thứ tự ổn định giữa các dòng có cùng giá trị name. Khi trang đầu và trang sau được lấy ở hai thời điểm khác nhau, thứ tự giữa các bản ghi trùng tên có thể thay đổi.

Nên thêm một khóa duy nhất làm tie-breaker:

~~~java
.orderBy(customer.name.asc(), customer.id.asc())
~~~

Quy tắc này hữu ích cho cả offset pagination lẫn keyset pagination. Với khóa chính ghép, cần đưa đủ các thành phần cần thiết để xác định duy nhất thứ tự.

## 6. Khi nào cần custom repository với JPAQueryFactory?

QuerydslPredicateExecutor phù hợp với việc tìm Entity theo Predicate. Khi cần kiểm soát rõ:
- Các JOIN và fetch join.
- Projection DTO.
- DISTINCT và cách đếm Entity duy nhất.
- GROUP BY/HAVING.
- Count query riêng.
- Sort động theo whitelist.
- Cách bỏ qua count query khi không cần.

hãy dùng custom repository với JPAQueryFactory.

Khai báo fragment:

~~~java
public interface CustomerSearchRepository {
    Page<Customer> search(
            BooleanBuilder predicate,
            Pageable pageable
    );
}
~~~

Repository chính:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer>,
                CustomerSearchRepository {
}
~~~

Implementation fragment theo quy ước Spring Data:

~~~java
public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private final JPAQueryFactory queryFactory;

    public CustomerSearchRepositoryImpl(JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    // Phần triển khai search() ở các mục tiếp theo.
}
~~~

Có thể khai báo JPAQueryFactory thành bean nhận EntityManager:

~~~java
@Configuration
public class QuerydslConfiguration {

    @Bean
    JPAQueryFactory jpaQueryFactory(EntityManager entityManager) {
        return new JPAQueryFactory(entityManager);
    }
}
~~~

Đặt implementation trong package mà cấu hình Spring Data repository có thể phát hiện. Không đặt truy vấn persistence trực tiếp trong controller.

## 7. Áp dụng offset và limit thủ công

JPAQueryFactory cho phép điều khiển giới hạn bằng offset() và limit():

~~~java
QCustomer customer = QCustomer.customer;

List<Customer> content = queryFactory
        .selectFrom(customer)
        .where(predicate)
        .orderBy(customer.name.asc(), customer.id.asc())
        .offset(pageable.getOffset())
        .limit(pageable.getPageSize())
        .fetch();
~~~

Ý nghĩa:
- offset() bỏ qua số dòng đứng trước vị trí trang.
- limit() giới hạn số dòng trả về.
- fetch() thực thi truy vấn và trả List.

pageable.getOffset() trả về long, phù hợp với offset của Querydsl. Pageable dùng chỉ số trang bắt đầu từ 0.

Đây mới là truy vấn nội dung. Nếu muốn trả Page<Customer>, còn phải tính totalElements bằng một count query tương ứng hoặc dùng tiện ích Spring Data để trì hoãn việc đếm.

## 8. Viết count query riêng

Ví dụ count query đơn giản:

~~~java
Long total = queryFactory
        .select(customer.id.count())
        .from(customer)
        .where(predicate)
        .fetchOne();

long totalElements = total == null ? 0L : total;
~~~

Count query phải giữ các điều kiện lọc làm thay đổi tập kết quả. Không cần ORDER BY vì kết quả chỉ là một số đếm.

Có thể đóng gói content và total thành Page:

~~~java
return new PageImpl<>(
        content,
        pageable,
        totalElements
);
~~~

PageImpl cần:
- Danh sách nội dung.
- Pageable dùng để lấy trang.
- Tổng số phần tử logic của toàn bộ kết quả.

Ví dụ này giả định mỗi Customer xuất hiện một lần trong truy vấn nội dung và không có JOIN collection gây nhân bản dòng. Nếu có JOIN collection, count query có thể cần COUNT(DISTINCT customer.id).

## 9. Dùng PageableExecutionUtils để tránh count không cần thiết

Spring Data cung cấp PageableExecutionUtils.getPage(). Tiện ích này nhận content, Pageable và một Supplier<Long> để chỉ chạy count khi không thể suy ra tổng số từ nội dung trang.

Ví dụ:

~~~java
List<Customer> content = queryFactory
        .selectFrom(customer)
        .where(predicate)
        .orderBy(customer.name.asc(), customer.id.asc())
        .offset(pageable.getOffset())
        .limit(pageable.getPageSize())
        .fetch();

return PageableExecutionUtils.getPage(
        content,
        pageable,
        () -> {
            Long total = queryFactory
                    .select(customer.id.count())
                    .from(customer)
                    .where(predicate)
                    .fetchOne();

            return total == null ? 0L : total;
        }
);
~~~

Nếu nội dung trang cho phép framework suy ra tổng số, Supplier có thể không được gọi. Ví dụ trang đầu trả ít hơn page size thường cho thấy không còn kết quả phía sau. Nếu trang đầy đủ, framework thường cần count query để biết tổng số.

Điểm quan trọng là không thực hiện fetchOne() trước rồi mới truyền giá trị vào getPage(). Nếu làm như vậy, count query đã chạy ngay và không còn được trì hoãn.

## 10. Ví dụ custom repository hoàn chỉnh cho truy vấn đơn giản

Đây là cấu trúc triển khai ghép truy vấn nội dung, sắp xếp mặc định và count query:

~~~java
public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private final JPAQueryFactory queryFactory;

    public CustomerSearchRepositoryImpl(JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    @Override
    public Page<Customer> search(
            BooleanBuilder predicate,
            Pageable pageable) {

        QCustomer customer = QCustomer.customer;

        JPAQuery<Customer> query = queryFactory
                .selectFrom(customer)
                .where(predicate);

        query.orderBy(customer.name.asc(), customer.id.asc());

        List<Customer> content = query
                .offset(pageable.getOffset())
                .limit(pageable.getPageSize())
                .fetch();

        return PageableExecutionUtils.getPage(
                content,
                pageable,
                () -> {
                    Long total = queryFactory
                            .select(customer.id.count())
                            .from(customer)
                            .where(predicate)
                            .fetchOne();

                    return total == null ? 0L : total;
                }
        );
    }
}
~~~

Đây là ví dụ cho truy vấn chỉ lọc trên Customer, không JOIN collection và không GROUP BY. Trong ứng dụng thực tế, cần xử lý Pageable.unpaged() nếu API cho phép yêu cầu không phân trang, đồng thời kiểm tra kích thước trang và giới hạn tối đa ở tầng service/API.

Nếu có Sort từ Pageable, phần orderBy cần chuyển Sort sang các OrderSpecifier an toàn như mục tiếp theo.

## 11. Chuyển Sort thành OrderSpecifier an toàn

JPAQueryFactory dùng OrderSpecifier của Querydsl thay vì nhận trực tiếp Spring Data Sort. Có thể ánh xạ các thuộc tính được cho phép bằng switch:

~~~java
private OrderSpecifier<?> toOrderSpecifier(
        Sort.Order order,
        QCustomer customer) {

    boolean ascending = order.isAscending();

    return switch (order.getProperty()) {
        case "name" ->
                ascending ? customer.name.asc() : customer.name.desc();

        case "createdAt" ->
                ascending ? customer.createdAt.asc()
                          : customer.createdAt.desc();

        case "id" ->
                ascending ? customer.id.asc() : customer.id.desc();

        default ->
                throw new IllegalArgumentException(
                        "Unsupported sort property: " + order.getProperty()
                );
    };
}
~~~

Áp dụng trong truy vấn:

~~~java
List<OrderSpecifier<?>> orders = new ArrayList<>();

for (Sort.Order order : pageable.getSort()) {
    orders.add(toOrderSpecifier(order, customer));
}

if (orders.stream().noneMatch(
        order -> pageable.getSort().getOrderFor("id") != null)) {
    orders.add(customer.id.asc());
}

query.orderBy(orders.toArray(OrderSpecifier<?>[]::new));
~~~

Trong code production, nên kiểm tra và thêm tie-breaker ID rõ ràng. Đoạn minh họa có thể viết gọn hơn bằng cách kiểm tra Sort trước khi thêm ID:

~~~java
boolean sortsById =
        pageable.getSort().getOrderFor("id") != null;

if (!sortsById) {
    orders.add(customer.id.asc());
}
~~~

Whitelist giúp tránh việc đưa tên thuộc tính tùy ý từ request vào query. Nếu hỗ trợ ignoreCase hoặc null handling, hãy ánh xạ các tùy chọn đó một cách tường minh. Không mặc định mọi thuộc tính đều có thể sắp xếp hoặc mọi database có cùng thứ tự NULL.

## 12. JOIN collection và COUNT(DISTINCT)

JOIN collection có thể làm một Entity xuất hiện trên nhiều dòng kết quả SQL. Khi đó, count query dùng COUNT(entity.id) có thể đếm trùng.

Ví dụ Customer có nhiều Order:

~~~java
QCustomer customer = QCustomer.customer;
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;

List<Customer> content = queryFactory
        .selectFrom(customer)
        .join(customer.orders, order)
        .where(order.status.eq(OrderStatus.PAID))
        .distinct()
        .orderBy(customer.id.asc())
        .offset(pageable.getOffset())
        .limit(pageable.getPageSize())
        .fetch();
~~~

Count tương ứng:

~~~java
Long total = queryFactory
        .select(customer.id.countDistinct())
        .from(customer)
        .join(customer.orders, order)
        .where(order.status.eq(OrderStatus.PAID))
        .fetchOne();
~~~

COUNT(DISTINCT customer.id) đếm mỗi Customer một lần dù một khách hàng có nhiều Order phù hợp.

Nếu chỉ cần kiểm tra có đơn hàng phù hợp, có thể viết điều kiện EXISTS để tránh nhân bản dòng Customer do JOIN. Dù chọn JOIN hay EXISTS, count query phải phản ánh cùng một tập Customer logic mà truy vấn nội dung trả về.

Không dùng COUNT(DISTINCT) một cách máy móc. Nếu quan hệ JOIN không thể nhân bản Entity phía được chọn, COUNT thông thường có thể đủ. Hãy xác định cardinality của quan hệ và kiểm tra kết quả thực tế.

## 13. Count query cho GROUP BY và HAVING

Truy vấn nhóm trả về một dòng cho mỗi nhóm. Vì vậy, totalElements phải là số nhóm thỏa HAVING, không phải số dòng nguồn trước khi nhóm.

Ví dụ truy vấn tổng số đơn hàng theo trạng thái:

~~~java
List<Tuple> groups = queryFactory
        .select(order.status, order.id.count())
        .from(order)
        .where(predicate)
        .groupBy(order.status)
        .having(order.id.count().goe(minimumCount))
        .fetch();
~~~

Nếu cần Page cho kết quả nhóm, count query phải đếm số trạng thái có nhóm đạt minimumCount. Đây là bài toán khác với đếm số Order.

JPQL không cung cấp derived table trong FROM theo chuẩn để bọc một truy vấn GROUP BY rồi COUNT(*) bên ngoài. Querydsl JPA cũng chịu giới hạn này. Với grouped count phức tạp, các lựa chọn gồm:
- Viết một truy vấn riêng tương đương để đếm số khóa nhóm.
- Dùng native SQL với derived table/CTE nếu database hỗ trợ.
- Dùng view hoặc bảng tổng hợp nếu báo cáo được gọi thường xuyên.
- Trả về Slice hoặc danh sách giới hạn nếu không cần tổng số nhóm chính xác.

Không dùng một count query chỉ đếm dòng nguồn rồi gán vào Page nhóm. totalElements sẽ sai khi nhiều dòng nguồn thuộc cùng một nhóm.

## 14. Vì sao không nên dựa vào fetchCount() cho mọi truy vấn?

Một số ví dụ Querydsl cũ dùng:

~~~java
long total = query.fetchCount();
~~~

hoặc:

~~~java
QueryResults<Customer> results = query.fetchResults();
~~~

Các API fetchCount() và fetchResults() đã bị deprecated trong Querydsl 5.x. Với truy vấn có GROUP BY/HAVING phức tạp, việc tính số kết quả có thể phải tải các nhóm về bộ nhớ rồi đếm thay vì thực hiện một COUNT SQL đơn giản. Cách đó có thể rất tốn kém.

Với truy vấn đơn giản, hãy viết count query riêng bằng select(count(...)). Với JOIN collection, cân nhắc countDistinct(). Với grouped query, thiết kế cách đếm nhóm riêng hoặc dùng native SQL phù hợp.

Không thay một count query phức tạp bằng fetchCount() mà chưa hiểu SQL và chi phí thực tế của phiên bản Querydsl đang dùng.

## 15. Tránh count query khi chỉ cần biết còn dữ liệu

Nếu không cần totalElements, có thể lấy pageSize + 1 phần tử. Phần tử dư dùng để xác định còn trang sau.

Ví dụ:

~~~java
int pageSize = pageable.getPageSize();

List<Customer> rows = queryFactory
        .selectFrom(customer)
        .where(predicate)
        .orderBy(customer.id.asc())
        .offset(pageable.getOffset())
        .limit(pageSize + 1L)
        .fetch();

boolean hasNext = rows.size() > pageSize;

List<Customer> content = hasNext
        ? rows.subList(0, pageSize)
        : rows;

return new SliceImpl<>(content, pageable, hasNext);
~~~

Slice không có totalElements hoặc totalPages. Cách này phù hợp với giao diện tải thêm và giúp tránh truy vấn đếm toàn bộ tập kết quả.

QuerydslPredicateExecutor không cung cấp cùng kiểu điều khiển count tùy chỉnh cho mọi trường hợp Slice; custom repository giúp thực hiện mẫu pageSize + 1 này.

## 16. Offset pagination và chi phí trang sâu

Offset pagination thường được dịch thành LIMIT/OFFSET hoặc cú pháp tương đương:

~~~sql
SELECT ...
FROM customers
ORDER BY id
LIMIT 20 OFFSET 100000;
~~~

Khi offset lớn, database có thể phải duyệt và bỏ qua nhiều dòng trước khi trả 20 dòng cần thiết. Vì vậy, trang càng sâu có thể càng chậm.

Offset vẫn hữu ích khi:
- Dữ liệu không quá lớn.
- Người dùng cần nhảy đến một trang cụ thể.
- Trang sâu không phải use case phổ biến.
- Truy vấn có index và execution plan phù hợp.

Nếu cần đọc tuần tự hàng trăm nghìn hoặc hàng triệu bản ghi, cân nhắc keyset/seek pagination.

## 17. Keyset pagination với Querydsl

Keyset pagination dùng giá trị sort của phần tử cuối cùng đã đọc để tìm phần tử tiếp theo. Ví dụ sắp xếp giảm dần theo createdAt rồi id:

~~~java
.orderBy(customer.createdAt.desc(), customer.id.desc())
~~~

Sau khi đọc phần tử cuối có createdAt = lastCreatedAt và id = lastId, điều kiện tiếp theo là:

~~~java
BooleanExpression afterCursor =
        customer.createdAt.lt(lastCreatedAt)
                .or(
                    customer.createdAt.eq(lastCreatedAt)
                            .and(customer.id.lt(lastId))
                );
~~~

Truy vấn tiếp theo:

~~~java
List<Customer> nextBatch = queryFactory
        .selectFrom(customer)
        .where(predicate, afterCursor)
        .orderBy(customer.createdAt.desc(), customer.id.desc())
        .limit(batchSize)
        .fetch();
~~~

Vì thứ tự là giảm dần, các bản ghi tiếp theo có createdAt nhỏ hơn; nếu createdAt bằng nhau, ID phải nhỏ hơn. Nếu sắp xếp tăng dần, đổi các phép so sánh thành lớn hơn.

Keyset thường tránh chi phí bỏ qua offset lớn, nhưng yêu cầu:
- Sort ổn định và có khóa phụ duy nhất.
- Các trường cursor có giá trị không-null.
- Cursor giữ đúng giá trị của phần tử cuối.
- Index phù hợp với điều kiện lọc và thứ tự.
- Xử lý rõ dữ liệu thay đổi trong lúc cuộn.

Keyset phù hợp với “tiếp theo” hoặc batch processing; không thuận tiện để nhảy trực tiếp đến trang số 500 như offset.

## 18. Thiết kế index cho truy vấn phân trang

Index nên phản ánh điều kiện lọc và thứ tự sắp xếp thường dùng.

Ví dụ:

~~~sql
SELECT *
FROM customers
WHERE active = true
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Có thể xem xét index kết hợp:

~~~sql
CREATE INDEX idx_customers_active_created_id
ON customers (active, created_at DESC, id DESC);
~~~

Đây chỉ là ví dụ định hướng. Cấu trúc index thực tế phụ thuộc database, độ chọn lọc của active, điều kiện tenant, các bộ lọc khác và workload ghi.

Với truy vấn JOIN theo khóa ngoại, index trên foreign key có thể giúp tìm bản ghi liên quan. Với COUNT(DISTINCT), database có thể cần bước sort hoặc hash để loại trùng.

Dùng EXPLAIN hoặc EXPLAIN ANALYZE để kiểm tra:
- Index có được dùng không?
- Bao nhiêu dòng được đọc?
- Có sort lớn hoặc hash aggregate không?
- Count query có đắt hơn truy vấn nội dung không?
- Trang sâu có tăng chi phí rõ rệt không?

Không tạo index chỉ dựa vào tên method. Đo trên dữ liệu gần production và cân nhắc chi phí INSERT/UPDATE/DELETE cùng dung lượng lưu trữ.

## 19. Tính nhất quán khi dữ liệu thay đổi đồng thời

Truy vấn nội dung và count query thường là hai câu SQL riêng. Nếu một transaction khác thêm hoặc xóa bản ghi giữa hai lần thực thi, totalElements có thể không khớp tuyệt đối với nội dung vừa đọc.

Offset pagination cũng nhạy với việc chèn/xóa bản ghi trước vị trí offset. Keyset ít phụ thuộc vào số dòng đã bỏ qua, nhưng vẫn có thể bị ảnh hưởng nếu giá trị sort thay đổi hoặc bản ghi bị xóa.

Nếu nghiệp vụ cần snapshot nhất quán, hãy xem xét transaction isolation và khả năng snapshot của database. Với batch/export dài, có thể giới hạn tập dữ liệu theo mốc thời gian hoặc ID cao nhất tại lúc bắt đầu. Nếu tiến trình có retry, thiết kế xử lý idempotent để tránh ghi nhận trùng.

Không giả định Page hoặc cursor tự bảo đảm một snapshot bất biến trong mọi mức isolation.

## 20. Kiểm thử phân trang và count query

Một integration test nên kiểm tra cả content lẫn totalElements:

~~~java
@DataJpaTest
class CustomerSearchRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void returnsCorrectPageAndTotal() {
        repository.save(new Customer("An", true));
        repository.save(new Customer("Binh", true));
        repository.save(new Customer("Chi", false));

        Pageable pageable = PageRequest.of(
                0,
                1,
                Sort.by("id").ascending()
        );

        Page<Customer> page =
                repository.findAll(
                        QCustomer.customer.active.isTrue(),
                        pageable
                );

        assertEquals(1, page.getContent().size());
        assertEquals(2, page.getTotalElements());
        assertEquals(2, page.getTotalPages());
        assertTrue(page.hasNext());
    }
}
~~~

Ví dụ cần Entity Customer có constructor tương ứng và Repository kế thừa QuerydslPredicateExecutor. QCustomer phải được sinh bởi annotation processor.

Với custom count query, bổ sung các trường hợp:
1. Tập kết quả rỗng: totalElements bằng 0.
2. Số kết quả nhỏ hơn page size.
3. Trang đầy đủ và trang cuối.
4. JOIN collection có nhiều bản ghi liên quan cho cùng Entity.
5. COUNT(DISTINCT) trả đúng số Entity duy nhất.
6. GROUP BY/HAVING đếm số nhóm thay vì số dòng nguồn.
7. Sort có giá trị trùng và ID làm tie-breaker.
8. Keyset không lặp hoặc bỏ sót khi dữ liệu ổn định.
9. Native count query chạy trên database mục tiêu.
10. Tenant và soft-delete filter được áp dụng nhất quán cho cả content và count.

Đo SQL và execution plan trên database production-like. H2 hoặc dữ liệu vài dòng không đủ để đánh giá chi phí count trên bảng lớn.

## 21. Những lỗi thường gặp

**Chỉ phân trang truy vấn nội dung mà quên count**

Nếu trả Page tự tạo, totalElements phải phản ánh toàn bộ tập kết quả. Dùng count query tương ứng hoặc PageableExecutionUtils.

**Count query thiếu điều kiện WHERE**

Nội dung trang có thể đúng nhưng totalElements quá lớn. Giữ mọi điều kiện ảnh hưởng đến tập kết quả.

**Đếm trùng sau JOIN collection**

Dùng COUNT(DISTINCT entity.id) khi truy vấn logic trả Entity duy nhất nhưng JOIN tạo nhiều dòng.

**Đếm dòng nguồn thay vì số nhóm**

Với GROUP BY/HAVING, count phải đếm số nhóm thỏa điều kiện.

**Đưa ORDER BY vào count query**

Thường không cần thiết và có thể tạo chi phí thừa. Count chỉ cần tính số lượng.

**Chuyển Sort đầu vào thẳng thành tên thuộc tính động**

Whitelist thuộc tính và hướng sắp xếp được phép. Không cho client điều khiển identifier tùy ý.

**Không có tie-breaker**

Sort không duy nhất có thể khiến bản ghi lặp hoặc thiếu giữa các trang. Thêm khóa chính vào cuối thứ tự.

**Dùng Page trong feed chỉ cần tải tiếp**

Dùng Slice hoặc pageSize + 1 để tránh count không cần thiết.

**Dùng fetchCount() cho truy vấn grouped phức tạp**

Các API cũ fetchCount()/fetchResults() đã deprecated trong Querydsl 5.x và có thể đếm nhóm bằng cách tải kết quả về bộ nhớ. Viết count riêng hoặc dùng native SQL phù hợp.

**Dùng offset rất sâu cho batch lớn**

Cân nhắc keyset pagination với sort ổn định và index phù hợp.

**Cho rằng count và content luôn cùng snapshot**

Hai câu SQL có thể quan sát dữ liệu ở các thời điểm khác nhau tùy isolation level.

## 22. Quy trình chọn cách phân trang và đếm

Khi thiết kế truy vấn Querydsl, hãy làm theo các bước:

1. Xác định giao diện có cần tổng số chính xác không.
2. Dùng QuerydslPredicateExecutor nếu predicate và phân trang đơn giản.
3. Dùng custom repository với JPAQueryFactory khi cần kiểm soát JOIN, projection, DISTINCT hoặc count.
4. Tạo thứ tự sắp xếp ổn định, có ID làm tie-breaker.
5. Ánh xạ Sort bằng whitelist sang OrderSpecifier.
6. Với Page, giữ count query tương ứng với tập kết quả logic.
7. Với JOIN collection, kiểm tra duplicate và cân nhắc countDistinct().
8. Với GROUP BY/HAVING, đếm số nhóm, không đếm dòng nguồn.
9. Dùng PageableExecutionUtils nếu có thể suy ra tổng số mà không chạy count.
10. Dùng Slice/pageSize + 1 nếu không cần totalElements.
11. Dùng keyset khi đọc tuần tự tập dữ liệu lớn và có sort key phù hợp.
12. Kiểm tra index, SQL, execution plan, transaction isolation và integration test trên database mục tiêu.

## 23. Kết luận

Querydsl có thể kết hợp với Pageable thông qua QuerydslPredicateExecutor để tạo Page và count tự động; khi cần kiểm soát sâu hơn, custom repository với JPAQueryFactory cho phép viết riêng truy vấn nội dung và count query. Hãy dùng COUNT(DISTINCT id) khi JOIN collection làm nhân bản Entity, đếm số nhóm khi có GROUP BY/HAVING và dùng PageableExecutionUtils để trì hoãn count nếu tổng số có thể suy ra. Page phù hợp khi cần tổng số chính xác; Slice phù hợp khi chỉ cần biết còn dữ liệu. Offset dễ triển khai nhưng có thể chậm ở trang sâu, còn keyset phù hợp với luồng tuần tự lớn có thứ tự ổn định và index tốt. Luôn kiểm tra SQL, execution plan và tính đúng của totalElements bằng integration test.
