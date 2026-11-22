# Phủ đỉnh bằng các đầu mút của một ghép cặp cực đại

Bài toán **phủ đỉnh nhỏ nhất (Minimum Vertex Cover)** trên đồ thị vô hướng yêu cầu chọn ít đỉnh nhất sao cho **mỗi cạnh có ít nhất một đầu mút được chọn**. Trên đồ thị tổng quát, tìm nghiệm tối ưu là bài toán NP-khó; nhưng có một thuật toán **xấp xỉ hệ số 2** đơn giản, nhanh, có chứng minh: xây **một ghép cặp cực đại (maximal matching)**, rồi lấy **tất cả đầu mút của những cạnh trong ghép cặp** làm tập phủ đỉnh.

Bài **“Phủ đỉnh bằng các đầu mút của một ghép cặp cực đại”** thuộc nhóm **Xấp xỉ và kinh nghiệm** của Computer Science Algorithms. Điểm cần phân biệt thật rõ là **ghép cặp cực đại (maximal)** *không đồng nghĩa* với **ghép cặp lớn nhất (maximum)**. Một phép quét cạnh tham lam O(n+m) đủ tạo maximal matching, và điều kiện cực đại chính là điều kiện bảo đảm rằng tập đầu mút phủ hết mọi cạnh. Chứng minh hệ số xấp xỉ dựa trên việc mọi cạnh của matching đôi một không chung đỉnh: một phủ đỉnh bất kỳ phải lấy ít nhất một đỉnh từ **mỗi** cạnh thuộc matching.

Bài giải thích khái niệm, thuật toán, bất biến, chứng minh đúng và hệ số 2, phản ví dụ đạt chặn trên, độ phức tạp, khác biệt với nghiệm exact và các giới hạn quan trọng. Cuối bài là chương trình **Java 17+ chạy độc lập**, kiểm chứng bằng **oracle vét cạn** trên 1.100 đồ thị đơn có nhãn, 3.000 đồ thị ngẫu nhiên cho phép cạnh song song và một đường đi 20.000 đỉnh. Bài dùng **đồ thị vô hướng không trọng số, không self-loop**; các cạnh song song hợp lệ và không thay đổi yêu cầu phủ đỉnh.

## 1. Phát biểu bài toán phủ đỉnh

Cho đồ thị vô hướng G=(V,E), n=|V|, m=|E|. **Tập phủ đỉnh (vertex cover)** là một tập C⊆V thỏa:

~~~text
Với mọi cạnh e=(u,v) thuộc E:
    u thuộc C hoặc v thuộc C.
~~~

Bài toán tối ưu:

~~~text
OPT(G) = min |C|
         trên mọi C là một phủ đỉnh hợp lệ.
~~~

Ví dụ một cạnh (0,1) có hai cách phủ tối ưu: chọn {0} hoặc chọn {1}, đều có kích thước 1. Nếu chọn cả {0,1}, đó vẫn là phủ đỉnh hợp lệ nhưng **không tối ưu**.

**Không cần chọn cả hai đầu của mọi cạnh**. Phủ đỉnh chỉ đòi **ít nhất một** đầu mút từ mỗi cạnh. Bài toán vì vậy khác việc chọn tất cả các đỉnh có bậc dương; tập ấy đương nhiên phủ mọi cạnh nhưng có thể lớn hơn nghiệm tốt rất nhiều.

Với E rỗng, tập rỗng là phủ đỉnh hợp lệ, OPT=0. Đỉnh cô lập (bậc 0) không cần nằm trong một phủ đỉnh tối ưu.

## 2. Phủ đỉnh, ghép cặp và tập độc lập

Ba khái niệm thường xuất hiện cùng nhau:

- **Vertex cover C:** mỗi cạnh có ít nhất một đầu trong C.
- **Matching M:** một tập các cạnh **đôi một không dùng chung đỉnh**.
- **Independent set I:** không có cạnh nào có cả hai đầu thuộc I.

Một tập C là phủ đỉnh **khi và chỉ khi** V\C là một tập độc lập. Nếu tồn tại cạnh (u,v) với cả u,v nằm ngoài C, cạnh đó không được phủ; ngược lại nếu V\C độc lập thì mỗi cạnh phải có đầu trong C.

Do đó:

~~~text
minimum vertex cover size
  = n - maximum independent set size.
~~~

Đây là liên hệ bài toán tối ưu, không phải cách tính hiệu quả trên đồ thị tổng quát: maximum independent set cũng khó trên trường hợp chung.

Matching lại cung cấp **cận dưới dễ tính** cho vertex cover, vì các cạnh matching không chung đầu mút. Đây là quan hệ được thuật toán xấp xỉ tận dụng.

## 3. Ghép cặp (matching) là gì?

Một matching M⊆E là tập cạnh sao cho **không có hai cạnh nào trong M chung một đỉnh**.

Ví dụ trên đường đi 0–1–2–3:

~~~text
E = {(0,1),(1,2),(2,3)}.

M1 = {(0,1),(2,3)}
là matching có 2 cạnh.

M2 = {(1,2)}
là matching có 1 cạnh.
~~~

Không thể cho cả (0,1) và (1,2) vào matching vì chúng chung đỉnh 1.

Matching khác vertex cover: matching chọn **cạnh** đôi một rời đầu mút, còn vertex cover chọn **đỉnh** sao cho mọi cạnh được phủ. Việc dùng matching tạo phủ đỉnh là một **phép dựng lời giải** từ một cấu trúc dễ tính, không phải hai định nghĩa đồng nhất.

## 4. Ghép cặp cực đại khác ghép cặp lớn nhất

**Maximal matching** nghĩa là matching không thể thêm **một cạnh nào khác** mà vẫn giữ tính không chung đỉnh. Đây là tối ưu theo quan hệ **bao hàm**: không thể mở rộng matching hiện tại bằng cách thêm cạnh đơn lẻ.

**Maximum matching** nghĩa là matching có **số cạnh lớn nhất** trong tất cả matching của đồ thị. Đây là tối ưu theo **kích thước**.

Mọi maximum matching đều maximal. Nhưng chiều ngược lại **không đúng**.

Phản ví dụ trên đường đi 0–1–2–3 khi duyệt cạnh theo thứ tự:

~~~text
(1,2), (0,1), (2,3).
~~~

Chọn trước (1,2). Hai cạnh còn lại đều chạm một đầu đã dùng, nên không thêm được; M={(1,2)} là **maximal** có một cạnh. Nhưng M'={(0,1),(2,3)} có **hai cạnh**, lớn hơn. Do đó M không phải maximum.

Thuật toán trong bài **chỉ cần maximal matching**, vì tính phủ đỉnh và hệ số 2 không đòi giải maximum matching. Đổi từ “cực đại” sang “lớn nhất” một cách vô tình có thể khiến người học tưởng phải dùng thuật toán matching phức tạp trước khi có lời giải xấp xỉ.

## 5. Thuật toán xấp xỉ hệ số 2 từ đầu mút matching

Ý tưởng:

~~~text
ApproxVertexCover(G):
    matched[v] = false cho mọi v.
    M = []

    duyệt mỗi cạnh (u,v) đúng một lần:
        nếu matched[u] == false
           và matched[v] == false:
            thêm (u,v) vào M
            matched[u] = true
            matched[v] = true

    C = {v thuộc V : matched[v] == true}
    trả C cùng matching M.
~~~

Chỉ một lượt duyệt cạnh là đủ. Khi gặp một cạnh có hai đầu chưa được matching dùng, ta **chọn ngay**. Nếu cạnh có ít nhất một đầu đã dùng, không thể đưa nó vào matching vì sẽ chung đỉnh.

Đối với một cạnh được chọn, **cả hai đầu** của nó được đánh dấu và cuối cùng đều thuộc C. Chính cách dựng này khiến |C|=2|M| trong đồ thị không có self-loop.

Thuật toán không chọn đỉnh theo bậc lớn nhất, không tìm đường tăng matching, không cần BFS/DFS, không cần giải integer programming. Đây là một thuật toán **tham lam, xấp xỉ, tất định theo thứ tự cạnh**, rất phù hợp làm baseline.

## 6. Bất biến của vòng duyệt cạnh

Sau khi xử lý t cạnh đầu tiên:

1. M luôn là matching: mỗi đỉnh thuộc **nhiều nhất một cạnh M**.
2. `matched[v]` đúng khi và chỉ khi v là một đầu mút của cạnh thuộc M.
3. Mọi cạnh đã xét đều có **ít nhất một đầu mút được đánh dấu**.

Chứng minh quy nạp:

- Ban đầu M rỗng, mọi matched=false, chưa có cạnh được xét nên cả ba mệnh đề đúng.
- Khi gặp (u,v) với cả hai chưa đánh dấu, thêm cạnh và đánh dấu hai đầu; do đó không có cạnh cũ trong M dùng u hoặc v, giữ matching hợp lệ. Cạnh mới có cả hai đầu được đánh dấu.
- Nếu đã có ít nhất một đầu được đánh dấu, bỏ qua cạnh nhưng cạnh này vẫn được phủ bởi một đầu đã đánh dấu. Các trạng thái khác không đổi.

Khi duyệt xong mọi cạnh, bất biến thứ ba nói rằng **mọi cạnh được phủ**. Vì thuật toán không bao giờ bỏ đánh dấu, một cạnh đã phủ sẽ không trở thành chưa phủ.

## 7. Chứng minh matching thu được là maximal

Giả sử sau khi kết thúc vẫn tồn tại cạnh e=(u,v) có thể thêm vào M mà matching vẫn hợp lệ.

Khi đó **cả u và v đều chưa thuộc đầu mút của cạnh nào trong M**, nghĩa là `matched[u]=matched[v]=false` ở thời điểm kết thúc. Vì biến matched chỉ chuyển từ false sang true, cả hai đầu cũng chưa đánh dấu khi e được duyệt.

Theo quy tắc thuật toán, e **phải được thêm** vào M khi duyệt. Mâu thuẫn.

Vì thế **không còn cạnh nào có hai đầu chưa được matched**, và M là **maximal matching**.

Đây là một điều kiện tương đương rất hữu ích:

~~~text
Matching M maximal
  ⇔ không có cạnh (u,v) nào
     mà cả u và v đều chưa được M ghép.
~~~

Điều kiện này kiểm tra được chỉ bằng cách quét lại các cạnh, không cần thuật toán maximum matching.

## 8. Chứng minh tập hai đầu mút là vertex cover

Đặt:

~~~text
C = { tất cả đầu mút của các cạnh trong M }.
~~~

Giả sử có cạnh (u,v) **không được phủ**. Khi đó u∉C và v∉C, tức cả u,v không được ghép bởi M.

Ta có thể thêm (u,v) vào M mà vẫn giữ matching, vì nó không chung đỉnh với bất kỳ cạnh đã chọn nào. Điều này **mâu thuẫn với tính maximal** của M.

Vậy mọi cạnh có ít nhất một đầu trong C; C là phủ đỉnh hợp lệ.

Điểm quan trọng là tính chất **maximal**, không phải maximum. Nếu lấy đầu mút của một matching **bất kỳ chưa maximal**, có thể tồn tại cạnh nối hai đỉnh chưa được ghép và tập đầu mút sẽ **không phủ** cạnh ấy.

Ví dụ E={(0,1),(2,3)}, M={(0,1)}. Hai đầu mút {0,1} không phủ cạnh (2,3); vì M chưa maximal nên thuật toán chưa được phép dừng ở đó.

## 9. Cận dưới OPT từ một matching

Gọi M gồm k cạnh:

~~~text
M = {e1,e2,...,ek}.
~~~

Vì M là matching, các cạnh ei **đôi một không có đỉnh chung**. Bất kỳ vertex cover hợp lệ C* nào phải chọn ít nhất một đầu mút từ mỗi ei.

Do không thể dùng một đỉnh duy nhất để phủ hai cạnh khác nhau của M (vì các cạnh không chung đỉnh), số đỉnh trong C* ít nhất bằng k:

~~~text
|C*| >= k = |M|.
~~~

Đặc biệt với C* tối ưu:

~~~text
OPT(G) >= |M|.
~~~

Cận dưới này đúng cho **bất kỳ matching** nào, dù maximal hay chưa maximal. Ta không cần biết OPT thực tế để nhận chứng cứ rằng lời giải tốt nhất không thể nhỏ hơn số cạnh M đã chọn.

## 10. Chứng minh hệ số xấp xỉ 2

Matching M có k cạnh đôi một rời đầu mút. Mỗi cạnh đóng góp **đúng hai đỉnh khác nhau** vào C, nên:

~~~text
|C| = 2|M|.
~~~

Từ cận dưới matching:

~~~text
|M| <= OPT(G).
~~~

Suy ra:

~~~text
|C| = 2|M| <= 2*OPT(G).
~~~

Kết hợp với việc C đã được chứng minh là vertex cover hợp lệ, ta có **thuật toán 2-approximation**:

~~~text
OPT(G) <= |C| <= 2*OPT(G).
~~~

Không cần chạy thuật toán tối ưu, không cần ngẫu nhiên hóa và không cần đặc tính đồ thị hai phía. Hai mảnh ghép của chứng minh phải đi cùng nhau:

1. **Maximal matching** ⇒ hai đầu mút phủ mọi cạnh.
2. **Matching (các cạnh không chung đỉnh)** ⇒ mọi cover cần ít nhất |M| đỉnh.

Nếu chỉ có phần (1) thì biết nghiệm hợp lệ nhưng chưa có cận tốt; nếu chỉ có phần (2) thì biết cận dưới nhưng chưa có cách dựng cover.

Với OPT=0 (đồ thị không có cạnh), thuật toán trả C rỗng. Bất đẳng thức vẫn đúng; **tỷ số |C|/OPT** không được tính vì là 0/0, nên phát biểu bằng bất đẳng thức thay vì thương khi xét trường hợp suy biến.

## 11. Ví dụ sắc nét: một cạnh đã đạt tỷ số 2

Đồ thị:

~~~text
V={0,1}.
E={(0,1)}.
~~~

Matching tham lam chọn ngay cạnh (0,1). Tập đầu mút:

~~~text
M={(0,1)}.
C={0,1}.
|C|=2.
~~~

Nhưng chỉ cần chọn một đầu mút, chẳng hạn {0}, đã phủ cạnh; vì đồ thị có cạnh nên OPT=1.

~~~text
|C|/OPT = 2/1 = 2.
~~~

Vì vậy cận xấp xỉ **2 là chặt** đối với quy tắc luôn lấy **cả hai đầu của mọi cạnh matching**: không thể chứng minh một hằng số nhỏ hơn 2 cho mọi input của chính thuật toán này.

Điều này **không nói** rằng tất cả thuật toán xấp xỉ vertex cover đều bắt buộc đạt tỷ số 2 trên mọi lớp đồ thị, cũng không có nghĩa việc tìm vertex cover tối ưu luôn bất khả thi với n nhỏ.

## 12. Ví dụ sao: phủ đỉnh chỉ cần tâm

Xét đồ thị sao với tâm 0 và năm lá 1..5:

~~~text
E={(0,1),(0,2),(0,3),(0,4),(0,5)}.
~~~

Nếu đầu vào bắt đầu bằng (0,1), greedy matching chọn cạnh đó, đánh dấu 0 và 1. Các cạnh còn lại đều chạm 0 nên không thể thêm vào matching.

~~~text
M={(0,1)}.
C={0,1}.
|C|=2.
~~~

Nhưng chỉ chọn **tâm {0}** đã phủ tất cả năm cạnh, nên OPT=1. Đây là lần nữa tỷ số 2.

Ví dụ sao minh họa sự khác biệt giữa **bảo đảm xấp xỉ** và **tối ưu hóa theo cấu trúc riêng**: một heuristic chọn đỉnh bậc lớn nhất có thể cho nghiệm 1 ở đây, nhưng không có nghĩa heuristic ấy tự động mang bảo đảm tốt trên mọi đồ thị.

## 13. Ví dụ đường đi sáu đỉnh

Cho đường đi:

~~~text
0--1--2--3--4--5.
~~~

Duyệt cạnh theo thứ tự:

~~~text
(0,1),(1,2),(2,3),(3,4),(4,5).
~~~

Thuật toán chọn:

~~~text
M={(0,1),(2,3),(4,5)}.
~~~

Tất cả sáu đỉnh thuộc các đầu mút matching:

~~~text
C={0,1,2,3,4,5}, |C|=6.
~~~

Nhưng có thể phủ đường đi bằng {1,3,5} với **3 đỉnh**. M cũng có ba cạnh đôi một rời nên không thể có cover ít hơn 3; do đó OPT=3.

Một lần nữa:

~~~text
|C| = 6 = 2*OPT.
~~~

Đây là một phản ví dụ cho suy nghĩ rằng các bước greedy sẽ tự loại những đỉnh không cần thiết. Phương pháp mặc định **lấy cả hai đầu** để đổi lấy chứng minh và tốc độ rất đơn giản, chứ không giải chính xác.

## 14. Ví dụ maximal nhưng không maximum

Xét đường đi bốn đỉnh, nhưng input có thứ tự:

~~~text
(1,2), (0,1), (2,3).
~~~

Khi bắt đầu, greedy chọn (1,2). Hai cạnh tiếp theo đều có một đầu đã ghép, nên bị bỏ:

~~~text
M={(1,2)}, |M|=1.
C={1,2}, |C|=2.
~~~

Có matching lớn hơn:

~~~text
M'={(0,1),(2,3)}, |M'|=2.
~~~

Vì vậy matching greedy là **maximal** nhưng **không maximum**. Tuy nhiên C={1,2} là phủ đỉnh hợp lệ (nó chạm cả ba cạnh) và OPT=2. Lời giải ở ví dụ này tình cờ **tối ưu** dù matching chưa lớn nhất.

Không có hàm ý rằng ghép cặp cực đại nhỏ hơn thì tự động cho phủ đỉnh tốt hơn. Tính tối ưu của cover phụ thuộc cấu trúc graph và thứ tự chọn cạnh, trong khi **bảo đảm 2-approx luôn giữ nguyên**.

## 15. Thứ tự cạnh ảnh hưởng đáp án nhưng không ảnh hưởng bảo đảm

Greedy matching phụ thuộc thứ tự cạnh. Chọn một cạnh sớm có thể khóa nhiều cạnh khác; chọn theo thứ tự khác có thể tạo matching với số cạnh khác, dẫn tới cover có số đỉnh khác.

Ví dụ với đường đi 0–1–2–3:

- Duyệt (1,2) trước: matching một cạnh, cover hai đỉnh.
- Duyệt (0,1), (2,3) trước: matching hai cạnh, cover bốn đỉnh.

**Cả hai đều maximal**, và cả hai cover đều hợp lệ, đáp ứng |C|≤2 OPT. Thuật toán không yêu cầu độ dài matching lớn nhất; nhiều cạnh matching hơn có thể làm tập đầu mút **lớn hơn** chứ không tự tốt hơn đối với phương pháp này.

Nếu muốn kết quả xác định, giữ nguyên thứ tự cạnh trong đầu vào và cùng quy tắc chọn. Nếu muốn thử nghiệm heuristic, có thể thay đổi thứ tự cạnh hoặc bỏ các đỉnh dư thừa sau đó, nhưng phải tách rõ **thuật toán gốc có bảo đảm** với các bước cải tiến không nằm trong phép dựng chuẩn.

## 16. Đồ thị có cạnh song song và đỉnh cô lập

Trong một **đa đồ thị vô hướng không self-loop**, các bản sao cạnh (u,v) và (v,u) đều đòi hỏi ít nhất một trong hai đỉnh u,v được chọn; ràng buộc phủ đỉnh về mặt tập hợp là như nhau.

Vì vậy:

- **Nhiều bản sao** giữa cùng hai đỉnh không làm thay đổi việc cặp đỉnh đó được phủ hay chưa.
- Greedy chọn bản sao đầu tiên nếu hai đầu còn tự do; bản sao sau đó không thể vào matching vì hai đầu đã đánh dấu.
- Cận |M|≤OPT và 2-approx vẫn đúng, vì matching không thể dùng chung đầu mút.
- **Đỉnh cô lập** không xuất hiện ở bất kỳ cạnh nào; greedy không đánh dấu và không thêm đỉnh đó vào cover.

Ví dụ E={(0,1),(0,1),(1,0)} trên n=3 có matching một cạnh và cover {0,1}; đỉnh 2 cô lập không được chọn. OPT=1, nên tỷ số 2.

**Self-loop là ngoại lệ:** với cạnh (v,v), một vertex cover phải chứa v. Khái niệm matching chuẩn trong bài yêu cầu mỗi cạnh có **hai đầu khác nhau**, và công thức |C|=2|M| không thể dùng nguyên xi với loop. Để giữ hợp đồng rõ ràng, chương trình **từ chối self-loop** bằng IllegalArgumentException thay vì xử lý âm thầm.

## 17. Vì sao không áp dụng trực tiếp cho vertex cover có trọng số?

Bài xét **mỗi đỉnh có chi phí 1**. Nếu mỗi đỉnh v có trọng số dương w(v), mục tiêu trở thành:

~~~text
min tổng w(v) trên các đỉnh được chọn,
sao cho mọi cạnh đều được phủ.
~~~

Lấy cả hai đầu mút của maximal matching **không tự bảo đảm hệ số 2 theo tổng trọng số**.

Phản ví dụ đồ thị sao:

~~~text
Tâm 0 có trọng số w(0)=1.
Mỗi lá i có trọng số w(i)=W, W rất lớn.

Matching greedy chọn (0,1).
Phủ đỉnh hai đầu = {0,1}, chi phí 1+W.

Nghiệm tối ưu chỉ chọn {0}, chi phí 1.
~~~

Tỷ số **1+W** có thể lớn tùy ý, nên không có bảo đảm 2 theo trọng số cho quy tắc đơn giản trên.

Để xấp xỉ **weighted vertex cover**, cần thuật toán khác với chứng minh phù hợp, ví dụ dựa trên **LP relaxation/dual** hoặc **primal-dual**. Không chuyển nguyên xi |C|=2|M| từ số đỉnh sang tổng chi phí.

## 18. Quan hệ với đồ thị hai phía và định lý Kőnig

Với đồ thị **hai phía (bipartite)**, có định lý Kőnig:

~~~text
Kích thước minimum vertex cover
  = kích thước maximum matching.
~~~

Điều này cho phép giải minimum vertex cover **chính xác** trong thời gian đa thức trên đồ thị hai phía bằng cách tìm **maximum matching** rồi dựng cover thích hợp.

Tuy nhiên **lấy tất cả đầu mút của một maximum matching** vẫn thường tạo 2|M| đỉnh, không phải cover tối ưu |M| đỉnh. Cần một bước dựng tập phủ từ cấu trúc đường đi xen kẽ/đỉnh reachable theo matching, không phải chỉ lấy mọi đầu.

Thuật toán trong bài không tận dụng tính hai phía, nên dùng được cho đồ thị tổng quát với bảo đảm 2-approx. Khi đề xác nhận đồ thị hai phía và yêu cầu đúng tối ưu, cách tiếp cận qua matching lớn nhất và Kőnig có thể thích hợp hơn.

## 19. Độ phức tạp của greedy matching và vertex cover

Với đồ thị n đỉnh, m cạnh đã có trong bộ nhớ:

- Tạo mảng `matched[n]`: O(n) thời gian/bộ nhớ.
- Duyệt mỗi cạnh một lần: O(m) thời gian; mỗi lần chỉ tra hai phần tử boolean và có thể thêm một cạnh vào list.
- Quét matched để xuất cover tăng dần theo nhãn: O(n).
- Danh sách matching có tối đa floor(n/2) cạnh.

Vì vậy:

~~~text
Time: O(n+m).
Extra space: O(n+|M|), ngoài danh sách cạnh input.
Số cạnh matching: |M| <= floor(n/2).
Kích thước cover: |C|=2|M| <= n.
~~~

Không cần sắp xếp cạnh, tìm maximum matching, DSU hay duyệt mọi tập con. Đây là lý do thuật toán rất nhanh ngay cả với số đỉnh/cạnh lớn.

Nếu đồ thị được đọc qua stream, vẫn cần lưu matched và (nếu phải trả chứng cứ) các cạnh matching; không nhất thiết phải lưu toàn bộ E để tạo nghiệm. Tuy nhiên chương trình demo nhận `Graph` chứa `List<Edge>` bất biến để tiện kiểm thử.

## 20. Vét cạn nghiệm tối ưu chỉ để kiểm thử

Đối với n nhỏ, có thể tìm minimum vertex cover chính xác bằng **liệt kê mọi tập con của V**. Với mỗi bitmask từ 0 tới 2^n−1:

1. Giải mã mask thành tập đỉnh C.
2. Kiểm tra mọi cạnh (u,v) có u hoặc v thuộc C.
3. Nếu hợp lệ và |C| nhỏ hơn best, cập nhật.

~~~text
ExactMinCover(G):
    best=n+1.
    for mỗi mask trong [0,2^n):
        nếu popcount(mask) >= best:
            bỏ qua.
        nếu mọi cạnh có ít nhất một đầu trong mask:
            best = popcount(mask).
    return best.
~~~

Giải thuật này không hiệu quả cho n lớn vì có tới 2^n tập con. Nhưng nó **không dùng greedy matching**, nên rất phù hợp làm **oracle độc lập** khi kiểm thử các đồ thị nhỏ.

Với n=0, mask duy nhất bằng 0 và tập rỗng là cover; oracle trả 0. Trong demo `exactMinimumCover` cho n≤15 để tránh thời gian tăng theo hàm mũ.

## 21. Mã Java 17+ hoàn chỉnh

Lưu chương trình sau dưới tên **MaximalMatchingVertexCover.java**. Đây là mã tự chứa, dùng Java record và các lớp trong java.util, không cần thư viện ngoài.

Các API chính:

- `Edge(u,v)`: mô tả cạnh vô hướng bằng hai đầu mút; mỗi phần tử List là một bản sao cạnh.
- `Graph(vertices,edges)`: kiểm tra số đỉnh, nhãn đầu mút và **từ chối self-loop**; sao chép danh sách cạnh bất biến.
- `Solution(matching,cover)`: chứng cứ gồm các cạnh matching được chọn và tập đỉnh cover đã sắp tăng.
- `approximate`: **phần thuật toán xấp xỉ chính**; một lần quét cạnh, không dùng oracle.
- `exactMinimumCover`: liệt kê mọi mask với n≤15 để so nghiệm.
- `assertCertificate`: xác nhận matching hợp lệ, matching maximal, cover đúng các đầu mút, không bỏ cạnh nào và |C|=2|M|.
- `check`: xác nhận |M|≤OPT≤|C|≤2 OPT.
- `verify`: sinh đồ thị đơn vét cạn, các đa đồ thị có seed, thử đồ thị lớn và đầu vào lỗi.

Cách xác định kết quả: greedy duyệt cạnh theo **đúng thứ tự đã có trong `Graph.edges()`**; đầu ra cover được xây bằng vòng lặp v=0..n−1 nên có thứ tự tăng. Matching là danh sách các cạnh đã chọn theo thứ tự xuất hiện.

~~~java
import java.util.*;

public final class MaximalMatchingVertexCover {
    private MaximalMatchingVertexCover() {}

    public record Edge(int u, int v) {}

    public record Graph(int vertices, List<Edge> edges) {
        public Graph {
            if (vertices < 0 || edges == null) {
                throw new IllegalArgumentException("invalid graph");
            }
            for (Edge e : edges) {
                if (e == null || e.u() < 0 || e.v() < 0
                        || e.u() >= vertices || e.v() >= vertices
                        || e.u() == e.v()) {
                    throw new IllegalArgumentException(
                            "invalid endpoint or self-loop");
                }
            }
            edges = List.copyOf(edges);
        }
    }

    public record Solution(List<Edge> matching, List<Integer> cover) {
        public Solution {
            matching = List.copyOf(matching);
            cover = List.copyOf(cover);
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

    public static Solution approximate(Graph graph) {
        if (graph == null) {
            throw new IllegalArgumentException("null graph");
        }
        boolean[] matched = new boolean[graph.vertices()];
        List<Edge> matching = new ArrayList<>();
        for (Edge e : graph.edges()) {
            int u = e.u(), v = e.v();
            if (!matched[u] && !matched[v]) {
                matched[u] = true;
                matched[v] = true;
                matching.add(e);
            }
        }
        List<Integer> cover = new ArrayList<>();
        for (int v = 0; v < matched.length; v++) {
            if (matched[v]) cover.add(v);
        }
        return new Solution(matching, cover);
    }

    public static int exactMinimumCover(Graph graph) {
        if (graph == null || graph.vertices() > 15) {
            throw new IllegalArgumentException(
                    "exact oracle supports at most 15 vertices");
        }
        int n = graph.vertices();
        int best = n + 1;
        int limit = 1 << n;
        for (int mask = 0; mask < limit; mask++) {
            int count = Integer.bitCount(mask);
            if (count >= best) continue;
            boolean allCovered = true;
            for (Edge e : graph.edges()) {
                boolean hasU = ((mask >>> e.u()) & 1) == 1;
                boolean hasV = ((mask >>> e.v()) & 1) == 1;
                if (!hasU && !hasV) {
                    allCovered = false;
                    break;
                }
            }
            if (allCovered) best = count;
        }
        if (best == n + 1) {
            throw new AssertionError("every graph has a vertex cover");
        }
        return best;
    }

    private static void assertCertificate(Graph graph, Solution solution) {
        int n = graph.vertices();
        boolean[] isMatched = new boolean[n];
        for (Edge e : solution.matching()) {
            if (!graph.edges().contains(e)
                    || isMatched[e.u()] || isMatched[e.v()]) {
                throw new AssertionError("not a matching in the graph");
            }
            isMatched[e.u()] = true;
            isMatched[e.v()] = true;
        }

        boolean[] inCover = new boolean[n];
        int last = -1;
        for (int v : solution.cover()) {
            if (v <= last || v < 0 || v >= n) {
                throw new AssertionError("invalid/unsorted/duplicate cover");
            }
            inCover[v] = true;
            last = v;
        }

        for (int i = 0; i < n; i++) {
            if (inCover[i] != isMatched[i]) {
                throw new AssertionError("cover differs from matching endpoints");
            }
        }
        for (Edge e : graph.edges()) {
            if (!inCover[e.u()] && !inCover[e.v()]) {
                throw new AssertionError("edge not covered");
            }
            if (!isMatched[e.u()] && !isMatched[e.v()]) {
                throw new AssertionError("matching not inclusion-maximal");
            }
        }
        if (solution.cover().size() != 2 * solution.matching().size()) {
            throw new AssertionError("wrong endpoint count");
        }
    }

    private static void check(Graph graph) {
        Solution solution = approximate(graph);
        assertCertificate(graph, solution);
        int optimum = exactMinimumCover(graph);
        if (solution.matching().size() > optimum
                || solution.cover().size() > 2 * optimum
                || solution.cover().size() < optimum) {
            throw new AssertionError("2-approx inequality failed: graph="
                    + graph + " cover=" + solution.cover()
                    + " optimum=" + optimum);
        }
    }

    private static void expectInvalid(Runnable operation) {
        try {
            operation.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("invalid input accepted");
    }

    public static void verify() {
        int exhaustive = 0;
        for (int n = 0; n <= 5; n++) {
            List<Edge> potential = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                for (int v = u + 1; v < n; v++) {
                    potential.add(new Edge(u, v));
                }
            }
            for (int mask = 0; mask < (1 << potential.size()); mask++) {
                List<Edge> edges = new ArrayList<>();
                for (int i = 0; i < potential.size(); i++) {
                    if ((mask & (1 << i)) != 0) {
                        edges.add(potential.get(i));
                    }
                }
                check(new Graph(n, edges));
                exhaustive++;
            }
        }

        Random rng = new Random(4722026L);
        int randomized = 0;
        for (int trial = 0; trial < 3000; trial++) {
            int n = rng.nextInt(11);
            int m = n < 2 ? 0 : rng.nextInt(31);
            List<Edge> edges = new ArrayList<>();
            for (int i = 0; i < m; i++) {
                int u = rng.nextInt(n);
                int v = rng.nextInt(n - 1);
                if (v >= u) v++;
                edges.add(new Edge(u, v));
                if (trial % 13 == 0 && i % 7 == 0) {
                    edges.add(new Edge(v, u));
                }
            }
            check(new Graph(n, edges));
            randomized++;
        }

        Graph singleEdge = graph(2, 0, 1);
        Graph star = graph(6, 0, 1, 0, 2, 0, 3, 0, 4, 0, 5);
        Graph pathSix = graph(6, 0, 1, 1, 2, 2, 3,
                                3, 4, 4, 5);
        Graph notMaximum = graph(4, 1, 2, 0, 1, 2, 3);
        check(singleEdge);
        check(star);
        check(pathSix);
        check(notMaximum);
        check(graph(0));
        check(graph(1));
        check(graph(4));
        check(graph(3, 0, 1, 0, 1, 1, 0));
        if (approximate(star).cover().size() != 2
                || exactMinimumCover(star) != 1
                || approximate(pathSix).cover().size() != 6
                || exactMinimumCover(pathSix) != 3
                || approximate(notMaximum).matching().size() != 1
                || exactMinimumCover(notMaximum) != 2) {
            throw new AssertionError("examples inconsistent");
        }

        List<Edge> largeEdges = new ArrayList<>();
        for (int i = 0; i < 19999; i++) {
            largeEdges.add(new Edge(i, i + 1));
        }
        Graph large = new Graph(20000, largeEdges);
        Solution largeSolution = approximate(large);
        assertCertificate(large, largeSolution);
        if (largeSolution.matching().size() != 10000
                || largeSolution.cover().size() != 20000) {
            throw new AssertionError("large path size mismatch");
        }

        expectInvalid(() -> approximate(null));
        expectInvalid(() -> graph(-1));
        expectInvalid(() -> graph(2, 0, 2));
        expectInvalid(() -> graph(3, 1, 1));
        expectInvalid(() -> graph(2, 0));
        expectInvalid(() -> new Graph(2, null));
        expectInvalid(() -> new Graph(2, Arrays.asList((Edge) null)));
        expectInvalid(() -> exactMinimumCover(graph(16)));

        System.out.println("Exhaustive simple graphs: "
                + exhaustive + " PASS");
        System.out.println("Seeded graphs with parallel/reversed edges: "
                + randomized + " PASS");
        System.out.println("Large path n=20000: matching=10000 cover=20000 PASS");
        System.out.println("Certificates, bounds and invalid inputs: PASS");
    }

    public static void main(String[] args) {
        Graph singleEdge = graph(2, 0, 1);
        Graph star = graph(6, 0, 1, 0, 2, 0, 3, 0, 4, 0, 5);
        Graph pathSix = graph(6, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5);
        Graph notMaximum = graph(4, 1, 2, 0, 1, 2, 3);
        System.out.println("Single edge: cover="
                + approximate(singleEdge).cover()
                + " optimum=" + exactMinimumCover(singleEdge));
        System.out.println("Star: cover=" + approximate(star).cover()
                + " optimum=" + exactMinimumCover(star));
        System.out.println("Path six: cover=" + approximate(pathSix).cover()
                + " optimum=" + exactMinimumCover(pathSix));
        System.out.println("Maximal not maximum: matching size="
                + approximate(notMaximum).matching().size()
                + " (another matching has size 2)");
        System.out.println("Empty graph: cover="
                + approximate(graph(0)).cover());
        verify();
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac MaximalMatchingVertexCover.java
java MaximalMatchingVertexCover
~~~

**Stdout chính xác quan sát được khi chạy:**

~~~text
Single edge: cover=[0, 1] optimum=1
Star: cover=[0, 1] optimum=1
Path six: cover=[0, 1, 2, 3, 4, 5] optimum=3
Maximal not maximum: matching size=1 (another matching has size 2)
Empty graph: cover=[]
Exhaustive simple graphs: 1100 PASS
Seeded graphs with parallel/reversed edges: 3000 PASS
Large path n=20000: matching=10000 cover=20000 PASS
Certificates, bounds and invalid inputs: PASS
~~~

Kết quả cho thấy ví dụ một cạnh, sao và đường đi sáu đỉnh đạt đúng tỷ số 2; ví dụ 4 đỉnh minh họa maximal không maximum; các nhóm PASS được in sau khi các phép kiểm tra hoàn thành.

## 22. Kiểm thử vét cạn 1.100 đồ thị đơn

Đồ thị đơn vô hướng không loop với n đỉnh gắn nhãn có n(n−1)/2 cạnh tiềm năng. Mỗi cạnh có hai trạng thái có/không, nên số đồ thị có nhãn là:

~~~text
2^[n(n−1)/2].
~~~

Chương trình thử **mọi** đồ thị với n từ 0 tới 5:

| n | Cạnh tiềm năng | Số đồ thị |
| ---: | ---: | ---: |
| 0 | 0 | 1 |
| 1 | 0 | 1 |
| 2 | 1 | 2 |
| 3 | 3 | 8 |
| 4 | 6 | 64 |
| 5 | 10 | 1024 |
| **Tổng** | | **1100** |

Với mỗi đồ thị, `check` tính nghiệm xấp xỉ, xác nhận chứng cứ matching và cover, rồi dùng oracle duyệt mọi tập đỉnh để tìm OPT thật. Bộ thử kiểm tra độc lập:

~~~text
M đúng là matching trong E.
M là inclusion-maximal.
C đúng là tập đầu mút của M.
Mỗi cạnh của G đều được phủ.
|M| <= OPT <= |C| <= 2*OPT.
~~~

Kết quả chương trình đã chạy: **1.100 đồ thị PASS**.

## 23. Kiểm thử 3.000 đồ thị ngẫu nhiên có cạnh song song

Bộ test dùng **Random(4722026L)** để tạo 3.000 đồ thị. Mỗi đồ thị chọn n ngẫu nhiên từ **0..10**; nếu n<2, m=0; nếu n≥2, số cạnh ban đầu ngẫu nhiên từ **0..30**.

Mỗi cạnh được sinh bằng hai đỉnh **khác nhau**, nên không có self-loop. Các cặp đầu mút có thể lặp; một số ca được thêm cả cạnh đảo chiều, để xác nhận rằng các bản sao không làm mất tính hợp lệ của thuật toán.

Vì n≤10, oracle 2^n còn đủ nhanh. Với từng đồ thị, bộ thử chạy đầy đủ cùng các kiểm tra:

- Matching không dùng chung đỉnh.
- Không còn cạnh có cả hai đầu chưa được matching dùng (**maximality**).
- Cover là toàn bộ đầu mút matching, theo thứ tự tăng và không trùng.
- Mọi cạnh đều được phủ.
- So độ lớn với OPT exact từ bitmask, bảo đảm 2-approx.

Cả **3.000 trường hợp PASS** trong chương trình đã chạy. Đây là kiểm thử trên seed và miền đã chọn, không phải thay thế cho chứng minh toán học.

## 24. Kiểm thử khả năng mở rộng 20.000 đỉnh

Để kiểm tra rằng phần greedy không dựa vào oracle hàm mũ, chương trình tạo một **đường đi 20.000 đỉnh**:

~~~text
V={0,1,...,19999}.
E={(0,1),(1,2),...,(19998,19999)}.
~~~

Quét cạnh từ trái sang phải chọn:

~~~text
(0,1),(2,3),...,(19998,19999).
~~~

Có **10.000 cạnh matching**, nên cover gồm **20.000 đầu mút**. Dù cover này lớn hơn minimum cover của đường đi, nó vẫn hợp lệ và chạm chặn 2.

Bộ kiểm thử lớn **không chạy oracle vét cạn**: chỉ kiểm tra chứng cứ matching/cover cùng kích thước kỳ vọng. Việc này tránh đưa thuật toán chính tuyến tính vào phụ thuộc không cần thiết vào phần kiểm thử lũy thừa.

## 25. Những lỗi triển khai thường gặp

1. **Nhầm maximal với maximum**, rồi cho rằng phải tìm matching lớn nhất trước khi có cover xấp xỉ.
2. **Dừng khi có matching chưa maximal**, khiến tồn tại cạnh hai đầu chưa được phủ.
3. **Thêm hai cạnh matching chung một đỉnh**, làm sai cận |M|≤OPT.
4. **Đánh dấu chỉ một đầu** của cạnh đã chọn, khiến dữ liệu matched không biểu diễn matching.
5. **Lấy một đầu mút bất kỳ từ mỗi cạnh M** rồi mong phủ hết mọi cạnh, dù chứng minh gốc dùng cả hai đầu.
6. **Lấy tất cả đầu mút của mọi cạnh G** thay vì chỉ cạnh M, gây cover thừa rất lớn.
7. **Cho rằng maximal matching luôn có kích thước maximum** trên đường đi hoặc đồ thị hai phía.
8. **Dùng số đỉnh cover làm số cạnh matching**, quên |C|=2|M| (với cạnh không self-loop).
9. **Dùng tập có trọng số rồi áp bảo đảm 2 của bản không trọng số**, sai do chi phí có thể lệch vô hạn.
10. **Không xử lý đồ thị không có cạnh**, và chia |C|/OPT khi cả hai bằng 0.
11. **Thêm đỉnh cô lập vào cover** dù nó không được matching dùng.
12. **Cho phép self-loop mà không đổi định nghĩa matching và chứng minh**, dẫn đến sai đếm.
13. **Cho rằng nhiều cạnh song song bắt buộc chọn nhiều đỉnh hơn**, dù cùng một đầu đã phủ tất cả bản sao.
14. **Nhầm phủ đỉnh với phủ cạnh (edge cover)**, vốn là bài toán khác.
15. **Nhầm bài phủ đỉnh với dominating set**, không cùng ràng buộc.
16. **Nhầm vertex cover với independent set**, quên quan hệ bổ sung giữa hai tập.
17. **Nói hệ số 2 là sai số cộng 2 đỉnh**, trong khi đây là cận **nhân** |C|≤2 OPT.
18. **Nói lúc nào cũng trả đúng hai lần OPT**, dù nhiều đồ thị/ thứ tự cho tỷ số nhỏ hơn 2.
19. **Bỏ kiểm tra tính hợp lệ của cover khi test**, chỉ so số đỉnh với 2 OPT.
20. **Dùng output của một greedy khác làm oracle**, cả hai có thể cùng sai.
21. **Quên quy tắc thứ tự cạnh**, kết quả thay đổi giữa những lần đọc input khác nhau.
22. **Chọn maximum matching rồi lấy hai đầu và khẳng định tối ưu trên bipartite**, sai nếu không dựng cover theo Kőnig.
23. **Báo độ phức tạp O(2^n) cho greedy**, nhầm nó với oracle exact.
24. **Tìm maximum independent set bằng lấy phần bù của cover xấp xỉ rồi khẳng định tối ưu**, không đúng.
25. **Không đảm bảo nhãn đỉnh thuộc [0,n)**, làm sai mảng matched.
26. **Bỏ qua dữ liệu null trong Graph**, dẫn đến NullPointerException không kiểm soát.
27. **Tự làm xáo trộn cạnh mà không báo seed/thứ tự**, gây khó tái lập các test heuristic.
28. **Đánh giá hiệu năng chỉ trên đồ thị cực ít cạnh**, không thử cả đồ thị đường đi dài/đồ thị dày.
29. **Cho rằng mọi thuật toán approximation đều chỉ là heuristic không bảo đảm**, bỏ qua chứng minh hệ số 2 của phương pháp này.
30. **Cho rằng có xấp xỉ 2 là không cần kiểm tra chứng cứ**, trong khi bug cài đặt vẫn có thể trả cover sai.

## 26. Bài tập tự luyện và mở rộng

**Bài 1 — Định nghĩa:** viết lại vertex cover, matching, maximal matching và maximum matching bằng ký hiệu tập hợp. Tìm ví dụ với M maximal nhưng không maximum.

**Bài 2 — Chạy tay:** trên đường đi 0–1–2–3, chạy greedy theo hai thứ tự cạnh khác nhau và xác định matching, cover, OPT.

**Bài 3 — Chứng minh maximal:** dùng bất biến matched chỉ tăng để chứng minh không thể còn cạnh có cả hai đầu chưa được ghép khi kết thúc.

**Bài 4 — Chứng minh cover:** giả sử có cạnh không được phủ bởi mọi đầu mút matching, suy ra có thể thêm nó vào M và mâu thuẫn với maximality.

**Bài 5 — Cận dưới:** với k cạnh matching đôi một rời, chứng minh mọi cover có ít nhất k đỉnh.

**Bài 6 — Hệ số 2:** kết hợp hai chứng minh để suy ra OPT≤|C|=2|M|≤2 OPT. Giải thích trường hợp OPT=0.

**Bài 7 — Chặn chặt:** với một cạnh đơn lẻ hoặc một đồ thị sao, tính tỷ số của thuật toán và chứng minh không thể cải thiện chặn dưới 2 cho cách luôn lấy hai đầu matching.

**Bài 8 — Đa đồ thị:** thêm nhiều bản sao cạnh (0,1) và (1,0) vào một đồ thị. Nêu lý do OPT và tính phủ không đổi.

**Bài 9 — Trọng số:** đặt w(tâm)=1, w(lá)=1000 trên đồ thị sao. Vì sao đầu mút matching không còn là 2-approx theo trọng số?

**Bài 10 — Hai phía:** trên một đồ thị bipartite nhỏ, tìm maximum matching và minimum vertex cover có cùng kích thước theo Kőnig; so với cover gồm cả hai đầu matching.

**Bài 11 — Oracle:** lập trình duyệt mọi bitmask của n≤15, kiểm tra từng cạnh, tìm OPT nhỏ nhất và so với greedy.

**Bài 12 — Vét cạn:** sinh toàn bộ đồ thị đơn có nhãn n=0..5 và kiểm tra chứng cứ, cận xấp xỉ và đầu vào rỗng.

**Bài 13 — Kiểm tra chứng cứ:** từ Solution(matching,cover), viết checker độc lập xác minh matching, maximality, cover và |C|=2|M| mà không gọi approximate.

**Bài 14 — Stress:** tạo đường đi dài 20.000 đỉnh và đồ thị sao 20.000 đỉnh, đo số cạnh matching và thời gian. Tránh chạy brute-force trên input này.

**Bài 15 — Heuristic cải tiến:** sau khi có C, thử loại một đỉnh v nếu mọi cạnh vẫn được phủ. Chứng minh cover sau loại vẫn hợp lệ, và vì kích thước chỉ giảm nên cận 2-approx không thể xấu đi. Quan sát kết quả phụ thuộc thứ tự loại đỉnh.

**Bài 16 — Ứng dụng:** xác định khi nào một bài thực tế có trọng số đỉnh không đều, khi nào là bipartite và khi nào đồ thị cho phép self-loop. Chỉ chọn lời giải đáp ứng đúng mô hình đã nêu.

## 27. Checklist cuối bài

Trước khi áp dụng thuật toán:

- Bài là **vertex cover không trọng số trên đồ thị vô hướng không self-loop**.
- Matching là một tập cạnh **không chung đỉnh**.
- Dùng **maximal matching**, không cần maximum matching.
- Duyệt mọi cạnh và chọn cạnh khi **cả hai đầu chưa được matched**.
- Chọn **cả hai đầu** của mỗi cạnh matching vào C.
- Kiểm tra cover bằng điều kiện **mọi cạnh có ít nhất một đầu thuộc C**.
- Ghi nhớ cận dưới **|M|≤OPT** và đầu ra **|C|=2|M|**.
- Kết luận **OPT≤|C|≤2 OPT**, kể cả đồ thị rỗng ở dạng bất đẳng thức.
- Không chuyển bảo đảm sang weighted vertex cover bằng cách thay số đỉnh thành tổng trọng số.
- Mã chính có thời gian **O(n+m)**; oracle 2^n chỉ dành cho kiểm thử n nhỏ.
- Đối chiếu cả tính hợp lệ, maximality và hệ số xấp xỉ, không chỉ so kích thước.

**Kết luận:** Lấy các đầu mút của **một ghép cặp cực đại** là một trong những ví dụ rõ nhất về thuật toán xấp xỉ có **bảo đảm chứng minh được**, chứ không chỉ là heuristic. Phần greedy xây matching nhanh, tính maximal bảo đảm tất cả cạnh được phủ, còn tính rời đầu mút cho cận dưới đối với OPT. Cùng ba quan hệ này, bài toán phủ đỉnh NP-khó trên đồ thị tổng quát có một lời giải **2-approximation O(n+m)** rất đơn giản và đáng tin khi dùng đúng mô hình dữ liệu.
