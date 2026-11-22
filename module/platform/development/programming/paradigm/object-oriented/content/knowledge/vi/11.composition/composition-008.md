# Chuyển thiết kế kế thừa sang kết hợp trong Java

> **Mục tiêu:** Nhận biết khi `extends` đang được dùng chỉ để tái sử dụng mã, chuyển quan hệ kế thừa đó thành các đối tượng cộng tác qua trường dữ liệu và lời gọi phương thức (composition + delegation), đồng thời giữ đúng hành vi và kiểm soát ảnh hưởng tới mã đang sử dụng.

## 1. Vì sao cần chuyển?

**Kế thừa** nói rằng lớp con là một dạng hợp lệ của lớp cha (*is-a*). Với Java, `class Child extends Parent` nhận phương thức, trạng thái có thể truy cập và hợp đồng hành vi của `Parent`; các đối tượng `Child` cũng có thể được sử dụng ở vị trí cần `Parent`.

**Kết hợp** nói rằng một đối tượng **sử dụng** đối tượng khác để hoàn thành công việc (*has-a / uses-a*). Thay vì `extends`, lớp nghiệp vụ giữ một tham chiếu đến thành phần cộng tác và **ủy quyền** cho thành phần đó xử lý phần việc phù hợp.

Ví dụ: `OrderService` **không phải là** một kho lưu đơn hàng; nó **sử dụng** `OrderRepository` để lưu đơn hàng. Cho `OrderService extends OrderStore` chỉ vì muốn dùng lại `save()` là dấu hiệu lệch mô hình.

Dấu hiệu nên xem xét chuyển đổi:

- Lớp con gọi vài phương thức của lớp cha nhưng không thực sự mang ý nghĩa *is-a*.
- Lớp con vô tình công khai các thao tác của lớp cha, như `deleteAll()` hay `resetConnection()`.
- Một thay đổi trong lớp cha làm hỏng nhiều lớp con, dù các lớp con chỉ cần một phần chức năng.
- Việc giả lập phụ thuộc khi kiểm thử buộc phải kế thừa, ghi đè hoặc tạo đối tượng hạ tầng thật.
- Muốn thay thuật toán / cách lưu trữ / dịch vụ gửi thông báo tại thời điểm chạy nhưng phải tạo thêm nhiều lớp con.
- Có nhu cầu ghi đè những phương thức với tiền điều kiện hoặc hậu điều kiện không còn phù hợp với hợp đồng lớp cha (rủi ro vi phạm **Liskov Substitution Principle – LSP**).

**Không có quy tắc “mọi kế thừa đều xấu”.** Giữ kế thừa khi mối quan hệ phân loại thật sự đúng và lớp con duy trì đầy đủ hợp đồng của lớp cha. Chuyển đổi khi việc kế thừa chủ yếu nhằm vay mượn triển khai hoặc dẫn đến liên kết quá chặt.

## 2. Trước khi chuyển: nghiệp vụ kế thừa lớp lưu trữ

Ví dụ sau dùng Java 17+, lưu trong bộ nhớ để tập trung vào thiết kế. Trên hệ thống thực, `OrderStore` có thể là một lớp truy cập JDBC, JPA hoặc API từ xa.

~~~java
import java.util.HashMap;
import java.util.Map;

record Order(long id, long totalCents) {}

class OrderStore {
    private final Map<Long, Order> data = new HashMap<>();

    public void save(Order order) {
        data.put(order.id(), order);
    }

    public Order find(long id) {
        return data.get(id);
    }

    public void deleteAll() {
        data.clear();
    }
}

// Thiết kế cũ: quan hệ "OrderService is-a OrderStore" không đúng.
class OrderService extends OrderStore {
    public void place(Order order) {
        if (order == null || order.totalCents() <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
        save(order); // Kế thừa để tái sử dụng phương thức lưu
    }
}
~~~

Vấn đề không nằm ở cú pháp Java mà ở **hợp đồng công khai**: mọi nơi có `OrderService` đều gọi được `deleteAll()`, `find()` và `save()` dù đó là thao tác ở tầng lưu trữ. Thay đổi `OrderStore` có thể tác động trực tiếp đến `OrderService`. Nếu có nhiều `OrderService` với kiểu lưu trữ khác nhau, số lớp kế thừa tiếp tục tăng.

Cần phân biệt hai loại tương thích khi chuyển:

1. **Hành vi nghiệp vụ:** gọi `place()` vẫn kiểm tra đơn hàng hợp lệ và lưu đúng một lần; dữ liệu đơn hàng vẫn được tìm thấy.
2. **API và kiểu tĩnh:** mã cũ có thể đang truyền `OrderService` vào tham số kiểu `OrderStore` hoặc gọi trực tiếp `deleteAll()`. Bỏ `extends` làm các chỗ đó không còn biên dịch. Đây có thể là thay đổi mong muốn về thiết kế nhưng cần kiểm tra người gọi và chuẩn bị lộ trình chuyển đổi.

## 3. Sau khi chuyển: phụ thuộc vào hợp đồng nhỏ

Tách thành bốn vai trò độc lập: mô hình dữ liệu, cổng lưu trữ (`OrderRepository`), triển khai lưu trữ và dịch vụ nghiệp vụ.

**Order.java**

~~~java
public record Order(long id, long totalCents) {}
~~~

**OrderRepository.java**

~~~java
import java.util.Optional;

public interface OrderRepository {
    void save(Order order);
    Optional<Order> findById(long id);
}
~~~

**InMemoryOrderRepository.java**

~~~java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class InMemoryOrderRepository implements OrderRepository {
    private final Map<Long, Order> data = new ConcurrentHashMap<>();

    @Override
    public void save(Order order) {
        data.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(long id) {
        return Optional.ofNullable(data.get(id));
    }
}
~~~

**OrderService.java**

~~~java
import java.util.Objects;
import java.util.Optional;

public final class OrderService {
    private final OrderRepository repository;

    // Constructor injection: phụ thuộc được cấp từ ngoài.
    public OrderService(OrderRepository repository) {
        this.repository = Objects.requireNonNull(repository, "repository");
    }

    public void place(Order order) {
        if (order == null || order.totalCents() <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
        repository.save(order); // Ủy quyền đúng trách nhiệm
    }

    public Optional<Order> find(long id) {
        return repository.findById(id);
    }
}
~~~

**Main.java**

~~~java
public class Main {
    public static void main(String[] args) {
        OrderRepository repository = new InMemoryOrderRepository();
        OrderService service = new OrderService(repository);

        service.place(new Order(101L, 125_000L));
        System.out.println(service.find(101L));
        // Optional[Order[id=101, totalCents=125000]]
    }
}
~~~

Tạo năm tệp trên cùng thư mục rồi chạy Java 17+: `javac Order.java OrderRepository.java InMemoryOrderRepository.java OrderService.java Main.java` rồi `java Main` (với terminal có Java SDK). Ví dụ sử dụng `totalCents` dạng số nguyên để tránh sai số tiền tệ do `double`.

**Kết quả thay đổi:** `OrderService` chỉ bộc lộ các thao tác nghiệp vụ cần thiết; lưu trữ thực tế có thể đổi sang JDBC/JPA bằng cách thay đối tượng triển khai `OrderRepository` mà không sửa thuật toán `place()`. `OrderService` là một lớp cộng tác với repository thay vì là lớp con của repository.

~~~mermaid
classDiagram
    class OrderService {
        -OrderRepository repository
        +place(Order)
        +find(long)
    }
    class OrderRepository {
        <<interface>>
        +save(Order)
        +findById(long)
    }
    class InMemoryOrderRepository {
        -Map data
        +save(Order)
        +findById(long)
    }
    OrderService --> OrderRepository : ủy quyền
    InMemoryOrderRepository ..|> OrderRepository : triển khai
~~~

Trong sơ đồ, mũi tên từ `OrderService` sang `OrderRepository` biểu diễn phụ thuộc/ủy quyền. Với **constructor injection**, vòng đời repository có thể do bên ngoài quản lý và có thể được chia sẻ; không nhất thiết dùng hình thoi đen (*strong ownership composition* trong UML). Ý tưởng thiết kế ở đây là **kết hợp các đối tượng**, không phải khẳng định dịch vụ sở hữu độc quyền vòng đời của repository.

## 4. So sánh trực tiếp

| Tiêu chí | `OrderService extends OrderStore` | `OrderService` chứa `OrderRepository` |
|---|---|---|
| Quan hệ mô hình | Ngầm tuyên bố dịch vụ **là** kho lưu trữ | Dịch vụ **dùng** kho lưu trữ |
| Tái sử dụng chức năng | Qua phương thức kế thừa | Qua lời gọi `repository.save(...)` |
| API công khai | Có thể thừa hưởng cả thao tác kỹ thuật | Chỉ công khai thao tác dịch vụ tự định nghĩa |
| Thay triển khai lưu trữ | Dễ phụ thuộc vào cấu trúc lớp cha | Thay đối tượng triển khai giao diện |
| Kiểm thử đơn vị | Dễ phụ thuộc lớp cha và trạng thái hạ tầng | Tiêm fake/stub/spy vào constructor |
| Liên kết | Chặt với triển khai và quan hệ kiểu `extends` | Chặt với hợp đồng `OrderRepository` nhỏ |
| Chi phí | Ít trường và lời gọi ủy quyền | Thêm một lớp trừu tượng và wiring phụ thuộc |

**Lưu ý:** `implements OrderRepository` ở lớp lưu trữ vẫn là đa hình qua giao diện Java. Nguyên tắc “ưu tiên kết hợp hơn kế thừa” chủ yếu nhắm tới **kế thừa triển khai không phù hợp**; không cấm dùng interface.

## 5. Quy trình refactor an toàn trên mã đang chạy

1. **Khoanh vùng quan hệ kế thừa:** xác định lớp con muốn đổi, các phương thức `super.method()`, phương thức `protected`, trường lớp cha, constructor và nơi dùng biến kiểu cha. Không suy luận chỉ từ tên lớp.
2. **Chốt hợp đồng hành vi:** liệt kê đầu vào hợp lệ/không hợp lệ, ngoại lệ, thứ tự gọi, thao tác dữ liệu, giao dịch và kết quả. Chụp lại các ca kiểm thử có giá trị trước khi đổi cấu trúc.
3. **Tách trách nhiệm:** chọn thành phần thực sự làm việc (repository, formatter, sender, policy…), tạo interface nhỏ khi cần thay thế triển khai hoặc dựng test double. Nếu chỉ có một cộng tác viên ổn định và không cần abstraction, giữ lớp cụ thể cũng hợp lý.
4. **Tiêm thành phần:** thêm trường `private final`, cấp qua constructor; ưu tiên dependency injection hơn việc `new ConcreteRepository()` ngay trong dịch vụ.
5. **Chuyển từng lời gọi:** đổi `save(order)` hoặc `super.save(order)` thành `repository.save(order)`; chỉ thêm phương thức ủy quyền trong dịch vụ khi thực sự là một phần API nghiệp vụ.
6. **Di chuyển người gọi:** sửa nơi trước đây dựa vào việc dịch vụ có kiểu của repository hoặc sử dụng các phương thức kế thừa. Nếu API được người khác sử dụng, xác định chiến lược tương thích và phiên bản phát hành.
7. **Bỏ `extends`:** sau khi không còn truy cập trạng thái/phương thức cha và đã xử lý các vị trí nhận kiểu cha, xóa quan hệ kế thừa cùng các override chỉ phục vụ cơ chế cũ.
8. **Kiểm thử và rà soát:** chạy test đơn vị, tích hợp và kiểm tra các trường hợp dữ liệu thật; xem lại vòng đời, luồng song song, transaction, logging và chi phí tạo đối tượng.

~~~mermaid
flowchart TD
    A[Nhận diện extends sai trách nhiệm] --> B[Liệt kê hợp đồng và caller]
    B --> C[Tách thành phần và interface khi cần]
    C --> D[Tiêm phụ thuộc qua constructor]
    D --> E[Thay lời gọi kế thừa bằng ủy quyền]
    E --> F[Di chuyển caller và gỡ extends]
    F --> G{Test hành vi và API đạt?}
    G -->|Có| H[Hoàn tất refactor]
    G -->|Chưa| I[Sửa chênh lệch rồi kiểm thử lại]
    I --> G
~~~

Ở dự án lớn, hai bước **di chuyển người gọi** và **gỡ kế thừa** có thể nằm ở nhiều commit hoặc nhiều phiên bản triển khai. Đừng tuyên bố thay đổi tương thích nếu chữ ký hoặc khả năng gán kiểu đã bị thay đổi.

## 6. Kiểm thử đúng phần cần bảo toàn

Với composition, có thể dùng một đối tượng ghi nhận lời gọi thay cho cơ sở dữ liệu. Ví dụ dưới đây giả định các tệp `Order.java`, `OrderRepository.java`, `OrderService.java` đã tồn tại, sử dụng JUnit Jupiter 5.

**OrderServiceTest.java**

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.Optional;

class OrderServiceTest {
    static final class RecordingRepository implements OrderRepository {
        Order saved;
        int saveCount;

        @Override
        public void save(Order order) {
            saved = order;
            saveCount++;
        }

        @Override
        public Optional<Order> findById(long id) {
            return Optional.ofNullable(saved)
                    .filter(order -> order.id() == id);
        }
    }

    @Test
    void validOrderIsSavedOnce() {
        RecordingRepository repository = new RecordingRepository();
        OrderService service = new OrderService(repository);
        Order order = new Order(7L, 50_000L);

        service.place(order);

        assertSame(order, repository.saved);
        assertEquals(1, repository.saveCount);
        assertEquals(Optional.of(order), service.find(7L));
    }

    @Test
    void invalidOrderDoesNotReachRepository() {
        RecordingRepository repository = new RecordingRepository();
        OrderService service = new OrderService(repository);

        assertThrows(IllegalArgumentException.class,
                () -> service.place(new Order(7L, 0L)));
        assertThrows(IllegalArgumentException.class,
                () -> service.place(null));
        assertEquals(0, repository.saveCount);
    }

    @Test
    void nullDependencyIsRejectedImmediately() {
        assertThrows(NullPointerException.class,
                () -> new OrderService(null));
    }
}
~~~

Các test kiểm tra **kết quả nghiệp vụ và tương tác ở ranh giới**: đơn hợp lệ được lưu đúng một lần, đơn không hợp lệ không tác động repository, phụ thuộc bắt buộc được kiểm tra. Không cần viết test xác nhận rằng lớp có trường tên `repository` hoặc rằng mã nguồn chứa dòng `repository.save(...)`: đó là chi tiết triển khai.

Bên cạnh các test trên, nên giữ một **integration test** dùng repository thật nếu thay đổi liên quan đến database: kiểm tra persistence, rollback, transaction boundary và việc đọc lại dữ liệu, bởi fake không chứng minh được các hành vi này.

## 7. Những rủi ro dễ bị bỏ sót

| Tình huống | Rủi ro khi bỏ `extends` | Cách xử lý |
|---|---|---|
| Caller gán `OrderService` cho `OrderStore` | Lỗi biên dịch do mất quan hệ subtype | Chuyển caller sang `OrderRepository` hoặc API nghiệp vụ phù hợp |
| Caller gọi phương thức kế thừa | Thay đổi API công khai | Kiểm kê usages; quyết định chuyển, giữ façade có chủ đích hoặc thay đổi phiên bản |
| Override `protected` hook / dùng `super` | Mất điểm mở rộng và thứ tự thực thi | Đưa hành vi thành policy/strategy hay callback có tên rõ |
| Lớp cha giữ trạng thái `protected` | Trạng thái không còn ở cùng đối tượng | Xác định chủ sở hữu trạng thái và quy tắc đồng bộ; không nhân bản dữ liệu vô thức |
| `new` repository ở từng lần gọi | Mất kiểm soát vòng đời, tốn tài nguyên | Tiêm một phụ thuộc đúng scope; đóng tài nguyên ở chủ sở hữu vòng đời |
| Các lớp con được framework xử lý đặc biệt | Metadata/proxy/ORM mapping có thể đổi | Kiểm tra JPA inheritance, Spring AOP, serialize và lifecycle dự án cụ thể |
| Dịch vụ bọc quanh thành phần nhưng công khai lại tất cả phương thức | Thiết kế vẫn rò rỉ API hạ tầng | Chỉ ủy quyền các thao tác phục vụ trách nhiệm của dịch vụ |
| Repository dùng chung và có trạng thái thay đổi | Race condition nếu các luồng gọi đồng thời | Đảm bảo thread safety phù hợp; ví dụ trên dùng `ConcurrentHashMap` cho bộ nhớ |
| Interface quá rộng hoặc một interface cho mọi lớp | Phát sinh boilerplate, abstraction giả | Đặt interface theo nhu cầu của client; chỉ tách khi đem lại khả năng thay thế hoặc ranh giới rõ |

Với mã giao dịch, cần đặc biệt kiểm tra chỗ đặt `@Transactional`: chuyển phương thức giữa các bean có thể thay đổi cách proxy của Spring bắt lời gọi. Với entity JPA, `extends` có thể đang mang ý nghĩa ánh xạ inheritance thật; không thay nó một cách máy móc khi chưa xác nhận schema và migration.

## 8. Khi nào kết hợp không phải lựa chọn tốt nhất?

- **Quan hệ phân loại đúng và ổn định:** `Circle extends Shape` có thể phù hợp nếu `Shape` định nghĩa một hợp đồng hình học thực sự và mọi `Circle` tuân thủ hợp đồng đó.
- **Framework yêu cầu lớp cơ sở:** một số adapter hay framework sử dụng template method và các hook cụ thể; trước khi bỏ kế thừa cần hiểu điểm mở rộng được hỗ trợ.
- **Đối tượng chỉ bọc một hành vi nhỏ, không cần đa triển khai:** có thể dùng trực tiếp một dependency cụ thể; không cần ép tạo interface cho mọi lớp.
- **Hành vi có thể biểu diễn tốt hơn bằng tham số/hàm:** với biến thể rất nhỏ, truyền `Function`/`Predicate` đôi khi gọn hơn cả tạo hierarchy hoặc Strategy riêng.

Câu hỏi quyết định: **“Mỗi đối tượng lớp con có thể thay thế một đối tượng lớp cha mà vẫn đúng mọi lời hứa của lớp cha không?”** Nếu không, và mục tiêu thật sự chỉ là sử dụng một chức năng, hãy ưu tiên kết hợp.

## 9. Bài tập áp dụng

Một `ReportService extends CsvFormatter` đang gọi `format(report)` vì cần xuất CSV. Nay có thêm JSON và XML.

Hãy phác thảo cách chuyển sang `ReportService` chứa `ReportFormatter`, trong đó `ReportFormatter` có `String format(Report report)`. Triển khai `CsvReportFormatter` và `JsonReportFormatter` theo interface; cấp implementation qua constructor. Kiểm tra rằng `ReportService` không còn thừa hưởng bất kỳ phương thức cấu hình CSV nào, và test có thể tiêm formatter giả để kiểm tra nội dung trả về.

**Điểm cần tự đánh giá:** Bạn đã loại bỏ mối quan hệ *is-a* giả chưa? Hợp đồng nghiệp vụ có còn rõ không? Có thể thay formatter mà không sửa `ReportService` không? Các caller trước đó phụ thuộc vào `CsvFormatter` đã được xử lý chưa?

---

**Ghi nhớ:** Chuyển từ kế thừa sang kết hợp không chỉ là thay `extends` bằng một trường đối tượng. Phải **đặt đúng trách nhiệm, tách hợp đồng, ủy quyền minh bạch, xử lý caller và bảo toàn hành vi có kiểm chứng**.