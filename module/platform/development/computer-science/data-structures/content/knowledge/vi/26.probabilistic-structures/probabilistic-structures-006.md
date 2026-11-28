# Counting Bloom filter và rủi ro khi cập nhật bộ đếm sai

Bloom filter chuẩn dùng một mảng **bit 0/1** để kiểm tra một khóa *có thể thuộc tập* hay không. Nó có thể trả **dương tính giả** (*false positive*), nhưng trong mô hình chỉ-thêm hợp lệ thì không trả **âm tính giả** (*false negative*) đối với khóa đã thêm. Đổi lại, nó không hỗ trợ xóa một khóa tùy ý bằng cách tắt bit: một bit có thể được nhiều khóa dùng chung.

**Counting Bloom filter (CBF)** thay mỗi bit bằng một **bộ đếm không âm**. Khi thêm khóa, các bộ đếm ở vị trí băm tăng; khi xóa *một lần xuất hiện thực sự đang tồn tại*, chúng giảm. Nhờ thông tin số đóng góp, CBF có thể hỗ trợ xóa một cách an toàn **nếu tất cả các thao tác cập nhật tuân thủ hợp đồng**.

Từ “nếu” là phần quan trọng nhất. Một lần xóa khóa chưa từng thêm, một lỗi tràn số, một cập nhật đồng thời bị mất, hoặc thao tác giảm nhầm số lần đều có thể khiến bộ đếm tại vị trí bắt buộc trở về **0 khi một khóa thật vẫn còn tồn tại**. Khi đó CBF trả **False cho khóa hiện hữu**, mất đi bảo đảm không âm tính giả.

Bài học thuộc chương **Cấu trúc xác suất**, nằm trong mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Nội dung nối việc học các cấu trúc dữ liệu với **bất biến, thao tác, độ phức tạp thời gian/bộ nhớ và lựa chọn cấu trúc đúng bài toán**. Trọng tâm không chỉ là cài đặt add/remove, mà còn là **hợp đồng cập nhật chính xác và cách phát hiện lỗi bộ đếm**.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt Bloom bit chuẩn và counting Bloom về **biểu diễn, API và chi phí bộ nhớ**.
2. Viết hợp đồng **add / might_contain / remove_one** và xác định thao tác nào yêu cầu nguồn sự thật chính xác.
3. Phát biểu bất biến \(c[j]\) bằng **tổng đóng góp của các khóa còn hoạt động**, kể cả vị trí băm trùng nhau.
4. Chứng minh **không âm tính giả** khi add/remove hợp lệ, bộ đếm không tràn và không mất cập nhật.
5. Giải thích tại sao CBF **vẫn có dương tính giả**, kể cả sau khi đã xóa đúng một khóa.
6. Truy vết phản ví dụ **xóa một khóa false positive** khiến hai khóa thật cùng âm tính giả.
7. Phân biệt **set semantics** (mỗi khóa có/không) và **multiset semantics** (đếm số lần xuất hiện).
8. Nhận biết lỗi **double-add, double-delete, underflow, overflow kiểu wraparound, saturation** và xử lý vị trí băm trùng.
9. Phân tích **lost update, thao tác đa-vị-trí dở dang, crash recovery, replay sai thứ tự** trong hệ thống đồng thời.
10. Xây một cài đặt Python minh họa có nguồn chính xác, kiểm tra điều kiện xóa và các invariant.
11. Phân tích thời gian O(h), bộ nhớ O(mb), ảnh hưởng độ dài khóa và chi phí xác thực xóa.
12. Lựa chọn giữa CBF, Bloom bit + tái xây, phân vùng thời gian và set/DB chính xác.
13. Thiết kế phép đo FPR và bộ kiểm thử no-FN sau các chuỗi add/remove.
14. Giải các tình huống tính bộ đếm, chọn thiết kế và phát hiện sai lầm vận hành.

## 2. Từ bit đến counter: điều gì đã thay đổi?

Bloom chuẩn có m vị trí, mỗi vị trí một bit:

~~~text
bits[j] ∈ {0, 1}
~~~

Counting Bloom có cùng ý tưởng vị trí băm nhưng dùng bộ đếm:

~~~text
count[j] ∈ {0, 1, 2, ...}
~~~

Với một khóa x, các hàm băm chọn h vị trí:

\[
H_0(x),H_1(x),\ldots,H_{h-1}(x)\in\{0,1,\ldots,m-1\}.
\]

Các thao tác được khái quát như sau:

~~~text
ADD(x):
    với từng vị trí j trong h kết quả băm của x:
        count[j] += 1

MIGHT_CONTAIN(x):
    nếu có vị trí j của x có count[j] == 0:
        return False
    return True

REMOVE_ONE(x):
    # Chỉ cho phép nếu x có ít nhất một lần add còn hiệu lực.
    với từng vị trí j trong h kết quả băm của x:
        count[j] -= 1
~~~

**Không được suy ra rằng có thể gọi REMOVE_ONE với mọi x mà MIGHT_CONTAIN trả True.** CBF chỉ trả lời membership **xấp xỉ**. Nó không tự xác nhận x thực sự đã được thêm.

### 2.1. Ví dụ truy vết ba khóa

Giả sử m=8 và h=2:

| Khóa | Vị trí băm | Đã thêm? |
| --- | --- | --- |
| A | {1,4} | Có |
| B | {4,6} | Có |
| C | {1,6} | Không |

Ban đầu:

~~~text
Vị trí:  0 1 2 3 4 5 6 7
Counter: 0 0 0 0 0 0 0 0
~~~

Sau add(A):

~~~text
Vị trí:  0 1 2 3 4 5 6 7
Counter: 0 1 0 0 1 0 0 0
~~~

Sau add(B):

~~~text
Vị trí:  0 1 2 3 4 5 6 7
Counter: 0 1 0 0 2 0 1 0
~~~

Cùng một vị trí 4 nhận đóng góp từ A và B, nên **counter[4]=2**, thay vì chỉ lưu bit 1.

### 2.2. Truy vấn vẫn có thể dương tính giả

Query A thấy counter[1]=1, counter[4]=2 nên True. Query B thấy counter[4]=2, counter[6]=1 nên True.

Query **C chưa từng add** nhưng thấy counter[1]=1 và counter[6]=1, vì vậy cũng trả **True**. Đây là **false positive**, chính xác theo hợp đồng approximate membership.

**Counting** bổ sung thông tin về **số đóng góp tại mỗi vị trí**, **không** bổ sung tên các khóa sở hữu vị trí đó.

### 2.3. Xóa hợp lệ

Sau add A và B, nếu biết chắc A hiện hữu và chỉ muốn xóa **một lần đóng góp của A**, thực hiện:

~~~text
remove_one(A):
    counter[1]: 1 → 0
    counter[4]: 2 → 1

Counter cuối:
    0 0 0 0 1 0 1 0

query(A): False  # Trong ví dụ này; không được bảo đảm trong mọi va chạm.
query(B): True   # B vẫn đủ vị trí 4 và 6.
~~~

Lệnh xóa hợp lệ giữ lại 1 đơn vị ở vị trí 4 vì B vẫn cần vị trí đó. Đây là lợi ích cốt lõi so với Bloom bit chuẩn.

## 3. Định nghĩa tập đang hoạt động và ngữ nghĩa số lần xuất hiện

Không thể định nghĩa remove đúng nếu chưa biết hệ thống đang duy trì **tập (set)** hay **đa tập (multiset)**.

Đặt \(a_t(x)\) là **số lần xuất hiện đang còn hiệu lực** của khóa x sau t thao tác, với \(a_t(x)\) là số nguyên không âm.

**Tập khóa đang hoạt động** ở thời điểm t:

\[
S_t=\{x:a_t(x)>0\}.
\]

Hai kiểu API hợp lệ nhưng khác nhau:

| Hợp đồng | Thêm x khi đã có | Xóa x |
| --- | --- | --- |
| **Set** | Idempotent, không tăng đóng góp nếu x đã hiện hữu | Xóa hẳn x nếu x có trong tập |
| **Multiset** | Tăng multiplicity của x thêm 1 | Xóa đúng **một lần xuất hiện** nếu a(x)>0 |

Một CBF chỉ gồm m counter không thể tự phân biệt hai kiểu API này khi có khóa trùng; cần có hợp đồng quản lý **các update đã được chấp nhận**.

### 3.1. Multiset: add ba lần, remove hai lần

~~~text
add(A)
add(A)
add(A)
⇒ a(A) = 3

remove_one(A)
remove_one(A)
⇒ a(A) = 1
⇒ query(A) BẮT BUỘC True nếu không có lỗi.
~~~

Nếu một lệnh remove(A) của ứng dụng được hiểu là **xóa hết A khỏi tập**, nhưng CBF chỉ giảm một lần, các counter có thể còn dấu vết. Điều đó chủ yếu tạo **false positive** sau xóa; không được gọi đây là đúng ngữ nghĩa xóa hoàn toàn.

Nếu CBF giảm **ba lần** dù A thật sự chỉ còn một lần add, counter có thể giảm nhầm đóng góp của những khóa khác và gây false negative.

### 3.2. Set: add trùng phải được xác thực

~~~text
insert(A)
insert(A)
insert(A)
⇒ A chỉ là một thành viên set.
~~~

Nếu ta tăng counter ở mọi lần insert nhưng nguồn set chính xác chỉ ghi nhận một lần, rồi khi delete(A) giảm đúng một lần, counter bị thừa dấu vết. Muốn giữ đúng set semantics, cần **tránh double-increment** bằng một nguồn xác minh hoặc cơ chế update idempotent.

Ngược lại, nếu một retry không thành công và chương trình lại giảm counter, có thể vô tình xóa đóng góp của khóa khác.

### 3.3. Truy vấn True không cho biết multiplicity

CBF không thể lấy trực tiếp số lần x xuất hiện từ các counter tại vị trí x vì các khóa khác cũng đóng góp. Trong minh họa:

~~~text
counter[4]=2
~~~

không cho biết A đã được add 2 lần; giá trị 2 có thể tới từ **A một lần + B một lần**.

Vì thế không nên dùng CBF như **bảng đếm tần suất chính xác theo key**.

## 4. Bất biến quan trọng nhất: tổng các đóng góp

Muốn hiểu vì sao một phép xóa có thể phá CBF, ta phát biểu chính xác counter cần biểu diễn gì.

Gọi:

- \(a_t(x)\): số lần xuất hiện còn hiệu lực của x ở thời điểm t.
- \(H_i(x)\): vị trí băm thứ i của x, với i từ 0 đến h−1.
- \(d_x(j)=|\{i:H_i(x)=j\}|\): số lần vị trí j xuất hiện trong h vị trí băm của x.

Trong mô hình cập nhật đúng, không mất thao tác và counter có đủ độ rộng:

\[
\boxed{c_t[j]=\sum_{x}a_t(x)\,d_x(j).}
\]

Công thức này quan trọng vì **cùng một khóa có thể băm trùng một vị trí**. Nếu H(A)={4,4,7}, ta có \(d_A(4)=2\), \(d_A(7)=1\).

### 4.1. Chứng minh bằng quy nạp theo thao tác

**Ban đầu:** Mọi \(a_0(x)=0\), mọi \(c_0[j]=0\), nên bất biến đúng.

**Sau add(x) hợp lệ:** \(a(x)\) tăng 1; tại mỗi vị trí j, counter tăng \(d_x(j)\), nên hai vế bất biến đều tăng cùng lượng.

**Sau remove_one(x) hợp lệ:** Vì \(a(x)>0\), multiplicity giảm 1; tại mỗi vị trí j, counter giảm \(d_x(j)\), nên hai vế bất biến cùng giảm và không âm do vẫn có ít nhất một đóng góp trước lúc giảm.

Do đó bất biến được bảo toàn qua mọi chuỗi thao tác hợp lệ.

### 4.2. Suy ra bảo đảm không âm tính giả

Nếu một khóa x đang hoạt động, \(a_t(x)>0\). Với mọi vị trí \(H_i(x)\), ta có \(d_x(H_i(x))\ge1\), nên:

\[
c_t[H_i(x)]\ge a_t(x)\,d_x(H_i(x))>0.
\]

Tất cả counter được query đều dương:

\[
\boxed{x\in S_t\Longrightarrow
\mathrm{mightContain}(x)=\mathrm{True}.}
\]

Lấy phản đảo:

\[
\boxed{\mathrm{mightContain}(x)=\mathrm{False}
\Longrightarrow x\notin S_t.}
\]

Đây là **bảo đảm không âm tính giả** khi CBF thực hiện update đúng, sử dụng cùng hàm băm/encoding, không overflow/underflow, không mất trạng thái và query chỉ quan sát trạng thái đã công bố nhất quán.

**Điểm khác Bloom bit:** CBF không còn bất biến “mọi vị trí chỉ tăng 0→1” vì counter được giảm hợp lệ. Nó dùng một bất biến mạnh hơn: **counter đúng bằng tổng đóng góp của các khóa hiện hữu**.

### 4.3. Vì sao không suy ra True nghĩa là có?

Nếu \(c[j]>0\), biết có ít nhất một khóa nào đó đóng góp vào j; ta **không biết khóa đang hỏi** là khóa ấy. Vì vậy, CBF vẫn cho phép FP.

Nếu hai khóa A và D có **cùng toàn bộ dấu vết băm**, xóa A hợp lệ còn D vẫn có thể khiến query A tiếp tục trả True. CBF giữ no FN cho D, **không bảo đảm mọi khóa vừa xóa đều trả False**.

## 5. Một phép xóa sai có thể phá cả nhiều khóa đang hoạt động

Quay lại ba khóa ở mục 2:

~~~text
H(A)={1,4}
H(B)={4,6}
H(C)={1,6}

Chỉ A và B đã add:
c[1]=1, c[4]=2, c[6]=1.
~~~

Query C thấy cả c[1] và c[6] dương, nên **might_contain(C)=True** dù C chưa từng add.

Nếu lập trình viên viết:

~~~text
if might_contain(C):
    remove_one(C)
~~~

thì phép xóa **không hợp lệ** làm:

~~~text
c[1]: 1 → 0
c[6]: 1 → 0
c[4]: 2 (không đổi)

query(A): c[1]=0 ⇒ False.
query(B): c[6]=0 ⇒ False.
~~~

Kết quả là **A và B vẫn hoạt động nhưng cả hai đều âm tính giả**. Không có hash bị hỏng; lỗi là **sử dụng kết quả approximate membership như bằng chứng xóa hợp lệ**.

### 5.1. Một quy tắc cần ghi nhớ

**Không bao giờ dùng might_contain(x) làm điều kiện duy nhất để cho phép remove_one(x).**

Phải biết từ **nguồn có thẩm quyền** rằng \(a(x)>0\) và phải biết update sẽ giảm **đúng số lần đóng góp**. Ví dụ nguồn có thể là dictionary chính xác, transaction DB, log update có trình tự và dedup, hoặc một giao thức đảm bảo xóa chỉ dành cho các khóa đang hiện hữu.

### 5.2. False positive sau xóa hợp lệ là điều bình thường

Nếu H(A)=H(D)={1,4}, add A và D rồi remove_one(A) hợp lệ:

~~~text
Trước xóa: c[1]=2, c[4]=2.
Sau xóa:   c[1]=1, c[4]=1.

query(D)=True (khóa còn hoạt động).
query(A)=True (A đã xóa, nhưng trùng dấu vết với D).
~~~

Xóa thành công trong CBF nên được hiểu là **giảm đúng đóng góp mà không làm khóa khác âm tính giả**, **không phải** mọi khóa vừa xóa bắt buộc nhận False.


## 6. Bộ đếm giới hạn bit: wraparound và saturation

Trong tài liệu lý tưởng, counter có thể tăng vô hạn. Trong hệ thống thật, để tiết kiệm bộ nhớ người ta có thể dùng **counter b-bit**. Mỗi ô chỉ biểu diễn tối đa:

\[
C_{\max}=2^b-1.
\]

Ví dụ 4 bit biểu diễn từ 0 đến 15; 8 bit biểu diễn từ 0 đến 255. Nếu số đóng góp vào một vị trí vượt giới hạn, cách xử lý quyết định **có còn giữ bất biến không**.

### 6.1. Tràn kiểu quay vòng (wraparound)

Với counter 2-bit:

~~~text
Giá trị hợp lệ: 0, 1, 2, 3

Trước add: c[j]=3
Một add nữa: c[j] = (3+1) mod 4 = 0
~~~

Giả sử có bốn khóa thật cùng cần vị trí j. Sau add thứ tư, counter tại j bằng 0 nên **bất kỳ khóa nào cần j đều có thể bị query False**, dù vẫn hoạt động.

**Đây là false negative do overflow**, không phải false positive thông thường.

Bộ đếm có kiểu số nguyên không dấu và phép tăng bị wrap không được sử dụng mà không có một cơ chế chặn/tránh tràn đúng hợp đồng.

### 6.2. Chặn tại cực đại (saturation) vẫn chưa đủ cho delete

Có thể nghĩ rằng thay vì wrap, ta dùng:

~~~text
c[j] = min(C_max, c[j] + 1)
~~~

Counter không bao giờ quay về 0 chỉ vì một lần add, nhưng **thông tin số đóng góp thật đã bị mất**:

~~~text
Counter 2-bit, C_max=3.
Có 4 khóa khác nhau cùng cần vị trí j.

Số đóng góp thật: 4
Giá trị lưu:       3 (saturated)

Xóa hợp lệ 3 trong 4 khóa:
Số đóng góp thật: 1
Giá trị lưu nếu cứ giảm: 0

Khóa thứ tư vẫn còn, nhưng counter[j]=0 → False.
~~~

Do đó chỉ **saturate rồi vẫn cho decrement thông thường** có thể tạo false negative **sau các thao tác xóa hợp lệ**.

Một thiết kế thực phải dùng counter đủ rộng, mở rộng vùng overflow, không cho phép xóa chưa bảo đảm chính xác, hoặc tái xây an toàn trước khi mất khả năng phục hồi số đóng góp. Không được tuyên bố saturation tự giải quyết bài toán.

### 6.3. Dự báo số đóng góp khác dự báo số khóa

Các khóa phân bố vào m vị trí, trung bình mỗi vị trí nhận khoảng:

\[
\lambda\approx\frac{hn_{\mathrm{active}}}{m}
\]

lượt đóng góp khi mỗi khóa hoạt động được add đúng một lần, các hash gần đều. Đây chỉ là **trung bình**; một số vị trí có thể nhận **nhiều hơn đáng kể** do va chạm, và add lặp theo multiset còn tăng tải.

Counter b-bit cần được chọn theo **phân phối cực trị/đỉnh tải** và chính sách overflow, không chỉ theo giá trị trung bình \(\lambda\).

Nếu có các khóa “nóng” được add nhiều lần hoặc luồng update bị retry, một số counter có thể tràn ngay cả khi số khóa phân biệt không lớn.

### 6.4. Underflow khi decrement quá mức

Nếu delete một khóa không hiện hữu hoặc delete cùng một lần add **hai lần**, counter có thể giảm dưới 0:

~~~text
c[j]=0
delete sai → c[j]=-1
~~~

Với số nguyên không dấu b-bit, có thể xảy ra wrap **0→2^b−1**. Giá trị dương giả ấy không nhất thiết gây FN ngay; nó làm **bất biến mất nghĩa**, có thể giữ false positive lâu dài hoặc kết hợp với các thao tác về sau tạo lỗi.

Trong một số code, bộ đếm âm cũng được xem là “khác 0”, càng làm ngữ nghĩa mơ hồ.

Giải pháp đúng không phải chỉ đặt **max(0,c−1)** vì decrement sai tại một counter dương vẫn có thể giảm đóng góp của khóa khác. Phải **từ chối delete không hợp lệ ngay từ nguồn quyết định**, rồi mới cập nhật counter.

### 6.5. Bảng rủi ro theo kiểu arithmetic

| Cách xử lý | Khi tăng vượt max | Khi giảm sai | Hệ quả cần cảnh giác |
| --- | --- | --- | --- |
| Wrap theo modulo | Max→0 | 0→max | FN ngay khi add hoặc mất bất biến |
| Saturation khi tăng | Giữ max, mất số đóng góp thật | Giảm từ max vẫn xảy ra | FN về sau khi xóa các khóa hợp lệ |
| Chặn 0 khi giảm | Không quyết định lỗi overflow | Ngăn âm ở chính ô 0 | Không ngăn giảm nhầm **ô đang dương** |
| Phát hiện và từ chối trước giới hạn | Không nhận update vượt mức khi không thể bảo đảm | Kiểm tra quyền xóa | Cần hợp đồng về add bị từ chối và nhất quán tập nguồn |
| Counter lớn/overflow table | Giữ được lượng đóng góp đủ lớn | Vẫn phải kiểm tra delete | Thêm RAM và độ phức tạp vận hành |

**Lưu ý:** Nếu hệ thống đã công bố **add thành công** trong nguồn dữ liệu nhưng sau đó từ chối tăng counter do đầy, không thể tiếp tục tin kết quả False của filter cho dữ liệu mới. Cần phối hợp việc chấp nhận/công bố update.

## 7. Nhầm số lần add/delete: idempotency và duplicate events

Một API counting Bloom cần xác định rõ **đang đếm bao nhiêu lần xuất hiện** của từng khóa. Các lỗi dưới đây có thể xuất hiện ngay cả khi counter không tràn.

### 7.1. Add lặp do retry

~~~text
DB INSERT(A) thành công một lần.
Thông điệp "add A" gửi qua queue bị retry hai lần.

CBF xử lý:
    add(A)
    add(A)
⇒ c[...] tăng hai lần.

Nguồn có thẩm quyền:
    A hiện hữu một lần.
~~~

Nếu sau đó delete(A) thực hiện một lần, counter còn dấu vết thừa. Tùy va chạm, đây chủ yếu làm **tăng FP**, nhưng trạng thái counter đã không còn bằng số đóng góp của tập nguồn.

Để giữ set semantics, cập nhật phải **idempotent theo khóa/phiên bản/sự kiện** hoặc ghi nhận số lần đã xử lý. Để giữ multiset semantics, mỗi lần add phải tương ứng một lần xuất hiện **thật sự được chấp nhận**.

### 7.2. Delete bị gửi hai lần

~~~text
DB DELETE(A) thực hiện một lần.
CBF nhận hai thông điệp delete(A).

Lần 1: giảm đúng đóng góp của A.
Lần 2: tiếp tục giảm dù A không còn.
~~~

Lần hai có thể làm counter dùng chung với B giảm về 0 → **B âm tính giả**.

**Dedup thông điệp delete** thường quan trọng hơn tránh double-add; double-add hay gây thừa dấu vết, còn double-delete có thể xóa đóng góp đang được khóa khác sử dụng.

### 7.3. Đổi từ set semantics sang multiset semantics giữa chừng

Nếu hệ thống ban đầu dùng add(A) idempotent, sau đó triển khai remove_one theo kiểu “trừ mỗi lần nhận sự kiện delete”, multiplicity không còn được định nghĩa nhất quán. Mọi migration phải xác định **trạng thái đã lưu đại diện cho loại đóng góp nào**, không chỉ thay chữ ký API.

### 7.4. Hash có thể trả vị trí trùng trong cùng một khóa

Giả sử \(h=3\), \(H(A)=(4,4,7)\). Nếu add tăng theo **ba lượt hash**:

~~~text
add(A):
    c[4] += 2
    c[7] += 1
~~~

Thì remove_one(A) cũng phải giảm:

~~~text
remove_one(A):
    c[4] -= 2
    c[7] -= 1
~~~

Một code add với danh sách vị trí nhưng delete với **set các vị trí duy nhất** (hoặc ngược lại) sẽ sai bất biến số đóng góp. Có thể chọn quy tắc mỗi vị trí phân biệt chỉ tăng một lần, nhưng **bắt buộc nhất quán ở cả add, remove và chứng minh**.

## 8. Đồng thời: counter không làm giao dịch trở thành nguyên tử

### 8.1. Lost update khi hai luồng cùng increment

Giả sử c[j]=0, hai luồng cùng thêm hai khóa có băm vào j:

~~~text
Thread A: đọc c[j]=0, chuẩn bị ghi 1.
Thread B: đọc c[j]=0, chuẩn bị ghi 1.

Thread A: ghi 1.
Thread B: ghi 1.

Đúng ra phải là 2; thực tế là 1.
~~~

Bây giờ nếu xóa hợp lệ khóa của A, c[j] giảm **1→0**, trong khi khóa của B vẫn còn. B có thể bị FN.

Một kiểu số nguyên thread-safe để **đọc** không tự khiến thao tác **read-modify-write** nguyên tử. Cần atomic increment/decrement, lock phù hợp hoặc kiến trúc cập nhật an toàn hơn.

### 8.2. Mỗi ô nguyên tử vẫn chưa làm toàn bộ add/remove nguyên tử

Add một khóa x có thể phải tăng h counter:

~~~text
add(X): H(X)={2,5,7}

Tăng c[2] thành công.
Tăng c[5] thành công.
Chưa kịp tăng c[7].

Query(X) chạy tại đây, thấy c[7]=0 → False.
~~~

Nếu add **chưa được công bố hoàn tất**, query False có thể phù hợp hợp đồng nhất quán yếu được xác định rõ. Nếu hệ thống đã báo add thành công từ trước, đây là **lỗi quan sát trạng thái không nhất quán**.

Delete cũng có thể tạm thời tạo trạng thái giữa chừng mà một query quan sát được; nếu các counter dùng chung vẫn đủ sau khi delete hợp lệ, kết quả của các khóa còn sống cần được phân tích theo thứ tự công bố.

### 8.3. Cần một điểm tuyến tính hóa hoặc hợp đồng snapshot

Các thiết kế có thể dùng:

- **Lock toàn thao tác** và query với cùng lock khi yêu cầu một trạng thái nhất quán mạnh.
- **Xây trạng thái mới bất biến rồi chuyển phiên bản** khi số khóa/cấu trúc phù hợp.
- **Sharding theo khóa/counter** và một giao thức ghi đảm bảo không mất update.
- **Event log + replay + version** để khôi phục và hợp nhất theo đúng thứ tự.

Một cập nhật nhiều vị trí có thể cần cơ chế rộng hơn atomic counter đơn lẻ. Khi không thể bảo đảm tính đầy đủ của filter, nên **bypass nhánh False** và tra nguồn chính xác, thay vì trả kết luận chắc chắn.

### 8.4. Concurrent delete và cùng một khóa

Hai luồng cùng đọc a(A)=1, cả hai tin rằng được phép delete(A), rồi cùng giảm các counter. Ngay cả khi mỗi decrement là nguyên tử, vẫn xảy ra **xóa hai lần cho một lần xuất hiện**.

Do đó **kiểm tra quyền xóa + tiêu thụ một lần hiện hữu** cũng phải nguyên tử/transactional ở nguồn có thẩm quyền, không chỉ cập nhật các counter.

## 9. Lỗi phân tán: thứ tự sự kiện, snapshot và crash recovery

### 9.1. Delete cũ đến sau reinsert

~~~text
T1: INSERT(A), A xuất hiện.
T2: DELETE(A), A hết hiệu lực.
T3: INSERT(A) mới, A lại hiện hữu.

CBF xử lý add mới tại T3.
Sau đó một bản sao thông điệp DELETE cũ của T2 tới muộn.
~~~

Nếu CBF nhận thông điệp delete cũ như **một lần xóa mới** mà không kiểm tra version/event ID, nó có thể giảm counter của lần insert mới, tạo FN.

Cần **thứ tự theo khóa, version/sequence number**, dedup retry và quy tắc tái chèn sau xóa. Một Bloom filter chỉ lưu counter **không tự biết lịch sử giao dịch**.

### 9.2. Crash giữa các vị trí

Một worker add x, tăng được 2/3 vị trí, rồi crash. Nếu DB đã báo x có hiệu lực, filter thiếu c[H_2(x)] và có thể trả False.

Ngược lại, một delete chỉ giảm được vài vị trí rồi crash có thể khiến counter thừa hoặc tạo trạng thái khó phục hồi khi replay.

Các hướng xử lý gồm:

1. **Write-ahead log** có quy tắc replay idempotent/versioned.
2. Giao dịch hoặc trình tự cập nhật đảm bảo **all-or-nothing** ở phạm vi cần thiết.
3. **Snapshot nhất quán** và lớp delta cho cập nhật đang diễn ra.
4. Tái xây filter từ nguồn chính xác khi không tin được trạng thái.

### 9.3. Không được khôi phục chỉ mỗi mảng counter

Một snapshot CBF phải đi kèm:

~~~text
version/snapshot của nguồn dữ liệu
số vị trí m
số hash h
thuật toán hash, seed/secret, version
encoding và chuẩn hóa khóa
độ rộng counter, endianness, overflow policy
mảng counter
cơ chế kiểm tra tính toàn vẹn và log chưa replay
~~~

Nếu hash/encoding thay đổi, cùng khóa có thể được query ở vị trí khác và âm tính giả. Nếu counter bị khôi phục từ snapshot cũ nhưng nguồn đã nhận các khóa mới, tính bao phủ cũng bị phá.

### 9.4. Hai loại sai lệch giữa database và CBF

- **DB có khóa nhưng CBF chưa add**: Tin kết quả False của CBF có thể gây **FN ở cấp ứng dụng**.
- **DB đã xóa nhưng CBF chưa remove**: CBF có thể trả True cho khóa đã xóa; nếu nhánh True được **xác minh bằng DB**, chủ yếu gây thêm lookup.

Hai chiều này **không đối xứng**. Trong nhiều ứng dụng ưu tiên an toàn, một Bloom chỉ-thêm không xóa bit và tái xây theo snapshot đôi khi **đơn giản hơn counting Bloom cập nhật đồng thời**.

## 10. FPR, dung lượng counter và độ phức tạp

### 10.1. Sai số membership sau xóa đúng

Nếu counter được cập nhật **chính xác theo tập khóa đang hoạt động**, phép query CBF kiểm tra **counter > 0** có cùng kiểu va chạm với một Bloom bit trên tập khóa ấy.

Với m vị trí, h vị trí băm mỗi khóa và n khóa phân biệt hiện hữu, xác suất dương tính giả xấp xỉ trong mô hình hash lý tưởng:

\[
p_{\rm FP}\approx(1-e^{-hn/m})^h.
\]

Khi có **multiset**, nhiều lượt add cùng một khóa làm counter tăng nhưng **không thay đổi tập vị trí có counter >0**, miễn update không tràn và không xóa sai. Vì vậy cơ chế FP trên các khóa lạ chủ yếu phụ thuộc **số khóa phân biệt đang có**, không phải tổng số multiplicity.

CBF **không loại bỏ FP**. Một khóa vừa xóa vẫn có thể True do các khóa khác cùng dùng vị trí.

### 10.2. Bộ nhớ b bit mỗi counter

| Loại bộ lọc | Dữ liệu lưu ở mỗi vị trí | Vùng nhớ lý thuyết |
| --- | --- | --- |
| Bloom bit chuẩn | 1 bit | **m bit** |
| Counting Bloom b=4 | 4 bit | **4m bit** |
| Counting Bloom b=8 | 8 bit | **8m bit** |
| Counting Bloom b=16 | 16 bit | **16m bit** |

Ví dụ m=1.000.000:

~~~text
Bloom bit:       1 000 000 bit ≈ 0,119 MiB.
Counting 4-bit:  4 000 000 bit ≈ 0,477 MiB.
Counting 8-bit:  8 000 000 bit ≈ 0,954 MiB.
Counting 16-bit:16 000 000 bit ≈ 1,907 MiB.
~~~

Đây chỉ là bộ nhớ **mảng được đóng gói**. Một list số nguyên Python hay object Java có thể có overhead cao hơn đáng kể. Nếu còn giữ dictionary/DB xác minh quyền xóa, phải tính **toàn bộ chi phí**.

### 10.3. Cận thời gian

Với phép hash một khóa được coi là O(1):

- **add**: O(h) cập nhật counter.
- **might_contain**: O(h) kiểm tra; có thể dừng sớm ở counter 0.
- **remove_one hợp lệ**: O(h) cập nhật, **chưa tính xác minh sự tồn tại**.
- **khởi tạo**: Θ(m) vị trí counter.
- **bộ nhớ**: Θ(mb) bit cho counter b-bit, chưa tính metadata.

Với khóa dài L byte và mỗi hash quét toàn bộ khóa, chi phí băm có thể là **O(hL)**. Nếu h cố định theo cấu hình, add/query có thể gọi là O(1) **theo số khóa n**, nhưng điều đó không có nghĩa h phép hash/ghi counter là miễn phí.

**Xác thực delete từ DB hoặc dictionary chính xác là chi phí riêng**; không được gộp thành “delete luôn O(h)” của toàn hệ thống.

### 10.4. So sánh cùng m hay cùng RAM?

Nếu so Bloom bit và CBF **cùng m vị trí**, CBF tốn nhiều bit hơn, nhưng có khả năng giảm đóng góp để xóa.

Nếu so **cùng ngân sách RAM**, CBF có thể chứa ít vị trí hơn, khiến FPR thực tăng. Một phép đánh đổi công bằng phải cố định **workload, ngân sách RAM tổng, FPR mục tiêu và yêu cầu xóa**, không chỉ con số m.


## 11. Python: mô phỏng các lỗi counter một cách xác định

Các đoạn mã mục này dùng bảng vị trí băm cho sẵn. Chúng **cố ý thực hiện thao tác không an toàn** để thấy hậu quả, không phải API nên đưa vào sản phẩm.

### 11.1. Xóa một khóa bị false positive

~~~python
positions = {
    "A": (1, 4),
    "B": (4, 6),
    "C": (1, 6),
}
counter = [0] * 8


def add_toy(key: str) -> None:
    for j in positions[key]:
        counter[j] += 1


def maybe_toy(key: str) -> bool:
    return all(counter[j] > 0 for j in positions[key])


def unsafe_remove_toy(key: str) -> None:
    # LỖI: không biết key có thật sự đang hiện hữu.
    for j in positions[key]:
        counter[j] -= 1


add_toy("A")
add_toy("B")

assert (counter[1], counter[4], counter[6]) == (1, 2, 1)
assert maybe_toy("A")
assert maybe_toy("B")
assert maybe_toy("C")  # C chưa add: false positive.

unsafe_remove_toy("C")  # Xóa sai khóa không hiện hữu.

assert counter[1] == 0
assert counter[6] == 0
assert maybe_toy("A") is False  # FN của A.
assert maybe_toy("B") is False  # FN của B.
~~~

Hai khóa thật bị false negative không phải do hash xấu, mà vì decrement của **một khóa chưa từng được thêm**.

### 11.2. Tràn số 2-bit gây FN ngay khi add

~~~python
MAX_2_BIT = 3

# Bốn khóa còn hoạt động cùng cần một vị trí j.
c_j = 0

for _ in range(4):
    c_j = (c_j + 1) % (MAX_2_BIT + 1)

assert c_j == 0  # Wraparound 3 -> 0.
# Nếu c_j là vị trí bắt buộc của một khóa active,
# query khóa ấy có thể False dù đã add.
~~~

Thao tác modulo **cố ý mô phỏng overflow**, không phải cách tăng counter an toàn.

### 11.3. Saturation gây FN khi xóa hợp lệ sau đó

~~~python
MAX_2_BIT = 3

actual_contributions = 0
stored_counter = 0

for _ in range(4):
    actual_contributions += 1
    stored_counter = min(MAX_2_BIT, stored_counter + 1)

assert actual_contributions == 4
assert stored_counter == 3  # Mất thông tin đóng góp thứ tư.

for _ in range(3):  # Xóa hợp lệ ba trong bốn đóng góp.
    actual_contributions -= 1
    stored_counter -= 1

assert actual_contributions == 1
assert stored_counter == 0  # Vẫn có một khóa nhưng counter=0.
~~~

Saturate tránh wrap tức thời khi add, nhưng **không bảo đảm xóa an toàn** nếu không lưu được lượng overflow thật.

### 11.4. Mất cập nhật qua read–modify–write

~~~python
# Mô phỏng lịch ghi/đọc hai luồng, không tạo luồng thật.
shared = 0

read_by_a = shared
read_by_b = shared

shared = read_by_a + 1
shared = read_by_b + 1  # Ghi đè cập nhật của A.

assert shared == 1      # Đúng ra phải 2.

shared -= 1             # Xóa hợp lệ một đóng góp.
assert shared == 0      # Khóa còn lại có thể thành FN.
~~~

**Bài học:** Phát biểu bất biến theo toán học chỉ đúng nếu **mọi phép tăng/giảm đã được nhận đủ, không tràn, không mất và đúng khóa**.

## 12. Python: counting Bloom tham chiếu có kiểm tra delete

CBF tự thân chỉ giữ counter; nó **không lưu danh tính mọi khóa**. Để kiểm chứng xóa hợp lệ, mã này lưu thêm dictionary **live_counts**, theo dõi multiplicity của từng khóa còn hoạt động.

**Đánh đổi:** Dictionary là một **nguồn chính xác**, có bộ nhớ tăng theo số khóa. Ví dụ vì thế là **mô hình giáo dục**, không phải counting Bloom thuần túy tối ưu bộ nhớ. Trong hệ thống thật, nguồn xác minh delete có thể là DB/log giao dịch bên ngoài.

Python 3.10 trở lên; SHA-256 với tiền tố phiên bản ổn định. Mã sử dụng Python int không có giới hạn 4/8-bit; nó **không thread-safe** và không có transaction đa hệ thống.

~~~python
from collections import Counter
import hashlib


class VerifiedCountingBloom:
    """Multiset counting Bloom có kiểm chứng delete, chạy tuần tự."""

    def __init__(self, slots: int, hash_count: int):
        if (
            isinstance(slots, bool)
            or not isinstance(slots, int)
            or slots <= 0
        ):
            raise ValueError("slots phải là int dương")

        if (
            isinstance(hash_count, bool)
            or not isinstance(hash_count, int)
            or hash_count <= 0
        ):
            raise ValueError("hash_count phải là int dương")

        self.m = slots
        self.h = hash_count
        self.counters = [0] * slots
        self.live_counts = {}  # Key -> số lần add còn hiệu lực.

    def _positions(self, key: str):
        if not isinstance(key, str):
            raise TypeError("Ví dụ chỉ nhận key str")

        raw = key.encode("utf-8")
        for i in range(self.h):
            digest = hashlib.sha256(
                b"cbf-lesson-v1|"
                + i.to_bytes(8, byteorder="big")
                + b"|"
                + raw
            ).digest()
            yield int.from_bytes(digest, "big") % self.m

    def _needed(self, key: str) -> Counter:
        # H(x) có thể là (4,4,7), vị trí 4 cần đếm hai lần.
        return Counter(self._positions(key))

    def add(self, key: str) -> None:
        needed = self._needed(key)

        for j, amount in needed.items():
            self.counters[j] += amount

        self.live_counts[key] = self.live_counts.get(key, 0) + 1

    def might_contain(self, key: str) -> bool:
        return all(
            self.counters[j] > 0
            for j in self._positions(key)
        )

    def remove_one(self, key: str) -> None:
        remaining = self.live_counts.get(key, 0)

        if remaining == 0:
            raise KeyError("Không có lần add hợp lệ cần xóa")

        needed = self._needed(key)

        # Kiểm tra toàn bộ trước khi sửa bất kỳ counter nào.
        if any(
            self.counters[j] < amount
            for j, amount in needed.items()
        ):
            raise RuntimeError("Counter hỏng; từ chối remove")

        for j, amount in needed.items():
            self.counters[j] -= amount

        if remaining == 1:
            del self.live_counts[key]
        else:
            self.live_counts[key] = remaining - 1

    def contains_exactly(self, key: str) -> bool:
        return self.live_counts.get(key, 0) > 0

    def assert_invariant(self) -> None:
        """Đối chiếu toàn bộ counter; chỉ dùng cho test/diagnostic."""
        expected = [0] * self.m

        for key, multiplicity in self.live_counts.items():
            assert multiplicity > 0
            for j, amount in self._needed(key).items():
                expected[j] += multiplicity * amount

        assert expected == self.counters

        for key in self.live_counts:
            assert self.might_contain(key)


cbf = VerifiedCountingBloom(slots=128, hash_count=3)

cbf.add("A")
cbf.add("A")
cbf.add("B")
cbf.assert_invariant()

assert cbf.live_counts["A"] == 2
assert cbf.might_contain("A")
assert cbf.might_contain("B")

cbf.remove_one("A")
assert cbf.live_counts["A"] == 1
assert cbf.might_contain("A")
cbf.assert_invariant()

cbf.remove_one("A")
assert not cbf.contains_exactly("A")
assert cbf.might_contain("B")
cbf.assert_invariant()

# A đã xóa vẫn có thể True vì va chạm; không ép nó False.
try:
    cbf.remove_one("A")
except KeyError:
    pass
else:
    raise AssertionError("Phải từ chối double-delete")

try:
    cbf.remove_one("never-added")
except KeyError:
    pass
else:
    raise AssertionError("Phải từ chối delete khóa chưa add")
~~~

### 12.1. Vì sao phải có Counter vị trí?

Nếu \(H(x)=(4,4,7)\), add theo h lượt hash phải tăng **2** ở vị trí 4 và **1** ở vị trí 7. Delete cũng giảm đúng các lượng đó. Dùng **Counter** giúp gộp vị trí để kiểm tra trước và giữ cập nhật đối xứng.

### 12.2. assert_invariant kiểm tra điều gì?

Hàm xây lại mảng counter mong đợi từ dictionary live_counts, rồi so sánh với mảng thật. Nó phát hiện nhiều lỗi **mất update, tăng/giảm sai, đếm trùng hoặc dữ liệu hỏng**.

Chi phí quét theo tất cả khóa đang hoạt động và số vị trí băm, nên **không gọi ở mỗi request** trong sản phẩm. Trong hệ thống lớn, có thể kiểm định định kỳ trên snapshot, test một tập nhỏ hoặc dùng phép đo giám sát.

### 12.3. Những giới hạn cần công bố

Bảo đảm của ví dụ chỉ áp dụng nếu:

- Update/query **chạy tuần tự** và được hoàn tất.
- Counter dùng Python int, không mô phỏng giới hạn b-bit.
- Không có crash/nhân bản thông điệp/snapshot lạc hậu.
- Hash, m, h, seed, encoding và version giữ nguyên.
- Dictionary chính xác và counter được cập nhật thành công cùng nhau.
- Không có điều kiện an toàn an ninh cần xác thực kết quả True.

Không thể suy ra một CBF bất kỳ trong hệ thống phân tán mặc nhiên có những điều kiện ấy.


## 13. Counter hữu hạn: kiểm tra trước khi chấp nhận add

Để tránh wrap, một thiết kế đơn giản là **kiểm tra mọi counter cần tăng trước khi cập nhật** rồi chỉ add nếu toàn bộ đều còn đủ dung lượng.

Ví dụ này giả định đã có danh sách vị trí băm và update **chạy tuần tự**; nó không giải quyết transaction với DB hoặc việc hai luồng kiểm tra đồng thời.

~~~python
from collections import Counter


class CapacityError(Exception):
    pass


def bounded_add(counters: list[int], positions, max_counter: int):
    """Từ chối toàn bộ add nếu bất kỳ counter nào sẽ tràn."""
    needed = Counter(positions)

    if any(
        counters[j] + amount > max_counter
        for j, amount in needed.items()
    ):
        raise CapacityError("Counter sẽ tràn; không nhận add")

    for j, amount in needed.items():
        counters[j] += amount


counts = [0] * 8

bounded_add(counts, (1, 4), max_counter=3)
bounded_add(counts, (4, 6), max_counter=3)

assert counts[1] == 1
assert counts[4] == 2
assert counts[6] == 1

try:
    # Vị trí 4 cần +2, từ 2 lên 4, vượt max 3.
    bounded_add(counts, (4, 4, 7), max_counter=3)
except CapacityError:
    pass
else:
    raise AssertionError("Phải từ chối add")

assert counts[4] == 2  # Không cập nhật nửa chừng.
assert counts[7] == 0
~~~

### 13.1. Điều kiện quan trọng ở cấp hệ thống

Giả sử DB đã insert X thành công rồi CBF từ chối add(X) vì một counter đầy. Bộ lọc **không còn bao phủ mọi khóa đang có trong DB**. Nếu ứng dụng dùng CBF False để loại, nó có thể trả **âm tính sai cho X**.

Vì thế cần phối hợp: chỉ công bố add khi index có thể biểu diễn, ghi **delta/overlay** cho khóa chưa vào CBF, tái xây trước ngưỡng hoặc **không tin kết quả False** khi filter không đầy đủ.

### 13.2. Preflight không phải transaction đa luồng

Hai luồng có thể cùng kiểm tra counter còn dưới max rồi đều tăng. Để bảo đảm không tràn, phần **kiểm tra + cập nhật + công bố trạng thái** cần được bảo vệ bằng lock, transaction hoặc giao thức nguyên tử phù hợp.

### 13.3. Khi đạt ngưỡng, làm gì?

Có thể **tái xây CBF với nhiều vị trí hoặc counter rộng hơn**, dùng một overflow table, phân vùng dữ liệu, chờ nguồn đủ nhất quán để đổi version, hoặc tra trực tiếp nguồn chính xác khi filter chưa thể cập nhật.

Không có cách nào cho phép **DB nhận khóa mới, CBF bỏ qua vì đầy mà vẫn tin CBF False** đối với tất cả khóa trong DB.

## 14. Counting Bloom như bộ lọc trước database

CBF thường là **tầng tăng tốc**, không phải nguồn sự thật. Đặt:

- **S_DB(t)**: tập khóa đang có trong database tại phiên bản t.
- **S_CBF(t)**: tập khóa đã được mã hóa đầy đủ vào CBF tại trạng thái t.

Muốn dùng CBF False để bỏ qua tra DB, cần bảo đảm:

\[
S_{\mathrm{DB}}(t)\subseteq S_{\mathrm{CBF}}(t)
\]

đối với **đúng phạm vi và phiên bản dữ liệu đang được đọc**.

### 14.1. Quy trình hai tầng

~~~text
Client hỏi K
    |
    v
CBF.might_contain(K)?
    |
    +-- False --> Có thể loại nhanh nếu CBF bao phủ đầy đủ tập DB
    |
    +-- True ---> Tra DB/set chính xác để xác minh
~~~

Nhánh True có thể gồm FP. Nhánh False chỉ đáng tin khi filter đã mã hóa tất cả khóa hiện hoạt động.

### 14.2. Insert vào DB nhưng chưa vào CBF

~~~text
T1: DB INSERT(X) thành công.
T2: Client hỏi X qua CBF snapshot cũ.
T3: Worker mới add X vào CBF.
~~~

Ở T2, CBF có thể trả False dù DB đã có X. Đây là **lỗi độ bao phủ dữ liệu**, không phải sai số FN được phép của counting Bloom đúng cập nhật.

Cần snapshot/phiên bản nhất quán, delta index hoặc fallback tra DB khi không thể chứng minh CBF đã bắt kịp.

### 14.3. Xóa ở DB nhưng chưa remove khỏi CBF

Nếu DB đã xóa A nhưng CBF chưa giảm đóng góp, filter có thể True cho A. Nếu ứng dụng luôn **xác minh True bằng DB**, kết quả cuối vẫn có thể chính xác; chủ yếu tốn thêm lookup.

Ngược lại, nếu remove A quá mức hoặc remove sai B, filter có thể False cho khóa còn tồn tại. Không thể giải quyết mọi race chỉ bằng đảo thứ tự hai lệnh write DB và update CBF.

### 14.4. Delete cũ đến sau reinsert

~~~text
v1: INSERT(A)
v2: DELETE(A)
v3: INSERT(A) lại

Sau khi xử lý v3, bản sao thông điệp DELETE(v2) đến muộn.
~~~

Nếu CBF không kiểm tra version/event ID và decrement thêm một lần, nó có thể xóa đóng góp của lần insert mới, gây FN. Cần **thứ tự theo khóa, version/sequence number và cơ chế dedup**.

### 14.5. Khi nào nên giữ Bloom bit thay vì dùng CBF?

Nếu xóa hiếm, nguồn khóa chính xác có sẵn và dấu vết lịch sử chưa làm filter quá bão hòa, phương án đơn giản hơn có thể là:

~~~text
Bloom bit chỉ-thêm
    +
DB xác minh các câu trả lời True
    +
Tái xây từ snapshot hiện hành định kỳ.
~~~

Giữ dấu vết khóa đã xóa gây FP nhưng **không giảm bit/counter dùng chung**, nhờ vậy giảm nguy cơ FN do thao tác xóa sai.

## 15. Các phương án khác và tiêu chí lựa chọn

| Nhu cầu | Phương án cân nhắc | Giới hạn chính |
| --- | --- | --- |
| Chỉ thêm, hỏi “đã từng thấy?” | Bloom bit chuẩn | Không xóa; FP tăng theo lịch sử |
| Xóa hiếm, DB hiện hành sẵn | Bloom bit + verify DB + rebuild | True chưa đủ chứng minh tồn tại |
| Xóa liên tục, approximate membership | **Counting Bloom** | Cần xác thực delete, chống tràn, đồng bộ |
| Hết hạn theo ngày/epoch | Bloom riêng theo phân vùng | Bỏ đúng phân vùng đã hết hạn |
| Membership chính xác, liệt kê khóa và xóa tùy ý | Set/hash index/DB | Tốn bộ nhớ/lưu trữ theo từng khóa |
| Xóa fingerprint gần đúng | Cuckoo filter thích hợp | FP/va chạm; xóa chỉ cho khóa có thật |
| Cố ý quên trong luồng vô hạn | Stable/aging Bloom | Có thể **cho phép FN** |
| Phân quyền/thanh toán cần chắc chắn | Nguồn dữ liệu có thẩm quyền | Không tin approximate True như bằng chứng |

### 15.1. Phân vùng thời gian

Với cửa sổ thời gian, giữ một filter theo phân vùng và **bỏ cả filter** khi toàn bộ phân vùng đã hết hạn, tránh giảm riêng bit/counter của từng khóa.

Nhưng với cửa sổ trượt, nếu bỏ filter của một ngày mà trong đó còn sự kiện thuộc cửa sổ, hệ thống có thể **bỏ sót khóa**. Phạm vi thời gian của mỗi filter phải khớp hợp đồng query.

### 15.2. Tái xây từ tập đang hoạt động

CBF hỏng counter nên được **tái xây từ snapshot khóa chính xác** hoặc log update được kiểm chứng. Do va chạm, không thể khôi phục danh sách khóa gốc từ counter array.

Nếu rebuild diễn ra song song với add/delete, cần thu thập delta, quản lý version và **chuyển trạng thái một cách nhất quán**. Không được dùng bản mới để loại khóa đã add sau snapshot mà chưa được delta bao phủ.

### 15.3. Cuckoo filter không phải giấy phép xóa mọi khóa

Cuckoo filter có thể hỗ trợ xóa fingerprint trong biến thể thích hợp, nhưng fingerprint có thể trùng. Xóa một khóa chưa hiện hữu chỉ dựa vào lời đáp gần đúng vẫn có thể xóa nhầm dấu vết khóa khác.

Điểm chung của những cấu trúc này: **approximate membership không tự cung cấp chứng cứ đủ mạnh để cấp quyền delete**.

### 15.4. Đánh giá chi phí đầu-cuối

CBF thường tốn nhiều bit hơn Bloom chuẩn, nhưng có thể tránh tái xây quá thường xuyên. Ngược lại, việc giữ dictionary chính xác để xác thực xóa, lock phân tán và xử lý overflow có thể khiến tổng chi phí cao hơn.

Nên đo **RAM tổng, throughput update/query, độ trễ, số lượt tra DB, chi phí rebuild và khả năng crash recovery**, không chỉ O(h) của thao tác giảm counter.


## 16. Kiểm thử: không âm tính giả sau chuỗi cập nhật hợp lệ

Với một CBF được quảng bá là **không FN khi update hợp lệ**, phép kiểm thử chính:

\[
\boxed{\forall x\in S_{\mathrm{active}}:\quad
\mathrm{mightContain}(x)=\mathrm{True}.}
\]

**Không được bắt mọi khóa đã xóa đều phải False**, bởi va chạm vẫn có thể gây false positive.

### 16.1. Thử một chuỗi add/remove với nguồn chính xác

Đoạn sau dùng lớp **VerifiedCountingBloom** ở mục 12:

~~~python
cbf = VerifiedCountingBloom(slots=256, hash_count=3)

operations = [
    ("add", "A"),
    ("add", "B"),
    ("add", "A"),
    ("add", "C"),
    ("remove", "A"),
    ("remove", "B"),
    ("add", "B"),
    ("remove", "A"),
]

for action, key in operations:
    if action == "add":
        cbf.add(key)
    else:
        cbf.remove_one(key)

    # Đối chiếu đầy đủ counter với live_counts sau mỗi thao tác.
    cbf.assert_invariant()

    # Kiểm tra no-FN cho mọi khóa còn hoạt động.
    for active_key in cbf.live_counts:
        assert cbf.might_contain(active_key)

# B và C còn hoạt động; A đã xóa hết.
assert cbf.contains_exactly("B")
assert cbf.contains_exactly("C")
assert not cbf.contains_exactly("A")

# A vẫn có thể là false positive, không assert False.
~~~

### 16.2. Đo false positive trên khóa không hoạt động

Với tập N gồm các khóa được biết chắc **không thuộc tập active**, FPR quan sát:

\[
\widehat{\mathrm{FPR}}=
\frac{\#\{x\in N:\mathrm{mightContain}(x)=\mathrm{True}\}}{|N|}.
\]

Có thể phân loại N thành **khóa chưa từng add** và **khóa đã xóa**; hai nhóm có lịch sử khác nhau. Với CBF đúng cập nhật, cả hai nhóm vẫn có thể false positive.

Không đo FPR bằng cách lặp cùng một negative key hàng nghìn lần trên một filter cố định: cùng khóa/hash/trạng thái thường trả cùng kết quả, không phải các phép thử ngẫu nhiên độc lập.

### 16.3. Các tình huống phải thử

| Tình huống | Điều kiện đúng |
| --- | --- |
| A, B chia sẻ một counter; xóa A | B còn hoạt động phải True |
| A, D có cùng toàn bộ vị trí; xóa A | D True; A có thể vẫn True |
| Add A ba lần, remove hai lần | A còn một lần xuất hiện và phải True |
| Remove khóa false positive chưa từng add | **Từ chối**, không giảm counter |
| Double-delete do retry | **Từ chối** lần không còn quyền xóa |
| H(A)=(4,4,7) | Add/remove cùng tính multiplicity tại 4 |
| Counter ở max, add tiếp | Không wrap/sai; xử lý theo policy |
| Saturated counter rồi xóa nhiều lần | Không cho counter về 0 trước khi hết đóng góp |
| Hai luồng tăng cùng counter | Không mất increment |
| Query chen giữa add/remove | Tính nhất quán được định nghĩa rõ |
| Crash khi mới tăng một phần vị trí | Replay/tái xây để không công bố trạng thái lỗi |
| DELETE cũ đến sau reinsert | Không xóa lần insert mới |
| Đổi hash/encoding/seed khi restart | Từ chối dùng nhầm version hoặc tái xây |
| Tăng khóa DB nhưng CBF chưa add | Bypass False hoặc dùng delta/phiên bản |
| Bỏ filter phân vùng thời gian | Không bỏ dữ liệu còn thuộc cửa sổ |

### 16.4. Giám sát vận hành

Những chỉ số cần theo dõi:

- Số khóa distinct và **số lần xuất hiện** đang hoạt động.
- Tỷ lệ vị trí counter >0, counter max, phân vị mức counter.
- Số lần **đụng ngưỡng overflow** hoặc remove bị từ chối.
- Số sự kiện update trùng, sai thứ tự hoặc phải replay.
- Tuổi snapshot và độ trễ giữa DB với CBF.
- FPR trên negative có nhãn; kiểm tra mẫu active **không FN**.
- RAM counter + metadata + nguồn xác minh; latency add/query/delete.
- Lần tái xây gần nhất, phiên bản hash/seed/encoding của từng replica.

**Một FN đối với khóa đã add thành công và đang hoạt động là lỗi bất biến**, không được coi là một tỷ lệ sai số thống kê có thể chấp nhận.

## 17. Những lỗi tư duy và triển khai cần tránh

| Sai lầm | Tại sao nguy hiểm? | Cách sửa |
| --- | --- | --- |
| “CBF có counter thì xóa khóa nào cũng được.” | Không xác minh khóa có thật; false positive có thể bị xóa nhầm | Chỉ remove theo nguồn chính xác |
| “True chứng minh đã add.” | Va chạm vẫn tạo FP | True chỉ là “có thể có” |
| “Delete khóa xong phải False.” | Khóa còn lại có thể dùng trùng toàn bộ vị trí | Cho phép FP sau delete |
| “Counter>0 chứng minh đúng số lần xuất hiện của khóa.” | Counter gồm đóng góp từ khóa khác | Multiplicity phải theo nguồn riêng |
| “Set add A hai lần nên tăng counter hai lần cũng không sao.” | Mất idempotency, dấu vết thừa hoặc lệch với delete | Thống nhất set/multiset semantics |
| “Retry delete không sao.” | Double-decrement có thể gây FN | Dedup thao tác theo event ID/version |
| “Counter 4-bit không tràn vì tải trung bình thấp.” | Một vị trí có thể chịu nhiều va chạm/khóa nóng | Xét cực trị và chính sách overflow |
| “Wrap max→0 chỉ là mất độ chính xác nhỏ.” | Một khóa active có thể False ngay sau add | Chặn wrap, dùng overflow/rebuild |
| “Saturate tại max là đủ cho xóa.” | Đã mất số đóng góp thật, delete về sau có thể gây FN | Không decrement không kiểm soát |
| “Không cho counter âm đã giải quyết delete sai.” | Delete nhầm có thể giảm counter dương của khóa khác | Phải xác nhận key đang active |
| “Các vị trí trùng trong h hash chỉ tính một lần lúc remove.” | Lệch add/remove | Dùng cùng quy tắc multiplicity |
| “Ghi tăng counter luôn nguyên tử.” | Read–modify–write có thể mất update | Atomic/lock và test race |
| “Atomic từng counter nghĩa là add nhiều vị trí atomic.” | Query có thể thấy state dở dang | Giao thức công bố/transaction |
| “Hai remove cùng khóa qua kiểm tra trước là hợp lệ.” | Cùng dùng một quyền xóa, gây double-delete | Xác minh và tiêu thụ quyền xóa nguyên tử |
| “Replay log không cần xét event ID.” | Duplicate/late delete có thể xóa reinsert | Version + dedup |
| “Crash khi update dở chỉ tạo FP.” | Add thiếu một vị trí có thể tạo FN | Recovery/replay hoặc rebuild |
| “Đổi m/h/hash nhưng giữ counter cũ.” | Query vị trí khác add, có thể FN | Không thay cấu hình đã dùng |
| “Chỉ lưu mảng counter để restart.” | Thiếu version/seed/encoding và log | Lưu metadata + consistency |
| “DB có khóa là CBF chắc có.” | Có thể chưa đồng bộ hoặc add bị từ chối do đầy | Chứng minh tập được bao phủ |
| “FPR 1% nghĩa là mọi request sai 1%.” | Mẫu số của FPR chỉ là negative | FP/(FP+TN) |
| “Counter rộng hơn chắc làm FPR nhỏ.” | Số vị trí vẫn thế; va chạm không mất | So theo RAM và n_active |
| “CBF cần O(h) nên luôn nhanh hơn DB.” | Xác minh delete, lock, cache, I/O chưa tính | Đo end-to-end |
| “Có approximate delete thì không cần set/DB.” | Không có danh sách khóa hay bằng chứng xóa hợp lệ | Dùng nguồn có thẩm quyền |
| “Bloom của deleted keys True thì chắc phải xóa.” | FP của bộ lọc xóa có thể loại khóa sống | Verify tombstone |
| “Stable Bloom cũng không FN như CBF chuẩn.” | Cơ chế aging có thể cố ý quên khóa | Tách hợp đồng FN |
| “Một FN là sai số được phép vì tên gọi probabilistic.” | CBF đúng cập nhật/no-overflow không FN | Điều tra vi phạm bất biến |

### 17.1. Checklist quyết định có dùng CBF không

Trước khi lựa chọn một counting Bloom cho hệ thống, hãy hỏi:

1. Tập cần biểu diễn là **set hay multiset**?
2. Nguồn nào xác nhận **mỗi remove có thật sự hợp lệ**?
3. Xóa một lần add hay xóa toàn bộ khóa?
4. Retry/add/delete trùng được xử lý idempotent thế nào?
5. Các counter có đủ độ rộng, xử lý **overflow/underflow** thế nào?
6. Có bảo đảm không mất increment/decrement khi song song không?
7. Khi một thao tác cập nhật h vị trí, query được nhìn thấy trạng thái nào?
8. Cơ chế recovery từ crash/snapshot/log là gì?
9. DB và CBF có chia sẻ ngữ nghĩa version/data visibility không?
10. FP sau delete có được chấp nhận và **xác minh nhánh True** không?
11. Nếu đã lưu dictionary chính xác, CBF có tiết kiệm đủ chi phí I/O/CPU không?
12. Có quy trình tái xây khi phát hiện counter lệch bất biến không?

Nếu thiếu câu trả lời cho một điều kiện ảnh hưởng no-FN, **không nên tin CBF False làm kết luận chắc chắn trong ứng dụng**.

## 18. Bài tập tự luyện có đáp án

### Nhóm A — Bất biến và ý nghĩa phép xóa

**Bài 1 — Từ bit sang counter.** Counting Bloom khác Bloom bit chuẩn ở cách lưu một vị trí như thế nào?

*Đáp án:* CBF lưu **số đóng góp không âm** tại vị trí, thay vì chỉ bit **0/1**, cho phép decrement khi xóa hợp lệ.

**Bài 2 — False positive.** CBF trả True cho một khóa chưa từng add. Điều đó có tự chứng minh counter sai không?

*Đáp án:* **Không**. Va chạm hash vẫn có thể tạo **false positive** như Bloom chuẩn.

**Bài 3 — No-FN.** Với update hợp lệ, cùng hash và không tràn, một khóa còn active có được trả False không?

*Đáp án:* **Không**. Mỗi vị trí của khóa nhận ít nhất một đóng góp dương từ chính khóa đó.

**Bài 4 — Công thức.** Viết bất biến counter tại vị trí j theo multiplicity của từng khóa.

*Đáp án:* \(c[j]=\sum_x a(x)d_x(j)\), với \(a(x)\) là số lần hiện hữu và \(d_x(j)\) là số lần j xuất hiện trong h vị trí hash của x.

**Bài 5 — Tập active.** Nếu a(A)=0, a(B)=2 thì tập active chứa khóa nào?

*Đáp án:* **Chỉ B**, vì \(S=\{x:a(x)>0\}\). A có thể vẫn bị CBF trả True do FP.

**Bài 6 — Xóa thành công.** Một thao tác remove_one(A) hợp lệ có bảo đảm might_contain(A) trả False không?

*Đáp án:* **Không**. Các khóa khác có thể vẫn làm mọi counter của A dương.

**Bài 7 — Xóa sai C.** Vì sao không được gọi remove_one(C) chỉ vì might_contain(C)=True?

*Đáp án:* C có thể **chưa từng add**, True chỉ là dương tính giả; decrement có thể làm hỏng đóng góp của khóa khác.

**Bài 8 — Set vs multiset.** Add A ba lần, theo multiset semantics thì a(A) là bao nhiêu?

*Đáp án:* **3** nếu cả ba add đều hợp lệ và hoàn tất. Theo set semantics, A chỉ là một thành viên và cần cơ chế tránh tăng trùng.

**Bài 9 — Remove hai lần.** Multiset đang có a(A)=3, gọi remove_one(A) hai lần đúng hợp đồng. A có phải còn True không?

*Đáp án:* **Có**. Multiplicity còn 1, các counter phải vẫn dương ở mọi vị trí băm của A.

**Bài 10 — Phản đảo.** Trong CBF đúng bất biến, từ “A active ⇒ query(A) True” suy ra điều gì hợp lệ?

*Đáp án:* **Query(A) False ⇒ A không active** trong tập đã được biểu diễn đúng theo version và các tiền điều kiện.


### Nhóm B — Truy vết phản ví dụ và vị trí băm trùng

**Bài 11 — Hai khóa chung counter.** Với H(A)={1,4}, H(B)={4,6}, sau add một lần mỗi khóa, các counter khác 0 là gì?

*Đáp án:* **c[1]=1, c[4]=2, c[6]=1**.

**Bài 12 — Xóa A hợp lệ.** Từ trạng thái bài 11, sau remove_one(A) các counter còn lại là gì?

*Đáp án:* **c[1]=0, c[4]=1, c[6]=1**; B vẫn True.

**Bài 13 — False positive C.** Khóa C chưa add, H(C)={1,6}. Trước khi xóa A ở bài 12, query C trả gì?

*Đáp án:* **True (false positive)** vì c[1] và c[6] đều dương do A/B.

**Bài 14 — Xóa C sai.** Trước khi xóa A, nếu decrement theo H(C) ở bài 13, có thể gây hậu quả gì?

*Đáp án:* **c[1] và c[6] về 0** dù A/B vẫn active, nên **cả A và B bị FN**.

**Bài 15 — Trùng toàn bộ vị trí.** H(A)=H(D)={2,5}. Add A, D rồi remove_one(A) hợp lệ. A có chắc False không?

*Đáp án:* **Không**. D vẫn làm c[2], c[5] dương; A có thể là FP sau xóa.

**Bài 16 — Hash trùng trong cùng khóa.** Với h=3, H(X)=(4,4,7), add(X) theo h lượt làm tăng counter nào, bao nhiêu?

*Đáp án:* **c[4] tăng 2 và c[7] tăng 1**. Remove_one(X) phải giảm đối xứng đúng những lượng đó.

**Bài 17 — Thay cách xử lý vị trí trùng.** Nếu add X theo ba lượt (4,4,7) nhưng remove chỉ giảm một lần ở 4, hậu quả là gì?

*Đáp án:* **Thừa đóng góp tại c[4]**, bất biến tổng đóng góp sai; có thể gây FP dư hoặc làm các lần update sau khó kiểm soát.

**Bài 18 — Counting Bloom có biết số lần A xuất hiện từ c[4]=3 không?**

*Đáp án:* **Không**. Các khóa khác có thể cùng đóng góp vào vị trí 4; counter là tổng va chạm, không phải tần suất riêng của A.

### Nhóm C — Overflow, saturation, underflow và retry

**Bài 19 — Counter 2-bit.** Counter 2-bit không dấu có thể biểu diễn từ bao nhiêu đến bao nhiêu?

*Đáp án:* **0 đến 3**.

**Bài 20 — Wraparound.** Counter 2-bit đang bằng 3 và tăng một lần theo modulo 4. Nó thành bao nhiêu, và có thể gây lỗi gì?

*Đáp án:* **0**, có thể gây **FN ngay** cho khóa còn cần vị trí ấy.

**Bài 21 — Saturation.** Có bốn đóng góp thật vào một counter 2-bit được saturate tại 3. Xóa hợp lệ ba đóng góp, nếu cứ giảm counter, số thật và số lưu còn bao nhiêu?

*Đáp án:* **Số thật còn 1, số lưu còn 0**; một khóa active có thể bị FN.

**Bài 22 — Underflow.** Một counter bằng 0 nhưng nhận delete sai. Dùng số nguyên không dấu b-bit có thể gây điều gì?

*Đáp án:* Có thể **wrap về 2^b−1**, làm mất bất biến. Không được chỉ dựa vào clamp ở 0 để kiểm tra quyền xóa.

**Bài 23 — Khóa nóng.** n khóa phân biệt nhỏ nhưng A được add rất nhiều lần theo multiset. Counter có thể tràn không?

*Đáp án:* **Có**. Multiplicity của khóa nóng và va chạm có thể làm một vị trí vượt max dù n phân biệt nhỏ.

**Bài 24 — Double-delete.** A chỉ active một lần, hệ thống nhận hai event DELETE(A) giống nhau. Xử lý cả hai có thể làm gì?

*Đáp án:* Lần thứ hai giảm **đóng góp không còn thuộc A**, có thể gây FN cho khóa khác. Cần dedup và xác thực số lần add còn hiệu lực.

**Bài 25 — Double-add ở set.** Database chỉ có một A nhưng worker tăng counter hai lần vì retry. Kết quả trực tiếp thường là gì?

*Đáp án:* **Counter thừa đóng góp**, không tương ứng với set hiện hành, thường tăng dấu vết/FP. Phải bảo đảm idempotency hoặc chọn multiset semantics có chủ đích.

**Bài 26 — Từ chối add do đầy.** CBF từ chối add X vì counter max nhưng DB đã công bố INSERT(X). Có được tin CBF False để kết luận X không ở DB không?

*Đáp án:* **Không**. Filter không bao phủ DB; cần delta/rebuild hoặc fallback tra nguồn chính xác.

**Bài 27 — Trung bình không phải cực đại.** Với \(\lambda\approx hn/m=2\), mọi counter có chắc không vượt 2 không?

*Đáp án:* **Không**. \(\lambda\) là trung bình theo mô hình; va chạm và khóa nóng có thể làm một số vị trí lớn hơn.

**Bài 28 — Lost update.** Hai luồng cùng thấy c[j]=0, mỗi luồng dự định tăng lên 1, cuối cùng ghi đè còn 1. Khi xóa hợp lệ một đóng góp, điều gì có thể xảy ra?

*Đáp án:* **c[j] về 0 dù còn một đóng góp thật**, dẫn tới FN. Cần atomic update/lock và giao thức đa-vị-trí.

### Nhóm D — Tính nhất quán và kiểm thử

**Bài 29 — Query giữa add.** Add(X) cần cập nhật ba counter nhưng mới cập nhật hai; query thấy counter thứ ba bằng 0. Có vi phạm cam kết “không FN cho add đã hoàn tất” không?

*Đáp án:* **Không nếu add chưa hoàn tất/công bố**. Nhưng nếu DB đã coi X active và ứng dụng tin False thì có thể sai; phải định nghĩa điểm công bố nhất quán.

**Bài 30 — Reinsert.** A bị DELETE ở v2 rồi INSERT lại ở v3; event DELETE(v2) bị retry sau v3. Rủi ro là gì?

*Đáp án:* **Decrement nhầm đóng góp của lần insert mới**, khiến A đang active có thể FN; cần version/event ID và dedup.


**Bài 31 — Crash khi add dở.** DB đã nhận X, CBF mới tăng hai trong ba vị trí rồi crash. Hậu quả là gì?

*Đáp án:* X có thể bị **FN ở cấp ứng dụng** vì CBF thiếu counter; cần replay/tái xây hoặc bypass False khi trạng thái chưa đủ.

**Bài 32 — Đổi seed sau restart.** Counter giữ nguyên nhưng hàm hash dùng seed khác. Có giữ được no-FN cho khóa cũ không?

*Đáp án:* **Không**. Vị trí query có thể khác vị trí add; phải khôi phục hash/seed/version/encoding phù hợp hoặc tái xây.

**Bài 33 — Counter đúng nhưng DB mới hơn.** CBF được xây từ snapshot v1, DB ở v2 đã thêm X. CBF False cho X có khẳng định X vắng ở DB v2 không?

*Đáp án:* **Không**, vì không có bằng chứng CBF bao phủ v2. Cần delta/version hoặc tra DB.

**Bài 34 — FPR đo trên nhóm nào?** Trong 10.000 truy vấn thật sự âm tính, có 150 truy vấn CBF True. FPR quan sát là bao nhiêu?

*Đáp án:* **150/10.000=1,5%**, không tính các true positive vào mẫu số.

**Bài 35 — False positive sau delete.** Một khóa đã xóa nhưng CBF vẫn trả True. Đây có phải bằng chứng remove_one bị triển khai sai không?

*Đáp án:* **Không nhất thiết**. Có thể là FP do các khóa còn active dùng chung toàn bộ vị trí. Cần đối chiếu bất biến counter và nguồn sự thật.

**Bài 36 — No-FN test.** Với tập khóa active có nhãn sự thật, assertion cốt lõi là gì?

*Đáp án:* **Mọi active key phải được might_contain trả True** sau mọi update hợp lệ. Một FN là dấu hiệu vi phạm hợp đồng.

### Nhóm E — Chọn cấu trúc phù hợp

**Bài 37 — Bộ nhớ.** Với m=1.000.000 vị trí, CBF 4-bit cần bao nhiêu bit lưu counter và gấp mấy lần Bloom bit cùng m?

*Đáp án:* **4.000.000 bit**, tức **4 lần** vùng bit của Bloom chuẩn, chưa tính metadata và nguồn xác minh.

**Bài 38 — Xóa theo phân vùng.** Dữ liệu hết hạn toàn bộ theo từng ngày, có nguồn khóa chính xác. Có cách nào tránh decrement từng khóa?

*Đáp án:* **Bloom riêng cho từng phân vùng thời gian** rồi bỏ toàn bộ filter của ngày hết hạn, khi đã chắc không còn dữ liệu trong cửa sổ truy vấn cần phân vùng đó.

**Bài 39 — Cấp quyền bằng filter.** CBF True cho ID người dùng. Có đủ để cấp quyền hoặc xác nhận thanh toán không?

*Đáp án:* **Không**. False positive vẫn có thể xảy ra; phải xác minh qua nguồn có thẩm quyền.

**Bài 40 — Kiến trúc hoàn chỉnh.** Hệ thống quản lý ID có add/delete thường xuyên, cần no-FN cho mọi ID đang hoạt động, chấp nhận FP gây thêm lookup. Hãy đề xuất cách dùng CBF an toàn hoặc một phương án đơn giản hơn.

*Đáp án:* Có thể dùng **CBF với nguồn xác thực delete chính xác, xử lý set/multiset nhất quán, counter đủ rộng hoặc overflow policy, atomic update, version/dedup, recovery và kiểm tra no-FN**. Nếu cập nhật xóa hiếm hoặc phức tạp, cân nhắc **Bloom bit chỉ-thêm + DB xác minh nhánh True + rebuild từ snapshot hiện hành**. Trong cả hai trường hợp, **CBF/Bloom False chỉ được dùng để loại khi đã bảo đảm bao phủ tập nguồn đúng version**.

## 19. Tổng kết và ghi nhớ

**Counting Bloom filter** thay mảng bit bằng mảng counter, cho phép **tăng khi add, giảm khi remove_one hợp lệ** và trả True khi **mọi vị trí băm có counter >0**. Nó giải quyết phần thiếu thông tin về **số đóng góp ở mỗi vị trí**, nhưng **không giải quyết hoàn toàn việc xác minh một khóa có thật hay không**.

Trong mô hình đúng, counter lưu:

\[
\boxed{c[j]=\sum_x a(x)d_x(j)}
\]

với \(a(x)\) là số lần xuất hiện còn hiệu lực, \(d_x(j)\) là số lần vị trí j xuất hiện trong h kết quả băm của x. Bất biến này giúp chứng minh:

\[
x\in S_{\mathrm{active}}
\Longrightarrow
\mathrm{mightContain}(x)=\mathrm{True}.
\]

Như vậy CBF **không âm tính giả** khi update hợp lệ, hash/encoding nhất quán, counter không tràn hoặc mất, và query thấy trạng thái đã công bố phù hợp. Nó **vẫn có dương tính giả**, cả với khóa chưa từng add lẫn khóa đã xóa nhưng trùng vị trí với khóa khác.

Các nguyên nhân hỏng counter chính cần ghi nhớ:

- **Remove một khóa chỉ vì might_contain True:** Có thể xóa nhầm false positive và giảm counter của khóa khác.
- **Double-delete / sai multiplicity:** Giảm nhiều hơn số lần add đang hiện hữu.
- **Overflow wrap:** Counter có thể 3→0 ngay khi add, tạo FN tức thì.
- **Saturation rồi decrement:** Mất thông tin đóng góp thực, có thể tạo FN về sau.
- **Lost update / crash giữa h vị trí:** Các counter không còn bằng tổng đóng góp.
- **Replay sai thứ tự / delete cũ sau reinsert:** Giảm nhầm đóng góp mới.
- **Đổi hash, seed, m, h hoặc version dữ liệu:** Query và add không còn cùng ngữ nghĩa.
- **DB có khóa mà CBF chưa add:** Không thể tin False đối với tập DB mới hơn.

Trong phân tích độ phức tạp, add/query/remove hợp lệ thường cần **O(h)** vị trí băm/đếm và vùng nhớ **O(mb) bit** với counter b-bit; **chi phí xác minh quyền xóa và nhất quán với nguồn dữ liệu là riêng**. Counting Bloom có thể phù hợp khi cần xóa thường xuyên, nhưng nếu nguồn chính xác đã có và chi phí cập nhật phức tạp, một Bloom bit + xác minh DB + tái xây có thể là lựa chọn đáng cân nhắc hơn.

**Ghi nhớ:** **CBF chỉ xóa an toàn khi biết chắc khóa đang có, giảm đúng số đóng góp và không làm mất counter của khóa khác.** Câu trả lời “có thể có” không bao giờ là giấy phép xóa. Muốn tin nhánh “không có”, trước hết phải chứng minh **bộ đếm và nguồn sự thật đang nhất quán**.
