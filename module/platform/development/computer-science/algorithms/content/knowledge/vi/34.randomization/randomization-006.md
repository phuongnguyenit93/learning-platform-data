# Lấy mẫu theo trọng số bằng tổng tiền tố

**Lấy mẫu theo trọng số** (*weighted random sampling*) là chọn ngẫu nhiên một mục trong n mục sao cho **xác suất được chọn tỷ lệ thuận với trọng số** của mục đó. Nếu trọng số là `w₀,w₁,...,w_{n−1}`, mỗi `wᵢ≥0` và tổng `W=Σwᵢ>0`, mục i phải được chọn với xác suất:

**`P(X=i)=wᵢ/W`.**

Khác với lấy mẫu đều, trong đó mỗi mục có xác suất 1/n, một mục có trọng số 10 phải có xác suất được chọn gấp đôi một mục có trọng số 5, miễn là cả hai nằm trong cùng một tập hợp ứng viên. **Trọng số không cần cộng thành 1**: dãy `[3,0,2,5]` có tổng 10 và tương ứng xác suất `[0,3;0;0,2;0,5]`. Trọng số 0 có nghĩa mục ấy **không bao giờ được chọn** trong phép lấy mẫu này.

**Tổng tiền tố** (*prefix sums*) biến những trọng số thành các **khoảng liên tiếp trên trục vé ngẫu nhiên**. Ta xây một mảng tổng tích lũy, sinh một số nguyên ngẫu nhiên đồng đều trong `[0,W)`, rồi dùng **tìm kiếm nhị phân** để xác định khoảng chứa vé. Từ đó, một lần tiền xử lý `O(n)` cho phép mỗi lượt lấy mẫu chạy `O(log n)` mà không phải cộng lại tất cả trọng số.

Bài thuộc nhóm **Ngẫu nhiên hóa** của **Computer Science Algorithms**, với đề bài **Lấy mẫu theo trọng số bằng tổng tiền tố**. Nội dung đi từ định nghĩa phân phối rời rạc, ví dụ vé nguyên, chứng minh xác suất, cách chọn **upper bound** đúng khi có trọng số bằng 0, cách sinh vé không thiên lệch, giới hạn kiểu số nguyên và tràn tổng, tính chất lấy mẫu **có hoàn lại**, và sự khác biệt với các thuật toán khác như **alias method**, **Fenwick tree** và weighted sampling without replacement. Phần thực hành có **Java 17+ hoàn chỉnh**, một oracle quét tuyến tính độc lập và các kiểm thử biên.

**Mục tiêu sau bài:** tự xây mảng prefix, dùng vé nguyên uniform và binary search để trả đúng mục, giải thích vì sao xác suất chính xác bằng wᵢ/W, xử lý các ca 0/âm/tổng tràn và ticket biên, phân tích thời gian và bộ nhớ, và chọn cấu trúc phù hợp khi trọng số thay đổi.

## 1. Bài toán, ký hiệu và hợp đồng dữ liệu

Cho n mục mang tên hoặc ID:

**`A₀,A₁,...,A_{n−1}`**,

tương ứng n trọng số:

**`w₀,w₁,...,w_{n−1}`**.

Trong phiên bản này, trọng số là **số nguyên `long` không âm**:

- `n≥1`.
- `wᵢ≥0` với mọi i.
- **Tổng `W=Σwᵢ>0`**, nên có ít nhất một trọng số dương.
- `W≤Long.MAX_VALUE`, để tính và lưu tổng chính xác bằng long.
- Mỗi lần gọi phép chọn sẽ chọn **đúng một chỉ số i**.
- Khi dùng cùng phân phối cố định qua các lần gọi, các lượt là **lấy mẫu có hoàn lại** (*with replacement*): một mục có thể xuất hiện nhiều lần; việc chọn không làm giảm trọng số.

Ví dụ một trò chơi có các phần thưởng:

| Chỉ số | Mục | Trọng số |
|---:|---|---:|
| 0 | A | 3 |
| 1 | B | 0 |
| 2 | C | 2 |
| 3 | D | 5 |

Tổng:

**`W=3+0+2+5=10`**.

Xác suất mong muốn:

| Mục | Xác suất chính xác |
|---|---:|
| A | 3/10 = 30% |
| B | 0/10 = 0% |
| C | 2/10 = 20% |
| D | 5/10 = 50% |

Cần phân biệt **trọng số tương đối** với **xác suất**. Nếu nhân tất cả trọng số với cùng một hệ số dương c, phân phối lý tưởng **không đổi**:

**`(cwᵢ)/(cW)=wᵢ/W`**.

Tuy nhiên, với dữ liệu `long`, nhân trọng số có thể gây tràn hoặc mất độ phân giải nếu sau đó làm tròn, nên chỉ làm phép biến đổi này khi có chứng minh an toàn.

### Không được trộn trọng số âm với dương

Một trọng số âm không thể là chiều dài một khoảng vé, cũng không thể cho xác suất âm. Ví dụ `[5,−2,7]` có tổng 10 nhưng không định nghĩa một phân phối rời rạc hợp lệ theo công thức wᵢ/W. Bản mã **từ chối trọng số âm**, không tự thay bằng trị tuyệt đối và không tự bỏ qua.

### Nhiều mục có cùng nhãn

Nếu hai mục có cùng tên hiển thị nhưng **khác chỉ số**, thuật toán vẫn xem đó là hai phần tử phân biệt. Ví dụ `[(A,2),(A,3),(B,5)]` cho xác suất chọn **một trong hai chỉ số mang nhãn A** bằng `(2+3)/10=1/2`. Nếu muốn gộp theo nhãn, phải **gộp trọng số theo khóa** trước khi xây prefix. Bản Java luôn trả chỉ số hoặc nhãn tương ứng với chỉ số đã chọn; không ngầm gộp.

## 2. Từ trọng số sang các tổng tiền tố

Định nghĩa:

**`Sᵢ=Σ_{j=0}^{i}wⱼ`**, với `i=0,1,...,n−1`.

Đặt thêm **`S_{−1}=0`** làm giá trị biên về mặt toán học. Khi `wⱼ≥0`, mảng `S` **không giảm**:

**`0=S_{−1}≤S₀≤S₁≤...≤S_{n−1}=W`**.

Với `w=[3,0,2,5]`:

~~~text
Index:        0   1   2   3
Item:         A   B   C   D
Weight:       3   0   2   5
Prefix S[i]:  3   3   5  10
~~~

Mỗi mục i gắn với một **khoảng vé nguyên nửa mở**:

**`Iᵢ=[S_{i−1},Sᵢ)`**.

Số giá trị nguyên trong khoảng này đúng bằng:

**`|Iᵢ|=Sᵢ−S_{i−1}=wᵢ`**.

Như vậy:

- A: `[0,3)` → vé **0,1,2**.
- B: `[3,3)` → **khoảng rỗng**, không có vé nào.
- C: `[3,5)` → vé **3,4**.
- D: `[5,10)` → vé **5,6,7,8,9**.

Các khoảng kề nhau, không chồng lấn và hợp của chúng phủ đúng **`[0,W)`**. Một vé nguyên trong miền này xác định duy nhất **một mục có trọng số dương**, kể cả khi có những mục có trọng số 0.

### Vì sao dùng khoảng nửa mở?

Ký hiệu `[a,b)` bao gồm a nhưng **không bao gồm b**. Điều này cho phép các khoảng kề nhau như [0,3), [3,5), [5,10) **không chung vé ở ranh giới**. Vé 3 không thuộc A mà thuộc C. Nếu dùng cả hai đầu đóng, vé 3 có thể bị đếm hai lần; nếu dùng cả hai đầu mở, vé 3 có thể không thuộc ai.

Các bài toán prefix/inverse CDF thường sai ở **dấu so sánh** tại ranh giới, không phải ở cách tính tổng.

## 3. Sinh vé nguyên đồng đều trên [0,W)

Tạo một số nguyên ngẫu nhiên **r** sao cho:

**`0≤r<W`** và mỗi giá trị nguyên trong miền có xác suất **`1/W`**.

Với W=10, r có thể là 0,1,2,3,4,5,6,7,8,9; không được sinh r=10. Khi W=1, vé duy nhất là 0.

Một phương thức Java 17 đơn giản là:

~~~java
long ticket = random.nextLong(totalWeight);
~~~

với `random` là một đối tượng `java.util.random.RandomGenerator` (ví dụ `SplittableRandom`) và `totalWeight>0`. Lệnh `nextLong(bound)` tạo số từ **0 (bao gồm)** tới **bound (không bao gồm)**.

### Không dùng modulo ngây thơ

Một cách tưởng dễ làm:

~~~java
long ticket = random.nextLong() % totalWeight;
~~~

là **sai** cho mục đích này:

1. `nextLong()` có thể âm, và toán tử `%` trong Java có thể trả phần dư âm.
2. Lấy modulo của một miền không chia hết cho W có thể tạo **thiên lệch modulo** (*modulo bias*).
3. Dùng `Math.abs(random.nextLong())` không giải quyết hoàn toàn vì `Math.abs(Long.MIN_VALUE)` vẫn âm.

Nên dùng API **bounded random** như `RandomGenerator.nextLong(W)`, thay vì tự lắp modulo.

### Cẩn thận với double và tổng lớn

Cách thường thấy:

~~~java
long ticket = (long) (Math.random() * totalWeight);
~~~

không phải lựa chọn tốt khi cần **vé nguyên đều chính xác trên miền long rất lớn**. `Math.random()` là double hữu hạn độ phân giải, không tạo đủ tất cả các mức nguyên khi W vượt khoảng độ phân giải của 53 bit significand; phép nhân/ép kiểu có thể làm một số vé có xác suất khác hoặc không thể xuất hiện.

Nếu trọng số là các số nguyên lớn, hãy **giữ thuật toán trên số nguyên** và dùng `nextLong(W)`. Chỉ chuyển sang double để **hiển thị xấp xỉ xác suất**, không đưa double vào phép chọn nếu yêu cầu phân phối vé chính xác.

### RNG cho mô phỏng và cho bảo mật

`SplittableRandom` thích hợp cho **mô phỏng, kiểm thử tái hiện bằng seed**, không phải nguồn ngẫu nhiên mật mã. Nếu ứng dụng là bốc thăm có đối thủ chủ động, token bảo mật hoặc phân phối phần thưởng có yêu cầu chống dự đoán, cần chọn **nguồn RNG đáp ứng threat model**, xem xét `SecureRandom` và kiểm định hệ thống ngoài thuật toán chọn chỉ số.

Việc các khoảng vé đúng tỷ lệ **không tự khiến bộ sinh ngẫu nhiên trở thành nguồn bảo mật**.

## 4. Tìm mục theo vé bằng binary search

Sau khi có mảng S không giảm, với một ticket r∈[0,W), ta muốn tìm:

**`i=min{k | Sₖ>r}`**.

Đây là **upper bound đối với r**: chỉ số đầu tiên có phần tử **lớn hơn nghiêm ngặt** r.

Không phải “phần tử đầu tiên ≥r” nếu vé được sinh trong `[0,W)`.

### Vì sao phải dùng dấu > thay vì ≥?

Với ví dụ:

**`S=[3,3,5,10]`**, vé `r=3`.

- Nếu tìm `S[i]≥3`, ta sẽ chọn chỉ số 0, tức A — **sai** vì A chỉ có vé 0,1,2.
- Nếu tìm `S[i]>3`, ta bỏ qua hai giá trị 3 ở chỉ số 0 và 1, tìm thấy S[2]=5 — chọn C, **đúng**.

Vé r=0 cần chỉ số đầu tiên có S[i]>0; r=9 cần chỉ số đầu tiên có S[i]>9; do `S[n−1]=W>r`, luôn có kết quả hợp lệ.

### Pseudocode upper bound

~~~text
pickByTicket(prefix, total, r):
    require 0 <= r < total

    lo = 0
    hi = prefix.length

    while lo < hi:
        mid = lo + (hi - lo) / 2   // integer floor

        if prefix[mid] <= r:
            lo = mid + 1
        else:
            hi = mid

    return lo
~~~

Bất biến vòng lặp là:

- Các phần tử ở bên trái lo đã được biết **≤r**.
- Vị trí đầu tiên có tổng >r, nếu tồn tại, luôn nằm trong [lo,hi].
- `hi` ban đầu bằng n, một biên **exclusive** không đọc phần tử prefix[n].
- Mỗi vòng giảm kích thước khoảng tìm kiếm.

Kết thúc `lo==hi` là chỉ số đầu tiên có S[lo]>r. Vì tổng W>r, chỉ số trả luôn nằm trong [0,n−1].

### Có dùng lower bound được không?

**Có**, nếu đổi quy ước vé. Ví dụ sinh vé nguyên `r'∈[1,W]` rồi tìm chỉ số đầu tiên có `Sᵢ≥r'` — đây là **lower bound**. Tương đương đặt `r'=r+1` với `r∈[0,W)`, nhưng cần đảm bảo không làm tràn kiểu khi chuyển đổi hoặc dùng cách lấy vé thích hợp.

Bài này cố định **0-based ticket** và **upper_bound(prefix,r)**, để xử lý ngay cả khi prefix có các giá trị trùng do trọng số 0.

## 5. Chứng minh xác suất chọn đúng tỷ lệ

Ta chứng minh bằng **đếm số vé nguyên**.

Mỗi mục i tương ứng khoảng nửa mở:

**`Iᵢ=[S_{i−1},Sᵢ)`**.

Vì prefix không giảm, các khoảng Iᵢ không chồng lấn và phủ toàn bộ [0,W). Binary search đầu tiên có `Sᵢ>r` chọn chính xác mục có:

**`S_{i−1}≤r<Sᵢ`**.

Trong `[0,W)` có đúng W vé nguyên đồng xác suất `1/W`. Khoảng Iᵢ chứa chính xác:

**`Sᵢ−S_{i−1}=wᵢ`** vé.

Vậy:

**`P(X=i)=wᵢ·(1/W)=wᵢ/W`**.

Đây là một chứng minh **chính xác về phân phối** dưới giả thiết vé r thực sự đồng đều; không phải kết luận rút ra từ vài chục lần chạy thử.

### Trọng số 0 có xác suất đúng bằng 0

Nếu `wᵢ=0` thì `Sᵢ=S_{i−1}`, nên Iᵢ là `[a,a)` rỗng, không có ticket hợp lệ. Upper bound tự bỏ qua mục ấy. **Không cần xóa các mục trọng số 0 khỏi mảng** nếu vẫn muốn giữ ổn định chỉ số gốc.

### Tại sao xóa trọng số 0 rồi đánh lại ID có thể gây lỗi ứng dụng?

Thuật toán chỉ yêu cầu chỉ số trả tương ứng với mục ban đầu. Nếu xóa B trong [A,B,C,D], danh sách đổi thành [A,C,D], khi đó chỉ số 1 **không còn là B**. Nếu downstream dựa trên ID/index gốc, cần giữ mảng dài n hoặc lưu **ánh xạ từ chỉ số mới về chỉ số cũ**.

### Điều kiện để tính đúng xác suất

Chứng minh cần đủ:

1. Tất cả trọng số là số nguyên không âm.
2. Tổng W dương và tính chính xác, không overflow.
3. Vé r **đồng đều** trên toàn bộ các số nguyên trong [0,W).
4. Prefix đúng bằng tích lũy của trọng số.
5. Tìm **first prefix > r**, không dùng comparator sai.

Nếu thiếu một điều kiện, kết quả thực nghiệm có thể gần đúng trong các test nhỏ nhưng không có phân phối được đảm bảo.

## 6. Ví dụ đầy đủ: 10 vé và 4 mục

Với:

**`items=[A,B,C,D]`**,  
**`weights=[3,0,2,5]`**,  
**`prefix=[3,3,5,10]`**.

Thử **toàn bộ** 10 vé khả dĩ:

| ticket r | Chỉ số chọn | Mục |
|---:|---:|---|
| 0 | 0 | A |
| 1 | 0 | A |
| 2 | 0 | A |
| 3 | 2 | C |
| 4 | 2 | C |
| 5 | 3 | D |
| 6 | 3 | D |
| 7 | 3 | D |
| 8 | 3 | D |
| 9 | 3 | D |

Tần suất **trên toàn bộ không gian vé** là **3 A / 0 B / 2 C / 5 D**. Đây là phép liệt kê tất cả khả năng, **không phải kết quả một đợt random có thể dao động**.

### Truy vết binary search với ticket=3

Ban đầu:

~~~text
prefix = [3,3,5,10]
ticket = 3

lo=0, hi=4
mid=2: prefix[2]=5 >3    => hi=2
lo=0, hi=2
mid=1: prefix[1]=3 <=3   => lo=2

lo=hi=2 -> C
~~~

Chú ý ticket=3 **không** chọn A hoặc B. Nếu dùng dấu `>=` sai, ví dụ này phát hiện lỗi ngay.

### Truy vết với ticket=9

~~~text
lo=0, hi=4
mid=2: prefix[2]=5 <=9  -> lo=3
mid=3: prefix[3]=10 >9  -> hi=3
lo=hi=3 -> D
~~~

Vé 9 thuộc [5,10), tức mục D; còn vé 10 **không hợp lệ** vì miền [0,10) không chứa 10.

## 7. Cách xây prefix an toàn

Duyệt trọng số từ trái sang phải, giữ `running`:

~~~text
running = 0
for i = 0..n-1:
    require weights[i] >= 0
    running = running + weights[i]
    prefix[i] = running

require running > 0
total = running
~~~

Với n phần tử:

- **Thời gian** O(n).
- **Bộ nhớ** O(n) cho mảng prefix.
- Có thể giữ thêm bản sao weights hoặc labels tùy API.

### Java: tránh tổng long bị tràn

Không chỉ viết:

~~~java
running += weights[i];
~~~

nếu tổng có thể lớn; long khi overflow sẽ wrap theo hai phần bù, khiến tổng âm hoặc nhỏ đi, phá bất biến prefix không giảm và xác suất.

Dùng:

~~~java
running = Math.addExact(running, weights[i]);
~~~

Nếu tổng không biểu diễn được trong long, `Math.addExact` ném `ArithmeticException` rõ ràng. Bản mã **không** tự clamp tổng về Long.MAX_VALUE, vì clamp sẽ thay đổi chiều dài khoảng vé, do đó thay đổi phân phối.

### Nếu tổng vượt Long.MAX_VALUE thì sao?

Có một số phương án tùy bài:

- Nếu trọng số là bội chung lớn, có thể **chia chính xác tất cả trọng số cho ước chung lớn nhất** (GCD) để giữ nguyên xác suất và giảm tổng; phải làm trên số nguyên không mất phần dư. Tuy nhiên GCD=1 hoặc tổng sau chia vẫn lớn thì không giải quyết được.
- Dùng `BigInteger` cho tổng/prefix và sinh **ticket BigInteger uniform bounded bằng rejection sampling**. Không chuyển ticket sang long khi không thể chứa.
- Nếu bài chấp nhận xác suất gần đúng và trọng số thực, chọn biểu diễn số thực có kiểm soát sai số; không quảng cáo là lấy vé nguyên chính xác.
- Nếu n quá lớn hoặc dữ liệu thay đổi liên tục, xem lại yêu cầu lưu trữ/cập nhật.

**Không** chuẩn hóa trọng số bằng cách nhân double rồi làm tròn mỗi phần tử một cách ngẫu nhiên nếu yêu cầu đúng chính xác tỷ lệ nguyên ban đầu.

### Trường hợp tổng bằng Long.MAX_VALUE

`W=Long.MAX_VALUE` vẫn **hợp lệ** nếu phép cộng không tràn, vì `nextLong(W)` chấp nhận bound dương. Ticket lớn nhất là `W−1`. Chương trình có test biên này để không vô tình dùng biến `W+1` gây overflow.

## 8. Java 17+: API lấy mẫu theo trọng số có kiểm thử

Phần thực hành dùng Java 17. Class `PrefixPicker` lưu:

- `String[] names` — bản sao nhãn;
- `long[] weights` — bản sao trọng số ban đầu;
- `long[] prefix` — tổng tiền tố không giảm;
- `long total` — tổng W>0.

Constructor từ chối đầu vào null, kích thước không khớp, mảng rỗng, nhãn null, trọng số âm, tổng bằng 0 và tổng overflow. API:

- `pickByTicket(long ticket)`: biến một vé hợp lệ đã biết thành **chỉ số**, tiện kiểm thử tất cả các ranh giới.
- `drawIndex(RandomGenerator rng)`: sinh vé bằng `rng.nextLong(total)` rồi binary search.
- `drawName(RandomGenerator rng)`: trả nhãn của chỉ số được chọn.
- `probability(int index)`: trả **double xấp xỉ chỉ để quan sát**, không dùng để chọn mẫu.
- `prefixSnapshot()`: bản sao mảng prefix, không để caller sửa state bên trong.

**Tính chất quan trọng:** object `PrefixPicker` sau khi tạo là **bất biến** về trọng số và prefix (defensive copies); RNG được truyền vào mỗi lần chọn, không lưu bên trong sampler. Nhờ vậy các phép đọc picker không tự thay đổi trọng số. Nhưng **một RNG cụ thể có thể không an toàn khi chia sẻ giữa nhiều thread**; không suy từ immutable picker rằng mọi cách sử dụng RNG đều tự thread-safe.

Lưu mã vào **`WeightedPrefixSamplingDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.SplittableRandom;
import java.util.random.RandomGenerator;

public final class WeightedPrefixSamplingDemo {
    private static final class PrefixPicker {
        private final String[] names;
        private final long[] weights;
        private final long[] prefix;
        private final long total;

        PrefixPicker(String[] names, long[] weights) {
            if (names == null || weights == null
                    || names.length == 0
                    || names.length != weights.length) {
                throw new IllegalArgumentException(
                        "Invalid input arrays");
            }

            this.names = names.clone();
            this.weights = weights.clone();
            this.prefix = new long[weights.length];

            long running = 0L;
            for (int i = 0; i < weights.length; i++) {
                if (this.names[i] == null) {
                    throw new IllegalArgumentException(
                            "Name must not be null");
                }
                long weight = this.weights[i];
                if (weight < 0L) {
                    throw new IllegalArgumentException(
                            "Weights must be nonnegative");
                }
                running = Math.addExact(running, weight);
                prefix[i] = running;
            }

            if (running == 0L) {
                throw new IllegalArgumentException(
                        "At least one positive weight required");
            }
            this.total = running;
        }

        long totalWeight() {
            return total;
        }

        long[] prefixSnapshot() {
            return prefix.clone();
        }

        long[] weightsSnapshot() {
            return weights.clone();
        }

        String nameAt(int index) {
            if (index < 0 || index >= names.length) {
                throw new IllegalArgumentException(
                        "Invalid item index");
            }
            return names[index];
        }

        double probability(int index) {
            if (index < 0 || index >= weights.length) {
                throw new IllegalArgumentException(
                        "Invalid item index");
            }
            return (double) weights[index] / (double) total;
        }

        // Upper bound: first prefix[i] STRICTLY > ticket.
        int pickByTicket(long ticket) {
            if (ticket < 0L || ticket >= total) {
                throw new IllegalArgumentException(
                        "Ticket must be in [0, total)");
            }

            int lo = 0;
            int hi = prefix.length;
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (prefix[mid] <= ticket) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            return lo;
        }

        int drawIndex(RandomGenerator rng) {
            Objects.requireNonNull(rng, "rng");
            long ticket = rng.nextLong(total);
            return pickByTicket(ticket);
        }

        String drawName(RandomGenerator rng) {
            return nameAt(drawIndex(rng));
        }
    }

    // Independent oracle: consume weight intervals
    // left-to-right, without prefix sums or binary search.
    private static int linearOracle(
            long[] weights, long ticket) {
        for (int i = 0; i < weights.length; i++) {
            if (ticket < weights[i]) {
                return i;
            }
            ticket -= weights[i];
        }
        throw new AssertionError("Invalid oracle ticket");
    }

    private static void requireReject(
            String label, Runnable action) {
        boolean rejected = false;
        try {
            action.run();
        } catch (IllegalArgumentException
                | ArithmeticException expected) {
            rejected = true;
        }
        if (!rejected) {
            throw new AssertionError(
                    "Expected rejection: " + label);
        }
        System.out.println(label + ": rejected");
    }

    private static void randomizedChecks() {
        SplittableRandom rng =
                new SplittableRandom(4512026L);

        for (int trial = 0; trial < 3000; trial++) {
            int n = 1 + rng.nextInt(24);
            String[] labels = new String[n];
            long[] weights = new long[n];

            long positiveSum = 0;
            for (int i = 0; i < n; i++) {
                labels[i] = "item-" + i;
                weights[i] = rng.nextInt(12);
                positiveSum += weights[i];
            }

            if (positiveSum == 0L) {
                weights[rng.nextInt(n)] = 1L;
            }

            PrefixPicker picker = new PrefixPicker(
                    labels, weights);

            // Exhaust both ends of every positive interval.
            long previous = 0L;
            long[] cumulative = picker.prefixSnapshot();
            for (int i = 0; i < n; i++) {
                if (weights[i] > 0L) {
                    if (picker.pickByTicket(previous) != i
                            || picker.pickByTicket(
                                    cumulative[i] - 1L) != i) {
                        throw new AssertionError(
                                "Interval boundary mismatch");
                    }
                }
                previous = cumulative[i];
            }

            // Independent O(n) weighted-selection oracle.
            for (int k = 0; k < 15; k++) {
                long ticket = rng.nextLong(
                        picker.totalWeight());
                int fast = picker.pickByTicket(ticket);
                int slow = linearOracle(weights, ticket);
                if (fast != slow) {
                    throw new AssertionError(
                            "Random ticket mismatch");
                }

                int randomIndex = picker.drawIndex(rng);
                if (weights[randomIndex] <= 0L) {
                    throw new AssertionError(
                            "Zero-weight item selected");
                }
            }
        }

        System.out.println(
                "Random cross-checks: 3000 PASS");
    }

    public static void main(String[] args) {
        String[] names = {"A", "B", "C", "D"};
        long[] weights = {3, 0, 2, 5};
        PrefixPicker picker = new PrefixPicker(
                names, weights);

        System.out.println(
                "Items: " + Arrays.toString(names));
        System.out.println(
                "Weights: " + Arrays.toString(
                        picker.weightsSnapshot()));
        System.out.println(
                "Prefix: " + Arrays.toString(
                        picker.prefixSnapshot()));
        System.out.println(
                "Total: " + picker.totalWeight());

        // All 10 equally likely tickets, not random draws.
        for (long ticket = 0;
                ticket < picker.totalWeight(); ticket++) {
            int index = picker.pickByTicket(ticket);
            System.out.println(
                    "ticket=" + ticket
                    + " -> " + picker.nameAt(index)
                    + " (index=" + index + ")");
        }

        System.out.printf(
                Locale.ROOT,
                "Probabilities: A=%.3f B=%.3f C=%.3f D=%.3f%n",
                picker.probability(0),
                picker.probability(1),
                picker.probability(2),
                picker.probability(3));

        requireReject("Negative weight",
                () -> new PrefixPicker(
                        new String[] {"A", "B"},
                        new long[] {2, -1}));
        requireReject("All-zero weights",
                () -> new PrefixPicker(
                        new String[] {"A", "B"},
                        new long[] {0, 0}));
        requireReject("Overflow total",
                () -> new PrefixPicker(
                        new String[] {"A", "B"},
                        new long[] {Long.MAX_VALUE, 1}));
        requireReject("Invalid ticket",
                () -> picker.pickByTicket(10L));

        PrefixPicker huge = new PrefixPicker(
                new String[] {"Big", "Zero", "Last"},
                new long[] {
                    Long.MAX_VALUE - 2L, 0L, 2L
                });
        if (huge.totalWeight() != Long.MAX_VALUE
                || huge.pickByTicket(
                        Long.MAX_VALUE - 3L) != 0
                || huge.pickByTicket(
                        Long.MAX_VALUE - 2L) != 2
                || huge.pickByTicket(
                        Long.MAX_VALUE - 1L) != 2) {
            throw new AssertionError("Large-bound error");
        }
        System.out.println(
                "Long.MAX_VALUE boundary: PASS");

        randomizedChecks();
    }
}
~~~

Biên dịch/chạy với **JDK 17+**:

~~~bash
javac -encoding UTF-8 WeightedPrefixSamplingDemo.java
java WeightedPrefixSamplingDemo
~~~

**Stdout chính xác:**

~~~text
Items: [A, B, C, D]
Weights: [3, 0, 2, 5]
Prefix: [3, 3, 5, 10]
Total: 10
ticket=0 -> A (index=0)
ticket=1 -> A (index=0)
ticket=2 -> A (index=0)
ticket=3 -> C (index=2)
ticket=4 -> C (index=2)
ticket=5 -> D (index=3)
ticket=6 -> D (index=3)
ticket=7 -> D (index=3)
ticket=8 -> D (index=3)
ticket=9 -> D (index=3)
Probabilities: A=0.300 B=0.000 C=0.200 D=0.500
Negative weight: rejected
All-zero weights: rejected
Overflow total: rejected
Invalid ticket: rejected
Long.MAX_VALUE boundary: PASS
Random cross-checks: 3000 PASS
~~~

### Ý nghĩa của các dòng quan trọng

**Prefix [3,3,5,10]** cho thấy hai giá trị 3 liên tiếp do trọng số B=0. Đây là tình huống cần dùng **upper_bound** thay vì tìm prefix≥r.

**ticket=3 → C** là phép thử ranh giới có sức phát hiện lỗi cao nhất trong ví dụ. Nếu trả A hoặc B thì điều kiện binary search sai.

**10 dòng ticket** không phải 10 lần rút vé ngẫu nhiên mà là **liệt kê hết không gian vé**. Vì thế chúng xác minh logic chọn mục chính xác, không chịu dao động thống kê.

**Probabilities** được tính dạng `double` để in 3 chữ số thập phân; thuật toán chọn mẫu vẫn dùng `long` nguyên chính xác. Khi W rất lớn, double có thể làm tròn tỷ số, nhưng không ảnh hưởng đến cách chọn ticket.

**Negative weight** từ chối vì không định nghĩa xác suất âm; **All-zero weights** từ chối vì W=0 không thể gọi nextLong(0); **Overflow total** từ chối vì tổng không thể biểu diễn chính xác bằng long; **Invalid ticket** từ chối r=10 khi W=10.

**Long.MAX_VALUE boundary** xác minh một tổng vừa đúng bằng long tối đa vẫn sử dụng được, ticket sát W−1 trả đúng mục cuối và mục 0-weight không bao giờ xuất hiện.

**Random cross-checks** tạo 3000 dãy trọng số với seed cố định, thử **đầu và cuối mọi khoảng dương**, rồi đối chiếu 15 vé được sinh cho mỗi dãy với oracle **quét và trừ trọng số**, hoàn toàn không dùng mảng prefix trong logic oracle. Dòng PASS chỉ in nếu mọi kiểm tra đều thành công.

### Vì sao dùng một oracle quét tuyến tính?

Nếu bộ kiểm thử gọi lại `pickByTicket` để tính “expected result”, một bug do dấu `<=`/`<` có thể xuất hiện ở cả code thật lẫn code kiểm thử. `linearOracle` làm việc **khác về cách tính**: lấy ticket, duyệt trọng số, trả mục đầu tiên có ticket còn lại nhỏ hơn trọng số của nó; nếu không, trừ đi trọng số rồi tiếp tục.

Vì thế oracle có cùng định nghĩa phân phối nhưng **không chia sẻ binary search hoặc prefix** với cài đặt đang kiểm thử.

## 9. Phân tích độ phức tạp

Gọi n là số mục, Q là số lượt lấy mẫu **có hoàn lại** từ cùng một phân phối tĩnh.

| Giai đoạn | Thời gian | Bộ nhớ phụ |
|---|---:|---:|
| Sao chép input và kiểm tra trọng số | O(n) | O(n), nếu copy |
| Xây prefix | **O(n)** | **O(n)** |
| Sinh một ticket bounded long | O(1) trong mô hình API thông dụng | O(1) |
| Upper-bound binary search | **O(log n)** | O(1) |
| Một lần draw | **O(log n)** | O(1) |
| Q lần draw sau tiền xử lý | **O(Q log n)** | O(1) thêm |
| Toàn quy trình | **O(n + Q log n)** | **O(n)** |

**Không được nói toàn bộ một lần khởi tạo rồi draw là O(log n)**: nếu bao gồm constructor, tiền xử lý prefix vẫn O(n). Tương tự, binary search chỉ O(log n) vì prefix đã được tạo và **không giảm**.

### Nếu Q rất nhỏ

Với **chỉ một lần chọn**, ta có thể làm scan tuyến tính O(n) mà **không cần lưu prefix**: tính W, sinh ticket, quét trừ từng trọng số đến khi tìm mục. Tổng thời gian O(n), có thể ít overhead hơn việc dựng mảng prefix cộng binary search riêng.

Prefix phát huy lợi ích khi có **nhiều lượt chọn trên cùng trọng số**, vì chi phí O(n) được phân bổ cho nhiều truy vấn.

### Nếu Q cực lớn và n tĩnh

Khi Q rất lớn, chi phí O(log n) mỗi draw có thể đáng kể. **Alias method** có thể xây cấu trúc trong O(n) và chọn mỗi lượt trong O(1) kỳ vọng/thường dùng (với cách sinh random phù hợp). Nó phức tạp hơn và thường dùng xác suất đã chuẩn hóa. Không chọn alias chỉ vì Big-O mà không xét lỗi số học, bộ nhớ, và nhu cầu giữ tỷ lệ nguyên chính xác.

### Có cần sắp xếp trọng số không?

**Không.** Mảng prefix không giảm vì các trọng số không âm theo thứ tự đầu vào, không phải vì `weights` đã sort. Sort các mục theo trọng số sẽ làm **đổi thứ tự index và tên**, không cần thiết và có thể phá ràng buộc ánh xạ của ứng dụng.

## 10. Thống kê: ngẫu nhiên không đồng nghĩa mỗi loạt rút đúng tỷ lệ

Nếu rút Q lần độc lập với xác suất P(X=i)=pᵢ, số lần chọn mục i là một biến ngẫu nhiên có:

**`E[countᵢ]=Qpᵢ`**.

Với Q=100 lần, p_A=0,3, ta **kỳ vọng** khoảng 30 lần chọn A, nhưng kết quả thực có thể là 24, 34 hoặc một con số khác. Không được bắt mỗi lần chạy ngẫu nhiên phải có **đúng** 30 A, 0 B, 20 C, 50 D.

Nếu các lượt độc lập và phân phối không đổi, phương sai của countᵢ:

**`Var(countᵢ)=Qpᵢ(1−pᵢ)`**.

Độ lệch chuẩn là căn bậc hai của phương sai. Với Q lớn, **tỷ lệ quan sát** thường tiến gần pᵢ theo quy luật số lớn, nhưng một bộ kiểm thử ngắn vẫn có thể chệch đáng kể mà code đúng.

### Kiểm thử nào đáng tin nhất?

1. **Kiểm định quyết định (deterministic):** Với W nhỏ, duyệt **mọi ticket** trong [0,W), đếm số ticket chọn từng mục. Kết quả phải **đúng wᵢ**, không có dao động thống kê. Đây là kiểm thử mạnh cho thuật toán ánh xạ ticket → chỉ số.
2. **Biên của mỗi khoảng:** Với wᵢ>0, ticket S_{i−1} và Sᵢ−1 đều phải trả i.
3. **Trọng số 0:** Không có ticket nào trả mục i có wᵢ=0.
4. **Oracle độc lập:** So binary search với quét/trừ tuyến tính cho nhiều vector/ticket ngẫu nhiên.
5. **Statistical sanity test:** Rút nhiều lần bằng RNG và kiểm tần suất gần pᵢ theo khoảng dao động hợp lý, nhưng không đặt ngưỡng cứng quá chặt khiến test xác suất thi thoảng FAIL dù thuật toán đúng.

Để chứng minh đúng tỷ lệ, **đếm độ dài khoảng vé** ở mục 5 là cốt lõi; thống kê chỉ hỗ trợ phát hiện bug RNG hoặc cách kết nối.

### Vì sao seed cố định hữu ích?

Seed cố định làm một loạt random **tái hiện được**, thuận tiện khi test fail ở vòng thứ 1234. Nó không bảo đảm phân phối tốt về mặt bảo mật hay sức mạnh thống kê. Khi đánh giá hệ thống thật, nên thử nhiều seed và có bộ test thống kê phù hợp.

## 11. Trọng số tĩnh, cập nhật và dữ liệu biến động

Mảng prefix tĩnh chỉ đúng khi các trọng số **không thay đổi**. Nếu thay `w_k` thành giá trị khác với độ chênh `Δ`, tất cả prefix tại chỉ số **i≥k** đều đổi thêm Δ.

### Sửa prefix trực tiếp

Với một cập nhật duy nhất, có thể duyệt i từ k tới n−1 và cộng Δ:

- Cập nhật: **O(n)** trong cận xấu.
- Lấy mẫu: O(log n).
- Nếu sửa nhiều lần, đây có thể là điểm nghẽn.

Cập nhật phải bảo đảm tất cả trọng số còn không âm và tổng W>0; nếu giảm trọng số tạo ra số âm hoặc tổng 0, phân phối không còn hợp lệ.

### Fenwick tree (Binary Indexed Tree)

Nếu có nhiều thao tác **đổi trọng số** xen kẽ nhiều lần draw, có thể dùng **Fenwick tree** lưu tổng từng đoạn:

- Xây từ n trọng số: có cách **O(n)**; cách gọi add n lần có thể O(n log n).
- Cập nhật một trọng số: **O(log n)**.
- Tính tổng W: O(log n) hoặc giữ một biến tổng cập nhật.
- Tìm phần tử theo **cumulative frequency**: **O(log n)** bằng binary lifting trên Fenwick, với cùng quy tắc ticket r∈[0,W).
- Bộ nhớ: O(n).

Kỹ thuật này là một dạng **order-statistics / kth-by-weight**. Cần kiểm phép cộng/trừ để không overflow, kiểm trọng số mới không âm, và giữ total chính xác. Nếu chỉ thay một trọng số thỉnh thoảng, rebuild prefix O(n) có thể đơn giản hơn.

### Segment tree

Segment tree lưu tổng trọng số trong mỗi nút. Mỗi lần chọn, từ gốc lấy ticket r, so với tổng cây con trái:

- Nếu r < sumLeft, đi trái.
- Ngược lại, trừ r-=sumLeft và đi phải.

Mỗi draw O(log n), cập nhật O(log n), bộ nhớ O(n). Cách này phù hợp khi đã có segment tree cho các phép tổng đoạn khác.

### Không được dùng prefix cũ sau khi sửa weights

Một bug đặc biệt nguy hiểm: ứng dụng giữ `weights` mutable, tính prefix một lần rồi ai đó thay weights mà không tái dựng. Lúc này xác suất thực được chọn theo **prefix cũ**, không còn bằng weights hiện tại. Bản Java copy weights khi khởi tạo và **không cung cấp setter**, để ngăn lỗi này.

## 12. Lấy mẫu có hoàn lại và không hoàn lại

### Có hoàn lại (with replacement)

Mỗi lượt chọn dùng **cùng một phân phối** `wᵢ/W`. Sau khi lấy A, trọng số A vẫn giữ nguyên. Vì vậy A có thể xuất hiện liên tiếp nhiều lần:

~~~text
A, D, D, A, C, D, ...
~~~

Đây là hành vi bình thường. Nếu dùng RNG cung cấp các vé độc lập đều trên [0,W), các lựa chọn cũng độc lập theo phân phối đã định.

### Không hoàn lại (without replacement)

Sau khi chọn một mục, mục ấy **không được xuất hiện lần nữa**. Một chính sách thường dùng là:

1. Chọn i với xác suất wᵢ/W trong tập ứng viên hiện tại.
2. Xóa i khỏi tập hoặc đặt trọng số i=0.
3. Tính tổng mới W←W−wᵢ.
4. Lặp cho lần sau.

Khi đó **phân phối thay đổi sau mỗi lượt**. Không thể tiếp tục dùng prefix tĩnh ban đầu nếu đã xóa mục được chọn; làm vậy vẫn có thể chọn lại i, trái yêu cầu không hoàn lại.

Nếu có k lần chọn không hoàn lại:
- Rebuild prefix sau mỗi lượt có thể O(kn) thời gian.
- Fenwick tree hỗ trợ cập nhật trọng số i thành 0 trong O(log n) và chọn tiếp O(log n).
- Nếu chỉ có vài mục, cách đơn giản có thể dễ kiểm chứng hơn.

**Cảnh báo:** k không thể lớn hơn số mục có trọng số dương nếu yêu cầu mỗi lượt chọn một mục mới với xác suất tỷ lệ theo trọng số hiện tại. Khi tổng còn lại W=0, phép chọn tiếp **không xác định**. Các thuật toán weighted reservoir sampling có những hợp đồng khác tùy dạng đầu vào/thiết kế mẫu; cần đọc đúng định nghĩa sampling without replacement của bài.

### Không nhầm “lấy k mẫu” với “mẫu k phần tử khác nhau”

Chạy `drawIndex` k lần chỉ tạo **k kết quả có hoàn lại**. Muốn k mục phân biệt, cần chiến lược cập nhật hoặc thuật toán mẫu-k khác. Lấy kết quả rồi dùng HashSet bỏ trùng sẽ làm số phần tử ít hơn k và thay đổi phân phối thống kê.

## 13. So sánh prefix, alias, Fenwick và weighted reservoir

| Yêu cầu | Cách phù hợp | Tiền xử lý / cập nhật | Chọn một mục |
|---|---|---|---|
| Một lần draw, n nhỏ | Quét tổng và trừ | O(n), không cần mảng prefix | O(n) |
| Nhiều draw, trọng số tĩnh | **Prefix + binary search** | O(n) | **O(log n)** |
| Rất nhiều draw, trọng số tĩnh | **Alias method** | O(n) | Thường **O(1)** |
| Draw xen kẽ cập nhật weights | **Fenwick / segment tree** | O(n) xây, O(log n) cập nhật | **O(log n)** |
| Mẫu k mục không hoàn lại | Fenwick xóa mục đã chọn hoặc thuật toán mẫu-k phù hợp | Tùy mô hình | Thường O(log n) mỗi chọn với Fenwick |
| Dữ liệu đến từng phần, không muốn lưu cả tập | **Weighted reservoir sampling** | Xử lý luồng, không cần tổng trước nếu chọn đúng biến thể | Theo dòng dữ liệu |
| Miền tổng trọng số vượt long | Prefix BigInteger + ticket BigInteger bounded | Phép BigInteger và RNG phù hợp | Binary search theo số lớn |

### Alias method có gì khác?

Alias method xây một bảng biến mỗi lần chọn thành việc lấy ngẫu nhiên một ô và quyết định theo một ngưỡng. Với phân phối tĩnh và nhiều draw, nó có thể giảm thời gian mỗi lượt so với binary search. Đổi lại:
- Cài đặt phức tạp hơn.
- Phải xử lý chuẩn hóa trọng số, bảng ngưỡng và alias.
- Tính chính xác số học và sinh random phải phù hợp yêu cầu.
- Khi trọng số thay đổi, bảng alias thường phải dựng lại hoặc dùng biến thể động.

Nếu có 1000 mục và chỉ 3 lần draw, tiền xử lý alias ít khi đáng hơn một lần quét đơn giản.

### Weighted reservoir sampling không phải tiền tố

Reservoir sampling được thiết kế cho **luồng dữ liệu**, khi không biết toàn bộ n hoặc không muốn lưu mọi phần tử. Với một số biến thể có trọng số, có thể tạo khóa ngẫu nhiên cho mỗi mục và duy trì k khóa tốt nhất mà không cần W biết trước. Các biến thể có thể cho **định nghĩa xác suất mẫu k** khác nhau; không được mặc định chúng đồng nhất với lấy k lần theo trọng số rồi loại mục đã chọn.

## 14. Những lưu ý về chính xác số học

### Tổng không âm và monotonicity

Prefix phải không giảm. Nếu có trọng số âm hoặc tổng overflow, mảng có thể giảm:

~~~text
weights: [5, -7, 10]
prefix : [5, -2, 8]   // invalid distribution
~~~

Binary search vốn dựa trên tính không giảm của prefix, nên kết quả không còn đáng tin. Không nên cố sort lại prefix: sort sẽ phá ánh xạ khoảng về các mục ban đầu và không chữa được trọng số âm.

### Số thực không chính xác và ticket nguyên

Nếu dữ liệu là xác suất thập phân như `[0,1;0,2;0,7]`, phải chọn một mô hình:
- Nhân với hệ số **chính xác** để chuyển thành số nguyên (ví dụ [1,2,7] nếu nguồn có ba giá trị thập phân đúng như vậy).
- Dùng BigDecimal/BigInteger và quy đổi với độ chính xác được xác định rõ.
- Hoặc dùng prefix double, sinh U∈[0,1), binary search theo tổng real với chấp nhận sai số làm tròn.

Không thể bảo đảm một phân phối từ số thực tùy ý **chính xác tuyệt đối** với mọi U vì floating point có số bit hữu hạn. Mã bài chọn **long integer weights** để có phép đếm vé và chứng minh rõ ràng.

### Nếu vài trọng số cực lớn, vài trọng số bằng 1

Ví dụ `[Long.MAX_VALUE−1,1]` có mục nhỏ với xác suất ~10⁻¹⁹. Dùng random double với khoảng 53 bit có thể **không có đủ mức** để thấy vé của mục cực nhỏ khi áp cắt ngưỡng thô; bounded-long ticket vẫn định nghĩa một vé có xác suất 1/W theo mô hình generator. Trong test có seed cụ thể, mục nhỏ có thể **không xuất hiện** dù code hoàn toàn đúng — không phải bug.

### Tính xác suất để in không nhất thiết chính xác

`(double)weight/total` chỉ là một tỷ số xấp xỉ. Nếu in `0.000` với ba chữ số thập phân, không có nghĩa xác suất thật bằng 0. Mục có trọng số 1 trên W rất lớn có thể in 0.000 nhưng vẫn có ticket hợp lệ. Hãy dùng **trọng số nguyên và tổng nguyên** khi cần lập luận chính xác.

### BigInteger vượt Long.MAX_VALUE

Nếu W vượt long, dùng mảng BigInteger prefix và r∈[0,W) bằng bộ sinh vé BigInteger **unbiased**, thường dựa trên **rejection sampling**: sinh ứng viên đủ bit rồi loại các giá trị ≥W. Không dùng `new BigInteger(bits, rng) % W` trực tiếp nếu muốn tính uniform chính xác, trừ khi chứng minh miền ứng viên chia hết cho W. Đây là một hướng mở rộng, không nằm trong API Java 17 long chính của bài.

## 15. Kiểm thử độc lập và các bất biến

Một bộ test tốt phải kiểm cả toán học, code và giới hạn dữ liệu.

### 15.1. Oracle quét từng trọng số

Tạo một hàm độc lập:

~~~text
linearOracle(weights, ticket):
    for i = 0..n-1:
        if ticket < weights[i]:
            return i
        ticket = ticket - weights[i]
    fail: ticket invalid
~~~

Hàm này **không cần prefix**, kiểm trực tiếp dựa trên số vé mà mỗi mục chiếm. Vì vậy nếu binary search dùng sai dấu ở biên, hai hàm sẽ trả khác nhau.

Với `weights=[3,0,2,5]`:
- ticket=3: trừ 3 ở A còn 0; qua B có w=0; đến C có 0<2 ⇒ C.
- ticket=5: qua A còn 2; qua B còn 2; qua C còn 0; đến D có 0<5 ⇒ D.

### 15.2. Exhaustive ticket test

Với W nhỏ, chạy mọi r từ 0 tới W−1 và đếm `count[i]`. Cần:

**`count[i]==weights[i]`** với từng i.

Đây là **kiểm thử chính xác toàn bộ ánh xạ**, không phải bài thống kê. Những dãy nên thử:

- `[1]`.
- `[0,1]`.
- `[1,0]`.
- `[0,1,0]`.
- `[3,0,2,5]`.
- `[0,0,5,0]`.
- `[2,2,2]`.
- `[0,1,0,1,0,1]`.
- Dãy có nhiều trọng số 0 liên tiếp.
- Một trọng số rất lớn kẹp giữa các trọng số rất nhỏ.

### 15.3. Biên dưới và trên của từng khoảng dương

Với wᵢ>0, phải có:

**`pickByTicket(S_{i−1})=i`**,  
**`pickByTicket(Sᵢ−1)=i`**.

Với wᵢ=0, khoảng [S_{i−1},Sᵢ) rỗng; không có biên vé thuộc i và i phải **không bao giờ được chọn**.

### 15.4. Tổng tràn và ticket ngoài miền

Phải từ chối:
- Danh sách rỗng.
- Trọng số âm.
- Tổng W=0.
- Tổng >Long.MAX_VALUE.
- Ticket r<0 hoặc r≥W.
- Mảng labels/weights null hay độ dài khác nhau.
- Chỉ số truy vấn probability/name ngoài [0,n−1].

Phải chấp nhận:
- W=1, ticket=0.
- W=Long.MAX_VALUE, ticket=W−1.
- Một mục có trọng số Long.MAX_VALUE và các mục còn lại trọng số 0.

### 15.5. Sao chép phòng vệ

Tạo sampler từ mảng input, rồi đổi giá trị trong **mảng input gốc**. Nếu constructor copy đúng, phân phối sampler **không thay đổi**. Tương tự, caller nhận `prefixSnapshot` rồi sửa snapshot không được làm hỏng prefix bên trong.

Nếu trả trực tiếp `long[] prefix` mutable từ API, code bên ngoài có thể phá tính không giảm và khiến binary search chọn sai. Với sampler tĩnh, defensive copy hoặc immutable representation là một phần của thiết kế đúng.

### 15.6. Kiểm ngẫu nhiên nhiều dãy

Có thể sinh 30.000 dãy trọng số với độ dài 1..32, bao gồm nhiều số 0 và các tổng nhỏ, rồi so nhiều ticket random cùng toàn bộ ticket khi W nhỏ với oracle quét. Một mô hình kiểm thử độc lập theo cách ấy đã đối chiếu **hơn 6,1 triệu lượt** binary search với quét/trừ tuyến tính, gồm hơn **762.000 kiểm tra biên** của các khoảng dương; không có sai khác. Các trường hợp BigInt gần Long.MAX_VALUE và các loại lỗi input cũng được kiểm riêng.

Những kiểm tra này củng cố tính đúng của cài đặt và xử lý ranh giới, nhưng **tính uniform cuối cùng vẫn dựa trên nguồn ticket** `nextLong(W)` đúng hợp đồng.

## 16. Những lỗi điển hình

1. **Chọn index bằng `rng.nextInt(n)`:** chỉ đúng phân phối đều, không đúng trọng số tùy ý.
2. **Nhầm wᵢ với xác suất tuyệt đối:** wᵢ phải chia cho tổng W.
3. **Không kiểm tất cả wᵢ≥0:** mảng prefix có thể giảm và binary search sai.
4. **Cho W=0 đi vào RNG bounded:** `nextLong(0)` không hợp lệ.
5. **Dùng ticket trong [0,W] thay vì [0,W):** thừa vé W.
6. **Dùng first prefix≥ticket với ticket 0-based:** sai tại ranh giới.
7. **Dùng first prefix>ticket nhưng sinh ticket 1..W:** lệch biên.
8. **Cho rằng prefix luôn tăng nghiêm ngặt:** w=0 tạo giá trị lặp.
9. **Không kiểm index trong range ở cuối binary search:** nếu total sai, có thể trả n.
10. **Dùng if thay vì while cho binary search:** không thu hẹp đến chỉ số đầu tiên đúng.
11. **Tính mid=(lo+hi)/2 trên int không xét tràn:** dùng `lo+(hi−lo)/2`.
12. **Dùng `Math.random()*W` ở W rất lớn và tuyên bố uniform integer chính xác:** thiếu độ phân giải.
13. **Dùng `nextLong()%W`:** modulo bias, có phần dư âm.
14. **Dùng `Math.abs(nextLong())%W`:** Long.MIN_VALUE và bias vẫn tồn tại.
15. **Tràn long khi tính tổng:** prefix có thể wrap âm.
16. **Clamp tổng ở Long.MAX_VALUE:** thay đổi xác suất, không giải quyết chính xác.
17. **Tự sort weights trước khi build prefix:** đổi ánh xạ index không cần thiết.
18. **Xóa mục w=0 rồi quên ánh xạ index cũ:** downstream nhận sai ID.
19. **Gộp nhãn trùng mà không gộp trọng số theo chính sách:** làm xác suất nhãn sai.
20. **Cho rằng một dãy random 100 lần phải khớp chính xác 30/20/50:** tần suất ngẫu nhiên dao động.
21. **Test bằng chính hàm binary search làm oracle:** không độc lập.
22. **Chỉ test ticket=0 mà không test ticket đúng prefix[i]:** bỏ lỗi off-by-one.
23. **Chỉ test mọi trọng số dương:** bỏ các giá trị prefix trùng do zero.
24. **Trả mảng prefix mutable:** caller có thể phá bất biến.
25. **Cho caller sửa weights sau constructor mà mong picker thay đổi:** picker đã copy, cần tạo lại hoặc API update chuyên dụng.
26. **Thay weights trong bộ nhớ nhưng không cập nhật prefix:** phân phối stale.
27. **Tái seed RNG giống nhau ở mỗi lần draw:** có thể lặp cùng chuỗi/ticket đầu, không đáp ứng kỳ vọng các lượt mới.
28. **Dùng SplittableRandom cho mục tiêu chống dự đoán:** nó không phải RNG bảo mật.
29. **Cho rằng nhiều draw là không hoàn lại:** prefix tĩnh là with replacement.
30. **Đặt trọng số mục vừa chọn thành 0 nhưng không cập nhật tổng:** vé không tương ứng với phân phối mới.
31. **Cố lấy thêm mục khi không còn trọng số dương:** W=0 không định nghĩa draw.
32. **Xây lại prefix O(n) cho mọi draw dù weights tĩnh:** mất lợi thế tiền xử lý.
33. **Áp alias method cho dữ liệu đổi liên tục mà không rebuild:** bảng có thể cũ.
34. **Dùng Fenwick nhưng quên cumulative search theo tổng trái và trừ ticket:** chọn sai node.
35. **Lấy mảng ticket từ xác suất đã làm tròn, không giữ trọng số gốc:** phân phối có thể đổi.
36. **Coi xác suất in 0.000 là đúng bằng 0:** do làm tròn hiển thị.
37. **Dùng double để tích lũy vô hạn số lượng trọng số không kiểm sai số:** prefix có thể mất khả năng phân biệt các trọng số nhỏ.
38. **Cho mọi object RNG thread-safe:** phải đọc hợp đồng RNG/điều kiện chia sẻ.
39. **So sánh thời gian draw mà quên thời gian build prefix:** đánh giá sai khi Q nhỏ.
40. **Khẳng định O(1) cho binary search:** lấy mẫu theo prefix thông thường O(log n).
41. **Cho rằng modulo bias chỉ xảy ra với W lớn:** có thể xuất hiện bất kỳ W không chia đều kích thước miền nguồn.
42. **Dùng trọng số nguyên âm để biểu diễn “phạt” trong phân phối:** phải biến đổi thành trọng số không âm theo một mô hình riêng.
43. **Không xử lý all-zero sau khi lọc ứng viên:** không có mục hợp lệ để chọn.
44. **Lưu total vào int dù weights là long:** tràn ở quy mô vừa.
45. **Tạo vé trước rồi sửa total:** vé trở thành ngoài miền hoặc phân phối sai.
46. **Không xác định mục trùng nhãn có được gộp hay không:** khó diễn giải xác suất ở cấp nhãn.
47. **Không phân biệt expected count và exact probability:** kiểm thử thống kê dễ báo fail giả.
48. **Dùng cùng seed và gọi số lượng RNG khác nhau rồi so chuỗi chọn mẫu từng lượt:** các bước tiêu thụ RNG khác nhau có thể cho chuỗi khác dù phân phối đúng.
49. **Coi một test tần suất ngẫu nhiên thay cho chứng minh toán học:** xác suất hiếm có thể không xuất hiện trong test.
50. **Cấp cấu trúc phức tạp khi n=1 và Q=1:** một scan đơn giản có thể đủ.

## 17. Bài tập áp dụng

**Bài 1 — Tạo bảng vé.** Với `weights=[4,0,1,3]`, tính prefix, W, các khoảng nửa mở và kết quả cho mọi ticket 0..W−1.

**Bài 2 — Tự cài upper bound.** Viết binary search không dùng thư viện để tìm first prefix[i]>r; kiểm `prefix=[3,3,5,10]`, r=3 phải trả 2.

**Bài 3 — Chứng minh xác suất.** Từ `Sᵢ−S_{i−1}=wᵢ` và ticket uniform, chứng minh xác suất item i bằng wᵢ/W; giải thích wᵢ=0.

**Bài 4 — Oracle tuyến tính.** Cài quét trừ trọng số và so với binary search cho 10.000 dãy random nhỏ; test mọi vé khi W≤100.

**Bài 5 — Robustness.** Thử weights rỗng, all-zero, chứa âm, tổng tràn long, có trọng số Long.MAX_VALUE và các mục 0. Mỗi ca phải trả kết quả hoặc lỗi theo đúng hợp đồng.

**Bài 6 — Defensive copying.** Tạo picker từ weights [2,3], sửa weights[0] thành 100 sau khi build, rồi kiểm picker vẫn có prefix [2,5]. Thử sửa mảng snapshot và xác nhận picker không đổi.

**Bài 7 — Thống kê.** Với p=[0,1;0,2;0,7], rút Q=100.000 lần và so count với kỳ vọng Qp. Đánh giá độ lệch dựa trên phân phối nhị thức, không bắt từng count chính xác 10.000/20.000/70.000.

**Bài 8 — Alias.** Tìm hiểu xây bảng alias cho 1000 mục tĩnh, so chi phí xây và draw với prefix trên Q=10,100,1.000.000.

**Bài 9 — Fenwick động.** Hỗ trợ `setWeight(i,newWeight)` và `draw()` xen kẽ, cả hai O(log n), giữ W dương và không overflow.

**Bài 10 — Without replacement.** Lấy k mục khác nhau bằng cách đặt trọng số item được chọn bằng 0 sau mỗi draw. Trình bày khi nào thuật toán dừng nếu không còn trọng số dương.

**Bài 11 — Tổng lớn.** Cho weights=[Long.MAX_VALUE,1]. Giải thích vì sao long prefix overflow, đề xuất BigInteger prefix và cách sinh vé uniform bằng rejection sampling.

**Bài 12 — Tính xác suất nhãn trùng.** Nếu danh sách mục là [(A,2),(A,3),(B,5)], tính xác suất từng **index**, sau đó xác suất nhìn thấy nhãn A hoặc B.

## 18. Checklist trước khi nộp

- Đã xác định đúng **lấy mẫu có hoàn lại** hay không hoàn lại?
- n≥1 và mọi weight là số nguyên không âm?
- Tổng W được tính chính xác, **W>0** và không tràn kiểu?
- Prefix[i] bằng tổng weights[0..i], không giảm và prefix[n−1]=W?
- Mỗi item i chiếm khoảng **[S_{i−1},Sᵢ)** với chiều dài wᵢ?
- Sinh ticket uniform **r∈[0,W)**, không có vé r=W?
- Dùng **upper_bound: first prefix[i]>r**, không dùng >= với vé 0-based?
- Có xử lý prefix lặp khi wᵢ=0?
- Có kiểm ticket âm hoặc ≥W trước binary search?
- Có dùng midpoint `lo+(hi−lo)/2` không tràn?
- Có giữ index gốc khi loại/giữ các mục weight=0?
- Có dùng `nextLong(W)` thay vì modulo hay double gây bias?
- Có phân biệt RNG mô phỏng với RNG chống dự đoán cho bài toán bảo mật?
- Nếu Q lớn và weights tĩnh, đã phân tích `O(n+Q log n)`?
- Nếu weights cập nhật, đã xây lại prefix hoặc dùng Fenwick/segment tree?
- Nếu lấy mẫu không hoàn lại, có cập nhật trọng số sau mỗi lựa chọn?
- Có test vé ngay **đầu/cuối** mỗi khoảng dương?
- Có oracle **quét/trừ tuyến tính độc lập**?
- Có test n=1, nhiều zero, all-zero, âm, tổng rất lớn và Long.MAX_VALUE?
- Có phân biệt tần suất ngẫu nhiên dao động với xác suất chính xác?
- Có đảm bảo các mảng input/snapshot không làm thay đổi state ngoài ý muốn?
- Có chứng minh ánh xạ ticket→index và xác suất wᵢ/W bằng số lượng vé?

**Kết luận:** lấy mẫu theo trọng số bằng tổng tiền tố là phép **đảo hàm phân phối tích lũy rời rạc** (*discrete inverse-CDF sampling*). Mỗi mục i chiếm một khoảng vé nguyên dài đúng **wᵢ**, nên khi sinh vé r đồng đều trong `[0,W)` và tìm **chỉ số đầu tiên có prefix[i]>r**, xác suất chọn mục i bằng chính xác **wᵢ/W**. Tiền xử lý **O(n)** và mỗi lượt chọn **O(log n)** làm kỹ thuật phù hợp cho nhiều lượt chọn **có hoàn lại** từ một bộ trọng số tĩnh. Các vấn đề dễ sai nhất là **dấu > tại biên**, **trọng số 0**, **tổng overflow**, **RNG modulo/double bias**, và nhầm với lấy mẫu không hoàn lại. Khi có nhiều cập nhật, cân nhắc Fenwick/segment tree; khi nhiều draw trên dữ liệu tĩnh, cân nhắc alias method.