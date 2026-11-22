# Khởi tạo nhiều lần và lựa chọn lời giải tốt nhất

## 1. Vấn đề: một lần chạy heuristic có thể bị mắc kẹt

Trong nhóm **xấp xỉ và kinh nghiệm (approximation and heuristics)**, nhiều thuật toán cải thiện dần một lời giải từ một điểm khởi tạo. Điểm bắt đầu khác nhau có thể dẫn đến **nghiệm cuối khác nhau**, ngay cả khi dùng cùng quy tắc cải thiện.

Ý tưởng **multi-start / random restart**: thay vì tin vào một lần khởi tạo, chạy nhiều lần từ các lời giải ban đầu khác nhau, cải thiện từng lời giải, **đánh giá bằng cùng một hàm mục tiêu**, rồi trả lời giải tốt nhất trong những lời giải đã thấy.

~~~text
best = none

repeat r times:
    x0 = generateFeasibleInitialSolution()
    candidate = improveLocally(x0)

    if best is none OR candidate better than best:
        best = copy(candidate)

return best
~~~

Một ví dụ dễ nhìn: trên đồ thị là **chu trình 6 đỉnh**, thuật toán cải thiện bằng cách đổi phía một đỉnh của bài toán Max-Cut có thể dừng ở một **cực đại cục bộ trọng số 4**, dù cực đại toàn cục là **6**. Một lần khởi tạo khác có thể đưa ta tới nghiệm 6. Chọn lời giải tốt nhất trong nhiều lần chạy giúp giảm rủi ro bị kẹt ở một miền kém.

### Câu hỏi phải xác định trước khi áp dụng

- Bài toán đang **tối đa hóa** hay **tối thiểu hóa**?
- Một lời giải **hợp lệ (feasible)** cần thỏa điều kiện nào?
- Có thể tính **giá trị mục tiêu** của các lời giải trên cùng thang đo không?
- Bước cải thiện chỉ chấp nhận thay đổi **tốt hơn nghiêm ngặt** hay chấp nhận cả bằng nhau?
- Một lần chạy kết thúc theo **cực trị cục bộ**, **ngân sách bước**, hay **giới hạn thời gian**?
- Các điểm bắt đầu có đủ **đa dạng** không? Các lần khởi tạo có thật sự dùng randomness mới?
- Lời giải cuối phải là **tối ưu có chứng minh**, **xấp xỉ có bảo đảm**, hay **nghiệm kinh nghiệm tốt nhất quan sát được**?

Không được gọi một nghiệm là “tối ưu toàn cục” chỉ vì nó tốt nhất trong 100 lần chạy. Từ “best” ở đây nghĩa là **best observed / incumbent**, trừ khi đã có chứng minh độc lập.

## 2. Mô hình toán học của multi-start

Gọi \(\mathcal F\) là tập tất cả lời giải hợp lệ. Với bài **tối đa hóa**, cần:

~~~text
maximize f(x)
subject to x in F
~~~

Với bài **tối thiểu hóa**, cần:

~~~text
minimize f(x)
subject to x in F
~~~

Quy trình gồm hai ánh xạ:

~~~text
Initialize(randomness, input) -> x0 in F

Improve(x0, input) -> x* in F
~~~

`Improve` có thể là hill climbing, local search, greedy improvement, 2-opt, coordinate descent hoặc một thuật toán chuyên biệt; không nhất thiết tối ưu toàn cục. Một lần thử trả cặp `(x*,f(x*))`.

Sau r lần khởi tạo và cải thiện:

~~~text
Maximize: best = argmax_{i=1..r} f(x_i*)
Minimize: best = argmin_{i=1..r} f(x_i*)
~~~

Tất cả `x_i*` phải được kiểm tra trên **cùng một định nghĩa mục tiêu và tính hợp lệ**. Không được so điểm sau khi mỗi lần dùng một hàm chuẩn hóa hoặc một hệ số phạt khác nhau rồi xem số lớn hơn là tốt hơn.

### Hai cấp độ kết quả

1. **Best of initializations:** sinh nhiều x0, không cải thiện, chọn tốt nhất. Có thể hữu ích nhưng thường bỏ lỡ khả năng tìm kiếm cục bộ.
2. **Best of local optima:** với mỗi x0, chạy một thủ tục cải thiện, rồi chọn nghiệm cuối tốt nhất. Đây là multi-start local search thường gặp.

Bài này tập trung vào cấp độ thứ hai.

### Bảo toàn tính hợp lệ

Nếu một phép biến đổi trong `Improve` tạo lời giải không hợp lệ, không được chỉ so f rồi chọn nó. Cách an toàn là:

~~~text
if feasible(candidate) AND better(candidate,best):
    best = deepCopy(candidate)
~~~

Với bài toán có ràng buộc mềm dùng penalty, phải mô tả rõ score và so sánh tính hợp lệ; một điểm penalty cao/thấp không tự đại diện cho nghiệm hợp lệ.

## 3. Khung thuật toán, bất biến và quy tắc chọn tốt nhất

Giả mã tổng quát cho bài tối đa hóa:

~~~text
multiStart(input, restarts, rng):
    require restarts >= 1

    best = none
    bestScore = -infinity

    for run = 1..restarts:
        initial = initializeFeasibly(input, rng)
        candidate = localImprove(input, initial)

        assert isFeasible(candidate)
        score = objective(input, candidate)

        if best is none OR score > bestScore:
            best = COPY(candidate)
            bestScore = score

        record bestScoreAfterRun[run] = bestScore

    return best, bestScore, bestScoreAfterRun
~~~

Đối với **tối thiểu hóa**, thay `score>bestScore` bằng `score<bestScore` và khởi tạo `+infinity`.

### Bất biến best-so-far

Sau khi xử lý t lần chạy:

~~~text
bestScore_t = max(score_1,score_2,...,score_t)
~~~

Vì thế:

~~~text
bestScore_(t+1) >= bestScore_t
~~~

cho bài tối đa hóa; với tối thiểu hóa bất đẳng thức đảo chiều.

**Chứng minh:** lần t+1 chỉ cập nhật khi ứng viên tốt hơn nghiêm ngặt, nên best mới bằng `max(best cũ,score mới)`. Do đó best không bao giờ tệ đi.

### Khi bằng điểm thì sao?

Nếu hai lời giải cùng score, quy tắc đơn giản là **giữ lời giải gặp trước**. Quy tắc này ổn định để tái hiện test và không làm sai giá trị mục tiêu.

Có thể dùng tie-break khác như ít tài nguyên, khoảng cách ngắn hơn theo tiêu chí phụ hoặc so từ điển, nhưng phải nói rõ. **Không được thay đổi thước đo tối ưu chính** chỉ để phá hòa nếu đề không cho phép.

### Vì sao phải sao chép lời giải tốt nhất?

Nếu mảng `best` trỏ tới cùng vùng dữ liệu mà lượt chạy sau tiếp tục sửa, lời giải tốt nhất có thể bị thay đổi ngoài ý muốn:

~~~text
best = currentArray       // alias nguy hiem
mutate(currentArray)      // best cung thay doi
~~~

Cần dùng `clone()` hoặc copy đúng kiểu dữ liệu, đặc biệt với danh sách, ma trận, object mutable. Mã Java phía dưới tạo bản sao và trả bản sao của mảng partition, tránh lỗi alias.

## 4. Hai lực đối lập: đa dạng hóa và khai thác vùng tốt

Multi-start thường kết hợp:

- **Diversification (đa dạng hóa):** khởi tạo từ những vùng khác nhau của không gian nghiệm, tăng cơ hội thăm nhiều “lưu vực” cực trị cục bộ.
- **Intensification (khai thác):** từ một điểm bắt đầu, cải thiện tích cực đến khi không còn bước cải thiện hợp lệ trong lân cận đang xét.

Nếu chỉ đa dạng hóa mà không cải thiện, thuật toán có thể chọn các nghiệm thô rất kém. Nếu chỉ cải thiện từ một điểm mà không thay đổi khởi tạo, thuật toán có thể mắc kẹt tại cùng cực trị cục bộ mãi.

### Hình dung trên cảnh quan mục tiêu

~~~text
gia tri f(x)
     ^
     |           GLOBAL BEST
     |              /\
     |      local  /  \      local
     |       /\   /    \      /\
     |      /  \_/      \____/  \
     +----------------------------> x

x0_a -> local opt A
x0_b -> global best
x0_c -> local opt C
~~~

Hình vẽ chỉ là ẩn dụ cho không gian nghiệm; trong bài tổ hợp, nghiệm thường là bitmask, hoán vị, tập con hoặc phương án phân bổ, không phải một số thực x duy nhất.

### Nguồn đa dạng

- Random partition hoặc random permutation.
- Greedy ngẫu nhiên: lựa chọn trong danh sách ứng viên tốt gần nhất.
- Perturbation từ nghiệm hiện tại bằng nhiều bước thay đổi.
- Khởi tạo từ các lời giải xây dựng khác nhau (constructive heuristics).
- Chia vùng tìm kiếm, ràng buộc seed hoặc các thông số khởi tạo có chủ đích.

**Nhiều lần chạy giống hệt nhau không tạo ra nhiều vùng tìm kiếm.** Khi local search xác định, cùng điểm bắt đầu sẽ cho cùng kết quả.

## 5. Thiết kế hàm khởi tạo để có lời giải hợp lệ và đa dạng

Khởi tạo không chỉ là bốc ngẫu nhiên một dãy byte. Nó phải trả **một lời giải hợp lệ** mà bộ cải thiện xử lý được.

### Ví dụ theo cấu trúc

| Bài toán | Một kiểu khởi tạo hợp lệ |
| --- | --- |
| Max-Cut | Gán mỗi đỉnh ngẫu nhiên vào phía A hoặc B |
| TSP | Hoán vị ngẫu nhiên danh sách thành phố |
| Knapsack 0/1 | Sinh tập con rồi sửa/kiểm để không vượt capacity |
| Scheduling | Sinh thứ tự tác vụ hợp lệ với ràng buộc trước–sau |
| Graph coloring với k màu | Gán màu rồi sửa vi phạm, hoặc dùng xây dựng hợp lệ |
| Clustering | Chọn tâm ban đầu theo chiến lược phù hợp với thuật toán |
| Timetable | Xây lịch hợp lệ trước khi thử cải thiện |

### Uniform không phải lúc nào cũng tốt nhất

Khởi tạo đồng đều trên mọi lời giải hợp lệ có thể khó thực hiện hoặc quá tốn chi phí. Một cách xây dựng ngẫu nhiên thiên về nghiệm tốt có thể hiệu quả hơn trên mỗi lần thử, miễn **không bị thiên lệch quá mức vào cùng một lưu vực**.

Có thể phối hợp, ví dụ 50% khởi tạo ngẫu nhiên hoàn toàn và 50% khởi tạo greedy ngẫu nhiên. Nhưng tỷ lệ này là **tham số thí nghiệm**, không có bảo đảm tối ưu cho mọi bài.

### Sinh rồi sửa (repair)

Một số bài toán dùng khởi tạo chưa hoàn toàn hợp lệ, sau đó sửa để vào tập F. Khi đó cần:

1. Chứng minh/kiểm rằng repair luôn kết thúc.
2. Bảo đảm nghiệm sau sửa thuộc F.
3. Tính chi phí repair vào ngân sách chạy.
4. Không chọn nghiệm chưa sửa chỉ vì có score hấp dẫn.

### Mảng rỗng, miền nghiệm quá nhỏ

Nếu chỉ có một lời giải hợp lệ, mọi khởi tạo đều đưa đến cùng một kết quả; random restart không giúp về chất lượng. Nếu có quá ít lời giải và n nhỏ, **liệt kê toàn bộ** có thể tốt hơn nhiều lần khởi tạo trùng.

## 6. Local search: lân cận, quy tắc cải thiện và điều kiện dừng

Gọi N(x) là tập **lời giải lân cận** của x, ví dụ các nghiệm chỉ khác x bởi một phép swap hoặc một bit flip.

Với bài tối đa hóa, x là **cực đại cục bộ theo N** nếu:

~~~text
for every y in N(x):
    f(y) <= f(x)
~~~

Điều này không có nghĩa x tốt nhất trên toàn bộ F.

### Ba quy tắc phổ biến

**First improvement:** duyệt ứng viên lân cận theo thứ tự và lấy ngay ứng viên đầu tiên có `f(y)>f(x)`. Có thể giảm chi phí mỗi bước nhưng phụ thuộc mạnh vào thứ tự duyệt.

**Best improvement:** tính độ tăng của mọi nước đi lân cận, chọn nước đi có **mức tăng dương lớn nhất**. Bài Java dùng quy tắc này, với tie-break bằng chỉ số đỉnh nhỏ nhất.

**Stochastic improvement:** chọn ngẫu nhiên trong các nước đi cải thiện, có thể thêm khả năng đa dạng nhưng cần chứng minh lại mọi tính chất muốn dùng.

### Kết thúc hữu hạn

Trên không gian nghiệm hữu hạn, nếu mỗi bước **chỉ nhận cải thiện nghiêm ngặt**, không thể quay về một nghiệm có cùng score rồi lặp vô hạn; vì vậy local search sẽ dừng. Với trọng số cạnh nguyên không âm trong Max-Cut, giá trị cut nguyên và tăng ít nhất 1 ở mỗi lần flip, nên có thể chặn số bước theo tổng trọng số W.

Nếu cho phép **bước hòa** (`f(y)=f(x)`) mà không có cơ chế chống vòng lặp, thuật toán có thể di chuyển qua nhiều nghiệm cùng điểm rồi trở về trạng thái cũ mãi.

### Dừng do ngân sách khác dừng ở cực trị cục bộ

Nếu đặt giới hạn 100 bước rồi ngừng dù vẫn còn bước cải thiện, nghiệm trả về **không chắc là cực trị cục bộ**. Một bảo đảm dựa trên tính cực trị cục bộ **không còn được phép khẳng định** khi chỉ chạy dang dở, trừ khi chứng minh bảo đảm khác.

## 7. Ví dụ xuyên suốt: bài toán Max-Cut

Cho đồ thị vô hướng G=(V,E) với mỗi cạnh e=(u,v) có trọng số **w(e)≥0**. Ta chia các đỉnh thành hai phía S và V\S.

Một cạnh được **cắt (crossing/cut edge)** nếu hai đầu mút thuộc hai phía khác nhau. Trọng số cut là:

~~~text
CutWeight(S)
    = SUM over edges (u,v) with side[u] != side[v]
      weight(u,v)
~~~

Bài toán **Maximum Cut (Max-Cut)** tìm cách chia đỉnh để tổng trọng số các cạnh cắt là **lớn nhất**.

### Ví dụ chu trình sáu đỉnh, mỗi cạnh trọng số 1

~~~text
0 -- 1 -- 2
|         |
5 -- 4 -- 3
~~~

Danh sách cạnh:

~~~text
(0,1),(1,2),(2,3),(3,4),(4,5),(5,0)
~~~

Tổng trọng số cạnh W=6. Một partition được mã hóa bởi `side[v]` nhận 0 hoặc 1.

Partition:

~~~text
side = 010101
~~~

cắt cả sáu cạnh vì hai đỉnh liên tiếp luôn ở hai phía khác nhau:

~~~text
CutWeight = 6
~~~

Không có partition nào đạt >6 vì tổng trọng số tất cả cạnh chỉ bằng 6. Nên **OPT=6** được chứng minh ngay bằng cận trên.

### Vì sao phù hợp để học multi-start?

Max-Cut tối ưu là bài toán NP-hard trên đồ thị tổng quát, nhưng một lời giải hợp lệ cực dễ tạo: gán 0/1 cho các đỉnh. Hàm mục tiêu có thể tính chính xác. Lân cận “lật phía đúng một đỉnh” đơn giản, khiến ta dễ thấy sự khác nhau giữa **cực trị cục bộ** và **tối ưu toàn cục**.

Mã Java dưới đây nhận đồ thị có trọng số nguyên không âm; ví dụ chu trình chỉ dùng trọng số 1. Chương trình **không khẳng định** multi-start giải chính xác Max-Cut tổng quát; oracle vét cạn chỉ dùng để kiểm các đồ thị rất nhỏ.

## 8. Lân cận 1-flip và công thức độ tăng Max-Cut

Một nước đi **1-flip tại đỉnh v** chuyển v từ phía 0 sang 1 hoặc ngược lại, giữ nguyên mọi đỉnh khác.

Phân các cạnh kề v thành:

- **Cạnh đang được cắt**: đầu bên kia ở phía đối diện v.
- **Cạnh chưa được cắt**: đầu bên kia ở cùng phía v.

Nếu lật v:

- Mọi cạnh đang cắt kề v trở thành **không cắt**.
- Mọi cạnh chưa cắt kề v trở thành **cắt**.
- Mọi cạnh không kề v giữ nguyên trạng thái.

Vậy:

~~~text
gain(v)
    = SUM weight of incident uncut edges
    - SUM weight of incident cut edges

CutWeight(after flipping v)
    = CutWeight(before) + gain(v)
~~~

Chỉ flip khi `gain(v)>0`. Nếu nhiều đỉnh cùng gain lớn nhất, Java chọn đỉnh có chỉ số nhỏ hơn.

### Ví dụ cực đại cục bộ nhưng chưa tối ưu

Trên chu trình sáu đỉnh, partition:

~~~text
side = 001001

cach cac canh:
(0,1): same  -> uncut
(1,2): diff  -> cut
(2,3): diff  -> cut
(3,4): same  -> uncut
(4,5): diff  -> cut
(5,0): diff  -> cut

CutWeight = 4
~~~

Kiểm từng đỉnh:

- v=0 hoặc 1: có một cạnh đang cắt và một cạnh chưa cắt, gain=0.
- v=2: có hai cạnh đang cắt, gain=−2.
- v=3 hoặc 4: có một cạnh đang cắt và một cạnh chưa cắt, gain=0.
- v=5: có hai cạnh đang cắt, gain=−2.

Không đỉnh nào có gain>0, nên thuật toán **1-flip best improvement dừng ngay ở 4**. Nhưng partition `010101` đạt 6. Đây là cực đại cục bộ không tối ưu toàn cục, không phải lỗi cài đặt.

### Ví dụ khởi tạo toàn 0

~~~text
start = 000000
~~~

Theo quy tắc chọn nước đi gain dương lớn nhất và phá hòa bằng đỉnh nhỏ nhất:

~~~text
000000 -> flip 0 -> 100000, score 2
100000 -> flip 2 -> 101000, score 4
101000 -> flip 4 -> 101010, score 6
~~~

Kết thúc sau **3 flips**, trả `101010` với score 6. Đây là một optimum khác so với `010101`, vì đảo tất cả bit của một partition không làm thay đổi cut.

### Khởi tạo nhiều lần

Một lần xuất phát từ `001001` dừng ở 4. Một lần xuất phát từ `010101` dừng ở 6. Chọn nghiệm tốt nhất giữa hai lần là **6**, lớn hơn mọi nghiệm từng được ghi nhận trước đó. Nhưng không có cơ chế nào bảo đảm mọi tập nhỏ điểm khởi tạo đều sẽ chứa một nghiệm của lưu vực tốt nhất.

## 9. Bảo đảm xấp xỉ 1/2 cho Max-Cut tại cực đại 1-flip

Một kết quả mạnh và có thể chứng minh: với **trọng số cạnh không âm**, mọi partition không còn **bước 1-flip tăng nghiêm ngặt** đều có cut weight ít nhất **một nửa tổng trọng số cạnh**.

Ký hiệu:

~~~text
W    = SUM_{e in E} w(e)
C    = tong trong so cac canh dang cat
U    = tong trong so cac canh chua cat

W = C + U
~~~

Tại cực đại cục bộ theo 1-flip, với mọi v:

~~~text
gain(v) = uncutIncidentWeight(v)
        - cutIncidentWeight(v)
        <= 0
~~~

Suy ra:

~~~text
uncutIncidentWeight(v)
    <= cutIncidentWeight(v)
~~~

Cộng bất đẳng thức trên qua mọi đỉnh v. Mỗi cạnh vô hướng không phải self-loop có **đúng hai đầu mút**, nên được đếm hai lần ở vế tương ứng:

~~~text
2*U <= 2*C
U <= C
W = U+C <= 2*C
C >= W/2
~~~

Vì lời giải tối ưu không thể cắt nhiều hơn tổng trọng số cạnh:

~~~text
OPT <= W
C >= W/2 >= OPT/2
~~~

Đó là bảo đảm **xấp xỉ 1/2** cho lời giải cực đại cục bộ 1-flip của Max-Cut trọng số không âm.

### Điều kiện của chứng minh

- Trọng số cạnh phải **không âm**.
- Lời giải phải thực sự là **cực đại cục bộ theo mọi phép lật một đỉnh**, không chỉ đã chạy một vài bước.
- Không được bỏ sót cạnh khi tính gain.
- Giải thích áp dụng cho đồ thị vô hướng không self-loop (mã minh họa từ chối self-loop).
- Giá trị mục tiêu dùng trong chọn bước và chọn best phải cùng trọng số ban đầu.

### Multi-start có cải thiện bảo đảm 1/2 không?

Mỗi lần local search hoàn chỉnh đã đạt ít nhất `OPT/2`. Chọn **tốt nhất** trong các lần chạy giữ nguyên cận 1/2, và thực tế có thể tốt hơn. Tuy nhiên **không có bảo đảm tổng quát** rằng chỉ cần r lần restart thì sẽ tìm OPT hay có tỷ lệ tốt hơn 1/2 cho mọi graph.

### Nếu có giới hạn số flips

Nếu dừng trước khi không còn gain dương, bất đẳng thức `gain(v)≤0` cho mọi v chưa được thiết lập. Do đó **không thể viện dẫn chứng minh 1/2 trên đây** cho nghiệm bị dừng sớm. Cần một cận khác, hoặc hoàn tất tới cực đại cục bộ.

## 10. Xác suất tìm nghiệm tốt với nhiều khởi tạo

Giả sử một lần khởi tạo + cải thiện cho kết quả có score **ít nhất ngưỡng T** với xác suất p. Nếu các lần thử có phân phối phù hợp và **độc lập**, xác suất sau r lần có ít nhất một nghiệm đạt T là:

~~~text
P(bestScore >= T)
    = 1 - (1-p)^r
~~~

Đây là xác suất vượt một **ngưỡng chất lượng**, không nhất thiết là tìm tối ưu toàn cục. Khi T=OPT, p là xác suất một lần chạy tìm đúng optimum.

### Ví dụ chu trình sáu đỉnh

Duyệt đủ 2⁶=64 partition đầu vào và chạy 1-flip best improvement với tie-break xác định:

~~~text
32 initial partitions -> local optimum cut weight 4
32 initial partitions -> local optimum cut weight 6
~~~

Nếu khởi tạo bằng 6 bit 0/1 **độc lập đồng đều**, xác suất một lượt đạt optimum 6 là:

~~~text
p = 32/64 = 1/2
~~~

Với r lần **khởi tạo độc lập đồng đều**:

| r | Xác suất tìm ít nhất một nghiệm score 6 |
| ---: | ---: |
| 1 | 0,5 |
| 2 | 0,75 |
| 3 | 0,875 |
| 4 | 0,9375 |
| 10 | 0,9990234375 |

Đây là phân tích **cho đúng đồ thị sáu đỉnh và đúng quy tắc local search nói trên**. Không được mang p=1/2 áp dụng cho một đồ thị tùy ý.

### Phụ thuộc giữa các lần chạy

Nếu mọi lần đều dùng cùng partition ban đầu và local search xác định, các kết quả giống hệt nhau. Khi ấy xác suất “ít nhất một lần đạt T” vẫn bằng xác suất của một lần, không phải `1−(1−p)^r`.

Dùng cùng một đối tượng pseudorandom generator xuyên suốt các lượt có thể cung cấp các bit mới hữu ích trong thực hành, nhưng tính độc lập toán học là **giả thiết mô hình**, không thể chứng minh đơn thuần bằng việc gọi `nextBoolean()` nhiều lần.

### Diminishing returns

Nếu p∈(0,1), lợi ích tăng xác suất khi thêm lần chạy thứ r+1 là:

~~~text
[1-(1-p)^(r+1)] - [1-(1-p)^r]
    = p*(1-p)^r
~~~

Giảm dần theo r. Điều này khuyến khích cân bằng số lượt restart với chi phí mỗi lượt thay vì tăng r vô hạn.

## 11. Phân phối kết quả tốt nhất trong r lượt

Không phải lúc nào cũng biết một ngưỡng T có xác suất p. Có thể mô tả kết quả sau mỗi lượt bằng biến ngẫu nhiên X, ví dụ score sau một local search.

Gọi hàm phân phối tích lũy:

~~~text
F(t) = P(X <= t)
~~~

Với **tối đa hóa**, kết quả tốt nhất sau r lượt độc lập cùng phân phối là:

~~~text
M_r = max(X_1, X_2, ..., X_r)

P(M_r <= t) = F(t)^r
~~~

Vì mọi X_i phải đồng thời ≤t thì cực đại mới ≤t.

Với một ngưỡng score **ít nhất T**:

~~~text
P(M_r >= T)
    = 1 - P(all X_i < T)
    = 1 - [P(X < T)]^r
~~~

Đây là dạng tổng quát của công thức phần 10.

### Với bài tối thiểu hóa

Gọi:

~~~text
m_r = min(X_1, ..., X_r)
~~~

Khi ấy:

~~~text
P(m_r > t) = [P(X > t)]^r
P(m_r <= t) = 1 - [P(X > t)]^r
~~~

**Không được** dùng công thức của `max` rồi chỉ đổi tên biến sang `min` mà quên đổi sự kiện.

### Khi các lượt có phân phối khác nhau

Nếu các biến X_i độc lập nhưng không đồng phân phối, với `F_i(t)=P(X_i≤t)`:

~~~text
P(max_i X_i <= t) = PRODUCT_i F_i(t)
~~~

Nếu các lượt có tương quan, nhìn riêng từng phân phối biên **không đủ** để lấy tích. Có thể dùng các cận xác suất khác nếu biết cấu trúc phụ thuộc, nhưng không được giả định tự động.

### Best-so-far không luôn tăng nhiều

Dù `bestScore` không giảm, nó có thể giữ nguyên qua nhiều restart: tất cả lượt mới đều kém hoặc bằng incumbent. Một đường best-so-far phẳng **không chứng minh** đã đạt tối ưu, chỉ nói rằng chưa thấy cải thiện trong số lượt đã chạy.

## 12. Chiến lược phân bổ ngân sách và dừng

Tổng ngân sách có thể tính theo **số lần restart**, **số lần đánh giá objective**, **số lần thử nước đi**, hoặc **thời gian thực tế**. Tùy bài, các đơn vị này khác nhau đáng kể.

### Ngân sách cố định

~~~text
for r = 1..R:
    initialize
    improve
    update best
~~~

Dễ tái hiện và so sánh khi mỗi lượt có chi phí gần tương tự. Nếu local search ở mỗi lượt chạy lâu khác nhau, số restart bằng nhau chưa chắc nghĩa là ngân sách tính toán bằng nhau.

### Ngân sách thời gian

~~~text
while timeRemaining > estimatedCost:
    run another initialization + improvement
~~~

Phù hợp hệ thống thực tế, nhưng thời gian đo được phụ thuộc máy, tải hệ thống và triển khai. Không nên dùng mỗi elapsed-time của một lần đo để khẳng định hiệu quả thuật toán mang tính toán học.

### Ngưỡng chất lượng

Nếu có **cận trên** U cho bài maximize, khi gặp score=U thì đã có chứng minh tối ưu và có thể dừng. Ví dụ chu trình 6 cạnh không âm có W=6, một cut 6 đạt đúng cận W, nên chắc chắn tối ưu.

Nếu chưa có cận chặt, “không cải thiện sau 10 lượt” chỉ là một heuristic dừng, **không chứng minh** global optimum.

### Phân bổ giữa số restart và độ sâu cải thiện

Với tổng ngân sách B, có thể chọn:

- **Nhiều restart, ít bước cải thiện:** thăm nhiều lưu vực nhưng kết thúc non-optimal local states.
- **Ít restart, cải thiện sâu:** mỗi lượt khai thác kỹ một lưu vực, có thể bỏ sót vùng khác.
- **Phân bổ thích nghi:** tăng restart khi nhiều lần cải thiện sâu không còn tiến triển; thay đổi cường độ perturbation.

Phải nói rõ bảo đảm nào mất đi khi cắt ngắn local search. Trong ví dụ Max-Cut 1/2, chỉ nghiệm **đã không còn bước 1-flip dương** mới dùng trực tiếp được chứng minh.

## 13. Chi phí tính toán và một bẫy giả đa thức

Với đồ thị n đỉnh, m cạnh, một lần tính cut score mất O(m), và một lần quét tất cả gain 1-flip có thể làm O(n+m) nếu cộng gain qua tất cả cạnh rồi quét n đỉnh.

Nếu mỗi restart chấp nhận I lần flip, cần một lần quét nữa để biết đã đạt local optimum:

~~~text
Time per run = O((I+1)*(n+m))
Memory per run = O(n+m) including graph
                 O(n) auxiliary for partition/gains
~~~

Với r restarts:

~~~text
O(r*(I_max+1)*(n+m))
~~~

trong đó I_max là số flips chấp nhận lớn nhất trong các lần chạy. Lưu thêm lịch sử best-so-far dài r cần O(r) bộ nhớ.

### Chặn I theo trọng số nguyên

Mã Java dùng **trọng số long nguyên không âm**, tổng W≤Long.MAX_VALUE, và chỉ chấp nhận nước đi có gain nguyên **dương**, nên mỗi flip tăng score ít nhất 1. Vì score luôn trong [0,W]:

~~~text
I <= W
~~~

Do đó có cận **O(r*(W+1)*(n+m))** theo giá trị W. Đây chỉ là một **cận giả đa thức** khi trọng số được mã hóa nhị phân: W có thể rất lớn so với số bit input. Không được gọi thuật toán này là mạnh đa thức chỉ nhờ cận theo W.

### Đồ thị không trọng số

Khi mọi cạnh có trọng số 1, W=m và số lần flip không vượt m. Vì vậy một lần local search như mã có cận O((m+1)(n+m)); với r lượt, nhân thêm r. Cận này khá bảo thủ, nhưng hữu ích để thấy thuật toán kết thúc hữu hạn.

### Cải tiến incremental gain

Thay vì tính lại gain từ tất cả cạnh sau mỗi flip, có thể duy trì mảng gain và chỉ cập nhật các đỉnh kề với đỉnh vừa lật. Với cấu trúc ưu tiên thích hợp, việc tìm move tốt nhất cũng có thể nhanh hơn. Tuy nhiên cần quản lý update và tie-break cẩn thận để không dùng gain đã lỗi thời.

**Mã minh họa chọn sự đơn giản và đúng đắn**, tính lại toàn bộ gain để dễ kiểm và chứng minh. Nó không tuyên bố là cài đặt Max-Cut nhanh nhất trên đồ thị rất lớn.

## 14. Java 17: multi-start Max-Cut với nghiệm tốt nhất được bảo toàn

Chương trình hoàn chỉnh sau cung cấp:

- `Graph`: kiểm n≥1, đỉnh hợp lệ, trọng số `long` không âm, không self-loop; chấp nhận cạnh song song như các cạnh trọng số độc lập; tổng trọng số kiểm overflow bằng `Math.addExact`.
- `score`: tính tổng trọng số các cạnh có hai đầu ở hai phía khác nhau.
- `localSearch`: clone partition đầu vào; liên tiếp chọn 1-flip có **gain dương lớn nhất**, phá hòa theo đỉnh nhỏ nhất; dừng khi không còn gain dương.
- `bestOfRandomStarts`: tạo r partition bằng `Random(seed)`, thực hiện local search, lưu kết quả tốt nhất và lịch sử best-so-far.
- `Solution` và `Summary`: clone mảng trong constructor và getter để tránh mutation làm hỏng nghiệm đã ghi nhận.
- `exactMaxCut`: vét cạn khi n≤20; không dùng trên input lớn.
- `verifyAllSmallGraphs`: xét **mọi đồ thị vô hướng đơn không trọng số** với n=1..5 và **mọi partition bắt đầu**, so sánh local search với oracle vét cạn và bảo đảm 1/2.
- Ví dụ weighted triangle, dữ liệu sai và tràn tổng trọng số.

**Tên tệp bắt buộc: `MultiStartMaxCutDemo.java`.**

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public class MultiStartMaxCutDemo {

    public record Edge(int u, int v, long weight) {}

    public static final class Graph {
        private final int n;
        private final Edge[] edges;
        private final long totalWeight;

        public Graph(int n, Edge[] originalEdges) {
            if (n < 1) {
                throw new IllegalArgumentException(
                        "vertex count must be >= 1");
            }
            Objects.requireNonNull(originalEdges, "edges");
            this.n = n;
            this.edges = originalEdges.clone();

            long sum = 0L;
            for (Edge edge : edges) {
                Objects.requireNonNull(edge, "edge");

                if (edge.u() < 0 || edge.u() >= n
                        || edge.v() < 0 || edge.v() >= n) {
                    throw new IllegalArgumentException(
                            "vertex out of range");
                }
                if (edge.u() == edge.v()) {
                    throw new IllegalArgumentException(
                            "self-loop is not allowed");
                }
                if (edge.weight() < 0L) {
                    throw new IllegalArgumentException(
                            "negative weights are not supported");
                }

                sum = Math.addExact(sum, edge.weight());
            }
            this.totalWeight = sum;
        }
    }

    public record Solution(
            long score, boolean[] side, int flips) {

        public Solution {
            Objects.requireNonNull(side, "side");
            side = side.clone();
        }

        // Do not expose mutable internal arrays.
        @Override
        public boolean[] side() {
            return side.clone();
        }
    }

    public record Summary(
            Solution first, Solution best, long[] bestSoFar) {

        public Summary {
            Objects.requireNonNull(first, "first");
            Objects.requireNonNull(best, "best");
            bestSoFar = bestSoFar.clone();
        }

        @Override
        public long[] bestSoFar() {
            return bestSoFar.clone();
        }
    }

    private record Move(int vertex, long gain) {}

    private static void validatePartition(
            Graph graph, boolean[] side) {
        Objects.requireNonNull(graph, "graph");
        Objects.requireNonNull(side, "side");
        if (side.length != graph.n) {
            throw new IllegalArgumentException(
                    "partition length mismatch");
        }
    }

    public static long score(Graph graph, boolean[] side) {
        validatePartition(graph, side);
        long total = 0L;
        for (Edge edge : graph.edges) {
            if (side[edge.u()] != side[edge.v()]) {
                total = Math.addExact(total, edge.weight());
            }
        }
        return total;
    }

    // Compute gain for flipping every vertex in one edge scan.
    private static Move bestMove(Graph graph, boolean[] side) {
        long[] gain = new long[graph.n];
        for (Edge edge : graph.edges) {
            int u = edge.u();
            int v = edge.v();

            long delta = side[u] == side[v]
                    ? edge.weight() : -edge.weight();

            gain[u] = Math.addExact(gain[u], delta);
            gain[v] = Math.addExact(gain[v], delta);
        }

        // Deterministic tie-break: lower vertex id.
        int vertex = -1;
        long largestGain = 0L;
        for (int v = 0; v < graph.n; v++) {
            if (gain[v] > largestGain) {
                largestGain = gain[v];
                vertex = v;
            }
        }
        return new Move(vertex, largestGain);
    }

    public static Solution localSearch(
            Graph graph, boolean[] initial) {
        validatePartition(graph, initial);
        boolean[] side = initial.clone();
        long currentScore = score(graph, side);
        int flips = 0;

        while (true) {
            Move move = bestMove(graph, side);
            if (move.vertex() < 0) {
                break; // strict 1-flip local optimum
            }

            side[move.vertex()] = !side[move.vertex()];
            currentScore = Math.addExact(
                    currentScore, move.gain());
            flips++;
        }

        if (currentScore != score(graph, side)) {
            throw new AssertionError(
                    "incremental score mismatch");
        }
        return new Solution(currentScore, side, flips);
    }

    public static Summary bestOfRandomStarts(
            Graph graph, int restarts, long seed) {
        Objects.requireNonNull(graph, "graph");
        if (restarts < 1) {
            throw new IllegalArgumentException(
                    "restarts must be >= 1");
        }

        Random rng = new Random(seed);
        Solution first = null;
        Solution best = null;
        long[] history = new long[restarts];

        for (int run = 0; run < restarts; run++) {
            boolean[] start = new boolean[graph.n];
            for (int v = 0; v < graph.n; v++) {
                start[v] = rng.nextBoolean();
            }

            Solution candidate = localSearch(graph, start);
            if (first == null) {
                first = candidate;
            }
            if (best == null
                    || candidate.score() > best.score()) {
                best = candidate;
            }
            history[run] = best.score();
        }
        return new Summary(first, best, history);
    }

    // Exact oracle only for small n.
    public static long exactMaxCut(Graph graph) {
        Objects.requireNonNull(graph, "graph");
        if (graph.n > 20) {
            throw new IllegalArgumentException(
                    "exact oracle only supports n <= 20");
        }

        long best = 0L;
        int partitions = 1 << graph.n;
        for (int mask = 0; mask < partitions; mask++) {
            long value = 0L;
            for (Edge edge : graph.edges) {
                int u = (mask >>> edge.u()) & 1;
                int v = (mask >>> edge.v()) & 1;

                if (u != v) {
                    value = Math.addExact(
                            value, edge.weight());
                }
            }
            best = Math.max(best, value);
        }
        return best;
    }

    private static boolean[] partitionFromMask(
            int n, int mask) {
        boolean[] side = new boolean[n];
        for (int v = 0; v < n; v++) {
            side[v] = ((mask >>> v) & 1) == 1;
        }
        return side;
    }

    private static String bits(boolean[] side) {
        StringBuilder builder = new StringBuilder();
        for (boolean value : side) {
            builder.append(value ? '1' : '0');
        }
        return builder.toString();
    }

    private static String show(Solution s) {
        return "score=" + s.score()
                + ", flips=" + s.flips()
                + ", side=" + bits(s.side());
    }

    private static int[] verifyCycleStarts(Graph cycle) {
        int score4 = 0;
        int score6 = 0;
        for (int mask = 0; mask < 64; mask++) {
            Solution s = localSearch(
                    cycle, partitionFromMask(6, mask));

            if (s.score() == 4L) {
                score4++;
            } else if (s.score() == 6L) {
                score6++;
            } else {
                throw new AssertionError(
                        "unexpected cycle local optimum");
            }
        }

        if (score4 != 32 || score6 != 32) {
            throw new AssertionError(
                    "cycle outcome counts differ");
        }
        return new int[] {score4, score6};
    }

    // All 2^(n*(n-1)/2) simple graphs, and all 2^n starts,
    // for n=1..5; oracle does NOT use local-search gains.
    private static int[] verifyAllSmallGraphs() {
        int graphsChecked = 0;
        int startsChecked = 0;

        for (int n = 1; n <= 5; n++) {
            int possibleEdges = n * (n - 1) / 2;
            int graphMasks = 1 << possibleEdges;

            for (int mask = 0; mask < graphMasks; mask++) {
                List<Edge> edges = new ArrayList<>();
                int bitIndex = 0;

                for (int u = 0; u < n; u++) {
                    for (int v = u + 1; v < n; v++) {
                        if ((mask & (1 << bitIndex)) != 0) {
                            edges.add(new Edge(u, v, 1L));
                        }
                        bitIndex++;
                    }
                }

                Graph graph = new Graph(
                        n, edges.toArray(new Edge[0]));
                long optimum = exactMaxCut(graph);

                for (int startMask = 0;
                        startMask < (1 << n); startMask++) {
                    boolean[] initial = partitionFromMask(
                            n, startMask);
                    boolean[] before = initial.clone();

                    Solution result = localSearch(graph, initial);

                    // Only small unweighted graphs here:
                    // 2*score cannot overflow long.
                    if (!Arrays.equals(initial, before)
                            || result.score() > optimum
                            || 2L * result.score()
                               < graph.totalWeight
                            || result.score()
                               != score(graph, result.side())
                            || bestMove(graph, result.side())
                               .vertex() >= 0) {
                        throw new AssertionError(
                                "local-search invariant failed");
                    }
                    startsChecked++;
                }
                graphsChecked++;
            }
        }

        if (graphsChecked != 1099
                || startsChecked != 33866) {
            throw new AssertionError(
                    "wrong exhaustive counts");
        }
        return new int[] {
                graphsChecked, startsChecked
        };
    }

    public static void main(String[] args) {
        Graph cycle = new Graph(6, new Edge[] {
                new Edge(0, 1, 1L),
                new Edge(1, 2, 1L),
                new Edge(2, 3, 1L),
                new Edge(3, 4, 1L),
                new Edge(4, 5, 1L),
                new Edge(5, 0, 1L)
        });

        Solution bad = localSearch(cycle, new boolean[] {
                false, false, true, false, false, true
        });
        Solution good = localSearch(cycle, new boolean[] {
                false, true, false, true, false, true
        });
        Solution zeros = localSearch(cycle, new boolean[] {
                false, false, false, false, false, false
        });

        System.out.println("bad local: " + show(bad));
        System.out.println("alternating local: " + show(good));
        System.out.println("all-zero local: " + show(zeros));
        System.out.println(
                "cycle exact optimum = " + exactMaxCut(cycle));

        int[] cycleCounts = verifyCycleStarts(cycle);
        System.out.println(
                "cycle 64 starts: score4=" + cycleCounts[0]
                + ", score6=" + cycleCounts[1]);

        Summary a = bestOfRandomStarts(cycle, 24, 2026L);
        Summary b = bestOfRandomStarts(cycle, 24, 2026L);
        boolean replay = Arrays.equals(
                a.bestSoFar(), b.bestSoFar())
                && a.first().score() == b.first().score()
                && a.best().score() == b.best().score()
                && Arrays.equals(
                        a.best().side(), b.best().side());
        System.out.println("same seed replay = " + replay);

        System.out.println(
                "best >= first = "
                + (a.best().score() >= a.first().score()));
        System.out.println(
                "best <= exact = "
                + (a.best().score() <= exactMaxCut(cycle)));
        System.out.println(
                "best is 1-flip local optimum = "
                + (bestMove(cycle, a.best().side())
                   .vertex() == -1));

        boolean monotone = true;
        long[] history = a.bestSoFar();
        for (int i = 1; i < history.length; i++) {
            if (history[i] < history[i - 1]) {
                monotone = false;
            }
        }
        System.out.println(
                "incumbent nondecreasing = " + monotone);

        Graph weighted = new Graph(3, new Edge[] {
                new Edge(0, 1, 2L),
                new Edge(1, 2, 3L),
                new Edge(0, 2, 4L)
        });
        System.out.println(
                "weighted triangle: total="
                + weighted.totalWeight
                + ", exact=" + exactMaxCut(weighted));

        Graph single = new Graph(1, new Edge[0]);
        System.out.println(
                "single-vertex optimum = "
                + exactMaxCut(single));

        try {
            bestOfRandomStarts(cycle, 0, 2026L);
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid restarts: " + error.getMessage());
        }

        try {
            new Graph(2, new Edge[] {
                    new Edge(0, 0, 1L)
            });
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid edge: " + error.getMessage());
        }

        boolean overflowDetected = false;
        try {
            new Graph(2, new Edge[] {
                    new Edge(0, 1, Long.MAX_VALUE),
                    new Edge(0, 1, 1L)
            });
        } catch (ArithmeticException error) {
            overflowDetected = true;
        }
        System.out.println(
                "weight overflow detected = "
                + overflowDetected);

        int[] checked = verifyAllSmallGraphs();
        System.out.println(
                "all simple graphs n=1..5 = "
                + checked[0]);
        System.out.println(
                "all starting partitions checked = "
                + checked[1]);
        System.out.println("all checks passed = true");
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac MultiStartMaxCutDemo.java
java MultiStartMaxCutDemo
~~~

**Stdout xác định:**

~~~text
bad local: score=4, flips=0, side=001001
alternating local: score=6, flips=0, side=010101
all-zero local: score=6, flips=3, side=101010
cycle exact optimum = 6
cycle 64 starts: score4=32, score6=32
same seed replay = true
best >= first = true
best <= exact = true
best is 1-flip local optimum = true
incumbent nondecreasing = true
weighted triangle: total=9, exact=7
single-vertex optimum = 0
invalid restarts: restarts must be >= 1
invalid edge: self-loop is not allowed
weight overflow detected = true
all simple graphs n=1..5 = 1099
all starting partitions checked = 33866
all checks passed = true
~~~

### Giải thích các kiểm thử trong main

- `bad local` cho thấy một nghiệm score=4 đã **không còn bước 1-flip dương**, nhưng chưa bằng OPT=6.
- `alternating local` đạt score=6 ngay từ khởi tạo.
- `all-zero local` chứng minh bộ cải thiện thật sự thực hiện ba bước tăng điểm.
- `cycle 64 starts` là kiểm chứng toàn bộ các đầu vào ngẫu nhiên có thể có cho sáu bit, không phải một phép đo thống kê từ vài lượt.
- `same seed replay` đối chiếu **toàn bộ lịch sử best-so-far, score của lượt đầu/cuối và partition tốt nhất** trên hai lần chạy cùng seed. Nó không chứng minh RNG mật mã hoặc tính độc lập toán học.
- `best >= first` và `incumbent nondecreasing` là hai bất biến chọn lời giải tốt nhất.
- `best is 1-flip local optimum` xác nhận có thể dùng chứng minh cận 1/2.
- `weighted triangle` kiểm xử lý trọng số nguyên không âm. Tổng W=9 và optimum=7.
- Các input `restarts=0` hoặc self-loop bị từ chối đúng hợp đồng.
- Tổng trọng số vượt miền `long` bị phát hiện bằng `Math.addExact`, không âm thầm overflow.
- `all simple graphs ...` dùng brute force để đối chiếu **33.866 lượt khởi tạo** trên **1.099 đồ thị nhỏ**, xác minh cả tính hợp lệ, cực đại cục bộ, score chính xác và cận ít nhất W/2.

### Về khả năng tái lập

`new Random(2026L)` cho chuỗi giả ngẫu nhiên xác định theo seed trong Java. Cùng seed và cùng thứ tự gọi RNG tạo kết quả lặp được trong cùng hợp đồng triển khai. Ở đây chương trình chỉ in **các thuộc tính bất biến**, không in score ngẫu nhiên cụ thể phụ thuộc seed để tránh biến một mẫu thành “bảo đảm”.

Nếu cần giữ đúng từng bit output qua những môi trường/triển khai khác nhau, hãy ghi rõ thuật toán PRNG, phiên bản và cách ánh xạ random bits thành các lựa chọn, hoặc lưu cả dãy initial partitions.

## 15. Kiểm thử exhaustive và oracle cho lời giải tốt nhất

Một bộ test đáng tin không chỉ gọi `multiStart` vài lần rồi nhìn xem cut “có vẻ lớn”.

### Oracle brute force Max-Cut

Với n đỉnh và các bên 0/1, có tối đa 2ⁿ partition. Oracle:

~~~text
exactMaxCut(G):
    best = 0

    for every bitmask in [0, 2^n):
        cut = evaluateAllEdges(G,bitmask)
        best = max(best,cut)

    return best
~~~

Đây là O(2ⁿ·m), không phù hợp cho đồ thị lớn, nhưng với n≤5 đủ nhỏ để **kiểm chứng độc lập**.

### Liệt kê mọi đồ thị đơn không trọng số n≤5

Một đồ thị đơn vô hướng trên n đỉnh có `n(n−1)/2` cạnh có thể có. Mỗi cạnh hoặc hiện diện hoặc không, nên tổng số đồ thị có nhãn là:

~~~text
2^(n*(n-1)/2)
~~~

Bảng:

| n | Đồ thị đơn có nhãn | Số partition đầu vào cho mỗi graph |
| ---: | ---: | ---: |
| 1 | 1 | 2 |
| 2 | 2 | 4 |
| 3 | 8 | 8 |
| 4 | 64 | 16 |
| 5 | 1.024 | 32 |
| **Tổng** | **1.099** | **33.866 lượt (đã nhân theo mỗi graph)** |

Với mọi đồ thị và mọi partition khởi tạo:

1. Chạy local search và kiểm input không bị sửa.
2. Tính lại cut score từ danh sách cạnh, so đúng với score lưu trong `Solution`.
3. Kiểm `score≤OPT` qua brute force.
4. Kiểm `score≥W/2` (chỉ khi tìm kiếm đã tới cực đại 1-flip).
5. Kiểm không có đỉnh nào có gain>0.
6. Đếm đúng số đồ thị/lượt thử.

Mã Java thực hiện đủ sáu nhóm kiểm này. Không phát hiện sai lệch ở 33.866 lượt được liệt kê theo định nghĩa thuật toán.

### Vì sao exhaustive này hữu ích nhưng chưa phải chứng minh tổng quát?

Nó phát hiện nhiều lỗi cài đặt trên instance nhỏ, kể cả đồ thị rỗng cạnh, đồ thị đầy đủ, cấu trúc thưa, chu trình và đồ thị không liên thông. Nhưng mọi đồ thị n>5 vẫn chưa được liệt kê. Bảo đảm cho mọi n đến từ **chứng minh gain và bất đẳng thức ở phần 9**, không phải từ số lượng test.

### Test mảng best-so-far

Với bài maximize, `bestSoFar` phải **không giảm**. Với minimize, nó phải **không tăng**. Test bảo toàn best giúp phát hiện lỗi alias, cập nhật best khi lời giải kém, hoặc đọc score của một đối tượng đã bị sửa sau khi lưu.

## 16. Chọn giải pháp tốt nhất: các tiêu chí và bẫy đánh giá

### Luôn so đúng hàm mục tiêu

Giả sử một bài lịch làm việc cần giảm trễ hạn nhưng vẫn thỏa ràng buộc năng lực. Nếu lần chạy A tính score theo tổng giờ trễ còn lần chạy B theo số tác vụ trễ, lấy số nhỏ hơn trực tiếp **không có ý nghĩa**.

Trước khi multi-start, phải định nghĩa **một score thống nhất**. Nếu dùng penalty cho ràng buộc, cần công bố trọng số và biết rằng tối ưu một penalty chưa chắc bảo đảm feasibility.

### Nghiệm tốt nhất đã quan sát không phải cận dưới/chứng minh optimum

Nếu maximize và có incumbent L, thì:

~~~text
L <= OPT
~~~

L là một **cận dưới cho giá trị tối ưu** (nếu nghiệm hợp lệ). Muốn chứng minh L=OPT cần thêm **cận trên U** sao cho U=L.

Với minimize và incumbent U, thì:

~~~text
OPT <= U
~~~

U là **cận trên** của optimum; cần thêm cận dưới bằng U để chứng minh tối ưu.

### Tỷ lệ xấp xỉ với mục tiêu không âm

Với bài maximize không âm, thuật toán có tỷ lệ α (0<α≤1) khi bảo đảm:

~~~text
algorithmScore >= alpha * OPT
~~~

Với Max-Cut 1-flip local optimum có α=1/2. Với bài minimize, khái niệm xấp xỉ thường là `algorithmCost <= alpha * OPT` với α≥1, dưới các điều kiện thích hợp; không được dùng nguyên dấu bất đẳng thức của maximize.

Nếu mục tiêu có giá trị âm, chuẩn hóa hoặc diễn giải ratio có thể không còn hợp lệ; phải phát biểu bảo đảm theo giả thiết cụ thể.

### Khi hòa điểm

Nếu hai partition cùng cut score, giữ lần xuất hiện đầu. Nếu một sản phẩm cần tính đa dạng của nghiệm, có thể lưu **nhiều nghiệm đồng hạng** thay vì một best duy nhất, nhưng sẽ tốn bộ nhớ và thay đổi API. Khi có nhiều tiêu chí, cần định nghĩa lexicographic hoặc Pareto order trước.

## 17. Ứng dụng khởi tạo nhiều lần trên các bài toán khác

### TSP và 2-opt

Với **Traveling Salesperson Problem**, một tour hợp lệ là hoán vị mỗi thành phố đúng một lần rồi quay về điểm đầu. Có thể sinh tour ngẫu nhiên, cải thiện bằng 2-opt, sau đó chọn tour có **tổng độ dài nhỏ nhất** trong r lần chạy.

Mỗi tour sau 2-opt có thể là cực tiểu cục bộ theo thao tác đảo đoạn, không chắc là tour toàn cục ngắn nhất. Cần kiểm khoảng cách/tour hợp lệ, kể cả trường hợp có chiều đi–về khác nhau trong TSP có hướng vì công thức delta 2-opt đối xứng có thể không đúng.

### Knapsack

Một lời giải là bitset chọn vật, với tổng trọng lượng không vượt capacity. Random initialization có thể vi phạm capacity nếu chọn độc lập từng bit; phải có repair hoặc constructor bảo đảm hợp lệ. Sau đó dùng swap/add/drop theo neighborhood và so **tổng giá trị**.

Nếu một candidate có value cao nhưng vượt capacity, không được nhận chỉ vì score cao.

### Scheduling và routing

Khởi tạo ngẫu nhiên/greedy theo thứ tự tác vụ, cải thiện bằng swap/insert. Phải giữ các ràng buộc cứng như precedence, giới hạn tài nguyên, ca làm việc hoặc giới hạn xe. Khi thay objective từ makespan sang tổng lateness, so giữa các lần chạy cũng phải cập nhật chính xác định nghĩa score.

### Clustering và nhiều cực tiểu cục bộ

Ví dụ k-means nhạy với vị trí tâm ban đầu. Dùng nhiều khởi tạo rồi chọn nghiệm có giá trị objective nhỏ nhất (tổng bình phương khoảng cách trong mô hình k-means). Nhưng cần xử lý cluster rỗng, stopping tolerance và phân biệt tốt nhất theo training objective với đánh giá tổng quát trên dữ liệu khác.

### SAT và local search

Một heuristic có thể đi qua nhiều cách gán và cố tăng số mệnh đề thỏa. Nếu cần trả kết luận SAT/UNSAT chính xác, một nghiệm thỏa mọi mệnh đề có thể được kiểm nhanh; còn hết nhiều restart mà chưa thấy nghiệm **không chứng minh UNSAT**. Muốn chứng minh vô nghiệm cần một thuật toán/chứng nhận phù hợp.

## 18. So sánh multi-start với các metaheuristic khác

| Kỹ thuật | Cơ chế chính | Khi nên cân nhắc |
| --- | --- | --- |
| Multi-start local search | Nhiều x0 độc lập, improve, chọn best | Dễ cài, dễ song song, local search nhạy khởi tạo |
| Iterated Local Search (ILS) | Perturb một cực trị cục bộ rồi cải thiện lại | Muốn khám phá gần nghiệm tốt hiện tại |
| Simulated Annealing | Có thể chấp nhận bước xấu theo nhiệt độ | Muốn vượt rào cục bộ mà không reset hoàn toàn |
| Tabu Search | Ghi nhớ nước đi/trạng thái tạm cấm | Hạn chế vòng lặp, đa dạng hóa tìm kiếm |
| GRASP | Randomized greedy construction + local search | Có phương pháp xây dựng tốt và tùy biến được |
| Genetic/Evolutionary | Quần thể, lai ghép, đột biến, chọn lọc | Muốn dùng thông tin từ nhiều nghiệm cùng lúc |
| Beam Search | Giữ nhiều trạng thái tốt theo lớp tìm kiếm | Không gian có cấu trúc mở rộng theo bước |
| Exact branch-and-bound | Cận trên/dưới để loại nhánh | Muốn chứng minh tối ưu trên instance giải được |

### Multi-start khác ILS ở đâu?

Trong multi-start thuần túy, các lần khởi tạo thường được tạo lại từ nguồn phân phối đầu vào, không nhất thiết dựa trên nghiệm cũ. Trong ILS, một cực trị cục bộ thường được **perturb** rồi tiếp tục cải thiện, nên các lượt liên quan mạnh với nhau và có cơ chế khám phá lân cận của incumbent.

### Chọn giải pháp phù hợp

Không có phương pháp nào luôn thắng trên mọi bài. Một baseline tốt thường là:

1. Một constructive heuristic hợp lệ.
2. Một local search rõ lân cận và điều kiện dừng.
3. Multi-start với seed và ngân sách cố định.
4. Đối chứng với nghiệm exact khi instance nhỏ, và với baseline đủ mạnh khi instance lớn.

Chỉ thêm metaheuristic phức tạp khi dữ liệu cho thấy baseline chưa đáp ứng yêu cầu chất lượng/thời gian.

## 19. Đánh giá thực nghiệm và các lỗi triển khai thường gặp

### Thiết kế thí nghiệm công bằng

Khi so hai biến thể, hãy dùng:

- Cùng tập input, kể cả trường hợp khó, cực trị và đặc biệt.
- Cùng thước đo mục tiêu và verifier feasibility.
- Cùng ngân sách phù hợp: số lần tính objective, số lần flip hoặc thời gian CPU/wall clock theo mục tiêu.
- Nhiều seed được chọn trước, lưu seed và cấu hình để tái lập.
- Báo cáo phân phối chất lượng: **best, median, mean, độ lệch/percentile**, không chỉ một lần chạy đẹp nhất.
- Khi có OPT từ exact solver, báo khoảng cách `OPT−score` cho maximize hoặc `score−OPT` cho minimize; nếu dùng phần trăm, phải cẩn thận OPT=0.
- Tách thời gian khởi tạo, thời gian improve và chi phí đánh giá.
- Kiểm input chưa bị biến đổi ngoài ý muốn sau mọi lần restart.

### Những lỗi phổ biến

| Lỗi | Hậu quả | Khắc phục |
| --- | --- | --- |
| Dùng lại cùng start trong mọi restart | Lặp cùng cực trị cục bộ | Sinh khởi tạo mới |
| Khởi tạo RNG mới với cùng seed mỗi lượt | Lặp cùng chuỗi lựa chọn | Quản lý RNG hợp lý |
| Chọn candidate trước khi kiểm hợp lệ | Có thể lấy lời giải sai | Kiểm feasibility |
| Dùng score không nhất quán giữa các lượt | Best vô nghĩa | Một hàm objective |
| Maximize nhưng dùng `<` | Chọn nghiệm tệ | Chốt chiều tối ưu |
| Ghi `best=current` rồi sửa `current` | Best bị thay đổi do alias | Deep copy |
| Chấp nhận move gain=0 vô hạn | Có thể lặp vòng | Strict improvement hoặc chống lặp |
| Bỏ bước kiểm local optimum | Không có bảo đảm xấp xỉ đã chứng minh | Dừng đúng hoặc đổi bảo đảm |
| Dùng score gia tăng nhưng không kiểm lại | Lỗi cập nhật tích lũy | Tính lại objective để test |
| Gọi “best of r” là global optimum | Quá khẳng định | Gọi incumbent; đối chiếu cận |
| Dùng kết quả một seed để so phương pháp | Selection bias | Nhiều seed/instance |
| So 100 restarts với 1 restart nhưng không tính thời gian | Không công bằng | So ngân sách thực |
| Quên tính chi phí repair | Ước lượng quá lạc quan | Tính đủ pipeline |
| Trọng số âm nhưng áp proof Max-Cut 1/2 | Chứng minh không còn hợp lệ | Ràng buộc w≥0 |
| Cho phép self-loop trong mô hình gain không xử lý | Cạnh tự nối gây hiểu sai | Từ chối hoặc định nghĩa riêng |
| Tổng trọng số long overflow | Score và chọn best sai | `Math.addExact`/BigInteger |
| Test chỉ một đồ thị đơn giản | Không phát hiện lỗi tổng quát | Exhaustive nhỏ + random lớn |
| Dừng khi best-so-far không tăng một số lượt rồi gọi tối ưu | Không có chứng minh | Gọi heuristic stop |
| Chuyển từ minimization sang maximization mà không đổi tie/gap | So sánh sai | Viết comparator rõ |
| Nhiều restart phụ thuộc nhưng dùng công thức p độc lập | Xác suất phóng đại | Chứng minh điều kiện |

### Dữ liệu có nhiều optimum

Max-Cut có tính đối xứng: đổi toàn bộ bit 0↔1 vẫn cho cùng cut. Vì vậy **không so mảng partition bằng nhau để quyết định duy nhất**, mà so score và tính hợp lệ. Hai nghiệm tốt nhất khác nhau có thể đều đúng và đều tối ưu.

### Khi cần bảo mật

`Random(seed)` cho test tái lập, không được dùng làm nguồn randomness có yêu cầu không thể dự đoán trước. Cần lựa chọn RNG phù hợp mục tiêu, nhưng ngay cả RNG mật mã cũng không biến một local search thành thuật toán tối ưu toàn cục.

## 20. Bài tập thực hành và checklist

### Bài tập

1. Định nghĩa feasible solution và objective cho một bài tối đa hóa.
2. Viết giả mã multi-start với r lần chạy và best-so-far.
3. Chuyển giả mã sang bài **tối thiểu hóa**.
4. Chứng minh best-so-far không giảm trong bài maximize.
5. Giải thích vì sao phải copy incumbent thay vì lưu alias mảng mutable.
6. So diversification và intensification bằng ví dụ.
7. Cho lân cận N(x), định nghĩa cực đại cục bộ.
8. Phân biệt first improvement và best improvement.
9. Giải thích tại sao strict improvement trên không gian hữu hạn dẫn tới dừng.
10. Mô tả một chu trình do chấp nhận move bằng điểm có thể gây ra.
11. Tính cut score của partition 001001 trên chu trình 6 đỉnh.
12. Tính gain từng đỉnh của partition 001001; xác nhận không còn gain>0.
13. Chứng minh partition 010101 cho cut=6 và là optimum.
14. Mô phỏng các flip từ 000000 tới 101010, tính từng score.
15. Chứng minh công thức gain(v)=uncut incident weight−cut incident weight.
16. Chứng minh một cực đại cục bộ 1-flip có cut≥W/2 khi w≥0.
17. Từ OPT≤W, suy ra tỷ lệ xấp xỉ 1/2.
18. Tạo một thuật toán có budget flip và nêu rõ vì sao bảo đảm local optimum có thể mất.
19. Liệt kê 64 partition ban đầu của chu trình 6 đỉnh, đếm 32 score4/32 score6.
20. Nếu mỗi restart có xác suất p=1/2 đạt tối ưu, tính xác suất sau 2,4,10 lần độc lập.
21. Chứng minh `P(max(X1,...,Xr)≤t)=F(t)^r`.
22. Viết công thức tương tự cho `min(X1,...,Xr)`.
23. Tạo hai restart trùng start và giải thích vì sao công thức độc lập có thể sai.
24. Viết hàm `bestOfRandomStarts` với seed và tie-break giữ lần đầu.
25. Viết test `bestScore[r+1]≥bestScore[r]`.
26. Kiểm partition đầu vào không bị sửa sau khi localSearch.
27. Sửa một hàm trả record chứa mảng để tránh caller mutate incumbent.
28. Tính exact Max-Cut bằng bitmask cho n≤12.
29. Liệt kê mọi đồ thị đơn không trọng số n=4 và so local search với brute.
30. Chứng minh tổng 1.099 đồ thị và 33.866 start khi n=1..5.
31. Thử đồ thị một đỉnh, đồ thị không cạnh và đồ thị có hai thành phần.
32. Thêm cạnh song song có trọng số 3 và kiểm objective cộng trọng số đúng.
33. Tạo input có self-loop và kiểm API từ chối.
34. Tạo hai cạnh tổng trọng số lớn hơn Long.MAX_VALUE và kiểm overflow.
35. Đánh giá time complexity một lần quét gain từ m cạnh.
36. Chứng minh I≤W khi gain là số nguyên dương và score≤W.
37. Giải thích vì sao cận O(r(W+1)(n+m)) không mạnh đa thức theo bit trọng số.
38. Đề xuất cách cập nhật gain sau mỗi flip mà không quét lại mọi cạnh.
39. Áp dụng multi-start cho TSP với 2-opt, nêu điều kiện tour hợp lệ.
40. Áp dụng cho Knapsack có capacity, nêu cách repair trước khi so score.
41. So sánh multi-start với ILS hoặc simulated annealing.
42. Thiết kế bảng thực nghiệm với nhiều seed, cùng ngân sách và báo cáo median/best.
43. Nếu một heuristic tìm best score nhưng không có cận U, giải thích không thể khẳng định tối ưu.
44. Thiết kế dừng sớm khi có cận trên U và bestScore=U.
45. Chứng minh hoặc bác bỏ ý tưởng “nhiều restart luôn tìm được optimum sau số lượt cố định” khi xác suất vào vùng optimum rất nhỏ.

### Checklist trước khi triển khai

- Đã chốt **max hay min**, objective và kiểm hợp lệ?
- `initialize()` có tạo lời giải feasible và đa dạng?
- Local search có neighborhood, tie-break và điều kiện dừng rõ?
- Có phân biệt đạt local optimum với bị cắt ngang do budget?
- Có sao chép nghiệm tốt nhất, không giữ alias?
- Có ghi score + seed + budget + phiên bản thuật toán để tái lập?
- Có test best-so-far đơn điệu theo chiều tối ưu?
- Có tính toàn bộ chi phí khởi tạo, improve, kiểm objective và repair?
- Nếu viện dẫn xác suất best-of-r, có đủ giả thiết độc lập/phân phối?
- Có phân biệt lời giải tốt nhất quan sát với optimum được chứng minh?
- Có kiểm bằng exact/brute trên instance nhỏ và random test lớn?
- Nếu dùng Max-Cut 1/2, đồ thị có trọng số không âm và đã thật sự đạt 1-flip local optimum?
- Có nêu rõ khi một lớp input không hỗ trợ hoặc ngân sách hết?
- Có báo cáo kết quả thử nghiệm trên nhiều seed và cùng ngân sách?

**Tổng kết:** Multi-start không phải một phép màu biến heuristic thành thuật toán exact. Nó tổ chức nhiều lần **khởi tạo → cải thiện → so sánh → giữ incumbent** để tăng cơ hội vào một vùng nghiệm tốt. Bất biến best-so-far đảm bảo chất lượng nghiệm đã chọn **không tệ đi** khi thêm restart. Với các lần độc lập có xác suất p đạt ngưỡng T, cơ hội đạt T sau r lượt là `1−(1−p)^r`. Ở Max-Cut trọng số không âm, local search hoàn chỉnh theo 1-flip còn cho cận **ít nhất 1/2 optimum**; chọn best trong nhiều lần không làm mất cận này. Khi áp dụng thực tế, điều quan trọng nhất vẫn là **tính hợp lệ, objective nhất quán, điểm bắt đầu đa dạng, ngân sách công bằng, kiểm thử độc lập và diễn giải trung thực mức bảo đảm**.
