# Thiết kế API nhỏ, nhất quán và dễ mở rộng

Trong Java 27, một **API (Application Programming Interface)** là tập hợp các kiểu, phương thức, constructor và hợp đồng hành vi mà một thành phần cung cấp cho mã khác sử dụng. API có thể nằm trong một thư viện công khai, giữa các module hoặc ngay giữa các package trong cùng ứng dụng.

Một API được thiết kế tốt không phải là API có thật nhiều phương thức. Nó cung cấp **đúng những khả năng cần thiết**, với tên gọi rõ ràng, quy tắc nhất quán và ranh giới đủ ổn định để bên trong có thể thay đổi mà không buộc người dùng phải sửa mã. Trong thiết kế hướng đối tượng, điều đó thường đạt được bằng **đóng gói (encapsulation)**, **trừu tượng hóa (abstraction)**, **đa hình**, và lựa chọn hợp lý giữa **kế thừa** với **composition**.

Bài viết tập trung vào các kỹ thuật hiện hành của Java 27: kiểu dữ liệu và phương thức phù hợp, interface, record, sealed type, generic, kiểm tra dữ liệu, quản lý thay đổi API và kiểm thử hợp đồng. Các ví dụ sử dụng cú pháp Java đã được hỗ trợ ổn định; không phụ thuộc vào API lỗi thời hay tính năng preview.

## 1. API nhỏ nghĩa là gì?

**API surface** là phần mã mà người sử dụng thành phần có thể nhìn thấy và phụ thuộc vào. Nó bao gồm nhiều thứ hơn số lượng phương thức công khai:

- Tên và chữ ký (signature) của lớp, interface, method và constructor.
- Kiểu tham số, kiểu trả về, generic type parameter và modifier truy cập.
- Các điều kiện hợp lệ của đầu vào, ý nghĩa đầu ra và các ngoại lệ có thể phát sinh.
- Hợp đồng về trạng thái, thứ tự, tính bất biến và khả năng sử dụng đồng thời, nếu có.
- Những hành vi người dùng có thể quan sát và dựa vào khi viết chương trình.

API **nhỏ** là API chỉ để lộ tập khả năng cần thiết cho người gọi. Nó không có nghĩa là cố ép mọi thao tác vào một phương thức duy nhất hoặc giấu đi các khái niệm quan trọng.

Ví dụ, một dịch vụ gửi thông báo chỉ cần công khai khả năng gửi:

~~~java
interface NotificationSender {
    void send(Notification notification);
}
~~~

Người gọi không cần biết dịch vụ đang dùng HTTP client nào, mở connection như thế nào, hoặc lưu thống kê bằng cấu trúc dữ liệu nào. Những chi tiết đó nên nằm trong phần triển khai.

Ngược lại, một API phơi bày các thao tác nội bộ như **openSocket()**, **buildHttpHeaders()**, **flushQueue()**, **closeInternalConnection()** sẽ khiến người sử dụng phụ thuộc vào quy trình triển khai, ngay cả khi nhu cầu của họ chỉ là gửi thông báo.

### Tác động của API surface lớn

Mỗi thành viên công khai tạo thêm một quyết định mà người gọi phải hiểu và một hợp đồng mà người phát triển có trách nhiệm duy trì. Khi API quá rộng:

- Khó tìm được phương thức đúng cho công việc cần làm.
- Nhiều cách làm tương tự dễ gây mâu thuẫn hành vi.
- Thay đổi bên trong có thể ảnh hưởng tới người dùng bên ngoài.
- Kiểm thử và tài liệu phải bao phủ nhiều trường hợp hơn.
- Một chi tiết triển khai vô tình trở thành phụ thuộc lâu dài.

Nguyên tắc thực hành: **công khai hành vi thiết yếu, giữ chi tiết triển khai ở phạm vi hẹp nhất hợp lý**.

## 2. Bắt đầu từ trường hợp sử dụng thay vì từ cấu trúc dữ liệu

Trước khi viết lớp, hãy mô tả những hành động mà người gọi thực sự cần. Chẳng hạn một hệ thống quản lý đơn hàng cần:

1. Tạo yêu cầu mua hàng có dữ liệu hợp lệ.
2. Tra cứu đơn hàng bằng mã định danh.
3. Hủy đơn hàng nếu trạng thái cho phép.

API có thể được phác thảo theo ngôn ngữ nghiệp vụ:

~~~java
interface OrderService {
    OrderId place(CreateOrderRequest request);

    java.util.Optional<OrderView> findById(OrderId id);

    void cancel(OrderId id);
}
~~~

**OrderService** là hợp đồng theo hành vi. Nó không yêu cầu người dùng trực tiếp thao tác với database session, SQL query hoặc cache entry.

Các kiểu như **OrderId**, **CreateOrderRequest** và **OrderView** ở đây là những kiểu miền nghiệp vụ do ứng dụng định nghĩa. Chúng giúp diễn đạt đầu vào và kết quả cụ thể thay vì lạm dụng một danh sách tham số rời rạc.

Không nhất thiết phải tạo một interface cho mọi lớp. Nếu một thành phần chỉ có một triển khai, chưa cần nhiều cách thay thế và không có ranh giới phụ thuộc cần tách, một lớp concrete với API nhỏ có thể đủ đơn giản.

### Tính kết dính (cohesion)

Các phương thức của một lớp nên phục vụ cùng một trách nhiệm có liên quan rõ ràng. Ví dụ, **OrderService** không nên kiêm gửi email quảng cáo, xuất báo cáo nhân sự và quản lý kết nối mạng. Khi trách nhiệm tách biệt, API sẽ dễ đặt tên, kiểm thử và thay đổi hơn.

Tuy nhiên, không nên chia nhỏ máy móc đến mức mỗi thao tác chỉ còn một lớp khó tìm kiếm. Ranh giới hợp lý được xác định theo nhu cầu thực tế và sự thay đổi của miền nghiệp vụ.

## 3. Dùng modifier truy cập để giữ ranh giới rõ ràng

Trong Java, phạm vi truy cập của thành viên quyết định mã nguồn nào có thể sử dụng trực tiếp thành viên đó.

| Mức truy cập | Ý nghĩa thực hành |
|---|---|
| **public** | Thành viên được cung cấp cho những mã có thể truy cập kiểu khai báo, còn chịu quy tắc package và module |
| **protected** | Thành viên mở cho mã trong cùng package và lớp con theo quy tắc của Java |
| Không ghi modifier (package-private) | Chỉ mã cùng package có thể truy cập trực tiếp |
| **private** | Giữ thành viên trong ranh giới truy cập private của kiểu khai báo |

Ví dụ:

~~~java
public final class TicketCounter {
    private int nextNumber = 1;

    public int issue() {
        return nextNumber++;
    }

    int peekNextNumberForPackageUse() {
        return nextNumber;
    }
}
~~~

**issue()** là hành vi công khai; **nextNumber** là trạng thái private. Phương thức package-private chỉ phục vụ mã cùng package, không trở thành phần API công khai. Ví dụ giả định một luồng thực thi; lớp này chưa cam kết an toàn khi có nhiều luồng gọi đồng thời.

### Cẩn trọng với protected

Một **protected** method có thể trở thành điểm mở rộng mà lớp con của người dùng dựa vào. Điều này tạo ràng buộc lâu dài: việc sửa đổi hoặc loại bỏ method có thể phá vỡ lớp con bên ngoài.

Chỉ dùng **protected** khi thực sự thiết kế một hợp đồng kế thừa. Nếu không chủ định cho phép thay đổi hành vi qua kế thừa, nên giữ method **private** hoặc package-private; có thể dùng **final** cho lớp hoặc phương thức khi cần ngăn ghi đè.

### Public trong hệ thống module

Với Java Platform Module System (JPMS), một lớp **public** trong module có tên không tự động trở nên truy cập được từ mọi module. Package chứa API cần được xuất bằng khai báo **exports** phù hợp và module sử dụng phải đọc được module cung cấp.

Ví dụ mô tả trong tệp **module-info.java** của module cung cấp:

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

Package **com.example.orders.internal** không được xuất nên không trở thành API công khai giữa các module theo cách truy cập thông thường, dù có lớp được khai báo **public** bên trong. Chi tiết triển khai vẫn có thể thay đổi trong module mà không phải xuất toàn bộ package.

## 4. Đặt tên nhất quán và chọn chữ ký dễ hiểu

Tên phương thức nên mô tả điều nó thực hiện, không để người dùng phải đoán cách dùng.

Ví dụ:

~~~java
interface Inventory {
    boolean contains(String sku);

    int availableQuantity(String sku);

    void reserve(String sku, int quantity);
}
~~~

Ba tên trên phản ánh rõ ý nghĩa: kiểm tra tồn tại, lấy số lượng khả dụng và đặt giữ hàng.

Tránh API gồm nhiều phương thức cùng mục đích nhưng khác cách đặt tên như **getQuantity()**, **quantityOf()**, **loadQuantity()** nếu chúng không có khác biệt rõ ràng. Sự nhất quán giúp người dùng dự đoán API còn lại từ những phương thức đã biết.

### Tránh tham số boolean khó đọc

Lời gọi dưới đây không thể hiện rõ ý nghĩa tham số cuối:

~~~java
// API khó hiểu tại vị trí gọi:
send(message, true);
~~~

Nếu cờ thể hiện một lựa chọn nghiệp vụ, một enum diễn đạt rõ hơn:

~~~java
enum DeliveryPriority {
    NORMAL,
    URGENT
}

interface DeliveryService {
    void send(String message, DeliveryPriority priority);
}
~~~

Lời gọi:

~~~java
service.send("Your order is ready", DeliveryPriority.URGENT);
~~~

Không phải mọi tham số boolean đều sai. Nếu tên method và ý nghĩa của cờ đã rất rõ thì boolean có thể phù hợp. Dùng enum khi cần thể hiện một lựa chọn quan trọng hoặc có khả năng thêm lựa chọn trong tương lai.

### Tránh overload dễ gây nhầm

Overloading dùng cùng tên method với danh sách tham số khác nhau. Nó hợp lý khi các phiên bản thực sự làm cùng một việc, nhưng quá nhiều overload có thể tạo lời gọi khó hiểu, nhất là với **null**, generic hoặc tự động boxing/unboxing.

~~~java
void log(String message) {
    System.out.println(message);
}

void log(Throwable error) {
    System.out.println(error);
}
~~~

Lời gọi **log(null)** trong ví dụ này bị nhập nhằng ở thời điểm biên dịch vì cả hai overload đều nhận được **null** và không kiểu nào cụ thể hơn kiểu còn lại.

Một API dễ dùng có thể chọn tên rõ ràng như **logMessage(String)** và **logError(Throwable)** nếu hai thao tác có ngữ nghĩa khác nhau. Không nên tạo overload chỉ để tiết kiệm vài ký tự.

## 5. Thiết kế hợp đồng dữ liệu và bảo vệ bất biến

Một API nên thể hiện trạng thái hợp lệ của dữ liệu ngay tại điểm tạo hoặc điểm tiếp nhận. Nếu một đối tượng luôn yêu cầu mã sản phẩm không rỗng và số lượng dương, hãy thể hiện các điều kiện đó trong constructor hoặc factory.

**Record** phù hợp với kiểu dữ liệu truyền tải có cấu trúc cố định. Ví dụ:

~~~java
import java.util.Objects;

public record OrderLine(String sku, int quantity) {
    public OrderLine {
        Objects.requireNonNull(sku, "sku");

        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}
~~~

Record trên có hai component **sku**, **quantity**. Java cung cấp các accessor tương ứng như **sku()**, **quantity()**, cùng **equals()**, **hashCode()** và **toString()** dựa trên trạng thái record.

Phần **public OrderLine { ... }** là compact canonical constructor, cho phép kiểm tra dữ liệu trước khi các component field được gán tự động.

~~~java
OrderLine line = new OrderLine("BOOK-01", 3);

System.out.println(line.sku());      // BOOK-01
System.out.println(line.quantity()); // 3
~~~

Lời gọi **new OrderLine("", 3)** bị từ chối bằng **IllegalArgumentException**, thay vì tạo ra một giá trị không hợp lệ để các bước sau phải xử lý.

### Không lạm dụng kiểu nguyên thủy hoặc String cho mọi khái niệm

Nếu nhiều tham số cùng kiểu nhưng khác ngữ nghĩa, rất dễ truyền sai thứ tự:

~~~java
// Cả hai đều là String nên có thể bị đảo lẫn tại điểm gọi:
void transfer(String senderAccount, String recipientAccount);
~~~

Với miền nghiệp vụ đủ quan trọng, có thể định nghĩa kiểu đại diện riêng, chẳng hạn **AccountId**, để kiểm tra dữ liệu và giúp chữ ký nói rõ ý nghĩa. Việc thêm kiểu mới nên cân bằng với độ phức tạp thực tế; không cần biến mọi String thành một record.

### Kiểm tra đầu vào ở ranh giới API

Trong Java, **Objects.requireNonNull()** hữu ích để từ chối tham chiếu null nếu đó là dữ liệu không hợp lệ. Dùng **IllegalArgumentException** cho giá trị đối số không đáp ứng điều kiện nghiệp vụ; dùng **IllegalStateException** khi thao tác không hợp lệ ở trạng thái hiện tại của đối tượng.

Quy tắc ngoại lệ nên nhất quán và được mô tả rõ để người gọi biết trường hợp nào là lỗi lập trình, trường hợp nào là kết quả nghiệp vụ có thể xảy ra bình thường.

## 6. Không để lộ trạng thái thay đổi được

Một API có vẻ đơn giản nhưng lại trả về collection nội bộ có thể vô tình cho phép mã bên ngoài thay đổi trạng thái của đối tượng.

Ví dụ không nên dùng làm API công khai:

~~~java
import java.util.ArrayList;
import java.util.List;

class UnsafeCart {
    private final List<String> items = new ArrayList<>();

    public List<String> items() {
        return items; // Trả trực tiếp tham chiếu nội bộ.
    }
}
~~~

Mã bên ngoài có thể gọi **cart.items().clear()** và thay đổi trạng thái của cart mà không qua quy tắc của lớp.

Có thể trả về một bản snapshot không sửa được bằng **List.copyOf()**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

class Cart {
    private final List<String> items = new ArrayList<>();

    public void add(String sku) {
        items.add(Objects.requireNonNull(sku, "sku"));
    }

    public List<String> items() {
        return List.copyOf(items);
    }
}
~~~

Lời gọi **items()** trả về một danh sách không cho phép sửa các phần tử qua API của danh sách trả về. Danh sách snapshot cũng không phản ánh những thay đổi sau đó của **items** trong cart.

Cần nhớ:

- **List.copyOf()** tạo danh sách không sửa được, nhưng không tự động sao chép sâu các đối tượng phần tử.
- Trong ví dụ trên, phần tử là **String** (bất biến), nên không có nguy cơ thay đổi trạng thái từng phần tử.
- Nếu phần tử là đối tượng có thể thay đổi trạng thái, việc sao chép danh sách không tự làm các đối tượng phần tử bất biến.
- **List.copyOf()** không chấp nhận phần tử null; API nên xác định rõ chính sách null.
- Không nên ngầm coi ví dụ **Cart** ở trên là thread-safe; việc đồng bộ truy cập là một hợp đồng khác.

**Record** có các component field final, nhưng không tự động bảo đảm bất biến sâu. Một record chứa **List** có thể dùng canonical constructor để sao chép phòng vệ:

~~~java
import java.util.List;

public record OrderRequest(List<OrderLine> lines) {
    public OrderRequest {
        lines = List.copyOf(lines);
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Order must contain lines");
        }
    }
}
~~~

Ở đây, **OrderLine** là record chứa **String** và **int**. Nhờ các phần tử đó bất biến, bản danh sách mới cũng tránh được nguy cơ thay đổi trạng thái phần tử trong ví dụ cụ thể.

## 7. Phụ thuộc vào abstraction, dùng composition khi phù hợp

Để API dễ mở rộng, một thành phần có thể định nghĩa **interface** cho khả năng biến đổi theo từng triển khai và sử dụng **composition** để kết hợp chúng.

~~~java
interface PaymentGateway {
    void charge(String paymentId, long amountInCents);
}

final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = java.util.Objects.requireNonNull(gateway);
    }

    void checkout(String paymentId, long amountInCents) {
        if (amountInCents <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }

        gateway.charge(paymentId, amountInCents);
    }
}
~~~

**CheckoutService** không kế thừa từ một cổng thanh toán cụ thể. Nó nhận một đối tượng triển khai **PaymentGateway** và gọi khả năng **charge()** qua hợp đồng chung. Có thể thay cổng thanh toán thật bằng một fake trong kiểm thử mà không thay đổi mã nghiệp vụ của checkout.

### Khi nào nên dùng extends?

**Kế thừa lớp** là phù hợp khi lớp con thực sự là một dạng chuyên biệt của lớp cha và giữ được hợp đồng hành vi của lớp cha. Kế thừa cũng tạo phụ thuộc vào các phương thức có thể ghi đè và hành vi khởi tạo của lớp cha.

Nếu quan hệ chỉ là “sử dụng một thành phần khác”, composition thường diễn đạt đúng hơn.

Ví dụ, **CheckoutService** *có một* **PaymentGateway**. Nó không phải là một loại **PaymentGateway**, nên kế thừa từ gateway chỉ để tái sử dụng mã là lựa chọn không tự nhiên.

Khi thiết kế điểm mở rộng qua kế thừa:

- Xác định rõ những method được phép ghi đè.
- Tránh gọi method có thể ghi đè từ constructor nếu method có thể dùng trạng thái lớp con chưa khởi tạo.
- Không để lộ field **protected** chỉ để lớp con sửa trạng thái trực tiếp.
- Ghi lại những điều kiện mà mọi lớp con phải duy trì.

Nếu không có yêu cầu kế thừa, một lớp **final** có thể giúp duy trì bất biến của lớp và giảm những hợp đồng mở rộng không chủ đích.

## 8. Interface nhỏ, nhưng không chia vụn vô lý

Một interface nên mô tả nhóm hành vi có ý nghĩa đối với một nhóm người sử dụng. Tránh bắt mọi triển khai phải cung cấp các method không liên quan tới trách nhiệm của chúng.

Một interface quá rộng:

~~~java
interface ResourceManager {
    void read();
    void write();
    void delete();
    void printReport();
    void sendNotification();
}
~~~

Một implementation chỉ cần đọc dữ liệu sẽ bị yêu cầu xử lý cả các phương thức không liên quan, dẫn tới các phần triển khai rỗng hoặc ném ngoại lệ “không hỗ trợ”.

Có thể tách theo khả năng nghiệp vụ:

~~~java
interface Reader<T> {
    T read();
}

interface Writer<T> {
    void write(T value);
}
~~~

Một component chỉ cần đọc sẽ phụ thuộc **Reader<T>**; component cần cả đọc và ghi có thể sử dụng cả hai khả năng.

Tuy nhiên, việc chia interface cũng cần có mục đích. Nếu mọi người dùng luôn cần một nhóm method và nhóm này có cùng trách nhiệm, giữ chúng trong một interface thống nhất có thể rõ ràng hơn tách thành hàng loạt interface chỉ có một method.

### Functional interface cho điểm mở rộng nhỏ

Nếu hợp đồng có một abstract method, có thể sử dụng lambda:

~~~java
@FunctionalInterface
interface PriceAdjustment {
    long apply(long originalPriceInCents);
}

PriceAdjustment discount = price -> price * 90 / 100;
~~~

Các interface có một abstract method thích hợp để biểu diễn hàm biến đổi hoặc callback ngắn. Không cần tạo lớp con có tên riêng cho mọi phép biến đổi đơn giản, miễn là lambda vẫn rõ nghĩa.

Khi cần dùng các functional interface chuẩn như **Function**, **Predicate**, **Consumer** hoặc **UnaryOperator**, ưu tiên dùng chúng nếu ngữ nghĩa đã phù hợp. Định nghĩa interface mới khi muốn cung cấp một tên hợp đồng miền nghiệp vụ cụ thể hoặc cần mở rộng hợp đồng đó bằng tài liệu rõ ràng.

## 9. Hợp đồng xử lý null, không tìm thấy và lỗi

API phải xác định rõ kết quả khi dữ liệu không tồn tại, đầu vào không hợp lệ hoặc thao tác thất bại.

Ba trường hợp không nên bị trộn lẫn:

| Tình huống | Ví dụ | Cách biểu diễn khả thi |
|---|---|---|
| Không tìm thấy là kết quả bình thường | Tra cứu mã đơn hàng không tồn tại | **Optional<Order>** hoặc kiểu kết quả miền nghiệp vụ |
| Đầu vào vi phạm điều kiện API | Mã đơn hàng null khi API không cho phép | **NullPointerException** từ kiểm tra non-null, hoặc ngoại lệ phù hợp |
| Thao tác thất bại khi thực thi | Không kết nối được tới dịch vụ lưu trữ | Ngoại lệ có ngữ nghĩa và hợp đồng rõ ràng |

Ví dụ một API tra cứu:

~~~java
import java.util.Optional;

interface OrderLookup {
    Optional<OrderView> findById(OrderId id);
}
~~~

**Optional<OrderView>** biểu diễn rõ khả năng “có hoặc không có kết quả”. Người gọi không phải suy đoán liệu **null** nghĩa là không tìm thấy, lỗi kết nối hay đối tượng chưa được nạp.

Với **Optional**, nên dùng theo hướng biểu diễn kết quả có thể vắng mặt. Không bắt buộc phải thay mọi kiểu tham số hay field bằng **Optional**; chọn cách biểu diễn nhất quán với hợp đồng của hệ thống.

### Dùng exception có ý nghĩa

Phương thức API có thể ném ngoại lệ khi người gọi vi phạm tiền điều kiện:

~~~java
void withdraw(long amountInCents) {
    if (amountInCents <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }
    // Thực hiện thao tác nếu đáp ứng các điều kiện khác.
}
~~~

Nếu thiếu tiền là một tình huống nghiệp vụ dự kiến, API có thể cân nhắc kiểu kết quả mô tả thành công/thất bại thay vì chỉ dựa vào một ngoại lệ chung. Quyết định phụ thuộc cách người gọi cần xử lý tình huống đó.

Với API công khai, nên mô tả ngoại lệ quan trọng bằng tài liệu và duy trì hành vi tương đối ổn định. Tránh trả giá trị “đặc biệt” như **-1** hoặc chuỗi rỗng để diễn đạt lỗi nếu giá trị đó có thể bị hiểu là dữ liệu hợp lệ.

### Kiểu kết quả theo miền nghiệp vụ

Khi tập kết quả được xác định rõ, có thể dùng sealed interface và record:

~~~java
sealed interface SaveResult permits Saved, Rejected {}

record Saved(String id) implements SaveResult {}

record Rejected(String reason) implements SaveResult {}
~~~

Người gọi nhận một **SaveResult**, sau đó xử lý theo loại kết quả tương ứng. Cách này hợp lý khi thành công và từ chối là hai nhánh nghiệp vụ bình thường cần được mô hình hóa.

## 10. Chọn kiểu tham số và trả về không ràng buộc quá mức

Một API nên yêu cầu **đúng những khả năng mà nó cần**, thay vì ép người gọi phải tạo một kiểu triển khai cụ thể.

Ví dụ, nếu một method chỉ duyệt các mã hàng, nó không cần bắt buộc **ArrayList<String>**:

~~~java
void printSkus(Iterable<String> skus) {
    for (String sku : skus) {
        System.out.println(sku);
    }
}
~~~

**Iterable<String>** đủ cho mục đích duyệt và cho phép người gọi truyền các kiểu triển khai phù hợp. Nếu method cần biết số lượng phần tử hoặc các thao tác collection khác, **Collection<String>** hay **List<String>** có thể phù hợp hơn.

### Generic và wildcard

Khi method chỉ đọc các phần tử để xử lý, wildcard có thể giúp nhận nhiều kiểu con:

~~~java
class Animal {
    String name() {
        return "Animal";
    }
}

class Dog extends Animal {
    @Override
    String name() {
        return "Dog";
    }
}

static void printNames(
        java.util.Collection<? extends Animal> animals) {
    for (Animal animal : animals) {
        System.out.println(animal.name());
    }
}
~~~

Method này có thể nhận **Collection<Animal>** hoặc **Collection<Dog>**, vì nó chỉ cần đọc phần tử như **Animal**. Với nơi ghi thêm các giá trị kiểu **Animal** vào collection, **? super Animal** có thể là lựa chọn phù hợp.

Nguyên tắc thường được nhắc tới là *producer extends, consumer super* (PECS), nhưng không cần thêm wildcard nếu chúng làm chữ ký khó hiểu hoặc không đem lại tính linh hoạt thực tế.

### Kiểu trả về nên nói rõ cam kết

Nếu một method trả về **List<T>**, người gọi có thể giả định có thứ tự phần tử và quyền truy cập theo chỉ số, nhưng **không được tự suy luận rằng danh sách có thể sửa**. Tài liệu API cần nói rõ collection trả về có thể thay đổi không, là snapshot hay view, và điều gì xảy ra khi dữ liệu nguồn thay đổi.

Đừng chuyển một kiểu triển khai như **ArrayList<T>** thành kiểu trả về công khai chỉ vì đó là cấu trúc hiện đang dùng bên trong. Trả về abstraction phù hợp giúp thay đổi cách lưu trữ mà ít ảnh hưởng người gọi hơn.

## 11. Record, sealed type và giới hạn khả năng mở rộng

Java hiện đại cung cấp nhiều công cụ giúp thể hiện ý định thiết kế hơn là chỉ dùng class thông thường.

| Công cụ | Phù hợp khi | Lưu ý |
|---|---|---|
| **class** | Đối tượng có trạng thái và hành vi, có thể kiểm soát khởi tạo và mức truy cập | Có thể là final hoặc cho phép kế thừa có chủ đích |
| **record** | Dữ liệu dạng giá trị với component cố định | Record là final; bản thân record không bảo đảm bất biến sâu |
| **interface** | Hợp đồng hành vi có thể có nhiều cách triển khai | Hạn chế thêm abstract method vào API đã công khai |
| **sealed class/interface** | Miền kiểu có tập lớp con trực tiếp được kiểm soát | Không phù hợp nếu người dùng phải tự do tạo implementation bên ngoài |
| **final class** | Không dự định cho lớp khác kế thừa | Giảm bề mặt hợp đồng kế thừa |

**Sealed type** hữu ích khi hệ thống muốn đóng tập biến thể một cách có chủ đích, như các trạng thái của một giao dịch. Nhưng nếu mục tiêu chính là cho nhà phát triển bên ngoài viết thêm plugin, một interface mở thường phù hợp hơn.

Hai chiến lược có mục tiêu khác nhau:

- **Mở rộng bằng implementation mới:** định nghĩa interface đủ nhỏ và cho phép các lớp mới triển khai.
- **Kiểm soát mọi biến thể hợp lệ:** dùng sealed type khi miền nghiệp vụ thực sự có một tập biến thể do hệ thống sở hữu.

Không nên dùng **sealed** chỉ vì đó là cú pháp mới, cũng không nên tạo cây kế thừa sâu để mô hình hóa những khác biệt có thể biểu diễn bằng dữ liệu hoặc composition.

## 12. Duy trì khả năng tương thích khi API thay đổi

API dễ mở rộng còn cần đủ ổn định để người gọi có thể nâng cấp phiên bản thư viện hoặc module.

Các loại tương thích thường cần phân biệt:

- **Source compatibility:** mã nguồn của người dùng còn biên dịch được khi dùng API mới hay không.
- **Binary compatibility:** mã đã biên dịch trước đó có thể liên kết với API mới theo các quy tắc tương thích nhị phân của Java hay không.
- **Behavioral compatibility:** hành vi có thể quan sát và hợp đồng nghiệp vụ còn đáp ứng kỳ vọng cũ hay không.

Một thay đổi có thể giữ nguyên chữ ký nhưng phá vỡ hành vi. Ví dụ, method trước đây chấp nhận giá trị rỗng nhưng phiên bản mới từ chối không có lý do có thể khiến chương trình người dùng hoạt động khác đi.

### Thận trọng khi thêm phương thức vào interface

Thêm **abstract method** vào một interface đã được nhiều lớp triển khai có thể khiến các lớp triển khai hiện tại không còn biên dịch với interface mới. Vì thế cần xem xét trước khi mở rộng một interface công khai.

**Default method** có thể cho phép bổ sung hành vi với triển khai mặc định:

~~~java
interface Formatter {
    String format(String text);

    default String formatUppercase(String text) {
        return format(text).toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Một triển khai **Formatter** cũ không nhất thiết phải thêm method mới ngay để biên dịch lại. Tuy nhiên, default method không phải giải pháp an toàn tuyệt đối: nó có thể tạo xung đột với các method từ interface khác, ảnh hưởng tới phân giải method hoặc không phù hợp với mọi implementation. Cần kiểm thử khả năng tương thích theo trường hợp thực tế.

### Tránh thay đổi chữ ký tùy tiện

Những thay đổi như xóa method, thay kiểu trả về không tương thích, làm hẹp quyền truy cập hoặc thay hợp đồng exception đều có thể làm hỏng người gọi.

Có thể cân nhắc quy trình tiến hóa có kiểm soát:

1. Giữ hợp đồng cũ trong giai đoạn chuyển đổi khi cần.
2. Thêm API thay thế với tên và ngữ nghĩa rõ ràng.
3. Ghi tài liệu hướng dẫn chuyển đổi.
4. Đánh dấu API dự kiến ngừng hỗ trợ bằng **@Deprecated** khi có kế hoạch thực tế, không xem đây là cách thay đổi hành vi mà không thông báo.
5. Chỉ loại bỏ hoặc thay đổi không tương thích tại ranh giới phiên bản và kế hoạch phát hành thích hợp.

Annotation **@Deprecated** là cơ chế Java vẫn được sử dụng để thông báo API không còn được khuyến nghị; bản thân annotation không tự loại bỏ method. Các thuộc tính như **since** và **forRemoval** cung cấp thông tin bổ sung khi cần.

## 13. Tài liệu API là một phần của hợp đồng

Chữ ký method chỉ thể hiện một phần ý nghĩa. Người gọi còn cần biết những quy tắc không thể đọc được chỉ từ kiểu dữ liệu.

Ví dụ một phương thức chuyển tiền phải nói rõ đơn vị tiền, điều kiện đầu vào, các quy tắc làm tròn hoặc vượt số, tác động trạng thái và cách xử lý lỗi.

Javadoc có thể dùng để diễn đạt hợp đồng ở ngay nơi khai báo:

~~~java
/**
 * Reserves a positive quantity for the given product code.
 *
 * @param sku product code; must not be null or blank
 * @param quantity number of units; must be positive
 * @throws IllegalArgumentException if the arguments are invalid
 */
public void reserve(String sku, int quantity) {
    if (sku == null || sku.isBlank() || quantity <= 0) {
        throw new IllegalArgumentException("Invalid reservation");
    }

    // Business implementation goes here.
}
~~~

Một hợp đồng đầy đủ còn có thể mô tả:

- Có cho phép **null** hay không.
- Đơn vị đo, miền giá trị và các bất biến.
- Phương thức có tác dụng phụ hoặc thay đổi trạng thái hay không.
- Collection trả về có sửa được không và thứ tự có được bảo đảm không.
- Có an toàn khi được gọi đồng thời từ nhiều thread hay không.
- Có chặn luồng, thực hiện I/O, gửi yêu cầu mạng hoặc phát sinh ngoại lệ nào không.
- Quan hệ giữa hai lần gọi, chẳng hạn kết quả có thể bị cache hoặc trạng thái có thể thay đổi.

Không nên đưa ra cam kết vượt khả năng thực tế. Ví dụ, nếu implementation chưa được thiết kế và kiểm tra cho truy cập đồng thời, không ghi trong tài liệu rằng API thread-safe.

## 14. Kiểm thử API từ góc nhìn người sử dụng

Một API dễ dùng nên được kiểm thử theo cách người gọi thật sự tương tác với nó, thay vì chỉ kiểm tra từng method private.

Một số câu hỏi cần kiểm tra:

- Người dùng có thể thực hiện tác vụ phổ biến chỉ với các method công khai không?
- Dữ liệu không hợp lệ có bị từ chối tại ranh giới phù hợp không?
- Giá trị trả về có rõ ràng và tuân theo hợp đồng không?
- Dùng implementation khác của cùng interface có vẫn hoạt động không?
- Việc lấy collection trả về có vô tình làm thay đổi trạng thái nội bộ không?
- Một thay đổi phiên bản có ảnh hưởng tới lời gọi hợp lệ hiện có không?

### Kiểm thử với fake implementation

Khi service phụ thuộc vào interface, có thể dùng fake nhỏ để quan sát các lời gọi mà không cần mạng hoặc database thật:

~~~java
import java.util.ArrayList;
import java.util.List;

class RecordingGateway implements PaymentGateway {
    private final List<String> calls = new ArrayList<>();

    @Override
    public void charge(String paymentId, long amountInCents) {
        calls.add(paymentId + ":" + amountInCents);
    }

    public List<String> recordedCalls() {
        return List.copyOf(calls);
    }
}
~~~

**RecordingGateway** triển khai chính hợp đồng **PaymentGateway** ở phần trước. Khi kiểm thử **CheckoutService**, mã có thể truyền fake này và xác minh nó nhận đúng mã thanh toán, số tiền mà không cần phụ thuộc hệ thống bên ngoài.

Kiểm thử qua interface cũng giúp phát hiện khi API khó sử dụng: nếu test buộc phải truy cập hàng loạt field private hoặc method nội bộ, rất có thể ranh giới abstraction đang chưa phù hợp.

## 15. Ví dụ tổng hợp: API gửi thông báo dễ mở rộng

Thiết kế sau thể hiện một API nhỏ với dữ liệu hợp lệ, interface làm điểm mở rộng và service dùng composition. Mọi khai báo nằm trong một tệp **NotificationDemo.java** để có thể biên dịch và chạy như một ví dụ độc lập.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class NotificationDemo {
    public record Message(String recipient, String body) {
        public Message {
            Objects.requireNonNull(recipient, "recipient");
            Objects.requireNonNull(body, "body");

            if (recipient.isBlank() || body.isBlank()) {
                throw new IllegalArgumentException(
                        "recipient and body must not be blank");
            }
        }
    }

    @FunctionalInterface
    public interface DeliveryChannel {
        void send(Message message);
    }

    public static final class NotificationService {
        private final DeliveryChannel channel;

        public NotificationService(DeliveryChannel channel) {
            this.channel = Objects.requireNonNull(channel, "channel");
        }

        public void notify(Message message) {
            channel.send(Objects.requireNonNull(message, "message"));
        }
    }

    private static final class RecordingChannel
            implements DeliveryChannel {
        private final List<Message> sentMessages = new ArrayList<>();

        @Override
        public void send(Message message) {
            sentMessages.add(message);
        }

        public List<Message> sentMessages() {
            return List.copyOf(sentMessages);
        }
    }

    public static void main(String[] args) {
        RecordingChannel channel = new RecordingChannel();
        NotificationService service = new NotificationService(channel);

        service.notify(new Message("lan@example.com", "Order confirmed"));
        service.notify(new Message("minh@example.com", "Payment received"));

        System.out.println(channel.sentMessages().size());
        System.out.println(channel.sentMessages().get(0).body());

        DeliveryChannel consoleChannel =
                message -> System.out.println(
                        "Send to " + message.recipient());

        new NotificationService(consoleChannel)
                .notify(new Message("an@example.com", "Welcome"));
    }
}
~~~

Kết quả:

~~~text
2
Order confirmed
Send to an@example.com
~~~

Những lựa chọn thiết kế quan trọng:

1. **Message** là record có cấu trúc rõ ràng; compact constructor từ chối nội dung thiếu hoặc rỗng.
2. **DeliveryChannel** chỉ có một phương thức **send(Message)**, đủ cho nhu cầu mở rộng kênh gửi. Có thể dùng lambda hoặc một lớp triển khai có tên.
3. **NotificationService** chỉ phụ thuộc vào **DeliveryChannel**, không biết channel dùng email, SMS hay một cơ chế khác.
4. Field **channel** là **private final**, được thiết lập qua constructor. Service giữ được một phụ thuộc ổn định.
5. **RecordingChannel** là triển khai nội bộ phục vụ ví dụ và kiểm thử; không phải một thành viên của API công khai dành cho người dùng.
6. **sentMessages()** trả về **List.copyOf(...)**, ngăn mã gọi sửa trực tiếp danh sách lưu bên trong fake.
7. Một implementation mới của **DeliveryChannel** có thể được đưa vào service mà không phải sửa method **notify(...)**.

Ví dụ chỉ mô phỏng việc gửi thông báo; nó không thực sự gửi email. **RecordingChannel** cũng không cam kết thread-safe. Những giới hạn này nên được nêu rõ thay vì để người dùng suy luận từ tên gọi.

## 16. Checklist thiết kế API

Trước khi công khai một lớp hoặc interface, có thể tự kiểm tra:

| Câu hỏi | Dấu hiệu thiết kế tốt |
|---|---|
| Người gọi cần làm gì? | API có một tập hành động gắn với nhu cầu thực |
| Có thành viên nào chỉ phục vụ nội bộ? | Chi tiết đó được giữ private hoặc package-private |
| Tên method có nhất quán không? | Cùng kiểu hành vi dùng cùng quy ước đặt tên |
| Các giá trị đầu vào có rõ nghĩa không? | Kiểu, tên tham số và kiểm tra bất biến phù hợp |
| Null và lỗi được xử lý như thế nào? | Hợp đồng không mơ hồ; có tài liệu cho trường hợp dự kiến |
| Có làm lộ collection nội bộ không? | Dữ liệu được trả về theo chính sách bất biến/view/snapshot rõ ràng |
| Có thể thay implementation không? | Sử dụng interface và composition ở đúng điểm biến đổi |
| Có cần cho người dùng kế thừa lớp không? | Điểm mở rộng được thiết kế và ghi tài liệu chủ đích |
| Thay đổi API có phá người dùng cũ không? | Đã xem xét source, binary và behavioral compatibility |
| Có thể kiểm thử như người dùng thật không? | Test được hành vi qua public API, không phụ thuộc chi tiết triển khai |

## Kết luận

Một API Java 27 nhỏ, nhất quán và dễ mở rộng cần cân bằng ba mục tiêu. **Nhỏ** là công khai ít khả năng nhưng đủ hoàn thành công việc. **Nhất quán** là dùng tên, kiểu, lỗi và quy tắc hành vi mà người gọi có thể dự đoán. **Dễ mở rộng** là cho phép thêm implementation hoặc thay đổi chi tiết bên trong qua các ranh giới có chủ đích mà không buộc mọi người dùng sửa mã.

Hãy bắt đầu từ trường hợp sử dụng, chọn abstraction phù hợp, bảo vệ bất biến, tài liệu hóa hợp đồng và kiểm thử từ phía người gọi. Với Java hiện đại, các công cụ như interface, record, sealed type, generic, **List.copyOf()** và modifier truy cập hỗ trợ những mục tiêu đó; không công cụ nào tự thay thế được một thiết kế có ranh giới và trách nhiệm rõ ràng.
