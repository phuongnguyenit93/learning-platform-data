# Generic và giới hạn kiểu để tránh trộn những loại dữ liệu khác nghĩa

## Mục tiêu học tập

Trong ứng dụng Java, nhiều giá trị có **cùng kiểu dữ liệu kỹ thuật** nhưng mang **ý nghĩa nghiệp vụ khác nhau**: mã khách hàng và mã đơn hàng đều có thể là UUID; tiền VND và tiền USD đều có thể biểu diễn bằng BigDecimal; khối lượng và khoảng cách đều có thể là số. Nếu mọi API chỉ nhận String, UUID hoặc BigDecimal, trình biên dịch không đủ thông tin để ngăn việc truyền nhầm.

**Generics** cho phép tham số hóa kiểu, còn **giới hạn kiểu** (*type bounds*) xác định những kiểu nào được phép tham gia một API dùng chung. Kết hợp generics với **kiểu miền có tên riêng** (*nominal domain types*, thường là value object) giúp những sai sót trộn dữ liệu khác nghĩa bị phát hiện ngay lúc biên dịch, thay vì chỉ bộc lộ khi truy vấn hoặc ghi vào cơ sở dữ liệu.

Bài học thuộc chương **Mô hình Java** của module **DATABASE_DATA_MODELING**. Mục tiêu của module là chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ và ràng buộc đến chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; đồng thời biết so sánh mô hình quan hệ, document, đồ thị và phân tích để chọn cấu trúc phù hợp, dễ tiến hóa và kiểm chứng. Bài này tập trung vào **biên giới kiểu của mô hình Java và cách bảo toàn ngữ nghĩa khi chuyển sang mô hình dữ liệu**.

Sau bài học, bạn có thể:

1. Giải thích generic type, type parameter, type argument, **giới hạn trên** (*upper bound*) và **nhiều giới hạn** (*multiple bounds*) trong Java.
2. Chỉ ra lý do generics **không tự tạo ra khác biệt ngữ nghĩa** nếu hai miền đều dùng String, UUID hay Number.
3. Thiết kế **CustomerId**, **OrderId**, **Money**, **Quantity** và **Repository** có kiểu rõ ràng để ngăn truyền nhầm dữ liệu.
4. Dùng mẫu **E extends Identified<ID>** để ràng buộc thực thể và kiểu khóa của kho dữ liệu.
5. Phân biệt **invariance**, **wildcard extends/super** và nguyên tắc **PECS** khi đọc hoặc ghi các tập hợp có kiểu.
6. Hiểu giới hạn của **type erasure**, raw types, unchecked casts, so sánh equality và sự khác biệt giữa an toàn lúc biên dịch với kiểm chứng lúc chạy.
7. Biết lớp bảo vệ nào thuộc Java, lớp nào phải tiếp tục được bảo đảm bằng **PRIMARY KEY**, **FOREIGN KEY**, **UNIQUE** và ràng buộc cơ sở dữ liệu.

> **Phiên bản ví dụ:** Các đoạn mã dùng cú pháp Java 17 trở lên, bao gồm record. Chúng minh họa mô hình miền và tập hợp trong bộ nhớ; không ngụ ý record tự động là JPA entity hoặc một repository trong bộ nhớ thay thế được giao dịch của cơ sở dữ liệu.

## 1. Cùng kiểu kỹ thuật không có nghĩa là cùng ý nghĩa

Giả sử API cũ được viết như sau:

~~~~java
import java.util.UUID;

class OrderServiceBad {
    void loadOrder(UUID orderId) {
        // Đọc đơn hàng theo id.
    }

    void changeCustomer(UUID orderId, UUID customerId) {
        // Chuyển đơn sang khách hàng được chỉ định.
    }
}
~~~~

Lệnh gọi dưới đây **hợp lệ ở mức Java**, dù hai tham số đã bị tráo ý nghĩa:

~~~~java
UUID orderId = UUID.randomUUID();
UUID customerId = UUID.randomUUID();

OrderServiceBad service = new OrderServiceBad();
service.changeCustomer(customerId, orderId); // Biên dịch được, nhưng sai nghiệp vụ.
~~~~

Trình biên dịch chỉ thấy hai UUID. Nếu hai giá trị có hình dạng hợp lệ, vấn đề có thể chỉ xuất hiện lúc truy vấn không tìm thấy bản ghi, cập nhật nhầm hoặc vi phạm khóa ngoại. **Tên biến giúp người đọc nhưng không tạo ràng buộc kiểu cho lời gọi hàm.**

Tương tự:

~~~~java
void transferAmount(java.math.BigDecimal amount);
void moveBy(java.math.BigDecimal distance);
~~~~

Không có gì ngăn truyền số tiền vào tham số khoảng cách, nếu mô hình chỉ dùng BigDecimal.

### Phân loại ba tầng của một giá trị

| Tầng | Ví dụ | Điều có thể bảo đảm |
| --- | --- | --- |
| **Kiểu kỹ thuật** | UUID, String, BigDecimal | Biểu diễn, phép toán cơ bản |
| **Kiểu miền** | CustomerId, OrderId, Money, Distance | Ngữ nghĩa, ràng buộc và phương thức hợp lệ cho từng loại |
| **Ràng buộc dữ liệu** | PK, FK, UNIQUE, CHECK trong DB | Tồn tại, duy nhất, liên kết và tính đúng khi nhiều giao dịch cùng ghi |

Ba tầng **bổ sung cho nhau**. Một CustomerId được thiết kế tốt ngăn truyền OrderId nhầm ở Java; nó **không tự bảo đảm** khách hàng ấy tồn tại trong cơ sở dữ liệu.

## 2. Generic là tham số hóa kiểu, không phải phép đổi tên dữ liệu

### 2.1. Một API không dùng generic

~~~~java
import java.util.ArrayList;
import java.util.List;

List raw = new ArrayList();
raw.add("KH01");
raw.add(123);

String customerCode = (String) raw.get(1); // ClassCastException khi chạy.
~~~~

**Raw type** List (không cung cấp type argument) bỏ qua phần bảo vệ kiểu của generic. Trình biên dịch có thể cảnh báo, nhưng phép thêm 123 vẫn được chấp nhận ở danh sách raw.

### 2.2. Khai báo generic

~~~~java
import java.util.ArrayList;
import java.util.List;

List<String> customerCodes = new ArrayList<>();
customerCodes.add("KH01");

// customerCodes.add(123); // Lỗi biên dịch: Integer không phải String.
String first = customerCodes.get(0);
~~~~

**List<E>** là kiểu generic với tham số E. Trong **List<String>**, String là *type argument*. Trình biên dịch biết danh sách này chỉ chấp nhận String và có thể trả String mà không yêu cầu ép kiểu thủ công.

Nhưng điều này **chưa đủ cho phân biệt ngữ nghĩa**:

~~~~java
List<String> customerCodes = new ArrayList<>();
List<String> productCodes = new ArrayList<>();

productCodes.add("SP01");
customerCodes.add(productCodes.get(0)); // Vẫn biên dịch: cả hai là String.
~~~~

Generic bảo đảm danh sách chứa String; nó **không biết String nào là mã khách, String nào là mã sản phẩm**. Muốn ngăn nhầm, phải tạo các kiểu miền khác nhau, rồi đưa chúng vào generics.

### 2.3. Type parameter và type argument

~~~~java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

Box<String> name = new Box<>("Nguyễn An");
Box<Integer> quantity = new Box<>(3);
~~~~

Ở phần định nghĩa, **T** là *type parameter* chưa biết cụ thể. Khi dùng, **String** và **Integer** là các *type argument*. Cùng một khuôn Box dùng lại cho nhiều loại dữ liệu mà không phải lặp mã.

Điều cần phân biệt: **Box<CustomerId> khác Box<OrderId> tại thời điểm kiểm tra kiểu**, nhưng **Box<UUID> cho khách và Box<UUID> cho đơn thì vẫn cùng một kiểu Box<UUID>**.

## 3. Giới hạn kiểu bằng extends

Một type parameter chưa có giới hạn thường chỉ cho phép thao tác mà Java biết mọi Object đều hỗ trợ. Nếu API cần gọi một phương thức chuyên biệt, hãy khai báo **upper bound**.

### 3.1. Một giới hạn trên

~~~~java
interface Identified<ID> {
    ID id();
}

final class IdPrinter<E extends Identified<?>> {
    void print(E entity) {
        System.out.println(entity.id());
    }
}
~~~~

**E extends Identified<?>** nói rằng E phải là một kiểu triển khai Identified với một kiểu ID nào đó. Nhờ vậy, mã trong IdPrinter được phép gọi **entity.id()**.

Đối với generic bound, Java dùng từ khóa **extends** kể cả khi giới hạn là một **interface**:

~~~~java
class Example<T extends java.io.Serializable> {
    // T phải triển khai Serializable.
}
~~~~

Không viết **T implements Serializable** trong phần khai báo type parameter.

### 3.2. Generic method và nhiều giới hạn

~~~~java
final class Comparisons {
    static <T extends Number & Comparable<T>> T larger(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }
}

Integer largerCount = Comparisons.larger(5, 8);
java.math.BigDecimal largerPrice = Comparisons.larger(
    new java.math.BigDecimal("10.50"),
    new java.math.BigDecimal("8.25")
);
~~~~

**T extends Number & Comparable<T>** yêu cầu T đồng thời:

- Là kiểu con của **Number**.
- Có khả năng so sánh với **chính T** thông qua Comparable<T>.

Trong khai báo nhiều giới hạn, nếu có **một lớp**, lớp đó phải được liệt kê **đầu tiên**; các interface theo sau với dấu **&**. Java không cho một type parameter kế thừa đồng thời hai lớp độc lập.

Giới hạn trên khiến phương thức **larger** biết chắc **compareTo** hợp lệ với cặp tham số có cùng T. Nhưng Number không phân biệt “số lượng hàng”, “đơn giá” và “mét đường”. **Giới hạn kiểu kỹ thuật chưa đủ để bảo vệ ý nghĩa miền.**

### 3.3. Giới hạn là hợp đồng năng lực, không phải xác thực nghiệp vụ

Ví dụ một generic repository cần các đối tượng có phương thức **id()**; giới hạn E extends Identified<ID> diễn đạt đúng hợp đồng này. Nhưng một API dành riêng cho tiền VND không nên chỉ nhận **T extends Number**: giới hạn đó vẫn cho phép nhiều số mang ý nghĩa khác nhau.

Sự khác biệt:

- **Bound** trả lời: “E phải **có khả năng gì**?”.
- **Kiểu miền** trả lời: “Giá trị này **đại diện cho điều gì**?”.
- **Kiểm tra nghiệp vụ** trả lời: “Giá trị này **có hợp lệ trong ngữ cảnh hiện tại**?”.

## 4. Tạo kiểu miền riêng bằng record

Java là ngôn ngữ có kiểu theo **tên khai báo** (*nominal typing*) đối với class/record. Hai record khác nhau vẫn là hai kiểu khác nhau, ngay cả khi cùng chứa UUID.

~~~~java
import java.util.Objects;
import java.util.UUID;

record CustomerId(UUID value) {
    CustomerId {
        Objects.requireNonNull(value, "customer id must not be null");
    }
}

record OrderId(UUID value) {
    OrderId {
        Objects.requireNonNull(value, "order id must not be null");
    }
}

record ProductId(UUID value) {
    ProductId {
        Objects.requireNonNull(value, "product id must not be null");
    }
}
~~~~

Ở đây:

- **CustomerId** và **OrderId** có cấu trúc bên trong như nhau, nhưng **khác kiểu Java**.
- **new CustomerId(uuid)** không thể được truyền trực tiếp vào tham số OrderId.
- Constructor từ chối UUID null, giúp giảm trạng thái miền không hợp lệ.
- Record tự cung cấp equals/hashCode dựa vào **kiểu record và các thành phần**; một CustomerId không bằng một OrderId chỉ vì có cùng UUID.

Ví dụ:

~~~~java
final class TypedOrderService {
    void changeCustomer(OrderId orderId, CustomerId customerId) {
        // Tìm đơn theo OrderId và kiểm tra khách hàng theo CustomerId.
    }
}

UUID rawId = UUID.randomUUID();
OrderId orderId = new OrderId(rawId);
CustomerId customerId = new CustomerId(rawId);

TypedOrderService service = new TypedOrderService();
service.changeCustomer(orderId, customerId); // Hợp lệ về kiểu.

// service.changeCustomer(customerId, orderId);
// Lỗi biên dịch: tham số thứ nhất phải là OrderId.
~~~~

Ngay cả khi hai wrapper chứa cùng UUID, compiler vẫn phân biệt loại định danh. Đó là cải tiến quan trọng so với API **changeCustomer(UUID, UUID)**.

### 4.1. Record không chỉ là kỹ thuật chống truyền nhầm

Một value object còn là nơi đặt quy tắc miền:

~~~~java
record CustomerCode(String value) {
    CustomerCode {
        Objects.requireNonNull(value);
        if (!value.matches("KH[0-9]{4}")) {
            throw new IllegalArgumentException("Invalid customer code");
        }
    }
}
~~~~

Giả sử miền yêu cầu mã khách ở dạng **KH0001**, mã không hợp lệ sẽ bị chặn ngay khi tạo CustomerCode. Đây là **quy tắc giả định của ví dụ**, không phải chuẩn mã chung.

Lưu ý: record cung cấp bất biến đơn giản và tính bất biến của **tham chiếu thành phần**, nhưng nếu thành phần là một đối tượng có thể thay đổi (như mảng), record **không tự tạo deep immutability**. Chọn kiểu thành phần bất biến hoặc sao chép phòng vệ khi cần.

## 5. Generic repository ràng buộc cả kiểu thực thể và kiểu khóa

Đây là ví dụ quan trọng của việc dùng generics **sau khi đã phân biệt định danh miền**.

### 5.1. Hợp đồng thực thể

~~~~java
interface Identified<ID> {
    ID id();
}

record Customer(CustomerId id, String name)
        implements Identified<CustomerId> {
    Customer {
        Objects.requireNonNull(id);
        Objects.requireNonNull(name);
    }
}

record Order(OrderId id, CustomerId customerId,
             java.math.BigDecimal total)
        implements Identified<OrderId> {
    Order {
        Objects.requireNonNull(id);
        Objects.requireNonNull(customerId);
        Objects.requireNonNull(total);
        if (total.signum() < 0) {
            throw new IllegalArgumentException("Total must be nonnegative");
        }
    }
}
~~~~

**Customer** có id kiểu **CustomerId**. **Order** có id kiểu **OrderId** nhưng cũng giữ **customerId** để diễn đạt tham chiếu đến khách. Hai vai trò này không bị lẫn chỉ vì chúng đều có UUID ở bên trong.

### 5.2. Repository generic có giới hạn

~~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

final class Repository<E extends Identified<ID>, ID> {
    private final Map<ID, E> rows = new HashMap<>();

    void save(E entity) {
        rows.put(entity.id(), entity);
    }

    Optional<E> findById(ID id) {
        return Optional.ofNullable(rows.get(id));
    }

    boolean existsById(ID id) {
        return rows.containsKey(id);
    }
}
~~~~

Khai báo **E extends Identified<ID>** tạo quan hệ bắt buộc giữa **loại thực thể E** và **loại khóa ID**. Do đó Repository biết rằng entity.id() trả về đúng ID và Map<ID,E> không phải chứa đối tượng hoặc khóa không phù hợp.

### 5.3. Cách sử dụng

~~~~java
import java.math.BigDecimal;
import java.util.UUID;

Customer customer = new Customer(
    new CustomerId(UUID.randomUUID()), "Nguyễn An"
);
Order order = new Order(
    new OrderId(UUID.randomUUID()),
    customer.id(),
    new BigDecimal("95000.00")
);

Repository<Customer, CustomerId> customers = new Repository<>();
Repository<Order, OrderId> orders = new Repository<>();

customers.save(customer);
orders.save(order);

Customer foundCustomer = customers.findById(customer.id()).orElseThrow();
Order foundOrder = orders.findById(order.id()).orElseThrow();

// orders.findById(customer.id());
// Lỗi biên dịch: tìm Order phải dùng OrderId, không phải CustomerId.

// orders.save(customer);
// Lỗi biên dịch: Repository<Order, OrderId> không nhận Customer.

// new Order(order.id(), order.id(), new BigDecimal("10"));
// Lỗi biên dịch: tham số thứ hai của Order phải là CustomerId.
~~~~

Nhờ kết hợp **record ID có tên riêng** và **Repository<E, ID>**, cả lớp dịch vụ và lớp lưu trữ trong bộ nhớ đều bảo vệ quan hệ “loại thực thể nào đi với loại khóa nào”.

> **Giới hạn của ví dụ:** Repository này là Map trong bộ nhớ, **không có giao dịch, FK, phân quyền, xử lý đồng thời, lưu bền hay kiểm tra khách tồn tại**. Nó chỉ minh họa hợp đồng kiểu. Trong ứng dụng thật, một adapter JDBC/JPA hoặc một triển khai kho dữ liệu khác phải thực hiện các nghĩa vụ lưu trữ tương ứng.

## 6. Thiết kế API generic mà không đánh mất ranh giới ngữ nghĩa

### 6.1. Đừng thay ID miền bằng một kiểu chung

Một phiên bản repository trông có vẻ tổng quát nhưng đánh mất ranh giới:

~~~~java
import java.util.UUID;

interface BadRepository<E> {
    E find(UUID id);
}
~~~~

Mọi repository đều nhận UUID, nên khách hàng và đơn hàng lại có thể bị tra cứu bằng UUID sai miền. Thay vào đó:

~~~~java
interface TypedRepository<E, ID> {
    java.util.Optional<E> findById(ID id);
    void save(E entity);
}
~~~~

Khai báo **TypedRepository<Order, OrderId>** xác định loại khóa được nhận. Nếu còn cần bảo đảm entity.id() trả về cùng loại, thêm giới hạn như:

~~~~java
interface BoundedRepository<E extends Identified<ID>, ID> {
    java.util.Optional<E> findById(ID id);
    void save(E entity);
}
~~~~

Sự kết hợp giữa **kiểu miền riêng** và **generic bound** quan trọng hơn việc chỉ dùng một trong hai.

### 6.2. Giới hạn generic không bắt buộc các type argument là hai kiểu khác nhau

Khai báo:

~~~~java
Repository<Customer, CustomerId> customers = new Repository<>();
Repository<Order, OrderId> orders = new Repository<>();
~~~~

chỉ cho thấy hai repository có ràng buộc khác nhau **vì CustomerId và OrderId đã là hai kiểu khác nhau**. Nếu cả hai entity đều khai báo **Identified<UUID>**, thì generic repository dùng ID=UUID cho cả hai; compiler không ngăn truyền UUID của đối tượng này sang nơi khác đang yêu cầu UUID.

Đây là một quy tắc thiết kế quan trọng:

> **Để bảo vệ ý nghĩa nghiệp vụ, phải biểu diễn sự khác biệt đó trong hệ thống kiểu.** Generics giữ và truyền sự khác biệt; nó không tự phát minh ý nghĩa cho hai giá trị cùng kiểu.

### 6.3. Một type parameter chung có thể được suy diễn quá rộng

Ví dụ:

~~~~java
final class Pairing {
    static <T> boolean equal(T left, T right) {
        return java.util.Objects.equals(left, right);
    }
}

boolean result = Pairing.equal(
    new CustomerId(UUID.randomUUID()),
    new OrderId(UUID.randomUUID())
);
// Lời gọi vẫn biên dịch được: T có thể được suy diễn là kiểu cha chung.
~~~~

Không nên cho rằng **hai tham số cùng ký hiệu T luôn bắt buộc có cùng kiểu miền cụ thể** trong mọi lời gọi generic method. Java có thể suy diễn một **kiểu chung rộng hơn** cho T, chẳng hạn Object.

Nếu một API thực sự chỉ so sánh hai OrderId, hãy viết chữ ký cố định:

~~~~java
static boolean sameOrder(OrderId a, OrderId b) {
    return a.equals(b);
}
~~~~

Hoặc cố định kiểu T ở **đối tượng nhận lời gọi** và phương thức xử lý của đối tượng đó, thay vì để compiler tự suy diễn T riêng từ hai đối số không cùng miền.

### 6.4. Kiểu kết quả cũng phải gắn với kiểu đầu vào

Một API nhận CustomerId nhưng trả về Object bắt người gọi ép kiểu và làm mất một phần lợi ích:

~~~~java
Object findCustomerBad(CustomerId id);
~~~~

API nên phản ánh hợp đồng:

~~~~java
java.util.Optional<Customer> findCustomer(CustomerId id);
~~~~

Hoặc dùng generic repository đã cố định **E** và **ID**. **Optional<Customer>** biểu diễn khả năng không tìm thấy một khách hàng trong khi vẫn bảo vệ kiểu kết quả; Optional **không chứng minh khách tồn tại**, chỉ giúp xử lý trường hợp thiếu kết quả một cách tường minh.

## 7. Invariance: vì sao List<Order> không phải List<Identified<?>>

Java generic **bất biến** (*invariant*) theo type argument. Giả sử Order implements Identified<OrderId>:

~~~~java
import java.util.ArrayList;
import java.util.List;

List<Order> orderList = new ArrayList<>();

// List<Object> objects = orderList;             // Lỗi biên dịch.
// List<Identified<?>> entities = orderList;     // Lỗi biên dịch.
~~~~

Lý do: nếu List<Order> được xem như List<Object>, một người có thể thêm Customer vào danh sách ấy, phá vỡ cam kết rằng mọi phần tử là Order.

Phân biệt:

- **Order** có thể là subtype của Identified<OrderId>.
- **List<Order>** không vì thế trở thành subtype của **List<Identified<OrderId>>**.
- Muốn nhận một danh sách các subtype của một giao diện để **đọc**, hãy cân nhắc wildcard.

### 7.1. Wildcard extends: đọc từ nhóm kiểu có chung hợp đồng

~~~~java
import java.util.List;

final class IdReporting {
    static void printIds(List<? extends Identified<?>> entities) {
        for (Identified<?> entity : entities) {
            System.out.println(entity.id());
        }

        // Không được thêm một Customer hay Order tùy ý vào entities:
        // kiểu phần tử cụ thể đang bị ẩn bởi wildcard capture.
    }
}

List<Order> allOrders = new ArrayList<>();
List<Customer> allCustomers = new ArrayList<>();

IdReporting.printIds(allOrders);
IdReporting.printIds(allCustomers);
~~~~

**? extends Identified<?>** chấp nhận danh sách của các loại thực thể có phương thức id(), giúp viết báo cáo chung. Vì wildcard ẩn đi kiểu phần tử chính xác, phương thức không được thêm tùy tiện một Order hoặc Customer vào danh sách.

**Cần phân biệt hai dấu hỏi:** Dấu hỏi bên ngoài là loại phần tử bất kỳ phù hợp với Identified; dấu hỏi bên trong nói rằng loại ID của thực thể cũng chưa biết. Nhờ vậy báo cáo chỉ được phép in id, **không nên giả định mọi id đều là OrderId**.

### 7.2. Wildcard super: ghi đối tượng vào đích có khả năng nhận nó

~~~~java
import java.util.List;

final class Collecting {
    static void addCustomer(List<? super Customer> target, Customer value) {
        target.add(value);
    }
}

List<Customer> customers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

Collecting.addCustomer(customers, customer);
Collecting.addCustomer(objects, customer);
~~~~

**? super Customer** cho biết danh sách nhận Customer hoặc một supertype của Customer. Ta có thể **thêm Customer**, nhưng khi đọc phần tử thông thường chỉ có thể xem nó như Object, vì loại phần tử cụ thể của danh sách không được biết.

### 7.3. Quy tắc PECS

**PECS** viết tắt của *Producer Extends, Consumer Super*:

- **Nguồn cung cấp giá trị để đọc:** thường dùng **? extends T**.
- **Đích nhận giá trị để ghi:** thường dùng **? super T**.
- **Vừa đọc đúng T vừa ghi T:** thường dùng kiểu T cụ thể, không cần wildcard.

Ví dụ khi sao chép:

~~~~java
static <T> void copy(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
~~~~

Tuy nhiên, **PECS là quy tắc API tập hợp, không phải công cụ chứng minh hai kiểu miền có cùng ý nghĩa**. Một hàm báo cáo chung có thể đọc nhiều kiểu thực thể; thao tác nghiệp vụ tạo đơn cần chữ ký cụ thể để không nhận nhầm khách hàng như đơn hàng.

### 7.4. Wildcard không phù hợp cho mọi kho dữ liệu

Nếu API khai báo:

~~~~java
void saveAny(Identified<?> value);
~~~~

nó nhận nhiều loại thực thể và có thể mất khả năng bảo đảm kho dành cho Order chỉ nhận Order. Các API thao tác ghi quan trọng nên cố định **E** và **ID** qua type parameter ở repository hoặc chữ ký riêng, thay vì lạm dụng wildcard.

## 8. Type erasure: an toàn lúc biên dịch không phải định danh kiểu lúc chạy

Trong Java, phần lớn thông tin type argument của generics được **xóa tại runtime** (*type erasure*). Điều này giúp tương thích với các thư viện Java cũ nhưng tạo ra những giới hạn cần lưu ý.

### 8.1. Hai List có type argument khác nhau vẫn có cùng lớp runtime

~~~~java
List<CustomerId> customerIds = new ArrayList<>();
List<OrderId> orderIds = new ArrayList<>();

System.out.println(customerIds.getClass() == orderIds.getClass());
// true: cùng là ArrayList tại runtime.
~~~~

Không thể dùng:

~~~~java
// if (value instanceof List<CustomerId>) { ... }
// Không hợp lệ: type argument cụ thể không thể kiểm tra theo cách này.
~~~~

Có thể kiểm tra **value instanceof List<?>** vì wildcard không đòi hỏi biết phần tử cụ thể; muốn xác minh mỗi phần tử có đúng loại, phải kiểm tra lần lượt với cơ chế runtime phù hợp.

### 8.2. Không thể new T() trực tiếp

~~~~java
class Creator<T> {
    // T make() { return new T(); } // Không biên dịch.
}
~~~~

Vì runtime không biết constructor của T và Java không bảo đảm T có constructor không tham số. Nếu cần tạo đối tượng, truyền **factory**:

~~~~java
import java.util.function.Supplier;

final class Creator<T> {
    private final Supplier<T> factory;

    Creator(Supplier<T> factory) {
        this.factory = factory;
    }

    T make() {
        return factory.get();
    }
}

Creator<CustomerId> idCreator =
    new Creator<>(() -> new CustomerId(UUID.randomUUID()));
CustomerId newId = idCreator.make();
~~~~

Nếu cần kiểm tra hoặc chuyển kiểu lúc chạy, có thể truyền **Class<T>** hay bộ giải mã có thông tin kiểu một cách tường minh. Không nên kỳ vọng type parameter T tự tồn tại đầy đủ khi chạy.

### 8.3. Nguy cơ khi dùng generic typed ID không có nhãn runtime

Giả sử người thiết kế muốn giảm số lượng record ID bằng một khuôn duy nhất:

~~~~java
record NaiveId<T>(UUID value) {}

UUID same = UUID.randomUUID();
NaiveId<Customer> customerId = new NaiveId<>(same);
NaiveId<Order> orderId = new NaiveId<>(same);

// Không thể truyền trực tiếp NaiveId<Customer> vào API yêu cầu NaiveId<Order>.
// Nhưng biểu thức sau lại là true:
System.out.println(customerId.equals(orderId)); // true
~~~~

Vì sao **equals** trả về true? Hai giá trị đều là **cùng lớp record NaiveId lúc chạy** và cùng thành phần UUID. Type argument **Customer/Order** không được lưu như thành phần của record; nó đã bị xóa về mặt định danh runtime.

Điều này có thể nguy hiểm nếu ID được so sánh chung, làm khóa Map không phân biệt miền, hoặc bị đưa qua API raw/unchecked. Đây là ví dụ điển hình cho việc **an toàn biên dịch không tự bảo đảm phân biệt miền khi đã mất thông tin generic**.

### 8.4. Hai giải pháp cho typed ID

**Cách A — record riêng cho từng miền:** CustomerId, OrderId, ProductId như mục 4. Đây thường là lựa chọn rõ ràng, đơn giản và an toàn cả khi so sánh equals.

**Cách B — generic ID mang nhãn runtime:**

~~~~java
import java.util.Objects;
import java.util.UUID;

interface EntityKind {}

final class CustomerKind implements EntityKind {
    private CustomerKind() {}
}

final class OrderKind implements EntityKind {
    private OrderKind() {}
}

record TaggedId<K extends EntityKind>(Class<K> kind, UUID value) {
    TaggedId {
        Objects.requireNonNull(kind, "kind");
        Objects.requireNonNull(value, "value");
    }
}

UUID shared = UUID.randomUUID();
TaggedId<CustomerKind> c = new TaggedId<>(CustomerKind.class, shared);
TaggedId<OrderKind> o = new TaggedId<>(OrderKind.class, shared);

System.out.println(c.equals(o)); // false: kind cũng là thành phần record.
~~~~

Nhờ **Class<K> kind**, giá trị ID có thông tin phân biệt miền lúc chạy. Khi dùng, phải bảo đảm mọi đường tạo ID đều cung cấp đúng kind; raw type hoặc unchecked cast vẫn có thể phá hợp đồng kiểu trong mã thiếu an toàn.

Không cần áp dụng TaggedId cho mọi dự án. Khi chỉ có vài loại ID, record riêng thường **ít phức tạp hơn và dễ đọc trong DTO, API, log**. Khi có nhiều kiểu định danh và framework generic rộng, TaggedId có thể là phương án đáng cân nhắc.

### 8.5. Raw types và unchecked casts làm thủng hàng rào

~~~~java
@SuppressWarnings({"rawtypes", "unchecked"})
static void unsafe(Repository<Order, OrderId> typed, Customer customer) {
    Repository raw = typed;
    raw.save(customer); // Tránh được kiểm tra generic của compiler.
}
~~~~

Hàm trên **không phải cách lập trình được khuyến nghị**. Nó minh họa rằng raw type và unchecked operations có thể đưa Customer vào kho Order trong bộ nhớ. Lỗi có thể chỉ xuất hiện khi đọc, cast hoặc xử lý dữ liệu sau đó.

Hãy tránh raw types, hạn chế **@SuppressWarnings("unchecked")** và đặt mọi chuyển kiểu không an toàn ở adapter nhỏ có kiểm tra, thay vì để lan vào mã miền.

## 9. Generic không chỉ dành cho ID: tiền tệ và đơn vị đo

Một mô hình dữ liệu tốt cần phân biệt các giá trị cùng kiểu số nhưng khác nghĩa. Chỉ dùng BigDecimal hoặc **T extends Number** không thể tự bảo vệ điều đó.

### 9.1. Tiền là giá trị có cả số lượng và đơn vị tiền

~~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

record Money(BigDecimal amount, Currency currency) {
    Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }

    Money plus(Money other) {
        Objects.requireNonNull(other);
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException(
                "Cannot add amounts in different currencies"
            );
        }
        return new Money(amount.add(other.amount()), currency);
    }
}

Money vndA = new Money(
    new BigDecimal("120000"), Currency.getInstance("VND")
);
Money vndB = new Money(
    new BigDecimal("30000"), Currency.getInstance("VND")
);
Money usd = new Money(
    new BigDecimal("10.00"), Currency.getInstance("USD")
);

Money sum = vndA.plus(vndB); // 150000 VND.
// vndA.plus(usd); // Biên dịch được; bị từ chối khi chạy.
~~~~

Với **Money**, loại tiền được lưu như **giá trị runtime**. Constructor bảo đảm amount và currency không NULL; plus bảo đảm hai đơn vị tiền giống nhau. Generic không phải công cụ bắt buộc cho mọi tình huống: đôi khi một **value object chứa đơn vị và kiểm tra runtime** là mô hình đơn giản nhất.

Không nên tự động cộng VND và USD bằng tỷ giá ngầm định. Nếu nghiệp vụ cần đổi tiền, phải có một hàm chuyển đổi **có tỷ giá, nguồn tỷ giá, thời điểm hiệu lực và quy tắc làm tròn rõ ràng**. Những yếu tố đó là dữ liệu nghiệp vụ, không suy ra được chỉ từ BigDecimal.

### 9.2. Phantom type: dùng type parameter làm nhãn ngữ nghĩa

Nếu muốn phân biệt đơn vị đo ở mức **compile-time**, có thể dùng kiểu đánh dấu:

~~~~java
import java.math.BigDecimal;
import java.util.Objects;

interface MeasureUnit {}

final class Kilogram implements MeasureUnit {
    private Kilogram() {}
}

final class Meter implements MeasureUnit {
    private Meter() {}
}

record Quantity<U extends MeasureUnit>(BigDecimal value) {
    Quantity {
        Objects.requireNonNull(value);
    }

    Quantity<U> plus(Quantity<U> other) {
        return new Quantity<>(value.add(other.value()));
    }
}

Quantity<Kilogram> weight = new Quantity<>(new BigDecimal("2.5"));
Quantity<Kilogram> extraWeight = new Quantity<>(new BigDecimal("1.2"));
Quantity<Meter> length = new Quantity<>(new BigDecimal("5.0"));

Quantity<Kilogram> totalWeight = weight.plus(extraWeight);

// weight.plus(length);
// Lỗi biên dịch: Quantity<Meter> không phải Quantity<Kilogram>.
~~~~

Tham số **U** không được dùng để tính giá trị; nó đóng vai trò **nhãn kiểu**. Đây thường được gọi là **phantom type** trong thiết kế kiểu.

Nhưng cần hiểu giới hạn:

- Do **type erasure**, U không có mặt như một thành phần runtime của record Quantity.
- Hai Quantity của hai đơn vị khác nhau nhưng cùng BigDecimal có thể có **equals trả về true**, tương tự NaiveId ở mục 8.
- Dữ liệu đọc từ JSON hoặc DB phải được gán **đúng loại đơn vị** bởi adapter; compiler không thể tự biết giá trị thô được đo bằng kg hay m.
- Khi phải lưu/kiểm tra đơn vị ở runtime, nên chứa thêm **unit token**, enum hoặc một value object rõ ràng thay vì chỉ dựa vào phantom type.

Vì vậy, lựa chọn giữa **Money có Currency runtime** và **Quantity<U> có nhãn generic compile-time** phụ thuộc vào yêu cầu: cần lưu dữ liệu đơn vị thực tế ở đâu, có đổi đơn vị không, và cần tránh nhầm đến mức nào.

### 9.3. Bound không thay thế điều kiện giá trị

**T extends Number** bảo đảm T có một số phương thức số học/công cụ chuyển kiểu, nhưng không kiểm tra:

- Số lượng đặt hàng phải **lớn hơn 0**.
- Phần trăm chiết khấu nằm trong **0–100%**.
- Giá không âm.
- Tiền và số lượng không được cộng.

Các quy tắc này cần được đặt trong **constructor, phương thức miền và ràng buộc DB** phù hợp. Chẳng hạn:

~~~~java
record OrderQuantity(int value) {
    OrderQuantity {
        if (value <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}
~~~~

OrderQuantity là một kiểu miền riêng, vừa ngăn nhầm với một kiểu int có ý nghĩa khác khi API yêu cầu OrderQuantity, vừa buộc giá trị luôn dương khi đối tượng được tạo qua constructor hợp lệ.

## 10. Bảo toàn ngữ nghĩa khi chuyển Java sang SQL

Một **mô hình Java có kiểu mạnh** và một **lược đồ quan hệ có khóa** phải được thiết kế đồng bộ. Type safety của Java kiểm tra **lời gọi và cấu trúc đối tượng**; cơ sở dữ liệu kiểm tra **trạng thái đã ghi, khóa, tham chiếu và cạnh tranh giao dịch**.

### 10.1. Cùng UUID ở SQL nhưng vẫn có ý nghĩa khác nhau

~~~~sql
CREATE TABLE customer (
    id UUID PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE sales_order (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    total NUMERIC(14, 2) NOT NULL CHECK (total >= 0),
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(id)
        ON DELETE RESTRICT
);
~~~~

Từ góc nhìn vật lý:

- customer.id và sales_order.id đều là **UUID**.
- sales_order.customer_id cũng là **UUID** và trỏ tới customer.id.
- DB không tự tạo các class **CustomerId** và **OrderId** của Java; adapter thực hiện ánh xạ những wrapper sang UUID.

Từ góc nhìn Java:

~~~~text
Customer.id       : CustomerId
Order.id          : OrderId
Order.customerId  : CustomerId

CustomerId.value  : UUID
OrderId.value     : UUID
~~~~

**Kiểu Java** ngăn truyền **OrderId** vào một tham số cần **CustomerId**. **FK trong SQL** ngăn chèn một customer_id không tồn tại ở bảng customer (trừ những trường hợp chính sách ràng buộc/trạng thái dữ liệu được thiết kế khác). **PRIMARY KEY** của hai bảng bảo vệ tính duy nhất trong từng quan hệ. Cả hai lớp kiểm tra đều quan trọng.

### 10.2. Một ví dụ ghi JDBC với chuyển đổi có chủ đích

~~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

static void insertOrder(Connection connection, Order order)
        throws SQLException {
    String sql = """
        INSERT INTO sales_order (id, customer_id, total)
        VALUES (?, ?, ?)
        """;
    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setObject(1, order.id().value());
        statement.setObject(2, order.customerId().value());
        statement.setBigDecimal(3, order.total());
        statement.executeUpdate();
    }
}
~~~~

Đây là ví dụ dùng JDBC với driver PostgreSQL hỗ trợ UUID. Trong thực tế, cách bind UUID và ánh xạ kiểu cơ sở dữ liệu cần phù hợp với JDBC driver và chính sách lỗi của ứng dụng.

Điểm quan trọng: adapter gọi **order.id().value()** cho cột id và **order.customerId().value()** cho cột customer_id. Nếu lỗi ánh xạ cố ý lấy **order.id()** để ghi vào customer_id, Java không thể bảo vệ vì tại thời điểm setObject cả hai đã được **tháo wrapper** về UUID. Đó là lý do adapter phải được **kiểm thử mapping** và DB phải giữ FK.

### 10.3. DTO/JSON là biên giới dữ liệu không đáng tin tuyệt đối

Một yêu cầu từ HTTP/JSON thường bắt đầu bằng String:

~~~~java
record CreateOrderRequest(String customerId, String total) {}

static CustomerId parseCustomerId(CreateOrderRequest request) {
    return new CustomerId(
        java.util.UUID.fromString(request.customerId())
    );
}
~~~~

Người dùng có thể gửi chuỗi UUID đúng cú pháp nhưng thuộc **một đối tượng không tồn tại** hoặc không có quyền sử dụng. Vì thế pipeline cần phân biệt:

1. **Parse/validate cấu trúc:** UUID có đúng định dạng không?
2. **Chuyển sang kiểu miền:** CustomerId thay vì String hoặc UUID tự do.
3. **Kiểm tra nghiệp vụ/quyền:** Người tạo đơn có được tạo đơn cho khách đó không?
4. **Bảo đảm ở DB:** FK, khóa và transaction bảo vệ dữ liệu kể cả khi có nhiều yêu cầu đồng thời.

Không thể dựa hoàn toàn vào kiểm tra tồn tại ở Java trước INSERT: trong môi trường đồng thời, bản ghi có thể bị xóa hoặc đổi trạng thái giữa lúc kiểm tra và ghi. Ràng buộc DB và cơ chế giao dịch phù hợp phải là lớp bảo vệ cuối cho tính toàn vẹn tham chiếu.

### 10.4. JPA và framework không tự hiểu semantic wrapper

Ở mức mô hình miền, record CustomerId và OrderId phù hợp để biểu đạt định danh bất biến. Nhưng việc ánh xạ chúng vào cột SQL có thể cần **AttributeConverter, mapping tùy chỉnh hoặc adapter** tùy JPA provider và phiên bản. Không được giả định mọi framework sẽ tự hiểu record ID hoặc generic ID.

Cũng không nên suy ra từ ví dụ record Customer và Order rằng chúng có thể trực tiếp làm **JPA entity chuẩn**: entity JPA thường có các ràng buộc riêng về class, constructor, mutability/proxy và quản lý vòng đời. Một kiến trúc có thể giữ **record làm domain model/DTO** và dùng **persistence entity class riêng** rồi mapping có kiểm chứng giữa hai lớp.

Khi dùng thư viện tạo repository generic, cần xem **kiểu ID trong API thực tế** có bị thu gọn về Object, Serializable, UUID hoặc String không. Nếu có, mô hình ở tầng domain vẫn cần đảm bảo các lời gọi nghiệp vụ không sử dụng sai kiểu.

## 11. ID có phạm vi: tenant và khóa ghép

Một vấn đề thực tế khác là tính duy nhất chỉ đúng trong **một phạm vi nghiệp vụ**. Ví dụ mã phòng **KT** có thể tồn tại ở nhiều tenant khác nhau.

~~~~java
import java.util.Objects;
import java.util.UUID;

record TenantId(UUID value) {
    TenantId {
        Objects.requireNonNull(value);
    }
}

record DepartmentCode(String value) {
    DepartmentCode {
        Objects.requireNonNull(value);
        if (value.isBlank()) {
            throw new IllegalArgumentException("Department code required");
        }
    }
}

record DepartmentKey(TenantId tenantId, DepartmentCode departmentCode) {
    DepartmentKey {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(departmentCode);
    }
}
~~~~

**DepartmentKey** biểu diễn một định danh ghép **(tenantId, departmentCode)**. Nó tránh làm rơi tenantId khi truy xuất phòng ban.

Lược đồ quan hệ tương ứng:

~~~~sql
CREATE TABLE department (
    tenant_id UUID NOT NULL,
    department_code VARCHAR(30) NOT NULL,
    department_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (tenant_id, department_code)
);

CREATE TABLE employee (
    tenant_id UUID NOT NULL,
    employee_code VARCHAR(30) NOT NULL,
    department_code VARCHAR(30) NOT NULL,
    PRIMARY KEY (tenant_id, employee_code),
    FOREIGN KEY (tenant_id, department_code)
        REFERENCES department(tenant_id, department_code)
);
~~~~

**Generic tag của DepartmentId chỉ phân biệt loại thực thể**, còn **DepartmentKey** thể hiện cả **giá trị tenant**. Java không có sẵn cách tĩnh để tạo một type argument riêng cho **mỗi UUID tenant có được lúc chạy**. Vì vậy, để bảo vệ ranh giới tenant, cần lưu tenantId trong khóa và dùng FK ghép, kiểm tra phân quyền/tenant ở dịch vụ và các lớp bảo vệ khác phù hợp.

Sai lầm cần tránh: chỉ dùng **DepartmentCode** (hoặc TaggedId<DepartmentKind>) rồi giả định rằng như vậy đã chứng minh nhân viên thuộc đúng tenant. Kiểu “phòng ban” và **tư cách thành viên của phòng trong tenant cụ thể** là hai lớp thông tin khác nhau.

## 12. Các bẫy thiết kế generic và mô hình Java

| Sai lầm | Tại sao sai | Hướng khắc phục |
| --- | --- | --- |
| Mọi mã đều là UUID, nhưng đặt tên biến khác nhau | Tên biến không phải rào chắn kiểu khi gọi phương thức | Tạo CustomerId, OrderId và chữ ký có kiểu miền |
| Dùng Repository<E> nhưng ID luôn là UUID | Không phân biệt UUID của các miền | Dùng Repository<E, ID> và ID riêng |
| Nghĩ T extends Number phân biệt tiền với khoảng cách | Bound chỉ bảo đảm năng lực kỹ thuật | Dùng Money, Distance, Quantity hoặc value object phù hợp |
| Dùng generic method cùng T cho hai tham số và cho rằng T phải là cùng class cụ thể | Type inference có thể chọn supertype chung | Cố định kiểu ở API miền hoặc trên generic receiver |
| Dùng List<Object> để gom mọi loại | Mất thông tin loại phần tử, cần cast | Dùng interface chung và wildcard khi chỉ đọc |
| Dùng wildcard extends để thêm mọi loại vào danh sách | Kiểu phần tử cụ thể không biết | Dùng kiểu cụ thể hoặc wildcard super khi làm consumer |
| Dùng kiểu generic ID chỉ có UUID và trông đợi equals phân biệt loại | Type argument bị xóa ở runtime | Record ID riêng hoặc runtime kind trong giá trị |
| Dùng raw types và cast tùy ý | Có thể vượt qua type checking, gây lỗi muộn | Loại bỏ raw types và cô lập chuyển đổi không an toàn |
| Nghĩ record tự bất biến sâu | Thành phần là mảng/đối tượng mutable vẫn có thể thay đổi | Chọn thành phần bất biến hoặc phòng vệ khi tạo/trả dữ liệu |
| Nghĩ Java type-safe đồng nghĩa customerId tồn tại | Kiểu đúng không chứng minh hàng được tham chiếu có thật | FK ở DB và kiểm tra nghiệp vụ/giao dịch |
| Chỉ dùng một DepartmentCode cho mọi tenant | Không có thông tin phạm vi tenant | Dùng DepartmentKey gồm tenantId và mã phòng |
| Đưa mọi ID vào một Map<Object,Object> | Có thể trộn thực thể, mất ràng buộc kiểu | Kho có E và ID cụ thể, mapping có kiểm chứng |
| Dùng converter tự động nhưng không kiểm thử mapping | Wrapper có thể bị tháo ra và ghi nhầm cột UUID | Kiểm thử JDBC/JPA adapter và ràng buộc DB |
| Biến đổi tiền tệ ngầm bằng phép cộng BigDecimal | Bỏ qua đơn vị, tỷ giá và làm tròn | Dùng Money và cơ chế chuyển đổi có ngữ nghĩa |

### 12.1. Type erasure ảnh hưởng đến overload

Đây là **hai chữ ký không thể cùng tồn tại** trong một lớp Java:

~~~~java
// void handle(List<CustomerId> ids) { ... }
// void handle(List<OrderId> ids) { ... }
// Lỗi biên dịch do cùng erasure của tham số: List.
~~~~

Vì type argument bị xóa khi tạo chữ ký runtime, hai overload trên có **name clash**. Thay vào đó:

~~~~java
void handleCustomers(List<CustomerId> ids) { /* ... */ }
void handleOrders(List<OrderId> ids) { /* ... */ }
~~~~

Hoặc dùng một interface xử lý generic có type parameter được cố định theo từng triển khai và **một tên phương thức**, nếu nghiệp vụ cần cùng quy trình cho nhiều miền.

Khác với hai overload List generic, các overload theo wrapper **trực tiếp** là hợp lệ:

~~~~java
void load(CustomerId id) { /* ... */ }
void load(OrderId id) { /* ... */ }
~~~~

Ở đây CustomerId và OrderId là **hai class runtime khác nhau**, không bị type erasure xóa thành UUID.

### 12.2. Không dùng instanceof với type argument cụ thể

~~~~java
Object value = new ArrayList<CustomerId>();

if (value instanceof List<?>) {
    // Chỉ chứng minh đây là List, chưa chứng minh phần tử là CustomerId.
}
~~~~

Khi nhận dữ liệu từ framework có kiểu tổng quát, phải kiểm tra từng phần tử hoặc dùng một bộ giải mã nhận **thông tin kiểu cụ thể**. Một unchecked cast từ Object sang List<CustomerId> không biến nội dung sai thành đúng.

### 12.3. Mô hình miền không phải bản sao 1:1 của bảng

Không nhất thiết mỗi cột SQL thành một class Java riêng, cũng không nhất thiết mọi value object có một bảng riêng. Ví dụ:

~~~~text
Java:
  OrderId(UUID)
  CustomerId(UUID)
  Order(id: OrderId, customerId: CustomerId, total: BigDecimal)

SQL:
  sales_order(id UUID PK, customer_id UUID FK, total NUMERIC)
~~~~

Hai value object ID có thể cùng ánh xạ về **hai cột UUID**. Ngược lại, một **DepartmentKey** gồm TenantId và DepartmentCode có thể ánh xạ về **hai cột PK ghép**.

Điều quan trọng là giữ nguyên **ý nghĩa** và **ràng buộc**, không phải bắt số class bằng số bảng hay kiểu Java bằng đúng một kiểu SQL.

## 13. Lựa chọn mức bảo vệ kiểu phù hợp

Không phải dự án nào cũng cần cùng mức độ tổng quát. Một ma trận lựa chọn:

| Tình huống | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Chỉ vài loại ID riêng biệt | CustomerId, OrderId dạng record riêng | Dễ đọc, compiler và equals đều phân biệt |
| Nhiều thực thể dùng cùng quy trình CRUD | Repository<E extends Identified<ID>, ID> | Tái sử dụng thuật toán mà giữ cặp thực thể–ID |
| Hàng chục loại ID và cần một cơ chế chung | TaggedId<K> có runtime kind hoặc wrapper riêng | Kiểm soát type erasure và equality |
| Kiểu số có đơn vị hiển thị/đổi đơn vị lúc chạy | Money/Currency hoặc value object chứa unit | Đơn vị là dữ liệu runtime phải được kiểm tra |
| Đơn vị cố định theo từng API, cần chống trộn lúc biên dịch | Quantity<U> với unit tag | Type parameter bảo vệ phép toán trên cùng loại |
| Tập hợp nhiều subtype chỉ để đọc | List<? extends InterfaceChung> | Có thể đọc năng lực chung mà không cho thêm phần tử tùy ý |
| Tập hợp cần nhận thêm một subtype | List<? super Subtype> | Có thể thêm Subtype an toàn |
| ID có phạm vi tenant | Composite value object chứa TenantId + mã | Phạm vi là giá trị dữ liệu, không chỉ loại tĩnh |
| API bên ngoài gửi String/UUID | Parse/validate tại boundary rồi tạo value object | Không để dữ liệu thô lan vào domain |
| Quan hệ giữa thực thể ở database | FK/UNIQUE/NOT NULL và giao dịch | Kiểu Java không ngăn dữ liệu sai từ giao dịch khác |

**Ưu tiên độ rõ ràng:** Nếu phải tạo hàng chục loại phantom type, converter và factory khiến code khó hiểu hơn yêu cầu nghiệp vụ, hãy cân nhắc **record ID riêng** hoặc một value object đơn giản. Mục tiêu không phải generic hóa tối đa, mà là **bất biến nghiệp vụ nào có thể được biểu diễn bằng kiểu thì nên để compiler hỗ trợ kiểm tra**.

## 14. Quy trình đưa type safety vào một mô hình dữ liệu Java

1. **Liệt kê những giá trị cùng kiểu kỹ thuật nhưng khác ý nghĩa.** Ví dụ CustomerId, OrderId, ProductId đều là UUID; số tiền và khối lượng đều dùng số.
2. **Xác định ranh giới nghiệp vụ.** Ở đâu một OrderId không được phép thay CustomerId? Ở đâu cần biết tiền tệ hay tenant?
3. **Tạo value object có tên miền riêng** cho các định danh hoặc giá trị cần chống trộn; đưa điều kiện bất biến cơ bản vào constructor.
4. **Viết chữ ký API bằng kiểu miền** thay vì String/UUID tự do; dùng constructor/factory đổi từ raw value chỉ tại boundary.
5. **Tách phần có thể tái sử dụng** thành generic class/method; dùng bound để diễn đạt năng lực bắt buộc, ví dụ E extends Identified<ID>.
6. **Khóa type argument trong các API thao tác ghi.** Repository<Order, OrderId> không nhận Customer; hạn chế wildcard, raw và Object trong vùng nghiệp vụ.
7. **Dùng wildcard có chủ đích** cho các thuật toán chỉ đọc, ghi hoặc tổng quát qua nhiều loại thực thể; nhớ PECS.
8. **Xem xét runtime behavior**: type erasure, equals/hashCode, serialization, reflection và dấu hiệu generic ID thiếu runtime tag.
9. **Thiết kế lược đồ SQL tương ứng**: PK, FK, UNIQUE, NOT NULL và composite key đúng với domain type.
10. **Kiểm tra adapter** từ HTTP/JSON, JDBC/JPA, queue/event và cache; đây là nơi có thể làm mất type argument hoặc tháo wrapper về primitive.
11. **Viết kiểm thử sai kiểu và sai dữ liệu.** Các lời gọi sai cần bị compiler từ chối; trường hợp sai tham chiếu ở DB cần bị FK chặn; converter phải gán đúng cột.
12. **Đánh giá tiến hóa mô hình.** Khi đổi khóa ID, thêm tenant hoặc đơn vị tiền, type safety nên khiến các vị trí cần sửa hiện ra thành lỗi biên dịch có ý nghĩa, thay vì cho phép sai âm thầm.

### Sơ đồ các lớp bảo vệ

~~~~mermaid
flowchart TD
    A["HTTP / JSON / thông điệp ngoài"] --> B["Parse + xác thực dữ liệu đầu vào"]
    B --> C["Value object: CustomerId / OrderId / Money"]
    C --> D["Domain API và Repository có generics + bounds"]
    D --> E["Adapter JDBC / JPA chuyển đổi kiểu"]
    E --> F["SQL PK / FK / UNIQUE / CHECK + giao dịch"]
    F --> G["Trạng thái dữ liệu đã lưu"]
    F -- "Lỗi ràng buộc" --> H["Xử lý lỗi nghiệp vụ"]
~~~~

Trong sơ đồ, **mọi lớp đều có một nhiệm vụ kiểm chứng riêng**:

- Boundary parse kiểu dữ liệu và định dạng đầu vào.
- Value object và generic API chống trộn loại dữ liệu trong mã Java.
- Adapter giữ phép ánh xạ có ý nghĩa.
- Database kiểm tra ràng buộc giữa các hàng và nhiều giao dịch.

Không nên bỏ một lớp chỉ vì đã có lớp khác. Một API Java dùng CustomerId chính xác vẫn có thể gửi ID khách không tồn tại; ngược lại, FK của SQL không khiến các lời gọi UUID bị tráo tham số tự trở thành rõ nghĩa.

## 15. Bài tập thực hành có đáp án

### Bài 1 — Compiler có phát hiện tráo UUID không?

Cho:

~~~~java
void updateCustomer(UUID orderId, UUID customerId) {}
~~~~

Một người gọi updateCustomer(customerId, orderId).

**Câu hỏi:** Compiler có báo lỗi không? Cách sửa mô hình?

**Đáp án:** Không; cả hai đối số đều là UUID. Đổi chữ ký thành **updateCustomer(OrderId orderId, CustomerId customerId)** và dùng record ID riêng. Khi đó hai tham số bị tráo sẽ tạo lỗi biên dịch.

### Bài 2 — List<String> đã phân biệt mã khách và mã sản phẩm?

Cho List<String> customerCodes và List<String> productCodes.

**Câu hỏi:** Câu customerCodes.add(productCodes.get(0)) có biên dịch không?

**Đáp án:** Có. Generic chỉ biết cả hai chứa String. Muốn bảo vệ ngữ nghĩa, dùng **List<CustomerCode>** và **List<ProductCode>** với hai kiểu riêng. Khi đó phần tử ProductCode không được chèn trực tiếp vào danh sách CustomerCode.

### Bài 3 — Bound cho repository

Cho giao diện:

~~~~java
interface Identified<ID> {
    ID id();
}
~~~~

**Câu hỏi:** Hãy khai báo repository có hai tham số E và ID sao cho entity.id() trả về ID; viết phương thức findById.

**Đáp án tham khảo:**

~~~~java
interface RepositoryContract<E extends Identified<ID>, ID> {
    java.util.Optional<E> findById(ID id);
    void save(E entity);
}
~~~~

Giới hạn **E extends Identified<ID>** kết nối kiểu thực thể và kiểu khóa. Tuy nhiên, nếu mọi ID đều là UUID, cần bổ sung kiểu miền riêng để phân biệt ngữ nghĩa.

### Bài 4 — Mục tiêu của multiple bounds

Cho phương thức:

~~~~java
static <T extends Number & Comparable<T>> T max(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~~

**Câu hỏi:** Hai giới hạn bảo đảm điều gì? Có cấm truyền giá tiền thay cho số lượng không?

**Đáp án:** Number quy định T là một kiểu số; Comparable<T> cho phép so sánh hai giá trị kiểu T. Chúng **không** phân biệt giá tiền và số lượng nếu hai miền vẫn dùng cùng kiểu kỹ thuật, ví dụ BigDecimal. Cần Money, Quantity hoặc value object tương ứng.

### Bài 5 — Vì sao generic method cùng T vẫn nhận hai loại ID?

~~~~java
static <T> void pair(T a, T b) {}

pair(new CustomerId(UUID.randomUUID()),
     new OrderId(UUID.randomUUID()));
~~~~

**Câu hỏi:** Có nhất thiết phát sinh lỗi biên dịch vì CustomerId khác OrderId không?

**Đáp án:** Không. Compiler có thể suy diễn **T là một supertype chung** của hai đối số. Nếu hai tham số phải cùng một loại ID cụ thể, hãy cố định kiểu tại API nghiệp vụ (ví dụ OrderId và OrderId) thay vì suy diễn T từ cả hai đối số.

### Bài 6 — Invariance của Java generics

~~~~java
List<Order> orders = new ArrayList<>();
// List<Object> objects = orders;
~~~~

**Câu hỏi:** Vì sao phép gán bị cấm dù Order là Object?

**Đáp án:** List<Order> **không** là subtype của List<Object> vì generic bất biến. Nếu phép gán được cho phép, người dùng có thể thêm Customer vào List<Object> thực chất đang là List<Order>, phá vỡ tính đúng của danh sách.

### Bài 7 — Chọn extends hay super

Một hàm cần đọc id của mọi thực thể triển khai Identified. Hàm khác cần thêm Customer vào một danh sách đích.

**Câu hỏi:** Wildcard nào phù hợp?

**Đáp án:** Để đọc, dùng **List<? extends Identified<?>>**. Để thêm Customer, dùng **List<? super Customer>**. Đây là nguyên tắc PECS. Nếu cả đọc và ghi cùng loại cụ thể, dùng List<Customer> sẽ rõ hơn.

### Bài 8 — Type erasure và equals

~~~~java
record NaiveId<T>(UUID value) {}

UUID shared = UUID.randomUUID();
NaiveId<Customer> a = new NaiveId<>(shared);
NaiveId<Order> b = new NaiveId<>(shared);
~~~~

**Câu hỏi:** a.equals(b) có thể là true không? Giải thích.

**Đáp án:** **Có; với record trên, kết quả là true.** Runtime chỉ thấy cùng loại record NaiveId với cùng giá trị UUID. Type argument bị erasure và không thuộc cấu trúc record. Có thể dùng record ID riêng hoặc thêm runtime kind vào generic ID.

### Bài 9 — Java có thay được FK của SQL không?

Một phương thức nhận OrderId và CustomerId đúng kiểu, nhưng CustomerId chứa UUID của khách không có trong database.

**Câu hỏi:** Có thể INSERT đơn thành công không, nếu customer_id NOT NULL có FK?

**Đáp án:** Nếu không có khách phù hợp, **INSERT bị FK từ chối**. CustomerId đúng kiểu chỉ bảo vệ rằng đây là **loại mã khách**, không chứng minh mã đó **tồn tại**. Java type safety và FK là hai ràng buộc bổ sung.

### Bài 10 — ID theo tenant

Một phòng có mã KT trong tenant A và cũng có mã KT trong tenant B.

**Câu hỏi:** Chỉ dùng DepartmentCode("KT") có định danh được đúng phòng không? Thiết kế khóa nào phù hợp?

**Đáp án:** Không; mã chỉ duy nhất trong tenant. Dùng **DepartmentKey(TenantId, DepartmentCode)** ở Java và **PRIMARY KEY(tenant_id, department_code)** cùng FK ghép ở SQL nếu các quan hệ tham chiếu phải giữ đúng tenant.

### Bài 11 — Đổi tiền trong API

~~~~java
Money vnd = new Money(new BigDecimal("100000"), Currency.getInstance("VND"));
Money usd = new Money(new BigDecimal("10"), Currency.getInstance("USD"));
~~~~

**Câu hỏi:** vnd.plus(usd) có bị compiler cấm không? Có nên cộng trực tiếp không?

**Đáp án:** **Không bị compiler cấm**, vì cả hai cùng kiểu Money; nhưng phương thức plus trong ví dụ **từ chối khi chạy** do khác Currency. Không nên cộng trực tiếp tiền khác đơn vị; cần bước chuyển đổi có tỷ giá, thời điểm và quy tắc làm tròn rõ ràng.

### Bài 12 — Kiểm thử ranh giới JDBC

Trong domain, Order.id() là OrderId còn Order.customerId() là CustomerId. Khi ghi database, adapter tháo cả hai wrapper thành UUID.

**Câu hỏi:** Vì sao vẫn cần kiểm thử mapping và FK?

**Đáp án:** Vì ở biên giới JDBC, hai giá trị đều trở về UUID; một lỗi ánh xạ có thể lấy sai value() cho cột customer_id mà compiler không nhận ra. Kiểm thử mapping bảo đảm cột đúng; **FK** bảo đảm giá trị được tham chiếu tồn tại.

### Bài 13 — Overload theo type argument

Một lớp định nghĩa hai phương thức handle(List<CustomerId>) và handle(List<OrderId>).

**Câu hỏi:** Java có cho phép overload này không?

**Đáp án:** Không. Hai phương thức có cùng tên và cùng **erasure** tham số List, gây name clash. Dùng tên khác nhau hoặc tổ chức API generic theo một kiểu đã cố định, hoặc overload trực tiếp bằng hai record CustomerId và OrderId (không bọc List generic).

### Bài 14 — Khi nào generic không cần thiết?

Một ứng dụng chỉ có ba loại ID, mỗi loại chứa UUID. Nhóm đề xuất tạo một hệ thống kiểu generic nhiều tầng với factory, reflection và nhiều annotation.

**Câu hỏi:** Có nhất thiết phải dùng một generic ID framework không?

**Đáp án:** Không. **Ba record CustomerId, OrderId, ProductId** thường rõ ràng, đơn giản, phân biệt được cả lúc compile lẫn so sánh runtime. Chỉ đầu tư generic framework khi mức độ dùng lại, số loại định danh và yêu cầu tích hợp thực sự xứng đáng với độ phức tạp.

## 16. Tổng kết

| Khái niệm | Quy tắc ghi nhớ |
| --- | --- |
| **Generic type** | Tham số hóa kiểu, ví dụ Repository<E, ID>, List<CustomerId> |
| **Upper bound** | Giới hạn type argument vào nhóm có hợp đồng, ví dụ E extends Identified<ID> |
| **Multiple bounds** | Kết hợp lớp và interface, ví dụ T extends Number & Comparable<T> |
| **Kiểu miền riêng** | CustomerId khác OrderId dù cùng chứa UUID |
| **Generic không tự tạo ngữ nghĩa** | Repository<E, UUID> vẫn cho phép ID sai miền nếu hai miền cùng UUID |
| **Generic method type inference** | Cùng T ở hai tham số có thể được suy diễn thành một supertype chung |
| **Invariance** | List<Order> không phải List<Object> |
| **PECS** | Đọc: ? extends; ghi: ? super |
| **Type erasure** | Type argument phần lớn không còn ở runtime |
| **Tagged ID** | Có thể thêm runtime kind để phân biệt generic ID khi equals |
| **Value object** | Chứa ý nghĩa và bất biến miền, như Money hoặc DepartmentKey |
| **Java type safety** | Ngăn gọi sai kiểu trong code có kiểm tra kiểu |
| **PK/FK/UNIQUE ở DB** | Bảo vệ tính duy nhất và tham chiếu của dữ liệu đã lưu, kể cả nhiều giao dịch |
| **Boundary mapping** | JSON/JDBC/ORM phải chuyển dữ liệu thô sang/ra khỏi kiểu miền chính xác |

**Kết luận:** Generics và giới hạn kiểu giúp tái sử dụng thuật toán mà vẫn giữ hợp đồng kiểu, nhưng **chỉ phát huy đầy đủ khi những khác biệt nghiệp vụ quan trọng đã được biểu diễn bằng kiểu Java riêng**. Với mã khách, mã đơn, đơn vị đo hoặc khóa theo tenant, hãy chọn value object rõ nghĩa, dùng generic bound để kết nối các kiểu phù hợp và dùng wildcard theo mục đích đọc/ghi. Cuối cùng, luôn bảo vệ những bất biến không thể chứng minh bằng compiler—sự tồn tại của bản ghi, tính duy nhất, liên kết và tranh chấp đồng thời—bằng ràng buộc và giao dịch tại cơ sở dữ liệu. Thiết kế như vậy giúp mô hình Java và lược đồ quan hệ cùng dễ đọc, kiểm chứng và tiến hóa.
