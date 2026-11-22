# Bloom filter và xác suất trả lời dương tính giả

## 1. Bài toán: “có thể thuộc tập” với bộ nhớ rất nhỏ

Giả sử một hệ thống nhận hàng triệu mã khóa qua luồng dữ liệu, rồi liên tục phải trả lời: “Khóa này đã được thấy chưa?”. Lưu mọi khóa trong một HashSet có thể tốn nhiều bộ nhớ. Nếu một câu trả lời **phủ định chắc chắn** hữu ích hơn câu trả lời khẳng định chính xác, ta có thể dùng **Bloom filter** để chặn phần lớn các truy vấn không tồn tại trước khi tra cứu ở tầng lưu trữ thật.

**Bloom filter là cấu trúc dữ liệu xác suất để kiểm tra thành viên của tập** bằng một mảng bit và một số hàm băm. Nó hỗ trợ hai thao tác cốt lõi:

- `add(x)`: đánh dấu các vị trí bit do các hàm băm của x chọn.
- `mightContain(x)`: trả **false** nếu có ít nhất một vị trí bit của x bằng 0, và trả **true** nếu tất cả vị trí ấy đều bằng 1.

Ý nghĩa phản hồi không đối xứng:

- **false / definitely not present:** chắc chắn chưa được thêm, với điều kiện các giả thiết về cùng bộ lọc, cùng hàm băm, không xóa bit, không lỗi bộ nhớ và mã hóa khóa nhất quán đều giữ đúng.
- **true / maybe present:** **có thể** đã thêm. Một khóa chưa từng thêm vẫn có thể nhận true do những khóa khác đã bật đúng các bit đó. Trường hợp này gọi là **dương tính giả** (*false positive*, FP).

Bloom filter chuẩn **không lưu nguyên bản khóa**, không thể liệt kê tất cả phần tử, và không thể kết luận “chắc chắn có” chỉ từ true.

### 1.1. Vì sao phù hợp với phần “Trực tuyến và luồng”?

Mỗi khóa được xử lý tại thời điểm nó đến; cập nhật bộ lọc chỉ cần truy cập một số vị trí bit, không phải nhìn dữ liệu tương lai. Bộ lọc có bộ nhớ được cấp phát trước, không tăng tuyến tính theo số khóa theo cách HashSet thường làm. Cấu trúc này là một **streaming summary**: nó hy sinh khả năng trả lời chính xác mọi truy vấn để đổi lấy bộ nhớ nhỏ.

Bloom filter khác các thuật toán online phân tích theo **competitive ratio** như ski rental hay cache replacement. Chất lượng ở đây được đo bằng **xác suất dương tính giả, bộ nhớ và chi phí cập nhật/truy vấn**, không phải mặc định là ALG/OPT.

## 2. Cấu tạo: m bit và k phép băm

Một Bloom filter cơ bản gồm:

1. Mảng bit B có **m vị trí**, đánh số 0..m−1, ban đầu toàn bộ bằng 0.
2. k hàm băm h₀, h₁, …, h_(k−1) chuyển cùng một khóa thành chỉ số từ 0 đến m−1.
3. Quy tắc băm **ổn định**: add và query của cùng khóa phải cho cùng k vị trí trong toàn bộ vòng đời bộ lọc.
4. Một chính sách dung lượng dự kiến: số khóa **phân biệt** n dự kiến thêm, mức xác suất dương tính giả mục tiêu và cách xử lý khi n vượt dự kiến.

Ví dụ với m=12 và k=3:

```text
Ban đầu:    000000000000

add("lan"): h -> {1,4,9}
Bit sau:    010010000100

add("dao"): h -> {2,4,10}
Bit sau:    011010000110

query("lan"):  các bit 1,4,9 đều 1   => MAYBE
query("mai"):  nếu hash chứa bit 7=0  => DEFINITELY NOT
query("chua"): nếu hash chỉ vào 1,4,10 => MAYBE (có thể FP)
```

Các vị trí trong minh họa được **giả định** để dễ hình dung, không phải giá trị băm của chương trình Java ở dưới. Nếu hai hàm băm tình cờ cùng trả một chỉ số cho một khóa, chương trình vẫn hợp lệ nhưng số phép kiểm bit độc lập hiệu dụng giảm; phân tích xác suất cần tính đến hiện tượng đó.

### 2.1. Thuật toán thêm khóa

```text
add(key):
    for i = 0 .. k-1:
        B[h_i(key)] = 1
```

Không cần tìm trước khóa đã tồn tại. Nếu thêm lại cùng một khóa, cùng các bit được đặt thành 1 lần nữa: **idempotent** theo trạng thái mảng bit. Vì vậy 1.000 lời gọi add của cùng một khóa không có nghĩa bộ lọc đã nhận 1.000 khóa phân biệt.

### 2.2. Thuật toán truy vấn

```text
mightContain(key):
    for i = 0 .. k-1:
        if B[h_i(key)] == 0:
            return false     // definitely absent
    return true              // maybe present
```

Có thể dừng ngay khi gặp bit 0 nên một truy vấn âm tính thường nhanh hơn k lần đọc bit trong điều kiện thông thường. Khi bộ lọc bão hòa, truy vấn dương tính phải xét đủ k vị trí; đồng thời giá trị của lọc có xu hướng giảm mạnh.

## 3. Chứng minh không âm tính giả trong mô hình chuẩn

**Mệnh đề:** Nếu x đã từng được add vào một Bloom filter chỉ có thao tác **đặt bit từ 0 thành 1** và không có thao tác xóa, thì mọi truy vấn sau đó của chính x phải trả true.

**Chứng minh:** Khi add(x), với từng i từ 0 đến k−1, thuật toán thực hiện B[h_i(x)]=1. Những thao tác add sau này chỉ có thể giữ nguyên bit 1 hoặc bật thêm bit 0, không bao giờ chuyển bit 1 thành 0. Vì hàm băm và mã hóa x không đổi, khi query(x), tất cả B[h_i(x)] vẫn bằng 1. Do đó query(x)=true. □

Chứng minh này **không** phụ thuộc việc các hash độc lập hay xác suất dương tính giả thấp. Ngay cả một bộ lọc băm rất tệ hoặc đã bão hòa vẫn không có false negative cho những khóa đã thêm **theo đúng các giả thiết**.

### 3.1. Khi nào âm tính giả xuất hiện?

Âm tính giả có thể xuất hiện nếu phá một giả thiết, ví dụ:

- Tự ý xóa một bit để “xóa khóa” và vô tình xóa bit còn được dùng bởi khóa khác.
- Dùng seed hoặc phiên bản hàm băm khác khi truy vấn so với khi thêm.
- Chuẩn hóa chuỗi khác nhau giữa add và query (Unicode normalization, chữ hoa/thường, mã hóa, locale).
- Mất dữ liệu bit, đọc một snapshot lỗi, hoặc lưu/khôi phục sai thông số m, k, seed.
- Dùng biến thể cho phép quên phần tử như **stable Bloom filter** hoặc cơ chế aging, vốn cố ý đánh đổi khả năng có false negatives.
- Xóa một thành viên không hợp lệ trong một counting Bloom filter hoặc để bộ đếm tràn/underflow.

Vì vậy câu “Bloom filter không có false negatives” phải đi kèm **bản insertion-only thông thường với hashing/bitset nhất quán**; không áp dụng vô điều kiện cho mọi biến thể hay mọi lỗi triển khai.

## 4. Dương tính giả đến từ đâu?

Một khóa chưa từng thêm có thể được băm vào những bit đã được bật bởi **các khóa khác**. Bộ lọc chỉ biết các bit, không biết bit nào do khóa nào bật. Từ một mảng bit chứa nhiều bit 1, hai tập khóa khác nhau có thể tạo **cùng một trạng thái**.

Ví dụ, với m=8 và vài khóa đã thêm, nếu mọi bit đều bằng 1 thì **mọi truy vấn** đều trả true, kể cả khóa chắc chắn chưa thêm. Đây là trạng thái **bão hòa** (*saturated*), có false-positive rate 100% trên mọi tập truy vấn vắng mặt.

Quan trọng: một câu trả true cho khóa đã thêm là **true positive**; không gọi đó là “dương tính giả”. Một câu trả false cho khóa chưa thêm là **true negative**; Bloom filter chỉ cần một bit 0 để xác nhận trường hợp này.

| Trạng thái thật | Bloom trả false | Bloom trả true |
|---|---|---|
| Khóa từng thêm | **Không xảy ra** trong mô hình insertion-only chuẩn | True positive |
| Khóa chưa thêm | True negative (chắc chắn vắng mặt) | **False positive** |

### 4.1. Lỗi nhận thức trong ứng dụng

Không lấy câu trả true từ Bloom filter để cấp quyền, xác nhận tài khoản tồn tại, ghi nhận giao dịch thành công, hoặc xóa một bản ghi khỏi cơ sở dữ liệu khi cần tính đúng tuyệt đối. Trong những quy trình này, **true phải dẫn tới bước xác minh chính xác** bằng HashSet/cơ sở dữ liệu/index thực tế.

Một cách dùng an toàn:

```text
if !bloom.mightContain(key):
    // chắc chắn không nằm trong tập đã nạp
    return NOT_FOUND

// Maybe: có thể do FP, cần kiểm chứng chính xác.
return database.lookup(key)
```

Mô hình này giảm số lần tra cứu tầng lưu trữ đối với những khóa chắc chắn vắng mặt. Nếu Bloom trả true sai, hệ thống chỉ phải thực hiện một tra cứu tốn kém không cần thiết; nó **không trả kết quả tồn tại sai** cho người dùng cuối.

## 5. Công thức xác suất dương tính giả kinh điển

Đặt:

- **m**: số bit.
- **k**: số hàm băm/vị trí ghi mỗi khóa.
- **n**: số khóa **phân biệt** đã thêm.
- Mô hình **lý tưởng**: mỗi lần băm cho một vị trí ngẫu nhiên đều trong m bit và các phép chọn độc lập theo mô hình phân tích.

Sau khi thêm n khóa, có tổng cộng k·n phép đặt bit (có thể lặp vị trí).

### 5.1. Xác suất một bit vẫn là 0

Trong một lần băm lý tưởng, xác suất không chọn một bit cố định là 1−1/m. Sau kn lần chọn độc lập:

**Pr[bit cố định = 0] = (1−1/m)^(k·n).**

Với m đủ lớn, dùng giới hạn (1−1/m)^m≈e^(−1):

**Pr[bit cố định = 0] ≈ e^(−kn/m).**

Vậy xác suất một bit cố định đã bật là xấp xỉ:

**q ≈ 1−e^(−kn/m).**

Đây cũng là **tỷ lệ bit 1 kỳ vọng**, không phải “xác suất khóa có trong tập”.

### 5.2. Xấp xỉ false-positive rate

Nếu một khóa chưa thêm có k vị trí hash độc lập đều, một cách xấp xỉ thông dụng là xem trạng thái các bit được kiểm gần độc lập. Khi ấy:

**p_FP ≈ (1−e^(−kn/m))^k.**

Một phiên bản giữ xác suất một bit chính xác nhưng vẫn xấp xỉ tính độc lập các bit là:

**p_FP ≈ [1−(1−1/m)^(kn)]^k.**

Đây là hai **công thức xấp xỉ** trong phân tích Bloom filter chuẩn. Không đọc dấu ≈ như dấu bằng chính xác cho m,n,k hữu hạn, vì các trạng thái bit có tương quan (cùng số phép băm đã tạo ra các bit 1).

### 5.3. Công thức exact dưới mô hình vị trí lý tưởng

Gọi X là **số bit 1 ngẫu nhiên** sau kn phép đặt bit độc lập trên m vị trí. Khi khóa truy vấn vắng mặt sinh k vị trí hash độc lập đều và độc lập với trạng thái đã xây, xác suất false positive **có điều kiện X** bằng (X/m)^k. Vì vậy xác suất chính xác dưới **mô hình lấy mẫu với hoàn lại** là:

**Pr(FP) = E[(X/m)^k].**

Nói cách khác, có thể tính chính xác bằng phân bố số ô đã được chiếm trong bài toán ném kn quả bóng vào m hộp. Xấp xỉ p≈(E[X]/m)^k thường được sử dụng vì đơn giản, nhưng nói chung **E[Y^k] khác (E[Y])^k**.

Công thức exact trên cũng phụ thuộc vào giả thiết các vị trí truy vấn độc lập với trạng thái lọc. Một cài đặt dùng **double hashing** từ hai giá trị băm thường không tạo ra k vị trí hoàn toàn độc lập, nên công thức lý tưởng là **mô hình dự đoán**, không phải cam kết xác suất tuyệt đối cho mọi tập khóa và seed.

### 5.4. Ảnh hưởng của ba tham số

- **Tăng m khi n,k cố định:** mỗi khóa chiếm ít tỷ lệ bit hơn, p_FP thường giảm.
- **Tăng n khi m,k cố định:** thêm nhiều bit 1, p_FP tăng, tiến gần 1 khi bão hòa.
- **Tăng k khi m,n cố định:** ban đầu có thể giảm p_FP vì truy vấn đòi nhiều bit 1; nhưng k quá lớn làm bộ lọc bão hòa nhanh hơn, khiến p_FP lại tăng.

**Không kết luận “càng nhiều hàm băm càng tốt”.** Có một k tối ưu theo m/n.

## 6. Chọn số bit m và số hash k theo mục tiêu

Với p≈(1−e^(−kn/m))^k, cho m,n cố định, xem k là biến liên tục và lấy cực tiểu (đạo hàm log p). Điều kiện cực tiểu đạt khi khoảng **một nửa bit được bật**, nghĩa e^(−kn/m)=1/2. Từ đó:

**k_opt ≈ (m/n)·ln 2.**

Thay trở lại:

**p_opt ≈ (1/2)^k ≈ exp[−(m/n)·(ln 2)^2].**

Nếu muốn false-positive target p_target∈(0,1), số bit cần thiết theo xấp xỉ:

**m ≈ −n·ln(p_target) / (ln 2)^2**,

và **k ≈ (m/n)·ln 2**.

Vì m,k phải là số nguyên, ta làm tròn rồi **tính lại p ước lượng với m,k thực tế**. Bài toán còn liên quan yêu cầu bộ nhớ, độ trễ cho mỗi hash và giới hạn PRNG.

### 6.1. Số liệu tham khảo

| p mục tiêu | Bit/khóa gần đúng m/n | k tối ưu gần đúng |
|---:|---:|---:|
| 10% = 0,1 | 4,79 | 3,32 |
| 1% = 0,01 | 9,59 | 6,64 |
| 0,1% = 0,001 | 14,38 | 9,97 |
| 0,01% = 0,0001 | 19,17 | 13,29 |

Ví dụ với **n=10.000**, mục tiêu **1%**:

- m_min_theory≈95.851 bit (khoảng 11,7 KiB chỉ tính mảng bit, chưa tính overhead cấu trúc).
- k gần 6,64, thường làm tròn thành 7 nếu giữ m gần 95.851.
- Nếu chọn m là **lũy thừa 2** để dùng phép bit-mask lấy chỉ số, có thể nâng lên m=131.072 bit (=16.384 byte, đúng 16 KiB cho nội dung bit).
- Với m=131.072 và n=10.000, k≈9,09 ⇒ chọn **9 hash probes**.
- Dư dung lượng do làm tròn m khiến false-positive estimate **thấp hơn mục tiêu 1%**, đổi lại dùng nhiều bit hơn.

Mã Java phía dưới chọn m là lũy thừa của 2 và h₂ **lẻ** để các vị trí `(h₁+i·h₂) mod m` của **một khóa** không lặp trong k≤m lượt. Điều này tiện về thực thi nhưng **khác mô hình k phép băm độc lập với hoàn lại** dùng trong công thức xác suất; công thức mục 5–6 chỉ được ghi nhãn là **ước lượng lý tưởng**, còn tỷ lệ đo thực tế phụ thuộc hàm băm và phân bố truy vấn.

### 6.2. Tính số byte bộ nhớ

Mảng bit m phần tử cần xấp xỉ **ceil(m/8) byte** cho payload, cộng overhead của đối tượng, mảng và metadata. 131.072 bit cần 16.384 byte payload. Một HashSet lưu 10.000 chuỗi thường phải giữ khóa, bảng bucket, object header và tham chiếu; Bloom có thể rẻ hơn đáng kể nhưng **không cung cấp danh sách khóa hay kết quả membership chính xác**.

### 6.3. Ngưỡng mục tiêu không phải bảo đảm tuyệt đối

Nếu bộ lọc được thiết kế cho 10.000 khóa phân biệt mà sau đó chèn 100.000 khóa phân biệt, p thực tế có thể tăng rất nhiều. Các tham số phải dựa trên **số khóa phân biệt dự kiến**, không phải số sự kiện trong stream nếu stream chứa nhiều bản sao.

## 7. Giá trị dương tính giả trong đo lường thực tế

Khi đã có một tập khóa đúng E dùng làm oracle, với bộ Q các truy vấn bảo đảm **không** thuộc E, tính:

**FPR_thực nghiệm = FP / |Q|**, trong đó FP là số truy vấn absent được Bloom trả true.

Đây là **tỷ lệ trên một mẫu truy vấn cụ thể**, không nhất thiết bằng xác suất lý tưởng. Nếu chỉ thử 100 truy vấn mà mục tiêu p≈0,001, không thấy false positive nào cũng là việc hoàn toàn bình thường.

Không tính **TP** (khóa đã thêm được trả true) vào mẫu absent; nếu đưa TP vào mẫu này, mẫu số không còn đúng định nghĩa FPR. Không lấy câu trả true làm sự kiện chắc chắn có tồn tại.

### 7.1. “False-positive probability” phụ thuộc gì?

Nếu tất cả truy vấn absent được lấy ngẫu nhiên theo một mô hình nhất định, ta có thể nói xác suất trung bình của FP theo các lựa chọn hash/truy vấn của mô hình đó. Một tập truy vấn được thiết kế có chủ đích để va chạm có thể có FPR thực nghiệm cao hơn rất nhiều.

Không nên công bố “p=1%” như **định mức bảo mật** trước đối thủ có thể chọn khóa thích nghi và biết hash/seed. Nếu dùng bộ lọc chống đầu vào độc hại, phải có threat model và giải pháp hash/secret phù hợp; một biến thể Bloom với `java.util.Random` hoặc một seed công khai không tự tạo bảo đảm mật mã.

### 7.2. Tỷ lệ bit đang bật (*fill ratio*)

Gọi x là số bit bằng 1, khi đó fill=x/m. Với mô hình hash lý tưởng:

**E[fill]≈1−e^(−kn/m).**

Ước lượng số khóa phân biệt dựa trên fill (khi chưa bão hòa) có thể dùng:

**n_hat≈−(m/k)·ln(1−fill).**

Đây là **ước lượng**, không phải số đếm chính xác. Khi fill=1, log(0) dẫn đến +Infinity (bộ lọc bão hòa, không thể khôi phục số khóa từ mảng bit). Khi fill gần 1, ước lượng rất nhạy với biến động nhỏ.

## 8. Ngẫu nhiên, hash và biểu diễn khóa

### 8.1. Hàm băm ổn định

Mọi add/query phải sử dụng **cùng chuẩn hóa và mã hóa khóa**. Ví dụ ký tự tiếng Việt có thể được biểu diễn bằng Unicode composed hoặc decomposed; nếu ứng dụng xem chúng là cùng khóa, hãy chuẩn hóa Unicode theo một quy tắc cụ thể **trước khi** gọi Bloom. Nếu ứng dụng phân biệt hoa/thường, đừng âm thầm lowercase; nếu ứng dụng muốn so khớp không phân biệt hoa/thường, phải dùng cùng locale/rule ở cả hai nơi.

Mã Java dùng UTF-8 cho các chuỗi nhận vào và không tự chuẩn hóa, do đó `"A"` và `"a"` là hai khóa khác nhau theo hợp đồng API.

### 8.2. k hàm băm độc lập so với double hashing

Tính k hash thật sự độc lập có thể tốn nhiều chi phí. Một kỹ thuật thường gặp tạo hai giá trị h₁,h₂ rồi sinh:

**h_i(x) = (h₁(x) + i·h₂(x)) mod m.**

Đây gọi là **double hashing**. Nó có thể cho hiệu năng tốt và gần công thức lý tưởng trong nhiều bài thực tế, nhưng những vị trí của cùng một khóa **không độc lập**: chúng là một cấp số cộng modulo m.

Ví dụ với m là lũy thừa 2, nếu h₂ lẻ thì gcd(h₂,m)=1 và các vị trí h₁+i·h₂ khác nhau cho 0≤i<m. Nếu m không là lũy thừa 2, chọn h₂ lẻ chưa đủ để bảo đảm gcd(h₂,m)=1. Mã Java buộc m là lũy thừa 2 và k≤m để giữ tính chất này.

### 8.3. Cách thực tế chọn hash

- Ưu tiên hàm băm chất lượng cao, ổn định, có phân bố tốt trên kiểu khóa thực tế; đánh giá bằng benchmark/corpus phù hợp.
- Ghi phiên bản/hash seed cùng bộ lọc khi serialize/khôi phục.
- Nếu dùng seed bí mật hay MAC để phòng tấn công, cần thiết kế và thư viện mật mã phù hợp; **hash minh họa FNV + avalanche trong Java không phải hash mật mã**.
- Nếu cần đầu ra deterministic giữa các JVM, tránh dựa vào object identity hoặc thứ tự ngẫu nhiên không kiểm soát; hash byte UTF-8 với thuật toán rõ ràng.
- Đừng đánh đồng kỹ thuật xây bitset đúng với đảm bảo độc lập thống kê của mọi phép băm.

## 9. Xóa khóa: vì sao Bloom filter thường không hỗ trợ?

Giả sử A và B cùng băm tới một bit j. Nếu xóa A bằng cách đặt B[j]=0, truy vấn B có thể nhận false dù B đã được thêm trước đó. Điều này phá bảo đảm **không false negative**.

### 9.1. Counting Bloom filter

Thay mỗi bit bằng bộ đếm. Khi thêm khóa, tăng các counter được hash chọn; khi xóa một **khóa đang hiện diện**, giảm những counter ấy; nếu mọi counter tương ứng >0 mới nhận có thể tồn tại.

**Lưu ý quan trọng:**

- Chỉ xóa khi biết khóa thật sự có trong tập gốc (tầng dữ liệu chính xác phải xác nhận). Nếu xóa một khóa **chưa từng được thêm** nhưng Bloom trả maybe vì FP, việc giảm counter có thể xóa đóng góp của khóa khác và tạo false negative.
- Phải tránh tràn/underflow counter, xử lý duplicate insert/remove và đảm bảo các thao tác đồng thời đúng.
- Counting Bloom tốn nhiều bộ nhớ hơn do mỗi vị trí cần nhiều bit đếm.
- Với sai sót thao tác, tính chất “no false negative” không còn đúng.

### 9.2. Stable / sliding Bloom và aging

Một số biến thể hỗ trợ luồng không giới hạn bằng cách **quên dần** dấu vết cũ, giảm bão hòa hoặc duy trì cửa sổ thời gian. Khi phần tử cũ bị quên, truy vấn nó có thể trả false: đây là đánh đổi có chủ đích và phải được mô tả là **có false negative** đối với toàn lịch sử, chứ không được gán tính chất của Bloom insertion-only cho nó.

### 9.3. Reset toàn bộ khác xóa từng khóa

`clear()` đặt **mọi bit** thành 0, tạo bộ lọc rỗng mới. Nó không phải phép xóa riêng một khóa, và mọi khóa đã thêm trước reset sẽ không còn được bảo đảm trả true. Mã Java có thao tác reset để kiểm thử, nhưng không cung cấp `remove(key)`.

## 10. Hợp nhất Bloom filter và bài toán phân tán

Hai Bloom filter chỉ có thể hợp nhất trực tiếp bằng phép OR mảng bit nếu chúng sử dụng **cùng kích thước m, cùng số hash k, cùng hàm/hash seed và cách biểu diễn khóa**. Khi đó:

**B_union = B₁ OR B₂.**

Mọi khóa đã thêm ở một trong hai phía vẫn có đủ bit 1 nên **không xuất hiện false negative** vì phép OR, nhưng các bit 1 tăng và xác suất FP của bộ lọc hợp có thể tăng. Không lấy n₁+n₂ làm chính xác số khóa phân biệt khi hai tập có giao nhau.

Với bộ lọc khác seed hoặc m,k khác, OR thẳng không có ý nghĩa vì cùng khóa ánh xạ tới các vị trí khác nhau. Cần khởi tạo lại từ tập khóa gốc nếu muốn thay thông số; thông thường Bloom filter **không lưu khóa** để tự rehash.

### 10.1. Giao hai bộ lọc bằng AND có đúng không?

Nếu hai bộ lọc cùng cấu hình, phép **AND bitset** vẫn giữ đủ bit của mọi khóa thật sự thuộc **giao của hai tập khóa**, vì khóa ấy được chèn ở cả hai bên. Tuy nhiên AND bitset không tạo ra trạng thái tương đương với một Bloom filter xây từ giao khóa: các bit có thể còn bằng 1 do các khóa khác nhau tạo ra ở hai phía, khiến vẫn có FP. Không dùng AND bitset để liệt kê giao hoặc suy ra số khóa giao chính xác.

Với hai bộ lọc không tương thích seed/hashes, phép AND thậm chí có thể phá tính không FN cho khóa chung. Tương tự, một mảng bit 0/1 không hỗ trợ phép trừ chính xác hai tập.

## 11. Dữ liệu luồng vượt dung lượng thiết kế

Vì số bit cố định, bộ lọc insertion-only chịu rủi ro **bão hòa** khi số khóa phân biệt tăng mãi. Một số hướng xử lý:

1. **Phân hoạch thời gian:** tạo Bloom riêng theo ngày/tuần hoặc cửa sổ dữ liệu; truy vấn có thể phải kiểm nhiều bộ lọc (FPR tổng có thể tăng).
2. **Scalable Bloom filter:** khi một tầng gần đầy, tạo tầng mới cho phần tử tiếp theo và kiểm qua tất cả tầng. Cần phân bổ ngân sách p theo các tầng để khống chế FPR toàn hệ.
3. **Counting/stable Bloom:** dùng khi có nhu cầu xóa/quên, nhưng phải chấp nhận chi phí bộ nhớ hoặc false negatives cho dữ liệu lịch sử.
4. **Cuckoo filter hoặc biến thể tương đương:** có thể hỗ trợ xóa trong những điều kiện cụ thể; không thay được mọi thuộc tính của Bloom bằng một phép đổi tên.
5. **Ước lượng fill và theo dõi FPR thực nghiệm:** thiết lập cảnh báo khi tải vượt thiết kế rồi xây lại hoặc mở rộng qua dữ liệu nguồn chính xác.

Bloom filter không phải bộ lưu trữ bền vững duy nhất của tập: nếu đã vứt toàn bộ khóa gốc, khi cần thay m/k/seed, ta không thể tái tạo chính xác nội dung lọc cho mọi khóa từ mảng bit đơn thuần.

## 12. Tính đúng, chi phí và lựa chọn Bloom filter

| Đặc tính | Bloom insertion-only | HashSet chính xác |
|---|---|---|
| Truy vấn chưa thuộc tập | Có thể trả true (FP) | Trả false chính xác theo equality |
| Truy vấn đã thêm | Luôn true khi giữ đúng giả thiết | True |
| Liệt kê khóa | Không | Có |
| Xóa riêng một khóa | Không an toàn trên bitset chuẩn | Có |
| Bộ nhớ | m bit cố định, nhỏ theo thiết kế | Phụ thuộc số khóa và dữ liệu |
| Thời gian add/query | O(|key bytes|+k), bit probes k | Trung bình phụ thuộc hash, bucket/equality |
| Chi phí khi quá tải | FPR tăng, có thể bão hòa | Dung lượng thường tăng hoặc cần rehash |
| Dùng trước database | Chặn truy vấn chắc chắn vắng mặt | Tầng xác minh chính xác |

Các công thức k và m tối ưu dựa vào **mô hình hash lý tưởng**, trong khi một implementation thực tế cần kiểm chất lượng hash, bộ nhớ và p thực nghiệm trên phân bố khóa thật.

**Không áp dụng Bloom filter cho những nơi một câu false positive được coi là xác nhận cuối cùng và dẫn tới thiệt hại trực tiếp.** Hãy dùng nó làm lớp **lọc trước** khi một nguồn dữ liệu chính xác tiếp nhận trách nhiệm quyết định.



## 13. Java 17 hoàn chỉnh: Bloom filter, phép đo FPR và test

Chương trình sau dùng `BitSet` để lưu m bit, khởi tạo m từ số khóa phân biệt dự kiến và target FPP, tự chọn k, hỗ trợ `add`, `mightContain`, ước lượng FPP và số khóa từ fill, reset toàn bộ và phép hợp OR **chỉ với bộ lọc tương thích**.

Để có bộ lọc đơn giản và test được, mã chọn m là **lũy thừa của 2** và dùng **double hashing với bước lẻ** trên hai hash 32-bit lấy từ chuỗi UTF-8. Đây là **hàm băm phi mật mã cho học thuật**; số liệu `approximateFpp` được ghi rõ là **ước lượng theo mô hình lý tưởng**, không phải định lý xác suất chính xác của phương pháp double hashing trong mã.

Lưu tên file `BloomFalsePositiveDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.BitSet;
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Random;
import java.util.Set;

public final class BloomFalsePositiveDemo {
    private BloomFalsePositiveDemo() {}

    static final class BloomFilter {
        static final int MAX_BITS = 1 << 24;
        static final double LN2 = Math.log(2.0);

        final int bitCount;
        final int hashCount;
        final int seed;
        final BitSet bits;

        private BloomFilter(int bitCount, int hashCount, int seed) {
            if (bitCount < 2 || bitCount > MAX_BITS
                    || Integer.bitCount(bitCount) != 1
                    || hashCount < 1 || hashCount > 64
                    || hashCount > bitCount) {
                throw new IllegalArgumentException(
                    "power-of-two bits, 1..64 hashes, hashes<=bits"
                );
            }
            this.bitCount = bitCount;
            this.hashCount = hashCount;
            this.seed = seed;
            this.bits = new BitSet(bitCount);
        }

        // Budget based on ideal independent-hash approximation.
        static BloomFilter forExpectedInsertions(
                int expectedUnique, double targetFpp, int seed) {
            if (expectedUnique < 1 || expectedUnique > 100_000
                    || !Double.isFinite(targetFpp)
                    || !(targetFpp > 0.0 && targetFpp < 1.0)) {
                throw new IllegalArgumentException(
                    "expectedUnique 1..100000, targetFpp in (0,1)"
                );
            }

            double desiredBits = -expectedUnique
                    * Math.log(targetFpp) / (LN2 * LN2);
            if (!Double.isFinite(desiredBits)
                    || desiredBits > MAX_BITS) {
                throw new IllegalArgumentException("bit budget exceeded");
            }

            int m = 2;
            while (m < desiredBits) m <<= 1;
            int k = Math.max(1,
                (int) Math.round((double) m / expectedUnique * LN2));
            if (k > 64 || k > m) {
                throw new IllegalArgumentException("hash budget exceeded");
            }
            return new BloomFilter(m, k, seed);
        }

        // Stable 32-bit non-cryptographic hash over UTF-8 bytes.
        private static int hash32(String key, int salt) {
            int h = 0x811c9dc5 ^ salt;
            byte[] bytes = key.getBytes(StandardCharsets.UTF_8);
            for (byte b : bytes) {
                h ^= (b & 0xff);
                h *= 0x01000193;
            }
            h ^= h >>> 16;
            h *= 0x7feb352d;
            h ^= h >>> 15;
            h *= 0x846ca68b;
            h ^= h >>> 16;
            return h;
        }

        // m is a power of 2. Odd step => distinct probes if k<=m.
        private int[] hashes(String key) {
            Objects.requireNonNull(key, "key");
            int first = hash32(key, seed ^ 0x9e3779b9);
            int step = hash32(key, seed ^ 0x7f4a7c15) | 1;
            int[] result = new int[hashCount];
            for (int i = 0; i < hashCount; i++) {
                result[i] = (first + i * step) & (bitCount - 1);
            }
            return result;
        }

        void add(String key) {
            for (int index : hashes(key)) bits.set(index);
        }

        boolean mightContain(String key) {
            for (int index : hashes(key)) {
                if (!bits.get(index)) return false;
            }
            return true;
        }

        int bitsSet() { return bits.cardinality(); }

        double fillRatio() {
            return (double) bitsSet() / bitCount;
        }

        // Ideal-hash EXponential approximation, not an exact FPR
        // guarantee for this deterministic double-hash scheme.
        double approximateFpp(int distinctAdded) {
            if (distinctAdded < 0) {
                throw new IllegalArgumentException("negative n");
            }
            double occupancy = -Math.expm1(
                -(double) hashCount * distinctAdded / bitCount);
            return Math.pow(occupancy, hashCount);
        }

        // Approximate unique item cardinality from occupied bits.
        // 100% full => cannot recover a finite cardinality.
        double estimateDistinct() {
            double fill = fillRatio();
            if (fill >= 1.0) return Double.POSITIVE_INFINITY;
            return -(double) bitCount / hashCount * Math.log1p(-fill);
        }

        void clearAll() { bits.clear(); }

        void mergeFrom(BloomFilter other) {
            Objects.requireNonNull(other, "other");
            if (bitCount != other.bitCount
                    || hashCount != other.hashCount
                    || seed != other.seed) {
                throw new IllegalArgumentException(
                    "incompatible Bloom filters"
                );
            }
            bits.or(other.bits);
        }
    }

    private static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }

    private static void verifyExactInsertions(
            BloomFilter filter, Set<String> exact) {
        for (String key : exact) {
            check(filter.mightContain(key),
                "false negative for inserted member: " + key);
        }
    }

    public static void main(String[] args) {
        BloomFilter bloom = BloomFilter.forExpectedInsertions(
            10_000, 0.01, 492);

        // Every inserted item must remain a positive membership query.
        Set<String> exact = new HashSet<>();
        for (int i = 0; i < 10_000; i++) {
            String key = "member-" + i;
            bloom.add(key);
            exact.add(key);
        }
        verifyExactInsertions(bloom, exact);

        int beforeDuplicate = bloom.bitsSet();
        bloom.add("member-123");
        check(bloom.bitsSet() == beforeDuplicate,
            "repeated insertion changed the bitset");

        // These strings were never inserted. A positive response is FP.
        int falsePositives = 0;
        for (int i = 0; i < 20_000; i++) {
            String absent = "absent-" + i;
            check(!exact.contains(absent), "test-set overlap");
            if (bloom.mightContain(absent)) falsePositives++;
        }

        double predicted = bloom.approximateFpp(exact.size());
        double measured = falsePositives / 20_000.0;
        check(Math.abs(predicted - measured) < 0.005,
            "measured FPP very far from simple model");
        check(bloom.bitsSet() <= bloom.bitCount,
            "bit count out of bounds");

        System.out.printf(Locale.ROOT,
            "Design m=%d, k=%d%n", bloom.bitCount, bloom.hashCount);
        System.out.println("Inserted members all maybe: true");
        System.out.println("Duplicate add leaves bits unchanged: true");
        System.out.printf(Locale.ROOT,
            "Ideal FPP estimate: %.6f%n", predicted);
        System.out.printf(Locale.ROOT,
            "Observed FP: %d/20000 (%.6f)%n",
            falsePositives, measured);
        System.out.printf(Locale.ROOT,
            "Estimated distinct from fill: %.0f%n",
            bloom.estimateDistinct());

        // Deliberate saturation: every query becomes 'maybe'.
        BloomFilter tiny = new BloomFilter(8, 3, 7);
        for (int i = 0; i < 100 && tiny.bitsSet() < 8; i++) {
            tiny.add("fill-" + i);
        }
        check(tiny.bitsSet() == 8, "toy filter should saturate");
        check(tiny.mightContain("never-added"),
            "saturated Bloom must return true");
        System.out.println(
            "Saturated unseen key is false positive: true");

        // Union only if bit count, hash count and hash seed match.
        BloomFilter left = new BloomFilter(256, 4, 77);
        BloomFilter right = new BloomFilter(256, 4, 77);
        left.add("left-only");
        right.add("right-only");
        left.mergeFrom(right);
        check(left.mightContain("left-only")
                && left.mightContain("right-only"),
            "merge lost an inserted key");
        System.out.println("Compatible OR union: true");

        boolean mismatchRejected = false;
        try {
            left.mergeFrom(new BloomFilter(256, 4, 78));
        } catch (IllegalArgumentException expected) {
            mismatchRejected = true;
        }
        check(mismatchRejected, "mismatched seed accepted");
        System.out.println("Incompatible seed rejected: true");

        bloom.clearAll();
        check(bloom.bitsSet() == 0
                && !bloom.mightContain("member-123"),
            "clear should make the filter empty");
        System.out.println("Clear resets entire filter: true");

        Random random = new Random(4922026L);
        for (int trial = 0; trial < 1_000; trial++) {
            int plan = 1 + random.nextInt(70);
            double target = new double[] {0.1, 0.03, 0.01, 0.005}[
                random.nextInt(4)];
            BloomFilter test = BloomFilter.forExpectedInsertions(
                plan, target, random.nextInt());
            Set<String> inserted = new HashSet<>();

            int events = random.nextInt(101);
            for (int j = 0; j < events; j++) {
                String key = "event-" + random.nextInt(60);
                inserted.add(key);
                test.add(key);
                verifyExactInsertions(test, inserted);
            }

            double estimate = test.approximateFpp(inserted.size());
            check(estimate >= 0 && estimate <= 1,
                "invalid ideal FPP estimate");
            check(test.bitsSet() >= 0
                    && test.bitsSet() <= test.bitCount,
                "invalid bit count");
            check(test.estimateDistinct() >= 0.0,
                "invalid cardinality estimator");

            BloomFilter partner = new BloomFilter(
                test.bitCount, test.hashCount, test.seed);
            partner.add("partner-" + trial);
            test.mergeFrom(partner);
            verifyExactInsertions(test, inserted);
            check(test.mightContain("partner-" + trial),
                "union lost partner member");
        }

        System.out.println("Random insertion/union tests: 1000 PASS");
    }
}
```

### 13.1. Biên dịch và chạy

```bash
javac -encoding UTF-8 BloomFalsePositiveDemo.java
java BloomFalsePositiveDemo
```

**Đầu ra xác định với thuật toán băm và seed trong chương trình:**

```text
Design m=131072, k=9
Inserted members all maybe: true
Duplicate add leaves bits unchanged: true
Ideal FPP estimate: 0.001841
Observed FP: 39/20000 (0.001950)
Estimated distinct from fill: 9997
Saturated unseen key is false positive: true
Compatible OR union: true
Incompatible seed rejected: true
Clear resets entire filter: true
Random insertion/union tests: 1000 PASS
```

### 13.2. Đọc đúng từng dòng kết quả

- `Design m=... k=...` cho biết bitCount đã được làm tròn lên lũy thừa 2 và k được tính lại từ m/n. Đây không nhất thiết đúng số bit tối thiểu theo công thức lý thuyết chưa làm tròn.
- `Inserted members all maybe: true` và phép kiểm nội bộ qua `HashSet` là kiểm chứng **không false negatives** trên 10.000 khóa đã thêm; Bloom không tự biết danh sách này, HashSet chỉ có mặt trong test.
- `Duplicate add leaves bits unchanged: true` minh họa idempotence của phép đặt bit. **Số lần gọi add không đồng nghĩa số khóa phân biệt.**
- `Ideal FPP estimate` là công thức \( (1-e^{-kn/m})^k \) cho n=10.000. `Observed FP` được đo trên đúng 20.000 chuỗi `absent-i` chắc chắn chưa thêm. Không được đồng nhất hai dòng.
- `Estimated distinct from fill` suy từ tỷ lệ bit 1, chỉ là ước lượng. Nó không đồng nhất với con số chính xác HashSet.size() ngay cả khi bitset hoạt động đúng.
- `Saturated unseen key is false positive: true` minh họa rõ FP: trong bộ lọc toy m=8, mọi bit đã bằng 1, nên cả `never-added` (chưa từng được thêm) cũng trả maybe.
- `Compatible OR union: true` cho thấy OR giữ khả năng trả maybe cho các khóa hai phía; nếu đổi seed/k/m thì không được ghép trực tiếp.
- `Clear resets entire filter: true` là reset tất cả bit; không có phương thức remove(key) vì xóa bit có thể tạo false negative cho khóa khác.
- `Random insertion/union tests` kiểm tính nhất quán trên nhiều chuỗi thao tác, bao gồm duplicate, query sau mỗi add và hợp nhiều bộ lọc.

### 13.3. Giới hạn của kiểm thử thực nghiệm

Trong chương trình, tỷ lệ FP đo được trên mẫu absent có thể **lệch** so với công thức xấp xỉ lý tưởng vì hash double có tương quan và số lượng truy vấn hữu hạn. Kiểm tra sai khác <0,005 trong demo là một **sanity check cho cấu hình/đầu vào cụ thể**, không phải lời hứa rằng mọi bộ lọc Bloom dùng code này luôn có FPR gần công thức trong mọi môi trường.

Bộ test ngẫu nhiên 1.000 ca dùng seed 4922026 để tạo cấu hình và sự kiện; mỗi lần add đều đối chiếu HashSet để bắt false negative. Ngoài ra kiểm bộ lọc sau OR union. Tuy nhiên **không** suy ra một chứng minh lý thuyết xác suất từ 1.000 test.

Chương trình giới hạn dung lượng tối đa m=2^24 bit và k≤64 theo nhu cầu trình diễn; đây **không** phải giới hạn toán học của Bloom filter. Khi n rất lớn và mục tiêu p cực nhỏ, nên dự trù dung lượng, thời gian hash và chính sách mở rộng thay vì cấp phát vô hạn hoặc âm thầm bỏ phần tử.

## 14. Các lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Trả “chắc chắn tồn tại” khi Bloom=true | False positive biến thành kết quả sai | Bloom=true phải xác minh tầng chính xác |
| Cho rằng Bloom không có false positives | Hiểu sai bản chất | Phân biệt true positive và false positive |
| Tự xóa bit khi remove(x) | Tạo false negative với khóa khác | Dùng counting Bloom có điều kiện hoặc rebuild |
| Dùng seed khác khi query | Có thể tạo false negatives | Đồng bộ m,k,seed và phiên bản hash |
| Chuẩn hóa Unicode không nhất quán | Khóa logic giống nhau băm khác | Cùng chuẩn hóa và UTF-8 |
| Đếm mọi lần add là khóa phân biệt n | Ước lượng FPR sai | Ước lượng distinct hoặc dùng nguồn exact |
| Dùng n dự kiến nhưng n thật lớn gấp 10 | Bộ lọc dễ bão hòa | Theo dõi fill và scale/rebuild |
| Coi p≈... là dấu bằng chính xác | Bỏ qua tương quan occupancy | Ghi rõ mô hình xấp xỉ |
| Cho k tăng vô hạn | Bit nhanh bão hòa | Chọn k≈(m/n)ln2 |
| Lấy bitIdx bằng signed % và không xử lý âm | Chỉ số âm, lỗi truy cập | floorMod/unsigned hoặc mask khi m lũy thừa 2 |
| Dùng h₂ chẵn với m=2^q | Có thể lặp trước m vị trí | Bước lẻ để gcd(h₂,m)=1 |
| Đổi m nhưng giữ bitset cũ | Vị trí hash thay đổi | Rebuild bằng khóa nguồn |
| OR hai filter khác seed/m/k | Gây sai ý nghĩa membership | Chỉ OR compatible |
| Dùng AND bitset để “lấy danh sách giao” | Không có danh sách khóa, vẫn FP | Xác minh chính xác ở tầng nguồn |
| Cho rằng filter đo cardinality chính xác | Chỉ có bitset, collision | Dùng estimator có sai số/nguồn exact |
| Không xử lý fill=1 trong estimator | ln(0) gây vô cực | Báo saturation rõ |
| Nhầm false-positive rate với tỷ lệ true trong mọi query | Trộn cả khóa tồn tại | Chỉ tính trên absent queries |
| Dùng hash phi mật mã trước adversarial queries | Đối thủ có thể chủ động tìm va chạm | Threat model và thiết kế hash có khóa bảo mật |
| Dùng counting Bloom xóa khóa chưa từng có | Bộ đếm giảm sai, có false negative | Xác minh membership thật trước delete |
| Không đồng bộ thao tác bit trên nhiều luồng | Lost updates hoặc trạng thái lỗi | Thiết kế concurrency/atomicity |
| Serialization chỉ lưu bitset | Quên hash/version/seed | Lưu toàn bộ metadata |
| Test một trường hợp không thấy FP rồi kết luận “FP=0” | Mẫu quá nhỏ | Dùng phân tích và đo đủ mẫu |
| Dùng Bloom như nguồn dữ liệu duy nhất | Không thể liệt kê/rebuild khóa | Giữ kho dữ liệu chính xác nếu cần |
| Nhầm m bit với m byte | Tính bộ nhớ sai 8 lần | Payload khoảng ceil(m/8) byte |

## 15. Bài tập có đáp án

**Bài 1.** Bloom filter chứa gì? *Đáp án:* mảng bit và quy tắc k vị trí hash cho mỗi khóa, không chứa danh sách khóa gốc.

**Bài 2.** Khi Bloom trả false trong insertion-only chuẩn, có nghĩa gì? *Đáp án:* khóa chắc chắn chưa từng được add vào bộ lọc hiện tại theo cùng hash/seed.

**Bài 3.** Khi Bloom trả true, kết luận gì? *Đáp án:* khóa có thể đã thêm; vẫn có thể là false positive.

**Bài 4.** Vì sao không có false negatives sau add? *Đáp án:* k bit của khóa đã được đặt 1 và add khác không hạ bit về 0.

**Bài 5.** Vì sao có false positives? *Đáp án:* những khóa khác có thể đã đặt 1 toàn bộ vị trí hash của khóa vắng mặt.

**Bài 6.** Với bitset bão hòa, FPR trên truy vấn absent bằng bao nhiêu? *Đáp án:* 1 (100%).

**Bài 7.** Tính Pr một bit vẫn 0 sau kn phép chọn độc lập. *Đáp án:* (1−1/m)^(kn).

**Bài 8.** Xấp xỉ xác suất một bit 1 là gì? *Đáp án:* 1−e^(−kn/m).

**Bài 9.** Công thức FPR xấp xỉ thường dùng? *Đáp án:* (1−e^(−kn/m))^k.

**Bài 10.** Vì sao công thức FPR trên không phải chính xác cho mọi m,n,k? *Đáp án:* trạng thái các bit có tương quan và hash thực tế có thể không độc lập.

**Bài 11.** Với X là số bit 1, FPR exact trong mô hình query độc lập đều? *Đáp án:* E[(X/m)^k].

**Bài 12.** Với m,n cố định, k gần tối ưu bằng bao nhiêu? *Đáp án:* (m/n)ln2.

**Bài 13.** Khi k gần tối ưu, khoảng bao nhiêu phần trăm bit bằng 1? *Đáp án:* xấp xỉ 50%.

**Bài 14.** Với p mục tiêu 0,01, gần bao nhiêu bit mỗi khóa? *Đáp án:* 9,59 bit/khóa.

**Bài 15.** Với n=10.000 và p≈1%, m lý thuyết gần bao nhiêu? *Đáp án:* 95.851 bit.

**Bài 16.** Nếu làm tròn m lên lũy thừa 2, m thành bao nhiêu? *Đáp án:* 131.072 bit.

**Bài 17.** Với m=131.072,n=10.000, k gần tối ưu? *Đáp án:* 9.

**Bài 18.** 131.072 bit payload bằng bao nhiêu byte? *Đáp án:* 16.384 byte = 16 KiB.

**Bài 19.** Càng tăng k có luôn giảm FP không? *Đáp án:* không, k quá lớn khiến bitset bão hòa.

**Bài 20.** Nếu n thực tế tăng trong khi m,k cố định thì FPR thường thay đổi thế nào? *Đáp án:* tăng dần, có thể tiến gần 1.

**Bài 21.** Vì sao duplicate add không làm tăng số bit 1? *Đáp án:* cùng khóa băm cùng vị trí, các bit đã được bật.

**Bài 22.** Để đo FPR thực nghiệm phải dùng nhóm query nào? *Đáp án:* những khóa chắc chắn chưa thêm (absent queries).

**Bài 23.** Thao tác xóa một bit để bỏ khóa có an toàn? *Đáp án:* không, có thể xóa bit dùng chung.

**Bài 24.** Counting Bloom cần điều kiện gì trước delete? *Đáp án:* xác minh khóa hiện diện thật, kiểm counter không tràn/underflow.

**Bài 25.** Có thể OR hai bộ lọc khác hash seed? *Đáp án:* không, vì các vị trí hash không tương thích.

**Bài 26.** Hợp OR hai filter cùng cấu hình ảnh hưởng FPR thế nào? *Đáp án:* không giảm số bit 1, nên thường tăng hoặc giữ FPR.

**Bài 27.** Vì sao AND bitset không cung cấp giao tập khóa chính xác? *Đáp án:* bit 1 có thể do khóa khác nhau gây ra ở mỗi bộ lọc, còn FP.

**Bài 28.** Công thức ước lượng distinct từ fill x/m? *Đáp án:* n_hat≈−(m/k)ln(1−x/m) khi chưa bão hòa.

**Bài 29.** Khi x=m trong estimator, giá trị ước lượng là gì? *Đáp án:* không hữu hạn (+Infinity) vì log(0).

**Bài 30.** Làm sao tránh false positive ảnh hưởng logic nghiệp vụ? *Đáp án:* kiểm Bloom false để loại chắc chắn vắng; Bloom true phải truy vấn nguồn chính xác.

**Bài 31.** “Dùng Random seed” có tự chứng minh bảo mật trước đối thủ? *Đáp án:* không, cần hash mật mã/keyed design theo threat model.

**Bài 32.** Khi có khóa Unicode, cần đồng nhất điều gì? *Đáp án:* chuẩn hóa và mã hóa chuỗi trước hashing.

**Bài 33.** Double hashing tạo k vị trí độc lập hoàn toàn không? *Đáp án:* không, các vị trí có quan hệ cấp số cộng modulo m.

**Bài 34.** Với m=2^q, chọn h₂ lẻ có tác dụng gì? *Đáp án:* gcd(h₂,m)=1, các probe không lặp cho k≤m.

**Bài 35.** Bloom filter có thể liệt kê lại mọi khóa từng được add không? *Đáp án:* không, dữ liệu gốc không được lưu.

**Bài 36.** Streaming filter cố định dùng mãi có nguy cơ gì? *Đáp án:* bão hòa và tăng dương tính giả; cần scale/rebuild/aging theo yêu cầu.

## 16. Checklist triển khai đúng

1. Xác định Bloom là **bộ lọc xác suất**, không phải kho thành viên chính xác.
2. Ghi rõ một câu false là “definitely absent”, true là “maybe present”.
3. Chứng minh no-FN chỉ trong mô hình insertion-only và hash/mã hóa ổn định.
4. Đặt n dự kiến theo **khóa phân biệt**, không theo số sự kiện trùng.
5. Chọn p mục tiêu, tính m≈−n ln p/(ln2)² và k≈(m/n)ln2.
6. Sau làm tròn m/k phải tính lại p dự kiến.
7. Phân biệt công thức exact theo occupancy và xấp xỉ phổ biến.
8. Giải thích false-positive probability phụ thuộc mô hình hash và phân bố query.
9. Tính m bit thành byte khi dự trù bộ nhớ; cộng overhead thực tế.
10. Đồng nhất UTF-8/normalization và version hash giữa add, query, reload.
11. Khi double hashing, kiểm tính tương thích bước hash và modulo m.
12. Không dùng hash phi mật mã làm lời hứa chống đầu vào độc hại.
13. Không xóa bit đơn lẻ để delete khóa.
14. Nếu dùng counting filter, xác nhận delete trên khóa hiện diện và kiểm counter.
15. Nếu OR/AND hai filter, kiểm m,k,seed/hàm hash hoàn toàn tương thích.
16. Theo dõi fill ratio, saturation và điều kiện scale khi n vượt dự kiến.
17. FPR đo bằng truy vấn absent; không trộn các true positive vào mẫu số.
18. Tách HashSet/DB chính xác làm oracle để kiểm no-FN.
19. Dùng nhiều dữ liệu test gồm duplicate, empty, Unicode, reset, union, saturation.
20. Khi đặt filter trước DB, Bloom=true phải kiểm nguồn chính xác.

## Kết luận

**Bloom filter** là cấu trúc m bit và k vị trí băm, phù hợp cho luồng dữ liệu khi cần loại nhanh các khóa chắc chắn chưa có với bộ nhớ hạn chế. Bản insertion-only chuẩn có **không âm tính giả** nhờ bit chỉ chuyển 0→1, nhưng có **dương tính giả** vì nhiều khóa có thể bật cùng các bit.

Trong mô hình băm lý tưởng, xác suất dương tính giả xấp xỉ **(1−e^(−kn/m))^k**. Số hash gần tối ưu **k≈(m/n)ln2**, và bộ nhớ cần thiết để đạt mục tiêu p gần **m≈−n ln p/(ln2)²**. Đây là **công thức thiết kế xấp xỉ**, không phải cận chắc chắn trước mọi khóa/seed. Muốn dùng an toàn, hãy theo dõi tải, bảo toàn hash/metadata, tránh xóa bit riêng, và luôn xác minh ở tầng lưu trữ chính xác khi Bloom trả “maybe”.
