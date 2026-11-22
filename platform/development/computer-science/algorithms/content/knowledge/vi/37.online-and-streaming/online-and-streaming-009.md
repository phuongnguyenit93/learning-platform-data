# Count-Min Sketch trên luồng có cập nhật không âm

**Count-Min Sketch (CMS)** là một cấu trúc dữ liệu xác suất dùng để ước lượng **tần suất của một khóa** trong luồng dữ liệu rất lớn mà không cần lưu một bộ đếm riêng cho từng khóa. Trong mô hình **luồng cập nhật không âm** (*cash-register stream*), mỗi sự kiện có dạng `(key, weight)` với `weight>=0`: khóa `key` tăng tần suất thêm `weight`. Nhờ nhiều hàng bộ đếm nhỏ và các hàm băm khác nhau, CMS có thể xử lý luồng chỉ trong bộ nhớ phụ thuộc vào **mức sai số mong muốn**, không phụ thuộc trực tiếp vào số khóa đã xuất hiện.

Đặc điểm quan trọng nhất của CMS theo mô hình này:

- Ước lượng **không bao giờ nhỏ hơn** tần suất thật, miễn số học và cập nhật được thực hiện chính xác.
- Ước lượng có thể **lớn hơn** tần suất thật do các khóa khác va chạm cùng bucket.
- Với một khóa/truy vấn **được cố định trước khi chọn ngẫu nhiên các hàm băm**, sai số cộng có thể được khống chế bằng xác suất.
- Tăng **số cột** giúp giảm nhiễu va chạm; tăng **số hàng độc lập** giúp giảm xác suất trường hợp tất cả hàng đều nhiễu nhiều.
- Hai sketch có **cùng kích thước và chính xác cùng các hàm băm** có thể gộp từng bộ đếm để đại diện cho luồng nối hoặc phân vùng.
- Đây là lời giải **ước lượng điểm** (*point query*), không phải bảng đếm chính xác và không tự liệt kê tất cả khóa phổ biến.

Bài thuộc chủ đề **Trực tuyến và luồng** (*Online and Streaming Algorithms*). Phần sau xây dựng định nghĩa, bất biến, ví dụ tính tay, chứng minh cận sai số, lưu ý tính ngẫu nhiên của hàm băm và một chương trình Java 17+ độc lập có thể chạy để so sánh với oracle đếm bằng `Map`, kiểm thử gộp luồng, dữ liệu không âm và tình huống va chạm có chủ đích.

## 1. Vì sao không dùng Map đếm chính xác cho mọi trường hợp?

Nếu có luồng:

```text
(7,5), (12,3), (7,2), (101,6), (12,1), ...
```

thì cách đếm chính xác là:

```text
frequency[key] += weight
```

Ví dụ khóa 7 nhận 5 rồi 2 nên tần suất hiện tại là 7. `HashMap<Integer,Long>` có thể xử lý cập nhật nhanh trung bình nhưng phải lưu **một mục cho từng khóa phân biệt**. Nếu mỗi giây có hàng triệu khóa mới và chỉ có bộ nhớ nhỏ cho một cửa sổ xử lý, số khóa phân biệt có thể vượt ngân sách RAM.

Count-Min Sketch thay Map bằng một bảng kích thước cố định:

```text
depth d hàng
width w cột / hàng

counters[d][w]
```

Mỗi khóa đi vào **một bucket trong từng hàng**; mọi sự kiện tăng bộ đếm của những bucket này. Không có cấu trúc map lưu danh sách tất cả khóa từng xuất hiện.

Đổi lại, CMS không biết trong một bucket đã có những khóa nào. Một truy vấn có thể nhận **tổng tần suất của các khóa bị băm trùng**, nên trả một **ước lượng**, không phải giá trị chính xác.

### 1.1. Mô hình cập nhật cụ thể của bài

Gọi `U` là miền khóa và luồng sự kiện là:

```text
(key_1, weight_1),
(key_2, weight_2),
...,
(key_t, weight_t)

weight_i >= 0.
```

Tần suất thật tại một thời điểm:

```text
f(x) = SUM_{i:key_i=x} weight_i.
```

Tổng khối lượng toàn luồng:

```text
F1 = SUM_{x in U} f(x)
   = SUM_i weight_i.
```

Ở mô hình chỉ có cập nhật không âm, `F1` chính là **tổng số lần tăng trọng số** và bằng chuẩn L1 của vector tần suất. Khi có nhiều sự kiện cùng khóa, **cộng dồn trọng số**, không chỉ ghi dấu “khóa từng xuất hiện”.

Ví dụ:

```text
(7,5), (12,3), (7,2), (101,6)

f(7)=7, f(12)=3, f(101)=6
F1=5+3+2+6=16.
```

**Cần phân biệt rõ:**

- `numberOfEvents=4` là số bản ghi cập nhật.
- `F1=16` là **tổng trọng số**.
- `numberOfDistinctKeys=3` là số khóa khác nhau.
- CMS ước lượng `f(x)`, không mặc định trả ba đại lượng trên như một kiểu dữ liệu duy nhất.

Với `weight=0`, trạng thái không đổi. **Không có phép giảm trọng số** trong mã Java của bài; nếu dữ liệu có `weight<0`, nó bị từ chối.

### 1.2. Cash-register khác turnstile stream

Tên **cash-register model** thường dùng cho mọi cập nhật không âm. Mô hình **turnstile** cho phép cập nhật tăng và giảm; **strict turnstile** còn yêu cầu tần suất thật của mỗi khóa không âm tại mọi thời điểm. Một số kết quả về linear sketch có thể thích nghi trong strict turnstile, nhưng phải chứng minh bất biến, phép cập nhật và độ an toàn số học riêng. Trong **general turnstile**, tần suất có thể âm và việc cộng các khóa khác vào bucket không còn đảm bảo giá trị bucket ≥f(x).

Vì tên bài là **“trên luồng có cập nhật không âm”**, toàn bộ bảo đảm/implementation ở đây chỉ nói về **cập nhật trọng số không âm**. Không gửi update âm vào chương trình rồi viện dẫn định lý overestimate của phiên bản cash-register.

## 2. Cấu trúc bảng băm và thao tác cập nhật

Với `d` hàng và `w` cột, chọn `d` hàm băm:

```text
h_0, h_1, ..., h_{d-1}

h_r: U -> {0,...,w-1}
```

Khởi tạo tất cả `counters[r][c]=0`.

Mỗi sự kiện `(x,weight)` với `weight>=0`:

```text
for r = 0..d-1:
    counters[r][h_r(x)] += weight
```

Một khóa luôn đi vào **một cột ở mỗi hàng**, nhưng có thể trùng cột với những khóa khác. Hai khóa khác nhau có thể trùng ở một hàng, nhiều hàng hoặc **toàn bộ hàng**.

### 2.1. Ví dụ minh họa hai hàng bằng tay

Cho ba khóa A, B, C với tần suất thật:

```text
f(A)=5, f(B)=3, f(C)=2
F1=10.
```

Giả sử các hàm băm ví dụ có kết quả:

| Khóa | Hàng 0 | Hàng 1 |
| --- | ---: | ---: |
| A | bucket 0 | bucket 2 |
| B | bucket 0 | bucket 1 |
| C | bucket 1 | bucket 2 |

Kết quả bộ đếm khác 0:

```text
Hàng 0: bucket 0 = f(A)+f(B)=8
        bucket 1 = f(C)=2

Hàng 1: bucket 1 = f(B)=3
        bucket 2 = f(A)+f(C)=7.
```

Truy vấn CMS lấy **nhỏ nhất** trong các hàng:

```text
estimate(A)=min(8,7)=7   (thật 5, nhiễu +2)
estimate(B)=min(8,3)=3   (thật 3, chính xác)
estimate(C)=min(2,7)=2   (thật 2, chính xác).
```

Các giá trị băm ở ví dụ này được **đặt trước để minh họa va chạm**, không phải bảng đầu ra của bộ sinh hàm băm trong Java.

### 2.2. Vì sao phải lấy min mà không lấy max hay trung bình?

Đối với một khóa x, mỗi hàng có:

```text
counters[r][h_r(x)]
  = f(x) + noise_r(x),

noise_r(x) =
  SUM_{y != x, h_r(y)=h_r(x)} f(y).
```

Vì mọi `f(y)>=0`, nên:

```text
noise_r(x)>=0
counters[r][h_r(x)]>=f(x).
```

Lấy `min` giữa các hàng sẽ **giảm lượng va chạm tích lũy** mà vẫn không nhỏ hơn `f(x)`. Lấy max thường làm nhiễu tăng; lấy trung bình cũng không tận dụng được hàng ít nhiễu nhất như min.

**Bất biến một phía chính xác:**

```text
For every x and every prefix of nonnegative updates:

    estimate(x) >= f(x).
```

Đây là thuộc tính **tất định** của bảng với mọi hàm băm, **không cần** giả thiết các hàm băm độc lập. Điều kiện: counters không bị tràn số, cập nhật đúng, mọi trọng số không âm, và giá trị đang truy vấn thật sự nằm trong miền khóa được hỗ trợ.

## 3. Truy vấn tần suất điểm

Để ước lượng tần suất của khóa x:

```text
query(x):
    answer = +infinity
    for r=0..d-1:
        answer = min(answer, counters[r][h_r(x)])
    return answer.
```

Với bảng khởi tạo chưa có cập nhật, mọi giá trị là 0 nên `query(x)=0` cho mọi khóa hợp lệ.

Nếu một khóa **chưa từng xuất hiện**, `f(x)=0`; nhưng `estimate(x)` có thể dương nếu toàn bộ bucket mà x tra cứu đều bị những khóa khác làm tăng. Vì vậy:

```text
estimate(x)>0  DOES NOT imply x appeared.
estimate(x)=0  IMPLIES f(x)=0
```

mệnh đề thứ hai dựa trên thuộc tính `estimate(x)>=f(x)>=0`. Cần lưu ý: `estimate(x)=0` chỉ chứng nhận khóa có **tần suất 0** dưới dữ liệu hiện tại; nếu trọng số có thể giảm và dương/âm, logic cần xem lại.

### 3.1. Cập nhật online không cần đợi hết luồng

Mỗi sự kiện mới được áp vào d bộ đếm ngay, sau đó có thể truy vấn. Đây là tính chất **streaming/online**: không cần lưu toàn bộ danh sách sự kiện, và không phải sắp xếp chúng.

Nếu luồng rất dài, có thể giữ sketch trong RAM và gửi thống kê định kỳ. Tuy nhiên CMS chỉ là một cấu trúc dữ liệu: đồng bộ giữa thread, xử lý mất sự kiện, replay sự kiện, chính xác một lần (*exactly-once*) và tính nhất quán khi checkpoint là vấn đề hệ thống **nằm ngoài** chứng minh của CMS thuần túy.

## 4. Sai số cộng và bảo đảm xác suất

Count-Min Sketch **không** bảo đảm ước lượng chính xác từng khóa. Bảo đảm kinh điển có dạng:

```text
For a fixed key x selected independently of the random hashes:

    f(x) <= estimate(x)

and with probability at least 1-delta:

    estimate(x) <= f(x) + epsilon * F1.
```

Trong đó:

- `epsilon>0` là **mức sai số cộng** tính theo tổng khối lượng `F1`.
- `delta` là xác suất **thất bại của cận sai số**, không phải phần trăm dữ liệu bị mất.
- Xác suất được tính theo **các hàm băm ngẫu nhiên chọn lúc khởi tạo**, còn luồng và khóa truy vấn được cố định trong phân tích.
- Bảo đảm nói về **một khóa cố định**, không tự động bảo đảm mọi khóa trong một miền cực lớn cùng chính xác.

### 4.1. Sai số cộng không phải sai số tương đối

Giả sử:

```text
F1=1,000,000
epsilon=0.01

epsilon * F1 = 10,000.
```

Định lý cho một truy vấn cố định nói nhiễu cộng có thể lên tới khoảng 10.000 ở phía trên với xác suất lỗi bị chặn.

- Nếu khóa có `f(x)=500,000`, cận 10.000 là khoảng 2% giá trị thật.
- Nếu khóa có `f(x)=10`, cận 10.000 là rất thô so với giá trị thật.
- Nếu khóa không xuất hiện, `f(x)=0` nhưng vẫn có thể được ước lượng >0.

Vì vậy CMS thích hợp khi cần **ước lượng luồng tần suất với giới hạn bộ nhớ**, đặc biệt quan tâm các khóa có tần suất đủ lớn so với F1. Nó không cung cấp **sai số tương đối epsilon cho mọi khóa nhỏ**.

### 4.2. Công thức kinh điển và biến thể hash trong Java

Trong lý thuyết CMS, nếu mỗi hàng dùng một hàm băm có cận va chạm đủ mạnh, chọn:

```text
width = ceil(e / epsilon)
depth = ceil(ln(1/delta))
```

là cấu hình phổ biến để đạt bảo đảm `epsilon*F1`, `delta`, với e là cơ số log tự nhiên khoảng 2.71828. Các hằng số có thể khác nhau theo giả thiết về họ băm.

**Chương trình Java của bài cố ý dùng cận bảo thủ hơn:**

```text
width = ceil(2e / epsilon)
depth = ceil(ln(1/delta)).
```

Lý do không phải vì CMS bắt buộc cần hệ số 2; đó là để bảo đảm một cận đơn giản khi dùng **hàm băm affine modulo một số nguyên tố rồi lấy modulo width**, nơi kích thước các bucket của trường nguyên tố có thể không đều hoàn toàn.

Miền khóa của mã là:

```text
0 <= key < p,
p = 2,147,483,647 (số nguyên tố).
```

Mỗi hàng dùng hai hệ số ngẫu nhiên `a_r,b_r` trong `[0,p-1]`:

```text
field_r(x) = (a_r*x + b_r) mod p
h_r(x) = field_r(x) mod width.
```

Với a,b **đồng đều và độc lập theo mô hình lý tưởng**, các giá trị `field_r(x)` và `field_r(y)` tại hai khóa khác nhau x≠y là **độc lập đều trên F_p**. Sau bước `%width`, kích thước một bucket nhiều nhất là `ceil(p/width)`, do đó:

```text
Pr[h_r(x)=h_r(y)]
    <= ceil(p/width)/p
    <= 1/width + 1/p
    <= 2/width,  provided width<=p.
```

Hàm khởi tạo kiểm tra `width<=p`. Số cột lấy `ceil(2e/epsilon)` nên:

```text
Pr[collision on a row] <= 2/width <= epsilon/e.
```

**Ghi chú ngẫu nhiên:** Java demo dùng `SplittableRandom(seed)` để tạo hệ số có thể tái lập khi kiểm thử. Vì seed được cố định, bản chạy thực tế là **giả ngẫu nhiên xác định**; các chứng minh xác suất ở đây giả định hệ số được rút **thực sự đồng đều, độc lập**. Không coi `SplittableRandom` là nguồn bảo mật mật mã hoặc một định lý rằng các hệ số giả ngẫu nhiên độc lập hoàn hảo.

## 5. Chứng minh cận sai số từng hàng

Đặt nhiễu hàng r:

```text
Z_r(x) = counters[r][h_r(x)] - f(x)

       = SUM_{y != x} f(y) *
           1[h_r(y)=h_r(x)].
```

Vì `f(y)>=0` và các biến chỉ báo không âm:

```text
Z_r(x) >= 0.
```

Dùng **tuyến tính của kỳ vọng** (không cần độc lập giữa những biến chỉ báo trong cùng hàng):

```text
E[Z_r(x)]
  = SUM_{y != x} f(y) *
          Pr[h_r(y)=h_r(x)]

  <= (2/width) * SUM_{y != x} f(y)

  <= (2/width) * F1
  <= epsilon * F1 / e.
```

Đây là phần cốt lõi: nhiễu **kỳ vọng** của một hàng nhỏ so với `epsilon*F1`. Nhưng từ kỳ vọng **chưa thể kết luận nhiễu từng lần luôn nhỏ**.

### 5.1. Dùng bất đẳng thức Markov

Với `Z_r(x)>=0` và `F1>0`:

```text
Pr[Z_r(x) >= epsilon*F1]
    <= E[Z_r(x)] / (epsilon*F1)
    <= 1/e.
```

Nếu `F1=0`, không có khối lượng cập nhật và mọi bộ đếm bằng 0, nên kết quả đúng chính xác, không cần chia cho `F1`.

### 5.2. Dùng nhiều hàng độc lập

Count-Min Sketch lấy:

```text
estimate(x) = f(x) + min_r Z_r(x).
```

Muốn kết quả có nhiễu lớn, **mọi hàng** đều phải nhiễu lớn. Nếu các hệ số băm của các hàng được chọn **độc lập**, biến cố của từng hàng độc lập khi luồng và x cố định. Do đó:

```text
Pr[estimate(x)-f(x) >= epsilon*F1]
   = Pr[ALL rows have Z_r(x)>=epsilon*F1]

   <= (1/e)^depth.
```

Chọn:

```text
depth=ceil(ln(1/delta))

=> (1/e)^depth <= delta.
```

Kết hợp với bất biến một phía:

```text
f(x) <= estimate(x)

and with probability >= 1-delta:
    estimate(x) < f(x) + epsilon*F1
```

Có thể trình bày kết luận thực tế phổ biến bằng ký hiệu `<=` cho cận sai số cộng; dùng dấu `<` nghiêm ngặt trong suy luận sự kiện không làm thay đổi ý nghĩa bảo đảm.

**Phân vai trò của tham số:**

- **width** chi phối kỳ vọng nhiễu trên **một hàng**.
- **depth** chi phối xác suất **tất cả hàng cùng nhiễu quá lớn**.
- Tăng số hàng không tự giảm số bucket trên một hàng.
- Tăng số cột không thay thế hoàn toàn vai trò khuếch đại xác suất của các hàng độc lập.

## 6. Ví dụ tham số thực tế

Chọn:

```text
epsilon = 0.12
delta   = 0.01
```

Theo phiên bản bảo thủ của bài:

```text
width = ceil(2e/0.12) = 46
depth = ceil(ln(100)) = 5.
```

Bảng có:

```text
46 * 5 = 230 bộ đếm long.
```

Chỉ riêng vùng primitive `long` của counters cần:

```text
230 * 8 = 1,840 bytes,
```

chưa tính object/array overhead, hai mảng hệ số hash, seed/RNG lúc khởi tạo và các biến khác của JVM.

Một truy vấn cố định có bảo đảm lý tưởng:

```text
estimate(x) <= f(x) + 0.12*F1
with probability at least 0.99.
```

Cận này là **cho khóa cố định trước khi rút hash**, không phải cho một khóa được tìm theo cách thích nghi sau khi xem tất cả hàm băm.

### 6.1. Tính toán trên ví dụ 11 sự kiện

Luồng trong mã:

```text
(7,5)
(12,3)
(7,2)
(101,6)
(0,4)
(12,1)
(99,8)
(33,2)
(101,5)
(200,7)
(7,1)
```

Tổng trọng số:

```text
F1 = 5+3+2+6+4+1+8+2+5+7+1
   = 44.
```

Tần suất chính xác:

| Khóa | f(x) |
| ---: | ---: |
| 0 | 4 |
| 7 | 8 |
| 12 | 4 |
| 33 | 2 |
| 99 | 8 |
| 101 | 11 |
| 200 | 7 |

Trong seed minh họa, các truy vấn được in ra trùng số đếm chính xác ở một số khóa. **Đó chỉ là một lần chạy không bị nhiễu đáng kể trên những truy vấn ấy**, không phải tuyên bố sketch luôn chính xác.

### 6.2. Chọn khóa sau khi biết các hàm băm có thể tạo false positive

Một thí nghiệm riêng dùng sketch rất nhỏ:

```text
epsilon=0.9
delta=0.1
width=ceil(2e/0.9)=7
depth=ceil(ln(10))=3.
```

Có nhiều khóa hơn số chữ ký bucket:

```text
signature(x) =
  (h_0(x),h_1(x),h_2(x))

number of possible signatures <= 7^3=343.
```

Theo nguyên lý Dirichlet (*pigeonhole*), nếu kiểm tra đủ 344 khóa phân biệt thì chắc chắn tồn tại hai khóa có **cùng chữ ký ở cả ba hàng**. Mã quét các khóa hợp lệ cho tới khi phát hiện cặp như vậy, trong seed cố định là:

```text
key 3 and key 12
```

Nó tăng:

```text
update(3,10)
```

rồi hỏi khóa 12 chưa xuất hiện:

```text
f(12)=0
estimate(12)=10.
```

Đây là một **false positive của truy vấn ước lượng**: không chứng minh khóa 12 từng xuất hiện. Và ví dụ không mâu thuẫn cận `(epsilon,delta)`, vì cặp khóa đã được **chọn thích nghi sau khi thấy hash**. Bảo đảm xác suất của mục 5 giả định stream/khóa truy vấn cố định **độc lập với việc khởi tạo hash**.

**Không đánh đồng:** Cận `delta=0.1` không nói “chỉ 10% khóa trên toàn miền có thể sai” và cũng không cho phép một đối thủ tra các hash rồi chọn khóa có va chạm với xác suất bị chặn như trường hợp cố định.

## 7. Đảm bảo bộ nhớ, thời gian và giới hạn dữ liệu

Với width `w`, depth `d`:

| Tác vụ | Thời gian | Bộ nhớ |
| --- | --- | --- |
| Khởi tạo bảng | `O(w*d)` | `O(w*d)` |
| Cập nhật một sự kiện `(x,weight)` | `O(d)` | `O(d)` tạm trong Java để kiểm tra overflow nguyên tử |
| Truy vấn một khóa | `O(d)` | `O(1)` tạm |
| Gộp hai sketch cùng schema/hash | `O(w*d)` | `O(w*d)` tạm trong Java để kiểm tra overflow nguyên tử |
| Truy vấn m khóa đã biết | `O(m*d)` | `O(1)` tạm khi xử lý nối tiếp |
| Cấu hình theo epsilon,delta | `O((1/epsilon)*ln(1/delta))` bộ đếm | Cùng bậc |

Trong lý thuyết, vì `w=Theta(1/epsilon)` và `d=Theta(log(1/delta))`, CMS cần:

```text
O((1/epsilon) * log(1/delta))
```

**bộ đếm**, không phải số bit. Nếu tổng trọng số lớn, mỗi bộ đếm cần đủ bit (mã dùng signed long 64 bit), và có thêm tham số hash. Nói “bộ nhớ độc lập hoàn toàn với độ dài stream” là quá mạnh nếu số bit của bộ đếm phải mở rộng để chứa tổng khối lượng không giới hạn.

### 7.1. Giới hạn long và cập nhật nguyên tử

Một luồng có thể chứa hàng tỷ cập nhật có trọng số rất lớn. Nếu `long` bị **overflow**, bộ đếm có thể quay sang âm, phá ngay tính một phía của ước lượng.

Mã Java dùng:

```java
Math.addExact(current, weight)
```

để **ném ArithmeticException** khi cộng tràn. Trong `update`, mã tính trước **giá trị mới của tổng F1 và tất cả d bucket**, sau đó mới ghi; nếu có lỗi ở bất cứ đâu thì không có cập nhật dở dang. Phương thức `mergeFrom` cũng tính trước toàn bộ bảng kết quả rồi mới commit, tránh việc gộp một nửa hàng trước khi báo overflow.

Đây là tính nguyên tử **trong một lời gọi trên một luồng thực thi**; nó **không** tự làm class thread-safe. Nếu nhiều thread đồng thời gọi update, cần synchronization/partition rồi merge hoặc cơ chế tương đương.

### 7.2. Miền khóa và hàm hash

Mã demo giới hạn khóa:

```text
0 <= key < 2,147,483,647.
```

Hàm hash affine sử dụng một trường nguyên tố và giảm về width. `a*key+b` được tính bằng long với các toán hạng <p, tổng lớn nhất vẫn dưới Long.MAX_VALUE nên không overflow trong phạm vi này.

Nếu khóa là chuỗi, UUID, 64-bit nguyên tùy ý hoặc đối tượng phức tạp, **không được** tự ép `(int)key` hay dùng `hashCode()` tùy tiện rồi giữ nguyên chứng minh phân phối của họ băm trong bài. Cần định nghĩa đúng cách ánh xạ miền khóa vào họ hash có bảo đảm phù hợp, hoặc nêu rõ chỉ là heuristic thực nghiệm. Giữ một Map từ toàn bộ khóa gốc sang mã số nén online có thể lại tốn O(số khóa phân biệt) bộ nhớ, làm mất lợi thế của CMS nếu Map ấy không nằm trong ngân sách đã tính.

## 8. Gộp sketch khi xử lý luồng phân tán

Suppose stream `S` chia thành hai phần `S_A`,`S_B`, đều chứa cập nhật không âm. Hai sketch **cùng width, depth và cùng mọi hàm băm ở từng hàng** sẽ có:

```text
CMS(S_A concatenated S_B)
   = CMS(S_A) + CMS(S_B)
```

trong đó phép cộng ở vế phải là **cộng từng counter tương ứng**, miễn không overflow.

### 8.1. Vì sao cộng từng bucket là đúng?

Mỗi sự kiện `(x,weight)` góp `weight` vào đúng bucket `h_r(x)` của mỗi hàng. Nếu hai sketch dùng **cùng `h_r`**, tổng đóng góp của các sự kiện trong A và B vào bucket `(r,c)` đúng bằng:

```text
counter_AB[r][c]
  = counter_A[r][c] + counter_B[r][c].
```

Cả tổng F1 cũng cộng:

```text
F1_AB = F1_A + F1_B.
```

Gộp là **tuyến tính ở mức bảng**. Tuy nhiên, vì truy vấn dùng **min giữa các hàng**, không được gộp kết quả điểm bằng:

```text
estimate_AB(x) = estimate_A(x) + estimate_B(x)
```

như một đẳng thức tổng quát. Đẳng thức đúng là **cộng bảng trước rồi lấy min**, không phải **lấy min mỗi bảng rồi cộng**.

### 8.2. Ví dụ phản chứng “cộng các estimate”

Giả sử hai hàng có lượng nhiễu của một khóa x:

```text
A: [10,0]
B: [0,10]
true frequency of x in both shards = 0.

estimate_A(x) = min(10,0)=0
estimate_B(x) = min(0,10)=0

estimate_A(x)+estimate_B(x)=0.

But merged row counters at x:
[10,0]+[0,10]=[10,10]

estimate_merged(x)=min(10,10)=10.
```

Vì vậy, khi phân tán, gửi **bảng CMS và hash configuration**, không chỉ gửi tập các estimate đã tính cục bộ. Cần lưu cả metadata về hash family/seed/số hàng/cột để kiểm tra compatibility.

### 8.3. Hai sketch cùng kích thước nhưng khác seed?

Không đủ. Nếu `h_r^A(x)` khác `h_r^B(x)` thì cùng cột chỉ là **số thứ tự bucket trùng**, không đại diện cho cùng tập khóa. Cộng hai bảng có hash khác nhau sẽ không còn tương đương sketch trên luồng hợp nhất.

Mã Java chỉ cho phép `mergeFrom(other)` khi:

```text
width == other.width
depth == other.depth
all a_r equal
all b_r equal.
```

Với cùng seed, class khởi tạo ra cùng hệ số trên phiên bản PRNG/hành vi được dùng. Trong hệ thống phân tán thật, nên truyền **tham số hash đã chọn** hoặc định danh cấu hình nhất quán chứ không suy đoán từ seed mà không kiểm soát phiên bản/chạy.

### 8.4. Gộp, nhân bản và đếm trùng

Một sự kiện được ghi vào cả hai shard thì phép cộng sẽ đếm **hai lần**, không phải chỉ một lần. CMS không khử trùng lặp ID sự kiện; muốn exactly-once phải xử lý phía ingest hoặc lưu thông tin de-dup thích hợp. Gộp cũng không khôi phục được những sự kiện đã mất.

## 9. Dùng CMS để lọc ứng viên heavy hitter

Gọi một khóa là **heavy hitter** nếu:

```text
f(x) >= phi*F1
```

với `phi` là ngưỡng tỷ lệ, ví dụ `phi=0.05`.

Từ bất biến không đánh giá thấp:

```text
estimate(x) >= f(x).
```

Do đó với một khóa có thể truy vấn:

```text
if estimate(x) < phi*F1:
    x definitely is NOT a heavy hitter.

if estimate(x) >= phi*F1:
    x is a CANDIDATE, not guaranteed heavy.
```

**Không có false negative** trong phép sàng lọc theo ngưỡng này nếu tính toán chính xác và không có cập nhật âm, nhưng có thể có **false positive** từ va chạm. Nếu một khóa thật có `f(x) <= (phi-epsilon)*F1`, thì với cận CMS xác suất nó bị đẩy lên ngưỡng `phi*F1` được chặn theo mô hình đã chứng minh (lưu ý xử lý nghiêm ngặt/không nghiêm ngặt ở biên).

### 9.1. CMS không tự liệt kê các khóa

Mảng `counters[d][w]` **không lưu tên khóa nào**; nó không thể quét bảng và biết ai là heavy hitter. Để liệt kê khóa phổ biến, cần một cơ chế **sinh tập ứng viên**: ví dụ Space-Saving, Misra–Gries, danh sách ứng viên từ luồng, hoặc một tầng xử lý khác. Sau đó CMS dùng để **ước lượng/kiểm tra ứng viên**.

Lưu mọi khóa từng gặp vào Map rồi truy vấn CMS có thể tốn gần bằng cách đếm chính xác; cần tính bộ nhớ toàn pipeline, không chỉ kích thước sketch.

### 9.2. Nhiều truy vấn và union bound

Bảo đảm `Pr[bad estimate of fixed x] <=delta` áp dụng cho **một x cố định**. Nếu cần đồng thời m khóa cố định, dùng union bound:

```text
Pr[ANY of m fixed queries is bad] <= m*delta.
```

Muốn xác suất có bất kỳ lỗi trong m truy vấn không quá `delta_global`, có thể xây sketch với:

```text
delta_per_query = delta_global / m
depth = ceil(ln(m/delta_global)).
```

Không cần các biến cố lỗi của các khóa độc lập để áp union bound. Nhưng nếu **chọn các khóa thích nghi sau khi quan sát hash/estimate**, mô hình cần chứng minh riêng; phép chọn thích nghi có thể khai thác các va chạm toàn bộ như thí nghiệm ở phần 6.

## 10. So sánh với các cấu trúc luồng khác

| Cấu trúc | Câu hỏi thường giải quyết | Loại câu trả lời |
| --- | --- | --- |
| `HashMap<Key,Long>` | Tần suất **chính xác** theo khóa | Exact, nhớ từng khóa |
| **Count-Min Sketch** | Ước lượng tần suất điểm với update không âm | Ước lượng **một phía từ trên** |
| **Count Sketch** | Ước lượng tần suất bằng hash có dấu | Thường sai số có dấu, dùng cận theo norm phù hợp |
| **Misra–Gries** | Tìm tập ứng viên khóa phổ biến | Một số bộ đếm ứng viên, không thay mọi point query |
| **Space-Saving** | Theo dõi ứng viên nặng | Danh sách candidate và ước lượng |
| **HyperLogLog** | Ước lượng số lượng **phần tử phân biệt** | Distinct count, không phải tần suất khóa cụ thể |
| **Bloom Filter** | Kiểm tra có thể là thành viên của tập hay không | Membership kiểu false positive, không phải weighted counts |

Các cấu trúc có thể được kết hợp, nhưng không thay thế chức năng của nhau bằng cách đổi tên. CMS không phải Bloom Filter hay bộ đếm distinct. Khi cần xóa, window trượt, top-k hoặc secure hashing, phải kiểm tra đúng biến thể và giới hạn.

### 10.1. “Conservative update” là biến thể khác

Một số triển khai CMS dùng **conservative update**: không tăng mọi counter như nhau mà chỉ tăng những bộ đếm cần thiết để hạn chế overcount. Điều này có thể cải thiện sai số thực nghiệm nhưng **không còn phép cộng từng bucket tương đương trực tiếp** với cấu trúc cập nhật tuyến tính trong ví dụ. Đừng vừa sửa thành conservative update vừa giữ nguyên chứng minh `mergeFrom` cộng bảng mà không phân tích lại.

## 11. Thiết kế Java 17+ của bài

Tệp **`CountMinSketchNonnegativeDemo.java`** cài đặt:

- `CountMinSketch(epsilon,delta,seed)` tạo bảng `long[depth][width]` với width bảo thủ `ceil(2e/epsilon)` và depth `ceil(ln1/delta)`.
- `update(key,weight)` yêu cầu `weight>=0`; kiểm tra mọi phép cộng bằng `Math.addExact` **trước khi ghi**.
- `estimate(key)` lấy min giữa d bộ đếm, trả tần suất ước lượng.
- `totalWeight()` trả tổng trọng số luồng đã nhận thành công.
- `mergeFrom(other)` chỉ gộp nếu cùng kích thước/hash; kiểm tra overflow trước khi commit.
- `sameAs(other)` đối chiếu nguyên bảng và hash configuration, dùng để kiểm tra phép gộp.
- `findFullCollision` tìm hai khóa có cùng bucket ở **mọi hàng** của một sketch nhỏ sau khi biết hash; mô tả một tình huống **thích nghi/đối kháng**, không được dùng làm “thất bại xác suất” của mô hình input cố định.
- `checkRandomStreams` so 300 luồng nhân tạo, mỗi luồng 100 event, với **oracle exact `Map`** và so toàn bộ bảng merge; tổng **30.000 cập nhật và 42.300 truy vấn thử**.
- `overflowAndValidationTests` kiểm tra update âm, khóa ngoài miền, update zero, gộp khác hash và overflow không làm hỏng bảng.

**Giới hạn:** Đây là demo **đơn luồng**. Nó không quản lý phân vùng thời gian, sliding window, cạnh tranh cập nhật, lưu vào đĩa, phân phối seed bí mật hoặc hash của mọi kiểu dữ liệu. `SplittableRandom` được dùng để tái lập kiểm thử, không phải random mật mã; cận xác suất lý thuyết dựa trên các hệ số băm lý tưởng độc lập và đồng đều.

### 11.1. Mã Java đầy đủ

```java
import java.util.*;

public class CountMinSketchNonnegativeDemo {
    static final long PRIME = 2_147_483_647L;

    record Event(int key, long weight) {}

    static final class CountMinSketch {
        final int width, depth;
        final long[] a, b;
        final long[][] counters;
        long total;

        CountMinSketch(double epsilon, double delta, long seed) {
            if (!Double.isFinite(epsilon) || epsilon <= 0
                    || epsilon > 1 || !Double.isFinite(delta)
                    || delta <= 0 || delta >= 1) {
                throw new IllegalArgumentException(
                        "Require 0<epsilon<=1 and 0<delta<1");
            }
            double columns = Math.ceil(2 * Math.E / epsilon);
            double rows = Math.ceil(-Math.log(delta));
            if (columns > PRIME || rows > 10000) {
                throw new IllegalArgumentException(
                        "Parameters exceed this illustrative implementation");
            }
            width = (int) columns;
            depth = Math.max(1, (int) rows);
            counters = new long[depth][width];
            a = new long[depth];
            b = new long[depth];
            SplittableRandom rng = new SplittableRandom(seed);
            for (int r = 0; r < depth; r++) {
                a[r] = rng.nextLong(PRIME); // includes zero
                b[r] = rng.nextLong(PRIME);
            }
        }

        static void checkKey(int key) {
            if (key < 0 || (long) key >= PRIME) {
                throw new IllegalArgumentException(
                        "Require key in [0, PRIME-1]");
            }
        }

        int bucket(int row, int key) {
            checkKey(key);
            long field = (a[row] * key + b[row]) % PRIME;
            return (int) (field % width);
        }

        // Atomic weighted insertion, including overflow validation.
        void update(int key, long weight) {
            checkKey(key);
            if (weight < 0) {
                throw new IllegalArgumentException(
                        "Updates must be nonnegative");
            }
            if (weight == 0) return;
            long nextTotal = Math.addExact(total, weight);
            int[] positions = new int[depth];
            long[] values = new long[depth];
            for (int r = 0; r < depth; r++) {
                positions[r] = bucket(r, key);
                values[r] = Math.addExact(
                        counters[r][positions[r]], weight);
            }
            for (int r = 0; r < depth; r++) {
                counters[r][positions[r]] = values[r];
            }
            total = nextTotal;
        }

        long estimate(int key) {
            checkKey(key);
            long minimum = Long.MAX_VALUE;
            for (int r = 0; r < depth; r++) {
                minimum = Math.min(minimum, counters[r][bucket(r, key)]);
            }
            return minimum;
        }

        long totalWeight() {
            return total;
        }

        // Only sketches with identical hash functions and shape
        // can be added cell by cell. Preflight overflow atomically.
        void mergeFrom(CountMinSketch other) {
            Objects.requireNonNull(other, "other");
            if (width != other.width || depth != other.depth
                    || !Arrays.equals(a, other.a)
                    || !Arrays.equals(b, other.b)) {
                throw new IllegalArgumentException(
                        "Sketches use different hashing");
            }
            long combinedTotal = Math.addExact(total, other.total);
            long[][] combined = new long[depth][width];
            for (int r = 0; r < depth; r++) {
                for (int c = 0; c < width; c++) {
                    combined[r][c] = Math.addExact(
                            counters[r][c], other.counters[r][c]);
                }
            }
            for (int r = 0; r < depth; r++) {
                System.arraycopy(combined[r], 0,
                        counters[r], 0, width);
            }
            total = combinedTotal;
        }

        boolean sameAs(CountMinSketch other) {
            if (width != other.width || depth != other.depth
                    || total != other.total
                    || !Arrays.equals(a, other.a)
                    || !Arrays.equals(b, other.b)) return false;
            for (int r = 0; r < depth; r++) {
                if (!Arrays.equals(counters[r], other.counters[r])) {
                    return false;
                }
            }
            return true;
        }
    }

    static int[] findFullCollision(CountMinSketch sketch) {
        Map<String, Integer> first = new HashMap<>();
        for (int key = 0; key < 10000; key++) {
            int[] signature = new int[sketch.depth];
            for (int row = 0; row < sketch.depth; row++) {
                signature[row] = sketch.bucket(row, key);
            }
            String label = Arrays.toString(signature);
            Integer prior = first.putIfAbsent(label, key);
            if (prior != null) return new int[] {prior, key};
        }
        throw new AssertionError("Pigeonhole collision not found");
    }

    static void expectInvalid(Runnable action) {
        boolean failed = false;
        try {
            action.run();
        } catch (IllegalArgumentException ex) {
            failed = true;
        }
        if (!failed) throw new AssertionError("Expected validation error");
    }

    static void checkRandomStreams() {
        SplittableRandom rng = new SplittableRandom(20261110L);
        for (int trial = 0; trial < 300; trial++) {
            long seed = 9000L + trial;
            CountMinSketch whole = new CountMinSketch(0.12, 0.01, seed);
            CountMinSketch left = new CountMinSketch(0.12, 0.01, seed);
            CountMinSketch right = new CountMinSketch(0.12, 0.01, seed);
            Map<Integer, Long> truth = new HashMap<>();
            long streamWeight = 0;
            for (int i = 0; i < 100; i++) {
                int key = rng.nextInt(100);
                long weight = rng.nextLong(8); // 0,...,7
                whole.update(key, weight);
                (i % 2 == 0 ? left : right).update(key, weight);
                truth.merge(key, weight, Math::addExact);
                streamWeight = Math.addExact(streamWeight, weight);
            }
            left.mergeFrom(right);
            if (!left.sameAs(whole)
                    || left.totalWeight() != streamWeight) {
                throw new AssertionError("Merge mismatch");
            }
            for (int key = 0; key <= 140; key++) {
                long exact = truth.getOrDefault(key, 0L);
                long estimate = left.estimate(key);
                if (estimate < exact
                        || estimate > streamWeight
                        || estimate != whole.estimate(key)) {
                    throw new AssertionError(
                            "Invalid bound at key=" + key);
                }
            }
        }
        System.out.println(
                "Random oracle QA: PASS (300 streams, 30000 updates, "
                + "42300 key checks)");
    }

    static void overflowAndValidationTests() {
        CountMinSketch s = new CountMinSketch(0.5, 0.1, 11L);
        expectInvalid(() -> s.update(5, -1));
        expectInvalid(() -> s.update(-1, 1));
        expectInvalid(() -> s.update(Integer.MAX_VALUE, 1));
        s.update(5, 0);
        if (s.totalWeight() != 0) {
            throw new AssertionError("Zero update changed total");
        }
        s.update(5, Long.MAX_VALUE);
        boolean overflowCaught = false;
        try {
            s.update(5, 1);
        } catch (ArithmeticException ex) {
            overflowCaught = true;
        }
        if (!overflowCaught || s.totalWeight() != Long.MAX_VALUE
                || s.estimate(5) != Long.MAX_VALUE) {
            throw new AssertionError("Overflow was not atomic");
        }
        CountMinSketch t = new CountMinSketch(0.5, 0.1, 12L);
        expectInvalid(() -> s.mergeFrom(t));
        CountMinSketch extra = new CountMinSketch(0.5, 0.1, 11L);
        extra.update(6, 1);
        overflowCaught = false;
        try {
            s.mergeFrom(extra);
        } catch (ArithmeticException ex) {
            overflowCaught = true;
        }
        if (!overflowCaught || s.totalWeight() != Long.MAX_VALUE) {
            throw new AssertionError("Merge overflow was not atomic");
        }
        System.out.println(
                "Validation QA: PASS (negative, key range, "
                + "zero weight, hash mismatch, overflow)");
    }

    public static void main(String[] args) {
        double epsilon = 0.12, delta = 0.01;
        long seed = 20261110L;
        CountMinSketch sketch = new CountMinSketch(
                epsilon, delta, seed);
        System.out.println("Parameters: epsilon=" + epsilon
                + ", delta=" + delta + ", width="
                + sketch.width + ", depth=" + sketch.depth);

        Event[] events = {
            new Event(7, 5), new Event(12, 3),
            new Event(7, 2), new Event(101, 6),
            new Event(0, 4), new Event(12, 1),
            new Event(99, 8), new Event(33, 2),
            new Event(101, 5), new Event(200, 7),
            new Event(7, 1)
        };
        Map<Integer, Long> exact = new TreeMap<>();
        CountMinSketch left = new CountMinSketch(
                epsilon, delta, seed);
        CountMinSketch right = new CountMinSketch(
                epsilon, delta, seed);
        for (int i = 0; i < events.length; i++) {
            Event e = events[i];
            sketch.update(e.key(), e.weight());
            (i % 2 == 0 ? left : right).update(e.key(), e.weight());
            exact.merge(e.key(), e.weight(), Math::addExact);
        }

        System.out.println("Total stream weight F1: "
                + sketch.totalWeight());
        System.out.println("Exact frequencies: " + exact);
        for (int key : new int[] {7, 12, 101, 99, 33, 500}) {
            System.out.println("key=" + key + " true="
                    + exact.getOrDefault(key, 0L)
                    + " estimate=" + sketch.estimate(key));
        }
        left.mergeFrom(right);
        System.out.println(
                "Shard merge equals single stream: "
                + left.sameAs(sketch));

        CountMinSketch tiny = new CountMinSketch(0.9, 0.1, 17L);
        int[] colliding = findFullCollision(tiny);
        tiny.update(colliding[0], 10);
        System.out.println(
                "Adaptive full-hash collision: keys="
                + Arrays.toString(colliding)
                + ", true(other)=0, estimate(other)="
                + tiny.estimate(colliding[1]));
        if (tiny.estimate(colliding[1]) != 10) {
            throw new AssertionError("Expected a visible collision");
        }

        checkRandomStreams();
        overflowAndValidationTests();
    }
}
```

### 11.2. Biên dịch và chạy

Dùng JDK 17 trở lên:

```bash
javac CountMinSketchNonnegativeDemo.java
java CountMinSketchNonnegativeDemo
```

**Stdout chính xác với những seed trong chương trình:**

```text
Parameters: epsilon=0.12, delta=0.01, width=46, depth=5
Total stream weight F1: 44
Exact frequencies: {0=4, 7=8, 12=4, 33=2, 99=8, 101=11, 200=7}
key=7 true=8 estimate=8
key=12 true=4 estimate=4
key=101 true=11 estimate=11
key=99 true=8 estimate=8
key=33 true=2 estimate=2
key=500 true=0 estimate=0
Shard merge equals single stream: true
Adaptive full-hash collision: keys=[3, 12], true(other)=0, estimate(other)=10
Random oracle QA: PASS (300 streams, 30000 updates, 42300 key checks)
Validation QA: PASS (negative, key range, zero weight, hash mismatch, overflow)
```

### 11.3. Giải thích từng nhóm kết quả

**Parameters:** Với epsilon 0.12 và delta 0.01, bản demo dùng 46 cột nhân 5 hàng. Đây là kích thước từ **cận bảo thủ** đã chứng minh, không phải tối ưu duy nhất cho mọi hash family.

**F1=44:** Tổng trọng số của 11 sự kiện; không phải số sự kiện hoặc số khóa phân biệt.

**Exact frequencies:** `TreeMap` giữ bộ đếm **chính xác** của tập dữ liệu nhỏ để so sánh với CMS. Số khóa phân biệt là 7, không phải 44.

**Các dòng key:** Ước lượng trong seed này bằng tần suất thật cho những khóa được in. Điều đó phù hợp bất biến không đánh giá thấp; **không được suy ra CMS luôn là exact Map**. Truy vấn khóa 500 chưa xuất hiện cho 0 trong lần thử này; khóa chưa xuất hiện có thể cho >0 trong lần thử khác.

**Shard merge:** Sketch của sự kiện chẵn và lẻ dùng cùng seed/hash đã được cộng bảng; toàn bộ counter và F1 khớp chính xác sketch được cập nhật nối tiếp bằng **tất cả 11 sự kiện**.

**Adaptive collision:** Tìm được hai khóa 3 và 12 băm vào cùng vị trí ở cả ba hàng của sketch nhỏ. Cập nhật khóa 3 với weight 10 làm `estimate(12)=10` dù `f(12)=0`. Đây là ví dụ về **false positive do va chạm và lựa chọn khóa sau khi biết hash**.

**Random oracle QA:** 300 luồng, mỗi luồng đúng 100 update nên tổng **30.000 update**; mỗi luồng query 141 khóa từ 0 đến 140, tổng **42.300 truy vấn thử**. Mỗi lần đối chiếu:

```text
true_frequency(key) <= estimate(key) <= F1
```

và bảng gộp hai shard đúng bằng bảng xử lý nối tiếp. Đây là **QA bất biến tất định và merge**, không phải phép đo rằng mọi truy vấn trong tất cả luồng đều đạt bảo đảm epsilon với xác suất 99%.

**Validation QA:** Những update âm/khóa ngoài miền bị từ chối, weight zero là no-op, không cho gộp sketch khác hash, và overflow bị phát hiện trước khi làm thay đổi trạng thái. Các test này không thay thế cơ chế khóa/synchronization nếu ứng dụng đa luồng.

## 12. Lưu ý về xác suất, lỗi và câu hỏi thích nghi

### 12.1. “Probability 1-delta” được hiểu thế nào?

Bảo đảm được viết:

```text
For a fixed stream and a fixed query key x
that do NOT depend on the random hash choices:

Pr_hash[
  estimate(x) <= f(x)+epsilon*F1
] >= 1-delta.
```

Nó không có nghĩa:

- Chính xác `1-delta` phần trăm khóa có estimate đúng.
- Cứ mỗi 100 query thì chắc chắn chỉ 1 query sai.
- Sketch được chọn một seed cố định là đã có xác suất mỗi truy vấn sai đúng delta.
- Một khóa được chọn **sau khi quan sát toàn bộ hash** vẫn được bảo đảm như một khóa cố định trước đó.
- Tất cả khóa trong vũ trụ `[0,p)` đồng thời đúng mà không cần điều chỉnh delta.

### 12.2. Chọn ngẫu nhiên chỉ từ miền nhỏ hơn

Nếu ứng dụng bảo đảm khóa lấy từ 0..999 và hash sinh lý tưởng độc lập với chúng, bảo đảm cho từng khóa vẫn dùng cùng chứng minh. Nhưng nếu muốn **tất cả 1000 khóa** đồng thời thỏa cận với xác suất 0.99, có thể dùng union bound và chọn:

```text
delta_per_key = 0.01/1000 = 0.00001

depth = ceil(ln(100000))
      = 12.
```

Nó khác với việc dùng `depth=5` rồi tuyên bố toàn bộ 1000 khóa đều có sai số cộng <=epsilon F1 với xác suất 99%.

### 12.3. Streaming adaptive/adversarial

Trong nhiều hệ thống, một đối thủ có thể hỏi nhiều khóa, xem ước lượng, suy đoán hash hoặc biết seed. Khi khóa được chọn dựa trên các giá trị này, cần mô hình hóa **truy vấn thích nghi**. Một cặp full-hash collision tồn tại chắc chắn trong miền khóa đủ lớn so với số chữ ký, dù sự kiện “cặp khóa cụ thể x,y va chạm” có xác suất thấp trước khi biết hash.

Có thể cần giữ hash secret, thay hash định kỳ, giới hạn truy vấn, hoặc dùng cơ chế có chứng minh chống adaptive adversary phù hợp. Các biện pháp ấy là vấn đề thiết kế hệ thống; không tự gọi seeded PRNG là an toàn vì đầu ra “trông ngẫu nhiên”.

## 13. Lỗi thường gặp

1. Dùng CMS như một bộ đếm exact rồi tin mọi estimate đúng tuyệt đối.
2. Dùng `max` thay vì `min` giữa các hàng.
3. Nhầm số hàng d với số cột w và vai trò độ chính xác của chúng.
4. Không xác định epsilon là **sai số cộng theo F1**.
5. Viết “sai số tương đối epsilon cho mọi khóa” thay vì sai số cộng `epsilon*F1`.
6. Đồng nhất tổng F1 với số sự kiện khi có weighted updates.
7. Nhầm số khóa phân biệt với tổng F1.
8. Cho rằng một khóa có estimate>0 chắc chắn đã xuất hiện.
9. Cho rằng estimate=0 cũng có thể bỏ sót tần suất dương trong mô hình nonnegative/no-overflow.
10. Dùng update âm vào chương trình chỉ hỗ trợ không âm.
11. Coi general turnstile vẫn luôn có nhiễu từ các khóa khác không âm.
12. Không phát hiện tràn số long ở counter và F1.
13. Ghi một số row rồi mới phát hiện overflow, làm trạng thái không nhất quán.
14. Dùng `int` cho tổng weighted count có thể vượt 2^31−1.
15. Cho rằng một lần đọc query có thể chạy O(1) nếu d tăng cùng delta; thực tế O(d).
16. Dùng `width=ceil(e/epsilon)` nhưng không kiểm tra giả thiết hàm băm của cận kinh điển.
17. Bỏ sai lệch do `%width` khi p không chia hết cho width mà lại khẳng định hoàn toàn uniform trên bucket.
18. Chọn các row hash giống hệt nhau rồi lấy lũy thừa xác suất `delta`.
19. Dùng cùng hệ số `(a,b)` cho mọi hàng nhưng tự gọi chúng độc lập.
20. Dùng seed cố định rồi tuyên bố đã chứng minh randomness độc lập lý tưởng.
21. Áp xác suất điểm cho một khóa được chọn sau khi biết hash.
22. Đọc “delta=1%” như “chắc chắn 99% tất cả query đều đúng”.
23. Quên union bound khi muốn bảo đảm đồng thời trên nhiều khóa cố định.
24. Chọn width vượt miền trường p nhưng vẫn dùng cận `2/width`.
25. Tính `a*key+b` trong int và để overflow trước phép modulo p.
26. Dùng `hashCode` tùy tiện cho String nhưng giữ nguyên định lý họ affine trên Fp.
27. Gộp hai sketch chỉ vì chúng có cùng width,depth, dù hash khác.
28. Gộp `estimate_A(x)+estimate_B(x)` rồi tưởng luôn bằng estimate trên luồng hợp nhất.
29. Cho phép shard ghi trùng sự kiện mà không phân tích double counting.
30. Không cộng đúng `totalWeight` khi merge.
31. Quên kiểm tra overflow của phép merge trước khi commit.
32. Tự động áp conservative update rồi vẫn dùng chứng minh gộp bảng tuyến tính.
33. Dùng CMS để tìm “tất cả heavy hitters” mà không có cơ chế lưu/gợi ý khóa ứng viên.
34. Coi một estimate lớn là chứng nhận khóa chắc chắn heavy hitter.
35. Dùng CMS để đếm distinct thay vì dùng cấu trúc phù hợp như HyperLogLog.
36. Coi CMS và Bloom filter có cùng ngữ nghĩa membership.
37. Không kiểm thử khóa chưa xuất hiện và khóa có tần suất bằng 0.
38. Chỉ test ngẫu nhiên thông thường mà không tạo va chạm có chủ đích.
39. Không kiểm tra gộp shard khớp sketch cập nhật tuần tự.
40. Không đối chiếu bất biến `f(x)<=estimate(x)<=F1` với Map trên dữ liệu nhỏ.
41. Không biết rằng một bộ đếm long mất chính xác nếu tràn, kể cả code không crash.
42. Giả định một đối tượng CMS Java hiện tại thread-safe chỉ vì hàm update ngắn.
43. Coi bộ nhớ tổng thể độc lập số khóa, nhưng lại lưu Map toàn khóa ở lớp candidate.
44. Nói bộ nhớ là số bit O(1/epsilon log1/delta) mà quên số bit mỗi counter.
45. Không nêu miền khóa, giới hạn trọng số và phương pháp hash khi triển khai thực tế.

## 14. Bài tập có đáp án

**Bài 1.** CMS giải câu hỏi nào?

**Đáp án:** Ước lượng tần suất của một khóa từ luồng, với bộ nhớ giới hạn và cho phép sai số va chạm.

**Bài 2.** Luồng `(5,3),(5,2),(8,7)` có `f(5)` bằng bao nhiêu?

**Đáp án:** `3+2=5`.

**Bài 3.** Trong cùng luồng, `F1` bằng bao nhiêu?

**Đáp án:** `3+2+7=12`.

**Bài 4.** Có mấy khóa phân biệt trong luồng trên?

**Đáp án:** 2 khóa: 5 và 8.

**Bài 5.** Count-Min Sketch có bao nhiêu bucket cho một sự kiện?

**Đáp án:** Một bucket ở **mỗi** hàng, tổng cộng d bucket được tăng.

**Bài 6.** Với giá trị bucket ở ba hàng `[10,7,13]`, estimate bằng bao nhiêu?

**Đáp án:** `min(10,7,13)=7`.

**Bài 7.** Nếu tần suất thật bằng 5, estimate=7 có thể xảy ra không?

**Đáp án:** Có, do va chạm, sai số từ trên bằng 2.

**Bài 8.** Trong luồng chỉ tăng không âm và không overflow, estimate có thể dưới f(x) không?

**Đáp án:** Không; mỗi bucket được cộng cả f(x) và các tần suất khác không âm.

**Bài 9.** Nếu `estimate(x)=0`, f(x) có thể bằng 3 không?

**Đáp án:** Không trong mô hình của bài, vì `estimate(x)>=f(x)>=0`.

**Bài 10.** Nếu `estimate(x)=3`, khóa x có chắc từng xuất hiện không?

**Đáp án:** Không, các khóa khác có thể gây va chạm ở mọi hàng.

**Bài 11.** Khác biệt giữa epsilon và delta là gì?

**Đáp án:** Epsilon là mức sai số **cộng theo F1**; delta là cận xác suất cận epsilon thất bại cho một truy vấn cố định dưới mô hình random hash.

**Bài 12.** Nếu F1=1000, epsilon=0.05, cận sai số cộng là gì?

**Đáp án:** `epsilon*F1=50`.

**Bài 13.** Cận 50 ở bài 12 có nghĩa sai số tương đối 5% cho khóa f=2 không?

**Đáp án:** Không; sai số cộng 50 rất lớn so với tần suất 2.

**Bài 14.** Trong phiên bản bài này, chọn width theo công thức nào?

**Đáp án:** `ceil(2e/epsilon)` để dùng cận va chạm bảo thủ `2/width`.

**Bài 15.** Chọn depth theo delta?

**Đáp án:** `ceil(ln(1/delta))`.

**Bài 16.** Với epsilon=0.12, delta=0.01, width,depth?

**Đáp án:** Width 46, depth 5.

**Bài 17.** Số bộ đếm long của bảng đó?

**Đáp án:** `46*5=230`.

**Bài 18.** Dung lượng **riêng các phần tử primitive** của 230 bộ đếm long?

**Đáp án:** `230*8=1840 bytes`, chưa tính overhead và hash arrays.

**Bài 19.** Cập nhật một khóa có thời gian theo d?

**Đáp án:** O(d) do tăng đúng một bucket mỗi hàng.

**Bài 20.** Truy vấn một khóa có thời gian theo d?

**Đáp án:** O(d) do đọc d bucket và lấy min.

**Bài 21.** Vì sao Markov áp dụng được với nhiễu hàng?

**Đáp án:** Nhiễu là tổng các tần suất không âm của những khóa khác băm trùng nên Z≥0.

**Bài 22.** Nếu mỗi hàng có xác suất nhiễu lớn ≤1/e, d hàng độc lập có cận nào?

**Đáp án:** `<=e^(-d)` cho biến cố tất cả hàng đều nhiễu lớn.

**Bài 23.** Với delta=0.01 và d=5, `e^-d` khoảng bao nhiêu?

**Đáp án:** Khoảng 0.00674, nhỏ hơn 0.01.

**Bài 24.** Có cần các va chạm với mọi khóa khác trong **cùng hàng** độc lập để cộng kỳ vọng không?

**Đáp án:** Không; tuyến tính kỳ vọng không đòi độc lập.

**Bài 25.** Vì sao các hàng phải độc lập để nhân cận xác suất?

**Đáp án:** Vì cần cận cho giao của các biến cố “mọi hàng đều nhiễu lớn”; nếu các hàng giống nhau, lỗi không tự giảm theo lũy thừa.

**Bài 26.** Hai shard cùng width/depth nhưng khác hash có gộp từng bucket được không?

**Đáp án:** Không; cùng cột không còn đại diện cùng tập khóa.

**Bài 27.** Hai shard cùng hash, cùng width/depth có gộp được không?

**Đáp án:** Có, cộng từng bucket và tổng F1 nếu các phép cộng không overflow; nhớ xử lý sự kiện trùng giữa shard.

**Bài 28.** `estimate(A)+estimate(B)` luôn bằng `estimate(merged)` không?

**Đáp án:** Không; phép min phi tuyến theo hàng. Phải cộng bảng trước rồi lấy min.

**Bài 29.** Với một khóa thật heavy `f(x)>=phi F1`, CMS sàng lọc theo `estimate(x)>=phi F1` có bỏ sót nó không?

**Đáp án:** Không, vì estimate≥f; nhưng có thể tạo false positives.

**Bài 30.** CMS có tự biết danh sách mọi khóa xuất hiện không?

**Đáp án:** Không; nó chỉ lưu các bộ đếm bucket, cần candidate generator nếu muốn liệt kê heavy hitters.

**Bài 31.** Với m=1000 khóa cố định và lỗi tổng mong muốn 0.01, chọn delta mỗi khóa?

**Đáp án:** `0.01/1000=0.00001`, dùng union bound.

**Bài 32.** Tại sao tạo khóa 12 sau khi thấy nó va chạm cùng mọi hàng với khóa 3 không bác bỏ định lý cận epsilon,delta?

**Đáp án:** Vì định lý yêu cầu khóa/luồng được cố định độc lập với hash, còn ở đây chọn truy vấn **thích nghi theo hash**.

**Bài 33.** Một update âm bị xử lý thế nào trong mã?

**Đáp án:** Ném `IllegalArgumentException`, không sửa bảng.

**Bài 34.** Khi cộng trọng số làm vượt Long.MAX_VALUE, mã làm gì?

**Đáp án:** `Math.addExact` ném `ArithmeticException` trước khi commit, giữ trạng thái cũ.

**Bài 35.** Nêu cách kiểm tra CMS bằng oracle exact.

**Đáp án:** Sinh luồng nhỏ, cập nhật Map chính xác và CMS; với nhiều khóa, xác nhận `f(x)<=estimate(x)<=F1`, đồng thời so bảng gộp shard với sketch cập nhật trực tiếp trên toàn luồng.

## 15. Checklist triển khai

- [ ] Phân biệt `f(x)`, `F1`, số sự kiện và số khóa phân biệt.
- [ ] Chỉ cho phép weighted updates không âm trong phiên bản này.
- [ ] Quy định miền khóa và hàm hash có giả thiết xác suất phù hợp.
- [ ] Chốt `epsilon` theo **sai số cộng epsilon F1**, không theo sai số tương đối.
- [ ] Chọn width/depth theo **cận collision của họ hash thực sự dùng**.
- [ ] Các hàng có hệ số hash độc lập trong mô hình lý thuyết.
- [ ] Hash coefficients/seed có được quản lý đúng và không vô tình lộ trước đối thủ thích nghi?
- [ ] Không có overflow của bộ đếm hoặc tổng F1.
- [ ] Cập nhật nhiều hàng có kiểm soát trạng thái khi lỗi xảy ra.
- [ ] Truy vấn lấy **min**, không lấy max hoặc cộng.
- [ ] Có test khóa chưa xuất hiện, weight=0, nhiều update một khóa?
- [ ] Có test chứng minh overestimate bằng Map exact?
- [ ] Có test va chạm có chủ đích và giải thích đúng phạm vi xác suất?
- [ ] Khi merge, tất cả hàm băm và kích thước phải khớp.
- [ ] Không gộp estimate thay cho cộng bảng rồi truy vấn.
- [ ] Có xử lý phát sinh sự kiện trùng khi phân vùng hoặc replay?
- [ ] Nếu cần liệt kê heavy hitters, có cơ chế lưu/gợi ý candidate?
- [ ] Nếu cần bảo đảm nhiều truy vấn, đã dùng union bound phù hợp?
- [ ] Nếu triển khai concurrent, đã bảo đảm synchronization hoặc phân vùng độc lập?
- [ ] Đã báo bộ nhớ theo **số bucket và số bit mỗi counter**, không chỉ theo tham số epsilon,delta?

## Kết luận

Count-Min Sketch là cấu trúc xấp xỉ tuyến tính thích hợp với **luồng cập nhật trọng số không âm**: mỗi update tăng **một bucket mỗi hàng**, mỗi truy vấn lấy **giá trị nhỏ nhất** trong các bucket tương ứng.

```text
update(x,weight>=0):
    for each row r:
        counter[r][h_r(x)] += weight

estimate(x):
    return min_r counter[r][h_r(x)].
```

Bất biến quan trọng nhất là:

```text
estimate(x) >= f(x)
```

cho mọi luồng chỉ tăng không âm, miễn các phép cộng không tràn. Bảo đảm xác suất bổ sung được xây dựng bằng **cận va chạm**, **Markov** và **các hàng độc lập**:

```text
Pr[estimate(x) > f(x)+epsilon*F1] <= delta
```

cho **khóa và luồng cố định, không phụ thuộc ngẫu nhiên hash**; kích thước bảng có bậc `O((1/epsilon)*log(1/delta))` bộ đếm.

Để dùng đúng, phải nhớ **CMS không phải đếm chính xác**, **không tự liệt kê heavy hitters**, **không chứng minh tất cả truy vấn đồng thời đúng nếu chỉ có cận cho một truy vấn cố định**, và **không được gộp các sketch khác hash**. Trong Java, thiết kế tránh overflow và kiểm tra bằng oracle Map cùng phép gộp phân vùng là cách thực hành tốt để giữ vững những bất biến trên.
