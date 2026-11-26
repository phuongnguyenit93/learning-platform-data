# Window và ScrollPosition để duyệt dữ liệu theo từng phần

Trong chương **Scrolling** của Spring Data Commons (`SPRING_DATA_COMMONS`), `Window<T>` và `ScrollPosition` cung cấp một hợp đồng để đọc lần lượt các phần của tập kết quả.

Ứng dụng nhận một Window, xử lý nội dung, lấy vị trí tiếp tục rồi yêu cầu Window kế tiếp. Cách làm này phù hợp với công việc duyệt tuần tự, khi không nhất thiết cần tổng số bản ghi hoặc nhảy trực tiếp tới một số trang bất kỳ.

Commons định nghĩa các abstraction chung. Khả năng thực hiện scroll query, loại query và chiến lược offset/keyset còn phụ thuộc module store và phiên bản. Các ví dụ dưới đây giả định module đang dùng hỗ trợ query method tương ứng.

## 1. Ba thành phần của một lượt scrolling

Một lượt duyệt cần xác định:

| Thành phần | Vai trò |
| --- | --- |
| Điều kiện và thứ tự ổn định | Xác định tập dữ liệu và cách sắp xếp các phần tử. |
| Giới hạn mỗi lần lấy | Kiểm soát kích thước một phần kết quả. |
| Vị trí bắt đầu hoặc tiếp tục | Xác định nơi lấy Window tiếp theo. |

Hai abstraction chính:

- **Window** chứa phần dữ liệu vừa lấy và thông tin để biết còn phần tiếp theo.
- **ScrollPosition** biểu đạt vị trí trong tập kết quả để bắt đầu hoặc tiếp tục.

Có thể hình dung:

```text
Điểm bắt đầu
  -> query -> Window thứ nhất
  -> xử lý -> vị trí phần tử cuối
  -> query -> Window thứ hai
  -> ...
  -> Window cuối -> dừng
```

Mỗi lần lấy Window vẫn phải giữ đúng bộ lọc và thứ tự của lượt duyệt. Một vị trí chỉ có ý nghĩa trong ngữ cảnh truy vấn tương ứng.

## 2. Window cung cấp dữ liệu và khả năng tiếp tục

`Window<T>` nằm trong package `org.springframework.data.domain` và có từ Commons 3.1.

Các API thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `getContent()` | Nội dung Window dưới dạng List. |
| `size()` | Số phần tử trong Window hiện tại. |
| `isEmpty()` | Window có rỗng không. |
| `hasNext()` | Còn Window tiếp theo hay không. |
| `isLast()` | Đây có phải Window cuối không. |
| `positionAt(index)` | Lấy vị trí tương ứng với phần tử ở index trong Window. |
| `hasPosition(index)` | Kiểm tra cơ chế bên dưới có cung cấp vị trí tại index đó không. |
| `map(converter)` | Tạo Window có nội dung được chuyển đổi. |

Window mở rộng `Streamable`, nên có thể duyệt bằng vòng for hoặc những thao tác phù hợp trên nội dung. Nó không có hợp đồng tổng số phần tử hay tổng số trang như Page. Xem [API Window](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Window.html).

Điểm quan trọng là `size()` chỉ mô tả phần hiện tại. Một Window đủ kích thước tối đa vẫn có thể là Window cuối; không thay `hasNext()` bằng phép đoán từ kích thước.

## 3. ScrollPosition có điểm bắt đầu riêng

`ScrollPosition` cũng thuộc `org.springframework.data.domain` và có từ Commons 3.1.

Hai điểm bắt đầu thường gặp:

```java
import org.springframework.data.domain.ScrollPosition;

ScrollPosition offsetStart = ScrollPosition.offset();
ScrollPosition keysetStart = ScrollPosition.keyset();
```

Có thể kiểm tra:

```java
System.out.println(offsetStart.isInitial()); // true
System.out.println(keysetStart.isInitial()); // true
```

Các factory tạo vị trí ban đầu và vị trí tiếp tục được mô tả trong [API ScrollPosition](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/ScrollPosition.html).

### Vị trí tiếp tục có ngữ nghĩa exclusive

Với chiều duyệt tiến trong các ví dụ của bài, kết quả tiếp tục bắt đầu **sau** phần tử được vị trí chỉ tới.

Giả sử Window đầu gồm:

```text
Ticket 101, Ticket 102, Ticket 103
```

Nếu lấy vị trí của Ticket 103 rồi truyền lại cho query, Window sau bắt đầu sau Ticket 103. Ứng dụng không cần tự cộng một phần tử nữa vào vị trí vừa nhận.

### offset() khác offset(0)

```java
ScrollPosition.offset();
```

biểu đạt điểm bắt đầu trước khi chọn một phần tử cụ thể.

Còn:

```java
ScrollPosition.offset(0);
```

biểu đạt vị trí của phần tử đầu tiên, tại offset 0. Do ngữ nghĩa exclusive, query tiếp tục sau vị trí đó sẽ bỏ qua phần tử đầu tiên.

Vì vậy, để bắt đầu từ đầu, dùng factory không đối số thay vì tự thay bằng con số 0.

Với `OffsetScrollPosition` ban đầu, `getOffset()` cũng chưa có một offset phần tử cụ thể để đọc và ném lỗi theo hợp đồng API. Xem [API OffsetScrollPosition](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/OffsetScrollPosition.html).

## 4. Repository minh họa với thứ tự rõ ràng

Giả sử `Ticket` đã được mapping theo module, có:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất. |
| `tenantId` | `String` | Tenant sở hữu ticket. |
| `status` | `TicketStatus` | Ví dụ OPEN hoặc CLOSED. |
| `createdAt` | `Instant` | Thời điểm tạo. |

Trong ví dụ, ID và thời điểm tạo không null.

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.repository.CrudRepository;

public interface TicketRepository extends CrudRepository<Ticket, Long> {

    Window<Ticket> findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
        String tenantId,
        TicketStatus status,
        ScrollPosition position
    );
}
```

Chữ ký diễn đạt:

- Lọc theo tenant và trạng thái.
- Sắp xếp thời điểm tăng dần, sau đó ID tăng dần.
- Lấy tối đa ba phần tử cho mỗi Window.
- Nhận vị trí để xác định nơi bắt đầu lần lấy này.

Trong scroll query này, `First3` giới hạn kích thước mỗi lần gọi. Duyệt nhiều Window có thể xử lý nhiều hơn ba ticket trong cả công việc.

ID là tiêu chí phân định khi nhiều ticket có cùng thời điểm. Việc có thứ tự đầy đủ giúp giữ rõ ranh giới các phần dữ liệu trong một tập kết quả cố định.

Tên method và domain mapping chỉ là một phần của thiết lập. Cần dùng module, phiên bản và loại query có hỗ trợ scrolling; Commons không tự cung cấp một engine lưu trữ cho interface này.

## 5. Lấy một Window rồi tiếp tục từ phần tử cuối

Lần gọi đầu:

```java
ScrollPosition position = ScrollPosition.offset();

Window<Ticket> window =
    repository.findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
        "ACME",
        TicketStatus.OPEN,
        position
    );
```

Nếu có dữ liệu và còn phần tiếp theo:

```java
if (!window.isEmpty() && window.hasNext()) {
    int lastIndex = window.size() - 1;

    ScrollPosition nextPosition = window.positionAt(lastIndex);

    Window<Ticket> next =
        repository.findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
            "ACME",
            TicketStatus.OPEN,
            nextPosition
        );
}
```

`lastIndex` là index trong Window hiện tại, không phải offset toàn cục tự tính.

Ví dụ Window có ba phần tử thì index cuối là 2. Không gọi `positionAt(window.size())`, vì đó là vị trí vượt ngoài danh sách.

Cũng không gọi `positionAt(window.size() - 1)` khi Window rỗng: giá trị tính được là -1.

Cơ chế dùng vị trí phần tử cuối để yêu cầu phần tiếp theo được giới thiệu trong [Spring Data Commons — Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html).

## 6. Một vòng duyệt hoàn chỉnh

Ví dụ service dưới đây xử lý Window lần lượt và không tích lũy toàn bộ kết quả vào một List:

```java
import java.util.Objects;
import java.util.function.Consumer;

import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public final class TicketTraversalService {

    private final TicketRepository repository;

    public TicketTraversalService(TicketRepository repository) {
        this.repository = repository;
    }

    public long visitOpenTickets(
        String tenantId,
        Consumer<Ticket> consumer
    ) {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(consumer, "consumer");

        ScrollPosition position = ScrollPosition.offset();
        long processed = 0;

        while (true) {
            Window<Ticket> window =
                repository.findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                    tenantId,
                    TicketStatus.OPEN,
                    position
                );

            if (window.isEmpty()) {
                break;
            }

            for (Ticket ticket : window) {
                consumer.accept(ticket);
                processed++;
            }

            if (!window.hasNext()) {
                break;
            }

            int lastIndex = window.size() - 1;

            if (!window.hasPosition(lastIndex)) {
                throw new IllegalStateException(
                    "Cannot resume from the last window element"
                );
            }

            position = window.positionAt(lastIndex);
        }

        return processed;
    }
}
```

Các điểm cần giữ:

1. Vị trí ban đầu được tạo bằng factory initial.
2. Điều kiện nghiệp vụ không thay đổi giữa các lần gọi.
3. Window rỗng được xử lý trước khi lấy vị trí.
4. Nội dung hiện tại được xử lý trước khi chuyển sang phần tiếp theo.
5. Dùng `hasNext()` để tránh một lần query tiếp không cần thiết khi đã biết kết thúc.
6. Vị trí mới được lấy từ Window, giữ đúng loại cơ chế scroll mà query cung cấp.

Ví dụ dùng kiểu ScrollPosition chung để truyền tiếp vị trí của query hỗ trợ. Khi một module hoặc hợp đồng repository chỉ nhận kiểu vị trí cụ thể, cần khai báo và sử dụng loại tương ứng.

Phần validation nghiệp vụ, transaction và xử lý lỗi của ứng dụng cần được thiết kế thêm theo module và use case; vòng duyệt không tự cung cấp những chính sách đó.

## 7. Minh họa bằng một tập dữ liệu cố định

Giả sử các thời điểm cùng ngày, cùng múi giờ:

| id | tenantId | status | createdAt |
| --- | --- | --- | --- |
| 101 | ACME | OPEN | 10:00 |
| 102 | ACME | OPEN | 10:01 |
| 103 | ACME | OPEN | 10:02 |
| 104 | ACME | OPEN | 10:03 |
| 105 | ACME | OPEN | 10:04 |
| 106 | ACME | OPEN | 10:05 |
| 107 | OTHER | OPEN | 10:06 |
| 108 | ACME | CLOSED | 10:07 |

Với tenant ACME, trạng thái OPEN và giới hạn ba phần tử:

| Lần gọi | Vị trí yêu cầu | Nội dung | Còn phần tiếp theo? |
| --- | --- | --- | --- |
| 1 | Initial offset. | 101, 102, 103. | Có. |
| 2 | Vị trí của 103 từ Window đầu. | 104, 105, 106. | Không. |

Window thứ hai có đủ ba phần tử nhưng đã là cuối. Kiểm tra `size() == 3` sẽ không đủ để kết luận có phần tiếp theo.

Ticket 107 và 108 không tham gia vì không thỏa bộ lọc. Việc chuyển vị trí không bỏ bộ lọc tenant hoặc trạng thái.

Với offset scrolling, vị trí của Ticket 103 trong tập khớp ở ví dụ là offset 2. Đây là vị trí phần tử đã nhận; lần tiếp bắt đầu sau nó, tại phần tử có offset 3.

Nếu dùng `ScrollPosition.offset(0)` ngay từ lần đầu, Ticket 101 bị bỏ qua và phần đầu sẽ là 102, 103, 104 trong bộ dữ liệu cố định này.

## 8. Offset và keyset khác nhau ở cách xác định điểm tiếp tục

| Khía cạnh | Offset | Keyset |
| --- | --- | --- |
| Thông tin định vị | Vị trí theo số phần tử trong tập kết quả. | Các giá trị khóa dùng để xác định ranh giới. |
| Factory bắt đầu | `ScrollPosition.offset()`. | `ScrollPosition.keyset()`. |
| Điểm cần chú ý | Offset sâu có thể khiến store đi qua nhiều dữ liệu. | Cần khóa sort phù hợp để tái tạo điều kiện tiếp tục. |
| Điều kiện thực thi | Module phải hỗ trợ kiểu scroll tương ứng. | Module phải hỗ trợ kiểu scroll và trích được keyset. |

Với thứ tự `createdAt ASC, id ASC`, keyset có thể dùng cặp giá trị thời điểm và ID tại ranh giới để yêu cầu các phần tử phía sau.

Nếu module và query hỗ trợ keyset, cùng mô hình vòng duyệt có thể khởi đầu bằng:

```java
ScrollPosition position = ScrollPosition.keyset();
```

Sau đó vẫn lấy vị trí tiếp tục từ `window.positionAt(...)`. Không chuyển một vị trí keyset nhận được thành offset tự tính rồi dùng tiếp trong cùng lượt.

Những điều kiện quan trọng của keyset theo hướng dẫn Commons:

- Thuộc tính dùng làm khóa sort cần không nullable.
- Kết quả query phải có các thuộc tính cần thiết để trích keyset.
- Projection cần chứa các trường sort liên quan.
- Index phù hợp với điều kiện và thứ tự giúp store có cơ hội thực thi hiệu quả.

Không suy rằng chỉ đổi factory là mọi query sẽ tự tối ưu. Cần kiểm chứng khả năng của module và kế hoạch thực thi phù hợp với store.

## 9. WindowIterator giúp giảm mã điều khiển vòng duyệt

Khi ứng dụng chỉ muốn xử lý từng phần tử, `WindowIterator` giữ vị trí hiện tại và yêu cầu Window tiếp theo giúp caller.

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.support.WindowIterator;

WindowIterator<Ticket> iterator = WindowIterator.of(
    position ->
        repository.findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
            "ACME",
            TicketStatus.OPEN,
            position
        )
).startingAt(ScrollPosition.offset());

while (iterator.hasNext()) {
    Ticket ticket = iterator.next();
    process(ticket);
}
```

`process(...)` đại diện cho xử lý của ứng dụng. Callback là nơi thực hiện query cho từng vị trí.

WindowIterator triển khai Iterator và theo dõi ScrollPosition qua nhiều Window. Nó có từ Commons 3.1. Xem [API WindowIterator](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/support/WindowIterator.html).

Tiện ích này giảm việc lặp lại mã kiểm tra ranh giới. Nó không tự tạo snapshot dữ liệu, retry nghiệp vụ hoặc một transaction bao trùm cả công việc.

Việc khởi tạo iterator cũng không có nghĩa toàn bộ dữ liệu đã được tải xong. Khi iterator cần phần tiếp theo, callback có thể tiếp tục truy cập repository và phát sinh lỗi tại thời điểm đó.

## 10. Window khác Page, Slice và Stream ở hợp đồng nào?

| Kiểu | Thông tin hoặc cách dùng nổi bật |
| --- | --- |
| `Page<T>` | Nội dung cùng metadata tổng số theo hợp đồng phân trang. |
| `Slice<T>` | Một phần kết quả và tín hiệu còn phần tiếp theo, thường gắn với Pageable. |
| `Window<T>` | Một phần kết quả có thể cung cấp vị trí phần tử để tiếp tục scrolling. |
| `Stream<T>` | Pipeline tiêu thụ nguồn dữ liệu, có thể gắn với tài nguyên phải đóng khi module hỗ trợ. |

Window là một phần dữ liệu đã được trả về theo hợp đồng của query. Không mặc định nó là một database cursor đang mở xuyên suốt mọi lần lấy.

Tương tự, `window.stream()` tạo cách xử lý nội dung Window bằng Java Stream; nó không tự tải các Window còn lại.

Có thể map nội dung đã nhận:

```java
Window<Long> idWindow = window.map(Ticket::getId);
```

Đây là biến đổi nội dung ở phía ứng dụng. Nó khác với việc yêu cầu store truy vấn một projection chỉ chứa ID. Nếu dùng projection cho keyset, vẫn phải đáp ứng yêu cầu trích các khóa cần thiết.

Khi chọn cursor tiếp tục, hãy dựa trên thứ tự và index của Window gốc tương ứng. Không tự lọc hoặc sắp xếp một bản sao rồi dùng index mới để suy ngược vị trí của Window cũ.

## 11. Vị trí tiếp tục không phải snapshot hoặc bảo đảm xử lý đúng một lần

Thứ tự ổn định và ScrollPosition không đóng băng dữ liệu giữa các query.

Ví dụ trong lúc duyệt có thể xảy ra:

- Ticket được thêm hoặc xóa.
- Trạng thái thay đổi khiến ticket vào hoặc ra khỏi bộ lọc.
- Giá trị sort được cập nhật và di chuyển qua ranh giới đã đọc.

Offset và keyset chịu tác động khác nhau, nhưng không nên mặc định cả hai đều cho một ảnh chụp nhất quán của tập dữ liệu tại thời điểm bắt đầu.

Nếu use case cần duyệt một tập được chốt, cần thiết kế thêm điều kiện mốc, snapshot hoặc chính sách transaction phù hợp với store.

### Giữ nguyên ngữ cảnh của một vị trí

Không dùng vị trí đã lấy cho tenant ACME với bộ lọc của tenant khác, hoặc đổi thứ tự sort giữa lượt rồi kỳ vọng nó giữ nguyên ý nghĩa.

Nếu lưu checkpoint, cần biết vị trí đó thuộc:

```text
Bộ lọc nào.
Thứ tự nào.
Chiến lược scroll nào.
Phiên bản hợp đồng hoặc biểu diễn vị trí nào.
```

ScrollPosition là abstraction Java; không mặc định `toString()` của nó là một định dạng token công khai, ổn định để lưu hoặc gửi qua API.

### Lỗi sau khi xử lý một phần Window

Trong ví dụ service, nếu consumer ném lỗi sau một số ticket, cả Window chưa được xử lý hoàn tất. Vị trí tiếp tục không nên được cập nhật như thể mọi phần tử trong Window đã thành công.

Khi chạy lại từ checkpoint trước đó, những phần tử đã xử lý có thể được gặp lại. Tùy use case, cần chính sách xử lý lặp, transaction hoặc checkpoint sau từng đơn vị công việc.

Window và ScrollPosition không tự cung cấp ngữ nghĩa exactly-once cho tác vụ ứng dụng.

## 12. Giữ chi phí theo từng phần trong cả hệ thống

Giới hạn mỗi Window giúp kiểm soát số phần tử nhận trong một lần gọi, nhưng không bảo đảm tổng bộ nhớ hay chi phí store luôn nhỏ.

Ví dụ làm mất lợi ích ở phía ứng dụng:

```java
List<Ticket> all = new ArrayList<>();

// Nếu cứ thêm nội dung mọi Window vào all,
// ứng dụng cuối cùng vẫn giữ toàn bộ tập đã duyệt.
```

Ở phía store, offset sâu có thể đòi hỏi đi qua nhiều kết quả. Với keyset, index và điều kiện ranh giới cần phù hợp để có lợi ích thực tế.

Trong JPA, cũng cần xét lượng entity được persistence context giữ nếu chọn một transaction dài. Không suy từ kích thước Window rằng mọi tầng đều tự giải phóng dữ liệu đã xử lý.

Kích thước Window là một lựa chọn cân bằng giữa số lần gọi, lượng dữ liệu mỗi lần và chi phí xử lý. Giá trị ba trong bài giúp nhìn rõ ranh giới; kích thước thực tế cần được chọn theo workload.

## 13. Những lỗi dễ gặp khi triển khai vòng duyệt

| Lỗi hoặc giả định | Cách xử lý |
| --- | --- |
| Dùng offset(0) để bắt đầu từ phần tử đầu. | Dùng offset() initial. |
| Gọi positionAt(size()). | Dùng index hợp lệ; phần tử cuối là size() - 1. |
| Lấy vị trí khi Window rỗng. | Kiểm tra empty trước. |
| Mỗi lần đều truyền lại initial position. | Giữ và cập nhật vị trí lấy từ Window đã xử lý. |
| Tự cộng thêm một bước sau positionAt. | Giữ đúng ngữ nghĩa exclusive của vị trí đã nhận. |
| Đoán hasNext từ kích thước Window. | Dùng metadata hasNext/isLast. |
| Đổi bộ lọc hoặc sort giữa lượt. | Giữ ngữ cảnh nhất quán hoặc bắt đầu một lượt mới. |
| Chỉ bắt lỗi quanh lúc tạo WindowIterator. | Lỗi còn có thể phát sinh khi iterator gọi tiếp repository. |
| Kết quả keyset thiếu trường sort. | Kiểm tra projection và khả năng trích khóa của module. |

## 14. Thực hành theo dấu một lượt duyệt

Với bộ dữ liệu của bài:

1. Bắt đầu bằng `ScrollPosition.offset()`.
2. Nhận Window chứa 101, 102, 103.
3. Xác định index cuối là 2.
4. Lấy vị trí bằng `positionAt(2)`.
5. Gọi lại cùng query, cùng tenant và trạng thái với vị trí vừa nhận.
6. Nhận 104, 105, 106.
7. Dừng khi Window báo không còn phần tiếp theo.

Sau đó thử các tình huống để kiểm chứng hợp đồng:

- Không có ticket nào khớp: không lấy vị trí từ Window rỗng.
- Có đúng ba ticket: Window đầy nhưng có thể đã là cuối.
- Nhiều ticket trùng createdAt: tiêu chí ID phải giữ thứ tự rõ ràng.
- Consumer lỗi giữa Window: checkpoint không được đánh dấu vượt phần chưa xử lý.
- Dùng keyset với projection: các khóa cần thiết phải có trong kết quả.
- Đổi store hoặc phiên bản module: xác nhận lại hỗ trợ query và hành vi vị trí.

Mỗi lần chuyển Window cần trả lời được ba câu: phần nào đã xử lý xong, vị trí nào xác định ranh giới tiếp tục và ngữ cảnh truy vấn nào phải được giữ nguyên.
