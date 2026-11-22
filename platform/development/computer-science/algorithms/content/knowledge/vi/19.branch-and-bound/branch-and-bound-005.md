# Cập nhật lời giải tốt nhất và điều kiện loại nhánh

Trong **nhánh và cận (branch and bound)**, ta tổ chức các phương án thành một cây tìm kiếm. Mỗi nút ứng với một **lời giải bộ phận**; mỗi cạnh tương ứng một quyết định. Ta không cần duyệt tất cả nhánh nếu có thể chứng minh rằng một nhánh **không thể tạo ra lời giải tốt hơn** đáp án tốt nhất đã biết. Để làm được như vậy, có hai khái niệm phải giữ rõ ràng:

- **Incumbent (lời giải tốt nhất hiện có):** một lời giải **đã hoàn chỉnh và hợp lệ**, cùng giá trị mục tiêu của nó.
- **Bound (cận cho nhánh):** một ước lượng **có chứng minh** rằng mọi lời giải hoàn chỉnh có thể đạt từ nhánh đó đều không vượt qua một giới hạn nhất định.

Đối với bài **tối thiểu hóa**, ta cần một **cận dưới (lower bound)** của chi phí mọi phương án có thể hoàn tất một nút. Nếu cận dưới đã lớn hơn hoặc bằng chi phí incumbent, nhánh không thể cải thiện đáp án. Đối với bài **tối đa hóa**, lập luận đối ngẫu dùng **cận trên (upper bound)**.

Bài học thuộc nhóm **Nhánh và cận** của Computer Science Algorithms. Trọng tâm là **“Cập nhật lời giải tốt nhất và điều kiện loại nhánh”**: khi nào cập nhật, khi nào được cắt, vì sao việc cắt là an toàn, cách xử lý nhiều nghiệm hòa, giá trị âm, trạng thái chưa có incumbent, và cách kiểm chứng một thuật toán nhánh-cận bằng vét cạn. Ví dụ xuyên suốt là **phân công n người cho n công việc với tổng chi phí nhỏ nhất**, có mã Java 17+ độc lập và kiểm thử.

## 1. Định nghĩa bài toán phân công

Có n nhân viên, n công việc, và một ma trận chi phí costs kích thước n×n. Phần tử costs[i][j] là chi phí khi giao **công việc j** cho **nhân viên i**.

Ta cần một hoán vị các công việc p[0],p[1],...,p[n−1] sao cho:

~~~text
Mỗi nhân viên i nhận đúng một công việc p[i].
Mỗi công việc được giao cho đúng một nhân viên.
Tổng chi phí = sum_{i=0..n-1} costs[i][p[i]].
Mục tiêu: làm tổng chi phí NHỎ NHẤT.
~~~

Không được gán cùng một công việc cho hai nhân viên. Bài học cho phép chi phí **âm, bằng 0 hoặc dương**; do đó mọi phép cắt dựa trên giả thiết “chi phí tích lũy chỉ tăng” đều cần được xem xét lại.

Một cách giải trực tiếp là duyệt toàn bộ n! hoán vị công việc, tính tổng chi phí và lấy phương án nhỏ nhất. Cách này là oracle đáng tin cho n nhỏ, nhưng số hoán vị tăng rất nhanh.

Phạm vi ví dụ: ma trận vuông, không có công việc bị cấm, mỗi nhân viên có thể nhận bất kỳ công việc chưa dùng. Đây là mô hình thuận tiện để chứng minh cận; nếu thêm việc cấm, khả năng không có lịch hợp lệ hoặc những ràng buộc phụ, ta phải điều chỉnh cả cách tạo incumbent và cách tính bound.

**Quy ước n=0:** có đúng một cách phân công rỗng, tổng chi phí bằng 0 và danh sách công việc rỗng. Chương trình dùng quy ước này để hành xử nhất quán ở trường hợp biên.

## 2. Mỗi nút của cây tìm kiếm lưu những gì?

Ta giao việc theo thứ tự nhân viên i=0,1,...,n−1. Một nút có các dữ liệu:

~~~text
worker       = nhân viên tiếp theo cần được giao công việc
used[j]      = công việc j đã được giao cho một nhân viên trước đó?
chosen[i]    = công việc được chọn cho nhân viên i đã xử lý
soFar        = tổng costs[i][chosen[i]] với 0 <= i < worker

incumbent    = tổng chi phí của phương án hoàn chỉnh tốt nhất đã biết
bestJobs     = hoán vị công việc của incumbent
~~~

**Bất biến:** ở đầu lời gọi tại mức worker, đúng worker công việc đã được chọn, chúng phân biệt, chosen[0..worker−1] chứa lựa chọn hợp lệ và soFar bằng đúng tổng chi phí của phần đó.

Một nhánh tại mức worker thử một công việc j chưa dùng, đánh dấu used[j], lưu chosen[worker]=j, rồi gọi đệ quy với worker+1 và soFar+costs[worker][j]. Khi quay về, hoàn tác used[j] để các nhánh anh em được thử trên cùng trạng thái ban đầu.

Nếu worker=n, mọi nhân viên đã được giao đủ, các công việc không trùng nên ta có một **nghiệm hoàn chỉnh hợp lệ**. Đây là thời điểm tự nhiên để so với incumbent và cập nhật nếu tốt hơn.

## 3. Incumbent không phải là một dự đoán bất kỳ

Incumbent phải là **giá trị mục tiêu của một nghiệm hoàn chỉnh khả thi**. Nếu chỉ lưu một con số do ước lượng ra, ta không thể dùng nó làm ngưỡng cắt an toàn.

Ví dụ bài minimization có nghiệm tốt nhất thật sự bằng 13, nhưng ta tùy ý đặt incumbent=5 mà không có phương án nào chi phí 5: điều kiện cắt LB≥5 có thể loại toàn bộ các nhánh chứa nghiệm tối ưu 13. Thuật toán sẽ tuyên bố sai rằng không có cách tốt hơn 5 dù 5 chưa từng đạt được.

Có hai phương án khởi tạo hợp lệ:

1. **Chưa có nghiệm:** incumbent=+vô cùng (hoặc một trạng thái Boolean “chưa tìm thấy”), rồi bắt buộc tìm ít nhất một lá hợp lệ trước khi cắt theo incumbent hữu hạn.
2. **Có nghiệm khả thi ban đầu:** xây nhanh một hoán vị hợp lệ bằng heuristic hoặc giải pháp đơn giản; lấy đúng chi phí của hoán vị đó làm incumbent.

Chương trình Java dùng **greedy khả thi**: xử lý các nhân viên theo thứ tự, mỗi người nhận công việc còn trống có chi phí nhỏ nhất. Vì có đúng n công việc và không có việc bị cấm, greedy luôn xây được một hoán vị hoàn chỉnh. **Greedy không được khẳng định là tối ưu**; nó chỉ cung cấp một upper bound ban đầu cho giá trị tối ưu của bài minimization.

Điểm phân biệt: **incumbent** là upper bound của giá trị tối ưu minimization vì nó là chi phí của một nghiệm có thật; còn **lower bound của nút** là cận dưới mà bất kỳ nghiệm hoàn tất nút đó đều không thể thấp hơn.

## 4. Quy tắc cập nhật lời giải tốt nhất

Tại lá hợp lệ, giả sử có chi phí total:

~~~text
if total < incumbent:
    incumbent = total
    bestJobs = bản sao của chosen[0..n-1]
~~~

Điều kiện **nhỏ hơn nghiêm ngặt** có ý nghĩa:

- Nếu total nhỏ hơn: ta đã tìm được nghiệm hoàn chỉnh tốt hơn, nên cập nhật cả chi phí và phương án.
- Nếu total bằng: với mục tiêu **chỉ cần một nghiệm tối ưu**, có thể giữ phương án cũ.
- Nếu total lớn hơn: giữ nguyên incumbent.

**Không được chỉ cập nhật số chi phí mà quên sao chép phương án.** chosen là mảng đang được ghi đè khi quay lui; nếu bestJobs chỉ tham chiếu cùng mảng, kết quả cuối có thể là một hoán vị khác với chi phí đã lưu.

**Không cập nhật incumbent từ chi phí của một nhánh chưa hoàn tất**. Khi còn nhân viên chưa giao, tổng soFar không phải giá trị mục tiêu của nghiệm hợp lệ. Đặc biệt khi có chi phí âm, nghiệm hoàn chỉnh có thể thấp hơn soFar; nhưng kể cả khi mọi chi phí không âm, một lời giải bộ phận vẫn chưa phải cách phân công đủ n nhân viên.

Trong mã, incumbentUpdates đếm **số lần có nghiệm hoàn chỉnh tốt hơn sau khi greedy đã khởi tạo**. Việc đặt nghiệm greedy ban đầu không được tính là một lần cải tiến trong thống kê đó.

## 5. Cận dưới đơn giản bằng tổng chi phí rẻ nhất còn lại

Giả sử đã giao công việc cho các nhân viên 0..worker−1, với tổng chi phí soFar. Gọi U là tập công việc **chưa dùng**.

Với mỗi nhân viên i từ worker đến n−1, đặt:

~~~text
rowMinimum(i,U) = min_{j thuộc U} costs[i][j].
~~~

Sau đó tính cận dưới:

~~~text
LB(state) = soFar + sum_{i=worker..n-1} rowMinimum(i,U).
~~~

Tại sao đây là **cận dưới hợp lệ**? Trong bất cứ cách hoàn tất nào, mỗi nhân viên i chưa được giao phải nhận **một công việc nào đó thuộc U**, do đó chi phí thật của người đó không thể nhỏ hơn rowMinimum(i,U). Cộng các bất đẳng thức cho mọi nhân viên còn lại, rồi cộng soFar, cho:

~~~text
LB(state) <= chi phí của MỌI cách hoàn tất state.
~~~

Công thức này **tạm cho phép nhiều nhân viên chọn cùng một công việc rẻ nhất** khi cộng các row minimum. Điều đó có thể làm LB thấp hơn chi phí của mọi hoán vị hợp lệ. Nhưng LB thấp hơn là **lạc quan**, vẫn an toàn cho việc cắt trong minimization; nó chỉ khiến thuật toán cắt được ít hơn.

Cận dưới **không cần là một phương án thực hiện được**. Ngược lại, incumbent phải đến từ một phương án thực hiện được. Đừng nhầm hai khái niệm này.

## 6. Điều kiện cắt cho bài minimization

Khi incumbent là chi phí của một nghiệm khả thi và LB là cận dưới hợp lệ của nhánh:

~~~text
Nếu chỉ cần giá trị tối ưu hoặc một phương án tối ưu bất kỳ:

    if LB(state) >= incumbent:
        return   // nhánh không thể cải thiện incumbent
~~~

Chứng minh bằng một chuỗi bất đẳng thức. Với bất cứ nghiệm hoàn chỉnh X nào mở rộng state:

~~~text
cost(X) >= LB(state) >= incumbent.
~~~

Vậy X không có chi phí **nhỏ hơn** incumbent. Bỏ toàn bộ nhánh không thể làm mất nghiệm cải thiện lời giải tốt nhất.

Điều kiện **LB >= incumbent** là đúng ngay cả khi chi phí có số âm, **nếu LB đã được chứng minh đúng**. Không cần giả định cost tăng theo độ sâu. Mọi thông tin về âm/dương đã được xét trong rowMinimum.

Nếu LB < incumbent, ta **chưa thể kết luận có nghiệm tốt hơn**: cận chỉ nói nhánh còn khả năng. Thuật toán vẫn phải đi sâu hoặc dùng một cận chặt hơn. Đây là chiều phân biệt giữa “chưa đủ cơ sở cắt” và “chắc chắn sẽ có cải thiện”.

## 7. Tại sao dấu bằng phụ thuộc mục tiêu đầu ra?

Quy tắc cắt LB≥incumbent đúng cho hai yêu cầu:

- Chỉ cần **giá trị mục tiêu nhỏ nhất**.
- Cần **một nghiệm tối ưu bất kỳ**.

Nếu yêu cầu **đếm mọi nghiệm tối ưu**, **liệt kê tất cả nghiệm tối ưu** hoặc chọn nghiệm tối ưu theo một quy tắc phụ như **thứ tự từ điển nhỏ nhất**, cắt tại dấu bằng có thể bỏ những phương án hòa mà đề yêu cầu giữ lại.

Ví dụ ma trận 3×3 toàn số 0:

~~~text
[0, 0, 0]
[0, 0, 0]
[0, 0, 0]
~~~

Mọi một trong 3! = 6 hoán vị đều có tổng chi phí 0. Greedy tạo ngay một nghiệm chi phí incumbent=0; LB ở gốc cũng bằng 0. Nếu dùng LB≥incumbent, thuật toán có thể **cắt ngay gốc**, trả một nghiệm tối ưu đúng nhưng **không thể đếm đủ 6 nghiệm tối ưu**.

Muốn giữ các nghiệm hòa, một lựa chọn là chỉ cắt khi **LB > incumbent** và xử lý đúng việc ghi nhận/đếm các lá có cost=incumbent. Với yêu cầu quy tắc hòa khác, còn phải thiết kế logic so sánh thứ tự phương án và thời điểm cho phép loại nhánh.

**Tóm lại:** điều kiện cắt không chỉ phụ thuộc vào **min/max**; nó còn phụ thuộc vào việc đề muốn **một nghiệm, tất cả nghiệm, số nghiệm hay nghiệm theo thứ tự phụ**.

## 8. Ví dụ 4×4: greedy, lower bound và nghiệm tối ưu

Xét ma trận chi phí:

| Nhân viên / Công việc | 0 | 1 | 2 | 3 |
| --- | ---: | ---: | ---: | ---: |
| 0 | 9 | 2 | 7 | 8 |
| 1 | 6 | 4 | 3 | 7 |
| 2 | 5 | 8 | 1 | 8 |
| 3 | 7 | 6 | 9 | 4 |

Greedy chọn việc rẻ nhất còn trống theo từng hàng:

~~~text
Nhân viên 0 -> việc 1, chi phí 2.
Nhân viên 1 -> việc 2, chi phí 3.
Nhân viên 2 -> việc 0, chi phí 5.
Nhân viên 3 -> việc 3, chi phí 4.

Greedy cost = 2+3+5+4 = 14.
Đây là incumbent ban đầu, KHÔNG phải lời giải tối ưu chắc chắn.
~~~

Tại gốc, chưa công việc nào được sử dụng. Row minimum của từng hàng lần lượt là 2,3,1,4:

~~~text
LB(root) = 2+3+1+4 = 10.
~~~

LB=10 < incumbent=14, nên **không được cắt gốc**. Cũng không được tuyên bố đã tìm được nghiệm có chi phí 10: các row minimum của hàng 0 và hàng 1 có thể không tạo cùng một hoán vị hợp lệ khi ghép các lựa chọn.

Khi duyệt các công việc theo chỉ số tăng dần, thuật toán tìm được phương án:

~~~text
jobOfWorker = [1, 0, 2, 3]

Chi phí:
  nhân viên 0 -> việc 1: 2
  nhân viên 1 -> việc 0: 6
  nhân viên 2 -> việc 2: 1
  nhân viên 3 -> việc 3: 4
Tổng = 13.
~~~

Vì 13<14, incumbent được cập nhật thành **13**, cùng bản sao của hoán vị [1,0,2,3]. Bản vét cạn xác nhận 13 là nhỏ nhất của tất cả 4! = 24 phương án hoàn chỉnh.

## 9. Lần theo cách cắt và cập nhật trong ví dụ

Ở gốc có incumbent=14.

**Thử giao việc 0 cho nhân viên 0:** soFar=9, còn các công việc {1,2,3}. Các row minimum cho nhân viên 1,2,3 lần lượt là 3,1,4; do đó LB=9+3+1+4=17≥14. Cắt ngay nhánh này, không cần thử ba hàng tiếp theo.

**Thử giao việc 1 cho nhân viên 0:** soFar=2, còn {0,2,3}; các row minimum của hàng 1,2,3 là 3,1,4. LB=10<14, nên phải thử tiếp.

**Tiếp tục giao việc 0 cho nhân viên 1:** soFar=2+6=8, còn {2,3}. Hàng 2 rẻ nhất ở việc 2 với chi phí 1, hàng 3 rẻ nhất ở việc 3 với chi phí 4. LB=8+1+4=13<14, nên tiếp tục đi sâu.

**Giao việc 2 cho nhân viên 2 và việc 3 cho nhân viên 3:** đi tới lá tổng 13, cập nhật incumbent từ 14 xuống 13. Từ thời điểm đó, mọi nhánh còn lại có LB≥13 đều bị cắt. Điều này tăng khả năng cắt nhánh so với khi best vẫn là 14.

Trong chương trình, mỗi lần gọi đệ quy tính một visitedNode. Ở ví dụ 4×4:

| Chỉ số | Duyệt mọi hoán vị | Dùng bound + incumbent |
| --- | ---: | ---: |
| Số nút đệ quy đã thăm | 65 | 11 |
| Số nút bị loại theo LB | 0 | 6 |
| Chi phí nhỏ nhất | 13 | 13 |
| Số lần incumbent được cải thiện sau greedy | Không sử dụng greedy | 1 |

Chương trình không đếm các ứng viên chưa được thử vì cha đã bị cắt là “prunedNodes” riêng. Mỗi nút bị cắt được tính một lần khi thuật toán đi vào nút và phát hiện LB≥best.

## 10. Phản ví dụ quan trọng khi chi phí âm

Một lỗi phổ biến là viết:

~~~text
if soFar >= incumbent:
    return
~~~

Điều này **không an toàn nếu chi phí chưa chọn có thể âm**. Xét ma trận:

~~~text
costs = [
    [  8, 10 ],
    [ -15,  1 ]
]
~~~

Greedy chọn cho nhân viên 0 việc 0 với chi phí 8, rồi nhân viên 1 việc 1 với chi phí 1, cho incumbent ban đầu **9**.

Nhánh tốt hơn chọn **việc 1 cho nhân viên 0**, có soFar=10. Lúc này **10≥9**, nên một thuật toán cắt theo soFar sẽ loại nhánh. Nhưng công việc còn lại cho nhân viên 1 là việc 0 với chi phí −15:

~~~text
Tổng chi phí cuối = 10 + (-15) = -5.
-5 < 9, nên đây mới là nghiệm tốt hơn.
~~~

Cận theo hàng của nhánh đó tính đúng:

~~~text
LB = soFar + min chi phí còn lại
   = 10 + (-15)
   = -5 < incumbent 9.
~~~

Vì vậy **không cắt**, đi tới lá và cập nhật incumbent=−5.

Nếu toàn bộ chi phí chưa xét được bảo đảm **không âm**, thì soFar thực sự là cận dưới của tổng cuối và có thể dùng làm bound (dù yếu). Nhưng không được âm thầm dùng điều kiện này cho dữ liệu có chi phí âm, chiết khấu, hoàn tiền hoặc điểm thưởng.

## 11. Chứng minh bound theo hàng là an toàn

Tại một nút, gọi R là tập nhân viên chưa xử lý và U là tập công việc chưa dùng. Với mỗi i thuộc R, định nghĩa m_i là chi phí nhỏ nhất của nhân viên i trên tập U.

Xét một cách hoàn tất hợp lệ bất kỳ p:

- Mỗi nhân viên i trong R được giao một công việc p[i] thuộc U.
- Vì m_i là giá trị nhỏ nhất trên U, ta có m_i≤costs[i][p[i]].
- Cộng các bất đẳng thức cho mọi i thuộc R, rồi thêm soFar, cho LB≤cost(p).

Vậy LB không lớn hơn **bất cứ** chi phí hoàn tất hợp lệ nào. Mọi nghiệm tốt hơn incumbent phải có tổng <incumbent, kéo theo LB<incumbent. Do đó nếu LB≥incumbent thì nhánh không thể chứa nghiệm cải thiện.

**Chứng minh không phụ thuộc dấu của chi phí.** Nó chỉ dùng tính chất “giá trị nhỏ nhất không lớn hơn giá trị của một phần tử thuộc tập”. Cũng không bắt buộc các rowMinimum ở các hàng phải chọn công việc phân biệt, bởi bound chỉ cần **lạc quan**, không cần là một hoán vị thực hiện được.

Khi không còn nhân viên chưa xét, tổng phần cận còn lại bằng 0. Mã kiểm tra lá **trước khi tính bound**, vì ở lá ta có nghiệm hoàn chỉnh để so sánh trực tiếp với incumbent.

## 12. Chứng minh thuật toán trả lời giải tối ưu

Ta cần hai tầng đúng đắn.

**Tầng 1 — Các lá được ghi nhận là hợp lệ:** tìm kiếm gán mỗi nhân viên một công việc chưa dùng. used[j] được đánh dấu khi chọn và hoàn tác sau nhánh. Khi worker=n, có n công việc khác nhau được chọn trong tập n công việc, nên ta có một hoán vị hợp lệ. Giá trị soFar đúng tổng chi phí nhờ bất biến cộng từng chi phí.

**Tầng 2 — Không bỏ một nghiệm cải thiện:** bất cứ nút nào bị cắt đều thỏa LB≥incumbent tại thời điểm cắt. Từ chứng minh ở mục trước, mọi nghiệm hoàn tất nút đều có tổng ≥incumbent lúc đó. Incumbent chỉ **giảm** khi tìm nghiệm hoàn chỉnh tốt hơn, nên một nghiệm ở nhánh đã cắt không thể tốt hơn chi phí tốt nhất đã được giữ lại về cuối.

Nếu ban đầu đã có một phương án khả thi (greedy), thuật toán luôn có nghiệm hợp lệ để trả ngay cả khi **gốc bị cắt**. Nếu có một phương án toàn cục tốt hơn incumbent cuối cùng, nhánh dẫn tới nó không thể bị cắt bởi một cận đúng; do đó tìm kiếm phải chạm lá hoặc đã tìm được một nghiệm không kém. Mâu thuẫn. Vì vậy kết quả cuối là tối ưu.

**Lưu ý quan trọng:** khi có nhiều nghiệm tối ưu, thuật toán chỉ bảo đảm **một** trong số đó theo hợp đồng hiện tại; không khẳng định thứ tự từ điển nhỏ nhất hay đếm đủ mọi phương án bằng nhau.

## 13. Bất biến của quay lui và việc hoàn tác

Ở một nút với tham số worker:

~~~text
used[j] = true nếu và chỉ nếu công việc j đã xuất hiện trong
          chosen[0..worker-1].

Tất cả chosen[0..worker-1] khác nhau.
soFar = tổng chi phí của đúng worker cặp đã chọn.
bestJobs chứa một hoán vị đã hoàn chỉnh.
incumbent là chi phí đúng của bestJobs.
~~~

Khi chọn job:

~~~text
used[job] = true
chosen[worker] = job
dfs(worker+1, soFar+costs[worker][job])
used[job] = false
~~~

Mã không cần xóa chosen[worker] sau nhánh, vì chỉ tiền tố chosen[0..worker−1] mới có nghĩa ở trạng thái cha. Tuy nhiên **used[job] phải được hoàn tác**, nếu không các nhánh anh em sẽ gặp những công việc bị khóa giả và có thể mất nghiệm.

Khi tìm được incumbent mới, bestJobs=current.clone(). Nếu không clone, những lần ghi chosen tiếp theo có thể làm kết quả trả về không còn khớp chi phí đã lưu. Record Solution trong mã còn copy mảng đầu ra để bên gọi không sửa trực tiếp mảng đã lưu bên trong record.

Chú ý **cập nhật incumbent** là trạng thái **toàn cục của quá trình tìm kiếm**, không được hoàn tác khi quay về nhánh cha. Chỉ các dấu lựa chọn của **nhánh hiện tại** mới cần undo. Hoàn tác cả incumbent sẽ làm thuật toán quên lời giải tốt nhất đã tìm được và giảm khả năng cắt.

## 14. Khởi tạo greedy và ảnh hưởng lên hiệu quả tìm kiếm

Việc có một incumbent tốt ngay từ đầu thường giúp cắt được nhiều nhánh. Với minimization:

- Incumbent càng **nhỏ** (nhưng vẫn là chi phí của một nghiệm hợp lệ), điều kiện LB≥incumbent càng dễ xảy ra.
- Incumbent quá lớn vẫn đúng, nhưng khó cắt nhánh.
- Incumbent nhỏ hơn giá trị tối ưu mà **không tương ứng nghiệm hợp lệ** thì sai nghiêm trọng.

Greedy theo từng hàng cho một cách nhanh để có nghiệm, với O(n²) thời gian và O(n) bộ nhớ cho used và danh sách công việc, nhưng **không bảo đảm kết quả gần tối ưu trong mọi ma trận**.

Một heuristic khác có thể cho phương án ban đầu tốt hơn; tuy nhiên chi phí xây dựng heuristic cũng là chi phí thuật toán. Trong bài thực hành, trước tiên hãy dùng cách khởi tạo đơn giản, chắc chắn hợp lệ, rồi đánh giá đo lường lợi ích của heuristic mạnh hơn trên nhiều đầu vào.

Đừng nhầm **tính hợp lệ của incumbent** với **tính an toàn của lower bound**. Hai điều này phải được chứng minh độc lập. Có incumbent rất tốt không giúp sửa một bound sai; một bound rất chặt không giúp sửa một incumbent không có nghiệm chứng thực.

## 15. Đặc điểm cận: yếu, chặt và chi phí tính

Một cận tốt cần **an toàn** trước tiên, sau đó mới xét độ chặt và tốc độ tính.

| Cách đánh giá phần còn lại | An toàn? | Độ chặt | Chi phí |
| --- | --- | --- | --- |
| Chỉ dùng soFar | Chỉ luôn an toàn nếu tổng chi phí còn lại không âm | Thường yếu | O(1) |
| soFar + tổng row minimum trên công việc chưa dùng | Có, cả khi chi phí âm | Trung bình; có thể dùng cùng một job nhiều lần | O(n²) mỗi nút với cách quét thẳng |
| Giải chính xác bài phân công còn lại | Có | Cận chặt nhất; bằng tối ưu phần còn lại | Có thể đắt hơn, tùy thuật toán sử dụng |
| Một giá trị “ước lượng” không có chứng minh | Không đảm bảo | Không có ý nghĩa chứng minh | Không nên dùng để cắt |

Cận qua row minimum đôi khi yếu vì các nhân viên đều muốn cùng một công việc rẻ nhất. Cộng tất cả chi phí rẻ nhất **bỏ qua xung đột trùng việc**, nên có thể thấp xa chi phí hoàn tất thực sự.

Có thể xây cận mạnh hơn bằng **bài toán gán thư giãn** hoặc thêm ràng buộc đã chứng minh, nhưng chi phí tính bound tăng. Một cận mạnh mà tính O(n³) ở mỗi nút đôi khi chậm hơn cận O(n²) đơn giản nếu chỉ loại được thêm rất ít nút.

Không nên thay bound đúng bằng một heuristic “trông gần nghiệm” rồi dùng nó cho phép cắt; heuristic giúp **ưu tiên duyệt** hoặc **tạo incumbent**, còn cận dùng để loại nhánh phải có lập luận toán học.

## 16. Thứ tự duyệt nhánh tác động thế nào đến incumbent?

Trong bài phân công, nếu thử những công việc có chi phí nhỏ sớm, thuật toán có thể gặp một nghiệm tốt hơn trước, giảm incumbent sớm hơn và cắt thêm nhiều nhánh phía sau.

Tuy nhiên, **thứ tự thử không phải điều kiện đúng đắn** của branch-and-bound nếu bound và logic cập nhật đã đúng. Chương trình ví dụ duyệt công việc theo thứ tự chỉ số tăng dần để kết quả tái hiện được. Greedy dùng công việc rẻ nhất chưa dùng để khởi tạo incumbent, nhưng DFS không áp đặt cách duyệt đó.

Một cách nâng cấp là sắp xếp các ứng viên tại mỗi nút theo một **ước tính chi phí đầy đủ**, ví dụ cận của nút con; sau đó thử nhánh lạc quan nhất trước. Muốn làm vậy cần cộng thêm chi phí tạo/sắp ứng viên vào độ phức tạp.

Đối với một phép tìm kiếm **chỉ cần một lời giải tối ưu**, việc tìm incumbent tốt sớm có thể tạo thay đổi lớn về số nút. Nhưng với bài **liệt kê mọi nghiệm tối ưu**, ta không được cắt nhánh hòa và có thể phải đi qua nhiều phương án dù đã biết giá trị tối ưu từ rất sớm.

## 17. Tối thiểu hóa và tối đa hóa: hai bất đẳng thức đối ngẫu

Cần ghi bảng so sánh rõ để tránh đảo chiều cắt:

| Mục tiêu | Incumbent là gì? | Cận nhánh cần có | Cập nhật tại nghiệm tốt hơn | Cắt nếu chỉ cần một nghiệm tối ưu |
| --- | --- | --- | --- | --- |
| **Minimize** | Chi phí một nghiệm khả thi, upper bound của optimum | LB ≤ mọi chi phí hoàn tất | candidate < incumbent | LB ≥ incumbent |
| **Maximize** | Lợi ích một nghiệm khả thi, lower bound của optimum | UB ≥ mọi lợi ích hoàn tất | candidate > incumbent | UB ≤ incumbent |

Với maximization, nếu mọi nghiệm hoàn tất từ nhánh có value≤UB và UB≤incumbent, nhánh đó không thể cải thiện. Cách kiểm tra đổi dấu **nhất quán với hàm mục tiêu**, không phải cứ gặp chữ “bound” là viết ≥.

Ví dụ bài knapsack tối đa lợi ích: một phương án chọn vật hợp lệ tạo incumbent profit; một upper bound lạc quan cho phần còn lại có thể được xây bằng cách cho phép **lấy phân số vật** sau khi đã cố định các lựa chọn nhị phân. Vì bài thư giãn cho nhiều quyền chọn hơn, giá trị tối ưu thư giãn không nhỏ hơn lợi ích của mọi nghiệm 0/1 hoàn tất, nên có thể dùng làm UB. Nhưng phải tính ràng buộc sức chứa và lợi ích đúng; một tổng profit đoán bừa không đủ.

Nếu bài toán có giá trị hòa và cần **mọi nghiệm tối ưu**, việc cắt tại UB=incumbent cũng cần được xét lại, tương tự dấu bằng của minimization.

## 18. Trạng thái chưa có nghiệm, không khả thi và giá trị vô cực

Nếu chưa có lời giải khả thi nào, chưa thể dùng một **incumbent hữu hạn** để cắt như thể nó đã là lời giải. Có thể biểu diễn “chưa có nghiệm” bằng một cờ riêng hoặc một sentinel cẩn thận như Long.MAX_VALUE trong bài minimization, và chỉ báo kết quả sau khi đã tìm được một lá hợp lệ.

Trong bài phân công của mã, **mọi phần tử ma trận đều cho phép gán**, nên greedy luôn tạo một hoán vị khả thi. Vì vậy không có trạng thái gốc “vô nghiệm” ngoại trừ đầu vào ngoài hợp đồng.

Nếu bài toán có **công việc bị cấm** hoặc các ràng buộc cặp người–việc:

- Greedy theo từng hàng có thể bị kẹt dù một phân công hợp lệ khác tồn tại.
- Một hàng còn lại không có công việc khả dụng có thể chứng minh nhánh vô nghiệm.
- Nếu mỗi hàng còn một việc khả dụng nhưng nhiều hàng buộc cùng một việc, vẫn có thể vô nghiệm; có thể cần kiểm tra matching hay một cận mạnh hơn.
- Không được dùng Integer.MAX_VALUE làm chi phí “cấm” rồi cộng như số bình thường mà không xác định rõ xử lý vô cực và overflow.
- Nếu không tìm thấy bất cứ nghiệm đầy đủ nào, API phải báo trạng thái **infeasible** thay vì trả một chi phí giả.

Đây là lý do bài học tách rõ **hợp đồng đầu vào**: mã chỉ xử lý mọi gán đều hợp lệ, không tự khẳng định giải được các phiên bản có gán bị cấm.

## 19. Những trường hợp có chi phí âm và dấu bằng

Chi phí âm là một bài kiểm tra rất hữu ích vì nó phát hiện những phép cắt được suy luận sai từ tính tăng của tổng tích lũy. Bản cận row minimum vẫn đúng vì giá trị nhỏ nhất có thể âm. Tổng bound có thể âm hơn nhiều soFar và cũng có thể thấp hơn tổng tối ưu của nhánh, nhưng không gây bỏ sót.

**Dấu bằng của bound** là một vấn đề khác: một nhánh có LB=incumbent có thể chứa **một nghiệm hòa tối ưu**. Khi chỉ cần một nghiệm, cắt được; khi cần đếm/khôi phục tất cả phương án hòa hoặc chọn theo quy tắc phụ, cần giữ lại hoặc bổ sung chứng minh mạnh hơn.

Mảng có nhiều giá trị bằng nhau không làm mất tính hợp lệ của phân công, vì công việc được phân biệt bằng **chỉ số**. Hai hoán vị khác nhau có thể có cùng chi phí và đều là nghiệm tối ưu.

**Trường hợp n=0:** tổng chi phí 0, hoán vị rỗng. Greedy đã là nghiệm khả thi và DFS vào thẳng lá; không cần tính cận trên tập hàng rỗng.

## 20. Kiểm thử không chỉ so chi phí mà còn kiểm tra hoán vị

Một chương trình branch-and-bound có thể báo đúng chi phí tối ưu nhưng trả về **danh sách công việc sai** nếu quên clone bestJobs, quên hoàn tác used hoặc khôi phục lựa chọn sai.

Vì vậy bộ kiểm thử Java thực hiện đồng thời:

1. Kiểm tra số phần tử của jobOfWorker đúng bằng n.
2. Kiểm tra từng chỉ số nằm trong [0,n−1] và không có hai nhân viên nhận trùng công việc.
3. Tính lại tổng chi phí từ ma trận và hoán vị đã trả, so chính xác với cost công bố.
4. Đối chiếu chi phí tối ưu branch-and-bound với **vét cạn tất cả hoán vị**, không dùng chính bound làm oracle.
5. Kiểm tra bản có cắt không thăm nhiều nút hơn bản vét cạn trong cùng cây tìm kiếm tuần tự.
6. Kiểm tra ma trận đầu vào không bị thay đổi.

Như vậy kiểm thử xác nhận cả **đúng giá trị mục tiêu** và **tính hợp lệ của nghiệm chứng minh cho giá trị đó**. Khi có nhiều nghiệm hòa, không buộc hai thuật toán trả cùng hoán vị vì chỉ cần **một** nghiệm tối ưu bất kỳ.

## 21. Java 17+ hoàn chỉnh: cập nhật incumbent và cắt nhánh theo LB

Chương trình bên dưới cài đặt:

- **exhaustive:** DFS tất cả n! hoán vị, chỉ đánh giá tại lá; là oracle tham chiếu.
- **branchAndBound:** tạo incumbent bằng greedy khả thi, tại mỗi nút tính LB bằng chi phí đã có cộng row minimum trên công việc còn lại; cắt khi LB≥incumbent.
- **Search:** giữ current, used, bestJobs, incumbent và thống kê, bảo đảm cập nhật bestJobs chỉ từ nghiệm hoàn chỉnh tốt hơn.
- **checkSolution:** xác nhận nghiệm trả về là một hoán vị và chi phí khớp.
- **verify:** sinh nhiều ma trận nhỏ, so với vét cạn và kiểm tra biên.

Đầu vào là ma trận int[][] vuông, có thể chứa số âm/dương/0, với n≤9 để giới hạn kích thước bộ trình diễn. Tổng tối đa của 9 chi phí int theo một hoán vị vẫn nằm trong **long**; chương trình dùng long cho soFar, incumbent và lower bound. Không phải mọi thuật toán branch-and-bound đều có thể dùng long mà không lo overflow; khi mở rộng số việc, kiểu chi phí hoặc công thức bound, phải đánh giá miền biểu diễn lại.

Record Solution có bản sao phòng vệ của mảng jobOfWorker khi xây record và khi đọc accessor, tránh để bên gọi làm thay đổi nghiệm đã được lưu. Mã không sửa ma trận đầu vào.

Lưu toàn bộ mã vào **IncumbentPruningAssignment.java**:

~~~java
import java.util.Arrays;
import java.util.Random;

public final class IncumbentPruningAssignment {
    public record Solution(long cost, int[] jobOfWorker, long visitedNodes,
                           long prunedNodes, long completeLeaves,
                           long incumbentUpdates) {
        public Solution {
            jobOfWorker = jobOfWorker.clone();
        }

        @Override
        public int[] jobOfWorker() {
            return jobOfWorker.clone();
        }
    }

    private record Baseline(long cost, int[] jobs) { }

    private IncumbentPruningAssignment() { }

    private static void validate(int[][] costs) {
        if (costs == null || costs.length > 9) {
            throw new IllegalArgumentException("square matrix, n <= 9 required");
        }
        int n = costs.length;
        for (int[] row : costs) {
            if (row == null || row.length != n) {
                throw new IllegalArgumentException("square matrix required");
            }
        }
    }

    private static Baseline greedy(int[][] costs) {
        int n = costs.length;
        int[] jobs = new int[n];
        boolean[] used = new boolean[n];
        long total = 0L;
        for (int worker = 0; worker < n; worker++) {
            int bestJob = -1;
            for (int job = 0; job < n; job++) {
                if (!used[job] && (bestJob < 0
                        || costs[worker][job] < costs[worker][bestJob])) {
                    bestJob = job;
                }
            }
            jobs[worker] = bestJob;
            used[bestJob] = true;
            total += costs[worker][bestJob];
        }
        return new Baseline(total, jobs);
    }

    private static final class Search {
        private final int[][] costs;
        private final boolean[] used;
        private final int[] current;
        private int[] bestJobs;
        private long incumbent;
        private long visited;
        private long pruned;
        private long completeLeaves;
        private long updates;

        Search(int[][] costs, Baseline initial) {
            this.costs = costs;
            used = new boolean[costs.length];
            current = new int[costs.length];
            bestJobs = initial == null ? new int[costs.length]
                    : initial.jobs().clone();
            incumbent = initial == null ? Long.MAX_VALUE : initial.cost();
        }

        void brute(int worker, long soFar) {
            visited++;
            if (worker == costs.length) {
                completeLeaves++;
                improveIfNecessary(soFar);
                return;
            }
            for (int job = 0; job < costs.length; job++) {
                if (!used[job]) {
                    used[job] = true;
                    current[worker] = job;
                    brute(worker + 1, soFar + costs[worker][job]);
                    used[job] = false;
                }
            }
        }

        void bounded(int worker, long soFar) {
            visited++;
            if (worker == costs.length) {
                completeLeaves++;
                improveIfNecessary(soFar);
                return;
            }

            long optimistic = lowerBound(worker, soFar);
            if (optimistic >= incumbent) {
                pruned++;
                return;
            }

            for (int job = 0; job < costs.length; job++) {
                if (!used[job]) {
                    used[job] = true;
                    current[worker] = job;
                    bounded(worker + 1, soFar + costs[worker][job]);
                    used[job] = false;
                }
            }
        }

        private long lowerBound(int firstUnassignedWorker, long soFar) {
            long bound = soFar;
            for (int worker = firstUnassignedWorker;
                    worker < costs.length; worker++) {
                int cheapest = Integer.MAX_VALUE;
                for (int job = 0; job < costs.length; job++) {
                    if (!used[job]) {
                        cheapest = Math.min(cheapest, costs[worker][job]);
                    }
                }
                bound += cheapest;
            }
            return bound;
        }

        private void improveIfNecessary(long totalCost) {
            if (totalCost < incumbent) {
                incumbent = totalCost;
                bestJobs = current.clone();
                updates++;
            }
        }

        Solution result() {
            return new Solution(incumbent, bestJobs, visited, pruned,
                    completeLeaves, updates);
        }
    }

    public static Solution exhaustive(int[][] costs) {
        validate(costs);
        Search search = new Search(costs, null);
        search.brute(0, 0L);
        return search.result();
    }

    public static Solution branchAndBound(int[][] costs) {
        validate(costs);
        Search search = new Search(costs, greedy(costs));
        search.bounded(0, 0L);
        return search.result();
    }

    private static void checkSolution(int[][] matrix, Solution sol) {
        int n = matrix.length;
        int[] choices = sol.jobOfWorker();
        if (choices.length != n) {
            throw new AssertionError("incorrect assignment length");
        }
        boolean[] used = new boolean[n];
        long actual = 0;
        for (int worker = 0; worker < n; worker++) {
            int job = choices[worker];
            if (job < 0 || job >= n || used[job]) {
                throw new AssertionError("non-bijective assignment");
            }
            used[job] = true;
            actual += matrix[worker][job];
        }
        if (actual != sol.cost()) {
            throw new AssertionError("reported cost disagrees with assignment");
        }
    }

    private static void compare(int[][] matrix) {
        int[][] original = new int[matrix.length][];
        for (int i = 0; i < matrix.length; i++) {
            original[i] = matrix[i].clone();
        }

        Solution brute = exhaustive(matrix);
        Solution bounded = branchAndBound(matrix);
        checkSolution(matrix, brute);
        checkSolution(matrix, bounded);
        if (brute.cost() != bounded.cost()
                || bounded.visitedNodes() > brute.visitedNodes()
                || !Arrays.deepEquals(matrix, original)) {
            throw new AssertionError(
                    "branch-and-bound mismatch: " + Arrays.deepToString(matrix));
        }
    }

    private static void verify() {
        int[] alphabet = {-2, 0, 3};
        int smallCases = 0;
        for (int n = 0; n <= 3; n++) {
            int combinations = 1;
            for (int cell = 0; cell < n * n; cell++) {
                combinations *= alphabet.length;
            }
            for (int code = 0; code < combinations; code++) {
                int remaining = code;
                int[][] matrix = new int[n][n];
                for (int row = 0; row < n; row++) {
                    for (int job = 0; job < n; job++) {
                        matrix[row][job] =
                                alphabet[remaining % alphabet.length];
                        remaining /= alphabet.length;
                    }
                }
                compare(matrix);
                smallCases++;
            }
        }

        Random random = new Random(1_234_567L);
        int largerCases = 0;
        for (int n = 4; n <= 6; n++) {
            for (int trial = 0; trial < 120; trial++) {
                int[][] matrix = new int[n][n];
                for (int i = 0; i < n; i++) {
                    for (int j = 0; j < n; j++) {
                        matrix[i][j] = random.nextInt(18) - 8;
                    }
                }
                compare(matrix);
                largerCases++;
            }
        }

        if (branchAndBound(new int[0][0]).cost() != 0
                || branchAndBound(new int[][] {{0,0,0},
                    {0,0,0}, {0,0,0}}).cost() != 0) {
            throw new AssertionError("empty or tie-only case failed");
        }
        if (branchAndBound(new int[][] {{8,10}, {-15,1}}).cost() != -5) {
            throw new AssertionError("negative-cost pruning failed");
        }
        if (branchAndBound(new int[][] {
                {Integer.MAX_VALUE, Integer.MAX_VALUE},
                {Integer.MAX_VALUE, Integer.MAX_VALUE}
            }).cost() != 2L * Integer.MAX_VALUE) {
            throw new AssertionError("long cost failed");
        }
        try {
            branchAndBound(new int[][] {{1,2}});
            throw new AssertionError("nonsquare input accepted");
        } catch (IllegalArgumentException expected) {
        }

        System.out.println("Verified " + smallCases
                + " exhaustive small matrices: PASS");
        System.out.println("Verified " + largerCases
                + " seeded larger matrices: PASS");
        System.out.println("Boundary, negative-cost and long checks: PASS");
    }

    public static void main(String[] args) {
        int[][] costs = {
            {9, 2, 7, 8},
            {6, 4, 3, 7},
            {5, 8, 1, 8},
            {7, 6, 9, 4}
        };
        Solution brute = exhaustive(costs);
        Solution bounded = branchAndBound(costs);
        System.out.println("Assignment optimal cost = " + bounded.cost());
        System.out.println("Assignment jobs = "
                + Arrays.toString(bounded.jobOfWorker()));
        System.out.println("Exhaustive nodes = " + brute.visitedNodes());
        System.out.println("Bounded nodes = " + bounded.visitedNodes());
        System.out.println("Bounded pruned nodes = " + bounded.prunedNodes());
        System.out.println("Bounded incumbent updates = "
                + bounded.incumbentUpdates());

        int[][] negative = {{8, 10}, {-15, 1}};
        System.out.println("Negative greedy cost = " + greedy(negative).cost());
        System.out.println("Negative optimal cost = "
                + branchAndBound(negative).cost());
        System.out.println("All-zero 3x3 cost = "
                + branchAndBound(new int[][] {
                    {0, 0, 0}, {0, 0, 0}, {0, 0, 0}
                }).cost());

        verify();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac IncumbentPruningAssignment.java
java IncumbentPruningAssignment
~~~

Stdout chính xác đã được thực thi:

~~~text
Assignment optimal cost = 13
Assignment jobs = [1, 0, 2, 3]
Exhaustive nodes = 65
Bounded nodes = 11
Bounded pruned nodes = 6
Bounded incumbent updates = 1
Negative greedy cost = 9
Negative optimal cost = -5
All-zero 3x3 cost = 0
Verified 19768 exhaustive small matrices: PASS
Verified 360 seeded larger matrices: PASS
Boundary, negative-cost and long checks: PASS
~~~

Từ output: với ma trận 4×4, hai phương pháp cho cùng chi phí 13; việc cắt theo bound giảm số nút 65 xuống 11. Với chi phí âm, greedy ban đầu 9, nhưng thuật toán tìm được nghiệm tốt hơn −5. Mảng 3×3 toàn 0 có kết quả 0 và một phương án tối ưu được giữ lại; chương trình **không** khẳng định đếm đủ sáu phương án hòa.

## 22. Bộ kiểm thử đầy đủ của chương trình

Đầu tiên, chương trình sinh **mọi ma trận vuông** kích thước n=0,1,2,3 với mỗi phần tử thuộc {-2,0,3}. Số ca:

~~~text
n=0: 3^(0*0) = 1 ma trận rỗng.
n=1: 3^(1*1) = 3 ma trận.
n=2: 3^(2*2) = 81 ma trận.
n=3: 3^(3*3) = 19683 ma trận.

Tổng = 1+3+81+19683 = 19768.
~~~

Mỗi ma trận được giải bằng **full permutation enumeration** và **branch-and-bound**, so chi phí, kiểm tra hoán vị, đối chiếu tổng, và bảo đảm không làm biến đổi input. Bộ dữ liệu bao gồm chi phí âm, cột/hàng hòa giá trị và cả ma trận rỗng.

Tiếp theo, chương trình dùng Random với seed cố định **1.234.567**, sinh 120 ma trận cho mỗi n=4,5,6; các giá trị nguyên từ −8 tới 9. Có **360** ca bổ sung, tất cả đều đối chiếu với oracle vét cạn.

Các ca biên riêng:

- 3×3 toàn số 0: nhiều phương án hòa nhưng chỉ cần một nghiệm có cost=0.
- Ma trận [[8,10],[-15,1]]: xác minh trường hợp partial cost có thể lớn hơn incumbent nhưng nghiệm cuối tốt hơn nhờ chi phí âm.
- Ma trận 2×2 toàn Integer.MAX_VALUE: chi phí tối ưu là 2×Integer.MAX_VALUE, vượt int nhưng vẫn trong long.
- Ma trận không vuông bị từ chối bằng IllegalArgumentException.
- Ma trận 0×0 có cost=0 và danh sách công việc rỗng.

**Phạm vi kiểm thử:** 19.768 ma trận vét cạn nhỏ và 360 ma trận seeded không thay thế một chứng minh tổng quát; điều kiện cắt được bảo đảm nhờ bất đẳng thức LB≤cost của mọi nghiệm hoàn tất, không nhờ “đã pass nhiều test”.

## 23. Độ phức tạp của hai cách tìm kiếm

Với n nhân viên và n công việc:

**Bản exhaustive:** có n! lá hoán vị. Số tiền tố ở mức r là P(n,r)=n!/(n−r)!, nên tổng số nút:

~~~text
N(n) = sum_{r=0..n} P(n,r).
~~~

Tổng này là Θ(n!) với n≥1. Tại mỗi nút chưa hoàn tất, code quét tối đa n công việc để tìm ứng viên chưa dùng. Vì vậy một cận tổng thời gian đơn giản là **O(n·n!)**, và bộ nhớ phụ O(n) cho used, current, bestJobs và stack đệ quy.

**Bản branch-and-bound:** cùng cây ứng viên về mặt lý thuyết, nhưng có thể bỏ nhiều nhánh. Bản cận theo hàng dùng hai vòng: mỗi hàng chưa giao quét các công việc chưa dùng, chi phí tối đa **O(n²) mỗi nút**. Vì vậy một cận trên an toàn cho thời gian xấu nhất là **O(n²·n!)** của hiện thực đơn giản này, cộng khởi tạo greedy O(n²). Bộ nhớ phụ vẫn O(n) cho quá trình tìm kiếm và O(n²) cho ma trận đầu vào đã có.

Cận O(n²·n!) không nói bản có cắt luôn chậm hơn: số nút thực tế có thể giảm rất mạnh, như 65 xuống 11 ở ví dụ. Nhưng cũng không có bảo đảm chung rằng pruning biến thời gian giai thừa thành đa thức.

Có thể cải tiến chi phí đánh giá bound bằng cách duy trì cấu trúc thông minh hơn, cập nhật cận gia tăng, hoặc dùng bound khác; tuy nhiên phải chứng minh đúng và đo hiệu quả. Số nút ít không đủ để xác định tốc độ nếu mỗi nút phải tốn quá nhiều công sức tính cận.

## 24. Phân biệt số nút, lá, nhánh bị loại và cập nhật

Trong code, các số thống kê có định nghĩa tường minh:

| Thống kê | Tăng khi nào? | Ý nghĩa |
| --- | --- | --- |
| visitedNodes | Mỗi lần vào hàm DFS, gồm cả lá và nút bị cắt | Số trạng thái đã khám phá |
| completeLeaves | Khi worker=n và có một phân công đầy đủ | Số nghiệm đầy đủ thực sự tới được |
| prunedNodes | Một nút chưa hoàn tất có LB≥incumbent | Số nút đã vào nhưng không mở rộng con |
| incumbentUpdates | Tìm một lá có cost thấp hơn incumbent hiện tại | Số lần cải thiện sau khởi tạo |
| incumbent cost | Không phải bộ đếm; thay khi có nghiệm tốt hơn | Chi phí tốt nhất đã có bằng một nghiệm thật |

**Nhánh bị cắt** không nhất thiết tương ứng đúng một lá bị bỏ. Cắt một nút ở mức r có thể bỏ hẳn nhiều hoán vị về sau. Vì vậy không được lấy số prunedNodes rồi trừ khỏi n! để suy ra số lá đã khám phá.

Tương tự, số lần incumbent cập nhật **không phải** số nghiệm hợp lệ đã tìm được; có thể đi tới nhiều lá nhưng chỉ một vài lá cải thiện best. Khi greedy đã tối ưu, số lần cập nhật có thể bằng 0, dù thuật toán vẫn trả kết quả đúng.

Khi báo hiệu năng, luôn ghi rõ đang đo **nút đệ quy**, **ứng viên được xét**, **lá**, **thời gian thực tế** hay **số lần tính bound**. Các đại lượng có liên hệ nhưng không hoán đổi trực tiếp cho nhau.

## 25. Những lỗi thường gặp khi cài đặt nhánh và cận

1. **Đặt best bằng một số chưa có nghiệm hợp lệ.** Một “ước lượng đẹp” không phải incumbent và có thể làm mất nghiệm.
2. **Cập nhật best bằng partial cost.** Trạng thái chưa hoàn chỉnh không phải một nghiệm phân công đủ n người.
3. **Đảo dấu trong minimization.** Cần lower bound và cắt khi LB≥best, không dùng upper bound như thể là lower bound.
4. **Đảo dấu trong maximization.** Cần upper bound và cắt khi UB≤best.
5. **Coi soFar là lower bound khi còn chi phí âm.** Phản ví dụ [[8,10],[-15,1]] loại nhầm nghiệm tối ưu −5.
6. **Dùng phép cắt ở dấu bằng khi cần đếm mọi nghiệm tối ưu.** Những nhánh hòa có thể bị mất.
7. **Tính row minimum trên cả công việc đã dùng.** Cận có thể vẫn lạc quan và an toàn, nhưng yếu không cần thiết; nếu lẫn cách tính lại tạo giá trị lớn hơn tối ưu thì có thể sai.
8. **Bỏ một hàng hoặc cộng trùng hàng trong bound.** Phải cộng đúng mỗi nhân viên chưa xử lý một lần và đúng soFar của tiền tố đã xử lý.
9. **Dùng một heuristic làm bound mà không chứng minh.** Giá trị dự đoán cao hơn optimum phần còn lại có thể cắt mất nghiệm tốt hơn.
10. **Dùng same-job row minima như một hoán vị khả thi.** Tổng minima có thể dùng một công việc nhiều lần, nên không phải incumbent.
11. **Quên hoàn tác used[job].** Những nhánh sau bị khóa công việc giả và có thể trả sai.
12. **Không clone phương án tốt nhất.** Mảng current tiếp tục bị thay trong DFS.
13. **Hoàn tác luôn incumbent sau mỗi nhánh.** Làm mất lời giải tốt đã tìm thấy và khiến cắt yếu hoặc sai.
14. **Kiểm tra bound tại lá trước khi cập nhật mà không có logic phù hợp.** Có thể bỏ mất cơ hội ghi nhận nghiệm hoàn chỉnh trong một triển khai chưa có incumbent.
15. **Không xét input không khả thi.** Với các cạnh gán bị cấm, greedy có thể không tìm được hoán vị dù một phương án khác tồn tại.
16. **Cộng chi phí bằng int.** Tổng n giá trị int có thể vượt int; sử dụng long hoặc kiểu số phù hợp.
17. **Giả định pruning là đa thức.** Trường hợp xấu vẫn có thể cần khảo sát cây lớn.
18. **Không đếm chi phí tính bound.** Cận mạnh nhưng đắt có thể không nhanh hơn cách khác.
19. **So khớp chính xác hoán vị khi có nhiều nghiệm tối ưu.** Hai thuật toán có thể trả hai hoán vị khác nhau cùng cost tối ưu.
20. **Không kiểm tra tổng từ nghiệm trả về.** Một bestCost đúng nhưng bestJobs không hợp lệ vẫn là lỗi.

## 26. Quy trình thiết kế một thuật toán branch-and-bound mới

Trước khi triển khai một bài tối ưu bằng nhánh và cận:

1. **Đặc tả đầy đủ** mục tiêu min/max, ràng buộc, miền dữ liệu và yêu cầu đầu ra (một nghiệm hay tất cả nghiệm tối ưu).
2. **Định nghĩa state** và các quyết định đã cố định; phải biết phần còn lại có những lựa chọn gì.
3. **Viết bất biến quay lui** để đảm bảo mọi lời giải bộ phận luôn nhất quán.
4. **Có cách nhận biết nghiệm hoàn chỉnh**, kiểm tra tính khả thi của nó và tính giá trị mục tiêu chính xác.
5. **Khởi tạo incumbent bằng nghiệm thật**, hoặc biểu diễn rõ chưa có nghiệm.
6. **Xây bound đúng chiều:** min cần LB; max cần UB.
7. **Chứng minh bound là lạc quan:** mọi nghiệm hoàn tất đều không tốt hơn bound theo chiều tương ứng.
8. **Chốt phép so sánh cắt**, đặc biệt với trường hợp hòa và yêu cầu đếm/tie-break.
9. **Đặt thời điểm cập nhật**, lưu bản sao phương án, không để ghi đè bởi nhánh sau.
10. **Hoàn tác biến cục bộ**, không hoàn tác best toàn cục.
11. **Kiểm soát số học**, nhất là giá trị âm và số cực trị.
12. **Tạo bản vét cạn làm oracle nhỏ**, so cả chi phí lẫn tính hợp lệ của phương án.
13. **Đo hiệu quả** bằng số node, thời gian và công sức tính cận trên dữ liệu đặc trưng.
14. **Cải thiện heuristic/bound nếu cần**, nhưng giữ nguyên chứng minh an toàn.

Một cách kiểm tra nhanh một điều kiện cắt: thử giả sử có một **nghiệm tốt hơn** nằm trong nhánh đang định bỏ. Nếu từ định nghĩa bound không thể suy ra mâu thuẫn với LB≥best (hoặc UB≤best), điều kiện đó chưa đủ cơ sở để loại nhánh.

## 27. Bài tập tự luyện

**Bài 1 — Duyệt tay ma trận 4×4:** dùng ma trận ở mục 8, tính greedy ban đầu và LB tại gốc, rồi tính LB sau khi thử công việc 0,1,2,3 cho nhân viên đầu tiên. Đánh dấu những nhánh cắt ngay. Giải thích vì sao nghiệm [1,0,2,3] có cost=13.

**Bài 2 — Chi phí âm:** với ma trận [[8,10],[-15,1]], tính hai hoán vị và chỉ rõ tại sao kiểm tra soFar≥best bỏ sai nghiệm −5. Tính bound sau khi giao việc 1 cho nhân viên 0.

**Bài 3 — Nghiệm hòa:** với ma trận 3×3 toàn 0, giải thích vì sao có 6 nghiệm tối ưu. Sửa điều kiện cắt và cách cập nhật để **đếm số nghiệm tối ưu**, rồi so với 6.

**Bài 4 — Truy vết và clone:** cố tình thay bestJobs=current bằng gán tham chiếu, chạy tìm kiếm thêm nhiều nhánh, kiểm tra tổng chi phí của hoán vị trả về. Sửa bằng clone và giải thích chu kỳ sống của mảng current.

**Bài 5 — Maximize:** đổi ma trận chi phí thành ma trận lợi ích. Xây một UB đơn giản bằng tổng lợi ích **lớn nhất** mỗi hàng trên công việc chưa dùng; chứng minh UB không nhỏ hơn mọi cách hoàn tất, rồi viết điều kiện cắt phù hợp.

**Bài 6 — Ràng buộc gán bị cấm:** thêm một ma trận allowed[i][j]. Hãy đề xuất cách tìm nghiệm khả thi ban đầu không giả định greedy luôn thành công, cách phát hiện một nhánh vô nghiệm và cách giữ bound an toàn khi thiếu công việc khả dụng.

**Bài 7 — Chất lượng bound:** trên một ma trận mà mọi hàng cùng thích một cột giá rất rẻ, giải thích vì sao tổng row minimum quá lạc quan. Tìm một cách đặt thêm ràng buộc hợp lệ để làm bound chặt hơn.

**Bài 8 — Hiệu năng:** đo thời gian và số nút của exhaustive vs branchAndBound trên các ma trận ngẫu nhiên có seed cố định, và trên ma trận nhiều số bằng nhau. Phân biệt trường hợp số nút giảm mạnh và trường hợp tính bound tốn nhiều công.

**Tự kiểm tra:** một cận dưới của nhánh có cần là chi phí của một phương án khả thi không? Có thể cắt tại LB=best khi cần đếm tất cả nghiệm tối ưu không? Tại sao best chỉ được cập nhật từ nghiệm đầy đủ? Điều gì phải hoàn tác khi lùi khỏi một nhánh và điều gì phải giữ lại?

**Kết luận:** chìa khóa của nhánh và cận không phải là “cắt càng nhiều càng tốt”, mà là biết **một lời giải tốt nhất có thật** và một **cận được chứng minh đúng**. Với minimization, chỉ được bỏ nhánh khi LB≥incumbent nếu mục tiêu là giá trị hoặc một nghiệm tối ưu; với maximization, dùng UB≤incumbent. Cập nhật best tại nghiệm hoàn chỉnh, lưu bản sao quyết định, xử lý dấu bằng theo yêu cầu đầu ra và kiểm chứng với vét cạn sẽ giúp kỹ thuật tối ưu có độ tin cậy cao ngay cả khi chi phí âm hoặc nhiều phương án hòa.
