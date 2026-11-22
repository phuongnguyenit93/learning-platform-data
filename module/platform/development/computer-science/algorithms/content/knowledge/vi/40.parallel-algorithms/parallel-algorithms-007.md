# Cân bằng tải khi các bài toán con có kích thước khác nhau

Trong **thuật toán song song (parallel algorithms)**, một bài toán lớn thường được chia thành nhiều **bài toán con** để chạy trên nhiều lõi CPU hoặc worker. Khi kích thước/công việc của các bài toán con **không đồng đều**, cách chia đều **số lượng task** không nhất thiết chia đều **thời gian chạy**. Một worker có thể xử lý một task quá lớn trong khi những worker khác đã xong và đang nhàn rỗi. Khi đó tổng thời gian hoàn thành bị quyết định bởi **worker kết thúc muộn nhất**, chứ không phải bởi thời gian trung bình.

Bài Knowledge này thuộc nhóm **Thuật toán song song** của **Computer Science Algorithms**, giải thích cách nhận diện mất cân bằng tải và chọn chiến lược phân công khi thời lượng task khác nhau: **chia khối tĩnh (static block)**, **round-robin**, **list scheduling với hàng đợi chung**, **LPT — Longest Processing Time first**, **chia nhỏ task**, **work stealing** và các ràng buộc tài nguyên ngoài mô hình lý tưởng. Ta sẽ học mô hình **makespan**, cận dưới bằng tổng việc và task lớn nhất, chứng minh bảo đảm cho list scheduling, giới hạn của LPT, quy tắc chọn độ hạt, đo speedup/efficiency, và cách đối chiếu lịch phân công với một **oracle tối ưu vét cạn**.

Phần thực hành có chương trình **Java 17 tự chạy**: mô phỏng bốn lịch phân công trên cùng dãy thời lượng, tính chính xác makespan và lower bound, tìm lịch tối ưu trên đầu vào nhỏ bằng branch-and-bound, kiểm thử bằng oracle brute force độc lập; sau đó chạy các phép tính độc lập bằng **ExecutorService** nhưng **không giả định thứ tự thực thi của thread là xác định**. Bài phân biệt rõ **thời lượng đã biết/ước lượng** với **runtime thực**, vì overhead, tranh chấp bộ nhớ, GC, I/O và sai số dự báo có thể khiến thực tế khác mô hình.

## 1. Tại sao chia đều số lượng chưa đủ?

Giả sử có ba worker và chín task có thời lượng lần lượt:

~~~text
[20, 1, 1, 1, 1, 1, 1, 1, 1]
~~~

Nếu chia đều **ba task cho một worker** theo khối liên tiếp:

~~~text
worker 0: 20 + 1 + 1 = 22
worker 1:  1 + 1 + 1 =  3
worker 2:  1 + 1 + 1 =  3

Tong cong viec W = 28
Makespan (thoi diem xong het) = 22
~~~

Hai worker hết việc từ rất sớm; phần còn lại không thể tự chuyển sang worker khác nếu lịch phân công đã đóng cứng. Nếu dùng **hàng đợi chung**, worker trống tiếp tục nhận task 1 đơn vị; tải cuối có thể thành:

~~~text
worker 0: 20
worker 1:  4
worker 2:  4
makespan = 20
~~~

Cận dưới của bất kỳ lịch nào là **20**, vì task dài 20 không được phép tách hay chạy một lúc trên hai worker. Trong mô hình này hàng đợi chung đã đạt tối ưu, nhưng tăng worker lên 4 hay 100 cũng **không thể hoàn thành nhanh hơn 20** nếu task lớn ấy không chia được.

Đây là điểm mấu chốt: **cân bằng tải giúp loại bỏ nhàn rỗi có thể tránh được, nhưng không thể phá cận do bài toán con không chia nhỏ được**.

## 2. Định nghĩa toán học: mục tiêu makespan

Xét \(n\) task **độc lập**, có thời gian xử lý dương:

\[
p_0,p_1,\ldots,p_{n-1}>0.
\]

Có \(P\) worker **đồng nhất** (mỗi worker xử lý một task mỗi lúc, cùng tốc độ), mọi task đều sẵn sàng tại thời điểm 0. Task là **không thể ngắt giữa chừng** (*non-preemptive*) và mỗi task chỉ chạy trên một worker.

Một lịch phân công \(a(i)\in\{0,\ldots,P-1\}\) tạo tải của worker \(w\):

\[
L_w=\sum_{i:a(i)=w}p_i.
\]

**Makespan**, tức thời gian xong toàn bộ trong mô hình lý tưởng, là:

\[
\boxed{C_{\max}=\max_{0\le w<P}L_w.}
\]

Bài toán tối ưu là tìm lịch có \(C_{\max}\) nhỏ nhất, gọi là \(OPT\). Trong lý thuyết lập lịch đây là biến thể **P||Cmax**: các máy giống nhau, các job không có ràng buộc thứ tự trước/sau, tối thiểu hóa makespan.

**Cận dưới rất quan trọng:**

\[
W=\sum_i p_i,\qquad
\boxed{OPT\ge LB=\max\left(\max_i p_i,\ \frac WP\right).}
\]

Vì một task không chia nhỏ phải chạy hết \(p_i\) trên một worker; và trong thời gian \(T\), \(P\) worker có thể xử lý tối đa \(P T\) đơn vị công việc. Với \(p_i\) nguyên, dùng \(\lceil W/P\rceil\) làm cận dưới nguyên.

Một lịch có makespan bằng **LB** chắc chắn **tối ưu**. Nếu lớn hơn LB thì chưa chắc kém tối ưu: LB đôi khi không đạt được do các task nguyên khối không thể ghép vừa các worker.

**Các giả thiết không được bỏ qua:** task phải độc lập và sẵn sàng từ đầu; worker cùng tốc độ; không có deadline/release time/affinity; không có overhead hoặc tranh chấp tài nguyên; thời gian \(p_i\) là hằng xác định. Khi bài toán thực khác các điều kiện này, lý thuyết bảo đảm phải điều chỉnh.

## 3. Các chỉ số nên đo

| Chỉ số | Công thức / cách đọc |
| --- | --- |
| Tổng công việc \(W\) | Tổng tất cả thời lượng task |
| Makespan \(C_{\max}\) | Tải/giờ kết thúc lớn nhất trên một worker |
| Cận dưới \(LB\) | Max(task lớn nhất, ceil(W/P)) trong mô hình nguyên |
| Độ lệch tải | Có thể dùng max(load) − min(load), phương sai hoặc CV; **không thay** makespan |
| Speedup lý tưởng | \(S_P=T_1/T_P=W/C_{\max}\) khi một worker chạy tuần tự mất W |
| Hiệu suất | \(E_P=S_P/P=W/(P C_{\max})\) |
| Tỷ lệ nhàn rỗi lý tưởng | \(1-W/(P C_{\max})\) |
| Load balance ratio | \(C_{\max}/(W/P)\), chú ý mẫu số không phải OPT |
| Approximation ratio | \(C_{\max}/OPT\) khi có OPT đúng, không dùng lower bound làm OPT |

Ví dụ với W=36, P=3 và một lịch \(C_{\max}=12\), ta có speedup lý tưởng 3, efficiency 100%. Nếu \(C_{\max}=15\), speedup=2,4 và efficiency=80%, tỷ lệ nhàn rỗi do mất cân bằng là 20%.

Các chỉ số trên chỉ có ý nghĩa rõ khi coi \(W\) là **tổng CPU work không bị đổi bởi việc song song hóa**. Với chương trình thực, cache, memory contention, GC, task management và thuật toán song song mới có thể khiến lượng CPU work không bằng bản tuần tự. Đừng tự thay \(T_1\) đo được bằng \(W\) ước lượng rồi công bố “speedup thực tế”.

Độ lệch tải nhỏ cũng chưa chắc là hiệu năng tốt nếu mọi worker đang **tranh chấp I/O, bộ nhớ hoặc khóa**. Vì vậy cùng với makespan phải đo throughput, CPU utilization, latency tail, queue wait, memory bandwidth và chi phí đồng bộ theo mục tiêu của hệ thống.

## 4. Chia khối tĩnh (block partitioning)

Một cách rất dễ cài đặt là cắt mảng task thành \(P\) khối liên tiếp, sao cho **số task mỗi khối xấp xỉ bằng nhau**. Worker \(w\) xử lý các task trong khối của nó.

Ưu điểm:
- Không cần hàng đợi chung; ít đồng bộ/dispatch.
- Giữ locality nếu task gần nhau chia sẻ dữ liệu liền kề, cache hoặc I/O.
- Tái lập assignment dễ dàng, hữu ích khi dữ liệu tương đối đồng đều.

Nhược điểm:
- Nếu một khối chứa nhiều task nặng, worker đó thành **straggler**.
- Các worker xong sớm không tự lấy thêm việc.
- “Mỗi worker có k task” không tương đương “mỗi worker có tổng thời lượng giống nhau”.

Trong Java demo, block size là \(\lceil n/P\rceil\); worker 0 nhận block đầu, worker 1 block kế tiếp... Cách chia này tối ưu **số lượng task trên mỗi khối theo một quy tắc đơn giản**, không tối ưu tổng thời lượng.

Với dãy [9,8,7,6,5,4,3,2,1] và P=3:

~~~text
worker 0: [9,8,7] -> 24
worker 1: [6,5,4] -> 15
worker 2: [3,2,1] ->  6
makespan = 24
~~~

Một lịch tối ưu thực tế có thể hoàn thành trong 15. Static block ở đây đạt makespan 24, lãng phí tiềm năng rất đáng kể dù mỗi worker nhận đúng ba task.

## 5. Round-robin: phân task xoay vòng

Round-robin đặt task i vào worker \(i \bmod P\):

~~~text
jobs = [9,8,7,6,5,4,3,2,1], P=3
worker 0: 9+6+3 = 18
worker 1: 8+5+2 = 15
worker 2: 7+4+1 = 12
makespan = 18
~~~

Round-robin tránh một số tình huống nhiều task nặng dồn vào cùng một **đoạn liên tiếp**, nhưng không hứa rằng các task nặng không trùng một **lớp modulo**. Ví dụ các job nặng ở chỉ số 0,3,6 có thể cùng vào worker 0 khi P=3.

**Khi nào phù hợp?** Khi thứ tự đầu vào đủ đa dạng hoặc chi phí task tương đối giống nhau; khi muốn ít overhead; khi assignment quyết định được trước. Không nên gọi round-robin là “cân bằng tải theo thời gian” mà không kiểm tra phân phối trọng số.

**Đừng nhầm** round-robin **phân công tĩnh theo chỉ số** với bộ lập lịch CPU time-slicing round-robin có preemption. Bài này **không** chia nhỏ một task trong lúc đang chạy.

## 6. Hàng đợi chung và list scheduling

Trong một hệ thống có nhiều worker, một lựa chọn linh hoạt là giữ các task chưa xử lý trong **hàng đợi chung**. Khi worker xong task, nó tiếp tục lấy task kế tiếp. Với **task độc lập, sẵn sàng ngay từ đầu và chi phí chạy là \(p_i\)**, lý tưởng hóa này tương đương quy tắc:

> Duyệt các task theo thứ tự đầu vào; phân mỗi task tới worker có tổng tải đã gán **nhỏ nhất**.

Quy tắc đó thường gọi là **list scheduling**. Nếu đầu vào được giữ nguyên thứ tự FIFO, bài gọi là `FIFO_LIST`. Các worker hòa tải được chọn theo **chỉ số nhỏ nhất** để mô phỏng xác định.

Ví dụ:

~~~text
jobs = [5,1,9,2,10,3,6], P=3

FIFO_LIST:
w0: 5 + 3 + 6 = 14
w1: 1 + 2 +10 = 13
w2: 9          =  9

makespan = 14
~~~

Trong mô hình không overhead, một worker có công việc đang chờ sẽ không bị để trống vô lý. Khi task duration **không dự báo được**, một queue động thường chống lệch tốt hơn so với chia khối cố định.

**Tuy nhiên:** simulation tính `load` bằng các thời lượng **đã biết** để suy ra thời điểm worker sẽ trống. Trong triển khai thực, hệ thống chỉ biết worker nào **thực sự xong việc**. ExecutorService với queue thực không thể biết trước tốc độ chính xác nếu có GC, preemption, I/O hay contention.

### 6.1. Chứng minh bảo đảm của list scheduling

Với P worker đồng nhất, task độc lập và tất cả sẵn sàng từ t=0, list scheduling không preemptive đạt:

\[
\boxed{C_{\max}\le(2-1/P)\,OPT.}
\]

**Chứng minh:** gọi j là task kết thúc cuối cùng, có thời lượng \(p_j\) và bắt đầu tại thời điểm \(s\). Khi list scheduling gán j tới worker ít tải nhất, mỗi worker khác đã được gán ít nhất s đơn vị công việc. Vì thế tổng công việc **trừ task j** ít nhất \(P s\):

\[
P s\le W-p_j
\quad\Longrightarrow\quad
s\le\frac{W-p_j}{P}.
\]

Vì \(C_{\max}=s+p_j\):

\[
C_{\max}\le W/P+(1-1/P)p_j
\le OPT+(1-1/P)OPT
=(2-1/P)OPT.
\]

Bước cuối dùng **hai cận dưới** \(W/P\le OPT\) và \(p_j\le OPT\). Đây là kết luận **với mọi dãy thời lượng dương hợp lệ** dưới giả thiết nêu ra, không chỉ là kết quả benchmark.

**Lưu ý:** phát biểu này áp dụng cho list scheduling **work-conserving** trên máy đồng nhất, không tự bảo vệ block partitioning, round-robin tĩnh, hệ thống có release dates hoặc worker tốc độ khác nhau.

## 7. LPT: ưu tiên bài toán con dài nhất

Khi **biết hoặc dự đoán được** thời lượng task trước lúc phân công, ta có thể sắp xếp task theo **thời gian giảm dần**, rồi gán từng task tới worker ít tải nhất. Đó là **Longest Processing Time first (LPT)**.

~~~text
sort jobs by estimated duration descending
for job in sorted jobs:
    worker = argmin(current assigned load)
    assign(job, worker)
~~~

Ví dụ dễ thấy hiệu quả LPT:

~~~text
jobs = [5,1,9,2,10,3,6], P=3
W = 36
LB = max(10,ceil(36/3)) = 12

BLOCK         loads=[15,15, 6]  makespan=15
ROUND_ROBIN   loads=[13,11,12]  makespan=13
FIFO_LIST     loads=[14,13, 9]  makespan=14
LPT           loads=[12,12,12]  makespan=12

OPT=12, vi LPT da cham can duoi LB.
~~~

Lịch LPT là:

~~~text
worker 0: 10 + 2     = 12
worker 1:  9 + 3     = 12
worker 2:  6 + 5 + 1 = 12
~~~

LPT cho cân bằng hoàn hảo trong ví dụ, nhưng **không luôn tìm đúng OPT**.

### 7.1. Bảo đảm xấp xỉ của LPT

Trên **máy đồng nhất**, tất cả task độc lập, có mặt ngay từ đầu, thời gian dương đã biết chính xác và không preemptive, định lý kinh điển cho:

\[
\boxed{C_{\max}^{LPT}\le(4/3-1/(3P))\,OPT}
\]

với P≥2 (P=1 hiển nhiên tối ưu). Đây là bảo đảm **mạnh hơn** cận \(2-1/P\) của list scheduling tổng quát.

**Trực giác**: đẩy các task lớn lên trước tránh dồn những việc rất dài vào cuối một worker. Chứng minh chặt chẽ cần phân tích task “cuối cùng” trên worker chậm nhất và chứng tỏ trường hợp LPT không tối ưu bị giới hạn bởi những task còn đủ nhỏ. Trong bài, ta chứng minh đầy đủ cận list scheduling ở trên và dùng cận LPT như **định lý được biết trong mô hình P||Cmax**; không coi vài nghìn test là chứng minh mới của định lý.

**Phản ví dụ rất nhỏ cho LPT**:

~~~text
jobs = [2,2,2,3,3], P=2
LPT sorting: [3,3,2,2,2]

worker 0: 3+2+2 = 7
worker 1: 3+2   = 5
LPT makespan=7

OPT: worker 0 = 3+3 = 6
     worker 1 = 2+2+2 = 6
OPT=6

LPT/OPT = 7/6 = 1.166666...
~~~

Với P=2, cận LPT là \(4/3-1/6=7/6\); ví dụ trên **đạt đúng cận**, cho thấy không nên hứa LPT luôn tối ưu.

Nếu chỉ biết **ước lượng** thay vì thời gian thực, chất lượng lịch thực có thể kém dự đoán. Nếu worker có tốc độ khác nhau, kết quả classical bound nói trên **không tự áp dụng**; cần dùng mô hình tốc độ/related/unrelated machines và thuật toán phù hợp.

## 8. Khi một task rất lớn quyết định tất cả

Dãy chín task:

~~~text
[20,1,1,1,1,1,1,1,1], P=3

W=28, LB=max(20,ceil(28/3))=20
BLOCK        loads=[22,3,3], makespan=22
ROUND_ROBIN  loads=[22,3,3], makespan=22
FIFO_LIST    loads=[20,4,4], makespan=20
LPT          loads=[20,4,4], makespan=20
OPT=20
~~~

Cả FIFO_LIST và LPT chạm cận 20, nhưng speedup lý tưởng bị giới hạn:

\[
S_P\le W/\max_i p_i=28/20=1.4.
\]

Ngay cả khi P lớn vô hạn, **task 20 đơn vị vẫn là nút cổ chai nếu không chia nhỏ được**. Trong ví dụ P=3, hiệu suất tại makespan20 là \(28/(3\cdot20)\approx46.7\%\): mất hiệu suất chủ yếu do **giới hạn song song sẵn có**, không phải do scheduler làm việc sai.

**Cách cải thiện thực sự:** nếu bài toán con nặng có thể phân tách **độc lập và đúng ngữ nghĩa**, chia nó thành các task nhỏ hơn. Nếu nó là một công đoạn tuần tự/bắt buộc, không có heuristic phân công nào vượt qua cận độ dài công đoạn ấy.

## 9. Độ hạt công việc (task granularity)

Chia nhỏ hơn thường tạo thêm cơ hội cân bằng tải, nhưng **mỗi task có overhead**:
- Đưa task vào queue, tạo/thu hồi object, đồng bộ, wake-up;
- Copy/serialize dữ liệu, truyền qua mạng giữa node;
- Khởi tạo context, bộ đệm và cấp phát;
- Tranh chấp shared queue, lock và cache;
- Chi phí gộp/giảm kết quả và garbage collection.

Nếu W là công việc hữu ích, chia thành K task và mỗi task tiêu tốn overhead h trong mô hình xấp xỉ, tổng công việc có thể lên đến \(W+Kh\). Chia quá nhỏ làm **overhead thống trị**. Chia quá lớn tạo **straggler** không thể di chuyển khi đang chạy.

Một nguyên tắc thực dụng:
1. Task cần đủ lớn để có thời gian xử lý **vượt đáng kể** dispatch/synchronization overhead.
2. Số task thường cần nhiều hơn số worker nếu thời lượng biến thiên, để worker trống còn việc lấy.
3. Nếu có một task rất lớn, thử tách chính **task đó**, không chỉ tăng số worker.
4. Tạo ngưỡng chia hoặc **adaptive chunking** dựa trên số mẫu đã đo, phân phối chi phí và ngân sách bộ nhớ.
5. Kiểm chứng bằng throughput/makespan và latency tail thực, không chỉ phân tích big-O.

**Ví dụ lặp nested recursion:** chia một nhánh thành hai nhánh chưa chắc độc lập; nếu mỗi nhánh lại sinh hàng triệu task cực nhỏ, overhead của task sẽ áp đảo. Có thể áp dụng ngưỡng: dưới kích thước nhất định thì giải tuần tự trong cùng thread; trên ngưỡng mới fork.

## 10. Work stealing khi cấu trúc bài toán con khó dự đoán

Với **bài toán chia để trị, backtracking, cây tìm kiếm không đều**, một worker có thể sinh nhiều task con hơn worker khác. **Work stealing** cho phép worker rảnh lấy task từ hàng đợi của worker bận:

~~~text
worker A: local deque [subtask, subtask, subtask]
worker B: local deque [subtask]
worker C: local deque []

worker C ranh -> thu steal mot task chua chay
tu deque cua A, neu policy cho phep.
~~~

Các hệ thống như **Java ForkJoinPool** cung cấp cơ chế work stealing cho các task dạng fork/join. Nó phù hợp với việc tính toán đệ quy có thể **chia nhỏ thành các subtask độc lập**.

**Giới hạn cốt lõi:** work stealing chỉ chuyển được **task chưa xử lý hoặc task được phân tách hợp lệ**. Nó không tự tạm dừng một task nguyên khối đang chạy 20 giây ở worker A rồi cắt một nửa công việc của A sang worker C. Muốn thế phải thiết kế **cooperative splitting/preemption** riêng.

**Cẩn trọng Java:** dùng `ForkJoinTask` và ngưỡng chia hợp lý; tránh blocking I/O lâu dài trong common pool mà không có chiến lược quản lý; tránh chia quá nhỏ; không chia sẻ trạng thái mutable mà không đồng bộ; tránh `fork()` hàng triệu task khi một vòng lặp tuần tự ngắn sẽ hiệu quả hơn.

Đối với các job độc lập, một **ThreadPoolExecutor/ForkJoinPool** có thể xử lý queue động thực tế; nhưng tác vụ đòi tài nguyên đặc thù như GPU, database connection hoặc một node có cache/data affinity riêng cần scheduler nhận biết ràng buộc ấy.

## 11. Tổng công việc và đường găng khi task có phụ thuộc

Mô hình P||Cmax giả định task **độc lập**. Nếu bài toán con có quan hệ phụ thuộc dạng **DAG**, phải tính thêm độ dài **critical path / span** S.

Với tổng công việc W và P worker:

\[
T_P\ge\max(W/P,\ S).
\]

Một bài toán có độ sâu phụ thuộc S gần bằng W không thể tăng tốc nhiều dù chia thành rất nhiều node nhỏ. Đây là lý do “có 100.000 task” không có nghĩa “100.000 task đều chạy đồng thời”.

**Ví dụ:** pipeline có các bước A→B→C bắt buộc lần lượt, mỗi bước 10 giây. W=30, S=30, nên T_P≥30 với mọi P; tăng worker không giúp nếu không thể pipeline nhiều dữ liệu độc lập theo thời điểm. Ngược lại, trong cây fork-join có nhiều nhánh độc lập, work stealing có thể giảm thời gian chờ các nhánh nặng.

Các định lý LPT và list scheduling ở mục trước áp dụng cho **independent jobs** đồng nhất; với precedence constraints và release times cần dùng định lý tương ứng, không sao chép kết quả bảo đảm nguyên xi.

## 12. Khi thời lượng chỉ là ước lượng

Thực tế có thể biết kích thước input nhưng **không biết chính xác p_i**:
- Số phần tử trong một chunk chưa chắc tỷ lệ thuận thời gian nếu chi phí mỗi phần tử khác nhau;
- Một nhánh backtracking có độ sâu nhỏ nhưng nhiều tổ hợp;
- Query database có selectivity/index/cache không ổn định;
- Task I/O bị ảnh hưởng bởi network và remote service;
- CPU task phụ thuộc locality, allocation, GC và cạnh tranh tài nguyên.

LPT dựa trên thời lượng dự kiến; khi dự đoán sai nghiêm trọng, nó có thể tạo lịch thực tế không tốt. Các lựa chọn:
- Dùng **cost model** tốt hơn: số nút, độ sâu, kích thước dữ liệu, lịch sử runtime, sampling;
- Sắp xếp theo **estimated remaining work** nếu có bằng chứng ước lượng;
- Kết hợp **LPT cho các job lớn đã biết** với **hàng đợi động** cho các job nhỏ/chưa chắc;
- Dùng work stealing nếu task con có thể di chuyển;
- Đưa vào **budget/timeout/chunk splitting** cho các task bất thường dài, nếu có thể dừng và tiếp tục an toàn.

**Tính công bằng và chi phí di chuyển:** chuyển task giữa worker có thể mất cache locality, NUMA locality hoặc phải truyền dữ liệu lớn. Một scheduler cân bằng số giây CPU về lý thuyết nhưng chuyển hàng gigabyte dữ liệu có thể **chậm hơn** lịch tĩnh giữ dữ liệu tại chỗ.

## 13. Java: điều gì có và không thể suy ra từ mô phỏng?

Phần mềm thực cần phân biệt:
- **Lịch lý tưởng:** mỗi task có duration xác định, start ngay khi worker rảnh, không overhead; dùng để tính makespan và nghiên cứu thuật toán.
- **Lịch chạy thật:** thread có thể bị scheduler hệ điều hành preempt, contention, lock, GC, I/O; công việc có thể chạy lâu hơn dự kiến.

Nếu chạy `ExecutorService` fixed pool:
- Số thread cố định là **giới hạn concurrency**, không nhất thiết bằng số core CPU hữu ích.
- Queue nhận task theo thứ tự submit (tùy executor), nhưng **thứ tự hoàn thành không xác định**.
- `invokeAll` trả danh sách Future **theo thứ tự danh sách task gửi vào**, **không có nghĩa** các task được thực hiện theo thứ tự đó.
- Task có side effects cần đồng bộ phù hợp hoặc thiết kế immutable/pure; tránh race ở shared accumulator.
- `Executors.newFixedThreadPool` dùng hàng đợi không giới hạn mặc định; production có lưu lượng lớn nên cân nhắc **bounded queue, backpressure, rejection policy** qua `ThreadPoolExecutor`.

**Benchmark thực:** ghi phiên bản JDK, P, số cores, kích thước task, warm-up, GC, I/O và nhiều lần chạy; đo **makespan thực** bằng clock monotonic bên ngoài toàn nhóm task, không dùng đơn lẻ một lần `System.nanoTime()` của task nhỏ rồi suy ra speedup. Với microbenchmark Java, có thể dùng JMH phù hợp.

## 14. Chương trình Java 17: bốn scheduler và lời giải tối ưu

File **UnevenParallelTasksDemo.java** sử dụng `long` và `Math.addExact` để tránh tràn tổng thời lượng trước khi so sánh. Chương trình giả định mọi duration **dương** và hợp lệ; worker count ≥1. Phân công theo bốn chiến lược:

- `BLOCK`: chia task theo khối chỉ số liên tiếp gần đều số lượng.
- `ROUND_ROBIN`: task i → worker i % P.
- `FIFO_LIST`: task theo thứ tự gốc, worker có tổng tải hiện tại nhỏ nhất.
- `LPT`: sort job giảm dần theo duration, hòa thì ưu tiên **chỉ số job gốc nhỏ hơn**, rồi gán tới worker ít tải nhất.

Hai oracle:
- `exactOptimum`: branch-and-bound với symmetry pruning cho đầu vào n≤11, P≤4; cận trên ban đầu là lịch LPT hợp lệ, bỏ nhánh không thể tốt hơn.
- `bruteOptimum`: duyệt **tất cả P^n phép gán** trên input thật nhỏ, độc lập với thuật toán branch-and-bound, để kiểm tra `exactOptimum`.

**Self-test:** mọi dãy **có thứ tự** dài 1..7, duration từ {1,2,3}, P=1..3: có **9.837 trường hợp**. Trên toàn bộ miền, oracle brute và branch-and-bound bằng nhau; FIFO_LIST thỏa cận \(2-1/P\); LPT thỏa \(4/3-1/(3P)\). Có **136 ca LPT kém OPT** và **2.368 ca FIFO_LIST có makespan lớn hơn LPT**. Các số đó là thống kê **miền hữu hạn đã kiểm**, không phải tỷ lệ thống kê trên dữ liệu thực.

Chương trình còn dùng `ExecutorService` thực hiện phép tính thuần trên ba worker và **chỉ xác nhận kết quả từng task trùng bản tuần tự**, không in thứ tự/latency phụ thuộc lịch thread.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class UnevenParallelTasksDemo {
    enum Strategy { BLOCK, ROUND_ROBIN, FIFO_LIST, LPT }

    record Schedule(long[] loads, int[] owner, long makespan) {}

    static void validate(long[] jobs, int workers) {
        if (jobs == null || jobs.length == 0 || workers < 1)
            throw new IllegalArgumentException(
                "Need >=1 positive-duration job and >=1 worker");
        for (long p : jobs) {
            if (p <= 0)
                throw new IllegalArgumentException(
                    "Every duration must be positive");
        }
    }

    static Integer[] descendingOrder(long[] jobs) {
        Integer[] ids = new Integer[jobs.length];
        for (int i = 0; i < jobs.length; i++) ids[i] = i;
        Arrays.sort(ids, (a, b) -> {
            int cmp = Long.compare(jobs[b], jobs[a]);
            return cmp != 0 ? cmp : Integer.compare(a, b);
        });
        return ids;
    }

    static long totalWork(long[] jobs) {
        long sum = 0;
        for (long p : jobs) sum = Math.addExact(sum, p);
        return sum;
    }

    static long lowerBound(long[] jobs, int workers) {
        validate(jobs, workers);
        long total = totalWork(jobs);
        long max = 0;
        for (long p : jobs) max = Math.max(max, p);
        long quotient = total / workers;
        long ceilAverage = quotient
                + (total % workers == 0 ? 0 : 1);
        return Math.max(max, ceilAverage);
    }

    static Schedule plan(long[] jobs, int workers,
                         Strategy strategy) {
        validate(jobs, workers);
        if (strategy == null)
            throw new IllegalArgumentException("Null strategy");

        long[] load = new long[workers];
        int[] owner = new int[jobs.length];
        Integer[] ids = strategy == Strategy.LPT
                ? descendingOrder(jobs)
                : new Integer[jobs.length];
        if (strategy != Strategy.LPT) {
            for (int i = 0; i < jobs.length; i++) ids[i] = i;
        }

        int blockSize = (int) (
                ((long) jobs.length + workers - 1) / workers);

        for (int i : ids) {
            int w;
            if (strategy == Strategy.BLOCK) {
                w = Math.min(workers - 1, i / blockSize);
            } else if (strategy == Strategy.ROUND_ROBIN) {
                w = i % workers;
            } else {
                w = 0;
                for (int j = 1; j < workers; j++) {
                    if (load[j] < load[w]) w = j;
                }
            }
            owner[i] = w;
            load[w] = Math.addExact(load[w], jobs[i]);
        }

        long finish = 0;
        for (long x : load) finish = Math.max(finish, x);
        return new Schedule(load, owner, finish);
    }

    // Exact optimum for SMALL cases by branch and bound.
    // Symmetric workers with identical loads need not be retried.
    static long exactOptimum(long[] jobs, int workers) {
        validate(jobs, workers);
        if (jobs.length > 11 || workers > 4)
            throw new IllegalArgumentException(
                "Exact oracle limited to n<=11, P<=4");

        long[] loads = new long[workers];
        long[] best = {
            plan(jobs, workers, Strategy.LPT).makespan()
        };
        searchExact(jobs, descendingOrder(jobs),
                    0, loads, best);
        return best[0];
    }

    static void searchExact(
            long[] jobs, Integer[] order, int at,
            long[] loads, long[] best) {
        if (at == order.length) {
            long finish = 0;
            for (long x : loads) finish = Math.max(finish, x);
            best[0] = Math.min(best[0], finish);
            return;
        }
        long p = jobs[order[at]];
        for (int w = 0; w < loads.length; w++) {
            long before = loads[w];
            boolean sameAsEarlier = false;
            for (int j = 0; j < w; j++) {
                if (loads[j] == before) {
                    sameAsEarlier = true;
                    break;
                }
            }
            if (sameAsEarlier) continue;
            long candidate = Math.addExact(before, p);
            if (candidate >= best[0]) continue;
            loads[w] = candidate;
            searchExact(jobs, order, at + 1, loads, best);
            loads[w] = before;
            if (before == 0) break;
        }
    }

    // Separate brute-force oracle: no scheduling heuristic,
    // no symmetry pruning, enumerates every worker choice.
    static long bruteOptimum(long[] jobs, int workers) {
        validate(jobs, workers);
        long[] best = { Long.MAX_VALUE };
        bruteRec(jobs, 0, new long[workers], best);
        return best[0];
    }

    static void bruteRec(long[] jobs, int at,
                         long[] loads, long[] best) {
        if (at == jobs.length) {
            long finish = 0;
            for (long x : loads) finish = Math.max(finish, x);
            best[0] = Math.min(best[0], finish);
            return;
        }
        for (int w = 0; w < loads.length; w++) {
            long before = loads[w];
            loads[w] = Math.addExact(before, jobs[at]);
            bruteRec(jobs, at + 1, loads, best);
            loads[w] = before;
        }
    }

    static void show(String name, Schedule s) {
        System.out.println(name + " loads="
                + Arrays.toString(s.loads())
                + ", makespan=" + s.makespan());
    }

    static final class Counts {
        int cases, lptSuboptimal, fifoWorseThanLpt;
        int boundViolations;
    }

    static void enumerateTests(long[] jobs, int at, Counts s) {
        if (at == jobs.length) {
            for (int workers = 1; workers <= 3; workers++) {
                long exact = exactOptimum(jobs, workers);
                long brute = bruteOptimum(jobs, workers);
                Schedule lpt = plan(jobs, workers, Strategy.LPT);
                Schedule fifo = plan(
                    jobs, workers, Strategy.FIFO_LIST);
                Schedule block = plan(
                    jobs, workers, Strategy.BLOCK);
                Schedule round = plan(
                    jobs, workers, Strategy.ROUND_ROBIN);

                if (exact != brute || exact < lowerBound(jobs,workers)
                    || lpt.makespan() < exact
                    || fifo.makespan() < exact
                    || block.makespan() < exact
                    || round.makespan() < exact)
                    s.boundViolations++;

                // Graham list scheduling:
                // P*C <= (2P-1)*OPT
                if ((long) workers * fifo.makespan()
                    > (2L * workers - 1) * exact)
                    s.boundViolations++;

                // Classical LPT bound:
                // 3P*C <= (4P-1)*OPT
                if (3L * workers * lpt.makespan()
                    > (4L * workers - 1) * exact)
                    s.boundViolations++;

                if (lpt.makespan() > exact) s.lptSuboptimal++;
                if (fifo.makespan() > lpt.makespan())
                    s.fifoWorseThanLpt++;
                s.cases++;
            }
            return;
        }
        for (long p = 1; p <= 3; p++) {
            jobs[at] = p;
            enumerateTests(jobs, at + 1, s);
        }
    }

    static Counts verify() {
        Counts s = new Counts();
        for (int n = 1; n <= 7; n++)
            enumerateTests(new long[n], 0, s);

        if (s.cases != 9837
            || s.lptSuboptimal != 136
            || s.fifoWorseThanLpt != 2368
            || s.boundViolations != 0)
            throw new AssertionError(
                "Unexpected exhaustive test statistics");
        return s;
    }

    // Pure deterministic workload; NOT a reliable benchmark.
    static long checksum(long weight) {
        long iterations = Math.multiplyExact(weight, 1000L);
        long acc = 0;
        for (long i = 0; i < iterations; i++)
            acc += i % 17;
        return acc;
    }

    // Executes concurrently, but gathers Future results in input
    // order and compares each with a sequential computation.
    static boolean parallelMatchesSequential(
            long[] jobs, int workers) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        try {
            List<Callable<Long>> tasks = new ArrayList<>();
            for (long p : jobs) {
                final long weight = p;
                tasks.add(() -> checksum(weight));
            }
            List<Future<Long>> futures = pool.invokeAll(tasks);
            for (int i = 0; i < jobs.length; i++) {
                if (futures.get(i).get() != checksum(jobs[i]))
                    return false;
            }
            return true;
        } finally {
            pool.shutdown();
        }
    }

    public static void main(String[] args) throws Exception {
        long[] jobs = {5,1,9,2,10,3,6};
        int p = 3;
        System.out.println("jobs=" + Arrays.toString(jobs)
                + ", workers=" + p);
        System.out.println("W=" + totalWork(jobs)
                + ", lowerBound=" + lowerBound(jobs,p));
        show("BLOCK", plan(jobs,p,Strategy.BLOCK));
        show("ROUND_ROBIN",
             plan(jobs,p,Strategy.ROUND_ROBIN));
        show("FIFO_LIST",
             plan(jobs,p,Strategy.FIFO_LIST));
        Schedule lpt = plan(jobs,p,Strategy.LPT);
        show("LPT", lpt);
        long opt = exactOptimum(jobs,p);
        System.out.println("OPT=" + opt);
        System.out.println("LPT.ownerByJob="
                + Arrays.toString(lpt.owner()));
        System.out.println("LPT.optimal=" + (lpt.makespan() == opt));

        long[] skew = {20,1,1,1,1,1,1,1,1};
        System.out.println("SKEW jobs="
            + Arrays.toString(skew) + ", workers=3");
        System.out.println("SKEW.W=" + totalWork(skew)
            + ", lowerBound=" + lowerBound(skew,3));
        show("SKEW.BLOCK", plan(skew,3,Strategy.BLOCK));
        show("SKEW.FIFO_LIST",
             plan(skew,3,Strategy.FIFO_LIST));
        show("SKEW.LPT", plan(skew,3,Strategy.LPT));
        System.out.println("SKEW.OPT="
            + exactOptimum(skew,3));

        long[] tight = {2,2,2,3,3};
        Schedule tightLpt = plan(tight,2,Strategy.LPT);
        long tightOpt = exactOptimum(tight,2);
        System.out.println("TIGHT jobs="
            + Arrays.toString(tight) + ", workers=2");
        show("TIGHT.LPT", tightLpt);
        System.out.println("TIGHT.OPT=" + tightOpt);
        System.out.println("TIGHT.ratio="
            + String.format(Locale.ROOT, "%.3f",
                (double) tightLpt.makespan() / tightOpt));

        System.out.println("parallel.sameAsSequential="
            + parallelMatchesSequential(jobs,p));

        Counts checked = verify();
        System.out.println("verified.cases=" + checked.cases);
        System.out.println("verified.lptSuboptimal="
            + checked.lptSuboptimal);
        System.out.println("verified.fifoWorseThanLpt="
            + checked.fifoWorseThanLpt);
        System.out.println("verified.boundViolations="
            + checked.boundViolations);
        System.out.println("verification=PASS");
    }
}
~~~

Lưu đúng tên **UnevenParallelTasksDemo.java** rồi chạy:

~~~bash
javac UnevenParallelTasksDemo.java
java UnevenParallelTasksDemo
~~~

**Stdout dự kiến:**

~~~text
jobs=[5, 1, 9, 2, 10, 3, 6], workers=3
W=36, lowerBound=12
BLOCK loads=[15, 15, 6], makespan=15
ROUND_ROBIN loads=[13, 11, 12], makespan=13
FIFO_LIST loads=[14, 13, 9], makespan=14
LPT loads=[12, 12, 12], makespan=12
OPT=12
LPT.ownerByJob=[2, 2, 1, 0, 0, 1, 2]
LPT.optimal=true
SKEW jobs=[20, 1, 1, 1, 1, 1, 1, 1, 1], workers=3
SKEW.W=28, lowerBound=20
SKEW.BLOCK loads=[22, 3, 3], makespan=22
SKEW.FIFO_LIST loads=[20, 4, 4], makespan=20
SKEW.LPT loads=[20, 4, 4], makespan=20
SKEW.OPT=20
TIGHT jobs=[2, 2, 2, 3, 3], workers=2
TIGHT.LPT loads=[7, 5], makespan=7
TIGHT.OPT=6
TIGHT.ratio=1.167
parallel.sameAsSequential=true
verified.cases=9837
verified.lptSuboptimal=136
verified.fifoWorseThanLpt=2368
verified.boundViolations=0
verification=PASS
~~~

**Vì sao các số này tin cậy?**

- Tất cả schedule dùng cùng input, cùng số worker và các quy tắc tie cố định.
- Cận dưới tính bằng tổng \(W\) và task lớn nhất; hai oracle exact tìm OPT trên n nhỏ.
- Vét cạn 9.837 trường hợp đối chiếu hai oracle theo **cấu trúc khác nhau** và kiểm tra bất đẳng thức bảo đảm bằng số nguyên: `P*C <= (2P−1)*OPT` và `3P*C <= (4P−1)*OPT`. Tránh sai số double trong test bound.
- 136 trường hợp LPT không tối ưu cho biết **LPT không phải exact solver**.
- 2.368 trường hợp FIFO_LIST tệ hơn LPT trong tập nhỏ cho thấy sorted order có thể giúp; **không** khẳng định LPT luôn tốt hơn FIFO cho mọi dữ liệu thực hoặc mọi phân phối.
- `parallel.sameAsSequential=true` chỉ kiểm tra **kết quả tính toán của từng task**, **không** kiểm chứng thứ tự hoàn thành, speedup hay tính tối ưu runtime.

**Giới hạn tính chính xác:** `long` có thể tràn nếu tổng duration vượt phạm vi; code dùng `Math.addExact` để báo lỗi thay vì im lặng wrap. `exactOptimum` chỉ cho n≤11 và P≤4 vì tìm tối ưu phân công task là bài toán tổ hợp; không dùng oracle này cho hàng triệu task thực tế.

## 15. Tại sao chọn lịch tốt vẫn có thể chạy chậm?

Một lịch LPT có makespan mô phỏng 12 không có nghĩa Java fixed pool sẽ hoàn tất trong đúng 12 đơn vị thời gian. Ngoài thời lượng CPU thuần còn có:

1. **Dispatch/queue overhead:** task 1ms có thể bị overhead lớn nếu tạo hàng triệu Future.
2. **Memory contention:** ba worker cùng đọc dữ liệu lớn có thể cùng chạm giới hạn băng thông, khiến tổng runtime tăng.
3. **False sharing:** các worker ghi các biến nằm chung cache line, gây invalidation dù chúng không ghi cùng biến.
4. **GC/allocation:** code có nhiều task object có thể tạo GC pause; CPU hữu ích không tăng tuyến tính theo P.
5. **I/O wait:** task có thể bị chặn bởi network, disk, connection pool; số threads hữu ích khác CPU-bound tasks.
6. **Data locality:** chuyển task sang worker khác có thể mất cache/NUMA locality và chi phí transfer.
7. **Synchronization:** khóa/counter global/shared queue có thể thành nút cổ chai.
8. **Skew không quan sát được:** task có duration dự báo 1 nhưng chạy thật 20 do dữ liệu khác thường.
9. **Dependencies:** một task dài nằm trên critical path dù tổng việc đủ lớn.
10. **Worker heterogeneity:** core và node chạy khác tốc độ, cùng “số lượng task” không cùng tốc độ hoàn thành.

Để benchmark công bằng, cần ghi **thời gian thực** sau khi chờ **toàn bộ** Future kết thúc, lặp nhiều lần, có warm-up và phân vị, theo dõi CPU time, wall-clock, queue wait, GC và dữ liệu. Đừng đo “time to submit tasks” rồi báo là makespan, vì phần lớn Future có thể chưa hoàn tất.

## 16. Worker đồng nhất và worker khác tốc độ

Đề bài trọng tâm là **bài toán con có kích thước khác nhau**; các công thức bảo đảm trước đây giả định worker **cùng tốc độ**. Trên hệ thống hỗn hợp CPU/GPU hoặc cluster node khác tốc độ, mỗi worker w có thể có tốc độ \(s_w\), thời gian job i trở thành \(p_i/s_w\) trong mô hình related machines; nếu mỗi job có chi phí khác nhau tùy máy, dùng ma trận thời gian \(p_{i,w}\) (unrelated machines).

Trong các mô hình đó, LPT với “worker có tổng duration danh nghĩa thấp nhất” có thể sai vì không xét tốc độ, affinity hoặc dữ liệu. Scheduler cần dự báo **thời điểm hoàn thành thực theo từng worker**, chứ không chỉ số job hoặc tổng kích thước input.

**Đừng dùng nguyên định lý LPT \(4/3-1/(3P)\)** cho heterogeneous-speed/unrelated machines, release dates, preemption, DAG hay memory-constrained placement. Phải chỉ rõ mô hình và dùng cận/thuật toán phù hợp.

## 17. Checklist áp dụng trong dự án

- [ ] Các task độc lập hay có DAG dependencies? Nếu có, tính critical path/span.
- [ ] Một task có chia nhỏ/di chuyển được không? Nếu không, task lớn nhất là cận thời gian.
- [ ] Chi phí có dự đoán được không? Có thể đo lịch sử hay sampling không?
- [ ] Worker có thật sự đồng nhất và cùng tốc độ xử lý loại task này không?
- [ ] Bắt đầu từ **W, max(p), W/P** trước khi tối ưu scheduler.
- [ ] Dùng **block** khi locality cao và thời lượng khá đều; không mặc định block tối ưu.
- [ ] Dùng **round-robin** khi muốn chia đều số lượng nhưng không có ước lượng đáng tin, rồi đo skew.
- [ ] Dùng **FIFO/dynamic queue** khi chi phí khó biết và task độc lập sẵn sàng.
- [ ] Dùng **LPT** khi có ước lượng tốt và có thể sắp xếp toàn bộ task trước.
- [ ] Dùng **work stealing** khi task sinh con động/không đều và có thể chuyển.
- [ ] Chọn granularity đủ lớn so với overhead, đủ nhỏ để tránh worker nhàn.
- [ ] Không coi work stealing là preemption của task đang chạy.
- [ ] Quản lý bounded queue, backpressure và memory trong hệ thống có lưu lượng cao.
- [ ] Tách mô phỏng lý tưởng khỏi benchmark có JIT/GC/OS scheduling.
- [ ] Đo makespan, speedup, efficiency, CPU utilization, queue wait và P95/P99 latency khi phù hợp.
- [ ] Dùng oracle exact chỉ trên input nhỏ, không thay thế bằng heuristic rồi gọi là OPT.
- [ ] Kiểm các tình huống P=1, P>n, mọi job bằng nhau, một job rất lớn, nhiều job bé.
- [ ] Tránh overflow trong W, duration, lower bound và tải worker.
- [ ] Có test chéo với mô hình brute-force khác cấu trúc trước khi tối ưu hóa sâu.

## 18. Bài tập có đáp án

**Bài 1.** Cân bằng số lượng task có đồng nghĩa với cân bằng thời gian chạy không?

*Đáp án:* Không. Duration khác nhau khiến hai worker cùng số task có tổng tải khác nhau.

**Bài 2.** Makespan của một lịch không preemptive trên P worker là gì?

*Đáp án:* Giá trị lớn nhất trong tải thời gian của các worker.

**Bài 3.** Hai cận dưới cơ bản của OPT là gì?

*Đáp án:* Task dài nhất và tổng công việc chia cho số worker.

**Bài 4.** Với W=36, P=3, max task10, lower bound nguyên?

*Đáp án:* Max(10,ceil(36/3))=12.

**Bài 5.** Một lịch đạt makespan bằng lower bound có tối ưu không?

*Đáp án:* Có, vì không lịch nào có thể thấp hơn cận dưới.

**Bài 6.** Với jobs [9,8,7,6,5,4,3,2,1], P=3, block 3 task mỗi worker cho tải nào?

*Đáp án:* [24,15,6], makespan24.

**Bài 7.** Với dãy bài 6, round-robin cho tải nào?

*Đáp án:* [18,15,12], makespan18.

**Bài 8.** FIFO_LIST chọn worker nào cho task mới?

*Đáp án:* Worker có tổng tải đã gán nhỏ nhất; hòa chọn ID nhỏ trong demo.

**Bài 9.** Bảo đảm của list scheduling trong mô hình máy đồng nhất là gì?

*Đáp án:* Makespan không quá \((2-1/P)OPT\).

**Bài 10.** Bước quan trọng trong chứng minh cận list scheduling?

*Đáp án:* Với task j kết thúc cuối và start s, trước khi gán j các P worker đều có tải ít nhất s, nên \(P s\le W-p_j\).

**Bài 11.** LPT làm gì trước khi phân công?

*Đáp án:* Sắp task theo thời gian giảm dần, rồi luôn gán job tiếp theo tới worker ít tải nhất.

**Bài 12.** Với jobs [5,1,9,2,10,3,6], P3, LPT cho tải nào?

*Đáp án:* [12,12,12], OPT12.

**Bài 13.** Với bài 12, FIFO_LIST cho makespan bao nhiêu?

*Đáp án:* 14.

**Bài 14.** LPT có luôn tìm đúng lịch tối ưu không?

*Đáp án:* Không. [2,2,2,3,3] với P2 có LPT7 nhưng OPT6.

**Bài 15.** LPT/OPT của phản ví dụ bài 14 là bao nhiêu?

*Đáp án:* 7/6≈1,1667.

**Bài 16.** Bảo đảm LPT cổ điển cho các máy đồng nhất là gì?

*Đáp án:* \(C^{LPT}_{max}\le(4/3-1/(3P))OPT\) với P≥2 và giả thiết task độc lập, duration đã biết.

**Bài 17.** Với P=2, cận LPT là bao nhiêu?

*Đáp án:* \(4/3-1/6=7/6\).

**Bài 18.** Một dãy có job20 và tám job1, P3, OPT tối thiểu?

*Đáp án:* 20 vì có task không chia nhỏ dài20; FIFO/LPT đạt20.

**Bài 19.** Speedup tối đa lý tưởng của dãy bài 18 so với một worker?

*Đáp án:* W/20=28/20=1,4.

**Bài 20.** Thêm 10 worker có vượt qua bottleneck task20 không?

*Đáp án:* Không, trừ khi task ấy có thể tách hoặc mô hình thay đổi.

**Bài 21.** Vì sao chia mọi job thành hàng triệu task rất nhỏ có thể chậm hơn?

*Đáp án:* Queue/dispatch, allocation, lock và GC overhead lớn hơn lợi ích cân bằng.

**Bài 22.** Vì sao task quá lớn cũng không tốt?

*Đáp án:* Worker khác nhàn rỗi trong khi task nặng không thể di chuyển/chia.

**Bài 23.** Work stealing thường lấy loại công việc nào?

*Đáp án:* Task chưa chạy hoặc được tách hợp lệ trong deque worker khác; không tự preempt một task nguyên khối đang chạy.

**Bài 24.** Java cung cấp cơ chế work stealing cho fork/join qua lớp nào?

*Đáp án:* ForkJoinPool và các ForkJoinTask/RecursiveTask phù hợp.

**Bài 25.** `newFixedThreadPool(P)` có bảo đảm hoàn thành task theo thứ tự submit không?

*Đáp án:* Không; thứ tự thực thi/kết thúc phụ thuộc scheduler và thời gian chạy.

**Bài 26.** `invokeAll` trả danh sách Future theo thứ tự gì?

*Đáp án:* Theo thứ tự collection task truyền vào, dù các task có thể chạy/kết thúc theo thứ tự khác.

**Bài 27.** `parallel.sameAsSequential=true` chứng minh speedup không?

*Đáp án:* Không; chỉ xác nhận đầu ra từng task trùng bản tuần tự.

**Bài 28.** Nếu task có quan hệ phụ thuộc, cận dưới nào phải bổ sung?

*Đáp án:* Critical path/span S: \(T_P\ge\max(W/P,S)\).

**Bài 29.** Dữ liệu dùng để ước lượng duration sai thì bound LPT trên duration dự báo có còn là bound cho runtime thật không?

*Đáp án:* Không tự động; bảo đảm yêu cầu processing times đúng trong mô hình chứng minh.

**Bài 30.** LPT cổ điển có áp dụng nguyên xi cho worker có tốc độ khác nhau không?

*Đáp án:* Không; cần mô hình related/unrelated machines và thuật toán phù hợp.

**Bài 31.** Bộ vét cạn 9.837 ca có tự chứng minh theorem LPT không?

*Đáp án:* Không. Nó kiểm tra một miền hữu hạn; định lý toán học có giả thiết riêng.

**Bài 32.** Vì sao oracle exact không nên dùng trực tiếp cho một triệu task?

*Đáp án:* Tối ưu phân công tổng quát có số phương án tăng tổ hợp; oracle chỉ dành cho bài nhỏ.

**Bài 33.** Block và round-robin có luôn đạt cận list scheduling \(2-1/P\) không?

*Đáp án:* Không. Hai cách này có thể phân công tĩnh gây worker nhàn dù còn nhiều việc trên worker khác; chứng minh cận trên dùng điều kiện list scheduling chọn worker ít tải.

**Bài 34.** Khi một worker xong sớm và queue còn task, một scheduler work-conserving nên làm gì?

*Đáp án:* Giao ngay một task hợp lệ khác nếu không vướng ràng buộc tài nguyên hoặc phụ thuộc.

**Bài 35.** Speedup lý tưởng khác speedup đo bằng wall-clock thế nào?

*Đáp án:* Lý tưởng dùng tổng thời lượng W và makespan mô phỏng; thực tế đo thời gian chạy tuần tự và song song, chịu overhead/GC/OS/I/O.

**Bài 36.** Khi nào ưu tiên locality dù tải chưa hoàn toàn bằng nhau?

*Đáp án:* Khi chi phí chuyển dữ liệu/NUMA/cache hoặc truyền mạng lớn hơn lợi ích giảm chênh lệch thời gian tính toán.

## Tổng kết

**Cân bằng tải** là giảm thời điểm kết thúc của worker chậm nhất, không chỉ phân chia đều số task. Với task độc lập, worker đồng nhất và duration đã biết, ta dùng \(C_{\max}\), \(W\), \(LB=\max(\max p_i,W/P)\) để đánh giá lịch. **List scheduling** với worker ít tải có cận \(2-1/P\), còn **LPT** ưu tiên task dài có cận mạnh hơn \(4/3-1/(3P)\) trong mô hình chuẩn, nhưng vẫn có phản ví dụ không tối ưu.

Với thời lượng biến thiên và khó biết trước, **dynamic queue, chia nhỏ có ngưỡng, work stealing** giúp worker rảnh nhận thêm việc, miễn task còn có thể phân tách/di chuyển. Không scheduler nào vượt cận do **task nguyên khối dài nhất** hoặc critical path của DAG. Trên hệ thống thật, overhead, locality, shared resource, worker speed và lỗi ước lượng quyết định hiệu quả cuối cùng. Cần kết hợp **phân tích toán học, oracle trên bài nhỏ, kiểm thử thuộc tính và benchmark thực tế** trước khi kết luận chiến lược nào phù hợp nhất.
