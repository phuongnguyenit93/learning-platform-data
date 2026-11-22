# Ghép cặp trọng số và bài toán phân công

## 1. Bài toán và phạm vi

**Ghép cặp (matching)** trên một đồ thị là tập cạnh mà không có hai cạnh nào chung đỉnh. Trong **đồ thị hai phía (bipartite graph)**, các đỉnh chia thành phía trái L và phía phải R, cạnh chỉ nối một đỉnh trái với một đỉnh phải.

**Bài toán phân công (assignment)** là trường hợp quan trọng của ghép cặp hai phía. Hãy coi L là người/robot/máy và R là công việc/vị trí. Chi phí hoặc điểm lợi ích của cặp người i–công việc j được cho bởi một ô ma trận. Mỗi người nhận nhiều nhất một việc và mỗi việc được dùng nhiều nhất một lần.

Ví dụ thực tế: gán nhân viên theo kỹ năng; phân bổ robot đến trạm sạc; gán tác vụ cho máy xử lý; phân bổ quảng cáo vào vị trí hiển thị; chọn các cặp người–việc đem lại doanh thu lớn nhất.

Trước khi chọn thuật toán, phải phân biệt **ba yêu cầu**:

1. **Min-cost full assignment:** tất cả n người phải được ghép; tổng chi phí nhỏ nhất.
2. **Max-weight full assignment:** tất cả n người phải được ghép; tổng lợi ích lớn nhất.
3. **Max-weight optional matching:** người có thể không được ghép nếu ghép làm giảm lợi ích; tối đa tổng điểm của các cặp được chọn.

Bài học sử dụng **Hungarian (Kuhn–Munkres)** cho ma trận hình chữ nhật và kỹ thuật thêm **công việc ảo** để giải matching tùy chọn. Trình bày cách sửa ghép cặp qua đường tăng, thế vị đối ngẫu, chi phí giảm, chứng chỉ tối ưu, ví dụ chi phí âm, code **Java 17 BigInteger**, kiểm thử độc lập và ranh giới áp dụng.

Hungarian chuẩn ở đây giả định **mọi cặp trong ma trận là hợp lệ**. Bài toán có cặp bị cấm hoặc dung lượng công việc lớn hơn một cần mô hình khác/phiên bản thuật toán phù hợp.

## 2. Matching thường, matching trọng số và assignment khác nhau thế nào?

Với matching M, số cặp là \(|M|\).

- **Maximum-cardinality matching:** tối đa \(|M|\), không xét trọng số.
- **Maximum-weight matching:** tối đa \(\sum_{(i,j)\in M}w_{ij}\).
- **Min-cost full assignment:** tối thiểu tổng chi phí nhưng phải ghép hết phía trái.
- **Max-weight full assignment:** tối đa lợi ích nhưng vẫn phải ghép hết phía trái.

**Tối đa số cặp** và **tối đa tổng trọng số** không đồng nghĩa. Nếu mọi lợi ích âm và cho phép bỏ các cặp, matching rỗng có tổng 0 tốt hơn mọi matching có tổng âm. Một bài yêu cầu tối đa số cặp trước rồi mới tối đa điểm là **mục tiêu từ điển hai tầng**, không phải max-weight optional thông thường.

Cũng phải phân biệt **maximal matching** (không thể thêm một cạnh mà không phá tính matching) với **maximum matching** (có số cặp nhiều nhất). Một matching maximal chưa chắc có số cặp lớn nhất, lại càng chưa chắc tối ưu trọng số.

### Hàng và cột trong bài toán phân công

Cho n người (hàng), m công việc (cột).

- **n=m**: ghép đủ mọi người có thể đồng thời dùng hết mọi việc.
- **n<m**: ghép đủ n người, để trống m−n công việc.
- **n>m**: không thể ghép đủ mọi người vào công việc thật nếu mỗi công việc chỉ có một slot.

Trong phần min-cost và max-weight full của code, hợp đồng là **n≤m**, mọi hàng bắt buộc có một cột phân biệt. Khi n>m, API full sẽ từ chối. Optional matching cho phép người không được ghép và hoạt động được khi n>m.

**Trọng số âm vẫn hợp lệ.** Chi phí âm có thể là ưu đãi/hoàn tiền; điểm lợi ích âm có thể là rủi ro hoặc thiệt hại. Không được coi chi phí âm là “không có cạnh”. Một cặp **bị cấm** cần được biểu diễn bằng sự không tồn tại của cạnh hoặc mô hình ràng buộc riêng.

## 3. Mô hình toán học của full assignment

Gọi \(c_{ij}\) là chi phí giao việc j cho người i. Đặt biến nhị phân \(x_{ij}\in\{0,1\}\) với ý nghĩa bằng 1 khi giao cặp (i,j).

Hàm mục tiêu:

\[
\min\sum_{i=1}^{n}\sum_{j=1}^{m}c_{ij}x_{ij}.
\]

Ràng buộc mỗi người đúng một việc:

\[
\sum_{j=1}^{m}x_{ij}=1\quad\forall i.
\]

Ràng buộc một việc tối đa một người:

\[
\sum_{i=1}^{n}x_{ij}\le1\quad\forall j.
\]

Cần có **n≤m** để ghép đủ n người vào m công việc khi mọi ô đều là cặp khả thi.

Nếu mô tả một nghiệm bằng mảng \(\pi(i)\), với \(\pi(i)\) là công việc của người i, thì mọi \(\pi(i)\) phải khác nhau và:

\[
C(\pi)=\sum_{i=1}^{n}c_{i,\pi(i)}.
\]

Với n=m có n! hoán vị; với n<m có \(m!/(m-n)!\) phép gán. Duyệt mọi trường hợp tăng nhanh theo giai thừa, vì vậy cần thuật toán tối ưu cấu trúc như Hungarian.

Trong Java, chỉ số người/công việc là **0-based**; công thức toán học trên dùng chỉ số 1-based để dễ đọc.

## 4. Ví dụ chi phí nhỏ nhất 3×3

Ma trận chi phí:

| Người / Việc | 0 | 1 | 2 |
|---|---:|---:|---:|
| 0 | 4 | 1 | 3 |
| 1 | 2 | 0 | 5 |
| 2 | 3 | 2 | 2 |

Một phân công tối ưu:
- Người 0 → việc 1: chi phí 1.
- Người 1 → việc 0: chi phí 2.
- Người 2 → việc 2: chi phí 2.

Tổng bằng **5**, mảng công việc theo người là **[1,0,2]**. Không có hai người dùng cùng một việc.

Với chỉ ba hàng, có thể liệt kê cả 3!=6 cách để kiểm chứng; với n lớn hơn, không thể coi liệt kê giai thừa là thuật toán chính.

### Bẫy của greedy

Cho ma trận:

| Người / Việc | 0 | 1 |
|---|---:|---:|
| 0 | 1 | 2 |
| 1 | 2 | 100 |

Nếu chọn công việc rẻ nhất trước cho người 0, ta chọn cột 0 chi phí 1 và buộc người 1 nhận cột 1 chi phí 100; tổng **101**.

Nhưng nếu đảo:
- Người 0 → việc 1: chi phí 2.
- Người 1 → việc 0: chi phí 2.

Tổng chỉ **4**, là tối ưu. Như vậy **chọn cặp rẻ nhất tại từng bước không đủ**, vì một công việc rẻ cho người đầu có thể là lựa chọn không thể thay thế cho người sau.

Hungarian có khả năng **điều chỉnh lại các cặp đã gán** bằng đường tăng, nên không mắc lỗi chốt cứng lựa chọn ban đầu.

## 5. Đường xen kẽ và đường tăng

**Đường xen kẽ (alternating path)** gồm những cạnh lần lượt thuộc matching và chưa thuộc matching. Nếu nó bắt đầu ở một người chưa được ghép và kết thúc ở một công việc chưa được dùng, lật trạng thái ghép dọc đường sẽ tạo một matching có **thêm một cặp**.

Ví dụ người A muốn việc X nhưng X đã thuộc B; nếu B có thể chuyển sang việc Y còn trống, ta dịch B sang Y, nhường X cho A. Quá trình dịch có thể qua nhiều người và việc, nhưng kết quả vẫn không trùng cột.

Hungarian xây **matching tăng dần theo hàng**. Ở vòng i, các hàng 1..i−1 đã được ghép; thuật toán tìm một đường tăng để ghép thêm hàng i, có thể xoay lại những cặp cũ.

Tuy nhiên, một đường tăng bất kỳ chỉ cải thiện **số cặp**. Muốn còn tối ưu **tổng chi phí**, Hungarian sử dụng **thế vị (potentials)** và **chi phí giảm (reduced costs)** để quyết định đường tăng và điều chỉnh giá.

## 6. Thế vị đối ngẫu và cạnh chặt

Với full assignment n≤m, đặt:
- \(u_i\): thế vị của hàng i.
- \(v_j\): thế vị của cột j.
- \(r_{ij}=c_{ij}-u_i-v_j\): chi phí giảm.

Đối ngẫu cho bài toán min-cost có dạng:

\[
\max\left(\sum_i u_i+\sum_j v_j\right)
\]

với ràng buộc:

\[
u_i+v_j\le c_{ij},\qquad v_j\le0.
\]

Khi các ràng buộc đúng, mọi \(r_{ij}\ge0\). Một cạnh với r_ij=0 gọi là **cạnh chặt (tight edge)**.

### Khởi tạo với chi phí âm

Cách khởi tạo dễ kiểm chứng:

\[
u_i=\min_j c_{ij},\qquad v_j=0.
\]

Khi đó u_i+v_j≤c_ij ngay từ đầu, **kể cả chi phí âm**. Ví dụ hàng [4,−2,3,1] có u_i=−2, mọi reduced cost không âm.

Không cần cộng hằng số vào ma trận chỉ để loại số âm; cũng không được tự thay chi phí âm thành 0.

### Vì sao nghiệm chặt là tối ưu?

Với mọi matching ghép đủ hàng và thế vị đối ngẫu khả thi:

\[
\sum_i c_{i,\pi(i)}
\ge\sum_i(u_i+v_{\pi(i)})
\ge\sum_i u_i+\sum_j v_j.
\]

Tổng đối ngẫu là **cận dưới** của tổng chi phí matching.

Nếu:
1. Mọi cạnh được chọn đều chặt: \(u_i+v_{\pi(i)}=c_{i,\pi(i)}\).
2. Mọi cột không được dùng có \(v_j=0\).

Thì:

\[
\boxed{\sum_i c_{i,\pi(i)}=\sum_i u_i+\sum_j v_j}.
\]

Matching đã đạt **cận dưới đối ngẫu**, nên không tồn tại matching nào có tổng nhỏ hơn. Đây là chứng minh tối ưu; không chỉ là kiểm thử thực nghiệm.

**Vì sao v_j≤0?** Ràng buộc mỗi cột “được dùng tối đa một lần” là bất đẳng thức ≤1 trong bài toán tối thiểu hóa, nên biến đối ngẫu tương ứng không dương. Ràng buộc mỗi hàng “đúng một lần” là đẳng thức nên u_i không bị cố định dấu.

## 7. Hungarian hình chữ nhật: dữ liệu và cập nhật

Một cài đặt phổ biến dùng chỉ số nội bộ 1-based, riêng **cột 0** là cột giả hỗ trợ bắt đầu đường tăng.

Các mảng:
- **u, v**: thế vị hàng và cột.
- **p[j]**: hàng hiện đang ghép với cột j; p[j]=0 nếu cột trống.
- **p[0]**: hàng mới cần gán.
- **way[j]**: cột đứng trước để truy ngược đường tăng đến j.
- **used[j]**: cột đã được đưa vào cây xen kẽ trong lượt hiện tại.
- **minv[j]**: reduced-cost/slack tốt nhất hiện tại để tới cột j từ cây xen kẽ.

Ở vòng thêm hàng i:
1. Gán p[0]=i, j0=0, các minv chưa biết, used=false.
2. Tại cột j0, đánh dấu used[j0]=true và lấy hàng i0=p[j0].
3. Với cột j chưa dùng, tính cur=c[i0][j]−u[i0]−v[j].
4. Nếu cur tốt hơn minv[j], cập nhật minv[j] và way[j]=j0.
5. Chọn Δ là minv nhỏ nhất của các cột chưa dùng.
6. Với cột used, tăng u[p[j]] thêm Δ, giảm v[j] đi Δ. Với cột chưa dùng có slack đã biết, trừ Δ khỏi minv[j].
7. Chọn cột j1 có slack nhỏ nhất. Nếu p[j1]!=0 thì tiếp tục mở rộng cây; nếu p[j1]==0 thì đã gặp cột trống.
8. Truy ngược way[] và **xoay matching** dọc đường tăng để thêm hàng i.

**Tính an toàn của Δ:** do Δ là slack nhỏ nhất, trừ Δ không khiến slack nào trở thành âm. Các thế vị được chỉnh để giữ cạnh chặt cần thiết và tạo thêm ít nhất một cạnh chặt mới. Với m≥n, khi đang ghép hàng i và chỉ i−1 hàng đã có việc, luôn có cột trống để hoàn thành đường tăng.

Nếu nhiều cột bằng reduced cost, có thể chọn theo ID cột để tái lập output. Nhưng **một nghiệm được chọn có thứ tự xác định không chứng minh nghiệm tối ưu là duy nhất**.

## 8. Ma trận hình chữ nhật và chi phí âm

Xét 3 người, 4 công việc:

| Người / Việc | 0 | 1 | 2 | 3 |
|---|---:|---:|---:|---:|
| 0 | 4 | −2 | 3 | 1 |
| 1 | 2 | 0 | 5 | 2 |
| 2 | 3 | −1 | 2 | −4 |

Một lời giải tối ưu là:
- Người 0 → việc 1, chi phí −2.
- Người 1 → việc 0, chi phí 2.
- Người 2 → việc 3, chi phí −4.
- Việc 2 để trống.

Tổng **−4**, output columns=[1,0,3].

Tổng âm không gây lỗi: nếu chi phí âm biểu diễn khoản hoàn tiền, mục tiêu minimization vẫn hợp lệ. Hungarian xử lý âm thông qua thế vị khả thi, không phải bằng cách thay chúng thành dương.

**n<m:** có việc không được dùng là bình thường, vì ràng buộc cột là ≤1, không phải =1.

**n>m:** không có full assignment bão hòa mọi hàng. Muốn cho phép bỏ người, cần mô hình optional matching; muốn mỗi việc nhận nhiều người, cần mô hình sức chứa.

## 9. Tối đa lợi ích nhưng vẫn buộc ghép tất cả

Nếu bảng là **điểm lợi ích** thay vì chi phí:

| Người / Việc | 0 | 1 | 2 |
|---|---:|---:|---:|
| 0 | 8 | 4 | 7 |
| 1 | 7 | 6 | 6 |
| 2 | 5 | 9 | 8 |

Một matching tối ưu full:
- Người 0→việc 0: lợi ích 8.
- Người 1→việc 2: lợi ích 6.
- Người 2→việc 1: lợi ích 9.
- Tổng **23**.

Để giải bằng Hungarian min-cost, đặt:

\[
c_{ij}=-w_{ij}.
\]

Vì **số cặp bắt buộc đúng n**, cực tiểu tổng −w tương đương cực đại tổng w. Chạy Hungarian trên cost đối dấu rồi đổi dấu total.

Không dùng trị tuyệt đối của trọng số; điều đó có thể phá thứ tự tối ưu.

**Lưu ý tràn số của Java:** Long.MIN_VALUE không thể đổi dấu bằng long thông thường. Code chuyển mỗi phần tử sang **BigInteger** trước khi .negate(), bảo đảm an toàn cho cả Long.MIN_VALUE và tổng vượt long.

Có thể có nhiều matching cùng tổng 23. Khi test, nên kiểm tra tổng, không trùng cột và tuân thủ hợp đồng thay vì đòi một bộ ID duy nhất trừ khi đã quy định tie-break.

## 10. Ghép cặp có trọng số được phép bỏ trống

Cho điểm lợi ích:

| Người / Việc | 0 | 1 |
|---|---:|---:|
| 0 | −8 | −2 |
| 1 | −4 | −6 |

**Bắt buộc ghép hết**: matching có tổng lớn nhất là −2 + (−4) = **−6**.

**Được phép không ghép**: matching rỗng có tổng **0**, tốt hơn −6.

Đây là hai đáp án đúng cho **hai bài toán khác nhau**; không được chọn theo cảm tính hay tự sửa điểm âm.

### 10.1. Thêm n công việc ảo

Với n người và m việc thật, thêm **n cột ảo (dummy jobs)** có điểm lợi ích bằng 0 cho mọi người. Ma trận mở rộng có n hàng, m+n cột và mọi hàng phải được ghép.

- Nếu người i được gán công việc thật j<m, output columns[i]=j.
- Nếu người i được gán cột ảo j≥m, output columns[i]=**−1**, nghĩa là không có việc thật.

Vì có n cột ảo, **tất cả n người đều có thể không ghép**. Chỉ thêm một cột ảo là sai, vì theo ràng buộc assignment mỗi cột chỉ dành cho tối đa một người.

Chứng minh tương đương:
- Mỗi matching tùy chọn trên việc thật có thể được mở rộng thành full assignment bằng cách gán các người chưa có việc vào những cột ảo phân biệt; tổng điểm không đổi vì điểm ảo bằng 0.
- Ngược lại, bỏ các cột ảo khỏi full assignment cho một matching hợp lệ trên việc thật có cùng tổng điểm.

Vậy tối đa hóa tổng trên ma trận mở rộng trả đúng **maximum-weight optional matching** trên dữ liệu thật.

### 10.2. Ba người, hai công việc

| Người / Việc | 0 | 1 |
|---|---:|---:|
| 0 | 5 | −1 |
| 1 | 4 | −3 |
| 2 | 2 | 1 |

Có 3 người nhưng chỉ 2 việc thật. Optional matching tốt nhất chọn:
- Người 0→việc 0, được 5.
- Người 1 không ghép.
- Người 2→việc 1, được 1.

Tổng **6**, kết quả columns=[0,−1,1].

### 10.3. Nếu phải tối đa số cặp trước rồi mới tối đa lợi ích

Đề có thể đặt thứ tự ưu tiên:
1. Ghép được **nhiều người nhất**.
2. Trong số matching đạt cardinality đó, có **tổng lợi ích lớn nhất**.

Bài này khác optional max-weight. Với điểm toàn âm, optional có thể chọn matching rỗng, còn cardinality-first cố ghép nhiều cặp.

Có thể dùng matching cực đại về số lượng để biết cardinality k, sau đó min-cost flow tìm lời giải có đúng k cặp và chi phí đối dấu tối thiểu. Nếu dùng thủ thuật cộng thưởng lớn vào trọng số, phải có cận giá trị để chứng minh thứ tự ưu tiên được bảo toàn; không được dùng hằng tùy ý.

## 11. Ranh giới áp dụng Hungarian

**Hungarian ma trận dày đầy đủ** phù hợp khi có chi phí/lợi ích của mọi cặp người–việc và mỗi công việc chỉ nhận tối đa một người.

Các biến thể cần cẩn thận:

- **Cặp bị cấm:** code không có sentinel “cạnh không tồn tại”. Dùng chi phí rất lớn M chỉ là penalty, không tự cấm cặp; nếu mọi full matching đều cần nó, thuật toán có thể vẫn chọn. Có thể dùng **min-cost max-flow** trên các cặp hợp lệ hoặc Hungarian có xử lý cặp thiếu thật sự.
- **Công việc có sức chứa 2 trở lên:** cần capacity, không còn ràng buộc mỗi cột ≤1; có thể dùng min-cost flow hoặc slot hóa đúng đặc tả.
- **Một người nhận nhiều công việc:** cần mô hình tổng quát hơn, thường là luồng chi phí nhỏ nhất hoặc quy hoạch số nguyên.
- **Đồ thị không hai phía:** matching trọng số tổng quát có thể cần **weighted blossom**, không dùng Hungarian trực tiếp.
- **Ràng buộc thời gian/ca/kỹ năng kết hợp:** đôi khi không biểu diễn được bằng tổng chi phí từng cặp độc lập.
- **Nhiều tiêu chí từ điển:** phải quy định rõ cardinality, lợi ích, công bằng, quota; không tự suy rằng Hungarian tối ưu tất cả.

Không được nhầm cặp chi phí âm với cặp bị cấm. Không được dùng Long.MAX_VALUE làm “vô hạn” một cách mù quáng trong code tính chi phí giảm, vì một phép tính trừ nhiều thế vị có thể tràn long.

## 12. Chương trình Java 17: Hungarian hình chữ nhật bằng BigInteger

API:
- **minCost(costs)**: tối thiểu chi phí, ghép hết hàng; yêu cầu n≤m.
- **maxWeightAll(scores)**: tối đa lợi ích, ghép hết hàng; chuyển score thành chi phí âm.
- **maxWeightOptional(scores)**: tối đa lợi ích, cho phép bỏ hàng; thêm n công việc ảo điểm 0.

Input là long[][] hình chữ nhật; mỗi ô là cặp hợp lệ. Output **Assignment(total,columns)**; total dùng BigInteger, columns[i] là ID việc thật 0-based của người i, hoặc −1 trong phiên bản optional nếu người ấy không ghép.

Chương trình kiểm tra:
- Ma trận không rỗng, không ragged/null.
- Full assignment phải có m≥n.
- Chi phí giảm và thế vị dùng BigInteger, không overflow.
- Đối ngẫu khả thi; mọi cạnh ghép chặt; v của cột chưa dùng bằng 0; tổng primal bằng dual.

Lưu thành **WeightedAssignmentDemo.java**:

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class WeightedAssignmentDemo {
    private WeightedAssignmentDemo() {
    }

    public record Assignment(
            BigInteger total, List<Integer> columns) {
        public Assignment {
            columns = List.copyOf(columns);
        }
    }

    private static BigInteger[][] readMatrix(long[][] input) {
        if (input == null || input.length == 0
                || input[0] == null || input[0].length == 0) {
            throw new IllegalArgumentException(
                    "Need a nonempty rectangular matrix");
        }

        int n = input.length;
        int m = input[0].length;
        BigInteger[][] result = new BigInteger[n][m];

        for (int i = 0; i < n; i++) {
            if (input[i] == null || input[i].length != m) {
                throw new IllegalArgumentException(
                        "Ragged/null matrix row");
            }

            for (int j = 0; j < m; j++) {
                result[i][j] = BigInteger.valueOf(input[i][j]);
            }
        }
        return result;
    }

    // Hungarian min-cost: n rows, m columns, n <= m.
    private static Assignment hungarian(BigInteger[][] cost) {
        int n = cost.length;
        int m = cost[0].length;

        if (n > m) {
            throw new IllegalArgumentException(
                    "Full assignment requires jobs >= workers");
        }

        // Hungarian 1-based; column 0 is a dummy start column.
        BigInteger[] u = new BigInteger[n + 1];
        BigInteger[] v = new BigInteger[m + 1];
        Arrays.fill(u, BigInteger.ZERO);
        Arrays.fill(v, BigInteger.ZERO);

        // Feasible dual initialization, including negative costs.
        for (int i = 1; i <= n; i++) {
            BigInteger minimum = cost[i - 1][0];
            for (int j = 1; j < m; j++) {
                if (cost[i - 1][j].compareTo(minimum) < 0) {
                    minimum = cost[i - 1][j];
                }
            }
            u[i] = minimum;
        }

        int[] p = new int[m + 1];
        int[] way = new int[m + 1];

        for (int i = 1; i <= n; i++) {
            p[0] = i;
            int j0 = 0;

            // Null means no known slack yet.
            BigInteger[] minv = new BigInteger[m + 1];
            boolean[] used = new boolean[m + 1];

            do {
                used[j0] = true;
                int i0 = p[j0];
                BigInteger delta = null;
                int j1 = -1;

                for (int j = 1; j <= m; j++) {
                    if (used[j]) {
                        continue;
                    }

                    BigInteger current = cost[i0 - 1][j - 1]
                            .subtract(u[i0]).subtract(v[j]);

                    if (minv[j] == null
                            || current.compareTo(minv[j]) < 0) {
                        minv[j] = current;
                        way[j] = j0;
                    }

                    if (delta == null
                            || minv[j].compareTo(delta) < 0) {
                        delta = minv[j];
                        j1 = j;
                    }
                }

                if (j1 == -1 || delta == null) {
                    throw new IllegalStateException(
                            "No augmenting column");
                }

                for (int j = 0; j <= m; j++) {
                    if (used[j]) {
                        u[p[j]] = u[p[j]].add(delta);
                        v[j] = v[j].subtract(delta);
                    } else if (minv[j] != null) {
                        minv[j] = minv[j].subtract(delta);
                    }
                }
                j0 = j1;
            } while (p[j0] != 0);

            // Reassign along the alternating augmenting path.
            do {
                int j1 = way[j0];
                p[j0] = p[j1];
                j0 = j1;
            } while (j0 != 0);
        }

        int[] assigned = new int[n];
        Arrays.fill(assigned, -1);

        for (int j = 1; j <= m; j++) {
            if (p[j] != 0) {
                assigned[p[j] - 1] = j - 1;
            }
        }

        List<Integer> columns = new ArrayList<>();
        BigInteger total = BigInteger.ZERO;
        for (int i = 0; i < n; i++) {
            int job = assigned[i];
            if (job < 0) {
                throw new IllegalStateException("Unmatched row");
            }

            columns.add(job);
            total = total.add(cost[i][job]);
        }

        // A mathematical certificate: feasible dual and equality.
        BigInteger dual = BigInteger.ZERO;

        for (int i = 1; i <= n; i++) {
            dual = dual.add(u[i]);
            for (int j = 1; j <= m; j++) {
                if (u[i].add(v[j])
                        .compareTo(cost[i - 1][j - 1]) > 0) {
                    throw new IllegalStateException(
                            "Dual feasibility violated");
                }
            }

            int chosen = assigned[i - 1] + 1;
            if (!u[i].add(v[chosen])
                    .equals(cost[i - 1][chosen - 1])) {
                throw new IllegalStateException(
                        "Matched edge is not tight");
            }
        }

        for (int j = 1; j <= m; j++) {
            if (v[j].signum() > 0
                    || (p[j] == 0 && v[j].signum() != 0)) {
                throw new IllegalStateException(
                        "Column potential invalid");
            }
            dual = dual.add(v[j]);
        }

        if (!dual.equals(total)) {
            throw new IllegalStateException(
                    "Primal and dual objectives differ");
        }
        return new Assignment(total, columns);
    }

    public static Assignment minCost(long[][] costs) {
        return hungarian(readMatrix(costs));
    }

    public static Assignment maxWeightAll(long[][] scores) {
        BigInteger[][] cost = readMatrix(scores);
        for (int i = 0; i < cost.length; i++) {
            for (int j = 0; j < cost[i].length; j++) {
                cost[i][j] = cost[i][j].negate();
            }
        }

        Assignment minimum = hungarian(cost);
        return new Assignment(
                minimum.total().negate(), minimum.columns());
    }

    public static Assignment maxWeightOptional(long[][] scores) {
        BigInteger[][] values = readMatrix(scores);
        int n = values.length;
        int m = values[0].length;

        if ((long) n + m > Integer.MAX_VALUE - 8L) {
            throw new IllegalArgumentException(
                    "Too many extended columns");
        }

        // m real jobs, n zero-score dummy jobs.
        BigInteger[][] cost = new BigInteger[n][m + n];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < m; j++) {
                cost[i][j] = values[i][j].negate();
            }
            for (int j = m; j < m + n; j++) {
                cost[i][j] = BigInteger.ZERO;
            }
        }

        Assignment extended = hungarian(cost);
        List<Integer> realJobs = new ArrayList<>();

        for (int job : extended.columns()) {
            realJobs.add(job < m ? job : -1);
        }
        return new Assignment(
                extended.total().negate(), realJobs);
    }

    private static String format(Assignment assignment) {
        return "total=" + assignment.total()
                + ", columns=" + assignment.columns();
    }

    public static void main(String[] args) {
        long[][] classic = {
                {4, 1, 3},
                {2, 0, 5},
                {3, 2, 2}
        };
        System.out.println("Classic min: "
                + format(minCost(classic)));

        long[][] greedyTrap = {
                {1, 2},
                {2, 100}
        };
        System.out.println("Greedy trap min: "
                + format(minCost(greedyTrap)));

        long[][] rectangular = {
                {4, -2, 3, 1},
                {2, 0, 5, 2},
                {3, -1, 2, -4}
        };
        System.out.println("Rectangular min: "
                + format(minCost(rectangular)));

        long[][] profit = {
                {8, 4, 7},
                {7, 6, 6},
                {5, 9, 8}
        };
        System.out.println("Profit max required: "
                + format(maxWeightAll(profit)));

        long[][] equalCost = {
                {1, 1},
                {1, 1}
        };
        System.out.println("Equal-cost min: "
                + format(minCost(equalCost)));

        long[][] negativeScores = {
                {-8, -2},
                {-4, -6}
        };
        System.out.println("Negative scores required: "
                + format(maxWeightAll(negativeScores)));
        System.out.println("Negative scores optional: "
                + format(maxWeightOptional(negativeScores)));

        long[][] extraWorkers = {
                {5, -1},
                {4, -3},
                {2, 1}
        };
        System.out.println("More workers optional: "
                + format(maxWeightOptional(extraWorkers)));

        System.out.println("One worker min: "
                + format(minCost(new long[][] {{7, -2, 8}})));

        long large = Long.MAX_VALUE;
        long[][] hugeScores = {
                {large, 0},
                {0, large}
        };
        System.out.println("BigInteger full max: "
                + format(maxWeightAll(hugeScores)));

        long[][] extreme = {
                {Long.MIN_VALUE, Long.MAX_VALUE}
        };
        System.out.println("Long.MIN safe minimum: "
                + format(minCost(extreme)));

        try {
            minCost(extraWorkers);
            System.out.println("More workers full rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("More workers full rejected: true");
        }

        try {
            minCost(new long[][] {{1, 2}, {3}});
            System.out.println("Ragged rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Ragged rejected: true");
        }

        try {
            minCost(new long[][] {});
            System.out.println("Empty rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Empty rejected: true");
        }
    }
}
~~~

### 12.1. Biên dịch và chạy

Dùng JDK 17 trở lên, lưu tệp đúng theo public class:

~~~bash
javac -encoding UTF-8 WeightedAssignmentDemo.java
java WeightedAssignmentDemo
~~~

**Stdout chính xác theo thứ tự duyệt của chương trình:**

~~~text
Classic min: total=5, columns=[1, 0, 2]
Greedy trap min: total=4, columns=[1, 0]
Rectangular min: total=-4, columns=[1, 0, 3]
Profit max required: total=23, columns=[0, 2, 1]
Equal-cost min: total=2, columns=[0, 1]
Negative scores required: total=-6, columns=[1, 0]
Negative scores optional: total=0, columns=[-1, -1]
More workers optional: total=6, columns=[0, -1, 1]
One worker min: total=-2, columns=[1]
BigInteger full max: total=18446744073709551614, columns=[0, 1]
Long.MIN safe minimum: total=-9223372036854775808, columns=[0]
More workers full rejected: true
Ragged rejected: true
Empty rejected: true
~~~

### 12.2. Các chi tiết Java quan trọng

**Ma trận chữ nhật:** readMatrix từ chối null, rỗng và hàng có độ dài khác nhau. Nếu n>m, hungarian từ chối full assignment không khả thi. Optional thêm n cột ảo nên sau mở rộng luôn có đủ cột.

**Số học chính xác:** long đầu vào được chuyển sang BigInteger trước phép đổi dấu, cộng hoặc trừ thế vị. Tổng hai Long.MAX_VALUE là 18446744073709551614, không nằm trong long nhưng hoàn toàn hợp lệ với BigInteger.

**Khởi tạo u_i theo min của hàng:** bảo đảm thế vị đối ngẫu khả thi khi chi phí âm. Nếu mặc định u=v=0 rồi khẳng định đối ngẫu khả thi từ đầu với ma trận có âm, lập luận sẽ sai.

**minv[j] chưa biết dùng null:** không dùng một INF giả làm số nguyên lớn; trong BigInteger không có một số hữu hạn cố định lớn hơn mọi dữ liệu.

**p[0] và way[]:** hỗ trợ truy đường tăng và xoay matching. Khi một cột đã có người, có thể dời người ấy sang cột khác trước khi gán người mới.

**Dual certificate:** code xác minh tất cả reduced cost không âm, matched edge chặt, cột trống có thế vị 0 và tổng primal bằng dual. Nếu bất biến sai, không coi đáp án như đã chứng minh đúng.

**Tie-break:** quét cột theo thứ tự ID tăng, chỉ cập nhật minv khi nhỏ hơn nghiêm ngặt. Nếu nhiều matching đồng tối ưu, output có thể phụ thuộc quy tắc ấy; matching toán học không nhất thiết duy nhất.

**−1 của optional:** chỉ để báo người chưa được ghép việc thật; nội bộ Hungarian đã gán người đó một **cột ảo cụ thể**. Không nhầm −1 với ID công việc thật.

## 13. Độ phức tạp

Với n người, m công việc, n≤m:
- Có n lần thêm một hàng vào matching.
- Trong mỗi lần, cây xen kẽ có tối đa O(n) cột đã ghép cần mở rộng.
- Mỗi lần mở rộng có thể duyệt O(m) cột.

Vì vậy Hungarian có cận **O(n²m)** phép toán số học, trường hợp n=m thành **O(n³)**.

Ma trận BigInteger cần **O(nm)** bộ nhớ. Các mảng u,v,p,way,minv,used cần **O(n+m)**; danh sách cột kết quả cần O(n). Kiểm tra đối ngẫu O(nm) sau thuật toán không thay đổi cận tổng.

BigInteger là số nguyên có độ dài biến đổi: một phép cộng/trừ/so sánh không luôn là O(1) theo **số bit**. Cận trên đang nói tới số phép toán mức cao; hiệu năng thực tế còn phụ thuộc độ lớn các số.

Khi optional thêm n cột ảo, ma trận thành n×(m+n). Thời gian **O(n²(m+n))**, bộ nhớ **O(n(m+n))**. Với đồ thị hai phía **thưa** và số cặp hợp lệ rất ít, cách lưu ma trận dày có thể không phù hợp; min-cost flow hoặc thuật toán matching trên danh sách cạnh có thể tốt hơn.

## 14. Kiểm thử độc lập bằng brute force

Trên ma trận nhỏ, một oracle độc lập là **liệt kê các phép gán cột không trùng**:

~~~text
bruteFull(row, usedColumns, currentTotal):
    if row == n:
        update best min/max with currentTotal
        return

    for job from 0 to m-1:
        if job not in usedColumns:
            mark job
            bruteFull(row+1, usedColumns,
                      currentTotal + value[row][job])
            unmark job
~~~

Với optional matching, ở mỗi hàng thêm một nhánh **không ghép người này**, cộng 0 và không dùng cột thật. Matching rỗng luôn hợp lệ, nên tổng tối ưu optional **không âm** khi không có ràng buộc ghép tối thiểu.

Kiểm tra cả:
- Không có hai hàng dùng cùng một cột thật.
- Full assignment có đúng n cột thật.
- Optional cho phép nhiều −1 nhưng không lặp cột thật.
- Tổng trọng số được tính lại từ ma trận bằng đúng total.
- Kết quả bằng oracle brute force.
- Đối ngẫu Hungarian khả thi và tổng primal=dual.
- Ma trận hình chữ nhật, chi phí âm, nhiều ô bằng nhau và dữ liệu cực đại long.
- Đổi tên/hoán vị cột không làm thay đổi tổng tối ưu.
- Với full assignment, cộng cùng K vào mọi chi phí làm tổng tối ưu tăng nK.
- Nếu mọi điểm âm, optional có thể chọn matching rỗng.
- Input n>m phải bị từ chối khi full, nhưng optional vẫn có thể có matching.

### Bảng test định hướng

| Dữ liệu | Kết quả |
|---|---|
| Classic 3×3 | min 5; columns [1,0,2] |
| Greedy trap 2×2 | min 4, không phải 101 |
| Rectangular 3×4 có âm | min −4; columns [1,0,3] |
| Profit 3×3 | max full 23 |
| Ma trận 2×2 toàn cost 1 | min 2; nhiều nghiệm hòa |
| Score 2×2 toàn âm | max full −6, optional 0 |
| Score 3×2 | max optional 6; một người không ghép |
| Một người ba việc | Chọn việc min/max đúng |
| Hai điểm Long.MAX_VALUE | BigInteger max 18446744073709551614 |
| Một chi phí Long.MIN_VALUE | Không overflow |
| Full n>m | Báo đầu vào không khả thi |
| Hàng ragged hoặc ma trận rỗng | Báo đầu vào không hợp lệ |
| Có cặp người–việc bị cấm | Không dùng code ma trận đầy đủ nếu chưa mô hình hóa |

Nếu đề chỉ cần tổng tối ưu hoặc một matching bất kỳ, khi có nhiều lời giải hòa thì **không nên bắt buộc so đúng một bộ ID**. Hãy so tổng và tính hợp lệ trước; chỉ so ID khi thuật toán và tie-break cụ thể đã được yêu cầu.

## 15. Lỗi phổ biến

1. **Nhầm tối đa số cặp với tối đa tổng trọng số.**
2. **Nhầm maximal matching với maximum matching.**
3. **Cho phép bỏ người khi đề bắt buộc ghép hết** và trả matching không khả thi.
4. **Bắt buộc ghép hết khi đề cho bỏ**, chọn cạnh âm làm tổng lợi ích thấp đi.
5. **Chọn chi phí nhỏ nhất của từng hàng theo greedy**, mắc bẫy 101 thay vì 4.
6. **Không kiểm tra công việc đã dùng**, gán cùng một việc cho hai người.
7. **Không phân biệt n<m và n>m** trong full assignment.
8. **Chỉ thêm một cột ảo**, không cho nhiều người cùng bỏ trống.
9. **Dùng −1 như một công việc thật**, trong khi đó là ký hiệu không ghép.
10. **Đổi dấu trực tiếp Long.MIN_VALUE**, gây overflow.
11. **Cộng tổng bằng int/long không kiểm tra**, gây overflow ở dữ liệu lớn.
12. **Coi chi phí âm là cạnh bị cấm**, làm sai ý nghĩa trọng số.
13. **Thay cạnh cấm bằng Long.MAX_VALUE** rồi tin thuật toán chắc chắn tránh nó.
14. **Áp dụng Hungarian cho đồ thị không hai phía**, thiếu thuật toán blossom.
15. **Dùng Hungarian để xử lý công việc có sức chứa >1** mà không sửa mô hình.
16. **Không kiểm tra ma trận ragged**, đọc sai số cột.
17. **Khởi tạo minv bằng 0** dù chưa biết slack, làm thuật toán không cập nhật đúng.
18. **Không lưu way[] khi cải thiện slack**, truy đường tăng sai.
19. **Không xoay matching trên đường tăng**, làm một hàng mất công việc.
20. **Nhầm p[j] là cột của hàng j**, trong khi p[j] là hàng tại cột j.
21. **Bỏ cập nhật thế vị bằng Δ**, phá điều kiện chặt/đối ngẫu.
22. **Đổi dấu sai khi chuyển min sang max**, tối ưu nhầm chiều.
23. **Cho rằng có nhiều trọng số bằng nhau chắc chắn có nhiều matching tối ưu**, bỏ qua các ràng buộc còn lại.
24. **Cho rằng tie-break cố định chứng minh nghiệm là duy nhất**, dù nó chỉ chọn một nghiệm.
25. **Cho rằng max-weight optional cũng tối đa số cặp**, khác mục tiêu từ điển.
26. **Bỏ qua bộ nhớ O(nm)** khi chỉ có vài cặp hợp lệ.
27. **Không so tổng thực tế từ columns với total**, không phát hiện sai truy vết.
28. **Không kiểm tra thế vị đối ngẫu**, bỏ mất chứng chỉ tối ưu mạnh.
29. **Chỉ test ma trận vuông, chi phí dương**, bỏ sót âm, rectangular và dummy.
30. **Ép so danh sách ID cột với một đáp án duy nhất** trong bài có nhiều nghiệm hòa.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Ghép cặp trọng số khác matching cực đại số lượng ở đâu?

**Đáp án:** Một bài tối ưu tổng điểm, một bài tối đa số cạnh. Với điểm âm và cho phép bỏ ghép, các nghiệm có thể khác nhau.

**Câu 2.** Khi nào có full left assignment trên ma trận đầy đủ n×m?

**Đáp án:** Khi n≤m. Mỗi người có một cột riêng; m−n cột có thể không dùng.

**Câu 3.** Vì sao greedy trên [[1,2],[2,100]] trả sai?

**Đáp án:** Greedy có thể trả tổng 1+100=101, nhưng phân công đảo cột cho hai hàng có tổng 2+2=4.

**Câu 4.** Đường tăng trong Hungarian dùng để làm gì?

**Đáp án:** Chuyển các hàng đã ghép sang cột khác theo đường xen kẽ để nhường công việc cho hàng mới mà không trùng cột.

**Câu 5.** Reduced cost là gì?

**Đáp án:** \(r_{ij}=c_{ij}-u_i-v_j\). Nó không âm với thế vị đối ngẫu khả thi; cạnh chặt có reduced cost 0.

**Câu 6.** Vì sao có thể khởi tạo u_i bằng min của hàng?

**Đáp án:** Vì khi v_j=0, ta có u_i+v_j≤c_ij cho mọi j, kể cả khi c_ij âm.

**Câu 7.** Vì sao tổng primal bằng dual chứng minh tối ưu?

**Đáp án:** Dual khả thi là cận dưới mọi full assignment. Nghiệm ghép đạt đúng cận dưới ấy nên không có nghiệm nào rẻ hơn.

**Câu 8.** Muốn tối đa điểm nhưng vẫn ghép mọi người, làm thế nào?

**Đáp án:** Lấy chi phí đối dấu của điểm, giải Hungarian min-cost, đảo dấu tổng. Dùng BigInteger để không tràn khi điểm bằng Long.MIN_VALUE.

**Câu 9.** Vì sao max-weight optional cần n cột ảo?

**Đáp án:** Vì có thể cả n người không được ghép, trong khi mỗi cột chỉ được dùng tối đa một lần.

**Câu 10.** Điểm toàn âm có thể cho matching tối ưu tổng 0 khi nào?

**Đáp án:** Khi được phép không ghép ai; matching rỗng có tổng 0. Full matching có thể buộc chấp nhận tổng âm.

**Câu 11.** Với ba người hai việc, có thể gọi minCost full không?

**Đáp án:** Không; cần ít nhất ba việc thật. Nhưng optional matching thêm các cột ảo có thể xử lý.

**Câu 12.** Hungarian trong bài có tự hiểu cặp bị cấm không?

**Đáp án:** Không, mọi ô đều là cặp hợp lệ. Phải mô hình hóa cặp không tồn tại và dùng thuật toán có khả năng xử lý chúng.

**Câu 13.** Có thể giải matching trọng số đồ thị không hai phía bằng Hungarian không?

**Đáp án:** Không trực tiếp. Có thể cần weighted blossom hoặc phương pháp matching tổng quát.

**Câu 14.** Độ phức tạp Hungarian hình chữ nhật n×m?

**Đáp án:** O(n²m) phép toán số học với n≤m; hình vuông O(n³). Optional có m+n cột nên O(n²(m+n)).

**Câu 15.** BigInteger giải quyết vấn đề nào?

**Đáp án:** Đổi dấu Long.MIN_VALUE và cộng/trừ thế vị/tổng trọng số mà không tràn long.

**Câu 16.** Nếu có nhiều matching cùng tổng tối ưu, nên test ra sao?

**Đáp án:** Kiểm tra giá trị tối ưu và tính hợp lệ của matching; chỉ áp đúng một danh sách ID khi có yêu cầu tie-break cụ thể.

**Ghi nhớ:** Bài toán phân công là **matching hai phía có trọng số** với ràng buộc phủ đủ người. Hungarian dùng **đường tăng, thế vị và chi phí giảm** để giải full assignment trong O(n²m). Với maximization, đổi dấu điểm; nếu cho phép người không có việc, thêm **n cột ảo điểm 0**. Luôn phân biệt cardinality với weight, chi phí âm với cạnh bị cấm, full với optional, và bài hai phía với matching tổng quát.
