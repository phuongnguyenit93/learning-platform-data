# Đánh giá lợi ích, chi phí và giới hạn của ORM

Khi xây dựng ứng dụng Java sử dụng cơ sở dữ liệu quan hệ, một quyết định quan trọng là **nên để ORM (Object–Relational Mapping) quản lý việc đọc/ghi dữ liệu đến mức nào**. ORM giúp biểu diễn các hàng trong bảng thành đối tượng Java và đồng bộ thay đổi của đối tượng với cơ sở dữ liệu. Tuy nhiên, ORM không làm biến mất SQL, khóa giao dịch, chi phí truy vấn hay sự khác biệt giữa mô hình đối tượng và mô hình quan hệ.

Bài học này tập trung vào cách **đánh giá một lựa chọn kiến trúc**, thay vì mặc định ORM luôn tốt hoặc luôn chậm. Trong hệ sinh thái Java, ví dụ chính là **Jakarta Persistence (JPA)** với một nhà cung cấp ORM như Hibernate; các nguyên tắc cũng áp dụng cho những ORM khác.

## 1. Hiểu rõ ORM đem lại điều gì

### 1.1. Hai mô hình dữ liệu khác nhau

Trong Java, một đơn hàng có thể được biểu diễn bằng đối tượng `PurchaseOrder` chứa danh sách `OrderLine`. Trong cơ sở dữ liệu quan hệ, cùng dữ liệu đó thường nằm ở hai bảng có khóa chính, khóa ngoại và ràng buộc:

```text
Mô hình đối tượng Java                   Mô hình quan hệ
PurchaseOrder                            purchase_orders
  id, status, total                         id (PK), status, total
  lines: List<OrderLine>                    ...
        |                                         |
        v                                         | 1 - n
     OrderLine                              order_lines
       id, quantity                           id (PK), order_id (FK), quantity
       order: PurchaseOrder
```

ORM chịu trách nhiệm ánh xạ lớp ↔ bảng, thuộc tính ↔ cột, quan hệ đối tượng ↔ khóa ngoại, rồi tạo hoặc thực thi câu SQL phù hợp. Điều này giảm mã lặp, nhưng không xóa được **sự chênh lệch giữa hai mô hình** (*object–relational impedance mismatch*): đối tượng có kế thừa, tham chiếu và vòng đời trong bộ nhớ; bảng có tập hợp hàng, phép JOIN và các ràng buộc nhất quán dữ liệu.

### 1.2. Phân biệt ORM, JPA, Hibernate và Spring Data JPA

| Thành phần | Vai trò | Điểm cần nhớ khi đánh giá |
|---|---|---|
| **ORM** | Kỹ thuật/công cụ ánh xạ đối tượng với dữ liệu quan hệ | Một cách tiếp cận kiến trúc, không đồng nghĩa với mọi thư viện truy cập dữ liệu |
| **JPA / Jakarta Persistence** | Đặc tả API và quy tắc quản lý thực thể, ngữ cảnh lưu trữ, truy vấn JPQL... | Đưa ra mô hình lập trình tương đối độc lập nhà cung cấp; không đảm bảo SQL và hiệu năng giống nhau |
| **Hibernate** | Một triển khai phổ biến của JPA, có thêm tính năng riêng | Hành vi fetch, batching, cache và SQL chịu ảnh hưởng của phiên bản/cấu hình |
| **Spring Data JPA** | Lớp repository hỗ trợ xây truy vấn và thao tác với JPA | Giảm mã tầng truy cập dữ liệu nhưng vẫn chạy trên JPA và nhà cung cấp ORM |
| **JDBC / SQL trực tiếp** | Gửi lệnh SQL và xử lý kết quả ở mức thấp hơn | Cho quyền kiểm soát truy vấn cao, đổi lại cần tự quản lý nhiều phần ánh xạ và mã truy cập |

Ví dụ ánh xạ thực thể bằng JPA (lược bớt constructor và accessor để tập trung vào ý chính):

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    private BigDecimal total;

    @Version
    private long version;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    public void approve() {
        this.status = OrderStatus.APPROVED;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}

@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    private int quantity;
}
```

Đối với thực thể đang được quản lý trong một giao dịch, JPA có thể phát hiện thay đổi (*dirty checking*) và ghi SQL `UPDATE` khi *flush*:

```java
@Transactional
public void approveOrder(Long orderId) {
    PurchaseOrder order = entityManager.find(PurchaseOrder.class, orderId);
    if (order == null) {
        throw new IllegalArgumentException("Không tìm thấy đơn hàng");
    }
    order.approve();
    // Không cần gọi UPDATE thủ công nếu order đang được quản lý.
}
```

Trong ví dụ, `@Transactional` thiết lập ranh giới giao dịch (chẳng hạn với Spring). *Flush* có thể diễn ra trước một số truy vấn hoặc khi commit; thời điểm chính xác phụ thuộc cách dùng API và chế độ flush. **Không nên hiểu rằng mỗi lệnh gán thuộc tính lập tức ghi xuống cơ sở dữ liệu.**

## 2. Lợi ích thực tế của ORM

### 2.1. Giảm mã lặp và tăng tốc phát triển nghiệp vụ

Một tác vụ CRUD thường cần ánh xạ tham số SQL, đọc từng cột từ kết quả truy vấn, chuyển kiểu, xử lý quan hệ và quản lý trạng thái cập nhật. ORM cung cấp cơ chế chung cho phần lớn công việc này. Với ứng dụng có nhiều thực thể và nghiệp vụ thay đổi thường xuyên, lợi ích lớn nhất có thể là **giảm chi phí xây dựng và bảo trì**, đặc biệt ở các thao tác ghi có quan hệ rõ ràng.

Ví dụ, thao tác đổi trạng thái đơn hàng có thể diễn đạt qua `order.approve()`, giúp mã nghiệp vụ thể hiện quy tắc của miền dữ liệu. Khi dùng JDBC thuần, đội ngũ thường phải viết thêm lớp ánh xạ kết quả, câu lệnh `UPDATE` và quy tắc phối hợp giữa các bảng.

Lợi ích này phụ thuộc vào mức độ phù hợp: nếu ứng dụng chỉ chạy vài truy vấn thống kê cố định, lớp thực thể và cơ chế quản lý trạng thái có thể tạo thêm việc hơn là tiết kiệm việc.

### 2.2. Quản lý trạng thái đối tượng trong giao dịch

JPA sử dụng **persistence context** để theo dõi các thực thể đang được quản lý (*managed entities*). Cơ chế này đem lại:

- **Identity map:** trong cùng một persistence context, một thực thể có một định danh sẽ tương ứng với cùng một thể hiện đối tượng được quản lý; giảm sự không nhất quán khi nhiều đoạn mã cùng xử lý thực thể đó.
- **Dirty checking:** phát hiện thuộc tính đã đổi và tạo câu lệnh cập nhật tại thời điểm flush.
- **Unit of work:** gom các thay đổi liên quan trong một phạm vi giao dịch, giúp tổ chức thao tác nghiệp vụ.
- **Ánh xạ quan hệ:** điều hướng giữa các thực thể theo cách tự nhiên trong mã Java khi dữ liệu tương ứng đã được tải.

Các cơ chế này **không thay thế** transaction của cơ sở dữ liệu: commit, rollback, khóa, mức cô lập và ràng buộc dữ liệu vẫn do cơ sở dữ liệu cùng tầng giao dịch thực thi.

### 2.3. Tổ chức mã, truy vấn và khả năng thay đổi

Các annotation như `@Entity`, `@ManyToOne`, `@Version` giúp khai báo ý nghĩa dữ liệu tại một vị trí nhất quán. JPQL và Criteria API cho phép viết truy vấn dựa trên thực thể, hỗ trợ tái cấu trúc mã cùng mô hình Java. Phần mềm có thể kết hợp thực thể, repository, service và DTO để tách cách lưu trữ khỏi giao diện API.

JPA cũng giúp giảm phụ thuộc vào một số cú pháp SQL riêng của từng hệ quản trị. Tuy nhiên, **tính di động là tương đối**: kiểu dữ liệu, hàm SQL, cách phân trang, chiến lược sinh khóa, khóa và tối ưu truy vấn vẫn có thể khác giữa PostgreSQL, MySQL, Oracle, SQL Server...

### 2.4. Khả năng dùng lại những tính năng đã được kiểm chứng

ORM thường cung cấp các chức năng như truy vấn có tham số, lazy/eager fetching, batch operation, bộ đệm cấp một và tùy chọn bộ đệm cấp hai, optimistic locking, tích hợp transaction. Dùng đúng cách giúp giảm lỗi ở mã truy cập dữ liệu tự viết. Nhưng mỗi tính năng cần hiểu rõ phạm vi; ví dụ **cache không thay thế thiết kế truy vấn tốt** và có thêm chi phí đồng bộ/vô hiệu hóa.

## 3. Chi phí của ORM: phải tính cả khi chạy và khi bảo trì

| Nhóm chi phí | Biểu hiện thường gặp | Hệ quả cần đo/kiểm soát |
|---|---|---|
| **Học và vận hành** | Cần hiểu entity state, flush, transaction, cascade, fetch, proxy, cache | Thời gian học, gỡ lỗi, đào tạo và review mã |
| **Truy vấn ẩn** | Đọc một quan hệ có thể tự tạo SQL; sửa đối tượng phát sinh UPDATE khi flush | Tăng số truy vấn, tăng độ trễ, khó dự đoán đường đi dữ liệu |
| **Tải dư dữ liệu** | Nạp cả thực thể và quan hệ khi màn hình chỉ cần vài cột | Tăng truyền dữ liệu, heap và thời gian xử lý |
| **Chi phí quản lý thực thể** | Tracking nhiều đối tượng, snapshot trạng thái, map kết quả thành object graph | Tăng bộ nhớ/CPU; không phù hợp với lô dữ liệu cực lớn |
| **Độ phức tạp quan hệ** | JOIN nhiều collection, cascade quá rộng, chu trình tham chiếu | Dữ liệu nhân bản khi JOIN, khóa lâu, phát sinh thao tác ngoài dự kiến |
| **Khác biệt nhà cung cấp** | SQL generator, dialect, hàm và tối ưu hóa không giống nhau | Cần kiểm tra SQL thực tế khi đổi phiên bản hoặc hệ CSDL |
| **Vòng đời dữ liệu** | Entity bị detached, lazy loading sau khi transaction đóng | Lỗi runtime, truy vấn phát sinh sai tầng, API phụ thuộc persistence context |

ORM **chuyển** một phần công việc từ mã ứng dụng sang framework; công việc đó vẫn tiêu thụ tài nguyên và vẫn phải được hiểu khi xảy ra lỗi.

### 3.1. N+1: một vòng lặp nhỏ có thể tạo nhiều truy vấn

Giả sử cần hiển thị 100 đơn hàng cùng số dòng hàng của từng đơn:

```java
List<PurchaseOrder> orders = entityManager.createQuery(
        "select o from PurchaseOrder o where o.status = :status",
        PurchaseOrder.class)
    .setParameter("status", OrderStatus.APPROVED)
    .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getLines().size());
}
```

Với quan hệ `LAZY` chưa được tải và không có tối ưu batch/cache phù hợp, thường xảy ra:

```text
1 SELECT lấy 100 đơn hàng
+ 100 SELECT lấy lines cho từng đơn
= 101 lượt truy vấn (ví dụ N+1)
```

Điểm gây chi phí chủ yếu không nhất thiết là kích thước dữ liệu mà có thể là **101 lượt tương tác với cơ sở dữ liệu**, nhất là khi có độ trễ mạng. ORM không tự biết màn hình cần quan hệ nào để tránh mọi N+1.

Một cách xử lý là lấy dữ liệu liên quan bằng `JOIN FETCH` khi khối dữ liệu đủ nhỏ:

```java
List<PurchaseOrder> orders = entityManager.createQuery(
        "select distinct o " +
        "from PurchaseOrder o " +
        "left join fetch o.lines " +
        "where o.status = :status",
        PurchaseOrder.class)
    .setParameter("status", OrderStatus.APPROVED)
    .getResultList();
```

Truy vấn này có thể giảm lượt truy vấn nhưng **JOIN với collection tạo nhiều hàng SQL cho một đơn hàng**. Nếu phân trang trực tiếp bằng `setMaxResults` trên collection fetch join, một số nhà cung cấp phải phân trang trong bộ nhớ hoặc không hỗ trợ tối ưu như mong đợi. Với danh sách lớn, thường nên **phân trang ID/thực thể chính rồi tải quan hệ cần thiết bằng truy vấn thứ hai**, hoặc dùng DTO/projection chỉ lấy những cột màn hình cần.

Lựa chọn khác là `EntityGraph` hoặc batch fetching, tùy nhu cầu và nhà cung cấp. Không có một cấu hình `EAGER` toàn cục nào giải quyết mọi truy vấn: tải quá nhiều quan hệ cũng gây chậm.

### 3.2. Lazy loading gắn chặt với ranh giới giao dịch

Khi quan hệ được tải chậm, việc gọi `order.getLines()` có thể yêu cầu một persistence context/session còn hoạt động. Nếu thực thể đã detached và collection chưa được tải, Hibernate có thể ném `LazyInitializationException`. Để tránh thiết kế khó kiểm soát:

1. Xác định dữ liệu đầu ra cần có ngay tại service hoặc use case.
2. Truy vấn đủ dữ liệu trong ranh giới transaction thích hợp.
3. Ánh xạ thành DTO cho API hoặc giao diện, không dựa vào serializer tự duyệt toàn bộ quan hệ của entity.

Giữ session mở đến tận lúc render/serialize có thể che giấu vấn đề nhưng làm tăng nguy cơ truy vấn phát sinh ngoài ý muốn. **Kế hoạch tải dữ liệu nên là lựa chọn có chủ đích của từng use case.**

### 3.3. Quá nhiều thực thể làm tăng chi phí bộ nhớ

Khi quét hàng trăm nghìn hoặc hàng triệu hàng, JPA có thể phải tạo object, lưu trạng thái quản lý để dirty checking và giữ chúng trong persistence context. Việc gọi `findAll()` rồi xử lý mọi dòng trong bộ nhớ có thể dẫn đến heap tăng mạnh, GC nhiều, transaction kéo dài.

Hướng xử lý tùy mục tiêu:

- Với truy vấn chỉ đọc: chọn **projection/DTO** phù hợp thay vì tải thực thể đầy đủ.
- Với xử lý theo lô: dùng batch có kích thước hữu hạn, `flush()`/`clear()` theo đợt khi thực sự cần, hoặc sử dụng JDBC batch, truy vấn SQL theo tập hợp.
- Với báo cáo và tổng hợp: đẩy `GROUP BY`, `SUM`, lọc và sắp xếp xuống cơ sở dữ liệu; không tải mọi hàng lên Java để tính.

Không có bảo đảm rằng ORM sẽ tự tối ưu một vòng lặp `persist()` thành thao tác hàng loạt hiệu quả. Batching phụ thuộc loại sinh khóa, cấu hình provider và cách dùng transaction.

### 3.4. Đồng thời và tính nhất quán không tự được giải quyết

`@Version` trong ví dụ thực thể hỗ trợ **optimistic locking**: khi hai giao dịch đọc cùng phiên bản rồi cùng cập nhật, giao dịch sau có thể gặp lỗi xung đột thay vì âm thầm ghi đè thay đổi trước. Ứng dụng vẫn phải quyết định báo lỗi, tải lại, gộp dữ liệu hay retry phù hợp nghiệp vụ.

ORM không thay được:

- Khóa chính, khóa ngoại, `UNIQUE`, `NOT NULL`, `CHECK` và các ràng buộc ở CSDL.
- Mức cô lập và việc phòng tránh deadlock/lock contention.
- Thiết kế transaction ngắn, rõ; quản lý số kết nối từ connection pool.
- Kế hoạch thay đổi schema bằng migration có kiểm soát.

Ngoài ra, JPQL/SQL bulk `UPDATE` hoặc `DELETE` có thể **bỏ qua cơ chế dirty checking thông thường của từng thực thể** và khiến dữ liệu đang có trong persistence context không còn khớp với CSDL. Sau thao tác bulk cần chủ động xử lý đồng bộ/clear context theo thiết kế.

## 4. Giới hạn: những bài toán ORM không biểu diễn tốt

**Truy vấn phân tích phức tạp.** Báo cáo dùng window function, recursive CTE, truy vấn địa lý, cấu trúc chuyên biệt theo CSDL, thao tác `UPSERT` hoặc các chiến lược tối ưu chỉ có ở một hệ quản trị có thể viết bằng SQL trực tiếp rõ ràng và hiệu quả hơn. JPQL là ngôn ngữ truy vấn thực thể; nó không bao phủ mọi khả năng của SQL hiện đại.

**Nhập/xuất dữ liệu quy mô lớn.** ETL, chuyển đổi và cập nhật hàng triệu hàng ưu tiên phép toán theo tập hợp hoặc batch, trong khi ORM mạnh ở thao tác đối tượng có vòng đời và quy tắc nghiệp vụ.

**Lược đồ di sản hoặc không phù hợp object graph.** Một database có trigger phức tạp, khóa ghép khó dùng, bảng phi chuẩn, nhiều view, stored procedure hoặc quyền truy cập đặc biệt có thể đòi hỏi ánh xạ khó bảo trì và nhiều ngoại lệ.

**Kiểm soát truy vấn rất chặt.** Khi cần kiểm soát từng JOIN, hint, index, thứ tự thực thi, locking clause, sử dụng SQL trực tiếp (hoặc công cụ SQL builder) thường dễ đánh giá hơn so với dựa hoàn toàn vào bộ sinh SQL của ORM.

**Tách biệt dữ liệu trong hệ phân tán.** ORM không tự biến các thao tác trên nhiều database/service thành một giao dịch nhất quán. Khi phát sinh giao tiếp giữa service, vẫn phải thiết kế outbox, idempotency, saga hoặc chiến lược phù hợp.

**Mô hình khác cơ sở dữ liệu quan hệ.** Document database, graph database hay hệ thống tìm kiếm văn bản có mô hình truy cập khác; ép chúng vào ORM quan hệ thường không đem lại lợi ích.

Những giới hạn này không có nghĩa phải loại bỏ JPA khỏi toàn bộ hệ thống. Một ứng dụng có thể dùng ORM cho luồng ghi nghiệp vụ, đồng thời dùng SQL trực tiếp cho một báo cáo hoặc tác vụ batch.

## 5. So sánh các cách truy cập dữ liệu

| Tiêu chí | ORM/JPA | JDBC hoặc SQL mapper | SQL builder kiểu jOOQ |
|---|---|---|---|
| CRUD nhiều thực thể liên hệ | Mạnh nhờ mapping, trạng thái và cascade có kiểm soát | Phải viết nhiều phần ánh xạ/thao tác hơn | SQL tường minh, vẫn cần thiết kế mapping/vòng đời |
| Kiểm soát SQL chính xác | Có thể dùng native query, nhưng truy vấn entity do provider sinh | Rất trực tiếp | Rất trực tiếp, thường hỗ trợ biểu diễn SQL theo kiểu an toàn |
| Truy vấn báo cáo/aggregation phức tạp | Thường kém thuận tiện hơn | Thuận tiện | Thuận tiện |
| Object graph và dirty checking | Có sẵn | Tự triển khai nếu cần | Không phải trọng tâm |
| Chi phí học | JPA state, mapping, fetch, provider | JDBC, SQL, mapping, transaction | SQL và API của thư viện |
| Rủi ro hiệu năng | N+1, fetch join, context lớn, SQL khó nhận biết | Truy vấn dễ quan sát nhưng vẫn có thể viết SQL chậm | Phụ thuộc chất lượng SQL và cách dùng |
| Phù hợp nhất | Nghiệp vụ hướng thực thể, CRUD, giao dịch | Lệnh SQL chuyên biệt, batch, đường truy cập tối ưu | Ứng dụng đặt SQL làm trung tâm, cần truy vấn phức tạp |

Không nên so sánh bằng một câu hỏi đơn giản như “ORM có nhanh hơn JDBC không?”. Cả hai đều đi qua kết nối đến cơ sở dữ liệu; khác biệt nằm ở **số truy vấn, hình dạng truy vấn, lượng dữ liệu, chi phí chuyển đổi và độ phức tạp bảo trì**. Một câu SQL được viết kém bằng JDBC vẫn có thể chậm hơn truy vấn JPA phù hợp, và ngược lại.

## 6. Khung ra quyết định cho một dự án

### Bước 1: Phân loại luồng dữ liệu thật sự

Liệt kê các use case quan trọng và xác định:

- **CRUD/giao dịch nghiệp vụ:** tạo/sửa đơn hàng, thanh toán, quản lý khách hàng; có quy tắc miền dữ liệu và quan hệ cần nhất quán.
- **Đọc để hiển thị:** trang danh sách có lọc, sắp xếp, phân trang, vài trường dữ liệu.
- **Phân tích/tổng hợp:** doanh thu theo tháng, top sản phẩm, truy vấn qua hàng triệu hàng.
- **Xử lý theo lô:** nhập CSV, đồng bộ dữ liệu, cập nhật hàng loạt.

Tỷ lệ gọi, kích thước kết quả, độ phức tạp JOIN, yêu cầu nhất quán và tần suất thay đổi nghiệp vụ thường ảnh hưởng quyết định hơn số lượng bảng đơn thuần.

### Bước 2: Đặt mục tiêu đo được

Ví dụ: API trang danh sách phải có độ trễ p95 dưới ngưỡng đã định, không vượt giới hạn kết nối, và các transaction cập nhật không giữ khóa quá lâu. Với từng use case, theo dõi **query count**, tổng thời gian SQL, p95/p99, số hàng trả về, CPU CSDL, bộ nhớ heap, tần suất GC, độ dài transaction và mức sử dụng connection pool.

Không chỉ nhìn thời gian chạy một query đơn lẻ: 100 query nhỏ nối tiếp có thể tốn hơn một query lớn, nhưng một JOIN quá lớn cũng có thể tiêu tốn bộ nhớ và băng thông. Phải đo trên dữ liệu và tải gần thực tế, quan sát SQL được tạo ra.

### Bước 3: So sánh phương án bằng mẫu đại diện

Chọn một vài tác vụ nặng hoặc rủi ro cao, thử ít nhất một cách dùng ORM hợp lý và một cách truy vấn trực tiếp/projection nếu có lý do cần đối chiếu. Cần so sánh **cùng dữ liệu, cùng kết quả, cùng điều kiện tải**, đồng thời ghi lại số dòng mã cần duy trì, khả năng kiểm tra và rủi ro thay đổi schema.

Đừng coi benchmark một truy vấn nhanh là kết luận cho cả dự án: chi phí phát triển, lỗi tính nhất quán và thay đổi yêu cầu cũng nằm trong tổng chi phí sở hữu.

### Bước 4: Quyết định theo từng luồng thay vì ép một công cụ cho tất cả

| Tình huống | Lựa chọn khởi đầu hợp lý | Điều cần cảnh giác |
|---|---|---|
| Ứng dụng quản lý có nhiều CRUD, quan hệ và giao dịch | JPA/ORM cho phần nghiệp vụ chính | Cascade, boundary transaction, N+1 |
| API danh sách tải nhiều, chỉ cần vài cột | Projection/DTO, có thể vẫn qua JPA | Tránh load toàn bộ entity và collection |
| Dashboard với JOIN, aggregation và hàm CSDL đặc thù | SQL trực tiếp hoặc SQL builder | Index, execution plan, tính ổn định của truy vấn |
| Import/update hàng trăm nghìn đến triệu bản ghi | Batch hoặc lệnh SQL theo tập hợp | Transaction lớn, lock, timeout, dung lượng log |
| Hệ thống dùng database di sản và stored procedure | Cách tiếp cận lai, chỉ ánh xạ phần phù hợp | Mapping rối, quy tắc bị phân tán |
| Nhóm chưa có kinh nghiệm quản lý persistence context | Giới hạn phạm vi ORM, đào tạo và review query | Sự tiện lợi ban đầu che khuất chi phí vận hành |

### Bước 5: Đặt các quy tắc kỹ thuật khi chọn ORM

Một hệ thống dùng JPA nên thống nhất những nguyên tắc tối thiểu: chọn fetch theo use case; không mặc định tải toàn bộ quan hệ; dùng DTO cho API; phân trang có chủ đích; tránh transaction quá dài; log hoặc quan sát SQL và query count ở môi trường phù hợp; kiểm tra execution plan cho truy vấn đắt; đặt ràng buộc ở CSDL; quản lý schema bằng migration. Với truy vấn cần tối ưu đặc thù, cho phép dùng native SQL thay vì cố viết mọi thứ bằng JPQL.

## 7. Ví dụ quyết định kiến trúc: hệ thống bán hàng

Giả sử một hệ thống có ba yêu cầu:

1. **Duyệt đơn hàng:** cập nhật trạng thái, kiểm tra quy tắc nghiệp vụ, ghi nhận lịch sử thay đổi; có nguy cơ cập nhật đồng thời.
2. **Hiển thị 20 đơn gần nhất:** chỉ cần mã đơn, trạng thái, tổng tiền; không cần toàn bộ dòng hàng.
3. **Báo cáo doanh thu nhiều năm:** gom nhóm theo thời gian, khu vực và sản phẩm trên lượng dữ liệu lớn.

Một phương án cân bằng:

- **Yêu cầu 1:** sử dụng JPA entity trong transaction, biểu diễn quy tắc qua phương thức miền dữ liệu, dùng `@Version` khi phù hợp, giữ ràng buộc dữ liệu ở CSDL.
- **Yêu cầu 2:** dùng projection DTO để chỉ lấy cột cần hiển thị, phân trang ở database; có thể viết bằng JPQL:

  ```java
  public record OrderSummary(
      Long id, OrderStatus status, BigDecimal total
  ) {}

  List<OrderSummary> page = entityManager.createQuery(
          "select new com.example.dto.OrderSummary(o.id, o.status, o.total) " +
          "from PurchaseOrder o order by o.id desc",
          OrderSummary.class)
      .setFirstResult(0)
      .setMaxResults(20)
      .getResultList();
  ```

  Trong mã thực tế, đặt `OrderSummary` ở package đúng với tên đầy đủ trong JPQL; cần bảo đảm truy vấn có thứ tự ổn định và bổ sung cơ chế phân trang phù hợp dữ liệu lớn.
- **Yêu cầu 3:** viết truy vấn SQL tổng hợp hoặc dùng kho dữ liệu chuyên báo cáo khi cần. Trả về các dòng kết quả dạng DTO thay vì tạo object graph từ hàng triệu bản ghi.

Cách tiếp cận này dùng JPA ở nơi vòng đời thực thể và giao dịch tạo lợi ích, đồng thời giữ quyền kiểm soát SQL ở những phần mà truy vấn là trọng tâm.

## 8. Những nhận định cần tránh

| Nhận định dễ mắc | Cách hiểu chính xác hơn |
|---|---|
| “Có ORM thì không cần biết SQL.” | Người phát triển vẫn phải hiểu JOIN, index, transaction, execution plan và SQL ORM sinh ra. |
| “`LAZY` luôn nhanh hơn `EAGER`.” | `LAZY` tránh tải dữ liệu chưa cần nhưng có thể gây N+1; `EAGER` có thể tải thừa. Kế hoạch fetch phụ thuộc từng truy vấn. |
| “ORM tự ngăn mọi lỗi đồng thời.” | Vẫn cần transaction, locking, constraint và quy tắc xử lý xung đột. |
| “JPA giúp đổi database không tốn công.” | API có tính di động, nhưng dialect, schema, data type, locking và hiệu năng còn phụ thuộc hệ quản trị. |
| “Cứ bật cache là truy vấn sẽ nhanh.” | Cache có tỷ lệ hit, chi phí bộ nhớ và bài toán invalidation; không sửa được query plan kém trong mọi tình huống. |
| “Dùng ORM nghĩa là cấm SQL thuần.” | JPA cho phép native query; kiến trúc lai thường là lựa chọn thực dụng. |
| “Ít dòng code thì tổng chi phí thấp.” | Phải tính cả giám sát, tuning, vận hành và thay đổi lâu dài. |

## 9. Câu hỏi tự đánh giá trước khi chọn ORM

Hãy thử trả lời cho **một use case cụ thể**, thay vì trả lời chung cho cả ứng dụng:

1. Trọng tâm là vòng đời thực thể/giao dịch nghiệp vụ hay một truy vấn báo cáo phức tạp?
2. Cần bao nhiêu thuộc tính và quan hệ để hoàn thành tác vụ? Có đang tải thừa dữ liệu không?
3. Một request gây ra bao nhiêu SQL và trả về bao nhiêu hàng? Query plan có phù hợp index?
4. Dữ liệu sẽ lớn đến đâu, cần batch/pagination/streaming không?
5. Những thao tác đồng thời có nguy cơ lost update, lock contention hay vi phạm constraint không?
6. Mức độ linh hoạt trước thay đổi nghiệp vụ có bù cho chi phí học và vận hành ORM?
7. Có truy vấn nào nên dùng DTO, JDBC, native SQL hoặc một hệ thống phân tích riêng?

**Kết luận:** ORM là lựa chọn mạnh khi ứng dụng cần quản lý nhiều thực thể và giao dịch nghiệp vụ có quan hệ rõ ràng, vì nó giảm mã lặp và cung cấp cơ chế quản lý trạng thái nhất quán. Giá phải trả là độ phức tạp ẩn trong SQL được tạo, kế hoạch tải dữ liệu và vòng đời persistence context. Đánh giá tốt là xác định use case, đo truy vấn và chi phí vận hành, rồi dùng **ORM cho phần phù hợp và SQL trực tiếp ở những đường truy cập cần kiểm soát chặt**.
