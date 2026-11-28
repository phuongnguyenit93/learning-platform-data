# Tập hợp như kiểu dữ liệu trừu tượng không chứa phần tử trùng

Khi xây dựng một ứng dụng, ta thường cần quản lý **những giá trị nào đang có mặt** thay vì quản lý vị trí của từng giá trị: danh sách mã sinh viên đã đăng ký môn học, các trang đã duyệt trong thuật toán đồ thị, hoặc các thẻ (tag) được gắn cho bài viết. **Tập hợp (set)** là kiểu dữ liệu trừu tượng phù hợp với nhu cầu đó: mỗi phần tử chỉ xuất hiện **một lần theo quy tắc so sánh bằng nhau**.

Bài học thuộc chương **Tập hợp và ánh xạ** của module cấu trúc dữ liệu. Ta sẽ làm rõ bất biến không trùng lặp, các phép toán nền tảng, cách cài đặt phổ biến và chi phí thời gian, bộ nhớ; từ đó chọn cấu trúc phù hợp cho từng bài toán.

## 1. Tập hợp là gì?

Trong toán học, tập hợp là một tập các phần tử phân biệt. Ví dụ:

- `S = {2, 4, 6}` chứa ba phần tử, nên `|S| = 3`.
- `{2, 4, 4, 6}` vẫn là cùng tập hợp `{2, 4, 6}`: viết lại số `4` không tạo phần tử mới.
- Thứ tự liệt kê không làm đổi tập hợp: `{2, 4, 6} = {6, 2, 4}`.
- `4 ∈ S` nghĩa là `4` thuộc `S`; `5 ∉ S` nghĩa là `5` không thuộc `S`.
- Tập rỗng `∅` không có phần tử, nên `|∅| = 0`.

Trong khoa học máy tính, **set là kiểu dữ liệu trừu tượng (Abstract Data Type – ADT)**: nó quy định các giá trị hợp lệ, hành vi của thao tác và các bất biến phải duy trì, **không quy định bắt buộc phải dùng cấu trúc lưu trữ nào**. Một set có thể được cài bằng bảng băm, cây tìm kiếm cân bằng, mảng bit hoặc cấu trúc khác.

Ví dụ hệ thống đăng ký khóa học nhận các mã học viên `["HV01", "HV02", "HV01", "HV03"]`. Nếu câu hỏi là “có bao nhiêu học viên khác nhau đã đăng ký?”, tập hợp kết quả là `{"HV01", "HV02", "HV03"}`, với kích thước `3`.

### Bất biến cốt lõi: không có hai phần tử bằng nhau

Với mọi hai phần tử `x` và `y` trong set, nếu `x` và `y` được xem là bằng nhau thì chúng đại diện cho **cùng một phần tử**. Vì vậy:

1. Chèn `x` khi `x` chưa tồn tại sẽ làm kích thước tăng một.
2. Chèn lại `x` khi `x` đã tồn tại sẽ không làm thay đổi tập hợp.
3. Xóa `x` khi `x` có mặt sẽ làm kích thước giảm một; xóa giá trị không tồn tại không thể tạo ra phần tử mới.

Quy tắc **“bằng nhau”** có thể thay đổi theo ngôn ngữ và cách cài đặt. Với set dựa trên hàm băm, hai khóa được coi là bằng nhau phải có giá trị băm tương thích: nếu `x == y` thì `hash(x) == hash(y)`. Điều ngược lại không nhất thiết đúng, vì hai giá trị khác nhau vẫn có thể va chạm băm.

## 2. Set khác danh sách, đa tập hợp và ánh xạ thế nào?

| Cấu trúc | Phần tử trùng | Thứ tự/vị trí | Đặc trưng chính |
| --- | --- | --- | --- |
| Danh sách (list) | Được phép | Có thứ tự, truy cập theo chỉ số | Lưu chuỗi phần tử, có thể lặp lại |
| Tập hợp (set) | Không | Không có vị trí chỉ số như list | Quan tâm phần tử có thuộc tập hay không |
| Đa tập hợp (multiset/bag) | Được phép và lưu số lần xuất hiện | Tùy cách cài đặt | Phân biệt “xuất hiện 1 lần” với “3 lần” |
| Ánh xạ (map/dictionary) | Khóa không trùng | Tùy cách cài đặt | Ánh xạ mỗi khóa duy nhất tới một giá trị |

Set chỉ trả lời câu hỏi **“mã HV01 có hiện diện không?”**. Nếu cần biết **“mã HV01 xuất hiện bao nhiêu lần?”**, dùng bộ đếm hoặc map từ mã tới số lần. Nếu cần biết **“học viên HV01 có điểm số bao nhiêu?”**, dùng map từ mã học viên tới điểm số. Nếu cần giữ nguyên thứ tự nhập và các bản ghi lặp, dùng list.

## 3. Giao diện thao tác của Set ADT

Tên hàm và kiểu giá trị trả về dưới đây là **quy ước minh họa**; thư viện ở từng ngôn ngữ có thể đặt tên hoặc xử lý lỗi khác.

| Thao tác ADT | Ý nghĩa | Ví dụ với `S = {2, 4}` |
| --- | --- | --- |
| `contains(x)` | Kiểm tra `x` có thuộc tập không | `contains(2) → true` |
| `insert(x)` | Thêm `x` nếu chưa có | `insert(4)` giữ nguyên `S` |
| `remove(x)` | Loại `x` nếu có | `remove(2) → {4}` |
| `size()` | Trả số phần tử phân biệt | `size() → 2` (trước khi xóa) |
| `isEmpty()` | Kiểm tra tập rỗng | `isEmpty() → false` |
| `iterate()` | Duyệt mỗi phần tử đúng một lần | Thăm `2` và `4`; thứ tự tùy cài đặt |
| `clear()` | Loại bỏ tất cả phần tử | `S → ∅` |

Một cách đặc tả ba thao tác cơ bản bằng giả mã:

```text
INSERT(S, x):
    nếu CONTAINS(S, x):
        trả về false       // Không có thay đổi
    lưu x vào S
    trả về true            // S tăng một phần tử

CONTAINS(S, x):
    trả về true nếu có phần tử trong S bằng x
    ngược lại trả về false

REMOVE(S, x):
    nếu không CONTAINS(S, x):
        trả về false
    xóa phần tử bằng x khỏi S
    trả về true
```

Giả mã này mô tả **ngữ nghĩa**, chưa chỉ ra cách tìm kiếm hoặc lưu trữ. Hiện thực sử dụng bảng băm, cây hay mảng sẽ quyết định độ phức tạp cụ thể.

### Các phép toán giữa hai tập hợp

Cho `A = {1, 2, 3}` và `B = {3, 4}`:

| Phép toán | Ký hiệu | Kết quả | Ý nghĩa |
| --- | --- | --- | --- |
| Hợp | `A ∪ B` | `{1, 2, 3, 4}` | Thuộc ít nhất một trong hai tập |
| Giao | `A ∩ B` | `{3}` | Thuộc cả hai tập |
| Hiệu | `A − B` | `{1, 2}` | Thuộc `A` nhưng không thuộc `B` |
| Hiệu đối xứng | `A △ B` | `{1, 2, 4}` | Thuộc đúng một trong hai tập |

Lưu ý `A − B` khác `B − A`: phép hiệu **không giao hoán**.

Ta còn có quan hệ **tập con**: `X ⊆ Y` khi mọi phần tử của `X` đều có trong `Y`. Chẳng hạn `{1, 2} ⊆ A`, nhưng `B ⊈ A` vì `4 ∈ B` và `4 ∉ A`. Hai tập bằng nhau khi chúng có đúng cùng các phần tử; không cần cùng thứ tự chèn hoặc cùng kiểu cấu trúc lưu trữ.

## 4. Thực hành bằng Python

Trong Python, kiểu `set` là một hiện thực set dựa trên băm. Các ví dụ dùng `sorted(...)` khi in ra nhằm tạo kết quả dễ kiểm tra; **bản thân `set` không bảo đảm thứ tự duyệt**.

```python
# Tạo set từ các mã học viên, tự loại mã trùng
students = set(["HV01", "HV02", "HV01", "HV03"])
print(sorted(students))                   # ['HV01', 'HV02', 'HV03']
print(len(students))                      # 3
print("HV02" in students)                 # True

students.add("HV03")                      # Đã tồn tại: không đổi
students.add("HV04")                      # Phần tử mới
print(len(students))                      # 4

students.discard("HV99")                  # Không tồn tại: không báo lỗi
students.remove("HV04")                   # Có tồn tại: xóa phần tử
# students.remove("HV99")                 # KeyError nếu bỏ chú thích

empty_set = set()                         # {} tạo dict rỗng, không phải set
assert len(empty_set) == 0
```

Sử dụng toán tử tập hợp:

```python
a = {1, 2, 3}
b = {3, 4}

print(sorted(a | b))                      # [1, 2, 3, 4] - hợp
print(sorted(a & b))                      # [3]          - giao
print(sorted(a - b))                      # [1, 2]       - hiệu
print(sorted(a ^ b))                      # [1, 2, 4]    - hiệu đối xứng
print({1, 2} <= a)                        # True         - tập con
print(a.isdisjoint({5, 6}))               # True         - không có phần tử chung
```

Đầu vào set dựa trên băm cần có thể **băm được** (hashable) theo quy tắc của ngôn ngữ. Trong Python, chuỗi, số nguyên và tuple chứa các giá trị hashable thường phù hợp; list, dict và set thay đổi được không thể làm phần tử của `set`:

```python
valid = {(1, 2), (3, 4)}                  # Tuple có thể làm phần tử set
# invalid = {[1, 2]}                      # TypeError: unhashable type: 'list'

immutable_set = frozenset({"A", "B"})     # Bản set bất biến của Python
# immutable_set.add("C")                  # Không có phương thức add
```

Đặc biệt, một đối tượng được dùng làm khóa trong bảng băm không nên thay đổi phần dữ liệu tham gia tính hàm băm hoặc so sánh bằng nhau sau khi đã được chèn. Vi phạm quy tắc này có thể khiến việc tìm hoặc xóa phần tử trở nên sai lệch trong những ngôn ngữ cho phép khóa tùy biến.

## 5. Hiện thực Set: tại sao cùng ADT có độ phức tạp khác nhau?

Gọi `n` là số phần tử **phân biệt** đang có trong tập và `U` là số giá trị có thể có trong miền dữ liệu.

| Hiện thực | Kiểm tra thuộc tập | Chèn | Xóa | Bộ nhớ điển hình | Khi nào phù hợp |
| --- | --- | --- | --- | --- | --- |
| Bảng băm (hash set) | Trung bình `O(1)` | Trung bình `O(1)` | Trung bình `O(1)` | `O(n)` | Tra cứu nhanh, không cần phần tử được sắp |
| Cây tìm kiếm cân bằng (tree set) | `O(log n)` | `O(log n)` | `O(log n)` | `O(n)` | Cần duyệt theo thứ tự, tìm min/max hoặc truy vấn khoảng |
| Mảng **đã sắp xếp** | `O(log n)` bằng tìm kiếm nhị phân | `O(n)` do dịch phần tử | `O(n)` do dịch phần tử | `O(n)` | Tập ít thay đổi, thường xuyên đọc |
| Mảng bit (bitset) | `O(1)` theo chỉ số | `O(1)` | `O(1)` | `O(U)` bit | Miền số nguyên hữu hạn và không quá lớn |

Các đánh giá trên dùng mô hình cơ bản: thao tác so sánh, băm hoặc truy cập bit tốn thời gian hằng số; không tính chi phí sao chép các đối tượng khóa rất lớn. Với bảng băm, `O(1)` là **trung bình/kỳ vọng**, không phải bảo đảm cho mọi đầu vào. Nhiều va chạm băm có thể đẩy một thao tác lên `O(n)`; khi mở rộng bảng, một lần tái băm có thể tốn `O(n)`, dù chi phí chèn trung bình theo chuỗi thao tác vẫn thường là `O(1)` theo phân tích khấu hao.

### Bảng băm và bất biến không trùng lặp

Một hash set thường dùng `hash(x)` để xác định vị trí cần tìm, sau đó kiểm tra bằng nhau giữa các khóa cùng vị trí hoặc cùng vùng xử lý va chạm:

```text
HASH_SET_INSERT(table, x):
    vị_trí = hash(x) ánh xạ vào table
    tìm trong vùng xử lý va chạm của vị_trí
    nếu đã có khóa bằng x:
        trả về false
    lưu x, cập nhật số phần tử
    nếu cần thì mở rộng và tái băm table
    trả về true
```

**Hàm băm trùng nhau không có nghĩa là hai phần tử bằng nhau.** Hiện thực vẫn phải so sánh bằng nhau để tránh loại nhầm phần tử khác. Nếu dùng định danh đối tượng thay vì nội dung để so sánh, hai đối tượng trông giống nhau vẫn có thể được xem là hai phần tử khác nhau: quy tắc đồng nhất phải được xác định rõ trong thiết kế.

### Độ phức tạp của phép toán tập hợp

Với hai hash set `A`, `B` có kích thước `n`, `m`, giả sử phép băm và tra cứu có chi phí trung bình `O(1)`:

| Phép toán tạo tập kết quả mới | Thời gian trung bình | Bộ nhớ bổ sung lớn nhất |
| --- | --- | --- |
| Hợp `A ∪ B` | `O(n + m)` | `O(n + m)` |
| Giao `A ∩ B` | `O(min(n, m))` nếu duyệt tập nhỏ, dò tập lớn | `O(min(n, m))` |
| Hiệu `A − B` | `O(n)` nếu duyệt `A` và dò `B` | `O(n)` |
| Hiệu đối xứng `A △ B` | `O(n + m)` | `O(n + m)` |
| Kiểm tra `A ⊆ B` | `O(n)` trong trường hợp phải kiểm tra hết `A` | `O(1)` nếu chỉ tra cứu |

Các mốc trên là **độ phức tạp của thuật toán được mô tả**, không phải cam kết chung cho mọi thư viện. Chẳng hạn, một hiện thực phép giao không chọn tập nhỏ để duyệt có thể tốn `O(n)` hoặc `O(m)` khác với bảng. Bộ nhớ bổ sung tính cho kết quả mới, không tính bộ nhớ vốn đã dùng để lưu hai tập đầu vào; phép toán sửa trực tiếp tập có thể có đặc tính khác.

## 6. Bài toán thực tế: loại trùng và tìm nhóm người dùng chung

Giả sử hệ thống học tập ghi nhận người dùng tham gia hai hoạt động:

```python
attended_python = {"HV01", "HV02", "HV03", "HV03"}
attended_algorithms = {"HV02", "HV04"}

all_students = attended_python | attended_algorithms
both_courses = attended_python & attended_algorithms
python_only = attended_python - attended_algorithms

print(sorted(all_students))               # ['HV01', 'HV02', 'HV03', 'HV04']
print(sorted(both_courses))               # ['HV02']
print(sorted(python_only))                # ['HV01', 'HV03']
```

Hai dòng dữ liệu gốc có thể chứa nhiều bản ghi giống nhau; chuyển thành set giúp loại trùng, rồi phép giao trả lời nhanh câu hỏi “ai tham gia cả hai hoạt động?”. Nếu chỉ muốn đếm người dùng khác nhau, dùng `len(all_students)` thay vì đếm tổng số sự kiện ghi nhận.

### Nếu cần vừa loại trùng vừa giữ thứ tự xuất hiện?

Set không bảo đảm thứ tự, nhưng có thể kết hợp **list để lưu kết quả** và **set để kiểm tra đã gặp**:

```python
def unique_in_first_seen_order(values):
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result

events = ["HV03", "HV01", "HV03", "HV02", "HV01"]
print(unique_in_first_seen_order(events))  # ['HV03', 'HV01', 'HV02']
```

Với `k` phần tử đầu vào, thuật toán này mất thời gian trung bình `O(k)` và bộ nhớ `O(d)`, trong đó `d` là số giá trị phân biệt, nếu thao tác với hash set có chi phí trung bình hằng số. Không nên dựa vào thứ tự duyệt của `set` để giải bài toán giữ thứ tự.

### Liên hệ với duyệt đồ thị

Trong BFS hoặc DFS, một tập `visited` lưu các đỉnh đã thăm. Khi gặp đỉnh `v`, ta kiểm tra `v in visited` trước khi đưa đỉnh vào hàng đợi hoặc ngăn xếp; sau đó thêm `v` vào `visited`. Bất biến không trùng lặp giúp mỗi đỉnh được đánh dấu một lần, ngăn thuật toán lặp vô hạn trên đồ thị có chu trình. Đây là ví dụ set hỗ trợ trực tiếp cho các cấu trúc queue/stack và thuật toán đồ thị trong module.

## 7. Những nhầm lẫn cần tránh

1. **Tưởng set tự động đếm số lần xuất hiện.** `{5, 5, 5}` chỉ có một phần tử. Muốn đếm tần suất hãy dùng map từ giá trị tới bộ đếm hoặc multiset.
2. **Tưởng set luôn có thứ tự chèn hoặc cho truy cập bằng chỉ số.** Set ADT không có khái niệm phần tử thứ `i`. Trong Python, `s[0]` không hợp lệ; dùng list nếu cần chỉ số.
3. **Tưởng va chạm băm là bằng nhau.** Hai giá trị có cùng hash vẫn phải được so sánh bằng nhau riêng.
4. **Tưởng mọi thao tác set đều `O(1)`.** Tra cứu trong hash set thường `O(1)` trung bình, nhưng phép hợp hai tập phải xử lý nhiều phần tử và thường tốn `O(n + m)`.
5. **Tưởng set lưu được mọi kiểu dữ liệu.** Python yêu cầu phần tử hashable; list không thể là phần tử của `set`.
6. **Sửa set trong lúc đang duyệt nó.** Trong Python, thao tác thêm/xóa làm đổi kích thước set giữa vòng lặp có thể gây `RuntimeError`. Có thể duyệt bản sao hoặc xây tập kết quả mới:

```python
numbers = {1, 2, 3, 4, 5}
even_numbers = {x for x in numbers if x % 2 == 0}
print(sorted(even_numbers))               # [2, 4]
```

## 8. Chọn cấu trúc nào cho bài toán?

Hãy bắt đầu từ loại truy vấn quan trọng nhất:

- Chỉ cần kiểm tra tồn tại, chèn và xóa nhiều lần trên khóa có thể băm: **hash set** thường là lựa chọn đầu tiên.
- Cần duyệt tăng dần, tìm phần tử nhỏ/lớn gần một giá trị, hoặc truy vấn theo khoảng: cân nhắc **tree set** có thứ tự.
- Các giá trị là số nguyên trong miền nhỏ đã biết, chẳng hạn chỉ số `0..9999`: **bitset** có thể rất gọn và hiệu quả.
- Dữ liệu đã sắp xếp, đọc nhiều và hiếm khi thêm/xóa: **mảng đã sắp xếp** có thể đơn giản và tiết kiệm chi phí phụ trợ.
- Cần số lần xuất hiện hoặc dữ liệu đi kèm từng khóa: dùng **map/counter**, vì set sẽ cố ý loại bỏ thông tin đó.

Không có hiện thực tốt nhất cho mọi tình huống. Quy tắc chọn là **xác định bất biến cần bảo vệ, thao tác phổ biến nhất, kích thước dữ liệu và yêu cầu về thứ tự**, rồi so sánh chi phí thời gian và bộ nhớ.

## 9. Tự kiểm tra

**Bài 1.** Cho `A = {1, 2, 5}`, `B = {2, 3, 5}`. Tính `A ∪ B`, `A ∩ B`, `A − B`, `A △ B`.

**Bài 2.** Bắt đầu với set rỗng, lần lượt chèn `7, 7, 8, 7`. Kích thước cuối cùng là bao nhiêu? Vì sao?

**Bài 3.** Một chương trình cần kiểm tra hàng triệu lần xem một mã đã xuất hiện chưa, không yêu cầu thứ tự. Nên cân nhắc hash set hay list trước? Nêu giả định về độ phức tạp.

**Bài 4.** Vì sao không thể kết luận hai khóa bằng nhau chỉ vì `hash(x) == hash(y)`?

**Bài 5.** Cần thống kê số lượt đăng ký của mỗi học viên. Set có đủ dữ liệu để trả lời không? Nêu cấu trúc thay thế.

<details>
<summary>Gợi ý đáp án</summary>

1. `A ∪ B = {1, 2, 3, 5}`; `A ∩ B = {2, 5}`; `A − B = {1}`; `A △ B = {1, 3}`.
2. Kích thước là `2` vì chỉ có hai phần tử phân biệt: `7` và `8`.
3. Hash set, vì tra cứu trung bình `O(1)` với hàm băm và phân bố khóa phù hợp; dò tuyến tính list thường `O(n)` mỗi lần.
4. Đó là **va chạm băm**: nhiều khóa khác nhau có thể cùng giá trị băm. Phải so sánh bằng nhau.
5. Không. Set chỉ giữ tính hiện diện, không giữ số lần; dùng `dict`/map với khóa là mã học viên và giá trị là bộ đếm.

</details>

## Ghi nhớ

**Set ADT bảo đảm mỗi phần tử phân biệt chỉ xuất hiện một lần** và hỗ trợ kiểm tra thành viên, thêm, xóa cùng các phép toán hợp, giao, hiệu. Tính duy nhất là bất biến của ADT, còn `O(1)`, `O(log n)` hay chi phí khác phụ thuộc vào **hiện thực cụ thể**. Khi bài toán chủ yếu hỏi “đã thấy giá trị này chưa?”, set thường diễn đạt ý định rõ ràng và hiệu quả hơn việc tự tìm trong danh sách.
