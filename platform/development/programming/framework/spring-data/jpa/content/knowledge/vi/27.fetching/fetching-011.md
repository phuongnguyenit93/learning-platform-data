# Tải nhiều tập hợp, tích Descartes và MultipleBagFetchException

Khi một entity có nhiều collection, việc tải tất cả bằng một câu truy vấn JOIN FETCH có thể tạo ra lượng dữ liệu lớn bất ngờ. Với Hibernate, nếu nhiều collection được ánh xạ theo kiểu bag cùng được fetch trong một truy vấn, ứng dụng còn có thể gặp MultipleBagFetchException.

Để xử lý đúng, cần phân biệt ba vấn đề:

- **Nhiều collection được tải cùng lúc:** đây là quyết định về fetch plan.
- **Tích Descartes:** là số dòng kết quả SQL tăng theo tích số phần tử của các collection được join.
- **MultipleBagFetchException:** là ngoại lệ riêng của Hibernate khi một truy vấn cố fetch đồng thời nhiều bag.

Bài học này dùng ví dụ đơn hàng có danh sách dòng hàng và danh sách khoản giảm giá để giải thích nguyên nhân, cách chẩn đoán và các phương án tải dữ liệu.

## 1. Mô hình có nhiều collection

Giả sử một đơn hàng có nhiều dòng hàng (lines) và nhiều khoản giảm giá (discounts):

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderDiscount> discounts = new ArrayList<>();

    // getters và các phương thức nghiệp vụ
}
~~~

Đây là đoạn ánh xạ minh họa, giả định OrderLine và OrderDiscount có quan hệ @ManyToOne trỏ về PurchaseOrder. Trong dự án thực tế, cần bổ sung constructor, getter, setter hoặc phương thức quản lý hai phía của quan hệ theo thiết kế entity.

Với Hibernate, một List không có @OrderColumn thường được ánh xạ theo ngữ nghĩa **bag**: collection không có chỉ số vị trí được lưu trữ để phân biệt từng phần tử theo thứ tự. Bag cho phép các phần tử trùng lặp và không đảm bảo thứ tự như một indexed list.

Cần phân biệt:

- List không có @OrderColumn: thường mang ngữ nghĩa bag trong Hibernate.
- List có @OrderColumn: Hibernate lưu vị trí phần tử; collection có ngữ nghĩa danh sách có thứ tự.
- Set: collection không cho phép phần tử trùng theo quy tắc equals()/hashCode() và không mang ngữ nghĩa bag.
- @OrderBy: sắp xếp phần tử khi đọc theo thuộc tính; không tương đương với việc lưu chỉ số vị trí bằng @OrderColumn.

MultipleBagFetchException là ngoại lệ của Hibernate, không phải ngoại lệ được đặc tả JPA quy định. Nó thường xuất hiện khi Hibernate phải fetch đồng thời nhiều association được ánh xạ theo kiểu bag trong cùng một truy vấn.

## 2. Vì sao JOIN FETCH nhiều collection tạo tích Descartes?

Giả sử một đơn hàng có:

- 3 dòng hàng trong lines.
- 4 khoản giảm giá trong discounts.

Truy vấn join đồng thời hai collection sẽ tạo các tổ hợp giữa dòng hàng và khoản giảm giá. Với ví dụ này, một đơn hàng có thể tạo ra:

**3 × 4 = 12 dòng kết quả SQL.**

Nếu có 10 dòng hàng và 8 khoản giảm giá, số tổ hợp có thể lên tới 80 dòng cho cùng một đơn hàng. Với nhiều collection và nhiều entity gốc, lượng dữ liệu truyền từ database về ứng dụng có thể tăng rất nhanh.

Ví dụ JPQL:

~~~java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    left join fetch o.discounts
    where o.id = :id
    """)
Optional<PurchaseOrder> findWithLinesAndDiscounts(@Param("id") Long id);
~~~

Sơ đồ kết quả join cho một đơn hàng:

~~~mermaid
flowchart TD
    O[PurchaseOrder]
    O --> L1[Line 1]
    O --> L2[Line 2]
    O --> L3[Line 3]
    O --> D1[Discount 1]
    O --> D2[Discount 2]
    O --> D3[Discount 3]
    O --> D4[Discount 4]
    L1 -. kết hợp với .- D1
    L1 -. kết hợp với .- D2
    L1 -. kết hợp với .- D3
    L1 -. kết hợp với .- D4
~~~

Về mặt SQL, mỗi dòng hàng được kết hợp với mỗi khoản giảm giá thuộc cùng đơn hàng. Database trả về các cột của đơn hàng và cả hai collection lặp lại trên nhiều dòng.

### DISTINCT giải quyết được gì?

select distinct o yêu cầu loại bỏ các kết quả entity gốc trùng lặp theo ngữ nghĩa truy vấn. Nó hữu ích khi kết quả JPQL có nhiều dòng tham chiếu cùng một entity.

Tuy nhiên, DISTINCT **không làm biến mất tích Descartes ở tầng SQL**: database vẫn phải tạo và xử lý các tổ hợp dòng hàng × khoản giảm giá để trả về dữ liệu cần hydrate. Vì vậy, DISTINCT không phải cách sửa hiệu năng cho việc fetch quá nhiều collection.

Trong Hibernate 6, các entity gốc trùng lặp do collection fetch join thường được loại bỏ tự động khỏi kết quả entity. Tùy phiên bản Hibernate và mục tiêu tương thích JPA, DISTINCT có thể vẫn được dùng để diễn đạt rõ ý định truy vấn; nó không thay đổi số tổ hợp SQL cần xử lý.

## 3. MultipleBagFetchException là gì?

Hibernate cần tái dựng collection từ các dòng SQL trả về. Khi một truy vấn fetch đồng thời nhiều bag, việc phân biệt các phần tử bag từ những tổ hợp dòng kết quả có thể không rõ ràng. Hibernate chủ động từ chối một số truy vấn như vậy và ném org.hibernate.loader.MultipleBagFetchException.

Ví dụ truy vấn có thể kích hoạt ngoại lệ khi cả lines và discounts đều là bag:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    left join fetch o.lines
    left join fetch o.discounts
    where o.id = :id
    """)
Optional<PurchaseOrder> findAllDetails(@Param("id") Long id);
~~~

Điều kiện cần nhớ:

- Ngoại lệ liên quan đến việc fetch đồng thời nhiều bag, không phải cứ entity có hai collection là sẽ gặp lỗi.
- Hai collection có thể được tải ở các truy vấn riêng mà không gây lỗi này.
- Một bag và một Set có thể không kích hoạt ngoại lệ cụ thể này, nhưng truy vấn vẫn có nguy cơ tạo tích Descartes lớn.
- Thay List bằng Set chỉ để né ngoại lệ có thể làm thay đổi ngữ nghĩa dữ liệu và không giải quyết gốc rễ vấn đề về số dòng join.

Khi gặp lỗi, hãy kiểm tra fetch plan của truy vấn, mapping collection và SQL được Hibernate phát ra. Đừng chỉ nhìn vào số lượng entity gốc trong kết quả Java; cần xem cả số dòng database thực sự trả về.

## 4. Cách khuyến nghị: chia thành nhiều truy vấn

Một cách phổ biến là mỗi truy vấn chỉ fetch một bag. Ví dụ, truy vấn thứ nhất tải đơn hàng cùng lines; truy vấn thứ hai tải cùng đơn hàng với discounts.

**Repository:**

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select distinct o
        from PurchaseOrder o
        left join fetch o.lines
        where o.id = :id
        """)
    Optional<PurchaseOrder> findWithLines(@Param("id") Long id);

    @Query("""
        select distinct o
        from PurchaseOrder o
        left join fetch o.discounts
        where o.id = :id
        """)
    Optional<PurchaseOrder> findWithDiscounts(@Param("id") Long id);
}
~~~

**Service:**

~~~java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public PurchaseOrder getOrderDetails(Long id) {
        PurchaseOrder order = repository.findWithLines(id)
                .orElseThrow(() ->
                        new EntityNotFoundException("Không tìm thấy đơn hàng"));

        // Truy vấn thứ hai fetch collection discounts.
        // Cùng persistence context nên entity có cùng ID được quản lý
        // bởi cùng một instance PurchaseOrder.
        repository.findWithDiscounts(id);

        return order;
    }
}
~~~

Đây là các đoạn mã minh họa, giả định entity và repository được cấu hình theo Spring Data JPA. Có thể cần import EntityNotFoundException, Entity, FetchType, JpaRepository, Query, Param, Service, Transactional và các kiểu liên quan trong dự án.

Điểm quan trọng là hai truy vấn chạy trong **cùng một transaction và persistence context**. Persistence context duy trì identity map: cùng một entity có cùng khóa chính được quản lý bởi cùng một instance. Truy vấn đầu khởi tạo lines; truy vấn sau khởi tạo discounts trên entity đang được quản lý đó. Khi trả về order, cả hai collection đã được tải.

Ưu điểm:

- Mỗi câu truy vấn chỉ join một collection bag.
- Tránh tích Descartes giữa hai collection trong cùng một câu SQL.
- Code repository thể hiện rõ fetch plan theo từng nhu cầu.
- Có thể kiểm soát transaction ở service và giữ các association cần thiết trong cùng persistence context.

Đổi lại, ứng dụng thực hiện nhiều câu SQL hơn. Với một đơn hàng và hai collection, thường cần hai truy vấn có fetch join; hãy cân nhắc số lượng collection, số entity gốc và chi phí round-trip thực tế.

## 5. Các chiến lược tải dữ liệu khác

Không có một fetch strategy phù hợp cho mọi màn hình hoặc ca sử dụng. Hãy chọn theo số lượng entity, kích thước collection và dữ liệu thực sự cần trả về.

### 5.1. Lazy loading kết hợp batch fetching

Để collection tiếp tục LAZY, Hibernate có thể gom việc tải nhiều collection cùng loại thành một truy vấn dùng IN thay vì phát sinh một truy vấn riêng cho từng entity.

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderLine> lines = new ArrayList<>();
~~~

@BatchSize là annotation riêng của Hibernate. Có thể cấu hình mặc định ở cấp ứng dụng bằng thuộc tính:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Khi nhiều collection cùng loại được truy cập trong một persistence context, Hibernate có thể tải chúng theo nhóm tối đa theo kích thước batch đã cấu hình. Chiến lược này giảm N+1 trong nhiều trường hợp mà không cần join tất cả collection vào một câu truy vấn.

Batch fetching không có nghĩa mọi truy vấn đều luôn dùng đúng số lượng batch đã đặt; Hibernate quyết định dựa trên các association đang chờ tải và ngữ cảnh thực tế.

### 5.2. Subselect fetching

Hibernate cung cấp @Fetch(FetchMode.SUBSELECT) để tải collection của một nhóm entity cha bằng một truy vấn phụ dựa trên truy vấn đã tải các entity cha:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderLine> lines = new ArrayList<>();
~~~

Đây là tính năng riêng của Hibernate. Nó có thể hữu ích khi một truy vấn lấy nhiều đơn hàng và ứng dụng cần truy cập cùng một collection trên nhiều đơn hàng trong persistence context.

Cần kiểm tra SQL thực tế và phạm vi entity bị ảnh hưởng, vì subselect có thể tải nhiều collection hơn nhu cầu của một đoạn code cụ thể.

### 5.3. EntityGraph

Spring Data JPA hỗ trợ @EntityGraph để mô tả association cần tải cho một phương thức repository:

~~~java
@EntityGraph(attributePaths = "lines")
@Query("select o from PurchaseOrder o where o.id = :id")
Optional<PurchaseOrder> findWithLinesById(@Param("id") Long id);
~~~

Có thể khai báo một phương thức khác chỉ tải discounts, rồi gọi chúng trong cùng transaction như cách chia truy vấn ở phần trước.

EntityGraph mô tả fetch plan, không đảm bảo provider luôn dùng một chiến lược SQL cụ thể. Nếu đưa nhiều collection vào cùng một graph, provider có thể vẫn tạo join lớn hoặc gặp giới hạn tương tự. Hãy kiểm tra SQL thực tế.

### 5.4. DTO projection

Nếu màn hình chỉ cần một số trường, hãy cân nhắc trả về DTO thay vì tải cả entity graph. DTO projection cho phép lấy đúng dữ liệu cần dùng, giảm lượng cột và tránh khởi tạo các collection không cần thiết.

Ví dụ projection đơn giản:

~~~java
public record OrderSummary(
        Long id,
        OrderStatus status,
        BigDecimal totalAmount) {
}
~~~

Repository có thể truy vấn trực tiếp các trường tương ứng:

~~~java
@Query("""
    select new com.example.dto.OrderSummary(
        o.id, o.status, o.totalAmount)
    from PurchaseOrder o
    where o.id = :id
    """)
Optional<OrderSummary> findSummaryById(@Param("id") Long id);
~~~

Tên package và kiểu dữ liệu trong ví dụ phải khớp với dự án. Nếu DTO cần dữ liệu từ nhiều collection, có thể truy vấn từng phần hoặc dùng một truy vấn cho mỗi nhóm dữ liệu rồi ghép kết quả trong service. Cách này giúp kiểm soát số dòng và hình dạng kết quả rõ ràng.

### 5.5. Dùng Set hoặc indexed List khi đúng ngữ nghĩa

Nếu nghiệp vụ thực sự yêu cầu tập hợp không trùng lặp, Set có thể là lựa chọn phù hợp. Khi dùng entity làm phần tử Set, cần thiết kế equals() và hashCode() cẩn thận, đặc biệt khi entity có ID được sinh sau khi persist.

Nếu nghiệp vụ cần danh sách có thứ tự và vị trí được lưu trong database, có thể dùng @OrderColumn:

~~~java
@OneToMany(mappedBy = "order")
@OrderColumn(name = "line_position")
private List<OrderLine> lines = new ArrayList<>();
~~~

Lưu ý: mapping thực tế của @OrderColumn phải phù hợp với quan hệ sở hữu, cách quản lý hai phía và phiên bản JPA/Hibernate của dự án. Hãy kiểm tra schema và SQL cập nhật vị trí trước khi áp dụng.

Set hoặc @OrderColumn có thể thay đổi cách Hibernate phân loại collection và tránh ngoại lệ bag trong một số trường hợp. Nhưng nếu vẫn join nhiều collection cùng lúc, tích Descartes vẫn có thể tồn tại. Chỉ chọn Set hay @OrderColumn khi ngữ nghĩa dữ liệu thực sự yêu cầu.

## 6. Lưu ý khi phân trang

Fetch join một collection cùng truy vấn phân trang có thể khiến Hibernate phải xử lý phân trang ở bộ nhớ hoặc tạo cảnh báo hiệu năng, bởi một entity gốc có thể chiếm nhiều dòng SQL. Nếu join thêm collection thứ hai, lượng dữ liệu còn tăng mạnh.

Một mẫu an toàn hơn:

1. Truy vấn trang ID của entity gốc bằng điều kiện lọc và Pageable, không fetch collection.
2. Tải entity và một collection bằng truy vấn where id in :ids.
3. Tải collection tiếp theo bằng truy vấn riêng trong cùng transaction.
4. Sắp xếp kết quả theo thứ tự ID của trang ban đầu vì truy vấn IN không đảm bảo giữ thứ tự.

Ví dụ truy vấn lấy ID:

~~~java
@Query(
    value = "select o.id from PurchaseOrder o order by o.createdAt desc",
    countQuery = "select count(o) from PurchaseOrder o"
)
Page<Long> findOrderIds(Pageable pageable);
~~~

Sau khi lấy được danh sách ID, service gọi các truy vấn fetch theo nhóm. Cần giữ transaction và persistence context nhất quán nếu muốn Hibernate hợp nhất các collection đã tải vào cùng entity instance. Với bộ lọc thực tế, value và countQuery phải dùng cùng điều kiện để tổng số trang chính xác.

## 7. Những cách xử lý dễ gây hiểu nhầm

**Thêm DISTINCT rồi cho rằng đã hết tích Descartes.** DISTINCT xử lý kết quả entity trùng lặp; nó không loại bỏ các tổ hợp dòng cần thiết ở tầng SQL.

**Đổi tất cả List thành Set chỉ để tránh ngoại lệ.** Điều này có thể làm thay đổi ý nghĩa dữ liệu, thứ tự, khả năng chứa phần tử trùng và cách equals()/hashCode() hoạt động. Đồng thời, SQL vẫn có thể rất lớn.

**Đặt mọi quan hệ thành FetchType.EAGER.** EAGER yêu cầu association được tải theo ngữ nghĩa fetch của JPA, nhưng không bảo đảm một câu SQL hiệu quả. Provider có thể dùng join hoặc các truy vấn phụ; việc tải quá nhiều dữ liệu vẫn gây chậm.

**Fetch đồng thời nhiều collection trong EntityGraph mà không kiểm tra SQL.** EntityGraph giúp định nghĩa association cần tải, nhưng không loại bỏ chi phí join hoặc giới hạn của Hibernate đối với nhiều bag.

**Dùng fetch join collection trực tiếp với Pageable.** Phân trang trên tập dòng đã nhân bản có thể cho kết quả sai kỳ vọng hoặc khiến Hibernate phải phân trang trong bộ nhớ. Hãy phân trang ID trước rồi tải collection theo nhóm.

**Trả entity có collection LAZY ra ngoài transaction.** Serializer hoặc tầng controller có thể truy cập collection sau khi persistence context đã đóng và gây LazyInitializationException. Hãy tải dữ liệu cần thiết trong transaction hoặc trả DTO phù hợp.

## 8. Kiểm thử và chẩn đoán

Một bài kiểm thử tích hợp hữu ích nên tạo dữ liệu có số lượng khác nhau ở từng collection, chẳng hạn một đơn hàng có 3 dòng hàng và 4 khoản giảm giá.

Với chiến lược chia truy vấn:

- Gọi service trong transaction.
- Xác nhận kết quả có đúng 3 dòng hàng.
- Xác nhận có đúng 4 khoản giảm giá.
- Xác nhận cả hai collection đã được khởi tạo trước khi kết thúc transaction.
- Kiểm tra dữ liệu không bị nhân đôi và các thuộc tính của từng phần tử đúng như database.

Với chiến lược batch hoặc subselect, hãy kiểm tra số câu SQL trên nhiều đơn hàng để xác nhận N+1 đã được giảm. Với phân trang, kiểm tra tổng số bản ghi, thứ tự trang và trường hợp một entity có nhiều phần tử trong collection.

Khi điều tra hiệu năng, bật SQL logging ở môi trường phát triển và xem:

- Số câu SQL được thực thi.
- Số dòng mỗi câu truy vấn trả về.
- Số lần truy vấn lặp theo từng entity.
- Các cột được lấy có thực sự cần thiết hay không.
- Thời gian database, thời gian hydrate entity và mức sử dụng bộ nhớ.

Có thể dùng Hibernate statistics hoặc công cụ quan sát truy vấn của database để đo số lần thực thi và thời gian. Không kết luận chỉ từ việc giảm số câu SQL: một câu join trả về hàng nghìn tổ hợp có thể tốn kém hơn vài câu truy vấn nhỏ.

## 9. Quy trình lựa chọn fetch strategy

1. Xác định chính xác collection nào cần dùng trong use case.
2. Kiểm tra mapping để biết collection nào là bag, Set hay indexed List.
3. Nếu chỉ cần một collection, cân nhắc fetch join hoặc EntityGraph cho collection đó.
4. Nếu cần nhiều bag, ưu tiên chia thành nhiều truy vấn trong cùng transaction hoặc dùng batch fetching.
5. Nếu cần trang dữ liệu, phân trang entity gốc trước rồi tải collection theo nhóm.
6. Nếu chỉ cần dữ liệu hiển thị, cân nhắc DTO projection.
7. Đo SQL và kiểm thử với dữ liệu có cardinality gần thực tế.

## Kết luận

MultipleBagFetchException thường là dấu hiệu fetch plan đang cố tải đồng thời nhiều bag trong một truy vấn Hibernate. Tích Descartes là vấn đề hiệu năng riêng: join nhiều collection có thể nhân số dòng SQL theo tích số phần tử, ngay cả khi không có ngoại lệ.

Cách xử lý bền vững là chọn dữ liệu theo nhu cầu của use case: chia truy vấn theo từng collection trong cùng persistence context, dùng batch/subselect fetching khi phù hợp, phân trang ID trước khi tải collection, hoặc trả DTO khi không cần entity graph đầy đủ. Chỉ chọn Set hay @OrderColumn khi ngữ nghĩa dữ liệu thực sự yêu cầu.