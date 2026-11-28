# Ứng dụng top-k, ghép nhiều dãy và lập lịch tác vụ

**Heap** không chỉ là cấu trúc dùng để minh họa thao tác *sift-up* và *sift-down*. Đặc điểm quan trọng nhất của nó là **phần tử ưu tiên nhất luôn có thể được xem nhanh ở gốc**, trong khi những phần tử khác không cần được sắp toàn cục. Ba ứng dụng thực tế sau giúp thấy rõ ích lợi đó:

1. **Top-k:** Giữ lại k phần tử tốt nhất trong một dòng dữ liệu lớn mà không lưu/sắp tất cả n phần tử.
2. **Ghép nhiều dãy đã sắp xếp (*k-way merge*):** Lấy phần tử nhỏ nhất tiếp theo từ k dãy đầu vào, mỗi dãy đã được sắp.
3. **Lập lịch tác vụ:** Khi nhiều công việc đã sẵn sàng, chọn công việc tiếp theo bằng quy tắc ưu tiên; xử lý đúng cả thời điểm đến, thời gian rảnh và hòa khóa.

Bài thuộc chương **Heap và hàng đợi ưu tiên** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Theo định hướng xây dựng nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, chúng ta sẽ bắt đầu từ **bất biến**, sau đó suy ra **thao tác, độ phức tạp thời gian và bộ nhớ**, để chọn cấu trúc thích hợp cho từng bài toán. Bài sử dụng **min-heap nhị phân** và thư viện chuẩn **heapq** trong Python 3.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhắc lại bất biến min-heap, max-heap và chi phí của **peek, push, pop, heapreplace, heapify**.
- Giải thích vì sao bài toán **k phần tử lớn nhất** nên dùng **min-heap chứa tối đa k ứng viên**.
- Chứng minh bất biến top-k: sau mỗi đầu vào, heap giữ **min(k, i)** khóa lớn nhất trong tiền tố đã đọc.
- Cài đặt top-k theo luồng với thời gian O(n log(k+1)), bộ nhớ O(k), xử lý k=0, k>n, khóa trùng và thứ tự xuất.
- Phân biệt **k entry lớn nhất** với **k giá trị phân biệt lớn nhất**, cùng quy tắc hòa khóa ưu tiên người đến sớm.
- Phát biểu bất biến **mỗi dãy đã sắp đóng góp tối đa một phần tử đầu chưa lấy** trong k-way merge.
- Mô phỏng và viết k-way merge bằng heap với tổng N phần tử, thời gian O(k + N log(k+1)) và bộ nhớ phụ O(k) nếu xuất kiểu iterator.
- Định nghĩa tác vụ với **thời điểm đến, mức ưu tiên, thời lượng chạy** và trạng thái **chưa đến / sẵn sàng / đang chạy / hoàn thành**.
- Viết bộ lập lịch **ưu tiên không ngắt** (*non-preemptive priority scheduling*), xử lý tác vụ đến trong lúc CPU đang chạy và các khoảng CPU rảnh.
- Tính thời gian chờ, thời điểm bắt đầu, hoàn thành, phân biệt **thứ tự ưu tiên** với **deadline** và vấn đề **starvation**.
- Nhận ra các lỗi trong quản lý heap như đặt sai khóa, đưa entry chưa sẵn sàng vào heap, quên đẩy phần tử tiếp theo của một dãy và so sánh payload khi hòa khóa.

## 2. Nền tảng chung: hàng đợi ưu tiên trên min-heap

**Binary min-heap** là cây nhị phân gần đầy đủ lưu theo mảng. Với mảng a chỉ số từ 0, tất cả i > 0 phải thỏa:

\[
a[\lfloor(i-1)/2\rfloor]\le a[i].
\]

Với **max-heap**, bất đẳng thức đổi chiều thành **≥**. Gốc của min-heap là một phần tử có khóa nhỏ nhất; gốc của max-heap là một phần tử có khóa lớn nhất. Những phần tử còn lại **không cần** nằm trong thứ tự đã sắp.

~~~text
Một min-heap hợp lệ:

             2
            / \
           5   3
          / \ /
         9  8 7

Mảng theo mức: [2, 5, 3, 9, 8, 7]

2 <= 5, 2 <= 3, 5 <= 9, 5 <= 8, 3 <= 7.
Nhưng 5 > 3: mảng chưa được sắp tăng dần.
~~~

Trong Python, thư viện chuẩn **heapq** thực hiện min-heap trên một list:

| Thao tác | Chức năng | Chi phí cơ bản |
| --- | --- | --- |
| **heapq.heapify(a)** | Xây min-heap tại chỗ trên list có sẵn | Θ(n) |
| **heapq.heappush(h, x)** | Thêm một entry | O(log n) |
| **heapq.heappop(h)** | Lấy và xóa entry nhỏ nhất | O(log n) |
| **h[0]** | Xem entry nhỏ nhất khi không rỗng | Θ(1) |
| **heapq.heapreplace(h, x)** | Xóa gốc rồi thêm x trong cùng thao tác | O(log n), h phải không rỗng |
| **len(h)** | Số entry đang nằm trong heap | Θ(1) |

Cận logarit dùng mô hình so sánh khóa O(1); đối với list động, việc mở rộng vùng chứa có chi phí cấp phát lại riêng và được phân tích khấu hao khi cần.

**Lưu ý về entry:** Heap có thể lưu tuple **(priority, tie_breaker, payload_id)**. Python so sánh tuple từ trái qua phải. Nên dùng **tie_breaker duy nhất** khi có khóa ưu tiên bằng nhau, để tránh so sánh payload không hỗ trợ toán tử thứ tự.

### 2.1. Ba bài toán, ba bất biến “nội dung heap”

| Ứng dụng | Những entry được phép có trong heap | Gốc là gì? |
| --- | --- | --- |
| **Top-k lớn nhất** | Tối đa k ứng viên tốt nhất đã đọc | **Yếu nhất** trong những ứng viên đang giữ |
| **K-way merge** | Tối đa một phần tử đầu chưa lấy của mỗi dãy | Phần tử **nhỏ nhất có thể xuất tiếp** |
| **Lập lịch ưu tiên** | Chỉ các tác vụ **đã đến, đang sẵn sàng** | Tác vụ có khóa ưu tiên cao nhất theo quy ước |

Cả ba cùng có thể dùng min-heap, nhưng **ý nghĩa mỗi entry** và **thời điểm được push** khác nhau. Một heap thỏa thứ tự cha–con vẫn có thể cho kết quả sai nếu thuật toán đưa vào **nhầm tập ứng viên**.

## 3. Top-k: định nghĩa chính xác yêu cầu

Cho dãy điểm:

~~~text
scores = [7, 1, 9, 3, 8, 4, 10, 2]
k = 3

Kết quả top-3 lớn nhất: [10, 9, 8]
~~~

Trong bài, “top-k lớn nhất” mặc định là **min(k,n) entry có khóa lớn nhất, tính cả số lần xuất hiện**. Ví dụ:

~~~text
scores = [9, 9, 8, 5]
k = 3

Top-3 entry (kể trùng lặp):  [9, 9, 8]
Top-3 giá trị phân biệt:     [9, 8, 5]
~~~

Hai kết quả này thuộc **hai đặc tả khác nhau**. Nếu đang xếp hạng khách hàng, hai khách hàng cùng điểm vẫn là hai entry riêng, không được tự xóa bớt.

### 3.1. Phương án sắp xếp toàn bộ

Cách đơn giản nhất là:

~~~python
scores = [7, 1, 9, 3, 8, 4, 10, 2]
top_three = sorted(scores, reverse=True)[:3]
assert top_three == [10, 9, 8]
~~~

Sắp xếp n entry với phép so sánh O(1) dùng O(n log n) thời gian trường hợp xấu nhất và **sorted** tạo danh sách mới kích thước O(n). Nếu n rất lớn, k nhỏ, hoặc dữ liệu đến như một luồng, ta không nhất thiết muốn lưu/sắp toàn bộ.

### 3.2. Tại sao top-k lớn nhất dùng min-heap?

Để quyết định một điểm x mới có đủ tốt hay không, chỉ cần biết **điểm thấp nhất trong nhóm k ứng viên đang giữ**.

Min-heap giữ tối đa k điểm sẽ đưa **ứng viên yếu nhất của top-k lên gốc**, tức **h[0]**:

- Heap chưa đủ k: thêm x.
- Heap đã đủ k, **x ≤ h[0]**: bỏ x, vì không cải thiện top-k.
- Heap đã đủ k, **x > h[0]**: loại gốc và thay bằng x.

Vì thế, lựa chọn min-heap để giữ **top-k lớn nhất** không hề ngược: min-heap giúp tìm nhanh **ứng viên cần bị thay thế nhất**.

## 4. Thuật toán top-k theo luồng và bất biến

Pseudocode:

~~~text
top_k_largest(stream, k):
    nếu k < 0: báo lỗi
    nếu k == 0: trả []

    h = min-heap rỗng

    cho mỗi phần tử x trong stream:
        nếu size(h) < k:
            push(h, x)
        ngược lại nếu x > h[0]:
            heapreplace(h, x)

    nếu yêu cầu thứ tự giảm dần:
        trả sorted(h, reverse=True)
    nếu chỉ cần tập giá trị:
        trả những entry trong h theo thứ tự bất kỳ
~~~

**Bất biến:** Sau khi đã đọc i entry, h chứa đúng **min(k,i) khóa lớn nhất** trong tiền tố đầu vào, tính cả số lần xuất hiện.

**Cơ sở:** Với i=0, heap rỗng, bất biến đúng.

**Duy trì:** Nếu heap chưa đủ k, giữ tất cả entry đã đọc. Nếu heap đã đủ k và x không lớn hơn gốc, có ít nhất k entry đang giữ có khóa ≥ x, nên x không nhất thiết thuộc tập top-k. Nếu x lớn hơn gốc, ta thay ứng viên yếu nhất bằng x và vẫn giữ đúng k ứng viên tốt nhất. Với khóa bằng nhau ở ranh giới, chọn entry nào là vấn đề **tie-breaking**, không ảnh hưởng đa tập các giá trị.

**Kết thúc:** Sau khi xử lý n entry, các khóa trong heap chính là top-k được yêu cầu.

### 4.1. Mô phỏng top-3

Với dữ liệu **[7, 1, 9, 3, 8, 4, 10, 2]**, k=3:

| Đọc x | Hành động | Các giá trị đang giữ, viết đã sắp để dễ nhìn | Min ở gốc |
| ---: | --- | --- | ---: |
| 7 | Push | [7] | 7 |
| 1 | Push | [1, 7] | 1 |
| 9 | Push | [1, 7, 9] | 1 |
| 3 | 3 > 1, thay 1 | [3, 7, 9] | 3 |
| 8 | 8 > 3, thay 3 | [7, 8, 9] | 7 |
| 4 | 4 ≤ 7, bỏ qua | [7, 8, 9] | 7 |
| 10 | 10 > 7, thay 7 | [8, 9, 10] | 8 |
| 2 | 2 ≤ 8, bỏ qua | [8, 9, 10] | 8 |

Cột các giá trị được **viết đã sắp để dễ hiểu tập ứng viên**, không có nghĩa list nội bộ của heap bắt buộc tăng dần. Trạng thái heap thực tế chỉ cần giữ đúng bất biến cha–con.

### 4.2. Độ phức tạp

Với n entry, k≥1:

- Đọc mỗi entry một lần: **Θ(n)**.
- Min-heap luôn có tối đa **min(k,n)** entry.
- Mỗi push/thay gốc mất **O(log(k+1))** thời gian.
- Tổng thời gian: **O(n log(k+1))**, thường viết O(n log k) khi k≥2.
- Bộ nhớ ứng viên: **O(min(k,n))** ngoài dữ liệu nguồn.
- Nếu muốn kết quả đã sắp giảm dần, cần thêm O(min(k,n) log(min(k,n)+1)) thời gian để sắp nhóm cuối, và bộ nhớ theo cách tạo kết quả.

Khi **k=0**, kết quả rỗng và có thể trả ngay **không cần tiêu thụ stream**. Khi **k>n**, tất cả n phần tử đầu vào đều được giữ; khi k=1, thuật toán chỉ cần duy trì một ứng viên tốt nhất.

## 5. Python cho top-k lớn nhất và nhỏ nhất

### 5.1. Lấy k giá trị lớn nhất

~~~python
import heapq
from collections.abc import Iterable


def top_k_largest(values: Iterable[int], k: int) -> list[int]:
    """Trả tối đa k giá trị lớn nhất, giảm dần."""
    if k < 0:
        raise ValueError("k phải không âm")
    if k == 0:
        return []

    h: list[int] = []

    for x in values:
        if len(h) < k:
            heapq.heappush(h, x)
        elif x > h[0]:
            heapq.heapreplace(h, x)

    # Trả thứ tự giảm dần; bản thân h chưa được sắp toàn cục.
    return sorted(h, reverse=True)


assert top_k_largest([7, 1, 9, 3, 8, 4, 10, 2], 3) == [10, 9, 8]
assert top_k_largest([9, 9, 8, 5], 3) == [9, 9, 8]
assert top_k_largest([], 3) == []
assert top_k_largest([4, 1], 5) == [4, 1]
assert top_k_largest([4, 1], 0) == []
assert top_k_largest([-5, -2, -9, 0], 2) == [0, -2]

try:
    top_k_largest([1, 2], -1)
except ValueError:
    pass
else:
    raise AssertionError("k âm phải gây lỗi")
~~~

Lệnh **heapreplace** chỉ được gọi khi heap đã đủ k và k≥1, vì không được gọi nó trên heap rỗng. Khi x bằng ngưỡng, bỏ qua x vẫn cho đúng top-k **giá trị**; nếu cần xác định entry nào thắng khi bằng điểm, phải định nghĩa khóa phụ.

### 5.2. Lấy k giá trị nhỏ nhất bằng cách đổi dấu

Top-k **nhỏ nhất** muốn biết **giá trị lớn nhất trong những ứng viên đang giữ**, để loại nó khi một số nhỏ hơn xuất hiện. Có thể dùng **max-heap kích thước k**. Với khóa số, Python min-heap có thể mô phỏng max-heap bằng số âm:

~~~python
import heapq


def top_k_smallest_numbers(values, k: int) -> list[int]:
    if k < 0:
        raise ValueError("k phải không âm")
    if k == 0:
        return []

    h = []  # Chứa các số âm.

    for x in values:
        minus_x = -x
        if len(h) < k:
            heapq.heappush(h, minus_x)
        elif minus_x > h[0]:
            heapq.heapreplace(h, minus_x)

    return sorted(-x for x in h)


assert top_k_smallest_numbers([7, 1, 9, 3, 8, 4, 10, 2], 3) == [1, 2, 3]
assert top_k_smallest_numbers([-5, -1, -3], 2) == [-5, -3]
assert top_k_smallest_numbers([], 4) == []
~~~

**Lý giải dấu:** Giá trị âm nhỏ nhất tương ứng số gốc **lớn nhất** trong nhóm giá trị gốc. Một số thật x nhỏ hơn ngưỡng có **-x lớn hơn h[0]**, nên được đưa vào.

Cách đổi dấu chỉ phù hợp với khóa số hỗ trợ phép đổi dấu, không nên áp dụng máy móc cho chuỗi hoặc payload. Với key phức tạp có thể dùng một kiểu wrapper với thứ tự đảo, hoặc API max-heap phù hợp.


## 6. Top-k nâng cao: hòa điểm và giá trị phân biệt

### 6.1. K bản ghi có điểm cao nhất, hòa điểm ưu tiên đến trước

Nếu entry chứa **(score, payload)**, hai payload không có phép so sánh có thể gây lỗi khi score bằng nhau. Nếu yêu cầu giữ người **đến trước khi hòa điểm**, dùng khóa:

~~~text
(score, -arrival_index)
~~~

Trong min-heap top-k lớn nhất, entry có score thấp hơn hoặc có arrival_index lớn hơn khi cùng điểm là ứng viên yếu nhất. Dùng index duy nhất giúp không cần so sánh payload.

~~~python
import heapq


def top_k_records(records, k: int):
    """Score giảm dần, hòa score thì đến trước đứng trước."""
    if k < 0:
        raise ValueError("k phải không âm")
    if k == 0:
        return []

    heap = []
    for index, (score, payload) in enumerate(records):
        item = (score, -index, payload)

        if len(heap) < k:
            heapq.heappush(heap, item)
        elif item[:2] > heap[0][:2]:
            heapq.heapreplace(heap, item)

    ordered = sorted(heap, key=lambda item: item[:2], reverse=True)
    return [(score, payload) for score, _index, payload in ordered]


players = [
    (9, "An"), (7, "Bình"), (9, "Chi"),
    (9, "Dung"), (4, "Em"),
]
assert top_k_records(players, 2) == [(9, "An"), (9, "Chi")]
assert top_k_records(players, 3) == [
    (9, "An"), (9, "Chi"), (9, "Dung")
]
assert top_k_records([], 3) == []
~~~

**Điểm cần hiểu:** Có nhiều entry cùng score vẫn có thể thuộc top-k. Khóa phụ chỉ quyết định entry nào thắng tại ranh giới k, không chuyển bài toán thành top-k **giá trị phân biệt**.

### 6.2. Top-k giá trị phân biệt

Ví dụ:

~~~text
values = [10, 10, 10, 9, 8, 7]
k = 3

Top-3 entry:             [10, 10, 10]
Top-3 giá trị phân biệt: [10, 9, 8]
~~~

Nếu lấy top-k entry rồi mới xóa trùng, có thể chỉ còn một giá trị, **không đáp ứng yêu cầu k giá trị phân biệt**.

Có thể dùng **set** đồng bộ với min-heap giữ k ứng viên:

~~~python
import heapq


def top_k_distinct(values, k: int) -> list[int]:
    if k < 0:
        raise ValueError("k phải không âm")
    if k == 0:
        return []

    h = []
    present = set()

    for x in values:
        if x in present:
            continue

        if len(h) < k:
            heapq.heappush(h, x)
            present.add(x)
        elif x > h[0]:
            removed = heapq.heapreplace(h, x)
            present.remove(removed)
            present.add(x)

    return sorted(h, reverse=True)


assert top_k_distinct([10, 10, 10, 9, 8, 7], 3) == [10, 9, 8]
assert top_k_distinct([5, 5, 5], 4) == [5]
assert top_k_distinct([], 3) == []
~~~

Với khóa có thể hash và so sánh nhất quán, heap và set dùng O(k) bộ nhớ; thao tác set có chi phí O(1) kỳ vọng trong mô hình thông thường. **NaN** trong dữ liệu số thực gây khó khăn vì so sánh không cho thứ tự toàn phần; cần chính sách chuẩn hóa/bỏ qua NaN trước khi dùng.

### 6.3. Top-k từ nhiều phân vùng

Nếu mỗi nguồn giữ đúng top-k theo **cùng thứ tự ưu tiên toàn phần**, top-k toàn cục luôn nằm trong **hợp các top-k cục bộ**. Một entry không thuộc top-k của phân vùng nó đã có ít nhất k entry trong chính phân vùng ấy đứng trước, nên không thể thuộc top-k toàn cục.

Nếu bản ghi hòa score cần xác định chính xác danh tính, các nguồn phải thống nhất **tie-breaker duy nhất**. Chỉ dùng score mà không thống nhất tie-breaker có thể tạo nhiều tập entry cùng điểm đúng về giá trị nhưng khác danh tính.

### 6.4. Chọn top-k theo yêu cầu

| Trường hợp | Cách đáng cân nhắc | Lý do |
| --- | --- | --- |
| n lớn, k nhỏ, dữ liệu là stream | Min-heap kích thước k | O(k) bộ nhớ |
| Cần sắp toàn bộ n entry | Sort | Sắp xếp toàn cục đã được yêu cầu |
| Chỉ xử lý một lần trên mảng đầy đủ | Selection/quickselect hoặc sort | Có thể phù hợp hơn tùy cận kỳ vọng/xấu nhất |
| Liên tục cập nhật ngưỡng top-k | Duy trì heap k entry | Ngưỡng ở gốc |
| Top-k giá trị phân biệt | Heap + set | Cần bỏ trùng đúng lúc |
| Top-k bản ghi ổn định khi hòa | Heap với arrival_index | Tie-breaker rõ ràng |

Nếu xuất top-k **đã sắp** sau mỗi lần cập nhật, còn phải tính chi phí sắp k ứng viên. Không được báo toàn bộ quá trình xuất là O(log k) chỉ vì cập nhật heap mất O(log k).


## 7. Ghép nhiều dãy đã sắp xếp: chỉ cần quan sát đầu mỗi nguồn

Cho k dãy tăng dần, có thể có độ dài khác nhau:

~~~text
A = [1, 4, 9]
B = [2, 2, 8]
C = [0, 6]

Kết quả:
[0, 1, 2, 2, 4, 6, 8, 9]
~~~

Gọi **N** là tổng số phần tử của tất cả dãy, **k** là số dãy nguồn. Ta cần xuất **N** phần tử theo thứ tự không giảm, không bỏ trùng lặp.

**Quan sát quan trọng:** Trong một dãy đã sắp, phần tử nhỏ nhất chưa xuất chính là **phần tử đầu tiên chưa được lấy** của dãy ấy. Không một phần tử đứng sau có thể nhỏ hơn nó.

Vì vậy, min của **toàn bộ phần dữ liệu chưa xuất** chắc chắn nằm trong **k phần tử đầu chưa lấy** — một phần tử từ mỗi dãy còn dữ liệu.

Thay vì đưa cả N phần tử vào heap, chỉ cần duy trì một **frontier** với tối đa **k entry**.

## 8. Bất biến và thuật toán k-way merge

Heap lưu entry:

~~~text
(value, source_id)
~~~

- **value:** phần tử đầu chưa lấy của nguồn.
- **source_id:** chỉ số duy nhất cho nguồn, dùng để lấy đúng phần tử tiếp theo và phân xử value bằng nhau.

**Bất biến vòng lặp:**

> Với mỗi dãy còn phần tử chưa xuất, heap chứa **đúng một entry cho phần tử đầu chưa lấy của dãy ấy**. Với dãy đã hết, heap không chứa entry tương ứng.

### 8.1. Khởi tạo

Lấy phần tử đầu của mỗi dãy **không rỗng**, push entry chứa giá trị và source_id vào min-heap. Dãy rỗng không tạo entry.

### 8.2. Một lượt xử lý

1. Pop **(value, source_id)** nhỏ nhất.
2. Xuất value.
3. Tiến con trỏ/iterator của **chính nguồn source_id**.
4. Nếu nguồn ấy còn phần tử, push entry cho phần tử mới.
5. Nếu nguồn cạn, không push thêm.
6. Lặp cho tới khi heap rỗng.

### 8.3. Vì sao thuật toán đúng?

**Khởi tạo:** Mỗi dãy còn dữ liệu có một đại diện trong heap, nên bất biến đúng.

**Duy trì:** Theo giả định từng dãy đã sắp, phần tử đầu chưa lấy của dãy không lớn hơn các phần tử còn lại của dãy. Vì vậy, gốc min của heap là **phần tử nhỏ nhất toàn cục chưa xuất**. Sau khi xuất nó, push phần tử kế tiếp của **đúng nguồn đã pop** khôi phục bất biến.

**Kết thúc:** Heap rỗng khi tất cả nguồn đều cạn. Mọi phần tử đã được xuất **đúng một lần** và theo thứ tự không giảm.

### 8.4. Pseudocode

~~~text
merge_sorted_sources(sources):
    heap = min-heap rỗng

    cho mỗi nguồn s:
        nếu nguồn s không rỗng:
            push(heap, (phần_tử_đầu(s), s))

    khi heap chưa rỗng:
        value, s = pop_min(heap)
        xuất value

        nếu nguồn s còn phần tử:
            push(heap, (phần_tử_tiếp_theo(s), s))
~~~

**Sai lầm nguy hiểm:** Pop phần tử từ A nhưng lại lấy phần tử mới của B để push. Khi đó có thể có hai entry đại diện cho B, không có entry đại diện cho A, và thuật toán sai dù heap vẫn thỏa cha ≤ con.

## 9. Mô phỏng k-way merge trên ba dãy

~~~text
A = [1, 4, 9]
B = [2, 2, 8]
C = [0, 6]

Khởi tạo heap:
(1, A), (2, B), (0, C)
~~~

| Lượt | Pop từ nguồn | Xuất | Push phần tử tiếp từ cùng nguồn | Dãy kết quả đã xuất |
| ---: | --- | ---: | --- | --- |
| 1 | C | 0 | C: 6 | [0] |
| 2 | A | 1 | A: 4 | [0, 1] |
| 3 | B | 2 | B: 2 | [0, 1, 2] |
| 4 | B | 2 | B: 8 | [0, 1, 2, 2] |
| 5 | A | 4 | A: 9 | [0, 1, 2, 2, 4] |
| 6 | C | 6 | C đã cạn | [0, 1, 2, 2, 4, 6] |
| 7 | B | 8 | B đã cạn | [0, 1, 2, 2, 4, 6, 8] |
| 8 | A | 9 | A đã cạn | [0, 1, 2, 2, 4, 6, 8, 9] |

Khi có hai phần tử 2 liên tiếp từ cùng B, thuật toán vẫn hoạt động: sau lần pop 2 đầu tiên, 2 tiếp theo của B được đưa vào heap. Nếu các nguồn khác cũng có 2, thứ tự giữa các nguồn sẽ phụ thuộc source_id hoặc tie-breaker đã chọn; **giá trị đầu ra vẫn không giảm**.

## 10. Python: hợp nhất nhiều dãy bằng một heap nhỏ

### 10.1. Phiên bản xuất từng phần tử

Dùng iterator để không cần giữ toàn bộ kết quả N phần tử trong bộ nhớ.

~~~python
import heapq
from collections.abc import Iterable, Iterator


def merge_sorted_sources(
    sources: Iterable[Iterable[int]],
) -> Iterator[int]:
    """Sinh lần lượt các giá trị tăng dần từ những nguồn đã sắp."""
    iterators = []
    h = []  # Mỗi entry: (value, source_id).

    for source_id, source in enumerate(sources):
        it = iter(source)
        iterators.append(it)

        try:
            first = next(it)
        except StopIteration:
            continue

        heapq.heappush(h, (first, source_id))

    while h:
        value, source_id = heapq.heappop(h)
        yield value

        # Tiến chính nguồn vừa được lấy.
        it = iterators[source_id]
        try:
            next_value = next(it)
        except StopIteration:
            continue

        heapq.heappush(h, (next_value, source_id))


sources = [
    [1, 4, 9],
    [2, 2, 8],
    [0, 6],
]

assert list(merge_sorted_sources(sources)) == [
    0, 1, 2, 2, 4, 6, 8, 9
]
assert list(merge_sorted_sources([])) == []
assert list(merge_sorted_sources([[], []])) == []
assert list(merge_sorted_sources([[], [1, 1], []])) == [1, 1]
assert list(merge_sorted_sources([[0, 5, 8]])) == [0, 5, 8]
assert list(merge_sorted_sources([[-3, 0], [-5, 2]])) == [
    -5, -3, 0, 2
]
~~~

**Vì sao tuple chỉ chứa (value, source_id)?** Có tối đa một entry đang ở heap cho mỗi nguồn, nên khi hai entry có value bằng nhau, source_id khác nhau. Không cần so sánh iterator hoặc payload.

Nếu muốn ghi nhận nguồn gốc của mỗi kết quả, đổi phần **yield value** thành **yield (value, source_id)** và sửa hợp đồng trả về.

### 10.2. Phiên bản giữ kết quả thành list

~~~python
def merge_to_list(sources) -> list[int]:
    return list(merge_sorted_sources(sources))


assert merge_to_list([[1, 4], [2, 3]]) == [1, 2, 3, 4]
~~~

Hàm iterator chỉ cần bộ nhớ phụ O(k), nhưng **list(...)** tạo thêm vùng nhớ O(N) cho N giá trị đầu ra. Không được nói toàn bộ việc trả một list N phần tử dùng O(k) bộ nhớ.

### 10.3. Chi phí và những giả định

Gọi k là số nguồn và N là tổng số phần tử:

- Khởi tạo **k iterator**: Θ(k) thời gian và O(k) bộ nhớ.
- Heap có tối đa **m ≤ min(k,N)** entry, với m là số nguồn không rỗng.
- Mỗi phần tử được pop đúng một lần; mỗi phần tử sau phần tử đầu một nguồn được push đúng một lần.
- Tổng thời gian: **O(k + N log(k+1))**.
- Bộ nhớ phụ của iterator và heap: **O(k)**, ngoài đầu vào và kết quả mà người gọi lưu.

Trường hợp **k=0** cho đầu ra rỗng; **k=1** chỉ duyệt một nguồn. Nếu **tất cả nguồn rỗng**, vẫn tốn Θ(k) để nhận biết chúng rỗng.

**Tiền điều kiện thiết yếu:** Mỗi nguồn phải được sắp không giảm. Nếu truyền nguồn [5,1], thuật toán không sửa lại nguồn và không bảo đảm kết quả toàn cục tăng dần.

**Dữ liệu đặc biệt:** Số âm, khóa bằng nhau, nguồn rỗng và các nguồn có độ dài khác nhau đều có thể xử lý. Nếu khóa là object, hãy đưa khóa có thể so sánh lên đầu entry, rồi thêm tie-breaker duy nhất để tránh so sánh payload khi hòa.

### 10.4. Không nhầm streaming với dữ liệu thiếu

Nếu một nguồn **chưa cung cấp** phần tử kế tiếp nhưng vẫn có thể chứa giá trị nhỏ hơn những nguồn khác, thuật toán không được giả định nguồn ấy đã cạn. Cần đợi phần tử đầu tiếp theo hoặc dùng **watermark/bảo đảm thứ tự** được xác định rõ cho luồng thời gian thực.

K-way merge kiểu iterator chỉ bảo đảm đúng khi mỗi nguồn cung cấp phần tử **theo thứ tự đã sắp** và trạng thái “hết nguồn” là chính xác.


## 11. So sánh k-way merge với các cách khác

| Cách làm | Ý tưởng | Thời gian | Bộ nhớ phụ nếu xuất dần |
| --- | --- | --- | --- |
| Nối toàn bộ rồi sort | Gom N entry vào mảng và sort | O(N log(N+1)) cộng chi phí gom | O(N) cho mảng gom |
| Quét k đầu dãy | Mỗi lần xem tất cả nguồn để tìm min | O(kN) cận trên | O(k) iterator |
| Dùng min-heap frontier | Pop min, bổ sung từ nguồn vừa pop | **O(k + N log(k+1))** | **O(k)** |

Với k nhỏ, quét thủ công có thể đơn giản và đủ nhanh. Khi có nhiều nguồn, heap giảm chi phí chọn entry tiếp theo từ O(k) xuống O(log k) mỗi lần xuất.

**Ứng dụng:** Hợp nhất log theo timestamp từ nhiều máy, external merge sort trên các run đã sắp, hoặc trộn kết quả từ các dịch vụ đã sắp theo điểm.

**Điều kiện:** Nếu một nguồn chưa trả phần tử kế tiếp mà vẫn có thể chứa khóa nhỏ hơn các nguồn khác, không thể tự tin xuất theo thứ tự toàn cục. Cần đợi nguồn, hoặc dùng watermark và bảo đảm sắp xếp/độ trễ phù hợp.

## 12. Lập lịch tác vụ: chỉ tác vụ đã đến mới được nằm trong ready heap

Lập lịch khác top-k và merge vì có yếu tố **thời gian**. Một tác vụ có ưu tiên cao nhưng **chưa đến** không được tham gia tranh quyền CPU.

Trong bài dùng **một CPU, lập lịch ưu tiên không ngắt** (*non-preemptive priority scheduling*) và mô hình sau:

| Trường | Ý nghĩa |
| --- | --- |
| **arrival** | Thời điểm tác vụ xuất hiện; không âm |
| **priority** | Số quy định mức ưu tiên; **số nhỏ hơn được chọn trước** |
| **duration** | Thời gian cần CPU, là số nguyên dương |
| **ready** | Đã đến, chưa chạy, có thể bắt đầu |
| **running** | Đã được chọn; chạy tới hết duration, không bị ngắt |
| **completed** | Đã thực thi xong |

**Bất biến của bộ lập lịch:**

> Mỗi khi CPU có thể chọn một công việc mới, ready heap chứa **đúng tất cả công việc đã đến, đủ điều kiện chạy và chưa được chọn**. Công việc ưu tiên nhất theo chính sách nằm ở gốc.

### 12.1. Khóa ưu tiên và xử lý hòa khóa

Min-heap dùng khóa:

~~~text
(priority, arrival, input_index)
~~~

Trong đó:

1. Priority **nhỏ hơn** thắng.
2. Nếu cùng priority, arrival **sớm hơn** thắng.
3. Nếu cả priority và arrival bằng nhau, input_index **nhỏ hơn** thắng.

Điều này cho thứ tự ổn định theo thời điểm đến với các task hòa mức ưu tiên. Heap lưu input_index thay vì so sánh trực tiếp các object Task, để tránh lỗi khi hai task có cùng priority.

### 12.2. Phân biệt tác vụ tương lai và tác vụ ready

Có hai vùng dữ liệu:

- **pending:** Danh sách tác vụ chưa được đưa vào heap, được sắp theo arrival.
- **ready:** Heap các tác vụ đã đến nhưng chưa bắt đầu chạy, sắp theo priority.

**Không được đẩy toàn bộ pending vào ready từ đầu.** Một tác vụ đến lúc t=100 với priority=0 không được chạy ở t=0 chỉ vì nó ưu tiên hơn những tác vụ đã có mặt.

### 12.3. Một vòng lặp lập lịch

Giả sử CPU đang rảnh ở t:

1. Push vào ready **tất cả** các task có arrival ≤ t mà chưa push.
2. Nếu ready không rỗng, pop tác vụ có khóa nhỏ nhất; đặt **start=t**, **finish=t+duration**.
3. Chạy không ngắt từ start tới finish. Công việc đến giữa khoảng ấy phải đợi.
4. Cập nhật **t=finish**, rồi lại bổ sung những công việc đã đến trước khi chọn tiếp.
5. Nếu ready rỗng nhưng còn pending, ghi khoảng CPU rảnh và **nhảy đồng hồ** tới arrival tiếp theo.

**Mẹo quan trọng:** Không cần lặp từng đơn vị thời gian. Dù khoảng rảnh là 1 hay 1_000_000 đơn vị, mô phỏng chỉ cần đổi t một lần.

### 12.4. Pseudocode

~~~text
nonpreemptive_schedule(tasks):
    pending = tasks được sắp theo arrival
    ready = min-heap rỗng
    i = 0
    t = 0

    trong khi còn pending hoặc ready không rỗng:
        trong khi i < n và pending[i].arrival <= t:
            push ready với khóa
                (priority, arrival, input_index)
            i += 1

        nếu ready rỗng:
            ghi đoạn rảnh [t, pending[i].arrival)
            t = pending[i].arrival
            tiếp tục

        task = pop_min(ready)
        start = t
        finish = t + task.duration
        ghi lịch chạy (task, start, finish)
        t = finish
~~~

Mỗi tác vụ được **push một lần** khi xuất hiện, **pop một lần** khi CPU nhận nó; một tác vụ đã chạy không quay lại heap trong mô hình không ngắt này.

## 13. Truy vết lập lịch với tác vụ đến trong khi CPU đang bận

Cho các tác vụ:

| ID | Arrival | Priority | Duration |
| --- | ---: | ---: | ---: |
| A | 0 | 2 | 4 |
| B | 1 | 0 | 2 |
| C | 1 | 1 | 3 |
| D | 7 | 0 | 1 |
| E | 9 | 2 | 1 |
| F | 9 | 2 | 2 |
| G | 14 | 0 | 1 |

**Quy ước:** Priority 0 cao hơn 1, cao hơn 2.

- **t=0:** Chỉ A đã đến, nên **A chạy [0,4)**. B và C đến ở t=1 nhưng không được ngắt A.
- **t=4:** B, C sẵn sàng; chọn **B [4,6)** vì priority 0 tốt hơn 1.
- **t=6:** Chọn **C [6,9)**; D đến ở t=7 nhưng C vẫn chạy hết.
- **t=9:** D, E, F đã đến. Chọn **D [9,10)**, ưu tiên 0.
- **t=10:** E và F cùng arrival=9, priority=2; E có input_index nhỏ hơn, nên **E [10,11)**.
- **t=11:** Chạy **F [11,13)**.
- **t=13:** Ready rỗng, G đến lúc 14; CPU **rảnh [13,14)**.
- **t=14:** Chạy **G [14,15)**.

~~~text
Các khoảng chạy theo thứ tự:
A[0,4)  B[4,6)  C[6,9)  D[9,10)
E[10,11) F[11,13)  idle[13,14)  G[14,15)
~~~

### 13.1. Kết quả và thời gian chờ

| Task | Start | Finish | Waiting = Start − Arrival |
| --- | ---: | ---: | ---: |
| A | 0 | 4 | 0 |
| B | 4 | 6 | 3 |
| C | 6 | 9 | 5 |
| D | 9 | 10 | 2 |
| E | 10 | 11 | 1 |
| F | 11 | 13 | 2 |
| G | 14 | 15 | 0 |

Tổng thời lượng thực thi là **14 đơn vị**, khoảng rảnh là **1 đơn vị** trong cửa sổ [0,15). **Waiting time** của mỗi task là **start − arrival**; **turnaround time** là **finish − arrival**, không được nhầm hai đại lượng.

### 13.2. Vì sao không được chọn G ở thời điểm t=0?

G có priority=0 nhưng arrival=14. Nếu đưa G vào ready trước t=14, heap có thể chọn G khi nó chưa đến. Đó là lỗi về **tập ứng viên** chứ không phải lỗi sift-up/sift-down.

**Sự thật quan trọng:** Một bộ lập lịch đúng phải duy trì **pending theo arrival** và **ready theo priority**, không thể thay thế bằng một heap đơn lẻ chứa mọi công việc tương lai chỉ sắp theo priority.


## 14. Python: lập lịch ưu tiên không ngắt

Mã dưới đây mô phỏng **một CPU** với arrival không âm, duration dương, và **priority nhỏ hơn được chọn trước**. Nó không cài đặt preemption hay phụ thuộc công việc.

~~~python
from dataclasses import dataclass
import heapq


@dataclass(frozen=True)
class Task:
    name: str
    arrival: int
    priority: int
    duration: int


def schedule_nonpreemptive(tasks: list[Task]):
    """Trả (timeline, idle_intervals).

    timeline: (name, start, finish).
    Tie-break: priority, arrival, input_index.
    """
    for task in tasks:
        if task.arrival < 0:
            raise ValueError("arrival phải không âm")
        if task.duration <= 0:
            raise ValueError("duration phải dương")

    # Tác vụ chưa đến được sắp theo thời điểm arrival.
    pending = sorted(
        enumerate(tasks),
        key=lambda pair: (pair[1].arrival, pair[0]),
    )

    ready = []  # (priority, arrival, original_index).
    next_index = 0
    current_time = 0
    timeline = []
    idle_intervals = []

    while next_index < len(pending) or ready:
        # Đưa đủ TẤT CẢ task đã đến vào ready.
        while (
            next_index < len(pending)
            and pending[next_index][1].arrival <= current_time
        ):
            original_index, task = pending[next_index]
            heapq.heappush(
                ready,
                (task.priority, task.arrival, original_index),
            )
            next_index += 1

        if not ready:
            # Không duyệt từng tick khi CPU rảnh.
            next_arrival = pending[next_index][1].arrival
            if next_arrival > current_time:
                idle_intervals.append((current_time, next_arrival))
            current_time = next_arrival
            continue

        _priority, _arrival, original_index = heapq.heappop(ready)
        task = tasks[original_index]

        start = current_time
        finish = start + task.duration
        timeline.append((task.name, start, finish))

        # Không ngắt: các arrival mới được nhận sau khi chạy xong.
        current_time = finish

    return timeline, idle_intervals


tasks = [
    Task("A", 0, 2, 4),
    Task("B", 1, 0, 2),
    Task("C", 1, 1, 3),
    Task("D", 7, 0, 1),
    Task("E", 9, 2, 1),
    Task("F", 9, 2, 2),
    Task("G", 14, 0, 1),
]

timeline, idle = schedule_nonpreemptive(tasks)

assert timeline == [
    ("A", 0, 4),
    ("B", 4, 6),
    ("C", 6, 9),
    ("D", 9, 10),
    ("E", 10, 11),
    ("F", 11, 13),
    ("G", 14, 15),
]
assert idle == [(13, 14)]

assert schedule_nonpreemptive([]) == ([], [])
assert schedule_nonpreemptive([
    Task("Z", 5, 0, 2),
]) == ([("Z", 5, 7)], [(0, 5)])

# Nếu arrival và priority bằng nhau, thứ tự đầu vào thắng.
assert schedule_nonpreemptive([
    Task("X", 0, 1, 2),
    Task("Y", 0, 1, 1),
])[0] == [("X", 0, 2), ("Y", 2, 3)]

try:
    schedule_nonpreemptive([Task("bad", 0, 1, 0)])
except ValueError:
    pass
else:
    raise AssertionError("duration 0 phải bị từ chối")
~~~

### 14.1. Vì sao cần hai vùng dữ liệu?

**Pending** là danh sách tác vụ sắp theo arrival, chưa nhất thiết có thể chạy. **Ready** là min-heap của tất cả tác vụ đã đến nhưng chưa được chọn. Khi CPU chạy xong một task, vòng while bên trong tiếp tục nhận đủ những arrival xảy ra trong thời gian chạy **trước khi chọn lần tiếp**.

Với ví dụ, ở t=9 cần đưa đủ D, E, F vào heap trước khi pop. Chỉ đưa một trong ba có thể dẫn đến lựa chọn sai.

### 14.2. Vì sao không lặp từng đơn vị thời gian?

Nếu ready rỗng mà vẫn còn pending, mã nhảy current_time tới arrival tiếp theo. Dù thời gian rảnh dài một triệu đơn vị, chỉ cần một bước thay đổi biến, không chạy một triệu vòng.

Duration là **thời gian mô phỏng nghiệp vụ**, không phải số lần lặp tương ứng trong chương trình.

### 14.3. Phân tích chi phí

Với n tác vụ:

- Sắp theo arrival: **O(n log(n+1))**.
- Mỗi tác vụ được push một lần, pop một lần: tổng **O(n log(n+1))**.
- Không xử lý từng tick, chỉ các sự kiện arrival, finish và idle.
- Pending, ready, timeline và idle_intervals: **O(n)** bộ nhớ.

Tổng: **O(n log(n+1)) thời gian và O(n) bộ nhớ**. Các khoảng chạy là **nửa mở [start,finish)**, nên một tác vụ có thể bắt đầu chính thời điểm tác vụ trước kết thúc.


## 15. Chính sách lập lịch, ưu tiên động và những giới hạn

**Heap chỉ triển khai quy tắc chọn phần tử.** Quy tắc ấy phải được định nghĩa bởi chính sách lập lịch. Thay trường khóa có thể tạo một chính sách khác nhưng cũng có thể làm thay đổi ý nghĩa của thuật toán.

### 15.1. Shortest Job First (SJF)

Nếu muốn ưu tiên task có **thời lượng dự kiến ngắn nhất**, đặt khóa:

~~~text
(duration, arrival, input_index)
~~~

thay cho khóa ưu tiên tĩnh. Khi một task chưa đến, nó vẫn **không được** đưa vào ready heap.

Kết quả tối ưu hóa thời gian chờ của SJF phụ thuộc các giả định về thời điểm đến và thông tin duration; nếu duration chỉ là ước lượng hoặc có preemption, phải phân tích chính sách cụ thể.

### 15.2. Earliest Deadline First (EDF)

Nếu mỗi task có **deadline tuyệt đối**, có thể chọn task ready theo:

~~~text
(deadline, arrival, input_index)
~~~

Tuy nhiên, dùng heap theo deadline **không có nghĩa mọi task chắc chắn hoàn thành đúng deadline**. Điều đó còn phụ thuộc lượng công việc, duration, khả năng ngắt và tài nguyên.

### 15.3. Ưu tiên có ngắt (preemptive scheduling)

Trong chính sách **có ngắt**, một task ưu tiên cao đến khi CPU đang chạy task ưu tiên thấp có thể khiến task đang chạy tạm dừng.

Vì vậy, mã ở mục 14 không áp dụng nguyên trạng. Bộ lập lịch cần:

1. Biết **arrival kế tiếp** khi một task đang chạy.
2. Chạy tới **sự kiện arrival hoặc finish sớm hơn**.
3. Cập nhật **remaining_time** nếu task chưa hoàn thành.
4. Quyết định ngắt hay tiếp tục theo chính sách.
5. Nếu ngắt, đưa phần công việc chưa chạy trở lại ready heap.

Chỉ thay phép so sánh của heap mà không mô hình hóa arrival trong khi chạy là **không đủ**.

### 15.4. Starvation và aging

Nếu task priority thấp liên tục bị các task priority cao mới đến vượt qua, nó có thể chờ rất lâu, thậm chí **không bao giờ chạy** nếu luồng task ưu tiên cao không ngừng.

**Aging** là cơ chế điều chỉnh ưu tiên theo thời gian chờ để giảm nguy cơ bỏ đói. Nhưng nếu một priority đang nằm trong heap thay đổi, thứ tự heap **không tự cập nhật**. Cần thao tác cập nhật khóa có khôi phục bất biến, hoặc tạo entry mới và vô hiệu hóa entry cũ đúng cách.

### 15.5. Hủy tác vụ và cập nhật theo ID

Min-heap bình thường không tìm entry theo **ID tùy ý** trong O(log n). Có thể dùng:

- **Indexed heap:** Bảng băm ID → chỉ số heap, cập nhật vị trí sau mọi swap.
- **Lazy invalidation:** Bảng trạng thái hoặc version cho biết entry trong heap đã lỗi thời. Khi nó lên gốc thì pop/bỏ qua, tiếp tục tìm entry hợp lệ.
- **Heapify lại:** Có thể hợp lý khi có nhiều thay đổi theo lô, nhưng phải tính chi phí tạo lại.

Entry bị hủy theo phương án lazy invalidation có thể vẫn nằm trong heap một thời gian, làm tăng bộ nhớ và số pop dọn rác. Phải tính chi phí này trong hệ thống thực tế.

### 15.6. Mô hình một CPU còn bỏ qua điều gì?

Ví dụ không tính **nhiều CPU, phụ thuộc DAG, khóa tài nguyên, thời gian chuyển ngữ cảnh, ngắt giữa chừng, deadline cứng, ưu tiên kế thừa và priority inversion**.

Priority inversion xuất hiện khi task ưu tiên cao phải chờ tài nguyên mà task ưu tiên thấp đang giữ; chỉ sắp ready heap theo priority không tự giải quyết được vấn đề này.

## 16. Bảng tổng hợp ba bài toán ứng dụng

| Thuộc tính | Top-k lớn nhất | K-way merge | Lập lịch tác vụ |
| --- | --- | --- | --- |
| Đầu vào | Luồng khóa bất kỳ | k nguồn **đã sắp** | Tasks có arrival/priority/duration |
| Heap chứa | Tối đa k ứng viên tốt nhất | Tối đa một phần tử đầu chưa lấy/nguồn | Tác vụ đã đến, đang ready |
| Gốc đại diện | **Yếu nhất** trong top-k tạm | **Giá trị xuất tiếp theo** | **Task được chạy tiếp theo** |
| Push khi nào? | Heap chưa đủ hoặc gặp ứng viên tốt hơn | Khởi tạo và sau pop của nguồn ấy | Khi một task đến |
| Pop khi nào? | Khi thay ứng viên yếu nhất | Mỗi lần xuất một giá trị | Khi CPU rảnh và ready có task |
| Cận thời gian | O(n log(k+1)) | O(k + N log(k+1)) | O(n log(n+1)) |
| Bộ nhớ phụ | O(k) | O(k) khi yield | O(n) gồm pending/ready/timeline |
| Bất biến quan trọng | Đúng k ứng viên tốt nhất đã đọc | Một phần tử đầu chưa lấy của mỗi nguồn | Chỉ tác vụ đã đến, chưa chạy trong ready |
| Lỗi điển hình | Sai min/max, xử lý trùng sai | Quên push tiếp đúng nguồn | Cho tác vụ tương lai tranh CPU |

### 16.1. Ba chữ k, n, N không được đánh tráo

Trong **top-k**, n là số entry đầu vào còn k là số ứng viên cần giữ.

Trong **k-way merge**, k là **số dãy nguồn**, N là **tổng số entry** của mọi dãy. Một nguồn có thể chứa rất nhiều entry nhưng heap vẫn chỉ giữ một đại diện của nó.

Trong **lập lịch**, n là tổng số task; kích thước ready heap biến đổi theo thời gian và không lớn hơn n.

Các công thức O(n log k), O(N log k) và O(n log n) vì vậy có **biến đầu vào khác nhau**, dù các thuật toán đều dùng heap.

### 16.2. Có thể kết hợp các ứng dụng như thế nào?

Một hệ thống phân tích log có thể:

1. **Merge** các luồng log đã sắp theo thời điểm thành một luồng tăng dần.
2. Trên luồng đó, dùng **top-k** để giữ các sự kiện có điểm bất thường cao nhất.
3. Tạo các **task phản hồi** cho sự kiện quan trọng và đưa vào hàng đợi ưu tiên của bộ lập lịch.

Từng giai đoạn có **bất biến heap riêng**. Không thể sử dụng một min-heap không phân biệt chức năng rồi kỳ vọng nó vừa sắp timestamp, vừa giữ điểm cao, vừa lập lịch task theo arrival đúng.

## 17. Những lỗi thường gặp

| Sai sót | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Dùng max-heap để giữ top-k lớn nhất rồi loại gốc | Loại ứng viên tốt nhất | Giữ **min-heap k ứng viên lớn nhất** |
| Dùng min-heap để giữ top-k nhỏ nhất rồi loại gốc | Loại ứng viên nhỏ nhất | Dùng max-heap/khóa đảo |
| k = 0 vẫn xem heap[0] | Lỗi truy cập mảng rỗng | Trả [] trước vòng lặp |
| Giữ top-k rồi coi list heap đã được sắp | Kết quả xuất sai thứ tự | Sắp riêng nếu API yêu cầu |
| Xóa trùng sau khi chọn top-k entry | Có thể còn ít hơn k giá trị phân biệt | Duy trì distinct ngay trong quá trình chọn |
| Chỉ dùng score để xếp hạng bản ghi hòa | Thứ tự không quyết định | Thêm sequence/tie-breaker |
| Đảo dấu cho một object không hỗ trợ số âm | TypeError hoặc sai thứ tự | Dùng comparator/wrapper phù hợp |
| Cho rằng O(k) bộ nhớ dù sorted toàn bộ n entry | Bỏ qua bản sao O(n) | Phân biệt stream và sorted đầu vào |
| Đưa tất cả N phần tử của k dãy vào heap | Dùng O(N) bộ nhớ không cần thiết | Mỗi nguồn chỉ một phần tử đầu |
| Pop merge nhưng không push phần tử tiếp theo | Bỏ sót phần tử còn lại của nguồn | Push từ đúng source vừa pop |
| Pop nguồn A nhưng push nguồn B | Phá bất biến frontier | Mang source_id trong entry |
| Chấp nhận dãy nguồn chưa sắp mà không kiểm tra | Kết quả merge có thể sai | Xác định tiền điều kiện/kiểm tra |
| So sánh iterator hoặc payload khi value bằng nhau | Có thể TypeError | Dùng source_id duy nhất |
| Đếm O(k) bộ nhớ cho list kết quả N entry | Bỏ qua bộ nhớ đầu ra | Phân biệt yield với list kết quả |
| Xem nguồn chưa phản hồi như đã cạn | Xuất vượt một phần tử nhỏ hơn chưa biết | Chờ nguồn/watermark có bảo đảm |
| Cho tất cả task tương lai vào ready heap | Có thể chạy trước arrival | Pending theo arrival, ready theo priority |
| Quên đưa đủ các task đến trong lúc CPU bận | Chọn sai task tiếp theo | Vòng while nhận tất cả arrival ≤ t |
| Dùng priority lớn hơn là tốt hơn nhưng vẫn min-heap | Đảo ý nghĩa ưu tiên | Định nghĩa rõ chiều của key |
| Không có tie-breaker khi nhiều task cùng priority | Kết quả không quyết định hoặc lỗi so sánh | Dùng arrival, input_index |
| CPU rảnh nhưng không nhảy tới arrival tiếp | Lặp vô hạn/chạy từng tick lãng phí | Nhảy đồng hồ theo sự kiện |
| Giả định job đến là được ngắt task đang chạy | Trái chính sách không ngắt | Để job chờ tới lần chọn tiếp |
| Dùng deadline như priority mà cho là luôn đúng hạn | Không xét tải/duration | Tách chính sách EDF khỏi kiểm chứng khả thi |
| Đổi priority của entry trong heap nhưng không sửa cấu trúc | Bất biến heap không còn đúng | Update/requeue/lazy invalidation |
| Chỉ tính chi phí push/pop mà bỏ qua sort pending | Thiếu thời gian khởi tạo | Tính O(n log n) cả bước sort |
| Nhầm waiting với turnaround | Báo chỉ số sai | Waiting = start-arrival; turnaround = finish-arrival |

**Checklist chung:** Ở mỗi bước hãy hỏi (1) entry nào đang ở heap, (2) khóa so sánh là gì, (3) gốc có ý nghĩa gì, (4) khi pop có cần bổ sung entry mới không, (5) dữ liệu đầu ra có bắt buộc được sắp không, và (6) chi phí bộ nhớ có tính cả kết quả hay chưa.


## 18. Bài tập tự luyện có đáp án

### Nhóm A — Top-k

**Bài 1 — Chọn heap.** Cần giữ **k điểm lớn nhất** của một luồng. Nên dùng min-heap hay max-heap kích thước k?

*Đáp án:* **Min-heap** kích thước k, vì gốc là điểm **nhỏ nhất trong top-k đang giữ**, tức điểm cần thay khi có ứng viên tốt hơn.

**Bài 2 — Truy vết top-3.** Với dãy [7,1,9,3,8,4,10,2], ba điểm lớn nhất là gì?

*Đáp án:* **[10,9,8]**. Khi heap đủ ba entry, lần lượt thay các ngưỡng 1→3→7→8 bằng những điểm tốt hơn.

**Bài 3 — Trường hợp k=0.** Top-k trả kết quả gì nếu k=0 và tại sao không nên truy cập heap[0]?

*Đáp án:* **[]**. Heap rỗng, không có gốc để đọc; thuật toán có thể trả ngay mà không đọc stream.

**Bài 4 — Trường hợp k>n.** Với dữ liệu [4,1], k=5, top-k lớn nhất trả gì?

*Đáp án:* **[4,1]** khi yêu cầu thứ tự giảm dần; chỉ có hai entry.

**Bài 5 — Trùng điểm.** Với dữ liệu [9,9,8,5], top-3 entry là gì?

*Đáp án:* **[9,9,8]**. Hai entry bằng 9 đều phải được tính.

**Bài 6 — Phân biệt.** Với [10,10,10,9,8,7], top-3 giá trị phân biệt là gì?

*Đáp án:* **[10,9,8]**. Không thể chỉ lấy top-3 entry rồi xóa trùng ở cuối.

**Bài 7 — Tie-breaking.** Hai người An và Chi cùng score=9, An đến trước. Nếu chỉ còn một vị trí ở ranh giới k, dùng khóa phụ nào để ưu tiên An?

*Đáp án:* Với min-heap giữ top-k lớn nhất, dùng **(score, -arrival_index)**, để entry đến muộn bị coi là yếu hơn khi hòa điểm.

**Bài 8 — Điều kiện thay gốc.** Khi heap top-k đủ k phần tử, vì sao có thể bỏ qua x nếu x ≤ h[0]?

*Đáp án:* Đã có k entry trong heap có khóa **≥ x**; x không cải thiện đa tập k giá trị lớn nhất.

**Bài 9 — Chi phí.** Duy trì top-k trên n entry với k≥2 tốn bao nhiêu thời gian và bộ nhớ?

*Đáp án:* **O(n log k)** thời gian và **O(k)** bộ nhớ ứng viên; nếu xuất đã sắp còn cần sắp k entry cuối.

**Bài 10 — Xuất kết quả.** Heap chứa đúng k ứng viên có đồng nghĩa list nội bộ đã được sắp giảm dần không?

*Đáp án:* **Không**. Min-heap chỉ có gốc nhỏ nhất trong tập; nếu API yêu cầu giảm dần phải sort hoặc lấy ra theo thuật toán phù hợp.

**Bài 11 — Top-k nhỏ nhất.** Với [7,1,9,3,8,4,10,2], k=3, kết quả ba số nhỏ nhất là gì?

*Đáp án:* **[1,2,3]**. Có thể dùng max-heap kích thước k hoặc đổi dấu số để sử dụng min-heap Python.

**Bài 12 — Khi nào nên sort?** Nếu hệ thống cần **toàn bộ n bản ghi đã sắp**, còn cần tối ưu bằng heap kích thước k nhỏ không?

*Đáp án:* Không phải mục tiêu phù hợp; **sort toàn bộ** là lựa chọn tự nhiên khi kết quả cần mọi phần tử theo thứ tự.

### Nhóm B — K-way merge

**Bài 13 — Bất biến frontier.** Tại sao trong k-way merge mỗi nguồn chỉ cần có một entry ở heap?

*Đáp án:* Vì nguồn đã sắp, phần tử đầu chưa lấy luôn là **min của những phần tử còn lại trong nguồn**, nên các phần tử sau không thể thắng nó.

**Bài 14 — Kết quả merge.** Hợp nhất [1,4,9], [2,2,8] và [0,6] cho kết quả nào?

*Đáp án:* **[0,1,2,2,4,6,8,9]**.

**Bài 15 — Bổ sung từ nguồn nào?** Sau khi pop (0,C), cần push entry từ A, B hay C?

*Đáp án:* **Từ C**, tức phần tử 6 tiếp theo của C, nếu C còn dữ liệu.

**Bài 16 — Nguồn rỗng.** Hợp nhất [[], [1,1], []] cho kết quả gì và heap có bao nhiêu entry sau khởi tạo?

*Đáp án:* **[1,1]**; heap ban đầu có **một entry** đại diện cho nguồn duy nhất không rỗng.

**Bài 17 — Không có nguồn.** Với k=0, merge trả gì?

*Đáp án:* **Luồng rỗng**; không có phần tử để xuất.

**Bài 18 — Khóa trùng giữa các nguồn.** Nếu A và B cùng bắt đầu bằng 5, có được bỏ một trong hai số 5 không?

*Đáp án:* **Không**, vì merge giữ nguyên **mọi entry**, không phải lấy distinct. Có thể dùng source_id để quyết định thứ tự hòa.

**Bài 19 — Nguồn chưa sắp.** Nếu một nguồn là [5,1], thuật toán frontier còn bảo đảm đúng không?

*Đáp án:* **Không**. 5 đứng trước 1 nhưng 1 mới là min nguồn; tiền điều kiện nguồn được sắp đã bị vi phạm.

**Bài 20 — Chi phí.** Với k nguồn và N phần tử tổng cộng, k-way merge bằng heap tốn bao nhiêu?

*Đáp án:* **O(k + N log(k+1))** thời gian, **O(k)** bộ nhớ phụ khi xuất từng phần tử, ngoài bộ nhớ nguồn.

**Bài 21 — List kết quả.** Nếu sau merge ta gọi list(...) để giữ toàn bộ N phần tử, bộ nhớ phụ còn chỉ O(k) không?

*Đáp án:* **Không** nếu tính cả đầu ra; list chứa N phần tử dùng **O(N)** bộ nhớ bổ sung.

**Bài 22 — Tệp log.** Ba máy tạo log đã sắp theo timestamp. Khi xuất bản ghi từ máy B, phải lấy bản ghi kế từ đâu?

*Đáp án:* **Từ máy B**, để luôn giữ đúng một phần tử đầu chưa đọc của từng máy còn dữ liệu.

### Nhóm C — Lập lịch tác vụ

**Bài 23 — Ready heap.** Một task arrival=14, priority=0 có được nằm trong ready heap tại t=5 không?

*Đáp án:* **Không**, vì task chưa đến. Ready heap chỉ chứa tác vụ đã đến, chưa chạy và đủ điều kiện chạy.

**Bài 24 — Không ngắt.** A chạy [0,4), B đến ở t=1 với priority tốt hơn A. Trong chính sách không ngắt, B bắt đầu lúc nào sớm nhất?

*Đáp án:* **t=4**, sau khi A chạy xong.

**Bài 25 — Hòa mức ưu tiên.** Hai task đều priority=2, arrival=9, E đứng trước F trong đầu vào. Task nào được chạy trước nếu cả hai cùng ready?

*Đáp án:* **E**, nhờ khóa phụ input_index nhỏ hơn.

**Bài 26 — Thời gian chờ.** Với task B của ví dụ (arrival=1, start=4, finish=6), waiting và turnaround là bao nhiêu?

*Đáp án:* **Waiting=4−1=3**, **turnaround=6−1=5**.

**Bài 27 — Khoảng rảnh.** Sau khi F kết thúc t=13, task tiếp theo G đến t=14. Bộ lập lịch phải làm gì?

*Đáp án:* Ghi **idle [13,14)**, nhảy current_time tới 14 rồi chạy G; không được chạy G sớm hoặc quét từng tick.

**Bài 28 — Chi phí.** Với n task bất kỳ, giải pháp sort theo arrival rồi dùng ready heap có thời gian và bộ nhớ bậc nào?

*Đáp án:* **O(n log(n+1)) thời gian**, **O(n) bộ nhớ** cho pending, heap và kết quả.

**Bài 29 — Aging.** Vì sao không được sửa trực tiếp priority của một entry đang nằm trong heap mà không làm gì thêm?

*Đáp án:* Có thể phá bất biến thứ tự cha–con. Cần **cập nhật khóa/reheapify hoặc tạo entry mới và vô hiệu hóa entry cũ**.

**Bài 30 — Chọn mô hình.** Một task mới đến phải được phép ngắt task đang chạy. Có dùng nguyên bộ lập lịch không ngắt ở mục 14 được không?

*Đáp án:* **Không**. Cần theo dõi **arrival trong khi chạy**, **remaining_time** và thao tác preemption; đây là chính sách khác.

## 19. Tổng kết

Heap giúp giữ một tập ứng viên đủ nhỏ để trả lời nhanh **“Phần tử nào cần xử lý tiếp theo?”**, nhưng ý nghĩa tập ứng viên khác nhau:

- **Top-k lớn nhất:** Giữ **k entry tốt nhất đã thấy** trong một **min-heap**. Gốc là ứng viên yếu nhất, dùng làm ngưỡng lọc. Chi phí O(n log(k+1)), bộ nhớ O(k).
- **K-way merge:** Giữ **tối đa một đầu chưa dùng** của mỗi trong k nguồn đã sắp. Mỗi lần pop min phải **đẩy phần tử tiếp theo từ đúng nguồn vừa pop**. Chi phí O(k + N log(k+1)), bộ nhớ O(k) khi xuất dần.
- **Lập lịch tác vụ:** Giữ **những task đã đến và đang ready** trong min-heap theo khóa **(priority, arrival, input_index)**. Tác vụ tương lai nằm ở pending, không được tranh CPU trước arrival. Mô phỏng không ngắt theo sự kiện dùng O(n log(n+1)) thời gian và O(n) bộ nhớ.

**Ghi nhớ:** **Cùng một heap, ba bất biến về tập entry khác nhau.** Chọn đúng chiều ưu tiên, đúng khóa so sánh, đúng thời điểm push/pop và tính đủ chi phí lưu **đầu ra, metadata và các trường hợp biên**. Heap không sắp toàn bộ dữ liệu, không tự biết tác vụ đã đến, cũng không tự tạo ra phần tử tiếp theo của một nguồn đã sắp.
