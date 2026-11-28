# Dấu mốc đã xóa và lý do không thể đơn giản đặt ô về rỗng

## 1. Xóa một khóa có thể làm hỏng việc tìm khóa khác

Trong **bảng băm (hash table)** dùng **địa chỉ mở (open addressing)**, các cặp khóa–giá trị được đặt trực tiếp trong các ô của mảng. Khi một khóa gặp va chạm, bảng thử các ô khác theo **dãy thăm dò** cho đến khi tìm được chỗ để lưu. Để tìm khóa sau này, chương trình phải đi lại chính dãy ấy.

Hãy xét bảng có `m = 7` ô, chọn chỉ số đầu tiên `h(k) = k mod 7` và dùng **thăm dò tuyến tính**:

\[
p(k,j)=(h(k)+j)\bmod7,\qquad j=0,1,\ldots,6.
\]

Chèn theo thứ tự các cặp `(10,"A")`, `(17,"B")`, `(24,"C")`, `(31,"D")`. Vì cả bốn khóa đều có số dư 3 khi chia cho 7, chúng nằm ở các ô liên tiếp:

```text
Chỉ số:       0       1       2       3       4       5       6
            +-------+-------+-------+-------+-------+-------+-------+
Trạng thái:  | RỖNG  | RỖNG  | RỖNG  | 10:A  | 17:B  | 24:C  | 31:D  |
            +-------+-------+-------+-------+-------+-------+-------+
                                      ^       ^       ^
                    Tìm 24 đi qua:   ô 3 --> ô 4 --> ô 5
```

Bây giờ xóa `17` ở ô 4. Nếu chương trình chỉ đặt ô 4 thành **rỗng (EMPTY)**, thao tác tìm `24` sẽ thực hiện:

1. Thử ô 3: đang lưu khóa 10, không trùng khóa 24, tiếp tục.
2. Thử ô 4: thấy `EMPTY`, kết luận khóa 24 **không tồn tại**.
3. Nhưng ô 5 vẫn đang lưu khóa 24! Kết luận trên **sai**.

Đây là lỗi kinh điển của việc xóa trong bảng băm địa chỉ mở: một ô rỗng giữa đường thăm dò làm tìm kiếm **dừng sớm**, bỏ sót các khóa đã bị đẩy sang phía sau bởi va chạm.

**Giải pháp thông dụng:** thay ô 4 bằng một **dấu mốc đã xóa (tombstone)**, ký hiệu `DELETED`. Khi tìm, chương trình **đi qua** dấu này, thay vì coi nó là ô chưa từng dùng.

## 2. Phân biệt ba trạng thái của một ô

Trong một cài đặt địa chỉ mở dùng tombstone, mỗi ô cần được xem là một trong ba trạng thái:

| Trạng thái | Ý nghĩa | Khi tìm khóa | Khi thêm khóa |
| --- | --- | --- | --- |
| **EMPTY** | Ô chưa từng chứa bản ghi kể từ lần khởi tạo/dựng lại bảng gần nhất | Có thể **dừng**, kết luận không thấy khóa trên dãy thăm dò | Có thể chèn tại đây nếu chưa thấy khóa trùng |
| **OCCUPIED** | Ô đang chứa cặp khóa–giá trị hợp lệ | So sánh khóa; trùng thì trả kết quả, khác thì tiếp tục | Trùng thì cập nhật; khác thì tiếp tục |
| **DELETED** | Ô từng chứa bản ghi nhưng bản ghi đó đã bị xóa | **Không được dừng**; phải tiếp tục | Có thể ghi nhớ để tái sử dụng sau khi kiểm tra khóa trùng ở phía sau |

Ba trạng thái có thể được biểu diễn bằng **enum**, cờ trạng thái hoặc đối tượng đánh dấu riêng. Không nên dùng giá trị `None` của **phần value** để phân biệt ô trống: một bản ghi hợp lệ hoàn toàn có thể có `value = None`. Trạng thái của ô cần độc lập với dữ liệu được lưu.

Ví dụ sau khi xóa khóa 17 đúng cách:

```text
Ô số:        0       1       2       3        4        5       6
          [EMPTY] [EMPTY] [EMPTY] [10:A] [DELETED] [24:C] [31:D]

Tìm 24:
          ô 3 (khóa khác) -> ô 4 (DELETED, bỏ qua) -> ô 5 (đúng khóa)
```

Tombstone **không phải một bản ghi đang hoạt động**: không có khóa/giá trị để trả về và không được tính vào số lượng phần tử `n`. Nhưng nó cũng **không tương đương EMPTY**: khi tra cứu, nó cho biết đường thăm dò vẫn có thể tiếp tục đến bản ghi phía sau.

## 3. Vì sao gặp EMPTY thì được dừng, còn DELETED thì không?

Đối với một bảng được chèn và xóa đúng quy tắc, ta duy trì bất biến:

> Mỗi khóa đang hoạt động nằm trên dãy thăm dò của chính nó, **trước ô EMPTY đầu tiên** theo dãy ấy (nếu có).

Lý do: khi thêm khóa mới vào một bảng không có khóa trùng, thuật toán đặt nó tại một ô `EMPTY` thích hợp hoặc một `DELETED` đã gặp trước `EMPTY`. Vì vậy, nếu lúc tìm bắt gặp `EMPTY` trước khi thấy khóa, khóa ấy không thể đang nằm sâu hơn trong cùng dãy, miễn là các thao tác trước đều giữ bất biến.

Ngược lại, ô `DELETED` đã từng có bản ghi; có thể một khóa khác đã va chạm tại ô này và được đặt phía sau **trước khi bản ghi cũ bị xóa**. Xóa không được thay đổi sự thật đó.

Lập luận này áp dụng cho những dãy thăm dò nhất quán như tuyến tính, bậc hai hay băm kép; điểm khác nhau là **thứ tự các ô**. Với dãy không bao phủ toàn bảng, cần giới hạn số lần thử và tôn trọng những điều kiện riêng để chèn được vào ô còn trống.

### Vết tìm trước và sau khi xóa

| Tình huống | Các ô thử khi tìm khóa 24 | Kết quả |
| --- | --- | --- |
| Chưa xóa 17 | `3 → 4 → 5` | Tìm thấy khóa 24 |
| Xóa 17 và **đặt 4 = EMPTY** | `3 → 4` | **Sai:** kết luận không thấy |
| Xóa 17 và **đặt 4 = DELETED** | `3 → 4 → 5` | **Đúng:** tìm thấy khóa 24 |

Nếu bảng có `m` ô, tìm kiếm cũng phải giới hạn **tối đa `m` lần thăm dò** trong trường hợp không gặp `EMPTY` (ví dụ bảng từng đầy rồi nhiều khóa bị xóa thành tombstone). Thiếu giới hạn này có thể gây vòng lặp vô hạn.

## 4. Xóa đúng cách bằng tombstone

Để xóa khóa `k` trong bảng địa chỉ mở:

1. Tính dãy thăm dò cho `k`, theo đúng công thức đã dùng lúc thêm.
2. Nếu gặp `OCCUPIED` với khóa bằng `k`, đánh dấu ô là `DELETED`; giảm số khóa đang hoạt động `n` đi 1 và tăng số tombstone `d` lên 1.
3. Nếu gặp `OCCUPIED` với khóa khác hoặc `DELETED`, tiếp tục thăm dò.
4. Nếu gặp `EMPTY` hoặc đã thử hết dãy hợp lệ mà không thấy khóa, trả kết quả “không tồn tại” và **không sửa trạng thái**.

Sơ đồ:

```text
Tìm vị trí khóa k
       |
       v
 [ô OCCUPIED?] -- đúng khóa --> chuyển sang DELETED, cập nhật bộ đếm
       |
       +-- khóa khác / DELETED --> thăm dò ô kế tiếp
       |
       +-- EMPTY / hết dãy ---> khóa không tồn tại
```

Khi xóa, không chỉ cần bảo vệ việc tìm **khóa phía sau**, mà còn bảo vệ phép cập nhật: nếu khóa đã tồn tại sâu trong dãy nhưng chương trình không đi qua tombstone, nó có thể tạo **bản ghi trùng khóa** ở một vị trí mới.

## 5. Tái sử dụng tombstone nhưng không tạo trùng khóa

Sau khi xóa 17, bảng có tombstone ở ô 4 và khóa 24 ở ô 5.

**Trường hợp A — cập nhật khóa đã tồn tại:** gọi `put(24, "C2")`.

- Thăm dò ô 3 (khóa 10): đi tiếp.
- Thăm dò ô 4 (`DELETED`): **ghi nhớ** ô 4, nhưng chưa chèn.
- Thăm dò ô 5 (khóa 24): **cập nhật tại ô 5** thành `(24,"C2")`.
- Không thay đổi số phần tử; ô 4 vẫn là `DELETED`.

Nếu lập tức chèn khóa 24 vào ô 4 khi gặp tombstone, bảng sẽ có hai bản ghi cho **cùng khóa logic**, vi phạm bất biến của map.

**Trường hợp B — thêm khóa mới:** gọi `put(38, "E")`, trong đó `38 mod 7 = 3`.

- Thử ô 3 (khóa 10), ô 4 (`DELETED`, ghi nhớ), ô 5 (khóa 24), ô 6 (khóa 31), rồi ô 0 (`EMPTY`).
- Không có khóa 38 đang tồn tại; ta có thể đặt `(38,"E")` vào ô `DELETED` đã ghi nhớ ở vị trí 4, thay vì dùng ô 0.
- Số khóa đang hoạt động tăng 1; số tombstone giảm 1.

```text
Sau xóa 17:      [3:10] [4:DEL] [5:24]   [6:31] [0:EMPTY]
Sau put(24,C2):  [3:10] [4:DEL] [5:24/C2] [6:31] [0:EMPTY]
Sau put(38,E):   [3:10] [4:38/E] [5:24/C2] [6:31] [0:EMPTY]
```

**Quy tắc chuẩn:** ghi nhớ tombstone đầu tiên nhìn thấy, **tiếp tục tìm** đến `EMPTY` đầu tiên hoặc hết dãy hợp lệ, rồi mới quyết định chèn khóa mới vào tombstone đó. Nếu tìm thấy khóa trùng trên đường đi, phải cập nhật khóa cũ thay vì thêm bản sao.

### Nếu bảng không còn ô EMPTY

Một bảng có thể **không còn EMPTY** nhưng vẫn có nhiều `DELETED`. Trường hợp đó, phép tìm phải giới hạn `m` lần thử. Phép chèn khóa mới cần kiểm tra toàn bộ dãy và nếu không thấy khóa trùng, vẫn được dùng tombstone đã ghi nhớ. Nếu không có cả `EMPTY` lẫn `DELETED` trong dãy, bảng đã hết chỗ phù hợp và cần mở rộng hoặc trả lỗi.

Đối với quadratic probing với dãy chỉ bao phủ một phần ô, “hết dãy hợp lệ” có thể xảy ra **ngay cả khi ô ngoài dãy đang trống**. Tombstone không tự sửa được hạn chế về độ phủ của quy tắc thăm dò.

## 6. Cài đặt Python: ba trạng thái và thao tác đầy đủ

Ví dụ sau cài đặt một map nhỏ dùng **linear probing** cho **khóa nguyên**. Bảng có dung lượng cố định để dễ quan sát; nó hỗ trợ chèn/cập nhật, tìm, xóa, theo dõi số tombstone và báo lỗi khi không còn vị trí phù hợp. Hai đối tượng `EMPTY` và `DELETED` là dấu riêng, không nhầm với `None` của giá trị.

```python
class BangBamCoTombstone:
    EMPTY = object()
    DELETED = object()

    def __init__(self, so_o=7):
        if so_o <= 0:
            raise ValueError("Số ô phải lớn hơn 0")
        self.o = [self.EMPTY] * so_o
        self.so_khoa = 0
        self.so_da_xoa = 0

    def _duong_thu(self, khoa: int):
        m = len(self.o)
        bat_dau = khoa % m
        for j in range(m):
            yield (bat_dau + j) % m

    def gan(self, khoa: int, gia_tri):
        o_da_xoa_dau = None
        for i in self._duong_thu(khoa):
            muc = self.o[i]
            if muc is self.EMPTY:
                dich = o_da_xoa_dau if o_da_xoa_dau is not None else i
                self.o[dich] = (khoa, gia_tri)
                self.so_khoa += 1
                if o_da_xoa_dau is not None:
                    self.so_da_xoa -= 1
                return
            if muc is self.DELETED:
                if o_da_xoa_dau is None:
                    o_da_xoa_dau = i
                continue
            if muc[0] == khoa:
                self.o[i] = (khoa, gia_tri)  # Đã có: cập nhật
                return

        # Đã thử m ô; có thể không còn EMPTY nhưng có DELETED.
        if o_da_xoa_dau is not None:
            self.o[o_da_xoa_dau] = (khoa, gia_tri)
            self.so_khoa += 1
            self.so_da_xoa -= 1
            return
        raise OverflowError("Bảng đầy; cần mở rộng")

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
                self.so_da_xoa += 1
                return muc[1]
        raise KeyError(khoa)

    def xem(self):
        return [
            "EMPTY" if muc is self.EMPTY else
            "DELETED" if muc is self.DELETED else
            f"{muc[0]}={muc[1]}"
            for muc in self.o
        ]


bang = BangBamCoTombstone(7)
for k, v in [(10, "A"), (17, "B"), (24, "C"), (31, "D")]:
    bang.gan(k, v)
print(bang.xem())
# ['EMPTY', 'EMPTY', 'EMPTY', '10=A', '17=B', '24=C', '31=D']

bang.xoa(17)
print(bang.xem())
# ['EMPTY', 'EMPTY', 'EMPTY', '10=A', 'DELETED', '24=C', '31=D']
print(bang.lay(24))                    # C
print(bang.so_khoa, bang.so_da_xoa)   # 3 1

bang.gan(24, "C2")                   # Cập nhật ở ô 5, không nhân bản
print(bang.so_khoa, bang.so_da_xoa)   # 3 1
bang.gan(38, "E")                    # Tái sử dụng ô 4
print(bang.xem())
# ['EMPTY', 'EMPTY', 'EMPTY', '10=A', '38=E', '24=C2', '31=D']
print(bang.so_khoa, bang.so_da_xoa)   # 4 0
```

Trường hợp đặc biệt, với bảng 3 ô đã từng đầy, xóa một khóa rồi thêm khóa mới:

```python
khac = BangBamCoTombstone(3)
for k in (0, 1, 2):
    khac.gan(k, str(k))

khac.xoa(1)         # Ô 1 thành DELETED; không còn EMPTY
khac.gan(4, "moi")  # Thăm đủ 3 ô rồi tái sử dụng ô 1
print(khac.xem())   # ['0=0', '4=moi', '2=2']
```

**Giới hạn của ví dụ:** chưa tự tăng dung lượng hoặc dọn tombstone; vì vậy nên dùng nó để học bất biến, không dùng trực tiếp làm cấu trúc dữ liệu sản xuất. Việc băm và so sánh đối tượng khóa phức tạp cần thêm hợp đồng “hai khóa bằng nhau phải có mã băm bằng nhau”, và khóa không nên bị sửa những thuộc tính tạo mã băm khi đang nằm trong bảng.

## 7. Tombstone ảnh hưởng đến hệ số tải và hiệu năng ra sao?

Gọi `m` là số ô, `n` là số khóa đang hoạt động, `d` là số ô `DELETED`. Cần phân biệt:

\[
\alpha=\frac{n}{m}
\quad\text{(tải khóa hoạt động)},\qquad
\beta=\frac{n+d}{m}
\quad\text{(tỷ lệ ô không EMPTY)}.
\]

Ví dụ `m = 10`, `n = 3`, `d = 5`: `α = 0,3`, nhưng `β = 0,8`. Dù bảng chỉ lưu ba khóa, việc tìm không thành công vẫn có thể phải đi qua nhiều tombstone trước khi gặp ô `EMPTY`.

| Hành động, khi `m` không đổi | `n` | `d` | `α` | `β` |
| --- | --- | --- | --- | --- |
| Chèn khóa vào ô `EMPTY` | Tăng 1 | Giữ nguyên | Tăng `1/m` | Tăng `1/m` |
| Chèn khóa mới vào ô `DELETED` | Tăng 1 | Giảm 1 | Tăng `1/m` | Giữ nguyên |
| Cập nhật khóa cũ | Giữ nguyên | Giữ nguyên | Giữ nguyên | Giữ nguyên |
| Xóa khóa, đặt tombstone | Giảm 1 | Tăng 1 | Giảm `1/m` | Giữ nguyên |
| Dựng lại cùng dung lượng, bỏ tombstone | Giữ nguyên | Về 0 | Giữ nguyên | Giảm còn `α` |

Không nên xem `β` là công thức chính xác của thời gian tìm kiếm: còn phải xét **phân bố các ô đã dùng**, chất lượng hàm băm và quy tắc thăm dò. Nhưng khi `β` cao, tìm thất bại thường khó gặp `EMPTY` hơn và số bước thử có thể tăng.

Với khóa có chi phí băm và so sánh được coi là hằng số, thao tác trong bảng dùng địa chỉ mở thường có **thời gian kỳ vọng `O(1)`** nếu phân bố băm tốt và tải được kiểm soát. Trường hợp xấu có thể cần **`O(m)` lần thử ô**, nhất là khi bảng có nhiều va chạm, tombstone hoặc gần đầy. Riêng xóa chỉ thay trạng thái sau khi đã tìm được ô; chi phí **tìm ô để xóa** vẫn có thể lớn.

**Bộ nhớ:** mảng ô và cờ trạng thái chiếm `O(m)`; tombstone không yêu cầu tạo nút liên kết riêng, nhưng làm giảm hiệu quả sử dụng các đường thăm dò. Khi tình trạng xóa–thêm lặp lại liên tục, bảng thường cần chính sách dọn dấu đã xóa.

## 8. Khi nào nên dọn tombstone hoặc thay cách xóa?

**Dựng lại (rehash/rebuild):** tạo mảng mới, chỉ chèn lại những bản ghi đang hoạt động rồi bỏ toàn bộ tombstone. Có thể giữ nguyên `m` nếu mục tiêu là dọn dấu xóa, hoặc tăng `m` nếu đồng thời cần giảm hệ số tải. Không được sao chép nguyên vị trí cũ khi thay đổi `m`: dãy thăm dò có thể khác.

**Theo dõi hai tỷ số:** `α=n/m` phản ánh số khóa, còn `β=(n+d)/m` phản ánh số ô vẫn cản trở điều kiện dừng khi tra cứu. Có thể khởi động dựng lại khi `d` nhiều hoặc `β` vượt ngưỡng cài đặt lựa chọn. Ngưỡng tối ưu phụ thuộc workload và bộ nhớ, không phải hằng số đúng cho mọi hệ thống.

**Xóa bằng dịch lùi (backward-shift deletion):** một số biến thể **linear probing** cho phép dịch các bản ghi tiếp sau về những vị trí thích hợp để không để lại tombstone. Nhưng phải xét chỉ số ban đầu của từng khóa và các cụm có thể quấn vòng cuối mảng; **không phải cứ dịch tất cả phần tử sang trái một ô là đúng**.

Đối với **quadratic probing** hoặc **double hashing**, đường thăm dò thường không phải một đoạn liên tiếp. Không thể tự ý áp dụng cùng thuật toán dịch lùi như linear probing; một lựa chọn an toàn, dễ lý giải là giữ tombstone rồi xây dựng lại khi cần.

Một lần dựng lại phải khởi tạo mảng mới và chèn lại `n` bản ghi. Với chiến lược phân bố và tải thích hợp, chi phí kỳ vọng thường ở bậc `O(m_{mới}+n)`; trường hợp va chạm bất lợi có thể đắt hơn. Khi resize theo cấp số nhân, chi phí tái phân bố có thể được **phân bổ (amortized)** qua nhiều thao tác, nhưng lần dựng lại đơn lẻ vẫn tốn thời gian.

## 9. Các sai lầm triển khai cần tránh

1. **Xóa bằng EMPTY:** làm đứt đường tìm đến các khóa bị va chạm phía sau.
2. **Tìm kiếm dừng tại DELETED:** không khác việc xóa sai; phải đi tiếp.
3. **Chèn ngay khi gặp tombstone đầu tiên:** có thể bỏ sót khóa trùng phía sau và tạo hai bản ghi cùng khóa.
4. **Nhầm giá trị rỗng với ô trống:** bản ghi có `value=None` vẫn là `OCCUPIED`.
5. **Không giới hạn lần thử:** khi toàn bảng không còn `EMPTY`, phép tìm khóa vắng mặt có thể lặp vô hạn.
6. **Chỉ theo dõi `α`:** nhiều tombstone có thể khiến việc tìm chậm dù số khóa thực tế nhỏ.
7. **Giữ tombstone khi phân bố lại bảng:** dọn bảng cần tái chèn **chỉ các bản ghi đang hoạt động**.
8. **Dùng quy tắc thăm dò khác khi tìm và chèn:** làm mất khả năng định vị đúng khóa.

## 10. Tự kiểm tra

**Câu 1.** Bảng 7 ô dùng linear probing, các khóa `10,17,24` chiếm ô `3,4,5`. Sau khi xóa 17, nếu đặt ô 4 thành `EMPTY`, điều gì xảy ra khi tìm 24?

**Đáp án:** Tìm bắt đầu ở ô 3, thấy khóa 10 rồi đến ô 4 `EMPTY` nên dừng sai. Ô 5 vẫn chứa 24 nhưng không được kiểm tra.

**Câu 2.** Vì sao `DELETED` phải được phân biệt với `EMPTY`?

**Đáp án:** `DELETED` từng có dữ liệu, nên khóa khác có thể đã bị đẩy ra phía sau trong cùng dãy thăm dò; phải tiếp tục tìm. `EMPTY` đánh dấu điểm có thể dừng tìm đúng theo bất biến.

**Câu 3.** Ô 4 là tombstone, khóa 24 vẫn nằm ở ô 5. Gọi `put(24, "mới")` nên làm gì?

**Đáp án:** Ghi nhớ ô 4 nhưng tiếp tục dò tới ô 5, rồi cập nhật giá trị của 24 tại ô 5. Không chèn bản ghi 24 thứ hai ở ô 4.

**Câu 4.** Bảng có `m=20`, `n=5` và `d=9`. Tính `α` và `β`. Xóa thêm một khóa thành tombstone sẽ thay đổi hai tỷ số ra sao?

**Đáp án:** Ban đầu `α=5/20=0,25`, `β=(5+9)/20=0,7`. Xóa thêm một khóa: `n=4`, `d=10`; `α=0,2` và `β` vẫn bằng `0,7`.

**Câu 5.** Không còn ô `EMPTY`, nhưng còn một tombstone. Liệu bảng có thể thêm khóa mới không?

**Đáp án:** Có thể, nếu dãy thăm dò của khóa chạm tới tombstone đó và không tìm thấy bản ghi cùng khóa. Cần giới hạn số lần thử để kết thúc chắc chắn.

**Câu 6.** Tại sao không áp dụng tùy tiện thao tác dịch trái một ô sau khi xóa cho mọi kiểu địa chỉ mở?

**Đáp án:** Vị trí hợp lệ phụ thuộc dãy thăm dò của từng khóa. Linear probing cần dịch lùi có kiểm tra, còn quadratic probing và double hashing có thứ tự thăm dò khác; dịch tùy tiện có thể đặt khóa sau điểm `EMPTY` và làm tìm kiếm sai.

**Ghi nhớ:** Trong bảng băm địa chỉ mở, **ô chưa từng dùng** và **ô đã xóa** không tương đương. `EMPTY` cho phép dừng tìm, còn `DELETED` buộc thuật toán tiếp tục vì phía sau có thể còn khóa bị đẩy đi do va chạm. Tombstone bảo vệ tính đúng đắn nhưng có thể làm đường thăm dò dài hơn; muốn chèn, cập nhật và xóa chính xác phải duy trì dãy thăm dò nhất quán, tái sử dụng dấu xóa có kiểm tra và định kỳ dựng lại bảng khi cần.
