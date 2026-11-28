# Thăm dò tuyến tính và hiện tượng kết cụm

## 1. Từ va chạm đến dãy ô liên tiếp

Trong **bảng băm (hash table)**, mỗi khóa xác định nơi bắt đầu tra cứu một cặp khóa–giá trị. Khi dùng **địa chỉ mở (open addressing)**, các bản ghi được đặt trực tiếp trong mảng của bảng: mỗi ô đang hoạt động chứa tối đa một cặp. Nếu vị trí dự kiến đã có một khóa khác, bảng phải thử ô tiếp theo.

**Thăm dò tuyến tính (linear probing)** là một cách giải quyết va chạm đơn giản: bắt đầu tại chỉ số băm rồi lần lượt kiểm tra từng ô kề nhau, quay về ô đầu tiên khi tới cuối mảng. Cách này dễ cài đặt và tận dụng tốt bộ nhớ liên tục, nhưng có nhược điểm quan trọng là **hiện tượng kết cụm sơ cấp (primary clustering)**: nhiều bản ghi tập trung thành những đoạn ô liên tiếp, khiến việc tìm kiếm và thêm mới ngày càng phải đi qua đoạn dài.

Ví dụ ứng dụng: bảng lưu số lần xuất hiện của các mã sản phẩm. Nếu nhiều mã rơi vào cùng vùng ô, một lần cập nhật cho mã có thể phải kiểm tra hàng loạt ô trước khi tìm thấy đúng bản ghi. Muốn đánh giá cấu trúc dữ liệu này, ta cần hiểu cả **quy tắc thăm dò**, **bất biến tra cứu** và **chi phí khi cụm dài lên**.

## 2. Công thức thăm dò tuyến tính và điều kiện dừng

Giả sử bảng có `m > 0` ô, đánh số từ `0` đến `m - 1`. Ký hiệu `h(k)` là chỉ số ban đầu dành cho khóa `k`, đã được đưa về phạm vi hợp lệ. Lần thăm dò thứ `j`, với `j = 0, 1, ..., m - 1`, kiểm tra:

\[
p(k,j) = (h(k) + j) \bmod m.
\]

Ví dụ `m = 11`, `h(k) = k mod 11` với khóa nguyên không âm:

```text
Khóa k = 37
h(37) = 37 mod 11 = 4

j:        0   1   2   3   4   5   6   7   8   9  10
p(37,j):  4   5   6   7   8   9  10   0   1   2   3
```

Do cộng từng bước `1` và lấy phần dư `m`, dãy này đi qua **đủ `m` ô khác nhau** trước khi lặp. Đây là đặc điểm của linear probing bất kể `m` có phải số nguyên tố hay không. Trong cài đặt cần giới hạn tối đa `m` lần thử để không lặp vô hạn khi bảng đầy hoặc chỉ còn các dấu đã xóa.

Khi thăm dò:

- Gặp ô đang chứa **đúng khóa**: trả giá trị hoặc cập nhật ngay tại ô đó.
- Gặp ô chứa **khóa khác**: tiếp tục theo dãy, dù mã băm hoặc chỉ số ban đầu có trùng nhau.
- Gặp ô **chưa từng dùng (EMPTY)**: có thể kết luận khóa không có khi tra cứu; khi thêm mới có thể dùng ô này, sau khi bảo đảm chưa gặp khóa trùng.
- Gặp ô **đã xóa (DELETED/tombstone)**: tiếp tục tìm kiếm; khi thêm mới có thể ghi nhớ ô đó để tái sử dụng sau khi kiểm tra các ô phía sau.

Các quy tắc dừng trên phụ thuộc việc thêm, tìm và xóa đều tuân thủ **cùng công thức thăm dò**.

## 3. Truy vết từng lần chèn: một cụm hình thành

Xét bảng có `m = 11`, ban đầu trống. Thêm lần lượt các khóa `15, 26, 37, 6, 7` với `h(k) = k mod 11`.

| Lần chèn | Khóa | Chỉ số bắt đầu | Các ô phải thử | Ô lưu cuối cùng |
| ---: | ---: | ---: | --- | ---: |
| 1 | 15 | 4 | `4` | 4 |
| 2 | 26 | 4 | `4 → 5` | 5 |
| 3 | 37 | 4 | `4 → 5 → 6` | 6 |
| 4 | 6 | 6 | `6 → 7` | 7 |
| 5 | 7 | 7 | `7 → 8` | 8 |

Sau năm lần chèn, mảng có trạng thái:

```text
Chỉ số:   0    1    2    3    4    5    6    7    8    9   10
         [ ]  [ ]  [ ]  [ ] [15] [26] [37]  [6]  [7]  [ ]  [ ]
                             └──────── cụm 4..8 ────────┘
```

Điều đáng chú ý: **không phải mọi khóa trong cụm đều có cùng chỉ số ban đầu**. Các khóa `15`, `26`, `37` bắt đầu tại 4; khóa `6` bắt đầu tại 6 và khóa `7` bắt đầu tại 7. Dù xuất phát từ các vị trí khác nhau, chúng vẫn nhập vào cùng một đoạn liên tiếp.

Thử thêm `18` (`18 mod 11 = 7`): vì các ô 7 và 8 đã có dữ liệu, bảng thử `7 → 8 → 9` và đặt `18` ở ô 9. Cụm tăng từ năm lên **sáu ô liên tiếp**. Nếu tìm một khóa vắng mặt cũng bắt đầu tại 7, thao tác phải duyệt qua cụm cho đến ô trống đầu tiên.

Đoạn cụm có thể **quấn vòng** qua cuối mảng: các ô `9, 10, 0, 1` đều đã dùng cũng tạo thành một cụm liên tiếp theo thứ tự thăm dò, dù khi in mảng chúng nằm ở hai đầu.

## 4. Vì sao kết cụm sơ cấp tự làm vấn đề nặng hơn?

**Kết cụm sơ cấp** không đơn thuần là nhiều khóa có mã băm giống nhau. Nó là sự hình thành các **đoạn ô liên tiếp đã bị chiếm**. Khi một khóa mới có vị trí ban đầu nằm ở bất kỳ đâu trong đoạn đó, quá trình thăm dò sẽ đi tới cuối đoạn và chèn vào ô trống kế tiếp:

```text
Trước:   ... [A] [B] [C] [D] [ ] ...
                      ↑
               khóa mới bắt đầu tại đây

Thử:            [C] → [D] → [ ]
Sau:     ... [A] [B] [C] [D] [X] ...
```

Một cụm dài có nhiều chỉ số ban đầu nằm trong nó hơn, do đó có thêm cơ hội nhận các khóa mới và tiếp tục lớn lên. Hai cụm vốn tách biệt còn có thể **nhập lại thành một cụm dài** khi một lần chèn lấp ô trống giữa chúng.

Ví dụ, hai đoạn đã chiếm là `[2,3]` và `[5,6]`. Nếu một khóa bắt đầu thăm dò tại ô 3 và được đặt vào ô 4 đang trống, đoạn `[2,3,4,5,6]` trở thành một cụm lớn. Khóa ấy không cần có cùng giá trị băm với bất kỳ khóa nào ở đoạn thứ hai.

Hệ quả đối với thao tác:

1. **Thêm mới:** khóa có chỉ số ban đầu nằm trong cụm phải đi tới ô trống phía sau cụm.
2. **Tìm thành công:** khóa được đẩy xa khỏi vị trí ban đầu cần nhiều phép kiểm tra hơn trước khi tìm thấy.
3. **Tìm không thành công:** một khóa bắt đầu bên trong cụm có thể phải kiểm tra hết phần còn lại của cụm mới gặp `EMPTY`.
4. **Xóa:** nếu chỉ thay bản ghi bằng dấu `DELETED`, các ô đã xóa vẫn không cho phép tra cứu dừng lại; quá nhiều tombstone tiếp tục làm đường tìm kiếm dài.

Vì vậy, **phân bố tốt các chỉ số ban đầu** là cần thiết nhưng chưa loại bỏ hoàn toàn kết cụm do chính quy tắc thăm dò tuyến tính tạo ra.

## 5. Ví dụ chi tiết về tìm kiếm và cập nhật

Dùng lại bảng sau khi thêm `15, 26, 37, 6, 7`:

```text
Ô:      0   1   2   3    4    5    6    7   8   9  10
Giá trị  -   -   -   -   15   26   37    6   7   -   -
```

**Tìm khóa 37:** `h(37) = 4`, thử ô 4 (khóa 15), ô 5 (khóa 26), ô 6 (đúng khóa 37). Cần **3 lần kiểm tra ô**.

**Tìm khóa 18 khi chưa chèn 18:** `h(18) = 7`, thử ô 7 (khóa 6), ô 8 (khóa 7), ô 9 (`EMPTY`). Vì ô 9 chưa từng dùng, kết luận không có 18 sau **3 lần kiểm tra**.

**Cập nhật khóa 26:** cũng bắt đầu tại 4, kiểm tra ô 4 rồi ô 5 và thay giá trị tại ô 5. Không chèn thêm bản ghi vào cuối cụm; một map chỉ có **một bản ghi đang hoạt động cho mỗi khóa logic**.

Trong mỗi ví dụ, cần so sánh **khóa đang lưu** với khóa cần tìm. Chỉ số ngăn, mã băm hoặc việc nằm cùng cụm đều không đủ để xác định hai khóa bằng nhau.

## 6. Xóa mà vẫn giữ đúng đường thăm dò

Sau khi chèn `15, 26, 37, 6, 7`, khóa `37` đang ở ô 6 nhưng đường tìm của nó bắt đầu từ ô 4 và đi qua ô 5.

Nếu xóa `26` ở ô 5 bằng cách chuyển ô này thẳng thành `EMPTY`, tìm `37` sẽ dừng tại ô 5 và **trả sai kết quả không tìm thấy**. Hai giải pháp được dùng phổ biến:

- **Đánh dấu đã xóa (tombstone):** ô 5 trở thành `DELETED`. Tìm `37` tiếp tục qua ô 5 để đến ô 6. Khi chèn mới, có thể tái sử dụng ô 5 sau khi đã kiểm tra không có khóa trùng ở phía sau.
- **Dịch lùi có kiểm soát (backward-shift deletion):** với một số thiết kế linear probing, có thể dịch các bản ghi thích hợp về các ô trống để giữ đường tìm đúng mà không cần tombstone. Việc dịch phải xét vị trí ban đầu của từng khóa và xử lý cả trường hợp quấn vòng.

Ví dụ dùng tombstone:

```text
Trước xóa 26:
  ô 4        ô 5       ô 6       ô 7       ô 8
 [15]  -->  [26] -->  [37] -->   [6] -->   [7]

Sau xóa 26:
 [15]  -->  [DEL] -->  [37] -->   [6] -->   [7]

Tìm 37: ô 4 (khác) → ô 5 (DEL, tiếp tục) → ô 6 (đúng)
```

Một lỗi tinh vi khác là **chèn ngay vào tombstone đầu tiên mà không tìm tiếp**. Ví dụ đang có khóa `37` ở ô 6, ô 5 bị đánh dấu xóa, và chương trình gọi `put(37, giá_trị_mới)`. Nếu đặt một bản ghi 37 mới vào ô 5 ngay lập tức, bảng có hai bản ghi cùng khóa; cài đặt đúng phải tìm thấy bản ghi 37 ở ô 6 để cập nhật nó.

## 7. Cài đặt Python: mô phỏng cụm và tombstone

Ví dụ này dùng khóa nguyên và `h(k)=k\bmod m` để nhìn rõ phép thăm dò. Mảng có dung lượng cố định; `EMPTY` và `DELETED` là hai đối tượng đánh dấu khác nhau. Mỗi ô có dữ liệu chứa một tuple `(khóa, giá trị)`; giá trị của bản ghi được phép là `None` mà không gây nhầm với ô trống.

```python
class BangBamTuyenTinh:
    EMPTY = object()
    DELETED = object()

    def __init__(self, so_o=11):
        if so_o <= 0:
            raise ValueError("Số ô phải dương")
        self.o = [self.EMPTY] * so_o
        self.so_khoa = 0

    def _duong_thu(self, khoa: int):
        m = len(self.o)
        bat_dau = khoa % m
        for j in range(m):              # Tránh lặp vô hạn khi bảng đầy
            yield (bat_dau + j) % m

    def gan(self, khoa: int, gia_tri):
        o_da_xoa_dau = None
        for i in self._duong_thu(khoa):
            muc = self.o[i]
            if muc is self.EMPTY:
                dich = o_da_xoa_dau if o_da_xoa_dau is not None else i
                self.o[dich] = (khoa, gia_tri)
                self.so_khoa += 1
                return
            if muc is self.DELETED:
                if o_da_xoa_dau is None:
                    o_da_xoa_dau = i
                continue
            if muc[0] == khoa:
                self.o[i] = (khoa, gia_tri)  # Cập nhật khóa cũ
                return

        if o_da_xoa_dau is not None:
            self.o[o_da_xoa_dau] = (khoa, gia_tri)
            self.so_khoa += 1
            return
        raise OverflowError("Không còn ô trống; cần mở rộng")

    def lay(self, khoa: int):
        for i in self._duong_thu(khoa):
            muc = self.o[i]
            if muc is self.EMPTY:
                break
            if muc is self.DELETED:
                continue
            if muc[0] == khoa:
                return muc[1]
        raise KeyError(khoa)

    def xoa(self, khoa: int):
        for i in self._duong_thu(khoa):
            muc = self.o[i]
            if muc is self.EMPTY:
                break
            if muc is self.DELETED:
                continue
            if muc[0] == khoa:
                self.o[i] = self.DELETED
                self.so_khoa -= 1
                return muc[1]
        raise KeyError(khoa)

    def vet_tim(self, khoa: int):
        """Những ô được kiểm tra khi tìm một khóa."""
        da_thu = []
        for i in self._duong_thu(khoa):
            da_thu.append(i)
            muc = self.o[i]
            if muc is self.EMPTY:
                break
            if muc is not self.DELETED and muc[0] == khoa:
                break
        return da_thu

    def xem(self):
        return [
            "EMPTY" if muc is self.EMPTY else
            "DELETED" if muc is self.DELETED else
            f"{muc[0]}:{muc[1]}"
            for muc in self.o
        ]


bang = BangBamTuyenTinh(11)
for k, v in [(15, "A"), (26, "B"), (37, "C"), (6, "D"), (7, "E")]:
    bang.gan(k, v)

print(bang.xem())
# ['EMPTY', 'EMPTY', 'EMPTY', 'EMPTY',
#  '15:A', '26:B', '37:C', '6:D', '7:E', 'EMPTY', 'EMPTY']

print(bang.vet_tim(37))  # [4, 5, 6]: tìm thành công
print(bang.vet_tim(18))  # [7, 8, 9]: tìm thất bại

bang.xoa(26)
print(bang.vet_tim(37))  # [4, 5, 6]: đi qua DELETED
print(bang.lay(37))      # C: vẫn tìm thấy khóa

bang.gan(48, "F")        # Bắt đầu tại ô 4; tái sử dụng ô 5
bang.gan(37, "C2")       # Cập nhật thay vì thêm trùng
print(bang.xem())
# ['EMPTY', 'EMPTY', 'EMPTY', 'EMPTY',
#  '15:A', '48:F', '37:C2', '6:D', '7:E', 'EMPTY', 'EMPTY']
print(bang.so_khoa)      # 5
```

Trong thực tế, thư viện có thể dùng những chiến lược băm khác, tự tăng kích thước hoặc dọn tombstone. Mã trên cố ý giữ số ô cố định để từng bước thăm dò và sự tăng trưởng của cụm đều quan sát được.

## 8. Hệ số tải và chi phí của kết cụm

Gọi `n` là số khóa đang hoạt động và `m` là số ô. **Hệ số tải (load factor)** được tính bởi:

\[
\alpha = \frac{n}{m}, \qquad 0 \leq \alpha \leq 1.
\]

Khi `α` tăng, bảng có ít ô trống hơn; xác suất một lần thăm dò chạm vào cụm dài thường tăng. Trong mô hình phân tích lý tưởng cho linear probing với các **chỉ số bắt đầu được phân bố độc lập và đều**, bảng đủ lớn và chưa có tombstone, số lần kiểm tra ô trung bình thường được ước lượng xấp xỉ:

\[
\begin{aligned}
E[\text{tìm thành công}] &\approx \tfrac12\left(1+\frac{1}{1-\alpha}\right),\\
E[\text{tìm thất bại}] &\approx \tfrac12\left(1+\frac{1}{(1-\alpha)^2}\right).
\end{aligned}
\]

| Hệ số tải `α` | Số ô kiểm tra xấp xỉ khi tìm thấy | Số ô kiểm tra xấp xỉ khi không thấy |
| ---: | ---: | ---: |
| 0,50 | 1,5 | 2,5 |
| 0,75 | 2,5 | 8,5 |
| 0,90 | 5,5 | 50,5 |

Các giá trị trong bảng là **ước lượng theo mô hình**, không phải kết quả chạy mã và không phải bảo đảm trên mọi dữ liệu. Mô hình này giả định các **chỉ số bắt đầu** phân bố đều, trong khi **dãy thăm dò vẫn là tuyến tính**. Không được thay bằng công thức của mô hình “mỗi khóa có một hoán vị thăm dò ngẫu nhiên”: đó là giả định khác và cho kết quả khác.

Với tải được kiểm soát và giả định băm phù hợp, chi phí kỳ vọng của một thao tác có thể xem là `O(1)` nếu tính băm và so sánh khóa mất `O(1)`. Tuy nhiên, trong trường hợp xấu nhất, bảng có thể phải kiểm tra đến `m` ô, tức **`O(m)` bước thăm dò**. Riêng khóa dài còn tốn thời gian tính băm và so sánh; không nên gộp chi phí đó vào `O(1)` nếu độ dài khóa thay đổi.

Một lần mở rộng hoặc dựng lại bảng phải phân bố lại các khóa theo số ô mới, có thể tốn `O(n+m_{mới})`. Nếu dung lượng tăng hợp lý, chi phí tái phân bố có thể được phân bổ trên nhiều lần thêm, nhưng không làm biến mất chi phí của một lần mở rộng cụ thể.

### Tải thực tế khi có tombstone

Nếu có `d` ô mang dấu `DELETED`, chỉ số `α = n/m` chưa thể hiện hết độ dài đường tìm kiếm. Một đại lượng hữu ích khác là:

\[
\alpha_{\text{hiệu dụng}} = \frac{n+d}{m}.
\]

Tombstone chưa phải là bản ghi hoạt động, nhưng khi tìm khóa không tồn tại, thuật toán vẫn phải thăm dò qua các ô đó. Vì vậy, các bảng thực tế có thể kích hoạt **rehash** để xóa dấu đã xóa hoặc tăng dung lượng khi số tombstone và cụm trở nên lớn.

## 9. Cách giảm tác động của kết cụm

**Chọn hàm băm phù hợp.** Những mã khóa có mẫu đều đặn, ví dụ chỉ khác ở vài bit cao, có thể dồn về ít chỉ số nếu hàm chọn ngăn quá đơn giản. Cần kiểm tra phân bố trên tập khóa ứng dụng thực sự dùng, nhất là khi dữ liệu có cấu trúc.

**Kiểm soát hệ số tải.** Mở rộng bảng trước khi quá đầy thường giúp giảm số ô phải thử. Ngưỡng tải phụ thuộc cách cài đặt, yêu cầu bộ nhớ và tần suất tìm thất bại; không có một ngưỡng tối ưu cho mọi chương trình.

**Quản lý tombstone.** Có thể tái sử dụng ô đánh dấu xóa khi thêm mới, hoặc định kỳ dựng lại bảng để bỏ tombstone. Với một số cài đặt linear probing, dịch lùi khi xóa cũng là một lựa chọn nhưng đòi hỏi xử lý đúng chuỗi thăm dò.

**Xem xét phương pháp khác khi cần.** Quadratic probing có thể giảm kết cụm sơ cấp nhưng vẫn có thể khiến những khóa cùng chỉ số ban đầu đi chung một dãy. Double hashing dùng bước nhảy phụ thuộc khóa, giúp các dãy thăm dò khác nhau hơn nếu thiết kế đúng. Separate chaining lại lưu nhiều khóa trong một ngăn và có đặc điểm bộ nhớ khác. Việc chọn cấu trúc nên dựa trên dữ liệu, tần suất thêm/xóa/tìm và kết quả đo thực tế.

## 10. Bất biến cần duy trì và lỗi thường gặp

Để một map dùng linear probing luôn tìm đúng dữ liệu:

1. **Cùng một quy tắc:** thêm, tìm, cập nhật và xóa phải dùng cùng `h(k)`, dung lượng hiện tại và thứ tự thử ô.
2. **Không dừng sớm:** một khóa đang hoạt động phải nằm trên đường thử trước ô `EMPTY` đầu tiên của khóa đó. Gặp `DELETED` không được dừng tìm.
3. **Không tạo khóa trùng:** khi thêm mới, phải kiểm tra khóa bằng nhau trong đoạn cần thăm dò trước khi tái sử dụng tombstone.
4. **Không lặp vô hạn:** giới hạn tối đa `m` lần thăm dò trong bảng dung lượng `m`.
5. **Khóa ổn định:** những thuộc tính tham gia hàm băm và so sánh khóa không bị thay đổi trong lúc khóa nằm trong bảng.
6. **Phân bố lại khi đổi dung lượng:** chỉ số `h(k)` và vị trí lưu thực tế có thể thay đổi; bản ghi cần được chèn lại vào bảng mới.

Một nhầm lẫn thường gặp là cho rằng **mọi phần tử nằm cùng một cụm đều có cùng mã băm**; ví dụ ở mục 3 đã bác bỏ điều đó. Nhầm lẫn khác là cho rằng **nhiều ô trống đồng nghĩa mọi thao tác đều nhanh**; khi các ô trống nằm xa nơi khóa bắt đầu, một cụm cục bộ vẫn có thể khiến tìm kiếm chậm.

## 11. Tự kiểm tra

**Câu 1.** Bảng có 11 ô, linear probing, `h(k)=k mod 11`. Thêm lần lượt `15,26,37,6,7`. Khóa `6` và `7` nằm ở đâu?

**Đáp án:** Khóa `6` có vị trí bắt đầu là 6 nhưng ô 6 chứa `37`, nên nằm ở ô 7. Khóa `7` bắt đầu ở 7 nhưng ô 7 có `6`, nên nằm ở ô 8. Đoạn `4..8` tạo thành một cụm.

**Câu 2.** Trên bảng đó, tìm khóa `18` chưa tồn tại cần kiểm tra những ô nào?

**Đáp án:** `18 mod 11 = 7`, nên kiểm tra ô `7 → 8 → 9`. Ô 9 là `EMPTY` nên dừng, kết luận chưa có khóa 18.

**Câu 3.** Sau khi xóa `26` tại ô 5, vì sao không được đặt ô 5 thành `EMPTY` theo cách xóa đơn giản?

**Đáp án:** Vì tìm `37` phải đi từ ô 4 qua ô 5 đến ô 6. Nếu ô 5 là `EMPTY`, thao tác tìm sẽ dừng sớm và bỏ sót `37`. Có thể dùng `DELETED` hoặc một kỹ thuật dịch lùi được cài đặt đúng.

**Câu 4.** Có phải kết cụm sơ cấp chỉ hình thành khi các khóa có cùng `h(k)`?

**Đáp án:** Không. Các khóa bắt đầu ở những vị trí khác nhau cũng có thể nhập vào một đoạn liên tiếp đã có dữ liệu, khiến đoạn ngày càng dài.

**Câu 5.** Vì sao bảng có `α = 0,9` thường gặp nhiều vấn đề hơn khi tìm không thành công so với bảng có `α = 0,5`?

**Đáp án:** Bảng gần đầy hơn, ít ô `EMPTY` để kết thúc tìm kiếm và các cụm có thể dài hơn. Theo mô hình băm đều của linear probing, số ô kiểm tra khi tìm thất bại tăng nhanh khi `α` tiến gần 1.

**Ghi nhớ:** Linear probing thử `h(k), h(k)+1, h(k)+2, ...` theo modulo dung lượng bảng. Nó sử dụng bộ nhớ liên tục hiệu quả nhưng dễ tạo **cụm ô đã chiếm liên tiếp**. Các cụm không chỉ do khóa có cùng mã băm mà còn do những khóa bắt đầu bên trong cụm làm cụm lớn thêm. Muốn giữ hiệu năng và tính đúng đắn, phải dùng quy tắc thăm dò nhất quán, xử lý xóa đúng cách, kiểm soát tải và phân bố lại dữ liệu khi cần.
