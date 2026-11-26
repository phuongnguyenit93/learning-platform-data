# Lấy vị trí tiếp theo bằng Window.positionAt

## 1. Vị trí tiếp tục phải xuất phát từ phần tử nào?

Scrolling chia một tập kết quả có thứ tự thành các cửa sổ dữ liệu. Sau khi đọc một cửa sổ, ứng dụng cần biết bắt đầu lần đọc tiếp theo từ đâu. Với Spring Data Commons, `Window<T>` cung cấp nội dung, thông tin còn dữ liệu và phương thức `positionAt` để lấy vị trí gắn với một phần tử trong cửa sổ.

Mẫu thường dùng là:

```java
ScrollPosition next = window.positionAt(window.size() - 1);
```

Mẫu này chỉ đúng khi cửa sổ không rỗng và ứng dụng muốn tiếp tục sau phần tử cuối của cửa sổ. Nếu mới xử lý thành công một phần cửa sổ, checkpoint có thể phải lấy ở phần tử khác.

Bài học tập trung vào quan hệ giữa chỉ số trong Window, ScrollPosition và trạng thái xử lý. Đây là abstraction chung của Commons; mô-đun kho dữ liệu quyết định khả năng query scrolling, cách tạo vị trí offset hoặc keyset và những kiểu kết quả được hỗ trợ.

Các ví dụ repository giả định mô-đun và phiên bản dự án hỗ trợ derived query trả Window với loại ScrollPosition tương ứng. Mapping entity và tích hợp kho dữ liệu vẫn phải được cấu hình đúng.

## 2. Hợp đồng cốt lõi của positionAt

Với overload nhận chỉ số, hình dạng sử dụng là:

```java
ScrollPosition position = window.positionAt(index);
```

Các kiểu `Window` và `ScrollPosition` thuộc `org.springframework.data.domain`.

Phương thức nhận một chỉ số hợp lệ của phần tử **bên trong Window hiện tại** và trả ScrollPosition gắn với phần tử ấy. Chỉ số bắt đầu từ 0.

```text
0 <= index < window.size()
```

Bốn điều cần giữ rõ:

1. Đối số là chỉ số cục bộ của cửa sổ, không phải id entity.
2. Đối số không phải offset toàn cục của toàn bộ tập dữ liệu.
3. Kết quả là một ScrollPosition, không phải số thứ tự của trang tiếp theo.
4. Lấy vị trí không tự gọi repository để đọc cửa sổ mới.

Ứng dụng phải truyền vị trí vừa nhận vào một lời gọi query phù hợp để tiếp tục.

### 2.1. Tiếp tục theo quy tắc loại trừ phần tử mốc

Scrolling dùng vị trí như mốc đã đi qua. Với cùng query, sort và cơ chế scrolling phù hợp, lần đọc tiếp tục sau phần tử gắn với mốc, thay vì cố ý trả lại chính phần tử mốc.

Nếu cửa sổ hiện tại là `[A, B, C]`:

| Vị trí lấy từ | Ý nghĩa tiếp tục |
| --- | --- |
| `positionAt(0)` | Sau A; B và C vẫn có thể nằm trong lần đọc tiếp |
| `positionAt(1)` | Sau B; C vẫn chưa được vượt qua |
| `positionAt(2)` | Sau C; thích hợp nếu đã xử lý cả cửa sổ |

Đây là lý do không chọn ngẫu nhiên một vị trí chỉ vì muốn “sang cửa sổ tiếp theo”. Phải biết phần nào của cửa sổ đã được tiêu thụ theo hợp đồng xử lý.

### 2.2. Không tự cộng thêm một bước vào vị trí trả về

Vị trí đã biểu đạt mốc mà cơ chế scrolling biết cách tiếp tục sau nó. Nếu ứng dụng tự cộng offset hoặc tự sửa khóa để bỏ thêm một phần tử, có thể làm mất dữ liệu.

Hãy truyền ScrollPosition do Window cung cấp theo đúng loại mà query method nhận, thay vì tự biến nó thành số trang hoặc id kế tiếp.

## 3. Chỉ số cục bộ không phải vị trí toàn cục

Giả sử kết quả có thứ tự là A, B, C, D, E, F và mỗi cửa sổ trả ba phần tử.

| Cửa sổ | Chỉ số cục bộ | Phần tử | Vị trí offset của phần tử trong ví dụ |
| --- | --- | --- | --- |
| Thứ nhất | 0 | A | 0 |
| Thứ nhất | 1 | B | 1 |
| Thứ nhất | 2 | C | 2 |
| Thứ hai | 0 | D | 3 |
| Thứ hai | 1 | E | 4 |
| Thứ hai | 2 | F | 5 |

Ở cửa sổ thứ hai, `positionAt(2)` vẫn nhận số 2, nhưng vị trí offset được tạo phải gắn với F ở vị trí toàn cục 5 trong ví dụ.

Ứng dụng không cần tự tính `offset + index` rồi đưa tổng đó vào `positionAt`. Cơ chế tạo Window đã chịu trách nhiệm liên hệ phần tử với vị trí nguồn.

Cũng không được đưa `F.getId()` vào overload nhận index chỉ vì id tình cờ là một số nhỏ. Định danh và chỉ số thuộc hai miền ý nghĩa khác nhau.

### 3.1. Size thực tế khác giới hạn tối đa

Nếu query giới hạn 50 phần tử nhưng cửa sổ cuối chỉ có 7, phần tử cuối có chỉ số 6. Dùng hằng số 49 sẽ vượt phạm vi.

```java
int lastIndex = window.size() - 1;
ScrollPosition afterLast = window.positionAt(lastIndex);
```

Đoạn này cần kiểm tra `window.isEmpty()` trước. Với cửa sổ rỗng, size bằng 0 và lastIndex bằng -1; không có phần tử nào để lấy vị trí.

Nếu mô-đun đọc dư dữ liệu để xác định `hasNext`, phần tử đọc dư không nhất thiết nằm trong nội dung Window công khai. Không dùng giới hạn hoặc số hàng nội bộ để tạo một chỉ số ngoài Window.

## 4. Vị trí ban đầu và vị trí của phần tử đầu không giống nhau

Với scrolling theo offset, Spring Data Commons có cách biểu đạt điểm bắt đầu:

```java
OffsetScrollPosition start = ScrollPosition.offset();
```

Điểm bắt đầu này chưa biểu đạt việc đã đi qua phần tử nào. Nó khác:

```java
OffsetScrollPosition afterFirst = ScrollPosition.offset(0);
```

Trong quy tắc tiếp tục loại trừ phần tử mốc, offset 0 đã biểu đạt vị trí của phần tử đầu. Tiếp tục từ đó sẽ đi sau phần tử đầu, không phải bắt đầu lại từ nó.

Vì vậy, nếu muốn đọc từ đầu, không thay `ScrollPosition.offset()` bằng `ScrollPosition.offset(0)` chỉ vì quen với page number bắt đầu từ 0.

| Khái niệm | Ý nghĩa |
| --- | --- |
| Vị trí offset ban đầu | Chưa đi qua phần tử nào |
| Vị trí offset của phần tử 0 | Phần tử đầu đã là mốc tiếp tục |
| Page number 0 | Yêu cầu trang đầu trong mô hình Pageable |

Đây là các abstraction khác nhau. Không chuyển đổi máy móc giữa chúng chỉ bằng một số nguyên.

Với keyset, cũng cần dùng vị trí ban đầu của cơ chế keyset, chẳng hạn `ScrollPosition.keyset()`, thay vì tự dựng một bộ khóa giả không thuộc hợp đồng dữ liệu.

## 5. Ví dụ đọc các cửa sổ offset

Giả sử entity `EventRecord` có các thuộc tính:

| Thuộc tính | Kiểu minh họa | Vai trò |
| --- | --- | --- |
| `id` | Long | Định danh duy nhất |
| `tenantId` | Long | Phạm vi dữ liệu |
| `status` | String | Bộ lọc trạng thái |
| `occurredAt` | Instant | Thời điểm sự kiện dùng để sắp xếp |

Ví dụ giả định khóa sort có giá trị và thứ tự tăng dần theo `occurredAt`, rồi `id`. Mapping entity phụ thuộc mô-đun.

Repository cho cơ chế offset:

```java
import org.springframework.data.domain.OffsetScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.repository.Repository;

public interface EventRecordRepository
        extends Repository<EventRecord, Long> {

    Window<EventRecord>
    findFirst50ByTenantIdAndStatusOrderByOccurredAtAscIdAsc(
            Long tenantId,
            String status,
            OffsetScrollPosition position);
}
```

Từ khóa giới hạn trong ví dụ xác định số phần tử tối đa của mỗi cửa sổ theo khả năng query method mà mô-đun hỗ trợ. Nó không nói toàn bộ bộ lọc chỉ có tối đa 50 sự kiện.

Vòng lặp minh họa dùng Java 17 trở lên:

```java
import java.util.Objects;
import java.util.function.Consumer;

import org.springframework.data.domain.OffsetScrollPosition;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public final class EventWindowReader {
    private final EventRecordRepository repository;

    public EventWindowReader(EventRecordRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public void consumeAll(
            Long tenantId,
            String status,
            Consumer<? super EventRecord> handler) {

        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(handler, "handler");

        OffsetScrollPosition position = ScrollPosition.offset();

        while (true) {
            Window<EventRecord> window =
                    repository
                        .findFirst50ByTenantIdAndStatusOrderByOccurredAtAscIdAsc(
                                tenantId, status, position);

            if (window.isEmpty()) {
                if (window.hasNext()) {
                    throw new IllegalStateException(
                            "Không có phần tử để lấy vị trí tiếp tục");
                }
                return;
            }

            for (EventRecord event : window) {
                handler.accept(event);
            }

            if (!window.hasNext()) {
                return;
            }

            ScrollPosition afterLast =
                    window.positionAt(window.size() - 1);

            if (!(afterLast instanceof OffsetScrollPosition next)) {
                throw new IllegalStateException(
                        "Query offset nhận loại vị trí không phù hợp");
            }
            position = next;
        }
    }
}
```

Ngữ cảnh truy cập phải xác định tenant được phép đọc. Chỉ truyền một tenantId không thay thế kiểm tra quyền của ứng dụng.

### 5.1. Tại sao phải giữ lại position mới?

`positionAt` trả một giá trị; nó không tự thay biến position của service. Nếu tiếp tục gọi repository với position cũ, chương trình có thể đọc lại cùng cửa sổ.

Lệnh gán `position = next` là bước chuyển trạng thái của vòng lặp. Việc có một Window mới trong bộ nhớ không tự làm lần query sau tiến lên.

### 5.2. Tại sao kiểm tra loại vị trí?

`Window.positionAt(int)` trả abstraction `ScrollPosition`, còn query method ví dụ nhận `OffsetScrollPosition`. Mã không nên ép mọi vị trí thành offset mà không biết query đã dùng cơ chế nào.

Kiểm tra loại giữ rõ hợp đồng giữa loader và người gọi. Nếu triển khai dùng keyset, cần dùng query và trạng thái keyset tương ứng, không trộn hai loại vị trí.

Vòng lặp này coi cửa sổ rỗng nhưng báo còn dữ liệu là tình trạng không thể tiếp tục theo hợp đồng của nó: không có phần tử hợp lệ để gọi positionAt. Một giao thức tùy chỉnh cho phép các đoạn rỗng phải cung cấp cách tiến lên rõ ràng, không tự suy ra từ chỉ số -1.

## 6. Với keyset, vị trí chứa khóa chứ không phải số thứ tự

Một query method tương ứng có thể nhận `KeysetScrollPosition` trong mô-đun hỗ trợ:

```java
Window<EventRecord>
findFirst50ByTenantIdAndStatusOrderByOccurredAtAscIdAsc(
        Long tenantId,
        String status,
        KeysetScrollPosition position);
```

Đây là biến thể dùng `org.springframework.data.domain.KeysetScrollPosition`. Điểm bắt đầu là vị trí keyset ban đầu; các vị trí sau được lấy từ Window do đường keyset tạo ra.

Giả sử phần tử cuối đã xử lý có:

```text
occurredAt = 2026-01-10T10:00:00Z
id = 103
```

Với thứ tự tăng dần theo hai khóa, ý tưởng điều kiện tiếp tục là:

```text
occurredAt > lastOccurredAt
OR (occurredAt = lastOccurredAt AND id > lastId)
```

Điều kiện này còn phải kết hợp với tenant, trạng thái và mọi bộ lọc của query. Đây là diễn giải cho thứ tự cụ thể trong ví dụ, không phải công thức để ứng dụng tự dựng cursor cho mọi kho dữ liệu.

Nếu hướng sort hoặc số khóa thay đổi, điều kiện tiếp tục cũng thay đổi. Vì vậy, lấy vị trí từ `window.positionAt(...)` giúp ứng dụng dùng metadata mà implementation đã gắn với phần tử, thay vì tự giả định chỉ cần tăng id.

Offset và keyset cùng dùng chỉ số cục bộ khi gọi positionAt, nhưng nội dung ScrollPosition khác nhau. Một index bằng 2 không có nghĩa vị trí keyset sẽ là số 2.

Vị trí keyset cũng không tự cho biết tổng số phần tử hoặc “đây là trang thứ mấy” trong toàn bộ tập kết quả.

## 7. Có vị trí hợp lệ khác với còn cửa sổ tiếp theo

`positionAt` gắn với một phần tử hiện diện. `hasNext()` cho biết metadata về khả năng còn phần dữ liệu phía sau theo lần đọc hiện tại. Hai câu hỏi này độc lập.

| Trạng thái Window | Có thể lấy vị trí của phần tử? | Cách dùng thông thường |
| --- | --- | --- |
| Không rỗng, hasNext true | Có, với chỉ số hợp lệ | Xử lý rồi lấy mốc để đọc tiếp |
| Không rỗng, hasNext false | Vẫn có vị trí của các phần tử hiện diện | Có thể lưu checkpoint; thường không cần query tiếp ngay |
| Rỗng | Không có phần tử để gọi positionAt | Dừng hoặc xử lý theo giao thức nguồn |

Một Window cuối có ba phần tử vẫn cho phép lấy vị trí của phần tử thứ ba. Việc không còn dữ liệu ở thời điểm đọc không làm phần tử đó mất vị trí.

Nếu API trả token tiếp tục cho người dùng, có thể chọn không trả token khi `hasNext` false. Nếu một job cần checkpoint của phần tử cuối đã hoàn thành, nó có thể vẫn cần lưu vị trí ấy. Đây là hai chính sách sử dụng metadata khác nhau.

### 7.1. Window rỗng không tạo ra một checkpoint mới

Không có phần tử nghĩa là không có “phần tử cuối” để biến thành vị trí. Không dùng `positionAt(0)`, `positionAt(-1)` hoặc một id giả để thay thế.

Nếu job đã có checkpoint từ trước, một lần đọc rỗng có thể giữ nguyên checkpoint và ghi trạng thái hoàn thành riêng. Nếu chưa xử lý phần tử nào, trạng thái ban đầu vẫn khác với mốc của phần tử đầu.

Với nguồn có thay đổi, kết quả rỗng hoặc hasNext false phản ánh lần đọc ấy, không khẳng định sẽ không bao giờ có dữ liệu mới trong tương lai. Hành vi một lần quét và hành vi theo dõi dữ liệu mới cần được thiết kế riêng.

## 8. Vị trí chỉ có ý nghĩa trong hợp đồng query tương ứng

Một cursor không phải địa chỉ chung có thể đưa vào bất kỳ truy vấn nào. Nó cần được hiểu cùng:

- Phạm vi tenant hoặc người dùng được phép xem.
- Các bộ lọc như status, khoảng thời gian hoặc loại sự kiện.
- Thứ tự và hướng của các khóa sort.
- Cơ chế offset hoặc keyset.
- Cách mô-đun ánh xạ dữ liệu và trích khóa vị trí.

Ví dụ cửa sổ trước được đọc với `status = NEW`, nhưng lần sau dùng cùng cursor với `status = DONE`. Hai lần đang đi trên hai tập kết quả khác nhau. Vị trí không tự chứng minh rằng lần đọc thứ hai là phần tiếp theo của lần đầu.

Tương tự, đổi `occurredAt ASC, id ASC` thành `occurredAt DESC, id DESC` không chỉ thay cách trình bày. Nó thay định nghĩa đi trước và đi sau trong hành trình scrolling.

### 8.1. Giữ trạng thái tìm kiếm riêng với trạng thái vị trí

Ứng dụng có thể giữ một mô tả phiên tìm kiếm gồm bộ lọc và sort, còn cursor chỉ là phần tiến độ bên trong phiên đó. Nếu cho phép đổi bộ lọc, cần quy định rõ có bắt đầu lại hay dùng một cơ chế chuyển đổi được thiết kế riêng.

Không nên tái sử dụng cursor cũ chỉ vì kiểu Java của nó vẫn là ScrollPosition. Kiểu đúng là điều kiện cần, chưa đủ để có đúng ngữ nghĩa query.

### 8.2. Khóa sort phải đáp ứng yêu cầu của mô-đun

Với keyset, implementation cần các giá trị khóa để tạo điều kiện tiếp tục. Những đường triển khai yêu cầu khóa non-null phải được cung cấp dữ liệu thỏa điều kiện ấy.

Nếu query trả projection, cần kiểm tra projection có đủ các thuộc tính mà mô-đun cần để trích vị trí. Chỉ hiển thị tên sự kiện không có nghĩa query có thể thiếu toàn bộ khóa sort mà vẫn tạo được cursor đúng.

Không đợi đến lúc gọi positionAt rồi tự bù một giá trị khóa bằng null hoặc 0. Vấn đề phải được giải quyết ở hợp đồng dữ liệu và cơ chế mapping được hỗ trợ.

## 9. Ánh xạ nội dung không được làm lệch chỉ số với vị trí

### 9.1. Map một-một và giữ nguyên thứ tự

Window có phép `map` để tạo Window của kiểu khác. Khi chỉ ánh xạ một-một qua API đó, metadata vị trí được giữ cùng cửa sổ theo hợp đồng ánh xạ:

```java
Window<EventView> views = window.map(event ->
        new EventView(event.getId(), event.getOccurredAt()));
```

`EventView` là DTO của ứng dụng, ví dụ một record dùng Java 17 trở lên:

```java
import java.time.Instant;

public record EventView(Long id, Instant occurredAt) {
}
```

Vị trí vẫn gắn với cùng thứ tự phần tử nguồn. Bản thân việc map sang DTO không biến một Window offset thành Window keyset hoặc ngược lại.

Tuy nhiên, ánh xạ sau khi đã lấy dữ liệu khác với chọn projection ngay trong repository. Nếu projection được dùng ở query keyset, vẫn phải đáp ứng yêu cầu trích khóa của mô-đun.

### 9.2. Lọc hoặc sắp xếp lại một List là tình huống khác

Giả sử Window nguồn có các id `[101, 102, 103]`. Giao diện bỏ phần tử 102 và chỉ giữ `[101, 103]`.

Nếu lấy `filtered.size() - 1`, giá trị là 1. Nhưng gọi `window.positionAt(1)` trên Window nguồn trả vị trí của 102, không phải 103.

Đây là lỗi trộn hai hệ chỉ số. Tương tự, nếu sắp xếp lại List nội dung rồi dùng vị trí thứ tự mới trên Window cũ, cursor có thể không gắn với phần tử mà chương trình tưởng đang chọn.

Nếu bộ lọc xác định tập kết quả thực sự cần duyệt, nên đưa điều kiện vào query phù hợp. Nếu đó chỉ là quy tắc trình bày và ứng dụng vẫn coi toàn bộ cửa sổ nguồn đã được tiêu thụ, cursor phải dựa trên phần nguồn đã tiêu thụ, không dựa trên số phần tử đang hiển thị.

### 9.3. Đừng tự dựng Window mới với metadata không tương ứng

Một custom implementation phải gắn position với đúng phần tử và đúng index. Sao chép List nhưng dùng lại một hàm vị trí vốn được xây cho thứ tự khác có thể tạo cursor sai dù các đối tượng kết quả trông hợp lệ.

Để kiểm chứng, cần đối chiếu phần tử ở index i với vị trí nguồn mà lần đọc tiếp theo sẽ dùng, không chỉ xác minh List có đủ số phần tử.

## 10. Checkpoint phải phản ánh phần đã xử lý thành công

### 10.1. Đã tải không có nghĩa đã hoàn thành

Giả sử Window có `[A, B, C]`:

1. A được xử lý và ghi nhận thành công.
2. Xử lý B thất bại.
3. C chưa được xử lý.

Nếu đã lưu `positionAt(2)` ngay khi tải xong Window, lần chạy lại bắt đầu sau C và có thể bỏ qua cả B lẫn C.

Checkpoint an toàn theo tiến độ lúc này chỉ có thể đi qua A, nếu thành công của A đã được ghi nhận theo hợp đồng. Vị trí cần lấy là `positionAt(0)`.

Vì vậy, mẫu lấy phần tử cuối chỉ áp dụng sau khi toàn bộ phần tương ứng đã được xác nhận hoàn thành, hoặc sau khi một transaction của cả lô đã commit thành công.

### 10.2. Mô hình checkpoint từng phần tử

Mã minh họa ở tầng ứng dụng có thể có dạng:

```java
for (int index = 0; index < window.size(); index++) {
    EventRecord event = window.getContent().get(index);

    processAndCommit(event);

    ScrollPosition completed = window.positionAt(index);
    checkpointStore.save(completed);
}
```

`processAndCommit` và `checkpointStore` là các hợp đồng do ứng dụng thiết kế, không phải phương thức có sẵn của Commons. Ví dụ giả định một lỗi sẽ dừng luồng thay vì bị bỏ qua rồi tiếp tục nâng checkpoint.

Sau khi xử lý thành công nhưng trước khi lưu checkpoint vẫn có một khoảng mà tiến trình có thể dừng. Lần chạy lại có thể xử lý lặp phần tử đã tạo hiệu ứng.

Nếu lưu checkpoint trước hiệu ứng, lại có nguy cơ bỏ sót. Chỉ gọi positionAt không tạo ra bảo đảm exactly-once. Cần chính sách transaction, idempotency hoặc cơ chế phối hợp ghi phù hợp với các hệ thống thực tế.

### 10.3. Xử lý song song cần một tiền tố hoàn thành liên tục

Giả sử C hoàn thành trước B do các handler chạy song song. Không được lưu vị trí của C chỉ vì nó là phần tử hoàn thành có index lớn nhất.

Một checkpoint tiến lên qua C có nghĩa toàn bộ phần trước và đến C đã được chấp nhận hoàn thành. Nếu B còn lỗi hoặc chưa chạy, vị trí ấy sẽ vượt qua một khoảng chưa xử lý.

Cần theo dõi phần tiền tố liên tục đã hoàn thành trong thứ tự query, không chỉ chọn id lớn nhất hoặc tác vụ hoàn thành cuối cùng. Với sort nhiều khóa, id lớn nhất cũng chưa chắc là phần tử cuối trong thứ tự đang duyệt.

### 10.4. Không bỏ qua lỗi handler một cách ngầm định

Nếu hệ thống có chính sách chấp nhận bỏ qua một sự kiện lỗi, trạng thái đó phải được ghi nhận rõ theo hợp đồng xử lý. Không đơn giản bắt mọi exception, tiếp tục đến cuối Window rồi đánh dấu cả Window đã xử lý thành công.

Lựa chọn cursor là một phần của tiến độ đã xác nhận, không phải công cụ che lỗi xử lý.

## 11. Tập dữ liệu thay đổi có thể làm vị trí không đủ để duyệt đầy đủ

### 11.1. Offset chịu ảnh hưởng khi tập phù hợp bị co lại

Giả sử bộ lọc là status NEW và dữ liệu ban đầu có A, B, C, D, E, F. Cửa sổ đầu trả A, B, C với các vị trí offset tương ứng.

Nếu handler đổi A, B, C sang DONE và các thay đổi đã được thấy ở lần query sau, tập NEW còn D, E, F. Tiếp tục bằng offset sau ba phần tử có thể bỏ qua cả D, E, F vì ba vị trí đầu của tập hiện tại đã khác.

Trong tình huống này, việc gọi `positionAt(window.size() - 1)` có thể hoàn toàn đúng với Window đã đọc. Sai lầm nằm ở việc kỳ vọng một vị trí số lượng vẫn diễn đạt cùng tiến độ sau khi tập phù hợp đã bị thay đổi.

### 11.2. Keyset có lợi khi khóa ổn định nhưng không phải snapshot

Một đường keyset theo khóa không đổi có thể tiếp tục bằng điều kiện sau khóa của C mà không cần bỏ qua ba hàng theo số lượng. Điều này có thể phù hợp hơn với một số tác vụ vừa đọc vừa đổi trạng thái.

Tuy nhiên, keyset không tự đóng băng dữ liệu. Nếu khóa sort của một bản ghi thay đổi hoặc có bản ghi mới được thêm vào vùng khóa đã đi qua, một lần quét vẫn có thể không mang ý nghĩa “tất cả dữ liệu ở mọi thời điểm”.

Cần xác định yêu cầu của tác vụ: duyệt một snapshot, duyệt một tập định danh đã chốt, xử lý dữ liệu đủ điều kiện tại thời điểm đọc hay liên tục theo dõi dữ liệu mới. Mỗi yêu cầu có thiết kế nhất quán khác nhau.

### 11.3. Transaction của từng handler chưa bao trùm toàn bộ hành trình

Mỗi sự kiện có thể được xử lý trong một transaction riêng. Điều đó không tự làm toàn bộ các cửa sổ cùng quan sát một snapshot hoặc làm checkpoint nguyên tử với mọi hiệu ứng bên ngoài.

Khi cần bảo đảm mạnh hơn, phải thiết kế ranh giới transaction và cơ chế lưu tiến độ tương ứng. Không suy ra các bảo đảm ấy chỉ từ việc repository trả Window.

## 12. Lưu và trao đổi vị trí tiếp tục

### 12.1. Không dùng toString làm hợp đồng lưu trữ

Một ScrollPosition có thể có biểu diễn chuỗi hữu ích khi chẩn đoán. Không nên mặc định `toString()` là định dạng lưu bền hoặc token API có thể đọc lại ổn định qua các phiên bản.

Nếu cần lưu checkpoint hoặc trả cursor ra ngoài, ứng dụng phải có định dạng và adapter tương ứng với khả năng của phiên bản, mô-đun và chiến lược scrolling đã chọn.

### 12.2. Thông tin cần ràng buộc với cursor

Một hợp đồng lưu tiến độ có thể cần:

| Thành phần | Lý do |
| --- | --- |
| Phiên bản định dạng | Xử lý thay đổi cấu trúc token hoặc model |
| Loại vị trí | Phân biệt offset với keyset |
| Phạm vi dữ liệu | Không áp cursor sang tenant hoặc tập được phép xem khác |
| Bộ lọc hoặc định danh phiên tìm kiếm | Giữ cùng tập kết quả |
| Mô tả sort | Giữ cùng thứ tự và hướng |
| Giá trị vị trí | Offset hoặc các khóa cần cho bước tiếp tục |
| Trạng thái xử lý | Phân biệt đang đọc, đã hoàn thành hoặc cần thử lại |

Đây là dữ liệu thuộc thiết kế ứng dụng, không phải schema token chuẩn của Commons.

Các khóa thời gian và định danh cần giữ đúng kiểu và độ chính xác. Ví dụ làm mất độ chính xác của một mốc thời gian trong quá trình chuyển đổi có thể làm điều kiện keyset không còn tương ứng với phần tử mốc.

Cursor đầu vào vẫn phải được kiểm tra theo phạm vi truy cập hiện tại; việc có một vị trí đọc không tự cấp quyền sang tenant hoặc bộ lọc khác.

### 12.3. Không tự tái tạo thiếu khóa

Nếu vị trí keyset cần nhiều khóa, không chỉ lưu id rồi giả định đủ để đọc tiếp theo `occurredAt, id`. Cũng không thay giá trị khóa bị thiếu bằng mặc định để làm query chạy được.

Nên dùng cơ chế biểu đạt và dựng vị trí được phiên bản hỗ trợ, với một adapter có trách nhiệm rõ. Nếu token cũ không còn tương thích hợp đồng sort mới, phải có chính sách xử lý thay vì âm thầm diễn giải lại.

## 13. Các lỗi thường gặp khi dùng positionAt

| Hiện tượng | Nguyên nhân có thể có | Hướng kiểm tra |
| --- | --- | --- |
| Bỏ mất phần tử đầu | Dùng offset 0 thay vị trí ban đầu | Phân biệt initial với mốc của phần tử 0 |
| Lỗi chỉ số ở cửa sổ cuối | Dùng giới hạn 50 thay size thực tế | Kiểm tra rỗng, dùng size trừ 1 |
| Đọc lại cùng Window | Không gán hoặc không truyền position mới | Đối chiếu vị trí đầu vào từng lần gọi |
| Bỏ qua B và C sau khi B lỗi | Checkpoint phần tử cuối quá sớm | Gắn checkpoint với hoàn thành được xác nhận |
| Cursor chỉ đúng ở cửa sổ đầu | Trộn index cục bộ với offset toàn cục | Đối số của positionAt luôn theo Window hiện tại |
| Lỗi ép kiểu vị trí | Trộn keyset và offset | Giữ đúng kiểu của query method |
| Map hoặc filter xong cursor lệch | Dùng chỉ số của List đã đổi trên Window nguồn | Giữ ánh xạ phần tử-vị trí đúng thứ tự |
| Đổi filter rồi kết quả khó hiểu | Cursor cũ thuộc tập query khác | Giữ hoặc kiểm tra mô tả query cùng cursor |
| Bỏ sót khi xử lý NEW thành DONE | Offset chạy trên tập đang co lại | Đánh giá lại chiến lược scrolling và nhất quán |
| HasNext false nhưng sau đó có dữ liệu mới | Hiểu metadata một lần đọc là trạng thái vĩnh viễn | Phân biệt quét hiện tại với theo dõi dữ liệu mới |

Khi chẩn đoán, cần đối chiếu bộ lọc, sort, loại vị trí, kích thước Window và phần tử mốc thực tế. Không cần phụ thuộc tên lớp proxy nội bộ để giải thích phần lớn các lỗi này.

## 14. Các ca kiểm chứng trong dự án thực tế

| Ca | Điều cần bảo vệ |
| --- | --- |
| Kết quả ban đầu rỗng | Không gọi positionAt khi không có phần tử |
| Chỉ có một phần tử | Index cuối là 0, không phải 1 |
| Cửa sổ cuối ngắn hơn giới hạn | Chọn index theo size thực tế |
| Nhiều cửa sổ trên dữ liệu ổn định | Không mất hoặc lặp phần tử ngoài ý định |
| Cửa sổ thứ hai trở đi | Chỉ số vẫn bắt đầu từ 0, vị trí nguồn vẫn đúng |
| Tiếp tục từ index giữa | Đúng phần sau mốc, không tự vượt toàn bộ Window |
| Window cuối không rỗng | Vẫn có vị trí hợp lệ để lưu checkpoint |
| Offset initial so với offset 0 | Không bỏ phần tử đầu ngoài ý muốn |
| Nhiều giá trị occurredAt bằng nhau | Khóa phụ tạo thứ tự và mốc tiếp tục đúng |
| Query trả projection | Có đủ dữ liệu để mô-đun trích vị trí |
| Handler lỗi giữa cửa sổ | Checkpoint không vượt phần chưa xác nhận |
| Lưu checkpoint thất bại | Không đánh dấu hoàn thành ngầm; hành vi thử lại được xác định |
| Xử lý song song | Chỉ tiến qua tiền tố đã hoàn thành |
| Đổi bộ lọc hoặc sort | Không tái dùng cursor trái hợp đồng |
| Đọc và đổi trạng thái trong cùng job | Không bỏ qua dữ liệu vì tập phù hợp thay đổi |

Một Window được dựng sẵn có thể giúp kiểm chứng logic chọn index hoặc tiến độ handler. Nó không chứng minh query scrolling của mô-đun đã ánh xạ khóa, offset và giới hạn đúng trên kho dữ liệu.

Các đặc tính đó cần kiểm chứng tích hợp với module và dữ liệu đại diện. Đặc biệt, nếu mọi thời điểm đều khác nhau hoặc số phần tử luôn ít hơn giới hạn, chưa đủ để phát hiện lỗi khóa phụ và bước chuyển qua nhiều cửa sổ.

Không nên dùng riêng số lần gọi repository để kết luận mọi phần tử đã được xử lý. Cần đối chiếu danh tính, thứ tự và trạng thái hoàn thành của dữ liệu quan sát được.

## 15. Quy trình dùng positionAt trong một luồng đọc

1. **Chọn query và chiến lược scrolling được hỗ trợ.** Giữ bộ lọc và sort rõ ràng.
2. **Khởi tạo bằng vị trí ban đầu đúng loại.** Không nhầm initial với một mốc phần tử đã tồn tại.
3. **Đọc Window và kiểm tra rỗng.** Không tính index cuối trước khi biết có phần tử.
4. **Xử lý phần dữ liệu cần tiêu thụ.** Ghi nhận thành công theo hợp đồng của tác vụ.
5. **Chọn index của phần tử cuối đã được xác nhận trong tiền tố.** Nếu cả Window thành công, thường là size trừ 1.
6. **Lấy ScrollPosition bằng positionAt.** Không tự cộng thêm offset hoặc khóa.
7. **Lưu checkpoint hoặc truyền vị trí cho query tiếp theo.** Giữ đúng kiểu và ngữ cảnh query.
8. **Dùng hasNext để quyết định đọc tiếp trong lượt hiện tại.** Phân biệt metadata này với checkpoint bền và trạng thái dữ liệu tương lai.
9. **Xử lý thay đổi và thử lại có chủ đích.** Không coi vị trí đọc là bảo đảm exactly-once hoặc snapshot.

## 16. Tình huống tự đánh giá

### A. Cửa sổ cuối có 7 phần tử

Query giới hạn 50 phần tử. Người viết luôn gọi `positionAt(49)` sau khi xử lý, kể cả ở cửa sổ cuối chỉ có 7 phần tử.

Xác định chỉ số đúng và điều kiện cần kiểm tra trước khi tính chỉ số. Giải thích vì sao giới hạn query không phải size của mọi Window.

### B. Không thấy phần tử đầu

Chương trình bắt đầu bằng `ScrollPosition.offset(0)` vì cho rằng số 0 luôn biểu thị bắt đầu từ đầu.

Phân biệt vị trí ban đầu với vị trí của phần tử đầu. Nêu cách kiểm chứng để phát hiện phần tử bị bỏ qua.

### C. Checkpoint trước khi xử lý

Window có A, B, C. Job lưu vị trí sau C ngay khi tải xong, sau đó thất bại ở B.

Giải thích nguy cơ bỏ sót khi chạy lại. Xác định vị trí có thể lưu nếu chỉ A đã hoàn thành và chính sách cần có cho khoảng giữa hiệu ứng với lưu checkpoint.

### D. Chỉ số sau khi lọc

Window gốc có `[101, 102, 103]`, List hiển thị sau lọc có `[101, 103]`. Chương trình gọi `window.positionAt(filtered.size() - 1)`.

Chỉ ra phần tử mà vị trí thực sự gắn vào. Đề xuất cách giữ đúng quan hệ giữa dữ liệu nguồn đã tiêu thụ và cursor.

### E. Đọc NEW rồi đổi thành DONE

Job dùng offset, đọc một cửa sổ NEW và đổi toàn bộ chúng sang DONE trước khi gọi tiếp. Một số sự kiện NEW còn lại không được xử lý.

Giải thích cách tập phù hợp bị co lại làm vị trí số lượng mất ý nghĩa mong muốn. Đánh giá những điều cần giữ ổn định nếu chuyển sang keyset hoặc một chiến lược khác.

### F. Tác vụ C hoàn thành trước B

Ba phần tử được xử lý song song. A và C xong nhưng B còn lỗi; hệ thống muốn lưu vị trí của C vì đó là index lớn nhất đã hoàn thành.

Giải thích vì sao checkpoint cần một tiền tố hoàn thành liên tục và cách suy nghĩ đúng về tiến độ trong thứ tự query.