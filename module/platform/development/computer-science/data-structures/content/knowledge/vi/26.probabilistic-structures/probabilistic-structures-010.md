# Hợp nhất cấu trúc xác suất và điều kiện tương thích tham số

## 1. Vì sao phải hợp nhất các cấu trúc xác suất?

Một nền tảng xử lý sự kiện trên nhiều máy. Máy A nhận lượt truy cập từ khu vực phía Bắc, máy B nhận lượt truy cập từ khu vực phía Nam. Mỗi máy có một cấu trúc dữ liệu xác suất (*probabilistic data structure*) trong bộ nhớ để trả lời nhanh một câu hỏi:

- **Bloom filter:** khóa `x` có thể đã xuất hiện hay chưa?
- **Count-Min Sketch:** khóa `x` đã xuất hiện khoảng bao nhiêu lần?
- **HyperLogLog:** đã có khoảng bao nhiêu khóa **phân biệt**?

Thay vì gửi toàn bộ sự kiện hoặc tất cả khóa về máy trung tâm, ta muốn **hợp nhất** (*merge*) các cấu trúc nhỏ do mỗi máy tạo ra. Hợp nhất có thể giảm băng thông và bộ nhớ, nhưng chỉ đúng khi thao tác gộp phù hợp với **ý nghĩa dữ liệu** và **cấu hình của thuật toán**.

Chẳng hạn, Bloom filter hợp nhất bằng phép **OR** trên các bit, Count-Min Sketch cộng từng **bộ đếm**, còn HyperLogLog lấy **max** từng thanh ghi. Áp dụng sai phép toán hoặc gộp hai bộ phác thảo có hàm băm khác nhau có thể làm kết quả vô nghĩa.

Trong thiết kế cấu trúc dữ liệu, đây là một bài toán về **bất biến**, **phép toán hỗ trợ** và **độ phức tạp**: cần biết dữ liệu được mã hóa như thế nào trước khi kết hợp các trạng thái đã nén.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt hợp nhất **tập khóa**, **tổng tần suất** và **cardinality**.
2. Giải thích vì sao từng cấu trúc có phép hợp nhất riêng.
3. Kiểm tra tương thích về kích thước, thuật toán băm, seed, mã hóa khóa, phiên bản và ngữ nghĩa luồng.
4. Triển khai một lớp kiểm tra cấu hình trước khi hợp nhất.
5. Nhận ra các trường hợp không thể gộp trực tiếp, đặc biệt với Cuckoo filter.

## 2. Hợp nhất có nghĩa gì về mặt toán học?

Gọi `S(A)` là trạng thái sketch sau khi nhận dãy cập nhật `A`. Một phép hợp nhất `⊕` được thiết kế đúng cho mô hình cập nhật tương ứng khi trạng thái sau gộp biểu diễn cùng thông tin như việc xử lý chung các cập nhật:

```text
S(A) ⊕ S(B)  ≈  S(A nối B)
```

Ký hiệu `≈` có nghĩa hai trạng thái mang **cùng ngữ nghĩa ước lượng**. Với một số cấu trúc và cùng cấu hình, biểu diễn bên trong thực sự giống nhau; với cấu trúc khác, thao tác hợp nhất phức tạp hơn hoặc có thể thất bại.

Điều quan trọng là biết `A` và `B` đại diện cho cái gì:

| Mục tiêu | Cách hiểu khi hợp nhất |
|---|---|
| Đã từng thấy khóa `x` ở bất kỳ máy nào? | Hợp các tập khóa |
| Đã xử lý bao nhiêu sự kiện mang khóa `x`? | Cộng số lần xuất hiện từ các **phần sự kiện không trùng** |
| Có bao nhiêu khóa duy nhất trên toàn hệ thống? | Ước lượng cardinality của **hợp các tập khóa** |

Ví dụ, máy A nhận `(u1, u1, u2)`, máy B nhận `(u2, u3)`. Có **5 lượt sự kiện** nhưng chỉ **3 khóa phân biệt** `{u1, u2, u3}`:

```text
Tần suất trên A: u1 = 2, u2 = 1
Tần suất trên B: u2 = 1, u3 = 1
Tổng tần suất:    u1 = 2, u2 = 2, u3 = 1
Hợp tập khóa:     {u1, u2, u3}  --> cardinality = 3
```

Do đó, **phép cộng tần suất** và **phép hợp tập khóa** trả lời hai câu hỏi khác nhau.

### Tính chất của phép hợp nhất

- **Giao hoán:** `A ⊕ B = B ⊕ A`, cho phép máy gửi kết quả theo bất kỳ thứ tự nào.
- **Kết hợp:** `(A ⊕ B) ⊕ C = A ⊕ (B ⊕ C)`, cho phép dựng cây tổng hợp phân tán.
- **Lũy đẳng:** `A ⊕ A = A`, cho phép gộp lại cùng một trạng thái mà không đổi kết quả.

Bloom filter dùng OR và HyperLogLog dùng max có cả ba tính chất trên, nếu cấu hình giống nhau. Count-Min Sketch dùng cộng nên có giao hoán và kết hợp, **nhưng không lũy đẳng**: `A + A` làm số đếm tăng gấp đôi. Sự khác biệt này rất quan trọng trong hệ thống có cơ chế gửi lại dữ liệu khi xảy ra lỗi mạng.

## 3. Ma trận phép hợp nhất

| Cấu trúc | Trạng thái lưu | Phép hợp nhất thích hợp | Ngữ nghĩa | Lưu ý chính |
|---|---|---|---|---|
| Bloom filter cơ bản | Mảng `m` bit | OR từng bit | Kiểm tra thành viên trên hợp tập khóa | Dương tính giả có thể tăng |
| Counting Bloom filter | Mảng bộ đếm | Cộng từng ô, khi gộp các luồng cập nhật | Tổng số lần chèn đã biểu diễn | Không dùng để khử trùng bản sao; phải chống tràn |
| Count-Min Sketch | Bảng `d × w` bộ đếm | Cộng từng ô | Tổng tần suất từ các luồng | Trùng sự kiện sẽ đếm hai lần |
| HyperLogLog | `2^p` thanh ghi | Max từng ô | Cardinality của hợp các tập | Không cộng hai ước lượng |
| Cuckoo filter | Fingerprint trong bucket | Không có phép OR/cộng/max trực tiếp phổ quát | Kiểm tra thành viên gần đúng | Cần thuật toán tái chèn phù hợp, có thể thất bại |

**Không thể lấy phép gộp của cấu trúc này áp dụng cho cấu trúc khác.** Dù Bloom filter và HLL đều diễn tả “hợp tập”, biểu diễn trạng thái và quy tắc cập nhật của chúng hoàn toàn khác nhau.

## 4. Điều kiện tương thích trước khi hợp nhất

Hình dạng mảng giống nhau chỉ là **một** điều kiện. Hai sketch cần cùng hiểu mỗi khóa, mỗi ô và mỗi giá trị được lưu.

### 4.1. Kích thước và bố cục

| Cấu trúc | Các tham số cốt lõi cần kiểm tra |
|---|---|
| Bloom filter | `m` bit, số hàm băm `k`, thứ tự bit, cách ánh xạ hash vào các bit |
| Counting Bloom filter | `m` bộ đếm, `k` hàm băm, kiểu/giới hạn bộ đếm, cách băm |
| Count-Min Sketch | `d` hàng, `w` cột, thứ tự hàng, cách tính `h_i(x)` |
| HyperLogLog | `p` (tức `m = 2^p`), độ dài hash, cách chia bit, cách tính `ρ`, ý nghĩa thanh ghi |
| Cuckoo filter | Số bucket, số ô/bucket, độ dài fingerprint, phép tính hai bucket và cách xử lý stash |

Ví dụ hai Count-Min Sketch đều có `1.000` ô nhưng một bảng là `10 × 100`, bảng còn lại là `5 × 200`: cộng theo chỉ số phẳng sẽ ghép các ô không cùng ý nghĩa.

Với HLL, có những thuật toán **giảm độ chính xác** từ `p` lớn xuống `p` nhỏ một cách có kiểm soát, nhưng việc này phải tính lại vị trí và giá trị rank theo quy tắc đúng. Không được tùy tiện cắt mảng thanh ghi rồi lấy max.

### 4.2. Hash, seed và mã hóa khóa

Hai sketch cùng kích thước vẫn không tương thích nếu chúng dùng hash hoặc seed khác nhau. Phải thống nhất ít nhất:

- Thuật toán băm và **phiên bản** hiện thực, seed hoặc khóa bí mật, cách tạo nhiều hàm băm và các tiền tố tách miền băm.
- Cách chuyển khóa sang bytes: UTF-8, chuẩn hóa Unicode, phân biệt chữ hoa/thường, định dạng số, thứ tự trường và delimiter.
- Cách ánh xạ đầu ra hash đến vị trí trong mảng, quy ước bit cao/thấp, cách tính rank hay fingerprint.

Ví dụ chuỗi `"café"` có thể được mã hóa ở dạng Unicode dựng sẵn hoặc dạng ký tự nền cộng dấu. Nếu một máy chuẩn hóa NFC còn máy kia không chuẩn hóa, chúng có thể băm hai chuỗi hiển thị giống nhau thành hai giá trị khác nhau. HLL sẽ có khả năng đếm chúng thành hai khóa; Bloom filter và CMS cũng mất tính tương thích.

Seed nên được xác định theo **định danh phiên bản** trong metadata. Không nên ghi trực tiếp khóa băm bí mật vào file sketch công khai.

### 4.3. Cùng ngữ nghĩa dữ liệu

Cần kiểm tra **đơn vị và phạm vi thời gian** của dữ liệu trước khi gộp:

- Hai Count-Min Sketch có cùng đơn vị lượt nhưng chứa **cùng một bản sao sự kiện** thì cộng sẽ làm tần suất sai. Cần phân vùng các sự kiện không trùng nhau hoặc cơ chế khử trùng.
- Hai HLL đếm khóa người dùng có thể gộp dù có người xuất hiện ở cả hai máy, vì cùng khóa có cùng hash và phép max không đếm trùng.
- Sketch đếm `user_id` không thể gộp có ý nghĩa với sketch đếm `session_id`, dù tham số kỹ thuật giống nhau.
- Sketch theo từng ngày có thể gộp thành tuần nếu thời gian và ngữ nghĩa sự kiện phù hợp; nhưng không được gắn nhãn “tuần này” cho kết quả chứa cả ngày cũ hoặc bị thiếu shard.

Ngoài ra phải thống nhất mô hình cập nhật (*chỉ thêm*, cập nhật âm, số đếm có trọng số), cách xử lý tràn bộ đếm, quy tắc xóa, phiên bản thuật toán và định dạng serialization.

## 5. Bloom filter: phép OR cho hợp tập khóa

Bloom filter gồm `m` bit ban đầu bằng `0` và `k` hàm băm. Khi thêm khóa `x`, đặt các bit `h_1(x), …, h_k(x)` bằng `1`. Tra cứu trả về “chắc chắn không” nếu có một bit bằng `0`, còn nếu tất cả là `1` thì trả về “có thể có”.

Giả sử hai Bloom filter `B_A` và `B_B` có **cùng `m`, `k` và cách băm**. Lấy OR từng bit:

```text
B_merged[j] = B_A[j] OR B_B[j]     với j = 0..m-1

Ví dụ:
B_A = 1 0 1 0 0 1 0 0
B_B = 0 1 1 0 1 0 0 0
OR  = 1 1 1 0 1 1 0 0
```

Kết quả đúng bằng mảng bit nhận được nếu lần lượt thêm các khóa của **cả hai tập** vào một Bloom filter cùng cấu hình. OR là lũy đẳng: nếu nhận lại `B_A` và OR thêm lần nữa, kết quả không đổi.

**Bất biến thành viên:** nếu khóa `x` thật sự nằm trong A hoặc B, tất cả các bit cần thiết của `x` vẫn bằng `1` sau phép OR. Do đó không phát sinh âm tính giả do chính thao tác gộp, miễn là hai filter ban đầu đúng và cùng cấu hình.

Tuy nhiên, khi số khóa phân biệt được biểu diễn tăng, mật độ bit `1` tăng nên **tỷ lệ dương tính giả thường tăng**. Với khoảng `n` khóa phân biệt, một ước lượng thường dùng là:

```text
P(false positive) ≈ (1 - exp(-k × n / m))^k
```

Đây là xấp xỉ dưới giả định băm phân bố tốt, không phải bảo đảm tuyệt đối. Nếu OR nhiều filter đến khi gần như mọi bit bằng `1`, filter hầu như không còn ích lợi sàng lọc.

**Không suy ra giao tập bằng phép AND một cách chính xác.** AND bit của hai Bloom filter không tạo đúng trạng thái Bloom filter của `A ∩ B`: những bit do các khóa khác nhau đặt vẫn có thể cùng bằng `1`. AND có thể dùng cho một số mục đích sàng lọc đặc biệt, nhưng không được coi là tính giao chính xác hoặc lấy trực tiếp số bit `1` để suy ra số khóa chung.

## 6. Count-Min Sketch: cộng từng bộ đếm để cộng tần suất

Count-Min Sketch (CMS) có `d` hàng và `w` cột. Mỗi lần thêm khóa `x` với trọng số dương `c`, mỗi hàng tăng một ô `C[i][h_i(x)]` thêm `c`. Truy vấn lấy giá trị nhỏ nhất của các bộ đếm tương ứng:

```text
estimate(x) = min_i C[i][h_i(x)]
```

Nếu hai máy dùng **cùng `d`, `w` và toàn bộ họ hàm băm**, phép gộp của CMS là:

```text
C_merged[i][j] = C_A[i][j] + C_B[i][j]
```

Vì phép tăng bộ đếm là phép cộng, trạng thái gộp giống với việc phát lần lượt tất cả cập nhật từ hai luồng vào cùng CMS. Truy vấn sau gộp ước lượng **tần suất tổng**, có thể cao hơn số thực vì các khóa va chạm.

Nếu `u2` xuất hiện 2 lần ở máy A và 5 lần ở máy B trong **các sự kiện không trùng**, tần suất mục tiêu là `7`. Ta không thể lấy `max(C_A, C_B)` để thay phép cộng, vì nó sẽ bỏ sót phần đóng góp của một máy.

CMS có bảo đảm sai số thường dùng, dưới các giả định về hash và chỉ có cập nhật dương:

```text
f(x) ≤ estimate(x) ≤ f(x) + εN
với xác suất ít nhất 1 − δ

w = ceil(e/ε),     d = ceil(ln(1/δ))
```

Khi gộp, `N = N_A + N_B` là **tổng trọng số các cập nhật được cộng**. Do đó biên sai số cộng `εN` cũng có thể tăng. Phép cộng bộ đếm không tự làm thay đổi `w` hay `d`, nhưng nếu hệ thống gộp cùng một shard hai lần, nó **đếm trùng dữ liệu**. Lưu `shard_id`, `window_id` và định danh bản snapshot/batch để tránh gộp lại những cập nhật đã tính.

**Lưu ý:** không cộng các ô của hai CMS có thứ tự hàng hoặc seed hash khác nhau. Một giá trị ở cùng chỉ số mảng khi ấy có thể biểu diễn các tập khóa khác nhau.

## 7. HyperLogLog: lấy max để ước lượng hợp tập phân biệt

HyperLogLog (HLL) dùng `m = 2^p` thanh ghi `M[j]`. Sau khi băm khóa, thuật toán chọn một thanh ghi `j` và cập nhật `M[j] = max(M[j], ρ)`, với `ρ` là vị trí bit `1` đầu tiên trong phần còn lại của giá trị băm.

Đối với hai HLL tương thích:

```text
M_merged[j] = max(M_A[j], M_B[j])     với j = 0..m-1

Ví dụ:
M_A    = [2, 0, 4, 1]
M_B    = [1, 3, 4, 0]
M_hợp  = [2, 3, 4, 1]
```

Mỗi thanh ghi giữ cực đại từ hai luồng, giống như xử lý tất cả khóa của hai luồng vào cùng HLL. Việc thêm một khóa đã có không đổi trạng thái; phép max **lũy đẳng**, nên gộp lại một bản HLL không làm số khóa phân biệt tăng thêm.

**Không cộng hai con số ước lượng cardinality.** Ví dụ máy A thấy `{u1,u2,u3}` và máy B thấy `{u2,u3,u4}`: tổng số khóa phân biệt của hợp tập là `4`, không phải `3+3=6`. Phải gộp **các thanh ghi trước**, sau đó mới chạy thuật toán ước lượng trên trạng thái gộp.

Khi dùng dạng HLL cổ điển, độ lệch chuẩn tương đối gần đúng là:

```text
RSE ≈ 1,04 / sqrt(m)
```

Ví dụ `p = 14` cho `m = 16.384` thanh ghi và RSE xấp xỉ `0,81%` trong vùng hoạt động phù hợp. Đó là **độ phân tán thống kê**, không phải cam kết mọi ước lượng đều sai dưới `0,81%`. HLL++ có thể dùng hiệu chỉnh sai lệch và biểu diễn thưa; gộp giữa những định dạng hoặc phiên bản khác nhau chỉ an toàn khi thư viện công bố quy tắc chuyển đổi đúng.

Các HLL phải dùng cùng hash, seed, độ dài hash, cách chia bit, `p` và ngữ nghĩa thanh ghi. Nếu `p` khác nhau, cần một thủ tục **downsample hợp lệ** trước khi gộp; việc cắt hoặc chép thẳng thanh ghi là sai.

## 8. Counting Bloom filter và Cuckoo filter: các ngoại lệ quan trọng

### Counting Bloom filter

Counting Bloom filter thay mỗi bit bằng bộ đếm. Nếu hai cấu trúc ghi nhận **các lượt chèn không trùng nhau**, có cùng số bộ đếm, hàm băm, seed và kiểu số, ta có thể **cộng** các bộ đếm để phản ánh toàn bộ lượt chèn:

```text
count_merged[j] = count_A[j] + count_B[j]
```

Lợi thế là có thể hỗ trợ giảm bộ đếm khi **biết chắc** một lần chèn tương ứng cần được xóa. Nhưng điều này đòi hỏi quản lý ngữ nghĩa lượt chèn/lượt xóa và chống tràn bộ đếm. Nếu cùng một bản sao dữ liệu được đưa vào cả hai nhánh, cộng trực tiếp tạo số đếm dư. Dùng phép `max` cũng không tương đương với cộng luồng cập nhật và có thể làm phép xóa về sau không còn đúng.

### Cuckoo filter

Cuckoo filter lưu **fingerprint** trong các bucket; mỗi fingerprint được phép nằm tại một trong hai bucket xác định từ hash của khóa và fingerprint. Vì cấu trúc chịu ràng buộc sức chứa từng bucket nên:

- **Không có phép OR, cộng hoặc max từng ô** tương đương với gộp hai tập khóa.
- Không thể ghép hai mảng bucket cạnh nhau rồi mặc định vị trí tìm kiếm vẫn đúng; số bucket và cách tính vị trí đã thay đổi.
- Cách đơn giản và chắc chắn về mặt thiết kế là **xây lại filter từ khóa gốc**, với cùng ngữ nghĩa tập, cấu hình mới có đủ sức chứa và xử lý lỗi chèn.
- Một triển khai chuyên biệt có thể tái chèn fingerprint từ các bucket cũ nếu giữ đúng phép tính vị trí thay thế và cấu hình tương thích. Tuy nhiên, nó phải xử lý trùng fingerprint, giới hạn dung lượng, chèn thất bại, xóa và tính nhất quán; không phải chức năng merge có sẵn trong mọi thư viện.

Điểm khác biệt nằm ở bất biến phân bố fingerprint: hai filter có thể đều hợp lệ riêng lẻ nhưng các phần tử sau khi đặt chung lại cạnh tranh những bucket đã đầy. Nếu di chuyển thất bại và bỏ mất fingerprint, filter có thể phát sinh âm tính giả.

## 9. Ví dụ hệ thống: tổng hợp thống kê từ hai shard

Hãy xét hai luồng **không trùng sự kiện**:

```text
Shard A: [u1, u1, u2]
Shard B: [u2, u2, u3]

Số lượt toàn hệ thống:       6
Số lượt của u1:             2
Số lượt của u2:             3
Số lượt của u3:             1
Số khóa phân biệt:          3
```

Ta dùng ba cấu trúc chung cấu hình:

| Câu hỏi sau khi gộp | Dùng cấu trúc | Gộp ra sao? | Diễn giải kết quả |
|---|---|---|---|
| `u3` có thể từng xuất hiện? | Bloom filter | OR bit | “Có thể có”; cần đối chiếu nguồn chính xác để khẳng định |
| `u2` xuất hiện khoảng bao nhiêu lần? | Count-Min Sketch | Cộng bộ đếm | Ước lượng ít nhất `3` trong mô hình chỉ thêm |
| Có bao nhiêu người dùng duy nhất? | HyperLogLog | Max thanh ghi | Ước lượng quanh `3` |

Nếu shard B là **bản phát lại** của chính shard A, mục tiêu phải được xác định lại: CMS cộng hai trạng thái sẽ đếm cả sự kiện phát lại, còn Bloom OR và HLL max không đổi trạng thái đối với các khóa trùng. Không thể dùng tính lũy đẳng của HLL để kết luận việc đếm tổng sự kiện cũng đã khử trùng.

## 10. Ví dụ Python: kiểm tra metadata rồi mới merge

Đoạn mã minh họa dưới đây tập trung vào **hợp nhất các trạng thái đã được tạo**, không cài đặt đầy đủ hàm thêm/truy vấn của từng cấu trúc. Để dễ nhìn, Bloom filter được biểu diễn bằng danh sách `0/1` thay vì mảng bit nén; CMS được trải phẳng thành `d×w` bộ đếm; HLL chứa các thanh ghi theo thứ tự chỉ số. Với thư viện thực, metadata cần được lưu và kiểm chứng cùng định dạng dữ liệu.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Spec:
    kind: str                # "bloom", "cms", "hll"
    shape: tuple             # bloom:(m,k), cms:(d,w), hll:(p,)
    hash_id: str             # thuat toan + phien ban
    seed_id: str             # dinh danh seed, khong chua secret
    key_codec: str           # quy uoc chuan hoa va ma hoa khoa
    format_version: int = 1


@dataclass
class Sketch:
    spec: Spec
    values: list[int]        # dai theo so bit/counter/register


def required_length(spec):
    if spec.kind == "bloom":
        m, k = spec.shape
        if m <= 0 or k <= 0:
            raise ValueError("Bloom: m va k phai duong")
        return m
    if spec.kind == "cms":
        depth, width = spec.shape
        if depth <= 0 or width <= 0:
            raise ValueError("CMS: depth va width phai duong")
        return depth * width
    if spec.kind == "hll":
        (p,) = spec.shape
        if not (4 <= p <= 16):
            raise ValueError("HLL: p ngoai pham vi vi du")
        return 1 << p
    raise ValueError("Loai sketch khong duoc ho tro")


def merge(a, b):
    # So sanh toan bo giao uoc hash, seed, codec, shape, version.
    if a.spec != b.spec:
        raise ValueError("Khong tuong thich tham so / metadata")

    n = required_length(a.spec)
    if len(a.values) != n or len(b.values) != n:
        raise ValueError("Du lieu khong khop shape")
    if any(not isinstance(v, int) or v < 0
           for v in a.values + b.values):
        raise ValueError("Gia tri sketch khong hop le")

    if a.spec.kind == "bloom":
        if any(v not in (0, 1) for v in a.values + b.values):
            raise ValueError("Bloom chi gom cac bit 0/1")
        output = [x | y for x, y in zip(a.values, b.values)]
    elif a.spec.kind == "cms":
        output = [x + y for x, y in zip(a.values, b.values)]
    else:  # hll
        output = [max(x, y) for x, y in zip(a.values, b.values)]

    return Sketch(a.spec, output)  # tao ban moi, khong sua input


base = dict(hash_id="hash-v1", seed_id="seed-2026",
            key_codec="utf8-nfc-v1")

bloom = Spec(kind="bloom", shape=(8, 2), **base)
a = Sketch(bloom, [1, 0, 1, 0, 0, 1, 0, 0])
b = Sketch(bloom, [0, 1, 1, 0, 1, 0, 0, 0])
assert merge(a, b).values == [1, 1, 1, 0, 1, 1, 0, 0]

cms = Spec(kind="cms", shape=(2, 3), **base)
a = Sketch(cms, [1, 2, 0, 2, 0, 1])
b = Sketch(cms, [0, 3, 1, 1, 2, 0])
assert merge(a, b).values == [1, 5, 1, 3, 2, 1]

hll = Spec(kind="hll", shape=(4,), **base)
a = Sketch(hll, [2, 0, 4, 1] + [0] * 12)
b = Sketch(hll, [1, 3, 4, 0] + [0] * 12)
assert merge(a, b).values[:4] == [2, 3, 4, 1]

wrong_seed = Spec(kind="hll", shape=(4,),
                  hash_id="hash-v1", seed_id="seed-other",
                  key_codec="utf8-nfc-v1")
try:
    merge(a, Sketch(wrong_seed, [0] * 16))
    raise AssertionError("Phai tu choi khac seed")
except ValueError:
    pass
```

Trong ví dụ, phép kiểm tra `a.spec == b.spec` là hàng rào đầu tiên, nhưng còn phụ thuộc việc các hệ thống **khai báo metadata trung thực và đầy đủ**. Khi đưa vào sản xuất, cần đối chiếu định dạng và phạm vi giá trị của bộ đếm, tràn số, checksum, cách chia bit HLL, quyền truy cập và phiên bản chuyển đổi dữ liệu. Ví dụ chỉ minh họa đại số gộp; các mảng dữ liệu `0/1` hoặc thanh ghi được dựng sẵn, không đại diện cho một bộ dữ liệu sự kiện cụ thể.

## 11. Quy trình hợp nhất an toàn trong hệ thống phân tán

Một thiết kế thực tế có thể tổ chức theo trình tự:

1. **Định nghĩa câu hỏi.** Cần hợp tập khóa, tổng số sự kiện hay cardinality? Chọn đúng cấu trúc và phép gộp.
2. **Đóng băng thông số.** Ghi vào metadata loại thuật toán, kích thước, hash/seed, mã hóa khóa, kiểu dữ liệu, phiên bản và thời gian/phân vùng nguồn.
3. **Xác thực đầu vào.** Kiểm tra số ô, kích thước payload, phạm vi bộ đếm/thanh ghi, version và checksum trước khi giải mã hay gộp.
4. **Kiểm tra luồng dữ liệu.** Với phép cộng CMS/Counting Bloom, xác định các sự kiện có trùng nhau do retry, replication hoặc vùng thời gian chồng lấn hay không.
5. **Hợp nhất theo phép toán.** OR cho Bloom, cộng cho CMS, max cho HLL; dùng logic chuyên biệt hoặc xây lại đối với Cuckoo.
6. **Kiểm tra kết quả.** Đối chiếu trên mẫu dữ liệu có kết quả chính xác, theo dõi tỷ lệ dương tính giả, lỗi ước lượng, mức lấp đầy và nguy cơ tràn.

Tránh xem `schema_version` là chi tiết trang trí. Nếu thay hàm băm hoặc thay quy tắc mã hóa khóa, dù mảng vẫn có cùng kích thước, sketch cũ và mới có thể **không còn gộp được**. Việc nâng cấp cần xây lại từ dữ liệu gốc hoặc dùng một thủ tục chuyển đổi đã được chứng minh đúng.

### Kiểm tra bất biến bằng ví dụ nhỏ

Có thể kiểm tra tính hợp nhất trên tập dữ liệu đã biết, chẳng hạn:

```text
events_A = [u1, u1, u2]
events_B = [u2, u2, u3]

Tạo sketch_A từ events_A
Tạo sketch_B từ events_B
Tạo sketch_all từ events_A nối events_B

Bloom:   OR(A,B) == sketch_all theo từng bit
CMS:     ADD(A,B) == sketch_all theo từng bộ đếm
HLL:     MAX(A,B) == sketch_all theo từng thanh ghi
```

So sánh **trạng thái** như trên là kiểm tra phù hợp khi mọi sketch cùng cấu hình và dùng thuật toán cập nhật xác định. Sau đó mới kiểm tra câu trả lời ước lượng và mức sai số bằng nhiều tập dữ liệu đại diện. Một phép kiểm tra bổ sung quan trọng là gộp cùng snapshot hai lần: Bloom và HLL phải giữ nguyên, còn CMS sẽ tăng bộ đếm, do đó tầng điều phối phải tránh tính lại snapshot.

## 12. Bài tập tự kiểm tra

**Câu 1.** Hai Bloom filter cùng `m = 8` và `k = 2` có mảng bit `10100100` và `01101000`. Mảng gộp là gì? Phép gộp có lũy đẳng không?

**Đáp án:** OR cho `11101100`. Có, vì `b OR b = b` với mọi bit.

**Câu 2.** Hai CMS cùng kích thước `3 × 64` nhưng dùng seed hash khác nhau. Có thể cộng từng ô không?

**Đáp án:** Không. Dù kích thước bằng nhau, cùng khóa không nhất thiết chọn cùng cột trên hai bảng. Cần cùng họ hash/seed và cách biểu diễn khóa.

**Câu 3.** HLL của hai shard ước lượng lần lượt `1.000` và `1.200` khóa phân biệt. Có thể kết luận hợp có `2.200` khóa không?

**Đáp án:** Không. Hai shard có thể chia sẻ khóa và cả hai con số đều là ước lượng. Cần lấy max từng thanh ghi của hai HLL tương thích rồi ước lượng cardinality trên sketch đã gộp.

**Câu 4.** Một batch sự kiện được gửi lại sau timeout. Nếu máy tổng hợp cộng CMS của batch này hai lần, điều gì xảy ra? HLL max cùng snapshot hai lần thì sao?

**Đáp án:** CMS sẽ đếm các lượt sự kiện của batch hai lần; HLL max lại cùng snapshot không đổi thanh ghi. Đây là sự khác biệt về tính lũy đẳng.

**Câu 5.** Vì sao không thể gộp hai Cuckoo filter bằng OR toàn bộ byte của chúng?

**Đáp án:** Byte lưu fingerprint và vị trí trong các bucket, không phải tập bit biểu diễn thành viên như Bloom. OR byte có thể biến fingerprint thành giá trị khác, phá quy tắc hai bucket và tạo âm tính giả.

**Câu 6.** Hai sketch có cùng số ô, cùng seed và cùng thuật toán hash, nhưng một hệ thống chuẩn hóa Unicode NFC và hệ còn lại giữ nguyên bytes. Đã tương thích chưa?

**Đáp án:** Chưa. Cùng khóa hiển thị có thể tạo bytes khác nhau. Cần thống nhất cách biểu diễn và chuẩn hóa khóa trước khi băm.

Hợp nhất cấu trúc xác suất không phải thao tác nối mảng thông thường. Muốn chọn phép gộp đúng, trước hết cần nắm **bất biến và ngữ nghĩa của phép cập nhật**, sau đó kiểm tra **đầy đủ tham số tương thích**. Khi những điều kiện này được giữ ổn định, Bloom filter, Count-Min Sketch và HyperLogLog mới có thể tổng hợp dữ liệu phân tán với chi phí nhỏ, đáp ứng đúng bài toán kiểm tra thành viên, ước lượng tần suất hoặc đếm phần tử phân biệt.
