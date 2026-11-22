# Collection, List, Set và hợp đồng thứ tự kết quả

Spring Data JPA cho phép repository trả về nhiều kiểu collection như Collection, List và Set. Các kiểu này có hợp đồng Java khác nhau: Collection là abstraction tổng quát, List giữ vị trí phần tử và cho phép phần tử trùng, còn Set không cho phần tử trùng theo quy tắc equals() nhưng không cam kết thứ tự duyệt. Những hợp đồng đó cần được phân biệt với thứ tự mà database trả về.

Một truy vấn chỉ có thứ tự xác định khi query có ORDER BY hoặc repository nhận Sort/Pageable có sắp xếp. Khai báo kiểu trả về là List không tự làm kết quả được sắp xếp; khai báo Set cũng không thay thế SELECT DISTINCT. Bài học này giải thích cách chọn kiểu trả về, cách bảo đảm thứ tự ổn định, cách xử lý kết quả trùng do JOIN, cách sắp xếp collection quan hệ và các lưu ý khi phân trang.

## 1. Ba kiểu collection có hợp đồng khác nhau

Java định nghĩa Collection là giao diện gốc cho nhóm collection. List và Set là hai kiểu con có quy tắc riêng.

| Kiểu | Cho phép phần tử trùng? | Hợp đồng thứ tự | Khi phù hợp |
|---|---|---|---|
| Collection<T> | Có | Không cam kết thứ tự hoặc vị trí | Caller chỉ cần duyệt kết quả |
| List<T> | Có | Có thứ tự theo vị trí trong danh sách | Cần hiển thị, phân trang hoặc giữ thứ tự query |
| Set<T> | Không, theo equals() | Không cam kết thứ tự duyệt | Cần tập phần tử duy nhất, không phụ thuộc vị trí |

Một số điểm cần nhớ:

- **Collection** không nói rõ có thứ tự hay không và cũng không loại trùng.
- **List** có index, giữ thứ tự phần tử được đưa vào list và cho phép nhiều phần tử bằng nhau.
- **Set** loại phần tử trùng theo quy tắc equality của implementation; Set nói chung không cam kết thứ tự lặp qua phần tử.
- **HashSet** không bảo đảm thứ tự lặp.
- **LinkedHashSet** giữ thứ tự chèn, nhưng không nên dựa vào implementation cụ thể mà Spring Data dùng để suy ra hợp đồng repository.
- **TreeSet** duy trì thứ tự theo comparator hoặc natural ordering, nhưng cần entity có quy tắc so sánh phù hợp và việc chuyển đổi kết quả sang kiểu đó phải được cấu hình, kiểm thử rõ ràng.

Chọn kiểu trả về theo ý nghĩa dữ liệu mà tầng gọi cần. Nếu người dùng cần kết quả theo thứ tự, List là lựa chọn rõ ràng. Nếu cần loại trùng theo equality, Set có thể phù hợp, nhưng cần hiểu equals() và hashCode() của phần tử.

## 2. Kiểu List không tự bảo đảm thứ tự database

Ví dụ repository:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);
}
~~~

Method trả về List, do đó caller có thể truy cập theo index. Nhưng query không có ORDER BY nên database được quyền trả các hàng theo bất kỳ thứ tự nào phù hợp với execution plan.

Thứ tự có thể thay đổi khi:

- Database chọn execution plan khác.
- Index được tạo hoặc thay đổi.
- Dữ liệu được thêm, xóa hoặc cập nhật.
- Database được nâng cấp.
- Query chạy trên hệ quản trị khác.

Không nên dựa vào thứ tự vật lý của bảng, thứ tự ID tự nhiên hoặc thứ tự insert. Nếu nghiệp vụ yêu cầu kết quả theo thời gian, tên hoặc mức ưu tiên, phải khai báo rõ tiêu chí sắp xếp.

Ví dụ JPQL:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
List<PurchaseOrder> findByStatusOrdered(
    @Param("status") OrderStatus status
);
~~~

ORDER BY xác định thứ tự kết quả theo createdAt giảm dần, sau đó theo id giảm dần. Khóa chính được thêm làm tiêu chí phụ để xử lý trường hợp nhiều đơn có cùng createdAt.

## 3. Sắp xếp bằng derived query

Spring Data JPA cho phép khai báo thứ tự cố định ngay trong tên method:

~~~java
List<PurchaseOrder> findByStatusOrderByCreatedAtDescIdDesc(
    OrderStatus status
);
~~~

Tên method được phân tích như sau:

- findByStatus: lọc theo thuộc tính status.
- OrderByCreatedAtDesc: sắp xếp createdAt giảm dần.
- IdDesc: nếu createdAt bằng nhau, sắp xếp id giảm dần.

Cách này thích hợp khi một repository method luôn có cùng quy tắc sắp xếp.

Có thể dùng First hoặc Top để giới hạn số kết quả:

~~~java
Optional<PurchaseOrder> findFirstByStatusOrderByCreatedAtDescIdDesc(
    OrderStatus status
);
~~~

Method này lấy tối đa một đơn hàng mới nhất theo thứ tự đã chỉ định. Nếu không có bản ghi phù hợp, Optional rỗng.

Không dùng First/Top nếu chưa xác định thứ tự mà nghiệp vụ mong muốn. Giới hạn số dòng mà không có ORDER BY vẫn có thể trả về một bản ghi khác nhau giữa các lần chạy.

## 4. Sắp xếp động bằng Sort

Khi caller cần chọn thứ tự ở thời điểm chạy, repository nhận Sort:

~~~java
List<PurchaseOrder> findByStatus(
    OrderStatus status,
    Sort sort
);
~~~

Cách gọi:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

List<PurchaseOrder> orders =
    repository.findByStatus(OrderStatus.PAID, sort);
~~~

Sort có thể chứa nhiều tiêu chí. Database áp dụng tiêu chí theo thứ tự khai báo: createdAt trước, id sau.

Tên thuộc tính trong Sort là tên property Java của entity, không phải tên cột SQL. Nếu field createdAt được ánh xạ bằng @Column(name = "created_at"), Sort vẫn dùng createdAt.

Với API nhận sort key từ client, hãy whitelist các trường cho phép. Không đưa raw chuỗi người dùng vào biểu thức query hoặc JpaSort.unsafe. Sort field là cấu trúc truy vấn, không phải giá trị bind parameter.

## 5. Vì sao cần tiêu chí sắp xếp phụ?

Giả sử hai đơn hàng cùng được tạo lúc 10:00. Truy vấn chỉ ORDER BY createdAt DESC không quy định thứ tự giữa hai đơn đó.

Khi dữ liệu có giá trị sort trùng nhau, thứ tự tương đối của chúng không được bảo đảm. Điều này có thể làm:

- Kết quả đổi vị trí giữa các lần chạy.
- Phân trang có phần tử lặp hoặc bị bỏ qua khi dữ liệu thay đổi.
- Test phụ thuộc thứ tự tình cờ của database.
- Giao diện hiển thị không ổn định.

Thêm khóa duy nhất làm tie-breaker:

~~~jpql
order by o.createdAt desc, o.id desc
~~~

Với thứ tự này, hai hàng có createdAt giống nhau vẫn được phân biệt bằng id. Nên dùng quy tắc tương tự cho mọi query phân trang hoặc API cần kết quả ổn định.

Nếu sắp xếp theo tên, cân nhắc collation và không phân biệt hoa thường. Nếu có NULL, thứ tự NULL có thể khác nhau giữa database; khi yêu cầu nghiệp vụ cần nhất quán, hãy quy định rõ bằng biểu thức phù hợp và kiểm thử trên database mục tiêu.

## 6. Set không phải là cơ chế sắp xếp

Ví dụ repository:

~~~java
Set<PurchaseOrder> findByStatus(OrderStatus status);
~~~

Kết quả Set không có hợp đồng về thứ tự lặp. Ngay cả khi query có ORDER BY hoặc caller truyền Sort, không nên dựa vào thứ tự duyệt của Set để hiển thị dữ liệu.

Nếu thứ tự là một phần của yêu cầu, hãy trả List:

~~~java
List<PurchaseOrder> findByStatus(
    OrderStatus status,
    Sort sort
);
~~~

Set phù hợp khi caller chỉ quan tâm thành viên có tồn tại hay không, hoặc cần loại trùng theo equals(). Không dùng Set chỉ vì muốn kết quả “gọn” hoặc hy vọng database trả về thứ tự nào đó.

Một implementation như LinkedHashSet có thể giữ thứ tự chèn, nhưng repository contract khai báo Set không bảo đảm caller sẽ nhận được implementation cụ thể nào. Nếu cần thứ tự, khai báo List và ORDER BY/Sort.

## 7. Set loại trùng theo equals() và hashCode()

Set xác định hai phần tử trùng nhau theo quy tắc equality của phần tử và implementation Set.

Với entity JPA, điều này khiến equals() và hashCode() trở nên quan trọng. Nếu entity dùng Object.equals() mặc định, hai instance khác nhau đại diện cho cùng một hàng database có thể không bị xem là bằng nhau. Nếu equals() được viết sai hoặc hashCode() thay đổi sau khi ID được cấp, Set có thể chứa kết quả ngoài mong muốn hoặc không tìm được phần tử đã thêm.

Cần xem xét:

- Hai instance của cùng entity có cùng ID có được xem là bằng nhau không?
- Entity mới chưa có ID được so sánh thế nào?
- hashCode có ổn định sau persist không?
- Hibernate proxy có được xử lý đúng không?
- Equality có vô tình phụ thuộc vào collection quan hệ hoặc field mutable không?

Đừng dùng Set như cách che giấu vấn đề equality của entity. Hãy thiết kế equals()/hashCode() theo identity và vòng đời entity; nếu không có nhu cầu equality qua persistence context, giữ object identity mặc định có thể phù hợp hơn.

## 8. Set và DISTINCT giải quyết hai vấn đề khác nhau

Có hai tầng cần phân biệt:

1. **DISTINCT trong JPQL/SQL** loại kết quả trùng theo ngữ nghĩa của truy vấn.
2. **Set trong Java** loại phần tử trùng theo equals()/hashCode() của object được đưa vào collection.

Ví dụ Customer có nhiều PurchaseOrder. Truy vấn:

~~~jpql
select c
from Customer c
join c.orders o
where o.status = :status
~~~

có thể tạo nhiều hàng cho cùng Customer nếu Customer có nhiều đơn thỏa điều kiện.

Nếu muốn truy vấn entity Customer duy nhất, viết:

~~~jpql
select distinct c
from Customer c
join c.orders o
where o.status = :status
~~~

Hoặc nếu chỉ cần một tập giá trị scalar duy nhất, chọn đúng biểu thức:

~~~jpql
select distinct c.city
from Customer c
where c.city is not null
~~~

Set không thay thế DISTINCT ở database. Khi query trả List có duplicate, chuyển kết quả sang Set có thể loại phần tử theo Java equality, nhưng việc đó xảy ra ở tầng Java và có thể yêu cầu tải toàn bộ kết quả. DISTINCT cho phép database xử lý ngữ nghĩa loại trùng trong truy vấn.

Cũng không nên cho rằng SELECT DISTINCT entity và SELECT DISTINCT field có cùng ý nghĩa. Hai Customer khác ID nhưng cùng city vẫn là hai entity riêng; còn SELECT DISTINCT c.city chỉ giữ một giá trị city.

## 9. DISTINCT và count query

Khi dùng JOIN, COUNT(entity) có thể đếm số hàng kết quả sau JOIN thay vì số entity gốc duy nhất.

Ví dụ cần đếm Customer có ít nhất một đơn PAID:

~~~jpql
select count(distinct c.id)
from Customer c
join c.orders o
where o.status = :status
~~~

COUNT(DISTINCT c.id) đếm số Customer khác nhau. Đây là cách rõ ràng khi quan hệ một-nhiều làm nhân số hàng.

Cẩn thận với tên derived query như countDistinctByStatus. Trong Spring Data JPA, DISTINCT có thể được áp dụng lên entity ID theo cách sinh query, chứ không có nghĩa đếm số giá trị status duy nhất. Nếu muốn đếm giá trị scalar khác nhau, hãy khai báo JPQL tường minh:

~~~java
@Query("""
    select count(distinct o.status)
    from PurchaseOrder o
    """)
long countDistinctStatuses();
~~~

Khi dùng Page với JOIN, countQuery phải phản ánh đúng đơn vị cần đếm. Nếu nội dung là Customer duy nhất, count query thường cần COUNT(DISTINCT c.id), không phải COUNT(*) trên hàng JOIN.

## 10. Collection, List và Set trong repository

Ví dụ repository tổng hợp:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Collection<PurchaseOrder> findByStatus(OrderStatus status);

    List<PurchaseOrder> findByStatusOrderByCreatedAtDescIdDesc(
        OrderStatus status
    );

    Set<PurchaseOrder> findDistinctByStatus(OrderStatus status);

    List<PurchaseOrder> findByStatus(
        OrderStatus status,
        Sort sort
    );

    Page<PurchaseOrder> findByStatus(
        OrderStatus status,
        Pageable pageable
    );

    Slice<PurchaseOrder> findSliceByStatus(
        OrderStatus status,
        Pageable pageable
    );
}
~~~

Các method minh họa các hợp đồng khác nhau:

- Collection là lựa chọn tổng quát khi caller không yêu cầu list index hay uniqueness.
- List phù hợp khi cần thứ tự hoặc cho phép kết quả trùng.
- Set phù hợp khi caller cần phần tử duy nhất theo equality.
- Page chứa nội dung của một trang và metadata tổng số phần tử/trang.
- Slice chứa nội dung trang và thông tin có trang tiếp theo, thường tránh count query tổng.
- Sort và Pageable cho phép quyết định thứ tự ở thời điểm gọi.

Không nên khai báo nhiều method trùng chữ ký như ví dụ trong cùng một interface Java. Khi áp dụng, giữ mỗi method một tên riêng, ví dụ findCollectionByStatus, findSetByStatus hoặc dùng một repository method chính với kiểu trả về phù hợp. Đoạn trên là bảng minh họa các kiểu trả về và chữ ký, không phải interface hoàn chỉnh để copy nguyên trạng vì Java không cho overload chỉ dựa trên kiểu trả về.

## 11. Page và Slice luôn cần thứ tự có chủ đích

Pageable có thể mang Sort:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Pageable pageable = PageRequest.of(0, 20, sort);

Page<PurchaseOrder> page =
    repository.findByStatus(OrderStatus.PAID, pageable);
~~~

Page<T> cung cấp getContent(), getTotalElements(), getTotalPages(), getNumber() và thông tin điều hướng. Nội dung trang là một List, nhưng thứ tự chỉ ổn định khi query có sort xác định.

Slice<T> hữu ích khi giao diện chỉ cần biết có trang tiếp theo hay không. Nó thường cần truy vấn thêm một phần tử để xác định hasNext() thay vì chạy count query toàn bộ.

Offset pagination có thể trở nên tốn kém ở offset lớn và có thể dịch chuyển kết quả khi dữ liệu mới được thêm hoặc xóa giữa các lần đọc. Với dữ liệu lớn hoặc thay đổi liên tục, cân nhắc keyset/scrolling nếu phiên bản Spring Data JPA và loại query hỗ trợ. Keyset cũng cần thứ tự ổn định, thường gồm các field sort và một khóa duy nhất.

## 12. Thứ tự của collection quan hệ: @OrderBy

Thứ tự của repository query khác với thứ tự của collection association trong entity.

Ví dụ:

~~~java
@Entity
public class Customer {

    @Id
    private Long id;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    @OrderBy("createdAt DESC, id DESC")
    private List<PurchaseOrder> orders = new ArrayList<>();
}
~~~

@OrderBy yêu cầu collection được tải theo thuộc tính của entity liên quan. Trong ví dụ, orders được sắp xếp theo createdAt giảm dần và id giảm dần khi collection được nạp.

Tên trong @OrderBy là thuộc tính Java của entity PurchaseOrder, không phải tên cột SQL. Annotation này áp dụng cho việc tải association collection; nó không tự sắp xếp mọi query repository độc lập.

Nếu cần thứ tự khác cho một truy vấn cụ thể, dùng Sort hoặc JPQL ORDER BY ở repository method đó.

## 13. @OrderBy khác @OrderColumn như thế nào?

Hai annotation có mục đích khác nhau:

| Annotation | Cách hoạt động | Khi phù hợp |
|---|---|---|
| @OrderBy | Sắp xếp phần tử theo giá trị của thuộc tính entity khi tải collection | Muốn danh sách luôn theo ngày, tên hoặc tiêu chí dữ liệu |
| @OrderColumn | Lưu vị trí phần tử vào một cột thứ tự trong bảng liên kết/collection table | Muốn bảo toàn thứ tự do người dùng sắp xếp hoặc thứ tự danh sách |

Ví dụ @OrderColumn:

~~~java
@OneToMany(mappedBy = "playlist")
@OrderColumn(name = "position_index")
private List<Track> tracks = new ArrayList<>();
~~~

Trong mô hình phù hợp với mapping sở hữu cột thứ tự, provider duy trì vị trí phần tử trong database. Khi danh sách được đổi thứ tự, các giá trị position_index có thể được cập nhật để phản ánh vị trí mới.

@OrderBy không lưu vị trí thủ công. Nó tính thứ tự dựa trên giá trị thuộc tính khi đọc. Nếu hai phần tử có cùng giá trị sort, cần thêm tiêu chí phụ để kết quả ổn định.

Không khai báo đồng thời @OrderBy và @OrderColumn cho cùng một association như hai cách thay thế tùy ý. Chọn cơ chế phù hợp với ý nghĩa thứ tự của domain và kiểm tra quy tắc mapping của phiên bản JPA/provider.

## 14. Set association có phù hợp khi cần thứ tự không?

Set association thường phù hợp khi quan hệ biểu diễn membership: ví dụ tập quyền của người dùng hoặc tập tag của bài viết. Nếu nghiệp vụ yêu cầu thứ tự hiển thị, một Set thông thường không thể hiện hợp đồng vị trí.

Có thể truy vấn association bằng repository riêng với Sort khi cần thứ tự. Hoặc dùng List association nếu thứ tự là một phần của mô hình.

Đừng thay List thành Set chỉ để ngăn duplicate nếu mỗi phần tử cần vị trí hoặc có thể lặp theo nghiệp vụ. Ví dụ, playlist có thể chứa cùng một bài hát nhiều lần ở các vị trí khác nhau; Set sẽ làm mất ý nghĩa đó.

Ngược lại, danh sách role hoặc permission thường có ngữ nghĩa tập hợp; Set có thể phù hợp nếu equality của phần tử được định nghĩa ổn định.

## 15. Streaming kết quả lớn

Repository có thể trả Stream<T> cho một số query method:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    where o.status = :status
    order by o.id
    """)
Stream<PurchaseOrder> streamByStatus(
    @Param("status") OrderStatus status
);
~~~

Stream có thể giữ tài nguyên JDBC hoặc persistence context trong quá trình đọc. Cần đóng stream và duy trì transaction phù hợp:

~~~java
@Transactional(readOnly = true)
public void processPaidOrders() {
    try (Stream<PurchaseOrder> stream =
             repository.streamByStatus(OrderStatus.PAID)) {
        stream.forEach(this::process);
    }
}
~~~

Đoạn code là minh họa service method; process phải tránh giữ entity lâu ngoài transaction hoặc tạo truy vấn N+1 không kiểm soát.

Stream không tự bảo đảm thứ tự. Trong ví dụ, ORDER BY o.id quy định thứ tự đọc. Nếu query stream không có ORDER BY, không dựa vào thứ tự lặp của stream.

## 16. Chọn kiểu trả về theo yêu cầu

Một số tình huống phổ biến:

| Nhu cầu | Kiểu phù hợp | Lưu ý |
|---|---|---|
| Trả mọi kết quả, không cần hợp đồng vị trí | Collection<T> | Không cam kết thứ tự hoặc uniqueness |
| Hiển thị danh sách theo thứ tự | List<T> | Bắt buộc có ORDER BY hoặc Sort |
| Cần danh sách có thể chứa kết quả bằng nhau | List<T> | Dùng DISTINCT nếu query cần loại trùng |
| Cần tập phần tử duy nhất theo equality | Set<T> | Thiết kế equals/hashCode ổn định |
| Cần trang và tổng số bản ghi | Page<T> | Có thể phát sinh count query |
| Chỉ cần biết có trang kế tiếp | Slice<T> | Thường tránh count query tổng |
| Xử lý dữ liệu lớn theo luồng | Stream<T> | Đóng stream và quản lý transaction |
| Chỉ cần một kết quả hoặc không có | Optional<T> | Nhiều hơn một kết quả có thể gây lỗi cardinality |

Nếu yêu cầu có cả uniqueness và ordering, hãy biểu diễn rõ cả hai ở tầng query và kiểu dữ liệu. Thường nên lấy List với DISTINCT và ORDER BY, sau đó trả DTO cho API. Đừng dùng Set rồi kỳ vọng thứ tự.

## 17. Kiểm thử thứ tự và uniqueness

Một bộ repository integration test nên chuẩn bị dữ liệu có:

- Nhiều đơn hàng cùng status.
- Hai đơn có cùng createdAt nhưng khác ID.
- Hai Customer có nhiều đơn thỏa cùng điều kiện JOIN.
- Hai DTO hoặc entity có một số field giống nhau nhưng ID khác nhau.
- Một collection association có phần tử được thêm theo thứ tự khác với thứ tự createdAt.

Các assertion cần xác minh:

1. List không ORDER BY không được kiểm thử bằng một thứ tự tình cờ cố định.
2. List có ORDER BY/Sort trả kết quả theo đúng tiêu chí.
3. Tie-breaker tạo thứ tự xác định khi giá trị chính bằng nhau.
4. Set không bị kiểm tra theo thứ tự lặp.
5. Set chỉ loại phần tử theo equals/hashCode của phần tử.
6. SELECT DISTINCT loại kết quả trùng theo ngữ nghĩa query.
7. COUNT(DISTINCT id) đếm entity duy nhất sau JOIN.
8. Page có totalElements khớp count query.
9. @OrderBy sắp xếp association khi collection được tải.
10. @OrderColumn bảo toàn vị trí đã lưu sau khi reload.

Ví dụ test cho thứ tự ổn định:

~~~java
@Test
void returnsOrdersInDeterministicOrder() {
    List<PurchaseOrder> orders =
        repository.findByStatusOrderByCreatedAtDescIdDesc(
            OrderStatus.PAID
        );

    assertEquals(
        List.of(12L, 10L, 8L),
        orders.stream().map(PurchaseOrder::getId).toList()
    );
}
~~~

Test này giả định fixture đã tạo ba đơn PAID với timestamp và ID theo đúng thứ tự mong đợi. Khi dùng database thật, flush dữ liệu trước khi query. Không viết test cho List không có ORDER BY bằng cách khẳng định một thứ tự ngẫu nhiên hiện tại.

Ví dụ test Set nên kiểm tra membership hoặc size, không kiểm tra thứ tự:

~~~java
assertEquals(3, resultSet.size());
assertTrue(resultSet.contains(expectedOrder));
~~~

Nếu test uniqueness của entity, bảo đảm equals/hashCode của entity có semantics mà domain mong muốn.

## 18. Lỗi thường gặp và cách khắc phục

**1. List thay đổi thứ tự giữa các lần chạy**

Query chưa có ORDER BY hoặc Sort. Thêm tiêu chí sắp xếp và khóa duy nhất làm tie-breaker.

**2. Dùng Set nhưng kết quả vẫn có phần tử trùng theo nghiệp vụ**

Kiểm tra equals/hashCode của entity hoặc projection. Set chỉ loại trùng theo equality Java, không tự hiểu hai object có cùng business meaning.

**3. Dùng Set rồi giao diện hiển thị không theo Sort**

Set không cam kết thứ tự duyệt. Đổi sang List nếu thứ tự là yêu cầu.

**4. Nghĩ Collection tự loại duplicate**

Collection cho phép phần tử trùng. Chọn Set hoặc DISTINCT theo đúng tầng cần uniqueness.

**5. Nghĩ Set tương đương SELECT DISTINCT**

Set loại trùng trong Java; DISTINCT thuộc ngữ nghĩa truy vấn. Với dữ liệu lớn, dùng DISTINCT hoặc EXISTS ở query khi phù hợp để tránh tải kết quả thừa.

**6. countDistinctByStatus đếm sai ý nghĩa**

Kiểm tra SQL/JPQL được tạo. Nếu cần đếm status duy nhất, viết COUNT(DISTINCT status) tường minh thay vì giả định tên method có nghĩa đếm giá trị status.

**7. Page có thứ tự không ổn định**

Thêm Sort có tie-breaker. Kiểm tra count query nếu JOIN có thể nhân hàng.

**8. @OrderBy không ảnh hưởng query repository khác**

@OrderBy chỉ quy định cách association collection được tải. Query repository riêng cần ORDER BY hoặc Sort riêng.

**9. Đổi List thành Set làm mất phần tử hợp lệ**

Nếu domain cho phép cùng một giá trị xuất hiện nhiều lần ở các vị trí khác nhau, Set không phù hợp. Dùng List và định danh riêng cho từng phần tử.

**10. Dùng @OrderColumn cho danh sách chỉ cần sắp xếp theo ngày**

Nếu thứ tự có thể tính từ thuộc tính createdAt, @OrderBy thường phù hợp hơn và không cần lưu thêm position index.

## 19. Quy trình chọn collection và thứ tự kết quả

Khi thiết kế repository method, hãy đi theo trình tự:

1. Xác định kết quả có thể chứa phần tử trùng theo nghiệp vụ hay không.
2. Xác định caller có cần thứ tự hoặc index hay không.
3. Chọn Collection, List hoặc Set theo hợp đồng Java.
4. Nếu cần thứ tự, thêm JPQL ORDER BY, derived OrderBy hoặc Sort.
5. Thêm khóa duy nhất làm tie-breaker khi cần kết quả ổn định.
6. Nếu query JOIN collection, xác định có cần SELECT DISTINCT hoặc EXISTS.
7. Nếu dùng Set, kiểm tra equals/hashCode và proxy semantics của entity.
8. Nếu phân trang, dùng Page/Slice với Sort ổn định và count query đúng.
9. Nếu sắp xếp association, chọn @OrderBy hoặc @OrderColumn theo ý nghĩa domain.
10. Nếu xử lý dữ liệu lớn, cân nhắc Stream và quản lý transaction/tài nguyên.
11. Viết integration test trên database phù hợp với production.

## 20. Checklist tự đánh giá

- [ ] Tôi phân biệt được hợp đồng của Collection, List và Set.
- [ ] Tôi biết List không tự bảo đảm thứ tự database nếu thiếu ORDER BY.
- [ ] Tôi biết dùng derived OrderBy và Sort động.
- [ ] Tôi thêm tie-breaker duy nhất cho thứ tự ổn định.
- [ ] Tôi hiểu Set loại trùng theo equals/hashCode và không cam kết thứ tự.
- [ ] Tôi phân biệt Set với SELECT DISTINCT.
- [ ] Tôi biết dùng COUNT(DISTINCT id) khi đếm entity sau JOIN.
- [ ] Tôi hiểu Page, Slice, Pageable và count query.
- [ ] Tôi phân biệt @OrderBy và @OrderColumn.
- [ ] Tôi biết association collection có thứ tự khác với query repository riêng.
- [ ] Tôi biết đóng Stream và giữ transaction trong khi xử lý.
- [ ] Tôi kiểm thử membership của Set và thứ tự của List theo query contract.

## 21. Câu hỏi ôn tập

**1. Collection, List và Set khác nhau thế nào?**

Collection là abstraction tổng quát và cho phép duplicate; List cho phép duplicate và giữ thứ tự vị trí; Set không cho phần tử trùng theo equals() nhưng không cam kết thứ tự duyệt.

**2. Repository trả List có bảo đảm kết quả theo thứ tự ID không?**

Không. Cần ORDER BY, derived OrderBy hoặc Sort. Không dựa vào thứ tự vật lý hay thứ tự insert.

**3. Vì sao Set không phù hợp khi cần hiển thị theo Sort?**

Set không có hợp đồng iteration order. Dùng List để giữ thứ tự query trả về.

**4. Set và DISTINCT khác nhau thế nào?**

Set loại trùng ở Java theo equals/hashCode. DISTINCT loại trùng theo biểu thức được chọn trong truy vấn và được xử lý ở tầng query/database.

**5. Vì sao hashCode của entity cần ổn định khi dùng Set?**

Set dựa trên hashCode để lưu và tìm phần tử. Nếu hashCode thay đổi sau khi entity được thêm, contains/remove có thể không tìm thấy phần tử.

**6. @OrderBy khác @OrderColumn thế nào?**

@OrderBy sắp xếp collection theo giá trị thuộc tính khi tải. @OrderColumn lưu vị trí phần tử trong database để bảo toàn thứ tự danh sách.

**7. Khi nào nên dùng Slice thay vì Page?**

Khi giao diện chỉ cần nội dung trang và biết có trang tiếp theo, không cần tổng số phần tử hoặc tổng số trang. Slice thường tránh count query tổng.

**8. Làm thế nào để phân trang ổn định?**

Dùng Sort có thứ tự xác định và thêm khóa duy nhất làm tie-breaker. Với dữ liệu lớn hoặc thay đổi liên tục, cân nhắc keyset scrolling nếu query và phiên bản hỗ trợ.

Chọn đúng Collection, List hoặc Set giúp repository thể hiện rõ hợp đồng dữ liệu. Kết hợp kiểu trả về với DISTINCT, ORDER BY, Sort và pagination đúng cách giúp ứng dụng tránh kết quả trùng ngoài ý muốn, thứ tự không ổn định và các lỗi khó tái hiện giữa những lần truy vấn.