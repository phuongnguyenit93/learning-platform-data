# Kiểm tra trạng thái thừa, thiếu và phụ thuộc tạo chu trình

Trong **quy hoạch động (Dynamic Programming, DP)**, công thức chuyển trạng thái chỉ là một phần của lời giải. Trước đó phải thiết kế **trạng thái** sao cho nó ghi lại vừa đủ thông tin về bài toán con, và sau đó phải bảo đảm **các trạng thái được tính theo một quan hệ phụ thuộc hợp lệ**.

Ba nhóm lỗi đặc biệt dễ nhầm:

1. **Trạng thái thừa:** lưu một thông tin mà mọi quyết định tương lai và giá trị tối ưu không cần đến. Kết quả có thể vẫn đúng nhưng số lượng trạng thái, bộ nhớ và số phép chuyển tăng rất nhiều.
2. **Trạng thái thiếu:** gộp hai lịch sử khác nhau vào cùng một trạng thái mặc dù tập lựa chọn tiếp theo hoặc giá trị tối ưu của chúng khác nhau. Lời giải có thể nhanh nhưng **sai về mặt mô hình**.
3. **Phụ thuộc tạo chu trình:** các trạng thái cần giá trị của nhau trước khi có điểm bắt đầu hoặc một phương pháp giải phù hợp. Với DP thông thường tính một lần trên đồ thị phụ thuộc không chu trình, công thức hoặc thứ tự tính bị sai; chương trình đệ quy có thể không dừng.

Bài này nằm trong nhóm **Quy hoạch động** của Computer Science Algorithms. Mục tiêu là học cách **kiểm toán thiết kế trạng thái**, phân biệt đúng/sai bằng phản ví dụ, tìm thứ tự tính có chứng minh, phát hiện chu trình và lựa chọn cách sửa thích hợp.

## 1. Nhìn DP như một hệ các bài toán con

Một lời giải DP cần mô tả bốn thành phần:

- **Trạng thái `S`:** thông tin định danh một bài toán con, chẳng hạn `dp[i][s]` là có thể đạt tổng s với i phần tử đầu hay không.
- **Giá trị `dp[S]`:** câu trả lời cho bài toán con, có thể là boolean, số cách, chi phí nhỏ nhất, giá trị lớn nhất hoặc một cấu trúc khác.
- **Trạng thái cơ sở:** những bài toán con giải ngay được, không cần phụ thuộc chưa biết, ví dụ `dp[0][0]=true`.
- **Chuyển trạng thái:** công thức lấy lời giải của những bài toán con phù hợp để tạo lời giải bài toán lớn.

Để một công thức DP đúng, cần hai loại lập luận độc lập:

1. **Lập luận ngữ nghĩa:** những thông tin có trong trạng thái đủ để xác định các lựa chọn hợp lệ và đáp án của bài toán con; công thức chuyển xét đầy đủ các khả năng mà không dùng phần tử trái luật.
2. **Lập luận phụ thuộc:** các bài toán con được sử dụng trong chuyển đã được tính đúng trước khi cần dùng, hoặc được tính qua một cơ chế có bảo đảm kết thúc.

Một công thức có thể có thứ tự tính hoàn hảo mà vẫn sai vì **thiếu thông tin trạng thái**. Ngược lại, một trạng thái mô tả đúng bài toán con nhưng triển khai với thứ tự duyệt sai cũng có thể cho kết quả sai.

### Mô hình đồ thị phụ thuộc

Hãy xem mỗi trạng thái `S` là một **đỉnh**. Nếu tính `dp[S]` cần giá trị `dp[T]`, vẽ cạnh phụ thuộc:

~~~text
S  --->  T
cần    tiên quyết
~~~

Để tính một trạng thái theo phương pháp DP **mỗi trạng thái một lần**, trước hết cần có kết quả của tất cả đỉnh ở đầu kia của những cạnh phụ thuộc. Nếu đồ thị không có chu trình (DAG), luôn tồn tại **thứ tự tô pô (topological order)** để các trạng thái tiên quyết được xử lý trước.

Nếu đồ thị có chu trình, không thể dùng nguyên quy tắc “tính xong mọi tiền nhiệm rồi mới tính trạng thái hiện tại” cho các đỉnh nằm trong chu trình. Điều đó **không có nghĩa mọi bài toán chứa chu trình đều vô nghiệm**; nghĩa là phải xem lại công thức, ý nghĩa trạng thái hoặc chọn kỹ thuật giải phương trình/đồ thị phù hợp.

## 2. Trạng thái “đủ” nghĩa là gì?

Một trạng thái đủ nếu từ nó, ta biết **tập hành động tiếp theo được phép**, cách các hành động thay đổi bài toán, và phần giá trị còn cần tối ưu. Hai lịch sử khác nhau có thể dùng chung một trạng thái **chỉ khi chúng tương đương đối với phần tương lai cần tính**.

Một câu hỏi kiểm tra mạnh:

> Có thể tồn tại hai cách đi tới cùng một khóa trạng thái, nhưng từ đó những hành động hợp lệ hoặc giá trị tối ưu còn lại khác nhau không?

Nếu **có**, khóa trạng thái đang thiếu thông tin hoặc cần chứng minh thêm rằng những khác biệt không ảnh hưởng mục tiêu. Nếu **không**, ta có cơ sở để gộp các lịch sử nhằm tránh tính lại bài toán con tương đương.

### Ví dụ không cần lưu toàn bộ lịch sử

Trong bài **0/1 knapsack** thông thường, mỗi vật chỉ được lấy tối đa một lần, vật i có trọng lượng `w[i]` và giá trị `v[i]`, túi có sức chứa W. Nếu xử lý vật theo thứ tự, một trạng thái tự nhiên là:

~~~text
dp[i][capacity] = giá trị lớn nhất
                  khi chỉ dùng i vật đầu tiên
                  với tổng trọng lượng <= capacity
~~~

Ta không cần lưu toàn bộ danh sách những vật đã chọn. Vì các vật tương lai là nhóm từ i trở đi và điều kiện còn lại chỉ liên quan đến sức chứa, nhiều lịch sử có cùng i và capacity có thể dùng chung một bài toán con. Giá trị tốt nhất trong số chúng được giữ qua phép `max`.

Tuy nhiên, nếu xuất hiện **ràng buộc kề nhau** như “không được chọn hai vật có chỉ số liên tiếp”, việc chỉ nhìn `i` và sức chứa còn lại theo một mô hình chọn từ trái sang phải có thể **không đủ**: quyền chọn vật i phụ thuộc vật i−1 đã được chọn hay chưa. Ta cần bổ sung một bit như `previousTaken`, **hoặc** đổi sang công thức DP theo tiền tố có bước nhảy phù hợp để mã hóa ràng buộc một cách khác.

**Kết luận:** trạng thái đủ hay thiếu phụ thuộc **bài toán và định nghĩa công thức**. Một biến có thể thừa trong bài không ràng buộc, nhưng trở thành thiết yếu khi bổ sung điều kiện.

## 3. Trạng thái thừa: đúng nhưng làm bài toán phình to

Giả sử vẫn giải 0/1 knapsack tiêu chuẩn. Một người thiết kế:

~~~text
dp[i][capacity][lastChosen]
~~~

trong đó `lastChosen` là chỉ số vật đã chọn gần nhất. Nếu bài **không có ràng buộc** liên quan đến vật được chọn gần nhất, mọi quyết định về các vật tiếp theo chỉ phụ thuộc:
- Còn những vật nào chưa xét: đã biểu diễn bởi i.
- Còn bao nhiêu sức chứa: đã biểu diễn bởi capacity.

Trường `lastChosen` **không thay đổi tập hành động hợp lệ hoặc lợi ích tương lai**, nên việc tách nhiều trạng thái theo lastChosen chỉ lặp lại bài toán con tương đương.

### Hậu quả về độ phức tạp

Với n vật và sức chứa nguyên W:
- `dp[i][capacity]`: có tối đa **O(nW)** trạng thái.
- `dp[i][capacity][lastChosen]`: nếu lastChosen có O(n) khả năng, có thể tạo **O(n²W)** khóa trạng thái.

Không nhất thiết mọi tổ hợp ba chiều đều có thể đạt được; đây là cận kích thước miền trạng thái khi cài theo mảng/không nén. Nhưng chiều thừa vẫn có thể tăng chi phí rất mạnh.

### Quy trình kiểm tra một chiều có thừa không

1. Giữ cố định tất cả trường còn lại trong trạng thái.
2. Chọn **hai giá trị khác nhau** của trường đang nghi ngờ.
3. Xét xem các hành động từ hai trạng thái có khác nhau không.
4. Xét xem giá trị **bài toán con còn lại** có khác nhau không, không trộn với điểm/lợi ích đã tích lũy của quá khứ.
5. Nếu không có khác biệt cho **mọi trường hợp hợp lệ**, thử gộp và viết lại chuyển trạng thái.
6. Chứng minh việc gộp không loại mất nghiệm tốt nhất.

**Không được loại một chiều chỉ vì nó “trông không quan trọng”.** Nếu ràng buộc tương lai thực sự cần biết lastChosen, việc loại chiều ấy biến lỗi trạng thái thừa thành lỗi trạng thái thiếu.

### Thông tin quá khứ không phải lúc nào cũng thuộc khóa

Trong DP tối ưu hóa, **giá trị tốt nhất đã đạt** thường nằm trong `dp[state]`, không cần đưa cả tổng giá trị đã tích lũy thành một chiều của khóa trạng thái khi những quyết định tương lai chỉ phụ thuộc trạng thái hiện tại. Ghi cùng một thông tin cả trong khóa và trong giá trị có thể tạo nhiều trạng thái tương đương.

Một ngoại lệ: khi đề có ràng buộc **trên tổng giá trị** hay nhiều tài nguyên, tổng ấy có thể là một chiều trạng thái cần thiết. Quy tắc vẫn là xét ảnh hưởng đến **tập tiếp diễn hợp lệ** và **mục tiêu**, không máy móc bỏ mọi trường có tên `sum`.

## 4. Trạng thái thiếu: bỏ quên sự khác biệt quan trọng

Xét bài **subset sum 0/1**: mỗi vật/đồng có giá trị nguyên dương, chỉ được dùng **tối đa một lần**. Hỏi có chọn được một tập con có tổng đúng `target` hay không.

Ví dụ:

~~~text
Các vật: [3, 4] (mỗi vật chỉ có 1 bản sao)
target = 6

Tập con hợp lệ:
[]        -> 0
[3]       -> 3
[4]       -> 4
[3,4]     -> 7

Không có tập con tổng 6 -> đáp án FALSE.
~~~

Nếu chỉ viết một công thức đệ quy theo tổng:

~~~text
can(s) = can(s - 3) OR can(s - 4)
can(0) = true
~~~

thì `can(6)` có thể thành `can(3)=true`, rồi `can(3)` lại nhờ đồng 3. Kết quả **TRUE**, vì công thức đã dùng **cùng đồng 3 hai lần**. Công thức này phù hợp với bài **unbounded subset sum** cho phép dùng mỗi mệnh giá không giới hạn, chứ không đúng với bài 0/1.

**Lỗi không nằm ở thứ tự tính**: s giảm dần trong các lời gọi `can(s-v)`, nên không nhất thiết có chu trình. Lỗi là **trạng thái s không cho biết còn được sử dụng những vật nào**, dẫn tới xét một quyết định không hợp lệ.

### Bổ sung chỉ số vật

Một trạng thái đầy đủ và dễ chứng minh là:

~~~text
dp[i][s] = có thể đạt tổng s
           bằng một tập con của i vật đầu tiên hay không
~~~

Khởi tạo:
- `dp[0][0] = true`: không dùng vật nào tạo tổng 0.
- `dp[0][s] = false` với s>0: không thể tạo tổng dương nếu không có vật.
- Với s=0, `dp[i][0]=true` khi chỉ có các giá trị dương và cho phép chọn tập rỗng.

Chuyển với vật mới `value = a[i-1]`:

\[
dp[i][s] =
dp[i-1][s]\ \lor\
(s\ge value\ \land\ dp[i-1][s-value]).
\]

Hai nhánh là **không chọn vật i−1** hoặc **chọn vật i−1 đúng một lần**. Cả hai đều phụ thuộc vào **hàng i−1**, nên không tái sử dụng vật mới ở cùng hàng i.

Với [3,4] và target=6, trạng thái cuối `dp[2][6]` là false; còn `dp[2][7]` là true vì có thể chọn cả 3 và 4.

### Unbounded cần công thức khác

Nếu cho phép dùng giá trị `value` không giới hạn số lần, có thể dùng công thức theo các mệnh giá đã xét:

\[
unbounded[i][s] =
unbounded[i-1][s]\ \lor\
(s\ge value\ \land\ unbounded[i][s-value]).
\]

Điểm khác biệt là nhánh **chọn** phụ thuộc vào **cùng hàng i** với tổng nhỏ hơn. Nhờ đó có thể chọn lại cùng mệnh giá. Với toàn bộ giá trị dương, `s-value<s` nên có thứ tự tính hợp lệ theo s tăng dần.

Cả hai công thức có thể **không có chu trình**, nhưng mô hình cho **hai bài toán khác nhau**. Đây là ví dụ rõ nhất để thấy **đúng thứ tự tính chưa chắc đúng trạng thái**.

## 5. Nén 2D xuống 1D: chiều i có biến mất không?

Đối với subset sum 0/1, có thể dùng `boolean[] can` kích thước `target+1` và cập nhật theo từng vật.

~~~text
can[0] = true
can[s > 0] = false

for each value v:
    for s from target down to v:
        can[s] = can[s] OR can[s - v]
~~~

**Tại sao phải quét s từ lớn xuống nhỏ?** Khi xử lý vật hiện tại, mọi `s-v < s`. Với thứ tự **giảm dần**, ô `can[s-v]` vẫn còn chứa trạng thái của **hàng trước** (chưa bị vật hiện tại cập nhật). Do đó vật này không được dùng hai lần.

Ví dụ chỉ có một vật `v=3`, target=6:

| Thao tác | Quét giảm s=6→3 (0/1) | Quét tăng s=3→6 (unbounded) |
| --- | --- | --- |
| Ban đầu | can[0]=true, các ô khác false | Giống nhau |
| Kiểm tra s=6 | can[3] còn false → can[6]=false | Chưa xét s=6 |
| Xử lý s=3 | can[0]=true → can[3]=true | can[3]=true |
| Kiểm tra s=6 sau khi can[3] đổi | Đã đi qua s=6 → vẫn false | Đọc can[3] mới → can[6]=true |

Nếu **quét tăng từ nhỏ tới lớn** cho bài 0/1, `can[6]` có thể thấy giá trị `can[3]` vừa được cập nhật bởi **chính vật 3** trong lượt này. Thuật toán đã vô tình chuyển thành xử lý theo kiểu unbounded.

**Nén không có nghĩa chỉ số vật không còn quan trọng về ngữ nghĩa.** Chỉ số i được mã hóa bằng **giai đoạn của vòng ngoài** và quy tắc không ghi đè dữ liệu mà chuyển trạng thái đang cần. Nếu không có giai đoạn này, một công thức chỉ nhìn `s` có thể cho phép tái sử dụng vật không hợp lệ.

### Khi cần giữ 2D

Giữ `dp[i][s]` có thể tốt hơn nếu:
- Cần truy vết phương án bằng các hàng trước.
- Cần giải thích/kiểm chứng việc xử lý từng vật.
- Có thêm ràng buộc mà nén một chiều làm mất thông tin.
- Việc tối ưu bộ nhớ không quan trọng bằng sự rõ ràng và khả năng mở rộng công thức.

Chỉ nén khi đã chứng minh **các phụ thuộc cần cho cập nhật có thể được bảo toàn** trong thứ tự duyệt đã chọn.

## 6. Cách phát hiện thiếu trạng thái bằng “hai lịch sử giống khóa”

Một phương pháp thực tế là tạo hai lịch sử khác nhau cho **cùng khóa trạng thái dự định**, sau đó tìm một lựa chọn mà lịch sử này cho phép còn lịch sử kia không cho phép.

Ví dụ với bài “chọn số có tổng không vượt W, nhưng **không được chọn hai phần tử kề nhau**”:
- Ta đang đứng ở vị trí i, còn sức chứa R.
- Lịch sử A vừa chọn phần tử i−1.
- Lịch sử B không chọn phần tử i−1.
- Cả hai có thể cùng i và R nếu đã chọn những phần tử khác nhau có tổng trọng lượng như nhau.
- Nhưng tại i, lịch sử A **không được chọn**, còn lịch sử B **có thể chọn**.

Nếu khóa chỉ là `(i,R)` trong một công thức quyết định tiến từ trái sang phải, hai lịch sử ấy bị gộp nhầm. Bổ sung `previousTaken` hoặc thiết kế công thức thay thế dựa trên những bước nhảy loại phần tử liền kề.

### Không phải cứ thiếu “last” là sai

Một cách đặt DP theo tiền tố có thể dùng:

\[
best[i]=\max(best[i-1], best[i-2]+value_i)
\]

để chọn các phần tử **không kề nhau** nhằm tối đa tổng giá trị, với quy ước giá trị và cơ sở đúng. Công thức này **không lưu previousTaken**, vì nhánh chọn phần tử i **tự chuyển tới i−2**, mã hóa điều kiện không kề nhau ngay trong phụ thuộc.

Vậy cùng ràng buộc nhưng có thể có **nhiều cách biểu diễn trạng thái đúng**. Câu hỏi đúng không phải “luôn cần bit previousTaken?”, mà là “công thức cụ thể đã mã hóa điều kiện trước đó ở đâu?”.

### Checklist thiết kế đủ trạng thái

Với mỗi chuyển trạng thái, hãy hỏi:
- Lựa chọn tiếp theo phụ thuộc vào **mốc nào đã xử lý**?
- Có nguồn lực còn lại như sức chứa, thời gian, số bước, ngân sách hay số lần dùng không?
- Có cần biết **phần tử trước**, tập phần tử đã dùng, hoặc điều kiện đang bật/tắt?
- Có hai lịch sử khác nhau gộp vào cùng khóa nhưng **có tập hành động hợp lệ khác nhau** không?
- Với hai lịch sử cùng khóa, phần lợi ích còn lại có thể khác nhau theo dữ liệu quá khứ không?
- Mọi lựa chọn hợp lệ có được công thức chuyển bao phủ, và mọi lựa chọn công thức sinh ra đều hợp lệ không?

Nếu không trả lời được, đừng vội tối ưu bộ nhớ hoặc chuyển sang triển khai.

## 7. Phụ thuộc tạo chu trình: vì sao memoization có thể lặp mãi?

Xét một DP giả định:

~~~text
dp[0] = 1
dp[1] = dp[2] + 1
dp[2] = dp[1] + 1
~~~

Đồ thị phụ thuộc có:

~~~text
dp[1] ---> dp[2]
  ^            |
  |____________|
~~~

Để biết dp[1], phải biết dp[2]; để biết dp[2], lại phải biết dp[1]. Đó là **chu trình phụ thuộc**. Hai phương trình thực tế còn mâu thuẫn với nghiệm hữu hạn vì nếu trừ nhau sẽ cho 0=2; việc chỉ viết hàm đệ quy không thể giải chúng.

### Vòng đệ quy sai điển hình

~~~text
solve(1):
    return solve(2) + 1

solve(2):
    return solve(1) + 1
~~~

Nếu chỉ đánh dấu `memo[state]` **sau khi đã giải xong**, cả hai giá trị đều chưa được đánh dấu. Hai lời gọi cứ gọi qua lại cho tới khi tràn stack.

**Phân biệt:** chưa tính, đang tính và đã tính là **ba trạng thái khác nhau** của bộ nhớ hóa. Nếu chỉ có cờ `computed=true/false`, không phải lúc nào cũng phát hiện được trường hợp đang nằm trên ngăn xếp đệ quy. Vì vậy thường dùng kỹ thuật **3 màu**:
- `WHITE/0`: chưa thăm.
- `GRAY/1`: đang trên đường DFS hiện tại, chưa hoàn thành.
- `BLACK/2`: đã tính xong và có thể dùng memo.

Nếu DFS cần một đỉnh đang **GRAY**, đồ thị phụ thuộc có **chu trình trên nhánh đang xét**.

### Tự phụ thuộc cũng là chu trình

Công thức `dp[i] = dp[i] + 1` mà không có ý nghĩa giải phương trình riêng tạo cạnh **i→i** và là chu trình độ dài 1. Lỗi có thể đến từ:
- Bước chuyển không làm giảm bài toán, ví dụ dùng một thao tác có độ dài **0** trong bài đếm cách có thể lặp vô hạn.
- Viết sai chỉ số `dp[i]` thay vì `dp[i-1]`.
- Tự gọi `solve(state)` với **đúng các đối số cũ** trong nhánh đệ quy.

Tuy nhiên không phải mọi phép gán dạng `dp[s] = dp[s] + ...` trong **DP lặp** đều là một phương trình đệ quy vô nghĩa. Nó có thể là cú pháp **cập nhật một giá trị đã biết qua các giai đoạn**, chẳng hạn `can[s] |= can[s-v]`, và phải phân tích **thời điểm đọc/ghi** riêng. Không thể chỉ dựa vào ký hiệu có `dp` ở cả hai phía để kết luận chu trình.

## 8. DAG, thứ tự tô pô và “hàm đo tiến triển”

Để dùng **bottom-up DP** một lần mỗi trạng thái, các trạng thái phụ thuộc phải được tính trước.

Ví dụ:

~~~text
f[0] = 1
f[1] = f[0]
f[i] = f[i-1] + f[i-2], với i >= 2
~~~

Đồ thị phụ thuộc của f[i] chỉ trỏ tới chỉ số **nhỏ hơn i**, nên duyệt `i=0,1,2,...` là thứ tự hợp lệ. Có thể coi **i là thước đo tiến triển**: mọi phụ thuộc đều làm i giảm.

Tương tự:
- DP theo tiền tố thường phụ thuộc hàng `i-1`, nên duyệt i tăng.
- DP đếm cách trên tổng với **bước dương** có thể phụ thuộc tổng nhỏ hơn, nên duyệt s tăng.
- DP theo hai chỉ số `(i,j)` có thể dùng thứ tự từ điển nếu mọi cạnh phụ thuộc đều dẫn tới trạng thái sớm hơn.
- DP trên đồ thị DAG dùng một **topological order** theo các cạnh từ điều kiện tiên quyết tới trạng thái cần tính.

### Một chứng minh kết thúc đơn giản

Hãy định nghĩa một **hàm thứ hạng** `rank(S)` nhận giá trị nguyên không âm hoặc một tập có thứ tự tốt. Nếu **mọi phụ thuộc đệ quy** từ S tới T đều có `rank(T)<rank(S)`, thì không thể có chu trình: đi quanh một chu trình sẽ đòi hỏi hạng giảm nghiêm ngặt rồi quay về giá trị ban đầu, điều bất khả thi.

Nhưng chỉ nói “mỗi bước làm số lượng giảm” là chưa đủ nếu có nhánh **giữ nguyên** hoặc **tăng lại** một tham số khác. Phải xét **mọi nhánh phụ thuộc** và thứ tự tổng thể. Với trạng thái hai chiều, có thể dùng thứ tự từ điển hoặc một đại lượng tổng hợp chỉ khi chứng minh được nó giảm trên từng cạnh.

### Đọc đúng hướng cạnh

Trong tài liệu này, `S → T` nghĩa là **S cần T**. Để tính bottom-up, T phải được xử lý **trước** S. Một số thư viện đồ thị lại lưu cạnh theo chiều **T → S** để chạy Kahn và đếm indegree; điều đó chỉ là cách biểu diễn khác. Nếu nhầm hướng, ta có thể tạo một thứ tự tô pô nhìn hợp lệ nhưng đánh giá các trạng thái trước khi có giá trị tiền nhiệm.

## 9. Kiểm toán đồ thị trạng thái như một DAG

Khi số trạng thái hữu hạn và có thể liệt kê phụ thuộc, ta có thể kiểm toán:

1. **Tính đầy đủ:** mọi phụ thuộc T của trạng thái S đều có định nghĩa hoặc thuộc miền cơ sở hợp lệ.
2. **Tính đạt được:** xét những trạng thái thực sự cần để tính đáp án. Một trạng thái không thể đạt có thể bỏ khỏi quá trình tính, nhưng phải chứng minh nó không cần cho đáp án.
3. **Tính không chu trình:** DFS với 3 màu hoặc thuật toán Kahn; thành phần liên thông mạnh (SCC) có từ hai đỉnh trở lên hoặc tự khép có chu trình.
4. **Thứ tự đánh giá:** từ một thứ tự phụ thuộc hợp lệ, mọi T được tính trước S.
5. **Tính ngữ nghĩa:** mỗi cạnh và công thức tính đúng đối với định nghĩa bài toán con; một DAG sai ngữ nghĩa vẫn có thể cho kết quả sai.
6. **Tính tràn số:** đếm cách có thể lớn hơn `long`, hoặc giá trị `INF` có thể tràn khi cộng; tránh nhầm lỗi số học với lỗi phụ thuộc.

**Lưu ý phạm vi:** một DFS bắt đầu từ **trạng thái đáp án** chỉ phát hiện các lỗi trên **đồ thị con mà đáp án phụ thuộc**. Chu trình nằm trong phần hoàn toàn không được tham chiếu có thể chưa lộ. Nếu mục tiêu là kiểm tra **toàn bộ bảng định nghĩa trạng thái**, cần duyệt mọi đỉnh; nếu chỉ cần bảo đảm việc giải truy vấn cụ thể, thường chỉ cần phần đạt được từ truy vấn đó.

### Phân biệt phụ thuộc chưa định nghĩa và chu trình

- **Thiếu định nghĩa:** công thức `f[2]` cần `f[8]` nhưng không có trạng thái 8 trong miền hợp lệ. Đây là lỗi về **miền và cơ sở**.
- **Chu trình:** trạng thái 1 được định nghĩa và cần 2; trạng thái 2 được định nghĩa và cần lại 1. Không thiếu tên trạng thái, nhưng không có thứ tự tính một lần theo các cạnh ấy.
- **Giá trị không thể đạt:** với bài tối ưu, có thể có trạng thái hợp lệ nhưng không có nghiệm. Khi đó nên gán giá trị logic như `-INF`, `INF` hoặc `false`, **không kết luận trạng thái chưa được định nghĩa**.
- **Giá trị bằng 0:** số cách bằng 0 hay lợi ích tối ưu bằng 0 vẫn là kết quả hợp lệ, không được dùng 0 làm dấu “chưa tính” nếu 0 có thể là đáp án.

Những trường hợp này phải được xử lý **khác nhau** khi thiết kế memo và thông báo lỗi.

## 10. Java 17 hoàn chỉnh: kiểm tra phụ thuộc, chu trình và lỗi mất giai đoạn

Chương trình độc lập dưới đây thực hiện hai phần:

**Phần A — kiểm toán đồ thị phụ thuộc:** mỗi trạng thái u có một danh sách các trạng thái tiên quyết. Để ví dụ tự chứa, giá trị của u được định nghĩa là:

~~~text
dp[u] = base[u] + SUM(dp[v]) với mọi v trong dependencies[u].
~~~

Đó là một **hệ truy hồi minh họa trên DAG**, không phải công thức chung cho mọi DP. Khi `dependencies[u]` rỗng, `dp[u]=base[u]`. DFS dùng cờ 0/1/2, phát hiện **phụ thuộc ngoài miền** và **back edge tạo chu trình**, đồng thời memo hóa kết quả.

**Phần B — subset sum 0/1:** dùng quét s **giảm dần** để đảm bảo mỗi giá trị đầu vào được dùng tối đa một lần. Hàm thứ hai quét s **tăng dần** để minh họa bài unbounded khác mục tiêu; so hai hàm trên ví dụ [3,4] với target 6.

~~~java
import java.util.Arrays;

public class DpStateAuditDemo {
    static class GraphDp {
        private final int[][] dependencies;
        private final long[] base;
        private final long[] memo;
        // 0=chua tham, 1=dang tinh, 2=da tinh.
        private final byte[] color;

        GraphDp(int[][] dependencies, long[] base) {
            if (dependencies == null || base == null
                    || dependencies.length != base.length) {
                throw new IllegalArgumentException(
                        "Invalid state definitions");
            }
            this.dependencies = dependencies;
            this.base = base;
            this.memo = new long[base.length];
            this.color = new byte[base.length];
        }

        long value(int state) {
            if (state < 0 || state >= base.length) {
                throw new IllegalArgumentException(
                        "undefined state " + state);
            }
            if (color[state] == 1) {
                throw new IllegalStateException(
                        "cycle at state " + state);
            }
            if (color[state] == 2) {
                return memo[state];
            }
            if (dependencies[state] == null) {
                throw new IllegalArgumentException(
                        "undefined recurrence for " + state);
            }

            color[state] = 1;
            long result = base[state];
            for (int dep : dependencies[state]) {
                result = Math.addExact(result, value(dep));
            }
            memo[state] = result;
            color[state] = 2;
            return result;
        }
    }

    // Mỗi phần tử chỉ được dùng tối đa một lần.
    static boolean subset01(int[] items, int target) {
        if (items == null || target < 0) {
            throw new IllegalArgumentException("Invalid input");
        }
        boolean[] can = new boolean[target + 1];
        can[0] = true;

        for (int value : items) {
            if (value <= 0) {
                throw new IllegalArgumentException(
                        "Item must be positive");
            }
            if (value > target) {
                continue;
            }
            for (int sum = target; sum >= value; sum--) {
                can[sum] = can[sum] || can[sum - value];
            }
        }
        return can[target];
    }

    // Mỗi mệnh giá được phép dùng không giới hạn lần.
    static boolean subsetUnbounded(int[] items, int target) {
        if (items == null || target < 0) {
            throw new IllegalArgumentException("Invalid input");
        }
        boolean[] can = new boolean[target + 1];
        can[0] = true;

        for (int value : items) {
            if (value <= 0) {
                throw new IllegalArgumentException(
                        "Item must be positive");
            }
            if (value > target) {
                continue;
            }
            for (int sum = value; sum <= target; sum++) {
                can[sum] = can[sum] || can[sum - value];
            }
        }
        return can[target];
    }

    // Oracle vét cạn: chỉ dùng trên mảng n nhỏ.
    static boolean brute01(int[] items, int target) {
        int n = items.length;
        if (n > 20) {
            throw new IllegalArgumentException("Too many items");
        }
        for (int mask = 0; mask < (1 << n); mask++) {
            long sum = 0;
            for (int i = 0; i < n; i++) {
                if ((mask & (1 << i)) != 0) {
                    sum += items[i];
                }
            }
            if (sum == target) {
                return true;
            }
        }
        return false;
    }

    static int verifySmall01() {
        int checked = 0;

        // Sinh mọi mảng độ dài 0..5 trên giá trị {1,2,3}.
        for (int n = 0; n <= 5; n++) {
            int patterns = 1;
            for (int i = 0; i < n; i++) {
                patterns *= 3;
            }

            for (int code = 0; code < patterns; code++) {
                int remaining = code;
                int[] items = new int[n];
                for (int i = 0; i < n; i++) {
                    items[i] = 1 + remaining % 3;
                    remaining /= 3;
                }

                for (int target = 0; target <= 12; target++) {
                    boolean actual = subset01(items, target);
                    boolean expected = brute01(items, target);
                    if (actual != expected) {
                        throw new AssertionError(
                            "items=" + Arrays.toString(items)
                            + " target=" + target);
                    }
                    checked++;
                }
            }
        }
        return checked;
    }

    public static void main(String[] args) {
        // dp[0]=1, dp[1]=dp[0],
        // dp[i]=dp[i-1]+dp[i-2] khi i>=2.
        int[][] dagDependencies = {
            {}, {0}, {0, 1}, {1, 2}, {2, 3}, {3, 4}
        };
        long[] dagBase = {1, 0, 0, 0, 0, 0};
        System.out.println("dagState5="
                + new GraphDp(dagDependencies, dagBase).value(5));

        // Trạng thái 1 cần trạng thái 3, nhưng chỉ có 0 và 1.
        try {
            new GraphDp(new int[][]{{}, {0, 3}},
                    new long[]{1, 0}).value(1);
        } catch (IllegalArgumentException e) {
            System.out.println("missing=" + e.getMessage());
        }

        // Hai trạng thái phụ thuộc lẫn nhau.
        try {
            new GraphDp(new int[][]{{1}, {0}},
                    new long[]{0, 0}).value(0);
        } catch (IllegalStateException e) {
            System.out.println("cycle=" + e.getMessage());
        }

        int[] items = {3, 4};
        System.out.println("subset01(6)=" + subset01(items, 6));
        System.out.println("subsetUnbounded(6)="
                + subsetUnbounded(items, 6));
        System.out.println("subset01(7)=" + subset01(items, 7));
        System.out.println("subsetTests=" + verifySmall01());
    }
}
~~~

Lưu tệp **DpStateAuditDemo.java** rồi chạy với **JDK 17 trở lên**:

~~~bash
javac DpStateAuditDemo.java
java DpStateAuditDemo
~~~

Kết quả chính xác:

~~~text
dagState5=8
missing=undefined state 3
cycle=cycle at state 0
subset01(6)=false
subsetUnbounded(6)=true
subset01(7)=true
subsetTests=4732
~~~

### Giải thích đầu ra

**`dagState5=8`:** dãy cơ sở và phụ thuộc tạo các giá trị `dp[0..5]=[1,1,2,3,5,8]`. Mỗi trạng thái chỉ đọc những phụ thuộc có chỉ số nhỏ hơn, nên là DAG và có thể đánh giá từ các base case.

**`missing=undefined state 3`:** trạng thái 1 cố đọc trạng thái 3 nhưng miền chỉ chứa `{0,1}`. Đây là **tham chiếu chưa định nghĩa**, không phải một chu trình.

**`cycle=cycle at state 0`:** khi DFS từ 0 gọi 1 rồi quay lại 0, `color[0]==1` (đang tính), nên phát hiện chu trình. Điều này khác với kết quả số 0 hợp lệ của một DP.

**`subset01(6)=false`:** hai vật 3 và 4 chỉ dùng một lần không thể tạo tổng 6. **`subsetUnbounded(6)=true`** vì bài cho phép dùng hai lần giá trị 3. Hai kết quả khác nhau **vì đặc tả và lớp trạng thái khác nhau**, không vì một hàm có lỗi chạy vòng lặp.

**`subset01(7)=true`:** chọn cả 3 và 4 một lần, tổng 7.

**`subsetTests=4732`:** chương trình sinh toàn bộ các mảng độ dài n từ 0 đến 5 trên các giá trị {1,2,3}. Tổng số mảng là `1+3+9+27+81+243=364`; mỗi mảng được kiểm tra với 13 mục tiêu từ 0 đến 12, nên **364 × 13 = 4.732** ca so sánh. Mỗi kết quả của DP 0/1 được đối chiếu với oracle liệt kê tất cả tập con.

### Ranh giới của ví dụ

- `GraphDp` chỉ mô hình hóa **các trạng thái phụ thuộc cộng**. Một DP thực tế có thể dùng min, max, phép OR, phân hoạch hoặc chuyển phức tạp; kỹ thuật kiểm tra phụ thuộc vẫn có ích nhưng cần quy tắc tương ứng.
- Mảng `dependencies` lưu **cạnh S→T** nghĩa là S cần T. DFS đánh giá T trước khi hoàn thành S. Không dùng một đỉnh đang GRAY như giá trị đã tính.
- Nếu một lần đánh giá `GraphDp` ném ngoại lệ vì thiếu trạng thái hoặc chu trình, đối tượng có thể còn các màu GRAY trên đường DFS đang dở; **không tiếp tục tái dùng nó như trạng thái đã kiểm chứng**. Hãy sửa định nghĩa rồi khởi tạo đồ thị mới.
- `Math.addExact` chủ động ném `ArithmeticException` nếu tổng vượt giới hạn long. Với DP đếm số cách lớn, dùng `BigInteger` hoặc số học modulo **nếu bài toán cho phép**; overflow không phải dấu hiệu của chu trình.
- Hai hàm subset sum giả định **giá trị dương** và `target` không âm, đủ nhỏ để cấp mảng độ dài `target+1`. Nếu muốn hỗ trợ giá trị âm hoặc trạng thái có miền lớn, phải thiết kế lại miền tổng, thứ tự và cách lưu.
- Kiểm thử 4.732 ca chỉ kiểm tra những đầu vào nhỏ đã sinh; để chứng minh đúng tổng quát còn cần bất biến và lập luận rằng cập nhật giảm dần không dùng lại một vật.

## 11. Khi đồ thị phụ thuộc có chu trình thì phải làm gì?

Phát hiện chu trình không phải lúc nào cũng dẫn tới câu “bài toán vô nghiệm”. Có ba tình huống khác nhau:

### Trường hợp A — chu trình do công thức sai

Ví dụ `dp[i]` gọi lại chính `dp[i]` mà không thu hẹp bài toán, hoặc công thức của một DP theo tiền tố vô tình dùng `i+1` thay vì `i-1`. Cách sửa là **sửa trạng thái, định nghĩa cơ sở hoặc chỉ số phụ thuộc** để các lời gọi đi tới bài toán con nhỏ hơn.

Đừng chỉ thêm bộ đếm giới hạn độ sâu đệ quy rồi trả 0 khi vượt ngưỡng: cách đó có thể biến lỗi không dừng thành **kết quả sai khó phát hiện**.

### Trường hợp B — bài toán thật sự là trên đồ thị có chu trình

Ví dụ tìm đường đi ngắn nhất trên một đồ thị có chu trình. Công thức dựa trên đỉnh `dist[v]` có thể phụ thuộc qua các cạnh tạo chu trình, nên không thể luôn tính từng `dist[v]` một lần bằng DFS memo như trên DAG.

Cần dùng phương pháp có bảo đảm phù hợp điều kiện trọng số, chẳng hạn:
- **BFS** cho đường đi ngắn nhất trên đồ thị không trọng số.
- **Dijkstra** khi trọng số cạnh không âm.
- **Bellman–Ford** trong các trường hợp có cạnh âm và cần phát hiện chu trình âm có thể ảnh hưởng khoảng cách.
- **Floyd–Warshall** cho mọi cặp đỉnh, với các giai đoạn cho phép đỉnh trung gian tạo một thứ tự cập nhật có chứng minh.

Những thuật toán này xử lý tính lặp/chu trình thông qua **thư giãn** hoặc **thứ tự giai đoạn có cấu trúc**, thay vì đòi một DAG trên đỉnh gốc.

### Trường hợp C — có thể tạo DAG bằng cách mở rộng trạng thái

Nếu đếm **đường đi đơn** (không lặp đỉnh) trong một đồ thị có chu trình, trạng thái chỉ chứa đỉnh hiện tại thường **thiếu tập đỉnh đã đi qua**. Có thể thiết kế `dp[vertex][visitedMask]` với số đỉnh đã thăm tăng khi bước tiếp; các bước không quay về cùng `visitedMask`, tạo một thứ tự tiến triển hữu hạn.

Nhưng miền trạng thái có thể tới **O(n2^n)**, chỉ khả thi khi số đỉnh nhỏ. Việc làm mất chu trình bằng cách thêm trạng thái có thể đổi lấy **bùng nổ không gian trạng thái**, nên phải đánh giá cả tính đúng và độ phức tạp.

Một số bài khác dùng **fixed-point iteration** hoặc giải các thành phần liên thông mạnh (SCC) theo cách riêng. Đó không còn là DP một lượt trên DAG đơn giản; phải phân tích **tồn tại nghiệm, cách hội tụ và điều kiện dừng** thay vì chỉ dùng memoization.

## 12. Phân biệt “trạng thái thừa” với “trạng thái không đạt được”

Một trạng thái nằm trong miền `dp[i][s]` nhưng không thể xuất hiện trên bất kỳ đường đi hợp lệ từ đầu vào **không tự động là trạng thái thừa về ngữ nghĩa**.

- **Không đạt được (unreachable):** khóa là hợp lệ theo định nghĩa nhưng không có cách thực hiện để tới đó từ trạng thái khởi đầu cụ thể. Ví dụ với các vật đều có trọng lượng chẵn, tổng lẻ có thể không đạt được.
- **Thừa (redundant):** hai khóa khác nhau cùng đại diện cho **bài toán con tương đương** về mọi phần tương lai, hoặc một chiều khóa không làm thay đổi lựa chọn/giá trị còn lại.
- **Không cần cho truy vấn hiện tại:** một trạng thái có thể có nghĩa và đạt được nhưng **không phải tiền nhiệm** của trạng thái đáp án, nên top-down không cần tính nó.
- **Thiếu trạng thái:** hai lịch sử cần phân biệt bị gộp vào một khóa, hoặc bài toán con cần thiết không được định nghĩa.

Các chiến lược tối ưu hóa khác nhau:
- **Sparse memoization:** chỉ tính những trạng thái được truy vấn và các phụ thuộc cần thiết.
- **State compression:** gộp các trạng thái tương đương với chứng minh.
- **Pruning:** bỏ các trạng thái bị thống trị bởi trạng thái khác, nhưng phải chứng minh rằng bỏ chúng không thể làm mất nghiệm tối ưu.
- **Rolling array:** dùng lại bộ nhớ của giai đoạn không còn cần thiết, với thứ tự duyệt bảo toàn phụ thuộc.

Các kỹ thuật này thường tiết kiệm bộ nhớ, nhưng nếu dùng sai có thể làm rơi nghiệm. Cần đo **số trạng thái được tạo, số trạng thái đạt được, số chuyển và mức bộ nhớ đỉnh**, không chỉ số chiều trên giấy.

## 13. Các lỗi cài đặt thường gặp và dấu hiệu phát hiện

| Lỗi | Dấu hiệu | Cách kiểm tra/sửa |
| --- | --- | --- |
| Thiếu `i` ở bài chọn mỗi vật một lần | Có thể chọn cùng vật nhiều lần | Dùng `dp[i][s]` hoặc 1D cập nhật giảm s |
| Thiếu `previousTaken` khi quyết định tiến tới và có cấm kề | Hai lịch sử cùng khóa có lựa chọn khác | Bổ sung bit hoặc đổi công thức DP |
| Thêm `lastChosen` vô nghĩa | O(n²W) thay vì O(nW) | Chứng minh tương lai không phụ thuộc last |
| Nén 1D nhưng duyệt sai chiều | 0/1 biến thành unbounded | Phân biệt dữ liệu tầng cũ/tầng mới |
| Thiếu base case | DFS đi tới trạng thái không được định nghĩa | Liệt kê base và miền phụ thuộc |
| Dùng 0 làm cờ chưa tính | Những kết quả hợp lệ bằng 0 bị tính lại | Dùng `computed` riêng hoặc 3 màu |
| Dùng -1 làm cờ chưa tính | Lỗi khi đáp án hợp lệ bằng -1 | Tách cờ và giá trị |
| Chu trình trong truy hồi | Đệ quy vô hạn / stack overflow | Phát hiện GRAY→GRAY; sửa công thức hoặc thuật toán |
| Duyệt bottom-up không theo topo | Đọc giá trị chưa sẵn sàng | Chứng minh thứ tự, dùng topo/DFS nếu cần |
| Nhầm không thể đạt với chưa khởi tạo | Tự tạo nghiệm ảo hoặc bỏ nghiệm | Dùng INF/−INF/false với ngữ nghĩa rõ |
| Tràn số khi đếm cách | Số cách âm hoặc sai im lặng | `Math.addExact`, BigInteger hoặc modulo đúng đề |
| Xem DFS từ một đỉnh là kiểm toán toàn bảng | Bỏ sót chu trình không liên quan truy vấn | Duyệt mọi trạng thái khi cần kiểm toán toàn bộ |
| Chỉ test một ví dụ | Không thấy lỗi biên hoặc lỗi mô hình | Sinh ca nhỏ, brute force và phản ví dụ |

### Một lưu ý quan trọng về INF

Khi tối thiểu hóa, thường dùng `INF` cho trạng thái không đạt. Nếu viết `dp[next]=min(dp[next],dp[current]+cost)` mà `dp[current]==INF`, phép cộng có thể tràn hoặc tạo giá trị giả. Phải kiểm tra `dp[current]` là trạng thái đạt được trước khi cộng và dùng kiểu đủ rộng. Với bài có chi phí âm hoặc đường đi có chu trình, cần thêm giả thiết/thuật toán thích hợp.

Tương tự, với số cách đếm, kết quả 0 nghĩa là **không có cách**, nhưng vẫn có thể là một giá trị đã tính hoàn chỉnh. Memoization phải tách **trạng thái tính toán** ra khỏi **giá trị bài toán**.

## 14. Quy trình tự kiểm toán trước khi nộp bài DP

Có thể dùng quy trình sau cho hầu hết các bài quy hoạch động:

1. **Ghi đặc tả:** đầu vào, tập phương án khả thi, mục tiêu hoặc số lượng muốn tính.
2. **Định nghĩa một trạng thái bằng câu đầy đủ:** ví dụ “`dp[i][s]` có thể tạo tổng s bằng i vật đầu”.
3. **Kiểm tra đủ thông tin:** hai lịch sử cùng khóa có cùng các lựa chọn tương lai hợp lệ không? Có quy tắc phụ nào chưa được mã hóa không?
4. **Kiểm tra trạng thái thừa:** trường nào không làm thay đổi tập lựa chọn và giá trị tối ưu còn lại? Có thể bỏ hay nén với chứng minh không?
5. **Liệt kê miền và cơ sở:** giá trị nào hợp lệ, trạng thái rỗng/không thể đạt xử lý thế nào, có tham chiếu ngoài biên không?
6. **Viết từng chuyển có diễn giải:** mỗi nhánh ứng với một hành động hợp lệ; các nhánh đã bao phủ mọi khả năng chưa?
7. **Vẽ hướng phụ thuộc:** nếu `S` cần `T`, ghi cạnh `S→T`. Tìm thước đo giảm hoặc thứ tự tô pô; kiểm tra chu trình.
8. **Chọn top-down hay bottom-up:** top-down cần memo và phát hiện GRAY nếu có nguy cơ chu trình; bottom-up cần thứ tự phụ thuộc hợp lệ.
9. **Khi nén mảng, chứng minh thứ tự ghi:** nguồn được đọc từ tầng trước hay tầng hiện tại? Có bị ghi đè trước khi sử dụng không?
10. **Kiểm thử bằng brute force ở n nhỏ:** thử 0 phần tử, một phần tử, giá trị trùng, mục tiêu không đạt, trường hợp cực trị, và các bài có hành động bị giới hạn số lần.
11. **Phân tích độ phức tạp:** số khóa trạng thái × số phép chuyển cho mỗi khóa; RAM cho bảng, stack, cấu trúc lưu phụ.
12. **Phát biểu giới hạn của lời giải:** tiền điều kiện, kiểu số, trường hợp có chu trình thực và khả năng dùng thuật toán khác.

**Điểm nhấn:** đừng chỉ hỏi “công thức có chạy không?”. Hãy hỏi “công thức có giải **đúng bài toán con** không?”, “có được dùng trạng thái chưa sẵn sàng không?” và “những lịch sử nào đã bị gộp mà không có chứng minh?”.

## 15. Bài tập tự luyện và đáp án định hướng

**Bài 1 — nhận diện chiều thừa.** Với 0/1 knapsack không có điều kiện về thứ tự vật đã chọn, người học dùng `dp[i][capacity][lastChosen]`. Trường nào nên xem xét loại bỏ trước?

*Đáp án:* `lastChosen`, vì sau khi biết i và capacity thì danh sách vật còn xét và sức chứa còn lại đã xác định. Tuy nhiên, cần xác nhận không có ràng buộc bổ sung liên quan lastChosen trước khi gộp.

**Bài 2 — thiếu chiều nào?** Bài subset sum dùng mỗi vật tối đa một lần, nhưng viết `can(s)=can(s-3)||can(s-4)`. Với [3,4] và target=6, vì sao công thức sai?

*Đáp án:* Nó cho phép dùng đồng/vật 3 hai lần, trả true cho 6. Phải theo dõi vật đã xét bằng `i` hoặc duy trì giai đoạn cập nhật đúng trong DP nén.

**Bài 3 — chiều cập nhật.** Với một vật có giá trị 3 và target=6, quét `can[s]` từ 3 lên 6 hay từ 6 xuống 3 phù hợp cho 0/1?

*Đáp án:* Từ 6 xuống 3, vì `can[s-3]` phải là kết quả trước khi xử lý vật hiện tại. Quét tăng cho phép dùng lại chính vật 3.

**Bài 4 — chu trình.** Xét `f[0]=1`, `f[1]=f[2]+1`, `f[2]=f[1]+1`. Vẽ cạnh phụ thuộc và giải thích vì sao memoization thông thường không hoàn thành.

*Đáp án:* 1→2 và 2→1 tạo chu trình. DFS lại chạm đỉnh đang GRAY; không có thứ tự đánh giá một lần theo phụ thuộc. Phải sửa mô hình hoặc chọn cách giải quan hệ khác.

**Bài 5 — phân biệt missing và unreachable.** Bảng `dp[0..4]` được định nghĩa đầy đủ nhưng một trạng thái có giá trị INF vì không đạt được. Nó có phải trạng thái “thiếu” không?

*Đáp án:* Không. Đây là **trạng thái hợp lệ nhưng không thể đạt**. Thiếu định nghĩa là khi công thức cần một trạng thái không có định nghĩa hợp lệ, hoặc thiếu thông tin trong khóa.

**Bài 6 — DFS chỉ tính một truy vấn.** Đồ thị có một chu trình ở các đỉnh 7 và 8, nhưng `dp[0]` không phụ thuộc hai đỉnh ấy. DFS từ 0 có bắt buộc phát hiện chu trình không?

*Đáp án:* Không. DFS từ 0 chỉ đi theo đồ thị con phụ thuộc của 0. Muốn kiểm tra **tất cả trạng thái**, phải chạy kiểm toán từ mọi đỉnh chưa được thăm.

**Bài 7 — khi nào cần thêm visitedMask?** Vì sao đếm đường đi đơn trên đồ thị có chu trình thường không thể dùng `dp[vertex]`?

*Đáp án:* Những đường đi đã qua cùng một vertex nhưng có tập đỉnh đã thăm khác nhau có những bước tiếp theo khác nhau. Cần thông tin như visitedMask để cấm đi lại đỉnh, hoặc một mô hình khác; trạng thái có thể tăng theo cấp số mũ.

**Bài 8 — kiểm thử DP.** Vì sao kiểm thử “4.732 ca đều đúng” chưa thể được dùng như chứng minh thuật toán tổng quát?

*Đáp án:* Nó chỉ kiểm tra các mảng độ dài 0..5 trên {1,2,3} với target0..12. Đầu vào lớn hơn, giá trị khác hoặc thay đổi điều kiện có thể gây lỗi. Tính đúng tổng quát cần chứng minh công thức chuyển và thứ tự cập nhật dựa trên định nghĩa trạng thái.

## Ghi nhớ

- **Đủ trạng thái:** mọi lịch sử gộp vào cùng khóa phải tương đương về lựa chọn hợp lệ và bài toán tương lai.
- **Không thừa trạng thái:** chỉ lưu thông tin thực sự ảnh hưởng bài toán con; loại một chiều phải có chứng minh, không chỉ vì muốn tiết kiệm bộ nhớ.
- **Trạng thái thiếu gây sai ngữ nghĩa** ngay cả khi đồ thị phụ thuộc không có chu trình, như dùng `sum` đơn lẻ cho subset sum giới hạn mỗi vật một lần.
- **DAG và thứ tự phụ thuộc:** một DP tính mỗi trạng thái một lần cần cơ sở hợp lệ và thứ tự sao cho phụ thuộc được giải trước. Dùng DFS 3 màu hoặc topo để phát hiện chu trình.
- **DP nén phụ thuộc giai đoạn:** cập nhật **giảm tổng** cho subset sum 0/1, **tăng tổng** cho biến thể unbounded với giá trị dương.
- **Chu trình không luôn đồng nghĩa vô nghiệm:** nếu bài toán thực sự có chu trình, có thể cần sửa trạng thái, đưa thêm giai đoạn, thuật toán đồ thị hoặc giải fixed point; không được trả bừa 0 khi gặp chu trình.
- **Content QA của DP** phải xét mô hình, base case, các chuyển, thứ tự tính, tràn số và phản ví dụ; kiểm thử brute force trên dữ liệu nhỏ là công cụ hỗ trợ chứ không thay chứng minh.
