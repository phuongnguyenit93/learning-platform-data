# Phạm vi hợp đồng, trách nhiệm và các bảo đảm hành vi

Khi học **Dependency Injection (DI)**, ta thường bắt đầu bằng thao tác truyền một interface vào constructor. Nhưng một interface chỉ giúp tách mã sử dụng khỏi mã triển khai khi **bên sử dụng và bên cung cấp hiểu cùng một lời hứa**: phương thức làm gì, chấp nhận dữ liệu nào, trả về kết quả gì, có tác dụng phụ nào và điều gì xảy ra khi thất bại.

Ví dụ, cả bộ lưu đơn hàng trong RAM lẫn bộ lưu qua JDBC đều có thể triển khai `OrderStore`. Tuy nhiên, nếu một triển khai từ chối mã đơn trùng còn triển khai kia âm thầm ghi đè, chương trình vẫn biên dịch nhưng nghiệp vụ sẽ thay đổi khi thay dependency. **Hợp đồng phụ thuộc (dependency contract)** vì vậy phải mô tả cả *cấu trúc API* và *hành vi có thể dựa vào*.

Trong chương **Hợp đồng phụ thuộc** của module Dependency Injection, bài này giải thích cách xác định phạm vi trách nhiệm, phân chia nghĩa vụ giữa các bên và viết các bảo đảm hành vi đủ rõ để có thể thay adapter, kiểm thử bằng Java thuần và về sau lắp ghép qua DI container.

Sau bài này, bạn có thể:

- Xác định điều gì thuộc phạm vi một hợp đồng phụ thuộc và điều gì nằm ngoài hợp đồng.
- Phân biệt trách nhiệm của bên sử dụng, abstraction, bên triển khai và composition root.
- Đặc tả các điều kiện đầu vào, hậu điều kiện, lỗi, tác dụng phụ, trạng thái và giới hạn vận hành.
- Nhận diện việc “đúng chữ ký Java nhưng sai hành vi” và viết contract test áp dụng cho nhiều triển khai.
- Tách **phạm vi chức năng của hợp đồng** khỏi **scope/vòng đời** đối tượng trong DI.

## 1. Interface là điểm bắt đầu, chưa phải toàn bộ hợp đồng

Xét một chức năng đăng ký đơn hàng. Nghiệp vụ cần tạo đơn mới và tra cứu đơn theo mã:

~~~java
interface OrderStore {
    void add(Order order);
    java.util.Optional<Order> findById(String orderId);
}
~~~

Chữ ký trên cho trình biên dịch biết:

- Phương thức `add` nhận một `Order` và không trả về giá trị.
- Phương thức `findById` nhận `String` và trả về `Optional<Order>`.
- Một lớp muốn được dùng như `OrderStore` phải cung cấp những phương thức tương thích.

Nhưng chữ ký **chưa trả lời** các câu hỏi mà use case thực sự cần biết:

1. `add` là **thêm mới**, hay được phép ghi đè một đơn đã tồn tại?
2. Tham số `null`, mã đơn rỗng hoặc số tiền âm có hợp lệ không?
3. Sau khi `add` trả về thành công, cùng đối tượng `OrderStore` gọi `findById` ngay có thấy đơn đó không?
4. Không tìm thấy đơn có nghĩa `Optional.empty()`, còn lỗi kết nối sẽ được báo thế nào?
5. Lệnh gọi có thể tạo email, thanh toán hoặc ghi log nghiệp vụ hay chỉ chịu trách nhiệm lưu đơn?
6. Hợp đồng có hứa an toàn khi nhiều luồng cùng gọi, bền vững sau khi ứng dụng tắt hoặc tính nguyên tử trên nhiều hệ thống không?

Nếu các câu hỏi đó không được giải thích, mỗi adapter có thể đưa ra một cách hiểu khác nhau. **Hợp đồng đáng tin cậy phải đủ rõ để người viết use case biết mình có quyền dựa vào điều gì, và người viết adapter biết mình phải bảo đảm điều gì.**

### Ba tầng cần đọc trong một hợp đồng

| Tầng | Mô tả | Ví dụ với `OrderStore` |
| --- | --- | --- |
| **Cấu trúc** | Kiểu, phương thức, khả năng truy cập, tham số, kiểu trả về | `add(Order)`, `findById(String): Optional<Order>` |
| **Ngữ nghĩa** | Tiền điều kiện, hậu điều kiện, lỗi, tính nhất quán, tác dụng phụ | Không ghi đè mã đơn trùng; sau khi thêm thành công có thể tra cứu được |
| **Vận hành** | Đồng thời, vòng đời, độ bền dữ liệu, timeout, retry, tài nguyên | Adapter RAM chỉ giữ dữ liệu khi phiên bản còn tồn tại; chưa hứa thread-safe |

Tầng cấu trúc thường được trình biên dịch Java kiểm tra. Hai tầng còn lại cần **tài liệu, quy ước thiết kế và kiểm thử phù hợp**. Annotation hay DI container không tự bổ sung những bảo đảm còn thiếu.

## 2. Phạm vi hợp đồng: hứa đúng khả năng mà nghiệp vụ cần

Một abstraction nên đại diện cho **khả năng có ý nghĩa với bên sử dụng**, tránh vừa quá rộng vừa rò rỉ chi tiết hạ tầng.

Ví dụ, use case đăng ký đơn hàng cần lưu một đơn mới và tra cứu đơn theo mã. Hợp đồng có thể giới hạn ở đúng hai thao tác đó. Nếu thêm các hàm kết nối JDBC, chạy SQL tùy ý, gửi email hay tạo hóa đơn vào `OrderStore`, lớp sử dụng sẽ phụ thuộc vào nhiều điều nó không cần.

| Nội dung | Có thuộc phạm vi `OrderStore` trong ví dụ? | Lý do |
| --- | --- | --- |
| Thêm đơn mới theo mã duy nhất | **Có** | Đây là khả năng use case đang cần |
| Tìm đơn theo mã và phân biệt không tìm thấy | **Có** | Là kết quả tra cứu mà use case cần |
| Không âm thầm ghi đè một đơn trùng mã | **Có** | Quy tắc bảo toàn dữ liệu mà các triển khai phải thống nhất |
| Tính tổng giá tiền, giảm giá hoặc thuế | **Không** | Thuộc quy tắc nghiệp vụ khác; `Order` nhận tổng đã tính |
| Gửi email xác nhận sau khi lưu | **Không** | Thuộc collaborator hoặc quy trình điều phối khác |
| Cung cấp `Connection`, câu lệnh SQL hoặc tên bảng | **Không** | Là chi tiết adapter lưu trữ, không phải hợp đồng nghiệp vụ |
| Bảo đảm giao dịch nguyên tử giữa lưu đơn và gửi email | **Không** | Cần cơ chế giao dịch/phối hợp riêng; `OrderStore` đơn lẻ không đủ |
| Bảo đảm dữ liệu tồn tại sau khi tiến trình tắt | **Chưa hứa** | Adapter RAM và adapter bền vững có năng lực khác nhau |

**“Phạm vi hợp đồng” ở đây là ranh giới lời hứa chức năng và hành vi.** Đừng nhầm với **DI scope**, vốn nói về số lượng và vòng đời phiên bản dependency (application-wide, request-scoped, per-operation). Một interface có thể được dùng với nhiều scope khác nhau nhưng vẫn phải giữ nguyên những hành vi mà interface đã cam kết.

### Hợp đồng hẹp có ích khi nào?

Một hợp đồng nhỏ giúp:

- Người gọi không phải hiểu API của nhà cung cấp kỹ thuật.
- Adapter mới chỉ cần hiện thực các khả năng thực sự được dùng.
- Fake trong unit test dễ mô phỏng hành vi cốt lõi.
- Thay đổi trong thư viện hoặc cơ sở dữ liệu ít lan vào tầng nghiệp vụ.

Tuy nhiên, không phải cứ tách mọi phương thức thành một interface là tốt. Hãy nhóm những thao tác tạo thành **một trách nhiệm có ý nghĩa và chung quy tắc bảo đảm**, thay vì chia nhỏ cơ học.

## 3. Ai chịu trách nhiệm về điều gì?

Tách trách nhiệm rõ ràng giúp tránh tình trạng “service nghĩ adapter đã kiểm tra” còn “adapter nghĩ service đã kiểm tra”.

~~~mermaid
flowchart TB
    Root["Composition root: tạo & lắp ghép"] -->|"constructor injection"| Service["OrderRegistrationService: use case"]
    Service -->|"sử dụng hợp đồng"| Port["OrderStore: khả năng & lời hứa"]
    Adapter["InMemoryOrderStore / JdbcOrderStore: triển khai"] -->|"implements"| Port
    Root -->|"chọn & tạo"| Adapter
~~~

Mũi tên `implements` biểu diễn quan hệ mã nguồn của adapter với hợp đồng. Khi chạy, service gọi phương thức trên đối tượng adapter được truyền vào.

| Thành phần | Trách nhiệm chính | Điều không nên tự làm |
| --- | --- | --- |
| **Bên sử dụng (consumer/use case)** | Kiểm tra quy tắc đầu vào của nghiệp vụ; điều phối công việc; xử lý kết quả và lỗi theo hợp đồng | Tự chọn JDBC/HTTP/SMTP, tự dựng client mạng hoặc đoán ngầm hành vi adapter |
| **Hợp đồng (port/interface + đặc tả)** | Diễn đạt khả năng, tiền điều kiện, hậu điều kiện, loại lỗi và mức bảo đảm tối thiểu | Chứa chi tiết riêng của cơ sở dữ liệu hoặc nhà cung cấp dịch vụ |
| **Bên cung cấp (adapter/implementation)** | Hiện thực các phương thức và giữ đúng lời hứa, kể cả trên các đường lỗi | Tự ý đổi ngữ nghĩa để tiện công nghệ: ghi đè, nuốt lỗi, trả `null` thay `Optional` |
| **Composition root / DI container** | Chọn adapter, tạo/cấu hình, truyền dependency, xác lập scope và xử lý vòng đời tài nguyên | Chèn quy tắc nghiệp vụ vào quá trình lắp ghép |

Sự phân chia này gắn với **Dependency Inversion Principle (DIP)**: phần nghiệp vụ phụ thuộc vào hợp đồng ổn định; adapter phụ thuộc vào hợp đồng để thực hiện. **Dependency Injection (DI)** cung cấp phiên bản adapter qua constructor hoặc một cơ chế injection khác. **Inversion of Control (IoC)** thể hiện ở việc đối tượng sử dụng không tự quyết định quá trình tạo và nối dependency.

**Đáng chú ý:** Không thể thay một adapter đúng nghĩa chỉ bằng cách cùng `implements` interface. Adapter thay thế còn phải tuân thủ những **bảo đảm hành vi** mà use case đã dựa vào.

## 4. Cách viết một đặc tả hành vi có thể kiểm tra

Ta chọn đặc tả minh họa cho `OrderStore`:

| Chủ đề | Cam kết trong bài này |
| --- | --- |
| **Đầu vào `add`** | Yêu cầu `Order` khác `null`; `Order` hợp lệ có mã không rỗng và số tiền dương |
| **Đầu vào `findById`** | Mã đơn khác `null`, không rỗng hoặc toàn khoảng trắng |
| **Thêm mới** | Nếu mã chưa có, lưu đơn theo mã; nếu đã có, ném `DuplicateOrderException` và giữ nguyên đơn cũ |
| **Đọc sau ghi** | Trong cùng phiên bản `OrderStore`, không có thao tác thay đổi chen vào, `add` thành công thì `findById` ngay sau đó trả về đúng đơn vừa lưu |
| **Không tìm thấy** | `findById` trả `Optional.empty()`, không trả `null` |
| **Đầu vào sai** | `add(null)` ném `NullPointerException`; `findById` với mã sai ném `IllegalArgumentException` |
| **Lỗi hạ tầng** | Không biến lỗi lưu trữ thành “không tìm thấy”; adapter thực tế phải báo lỗi rõ theo chính sách API |
| **Tác dụng phụ** | Chỉ cập nhật dữ liệu đơn hàng thuộc phạm vi store; không gửi email, trừ tiền hoặc gọi quy trình nghiệp vụ khác |
| **Chưa cam kết** | Độ bền sau khi tiến trình dừng, thread-safety, giao dịch phân tán, độ trễ tối đa và khả năng tự retry |

Đặc tả trên chủ động **không hứa quá mức**. Một adapter trong RAM có thể đáp ứng tính duy nhất, tra cứu và đọc sau ghi trong cùng phiên bản; nó không thể bảo đảm dữ liệu còn nguyên sau khi ứng dụng khởi động lại. Nếu ứng dụng bắt buộc có tính bền vững, cần **một yêu cầu triển khai/vận hành rõ hơn** và loại trừ những adapter không đạt yêu cầu, thay vì âm thầm giả định mọi `OrderStore` đều bền vững.

### Tiền điều kiện, hậu điều kiện và lỗi

Có thể đọc một thao tác theo dạng:

- **Tiền điều kiện:** caller cung cấp dữ liệu gì để phương thức có thể thực hiện đúng?
- **Hậu điều kiện khi thành công:** trạng thái/kết quả nào được bảo đảm sau khi phương thức trả về?
- **Hậu điều kiện khi thất bại:** dữ liệu có bị thay đổi một phần không? Loại lỗi nào thể hiện nguyên nhân?
- **Tác dụng phụ:** ngoài giá trị trả về, điều gì thay đổi được phép quan sát?

Với `add`, ví dụ này cam kết không ghi đè **khi phát hiện đơn trùng**. Không nên tự diễn giải từ đó thành cam kết giao dịch nguyên tử trước mọi dạng lỗi hạ tầng. Muốn được phép dựa vào tính nguyên tử trên lỗi mạng, mất điện hoặc giao dịch phân tán, phải đặc tả và kiểm thử riêng.

## 5. Ví dụ hoàn chỉnh với Java thuần: interface, adapter và use case

Đây là chương trình **Java 17+** độc lập. Nó thực hiện các cam kết cơ bản phía trên, làm rõ nơi kiểm tra quy tắc nghiệp vụ và nơi bảo vệ dữ liệu. Bộ lưu trữ trong RAM giúp học DI trước khi mở rộng sang DI container hoặc cơ sở dữ liệu thực tế.

Lưu toàn bộ mã sau vào file `Main.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

// Giá trị nghiệp vụ hợp lệ ngay khi được tạo.
record Order(String id, long amountInCents) {
    Order {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Ma don khong hop le");
        }
        if (amountInCents <= 0) {
            throw new IllegalArgumentException("So tien phai lon hon 0");
        }
    }
}

// Lỗi nghiệp vụ có ý nghĩa: trùng mã đơn.
final class DuplicateOrderException extends RuntimeException {
    DuplicateOrderException(String orderId) {
        super("Ma don da ton tai: " + orderId);
    }
}

// Port: tách ý nghĩa thao tác khỏi phương thức lưu trữ cụ thể.
interface OrderStore {
    // add: thêm mới, không ghi đè mã đã tồn tại.
    // Thất bại vì trùng mã: DuplicateOrderException.
    // Đầu vào null: NullPointerException.
    void add(Order order);

    // Không tìm thấy: Optional.empty().
    // Mã null/rỗng: IllegalArgumentException.
    Optional<Order> findById(String orderId);
}

// Adapter RAM: phù hợp ví dụ đơn luồng, không bền vững sau khi tắt.
final class InMemoryOrderStore implements OrderStore {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public void add(Order order) {
        Objects.requireNonNull(order, "order");

        Order previous = orders.putIfAbsent(order.id(), order);
        if (previous != null) {
            throw new DuplicateOrderException(order.id());
        }
    }

    @Override
    public Optional<Order> findById(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Ma don khong hop le");
        }
        return Optional.ofNullable(orders.get(orderId));
    }
}

// Bên sử dụng: tạo giá trị nghiệp vụ và điều phối qua port.
final class OrderRegistrationService {
    private final OrderStore store;

    OrderRegistrationService(OrderStore store) {
        this.store = Objects.requireNonNull(store, "store");
    }

    Order register(String orderId, long amountInCents) {
        Order order = new Order(orderId, amountInCents);
        store.add(order);
        return order;
    }
}

// Composition root: chọn adapter, tạo và nối đồ thị đối tượng.
public class Main {
    public static void main(String[] args) {
        InMemoryOrderStore store = new InMemoryOrderStore();
        OrderRegistrationService service =
                new OrderRegistrationService(store);

        service.register("ORD-01", 99_000);
        System.out.println(store.findById("ORD-01").orElseThrow());

        try {
            service.register("ORD-01", 120_000);
        } catch (DuplicateOrderException expected) {
            System.out.println("Da chan trung ma: ORD-01");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Kết quả dự kiến:

~~~text
Order[id=ORD-01, amountInCents=99000]
Da chan trung ma: ORD-01
~~~

### Điều gì đang được bảo đảm?

1. **`Order` kiểm tra invariant của giá trị nghiệp vụ.** Một `Order` mới không thể có mã rỗng hoặc số tiền không dương qua constructor thông thường.
2. **`OrderStore` định nghĩa khả năng và ý nghĩa của thao tác.** Use case biết `add` là thêm mới và lỗi trùng mã phải có ý nghĩa riêng.
3. **`InMemoryOrderStore` thực thi phần lưu và bảo vệ dữ liệu.** `putIfAbsent` cho kết quả đúng trong ví dụ đơn luồng: đơn cũ không bị ghi đè khi thêm trùng mã.
4. **`OrderRegistrationService` không biết `HashMap` hay JDBC.** Nó nhận `OrderStore` qua constructor; chuyển sang adapter khác không đòi hỏi thay logic đăng ký nếu adapter giữ đúng hợp đồng.
5. **`Main` chịu trách nhiệm lắp ghép.** Đây là composition root. Về sau container có thể tự động hóa bước chọn và truyền dependency, nhưng không thay cho thiết kế hợp đồng.

**Giới hạn thực hành:** `HashMap` trong adapter này không bảo đảm an toàn luồng. Dùng nhiều request đồng thời đòi hỏi triển khai và đặc tả đồng thời phù hợp; `putIfAbsent` của một `HashMap` thường không trở thành thao tác nguyên tử an toàn giữa nhiều luồng chỉ vì có tên như vậy.

## 6. Kiểm thử hợp đồng: cùng một bộ kiểm tra cho nhiều adapter

Unit test của use case có thể dùng fake `OrderStore` để kiểm tra điều phối. Nhưng còn một câu hỏi khác: **mọi adapter được cung cấp cho use case có thật sự tuân thủ cùng hợp đồng không?** Đó là mục tiêu của *contract test*.

Bộ kiểm tra dưới đây chạy trên `OrderStore` do một factory cung cấp. Ta chạy với InMemoryOrderStore, rồi có thể dùng **cùng các kiểm tra** cho adapter JDBC/HTTP khi đã có triển khai và môi trường kiểm thử tương ứng.

Lưu vào `OrderStoreContractTest.java` cạnh `Main.java`:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

public class OrderStoreContractTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void verifyContract(
            String adapterName,
            Supplier<OrderStore> createFreshStore) {

        OrderStore store = createFreshStore.get();
        Order first = new Order("CONTRACT-001", 50_000);

        // Một store mới chưa có đơn này.
        check(store.findById(first.id()).isEmpty(),
                "Phai tra Optional.empty khi khong tim thay");

        store.add(first);

        // Đọc sau khi ghi trong cùng phiên bản.
        check(Objects.equals(
                    store.findById(first.id()).orElseThrow(), first),
                "Them thanh cong phai doc lai duoc dung don");

        // Trùng mã phải bị từ chối và không được ghi đè dữ liệu cũ.
        boolean duplicateRejected = false;
        try {
            store.add(new Order(first.id(), 70_000));
        } catch (DuplicateOrderException expected) {
            duplicateRejected = true;
        }
        check(duplicateRejected, "Phai tu choi ma don trung");
        check(store.findById(first.id()).orElseThrow().equals(first),
                "Khong duoc ghi de don cu");

        // Kiểu lỗi khi đầu vào không hợp lệ là một phần hợp đồng.
        boolean invalidIdRejected = false;
        try {
            store.findById(" ");
        } catch (IllegalArgumentException expected) {
            invalidIdRejected = true;
        }
        check(invalidIdRejected, "Ma don rong phai bi tu choi");

        boolean nullRejected = false;
        try {
            store.add(null);
        } catch (NullPointerException expected) {
            nullRejected = true;
        }
        check(nullRejected, "add(null) phai bi tu choi");

        System.out.println("PASS: " + adapterName);
    }

    public static void main(String[] args) {
        verifyContract("InMemoryOrderStore", InMemoryOrderStore::new);

        // Adapter thật có thể tham gia cùng bộ test:
        // verifyContract("JdbcOrderStore", () -> createTestJdbcStore());
    }
}
~~~

Chạy:

~~~bash
javac Main.java OrderStoreContractTest.java
java OrderStoreContractTest
~~~

Kết quả dự kiến: `PASS: InMemoryOrderStore`.

**Điểm quan trọng của contract test** là kiểm tra những quan sát mà bên sử dụng được phép trông đợi, chứ không kiểm tra adapter đã dùng `HashMap`, SQL hay HTTP thế nào. Khi triển khai adapter khác, factory kiểm thử phải cung cấp môi trường dữ liệu sạch hoặc mã đơn riêng biệt để tránh nhiễu giữa các lượt chạy.

Bộ kiểm tra này là **mẫu minh họa tối thiểu**, không kiểm tra tính bền vững, tính đồng thời hay lỗi mạng vì đặc tả chung chưa hứa các khả năng ấy. Nếu ứng dụng yêu cầu những bảo đảm đó, cần bổ sung đặc tả và kiểm thử tương ứng, tránh tuyên bố chất lượng vượt ngoài những gì đã xác minh.

## 7. “Đúng interface” nhưng vẫn vi phạm hợp đồng

Một lớp có thể biên dịch vì ký đúng `implements OrderStore`, trong khi các lựa chọn sau làm sai ngữ nghĩa:

| Hành vi của adapter | Vì sao vi phạm? | Hậu quả với use case |
| --- | --- | --- |
| `add` âm thầm ghi đè khi trùng mã | Phá lời hứa “thêm mới và từ chối trùng” | Đơn hàng cũ có thể bị thay đổi dữ liệu |
| `findById` trả `null` khi không tìm thấy | Phá lời hứa trả `Optional` không `null` | Caller gặp lỗi ngoài dự kiến |
| Catch lỗi kết nối rồi trả `Optional.empty()` | Đánh đồng “không tồn tại” với “không thể truy vấn” | Use case có thể kết luận sai rằng cần tạo mới |
| `add` trả thành công rồi gọi `findById` ngay vẫn không thấy đơn | Không đáp ứng lời hứa đọc sau ghi của ví dụ | Mã điều phối có thể hành xử không nhất quán |
| `add` tự gửi email hoặc trừ tiền | Thêm tác dụng phụ ngoài phạm vi | Retry lưu đơn có thể phát sinh tác động không mong muốn |
| Trùng mã nhưng báo lỗi `NullPointerException` | Thay đổi loại lỗi mà consumer dựa vào | Consumer không phân biệt được lỗi dữ liệu và lỗi cấu hình |

Đây là biểu hiện của **tính thay thế theo hành vi** (*behavioral substitutability*), gắn với nguyên lý Liskov Substitution Principle (LSP). Thay một đối tượng bằng triển khai khác có cùng interface **không nên phá những giả định hợp lệ** mà consumer đã dựa vào. Vì vậy, nguyên lý DIP về hướng phụ thuộc và kỹ thuật DI để truyền dependency chỉ thật sự hữu ích khi hợp đồng có ngữ nghĩa ổn định.

### Có nên viết contract trong comment/Javadoc?

Nên, nhất là tại các điểm ranh giới quan trọng. Ví dụ:

~~~java
/**
 * Thêm một đơn mới.
 *
 * @param order đơn hợp lệ, khác null
 * @throws NullPointerException nếu order là null
 * @throws DuplicateOrderException nếu mã đơn đã tồn tại;
 *         đơn cũ phải được giữ nguyên
 */
void add(Order order);
~~~

Javadoc không thay thế test, và test không thay thế việc mô tả đầy đủ. Hai phần bổ trợ nhau: đặc tả ghi rõ ý định, kiểm thử giúp phát hiện adapter đi lệch ý định.

## 8. Bảo đảm hành vi khó: lỗi, đồng thời, idempotency và giao dịch

Với hệ thống thật, đây thường là phần quyết định một abstraction có đáng tin hay không.

### 8.1. Không tìm thấy khác với không thể truy cập

`Optional.empty()` nên biểu thị **truy vấn hợp lệ và xác nhận không có đơn**. Nếu database timeout hoặc HTTP trả lỗi, adapter không được tự chuyển nó thành “không tìm thấy” nếu hợp đồng không cho phép. Tùy nhu cầu, hợp đồng có thể chọn một exception ổn định (ví dụ `StoreUnavailableException`) hoặc một kiểu kết quả phân biệt rõ `FOUND`, `NOT_FOUND`, `UNAVAILABLE`.

Không cần quy định chi tiết mọi exception nội bộ của JDBC, nhưng cần quy định **những loại kết quả mà consumer có thể dựa vào để ra quyết định**.

### 8.2. Idempotency phải được nêu rõ

Idempotency nghĩa là lặp lại một thao tác có cùng ý định sẽ không tạo thêm tác dụng ngoài ý muốn. Trong hợp đồng ví dụ, gọi `add` lần hai với cùng mã đơn **không được coi là thành công**, mà phát sinh `DuplicateOrderException`. Do đó `add` **không phải API bảo đảm “retry luôn thành công”**, dù việc từ chối trùng giúp bảo vệ dữ liệu.

Nếu bài toán cần retry an toàn sau timeout mạng, có thể thiết kế thêm một thao tác có **idempotency key** và quy tắc rõ ràng về kết quả của các lần gọi lặp. Không nên tự giả định thao tác thêm mới hay thanh toán có sẵn idempotency.

### 8.3. Đồng thời là một phần của phạm vi bảo đảm

Tính duy nhất theo mã đơn là cam kết nghiệp vụ rất mạnh khi có nhiều request. Ví dụ RAM chỉ chứng minh được trường hợp tuần tự. Nếu hợp đồng được sử dụng đồng thời, triển khai thực tế phải bảo đảm hành vi tương ứng: chẳng hạn dùng cơ chế đồng bộ hóa hoặc ràng buộc unique của database kết hợp xử lý lỗi cạnh tranh.

Một `HashMap` đơn thuần **không** đủ cho truy cập đồng thời. Chỉ dùng `ConcurrentHashMap` cũng không tự giải quyết tất cả các giao dịch gồm nhiều bước. Hãy xác định đối tượng có được phép gọi từ nhiều luồng không, phần nào được bảo đảm nguyên tử, và những giới hạn đó có phù hợp với consumer không.

### 8.4. Phạm vi giao dịch không tự kéo dài qua nhiều dependency

Giả sử `OrderRegistrationService` gọi `OrderStore.add` rồi `ConfirmationSender.send`. Từng hợp đồng có thể hoạt động đúng nhưng gửi thông báo vẫn thất bại sau khi lưu đơn. Muốn bảo đảm không mất thông báo hoặc hạn chế gửi trùng cần thiết kế ở mức quy trình như outbox, retry có điều kiện hoặc cơ chế điều phối phù hợp.

**DI không cung cấp giao dịch**; nó chỉ giúp truyền các collaborator. Chính sách về nhất quán và bù trừ thuộc về thiết kế use case và cơ chế hạ tầng đi kèm.

## 9. Scope, vòng đời và quyền sở hữu phụ thuộc

Hợp đồng có thể mô tả khả năng dùng chung đối tượng và yêu cầu tài nguyên, nhưng **composition root** hoặc DI container quyết định cách tạo, cấp và giải phóng các phiên bản.

| Vấn đề | Câu hỏi cần trả lời |
| --- | --- |
| **Scope** | Một phiên bản `OrderStore` được dùng chung cho ứng dụng, mỗi request hay mỗi thao tác? |
| **Trạng thái** | Trạng thái trong adapter có được chia sẻ giữa các use case không? Có cần isolation? |
| **Đồng thời** | Phiên bản được dùng chung có cho phép nhiều thread gọi cùng lúc không? |
| **Vòng đời** | Ai tạo và ai đóng connection, client hoặc thread pool do adapter sở hữu? |
| **Dữ liệu sau khởi động lại** | Hợp đồng yêu cầu persistence hay ứng dụng có thể dùng adapter RAM tạm thời? |

Ví dụ `InMemoryOrderStore` giữ trạng thái trong một đối tượng. Hai phiên bản khác nhau sẽ có hai `Map` độc lập; test đọc sau ghi chỉ hứa kết quả trên **cùng phiên bản**. Nếu ứng dụng có nhiều node cần cùng nhìn thấy dữ liệu, đó là yêu cầu mạnh hơn, đòi hỏi một adapter và hạ tầng phù hợp.

Khi dependency sở hữu tài nguyên `AutoCloseable`, nơi nắm quyền sở hữu vòng đời phải bảo đảm đóng nó tại thời điểm thích hợp. Consumer được inject một dependency dùng chung không nên tự đóng nó sau mỗi lần gọi. Cách truyền qua constructor giúp các ranh giới sử dụng rõ ràng hơn, nhưng **constructor injection không tự quyết định scope hay quyền sở hữu tài nguyên**.

## 10. Thiết kế hợp đồng vừa đủ và thay đổi có kiểm soát

Một hợp đồng quá lỏng khiến adapter dễ làm sai; một hợp đồng quá mạnh có thể không triển khai được trên những hệ thống được phép dùng. Ví dụ:

- Hứa mọi adapter có độ trễ dưới 1 ms là không thực tế khi cho phép adapter truy cập mạng.
- Bỏ qua loại lỗi, khả năng retry và đặc tính đọc sau ghi khiến caller phải tự phỏng đoán.
- Đưa đối tượng JDBC hoặc ORM entity vào chữ ký hợp đồng khiến core bị ràng buộc với công nghệ cấp thấp.
- Thêm phương thức vào một interface đang có nhiều adapter có thể khiến tất cả triển khai phải thay đổi.
- Thay `add` từ “từ chối trùng” sang “ghi đè nếu trùng” là thay đổi hành vi phá vỡ kỳ vọng, dù chữ ký Java không đổi.

Khi phát triển API, hãy giữ câu hỏi: **Consumer hiện có đang được quyền dựa vào hành vi nào?** Nếu thay đổi những hành vi đó, cần xem đây là thay đổi hợp đồng, cập nhật tài liệu, test và kế hoạch chuyển đổi các adapter/caller; việc Java vẫn biên dịch không chứng minh tương thích.

## 11. Checklist thiết kế một dependency contract

Trước khi đưa một interface vào constructor, hãy kiểm tra theo thứ tự:

1. **Nhu cầu:** use case cần khả năng gì, ở mức khái niệm nghiệp vụ nào?
2. **Ranh giới:** phương thức nào thuộc hợp đồng; điều gì cố ý đặt ngoài hợp đồng?
3. **Đầu vào:** dữ liệu hợp lệ, `null`, giá trị rỗng, miền giá trị và quy tắc kiểm tra?
4. **Đầu ra:** kết quả khi thành công, khi không tìm thấy, khi không có dữ liệu?
5. **Lỗi:** các loại lỗi nghiệp vụ và lỗi hạ tầng mà caller được phép phân biệt?
6. **Tác dụng phụ:** trạng thái nào có thể thay đổi; được phép gửi thông báo hay gây tác động ngoài không?
7. **Thời gian và đồng thời:** có yêu cầu đọc sau ghi, timeout, idempotency, thứ tự hay an toàn đa luồng không?
8. **Scope và lifecycle:** yêu cầu nào thuộc contract, quyết định cấp đối tượng nào thuộc composition root?
9. **Kiểm thử:** contract test dùng chung có phát hiện adapter lệch lời hứa không?
10. **Khả năng tiến hóa:** thay adapter hoặc đổi API có làm mất bảo đảm mà consumer đang sử dụng không?

### Tự kiểm tra

**Tình huống A:** Cả `InMemoryOrderStore` lẫn `JdbcOrderStore` đều có `findById`. JDBC adapter bắt lỗi kết nối và trả `Optional.empty()`. Có ổn không?

**Không.** Hợp đồng dùng `Optional.empty()` để biểu thị “không có đơn”, không phải “không thể kiểm tra”. Adapter đã đổi ngữ nghĩa lỗi thành kết quả nghiệp vụ sai.

**Tình huống B:** Một adapter dùng `Map.put(order.id(), order)`; adapter khác dùng `putIfAbsent` và từ chối trùng. Cả hai cùng `implements OrderStore`. Có thể thay thế cho nhau không?

**Không theo hợp đồng hiện tại.** Adapter đầu tiên ghi đè đơn cũ, vi phạm bảo đảm thêm mới và bảo toàn dữ liệu khi trùng mã.

**Tình huống C:** Constructor của `OrderRegistrationService` nhận `OrderStore`. Điều này đã bảo đảm dữ liệu không mất khi tắt ứng dụng chưa?

**Chưa.** Constructor injection chỉ đưa dependency vào service. Tính bền vững phụ thuộc vào đặc tả cần có và adapter/vận hành cụ thể được chọn tại composition root.

**Tình huống D:** Unit test với fake `OrderStore` chạy đúng. Có thể bỏ qua kiểm thử adapter thật?

**Không.** Unit test xác minh logic của consumer trong điều kiện fake được cấp; contract test và kiểm thử tích hợp mới giúp xác nhận adapter thật giữ đúng các lời hứa liên quan.

**Ghi nhớ:** **Hợp đồng phụ thuộc xác định điều bên sử dụng được phép tin tưởng; adapter có trách nhiệm biến những lời hứa đó thành hành vi thực tế; composition root có trách nhiệm cung cấp đúng adapter với scope và vòng đời phù hợp.** DIP giúp hướng mã nguồn về hợp đồng, còn DI giúp truyền dependency mà không buộc nghiệp vụ biết cách tạo nó. Chữ ký interface là nền tảng, nhưng phạm vi trách nhiệm và bảo đảm hành vi mới quyết định một dependency có thật sự thay thế và kiểm thử được hay không.
