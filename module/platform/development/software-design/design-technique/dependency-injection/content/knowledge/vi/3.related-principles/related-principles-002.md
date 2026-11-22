# Nguyên lý đảo ngược phụ thuộc (DIP) và điểm khác biệt với DI

**Dependency Inversion Principle (DIP)** là một nguyên lý thiết kế giúp quy tắc nghiệp vụ cấp cao ít bị ràng buộc bởi chi tiết kỹ thuật cấp thấp. **Dependency Injection (DI)** là kỹ thuật cung cấp các đối tượng phụ thuộc từ bên ngoài cho đối tượng cần sử dụng chúng. Hai khái niệm thường đi cùng nhau, nhưng trả lời **hai câu hỏi khác nhau**:

- **DIP:** Mã nguồn của phần nghiệp vụ nên phụ thuộc vào những kiểu và hợp đồng nào?
- **DI:** Ai tạo, chọn và truyền các đối tượng thực thi những hợp đồng đó vào phần nghiệp vụ?

Trong module Dependency Injection, việc phân biệt hai câu hỏi này rất quan trọng: constructor injection, composition root, quản lý scope và vòng đời đều trở nên rõ ràng hơn khi ta đã xác định đúng hướng phụ thuộc trong thiết kế. Có thể hiểu và thực hành bằng Java thuần trước khi dùng DI container.

Sau bài này, bạn có thể nhận diện vi phạm DIP, giải thích chính xác quan hệ giữa DIP, DI và Inversion of Control (IoC), thiết kế một *port* nghiệp vụ và adapter triển khai nó, rồi kiểm thử service bằng fake mà không cần kết nối hạ tầng.

## 1. DIP nói gì?

Nguyên lý đảo ngược phụ thuộc (*Dependency Inversion Principle*), một trong năm nguyên lý SOLID, thường được diễn đạt bằng hai mệnh đề:

1. **Module cấp cao không nên phụ thuộc trực tiếp vào module cấp thấp. Cả hai nên phụ thuộc vào abstraction.**
2. **Abstraction không nên phụ thuộc vào chi tiết triển khai. Chi tiết triển khai nên phụ thuộc vào abstraction.**

Trong ngữ cảnh ứng dụng Java:

- **Module cấp cao (high-level):** quy tắc nghiệp vụ hoặc use case, chẳng hạn đặt đơn hàng, tính phí, xét điều kiện hoàn tiền.
- **Module cấp thấp (low-level):** chi tiết kỹ thuật để phục vụ use case, chẳng hạn gửi email qua SMTP, lưu dữ liệu qua JDBC, gọi REST API.
- **Abstraction:** một hợp đồng ổn định mô tả điều nghiệp vụ cần, ví dụ OrderStore hay ConfirmationSender.

“Đảo ngược” ở đây nói chủ yếu về **hướng phụ thuộc trong mã nguồn** (*source-code dependency*), không có nghĩa đảo ngược trình tự thực thi. Khi chạy, service nghiệp vụ vẫn gọi repository hoặc adapter như bình thường. Điều thay đổi là phần nghiệp vụ **không cần import tên lớp triển khai hạ tầng**.

### Hai loại quan hệ dễ bị nhầm

| Loại quan hệ | Ví dụ | DIP/DI liên quan thế nào? |
| --- | --- | --- |
| **Phụ thuộc trong mã nguồn** | PlaceOrderService khai báo một trường kiểu OrderStore | DIP hướng dẫn mã nguồn nên trỏ tới hợp đồng ổn định |
| **Phụ thuộc đối tượng lúc chạy** | Một phiên bản PlaceOrderService cần một phiên bản OrderStore | DI quyết định cách cung cấp phiên bản phù hợp |

Một service có thể vẫn gọi cùng thao tác save, nhưng sau khi áp dụng DIP, việc save được mô tả qua hợp đồng do nghiệp vụ cần thay vì phụ thuộc vào lớp JdbcOrderStore hoặc InMemoryOrderStore cụ thể.

## 2. Ví dụ vi phạm: nghiệp vụ phụ thuộc vào chi tiết

Giả sử một hệ thống cần nhận đơn hàng, lưu đơn và gửi thông báo xác nhận. Ban đầu, lập trình viên viết:

~~~java
// Mã minh họa vấn đề thiết kế.
final class PlaceOrderService {
    void place(Order order) {
        JdbcOrderStore store = new JdbcOrderStore(/* cấu hình DB */);
        SmtpConfirmationSender sender =
                new SmtpConfirmationSender(/* cấu hình mail */);

        // Kiểm tra các điều kiện nghiệp vụ...
        store.save(order);
        sender.send(order);
    }
}
~~~

PlaceOrderService là phần mô tả quy trình nghiệp vụ nhưng lại **biết lớp JDBC và SMTP cụ thể**, thậm chí tự tạo và cấu hình chúng. Cách viết này gây nhiều vấn đề:

- Thay DB hoặc nhà cung cấp email có thể buộc sửa PlaceOrderService dù quy tắc đặt đơn không thay đổi.
- Kiểm thử logic đặt đơn có nguy cơ cần cơ sở dữ liệu hoặc máy chủ mail.
- Vòng đời của kết nối, client và cấu hình nằm trong luồng xử lý thay vì một nơi kiểm soát chung.
- Phần chính sách nghiệp vụ có xu hướng bị lẫn với cách thao tác hạ tầng.

Có hai vấn đề cần phân biệt: **phụ thuộc vào lớp cụ thể** là vấn đề về DIP; **tự tạo dependency bên trong service** là vấn đề về cách lắp ghép mà DI thường giải quyết. Chỉ sửa một trong hai chưa chắc sửa được vấn đề còn lại.

## 3. Đảo hướng phụ thuộc: nghiệp vụ định nghĩa hợp đồng

Trong thiết kế theo DIP, phần nghiệp vụ làm việc với những hợp đồng diễn đạt nhu cầu của chính nó:

~~~java
interface OrderStore {
    void save(Order order);
}

interface ConfirmationSender {
    void send(Order order);
}

final class PlaceOrderService {
    private final OrderStore store;
    private final ConfirmationSender sender;

    PlaceOrderService(OrderStore store, ConfirmationSender sender) {
        this.store = store;
        this.sender = sender;
    }

    void place(Order order) {
        // Kiểm tra các điều kiện nghiệp vụ...
        store.save(order);
        sender.send(order);
    }
}
~~~

Các adapter cấp thấp hiện **triển khai** hợp đồng đó:

~~~java
final class JdbcOrderStore implements OrderStore {
    @Override
    public void save(Order order) {
        // Lưu bằng JDBC: chi tiết nằm trong adapter.
    }
}

final class SmtpConfirmationSender implements ConfirmationSender {
    @Override
    public void send(Order order) {
        // Gửi bằng SMTP: chi tiết nằm trong adapter.
    }
}
~~~

Hai đoạn trên tập trung mô tả quan hệ thiết kế; chưa phải một chương trình đầy đủ để kết nối JDBC/SMTP. Điểm cốt lõi là PlaceOrderService chỉ biết OrderStore và ConfirmationSender. Các adapter phải tuân thủ hợp đồng mà phần nghiệp vụ cần.

~~~mermaid
flowchart TB
    subgraph Before["Trước: phụ thuộc trực tiếp vào chi tiết"]
        H1["PlaceOrderService"] --> L1["JdbcOrderStore"]
        H1 --> L2["SmtpConfirmationSender"]
    end
    subgraph After["Sau: phụ thuộc vào abstraction"]
        H2["PlaceOrderService"] --> P1["OrderStore (port)"]
        H2 --> P2["ConfirmationSender (port)"]
        L3["JdbcOrderStore"] -->|"implements"| P1
        L4["SmtpConfirmationSender"] -->|"implements"| P2
    end
~~~

**Mũi tên trong sơ đồ biểu diễn phụ thuộc mã nguồn.** Lúc chạy, PlaceOrderService vẫn gọi save và send trên các đối tượng cụ thể được cung cấp; DIP không làm lời gọi biến mất. Sự thay đổi quan trọng nằm ở việc **chi tiết kỹ thuật phụ thuộc vào hợp đồng ổn định**, thay vì buộc nghiệp vụ phụ thuộc vào chi tiết đó.

Trong dự án có chia module, interface OrderStore và ConfirmationSender thường được đặt trong module nghiệp vụ/application core hoặc một module hợp đồng do phía nghiệp vụ sở hữu. Adapter hạ tầng tham chiếu module này. Việc đặt interface cạnh một lớp JDBC rồi buộc nghiệp vụ tham chiếu toàn bộ module JDBC có thể khiến phụ thuộc cấp mã nguồn vẫn sai hướng, dù service dùng interface.

## 4. DIP khác DI ở đâu?

| Góc nhìn | DIP — Dependency Inversion Principle | DI — Dependency Injection |
| --- | --- | --- |
| Bản chất | Nguyên lý thiết kế hướng phụ thuộc | Kỹ thuật đưa dependency vào đối tượng |
| Câu hỏi chính | “Lớp nghiệp vụ phụ thuộc vào hợp đồng nào?” | “Đối tượng cần dùng được ai cung cấp, vào lúc nào?” |
| Trọng tâm | Mức độ ghép nối giữa chính sách và chi tiết triển khai | Khởi tạo, truyền, lắp ghép và quản lý đối tượng |
| Biểu hiện | Core tham chiếu port; adapter hiện thực port | Constructor nhận tham số được tạo từ bên ngoài |
| Có cần container? | Không | Không |
| Dấu hiệu sai thường gặp | Core import trực tiếp lớp JDBC, HTTP, SMTP cụ thể | Service tự tạo hoặc tự tìm dependency bị ẩn |

**DI không tự động bảo đảm DIP.** Đoạn sau đã dùng constructor injection nhưng service vẫn phụ thuộc vào lớp cụ thể:

~~~java
// Mã minh họa: dependency được "inject" nhưng chưa đảo hướng phụ thuộc.
final class ReportService {
    private final SqlReportRepository repository;

    ReportService(SqlReportRepository repository) {
        this.repository = repository;
    }
}
~~~

Người khác có thể tạo SqlReportRepository và truyền vào ReportService, nên đây vẫn là DI. Tuy vậy, ReportService phải biết kiểu SqlReportRepository, vì thế thay một adapter bằng triển khai khác có thể buộc sửa service. Nếu SqlReportRepository là chi tiết hạ tầng, thiết kế vẫn chưa đạt mục tiêu DIP.

Ngược lại, **DIP không yêu cầu phải dùng constructor injection hoặc một DI framework cụ thể**. Phần nghiệp vụ có thể phụ thuộc đúng vào abstraction trong khi ứng dụng chọn cách lắp ghép bằng factory, cơ chế plugin hoặc một composition root viết tay. Constructor injection thường là cách đơn giản và minh bạch nhất để kết hợp hai ý tưởng, nhưng không phải định nghĩa của DIP.

### DI, DIP và IoC liên hệ với nhau như thế nào?

**Inversion of Control (IoC)** là ý tưởng rộng hơn về việc chuyển quyền điều phối một số hoạt động khỏi đối tượng đang thực hiện công việc. **DI** là một kỹ thuật thể hiện IoC khi phần bên ngoài cung cấp dependency cho đối tượng thay vì đối tượng tự tìm hoặc tạo dependency. **DIP** định hướng việc các module nên tham chiếu hợp đồng nào trong thiết kế.

Một trình tự thực hành hợp lý là:

1. Theo **DIP**, định nghĩa hợp đồng OrderStore theo nhu cầu nghiệp vụ.
2. Theo **DI**, cho PlaceOrderService nhận OrderStore qua constructor.
3. Tại **composition root**, quyết định dùng InMemoryOrderStore trong ví dụ hoặc adapter lưu trữ thật ở môi trường triển khai.
4. Quản lý **scope và vòng đời** của các adapter tại nơi phù hợp, đặc biệt khi chúng sở hữu kết nối hoặc tài nguyên dùng chung.

Không nên đồng nhất IoC với DI container. IoC có thể xuất hiện ở nhiều cơ chế khác như callback và framework lifecycle; DI chỉ là một trường hợp cụ thể.

## 5. Kết hợp DIP và constructor injection bằng Java thuần

Ví dụ dưới đây là một chương trình Java 17+ chạy độc lập. Nó cho thấy cả **quan hệ mã nguồn** (service dùng interface) lẫn **quá trình lắp ghép đối tượng** (Main tạo adapter và truyền vào constructor).

Lưu toàn bộ vào file Main.java:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

// Dữ liệu nghiệp vụ.
record Order(String id, long totalVnd) {}

// Hợp đồng ở ranh giới nghiệp vụ (ports).
interface OrderStore {
    void save(Order order);
}

interface ConfirmationSender {
    void send(Order order);
}

// Phần chính sách nghiệp vụ: không biết loại DB hay phương thức gửi tin.
final class PlaceOrderService {
    private final OrderStore store;
    private final ConfirmationSender sender;

    PlaceOrderService(OrderStore store, ConfirmationSender sender) {
        this.store = Objects.requireNonNull(store, "store");
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    void place(Order order) {
        if (order == null
                || order.id() == null
                || order.id().isBlank()
                || order.totalVnd() <= 0) {
            throw new IllegalArgumentException("Don hang khong hop le");
        }

        store.save(order);
        sender.send(order);
    }
}

// Chi tiết triển khai: lưu trong RAM để minh họa, không phải DB thật.
final class InMemoryOrderStore implements OrderStore {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public void save(Order order) {
        orders.put(order.id(), order);
    }

    boolean contains(String orderId) {
        return orders.containsKey(orderId);
    }
}

// Chi tiết triển khai: in thông báo, không gửi email thật.
final class ConsoleConfirmationSender implements ConfirmationSender {
    @Override
    public void send(Order order) {
        System.out.println("Da ghi nhan don: " + order.id());
    }
}

// Composition root: biết cả core lẫn các adapter để lắp ghép.
public class Main {
    public static void main(String[] args) {
        InMemoryOrderStore store = new InMemoryOrderStore();
        ConfirmationSender sender = new ConsoleConfirmationSender();

        PlaceOrderService service = new PlaceOrderService(store, sender);

        Order order = new Order("ORD-100", 250_000);
        service.place(order);

        System.out.println("Da luu: " + store.contains(order.id()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Đầu ra kỳ vọng:

~~~text
Da ghi nhan don: ORD-100
Da luu: true
~~~

Phân tích từng vai trò:

- **DIP:** PlaceOrderService khai báo OrderStore và ConfirmationSender, không tham chiếu trực tiếp InMemoryOrderStore hay ConsoleConfirmationSender. Các adapter thực hiện hợp đồng của phần nghiệp vụ.
- **DI:** Hai dependency được đưa vào constructor của PlaceOrderService từ bên ngoài.
- **Composition root:** Main chọn triển khai cụ thể, khởi tạo các đối tượng và nối chúng thành đồ thị đối tượng trước khi gọi nghiệp vụ.
- **Scope:** ví dụ tạo một phiên bản của mỗi adapter cho toàn bộ lần chạy main. Với server có nhiều request, cách chia sẻ đối tượng phải xét trạng thái và tính an toàn luồng.

Trong ví dụ console đơn luồng, HashMap là đủ để diễn giải cấu trúc. Khi dùng cho server nhiều luồng, cần chọn bộ lưu trữ hỗ trợ đồng thời hoặc cấu trúc phù hợp; DI không tự làm cho một adapter trở nên thread-safe.

Lưu ý: nếu gửi thông báo thất bại sau khi đã lưu đơn, hệ thống có thể rơi vào trạng thái “đơn đã lưu nhưng chưa thông báo”. DIP và DI không giải quyết tự động vấn đề nhất quán đó. Hệ thống thực tế phải thiết kế retry, outbox hoặc cơ chế xử lý lỗi phù hợp với yêu cầu nghiệp vụ.

## 6. Kiểm thử: DIP tạo điểm thay thế, DI đưa fake vào

Khi service chỉ biết các port, test có thể thay adapter thật bằng fake hoặc spy tự viết. Constructor injection khiến việc cấp các fake này rõ ràng.

Đặt đoạn sau vào OrderServiceTest.java, cùng thư mục với Main.java:

~~~java
final class FakeOrderStore implements OrderStore {
    Order savedOrder;
    int saveCount;

    @Override
    public void save(Order order) {
        savedOrder = order;
        saveCount++;
    }
}

final class RecordingConfirmationSender implements ConfirmationSender {
    Order sentOrder;
    int sendCount;

    @Override
    public void send(Order order) {
        sentOrder = order;
        sendCount++;
    }
}

public class OrderServiceTest {
    public static void main(String[] args) {
        FakeOrderStore store = new FakeOrderStore();
        RecordingConfirmationSender sender =
                new RecordingConfirmationSender();

        PlaceOrderService service = new PlaceOrderService(store, sender);
        Order order = new Order("TEST-1", 99_000);

        service.place(order);

        if (!order.equals(store.savedOrder)
                || !order.equals(sender.sentOrder)
                || store.saveCount != 1
                || sender.sendCount != 1) {
            throw new AssertionError("Sai luong dat don");
        }

        try {
            service.place(new Order("", 10));
            throw new AssertionError("Phai tu choi ma don rong");
        } catch (IllegalArgumentException expected) {
            // Hop le: don sai bi tu choi truoc khi goi dependency.
        }

        if (store.saveCount != 1 || sender.sendCount != 1) {
            throw new AssertionError("Don sai da goi dependency");
        }

        System.out.println("PASS");
    }
}
~~~

Chạy:

~~~bash
javac Main.java OrderServiceTest.java
java OrderServiceTest
~~~

Đầu ra kỳ vọng: PASS.

Bài kiểm thử không cần database, mail server hoặc DI container. Nó chứng minh PlaceOrderService phối hợp các hợp đồng như mong đợi và không gọi dependency khi đơn hàng không hợp lệ. **DIP** giúp tạo ranh giới để thay adapter bằng fake; **DI** giúp truyền fake vào service. Các adapter thật vẫn cần kiểm thử tích hợp riêng.

## 7. Chọn abstraction theo nhu cầu nghiệp vụ

Tuân thủ DIP không đồng nghĩa tạo interface cho *mọi* class. Một abstraction hữu ích cần ổn định so với nhu cầu của phần nghiệp vụ và không vô tình làm lộ chi tiết hạ tầng.

So sánh hai cách đặt hợp đồng:

~~~java
// Phụ thuộc vào công nghệ của adapter, khó thay thế:
interface JdbcOrderGateway {
    void executeSql(String sql);
}

// Phụ thuộc vào điều phần nghiệp vụ cần:
interface OrderStore {
    void save(Order order);
}
~~~

Interface đầu tiên vẫn khiến use case biết SQL và chịu trách nhiệm tạo câu lệnh. Interface thứ hai diễn đạt khả năng lưu đơn ở mức nghiệp vụ. Nó có thể được thực hiện bằng JDBC, API bên ngoài, file hoặc một fake trong test mà không buộc service biết chi tiết.

Khi thiết kế abstraction, hãy tự hỏi:

- Hợp đồng mô tả **khả năng mà nghiệp vụ cần** hay chỉ sao chép API của thư viện?
- Thay công nghệ lưu trữ hoặc gửi thông báo có buộc thay đổi hợp đồng và quy tắc nghiệp vụ không?
- Có cần một abstraction riêng tại ranh giới này, hay đây chỉ là một giá trị/đối tượng đơn giản không mang chi tiết hạ tầng?
- Core có đang phụ thuộc vào kiểu dữ liệu của framework, như đối tượng request HTTP hoặc ORM entity, theo cách khiến nó khó dùng độc lập không?

Trong kiến trúc phân tầng, hexagonal hoặc clean architecture, các interface như OrderStore và ConfirmationSender thường được gọi là **ports**, còn JDBC/SMTP/HTTP implementations là **adapters**. DIP giải thích vì sao hướng tham chiếu từ adapter vào port quan trọng. Đây là một cách áp dụng phổ biến, không phải yêu cầu phải dùng toàn bộ một phong cách kiến trúc cụ thể.

## 8. Những nhầm lẫn phổ biến

| Nhầm lẫn | Điều cần hiểu |
| --- | --- |
| “Chỉ cần @Inject/@Autowired là đã đạt DIP.” | Annotation/container chỉ liên quan cơ chế lắp ghép; service vẫn có thể import trực tiếp lớp hạ tầng. |
| “Đã truyền qua constructor là phụ thuộc đã được đảo.” | Constructor nhận concrete type vẫn là DI nhưng chưa chắc là DIP. |
| “DIP yêu cầu tất cả class đều có interface.” | Abstraction nên phục vụ ranh giới thay đổi có ý nghĩa; tạo interface vô mục đích có thể khiến mã phức tạp hơn. |
| “Đảo phụ thuộc nghĩa là adapter gọi service.” | DIP mô tả hướng phụ thuộc mã nguồn. Thứ tự gọi khi chạy vẫn xuất phát từ use case. |
| “Có DI container thì không cần composition root.” | Container đảm nhiệm lắp ghép theo cấu hình, nhưng ứng dụng vẫn cần ranh giới bootstrap và quyết định triển khai, scope, vòng đời. |
| “Đổi adapter chắc chắn không ảnh hưởng nghiệp vụ.” | Chỉ đúng khi adapter mới thực hiện đúng hợp đồng và ngữ nghĩa mong đợi, kể cả lỗi, tính nhất quán và các ràng buộc phi chức năng. |

Một lỗi ít rõ ràng là đặt interface mang tên trung tính nhưng chứa những kiểu đặc thù của adapter, ví dụ nhận một kiểu kết nối JDBC hoặc trả về đối tượng của thư viện ORM. Khi đó tên gọi có thể là abstraction, nhưng module nghiệp vụ vẫn bị chi tiết hạ tầng chi phối ở mức mã nguồn.

## 9. Quy trình áp dụng DIP và DI khi refactor Java

1. **Xác định chính sách nghiệp vụ cấp cao:** lớp/use case nào chứa quy tắc không nên thay đổi khi đổi DB, API hay phương thức gửi tin?
2. **Tìm phụ thuộc cấp thấp:** kiểm tra các import, trường, constructor và lời gọi trực tiếp tới lớp triển khai hạ tầng.
3. **Định nghĩa hợp đồng ở ranh giới thích hợp:** dùng tên và phương thức thể hiện khả năng nghiệp vụ cần; đặt hợp đồng ở nơi không làm core phải phụ thuộc vào module hạ tầng.
4. **Cho adapter triển khai hợp đồng:** đưa JDBC, SMTP, REST và cấu hình kỹ thuật ra lớp adapter; bảo đảm chúng thực thi đúng ý nghĩa của hợp đồng.
5. **Dùng constructor injection cho dependency bắt buộc:** nhờ đó đối tượng nghiệp vụ nhận đủ cộng tác viên khi được tạo và có thể giữ trường final.
6. **Lắp ghép tại composition root:** chọn adapter theo môi trường, quyết định scope, vòng đời và ai đóng tài nguyên do mình sở hữu.
7. **Kiểm thử theo hai lớp:** fake/stub giúp kiểm tra chính sách độc lập; kiểm thử tích hợp xác minh adapter thật đúng hợp đồng.

### Câu hỏi tự kiểm tra

**1. Một service nhận JdbcOrderStore qua constructor, không tự new JdbcOrderStore. Đã áp dụng DI hay DIP?**

Đã áp dụng DI vì dependency được cung cấp từ ngoài. Chưa đạt mục tiêu DIP nếu JdbcOrderStore là chi tiết kỹ thuật mà service nghiệp vụ trực tiếp phụ thuộc.

**2. Vì sao một interface tên OrderStore nhưng nhận tham số Connection của JDBC vẫn có thể là thiết kế kém?**

Vì hợp đồng vẫn kéo khái niệm JDBC vào tầng nghiệp vụ. Chi tiết kỹ thuật đã rò rỉ qua abstraction; thay hạ tầng có thể buộc service sửa mã.

**3. Khi thay InMemoryOrderStore bằng JdbcOrderStore, file nào nên thay đổi?**

Thông thường phần khởi tạo/cấu hình và adapter mới cần thay đổi. PlaceOrderService không cần đổi nếu cả hai adapter đáp ứng cùng hợp đồng OrderStore với ngữ nghĩa phù hợp.

**4. DIP có bảo đảm code an toàn đồng thời, không rò rỉ tài nguyên hoặc nhất quán giao dịch không?**

Không. DIP định hướng phụ thuộc mã nguồn. DI/composition root giúp làm rõ sở hữu và vòng đời, còn an toàn luồng, quản lý tài nguyên và giao dịch đòi hỏi các quyết định thiết kế riêng.

**Ghi nhớ:** **DIP quyết định hướng phụ thuộc giữa các phần mã nguồn; DI quyết định cách đối tượng nhận dependency lúc chạy.** Kết hợp DIP với constructor injection và composition root bằng Java thuần giúp tầng nghiệp vụ độc lập hơn với hạ tầng, đồng thời tạo nền tảng vững để học DI container, scope và quản lý vòng đời.
