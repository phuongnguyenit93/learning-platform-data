# Chọn kích thước nút theo trang lưu trữ và chi phí I/O

Khi học cây tìm kiếm nhiều nhánh, ta thường nghe rằng **B-tree** và **B+ tree** thấp hơn cây tìm kiếm nhị phân vì mỗi nút có thể chứa nhiều khóa và nhiều con. Nhưng trên hệ thống lưu trữ thực tế, quyết định **một nút chứa bao nhiêu khóa** không hoàn toàn tùy ý: nút thường được thiết kế vừa trong **một trang lưu trữ** (*page*), chẳng hạn 4 KiB, 8 KiB hoặc 16 KiB.

Trang càng lớn, một nút càng có thể chứa nhiều khóa và con trỏ; hệ số phân nhánh (*fan-out*) lớn thường làm **giảm số tầng của cây**. Tuy nhiên, trang lớn cũng đồng nghĩa một lần tải hoặc ghi trang có thể chuyển nhiều byte hơn, bộ nhớ đệm chứa được ít trang hơn, và việc tách nút có thể đụng tới nhiều dữ liệu hơn. Vì vậy, câu hỏi đúng không phải là “kích thước nút lớn nhất có thể là bao nhiêu?” mà là:

> **Với kích thước khóa, kiểu bản ghi, loại thiết bị và kiểu truy vấn đã biết, nên tổ chức nút vừa với trang nào để cân bằng số tầng, số lần I/O, lượng byte chuyển và chi phí cập nhật?**

Bài này tập trung vào cách **chọn kích thước nút theo trang và mô hình chi phí I/O** cho B-tree/B+ tree. Ta xây dựng công thức sức chứa cho nút trong và lá, tính ví dụ 4/8/16 KiB, ước lượng số tầng cho mười triệu mục, phân tích tìm chính xác, truy vấn khoảng, chèn/xóa, bộ nhớ đệm và viết chương trình Java tính thử các phương án. Mọi con số về kích thước đều là **giả định minh họa**, không phải đặc tả của một hệ quản trị cụ thể.

## 1. Vì sao nút thường gắn với trang lưu trữ?

Một **trang** (*page*) là đơn vị dữ liệu logic mà hệ quản lý lưu trữ hoặc bộ đệm của cơ sở dữ liệu thường quản lý cùng nhau. Nó chứa nhiều byte liên tiếp, gồm phần dữ liệu và thông tin điều khiển. Một trang cơ sở dữ liệu **không nhất thiết** trùng kích thước sector vật lý, khối NAND của SSD hay đơn vị truyền tối thiểu mà hệ điều hành thực sự dùng.

Nếu một nút B+ tree được lưu vừa trong **một trang**, khi cần nút đó hệ thống có thể yêu cầu nạp một trang vào **buffer pool**. Sau khi trang nằm trong RAM, thuật toán so sánh các khóa trong nút và chọn con tiếp theo. Các liên kết con trên đĩa thường là **mã trang** (*page ID*), chứ không phải con trỏ địa chỉ bộ nhớ có hiệu lực vĩnh viễn.

```text
                    B+ tree trên hệ lưu trữ phân trang

                         [50 | 80]              trang gốc
                        /    |    \
                      P7    P18    P42          page ID của con
                      |      |      |
                      v      v      v
                 [10..40] [50..70] [80..99]    các trang lá

Một lần tìm x=60:
  1. Tải/truy cập trang gốc.
  2. So sánh 50, 80 -> chọn con có page ID = P18.
  3. Tải/truy cập trang P18.
  4. Tìm mục có khóa 60 trong trang lá.
```

Nếu trang gốc đã ở RAM, bước 1 **không phải** một lượt đọc đĩa. Nếu trang lá chưa ở RAM, bước 3 có thể phải đọc thiết bị. Cần tách **số nút được thăm**, **số trang chưa có trong cache** và **số I/O vật lý**; ba đại lượng này liên quan nhưng không đồng nhất.

### Nút và trang không luôn là một

Mô hình “**một nút = một trang**” rất hữu ích khi phân tích B-tree/B+ tree trên đĩa. Tuy nhiên, một số cài đặt có:

- Trang với **nhiều nút logic**, nút kích thước biến thiên hoặc cấu trúc chia sẻ trang.
- Nút/trang lớn có vùng **overflow** cho khóa hay giá trị quá dài.
- Khóa được nén, trang có vùng slot directory và các bản ghi được dồn lại khi cập nhật.
- Bộ lưu trữ dùng các đơn vị truyền vật lý khác với trang logic.

Vì vậy, ta cần nói rõ **mô hình bố cục** trước khi suy số khóa tối đa hay fan-out.

## 2. Hai loại nút có bài toán sức chứa khác nhau

Trong B+ tree thông dụng:

| Thành phần | Nút trong (*internal*) | Nút lá (*leaf*) |
| --- | --- | --- |
| Khóa | **Separator** để định tuyến | Khóa của mục dữ liệu |
| Liên kết | Page ID của **các nút con** | Thường có `next` và có thể `prev` |
| Dữ liệu nghiệp vụ | Thường không giữ bản ghi | Có thể giữ giá trị, toàn bộ bản ghi hoặc `record_id` |
| Quan hệ cấu trúc | `k` separator → `k+1` con | Có `r` mục dữ liệu, **không có con đi xuống** |
| Tác động của kích thước mục | Chủ yếu kích thước separator + page ID | Kích thước khóa + payload/`RID` + metadata |

**Fan-out tối đa** của một nút trong là số con mà nó có thể giữ, ký hiệu `F_{\max}`. Với `k_{\max}` separator:

\[
F_{\max}=k_{\max}+1.
\]

Ngược lại, **sức chứa lá** là số mục dữ liệu tối đa trên một lá, ký hiệu `L_{\max}`. Hai đại lượng thường **khác nhau** vì payload ở lá có thể lớn hơn nhiều so với một page ID.

Trong **B-tree** theo mô hình bản ghi có thể nằm ở cả nút trong và lá, một nút trong có thể phải dành thêm chỗ cho dữ liệu gắn với khóa, khiến công thức fan-out khác B+ tree. Không được lấy công thức nút trong của B+ tree để áp máy móc cho mọi B-tree.

## 3. Một mô hình bố cục trang đơn giản

Giả sử mỗi trang có:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `P` | Số byte của một trang |
| `H` | Phần header/metadata chung của trang, tính bằng byte |
| `K` | Số byte của một khóa hoặc separator đã lưu |
| `C` | Số byte của một page ID/con trỏ con |
| `S` | Chi phí phụ cho mỗi khóa/mục, chẳng hạn một slot trong slot directory |
| `R` | Số byte của payload/`record_id` cho mỗi mục lá |
| `N` | Byte dành cho liên kết đến lá kế tiếp (và liên kết phụ nếu được tính) |

**Giả định quan trọng:** `K`, `C`, `S` và `R` là kích thước cố định trong phép tính. Điều này giúp xây dựng mô hình dễ kiểm tra; cấu trúc thực tế có thể dùng khóa độ dài biến thiên, nén, căn chỉnh hoặc các slot có kích thước khác nhau.

### Bố cục nút trong

Một nút trong có `k` separator và `k+1` con:

```text
+------------------------------------------------------------+
| Header H                                                   |
+------------------------------------------------------------+
| P0 | K0 | P1 | K1 | P2 | ... | K(k-1) | Pk              |
+------------------------------------------------------------+
| Metadata/slot per separator: S * k (mô hình minh họa)      |
+------------------------------------------------------------+
```

Điều kiện vừa trang:

\[
H+kK+(k+1)C+kS\le P.
\]

Gom các phần:

\[
H+C+k(K+C+S)\le P.
\]

Suy ra số separator tối đa:

\[
\boxed{
k_{\max}
=\left\lfloor\frac{P-H-C}{K+C+S}\right\rfloor
}
\]

và fan-out tối đa:

\[
\boxed{F_{\max}=k_{\max}+1.}
\]

Điều kiện để mô hình hợp lý là `P>H+C`, các kích thước đều dương khi cần, và trang đủ chứa ít nhất **một separator cùng hai con** nếu được dùng làm nút trong không rỗng.

### Bố cục nút lá

Một lá có `r` mục `(khóa, payload)` và cần chừa `N` byte cho liên kết lá:

\[
H+N+r(K+R+S)\le P.
\]

Suy ra:

\[
\boxed{
L_{\max}
=\left\lfloor\frac{P-H-N}{K+R+S}\right\rfloor.
}
\]

Trong mô hình này, `N` là **tổng chi phí liên kết lá được chọn**. Nếu lá có cả `next` và `prev`, hoặc hệ thống lưu thêm page ID của anh em phải để hỗ trợ B-link tree, phải tính đúng số byte tương ứng; không mặc định chỉ một liên kết.

### Đừng trừ header hai lần

Trong phép tính, header `H` được trừ **một lần trên mỗi trang**. Slot directory được biểu diễn bằng `S` **mỗi mục**. Nếu tài liệu bố cục đã đưa slot directory vào `H` hoặc không cần slot cho separator, phải thay đổi `S` để tránh **đếm chi phí hai lần**.

## 4. Ví dụ định lượng: trang 4, 8 và 16 KiB

Giả sử một chỉ mục B+ tree có bố cục:

- Header trang: `H=128` byte.
- Separator/khóa: `K=16` byte.
- Page ID con: `C=8` byte.
- Chi phí slot mỗi separator/mục: `S=4` byte.
- Lá có **một** liên kết `next`: `N=8` byte.
- Mục lá chứa `record_id`: `R=8` byte.

Ta tính lần lượt cho trang `4\ \mathrm{KiB}=4096` byte, `8\ \mathrm{KiB}=8192` byte và `16\ \mathrm{KiB}=16384` byte.

### Tính nút trong với trang 4 KiB

\[
\begin{aligned}
k_{\max}
&=\left\lfloor\frac{4096-128-8}{16+8+4}\right\rfloor\\
&=\left\lfloor\frac{3960}{28}\right\rfloor\\
&=141.
\end{aligned}
\]

Nút trong chứa được tối đa **141 separator**, nên có tối đa **142 con**. Kiểm tra số byte:

\[
128+141(16+4)+142(8)=4084\ \text{byte}.
\]

Trang còn `4096-4084=12` byte chưa dùng trong mô hình. Nếu thử `142` separator, nhu cầu sẽ là `4112` byte, **vượt 4 KiB**.

### Tính lá với `record_id` 8 byte

Với `N=8`:

\[
L_{\max}
=\left\lfloor
\frac{4096-128-8}{16+8+4}
\right\rfloor
=141.
\]

Trong bộ giả định này, nút trong và lá tình cờ có cùng giá trị số nguyên `141` cho separator/mục. **Đó là do lựa chọn kích thước minh họa**, không phải tính chất bắt buộc của B+ tree.

### Bảng cho ba kích thước trang

| Kích thước trang | `k_{\max}` separator/nút trong | `F_{\max}` con/nút trong | `L_{\max}` mục/lá với `RID` 8 B |
| --- | ---: | ---: | ---: |
| 4 KiB | 141 | 142 | 141 |
| 8 KiB | 287 | 288 | 287 |
| 16 KiB | 580 | 581 | 580 |

Trang tăng bốn lần từ 4 KiB lên 16 KiB thì số separator tối đa tăng từ 141 lên 580, gần nhưng không đúng bốn lần vì mỗi trang đều phải chừa header và các phần cố định.

### Nếu lá giữ bản ghi dài thay vì `RID`?

Giả sử vẫn khóa 16 byte, nhưng mỗi mục lá giữ **payload 128 byte** thay cho `RID` 8 byte. Khi đó:

\[
K+R+S=16+128+4=148\ \text{byte/mục}.
\]

| Trang | Lá với `RID` 8 B | Lá với payload 128 B |
| --- | ---: | ---: |
| 4 KiB | 141 mục | 26 mục |
| 8 KiB | 287 mục | 54 mục |
| 16 KiB | 580 mục | 109 mục |

Với trang 4 KiB:

\[
\left\lfloor\frac{4096-128-8}{148}\right\rfloor
=\left\lfloor\frac{3960}{148}\right\rfloor
=26.
\]

Vậy **chọn kích thước trang không thể tách khỏi quyết định lá lưu gì**. Chỉ mục phụ với `RID` nhỏ và cấu trúc lưu bản ghi ngay trong lá có thể có số lá rất khác nhau dù số khóa giống nhau.

## 5. Sức chứa tối đa không đồng nghĩa mức lấp đầy thực tế

Khi trang có thể giữ tối đa `L_{\max}` mục, **không phải mọi lá lúc nào cũng chứa đầy `L_{\max}` mục**. Chèn, xóa, tách/gộp và chính sách dành chỗ cho cập nhật có thể để lại các khoảng trống.

Đặt `\alpha` là **tỷ lệ lấp đầy lá dự kiến**, ví dụ `\alpha=0.70`. Một ước lượng đơn giản cho số mục thực trên một lá:

\[
L_{\text{eff}}
\approx\left\lfloor\alpha L_{\max}\right\rfloor.
\]

Với cấu hình chứa `RID` 8 B:

| Trang | `L_{\max}` | `L_{\text{eff}}` khi dùng 70% | Giải thích |
| --- | ---: | ---: | --- |
| 4 KiB | 141 | 98 | Khoảng 98 mục trên mỗi lá được dùng để ước lượng |
| 8 KiB | 287 | 200 | Khoảng 200 mục mỗi lá |
| 16 KiB | 580 | 406 | Khoảng 406 mục mỗi lá |

Giá trị `70\%` ở đây chỉ là **giả định lập kế hoạch**, không phải quy tắc bắt buộc của B-tree/B+ tree. Các thuật toán cân bằng có thể yêu cầu cận lấp đầy tối thiểu riêng cho từng loại nút; gốc cũng có ngoại lệ. **Fill factor khi xây chỉ mục** và **mức lấp đầy sau nhiều cập nhật** có thể khác nhau.

Đối với nút trong, phải ước lượng một **fan-out hiệu dụng** `F_{\text{eff}}` nếu muốn phản ánh mức sử dụng trung bình. Không được kết luận mọi nút có đúng `F_{\max}` con chỉ từ sức chứa trang.

### Một lưu ý về chèn tuần tự

Nếu khóa được thêm liên tiếp theo thứ tự tăng, phần lớn chèn có thể đi vào **lá phải nhất**. Chính sách tách nút cân đôi, tách theo hướng tăng khóa hay dành chỗ ở cuối trang ảnh hưởng đến mức lấp đầy sau đó. Hai cây có cùng `P,K,C,R,S` vẫn có thể khác đáng kể về số lá và số lần tách do **thứ tự cập nhật**.

## 6. Từ fan-out tới số tầng phải đi qua

Một cây nhiều nhánh có càng nhiều con ở mỗi nút trong thì thường càng **ít tầng**, nhưng cần xét số lượng lá và mức lấp đầy trước.

Giả sử:

- Chỉ mục chứa `n=10\,000\,000` mục dữ liệu.
- Lá chứa `RID` 8 B theo mô hình ở Mục 4.
- Dự kiến 70% sức chứa lá được sử dụng.
- **Để đơn giản cho phép tính cận thuận lợi**, các nút trong được tổ chức với số con gần `F_{\max}`. Đây là ước lượng thiên về cây gọn, **không phải bảo đảm chiều cao khi nút trong chỉ đạt mức lấp đầy thấp hơn**.

Số lá ước tính:

\[
N_{\text{leaf}}
=\left\lceil\frac{n}{L_{\text{eff}}}\right\rceil.
\]

Để đếm các tầng cha từ dưới lên, lặp:

\[
N_{\text{parent}}
=\left\lceil\frac{N_{\text{child}}}{F_{\max}}\right\rceil
\]

cho đến khi còn một nút gốc. Đây là mô hình **số trang lý tưởng**; khi xây cây thật phải phân phối số con phù hợp mức tối thiểu/tối đa, kể cả ngoại lệ của gốc.

### Tính từng trường hợp

**Trang 4 KiB:** `L_{\text{eff}}=98`, `F_{\max}=142`.

```text
10.000.000 mục dữ liệu
    -> 102.041 lá       (ceil(10.000.000 / 98))
    ->     719 nút cha  (ceil(102.041 / 142))
    ->       6 nút cha  (ceil(719 / 142))
    ->       1 gốc

Một đường gốc -> lá đi qua 4 trang logic.
```

**Trang 8 KiB:** `L_{\text{eff}}=200`, `F_{\max}=288`.

```text
10.000.000 mục dữ liệu
    -> 50.000 lá
    ->    174 nút cha
    ->      1 gốc

Một đường gốc -> lá đi qua 3 trang logic.
```

**Trang 16 KiB:** `L_{\text{eff}}=406`, `F_{\max}=581`.

```text
10.000.000 mục dữ liệu
    -> 24.631 lá
    ->     43 nút cha
    ->      1 gốc

Một đường gốc -> lá đi qua 3 trang logic.
```

Tóm tắt:

| Trang | Lá ước tính | Tầng nút trong từ dưới lên | Số trang trên đường tìm |
| --- | ---: | --- | ---: |
| 4 KiB | 102.041 | 719 → 6 → 1 | 4 |
| 8 KiB | 50.000 | 174 → 1 | 3 |
| 16 KiB | 24.631 | 43 → 1 | 3 |

**Không được kết luận 16 KiB luôn nhanh hơn 8 KiB vì cả hai có ba tầng.** Hai phương án cùng số tầng nhưng khác lượng byte trên mỗi trang, số mục một lá, số trang bị sửa khi cập nhật và hiệu quả cache.

### Điều kiện để ước lượng này có ích

Các phép đếm trên không đảm bảo chính xác cấu trúc sau chèn/xóa vì chúng giả định nội bộ được lấp gần đầy. Chúng hữu ích để **ước lượng cỡ lớn** và loại bỏ những phương án quá nhỏ/quá lớn, rồi tiếp tục bằng thử nghiệm với dữ liệu và mức lấp đầy thực tế.

Nếu dự kiến nút trong chỉ có trung bình `0.7 F_{\max}` con, hãy dùng `F_{\text{eff}}` thấp hơn trong phép chia; số tầng có thể tăng. Không trình bày số trang lý tưởng như một cận trên cho mọi cây hợp lệ.

## 7. Mô hình chi phí cho tìm kiếm chính xác

Với phép tìm một khóa trong B+ tree:

1. Đi từ gốc xuống một lá: thăm một nút ở mỗi tầng.
2. Tìm separator trong từng nút trong để chọn con.
3. Tìm khóa trong lá để lấy mục hoặc kết luận không có.
4. Nếu lá chứa `RID`, có thể cần đọc thêm trang giữ **bản ghi thật**.

Đặt:

- `h`: số cạnh từ gốc đến lá.
- `D=h+1`: số nút trên đường tìm.
- `M`: số trang trên đường tìm **chưa có trong buffer pool**.
- `T_{\text{read}}(P)`: chi phí đọc một trang kích thước `P` theo môi trường và thiết bị cụ thể.
- `T_{\text{cpu}}`: chi phí so sánh trong các nút và xử lý phần còn lại.

Một mô hình rất đơn giản:

\[
T_{\text{lookup}}
\approx M\cdot T_{\text{read}}(P)+T_{\text{cpu}}
+T_{\text{record}},
\]

trong đó `T_{\text{record}}` đại diện phần lấy bản ghi ngoài chỉ mục nếu cần. Công thức này giả định các lần đọc nằm trên đường phụ thuộc nhau; thực tế có thể có cache, prefetch và cơ chế thực thi khác.

### Đừng lấy số tầng nhân trực tiếp thành số I/O thật

Với cây 4 KiB ở Mục 6, một đường tìm có bốn trang logic. Nếu gốc và hai tầng nút trong đã nằm trong RAM, truy vấn chỉ có thể cần **một lần nạp lá**, hoặc **không có I/O** nếu lá cũng đã cache.

```text
4 trang logic trên đường tìm:

  root             [cache hit]
  internal level 1 [cache hit]
  internal level 2 [cache hit]
  leaf             [cache miss]  -> 1 lần nạp trang

Số nút thăm = 4
Số lần nạp trang = 1 (trong ví dụ)
```

Nếu fan-out lớn làm phần lớn tầng trong vừa với buffer pool, sự khác biệt về **chiều cao cây** có thể ít quan trọng hơn **tỷ lệ hit/miss của các lá**.

### Chi phí so sánh bên trong nút

Khi một nút chứa `k` khóa:

- Quét tuyến tính: O(k) phép so sánh trong trường hợp xấu.
- Tìm nhị phân: O(log(`k+1`)) phép so sánh.

Trong mô hình fan-out `F`, đường tìm có xấp xỉ O(log_F n) tầng. Nếu tìm nhị phân trong nút, tổng số so sánh CPU có thể được ước lượng:

\[
O(\log_F n\cdot\log F)=O(\log n).
\]

Vì vậy, tăng fan-out có thể làm **giảm số tầng** nhưng không tự động làm mọi phép so sánh CPU biến mất. Kích thước cache line, cách nén khóa, dự đoán nhánh và việc so sánh khóa dài cũng ảnh hưởng hiệu năng thực tế.

## 8. Mô hình chi phí cho truy vấn khoảng

Truy vấn khoảng trên B+ tree gồm hai pha:

1. **Định vị lá bắt đầu** bằng một đường từ gốc.
2. **Quét các lá kế tiếp** qua `next` cho đến hết khoảng hoặc đủ `LIMIT`.

Nếu cần trả `r` mục và các lá chứa khoảng `L_{\text{eff}}` mục liên tiếp, số lá phục vụ kết quả có thể được ước lượng ở bậc:

\[
N_{\text{scan}}
=O\left(\left\lceil\frac{r}{L_{\text{eff}}}\right\rceil+1\right).
\]

Hằng `+1` phản ánh lá ở ranh giới bắt đầu/kết thúc có thể chỉ có một phần mục phù hợp hoặc cần kiểm tra khóa đầu tiên vượt cận trên. Không coi công thức là số trang **chính xác** khi lá lấp đầy không đều.

### Ví dụ quét 1.000 mục liên tiếp

Với cùng giả định 70% mức đầy lá:

| Trang | `L_{\text{eff}}` | Số lá xấp xỉ để lấy 1.000 mục | Byte trang đọc, nếu đọc đủ các lá |
| --- | ---: | ---: | ---: |
| 4 KiB | 98 | 11 | `11\times4096=45.056` B |
| 8 KiB | 200 | 5 | `5\times8192=40.960` B |
| 16 KiB | 406 | 3 | `3\times16384=49.152` B |

Con số tính lượng byte này **không bao gồm** đường tìm tới lá đầu, cache hit/miss, trang biên bổ sung, định dạng payload ngoài chỉ mục hay chi phí metadata. Nó chỉ cho thấy **ít trang hơn không nhất thiết đồng nghĩa ít byte hơn**.

Nếu truy vấn thường trả **một hoặc vài mục**, trang lớn có thể tải nhiều dữ liệu không dùng tới. Nếu truy vấn thường quét **hàng nghìn mục liên tiếp**, trang lớn có thể giảm số lần chuyển lá và số yêu cầu I/O logic. Không có câu trả lời đúng cho mọi tỷ lệ giữa point lookup và range scan.

### Khi lá lưu `RID` thay cho bản ghi

Đọc 1.000 mục `(key,RID)` từ các lá chỉ mới cho biết **vị trí bản ghi**. Để lấy 1.000 bản ghi đầy đủ, hệ thống có thể phải đọc nhiều trang dữ liệu khác, nhất là khi các bản ghi phân tán ngẫu nhiên.

Vì thế, với chỉ mục không bao phủ (*non-covering index*), chi phí **fetch bản ghi** có thể lớn hơn chi phí quét lá. Với truy vấn chỉ cần các cột đã có trong chỉ mục (*covering index*), có thể không cần bước đọc bản ghi ngoài chỉ mục.

## 9. Chèn và xóa: kích thước trang ảnh hưởng chi phí ghi

Lợi ích của nút lớn là giảm độ cao, nhưng B-tree/B+ tree còn phải hỗ trợ **thay đổi dữ liệu**.

### 9.1. Chèn khi lá còn chỗ

Một mục mới được chèn vào vị trí đã sắp. Nếu trang dùng mảng/slot directory, cần chèn slot mới hoặc dịch vị trí; trang được đánh dấu **dirty** và cuối cùng có thể phải ghi lại.

Với trang lớn, một nút có thể chứa nhiều khóa nên có thể cần dịch nhiều mục hơn nếu tổ chức vật lý đơn giản. Tuy nhiên, thiết kế slotted page có thể giảm số byte phải dịch bằng cách thao tác slot thay vì di chuyển toàn bộ bản ghi; chi phí phụ thuộc cách cài đặt.

### 9.2. Chèn khi lá đầy: tách trang

```text
Trang lá L đầy:
    [10,20,30,40,50,60]

Chèn 35 -> cần phân phối lại:
    L: [10,20,30]
    R: [35,40,50,60]

Cha nhận separator = 35 (B+ tree theo min khóa lá phải).
Chuỗi lá: L -> R -> lá kế tiếp cũ.
```

Một lần tách có thể yêu cầu:

- Cấp phát trang mới `R`.
- Di chuyển/ghi một phần mục từ `L` sang `R`.
- Ghi lại `L`, `R`, separator và con trỏ ở **cha**.
- Cập nhật liên kết `next/prev` giữa các lá.
- Nếu cha đầy, tiếp tục tách ở tầng cao hơn, thậm chí tạo gốc mới.

Đây không chỉ là một phép đọc trang. Phép tách có thể sinh **nhiều trang bị thay đổi và nhiều bản ghi nhật ký**. Trong hệ thống bền vững, việc ghi nhật ký trước khi ghi trang dữ liệu (*write-ahead logging*) hay cơ chế copy-on-write còn ảnh hưởng lượng ghi thực tế.

### 9.3. Xóa khi nút thiếu mục

Xóa có thể làm lá hoặc nút trong thiếu mức lấp đầy. Thuật toán có thể:

- **Mượn** mục từ anh em và cập nhật separator.
- **Gộp** các trang kề nhau rồi loại một liên kết con của cha.
- **Hạ gốc** nếu gốc rỗng và chỉ còn một con.

Các thao tác mượn/gộp chạm vào ít nhất các trang liên quan và có thể lan lên trên. Vì thế, chọn trang rất lớn không chỉ giảm số nút mà còn thay đổi **chi phí thao tác cấu trúc và lượng dữ liệu cần ghi** khi cập nhật.

### 9.4. Fill factor là một đánh đổi

Để trang tương đối rỗng sau khi xây chỉ mục, ta có thể chọn fill factor thấp hơn nhằm **dành chỗ cho chèn mới**. Điều này có thể làm giảm tần suất tách gần hạn, nhưng sẽ tăng số lá và có thể tăng chi phí đọc/quét.

| Fill factor thấp | Fill factor cao |
| --- | --- |
| Nhiều chỗ trống cho chèn mới | Dùng dung lượng lưu trữ chặt hơn |
| Có thể giảm tách trang trong một số tải cập nhật | Có thể phát sinh tách sớm hơn khi chèn thêm |
| Số lá thường lớn hơn | Số lá thường ít hơn |
| Có thể quét nhiều trang hơn cùng số mục | Quét tuần tự có thể gọn hơn |

Không nên hiểu fill factor là núm vặn làm mọi workload nhanh hơn. Cần xem dữ liệu được chèn ngẫu nhiên hay tăng dần, tần suất xóa, độ ổn định khóa, cách hệ thống phân phối lại mục và yêu cầu đọc.

## 10. Tác động của khóa dài, nén và dữ liệu độ dài biến thiên

Công thức ở Mục 3 giả định kích thước khóa và mục **cố định**. Trong thực tế, khóa có thể là chuỗi dài, khóa ghép hoặc giá trị được nén.

### Khi khóa dài hơn

Với trang 4 KiB và giữ `H=128,C=8,S=4`:

| Độ dài separator `K` | `k_{\max}` theo mô hình | `F_{\max}` |
| --- | ---: | ---: |
| 8 B | 198 | 199 |
| 16 B | 141 | 142 |
| 32 B | 90 | 91 |

Ví dụ với `K=32`:

\[
k_{\max}
=\left\lfloor\frac{4096-128-8}{32+8+4}\right\rfloor
=\left\lfloor\frac{3960}{44}\right\rfloor
=90.
\]

Separator dài làm giảm fan-out và có thể tăng số tầng. Nếu khóa rất dài, một số hệ thống dùng **nén tiền tố** hoặc separator ngắn hơn khóa đầy đủ, nhưng việc so sánh và bảo toàn ranh giới cần thiết kế cẩn thận.

### Khóa/giá trị độ dài biến thiên

Với các chuỗi độ dài khác nhau, sức chứa trang là kết quả của tổng các kích thước thực tế:

\[
H+\text{fixed overhead}
+\sum_{i=1}^{q}\left(K_i+R_i+S_i\right)\le P.
\]

Không còn một số `L_{\max}` duy nhất đúng cho mọi trang. Có thể cần ước lượng bằng độ dài trung bình, phân vị cao hoặc kích thước lớn nhất, rồi kiểm thử bằng dữ liệu thật.

Với bản ghi quá lớn, hệ thống có thể để **payload ngoài trang** (*overflow/LOB pages*) và giữ tại lá một tham chiếu. Khi đó, việc đếm số mục trên lá chỉ mô tả **độ lớn của chỉ mục**, không bao gồm các trang chứa toàn bộ payload.

### Một vài chi phí ít thấy

- Slot directory, cờ xóa, con trỏ anh em, số phiên bản/MVCC và metadata giao dịch.
- Căn chỉnh và khoảng trống do sửa đổi bản ghi độ dài biến thiên.
- Checksum, mã hóa, nén trang và phần dự phòng cho cấu trúc nhật ký.
- Giới hạn tối đa cho kích thước khóa hoặc giá trị nội tuyến.

Muốn ước lượng chính xác cho một hệ thống cụ thể, phải lấy **bố cục trang của chính hệ thống đó**, không suy hoàn toàn từ mô hình lý thuyết.

## 11. Java: công cụ ước lượng sức chứa, fan-out và số tầng

Đoạn Java dưới đây dùng đúng **mô hình cố định của Mục 4**, gồm:

- Header 128 B, khóa 16 B, page ID 8 B.
- Slot 4 B mỗi separator/mục.
- Liên kết lá 8 B, `RID` 8 B.
- Tỷ lệ lấp đầy lá để tính thử là **70%**.
- Nút trong được ước lượng **gần đầy**, để tính một cấu trúc trang lý tưởng.

Chương trình **không tạo B+ tree thật**, mà tính **sức chứa vật lý** và **số trang của các tầng ước lượng** cho 10 triệu mục. Đây là một công cụ lập kế hoạch, không phải benchmark I/O.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class BPlusPageSizeEstimator {
    static final int HEADER_BYTES = 128;
    static final int KEY_BYTES = 16;
    static final int CHILD_POINTER_BYTES = 8;
    static final int SLOT_BYTES = 4;
    static final int LEAF_NEXT_BYTES = 8;
    static final int RECORD_ID_BYTES = 8;

    // ceil(n / d) cho n >= 0, d > 0, khong can cong d-1.
    static long ceilDiv(long n, long d) {
        if (n < 0 || d <= 0) {
            throw new IllegalArgumentException("Invalid division");
        }
        return n / d + (n % d == 0 ? 0 : 1);
    }

    static int maxInternalKeys(int pageBytes) {
        int available = pageBytes - HEADER_BYTES - CHILD_POINTER_BYTES;
        int perSeparator = KEY_BYTES + CHILD_POINTER_BYTES + SLOT_BYTES;
        if (available < perSeparator) {
            throw new IllegalArgumentException("Page too small");
        }
        return available / perSeparator;
    }

    static int maxLeafEntries(int pageBytes, int payloadBytes) {
        int available = pageBytes - HEADER_BYTES - LEAF_NEXT_BYTES;
        int perEntry = KEY_BYTES + payloadBytes + SLOT_BYTES;
        if (payloadBytes < 0 || perEntry <= 0 || available < perEntry) {
            throw new IllegalArgumentException("Invalid leaf layout");
        }
        return available / perEntry;
    }

    // Tu so la di nguoc len toi goc.
    // Danh sach sau cung duoc dao nguoc: [goc, ..., la].
    static List<Long> idealLevelPages(long records,
                                       int entriesPerLeaf,
                                       int fanout) {
        if (records <= 0 || entriesPerLeaf <= 0 || fanout < 2) {
            throw new IllegalArgumentException("Invalid tree parameters");
        }
        List<Long> levels = new ArrayList<>();
        long pages = ceilDiv(records, entriesPerLeaf);
        levels.add(pages);
        while (pages > 1) {
            pages = ceilDiv(pages, fanout);
            levels.add(pages);
        }
        Collections.reverse(levels);
        return levels;
    }

    static void show(int pageBytes, long records) {
        int maxKeys = maxInternalKeys(pageBytes);
        int fanout = maxKeys + 1;
        int leafMax = maxLeafEntries(pageBytes, RECORD_ID_BYTES);
        int leafExpected = Math.max(1, leafMax * 7 / 10);
        int leafWithPayload128 = maxLeafEntries(pageBytes, 128);
        List<Long> levels =
            idealLevelPages(records, leafExpected, fanout);

        System.out.println(
            (pageBytes / 1024) + " KiB:"
            + " maxInternalKeys=" + maxKeys
            + ", fanout=" + fanout
            + ", leafMax=" + leafMax
            + ", leaf~70%=" + leafExpected
            + ", leafWithPayload128=" + leafWithPayload128);
        System.out.println("  pages root->leaves = " + levels
            + ", levels = " + levels.size());
    }

    public static void main(String[] args) {
        long records = 10_000_000L;
        show(4 * 1024, records);
        show(8 * 1024, records);
        show(16 * 1024, records);
    }
}
```

Kết quả dự kiến:

```text
4 KiB: maxInternalKeys=141, fanout=142, leafMax=141, leaf~70%=98, leafWithPayload128=26
  pages root->leaves = [1, 6, 719, 102041], levels = 4
8 KiB: maxInternalKeys=287, fanout=288, leafMax=287, leaf~70%=200, leafWithPayload128=54
  pages root->leaves = [1, 174, 50000], levels = 3
16 KiB: maxInternalKeys=580, fanout=581, leafMax=580, leaf~70%=406, leafWithPayload128=109
  pages root->leaves = [1, 43, 24631], levels = 3
```

### Kiểm tra các hàm

**`maxInternalKeys`** trừ header và **con trỏ con đầu tiên** rồi chia phần còn lại cho mỗi nhóm một separator + một con trỏ + một slot:

\[
k_{\max}=\left\lfloor\frac{P-H-C}{K+C+S}\right\rfloor.
\]

**`maxLeafEntries`** trừ header và byte liên kết lá, rồi chia cho chi phí mỗi mục:

\[
L_{\max}=\left\lfloor\frac{P-H-N}{K+R+S}\right\rfloor.
\]

**`idealLevelPages`** bắt đầu bằng số lá, sau đó liên tiếp chia cho fan-out **tối đa** và làm tròn lên tới khi được một gốc. Danh sách được đảo ngược để in theo thứ tự gốc → lá.

**`ceilDiv`** tránh công thức `(n+d-1)/d` có thể tràn số ở những giá trị `long` lớn; nó tính phần nguyên và cộng thêm một khi còn dư.

### Những giới hạn của bộ ước lượng

1. **Không đo I/O vật lý**: không đọc file hay tương tác với đĩa.
2. **Không tính mức lấp đầy thực của nút trong**: dùng fan-out tối đa để tạo một phép ước lượng lạc quan về chiều cao.
3. **Không áp cận tối thiểu khi phân phối số con của một B+ tree thật**: số trang làm tròn lên chỉ cho biết quy mô lý tưởng, không phải một cấu trúc chèn/xóa cụ thể.
4. **Không tính byte dư của từng trang, nén hoặc khóa độ dài biến thiên**.
5. **Không tính chi phí lấy bản ghi từ `RID`** hoặc buffer pool.

Để đánh giá sản phẩm thật, cần dùng công cụ ước lượng như một bước đầu, sau đó đối chiếu bằng đặc tả trang, chỉ số hit cache, số page split, I/O và độ trễ đo được dưới workload dự kiến.

## 12. Cách lựa chọn kích thước trang theo workload

Một quy trình quyết định thực tế có thể chia thành các bước sau:

### Bước 1: Xác định mục tiêu chính

Các workload khác nhau ưu tiên những điều khác nhau:

| Workload | Điều cần xem kỹ |
| --- | --- |
| Tìm một khóa ngẫu nhiên với tần suất cao | Tỷ lệ cache hit ở lá, số tầng, độ trễ tải trang |
| Quét khoảng dài hoặc duyệt tăng dần | Số lá, thông lượng đọc, lượng byte chuyển, cache/prefetch |
| Chèn khóa ngẫu nhiên liên tục | Page split, cập nhật cha, lượng log và write amplification |
| Chèn theo thứ tự tăng | Hành vi lá ngoài cùng bên phải, tách trang, phân bổ vùng trống |
| Xóa nhiều và cập nhật khóa | Mượn/gộp, phân mảnh, chênh lệch mức đầy |
| Dữ liệu khóa hoặc payload rất dài | Sức chứa mỗi trang, overflow, chi phí so sánh/nén |
| Bộ nhớ đệm hạn chế | Số trang trong RAM, tần suất cache miss và mức đọc thừa |

### Bước 2: Lập bảng sức chứa cho vài cấu hình trang

Thử ít nhất một vài phương án mà **hệ quản trị hoặc thư viện thực sự hỗ trợ**, ví dụ 4/8/16 KiB. Với mỗi phương án, tính:

- `k_{\max}` và `F_{\max}` của nút trong.
- `L_{\max}` cho kiểu mục lá đang dùng.
- Số lá ở mức lấp đầy dự kiến.
- Số tầng ước tính và mức RAM cần cho các tầng trong.
- Số trang lá phải đi qua cho các truy vấn khoảng mẫu.

Nếu hệ thống chỉ hỗ trợ một kích thước trang cố định, việc chọn trang thực tế có thể không phải tùy chọn; khi đó cần tối ưu **cấu trúc khóa, nén, mức đầy, thiết kế chỉ mục** hoặc chọn hệ thống khác theo yêu cầu.

### Bước 3: Tách **I/O ngẫu nhiên** khỏi **thông lượng tuần tự**

- Một truy vấn điểm bị cache miss thường nhạy với **độ trễ truy cập ngẫu nhiên**.
- Quét nhiều lá liên tiếp quan tâm cả **thông lượng byte/giây**, prefetch và số trang được đọc.
- Ghi và tách trang quan tâm **chi phí ghi**, số trang dirty, WAL và cơ chế flush.

Không thể dùng một con số “trang lớn hơn nên ít I/O hơn” để tối ưu đồng thời tất cả các nhóm này.

### Bước 4: Tính chi phí cache

Ví dụ, với bộ nhớ đệm có chỗ dành cho **64 MiB** trang cùng kích thước, số trang tối đa (bỏ qua metadata quản lý) là:

| Kích thước trang | Số trang có thể chứa trong 64 MiB |
| --- | ---: |
| 4 KiB | 16.384 |
| 8 KiB | 8.192 |
| 16 KiB | 4.096 |

Trang lớn chứa nhiều mục hơn trên **mỗi trang**, nhưng số trang có thể cache giảm. Hiệu quả thực tế phụ thuộc tập mục được truy cập và tính cục bộ. Nếu truy vấn ngẫu nhiên chỉ lấy một mục trên mỗi trang, trang lớn có thể mang vào RAM nhiều byte ít dùng tới.

### Bước 5: Đo và chọn theo ràng buộc

Một bộ thử nghiệm tối thiểu nên quan sát:

- Độ trễ p50/p95/p99 cho tìm chính xác và truy vấn khoảng.
- Số lần cache hit/miss, trang đọc/ghi và byte đọc/ghi.
- Tần suất page split, merge, số lần thay đổi chiều cao.
- CPU dùng cho so sánh khóa, số trang dirty và lượng log.
- Dung lượng chỉ mục, số tầng cây và mức đầy trung bình của lá/nút trong.

Đánh giá cần có dữ liệu đại diện: phân bố khóa, tỷ lệ tìm/chèn/xóa, kích thước payload, tần suất truy vấn khoảng, mức RAM và thiết bị lưu trữ. Kết luận nên dựa trên **độ trễ và thông lượng đo được trong cùng điều kiện**, không chỉ dựa vào fan-out lý thuyết.

## 13. Những nhầm lẫn thường gặp

1. **“Kích thước nút càng lớn luôn càng tốt.”** Trang lớn có thể giảm chiều cao nhưng tăng lượng byte đọc/ghi và chi phí cache.
2. **“Fan-out là số khóa tối đa.”** Nút trong `k` separator có `k+1` con; fan-out là **số con**.
3. **“Một nút có thể dùng đủ `P` byte để lưu khóa.”** Phải chừa header, con trỏ, slot và metadata khác.
4. **“Nút trong và lá luôn chứa cùng số mục.”** Nút trong chứa separator + con trỏ, lá chứa mục dữ liệu hoặc `RID`; sức chứa có thể rất khác.
5. **“Lá chứa toàn bộ bản ghi trong mọi B+ tree.”** Một số lá chỉ giữ định danh/vị trí bản ghi.
6. **“`F_{\max}` bằng số nhánh trung bình.”** Mức lấp đầy thực tế có thể thấp hơn trần sức chứa.
7. **“Chọn trang 16 KiB sẽ giảm chiều cao một nửa so với 8 KiB.”** Chiều cao thay đổi theo logarit và làm tròn theo số tầng; nhiều cấu hình có cùng số tầng.
8. **“Số tầng bằng số lần đọc đĩa.”** Buffer pool có thể giữ một hoặc nhiều tầng, nên số I/O vật lý khác số nút đi qua.
9. **“Trang lớn có ít trang hơn nên chắc chắn đọc ít byte hơn.”** Quét 1.000 mục trong ví dụ 16 KiB có thể chuyển nhiều byte hơn phương án 8 KiB.
10. **“Đọc một mục từ lá chứa `RID` là đã đọc bản ghi thật.”** Có thể còn cần truy cập trang dữ liệu ngoài chỉ mục.
11. **“Fill factor 70% là bất biến của mọi B-tree.”** Đó là tham số/giả định lập kế hoạch; cận cân bằng của từng biến thể là chuyện khác.
12. **“Có thể bỏ chi phí tách trang khi phân tích chèn.”** Tách có thể sửa lá, cha, liên kết anh em, log và đôi khi cả gốc.
13. **“Khóa có độ dài biến thiên vẫn tính được một sức chứa chính xác bằng `K` trung bình.”** Giá trị trung bình chỉ phục vụ ước lượng, không bảo đảm vừa trang trong mọi trường hợp.
14. **“Mọi trang hệ quản trị đều bằng sector đĩa.”** Trang là đơn vị logic; thiết bị có thể dùng các kích thước vật lý khác.
15. **“Càng nhiều nút trong cache thì mọi truy vấn đều không cần đĩa.”** Lá và bản ghi thật vẫn có thể gây cache miss.
16. **“Chỉ cần phép tính sức chứa để chọn một page size.”** Cần thử nghiệm workload thật, gồm độ trễ, throughput, cache miss và write amplification.
17. **“Nếu giữ separator ngắn hơn khóa thật thì không cần quan tâm định tuyến.”** Nén/rút gọn phải bảo đảm quy tắc chọn con vẫn đúng.
18. **“Chọn trang nhỏ luôn cho CPU cache tốt hơn.”** Còn phụ thuộc cách truy cập, bố cục khóa, nén và tỷ lệ tìm/quét; không có bảo đảm tuyệt đối.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao trong hệ lưu trữ phân trang thường thiết kế một nút B+ tree vừa một trang?

**Đáp án:** Để một lần tải trang vào buffer pool có thể cung cấp các khóa và con trỏ cần xử lý tại nút. Đây là lựa chọn thiết kế phổ biến, không phải định luật bắt buộc mọi triển khai phải theo.

**Câu 2.** Nút trong có `k` separator thì có bao nhiêu con? Fan-out tối đa bằng bao nhiêu nếu chứa được `k_{\max}` separator?

**Đáp án:** Có `k+1` con; `F_{\max}=k_{\max}+1`.

**Câu 3.** Viết công thức giới hạn số separator khi trang có `P` byte, header `H`, khóa `K`, con trỏ `C` và slot `S` byte/mục.

**Đáp án:** `k_{\max}=floor((P-H-C)/(K+C+S))` theo bố cục cố định đã giả định.

**Câu 4.** Với `P=4096,H=128,K=16,C=8,S=4`, số separator và fan-out tối đa là bao nhiêu?

**Đáp án:** `floor(3960/28)=141` separator, tương ứng **142 con**.

**Câu 5.** Công thức sức chứa lá với liên kết `next` chiếm `N` byte và payload `R` byte/mục là gì?

**Đáp án:** `L_{\max}=floor((P-H-N)/(K+R+S))`, nếu mục có kích thước cố định và các chi phí đã được tính đúng.

**Câu 6.** Với trang 4 KiB, các tham số ví dụ và `RID` 8 byte, lá có tối đa bao nhiêu mục?

**Đáp án:** 141 mục theo mô hình trong bài.

**Câu 7.** Nếu payload mỗi mục tăng lên 128 byte trong cùng trang 4 KiB thì sức chứa lá trở thành bao nhiêu?

**Đáp án:** `floor(3960/148)=26` mục.

**Câu 8.** Vì sao không nên dùng `L_{\max}` làm số mục trung bình của mỗi lá?

**Đáp án:** Lá có thể còn khoảng trống do tách/gộp/chèn/xóa hoặc chính sách fill factor; mức đầy thực tế thường không bằng tối đa.

**Câu 9.** Với `L_{\max}=141` và giả định mức đầy 70%, bài dùng `L_{\text{eff}}` bằng bao nhiêu?

**Đáp án:** `floor(0.7×141)=98` mục/lá.

**Câu 10.** Vì sao trong mô hình 10 triệu mục, phương án 8 KiB và 16 KiB đều có thể có ba tầng?

**Đáp án:** Chiều cao là số nguyên và giảm theo logarit fan-out. Khi sức chứa đủ lớn, hai mức trang khác nhau vẫn có thể xếp toàn bộ lá dưới cùng số tầng nút trong.

**Câu 11.** Một đường tìm đi qua bốn nút nhưng ba nút trong đã được cache. Nếu lá chưa ở cache và giả định nạp mỗi nút từ một trang, có thể cần bao nhiêu lần nạp trang?

**Đáp án:** Có thể chỉ **một lần** nạp trang lá, không phải bốn lần; cũng có thể bằng không nếu lá đã được cache.

**Câu 12.** Với truy vấn quét 1.000 mục liên tiếp, vì sao số trang ít hơn chưa đủ chứng minh lượng byte đọc ít hơn?

**Đáp án:** Mỗi trang lớn hơn chứa nhiều byte; ví dụ 3 trang 16 KiB là 49.152 byte, nhiều hơn 5 trang 8 KiB là 40.960 byte trong phép tính minh họa.

**Câu 13.** Khi lá chỉ giữ `record_id`, tại sao truy vấn khoảng còn có thể phát sinh I/O ngoài chỉ mục?

**Đáp án:** Vì cần dùng `record_id` để lấy các bản ghi thật từ vùng lưu dữ liệu, trừ khi chỉ mục đã bao phủ đầy đủ dữ liệu cần truy vấn.

**Câu 14.** Ba tác động chính của tách một trang lá lên B+ tree là gì?

**Đáp án:** Phân phối mục giữa hai lá, cập nhật separator/con trỏ ở cha và sửa liên kết lá `next/prev`; có thể lan tách lên các tầng cao.

**Câu 15.** Trang 4 KiB giữ được tối đa bao nhiêu separator nếu separator dài 32 byte và các tham số khác là `H=128,C=8,S=4`?

**Đáp án:** `floor(3960/(32+8+4))=90` separator, tức tối đa 91 con.

**Câu 16.** Vì sao tham số `K` cố định không thể mô tả chính xác mọi trang chứa khóa chuỗi có độ dài biến thiên?

**Đáp án:** Vì mỗi khóa có `K_i` khác nhau, có thể có nén/căn chỉnh/slot directory; sức chứa phụ thuộc tổng byte thực tế, không chỉ một giá trị trung bình.

**Câu 17.** Trong mô hình 4 KiB với `n=10\,000\,000`, `L_{\text{eff}}=98` và `F_{\max}=142`, số lá xấp xỉ là bao nhiêu?

**Đáp án:** `ceil(10\,000\,000/98)=102\,041` lá.

**Câu 18.** Vì sao nên đo cả cache miss, số lần page split và lượng log khi thử thay đổi kích thước trang?

**Đáp án:** Vì fan-out và số tầng chỉ phản ánh một phần chi phí; trang lớn/nhỏ còn tác động đến cache, ghi và việc tái cấu trúc trong các lần chèn/xóa.

**Câu 19.** Có thể kết luận trang 16 KiB luôn tốt hơn trang 4 KiB cho tìm một khóa ngẫu nhiên không?

**Đáp án:** Không. Tỷ lệ cache hit ở lá, thời gian nạp trang, byte đọc thừa, CPU so sánh và thiết bị lưu trữ có thể khiến phương án nhỏ hơn phù hợp với workload nhất định.

**Câu 20.** Nếu hệ quản trị chỉ hỗ trợ trang cố định 8 KiB, có thể tiếp tục tối ưu fan-out bằng cách nào?

**Đáp án:** Có thể giảm kích thước separator nếu cấu trúc cho phép, dùng nén, điều chỉnh payload được lưu tại lá, thiết kế khóa/index phù hợp, và quản lý fill factor; tất cả cần tuân bố cục và khả năng thật của hệ thống.

**Điểm ghi nhớ:** **Kích thước trang quyết định sức chứa tối đa của nút** nhưng không quyết định một mình hiệu năng B-tree/B+ tree. Nút trong có `k` separator và `k+1` con; lá chứa mục dữ liệu với kích thước có thể rất khác con trỏ. **Trang lớn** thường tăng fan-out, giảm số lá/tầng; **trang nhỏ** có thể giảm byte đọc thừa và giúp cache linh hoạt hơn. Chi phí thực sự phải xét **số trang cache miss, số byte đọc/ghi, mức lấp đầy, page split, truy vấn điểm và quét khoảng**. Công thức giúp sàng lọc phương án; **workload và phép đo** mới giúp chọn cấu hình phù hợp.
