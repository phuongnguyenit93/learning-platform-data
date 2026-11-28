# Mảng như ánh xạ từ chỉ số sang phần tử

## 1. Mục tiêu của bài học

Mảng (array) thường được giới thiệu như một dãy phần tử đặt cạnh nhau. Cách nhìn đó hữu ích khi tìm hiểu bộ nhớ, nhưng để hiểu bản chất cấu trúc dữ liệu, hãy bắt đầu từ một ý tưởng trừu tượng hơn: **mảng là một ánh xạ từ chỉ số hợp lệ đến phần tử tương ứng**.

Sau bài học, bạn có thể:

- Mô tả mảng bằng miền chỉ số, tập giá trị và phép truy cập `A[i]`.
- Phân biệt **chỉ số** (vị trí) với **giá trị** được lưu tại vị trí ấy.
- Giải thích vì sao truy cập theo chỉ số thường có thời gian `O(1)` và khi nào việc thêm, xóa phần tử tốn `O(n)`.
- Nhận ra bất biến về phạm vi chỉ số và tránh lỗi lệch một đơn vị (*off-by-one*).
- Chọn mảng cho các bài toán cần truy cập vị trí nhanh, đồng thời biết giới hạn của nó so với danh sách liên kết và bảng băm.

Đây là nền tảng để học các cấu trúc khác trong học phần cấu trúc dữ liệu: danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Mỗi cấu trúc có cách tổ chức phần tử và đánh đổi riêng về thời gian, bộ nhớ.

## 2. Mô hình toán học: từ chỉ số đến phần tử

Cho một mảng `A` có `n` phần tử, đánh chỉ số từ `0`. Ta có thể xem mảng là hàm:

\[
A: I_n \rightarrow T, \qquad I_n = \{0,1,\ldots,n-1\}
\]

Trong đó:

- `I_n` là **miền chỉ số hợp lệ**; mỗi chỉ số đại diện cho đúng một vị trí của mảng.
- `T` là tập kiểu giá trị mà mảng có thể lưu, chẳng hạn các số nguyên.
- `A(i)` hoặc cách viết quen thuộc `A[i]` là **giá trị tại chỉ số `i`**.
- `n` là **độ dài** (*length*), tức số vị trí đang thuộc mảng.

Ví dụ, mảng lưu số sách được mượn trong bốn ngày liên tiếp:

```text
A = [12,  8, 15,  8]
     ──  ──  ──  ──   giá trị
      0   1   2   3   chỉ số
```

| Chỉ số `i` | `A[i]` | Ý nghĩa |
|---:|---:|---|
| `0` | `12` | Số sách của ngày thứ nhất |
| `1` | `8` | Số sách của ngày thứ hai |
| `2` | `15` | Số sách của ngày thứ ba |
| `3` | `8` | Số sách của ngày thứ tư |

Ta có ánh xạ `0 → 12`, `1 → 8`, `2 → 15`, `3 → 8`. Hai chỉ số khác nhau **được phép ánh xạ đến cùng một giá trị**: `A[1]` và `A[3]` đều bằng `8`. Nhưng với một trạng thái mảng nhất định, **một chỉ số hợp lệ chỉ có một giá trị tại thời điểm truy cập**.

Đừng nhầm lẫn `A[2]` với “phần tử có giá trị `2`”: biểu thức `A[2]` yêu cầu đọc **vị trí số 2** (phần tử thứ ba trong quy ước bắt đầu từ 0), nên ở ví dụ trên kết quả là `15`.

### Phạm vi chỉ số là một bất biến

Với quy ước chỉ số bắt đầu từ 0, điều kiện truy cập hợp lệ là:

\[
0 \le i < n
\]

Nếu `n = 4`, chỉ số hợp lệ là `0`, `1`, `2`, `3`; `A[4]` nằm ngoài mảng. Nếu `n = 0`, miền chỉ số rỗng: không có bất kỳ `A[i]` hợp lệ nào. **Độ dài** và **chỉ số lớn nhất** là hai đại lượng khác nhau: với mảng không rỗng, chỉ số lớn nhất bằng `n - 1`.

Một số ngôn ngữ hoặc giao diện mô tả phần tử “thứ nhất, thứ hai, ...” theo cách đếm từ 1. Khi chuyển sang mảng đánh chỉ số từ 0, phần tử thứ `k` tương ứng với `A[k - 1]`. Trong Python, chỉ số âm còn có ý nghĩa đặc biệt (`A[-1]` là phần tử cuối); đây là **quy tắc bổ sung của ngôn ngữ**, không thuộc miền `I_n` trong mô hình đang xét.

## 3. Vì sao phép truy cập `A[i]` nhanh?

Mô hình ánh xạ giải thích **ta muốn lấy phần tử nào**; cách lưu trong bộ nhớ giải thích **máy tính tìm phần tử ấy bằng cách nào**.

Với mảng truyền thống lưu các phần tử có kích thước cố định `s` byte trong một vùng nhớ liên tiếp, địa chỉ phần tử được tính trực tiếp:

\[
\operatorname{address}(A[i]) = \operatorname{base}(A) + i \times s
\]

Ở đây `base(A)` là địa chỉ của phần tử đầu tiên. Ví dụ, nếu `base(A) = 1000`, mỗi phần tử chiếm `4` byte thì phần tử tại chỉ số `3` bắt đầu ở địa chỉ `1000 + 3 × 4 = 1012`. Máy tính tính vị trí từ `i` mà không phải lần lượt đi qua `A[0]`, `A[1]`, `A[2]`.

Đó là cơ sở cho **truy cập ngẫu nhiên** (*random access*) với độ phức tạp thời gian `O(1)` theo mô hình RAM: số bước xác định vị trí không tăng theo số phần tử `n`. Thao tác gán `A[i] = x` cũng thường là `O(1)` khi `i` hợp lệ. Ký hiệu `O(1)` diễn tả tốc độ tăng theo kích thước dữ liệu, **không** có nghĩa mọi lần truy cập đều mất cùng số nano giây; bộ nhớ đệm, kiểm tra giới hạn và phần cứng vẫn ảnh hưởng thời gian thực tế.

> **Phân biệt hai mức trừu tượng:** Tính chất cốt lõi của mảng ở bài này là ánh xạ theo chỉ số. Công thức địa chỉ trực tiếp áp dụng cho cách biểu diễn mảng liên tiếp với kích thước ô lưu trữ cố định. Ví dụ, `list` của Python là một dạng mảng động lưu tham chiếu đến đối tượng; bản thân các đối tượng không nhất thiết nằm liền nhau. Vì vậy, không nên mặc định mọi kiểu dữ liệu hỗ trợ cú pháp `A[i]` đều lưu toàn bộ giá trị liên tiếp.

## 4. Đọc, ghi và duyệt mảng bằng một ví dụ

Giả sử một trạm đo lưu nhiệt độ cao nhất trong bảy ngày liên tiếp. Chỉ số `0` đại diện cho ngày đầu, chỉ số `6` đại diện cho ngày cuối:

```python
temperatures = [28, 29, 27, 30, 31, 29, 28]

# Đọc phần tử ở chỉ số 3 (ngày thứ tư).
print(temperatures[3])  # 30

# Cập nhật nhiệt độ của ngày thứ ba.
temperatures[2] = 26

# Duyệt mọi chỉ số hợp lệ.
for i in range(len(temperatures)):
    print(f"Ngày {i + 1}: {temperatures[i]}°C")
```

Sau câu lệnh gán, ánh xạ tại chỉ số `2` đổi từ `2 → 27` sang `2 → 26`; các chỉ số khác và độ dài mảng không đổi. Vòng lặp chạy từ `0` tới `len(temperatures) - 1`, nhờ đó bao phủ toàn bộ các vị trí đúng một lần.

Khi đầu vào do người dùng nhập được đánh số ngày từ `1`, ta cần đổi sang chỉ số từ `0` và kiểm tra giới hạn:

```python
def temperature_on_day(values: list[int], day_number: int) -> int:
    """Trả về nhiệt độ ngày thứ 1, 2, ... theo cách đếm của người dùng."""
    if not 1 <= day_number <= len(values):
        raise ValueError("Số thứ tự ngày nằm ngoài dữ liệu đã ghi")
    return values[day_number - 1]

print(temperature_on_day(temperatures, 1))  # 28
print(temperature_on_day(temperatures, 4))  # 30
```

Kiểm tra trên cũng ngăn `day_number = 0` vô tình được hiểu là phần tử cuối vì quy tắc chỉ số âm của Python. Trong ví dụ, `list` được dùng để minh họa thao tác theo chỉ số; nó là **mảng động**, có khả năng thêm hoặc xóa phần tử.

## 5. Ánh xạ thay đổi ra sao khi chèn hoặc xóa?

Hãy phân biệt hai hành động:

1. **Cập nhật một vị trí:** `A[1] = 99` giữ nguyên tập chỉ số; chỉ thay giá trị gắn với chỉ số `1`.
2. **Chèn một phần tử tại vị trí:** phải tạo thêm vị trí, đồng thời chuyển chỉ số của các phần tử phía sau.

```text
Ban đầu:          [10, 20, 30, 40]
Chỉ số:             0   1   2   3

Chèn 99 tại i = 1:
                  [10, 99, 20, 30, 40]
Chỉ số mới:         0   1   2   3   4

Xóa phần tử i = 2:
                  [10, 99, 30, 40]
Chỉ số mới:         0   1   2   3
```

Trong bước chèn, giá trị `20` chuyển từ chỉ số `1` sang `2`; `30` từ `2` sang `3`. Trong bước xóa, phần tử phía sau vị trí bị xóa được dịch trái. Vì thế, **chỉ số biểu diễn vị trí tại một thời điểm, không phải mã định danh ổn định của phần tử**. Nếu ứng dụng cần giữ định danh của đối tượng dù thứ tự thay đổi, hãy lưu định danh riêng hoặc cân nhắc một cấu trúc ánh xạ theo khóa.

### Chi phí các thao tác thường gặp

Giả sử mảng có `n` phần tử và dùng cách biểu diễn mảng liên tiếp thông thường:

| Thao tác | Thời gian điển hình | Lý do |
|---|---|---|
| Đọc `A[i]` | `O(1)` | Tính trực tiếp vị trí từ chỉ số |
| Gán `A[i] = x` | `O(1)` | Ghi vào một vị trí đã biết |
| Duyệt toàn bộ | `O(n)` | Cần thăm `n` phần tử |
| Tìm một giá trị trong mảng chưa sắp xếp | `O(n)` | Trường hợp xấu nhất phải kiểm tra toàn bộ |
| Chèn/xóa tại đầu hoặc giữa | `O(n)` | Phải dịch chuyển các phần tử liên quan |
| Chèn/xóa tại cuối mảng động | `O(1)` thường gặp cho xóa cuối; thêm cuối `O(1)` khấu hao | Không cần dịch dãy, nhưng đôi lúc phải cấp phát lại |

**Khấu hao** (*amortized*) ở thao tác thêm cuối nghĩa là: phần lớn lần thêm mất `O(1)`, đôi lúc cần tạo vùng chứa lớn hơn và sao chép `O(n)` phần tử. Nếu dung lượng được tăng theo cấp số nhân, tổng chi phí của nhiều lần thêm vẫn cho trung bình `O(1)` mỗi lần. Còn với **mảng kích thước cố định**, không thể mở rộng trực tiếp: cần tạo mảng mới đủ lớn để chứa phần tử thêm vào.

Không nên đánh đồng **độ dài** (*length*, số phần tử đang dùng) với **sức chứa** (*capacity*, số ô đã dành sẵn) của mảng động. Chẳng hạn, độ dài là `5` nhưng sức chứa có thể là `8`; ba ô dự phòng chưa phải ba phần tử có chỉ số truy cập hợp lệ. Bộ nhớ để chứa `n` phần tử thường tăng theo `O(n)`; mảng động có thể dùng thêm phần dung lượng dự phòng để đổi lấy tốc độ thêm cuối.

## 6. Mảng có phải bảng băm dùng khóa số?

Mảng và bảng băm đều cho phép liên hệ một “đầu vào” với một giá trị, nhưng **miền đầu vào và cách truy cập khác nhau**:

| Tiêu chí | Mảng | Bảng băm (*hash table*) |
|---|---|---|
| Đầu vào để truy cập | Chỉ số nguyên thuộc khoảng hợp lệ, thường `0..n-1` | Khóa bất kỳ thuộc kiểu được hỗ trợ, ví dụ `"SV042"` |
| Ý nghĩa vị trí | Gắn với thứ tự, có thể dịch khi chèn/xóa | Gắn với khóa; không đòi hỏi các khóa liên tiếp |
| Truy cập | `O(1)` theo chỉ số | Trung bình thường `O(1)` theo khóa khi băm tốt |
| Phù hợp khi | Dữ liệu có vị trí liên tiếp, cần duyệt theo thứ tự | Cần tra cứu bằng mã/khóa không liên tiếp |

Ví dụ, lưu điểm của `100` học sinh theo **số thứ tự từ 0 đến 99** là một cách dùng mảng hợp lý: `scores[i]` trả về điểm của vị trí `i`. Nếu mã học sinh là các chuỗi như `"SV042"` và `"SV190"`, tạo mảng với chỉ số theo phần số của mã có thể sinh nhiều vị trí không sử dụng; bảng băm `scores_by_id["SV042"]` thường tự nhiên hơn.

Danh sách liên kết lại có đánh đổi khác: các nút nối bằng tham chiếu, nên truy cập phần tử thứ `i` thường tốn `O(n)` do phải đi qua các nút trước đó; đổi lại, khi **đã có vị trí nút thích hợp**, chèn/xóa cục bộ có thể mất `O(1)` (với đủ tham chiếu). Mảng phù hợp hơn khi truy cập theo chỉ số xảy ra thường xuyên.

## 7. Từ mảng một chiều đến nhiều chiều

Một bảng dữ liệu cũng có thể được mô tả như ánh xạ, nhưng từ **cặp chỉ số** `(hàng, cột)` đến giá trị:

\[
M: \{0,\ldots,r-1\} \times \{0,\ldots,c-1\} \rightarrow T
\]

Ví dụ một bảng `2 × 3`:

```text
             cột 0  cột 1  cột 2
hàng 0          5      7      9
hàng 1          2      4      6
```

Ta có `M[1][2] = 6`: chỉ số thứ nhất chọn hàng `1`, chỉ số thứ hai chọn cột `2` (theo quy ước bắt đầu từ 0). Nếu lưu dữ liệu dưới dạng một mảng một chiều theo thứ tự từng hàng (*row-major*), phần tử `(i, j)` nằm tại chỉ số:

\[
\operatorname{index}(i,j) = i \times c + j
\]

Với `c = 3`, phần tử `(1, 2)` nằm tại `1 × 3 + 2 = 5` của mảng phẳng `[5, 7, 9, 2, 4, 6]`. Công thức chỉ đúng khi bố trí theo thứ tự từng hàng và các hàng có cùng số cột; kiểu danh sách lồng nhau có thể lưu các hàng ở những vùng nhớ riêng biệt.

Ý tưởng này được dùng trong xử lý ảnh (tọa độ hàng, cột của điểm ảnh), ma trận, bản đồ ô vuông và lưu trạng thái cho các thuật toán trên đồ thị.

## 8. Các lỗi tư duy và lập trình thường gặp

1. **Truy cập `A[n]` vì nhầm độ dài với chỉ số cuối.** Với mảng độ dài `n`, phần tử cuối là `A[n - 1]` nếu `n > 0`.
2. **Trộn số thứ tự từ 1 với chỉ số từ 0.** “Ngày thứ tư” tương ứng `A[3]`, không phải `A[4]`.
3. **Nhầm chỉ số với giá trị.** `A[2]` là phần tử ở vị trí `2`, không có nghĩa tìm giá trị `2` trong mảng.
4. **Giữ một chỉ số rồi chèn/xóa trước nó.** Phần tử ban đầu có thể chuyển sang chỉ số mới; chỉ số cũ sẽ chỉ phần tử khác.
5. **Coi mọi số nguyên là chỉ số có thể dùng.** Chỉ số phải thuộc miền hợp lệ; nhiều ứng dụng dùng mã số thưa hoặc rất lớn nên thích hợp với bảng băm hơn.
6. **Cho rằng mọi cú pháp `A[i]` đều tương ứng với một phép đọc bộ nhớ liên tiếp.** Tổ chức vật lý phụ thuộc cấu trúc cụ thể và ngôn ngữ; độ phức tạp phải xét theo cách triển khai.

Một cách phòng lỗi là luôn xác định ba điều trước khi viết thuật toán: `n` hiện là bao nhiêu, chỉ số nào được phép, và thao tác có làm thay đổi vị trí các phần tử hay không.

## 9. Tự kiểm tra

Xét mảng `B = [4, 9, 4, 7]` đánh chỉ số từ `0`:

1. `B[2]` bằng bao nhiêu? Độ dài mảng là bao nhiêu và chỉ số cuối là gì?
2. Vì sao không thể suy ra phần tử ở chỉ số `3` chỉ từ giá trị `B[0]` nếu chưa có thông tin về các phần tử khác?
3. Chèn `5` tại chỉ số `1` thì giá trị `9` chuyển tới chỉ số nào? Chi phí chèn trong mảng liên tiếp là bao nhiêu theo `n`?
4. Với bảng `3 × 4` lưu theo thứ tự từng hàng, ô `(2, 1)` tương ứng chỉ số bao nhiêu trong mảng phẳng?

**Đáp án gợi ý:** (1) `B[2] = 4`, `n = 4`, chỉ số cuối là `3`. (2) Ánh xạ từ chỉ số đến phần tử không có quy luật suy diễn giá trị từ các vị trí khác; phải truy cập dữ liệu ở chỉ số `3`. (3) Giá trị `9` chuyển từ chỉ số `1` sang `2`; chèn giữa có chi phí `O(n)` trong trường hợp xấu nhất. (4) `2 × 4 + 1 = 9`.

## 10. Ghi nhớ

**Mảng là ánh xạ có miền chỉ số xác định:** mỗi chỉ số hợp lệ truy cập một vị trí và một giá trị tại vị trí ấy. Từ góc nhìn này, ta hiểu được tính có thứ tự, phép đọc/ghi theo chỉ số, lỗi vượt giới hạn và lý do chỉ số thay đổi sau khi chèn hoặc xóa. Với cách biểu diễn mảng liên tiếp thông dụng, công thức địa chỉ giúp truy cập `O(1)`, trong khi việc dịch phần tử khiến thao tác chèn/xóa ở giữa thường là `O(n)`. Nắm chắc các bất biến này là bước đầu để so sánh mảng với những cấu trúc dữ liệu khác theo yêu cầu thực tế về thời gian và bộ nhớ.
