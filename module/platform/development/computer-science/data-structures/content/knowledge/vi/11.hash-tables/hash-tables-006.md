# Địa chỉ mở và quy tắc thăm dò ô

## 1. Va chạm khi mọi phần tử nằm ngay trong bảng

Trong **bảng băm (hash table)**, ta dùng một khóa để lưu và tìm giá trị, chẳng hạn `"SV1024"` để lấy hồ sơ sinh viên. Hàm băm biến khóa thành mã băm; từ mã băm, bảng chọn vị trí bắt đầu tra cứu. Nếu nhiều khóa hướng đến cùng một vị trí, ta gặp **va chạm (collision)**.

**Địa chỉ mở (open addressing)** giải quyết va chạm bằng cách tìm **một ô khác ngay trong mảng nền**. Mỗi ô chứa tối đa một bản ghi khóa–giá trị đang hoạt động. Khác với nối chuỗi (separate chaining), không cần một danh sách liên kết riêng cho mỗi ngăn.

Ví dụ một mảng gồm 7 ô:

```text
Chỉ số       0     1     2     3     4     5     6
           +-----+-----+-----+-----+-----+-----+-----+
Bảng       |     |     |     | 10  | 17  | 24  | 31  |
           +-----+-----+-----+-----+-----+-----+-----+
```

Nếu các khóa `10`, `17`, `24`, `31` cùng có chỉ số ban đầu `k mod 7 = 3`, bảng không thể đặt tất cả vào ô 3. Thay vào đó, nó thử các ô theo một **quy tắc thăm dò (probing rule)** đã xác định: ô 3, rồi ô khác, rồi ô khác nữa, cho đến khi tìm được nơi phù hợp.

Trong địa chỉ mở, cần phân biệt:

- **Chỉ số ban đầu:** vị trí suy ra từ hàm băm trước khi xử lý va chạm.
- **Dãy thăm dò:** thứ tự những ô mà thuật toán sẽ thử đối với khóa đó.
- **Ô lưu thực tế:** ô được chọn sau khi thăm dò, có thể khác chỉ số ban đầu.

Địa chỉ mở cần có chỗ trống để thêm khóa mới. Với `n` khóa và `m` ô, hệ số tải `α = n/m` phải nhỏ hơn 1 tại thời điểm cần thêm một khóa mới chưa có, trừ khi bảng mở rộng trước khi chèn.

## 2. Công thức tổng quát của dãy thăm dò

Gọi `h_1(k)` là chỉ số ban đầu của khóa `k`, với `0 <= h_1(k) < m`; `j` là số thứ tự lần thử, bắt đầu từ 0. Quy tắc thăm dò tạo ra:

\[
p(k,j) \in \{0,1,\ldots,m-1\},\qquad j=0,1,2,\ldots
\]

Thường có `p(k,0) = h_1(k)`. Khi ô thử đã chứa khóa khác, thuật toán tăng `j` rồi thử `p(k,j)`.

Để bảng hoạt động đúng, việc **thêm, tìm, cập nhật và xóa** phải dựa trên cùng quy tắc thăm dò, cùng cách so sánh khóa và cùng kích thước bảng hiện tại. Đặc biệt, thuật toán không được kết luận “không tìm thấy” chỉ vì ô ban đầu chứa khóa khác.

Một dãy thăm dò tốt cần tiếp cận đủ ô để tìm chỗ trống, hạn chế những cụm va chạm lớn và tránh kiểm tra đi kiểm tra lại một nhóm ô quá sớm. Không phải công thức nào cũng đi qua tất cả `m` ô; tính chất này phải được kiểm tra theo từng phương pháp.

## 3. Thăm dò tuyến tính (linear probing)

**Thăm dò tuyến tính** thử lần lượt các ô liền kề, quay về đầu mảng khi tới cuối:

\[
p(k,j)=(h_1(k)+j)\bmod m.
\]

Với `m=7` và `h_1(k)=k\bmod7`, thêm lần lượt `10`, `17`, `24`, `31`:

| Khóa | Ô thử theo thứ tự | Ô được chọn |
| ---: | --- | ---: |
| 10 | 3 (trống) | 3 |
| 17 | 3 (bận) → 4 (trống) | 4 |
| 24 | 3 (bận) → 4 (bận) → 5 (trống) | 5 |
| 31 | 3 (bận) → 4 (bận) → 5 (bận) → 6 (trống) | 6 |

```text
                bắt đầu tại 3
                      |
                      v
Chỉ số:   0    1    2    3    4    5    6
         [ ]  [ ]  [ ]  [10] [17] [24] [31]
                       ^----^----^----^
                       chuỗi ô liên tiếp có dữ liệu
```

Nếu tìm `24`, ta phải đi qua ô 3 (`10`) và ô 4 (`17`) rồi mới thấy `24` ở ô 5. Nếu tìm `38`, cũng có chỉ số ban đầu là 3, ta thử lần lượt 3, 4, 5, 6, rồi **quấn vòng (wrap around)** tới ô 0 đang trống. Khi không có dấu đã xóa ảnh hưởng đến việc tìm kiếm, gặp ô **chưa từng sử dụng** như ô 0 cho phép kết luận khóa `38` không có trong bảng.

**Ưu điểm:** đơn giản, duyệt các ô kề nhau nên thường tận dụng bộ nhớ đệm tốt, và dãy thăm dò lần lượt đi qua mọi ô nếu cho phép tối đa `m` lần thử.

**Nhược điểm:** dễ xuất hiện **kết cụm sơ cấp (primary clustering)**: một đoạn dài các ô liên tiếp đã có dữ liệu làm các lần chèn hoặc tra cứu sau phải đi qua cùng đoạn, khiến cụm có xu hướng kéo dài.

## 4. Thăm dò bậc hai (quadratic probing)

Thăm dò bậc hai tăng khoảng cách theo biểu thức bậc hai thay vì luôn dịch một ô:

\[
p(k,j)=(h_1(k)+c_1j+c_2j^2)\bmod m.
\]

Các hằng số `c_1`, `c_2` và dung lượng `m` phải được chọn phù hợp để tạo dãy thăm dò có các tính chất cần thiết. Không có bảo đảm rằng công thức với hệ số bất kỳ sẽ thử được tất cả các ô.

Ví dụ chọn `m=7`, `h_1(k)=3`, `c_1=0`, `c_2=1`, tức `p(k,j)=(3+j^2) mod 7`:

| Lần thử `j` | `(3+j²) mod 7` | Ô thử |
| ---: | ---: | ---: |
| 0 | 3 | 3 |
| 1 | 4 | 4 |
| 2 | 0 | 0 |
| 3 | 5 | 5 |
| 4 | 5 | 5 (lặp) |
| 5 | 0 | 0 (lặp) |
| 6 | 4 | 4 (lặp) |

Dãy này chỉ thăm được bốn ô khác nhau (`3, 4, 0, 5`) trong bảy lần thử. Nếu cả bốn ô đó đều bận, **phép chèn có thể thất bại dù các ô 1, 2, 6 vẫn trống**. Vì vậy, khi triển khai quadratic probing cần biết rõ điều kiện về kích thước bảng, hệ số và ngưỡng tải để bảo đảm tìm được ô thích hợp; không thể chỉ đếm số ô còn trống trên toàn bảng.

Thăm dò bậc hai thường giảm vấn đề các cụm ô liên tiếp của linear probing, nhưng các khóa có **cùng chỉ số ban đầu** vẫn đi qua cùng một dãy khi dùng cùng hệ số. Đây là dạng **kết cụm thứ cấp (secondary clustering)**.

## 5. Băm kép (double hashing)

**Băm kép** dùng hai hàm để xác định chỉ số bắt đầu và **bước nhảy** của một khóa:

\[
p(k,j)=(h_1(k)+j\,h_2(k))\bmod m.
\]

Yêu cầu quan trọng là `h_2(k)\neq0` theo modulo `m` và `\gcd(h_2(k),m)=1`. Khi bước nhảy nguyên tố cùng nhau với `m`, dãy sẽ thăm **đủ `m` ô** trước khi quay lại ô đầu.

Ví dụ đặt `m=7` (số nguyên tố):

\[
h_1(k)=k\bmod7,\qquad h_2(k)=1+(k\bmod6).
\]

Khi thêm `10,17,24,31`, cả bốn khóa đều có `h_1(k)=3`, nhưng bước nhảy khác nhau:

| Khóa | `h_1` | `h_2` | Dãy ô được thử đến lúc chèn |
| ---: | ---: | ---: | --- |
| 10 | 3 | 5 | 3 (trống) |
| 17 | 3 | 6 | 3 → 2 (trống) |
| 24 | 3 | 1 | 3 → 4 (trống) |
| 31 | 3 | 2 | 3 → 5 (trống) |

```text
Chỉ số:   0    1    2    3    4    5    6
         [ ]  [ ]  [17] [10] [24] [31] [ ]
```

Các khóa cùng ô bắt đầu không nhất thiết đi cùng một dãy, nên double hashing thường hạn chế kết cụm thứ cấp tốt hơn quadratic probing. Đổi lại, cần tính thêm một hàm băm và bảo đảm bước nhảy phù hợp với dung lượng bảng.

Nếu `m` là lũy thừa của hai, bước nhảy phải là số **lẻ** để nguyên tố cùng nhau với `m`; nếu `m` nguyên tố, bước nhảy thuộc `1,\ldots,m-1` đều hợp lệ.

## 6. So sánh ba quy tắc thăm dò

| Quy tắc | Công thức minh họa | Ưu điểm | Điều cần lưu ý |
| --- | --- | --- | --- |
| Tuyến tính | `(h_1+j) mod m` | Đơn giản, locality tốt; thăm đủ các ô | Primary clustering |
| Bậc hai | `(h_1+c_1 j+c_2 j²) mod m` | Giảm cụm liền kề | Có thể lặp trước khi thăm đủ ô; secondary clustering |
| Băm kép | `(h_1+j h_2) mod m` | Dãy thăm dò thay đổi theo khóa, giảm kết cụm | Cần `gcd(h_2,m)=1`, chi phí hàm băm thứ hai |

Không có quy tắc tối ưu cho mọi dữ liệu. Chọn cách phù hợp cần xét chất lượng hàm băm, hệ số tải, số thao tác tìm thất bại, số lần xóa, cách quản lý bộ nhớ và hiệu quả bộ nhớ đệm.

## 7. Thêm, tìm, cập nhật: khi nào dừng thăm dò?

Mỗi ô trong bảng địa chỉ mở cần một trạng thái để việc tìm kiếm diễn ra chính xác:

| Trạng thái | Ý nghĩa | Khi tìm khóa | Khi thêm khóa |
| --- | --- | --- | --- |
| **EMPTY** (chưa dùng) | Chưa từng đặt bản ghi vào ô theo chuỗi thao tác hiện tại | Có thể kết luận không thấy khi đến ô này theo dãy thăm dò | Có thể dùng để lưu khóa mới |
| **OCCUPIED** (đang dùng) | Có cặp khóa–giá trị | So sánh khóa; nếu khác thì tiếp tục | Nếu khóa bằng thì cập nhật; nếu khác thì tiếp tục |
| **DELETED** (đã xóa, tombstone) | Trước đó có bản ghi ở đây nhưng đã xóa | **Phải tiếp tục tìm**, không được dừng | Ghi nhớ để có thể tái sử dụng, nhưng phải kiểm tra khóa trùng ở các ô phía sau |

### Thêm/cập nhật `put(k,v)`

1. Tạo dãy thăm dò của `k`, đi qua tối đa số ô được phép theo quy tắc.
2. Nếu gặp `OCCUPIED` có khóa bằng `k`, **cập nhật giá trị** và kết thúc.
3. Ghi nhớ vị trí `DELETED` đầu tiên gặp được, nhưng tiếp tục tra cứu để tránh tạo khóa trùng ở các ô sau.
4. Khi gặp `EMPTY`, thêm khóa mới vào `DELETED` đã ghi nhớ (nếu có), hoặc vào chính `EMPTY`.
5. Nếu đã thăm hết dãy hợp lệ mà chưa gặp khóa hoặc `EMPTY`, có thể tái sử dụng `DELETED` đã thấy; nếu không còn chỗ thích hợp thì phải mở rộng bảng hoặc báo đầy.

### Tìm `get(k)`

Tính lại **cùng dãy thăm dò** đã dùng khi chèn. Gặp khóa bằng `k` thì trả về giá trị. Gặp `DELETED` hoặc bản ghi của khóa khác thì tiếp tục. Gặp `EMPTY` thì dừng vì nếu khóa tồn tại và được chèn theo đúng quy tắc, nó đã phải xuất hiện trước ô chưa từng dùng này. Nếu không gặp `EMPTY`, cần giới hạn số lần thử để tránh lặp vô hạn.

**Bất biến mấu chốt:** Trên đường thăm dò đến một khóa đang lưu không được có ô `EMPTY` khiến thao tác tìm dừng sớm. Vì vậy, các ô từng chứa dữ liệu mà bị xóa phải được xử lý đúng.

## 8. Xóa: vì sao cần dấu đã xóa (tombstone)?

Trở lại bảng tuyến tính gồm `10,17,24,31` ở các ô `3,4,5,6`. Giả sử ta xóa khóa `17` ở ô 4.

Nếu xóa bằng cách đánh dấu ô 4 là **EMPTY**, thao tác tìm `24` sẽ:

```text
Ô 3: thấy 10, không bằng 24 → đi tiếp
Ô 4: EMPTY → dừng, kết luận không có 24    (SAI)
Ô 5: thực tế vẫn còn 24
```

Cách xử lý đơn giản là để ô 4 mang trạng thái **DELETED**:

```text
Trước xóa:  [3:10] [4:17]      [5:24] [6:31]
Sau xóa:    [3:10] [4:DELETED] [5:24] [6:31]

Tìm 24: ô 3 (khác) → ô 4 (đã xóa, tiếp tục) → ô 5 (thấy 24).
```

Trong một số cách cài đặt linear probing, có thể **dịch các bản ghi phía sau về chỗ phù hợp** thay cho tombstone (backward-shift deletion), nhưng cần bảo vệ đúng bất biến dãy thăm dò. Với quadratic probing và double hashing, không thể tùy tiện áp dụng quy tắc dịch lùi của linear probing.

Tombstone hỗ trợ tìm chính xác, nhưng để lại chi phí: nếu bảng tích lũy nhiều ô `DELETED`, tìm một khóa không có có thể phải đi qua nhiều ô hơn. Bởi vậy các bảng thực tế thường **tái phân bố (rehash)** để loại tombstone khi chúng trở nên quá nhiều.

## 9. Ví dụ Python: bảng địa chỉ mở với linear probing

Đoạn mã cài đặt một map nhỏ cho **khóa nguyên** để quan sát trực tiếp dãy thăm dò. Mảng có dung lượng cố định, dùng `None` biểu diễn `EMPTY`, và một đối tượng riêng `DA_XOA` biểu diễn tombstone. Mỗi ô đang dùng chứa tuple `(khóa, giá_trị)`; **giá trị có thể là `None`** mà không bị nhầm với ô trống.

```python
class BangBamDiaChiMo:
    def __init__(self, so_o=7):
        if so_o <= 0:
            raise ValueError("Số ô phải lớn hơn 0")
        self.o = [None] * so_o
        self.DA_XOA = object()
        self.so_khoa = 0

    def _cac_o_thu(self, khoa: int):
        m = len(self.o)
        bat_dau = khoa % m
        for j in range(m):  # Thử nhiều nhất m ô, kể cả khi bảng đầy
            yield (bat_dau + j) % m

    def gan(self, khoa: int, gia_tri):
        o_da_xoa = None
        for i in self._cac_o_thu(khoa):
            hien_tai = self.o[i]

            if hien_tai is None:  # Gặp ô chưa từng dùng
                dich = o_da_xoa if o_da_xoa is not None else i
                self.o[dich] = (khoa, gia_tri)
                self.so_khoa += 1
                return

            if hien_tai is self.DA_XOA:
                if o_da_xoa is None:
                    o_da_xoa = i
                continue  # Vẫn phải tìm khóa có thể nằm phía sau

            if hien_tai[0] == khoa:
                self.o[i] = (khoa, gia_tri)  # Cập nhật đúng khóa
                return

        if o_da_xoa is not None:  # Không còn EMPTY nhưng vẫn có tombstone
            self.o[o_da_xoa] = (khoa, gia_tri)
            self.so_khoa += 1
            return
        raise OverflowError("Bảng đã đầy; cần mở rộng")

    def lay(self, khoa: int):
        for i in self._cac_o_thu(khoa):
            hien_tai = self.o[i]
            if hien_tai is None:
                break
            if hien_tai is self.DA_XOA:
                continue
            if hien_tai[0] == khoa:
                return hien_tai[1]
        raise KeyError(khoa)

    def xoa(self, khoa: int):
        for i in self._cac_o_thu(khoa):
            hien_tai = self.o[i]
            if hien_tai is None:
                break
            if hien_tai is self.DA_XOA:
                continue
            if hien_tai[0] == khoa:
                self.o[i] = self.DA_XOA
                self.so_khoa -= 1
                return hien_tai[1]
        raise KeyError(khoa)

    def trang_thai(self):
        return [
            "EMPTY" if x is None else
            "DELETED" if x is self.DA_XOA else
            f"{x[0]}={x[1]}"
            for x in self.o
        ]


bang = BangBamDiaChiMo(7)
for k, v in [(10, "A"), (17, "B"), (24, "C"), (31, "D")]:
    bang.gan(k, v)
print(bang.trang_thai())
# ['EMPTY', 'EMPTY', 'EMPTY', '10=A', '17=B', '24=C', '31=D']

bang.xoa(17)
print(bang.trang_thai())
# ['EMPTY', 'EMPTY', 'EMPTY', '10=A', 'DELETED', '24=C', '31=D']
print(bang.lay(24))  # C: đi xuyên qua DELETED ở ô 4

bang.gan(38, "E")   # 38 mod 7 = 3, tái sử dụng tombstone ở ô 4
bang.gan(24, "C2")  # Cập nhật khóa cũ, không thêm bản sao
print(bang.trang_thai())
# ['EMPTY', 'EMPTY', 'EMPTY', '10=A', '38=E', '24=C2', '31=D']
print(bang.so_khoa)  # 4
```

Đây là cài đặt giảng dạy cố định 7 ô, nên khi không còn ô phù hợp sẽ báo `OverflowError`; nó chưa có cơ chế tự mở rộng hay dọn tombstone. Trong hệ thống sử dụng lâu dài cần bổ sung các chức năng đó. Nếu dùng khóa đối tượng, còn phải áp dụng một hàm băm phù hợp và bảo đảm khóa bằng nhau cho cùng mã băm.

## 10. Hệ số tải, độ phức tạp và thời điểm mở rộng

Gọi `n` là số khóa đang hoạt động và `m` là số ô:

\[
\alpha=\frac{n}{m},\qquad 0\leq\alpha\leq1.
\]

Để **chèn một khóa mới chưa tồn tại** mà không mở rộng bảng, ít nhất phải có một ô không chứa khóa đang hoạt động, và quy tắc thăm dò phải có khả năng tiếp cận ô đó. Địa chỉ mở thường chủ động giữ `α` nhỏ hơn một ngưỡng nhất định để các dãy thăm dò không quá dài.

| Thao tác | Kỳ vọng khi băm và thăm dò phù hợp, tải được kiểm soát | Trường hợp xấu nhất |
| --- | --- | --- |
| Tìm `get(k)` | `O(1)` | `O(m)` lần thăm dò |
| Thêm/cập nhật `put(k,v)` | `O(1)` nếu chưa tính một lần mở rộng | `O(m)` lần thăm dò |
| Xóa `remove(k)` | `O(1)` | `O(m)` lần thăm dò |

Kỳ vọng `O(1)` **không phải bảo đảm cho mọi khóa hoặc mọi hàm băm**. Chẳng hạn, khi nhiều khóa va chạm vào cùng một vùng, linear probing có thể phải duyệt chuỗi ô dài. Một số cận kỳ vọng lý thuyết yêu cầu **giả định băm đều cho toàn bộ dãy thăm dò**; chỉ số ban đầu phân bố đều không tự bảo đảm điều đó.

Nếu có `d` ô mang tombstone, số ô chưa thực sự trống là `n+d`. Do đó, chỉ số `α=n/m` có thể còn nhỏ trong khi việc tìm khóa không tồn tại vẫn chậm vì phải đi qua nhiều `DELETED`. Một đại lượng hữu ích để theo dõi là **tỷ lệ ô chưa trống** `(n+d)/m`, bên cạnh hệ số tải của các khóa đang hoạt động.

Khi tải quá cao hoặc quá nhiều tombstone, ta tạo mảng mới (thường có nhiều ô hơn hoặc cùng dung lượng để dọn tombstone), rồi **chèn lại mọi khóa đang hoạt động theo quy tắc thăm dò của mảng mới**. Một lần làm lại bảng có chi phí cỡ `O(n+m_{mới})` khi phân bố lại dữ liệu và khởi tạo mảng. Nếu tăng dung lượng hợp lý, phân tích chi phí thêm có thể tính thêm yếu tố **phân bổ (amortized)**.

Không gian dùng cho các ô là `O(m)`; đây cũng là ưu điểm về locality so với cài đặt nối chuỗi bằng nhiều nút phân tán. Đổi lại, địa chỉ mở thường nhạy với hệ số tải và đòi hỏi xử lý xóa cẩn thận hơn.

## 11. Các lỗi triển khai thường gặp

1. **Dừng khi thấy ô có khóa khác:** một va chạm chỉ có nghĩa phải thử vị trí tiếp theo, không có nghĩa khóa cần tìm vắng mặt.
2. **Biến ô vừa xóa thành EMPTY:** có thể làm đứt đường thăm dò đến những khóa phía sau. Dùng tombstone hoặc thuật toán xóa có chứng minh giữ bất biến.
3. **Dùng ngay tombstone đầu tiên mà không tìm tiếp:** có thể tạo hai bản ghi cho cùng khóa, vì bản ghi cũ có thể nằm xa hơn trên dãy.
4. **Không giới hạn số lần thử:** bảng đầy hoặc một dãy quadratic lặp ô sớm có thể dẫn đến vòng lặp vô tận.
5. **Chọn bước nhảy double hashing không nguyên tố cùng nhau với `m`:** có thể chỉ thử một phần các ô và báo hết chỗ dù vẫn còn ô trống.
6. **Giữ nguyên vị trí cũ khi đổi kích thước bảng:** phép ánh xạ và dãy thăm dò phụ thuộc `m`; cần phân bố lại bản ghi.
7. **Thay đổi thuộc tính tạo hash của khóa đã lưu:** lần tra cứu sau có thể bắt đầu ở dãy khác và không tìm thấy khóa dù bản ghi vẫn còn.

## 12. Tự kiểm tra

**Câu 1.** Bảng có 7 ô, linear probing, `h_1(k)=k mod 7`. Sau khi thêm `10,17,24`, mỗi khóa nằm ở ô nào?

**Đáp án:** `10` ở ô 3, `17` ở ô 4, `24` ở ô 5. Cả ba có chỉ số ban đầu là 3 nhưng phải thăm dò qua ô đã bận.

**Câu 2.** Vì sao xóa khóa 17 ở ô 4 rồi đánh dấu ô 4 là EMPTY khiến tìm khóa 24 có thể sai?

**Đáp án:** Tìm 24 theo linear probing bắt đầu ở ô 3 rồi đến ô 4. Nếu ô 4 là EMPTY, thuật toán dừng trước khi tới ô 5 nơi 24 còn lưu. Đánh dấu DELETED giúp tìm kiếm tiếp tục.

**Câu 3.** Với `m=7`, `p(k,j)=(3+j^2) mod 7`, tại sao biết bảng còn ô trống vẫn chưa chắc thêm được khóa?

**Đáp án:** Dãy chỉ đi qua các ô 3, 4, 0, 5 rồi lặp. Nếu bốn ô ấy đã bận, các ô 1, 2, 6 dù trống cũng không xuất hiện trong dãy này.

**Câu 4.** Băm kép với `m=8`, bước nhảy `h_2(k)=2` có thể thử bao nhiêu ô khác nhau trước khi lặp? Làm sao khắc phục?

**Đáp án:** Chỉ thử được `8/gcd(8,2)=4` ô. Có thể chọn bước nhảy lẻ để nguyên tố cùng nhau với 8, nhờ đó đi qua đủ 8 ô.

**Câu 5.** Một bảng có 10 khóa đang hoạt động, 10 tombstone và 100 ô. `α` bằng bao nhiêu? Vì sao tìm kiếm có thể chậm hơn bảng chỉ có 10 khóa và không có tombstone?

**Đáp án:** `α=10/100=0,1`. Nhưng có 20 ô chưa trống, tương ứng `(n+d)/m=0,2`; tombstone khiến tìm kiếm phải tiếp tục thăm dò qua những ô này thay vì dừng ngay như khi gặp EMPTY. Chi phí thực tế còn phụ thuộc cách chúng phân bố.

**Ghi nhớ:** Địa chỉ mở lưu bản ghi **ngay trong các ô của mảng** và dùng một **dãy thăm dò nhất quán** để giải quyết va chạm. Linear probing, quadratic probing và double hashing khác nhau ở thứ tự thử ô; thao tác xóa phải giữ đường tìm kiếm thông qua tombstone hoặc kỹ thuật tương đương. Hiệu năng phụ thuộc vào hàm băm, hệ số tải, cách thăm dò và chính sách mở rộng/dọn tombstone.
