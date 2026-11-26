# Phân biệt dependency injection với dependency inversion

Khi tổ chức phần mềm theo kiến trúc phân tầng, một câu hỏi quan trọng là: tầng ứng dụng lấy những đối tượng cộng tác như repository, cổng gửi thông báo hoặc dịch vụ định giá từ đâu? Nếu tự tạo các lớp triển khai cụ thể, tầng ứng dụng dễ bị gắn chặt với công nghệ bên dưới. Nếu có một thành phần bên ngoài cung cấp các dependency qua constructor hoặc một cơ chế lắp ráp khác, tầng ứng dụng có thể tập trung vào ca sử dụng.

Hai khái niệm thường xuất hiện trong tình huống này là **dependency injection (DI)** và **dependency inversion principle (DIP)**. Chúng liên quan nhưng giải quyết hai câu hỏi khác nhau. DI là kỹ thuật cung cấp một đối tượng mà thành phần cần dùng từ bên ngoài. DIP là nguyên tắc thiết kế quy định hướng phụ thuộc giữa chính sách cấp cao và chi tiết cấp thấp. Một hệ thống có thể dùng DI mà vẫn vi phạm DIP; ngược lại, có thể tuân theo DIP mà không cần một DI container như Spring.

Trong module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED, mục tiêu là học tổ chức phần mềm theo kiến trúc phân tầng. Bài này đặt DI và DIP vào bối cảnh các tầng trình bày, ứng dụng, miền và hạ tầng, đồng thời giải thích cách lắp ráp đối tượng sao cho các ranh giới vẫn có ý nghĩa.

## 1. Dependency là gì?

Một lớp có dependency khi nó cần một lớp, interface hoặc dịch vụ khác để thực hiện trách nhiệm. Ví dụ, một service tạo đơn hàng cần khả năng lưu đơn hàng:

~~~java
public class PlaceOrderService {
    private final OrderRepository orders;

    public PlaceOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public void place(Order order) {
        orders.save(order);
    }
}
~~~

PlaceOrderService phụ thuộc vào OrderRepository. Nó không thể hoàn thành thao tác lưu nếu không có một đối tượng đáp ứng hợp đồng đó. Mối quan hệ này có thể được nhìn ở hai mức:

- **Phụ thuộc mã nguồn:** lớp cần tham chiếu kiểu OrderRepository để biên dịch. Đây là quan hệ thể hiện trong đồ thị package hoặc module.
- **Phụ thuộc lúc chạy:** một đối tượng cụ thể được truyền vào constructor và nhận lời gọi save. Đối tượng đó có thể là adapter JPA, adapter JDBC hoặc một fake dùng trong kiểm thử.

Đừng nhầm dependency với thứ tự gọi phương thức. PlaceOrderService có thể gọi OrderRepository lúc chạy, nhưng hướng phụ thuộc mã nguồn còn phụ thuộc vào kiểu mà service tham chiếu. Nếu trường và constructor dùng JpaOrderRepository, service phụ thuộc trực tiếp vào adapter JPA. Nếu chúng dùng interface OrderRepository, service chỉ phụ thuộc vào hợp đồng.

## 2. Dependency injection: cung cấp dependency từ bên ngoài

**Dependency injection** là kỹ thuật đưa dependency vào một đối tượng thay vì để đối tượng đó tự tìm hoặc tự tạo dependency. Thành phần nhận dependency không chịu trách nhiệm quyết định cách khởi tạo implementation cụ thể.

Ví dụ, PlaceOrderService nhận OrderRepository qua constructor:

~~~java
public class PlaceOrderService {
    private final OrderRepository orders;

    public PlaceOrderService(OrderRepository orders) {
        this.orders = Objects.requireNonNull(orders);
    }

    public void place(Order order) {
        orders.save(order);
    }
}
~~~

Đối tượng gọi tạo repository rồi truyền vào:

~~~java
OrderRepository repository = new JpaOrderRepository(entityManager);
PlaceOrderService service = new PlaceOrderService(repository);
~~~

Dependency đã được inject vào service. Ví dụ này không cần Spring, Guice hay một container nào khác. Một factory hoặc composition root có thể tạo các đối tượng theo cách thủ công và truyền chúng qua constructor.

DI có thể dùng nhiều hình thức:

| Hình thức | Cách hoạt động | Khi nào phù hợp |
|---|---|---|
| Constructor injection | Dependency được truyền khi tạo đối tượng | Dependency bắt buộc; thường là lựa chọn mặc định |
| Setter injection | Dependency được gán sau khi đối tượng được tạo | Dependency tùy chọn hoặc có thể cấu hình lại |
| Method injection | Dependency được truyền vào một phương thức cụ thể | Chỉ cần dependency trong một thao tác, hoặc muốn phạm vi sử dụng rõ ràng |
| Field injection | Container gán trực tiếp vào trường | Có thể gặp trong framework, nhưng làm đối tượng khó khởi tạo độc lập và khó kiểm thử hơn |

Constructor injection làm lộ rõ các dependency bắt buộc, cho phép trường được khai báo final và giúp đối tượng không tồn tại ở trạng thái thiếu dependency. Setter injection có thể hợp lý với dependency thực sự tùy chọn; không nên dùng setter chỉ để né constructor dài mà không xem lại trách nhiệm của lớp. Field injection phụ thuộc vào container để hoàn tất khởi tạo, khiến việc tạo đối tượng trong unit test hoặc dùng ngoài Spring khó hơn.

DI chỉ nói về cách dependency được cung cấp. Nó chưa nói dependency đó có phải abstraction phù hợp hay không. Nếu constructor nhận một lớp hạ tầng cụ thể, việc inject vẫn là DI, nhưng thiết kế có thể vẫn vi phạm nguyên tắc đảo ngược phụ thuộc.

## 3. Dependency inversion principle: đảo hướng phụ thuộc thiết kế

**Dependency inversion principle (DIP)** là nguyên tắc thiết kế có hai ý chính:

1. Chính sách cấp cao không nên phụ thuộc trực tiếp vào chi tiết cấp thấp. Cả hai nên phụ thuộc vào abstraction.
2. Abstraction không nên phụ thuộc vào chi tiết; chi tiết nên phụ thuộc vào abstraction.

Trong ví dụ đặt hàng, tầng ứng dụng chứa chính sách điều phối ca sử dụng. JPA, JDBC hoặc một dịch vụ lưu trữ cụ thể là chi tiết kỹ thuật. Nếu PlaceOrderService import JpaOrderRepository, thay đổi công nghệ persistence có thể kéo theo thay đổi tầng ứng dụng.

Có thể đảo hướng phụ thuộc mã nguồn bằng cách để tầng ứng dụng định nghĩa interface mô tả khả năng nó cần:

~~~java
// application/port/OrderRepository.java
public interface OrderRepository {
    void save(Order order);
}

// application/PlaceOrderService.java
public class PlaceOrderService {
    private final OrderRepository orders;

    public PlaceOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public void place(Order order) {
        orders.save(order);
    }
}

// infrastructure/persistence/JpaOrderRepository.java
public class JpaOrderRepository implements OrderRepository {
    private final EntityManager entityManager;

    public JpaOrderRepository(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public void save(Order order) {
        entityManager.persist(OrderEntity.from(order));
    }
}
~~~

PlaceOrderService chỉ biết OrderRepository. JpaOrderRepository phụ thuộc vào interface để triển khai hợp đồng. Hướng phụ thuộc mã nguồn đã thay đổi:

~~~mermaid
flowchart TB
    subgraph App["Tầng ứng dụng"]
        S["PlaceOrderService"]
        P["OrderRepository<br/>(abstraction / port)"]
        S --> P
    end
    subgraph Infra["Tầng hạ tầng"]
        J["JpaOrderRepository<br/>(implementation / adapter)"]
        DB["JPA / Database"]
        J --> DB
    end
    J -. "implements" .-> P
~~~

Trong sơ đồ, mũi tên nét liền biểu diễn tham chiếu sử dụng trong mã nguồn; đường nét đứt biểu diễn quan hệ hiện thực interface. Tầng ứng dụng sở hữu hợp đồng vì nó xác định khả năng cần có để thực hiện ca sử dụng. Adapter hạ tầng phụ thuộc vào hợp đồng đó để cung cấp khả năng bằng công nghệ cụ thể.

Đây là một cách áp dụng DIP thường gặp trong kiến trúc phân tầng hoặc kiến trúc ports and adapters. Không có quy định mọi interface đều phải nằm trong tầng ứng dụng. Vị trí sở hữu abstraction nên theo trách nhiệm: bên cần một khả năng và định nghĩa ý nghĩa của nó thường là bên phù hợp để sở hữu hợp đồng. Với một hợp đồng tích hợp dùng chung hoặc một ranh giới module khác, vị trí có thể khác.

## 4. Vì sao DI và DIP không phải cùng một khái niệm?

Hãy xem hai ví dụ:

**Ví dụ A — Có DI nhưng chưa tuân DIP**

~~~java
public class PlaceOrderService {
    private final JpaOrderRepository orders;

    public PlaceOrderService(JpaOrderRepository orders) {
        this.orders = orders;
    }
}
~~~

Một đối tượng JpaOrderRepository được truyền từ bên ngoài qua constructor, nên dependency đã được inject. Tuy nhiên, tầng ứng dụng vẫn tham chiếu trực tiếp lớp JPA cụ thể. Cách khởi tạo đã dùng DI nhưng hướng phụ thuộc mã nguồn chưa được đảo ngược.

**Ví dụ B — Có DIP và dùng DI**

~~~java
public class PlaceOrderService {
    private final OrderRepository orders;

    public PlaceOrderService(OrderRepository orders) {
        this.orders = orders;
    }
}
~~~

Service phụ thuộc abstraction OrderRepository và nhận implementation từ bên ngoài. Ví dụ này dùng DI để cung cấp dependency và dùng DIP để giữ hướng phụ thuộc về abstraction.

Có thể tóm tắt sự khác biệt:

| Câu hỏi | Dependency injection | Dependency inversion principle |
|---|---|---|
| Giải quyết điều gì? | Đối tượng nhận dependency bằng cách nào? | Các thành phần nên phụ thuộc theo hướng nào? |
| Trọng tâm | Cách tạo và kết nối đối tượng | Cấu trúc phụ thuộc mã nguồn và quyền sở hữu abstraction |
| Công cụ bắt buộc | Không; có thể truyền thủ công hoặc dùng container | Không; là nguyên tắc thiết kế |
| Dấu hiệu | Constructor, setter, method hoặc container cung cấp dependency | Chính sách cấp cao tham chiếu abstraction; chi tiết hiện thực abstraction |
| Có thể dùng riêng? | Có, kể cả khi inject lớp cụ thể | Có, không nhất thiết phải dùng DI container |

Một hệ thống có thể inject qua constructor nhưng vẫn phụ thuộc vào lớp cụ thể. Ngược lại, một hệ thống có thể đặt interface đúng phía và giữ hướng phụ thuộc phù hợp, nhưng việc tạo implementation vẫn được thực hiện thủ công ở composition root. DI thường hỗ trợ triển khai DIP thuận tiện hơn, nhưng bản thân DI không bảo đảm DIP.

## 5. Lắp ráp đối tượng bằng Spring

Trong ứng dụng Spring, container đóng vai trò tạo bean, quản lý vòng đời và inject dependency. Tầng ứng dụng không cần gọi container để tìm repository; nó chỉ khai báo dependency trong constructor.

Ví dụ:

~~~java
public interface OrderRepository {
    void save(Order order);
}

@Service
public class PlaceOrderService {
    private final OrderRepository orders;

    public PlaceOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public void place(Order order) {
        orders.save(order);
    }
}

@Repository
public class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderJpaRepository jpa;

    public JpaOrderRepository(SpringDataOrderJpaRepository jpa) {
        this.jpa = jpa;
    }

    @Override
    public void save(Order order) {
        jpa.save(OrderEntity.from(order));
    }
}
~~~

Khi component scanning tìm thấy các bean, Spring tạo JpaOrderRepository, tạo PlaceOrderService và truyền bean phù hợp vào constructor. Việc chọn implementation có thể dựa trên một bean duy nhất, qualifier hoặc cấu hình rõ ràng. Nếu có nhiều bean cùng implement OrderRepository mà không có quy tắc chọn, ứng dụng có thể không khởi động do dependency chưa được phân giải.

Với cấu hình tường minh, có thể dùng @Configuration và @Bean:

~~~java
@Configuration
public class OrderConfiguration {

    @Bean
    OrderRepository orderRepository(
            SpringDataOrderJpaRepository jpaRepository) {
        return new JpaOrderRepository(jpaRepository);
    }

    @Bean
    PlaceOrderService placeOrderService(OrderRepository orders) {
        return new PlaceOrderService(orders);
    }
}
~~~

Ví dụ này minh họa composition bằng cấu hình. Trong một ứng dụng thực tế, hãy chọn component scanning hoặc khai báo bean tường minh theo quy ước dự án; không cần khai báo trùng một bean bằng cả hai cách.

## 6. Composition root: nơi quyết định lắp ráp

**Composition root** là điểm trong ứng dụng chịu trách nhiệm tạo và kết nối các thành phần. Đây thường là vùng gần điểm khởi động ứng dụng hoặc cấu hình container, chẳng hạn lớp cấu hình Spring và phương thức main. Nó biết các implementation cụ thể cần dùng trong môi trường hiện tại.

Một cách nhìn đơn giản:

~~~mermaid
flowchart TD
    MAIN["Application entry point / Spring configuration"]
    APP["PlaceOrderService"]
    PORT["OrderRepository abstraction"]
    ADAPTER["JpaOrderRepository"]
    TECH["EntityManager / Database"]
    MAIN -->|"lắp ráp bean"| APP
    MAIN -->|"chọn implementation"| ADAPTER
    APP --> PORT
    ADAPTER -. "implements" .-> PORT
    ADAPTER --> TECH
~~~

Composition root biết cả abstraction lẫn implementation vì nó có nhiệm vụ kết nối chúng. Chính sách nghiệp vụ không cần biết cách chọn adapter. Khi đổi từ JPA sang JDBC, có thể thay cách lắp ráp hoặc cấu hình bean mà không cần sửa PlaceOrderService, miễn là implementation mới đáp ứng hợp đồng.

Trong Spring, container đảm nhận phần lớn việc lắp ráp. Không nên để mọi service tự gọi ApplicationContext.getBean hoặc inject ApplicationContext rồi tra cứu bean theo tên. Cách đó thường được gọi là service locator: dependency bị ẩn trong thân phương thức, người đọc khó biết lớp cần những gì và unit test phải dựng container hoặc mô phỏng cơ chế tra cứu.

## 7. Dependency direction và runtime call flow

Một điểm dễ gây nhầm lẫn là hướng phụ thuộc mã nguồn có thể khác với hướng lời gọi lúc chạy.

Với ví dụ repository:

- Khi biên dịch, PlaceOrderService tham chiếu interface OrderRepository.
- JpaOrderRepository tham chiếu và triển khai interface OrderRepository.
- Khi chạy, PlaceOrderService gọi phương thức save trên đối tượng được inject; đối tượng thực tế có thể là JpaOrderRepository.

Vì thế, lời gọi runtime có thể đi từ tầng ứng dụng đến adapter hạ tầng, trong khi hướng phụ thuộc mã nguồn của adapter đi về abstraction thuộc tầng ứng dụng. Đây là ý nghĩa của việc đảo ngược hướng phụ thuộc trong thiết kế. Không nên dùng sơ đồ runtime call để kết luận ngay rằng mã nguồn của tầng ứng dụng phải import lớp hạ tầng.

~~~mermaid
sequenceDiagram
    participant C as OrderController
    participant A as PlaceOrderService
    participant J as JpaOrderRepository
    participant DB as Database
    C->>A: place(command)
    Note over A,J: Kiểu tham chiếu lúc biên dịch là OrderRepository; đối tượng runtime là JpaOrderRepository
    A->>J: save(order) qua interface OrderRepository
    J->>DB: Persist entity
    DB-->>J: Kết quả
    J-->>A: Hoàn tất
    A-->>C: Kết quả ca sử dụng
~~~

Sơ đồ trình tự diễn tả lời gọi lúc chạy. Sơ đồ package/module mới cho biết lớp nào cần tham chiếu lớp nào để biên dịch. Hai góc nhìn bổ sung cho nhau nhưng không thể thay thế nhau.

## 8. DI giúp kiểm thử độc lập như thế nào?

Khi service nhận dependency qua constructor, kiểm thử có thể truyền một fake hoặc mock mà không cần tạo cơ sở dữ liệu hay khởi động Spring:

~~~java
class InMemoryOrderRepository implements OrderRepository {
    private final Map<UUID, Order> stored = new HashMap<>();

    @Override
    public void save(Order order) {
        stored.put(order.id(), order);
    }

    Optional<Order> findById(UUID id) {
        return Optional.ofNullable(stored.get(id));
    }
}

class PlaceOrderServiceTest {
    @Test
    void savesOrderThroughRepositoryContract() {
        var repository = new InMemoryOrderRepository();
        var service = new PlaceOrderService(repository);
        var order = Order.sample();

        service.place(order);

        assertTrue(repository.findById(order.id()).isPresent());
    }
}
~~~

Ví dụ dùng fake repository để minh họa việc thay implementation. Unit test này xác nhận service sử dụng hợp đồng; nó không chứng minh adapter JPA ghi dữ liệu đúng. Cần có persistence integration test riêng để kiểm tra mapping và hành vi database.

DI cũng làm cho các dependency bắt buộc trở nên rõ ràng. Nếu một service cần repository, clock và cổng gửi thông báo, constructor thể hiện các yêu cầu đó. Nếu danh sách dependency tăng quá nhiều, đó có thể là dấu hiệu lớp đang gánh quá nhiều trách nhiệm hoặc cần một abstraction phù hợp hơn. Không nên gom mọi dependency vào một ServiceContext hoặc ApplicationContext chỉ để làm constructor ngắn; cách đó che giấu mối quan hệ thay vì giải quyết nó.

## 9. Các lỗi thường gặp khi áp dụng DI và DIP

- **Inject implementation cụ thể:** constructor injection có mặt nhưng tầng ứng dụng vẫn tham chiếu JpaOrderRepository. Hãy xác định hợp đồng mà ca sử dụng cần và phụ thuộc vào abstraction phù hợp.
- **Tạo interface cho mọi lớp:** interface không tự động làm thiết kế tốt hơn. Chỉ tạo abstraction khi nó biểu đạt ranh giới, khả năng thay thế, hợp đồng hoặc chính sách cần ổn định.
- **Đưa abstraction về sai phía:** nếu interface chỉ phản ánh API của framework hoặc schema của database, tầng ứng dụng vẫn bị chi tiết thấp cấp chi phối. Hãy để hợp đồng diễn đạt nhu cầu của bên sử dụng.
- **Dùng service locator:** tra cứu dependency bên trong phương thức khiến dependency bị ẩn. Ưu tiên khai báo dependency rõ ràng qua constructor.
- **Field injection cho dependency bắt buộc:** đối tượng có thể tồn tại trước khi field được inject và khó tạo độc lập. Constructor injection thường phù hợp hơn.
- **Có nhiều implementation nhưng không cấu hình lựa chọn:** Spring không biết bean nào cần inject. Dùng qualifier, primary hoặc cấu hình rõ ràng theo ngữ cảnh.
- **Chu trình dependency:** A cần B và B cần A trong constructor có thể khiến container không tạo được bean. Xem lại trách nhiệm, tách hợp đồng hoặc điều chỉnh luồng cộng tác thay vì chỉ che chu trình bằng tra cứu động.
- **Nhầm DI với DIP:** có container không có nghĩa kiến trúc đã đảo ngược phụ thuộc. Hãy kiểm tra kiểu được import và đồ thị module.

## 10. Cân nhắc mức độ áp dụng

DI là một kỹ thuật có ích khi một thành phần cần cộng tác với đối tượng khác và việc tạo implementation nên thuộc về bên lắp ráp. DIP hữu ích khi chính sách cấp cao cần ổn định trước thay đổi của chi tiết cấp thấp. Hai khái niệm hỗ trợ nhau nhưng không bắt buộc mọi lớp phải có interface hoặc mọi ứng dụng phải dùng container.

Với một chương trình nhỏ, có thể truyền dependency thủ công trong main hoặc factory. Với ứng dụng Spring, container giúp quản lý việc tạo bean và kết nối implementation. Với một hệ thống có nhiều adapter hoặc cần thay đổi công nghệ độc lập, abstraction thuộc đúng ranh giới giúp giữ hướng phụ thuộc rõ ràng. Chi phí của interface, cấu hình và ánh xạ cũng cần được cân nhắc; chỉ thêm chúng khi chúng bảo vệ một hợp đồng hoặc ranh giới có ý nghĩa.

Khi xem một lớp trong hệ thống phân tầng, hãy tự hỏi: lớp này cần khả năng nào, dependency được cung cấp ở đâu, kiểu mà nó tham chiếu là abstraction hay chi tiết cụ thể, ai chịu trách nhiệm lắp ráp implementation, và có thể thay implementation trong kiểm thử mà không thay đổi chính sách nghiệp vụ hay không. Trả lời được các câu hỏi đó sẽ giúp phân biệt rõ kỹ thuật DI với nguyên tắc DIP và áp dụng chúng đúng chỗ.
