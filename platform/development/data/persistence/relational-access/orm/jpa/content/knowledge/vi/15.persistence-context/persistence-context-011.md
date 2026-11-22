# Kiểm tra trạng thái tải bằng PersistenceUnitUtil và PersistenceUtil trong JPA

Trong **Jakarta Persistence (JPA)**, một entity lấy từ database không nhất thiết đã tải mọi thuộc tính và mọi quan hệ liên quan. JPA có thể trì hoãn việc tải một số trường hoặc collection bằng cơ chế **lazy loading**. Điều đó giúp tránh truy vấn và chuyển dữ liệu không cần thiết, nhưng cũng đặt ra câu hỏi quan trọng:

> Trước khi truy cập một thuộc tính, làm thế nào biết thuộc tính ấy đã được JPA tải hay chưa, mà không vô tình kích hoạt thêm truy vấn?

JPA cung cấp hai API chuẩn để kiểm tra:

- **`PersistenceUnitUtil`**: tiện ích gắn với một `EntityManagerFactory`, tức một **persistence unit** cụ thể.
- **`PersistenceUtil`**: tiện ích lấy qua `Persistence.getPersistenceUtil()`, hữu ích khi code muốn kiểm tra trạng thái tải theo cơ chế chung của các persistence provider đang được nhận diện.

Cả hai đều hỗ trợ `isLoaded(entity)` và `isLoaded(entity, attributeName)`. Khác biệt quan trọng nằm ở **phạm vi sử dụng**, **cách lấy đối tượng tiện ích** và việc `PersistenceUnitUtil` còn cung cấp `getIdentifier(entity)`.

Bài học đặt hai công cụ vào bối cảnh **Persistence Context**: một entity đang managed, một tham chiếu lazy, một collection chưa tải, hay một entity đã detached có thể cho những kết quả kiểm tra khác nhau. Cần hiểu trạng thái tải trước khi thiết kế API, mapper DTO, xử lý transaction hoặc tối ưu vấn đề N+1 queries.

## 1. “Đã tải” không đồng nghĩa “đang được quản lý”

Trước hết cần phân biệt hai câu hỏi độc lập:

1. **Entity có thuộc persistence context hiện hành không?** Đây là vấn đề của trạng thái **managed/detached**, có thể kiểm tra bằng `EntityManager.contains(entity)` trong ngữ cảnh phù hợp.
2. **Các giá trị của entity đã được nạp từ cơ chế persistence chưa?** Đây là vấn đề **load state**, được kiểm tra bằng `PersistenceUnitUtil.isLoaded(...)` hoặc `PersistenceUtil.isLoaded(...)`.

Ví dụ một khách hàng có nhiều đơn hàng:

~~~text
Persistence context
    |
    +-- Customer#42  [managed]
          id = 42
          fullName = "Mai"
          orders = [chưa tải]
                       |
                       | gọi customer.getOrders()
                       v
                     SELECT ... FROM purchase_orders
                     WHERE customer_id = 42
                       |
                       v
          orders = [Order#91, Order#92]
~~~

Ở đây:

- `Customer#42` có thể đã **managed** ngay sau `em.find(Customer.class, 42L)`.
- Trường `fullName` có thể đã tải cùng bản ghi khách hàng.
- Collection `orders` có thể **chưa tải**, dù entity owner đang managed.
- Sau khi tải collection, entity vẫn managed nhưng trạng thái tải của thuộc tính `orders` đã thay đổi.

Vì vậy **`em.contains(customer) == true` không chứng minh `orders` đã tải**; ngược lại, một entity đã detached vẫn có thể giữ những thuộc tính đã được tải trước khi detach.

### 1.1. Tại sao không gọi getter để “kiểm tra”?

Đoạn sau không chỉ kiểm tra:

~~~java
int count = customer.getOrders().size();
~~~

Tùy provider và cách ánh xạ collection, truy cập như vậy có thể khiến ORM thực hiện SQL để lấy dữ liệu. Với nhiều entity, gọi getter trong vòng lặp dễ tạo **N+1 queries**. Khi persistence context đã đóng và collection chưa tải, nó có thể gây lỗi lazy loading tùy provider.

Đối với mục tiêu chỉ xem thuộc tính đã tải hay chưa, nên dùng:

~~~java
boolean loaded =
    util.isLoaded(customer, "orders");
~~~

API kiểm tra load state được thiết kế để **không chủ động nạp thuộc tính đang kiểm tra**.

## 2. Hai interface cần biết

### 2.1. PersistenceUnitUtil

Interface `jakarta.persistence.PersistenceUnitUtil` gắn với một persistence unit:

~~~java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceUnitUtil;

PersistenceUnitUtil unitUtil =
    entityManagerFactory.getPersistenceUnitUtil();
~~~

Những thao tác cốt lõi:

~~~java
boolean entityLoaded = unitUtil.isLoaded(customer);

boolean ordersLoaded =
    unitUtil.isLoaded(customer, "orders");

Object primaryKey = unitUtil.getIdentifier(customer);
~~~

`getIdentifier(...)` là khả năng bổ sung của `PersistenceUnitUtil`. Nó lấy định danh của entity theo metadata ORM trong persistence unit, không cần ứng dụng tự đoán trường `id` hay gọi getter của một entity proxy.

### 2.2. PersistenceUtil

Interface `jakarta.persistence.PersistenceUtil` được lấy qua lớp `Persistence`:

~~~java
import jakarta.persistence.Persistence;
import jakarta.persistence.PersistenceUtil;

PersistenceUtil persistenceUtil =
    Persistence.getPersistenceUtil();
~~~

Sử dụng:

~~~java
boolean entityLoaded =
    persistenceUtil.isLoaded(customer);

boolean ordersLoaded =
    persistenceUtil.isLoaded(customer, "orders");
~~~

`PersistenceUtil` chỉ cung cấp những thao tác kiểm tra trạng thái tải trong phạm vi đang xét; **không có phương thức `getIdentifier(...)`** như `PersistenceUnitUtil`.

### 2.3. Bảng so sánh

| Tiêu chí | `PersistenceUnitUtil` | `PersistenceUtil` |
| --- | --- | --- |
| Namespace Jakarta | `jakarta.persistence.PersistenceUnitUtil` | `jakarta.persistence.PersistenceUtil` |
| Cách lấy | `emf.getPersistenceUnitUtil()` | `Persistence.getPersistenceUtil()` |
| Gắn với một persistence unit xác định | Có | Không gắn với một `EntityManagerFactory` cụ thể |
| Kiểm tra toàn entity | `isLoaded(entity)` | `isLoaded(entity)` |
| Kiểm tra từng attribute | `isLoaded(entity, "attributeName")` | `isLoaded(entity, "attributeName")` |
| Lấy primary key bằng metadata | `getIdentifier(entity)` | Không có |
| Tình huống dùng | Service/repository đã có EMF hoặc biết PU | Thư viện/tầng tiện ích không muốn nhận EMF cụ thể |
| Điểm cần lưu ý | Dùng entity thuộc persistence unit phù hợp | Provider phải nhận diện được đối tượng để diễn giải trạng thái |

Nếu đã có `EntityManagerFactory` tương ứng với entity, `PersistenceUnitUtil` thường là lựa chọn rõ ràng nhất vì thể hiện phạm vi persistence unit một cách tường minh.

## 3. Ví dụ mô hình: Customer và PurchaseOrder

Bài học dùng Java 17+ và namespace **Jakarta Persistence**. Với dự án JPA 2.x cũ, tên package tương ứng bắt đầu bằng `javax.persistence`; nguyên tắc phân biệt hai tiện ích vẫn tương tự, nhưng phải dùng dependency phù hợp phiên bản dự án.

### 3.1. Entity Customer

~~~java
package com.example.shop.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @OneToMany(
        mappedBy = "customer",
        cascade = CascadeType.PERSIST
    )
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
    }

    public Customer(String fullName) {
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public List<PurchaseOrder> getOrders() {
        return orders;
    }

    public void addOrder(PurchaseOrder order) {
        orders.add(order);
        order.attachCustomer(this);
    }
}
~~~

### 3.2. Entity PurchaseOrder

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(
        fetch = FetchType.LAZY,
        optional = false
    )
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(name = "order_number", nullable = false, length = 60)
    private String orderNumber;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    void attachCustomer(Customer customer) {
        this.customer = customer;
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public String getOrderNumber() {
        return orderNumber;
    }
}
~~~

Có hai hướng lazy đáng chú ý:

- `Customer.orders` là collection `@OneToMany`. Nếu không chỉ định fetch, mặc định của `@OneToMany` là **LAZY**.
- `PurchaseOrder.customer` là `@ManyToOne(fetch = FetchType.LAZY)`. Mặc định của `@ManyToOne` là **EAGER**, nên ở đây cần ghi rõ LAZY khi muốn trì hoãn tải quan hệ.

Ví dụ schema:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(60) NOT NULL,
    CONSTRAINT fk_purchase_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~

Các bảng và class chỉ tạo ngữ cảnh để kiểm tra load state; `isLoaded` không kiểm tra trực tiếp tên cột SQL.

## 4. Dùng PersistenceUnitUtil kiểm tra một attribute

Ví dụ ứng dụng quản lý `EntityManagerFactory emf` và `EntityManager em`:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceUnitUtil;

PersistenceUnitUtil util =
    emf.getPersistenceUnitUtil();

EntityManager em = emf.createEntityManager();
try {
    Customer customer = em.find(Customer.class, 42L);

    if (customer != null) {
        boolean nameLoaded =
            util.isLoaded(customer, "fullName");

        boolean ordersLoaded =
            util.isLoaded(customer, "orders");

        System.out.println("fullName loaded: " + nameLoaded);
        System.out.println("orders loaded: " + ordersLoaded);
    }
} finally {
    em.close();
}
~~~

`isLoaded(customer, "orders")` kiểm tra **thuộc tính collection** mà không cần gọi `customer.getOrders()` để đọc phần tử.

### 4.1. Tên attribute là tên thuộc tính Java

Trong model trên:

~~~java
util.isLoaded(customer, "orders");
util.isLoaded(customer, "fullName");
~~~

là các cách gọi dựa trên **tên attribute JPA trong entity**.

Không dùng tên bảng hoặc tên cột:

~~~java
// Không phải tên attribute của Customer:
util.isLoaded(customer, "purchase_orders");
util.isLoaded(customer, "full_name");
~~~

`@Table(name = "customers")` và `@Column(name = "full_name")` mô tả dữ liệu vật lý; load-state API dùng **mô hình đối tượng đã ánh xạ**.

Nếu dùng `@Access(AccessType.PROPERTY)`, attribute name là tên property JPA suy ra theo metadata truy cập, không phải một tên tùy ý do database đặt. Với ví dụ dùng field access, thuộc tính `fullName` và `orders` có tên trùng với field Java.

### 4.2. Kết quả true và false có ý nghĩa gì?

~~~java
boolean ordersLoaded =
    util.isLoaded(customer, "orders");
~~~

- `true`: provider xác định thuộc tính `orders` ở trạng thái đã tải theo hợp đồng load-state.
- `false`: thuộc tính chưa được xác định là đã tải; với lazy collection thông thường, điều này thường có nghĩa collection chưa được khởi tạo.
- Kết quả **không phải số lần SQL đã chạy**.
- Kết quả **không nói collection có bao nhiêu phần tử** hoặc có rỗng không.

Ví dụ, `ordersLoaded == true` vẫn có thể tương ứng với `customer.getOrders().isEmpty() == true`. Một collection đã tải nhưng không có bản ghi là điều hoàn toàn bình thường.

### 4.3. Không dùng tên đường dẫn tùy ý như JPQL

JPQL có thể dùng đường dẫn:

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.customer.fullName = :name
~~~

Nhưng `isLoaded(entity, attributeName)` nhận **một tên thuộc tính ánh xạ của entity được truyền vào**, không phải ngôn ngữ path expression tổng quát như JPQL.

Vì vậy không mặc định chuỗi sau sẽ được hiểu theo chuẩn:

~~~java
util.isLoaded(order, "customer.fullName");
~~~

Thay vào đó, kiểm tra theo từng đối tượng:

~~~java
if (util.isLoaded(order, "customer")) {
    Customer owner = order.getCustomer();

    if (owner != null) {
        boolean nameLoaded =
            util.isLoaded(owner, "fullName");
    }
}
~~~

Cách kiểm tra này tránh tự truy cập association `customer` khi nó chưa được tải. Với giá trị null hoặc mô hình proxy, vẫn cần xử lý theo hành vi provider phù hợp.

## 5. isLoaded(entity) khác isLoaded(entity, attributeName)

Đây là điểm dễ gây hiểu nhầm nhất.

### 5.1. isLoaded(entity)

~~~java
boolean loaded = util.isLoaded(customer);
~~~

Theo hợp đồng tải entity của JPA, việc đánh giá trạng thái **toàn entity** chủ yếu liên quan tới những thuộc tính phải được tải theo **FetchType.EAGER**. Vì vậy, một entity có thể được xem là **loaded** ngay cả khi một hoặc nhiều thuộc tính LAZY vẫn chưa được khởi tạo.

Ví dụ thường gặp:

~~~text
Customer#42
  id       : loaded
  fullName : loaded
  orders   : not loaded (LAZY)

isLoaded(customer)           -> có thể là true
isLoaded(customer, "orders") -> false
~~~

Không nên viết:

~~~java
if (util.isLoaded(customer)) {
    // SAI SUY LUẬN: mọi LAZY relation đều an toàn để duyệt.
    for (PurchaseOrder order : customer.getOrders()) {
        // ...
    }
}
~~~

`isLoaded(customer)` **không phải lời cam kết mọi quan hệ LAZY đã tải**. Nếu nghiệp vụ cần bảo đảm một collection cụ thể có sẵn, hãy hỏi trực tiếp **`isLoaded(customer, "orders")`**.

### 5.2. isLoaded(entity, attributeName)

~~~java
boolean ordersLoaded =
    util.isLoaded(customer, "orders");
~~~

Đây là lựa chọn cụ thể hơn khi muốn biết **một attribute đã tải hay chưa**.

| Câu hỏi | API nên dùng |
| --- | --- |
| Provider xem entity là đã tải theo quy tắc load state tổng thể chưa? | `isLoaded(entity)` |
| Collection `orders` có đang ở trạng thái loaded không? | `isLoaded(customer, "orders")` |
| Thuộc tính `fullName` đã tải không? | `isLoaded(customer, "fullName")` |
| ID của entity đang được JPA nhận diện là gì? | `PersistenceUnitUtil.getIdentifier(entity)` |
| Entity có đang managed trong `em` cụ thể không? | `em.contains(entity)` |
| Có bao nhiêu SQL SELECT được thực thi? | SQL logging, metrics hoặc thống kê provider |

**Không dùng `isLoaded(entity)` thay cho từng phép kiểm tra thuộc tính LAZY.** Hai overload có mục đích khác nhau.

### 5.3. True không đồng nghĩa “không có khả năng phát sinh SQL nữa”

Ngay cả khi `isLoaded(customer, "orders") == true`, việc duyệt từng `PurchaseOrder` rồi truy cập `order.getCustomer()` hoặc các quan hệ khác chưa tải vẫn có thể kích hoạt SQL.

Một collection đã loaded chỉ xác nhận trạng thái của **collection đó**. Nó không chứng minh **toàn bộ object graph lồng nhau** đều loaded:

~~~text
Customer.orders          : loaded
  |
  +-- Order#91           : entity đang truy cập được
        |
        +-- orderItems   : có thể vẫn LAZY
              |
              +-- product: có thể vẫn LAZY
~~~

Cần xác định **đường truy cập dữ liệu** của chức năng cụ thể, rồi đánh giá từng quan hệ cần dùng.

## 6. Dùng PersistenceUtil khi không có EntityManagerFactory cụ thể

Một lớp tiện ích độc lập có thể sử dụng `Persistence.getPersistenceUtil()`:

~~~java
package com.example.shop.util;

import jakarta.persistence.Persistence;
import jakarta.persistence.PersistenceUtil;

public final class LoadState {

    private LoadState() {
    }

    private static final PersistenceUtil UTIL =
        Persistence.getPersistenceUtil();

    public static boolean isAttributeLoaded(
            Object entity,
            String attributeName) {
        return UTIL.isLoaded(entity, attributeName);
    }

    public static boolean isEntityLoaded(Object entity) {
        return UTIL.isLoaded(entity);
    }
}
~~~

Sử dụng:

~~~java
boolean loaded =
    LoadState.isAttributeLoaded(customer, "orders");
~~~

Cách này phù hợp khi một module xử lý đối tượng persistence nhưng không trực tiếp nhận `EntityManagerFactory`, chẳng hạn một thành phần hỗ trợ ánh xạ hoặc một thư viện dùng chung.

Tuy nhiên, `PersistenceUtil` cần có khả năng xác định provider quản lý entity trong môi trường đang chạy. Với ứng dụng nhiều provider hoặc nhiều persistence unit, hành vi nhận diện có thể phụ thuộc cách provider đăng ký và cách entity được tạo. **Không xem `PersistenceUtil` là cơ chế phát hiện tùy ý các object Java**, kể cả những object không hề được JPA quản lý.

### 6.1. Hai tiện ích không tạo ra cùng một loại object

~~~java
PersistenceUnitUtil unitUtil =
    emf.getPersistenceUnitUtil();

PersistenceUtil generalUtil =
    Persistence.getPersistenceUtil();
~~~

Hai biến trên đều kiểm tra trạng thái tải, nhưng:

- `unitUtil` mang ngữ cảnh persistence unit cụ thể.
- `generalUtil` sử dụng cơ chế tiện ích persistence tổng quát.
- `unitUtil` có `getIdentifier(...)`.
- `generalUtil` không phải đối tượng `EntityManager`, không có `find`, `persist`, `flush` hoặc `clear`.

Không có phương thức “load toàn bộ entity” được chuẩn hóa chỉ bằng việc gọi `isLoaded`. Đây là **API quan sát trạng thái**, không phải API yêu cầu eager fetch.

## 7. Lấy ID bằng PersistenceUnitUtil.getIdentifier

Khi một mapper hoặc service cần biết khóa chính của entity, `PersistenceUnitUtil` có tiện ích:

~~~java
PersistenceUnitUtil util =
    emf.getPersistenceUnitUtil();

Object identifier = util.getIdentifier(customer);

if (identifier instanceof Long customerId) {
    System.out.println("Customer ID = " + customerId);
}
~~~

Khi loại entity đã biết:

~~~java
Long customerId =
    (Long) util.getIdentifier(customer);
~~~

Lưu ý:

- Kiểu trả về là `Object` vì ID có thể là `Long`, `UUID`, `String` hoặc một **composite key object** tùy entity.
- Với entity mới chưa được cấp ID, kết quả có thể chưa có giá trị; không giả định mọi object vừa `new` đã có khóa.
- Với ID ghép, giá trị có thể là instance của lớp khóa đã ánh xạ.
- Không dùng `getIdentifier(...)` như một “dịch vụ cấp ID mới”. Nó **đọc định danh của entity**, không sinh khóa.

### 7.1. ID và lazy reference

Giả sử có một khóa `orderId` và ứng dụng lấy tham chiếu:

~~~java
PurchaseOrder orderRef =
    em.getReference(PurchaseOrder.class, orderId);
~~~

Một provider có thể trả về proxy/reference mà chưa phải tải mọi dữ liệu của `PurchaseOrder`. Việc lấy ID qua metadata persistence unit có thể hữu ích khi chỉ cần khóa:

~~~java
Object id = util.getIdentifier(orderRef);
~~~

Đừng chỉ vì muốn ID mà gọi nhiều getter khác khiến proxy bị khởi tạo không cần thiết. Trạng thái của reference cần được đánh giá riêng với `isLoaded(orderRef)` hoặc `isLoaded(orderRef, "orderNumber")`.

**`getReference()` không cam kết object đã được nạp đầy đủ.** Thời điểm provider phải xác thực sự tồn tại của bản ghi hoặc phát sinh exception có thể khác nhau tùy cách sử dụng reference và provider. Chỉ dùng reference khi hiểu điều kiện transaction và tính hợp lệ của ID.

## 8. Kiểm tra trạng thái tải không kích hoạt lazy load

Một pattern thường dùng:

~~~java
PersistenceUnitUtil util =
    emf.getPersistenceUnitUtil();

Customer customer = em.find(Customer.class, customerId);

if (customer == null) {
    return;
}

if (util.isLoaded(customer, "orders")) {
    // Chỉ xử lý dữ liệu đã được tải theo mục tiêu của đoạn code.
    for (PurchaseOrder order : customer.getOrders()) {
        System.out.println(order.getOrderNumber());
    }
} else {
    System.out.println("orders chưa được tải");
}
~~~

Điểm chính: lời gọi `isLoaded(customer, "orders")` không nhằm gây SQL `SELECT purchase_orders ...`.

Nhưng cần phân biệt **không cố ý tải thêm** với **đảm bảo dữ liệu nghiệp vụ**. Nếu hàm bắt buộc phải trả danh sách đơn hàng, việc “bỏ qua vì chưa loaded” có thể khiến response bị thiếu dữ liệu. Khi cần dữ liệu, hãy **truy vấn đúng cách**, không lạm dụng isLoaded để quyết định tùy tiện bỏ qua trường.

### 8.1. Vì sao không dùng getter rồi bắt exception?

Đoạn như sau là pattern không phù hợp để kiểm tra trạng thái:

~~~java
try {
    customer.getOrders().size();
    // Đoán rằng dữ liệu đã tải.
} catch (RuntimeException ex) {
    // Đoán rằng dữ liệu chưa tải.
}
~~~

Vấn đề:

1. Getter có thể kích hoạt truy vấn không mong muốn.
2. Exception có thể do SQL, quyền truy cập, session, mapping hoặc nguyên nhân khác.
3. Lỗi bị bắt quá rộng làm che giấu sự cố thật.
4. Đọc dữ liệu và kiểm tra trạng thái bị trộn thành một hành động không rõ trách nhiệm.

Nếu chỉ cần câu trả lời boolean, dùng `isLoaded`. Nếu thật sự cần dữ liệu, thực hiện fetch có chủ đích trong transaction phù hợp.

## 9. Entity managed, detached và persistence context đã đóng

### 9.1. Managed với thuộc tính LAZY chưa tải

~~~java
Customer customer = em.find(Customer.class, customerId);

boolean managed = em.contains(customer);
boolean ordersLoaded = util.isLoaded(customer, "orders");
~~~

Một kết quả có thể xảy ra là:

~~~text
managed      = true
ordersLoaded = false
~~~

Không có mâu thuẫn: entity được quản lý, nhưng collection được phép tải trễ.

### 9.2. Sau khi tải collection

~~~java
customer.getOrders().size();

boolean ordersLoadedAfter =
    util.isLoaded(customer, "orders");
~~~

Trong cách dùng collection lazy thông thường, thao tác truy cập trên có thể tải collection và trạng thái sau đó được nhận diện là loaded. Tuy nhiên một số provider có tối ưu hóa như **extra-lazy** hoặc xử lý truy vấn đếm riêng, nên không dùng `size()` như công cụ chuẩn bắt buộc tải **toàn bộ phần tử** trong mọi cấu hình.

Để yêu cầu collection được tải phục vụ nghiệp vụ, nên dùng fetch plan hoặc truy vấn tường minh thay vì dựa vào một thao tác phụ như `size()`.

### 9.3. Sau khi detach/clear

~~~java
Customer customer = em.find(Customer.class, customerId);

boolean before =
    util.isLoaded(customer, "orders");

em.detach(customer);

boolean managedAfter =
    em.contains(customer); // false

boolean loadedAfter =
    util.isLoaded(customer, "orders");
~~~

Detaching khiến entity không còn được context hiện tại theo dõi. **Detach không tự xóa các giá trị đã được tải khỏi object**. Nếu collection đã loaded trước detach, dữ liệu thường vẫn có thể được sử dụng trong object đã detached.

Nếu collection chưa tải và provider cần context/session để khởi tạo nó, gọi getter sau detach có thể thất bại. Với Hibernate, lỗi điển hình là `LazyInitializationException`. Lỗi đó thuộc provider, không phải tên exception chuẩn của mọi JPA implementation.

`isLoaded` hữu ích để kiểm tra tình huống này, nhưng **đừng xem nó là giải pháp cho một API được thiết kế cần dữ liệu bắt buộc**. Trong trường hợp đó, tải dữ liệu trước khi detach hoặc dùng DTO projection phù hợp.

### 9.4. Sau khi EntityManager đóng

~~~java
Customer detachedCustomer;

EntityManager em = emf.createEntityManager();
try {
    detachedCustomer = em.find(Customer.class, customerId);
} finally {
    em.close();
}

boolean loaded =
    util.isLoaded(detachedCustomer, "orders");
~~~

Đối với entity đã lấy ra từ persistence unit phù hợp, việc đọc thông tin trạng thái tải là một nhu cầu hợp lệ. Nhưng lúc này nếu `orders` chưa loaded thì không nên truy cập nó theo cách buộc provider phải phát sinh SQL từ một context đã đóng.

Bảng đối chiếu:

| Trạng thái | `em.contains(entity)` | `isLoaded(entity, "orders")` |
| --- | --- | --- |
| Managed, orders chưa tải | `true` | Có thể `false` |
| Managed, orders đã tải | `true` | `true` nếu provider nhận diện đã tải |
| Detached, orders đã tải trước đó | `false` trong EM cũ/phù hợp | Có thể vẫn `true` |
| Detached, orders chưa tải | `false` | Có thể vẫn `false` |
| Object DTO không phải entity | Không phải đối tượng dùng để đánh giá managed entity | Không dùng như một entity JPA |

Hai cột trong bảng mô tả **hai trục trạng thái khác nhau**; không suy diễn kết quả của cột này từ cột kia.

## 10. FetchType.EAGER và LAZY tác động thế nào?

Các association có giá trị fetch mặc định theo JPA:

| Loại ánh xạ | Mặc định fetch trong JPA | Nhận xét |
| --- | --- | --- |
| `@ManyToOne` | EAGER | Cần ghi `fetch = LAZY` nếu muốn yêu cầu tải trễ |
| `@OneToOne` | EAGER | LAZY ở một số chiều có thể phụ thuộc enhancement/provider |
| `@OneToMany` | LAZY | Thường là collection chưa tải ngay sau khi đọc owner |
| `@ManyToMany` | LAZY | Cần chú ý N+1 khi duyệt nhiều owner |
| `@ElementCollection` | LAZY | Dùng cho basic/embeddable collection |
| `@Basic` | EAGER | Có thể chỉ định LAZY theo khả năng hỗ trợ của provider |

Trong JPA, **EAGER** là yêu cầu provider phải bảo đảm dữ liệu được tải theo fetch semantics; không có nghĩa nhất thiết phải dùng **một câu SQL JOIN duy nhất**. Provider có thể thực hiện nhiều câu SQL để đáp ứng eager fetch.

Ngược lại, **LAZY là một gợi ý (hint)** để provider có thể trì hoãn tải. Tùy provider, phiên bản, enhancement và cấu hình, một thuộc tính khai báo LAZY vẫn có thể được tải sớm.

Vì vậy không nên kết luận tuyệt đối:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

// KẾT LUẬN SAI:
// isLoaded(order, "customer") chắc chắn là false.
~~~

Kết quả thực tế còn phụ thuộc provider đã materialize thuộc tính như thế nào.

### 10.1. @Basic(fetch = LAZY) và các trường lớn

Ví dụ:

~~~java
@Lob
@Basic(fetch = FetchType.LAZY)
@Column(name = "document_body")
private String documentBody;
~~~

Một số provider cần **bytecode enhancement** để thực sự trì hoãn việc nạp basic attribute này. Không nên chỉ nhìn annotation mà khẳng định `documentBody` chưa loaded.

Dùng:

~~~java
boolean bodyLoaded =
    util.isLoaded(document, "documentBody");
~~~

và kiểm tra SQL/behavior của provider khi cần đánh giá tối ưu tải. Kể cả khi một attribute dùng LAZY, `isLoaded(entity)` vẫn không phải công cụ thay cho `isLoaded(entity, "documentBody")` nếu muốn biết trạng thái của chính attribute đó.

## 11. Lazy proxy và trạng thái tải của reference

Một quan hệ many-to-one LAZY có thể được biểu diễn bởi proxy hoặc cơ chế enhancement:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

boolean customerLoaded =
    util.isLoaded(order, "customer");
~~~

Một tình huống có thể gặp:

~~~text
PurchaseOrder#91 loaded
  |
  +-- customer -> Customer reference
                       |
                       +-- id có thể đã biết
                       +-- fullName chưa tải
~~~

Cần phân biệt **liên kết đã được gắn reference** với **dữ liệu của entity đích đã được nạp**. Provider có thể biểu diễn association thông qua proxy mà chưa cần SELECT toàn bộ customer.

Một số tình huống thực tế:

- Provider đã tải target trong cùng persistence context: kiểm tra có thể trả loaded.
- Provider chỉ tạo proxy: target có thể chưa được khởi tạo.
- FK null trong association tùy chọn: không có target để tải.
- Fetch join hoặc entity graph đã nạp target: trạng thái loaded có thể khác.

Không nên viết logic dựa trên việc kiểm tra concrete Java class của một proxy bằng `getClass()` rồi suy ra trạng thái tải. Dùng API JPA chuẩn giúp giảm phụ thuộc vào cơ chế proxy riêng của ORM.

## 12. Chủ động tải dữ liệu thay vì chỉ hỏi trạng thái

`isLoaded` không phải thao tác gọi SQL để tải; nếu một chức năng **cần** orders, có thể yêu cầu fetch ngay trong truy vấn.

### 12.1. JPQL JOIN FETCH

~~~java
List<Customer> result = em.createQuery(
    """
    SELECT DISTINCT c
    FROM Customer c
    LEFT JOIN FETCH c.orders
    WHERE c.id = :id
    """,
    Customer.class
)
.setParameter("id", customerId)
.getResultList();

Customer customer =
    result.isEmpty() ? null : result.get(0);
~~~

`LEFT JOIN FETCH` yêu cầu truy vấn đồng thời lấy collection `orders` cho customer được chọn. Dùng LEFT JOIN để customer không có đơn hàng vẫn xuất hiện. `DISTINCT` trong JPQL diễn đạt mong muốn không trả bản sao parent entity ở kết quả logic khi join collection có nhiều dòng; SQL/provider có thể xử lý deduplication theo cách khác nhau.

Sau truy vấn, kiểm tra trạng thái:

~~~java
if (customer != null) {
    boolean ordersLoaded =
        util.isLoaded(customer, "orders");
}
~~~

Đây là cách sử dụng `isLoaded` để **quan sát kết quả của một fetch plan đã chọn**, không phải dựa vào `isLoaded` để tự thực hiện fetch.

**Lưu ý phân trang:** fetch join collection một-nhiều có thể làm số dòng SQL tăng theo số phần tử và không phù hợp với cách phân trang offset thông thường trên parent. Với danh sách lớn, nên cân nhắc query hai bước, batch fetching hoặc projection riêng.

### 12.2. EntityGraph

JPA cho phép khai báo các attribute cần tải qua entity graph:

~~~java
import jakarta.persistence.EntityGraph;
import java.util.Map;

EntityGraph<Customer> graph =
    em.createEntityGraph(Customer.class);

graph.addAttributeNodes("orders");

Customer customer = em.find(
    Customer.class,
    customerId,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
~~~

Ý nghĩa:

1. Graph khai báo `orders` là thuộc tính cần được tải.
2. `find` sử dụng graph để điều chỉnh fetch plan.
3. Sau thao tác, kiểm tra `isLoaded(customer, "orders")` có thể giúp quan sát trạng thái đã tải.
4. Cách provider phát sinh SQL (JOIN hay SELECT bổ sung) không được quyết định chỉ bởi cách viết graph.

Với dự án JPA 2.x sử dụng namespace `javax.persistence`, tên hint tương ứng là `"javax.persistence.fetchgraph"`. Không trộn namespace/hint giữa hai thế hệ API một cách tùy tiện.

### 12.3. DTO projection

Nếu API chỉ cần mã đơn hàng và tên khách hàng, không nhất thiết phải materialize một object graph rồi kiểm tra lazy state:

~~~java
public record OrderSummary(
    Long orderId,
    String orderNumber,
    String customerName
) {
}
~~~

~~~java
List<OrderSummary> summaries = em.createQuery(
    """
    SELECT new com.example.shop.dto.OrderSummary(
        o.id,
        o.orderNumber,
        c.fullName
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    ORDER BY o.id
    """,
    OrderSummary.class
).getResultList();
~~~

`OrderSummary` là DTO, không phải managed JPA entity. Nó mang giá trị đã chọn trong truy vấn. **Không sử dụng `isLoaded(summary, "customerName")` như thể record là entity có lazy attribute**.

Nếu một response bắt buộc có những trường cụ thể, projection thường tạo hợp đồng dữ liệu rõ hơn việc kiểm tra từng association rồi quyết định có trả field hay không.

## 13. isLoaded không phải công cụ đo số lượng truy vấn

Hai trạng thái có thể giống nhau nhưng số SQL khác nhau:

~~~text
Lần chạy A: lấy Customer rồi lazy-load orders bằng SELECT riêng.
Lần chạy B: JOIN FETCH Customer cùng orders trong SELECT chính.

Cuối cả hai:
isLoaded(customer, "orders") == true
~~~

`isLoaded` trả lời **trạng thái hiện tại**. Nó không trả lời:

- Có bao nhiêu `SELECT` đã chạy?
- Đã lấy dữ liệu từ database hay second-level cache?
- Có xảy ra N+1 queries trước khi kiểm tra?
- Một fetch join có được provider tối ưu thành nhiều SQL không?
- Bao nhiêu hàng được đọc từ bảng và bao nhiêu byte được truyền qua mạng?

Để đánh giá những câu hỏi này, dùng **SQL logging**, số liệu thống kê của provider hoặc công cụ quan sát database. Ví dụ Hibernate có các API thống kê riêng; chúng hữu ích cho đo hiệu năng nhưng không phải một phần của `PersistenceUtil` chuẩn.

### 13.1. N+1 khi lặp qua nhiều customer

Ví dụ:

~~~java
List<Customer> customers =
    em.createQuery(
        "SELECT c FROM Customer c",
        Customer.class
    ).getResultList();

for (Customer c : customers) {
    System.out.println(c.getOrders().size());
}
~~~

Trong một cách fetch lazy thường gặp, provider có thể chạy một query lấy customers, sau đó một query lấy orders cho mỗi customer: **1 + N queries**.

Thêm:

~~~java
for (Customer c : customers) {
    System.out.println(
        util.isLoaded(c, "orders")
    );
}
~~~

chỉ giúp quan sát collection nào đang loaded, không tự xử lý N+1. Để tối ưu, cần thiết kế fetch plan hoặc truy vấn phù hợp với dữ liệu và yêu cầu phân trang.

**Tránh giải pháp “chỉ truy cập collection nếu đã loaded”** nếu hợp đồng nghiệp vụ bắt buộc có dữ liệu đơn hàng: đó là bỏ qua dữ liệu chứ không giải quyết truy vấn.

## 14. Sử dụng trong service, mapper và serializer

### 14.1. Kiểm tra để tránh vô tình chạm vào lazy association

Giả sử có một mapper tùy chọn, chỉ bổ sung danh sách order number nếu collection đã có sẵn trong phạm vi sử dụng:

~~~java
public record CustomerPreview(
    Long id,
    String fullName,
    java.util.List<String> orderNumbers
) {
}
~~~

~~~java
public CustomerPreview toPreview(
        Customer customer,
        PersistenceUnitUtil util) {

    java.util.List<String> numbers = null;

    if (util.isLoaded(customer, "orders")) {
        numbers = customer.getOrders().stream()
            .map(PurchaseOrder::getOrderNumber)
            .toList();
    }

    return new CustomerPreview(
        customer.getId(),
        customer.getFullName(),
        numbers
    );
}
~~~

Đoạn này minh họa **mapper tùy chọn** có hợp đồng rõ: `orderNumbers == null` nghĩa là không đưa dữ liệu vào preview vì collection chưa loaded. Nếu API cần phân biệt ba trạng thái “không lấy”, “đã lấy nhưng rỗng”, “đã lấy và có giá trị”, phải thiết kế kiểu response phản ánh rõ ba trạng thái đó.

**Không sử dụng pattern này để vô tình giấu dữ liệu bắt buộc**. Nếu caller cần đầy đủ order numbers, service phải fetch chúng chủ động và truyền vào mapper với điều kiện xác định.

### 14.2. Tránh serialize entity trực tiếp ra JSON

Khi API trả thẳng entity `Customer`, serializer có thể lần theo `getOrders()`:

~~~text
HTTP controller
    |
    +-- return Customer entity
            |
            +-- JSON serializer gọi getOrders()
                    |
                    +-- SQL lazy load bất ngờ
                        hoặc lỗi nếu context đóng
~~~

`isLoaded` có thể phục vụ một số serializer tích hợp JPA để tránh truy cập thuộc tính chưa nạp. Nhưng việc dùng load state làm tiêu chí loại field có thể khiến hình dạng JSON phụ thuộc vào fetch plan vô tình của request.

Một chiến lược thường rõ ràng hơn là:

1. Xác định DTO response cho từng API.
2. Truy vấn đủ những trường cần công khai.
3. Map từ dữ liệu đã tải trong transaction thích hợp.
4. Không để serializer tự duyệt mọi association của entity.

### 14.3. Dùng trong Jakarta EE

Khi container quản lý EntityManager:

~~~java
import jakarta.ejb.Stateless;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceUnit;
import jakarta.persistence.PersistenceUnitUtil;

@Stateless
public class CustomerReader {

    @PersistenceContext(unitName = "shopPU")
    private EntityManager em;

    @PersistenceUnit(unitName = "shopPU")
    private EntityManagerFactory emf;

    public boolean areOrdersLoaded(Long id) {
        Customer customer = em.find(Customer.class, id);
        if (customer == null) {
            return false;
        }

        PersistenceUnitUtil util =
            emf.getPersistenceUnitUtil();

        return util.isLoaded(customer, "orders");
    }
}
~~~

Ví dụ trả về boolean chỉ để minh họa API; trong business service thực tế, `false` do **không tìm thấy customer** nên được phân biệt với `false` do **collection chưa loaded**. Có thể trả về một DTO trạng thái, `Optional` hoặc exception domain phù hợp, thay vì gộp hai nguyên nhân nếu caller cần biết rõ.

Trong Jakarta EE container-managed transaction, không gọi `em.getTransaction().begin()` như với RESOURCE_LOCAL. Framework/container quản lý ranh giới giao dịch phù hợp.

## 15. Multiple persistence units và lựa chọn tiện ích phù hợp

Ứng dụng có thể có nhiều persistence unit, ví dụ:

~~~text
shopPU         -> customers, purchase_orders
reportingPU    -> reporting_snapshots, audit_records
~~~

Khi đã biết entity thuộc `shopPU`:

~~~java
PersistenceUnitUtil shopUtil =
    shopEntityManagerFactory.getPersistenceUnitUtil();
~~~

là cách gắn câu hỏi về entity vào đúng ngữ cảnh metadata.

Nếu một code tiện ích chỉ nhận `Object entity` mà không biết entity đến từ PU nào, `Persistence.getPersistenceUtil()` có thể cung cấp cơ chế kiểm tra tổng quát. Tuy nhiên không nên dùng nó để suy ra mọi object đang thuộc PU nào, đang tồn tại trong DB nào hay có quyền truy cập hay không.

### 15.1. POJO và DTO không phải đối tượng kiểm tra hợp lệ

Một đối tượng thông thường:

~~~java
public record CustomerCard(
    Long id,
    String fullName
) {
}
~~~

không có JPA identity hay lazy association. Vì vậy:

~~~java
CustomerCard card =
    new CustomerCard(42L, "Mai");

// Không xem đây là phép kiểm tra lazy state của entity:
persistenceUtil.isLoaded(card);
~~~

không có giá trị ứng dụng như kiểm tra một managed JPA entity. Tùy API và provider, đối tượng không phải entity hoặc thuộc tính không tồn tại có thể dẫn tới hành vi xác định riêng, thậm chí exception. Hãy giới hạn `isLoaded` vào các đối tượng thuộc mô hình JPA được hỗ trợ.

### 15.2. Attribute name không hợp lệ

Không nên viết:

~~~java
util.isLoaded(customer, "orders[0]");
util.isLoaded(customer, "orders.customer");
util.isLoaded(customer, "customer_id");
~~~

Ba chuỗi này không phải những attribute name đúng của `Customer` trong ví dụ. `isLoaded` không phải expression evaluator, không đọc chỉ số collection và không diễn giải tên khóa ngoại.

Nếu tên attribute nhận từ input ngoài, nên đối chiếu nó với metadata hoặc danh sách được phép của application thay vì truyền chuỗi tùy ý.

## 16. Một số bẫy về độ chính xác của kết quả

### 16.1. Entity loaded nhưng một lazy collection chưa loaded

~~~java
util.isLoaded(customer)            // Có thể true
util.isLoaded(customer, "orders")   // Có thể false
~~~

Đây không phải lỗi. `isLoaded(entity)` có ngữ nghĩa khác `isLoaded(entity, attributeName)`; đừng coi hai phép kiểm tra là thay thế hoàn toàn.

### 16.2. FetchType.LAZY nhưng attribute đã loaded

~~~java
@OneToMany(fetch = FetchType.LAZY, mappedBy = "customer")
private List<PurchaseOrder> orders;
~~~

Annotation LAZY không có nghĩa trạng thái sẽ luôn false. Collection có thể đã được tải bởi fetch join, entity graph, truy cập trước đó, hoặc provider có quyết định fetch phù hợp khác.

### 16.3. Attribute đã loaded không đồng nghĩa association lồng nhau đã loaded

~~~java
util.isLoaded(customer, "orders") // true
~~~

không có nghĩa mọi lazy property của mọi `PurchaseOrder` trong list đã loaded. Cần xác định rõ **node nào trong object graph** ứng dụng chuẩn bị truy cập.

### 16.4. Cache không thể suy ra từ isLoaded

Nếu dữ liệu lấy từ second-level cache thay vì SQL query, attribute vẫn có thể được xem là loaded. `isLoaded` không phân biệt nguồn dữ liệu của lần tải.

### 16.5. Sau flush không nhất thiết mọi lazy attribute đã loaded

~~~java
em.flush();
~~~

là thao tác **đồng bộ dữ liệu thay đổi** xuống database, không phải yêu cầu tải mọi collection LAZY. Không dùng `flush` như giải pháp “khởi tạo toàn bộ entity graph”.

### 16.6. Load state không phản ánh dữ liệu mới nhất trong database

Một entity loaded có thể đã bị thay đổi bởi transaction khác. `isLoaded` không có nghĩa dữ liệu đang mới nhất, hợp lệ cho nghiệp vụ hay đã được refresh từ DB.

Nếu cần xử lý cập nhật cạnh tranh, phải dùng transaction isolation, optimistic locking (ví dụ `@Version`), pessimistic lock hoặc refresh khi phù hợp. `isLoaded` chỉ cung cấp **trạng thái tải**, không phải trạng thái đồng bộ dữ liệu giữa các transaction.

## 17. Khi nào nên dùng API riêng của provider?

Trong Hibernate có API như:

~~~java
// Phụ thuộc Hibernate, không phải Jakarta Persistence API:
org.hibernate.Hibernate.isInitialized(object);
~~~

Nó có thể hữu ích để kiểm tra proxy/collection theo cơ chế của Hibernate trong dự án xác định rõ provider. Tuy nhiên:

- `Hibernate.isInitialized` không portable sang EclipseLink hoặc JPA provider khác.
- Ý nghĩa và cách nhận diện proxy/collection có thể khác so với `PersistenceUnitUtil.isLoaded(...)` ở những tình huống phức tạp.
- Nếu chỉ cần kiểm tra một attribute JPA thông thường, nên cân nhắc API chuẩn trước.
- Không nên trộn logic ứng dụng với API nội bộ của provider chỉ để giải quyết bài toán fetch plan chưa được thiết kế rõ.

| Mục tiêu | Công cụ phù hợp |
| --- | --- |
| Kiểm tra attribute JPA được tải chưa | `PersistenceUnitUtil.isLoaded(entity, name)` |
| Không biết EMF cụ thể, cần tiện ích persistence chung | `Persistence.getPersistenceUtil()` |
| Lấy ID theo metadata persistence unit | `PersistenceUnitUtil.getIdentifier(entity)` |
| Biết entity có managed trong EM hiện hành không | `EntityManager.contains(entity)` |
| Kiểm tra cơ chế proxy Hibernate chuyên biệt | `Hibernate.isInitialized` nếu chấp nhận phụ thuộc provider |
| Chủ động tải đúng dữ liệu cho API | Fetch join, entity graph hoặc projection |
| Đếm SQL và phát hiện N+1 | SQL logs, metrics và statistics của provider |

## 18. Những lỗi và cách xử lý thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `isLoaded(entity) == true` nhưng truy cập collection vẫn phát SQL | Entity loaded theo EAGER, collection vẫn LAZY | Kiểm tra `isLoaded(entity, "collectionName")` |
| Gọi `getOrders()` để “kiểm tra” rồi phát SQL | Getter kích hoạt lazy loading | Dùng `isLoaded` nếu chỉ cần load state |
| Lỗi lazy loading sau khi đóng EM | Association chưa tải, nhưng code tiếp tục dereference | Fetch dữ liệu trước khi detach/close, hoặc dùng DTO query |
| `isLoaded` luôn true dù field có `LAZY` | Provider đã tải sớm hoặc cấu hình chưa hỗ trợ lazy basic attribute | Xem fetch plan và khả năng enhancement/provider |
| `isLoaded(entity, "full_name")` không hợp lệ | Dùng tên cột SQL thay cho attribute Java | Đổi thành `"fullName"` |
| Thử `isLoaded(entity, "orders[0]")` | API không xử lý cú pháp index/path tùy ý | Kiểm tra attribute entity trực tiếp |
| `PersistenceUtil` không có `getIdentifier` | Nhầm hai interface | Dùng `emf.getPersistenceUnitUtil().getIdentifier(...)` |
| Đã `flush()` nhưng collection vẫn chưa loaded | Flush không phải eager fetch | Chọn query/fetch plan cần thiết |
| `em.contains(entity) == false` nhưng dữ liệu vẫn đọc được | Entity detached vẫn giữ giá trị đã tải | Phân biệt managed state và loaded state |
| Truy vấn bị N+1 mặc dù đã thêm isLoaded | isLoaded chỉ quan sát, không tối ưu fetch | Dùng fetch join, batch fetching hoặc DTO projection |
| DTO có `id` nhưng không được JPA nhận diện | DTO không phải entity | Không dùng `isLoaded` để đánh giá DTO |
| Đọc entity loaded nhưng dữ liệu không mới | Transaction khác đã cập nhật DB | Dùng cơ chế concurrency/refresh phù hợp, không suy từ load state |
| Test cứng “LAZY luôn false” thất bại | LAZY là hint và provider có quyền tải sớm | Kiểm tra điều kiện thực tế thay vì suy diễn cứng |
| Trạng thái collection loaded nhưng phần tử gây SQL | Các quan hệ của phần tử vẫn LAZY | Đánh giá object graph đến đúng mức cần sử dụng |

## 19. Bài tập thực hành

### Bài 1. Phân biệt hai overload

Có entity `Customer` với `fullName` và `orders` khai báo lazy. Code:

~~~java
boolean a = util.isLoaded(customer);
boolean b = util.isLoaded(customer, "orders");
~~~

**Câu hỏi:** Có thể có `a == true` và `b == false` không?

**Đáp án:** Có. `isLoaded(entity)` không đồng nghĩa toàn bộ lazy attributes đã tải. Muốn biết collection `orders`, phải kiểm tra thuộc tính đó.

### Bài 2. Tên attribute nào hợp lệ?

Entity có:

~~~java
@Column(name = "full_name")
private String fullName;

@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders;
~~~

Các cách gọi:

~~~java
util.isLoaded(customer, "fullName");
util.isLoaded(customer, "full_name");
util.isLoaded(customer, "orders");
~~~

**Đáp án:** `"fullName"` và `"orders"` là tên thuộc tính Java được mapping. `"full_name"` là tên cột vật lý, không phải tên attribute tương ứng.

### Bài 3. Kiểm tra mà không chạy query

Bạn chỉ muốn log xem `orders` đã tải hay chưa, không muốn phát sinh query lấy orders.

**Đáp án:**

~~~java
boolean loaded =
    emf.getPersistenceUnitUtil()
       .isLoaded(customer, "orders");

System.out.println("orders loaded = " + loaded);
~~~

Không dùng `customer.getOrders().size()` như phép kiểm tra thuần.

### Bài 4. Entity đã detached nhưng orders đã loaded

Trước khi đóng `EntityManager`, application đã tải collection `orders`. Sau khi đóng, entity không còn managed.

**Câu hỏi:** Có chắc `isLoaded(customer, "orders")` phải false?

**Đáp án:** Không. Detach không xóa dữ liệu đã tải. Load state và trạng thái managed/detached là hai đặc tính khác nhau.

### Bài 5. Chỉ cần ID của proxy

Service có một JPA reference tới `PurchaseOrder`, cần lấy ID mà không muốn đọc toàn bộ field.

**Đáp án:**

~~~java
Object id =
    emf.getPersistenceUnitUtil()
       .getIdentifier(orderReference);
~~~

API này lấy định danh theo metadata của persistence unit, khác với việc kiểm tra thuộc tính lazy.

### Bài 6. Có cần lấy tất cả order numbers khi API trả response?

Response bắt buộc phải có trường `orderNumbers` đầy đủ. Collection của customer hiện chưa loaded.

**Đáp án:** Không nên dùng `if (isLoaded) ... else []` để trả danh sách rỗng giả. Nên truy vấn hoặc fetch các order numbers trước khi xây DTO, vì dữ liệu là bắt buộc theo hợp đồng API.

### Bài 7. isLoaded có phát hiện N+1 không?

Một vòng lặp qua 100 customers đã phát sinh nhiều SELECT tải order collection. Cuối vòng lặp `isLoaded(c, "orders")` trả true.

**Đáp án:** True chỉ nói trạng thái collection hiện đã loaded; nó không tiết lộ số query hay dữ liệu được lấy bằng cache. Dùng SQL logging/metrics để xác định N+1, sau đó thiết kế fetch plan phù hợp.

### Bài 8. PersistenceUtil hay PersistenceUnitUtil?

Bạn ở trong repository/service đã có `EntityManagerFactory` thuộc `shopPU` và cần vừa kiểm tra `orders` vừa lấy ID.

**Đáp án:** Dùng `PersistenceUnitUtil` từ `emf.getPersistenceUnitUtil()` vì biết rõ PU và cần `getIdentifier`. `PersistenceUtil` phù hợp hơn khi chỉ cần kiểm tra chung và không giữ EMF cụ thể.

### Bài 9. isLoaded(customer, "orders") true nghĩa là gì?

**Đáp án:** Collection `orders` được xem là loaded. Không suy ra tất cả các quan hệ của mỗi `PurchaseOrder` đều loaded, không suy ra không có SQL nào đã chạy và không suy ra dữ liệu vừa được refresh từ database.

### Bài 10. Flush có làm lazy load không?

~~~java
em.flush();
boolean loaded = util.isLoaded(customer, "orders");
~~~

**Đáp án:** Flush đồng bộ thay đổi với database, không phải yêu cầu tải collection lazy. Trạng thái loaded phụ thuộc việc dữ liệu đã được nạp như thế nào, không phải chỉ vì vừa gọi flush.

## 20. Ghi nhớ

- **`PersistenceUnitUtil`** lấy từ `EntityManagerFactory.getPersistenceUnitUtil()`, gắn với persistence unit và hỗ trợ `isLoaded(...)` cùng `getIdentifier(...)`.
- **`PersistenceUtil`** lấy từ `Persistence.getPersistenceUtil()`, cung cấp các phép kiểm tra tải chung mà không cần một EMF cụ thể.
- **`isLoaded(entity)` không chứng minh mọi thuộc tính LAZY đã tải**; với collection hay field cụ thể, dùng `isLoaded(entity, "attributeName")`.
- **`attributeName` là tên attribute Java được JPA ánh xạ**, không phải tên cột SQL hay biểu thức đường dẫn tùy ý.
- **Load state khác managed state**. `em.contains(entity)` cho biết association với persistence context cụ thể; `isLoaded` cho biết trạng thái dữ liệu đã nạp.
- **Kiểm tra trạng thái tải không phải thao tác chủ động fetch**. Khi nghiệp vụ cần dữ liệu, dùng JPQL fetch join, entity graph hoặc DTO projection.
- **Kết quả loaded không đo hiệu năng và không khẳng định dữ liệu mới nhất**. Muốn đếm SQL/N+1 phải dùng công cụ quan sát; muốn xử lý đồng thời phải dùng cơ chế transaction/locking thích hợp.
- **Không dùng isLoaded trên DTO** như thể DTO là entity; API này có ý nghĩa với các đối tượng JPA thuộc persistence unit/provider phù hợp.

Cách đặt câu hỏi đúng trước mỗi lần truy cập quan hệ LAZY là: **“Tôi chỉ cần biết dữ liệu đã được tải, hay nghiệp vụ thực sự cần tải dữ liệu đó?”** Nếu chỉ cần biết, dùng `isLoaded`. Nếu cần dữ liệu, thiết kế fetch plan và ranh giới transaction để tải đúng phần dữ liệu cần dùng, rồi chuyển sang DTO hoặc xử lý trong persistence context một cách có chủ đích.
