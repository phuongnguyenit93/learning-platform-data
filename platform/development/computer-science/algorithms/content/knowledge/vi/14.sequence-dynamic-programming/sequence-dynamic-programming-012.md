# Thiết kế trạng thái theo phần tử cuối và trạng thái trước đó

Trong **quy hoạch động dãy (sequence dynamic programming)**, nhiều bài toán yêu cầu chọn một dãy con sao cho vẫn giữ thứ tự của các phần tử gốc. Ta thường phải quyết định: **một trạng thái nên ghi nhớ phần tử cuối cùng đã chọn, phần tử đang xét, hay cả hai?**

Chọn đúng ý nghĩa trạng thái giúp việc viết công thức chuyển trở nên tự nhiên. Chọn sai có thể làm mất thông tin cần thiết: hai dãy con có cùng độ dài nhưng **kết thúc bằng hai giá trị khác nhau** không phải lúc nào cũng được mở rộng bằng cùng một phần tử tiếp theo.

Bài này thuộc nhóm **Quy hoạch động dãy**, tập trung vào cách thiết kế trạng thái theo **phần tử cuối** và **trạng thái trước đó**. Ví dụ xuyên suốt là **Longest Increasing Subsequence (LIS)**, tức dãy con tăng nghiêm ngặt dài nhất. Ta sẽ xây dựng hai cách định nghĩa trạng thái, lưu chỉ số tiền nhiệm để khôi phục lời giải, phân tích phương án O(n²) và cách tăng tốc O(n log n), rồi so sánh với bài toán **dãy con tăng có tổng lớn nhất** để thấy chỉ cần đổi mục tiêu là cách tính trạng thái cũng thay đổi.

## 1. Đặc tả bài toán và phân biệt dãy con với đoạn con

Cho mảng số nguyên a có n phần tử, đánh số từ 0 đến n−1. Một **subsequence (dãy con)** được chọn bằng dãy chỉ số tăng nghiêm ngặt:

~~~text
0 <= i1 < i2 < ... < ik < n
~~~

Các phần tử không cần kề nhau trong mảng gốc. Ví dụ với a = [4,1,3,2,5], các dãy [1,3,5] (chỉ số [1,2,4]) và [1,2,5] (chỉ số [1,3,4]) đều là những dãy con hợp lệ.

Một dãy con **tăng nghiêm ngặt** cần thêm điều kiện:

~~~text
a[i1] < a[i2] < ... < a[ik].
~~~

**Bài toán LIS:** tìm dãy con tăng nghiêm ngặt có số phần tử k lớn nhất. Đầu ra có thể chỉ yêu cầu k, hoặc yêu cầu thêm các chỉ số và giá trị đã chọn. Nếu n = 0, độ dài LIS được quy ước là 0 và dãy con kết quả rỗng.

**Không nhầm với subarray:** đoạn con liên tiếp phải dùng các chỉ số liền nhau; LIS cho phép bỏ qua các vị trí. Ví dụ a = [4,1,3,2,5] có LIS độ dài 3 mặc dù những vị trí tạo nên LIS có thể không liền kề. Thuật toán cửa sổ trượt cho đoạn liên tiếp không tự áp dụng cho dãy con.

**Không nhầm tăng nghiêm ngặt với không giảm:** trong dãy tăng nghiêm ngặt, hai giá trị bằng nhau **không** được cùng xuất hiện liên tiếp trong một dãy con. Với [2,2,2], LIS nghiêm ngặt có độ dài 1; dãy con không giảm có thể có độ dài 3.

## 2. Vì sao độ dài dãy con đã chọn là chưa đủ làm trạng thái?

Giả sử đang xét thêm giá trị x. Ta chỉ được nối x vào một dãy con tăng nếu **giá trị cuối** của dãy đang có nhỏ hơn x.

Ví dụ có hai dãy con đã chọn:

- Dãy A = [1,4] dài 2, kết thúc bằng 4.
- Dãy B = [1,3] dài 2, kết thúc bằng 3.

Khi gặp x = 4, có thể nối vào B để thành [1,3,4], nhưng không thể nối vào A vì 4 không nhỏ hơn 4. Nếu chỉ lưu **độ dài 2** và bỏ qua giá trị/chỉ số cuối, hai tình huống bị đồng nhất sai.

Vì vậy, muốn quyết định một phần tử có nối tiếp được hay không, trạng thái phải giữ được **thông tin đủ để kiểm tra điều kiện chuyển**. Với LIS trên mảng cố định, lưu **chỉ số cuối i** đủ để biết cả giá trị a[i] và vị trí tương ứng.

Đây là nguyên tắc chung: trạng thái DP phải phân biệt mọi quá khứ có ảnh hưởng đến các quyết định tương lai. Những chi tiết không ảnh hưởng tương lai có thể được loại bỏ, nhưng **không được loại bỏ điều kiện nối tiếp**.

## 3. Cách 1: dpEnd[i] là độ dài tốt nhất kết thúc đúng tại i

Đặt:

~~~text
dpEnd[i] = độ dài lớn nhất của một dãy con tăng nghiêm ngặt
           mà phần tử CUỐI CÙNG bắt buộc là a[i].
~~~

Vì mọi dãy kết thúc ở i đều chứa a[i], ta có base case **dpEnd[i] ≥ 1**, với ứng viên đơn giản nhất chỉ gồm một phần tử [a[i]].

Để dãy kết thúc tại i có nhiều hơn một phần tử, phần tử áp cuối phải nằm ở một vị trí j thỏa:

~~~text
j < i     (đảm bảo giữ thứ tự chỉ số)
a[j] < a[i]   (đảm bảo tăng nghiêm ngặt)
~~~

Nếu một dãy tối ưu kết thúc tại j đã có độ dài dpEnd[j], nối a[i] vào sẽ tạo dãy độ dài dpEnd[j]+1. Do đó:

~~~text
dpEnd[i] = 1 + max(dpEnd[j]) trên mọi j<i có a[j]<a[i].

Nếu không tồn tại j phù hợp, dpEnd[i] = 1.

LIS_length = max(dpEnd[i]) trên i=0..n-1,
và LIS_length = 0 khi n=0.
~~~

Điểm then chốt: **dpEnd[i] là lời giải tối ưu trong nhóm buộc kết thúc tại i**, không phải “LIS của tiền tố a[0..i]”. Hai định nghĩa này khác nhau. Khi a[i] rất nhỏ, dpEnd[i] có thể chỉ là 1 dù LIS tốt nhất của tiền tố đã dài hơn.

## 4. Bảng ví dụ và cách chọn phần tử trước đó

Xét a = [4,1,3,2,5]. Đi lần lượt từ i=0 tới 4:

| i | a[i] | Các j hợp lệ có a[j]<a[i] | dpEnd[i] | previous[i] |
| ---: | ---: | --- | ---: | ---: |
| 0 | 4 | Không có | 1 | −1 |
| 1 | 1 | Không có | 1 | −1 |
| 2 | 3 | 1 (giá trị 1) | 2 | 1 |
| 3 | 2 | 1 (giá trị 1) | 2 | 1 |
| 4 | 5 | 0,1,2,3 | 3 | 2 |

Với i=4, có hai ứng viên độ dài 3: nối 5 vào [1,3] hoặc vào [1,2]. Hiện thực O(n²) phía dưới chỉ cập nhật khi gặp độ dài **lớn hơn** (không cập nhật khi bằng nhau), nên trước tiên chọn j=2 và giữ previous[4]=2. Kết quả được dựng là chỉ số [1,2,4], giá trị [1,3,5].

LIS tối ưu của mảng có độ dài **3**. Cả [1,3,5] và [1,2,5] đều đúng. **Nếu đề chỉ yêu cầu một LIS bất kỳ**, không phải áp đặt thứ tự từ điển hay chọn chỉ số nhỏ nhất; các quy tắc hòa khác nhau có thể trả những dãy tối ưu khác nhau.

Điều kiện thử j<i vừa bảo đảm dãy con giữ đúng thứ tự gốc, vừa tạo thứ tự phụ thuộc DP: khi xử lý i, mọi dpEnd[j] cần dùng đã tính xong.

## 5. Chứng minh công thức kết thúc tại i đúng

Ta chứng minh bằng quy nạp theo i:

**Cơ sở i=0:** mọi dãy con tăng kết thúc ở a[0] chỉ có thể chọn chính phần tử này, nên dpEnd[0]=1.

**Bước quy nạp:** giả sử dpEnd[j] đã đúng với mọi j<i. Xét một dãy con tăng bất kỳ kết thúc ở i.

- Nếu dãy dài 1, nó được tính bởi ứng viên cơ sở dpEnd[i]=1.
- Nếu dãy dài ít nhất 2, gọi j là chỉ số phần tử áp cuối. Vì đây là dãy con tăng, j<i và a[j]<a[i]. Bỏ a[i] đi ta được một dãy con tăng kết thúc tại j, nên độ dài tối đa không thể vượt dpEnd[j]. Do đó dãy ban đầu dài tối đa dpEnd[j]+1.
- Ngược lại, với mỗi j hợp lệ, nối a[i] vào một dãy tối ưu kết thúc tại j tạo đúng một dãy hợp lệ có độ dài dpEnd[j]+1.

Vậy lấy max các ứng viên trên cùng base case 1 cho đúng độ dài tốt nhất kết thúc ở i. Mọi LIS có một phần tử cuối ở chỉ số i nào đó, nên lấy max trên toàn bộ i cho độ dài LIS của cả mảng.

Ở đây **chỉ số cuối** đóng hai vai trò: xác định điều kiện nối tiếp qua a[i], và bảo đảm các trạng thái phụ thuộc chỉ nằm ở những chỉ số nhỏ hơn.

## 6. Phân biệt độ dài tối ưu với khôi phục lời giải

Nếu chỉ cần độ dài, mảng dpEnd[] là đủ. Nhưng nếu cần in lại các phần tử thuộc một LIS, chỉ biết số 3 không cho biết những vị trí đã chọn.

Ta lưu thêm:

~~~text
previous[i] = chỉ số j đứng ngay trước i trong lời giải
              tạo ra dpEnd[i], hoặc -1 nếu dãy chỉ có a[i].
~~~

Mỗi lần tìm được ứng viên tốt hơn thông qua j, cập nhật đồng thời:

~~~text
dpEnd[i] = dpEnd[j] + 1
previous[i] = j
~~~

Sau khi tính xong, tìm chỉ số last có dpEnd[last] lớn nhất. Đi ngược từ last qua previous[last], previous[previous[last]], ... tới −1. Vì mọi previous[i] được gán từ một j<i, chuỗi chỉ số giảm nghiêm ngặt khi đi ngược nên không thể tạo chu trình. Đảo thứ tự truy vết lại sẽ cho chỉ số và giá trị tăng theo chiều từ trái sang phải.

**Ví dụ:** last=4 → previous[4]=2 → previous[2]=1 → previous[1]=−1. Đảo thành [1,2,4], đọc được [1,3,5].

**Một lưu ý về độ phức tạp:** truy vết tốn O(L) với L là độ dài LIS, tối đa O(n). Vì việc tính bảng đã O(n²), chi phí truy vết không làm đổi độ phức tạp thời gian tổng thể.

## 7. Cách 2: DP theo vị trí đang xét và phần tử đã chọn trước đó

Một mô hình khác là đi từ trái sang phải và quyết định **bỏ qua** hay **lấy** phần tử hiện tại. Khi đó trạng thái tự nhiên có hai tham số:

~~~text
F(pos, prev) = độ dài lớn nhất có thể chọn thêm từ các vị trí
               pos..n-1, khi phần tử cuối ĐÃ CHỌN nằm ở prev.

prev = -1 nghĩa là chưa chọn phần tử nào.
Khi prev >= 0, cần prev < pos và a[prev] là giá trị
cuối cùng mà mọi phần tử tiếp theo phải vượt qua.
~~~

Ở trạng thái (pos, prev) có hai hành động:

1. **Skip:** bỏ a[pos], chuyển tới F(pos+1, prev).
2. **Take:** chỉ hợp lệ khi prev=−1 hoặc a[prev]<a[pos]. Chọn a[pos], được 1 + F(pos+1, pos).

Công thức:

~~~text
F(pos, prev) = max(
    F(pos+1, prev),
    1 + F(pos+1, pos) nếu prev=-1 hoặc a[prev]<a[pos]
)

F(n, prev) = 0.
Đáp án = F(0, -1).
~~~

Hai thông tin pos và prev có nhiệm vụ khác nhau:

- pos cho biết còn được xét những phần tử nào về sau, tránh chọn lại hoặc đổi thứ tự;
- prev cho biết phần tử cuối đã chọn, quyết định khả năng nối tiếp.

Đây là **trạng thái theo phần tử trước đó**, trong khi dpEnd[i] ở cách 1 là **trạng thái theo phần tử cuối của đáp án đang xây**. Hai định nghĩa đều giải đúng LIS nhưng đồ thị phụ thuộc và cách truy vết khác nhau.

## 8. Memoization với prev = −1 và phân tích O(n²)

Trong Java, ta dùng mảng memo[pos][prev+1]. Đẩy prev thêm 1 là cách mã hóa an toàn chỉ số sentinel −1 thành cột 0:

~~~text
prev = -1 -> cột 0
prev =  0 -> cột 1
prev =  1 -> cột 2
...
prev = n-1 -> cột n
~~~

Mỗi bộ (pos,prev) được tính nhiều nhất một lần sau khi memoization đã lưu kết quả. Số trạng thái hợp lệ thực tế thỏa **−1 ≤ prev < pos ≤ n** (trừ những trạng thái biên không phải lưu kết quả). Cận trên để cấp bảng là n×(n+1) ô, tức **O(n²)** bộ nhớ. Mỗi trạng thái có tối đa hai phép chuyển O(1), nên **O(n²)** thời gian cho lời giải top-down có nhớ.

**Đừng nhầm với đệ quy skip/take thuần:** nếu không memo, nhiều chuỗi quyết định khác nhau có thể dẫn tới cùng (pos,prev), bị giải lại nhiều lần. Thời gian có thể tăng theo cấp số nhân. Memo là yếu tố làm việc đếm trạng thái O(n²) có ý nghĩa.

**Chi phí ngăn xếp:** mọi lời gọi con đều tăng pos lên 1; độ sâu tối đa O(n). Với n lớn, bản top-down có thể chạm giới hạn stack dù số trạng thái và thời gian O(n²) đã được phân tích đúng. Cách bottom-up theo dpEnd tránh recursion stack.

**Quan trọng khi thiết kế khóa memo:** prev phải là **chỉ số**, không được nhầm với “độ dài hiện tại” hoặc dùng một giá trị sentinel trùng với phần tử có thể xuất hiện trong mảng. Mã −1 ở đây là sentinel chỉ số, hoàn toàn độc lập với giá trị a[i], nên vẫn hoạt động khi mảng có số âm.

## 9. So sánh hai lựa chọn trạng thái

| Tiêu chí | Kết thúc tại i | Vị trí pos + phần tử trước prev |
| --- | --- | --- |
| Định nghĩa | dpEnd[i]: LIS bắt buộc kết thúc ở i | F(pos,prev): LIS dài nhất có thể lấy trong hậu tố từ pos |
| Điều kiện nối | j<i và a[j]<a[i] | prev=−1 hoặc a[prev]<a[pos] |
| Quyết định | Chọn một j đứng trước i | Skip hoặc Take phần tử ở pos |
| Base case | Dãy chỉ gồm a[i], độ dài 1 | pos=n, còn 0 phần tử để chọn |
| Số trạng thái cận trên | n | O(n²) |
| Chi phí mỗi trạng thái | Quét tới n phần tử trước | Tối đa hai lựa chọn O(1) |
| Tổng thời gian | O(n²) | O(n²) với memo |
| Bộ nhớ trạng thái | O(n) cho dpEnd, O(n) cho previous | O(n²) memo và O(n) stack |
| Khôi phục | Đi previous[] từ chỉ số cuối | Lưu choice hoặc đối chiếu các nhánh memo |

**Bài học:** số trạng thái ít hơn không nhất thiết luôn nhanh hơn nếu mỗi trạng thái có nhiều ứng viên chuyển. Ngược lại, tăng số chiều có thể làm mỗi chuyển đơn giản hơn. Phân tích phải gồm **số trạng thái × chi phí tính mỗi trạng thái**, không chỉ nhìn kích thước bảng.

Nếu yêu cầu đếm số LIS, chọn LIS có thứ tự từ điển nhỏ nhất, hoặc áp dụng một quan hệ nối khác, có thể cần mở rộng trạng thái, quy tắc hòa và dữ liệu lưu. Không thể suy diễn trực tiếp rằng các kết quả trả về cũng giống nhau chỉ vì độ dài LIS bằng nhau.

## 10. Bất biến để khôi phục dãy con hợp lệ

Một hiện thực trả về các **chỉ số** i1,i2,...,ik cần kiểm tra tối thiểu ba điều kiện:

1. Độ dài của danh sách chỉ số đúng bằng k đã công bố.
2. **0 ≤ i1 < i2 < ... < ik < n** — các vị trí thuộc mảng gốc và không bị lặp.
3. **a[i1] < a[i2] < ... < a[ik]** — giá trị tăng nghiêm ngặt.

Các điều kiện này mới chứng minh dãy đã in **hợp lệ**, chưa chứng minh nó dài nhất. Để chứng minh tính tối ưu, cần thêm công thức quy hoạch động hoặc so sánh với lời giải chuẩn độc lập.

Trong bài kiểm thử Java, một dãy được coi là đúng khi **vừa hợp lệ vừa có độ dài trùng oracle vét cạn**. Không yêu cầu hai thuật toán in cùng chuỗi chỉ số, vì có thể có nhiều nghiệm tối ưu.

Việc giữ chỉ số gốc cũng rất cần thiết khi đề yêu cầu trả các vị trí đã chọn hoặc khi mỗi phần tử còn mang thêm dữ liệu phụ. Chỉ in mảng giá trị đã tăng không đủ để khôi phục chính xác lựa chọn trong trường hợp có giá trị trùng.

## 11. Tăng tốc LIS bằng đuôi tối ưu và tìm nhị phân

Với bài toán LIS **chỉ cần độ dài hoặc một LIS bất kỳ**, có thể giảm thời gian từ O(n²) xuống **O(n log n)** bằng một bất biến khác.

Đặt tailIndex[t] là chỉ số của phần tử kết thúc một dãy con tăng có độ dài t+1, được chọn sao cho **giá trị kết thúc nhỏ nhất có thể** trong số các dãy cùng độ dài đã xét. Các giá trị ở các vị trí tailIndex[0], tailIndex[1], ... tăng nghiêm ngặt.

Ý nghĩa: trong hai dãy con tăng cùng độ dài, dãy có **giá trị kết thúc nhỏ hơn** dễ được nối bằng các phần tử tương lai hơn. Ta có thể bỏ đại diện kết thúc lớn mà **không giảm khả năng đạt độ dài LIS lớn nhất**.

Với mỗi phần tử a[i], tìm **vị trí đầu tiên t có giá trị đuôi ≥ a[i]** (lower bound):

- Nếu t bằng số độ dài đang có, a[i] mở rộng dãy dài nhất thêm một.
- Nếu t đã tồn tại, thay đại diện kết thúc của độ dài t+1 bằng a[i] để giữ đuôi nhỏ.
- Nếu t>0, ghi previous[i] = tailIndex[t−1] **trước khi** cập nhật tailIndex[t]. Đây là tiền nhiệm của dãy mới kết thúc tại i.

Tìm t bằng binary search O(log n) trên các đuôi có thứ tự. Tổng n phần tử là O(n log n); hai mảng tailIndex và previous tốn O(n) bộ nhớ. Sau khi xử lý hết, truy vết từ tailIndex[length−1] qua previous[] để dựng một LIS.

**Lưu ý quan trọng:** tailIndex[t] chỉ là đại diện đuôi tốt nhất ở thời điểm hiện tại; không phải mọi tailIndex[t] trên các độ dài khác nhau cùng nằm trong một chuỗi chỉ số đang chọn. Để truy vết, ta dùng **chuỗi previous đã ghi ở từng thời điểm**, không đơn giản ghép các tailIndex lại.

## 12. Phân biệt lower bound, upper bound và quy tắc trùng nhau

Với LIS **tăng nghiêm ngặt**, ta tìm vị trí đầu tiên có **đuôi ≥ x**, tức lower bound. Khi giá trị x trùng một đuôi cũ, nó **thay đại diện** chứ không tạo một mức độ dài mới.

~~~text
a = [2, 2, 2]
LIS tăng nghiêm ngặt: 1 phần tử
Đuôi độ dài 1 được cập nhật nhiều lần, nhưng length luôn bằng 1.
~~~

Nếu bài toán yêu cầu **dãy con không giảm** (được phép bằng nhau), điều kiện chuyển của dpEnd đổi thành a[j] ≤ a[i], và binary search trên đuôi cần tìm vị trí đầu tiên có **đuôi > x** (upper bound), cho phép các phần tử bằng nhau mở rộng dãy.

Đây không phải một thay đổi cú pháp vô hại. Hai yêu cầu **strictly increasing** và **nondecreasing** có tập nghiệm hợp lệ khác nhau. Khi áp dụng giải pháp cho bài cụ thể, phải viết rõ quan hệ so sánh trước khi chọn lower/upper bound.

**Tình huống mảng âm và cực trị int:** cách tìm nhị phân so sánh trực tiếp các phần tử bằng <, ≥, không lấy hiệu hai giá trị int, nên không bị tràn vì phép trừ comparator. Nó xử lý được Integer.MIN_VALUE và Integer.MAX_VALUE theo thứ tự số nguyên có dấu.

## 13. Biến thể: dãy con tăng có tổng lớn nhất, không phải dài nhất

Hãy thay đổi mục tiêu: chọn một **dãy con tăng nghiêm ngặt không rỗng**, tối đa hóa **tổng giá trị**, không tối đa hóa số phần tử.

Đặt sumEnd[i] là tổng lớn nhất của một dãy con tăng kết thúc đúng tại a[i]. Ta có:

~~~text
sumEnd[i] = max(
    a[i],
    sumEnd[j] + a[i] với mọi j<i và a[j]<a[i]
).

Đáp án = max(sumEnd[i]) trên mọi i, n>0.
~~~

Base case phải là **a[i]**, không phải 0 hoặc 1. Khi tất cả phần tử âm, đáp án vẫn phải chọn ít nhất một phần tử. Ví dụ:

- a = [9,1,2,3]: LIS dài nhất là [1,2,3] có độ dài 3 và tổng 6, nhưng **tổng dãy con tăng lớn nhất là 9** bằng cách chỉ chọn [9].
- a = [−5,−2,−7]: tổng lớn nhất của dãy con tăng không rỗng là **−2**, không phải 0.

Nếu cố dùng dpEnd (độ dài) để giải tối đa tổng, ta tối ưu sai mục tiêu. Chúng ta có thể giữ **cùng kiểu phụ thuộc theo phần tử cuối i**, nhưng đại lượng lưu trong mỗi trạng thái và base case phải thay đổi.

Trong Java, phương thức maxSumIncreasing dùng **long** để tránh mất kết quả do tổng vượt int. Nó từ chối mảng rỗng bằng IllegalArgumentException, khác với LIS độ dài được định nghĩa bằng 0 khi mảng rỗng. Đó là lựa chọn hợp đồng có chủ đích.

## 14. Mở rộng cách nghĩ trạng thái cho bài toán dãy khác

Nhiều bài toán dãy được giải bằng cách hỏi: **tương lai cần nhớ gì về phần tử cuối hoặc quyết định trước?**

| Bài toán | Trạng thái ứng viên | Phụ thuộc / điều kiện chuyển |
| --- | --- | --- |
| Dãy con tăng dài nhất | dpEnd[i] | j<i và a[j]<a[i] |
| Dãy con tăng tổng lớn nhất | sumEnd[i] | j<i, a[j]<a[i], dùng tổng thay độ dài |
| Dãy con giảm dài nhất | dpEndDecreasing[i] | j<i và a[j]>a[i] |
| Dãy xen kẽ tăng/giảm | dp[i][sign] | Trạng thái còn nhớ hướng tăng/giảm gần nhất |
| Dãy con có tổng theo modulo m | dp[pos][remainder] | Trạng thái nhớ số dư sau khi lấy/bỏ |
| Dãy con có giới hạn phần tử cuối | dp[pos][previousIndex][constraint] | Cần thêm giới hạn hoặc dữ liệu liên quan |
| Đường đi dài nhất trong DAG | dp[v] | Mỗi cạnh hợp lệ nối một trạng thái tiền nhiệm |
| Dãy liên tiếp có quy tắc cặp kề | dpEnd[i] hoặc dp[i][lastType] | Ràng buộc **chỉ trên phần tử kề** của đoạn |

Không phải mọi bài dãy đều cần nhớ toàn bộ prefix. Nếu chỉ giá trị cuối và một số điều kiện phụ quyết định được các hành động hợp lệ tiếp theo, ta có thể gộp rất nhiều quá khứ vào một trạng thái.

Nhưng không thể gộp hai tình huống có **khả năng tiếp tục khác nhau**. Ví dụ bài dãy xen kẽ dấu tăng/giảm cần nhớ hướng của bước gần nhất; chỉ nhớ vị trí cuối có thể chưa đủ nếu không biết trạng thái hướng đi.

**Chú ý loại bài:** dãy con cho phép bỏ phần tử, trong khi đoạn liên tiếp có thể có công thức khác dựa vào việc kéo dài từ đúng vị trí kề trước đó. Cùng có chữ “dãy”, nhưng không được tự ý dùng cùng một công thức chuyển.

## 15. Chương trình Java 17+ hoàn chỉnh

Mã dưới đây cung cấp:

- **lisEndingAt:** DP O(n²) theo phần tử kết thúc i; trả độ dài, danh sách chỉ số gốc và giá trị của một LIS.
- **lisPreviousState:** top-down memoization theo (position, previousIndex), trả độ dài LIS để minh họa trạng thái trước đã chọn.
- **lisBinarySearch:** LIS O(n log n), dùng đại diện đuôi tốt nhất và previous[] để trả một LIS hợp lệ.
- **maxSumIncreasing:** tối đa tổng của dãy con tăng nghiêm ngặt không rỗng, dùng long.
- **verify:** kiểm thử các phương thức trên bằng oracle duyệt tập con và kiểm tra tính hợp lệ của dãy trả về.

Hợp đồng: mảng đầu vào không null, không bị sửa đổi. Với LIS, mảng rỗng có độ dài 0 và mảng chỉ số/giá trị rỗng; với tổng lớn nhất không rỗng, mảng rỗng bị từ chối. Đối với record chứa int[] trong chương trình học, accessor trả mảng có thể bị bên gọi sửa; trong API sản xuất, có thể copy phòng vệ hoặc trả cấu trúc bất biến để tránh vô tình thay đổi kết quả.

Lưu toàn bộ mã vào tệp **SequenceDpStates.java**:

~~~java
import java.util.Arrays;

public final class SequenceDpStates {
    public record LisResult(int length, int[] indices, int[] values) { }

    private SequenceDpStates() {
    }

    private static void requireArray(int[] a) {
        if (a == null) {
            throw new IllegalArgumentException("array must not be null");
        }
    }

    private static LisResult buildResult(int[] a, int[] previous,
                                         int last, int length) {
        int[] indices = new int[length];
        int[] values = new int[length];
        int at = last;
        for (int k = length - 1; k >= 0; k--) {
            indices[k] = at;
            values[k] = a[at];
            at = previous[at];
        }
        return new LisResult(length, indices, values);
    }

    public static LisResult lisEndingAt(int[] a) {
        requireArray(a);
        int n = a.length;
        int[] best = new int[n];
        int[] previous = new int[n];
        Arrays.fill(previous, -1);
        int longest = 0;
        int last = -1;

        for (int i = 0; i < n; i++) {
            best[i] = 1;
            for (int j = 0; j < i; j++) {
                if (a[j] < a[i] && best[j] + 1 > best[i]) {
                    best[i] = best[j] + 1;
                    previous[i] = j;
                }
            }
            if (best[i] > longest) {
                longest = best[i];
                last = i;
            }
        }
        return buildResult(a, previous, last, longest);
    }

    public static int lisPreviousState(int[] a) {
        requireArray(a);
        int n = a.length;
        int[][] memo = new int[n][n + 1];
        for (int[] row : memo) {
            Arrays.fill(row, -1);
        }
        return solve(a, 0, -1, memo);
    }

    private static int solve(int[] a, int position, int previousIndex,
                             int[][] memo) {
        if (position == a.length) {
            return 0;
        }
        int key = previousIndex + 1;
        if (memo[position][key] != -1) {
            return memo[position][key];
        }

        int skip = solve(a, position + 1, previousIndex, memo);
        int take = 0;
        if (previousIndex == -1 || a[previousIndex] < a[position]) {
            take = 1 + solve(a, position + 1, position, memo);
        }
        int result = Math.max(skip, take);
        memo[position][key] = result;
        return result;
    }

    public static LisResult lisBinarySearch(int[] a) {
        requireArray(a);
        int n = a.length;
        int[] tailIndex = new int[n];
        int[] previous = new int[n];
        Arrays.fill(previous, -1);
        int length = 0;

        for (int i = 0; i < n; i++) {
            int lo = 0;
            int hi = length;
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (a[tailIndex[mid]] < a[i]) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            int slot = lo;
            if (slot > 0) {
                previous[i] = tailIndex[slot - 1];
            }
            tailIndex[slot] = i;
            if (slot == length) {
                length++;
            }
        }
        return buildResult(a, previous,
                length == 0 ? -1 : tailIndex[length - 1], length);
    }

    public static long maxSumIncreasing(int[] a) {
        requireArray(a);
        if (a.length == 0) {
            throw new IllegalArgumentException("nonempty array required");
        }

        long[] best = new long[a.length];
        long answer = Long.MIN_VALUE;
        for (int i = 0; i < a.length; i++) {
            best[i] = a[i];
            for (int j = 0; j < i; j++) {
                if (a[j] < a[i]) {
                    best[i] = Math.max(best[i], best[j] + a[i]);
                }
            }
            answer = Math.max(answer, best[i]);
        }
        return answer;
    }

    private static int bruteLis(int[] a) {
        int result = 0;
        for (int mask = 1; mask < (1 << a.length); mask++) {
            int last = -1;
            int count = 0;
            boolean valid = true;
            for (int i = 0; i < a.length; i++) {
                if ((mask & (1 << i)) != 0) {
                    if (last >= 0 && a[last] >= a[i]) {
                        valid = false;
                        break;
                    }
                    last = i;
                    count++;
                }
            }
            if (valid) {
                result = Math.max(result, count);
            }
        }
        return result;
    }

    private static long bruteMaxSum(int[] a) {
        long best = Long.MIN_VALUE;
        for (int mask = 1; mask < (1 << a.length); mask++) {
            int last = -1;
            long sum = 0L;
            boolean valid = true;
            for (int i = 0; i < a.length; i++) {
                if ((mask & (1 << i)) != 0) {
                    if (last >= 0 && a[last] >= a[i]) {
                        valid = false;
                        break;
                    }
                    last = i;
                    sum += a[i];
                }
            }
            if (valid) {
                best = Math.max(best, sum);
            }
        }
        return best;
    }

    private static void checkWitness(int[] a, LisResult result,
                                     int expected) {
        if (result.length() != expected
                || result.indices().length != expected
                || result.values().length != expected) {
            throw new AssertionError("incorrect witness length");
        }
        int previousIndex = -1;
        for (int k = 0; k < expected; k++) {
            int i = result.indices()[k];
            if (i <= previousIndex || i < 0 || i >= a.length
                    || result.values()[k] != a[i]
                    || (k > 0 && result.values()[k - 1] >= a[i])) {
                throw new AssertionError("invalid witness");
            }
            previousIndex = i;
        }
    }

    private static void checkOne(int[] a) {
        int[] copy = a.clone();
        int expected = bruteLis(a);
        LisResult quadratic = lisEndingAt(a);
        LisResult fast = lisBinarySearch(a);
        if (lisPreviousState(a) != expected) {
            throw new AssertionError("top-down LIS mismatch");
        }
        checkWitness(a, quadratic, expected);
        checkWitness(a, fast, expected);

        if (a.length > 0 && maxSumIncreasing(a) != bruteMaxSum(a)) {
            throw new AssertionError("maximum-sum mismatch");
        }
        if (!Arrays.equals(a, copy)) {
            throw new AssertionError("input modified");
        }
    }

    private static void verify() {
        int[] alphabet = {-2, -1, 0, 1, 2};
        int checked = 0;
        for (int n = 0; n <= 6; n++) {
            int combinations = 1;
            for (int i = 0; i < n; i++) {
                combinations *= alphabet.length;
            }
            for (int code = 0; code < combinations; code++) {
                int[] a = new int[n];
                int remaining = code;
                for (int i = 0; i < n; i++) {
                    a[i] = alphabet[remaining % alphabet.length];
                    remaining /= alphabet.length;
                }
                checkOne(a);
                checked++;
            }
        }

        checkOne(new int[] {
            Integer.MAX_VALUE, Integer.MIN_VALUE, 0,
            Integer.MAX_VALUE
        });
        checkOne(new int[] {1, 2, 3, 4, 5, 6, 7});
        checkOne(new int[] {7, 6, 5, 4, 3, 2, 1});
        checkOne(new int[] {4, 4, 4, 4, 4});

        System.out.println("Verified " + checked + " generated arrays: PASS");
        System.out.println("Additional edge arrays: PASS");
    }

    public static void main(String[] args) {
        int[] a = {4, 1, 3, 2, 5};
        LisResult quadratic = lisEndingAt(a);
        LisResult fast = lisBinarySearch(a);

        System.out.println("LIS length = " + quadratic.length());
        System.out.println("LIS indices = "
                + Arrays.toString(quadratic.indices()));
        System.out.println("LIS values = "
                + Arrays.toString(quadratic.values()));
        System.out.println("Fast LIS length = " + fast.length());
        System.out.println("Fast LIS values = "
                + Arrays.toString(fast.values()));
        System.out.println("Previous-state length = " + lisPreviousState(a));
        System.out.println("Strict duplicates = "
                + lisEndingAt(new int[] {2, 2, 2}).length());
        System.out.println("Empty LIS length = "
                + lisEndingAt(new int[0]).length());
        System.out.println("Max-sum [9,1,2,3] = "
                + maxSumIncreasing(new int[] {9, 1, 2, 3}));
        System.out.println("Max-sum negatives = "
                + maxSumIncreasing(new int[] {-5, -2, -7}));

        verify();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SequenceDpStates.java
java SequenceDpStates
~~~

Đầu ra chính xác đã chạy kiểm chứng:

~~~text
LIS length = 3
LIS indices = [1, 2, 4]
LIS values = [1, 3, 5]
Fast LIS length = 3
Fast LIS values = [1, 2, 5]
Previous-state length = 3
Strict duplicates = 1
Empty LIS length = 0
Max-sum [9,1,2,3] = 9
Max-sum negatives = -2
Verified 19531 generated arrays: PASS
Additional edge arrays: PASS
~~~

Hai dòng LIS values và Fast LIS values khác nhau nhưng cùng có độ dài 3, là minh họa rằng bài toán cho phép **nhiều đáp án đúng tối ưu**. Một lời giải không được coi là sai chỉ vì nó không trùng chính xác chuỗi chỉ số của một lời giải khác.

## 16. Kiểm thử độc lập: không chỉ so sánh hai cách DP với nhau

Bộ verify sinh mọi mảng độ dài 0 tới 6 từ tập 5 giá trị {-2,−1,0,1,2}. Số mảng:

~~~text
5^0 + 5^1 + 5^2 + 5^3 + 5^4 + 5^5 + 5^6
= 1 + 5 + 25 + 125 + 625 + 3125 + 15625
= 19531 mảng.
~~~

Với mỗi mảng, chương trình:

1. Duyệt tất cả **tập con chỉ số** bằng bitmask (chỉ trên các n nhỏ) và lọc những tập con tạo dãy con tăng nghiêm ngặt, lấy độ dài lớn nhất làm oracle độc lập.
2. So sánh độ dài LIS của lisPreviousState với oracle.
3. Kiểm tra hai kết quả của lisEndingAt và lisBinarySearch có cùng độ dài tối ưu; đồng thời xác nhận chỉ số thuộc mảng, tăng theo thứ tự gốc và giá trị cũng tăng nghiêm ngặt.
4. Nếu mảng không rỗng, đối chiếu maxSumIncreasing với oracle duyệt tất cả dãy con tăng không rỗng rồi lấy tổng lớn nhất.
5. Xác nhận các hàm không làm đổi mảng đầu vào.

Sau đó có các mảng biên chứa Integer.MIN_VALUE và Integer.MAX_VALUE, đã tăng, đã giảm, toàn phần tử trùng nhau. Các phép thử **không** yêu cầu hai thuật toán khôi phục cùng danh sách chỉ số.

Chi phí oracle bitmask là **O(n2^n)** cho mỗi mảng nhỏ nếu quét n vị trí của từng mask; nó phục vụ xác minh, **không phải giải pháp đề xuất cho n lớn**. Dòng PASS chỉ phản ánh những ca đã chạy, không thay thế chứng minh quy nạp theo trạng thái.

## 17. Độ phức tạp của các phương án

| Thuật toán | Trạng thái / dữ liệu phụ | Chi phí chuyển hoặc tìm | Thời gian | Bộ nhớ phụ |
| --- | --- | --- | --- | --- |
| LIS theo dpEnd[i] | n trạng thái độ dài | Mỗi i xét tối đa i chỉ số trước | O(n²) | O(n) gồm best và previous |
| LIS theo (pos,prev) memo | O(n²) trạng thái hợp lệ | Skip/Take, mỗi chuyển O(1) | O(n²) | O(n²) memo + O(n) stack |
| LIS dùng đuôi + binary search | Tối đa n giá trị đuôi | Mỗi phần tử tìm nhị phân O(log n) | O(n log n) | O(n) cho tailIndex, previous |
| Tổng dãy con tăng lớn nhất | n trạng thái sumEnd | Mỗi i xét tối đa i chỉ số trước | O(n²) | O(n) |

Với DP kết thúc tại i, tổng số cặp j<i cần thử là 0+1+2+...+(n−1)=n(n−1)/2, giải thích cận O(n²). Truy vết O(n) không làm tăng bậc.

Với memo (pos,prev), mỗi trạng thái được tính một lần và mỗi lần có tối đa hai nhánh; bộ nhớ bảng vuông O(n²) có thể là vấn đề trước cả khi n đủ lớn để thời gian O(n²) trở nên không chấp nhận được.

Với cách đuôi, việc **thay thế đại diện** không phải là thao tác ghi đè bảng dpEnd. Ta đã dùng một invariant mới để bỏ phần lớn các lựa chọn j và chỉ giữ giá trị đuôi tối ưu cho mỗi độ dài; cần chứng minh riêng việc giữ đuôi nhỏ hơn không làm mất khả năng đạt một LIS dài hơn.

## 18. Những lỗi thường gặp khi chọn trạng thái và khôi phục lời giải

1. **Chỉ lưu độ dài prefix thay cho phần tử cuối.** Độ dài tốt nhất của tiền tố không đủ để biết có thể nối a[i] hay không.
2. **Nhầm dãy con với đoạn liên tiếp.** Chỉ kiểm tra a[i−1] trong LIS có thể bỏ lỡ một j hợp lệ xa hơn.
3. **Quên điều kiện j<i.** Chọn phần tử có vị trí sau rồi quay lại trước không còn là subsequence hợp lệ.
4. **Dùng ≤ thay vì <.** Dãy không giảm và dãy tăng nghiêm ngặt là hai bài toán khác nhau; [2,2,2] phát hiện lỗi ngay.
5. **Khởi tạo dpEnd[i]=0.** Dãy đơn phần tử kết thúc ở i đã có độ dài 1.
6. **Chỉ lấy dpEnd[n−1].** LIS tốt nhất có thể kết thúc trước phần tử cuối; phải lấy max qua mọi i.
7. **Không lưu previous khi cần dãy thực tế.** Một số độ dài không thể khôi phục trực tiếp thành chỉ số.
8. **Truy vết nhưng quên đảo thứ tự.** previous đi từ phần tử cuối về đầu.
9. **Không phân biệt sentinel −1 và dữ liệu âm.** Sentinel là chỉ số, không phải một giá trị trong mảng.
10. **Sai khóa memo:** dùng (pos,length) thay cho (pos,previousIndex) có thể gộp hai quá khứ có điều kiện nối khác nhau.
11. **Có memo nhưng base case sai.** F(n,prev)=0 vì không còn phần tử; không dùng F(n,prev)=1.
12. **Dùng upper bound cho LIS strict.** Với các phần tử bằng nhau, upper bound có thể đếm thêm bước không hợp lệ.
13. **Ghép trực tiếp mọi tailIndex hiện tại.** Các đại diện đuôi của những độ dài khác nhau không nhất thiết tạo thành cùng một chuỗi; phải dùng previous.
14. **Giả định hai LIS phải giống nhau.** Khi có nhiều nghiệm tối ưu, đúng đắn được quyết định bởi độ dài tối ưu và điều kiện chỉ số/giá trị.
15. **Đổi mục tiêu nhưng giữ trạng thái sai.** Độ dài LIS không đồng nghĩa tổng lớn nhất, nhất là khi có số âm hoặc giá trị lớn.
16. **Bỏ qua stack top-down.** O(n²) trạng thái không ngăn việc đệ quy có độ sâu O(n) gây StackOverflowError.
17. **Thay đổi mảng gốc khi khôi phục.** Nếu sắp xếp đầu vào trước khi tính LIS sẽ phá quan hệ thứ tự chỉ số của dãy con.
18. **Đánh giá chỉ bằng vài ví dụ thuận lợi.** Cần kiểm tra rỗng, trùng, tăng, giảm, số âm và cực trị int.

## 19. Quy trình thiết kế DP dãy theo phần tử cuối

Một checklist có thể áp dụng lại cho nhiều bài:

1. **Định nghĩa chính xác dãy được chọn:** liên tiếp hay không; thứ tự chỉ số; quan hệ <, ≤, > hay điều kiện khác.
2. **Xác định thông tin tối thiểu về quá khứ:** phần tử cuối, chỉ số cuối, số lần đổi hướng, giá trị tích lũy hoặc trạng thái ràng buộc.
3. **Nêu ý nghĩa một ô DP bằng câu đầy đủ:** không chỉ đặt tên dp[i], mà nói nó tối ưu cho những lời giải nào.
4. **Viết base case theo mục tiêu:** độ dài dãy đơn là 1, tổng dãy đơn là a[i], hậu tố đã hết có thể trả 0.
5. **Chỉ ra mọi tiền nhiệm hợp lệ:** với LIS là j<i và a[j]<a[i], hoặc Skip/Take theo (pos,prev).
6. **Chứng minh không bỏ sót và không tính sai:** mỗi lời giải hợp lệ tương ứng với một tiền nhiệm hợp lệ, và nối từ một nghiệm tối ưu con tạo được nghiệm hợp lệ.
7. **Chọn thứ tự tính:** i tăng cho dpEnd, hoặc pos tăng qua lời gọi và memo cho top-down.
8. **Tính cả công việc mỗi trạng thái:** n trạng thái quét tới n tiền nhiệm vẫn là O(n²).
9. **Thiết kế cách khôi phục:** lưu previous/choice ngay khi cập nhật, không cố đoán chuỗi chỉ từ độ dài.
10. **Nếu tối ưu, viết lại invariant:** phương án tails có bất biến “đuôi nhỏ nhất cho từng độ dài”, không đơn thuần là nén dpEnd.
11. **Kiểm thử bằng oracle nhỏ:** so độ dài, tính hợp lệ của chuỗi, chỉ số gốc và quy tắc strict/nondecreasing.
12. **Xem xét yêu cầu bổ sung:** thứ tự hòa, đếm số nghiệm, output nhiều dãy tối ưu, tràn số và bộ nhớ.

## 20. Bài tập tự luyện và câu hỏi kiểm tra

**Bài 1 — Lập bảng:** với a = [5,2,6,3,4,7], ghi dpEnd[i] và previous[i] tại từng vị trí. Tìm một LIS bằng truy vết. Giải thích vì sao không chỉ cần biết LIS dài nhất của tiền tố.

**Bài 2 — Đổi quan hệ:** thay yêu cầu tăng nghiêm ngặt bằng không giảm. Hãy sửa công thức dpEnd, điều kiện Take trong F(pos,prev) và cách binary search tails. Kiểm thử với [2,2,2] và [1,1,2].

**Bài 3 — Top-down có nhớ:** viết tay các trạng thái F(pos,prev) có thể được gọi với mảng [3,1,2]. Tách rõ hai nhánh Skip và Take, đánh dấu những bộ trạng thái lặp lại để hiểu lợi ích memoization.

**Bài 4 — Tổng lớn nhất:** với [9,1,2,3], tạo bảng sumEnd và so với dpEnd. Với [−5,−2,−7], chứng minh vì sao phải trả −2 thay vì 0 khi dãy không rỗng.

**Bài 5 — Khôi phục tails:** với [4,1,3,2,5], theo dõi tailIndex và previous sau mỗi lần cập nhật. Giải thích vì sao kết quả nhanh có thể là [1,2,5] còn kết quả O(n²) là [1,3,5].

**Bài 6 — Đếm số LIS:** mở rộng trạng thái dpEnd[i] bằng số dãy tối ưu kết thúc ở i. Nêu cách cộng số phương án khi hai j khác nhau cho cùng độ dài tối ưu, cách đếm các dãy theo **bộ chỉ số** và khi nào cần lấy modulo để tránh tràn số.

**Bài 7 — Phần tử cuối và hướng biến thiên:** thiết kế trạng thái cho dãy con *wiggle* (dấu hiệu của các hiệu giữa phần tử kề được chọn phải đổi từ dương sang âm hoặc ngược lại). Nêu vì sao chỉ lưu độ dài dãy con chưa đủ, cần nhớ hướng của bước cuối.

**Tự kiểm tra:** vì sao previous[i] là **chỉ số** chứ không chỉ là giá trị? Vì sao dpEnd[i] và F(pos,prev) có số trạng thái khác nhau nhưng cùng trả độ dài LIS? Tại sao giảm thời gian từ O(n²) xuống O(n log n) cần một bất biến mới về giá trị đuôi?

**Kết luận:** khi thiết kế quy hoạch động dãy, hãy tìm hiểu **điều gì của phần tử đã chọn cuối cùng còn ảnh hưởng đến lựa chọn tiếp theo**. Trạng thái kết thúc tại i giúp tính độ dài hoặc tổng tốt nhất cho mỗi điểm kết; trạng thái (pos,prev) mô tả trực tiếp quyết định lấy/bỏ. Lưu chỉ số tiền nhiệm cho phép khôi phục lời giải, còn bất biến đuôi nhỏ nhất mở đường cho thuật toán LIS nhanh hơn. Nắm được **ý nghĩa trạng thái → điều kiện nối → công thức chuyển → thứ tự tính → truy vết** quan trọng hơn học thuộc một công thức duy nhất.
