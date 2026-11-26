# OffsetScrollPosition và ý nghĩa vị trí bắt đầu

Trong offset scrolling của Spring Data, một vị trí thường biểu diễn điểm đã đi qua, không phải phần tử tiếp theo cần trả. Vì vậy, `ScrollPosition.offset()` và `ScrollPosition.offset(0)` là hai trạng thái khác nhau.

Nếu nhầm hai trạng thái này, một lần đọc đầu tiên có thể bỏ mất phần tử đầu, hoặc một lần đọc tiếp có thể lặp lại hay bỏ sót phần tử ở ranh giới cửa sổ.

Trong chương **Scrolling** của module `SPRING_DATA_COMMONS`, bài này giải thích hợp đồng của `OffsetScrollPosition`, cách bắt đầu và tiếp tục một lần cuộn, cùng giới hạn của offset trên một tập dữ liệu có thể thay đổi. Các ví dụ repository cần module store và phiên bản có hỗ trợ scrolling tương ứng; khai báo kiểu Commons không tự làm mọi store hỗ trợ cùng một cơ chế query.

## 1. Đặt OffsetScrollPosition vào bản đồ scrolling

Một lần scrolling thường có ba thành phần:

| Thành phần | Vai trò |
| --- | --- |
| Thứ tự truy vấn | Xác định trình tự các phần tử trong tập kết quả |
| `ScrollPosition` | Vị trí dùng để bắt đầu hoặc tiếp tục đọc |
| `Window<T>` | Một cửa sổ kết quả cùng thông tin để tiếp tục |

`OffsetScrollPosition` là một dạng `ScrollPosition`, dựa trên vị trí số trong tập kết quả đã được sắp thứ tự. Nó khác với keyset position, vốn mô tả điểm tiếp tục bằng giá trị các khóa sắp xếp theo cơ chế được store hỗ trợ.

Các kiểu dùng trong bài:

```java
import org.springframework.data.domain.OffsetScrollPosition;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
```

Không nên hiểu tên “position” là ID của entity. Nếu phần tử ở chỉ số 2 có ID 9000, offset position 2 vẫn là vị trí số 2 trong kết quả query, không phải một yêu cầu tìm ID bằng 2 hoặc 9000.

## 2. Hai trạng thái: initial và offset cụ thể

### 2.1. Initial: chưa đi qua phần tử nào

```java
OffsetScrollPosition start = ScrollPosition.offset();
```

Đây là vị trí khởi đầu, có thể hình dung nằm trước phần tử đầu tiên của tập kết quả.

```java
boolean initial = start.isInitial(); // true
```

Một query offset scrolling bắt đầu ở vị trí initial sẽ bắt đầu lấy từ phần tử đầu tiên, nếu có.

### 2.2. Offset cụ thể: tiếp tục sau phần tử ở vị trí đó

```java
OffsetScrollPosition afterFirst = ScrollPosition.offset(0);
```

Đây là một vị trí cụ thể, không phải initial:

```java
boolean initial = afterFirst.isInitial(); // false
long offset = afterFirst.getOffset();     // 0
```

Scrolling có ngữ nghĩa tiếp tục **sau** vị trí đã cho. Vì vậy, offset 0 có nghĩa là phần tử tại chỉ số 0 đã nằm phía trước ranh giới tiếp tục; cửa sổ sau bắt đầu từ chỉ số 1.

```text
Initial:
  | [0] [1] [2] [3] ...
  ↑ bắt đầu lấy từ đây

Offset 0:
    [0] | [1] [2] [3] ...
        ↑ tiếp tục sau phần tử số 0
```

### 2.3. Initial không phải một offset 0 bị ẩn

Hai đối tượng có ý nghĩa khác nhau:

| Cách tạo | `isInitial()` | Lần đọc bắt đầu ở đâu? |
| --- | --- | --- |
| `ScrollPosition.offset()` | true | Phần tử đầu tiên, chỉ số 0 |
| `ScrollPosition.offset(0)` | false | Sau phần tử chỉ số 0, tức từ chỉ số 1 |
| `ScrollPosition.offset(2)` | false | Sau phần tử chỉ số 2, tức từ chỉ số 3 |

Không thay factory không đối số bằng một factory nhận số 0 khi khởi tạo vòng lặp.

## 3. getOffset chỉ dùng khi có offset cụ thể

Với một vị trí cụ thể:

```java
OffsetScrollPosition position = ScrollPosition.offset(5);
long lastIndex = position.getOffset(); // 5
```

Với initial, không có offset cụ thể để đọc theo hợp đồng này. Gọi `getOffset()` trên initial sẽ bị từ chối bằng `IllegalStateException`.

Cần kiểm tra trạng thái:

```java
OffsetScrollPosition position = ScrollPosition.offset();

if (position.isInitial()) {
    System.out.println("Bắt đầu trước phần tử đầu tiên");
} else {
    System.out.println("Tiếp tục sau chỉ số " + position.getOffset());
}
```

Khi viết log hoặc serialize checkpoint, không gọi `getOffset()` vô điều kiện rồi mặc định initial sẽ cho số 0.

### 3.1. Không tự dùng số âm để biểu đạt initial

Factory nhận offset cụ thể yêu cầu giá trị không âm. Không dùng:

```java
ScrollPosition.offset(-1);
```

để thay cho vị trí bắt đầu. Hãy dùng factory `ScrollPosition.offset()` có ý nghĩa rõ ràng, thay vì phụ thuộc vào một giả định về sentinel nội bộ.

Điều quan trọng ở mức API là trạng thái `isInitial()`, không phải cách implementation lưu trạng thái đó trong một field.

## 4. Ví dụ với tập kết quả có thứ tự xác định

Giả sử query tìm các khách hàng đang hoạt động, sắp theo `id ASC`, và tại thời điểm quan sát có dữ liệu:

| Chỉ số trong kết quả query | ID khách hàng |
| --- | --- |
| 0 | 10 |
| 1 | 20 |
| 2 | 30 |
| 3 | 40 |
| 4 | 50 |
| 5 | 60 |
| 6 | 70 |
| 7 | 80 |

Chỉ số là vị trí trong **kết quả đã lọc và sắp thứ tự**, không phải số thứ tự vật lý của hàng trong database và cũng không phải ID.

Giả sử mỗi cửa sổ lấy tối đa 3 phần tử:

| Vị trí đầu vào | Chỉ số bắt đầu lấy | ID trong cửa sổ kế tiếp |
| --- | --- | --- |
| Initial | 0 | 10, 20, 30 |
| Offset 0 | 1 | 20, 30, 40 |
| Offset 2 | 3 | 40, 50, 60 |
| Offset 5 | 6 | 70, 80 |
| Offset 7 | 8 | Rỗng trong tập dữ liệu này |

Nếu gọi lần đầu với offset 0, khách hàng ID 10 bị bỏ qua. Không có exception bắt buộc để báo lỗi ý định đó: yêu cầu offset 0 là một yêu cầu tiếp tục hợp lệ, chỉ không phải yêu cầu khởi đầu.

### 4.1. Công thức phân biệt ranh giới và chỉ số tiếp theo

Trong mô hình offset scrolling tiến về trước:

```text
Initial:
  chỉ số bắt đầu lấy = 0

Offset k, với k >= 0:
  chỉ số bắt đầu lấy = k + 1
```

Công thức này giải thích ngữ nghĩa vị trí. Khi thực thi, store có thể có giới hạn biểu diễn và chi phí riêng; không coi mọi giá trị long lớn đều là một yêu cầu được backend hỗ trợ hoặc có thể thực thi hiệu quả.

### 4.2. Vị trí thuộc query, không thuộc riêng entity

Cùng khách hàng ID 40 có thể ở chỉ số 3 khi lọc các khách hàng đang hoạt động theo ID, nhưng ở một chỉ số khác khi lọc theo thành phố hoặc sắp theo ngày tạo.

Vì vậy, không lấy một offset từ query này rồi dùng lại với một query khác và kỳ vọng tiếp tục từ cùng entity. Bộ lọc và thứ tự là một phần của ngữ cảnh vị trí.

## 5. Lấy vị trí tiếp tục từ Window

Một repository minh họa:

```java
import org.springframework.data.domain.OffsetScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.repository.Repository;

interface CustomerRepository extends Repository<Customer, Long> {

    Window<Customer> findFirst3ByActiveTrueOrderByIdAsc(
        OffsetScrollPosition position
    );
}
```

Giả định `Customer` là domain type có `id` và `active`, được module ánh xạ phù hợp. Method dùng giới hạn 3, điều kiện đang hoạt động và thứ tự ID tăng dần. Module và phiên bản cần hỗ trợ derived query trả `Window` với offset scrolling.

Lần đọc đầu:

```java
Window<Customer> first = repository
    .findFirst3ByActiveTrueOrderByIdAsc(ScrollPosition.offset());
```

Nếu nội dung là ID 10, 20, 30, vị trí phần tử cuối được lấy bằng:

```java
ScrollPosition boundary = first.positionAt(first.size() - 1);
```

`positionAt` trả về hợp đồng tổng quát `ScrollPosition`. Trong luồng offset của ví dụ, vị trí mong đợi là `OffsetScrollPosition` có offset 2.

### 5.1. Chỉ số truyền vào positionAt là chỉ số cục bộ

`positionAt(2)` nói tới phần tử thứ ba **trong Window hiện tại**, không có nghĩa luôn tạo offset toàn cục bằng 2.

| Window | Nội dung | Chỉ số cục bộ của mục cuối | Offset của mục cuối |
| --- | --- | --- | --- |
| Thứ nhất | 10, 20, 30 | 2 | 2 |
| Thứ hai | 40, 50, 60 | 2 | 5 |
| Thứ ba | 70, 80 | 1 | 7 |

Window chứa cơ chế liên hệ phần tử với vị trí của nó trong query. Dùng `positionAt` giúp tránh tự tính lại từ số cửa sổ và kích thước dự kiến.

### 5.2. Không lấy vị trí cuối của một Window rỗng

Khi `window.size()` là 0, `window.size() - 1` là -1 và không phải chỉ số phần tử hợp lệ.

Kiểm tra rỗng trước khi gọi `positionAt`. Cũng không dùng một chỉ số bằng `window.size()` để yêu cầu “vị trí sau cửa sổ”; API nhận chỉ số của một phần tử có vị trí, không nhận chỉ số nằm ngoài nội dung.

### 5.3. Dùng đúng loại ScrollPosition

Nếu repository nhận `OffsetScrollPosition`, cần chuyển vị trí tổng quát về đúng loại đã xác định của luồng. Ví dụ có kiểm tra kiểu trong Java 17:

```java
ScrollPosition boundary = window.positionAt(window.size() - 1);

if (!(boundary instanceof OffsetScrollPosition next)) {
    throw new IllegalStateException(
        "Luồng offset nhận loại ScrollPosition không phù hợp"
    );
}

Window<Customer> following = repository
    .findFirst3ByActiveTrueOrderByIdAsc(next);
```

Đoạn này không phải một phép chuyển đổi keyset thành offset. Nó xác nhận kết quả thuộc đúng cơ chế scrolling mà ứng dụng đang sử dụng.

## 6. Vòng lặp đọc từng Window

Ví dụ dưới đây dùng `Consumer` để biểu diễn bước xử lý mỗi khách hàng:

```java
import java.util.function.Consumer;

import org.springframework.data.domain.OffsetScrollPosition;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

static void scan(
    CustomerRepository repository,
    Consumer<Customer> handler
) {
    OffsetScrollPosition position = ScrollPosition.offset();

    while (true) {
        Window<Customer> window = repository
            .findFirst3ByActiveTrueOrderByIdAsc(position);

        if (window.isEmpty()) {
            return;
        }

        for (Customer customer : window) {
            handler.accept(customer);
        }

        if (!window.hasNext()) {
            return;
        }

        ScrollPosition boundary = window.positionAt(window.size() - 1);
        if (!(boundary instanceof OffsetScrollPosition next)) {
            throw new IllegalStateException(
                "Cần vị trí offset để tiếp tục"
            );
        }

        position = next;
    }
}
```

Đặt method trong lớp thích hợp khi triển khai. Ví dụ giả định bộ lọc và thứ tự giữ nguyên, đồng thời việc xử lý không làm tập kết quả dịch chuyển theo cách phá vỡ các giả định offset; những biến động này được phân tích ở phần sau.

### 6.1. Ba điểm quyết định của vòng lặp

1. **Bắt đầu bằng initial**, không bắt đầu bằng offset 0.
2. **Xử lý nội dung rồi dùng thông tin tiếp tục của Window**, không đoán rằng mọi cửa sổ đủ 3 mục đều còn dữ liệu.
3. **Lấy vị trí của phần tử cuối**, không tự cộng một số cố định vào position.

Với dữ liệu tám khách hàng, luồng là:

```text
Initial
  -> [10, 20, 30]
     tiếp tục sau offset 2
  -> [40, 50, 60]
     tiếp tục sau offset 5
  -> [70, 80]
     không còn Window tiếp theo theo thông tin đã nhận
```

`hasNext()` là thông tin điều hướng của Window. Nó không phải tổng số phần tử toàn bộ tập dữ liệu và không bảo đảm tập dữ liệu không đổi sau khi cửa sổ được đọc.

### 6.2. Không dùng size bằng limit làm bằng chứng còn dữ liệu

Nếu tập kết quả có đúng 6 phần tử với giới hạn 3, cửa sổ thứ hai vẫn có đủ 3 mục nhưng có thể đã là cửa sổ cuối.

Một module có thể lấy thêm dữ liệu để xác định khả năng tiếp tục theo cách của nó. Caller nên dùng hợp đồng `hasNext()` thay vì tự thay bằng phép so sánh `window.size() == 3`.

### 6.3. Window không phải Page có tổng số

Window giúp xử lý từng phần và tiếp tục từ vị trí. Nó không công bố `totalElements` như Page và không phải một yêu cầu tính tổng số trang.

Không dùng số mục của Window hiện tại làm tổng số dữ liệu. Cũng không cần tải toàn bộ các Window chỉ để biết vị trí tiếp tục của cửa sổ đang có.

## 7. Checkpoint phải phản ánh phần tử đã xử lý thành công

Ví dụ vòng lặp trên xử lý toàn bộ Window trước khi đọc tiếp. Với một tiến trình có checkpoint bền vững, cần xác định rõ checkpoint có ý nghĩa gì.

Giả sử Window đầu là:

```text
Chỉ số cục bộ:      0   1   2
ID:               10  20  30
Offset:            0   1   2
```

Nếu chỉ ID 10 và 20 được xử lý thành công, vị trí tiếp tục phù hợp theo trạng thái ổn định của query là vị trí của ID 20:

```java
ScrollPosition checkpoint = window.positionAt(1);
```

Offset tương ứng là 1. Lần đọc sau bắt đầu từ chỉ số 2 và có thể trả ID 30, 40, 50.

Nếu lưu ngay vị trí cuối Window là offset 2 trong khi ID 30 chưa xử lý xong, lần tiếp tục sẽ bắt đầu sau ID 30. Việc đã đọc một phần tử không tự đồng nghĩa đã hoàn tất xử lý phần tử đó.

### 7.1. Vị trí đọc và vị trí hoàn tất có thể khác nhau

| Khái niệm | Ý nghĩa |
| --- | --- |
| Vị trí cuối Window đã tải | Đã nhận dữ liệu tới đâu |
| Vị trí xử lý thành công cuối | Đã hoàn tất công việc tới đâu |
| Checkpoint đã lưu | Điểm mà lần khôi phục sẽ dựa vào |

Ba vị trí có thể trùng trong một quy trình đơn giản, nhưng không mặc định luôn trùng.

### 7.2. OffsetScrollPosition không cung cấp exactly-once

Nếu lưu kết quả xử lý và checkpoint là hai thao tác không nguyên tử, một lỗi giữa chúng có thể dẫn đến xử lý lặp hoặc bỏ sót theo cách tổ chức của tiến trình.

Transaction, tính idempotent và cách phục hồi thuộc thiết kế xử lý của ứng dụng. Một đối tượng position chỉ mô tả điểm tiếp tục; nó không tự bảo đảm mỗi entity được xử lý đúng một lần.

Ngay cả checkpoint theo mục thành công cuối cũng cần tập kết quả có các giả định ổn định phù hợp. Nếu nội dung trước checkpoint bị thêm hoặc xóa, vị trí số có thể trỏ tới một ranh giới khác.

## 8. So sánh với số hàng cần bỏ qua và số trang

Một giá trị “offset” trong API khác có thể biểu diễn **số hàng cần bỏ qua**. `OffsetScrollPosition` cụ thể lại biểu diễn **chỉ số cuối nằm trước ranh giới tiếp tục**.

Để bắt đầu ở chỉ số s:

```text
s = 0  -> initial
s > 0  -> ScrollPosition.offset(s - 1)
```

Ví dụ helper chuyển đổi theo ngữ nghĩa đó:

```java
static OffsetScrollPosition positionForRowsToSkip(long rowsToSkip) {
    if (rowsToSkip < 0) {
        throw new IllegalArgumentException(
            "Số hàng cần bỏ qua không được âm"
        );
    }

    return rowsToSkip == 0
        ? ScrollPosition.offset()
        : ScrollPosition.offset(rowsToSkip - 1);
}
```

Helper chỉ chuyển ngữ nghĩa số, không giải quyết giới hạn hoặc chi phí backend.

### 8.1. Ví dụ khi bắt đầu từ quy ước PageRequest

Với chỉ số trang bắt đầu từ 0 và kích thước 3:

| Chỉ số trang | Số hàng cần bỏ qua | Vị trí scrolling tương ứng | Phần tử đầu mong đợi trong dữ liệu ví dụ |
| --- | --- | --- | --- |
| 0 | 0 | Initial | ID 10 |
| 1 | 3 | Offset 2 | ID 40 |
| 2 | 6 | Offset 5 | ID 70 |

Nếu lấy số hàng cần bỏ qua là 3 rồi gọi thẳng `ScrollPosition.offset(3)`, lần đọc bắt đầu từ chỉ số 4, tức ID 50. Một phần tử đã bị bỏ thêm so với ý định.

Nếu phiên bản stack cung cấp API chuyển đổi giữa các abstraction phân trang và scrolling, dùng đúng hợp đồng của API đó và kiểm chứng ranh giới. Không suy mọi giá trị cùng được gọi là “offset” đều có thể sao chép nguyên số qua lại.

### 8.2. Ba con số cần được đặt tên khác nhau

```text
pageNumber       = số trang
rowsToSkip       = số phần tử cần bỏ qua trước khi bắt đầu lấy
lastConsumedIndex = chỉ số đã đi qua trong ngữ nghĩa offset position
```

Đặt tên biến như `lastConsumedIndex` hoặc `rowsToSkip` khi phù hợp giúp người đọc thấy rõ phép chuyển đổi cần thiết. Một biến tên chung `offset` dễ che sự khác nhau một đơn vị.

## 9. Biểu diễn vị trí bắt đầu trong request hoặc checkpoint

Nếu đưa position ra ngoài tiến trình, phải giữ được sự khác nhau giữa initial và offset 0.

Một hợp đồng minh họa có thể dùng hai trạng thái tường minh:

```json
{
  "mode": "offset",
  "initial": true
}
```

Và:

```json
{
  "mode": "offset",
  "initial": false,
  "lastIndex": 0
}
```

Đây là định dạng do ứng dụng tự thiết kế, không phải định dạng JSON bắt buộc của Commons. Trạng thái đầu lấy từ phần tử đầu; trạng thái sau tiếp tục sau phần tử đầu.

### 9.1. Một quy ước dùng giá trị vắng mặt

Nếu hợp đồng chọn “không có lastIndex nghĩa là initial”, có thể diễn đạt phần chuyển đổi bằng:

```java
static OffsetScrollPosition decodeCheckpoint(Long lastConsumedIndex) {
    if (lastConsumedIndex == null) {
        return ScrollPosition.offset();
    }

    if (lastConsumedIndex < 0) {
        throw new IllegalArgumentException(
            "Checkpoint offset không được âm"
        );
    }

    return ScrollPosition.offset(lastConsumedIndex);
}
```

So sánh hai helper trong bài:

| Đầu vào 0 | Kết quả | Lý do |
| --- | --- | --- |
| `positionForRowsToSkip(0)` | Initial | Không bỏ qua phần tử nào |
| `decodeCheckpoint(0L)` | Offset 0 | Đã đi qua phần tử tại chỉ số 0 |

Chúng nhận hai loại ý nghĩa khác nhau, nên không thay thế nhau chỉ vì đều xử lý một số.

Ở biên HTTP hoặc message, không để một giá trị primitive mặc định 0 làm mất thông tin “caller chưa gửi checkpoint”. Cần giữ trạng thái vắng mặt theo hợp đồng đã chọn rồi mới tạo đối tượng position không-null cho repository.

### 9.2. Gắn checkpoint với ngữ cảnh truy vấn

Một checkpoint chỉ có số offset chưa đủ mô tả query mà nó thuộc về. Nếu tiến trình cần phục hồi đúng ý nghĩa, phải giữ hoặc xác định lại nhất quán các yếu tố như:

- Điều kiện lọc và phạm vi dữ liệu của lần cuộn.
- Thứ tự và cách phân biệt các giá trị bằng nhau.
- Phiên bản của hợp đồng checkpoint nếu có thay đổi.
- Ý nghĩa “đã đọc” hay “đã xử lý thành công” của điểm lưu.

Ngữ cảnh truy cập dữ liệu vẫn phải được ứng dụng xác định đúng khi đọc tiếp. Checkpoint không tự cấp quyền xem dữ liệu và không biến một offset thành vị trí dùng chung cho mọi query.

Nếu không dùng định dạng riêng, vẫn phải bảo đảm cơ chế serialize đã chọn xử lý được initial mà không cố gọi `getOffset()` như với một vị trí cụ thể.

## 10. Tập kết quả thay đổi làm vị trí số dịch chuyển

Giữ thứ tự duy nhất giúp loại một nguồn mơ hồ, nhưng không làm vị trí số bền vững trước mọi thay đổi dữ liệu.

Giả sử đã đọc ID 10, 20, 30 và lưu offset 2. Mỗi tình huống sau bắt đầu từ dữ liệu ban đầu ở phần 4 rồi có thay đổi trước lần đọc tiếp:

| Thay đổi | Đầu tập kết quả mới | Phần tử đầu sau offset 2 | Hệ quả |
| --- | --- | --- | --- |
| Không thay đổi | 10, 20, 30, 40, 50, ... | 40 | Tiếp tục như mong đợi |
| Thêm ID 5 trước các mục đã đọc | 5, 10, 20, 30, 40, ... | 30 | Có thể đọc lại mục đã xử lý |
| Xóa ID 10 | 20, 30, 40, 50, 60, ... | 50 | Có thể bỏ qua ID 40 chưa xử lý |

Offset 2 vẫn có nghĩa tiếp tục sau chỉ số 2 của lần query hiện tại. Nó không nhớ rằng lần trước index 2 tương ứng ID 30.

### 10.1. Handler tự làm thay đổi bộ lọc là một trường hợp đặc biệt quan trọng

Method ví dụ chỉ tìm `active = true`. Nếu handler xử lý xong ba mục đầu rồi đặt chúng thành `active = false`, tập phù hợp còn lại bắt đầu bằng:

```text
40, 50, 60, 70, 80
```

Tiếp tục sau offset 2 trên tập mới bắt đầu từ ID 70, không phải ID 40. Các mục 40, 50, 60 có thể bị bỏ qua dù ID luôn được sắp tăng dần.

Vì vậy, không dùng vòng lặp offset một cách máy móc cho một công việc đang làm các mục trước ranh giới rời khỏi tập query.

Thiết kế có thể cần tập ID cố định, một cách đọc có tính nhất quán phù hợp, hoặc cơ chế tiếp tục dựa trên khóa nếu module và bài toán hỗ trợ. Cần chọn theo yêu cầu xử lý; `OffsetScrollPosition` không tự cung cấp snapshot.

### 10.2. Thứ tự có tie-breaker vẫn cần thiết

Nếu chỉ sắp theo một thời điểm có nhiều giá trị bằng nhau, thứ tự giữa các mục có thể chưa được xác định đầy đủ ngay cả khi không chủ động sửa dữ liệu.

Một tiêu chí duy nhất như ID trong ví dụ, hoặc một tie-breaker phù hợp sau tiêu chí nghiệp vụ, giúp vị trí có nghĩa rõ hơn trên tập dữ liệu đang xét.

Đó là điều kiện hữu ích cho scrolling, nhưng không giải quyết được việc thêm/xóa hoặc thay đổi khóa sắp xếp làm dịch chuyển chỉ số.

## 11. Offset không đồng nghĩa với keyset hoặc cursor server

### 11.1. Một đối tượng position không bảo đảm chi phí đọc sâu nhỏ

Với nhiều store, query offset sâu vẫn có thể phải đi qua hoặc loại bỏ nhiều phần tử trước khi lấy cửa sổ cần trả. Một cửa sổ chỉ có 3 mục không chứng minh tổng công việc backend cũng chỉ tương ứng 3 mục.

Chi phí phụ thuộc store, query, index và dữ liệu. Kiểu `OffsetScrollPosition` không tự biến một query offset thành một phép seek theo khóa.

Giới hạn kích thước Window, phạm vi query và độ sâu cuộn là các quyết định ứng dụng cần xét theo khả năng thực tế. Một giá trị offset hợp lệ ở mức Commons vẫn có thể vượt giới hạn hữu ích hoặc giới hạn biểu diễn của backend.

### 11.2. Không mặc định có một ResultSet mở xuyên mọi lần gọi

Mỗi lần repository nhận position và trả Window có thể là một lần query riêng theo implementation. Abstraction không yêu cầu giữ một cursor database hoặc một transaction mở xuyên toàn bộ vòng lặp.

Do đó, không suy “đang ở cùng vòng scan” nghĩa là mọi Window nhìn thấy một snapshot duy nhất. Vòng đời tài nguyên và mức nhất quán thuộc store và cấu hình truy cập dữ liệu.

### 11.3. Keyset có ngữ nghĩa vị trí khác

Offset dựa trên vị trí số. Keyset scrolling dùng các giá trị khóa theo thứ tự query để biểu diễn ranh giới, theo khả năng module cung cấp.

Không tạo offset bằng ID cuối rồi coi đó là keyset, và không cast một keyset position thành offset để tiếp tục một method khác. Hai cơ chế có điều kiện hỗ trợ và cách tạo query khác nhau.

Nếu chuyển chiến lược, cần xem lại kiểu vị trí, thứ tự, dữ liệu cần để tạo checkpoint và hợp đồng phục hồi. Một tên chung `ScrollPosition` không có nghĩa mọi implementation có thể thay nhau nguyên trạng.

## 12. Kịch bản thực hành kiểm chứng ranh giới

Dùng dữ liệu có ID 10 đến 80 như bảng ở phần 4, mỗi Window tối đa 3 mục. Mỗi tình huống được xét trên tập dữ liệu ổn định tương ứng:

| Kịch bản | Điều cần kiểm chứng |
| --- | --- |
| Bắt đầu bằng `ScrollPosition.offset()` | Mục đầu là ID 10 |
| Bắt đầu bằng `ScrollPosition.offset(0)` | Mục đầu là ID 20 |
| Tiếp tục từ vị trí cuối Window đầu | Window sau có ID 40, 50, 60 |
| Lấy `positionAt(2)` của Window thứ hai | Nhận offset 5, không phải 2 |
| Tiếp tục từ offset 5 | Nhận ID 70, 80 |
| Chỉ hoàn tất hai mục đầu rồi lưu vị trí mục thứ hai | Lần đọc tiếp bắt đầu lại từ ID 30 |
| Query không có dữ liệu | Dừng mà không gọi positionAt với chỉ số -1 |
| Gọi getOffset trên initial | Bị từ chối theo hợp đồng API |
| Tạo offset cụ thể âm | Bị từ chối, không thay initial |
| Đổi rowsToSkip 3 thành position | Dùng offset 2 và bắt đầu từ ID 40 |
| Serialize rồi khôi phục offset 0 | Vẫn là vị trí cụ thể, không bị đổi thành initial |

Đây là kịch bản thiết kế thực hành, không phải kết quả của một bộ test đã được chạy trong bài.

Nên dùng ID không trùng chỉ số để phát hiện việc nhầm “vị trí” với “định danh”. Dữ liệu có ID 0, 1, 2 có thể che sự khác nhau đó trong một ví dụ quá đơn giản.

Để xem tác động của biến động dữ liệu, thực hiện riêng các tình huống thêm, xóa hoặc đổi `active` giữa hai lần lấy Window. Không trộn chúng với các kịch bản dữ liệu ổn định rồi gán mọi kết quả khác nhau cho lỗi cộng/trừ một.

## 13. Chẩn đoán những lỗi thường gặp

| Dấu hiệu | Điểm cần kiểm tra |
| --- | --- |
| Lần đọc đầu mất mục đầu tiên | Có dùng offset 0 thay initial không |
| Lần đọc tiếp mất một mục ở ranh giới | Có lấy số hàng cần bỏ qua rồi dùng thẳng làm position không |
| Window sau lặp lại các mục đầu | Có tự tạo offset từ chỉ số cục bộ thay vì dùng positionAt không |
| Log hoặc serialize lỗi ngay ở đầu scan | Có gọi getOffset trên initial không |
| Lỗi chỉ số khi query rỗng | Có lấy positionAt(size - 1) trước khi kiểm tra rỗng không |
| Mất mục sau khi xử lý một phần Window | Checkpoint có được lưu theo mục cuối đã tải thay vì mục cuối đã hoàn tất không |
| Xử lý cập nhật active rồi bị bỏ sót nhiều mục | Tập phù hợp có bị thu nhỏ trước ranh giới offset không |
| Dùng cùng checkpoint nhưng query khác cho kết quả lạ | Bộ lọc và thứ tự có còn cùng ngữ cảnh không |
| Offset sâu ngày càng chậm | Chi phí bỏ qua dữ liệu và giới hạn backend, không chỉ kích thước Window |
| Lỗi kiểu ScrollPosition | Method có đang nhận vị trí của đúng chiến lược không |

Khi điều tra, ghi rõ bốn thông tin: vị trí đầu vào có initial hay không, offset cụ thể nếu có, ID/thứ tự mục trong Window và vị trí được dùng cho lần kế tiếp. Tách chỉ số khỏi ID giúp nhìn ra lỗi ranh giới nhanh hơn một log chỉ ghi “offset hiện tại”.

## 14. Tự kiểm tra mức độ hiểu

1. Vì sao `ScrollPosition.offset()` khác `ScrollPosition.offset(0)`?
2. Offset 5 làm lần đọc tiếp bắt đầu từ chỉ số nào?
3. Tại sao không nên gọi `getOffset()` vô điều kiện khi vị trí có thể initial?
4. `window.positionAt(2)` nhận chỉ số cục bộ hay offset toàn cục?
5. Vì sao Window thứ hai có thể có phần tử cuối ở chỉ số cục bộ 2 nhưng offset 5?
6. Muốn bỏ qua đúng 6 phần tử, cần dùng vị trí nào theo helper chuyển đổi của bài?
7. Khi xử lý lỗi ở mục thứ ba, checkpoint cuối Window có chắc là checkpoint xử lý đúng không?
8. Sắp xếp theo ID duy nhất có ngăn việc offset dịch chuyển khi xóa dữ liệu không?
9. Vì sao position không tự cung cấp snapshot hoặc exactly-once?

Khi dùng offset scrolling, hãy xem vị trí là **ranh giới tiếp tục sau phần tử đã đi qua**, với initial là trạng thái riêng trước mục đầu. Bắt đầu bằng đúng factory, lấy vị trí tiếp tục từ Window và giữ ngữ cảnh query nhất quán sẽ giúp tránh phần lớn nhầm lẫn giữa chỉ số, số hàng cần bỏ qua và định danh entity.
