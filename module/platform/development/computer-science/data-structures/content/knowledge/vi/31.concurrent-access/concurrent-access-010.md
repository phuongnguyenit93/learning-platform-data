# Vấn đề ABA và thu hồi nút khi vẫn còn người đọc

Trong cấu trúc dữ liệu dùng chung giữa nhiều luồng, việc một nút **không còn nằm trong danh sách liên kết, stack hoặc queue** chưa đồng nghĩa với việc có thể giải phóng vùng nhớ của nó. Một luồng khác có thể đã đọc địa chỉ nút, tạm dừng ngay trước khi truy cập trường `next`, rồi tiếp tục chạy sau khi nút bị loại khỏi cấu trúc.

Tình huống này đặt ra hai bài toán liên quan nhưng khác nhau:

- **ABA:** trạng thái mà luồng quan sát tưởng như không đổi vì giá trị đã đi từ `A` sang một giá trị khác rồi trở về `A`. Một lệnh *compare-and-set* (CAS) chỉ so sánh giá trị hiện tại có thể bỏ sót các thay đổi ở giữa.
- **Thu hồi nút an toàn (*safe memory reclamation*):** quyết định **khi nào** vùng nhớ của một nút đã bị gỡ khỏi cấu trúc có thể giải phóng hoặc tái sử dụng mà không còn người đọc nào truy cập nó.

Đây là những vấn đề nền tảng của chương **Truy cập đồng thời** trong môn cấu trúc dữ liệu. Chúng xuất hiện đặc biệt rõ ở danh sách liên kết, stack Treiber, queue dùng CAS và những cấu trúc dựa trên con trỏ. Muốn chọn cấu trúc đúng cho bài toán thực tế, cần xét đồng thời bất biến của cấu trúc, chi phí thao tác, tiến triển của các luồng và vòng đời bộ nhớ.

## 1. Ba mốc thời gian khác nhau trong vòng đời của một nút

Xét một stack liên kết có con trỏ nguyên tử `head`:

```text
head ──> A ──> B ──> C ──> null
```

Giả sử luồng T1 vừa lấy được địa chỉ nút `A`, trong khi luồng T2 muốn lấy `A` ra khỏi stack. Cần phân biệt:

1. **Còn được liên kết (*linked*):** nút vẫn thuộc cấu trúc và có thể tìm thấy từ `head`.
2. **Đã gỡ nhưng chưa thu hồi (*retired*):** nút không còn thuộc cấu trúc, nhưng có thể có luồng khác còn giữ tham chiếu tới nó. Nút phải được giữ sống trong giai đoạn này.
3. **Đã thu hồi (*reclaimed*):** hệ thống xác nhận không còn luồng nào có thể truy cập nút qua tham chiếu cũ và cho phép giải phóng/tái sử dụng bộ nhớ.

Sơ đồ vòng đời:

```text
Đang ở cấu trúc ──gỡ liên kết──> Retired ──an toàn với mọi reader──> Reclaimed
                   (unlink)                 (grace period/quét bảo vệ)
```

**Gỡ liên kết là thay đổi cấu trúc logic; thu hồi là thay đổi quyền sở hữu bộ nhớ.** Hai bước này không thể tùy tiện gộp làm một trong thuật toán nhiều luồng. Đặc biệt, một reader có thể giữ con trỏ tới nút không còn truy cập được từ `head`.

Một bất biến tối thiểu cần bảo vệ là:

> **Chỉ thu hồi một nút khi không còn thao tác đang hoạt động nào có thể dùng tham chiếu cũ để truy cập nút đó.**

Trong hệ thống quản lý bộ nhớ thủ công (C/C++), vi phạm bất biến này có thể dẫn đến *use-after-free*, đọc dữ liệu rác hoặc hỏng vùng nhớ. Trong môi trường có garbage collector (GC), đối tượng còn được tham chiếu thường chưa bị giải phóng, nhưng lỗi **ABA về mặt logic** vẫn có thể tồn tại nếu thuật toán cho phép tái sử dụng đối tượng đã gỡ.

## 2. ABA xảy ra như thế nào?

CAS thường có dạng:

```text
CAS(vị_trí, giá_trị_dự_kiến, giá_trị_mới)
```

CAS thành công nếu **giá trị tại thời điểm so sánh** bằng `giá_trị_dự_kiến`; CAS không tự ghi nhớ toàn bộ lịch sử thay đổi của vị trí ấy.

Xét stack ban đầu:

```text
head = A ──> B ──> C
```

Hai luồng cùng thao tác. T1 chuẩn bị `pop()`: đọc `oldHead = A` và `next = B`, nhưng bị tạm dừng trước khi gọi CAS. T2 tiếp tục chạy, thực hiện nhiều thao tác rồi **đưa lại chính đối tượng nút A** vào đầu stack.

| Bước | Luồng T1 | Luồng T2 | Giá trị `head` |
| --- | --- | --- | --- |
| 0 | — | — | `A -> B -> C` |
| 1 | Đọc `oldHead = A` và `next = B`; tạm dừng | — | `A -> B -> C` |
| 2 | Đang dừng | `pop A` thành công | `B -> C` |
| 3 | Đang dừng | `pop B` thành công; B bị gỡ khỏi stack | `C` |
| 4 | Đang dừng | Gắn lại **đúng nút A** với `A.next = C`, rồi `push A` | `A -> C` |
| 5 | `CAS(head, A, B)` thành công vì `head` lại bằng A | — | **`B -> ...` (sai)** |

Vấn đề ở bước 5: T1 nghĩ rằng `A` vẫn đứng trước `B`, trong khi `A` đã bị lấy ra rồi đưa lại, và `B` không còn nằm trong stack. Lệnh CAS thành công với giá trị `A` hợp lệ về mặt so sánh con trỏ, nhưng **dữ kiện `next = B` của T1 đã lỗi thời**. Stack có thể mất nút hoặc trỏ tới nút đã bị thu hồi.

Diễn biến của giá trị ở `head` là:

```text
A  ──>  B  ──>  C  ──>  A
^                        ^
đọc lần đầu              CAS so sánh A và vẫn thấy A
```

Vì giá trị thay đổi rồi quay lại giá trị cũ, hiện tượng được gọi là **A-B-A**.

### Những điều cần hiểu đúng về ABA

- ABA có thể xảy ra với **con trỏ, chỉ số ô nhớ, ID, số nguyên hay trạng thái khác**, không riêng danh sách liên kết.
- CAS so sánh giá trị theo cách mà kiểu nguyên tử định nghĩa; với một con trỏ đơn thuần, việc cùng địa chỉ **không chứng minh đây vẫn là lần tồn tại cũ của nút**.
- ABA chỉ là **nguy cơ gây lỗi khi thuật toán dựa vào giả định “không đổi”**. Nếu tính đúng đắn không phụ thuộc lịch sử thay đổi, quay lại cùng giá trị chưa chắc là lỗi.
- Trong ví dụ trên phải tái sử dụng **đúng nút A**, hoặc tái sử dụng đúng địa chỉ của A, để CAS trên con trỏ `head` thấy lại cùng giá trị. Nếu mỗi lần `push` luôn tạo đối tượng nút mới và không bao giờ đẩy lại nút cũ, kịch bản cụ thể này không xuất hiện.

## 3. Use-after-free có thể xảy ra mà không cần ABA

Thậm chí chưa cần giá trị `head` quay lại `A`, việc thu hồi ngay khi `pop` thành công đã có thể sai.

Giả sử T1 chạy:

```cpp
// Mã minh họa không an toàn: không sử dụng nguyên xi trong C++.
Node* p = head.load();
Node* next = p->next;   // Có thể dereference vùng nhớ đã giải phóng.
```

Nếu T1 tạm dừng **sau khi đọc `p = A` nhưng trước khi đọc `p->next`**, T2 có thể `pop A` rồi gọi `delete A`. Khi T1 tiếp tục, phép truy cập `p->next` là **use-after-free**. Không có bước `head` trở lại `A` nào ở đây.

Một kiểu lỗi tương tự có thể xuất hiện khi:

- Reader đang duyệt danh sách liên kết và giữ con trỏ tới nút kế tiếp.
- Writer xóa nút, rồi bộ cấp phát tái sử dụng cùng địa chỉ cho một đối tượng khác.
- Reader tiếp tục đọc trường hoặc CAS bằng con trỏ cũ, dù thực thể logic ban đầu đã biến mất.

**CAS chỉ giúp thay đổi một ô nhớ nguyên tử; nó không giữ sống đối tượng nằm ở địa chỉ được lưu trong ô đó.** Hơn nữa, lệnh CAS thất bại vẫn có thể đã xảy ra **sau** một phép truy cập tới bộ nhớ không còn hợp lệ. Vì vậy, chỉ “thử lại nếu CAS thất bại” không giải quyết được vấn đề.

Ta phải bảo vệ **hai loại an toàn riêng**:

| Vấn đề | Điều có thể sai | Cách bảo vệ chính |
| --- | --- | --- |
| **ABA / thay đổi bị bỏ sót** | CAS chấp nhận trạng thái đã quay về giá trị cũ, khiến quyết định dựa trên snapshot lỗi thời | Nhận diện thế hệ/phiên bản; thiết kế lại giao thức để quay về giá trị cũ không làm sai bất biến |
| **Use-after-free** | Một reader dereference nút đã giải phóng hoặc tái sử dụng | Trì hoãn thu hồi cho đến khi chắc chắn không còn reader có thể truy cập; dùng GC, hazard pointers, epoch, RCU hoặc cơ chế sở hữu phù hợp |

Hai bài toán có liên quan: nếu cho phép tái sử dụng địa chỉ sớm, nguy cơ ABA thường tăng. Tuy vậy, **chống ABA không thay thế thu hồi an toàn**, và **giữ sống nút không tự ngăn ABA logic do tái liên kết chính nút ấy**.

## 4. Dùng bộ đếm phiên bản để nhận diện ABA

Thay vì chỉ lưu con trỏ `head = A`, có thể lưu một cặp:

```text
head = (con_trỏ, phiên_bản)
```

Mỗi thay đổi thành công trên `head` tăng `phiên_bản`. T1 đọc `(A, 7)`; sau các thao tác của T2, `head` có thể trở về con trỏ `A` nhưng với phiên bản `(A, 10)`:

```text
T1 quan sát:         (A, 7)
T2 pop A:            (B, 8)
T2 pop B:            (C, 9)
T2 gắn lại A:        (A, 10)

T1 CAS((A, 7), (B, 8))  →  THẤT BẠI
```

Đây là kỹ thuật **tagged pointer / versioned pointer** (con trỏ có nhãn phiên bản). Phiên bản giúp nhận diện thay đổi mà phép so sánh con trỏ đơn thuần bỏ qua.

Pseudocode, với yêu cầu cặp được thao tác **như một giá trị nguyên tử duy nhất**:

```text
function pop():
    loop:
        old = atomic_load(head)                // (ptr, version)
        if old.ptr == null: return EMPTY
        next = old.ptr.next                     // CẦN bảo vệ vòng đời old.ptr
        desired = (next, old.version + 1)
        if CAS(head, old, desired):
            retire(old.ptr)                    // Chưa được free ngay
            return old.ptr.value
```

**Giới hạn quan trọng:**

1. `(ptr, version)` phải được đọc và CAS **nguyên tử như một cặp**. Hai biến nguyên tử cập nhật tách rời không cho cùng bảo đảm. Trên một số nền tảng phải dùng double-width CAS hoặc cách đóng gói được hỗ trợ.
2. Bộ đếm có kích thước hữu hạn có thể **tràn và quay vòng**. Cần chứng minh số lần cập nhật giữa hai quan sát không thể làm phiên bản quay lại cùng giá trị, hoặc dùng chiến lược loại trừ nguy cơ đó.
3. Phiên bản chống ABA tại `head` nhưng **không bảo vệ** phép đọc `old.ptr.next` trước khi CAS. Nếu `old.ptr` đã bị giải phóng, pseudocode vẫn có use-after-free.
4. Thêm phiên bản cho `head` không tự giải quyết ABA ở mọi liên kết hoặc thao tác nhiều con trỏ trong một cấu trúc lớn.

Kết luận: có thể cần **cơ chế chống ABA** và **cơ chế thu hồi an toàn** cùng lúc; chọn một không có nghĩa đã thay thế cái kia.

## 5. Hazard pointers: reader công bố nút đang sử dụng

**Hazard pointer** cho phép luồng đọc/ghi công bố rằng nó đang sử dụng một nút cụ thể. Mỗi luồng tham gia có một hoặc nhiều ô con trỏ bảo vệ (*hazard slots*), thường là các biến nguyên tử. Writer không giải phóng các nút đã gỡ nếu vẫn thấy chúng được bảo vệ.

Quy trình khái niệm để T1 lấy và sử dụng nút đầu stack:

1. Đọc `p = head`.
2. Công bố `hazard[T1] = p` để thông báo T1 có thể dùng `p`.
3. **Đọc lại `head` để xác nhận** `p` vẫn là nút đầu. Nếu giá trị thay đổi, bỏ bảo vệ cũ và thử lại; không được dereference `p` trước khi xác nhận.
4. Sau khi xác nhận, mới đọc trường của `p` và thực hiện thao tác. Giữ hazard cho tới khi không còn truy cập `p`.
5. Xóa `hazard[T1]` khi hoàn tất.

Pseudocode diễn tả ý tưởng, **không phải bản C++ đầy đủ về memory ordering**:

```text
function protect_head(myHazardSlot):
    loop:
        p = atomic_load(head)
        atomic_publish_hazard(myHazardSlot, p)
        if atomic_load(head) == p:
            return p            // p được bảo vệ khi sử dụng
        // head đổi; lần lặp tiếp theo cập nhật slot

function retire_node(node):
    retired_list.add(node)
    // Lúc thích hợp: thu thập tất cả hazard slot với quy tắc
    // đồng bộ thích hợp rồi đối chiếu với các nút retired.
    // Chỉ reclaim các nút chắc chắn không được bảo vệ.
```

**Vì sao cần bước xác nhận?** Nếu T1 chỉ đọc `p` rồi mới ghi hazard mà không kiểm tra lại, T2 có thể gỡ và giải phóng `p` trong khoảng giữa hai bước. Hazard được công bố **sau khi đã quá muộn** và không cứu được lần truy cập tiếp theo.

**Vì sao cần memory ordering?** Việc công bố hazard, đọc lại nguồn con trỏ, gỡ liên kết và quét hazard của reclaimer phải có quan hệ đồng bộ đúng theo mô hình bộ nhớ. Một bản cài đặt dùng thứ tự bộ nhớ quá yếu có thể để reclaimer bỏ sót hazard dù mã trông như đã làm đủ năm bước. Cần dùng thuật toán hazard pointers đã được chứng minh và triển khai đúng cho nền tảng cụ thể.

### Writer xử lý nút đã gỡ thế nào?

Writer không `delete` ngay sau CAS gỡ nút. Nó đưa nút vào **danh sách retired**, định kỳ đọc các hazard slots và chỉ thu hồi nút không xuất hiện trong bất kỳ hazard nào và đã thỏa điều kiện an toàn của giao thức.

Ví dụ:

```text
Hazard của các luồng:
T1: A       T2: C       T3: null

Retired list: A, B, D

Có hazard bảo vệ: A
Ứng viên có thể reclaim khi quét hợp lệ: B, D
Phải giữ lại: A
```

Khi duyệt danh sách liên kết có nhiều nút, **bảo vệ nút hiện tại chưa đủ nếu sắp dereference nút kế tiếp**. Reader có thể cần một hazard slot thứ hai cho `next` và xác nhận liên kết vẫn hợp lệ trước khi chuyển bảo vệ. Cần biết chính xác nút nào được phép dereference tại mỗi thời điểm.

Hazard pointers thích hợp khi cần thu hồi **riêng từng nút** mà không buộc mọi reader đi qua một epoch chung. Đổi lại, mỗi luồng phải quản lý các slot, thao tác công bố nguyên tử và quét danh sách retired; tốc độ thu hồi phụ thuộc reader rời khỏi nút và quá trình quét. Reader giữ hazard quá lâu có thể khiến nút tương ứng không được thu hồi lâu dài.

## 6. Epoch-based reclamation (EBR): đợi reader rời giai đoạn đọc

**Epoch-based reclamation** nhóm khoảng thời gian truy cập thành các **epoch** (thế hệ). Reader đánh dấu mình đang tham gia một vùng đọc trước khi lấy con trỏ dùng chung; writer ghi nhận epoch mà nút bị gỡ khỏi cấu trúc.

Sơ đồ ý tưởng:

```text
Thời gian →
Reader R1: [vào epoch e ── đọc A ───────── ra khỏi vùng đọc]
Writer W :             gỡ A, retire(A, e)
Reader R2:                           [vào epoch e+1 ─ đọc ... ─ ra]

Thu hồi A: chỉ sau khi các reader có thể đã thấy A
           từ trước lúc gỡ đều rời vùng đọc an toàn.
```

Các bước điển hình:

1. Reader **pin/enter** một epoch trước khi đọc con trỏ chia sẻ.
2. Reader có thể đi qua nhiều nút đã được liên kết; trong lúc pin, hệ thống không thu hồi những nút mà reader vẫn có thể chạm tới.
3. Writer gỡ nút ra khỏi cấu trúc, đưa vào danh sách retired cùng metadata epoch.
4. Khi mọi reader có thể đã quan sát nút đó đi qua điểm an toàn (*quiescent state*), reclaimer mới giải phóng nút.
5. Reader **unpin/exit** khi không dùng các con trỏ bảo vệ bởi epoch nữa.

Ưu điểm: reader thường chỉ cần ghi nhận epoch ở đầu/cuối **một lượt đọc**, không nhất thiết công bố riêng từng con trỏ. Điều này phù hợp khi reader duyệt nhiều nút liên tục.

Nhược điểm: chỉ một reader bị tạm dừng trong vùng đã pin có thể trì hoãn thu hồi **nhiều nút** bị retired về sau, làm bộ nhớ tăng mạnh. Do đó, **cấu trúc có thể lock-free về thao tác logic nhưng việc thu hồi hoặc cấp phát bộ nhớ vẫn gặp áp lực khi reader chậm**.

Không được giữ con trỏ sang nút bảo vệ bằng EBR để sử dụng **sau khi unpin** nếu không có cơ chế sở hữu khác. Quy tắc “pin trước khi đọc, unpin sau lần truy cập cuối” là một phần của bất biến an toàn.

## 7. Read-copy-update (RCU) và các lựa chọn khác

### RCU: công bố phiên bản mới rồi chờ grace period

**Read-copy-update (RCU)** cũng tách việc **gỡ/công bố phiên bản mới** với việc **thu hồi phiên bản cũ**. Reader vào vùng đọc RCU, truy cập phiên bản, rồi ra khỏi vùng; updater công bố cấu trúc mới và đặt cấu trúc cũ vào hàng đợi thu hồi sau một **grace period**. Grace period bảo đảm các vùng đọc có thể đã nhìn thấy phiên bản cũ đã kết thúc.

```text
Reader trước công bố: [đọc bản cũ ───────────]
Writer:                         [công bố bản mới]----[grace period]---free(cũ)
Reader sau công bố:                  [đọc bản mới ────]
```

RCU phổ biến trong hệ thống có số lượt đọc rất lớn, số lần cập nhật ít hơn, ví dụ bảng định tuyến hoặc các cấu trúc nhân hệ điều hành. EBR và RCU đều dựa trên sự chuyển tiếp qua trạng thái an toàn của reader, nhưng **cách tổ chức epoch, grace period, API và bảo đảm tiến triển khác nhau theo triển khai**; không nên coi chúng là một giao thức có thể tráo đổi trực tiếp.

### Đếm tham chiếu (*reference counting*)

Mỗi reader sở hữu một tham chiếu được đếm; nút chỉ được thu hồi khi số đếm về 0 và không còn tham chiếu sở hữu hợp lệ. Ví dụ, C++ dùng `std::shared_ptr` có thể hỗ trợ quản lý vòng đời tự động khi **mọi lần lấy và chuyển giao tham chiếu** được đồng bộ đúng; dùng thao tác nguyên tử thích hợp cho biến `shared_ptr` được chia sẻ là điều quan trọng.

Tuy nhiên, với **con trỏ thô**, quy trình “đọc con trỏ, sau đó tăng `refcount`” có một cửa sổ nguy hiểm: nút có thể đã bị luồng khác thu hồi **trước khi** tăng số đếm. Bản thân refcount không bảo vệ được việc lần đầu lấy một con trỏ đang thay đổi đồng thời. Ngoài ra, cập nhật bộ đếm tạo thêm tranh chấp nguyên tử và cơ chế đếm không tự giải quyết vòng tham chiếu chu trình.

### Garbage collector (GC)

Trong Java, C# hoặc môi trường quản lý bộ nhớ tương tự, nếu T1 còn giữ **tham chiếu mạnh** tới đối tượng `A`, GC thông thường không giải phóng đối tượng đó chỉ vì `A` bị gỡ khỏi stack. Vì vậy, lỗi use-after-free kiểu `delete A` trong C++ không xuất hiện theo cùng cách nếu chỉ dùng tham chiếu đối tượng quản lý.

Tuy nhiên, GC **không biến một thuật toán CAS sai thành đúng**. Nếu chính đối tượng nút được gỡ rồi đưa lại vào stack, ABA logic vẫn có thể xảy ra. Cũng cần kiểm soát bất biến của các trường mutable, thứ tự công bố và việc giữ tham chiếu quá lâu gây áp lực bộ nhớ.

### So sánh để chọn cơ chế

| Cơ chế | Bảo vệ theo | Chi phí/đổi lại | Tình huống hợp lý |
| --- | --- | --- | --- |
| **Tagged/versioned pointer** | Lịch sử thay đổi tại một vị trí nguyên tử | CAS cặp giá trị, rủi ro tràn version; **không** bảo vệ use-after-free | Ngăn CAS bỏ qua thay đổi A-B-A |
| **Hazard pointers** | Nút cụ thể reader đang dùng | Công bố hazard, xác nhận lại, quét danh sách retired | Stack/queue/list trong C++ có thu hồi theo nút |
| **EBR** | Vùng đọc gắn với epoch | Pin/unpin; reader chậm có thể giữ nhiều nút retired | Đường đọc duyệt nhiều nút, reader kết thúc tương đối nhanh |
| **RCU** | Vùng đọc và grace period | Hạ tầng RCU/điều phối thu hồi; reader dài làm chậm grace period | Tải đọc rất cao, cập nhật ít |
| **Reference counting** | Quyền sở hữu từng đối tượng | Tăng/giảm bộ đếm nguyên tử; phải lấy tham chiếu an toàn | Đối tượng có quan hệ sở hữu rõ ràng |
| **GC** | Các đối tượng còn tham chiếu mạnh | Chi phí collector và thời gian giữ đối tượng | Cấu trúc đồng thời trên runtime quản lý bộ nhớ |

Không có cơ chế nào phù hợp với mọi tải. Nên chọn dựa trên tỷ lệ đọc/ghi, thời gian một reader giữ con trỏ, số luồng hoạt động, chính sách cấp phát và mức bảo đảm tiến triển cần đạt.

## 8. Ví dụ Java: stack CAS với nút không tái sử dụng

Ví dụ sau minh họa một cách **giảm nguồn ABA** trong môi trường có GC: mỗi lần `push` tạo đối tượng nút mới, và `pop` chỉ trả **giá trị** chứ không để người dùng lấy nút rồi đẩy lại. Khi nút còn được một luồng tham chiếu, GC đảm bảo an toàn vòng đời đối tượng theo mô hình quản lý bộ nhớ của Java.

```java
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

public final class ImmutableNodeStack<T> {
    private static final class Node<T> {
        final T value;
        final Node<T> next;

        Node(T value, Node<T> next) {
            this.value = value;
            this.next = next;
        }
    }

    private final AtomicReference<Node<T>> head =
            new AtomicReference<>();

    public void push(T value) {
        Objects.requireNonNull(value);

        while (true) {
            Node<T> before = head.get();
            Node<T> fresh = new Node<>(value, before);

            if (head.compareAndSet(before, fresh)) {
                return;
            }
        }
    }

    public Optional<T> pop() {
        while (true) {
            Node<T> before = head.get();
            if (before == null) {
                return Optional.empty();
            }

            Node<T> successor = before.next;
            if (head.compareAndSet(before, successor)) {
                return Optional.of(before.value);
            }
        }
    }
}
```

Những điều giúp ví dụ này an toàn hơn kịch bản ABA đã nêu:

- `Node` được tạo mới ở mỗi lượt `push`; nút đã `pop` không có API để được đưa lại vào cấu trúc.
- Trường `next` và `value` là `final`, không có bước sửa lại liên kết của một nút đang được dùng.
- GC giữ sống đối tượng `before` khi vẫn có tham chiếu phù hợp tới nó; không cần gọi `delete` sau `pop`.
- `AtomicReference` cung cấp phép đọc và CAS với các bảo đảm nguyên tử/khả kiến thích hợp trong Java Memory Model.

Các điều kiện này chỉ áp dụng cho thiết kế cụ thể. Nếu thay đổi API để **tái sử dụng nút**, thêm pool nút với thao tác gắn lại, hoặc chuyển sang C++ quản lý con trỏ thô, phải phân tích lại cả ABA lẫn thu hồi bộ nhớ. Ngoài ra, vì thao tác `push` có cấp phát đối tượng, không nên suy luận rằng toàn bộ lời gọi Java luôn có bảo đảm tiến triển lock-free ở cấp runtime trong mọi tình huống.

## 9. Độ phức tạp và những đánh đổi ẩn

Thuật toán stack Treiber cơ bản có thao tác `push/pop` **`O(1)` cho một lần CAS thành công không tranh chấp**. Tuy nhiên, `O(1)` không nói lên số lần CAS thất bại khi có nhiều writer và cũng không tính các bước cần để bảo đảm vòng đời của nút.

Với `P` luồng tham gia, `H` hazard slots và `R` nút trong danh sách retired:

- **Version tag:** cộng phiên bản là `O(1)` về mặt logic, nhưng có thể đòi hỏi CAS rộng hoặc cách đóng gói phức tạp hơn; điều kiện tránh tràn phiên bản vẫn cần được chứng minh.
- **Hazard pointers:** một lượt lấy con trỏ phải công bố hazard và kiểm tra lại; quét để chọn các nút có thể thu hồi cần xét các hazard đang công bố và các nút chờ (`H` và `R`). Tần suất quét quyết định chi phí trung bình và dung lượng bộ nhớ giữ lại.
- **EBR/RCU:** đường đọc có thể rất nhẹ, nhưng tổng số nút chờ thu hồi tăng nếu reader ở trong vùng bảo vệ lâu. Chi phí không chỉ là CPU mà còn là **đỉnh bộ nhớ**.
- **Refcount:** phép chuyển giao tham chiếu tạo lưu lượng cập nhật bộ đếm; khi chia sẻ rất rộng, đây có thể là điểm tranh chấp.
- **GC:** lập trình viên không trực tiếp giải phóng nút, nhưng việc cấp phát liên tục và giữ tham chiếu lâu vẫn tác động độ trễ, thông lượng và bộ nhớ.

Có thể có một cấu trúc **lock-free về thao tác logic** nhưng pipeline thực tế bị kẹt bởi bộ cấp phát, cơ chế thu hồi hoặc giới hạn bộ nhớ. Khi đánh giá yêu cầu lock-free/wait-free, cần nêu rõ **phạm vi của bảo đảm tiến triển** và những primitive được giả định.

## 10. Checklist thiết kế và kiểm chứng

Trước khi công bố một cấu trúc liên kết có thao tác gỡ nút đồng thời, hãy trả lời:

1. **Ai còn có thể giữ con trỏ?** Bao gồm reader tạm dừng, writer đang retry CAS, người duyệt qua nhiều liên kết và callback của ứng dụng.
2. **Khi nào nút được coi là retired?** Thường sau khi gỡ liên kết thành công tại điểm tuyến tính hóa, nhưng cần phân biệt trạng thái logic với quyền sở hữu vùng nhớ.
3. **Ai quyết định được phép thu hồi?** GC, hazard scan, epoch/grace period hay bộ đếm tham chiếu? Điều gì xảy ra nếu reader dừng rất lâu?
4. **Địa chỉ có thể xuất hiện lại không?** Pool, freelist hoặc tái sử dụng nút có thể làm phát sinh ABA. Nếu dùng version tag, đã có cận tràn và CAS nguyên tử trên cả cặp chưa?
5. **Reader có dereference trước khi được bảo vệ không?** Đặc biệt giữa `load(head)` và đọc `head->next`.
6. **Khi reader chuyển từ nút hiện tại sang nút tiếp theo, nút tiếp theo được bảo vệ như thế nào?** Không thể mặc định hazard cho nút trước bảo vệ toàn chuỗi.
7. **Các phép tải/lưu nguyên tử có đúng memory ordering không?** Thứ tự lệnh trong mã nguồn chưa đủ để tạo quan hệ đồng bộ cần thiết.
8. **Bảo đảm tiến triển xét đến cả bộ quản lý bộ nhớ chưa?** Một thuật toán CAS nhanh có thể phát sinh cấp phát hoặc quét retired khiến giới hạn độ trễ thay đổi.

Đối với C/C++, nên dùng thư viện và kỹ thuật thu hồi đã được kiểm chứng thay vì tự lắp ghép hazard/epoch từ vài biến nguyên tử. Những lỗi ở đây thường chỉ xuất hiện sau hàng triệu lần xen kẽ thao tác; việc chạy thử không phát hiện lỗi không phải bằng chứng an toàn.

## 11. Tình huống tự kiểm tra

**Câu 1.** T1 đọc `head = A` rồi tạm dừng. T2 gỡ `A`, giải phóng vùng nhớ của A, nhưng không đưa địa chỉ đó trở lại `head`. T1 tiếp tục đọc `A.next`. Đây là ABA hay use-after-free?

*Giải thích:* Đây là **use-after-free**, không cần ABA. T1 đang sử dụng vùng nhớ đã bị giải phóng; CAS có thể còn chưa xảy ra.

**Câu 2.** Stack dùng CAS trên cặp `(pointer, version)`, nhưng `pop` vẫn đọc `p->next` trước khi bảo vệ `p` khỏi thu hồi. Đã an toàn chưa?

*Giải thích:* **Chưa.** Version có thể ngăn CAS chấp nhận một giá trị `head` quay về trạng thái cũ, nhưng phép dereference `p->next` vẫn có thể truy cập nút đã bị giải phóng.

**Câu 3.** Một hệ thống EBR có reader giữ epoch suốt vài phút, trong khi writer liên tục xóa hàng trăm nghìn nút. Điều gì có thể xảy ra?

*Giải thích:* Nhiều nút bị retired **chưa đủ điều kiện thu hồi**, vì reader cũ có thể còn dùng chúng. Bộ nhớ tăng dù phép CAS gỡ nút vẫn hoàn tất. Cần kiểm soát thời gian giữ epoch, tốc độ tạo nút retired và dung lượng hệ thống.

**Câu 4.** Trong Java, hai luồng dùng stack với `Node` bất biến; mỗi `push` luôn tạo `Node` mới và `pop` trả giá trị. Có cần trực tiếp giải phóng nút bằng `free` không? Có thể bỏ phân tích ABA cho mọi phiên bản stack không?

*Giải thích:* **Không cần gọi `free`** trong thiết kế GC thông thường. Với API không tái sử dụng nút này, ABA do tái dùng đúng đối tượng nút không xuất hiện như ví dụ Treiber. Nhưng một thiết kế khác cho phép nút quay lại hoặc có trường mutable vẫn cần phân tích ABA và tính tuyến tính hóa.

**Câu 5.** Reader dùng hazard pointer cho nút `A` rồi muốn truy cập trường của nút `B = A.next`. Vì sao không được mặc định `B` an toàn?

*Giải thích:* Hazard của A chỉ bảo vệ **A**; writer khác có thể đã gỡ và retire B. Reader phải tuân thủ giao thức bảo vệ nút kế tiếp (thường dùng slot thứ hai và xác nhận liên kết) trước khi dereference B.

**Điểm cần nhớ:** Có ba việc khác nhau phải chứng minh khi xây dựng cấu trúc liên kết đồng thời: **bất biến và tính tuyến tính hóa** của thao tác, **chống ABA** khi lịch sử thay đổi có ý nghĩa, và **thu hồi an toàn** khi reader còn giữ tham chiếu. CAS giải quyết một phần vấn đề đồng bộ; chỉ cơ chế quản lý vòng đời thích hợp mới cho phép tái sử dụng bộ nhớ mà không gây lỗi cho các luồng đang đọc.
