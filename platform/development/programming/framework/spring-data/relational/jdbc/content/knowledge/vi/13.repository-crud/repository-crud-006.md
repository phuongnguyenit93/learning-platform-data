# existsById và count trong kiểm tra dữ liệu

Trong **Spring Data Relational JDBC (Spring Data JDBC)**, repository cung cấp các thao tác kiểm tra dữ liệu mà không cần tải toàn bộ entity về ứng dụng. Hai thao tác cơ bản là **`existsById(id)`** để biết một aggregate root có tồn tại theo ID hay không, và **`count()`** để đếm số aggregate root mà repository quản lý.

Các phương thức này hữu ích khi kiểm tra tham chiếu, hiển thị số lượng bản ghi, kiểm tra trạng thái trước một use case hoặc xây dựng báo cáo. Tuy nhiên, cần hiểu đúng phạm vi đếm, chi phí truy vấn và giới hạn của việc “kiểm tra trước rồi mới ghi”.

## 1. Hai câu hỏi khác nhau: có tồn tại không và có bao nhiêu?

Giả sử hệ thống bán hàng có hai bảng:

- `customers`: lưu khách hàng.
- `sales_orders`: lưu đơn hàng, mỗi đơn có `customer_id` tham chiếu tới Customer.

Repository của Order có thể trả lời:

| Nhu cầu | Phương thức | Kết quả |
|---|---|---|
| Đơn hàng ID 501 có tồn tại không? | `existsById(501L)` | `true` hoặc `false` |
| Có bao nhiêu đơn hàng trong hệ thống? | `count()` | Một số nguyên kiểu `long` |
| Khách hàng ID 10 có đơn nào không? | `existsByCustomerId(10L)` | `true` hoặc `false` |
| Khách hàng ID 10 có bao nhiêu đơn? | `countByCustomerId(10L)` | Một số nguyên kiểu `long` |
| Có bao nhiêu đơn ở trạng thái DRAFT? | `countByStatus("DRAFT")` | Một số nguyên kiểu `long` |

**exists** trả lời câu hỏi logic có/không; **count** trả lời số lượng. Nếu chỉ cần biết có dữ liệu phù hợp hay không, không nên tải toàn bộ danh sách rồi gọi `isEmpty()`.

~~~mermaid
flowchart TB
    App["Application Service"]
    App --> Exists["existsById(id)<br/>Có bản ghi không?"]
    App --> Count["count()<br/>Có bao nhiêu bản ghi?"]
    Exists --> Bool["boolean"]
    Count --> Number["long"]
    Exists --> DB[("Database")]
    Count --> DB
~~~

## 2. existsById trong CrudRepository

`CrudRepository<T, ID>` cung cấp sẵn phương thức:

~~~java
boolean existsById(ID id);
~~~

Ví dụ repository:

~~~java
package com.example.sales.order;

import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<Order, Long> {
}
~~~

Sử dụng:

~~~java
boolean exists = orderRepository.existsById(501L);

if (exists) {
    System.out.println("Order exists");
} else {
    System.out.println("Order does not exist");
}
~~~

Hành vi:

- Trả `true` khi repository tìm thấy aggregate root có ID tương ứng.
- Trả `false` khi không có root với ID đó.
- ID truyền vào phải khác null; truyền null không phải cách kiểm tra “ID chưa có”, mà là đầu vào không hợp lệ theo hợp đồng repository.
- Phương thức chỉ trả trạng thái tồn tại; nó không trả entity và không cung cấp các thuộc tính của Order.

### existsById khác findById như thế nào?

~~~java
boolean exists = orderRepository.existsById(orderId);

Order order = orderRepository.findById(orderId)
    .orElseThrow(() -> new IllegalArgumentException("Order not found"));
~~~

| Tiêu chí | `existsById` | `findById` |
|---|---|---|
| Mục đích | Kiểm tra có root theo ID | Lấy root theo ID |
| Kiểu trả về | `boolean` | `Optional<Order>` |
| Dữ liệu ứng dụng nhận | Có/không | Entity nếu tìm thấy |
| Khi nào dùng | Chỉ cần biết sự tồn tại | Cần đọc hoặc thay đổi entity |
| Có cần dựng object aggregate? | Không cần cho caller | Có, theo mapping của aggregate |

Nếu use case tiếp theo chắc chắn cần Order, gọi `findById` một lần thường hợp lý hơn gọi `existsById` rồi lại `findById`, vì hai thao tác sẽ tạo hai lần truy cập database. Ví dụ:

~~~java
Order order = orderRepository.findById(orderId)
    .orElseThrow(() -> new IllegalArgumentException(
        "Order not found: " + orderId
    ));

order.confirm();
orderRepository.save(order);
~~~

Không cần kiểm tra `existsById` trước khi tải Order rồi mới tiếp tục. `findById` đã thể hiện trực tiếp cả hai khả năng.

### Framework thực thi truy vấn như thế nào?

`existsById` có thể được triển khai bằng truy vấn kiểm tra tồn tại hoặc dạng SQL tương đương tùy phiên bản, dialect và hệ quản trị. Ứng dụng nên dựa vào **hợp đồng boolean** thay vì phụ thuộc một câu SQL cụ thể.

Về ý tưởng, câu SQL có thể tương đương:

~~~sql
SELECT 1
FROM sales_orders
WHERE id = :id;
~~~

Một số cách triển khai có thể dùng biểu thức `EXISTS` hoặc cơ chế khác. Không cần tự viết câu SQL trên để dùng `CrudRepository.existsById`; Spring Data JDBC tạo thao tác phù hợp cho repository.

## 3. count trong CrudRepository

`CrudRepository<T, ID>` cũng cung cấp:

~~~java
long count();
~~~

Ví dụ:

~~~java
long totalOrders = orderRepository.count();
System.out.println("Total orders: " + totalOrders);
~~~

Phương thức trả về `long` (64 bit), vì số hàng có thể vượt phạm vi `int`. `count()` đếm số entity root mà repository đại diện; trong ví dụ `OrderRepository`, đó là **số đơn hàng**, không phải tổng số dòng hàng của mọi đơn.

Nếu một aggregate Order gồm một hàng trong `sales_orders` và nhiều hàng trong `order_items`, thì:

- `orderRepository.count()` đếm các Order root.
- Nó không cộng số hàng trong `order_items`.
- Nó cũng không đếm số Customer.

Đây là điểm quan trọng khi phân biệt aggregate với bảng dữ liệu: repository thao tác theo root, còn database có thể lưu aggregate qua nhiều bảng.

### Đếm theo điều kiện với query method

Ngoài `count()`, Spring Data JDBC hỗ trợ query method suy diễn từ tên phương thức. Ví dụ:

~~~java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<Order, Long> {

    boolean existsByCustomerId(Long customerId);

    long countByCustomerId(Long customerId);

    long countByStatus(String status);

    long countByCustomerIdAndStatus(
        Long customerId,
        String status
    );

    List<Order> findAllByCustomerIdOrderByIdAsc(Long customerId);
}
~~~

Các phương thức trả lời:

- `existsByCustomerId(10L)`: khách hàng có ít nhất một Order không?
- `countByCustomerId(10L)`: khách hàng có bao nhiêu Order?
- `countByStatus("DRAFT")`: có bao nhiêu Order đang nháp?
- `countByCustomerIdAndStatus(10L, "DRAFT")`: khách hàng 10 có bao nhiêu Order đang nháp?

Tên thuộc tính trong query method phải khớp với **property của entity**. Ví dụ nếu entity có `customerId`, tên method dùng `CustomerId`; không nhất thiết phải dùng tên cột SQL `customer_id`. Spring Data JDBC ánh xạ property tới cột theo naming strategy hoặc annotation mapping.

Không cần tải danh sách để đếm:

~~~java
// Không tối ưu nếu chỉ cần số lượng:
long count = orderRepository
    .findAllByCustomerIdOrderByIdAsc(customerId)
    .size();

// Nên dùng query đếm:
long count = orderRepository.countByCustomerId(customerId);
~~~

Cách đầu có thể đọc và dựng nhiều Order không cần thiết, làm tăng bộ nhớ và thời gian xử lý. Cách sau để database thực hiện phép đếm và chỉ trả một giá trị.

## 4. SQL tương ứng và phạm vi dữ liệu

Với bảng `sales_orders`:

~~~sql
-- Tổng số đơn hàng.
SELECT COUNT(*)
FROM sales_orders;

-- Số đơn của khách hàng cụ thể.
SELECT COUNT(*)
FROM sales_orders
WHERE customer_id = 10;

-- Số đơn ở trạng thái DRAFT.
SELECT COUNT(*)
FROM sales_orders
WHERE status = 'DRAFT';

-- Số đơn DRAFT của khách hàng cụ thể.
SELECT COUNT(*)
FROM sales_orders
WHERE customer_id = 10
  AND status = 'DRAFT';
~~~

Đây là các câu SQL minh họa ý nghĩa của truy vấn. Khi gọi repository, Spring Data JDBC thực hiện truy vấn và bind tham số; không ghép ID hoặc status do người dùng nhập trực tiếp vào chuỗi SQL.

### Đếm OrderItem là một câu hỏi khác

Nếu muốn đếm số dòng hàng, truy vấn cần nhắm tới bảng `order_items`:

~~~sql
SELECT COUNT(*)
FROM order_items;

-- Số item thuộc một Order.
SELECT COUNT(*)
FROM order_items
WHERE order_id = 501;
~~~

`OrderRepository.count()` không trả về hai kết quả trên. Có thể dùng repository/query chuyên cho báo cáo hoặc `@Query` với kiểu trả về scalar/projection phù hợp để thực hiện phép đếm trên bảng con.

Ví dụ một query method với SQL tường minh:

~~~java
@Query("""
    SELECT COUNT(*)
    FROM order_items
    WHERE order_id = :orderId
    """)
long countItemsByOrderId(long orderId);
~~~

Đặt phương thức trong repository có quyền thực hiện truy vấn đọc này và bảo đảm tên cột đúng với schema. Phép đếm item phục vụ truy vấn đọc không làm cho `OrderItem` trở thành aggregate root hoặc cần một repository ghi độc lập.

## 5. existsBy... và countBy... cho điều kiện nghiệp vụ

Các query method có thể kiểm tra nhiều điều kiện:

~~~java
boolean existsByCustomerIdAndStatus(
    Long customerId,
    String status
);

long countByCustomerIdAndStatus(
    Long customerId,
    String status
);
~~~

Ví dụ kiểm tra khách hàng có đơn DRAFT hay không:

~~~java
boolean hasDraft = orderRepository
    .existsByCustomerIdAndStatus(customerId, "DRAFT");
~~~

Ví dụ kiểm tra số đơn đã xác nhận:

~~~java
long confirmedOrders = orderRepository
    .countByCustomerIdAndStatus(customerId, "CONFIRMED");
~~~

Đây là truy vấn dựa trên dữ liệu hiện tại. Nếu điều kiện nghiệp vụ cần phân biệt khách không tồn tại với khách tồn tại nhưng không có đơn, cần kiểm tra Customer riêng hoặc dùng truy vấn trả về cả trạng thái Customer và kết quả đếm.

Ví dụ:

~~~java
if (!customerRepository.existsById(customerId)) {
    throw new IllegalArgumentException("Customer not found");
}

long orderCount = orderRepository.countByCustomerId(customerId);
~~~

Lưu ý rằng đoạn code này có hai lần truy cập database. Nếu use case cần nhiều thông tin Customer, tải Customer bằng `findById` và dùng chính entity trả về thay vì gọi exists rồi tải lại.

## 6. Hiệu năng: existence và count không có cùng chi phí

### exists thường chỉ cần biết có một kết quả

Về mặt logic, khi đã tìm thấy một hàng thỏa điều kiện, câu hỏi tồn tại đã được trả lời. Hệ quản trị có thể tận dụng khóa chính hoặc index để tìm nhanh. Với `existsById`, cột ID thường là primary key nên có index tương ứng.

Không nên hiểu điều này là mọi truy vấn tồn tại luôn có chi phí hằng số hoặc database chắc chắn dừng sau hàng đầu tiên. Kế hoạch thực thi còn phụ thuộc index, statistics, điều kiện, dữ liệu và database. Hãy kiểm tra bằng công cụ explain/analyze khi có vấn đề hiệu năng thực tế.

### count phải xác định số hàng thỏa điều kiện

`COUNT(*)` cần xác định tổng số hàng thỏa điều kiện. Với bảng lớn, phép đếm chính xác có thể cần đọc nhiều mục dữ liệu hoặc index. Vì vậy:

- Dùng `countBy...` thay cho tải toàn bộ danh sách và gọi `size()`.
- Tạo index phù hợp cho cột thường xuyên dùng trong điều kiện lọc.
- Không gọi count lặp lại trong vòng lặp nếu có thể gom truy vấn.
- Với dashboard yêu cầu số liệu tức thời trên bảng rất lớn, đánh giá truy vấn, cache, bảng tổng hợp hoặc cơ chế cập nhật số liệu phù hợp.

### Index cho các truy vấn phổ biến

Nếu ứng dụng thường lọc đơn theo Customer và trạng thái, có thể cân nhắc:

~~~sql
CREATE INDEX idx_sales_orders_customer_status
    ON sales_orders(customer_id, status);
~~~

Index ghép này có thể hỗ trợ các truy vấn lọc theo `customer_id` và `status`. Nó không tự động làm mọi phép count nhanh; thứ tự cột, độ chọn lọc, số lượng dữ liệu và workload thực tế cần được xem xét. Không tạo index cho mọi tổ hợp điều kiện vì index làm tăng dung lượng và chi phí ghi.

Kiểm tra kế hoạch thực thi bằng:

~~~sql
-- PostgreSQL
EXPLAIN ANALYZE
SELECT COUNT(*)
FROM sales_orders
WHERE customer_id = 10
  AND status = 'DRAFT';
~~~

~~~sql
-- MySQL
EXPLAIN
SELECT COUNT(*)
FROM sales_orders
WHERE customer_id = 10
  AND status = 'DRAFT';
~~~

Chọn lệnh phù hợp hệ quản trị. `EXPLAIN ANALYZE` của PostgreSQL thực thi truy vấn để đo; hãy cân nhắc khi truy vấn có side effect. Các ví dụ ở đây là SELECT chỉ đọc.

## 7. existsById không thay thế ràng buộc database

Một lỗi thường gặp là kiểm tra tồn tại trước rồi tin rằng bản ghi sẽ còn tồn tại khi ghi:

~~~java
if (customerRepository.existsById(customerId)) {
    orderRepository.save(new Order(customerId));
}
~~~

Có thể xảy ra tình huống:

~~~text
Request A                         Request B
existsById(customerId) -> true
                                  DELETE Customer
                                  COMMIT
INSERT Order(customer_id)
-> FK violation
~~~

Khoảng thời gian giữa bước kiểm tra và bước ghi tạo ra **race condition** (TOCTOU: time of check to time of use). Vì vậy:

- Kiểm tra tồn tại trong service giúp trả thông báo nghiệp vụ dễ hiểu.
- Foreign key giúp database bảo đảm tham chiếu thực sự tồn tại tại thời điểm insert/update.
- Transaction, lock hoặc cơ chế phối hợp phù hợp có thể cần nếu nghiệp vụ yêu cầu đồng bộ chặt hơn.
- Luôn xử lý lỗi integrity khi thao tác ghi, vì trạng thái có thể thay đổi đồng thời.

**Không bỏ FK chỉ vì đã có existsById.** Hai lớp có mục tiêu khác nhau: một lớp hỗ trợ logic ứng dụng, một lớp bảo vệ tính toàn vẹn dữ liệu.

## 8. count không phải khóa để giới hạn số lượng trong điều kiện đồng thời

Giả sử mỗi khách hàng chỉ được có tối đa 5 đơn DRAFT. Code:

~~~java
long draftCount = orderRepository
    .countByCustomerIdAndStatus(customerId, "DRAFT");

if (draftCount < 5) {
    orderRepository.save(new Order(customerId));
}
~~~

Cách này có thể sai khi hai request chạy đồng thời:

~~~text
Trạng thái ban đầu: 4 đơn DRAFT

Request A: count = 4       Request B: count = 4
Request A: 4 < 5 -> pass  Request B: 4 < 5 -> pass
Request A: insert          Request B: insert

Kết quả: 6 đơn DRAFT
~~~

`count` phản ánh trạng thái tại thời điểm truy vấn; nó không khóa số lượng tương lai. Nếu giới hạn là quy tắc cứng, cần một thiết kế đồng thời phù hợp, ví dụ:

- Khóa hàng Customer trong transaction trước khi đếm và tạo đơn, với isolation/locking được lựa chọn đúng.
- Lưu bộ đếm/slot trong một hàng được cập nhật nguyên tử bằng câu lệnh có điều kiện.
- Dùng isolation level phù hợp và retry khi phát hiện serialization conflict.
- Thiết kế một cấu trúc dữ liệu có thể biểu diễn ràng buộc bằng unique key/constraint nếu bài toán cho phép.

Chỉ thêm `@Transactional` mà không xét isolation/locking không tự đảm bảo quy tắc “tối đa 5” dưới mọi lịch thực thi đồng thời.

## 9. existsById và kiểm tra quyền truy cập

Biết một Order tồn tại không có nghĩa người dùng hiện tại được phép xem hoặc sửa nó:

~~~java
if (orderRepository.existsById(orderId)) {
    // Không đủ để kết luận người dùng được phép truy cập.
}
~~~

Phân quyền cần kiểm tra quan hệ giữa người dùng hiện tại và chủ thể của tài nguyên, ví dụ Order thuộc Customer nào và Customer đó có liên kết với user hiện tại không. Có thể truy vấn theo cả ID tài nguyên và phạm vi chủ sở hữu:

~~~java
boolean belongsToCustomer = orderRepository
    .existsByIdAndCustomerId(orderId, currentCustomerId);
~~~

Phương thức này vừa kiểm tra tồn tại vừa giới hạn theo customer ID. Tuy vậy, nếu cần cập nhật Order sau đó, hãy tải entity bằng truy vấn có phạm vi thích hợp và thực hiện kiểm tra quyền trong use case; tránh coi một boolean cũ là giấy phép tồn tại mãi.

Ngoài ra, nếu hệ thống dùng **soft delete** (đánh dấu đã xóa nhưng giữ hàng trong bảng), hành vi của `existsById` và `count()` mặc định phụ thuộc cách repository được cấu hình. Các phương thức CRUD cơ bản không tự hiểu cột `deleted_at` hoặc `active` nếu bạn không định nghĩa điều kiện đó. Khi cần chỉ tính bản ghi đang hoạt động, hãy dùng query method có điều kiện hoặc custom query rõ ràng.

## 10. Tổ chức service: chọn đúng thao tác cho từng use case

### Chỉ cần xác nhận ID có tồn tại

~~~java
public boolean orderExists(Long orderId) {
    return orderRepository.existsById(orderId);
}
~~~

### Cần tải để xử lý

~~~java
public Order getOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .orElseThrow(() -> new IllegalArgumentException(
            "Order not found: " + orderId
        ));
}
~~~

### Cần đếm tất cả

~~~java
public long totalOrders() {
    return orderRepository.count();
}
~~~

### Cần đếm theo Customer

~~~java
public long orderCountFor(Long customerId) {
    return orderRepository.countByCustomerId(customerId);
}
~~~

Các phương thức service nên đặt tên theo ý nghĩa nghiệp vụ, chẳng hạn `hasOrders` hoặc `countDraftOrders`, nếu chúng là một phần của API ứng dụng. Không để controller tự ghép nhiều truy vấn và tự quyết định invariant.

## 11. Bài thực hành

Giả sử dữ liệu mẫu:

~~~sql
INSERT INTO customers (id, customer_code, display_name) VALUES
    (10, 'CUS-010', 'Nguyễn An'),
    (20, 'CUS-020', 'Trần Bình');

INSERT INTO sales_orders (id, customer_id, status) VALUES
    (501, 10, 'CONFIRMED'),
    (502, 10, 'DRAFT'),
    (503, 20, 'CONFIRMED');
~~~

Trong môi trường có identity/auto-increment, chỉ chèn ID tường minh nếu schema và cấu hình cho phép; ví dụ trên minh họa giá trị để suy luận kết quả. Có thể bỏ cột ID và để database tự sinh khi thực hành thông thường.

Hãy trả lời:

1. `existsById(501L)` trả về gì? `existsById(999L)` trả về gì?
2. `count()` của OrderRepository trả về bao nhiêu?
3. `existsByCustomerId(10L)` và `countByCustomerId(10L)` trả về gì?
4. `countByStatus("DRAFT")` trả về bao nhiêu?
5. `countByCustomerIdAndStatus(10L, "DRAFT")` trả về bao nhiêu?
6. Vì sao không nên gọi `findAllByCustomerId(10L).size()` chỉ để đếm?
7. Nếu cần đếm tổng item trong tất cả Order, vì sao `OrderRepository.count()` không phù hợp?
8. Vì sao `existsById(customerId)` không đủ để bảo đảm FK luôn hợp lệ khi insert Order?
9. Nếu giới hạn mỗi Customer tối đa 5 đơn DRAFT, vì sao count rồi insert có thể vượt giới hạn khi hai request đồng thời?
10. Nếu dùng soft delete, cần thay đổi truy vấn count/exists thế nào để bỏ qua hàng đã xóa?

Kết quả kỳ vọng:

| Biểu thức | Kết quả |
|---|---:|
| `existsById(501L)` | `true` |
| `existsById(999L)` | `false` |
| `count()` | `3` |
| `existsByCustomerId(10L)` | `true` |
| `countByCustomerId(10L)` | `2` |
| `countByStatus("DRAFT")` | `1` |
| `countByCustomerIdAndStatus(10L, "DRAFT")` | `1` |

## 12. Ghi nhớ

`existsById` là lựa chọn khi chỉ cần biết aggregate root có tồn tại theo ID; `findById` là lựa chọn khi cần entity; `count` đếm số root của repository; `countBy...` và `existsBy...` hỗ trợ kiểm tra theo thuộc tính và điều kiện.

Đừng nhầm số aggregate với số hàng ở bảng con, đừng tải cả danh sách chỉ để đếm, và đừng xem kết quả exists/count là khóa bảo đảm trạng thái không thay đổi sau truy vấn. **Database constraint bảo vệ dữ liệu ở thời điểm ghi; repository query hỗ trợ ứng dụng đưa ra quyết định dựa trên trạng thái quan sát được.** Khi số lượng dữ liệu lớn, cân nhắc index và kế hoạch thực thi thay vì giả định phép đếm luôn rẻ.
