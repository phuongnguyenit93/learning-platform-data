# Chọn cấu trúc cho lịch sự kiện, gợi ý tiền tố và truy vấn thời gian

Một ứng dụng lịch tưởng như chỉ quản lý danh sách sự kiện, nhưng thực tế phải thực hiện nhiều kiểu truy vấn: hiển thị sự kiện theo ngày, tìm cuộc họp có tên bắt đầu bằng một cụm chữ, nhắc sự kiện sắp tới, phát hiện các cuộc họp trùng giờ, hoặc tổng hợp số sự kiện theo tuần. Nếu chỉ chọn một cấu trúc dữ liệu dựa trên phép toán “tìm kiếm” chung chung, ta rất dễ có một đường truy cập nhanh nhưng các chức năng khác lại chậm hoặc sai.

Trong chương **Lựa chọn và thiết kế**, ta sẽ chọn cấu trúc dựa trên ba nhóm nhu cầu:

1. **Lịch sự kiện:** quản lý bản ghi có thời điểm bắt đầu, kết thúc, mã sự kiện; hiển thị và cập nhật lịch.
2. **Gợi ý tiền tố:** tìm sự kiện có tiêu đề bắt đầu bằng chuỗi người dùng gõ, có thể trả nhiều kết quả hoặc `top-k`.
3. **Truy vấn thời gian:** tra cứu theo mốc bắt đầu, tìm khoảng thời gian giao nhau, nhắc việc đến hạn, hoặc tổng hợp theo các ô thời gian.

Bài vận dụng mảng, bảng băm, cây tìm kiếm, heap, trie, các cấu trúc truy vấn khoảng và những nguyên tắc bất biến/độ phức tạp thời gian–bộ nhớ. Điểm cốt lõi là **không có một cấu trúc duy nhất tối ưu cho mọi chức năng**; thiết kế hợp lý thường dùng một bản ghi nguồn và các chỉ mục phụ có nhiệm vụ rõ ràng.

## 1. Đặc tả tập sự kiện và thao tác cần hỗ trợ

Giả sử một sự kiện có:

```text
Event {
    id:             EventId
    title:          String
    startUTC:       Instant
    endUTC:         Instant
    timezone:       ZoneId
    reminderLead:   Duration?  // số thời gian nhắc trước, có thể không có
    status:         active | canceled
}
```

Trong ví dụ cơ bản, sự kiện có khoảng hiệu lực **`[startUTC, endUTC)`**: bao gồm thời điểm bắt đầu nhưng **không** bao gồm thời điểm kết thúc. Với sự kiện có thời lượng dương, yêu cầu `startUTC < endUTC`. Nếu nghiệp vụ có sự kiện tức thời với `startUTC = endUTC`, nên định nghĩa riêng ngữ nghĩa loại sự kiện đó thay vì mặc định chúng giao với mọi khoảng.

Các API minh họa:

| Phép toán | Kết quả phải có | Câu hỏi thiết kế |
| --- | --- | --- |
| `getById(id)` | Đúng một sự kiện nếu tồn tại | Cần tra ID nhanh, không phụ thuộc vị trí |
| `eventsStartingIn(a,b)` | Sự kiện có `a ≤ startUTC < b`, theo thứ tự bắt đầu | Dữ liệu đã sắp hay còn cập nhật? |
| `eventsOverlapping(a,b)` | Sự kiện có thời lượng giao với `[a,b)` | Cần xét cả thời gian kết thúc |
| `suggestTitle(prefix,k)` | Tối đa `k` tiêu đề/sự kiện khớp tiền tố | Thứ tự từ điển hay mức độ phù hợp? |
| `nextReminder()` | Nhắc việc có thời điểm kích hoạt sớm nhất | Chỉ cần cực trị hay cần tìm theo ID? |
| `popDueReminders(now)` | Các nhắc việc đến hạn theo thứ tự | Phải tránh gửi lặp/lọc nhắc việc đã hủy |
| `reschedule(id,newStart,newEnd)` | Đổi lịch và cập nhật mọi đường truy cập | Bất biến nhiều chỉ mục phải đồng bộ |
| `countInDay(day)` hoặc `sumInRange(a,b)` | Tổng hợp số lượng theo bucket thời gian | Cần cập nhật điểm/đoạn ra sao? |

Đừng nhầm “tìm theo thời gian” thành một phép toán duy nhất. Tìm sự kiện **bắt đầu** trong tuần khác với tìm sự kiện **đang diễn ra** trong tuần. Một cuộc họp bắt đầu từ cuối tháng trước nhưng kết thúc đầu tháng này không thuộc truy vấn “bắt đầu trong tháng”, song có thể thuộc truy vấn “giao với tháng”.

### Mô hình tải công việc

Gọi `n` là số sự kiện, `q_s` là số lần hỏi khoảng theo thời điểm bắt đầu, `q_o` là số lần hỏi giao khoảng, `q_p` là số lần gợi ý tiền tố, và `u` là số lần cập nhật. Ngoài độ phức tạp mỗi lần hỏi, cần tính chi phí dựng chỉ mục, duy trì khi đổi lịch và bộ nhớ phụ:

```text
T_total ≈ T_build
        + q_s × T_startRange
        + q_o × T_overlap
        + q_p × T_prefix
        + u × T_updateAllIndexes
        + T_reminderProcessing
```

Mỗi kiểu kết quả phải trả `k` bản ghi đều cần ít nhất `Ω(k)` công việc để xuất đủ chúng. Vì vậy, phát biểu “truy vấn khoảng `O(log n)`” là thiếu nếu truy vấn còn phải trả hàng nghìn sự kiện.

## 2. Đặt ngữ nghĩa thời gian đúng trước khi lập chỉ mục

Một chỉ mục rất nhanh vẫn có thể trả kết quả sai nếu không thống nhất cách biểu diễn thời gian.

### 2.1. Thời điểm tuyệt đối và giờ địa phương

Nên phân biệt:

- **Instant:** một thời điểm tuyệt đối, có thể lưu như số mili giây/giây UTC kể từ một mốc hoặc kiểu thời gian có timezone được quy đổi thống nhất.
- **Local date-time:** biểu diễn người dùng nhìn thấy, chẳng hạn “09:00 ngày 15/03 tại Hà Nội”.
- **Timezone ID:** vùng giờ có quy tắc lịch sử và thay đổi giờ theo chính sách, ví dụ `Asia/Ho_Chi_Minh`.
- **Duration:** khoảng cách thời gian tuyệt đối, như 30 phút.
- **Lịch lặp:** quy tắc như “9 giờ sáng mỗi thứ Hai theo giờ địa phương”, không chỉ là một Instant cố định.

Sự kiện đơn lẻ thường nên được **lập chỉ mục theo Instant chuẩn hóa**, trong khi hiển thị và diễn giải yêu cầu theo ngày địa phương phải dùng timezone tương ứng. Không nên so sánh chuỗi giờ địa phương từ hai vùng khác nhau như thể chúng nằm trên cùng một trục thời gian.

Khi ứng dụng có múi giờ áp dụng giờ mùa hè, một ngày địa phương có thể dài 23 hoặc 25 giờ. Nếu người dùng hỏi các sự kiện trong một ngày địa phương, hãy **chuyển biên đầu ngày và biên đầu ngày kế tiếp ở vùng giờ đó sang Instant**, thay vì luôn cộng 24 giờ UTC.

### 2.2. Khoảng nửa mở và điều kiện giao nhau

Với hai sự kiện có khoảng `[s_1,e_1)` và `[s_2,e_2)`, chúng giao nhau khi:

```text
s_1 < e_2  AND  s_2 < e_1
```

Ví dụ:

```text
A: [09:00, 10:00)
B: [10:00, 11:00)    => A và B KHÔNG giao nhau

C: [09:30, 10:15)    => A và C giao nhau

D: [08:00, 12:00)    => D giao cả A, B và C
```

Một truy vấn hỏi “sự kiện giao với `[a,b)`” cần kiểm tra:

```text
event.startUTC < b AND a < event.endUTC
```

Nếu chỉ tìm sự kiện có `startUTC ∈ [a,b)`, sự kiện D bắt đầu trước `a` sẽ bị bỏ sót mặc dù đang diễn ra trong khoảng hỏi.

### 2.3. Lịch lặp lại và ngoại lệ

Một cuộc họp “thứ Hai hàng tuần” có thể tạo **vô hạn số lần diễn ra**. Không thể chèn vô hạn bản ghi vào heap hoặc cây thời gian. Thường có hai lớp dữ liệu:

- **Quy tắc lặp gốc**: tần suất, timezone, thời điểm địa phương, ngày kết thúc (nếu có).
- **Lần diễn ra (occurrence)**: những khoảng thời gian cụ thể được mở rộng cho một chân trời hữu hạn, chẳng hạn 30 hoặc 90 ngày tiếp theo.

Khi truy vấn vượt chân trời đã mở rộng, hệ thống cần sinh thêm occurrence hoặc tính các lần khớp theo quy tắc. Sự kiện lặp có thể có **ngoại lệ**: hủy một lần, đổi giờ riêng một lần, hoặc đổi quy tắc từ một ngày. Mỗi occurrence cần định danh ổn định, chẳng hạn `(seriesId, originalOccurrenceStart)`, để không tạo trùng khi sinh lại.

Một lịch lặp theo “09:00 giờ địa phương” không nên được hiện thực bằng cách **cộng đúng 24 giờ UTC** mỗi lần nếu mục tiêu là giữ nguyên giờ địa phương qua các lần đổi quy tắc múi giờ.

## 3. Chọn cấu trúc cho lịch theo thời điểm bắt đầu

### 3.1. Dữ liệu tĩnh: mảng sắp có thể là đủ

Nếu ứng dụng nhập một lần rồi chủ yếu đọc lịch, hãy lưu mảng các khóa:

```text
byStart = sorted((startUTC, eventId) for each event)
```

Với khóa ghép `(startUTC,eventId)`, hai sự kiện cùng thời điểm bắt đầu vẫn có thứ tự tất định và không ghi đè nhau. Tìm cận dưới `lowerBound((a, ...))`, rồi duyệt đến khi `startUTC ≥ b`.

- Xây dựng từ `n` phần tử: `O(n log n)` với sắp xếp so sánh.
- Tìm điểm bắt đầu: `O(log n)` lần so sánh.
- Liệt kê `k` kết quả: `O(k)` thêm vào truy vấn, tổng `O(log n+k)` trong mô hình so sánh khóa hằng số.
- Chèn/xóa giữa mảng: có thể `O(n)` do phải dịch phần tử.

Mảng sắp có tính liên tục bộ nhớ, thích hợp đọc tuần tự. Nếu dữ liệu đã có sẵn đúng thứ tự, không nên cộng lại chi phí sắp xếp khi không cần.

### 3.2. Dữ liệu động: cây tìm kiếm tự cân bằng

Nếu người dùng thường xuyên thêm, hủy và dời lịch, một cây AVL/red-black hoặc cây tìm kiếm tự cân bằng tương đương theo `(startUTC,eventId)` là lựa chọn đáng xét:

- Tìm/chèn/xóa theo khóa: `O(log n)` trường hợp xấu về số bước so sánh/cân bằng.
- Tìm cận dưới: `O(log n)`.
- Liệt kê liên tiếp `k` sự kiện sau cận: `O(k)` thêm khi có bộ duyệt cây thích hợp.

Cần giữ **khóa cũ** khi dời lịch: xóa `(oldStartUTC,id)` rồi thêm `(newStartUTC,id)`. Chỉ sửa trường `startUTC` trong bản ghi mà quên thay khóa cây sẽ làm truy vấn thời gian trả sai.

Nếu ứng dụng cần danh sách sự kiện theo **thứ tự tạo**, không phải thứ tự bắt đầu, cây theo `startUTC` chưa đáp ứng điều đó; phải chọn khóa hoặc chỉ mục tương ứng với hợp đồng duyệt.

### 3.3. Khi thời gian luôn đến tăng dần

Một luồng sự kiện append-only có thời gian không giảm có thể duy trì mảng sắp bằng cách thêm cuối `O(1)` khấu hao mà không phải dịch phần tử. Tuy nhiên, lịch do người dùng tạo thường **không** có đặc tính này: hôm nay người dùng có thể tạo một sự kiện sẽ diễn ra vào tháng trước hoặc dời cuộc họp sang ngày sớm hơn.

Hãy kiểm tra **bất biến đầu vào tăng dần** trước khi chọn giải pháp append-only. Nếu có sự kiện đến muộn, có thể chuyển sang cây hoặc dùng vùng delta rồi hợp nhất theo lô; truy vấn phải kết hợp các vùng mà không bỏ sót kết quả.

## 4. Heap cho nhắc việc đến hạn, không phải cho mọi truy vấn lịch

Một yêu cầu khác là “lấy nhắc việc sắp đến hạn nhất”. Ta có thể đặt thời điểm nhắc:

```text
remindAt = event.startUTC - reminderLead
```

Với **min-heap** theo khóa `(remindAt,sequence,eventId)`, đỉnh luôn là nhắc việc sớm nhất. Thứ tự chèn `sequence` hoặc một khóa phụ tất định giúp phá hòa khi nhiều nhắc việc cùng hạn.

| Thao tác | Min-heap nhị phân |
| --- | --- |
| `peekNext()` | `O(1)` xem đỉnh |
| `insertReminder` | `O(log r)` bước heap, `r` là số nhắc việc |
| `popDue` từng mục | `O(log r)` bước heap mỗi lần |
| Sửa/hủy theo `eventId` với heap thuần | Có thể `O(r)` để tìm đúng mục |
| Sửa/hủy với bảng vị trí `eventId → index` | Định vị kỳ vọng `O(1)` và sửa heap `O(log r)` kỳ vọng, với cập nhật bảng ở mọi lần swap |

Heap **không** trả hiệu quả mọi sự kiện trong một khoảng theo thứ tự tổng thể, và mảng heap **không được sắp hoàn toàn**. Do đó, một hệ thống vừa cần hiển thị lịch theo ngày vừa cần nhắc việc đúng hạn có lý do chính đáng để giữ **cây theo thời gian bắt đầu** và **heap theo thời gian nhắc**.

### 4.1. Hai cách cập nhật/hủy nhắc việc

**Indexed heap:** duy trì `pos[eventId] = index`. Khi sửa thời điểm nhắc, tìm vị trí rồi `siftUp/siftDown`; khi swap phải sửa vị trí của **cả hai** mục. Hữu ích khi cập nhật/hủy rất thường xuyên và muốn mỗi sự kiện chỉ có một mục nhắc đang hoạt động.

**Lazy invalidation:** không xóa mục cũ khỏi heap ngay. Mỗi lần đổi lịch tạo một mục mới kèm `version/token`; khi đến hạn, nếu mục lấy ra không còn khớp token đang hoạt động thì bỏ qua:

```text
schedule(id, newDue):
    token[id] = freshUniqueToken()
    heap.push((newDue, token[id], id))

popDue(now):
    while heap not empty and heap.min.due <= now:
        (due, t, id) = heap.popMin()
        if activeToken.get(id) != t:
            continue           // bản ghi cũ/hủy, bỏ qua
        remove activeToken[id]
        return validReminder(id, due)
    return NO_DUE
```

Lazy invalidation tránh thao tác tìm/xóa tùy ý trong heap và dễ dùng thư viện heap phổ biến, nhưng các mục cũ **vẫn chiếm bộ nhớ và phải được lấy ra/loại bỏ về sau**. Nếu lịch liên tục bị dời, heap có thể phình theo **số lần lập lịch đã phát sinh**, không chỉ theo số nhắc việc đang hoạt động; cần chính sách tái xây hoặc nén heap.

### 4.2. Tại sao chỉ dùng queue FIFO không đủ?

FIFO xử lý theo **thứ tự được đưa vào**, không phải **thời điểm đến hạn**. Nếu thêm nhắc việc A cho ngày mai trước nhắc việc B cho 5 phút nữa, queue FIFO sẽ đứng ở A dù B đến hạn sớm hơn.

Chỉ dùng queue FIFO khi dữ liệu được đưa vào **theo thứ tự thời điểm nhắc không giảm** và điều kiện ấy luôn đúng. Trong lịch thực tế có cập nhật và đặt lịch tùy ý, min-heap hoặc cấu trúc có thứ tự phù hợp hơn.

### 4.3. Timing wheel khi có nhiều timer

Với khối lượng timer rất lớn, giới hạn độ phân giải rõ ràng và phạm vi thời gian dự kiến phù hợp, có thể xét **timing wheel** hoặc cấu trúc bucket theo thời gian. Chúng tổ chức timer vào các ô theo mốc và có thể cho thao tác thêm/xử lý khá hiệu quả trong điều kiện phù hợp. Đổi lại cần thiết kế xử lý timer xa trong tương lai, vòng quay, độ chính xác và độ trễ khi một bucket chứa nhiều timer.

Timing wheel không phải thay thế mặc định cho min-heap: hãy chọn theo yêu cầu **độ phân giải, số timer, cách hủy/dời hạn và độ trễ chấp nhận được**.

## 5. Chọn cấu trúc cho gợi ý tiền tố tiêu đề

Khi người dùng gõ `"mee"`, ứng dụng muốn gợi ý các tên như `"meeting"` hoặc `"meetup"`. Đây là truy vấn **tiền tố**: kiểm tra xem dạng chuẩn hóa của tiêu đề có bắt đầu bằng một chuỗi hay không. Nó khác với tìm một từ **ở giữa** tiêu đề hoặc tìm kiếm toàn văn.

### 5.1. Mảng chuỗi đã sắp

Tạo chỉ mục:

```text
byTitle = sorted((normalize(title), eventId) for each event)
```

Để tìm tiền tố `p`:

1. Tính `p = normalize(inputPrefix)`.
2. Tìm cận dưới cho các tiêu đề không nhỏ hơn `p`.
3. Đi tới trước trong mảng khi tiêu đề còn `startsWith(p)`; dừng khi gặp khóa không khớp.

Ưu điểm:

- Một mảng sắp gọn, dễ dùng binary search; duyệt kết quả liền kề thuận lợi cho cache.
- Xây từ dữ liệu tĩnh tốn `O(n log n)` lần so sánh (bỏ qua độ dài chuỗi trong mô hình đơn giản).
- Mỗi truy vấn thường khoảng `O(log n + k)` phép so sánh/duyệt để trả `k` kết quả, nhưng một lần so sánh/kiểm tra tiền tố có thể tốn theo **độ dài chuỗi**.
- Chèn/xóa tiêu đề trong dãy sắp thường mất `O(n)` vì dịch phần tử.

Dùng cách này nếu **đọc nhiều, cập nhật ít** hoặc có thể xây lại chỉ mục theo lô.

### 5.2. Trie (cây tiền tố)

Trie lưu một đường đi ứng với các ký tự của từng tiêu đề chuẩn hóa. Mỗi nút biểu diễn một tiền tố; nút cuối của tiêu đề giữ tập ID (vì nhiều sự kiện có thể cùng tiêu đề).

```text
root
 └─ m
    └─ e
       ├─ e
       │  └─ t
       │     ├─ i ... "meeting" → {E1, E7}
       │     └─ u ... "meetup"  → {E4}
       └─ m ... "memo"          → {E2}
```

Với tiền tố `p` có độ dài `|p|`:

- Đi tới nút của `p`, thường mất `O(|p|)` bước ký tự nếu tìm cạnh hiệu quả.
- Duyệt cây con để xuất kết quả. Chi phí phụ thuộc **số nút thực sự thăm và số ký tự/ID phải xuất**, không chỉ `|p|`.
- Thêm/xóa một tiêu đề dài `L` thường `O(L)` bước theo ký tự (chưa kể số ID tại nút và overhead của cấu trúc lưu con).
- Bộ nhớ phụ có thể tỷ lệ tổng số ký tự của các tiêu đề trong trường hợp xấu, cùng các liên kết và tập ID.

Trie hấp dẫn khi nhiều truy vấn tiền tố trên tập thường xuyên đổi, các tiêu đề có tiền tố chung và cần thao tác theo độ dài từ khóa. Nhưng trie dạng mỗi ký tự một nút có thể tốn nhiều con trỏ và cấp phát; *radix tree / compressed trie* gộp các đoạn không phân nhánh để tiết kiệm bộ nhớ.

**Không được khẳng định mọi truy vấn tiền tố trên trie hoàn tất trong `O(|p|)`** nếu API phải liệt kê hàng nghìn kết quả; chỉ bước tìm nút tiền tố có chặn đó. Việc tạo kết quả có chi phí riêng.

### 5.3. Hash map có giúp tìm tiền tố không?

Hash map từ **toàn bộ tiêu đề** sang ID tra cứu chính xác kỳ vọng `O(1)`, nhưng không tự cho danh sách tất cả khóa bắt đầu bằng `p`. Quét mọi tiêu đề vẫn có thể mất `O(n)`.

Có thể xây map cho **mọi tiền tố**:

```text
prefixIndex["m"]   -> {E1, E2, E4, E7, ...}
prefixIndex["me"]  -> {E1, E2, E4, E7, ...}
prefixIndex["mee"] -> {E1, E4, E7, ...}
```

Cách này giúp tra chính xác tiền tố nhanh, nhưng một tiêu đề dài `L` sinh tới `L` khóa tiền tố; nếu mỗi tập ID được lưu tách biệt, tổng số liên kết ID có thể lớn theo tổng độ dài tiêu đề. Xóa/sửa tiêu đề phải đồng bộ nhiều tập tiền tố.

Trie thường chia sẻ tiền tố tốt hơn ở mức nút/cạnh, nhưng vẫn cần chi phí duyệt kết quả hoặc cache kết quả ở nút.

### 5.4. Chuẩn hóa chuỗi phải nhất quán

Với tiếng Việt, cần nêu rõ các quyết định:

- Chuyển chữ hoa/thường bằng *case folding* hoặc chính sách tương đương.
- Chuẩn hóa Unicode (ví dụ NFC hoặc NFKC) trước khi lập chỉ mục và truy vấn.
- Có hay không bỏ dấu tiếng Việt: `"hoa"` và `"hòa"` có được coi là cùng tiền tố không?
- Xử lý khoảng trắng đầu/cuối, dấu câu, nhiều khoảng trắng, emoji và ký tự kết hợp.
- Phân biệt **tiền tố của toàn tiêu đề** với **tiền tố của từng từ**; `"họp"` có thể không khớp `"Lịch họp nhóm"` theo tiền tố toàn chuỗi.

Một quy tắc chuẩn hóa thay đổi sẽ làm **mọi khóa chỉ mục cũ** có nguy cơ không còn tương thích. Khi đổi chính sách tìm kiếm, cần xây lại chỉ mục và có cơ chế chuyển phiên bản phù hợp.

## 6. Gợi ý tất cả kết quả và `top-k` xếp hạng là hai bài toán khác nhau

Giả sử `10.000` tiêu đề bắt đầu bằng `"meet"` nhưng giao diện chỉ hiện 5 gợi ý.

**Liệt kê theo từ điển:** đi từ cận dưới trong mảng sắp hoặc duyệt trie theo thứ tự cạnh, lấy tối đa 5 kết quả. Thường có thể dừng sớm, với chi phí phụ thuộc việc tìm và đi tới 5 kết quả.

**Gợi ý được xếp hạng:** muốn 5 sự kiện có độ phù hợp cao nhất theo tần suất sử dụng, mức ưu tiên, khoảng thời gian gần nhất hoặc mức phổ biến. Thứ tự từ điển **không bảo đảm đúng top-5** theo những tiêu chí ấy.

Một số lựa chọn:

| Cách lấy gợi ý xếp hạng | Chi phí/đánh đổi |
| --- | --- |
| Duyệt toàn bộ `m` kết quả khớp rồi sắp theo điểm | Thường `O(m log m)`, dễ triển khai |
| Duyệt `m` kết quả và giữ min-heap kích thước `k` cho các điểm cao nhất | `O(m log(k+1))` khi `k ≥ 1`; cần kiểm tra mọi ứng viên nếu không có chặn trên điểm |
| Lưu sẵn top-`k` tại từng nút trie | Trả kết quả nhanh hơn nhưng thêm bộ nhớ, cập nhật tiêu đề/điểm có thể phải sửa nhiều nút |
| Dùng cơ chế ranking chuyên dụng | Có thể tốt với nhiều tín hiệu, nhưng thêm chi phí xây, độ phức tạp và yêu cầu làm mới |

Nếu điểm xếp hạng thay đổi thường xuyên, cache top-`k` tại từng tiền tố có thể trở nên **cũ**. Muốn kết quả chính xác, phải duy trì hoặc làm mới kết quả cache theo quy tắc, và tính chi phí cập nhật đó. Nếu chấp nhận gợi ý gần đúng hoặc trễ, cần ghi rõ hợp đồng.

Một tiêu đề giống hệt nhau có thể gắn nhiều sự kiện. API phải quyết định trả từng **sự kiện theo ID** hay gộp theo **tiêu đề duy nhất** rồi mới chọn top-`k`. Hai ngữ nghĩa cho kết quả và chi phí khác nhau.

## 7. Truy vấn thời gian: bắt đầu trong khoảng khác với giao khoảng

### 7.1. Sự kiện **bắt đầu** trong khoảng

Với cây có thứ tự hoặc mảng đã sắp theo `(startUTC,eventId)`, truy vấn:

```text
eventsStartingIn(a,b):
    it = lowerBound((a, smallestEventId))
    while it tồn tại và it.startUTC < b:
        output it.event
        it = next(it)
```

Chi phí `O(log n+k)` để liệt kê `k` kết quả trong mô hình khóa và bộ duyệt thích hợp. Cách này rất hiệu quả khi API thực sự chỉ hỏi **thời điểm bắt đầu**.

### 7.2. Sự kiện **giao** với khoảng

Với điều kiện:

```text
event.startUTC < b AND event.endUTC > a
```

chỉ mục theo thời điểm bắt đầu **không đủ để nhảy thẳng tới mọi kết quả**. Một sự kiện bắt đầu từ lâu và kéo dài tới hôm nay vẫn phải được xét. Nếu dùng mảng/cây theo `startUTC` đơn lẻ, quét tất cả sự kiện có `startUTC < b` rồi lọc `endUTC > a` có thể mất `O(n)` cho một truy vấn dù kết quả chỉ có ít mục.

Một lựa chọn là **interval tree**: cây lưu các khoảng, được tăng cường thông tin như `maxEnd` của mỗi cây con để có thể cắt tỉa những nhánh chắc chắn không giao khoảng hỏi.

Bất biến quan trọng:

```text
node.maxEnd = max(
    node.event.endUTC,
    maxEnd(node.left),
    maxEnd(node.right)
)
```

Khi chèn, xóa hoặc xoay cây, phải cập nhật `maxEnd` đúng. Với cây cân bằng tăng cường phù hợp, việc tìm **một** khoảng giao nhau có thể có thời gian `O(log n)` trường hợp xấu trong mô hình chuẩn. Tuy nhiên, khi **liệt kê tất cả** khoảng giao nhau, chặn thời gian phụ thuộc **biến thể interval tree và thuật toán duyệt**: một thuật toán quét/cắt tỉa đơn giản vẫn có thể thăm nhiều nút không được xuất, tới `O(n)`. Không nên hứa `O(log n+k)` cho mọi cách cài đặt interval tree chỉ vì có trường `maxEnd`.

Một số cấu trúc truy vấn khoảng chuyên dụng có thể đạt chặn tốt hơn cho bài toán báo cáo giao khoảng, đổi lại cấu trúc phức tạp hơn và chi phí bảo trì riêng.

### 7.3. Sự kiện đang diễn ra ở thời điểm `t`

Điều kiện:

```text
startUTC <= t AND t < endUTC
```

là một dạng truy vấn chứa điểm. Nếu có nhiều sự kiện dài và nhiều truy vấn ngẫu nhiên trên trục thời gian, interval tree hoặc kỹ thuật chỉ mục khoảng thường hữu ích. Nếu chỉ xử lý **một lần theo dòng thời gian tăng dần**, ta có thể dùng thuật toán quét sự kiện (*sweep line*): sắp các mốc bắt đầu/kết thúc rồi duy trì tập sự kiện đang hoạt động.

Với khoảng nửa mở, tại cùng thời điểm cần xử lý **kết thúc trước bắt đầu** nếu muốn đánh giá tập đang hoạt động ngay sau mốc đó, để hai sự kiện `[09:00,10:00)` và `[10:00,11:00)` không bị coi là đồng thời hoạt động.

### 7.4. Đếm sự kiện theo bucket thời gian

Một truy vấn khác là “có bao nhiêu sự kiện **bắt đầu** trong ngày/tháng?” hoặc “tổng số lượt đăng ký trong giờ `[a,b)`?” Nếu dữ liệu được tổng hợp theo các ô thời gian liên tiếp:

- **Mảng đếm**: cộng vào bucket khi sự kiện được thêm, trừ khi xóa; truy cập bucket `O(1)`.
- **Prefix sum**: xây `O(B)` trên `B` bucket tĩnh, tổng đoạn `O(1)`; sửa một bucket có thể khiến cập nhật tổng tiền tố `O(B)`.
- **Fenwick tree**: cập nhật bucket và hỏi tổng đoạn `O(log B)`.
- **Segment tree**: cập nhật điểm/tổng đoạn `O(log B)`; hỗ trợ nhiều phép tổng hợp có tính kết hợp tùy thiết kế.

**Đếm sự kiện bắt đầu** không đồng nghĩa **đếm sự kiện đang hoạt động** trong một ngày. Với sự kiện kéo dài qua nhiều bucket, phải định nghĩa phép đo: đếm một lần, đếm mỗi bucket mà sự kiện giao, hay cộng tổng thời lượng? Mỗi kiểu cần thuật toán cập nhật/tổng hợp khác nhau.

## 8. Kiến trúc ghép: một nguồn dữ liệu và các chỉ mục có nhiệm vụ rõ

Giả sử yêu cầu của ứng dụng là:

- Có khoảng `n = 200.000` sự kiện, thêm và dời lịch thường xuyên.
- Tìm nhanh theo `eventId`.
- Xem lịch theo thời điểm bắt đầu.
- Tìm tiền tố tiêu đề.
- Xử lý nhắc việc đến hạn.
- Tìm cuộc họp trùng khoảng thời gian là chức năng tùy chọn.

Thiết kế ứng viên:

```text
                         byId: HashMap<EventId, Event>
                                    │
                  ┌─────────────────┼─────────────────┐
                  │                 │                 │
       byStart: BalancedBST   byTitle: Trie      reminders: MinHeap
       (startUTC, eventId)    title → EventIds   (remindAt, token, id)
                  │                                   │
                  │                           activeReminderById
                  │                              / index map
                  └───────────────┬───────────────────┘
                                  │
                    optional byInterval: IntervalTree
                    (startUTC, endUTC, eventId)
```

Trong thiết kế này, **`byId` là nguồn bản ghi có thẩm quyền**. Các chỉ mục còn lại lưu khóa và ID để tránh sao chép toàn bộ payload.

| Chỉ mục | Bất biến | Phép toán chính |
| --- | --- | --- |
| `byId` | Mỗi ID đang hoạt động trỏ đúng một bản ghi | `getById` |
| `byStart` | Có đúng một cặp `(event.startUTC,event.id)` cho mỗi sự kiện thuộc lịch | Truy vấn lịch theo mốc bắt đầu |
| `byTitle` | Mỗi tiêu đề chuẩn hóa có đúng tập ID tương ứng; không chứa ID đã xóa | Gợi ý theo tiền tố |
| `reminders` và bảng token/vị trí | Mọi nhắc việc còn hoạt động có thể được lấy đúng một lần theo quy tắc; bản ghi stale không được phát | Nhắc việc đến hạn |
| `byInterval` (nếu có) | Mỗi khoảng đang hoạt động được lưu và metadata cây con cập nhật đúng | Truy vấn giao khoảng |

**Không bắt buộc tạo mọi chỉ mục.** Nếu chức năng tìm giao khoảng chỉ được dùng mỗi năm một lần trên tập sự kiện nhỏ, quét và lọc có thể kinh tế hơn một interval tree phải duy trì liên tục. Nếu ít người dùng gợi ý tiêu đề, mảng sắp theo tên có thể tốt hơn trie nhiều nút.

### 8.1. Giao diện giúp giữ đúng nghĩa

Cần giữ riêng các API:

```text
getById(id)
listStartsBetween(aUTC, bUTC)
listOverlaps(aUTC, bUTC)
suggestTitles(prefix, limit, rankingMode)
peekNextReminder()
popDueReminders(nowUTC)
reschedule(id, newStartUTC, newEndUTC)
cancel(id)
```

Đặc tả còn phải nói rõ kết quả có được sắp theo mốc, thời gian được diễn giải theo timezone nào, cách phá hòa khi có hai sự kiện cùng lúc, và phiên bản dữ liệu mà các lần đọc phản ánh.

## 9. Bất biến và cập nhật nguyên tử khi dời lịch, đổi tên, hủy sự kiện

Đây là nơi một thiết kế nhiều chỉ mục dễ phát sinh lỗi nhất. Một lần **reschedule** có thể đụng tới cây thời gian, heap nhắc việc và interval tree; một lần **rename** có thể đụng tới trie; một lần **cancel** phải dọn mọi đường dẫn tới sự kiện.

### 9.1. Thêm sự kiện

```text
create(event):
    validate(event)
    require event.id chưa tồn tại

    atomic_change:
        byId[event.id] = event
        byStart.insert((event.startUTC, event.id))
        byTitle.insert(normalize(event.title), event.id)
        if event có reminder:
            scheduleReminder(event.id, event.startUTC - lead)
        if byInterval tồn tại:
            byInterval.insert(event.startUTC, event.endUTC, event.id)
```

Nếu việc thêm vào trie hoặc heap thất bại, không thể báo thành công trong khi chỉ một phần chỉ mục được tạo. Với cấu trúc RAM tự quản lý, cần lock + rollback hoặc copy-on-write; với DB, có thể dùng transaction nếu các chỉ mục ở trong cùng phạm vi giao dịch.

### 9.2. Dời lịch

Giả sử sự kiện E17 từ `[09:00,10:00)` chuyển sang `[14:00,15:00)`. Thao tác cần biết **cả khóa cũ và khóa mới**:

```text
reschedule(id, newStart, newEnd):
    old = byId.get(id)
    new = old.copy(start=newStart, end=newEnd)

    atomic_change:
        byStart.remove((old.startUTC, id))
        byStart.insert((new.startUTC, id))

        if byInterval tồn tại:
            byInterval.remove((old.startUTC, old.endUTC, id))
            byInterval.insert((new.startUTC, new.endUTC, id))

        invalidateOldReminder(id)
        if new có reminder:
            scheduleReminder(id, new.startUTC - new.reminderLead)

        byId[id] = new
```

Không thay `old.startUTC` trực tiếp **trước** khi lấy khóa cũ: lúc đó có thể không còn biết phải xóa cặp nào khỏi cây. Nếu `reminderLead` không đổi nhưng thời điểm bắt đầu đổi, thời điểm nhắc vẫn phải tính lại.

Nếu nhắc việc cũ đã được gửi, ứng dụng cần định nghĩa việc dời lịch có tạo một nhắc việc mới hay không; **cấu trúc heap không tự quyết định chính sách nghiệp vụ**.

### 9.3. Đổi tên sự kiện

Nếu tiêu đề đổi từ `"Họp nhóm"` thành `"Báo cáo tuần"`:

```text
rename(id, newTitle):
    old = byId[id]
    oldKey = normalize(old.title)
    newKey = normalize(newTitle)

    atomic_change:
        if oldKey != newKey:
            byTitle.remove(oldKey, id)
            byTitle.insert(newKey, id)
        byId[id] = old.copy(title=newTitle)
```

Không nhất thiết thay chỉ mục thời gian hoặc nhắc việc khi chỉ sửa tiêu đề. Nhưng nếu top-`k` gợi ý phụ thuộc vào điểm phổ biến/tần suất, phải xác định các cache ranking nào cần vô hiệu hóa.

### 9.4. Hủy sự kiện

Xóa mọi chỉ mục cho sự kiện đó:

```text
cancel(id):
    old = byId.get(id)
    if old không tồn tại:
        return NOT_FOUND

    atomic_change:
        byStart.remove((old.startUTC, id))
        byTitle.remove(normalize(old.title), id)
        invalidateOldReminder(id)
        if byInterval tồn tại:
            byInterval.remove(old.startUTC, old.endUTC, id)
        byId.remove(id)
```

Với heap theo cơ chế lazy, **không nhất thiết xóa vật lý mục cũ khỏi heap ngay**; nhưng phải khiến token cũ mất hiệu lực để `popDue` không phát nhắc việc của sự kiện đã hủy.

### 9.5. Đồng thời và phiên bản đọc

Một người đang xem sự kiện E17 trong danh sách theo ngày, trong khi người khác dời lịch. Nếu truy vấn lấy ID từ cây cũ nhưng bản ghi từ map mới, cùng lời gọi có thể thấy **hai phiên bản khác nhau**.

Các lựa chọn:

- Khóa chung cho cập nhật và lượt đọc nhiều chỉ mục.
- Snapshot bất biến/MVCC cho truy vấn nhiều bước.
- Dùng transaction có mức cô lập phù hợp.
- Chấp nhận kết quả cập nhật dần, nhưng công bố rõ hợp đồng nếu nghiệp vụ cho phép.

**Khóa không thay thế rollback:** nếu cập nhật được một nửa rồi có exception, mở khóa không tự sửa chỉ mục cũ. Ngoài việc ngăn đọc giữa chừng còn phải bảo đảm **commit toàn bộ hoặc phục hồi**.

## 10. Ví dụ Python: bản tối giản, ưu tiên tính đúng đắn và dễ quan sát

Phiên bản minh họa dưới đây dùng:

- `dict` để tra ID.
- **Hai mảng sắp** để truy vấn thời điểm bắt đầu và tiền tố tiêu đề.
- `heapq` với **token phiên bản** để xử lý nhắc việc, bỏ qua nhắc việc cũ sau khi dời lịch/hủy.

Nó không triển khai cây cân bằng hoặc trie vì muốn giúp người học thấy rõ **sự khác biệt giữa các kiểu chỉ mục** bằng mã Python chuẩn, không cần thư viện ngoài. Mọi lần ghi tạo **bản sao của các chỉ mục rồi công bố một trạng thái mới dưới khóa**; các bản đọc dùng cùng một snapshot. Cách làm này thiên về rõ ràng và nhất quán, **không tối ưu chi phí ghi**: một lần thêm/sửa/xóa có thể cần `O(n+m)` sao chép, với `m` là số mục nhắc (bao gồm mục stale).

Dùng **số nguyên biểu diễn phút UTC tuyệt đối** cho `start`, `end`, `now` và `reminderLead`. Trong sản phẩm thật, nên dùng kiểu Instant/Duration phù hợp và xác định chính sách timezone/lịch lặp riêng.

```python
from bisect import bisect_left, insort
from dataclasses import dataclass
from threading import RLock
from typing import Optional
import heapq
import unicodedata


def normalize(text):
    return unicodedata.normalize("NFKC", text).casefold()


@dataclass(frozen=True)
class Event:
    id: str
    title: str
    start: int
    end: int
    reminder_lead: Optional[int] = None


@dataclass(frozen=True)
class State:
    by_id: dict
    by_start: tuple        # sorted (start, id)
    by_title: tuple        # sorted (normalized_title, id)
    heap: tuple            # binary min-heap (due, token, id)
    active_reminders: dict  # id -> (due, token)
    next_token: int


class Agenda:
    def __init__(self):
        self._lock = RLock()
        self._state = State({}, (), (), (), {}, 0)

    def _snapshot(self):
        with self._lock:
            return self._state

    @staticmethod
    def _check_event(e):
        if not isinstance(e.id, str) or not e.id:
            raise ValueError("event id must be nonempty")
        if not isinstance(e.title, str):
            raise ValueError("title must be a string")
        if type(e.start) is not int or type(e.end) is not int:
            raise ValueError("start/end must be UTC-minute integers")
        if e.start >= e.end:
            raise ValueError("event interval must be nonempty")
        if e.reminder_lead is not None:
            if type(e.reminder_lead) is not int or e.reminder_lead < 0:
                raise ValueError("reminder lead must be nonnegative")

    @staticmethod
    def _erase(sorted_items, key):
        i = bisect_left(sorted_items, key)
        if i == len(sorted_items) or sorted_items[i] != key:
            raise AssertionError("secondary index is inconsistent")
        sorted_items.pop(i)

    def put(self, event):
        self._check_event(event)

        with self._lock:
            old_state = self._state
            old = old_state.by_id.get(event.id)
            rows = dict(old_state.by_id)
            starts = list(old_state.by_start)
            titles = list(old_state.by_title)
            heap = list(old_state.heap)
            active = dict(old_state.active_reminders)
            token = old_state.next_token

            if old is not None:
                self._erase(starts, (old.start, old.id))
                self._erase(titles, (normalize(old.title), old.id))

            rows[event.id] = event
            insort(starts, (event.start, event.id))
            insort(titles, (normalize(event.title), event.id))

            # Sửa title thuần túy không tạo lại reminder đã phát.
            timing_changed = (
                old is None
                or old.start != event.start
                or old.reminder_lead != event.reminder_lead
            )
            if timing_changed:
                active.pop(event.id, None)  # token cũ trở thành stale
                if event.reminder_lead is not None:
                    token += 1
                    due = event.start - event.reminder_lead
                    active[event.id] = (due, token)
                    heapq.heappush(heap, (due, token, event.id))

            # Công bố cùng một phiên bản của mọi chỉ mục.
            self._state = State(
                rows, tuple(starts), tuple(titles),
                tuple(heap), active, token
            )

    def delete(self, event_id):
        with self._lock:
            s = self._state
            old = s.by_id.get(event_id)
            if old is None:
                return False

            rows = dict(s.by_id)
            starts = list(s.by_start)
            titles = list(s.by_title)
            active = dict(s.active_reminders)

            del rows[event_id]
            self._erase(starts, (old.start, event_id))
            self._erase(titles, (normalize(old.title), event_id))
            active.pop(event_id, None)  # mục heap cũ sẽ bị bỏ qua

            self._state = State(
                rows, tuple(starts), tuple(titles),
                s.heap, active, s.next_token
            )
            return True

    def get(self, event_id):
        return self._snapshot().by_id.get(event_id)

    def starts_between(self, lo, hi):
        if lo >= hi:
            return []
        s = self._snapshot()
        i = bisect_left(s.by_start, (lo, ""))
        result = []
        while i < len(s.by_start):
            start, event_id = s.by_start[i]
            if start >= hi:
                break
            result.append(s.by_id[event_id])
            i += 1
        return result

    def suggest(self, prefix, limit=5):
        if limit <= 0:
            return []
        s = self._snapshot()
        p = normalize(prefix)
        i = bisect_left(s.by_title, (p, ""))
        result = []
        while i < len(s.by_title) and len(result) < limit:
            title, event_id = s.by_title[i]
            if not title.startswith(p):
                break
            result.append(s.by_id[event_id])
            i += 1
        return result

    def pop_due(self, now):
        # Cố ý tạo bản sao để các snapshot đọc cũ không bị sửa.
        with self._lock:
            s = self._state
            heap = list(s.heap)
            active = dict(s.active_reminders)
            result = []

            while heap and heap[0][0] <= now:
                due, token, event_id = heapq.heappop(heap)
                if active.get(event_id) != (due, token):
                    continue  # đã dời lịch, hủy hoặc nhắc việc cũ
                del active[event_id]
                result.append(s.by_id[event_id])

            self._state = State(
                s.by_id, s.by_start, s.by_title,
                tuple(heap), active, s.next_token
            )
            return result

    def compact_reminders(self):
        # Tái xây heap từ đúng các nhắc việc còn hoạt động.
        with self._lock:
            s = self._state
            heap = [
                (due, token, event_id)
                for event_id, (due, token) in s.active_reminders.items()
            ]
            heapq.heapify(heap)
            self._state = State(
                s.by_id, s.by_start, s.by_title,
                tuple(heap), s.active_reminders, s.next_token
            )

    def check_invariants(self):
        s = self._snapshot()
        expected_starts = sorted(
            (e.start, e.id) for e in s.by_id.values()
        )
        expected_titles = sorted(
            (normalize(e.title), e.id) for e in s.by_id.values()
        )
        assert list(s.by_start) == expected_starts
        assert list(s.by_title) == expected_titles

        heap_entries = set(s.heap)
        for event_id, (due, token) in s.active_reminders.items():
            e = s.by_id[event_id]
            assert e.reminder_lead is not None
            assert due == e.start - e.reminder_lead
            assert (due, token, event_id) in heap_entries

        for i in range(1, len(s.heap)):
            assert s.heap[(i - 1) // 2] <= s.heap[i]
        return True
```

### Kiểm tra hoạt động trên một tập dữ liệu nhỏ

```python
agenda = Agenda()
agenda.put(Event("A", "Họp nhóm", 100, 160, reminder_lead=10))
agenda.put(Event("B", "Họp khách", 140, 210, reminder_lead=20))
agenda.put(Event("C", "Ăn trưa", 180, 220))

assert agenda.check_invariants()
assert [e.id for e in agenda.starts_between(90, 150)] == ["A", "B"]
assert [e.id for e in agenda.suggest("hỌp")] == ["B", "A"]
# Hai tiêu đề được sắp theo chuỗi chuẩn hóa, không theo start.

agenda.put(Event("A", "Họp nhóm", 240, 300, reminder_lead=10))
assert agenda.check_invariants()
assert [e.id for e in agenda.starts_between(90, 150)] == ["B"]

# A có nhắc việc cũ ở phút 90 nhưng token đã stale.
# B nhắc tại phút 120; A mới nhắc tại phút 230.
assert [e.id for e in agenda.pop_due(125)] == ["B"]
assert [e.id for e in agenda.pop_due(235)] == ["A"]
assert agenda.pop_due(300) == []

agenda.delete("B")
assert agenda.get("B") is None
agenda.compact_reminders()
assert agenda.check_invariants()
```

**Lưu ý về thứ tự gợi ý:** mã sử dụng thứ tự từ điển của tiêu đề sau chuẩn hóa, **không** phải ưu tiên theo thời gian, tần suất hay độ liên quan. Nếu API cần gợi ý theo điểm, phải có thuật toán ranking và dữ liệu điểm tương ứng.

**Lưu ý về ngữ nghĩa nhắc việc:** `pop_due(now)` trả các sự kiện có nhắc việc còn hiệu lực đến hạn **tối đa một lần trong bộ nhớ của tiến trình** theo trạng thái đó. Nó không bảo đảm gửi thông báo ra mạng đúng một lần, khôi phục sau crash hoặc xử lý nhiều thiết bị cùng nhận lịch. Cần lưu trạng thái bền vững, khóa/transaction và chính sách idempotency nếu hệ thống thật yêu cầu.

### Độ phức tạp của bản minh họa

Bản mã ưu tiên tính nhất quán và đơn giản nên có các chi phí:

| Phép toán | Chi phí mô hình |
| --- | --- |
| `get(id)` | Kỳ vọng `O(1)` tra dict |
| `starts_between(a,b)` trả `k` mục | `O(log n+k)` lần so sánh/duyệt trên mảng sắp |
| `suggest(prefix,k)` | Tìm cận bằng binary search, rồi duyệt tới `k` mục khớp; tính thêm chi phí so sánh chuỗi |
| `put(event)` | **`O(n+m)`** hoặc nhiều hơn do copy danh sách/mảng/heap; thao tác mảng sắp có thể dịch `O(n)` |
| `delete(id)` | **`O(n)`** vì copy/chỉnh hai mảng sắp |
| `pop_due(now)` lấy `d` mục heap (kể cả stale) | Copy heap `O(m)`, cộng `O(d log m)`; có thể trả ít hơn `d` mục hợp lệ |
| `compact_reminders()` | `O(r)` với `r` nhắc việc đang hoạt động, theo heapify |
| Bộ nhớ | `O(n+m)` với `m` mục heap, kể cả stale; lúc copy có thêm bộ nhớ tạm cùng bậc |

Các chặn trên giả định các khóa/giá trị cơ bản có chi phí xử lý phù hợp. Một lần sửa title hoặc time bằng mảng sắp không đạt `O(log n)`, vì **tìm bằng nhị phân nhanh không loại bỏ chi phí dịch chuyển phần tử**. Với nhiều cập nhật, thay `by_start` bằng cây cân bằng và `by_title` bằng trie có thể cải thiện chi phí cập nhật, nhưng phải có cơ chế giao dịch/đồng bộ giữ mọi chỉ mục nhất quán.

Phương thức `compact_reminders` nên được gọi theo chính sách quan sát kích thước heap so với số reminder còn hoạt động. Nếu không tái xây, lazy invalidation có thể giữ các bản ghi stale trong thời gian dài, đặc biệt khi người dùng liên tục dời một sự kiện ra xa tương lai.

## 11. So sánh các thiết kế theo tải công việc

| Nhu cầu | Dữ liệu tĩnh/ít ghi | Dữ liệu động/nhiều ghi | Đánh đổi |
| --- | --- | --- | --- |
| Tra theo ID | Hash map | Hash map | Tra kỳ vọng `O(1)`, bộ nhớ thêm `O(n)` |
| Liệt kê sự kiện **bắt đầu** trong khoảng | Mảng sắp `(start,id)` | Cây tự cân bằng theo `(start,id)` | Mảng đọc tuần tự tốt; cây chèn/xóa `O(log n)` |
| Truy vấn **giao khoảng** | Quét nếu ít câu hỏi; cấu trúc chỉ mục khoảng nếu nhiều | Interval tree có cập nhật hoặc giải pháp truy vấn khoảng chuyên dụng | Chi phí và chặn duyệt kết quả tùy biến thể |
| Gợi ý tiền tố | Mảng title chuẩn hóa đã sắp | Trie/radix tree, hoặc cây từ điển | Trie thuận truy vấn tiền tố nhưng có overhead nút |
| Gợi ý top-`k` theo điểm | Lọc + heap `k` phần tử hoặc cache sẵn | Cấu trúc ranking cần cập nhật điểm | Chi phí duyệt ứng viên vs chi phí cache điểm |
| Lấy nhắc việc sớm nhất | Min-heap | Indexed min-heap hoặc heap + token lazy | Hủy/dời nhắc việc và bộ nhớ stale quyết định |
| Đếm số sự kiện bắt đầu theo bucket | Mảng đếm + prefix sum | Fenwick tree/segment tree | Cần định nghĩa rõ bucket và loại đếm |
| Sự kiện lặp vô hạn | Quy tắc lặp + sinh trong chân trời hữu hạn | Quy tắc lặp/ngoại lệ + cập nhật các occurrence đã sinh | Không lập chỉ mục vô hạn lần diễn ra |

### 11.1. Phương án tối giản khi tải nhỏ

Nếu chỉ có vài trăm sự kiện, số lần cập nhật rất thấp và người dùng không kỳ vọng hàng nghìn truy vấn mỗi giây, **một mảng bản ghi và thao tác lọc/sắp theo nhu cầu** có thể đơn giản, dễ bảo trì và đủ nhanh. Thêm chỉ mục làm tăng số bất biến cần giữ, nguy cơ bug và công sức kiểm thử.

### 11.2. Phương án đọc nhiều, ít ghi

Nếu nạp một bộ lịch công khai theo tuần/tháng và hiếm thay đổi, dùng **mảng sắp theo thời gian** và **mảng sắp theo tiêu đề chuẩn hóa** có thể đạt truy vấn tốt mà không cần nhiều nút trie/cây. Có thể xây lại các mảng theo lô khi dữ liệu thay đổi.

### 11.3. Phương án đọc/ghi thời gian thực

Nếu liên tục thêm, dời lịch và hủy, cùng lúc có người truy vấn ngày và gõ tiền tố, hãy xét **hash map ID + cây thời gian + trie + indexed heap**, thêm interval tree nếu truy vấn giao khoảng thật sự phổ biến. Phải định nghĩa giao dịch cập nhật tất cả chỉ mục, trạng thái snapshot cho lượt đọc, giới hạn bộ nhớ và cách phục hồi khi sự cố.

## 12. Các sai lầm thường gặp

**1. Dùng heap để liệt kê lịch theo thứ tự bắt đầu.** Heap chỉ bảo đảm đỉnh nhỏ nhất, **không** sắp toàn bộ mảng. Nếu cần liệt kê liên tiếp theo thời điểm, dùng cây có thứ tự hoặc mảng sắp.

**2. Dùng hash map tiêu đề cho truy vấn tiền tố.** Hash map tra toàn khóa, không hỗ trợ tự động liệt kê mọi chuỗi bắt đầu bằng `p`. Cần trie, mảng/cây từ điển hoặc chỉ mục tiền tố riêng.

**3. Nhầm “bắt đầu trong khoảng” với “giao khoảng”.** Sự kiện kéo dài có thể bắt đầu từ trước `a` mà vẫn giao `[a,b)`. Chỉ tìm cận theo start sẽ bỏ sót nó.

**4. Bỏ quy tắc ở hai biên thời gian.** Với khoảng nửa mở, sự kiện kết thúc lúc 10:00 và sự kiện bắt đầu lúc 10:00 không giao nhau. Dùng sai dấu `≤`/`<` có thể tạo lỗi “xung đột lịch” giả.

**5. Lưu giờ địa phương như một số có thể so sánh toàn cục.** Những timestamp thuộc vùng giờ khác nhau hoặc lịch qua ngày đổi giờ phải được quy về Instant đúng và vẫn giữ timezone để hiển thị/lặp.

**6. Sinh vô hạn occurrence từ sự kiện lặp.** Phải mở rộng trong chân trời hữu hạn hoặc có thuật toán sinh theo khoảng hỏi, quản lý ngoại lệ và ID của occurrence.

**7. Sửa lịch nhưng quên sửa nhắc việc.** Heap có thể giữ thời điểm nhắc cũ. Nếu dùng lazy, phải vô hiệu token cũ; nếu dùng indexed heap, phải cập nhật vị trí/khóa đúng.

**8. Chỉnh heap mà quên cập nhật bảng vị trí.** Với indexed heap, mỗi swap thay chỉ số của cả hai phần tử; bảng `id → index` phải được cập nhật tương ứng.

**9. Chuẩn hóa tiêu đề khi ghi khác khi hỏi.** Case-fold, Unicode, dấu tiếng Việt và khoảng trắng cần chính sách nhất quán. Đổi chính sách phải xem xét xây lại chỉ mục.

**10. Hứa truy vấn tiền tố chỉ mất `O(|p|)` dù phải trả nhiều kết quả.** Tìm nút trong trie có thể tốn theo độ dài tiền tố, nhưng liệt kê `k` kết quả có chi phí ít nhất `Ω(k)`.

**11. Dùng danh sách gợi ý theo thứ tự từ điển khi API cần top-`k` theo điểm.** Phải xác định hàm ranking và duy trì cache/heap chọn kết quả phù hợp, không đánh đồng hai loại thứ tự.

**12. Chỉ bảo vệ thao tác ghi mà không giữ snapshot cho truy vấn nhiều chỉ mục.** Một lời đọc có thể lấy ID từ cây phiên bản cũ và bản ghi từ map phiên bản mới, tạo kết quả không tương ứng với cùng thời điểm.

**13. Gọi `popDue` là “gửi thông báo đúng một lần”.** Lấy mục khỏi heap trong RAM khác với xác nhận gửi thông báo qua mạng; crash và retry có thể tạo bản gửi trùng hoặc bị mất nếu không có lưu trạng thái bền vững.

## 13. Bài tập áp dụng

### Bài 1 — Chọn cấu trúc hiển thị lịch

Ứng dụng có `n=100.000` sự kiện đã sắp theo thời điểm bắt đầu; dữ liệu chỉ đọc và một ngày có hàng nghìn truy vấn liệt kê sự kiện bắt đầu trong khoảng giờ `[a,b)`.

**Hỏi:** có cần chuyển sang cây cân bằng không?

*Gợi ý đáp án:* chưa chắc. Mảng đã sắp có thể tìm cận trong `O(log n)`, duyệt `k` kết quả trong `O(k)`, sử dụng bộ nhớ liên tiếp. Cây giúp cập nhật có thứ tự nhưng không đem lại lợi ích rõ nếu dữ liệu tĩnh.

### Bài 2 — Trùng thời điểm bắt đầu

Hai sự kiện A và B đều bắt đầu lúc 09:00. Nếu dùng cây set chỉ theo `startUTC`, có nguy cơ gì?

*Đáp án:* nếu set không cho khóa trùng, một sự kiện có thể bị bỏ mất. Dùng khóa ghép `(startUTC,eventId)` hoặc cấu trúc hỗ trợ nhiều mục tại cùng khóa.

### Bài 3 — Giao khoảng

Sự kiện A có khoảng `[08:30,11:00)`; câu hỏi tìm sự kiện trong `[09:00,09:30)`. Nếu chỉ chọn các sự kiện có thời điểm **bắt đầu** nằm trong khoảng hỏi, có tìm được A không?

*Đáp án:* không, nhưng A **giao khoảng** vì `08:30 < 09:30` và `09:00 < 11:00`. Muốn tìm đúng phải dùng điều kiện giao và chỉ mục/thuật toán phù hợp.

### Bài 4 — Gợi ý tiền tố có xếp hạng

Có 50.000 tiêu đề bắt đầu bằng `"họp"`, nhưng API cần 5 sự kiện được sử dụng nhiều nhất. Trie chỉ lưu các cạnh ký tự và ID có trả ngay top-5 trong `O(|p|+5)` không?

*Đáp án:* không có bảo đảm đó. Cần duyệt các ứng viên và chọn theo điểm hoặc duy trì kết quả xếp hạng sẵn với chi phí cập nhật/độ mới được định nghĩa rõ.

### Bài 5 — Dời lịch và lazy heap

Một sự kiện có nhắc việc ở phút 90, sau đó được dời để nhắc ở phút 230. Heap vẫn giữ bản ghi cũ ở phút 90.

**Hỏi:** làm sao tránh phát nhắc việc ở phút 90 mà không phải tìm/xóa bản ghi cũ trong heap?

*Đáp án:* mỗi lần đặt nhắc tạo token mới, `activeReminder[eventId]` giữ token hiện hành. Khi pop mục cũ, so token và bỏ qua nếu không khớp. Theo dõi/tái xây heap để kiểm soát bộ nhớ stale.

### Bài 6 — Tổng hợp bucket có cập nhật

Ứng dụng có 365 bucket ngày và thường xuyên cập nhật số sự kiện bắt đầu mỗi ngày, đồng thời trả nhiều câu hỏi tổng số bắt đầu trong một khoảng ngày.

**Hỏi:** prefix sum hay Fenwick tree?

*Gợi ý:* nếu hầu như không ghi, prefix sum `O(1)` mỗi truy vấn sau khi xây có lợi. Nếu cập nhật điểm thường xuyên, Fenwick tree cho cập nhật và truy vấn `O(log 365)`, tránh làm mới toàn bộ tổng tiền tố mỗi lần sửa.

### Bài 7 — Lịch lặp theo giờ địa phương

Một cuộc họp diễn ra 09:00 mỗi thứ Hai trong một múi giờ có giờ mùa hè. Có thể tạo occurrence tuần sau bằng cách luôn cộng `7×24` giờ vào UTC Instant của tuần này không?

*Đáp án:* không bảo đảm giữ nguyên 09:00 giờ địa phương khi thay đổi offset. Phải tính lần diễn ra theo quy tắc lịch địa phương và chuyển sang Instant theo timezone của ngày tương ứng.

### Bài 8 — Đổi tên và nhất quán chỉ mục

Sự kiện E có tiêu đề `"Workshop"` và chỉ mục trie đang gắn E dưới tiền tố `"work"`. Người dùng đổi thành `"Họp nhóm"` nhưng chương trình chỉ cập nhật `byId`.

*Đáp án:* chỉ mục tiền tố sai: truy vấn `"work"` vẫn thấy E, còn `"họp"` có thể không thấy. Cần xóa liên kết ID khỏi khóa cũ, thêm vào khóa mới và công bố thay đổi nhất quán với dữ liệu chính.

## 14. Checklist lựa chọn cuối cùng

Trước khi chốt kiến trúc lịch sự kiện, hãy kiểm tra:

- **Phép toán:** hỏi theo ID, bắt đầu trong khoảng, giao khoảng, đang diễn ra tại điểm, gợi ý tiền tố, top-`k`, nhắc việc hay tổng hợp bucket?
- **Ngữ nghĩa thời gian:** Instant UTC, timezone hiển thị, khoảng nửa mở, ngày địa phương, lịch lặp và ngoại lệ có được định nghĩa rõ không?
- **Khóa và thứ tự:** có `eventId` duy nhất, khóa ghép khi trùng thời điểm, thứ tự kết quả và quy tắc phá hòa khi nhắc cùng hạn không?
- **Dữ liệu tĩnh/động:** thêm/xóa/dời lịch nhiều hay ít, đã có mảng sắp hay cần cây/trie cập nhật?
- **Gợi ý:** tìm tiền tố toàn tiêu đề hay từng từ, chuẩn hóa Unicode thế nào, liệt kê từ điển hay xếp hạng theo điểm?
- **Nhắc việc:** heap thuần, indexed heap hay lazy token; hủy/dời hạn ra sao; có chính sách dọn stale và chống gửi trùng không?
- **Bất biến nhiều chỉ mục:** mọi ID hiện hành có đúng khóa thời gian/tiêu đề/nhắc tương ứng; thao tác thất bại có rollback/snapshot không?
- **Đồng thời và bền vững:** người đọc có thấy cùng một phiên bản không, trạng thái nhắc đã gửi có tồn tại qua crash không?
- **Chi phí:** thời gian dựng/cập nhật, chi phí xuất `k` kết quả, bộ nhớ thường trực/đỉnh và độ phức tạp do lịch lặp.
- **Kiểm thử:** có kiểm tra sự kiện trùng giờ, khoảng chạm biên, timezone, token stale, đổi tiêu đề, cancel/reschedule và truy vấn giao khoảng không?

## Kết luận

Thiết kế lịch sự kiện hiệu quả bắt đầu bằng cách **tách các phép toán khác nhau**: bảng băm theo ID giải quyết tra cứu chính xác; mảng sắp hoặc cây cân bằng phục vụ sự kiện bắt đầu theo thời gian; trie hoặc chỉ mục chuỗi đã sắp phục vụ tiền tố; min-heap xử lý nhắc việc sớm nhất; interval tree hoặc thuật toán quét phù hợp hỗ trợ tìm giao khoảng; prefix sum, Fenwick tree hay segment tree xử lý tổng hợp theo bucket.

Mỗi lựa chọn có bất biến và đánh đổi riêng về thời gian/bộ nhớ. Những lợi ích tra cứu chỉ bền vững khi cập nhật **mọi chỉ mục liên quan một cách nhất quán**, đặc biệt lúc dời lịch, đổi tiêu đề, hủy sự kiện hoặc xử lý lịch lặp. Hãy so các phương án theo tải đọc/ghi thực tế, đo cả chi phí duy trì và chọn bảo đảm phù hợp với tính đúng đắn của thời gian, thứ tự và thông báo.
