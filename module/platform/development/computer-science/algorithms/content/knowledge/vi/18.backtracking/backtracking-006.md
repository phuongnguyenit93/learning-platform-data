# Kiểm tra ràng buộc sớm để cắt nhánh

Trong **quay lui (backtracking)**, ta xây một lời giải từng bước, thử những lựa chọn có thể thực hiện, đi sâu vào một nhánh rồi hoàn tác để thử lựa chọn tiếp theo. Cách làm này rất tự nhiên cho xếp quân hậu, tìm tập con, tô màu đồ thị, sắp lịch có ràng buộc hay giải các câu đố. Tuy nhiên, nếu **đợi tới khi dựng xong cả lời giải mới kiểm tra hợp lệ**, chương trình sẽ tốn rất nhiều công sức khám phá những nhánh vốn đã chắc chắn không thể tạo ra đáp án đúng.

Một trong những kỹ thuật hiệu quả nhất là **kiểm tra ràng buộc sớm để cắt nhánh (early constraint checking / pruning)**: ngay khi một lời giải bộ phận không còn khả năng được mở rộng thành lời giải hợp lệ, dừng nhánh đó và trở lại thử lựa chọn khác. Điểm quan trọng nhất là **chứng minh nhánh bị bỏ thực sự vô vọng**. Cắt nhánh dựa trên phỏng đoán có thể làm chương trình chạy nhanh nhưng trả thiếu nghiệm, sai tối ưu hoặc sai số cách.

Bài học thuộc nhóm **Quay lui** của Computer Science Algorithms. Ta sẽ phân biệt kiểm tra hợp lệ tức thời và kiểm tra khả năng hoàn tất; làm rõ các bất biến trong cây tìm kiếm; so sánh bản kiểm tra muộn với bản kiểm tra sớm cho **N-Queens**; xây dựng **cận khả thi hai phía cho bài đếm tập con có tổng T** dù số âm xuất hiện; chứng minh tính đúng, phân tích giới hạn hiệu năng, triển khai Java 17+ và kiểm thử vét cạn độc lập.

## 1. Cấu trúc của một lời giải quay lui

Gọi state là một lời giải bộ phận đã cố định một số quyết định. Tại mỗi mức đệ quy, thuật toán làm bốn việc:

1. **Xác định lựa chọn tiếp theo:** đặt một quân hậu vào cột nào của hàng hiện tại, hoặc lấy/bỏ một phần tử của mảng.
2. **Kiểm tra ràng buộc liên quan:** lựa chọn mới có vi phạm điều kiện bất biến không; nếu chưa vi phạm, phần còn lại còn khả năng đạt mục tiêu không?
3. **Đi sâu:** cập nhật trạng thái, gọi đệ quy cho phần chưa xử lý.
4. **Hoàn tác:** đưa trạng thái về đúng giá trị trước khi thử lựa chọn để xét nhánh khác.

Một khung giả mã:

~~~text
search(state):
    nếu state đã chắc chắn không thể hoàn tất:
        return                       // cắt nhánh an toàn

    nếu state đã là lời giải hoàn chỉnh:
        nếu hợp lệ: ghi nhận lời giải
        return

    cho mỗi lựa chọn c:
        nếu c vi phạm điều kiện cục bộ bắt buộc:
            continue                 // không đi sâu nhánh này

        áp dụng c
        search(state sau c)
        hoàn tác c
~~~

Vị trí của kiểm tra phụ thuộc bài toán: có thể **trước khi áp dụng lựa chọn**, hoặc ngay **đầu hàm đệ quy** sau khi lựa chọn đã được áp dụng. Mẫu nào cũng được nếu mọi nhánh cần loại đều bị phát hiện và thao tác hoàn tác không làm hỏng nhánh khác.

**Điểm dễ nhầm:** chỉ vì trạng thái hiện tại chưa sai không có nghĩa nó chắc chắn hoàn tất được; ngược lại, khi một điều kiện **bắt buộc** đã vi phạm theo cách không thể sửa bởi phần tương lai, ta có quyền dừng ngay.

## 2. Phân biệt ba loại kiểm tra

| Loại kiểm tra | Câu hỏi | Phản ứng | Ví dụ |
| --- | --- | --- | --- |
| Hợp lệ cục bộ | Quyết định vừa thử đã xung đột với quyết định trước đó chưa? | Từ chối lựa chọn ngay | Hai quân hậu cùng đường chéo |
| Khả thi tương lai | Dù chưa xung đột, có còn cách nào thỏa mục tiêu cuối không? | Loại cả nhánh nếu cận chứng minh bất khả thi | Không thể đạt tổng T kể cả dùng tất cả số dương hoặc âm còn lại |
| Tối ưu hóa | Nhánh còn khả năng tốt hơn nghiệm tối ưu hiện có không? | Cắt khi cận tốt nhất của nhánh vẫn không cải thiện incumbent | Bài minimization có lower bound không nhỏ hơn best cost hiện có |

Loại thứ ba thường được gọi **branch and bound**, có điểm chung là cắt nhánh nhưng mục tiêu và chứng minh khác với chỉ kiểm tra hợp lệ. Bài này chủ yếu tập trung vào **đúng/sai và khả thi**, rồi giải thích cách mở rộng sang tối ưu.

Một điều kiện kiểm tra sớm hợp lệ phải thỏa:

> Nếu thuật toán loại state, **không tồn tại** một dãy lựa chọn hợp lệ từ state đó tới lời giải đầy đủ cần tính.

Đây là chiều quan trọng để **không làm mất đáp án**. Điều kiện cắt không cần phát hiện mọi trạng thái vô vọng; bỏ sót một số nhánh xấu chỉ ảnh hưởng tốc độ, không làm sai kết quả.

## 3. Thế nào là ràng buộc có tính duy trì qua quá trình mở rộng?

Một **vi phạm bền vững** là lỗi mà việc thêm quyết định sau không thể xóa đi. Ví dụ đã đặt hai quân hậu vào cùng một đường chéo thì thêm quân thứ ba không làm hai quân đầu hết xung đột. Vì vậy mọi nhánh chứa cặp xung đột đó đều vô hiệu.

Trái lại, không phải mọi đại lượng có vẻ “đang sai” đều là vi phạm bền vững. Chẳng hạn tổng các phần tử đã chọn hiện bằng 7, mục tiêu là 4, nhưng các phần tử còn lại có −3: ta vẫn có thể đạt 4. Điều kiện “currentSum > target” là **không an toàn** nếu dữ liệu có số âm.

Với bài cần đếm **tất cả** nghiệm, kiểm tra sớm phải giữ lại mọi nghiệm hợp lệ. Với bài chỉ cần **một nghiệm**, thuật toán có thể dừng ngay sau khi tìm thấy nghiệm, nhưng đó là **early termination do đạt mục tiêu**, không phải chứng minh các nhánh khác vô vọng. Với bài tối ưu, chỉ được bỏ nhánh khi có chứng minh nó không thể tạo lời giải tốt hơn theo hàm mục tiêu đã chọn.

## 4. Ví dụ 1 — Đặc tả N-Queens

Cho bàn cờ n×n. Cần đặt n quân hậu sao cho:

- Mỗi hàng có đúng một hậu.
- Mỗi cột có đúng một hậu.
- Không có hai quân nào trên cùng một đường chéo.

Ta sẽ **đếm số cách đặt** chứ không chỉ tìm một cách. Các quân hậu không được phân biệt danh tính; một cách đặt được xác định bằng cột của quân hậu ở từng hàng.

Đặt:

~~~text
columnAtRow[r] = cột đặt quân hậu của hàng r.
~~~

Ta đặt theo thứ tự hàng **r=0,1,...,n−1**. Như vậy điều kiện mỗi hàng có một hậu đã được cấu trúc tìm kiếm bảo đảm. Dùng usedColumn[c] để không chọn lại một cột đã dùng, nên điều kiện mỗi cột có một hậu cũng được bảo đảm ngay trong việc **sinh ứng viên**.

Còn lại ràng buộc đường chéo. Có hai chiến lược:

- **Kiểm tra muộn:** sinh hết các hoán vị cột không trùng, khi r=n mới kiểm tra toàn bộ đường chéo.
- **Kiểm tra sớm:** trước khi đặt quân vào (r,c), hỏi cặp đường chéo đi qua ô đó đã có hậu chưa. Nếu có, **bỏ ứng viên ngay**; nếu không, đặt rồi đệ quy.

Cả hai phải đếm đúng như nhau. Bản kiểm tra sớm chỉ thay đổi phần nào của cây tìm kiếm được khám phá, không thay đổi định nghĩa nghiệm.

## 5. Biểu diễn đường chéo để kiểm tra O(1)

Với tọa độ hàng r, cột c, hai họ đường chéo được xác định bởi:

~~~text
r - c = hằng số      (một hướng đường chéo)
r + c = hằng số      (hướng đường chéo kia)
~~~

Các giá trị r−c có thể âm, nên đổi về chỉ số mảng không âm:

~~~text
downIndex = r - c + n - 1
upIndex   = r + c
~~~

Với 0≤r,c<n và n≥1, cả hai chỉ số thuộc [0,2n−2]. Có thể lưu hai mảng boolean kích thước 2n−1:

- down[d] cho biết đã có hậu trên đường chéo r−c+n−1=d.
- up[u] cho biết đã có hậu trên đường chéo r+c=u.

Một ô (r,c) được chọn nếu đồng thời:

~~~text
usedColumn[c] == false
down[r-c+n-1] == false
up[r+c] == false
~~~

Khi đặt hậu, gán cả ba dấu thành true; khi hoàn tác, gán về false. Việc dùng mảng boolean thay vì so sánh vị trí mới với từng quân hậu trước đó giảm chi phí kiểm tra xung đột của một ứng viên từ O(r) xuống **O(1)**.

**Chú ý hai hiệu ứng khác nhau:** việc kiểm tra sớm giảm **số nhánh thực sự đi sâu**, còn mảng đánh dấu giúp giảm **chi phí kiểm tra mỗi ứng viên**. Đây là hai tối ưu riêng và đều cần tính trong phân tích thời gian.

## 6. So sánh hai cây tìm kiếm trên N-Queens

Ở bản kiểm tra muộn, mỗi hàng vẫn không được dùng lại cột cũ. Vì vậy các lá của cây là toàn bộ **n! hoán vị** của các cột. Ở lá, hàm kiểm tra đường chéo quét các hàng để quyết định có ghi nhận nghiệm hay không.

Ở bản kiểm tra sớm, ta không gọi đệ quy khi cột đã được dùng hoặc một đường chéo đã có hậu. Mọi nút đã đi sâu đều chứa một cách đặt bộ phận **không xung đột**. Điều này loại được nhiều nhánh trước khi tới lá.

Ví dụ với n=4, hai nghiệm có thể biểu diễn bằng các dãy cột:

~~~text
[1, 3, 0, 2]
[2, 0, 3, 1]
~~~

Dãy [1,3,0,2] có bàn cờ:

~~~text
. Q . .
. . . Q
Q . . .
. . Q .
~~~

Đường chéo hoặc cột bị đánh dấu từ các hàng trước đủ để đánh giá mỗi ô ở hàng tiếp theo. Nếu thử một ô trùng đường chéo, việc đặt thêm hậu về sau **không thể sửa** xung đột cũ, nên có thể cắt ngay.

**Trường hợp n=0:** ví dụ Java quy ước có **một cách đặt rỗng**, vì có đúng một dãy quyết định độ dài 0 thỏa mọi điều kiện. Với n=2 hoặc n=3 không có nghiệm. Hãy nêu rõ quy ước n=0 của API thay vì mặc định một nghĩa không có trong đề.

## 7. Bất biến của phiên bản N-Queens kiểm tra sớm

Ở đầu lời gọi search(row), khi đã đặt hậu cho các hàng 0..row−1:

1. Mỗi hàng đã xử lý có đúng một quân hậu.
2. Không có hai hàng đã xử lý dùng chung cột.
3. Không có hai quân hậu đã đặt cùng đường chéo r−c hoặc r+c.
4. usedColumn, down và up mô tả **đúng các cột và đường chéo** đang bị chiếm; những vị trí không bị chiếm có giá trị false.
5. Mọi hàng từ row tới n−1 chưa có hậu.

Bất biến đúng tại gốc vì chưa đặt quân nào. Khi thử cột c an toàn, đặt ba dấu true tạo trạng thái mới giữ cả năm điều kiện. Sau khi đệ quy về, hoàn tác ba dấu trả trạng thái của lời gọi hiện tại **đúng như trước lần thử**.

Khi row=n, tất cả n hàng đều có hậu và bất biến bảo đảm mọi ràng buộc đều đúng; không cần quét lại đường chéo ở lá. Vì vậy mỗi lời gọi lá của bản kiểm tra sớm tương ứng một nghiệm hợp lệ.

Một lỗi khó phát hiện là **quên hoàn tác một cờ**: nhánh sau sẽ bị đánh giá như thể vẫn tồn tại một quân hậu của nhánh trước, dẫn tới đếm thiếu nghiệm. Kiểm tra tính đối xứng giữa thao tác **mark** và **unmark** là một phần quan trọng của QA backtracking.

## 8. Chứng minh cắt nhánh N-Queens không mất nghiệm

Ta chứng minh cả hai chiều.

**Không nhận nghiệm sai (soundness):** bản kiểm tra sớm chỉ đặt hậu ở cột chưa dùng và trên hai đường chéo chưa bị chiếm. Theo bất biến, sau n hàng ta có một cấu hình hợp lệ. Mỗi cấu hình được sinh duy nhất bởi chuỗi lựa chọn cột theo các hàng, nên không đếm trùng từ việc hoán đổi thứ tự đặt các hàng.

**Không bỏ sót nghiệm (completeness):** xét một cấu hình N-Queens hợp lệ bất kỳ, với cột ở mỗi hàng là c_0,c_1,...,c_{n−1}. Ở hàng 0, c_0 là một lựa chọn không xung đột, nên nhánh tương ứng được duyệt. Giả sử nhánh đi đúng cấu hình tới hàng r−1, thì ô (r,c_r) không trùng cột hay đường chéo với các hậu trước vì cấu hình hoàn chỉnh vốn hợp lệ. Do đó thuật toán không cắt lựa chọn c_r và sẽ đi tới hàng r+1. Theo quy nạp, nhánh của cấu hình đó tới được lá.

Kết quả: bản kiểm tra sớm **đếm đúng tập nghiệm** của bản sinh hoán vị rồi kiểm tra ở lá; nó chỉ loại các tiền tố **không thể là tiền tố của một lời giải hợp lệ**.

Điều kiện đủ của chứng minh là **xung đột giữa hai quân đã đặt không thể biến mất khi thêm quân mới**. Điều này không phụ thuộc vào cách bố trí các hàng còn lại.

## 9. Đo hiệu quả bằng số nút, không chỉ thời gian đồng hồ

Chương trình Java đếm một **visitedNode** mỗi lần vào hàm đệ quy. Với n=8:

| Phiên bản | Số nút đệ quy đã thăm | Số nghiệm |
| --- | ---: | ---: |
| Chỉ kiểm tra đường chéo ở lá, sinh hoán vị cột | 109.601 | 92 |
| Kiểm tra đường chéo trước khi đệ quy | 2.057 | 92 |

Phiên bản kiểm tra sớm còn đếm **3.452 ứng viên cột còn trống nhưng bị từ chối do xung đột đường chéo**. Một ứng viên bị từ chối như thế không tạo lời gọi đệ quy mới, nên không nằm trong số visitedNode của bản tối ưu.

Với bản sinh hoán vị cột, tổng nút đệ quy đến hết độ sâu n có thể viết:

~~~text
visitedNodes(n) = sum_{r=0..n} P(n,r),
P(n,r) = n! / (n-r)!.

Với n=8:
1+8+56+336+1680+6720+20160+40320+40320 = 109601.
~~~

**Không được nói 109.601 là số lá:** số **lá** của bản sinh hoán vị là 8! = 40.320. 109.601 là tổng cả nút trong lẫn lá, bao gồm gốc.

Nút ít hơn thường là một dấu hiệu cải thiện mạnh, nhưng không luôn đồng nghĩa thời gian thực tế giảm theo đúng cùng tỉ lệ: mỗi phép kiểm tra cận có chi phí riêng, cache/JIT và thao tác đánh dấu khác nhau. Hãy đo cả **số nút, số kiểm tra, số lá hợp lệ và thời gian thực tế** nếu cần đánh giá hệ thống.

## 10. Độ phức tạp của N-Queens với sinh hoán vị cột

Một cách đặt n quân mỗi hàng một hậu và không trùng cột có n! phương án hoàn chỉnh. Số tiền tố độ dài r là P(n,r). Bản kiểm tra muộn đi qua toàn bộ các tiền tố này.

Trong mã minh họa:

- Mỗi nút chưa kết thúc duyệt c từ 0 tới n−1, nên có thể làm O(n) thao tác kiểm tra usedColumn ở nút đó.
- Bản kiểm tra muộn tại mỗi lá còn quét O(n) hậu để kiểm tra đường chéo.
- Tổng thời gian của cách sinh hoán vị và quét cột có **cận trên O(n·n!)** trong mô hình thao tác boolean/so sánh O(1); bản pruned không tệ hơn cận này nhưng có thể thăm ít nút hơn rất nhiều.
- Mảng columnAtRow, usedColumn và hai mảng đường chéo đều có kích thước O(n). Độ sâu stack tối đa O(n), do đó **bộ nhớ phụ O(n)** cho mỗi phiên bản.

Nếu đổi thuật toán sinh ứng viên, dùng bitmask, hoặc dùng một chiến lược tìm kiếm khác, cận và hằng số có thể thay đổi. Quan trọng nhất: **cắt nhánh là tối ưu hiệu năng trên cây tìm kiếm này, không phải chứng minh rằng bài toán N-Queens luôn giải được trong thời gian đa thức**.

Chương trình giới hạn n trong [0,10] để việc chạy ví dụ đối chiếu bằng hoán vị không kéo dài không kiểm soát; giới hạn đó thuộc **API trình diễn**, không phải định nghĩa toán học của N-Queens.

## 11. Ví dụ 2 — Đếm tập con có tổng đúng bằng target

Cho mảng int values[0..n−1] và số target kiểu long. Hãy **đếm số tập con của các vị trí** có tổng đúng target. Với mỗi phần tử ở vị trí i, có hai quyết định: **bỏ qua** hoặc **chọn**.

Ta xem hai phần tử cùng giá trị nhưng ở chỉ số khác nhau là **hai lựa chọn riêng biệt**. Ví dụ values=[0,0], target=0 có 4 tập con theo chỉ số: {}, {0}, {1}, {0,1}. Nếu đếm theo đa tập giá trị không phân biệt vị trí thì đó là bài toán khác.

Trạng thái đệ quy:

~~~text
search(i, currentSum)

i là chỉ số đầu tiên chưa quyết định.
currentSum là tổng những giá trị đã chọn ở các vị trí < i.

Nhánh 1: bỏ values[i]  -> search(i+1, currentSum).
Nhánh 2: lấy values[i] -> search(i+1, currentSum+values[i]).
Khi i=n: ghi một nghiệm nếu currentSum=target.
~~~

Bản kiểm tra ở lá duyệt **2^n tập con**, có 2^(n+1)−1 nút trong cây nhị phân đầy đủ. Nó rất đơn giản và dùng được làm **oracle** cho n nhỏ.

Bản tối ưu sẽ không sửa lựa chọn lấy/bỏ; nó sẽ đưa thêm một kiểm tra **khả năng đạt target từ những phần tử còn lại** để bỏ nhánh vô vọng sớm hơn.

## 12. Phản ví dụ: không thể cắt chỉ vì tổng hiện tại đã vượt target

Nếu tất cả values[i] đều không âm và chỉ cần đếm tập con có tổng đúng target≥0, thì khi currentSum>target, chọn thêm phần tử không thể làm tổng giảm: đó là một phép cắt an toàn.

Nhưng với **số âm**, lập luận này sai:

~~~text
values = [7, -3]
target = 4

Sau khi chọn 7:
currentSum = 7 > 4.
Nếu cắt ngay, ta bỏ mất nhánh hợp lệ lấy tiếp -3.

Tập con {7,-3} có tổng 4.
~~~

Tương tự, không được cắt chỉ vì currentSum<target khi vẫn còn số dương có thể được chọn. Một điều kiện pruning có vẻ “tự nhiên” chỉ an toàn sau khi đã xác nhận **giả thiết dữ liệu** khiến giá trị có tính đơn điệu.

Để không phụ thuộc vào dấu của các phần tử, ta xây **cận dưới và cận trên của mọi phần đóng góp có thể có trong tương lai**.

## 13. Tạo hai mảng cận phần còn lại

Khi đang ở trạng thái search(i, currentSum), ta chưa quyết định các phần tử từ i tới n−1. Mỗi phần tử có thể đóng góp **0 nếu bỏ** hoặc **values[k] nếu lấy**.

Do đó tổng đóng góp nhỏ nhất có thể từ các phần tử chưa xét (khi bỏ mọi số dương và lấy mọi số âm) là:

~~~text
minRest[i] = sum_{k=i..n-1} min(0, values[k]).
~~~

Tổng đóng góp lớn nhất có thể (khi lấy mọi số dương và bỏ mọi số âm) là:

~~~text
maxRest[i] = sum_{k=i..n-1} max(0, values[k]).
~~~

Hai mảng tính trong **O(n)** từ phải sang trái:

~~~text
minRest[n] = 0
maxRest[n] = 0

for i = n-1 ... 0:
    minRest[i] = minRest[i+1] + min(0, values[i])
    maxRest[i] = maxRest[i+1] + max(0, values[i])
~~~

Với trạng thái đã có currentSum, mọi tổng cuối cùng có thể đạt đều nằm trong đoạn:

~~~text
[currentSum + minRest[i], currentSum + maxRest[i]].
~~~

Vì vậy cắt ngay khi:

~~~text
target < currentSum + minRest[i]
HOẶC
target > currentSum + maxRest[i].
~~~

Đây là phép cắt **an toàn cho cả số âm, số 0 và số dương**. Hai cận đạt được riêng rẽ bằng một lựa chọn lấy/bỏ cụ thể; tuy nhiên không phải mọi số nguyên giữa hai cận đều nhất thiết đạt được. Điều kiện “target nằm trong khoảng” chỉ nói **chưa thể loại**, không chứng minh tồn tại một tập con.

## 14. Chứng minh phép cắt theo cận không bỏ nghiệm

Giả sử từ trạng thái (i,currentSum) có một cách chọn các phần tử chưa xét để đạt target. Mỗi phần tử chưa xét đóng góp hoặc 0 hoặc values[k].

Với mọi k:

~~~text
min(0, values[k]) <= đóng góp của k <= max(0, values[k]).
~~~

Cộng các bất đẳng thức qua mọi k từ i tới n−1:

~~~text
minRest[i] <= tổng đóng góp tương lai <= maxRest[i].
~~~

Cộng currentSum vào ba vế:

~~~text
currentSum+minRest[i]
   <= tổng cuối cùng
   <= currentSum+maxRest[i].
~~~

Nếu tổng cuối cùng phải bằng target, **target bắt buộc nằm trong khoảng đó**. Lấy phản chứng: nếu target nằm ngoài khoảng thì không có lựa chọn lấy/bỏ nào đưa tổng tới target, nên cắt nhánh không làm mất nghiệm.

Bản kiểm tra sớm vẫn xét **cả hai nhánh** tại những trạng thái chưa được chứng minh vô vọng. Khi i=n, hai cận phần còn lại bằng 0, nên chỉ trạng thái có currentSum=target được ghi nghiệm. Vì vậy không có nghiệm sai cũng không bỏ sót nghiệm đúng.

**Phân biệt cần/đủ:** thuộc khoảng là điều kiện **cần** để đạt target, không phải điều kiện **đủ**. Một phép cắt sound có thể yếu (bỏ qua vài nhánh vô vọng) nhưng vẫn chính xác.

## 15. Tính tay cận cho dữ liệu có cả số âm và số dương

Xét:

~~~text
values = [7, -3, 2, 5, -2]
target = 4
~~~

Nếu chọn phần tử đầu tiên 7, ta đến trạng thái i=1, currentSum=7. Các phần tử còn lại [-3,2,5,-2] có:

~~~text
minRest[1] = -3 + (-2) = -5
maxRest[1] = 2 + 5 = 7

Tổng cuối nằm trong [7-5, 7+7] = [2,14].
target=4 nằm trong khoảng, nên CHƯA được cắt.
~~~

Nếu sau đó **bỏ −3**, ta có i=2,currentSum=7, phần còn lại [2,5,-2]:

~~~text
minRest[2] = -2
maxRest[2] = 2+5 = 7

Tổng cuối phải nằm trong [7-2, 7+7] = [5,14].
target=4 nhỏ hơn 5, nên cắt nhánh tại đây là AN TOÀN.
~~~

Nếu chọn −3, tổng tạm thành 4 và còn các số [2,5,-2]. Không được dừng với một nghiệm ngay chỉ vì tạm bằng target: nếu cần **đếm mọi tập con**, còn những cách chọn/bỏ phần tử tiếp theo, kể cả các cặp bù nhau 2 và −2, có thể tạo thêm các tập con khác tổng 4.

Với dữ liệu trên, cả hai thuật toán trong mã Java đếm được **3 tập con theo chỉ số** có tổng 4. Bản duyệt hết thăm 63 nút của cây nhị phân đủ 5 quyết định; bản dùng cận chỉ thăm 31 nút.

## 16. Mẫu vòng đời trạng thái khi cắt theo cận

Giả mã cho phiên bản có cận:

~~~text
dfs(i, currentSum):
    nếu target < currentSum + minRest[i]:
        return
    nếu target > currentSum + maxRest[i]:
        return

    nếu i == n:
        ghi 1 nghiệm
        return

    dfs(i+1, currentSum)
    dfs(i+1, currentSum + values[i])
~~~

Điểm đặt kiểm tra **trước base case** giúp chính hai cận minRest[n]=maxRest[n]=0 xác định xem một lá có trúng target hay không. Đây là lựa chọn triển khai có chủ đích; đặt base case trước rồi kiểm tra currentSum==target ở lá cũng đúng.

Không cần một mảng boolean cho tập con nếu **chỉ đếm số nghiệm** và currentSum đủ để xác định kết quả. Nếu đề yêu cầu **in từng tập con**, cần lưu thêm danh sách chỉ số đã chọn hoặc một mảng take[i]; sau mỗi nhánh lấy phần tử, phải hoàn tác lựa chọn trước khi thử nhánh khác.

Số cách có thể lên tới 2^n. Chương trình minh họa giới hạn n≤20 và dùng long để đếm, nên nằm an toàn trong miền long. Với n lớn hơn, nếu cần đếm chính xác mọi nghiệm và số cách có thể vượt long, cần xem xét BigInteger hoặc modulo theo đặc tả.

## 17. Độ phức tạp của bài đếm tập con có cắt sớm

Bản leaf-only thực hiện đúng 2^n lá và **2^(n+1)−1 nút**, do đó thời gian Θ(2^n) và bộ nhớ stack O(n).

Bản dùng cận:

- Tiền xử lý minRest/maxRest: O(n) thời gian, O(n) bộ nhớ.
- Mỗi trạng thái thăm thực hiện O(1) phép cộng, so sánh và quyết định cắt.
- Nếu không cắt được nhánh nào, cây vẫn có thể có Θ(2^n) nút.
- Nếu cận loại được nhiều nhánh, thời gian thực tế có thể giảm đáng kể nhưng **không có bảo đảm giảm bậc độ phức tạp trường hợp xấu nhất**.
- Bộ nhớ phụ O(n) cho hai mảng cận và O(n) stack, không phải O(2^n), vì duyệt DFS và không lưu toàn bộ cây.

Ví dụ values toàn số 0, target=0: mọi nhánh đều có tổng cuối bằng 0; không thể cắt nhánh nào mà vẫn đếm đúng **2^n nghiệm** theo chỉ số. Với n=4 có 16 nghiệm. Đó là một ví dụ cho thấy **output/count bản chất lớn** khiến pruning không phải phép biến bài toán tổng quát thành đa thức.

Nên đánh giá hiệu quả cắt nhánh trên nhiều kiểu dữ liệu: số âm/dương xen kẽ, nhiều số 0, target nằm ngoài cận ngay từ gốc, target gần biên và target khó đạt nhưng vẫn nằm trong khoảng cận.

## 18. Ràng buộc cục bộ, cận khả thi và thứ tự thử lựa chọn

Có ba phương diện tối ưu độc lập:

**Kiểm tra cục bộ mạnh:** N-Queens dùng usedColumn và hai dấu đường chéo, loại xung đột ngay khi thử đặt hậu. Nếu có cấu trúc phù hợp, có thể kiểm tra trong O(1) thay vì duyệt tất cả quyết định trước.

**Cận tương lai hợp lệ:** bài tập con dùng hai tổng suffix cho phần còn lại. Một cận càng chặt thì càng dễ cắt, nhưng tính cận quá đắt có thể làm tốc độ tổng giảm. Luôn cân bằng công sức kiểm tra với số nhánh được cứu.

**Heuristic thứ tự duyệt:** thử lựa chọn nhiều khả năng hợp lệ trước, hoặc thử biến có ít giá trị hợp lệ nhất (MRV — minimum remaining values) trong các bài CSP. Thứ tự hợp lý thường giúp **tìm một nghiệm** sớm hơn; khi phải **đếm tất cả**, thay thứ tự không tự động thay số nghiệm, nhưng có thể thay khả năng phát hiện xung đột và hiệu quả của các cận bổ sung.

Heuristic chỉ quyết định **đi đâu trước**, không được xem là bằng chứng được **bỏ luôn các nhánh còn lại**. Muốn dừng hoặc loại các nhánh, vẫn cần điều kiện logic phù hợp với yêu cầu tìm một nghiệm, đếm tất cả hay tối ưu.

## 19. Tăng sức mạnh của kiểm tra sớm mà vẫn đúng

Trong N-Queens, sau khi đặt một phần quân hậu có thể xem trước những hàng chưa đi tới: nếu một hàng tương lai **không còn bất kỳ ô nào** thỏa cột/đường chéo với các hậu đã đặt, thì chắc chắn không có cách hoàn tất. Vì đặt thêm hậu chỉ **loại** thêm ô hợp lệ, nhánh đó có thể bị loại an toàn.

Tuy nhiên, việc mỗi hàng còn ít nhất một ô trống **không đủ** để bảo đảm có một cách đặt chung: các hàng có thể cần cùng một cột. Những thuật toán constraint programming mạnh hơn có thể dùng **forward checking** và **constraint propagation** để phát hiện bế tắc sớm hơn, đôi khi xét cả quan hệ all-different.

Trong subset-sum, các cận minRest/maxRest bỏ qua khả năng **không thể ghép đúng từng giá trị rời rạc**; do đó có thể yếu. Nếu tập giá trị nhỏ, có thể dùng DP khả đạt cho suffix để kiểm tra chính xác hơn, nhưng xây bảng trạng thái có thể tốn nhiều RAM/thời gian và không phù hợp khi miền tổng lớn.

**Nguyên tắc:** tăng độ mạnh của điều kiện cắt bằng một **suy luận đúng về mọi phần tiếp theo**, không bằng trực giác rằng “nhánh này có vẻ khó thắng”.

## 20. Trường hợp bài toán chỉ tìm một nghiệm hoặc cần tối ưu

Nếu cần **một nghiệm bất kỳ**, backtracking có thể trả về true ngay sau khi tìm thấy nghiệm. Đường tìm kiếm chưa xét không cần chứng minh vô vọng vì yêu cầu đã hoàn thành. Nhưng nếu báo “không có nghiệm”, phải chứng minh toàn bộ những nhánh còn lại đã được xét hoặc bị cắt an toàn.

Nếu cần **đếm tất cả nghiệm**, không được dừng khi thấy nghiệm đầu tiên. Phải đi hết mọi nhánh chưa bị loại bởi lý do logic.

Nếu cần **tối ưu** một giá trị f:

- Với minimization, giữ giá trị tốt nhất đã tìm được là incumbent.
- Với mỗi nhánh chưa hoàn tất, tính một **lower bound** LB mà mọi lời giải hoàn tất của nhánh đều phải có f≥LB.
- Nếu chỉ cần giá trị tối ưu và không cần tất cả nghiệm tối ưu, có thể cắt khi **LB≥incumbent**.
- Với maximization, dùng **upper bound** UB và cắt khi UB≤incumbent.

Nếu đề yêu cầu **liệt kê mọi nghiệm tối ưu**, điều kiện cắt khi bằng nhau phải xem lại: cắt ở LB=incumbent có thể bỏ những nghiệm tối ưu khác. Khi đó cần điều kiện nghiêm ngặt hơn hoặc xử lý đếm nghiệm hòa.

Đừng nhầm **cận khả thi** của subset-sum với **cận tối ưu** của branch and bound. Một cái chứng minh target không thể đạt; cái kia chứng minh nhánh không thể cải thiện mục tiêu.

## 21. Mã Java 17+ hoàn chỉnh có hai oracle độc lập

Chương trình **EarlyBacktrackingPruning.java** cài đặt bốn hàm công khai:

- queensLeafOnly(n): sinh **mọi hoán vị cột** rồi kiểm tra đường chéo chỉ tại lá.
- queensEarly(n): cùng cấu trúc hàng/cột nhưng **kiểm tra đường chéo trước khi đặt**, duy trì dấu cột và hai hướng đường chéo.
- subsetsLeafOnly(values,target): xét mọi nhánh lấy/bỏ, chỉ so tổng tại lá.
- subsetsEarly(values,target): tạo cận minRest/maxRest cho suffix rồi loại mọi state không thể đạt target.

Cả bốn trả record Stats(solutions,visitedNodes,rejected), cho phép phân biệt **đúng đắn (cùng số nghiệm)** và **hiệu năng tìm kiếm (số nút đã thăm)**. Ở queensEarly, rejected đếm ứng viên cột chưa dùng nhưng xung đột đường chéo trước khi đi sâu. Ở subsetsEarly, rejected đếm trạng thái đã vào đệ quy nhưng bị cận tương lai loại. Hai số rejected dùng cách đếm khác nhau; không so trực tiếp chúng với nhau.

Phiên bản N-Queens kiểm tra từ n=0 tới 10 để phù hợp ví dụ sinh hoán vị. Phiên bản tập con chấp nhận mảng không null với tối đa 20 phần tử, để oracle vét cạn còn dùng được trong môi trường học tập. Đây là **giới hạn API minh họa**, không phải giới hạn toán học của phương pháp.

Bài toán tập con dùng int[] cho dữ liệu và long cho tổng/target. Với n≤20 và mỗi số thuộc int, tổng tuyệt đối của bất cứ tập con nào nhỏ hơn miền long rất nhiều; các phép cộng và cận trong chương trình được biểu diễn chính xác. Đầu vào không bị thay đổi. N-Queens chỉ trả số nghiệm và thống kê, không lưu tất cả bàn cờ; nếu cần in các bàn cờ phải lưu cột từng hàng theo đường quay lui.

~~~java
import java.util.Arrays;

public final class EarlyBacktrackingPruning {
    public record Stats(long solutions, long visitedNodes, long rejected) { }

    private static final class Counter {
        long solutions;
        long nodes;
        long rejected;

        Stats snapshot() {
            return new Stats(solutions, nodes, rejected);
        }
    }

    private EarlyBacktrackingPruning() {
    }

    private static void checkQueensSize(int n) {
        if (n < 0 || n > 10) {
            throw new IllegalArgumentException("demo supports 0 <= n <= 10");
        }
    }

    public static Stats queensLeafOnly(int n) {
        checkQueensSize(n);
        Counter count = new Counter();
        int[] columnAtRow = new int[n];
        boolean[] usedColumn = new boolean[n];
        queensLeafDfs(0, columnAtRow, usedColumn, count);
        return count.snapshot();
    }

    private static void queensLeafDfs(int row, int[] columnAtRow,
                                      boolean[] usedColumn, Counter count) {
        count.nodes++;
        int n = columnAtRow.length;
        if (row == n) {
            if (diagonalsAreValid(columnAtRow)) {
                count.solutions++;
            }
            return;
        }
        for (int col = 0; col < n; col++) {
            if (!usedColumn[col]) {
                usedColumn[col] = true;
                columnAtRow[row] = col;
                queensLeafDfs(row + 1, columnAtRow, usedColumn, count);
                usedColumn[col] = false;
            }
        }
    }

    private static boolean diagonalsAreValid(int[] columnAtRow) {
        int n = columnAtRow.length;
        if (n == 0) {
            return true;
        }
        boolean[] down = new boolean[2 * n - 1];
        boolean[] up = new boolean[2 * n - 1];
        for (int row = 0; row < n; row++) {
            int col = columnAtRow[row];
            int d = row - col + n - 1;
            int u = row + col;
            if (down[d] || up[u]) {
                return false;
            }
            down[d] = true;
            up[u] = true;
        }
        return true;
    }

    public static Stats queensEarly(int n) {
        checkQueensSize(n);
        Counter count = new Counter();
        boolean[] usedColumn = new boolean[n];
        boolean[] down = new boolean[Math.max(0, 2 * n - 1)];
        boolean[] up = new boolean[Math.max(0, 2 * n - 1)];
        queensEarlyDfs(0, n, usedColumn, down, up, count);
        return count.snapshot();
    }

    private static void queensEarlyDfs(int row, int n, boolean[] usedColumn,
                                       boolean[] down, boolean[] up,
                                       Counter count) {
        count.nodes++;
        if (row == n) {
            count.solutions++;
            return;
        }
        for (int col = 0; col < n; col++) {
            if (usedColumn[col]) {
                continue;
            }
            int d = row - col + n - 1;
            int u = row + col;
            if (down[d] || up[u]) {
                count.rejected++;
                continue;
            }
            usedColumn[col] = true;
            down[d] = true;
            up[u] = true;
            queensEarlyDfs(row + 1, n, usedColumn, down, up, count);
            usedColumn[col] = false;
            down[d] = false;
            up[u] = false;
        }
    }

    private static void checkSubset(int[] values) {
        if (values == null || values.length > 20) {
            throw new IllegalArgumentException("demo needs nonnull n <= 20");
        }
    }

    public static Stats subsetsLeafOnly(int[] values, long target) {
        checkSubset(values);
        Counter count = new Counter();
        subsetsLeafDfs(values, 0, 0L, target, count);
        return count.snapshot();
    }

    private static void subsetsLeafDfs(int[] values, int i, long sum,
                                       long target, Counter count) {
        count.nodes++;
        if (i == values.length) {
            if (sum == target) {
                count.solutions++;
            }
            return;
        }
        subsetsLeafDfs(values, i + 1, sum, target, count);
        subsetsLeafDfs(values, i + 1, sum + values[i], target, count);
    }

    public static Stats subsetsEarly(int[] values, long target) {
        checkSubset(values);
        int n = values.length;
        long[] minRest = new long[n + 1];
        long[] maxRest = new long[n + 1];
        for (int i = n - 1; i >= 0; i--) {
            minRest[i] = minRest[i + 1] + Math.min(0, values[i]);
            maxRest[i] = maxRest[i + 1] + Math.max(0, values[i]);
        }
        Counter count = new Counter();
        subsetsEarlyDfs(values, 0, 0L, target, minRest, maxRest, count);
        return count.snapshot();
    }

    private static void subsetsEarlyDfs(int[] values, int i, long sum,
                                        long target, long[] minRest,
                                        long[] maxRest, Counter count) {
        count.nodes++;
        long lowest = sum + minRest[i];
        long highest = sum + maxRest[i];
        if (target < lowest || target > highest) {
            count.rejected++;
            return;
        }
        if (i == values.length) {
            count.solutions++;
            return;
        }
        subsetsEarlyDfs(values, i + 1, sum, target,
                minRest, maxRest, count);
        subsetsEarlyDfs(values, i + 1, sum + values[i], target,
                minRest, maxRest, count);
    }

    private static void verify() {
        long[] knownQueens = {1, 1, 0, 0, 2, 10, 4, 40, 92, 352};
        int queenCases = 0;
        for (int n = 0; n < knownQueens.length; n++) {
            Stats leaf = queensLeafOnly(n);
            Stats early = queensEarly(n);
            if (leaf.solutions() != knownQueens[n]
                    || early.solutions() != knownQueens[n]
                    || early.visitedNodes() > leaf.visitedNodes()) {
                throw new AssertionError("queens mismatch n=" + n);
            }
            queenCases++;
        }

        int[] alphabet = {-2, 0, 3};
        int subsetCases = 0;
        for (int n = 0; n <= 7; n++) {
            int combinations = 1;
            for (int i = 0; i < n; i++) {
                combinations *= alphabet.length;
            }
            for (int code = 0; code < combinations; code++) {
                int[] values = new int[n];
                int rest = code;
                for (int i = 0; i < n; i++) {
                    values[i] = alphabet[rest % alphabet.length];
                    rest /= alphabet.length;
                }
                int[] original = values.clone();
                for (int target = -5; target <= 5; target++) {
                    Stats leaf = subsetsLeafOnly(values, target);
                    Stats early = subsetsEarly(values, target);
                    if (leaf.solutions() != early.solutions()
                            || early.visitedNodes() > leaf.visitedNodes()) {
                        throw new AssertionError("subset mismatch: "
                                + Arrays.toString(values) + " t=" + target);
                    }
                    subsetCases++;
                }
                if (!Arrays.equals(values, original)) {
                    throw new AssertionError("input was modified");
                }
            }
        }

        if (subsetsEarly(new int[] {0, 0, 0, 0}, 0).solutions() != 16
                || subsetsEarly(new int[0], 0).solutions() != 1
                || subsetsEarly(new int[0], 1).solutions() != 0) {
            throw new AssertionError("zero and empty subset checks failed");
        }
        if (subsetsEarly(new int[] {
                Integer.MAX_VALUE, Integer.MIN_VALUE, 2}, 1).solutions()
                != subsetsLeafOnly(new int[] {
                Integer.MAX_VALUE, Integer.MIN_VALUE, 2}, 1).solutions()) {
            throw new AssertionError("integer extremes failed");
        }
        try {
            queensEarly(-1);
            throw new AssertionError("negative n was accepted");
        } catch (IllegalArgumentException expected) {
        }
        try {
            subsetsEarly(null, 0);
            throw new AssertionError("null input was accepted");
        } catch (IllegalArgumentException expected) {
        }

        System.out.println("Verified " + queenCases
                + " N-Queens sizes: PASS");
        System.out.println("Verified " + subsetCases
                + " subset cases: PASS");
        System.out.println("Edge cases and input validation: PASS");
    }

    public static void main(String[] args) {
        System.out.println("N-Queens(4) = "
                + queensEarly(4).solutions());
        Stats leafEight = queensLeafOnly(8);
        Stats earlyEight = queensEarly(8);
        System.out.println("N-Queens(8) leaf nodes = "
                + leafEight.visitedNodes());
        System.out.println("N-Queens(8) early nodes = "
                + earlyEight.visitedNodes());
        System.out.println("N-Queens(8) rejected candidates = "
                + earlyEight.rejected());
        System.out.println("N-Queens(8) solutions = "
                + earlyEight.solutions());

        int[] values = {7, -3, 2, 5, -2};
        Stats subsetLeaf = subsetsLeafOnly(values, 4);
        Stats subsetEarly = subsetsEarly(values, 4);
        System.out.println("Subset target 4 solutions = "
                + subsetEarly.solutions());
        System.out.println("Subset target 4 leaf nodes = "
                + subsetLeaf.visitedNodes());
        System.out.println("Subset target 4 early nodes = "
                + subsetEarly.visitedNodes());
        System.out.println("Subsets from empty array for target 0 = "
                + subsetsEarly(new int[0], 0).solutions());

        verify();
    }
}
~~~

Lưu tệp với tên đúng của lớp công khai:

~~~bash
javac EarlyBacktrackingPruning.java
java EarlyBacktrackingPruning
~~~

Stdout chính xác của chương trình:

~~~text
N-Queens(4) = 2
N-Queens(8) leaf nodes = 109601
N-Queens(8) early nodes = 2057
N-Queens(8) rejected candidates = 3452
N-Queens(8) solutions = 92
Subset target 4 solutions = 3
Subset target 4 leaf nodes = 63
Subset target 4 early nodes = 31
Subsets from empty array for target 0 = 1
Verified 10 N-Queens sizes: PASS
Verified 36080 subset cases: PASS
Edge cases and input validation: PASS
~~~

Chương trình đã được chạy trên Java có hỗ trợ cú pháp Java 17+ (record, class, mảng và đệ quy). Các dòng PASS là kết quả của các phép so sánh chạy thật, không phải thông báo mặc định khi không kiểm tra.

## 22. Kiểm thử tính đầy đủ của số nghiệm

**N-Queens:** chương trình so hai cách tìm kiếm cho n=0..9 với bảng số nghiệm đã biết:

~~~text
n                 0  1  2  3  4   5  6   7   8    9
số nghiệm         1  1  0  0  2  10  4  40  92  352
~~~

Mỗi n cần thỏa đồng thời:

1. queensLeafOnly(n).solutions trùng số nghiệm đã biết.
2. queensEarly(n).solutions trùng số nghiệm đó.
3. Số nút của bản cắt sớm **không lớn hơn** bản sinh hoán vị rồi kiểm tra ở lá.

Có **10 kích cỡ** được kiểm tra. Hai phiên bản không cần có số visitedNodes bằng nhau; chính sự khác nhau này phản ánh hiệu quả loại bỏ nhánh.

**Subset-sum:** chương trình sinh mọi mảng độ dài n=0..7 trên tập giá trị {-2,0,3}. Số mảng là:

~~~text
3^0 + 3^1 + ... + 3^7
= 1 + 3 + 9 + 27 + 81 + 243 + 729 + 2187
= 3280 mảng.
~~~

Với mỗi mảng thử tất cả target nguyên từ −5 tới 5 (11 giá trị), tổng số phép đối chiếu:

~~~text
3280 × 11 = 36080 trường hợp.
~~~

Mỗi trường hợp so số nghiệm của subsetsLeafOnly với subsetsEarly và kiểm tra số nút của bản cắt sớm không vượt bản không cắt. Bản oracle sinh đầy đủ các nhánh nhị phân và chỉ xét tổng ở lá, độc lập với công thức cận suffix của bản tối ưu.

Các ca biên bổ sung gồm: mảng rỗng/target=0 có một tập con rỗng; mảng rỗng/target khác 0 có không nghiệm; bốn số 0 tạo 16 tập con theo vị trí; các cực trị Integer.MAX_VALUE/Integer.MIN_VALUE; từ chối n âm với N-Queens hoặc input null với tập con.

**Giới hạn kiểm thử:** 10 kích cỡ N-Queens và 36.080 trường hợp tập con chỉ là một tập hữu hạn. Chúng hỗ trợ phát hiện bug triển khai; chứng minh ở mục 8 và 14 vẫn cần để đảm bảo cắt nhánh đúng trên toàn bộ đầu vào thuộc hợp đồng.

## 23. Những lỗi phổ biến khi kiểm tra ràng buộc sớm

1. **Cắt chỉ vì lời giải bộ phận chưa đạt mục tiêu.** Trong nhiều bài, các quyết định còn lại vẫn có thể bù thêm hoặc trừ đi phần thiếu/thừa.
2. **Giả sử mọi giá trị không âm.** Cắt currentSum>target khi có số âm là sai; [7,−3] với target=4 là phản ví dụ.
3. **Dùng cận sai chiều.** Muốn loại khi target nhỏ hơn min khả đạt hoặc lớn hơn max khả đạt, không phải loại khi target chỉ nằm ngoài một cận tùy ý.
4. **Nhầm cận cần với điều kiện đủ.** Target nằm giữa min và max không bảo đảm tồn tại tập con chính xác; vẫn phải tìm tiếp.
5. **Không giữ đúng tập phần tử còn lại.** minRest[i] và maxRest[i] chỉ tính từ chỉ số i tới n−1, không gồm các phần tử đã quyết định.
6. **Cắt trước khi ghi một nghiệm đã hoàn chỉnh mà không xét base case phù hợp.** Phải bảo đảm lá đúng target được ghi, lá sai không được ghi.
7. **Dừng khi thấy tổng bằng target trong bài đếm tất cả tập con.** Các phần tử 0 hoặc cặp bù dương/âm còn lại có thể tạo thêm nghiệm.
8. **Tính các phần tử trùng theo giá trị thay vì theo vị trí.** Nếu đề đếm tập con theo chỉ số, mỗi quyết định lấy/bỏ ở vị trí khác nhau là một khả năng riêng.
9. **Chỉ đánh dấu một họ đường chéo của N-Queens.** Cần cả r−c và r+c, ngoài cột đã dùng.
10. **Quên dịch r−c về chỉ số không âm.** Chỉ số âm gây lỗi mảng; phải cộng n−1.
11. **Quên hoàn tác khi quay lui.** Dấu dùng cột/đường chéo còn sót sẽ tạo xung đột giả trong nhánh khác.
12. **Đếm nhầm số node và số lá.** N-Queens n=8 có 40.320 lá hoán vị nhưng 109.601 nút nếu tính cả các tiền tố.
13. **Dùng một heuristic như chứng minh.** Thử lựa chọn có vẻ tốt trước không có nghĩa được bỏ những lựa chọn khác.
14. **Tối ưu theo một mục tiêu rồi so với mục tiêu khác.** Cận của bài minimization cần là lower bound thực, không phải giá trị ước lượng lạc quan thiếu chứng minh.
15. **Quên đo chi phí check.** Một phép kiểm tra nặng có thể làm tổng thời gian chậm hơn dù số nút giảm.
16. **Không xét miền số/overflow.** Cận tính sai vì tràn số có thể cắt mất nghiệm hợp lệ dù lập luận toán học đúng.
17. **Không bảo đảm input contract.** n âm, mảng null hoặc kích thước ngoài giới hạn demo phải được xử lý rõ ràng.
18. **Chỉ kiểm thử trường hợp có nghiệm.** Cần cả trường hợp vô nghiệm, nhiều nghiệm, một nghiệm rỗng và giá trị biên.
19. **Kết luận pruning luôn cho thời gian đa thức.** Trong trường hợp xấu, quay lui vẫn có thể duyệt cây kích thước hàm mũ hoặc giai thừa.

## 24. Quy trình áp dụng cắt nhánh an toàn cho bài mới

Có thể dùng checklist sau cho mọi bài quay lui:

1. **Xác định yêu cầu:** tìm một nghiệm, đếm mọi nghiệm, liệt kê tất cả hay tìm nghiệm tối ưu?
2. **Định nghĩa state:** những lựa chọn nào đã cố định, còn những biến nào chưa quyết định?
3. **Viết bất biến:** phần đã chọn luôn thỏa ràng buộc gì, dấu hoặc cấu trúc dữ liệu phụ đang mô tả điều gì?
4. **Liệt kê lựa chọn hợp lệ:** ứng viên nào vi phạm điều kiện không thể sửa ngay khi được đặt?
5. **Tìm cận tương lai:** với mọi cách hoàn tất, giá trị mục tiêu có nằm trong một miền bắt buộc không?
6. **Chứng minh chiều loại bỏ:** nếu kiểm tra nói “không thể”, tại sao mọi phần mở rộng đều không tạo lời giải?
7. **Đặt điểm cắt hợp lý:** trước khi đệ quy hoặc ngay đầu hàm; xử lý base case nhất quán.
8. **Hoàn tác đầy đủ:** mọi biến đánh dấu, tổng, danh sách lựa chọn và trạng thái tạm phải trở về giá trị cũ sau nhánh.
9. **Giữ thông tin để khôi phục:** nếu cần in lời giải, lưu quyết định đã chọn; nếu chỉ cần đếm, có thể giữ bộ đếm.
10. **So với oracle nhỏ:** bản thử tất cả không cắt là tham chiếu thuận tiện để phát hiện mất nghiệm.
11. **Đo số nút và chi phí kiểm tra:** xác minh tối ưu có cải thiện thực tế trên dữ liệu điển hình và biên.
12. **Phân tích worst-case:** trình bày trung thực rằng pruning có thể giảm lớn trong thực tế nhưng không tự động đổi hàm mũ thành đa thức.

**Một cách tự hỏi hiệu quả:** “Tôi có thể tạo một phản ví dụ chỉ với 2–4 quyết định trong đó kiểm tra này loại mất nghiệm không?”. Nếu có, điều kiện chưa đủ an toàn; cần siết giả thiết hoặc tìm cận chính xác hơn.

## 25. Bài tập tự luyện

**Bài 1 — Vẽ cây N-Queens nhỏ:** với n=4, đặt hậu theo hàng. Vẽ những ứng viên cột bị loại ở các mức đầu và tìm hai nghiệm [1,3,0,2], [2,0,3,1]. Giải thích mỗi lần cắt dựa trên xung đột cột hay đường chéo nào.

**Bài 2 — Bắt lỗi hoàn tác:** bỏ một câu lệnh unmark của mảng đường chéo trong queensEarly. Dùng bảng số nghiệm n=0..9 để tìm kích cỡ đầu tiên gây sai; giải thích vì sao trạng thái giữa hai nhánh bị nhiễm.

**Bài 3 — Tổng với số âm:** với values=[7,−3,2,5,−2], target=4, ghi minRest/maxRest tại mọi i, rồi vẽ một phần cây. Xác định nhánh bị loại bởi cận dưới và nhánh bị loại bởi cận trên.

**Bài 4 — Tập con nhiều số 0:** với values=[0,0,0,0], target=0, kiểm tra có 16 nghiệm theo chỉ số. Giải thích vì sao currentSum==target ở mức chưa tới n chưa đủ để dừng và đếm một nghiệm.

**Bài 5 — Thêm khả năng khôi phục:** mở rộng subsetsEarly để trả từng danh sách chỉ số tạo ra tổng target; bảo đảm kết quả phân biệt các phần tử trùng giá trị nhưng khác vị trí và danh sách lựa chọn được hoàn tác đúng.

**Bài 6 — Điều kiện không âm:** viết phép cắt currentSum>target cho phiên bản chỉ nhận toàn số không âm. So sánh với minRest/maxRest trong cùng miền dữ liệu; thử target âm, target=0 và mảng nhiều số 0.

**Bài 7 — Ràng buộc tương lai:** trong N-Queens, sau khi đặt một hậu, kiểm tra trước liệu có hàng tương lai nào không còn ô hợp lệ hay không. Chứng minh đây là **điều kiện cần** để hoàn tất, nhưng một ô hợp lệ ở mỗi hàng chưa phải điều kiện đủ.

**Bài 8 — Branch and bound:** với bài tối thiểu hóa tổng chi phí của một lịch, đề xuất lower bound cho phần chưa xếp. Chứng minh khi nào có thể cắt nếu lower bound bằng nghiệm tốt nhất đã biết và khi nào không được cắt vì đề cần **liệt kê mọi nghiệm tối ưu**.

**Tổng kết:** kiểm tra ràng buộc sớm là một trong những cách hiệu quả nhất để tăng tốc quay lui, nhưng **giá trị của nó phụ thuộc vào chứng minh an toàn**. N-Queens có xung đột cột/đường chéo không thể sửa được sau khi đặt; subset-sum có cận thấp nhất/cao nhất cho mọi tổng tương lai, kể cả khi dữ liệu có số âm. Chỉ nên bỏ một nhánh khi biết **không có phần mở rộng nào của nhánh đó góp được lời giải cần tìm**. Kết hợp bất biến, hoàn tác chính xác, oracle vét cạn và phép đo số nút sẽ biến một mẹo cắt nhánh thành một kỹ thuật có thể tin cậy.
