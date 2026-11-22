# Tỷ số cạnh tranh và lời giải biết trước toàn bộ đầu vào

**Tỷ số cạnh tranh (competitive ratio)** là thước đo chất lượng của **thuật toán trực tuyến (online algorithm)** khi so với một **lời giải offline tối ưu** được quyền **biết trước toàn bộ chuỗi đầu vào**. Một thuật toán online phải ra quyết định ngay khi sự kiện xuất hiện, chỉ biết quá khứ và hiện tại; offline có thể xem toàn bộ tương lai nhưng **vẫn phải tuân thủ đúng những ràng buộc, giá cả và tài nguyên như online**.

Bài học thuộc nhóm **Trực tuyến và luồng** trong Computer Science Algorithms. Các phần trọng tâm gồm mô hình online/offline, định nghĩa tỷ số cạnh tranh cho bài MIN và MAX, hằng số cộng và trường hợp OPT=0, adversary và các bảo đảm ngẫu nhiên, ba ví dụ có chứng minh là **Ski Rental**, **LRU Paging so với Belady offline**, **Online List Scheduling**, chương trình Java 17+ chạy độc lập, oracle vét cạn để đối chiếu offline OPT, độ phức tạp, phản ví dụ và bài tập có lời giải.

## 1. Thuật toán trực tuyến là gì?

Một input được tiết lộ lần lượt dưới dạng chuỗi:

`σ=(r₁,r₂,…,r_T)`.

Tại bước t, online được dùng tiền tố `r₁,…,r_t`, trạng thái sau những quyết định trước và các tham số được công bố trước. Nó **không được dùng** các yêu cầu chưa tới `r_(t+1),…,r_T`, trừ khi đề bài chủ động cho một mức nhìn trước.

**Ví dụ:**

- Ski Rental: hôm nay thuê hay mua đồ, chưa biết còn bao nhiêu ngày sử dụng.
- Paging: cache đầy thì đuổi trang nào, chưa biết trang nào sẽ được truy cập tiếp.
- Scheduling: công việc mới tới thì đưa vào máy nào, chưa biết các công việc sau.

Các quyết định có thể không thể thu hồi: tiền mua đã trả, trang đã bị đuổi, job đã được giao vào máy. Mức thiệt hại vì không biết tương lai là đối tượng phân tích của tỷ số cạnh tranh.

### Offline không có nghĩa là được gian lận

Trong Ski Rental, offline vẫn trả B khi mua và 1 cho mỗi ngày thuê. Trong Paging, offline vẫn có k ô cache, phải trả fault khi nạp trang ngoài cache. Trong Scheduling, offline vẫn chỉ có m máy giống nhau và không được chia một job ra nhiều máy.

**Khác biệt duy nhất về tri thức** là offline được xem toàn bộ σ trước khi đưa ra quyết định. Nếu offline được thêm máy, thêm cache hoặc được bỏ qua yêu cầu khó, đó là một **mô hình khác** (chẳng hạn resource augmentation), phải phát biểu và chứng minh lại.

## 2. Giá trị tối ưu offline OPT

Cho tập các kế hoạch khả thi trên toàn chuỗi là `F(σ)`.

Với bài **tối thiểu hóa chi phí**:

`OPT(σ)=min_{S∈F(σ)} cost(S,σ)`.

Với bài **tối đa hóa lợi ích**:

`OPT(σ)=max_{S∈F(σ)} value(S,σ)`.

Nếu online A cũng tạo được kế hoạch khả thi trên **chính σ**, thì:

- Bài MIN: `A(σ)≥OPT(σ)`.
- Bài MAX: `A(σ)≤OPT(σ)`.

**Nghiệm khả thi phải được kiểm tra trước khi tính tỷ số.** Một thuật toán bỏ sót request có thể trả chi phí thấp hơn OPT vì nó đang không giải đúng bài. Một trình giải offline heuristic cũng không được tự gắn nhãn OPT nếu chưa có chứng nhận tối ưu.

## 3. Định nghĩa tỷ số cạnh tranh cho bài MIN

Giả sử chi phí không âm. Thuật toán A được gọi là **c-competitive** nếu tồn tại `c≥1` và một hằng số `β≥0` độc lập với độ dài và nội dung σ sao cho:

`A(σ)≤c·OPT(σ)+β`

với **mọi chuỗi σ hợp lệ** trong mô hình.

Nếu β=0, gọi là **strictly c-competitive**:

`A(σ)≤c·OPT(σ)`.

Với OPT>0, ta có thể diễn giải dưới dạng:

`A(σ)/OPT(σ)≤c`.

**Tỷ số quan sát trên một input** là A/OPT của input đó; nó không nhất thiết bằng c. Một thuật toán có chứng minh 2-competitive có thể đạt ratio=1 trên rất nhiều chuỗi.

### Vai trò của hằng số cộng

Từ `A≤2OPT+10`, không thể tự bỏ 10 để nói `A≤2OPT`. Chẳng hạn khi OPT=1, vế phải của cận ban đầu là 12. Trong nhiều bài có chi phí khởi tạo, người ta dùng **asymptotic competitive ratio** với additive constant, nhưng phải công bố β.

Nếu β phụ thuộc kích thước cache k mà không phụ thuộc độ dài T của chuỗi, phải ghi rõ đang xem k là tham số mô hình cố định. Không nên nói β là hằng số tuyệt đối nếu thực tế β=k có thể lớn khi k thay đổi.

### OPT bằng 0

Khi σ rỗng, có thể A=OPT=0. Phép chia `0/0` **không xác định**; vẫn kiểm tra được bất đẳng thức cạnh tranh bằng phép nhân, nhưng không tự gán ratio=1 hoặc 0. Chương trình Java sẽ in `ratio=undefined`.

### Khi mục tiêu âm

Multiplicative ratio thường giả định chi phí không âm. Nếu OPT=−10 và A=−9 trong bài MIN, hai giá trị rất gần nhau nhưng điều kiện A≤2OPT biến thành −9≤−20, vô lý. Khi chi phí/lợi ích có thể âm, cần chuẩn hóa, chọn sai số cộng hoặc một định nghĩa cạnh tranh thích hợp.

## 4. Định nghĩa cho bài MAX

Với lợi ích không âm, online có `A≤OPT`. Một cách biểu diễn là:

`A(σ)≥OPT(σ)/c−β`,

với c≥1. Trong trường hợp strict, có thể đặt `γ=1/c∈(0,1]`:

`A(σ)≥γ·OPT(σ)`.

Ví dụ γ=0.8 nghĩa là thuật toán đạt **ít nhất 80%** lợi ích offline trên mọi chuỗi trong phạm vi định lý; tương đương c=1.25. Tỷ lệ γ càng gần 1 càng tốt, còn c của cả MIN và MAX càng gần 1 càng tốt.

Không dùng bất đẳng thức `A≤cOPT` của bài MIN cho MAX một cách máy móc. Trong bài MAX, offline OPT là **giới hạn trên** của mọi kế hoạch khả thi.

## 5. Competitive analysis khác gì approximation và regret?

| Phương pháp | Comparator | Trọng tâm |
| --- | --- | --- |
| Competitive analysis | Offline OPT nhìn **toàn bộ chuỗi** | Ra quyết định khi thiếu thông tin tương lai |
| Approximation analysis | OPT của một instance tối ưu | Chấp nhận gần tối ưu khi giải exact khó |
| Regret analysis | Comparator tốt nhất trong **một lớp chính sách/hành động** sau khi nhìn dữ liệu | Học qua chuỗi lượt |
| Benchmark | Các input được thử thực nghiệm | Mô tả chất lượng trên tập kiểm thử |

**Regret thấp** so với hành động cố định tốt nhất trong hindsight không tự suy ra cạnh tranh tốt so với một offline schedule được phép thay đổi theo toàn bộ chuỗi.

Thử 100 input mà ratio đều thấp hơn 1.3 cũng **không chứng minh** tỷ số cạnh tranh tệ nhất là 1.3. Cần một chứng minh cho **mọi** chuỗi thuộc mô hình.

## 6. Adversary, upper bound và lower bound

**Upper bound:** chứng minh một thuật toán cụ thể A thỏa `A≤cOPT+β` với mọi σ.

**Lower bound:** chứng minh **với mọi thuật toán A** trong một lớp, **tồn tại** chuỗi σ buộc A có tỷ số ít nhất một cận nhất định.

Thứ tự lượng từ `∀A∃σ` rất quan trọng: một chuỗi làm thuật toán A₁ xấu chưa chắc cũng làm thuật toán A₂ xấu. Khi thiết kế chuỗi, adversary có thể tận dụng quy tắc quyết định đã biết của một thuật toán xác định.

Với thuật toán ngẫu nhiên:

- **Oblivious adversary** chọn σ trước và độc lập với random bits của A; một bound thường có dạng `E[A(σ)]≤cOPT(σ)+β`.
- **Adaptive adversary** có thể chọn yêu cầu tiếp theo dựa trên quá trình đã quan sát; cần xác định rõ comparator và phạm vi bảo đảm.
- Bound **theo kỳ vọng** khác bound **với xác suất cao** và khác bound cho **mọi seed**.

Không lấy một vài seed đẹp làm chứng minh kỳ vọng.

## 7. Ski Rental: thuê hay mua mà không biết mùa dài bao lâu

### Mô hình

Mỗi ngày cần sử dụng đồ: **thuê giá 1** cho ngày đó hoặc **mua đứt một lần với giá nguyên B≥1**, dùng miễn phí kể từ ngày mua. Mùa kéo dài D≥0 ngày nhưng online không biết trước D. Không có giá bán lại hay phí phụ.

### Mốc offline

Biết trước D, offline có thể thuê D ngày hoặc mua ngay từ ngày đầu. Thuê vài ngày rồi mua không rẻ hơn mua ngay khi D đã biết.

`OPT(D)=min(D,B)`.

### Thuật toán trực tuyến break-even

**Thuê trong B−1 ngày đầu. Nếu ngày B thực sự tới, mua vào đầu ngày B.**

Chính sách chỉ dùng chỉ số ngày hiện tại và B, không cần biết D.

`A(D)=D` nếu `D<B`,

`A(D)=2B−1` nếu `D≥B`.

Nếu D=0, A=OPT=0. Nếu 0<D<B, A=OPT=D và ratio=1. Nếu D≥B:

`A/OPT=(2B−1)/B=2−1/B`.

Do đó với mọi D:

`A(D)≤(2−1/B)·OPT(D)`.

Đây là **strict competitive guarantee**. Khi B=5, c=1.8; khi B=1, mua ngay ngày đầu nếu cần và c=1. Khi B tăng lớn, c tiến gần 2 từ phía dưới.

| B | D | Online hành động | A | OPT | Ratio |
| ---: | ---: | --- | ---: | ---: | ---: |
| 5 | 0 | Không có ngày nào | 0 | 0 | Không xác định |
| 5 | 4 | Thuê bốn ngày | 4 | 4 | 1 |
| 5 | 5 | Thuê bốn ngày, mua ngày năm | 9 | 5 | 1.8 |
| 5 | 8 | Thuê bốn ngày rồi mua | 9 | 5 | 1.8 |
| 1 | 1 | Mua ngay | 1 | 1 | 1 |

### Cận dưới deterministic: vì sao break-even tối ưu?

Một chính sách xác định sẽ mua vào một ngày t nếu mùa còn kéo dài, hoặc không bao giờ mua.

- Nếu 1≤t≤B, adversary cho D=t. Online trả t−1+B, offline trả t; ratio = `1+(B−1)/t≥2−1/B`.
- Nếu t>B, adversary cũng cho D=t. Online trả t−1+B, offline B; ratio≥2≥2−1/B.
- Nếu không bao giờ mua, cho D tăng không giới hạn; online=D còn OPT=B, nên ratio tăng vô hạn.

Do chính sách break-even đã đạt cận 2−1/B, đây là tỷ số tối ưu **trong mô hình nguyên và deterministic đã định nghĩa**. Kết luận không tự áp cho randomized ski rental.

### Hai chính sách yếu

**Luôn thuê:** ratio D/B không bị chặn khi D rất lớn. **Mua ngay:** nếu D=1 thì ratio=B; nó có cận hữu hạn với B cố định, nhưng **không có một hằng số thống nhất độc lập với B** nếu B là tham số đầu vào được phép tăng.

### Lỗi lệch một ngày

Nếu mua **đầu ngày B** thì không phải thuê ngày B nữa. Chi phí là B−1+B=2B−1, **không phải 2B**. Nếu thay quy tắc mua cuối ngày, toàn bộ công thức phải đổi.

## 8. Paging: LRU online so với Belady offline

### Mô hình

Cache chứa tối đa k≥1 trang, **ban đầu rỗng**, mỗi request là một trang. Hit tốn 0, miss (**page fault**) tốn 1 và phải nạp trang. Nếu cache đầy, phải đuổi một trang. Không cho prefetch miễn phí. Online và offline có **cùng k và cùng chuỗi request**.

### LRU chỉ nhìn quá khứ

**Least Recently Used** đuổi trang được dùng xa nhất về **quá khứ**. Khi hit, thứ tự sử dụng gần đây phải cập nhật; chỉ cập nhật khi miss là cài đặt sai LRU.

### Belady/MIN nhìn toàn bộ tương lai

Khi phải đuổi trang, **Belady chọn trang có lần sử dụng tiếp theo xa nhất trong tương lai**, hoặc không bao giờ dùng lại. Trong mô hình demand paging với fault cost đồng nhất, Belady là **offline optimum**.

Lập luận tối ưu bằng **exchange argument**: nếu offline đuổi một trang cần sớm hơn trong khi có một trang cần muộn hơn, có thể hoán đổi lựa chọn đuổi với lịch tương lai mà không tăng faults; lặp lại thu được quy tắc Belady.

Belady **không phải thuật toán online** vì cần hậu tố request.

### Ví dụ k=2

Chuỗi `[1,2,3,1,2,3]`.

LRU miss ở **cả sáu yêu cầu**, vì sau hai trang đầu, mỗi trang sắp dùng đã bị đuổi.

Belady nạp 1, nạp 2, khi 3 tới thì đuổi 2 vì 2 được dùng muộn hơn 1. Yêu cầu 1 là hit; yêu cầu 2 tiếp theo là miss và có thể đuổi 1; yêu cầu 3 cuối là hit. Tổng **Belady=4**, còn LRU=6.

Ratio thực tế: `6/4=1.5`.

### Bảo đảm LRU

Trong mô hình chuẩn, LRU có:

`LRU(σ)≤k·OPT(σ)+k`.

Đây là **k-competitive với additive constant k**; không được tự lược hằng số cộng để tuyên bố strict ratio. Với k=1, LRU và offline buộc có cùng hành vi: cache chỉ giữ một trang.

## 9. Chứng minh cận LRU qua thế năng

Xếp các trang LRU cache theo rank:

- Rank 1 cho trang mới sử dụng nhất.
- Rank 2,…,k cho các trang ít mới hơn.
- Rank k+1 cho trang **không nằm trong cache LRU**.

Đặt thế năng:

`Φ=Σ_(p∈cache_OPT) rank_LRU(p)`.

Φ≥0 và ban đầu bằng 0 vì hai cache rỗng. Với mỗi yêu cầu, tưởng tượng offline phục vụ trước rồi LRU phục vụ, hai cache vẫn độc lập nên không thay đổi kết quả.

**Offline hit:** không thay cache offline, Φ không đổi.

**Offline miss với cache offline đầy:** thay một trang có rank≥1 bằng trang mới có rank≤k+1, nên Φ tăng tối đa k.

**Offline miss khi chưa đầy:** thêm trang rank≤k+1; Φ tăng tối đa k+1. Có **nhiều nhất k lần** loại này, do offline bắt đầu rỗng và không vứt trang chủ động.

Sau offline phục vụ, trang được yêu cầu nằm trong cache OPT.

**LRU hit:** rank trang đó giảm về 1; một số trang OPT đứng trước nó trong thứ tự gần đây tăng rank tối đa 1, và tổng Φ không tăng.

**LRU miss:** trang vừa yêu cầu từ rank k+1 xuống rank 1, làm Φ giảm k. Nhiều nhất k−1 trang OPT khác tăng rank một đơn vị, nên Φ giảm ít nhất 1.

Cộng qua chuỗi:

`faults_LRU + (Φ_final−Φ_initial)≤k·faults_OPT+k`.

Vì Φ_initial=0 và Φ_final≥0:

`faults_LRU≤k·faults_OPT+k`.

Hằng số cộng k đến từ tối đa k lần khởi tạo cache offline. Đây là ví dụ phân tích cạnh tranh bằng **potential function**, theo dõi sự chênh lệch trạng thái giữa online và offline.

## 10. Oracle paging độc lập: DP bitmask

Để kiểm tra chính mã Belady, dùng một oracle **không dựa trên quy tắc xa nhất tương lai**.

Khi universe có u≤8 trang, mã hóa tập trang trong cache bằng mask. Đặt `DP(i,mask)` = số faults **tối thiểu** khi phục vụ suffix bắt đầu ở vị trí i, với trạng thái cache mask.

- Nếu i=T: DP=0.
- Nếu trang p đã có: DP(i+1,mask).
- Nếu miss mà cache còn chỗ: 1+DP(i+1,mask∪{p}).
- Nếu miss và cache đầy: 1+minimum qua **mọi trang q** có thể đuổi: `DP(i+1,(mask\{q})∪{p})`.

Công thức xét **tất cả lựa chọn eviction** nên tính đúng offline OPT cho input nhỏ, độc lập với thuật toán Belady. Mã sau sẽ kiểm `beladyFaults==exactPagingDp`.

Độ phức tạp oracle xấp xỉ O(T·2^u·k), bộ nhớ O(T·2^u). Chỉ dùng cho **input nhỏ** để xác minh, không phải cách triển khai online cho mọi dữ liệu.

## 11. List Scheduling: gán job mới cho máy đang nhẹ nhất

Có m≥1 máy **giống nhau**, các job đến tuần tự. Khi job j đến, ta biết thời lượng `p_j>0` của job đó và phải gán ngay vào một máy. Job không bị chia nhỏ, không di chuyển sau khi gán.

Mô hình này dùng **thứ tự tiết lộ**, không có release time thực khiến máy phải chờ. Mục tiêu là giảm **makespan**:

`C_max=max_i load_i`,

với load_i là tổng thời lượng các job trên máy i.

**Online List Scheduling:** gán mỗi job mới vào máy có **tải đang nhỏ nhất**. Nếu nhiều máy bằng nhau, chọn chỉ số nhỏ nhất.

**Offline OPT:** xem toàn bộ dãy jobs, phân chúng vào cùng m máy để có makespan tối thiểu.

### Chứng minh (2−1/m)-competitive

Gọi tổng thời lượng `P=Σp_j`, và job dài nhất `p_max`.

Mọi lịch offline có:

`OPT≥P/m` và `OPT≥p_max`.

Xét job j **kết thúc cuối cùng** trong lịch online. Khi nó được gán, máy được chọn có tải s nhỏ nhất, nên:

`s≤(tổng công việc xuất hiện trước j)/m≤(P−p_j)/m`.

Makespan của online:

`A=s+p_j≤P/m+(1−1/m)p_j`.

Từ hai cận dưới:

`A≤OPT+(1−1/m)OPT=(2−1/m)OPT`.

Vậy List Scheduling **strictly (2−1/m)-competitive** theo mô hình này.

### Các input sát cận

- m=2, jobs `[1,1,2]`. Online tải [3,1], makespan3. Offline phân [1,1] vào một máy và [2] vào máy kia, OPT2; ratio=3/2.
- m=3, jobs `[1,1,1,1,1,1,3]`. Online tải [5,2,2], makespan5. Offline đặt job3 riêng, chia sáu job1 vào hai máy còn lại, OPT3; ratio=5/3.

Tổng quát, đưa m(m−1) job có độ dài 1 tới trước rồi một job dài m, online cho makespan 2m−1, offline m, chạm đúng cận `2−1/m`.

### Vì sao phải nói rõ mô hình?

Nếu có **release times thực**, máy có thể phải chờ job đến và makespan không chỉ là tổng tải. Nếu máy có tốc độ khác nhau, việc chọn máy có load nhỏ nhất có thể sai. Nếu job được chia hoặc chuyển máy, miền nghiệm cũng thay đổi. Không áp dụng định lý trên cho những biến thể này khi chưa có chứng minh mới.

## 12. Bảng so sánh ba bảo đảm

| Bài toán | Online chỉ biết | Offline biết | Bảo đảm |
| --- | --- | --- | --- |
| Ski Rental | Ngày hiện tại, giá B | Cả thời hạn D | Strict `2−1/B` |
| Paging LRU | Lịch sử truy cập và cache | Toàn bộ suffix, dùng Belady | `A≤kOPT+k` |
| List Scheduling | Các job đã đến và tải máy | Tất cả job | Strict `2−1/m` |

Ba mô hình có cùng nguyên tắc so sánh nhưng khác ràng buộc. Không thể lấy hệ số từ một mô hình áp vào mô hình khác bằng cách đổi tên thuật toán.

## 13. Chương trình Java 17+ hoàn chỉnh

Lưu thành **`OnlineCompetitiveRatioDemo.java`**. Chương trình có ba thuật toán online, ba mốc offline và các oracle kiểm tra nhỏ:

- **Ski:** mô phỏng các ngày tới; lựa chọn mua chỉ dựa trên số thứ tự ngày và B, không nhìn trước D.
- **Paging:** `LinkedHashMap` access-order cho LRU, Belady quét tương lai, DP bitmask duyệt mọi khả năng đuổi trang.
- **Scheduling:** List Scheduling gán vào máy nhẹ nhất, offline oracle vét cạn phân công n≤10 jobs.
- **Kiểm thử:** 500 mùa ski, 350 chuỗi paging và 350 lịch scheduling; tính ratio chỉ khi OPT>0, kiểm tra các bất đẳng thức ngay cả khi OPT=0.

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Random;
import java.util.Set;
import java.util.TreeSet;

public class OnlineCompetitiveRatioDemo {
    record SkiResult(long cost, int rentedDays, boolean bought) {}

    static SkiResult skiRental(int buyCost, int days) {
        if (buyCost < 1 || days < 0)
            throw new IllegalArgumentException("Invalid ski input");
        long cost = 0;
        int rented = 0;
        boolean bought = false;
        // The harness reveals one day at a time; decisions
        // depend only on the current day and known buyCost.
        for (int day = 1; day <= days; day++) {
            if (day == buyCost) {
                cost += buyCost;
                bought = true;
                break; // Remaining days after purchase are free.
            }
            cost++;
            rented++;
        }
        return new SkiResult(cost, rented, bought);
    }

    static long skiOffline(int buyCost, int days) {
        if (buyCost < 1 || days < 0)
            throw new IllegalArgumentException("Invalid ski input");
        return Math.min((long) buyCost, (long) days);
    }

    static String ratio(long online, long offline) {
        return offline == 0 ? "undefined"
                : String.format(Locale.ROOT, "%.3f",
                        (double) online / offline);
    }

    static void showSki(String name, int b, int days) {
        SkiResult a = skiRental(b, days);
        long opt = skiOffline(b, days);
        boolean bound = a.cost() >= opt
                && a.cost() <= (2.0 - 1.0 / b) * opt + 1e-9;
        if (!bound) throw new AssertionError("Ski bound failed");
        System.out.printf(Locale.ROOT,
                "%s rent=%d bought=%s online=%d offline=%d"
                + " ratio=%s bound=%s%n",
                name, a.rentedDays(), a.bought(), a.cost(),
                opt, ratio(a.cost(), opt), bound);
    }

    // Online LRU: get() refreshes order on a hit.
    static int lruFaults(int[] requests, int capacity) {
        if (capacity < 1)
            throw new IllegalArgumentException("Invalid cache");
        LinkedHashMap<Integer, Boolean> cache =
                new LinkedHashMap<>(16, .75f, true);
        int faults = 0;
        for (int page : requests) {
            if (cache.get(page) != null) continue;
            faults++;
            if (cache.size() == capacity) {
                Iterator<Integer> it = cache.keySet().iterator();
                it.next();
                it.remove(); // Least recent first.
            }
            cache.put(page, Boolean.TRUE);
        }
        return faults;
    }

    // Offline Belady uses future requests.
    static int beladyFaults(int[] requests, int capacity) {
        if (capacity < 1)
            throw new IllegalArgumentException("Invalid cache");
        Set<Integer> cache = new TreeSet<>();
        int faults = 0;
        for (int i = 0; i < requests.length; i++) {
            int page = requests[i];
            if (cache.contains(page)) continue;
            faults++;
            if (cache.size() == capacity) {
                int victim = 0, farthest = -1;
                for (int q : cache) {
                    int next = requests.length;
                    for (int j = i + 1; j < requests.length; j++) {
                        if (requests[j] == q) {
                            next = j;
                            break;
                        }
                    }
                    if (next > farthest
                            || (next == farthest && q < victim)) {
                        farthest = next;
                        victim = q;
                    }
                }
                cache.remove(victim);
            }
            cache.add(page);
        }
        return faults;
    }

    // Independent offline oracle: explore all legal evictions.
    static int exactPagingDp(int[] requests, int k, int u) {
        if (u < 1 || u > 8 || k < 1 || k > u)
            throw new IllegalArgumentException("Need 1<=k<=u<=8");
        for (int page : requests)
            if (page < 0 || page >= u)
                throw new IllegalArgumentException("Invalid page");
        int[][] memo = new int[requests.length + 1][1 << u];
        for (int[] row : memo) Arrays.fill(row, -1);
        return pagingRec(0, 0, requests, k, u, memo);
    }

    static int pagingRec(int index, int mask,
            int[] requests, int k, int u, int[][] memo) {
        if (index == requests.length) return 0;
        if (memo[index][mask] >= 0)
            return memo[index][mask];
        int bit = 1 << requests[index];
        int result;
        if ((mask & bit) != 0) {
            result = pagingRec(index + 1, mask,
                    requests, k, u, memo);
        } else if (Integer.bitCount(mask) < k) {
            result = 1 + pagingRec(index + 1, mask | bit,
                    requests, k, u, memo);
        } else {
            result = Integer.MAX_VALUE;
            for (int p = 0; p < u; p++) {
                int old = 1 << p;
                if ((mask & old) == 0) continue;
                result = Math.min(result,
                        1 + pagingRec(index + 1,
                            (mask ^ old) | bit, requests, k, u, memo));
            }
        }
        memo[index][mask] = result;
        return result;
    }

    static void showPaging(String name, int k, int u,
            int[] requests) {
        int online = lruFaults(requests, k);
        int offline = beladyFaults(requests, k);
        if (offline != exactPagingDp(requests, k, u))
            throw new AssertionError("Belady vs exact DP");
        boolean bound = online >= offline
                && online <= k * offline + k;
        if (!bound) throw new AssertionError("Paging bound failed");
        System.out.printf(Locale.ROOT,
                "%s k=%d lru=%d offline=%d ratio=%s bound=%s%n",
                name, k, online, offline,
                ratio(online, offline), bound);
    }

    record Schedule(long[] loads, long makespan) {
        Schedule { loads = loads.clone(); }
        @Override
        public long[] loads() { return loads.clone(); }
    }

    static Schedule listSchedule(int[] jobs, int machines) {
        if (jobs == null || machines < 1)
            throw new IllegalArgumentException("Invalid machines");
        long[] loads = new long[machines];
        for (int duration : jobs) {
            if (duration <= 0)
                throw new IllegalArgumentException("Invalid duration");
            int best = 0;
            for (int j = 1; j < machines; j++)
                if (loads[j] < loads[best]) best = j;
            loads[best] += duration;
        }
        long makespan = 0;
        for (long load : loads)
            makespan = Math.max(makespan, load);
        return new Schedule(loads, makespan);
    }

    // Offline optimal assignment oracle for at most 10 jobs.
    static long exactMakespan(int[] jobs, int machines) {
        if (jobs == null || machines < 1 || jobs.length > 10)
            throw new IllegalArgumentException("Too many jobs");
        if (jobs.length == 0) return 0;
        long[] best = {listSchedule(jobs, machines).makespan()};
        searchSchedules(0, jobs, new long[machines], best);
        return best[0];
    }

    static void searchSchedules(int i, int[] jobs,
            long[] loads, long[] best) {
        if (i == jobs.length) {
            long cost = 0;
            for (long v : loads) cost = Math.max(cost, v);
            best[0] = Math.min(best[0], cost);
            return;
        }
        Set<Long> seen = new HashSet<>();
        for (int m = 0; m < loads.length; m++) {
            if (!seen.add(loads[m])) continue;
            loads[m] += jobs[i];
            if (loads[m] < best[0])
                searchSchedules(i + 1, jobs, loads, best);
            loads[m] -= jobs[i];
        }
    }

    static void showSchedule(String name, int machines,
            int[] jobs) {
        Schedule a = listSchedule(jobs, machines);
        long opt = exactMakespan(jobs, machines);
        boolean bound = a.makespan() >= opt
                && a.makespan()
                    <= (2.0 - 1.0 / machines) * opt + 1e-9;
        if (!bound)
            throw new AssertionError("Scheduling bound failed");
        System.out.printf(Locale.ROOT,
                "%s m=%d jobs=%s loads=%s online=%d"
                + " offline=%d ratio=%s bound=%s%n",
                name, machines, Arrays.toString(jobs),
                Arrays.toString(a.loads()), a.makespan(),
                opt, ratio(a.makespan(), opt), bound);
    }

    static void randomCheck() {
        Random r = new Random(4842026L);
        for (int t = 0; t < 500; t++) {
            int b = 1 + r.nextInt(100);
            int days = r.nextInt(3 * b + 1);
            long actual = skiRental(b, days).cost();
            long expected = days < b ? days : 2L * b - 1;
            if (actual != expected
                    || actual > (2.0 - 1.0 / b)
                            * skiOffline(b, days) + 1e-9)
                throw new AssertionError("Random ski");
        }
        System.out.println("skiRandom=PASS (500 cases)");

        for (int t = 0; t < 350; t++) {
            int k = 1 + r.nextInt(3);
            int u = k + 1 + r.nextInt(4);
            int len = 1 + r.nextInt(12);
            int[] req = new int[len];
            for (int i = 0; i < len; i++) req[i] = r.nextInt(u);
            int a = lruFaults(req, k);
            int b = beladyFaults(req, k);
            int opt = exactPagingDp(req, k, u);
            if (b != opt || a < opt || a > k * opt + k)
                throw new AssertionError("Random paging");
        }
        System.out.println("pagingRandom=PASS (350 cases)");

        for (int t = 0; t < 350; t++) {
            int machines = 1 + r.nextInt(4);
            int n = 1 + r.nextInt(9);
            int[] jobs = new int[n];
            for (int i = 0; i < n; i++)
                jobs[i] = 1 + r.nextInt(9);
            long a = listSchedule(jobs, machines).makespan();
            long opt = exactMakespan(jobs, machines);
            if (a < opt
                    || a > (2.0 - 1.0 / machines) * opt + 1e-9)
                throw new AssertionError("Random scheduling");
        }
        System.out.println("scheduleRandom=PASS (350 cases)");
    }

    public static void main(String[] args) {
        showSki("skiNoDays", 5, 0);
        showSki("skiFour", 5, 4);
        showSki("skiFive", 5, 5);
        showSki("skiEight", 5, 8);
        showSki("skiBuyOne", 1, 1);

        showPaging("pagingCycle", 2, 4,
                new int[]{1, 2, 3, 1, 2, 3});
        showPaging("pagingHits", 2, 3,
                new int[]{1, 2, 1, 2});
        showPaging("pagingTriple", 3, 5,
                new int[]{1, 2, 3, 4, 1, 2, 3, 4});
        showPaging("pagingEmpty", 2, 3, new int[0]);

        showSchedule("scheduleTight2", 2,
                new int[]{1, 1, 2});
        showSchedule("scheduleTight3", 3,
                new int[]{1, 1, 1, 1, 1, 1, 3});
        showSchedule("scheduleMixed", 3,
                new int[]{2, 3, 1, 4});
        showSchedule("scheduleEmpty", 2, new int[0]);

        try {
            skiRental(5, -1);
            throw new AssertionError("Expected ski error");
        } catch (IllegalArgumentException expected) {
            System.out.println("negativeDays=rejected");
        }
        try {
            exactPagingDp(new int[]{0, 3}, 2, 3);
            throw new AssertionError("Expected page error");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidPage=rejected");
        }
        try {
            listSchedule(new int[]{1, 0, 2}, 2);
            throw new AssertionError("Expected job error");
        } catch (IllegalArgumentException expected) {
            System.out.println("zeroJob=rejected");
        }
        randomCheck();
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 OnlineCompetitiveRatioDemo.java
java OnlineCompetitiveRatioDemo
~~~

**Đầu ra kỳ vọng:**

~~~text
skiNoDays rent=0 bought=false online=0 offline=0 ratio=undefined bound=true
skiFour rent=4 bought=false online=4 offline=4 ratio=1.000 bound=true
skiFive rent=4 bought=true online=9 offline=5 ratio=1.800 bound=true
skiEight rent=4 bought=true online=9 offline=5 ratio=1.800 bound=true
skiBuyOne rent=0 bought=true online=1 offline=1 ratio=1.000 bound=true
pagingCycle k=2 lru=6 offline=4 ratio=1.500 bound=true
pagingHits k=2 lru=2 offline=2 ratio=1.000 bound=true
pagingTriple k=3 lru=8 offline=5 ratio=1.600 bound=true
pagingEmpty k=2 lru=0 offline=0 ratio=undefined bound=true
scheduleTight2 m=2 jobs=[1, 1, 2] loads=[3, 1] online=3 offline=2 ratio=1.500 bound=true
scheduleTight3 m=3 jobs=[1, 1, 1, 1, 1, 1, 3] loads=[5, 2, 2] online=5 offline=3 ratio=1.667 bound=true
scheduleMixed m=3 jobs=[2, 3, 1, 4] loads=[2, 3, 5] online=5 offline=4 ratio=1.250 bound=true
scheduleEmpty m=2 jobs=[] loads=[0, 0] online=0 offline=0 ratio=undefined bound=true
negativeDays=rejected
invalidPage=rejected
zeroJob=rejected
skiRandom=PASS (500 cases)
pagingRandom=PASS (350 cases)
scheduleRandom=PASS (350 cases)
~~~

**Ý nghĩa từng nhóm kết quả.** Ski Rental đối chiếu A với `min(D,B)`; B=5,D=5 hoặc D=8 đều có ratio1.8. Paging đối chiếu LRU với **Belady và DP exact**; chuỗi [1,2,3,1,2,3] cho 6 so với 4. Scheduling đối chiếu với phân công offline tối ưu; [1,1,2] và sáu job1 rồi job3 đều sát hệ số lý thuyết. Input rỗng cho OPT=0 được báo ratio không xác định thay vì chia 0. Các phép thử với dữ liệu sai xác nhận API **từ chối** input ngoài mô hình.

**Kiểm thử ngẫu nhiên.** 500 trường hợp ski đối chiếu trực tiếp với công thức đóng; 350 chuỗi paging so Belady với oracle DP và kiểm tra cận LRU; 350 lịch scheduling so với oracle exact và cận 2−1/m. Đây là **kiểm chứng thực nghiệm trên input đã thử**, không thay thế chứng minh toán học cho mọi chuỗi.

## 14. Độ phức tạp

| Thành phần | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Ski Rental duyệt tới ngày mua/kết thúc | O(min(D,B)) | O(1) |
| LRU với LinkedHashMap | O(T) trung bình | O(k) |
| Belady bản đơn giản quét suffix | O(T²k) | O(k) |
| Offline paging DP với u trang | O(T·2^u·k) | O(T·2^u) |
| List Scheduling quét m máy mỗi job | O(nm) | O(m) |
| Exact Scheduling duyệt phân công | O(m^n) trường hợp xấu | O(m+n) cho ngăn xếp/tải, chưa tính cấu trúc phụ |

Có thể tăng tốc List Scheduling bằng priority queue O(n log m), Belady bằng tiền xử lý lần truy cập tiếp theo, nhưng bản demo ưu tiên làm rõ **online vs offline** và chứng minh chất lượng.

## 15. Khi mô hình thay đổi

- **Ski Rental giá thuê r khác 1:** ngưỡng mua phụ thuộc B/r, không dùng lại công thức `2−1/B` của mô hình thuê giá 1.
- **Paging lỗi có chi phí khác nhau:** chứng minh LRU và Belady fault-uniform có thể không còn đúng.
- **Paging offline có cache lớn hơn:** đổi thành mô hình resource augmentation, không so trực tiếp bằng cận cũ.
- **Scheduling máy khác tốc độ:** máy ít tải nhất chưa chắc xử lý nhanh nhất; bound 2−1/m không tự áp dụng.
- **Scheduling có release times:** makespan phụ thuộc chờ đợi, không chỉ tổng tải; cần định nghĩa comparator khác.
- **Scheduling cho phép chia nhỏ job:** miền nghiệm khác với mô hình nonpreemptive, không áp nguyên proof.
- **Randomized online:** phải chỉ rõ đối thủ chọn chuỗi trước hay thích nghi, và bound theo kỳ vọng, xác suất hay worst case trên mọi lần chạy.

## 16. Các lỗi thường gặp

1. Cho online biết D hoặc suffix request trước khi quyết định.
2. So với offline có thêm cache hoặc máy mà không nói rõ.
3. Dùng một offline heuristic chưa tối ưu làm OPT.
4. Tính A và OPT trên hai chuỗi khác nhau.
5. Nhầm tỷ số cạnh tranh của bài MIN và MAX.
6. Chia cho OPT=0.
7. Bỏ additive β khỏi bound cạnh tranh.
8. Đọc ratio trên benchmark rồi gọi đó là bound tệ nhất.
9. Nhầm cạnh tranh với regret so comparator khác.
10. Từ bound kỳ vọng suy ra bound mọi seed.
11. Không định nghĩa oblivious/adaptive adversary.
12. Ski: mua cuối ngày B nhưng tính chi phí như mua đầu ngày.
13. Ski: cho offline thuê trước rồi mua dù offline biết D.
14. Ski: quên trường hợp B=1 hoặc D=0.
15. Paging: không cập nhật LRU thứ tự khi hit.
16. Paging: gọi Belady là online.
17. Paging: cho phép offline prefetch miễn phí.
18. Paging: không kiểm độc lập Belady bằng DP trên input nhỏ.
19. Paging: tính hits thay vì faults cho mục tiêu MIN.
20. Scheduling: tính makespan là tổng jobs thay vì max load.
21. Scheduling: gán job dựa trên những job chưa tiết lộ.
22. Scheduling: cho offline chia job mà online không được chia.
23. Scheduling: áp cận máy giống nhau cho máy khác tốc độ.
24. Không kiểm tính khả thi trước khi so OPT.
25. Không thử trường hợp sát cận xấu nhất.
26. Dùng một số test ngẫu nhiên làm chứng minh mọi input.
27. Không công bố điều kiện của mô hình trước khi trích theorem.
28. Không phân biệt upper bound cho một thuật toán với lower bound cho cả lớp.

## 17. Bài tập có lời giải

**Bài 1.** Online biết những gì khi xử lý r_t? **Đáp án:** tiền tố r₁..r_t và tham số công bố trước.

**Bài 2.** Offline OPT được quyền biết gì? **Đáp án:** toàn chuỗi nhưng vẫn cùng tài nguyên và ràng buộc.

**Bài 3.** Bài MIN có A khả thi thì A và OPT quan hệ ra sao? **Đáp án:** A≥OPT.

**Bài 4.** Bài MAX có quan hệ nào? **Đáp án:** A≤OPT.

**Bài 5.** Strict c-competitive với MIN là gì? **Đáp án:** `A≤cOPT` trên mọi chuỗi.

**Bài 6.** Bound có additive constant như thế nào? **Đáp án:** `A≤cOPT+β`, β không tăng theo chiều dài chuỗi.

**Bài 7.** Từ A≤2OPT+10 có suy ra A≤2OPT không? **Đáp án:** không.

**Bài 8.** Khi A=OPT=0 thì A/OPT bao nhiêu? **Đáp án:** không xác định.

**Bài 9.** Với MAX, γ=0.8 có nghĩa gì? **Đáp án:** A≥0.8OPT trên mọi input thuộc mô hình.

**Bài 10.** γ=0.8 tương ứng c nào? **Đáp án:** c=1.25.

**Bài 11.** Competitive ratio khác regret ở đâu? **Đáp án:** comparator offline toàn chuỗi thường khác lớp comparator của regret.

**Bài 12.** Với B=5,D=4, ski offline OPT? **Đáp án:** 4.

**Bài 13.** Với B=5,D=5, ski offline OPT? **Đáp án:** 5.

**Bài 14.** Chính sách break-even B=5 mua ngày nào? **Đáp án:** đầu ngày 5 nếu mùa còn kéo dài.

**Bài 15.** B=5,D=5, online tốn bao nhiêu? **Đáp án:** 9.

**Bài 16.** Tỷ số tương ứng? **Đáp án:** 9/5=1.8.

**Bài 17.** B=5,D=8, online tốn bao nhiêu? **Đáp án:** vẫn 9 vì đã mua.

**Bài 18.** Ski Rental deterministic break-even có tỷ số nào? **Đáp án:** 2−1/B.

**Bài 19.** Vì sao always-rent không có ratio hữu hạn khi D không bị chặn? **Đáp án:** D tăng vô hạn trong khi OPT≤B.

**Bài 20.** LRU sử dụng thông tin nào? **Đáp án:** lịch sử dùng trang trong quá khứ.

**Bài 21.** Belady cần thông tin nào? **Đáp án:** lần dùng tiếp theo xa nhất ở tương lai.

**Bài 22.** k=2, chuỗi [1,2,3,1,2,3], LRU faults? **Đáp án:** 6.

**Bài 23.** Offline Belady trên chuỗi đó? **Đáp án:** 4.

**Bài 24.** Ratio thực tế của hai kết quả? **Đáp án:** 1.5.

**Bài 25.** Bound LRU có additive constant nào? **Đáp án:** `LRU≤kOPT+k`.

**Bài 26.** Tại sao paging DP giúp kiểm Belady? **Đáp án:** xét tất cả lựa chọn eviction thay vì lặp quy tắc Belady.

**Bài 27.** List Scheduling gán job mới vào máy nào? **Đáp án:** máy có tải hiện tại nhỏ nhất.

**Bài 28.** Với tổng P và m máy, OPT≥gì? **Đáp án:** OPT≥P/m.

**Bài 29.** Với job dài nhất p_max, OPT≥gì? **Đáp án:** OPT≥p_max.

**Bài 30.** Bound List Scheduling? **Đáp án:** `A≤(2−1/m)OPT`.

**Bài 31.** m=2, jobs [1,1,2], A/OPT là bao nhiêu? **Đáp án:** 3/2=1.5.

**Bài 32.** m=3, sáu jobs1 rồi job3, A và OPT? **Đáp án:** A=5, OPT=3.

**Bài 33.** Bound theo kỳ vọng có đúng cho từng seed không? **Đáp án:** không.

**Bài 34.** Oblivious adversary chọn chuỗi khi nào? **Đáp án:** cố định trước, không phụ thuộc random bits của A.

**Bài 35.** 350 test paging PASS có chứng minh bound cho mọi input không? **Đáp án:** không, cần chứng minh toán học.

**Bài 36.** Có thể chuyển trực tiếp bound scheduling sang máy không giống nhau không? **Đáp án:** không, vì mô hình đã thay đổi.

## 18. Checklist

1. Đã xác định cách và thời điểm reveal sự kiện chưa?
2. Online có thật sự không nhìn hậu tố khi ra quyết định?
3. Offline OPT có dùng đúng cùng chuỗi, cùng tài nguyên và chi phí?
4. OPT là nghiệm tối ưu được chứng nhận?
5. Mọi hành động online có khả thi không?
6. Bài MIN/MAX và chiều bất đẳng thức đã đúng?
7. Bound strict hay có β và đã ghi rõ?
8. Có xử lý OPT=0 và giá trị âm?
9. Có phân biệt upper/lower bound cạnh tranh?
10. Nếu randomized, đã định nghĩa adversary và loại bảo đảm?
11. Ski có B≥1,D≥0, mua đầu ngày B và tính `min(D,B)`?
12. Paging có cache k giống nhau và cùng empty initial state?
13. LRU cập nhật recency trên hit?
14. Belady chỉ dùng làm offline, và được kiểm bằng oracle DP nhỏ?
15. Scheduling có m máy giống nhau, job dương, không preempt và không release times thực?
16. Makespan có đúng bằng tải tối đa?
17. Có test chuỗi sát cận tệ nhất?
18. Có test chuỗi rỗng, đầu vào lỗi và OPT=0?
19. Có in A, OPT, ratio, bound và lý do cận khi báo cáo?
20. Có nhớ rằng test thực nghiệm không thay thế chứng minh cho mọi σ?

**Kết luận:** tỷ số cạnh tranh so **thuật toán online thiếu thông tin tương lai** với **offline OPT biết trước toàn chuỗi** nhưng **không được hưởng thêm tài nguyên**. Ski Rental đạt hệ số strict `2−1/B`, LRU có `kOPT+k` trong mô hình paging chuẩn, List Scheduling có hệ số strict `2−1/m`. Phải tách **bảo đảm cho mọi chuỗi** khỏi **tỷ số thực nghiệm**, đồng thời công khai hằng số cộng, adversary và trường hợp OPT=0.
