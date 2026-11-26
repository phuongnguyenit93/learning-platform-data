# Xác định ranh giới aggregate và các mẫu truy cập dữ liệu trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **aggregate** trong thiết kế miền nghiệp vụ với **document** và **collection** trong Couchbase.
2. Xác định phần dữ liệu nên nhúng (embed), phần nên tham chiếu bằng ID và phần có thể sao chép thành read model.
3. Phác thảo mô hình theo các thao tác đọc/ghi chủ đạo trước khi chọn cấu trúc JSON, khóa tài liệu và chỉ mục.
4. Ánh xạ một aggregate bằng Spring Data Couchbase, chọn Key-Value (KV), repository hoặc SQL++ theo từng nhu cầu, đồng thời dự kiến chi phí nhất quán và đồng thời ghi.

Bối cảnh: **Spring Data Couchbase** cung cấp document mapping, repository, CouchbaseTemplate và truy vấn SQL++; Couchbase tổ chức dữ liệu theo bucket/scope/collection, hỗ trợ CAS, TTL, transaction và API reactive. Bài này tập trung vào quyết định **ranh giới dữ liệu** và **mẫu truy cập**; những khả năng kể trên là công cụ triển khai quyết định đó.

## 1. Bắt đầu từ bất biến nghiệp vụ, không bắt đầu từ các bảng

Trong Domain-Driven Design (DDD), **aggregate** là một nhóm đối tượng được thay đổi thông qua một **aggregate root** để bảo vệ những điều kiện phải luôn đúng (*invariants*). Ví dụ:

- Một đơn hàng có các dòng hàng, số lượng và tổng tiền. Khi thêm dòng hàng, tổng tiền phải được tính lại phù hợp với chính các dòng hàng đó.
- Sản phẩm trong danh mục có giá hiện hành và tên hiển thị riêng; việc cập nhật giá sản phẩm không được làm thay đổi giá đã chốt của đơn hàng cũ.
- Tồn kho có quy tắc đặt giữ và đồng thời ghi riêng. Không nên coi toàn bộ tồn kho của một sản phẩm là thành phần bên trong một đơn hàng.

Một **document JSON** của Couchbase là đơn vị lưu trữ có khóa riêng; một mutation trên một document là nguyên tử. Vì vậy, ánh xạ một aggregate nhỏ, có dữ liệu con thay đổi cùng nhau vào một document thường giúp giữ bất biến bằng một lần ghi. Tuy nhiên, **aggregate là khái niệm miền**, còn document là đơn vị kỹ thuật: không được suy ra rằng mọi quan hệ đối tượng đều phải nhúng, hoặc mọi collection đều là một aggregate.

~~~mermaid
flowchart LR
    C["Customer\naggregate riêng"] -->|"customerId"| O["Order\naggregate root"]
    O --> I["OrderLine[]\nnhúng trong Order"]
    I -.->|"sku; giá và tên tại thời điểm mua"| P["Product\naggregate riêng"]
    O -.->|"yêu cầu giữ hàng"| S["Inventory\naggregate riêng"]
~~~

**Nguyên tắc ưu tiên:** những dữ liệu bắt buộc nhất quán **trong cùng một thao tác nghiệp vụ** là ứng viên tốt để chung aggregate; những đối tượng có vòng đời, quyền sửa hoặc mức độ cạnh tranh ghi độc lập thường nên tách.

## 2. Lập bản đồ mẫu truy cập trước khi vẽ document

Đặt câu hỏi từ API, công việc nền và báo cáo thực tế. Ví dụ với hệ thống bán hàng:

| Thao tác | Điều kiện truy cập | Tần suất dự kiến | Yêu cầu nhất quán | Cách truy cập phù hợp |
| --- | --- | --- | --- | --- |
| Xem chi tiết đơn | Biết chính xác orderId | Cao | Thấy dữ liệu đơn đã lưu | KV theo ID bằng repository |
| Thêm dòng vào đơn nháp | Biết orderId | Trung bình | Tổng tiền và danh sách dòng phải đồng bộ | Đọc–sửa–ghi một document, kiểm tra CAS |
| Liệt kê đơn của khách | Lọc customerId, sắp xếp thời gian | Cao | Có thể cần độ tươi tùy màn hình | SQL++ qua repository/query + secondary index |
| Xem giá sản phẩm hiện tại | Biết sku | Cao | Theo document sản phẩm | KV theo product ID |
| Giữ tồn kho khi đặt hàng | Liên quan đơn và tồn kho | Trung bình, có tranh chấp | Không được bán vượt tồn | Thiết kế phối hợp giữa các aggregate |
| Báo cáo doanh thu | Quét/lọc nhiều đơn theo thời gian | Theo lô | Có thể chấp nhận trễ có kiểm soát | Query/projection hoặc read model chuyên biệt |

Bảng trên là **giả định minh họa**, không phải đo đạc sản xuất. Với hệ thống thật, bổ sung số liệu như QPS, p95 latency, kích thước document, số phần tử tối đa của mảng, tốc độ tăng dữ liệu, số writer cùng sửa một khóa, nhu cầu phân trang và độ trễ chấp nhận được.

Ba câu hỏi phải trả lời cho **mỗi** luồng:

1. **Đọc:** truy xuất theo khóa đã biết, theo điều kiện lọc hay duyệt quan hệ? Cần trả cả document hay chỉ một vài trường?
2. **Ghi:** những trường nào phải cập nhật nguyên tử? Ai cùng ghi một document? Có thao tác chéo aggregate không?
3. **Tăng trưởng:** số phần tử con có giới hạn rõ không? Dữ liệu tồn tại bao lâu và có cần truy vấn riêng không?

Truy cập KV theo ID thường có đường đi trực tiếp và không cần secondary index. Truy vấn theo thuộc tính khác ID dùng SQL++/index và có chi phí lập chỉ mục, thực thi và độ tươi khác với KV. Spring Data Couchbase cũng phân biệt hai đường đi này: các thao tác một document với ID đã biết mặc định dùng KV; nhiều thao tác còn lại được triển khai bằng truy vấn SQL++.

## 3. Quy tắc chọn embed, reference và read model

| Lựa chọn | Phù hợp khi | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- | --- |
| **Embed** giá trị con trong document gốc | Con thuộc cùng vòng đời, thường đọc/ghi cùng, kích thước có giới hạn | Một lần lấy/gắn dữ liệu; mutation nguyên tử của document | Document phình to; nhiều writer cùng chạm một CAS; lặp dữ liệu nếu nhúng đối tượng dùng chung |
| **Reference bằng ID** tới document riêng | Đối tượng có danh tính/vòng đời riêng, được nhiều aggregate sử dụng hoặc cập nhật độc lập | Tránh nhân bản dữ liệu nguồn; giảm cạnh tranh ghi ở document gốc | Đọc thêm nhiều khóa hoặc query; nhất quán liên document cần cơ chế riêng |
| **Snapshot/denormalization** | Dữ liệu cần phản ánh thời điểm nghiệp vụ hoặc phục vụ truy vấn đọc rất thường xuyên | Đọc nhanh, ít phép ghép; lưu lịch sử đúng | Phải xác định ai làm chủ dữ liệu và cách đồng bộ khi nguồn thay đổi |
| **Read model / projection riêng** | Báo cáo, dashboard, tìm kiếm khác đáng kể thao tác ghi | Tối ưu chỉ mục, cấu trúc đọc, tránh làm aggregate quá lớn | Độ trễ cập nhật, vận hành pipeline và xử lý phát lại sự kiện |

**Cách xét ranh giới:**

- Nếu một thay đổi phải giữ nhiều trường nhất quán ngay lập tức, xem xét **cùng aggregate**.
- Nếu một thực thể còn sống và được cập nhật độc lập khi cha không tồn tại, xem xét **aggregate riêng**.
- Nếu một mảng có thể tăng không giới hạn (bình luận, sự kiện theo dõi, lượt truy cập), **không nhúng toàn bộ** vào document cha.
- Nếu nhiều tiến trình thường xuyên ghi các phần khác nhau của một document, đánh giá **hot document/CAS conflict** trước khi nhúng.
- Nếu đối tượng chỉ được đọc như một bản chụp lịch sử (tên và giá lúc mua), có thể **nhúng snapshot**, nhưng ghi rõ nguồn sự thật của giá hiện hành.
- Nếu yêu cầu tìm kiếm lặp lại trên dữ liệu con, cân nhắc array index hoặc read model; **đừng tách aggregate chỉ để có thể truy vấn một trường** khi bất biến vẫn đòi ghi nguyên tử.

**Điểm cân bằng:** nhúng quá ít gây nhiều lượt đọc và phối hợp; nhúng quá nhiều làm tăng kích thước, contention và chi phí cập nhật. Chọn theo **bất biến + vòng đời + workload**, không theo việc JSON cho phép lồng nhau bao nhiêu cấp.

## 4. Thiết kế mẫu: đơn hàng, sản phẩm và tồn kho

Giả sử lưu đơn hàng trong bucket **shop**, scope **sales**, collection **orders**; catalog và tồn kho ở những collection thích hợp khác. Cấu trúc tổ chức bucket/scope/collection là quyết định triển khai và phân quyền, **không tự động xác lập ranh giới aggregate**.

Document có khóa Couchbase `order::2026::00125`:

~~~json
{
  "customerId": "customer::u18",
  "createdAt": "2026-11-23T09:15:00Z",
  "status": "CONFIRMED",
  "items": [
    {
      "sku": "product::coffee250",
      "productNameAtPurchase": "Cà phê 250 g",
      "unitPriceAtPurchase": 120000,
      "quantity": 2
    },
    {
      "sku": "product::cup01",
      "productNameAtPurchase": "Ly sứ",
      "unitPriceAtPurchase": 90000,
      "quantity": 1
    }
  ],
  "totalAmount": 330000
}
~~~

Một document sản phẩm độc lập có thể dùng khóa `product::coffee250` và chứa tên/giá **hiện hành**. Một document tồn kho khác quản lý số lượng khả dụng/đã giữ. Dòng hàng lưu **snapshot** tên và đơn giá tại thời điểm chốt đơn để lịch sử không bị đổi khi catalog cập nhật. Trong thực tế nên quy định đơn vị tiền (ví dụ VND) và xử lý giảm giá, thuế, làm tròn trong cùng quy tắc tính tổng.

**Lưu ý về khóa:** khóa như `order::2026::00125` là **document key** của Couchbase, không buộc phải có trường `id` trong JSON. Spring Data ánh xạ khóa qua `@Id`; tên kiểu có tiền tố giúp quan sát và định tuyến logic nhưng không thay thế cho scope/collection hoặc ràng buộc nghiệp vụ.

### Ranh giới đề xuất

**Order** là aggregate root; **OrderLine** là value object nằm trong Order. Các thao tác thêm/bớt dòng, chốt trạng thái, tính lại tổng được định nghĩa qua Order. **Customer**, **Product** và **Inventory** giữ aggregate riêng; Order chỉ lưu ID hoặc snapshot cần thiết.

Khi chốt đơn mà phải trừ tồn kho, quy tắc này đi **qua hai aggregate**. Cần lựa chọn rõ: transaction đa document nếu bắt buộc cùng commit; hoặc giữ hàng/reservation và xử lý sự kiện bù nếu chấp nhận quy trình nhiều bước. Không nên mặc định việc gọi hai `repository.save(...)` sẽ trở thành một giao dịch nguyên tử.

## 5. Mapping aggregate bằng Spring Data Couchbase

Ví dụ dưới đây minh họa cấu trúc (rút gọn phần getter và những API quản lý trạng thái không liên quan):

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Order {
    @Id
    private String id;                 // Couchbase document key

    @Version
    private Long version;              // CAS do Spring Data quản lý

    @Field
    private String customerId;

    @Field
    private Instant createdAt;

    @Field
    private String status = "DRAFT";

    @Field
    private List<OrderLine> items = new ArrayList<>();

    @Field
    private BigDecimal totalAmount = BigDecimal.ZERO;

    protected Order() {}              // cho cơ chế ánh xạ dữ liệu

    public Order(String id, String customerId, Instant createdAt) {
        this.id = id;
        this.customerId = customerId;
        this.createdAt = createdAt;
    }

    public void addLine(OrderLine line) {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException("Chỉ sửa đơn nháp");
        }
        if (line == null || line.quantity() <= 0
                || line.unitPriceAtPurchase().signum() < 0) {
            throw new IllegalArgumentException("Dòng hàng không hợp lệ");
        }
        items.add(line);
        totalAmount = totalAmount.add(
            line.unitPriceAtPurchase()
                .multiply(BigDecimal.valueOf(line.quantity()))
        );
    }

    // Getter và các phương thức chuyển trạng thái được lược bớt.
}

public record OrderLine(
    String sku,
    String productNameAtPurchase,
    BigDecimal unitPriceAtPurchase,
    int quantity
) {}
~~~

**Giải thích quyết định:**

- `@Document` đánh dấu lớp gốc được lưu thành document; `@Id` ánh xạ khóa.
- **OrderLine không có repository và ID độc lập** trong thiết kế này: nó được lưu như giá trị lồng trong Order.
- `@Version Long` giữ giá trị CAS phục vụ optimistic locking; **không tự tăng/sửa version** như bộ đếm thông thường.
- Các phương thức nghiệp vụ phải bảo vệ bất biến. Mã thực tế còn cần kiểm tra null, SKU hợp lệ, trùng dòng, currency, tính tổng sau giảm giá và chuyển trạng thái có kiểm soát.
- Ví dụ dùng Java record cho giá trị con; nếu dự án dùng phiên bản Java/mapping khác, chọn POJO có constructor phù hợp. Cấu hình scope/collection của repository hoặc template phải trỏ đúng nơi lưu Order.

Repository minh họa hai kiểu truy cập:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository extends CouchbaseRepository<Order, String> {
    // Tìm theo ID: kế thừa findById(...), dùng KV khi biết khóa.
    // Tìm theo customerId: tạo truy vấn, cần index tương ứng.
    List<Order> findByCustomerIdOrderByCreatedAtDesc(String customerId);
}
~~~

Luồng sửa một aggregate:

~~~java
public void addOrderLine(String orderId, OrderLine line) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow(() -> new IllegalArgumentException("Không có đơn"));
    order.addLine(line);
    orderRepository.save(order);
}
~~~

Nếu hai request cùng đọc một phiên bản rồi cùng ghi, phiên bản cũ có thể gây `OptimisticLockingFailureException`. Xử lý bằng cách **đọc lại, đánh giá lại quy tắc nghiệp vụ và thử lại cả chu trình** với giới hạn số lần thích hợp, hoặc trả lỗi xung đột cho client. Không chỉ gọi lại `save` trên đối tượng cũ; mọi side effect bên ngoài cần tránh bị lặp khi retry.

### Khi nào dùng CouchbaseTemplate?

Repository phù hợp với thao tác aggregate phổ biến và phương thức truy vấn đơn giản. Dùng **CouchbaseTemplate** khi cần điều khiển rõ truy vấn/ghi nâng cao, phép tác động sub-document hay xây dựng thao tác phức tạp; vẫn giữ quy tắc chỉ sửa aggregate qua dịch vụ nghiệp vụ. Chọn API reactive khi toàn bộ đường đi xử lý và tải đồng thời có lợi từ I/O không chặn; reactive không thay đổi ranh giới aggregate hay bảo đảm nhất quán.

## 6. Thiết kế truy vấn và chỉ mục theo mẫu đọc

**Đọc theo ID:**

~~~java
Order order = orderRepository.findById("order::2026::00125")
    .orElseThrow();
~~~

Đây là truy cập KV, không cần secondary index trên `customerId` để đọc một document đã biết khóa.

**Danh sách đơn của khách theo thời gian:** giả sử truy vấn trực tiếp trên collection `shop.sales.orders` đã cấu hình trong môi trường minh họa:

~~~sql
CREATE INDEX ix_orders_customer_created
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);

SELECT META(o).id AS orderId,
       o.createdAt,
       o.status,
       o.totalAmount
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

- **Index bắt đầu bằng trường lọc** `customerId`, sau đó là `createdAt` phục vụ sắp xếp. Đây là điểm khởi đầu để đo và tinh chỉnh, không khẳng định luôn là phương án tối ưu.
- Truy vấn trên chỉ là **projection để đọc danh sách**. Nếu ánh xạ kết quả thành entity Order đầy đủ bằng Spring Data, phải dùng hình thức SELECT/mapping phù hợp, gồm metadata và điều kiện phân biệt lớp khi cần. Xem SQL++ thực tế do repository tạo, đặc biệt khi Spring Data thêm bộ lọc `_class`.
- Kiểm tra `EXPLAIN` và đo độ trễ/số document fetch trước khi chốt index. Index thêm chi phí bộ nhớ/lưu trữ và tác động tốc độ ghi.
- Với danh sách lớn, dùng phân trang có khóa tiếp nối ổn định (ví dụ `createdAt` kèm ID để phá hòa), hạn chế `OFFSET` sâu và tránh trả toàn bộ Order khi UI chỉ cần tóm tắt.
- Nếu truy vấn lọc sâu trong mảng **items**, SQL++ có cú pháp `ANY ... SATISFIES ... END` và Couchbase hỗ trợ **array index**. Chỉ tạo index kiểu này khi mẫu truy cập thực sự cần; không xây mọi index có thể có.

**Độ tươi dữ liệu:** index phục vụ SQL++ có thể được cập nhật bất đồng bộ so với KV. Một danh sách được truy vấn ngay sau khi ghi có thể chưa nhìn thấy kết quả nếu dùng mức nhất quán scan mặc định. Với luồng cần đọc lại ngay sau ghi, cân nhắc đọc KV theo ID hoặc cấu hình **scan consistency** thích hợp cho truy vấn; mức nhất quán cao hơn có thể tăng độ trễ. Kiểm chứng bằng đo đạc trong workload thật.

## 7. Ranh giới aggregate quyết định phương án nhất quán

| Tình huống | Biện pháp hợp lý | Lưu ý |
| --- | --- | --- |
| Sửa items và totalAmount của cùng Order | Một mutation document, `@Version`/CAS khi nhiều writer | Bất biến trong Order được giữ cùng một phiên bản |
| Hai tiến trình cùng sửa Order | Optimistic locking + xử lý xung đột | Retry phải đọc lại và không lặp thanh toán/gửi thông báo |
| Chốt Order đồng thời giữ Inventory | Transaction đa document **nếu yêu cầu nguyên tử nghiêm ngặt** | Cần cấu hình và đánh giá overhead/khả năng xung đột |
| Đặt hàng với giữ chỗ bất đồng bộ | Reservation + trạng thái chờ + idempotency/compensation | Phải mô hình hóa trạng thái trung gian và quy tắc bù |
| Cập nhật read model doanh thu | Event/projection có thể trễ | Gắn thời gian cập nhật và quy trình replay khi có lỗi |

Couchbase hỗ trợ transaction ACID trên nhiều document, kể cả khác collection/bucket. Trong Spring Data Couchbase, các thao tác template/repository phù hợp có thể tham gia transaction khi cấu hình đúng `CouchbaseTransactionManager` và `@Transactional`; tài liệu Spring Data yêu cầu entity tham gia transaction có trường `@Version Long`. **Transaction không thay thế thiết kế aggregate:** càng nhiều document phải phối hợp, càng tăng overhead và phạm vi tranh chấp.

TTL có ích cho document tạm (ví dụ yêu cầu giữ chỗ có hạn dùng) khi vòng đời dữ liệu cho phép xóa; không bật TTL cho toàn bộ lịch sử Order chỉ vì cart hoặc reservation có thời hạn. CAS và TTL là thuộc tính/thao tác lưu trữ; bất biến nghiệp vụ vẫn phải được diễn đạt trong code.

## 8. Những dấu hiệu thiết kế cần xem lại

1. **Nhúng toàn bộ lịch sử:** Customer chứa mảng hàng trăm nghìn Order hoặc Product chứa mọi Review. Mảng không có trần kích thước làm mỗi lần đọc/ghi ngày càng nặng. Nên tách Order/Review thành document riêng và truy vấn bằng index.
2. **Lưu toàn bộ thông tin Product trong mọi Order và luôn cố đồng bộ:** giá lịch sử bị thay đổi sai nghiệp vụ, fan-out cập nhật rất tốn kém. Chỉ lưu snapshot các trường cần tại thời điểm mua.
3. **Tách OrderLine thành document độc lập dù luôn phải cập nhật cùng tổng tiền:** một thao tác đơn giản thành nhiều lần đọc/ghi và bài toán nhất quán. Nhúng các dòng hàng có giới hạn thường hợp lý hơn.
4. **Dùng một Order làm nơi mọi workflow liên tục cập nhật:** payment, shipment, tracking và audit cùng ghi gây CAS conflict. Phân biệt trạng thái cốt lõi của Order với các thực thể/trạng thái có vòng đời độc lập; chỉ giữ thông tin tóm tắt cần thiết trong Order nếu phù hợp.
5. **Dùng query để tìm một ID đã biết:** thêm chi phí index và nguy cơ độ trễ cập nhật. Chọn KV khi đã có khóa.
6. **Thêm index theo mọi trường JSON:** tăng chi phí ghi nhưng không bảo đảm cải thiện truy vấn. Chỉ thiết kế theo mẫu lọc/sắp xếp và xác nhận bằng `EXPLAIN`.
7. **Giả định tham chiếu ID là khóa ngoại:** Couchbase không tự thực thi foreign-key constraint giữa các document như cơ sở dữ liệu quan hệ. Ứng dụng phải quản lý tính hợp lệ và chiến lược xóa/cập nhật tương ứng.

## 9. Quy trình thực hành và câu hỏi tự kiểm tra

Khi nhận một yêu cầu dữ liệu mới, hãy thực hiện theo thứ tự:

1. Viết **3–5 bất biến** nghiệp vụ và xác định thao tác nào phải nguyên tử.
2. Liệt kê **5–10 mẫu đọc/ghi** thực tế, nêu khóa truy cập, bộ lọc, sắp xếp, số lượng bản ghi, SLA, tần suất và cạnh tranh ghi.
3. Nhóm dữ liệu có cùng vòng đời và quy tắc nhất quán thành các aggregate, đánh dấu root.
4. Chọn **embed/reference/snapshot/read model** cho từng quan hệ, đặt giới hạn tăng trưởng rõ ràng.
5. Định nghĩa document key, collection thích hợp, `@Id`, `@Version`, repository và các đường đi KV/SQL++.
6. Thiết kế index cho truy vấn quan trọng, kiểm tra `EXPLAIN`, đo p95, số lượt đọc, kích thước document và tỷ lệ CAS conflict.
7. Diễn tập các ca sai: hai request cùng thêm dòng, sửa giá Product sau khi mua, hết hàng lúc chốt đơn, read model cập nhật chậm và dữ liệu con tăng đột biến.

**Bài tập:** Một sàn bán hàng có Product (giá hiện hành), Order (tối đa 50 dòng), Review (có thể hàng triệu đánh giá) và Inventory (liên tục được cập nhật). Hãy đề xuất nơi lưu cho danh sách dòng hàng, giá lúc mua, review và số lượng tồn.

**Đáp án tham khảo:** dòng hàng được nhúng trong Order vì cùng vòng đời, kích thước được giới hạn; giá lúc mua lưu snapshot trong OrderLine; Review là document riêng liên kết productId và truy vấn qua index/read model; Inventory là aggregate riêng, phối hợp với Order bằng transaction hoặc reservation tùy yêu cầu nguyên tử. Nếu thực tế có đơn vượt giới hạn hoặc nhiều writer sửa cùng Order, cần đánh giá lại thiết kế dựa trên workload.

## Tài liệu tham khảo chính thức

- [Couchbase — The Couchbase Data Model](https://docs.couchbase.com/server/current/learn/data/document-data-model.html): cách cân nhắc embed và reference theo mẫu đọc/ghi.
- [Couchbase — Key-Value Operations](https://docs.couchbase.com/server/current/guides/kv-operations.html): đọc/ghi document khi biết key.
- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Document`, `@Id`, mapping và CAS.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): KV và query derivation.
- [Spring Data Couchbase — Transactions](https://docs.spring.io/spring-data/couchbase/reference/couchbase/transactions.html): giao dịch đa document trong Spring.
- [Couchbase — CREATE INDEX](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/createindex.html): index phục vụ SQL++.
