# Chi phí nối lặp nhiều lần và vai trò của bộ đệm tăng trưởng

Một chương trình tạo báo cáo từ 10.000 dòng thường phải nối nhiều đoạn văn bản nhỏ. Cách đơn giản là giữ một chuỗi kết quả rồi cộng thêm từng đoạn. Cách khác là dùng **bộ đệm tăng trưởng (growing buffer)**: giữ dung lượng dự phòng, thêm các đoạn vào cuối và chỉ tạo giá trị kết quả khi hoàn tất. Hai cách cho cùng đầu ra nhưng có thể chênh lệch rất lớn về số lần cấp phát và lượng dữ liệu phải sao chép.

Bài học thuộc chương **Chuỗi và dãy bit** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trọng tâm là phân tích **thời gian, bộ nhớ và bất biến** khi nối nhiều đoạn; từ đó hiểu tại sao bộ đệm tăng trưởng là một ứng dụng quan trọng của **mảng động**, và chọn cách xây dựng chuỗi phù hợp với từng bài toán.

## 1. Phải định nghĩa chính xác bài toán nối chuỗi

Giả sử đầu vào có `k` đoạn `p₁, p₂, …, pₖ`. Độ dài đoạn thứ `j` theo một đơn vị lưu trữ xác định là `mⱼ`. Gọi:

- `Sⱼ = m₁ + m₂ + ⋯ + mⱼ` là độ dài tiền tố sau khi nối `j` đoạn.
- `N = Sₖ` là tổng độ dài đầu ra.
- `k` là số lần thêm đoạn, không nhất thiết bằng `N`.

Chuỗi kết quả là:

```text
result = p1 + p2 + ... + pk
```

Nếu đơn vị là byte UTF-8 thì `N` là số byte, còn nếu là UTF-16 code unit thì `N` là số đơn vị mã 16 bit. **Không được tự đồng nhất `N` với số ký tự hiển thị.** Ví dụ ký hiệu `🙂` có 4 byte UTF-8, 2 code unit UTF-16 nhưng thường là 1 grapheme cluster.

Một thuật toán xây dựng chuỗi từ đầu vào `N` đơn vị phải ít nhất **ghi hoặc biểu diễn đủ `N` đơn vị đầu ra**, nên thời gian `Ω(N)` là mốc so sánh tự nhiên nếu bắt buộc tạo một vùng kết quả liên tiếp. Mục tiêu hợp lý là tránh ghi lặp lại các tiền tố đã hoàn thành.

## 2. Vì sao nối lặp có thể dẫn đến chi phí bậc hai?

Xét một chuỗi **bất biến** được triển khai theo cách mà phép nối hai đoạn cấp phát bộ nhớ mới rồi sao chép cả hai toán hạng. Với mỗi lần:

```text
result = result + nextPart
```

chương trình phải sao chép cả phần `result` cũ và `nextPart` vào chuỗi mới dài `Sⱼ` đơn vị.

Với `k` lần nối, tổng số đơn vị được ghi vào kết quả trung gian là:

\[
C_{\text{concat}} = \sum_{j=1}^{k} S_j.
\]

Vì `Sⱼ ≤ N`, ta có chặn trên `C_concat ≤ kN`. Nếu các đoạn có độ dài tương đương nhau, cụ thể `mⱼ = m`:

\[
S_j = jm,\qquad
C_{\text{concat}} = m\sum_{j=1}^{k}j
= \frac{m\,k(k+1)}{2}
= \Theta(mk^2).
\]

Vì `N = mk`, công việc này bằng `Θ(Nk)`. Khi mỗi đoạn dài một số cố định đơn vị (`m = Θ(1)`) thì `k = Θ(N)` và tổng sao chép trở thành **`Θ(N²)`**.

### Ví dụ có thể tính bằng tay

Thêm tuần tự tám ký hiệu đơn vị vào chuỗi ban đầu rỗng, giả sử mỗi lần tạo đúng một chuỗi mới:

| Lần nối | Độ dài kết quả | Số đơn vị ghi vào chuỗi mới |
|---:|---:|---:|
| 1 | 1 | 1 |
| 2 | 2 | 2 |
| 3 | 3 | 3 |
| 4 | 4 | 4 |
| 5 | 5 | 5 |
| 6 | 6 | 6 |
| 7 | 7 | 7 |
| 8 | 8 | 8 |
| **Tổng** | **8** | **36** |

Đầu ra chỉ có 8 đơn vị nhưng tổng các vùng kết quả đã nhận 36 đơn vị ghi. Phần lớn công việc là **chép lại tiền tố**, không tạo thêm thông tin mới.

Nếu thêm **10.000 đoạn, mỗi đoạn 10 đơn vị**, đầu ra dài `N = 100.000` đơn vị, song tổng độ dài các chuỗi trung gian là:

\[
10 \times \frac{10.000 \times 10.001}{2}
= 500.050.000\ \text{đơn vị}.
\]

Đây là ví dụ định lượng của mô hình “mỗi lần nối đều sao chép toàn bộ tiền tố”; chưa tính cấp phát, giải phóng bộ nhớ và metadata. Một số runtime có tối ưu nối chuỗi riêng, nên không nên lấy con số này làm dự đoán hiệu năng tuyệt đối cho mọi triển khai.

### Mô hình này có những giả định gì?

- Kết quả của mỗi phép nối là một chuỗi mới **lưu liên tiếp** và phải sao chép hai toán hạng.
- Không có cơ chế chia sẻ tiền tố, tối ưu nối tại chỗ hoặc hợp nhất các biểu thức.
- Các phép sao chép tính theo **đơn vị lưu trữ**; nếu mã hóa Unicode có độ rộng thay đổi, chi phí tính theo byte hoặc code unit có thể khác số code point.

Python, Java, JavaScript hay C++ có thể có tối ưu runtime hoặc đối tượng chuỗi khác nhau. Vì thế, khẳng định chính xác phải là: **nối lặp gây chi phí bậc hai khi mỗi lần nối phải sao chép toàn bộ tiền tố và số đoạn tăng tỷ lệ với độ dài đầu ra**.

## 3. Bộ đệm tăng trưởng giải quyết phần việc dư thừa như thế nào?

Bộ đệm tăng trưởng giữ ba thông tin:

```text
buffer   : vùng chứa các đơn vị
length   : số đơn vị đã thực sự ghi
capacity : số đơn vị vùng nhớ có thể chứa

Ví dụ:
index:     0   1   2   3   4   5   6   7
buffer:   [A] [B] [C] [D] [ ] [ ] [ ] [ ]
          └──── length = 4 ────┘
          └──────── capacity = 8 ────────┘
```

**Bất biến cơ bản** là:

\[
0 \leq \text{length} \leq \text{capacity}.
\]

Chỉ vùng `[0, length)` tạo thành nội dung logic; không được đọc phần dung lượng dự phòng như văn bản. Khi thêm đoạn dài `m`:

1. Xác định `required = length + m` và kiểm tra tràn số nguyên.
2. Nếu `required ≤ capacity`, ghi đoạn mới ở cuối nội dung đang có.
3. Nếu thiếu chỗ, cấp phát vùng đủ lớn, sao chép nội dung cũ **một lần** sang vùng mới.
4. Ghi đoạn mới, rồi cập nhật `length` chính xác.

Giả mã đơn giản:

```text
append(chunk):
    m = chunk.length_in_storage_units
    required = checked_add(length, m)

    if required > capacity:
        newCapacity = max(required, max(1, 2 * capacity))
        newBuffer = allocate(newCapacity)
        copy(newBuffer, 0, buffer, 0, length)
        buffer = newBuffer
        capacity = newCapacity

    copy(buffer, length, chunk, 0, m)
    length = required
```

Mã trên dùng để diễn tả thuật toán. Triển khai thật còn phải xử lý **lỗi cấp phát, nguồn và đích chồng lấn, tham chiếu tới bộ đệm cũ** và quy tắc an toàn ngoại lệ. Chẳng hạn, nếu `chunk` là view trỏ vào chính `buffer`, việc đổi chỗ `buffer` có thể làm nguồn sao chép không còn hợp lệ; API phải bảo đảm nguồn được giữ ổn định hoặc xử lý trường hợp chồng lấn.

Nhờ `capacity`, hầu hết các lần thêm không phải chép lại tiền tố. Chỉ khi hết chỗ, builder mới phải cấp phát và sao chép.

## 4. Quy tắc tăng dung lượng quyết định độ phức tạp

Không phải bộ đệm tăng trưởng nào cũng hiệu quả như nhau. Cùng phép `append` nhưng cách tăng `capacity` có thể làm tổng công việc từ gần tuyến tính thành bậc hai.

### 4.1. Tăng từng đơn vị: ít chỗ thừa nhưng tốn sao chép

Giả sử ban đầu dung lượng 1, mỗi khi đầy thì chỉ tăng thêm 1 đơn vị. Khi thêm một đơn vị mới thứ `j`, có thể phải cấp phát vùng `j` đơn vị và sao chép `j - 1` đơn vị cũ.

Tổng phần bị chép lại:

\[
0+1+2+\cdots+(N-1)=\frac{N(N-1)}2=\Theta(N^2).
\]

Dung lượng dự phòng có thể rất nhỏ nhưng công cấp phát/sao chép tăng mạnh. Nếu thay vì 1 đơn vị, tăng cố định `h` đơn vị mỗi lần, tổng sao chép trong mô hình thêm đơn vị vẫn có bậc `\Theta(N^2/h)` khi `h` cố định và `N` đủ lớn.

### 4.2. Tăng theo hệ số: nhiều chỗ dự phòng, tổng sao chép tuyến tính

Quy tắc thông dụng: khi hết chỗ thì nhân `capacity` với 2, trừ khi đoạn mới cần nhiều hơn.

```text
capacity: 1 → 2 → 4 → 8 → 16 → 32 → 64 → ...
```

Nếu thêm từng đơn vị, các lần cấp phát lại sẽ sao chép số đơn vị cũ:

```text
1, 2, 4, 8, 16, ...
```

Giả sử dung lượng cuối là `2^q`, tổng số đơn vị cũ đã sao chép là:

\[
1+2+4+\cdots+2^{q-1}=2^q-1.
\]

Vì `2^q < 2N` khi kết quả vừa vượt ngưỡng `2^{q-1}`, tổng sao chép ở các lần tăng dung lượng **nhỏ hơn `2N`**. Cộng với `N` đơn vị dữ liệu thực sự được ghi, chi phí xây dựng là **`O(N)`**, bỏ qua chi phí cố định của mỗi lời gọi.

Với `k` lời gọi `append` có tổng độ dài `N`, mô hình chi phí tổng quát thường được viết **`O(N+k)`**: `O(N)` cho dữ liệu và sao chép do tăng dung lượng, cộng `O(k)` để xử lý các lời gọi. Khi mỗi lần thêm có ít nhất một đơn vị, `k ≤ N`, nên tổng là `O(N)`.

### 4.3. “Khấu hao `O(1)`” không có nghĩa mọi lần đều nhanh như nhau

Với `append` một đơn vị và tăng dung lượng theo hệ số:

- Lúc vẫn còn chỗ: ghi trực tiếp, **`O(1)`**.
- Đúng lúc hết chỗ: cấp phát và chép `n` đơn vị cũ, **`O(n)`** cho lần đó.
- Trên một chuỗi dài `N` lần thêm: tổng `O(N)`, nên trung bình **khấu hao `O(1)` cho mỗi lần thêm**.

Đây là *amortized analysis*, không phải khẳng định thời gian tệ nhất của mỗi lời gọi là `O(1)`. Nó cũng không phải một trung bình xác suất: phép phân tích đảm bảo một giới hạn tổng trên **mọi chuỗi thao tác** thỏa giả định, không cần giả định đầu vào ngẫu nhiên.

Với `append` đoạn dài `m`, cần **`O(m)`** để ghi chính đoạn đó; không thể gọi là `O(1)` nếu `m` không cố định. Nếu lần thêm kích hoạt cấp phát, một lời gọi có thể tốn **`O(n+m)`**, nhưng tổng trên nhiều lần thêm vẫn tuyến tính theo tổng dữ liệu dưới chiến lược tăng dung lượng theo hệ số.

## 5. Chứng minh khấu hao bằng phương pháp tổng

Xét `N` lần thêm đúng một đơn vị, mảng bắt đầu rỗng với `capacity = 1` và nhân đôi khi đầy.

Có hai loại công việc:

**Ghi mới:** mỗi đơn vị đầu vào được ghi một lần, nên đúng `N` lần ghi.

**Chép dữ liệu cũ:** khi tăng dung lượng từ 1 lên 2, chép 1 đơn vị; từ 2 lên 4, chép 2; từ 4 lên 8, chép 4; tiếp tục theo cấp số nhân. Tổng các lần chép dữ liệu cũ nhỏ hơn `2N`.

Vì vậy tổng số đơn vị dữ liệu được ghi/chép nhỏ hơn `3N`, chưa tính chi phí cố định của cấp phát và xử lý từng lời gọi. Do số lần cấp phát tăng theo cấp số nhân là `O(\log N)`, tổng công việc là **`O(N)`** trong mô hình chi phí thông thường.

Ví dụ với tám lần thêm:

| Lần thêm | `length` sau thêm | `capacity` sau thêm | Có mở rộng? | Đơn vị cũ bị chép |
|---:|---:|---:|---|---:|
| 1 | 1 | 1 | Không, vùng ban đầu đủ chỗ | 0 |
| 2 | 2 | 2 | Có | 1 |
| 3 | 3 | 4 | Có | 2 |
| 4 | 4 | 4 | Không | 0 |
| 5 | 5 | 8 | Có | 4 |
| 6 | 6 | 8 | Không | 0 |
| 7 | 7 | 8 | Không | 0 |
| 8 | 8 | 8 | Không | 0 |
| **Tổng** | **8** | | | **7** |

Builder ghi 8 đơn vị mới và chép lại 7 đơn vị cũ, tổng **15 đơn vị** dữ liệu. Với mô hình nối bất biến tạo vùng mới ở mỗi lần, tổng độ dài các kết quả trung gian là **36 đơn vị**.

Chênh lệch còn lớn hơn khi `N` tăng. Tuy nhiên, con số đo lường thực tế còn phụ thuộc cách cấp phát, cache CPU, sao chép bộ nhớ, bộ thu gom rác và tối ưu của runtime.

## 6. Chi phí bộ nhớ: `length` khác `capacity`

Bộ đệm tăng trưởng dành trước vùng nhớ nên không nhất thiết lưu vừa khít nội dung:

| Thuộc tính | Vai trò |
|---|---|
| `length` | Độ dài dữ liệu logic đang sử dụng |
| `capacity` | Sức chứa đã cấp phát |
| `capacity - length` | Số đơn vị chưa sử dụng nhưng được dành sẵn |
| `sizeof(unit)` | Độ rộng một đơn vị vật lý để tính byte chiếm dụng |

Khi nhân đôi dung lượng và thêm từng đơn vị, sau một lần mở rộng có thể có gần một nửa `capacity` còn trống. Đây là chi phí bộ nhớ đổi lấy việc giảm sao chép. Với chính sách nhân đôi và thêm liên tục, sau khi nội dung không rỗng, dung lượng thường nhỏ hơn `2 × length`; nhưng **đây không phải cam kết của mọi thư viện**, nhất là khi builder được `reserve` trước một số lớn hoặc có phép xóa.

### Đỉnh bộ nhớ khi cấp phát lại

Nếu `buffer` cũ có dung lượng `C` và cần cấp phát vùng mới có dung lượng `2C`, có thời điểm cả hai vùng còn tồn tại:

```text
old allocation:  C  đơn vị
new allocation: 2C  đơn vị
-------------------------
peak:           3C  đơn vị (chưa tính metadata/allocator)
```

Điều đó không có nghĩa bộ đệm **luôn** dùng `3C`; chỉ là mô hình đỉnh bộ nhớ của thao tác cấp phát mới rồi chép và giải phóng cũ. Trình quản lý bộ nhớ, growth factor, cơ chế `realloc` và lifetime của bản sao có thể làm con số thực tế khác.

Nếu gọi `build()` và API yêu cầu trả về một **chuỗi bất biến độc lập**, có thể cần thêm một bản sao kích thước `N`. Khi tính ngân sách bộ nhớ cho báo cáo lớn, hãy tính cả **bộ đệm đang xây** và **kết quả cuối**, thay vì chỉ nhìn độ dài kết quả.

### Dung lượng được tính theo đơn vị nào?

Một số builder đếm byte, một số dựa trên UTF-16 code unit, một số lưu ký tự theo cách riêng. Ví dụ Java `StringBuilder.length()` trả số UTF-16 code unit theo API; không thể mặc nhiên coi `reserve(100)` hoặc dung lượng 100 là “100 ký tự hiển thị”. Để kiểm tra giới hạn truyền mạng, cần tính số **byte sau mã hóa**.

## 7. Đánh đổi giữa các chiến lược tăng dung lượng

| Chiến lược | Tổng công việc khi thêm `N` đơn vị từ rỗng | Bộ nhớ dự phòng | Đặc điểm |
|---|---|---|---|
| Tạo chuỗi bất biến mới, sao chép toàn tiền tố mỗi lần | `Θ(N²)` nếu có `N` lần thêm đơn vị | Mỗi kết quả mới có thể vừa đủ; có nhiều kết quả trung gian | Dễ viết nhưng có thể lặp sao chép lớn |
| Tăng `capacity` thêm 1 đơn vị | `Θ(N²)` | Rất ít vùng trống | Cấp phát và sao chép thường xuyên |
| Tăng `capacity` thêm `h` đơn vị cố định | `Θ(N²/h)` với `h` cố định | Tối đa khoảng `h` đơn vị trống giữa các lần mở rộng | Thường không phù hợp cho `N` lớn |
| Tăng theo hệ số lớn hơn 1, ví dụ nhân đôi | `O(N)` | `O(N)` trong trường hợp xấu | Chi phí khấu hao tốt, có khoảng dự phòng |
| Biết trước `N`, cấp phát một lần đủ chứa | `Θ(N)` để ghi dữ liệu | Có thể ít hoặc không có dư nếu ước lượng đúng | Ít cấp phát; cần biết hoặc ước lượng tổng kích thước |
| Gom các mảnh, ghép một lần (`join`) | Thường `O(N+k)` | Mảnh và kết quả có thể cùng tồn tại | Đơn giản nếu các phần được giữ lại trước khi ghép |

Các hàng nói về **mô hình**: khi `N` phần tử được thêm mỗi lần một đơn vị, tính chi phí chép/ghi vùng nhớ; không phải benchmark so sánh mọi phiên bản runtime. Cấp phát trước đúng `N` đơn vị là giải pháp lý tưởng khi biết kích thước đầu ra, nhưng không phải lúc nào cũng biết hoặc đáng để đo trước.

### Chọn hệ số tăng bao nhiêu?

Hệ số 2 dễ phân tích và có tổng sao chép nhỏ. Hệ số gần 1 hơn có thể giảm phần dung lượng thừa nhưng tăng số lần cấp phát, lượng sao chép và quản lý bộ nhớ. Hệ số lớn hơn có thể ít cấp phát hơn nhưng tăng đỉnh bộ nhớ. Các thư viện thực tế có thể dùng nhiều quy tắc hoặc thay đổi chính sách theo kích thước vùng nhớ.

Trong ứng dụng thông thường, **ưu tiên API builder/dynamic buffer chuẩn** và chỉ điều chỉnh dung lượng khi có dữ liệu đo đạc hoặc biết trước kích thước kết quả. Không cần tự viết bộ cấp phát chỉ để chọn một hệ số tăng trưởng.

## 8. Ví dụ triển khai và những bẫy theo ngôn ngữ

### 8.1. Python: gom phần rồi `join`

Python `str` là bất biến. Khi tạo một chuỗi từ nhiều phần có sẵn hoặc được sinh dần:

```python
def render_rows(rows):
    parts = ["MỤC LỤC\n"]
    for index, title in enumerate(rows, 1):
        parts.append(f"{index}. {title}\n")
    return "".join(parts)

print(render_rows(["Mảng", "Danh sách liên kết", "Hàng đợi"]))
```

`parts.append` trên danh sách Python có chi phí khấu hao nhỏ cho việc thêm một tham chiếu, còn `"".join(parts)` ghép các chuỗi thành kết quả trong một bước. Tổng thời gian thường `O(N+k)`, với `N` là tổng độ dài văn bản và `k` số phần tử. Bộ nhớ giữ mảng tham chiếu cùng các đoạn và chuỗi kết quả trong lúc ghép.

Một cách khác là `io.StringIO`, cung cấp giao diện ghi vào bộ đệm văn bản:

```python
from io import StringIO

def build_notice(entries):
    out = StringIO()
    out.write("Thông báo:\n")
    for entry in entries:
        out.write("* ")
        out.write(entry)
        out.write("\n")
    return out.getvalue()

print(build_notice(["Đã lưu", "Đã kiểm tra"]))
```

**Lưu ý:** Trong CPython, phép `s += part` có thể được tối ưu ở một số trường hợp cụ thể; hiệu năng còn tùy phiên bản, aliasing và dạng thao tác. Cần phân biệt **mô hình nối bất biến có sao chép tiền tố** với **hành vi thực tế của một trình thông dịch**. Đối với thuật toán cần chi phí có thể lý giải, `join` hoặc một đối tượng buffer/builder có hợp đồng rõ ràng thường dễ đánh giá hơn.

### 8.2. Java: `StringBuilder`

```java
import java.util.List;

public class Report {
    static String render(List<String> names) {
        StringBuilder out = new StringBuilder(128);
        for (int i = 0; i < names.size(); i++) {
            out.append(i + 1).append(". ");
            out.append(names.get(i)).append('\n');
        }
        return out.toString();
    }

    public static void main(String[] args) {
        System.out.println(render(List.of("Array", "Stack", "Queue")));
    }
}
```

Trong Java, `StringBuilder` hỗ trợ `append`, `capacity()`, `ensureCapacity()` và `toString()`. Có thể cấp dung lượng ban đầu để giảm số lần mở rộng khi biết ước lượng. Một `String` trả về từ `toString()` giữ nội dung đã hoàn thành và không thay đổi nếu builder tiếp tục được sửa.

`StringBuilder` không có bảo đảm an toàn khi chia sẻ và sửa đồng thời mà không tổ chức đồng bộ. `StringBuffer` cung cấp các thao tác đồng bộ ở mức phương thức, nhưng nhiều thao tác ghép lại vẫn cần thiết kế đồng bộ nếu ứng dụng yêu cầu một giao dịch nguyên tử.

### 8.3. C++: `std::string::reserve` và `append`

Trong C++, `std::string` có thể sửa và có quản lý dung lượng:

```cpp
#include <iostream>
#include <string>
#include <vector>

std::string render(const std::vector<std::string>& pieces) {
    std::size_t total = 0;
    for (const auto& part : pieces) {
        total += part.size();  // Mã production phải xử lý overflow nếu cần
    }

    std::string result;
    result.reserve(total);

    for (const auto& part : pieces) {
        result.append(part);
    }
    return result;
}

int main() {
    std::cout << render({"Xin", " ", "chào", "!"}) << '\n';
}
```

`reserve` yêu cầu tối thiểu sức chứa cần dùng; `size()` là độ dài theo các phần tử `char` mà chuỗi lưu. Với văn bản UTF-8 nằm trong `std::string`, đó thường là **số byte**, không phải số code point. Mã chỉ mang tính minh họa, trước khi tính `total` trong hệ thống thực cần đảm bảo không tràn và không vượt `max_size()`.

### 8.4. JavaScript: lưu các mảnh rồi `join`

```javascript
function buildRows(items) {
  const parts = [];
  for (let i = 0; i < items.length; i++) {
    parts.push(String(i + 1), ". ", items[i], "\n");
  }
  return parts.join("");
}

console.log(buildRows(["Array", "Stack", "Queue"]));
```

Engine JavaScript có thể dùng các dạng **concatenated/rope strings** hoặc tối ưu nội bộ phép cộng; chi phí thực tế phụ thuộc engine và thao tác kích hoạt việc làm phẳng chuỗi. `Array.join` là cách rõ ràng để thu thập mảnh rồi ghép. Hệ thống lớn nên đo trên engine, kích thước đầu vào và phiên bản thực tế khi hiệu năng là vấn đề trọng yếu.

## 9. Khi nào nên tránh giữ cả kết quả trong bộ nhớ?

Builder vẫn phải giữ kết quả ở đâu đó. Nếu đầu ra rất lớn và mục tiêu cuối cùng là tệp, kết nối mạng hoặc luồng nén, có thể **ghi từng đoạn trực tiếp tới output stream**.

```text
Nguồn dữ liệu → định dạng từng đoạn → output stream → tệp/mạng

thay vì:

Nguồn dữ liệu → builder rất lớn → chuỗi kết quả → tệp/mạng
```

Streaming có thể giảm bộ nhớ phụ từ `O(N)` xuống cỡ bộ đệm ghi/đọc, nếu đầu ra không cần giữ toàn bộ để xử lý lại. Đổi lại, thiết kế phải xử lý lỗi ghi giữa chừng, thứ tự xuất dữ liệu và chính sách hủy/rollback nếu kết quả phải được công bố nguyên tử.

Ví dụ Python ghi tuần tự, không tạo toàn bộ báo cáo dưới dạng một chuỗi lớn:

```python
def write_report(stream, rows):
    stream.write("DANH SÁCH\n")
    for number, row in enumerate(rows, start=1):
        stream.write(f"{number}. {row}\n")

with open("report.txt", "w", encoding="utf-8") as file:
    write_report(file, ["Mảng", "Stack", "Queue"])
```

Nếu bắt buộc tạo một chuỗi hoàn chỉnh để trả về từ API, builder hoặc `join` vẫn có ý nghĩa. Nếu chỉ cần gửi từng phần tới nơi tiêu thụ, streaming có thể phù hợp hơn.

## 10. Đánh giá hiệu năng đúng cách

Khi benchmark, cần xác định rõ **đang đo gì**:

- **Kích thước:** cùng `N` byte/code unit nhưng số đoạn `k` khác nhau cho các mẫu chi phí khác nhau.
- **Cách xây dựng:** nối từng ký tự, nối theo từng dòng, `join`, builder, hoặc streaming.
- **Bộ nhớ:** phân biệt tổng cấp phát, mức bộ nhớ sống cuối cùng và **đỉnh bộ nhớ** khi mở rộng.
- **Cơ chế runtime:** tối ưu nối, garbage collector, allocator, cơ chế cache và chi phí mã hóa Unicode.
- **Đầu ra:** bảo đảm các phương pháp tạo nội dung giống nhau và kết quả thật sự được sử dụng, tránh để bộ tối ưu bỏ qua công việc.

Ví dụ so sánh phép nối từng đoạn dài 100 byte trên 10.000 đoạn với `join` sẽ cho một kịch bản khác việc nối đúng 2 đoạn. Nếu chương trình chỉ nối một vài chuỗi ngắn, thay đổi cấu trúc có thể không tạo lợi ích đáng kể.

Không suy ra độ phức tạp chỉ từ thời gian của một đầu vào. Để nhận ra xu hướng, đo trên nhiều giá trị `N` và `k`, giữ môi trường ổn định, lặp thí nghiệm hợp lý và kiểm tra chi phí bộ nhớ cùng thời gian.

## 11. Bài tập có lời giải

### Bài 1. Đếm số đơn vị đã sao chép

Nối 100 đoạn, mỗi đoạn dài 10 code unit, bằng cách luôn tạo mới kết quả bất biến rồi sao chép tất cả nội dung. Tổng số code unit được ghi vào các kết quả trung gian là bao nhiêu?

**Lời giải:** `N = 100 × 10 = 1.000` code unit. Tổng công việc:

\[
C = 10 \times \frac{100 \times 101}{2} = 50.500\ \text{code unit}.
\]

Số đơn vị đầu ra chỉ là 1.000; phần lớn công việc là ghi lại các tiền tố.

### Bài 2. Mô phỏng tăng dung lượng

Một builder bắt đầu với `capacity = 1`, `length = 0` và nhân đôi khi đầy. Thêm 9 lần, mỗi lần một đơn vị. Hãy cho biết dung lượng cuối và các lần sao chép.

**Lời giải:** Sức chứa lần lượt đạt `1, 2, 4, 8, 16`. Trước lần thêm thứ 9 phải tăng từ 8 lên 16 nên số đơn vị cũ chép trong các lần mở rộng là `1 + 2 + 4 + 8 = 15`. Dung lượng cuối là **16**, độ dài là **9**; tổng đơn vị dữ liệu ghi mới là **9**.

### Bài 3. Quy tắc tăng nào phù hợp?

Một chương trình mỗi giây tạo hàng nghìn dòng log. Phần lớn dòng được gửi thẳng ra tệp, và bộ nhớ bị giới hạn. Có cần tích lũy tất cả dòng trong một builder rồi xuất một lần không?

**Lời giải:** Không nhất thiết. Nếu không cần toàn bộ báo cáo trong RAM, dùng **buffered streaming** để giữ bộ nhớ phụ nhỏ; cần lựa chọn cơ chế flush và xử lý lỗi khi ghi. Nếu chương trình cần toàn bộ nội dung để tính chữ ký hoặc trả về qua API, builder hoặc cấu trúc lưu đoạn có thể phù hợp hơn.

### Bài 4. Phân biệt chi phí một lần và khấu hao

Một lời gọi `append` kéo dài 1 ms ở nhiều lần nhưng có một lần mất 40 ms vì cấp phát lại. Có mâu thuẫn với phát biểu “`append` là `O(1)` khấu hao” không?

**Lời giải:** Không. “`O(1)` khấu hao” là chặn cho **tổng chi phí qua nhiều thao tác**, không phải giới hạn thời gian tệ nhất của từng lần. Việc cấp phát lại có thể tốn `O(n)` trong một lần mà tổng trên `N` lần vẫn là `O(N)`.

### Bài 5. Chuỗi Unicode và dung lượng builder

Một builder lưu UTF-8 và cần thêm 1.000 emoji `🙂`. Cần ít nhất bao nhiêu byte dữ liệu đầu ra, chưa tính metadata?

**Lời giải:** Mỗi `🙂` cần 4 byte UTF-8 nên dữ liệu dài **4.000 byte**. Nếu giới hạn tính theo grapheme cluster thì số cụm thường là 1.000; con số này không quyết định đủ dung lượng byte của bộ đệm.

## 12. Checklist thiết kế trước khi triển khai

1. **Xác định đầu ra:** có cần chuỗi hoàn chỉnh hay có thể streaming?
2. **Ước lượng `N` và `k`:** nhiều lần nối nhỏ là dấu hiệu cần builder, `join` hoặc thu gom mảnh.
3. **Chọn đơn vị:** `length`/`capacity` tính theo byte, code unit hay phần tử khác?
4. **Xác nhận quy tắc tăng trưởng:** tăng theo hệ số hoặc dùng API thư viện có đảm bảo phù hợp; cân nhắc `reserve` khi biết kích thước.
5. **Tính bộ nhớ đỉnh:** kể cả vùng cũ khi cấp phát lại và chuỗi kết quả sau `build`.
6. **Giữ bất biến:** `0 ≤ length ≤ capacity`; cập nhật độ dài đúng; không cắt mã Unicode giữa chừng; xử lý lỗi cấp phát.
7. **Đo khi cần:** kiểm tra thời gian, cấp phát, đỉnh RAM và sự thay đổi theo số đoạn, không dựa trên một benchmark nhỏ.

## Ghi nhớ

- Nối liên tục vào chuỗi bất biến **có thể** tốn `Θ(N²)` khi mỗi lần nối tạo bản mới và sao chép toàn tiền tố, với số đoạn tỷ lệ cùng độ dài đầu ra.
- Bộ đệm tăng trưởng giữ `length` và `capacity`, tận dụng vùng dự phòng để tránh sao chép ở hầu hết các lần `append`.
- **Tăng `capacity` theo hệ số** cho phép tổng sao chép dữ liệu cũ `O(N)`, do đó append một đơn vị là **`O(1)` khấu hao**, dù một lần mở rộng riêng lẻ có thể tốn `O(n)`.
- Đổi lại tốc độ, builder cần bộ nhớ dự phòng và có thể tạo đỉnh sử dụng bộ nhớ cao lúc cấp phát lại hoặc hoàn tất chuỗi.
- Với dữ liệu đã chia mảnh, `join` thường là cách ghép đơn giản; khi biết kích thước, cân nhắc `reserve`; khi chỉ cần ghi ra tệp/mạng, **streaming** có thể tiết kiệm bộ nhớ hơn giữ toàn bộ kết quả.
