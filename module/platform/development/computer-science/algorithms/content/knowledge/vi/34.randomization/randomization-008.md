# Thuật toán Karger cho lát cắt nhỏ nhất

**Thuật toán Karger** là một thuật toán **ngẫu nhiên hóa** để tìm **lát cắt nhỏ nhất toàn cục (global minimum cut)** trên đồ thị vô hướng. Thay vì liệt kê tất cả phân hoạch đỉnh, thuật toán liên tiếp **chọn ngẫu nhiên đều một cạnh đang nối hai nhóm đỉnh khác nhau và co cạnh đó**. Khi còn hai nhóm đỉnh (hai siêu đỉnh), số cạnh bắc qua giữa chúng là một giá trị lát cắt ứng viên. Một lần chạy có thể chưa đạt tối ưu, nhưng nhiều lần chạy độc lập giúp giảm nhanh xác suất thất bại.

Bài **“Thuật toán Karger cho lát cắt nhỏ nhất”**, thuộc nhóm **Ngẫu nhiên hóa** của Computer Science Algorithms, giải thích đầy đủ việc co cạnh của **đa đồ thị**, tác dụng của cạnh song song và self-loop, thuật toán chọn cạnh đều bằng reservoir sampling, DSU, chứng minh xác suất thành công tối thiểu **2/[n(n−1)]** trên đồ thị vô hướng liên thông, cách lặp để khuếch đại xác suất, cận thời gian của cách cài thực tế, ví dụ K4 có thể thất bại, và kiểm thử độc lập bằng vét cạn.

Phần Java 17+ là chương trình độc lập, có kiểm thử kết quả cùng chứng cứ hai phía lát cắt. Các phép thử thực tế đã qua **1.098 đồ thị đơn vét cạn** và **1.600 đa đồ thị có seed** với cạnh song song và self-loop.

## 1. Lát cắt toàn cục là gì?

Cho đồ thị G=(V,E) vô hướng. Chọn một tập S sao cho:

~~~text
S khác rỗng.
V\S khác rỗng.
~~~

Lát cắt δ(S) là tập những **bản sao cạnh** có đúng một đầu trong S và đầu còn lại ở V\S. Giá trị lát cắt là số cạnh bắc qua:

~~~text
cut(S) = |δ(S)|.

λ(G) = min cut(S)
       với mọi S khác rỗng, S khác V.
~~~

Giá trị λ(G) gọi là **global min-cut**. Nếu G có n≥2 đỉnh nhưng không liên thông, λ(G)=0: có thể lấy một thành phần liên thông làm S. Với n=0 hoặc n=1, không tồn tại phân hoạch thành hai nhóm khác rỗng; API trong bài chọn quy ước trả 0, phải nói rõ đây là quy ước phần mềm.

**Không nhầm global min-cut với s–t min-cut:** ở bài toán s–t, một đỉnh s phải nằm bên này và t bên kia, còn Karger cơ bản ở đây được tự do chọn hai phía.

## 2. Đa đồ thị: cạnh song song phải được giữ nguyên

Thuật toán Karger hoạt động tự nhiên trên **đa đồ thị (multigraph)**: có thể có nhiều cạnh với cùng hai đầu mút. Mỗi cạnh là một phần tử riêng trong danh sách E.

Ví dụ:

~~~text
V={0,1}.
E={(0,1),(0,1),(1,0)}.

Global min-cut = 3.
~~~

Cả ba bản sao cạnh đều băng qua lát cắt {0}|{1}; cạnh (1,0) là một bản sao vô hướng riêng, không bị bỏ chỉ vì hai đầu viết ngược thứ tự.

Nếu thêm hai self-loop (0,0) và (1,1), chúng **không băng qua bất kỳ lát cắt nào**. Khi co cạnh, các cạnh từng nối hai đỉnh có thể trở thành self-loop vì hai đầu bây giờ ở chung một siêu đỉnh; phải bỏ chúng khỏi tập cạnh hợp lệ để co tiếp.

**Sai lầm nghiêm trọng:** chuyển List<Edge> thành Set<Edge> làm mất bản sao cạnh song song, vừa thay đổi giá trị cut vừa thay đổi phân phối xác suất của thuật toán.

## 3. Co một cạnh là gì?

Chọn cạnh (u,v) sao cho u,v đang thuộc **hai siêu đỉnh khác nhau**. Co cạnh nghĩa là hợp nhất hai siêu đỉnh, coi mọi đỉnh cũ trong hai nhóm thành một nhóm mới. Các cạnh nối nhóm mới với những siêu đỉnh khác vẫn được giữ, kể cả những cạnh có cùng hai siêu đỉnh.

~~~text
Trước:
A -- B   và   A -- C, B -- C.

Co A--B:
{A,B} -- C có hai bản sao cạnh.
A--B trở thành cạnh nội bộ (self-loop).
~~~

Một lần co hợp lệ làm **số siêu đỉnh giảm đúng một**. Nếu chọn cạnh đã trở thành self-loop, số siêu đỉnh không giảm và thuật toán mất bất biến tiến triển.

Trong cách cài Java, không cần sửa danh sách cạnh gốc. DSU ghi nhận nhóm của từng đầu mút; hai đầu có cùng root thì cạnh được xem là self-loop trong đồ thị đã co, hai đầu khác root thì vẫn là cạnh hợp lệ.

## 4. Ví dụ tam giác

Cho tam giác:

~~~text
V={0,1,2}.
E={(0,1),(1,2),(2,0)}.
~~~

Mọi phân hoạch không tầm thường đều cắt hai cạnh, nên λ(G)=2. Nếu Karger chọn cạnh (0,1) để co, ta còn hai siêu đỉnh A={0,1} và B={2}. Hai cạnh cũ (1,2) và (2,0) đều trở thành cạnh A–B.

Giá trị đếm được là **2**. Chọn cạnh đầu tiên nào trong tam giác cũng có kết quả như nhau; xác suất thành công thực tế của tam giác là 1. Điều này **không mâu thuẫn** với cận dưới tổng quát 2/[3·2]=1/3: cận dưới không phải xác suất chính xác ở mọi đồ thị.

## 5. Pseudo-code một lượt Karger

~~~text
KargerOnce(G):
    Ban đầu mỗi đỉnh là một siêu đỉnh.

    while số siêu đỉnh > 2:
        Chọn đều một bản sao cạnh e
        có hai đầu ở hai siêu đỉnh khác nhau.

        Nếu không còn cạnh hợp lệ:
            Đồ thị còn lại không liên thông.
            Dừng, có thể tạo cut bằng 0.

        Co hai siêu đỉnh ở hai đầu e.

    Chọn một siêu đỉnh làm nhóm A,
    tất cả đỉnh gốc còn lại làm nhóm B.

    Đếm các bản sao cạnh G gốc
    có hai đầu thuộc hai nhóm khác nhau.

    Trả cut size cùng hai phía A và B.
~~~

Nếu n≥2 và đồ thị liên thông, luôn có cạnh nối giữa các siêu đỉnh khi còn hơn một siêu đỉnh, nên thuật toán có thể co tới đúng hai siêu đỉnh.

Với đồ thị **không liên thông**, cần kiểm tra tình huống không còn cạnh hợp lệ trước khi còn hai siêu đỉnh. Chương trình xử lý bằng cách thoát vòng lặp và trả phân hoạch có giá trị 0, thay vì chọn ngẫu nhiên từ một tập rỗng.

## 6. Chọn cạnh phải đều trên các bản sao còn sống

Giả sử sau khi co, ba siêu đỉnh A,B,C có:

~~~text
5 cạnh nối A-B.
1 cạnh nối A-C.
2 cạnh nối B-C.

Tổng 8 cạnh hợp lệ.
~~~

Karger chuẩn chọn một bản sao cạnh **đều trong 8 bản sao**, do đó xác suất chọn loại A-B là 5/8, A-C là 1/8 và B-C là 2/8.

Nếu chọn đều ba **cặp siêu đỉnh** A-B, A-C, B-C, mỗi loại có xác suất 1/3. Đó **không còn là phân phối của Karger chuẩn**; chứng minh xác suất thành công không thể đem áp nguyên dạng.

Tương tự, chọn một đỉnh ngẫu nhiên rồi một cạnh kề cũng chưa chắc chọn đều trên cạnh, vì các đỉnh có bậc khác nhau. Muốn nhận cận Karger kinh điển, phải thực sự chọn đều từng bản sao cạnh hợp lệ.

## 7. Reservoir sampling và DSU

Một cách dễ kiểm toán là quét toàn bộ cạnh gốc, bỏ cạnh có hai đầu cùng DSU root, rồi dùng **reservoir sampling** để chọn đều một trong những cạnh còn hợp lệ:

~~~text
selected = không có.
seen = 0.

for mỗi bản sao cạnh e:
    if find(e.u) != find(e.v):
        seen++
        với xác suất 1/seen:
            selected = e.
~~~

Chứng minh: sau k cạnh hợp lệ, mỗi cạnh đã đọc có xác suất 1/k được giữ. Cạnh thứ k được chọn với xác suất 1/k; một cạnh cũ sống từ k−1 bước với xác suất 1/(k−1), rồi không bị thay với xác suất (k−1)/k, nhân lại bằng 1/k.

Trong Java:

~~~java
candidates++;
if (random.nextInt(candidates) == 0) {
    selected = i;
}
~~~

DSU gồm `find` có **path compression** và `union` theo **size**. Nó biểu diễn mỗi siêu đỉnh bằng một tập các nhãn đỉnh gốc và đếm components. Mỗi cạnh hợp lệ được chọn làm giảm components một đơn vị.

## 8. Ví dụ K4 có thể thất bại

Đồ thị đầy đủ K4 có bốn đỉnh 0,1,2,3 và 6 cạnh. Mỗi đỉnh bậc 3, nên global min-cut là **3**: tách một đỉnh khỏi ba đỉnh còn lại.

Giả sử lần co đầu chọn (0,1), tạo siêu đỉnh A={0,1}. Khi ấy ba siêu đỉnh A,2,3 có:

~~~text
A--2: 2 bản sao.
A--3: 2 bản sao.
2--3: 1 bản sao.
Tổng: 5 cạnh.
~~~

Nếu lần co tiếp theo chọn (2,3), ta thu hai siêu đỉnh {0,1} và {2,3}; có **4 cạnh** băng qua. Lượt Karger này trả **4**, lớn hơn min-cut thật 3.

Nếu lần co thứ hai chọn một trong **4** cạnh nối A với 2 hoặc 3, ta nhận phân hoạch một đỉnh so với ba đỉnh còn lại, cut=3. Vì thế trong K4, xác suất thành công của một lượt là **4/5**, xác suất trả 4 là 1/5.

Ví dụ minh họa bản chất **Monte Carlo một phía**: một lượt luôn trả **một cut hợp lệ**, nhưng có thể trả một cut chưa tối ưu.

## 9. Bất biến phân hoạch và chứng cứ kết quả

Ở mọi thời điểm, mỗi đỉnh gốc thuộc **đúng một siêu đỉnh**. Các siêu đỉnh tạo một phân hoạch của tập V. Một lần `union` hợp lệ chỉ hợp hai nhóm, không mất đỉnh hay tạo đỉnh mới.

Một cạnh gốc được xem là nội bộ nếu hai đầu cùng root, hoặc đang sống nếu hai đầu khác root. Mọi cạnh song song đều xuất hiện riêng trong danh sách, nên bội số được bảo toàn trong việc đếm.

Sau khi có hai phía A,B, hàm `partition` đếm trên danh sách cạnh gốc:

~~~text
crossing = 0
for mỗi Edge(u,v) trong G.edges:
    if side(u) != side(v):
        crossing++
~~~

Đây là **chứng cứ kiểm tra được**: Cut lưu size, sideA, sideB. Ta có thể tự đếm lại mà không cần tin vào trạng thái trung gian hoặc ngẫu nhiên đã tạo kết quả.

## 10. Một lượt không thể trả nhỏ hơn min-cut thật

Định nghĩa λ(G) là **giá trị nhỏ nhất trên tất cả phân hoạch hợp lệ**. Một lượt Karger trả một phân hoạch hợp lệ khi n≥2, do đó:

~~~text
cut(KargerOnce(G)) >= λ(G).
~~~

Bất đẳng thức này **tất định**: không phụ thuộc may mắn của random. Một lượt có thể trả lớn hơn λ(G), nhưng không thể trả giá trị nhỏ hơn λ(G) trừ khi có lỗi ở cài đặt hoặc oracle.

Khi chạy nhiều lượt và lấy min:

~~~text
best = min(cut_1, cut_2, ..., cut_T).
best >= λ(G).
~~~

Chỉ cần một lượt trong số đó đạt đúng min-cut, best sẽ bằng λ(G). Vì thế thuật toán giảm xác suất sai **theo hướng quá lớn**, không giảm độ tin cậy ở chiều ngược lại.

## 11. Chứng minh cận xác suất 2/[n(n−1)]

Giả sử G vô hướng **liên thông**, n≥2, và k=λ(G)>0. Chọn **một min-cut cố định** C gồm k bản sao cạnh.

Nếu toàn bộ quá trình **không co bất kỳ cạnh nào thuộc C**, hai phía của C không bao giờ bị nhập lẫn. Khi còn hai siêu đỉnh, thuật toán trả đúng C.

Giả sử đã co đến r siêu đỉnh nhưng vẫn chưa chạm C. Mỗi siêu đỉnh tương ứng một tập đỉnh gốc không rỗng và không phải toàn bộ V, nên ranh giới của mỗi siêu đỉnh có ít nhất k bản sao cạnh (vì k là global min-cut). Tổng bậc của đồ thị đã co ít nhất rk, do đó số cạnh hợp lệ m_r thỏa:

~~~text
m_r >= r*k/2.
~~~

Đúng **k cạnh thuộc C** còn đi qua hai phía của lát cắt cố định. Chọn đều cạnh sống nên:

~~~text
P(co cạnh C ở bước r | C còn nguyên)
     = k/m_r
     <= 2/r.

P(tránh C ở bước r | C còn nguyên)
     >= (r−2)/r.
~~~

Nhân các xác suất **có điều kiện** khi r giảm từ n xuống 3:

~~~text
P(giữ nguyên C)
 >= product_(r=3)^n [(r−2)/r]
 = [1*2*...*(n−2)]/[3*4*...*n]
 = 2/[n(n−1)].
~~~

Vậy xác suất **một lượt trả min-cut** ít nhất bằng 2/[n(n−1)]. Đây là cận dưới, không có nghĩa mọi đồ thị thành công với đúng xác suất ấy.

Bản chứng minh phụ thuộc việc **chọn đều trên cạnh còn sống** và đa đồ thị giữ đúng bội số; nếu sửa phân phối ngẫu nhiên, các bước k/m_r có thể không còn đúng.

## 12. Khuếch đại xác suất bằng T lượt

Giả sử một lượt có xác suất thành công tối thiểu p=2/[n(n−1)]. Chạy T lượt **độc lập**, mỗi lượt bắt đầu với DSU mới, rồi giữ cut nhỏ nhất.

Xác suất tất cả T lượt đều thất bại được chặn:

~~~text
P(miss all T)
 <= (1−p)^T
 <= exp(−p*T).
~~~

Nếu muốn xác suất thất bại không quá δ với 0<δ<1, có thể chọn:

~~~text
T >= [n(n−1)/2] * ln(1/δ).
~~~

Do đó số lượt O(n² log(1/δ)) là đủ theo **cận kinh điển**. Với n=2, bài toán có hai đỉnh nên một lượt đã cho cut duy nhất.

`java.util.Random` trong demo là **PRNG** với seed để kiểm thử tái lập được; chứng minh độc lập ở trên là mô hình các lựa chọn đều, độc lập lý tưởng. Không tự suy luận rằng một seed cố định cung cấp bảo đảm xác suất hay biến Karger thành thuật toán tất định.

## 13. Vì sao phải lấy min thay vì trung bình?

Karger có thể trả kết quả quá lớn; trung bình của các cut quan sát được không phải min-cut và có thể lớn hơn λ(G), ngay cả khi một vài lượt đã tìm đúng.

Một cách lặp đúng:

~~~text
best = chưa có.
random = Random(seed).

for t=1..T:
    current = KargerOnce(G, random).
    if best chưa có hoặc current.size < best.size:
        best = current.

return best.
~~~

Trong mã thực tế, khi size hòa nhau, hàm `repeated` dùng **thứ tự từ điển của sideA** để phá hòa cho kết quả có thể tái hiện. Quy tắc tie này **không ảnh hưởng xác suất đạt giá trị min-cut**.

Luôn lưu cả hai phía của best nếu cần chứng cứ. Việc chỉ giữ số nguyên cut mà không thể khôi phục phân hoạch có thể khiến người dùng khó xác minh và khó sử dụng kết quả ở bước sau.

## 14. Đồ thị không liên thông

Nếu G có từ hai thành phần liên thông, chọn một thành phần làm S, các thành phần còn lại làm V\S; không có cạnh nối giữa chúng, nên global min-cut bằng **0**.

Ví dụ:

~~~text
V={0,1,2,3}.
E={(0,1),(2,3)}.

Hai thành phần: {0,1} và {2,3}.
S={0,1}, V\S={2,3}.
cut(S)=0.
~~~

Karger không thể co hai nhóm ở hai thành phần gốc khác nhau vì không có cạnh nối chúng. Nếu không còn cạnh sống khi số siêu đỉnh vẫn lớn hơn 2, chương trình dừng, chọn nhóm chứa đỉnh 0 làm A và phần còn lại làm B. Hai phía vẫn tạo cut=0.

Trường hợp này rất quan trọng: một vòng `while components>2` không kiểm tra tập cạnh hợp lệ rỗng có thể lỗi hoặc không kết thúc trên input disconnected.

## 15. Các trường hợp suy biến

| Đầu vào | Ý nghĩa/hành vi của API |
| --- | --- |
| n=0 | Theo quy ước trả cut=0, cả hai phía rỗng |
| n=1 | Theo quy ước trả cut=0, A=[0], B=[] |
| n=2 có t cạnh chéo | Cut chính xác bằng t |
| Chỉ có self-loop | Cut=0 |
| Không có cạnh, n≥2 | Cut=0 |
| Đồ thị đường đi liên thông | Min-cut=1 |
| Đồ thị không liên thông n≥2 | Min-cut=0 |
| Endpoints không thuộc [0,n) | IllegalArgumentException |
| Gọi repeated với T≤0 | IllegalArgumentException |

Với n=0/1, không tồn tại hai phía không rỗng nên phải nói rõ kết quả 0 là **quy ước để API có tổng quát**, không phải kết quả của phép tối ưu trên tập phân hoạch hợp lệ.

Danh sách cạnh của Graph được sao chép bất biến bằng `List.copyOf`. Mã kiểm tra nhãn đỉnh và không làm thay đổi đối tượng Graph gốc khi chạy các lượt.

## 16. Độ phức tạp của bản cài DSU quét cạnh

Gọi n=|V|, m=|E| gồm từng **bản sao cạnh**, cả self-loop. Mỗi lần co hợp lệ làm số siêu đỉnh giảm 1, nên tối đa **n−2** bước co.

Ở mỗi bước, mã quét toàn bộ m cạnh gốc, thực hiện hai phép `find` để kiểm tra còn sống. Với DSU dùng path compression và union by size, chi phí trung bình được chặn bởi hàm ngược Ackermann α(n).

Vì vậy:

~~~text
Một lượt:
    O(n*m*α(n) + n) thời gian.
    O(n) bộ nhớ bổ sung ngoài danh sách cạnh.

Nếu coi DSU/find gần hằng số:
    O(n*m) thời gian.

T lượt:
    O(T*n*m*α(n) + T*n).
~~~

Đồ thị lưu O(n+m) nếu tính cả danh sách cạnh và DSU. `bruteMinCut` là oracle độc lập có thời gian **O(m·2^n)** trên dữ liệu nhỏ.

Không gọi đoạn code này là O(n+m), cũng không dùng cận thời gian của **Karger–Stein** cho Karger đơn giản. Có những thuật toán min-cut cải tiến nhanh hơn nhưng cần cấu trúc và chứng minh riêng.

## 17. Oracle vét cạn tất định

Để kiểm thử thuật toán xác suất, dùng một oracle cho đáp án **chắc chắn** trên input nhỏ. Mọi cách cắt S|V\S đều trùng với cách cắt đảo hai phía, nên cố định đỉnh 0 luôn thuộc S rồi liệt kê các lựa chọn của các đỉnh khác.

~~~text
S phải chứa đỉnh 0.
Mỗi đỉnh 1..n−1 chọn vào S hoặc không.
Loại duy nhất trường hợp S=V.

Số phân hoạch cần thử:
2^(n−1) − 1.
~~~

Mỗi phân hoạch, duyệt mọi cạnh để đếm bản sao có hai đầu khác phía. Lấy giá trị nhỏ nhất, thu đúng **global min-cut**.

Oracle này không dùng random, không dùng DSU và không co cạnh. Trong demo, hàm `bruteMinCut` giới hạn n≤15 để tránh bùng nổ 2^n; dùng kiểm thử chứ không dùng làm thuật toán chính trên input lớn.

## 18. Chứng cứ Cut và kiểm tra hai phía

Bản Java trả `Cut(size, sideA, sideB)`.

Một witness hợp lệ phải thỏa:

- Mỗi đỉnh đầu vào thuộc **đúng một phía**, không mất hay lặp.
- Với n≥2, cả hai phía **khác rỗng**.
- Đỉnh 0 thuộc phía A (theo quy ước của hàm `partition`).
- Đếm lại số cạnh gốc đi qua ranh giới phải bằng đúng `size`.
- Các self-loop luôn là cạnh cùng phía và không được tính.
- Nhiều bản sao cạnh bắc qua ranh giới phải được tính nhiều lần.

Với witness hợp lệ, ta có một cận trên chắc chắn cho min-cut thật: λ(G)≤size. Khi lặp và có nhiều witness, giữ witness có size nhỏ nhất.

Hàm `checkWitness` trong bộ test thực hiện các kiểm tra này độc lập với quá trình lấy mẫu cạnh.

## 19. Chương trình Java 17+ đầy đủ

Lưu toàn bộ mã dưới đây vào **KargerMinimumCut.java**. Nội dung gồm:

- `Edge(u,v)`: một bản sao cạnh vô hướng.
- `Graph(vertices, edges)`: dữ liệu bất biến, kiểm tra endpoints.
- `DSU`: union by size và path compression.
- `kargerOnce`: một lượt chọn **đều cạnh còn sống** nhờ reservoir sampling.
- `partition`: chuyển DSU thành hai phía và đếm lại cut trên cạnh gốc.
- `repeated`: chạy T lượt, chọn giá trị nhỏ nhất và phá hòa có quy tắc.
- `bruteMinCut`: duyệt mọi phân hoạch để làm oracle.
- `checkWitness` và `verify`: kiểm tra dữ liệu, partition, min-cut thật và các trường hợp biên.

**Lưu ý:** lõi Karger không gọi oracle. Hàm brute-force chỉ dùng trong phần kiểm thử để phát hiện lỗi. `Random` dùng seed cố định để stdout và bộ thử tái lập được trên cùng phiên bản mã.

~~~java
import java.util.*;

public final class KargerMinimumCut {
    private KargerMinimumCut() { }

    public record Edge(int u, int v) { }

    public record Graph(int vertices, List<Edge> edges) {
        public Graph {
            if (vertices < 0 || edges == null) {
                throw new IllegalArgumentException("invalid graph");
            }
            for (Edge edge : edges) {
                if (edge == null || edge.u() < 0 || edge.u() >= vertices
                        || edge.v() < 0 || edge.v() >= vertices) {
                    throw new IllegalArgumentException("invalid endpoint");
                }
            }
            edges = List.copyOf(edges);
        }
    }

    public record Cut(int size, List<Integer> sideA, List<Integer> sideB) { }

    private static final class DSU {
        private final int[] parent;
        private final int[] size;
        private int components;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
            components = n;
            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int x) {
            if (parent[x] != x) {
                parent[x] = find(parent[x]);
            }
            return parent[x];
        }

        void union(int a, int b) {
            int rootA = find(a), rootB = find(b);
            if (rootA == rootB) return;
            if (size[rootA] < size[rootB]) {
                int t = rootA;
                rootA = rootB;
                rootB = t;
            }
            parent[rootB] = rootA;
            size[rootA] += size[rootB];
            components--;
        }
    }

    private static Graph graph(int n, int... endpoints) {
        if (endpoints.length % 2 != 0) {
            throw new IllegalArgumentException("odd number of endpoints");
        }
        List<Edge> edges = new ArrayList<>();
        for (int i = 0; i < endpoints.length; i += 2) {
            edges.add(new Edge(endpoints[i], endpoints[i + 1]));
        }
        return new Graph(n, edges);
    }

    private static Cut partition(Graph graph, DSU dsu) {
        int n = graph.vertices();
        if (n == 0) return new Cut(0, List.of(), List.of());
        List<Integer> sideA = new ArrayList<>();
        List<Integer> sideB = new ArrayList<>();
        int rootZero = dsu.find(0);
        for (int i = 0; i < n; i++) {
            if (dsu.find(i) == rootZero) {
                sideA.add(i);
            } else {
                sideB.add(i);
            }
        }

        int crossing = 0;
        for (Edge edge : graph.edges()) {
            if ((dsu.find(edge.u()) == rootZero)
                    != (dsu.find(edge.v()) == rootZero)) {
                crossing++;
            }
        }
        return new Cut(crossing, List.copyOf(sideA), List.copyOf(sideB));
    }

    public static Cut kargerOnce(Graph graph, Random random) {
        if (graph == null || random == null) {
            throw new IllegalArgumentException("null graph or random");
        }
        DSU dsu = new DSU(graph.vertices());
        while (dsu.components > 2) {
            int selected = -1;
            int candidates = 0;
            List<Edge> edges = graph.edges();

            for (int i = 0; i < edges.size(); i++) {
                Edge edge = edges.get(i);
                if (dsu.find(edge.u()) != dsu.find(edge.v())) {
                    candidates++;
                    if (random.nextInt(candidates) == 0) {
                        selected = i;
                    }
                }
            }
            if (selected == -1) {
                // All remaining components are disconnected.
                break;
            }
            Edge picked = edges.get(selected);
            dsu.union(picked.u(), picked.v());
        }
        return partition(graph, dsu);
    }

    private static int compareIntLists(List<Integer> a, List<Integer> b) {
        int size = Math.min(a.size(), b.size());
        for (int i = 0; i < size; i++) {
            int cmp = Integer.compare(a.get(i), b.get(i));
            if (cmp != 0) return cmp;
        }
        return Integer.compare(a.size(), b.size());
    }

    public static Cut repeated(Graph graph, int trials, long seed) {
        if (graph == null || trials <= 0) {
            throw new IllegalArgumentException("graph or trials invalid");
        }
        Random random = new Random(seed);
        Cut best = null;
        for (int t = 0; t < trials; t++) {
            Cut candidate = kargerOnce(graph, random);
            if (best == null
                    || candidate.size() < best.size()
                    || (candidate.size() == best.size()
                        && compareIntLists(candidate.sideA(),
                                           best.sideA()) < 0)) {
                best = candidate;
            }
        }
        return best;
    }

    public static int bruteMinCut(Graph graph) {
        if (graph == null || graph.vertices() > 15) {
            throw new IllegalArgumentException(
                    "brute force requires at most 15 vertices");
        }
        int n = graph.vertices();
        if (n < 2) return 0;
        int best = Integer.MAX_VALUE;
        int masks = 1 << (n - 1);
        for (int mask = 0; mask < masks - 1; mask++) {
            boolean[] sideA = new boolean[n];
            sideA[0] = true;
            for (int vertex = 1; vertex < n; vertex++) {
                sideA[vertex] = (mask & (1 << (vertex - 1))) != 0;
            }
            int crossing = 0;
            for (Edge edge : graph.edges()) {
                if (sideA[edge.u()] != sideA[edge.v()]) {
                    crossing++;
                }
            }
            best = Math.min(best, crossing);
        }
        return best;
    }

    private static void checkWitness(Graph graph, Cut result) {
        int n = graph.vertices();
        boolean[] seen = new boolean[n];
        boolean[] sideA = new boolean[n];
        for (int v : result.sideA()) {
            if (v < 0 || v >= n || seen[v]) {
                throw new AssertionError("duplicate/invalid vertex in A");
            }
            seen[v] = true;
            sideA[v] = true;
        }
        for (int v : result.sideB()) {
            if (v < 0 || v >= n || seen[v]) {
                throw new AssertionError("duplicate/invalid vertex in B");
            }
            seen[v] = true;
        }
        for (boolean present : seen) {
            if (!present) throw new AssertionError("missing vertex");
        }
        if (n >= 2
                && (result.sideA().isEmpty() || result.sideB().isEmpty())) {
            throw new AssertionError("nontrivial cut must split vertices");
        }
        if (n >= 1
                && (result.sideA().isEmpty() || result.sideA().get(0) != 0)) {
            throw new AssertionError("vertex 0 must belong to A");
        }
        int crossing = 0;
        for (Edge edge : graph.edges()) {
            if (sideA[edge.u()] != sideA[edge.v()]) {
                crossing++;
            }
        }
        if (result.size() != crossing) {
            throw new AssertionError("cut weight differs from witness");
        }
    }

    private static void checkGraph(Graph graph,
                                   int trials, long seed) {
        int exact = bruteMinCut(graph);
        Cut single = kargerOnce(graph, new Random(seed));
        Cut best = repeated(graph, trials, seed + 9);
        checkWitness(graph, single);
        checkWitness(graph, best);
        if (single.size() < exact) {
            throw new AssertionError("random contraction beat true optimum");
        }
        if (best.size() != exact) {
            throw new AssertionError("repeated failed: graph=" + graph
                    + " best=" + best.size() + " oracle=" + exact);
        }
    }

    public static void verify() {
        int simpleGraphs = 0;
        for (int n = 2; n <= 5; n++) {
            List<Edge> possible = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                for (int v = u + 1; v < n; v++) {
                    possible.add(new Edge(u, v));
                }
            }
            int subsets = 1 << possible.size();
            for (int mask = 0; mask < subsets; mask++) {
                List<Edge> edges = new ArrayList<>();
                for (int bit = 0; bit < possible.size(); bit++) {
                    if ((mask & (1 << bit)) != 0) {
                        edges.add(possible.get(bit));
                    }
                }
                Graph graph = new Graph(n, edges);
                checkGraph(graph, 160, 4532026L + n * 10000L + mask);
                simpleGraphs++;
            }
        }

        Random random = new Random(4532026L);
        int randomGraphs = 0;
        for (int trial = 0; trial < 1600; trial++) {
            int n = 2 + random.nextInt(5);
            int m = random.nextInt(23);
            List<Edge> edges = new ArrayList<>();
            for (int i = 0; i < m; i++) {
                int u = random.nextInt(n);
                int v = random.nextInt(n);
                edges.add(new Edge(u, v));
            }
            checkGraph(new Graph(n, edges), 256, 880000L + trial);
            randomGraphs++;
        }

        Graph triangle = graph(3, 0, 1, 1, 2, 2, 0);
        Graph parallel = graph(2, 0, 1, 0, 1, 1, 0,
                                 0, 0, 1, 1);
        Graph disconnected = graph(4, 0, 1, 2, 3);
        Graph withLoops = graph(3, 0, 0, 1, 1, 2, 2,
                                   0, 1, 1, 2);
        for (Graph graph : List.of(triangle, parallel,
                                   disconnected, withLoops,
                                   graph(0), graph(1), graph(4))) {
            checkGraph(graph, 200, 123456L);
        }
        if (repeated(parallel, 20, 11L).size() != 3
                || repeated(disconnected, 20, 11L).size() != 0) {
            throw new AssertionError("parallel/disconnected boundary");
        }

        boolean rejected = false;
        try {
            graph(3, 0, 3);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        if (!rejected) throw new AssertionError("endpoint not validated");
        rejected = false;
        try {
            repeated(triangle, 0, 9L);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        if (!rejected) throw new AssertionError("trial count not validated");

        System.out.println("Exhaustive simple graphs: "
                           + simpleGraphs + " PASS");
        System.out.println("Seeded multigraphs: "
                           + randomGraphs + " PASS");
        System.out.println("Cut witnesses and boundary checks: PASS");
    }

    public static void main(String[] args) {
        Graph triangle = graph(3, 0, 1, 1, 2, 2, 0);
        Graph path = graph(4, 0, 1, 1, 2, 2, 3);
        Graph parallel = graph(2, 0, 1, 0, 1, 1, 0,
                                 0, 0, 1, 1);
        Graph disconnected = graph(4, 0, 1, 2, 3);
        System.out.println("Triangle min cut: "
                + repeated(triangle, 120, 453L).size());
        System.out.println("Path min cut: "
                + repeated(path, 120, 453L).size());
        System.out.println("Parallel-edge min cut: "
                + repeated(parallel, 120, 453L).size());
        System.out.println("Disconnected min cut: "
                + repeated(disconnected, 120, 453L).size());
        System.out.println("Empty graph min cut: "
                + repeated(graph(0), 1, 453L).size());
        System.out.println("One-vertex graph min cut: "
                + repeated(graph(1), 1, 453L).size());
        verify();
    }
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac KargerMinimumCut.java
java KargerMinimumCut
~~~

**Stdout chính xác quan sát được:**

~~~text
Triangle min cut: 2
Path min cut: 1
Parallel-edge min cut: 3
Disconnected min cut: 0
Empty graph min cut: 0
One-vertex graph min cut: 0
Exhaustive simple graphs: 1098 PASS
Seeded multigraphs: 1600 PASS
Cut witnesses and boundary checks: PASS
~~~

Dòng triangle=2, path=1, parallel=3, disconnected=0, empty=0 và one-vertex=0 đều khớp phân tích. Mọi dòng PASS được in sau khi chương trình hoàn tất các phép đối chứng, nếu mismatch thì ném AssertionError.

## 20. Kiểm thử 1.098 đồ thị đơn vét cạn

Với một đồ thị đơn vô hướng có n đỉnh gắn nhãn, số cạnh có thể tồn tại là n(n−1)/2. Vì mỗi cạnh có thể hiện diện hoặc vắng mặt, số đồ thị có nhãn là:

~~~text
2^[n(n−1)/2].
~~~

Bộ test duyệt n=2..5:

| n | Số cạnh tiềm năng | Số đồ thị |
| ---: | ---: | ---: |
| 2 | 1 | 2 |
| 3 | 3 | 8 |
| 4 | 6 | 64 |
| 5 | 10 | 1024 |
| **Tổng** | | **1098** |

Với mỗi đồ thị, code dùng `bruteMinCut` để tính min-cut thật, chạy một lượt Karger để xác nhận **không trả thấp hơn optimum**, rồi chạy **160 lượt** để đối chiếu kết quả tốt nhất với oracle. Cả hai lượt được kiểm tra witness hợp lệ.

Các đồ thị được kiểm thử bao gồm connected, disconnected, không có cạnh, có bridge, chu trình và đồ thị đầy đủ. Thực thi cho thấy **1.098/1.098 trường hợp PASS** với seed đã chọn.

## 21. Kiểm thử 1.600 đa đồ thị ngẫu nhiên

Bộ thử với seed `Random(4532026L)` sinh 1.600 đồ thị, mỗi đồ thị gồm:

~~~text
n từ 2 tới 6.
m từ 0 tới 22.

Với mỗi cạnh:
    u = random.nextInt(n).
    v = random.nextInt(n).
~~~

Việc sinh này **cho phép u=v** (self-loop) và **các cạnh trùng lặp** (cạnh song song). Vì vậy nó thử đúng đặc điểm quan trọng nhất của Karger thay vì chỉ dùng đồ thị đơn.

Với mỗi đồ thị, code đối chiếu:

- Oracle chính xác bằng mọi phân hoạch.
- Một lượt Karger cùng chứng cứ hai phía.
- **256 lượt Karger** giữ kết quả min.
- Kiểm tra cut≥oracle của một lượt, và cut tốt nhất bằng oracle với seed kiểm thử.

Kết quả **1.600 đa đồ thị PASS**. Điều đó chứng minh bộ test đã qua với dữ liệu này, không phải bảo đảm mọi run ngẫu nhiên trên đồ thị bất kỳ đều tìm được min-cut.

## 22. Sai lầm phổ biến

1. Chọn đều **cặp đỉnh** thay vì đều **bản sao cạnh còn sống**.
2. Gộp cạnh song song thành một, làm sai cả giá trị cut và phân phối chọn cạnh.
3. Tiếp tục chọn self-loop sau khi co, khiến components không giảm.
4. Không xử lý trường hợp hết cạnh hợp lệ khi đồ thị không liên thông.
5. Quên khởi tạo lại DSU cho lượt chạy tiếp theo.
6. Chỉ giữ giá trị cut mà không giữ hai phía để chứng minh.
7. Đếm số cạnh qua ranh giới trên một adjacency list bị nhân đôi không chủ ý.
8. Dừng trước khi còn hai siêu đỉnh trên đồ thị liên thông.
9. Nhầm chọn cạnh ngẫu nhiên với chọn đỉnh ngẫu nhiên rồi một cạnh kề.
10. Cho rằng một lượt luôn tìm đúng global min-cut.
11. Hiểu cận 2/[n(n−1)] là **xác suất chính xác**, không phải cận dưới.
12. Nhân sai các xác suất có điều kiện khi chứng minh sự sống sót của một min-cut.
13. Không lấy **min** trong kết quả của T lượt.
14. Coi seed cố định là bằng chứng xác suất hoặc tính tất định.
15. Lấy kết quả trung bình của các lượt thay cho min-cut.
16. Không xử lý n=0/1 và các quy ước suy biến.
17. Nhầm global min-cut với min-cut s–t có source/sink.
18. Áp Karger không hướng cho đồ thị có hướng mà thiếu biến thể và chứng minh.
19. Áp trực tiếp cho các trọng số tổng quát mà không sửa phân phối chọn cạnh.
20. Không đếm theo từng bản sao cạnh trong oracle.
21. Chỉ test đồ thị đầy đủ, bỏ bridge, path, disconnected và multi-edge.
22. Báo O(n+m) cho một lượt dù phải quét m cạnh mỗi lần co.
23. Gán độ phức tạp của Karger–Stein cho phiên bản Karger cơ bản.
24. Không kiểm tra hai phía của witness có phủ đủ V.
25. Giữ một cạnh đã co như cạnh sống dù hai đầu cùng DSU root.
26. Không kiểm tra endpoints nằm trong [0,n).
27. Dùng Random cho bảo mật khi ứng dụng có yêu cầu ngẫu nhiên bí mật.

## 23. Trọng số, min-cut có hướng và thuật toán liên quan

Với **trọng số nguyên không âm nhỏ**, một cạnh trọng số w có thể được biểu diễn như w bản sao cạnh. Khi đó giá trị và xác suất co tương ứng với tổng số bản sao. Nhưng w lớn khiến cách nhân bản cạnh rất tốn bộ nhớ; muốn thuật toán hiệu quả cần chọn cạnh **tỷ lệ trọng số** và bảo đảm cận xác suất theo biến thể thích hợp.

Với **cạnh có hướng**, bài toán khác về định nghĩa cạnh bắc qua ranh giới và tính đối xứng. Không dùng nguyên xi thuật toán Karger vô hướng.

Nếu cần giải pháp **tất định** cho global min-cut vô hướng có trọng số không âm, có thể nghiên cứu **Stoer–Wagner**. Nếu cần min-cut giữa hai đỉnh nguồn và đích cố định, dùng **max-flow/min-cut**. Họ **Karger–Stein** dùng co ngẫu nhiên theo đệ quy để cải thiện chi phí/xác suất so với chạy Karger cơ bản nhiều lượt.

Karger là bài học mạnh về **ngẫu nhiên hóa một phía**: mọi kết quả đều có chứng cứ hợp lệ, chỉ có việc có đạt optimum hay không phụ thuộc random.

## 24. Bài tập tự luyện

**Bài 1:** Liệt kê mọi lát cắt của tam giác K3, kiểm tra λ=2.

**Bài 2:** Hai đỉnh có 5 cạnh song song và 3 self-loop. Min-cut bằng mấy? Vì sao không được gộp cạnh song song?

**Bài 3:** Sau khi co (0,1) trong K4, liệt kê 5 cạnh còn sống, tính xác suất cho kết quả 3 hoặc 4 ở lần co kế.

**Bài 4:** Chứng minh reservoir sampling cho kết quả mỗi cạnh có xác suất 1/k sau khi đã duyệt k cạnh hợp lệ.

**Bài 5:** Theo dõi parent/size/components của DSU khi co nhiều cạnh trong đồ thị 5 đỉnh.

**Bài 6:** Chứng minh mỗi union giữ một phân hoạch các đỉnh gốc và vì sao đếm cạnh qua partition luôn cho một cut hợp lệ.

**Bài 7:** Từ bậc tối thiểu k của mọi siêu đỉnh khi chưa chạm một min-cut cố định, suy ra m_r≥rk/2.

**Bài 8:** Rút gọn tích các phân số (r−2)/r từ r=3 tới n để được 2/[n(n−1)].

**Bài 9:** Với xác suất thành công mỗi lượt p, suy ra số lượt đủ để xác suất thất bại không quá δ.

**Bài 10:** Vẽ một đồ thị n=4 gồm hai cạnh (0,1),(2,3), giải thích min-cut=0 và điều kiện thoát vòng co.

**Bài 11:** Cài oracle duyệt 2^(n−1)−1 phân hoạch bằng cách cố định đỉnh 0 ở phía A.

**Bài 12:** Sinh tất cả đồ thị đơn có nhãn n=2..5 rồi so best của nhiều lượt Karger với oracle exact.

**Bài 13:** Sinh đa đồ thị cho phép loop và bản sao cạnh, xác minh bội số cạnh qua partition.

**Bài 14:** Đo số lần DSU.find khi n,m tăng để thấy chi phí bản cài chọn cạnh bằng quét toàn bộ m.

**Bài 15:** So kết quả và thời gian của Karger, brute-force và một thuật toán tất định trên tập đồ thị nhỏ.

## 25. Checklist và kết luận

Trước khi dùng Karger, cần chắc rằng bài yêu cầu **global min-cut trên đồ thị vô hướng**; lưu cạnh song song dưới dạng **các bản sao riêng**; loại self-loop khỏi tập cạnh co; chọn **đều cạnh còn sống**; khởi tạo lại DSU ở từng lượt; dừng ở hai siêu đỉnh hoặc xử lý không còn cạnh hợp lệ; lưu hai phía và **đếm lại số cạnh cắt**. Với đồ thị không liên thông, giá trị 0 được phát hiện; với n=0/1 cần có quy ước.

Một lượt Karger cho một lát cắt hợp lệ và không bao giờ dưới optimum, nhưng có thể quá lớn. Trên đồ thị liên thông n≥2, xác suất bảo toàn một min-cut cố định ít nhất **2/[n(n−1)]**, nên lặp T lượt và giữ min làm xác suất thất bại giảm theo **(1−p)^T**. Bản cài DSU quét toàn bộ cạnh có thời gian **O(nm·α(n)) mỗi lượt**, không phải cận của các biến thể tối ưu hơn.

**Kết luận:** Thuật toán Karger kết hợp ba ý tưởng quan trọng: **bất biến phân hoạch tất định**, **lấy mẫu ngẫu nhiên đều trên từng bản sao cạnh**, và **phân tích xác suất có điều kiện**. Việc kiểm chứng bằng oracle exact trên đồ thị nhỏ, thêm cả self-loop, cạnh song song và disconnected, giúp biến một mô tả ngắn gọn thành chương trình Java có thể tin cậy và phân tích được.
