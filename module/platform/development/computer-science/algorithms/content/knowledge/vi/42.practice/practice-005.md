# Lập lịch và phân bổ nguồn lực theo các ràng buộc khác nhau

**Chủ đề:** Computer Science Algorithms · Thực hành tổng hợp

## 1. Bài toán lập lịch là gì?

**Lập lịch (scheduling)** quyết định công việc nào được thực hiện, bắt đầu lúc nào, kết thúc lúc nào và chạy trên tài nguyên nào. **Phân bổ nguồn lực (resource allocation)** quyết định mỗi công việc nhận máy, nhân lực, thiết bị, ngân sách hoặc năng lực xử lý nào.

Một bài toán thực tế thường có:
- Nhiều công việc với thời lượng và mức ưu tiên khác nhau.
- Một hoặc nhiều máy/nhân viên/tài nguyên.
- Thời điểm sẵn sàng, deadline, thời gian nghỉ hoặc thời gian bảo trì.
- Quan hệ phụ thuộc giữa công việc.
- Giới hạn số lượng tài nguyên có thể dùng cùng lúc.
- Mục tiêu tối ưu như hoàn tất sớm, lợi nhuận cao, ít trễ hạn hoặc sử dụng tài nguyên cân bằng.

Ví dụ, một đội vận hành có 8 kỹ thuật viên, mỗi người có kỹ năng khác nhau. Mỗi yêu cầu bảo trì cần một khoảng thời gian, một nhóm kỹ năng và có deadline. Không thể chỉ sắp xếp theo deadline rồi giao tùy ý: một kỹ thuật viên không thể xử lý hai việc cùng thời điểm, một công việc có thể phải chờ công việc trước, và một số thiết bị chỉ có số lượng giới hạn.

Cần phân biệt:
- **Scheduling:** chọn thứ tự và thời điểm thực hiện.
- **Assignment:** gán công việc cho tài nguyên.
- **Allocation:** cấp một lượng tài nguyên có giới hạn cho từng công việc.
- **Routing:** chọn đường đi hoặc chuỗi máy/trạm mà công việc phải qua.

Nhiều bài toán kết hợp cả bốn. Chọn thuật toán đúng bắt đầu từ việc mô tả rõ **công việc, tài nguyên, ràng buộc và mục tiêu**.

## 2. Mô hình hóa công việc và tài nguyên

Gọi J là tập công việc. Với mỗi công việc j, có thể có:

| Ký hiệu | Ý nghĩa |
|---|---|
| p_j | Thời lượng xử lý |
| s_j | Thời điểm bắt đầu |
| c_j | Thời điểm hoàn tất, thường c_j=s_j+p_j |
| r_j | Release time: thời điểm sớm nhất được bắt đầu |
| d_j | Deadline hoặc due date |
| w_j | Trọng số/giá trị/lợi ích |
| q_jr | Lượng tài nguyên loại r mà công việc j cần |
| M_j | Tập máy/tài nguyên đủ điều kiện xử lý j |
| pred(j) | Các công việc phải hoàn thành trước j |

Mỗi tài nguyên r có thể có:
- Năng lực cố định C_r.
- Năng lực thay đổi theo thời gian C_r(t).
- Lịch sẵn sàng và bảo trì.
- Kỹ năng hoặc loại công việc được phép.
- Chi phí sử dụng.

Nếu các công việc chiếm một khoảng thời gian liên tục, dùng quy ước khoảng nửa mở **[s_j,c_j)**: thời điểm bắt đầu được tính, thời điểm kết thúc không còn chiếm tài nguyên. Vì thế hai việc [1,3) và [3,5) có thể chạy nối tiếp trên cùng một máy.

### 2.1. Ràng buộc thời gian

**Release time:**

\[
s_j\ge r_j.
\]

Công việc không được bắt đầu trước khi tài nguyên hoặc dữ liệu sẵn sàng.

**Deadline cứng:**

\[
c_j\le d_j.
\]

Nếu không thể đáp ứng, lịch đó không hợp lệ.

**Due date mềm:** công việc có thể hoàn tất trễ, nhưng bị tính phạt. Ví dụ tardiness:

\[
T_j=\max(0,c_j-d_j).
\]

**Precedence (phụ thuộc trước-sau):**

\[
s_j\ge c_i\quad\text{nếu }i\to j.
\]

Công việc j chỉ được bắt đầu sau khi i hoàn tất.

### 2.2. Ràng buộc tài nguyên

Với tài nguyên r có sức chứa C_r(t), tại mọi thời điểm t:

\[
\boxed{
\sum_{j:\ s_j\le t<c_j}q_{jr}\le C_r(t).
}
\]

Tổng nhu cầu của các công việc đang chạy không được vượt năng lực hiện có.

Ví dụ có 4 CPU cores, một job dùng 2 cores, một job dùng 1 core và một job dùng 2 cores. Nếu chạy đồng thời cả ba thì nhu cầu 5 cores vượt giới hạn 4; ít nhất một job phải chờ.

Với máy đơn, mỗi máy chỉ chạy tối đa một công việc tại một thời điểm. Với tài nguyên có sức chứa nhiều đơn vị, nhiều công việc có thể cùng dùng miễn tổng nhu cầu không vượt capacity.

### 2.3. Ràng buộc gán máy

Nếu công việc j chỉ được chạy trên tập máy M_j, chỉ những phép gán m∈M_j mới hợp lệ. Một máy có thể có tốc độ xử lý khác nhau, nên thời lượng thực tế có thể là p_jm thay vì một p_j chung.

Trong bài toán gán người:
- Công việc có thể cần một kỹ năng.
- Nhân viên có tập kỹ năng và ca làm.
- Một người có thể không đủ điều kiện cho một số việc.
- Thời lượng hoặc chi phí phụ thuộc người được giao.

Chỉ kiểm tổng số người rảnh là chưa đủ; phải kiểm **đủ điều kiện**.

## 3. Xác định mục tiêu trước khi chọn thuật toán

Cùng một tập công việc có thể có nhiều lịch hợp lệ, nhưng “tốt nhất” phụ thuộc mục tiêu.

| Mục tiêu | Cách hiểu |
|---|---|
| Maximize job count | Hoàn thành nhiều công việc nhất |
| Maximize total value | Tối đa tổng lợi nhuận/điểm ưu tiên |
| Minimize makespan | Giảm thời điểm hoàn tất công việc cuối cùng |
| Minimize total completion time | Giảm tổng thời điểm hoàn tất |
| Minimize weighted completion | Ưu tiên việc có trọng số cao |
| Minimize tardiness | Giảm tổng hoặc mức trễ deadline |
| Maximize utilization | Tăng tỷ lệ tài nguyên đang hữu ích |
| Fairness | Tránh một người/tài nguyên luôn nhận việc nặng |
| Minimize cost | Giảm chi phí nhân công, máy hoặc năng lượng |

Không có một lịch tối ưu đồng thời cho mọi mục tiêu. Ví dụ:
- Chọn công việc ngắn có thể tăng số việc hoàn tất.
- Chọn việc có giá trị lớn có thể tăng lợi nhuận nhưng giảm số việc.
- Dồn việc vào một máy có thể giảm thời gian thiết lập nhưng gây mất cân bằng.
- Giữ capacity dự phòng có thể giảm utilization nhưng giúp chống sự cố và biến động.

### 3.1. Feasibility và optimality là hai câu hỏi khác nhau

**Feasibility:** lịch có thỏa tất cả ràng buộc không?

**Optimality:** trong các lịch hợp lệ, lịch này có tối ưu mục tiêu không?

Một thuật toán heuristic có thể luôn tạo lịch hợp lệ nhưng không đảm bảo tối ưu. Ngược lại, một mô hình tối ưu hóa có thể chứng minh tối ưu nếu solver hoàn tất và có chứng nhận phù hợp, nhưng thời gian giải có thể rất lớn.

Trong hệ thống thực, nên kiểm tính hợp lệ của lịch bằng một **validator độc lập** trước khi xuất lệnh thực thi.

## 4. Bài toán cơ bản: interval scheduling trên một tài nguyên

Giả sử có n công việc, mỗi việc chiếm một khoảng [start,end), tất cả dùng chung **một máy**, không có precedence, mọi việc có giá trị như nhau và không được preempt.

Mục tiêu: chọn nhiều công việc nhất sao cho không chồng lấn.

### 4.1. Greedy theo thời điểm kết thúc sớm nhất

Thuật toán:
1. Sắp xếp công việc theo end tăng dần.
2. Giữ lastEnd là thời điểm kết thúc của việc được chọn gần nhất.
3. Duyệt theo thứ tự đã sắp.
4. Chọn j nếu start_j≥lastEnd.
5. Cập nhật lastEnd=end_j.

Độ phức tạp O(n log n) do sort, phần duyệt O(n).

Ví dụ:

~~~text
A: [0,3)
B: [1,4)
C: [3,5)
D: [4,7)
E: [5,8)
F: [7,9)
~~~

Theo end tăng dần:
- Chọn A [0,3).
- B bắt đầu 1<3 nên bỏ.
- Chọn C [3,5).
- D bắt đầu 4<5 nên bỏ.
- Chọn E [5,8).
- F bắt đầu 7<8 nên bỏ.

Kết quả [A,C,E], tổng 3 công việc.

### 4.2. Vì sao greedy này tối ưu?

Gọi g là công việc kết thúc sớm nhất trong các việc còn lại. Xét một lịch tối ưu bất kỳ; công việc đầu tiên của lịch ấy là o.

Vì g kết thúc không muộn hơn o, thay o bằng g:
- Không giảm số công việc được chọn.
- Các công việc sau o vẫn bắt đầu sau hoặc tại end_o.
- Vì end_g≤end_o, chúng cũng bắt đầu sau hoặc tại end_g.

Do đó tồn tại một lịch tối ưu bắt đầu bằng g. Sau khi chọn g, phần còn lại là cùng bài toán trên các công việc có start≥end_g. Áp dụng quy nạp, greedy chọn tối ưu.

**Điều kiện quan trọng:** mục tiêu là số công việc, một tài nguyên, không có trọng số khác nhau, không có ràng buộc phụ thêm. Greedy earliest-finish không tự giải bài toán có lợi nhuận, precedence hay nhiều loại tài nguyên.

## 5. Khi công việc có giá trị khác nhau: weighted interval scheduling

Nếu mỗi công việc có lợi nhuận w_j, tối đa số lượng việc không còn tương đương tối đa lợi nhuận.

Ví dụ:
- A [0,3), value 5.
- B [1,4), value 6.
- C [3,5), value 5.
- D [4,7), value 8.
- E [5,8), value 4.
- F [7,9), value 3.

Greedy earliest-finish chọn A,C,E với tổng giá trị 14. Lịch B,D,F hợp lệ và có tổng 17, tốt hơn.

### 5.1. Dynamic programming

Sắp xếp theo end tăng dần. Đánh số việc từ 1 đến n. Gọi p(i) là chỉ số lớn nhất j<i sao cho:

\[
end_j\le start_i.
\]

Nếu không có việc tương thích trước i thì p(i)=0.

Định nghĩa OPT(i) là giá trị lớn nhất từ i công việc đầu tiên:

\[
\boxed{
OPT(i)=\max\left(
OPT(i-1),
w_i+OPT(p(i))
\right)
}
\]

với OPT(0)=0 nếu được phép không chọn việc nào.

Hai lựa chọn:
- Bỏ công việc i, lấy OPT(i−1).
- Chọn i, khi đó chỉ có thể kết hợp với các việc kết thúc trước start_i; giá trị là w_i+OPT(p(i)).

Tính p(i) bằng binary search vì danh sách đã sort theo end. Toàn bộ DP có O(n log n) thời gian và O(n) bộ nhớ. Có thể truy vết quyết định để lấy các việc được chọn.

Nếu tất cả w_j âm và được phép không làm việc, đáp án 0 với lịch rỗng. Nếu đặc tả bắt buộc chọn ít nhất một việc, base case và xử lý kết quả phải thay đổi.

### 5.2. Tại sao không dùng greedy theo value lớn nhất?

Chọn job có value cao nhất trước có thể chặn hai job khác có tổng value lớn hơn. Ví dụ:
- X [0,10), value 12.
- Y [0,5), value 8.
- Z [5,10), value 8.

Greedy chọn X được 12, trong khi Y+Z được 16. Cần DP vì quyết định hiện tại ảnh hưởng tập lựa chọn tương thích phía sau.

## 6. Nhiều tài nguyên giống nhau: capacity k

Giả sử có k máy giống nhau. Mỗi công việc cần đúng một máy trong toàn bộ khoảng [start,end), không preempt, tất cả có giá trị bằng nhau và mục tiêu là **tối đa số công việc**.

Một lịch hợp lệ cần bảo đảm tại mọi thời điểm không có quá k công việc được chọn đang chạy.

### 6.1. Chọn tập công việc có độ chồng lấn tối đa k

Một thuật toán greedy:
1. Sắp công việc theo start tăng dần.
2. Duy trì tập active gồm các công việc đã chọn nhưng chưa kết thúc tại start hiện tại.
3. Loại khỏi active các việc có end≤start hiện tại.
4. Thêm công việc mới.
5. Nếu active có hơn k việc, bỏ việc có **end lớn nhất** trong active.

Vì mọi việc active đều đã bắt đầu và chưa kết thúc tại thời điểm hiện tại, chúng cùng chồng lấn ở thời điểm ấy. Nếu có k+1 việc, ít nhất một phải bị bỏ. Bỏ việc kết thúc muộn nhất giữ lại những khoảng kết thúc sớm hơn, nên để lại nhiều cơ hội nhất cho các công việc tương lai.

Có thể cài active bằng TreeSet theo end tăng dần:
- first() là việc kết thúc sớm nhất, dùng để loại việc đã hết.
- last() là việc kết thúc muộn nhất, dùng khi phải loại một việc do vượt capacity.

Thuật toán này tối đa số lượng interval khi các tài nguyên **giống nhau**, mỗi job dùng một đơn vị, không có giá trị/ưu tiên khác nhau và không có ràng buộc phụ.

### 6.2. Gán các việc đã chọn vào từng máy

Sau khi tập được chọn có độ chồng lấn không vượt k, sắp chúng theo start. Duy trì min-heap các máy theo thời điểm sẵn sàng:
- Nếu máy rảnh sớm nhất có availableAt≤start_j, tái sử dụng máy đó.
- Nếu chưa có máy rảnh nhưng đã dùng ít hơn k máy, mở một máy mới.
- Nếu không còn máy nào mà mọi máy đều bận, lịch chọn đã vi phạm capacity hoặc bước gán bị lỗi.

Đây là **interval partitioning**: khi số khoảng chồng lấn tối đa là k, chúng có thể được phân vào tối đa k máy sao cho mỗi máy nhận những khoảng không giao nhau.

### 6.3. Ví dụ hai máy

~~~text
R1 [0,4)
R2 [1,3)
R3 [2,5)
R4 [3,6)
R5 [4,7)
R6 [5,8)
R7 [6,9)
R8 [7,10)
~~~

Với k=2, tập được chọn tối ưu có thể là:

~~~text
R1, R2, R4, R5, R7, R8
~~~

Gán máy:
- M1: R1 [0,4), R5 [4,7), R8 [7,10).
- M2: R2 [1,3), R4 [3,6), R7 [6,9).

Có 6 công việc, không có hai việc cùng máy chồng lấn và tại mọi thời điểm tổng số việc đang chạy không vượt 2. R3 và R6 bị bỏ vì khi thêm chúng, tập active sẽ vượt capacity; bỏ interval kết thúc muộn nhất giữ được các khoảng kết thúc sớm hơn.

**Không áp dụng nguyên xi** cho bài toán có trọng số khác nhau, nhiều loại tài nguyên, thời lượng phụ thuộc máy hoặc precedence. Những thay đổi đó tạo ra bài toán khác.

## 7. Precedence và lập lịch dự án

Trong dự án, công việc có thể phụ thuộc nhau theo đồ thị có hướng. Nếu có cạnh i→j, i phải hoàn tất trước j.

Nếu đồ thị precedence là DAG:
- Topological sort cho một thứ tự hợp lệ.
- Earliest start/finish có thể tính bằng đường dài nhất trên DAG.
- Đường găng (critical path) là chuỗi phụ thuộc có tổng thời lượng lớn nhất.
- Thời lượng dự án tối thiểu nếu bỏ qua tranh chấp tài nguyên bằng độ dài đường găng.

Ví dụ:

~~~text
A (3 ngày) -> C (4 ngày) -> E (2 ngày)
B (5 ngày) -> D (1 ngày) -> E (2 ngày)
~~~

Nhánh A→C kết thúc sau 7 ngày, nhánh B→D sau 6 ngày. E chỉ bắt đầu khi cả C và D hoàn tất, nên sớm nhất ngày 7; dự án kết thúc ngày 9. Đường A→C→E là critical path.

### 7.1. Có precedence chưa chắc có tài nguyên

Nếu bỏ qua giới hạn nhân lực/máy, tính critical path có thể cho một lịch hợp lệ theo precedence nhưng không thể thực thi vì hai việc cần cùng một kỹ thuật viên.

Khi vừa có precedence vừa có capacity tài nguyên, đó là **Resource-Constrained Project Scheduling Problem (RCPSP)**. Bài toán tổng quát khó; nhiều biến thể là NP-hard. Cần phối hợp:
- Ràng buộc precedence.
- Cumulative resource constraints.
- Deadline/due dates.
- Mục tiêu makespan hoặc chi phí.
- Các quyết định về thời điểm và phân bổ.

Không thể giải RCPSP tổng quát chỉ bằng topological sort hay critical path.

## 8. Assignment: giao việc cho người hoặc máy

Nếu mỗi công việc cần đúng một người/máy, và mỗi tài nguyên nhận tối đa một công việc trong một đợt, có thể mô hình thành **bài toán ghép cặp hai phía**:
- Phía trái: công việc.
- Phía phải: người/máy.
- Cạnh j→m tồn tại nếu m đủ điều kiện làm j.
- Cost trên cạnh là thời gian, tiền, năng lượng hoặc penalty.

Nếu cần gán mọi công việc và mỗi máy nhận tối đa một việc, bài toán assignment có thể giải bằng Hungarian algorithm (ma trận chi phí vuông hoặc được mở rộng bằng dummy nodes). Nếu chỉ một số công việc được chọn, hoặc có capacity/luồng, **min-cost max-flow** có thể phù hợp.

Nếu một người có thể nhận nhiều công việc nhưng các khoảng thời gian không chồng lấn, assignment trở thành bài toán lập lịch theo tài nguyên, không còn là một matching tĩnh đơn giản.

### 8.1. Kỹ năng và eligibility

Không được gán một công việc chỉ vì người đó rảnh. Cần kiểm:
- Kỹ năng bắt buộc.
- Chứng chỉ/hạn mức.
- Địa điểm và ca làm.
- Thiết bị hoặc quyền truy cập.
- Số việc đang nhận và thời gian nghỉ.
- Chi phí và ưu tiên.

Có thể tạo tập eligible M_j trước, rồi chỉ cho phép assignment trên các cạnh hợp lệ.

## 9. Nhiều loại tài nguyên và capacity thay đổi

Một công việc có thể đồng thời cần:
- 1 máy.
- 2 kỹ thuật viên.
- 4 CPU cores.
- 8 GB RAM.
- Một thiết bị chuyên dụng.
- Ngân sách hoặc năng lượng.

Nếu q_jr là nhu cầu tài nguyên r, ràng buộc cumulative phải thỏa với **từng loại r**. Một lịch có đủ máy vẫn có thể không khả thi vì thiếu kỹ thuật viên hoặc bộ nhớ.

Capacity có thể thay đổi theo thời gian:
- Nhân viên đổi ca.
- Máy bảo trì.
- Hạn mức cloud tăng/giảm.
- Năng lượng bị giới hạn vào giờ cao điểm.

Khi đó C_r(t) không cố định. Mô hình cần biểu diễn lịch sẵn sàng hoặc chia horizon thành các đoạn thời gian có capacity riêng.

### 9.1. Thời gian rời rạc và liên tục

**Time-indexed model:** chia thời gian thành slot, quyết định công việc bắt đầu ở slot nào. Dễ biểu diễn capacity theo từng slot nhưng số biến có thể rất lớn và độ phân giải phụ thuộc bước thời gian.

**Continuous-time model:** dùng biến start/finish và ràng buộc thứ tự/non-overlap. Mô hình gọn hơn trong một số bài, nhưng các ràng buộc thứ tự có thể phức tạp.

Không nên làm tròn thời lượng 7,5 phút thành 8 phút mà không xem ảnh hưởng đến tính khả thi, deadline và tổng capacity.

## 10. Preemption, setup và các ràng buộc thực tế

### 10.1. Preemptive và non-preemptive

**Non-preemptive:** khi bắt đầu, công việc chạy liên tục đến khi hoàn tất. Các ví dụ interval scheduling ở trên giả định loại này.

**Preemptive:** có thể tạm dừng rồi tiếp tục sau, có thể đổi máy hoặc không tùy đặc tả. Khi preemption được phép, một khoảng [start,end) không còn mô tả đủ thời gian thực thi; phải mô hình hóa các đoạn processing hoặc tổng thời gian chạy.

### 10.2. Setup time

Đổi từ công việc i sang j có thể mất thời gian chuẩn bị s_ij. Khi đó điều kiện tương thích có thể là:

\[
s_j\ge c_i+s_{ij}.
\]

Nếu setup phụ thuộc thứ tự, s_ij có thể khác s_ji. Greedy earliest-finish đơn giản không giải được toàn bộ bài toán sequence-dependent setup.

### 10.3. Maintenance và unavailable windows

Máy có thể không sẵn sàng trong [u,v). Cần xem khoảng bảo trì như một block đã chiếm máy, hoặc đưa unavailable windows vào constraint model. Đừng chỉ kiểm việc-với-việc mà quên lịch bảo trì.

### 10.4. Deadline mềm và penalty

Một mục tiêu có thể là:

\[
\min\sum_j w_j\max(0,c_j-d_j).
\]

w_j lớn có nghĩa trễ công việc đó bị phạt nhiều hơn. Đây là bài toán khác với maximize job count hay earliest finish.

### 10.5. Lịch động và online

Trong môi trường online, công việc mới đến liên tục và thời lượng thực tế có thể khác dự kiến. Scheduler cần quyết định dựa trên thông tin hiện có, đôi khi phải sửa lịch đã tạo:
- Rolling horizon: tối ưu một khoảng tương lai rồi cập nhật.
- Rescheduling: tính lại khi job mới, hỏng máy hoặc deadline đổi.
- Freeze window: giữ cố định các việc sắp bắt đầu.
- Buffer/slack: dự phòng cho biến động và sự cố.

Lịch tối ưu cho một snapshot tĩnh có thể không tốt khi dữ liệu thay đổi sau vài phút.

## 11. Chọn thuật toán theo cấu trúc bài toán

| Cấu trúc | Hướng tiếp cận thường phù hợp | Bảo đảm |
|---|---|---|
| Một máy, interval, tối đa số việc | Greedy earliest finish | Tối ưu cho đúng mô hình |
| Một máy, interval có profit | Weighted interval DP | Tối ưu O(n log n) |
| k máy giống nhau, interval, tối đa số việc | Greedy capacity-k + partition | Tối ưu cho đúng mô hình |
| DAG precedence, bỏ qua tranh chấp tài nguyên | Topological order + critical path | Tính earliest schedule |
| Gán một việc cho một máy, chi phí và eligibility | Matching/Hungarian/min-cost flow | Tối ưu theo mô hình |
| Nhiều tài nguyên cumulative + precedence | CP-SAT/MILP/RCPSP | Exact nếu solver chứng minh tối ưu |
| Bài lớn cần đáp án nhanh | List scheduling, greedy, local search | Thường là heuristic |
| Thời lượng không chắc chắn | Robust/stochastic optimization | Phụ thuộc mô hình xác suất |

### 11.1. Exact methods

**Dynamic programming:** khai thác cấu trúc con tối ưu, như weighted interval scheduling.

**Min-cost flow / matching:** tốt khi quyết định gán có cấu trúc mạng và capacity rõ.

**MILP:** dùng biến nguyên/nhị phân và ràng buộc tuyến tính; linh hoạt nhưng có thể khó giải ở quy mô lớn.

**Constraint programming / CP-SAT:** biểu diễn interval variables, precedence, optional intervals, cumulative resource constraints và mục tiêu; phù hợp nhiều bài lập lịch tổ hợp.

**Branch and bound:** tìm kiếm không gian phương án, dùng cận để cắt nhánh không thể tốt hơn incumbent.

Exact solver có thể dừng ở trạng thái feasible hoặc time limit mà **chưa chứng minh optimality**. Cần đọc status, objective bound và gap; không gọi một nghiệm khả thi là “đã tối ưu” khi solver chưa chứng minh.

### 11.2. Heuristics và metaheuristics

Khi bài toán lớn hoặc cần lịch rất nhanh:
- **List scheduling:** chọn công việc sẵn sàng theo priority rule.
- **Shortest processing time (SPT):** ưu tiên việc ngắn trong một số mục tiêu tổng completion time.
- **Longest processing time (LPT):** phân việc dài trước cho máy đang rảnh để cân bằng tải trong một số bài makespan.
- **Earliest due date (EDD):** ưu tiên deadline gần trong mô hình một máy nhất định.
- **Local search:** thử đổi thứ tự, đổi máy hoặc dời thời điểm.
- **Tabu search / simulated annealing / genetic algorithms:** tìm kiếm phương án tốt trong không gian lớn.

Heuristic cần một **validator** để không tạo lịch vi phạm ràng buộc. Cũng nên ghi objective value, lower bound nếu có và gap so với cận, thay vì chỉ ghi “schedule tốt”.

## 12. Một quy trình giải bài toán thực tế

1. **Xác định đơn vị công việc:** job, task, operation hay request; thời lượng tính bằng gì.
2. **Xác định tài nguyên:** máy, người, loại kỹ năng, capacity, ca làm, chi phí.
3. **Viết ràng buộc cứng:** precedence, release, deadline cứng, non-overlap, eligibility, capacity.
4. **Tách ràng buộc mềm:** deadline mềm, ưu tiên, fairness, chi phí, mức sử dụng.
5. **Chọn objective rõ:** maximize profit hay minimize makespan; nếu nhiều mục tiêu, quy định thứ tự ưu tiên hoặc trọng số.
6. **Nhận dạng cấu trúc:** interval scheduling, assignment, DAG, RCPSP, bin packing, flow hay tổ hợp.
7. **Chọn exact/heuristic:** cân bằng quy mô, thời gian đáp ứng và mức tối ưu cần thiết.
8. **Tạo lịch và kiểm độc lập:** mọi job hợp lệ, không vượt capacity, không vi phạm precedence/deadline.
9. **Đo chất lượng:** objective, utilization, tardiness, fairness, runtime, bound/gap.
10. **Theo dõi thay đổi:** job mới, duration thực tế, tài nguyên unavailable và nhu cầu rescheduling.

Một hệ thống tốt giữ riêng **schedule generator** và **schedule validator**. Validator nên kiểm lại các constraint từ dữ liệu gốc, không tin hoàn toàn vào logic tạo lịch.

## 13. Java 17: ba thuật toán lập lịch trên khoảng thời gian

Chương trình **SchedulingResourceDemo.java** minh họa ba mô hình riêng:

1. **Earliest-finish greedy:** tối đa số công việc trên một tài nguyên giống nhau.
2. **Weighted interval scheduling:** tối đa tổng value trên một tài nguyên bằng DP và binary search predecessor.
3. **Capacity-k scheduling:** chọn tối đa số interval trên k tài nguyên giống nhau, sau đó gán từng interval vào máy bằng min-heap thời điểm sẵn sàng.

Tất cả interval dùng [start,end), start<end. Việc kết thúc đúng lúc việc khác bắt đầu được xem là không chồng lấn. ID công việc phải duy nhất. Giá trị có thể âm; weighted DP cho phép lịch rỗng với tổng value 0. Tổng các candidate value trong ví dụ và test phải biểu diễn được bằng long.

### 13.1. Mã nguồn hoàn chỉnh

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.Random;
import java.util.Set;
import java.util.TreeSet;

public final class SchedulingResourceDemo {
    private SchedulingResourceDemo() {
    }

    public record Job(
            String id, long start, long end, long value) {
        public Job {
            Objects.requireNonNull(id, "id");
            if (start >= end) {
                throw new IllegalArgumentException(
                        "Require start < end for [start,end)");
            }
        }
    }

    public record WeightedSchedule(
            List<Job> jobs, long totalValue) {
        public WeightedSchedule {
            jobs = List.copyOf(jobs);
        }
    }

    public record Assignment(
            String jobId, int resourceId,
            long start, long end) {
    }

    private record IndexedJob(Job job, int index) {
    }

    private record MachineState(
            long availableAt, int resourceId) {
    }

    private static void validateJobs(List<Job> jobs) {
        Objects.requireNonNull(jobs, "jobs");
        Set<String> ids = new HashSet<>();

        for (Job job : jobs) {
            Objects.requireNonNull(job, "job");
            if (!ids.add(job.id())) {
                throw new IllegalArgumentException(
                        "Job IDs must be unique: " + job.id());
            }
        }
    }

    // One machine, all jobs have equal value:
    // maximize the number of non-overlapping intervals.
    public static List<Job> maxCountSingleMachine(
            List<Job> jobs) {
        validateJobs(jobs);

        List<Job> sorted = new ArrayList<>(jobs);
        sorted.sort(
                Comparator.comparingLong(Job::end)
                        .thenComparingLong(Job::start)
                        .thenComparing(Job::id));

        List<Job> chosen = new ArrayList<>();
        long lastEnd = Long.MIN_VALUE;

        for (Job job : sorted) {
            if (job.start() >= lastEnd) {
                chosen.add(job);
                lastEnd = job.end();
            }
        }
        return List.copyOf(chosen);
    }

    // Weighted interval scheduling on one machine.
    // Empty schedule is allowed; negative-value jobs can be skipped.
    public static WeightedSchedule weightedSingleMachine(
            List<Job> jobs) {
        validateJobs(jobs);

        List<Job> sorted = new ArrayList<>(jobs);
        sorted.sort(
                Comparator.comparingLong(Job::end)
                        .thenComparingLong(Job::start)
                        .thenComparing(Job::id));

        int n = sorted.size();
        int[] predecessor = new int[n];
        long[] dp = new long[n + 1];

        for (int i = 0; i < n; i++) {
            int lo = 0;
            int hi = i;

            // First earlier job whose end is greater than start_i.
            // The compatible predecessor is the index before it.
            while (lo < hi) {
                int mid = lo + ((hi - lo) >>> 1);
                if (sorted.get(mid).end()
                        <= sorted.get(i).start()) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }

            predecessor[i] = lo - 1;
            long take = Math.addExact(
                    sorted.get(i).value(),
                    dp[predecessor[i] + 1]);
            dp[i + 1] = Math.max(dp[i], take);
        }

        // Reconstruct one optimal schedule.
        List<Job> chosen = new ArrayList<>();
        int i = n;

        while (i > 0) {
            int j = i - 1;
            long take = Math.addExact(
                    sorted.get(j).value(),
                    dp[predecessor[j] + 1]);

            // On a tie, skip the current job deterministically.
            if (take > dp[i - 1]) {
                chosen.add(sorted.get(j));
                i = predecessor[j] + 1;
            } else {
                i--;
            }
        }

        Collections.reverse(chosen);
        return new WeightedSchedule(chosen, dp[n]);
    }

    // Maximize selected interval count on k identical resources.
    // Each selected job needs one resource for its whole interval.
    public static List<Assignment> maxCountKResources(
            List<Job> jobs, int resourceCount) {
        validateJobs(jobs);

        if (resourceCount <= 0) {
            throw new IllegalArgumentException(
                    "resourceCount must be positive");
        }

        List<IndexedJob> byStart = new ArrayList<>();
        for (int i = 0; i < jobs.size(); i++) {
            byStart.add(new IndexedJob(jobs.get(i), i));
        }

        byStart.sort(
                Comparator.comparingLong(
                        (IndexedJob x) -> x.job().start())
                        .thenComparingLong(x -> x.job().end())
                        .thenComparingInt(IndexedJob::index));

        // Active selected intervals ordered by finish time.
        TreeSet<IndexedJob> active = new TreeSet<>(
                Comparator.comparingLong(
                        (IndexedJob x) -> x.job().end())
                        .thenComparingInt(IndexedJob::index));

        boolean[] selected = new boolean[jobs.size()];

        for (IndexedJob current : byStart) {
            long currentStart = current.job().start();

            // Half-open intervals: end <= start means no overlap.
            while (!active.isEmpty()
                    && active.first().job().end() <= currentStart) {
                active.pollFirst();
            }

            active.add(current);
            selected[current.index()] = true;

            if (active.size() > resourceCount) {
                // Drop the active interval that finishes latest.
                IndexedJob removed = active.pollLast();
                selected[removed.index()] = false;
            }
        }

        List<Job> chosen = new ArrayList<>();
        for (int i = 0; i < jobs.size(); i++) {
            if (selected[i]) {
                chosen.add(jobs.get(i));
            }
        }

        chosen.sort(
                Comparator.comparingLong(Job::start)
                        .thenComparingLong(Job::end)
                        .thenComparing(Job::id));

        // Interval partitioning: reuse the earliest available machine.
        PriorityQueue<MachineState> available =
                new PriorityQueue<>(
                        Comparator.comparingLong(
                                MachineState::availableAt)
                                .thenComparingInt(
                                        MachineState::resourceId));

        int createdResources = 0;
        List<Assignment> result = new ArrayList<>();

        for (Job job : chosen) {
            int resourceId;

            if (!available.isEmpty()
                    && available.peek().availableAt()
                            <= job.start()) {
                resourceId = available.poll().resourceId();
            } else if (createdResources < resourceCount) {
                resourceId = ++createdResources;
            } else {
                throw new AssertionError(
                        "Selected intervals exceed resource capacity");
            }

            available.add(
                    new MachineState(job.end(), resourceId));
            result.add(new Assignment(
                    job.id(), resourceId,
                    job.start(), job.end()));
        }

        return List.copyOf(result);
    }

    private static boolean compatibleOnOneMachine(
            List<Job> chosen) {
        for (int i = 0; i < chosen.size(); i++) {
            for (int j = i + 1; j < chosen.size(); j++) {
                Job a = chosen.get(i);
                Job b = chosen.get(j);
                boolean overlap =
                        a.start() < b.end()
                        && b.start() < a.end();
                if (overlap) {
                    return false;
                }
            }
        }
        return true;
    }

    private static long bruteWeighted(List<Job> jobs) {
        int n = jobs.size();
        long best = 0;

        for (int mask = 0; mask < (1 << n); mask++) {
            List<Job> chosen = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                if ((mask & (1 << i)) != 0) {
                    chosen.add(jobs.get(i));
                }
            }

            if (compatibleOnOneMachine(chosen)) {
                long value = 0;
                for (Job job : chosen) {
                    value = Math.addExact(value, job.value());
                }
                best = Math.max(best, value);
            }
        }
        return best;
    }

    // For interval sets, maximum overlap occurs at a job start.
    private static boolean capacityFeasible(
            List<Job> chosen, int capacity) {
        for (Job point : chosen) {
            int active = 0;
            long time = point.start();

            for (Job job : chosen) {
                if (job.start() <= time && time < job.end()) {
                    active++;
                }
            }

            if (active > capacity) {
                return false;
            }
        }
        return true;
    }

    private static int bruteMaxCount(
            List<Job> jobs, int capacity) {
        int n = jobs.size();
        int best = 0;

        for (int mask = 0; mask < (1 << n); mask++) {
            List<Job> chosen = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                if ((mask & (1 << i)) != 0) {
                    chosen.add(jobs.get(i));
                }
            }

            if (capacityFeasible(chosen, capacity)) {
                best = Math.max(best, chosen.size());
            }
        }
        return best;
    }

    private static boolean assignmentsAreFeasible(
            List<Assignment> assignments, int capacity) {
        Set<String> ids = new HashSet<>();

        for (Assignment a : assignments) {
            if (a.resourceId() < 1
                    || a.resourceId() > capacity
                    || !ids.add(a.jobId())) {
                return false;
            }
        }

        for (int i = 0; i < assignments.size(); i++) {
            for (int j = i + 1; j < assignments.size(); j++) {
                Assignment a = assignments.get(i);
                Assignment b = assignments.get(j);

                if (a.resourceId() == b.resourceId()
                        && a.start() < b.end()
                        && b.start() < a.end()) {
                    return false;
                }
            }
        }
        return true;
    }

    private static String ids(List<Job> jobs) {
        return jobs.stream().map(Job::id).toList().toString();
    }

    private static String assignmentText(
            List<Assignment> assignments) {
        return assignments.stream()
                .map(a -> a.jobId() + "->M" + a.resourceId())
                .toList().toString();
    }

    private static void require(
            boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    // Small exhaustive oracle tests for all three algorithms.
    private static int selfTest() {
        Random random = new Random(5542026L);

        for (int test = 0; test < 300; test++) {
            int n = random.nextInt(11);
            List<Job> jobs = new ArrayList<>();

            for (int i = 0; i < n; i++) {
                long start = random.nextInt(12);
                long end = start + 1 + random.nextInt(6);
                long value = random.nextInt(21) - 5;
                jobs.add(new Job(
                        "J" + i, start, end, value));
            }

            WeightedSchedule weighted =
                    weightedSingleMachine(jobs);
            require(
                    weighted.totalValue() == bruteWeighted(jobs),
                    "Weighted DP differs from brute-force oracle");

            int oneResourceOptimum = bruteMaxCount(jobs, 1);
            require(
                    maxCountSingleMachine(jobs).size()
                            == oneResourceOptimum,
                    "Earliest-finish greedy differs from oracle");

            int k = 1 + random.nextInt(4);
            List<Assignment> assigned =
                    maxCountKResources(jobs, k);

            require(
                    assigned.size() == bruteMaxCount(jobs, k),
                    "Capacity-k greedy differs from oracle");
            require(
                    assignmentsAreFeasible(assigned, k),
                    "Resource assignment violates capacity");
        }
        return 300;
    }

    public static void main(String[] args) {
        List<Job> singleMachine = List.of(
                new Job("A", 0, 3, 5),
                new Job("B", 1, 4, 6),
                new Job("C", 3, 5, 5),
                new Job("D", 4, 7, 8),
                new Job("E", 5, 8, 4),
                new Job("F", 7, 9, 3)
        );

        List<Job> unweighted =
                maxCountSingleMachine(singleMachine);
        WeightedSchedule weighted =
                weightedSingleMachine(singleMachine);

        System.out.println(
                "Unweighted single resource: " + ids(unweighted)
                + " (count=" + unweighted.size() + ")");
        System.out.println(
                "Weighted single resource: "
                + ids(weighted.jobs())
                + " (value=" + weighted.totalValue() + ")");

        List<Job> twoMachineJobs = List.of(
                new Job("R1", 0, 4, 1),
                new Job("R2", 1, 3, 1),
                new Job("R3", 2, 5, 1),
                new Job("R4", 3, 6, 1),
                new Job("R5", 4, 7, 1),
                new Job("R6", 5, 8, 1),
                new Job("R7", 6, 9, 1),
                new Job("R8", 7, 10, 1)
        );

        List<Assignment> twoMachines =
                maxCountKResources(twoMachineJobs, 2);

        System.out.println(
                "Two identical resources: "
                + assignmentText(twoMachines)
                + " (count=" + twoMachines.size() + ")");
        System.out.println(
                "Capacity respected: "
                + assignmentsAreFeasible(twoMachines, 2));

        System.out.println(
                "Empty schedule count: "
                + maxCountSingleMachine(List.of()).size());

        WeightedSchedule negative =
                weightedSingleMachine(List.of(
                        new Job("N1", 0, 2, -5)));
        System.out.println(
                "Negative-value optimum: "
                + ids(negative.jobs())
                + " (value=" + negative.totalValue() + ")");

        try {
            maxCountKResources(twoMachineJobs, 0);
            System.out.println(
                    "Invalid resource count rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println(
                    "Invalid resource count rejected: true");
        }

        try {
            new Job("BAD", 2, 2, 1);
            System.out.println(
                    "Invalid interval rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println(
                    "Invalid interval rejected: true");
        }

        System.out.println(
                "Self-test: " + selfTest() + " cases PASS");
    }
}
~~~

### 13.2. Biên dịch và chạy

Dùng **JDK 17 trở lên**, lưu đúng tên file **SchedulingResourceDemo.java**:

~~~bash
javac -encoding UTF-8 SchedulingResourceDemo.java
java SchedulingResourceDemo
~~~

**Stdout dự kiến:**

~~~text
Unweighted single resource: [A, C, E] (count=3)
Weighted single resource: [B, D, F] (value=17)
Two identical resources: [R1->M1, R2->M2, R4->M2, R5->M1, R7->M2, R8->M1] (count=6)
Capacity respected: true
Empty schedule count: 0
Negative-value optimum: [] (value=0)
Invalid resource count rejected: true
Invalid interval rejected: true
Self-test: 300 cases PASS
~~~

### 13.3. Giải thích code và kết quả

**maxCountSingleMachine:** sort theo end, sau đó chọn việc đầu tiên tương thích. Dùng điều kiện start≥lastEnd vì các interval nửa mở; việc kết thúc đúng lúc việc kế tiếp bắt đầu không chồng lấn.

**weightedSingleMachine:** sau sort, binary search p(i), tính DP giữa bỏ việc i và chọn việc i. Khi truy vết, nếu hai phương án bằng nhau code bỏ việc hiện tại để kết quả deterministic. Nếu mọi value âm, lịch rỗng có giá trị 0.

**maxCountKResources:** active TreeSet giữ những interval được chọn đang chồng lấn với start hiện tại. Khi số active vượt k, pollLast loại interval kết thúc muộn nhất. Sau đó thuật toán partition các interval đã chọn vào máy sẵn sàng sớm nhất bằng PriorityQueue.

**Unweighted [A,C,E]:** greedy earliest-finish chọn ba việc. **Weighted [B,D,F] value=17:** DP chọn phương án có lợi nhuận lớn hơn phương án A,C,E value14.

**Hai tài nguyên:** sáu việc được chọn và gán lần lượt:
- M1 nhận R1, R5, R8.
- M2 nhận R2, R4, R7.

Mỗi chuỗi trên máy không chồng lấn và số máy không vượt hai.

**Empty schedule count 0:** không có công việc nào cần lập lịch. **Negative-value optimum:** nếu có thể không làm việc nào, một job value âm không được chọn.

**Self-test 300 cases PASS:** với mỗi test, chương trình tạo tối đa 10 interval ngẫu nhiên và so:
- Weighted DP với brute-force enumeration.
- Earliest-finish greedy với nghiệm vét cạn cho một tài nguyên.
- Capacity-k selection với nghiệm vét cạn cho k tài nguyên.
- Kiểm mọi assignment không vượt k và không có hai interval giao nhau trên cùng máy.

Oracle vét cạn chỉ dùng input nhỏ trong test, không phải thuật toán production. Chương trình không in thời gian chạy vì thời gian phụ thuộc máy/JVM; các output ở trên là kết quả logic xác định.

### 13.4. Độ phức tạp

| Phương thức | Thời gian | Bộ nhớ phụ |
|---|---:|---:|
| Earliest-finish, một máy | O(n log n) | O(n) cho bản sao và output |
| Weighted interval DP | O(n log n) | O(n) |
| Capacity-k chọn interval | O(n log n) | O(n) |
| Partition vào k máy | O(n log k) trên tập được chọn | O(k+n output) |
| Brute-force oracle | O(2^n · n²) trong cài đặt kiểm tra | O(n) mỗi subset |

Ba thuật toán đầu có bảo đảm tối ưu **chỉ trong các mô hình đã nêu**. Không suy diễn bảo đảm ấy sang bài toán nhiều tài nguyên khác loại hoặc có precedence.

## 14. Kiểm thử và xác minh lịch

Một scheduler nên có một lớp validator độc lập kiểm:

1. Mọi job được chọn đều tồn tại và chỉ được chọn một lần.
2. Thời gian start/end hợp lệ, thời lượng dương.
3. Không bắt đầu trước release time.
4. Không kết thúc sau hard deadline.
5. Mọi predecessor đã hoàn tất trước successor.
6. Máy được gán thuộc tập eligible của job.
7. Không có hai job trên cùng máy chồng lấn.
8. Tổng demand từng tài nguyên tại mọi thời điểm không vượt capacity.
9. Maintenance/unavailable windows không bị sử dụng.
10. Tổng objective được tính lại từ schedule đã xác minh.

### 14.1. Kiểm tra overlap

Với hai khoảng nửa mở [s1,e1) và [s2,e2), chúng giao nhau khi:

\[
s_1<e_2\quad\text{và}\quad s_2<e_1.
\]

Không giao nhau nếu e1≤s2 hoặc e2≤s1. Đây là lý do code dùng điều kiện start≥lastEnd.

### 14.2. Sweep-line cho capacity

Để kiểm capacity k:
- Tạo event +q tại start.
- Tạo event −q tại end.
- Sắp theo thời gian.
- Tại cùng timestamp, xử lý end trước start cho interval nửa mở.
- Cộng dồn active demand và kiểm không vượt capacity.

Với nhiều loại tài nguyên, thực hiện riêng từng r hoặc dùng vector demand/capacity. Nếu có demand lớn hơn một đơn vị, chỉ đếm số interval active là không đủ.

### 14.3. Differential và brute-force tests

Với n nhỏ:
- Sinh tất cả subset.
- Loại những subset vi phạm overlap/capacity.
- Tính objective chính xác cho các subset hợp lệ.
- So heuristic/DP với optimum brute-force nếu thuật toán được tuyên bố optimal.
- Nếu chỉ là heuristic, dùng brute force để đo **optimality gap**, không đòi heuristic phải bằng optimum.

### 14.4. Randomized và property tests

Một số tính chất:
- Mọi assignment phải nằm trong capacity.
- Đổi tên job IDs không làm thay đổi objective.
- Thêm một job không đủ điều kiện không được cải thiện nghiệm tối ưu.
- Tăng capacity không thể làm giảm maximum job count trong mô hình chỉ có capacity upper bound.
- Nếu tất cả jobs có cùng khoảng và k tăng từ 1 lên 2, số việc chọn không thể giảm.
- Với weighted interval, đảo thứ tự input không đổi optimal value nếu ID tie-breaking không tham gia objective.

Các property này cũng cần tiền điều kiện: thêm job mới có thể cải thiện nghiệm, nhưng **không được** làm giảm optimal objective nếu lựa chọn cũ vẫn khả thi.

## 15. Những lỗi thường gặp

1. **Không xác định mục tiêu trước:** tối đa số việc và tối đa profit là hai bài khác nhau.
2. **Dùng earliest-finish greedy cho weighted interval:** có thể bỏ mất lịch lợi nhuận cao hơn.
3. **Dùng job value cao nhất trước:** một job dài có thể chặn nhiều job có tổng value cao hơn.
4. **Nhầm [start,end] với [start,end):** xử lý sai hai việc tiếp giáp.
5. **Dùng điều kiện start>lastEnd:** bỏ lỡ việc bắt đầu đúng lúc máy vừa rảnh.
6. **Không validate start<end:** tạo interval rỗng hoặc ngược thời gian.
7. **Không tính release time:** bắt đầu việc trước khi dữ liệu/tài nguyên sẵn sàng.
8. **Coi due date mềm như hard deadline:** loại việc đáng ra có thể làm trễ với penalty.
9. **Quên precedence:** chạy successor trước predecessor.
10. **Dùng topological sort như lời giải RCPSP đầy đủ:** thứ tự hợp lệ chưa chắc đủ tài nguyên.
11. **Không kiểm machine eligibility:** gán việc cho máy/người thiếu kỹ năng.
12. **Đếm số máy rảnh nhưng không kiểm capacity tổng:** nhiều job có thể cùng vượt một loại tài nguyên khác.
13. **Chỉ kiểm số interval active khi job dùng nhiều units:** phải cộng demand q_jr.
14. **Xử lý start trước end tại cùng timestamp:** sai semantics interval nửa mở.
15. **Bỏ maintenance/unavailable windows:** lịch nhìn hợp lệ nhưng máy đang bảo trì.
16. **Dùng capacity-k greedy cho job có profit khác nhau:** thuật toán đó chỉ tối đa số lượng trong mô hình đồng nhất.
17. **Dùng capacity-k interval algorithm cho nhiều loại tài nguyên:** không đủ biểu diễn các constraint khác nhau.
18. **Dùng một predecessor sai trong weighted DP:** binary search phải tìm end≤start.
19. **DP dùng sai chỉ số p(i):** nhầm 0-based/1-based và bỏ hoặc lặp job.
20. **Không truy vết DP:** có optimal value nhưng không tạo được danh sách việc tương ứng.
21. **Không quy định lịch rỗng có hợp lệ:** làm kết quả khi tất cả profit âm bị sai.
22. **Tràn long khi cộng profit/duration:** objective có thể âm thầm sai nếu không kiểm.
23. **Không dùng validator độc lập:** bug trong scheduler cũng có thể lặp lại trong code kiểm.
24. **Gọi nghiệm feasible là optimal:** solver có thể chưa chứng minh optimality.
25. **Không đo optimality gap:** heuristic tốt nhưng không biết cách optimum bao xa.
26. **Discretize thời gian quá thô:** có thể làm mất lịch hợp lệ hoặc tạo lịch sai deadline.
27. **Bỏ setup time phụ thuộc thứ tự:** chuyển máy giữa hai việc có thể tốn thời gian.
28. **Bỏ preemption semantics:** việc có thể bị dừng/tiếp tục hay không ảnh hưởng mô hình.
29. **Tối ưu một objective nhưng quên mục tiêu còn lại:** utilization cao có thể làm deadline/fairness tệ.
30. **Không xét biến động thời lượng:** lịch tối ưu trên estimate có thể vỡ khi job kéo dài.
31. **Không freeze các công việc sắp thực thi:** reschedule liên tục có thể làm hệ thống bất ổn.
32. **Cho rằng mọi bài scheduling đều giải bằng greedy:** nhiều biến thể tổng quát là NP-hard.
33. **Dùng brute force cho input production:** số subset tăng theo hàm mũ.
34. **Không giữ seed và counterexample:** lỗi random khó tái lập.
35. **Không kiểm tính duy nhất ID:** tie-breaking, truy vết và báo cáo có thể mơ hồ.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Scheduling và assignment khác nhau thế nào?

**Đáp án:** Scheduling quyết định thứ tự/thời điểm; assignment gán công việc cho người hoặc máy. Một bài có thể cần cả hai.

**Câu 2.** Interval [1,3) và [3,5) có chồng lấn không?

**Đáp án:** Không; việc đầu kết thúc đúng lúc việc sau bắt đầu.

**Câu 3.** Greedy nào tối ưu số interval trên một máy?

**Đáp án:** Sort theo end tăng và chọn job đầu tiên có start≥lastEnd.

**Câu 4.** Vì sao earliest-finish greedy đúng trong mô hình ấy?

**Đáp án:** Có thể thay job đầu của một lịch tối ưu bằng job kết thúc sớm nhất mà không làm mất các job phía sau.

**Câu 5.** Weighted interval dùng công thức nào?

**Đáp án:** OPT(i)=max(OPT(i−1),w_i+OPT(p(i))).

**Câu 6.** p(i) là gì?

**Đáp án:** Chỉ số job cuối cùng trước i có end≤start_i.

**Câu 7.** Vì sao weighted interval DP chạy O(n log n)?

**Đáp án:** Sort O(n log n), binary search predecessor cho mỗi job O(log n), DP còn lại O(n).

**Câu 8.** Nếu mọi value âm và lịch rỗng hợp lệ thì optimum là gì?

**Đáp án:** Chọn không job nào, tổng value 0.

**Câu 9.** Capacity-k interval greedy bỏ job nào khi active vượt k?

**Đáp án:** Job đang active có end lớn nhất.

**Câu 10.** Sau chọn interval, làm sao gán máy?

**Đáp án:** Sắp theo start và tái sử dụng máy có availableAt sớm nhất nếu availableAt≤start.

**Câu 11.** Khi nào capacity-k greedy trong bài có bảo đảm tối ưu?

**Đáp án:** k tài nguyên giống nhau, mỗi job cần một đơn vị, interval cố định, mục tiêu maximize count và không có constraint phụ.

**Câu 12.** Precedence graph nên là loại đồ thị nào?

**Đáp án:** DAG nếu muốn có thứ tự thực hiện không chu trình.

**Câu 13.** Critical path cho biết điều gì?

**Đáp án:** Độ dài phụ thuộc lớn nhất và thời điểm hoàn tất sớm nhất khi bỏ qua tranh chấp tài nguyên.

**Câu 14.** RCPSP khác critical path ra sao?

**Đáp án:** RCPSP còn phải thỏa capacity tài nguyên trong khi tuân precedence.

**Câu 15.** Matching/min-cost flow phù hợp loại bài nào?

**Đáp án:** Gán việc cho người/máy theo eligibility và chi phí khi cấu trúc capacity có thể biểu diễn thành mạng.

**Câu 16.** Hard deadline và soft due date khác nhau thế nào?

**Đáp án:** Hard deadline vi phạm làm lịch không hợp lệ; soft due date cho phép trễ nhưng bị phạt.

**Câu 17.** Preemption là gì?

**Đáp án:** Cho phép tạm dừng một công việc và tiếp tục sau, theo quy tắc của bài toán.

**Câu 18.** Tại sao cần validator độc lập?

**Đáp án:** Để phát hiện lịch vi phạm capacity/precedence ngay cả khi scheduler có bug.

**Câu 19.** Khi capacity tăng, maximum job count có giảm không?

**Đáp án:** Không, nếu chỉ tăng upper bound và các constraint khác giữ nguyên; tập lịch cũ vẫn khả thi.

**Câu 20.** Nghiệm feasible có đồng nghĩa optimal không?

**Đáp án:** Không; nó chỉ chứng minh các constraint được thỏa, chưa chứng minh objective tốt nhất.

**Câu 21.** Vì sao phải đọc solver status và bound?

**Đáp án:** Để biết solver đã chứng minh tối ưu, còn gap hay dừng do time limit.

**Câu 22.** Tại sao job có demand 2 units không thể chỉ đếm active job?

**Đáp án:** Capacity phải cộng tổng q_jr, không phải đếm số interval.

**Câu 23.** Khi nào cần rolling horizon?

**Đáp án:** Khi job, duration hoặc tài nguyên thay đổi liên tục và lịch phải được cập nhật.

**Câu 24.** Utilization 100% luôn tốt không?

**Đáp án:** Không; không có slack khiến hệ thống dễ trễ khi job kéo dài hoặc có sự cố.

## 17. Bài tập thực hành

**Bài 1 — Earliest finish:** tạo 20 interval ngẫu nhiên, so greedy một máy với brute-force maximum cardinality.

**Bài 2 — Weighted DP:** tạo interval có value dương/âm, so DP và brute force, kiểm cả truy vết job IDs.

**Bài 3 — Capacity k:** thử k=1,2,3,4; xác minh overlap không vượt k và so với brute force cho n≤12.

**Bài 4 — Deadline:** thêm release time và deadline cứng; cập nhật validator để loại lịch vi phạm.

**Bài 5 — Precedence:** xây DAG, tính critical path, rồi tạo trường hợp thiếu tài nguyên để thấy critical path chưa đủ.

**Bài 6 — Assignment:** tạo ma trận chi phí và eligibility, giải bằng Hungarian/min-cost flow, so với brute force trên ma trận nhỏ.

**Bài 7 — Multi-resource:** cho mỗi job demand CPU, RAM và nhân lực; viết sweep-line validator riêng cho từng resource.

**Bài 8 — Objective:** so lịch tối đa số job với lịch tối đa profit; giải thích vì sao không thể dùng cùng một greedy rule.

**Bài 9 — Rescheduling:** mô phỏng một máy hỏng giữa ca, giữ các job đã bắt đầu cố định và lập lịch lại phần còn lại.

## 18. Ghi nhớ

**Lập lịch** quyết định thời điểm/thứ tự thực hiện; **phân bổ nguồn lực** quyết định công việc nhận máy, người hoặc capacity nào. Một mô hình tốt phải xác định rõ interval, duration, release/deadline, precedence, eligibility, resource demand, capacity, preemption và objective.

Một số cấu trúc có lời giải hiệu quả:
- Interval scheduling một máy, maximize count: greedy earliest finish.
- Weighted interval một máy: DP với predecessor binary search.
- k máy giống nhau, interval cố định và maximize count: capacity-k greedy rồi interval partitioning.
- Assignment có chi phí: matching/Hungarian/min-cost flow.
- Precedence cộng nhiều cumulative resources: RCPSP/CP-SAT/MILP hoặc heuristic phù hợp.

Các thuật toán trên chỉ tối ưu trong **đúng mô hình và giả thiết đã nêu**. Khi thêm trọng số, nhiều loại tài nguyên, setup, deadline, precedence hay dữ liệu động, phải cập nhật mô hình và kiểm lại bảo đảm. Luôn có **validator độc lập** để xác nhận lịch không vi phạm ràng buộc trước khi triển khai.
