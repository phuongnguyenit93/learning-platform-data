# WindowIterator và vòng lặp qua nhiều cửa sổ

Trong chương **Scrolling** của Spring Data Commons (`SPRING_DATA_COMMONS`), một lượt duyệt thường phải lặp lại ba việc: lấy một Window, tiêu thụ nội dung rồi chuyển vị trí để lấy Window tiếp theo.

`WindowIterator<T>` đóng gói phần điều khiển này thành một Iterator của từng phần tử T. Ứng dụng cung cấp hàm lấy Window; tiện ích giữ vị trí hiện tại và gọi hàm khi cần thêm dữ liệu.

Bài này tập trung vào vòng đời của iterator, thời điểm phát sinh truy cập repository, cách dừng sớm và giới hạn của nó đối với xử lý lỗi hoặc checkpoint. Các ví dụ duyệt theo chiều tiến và giả định module store hỗ trợ scroll query tương ứng.

## 1. Iterator trả từng phần tử, callback trả từng Window

Hai hợp đồng nằm ở hai phía khác nhau:

```text
Callback:
    ScrollPosition -> Window<T>

WindowIterator:
    hasNext() / next() -> lần lượt nhận từng T
```

Ví dụ về mặt ý tưởng:

```text
Callback lần 1 -> [101, 102, 103]
Callback lần 2 -> [104, 105, 106]
Callback lần 3 -> [107]

Iterator đưa cho caller:
101 -> 102 -> 103 -> 104 -> 105 -> 106 -> 107
```

`WindowIterator<T>` không phải `Iterator<Window<T>>`. Caller xử lý từng ticket, không tự nhận từng Window từ `next()`.

Lớp thuộc package `org.springframework.data.support`, triển khai `Iterator<T>` và có từ Commons 3.1. Xem [API WindowIterator](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/support/WindowIterator.html).

Khi use case cần biết ranh giới từng batch, chẳng hạn ghi checkpoint sau một Window, vòng lặp Window tường minh vẫn có thể phù hợp hơn.

## 2. Tạo iterator bằng hàm lấy dữ liệu và vị trí ban đầu

Giả sử `Ticket` có các thuộc tính Java:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất. |
| `tenantId` | `String` | Tenant sở hữu ticket. |
| `status` | `TicketStatus` | Ví dụ OPEN hoặc CLOSED. |
| `createdAt` | `Instant` | Thời điểm tạo. |

Trong ví dụ, ID và createdAt không null, domain mapping và cấu hình store đã được chuẩn bị.

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

Tạo iterator:

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
).startingAt(ScrollPosition.keyset());
```

Có hai bước:

1. `of(...)` nhận hàm tải Window và trả builder.
2. `startingAt(...)` tạo iterator với vị trí bắt đầu.

Trong ví dụ, query cần hỗ trợ keyset. Nếu chọn offset cho một query có hỗ trợ, dùng `ScrollPosition.offset()` làm vị trí ban đầu.

Builder và phương thức startingAt được mô tả trong [API WindowIteratorBuilder](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/support/WindowIterator.WindowIteratorBuilder.html).

Không thay điểm bắt đầu offset bằng `ScrollPosition.offset(0)`: đó là vị trí của phần tử đầu tiên, và ngữ nghĩa tiếp tục exclusive sẽ bắt đầu sau phần tử ấy.

## 3. Callback phải dùng vị trí được iterator truyền vào

Phần quan trọng nhất của callback là chuyển đúng `position` tới repository:

```java
position -> repository.findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
    tenantId,
    TicketStatus.OPEN,
    position
)
```

Một callback sai:

```java
position -> repository.findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
    tenantId,
    TicketStatus.OPEN,
    ScrollPosition.keyset()
)
```

Ở dạng sai, mỗi lần tải đều quay về điểm bắt đầu. Nếu Window đầu báo còn dữ liệu, vòng duyệt có thể nhận lặp lại cùng phần dữ liệu.

Hàm tải cần giữ hợp đồng:

- Dùng đúng vị trí đầu vào.
- Giữ cùng điều kiện nghiệp vụ và thứ tự trong một lượt.
- Trả một Window hợp lệ; khi không có kết quả thì dùng Window rỗng theo hợp đồng của nguồn.
- Cung cấp metadata `hasNext` chính xác.
- Cung cấp vị trí cần thiết để tiếp tục khi còn phần sau.

Với một Window rỗng kết thúc lượt, `hasNext` phải phản ánh việc không còn phần tiếp theo. Không tự tạo Window rỗng nhưng vẫn báo còn phần sau khi không có phần tử để xác định vị trí tiếp tục.

Commons cung cấp cơ chế duyệt; callback và module vẫn chịu trách nhiệm về tính đúng của từng Window.

## 4. hasNext có thể thực hiện truy vấn

Một lời gọi `hasNext()` không nhất thiết chỉ kiểm tra một biến trong bộ nhớ. Khi chưa có Window hoặc đã tiêu thụ hết Window hiện tại, iterator có thể gọi callback để lấy dữ liệu.

Trong triển khai Commons 4.1.0 được tham chiếu:

| Thao tác | Hành vi điển hình |
| --- | --- |
| Tạo builder rồi gọi startingAt | Lưu hàm tải và vị trí; chưa tải Window. |
| hasNext lần đầu | Có thể gọi callback để tải Window đầu. |
| next khi Window còn phần tử | Trả phần tử tiếp theo của Window đang giữ. |
| hasNext sau khi Window đã hết và còn phần sau | Lấy vị trí tiếp tục rồi tải Window mới. |
| hasNext sau Window cuối đã hết | Trả false, không tự tải một Window rỗng bổ sung. |

`next()` cũng kiểm tra khả năng còn phần tử, nên nó có thể gây việc tải Window nếu caller chưa gọi hasNext ở thời điểm đó.

Khi Window đang giữ vẫn còn phần tử, nhiều lần gọi hasNext không làm callback được gọi lại cho mỗi phần tử. Cấu trúc điều khiển có thể xem ở [mã nguồn WindowIterator tại tag Commons 4.1.0](https://github.com/spring-projects/spring-data-commons/blob/4.1.0/src/main/java/org/springframework/data/support/WindowIterator.java).

Điều này có hai hệ quả thực tế:

- Lỗi truy cập store có thể xuất hiện ở hasNext hoặc next.
- Thời gian tiêu thụ iterator là một phần thời gian đọc dữ liệu; chỉ đo thời gian tạo iterator sẽ bỏ lỡ công việc chính.

## 5. Vòng lặp xử lý toàn bộ dữ liệu

Một service minh họa:

```java
import java.util.Objects;
import java.util.function.Consumer;

import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.support.WindowIterator;

public final class TicketVisitor {

    private final TicketRepository repository;

    public TicketVisitor(TicketRepository repository) {
        this.repository = repository;
    }

    public long visitOpenTickets(
        String tenantId,
        Consumer<Ticket> consumer
    ) {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(consumer, "consumer");

        WindowIterator<Ticket> iterator = WindowIterator.of(
            position ->
                repository.findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                    tenantId,
                    TicketStatus.OPEN,
                    position
                )
        ).startingAt(ScrollPosition.keyset());

        long processed = 0;

        while (iterator.hasNext()) {
            Ticket ticket = iterator.next();
            consumer.accept(ticket);
            processed++;
        }

        return processed;
    }
}
```

`processed` là số phần tử được consumer xử lý thành công trước khi method trả về bình thường. Nếu một thao tác ném lỗi, method không tự trả số đếm như thể công việc đã hoàn tất.

Số ba trong tên method là kích thước mỗi lần tải, không phải tổng số ticket tối đa mà service được phép xử lý. Với bảy ticket khớp, vòng lặp có thể xử lý cả bảy qua ba Window.

Nếu không cần biến đếm hoặc logic điều khiển riêng, có thể dùng:

```java
iterator.forEachRemaining(this::process);
```

`process(...)` là xử lý của ứng dụng. Đây vẫn là quá trình tiêu thụ có thể gọi repository nhiều lần.

WindowIterator là Iterator, không phải một collection có thể đọc lại tùy ý. Muốn bắt đầu một lượt mới, cần tạo iterator mới với vị trí phù hợp.

## 6. Dừng sớm và giới hạn số phần tử đã xử lý

Giới hạn Window khác với giới hạn tổng công việc.

Giả sử mỗi Window có tối đa ba ticket nhưng lần chạy chỉ được xử lý tối đa bốn ticket:

```java
long processed = 0;
long maxItems = 4;

while (processed < maxItems && iterator.hasNext()) {
    Ticket ticket = iterator.next();
    process(ticket);
    processed++;
}
```

Đặt điều kiện giới hạn trước hasNext giúp tránh tải thêm Window khi đã đạt mức công việc và đang ở đúng ranh giới Window.

Nếu viết:

```java
while (iterator.hasNext() && processed < maxItems) {
    // ...
}
```

hasNext được đánh giá trước. Sau khi đã xử lý đủ, nó vẫn có thể tải Window kế tiếp rồi mới biết điều kiện giới hạn là false.

### Dừng giữa Window không hoàn tác phần đã tải

Với giới hạn xử lý bốn phần tử và Window ba phần tử:

```text
Đã tải:   [101, 102, 103]
Đã xử lý: 101, 102, 103

Đã tải:   [104, 105, 106]
Đã xử lý: 104

Dừng vì đủ bốn phần tử.
```

105 và 106 có thể đã được tải vào Window nhưng chưa được consumer xử lý. Đây là khác biệt giữa lượng dữ liệu đã lấy và tiến độ nghiệp vụ.

Tương tự, maxItems bằng 0 nên không cần gọi callback nếu kiểm tra ngân sách trước hasNext và iterator chưa được tiêu thụ ở nơi khác.

## 7. Theo dấu các ranh giới trên dữ liệu cố định

Giả sử có bảy ticket khớp, được sắp xếp theo createdAt ASC rồi ID ASC:

| id | createdAt |
| --- | --- |
| 101 | 10:00 |
| 102 | 10:01 |
| 103 | 10:02 |
| 104 | 10:02 |
| 105 | 10:03 |
| 106 | 10:04 |
| 107 | 10:05 |

Các thời điểm cùng ngày, cùng múi giờ.

Callback cần cung cấp:

| Window | Nội dung | hasNext |
| --- | --- | --- |
| 1 | 101, 102, 103. | true. |
| 2 | 104, 105, 106. | true. |
| 3 | 107. | false. |

Ở chiều tiến, iterator lấy vị trí phần tử cuối của Window đã tiêu thụ để yêu cầu phần sau. Nhờ tiêu chí ID, Ticket 104 có cùng createdAt với 103 vẫn nằm sau ranh giới tương ứng.

Các kỳ vọng về số lần gọi callback, với dữ liệu cố định và metadata đúng:

| Phạm vi tiêu thụ từ một iterator mới | Phần tử được xử lý | Callback được gọi |
| --- | --- | --- |
| Không tiêu thụ, ngân sách 0. | 0. | 0 lần. |
| Dừng sau 3 phần tử, kiểm tra ngân sách trước hasNext. | 3. | 1 lần. |
| Dừng sau 4 phần tử. | 4. | 2 lần. |
| Tiêu thụ hết. | 7. | 3 lần. |

Đây là số lần callback, không phải bảo đảm tuyệt đối về số câu lệnh vật lý ở mọi module. Provider, mapping hoặc xử lý liên quan có thể tạo thêm công việc cần quan sát riêng.

## 8. Ví dụ trong bộ nhớ để quan sát vòng duyệt

Có thể tách việc học cơ chế iterator khỏi cấu hình database bằng một nguồn nhỏ dùng `Window.from(...)`.

Ví dụ Java đầy đủ:

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.data.domain.OffsetScrollPosition;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.support.WindowIterator;

public class WindowIteratorDemo {

    public static void main(String[] args) {
        List<Long> ids = Arrays.asList(
            101L, 102L, 103L, 104L, 105L, 106L, 107L
        );

        int windowSize = 3;
        AtomicInteger windowLoads = new AtomicInteger();

        WindowIterator<Long> iterator = WindowIterator.<Long>of(
            position -> {
                OffsetScrollPosition offset =
                    (OffsetScrollPosition) position;

                int start = offset.isInitial()
                    ? 0
                    : Math.toIntExact(offset.getOffset() + 1);

                int end = Math.min(
                    start + windowSize,
                    ids.size()
                );

                windowLoads.incrementAndGet();

                return Window.from(
                    ids.subList(start, end),
                    index -> ScrollPosition.offset(
                        (long) start + index
                    ),
                    end < ids.size()
                );
            }
        ).startingAt(ScrollPosition.offset());

        while (iterator.hasNext()) {
            System.out.println(iterator.next());
        }

        System.out.println(
            "windowLoads=" + windowLoads.get()
        );
    }
}
```

Kỳ vọng khi chạy ví dụ:

```text
101
102
103
104
105
106
107
windowLoads=3
```

Cách đọc nguồn mô phỏng:

- Initial position bắt đầu tại index 0.
- Một offset cụ thể là vị trí đã trả, nên lần tiếp bắt đầu tại offset cộng 1.
- Hàm position gắn index cục bộ của Window với offset trong danh sách nguồn.
- Tham số `hasNext` bằng `end < ids.size()` phản ánh còn phần tử sau Window hiện tại.

Overload `Window.from(items, positionFunction, hasNext)` và hợp đồng vị trí có trong [API Window](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Window.html).

Nguồn này chỉ minh họa điều khiển vòng lặp trên bảy ID. Nó không kiểm chứng query, mapping, index hay hiệu năng của một store thực tế.

## 9. Lỗi tải Window và lỗi xử lý phần tử là hai thời điểm khác nhau

### Lỗi khi lấy dữ liệu

Callback có thể ném lỗi trong quá trình hasNext hoặc next cần tải Window mới.

Vì vậy, nếu có ranh giới dịch lỗi ứng dụng, phạm vi đó phải bao trùm quá trình tiêu thụ. Chỉ bắt lỗi quanh dòng tạo iterator không bao phủ các truy vấn diễn ra sau đó.

Không chuyển lỗi tải thành một Window rỗng để âm thầm kết thúc nếu hợp đồng yêu cầu báo rằng lượt duyệt thất bại.

### Lỗi sau khi next đã trả phần tử

Xét:

```java
Ticket ticket = iterator.next();
process(ticket);
```

Nếu process ném lỗi, iterator đã đưa Ticket đó ra khỏi vị trí đọc hiện tại. Gọi next lần nữa không có nghĩa thử lại cùng Ticket.

Ứng dụng cần giữ phần tử đang xử lý nếu muốn retry nó, hoặc khởi động lại theo một checkpoint được thiết kế có chủ đích.

Không mặc định catch rồi continue sẽ bảo đảm mọi phần tử đã thành công.

### Iterator không tự cung cấp retry nghiệp vụ

WindowIterator không tự quyết định:

- Lỗi nào có thể thử lại.
- Thử lại phần tử hay cả Window.
- Ghi nhận tiến độ ở đâu.
- Xử lý tác động đã thực hiện trước khi lỗi ra sao.

Những quyết định đó thuộc use case. Nếu bắt đầu lại từ đầu, cần tính đến khả năng gặp lại các ticket đã xử lý.

## 10. Khi cần checkpoint theo Window, dùng ranh giới tường minh

WindowIterator làm phẳng các Window thành luồng phần tử. API công khai không cung cấp một getter tiến độ nghiệp vụ hoặc một callback mặc định “Window này đã được xử lý thành công”.

Nếu cần commit theo batch hoặc lưu vị trí sau từng Window, có thể giữ vòng lặp Window:

```text
Lấy Window bằng vị trí đã lưu
  -> xử lý nội dung Window
  -> xác nhận đơn vị công việc đã thành công
  -> lấy vị trí tương ứng để lưu checkpoint
  -> chuyển sang Window sau
```

Với chiều tiến, vị trí cuối Window có thể được lấy bằng:

```java
ScrollPosition completedPosition =
    window.positionAt(window.size() - 1);
```

Cần kiểm tra Window không rỗng và cơ chế có cung cấp vị trí tương ứng.

### Không đánh dấu hoàn tất ngay trong callback tải

Callback chỉ chứng minh rằng dữ liệu đã được lấy. Khi callback trả về, consumer có thể chưa xử lý phần tử nào của Window đó.

Nếu lưu vị trí cuối Window ngay lúc tải như một checkpoint thành công, rồi tiến trình lỗi trước khi xử lý xong, lần chạy sau có thể bỏ qua công việc còn thiếu.

Checkpoint và tác động nghiệp vụ cần có một chính sách phối hợp phù hợp. Chỉ giữ một ScrollPosition không tự tạo ngữ nghĩa exactly-once.

Vị trí cũng cần được gắn với bộ lọc và thứ tự của lượt duyệt. Không dùng `toString()` như một định dạng lưu trữ công khai mặc định mà chưa thiết kế biểu diễn tương ứng.

## 11. Những bất biến cần giữ khi callback truy cập repository

### Giữ bộ lọc và thứ tự

Trong một iterator, không tự đổi tenant, trạng thái hoặc thứ tự theo số lần callback được gọi.

Với keyset, query phải trả được các khóa cần trích và dùng thuộc tính sort phù hợp, không nullable theo yêu cầu của cơ chế. Với offset, vị trí sâu có thể làm tăng công việc ở store.

Các điều kiện về sort, giới hạn và vị trí được giải thích trong [Spring Data Commons — Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html).

### Xét cả việc consumer thay đổi tập khớp

Nếu đang duyệt ticket OPEN bằng offset rồi consumer đổi chúng sang CLOSED, tập dữ liệu khớp sẽ thu nhỏ giữa các lần query. Offset cũ có thể khiến những ticket chưa xử lý bị bỏ qua.

Keyset có cách xác định ranh giới khác nhưng cũng không mặc nhiên tạo snapshot. Khi chính công việc làm thay đổi điều kiện hoặc khóa sort, cần thiết kế cách duyệt phù hợp với thay đổi đó.

### Giữ một luồng điều khiển rõ ràng

WindowIterator có trạng thái tiến độ. Không dùng chung một instance như một nguồn thread-safe cho nhiều worker.

Nếu cần xử lý song song, nên thiết kế các phần dữ liệu độc lập và cơ chế phối hợp riêng, thay vì chỉ gọi hasNext/next đồng thời trên cùng iterator.

### Quản lý tài nguyên theo module

WindowIterator không triển khai AutoCloseable như Java Stream. Việc giữ một instance không đồng nghĩa có một database cursor mở xuyên suốt cả lượt.

Transaction, persistence context, tài nguyên query và truy cập thuộc tính lazy vẫn cần được quản lý theo module. Một transaction dài giữ nhiều entity có thể làm bộ nhớ tăng dù mỗi Window nhỏ.

## 12. Chọn WindowIterator hay vòng lặp Window

| Nhu cầu | Cách tổ chức nên cân nhắc |
| --- | --- |
| Xử lý tuần tự từng phần tử, ít quan tâm ranh giới batch | WindowIterator. |
| Muốn dùng while hoặc forEachRemaining để tiêu thụ toàn bộ | WindowIterator. |
| Cần biết chính xác mỗi Window đã hoàn tất | Vòng lặp Window tường minh. |
| Cần transaction hoặc checkpoint theo batch | Vòng lặp Window và chính sách tiến độ phù hợp. |
| Cần dừng theo số lượng đã xử lý | Có thể dùng iterator với điều kiện dừng đặt trước hasNext. |
| Cần tổng số hoặc nhảy tới một số trang | Xem lại hợp đồng Page/Pageable thay vì suy từ iterator. |

Dù chọn cách nào, tránh tích lũy mọi phần tử vào một List lớn nếu mục tiêu là xử lý theo từng phần.

Kích thước Window chỉ giới hạn phần được lấy mỗi lần. Consumer, bộ đệm đầu ra và tầng persistence cũng phải giữ chính sách bộ nhớ phù hợp.

## 13. Thực hành với nguồn mô phỏng

Từ ví dụ bảy ID, hãy thay đổi riêng cách tiêu thụ:

1. Gọi hasNext hai lần trước next đầu tiên.
2. Tiêu thụ đúng ba phần tử rồi dừng trước khi gọi hasNext thêm.
3. Tiêu thụ bốn phần tử.
4. Tiêu thụ hết.
5. Đổi danh sách thành đúng sáu ID và tiêu thụ hết.
6. Dùng danh sách rỗng.

Kỳ vọng cần kiểm chứng:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Hai lần hasNext khi Window đầu còn dữ liệu | Không tải lại Window cho mỗi lời kiểm tra. |
| Dừng đúng ranh giới ba phần tử | Không tải Window sau nếu chưa yêu cầu thêm dữ liệu. |
| Dừng ở phần tử thứ tư | Window thứ hai đã được tải, nhưng chưa được xử lý hết. |
| Bảy ID, kích thước ba | Ba Window được tải khi duyệt hết. |
| Sáu ID, kích thước ba | Hai Window; không cần Window rỗng thứ ba nếu metadata đúng. |
| Nguồn rỗng | hasNext false; không gọi next để lấy một phần tử giả. |

Sau đó tách riêng các tình huống lỗi của callback và consumer. Hãy xác định phần tử nào đã được lấy, phần nào đã xử lý thành công và checkpoint nào được phép sử dụng.

Cách theo dõi đó giúp dùng WindowIterator như một bộ điều khiển duyệt dữ liệu rõ ràng, đồng thời giữ tiến độ nghiệp vụ và tính đúng của truy vấn trong hợp đồng của ứng dụng.
