# Sự khác nhau giữa ScrollPosition.offset() và offset(0)

## Mục tiêu bài học

Trong offset scrolling của Spring Data, một vị trí cuộn mô tả mốc để tiếp tục đọc **sau** mốc đó. Vì vậy, `ScrollPosition.offset()` và `ScrollPosition.offset(0)` có ý nghĩa khác nhau dù cả hai thường bị liên tưởng đến “bắt đầu từ 0”.

Sau bài học, bạn có thể:

- Phân biệt vị trí khởi đầu với vị trí offset cụ thể.
- Giải thích vì sao dùng `offset(0)` cho lần đọc đầu có thể bỏ mất phần tử đầu tiên.
- Lấy vị trí tiếp tục từ `Window` mà không tự cộng sai offset.
- Chuyển đổi có chủ đích giữa số phần tử muốn bỏ qua và mốc offset scrolling.
- Giữ nguyên sự phân biệt INITIAL và AFTER khi lưu hoặc truyền cursor.

Các ví dụ sử dụng Scrolling API của Spring Data Commons trong dòng phiên bản có hỗ trợ, cùng một module lưu trữ hỗ trợ query method trả `Window<T>`. Việc có abstraction trong dependency chưa bảo đảm mọi store hay mọi loại truy vấn đều hỗ trợ scrolling.

## 1. Hai factory không tương đương

```java
import org.springframework.data.domain.OffsetScrollPosition;
import org.springframework.data.domain.ScrollPosition;

OffsetScrollPosition initial = ScrollPosition.offset();
OffsetScrollPosition afterFirst = ScrollPosition.offset(0);
```

| Biểu thức | Ý nghĩa | Phần tử đầu tiên có thể được đọc tiếp |
| --- | --- | --- |
| `ScrollPosition.offset()` | Vị trí khởi đầu, chưa đi qua phần tử nào | Phần tử ở chỉ số 0 |
| `ScrollPosition.offset(0)` | Tiếp tục sau phần tử ở chỉ số 0 | Phần tử ở chỉ số 1 |

Offset cụ thể là một mốc có ngữ nghĩa exclusive: tiếp tục sau mốc, không đọc lại phần tử tại mốc.

Có thể hình dung:

```text
                    Chỉ số:     0      1      2      3
                               A      B      C      D

Vị trí initial:          ↑
                        trước A

Vị trí offset(0):               ↑
                                sau A, trước B
```

Các chỉ số trên thuộc tập kết quả đã được lọc và sắp xếp. Chúng không phải định danh domain và không nhất thiết trùng với bất kỳ giá trị `id` nào.

Nếu muốn đọc toàn bộ tập từ đầu, dùng `ScrollPosition.offset()` cho lần gọi đầu tiên.

## 2. Offset scrolling dùng mốc đã đi qua

Giả sử thứ tự kết quả ổn định là:

| Chỉ số trong kết quả | id sản phẩm |
| --- | --- |
| 0 | 10 |
| 1 | 20 |
| 2 | 30 |
| 3 | 40 |
| 4 | 50 |
| 5 | 60 |
| 6 | 70 |
| 7 | 80 |

Với một cửa sổ tối đa ba phần tử:

| Vị trí được truyền | Số phần tử đứng trước lần đọc mới | Nội dung mong đợi |
| --- | --- | --- |
| `offset()` | 0 | 10, 20, 30 |
| `offset(0)` | 1 | 20, 30, 40 |
| `offset(2)` | 3 | 40, 50, 60 |
| `offset(5)` | 6 | 70, 80 |
| `offset(7)` | 8 | Rỗng |

Với offset cụ thể `o`, chỉ số bắt đầu của lần đọc tiếp có ý nghĩa:

```text
 nextStartIndex = o + 1
```

Với vị trí initial:

```text
 nextStartIndex = 0
```

Đây là sự khác biệt giữa **mốc đã đi qua** và **số phần tử muốn bỏ qua**. Không chuyển hai khái niệm thành cùng một con số mà không đổi quy tắc.

### Không suy diễn offset từ id

Sau khi đọc sản phẩm có id 30 ở chỉ số 2, mốc offset của nó là 2, không phải 30. Truyền `ScrollPosition.offset(30)` không có nghĩa tiếp tục sau sản phẩm id 30; nó mô tả một vị trí khác trong tập kết quả.

Nếu muốn tiếp tục dựa trên giá trị khóa và thứ tự, đó là hướng keyset scrolling trong store có hỗ trợ, với một loại thông tin vị trí khác.

## 3. Nhận diện vị trí initial bằng API

```java
OffsetScrollPosition initial = ScrollPosition.offset();
OffsetScrollPosition zero = ScrollPosition.offset(0);

boolean firstIsInitial = initial.isInitial(); // true
boolean secondIsInitial = zero.isInitial();   // false
long secondOffset = zero.getOffset();         // 0
```

`isInitial()` là cách phân biệt trạng thái bắt đầu. Không coi mọi vị trí có liên quan đến số 0 là initial.

### Không đọc offset hữu hạn của initial như một giá trị thông thường

Vị trí initial chưa có một offset cụ thể của phần tử đã đi qua. Không gọi `getOffset()` trên initial để lấy “offset bắt đầu”; API không cung cấp nó theo hợp đồng đó và lời gọi có thể ném lỗi trạng thái như `IllegalStateException`.

Một hàm mô tả vị trí cho log hoặc kiểm tra có thể là:

```java
static String describe(OffsetScrollPosition position) {
    if (position.isInitial()) {
        return "INITIAL";
    }

    return "AFTER_INDEX_" + position.getOffset();
}
```

Không dựa vào một giá trị sentinel nội bộ và không tự gọi `offset(-1)` để dựng initial. Dùng factory không đối số để thể hiện trạng thái khởi đầu theo API công khai.

## 4. Ví dụ repository trả Window

Giả sử domain Product có `id`, `tenantId` và `active`. Dùng thứ tự id tăng dần để minh họa, với id duy nhất trong phạm vi tenant:

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.repository.Repository;

interface ProductScrollRepository extends Repository<Product, Long> {

    Window<Product> findFirst3ByTenantIdAndActiveTrueOrderByIdAsc(
            String tenantId, ScrollPosition position);
}
```

Ví dụ cần module hỗ trợ derived query cùng Scrolling API này. Mọi lời gọi trong bài truyền một vị trí offset; chữ ký nhận ScrollPosition không có nghĩa mọi loại vị trí đều được mọi store hỗ trợ.

Trong hợp đồng scrolling được minh họa:

- `TenantId` và `ActiveTrue` giới hạn phạm vi dữ liệu.
- `OrderByIdAsc` xác định thứ tự.
- `First3` đặt kích thước tối đa của cửa sổ được lấy trong mỗi lần gọi.
- `ScrollPosition` là tham số đặc biệt mô tả điểm tiếp tục.
- `Window<Product>` chứa nội dung cùng thông tin vị trí và khả năng có cửa sổ sau.

Kích thước cửa sổ ở đây phục vụ việc đọc nhiều đợt. Không hiểu rằng toàn bộ quá trình cuộn chỉ được phép đọc đúng ba sản phẩm rồi tự dừng.

### So sánh hai lần gọi đầu

```java
Window<Product> fromBeginning = repository
        .findFirst3ByTenantIdAndActiveTrueOrderByIdAsc(
                tenantId, ScrollPosition.offset());

Window<Product> afterIndexZero = repository
        .findFirst3ByTenantIdAndActiveTrueOrderByIdAsc(
                tenantId, ScrollPosition.offset(0));
```

Với dữ liệu tám sản phẩm ở phần trước:

```text
fromBeginning  → 10, 20, 30
afterIndexZero → 20, 30, 40
```

Cả hai query có thể thực thi hợp lệ. Lỗi của việc dùng `offset(0)` để bắt đầu không nhất thiết là một exception; nó có thể là dữ liệu bị bỏ qua âm thầm.

## 5. Lấy mốc tiếp tục từ Window

Sau lần đọc đầu:

```java
Window<Product> first = repository
        .findFirst3ByTenantIdAndActiveTrueOrderByIdAsc(
                tenantId, ScrollPosition.offset());
```

Nếu first có ba phần tử, các chỉ số bên trong cửa sổ là 0, 1 và 2. Vị trí của phần tử cuối được lấy bằng:

```java
ScrollPosition resumeAfterLast = first.positionAt(first.size() - 1);
```

Với cửa sổ đầu gồm id 10, 20, 30, vị trí đó tương ứng mốc offset 2. Lần đọc tiếp bắt đầu sau phần tử ở mốc 2:

```java
Window<Product> second = repository
        .findFirst3ByTenantIdAndActiveTrueOrderByIdAsc(
                tenantId, resumeAfterLast);
```

Kết quả là id 40, 50, 60 trong dữ liệu ổn định.

### Chỉ số trong Window và offset toàn cục là hai giá trị khác nhau

| Cửa sổ | Nội dung | Chỉ số phần tử cuối trong cửa sổ | Offset của phần tử cuối trong tập kết quả |
| --- | --- | --- | --- |
| 1 | 10, 20, 30 | 2 | 2 |
| 2 | 40, 50, 60 | 2 | 5 |
| 3 | 70, 80 | 1 | 7 |

`positionAt(...)` nhận chỉ số cục bộ của phần tử trong Window, rồi cung cấp ScrollPosition tương ứng. Không tự gọi `offset(window.size() - 1)` sau mọi cửa sổ, vì từ cửa sổ thứ hai cách đó sẽ quay về một mốc quá sớm.

Cũng không dùng `positionAt(window.size())`: chỉ số đó nằm sau phần tử cuối và không phải một phần tử hợp lệ để lấy vị trí.

### Không cộng thêm 1 vào mốc trả về

Nếu phần tử cuối có offset 2, truyền chính mốc đó để đọc sau nó. Tự đổi thành `offset(3)` sẽ yêu cầu tiếp tục sau phần tử ở chỉ số 3, làm bỏ qua thêm một phần tử.

Ngữ nghĩa exclusive đã được hạ tầng xử lý; người gọi không cần cộng bù lần nữa.

## 6. Vòng lặp đọc nhiều cửa sổ

```java
import java.util.function.Consumer;

import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

void consumeAll(
        ProductScrollRepository repository,
        String tenantId,
        Consumer<Product> consumer) {

    ScrollPosition position = ScrollPosition.offset();

    while (true) {
        Window<Product> window = repository
                .findFirst3ByTenantIdAndActiveTrueOrderByIdAsc(
                        tenantId, position);

        if (window.isEmpty()) {
            break;
        }

        for (Product product : window) {
            consumer.accept(product);
        }

        if (!window.hasNext()) {
            break;
        }

        position = window.positionAt(window.size() - 1);
    }
}
```

Phương thức minh họa được đặt trong một lớp của ứng dụng. Các điểm quan trọng:

1. Khởi tạo bằng factory `offset()` không đối số.
2. Kiểm tra cửa sổ rỗng trước khi lấy vị trí của phần tử.
3. Xử lý các phần tử của cửa sổ hiện tại.
4. Chỉ yêu cầu cửa sổ tiếp khi kết quả báo còn dữ liệu.
5. Dùng vị trí phần tử cuối đã xử lý làm mốc tiếp tục.

Với dữ liệu minh họa, chuỗi cửa sổ là:

```text
INITIAL
   ↓
10, 20, 30       mốc cuối: offset(2)
   ↓
40, 50, 60       mốc cuối: offset(5)
   ↓
70, 80          không có cửa sổ sau
```

Nếu lưu checkpoint cho một tác vụ xử lý dữ liệu, chỉ ghi nhận mốc sau khi phần dữ liệu tương ứng đã được xử lý thành công theo thiết kế. Việc có ScrollPosition không tự bảo đảm hiệu ứng xử lý đúng một lần; retry và tính idempotent vẫn thuộc hợp đồng của tác vụ.

## 7. So sánh với Pageable và offset của backend

Một nguồn nhầm lẫn phổ biến là mang ý nghĩa của SQL OFFSET hoặc Pageable sang offset scrolling.

Với Pageable, offset thường có nghĩa số phần tử muốn bỏ qua. Với OffsetScrollPosition cụ thể, con số mô tả mốc phần tử đã đi qua.

Ví dụ size 3:

| Yêu cầu trang | Số phần tử cần bỏ qua | Vị trí offset scrolling tương ứng về điểm bắt đầu |
| --- | --- | --- |
| PageRequest trang 0 | 0 | `ScrollPosition.offset()` |
| PageRequest trang 1 | 3 | `ScrollPosition.offset(2)` |
| PageRequest trang 2 | 6 | `ScrollPosition.offset(5)` |

Sự tương ứng này giả định cùng dữ liệu, cùng bộ lọc và cùng thứ tự. Nó mô tả điểm bắt đầu, không khẳng định Page và Window có cùng metadata hay chi phí truy vấn.

### Chuyển số phần tử muốn bỏ qua thành mốc

Nếu viết một adapter có đầu vào là số phần tử bỏ qua, có thể dùng một hàm chuyển đổi rõ nghĩa:

```java
static OffsetScrollPosition positionForSkippedCount(long skippedCount) {
    if (skippedCount < 0) {
        throw new IllegalArgumentException(
                "Số phần tử bỏ qua phải lớn hơn hoặc bằng 0");
    }

    return skippedCount == 0
            ? ScrollPosition.offset()
            : ScrollPosition.offset(skippedCount - 1);
}
```

Đây là helper của ứng dụng, không phải factory bổ sung của Spring Data.

Nếu dòng Pageable đang dùng có API chuyển sang ScrollPosition, hãy dùng theo đúng hợp đồng của phiên bản và xác minh điểm bắt đầu. Đừng tự viết `ScrollPosition.offset(pageable.getOffset())` chỉ vì hai API cùng có từ offset: cách ghép đó có thể bỏ qua thêm một phần tử.

Unpaged không tự cung cấp một offset hữu hạn để chuyển thành một vị trí cuộn tương đương. Cần quyết định riêng nếu adapter cho phép đầu vào không phân trang.

## 8. Lưu hoặc truyền cursor mà không làm mất trạng thái

Một token offset scrolling cần giữ được khác biệt giữa vị trí ban đầu và mốc cụ thể bằng 0.

Hai cấu trúc minh họa:

```json
{
  "mode": "OFFSET",
  "state": "INITIAL"
}
```

```json
{
  "mode": "OFFSET",
  "state": "AFTER",
  "offset": 0
}
```

Token thứ nhất bắt đầu từ phần tử đầu. Token thứ hai tiếp tục sau phần tử đầu.

Đây là schema minh họa của ứng dụng, không phải định dạng serialization mặc định bắt buộc của Spring Data. Khi decode, cần khôi phục đúng factory:

```text
INITIAL  → ScrollPosition.offset()
AFTER 0  → ScrollPosition.offset(0)
AFTER 5  → ScrollPosition.offset(5)
```

### Không chuẩn hóa initial thành offset 0

Nếu hệ thống lưu mọi vị trí bằng một field số và dùng 0 thay cho trạng thái initial, sau khi khôi phục bằng `offset(0)` nó sẽ bỏ mất phần tử đầu.

Chiều ngược lại, nếu coi mọi offset 0 là initial, một cursor thật sự chỉ ra đã xử lý phần tử đầu sẽ đọc lại phần tử đó.

Cần có một discriminator, một trạng thái riêng hoặc một biểu diễn khác bảo toàn thông tin. Không suy ra trạng thái từ con số 0 đơn lẻ.

### Vị trí còn gắn với ngữ cảnh truy vấn

Offset 5 trong danh sách theo `id ASC` không có cùng ý nghĩa với offset 5 trong danh sách theo `createdAt DESC`. Tương tự, đổi tenant, trạng thái hoặc bộ lọc làm thay đổi tập mà chỉ số đang tham chiếu.

Một hợp đồng cursor cần bảo đảm truy vấn tiếp tục giữ đúng ngữ cảnh được phép dùng. Cursor không thay thế kiểm tra quyền và không tự xác nhận tenant mà người gọi được truy cập.

## 9. Điều kiện để một lần tiếp tục có ý nghĩa

### 9.1. Thứ tự phải được xác định

Một thứ tự chỉ theo `createdAt` có thể không phân biệt các phần tử trùng thời điểm. Với store hỗ trợ, nên có khóa phụ đủ phân biệt, chẳng hạn `createdAt DESC, id DESC`.

Trong ví dụ bài học, `id ASC` giúp thứ tự đơn giản và rõ ràng nếu id duy nhất trong phạm vi tenant. Không mặc định mọi mô hình đều có một id toàn cục duy nhất.

### 9.2. Đúng factory không tự tạo snapshot

Giả sử đã đọc A, B, C và giữ mốc offset 2:

```text
Trước thay đổi: A, B, C, D, E, F
```

Nếu có X được chèn trước A:

```text
Sau thay đổi:  X, A, B, C, D, E, F
```

Tiếp tục sau chỉ số 2 sẽ bắt đầu ở C, làm đọc lại một phần tử đã xử lý.

Nếu A bị xóa thay vì chèn X:

```text
Sau thay đổi:  B, C, D, E, F
```

Tiếp tục sau chỉ số 2 sẽ bắt đầu ở E, khiến D bị bỏ qua trong quá trình này.

Đây là vấn đề chỉ số dịch chuyển khi dữ liệu thay đổi, khác với lỗi khởi tạo bằng `offset(0)`. Sửa factory khởi đầu không tự giải quyết sự nhất quán qua nhiều lần query.

Nếu nghiệp vụ cần tránh loại dịch chuyển này, hãy đánh giá keyset scrolling hoặc cơ chế snapshot/transaction thích hợp theo store. Những cơ chế đó cũng có điều kiện và giới hạn riêng.

### 9.3. Offset sâu vẫn có chi phí

Backend có thể phải đi qua hoặc xử lý một phạm vi lớn trước khi trả cửa sổ ở offset sâu. Window nhỏ không tự bảo đảm việc lấy nó rẻ.

Cần xem bộ lọc, index, thứ tự và khả năng backend. Sự khác nhau giữa `offset()` và `offset(0)` là ngữ nghĩa điểm bắt đầu, không phải hai chế độ tối ưu hóa query.

## 10. Các lỗi lệch vị trí thường gặp

| Cách dùng | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `offset(0)` cho lần đọc đầu | Bỏ phần tử ở chỉ số 0 | Dùng `offset()` |
| Gọi getOffset trên initial như một offset thường | Có thể lỗi trạng thái | Kiểm tra `isInitial()` trước |
| Dùng id cuối làm offset | Nhảy tới vị trí không liên quan | Lấy mốc từ Window |
| Tạo offset bằng size trừ 1 sau mọi cửa sổ | Quay lại mốc quá sớm từ các cửa sổ sau | Dùng `window.positionAt(...)` |
| Cộng thêm 1 vào mốc phần tử cuối | Bỏ thêm một phần tử | Truyền nguyên ScrollPosition được trả về |
| Lấy `positionAt(window.size())` | Vượt chỉ số phần tử trong cửa sổ | Dùng size trừ 1 sau khi đã kiểm tra không rỗng |
| Luôn lấy positionAt dù Window rỗng | Không có phần tử để lấy vị trí | Xử lý empty trước |
| Lưu initial thành số 0 rồi decode bằng offset(0) | Mất phần tử đầu sau khi khôi phục | Giữ trạng thái initial riêng |
| Đổi bộ lọc hoặc sort nhưng giữ nguyên cursor | Mốc chỉ sang một tập khác | Giữ ngữ cảnh hoặc khởi động lại theo hợp đồng |

Không phải mọi lỗi đều tạo exception. Lỗi nguy hiểm nhất trong bài thường là một lần đọc hợp lệ nhưng thiếu đúng một phần tử, nên cần ca dữ liệu đủ nhỏ để quan sát được phần tử đầu.

## 11. Những ca dữ liệu phân biệt được hai factory

| Dữ liệu | Dùng offset() | Dùng offset(0) |
| --- | --- | --- |
| Rỗng | Rỗng | Rỗng |
| Một phần tử A | Có A | Rỗng |
| Hai phần tử A, B; cửa sổ size 1 | Bắt đầu bằng A | Bắt đầu bằng B |
| Nhiều phần tử, size 3 | Lấy từ chỉ số 0 | Lấy từ chỉ số 1 |

Chỉ kiểm tra tập rỗng sẽ không phát hiện việc chọn sai factory, vì cả hai đều trả rỗng. Tập một phần tử là ca đặc biệt rõ: dùng initial phải đọc được phần tử đó.

Với quá trình nhiều cửa sổ, nên xác minh:

- Mọi phần tử được đọc đúng theo thứ tự trong dữ liệu ổn định.
- Phần tử đầu không bị mất.
- Ranh giới giữa hai cửa sổ không bị lặp hoặc bỏ sót.
- Cửa sổ cuối thiếu phần tử vẫn được xử lý.
- Cửa sổ rỗng không dẫn tới `positionAt(-1)`.
- Lưu và khôi phục cursor giữ khác biệt giữa initial và offset 0.

Các ca này kiểm tra hợp đồng điểm bắt đầu. Tình huống thay đổi dữ liệu giữa các lần gọi cần được đánh giá riêng theo yêu cầu nhất quán.

## 12. Bài tập tự kiểm tra

### Bài 1: Bắt đầu từ đâu?

Tập kết quả đã sắp xếp là A, B, C, D. Cửa sổ tối đa hai phần tử. Hai lời gọi `offset()` và `offset(0)` bắt đầu bằng nội dung nào?

**Gợi ý đáp án:** Initial `offset()` trả A, B. `offset(0)` tiếp tục sau A nên trả B, C.

### Bài 2: Mốc sau cửa sổ đầu

Cửa sổ đầu có ba phần tử ở các chỉ số toàn cục 0, 1, 2. Mốc để tiếp tục là offset 2 hay offset 3?

**Gợi ý đáp án:** Offset 2, vì vị trí cụ thể được dùng theo ngữ nghĩa tiếp tục sau mốc. Offset 3 sẽ bỏ thêm phần tử ở chỉ số 3.

### Bài 3: Chỉ số cục bộ

Cửa sổ thứ hai gồm các phần tử ở chỉ số toàn cục 3, 4, 5. `window.positionAt(2)` có nên được hiểu là quay về offset 2 không?

**Gợi ý đáp án:** Không. Đối số 2 là chỉ số cục bộ trong Window; vị trí được cung cấp cho phần tử cuối tương ứng offset toàn cục 5 trong ví dụ.

### Bài 4: Token chỉ có số 0

Một hệ thống lưu token đầu bằng số 0, rồi khôi phục mọi số bằng `ScrollPosition.offset(value)`. Nó có bảo toàn ý nghĩa initial không?

**Gợi ý đáp án:** Không. `offset(0)` là sau phần tử đầu, không phải initial. Cần lưu trạng thái khởi đầu riêng.

### Bài 5: Đổi từ PageRequest

Muốn bỏ qua sáu phần tử đầu rồi đọc tiếp. Về điểm bắt đầu, nên dùng `offset(6)` hay `offset(5)`?

**Gợi ý đáp án:** Offset 5, vì đó là mốc phần tử cuối trong sáu phần tử đã bỏ qua. Với bỏ qua 0 phần tử, dùng factory không đối số.

### Bài 6: Đọc lại sau khi dữ liệu thay đổi

Khởi tạo đúng bằng `offset()` có bảo đảm không lặp/bỏ sót phần tử nếu dữ liệu bị chèn hoặc xóa trước mốc giữa các lần query không?

**Gợi ý đáp án:** Không. Offset là vị trí trong tập kết quả và có thể bị dịch chuyển. Cần đánh giá chiến lược scrolling và tính nhất quán riêng.

## Những điểm cần nhớ

- `ScrollPosition.offset()` biểu đạt chưa đi qua phần tử nào; `offset(0)` biểu đạt tiếp tục sau phần tử ở chỉ số 0.
- Offset scrolling dùng mốc exclusive, khác với số phần tử muốn bỏ qua trong phân trang offset thông thường.
- Dùng vị trí do Window cung cấp cho phần tử cuối đã xử lý; không tự cộng thêm hoặc dùng id thay offset.
- Kiểm tra cửa sổ rỗng và khả năng đi tiếp trước khi lấy vị trí hoặc gọi query tiếp theo.
- Cursor phải giữ trạng thái initial cùng ngữ cảnh truy vấn; factory đúng không tự tạo snapshot hay loại bỏ chi phí offset sâu.
