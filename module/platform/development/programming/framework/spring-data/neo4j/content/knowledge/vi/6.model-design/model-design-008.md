# Phân biệt mô hình ghi nghiệp vụ với mô hình đọc cho báo cáo

Trong một ứng dụng dùng Neo4j, cùng một dữ liệu có thể phục vụ hai nhóm công việc rất khác nhau. Luồng **ghi nghiệp vụ** cần bảo vệ quy tắc miền, lưu trạng thái có thẩm quyền và cập nhật các quan hệ liên quan một cách nhất quán. Luồng **đọc báo cáo** thường cần tổng hợp nhiều bản ghi, nhóm theo thời gian hoặc danh mục, và trả về đúng các chỉ số mà màn hình hay hệ thống phân tích cần.

Nếu cố dùng một cấu trúc duy nhất cho cả hai mục tiêu, mô hình có thể trở nên khó cập nhật hoặc truy vấn báo cáo tốn kém. Một cách tiếp cận hữu ích là phân biệt **write model** (mô hình ghi) và **read model** (mô hình đọc). Đây là tư duy thường gặp trong CQRS, nhưng không bắt buộc phải triển khai đầy đủ CQRS hay tách thành hai cơ sở dữ liệu. Với Spring Data Neo4j, ta có thể giữ dữ liệu nghiệp vụ trong một đồ thị chuẩn, dùng repository/service để ghi, và tạo truy vấn hoặc projection chuyên biệt cho nhu cầu đọc.

## 1. Hai mô hình giải quyết hai mục tiêu

**Write model** mô tả cách ứng dụng tạo và thay đổi trạng thái nghiệp vụ. Nó là nguồn dữ liệu có thẩm quyền (source of truth) cho các quyết định như đơn hàng thuộc khách hàng nào, sản phẩm nào nằm trong đơn, số lượng mua, giá tại thời điểm mua và trạng thái thanh toán.

**Read model** mô tả dữ liệu theo cách thuận tiện cho một hoặc nhiều truy vấn đọc. Nó có thể là kết quả truy vấn được ánh xạ thành DTO, một projection trả về một số trường, hoặc một cấu trúc đồ thị đã được tính toán trước để phục vụ báo cáo thường xuyên.

| Tiêu chí | Write model | Read model |
|---|---|---|
| Mục tiêu | Thực hiện lệnh nghiệp vụ và bảo toàn quy tắc miền | Trả lời câu hỏi đọc nhanh, rõ ràng và đúng định dạng |
| Câu hỏi thiết kế | Cần lưu thực thể và quan hệ nào để cập nhật trạng thái đúng? | Báo cáo cần nhóm, lọc, tổng hợp và hiển thị dữ liệu nào? |
| Dữ liệu | Dữ liệu nghiệp vụ có thẩm quyền, cùng các sự kiện/trạng thái cần thiết | Dữ liệu được chọn lọc, biến đổi, tổng hợp hoặc phi chuẩn hóa từ write model |
| Cách thay đổi | Qua các thao tác nghiệp vụ có kiểm soát | Được tính khi truy vấn hoặc cập nhật từ thay đổi ở write model |
| API thường dùng | Service, repository, `Neo4jTemplate` | `@Query`, projection, `Neo4jClient`, truy vấn Cypher báo cáo |
| Ưu tiên | Tính đúng đắn, tính nhất quán và khả năng bảo trì | Hiệu năng đọc, cấu trúc kết quả và khả năng phân tích |

Hai mô hình là hai cách tổ chức dữ liệu và thao tác theo mục đích. Chúng có thể dùng chung một database Neo4j, cùng một cụm node, hoặc dùng một read model được lưu riêng. Quyết định phụ thuộc tải đọc, độ phức tạp truy vấn, yêu cầu cập nhật và độ trễ dữ liệu mà nghiệp vụ chấp nhận.

## 2. Thiết kế write model theo nghiệp vụ

Giả sử hệ thống bán hàng cần lưu khách hàng, đơn hàng, sản phẩm và các dòng hàng trong đơn. Mô hình ghi có thể gồm:

- `Customer`: khách hàng đặt đơn.
- `Order`: đơn hàng, có mã đơn, thời điểm tạo và trạng thái.
- `Product`: sản phẩm trong danh mục.
- `PLACED_BY`: relationship nối đơn hàng với khách hàng.
- `CONTAINS`: relationship nối đơn hàng với sản phẩm, mang theo số lượng và đơn giá tại thời điểm mua.

Biểu diễn đồ thị:

```text
(Order)-[:PLACED_BY]->(Customer)
(Order)-[:CONTAINS {quantity, unitPrice}]->(Product)
```

`quantity` và `unitPrice` là thuộc tính của relationship `CONTAINS`, vì chúng mô tả dòng sản phẩm trong một đơn cụ thể. Giá hiện tại của `Product` có thể thay đổi, nhưng `unitPrice` trong dòng hàng cần giữ giá đã áp dụng tại thời điểm mua để báo cáo doanh thu lịch sử chính xác.

Ví dụ entity theo Spring Data Neo4j:

```java
@Node("Order")
public class PurchaseOrder {
    @Id
    @GeneratedValue
    private Long id;

    private String orderNumber;
    private String status;
    private Instant createdAt;

    @Relationship(type = "PLACED_BY", direction = Relationship.Direction.OUTGOING)
    private Customer customer;

    @Relationship(type = "CONTAINS", direction = Relationship.Direction.OUTGOING)
    private List<OrderLine> lines = new ArrayList<>();
}

@RelationshipProperties
public class OrderLine {
    @TargetNode
    private Product product;

    private int quantity;
    private BigDecimal unitPrice;
}
```

Các lớp `Customer` và `Product` cũng được khai báo là node entity bằng `@Node`, với thuộc tính định danh phù hợp. Đoạn mã tập trung minh họa cấu trúc của đơn hàng và relationship properties; trong ứng dụng thực tế cần bổ sung constructor, getter/setter, validation và quy tắc sinh ID theo thiết kế.

Write model nên lưu những thông tin cần để thực hiện nghiệp vụ và tái dựng sự thật đã xảy ra. Ví dụ, không nên chỉ lưu `totalAmount` nếu ứng dụng còn cần biết số lượng từng sản phẩm, giá tại thời điểm mua và sản phẩm thuộc danh mục nào. Ngược lại, không cần thêm hàng loạt thuộc tính chỉ để phục vụ một biểu đồ nếu chúng có thể được tính từ dữ liệu nghiệp vụ.

### Quy tắc khi cập nhật write model

- Thay đổi trạng thái đơn hàng qua service nghiệp vụ, nơi kiểm tra chuyển trạng thái hợp lệ.
- Giữ giá, số lượng và thông tin giao dịch có ý nghĩa lịch sử trong dòng hàng hoặc snapshot thích hợp.
- Dùng constraint và index cho các khóa nghiệp vụ cần duy nhất hoặc thường xuyên tra cứu, chẳng hạn `orderNumber` hay `customerId`.
- Đặt các thay đổi cần thành công cùng nhau trong một transaction Neo4j.
- Không để luồng báo cáo tự sửa dữ liệu nghiệp vụ chỉ nhằm làm cho một con số hiển thị thuận tiện.

## 3. Đọc báo cáo trực tiếp từ write model

Không phải hệ thống nào cũng cần lưu một read model riêng. Nếu dữ liệu còn vừa phải và truy vấn báo cáo đáp ứng yêu cầu thời gian, có thể đọc trực tiếp từ đồ thị nghiệp vụ bằng Cypher.

Ví dụ, báo cáo doanh thu theo tháng và danh mục sản phẩm:

```cypher
MATCH (o:Order)-[line:CONTAINS]->(p:Product)-[:IN_CATEGORY]->(c:Category)
WHERE o.status = 'PAID'
  AND date(o.createdAt) >= $fromDate
  AND date(o.createdAt) < $toDate
WITH date.truncate('month', date(o.createdAt)) AS month,
     c.categoryId AS categoryId,
     c.name AS categoryName,
     count(DISTINCT o) AS orderCount,
     sum(line.quantity) AS unitsSold,
     sum(line.quantity * line.unitPrice) AS grossRevenue
RETURN toString(month) AS yearMonth,
       categoryId,
       categoryName,
       orderCount,
       unitsSold,
       grossRevenue
ORDER BY month DESC, grossRevenue DESC
```

Truy vấn đi từ đơn hàng qua relationship `CONTAINS` đến sản phẩm rồi đến danh mục. Nó chỉ tính đơn đã thanh toán trong khoảng ngày yêu cầu. `sum(line.quantity * line.unitPrice)` tính doanh thu từ giá trị của từng dòng hàng; `count(DISTINCT o)` đếm số đơn khác nhau trong từng nhóm tháng và danh mục.

Các tham số `$fromDate` và `$toDate` giúp giới hạn kỳ báo cáo. Cận trên được dùng theo kiểu không bao gồm (`< $toDate`) để thuận tiện ghép các khoảng thời gian liền nhau mà không đếm trùng ngày biên. Cần thống nhất múi giờ và cách chuyển thời điểm giao dịch sang ngày nghiệp vụ trước khi tổng hợp.

Đọc trực tiếp có các lợi ích:

- Không cần đồng bộ một bản sao dữ liệu báo cáo.
- Kết quả phản ánh trạng thái hiện tại của write model trong transaction đọc.
- Ít thành phần vận hành và ít nguy cơ sai lệch giữa dữ liệu gốc với dữ liệu tổng hợp.

Tuy nhiên, truy vấn có thể phải duyệt nhiều đơn hàng, relationship và dòng hàng mỗi lần mở dashboard. Khi báo cáo chạy liên tục, phạm vi thời gian dài hoặc đồ thị tăng lớn, phép tổng hợp lặp lại có thể trở thành nút thắt. Khi đó, hãy đo truy vấn và xem xét projection đọc.

## 4. Tạo read model cho báo cáo

Một read model được lưu trước (materialized read model) là dữ liệu đã được chuẩn bị theo hình dạng mà báo cáo thường xuyên cần. Với ví dụ trên, có thể tạo node `MonthlyCategorySales` cho mỗi cặp tháng và danh mục:

```text
(MonthlyCategorySales {
    yearMonth,
    categoryId,
    categoryName,
    orderCount,
    unitsSold,
    grossRevenue,
    updatedAt
})
```

Read model này đã gom các đơn hàng thành chỉ số theo tháng và danh mục. Dashboard có thể đọc trực tiếp các node tổng hợp thay vì đi qua từng đơn hàng và dòng sản phẩm.

Tạo constraint để bảo đảm mỗi cặp tháng và danh mục chỉ có một node tổng hợp:

```cypher
CREATE CONSTRAINT monthly_category_sales_key IF NOT EXISTS
FOR (s:MonthlyCategorySales)
REQUIRE (s.yearMonth, s.categoryId) IS UNIQUE
```

Ví dụ cập nhật một nhóm tổng hợp sau khi một đơn hàng được thanh toán:

```cypher
MERGE (s:MonthlyCategorySales {
    yearMonth: $yearMonth,
    categoryId: $categoryId
})
ON CREATE SET s.orderCount = 0,
              s.unitsSold = 0,
              s.grossRevenue = 0
SET s.orderCount = s.orderCount + $orderCountDelta,
    s.unitsSold = s.unitsSold + $unitsSoldDelta,
    s.grossRevenue = s.grossRevenue + $revenueDelta,
    s.categoryName = $categoryName,
    s.updatedAt = datetime()
```

Trước khi chạy câu lệnh này, ứng dụng cần tính các delta từ đơn hàng vừa thanh toán và gom các dòng hàng cùng danh mục thành một nhóm. Với mỗi danh mục xuất hiện trong đơn, `orderCountDelta` thường là `1`, `unitsSoldDelta` là tổng số lượng của danh mục trong đơn và `revenueDelta` là tổng số lượng nhân với đơn giá snapshot. Nếu một đơn có nhiều dòng thuộc cùng danh mục, phải cộng chúng trước khi cập nhật node tổng hợp để không tăng số đơn nhiều lần.

Truy vấn đọc báo cáo khi đó đơn giản hơn:

```cypher
MATCH (s:MonthlyCategorySales)
WHERE s.yearMonth >= $fromMonth
  AND s.yearMonth < $toMonth
RETURN s.yearMonth AS yearMonth,
       s.categoryId AS categoryId,
       s.categoryName AS categoryName,
       s.orderCount AS orderCount,
       s.unitsSold AS unitsSold,
       s.grossRevenue AS grossRevenue
ORDER BY yearMonth DESC, grossRevenue DESC
```

Đây là một read model phi chuẩn hóa có chủ đích: tên danh mục và các số tổng hợp được lưu cùng nhau để đọc thuận tiện. Nếu tên danh mục thay đổi, cần quyết định báo cáo dùng tên hiện tại hay tên tại thời điểm phát sinh giao dịch, rồi cập nhật projection theo quy tắc đã chọn.

## 5. Cập nhật read model và độ nhất quán

Read model được tạo từ write model nên cần một chiến lược đồng bộ. Hai cách phổ biến là cập nhật đồng bộ trong cùng transaction hoặc cập nhật bất đồng bộ qua sự kiện.

### Cập nhật đồng bộ

Sau khi nghiệp vụ ghi thành công, ứng dụng cập nhật projection trong cùng transaction Neo4j. Nếu cả hai thao tác dùng cùng transaction manager và cùng database, transaction có thể bảo đảm thay đổi nghiệp vụ và projection cùng commit hoặc cùng rollback.

Ưu điểm là dữ liệu báo cáo sẵn sàng ngay sau khi transaction hoàn tất. Đổi lại, transaction ghi phải thực hiện thêm công việc tổng hợp; thời gian ghi tăng và mô hình cập nhật projection trở nên gắn với luồng nghiệp vụ.

### Cập nhật bất đồng bộ

Luồng ghi phát ra sự kiện như `OrderPaid`, còn một projection handler nhận sự kiện và cập nhật `MonthlyCategorySales`. Sự kiện có thể được chuyển qua message broker hoặc một cơ chế truyền sự kiện phù hợp. Cách này giảm công việc báo cáo trong request ghi và cho phép xây dựng nhiều projection độc lập.

Đổi lại, read model có thể chậm hơn write model một khoảng thời gian. Đây là **eventual consistency**: sau khi đơn hàng được thanh toán, dashboard có thể chưa phản ánh đơn đó cho đến khi projection xử lý xong sự kiện.

Khi triển khai bất đồng bộ, cần thiết kế rõ:

- **Phát sự kiện đáng tin cậy:** tránh trường hợp transaction ghi đã commit nhưng sự kiện không được gửi. Có thể dùng transactional outbox hoặc cơ chế tương đương.
- **Xử lý lặp an toàn:** message broker có thể giao lại sự kiện. Handler phải có idempotency key hoặc bảng/đồ thị ghi nhận sự kiện đã xử lý để không cộng doanh thu hai lần.
- **Thứ tự sự kiện:** nếu trạng thái đơn hàng có thể thay đổi nhiều lần, cần xác định cách xử lý sự kiện đến trễ hoặc sai thứ tự.
- **Thử lại và giám sát:** theo dõi số sự kiện chờ xử lý, lỗi projection và độ trễ cập nhật.
- **Tái dựng projection:** có quy trình xóa/tạo lại hoặc tính lại read model từ dữ liệu nguồn khi thay đổi công thức báo cáo hoặc phát hiện sai lệch.

Đặc biệt, câu lệnh tăng bộ đếm bằng `s.orderCount = s.orderCount + 1` không tự idempotent. Nếu cùng sự kiện thanh toán được xử lý hai lần, số liệu sẽ bị cộng hai lần. Cần ghi nhận định danh sự kiện/đơn hàng đã áp dụng trước khi thực hiện delta, hoặc dùng chiến lược tính lại có thể chạy lặp mà cho cùng kết quả.

## 6. Tích hợp với Spring Data Neo4j

Trong ứng dụng Spring Boot, có thể tổ chức hai luồng bằng các service và repository riêng theo trách nhiệm.

Luồng ghi sử dụng repository entity để lưu mô hình nghiệp vụ:

```java
public interface PurchaseOrderRepository
        extends Neo4jRepository<PurchaseOrder, Long> {
    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}

@Service
public class OrderCommandService {
    private final PurchaseOrderRepository orderRepository;

    public OrderCommandService(PurchaseOrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public PurchaseOrder save(PurchaseOrder order) {
        // Kiểm tra quy tắc nghiệp vụ trước khi lưu trong ứng dụng thực tế.
        return orderRepository.save(order);
    }
}
```

Luồng đọc có thể dùng `@Query` với interface projection để trả về đúng cột báo cáo, không cần tải toàn bộ entity và các quan hệ không liên quan:

```java
public interface MonthlyCategorySalesView {
    String getYearMonth();
    String getCategoryId();
    String getCategoryName();
    Long getOrderCount();
    Long getUnitsSold();
    BigDecimal getGrossRevenue();
}

public interface OrderReportRepository
        extends Neo4jRepository<PurchaseOrder, Long> {

    @Query("""
        MATCH (o:Order)-[line:CONTAINS]->(p:Product)-[:IN_CATEGORY]->(c:Category)
        WHERE o.status = 'PAID'
          AND date(o.createdAt) >= $fromDate
          AND date(o.createdAt) < $toDate
        WITH date.truncate('month', date(o.createdAt)) AS month,
             c.categoryId AS categoryId,
             c.name AS categoryName,
             count(DISTINCT o) AS orderCount,
             sum(line.quantity) AS unitsSold,
             sum(line.quantity * line.unitPrice) AS grossRevenue
        RETURN toString(month) AS yearMonth,
               categoryId AS categoryId,
               categoryName AS categoryName,
               orderCount AS orderCount,
               unitsSold AS unitsSold,
               grossRevenue AS grossRevenue
        ORDER BY month DESC, grossRevenue DESC
        """)
    List<MonthlyCategorySalesView> findMonthlySales(
        @Param("fromDate") LocalDate fromDate,
        @Param("toDate") LocalDate toDate
    );
}
```

Interface projection chỉ khai báo những getter cần thiết cho báo cáo. Các alias trong `RETURN` cần khớp với tên property mà projection cung cấp. Tùy phiên bản Spring Data Neo4j và cách ánh xạ kết quả, có thể dùng DTO class hoặc `Neo4jClient` để kiểm soát việc chuyển đổi kết quả tùy chỉnh.

Nếu dùng read model đã lưu, repository báo cáo sẽ truy vấn label `MonthlyCategorySales`. Có thể tạo một repository riêng cho projection hoặc dùng `Neo4jClient` để thực hiện Cypher. Không nên giả định mọi projection báo cáo đều là entity có vòng đời giống write model: một DTO trả về từ truy vấn chỉ là cấu trúc kết quả, còn node tổng hợp được lưu trong Neo4j là dữ liệu cần cơ chế cập nhật và tái dựng.

## 7. Chọn đọc trực tiếp hay tạo projection?

Không cần tạo read model riêng cho mọi màn hình. Hãy bắt đầu bằng truy vấn trên write model, đo thời gian và mức tải, sau đó chỉ materialize những báo cáo có tần suất cao hoặc chi phí tính toán đáng kể.

| Tình huống | Hướng tiếp cận phù hợp | Lý do |
|---|---|---|
| Màn hình chi tiết một đơn hàng | Đọc write model qua repository | Dữ liệu có cấu trúc rõ và cần trạng thái hiện tại. |
| Báo cáo nhỏ, truy vấn chạy nhanh | Cypher aggregation trực tiếp | Không phải duy trì dữ liệu trùng lặp. |
| Dashboard tổng hợp theo ngày/tháng, được mở thường xuyên | Materialized read model | Tránh tính lại cùng một phép tổng hợp trên nhiều request. |
| Nhiều báo cáo cần hình dạng dữ liệu khác nhau | Nhiều projection theo mục tiêu đọc | Mỗi projection có thể tối ưu cho một nhóm truy vấn. |
| Báo cáo cần số liệu gần thời gian thực | Đọc trực tiếp hoặc projection đồng bộ | Giảm độ trễ giữa thay đổi và kết quả hiển thị. |
| Báo cáo chấp nhận trễ vài giây/phút và tải ghi cao | Projection bất đồng bộ | Tách tải tổng hợp khỏi request ghi. |

Trước khi tạo projection, hãy trả lời được ba câu hỏi: truy vấn hiện tại chậm ở đâu, báo cáo chấp nhận độ trễ bao lâu, và nhóm nào chịu trách nhiệm sửa/tái dựng projection khi công thức thay đổi. Nếu chưa có câu trả lời, một truy vấn Cypher rõ ràng trên dữ liệu gốc thường là điểm bắt đầu tốt.

## 8. Rủi ro khi duy trì hai mô hình

Read model làm tăng tốc độ đọc bằng cách lưu thêm dữ liệu, nhưng cũng tạo thêm trách nhiệm vận hành.

- **Dữ liệu trùng lặp:** một giá trị như `categoryName` có thể tồn tại ở cả node `Category` và node tổng hợp. Cần xác định nguồn nào có thẩm quyền và thời điểm cập nhật bản sao.
- **Sai lệch do cập nhật thiếu:** nếu một luồng ghi thay đổi trạng thái đơn nhưng không phát sự kiện hoặc không cập nhật projection, báo cáo sẽ sai. Mọi đường thay đổi write model cần tham gia cùng quy trình đồng bộ.
- **Sự kiện lặp:** tăng số liệu theo delta có thể làm báo cáo phình lên khi handler nhận lại sự kiện. Idempotency phải được thiết kế ngay từ đầu.
- **Thay đổi công thức:** khi định nghĩa doanh thu thay đổi, cần version hóa hoặc tái dựng projection để các kỳ báo cáo không trộn lẫn công thức cũ và mới.
- **Xóa hoặc hoàn tiền:** phải quyết định sự kiện hủy đơn, hoàn tiền hay trả hàng làm giảm chỉ số cũ, tạo bút toán điều chỉnh hay ghi nhận chỉ số riêng. Không nên xóa dấu vết giao dịch đã phát sinh nếu nghiệp vụ cần kiểm toán.
- **Bảo mật và phân quyền:** projection phải giữ các ranh giới tenant, tổ chức hoặc quyền xem dữ liệu như write model. Dữ liệu tổng hợp không mặc nhiên được phép công khai cho mọi người dùng.
- **Chi phí lưu trữ và cập nhật:** mỗi projection tiêu tốn dung lượng và thêm công việc ghi. Chỉ duy trì những projection có người dùng và mục đích rõ ràng.

Với báo cáo tài chính hoặc doanh thu, cần thống nhất đơn vị tiền tệ, quy tắc làm tròn, thời điểm ghi nhận doanh thu, múi giờ và cách xử lý thuế/hoàn tiền. Một con số tổng hợp nhanh nhưng định nghĩa nghiệp vụ không rõ vẫn là một báo cáo sai.

## 9. Quy trình thiết kế thực tế

1. **Xác định lệnh và quy tắc nghiệp vụ.** Liệt kê thao tác tạo, cập nhật, hủy, thanh toán và các invariant cần bảo vệ.
2. **Thiết kế write model.** Chọn node, label, relationship, hướng quan hệ và relationship properties phản ánh sự thật nghiệp vụ.
3. **Liệt kê câu hỏi báo cáo.** Xác định bộ lọc, chiều nhóm, phép tổng hợp, kỳ thời gian và định dạng đầu ra.
4. **Thử truy vấn trực tiếp.** Viết Cypher và kiểm tra kế hoạch bằng `EXPLAIN`/`PROFILE` với dữ liệu gần thực tế.
5. **Chỉ tạo read model khi có bằng chứng cần thiết.** Chọn projection dạng DTO nếu chỉ cần ánh xạ kết quả, hoặc node/relationship tổng hợp nếu cần lưu kết quả để tái sử dụng.
6. **Chọn cơ chế đồng bộ.** Quyết định cập nhật cùng transaction hay xử lý sự kiện bất đồng bộ, kèm chiến lược idempotency và retry.
7. **Đo và đối soát.** So sánh số liệu projection với truy vấn tính từ write model; theo dõi độ trễ và xây dựng khả năng rebuild.

## 10. Ghi nhớ

Write model là cấu trúc có thẩm quyền để thực hiện nghiệp vụ và bảo toàn dữ liệu. Read model là cách tổ chức dữ liệu nhằm trả lời truy vấn hoặc báo cáo hiệu quả. Trong Neo4j, write model thường thể hiện các thực thể và quan hệ miền nghiệp vụ; read model có thể là DTO/projection lấy bằng Cypher hoặc đồ thị tổng hợp đã materialize.

Spring Data Neo4j hỗ trợ cả hai hướng: repository và transaction cho luồng ghi; `@Query`, projection và `Neo4jClient` cho luồng đọc. Chỉ nên duy trì read model lưu riêng khi lợi ích đọc đủ lớn để bù cho chi phí đồng bộ, xử lý sự kiện, chống cập nhật lặp, đối soát và tái dựng dữ liệu.
