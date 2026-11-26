# Stream và Streamable

Trong chương **Kiểu kết quả truy vấn** của Spring Data Commons (`SPRING_DATA_COMMONS`), `Stream<T>` và `Streamable<T>` cung cấp hai hợp đồng khác nhau để xử lý nhiều kết quả. Chọn đúng hợp đồng ảnh hưởng đến cách duyệt dữ liệu, vòng đời tài nguyên và lượng dữ liệu ứng dụng có thể giữ trong bộ nhớ.

`Stream` thuộc Java; `Streamable` là abstraction của Spring Data Commons. Việc một repository hỗ trợ streaming từ kho dữ liệu còn tùy module, provider và driver. Các ví dụ chính trong bài dùng repository imperative; phần transaction được ghi rõ khi nói riêng về Spring Data JPA.

## 1. Phân biệt hai hợp đồng

| Khía cạnh | `Stream<T>` | `Streamable<T>` |
| --- | --- | --- |
| Package | `java.util.stream`. | `org.springframework.data.util`. |
| Vai trò | Pipeline xử lý một nguồn dữ liệu. | Abstraction mở rộng khả năng duyệt của `Iterable`. |
| Cách dùng thường gặp | Tạo pipeline rồi thực hiện một terminal operation. | Duyệt, map, filter, nối nguồn hoặc lấy một Stream. |
| Đọc lại | Không tái sử dụng cùng một Stream sau khi đã tiêu thụ. | Có thể tạo các lượt duyệt từ nguồn; kết quả phụ thuộc đặc tính nguồn. |
| Tài nguyên từ repository | Có thể giữ cursor, connection hoặc tài nguyên tương ứng của store. | Bản thân interface không cung cấp hợp đồng đóng cursor như Stream. |
| Bảo đảm ít bộ nhớ | Không có bảo đảm chỉ từ tên kiểu. | Không có bảo đảm chỉ từ tên kiểu. |

Không suy từ chữ “stream” rằng hai kiểu đều đọc từng bản ghi trực tiếp từ database. Cần phân biệt khả năng tạo pipeline Java với cơ chế lấy dữ liệu thực tế của module.

## 2. Repository minh họa

Giả sử `Ticket` đã được mapping theo module, có:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất. |
| `status` | `TicketStatus` | Ví dụ `OPEN`, `CLOSED`. |
| `priority` | `TicketPriority` | Ví dụ `LOW`, `HIGH`. |
| `queueCode` | `String` | Mã hàng đợi. |

Các getter tương ứng như `getId()`, `getStatus()`, `getQueueCode()` được dùng trong ví dụ.

```java
import java.util.stream.Stream;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.util.Streamable;

public interface TicketRepository extends CrudRepository<Ticket, Long> {

    Stream<Ticket> streamByStatusOrderByIdAsc(TicketStatus status);

    Streamable<Ticket> findByStatusOrderByIdAsc(TicketStatus status);

    Streamable<Ticket> findByPriorityOrderByIdAsc(
        TicketPriority priority
    );
}
```

Cấu hình repository, domain mapping và kết nối được chuẩn bị theo module đang dùng. Không phải mọi Spring Data module đều hỗ trợ `Stream<T>` làm kiểu trả về query method.

Đối với module có hỗ trợ, dạng Stream có thể dùng cơ chế streaming riêng của store, thay vì chỉ lấy một danh sách rồi bọc bằng `list.stream()`. Hợp đồng chung được trình bày trong [Spring Data Commons — Streaming Query Results](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.query-streaming).

## 3. Dùng Stream trong một phạm vi đóng tài nguyên rõ ràng

Một Stream Java có các thao tác trung gian như `map`, `filter` và thao tác kết thúc như `forEach`, `count`, `collect`, `findFirst`.

Ví dụ cơ bản:

```java
try (Stream<Ticket> tickets =
        repository.streamByStatusOrderByIdAsc(TicketStatus.OPEN)) {

    tickets
        .map(Ticket::getId)
        .forEach(System.out::println);
}
```

Với kết quả streaming từ repository, dùng `try-with-resources` để đóng Stream kể cả khi xử lý thành công, dừng sớm hoặc ném exception.

Việc thực hiện terminal operation không thay thế trách nhiệm đóng tài nguyên. `Stream` triển khai `AutoCloseable`; các nguồn có tài nguyên I/O cần được đóng đúng phạm vi. Xem [Java Stream API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).

### Chỉ tiêu thụ một lần

Đoạn sau tái sử dụng cùng một Stream:

```java
try (Stream<Ticket> tickets =
        repository.streamByStatusOrderByIdAsc(TicketStatus.OPEN)) {

    long count = tickets.count();

    // Sai: Stream đã được tiêu thụ.
    tickets.forEach(System.out::println);
}
```

Nếu cần vừa xử lý vừa đếm, thực hiện trong một lượt duyệt phù hợp. Nếu chủ động mở query lần nữa, đó là một lần đọc mới, có thể quan sát dữ liệu khác và phát sinh thêm chi phí.

### Dừng sớm vẫn cần đóng

```java
import java.util.Optional;
import java.util.stream.Stream;

try (Stream<Ticket> tickets =
        repository.streamByStatusOrderByIdAsc(TicketStatus.OPEN)) {

    Optional<Long> firstId = tickets
        .map(Ticket::getId)
        .findFirst();

    firstId.ifPresent(System.out::println);
}
```

Ví dụ lấy định danh đầu tiên theo thứ tự ID đã khai báo. Việc chỉ cần một phần tử không làm mất yêu cầu đóng Stream.

Nếu yêu cầu nghiệp vụ luôn chỉ lấy một kết quả, nên cân nhắc một query giới hạn phù hợp với module để thể hiện ý định ngay ở hợp đồng repository.

## 4. Vòng đời transaction: ví dụ riêng cho JPA

Với Spring Data JPA, việc tiêu thụ một query Stream thường cần diễn ra khi persistence context và tài nguyên đọc còn mở. Một cách tổ chức rõ ràng là mở Stream, duyệt và đóng trong cùng service transaction.

```java
import java.util.Iterator;
import java.util.Objects;
import java.util.function.Consumer;
import java.util.stream.Stream;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TicketExportService {

    private final TicketRepository repository;

    public TicketExportService(TicketRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public long exportOpenIds(Consumer<Long> sink) {
        Objects.requireNonNull(sink, "sink");

        try (Stream<Ticket> tickets =
                repository.streamByStatusOrderByIdAsc(
                    TicketStatus.OPEN
                )) {

            Iterator<Ticket> iterator = tickets.iterator();
            long exported = 0;

            while (iterator.hasNext()) {
                Ticket ticket = iterator.next();
                sink.accept(ticket.getId());
                exported++;
            }

            return exported;
        }
    }
}
```

Giả định trong ví dụ:

- `TicketRepository` được module JPA triển khai.
- Transaction management đã được bật.
- Service được gọi qua Spring bean/proxy để annotation transaction có hiệu lực.
- `sink.accept(...)` được gọi trong lúc vòng duyệt đang chạy.

Luồng tài nguyên là:

```text
Bắt đầu service transaction
  -> gọi query streaming
  -> đọc từng phần tử và chuyển ID cho sink
  -> đóng Stream
Kết thúc transaction
```

Cấu hình transaction ở ranh giới service giúp bao trùm cả giai đoạn tiêu thụ kết quả. Các query method tự khai báo không mặc nhiên có cùng cấu hình transaction với mọi method CRUD cơ sở. Xem [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html).

### Trả Stream ra ngoài transaction cần một hợp đồng khác

Ví dụ có rủi ro về vòng đời:

```java
@Transactional(readOnly = true)
public Stream<Ticket> openTickets() {
    return repository.streamByStatusOrderByIdAsc(
        TicketStatus.OPEN
    );
}
```

Nếu method này là ranh giới transaction ngoài cùng, transaction kết thúc khi method trả về, trong khi caller có thể mới bắt đầu tiêu thụ Stream sau đó.

Chỉ đặt annotation ở method tạo Stream chưa bảo đảm tài nguyên còn sống trong toàn bộ quá trình duyệt. Việc trả Stream cho caller cần quy định rõ ai giữ phạm vi tài nguyên và ai đóng.

Cũng không trả một Stream từ bên trong `try-with-resources` rồi dùng nó bên ngoài: khi ra khỏi block, tài nguyên đã được đóng.

Không suy rằng mọi store đều cần cùng một mô hình transaction như JPA. Với module khác, áp dụng hợp đồng tài nguyên mà module đó hỗ trợ.

## 5. Streaming không tự bảo đảm bộ nhớ bị chặn ở một mức nhỏ

Lợi ích kỳ vọng của đọc tuần tự có thể bị mất ở nhiều chỗ.

### Thu thập toàn bộ kết quả

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

try (Stream<Ticket> tickets =
        repository.streamByStatusOrderByIdAsc(TicketStatus.OPEN)) {

    List<Ticket> all = tickets.collect(Collectors.toList());
}
```

Dù nguồn có streaming, `all` vẫn giữ toàn bộ phần tử đã thu thập. Với tập kết quả lớn, đổi `List<T>` thành `Stream<T>` rồi gom lại thành List không giải quyết mục tiêu giới hạn bộ nhớ ở phía ứng dụng.

### Thao tác có trạng thái

Một số thao tác pipeline cần giữ nhiều dữ liệu:

- `sorted(...)` có thể phải đọc toàn bộ nguồn trước khi phát kết quả theo thứ tự.
- `distinct()` cần ghi nhớ các giá trị đã gặp.
- `collect(...)` phụ thuộc cấu trúc tích lũy được chọn.

Nếu thứ tự là một phần của truy vấn, thể hiện nó ở query hoặc cơ chế sort của repository giúp kho dữ liệu có cơ hội xử lý theo khả năng của nó.

### Bộ đệm và entity được giữ lại

Kiểu trả về không quyết định toàn bộ cách provider hoặc driver lấy dữ liệu. Cần kiểm chứng cơ chế đọc và cấu hình fetch của môi trường thực tế.

Trong JPA, cũng cần xét lượng entity persistence context giữ trong quá trình duyệt. `readOnly = true` không phải một API bảo đảm bộ nhớ luôn hằng số.

Khi xử lý rất nhiều kết quả, có thể cân nhắc projection/DTO, đọc theo từng phần hoặc cơ chế batch phù hợp với module. Mỗi lựa chọn cần giữ đúng điều kiện, thứ tự và yêu cầu nhất quán dữ liệu.

### Limit ở Java và giới hạn truy vấn

```java
tickets.limit(100);
```

là thao tác trên pipeline Java. Nó không tự chứng minh câu query được gửi tới store đã có giới hạn 100, hoặc driver chưa tải trước nhiều dữ liệu hơn.

Tương tự, fetch size của driver không đồng nghĩa page size hay tổng số kết quả tối đa. Muốn giới hạn tập kết quả ở hợp đồng truy vấn, cần dùng khả năng giới hạn được module hỗ trợ.

## 6. Streamable cung cấp thao tác thuận tiện trên Iterable

`Streamable<T>` mở rộng `Iterable<T>` và `Supplier<Stream<T>>`. Nó có các thao tác như `stream()`, `map`, `filter`, `and`, `toList`, `toSet`. `stream()` tạo một Stream không song song từ nguồn Iterable. Xem [API Streamable](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/util/Streamable.html).

Ví dụ:

```java
import java.util.List;

import org.springframework.data.util.Streamable;

Streamable<Ticket> open =
    repository.findByStatusOrderByIdAsc(TicketStatus.OPEN);

Streamable<Long> supportIds = open
    .filter(ticket -> "SUPPORT".equals(ticket.getQueueCode()))
    .map(Ticket::getId);

List<Long> ids = supportIds.toList();
```

Trong đoạn này, query method lọc theo trạng thái. Phép lọc `queueCode` và map ID được viết sau khi nhận kết quả, nên là xử lý phía Java; chúng không tự được đẩy ngược vào điều kiện hoặc projection của query đã chạy.

Nếu nghiệp vụ cần lọc hàng đợi ngay tại store, hãy khai báo một query có cả điều kiện trạng thái lẫn hàng đợi. Nếu chỉ cần một số trường, dùng projection được module hỗ trợ thay vì mặc định rằng `map` làm giảm các trường được truy vấn.

### Lazy ở pipeline không đồng nghĩa lazy ở database

Các phép biến đổi có thể được áp dụng khi duyệt nguồn. Điều này không chứng minh kết quả repository chưa được tải trước đó.

Với kiểu kết quả `Streamable` thông thường của repository, nên xem đây là sự tiện lợi cho tập kết quả nhiều phần tử, không coi nó là cam kết về một cursor database đang mở.

### Đọc nhiều lượt phụ thuộc nguồn

Ví dụ với một nguồn trong bộ nhớ cố định:

```java
Streamable<Long> numbers = Streamable.of(1L, 2L, 3L);

long firstCount = numbers.stream().count();
long secondCount = numbers.stream().count();
```

Hai lời gọi tạo hai pipeline, mỗi lượt đếm được ba phần tử.

Nhưng `Streamable` không tự tạo snapshot hoặc cache cho mọi nguồn. Nếu bọc một Iterable thay đổi, kết quả các lượt có thể khác nhau. Nếu dùng supplier tùy chỉnh, supplier phải cung cấp nguồn có vòng đời phù hợp cho mỗi lượt.

Không bọc một query Stream đã mở bằng supplier luôn trả lại chính Stream đó rồi kỳ vọng có thể đọc lặp an toàn.

## 7. And của Streamable là nối nguồn, không kết hợp điều kiện query

Ví dụ độc lập, chỉ dùng dữ liệu trong bộ nhớ:

```java
Streamable<Long> first = Streamable.of(101L, 103L);
Streamable<Long> second = Streamable.of(102L, 103L);

List<Long> ids = first.and(second).toList();
```

Kết quả theo thứ tự nguồn:

```text
101, 103, 102, 103
```

`and` nối các phần tử. Nó không tự loại trùng, không sắp xếp chung và không có nghĩa phép AND giữa hai điều kiện truy vấn.

Với repository:

```java
Streamable<Ticket> open =
    repository.findByStatusOrderByIdAsc(TicketStatus.OPEN);

Streamable<Ticket> high =
    repository.findByPriorityOrderByIdAsc(TicketPriority.HIGH);

Streamable<Ticket> combined = open.and(high);
```

Hai query method đã được gọi riêng. `and` không tự hợp nhất chúng thành một câu query hay một phép UNION tại store.

Một ticket vừa OPEN vừa HIGH có thể xuất hiện trong cả hai nguồn và do đó xuất hiện hai lần khi nối. Thứ tự tăng dần trong từng nguồn cũng không tạo ra thứ tự tăng dần của toàn bộ kết quả nối.

Nếu cần một tập dữ liệu đã lọc, loại trùng, sắp xếp hoặc phân trang chung theo hợp đồng cụ thể, nên biểu đạt yêu cầu đó bằng truy vấn phù hợp.

## 8. Tạo kiểu kết quả miền nghiệp vụ bằng Streamable

Có thể dùng một wrapper để đặt những thao tác liên quan đến tập ticket vào một kiểu có tên rõ nghĩa.

```java
import java.util.Iterator;
import java.util.Objects;

import org.springframework.data.util.Streamable;

public final class Tickets implements Streamable<Ticket> {

    private final Streamable<Ticket> source;

    public Tickets(Streamable<Ticket> source) {
        this.source = Objects.requireNonNull(source, "source");
    }

    @Override
    public Iterator<Ticket> iterator() {
        return source.iterator();
    }

    public Streamable<Long> ids() {
        return source.map(Ticket::getId);
    }

    public Tickets inQueue(String queueCode) {
        Objects.requireNonNull(queueCode, "queueCode");

        return new Tickets(
            source.filter(ticket ->
                queueCode.equals(ticket.getQueueCode())
            )
        );
    }
}
```

Trong module có hỗ trợ cơ chế wrapper này, repository có thể khai báo thêm:

```java
Tickets findTicketsByStatus(TicketStatus status);
```

Wrapper triển khai `Streamable` và có constructor nhận một `Streamable`. Ngoài constructor, cơ chế chung còn hỗ trợ static factory tên `of` hoặc `valueOf` với đối số phù hợp. Xem [Spring Data Commons — Returning Custom Streamable Wrapper Types](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.collections-and-iterables.streamable-wrapper).

Phía gọi có thể viết:

```java
List<Long> ids = repository
    .findTicketsByStatus(TicketStatus.OPEN)
    .inQueue("SUPPORT")
    .ids()
    .toList();
```

`inQueue` trong wrapper vẫn là xử lý trên nguồn phía Java. Nó không biến thành điều kiện query chỉ vì wrapper được trả từ repository.

Wrapper này tổ chức hành vi của tập kết quả; nó không bổ sung cơ chế streaming database hay trách nhiệm đóng tài nguyên mà `Streamable` chưa quy định.

## 9. Chọn kiểu kết quả theo nhu cầu thực tế

| Nhu cầu | Lựa chọn để cân nhắc |
| --- | --- |
| Tập kết quả có quy mô kiểm soát, muốn dùng map/filter thuận tiện | `Streamable<T>`. |
| Cần xử lý tuần tự với nguồn streaming được module hỗ trợ | `Stream<T>`, kèm phạm vi tiêu thụ và đóng tài nguyên. |
| Muốn giữ toàn bộ kết quả để truy cập nhiều lần như một collection | `List<T>` hoặc wrapper phù hợp. |
| Cần duyệt từng phần và biết còn phần tiếp theo | `Slice<T>` với `Pageable`, nếu module hỗ trợ. |
| Cần tổng số phần tử và số trang | `Page<T>`, xét thêm chi phí lấy tổng số. |
| Cần luồng xử lý reactive | API reactive của module, không suy từ Java Stream. |

`Stream<T>` là cơ chế pull đồng bộ của Java. Nó không tự biến thao tác repository thành bất đồng bộ hoặc non-blocking.

Tương tự, gọi `parallel()` không tạo một reactive repository. Với nguồn đang gắn tài nguyên persistence, cần tuân theo hợp đồng sử dụng thread của tài nguyên đó; không tự chuyển việc đọc cursor sang nhiều thread để kỳ vọng tăng tốc.

Đối với một công việc dài, cũng cần cân nhắc thời gian giữ transaction và connection. Đọc theo từng phần có thể là lựa chọn phù hợp hơn việc giữ một tài nguyên mở suốt quá trình, tùy yêu cầu nhất quán và khả năng store.

## 10. Những lỗi thường gặp và cách nhận diện

| Biểu hiện | Điều cần kiểm tra |
| --- | --- |
| Stream không đọc được sau khi service trả về | Phạm vi transaction và vòng đời tài nguyên có bao trùm lúc tiêu thụ không. |
| Lỗi Stream đã được dùng hoặc đóng | Có terminal operation trước đó hoặc đã ra khỏi block tài nguyên không. |
| Tài nguyên không được trả lại sau khi xử lý dở | Có đóng Stream trên mọi đường thoát, kể cả exception và dừng sớm không. |
| Dùng Stream nhưng bộ nhớ vẫn tăng | Có collect toàn bộ, stateful operation, bộ đệm hoặc entity được giữ lại không. |
| Streamable vẫn tải nhiều dữ liệu | Có đang coi khả năng tạo pipeline là cam kết streaming từ store không. |
| Sau and có phần tử trùng hoặc thứ tự bất ngờ | Có đang nối nguồn rồi kỳ vọng loại trùng và sort chung không. |
| filter phía Java nhưng query lấy quá nhiều | Điều kiện có cần được đưa vào query repository không. |

Nếu module không hỗ trợ query method trả `Stream`, cần chọn kiểu kết quả hoặc cách đọc mà module có hỗ trợ. Không sửa cú pháp SQL chỉ từ giả định rằng mọi query method streaming phải hoạt động như nhau.

## 11. Thực hành với một tập kết quả nhỏ

Giả sử dữ liệu có:

| id | status | priority | queueCode |
| --- | --- | --- | --- |
| 101 | OPEN | LOW | SUPPORT |
| 102 | CLOSED | HIGH | BILLING |
| 103 | OPEN | HIGH | SUPPORT |

### Bài 1: Duyệt một query Stream

Gọi `streamByStatusOrderByIdAsc(OPEN)` và xử lý trong `try-with-resources`.

Kết quả cần quan sát theo thứ tự là 101 rồi 103. Sau terminal operation, không dùng lại cùng Stream để đếm lần thứ hai.

Với JPA, đặt việc gọi query và tiêu thụ trong cùng transaction có hiệu lực như ví dụ service.

### Bài 2: Nối hai kết quả Streamable

Lấy:

```text
OPEN, thứ tự ID tăng dần -> 101, 103
HIGH, thứ tự ID tăng dần -> 102, 103
```

Nối bằng `and` cho:

```text
101, 103, 102, 103
```

Đây là bốn vị trí phần tử, dù chỉ có ba ID khác nhau. Nếu yêu cầu là một tập ticket không trùng, cần xác định cách biểu đạt tập đó và ngữ nghĩa định danh phù hợp.

### Bài 3: Tách rõ nơi thực hiện công việc

Với:

```java
repository.findByStatusOrderByIdAsc(TicketStatus.OPEN)
    .filter(ticket -> "SUPPORT".equals(ticket.getQueueCode()))
    .map(Ticket::getId)
    .toList();
```

hãy xác định:

1. Điều kiện nào được tên query method yêu cầu store áp dụng?
2. Điều kiện nào chạy ở phía Java?
3. Việc map sang ID có tự làm query chỉ chọn cột ID không?
4. Kết quả cuối có đang được thu thập thành List không?

Trong ví dụ, query method yêu cầu trạng thái OPEN và thứ tự ID. Phần filter hàng đợi cùng map ID là xử lý trên kết quả ở Java; List cuối giữ toàn bộ ID được thu thập.

Khi áp dụng cho dữ liệu lớn, hãy kiểm chứng đúng cơ chế lấy dữ liệu của module, phạm vi tài nguyên và lượng dữ liệu mỗi bước giữ lại, thay vì quyết định chỉ dựa trên tên `Stream` hoặc `Streamable`.
