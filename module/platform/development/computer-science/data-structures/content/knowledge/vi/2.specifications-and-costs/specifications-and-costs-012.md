# Mô hình so sánh, mô hình RAM và giả định về kích thước từ máy

> **Chương:** Đặc tả và chi phí · **Bài học:** Mô hình so sánh, mô hình RAM và giả định về kích thước từ máy

Tại sao sắp xếp `n` khóa bằng so sánh thường được phân tích với giới hạn dưới Ω(n log n), nhưng có thuật toán sắp xếp số nguyên chạy O(n + K)? Tại sao truy cập `a[i]` được gọi là O(1) trong mảng, trong khi tìm phần tử thứ `i` của danh sách liên kết có thể mất O(n)? Và tại sao cộng hai số nguyên lại được xem là O(1) trong nhiều bảng độ phức tạp, nhưng chương trình làm việc với số nguyên có hàng triệu chữ số không thể thực hiện phép cộng trong thời gian hằng số?

Các nhận định trên chỉ có thể được hiểu đúng khi nêu rõ **mô hình tính toán**: những thao tác nào được phép thực hiện, một thao tác có giá bao nhiêu và một ô nhớ hoặc một từ máy có thể chứa bao nhiêu thông tin.

Bài học thuộc chương **Đặc tả và chi phí** của mô-đun **Cấu trúc dữ liệu** (`COMPUTER_SCIENCE_DATA_STRUCTURES`). Trong phạm vi học mảng, danh sách liên kết, Stack, Queue, bảng băm, cây, heap và đồ thị, chúng ta sẽ làm rõ cách mô hình so sánh và mô hình RAM dẫn đến các kết luận về **thời gian, bộ nhớ, bất biến và lựa chọn cài đặt**. Không có ghi chú chuyên biệt bổ sung cho bài này.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Nêu đúng giả định của **mô hình so sánh** (*comparison model*) và giải thích vì sao giới hạn dưới cho thuật toán so sánh không áp dụng cho mọi thuật toán.
2. Hiểu **mô hình RAM** (*Random Access Machine*) và ý nghĩa của thao tác truy cập ngẫu nhiên O(1).
3. Phân biệt **unit-cost RAM** với **word-RAM** có từ máy `w` bit; nhận biết nguy cơ khi coi phép toán trên số nguyên dài bất kỳ là O(1).
4. Giải thích mối liên hệ giữa số phần tử `n`, miền khóa `U`, độ dài khóa `k` và kích thước từ máy `w`.
5. Viết độ phức tạp theo phép so sánh, thao tác từ máy, bit và bộ nhớ mà không trộn lẫn đơn vị.
6. Đánh giá các phát biểu O(1), O(log n), O(n), O(V+E) của cấu trúc dữ liệu cùng điều kiện áp dụng.
7. Nhận biết khi nào cần mô hình bổ sung, như bộ nhớ ngoài hoặc số lần truy cập khối, để phản ánh hệ thống thật.

## 2. Vì sao phải chọn mô hình chi phí?

Một thuật toán nhận đầu vào `x` và thực hiện một chuỗi bước. Để nói nó “tốn bao nhiêu”, ta phải định nghĩa:

- **Tham số kích thước:** `n` là số phần tử, số bit hay số byte?
- **Phép toán hợp lệ:** được so sánh khóa, tính chỉ số, cộng số nguyên, băm khóa, đọc địa chỉ tùy ý hay chỉ đi theo con trỏ?
- **Chi phí một bước:** một lần so sánh khóa dài có tính bằng một bước hay nhiều bước?
- **Cách tính bộ nhớ:** tính theo bit, byte, từ máy hay số ô/nút?
- **Kiểu bảo đảm:** xấu nhất, trung bình, kỳ vọng hay khấu hao?

Mô hình không cố tái hiện từng chu kỳ CPU. Nó là một **bản hợp đồng toán học** giúp so sánh thuật toán trên một tập giả định nhất quán.

| Mô hình | Một bước thường đếm | Thích hợp cho | Điều phải thận trọng |
| --- | --- | --- | --- |
| **So sánh** | So sánh hai khóa | Sắp xếp, tìm kiếm có thứ tự, cây tìm kiếm | Không áp dụng nguyên xi cho thuật toán dùng chữ số, chỉ số trực tiếp hoặc hash |
| **RAM chi phí đơn vị** | Phép toán cơ bản và đọc/ghi địa chỉ bất kỳ | Phân tích cấu trúc dữ liệu phổ thông | Có thể phi thực tế nếu cho số nguyên vô hạn kích thước |
| **Word-RAM** | Phép toán trên từ máy `w` bit | Mảng, bitset, hash, heap với khóa vừa từ máy | Phải quy định `w`, miền giá trị và tập phép toán |
| **Mô hình bit** | Phép logic/cộng/truyền một bit hoặc chi phí theo số bit | Số nguyên rất lớn, số học chính xác | Một phép cộng số lớn không còn O(1) |
| **Bộ nhớ ngoài/I/O** | Đọc/ghi một khối chứa `B` phần tử hoặc từ máy | Dữ liệu trên đĩa, hệ quản trị chỉ mục | Số phép so sánh và số lần chuyển khối là hai chỉ số khác |

Không có mô hình nào tự động “đúng nhất” trong mọi bài toán. Chúng trả lời **những câu hỏi khác nhau**.

### 2.1. Ví dụ đầu tiên: thế nào là “một phép so sánh”?

Khi so sánh hai số nguyên vừa từ máy, ta có thể coi kết quả `a < b` là một bước O(1). Khi so sánh hai chuỗi dài `k` ký tự từ trái sang phải, trường hợp xấu nhất cần đọc đến `k` ký tự.

Do đó, một câu như “sắp xếp mất O(n log n) phép so sánh” **không đồng nghĩa** “mất O(n log n) thao tác ký tự” nếu mỗi phép so sánh có thể tốn O(k).

## 3. Mô hình so sánh: chỉ khai thác quan hệ thứ tự giữa các khóa

Trong **mô hình so sánh thuần túy**, thuật toán xác định thứ tự các khóa bằng những câu hỏi như:

```text
a < b ?
a > b ?
a == b ?
```

Với khóa phân biệt, một câu hỏi kiểu `a < b` có hai kết quả đúng/sai. Thuật toán có thể di chuyển, hoán đổi và lưu tham chiếu tới khóa, nhưng **không được khai thác trực tiếp biểu diễn bit/chữ số của khóa để suy ra thứ tự**.

Mô hình này phù hợp với dữ liệu mà ta chỉ biết phép so sánh có thứ tự, chẳng hạn:

- Các khóa là đối tượng triển khai một bộ so sánh tổng quát.
- Chương trình không thể giả định khóa nằm trong miền số nhỏ.
- Ta muốn chứng minh kết quả đúng cho mọi thứ tự tương đối của các khóa.
- Cấu trúc như cây tìm kiếm duy trì bất biến `key_left < key_node < key_right` theo quan hệ so sánh đã chọn.

**Lưu ý:** một thuật toán dùng thêm hash hoặc dùng khóa làm chỉ số mảng không còn là thuật toán *thuần so sánh* theo giả định này.

### 3.1. Chi phí trong mô hình so sánh

Ta thường báo:

\[
C(n)=\text{số phép so sánh khóa}.
\]

Nếu mỗi phép so sánh có chi phí hằng số, `C(n)` giúp suy ra độ phức tạp thời gian. Nhưng để tính **toàn bộ công việc** của một cài đặt, đôi khi còn phải đếm:

- Số lần hoán đổi/di chuyển phần tử.
- Số lần cấp phát và sao chép bộ đệm.
- Chi phí tính khóa so sánh hoặc gọi hàm so sánh người dùng.
- Không gian phụ của thuật toán.

Ví dụ, tìm vị trí chèn trong mảng đã sắp bằng tìm kiếm nhị phân có O(log n) phép so sánh, nhưng chèn xong vẫn có thể phải dịch O(n) phần tử.

### 3.2. Mô hình so sánh không quyết định ngữ nghĩa khóa

Hai khóa được xem bằng nhau theo quy tắc nào? Phân biệt chữ hoa/thường, locale, thứ tự từ điển hay một trường mã định danh? Đó là phần **hợp đồng** của kiểu dữ liệu.

Một BST hoặc thuật toán sắp xếp chỉ được xem là đúng nếu quan hệ so sánh nhất quán với hợp đồng: chẳng hạn có tính bắc cầu, không tự mâu thuẫn và xử lý khóa bằng nhau theo quy tắc đã nêu. Sửa quan hệ so sánh có thể làm thay đổi hành vi dù số phép so sánh vẫn ít.

## 4. Giới hạn dưới sắp xếp bằng so sánh: vì sao Ω(n log n)?

Giả sử có `n` khóa **phân biệt**, và thuật toán sắp xếp chỉ khai thác các câu hỏi so sánh thứ tự giữa các khóa.

Có `n!` hoán vị thứ tự tương đối có thể xuất hiện. Thuật toán phải phân biệt đủ các khả năng để đưa khóa về thứ tự tăng dần.

Ta biểu diễn quá trình ra quyết định bằng **cây quyết định nhị phân**:

- Mỗi nút bên trong là một phép so sánh kiểu `a < b`.
- Mỗi cạnh tương ứng với kết quả đúng hoặc sai.
- Mỗi lá chứa quyết định cuối cùng về thứ tự các khóa đầu vào.

Một cây nhị phân có chiều cao `h` có nhiều nhất `2^h` lá. Vì cần ít nhất `n!` kết quả phân biệt:

\[
2^h \ge n!
\quad\Rightarrow\quad
h \ge \log_2(n!).
\]

Với `n` đủ lớn:

\[
\log_2(n!)=\Theta(n\log n).
\]

Vì vậy, **mọi thuật toán sắp xếp thuần so sánh xác định** đều cần ít nhất Ω(n log n) phép so sánh trong **trường hợp xấu nhất**.

### 4.1. Trực giác về `n!`

Với bốn khóa phân biệt, có:

\[
4!=4\cdot3\cdot2\cdot1=24
\]

thứ tự đầu vào có thể xảy ra. Mỗi câu hỏi có hai kết quả chỉ chia được tập khả năng thành tối đa hai nhánh. Do đó cần đủ những câu hỏi để phân biệt 24 khả năng trong trường hợp xấu nhất.

Với `n` lớn, số khả năng `n!` tăng cực nhanh, dẫn tới số phép so sánh tăng theo bậc `n log n`.

### 4.2. Nếu so sánh có ba kết quả thì sao?

Một phép so sánh ba chiều có thể trả `<, =, >`. Nếu chỉ xét các khóa **phân biệt**, nhánh `=` không xuất hiện khi so hai khóa khác nhau. Ngay cả khi mô hình cho phép tối đa ba nhánh, cây quyết định có tối đa `3^h` lá; khi đó vẫn cần:

\[
h\ge\log_3(n!)=\Omega(n\log n).
\]

Cơ số logarit chỉ làm thay đổi một hệ số hằng, không thay đổi bậc tăng trưởng.

### 4.3. Cận dưới nói về thao tác nào?

Cận dưới Ω(n log n) áp dụng cho **số phép so sánh** của bài toán sắp xếp khóa tùy ý trong mô hình so sánh đã nêu. Nó **không tự khẳng định** mọi cách sắp xếp số nguyên đều tốn Ω(n log n) thao tác RAM.

Đây là phân biệt then chốt giữa **giới hạn do mô hình** và **giới hạn của mọi thuật toán có thể tưởng tượng**.

## 5. Tìm kiếm trong mô hình so sánh

Với mảng **đã sắp xếp** và `n` khóa phân biệt, tìm kiếm nhị phân có thể loại một phần lớn ứng viên sau mỗi so sánh, dẫn đến O(log n) phép so sánh trong trường hợp xấu nhất.

Nếu yêu cầu xác định **vị trí chèn** của một khóa không có trong mảng, tồn tại `n+1` khoảng cần phân biệt:

```text
x < a[0]
a[0] < x < a[1]
...
a[n-2] < x < a[n-1]
a[n-1] < x
```

Trong mô hình chỉ so sánh thứ tự, cần tối thiểu Ω(log(n+1)) câu hỏi nhị phân trong trường hợp xấu nhất để phân biệt những khoảng ấy. Tìm kiếm nhị phân đạt chặn trên O(log n), nên về bậc tăng trưởng nó là tối ưu cho bài toán này trong mô hình đang xét.

Với mảng **chưa sắp xếp** và chỉ được kiểm tra từng phần tử bằng quan hệ bằng nhau, một truy vấn tìm khóa vắng mặt phải loại trừ toàn bộ `n` ứng viên trong trường hợp xấu nhất: Θ(n) phép so sánh. Tuyên bố này áp dụng cho mô hình và thông tin sẵn có đã nêu; nếu đã có chỉ mục bổ sung, phân tích phải cộng chi phí xây và duy trì chỉ mục đó.

### 5.1. Mã đếm vị trí khảo sát

```python
def binary_search_counted(values, target):
    """values đã sắp tăng dần; trả (vị trí, số lần khảo sát)."""
    left = 0
    right = len(values) - 1
    probes = 0

    while left <= right:
        middle = (left + right) // 2
        probes += 1

        if values[middle] == target:
            return middle, probes
        if values[middle] < target:
            left = middle + 1
        else:
            right = middle - 1

    return -1, probes


data = [2, 4, 6, 8, 10, 12, 14]
assert binary_search_counted(data, 8) == (3, 1)
assert binary_search_counted(data, 12) == (5, 2)
```

Biến `probes` đếm **lần khảo sát phần tử giữa**, không phải tổng số toán tử so sánh khóa: một lần không tìm thấy trong mã có thể dùng cả `==` và `<`. Hai cách đếm vẫn khác nhau tối đa một hệ số hằng trong ví dụ này.

## 6. Thuật toán vượt ra ngoài mô hình so sánh

Không có mâu thuẫn giữa cận dưới Ω(n log n) của sắp xếp thuần so sánh và các thuật toán sau:

- **Counting sort:** dùng giá trị khóa làm chỉ số trong một bảng đếm.
- **Radix sort:** xử lý các chữ số hoặc nhóm bit của khóa theo từng lượt.
- **Bucket sort:** phân phối vào bucket dựa trên miền giá trị, với thời gian phụ thuộc phân bố và cách xử lý bucket.
- **Hash Map:** tính hash từ biểu diễn khóa để định vị bucket thay vì chỉ so sánh thứ tự giữa khóa.

Các phương pháp này dựa trên **khả năng khai thác biểu diễn của khóa** mà mô hình so sánh thuần túy không cho phép.

### 6.1. Counting sort và miền khóa `K`

Giả sử đầu vào gồm `n` số nguyên với giá trị nằm trong `[0,K-1]` và ta có thể dùng mỗi số làm chỉ số mảng trong O(1).

```python
def counting_sort(values, K):
    if K < 0:
        raise ValueError("K phải không âm")

    counts = [0] * K

    for x in values:
        if not 0 <= x < K:
            raise ValueError("giá trị ngoài miền [0, K)")
        counts[x] += 1

    result = []
    for value, amount in enumerate(counts):
        result.extend([value] * amount)

    return result


assert counting_sort([3, 1, 0, 3, 2, 1], 4) == [0, 1, 1, 2, 3, 3]
```

Với các thao tác đếm/ghi một phần tử có chi phí O(1) theo mô hình RAM thích hợp:

\[
T(n,K)=\Theta(n+K).
\]

Bộ nhớ cần O(n+K) nếu tính cả mảng kết quả; vùng bảng đếm riêng là Θ(K).

Nếu `K=O(n)`, thời gian là O(n), **không vi phạm** cận dưới của sắp xếp bằng so sánh vì thuật toán đã sử dụng khóa làm chỉ số trực tiếp.

Nếu `K` cực lớn so với `n`, ví dụ chỉ có 10 khóa nhưng miền có hàng tỷ khả năng, việc cấp phát bảng dài `K` có thể không phù hợp. Chi phí **phải nêu cả `K`**, không chỉ `n`.

### 6.2. Radix sort và số chữ số

Với các khóa gồm `d` chữ số trên cơ số `K`, nếu mỗi lượt phân loại một chữ số dùng counting sort thích hợp, mô hình phổ thông cho thời gian:

\[
T(n,d,K)=O(d(n+K)).
\]

`d` phụ thuộc số bit hoặc số chữ số của khóa. Nếu giả định `d` là hằng số nhưng thực tế khóa dài tùy ý, kết luận “O(n)” có thể sai.

Tóm lại, **nói một thuật toán sắp xếp “tuyến tính” phải kèm điều kiện về miền giá trị, số chữ số và mô hình thao tác**.

## 7. Mô hình RAM: thao tác và truy cập ngẫu nhiên

RAM (*Random Access Machine*) trừu tượng hóa một máy có các ô nhớ được đánh địa chỉ. Điểm nổi bật là ta có thể đọc hoặc ghi **một ô bất kỳ theo địa chỉ đã biết** mà không phải đi từ ô đầu tới ô cần đọc.

Trong phiên bản **RAM chi phí đơn vị** (*unit-cost RAM*), các thao tác nguyên thủy được chỉ định có giá O(1), chẳng hạn:

| Thao tác | Chi phí trong RAM cơ bản | Điều kiện ngầm |
| --- | --- | --- |
| Đọc/ghi một ô ở địa chỉ hợp lệ | O(1) | Địa chỉ được biểu diễn và tính toán theo mô hình |
| So sánh hai giá trị vừa ô | O(1) | Phép so sánh nằm trong tập phép toán được phép |
| Cộng/trừ chỉ số | O(1) | Số và kết quả thuộc miền mà mô hình cho một bước |
| Dịch chuyển tham chiếu `next` | O(1) cho một liên kết | Đã có tham chiếu tới nút hiện tại |
| Phép bitwise trên một từ | O(1) nếu được cho phép | Toán hạng vừa từ máy |
| Nhân/chia | Không mặc định trong mọi biến thể | Phải nói rõ có phải thao tác nguyên thủy O(1) hay không |

Một định nghĩa RAM cụ thể có thể cho phép phép nhân, chia hay dịch bit trong O(1); định nghĩa khác không. **Không nên dùng các phép toán mạnh không được liệt kê rồi coi chúng “miễn phí”.**

### 7.1. Vì sao mảng truy cập O(1)?

Với mảng các ô cùng kích thước, khi có địa chỉ cơ sở `base` và chỉ số hợp lệ `i`, vị trí ô `i` được tính theo:

\[
\operatorname{address}(a[i])
=\operatorname{base}+i\cdot s,
\]

trong đó `s` là kích thước mỗi ô hoặc một bước đơn vị địa chỉ phù hợp.

Trong RAM, tính địa chỉ và đọc ô dùng một số lượng hằng số thao tác, **miễn là số chỉ địa chỉ và phép toán tính địa chỉ nằm trong miền từ máy được cho phép**.

Với danh sách liên kết, chỉ có tham chiếu `head` và liên kết `next`. Không có công thức chung để lấy nút thứ `i` từ `head` bằng một phép tính địa chỉ. Muốn tới nút thứ `i`, thường phải đi qua Θ(i+1) nút.

**Giao diện “List” không đồng nhất với biểu diễn “array”.** Hai cách cài đặt có thể có cùng thao tác duyệt nhưng chi phí truy cập vị trí khác nhau.

### 7.2. Đơn vị nhớ là ô, từ hay byte?

Trong RAM trừu tượng, người phân tích thường đếm **số ô/từ** đã sử dụng. Trên máy thật, RAM được tính bằng byte và có kích thước từ nhất định. Khi đánh giá bộ nhớ cần ghi đơn vị:

- `S(n)=O(n)` **từ máy** không đồng nghĩa chính xác O(n) **bit**.
- Nếu mỗi từ có `w` bit, `O(n)` từ tương ứng `O(nw)` bit.
- Nếu `w` thay đổi cùng kích thước bài toán, hệ số `w` không được tự xem là hằng số khi đổi sang đơn vị bit.

## 8. Giả định về kích thước từ máy `w` bit

Mô hình **word-RAM** giới hạn mỗi từ máy có `w` bit. Một ô/từ lưu được các mẫu bit từ 0 đến `2^w-1`; khi diễn giải như số nguyên có dấu, miền biểu diễn tùy cách mã hóa.

Nếu bộ nhớ có `N` ô cần đánh địa chỉ riêng, địa chỉ cần ít nhất:

\[
w\ge\lceil\log_2 N\rceil
\]

bit trong một sơ đồ đánh địa chỉ trực tiếp theo ô.

Nếu cần lưu trực tiếp mọi khóa nguyên không âm trong miền `[0,U-1]` bằng một từ, ta cũng cần:

\[
w\ge\lceil\log_2 U\rceil.
\]

Hai điều kiện là **yêu cầu khác nhau**: kích thước bộ nhớ quyết định khả năng đánh địa chỉ, còn miền khóa quyết định một khóa có vừa một từ hay không.

### 8.1. Word-RAM thường giả định `w=Ω(log n)`

Khi nghiên cứu một họ bài toán có `n` phần tử, mô hình word-RAM thường chọn từ đủ dài để chứa chỉ số vị trí và địa chỉ, tức `w=Ω(log n)`. Nếu miền khóa và dung lượng bộ nhớ bị chặn bởi một đa thức theo `n`, giả định `w=Θ(log n)` có thể đủ cho nhiều phân tích lý thuyết.

Ký hiệu `w=Ω(log n)` **không có nghĩa** mọi chương trình chạy trên CPU 64 bit đều có `w` tăng theo `n`. Máy thật có kích thước từ cố định và không thể tăng `n` vô hạn mà vẫn giữ mọi chỉ số trong một từ. Trong phân tích tiệm cận, ta xét **một họ mô hình** với từ đủ lớn cho từng kích thước bài toán.

### 8.2. Ví dụ về sức chứa của một từ

Giả sử từ máy `w=64` bit:

- Có thể biểu diễn `2^{64}` mẫu bit khác nhau.
- Một số nguyên không âm nhỏ hơn `2^{64}` vừa về mặt bit.
- Một giá trị cần 200 bit **không vừa một từ 64 bit**.

Muốn lưu và cộng số 200 bit, ta phải dùng nhiều từ hoặc biểu diễn số nguyên lớn. Không được mặc định “200 bit chỉ là một biến integer, nên cộng nó O(1)” theo word-RAM 64 bit.

### 8.3. Tràn số cũng là vấn đề hợp đồng

Một phép cộng hai từ `w` bit có thể tạo kết quả cần `w+1` bit. Cài đặt phải quy định:

- Phép toán lấy kết quả modulo `2^w`?
- Phát hiện và báo lỗi tràn?
- Nâng lên kiểu số nguyên nhiều từ?
- Dùng quy tắc số nguyên có dấu cụ thể?

Những lựa chọn này ảnh hưởng **tính đúng**. Một thuật toán tính chỉ số heap `2i+1` phải bảo đảm chỉ số/địa chỉ được tính hợp lệ, không âm và không tràn theo ngữ nghĩa đang dùng. Giới hạn thời gian O(1) cho phép tính chỉ số không biện minh cho việc bỏ kiểm tra phạm vi cần thiết.

## 9. Unit-cost RAM với số nguyên vô hạn có thể phi thực tế

Giả sử ta dùng một mô hình quá mạnh:

> Một thanh ghi chứa số nguyên có bao nhiêu bit cũng được, và cộng/nhân hai số bất kỳ đều O(1).

Nếu trong vòng lặp ta liên tục nhân đôi một số:

```python
def huge_number(n):
    value = 1
    for _ in range(n):
        value *= 2
    return value
```

Sau `n` lần nhân đôi, giá trị là `2^n`, cần `n+1` bit để biểu diễn. Phân tích “mỗi vòng có một phép nhân, vậy O(n) thời gian” là đúng **trong mô hình unit-cost vô hạn vừa giả định**, nhưng không thể coi đó là mô hình chi phí bit của phép toán trên máy thật.

Trong **word-RAM có từ `w` bit**, khi giá trị vượt một từ, phải dùng biểu diễn nhiều từ hoặc giới hạn phép toán. Trong **mô hình bit**, việc tạo ra và lưu kết quả có `n+1` bit đã yêu cầu Ω(n) bit đầu ra; các phép nhân/copy trung gian cũng có chi phí phụ thuộc độ dài.

### 9.1. Cộng hai số lớn có chi phí khác O(1)

Nếu hai số nguyên có độ dài tối đa `k` bit, phép cộng nhị phân theo cách thông thường có thể cần O(k) phép toán bit, hoặc O(⌈k/w⌉) thao tác từ máy với thuật toán cộng theo từng từ, bỏ qua chi phí hằng số.

Ví dụ, cộng số có một triệu bit trên máy 64 bit phải xử lý nhiều khối từ. Python hỗ trợ số nguyên độ dài tùy ý, nhưng **kiểu `int` của Python không có nghĩa mọi phép toán số học O(1)**.

### 9.2. Không phải mọi phép toán số lớn có cùng bậc

| Phép toán | Một từ `w` bit | Số nguyên nhiều từ |
| --- | --- | --- |
| So sánh bằng/nhỏ hơn | O(1) theo word-RAM | Có thể phải xem nhiều từ, trường hợp xấu phụ thuộc độ dài |
| Cộng/trừ | O(1) nếu mô hình cho phép | O(⌈k/w⌉) với cộng theo từ cho số dài `k` bit |
| Nhân | O(1) **nếu** mô hình cho phép nhân từ | Thuật toán nhân nhiều từ có chi phí phụ thuộc số từ và thuật toán được chọn |
| Băm khóa số lớn | Không tự động O(1) | Thường cần xử lý hoặc kết hợp thông tin từ nhiều từ |
| Sao chép giá trị | O(1) nếu giá trị nằm trong một từ | Sao chép đầy đủ `k` bit có thể cần Θ(⌈k/w⌉) thao tác từ |

Không gán một chặn cụ thể như O(k²) cho **mọi** thuật toán nhân số lớn: có nhiều thuật toán nhân với độ phức tạp khác nhau. Chỉ cần nhớ rằng **chi phí phụ thuộc kích thước biểu diễn**.

## 10. Đếm phép so sánh, thao tác từ máy và phép toán bit

Đây là ba thước đo khác nhau, mặc dù chúng có thể cùng dùng ký hiệu O.

Giả sử một thuật toán tìm kiếm duyệt `n` khóa, mỗi khóa dài `k` bit:

- Trong **mô hình so sánh**, có nhiều nhất `n` phép so sánh khóa.
- Nếu một lần so sánh khóa dài đòi kiểm tra tới `k` bit, số phép bit có thể là O(nk).
- Nếu khóa được biểu diễn bằng `t=⌈k/w⌉` từ và so sánh theo các từ, số thao tác từ máy có thể là O(nt).

Với các khóa phân biệt và việc so sánh dừng sớm tại từ khác đầu tiên, thời gian **trung bình** theo một phân bố khóa cụ thể có thể ít hơn. Nhưng chặn trường hợp xấu vẫn phải tính trường hợp hai khóa chung tiền tố dài.

### 10.1. Ví dụ đối chiếu

Giả sử:

- `n=1.000` khóa.
- Mỗi khóa dài `k=256` bit.
- Từ máy `w=64` bit.

Một khóa cần `t=⌈256/64⌉=4` từ. Nếu mỗi lần so sánh phải xem cả 4 từ, tìm tuyến tính thất bại có thể cần gần `4n` thao tác so sánh từ, thay vì `n` phép so sánh **logic**.

Đó không phải mâu thuẫn. Một phép so sánh logic đã được triển khai bằng nhiều thao tác từ máy.

### 10.2. Bảng quy đổi đơn vị

| Phát biểu | Diễn giải đúng |
| --- | --- |
| “O(n) phép so sánh khóa” | Đếm số lần gọi phép so sánh, chưa biết giá từng lần |
| “O(n) thao tác từ máy” | Mỗi thao tác nằm trên một số hữu hạn từ `w` bit theo tập lệnh mô hình |
| “O(n) phép toán bit” | Chi phí được đo theo đơn vị bit, phù hợp khi số lớn |
| “O(n) từ bộ nhớ” | Cần có thể lên tới O(nw) bit nếu tính theo `w` |
| “O(n) byte bộ nhớ” | Đã cố định byte làm đơn vị; khác với số đối tượng hoặc số ô biến độ dài |

Để công thức có ý nghĩa, cần **định nghĩa cả tham số kích thước lẫn đơn vị đo chi phí**.

## 11. Phân tích không gian theo từ và theo bit

Một mảng `n` số nguyên vừa một từ dùng Θ(n) từ cho payload, tương đương Θ(nw) bit. Nếu có `C` ô đã cấp phát nhưng chỉ `n` ô sử dụng, vùng đệm là Θ(C) từ, không phải Θ(n) từ khi `C` có thể lớn hơn nhiều `n`.

### 11.1. Bitset và nén dữ liệu

Một mảng `n` giá trị boolean có thể biểu diễn bằng:

- Mỗi boolean một từ: Θ(n) từ = Θ(nw) bit.
- Một bit cho mỗi boolean: Θ(n) bit = Θ(⌈n/w⌉) từ.

Nếu mô hình word-RAM cho phép phép toán mask, shift và truy cập từ theo chỉ số O(1), kiểm tra hoặc sửa **một bit ở vị trí đã biết** vẫn có thể O(1) thao tác từ.

Tuy nhiên, việc duyệt và xử lý riêng **từng** boolean có thể mất Θ(n) lần xử lý. Các phép xử lý hàng loạt như AND/OR trên toàn bộ bitset có thể thực hiện theo từng từ, tốn Θ(⌈n/w⌉) thao tác từ. Nếu cần đếm bit 1 bằng lệnh `popcount`, phải nêu rõ lệnh đó có được coi O(1) trong mô hình hay không.

### 11.2. Mã minh họa bitset đơn giản

```python
def set_bit(bits, position):
    if position < 0:
        raise IndexError("position phải không âm")
    return bits | (1 << position)


def has_bit(bits, position):
    if position < 0:
        raise IndexError("position phải không âm")
    return (bits & (1 << position)) != 0


mask = 0
mask = set_bit(mask, 3)
mask = set_bit(mask, 8)
assert has_bit(mask, 3)
assert not has_bit(mask, 4)
```

Đoạn Python dùng `int` với độ dài tùy ý. Khi `position` rất lớn, `1 << position` tạo số nguyên lớn, nên thao tác trong Python **không phải O(1) theo word-RAM `w` cố định**. Nếu muốn hiện thực bitset gồm nhiều từ `w` bit, ta thường tính `word_index=position//w` và `bit_index=position%w`, sau đó truy cập và sửa từ tương ứng.

### 11.3. Đồ thị và số bit lưu cạnh

Ma trận kề cho đồ thị có `V` đỉnh cần `V²` vị trí quan hệ cạnh. Nếu lưu một bit cho mỗi vị trí, payload là Θ(V²) bit, tương đương Θ(⌈V²/w⌉) từ. Nếu lưu một boolean bằng một byte hoặc một đối tượng riêng, byte thực tế có thể lớn hơn đáng kể.

Danh sách kề thường dùng Θ(V+E) mục cấu trúc, nhưng mỗi định danh đỉnh có thể cần Θ(log V) bit nếu được đánh chỉ số từ 0 đến `V-1`. Nói “danh sách kề dùng O(V+E) bộ nhớ” thường là **O(V+E) từ hoặc mục**, với điều kiện các định danh và liên kết vừa từ máy.

## 12. Mảng, danh sách liên kết, cây và heap dưới các mô hình

| Cấu trúc và thao tác | Mô hình RAM/word-RAM thông dụng | Giả định đáng chú ý |
| --- | --- | --- |
| Mảng `a[i]` | O(1) | Chỉ số, địa chỉ vừa từ và ô có thể đọc trực tiếp |
| Mảng động `append` | O(1) khấu hao | Tăng sức chứa theo hệ số; một lần resize có thể Θ(n) |
| Mảng chèn đầu | Θ(n) xấu nhất | Cần di chuyển `n` phần tử |
| Danh sách liên kết lấy nút đầu | O(1) | Có tham chiếu `head` |
| Danh sách liên kết lấy nút thứ `i` | O(i+1), xấu nhất O(n) | Chỉ có các liên kết `next`, không có chỉ mục |
| Stack `push/pop` bằng liên kết đầu | O(1) theo mô hình cấp phát nút | Một lần cấp phát nút được tính hằng số |
| Queue `enqueue/dequeue` bằng liên kết đầu/đuôi | O(1) theo mô hình | Duy trì `head`, `tail` hợp lệ |
| BST không tự cân bằng `find` | O(h), xấu nhất O(n) | Chiều cao `h` có thể tuyến tính |
| Cây cân bằng `find/insert/delete` | O(log n) xấu nhất | So sánh khóa O(1), giữ bất biến cân bằng |
| Heap nhị phân `insert/extract_min` | O(log n) xấu nhất | So sánh ưu tiên và truy cập mảng O(1) |
| Heap đọc đỉnh | O(1) | Heap không đồng nghĩa toàn bộ mảng được sắp |
| Hash Map `get` | O(1) kỳ vọng | Tính hash và so sánh O(1), phân bố và tải phù hợp |

Một bảng như vậy không thể thay thế việc nêu **hợp đồng phép toán**. Stack có quy tắc LIFO, Queue FIFO, Heap theo độ ưu tiên, còn Map theo khóa. Chi phí thấp cho một phép toán **không cho phép** thay đổi phần tử mà người dùng nhận được.

### 12.1. Cây và chi phí so sánh khóa dài

Một cây cân bằng có chiều cao O(log n), nên một lời gọi `find` đi qua O(log n) nút trong trường hợp xấu nhất. Nếu mỗi lần so sánh khóa dài `k` bit cần O(⌈k/w⌉) thao tác từ, thời gian có thể là:

\[
T_{\mathrm{find}}(n,k,w)
=O\left(\log(n+1)\cdot\left\lceil\frac{k}{w}\right\rceil\right),
\]

bỏ qua các chi phí hằng số khác.

Khi khóa vừa một từ, `⌈k/w⌉=1` và ta thu được O(log n). Khi khóa là chuỗi dài tùy ý, không được tự gắn mác O(log n) **thao tác từ** nếu chưa xét chi phí so sánh.

### 12.2. Heap và chỉ số tính toán

Heap lưu trong mảng thường xác định con của ô `i` tại chỉ số `2i+1` và `2i+2`. Tính chỉ số này O(1) trong word-RAM nếu kết quả vừa từ máy; việc điều chỉnh theo chiều cao heap tốn O(log n) bước so sánh/hoán đổi.

Nếu đối tượng ưu tiên là một số lớn hoặc chuỗi dài, chi phí so sánh vẫn có thể tăng theo kích thước biểu diễn. Chiều cao O(log n) chỉ chặn **số nút đi qua**, không tự chặn số thao tác bit.

## 13. Bảng băm: O(1) kỳ vọng cần thêm những giả định nào?

Bảng băm không dùng riêng quan hệ thứ tự như BST. Nó tính giá trị hash từ khóa và xác định bucket hoặc chuỗi dò trong bảng.

Câu “Hash Map tìm O(1)” chỉ có ý nghĩa khi xác định ít nhất:

1. **Chi phí tính hash:** một khóa có vừa một từ không, hay phải đọc `k` byte?
2. **Chi phí kiểm tra bằng nhau:** so sánh hai khóa có giá hằng số trong mô hình hay không?
3. **Phân bố va chạm:** có giả định băm đủ đều hoặc chọn hàm băm từ họ phù hợp?
4. **Hệ số tải:** số mục và số bucket có được duy trì hợp lý?
5. **Chi phí tái băm:** đã tính vào `put` hoặc chứng minh khấu hao chưa?

Với chaining, nếu `n` khóa được chia vào `b` bucket, hệ số tải `α=n/b`. Dưới giả định phân bố đều phù hợp, chi phí xem mục trong bucket có thể O(1+α) kỳ vọng. Nếu `α=O(1)` và hash/so sánh khóa O(1), tra cứu có thể O(1) kỳ vọng theo `n`.

Nếu mọi khóa cùng vào một bucket, tìm khóa vắng mặt có thể Θ(n). Nếu khóa dài `k` ký tự, riêng việc tính hash có thể O(k) ngay cả khi chỉ có một mục trong bucket.

### 13.1. Hàm băm không “miễn phí” trong mô hình so sánh

Cận dưới Ω(log n) cho tìm vị trí theo thứ tự và cận kỳ vọng O(1) cho Hash Map **không mâu thuẫn**:

- Tìm kiếm dựa thuần trên so sánh thứ tự bị giới hạn bởi số câu hỏi so sánh.
- Hash Map sử dụng biểu diễn khóa để tính hash và tra địa chỉ, là **khả năng mạnh hơn** mô hình so sánh thuần túy.

Nếu dùng một đối tượng khóa tùy ý chỉ hỗ trợ toán tử `<` mà không có cách băm hợp lệ, ta không thể tự áp dụng kết luận O(1) kỳ vọng của Hash Map.

### 13.2. Một lần `put` có thể đắt

Ngay cả khi chi phí tra bucket kỳ vọng O(1), một `put` gây mở rộng và tái băm nhiều mục có thể tốn Θ(n) cho lần đó. Với chính sách tăng trưởng phù hợp, có thể chứng minh tổng công việc tái băm được phân bổ trên một chuỗi thao tác: O(1) **khấu hao** cho phần duy trì sức chứa.

Đây là hai tính chất khác nhau:

- **Kỳ vọng:** phụ thuộc xác suất va chạm.
- **Khấu hao:** phụ thuộc cấu trúc và lịch sử mở rộng.

Chúng cần được phát biểu riêng, không tự động suy ra lẫn nhau.

## 14. Đồ thị: số đỉnh, cạnh và đơn vị lưu trữ

Với đồ thị có `V` đỉnh và `E` cạnh:

| Biểu diễn | Bộ nhớ thường nêu | Kiểm tra cạnh `(u,v)` | Duyệt toàn bộ |
| --- | --- | --- | --- |
| Ma trận kề | Θ(V²) ô hoặc bit tùy cách đóng gói | O(1) theo RAM khi đã có chỉ số đỉnh | O(V²) nếu quét mọi hàng |
| Danh sách kề bằng danh sách | Θ(V+E) mục/từ | O(deg(u)+1) | O(V+E) |
| Tập kề băm | O(V+E) mục/từ kỳ vọng về dung lượng phù hợp | O(1) kỳ vọng | O(V+E) kỳ vọng, tùy cách duyệt |

Với đồ thị vô hướng, mỗi cạnh thường được ghi trong danh sách kề của cả hai đầu; hệ số 2 không thay đổi bậc O(V+E). Nhưng **kích thước định danh đỉnh, ô metadata và chỉ mục** ảnh hưởng số byte vật lý.

### 14.1. Khi đỉnh được định danh bằng chuỗi

Nếu mỗi đỉnh có mã chuỗi dài, việc tìm ra chỉ số hoặc node từ định danh có thể cần băm/so sánh chuỗi. Công thức BFS O(V+E) theo RAM thường giả định mỗi đỉnh đã có định danh chỉ số hoặc tham chiếu có thể xử lý trong O(1).

Nếu thuật toán liên tục thực hiện hash chuỗi lớn để xác định đỉnh, phải tính thêm chi phí đó. Cũng cần phân biệt một đồ thị lưu bằng **đối tượng nút và con trỏ** với một đồ thị lưu bằng **mảng chỉ số đóng gói**.

### 14.2. Ma trận kề bitset có thể tận dụng thao tác từ

Với bitset đóng gói, mỗi từ mang `w` quan hệ cạnh. Nếu thuật toán chỉ cần thực hiện phép OR/AND hàng loạt trên hàng kề và mô hình cho phép phép bitwise O(1) trên từ, có thể xử lý `w` bit trong một bước từ máy.

Tuy nhiên, việc **liệt kê chính xác từng láng giềng** vẫn phải tạo ra `deg(u)` kết quả; không thể xuất `deg(u)` định danh mà không trả chi phí liên quan. Phải phân biệt xử lý hàng loạt trên bit với việc xuất từng phần tử.

## 15. Mô hình RAM và máy thật: bộ nhớ không đồng nhất về độ trễ

Mô hình RAM cho phép đọc ô ở địa chỉ bất kỳ với cùng mức chi phí O(1). Trong thực tế:

- Đọc dữ liệu còn trong cache có thể nhanh hơn nhiều so với đọc RAM chính.
- Truy cập tuần tự dễ tận dụng cache và cơ chế đọc trước (*prefetch*).
- Danh sách liên kết có thể gặp nhiều lần truy cập bộ nhớ rải rác.
- Truy cập đĩa hoặc mạng thường đắt hơn thao tác CPU.
- Cấp phát/thu hồi, phân mảnh và thu gom rác có thể tạo độ trễ đỉnh.

Vì vậy hai thuật toán cùng O(n) thao tác RAM không nhất thiết có cùng số giây thực tế.

### 15.1. Ví dụ mảng so với danh sách liên kết

Cả hai đều duyệt `n` phần tử trong Θ(n) bước logic:

- Với mảng liên tiếp, CPU thường có thể đọc theo từng dòng cache hiệu quả.
- Với danh sách liên kết, CPU phải đi theo `next`, và nút kế tiếp có thể không nằm gần trong bộ nhớ.

Mô hình RAM giải thích **bậc số bước**; phép đo trên phần cứng cụ thể mới đánh giá chênh lệch về cache, cấp phát và hằng số ẩn.

### 15.2. Mô hình bộ nhớ ngoài và số lần chuyển khối

Khi dữ liệu lớn hơn RAM, một mô hình phổ biến đếm **số lần truyền khối** giữa bộ nhớ chậm và nhanh.

Gọi:

- `B`: số phần tử hoặc từ máy trong một khối truyền dữ liệu.
- `M`: sức chứa của bộ nhớ nhanh, theo cùng đơn vị.
- `n`: số phần tử cần xử lý.

Đọc tuần tự `n` phần tử bố trí liên tiếp có thể cần khoảng:

\[
\Theta\left(\left\lceil\frac{n}{B}\right\rceil\right)
\]

lần đọc khối, nếu các khối được sử dụng hiệu quả.

Một tìm kiếm nhị phân trên mảng vẫn chỉ cần O(log n) lần so sánh, nhưng các bước nhảy tới vị trí giữa có thể cần những lần đọc khối rời rạc. Đối với chỉ mục dữ liệu ngoài, cây B (*B-tree*) được thiết kế để tăng số nhánh trên mỗi nút/khối; một truy vấn có thể cần O(log_B n) lần đọc khối trong mô hình phù hợp, khác với số phép so sánh bên trong các khối.

**Đây là hai thước đo khác nhau:** một thuật toán có ít phép so sánh chưa chắc có ít thao tác I/O.

### 15.3. Mô hình cache-aware và cache-oblivious

Một số thuật toán chủ động dùng `B,M` để tối ưu truy cập bộ nhớ (*cache-aware*); một số được thiết kế để hoạt động tốt trên nhiều tầng cache mà không cần biết chính xác tham số (*cache-oblivious*).

Bài học cơ sở vẫn là: nếu chi phí truyền dữ liệu chi phối, hãy dùng hoặc bổ sung mô hình phù hợp thay vì suy tất cả từ số bước RAM.

## 16. Viết phân tích đúng đơn vị từ một đoạn mã

Xét phép cộng toàn bộ phần tử:

```python
def total(values):
    result = 0
    for value in values:
        result += value
    return result
```

### Trường hợp A — Mảng gồm số nguyên vừa từ

Nếu `values` chứa `n` số nguyên nhỏ và **tổng tích lũy cũng luôn vừa trong một từ** theo ngữ nghĩa phép cộng đã chọn, mỗi vòng có O(1) thao tác từ. Khi đó:

\[
T(n)=\Theta(n),\qquad S_{\mathrm{aux}}=O(1)\text{ từ}.
\]

### Trường hợp B — Số nguyên lớn tùy ý

Nếu mỗi `value` có `k` bit, `result` có thể dài hơn `k` bit theo số phần tử. Với phép cộng số lớn theo các từ, chi phí mỗi lần cộng phụ thuộc độ dài toán hạng và số từ cần truyền nhớ/carry.

Vì vậy không thể nói `T(n)=Θ(n)` **thao tác từ** mà không thêm giả định. Cần mô hình hóa độ dài bit của tổng trung gian hoặc chặn `k+\lceil\log_2 n\rceil` bit trong trường hợp cộng `n` số nguyên không âm, mỗi số không quá `k` bit.

Với phép cộng nhiều từ thông thường, một chặn trên sơ bộ là:

\[
T(n,k,w)
=O\left(n\left(1+\left\lceil
\frac{k+\log_2(n+1)}{w}
\right\rceil\right)\right).
\]

Đây là **chặn trên cho cách cộng theo từ**; không tuyên bố nó là tối ưu cho mọi kỹ thuật cộng hoặc trường hợp các giá trị nhỏ. Công thức làm rõ phần công việc bị ẩn khi chỉ đếm `n` lượt vòng lặp.

### 16.1. Tại sao có `log n` trong số bit tổng?

Nếu mỗi số nguyên không âm `x_i < 2^k`, tổng:

\[
0\le\sum_{i=1}^{n}x_i<n2^k.
\]

Do đó số bit của tổng không vượt quá xấp xỉ `k+\lceil\log_2(n+1)\rceil` bit. Kích thước **giá trị trung gian** cũng là một tham số của chi phí bit, không chỉ số phần tử đầu vào.

### 16.2. Chú ý thời gian xây và sao chép cấu trúc

Nếu dữ liệu đến từ file văn bản, phải tính thời gian phân tích chuỗi thành số. Nếu trước khi tính tổng ta sao chép mảng thành cấu trúc mới, phải tính cả sao chép và vùng nhớ phát sinh nếu mục tiêu là **toàn vòng đời**.

Một công thức đúng cho một phép toán đơn lẻ không tự mô tả chi phí chuẩn bị và bảo trì cấu trúc dữ liệu trong ứng dụng.

## 17. Đọc một khẳng định Big-O: checklist các giả định bị ẩn

Ví dụ với câu “Hash Map truy vấn O(1)”, hãy kiểm tra:

1. `n` là số khóa hiện có hay số bucket?
2. Khóa có vừa một từ hay phải hash `k` ký tự?
3. Hàm băm và so sánh có nằm trong tập thao tác O(1) của mô hình?
4. Có giả định phân bố băm nào để xử lý va chạm?
5. Đó là **kỳ vọng** hay **xấu nhất**?
6. Cấu trúc có thể phải resize/rehash sau cập nhật không?
7. Đang tính thời gian tra một khóa hay cả chi phí tạo chỉ mục?
8. Bộ nhớ tính theo số mục, số từ hay byte?
9. Có cần kết quả theo thứ tự khóa hay chỉ cần truy vấn chính xác?
10. Có giới hạn độ trễ mỗi lời gọi hay chỉ mục tiêu thông lượng?

Một khẳng định độ phức tạp đáng tin cậy nên nêu **đúng phạm vi** thay vì thêm chữ “luôn” ở những nơi cần giả định.

### 17.1. Mẫu ghi chú gọn cho từng thuật toán

```text
Thuật toán / phép toán:
Đầu vào:
  n = số phần tử?
  k = số bit/ký tự của khóa?
  U = số giá trị khóa có thể có?
  V, E = đỉnh/cạnh nếu là đồ thị?

Mô hình:
  Comparison / unit-cost RAM / word-RAM / bit / I/O?
  Word size w = ?
  Các phép toán O(1) được phép:
  Đơn vị bộ nhớ: từ, bit hay byte?

Đếm chi phí:
  Số lần so sánh khóa:
  Chi phí một lần so sánh:
  Đọc/ghi/hoán đổi/cấp phát:
  Bộ nhớ phụ và bộ nhớ đầu ra:
  Tiền xử lý và cập nhật:

Bảo đảm:
  Tốt nhất, xấu nhất, kỳ vọng hay khấu hao?
  Phân bố ngẫu nhiên nào (nếu có)?
  Kết luận Big-O/Theta/Omega:
  Điều kiện nào khiến kết luận không còn áp dụng?
```

## 18. Các sai lầm mô hình hóa thường gặp

| Sai lầm | Vì sao không đúng | Cách khắc phục |
| --- | --- | --- |
| “Mọi sắp xếp đều cần Ω(n log n).” | Cận dưới này dành cho thuật toán thuần so sánh với khóa tùy ý. | Nêu mô hình; counting/radix có thêm giả định về miền khóa. |
| “Counting sort O(n) trong mọi trường hợp.” | Thời gian và bộ nhớ còn phụ thuộc `K`. | Ghi Θ(n+K), chỉ nói O(n) khi `K=O(n)`. |
| “So sánh hai khóa luôn O(1).” | Chuỗi hoặc số lớn có thể cần xem nhiều bit/từ. | Ghi chi phí theo độ dài `k`. |
| “RAM cho phép đọc địa chỉ vô hạn trong O(1).” | Không giới hạn độ dài địa chỉ là giả định quá mạnh. | Dùng word-RAM và nói rõ `w≥log N`. |
| “CPU 64 bit chứng minh mọi bài toán lớn đều có chỉ số O(1).” | Miền địa chỉ của từ cố định là hữu hạn. | Phân biệt máy thực và họ mô hình tiệm cận. |
| “Phép cộng số nguyên Python luôn O(1).” | `int` có độ dài tùy ý. | Phân tích số từ/bit của toán hạng và kết quả. |
| “O(n) từ chính là O(n) bit.” | Một từ chứa `w` bit. | Đổi thành O(nw) bit khi `w` là tham số. |
| “Hash Map O(1) xấu nhất.” | Va chạm và tái băm có thể đắt. | Nêu điều kiện kỳ vọng và khấu hao. |
| “Truy cập nhanh theo chỉ số nên linked list cũng O(1).” | Chỉ có con trỏ `head/next` thì phải đi qua liên kết. | Phân biệt mảng RAM và biểu diễn liên kết. |
| “Một phép đọc RAM luôn nhanh như nhau trên máy thật.” | Có cache, RAM, bộ nhớ ngoài và các tầng truy cập. | Dùng benchmark và mô hình I/O khi cần. |
| “Mảng bitset `n` bit cần `n` từ.” | Có thể đóng gói `w` bit vào một từ. | Tính Θ(⌈n/w⌉) từ. |
| “Mô hình càng mạnh thì cận dưới càng phổ quát.” | Cận dưới theo mô hình mạnh có thể yếu hơn; cận dưới của mô hình yếu không áp dụng cho mô hình mạnh. | Luôn ghi rõ tập thao tác cho phép. |

## 19. Bài tập vận dụng có gợi ý giải

### Bài 1 — Giới hạn dưới sắp xếp

Với `n` khóa phân biệt, hãy giải thích vì sao một thuật toán thuần so sánh cần Ω(n log n) so sánh trong trường hợp xấu nhất.

**Gợi ý:** Có `n!` hoán vị thứ tự. Cây quyết định nhị phân phải có ít nhất `n!` lá. Do đó chiều cao ít nhất `log₂(n!)=Ω(n log n)`. Đây là giới hạn về **phép so sánh khóa**, không phải mọi cách sắp xếp số nguyên.

### Bài 2 — Vì sao counting sort không mâu thuẫn?

Có `n=100.000` số nguyên không âm, tất cả nhỏ hơn `K=1.000`. Nếu các số dùng được làm chỉ số mảng O(1), hãy ước lượng chi phí counting sort.

**Gợi ý:** Thời gian Θ(n+K), bộ nhớ bảng đếm Θ(K) và vùng kết quả Θ(n). Vì `K=O(n)`, thời gian O(n). Thuật toán truy cập bảng theo giá trị khóa, vượt ngoài mô hình thuần so sánh.

### Bài 3 — Khi miền khóa quá lớn

Có 10 số nguyên nhưng mỗi số có thể thuộc miền `[0,10^{12})`. Dùng bảng đếm một ô cho mỗi giá trị có hợp lý không?

**Gợi ý:** `K=10^{12}` làm chi phí khởi tạo và bộ nhớ bảng Θ(K), quá lớn so với `n=10`. Cần chọn thuật toán khác hoặc cách biểu diễn thưa; không được gọi counting sort chỉ có O(n) trong bài này.

### Bài 4 — Độ dài từ và số ô nhớ

Một chương trình phải đánh địa chỉ `N=2^{40}` ô khác nhau bằng chỉ số trực tiếp. Theo mô hình địa chỉ nhị phân, từ máy cần ít nhất bao nhiêu bit chỉ để biểu diễn địa chỉ?

**Gợi ý:** `w≥log₂ N=40` bit. Nếu còn phải lưu khóa trong một miền lớn hơn, có thể cần từ dài hơn hoặc biểu diễn nhiều từ.

### Bài 5 — So sánh khóa dài

Có `n=5000` khóa dài `k=256` bit. Máy mô hình có `w=64` bit/từ. Trong trường hợp xấu nhất phải so sánh toàn bộ khóa, một lần so sánh cần xem bao nhiêu từ? Tìm tuyến tính có chặn trên bao nhiêu thao tác so sánh từ?

**Gợi ý:** Một khóa có `⌈256/64⌉=4` từ. Có thể cần tối đa O(4n)=O(20.000) bước xử lý từ cho 5000 lượt so sánh logic, bỏ qua chi phí khác. Tổng vẫn O(n⌈k/w⌉) theo các tham số.

### Bài 6 — Bộ nhớ mảng theo từ và bit

Một mảng gồm `n=10.000` từ, mỗi từ `w=64` bit, cần bao nhiêu bit payload? Nếu chỉ cần lưu 10.000 cờ boolean, bitset đóng gói cần bao nhiêu từ?

**Gợi ý:** Mảng đầy từ cần 640.000 bit. Bitset cần `⌈10.000/64⌉=157` từ, tương đương 10.048 bit đã cấp theo số từ; bỏ qua header.

### Bài 7 — Phép cộng số lớn

Vì sao vòng lặp cộng `n` số nguyên `k` bit trong Python không nhất thiết chỉ tốn Θ(n) thao tác từ máy?

**Gợi ý:** Tổng tích lũy có thể lớn hơn một từ; phép cộng nhiều từ phải xử lý dữ liệu theo độ dài bit. Với số không âm, độ dài tổng có thể lên tới `k+⌈log₂(n+1)⌉` bit. Cần mô hình theo `k,n,w`.

### Bài 8 — Hash Map hay cây cân bằng?

Một hệ thống lưu khóa số nguyên vừa một từ, cần tra theo khóa và đôi lúc duyệt khóa tăng dần. So sánh Hash Map với cây tìm kiếm cân bằng.

**Gợi ý:** Với hash/so sánh O(1) và phân bố thích hợp, Hash Map tra O(1) kỳ vọng nhưng không tự có thứ tự tăng dần; cây cân bằng có tra O(log n) trường hợp xấu nhất và duyệt có thứ tự. Lựa chọn phụ thuộc tần suất truy vấn, độ trễ yêu cầu, bộ nhớ và hợp đồng.

### Bài 9 — Mô hình RAM với dữ liệu trên đĩa

Một dãy có `n` phần tử liên tục trên đĩa, mỗi khối chứa `B` phần tử. Nếu đọc toàn bộ dãy theo thứ tự, cần khoảng bao nhiêu lần truyền khối? Vì sao số này khác số phép đọc ô RAM?

**Gợi ý:** Khoảng Θ(⌈n/B⌉) lần truyền khối; mỗi lần chuyển mang theo nhiều phần tử. Mô hình RAM vẫn tính Θ(n) lần xử lý từng phần tử nếu mỗi phần tử phải được xem.

### Bài 10 — Phân tích BST và khóa chuỗi

Một cây cân bằng chứa `n` khóa chuỗi dài tối đa `k` bit. Mỗi phép so sánh khóa tốn O(⌈k/w⌉) thao tác từ. Hãy lập công thức thời gian `find` trong trường hợp xấu nhất.

**Gợi ý:** Đi qua O(log n) nút, mỗi nút so sánh O(⌈k/w⌉) từ, nên O(log(n+1)⌈k/w⌉) thao tác từ. Chỉ rút về O(log n) khi chi phí so sánh khóa được xem là O(1).

## 20. Tự kiểm tra kiến thức và kết luận

Trước khi xem một bảng độ phức tạp là “sự thật tuyệt đối”, hãy tự trả lời:

1. **Mô hình so sánh giới hạn điều gì?** Chỉ cho khai thác quan hệ thứ tự khóa thông qua phép so sánh; vì thế mới có cận dưới Ω(n log n) cho sắp xếp thuần so sánh.
2. **Counting sort vì sao có thể tuyến tính?** Vì nó dùng trực tiếp giá trị khóa làm chỉ số, với miền `K` đủ nhỏ; thời gian Θ(n+K).
3. **RAM giải thích điều gì?** Đọc một ô theo địa chỉ có chi phí O(1) trong mô hình đã chọn; mảng có truy cập chỉ số trực tiếp còn danh sách liên kết phải đi qua nút.
4. **Kích thước từ `w` có vai trò gì?** Giới hạn lượng thông tin trong một từ, độ dài địa chỉ và kích thước khóa có thể xử lý bằng phép toán từ đơn lẻ.
5. **Tại sao số nguyên lớn làm thay đổi Big-O?** Một giá trị có `k` bit có thể cần nhiều từ, và phép toán trên nó phải xử lý nhiều phần của biểu diễn.
6. **Khi nào O(n) bộ nhớ không đủ thông tin?** Khi chưa biết đơn vị là từ, bit hay byte, và chưa tính sức chứa dư, vùng đệm, đối tượng/nút.
7. **Hash Map O(1) là loại kết luận nào?** Thường là kỳ vọng cho tra cứu dưới giả định băm, hệ số tải và chi phí khóa phù hợp; thao tác resize cần phân tích riêng.
8. **Mô hình RAM có mô tả cache và đĩa chính xác không?** Không; cần thêm số đo thực tế hoặc mô hình I/O/phân cấp bộ nhớ.

**Kết luận:** Độ phức tạp không chỉ là một biểu thức O(...). Nó là một phát biểu có điều kiện về **đầu vào, tập phép toán, giá mỗi phép toán và đơn vị bộ nhớ**. Mô hình so sánh phù hợp để nghiên cứu giới hạn của thuật toán dựa trên thứ tự khóa; mô hình RAM giải thích chi phí truy cập và thao tác cấu trúc; mô hình word-RAM bổ sung giới hạn `w` bit để ngăn giả định phi thực tế về số lớn. Khi các giả định được nêu rõ, ta mới có thể so sánh đáng tin cậy thời gian và bộ nhớ của mảng, danh sách liên kết, Stack, Queue, bảng băm, cây, heap và đồ thị, rồi chọn cấu trúc đúng cho từng bài toán.
