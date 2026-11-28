# Thực hành truy vấn khoảng, tiền tố và phiên bản dữ liệu lịch sử

Một hệ thống lưu lịch hoạt động phải trả lời ba câu hỏi khác nhau:

1. **Truy vấn khoảng:** tổng điểm hoặc danh sách hoạt động trong các ngày `[l,r)` là gì?
2. **Truy vấn tiền tố:** những hoạt động nào có tên bắt đầu bằng chuỗi `p`?
3. **Phiên bản lịch sử:** các câu hỏi trên trả về kết quả gì **tại một phiên bản đã lưu**, ngay cả khi hoạt động hiện tại đã được sửa hoặc xóa?

Nếu chỉ lưu mảng và quét toàn bộ, ba câu hỏi đều có thể giải quyết đúng cho một tập nhỏ. Nhưng khi cần nhiều truy vấn hoặc hàng nghìn phiên bản, phải suy nghĩ về chỉ mục và cách **giữ dữ liệu cũ bất biến**. Đây là bài thực hành tổng hợp trong chương **Kiểm chứng và thực hành**: người học sẽ làm rõ đặc tả, xây dữ liệu kiểm thử bằng tay, triển khai một mô hình có thể chạy, kiểm tra bất biến, phân tích chi phí và mở rộng sang cấu trúc dữ liệu lưu phiên bản (*persistent data structures*).

Bài sử dụng mảng sắp, binary search, bảng băm, cây đoạn (*segment tree*), chia sẻ cấu trúc (*structural sharing*) và ý tưởng trie. **Phiên bản dữ liệu** ở đây là trạng thái đã được ghi nhận tại một lần cập nhật; nó khác với việc chỉ lọc bản ghi theo trường thời gian.

## 1. Mục tiêu và bài toán thực hành

Sau bài học, bạn cần có thể:

- Viết rõ điều kiện khoảng nửa mở `[l,r)` và phân biệt **tổng đoạn** với **liệt kê các bản ghi trong đoạn**.
- Tìm theo tiền tố tiêu đề bằng mảng sắp và binary search; giải thích lúc nào nên thay bằng trie.
- Giữ nguyên kết quả của phiên bản cũ khi bản ghi mới được sửa, thêm hoặc xóa.
- Kiểm chứng ba loại truy vấn bằng một mô hình tham chiếu độc lập, không chỉ bằng vài ví dụ đúng tình cờ.
- Triển khai hoặc đọc hiểu **persistent segment tree** để lấy tổng đoạn ở những phiên bản cũ.
- Phân tích độ phức tạp của **từng chỉ mục** và của **toàn bộ thao tác cập nhật đa chỉ mục**.
- Giải thích trade-off thời gian, bộ nhớ, tính nguyên tử và vòng đời phiên bản.

### Bối cảnh

Một hoạt động có các trường sau:

```text
Activity {
    id:      string      // định danh duy nhất, ổn định
    title:   string      // tên hoạt động, có thể thay
    day:     integer     // ngày quy đổi thành chỉ số 0..B-1
    points:  integer     // số điểm không âm
}
```

Trong bài, cố định `B=8` ô ngày, đánh số `0..7`. Mỗi hoạt động đóng góp toàn bộ `points` vào **ngày bắt đầu `day`** của nó. Ta không mô tả hoạt động kéo dài nhiều ngày; nếu muốn thống kê theo thời lượng hoặc theo khoảng giao nhau, phải đổi đặc tả và cấu trúc tương ứng.

Các API cần hỗ trợ:

| API | Ý nghĩa | Trật tự kết quả |
| --- | --- | --- |
| `get(version,id)` | Đọc một hoạt động theo ID tại phiên bản được chỉ định | Một bản ghi hoặc không tồn tại |
| `rangeSum(version,l,r)` | Tổng `points` của hoạt động có `l ≤ day < r` | Một số nguyên |
| `rangeEvents(version,l,r)` | Liệt kê các hoạt động có `l ≤ day < r` | Tăng dần theo `(day,id)` |
| `prefixEvents(version,p,limit)` | Liệt kê tối đa `limit` hoạt động có tiêu đề khớp tiền tố `p` | Tăng dần theo `(normalize(title),id)` |
| `create(activity)` | Thêm hoạt động mới vào trạng thái hiện hành | Tạo phiên bản mới |
| `revise(id,...)` | Đổi tên, ngày hoặc điểm của hoạt động | Tạo phiên bản mới |
| `delete(id)` | Xóa hoạt động đang tồn tại | Tạo phiên bản mới |

**Quy ước của bài:**

- Phiên bản đầu tiên là `v0`, chứa dữ liệu khởi tạo; mỗi lần cập nhật thành công sinh `v1, v2, ...`.
- Cập nhật luôn xuất phát từ phiên bản mới nhất; **không phân nhánh lịch sử** trong ví dụ cơ bản.
- Các bản ghi ở mỗi phiên bản là **bất biến**; bản ghi mới cùng ID thay cho bản ghi cũ chỉ ở phiên bản tiếp theo.
- ID của thực thể mới **không tái sử dụng trong vòng đời kho lịch sử**.
- Truy vấn khoảng dùng `0 ≤ l ≤ r ≤ B`; khoảng rỗng `[l,l)` có tổng 0 và danh sách rỗng.
- Chuỗi tiền tố được chuẩn hóa bằng Unicode NFKC rồi `casefold`, **không bỏ dấu tiếng Việt**.
- Khi tiêu đề trùng nhau, phá hòa bằng `id` để kết quả tất định.
- Không có sửa song song trong mã học tập; phần cuối bàn về cách mở rộng tính nhất quán khi có nhiều luồng.

## 2. Dữ liệu mẫu và bảng đáp án tự tính

Bắt đầu tại phiên bản `v0`:

| ID | Tiêu đề | `day` | `points` |
| --- | --- | ---: | ---: |
| A | Họp nhóm | 2 | 3 |
| B | Học máy | 4 | 5 |
| C | Báo cáo | 6 | 2 |

Các cập nhật tiếp theo:

- **`v1`:** sửa B thành tiêu đề **Hướng dẫn**, chuyển từ ngày 4 sang ngày 5, đổi điểm từ 5 thành 7.
- **`v2`:** xóa A.
- **`v3`:** thêm D với tiêu đề **Học lập trình**, ngày 2, điểm 4.

Hãy vẽ trạng thái sau mỗi cập nhật trước khi xem bảng:

| Phiên bản | A | B | C | D |
| --- | --- | --- | --- | --- |
| `v0` | Họp nhóm, 2, 3 | Học máy, 4, 5 | Báo cáo, 6, 2 | — |
| `v1` | Họp nhóm, 2, 3 | Hướng dẫn, 5, 7 | Báo cáo, 6, 2 | — |
| `v2` | — | Hướng dẫn, 5, 7 | Báo cáo, 6, 2 | — |
| `v3` | — | Hướng dẫn, 5, 7 | Báo cáo, 6, 2 | Học lập trình, 2, 4 |

Các đáp án quan trọng:

| Truy vấn | `v0` | `v1` | `v2` | `v3` |
| --- | --- | --- | --- | --- |
| `rangeSum([2,5))` | 8 = 3+5 | 3 | 0 | 4 |
| `rangeSum([2,6))` | 8 | 10 = 3+7 | 7 | 11 = 7+4 |
| `rangeSum([6,8))` | 2 | 2 | 2 | 2 |
| `prefixEvents("họ")`, lấy mọi kết quả | [B,A] | [A] | [] | [D] |
| `get("A")` | Có A | Có A | Không | Không |

Tại `v0`, tiêu đề “Học máy” và “Họp nhóm” đều khớp tiền tố **`"họ"`**, vì `normalize("Học máy")` bắt đầu bằng `"họ"`. Kết quả được **sắp theo tiêu đề chuẩn hóa**, nên B đứng trước A. “Hướng dẫn” không khớp `"họ"`.

**Bài kiểm tra cốt lõi:** sau khi tạo `v3`, hỏi lại `rangeSum(v0,2,5)` vẫn phải bằng **8**, và `prefixEvents(v0,"họ")` vẫn trả **[B,A]**. Nếu kết quả của `v0` đổi khi cập nhật dữ liệu mới, thiết kế phiên bản đã sai.

## 3. Tách ba chiều dữ liệu và ba loại truy vấn

Một bản ghi có:

- **Định danh:** `id`, dùng cho tra cứu chính xác, sửa và xóa.
- **Khóa khoảng:** `day`, dùng cho tổng đoạn và liệt kê theo ngày.
- **Khóa từ điển:** `normalize(title)`, dùng cho tiền tố.
- **Phiên bản:** số phiên bản mà một truy vấn cần nhìn thấy.

Mỗi chiều dẫn đến một chỉ mục khác nhau:

```text
                 Snapshot v
                     |
        +------------+-------------+
        |            |             |
    byId[id]      byDay         byTitle
      record    (day,id)    (normTitle,id)
                     |
                sumRoot(v)
             tổng điểm theo ngày

V0, V1, V2, V3: mỗi phiên bản gắn với
một bộ chỉ mục thuộc CÙNG trạng thái logic.
```

Nếu lưu `byDay` và `byTitle` là mảng đã sắp, việc hỏi cận có thể dùng binary search. Nếu chỉ cần tổng đoạn trên bucket ngày, dùng mảng prefix sum hoặc cây đoạn. Nếu muốn truy vấn lại bản cũ, cần giữ **snapshot**, **sự kiện để phát lại**, hoặc **cấu trúc persistent**.

Không nên dùng phiên bản mới của `byId` cùng với cây tổng đoạn của `v0` trong một lời gọi: đó là trộn hai trạng thái và có thể cho kết quả không thuộc phiên bản nào.

### 3.1. Truy vấn có kết quả khác nhau về độ phức tạp

- `rangeSum` chỉ trả **một tổng**. Có thể dùng prefix sums hoặc segment tree để không duyệt từng hoạt động.
- `rangeEvents` phải trả **`k` hoạt động**. Bất kỳ cách nào cũng cần ít nhất `Ω(k)` công việc để xuất `k` kết quả.
- `prefixEvents` có thể chỉ cần tìm vài gợi ý, nhưng nếu muốn tất cả `m` tiêu đề khớp, phải duyệt và xuất ít nhất `m` mục.
- `get(version,id)` là truy cập chính xác trong một **snapshot cụ thể**, không phải tìm phiên bản “gần nhất” nếu API đã yêu cầu số phiên bản chính xác.

## 4. Khởi đầu từ lời giải tham chiếu: quét bản ghi

Trước khi tối ưu, hãy viết một **oracle** — cách tính đúng nhưng có thể chậm. Oracle rất hữu ích để kiểm thử các cấu trúc phức tạp hơn.

Giả sử `records_v` là ánh xạ ID → Activity của đúng phiên bản `v`:

```python
import unicodedata


def normalize(text):
    return unicodedata.normalize("NFKC", text).casefold()


def slow_range_sum(records_v, lo, hi):
    return sum(
        event.points for event in records_v.values()
        if lo <= event.day < hi
    )


def slow_range_events(records_v, lo, hi):
    return sorted(
        (e for e in records_v.values() if lo <= e.day < hi),
        key=lambda e: (e.day, e.id),
    )


def slow_prefix_events(records_v, prefix, limit):
    p = normalize(prefix)
    matched = sorted(
        (e for e in records_v.values()
         if normalize(e.title).startswith(p)),
        key=lambda e: (normalize(e.title), e.id),
    )
    return matched[:max(0, limit)]
```

Với `n` hoạt động:

- `slow_range_sum`: `O(n)`.
- `slow_range_events`: lọc `O(n)` rồi sắp `k` kết quả: `O(n+k log k)` theo mô hình so sánh có chi phí hằng số.
- `slow_prefix_events`: kiểm tra toàn bộ `n` tiêu đề rồi sắp các kết quả khớp. Chi phí phụ thuộc độ dài chuỗi và số kết quả; không thể gọi là `O(|prefix|)`.
- Nếu tạo mỗi phiên bản bằng cách sao chép map, một lần cập nhật có thể tốn `O(n)` bộ nhớ và thời gian.

Oracle không phải lựa chọn tối ưu cho tải lớn, nhưng giúp xác minh chính xác **ngữ nghĩa**. Khi triển khai chỉ mục, hãy so kết quả với oracle ở **cùng phiên bản**.

## 5. Truy vấn khoảng bằng mảng sắp và binary search

Để liệt kê các hoạt động bắt đầu trong ngày `[lo,hi)`, xây mảng:

```text
byDay(v0):
    (2, A)
    (4, B)
    (6, C)
```

Tìm vị trí đầu tiên có khóa không nhỏ hơn `(lo,"")` rồi duyệt khi `day < hi`:

```text
rangeEvents(v,lo,hi):
    i = lowerBound(byDay(v), (lo, ""))
    while i < size and byDay(v)[i].day < hi:
        id = byDay(v)[i].id
        output byId(v)[id]
        i += 1
```

Vì ID là chuỗi không rỗng, `""` đứng trước mọi ID hợp lệ ở cùng ngày. Nếu dùng loại ID khác, hãy chọn đúng phần tử mốc bé nhất hoặc một cách so sánh cận phù hợp, thay vì sao chép nguyên kỹ thuật này.

| Công việc | Độ phức tạp |
| --- | --- |
| Xây `byDay` từ `n` hoạt động chưa sắp | `O(n log n)` lần so sánh |
| Tìm cận dưới | `O(log n)` lần so sánh |
| Xuất `k` mục liên tiếp | `O(k)` lần duyệt và tra ID (tra map thường kỳ vọng `O(1)`) |
| Chèn/xóa trong mảng sắp | Thường `O(n)` do dời phần tử |
| Bộ nhớ chỉ mục | `O(n)` |

Nếu dữ liệu thay đổi thường xuyên, cây tự cân bằng theo `(day,id)` có thể chèn/xóa và tìm cận trong `O(log n)`, liệt kê `k` phần tử trong `O(log n+k)`. Nếu phần lớn truy vấn trên những snapshot bất biến, mảng sắp có ưu điểm lưu trữ gọn và duyệt liên tiếp thuận lợi.

**Bẫy thường gặp:** dùng tìm kiếm nhị phân trên mảng **chưa sắp** rồi tin kết quả. Binary search đòi bất biến thứ tự của toàn mảng.

## 6. Tổng đoạn: prefix sums, Fenwick và segment tree

Đặt:

```text
bucket[d] = tổng points của các hoạt động có day = d
d thuộc [0,B)
```

Với `v0`:

```text
d:         0  1  2  3  4  5  6  7
bucket:    0  0  3  0  5  0  2  0

prefix:    0  0  0  3  3  8  8 10 10
          P0 P1 P2 P3 P4 P5 P6 P7 P8
```

Quy ước `prefix[0]=0`, `prefix[i+1]=prefix[i]+bucket[i]`. Khi đó:

```text
rangeSum(l,r) = prefix[r] - prefix[l]
```

Ví dụ `rangeSum(v0,2,5) = prefix[5]-prefix[2] = 8-0 = 8`.

**Ưu điểm của prefix sum:** xây trong `O(B)` từ bucket, hỏi tổng đoạn `O(1)`. **Nhược điểm:** thay một bucket có thể phải cập nhật `O(B)` giá trị prefix sau đó, hoặc xây lại.

Khi cần cập nhật điểm và hỏi tổng đoạn thường xuyên:

| Cấu trúc | Cập nhật một bucket | Tổng `[l,r)` | Bộ nhớ | Ghi chú |
| --- | --- | --- | --- | --- |
| Mảng bucket, cộng trực tiếp | `O(1)` | `O(r-l)` | `O(B)` | Đơn giản nhất |
| Prefix sum tĩnh | `O(B)` nếu duy trì bản đã cập nhật | `O(1)` | `O(B)` | Tốt cho ảnh chụp tĩnh |
| Fenwick tree | `O(log B)` | `O(log B)` | `O(B)` | Phù hợp tổng tiền tố và cập nhật điểm |
| Segment tree | `O(log B)` | `O(log B)` | `O(B)` | Dễ tổng quát hóa phép gộp |
| Persistent segment tree | `O(log B)` nút mới mỗi cập nhật điểm | `O(log B)` **trên một phiên bản** | `O(B+U log B)` trong mô hình chuẩn | Giữ nhiều root phiên bản |

Ở đây `U` là số **lần cập nhật điểm** đã lưu, không phải số truy vấn hoặc số bản ghi. Khi chuyển một hoạt động từ ngày cũ sang ngày mới, thường có **hai thay đổi bucket**: trừ điểm cũ và cộng điểm mới.

### 6.1. Khi nào không cần segment tree?

Nếu chỉ có `B=8` ô ngày và vài chục truy vấn, một mảng đơn giản đã đủ. Segment tree có nhiều nút, thêm độ phức tạp code và đòi kiểm tra bất biến. Nó đáng xét khi `B` lớn, có nhiều cập nhật/truy vấn, hoặc khi cần **truy vấn các phiên bản khác nhau** mà không lưu bản sao hoàn chỉnh cho từng phiên bản.

## 7. Tiền tố: từ mảng tiêu đề sắp đến trie

Chỉ mục tiêu đề của `v0` được sắp theo cặp `(normalize(title),id)`:

```text
("báo cáo", C)
("học máy", B)
("họp nhóm", A)
```

Để hỏi `prefixEvents(v0,"họ")`:

1. Chuẩn hóa tiền tố thành `"họ"`.
2. Dùng binary search tìm cặp đầu tiên có khóa tiêu đề không nhỏ hơn `("họ","")`.
3. Duyệt cho tới khi gặp tiêu đề không bắt đầu bằng `"họ"` hoặc đã có đủ `limit` kết quả.
4. Tra ID qua `byId(v0)`, không phải `byId(v3)`.

Kết quả là **[B,A]** theo thứ tự tiêu đề chuẩn hóa.

### 7.1. Phân biệt từ điển và mức độ phù hợp

Mảng sắp cho kết quả theo **thứ tự từ điển**. Nếu yêu cầu “5 hoạt động phổ biến nhất” hoặc “5 hoạt động gần ngày hiện tại nhất”, tìm cận tiền tố chỉ giúp xác định ứng viên; còn phải xếp hạng theo tiêu chí riêng, hoặc duy trì cache top-`k` có cơ chế cập nhật.

Không được tuyên bố truy vấn tiền tố trả `k` kết quả luôn chỉ tốn `O(log n)`: việc kiểm tra và xuất kết quả có chi phí theo `k` và độ dài chuỗi.

### 7.2. Trie khi thay đổi thường xuyên

Trie đặt các tiêu đề chuẩn hóa lên đường đi ký tự:

```text
root
 ├─ b ... "báo cáo" -> {C}
 └─ h
    └─ ọ
       ├─ c ... "học máy" -> {B}
       └─ p ... "họp nhóm" -> {A}
```

Tìm nút tiền tố dài `L` mất khoảng `O(L)` bước đi theo ký tự nếu phép tra cạnh đủ hiệu quả. Để lấy tất cả kết quả phải duyệt cây con và xuất các ID, với chi phí theo số nút đã thăm/ký tự và kết quả.

Thêm/xóa một tiêu đề trong trie mutable làm thay đổi đường đi của nó. Nếu một sự kiện đổi tiêu đề, phải xóa liên kết ID ở khóa cũ rồi thêm ID vào khóa mới. Nếu giữ dữ liệu lịch sử, **không được thay đổi trực tiếp trie mà các phiên bản cũ còn tham chiếu**.

### 7.3. Persistent trie là một lựa chọn nâng cao

Với **trie lưu phiên bản**, khi thêm/xóa một khóa, chỉ các nút trên đường đi từ gốc tới khóa ấy được tạo bản mới; các nhánh không đổi được **chia sẻ** với trie cũ:

```text
root_v0 -> ... old-path ... -> {A, B}
    |
    +---- các nhánh không đổi

root_v1 -> ... new-path ... -> {A}
    |
    +---- dùng lại những nhánh không đổi của v0
```

Nếu khóa dài `L`, một biến thể trie path-copying có thể tạo `O(L)` nút mới, **nhưng chi phí còn phụ thuộc biểu diễn tập ID ở nút và số cạnh mỗi nút**. Nếu mỗi nút lưu một danh sách lớn rồi sao chép cả danh sách khi đổi một ID, phép cập nhật có thể tốn hơn `O(L)`. Persistent trie không tự cho top-`k` đã xếp hạng nếu không duy trì metadata phù hợp.

Trong bài thực hành chính, ta dùng **mảng tiêu đề sắp theo mỗi snapshot** để mã ngắn, dễ đọc và dễ kiểm thử; persistent trie là hướng mở rộng khi muốn giảm chi phí ghi ở quy mô lớn.

## 8. Persistent segment tree: chỉ sao chép đường dẫn thay đổi

Cây đoạn nhị phân lưu tổng điểm theo các khoảng con. Ví dụ `B=8`:

```text
                        [0,8)
                       /     \
                  [0,4)       [4,8)
                 /    \       /    \
              [0,2) [2,4) [4,6) [6,8)
              ...     ...    ...    ...
```

**Bất biến của mỗi nút:**

```text
node.sum = sum(node.left) + sum(node.right)
```

Với nút lá tương ứng một ngày `d`, `node.sum = bucket[d]`. Nút rỗng được hiểu là tổng 0.

Nếu sửa ngày 4, một cây đoạn thông thường sẽ sửa các nút dọc đường đi tới lá ngày 4. Cây **persistent** không sửa nút cũ. Thay vào đó:

1. Đi từ gốc của phiên bản cũ đến lá cần cập nhật.
2. Tạo các nút **mới** trên đường đi, cập nhật tổng.
3. Giữ nguyên và **chia sẻ** toàn bộ nhánh không bị ảnh hưởng.
4. Trả về **gốc mới**; gốc cũ vẫn truy vấn được.

```text
v0.root  ------------> old root
                        /        \
                  old-left     old-right
                                  |
                            old leaf(day 4)

v1.root  ------------> new root
                        /        \
            shared old-left     new-right
                                  |
                             new leaf(day 4)
```

Sơ đồ mang tính ý tưởng: các nút nằm dọc đường từ root đến lá được tạo mới, còn những cây con không nằm trên đường ấy được chia sẻ. Không được sửa tổng hoặc con trỏ của nút cũ sau khi nó đã được dùng ở một phiên bản.

### 8.1. Mã giả cập nhật điểm theo path-copying

```text
add(node, segment=[l,r), position, delta):
    if r-l == 1:
        return NEW Node(sum=node.sum + delta)

    mid = (l+r)//2

    if position < mid:
        newLeft = add(node.left, [l,mid), position, delta)
        newRight = node.right           // chia sẻ
    else:
        newLeft = node.left             // chia sẻ
        newRight = add(node.right, [mid,r), position, delta)

    return NEW Node(
        sum = sum(newLeft) + sum(newRight),
        left = newLeft,
        right = newRight
    )
```

Mỗi cập nhật điểm chỉ tạo `O(log B)` nút mới đối với cây nhị phân cân bằng theo khoảng. Một phiên bản mới có thể áp dụng nhiều cập nhật điểm liên tiếp để tạo root cuối, nhưng **chỉ root cuối** được công bố như trạng thái hoàn chỉnh.

### 8.2. Liệt kê các root lịch sử

Với dữ liệu mẫu, gọi `root_v0` là cây chứa A, B, C:

```text
v0:
  day 2 += 3
  day 4 += 5
  day 6 += 2

v1: sửa B
  day 4 -= 5
  day 5 += 7
  root_v1 = add(add(root_v0, day4, -5), day5, +7)

v2: xóa A
  day 2 -= 3
  root_v2 = add(root_v1, day2, -3)

v3: thêm D
  day 2 += 4
  root_v3 = add(root_v2, day2, +4)
```

Kết quả `rangeSum(v0,2,5)=8` không đổi dù `root_v1, root_v2, root_v3` đã tồn tại. Cây không cần một bản sao hoàn chỉnh của toàn bộ `B` bucket cho mỗi phiên bản; nó giữ các nút chia sẻ.

**Phân biệt:** persistent segment tree giải quyết **tổng đoạn theo phiên bản**. Nếu còn phải liệt kê hoạt động theo ngày hoặc tìm tiền tố tiêu đề trong lịch sử, ta vẫn cần cấu trúc **có phiên bản tương ứng** cho `byId`, `byDay` và `byTitle`; chỉ giữ nhiều segment-root là chưa đủ.

## 9. Hiện thực Python 3 tích hợp ba truy vấn và lịch sử

Phiên bản mã sau kết hợp:

- **Bảng băm `by_id` cho mỗi snapshot:** bản sao của map khi cập nhật; mỗi bản ghi `Activity` bất biến.
- **Mảng `by_day` và `by_title` sắp:** tạo mới khi commit, dùng `bisect_left` khi truy vấn.
- **Persistent segment tree:** mỗi snapshot giữ một `sum_root` riêng; những node không đổi được chia sẻ.

Đây là thiết kế học tập ưu tiên **tính đúng đắn, dễ kiểm chứng và nguyên tắc không sửa phiên bản cũ**. Các mảng/map chính được dựng lại khi ghi nên **tổng chi phí cập nhật chưa tối ưu**, dù riêng chỉ mục tổng đoạn được cập nhật bằng structural sharing.

```python
from bisect import bisect_left
from dataclasses import dataclass, replace
from types import MappingProxyType
import unicodedata


def normalize(text):
    return unicodedata.normalize("NFKC", text).casefold()


@dataclass(frozen=True)
class Activity:
    id: str
    title: str
    day: int
    points: int


@dataclass(frozen=True)
class SumNode:
    total: int
    left: object = None
    right: object = None


@dataclass(frozen=True)
class Snapshot:
    by_id: object                 # mapping proxy: id -> Activity
    by_day: tuple                 # sorted (day, id)
    by_title: tuple               # sorted (normalized title, id)
    sum_root: object              # root của persistent segment tree


def point_add(node, lo, hi, day, delta):
    """Trả root MỚI, không sửa node/root cũ."""
    if hi - lo == 1:
        old_total = 0 if node is None else node.total
        return SumNode(old_total + delta)

    mid = (lo + hi) // 2
    left = None if node is None else node.left
    right = None if node is None else node.right

    if day < mid:
        left = point_add(left, lo, mid, day, delta)
    else:
        right = point_add(right, mid, hi, day, delta)

    left_total = 0 if left is None else left.total
    right_total = 0 if right is None else right.total
    return SumNode(left_total + right_total, left, right)


def query_sum(node, lo, hi, ask_lo, ask_hi):
    if node is None or ask_hi <= lo or hi <= ask_lo:
        return 0
    if ask_lo <= lo and hi <= ask_hi:
        return node.total

    mid = (lo + hi) // 2
    return (
        query_sum(node.left, lo, mid, ask_lo, ask_hi)
        + query_sum(node.right, mid, hi, ask_lo, ask_hi)
    )


class ActivityHistory:
    def __init__(self, days, initial):
        if type(days) is not int or days <= 0:
            raise ValueError("days must be positive")
        self.days = days
        self._used_ids = set()
        rows = {}
        root = None

        for item in initial:
            self._validate(item)
            if item.id in rows:
                raise ValueError("duplicate ID")
            rows[item.id] = item
            root = point_add(root, 0, days, item.day, item.points)

        self._used_ids.update(rows)
        self._versions = [self._make_snapshot(rows, root)]

    def _validate(self, item):
        if not isinstance(item.id, str) or not item.id:
            raise ValueError("ID must be a nonempty string")
        if not isinstance(item.title, str):
            raise ValueError("title must be a string")
        if type(item.day) is not int or not 0 <= item.day < self.days:
            raise ValueError("day out of range")
        if type(item.points) is not int or item.points < 0:
            raise ValueError("points must be nonnegative")

    @staticmethod
    def _make_snapshot(rows, root):
        # rows là dict riêng vừa tạo; từ đây không sửa nó nữa.
        return Snapshot(
            by_id=MappingProxyType(rows),
            by_day=tuple(sorted(
                (e.day, e.id) for e in rows.values()
            )),
            by_title=tuple(sorted(
                (normalize(e.title), e.id) for e in rows.values()
            )),
            sum_root=root,
        )

    def _snapshot(self, version):
        if type(version) is not int:
            raise TypeError("version must be an integer")
        if version < 0 or version >= len(self._versions):
            raise IndexError("version does not exist")
        return self._versions[version]

    @property
    def latest_version(self):
        return len(self._versions) - 1

    def _publish(self, rows, changes):
        # changes = iterable (day, signed delta).
        # Không công bố các root trung gian.
        root = self._versions[-1].sum_root
        for day, delta in changes:
            root = point_add(root, 0, self.days, day, delta)

        new_snapshot = self._make_snapshot(rows, root)
        self._versions.append(new_snapshot)
        return self.latest_version

    def create(self, item):
        self._validate(item)
        if item.id in self._used_ids:
            raise ValueError("ID has already been used")

        rows = dict(self._versions[-1].by_id)
        rows[item.id] = item
        version = self._publish(rows, [(item.day, item.points)])
        self._used_ids.add(item.id)
        return version

    def revise(self, id, *, title=None, day=None, points=None):
        current = self._versions[-1]
        if id not in current.by_id:
            raise KeyError(id)

        old = current.by_id[id]
        new = replace(
            old,
            title=old.title if title is None else title,
            day=old.day if day is None else day,
            points=old.points if points is None else points,
        )
        self._validate(new)

        rows = dict(current.by_id)
        rows[id] = new
        # Hai thao tác point_add có thể gộp nếu cùng day.
        version = self._publish(rows, [
            (old.day, -old.points),
            (new.day, new.points),
        ])
        return version

    def delete(self, id):
        current = self._versions[-1]
        if id not in current.by_id:
            raise KeyError(id)

        old = current.by_id[id]
        rows = dict(current.by_id)
        del rows[id]
        return self._publish(rows, [(old.day, -old.points)])

    def get(self, version, id):
        return self._snapshot(version).by_id.get(id)

    def range_sum(self, version, lo, hi):
        if not (0 <= lo <= hi <= self.days):
            raise ValueError("invalid half-open range")
        s = self._snapshot(version)
        return query_sum(s.sum_root, 0, self.days, lo, hi)

    def range_events(self, version, lo, hi):
        if not (0 <= lo <= hi <= self.days):
            raise ValueError("invalid half-open range")
        s = self._snapshot(version)
        i = bisect_left(s.by_day, (lo, ""))
        out = []
        while i < len(s.by_day):
            day, id = s.by_day[i]
            if day >= hi:
                break
            out.append(s.by_id[id])
            i += 1
        return out

    def prefix_events(self, version, prefix, limit=100):
        if type(prefix) is not str:
            raise TypeError("prefix must be a string")
        if type(limit) is not int or limit < 0:
            raise ValueError("limit must be nonnegative")

        s = self._snapshot(version)
        p = normalize(prefix)
        i = bisect_left(s.by_title, (p, ""))
        out = []
        while i < len(s.by_title) and len(out) < limit:
            title, id = s.by_title[i]
            if not title.startswith(p):
                break
            out.append(s.by_id[id])
            i += 1
        return out

    def check_version(self, version):
        """Phép kiểm tra đắt, chỉ dùng trong test."""
        s = self._snapshot(version)
        values = list(s.by_id.values())

        assert list(s.by_day) == sorted(
            (e.day, e.id) for e in values
        )
        assert list(s.by_title) == sorted(
            (normalize(e.title), e.id) for e in values
        )

        # Kiểm tra từng bucket để khẳng định root phản ánh by_id.
        for d in range(self.days):
            expected = sum(e.points for e in values if e.day == d)
            assert self.range_sum(version, d, d + 1) == expected
        assert self.range_sum(version, 0, self.days) == sum(
            e.points for e in values
        )
        return True
```

### 9.1. Tại sao mã không phá snapshot cũ?

- `Activity` và `SumNode` dùng `@dataclass(frozen=True)`, nên mã không sửa thuộc tính của những đối tượng này.
- Mỗi lần commit tạo **dict mới** `rows`, không sửa dict đang thuộc snapshot trước.
- `MappingProxyType(rows)` ngăn ghi qua map được công bố; vì `rows` chỉ là biến cục bộ và không được tiếp tục sửa sau khi công bố, mỗi snapshot giữ được ánh xạ ổn định. Nếu mã khác còn giữ một tham chiếu ghi được tới `rows` thì proxy **không** đủ; đây là quy tắc sở hữu mà thiết kế phải giữ.
- `by_day` và `by_title` là tuple chứa các cặp giá trị, được dựng mới khi commit.
- `point_add` chỉ tạo nút mới và dùng lại con trỏ tới các nút cũ; root cũ không bao giờ bị ghi đè.
- `_publish` chỉ append **snapshot hoàn chỉnh** sau khi đã tạo xong mọi chỉ mục. Nếu việc dựng chỉ mục lỗi trước đó, phiên bản chưa được thêm.

Mã dành cho **một luồng ghi/đọc có trình tự**. Nó không bảo đảm nguyên tử cho nhiều luồng đọc/ghi song song hoặc cho dữ liệu bền vững trên đĩa; cần khóa/transaction, quản lý snapshot và phục hồi crash riêng nếu triển khai thực tế.

### 9.2. Chạy kịch bản mẫu

```python
initial = [
    Activity("A", "Họp nhóm", 2, 3),
    Activity("B", "Học máy", 4, 5),
    Activity("C", "Báo cáo", 6, 2),
]
h = ActivityHistory(8, initial)

assert h.latest_version == 0
assert h.range_sum(0, 2, 5) == 8
assert [x.id for x in h.prefix_events(0, "họ")] == ["B", "A"]
assert h.check_version(0)

v1 = h.revise("B", title="Hướng dẫn", day=5, points=7)
assert v1 == 1
assert h.range_sum(v1, 2, 5) == 3
assert h.range_sum(v1, 2, 6) == 10
assert [x.id for x in h.prefix_events(v1, "họ")] == ["A"]
assert h.check_version(v1)

v2 = h.delete("A")
assert v2 == 2
assert h.range_sum(v2, 2, 6) == 7
assert h.prefix_events(v2, "họ") == []
assert h.get(v2, "A") is None
assert h.check_version(v2)

v3 = h.create(Activity("D", "Học lập trình", 2, 4))
assert v3 == 3
assert h.range_sum(v3, 2, 6) == 11
assert [x.id for x in h.prefix_events(v3, "họ")] == ["D"]
assert h.check_version(v3)

# Câu hỏi lịch sử: bản cũ PHẢI giữ nguyên.
assert h.range_sum(0, 2, 5) == 8
assert [x.id for x in h.prefix_events(0, "họ")] == ["B", "A"]
assert h.get(1, "A") is not None
assert h.get(2, "A") is None

# Biên khoảng và tiền tố:
assert h.range_sum(v3, 3, 3) == 0
assert h.range_events(v3, 7, 8) == []
assert [x.id for x in h.range_events(0, 2, 7)] == [
    "A", "B", "C"
]
assert [x.id for x in h.prefix_events(0, "họ", limit=1)] == [
    "B"
]
```

Mã kiểm thử này được cung cấp cho người học **tự chạy và mở rộng**. Nó không thay thế vòng QA chuyên môn của toàn bộ học liệu.

## 10. Phân tích độ phức tạp phải xét toàn bộ phiên bản

Gọi:

- `n_v`: số hoạt động trong phiên bản `v`.
- `B`: số bucket ngày.
- `k`: số kết quả được trả về.
- `L`: độ dài chuỗi tiêu đề/tiền tố khi tính toán so sánh và chuẩn hóa.
- `V`: số phiên bản đang giữ.

Trong mã trên:

| Thao tác | Chi phí chính |
| --- | --- |
| `get(version,id)` | Tra dict thông thường kỳ vọng `O(1)`, sau khi định vị phiên bản `O(1)` |
| `range_sum(version,l,r)` | `O(log B)` trên cây đoạn |
| `range_events(version,l,r)` | `O(log n_v+k)` lần so sánh/duyệt, cộng `k` lần tra dict kỳ vọng `O(1)` |
| `prefix_events(version,p,k)` | Tìm cận `O(log n_v)` phép so sánh chuỗi, sau đó xuất tối đa `k` phần tử khớp; tính thêm chi phí theo độ dài chuỗi |
| `point_add` của một delta | Tạo `O(log B)` nút mới và thực hiện `O(log B)` phép cộng |
| `create/revise/delete` **toàn bộ** | Sao chép map `O(n_v)` và xây hai mảng sắp `O(n_v log n_v)` lần so sánh; thêm tối đa vài cập nhật cây `O(log B)` |
| Bộ nhớ một snapshot đầy đủ | `O(n_v)` cho map và hai mảng, bên cạnh cây/đối tượng được chia sẻ |
| Bộ nhớ tất cả phiên bản | Xấp xỉ `O(\sum_v n_v + B + U log B)` với `U` là số delta điểm, bỏ qua overhead dữ liệu chuỗi và allocator |

Việc có **persistent segment tree** không làm toàn bộ lời gọi `revise` trong ví dụ trở thành `O(log B)`: mã vẫn sao chép map và xây lại hai chỉ mục sắp. Đây là điểm quan trọng khi phân tích một hệ nhiều chỉ mục: **chi phí commit là tổng chi phí của mọi chỉ mục bị ảnh hưởng**.

### 10.1. Khi nào nên tối ưu hơn?

Nếu số phiên bản rất lớn và mỗi phiên bản chỉ đổi một bản ghi, chi phí sao chép `O(n_v)` cho mỗi commit có thể quá cao. Khi đó có thể xem xét:

- **Persistent map** (ví dụ HAMT) cho `id → Activity`, chia sẻ những nhánh không đổi, cập nhật chỉ tạo các nút dọc đường truy cập theo cấu trúc cụ thể.
- **Persistent balanced BST/treap** theo `(day,id)` để liệt kê theo ngày mà không dựng lại toàn bộ mảng sắp.
- **Persistent trie/radix tree** theo tiêu đề chuẩn hóa, có tập ID ở các khóa đầu cuối; cần thiết kế cẩn thận khi một tiêu đề có nhiều ID.
- **Persistent segment tree** theo bucket để tổng đoạn ở phiên bản cũ vẫn nhanh.
- **Event sourcing kèm checkpoint** khi phù hợp tải và yêu cầu lưu trữ: lưu các thay đổi, tạo snapshot định kỳ, phát lại để tái tạo phiên bản; đánh đổi chi phí đọc lịch sử và xử lý sự kiện.

Cấu trúc persistent cho phép chia sẻ nhiều dữ liệu giữa các phiên bản. Tuy nhiên, **mỗi chỉ mục được lưu phiên bản riêng phải cùng trỏ tới trạng thái logic của một commit**. Chỉ dùng persistent map còn chỉ mục prefix là trie mutable dùng chung sẽ vẫn làm sai truy vấn tiền tố lịch sử.

## 11. Kiểm chứng bằng mô hình tham chiếu độc lập

Không nên kiểm tra một thuật toán tối ưu chỉ bằng cách chạy chính thuật toán đó lần nữa. Một **oracle** đơn giản, chậm nhưng độc lập giúp phát hiện sai lệch.

### 11.1. Kiểm tra từng truy vấn với quét trực tiếp

```python
def check_against_oracle(history):
    for v in range(history.latest_version + 1):
        # Trong mã học tập, dùng snapshot nội bộ chỉ cho kiểm thử.
        rows = history._snapshot(v).by_id
        for lo in range(history.days + 1):
            for hi in range(lo, history.days + 1):
                assert history.range_sum(v, lo, hi) == (
                    slow_range_sum(rows, lo, hi)
                )
                assert history.range_events(v, lo, hi) == (
                    slow_range_events(rows, lo, hi)
                )

        for prefix in ["", "h", "họ", "b", "xyz"]:
            for limit in [0, 1, 2, 100]:
                assert history.prefix_events(v, prefix, limit) == (
                    slow_prefix_events(rows, prefix, limit)
                )

    return True
```

Đoạn này giả định ba hàm `slow_*` đã khai báo ở phần 4 và các lớp ở phần 9 đã được định nghĩa. Với `B=8`, duyệt mọi cặp `(lo,hi)` không tốn nhiều; với `B` lớn, nên chọn các biên và tập khoảng thử đại diện thay vì kiểm tra mọi cặp.

### 11.2. Thuộc tính quan trọng hơn ví dụ cụ thể

| Thuộc tính | Cách kiểm tra |
| --- | --- |
| **Phiên bản cũ bất biến** | Ghi kết quả tại `v0`, tạo `v1..vN`, hỏi lại `v0` và so chính xác |
| **Tổng toàn miền** | `rangeSum(v,0,B) == sum(points của mọi bản ghi trong v)` |
| **Tổng theo phân hoạch** | Với `l ≤ m ≤ r`, `sum(v,l,r) == sum(v,l,m)+sum(v,m,r)` |
| **Khoảng rỗng** | `rangeSum(v,x,x) == 0` và `rangeEvents(v,x,x) == []` |
| **Đúng tập ID trong khoảng** | Mọi kết quả có `l ≤ day < r`, không thiếu hoặc trùng ID |
| **Tiền tố** | Mọi kết quả có tiêu đề chuẩn hóa bắt đầu bằng `normalize(p)` |
| **Thứ tự** | Khoảng theo `(day,id)`; tiền tố theo `(normalize(title),id)` |
| **Cập nhật** | Sửa ngày/điểm/tên chỉ ảnh hưởng phiên bản mới; ID vẫn đúng |
| **Xóa** | ID bị xóa không tồn tại từ phiên bản xóa trở đi, nhưng vẫn có ở bản cũ |
| **Không tái sử dụng ID** | Chèn lại ID từng dùng phải bị từ chối theo chính sách bài này |

Một phép kiểm tra hấp dẫn nhưng **không đầy đủ** là chỉ so tổng toàn miền. Nếu một hoạt động bị chuyển từ ngày 2 sang ngày 5, tổng toàn miền không đổi nếu điểm không đổi, nhưng tổng của nhiều khoảng riêng đã đổi. Vì vậy cần kiểm tra **nhiều khoảng**, đặc biệt là các biên sát ngày được cập nhật.

### 11.3. Kiểm thử ngẫu nhiên có hạt giống cố định

Một kiểm thử *property-based* đơn giản có thể chọn ngẫu nhiên thao tác chèn, sửa, xóa với `random.Random(seed)` và sau mỗi commit:

1. So `get`, `rangeSum`, `rangeEvents`, `prefixEvents` với oracle.
2. Hỏi lại một vài phiên bản cũ đã lưu.
3. Kiểm tra các khoảng `[0,B)`, `[x,x)`, `[x,x+1)` và một vài khoảng ngẫu nhiên.
4. Tạo nhiều hoạt động cùng ngày, cùng tiêu đề và cùng tiền tố.
5. Thử các title có Unicode kết hợp, chữ hoa/thường và các dấu tiếng Việt.

Nếu một chuỗi thao tác thất bại, hãy lưu **seed và chuỗi thao tác tối thiểu gây lỗi** để tái hiện. Việc thêm random test không thay thế kiểm thử những điều kiện biên có chủ đích.

## 12. Những lỗi thường gặp khi kết hợp truy vấn và lịch sử

### 12.1. Sửa trực tiếp bản ghi được các snapshot cũ chia sẻ

Sai:

```python
old = versions[v0]["B"]
old.points = 7                 # nếu old là mutable object
```

Nếu `old` được dùng chung giữa `v0` và `v1`, cách sửa này khiến truy vấn lịch sử thay đổi theo. Giải pháp là dùng bản ghi bất biến và **tạo bản ghi mới cho lần sửa**, hoặc sao chép đúng mức cần thiết trước khi sửa.

### 12.2. Sao chép nông cấu trúc nhưng vẫn sửa đối tượng lồng bên trong

```python
new_map = old_map.copy()
new_map["B"].title = "Hướng dẫn"
```

Nếu hai map cùng tham chiếu đối tượng B mutable, `old_map["B"]` cũng thay đổi. *Shallow copy* chỉ sao chép container ngoài, không tự sao chép mọi đối tượng.

### 12.3. Cây persistent nhưng sửa node cũ

Một hàm cập nhật như `node.total += delta` có thể làm mọi root chia sẻ node đó nhìn thấy tổng mới. Phải tạo **node mới trên đường cập nhật** và giữ những node cũ bất biến.

### 12.4. Trộn root của một phiên bản với chỉ mục khác phiên bản

Ví dụ `rangeSum(v0,...)` dùng `sumRoot(v0)` nhưng `rangeEvents(v0,...)` lấy `byDay(v3)`. Hai kết quả mâu thuẫn không phải vì thuật toán tổng đoạn sai mà vì trạng thái đọc không thuộc cùng snapshot.

### 12.5. Nhầm khoảng đóng và nửa mở

Với `[2,5)`, hoạt động ở ngày 5 **không** thuộc kết quả. Dùng điều kiện `day <= hi` hoặc `prefix[hi+1]-prefix[lo]` khi API đã quy định nửa mở sẽ sinh lỗi lệch một.

### 12.6. Quên sửa chỉ mục sau khi đổi ngày hoặc tiêu đề

Nếu chỉ cập nhật `byId`, `byDay` vẫn chứa cặp ngày cũ hoặc `byTitle` giữ tên cũ. Mỗi snapshot phải thỏa bất biến rằng các chỉ mục phụ đúng với tập bản ghi cùng phiên bản.

### 12.7. Trie không lưu được nhiều ID có cùng tiêu đề

Một map `title → id` có thể ghi đè khi hai hoạt động cùng tiêu đề. Cần `title → Set<ID>` hoặc khóa ghép. Khi xóa một hoạt động, chỉ xóa ID của nó; không được xóa luôn mọi hoạt động cùng tiêu đề.

### 12.8. Hiểu `O(log B)` là chi phí toàn bộ hệ thống

Persistent segment tree cập nhật tổng đoạn trong `O(log B)`, nhưng nếu cùng commit còn sao chép map `O(n)` và xây mảng sắp `O(n log n)`, chi phí thực của commit vẫn bị chi phối bởi những phần đó.

### 12.9. Không quản lý vòng đời phiên bản

Lưu mọi phiên bản mãi mãi tiêu tốn bộ nhớ, dù có structural sharing. Cần xác định thời gian lưu, nhu cầu audit, cách cắt bỏ phiên bản cũ và cơ chế giải phóng node không còn root nào tham chiếu. Trong ngôn ngữ có quản lý bộ nhớ thủ công cần đặc biệt cẩn thận với vòng đời node chia sẻ.

### 12.10. Cho phép cập nhật đồng thời mà không có điểm commit nguyên tử

Hai luồng có thể cùng đọc snapshot mới nhất rồi mỗi luồng tạo bản mới; nếu không đồng bộ/cas phiên bản, một cập nhật có thể **ghi đè** cập nhật khác (*lost update*). Nếu người đọc lấy map từ một phiên bản và segment-root từ phiên bản khác, tính nhất quán đọc cũng bị phá. Cần một cơ chế công bố **một đối tượng snapshot hoàn chỉnh**, điều phối writer và quy tắc đọc phù hợp.

## 13. Mở rộng: version, snapshot, event log và thời gian thực

### 13.1. Version number không nhất thiết là timestamp

`v0, v1, v2...` là **thứ tự commit logic**. Nó không nói trực tiếp thời điểm UTC nào bản ghi có hiệu lực. Nếu ứng dụng cần truy vấn *as of 2026-03-01 12:00 UTC*, phải có bảng ánh xạ từ mốc thời gian/transaction sang version theo quy tắc rõ ràng.

Khi có cập nhật ngoài thứ tự, timestamp sự kiện và thời điểm commit có thể khác nhau. Phải xác định “lịch sử” nghĩa là **trạng thái hệ thống đã biết tại thời điểm commit** hay **dữ liệu có hiệu lực nghiệp vụ tại một thời điểm**; đây là hai chiều thời gian có thể khác nhau (*transaction time* và *valid time*).

### 13.2. Persistent structure khác với event sourcing

**Persistent data structure** giữ nhiều root/phiên bản với structural sharing, nên truy vấn phiên bản cũ thường không cần phát lại toàn bộ lịch sử.

**Event sourcing** lưu chuỗi sự kiện thay đổi, có thể tái dựng trạng thái bằng cách phát lại từ đầu hoặc từ checkpoint. Nó thuận cho audit và tái tạo, nhưng truy vấn một phiên bản quá cũ có thể tốn chi phí replay nếu không có checkpoint/chỉ mục phù hợp.

Hai kỹ thuật có thể **kết hợp**: event log cho nguồn thay đổi, persistent index hoặc snapshot/checkpoint cho truy vấn nhanh. Không nên tuyên bố một kỹ thuật thay thế hoàn toàn kỹ thuật còn lại.

### 13.3. Lịch sử tuyến tính và lịch sử có nhánh

Mã thực hành chỉ cho phép commit từ phiên bản mới nhất:

```text
v0 -> v1 -> v2 -> v3
```

Một hệ chỉnh sửa hợp tác có thể cho phép tạo nhánh:

```text
        v1a -> v2a
       /
v0 ---+
       \
        v1b -> v2b
```

Trong mô hình phân nhánh, một phiên bản cần tham chiếu **parent version** hoặc danh sách parent; việc gộp nhánh phải có quy tắc giải quyết xung đột. Tạo root persistent mới từ bất kỳ root cũ thường khả thi về mặt cấu trúc, nhưng quản lý ID, giao dịch và chỉ mục đi kèm vẫn cần thiết kế riêng.

### 13.4. Snapshot bền vững qua crash là yêu cầu khác

Bản mã dùng bộ nhớ RAM; tiến trình kết thúc có thể mất mọi phiên bản. Nếu phải lưu lịch sử lâu dài, cần ghi snapshot/log và metadata commit vào nơi lưu bền vững, dùng giao dịch hoặc giao thức phục hồi đúng. Một `@dataclass(frozen=True)` chỉ làm đối tượng khó bị sửa trong mã, không tạo độ bền dữ liệu qua sự cố.

## 14. Bài tập theo cấp độ

### Bài 1 — Tính tay tổng đoạn

Tại `v0`, tính `rangeSum(0,4,7)` và `rangeSum(0,5,5)`. Tại `v1`, tính `rangeSum(1,4,7)`.

*Đáp án:* `v0:[4,7)` gồm B=5 và C=2 nên bằng **7**. Khoảng rỗng `[5,5)` bằng **0**. `v1:[4,7)` gồm B=7 và C=2 nên bằng **9**.

### Bài 2 — Sửa một ngày nhưng giữ bản cũ

Tại `v1`, B chuyển từ ngày 4 sang 5 và tăng điểm 5→7. Nêu chính xác các delta cần áp dụng lên root `v0` và kết quả hai bucket ngày 4, 5 trong `v1`.

*Đáp án:* `(4,-5)` và `(5,+7)`. Ngày 4 từ 5 thành 0, ngày 5 từ 0 thành 7. Root `v0` vẫn trả ngày 4 bằng 5.

### Bài 3 — Truy vấn tiền tố

Vì sao `prefixEvents(v0,"họ")` trả [B,A] mà không phải [A,B]? Nếu yêu cầu trả theo ngày tăng dần thì cần thay gì?

*Đáp án:* thứ tự hiện tại là tiêu đề chuẩn hóa: “học máy” đứng trước “họp nhóm”. Muốn theo ngày thì phải xác định tiêu chí mới `(day,id)` và sắp lại các kết quả khớp, hoặc duy trì chỉ mục phù hợp; không nên thay đổi thứ tự API mà không sửa hợp đồng.

### Bài 4 — Độ phức tạp cập nhật đa chỉ mục

Một người tuyên bố: “Vì dùng persistent segment tree, `revise()` của lớp `ActivityHistory` chỉ mất `O(log B)`.” Chỉ ra vấn đề.

*Đáp án:* `revise()` còn sao chép `by_id` và xây lại `by_day`/`by_title`; các bước này có thể tốn `O(n log n)` lần so sánh. `O(log B)` chỉ áp dụng cho mỗi delta trên cây đoạn.

### Bài 5 — Sai lệch một ở biên

Một hàm lấy sự kiện trong `[2,5)` dùng `if 2 <= event.day <= 5`. Hãy đưa ra một phản ví dụ trong dữ liệu lịch sử.

*Đáp án:* tại `v1`, B có `day=5`. Hàm sai sẽ đưa B vào `[2,5)` dù biên phải 5 phải được loại trừ.

### Bài 6 — Bảo vệ lịch sử

Một lập trình viên copy dict của `v0` sang `v1`, nhưng các giá trị dict là đối tượng mutable và sửa `title` trực tiếp. Điều gì xảy ra? Nêu hai cách tránh.

*Đáp án:* cả hai dict có thể cùng trỏ tới một đối tượng và `v0` đổi theo. Có thể dùng các bản ghi bất biến + tạo bản ghi mới bằng `replace`, hoặc deep copy/structural sharing có nguyên tắc không sửa đối tượng đã công bố.

### Bài 7 — Kiểm chứng tổng đoạn theo phân hoạch

Chứng minh với `l ≤ m ≤ r`:

```text
rangeSum(v,l,r) =
    rangeSum(v,l,m) + rangeSum(v,m,r)
```

*Gợi ý:* hai khoảng nửa mở `[l,m)` và `[m,r)` rời nhau và hợp thành `[l,r)`. Mỗi hoạt động được tính đúng một lần dựa vào `day`.

### Bài 8 — Persistent trie

Nếu một tiêu đề dài `L` được đổi trong snapshot mới, giải thích vì sao một persistent trie có thể chia sẻ các nhánh không nằm trên hai đường tiêu đề cũ/mới. Nêu một lý do khiến chi phí sửa thực tế không chỉ là `O(L)`.

*Định hướng:* path-copying chỉ tạo node dọc đường thay đổi, nhưng nếu mỗi node chứa danh sách ID lớn phải sao chép hoặc metadata top-`k`, chi phí thêm theo số ID/cấu trúc phụ.

### Bài 9 — Giải pháp nào hợp lý?

Hệ thống chỉ có 8 bucket ngày, 100 hoạt động và khoảng 10 phiên bản. Mọi truy vấn chỉ xảy ra khi người dùng nhấn nút “xem báo cáo”. Có nhất thiết cần persistent segment tree không?

*Đáp án:* không. Snapshot map nhỏ và quét trực tiếp có thể đơn giản hơn, dễ kiểm chứng và đủ nhanh. Chỉ chọn cấu trúc phức tạp hơn khi số liệu tải hoặc yêu cầu cho thấy lợi ích đáng kể.

### Bài 10 — Version và as-of time

Một hoạt động diễn ra trong ngày 2 nhưng chỉ được nhập vào hệ thống ở commit `v3`. Nó có xuất hiện trong truy vấn `rangeEvents(v0,2,3)` không?

*Đáp án:* không, vì `v0` không biết bản ghi ấy. Trường `day=2` mô tả thời gian nghiệp vụ, còn `v3` là thời điểm hệ thống ghi nhận bản ghi. Muốn truy vấn lịch sử theo *valid time* phải định nghĩa cách khác.

### Bài 11 — Đọc nhất quán đa chỉ mục

Một tác vụ đọc `by_id` ở phiên bản `v3` nhưng đọc `by_title` ở `v0`. Nó hỏi tiền tố `"họ"` và nhận ID B từ `v0`, rồi tra B trong `v3` thấy tiêu đề “Hướng dẫn”. Hệ thống đã sai ở đâu?

*Đáp án:* trộn các chỉ mục khác phiên bản. Truy vấn phải lấy tất cả đường truy cập từ **cùng snapshot** hoặc một transaction/snapshot-consistent view.

### Bài 12 — Nhiều người ghi

Hai luồng cùng đọc phiên bản mới nhất `v3`. Luồng A thêm E, luồng B sửa C; cả hai xây snapshot `v4` độc lập rồi chỉ có bản của B được công bố. Loại lỗi nào xảy ra?

*Đáp án:* *lost update* — thay đổi thêm E bị ghi đè. Cần điều phối writer bằng lock, compare-and-swap/version check và retry, hoặc transaction đảm bảo đúng ngữ nghĩa mong muốn.

## 15. Checklist kiểm chứng trước khi kết thúc thực hành

Đối với một lời giải, hãy xác nhận:

- **Đặc tả đúng:** ngày thuộc `0..B-1`, khoảng nửa mở, điểm không âm, tiêu đề và ID hợp lệ.
- **Nguồn chuẩn:** mỗi snapshot có map ID → bản ghi rõ ràng; không có một ID xuất hiện hai lần trong trạng thái.
- **Bất biến mảng sắp:** `by_day` đúng theo `(day,id)`, `by_title` đúng theo `(normalize(title),id)`.
- **Bất biến tổng đoạn:** mỗi nút có tổng bằng hai nút con; tổng của mỗi bucket bằng tổng điểm các bản ghi cùng ngày.
- **Bất biến lịch sử:** commit mới không sửa record, map, tuple hoặc node đã công bố trong phiên bản cũ.
- **Cập nhật:** khi sửa ngày/điểm phải trừ đóng góp cũ và cộng đóng góp mới; đổi tên phải cập nhật khóa tiền tố.
- **Xóa:** các chỉ mục của phiên bản mới không giữ ID đã xóa; phiên bản cũ vẫn có ID đó.
- **Thứ tự và Unicode:** normalize khi lập chỉ mục và khi hỏi giống nhau; có khóa ghép phá hòa.
- **Biên:** khoảng rỗng, ngày đầu/cuối, prefix rỗng, limit=0, ID thiếu, version không hợp lệ, tiêu đề trùng.
- **Chi phí:** phân tích toàn bộ commit và bộ nhớ mọi phiên bản, không chỉ một cây đoạn.
- **Kiểm thử:** có oracle độc lập, bảng đáp án tính tay, kiểm thử ngẫu nhiên tái hiện được và kiểm tra lại version cũ.
- **Triển khai thực tế:** nếu nhiều luồng hoặc cần lưu bền vững, có quy tắc commit nguyên tử, giao dịch và lưu phiên bản tương ứng.

## Kết luận

Truy vấn khoảng, truy vấn tiền tố và truy vấn lịch sử là ba bài toán liên quan nhưng có bất biến khác nhau. **Mảng sắp và binary search** giúp liệt kê bản ghi theo ngày hoặc tiêu đề; **prefix sum/Fenwick/segment tree** xử lý tổng đoạn; **trie** hướng tới truy vấn tiền tố động; còn **snapshot và cấu trúc persistent** giữ kết quả cũ bất biến khi dữ liệu mới thay đổi.

Trong bài thực hành này, một **snapshot gồm nhiều chỉ mục của cùng phiên bản** là đơn vị đúng đắn quan trọng nhất. Persistent segment tree chỉ sao chép đường cập nhật và cho phép `rangeSum(v,l,r)` nhanh trên mỗi root lịch sử; tuy nhiên, phải phân tích thêm chi phí của bản ghi chính và các chỉ mục tiền tố/khoảng. Hãy dùng oracle, thuộc tính bất biến và các tình huống cập nhật–xóa–hỏi lại lịch sử để chứng minh lời giải đúng **trước khi** tìm cách tối ưu thời gian và bộ nhớ.
