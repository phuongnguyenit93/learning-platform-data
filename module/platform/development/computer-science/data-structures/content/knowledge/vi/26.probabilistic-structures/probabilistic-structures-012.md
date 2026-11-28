# Đánh giá sai số, mức tin cậy và tác động đến ứng dụng

## 1. Đúng theo nghĩa nào khi dùng cấu trúc dữ liệu xác suất?

Trong hệ thống theo dõi lượt truy cập, một câu hỏi có thể là “người dùng `x` đã xuất hiện chưa?”, “`x` xuất hiện mấy lần?” hoặc “hôm nay có bao nhiêu người dùng phân biệt?”. Ba câu hỏi dẫn đến ba nhóm cấu trúc khác nhau:

| Nhu cầu | Cấu trúc thường dùng | Ý nghĩa của kết quả |
|---|---|---|
| Kiểm tra thành viên gần đúng | Bloom filter, Cuckoo filter | “Chắc chắn không” hoặc “có thể có” |
| Ước lượng tần suất của một khóa | Count-Min Sketch (CMS) | Số đếm thường **không thấp hơn** giá trị thực trong mô hình chỉ thêm |
| Ước lượng số khóa phân biệt | HyperLogLog (HLL) | Giá trị gần đúng, có thể cao hơn **hoặc** thấp hơn thực tế |
| Cần kết quả chính xác | `set`, `map`, chỉ mục cơ sở dữ liệu | Giá trị đúng theo trạng thái và quy tắc khóa của nguồn dữ liệu |

Trong chương **Cấu trúc xác suất** của nền tảng cấu trúc dữ liệu, không nên xem “xác suất” là một mức sai số chung cho mọi thuật toán. Mỗi cấu trúc có **biến cố lỗi**, **đơn vị sai số** và **điều kiện bảo đảm** riêng.

**Ba câu hỏi phải được trả lời trước khi chọn cấu trúc:**

1. **Sai theo hướng nào?** Một bộ lọc có thể trả về “có” khi khóa vắng mặt; CMS có thể đếm dư; HLL có thể ước lượng lệch cả hai phía.
2. **Sai bao nhiêu?** Đơn vị sai số là tỷ lệ truy vấn, số lượt cập nhật hay phần trăm của cardinality?
3. **Với xác suất và điều kiện gì?** Bảo đảm phụ thuộc cách băm, kích thước cấu trúc, mô hình cập nhật, số truy vấn và tính nhất quán của hệ thống.

Bài này hướng dẫn cách biến các bảo đảm toán học thành phép đo thực nghiệm và quyết định kiến trúc: cấp phát bộ nhớ, kiểm soát truy vấn cơ sở dữ liệu, chọn ngưỡng cảnh báo và xử lý khi kết quả chưa đủ chắc chắn.

## 2. Tách sai số thuật toán khỏi lỗi vận hành

Giả sử bộ lọc được xây dựng từ tập khóa `S`. Một Bloom filter đúng, chỉ thêm, luôn có tất cả các bit cần thiết của mỗi khóa đã chèn bằng `1`. Vì thế nó không tạo âm tính giả đối với **những khóa được chèn thành công**. Nhưng nếu cơ sở dữ liệu chứa khóa vừa được ghi mà filter chưa được cập nhật, filter có thể trả về “không có” dù khóa thực sự tồn tại trong cơ sở dữ liệu.

Hai lớp bảo đảm khác nhau:

- **Đúng đắn bên trong cấu trúc:** các bất biến của thuật toán được giữ; mọi thao tác chèn đã báo thành công; bộ đếm không tràn; không có xóa nhầm.
- **Đúng đắn so với nguồn sự thật:** filter/sketch bao phủ đúng tập khóa, sự kiện, khoảng thời gian và phiên bản dữ liệu mà ứng dụng đang hỏi.

Một kết quả “không có” chỉ được dùng để bỏ qua tra cứu chính xác khi **cả hai lớp bảo đảm** đều đạt yêu cầu. Đánh giá sai số cần xem xét lỗi thuật toán **và** các rủi ro như cập nhật bất đồng bộ, shard bị thiếu, replay sự kiện, thay hash seed, cửa sổ thời gian sai và tranh chấp khi nhiều luồng ghi đồng thời.

## 3. Đo bộ lọc thành viên: FP, FN, FPR và độ chính xác dương tính

Cho một tập khóa đúng `S` được xác nhận bằng nguồn chính xác. Mỗi truy vấn có hai trạng thái thật (khóa có/không có) và hai trạng thái filter (có thể có/chắc chắn không):

| Trạng thái thật | Filter trả lời “có thể có” | Filter trả lời “không” |
|---|---|---|
| Khóa có trong `S` | **TP:** dương tính đúng | **FN:** âm tính giả |
| Khóa không có trong `S` | **FP:** dương tính giả | **TN:** âm tính đúng |

Từ đó định nghĩa:

```text
FPR = FP / (FP + TN)        // tỷ lệ dương tính giả trong các truy vấn âm
FNR = FN / (FN + TP)        // tỷ lệ âm tính giả trong các truy vấn dương
TPR = TP / (TP + FN)        // độ nhạy, = 1 - FNR
PPV = TP / (TP + FP)        // precision của câu trả lời "có thể có"
```

Chỉ tính một tỷ lệ khi mẫu số khác `0`. Với Bloom filter cơ bản được duy trì đúng, `FNR = 0` đối với tập đã được biểu diễn là **bảo đảm của thuật toán**, còn FPR có thể lớn hơn `0`. Cuckoo filter cũng có thể sinh FP do trùng fingerprint, nhưng phải thêm điều kiện xóa an toàn và xử lý đúng các lần chèn thất bại để tránh FN.

**Không đánh đồng FPR với PPV.** FPR là xác suất filter báo có khi khóa thực tế không tồn tại; PPV là xác suất một kết quả “có thể có” thực sự thuộc tập. PPV còn phụ thuộc tỷ lệ khóa thật sự tồn tại trong **luồng truy vấn**.

### 3.1. Ví dụ: FPR chỉ 1% nhưng phần lớn kết quả dương có thể sai

Giả sử trong `10.000` truy vấn có khoảng `0,5%` khóa thực sự tồn tại. Filter không bỏ sót khóa đã có (`TPR = 100%`), còn `FPR = 1%`.

```text
Số truy vấn thật sự có khóa:     10.000 × 0,005 = 50
Số truy vấn thật sự vắng mặt:   10.000 × 0,995 = 9.950
TP kỳ vọng:                     50
FP kỳ vọng:                     9.950 × 0,01 = 99,5
PPV dự kiến:                    50 / (50 + 99,5) ≈ 33,44%
```

Khoảng **hai phần ba** các kết quả “có thể có” cần bị bác bỏ bởi nguồn chính xác, mặc dù FPR chỉ 1%. Con số thập phân `99,5` là **số lượng kỳ vọng**, không phải số truy vấn thực tế có thể là nửa truy vấn.

Gọi `π = P(khóa có thật trong truy vấn)` là tỷ lệ nền (*base rate*). Theo Bayes:

```text
PPV = (TPR × π) / (TPR × π + FPR × (1 − π))
```

Vì thế một FPR nhìn có vẻ nhỏ vẫn có thể tạo nhiều dương tính giả khi phần lớn truy vấn hướng vào khóa vắng mặt. Điều này ảnh hưởng trực tiếp đến chi phí truy vấn xác minh và cách diễn giải kết quả.

### 3.2. FPR lý thuyết của Bloom filter

Với `m` bit, `k` vị trí băm cho mỗi khóa và khoảng `n` khóa phân biệt đã thêm, xác suất dương tính giả thường được xấp xỉ bởi:

```text
FPR ≈ (1 − exp(−kn/m))^k

m_tối_ưu ≈ −n × ln(FPR_mục_tiêu) / (ln 2)^2
k_tối_ưu ≈ (m/n) × ln 2
```

Đây là công thức gần đúng dưới giả định hash phân bố phù hợp. Chẳng hạn với `n = 1.000.000` và FPR mục tiêu `1%`, phần mảng bit cần khoảng **9,59 triệu bit**, xấp xỉ **1,14 MiB**, và `k` gần `7`.

Nếu giữ `m`, `k` nhưng số khóa thực tế tăng gấp đôi, FPR thường tăng mạnh. Với các thông số trên, thay `n` bằng `2.000.000` trong công thức cho FPR xấp xỉ **15,8%**. Vì vậy, **kiểm thử tại tải dự kiến và theo dõi mức sử dụng** cần thiết không kém việc chọn thông số ban đầu.

## 4. Count-Min Sketch: sai số cộng và xác suất thất bại

CMS có `d` hàng, mỗi hàng `w` bộ đếm. Khi khóa `x` xuất hiện, thuật toán tăng một bộ đếm trên mỗi hàng; truy vấn lấy số nhỏ nhất:

```text
f̂(x) = min(C[i][h_i(x)] với i = 0..d−1)
```

Trong **mô hình chỉ thêm** (*insertion-only*) với trọng số không âm, không tràn và mọi cập nhật thành công, giá trị mỗi ô bằng số lần của `x` cộng các lần của khóa khác va chạm. Do đó:

```text
f̂(x) ≥ f(x)                         // không đếm thiếu
P[f̂(x) ≤ f(x) + εN] ≥ 1 − δ        // bảo đảm xác suất cho một x cố định
```

Ở đây `N` là **tổng trọng số cập nhật của toàn luồng**, `ε` kiểm soát **sai số cộng**, còn `δ` là xác suất có thể vượt giới hạn. Một cách chọn cấu hình thông dụng:

```text
w = ceil(e/ε)        // e ≈ 2,71828
d = ceil(ln(1/δ))
```

Bảo đảm này được xét theo sự ngẫu nhiên trong cách chọn các hàm băm thỏa giả định, với một luồng và khóa truy vấn đã cố định. Nó **không có nghĩa** mỗi kết quả truy vấn là đúng với xác suất `1−δ`, hay một tập truy vấn được chọn thích nghi sau khi quan sát sketch sẽ tự động có cùng bảo đảm.

### 4.1. Sai số cộng khác sai số phần trăm của riêng khóa

Cho `N = 2.000.000` lượt cập nhật, `ε = 0,005` và `δ = 0,01`. Theo bảo đảm, với một khóa `x` cố định:

```text
εN = 0,005 × 2.000.000 = 10.000 lượt

f(x) = 250
250 ≤ f̂(x) ≤ 10.250   với xác suất ít nhất 99%
```

Khoảng này quá rộng nếu cần phân biệt một khóa có `250` hay `300` lượt. Ngược lại, với khóa xuất hiện hàng trăm nghìn lượt, sai số cộng `10.000` có thể phù hợp với một báo cáo tổng quan. Cấu hình CMS phải xuất phát từ **độ lệch tuyệt đối chấp nhận được ở quy mô `N` dự kiến**, không chỉ từ tên gọi “độ tin cậy 99%”.

### 4.2. Nhiều truy vấn và union bound

Nếu muốn một bảo đảm đồng thời cho `K` khóa **định trước**, ta có thể phân bổ xác suất thất bại `δ_total` cho mỗi khóa:

```text
δ_per_key = δ_total / K
d ≥ ceil(ln(K / δ_total))
```

Theo *union bound*, xác suất có ít nhất một khóa trong `K` khóa vi phạm biên sai số không quá `δ_total`. Cách này làm tăng số hàng và bộ nhớ. Với các khóa được chọn **thích nghi** theo kết quả trước đó hoặc truy vấn do đối thủ điều khiển, cần phân tích riêng thay vì áp dụng máy móc công thức.

Đánh giá thực tế CMS còn phải theo dõi **tỷ lệ đếm dư**, độ lệch tuyệt đối `f̂−f`, các phân vị sai số, mức tải mỗi hàng, tràn bộ đếm và độ chính xác tại nhóm khóa tần suất thấp. Khi gộp sketch từ các shard, phép cộng bộ đếm đòi hỏi các shard **không đếm trùng sự kiện** nếu mục tiêu là tổng số lượt duy nhất.

## 5. HyperLogLog: độ lệch chuẩn tương đối không phải giới hạn tuyệt đối

HyperLogLog (HLL) ước lượng số khóa phân biệt `D` từ `m = 2^p` thanh ghi nhỏ. Ở vùng hoạt động phù hợp và với hash phân bố tốt, **độ lệch chuẩn tương đối** (*relative standard error*, RSE) của HLL cổ điển thường gần:

```text
RSE ≈ 1,04 / sqrt(m)
```

| `p` | Thanh ghi `m` | RSE xấp xỉ | Bộ nhớ mảng nếu dùng 1 byte/thanh ghi |
|---:|---:|---:|---:|
| 10 | 1.024 | 3,25% | 1 KiB |
| 12 | 4.096 | 1,63% | 4 KiB |
| 14 | 16.384 | 0,81% | 16 KiB |
| 16 | 65.536 | 0,41% | 64 KiB |

**RSE đo độ phân tán**, không phải “xác suất đúng” hay mức sai số tối đa. Một HLL có RSE `0,81%` vẫn có thể cho kết quả lệch nhiều hơn `0,81%`. Ngoài ra, HLL có thể ước lượng **cao hoặc thấp** hơn cardinality thực; các hiệu chỉnh cho cardinality nhỏ và lớn ảnh hưởng đến độ lệch (*bias*) và phân phối sai số.

### 5.1. Ước lượng khoảng dao động

Giả sử `m = 16.384`, RSE khoảng `0,8125%` và một HLL trả về `D̂ = 200.000` khóa phân biệt. Độ lệch chuẩn tuyệt đối có thể ước lượng sơ bộ:

```text
σ_ước_tính ≈ 200.000 × 0,008125 = 1.625 khóa
```

Nếu phân phối sai số gần chuẩn, bias nhỏ và đang ở vùng cardinality phù hợp, một khoảng **tham khảo** kiểu hai phía 95% là:

```text
D̂ ± 1,96 × σ_ước_tính
≈ 200.000 ± 3.185
≈ [196.815 ; 203.185]
```

Đây **không phải khoảng tin cậy được bảo đảm chặt chẽ cho mọi HLL**. Trong thực tế phải kiểm tra bias, phân phối sai số và hiệu chỉnh của thư viện cụ thể; không được dùng khoảng trên như chứng nhận rằng số khóa thật chắc chắn nằm trong đó.

Muốn giảm RSE xuống một nửa, cần tăng số thanh ghi khoảng **bốn lần**. Do vậy một yêu cầu báo cáo sát hơn có thể khiến chi phí RAM tăng đáng kể, ngay cả khi thuật toán vẫn có độ phức tạp gần cố định theo lượng dữ liệu.

### 5.2. Khi gộp, phải gộp trạng thái trước khi ước lượng

Đối với hai HLL cùng cấu hình hash/seed, mã hóa khóa và `p`:

```text
M_merged[j] = max(M_A[j], M_B[j])
```

HLL gộp ước lượng số khóa phân biệt trong **hợp** hai tập khóa. **Không cộng trực tiếp** `estimate(A) + estimate(B)` vì khóa xuất hiện ở cả hai nơi sẽ bị đếm hai lần. Một HLL đơn lẻ không thể xác minh khóa cụ thể, hoàn tác an toàn một lần thêm hoặc tự xóa các khóa cũ khỏi khoảng thời gian đã gộp.

## 6. “Mức tin cậy” có thể chỉ ba khái niệm khác nhau

| Khái niệm | Ví dụ | Diễn giải đúng |
|---|---|---|
| Xác suất biến cố lỗi của bộ lọc | Bloom có FPR khoảng `1%` | Trong các truy vấn **thật sự vắng mặt** thuộc mô hình đánh giá, khoảng 1% có thể bị báo dương |
| Xác suất đạt một **biên sai số** | CMS: `1−δ = 99%` | Với một khóa cố định và giả định hash, ước lượng nằm trong khoảng `[f, f+εN]` với xác suất ít nhất 99% |
| Độ phân tán tương đối của ước lượng | HLL: RSE khoảng `0,81%` | Một thước đo biến động giữa các lần thử; không trực tiếp là mức tin cậy 99% hoặc 95% |

Khi viết tài liệu yêu cầu hoặc báo cáo, tránh câu “thuật toán chính xác 99%” nếu không định nghĩa rõ **mẫu số, đơn vị và biến cố**. Nên viết, ví dụ:

> “Trên tập truy vấn âm đại diện, mục tiêu FPR của Bloom filter không quá 1%; mọi khóa đã chèn phải được báo có thể có.”

> “Với CMS, biên sai số cộng đặt ở `0,5%` tổng trọng số luồng, xác suất vượt biên không quá `1%` cho một khóa cố định dưới các giả định băm.”

> “Với HLL, RSE mục tiêu khoảng `1%` trong dải cardinality đã kiểm chứng; báo cáo kèm ước lượng và mức dao động quan sát được.”

Một số thuật toán cho **bất biến chắc chắn**, một số cho **bảo đảm xác suất**, còn các con số đo trên dữ liệu thực là **ước lượng thực nghiệm**. Không nên thay thế ba loại phát biểu cho nhau.

## 7. Thiết kế thí nghiệm đánh giá sai số

Một phép đánh giá đáng tin cậy cần có dữ liệu thật được đếm chính xác bằng `set`, `map` hoặc xử lý batch đáng tin cậy. Cần định nghĩa **cùng miền khóa và cùng cửa sổ thời gian** cho số đúng và số ước lượng.

### 7.1. Chuẩn bị dữ liệu và mẫu truy vấn

1. **Xác định tập nguồn** và quy tắc chuẩn hóa khóa: kiểu dữ liệu, Unicode, phân biệt chữ hoa, định danh người dùng hay phiên.
2. **Lập ground truth:** với bộ lọc, biết khóa nào thuộc tập; với CMS, lưu số lần xuất hiện chính xác; với HLL, đếm `len(set(keys))` trên mẫu/thời đoạn kiểm thử.
3. **Chọn tải đầu vào đại diện:** số khóa phân biệt, tổng sự kiện, phân bố khóa phổ biến/hiếm, độ dài khóa và số lần trùng.
4. **Tạo truy vấn dương và âm tách biệt:** dương lấy từ các khóa đã thêm; âm phải chắc chắn chưa được thêm. Tránh xem một truy vấn bị filter báo âm là “ground truth âm”.
5. **Đánh giá ở nhiều mức tải:** ví dụ 25%, 50%, 75%, 100%, 125% dung lượng thiết kế; đo tốc độ, bộ nhớ và sự biến thiên sai số.

Với các truy vấn âm không độc lập (lặp lại cùng khóa), FPR quan sát có thể bị lệch mạnh vì kết quả của cùng khóa trên một Bloom filter cố định là **tất định**. Cần ghi rõ cách lấy mẫu, tỷ lệ trùng khóa, nguồn các khóa âm và cách chọn hash seed.

### 7.2. Thước đo cần báo cáo

| Cấu trúc | Phép đo chính | Phép đo bổ sung |
|---|---|---|
| Bloom / Cuckoo | FPR trên truy vấn âm, FN trên khóa đã chèn | Mật độ bit/bucket, số lần chèn thất bại, chi phí xác minh, latency |
| CMS | Sai số `f̂(x)−f(x)`, tỷ lệ vượt `εN` | Sai số theo nhóm tần suất, phân vị P50/P95/P99, tình trạng tràn |
| HLL | Sai số tương đối `(D̂−D)/D` khi `D>0` | Bias trung bình, độ lệch chuẩn, RMSE, phân vị của `|sai số|` |

Với HLL, nên chạy **nhiều lần thử có seed băm độc lập** và trên nhiều tập dữ liệu đại diện để ước lượng bias, độ lệch chuẩn và phân vị. Lặp đi lặp lại `estimate()` trên **cùng trạng thái HLL** không tạo ra các phép thử ngẫu nhiên mới.

### 7.3. Đo sai số không đồng nghĩa chứng minh công thức

Nếu thử `10.000` khóa âm độc lập một cách phù hợp và quan sát `102` false positive:

```text
FPR_quan_sát = 102 / 10.000 = 1,02%
```

Một xấp xỉ độ lệch chuẩn của tỷ lệ quan sát trong mô hình Bernoulli độc lập là:

```text
SE ≈ sqrt(p_hat(1 − p_hat) / q)
   ≈ sqrt(0,0102 × 0,9898 / 10.000)
   ≈ 0,001005 = 0,1005 điểm phần trăm
```

Khoảng hai phía dùng quy tắc chuẩn `p_hat ± 1,96SE` cho kết quả tham khảo khoảng **0,823% đến 1,217%**. Cách tính này chỉ thích hợp khi các quan sát thực sự gần độc lập và cỡ mẫu đủ lớn; với nhiều khóa lặp, cùng một hash seed, truy vấn được lựa chọn thích nghi hoặc sai số rất nhỏ, cần phương pháp đánh giá phù hợp hơn (chẳng hạn khoảng Wilson, phân cụm hoặc lặp seed).

Đo FPR chỉ ở một tập truy vấn nhỏ rồi tuyên bố mọi dữ liệu đều có FPR như vậy là không đủ. Phải kiểm tra trên phân bố truy vấn và mức tải ứng dụng sẽ gặp.

## 8. Mã Python minh họa: đo Bloom filter bằng tập chính xác

Ví dụ sau dùng một Bloom filter đơn giản và `set` làm ground truth. Các khóa dương đã được thêm, các khóa âm được tạo riêng, và phép đo thống kê số FP/FN. `blake2b` giúp hàm băm ổn định giữa các lần chạy; ví dụ có mục đích giảng giải, chưa phải bộ kiểm định xác suất đầy đủ.

```python
from hashlib import blake2b


class BloomFilter:
    def __init__(self, bit_count, hash_count):
        if bit_count <= 0 or hash_count <= 0:
            raise ValueError("kich thuoc va so hash phai duong")
        self.m = bit_count
        self.k = hash_count
        self.bits = bytearray((bit_count + 7) // 8)

    def _positions(self, key):
        data = key.encode("utf-8")
        for i in range(self.k):
            digest = blake2b(
                b"bloom-test-v1:" + i.to_bytes(4, "big") + data,
                digest_size=8
            ).digest()
            yield int.from_bytes(digest, "big") % self.m

    def add(self, key):
        for pos in self._positions(key):
            self.bits[pos // 8] |= 1 << (pos % 8)

    def might_contain(self, key):
        return all(
            self.bits[pos // 8] & (1 << (pos % 8))
            for pos in self._positions(key)
        )


def evaluate(filter_, true_keys, negative_queries):
    positives = list(true_keys)
    negatives = list(negative_queries)
    truth = set(positives)
    if not positives or not negatives:
        raise ValueError("can ca truy van duong va am")
    if len(set(negatives)) != len(negatives):
        raise ValueError("truy van am phai phan biet trong vi du nay")
    if any(key in truth for key in negatives):
        raise ValueError("truy van am khong duoc la khoa da chen")

    tp = sum(filter_.might_contain(key) for key in positives)
    fn = len(positives) - tp
    fp = sum(filter_.might_contain(key) for key in negatives)
    tn = len(negatives) - fp

    return {
        "TP": tp, "FN": fn, "FP": fp, "TN": tn,
        "FPR": fp / (fp + tn),
        "FNR": fn / (fn + tp)
    }


present = [f"member-{i}" for i in range(5_000)]
absent = [f"other-{i}" for i in range(10_000)]
filter_ = BloomFilter(bit_count=48_000, hash_count=7)
for key in present:
    filter_.add(key)

metrics = evaluate(filter_, present, absent)
print(metrics)
assert metrics["FN"] == 0
print("FPR quan sat:", f'{metrics["FPR"]:.2%}')
```

Đoạn mã cho **một** tập khóa và **một** cách băm cố định. Kết quả FPR có thể khác giá trị lý thuyết vì số khóa, mẫu truy vấn, cách băm và tương quan giữa các vị trí băm. Trong một nghiên cứu thực nghiệm đầy đủ, cần thử nhiều seed/cấu hình, tải dữ liệu và phân bố truy vấn; không được suy ra mức tin cậy chỉ từ `assert FN == 0` hay một lần chạy thành công.

## 9. Sai số tác động trực tiếp đến chi phí và quyết định nghiệp vụ

### 9.1. Bộ lọc trước cơ sở dữ liệu

Giả sử dịch vụ nhận `Q = 1.000.000` truy vấn trong ngày, `90%` hỏi khóa vắng mặt, Bloom filter có FPR gần `1%` và phản ánh đầy đủ nguồn sự thật:

```text
Truy vấn khóa vắng mặt = 900.000
Truy vấn khóa có thật  = 100.000
FP kỳ vọng             = 900.000 × 1% = 9.000

Truy vấn phải xác minh nguồn chính xác
≈ 100.000 + 9.000 = 109.000
```

So với `1.000.000` lần truy vấn nguồn nếu không có filter, lượng truy vấn xác minh có thể giảm khoảng **89,1%**. Đổi lại là RAM cho filter, chi phí hash, thời gian cập nhật và rủi ro bất đồng bộ. Nếu bản thân tra cứu nguồn đã rẻ hoặc tỷ lệ truy vấn âm thấp, lợi ích có thể không đủ bù các chi phí đó.

**Bộ lọc không được tự quyết định từ chối một giao dịch chỉ vì trả về “có thể có”.** Một FP có thể khiến người dùng bị từ chối sai; trong luồng nghiệp vụ này cần xác minh bằng nguồn chính xác trước khi hành động.

### 9.2. CMS cho phát hiện tải bất thường

Một hệ thống dùng CMS để cảnh báo khi endpoint nhận trên `20.000` yêu cầu. Vì CMS có thể đếm dư, có thể xảy ra trường hợp tần suất thật là `18.000` nhưng ước lượng vượt ngưỡng. Nếu hậu quả chỉ là **đưa endpoint vào danh sách cần kiểm tra thêm**, FP có thể chấp nhận. Nếu hành động là **chặn người dùng hoặc cắt dịch vụ**, cần một bước đo chính xác hay cơ chế xác minh trước khi chặn.

### 9.3. HLL cho báo cáo người dùng duy nhất

HLL phù hợp để hiển thị xu hướng lượng người dùng duy nhất, thống kê dashboard và so sánh tương đối ở quy mô lớn. Nhưng khi dùng một mốc như “đạt `200.000` người dùng để được thưởng”, ước lượng `199.800` hay `200.200` có thể nằm trong vùng dao động thống kê. Quyết định thanh toán, phân chia doanh thu hoặc kiểm toán nên dựa trên nguồn đếm chính xác hay một quy trình đối soát được định nghĩa rõ.

| Hệ quả khi sai | Cách dùng cấu trúc xác suất |
|---|---|
| Tăng vài lần truy vấn xác minh | Có thể chấp nhận FPR vừa phải để tiết kiệm RAM |
| Cảnh báo sớm cho người vận hành | Có thể dùng ngưỡng trên ước lượng, rồi xác minh |
| Từ chối giao dịch hoặc giới hạn quyền truy cập | Không kết luận chỉ từ dương tính của filter hoặc số đếm gần ngưỡng |
| Báo cáo xu hướng ở quy mô lớn | HLL/CMS có thể phù hợp nếu công bố sai số |
| Tính tiền, đối soát, chứng minh sự kiện | Giữ nguồn chính xác hoặc quy trình kiểm chứng bắt buộc |

## 10. Theo dõi chất lượng sau khi triển khai

Thông số tính lúc khởi tạo không bảo đảm độ chính xác suốt vòng đời hệ thống. Các chỉ số nên theo dõi:

- **Bloom filter:** số khóa dự kiến/đã thêm, tỷ lệ bit bằng `1`, FPR quan sát từ mẫu truy vấn được xác minh, số lần rebuild và tình trạng đồng bộ nguồn.
- **Cuckoo filter:** hệ số lấp đầy, độ dài fingerprint, số bước *kicking*, tỷ lệ chèn thất bại, tình trạng stash và lỗi xóa.
- **Count-Min Sketch:** tổng trọng số `N`, độ phân tán bộ đếm, tỷ lệ vượt biên `εN` trên tập kiểm thử, tràn số và tăng sai số của khóa hiếm.
- **HyperLogLog:** số thanh ghi `m`, tỷ lệ thanh ghi bằng `0` trong vùng cardinality nhỏ, độ lệch tương đối trên mẫu chính xác, version hash và mức thay đổi cardinality.

Ngoài sai số, đo **độ trễ P50/P95/P99**, thời gian cập nhật, dung lượng RAM thực tế và lưu lượng gộp sketch. Một cấu trúc “`O(1)` trung bình” vẫn có thể chậm vì cache miss, hash khóa dài, truy cập bộ nhớ, đồng bộ luồng hoặc triển khai chưa tối ưu.

Nên xác định trước các **ngưỡng hành động**: FPR vượt mức cho phép thì xây lại filter với kích thước phù hợp; CMS tiến gần giới hạn bộ đếm thì mở rộng hoặc chia cửa sổ; HLL có lỗi tương đối đo được cao trên mẫu đối soát thì kiểm tra hash, miền cardinality và cách hiệu chỉnh. Nếu phát hiện dữ liệu không nhất quán, chuyển sang đường truy vấn chính xác cho đến khi sketch được dựng lại đáng tin cậy.

## 11. Chọn tham số theo ngân sách sai số

Một quy trình thiết kế có thể thực hiện theo thứ tự:

1. **Xác định câu hỏi và độ chính xác cần thiết.** Thành viên, tần suất hay cardinality? Có cần kết luận chính xác cho nghiệp vụ không?
2. **Ước lượng tải:** số khóa phân biệt, tổng lượt sự kiện, tốc độ cập nhật và thời gian giữ dữ liệu.
3. **Định nghĩa ngân sách sai số:** FPR mục tiêu cho bộ lọc; `εN` và `δ` cho CMS; RSE và mức dao động thực nghiệm cho HLL.
4. **Quy đổi sang bộ nhớ và thao tác:** bit và hash của Bloom, bucket/fingerprint của Cuckoo, hàng/cột của CMS, số thanh ghi của HLL.
5. **Xác minh bằng dữ liệu đại diện:** đo kết quả theo phân bố thực tế, nhiều tải và các trường hợp cực trị.
6. **Xác định đường xử lý khi sai số hoặc đồng bộ không đạt:** truy vấn nguồn chính xác, retry có kiểm soát, rebuild, versioning và cảnh báo.

Những câu hỏi cụ thể giúp lựa chọn phù hợp hơn:

| Ràng buộc | Hướng cân nhắc |
|---|---|
| Nhiều truy vấn âm, DB tốn chi phí | Bloom hoặc Cuckoo đặt trước nguồn chính xác |
| Nguồn phải xóa khóa thường xuyên | Cuckoo hoặc biến thể Bloom hỗ trợ đếm, với điều kiện xóa an toàn |
| Cần đếm tần suất gần đúng, luồng rất lớn | CMS; kiểm tra sai số cộng theo `N` |
| Chỉ cần số phần tử phân biệt | HLL; tính bộ nhớ từ RSE mục tiêu |
| Sai một đơn vị cũng gây hậu quả lớn | `set`, `map`, chỉ mục chính xác hoặc đối soát |
| Nhiều shard cần tổng hợp | Chỉ merge sketch có cùng cấu hình hash, seed, mã hóa khóa, cửa sổ và ngữ nghĩa |

## 12. Bài tập tự kiểm tra

**Câu 1.** Trong `5.000` truy vấn vào khóa **không tồn tại**, Bloom filter trả về “có thể có” `75` lần. FPR quan sát là bao nhiêu?

**Đáp án:** `75 / 5.000 = 1,5%`. Đây là FPR trên mẫu truy vấn âm, không phải tỷ lệ chính xác của mọi kết quả dương.

**Câu 2.** Một filter có `FPR = 2%`, `TPR = 100%`. Nếu `π = 1%` truy vấn thật sự có khóa, PPV xấp xỉ bao nhiêu?

**Đáp án:** `PPV = 0,01 / (0,01 + 0,02 × 0,99) ≈ 33,56%`. Tỷ lệ khóa thật sự tồn tại thấp làm phần lớn dương tính cần xác minh.

**Câu 3.** CMS có `ε = 0,002`, `δ = 0,05` và đã xử lý `N = 500.000` sự kiện đơn vị. Với khóa thực sự xuất hiện `400` lần, biên sai số là bao nhiêu?

**Đáp án:** `εN = 1.000`. Theo bảo đảm một khóa cố định, `400 ≤ f̂(x) ≤ 1.400` với xác suất ít nhất `95%`, nếu giả định hash và mô hình cập nhật được thỏa mãn.

**Câu 4.** Một HLL có `m = 4.096` thanh ghi. RSE theo công thức gần đúng là bao nhiêu? Có được xem đó là sai số tối đa không?

**Đáp án:** `1,04/√4.096 = 1,04/64 = 1,625%`. Đây là độ lệch chuẩn tương đối xấp xỉ, **không phải** sai số tối đa cho mỗi kết quả.

**Câu 5.** Bloom filter trả về “không” cho mã giao dịch vừa ghi vào DB, nhưng sự kiện cập nhật filter đang chờ xử lý. Có được bỏ qua DB không?

**Đáp án:** Không. Bảo đảm “không có” chỉ áp dụng với tập đã được filter biểu diễn. Cần xác minh DB hoặc bảo đảm đồng bộ hoàn tất trước khi tin kết quả âm.

**Câu 6.** Một nhóm đo 100 lần `estimate()` trên cùng HLL không đổi và thấy mọi kết quả bằng nhau. Điều đó chứng minh RSE bằng `0` không?

**Đáp án:** Không. Với trạng thái cố định, phép ước lượng là tất định. Đánh giá RSE cần nhiều sketch từ những lần thử thích hợp, chẳng hạn các seed băm độc lập trên tập dữ liệu biết cardinality.

**Câu 7.** CMS cảnh báo vượt ngưỡng khi số thật chưa vượt ngưỡng. Có nên coi đó là lỗi cập nhật?

**Đáp án:** Chưa chắc. CMS có thể đếm dư theo thiết kế. Cần so sánh sai số với biên `εN` và kiểm tra hash/cập nhật; nếu cảnh báo gây hậu quả lớn, xác minh số thật trước khi hành động.

Một cấu trúc xác suất chỉ hữu ích khi **cách diễn giải kết quả phù hợp với bảo đảm của nó**. Đánh giá đúng cần chỉ rõ loại sai số, mức tin cậy, giả định băm và phạm vi dữ liệu; sau đó kiểm chứng trên tải thực tế và xây dựng cơ chế xác minh cho các quyết định cần độ chính xác tuyệt đối.
