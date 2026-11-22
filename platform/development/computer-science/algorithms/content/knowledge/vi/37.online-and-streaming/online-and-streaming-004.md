# Thay trang và các chiến lược lưu đệm

**Thay trang (page replacement)** và **quản lý lưu đệm (cache replacement)** trả lời một câu hỏi chung: khi bộ nhớ nhanh chỉ chứa được một số lượng mục nhất định và một mục mới cần được truy cập, **nên giữ mục nào, loại mục nào** để giảm chi phí truy cập trong tương lai?

Trong hệ điều hành, các mục có thể là **trang bộ nhớ** đang nằm trong RAM; trong cache ứng dụng, các mục có thể là block đĩa, object, response HTTP, kết quả truy vấn, phần dữ liệu của một luồng sự kiện hoặc bản ghi cần dùng lại. Các môi trường khác nhau có cơ chế và chi phí riêng, nhưng nhiều thuật toán thay thế có chung mô hình.

Bài học thuộc nhóm **Trực tuyến và luồng**, nhấn mạnh rằng **thuật toán trực tuyến (online)** phải ra quyết định khi yêu cầu xuất hiện, **không biết trước chuỗi truy cập tương lai**. Đây là lý do chúng ta phân biệt:

- **FIFO (First-In, First-Out):** thay mục được nạp vào cache sớm nhất.
- **LRU (Least Recently Used):** thay mục lâu nhất chưa được truy cập.
- **Belady OPT/MIN:** với toàn bộ chuỗi truy cập biết trước, thay mục có lần sử dụng kế tiếp **xa nhất trong tương lai**, hoặc không dùng lại; tạo cận tối ưu offline dưới giả thiết đơn giản.
- **CLOCK/Second Chance:** dùng bit tham chiếu để xấp xỉ tính gần đây với chi phí quản lý phù hợp.
- **LFU và biến thể:** dùng tần suất thay vì chỉ thời điểm truy cập gần nhất.
- **Các chiến lược thích ứng:** thêm tuổi dữ liệu, cách chống quét tuần tự, nhiều mức cache, giới hạn bộ nhớ và chính sách write-back.

Trọng tâm là **tính đúng, lỗi trang (miss/page fault), hiện tượng Belady's anomaly, stack property, phân tích cạnh tranh (competitive analysis)**, các workload đối kháng và một chương trình **Java 17+ độc lập** so sánh FIFO/LRU/OPT bằng cùng một chuỗi truy cập.

Bảo đảm và thuật toán trong phần lý thuyết trước hết dùng mô hình **demand paging, một cache k khung, mọi trang có cùng kích thước, chi phí mỗi miss bằng 1, không prefetch, không có trang bị khóa, ban đầu cache trống**. Khi mở rộng sang hệ thống thực, phải nêu lại những giả thiết thay đổi.

## 1. Mô hình paging trực tuyến

Cho một chuỗi yêu cầu truy cập trang:

**σ=(p₁,p₂,...,pₙ)**.

Cache có thể giữ tối đa **k trang phân biệt**. Với mỗi yêu cầu pᵢ:

1. Nếu pᵢ đã nằm trong cache, đó là **hit**: phục vụ ngay, không cần tải trang vào khung mới.
2. Nếu pᵢ không nằm trong cache, đó là **miss**: phải tải trang cần thiết vào cache (hoặc xử lý trực tiếp nếu k=0).
3. Khi cache đầy và phát sinh miss, chọn một trang đang ở cache để **evict** trước khi nhận trang mới.
4. Sau mỗi bước, cache chứa nhiều nhất k trang phân biệt.

Trong mô hình đơn giản, mục tiêu là:

**minimize số miss trên toàn chuỗi σ**.

Nếu n>0, tỷ lệ hit được tính:

**hitRate=hits/n**,

và:

**missRate=misses/n**.

Với n=0, hai tỷ lệ có mẫu số 0 nên phải định nghĩa riêng hoặc ghi “không áp dụng”, không in 0/0 và coi đó là dữ liệu đo chính xác.

### Hai thành phần không được nhầm

**Replacement policy** quyết định **trang nạn nhân** khi cần giải phóng một khung.

**Admission policy** quyết định **trang vừa yêu cầu có nên đưa vào cache hay không**. Mô hình demand paging cổ điển thường mặc định trang vừa miss phải được đưa vào; một cache ứng dụng có thể cho phép bỏ qua admission với object ít giá trị.

Khi thay đổi admission policy, đang nghiên cứu một bài toán khác; các chứng minh tối ưu cho demand paging không nhất thiết áp dụng nguyên xi.

## 2. Trực tuyến, ngoại tuyến và thông tin tương lai

Thuật toán **online** phải quyết định ở bước i bằng thông tin đã biết đến thời điểm đó:

**p₁,...,pᵢ**, tình trạng cache và trạng thái nội bộ.

Nó không được biết chính xác pᵢ₊₁,...,pₙ, trừ khi thông tin dự đoán được chỉ rõ trong bài toán.

Thuật toán **offline** có thể biết toàn bộ σ trước khi ra quyết định. Trong mô hình trang đồng kích thước, một cache k khung và mọi miss cùng chi phí, **Belady MIN** là một chính sách offline tối ưu.

### Vì sao còn cần OPT nếu không triển khai được online?

- Dùng làm **lower bound** số miss mà bất kỳ chính sách hợp lệ nào có thể đạt trên trace đó.
- Đo khoảng cách giữa chính sách hiện tại và **một chuẩn lý tưởng**.
- Kiểm tra đúng sai các thuật toán mô phỏng.
- Làm chuẩn để học về **competitive analysis**.

OPT **không phải** là một hệ điều hành tiên tri có thể triển khai trực tiếp cho trace chưa xảy ra. Dùng kết quả OPT của một log quá khứ để tuyên bố hệ thống thực sẽ luôn đạt OPT trong tương lai là sai.

## 3. Hit, miss và chi phí thực tế

**Hit** có nghĩa trang/mục được phục vụ từ tầng lưu đệm đang phân tích.

**Miss** có nghĩa phải tìm ở tầng dưới hoặc thực hiện một hoạt động bổ sung. Trong virtual memory, page fault có thể kéo theo truy xuất đĩa hoặc chỉ là xử lý mapping tùy nguyên nhân và trạng thái; không phải mọi page fault đều có chi phí bằng nhau.

Trong một mô hình có miss cost c_m và hit cost c_h, chi phí thời gian sơ bộ có thể là:

**TotalCost≈hits·c_h + misses·c_m + overhead quản lý cache**.

Nếu trang bị dirty cần write-back, chi phí evict còn có thể bao gồm **ghi dữ liệu ra tầng lưu trữ**. Khi đó chỉ tối thiểu hóa số miss chưa chắc tối thiểu hóa latency hay I/O bytes.

### Ba loại miss để chẩn đoán

- **Compulsory/cold miss:** lần truy cập đầu tiên tới một mục, khi mục chưa từng được tải.
- **Capacity miss:** tập dữ liệu cần dùng lớn hơn dung lượng cache.
- **Conflict miss:** với cache set-associative hoặc ánh xạ giới hạn, nhiều mục tranh cùng một nhóm khung dù toàn cache còn không gian ở nhóm khác.

Mô hình cache **fully associative k khung** của bài không có conflict miss do mapping set. Không nên suy luận một vết miss trong mô hình đó là giải thích đầy đủ cho cache CPU hay TLB thực tế.

## 4. FIFO: vào trước, ra trước

**FIFO** giữ thứ tự trang **được nạp vào cache**. Khi xảy ra miss lúc cache đầy, loại trang được nạp sớm nhất, bất kể trang ấy vừa được truy cập hay chưa.

Mỗi lần trang mới được nạp, đưa vào cuối hàng đợi. Trang ở đầu hàng đợi là ứng viên bị loại đầu tiên.

### Pseudocode

~~~text
FIFO(requests, capacity):
    resident = empty set
    queue = empty FIFO queue
    misses = 0

    for page in requests:
        if page in resident:
            continue

        misses++

        if capacity == 0:
            continue

        if resident has capacity pages:
            victim = queue.pop_front()
            resident.remove(victim)

        resident.add(page)
        queue.push_back(page)

    return misses
~~~

### Bất biến

Sau mỗi yêu cầu:

- resident và queue chứa đúng cùng các trang.
- Mỗi trang có mặt tối đa một lần.
- queue sắp theo **thời điểm nạp gần nhất** (không theo lần hit).
- Số trang không vượt capacity.

### Độ phức tạp

Với hash set và deque thông thường, mỗi yêu cầu xử lý **O(1) kỳ vọng**, nên tổng **O(n) kỳ vọng**, bộ nhớ O(k) ngoài input.

Nếu dùng mảng và mỗi lần kiểm tra hit phải quét k trang, implementation khác có thể tốn **O(nk)** dù tên chính sách vẫn là FIFO. Cần phân biệt **chính sách** và **cấu trúc dữ liệu triển khai**.

## 5. Điểm yếu cơ bản của FIFO

FIFO không quan tâm đến thời điểm sử dụng gần đây. Một trang nóng được truy cập liên tục nhưng đã được nạp từ lâu vẫn có thể là trang đầu queue và bị loại.

Ví dụ cache k=3, ban đầu chứa thứ tự FIFO:

**[A,B,C]** từ cũ tới mới.

Nếu có hit A nhiều lần, thứ tự vẫn:

**[A,B,C]**.

Khi miss trang D:

- FIFO evict **A**.
- Cache thành **[B,C,D]**.

Chính sách không nhận biết A có thể vừa được dùng ngay trước D. Điều này có thể làm tăng miss trên workload có **temporal locality** mạnh.

### FIFO đơn giản nhưng không luôn tối ưu

Ưu điểm:

- Dễ cài bằng queue.
- Không cần cập nhật thứ tự ở mỗi hit.
- Mỗi lần evict có chi phí quản lý thấp khi dùng cấu trúc phù hợp.

Nhược điểm:

- Bỏ qua thông tin tái sử dụng gần đây.
- Có thể xảy ra **Belady's anomaly**: tăng dung lượng cache nhưng số miss FIFO lại tăng trên cùng trace.
- Một số pattern lặp lại làm chính sách chọn nạn nhân kém hiệu quả.

## 6. LRU: ít được truy cập gần đây nhất

**LRU** loại trang có **lần truy cập gần nhất xa nhất trong quá khứ**.

Với mỗi hit, trang vừa truy cập được chuyển thành **mới nhất**. Với miss, nếu cache đầy, loại trang **cũ nhất theo thời gian truy cập**, sau đó thêm trang mới vào vị trí mới nhất.

### Pseudocode

~~~text
LRU(requests, capacity):
    cache = ordered map from LRU to MRU
    misses = 0

    for page in requests:
        if page in cache:
            move page to MRU end
            continue

        misses++

        if capacity == 0:
            continue

        if cache is full:
            remove LRU entry

        insert page as MRU

    return misses
~~~

**LRU ≠ FIFO**: cả hai đều có thứ tự, nhưng FIFO thay thứ tự **khi nạp**, còn LRU cập nhật thứ tự **cả khi hit**.

### Cách cài trong Java

LinkedHashMap với **accessOrder=true** duy trì thứ tự truy cập; gọi get vào key đang tồn tại có thể thay thứ tự và đưa mục tới MRU end. Khi cache đầy, iterator đầu danh sách là LRU.

Với HashMap/LinkedHashMap thông thường, lookup và cập nhật có chi phí **O(1) kỳ vọng**, tổng **O(n) kỳ vọng**, bộ nhớ O(k).

### Khi LRU hữu ích

LRU khai thác **temporal locality**: một trang vừa được dùng có xu hướng được dùng lại sớm.

Nhưng LRU không hiểu ngữ nghĩa dữ liệu. Một lần quét tuần tự qua rất nhiều trang mới có thể đẩy những trang nóng cũ ra khỏi cache.

## 7. Belady OPT/MIN: trang dùng lại xa nhất

Với toàn bộ chuỗi σ được biết trước, sau một miss lúc cache đầy, **Belady OPT** loại trang mà lần truy cập tiếp theo nằm **xa nhất trong tương lai**.

Nếu một trang sẽ **không bao giờ được truy cập lại**, ưu tiên loại nó: thời điểm tiếp theo là **+∞**.

### Pseudocode

~~~text
OPT(requests, capacity):
    cache = empty set
    misses = 0

    for each position i:
        page = requests[i]

        if page is already cached:
            continue

        misses++

        if capacity == 0:
            continue

        if cache is full:
            for each cached page q:
                next(q) = first position j>i with requests[j]=q
                          or +infinity if no later use
            victim = a cached page maximizing next(q)
            evict victim

        insert page

    return misses
~~~

### Ví dụ chọn nạn nhân

Cache k=3 hiện có A,B,C; xuất hiện miss trang D. Phần tương lai:

~~~text
... A, B, X, A, Y, C, ...
~~~

Lần tái dùng tiếp theo:

- A: sớm nhất.
- B: tiếp theo.
- C: muộn hơn.

OPT evict **C** vì giữ C không tạo lợi ích trước khi A và B được dùng lại. Nếu một trang không xuất hiện nữa, OPT evict trang đó còn tốt hơn.

### Chi phí tính toán

Phiên bản ngây thơ quét toàn bộ suffix cho mỗi victim có thể rất chậm. Bản Java phía dưới:

1. Duyệt trace **từ phải sang trái** để tiền xử lý nextUse[i].
2. Lưu với mỗi trang resident thời điểm xuất hiện tiếp theo.
3. Khi miss cache đầy, quét tối đa k trang để chọn nextUse xa nhất.

Thời gian **O(nk) kỳ vọng** với hash map cho preprocessing và lookup, bộ nhớ O(n+k). Đây là chi phí của **bộ mô phỏng offline**; không làm thay đổi tính tối ưu số miss của chính sách.

## 8. Vì sao OPT là tối ưu offline?

**Lập luận trao đổi (exchange argument)** là cách chứng minh cổ điển.

Xét thời điểm đầu tiên một lịch thay trang tối ưu O* khác quy tắc MIN trên một miss khi cache đầy. Giả sử:

- MIN muốn loại trang x có lần dùng tiếp theo xa nhất.
- O* loại trang y khác, giữ x.

Ta có thời điểm dùng tiếp theo của y **không muộn hơn** x, bởi MIN chọn x xa nhất.

Có thể sửa lịch O* để loại x tại bước ấy và giữ y, sau đó đồng bộ lại với lịch ban đầu vào một thời điểm thích hợp trước hoặc tại khi x được yêu cầu lần kế tiếp. Trước lúc ấy, giữ y thay vì x không gây thêm miss do yêu cầu tới x chưa đến, trong khi yêu cầu tới y có thể được phục vụ tốt hơn.

Vì không tăng tổng số miss, tồn tại một lịch tối ưu đồng ý với lựa chọn của MIN ở bước đang xét. Lặp phép trao đổi cho những khác biệt về sau, ta có một lịch tối ưu trùng với mọi lựa chọn của MIN.

### Phạm vi chứng minh

Lập luận dùng:

- Trang có **cùng kích thước**.
- Một miss có **chi phí như nhau**.
- Không tính prefetch/writeback khác nhau.
- Cache chứa tối đa k trang và phục vụ **theo yêu cầu**.
- Chuỗi yêu cầu được biết **đầy đủ**.

Với trang có kích thước khác nhau hoặc chi phí fetch khác nhau, chính sách loại lần dùng xa nhất **không mặc nhiên tối ưu**. Phải phát biểu bài toán weighted caching, file caching hoặc mô hình phù hợp khác.

## 9. Chuỗi kinh điển thể hiện Belady's anomaly

Xét dãy 12 yêu cầu:

~~~text
1 2 3 4 1 2 5 1 2 3 4 5
~~~

Cache khởi đầu trống. Bảng dưới đây ghi **miss (M)** hoặc **hit (H)** với FIFO k=3 và FIFO k=4. Thứ tự hàng đợi ghi **cũ → mới**.

| Bước | Trang | FIFO k=3 | Queue k=3 | FIFO k=4 | Queue k=4 |
| ---: | ---: | :---: | --- | :---: | --- |
| 1 | 1 | M | [1] | M | [1] |
| 2 | 2 | M | [1,2] | M | [1,2] |
| 3 | 3 | M | [1,2,3] | M | [1,2,3] |
| 4 | 4 | M | [2,3,4] | M | [1,2,3,4] |
| 5 | 1 | M | [3,4,1] | H | [1,2,3,4] |
| 6 | 2 | M | [4,1,2] | H | [1,2,3,4] |
| 7 | 5 | M | [1,2,5] | M | [2,3,4,5] |
| 8 | 1 | H | [1,2,5] | M | [3,4,5,1] |
| 9 | 2 | H | [1,2,5] | M | [4,5,1,2] |
| 10 | 3 | M | [2,5,3] | M | [5,1,2,3] |
| 11 | 4 | M | [5,3,4] | M | [1,2,3,4] |
| 12 | 5 | H | [5,3,4] | M | [2,3,4,5] |

Tổng:

**FIFO k=3 có 9 miss**.

**FIFO k=4 có 10 miss**.

Tăng cache từ 3 lên 4 khung **làm số miss tăng từ 9 lên 10** trên cùng dãy yêu cầu và cùng policy FIFO.

Đây là **Belady's anomaly**.

### Điều kiện để gọi là anomaly

Phải so cùng:

- Một chuỗi truy cập.
- Một policy FIFO.
- Trạng thái khởi đầu tương ứng, ở đây cache trống.
- Mô hình tính miss giống nhau.

Không so hai workload khác rồi gán cho sự bất thường tăng cache.

## 10. LRU và OPT trên cùng chuỗi

Với trace Belady kinh điển:

~~~text
1 2 3 4 1 2 5 1 2 3 4 5
~~~

Kết quả:

| Thuật toán | k=3 | k=4 |
| --- | ---: | ---: |
| FIFO | **9** | **10** |
| LRU | **10** | **8** |
| OPT | **7** | **6** |

**Không được suy ra LRU luôn ít miss hơn FIFO.** Ở k=3 trên trace này, FIFO có 9 miss còn LRU có **10 miss**. LRU không thống trị FIFO trên mọi input.

**Không được suy ra OPT dùng được online.** OPT cho cận lý tưởng 7 hoặc 6 bằng quyền biết future. Dùng OPT để đánh giá chi phí của chính sách online là hợp lý, nhưng không coi OPT là một lời giải thực thi khi chưa biết trace.

### Khi nào cùng một policy tăng k sẽ không tăng miss?

Không phải mọi policy đều có **stack property**. LRU có, FIFO không. Vì vậy LRU tránh được loại anomaly này trong mô hình standard demand paging.

## 11. Stack property của LRU

Một chính sách có **stack/inclusion property** nếu, sau cùng một tiền tố yêu cầu với trạng thái ban đầu phù hợp, tập trang cache dung lượng k luôn là **tập con** của cache dung lượng k+1:

**C_k(t)⊆C_{k+1}(t)**.

LRU thỏa điều kiện vì:

- Cache k lưu **k trang phân biệt được truy cập gần đây nhất**.
- Cache k+1 lưu **k+1 trang phân biệt được truy cập gần đây nhất**.
- Danh sách k trang gần nhất là một phần của danh sách k+1 trang gần nhất.

Vì vậy nếu một truy cập hit trong cache k, nó cũng hit trong cache k+1; tương đương:

**misses_LRU(k+1)≤misses_LRU(k)**

cho cùng trace và cold-start.

### Không phải nói “LRU luôn tốt hơn mọi policy”

Stack property chỉ so **LRU với chính LRU** khi thay capacity. Nó không chứng minh LRU luôn ít miss hơn FIFO, CLOCK hay LFU ở cùng k.

### OPT cũng không tăng miss khi cache lớn hơn

Ngay cả khi không dùng một thuật toán mô phỏng OPT cụ thể, tập các lịch thay trang khả thi với k+1 khung bao hàm các lịch với k khung. Vì thế:

**OPT(k+1)≤OPT(k)**.

Đây là tính chất của **giá trị tối ưu**, không phải bảo đảm mọi chính sách online có tính đơn điệu tương tự.

## 12. Dùng OPT để đo khoảng cách chính sách online

Với trace σ và capacity k, đặt:

**F_A(σ,k)** là số miss của thuật toán A.

**F_OPT(σ,k)** là số miss offline tối ưu.

Do OPT tối ưu theo mục tiêu này:

**F_OPT(σ,k)≤F_A(σ,k)**

cho mọi chính sách A hợp lệ trong cùng mô hình.

Nếu OPT>0, có thể tính tỷ số thử nghiệm:

**ratio(σ)=F_A(σ,k)/F_OPT(σ,k)≥1**.

Trên trace Belady k=3:

- FIFO/OPT = 9/7 ≈ 1.2857.
- LRU/OPT = 10/7 ≈ 1.4286.

Với k=4:

- FIFO/OPT = 10/6 ≈ 1.6667.
- LRU/OPT = 8/6 ≈ 1.3333.

Các tỷ số này chỉ mô tả **một trace cụ thể**. Chúng **không tự chứng minh** competitive ratio worst-case cho mọi trace.

### Trường hợp OPT=0

Với cache khởi đầu trống, không có miss nếu trace rỗng; tỷ số 0/0 không định nghĩa. Với mô hình warm-start, OPT=0 có thể xảy ra trên các trace chỉ truy cập trang đã cache.

Khi OPT=0, nên báo trực tiếp counts, hoặc dùng định nghĩa bảo đảm **có hằng số cộng** thay vì tùy tiện gán ratio=1.

## 13. Competitive analysis: so với đối thủ offline

Một thuật toán paging online A được gọi là **c-competitive** theo số miss nếu tồn tại hằng số b (không phụ thuộc độ dài/chi tiết trace) sao cho với mọi σ hợp lệ:

**F_A(σ,k)≤c·F_OPT(σ,k)+b**.

Ở đây A và OPT có **cùng capacity k**, trừ khi phát biểu rõ resource augmentation.

Ý nghĩa:

- **c** mô tả chênh lệch nhân trong trường hợp xấu.
- **b** xử lý các sai lệch khởi động, phase đầu tiên hoặc những chi phí cố định.
- Lượng từ **“mọi trace”** khiến định nghĩa mạnh hơn rất nhiều so với đánh giá trung bình vài log thực tế.

### Kết quả cổ điển

Trong mô hình paging chuẩn với k≥1:

- LRU có bảo đảm **k-competitive** (với hằng số cộng thích hợp).
- FIFO cũng có bảo đảm **k-competitive** theo phân tích chuẩn, nhưng proof và invariant quản lý không nhất thiết giống LRU.
- Hệ số **k** là một mốc lower bound cổ điển cho thuật toán paging **xác định** với k khung trong mô hình đối thủ thích hợp.

Tỷ số k có thể khá lớn, nhưng vẫn hữu ích vì không cần giả định trace tương lai hay phân phối input.

Không áp dụng phát biểu này cho k=0, cho cache có trang trọng số/biến kích thước hoặc cho workload có quyền prefetch nếu chưa xây lại mô hình.

## 14. Phân tích LRU bằng phase và marking

Một cách hiểu kết quả cạnh tranh của LRU là chia trace thành **các phase**, mỗi phase chứa **không quá k trang phân biệt** và dài tối đa theo điều kiện ấy.

Khi một yêu cầu mới tạo trang phân biệt thứ k+1, bắt đầu phase mới.

Trong mỗi phase, LRU không cần loại một trang đã được truy cập trong phase để phục vụ một trang **chưa từng xuất hiện trong phase**, bởi luôn có thể evict trang chưa được “đánh dấu” của phase trước hoặc các trang ít gần đây hơn.

Vì thế LRU bị nhiều nhất **k miss mỗi phase**.

Một lập luận chuẩn về các phase liên tiếp, k trang của phase hoàn chỉnh và trang mới bắt đầu phase sau cho cận offline tối thiểu **tuyến tính theo số phase** (trừ một hằng số khởi động). Ghép hai cận thu được:

**F_LRU(σ)≤k·F_OPT(σ)+O(k)**.

### Tránh nhầm proof của FIFO

FIFO có thể có bảo đảm k-competitive nhưng **không phải stack policy**. Không nên lấy bất biến “cache luôn chứa k trang truy cập gần nhất của LRU” rồi gắn cho FIFO.

Khi cần formal proof FIFO, dùng phân tích riêng theo số page faults/hàng đợi, không giả vờ FIFO cũng đánh dấu theo lần truy cập như LRU.

### Vì sao xác định online phải chịu input đối kháng?

Với universe có ít nhất k+1 trang, một adversary biết trạng thái cache của thuật toán xác định có thể liên tục yêu cầu một trang không nằm trong cache ấy, khiến policy online fault thường xuyên. Offline biết toàn bộ chuỗi nên có thể chọn victims tốt hơn.

Phát biểu lower bound cần nói rõ mô hình adversary, initial cache, capacity và kiểu ngẫu nhiên; không phải một nhận xét rằng mọi workload thực đều có tỷ lệ sát k.

## 15. Randomized paging và đối thủ biết ngẫu nhiên

Thuật toán randomized chọn nạn nhân theo xác suất hoặc dùng cấu trúc ngẫu nhiên.

Một chiến lược **randomized marking** có thể đạt competitive ratio kỳ vọng **O(log k)** trong mô hình đối thủ **oblivious** thích hợp (trace không thay đổi để phản ứng với các random choices của thuật toán).

Các kết quả chính xác còn phụ thuộc định nghĩa competitive ratio, additive constants và cách xây thuật toán.

### Vì sao adversary model quan trọng?

- **Oblivious adversary** chọn trace độc lập với các phép tung đồng xu thực tế của thuật toán.
- **Adaptive adversary** có thể phản ứng với quyết định của thuật toán; tùy khả năng quan sát, bảo đảm có thể yếu hơn.

Không được chuyển nguyên cận O(log k) dưới một mô hình adversary sang mọi mô hình, đặc biệt khi đối thủ biết trước các random bits.

### RANDOM eviction không tự có bound tốt

“Bốc thăm ngẫu nhiên một trang để thay” là một chính sách cụ thể, không đồng nghĩa với **randomized marking algorithm** có chứng minh. Muốn gắn nhãn competitive factor cần chính thuật toán và proof tương ứng.

## 16. CLOCK/Second Chance

**CLOCK** là một cách giảm overhead quản lý thứ tự chính xác của LRU bằng cách lưu một **reference bit** cho từng frame và một “kim đồng hồ” chỉ vị trí kiểm tra tiếp theo.

Khi trang được truy cập:

- Nếu hit, đặt reference bit của trang thành 1.
- Khi cần evict, quét từ vị trí kim:
  - Bit=1: chuyển về 0, đi tiếp, cho “cơ hội thứ hai”.
  - Bit=0: chọn trang đó làm nạn nhân.
- Sau thay thế, kim di chuyển theo quy tắc implementation nhất quán.

### Pseudocode

~~~text
CLOCK_ON_MISS(page):
    if cache still has an empty slot:
        place page in a free slot
        reference_bit[slot] = 1
        return

    while reference_bit[hand] == 1:
        reference_bit[hand] = 0
        hand = (hand + 1) mod capacity

    evict slot at hand
    store page in that slot
    reference_bit[hand] = 1
    hand = (hand + 1) mod capacity
~~~

### Đây là approximation của LRU, không phải LRU

CLOCK không duy trì thứ tự truy cập chính xác. Hai trang cùng có bit=1 vẫn có thể có mức độ mới/cũ rất khác nhau. Kết quả miss của CLOCK có thể khác LRU trên cùng trace.

Một bước miss có thể phải quét nhiều slot; với một vòng quét xóa bit và tìm victim, worst-case chi phí quản lý có thể **O(k)** trong implementation điển hình, dù nhiều workload có chi phí trung bình nhỏ.

### Hệ thống thực

Các biến thể CLOCK có thể xem xét dirty bit, referenced bit, aging, nhiều danh sách và chiến lược kernel-specific. Đừng đồng nhất mô hình CLOCK hai dòng ở đây với toàn bộ implementation quản lý bộ nhớ của một hệ điều hành cụ thể.

## 17. LFU: ít được dùng thường xuyên nhất

**LFU (Least Frequently Used)** tìm trang có số lần truy cập tích lũy hoặc theo cửa sổ nhỏ nhất, rồi loại trang đó.

Ưu điểm:

- Nếu độ phổ biến ổn định, những trang hay được dùng có thể được giữ lâu.
- Có thể chống một số lần truy cập đơn lẻ tốt hơn LRU.

Nhược điểm:

- **Cache pollution từ lịch sử cũ:** một trang từng rất nóng nhưng nay lạnh có thể còn bộ đếm cao mãi.
- Cần xử lý **aging/decay** để dữ liệu gần đây quan trọng hơn lịch sử xa.
- Tie-break giữa các trang cùng frequency phải được định nghĩa.
- Một policy chỉ đếm global frequency có thể bỏ lỡ sự chuyển pha của workload.

### Windowed/aging LFU

Có thể giảm các counter theo thời gian, dùng cửa sổ sliding window hoặc sketch tần suất có sai số. Mỗi lựa chọn có tradeoff CPU, RAM và độ chính xác ước lượng.

Không thể chỉ từ tên LFU suy ra luôn tốt hơn LRU hay có competitive ratio tốt cho **mọi** trace.

## 18. Temporal locality, working set và phase change

**Temporal locality:** mục vừa được truy cập có khả năng được truy cập lại sớm.

**Spatial locality:** mục gần vị trí truy cập có thể được dùng tiếp; liên quan đến cách chọn kích thước block/page và prefetch.

**Working set** là tập các trang được dùng trong một cửa sổ tham chiếu gần đây. Nếu cache đủ chứa working set của giai đoạn hiện tại, miss có thể giảm mạnh sau một số compulsory loads.

### Workload thay đổi pha

Ví dụ ứng dụng ban đầu thường dùng:

**A,B,C**,

sau đó chuyển sang:

**D,E,F**.

LRU có thể thích ứng bằng cách đẩy ra các trang của pha cũ khi pha mới lặp lại.

LFU không aging có thể giữ lại các trang cũ với bộ đếm lớn, làm quá trình thích ứng chậm.

### Không có một policy thắng mọi chuỗi

Trong workload scan, LFU hoặc admission control có thể tốt hơn LRU. Trong workload lặp lại có recency mạnh, LRU có thể tốt hơn FIFO. Với trace adversarial, mọi chính sách online đều có hạn chế.

Vì vậy lựa chọn policy cần dựa trên **loại locality và mục tiêu chi phí**, không chỉ một bảng xếp hạng chung.

## 19. Scan pollution và các chiến lược chống quét

Một ứng dụng thường dùng đi dùng lại hai trang nóng A,B, nhưng thỉnh thoảng đọc một dãy trang mới:

~~~text
A B A B | X1 X2 X3 X4 X5 X6 ... | A B
~~~

Nếu cache nhỏ và mọi trang scan mới đều được nạp, LRU có thể evict A,B trong quá trình scan. Khi quay lại A,B, cả hai thành miss.

Một số chiến lược thực tế:

- **Bypass/admission policy:** không lưu những trang đoán là chỉ dùng một lần.
- **2Q, segmented LRU:** dùng vùng probationary và protected để tách trang mới khỏi trang có reuse.
- **ARC hoặc biến thể thích ứng:** cân bằng tín hiệu recency và frequency theo lịch sử workload.
- **Readahead/prefetch:** giảm latency khi đọc tuần tự, nhưng phải tính chi phí I/O, bandwidth và pollution.

Các chính sách trên có chi tiết cài đặt quan trọng. Không được mặc định chúng có cùng competitive ratio với LRU nếu chưa có chứng minh theo mô hình đã chọn.

### Vì sao scan khó cho LRU?

LRU chỉ nhìn **thời điểm truy cập cuối**, không biết trang mới X_i có được tái sử dụng hay không. Thấy một lần X_i mới hơn A, nó có thể giữ X_i và loại A dù A thật sự quan trọng hơn.

## 20. Write-through, write-back và dirty eviction

Trong cache lưu dữ liệu có thể bị sửa đổi, chính sách ghi ảnh hưởng chi phí tổng:

**Write-through:** ghi thay đổi xuống tầng dưới ngay theo chính sách đồng bộ đã định.

**Write-back:** giữ dữ liệu dirty trong cache và chỉ ghi về tầng dưới khi evict/flush hoặc theo một sự kiện khác.

**Write-allocate:** khi write miss, đưa block vào cache rồi cập nhật.

**No-write-allocate:** khi write miss, có thể chuyển thao tác ghi tới tầng dưới mà không cache block.

### Hệ quả với replacement

Nếu evict một trang dirty cần ghi lại dữ liệu, hai victims có cùng xác suất tái sử dụng có thể có chi phí evict khác nhau.

Trong mô hình unit miss, OPT “farthest next use” là tối ưu số miss. Trong mô hình dirty/writeback, cùng chính sách ấy **không nhất thiết tối ưu tổng I/O cost**.

Không thể so fault counts mà bỏ dirty writes rồi kết luận policy nào nhanh hơn về mặt wall-clock.

## 21. Kích thước mục khác nhau và các tầng cache

Mô hình k khung ngầm định **mọi trang chiếm một khung**. Trong object cache, kích thước mục có thể rất khác:

- Object A: 1 KB.
- Object B: 1 MB.
- Cache giới hạn: 2 MB.

Việc loại “một object” không tương đương giải phóng một frame. Chính sách phải xét **số byte**, admission, fragmentation và có thể cả hit cost.

Trong cache nhiều tầng L1/L2/L3 hoặc RAM/SSD/disk:

- Một miss ở tầng này có thể là hit ở tầng dưới.
- Policy từng tầng ảnh hưởng nhau.
- Các điều kiện inclusion/exclusion của hệ thống có thể khác stack property của LRU thuần túy.
- Mục tiêu toàn hệ thống có thể là latency, bandwidth, energy hoặc tail latency, không đơn thuần số miss.

Do đó **không chuyển nguyên kết quả lý thuyết paging đơn tầng sang hệ thống nhiều tầng** nếu chưa định nghĩa lại cost model.

## 22. Prefetching, dự đoán và tính trực tuyến

**Prefetching** tải trang trước khi có yêu cầu trực tiếp. Nếu dự đoán đúng, latency của request có thể giảm; nếu dự đoán sai, cache pollution và I/O tăng.

Một chính sách có dự đoán learned model vẫn là online theo nghĩa quyết định dựa trên thông tin đã có và dự báo không hoàn hảo. Nó **không phải OPT offline**, trừ khi biết chính xác toàn bộ future trace.

### Có thể tận dụng dự đoán trong competitive analysis?

Có các mô hình **learning-augmented online algorithms** đo lỗi dự đoán, độ vững khi dự đoán sai và cải thiện khi dự đoán đúng. Nhưng bảo đảm còn tùy định nghĩa chất lượng dự báo, khung so sánh và thuật toán cụ thể.

Không tự thay future thật bằng predicted nextUse rồi tuyên bố cận tối ưu Belady MIN còn đúng. Nếu dự báo sai, có thể evict nhầm trang.

## 23. Bảng so sánh chính sách

| Chính sách | Dữ liệu dùng khi chọn nạn nhân | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| FIFO | Thời điểm nạp | Đơn giản, overhead thấp | Bỏ qua hit gần đây; Belady anomaly |
| LRU | Thời điểm truy cập gần đây | Khai thác temporal locality; stack property | Scan pollution; cập nhật recency |
| OPT/MIN | Lần truy cập tiếp theo trong tương lai | Ít miss nhất offline trong mô hình chuẩn | Không thể dùng online khi future chưa biết |
| CLOCK | Reference bit và kim quét | Gần recency, overhead quản lý vừa phải | Không phải LRU chính xác; chi phí quét |
| LFU | Tần suất truy cập | Giữ trang phổ biến | Đếm lịch sử có thể lỗi thời; aging |
| 2Q/segmented | Recency qua nhiều vùng | Phân biệt trang mới và reuse | Nhiều tham số và trạng thái hơn |
| Random eviction | Ngẫu nhiên | Đơn giản ở một số cấu hình | Không tự có guarantee tốt |

### Chi phí mô phỏng trên n yêu cầu, k khung

**FIFO Java:** O(n) kỳ vọng, O(k) bộ nhớ phụ.

**LRU Java:** O(n) kỳ vọng, O(k) bộ nhớ phụ.

**OPT Java:** O(nk) kỳ vọng và O(n+k) bộ nhớ phụ nhờ tiền xử lý nextUse.

Đây là chi phí **implementation cụ thể**, không phải lower bound cho mọi cách mô phỏng chính sách. Nếu n=0 hoặc k=0, các hàm có đường xử lý riêng an toàn.

## 24. Ví dụ Java 17+: cùng trace, ba policy

Chương trình sau mô phỏng đúng mô hình **demand paging, equal-size pages, mỗi miss chi phí 1, cache bắt đầu trống**.

- **fifo:** dùng HashSet resident + ArrayDeque theo thứ tự nạp.
- **lru:** dùng LinkedHashMap với accessOrder=true để loại least-recently-used.
- **beladyOpt:** tiền xử lý nextUse bằng một lượt quét ngược; giữ future nextUse cho resident pages rồi evict trang có next use xa nhất.
- **show:** chạy cả ba trên cùng input và in số miss; kiểm tra bất biến offline OPT không thể tệ hơn một policy hợp lệ.
- **main:** 9 bộ kiểm thử, gồm anomaly, reuse, trang ID âm, k=0, input rỗng và cache lớn hơn số trang phân biệt; sau đó in đối chiếu Belady anomaly.

**Lưu tệp: OnlinePagingPoliciesDemo.java**

~~~java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class OnlinePagingPoliciesDemo {

    record Stats(int hits, int misses) {}

    static void validate(int[] requests, int capacity) {
        Objects.requireNonNull(requests, "requests");
        if (capacity < 0) {
            throw new IllegalArgumentException(
                    "capacity must be nonnegative");
        }
    }

    // FIFO: hits DO NOT change the loading order.
    // Expected O(n) time, O(k) extra memory.
    static Stats fifo(int[] requests, int capacity) {
        validate(requests, capacity);

        Set<Integer> resident = new HashSet<>();
        Deque<Integer> queue = new ArrayDeque<>();
        int misses = 0;

        for (int page : requests) {
            if (resident.contains(page)) {
                continue;
            }

            misses++;

            if (capacity == 0) {
                continue;
            }

            if (resident.size() == capacity) {
                int victim = queue.removeFirst();
                resident.remove(victim);
            }

            resident.add(page);
            queue.addLast(page);
        }

        return new Stats(requests.length - misses, misses);
    }

    // LRU: accessOrder=true means get() refreshes recency.
    // Expected O(n) time, O(k) extra memory.
    static Stats lru(int[] requests, int capacity) {
        validate(requests, capacity);

        LinkedHashMap<Integer, Boolean> cache =
                new LinkedHashMap<>(16, 0.75f, true);
        int misses = 0;

        for (int page : requests) {
            if (cache.get(page) != null) {
                continue;
            }

            misses++;

            if (capacity == 0) {
                continue;
            }

            if (cache.size() == capacity) {
                Iterator<Integer> iterator =
                        cache.keySet().iterator();
                iterator.next();
                iterator.remove();
            }

            cache.put(page, Boolean.TRUE);
        }

        return new Stats(requests.length - misses, misses);
    }

    // MIN/OPT: needs the ENTIRE future request sequence.
    // O(n*k) expected time, O(n+k) memory.
    static Stats beladyOpt(
            int[] requests, int capacity) {

        validate(requests, capacity);

        int n = requests.length;

        // nextUse[i]: next index j>i with same page,
        // or n when page is never requested again.
        int[] nextUse = new int[n];
        Map<Integer, Integer> nextPosition =
                new HashMap<>();

        for (int i = n - 1; i >= 0; i--) {
            int page = requests[i];
            nextUse[i] =
                    nextPosition.getOrDefault(page, n);
            nextPosition.put(page, i);
        }

        // Insertion order only fixes victim tie-breaking.
        Map<Integer, Integer> resident =
                new LinkedHashMap<>();

        int misses = 0;

        for (int i = 0; i < n; i++) {
            int page = requests[i];

            if (resident.containsKey(page)) {
                // Future index must change even after a hit.
                resident.put(page, nextUse[i]);
                continue;
            }

            misses++;

            if (capacity == 0) {
                continue;
            }

            if (resident.size() == capacity) {
                int victim = 0;
                int farthest = -1;

                for (Map.Entry<Integer, Integer> entry
                        : resident.entrySet()) {

                    if (entry.getValue() > farthest) {
                        farthest = entry.getValue();
                        victim = entry.getKey();
                    }
                }

                resident.remove(victim);
            }

            resident.put(page, nextUse[i]);
        }

        return new Stats(n - misses, misses);
    }

    static void show(
            String label, int[] requests, int capacity) {

        Stats fifoStats = fifo(requests, capacity);
        Stats lruStats = lru(requests, capacity);
        Stats optStats = beladyOpt(requests, capacity);

        if (optStats.misses() > fifoStats.misses()
                || optStats.misses() > lruStats.misses()) {
            throw new AssertionError(
                    "OPT cannot be worse than online");
        }

        System.out.println(
                label + " k=" + capacity
                + ": FIFO=" + fifoStats.misses()
                + ", LRU=" + lruStats.misses()
                + ", OPT=" + optStats.misses()
                + ", requests=" + requests.length);
    }

    public static void main(String[] args) {

        int[] classic = {
                1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5
        };

        int[] repeated = {
                1, 2, 1, 3, 1, 2, 4, 1, 2
        };

        show("Belady", classic, 3);
        show("Belady", classic, 4);

        show("Repeated", repeated, 2);
        show("Repeated", repeated, 3);

        show("Negative IDs",
                new int[] {-1, 0, -1, 2, -1, 0}, 2);

        show("Single page", new int[] {7, 7, 7, 7}, 1);

        show("Zero frames", repeated, 0);
        show("Empty", new int[] {}, 3);
        show("Roomy", repeated, 10);

        int fifo3 = fifo(classic, 3).misses();
        int fifo4 = fifo(classic, 4).misses();
        int lru3 = lru(classic, 3).misses();
        int lru4 = lru(classic, 4).misses();

        if (fifo3 != 9 || fifo4 != 10
                || lru3 != 10 || lru4 != 8) {
            throw new AssertionError(
                    "Unexpected Belady demonstration");
        }

        System.out.println(
                "Belady anomaly: FIFO(3)=" + fifo3
                + ", FIFO(4)=" + fifo4);

        System.out.println(
                "LRU monotonic example: LRU(3)=" + lru3
                + ", LRU(4)=" + lru4);
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 OnlinePagingPoliciesDemo.java
java OnlinePagingPoliciesDemo
~~~

**Đầu ra mẫu chính xác theo trace:**

~~~text
Belady k=3: FIFO=9, LRU=10, OPT=7, requests=12
Belady k=4: FIFO=10, LRU=8, OPT=6, requests=12
Repeated k=2: FIFO=8, LRU=7, OPT=6, requests=9
Repeated k=3: FIFO=6, LRU=4, OPT=4, requests=9
Negative IDs k=2: FIFO=5, LRU=4, OPT=4, requests=6
Single page k=1: FIFO=1, LRU=1, OPT=1, requests=4
Zero frames k=0: FIFO=9, LRU=9, OPT=9, requests=9
Empty k=3: FIFO=0, LRU=0, OPT=0, requests=0
Roomy k=10: FIFO=4, LRU=4, OPT=4, requests=9
Belady anomaly: FIFO(3)=9, FIFO(4)=10
LRU monotonic example: LRU(3)=10, LRU(4)=8
~~~

### Tại sao mã xử lý hit của OPT khác FIFO?

OPT phải cập nhật **thời điểm xuất hiện kế tiếp** của trang resident mỗi khi trang đó được truy cập, kể cả hit. Nếu cache đang giữ p và ta vừa truy cập p ở vị trí i, một nextUse cũ có thể trỏ tới i, không còn là future; không cập nhật sẽ dẫn đến chọn victim sai.

FIFO không thay đổi thứ tự nạp khi hit. LRU thì cập nhật access order khi hit. **Ba chính sách có state transitions khác nhau dù cùng dùng map/set.**

### Tie-breaking trong OPT

Nếu nhiều trang không xuất hiện lại nữa, tất cả có nextUse=n. Evict bất kỳ trang nào trong nhóm ấy vẫn đạt số miss tối ưu cho đoạn còn lại. Chương trình chọn trang gặp trước khi duyệt LinkedHashMap để kết quả deterministic.

### Cache dung lượng 0

Với k=0, không có nơi chứa trang. Mọi request là miss, kể cả lặp lại cùng page. Đây là một **quy ước mô phỏng hợp lý** để test biên; trong một hệ thống thật, “không có RAM frames” có thể khiến tiến trình không thể phục vụ request, và cần đặc tả hành vi khác.

### Trang ID âm có hợp lệ không?

Ở đây page IDs chỉ là các **nhãn int**. Nhãn âm không có ý nghĩa bộ nhớ thật, nhưng là input hợp lệ của **bộ mô phỏng tổng quát**, giúp kiểm tra code không phụ thuộc vào việc page IDs luôn dương.

## 25. Kiểm chứng OPT bằng quy hoạch động vét cạn

Bởi OPT là một chuẩn offline rất quan trọng, cần kiểm tra rằng chính implementation Belady thực sự đạt **số miss tối thiểu**.

Với trace nhỏ, có thể dùng oracle độc lập:

**DP(i,C)** = số miss tối thiểu để phục vụ suffix từ vị trí i khi cache hiện tại chứa tập trang C.

Các trường hợp:

1. Nếu i=n: **DP(i,C)=0**.
2. Nếu pᵢ∈C: **DP(i,C)=DP(i+1,C)**.
3. Nếu pᵢ∉C và |C|<k: **DP(i,C)=1+DP(i+1,C∪{pᵢ})**.
4. Nếu pᵢ∉C và |C|=k>0:
   
   **DP(i,C)=1+min_{q∈C} DP(i+1,(C\\{q})∪{pᵢ})**.

5. Nếu k=0: **DP(i,∅)=n−i**.

Oracle thử mọi victim ở mỗi miss, lưu memo theo (i, tập C) và trả giá trị thấp nhất.

### Vì sao độc lập?

Belady greedily loại trang có future next-use xa nhất. DP **không dùng quy tắc này**; nó thử **tất cả lựa chọn victim**. Vì vậy việc hai kết quả khớp trên nhiều trace ngắn có giá trị kiểm thử cao hơn so với việc copy lại cùng một greedy rule.

### Độ phức tạp oracle

Số trạng thái cache có thể tăng theo tổ hợp số trang và capacity, nên DP là một oracle **đắt trên input lớn**. Chỉ chạy trên trace ngắn với ít page IDs.

Bản Java demo không gọi oracle này trong luồng xử lý thông thường; có thể triển khai test harness riêng để đối chiếu trên random cases.

## 26. Kiểm thử ngẫu nhiên và metamorphic testing

Một bộ test tốt cần bao gồm:

- Chuỗi rỗng.
- Cache k=0, k=1, k lớn hơn số trang phân biệt.
- Một trang lặp nhiều lần.
- ID âm, ID bằng Integer.MIN_VALUE/Integer.MAX_VALUE.
- Hai hoặc nhiều trang luân phiên.
- Chuỗi có vòng lặp dài hơn capacity.
- Trace Belady anomaly cổ điển.
- Những đợt chuyển phase nóng/lạnh.
- Trace từ tập 4–6 page IDs và độ dài 5–12 để so OPT với DP vét cạn.

### Bất biến chung

Với cùng request list và k:

**0≤misses≤n**.

**hits+misses=n**.

**misses_OPT≤misses_FIFO**.

**misses_OPT≤misses_LRU**.

Nếu cache ban đầu trống và k ít nhất bằng số trang phân biệt của trace:

**misses=number of distinct pages** với cả ba chính sách.

Nếu k=0:

**misses=n**.

### Metamorphic properties

**Đổi tên trang bằng một song ánh:** số miss không đổi với FIFO/LRU/OPT, vì algorithm chỉ so page IDs để phân biệt.

**Tăng capacity LRU:** miss không được tăng cho cùng trace.

**Tăng capacity OPT:** miss tối ưu không được tăng.

**Tăng capacity FIFO:** **không có** tính chất trên, như Belady anomaly đã chứng minh.

**Thêm một yêu cầu trùng đúng trang vừa yêu cầu:** đối với k>0 trong demand paging, yêu cầu được thêm có thể là hit nếu không có eviction khác xen vào, nhưng nó vẫn có thể làm thay đổi recency của LRU và do đó ảnh hưởng các miss về sau. Không khẳng định tổng miss của mọi suffix không đổi.

### Không lấy random test làm chứng minh

Random test có thể phát hiện bug trong mô phỏng, nhưng chỉ **chứng minh trao đổi** mới giải thích Belady OPT đúng với mọi trace thuộc mô hình. Tương tự, một nghìn trace không có anomaly không chứng minh FIFO tránh anomaly.

## 27. Đo cache bằng trace replay và benchmark

Để so các policy trong thực tế:

1. Ghi lại chuỗi truy cập ở cùng granularity: page/block/object.
2. Xác định cold-start hay warm-start; có hay không prefetch.
3. Chạy mọi policy trên **cùng trace** và **cùng capacity**.
4. Báo misses, hits, miss rate.
5. Nếu có dirty/write-back, báo thêm số lần ghi, số bytes ghi và chi phí I/O.
6. Khi cache nhiều tầng, đo hit/miss của từng tầng và end-to-end latency.
7. Xem các workload theo pha, quét tuần tự, burst, vòng lặp và phân phối khóa.
8. Tính chi phí điều khiển chính sách: cấu trúc dữ liệu, đồng bộ, contention, GC.
9. Thử capacity khác nhau; riêng FIFO không mặc định miss count đơn điệu.
10. Nếu dùng OPT offline, ghi rõ đây là **baseline biết tương lai**, không phải một policy có thể deploy trực tiếp.

### Cẩn thận với trace sampling

Nếu lấy mẫu chỉ một phần truy cập, chuỗi sampled không nhất thiết giữ nguyên temporal locality và working-set size. Một policy có thể trông tốt hơn trong trace sample nhưng tệ hơn trên toàn workload.

Nếu trace chứa request có kích thước và thời gian phục vụ khác nhau, miss count đơn thuần chưa đủ đánh giá hiệu quả. Cần thêm **cost-weighted metrics**.

## 28. Lựa chọn chiến lược cho hệ thống thực

**Chọn FIFO** nếu cần đơn giản, overhead thấp, số miss không quá nhạy hoặc workload không có mô hình reuse rõ. Tuy nhiên hãy thử anomaly và kiểm tra SLA.

**Chọn LRU** khi temporal locality mạnh, cache metadata đủ để cập nhật access order, và workload không quá nhạy với scan pollution.

**Chọn CLOCK** khi muốn khai thác reference bit và giảm chi phí quản lý thứ tự LRU chính xác trong thiết kế phù hợp.

**Chọn LFU có aging** khi popularity ổn định nhưng vẫn cần thích ứng với thay đổi theo thời gian; phải xác định cửa sổ và xử lý counter.

**Chọn policy có probation/protected segments** khi cần bảo vệ hot set khỏi những lần scan hoặc request một lần.

**Dùng OPT** cho **đánh giá offline trên log đã biết**, không để ra quyết định online trong production.

### Không có policy “tốt nhất” độc lập workload

Một policy tối ưu về số miss trên log A có thể không tối ưu về latency trên log B. Một lựa chọn đúng cần dựa trên:

- Dung lượng và kích thước mục.
- Pattern truy cập.
- Chi phí hit/miss/writeback.
- Độ trễ tail và SLA.
- Khả năng cập nhật metadata đồng thời.
- Ưu tiên CPU/RAM/I/O.
- Độ ổn định khi workload chuyển phase.

## 29. Lỗi thường gặp khi học và cài đặt

1. **Nhầm FIFO với LRU:** hit FIFO không đổi vị trí hàng đợi.
2. **Gọi OPT là thuật toán online:** thực tế cần biết tương lai.
3. **Evict trang được dùng sớm nhất trong OPT:** phải chọn dùng lại xa nhất.
4. **Không ưu tiên trang không bao giờ dùng lại:** future next use phải được coi là +∞.
5. **Quên cập nhật nextUse của trang OPT trên hit:** giữ stale future index.
6. **Không kiểm tra cache đã đầy trước khi evict:** bỏ trang khi còn slot trống.
7. **Đếm một hit như miss chỉ vì trang được tải trước đó:** miss chỉ xảy ra khi không resident tại thời điểm yêu cầu.
8. **Không giới hạn số trang resident≤k:** mô phỏng cho kết quả sai.
9. **Bỏ xử lý k=0:** lỗi queue.removeFirst hoặc iterator trên map rỗng.
10. **Lấy hitRate=hits/0 trên trace rỗng:** không có ý nghĩa.
11. **Không xác định cache khởi đầu trống hay ấm:** miss count khác nhau.
12. **Dùng FIFO queue mà thêm lại page khi hit:** vô tình biến nó thành policy khác.
13. **Dùng LinkedHashMap accessOrder=false cho LRU:** chỉ có insertion order, không phải LRU.
14. **Dùng cache.get rồi không kiểm tra null/giá trị trả về đúng:** hit detection sai nếu map lưu null.
15. **Cho rằng FIFO không có Belady anomaly:** ví dụ 12 phần tử chứng minh điều ngược lại.
16. **Cho rằng LRU luôn ít miss hơn FIFO trên mọi trace:** trace k=3 cho LRU 10, FIFO 9.
17. **Cho rằng tăng k luôn giảm miss cho mọi policy:** sai với FIFO.
18. **Nhầm stack property của LRU với yêu cầu cache “dùng stack” trong code:** đây là inclusion của tập resident khi so capacities.
19. **Đo một trace rồi suy ra competitive ratio worst-case:** không đủ.
20. **Quên additive constant trong competitive analysis:** phát biểu c·OPT có thể thiếu điều kiện khởi tạo.
21. **Áp dụng cận k-competitive cho k=0 hoặc weighted cache:** thiếu giả thiết.
22. **Lấy randomized marking bound gắn cho random victim eviction:** hai thuật toán khác nhau.
23. **Không nói loại adversary khi dùng expected bound:** có thể sai mệnh đề.
24. **Dùng CLOCK mà coi bit=1 nghĩa là trang được truy cập mới nhất:** reference bit chỉ lưu một thông tin thô.
25. **Dùng LFU không aging rồi mặc định thích ứng tốt mọi phase:** counter cũ gây pollution.
26. **Chỉ báo số miss mà không báo dirty writeback:** chưa đo toàn bộ cost.
27. **Dùng mô hình same-size pages cho cache object kích thước khác nhau:** chọn victim có thể không giải phóng đủ bytes.
28. **Nhầm demand paging với prefetching:** chính sách admission và số I/O có thể khác.
29. **Nhầm cache hit tầng RAM với TLB hit:** hai lớp lưu đệm khác nhau.
30. **Dùng cache k=10 rồi cho rằng có thể giữ 10 trang trùng ID:** capacity tính trang phân biệt.
31. **Gọi số miss OPT là cận trên:** đó là lower bound cho miss của các policy hợp lệ.
32. **Dùng Belady MIN để đánh giá cost-weighted misses mà không chứng minh:** không còn guaranteed optimum.
33. **Không đọc toàn bộ prefix trong phép kiểm tra online:** policy có thể vô tình nhìn future.
34. **Không thử input trang âm hoặc ID cực trị:** có thể phát hiện code dùng ID làm chỉ số mảng sai.
35. **Coi O(nk) chi phí mô phỏng OPT là độ phức tạp của mọi chính sách online:** hai bài toán khác nhau.
36. **Tuyên bố HashMap operations worst-case O(1) vô điều kiện:** phải phân biệt expected và worst-case.
37. **Nhầm cold misses và capacity misses:** chẩn đoán sai nguyên nhân.
38. **Đếm một trang xuất hiện nhiều lần là nhiều mục resident:** cache lưu theo key phân biệt.
39. **Không tách chính sách evict và policy admission:** một số cache không nhất thiết cache mọi miss.
40. **Không kiểm tra feasibility trước khi so với OPT:** một policy giữ quá k trang có thể có misses thấp “ảo”.
41. **Nhầm kết quả Java mô phỏng chính sách với behavior của một OS kernel cụ thể:** mỗi kernel có nhiều tầng và biến thể.
42. **Đánh giá cache chỉ bằng asymptotic CPU complexity:** overhead metadata, lock và tail latency cũng quan trọng.

## 30. Bài tập tự luyện kèm đáp án

**Câu 1.** Online paging khác offline paging ở điểm nào?  
**Đáp án:** Online không biết chính xác future requests; offline có thể xem toàn bộ trace.

**Câu 2.** Khi FIFO hit, thứ tự queue thay đổi không?  
**Đáp án:** Không.

**Câu 3.** Khi LRU hit, điều gì đổi?  
**Đáp án:** Trang đó trở thành mới nhất theo thời gian truy cập.

**Câu 4.** OPT evict trang nào khi cache đầy?  
**Đáp án:** Trang có lần truy cập tiếp theo xa nhất hoặc không bao giờ dùng lại.

**Câu 5.** Với trace Belady kinh điển, FIFO k=3 và k=4 có mấy miss?  
**Đáp án:** 9 và 10.

**Câu 6.** Với cùng trace, LRU k=3 và k=4 có mấy miss?  
**Đáp án:** 10 và 8.

**Câu 7.** OPT k=3 và k=4 trên trace ấy?  
**Đáp án:** 7 và 6.

**Câu 8.** Belady's anomaly là gì?  
**Đáp án:** Với cùng policy/trace, tăng số frames lại làm tăng misses; ví dụ FIFO 9→10.

**Câu 9.** LRU có anomaly dạng này không?  
**Đáp án:** Không trong mô hình chuẩn, nhờ stack/inclusion property.

**Câu 10.** Nếu k=0 và có 100 yêu cầu?  
**Đáp án:** Mô phỏng demand-paging định nghĩa mỗi yêu cầu là miss, tổng 100.

**Câu 11.** Nếu k đủ chứa mọi trang phân biệt và cold-start?  
**Đáp án:** Mỗi trang phân biệt miss lần đầu đúng một lần, còn lại hit.

**Câu 12.** Vì sao OPT không thể là một policy online thực thi trực tiếp?  
**Đáp án:** Nó cần biết future next-use của trang resident.

**Câu 13.** Một trace cho FIFO=10, OPT=5; ratio thực nghiệm?  
**Đáp án:** 2, nhưng không phải tự động là competitive ratio worst-case.

**Câu 14.** Competitive analysis dùng bất đẳng thức nào?  
**Đáp án:** F_A(σ)≤c·F_OPT(σ)+b trên mọi trace hợp lệ.

**Câu 15.** LRU k-competitive có nghĩa LRU luôn fault đúng k lần OPT?  
**Đáp án:** Không, đó là cận trên có additive constant, có thể tốt hơn nhiều.

**Câu 16.** CLOCK có cùng thứ tự LRU chính xác không?  
**Đáp án:** Không, dùng reference bits và kim quét để xấp xỉ.

**Câu 17.** Vì sao LFU có thể kém khi workload đổi phase?  
**Đáp án:** Trang từng hot có counter cao nhưng nay lạnh vẫn được giữ nếu không aging.

**Câu 18.** Chi phí của OPT simulator tiền xử lý nextUse và scan k trang?  
**Đáp án:** O(nk) kỳ vọng thời gian, O(n+k) bộ nhớ.

**Câu 19.** Khi object có kích thước khác nhau, Belady MIN chắc tối ưu tổng chi phí không?  
**Đáp án:** Không; chứng minh cơ bản yêu cầu các trang cùng kích thước và miss cùng chi phí.

**Câu 20.** Nếu cache có dirty writes, chỉ so miss counts đã đủ chưa?  
**Đáp án:** Chưa; phải xét writebacks và cost/lateness.

**Câu 21.** Vì sao một scan dài gây pollution cho LRU?  
**Đáp án:** Trang mới được truy cập gần đây thay thế các trang hot cũ chưa kịp tái dùng.

**Câu 22.** Với trace rỗng, hit rate được tính thế nào?  
**Đáp án:** Không chia cho 0; báo không áp dụng hoặc quy ước rõ.

**Câu 23.** Nếu OPT=0 thì tỷ số faults_A/OPT có nghĩa không?  
**Đáp án:** Không; báo counts hoặc dùng bất đẳng thức competitive với additive b.

**Câu 24.** Có thể dùng DP thử mọi victim làm oracle OPT cho n nhỏ không?  
**Đáp án:** Có; nó độc lập với quy tắc farthest-next-use.

**Câu 25.** Cache K+1 của LRU có luôn chứa mọi trang của cache K không?  
**Đáp án:** Có với cùng trace và cold-start; đó là stack property.

## 31. Checklist và kết luận

Trước khi lựa chọn/chứng minh một chính sách thay trang:

1. **Định nghĩa request sequence** và đơn vị trang/block/object.
2. **Nêu capacity k**, cache ban đầu và xử lý k=0.
3. **Xác định mục tiêu:** misses, I/O bytes, latency, dirty writes hay energy.
4. **Nêu miss cost có đồng nhất không**, page sizes có giống nhau không.
5. **Phân biệt online và offline**: thuật toán online không được xem future.
6. **Kiểm tra quy tắc hit:** FIFO không đổi order; LRU có refresh.
7. **Kiểm tra quy tắc OPT:** evict farthest future next use.
8. **Duy trì cache size≤k** trong mọi bước.
9. **Đo cùng trace/cùng trạng thái ban đầu** trước khi so policies.
10. **Thử trace Belady anomaly**, không mặc định FIFO monotonic theo capacity.
11. **Khai thác LRU stack property** khi phân tích nhiều capacities.
12. **Dùng OPT làm baseline lower bound** nhưng không tuyên bố có thể deploy online.
13. **Nếu dùng competitive analysis**, nêu k, additive constant, adversary model.
14. **Nếu có randomness**, phân biệt expected và high-probability guarantee.
15. **Nếu có phase changes/scans**, đánh giá LFU aging và admission/protected segments.
16. **Nếu dirty data**, đếm writeback và flush costs.
17. **Nếu variable object sizes**, đánh giá theo bytes, không chỉ số object.
18. **Nếu prefetch**, phân tích thêm bandwidth/pollution và đừng áp dụng thẳng proof MIN.
19. **Nếu benchmark**, tránh trộn các traces hoặc lấy input sampling sai.
20. **Nếu QA**, dùng DP/exhaustive offline oracle cho trace ngắn, test invariant và metamorphic properties.
21. **Kiểm tra input rỗng, k=0, k lớn, IDs âm và lặp lại**.
22. **Báo time/space đúng implementation**, phân biệt O(n) expected của hash và O(nk) OPT simulation.
23. **Nói rõ giới hạn mô hình**, không coi một policy đơn giản là đầy đủ hành vi của operating system.
24. **Chọn policy dựa trên workload và chi phí thực**, không chỉ một bảng miss counts.

**Kết luận:** thay trang là một bài toán quyết định **trực tuyến** dưới giới hạn dung lượng. FIFO dùng lịch sử **nạp vào**, LRU dùng lịch sử **truy cập**, còn Belady OPT dùng **tương lai** và tạo chuẩn lý tưởng thấp nhất về số miss. Belady's anomaly nhắc rằng tăng cache không bảo đảm giảm miss với mọi policy, trong khi stack property giải thích sự đơn điệu của LRU. Khi sang hệ thống thực, cần đánh giá thêm locality, biến đổi workload, admission, prefetch, dirty writes và chi phí nhiều tầng trước khi chọn chiến lược lưu đệm.
