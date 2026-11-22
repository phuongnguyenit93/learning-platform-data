# Nguồn ngẫu nhiên và vai trò trong thiết kế thuật toán

**Ngẫu nhiên hóa (randomization)** là cách cho phép một thuật toán sử dụng các lựa chọn không cố định — ví dụ chọn pivot, xáo trộn đầu vào, chọn mẫu từ dòng dữ liệu, chọn điểm kiểm tra một đẳng thức hoặc chọn hàm băm. Nếu được thiết kế đúng, những lựa chọn này có thể cải thiện **hiệu năng kỳ vọng**, giảm phụ thuộc vào thứ tự đầu vào, xử lý dữ liệu chưa biết trước, hoặc đổi một phần tính chắc chắn lấy một **giới hạn xác suất lỗi đã phân tích**.

Nhưng thuật toán chỉ đáng tin khi phân biệt được: **nguồn ngẫu nhiên** đến từ đâu, **phân phối mẫu** có đúng không, **seed** ảnh hưởng thế nào tới khả năng lặp lại, sự khác biệt giữa **độ khó dự đoán và chất lượng thống kê**, và **kết quả sai có được phép xảy ra hay không**. Không có quy tắc “thêm vài lệnh `random` thì thuật toán sẽ nhanh/đúng/an toàn hơn” cho mọi trường hợp.

Bài thuộc nhóm **Ngẫu nhiên hóa** của Computer Science Algorithms. Nội dung đi từ nền tảng xác suất, entropy và trình sinh số giả ngẫu nhiên tới **Fisher–Yates shuffle**, **reservoir sampling**, **Quicksort chọn pivot ngẫu nhiên**, **kiểm tra đồng nhất đa thức xác suất (PIT)**, phân biệt **Las Vegas/Monte Carlo**, kiểm thử và tái lập thực nghiệm, và lựa chọn API ngẫu nhiên trong **Java 17**. Chương trình chạy độc lập, có kết quả mẫu xác định với `Random(2026L)` và đối chiếu bằng các phép vét cạn.

**Phạm vi:** Đây là bài học về vai trò của randomness trong **thiết kế thuật toán**, không phải hướng dẫn tự viết bộ sinh số mật mã, không bảo đảm `java.util.Random` chống được đối thủ, và không coi vài lần chạy “trông ngẫu nhiên” là chứng minh phân phối.

## 1. Ngẫu nhiên thực sự, giả ngẫu nhiên và entropy

Một **nguồn ngẫu nhiên vật lý** (*physical/true random source*, TRNG) lấy nhiễu từ hiện tượng không hoàn toàn xác định khi quan sát: nhiệt, nhiễu điện tử, bộ tạo số phần cứng hoặc nguồn entropy của hệ điều hành. Dữ liệu thô vẫn có thể **lệch phân phối**, phụ thuộc theo thời gian hoặc có lỗi thiết bị; “từ phần cứng” không tự chứng nhận dãy bit đồng đều và an toàn.

Một **bộ sinh số giả ngẫu nhiên** (*pseudorandom number generator*, PRNG) bắt đầu từ một **trạng thái/seed** và dùng quy tắc xác định để sinh dãy số:

\[
S_{t+1}=F(S_t),\qquad R_t=G(S_t).
\]

Với **cùng thuật toán, seed và trình tự gọi**, một PRNG xác định thường tạo **cùng một dãy**. Điều này rất hữu ích khi debug, benchmark và tái lập lỗi. Nhưng dãy có vẻ hỗn loạn **không đồng nghĩa** không thể dự đoán.

Một **CSPRNG** (*cryptographically secure PRNG*) được thiết kế để đầu ra **khó dự đoán về mặt tính toán** nếu được khởi tạo/duy trì đúng với entropy phù hợp. CSPRNG có thể mở rộng một lượng entropy hữu hạn thành nhiều byte giả ngẫu nhiên; nó không cần đưa ra “số ngẫu nhiên vật lý mới” cho mọi byte.

**Entropy** là lượng bất định về một biến/ngồn theo một mô hình xác suất. Nếu một bit luôn bằng 0, không có entropy dù dài hàng triệu bit. Nếu một biến chọn đều trong M khả năng thì entropy Shannon là `log₂ M` bit; trong an ninh có thể cần xét thêm **min-entropy** để đánh giá khả năng đoán giá trị phổ biến nhất.

Ví dụ: chọn một ngày trong 365 ngày bằng đồng hồ hệ thống **không tự cung cấp 128 bit bí mật** chỉ vì lưu seed vào một biến kiểu `long` có 64 bit. Số bit lưu trữ seed, entropy thật và độ khó đoán là **ba khái niệm khác nhau**.

### Ba tiêu chí thường bị đánh đồng

| Thuộc tính | Câu hỏi đúng | Ví dụ |
| --- | --- | --- |
| Phân phối | Các lựa chọn có đúng xác suất yêu cầu? | Mỗi chỉ số pivot được chọn với xác suất 1/n |
| Độc lập theo mô hình | Kết quả vòng sau có tiếp tục tuân giả thiết cần cho chứng minh? | k cơ sở Miller–Rabin mới thay vì lặp cùng một cơ sở |
| Khó dự đoán | Kẻ quan sát đầu ra có đoán được kết quả kế tiếp hoặc seed không? | Token xác thực cần CSPRNG, không dùng Random với seed đoán được |

Một PRNG có thể có **phân phối thống kê hữu ích** cho mô phỏng/quicksort nhưng **không an toàn mật mã**. Ngược lại, một nguồn byte được sinh bằng CSPRNG vẫn cần **lấy mẫu theo khoảng đúng cách** nếu muốn chọn đều số nguyên 0..n−1.

## 2. Mô hình một thuật toán ngẫu nhiên

Thuật toán ngẫu nhiên có thể được xem là:

\[
A(x;R),
\]

trong đó `x` là đầu vào và `R` là chuỗi lựa chọn ngẫu nhiên. Với cùng `x` và `R`, quá trình thực thi vẫn xác định.

Khi phân tích, cần phân biệt:

1. **Đầu vào cố định, các bit R ngẫu nhiên:** thời gian chạy/kết quả là biến ngẫu nhiên. Đây là mô hình phổ biến khi nói expected time của randomized Quicksort.
2. **Đầu vào cũng được lấy từ một phân phối:** average-case theo phân phối đầu vào. Điều này **khác** expected time do thuật toán chủ động random.
3. **Đối thủ chọn đầu vào** trước hoặc trong lúc quan sát lựa chọn: yêu cầu bảo đảm có thể thay đổi; nguồn dễ dự đoán có thể bị lợi dụng.

Ví dụ, quicksort **chọn pivot cố định** có thể rơi vào trường hợp xấu với đầu vào đã sắp xếp. Quicksort **chọn pivot đều trong đoạn đang xét** thường có `O(n\log n)` thời gian **kỳ vọng theo lựa chọn nội tại**, cho **một đầu vào cố định**. Nhưng vẫn tồn tại các chuỗi pivot bất lợi cho `O(n^2)`.

**Không hứa “ngẫu nhiên thì luôn nhanh”:** ngẫu nhiên hóa thay đổi **phân phối các đường chạy**, chứ không xóa bỏ mọi trường hợp chậm.

## 3. Lấy mẫu đều và lỗi modulo bias

Giả sử cần chọn đều một số nguyên `j\in\{0,1,\ldots,b-1\}`. Một lỗi phổ biến:

~~~text
j = random.nextInt() % b
~~~

Trong Java, `nextInt()` có thể âm và phần dư `%` có thể âm. Ngay cả khi sửa dấu bằng `Math.abs`, vẫn có thể gặp `Integer.MIN_VALUE` và **lệch xác suất** nếu kích thước miền đầu vào không chia hết cho b.

### Ví dụ nhỏ, nhìn thấy thiên lệch

Giả sử x được chọn **đều** trong `\{0,1,2,3,4,5,6,7\}` rồi lấy `x%6`:

~~~text
x:     0 1 2 3 4 5 6 7
x%6:   0 1 2 3 4 5 0 1
~~~

Các kết quả 0 và 1 xuất hiện **2/8** mỗi giá trị; 2,3,4,5 xuất hiện **1/8** mỗi giá trị. Vậy `%6` **không tạo phân phối đều trên 6 số** từ một miền đều gồm 8 phần tử.

### Cách đúng: bounded generation có loại bỏ

Trong Java 17, để chọn đều chỉ số:

~~~text
rng.nextInt(bound)      // 0 <= j < bound, bound > 0
~~~

`Random.nextInt(int bound)` dùng cơ chế phù hợp để tránh modulo bias (bao gồm rejection khi cần) theo đặc tả của nguồn pseudorandom. `SecureRandom` có API bounded tương ứng. Với miền lớn hơn hoặc đối tượng BigInteger, có thể rút một giá trị trong miền lũy thừa hai rồi **từ chối** nếu nằm ngoài khoảng đích (*rejection sampling*).

**Điều kiện:** các chứng minh “mỗi nhánh có xác suất bằng nhau” giả định nguồn các lựa chọn được lấy **đều và theo mô hình độc lập thích hợp**. Một PRNG seeded thực tế là xác định và có chu kỳ; mục đích của nó là mô phỏng hiệu quả các lựa chọn ấy, không phải tạo một nguồn entropy toán học vô hạn.

## 4. Seed và khả năng tái lập

**Seed** là giá trị khởi tạo trạng thái của PRNG. Trong Java:

~~~text
new Random(2026L)
~~~

Tạo một dãy lặp lại được theo quy tắc `java.util.Random` khi cùng seed và thứ tự gọi. Dùng cùng seed có lợi cho:
- Lặp lại một ca lỗi quicksort hoặc lấy mẫu.
- So sánh hai phiên bản thuật toán với cùng bộ lựa chọn.
- Làm ví dụ có đầu ra dự kiến ổn định trong tài liệu học.
- Kiểm thử hồi quy.

Tuy nhiên, **thứ tự gọi** là một phần của kết quả: nếu một phiên bản gọi `nextInt` thêm một lần, tất cả lựa chọn về sau có thể thay đổi. Dùng **một đối tượng Random chung qua nhiều luồng** cũng làm lịch gọi khó tái lập do interleaving. Với mô phỏng song song, nên định nghĩa rõ cách phân chia stream và lưu cấu hình seed/algorithm/partition của từng worker.

Một bản ghi thực nghiệm tốt có:
- **Seed** và thuật toán PRNG cụ thể;
- Phiên bản JDK/thư viện, dữ liệu đầu vào;
- Số vòng, kích thước mẫu, ràng buộc;
- Cách chia stream khi chạy song song;
- Tiêu chí thành công, metric, môi trường máy và các giá trị ngoại lai.

**Không dùng seed cố định để bảo vệ bí mật.** Nếu seed hoặc quy tắc PRNG bị đoán, kẻ tấn công có thể dự đoán các giá trị sắp sinh; `java.util.Random` không phù hợp cho token đăng nhập, mật khẩu tạm thời, nonce mật mã có yêu cầu riêng, khóa hay salt trong hệ thống cần an ninh thực sự.

## 5. API nguồn ngẫu nhiên trong Java 17

| API / nguồn | Vai trò thường gặp | Khả năng lặp lại | Dùng cho bảo mật? |
| --- | --- | --- | --- |
| `java.util.Random` | Bài học, test, mô phỏng nhỏ, chọn pivot | Cùng seed và trình tự gọi thường tái lập chính xác | **Không** |
| `java.util.SplittableRandom` | Phân stream trong mô phỏng/tính toán song song, thuật toán không cần crypto | Có thể tạo bằng seed; cần quản lý cách split | **Không** |
| `java.util.concurrent.ThreadLocalRandom` | Ngẫu nhiên tiện lợi theo luồng, giảm tranh chấp | Không thiết kế để người dùng đặt seed tùy ý | **Không** |
| `java.util.random.RandomGenerator` và `RandomGeneratorFactory` | Giao diện/bộ chọn thuật toán PRNG trong JDK 17 | Phụ thuộc thuật toán cụ thể, seed và thứ tự gọi | Không mặc nhiên |
| `java.security.SecureRandom` | Sinh byte khó dự đoán cho token/secret khi dùng đúng | Không giả định seed cố định sẽ tái lập trên các provider | **Có, phù hợp hơn** |
| Nguồn entropy hệ điều hành/phần cứng | Đầu vào entropy cho hệ thống RNG | Không thiết kế để replay | Tùy chất lượng/kiến trúc và xử lý |

**Chọn API theo mục tiêu.** Với ví dụ học thuật và output cần lặp lại, `Random(seed)` đủ tiện lợi. Với thử nghiệm song song, `SplittableRandom` hay các `RandomGenerator` có cách tách stream có thể tốt hơn việc chia sẻ một RNG có trạng thái. Với dữ liệu **bí mật**, `SecureRandom` thích hợp hơn; không tự triển khai CSPRNG chỉ bằng một vài phép XOR và bit shift.

`SecureRandom` là bộ sinh mã hóa dựa trên cơ chế/provider của môi trường; không nên khẳng định mọi lời gọi lấy bit “ngẫu nhiên vật lý” trực tiếp. Không giả định `setSeed` bảo đảm tái lập giống `Random(seed)` hoặc kết quả luôn giống nhau giữa JDK/provider. `SecureRandom.getInstanceStrong()` còn có thể khác nhau theo nền tảng; lựa chọn mặc định `new SecureRandom()` thường đủ cho ví dụ sinh token ngẫu nhiên, nhưng trong môi trường thực tế vẫn cần chính sách quản lý secret.

### Lưu ý về token

Dùng `SecureRandom.nextBytes(byte[])` cho một bộ byte được sinh an toàn hơn PRNG dự đoán được. Không in token bí mật thật ra console/log chỉ để debug. Ví dụ chạy ở cuối tạo **16 byte**, nhưng chỉ in **độ dài mảng**, để stdout tái lập mà không lộ giá trị.

Token 16 byte chứa **128 bit vị trí lưu**, không tự là bằng chứng mọi hệ thống triển khai đều có đúng 128 bit entropy min-entropy. Chất lượng nguồn và bối cảnh bảo mật vẫn cần được đánh giá.

## 6. Fisher–Yates: xáo trộn đồng đều

**Fisher–Yates shuffle** xáo trộn n phần tử trong **O(n)**, dùng O(1) bộ nhớ phụ nếu xáo trộn tại chỗ:

~~~text
for i = n-1 downto 1:
    j = uniformInt(0..i)
    swap(a[i], a[j])
~~~

### Tại sao là phép xáo trộn đúng?

Ở bước i, thuật toán chọn đều một trong i+1 vị trí chưa “chốt” để đưa vào a[i]. Sau khi chốt a[i], thuật toán không đụng vị trí đó nữa.

Với **n phần tử phân biệt** và lựa chọn đều/độc lập theo mô hình, bất kỳ một hoán vị cụ thể nào có xác suất:

\[
\frac1n\cdot\frac1{n-1}\cdots\frac11=\boxed{\frac1{n!}}.
\]

Mỗi chuỗi lựa chọn `j_{n-1},\ldots,j_1` tạo một hoán vị; ngược lại, mọi hoán vị xác định duy nhất chuỗi lựa chọn tương ứng.

**Phản ví dụ thường gặp:** chọn ngẫu nhiên j trong `[0,n-1]` cho mọi i rồi swap, không phải Fisher–Yates chuẩn; cách này không tạo mọi hoán vị với xác suất bằng nhau nói chung. Hoặc dùng `Math.random()*n` rồi làm tròn về số nguyên gần nhất; biên và xác suất không đồng đều.

### Nếu có phần tử bằng nhau?

Định lý `1/n!` áp dụng cho **các vị trí/phần tử được gắn nhãn phân biệt**. Khi mảng có giá trị trùng, nhiều hoán vị gắn nhãn cùng cho **một dãy giá trị hiển thị**. Đây không phải lỗi shuffle; không được đếm số hoán vị giá trị bằng số hoán vị của các nhãn rồi kết luận thiên lệch.

### Kiểm thử vét cạn n=4

Với bốn phần tử 0,1,2,3, có `4×3×2×1=24` chuỗi lựa chọn hợp lệ. Mô phỏng **toàn bộ lựa chọn** (không dựa vào PRNG) cho ra **24 hoán vị phân biệt**, mỗi hoán vị xuất hiện đúng một lần. Đây là kiểm tra cấu trúc của thuật toán Fisher–Yates, không phải bài test thống kê của bộ sinh `Random`.

## 7. Reservoir sampling: chọn k phần tử từ luồng chưa biết n

Với một dòng dữ liệu chỉ duyệt **một lượt**, độ dài n có thể chưa biết trước, **reservoir sampling** giữ đúng k phần tử mẫu mà chỉ cần **O(k)** bộ nhớ:

~~~text
reservoir = k phan tu dau
for i = k .. n-1:           // i la chi so 0-based
    j = uniformInt(0..i)
    if j < k:
        reservoir[j] = item[i]
~~~

Điều kiện phải xác định: `0≤k≤n` nếu dòng đã kết thúc. Nếu n<k, không thể trả k phần tử khác nhau; API có thể trả ít hơn k hoặc **ném lỗi**. Code bài này chọn **ném lỗi nếu k>n** để hợp đồng rõ ràng.

**Nếu k=0**, kết quả là mảng rỗng; không cần rút số ngẫu nhiên.

### Vì sao mỗi phần tử có xác suất k/n?

- Sau khi nhận k phần tử, mỗi phần tử đầu đang trong reservoir với xác suất 1.
- Khi phần tử thứ `i+1` (0-based index i≥k) xuất hiện, ta chọn j đều trong [0,i]. Nó được đưa vào reservoir khi j<k, xác suất `k/(i+1)`.
- Một phần tử cũ đang được giữ chỉ bị thay thế khi vị trí j của nó được chọn: xác suất sống sót qua vòng này `1−1/(i+1)=i/(i+1)`.
- Một phần tử đã vào reservoir ở thời điểm t có xác suất còn lại cuối cùng bằng tích xác suất sống sót, dẫn tới `k/n`.
- Thực ra, thuật toán còn tạo **một tập con k phần tử đồng đều trong tất cả \(\binom nk\) tập con**, dưới mô hình lựa chọn đều độc lập.

### Kiểm chứng bằng vét cạn n=5, k=2

Khởi tạo reservoir là [0,1]. Xét toàn bộ lựa chọn khi đọc ba phần tử có index 2,3,4:
- vòng i=2 có 3 lựa chọn;
- i=3 có 4 lựa chọn;
- i=4 có 5 lựa chọn.

Có tổng `3×4×5=60` đường chọn. Khi sắp xếp hai index trong mỗi reservoir để đại diện tập con không thứ tự, xuất hiện đúng \(\binom52=10\) tập con, mỗi tập **6 đường**, nghĩa là xác suất `6/60=1/10`. Đó là một kiểm thử đúng phân phối ở trường hợp nhỏ, không thay thế chứng minh quy nạp cho n,k tùy ý.

**Không nhầm với “chọn k lần một số trong [0,n)”**: cách đó có thể lấy trùng, và nếu loại trùng bằng retry sẽ cần thêm phân tích về chi phí/sự công bằng.

## 8. Randomized Quicksort: ngẫu nhiên hóa thời gian, không ngẫu nhiên hóa kết quả

Quicksort phân đoạn quanh pivot rồi đệ quy trên các đoạn con. Nếu pivot luôn chọn phần tử đầu/cuối, một số cấu trúc đầu vào có thể cho phân hoạch `0` và `n−1` lặp lại, gây `O(n^2)`.

**Randomized Quicksort** rút pivot **đều** từ các vị trí trong đoạn hiện tại. Với đầu vào cố định, kỳ vọng số so sánh trên mô hình pivot ngẫu nhiên là **O(n log n)**; trường hợp xấu `O(n²)` vẫn có thể xảy ra nhưng có xác suất nhỏ cho nhiều cấu hình đầu vào.

Bài dùng **3-way partition (Dutch national flag)** để xử lý trùng khóa:
- `a[lo..lt−1]<pivot`;
- `a[lt..i−1]=pivot`;
- `a[i..gt]` chưa xử lý;
- `a[gt+1..hi]>pivot`.

Mỗi bước đưa một phần tử vào vùng thích hợp. Khi hết vòng, **vùng =pivot không cần đệ quy**, giảm bất lợi khi có nhiều phần tử bằng nhau.

### Las Vegas ở đây nghĩa là gì?

Khi code partition/sort đúng, **bất kể pivot được rút ra là gì, kết quả luôn là mảng đã sắp xếp**. Ngẫu nhiên chỉ thay đổi **thời gian/đường phân hoạch**. Đây là tinh thần thuật toán **Las Vegas**: tính đúng không phụ thuộc may rủi, nhưng runtime có thể biến động.

Nếu seed bị đối thủ đoán, họ có thể chọn/thiết kế đầu vào thích hợp để gây các đường pivot tệ hơn trong một hệ thống thực; `java.util.Random` không bảo vệ được lịch pivot trước kẻ tấn công. Nếu an ninh hoặc độ ổn định trên đầu vào đối kháng là vấn đề chính, cân nhắc thuật toán có worst-case được kiểm soát như introsort hoặc chiến lược deterministic phù hợp, thay vì chỉ kỳ vọng PRNG dễ đoán.

### Kết quả mẫu

Input:

~~~text
[9,1,4,1,5,9,2,6,5,3,5]
~~~

Sau randomized 3-way Quicksort, với mọi chuỗi pivot **hợp lệ**:

~~~text
[1,1,2,3,4,5,5,5,6,9,9]
~~~

Vì kết quả sort là **xác định**, không cần biết seed để xác định stdout. Seed chỉ giúp lặp lại đường chạy cho debug.

## 9. Monte Carlo và Las Vegas: khác nhau về bảo đảm

Thuật toán ngẫu nhiên thường chia theo tính chất:

| Kiểu | Kết quả có thể sai? | Thời gian có ngẫu nhiên? | Ví dụ |
| --- | --- | --- | --- |
| **Las Vegas** | **Không** (nếu cài đúng và hoàn thành) | Có thể | Randomized Quicksort |
| **Monte Carlo** | **Có**, nhưng giới hạn xác suất lỗi | Thường có cận số vòng / runtime | Kiểm tra đồng nhất đa thức bằng đánh giá ngẫu nhiên |
| Deterministic | Không dùng lựa chọn random nội tại | Không theo RNG | Sort được chọn cố định |

Không phải thuật toán dùng ngẫu nhiên nào cũng có “tỉ lệ đúng 99%”: phải biết **loại lỗi, phân phối lấy mẫu và giới hạn toán học**.

Ví dụ đối với một thuật toán Monte Carlo **một phía**:
- Nếu phát hiện chứng cứ sai, kết luận **chắc chắn**;
- Nếu chưa thấy chứng cứ, chỉ nói **probably**;
- Chọn nhiều thử nghiệm độc lập có thể làm xác suất bỏ sót giảm.

Đối với Las Vegas, việc rút thêm nhiều mẫu không nhằm sửa kết quả sai (vì kết quả luôn đúng), mà nhằm ảnh hưởng **chi phí thực thi**, tránh một phân hoạch tệ hoặc cải thiện kỳ vọng.

## 10. Ví dụ Monte Carlo: kiểm tra đồng nhất đa thức (PIT)

Xét hai đa thức `A(x)`, `B(x)` với hệ số trên **trường hữu hạn** \(\mathbb F_{101}\) (tính modulo số nguyên tố 101). Muốn biết chúng có bằng nhau **như đa thức trên trường** hay không.

Một phép thử ngẫu nhiên:
1. Chọn `x` **đều** từ các phần tử `0,1,\ldots,100`.
2. Tính A(x) và B(x) modulo 101 bằng **Horner**.
3. Nếu `A(x)\ne B(x)`, hai đa thức **chắc chắn khác nhau**.
4. Nếu chúng bằng nhau ở x, có thể chúng là **cùng đa thức** hoặc là **hai đa thức khác nhau cùng nhận giá trị tại x**.

Nếu `D(x)=A(x)-B(x)` là một **đa thức khác 0** có bậc d trên trường, D có **không quá d nghiệm**. Vì vậy:

\[
\Pr[A(x)=B(x)\mid A\ne B]\le \min(1,d/101).
\]

Với k điểm x chọn độc lập và đều có hoàn lại:

\[
\Pr[\text{nhầm không phát hiện khác biệt qua k vòng}]
\le \left(\min(1,d/101)\right)^k.
\]

**Đây là cận theo randomness của thuật toán cho một cặp đa thức cố định**, không phải một xác suất hậu nghiệm rằng “hai đa thức có 99,9% khả năng bằng nhau” khi chúng vượt qua phép thử.

### Ví dụ cụ thể có xác suất lỗi biết chính xác

Chọn:

\[
A(x)=x^2-x=x(x-1),\qquad B(x)=0
\quad\text{trong }\mathbb F_{101}.
\]

Hai đa thức **khác nhau**, nhưng `A(x)=B(x)` tại chính xác **hai** điểm `x=0` và `x=1`. Một lần chọn đều:
- Xác suất **báo nhầm “có vẻ bằng”**: `2/101`.
- Xác suất **phát hiện khác biệt**: `99/101`.

Năm vòng độc lập cho xác suất bỏ sót **chính xác trong ví dụ này**:

\[
(2/101)^5\approx 3.04\times10^{-9}.
\]

Nếu lặp lại **cùng một x** năm lần, không được nhân xác suất `(2/101)^5`; việc kiểm tra đó chỉ thu được **một điểm thông tin**.

### Cẩn thận với miền trường

PIT này xác minh **đẳng thức modulo 101**, không trực tiếp chứng minh hai đa thức có hệ số nguyên bằng nhau trên `\mathbb Z`.

Ví dụ `A(x)=101`, `B(x)=0` là hai đa thức **khác nhau trên số nguyên**, nhưng **cùng là đa thức 0** trên `\mathbb F_{101}`. Muốn xác minh đa thức nguyên chính xác phải dùng bound hệ số, nhiều mô-đun hoặc chứng minh thích hợp.

Nếu d≥101, cận `d/101` có thể ≥1 và không còn hữu ích. Ví dụ đa thức không zero `x^{101}-x` trên `\mathbb F_{101}` nhận giá trị 0 tại **mọi điểm x trong trường**. Chọn trường đủ lớn so với bậc hoặc thêm cơ chế kiểm chứng khác nếu cần xác suất lỗi nhỏ.

### Monte Carlo một phía

Trong PIT:
- Nếu tìm được x với `A(x)≠B(x)` → **khác nhau chắc chắn**.
- Nếu mọi x đã thử cho bằng → chỉ **probably equal**.
- Nếu A và B thực sự là cùng đa thức trên trường → **không báo nhầm khác nhau**.

Đây là **one-sided error**. Mức lỗi nằm ở nhánh “báo có vẻ bằng mặc dù khác”, không phải cả hai chiều.

## 11. Ngẫu nhiên trong những cấu trúc và thuật toán khác

Ngoài các ví dụ được cài đầy đủ, randomness có vai trò ở:

**Randomized hashing:** lựa chọn một thành phần hàm băm ngẫu nhiên để giảm phụ thuộc vào cấu trúc khóa. Tính chất **universal hashing** thường bảo đảm cận xác suất va chạm cho mỗi cặp khóa dưới phân phối chọn hàm phù hợp; không có nghĩa mọi hàm băm dùng seed đều chống được đối thủ hoặc là hash mật mã.

**Treap:** mỗi node có key theo thứ tự BST và priority được lấy ngẫu nhiên; các priority độc lập, phân phối thích hợp giúp chiều cao **kỳ vọng** O(log n), nhưng tồn tại tình huống xấu. Cần chính sách xử lý priority trùng, nguồn và seed.

**Randomized selection / Quickselect:** chọn pivot ngẫu nhiên giúp tìm phần tử thứ k với thời gian kỳ vọng tuyến tính trong các mô hình chuẩn; worst-case vẫn có thể là `O(n²)`. Nếu cần bảo đảm worst-case O(n) theo lý thuyết, có thể dùng median-of-medians thay vì chỉ dựa randomness.

**Miller–Rabin:** mỗi cơ sở là một phép thử có thể chứng minh hợp số; một hợp số có thể vượt qua một số cơ sở. Với mô hình cơ sở ngẫu nhiên **đều, độc lập và thích hợp**, xác suất hợp số vượt qua k vòng có cận giảm theo k. Một **bộ cơ sở cố định được chứng nhận cho miền** (như 64-bit) có thể cho kết luận tất định trong miền đó; đây là lý do khác với cận xác suất.

**Mô phỏng Monte Carlo:** lấy mẫu nhiều kịch bản của một quá trình rồi ước lượng kỳ vọng/xác suất. Độ chính xác thường liên quan tới phương sai, số mẫu và sự độc lập, không chỉ seed. Dữ liệu có tương quan khiến công thức sai số chuẩn iid không còn áp dụng nguyên xi.

**Thuật toán streaming:** reservoir sampling hữu ích khi không biết n trước và chỉ có O(k) bộ nhớ; lấy mẫu có trọng số, sliding window hay stream vô hạn cần biến thể/phân tích khác.

### Ranh giới quan trọng

“Randomized” là **kỹ thuật thiết kế thuật toán**; “cryptographically secure” là **mức bảo vệ trước dự đoán/tấn công**; “statistically uniform” là một **tính chất phân phối**. Ba tiêu chí liên quan nhưng không tương đương.

## 12. Chương trình Java 17 chạy độc lập

File **RandomnessInAlgorithmsDemo.java** trình diễn:
1. Fisher–Yates với `Random(2026L)`.
2. Reservoir sampling k=3 của 8 số bằng một lần duyệt.
3. Randomized 3-way Quicksort, kết quả đúng bất kể pivot.
4. PIT trên trường `\mathbb F_{101}`, ví dụ `x²−x` so với 0.
5. Tần suất 10.000 lần chọn `nextInt(4)` như **thống kê chẩn đoán**, không dùng làm bằng chứng bảo mật hay kiểm định tính độc lập.
6. Sinh 16 byte token bằng `SecureRandom` và **chỉ in độ dài**, không xuất nội dung bí mật.
7. Vét cạn 24 đường shuffle, 60 đường reservoir, 364 mảng quicksort, 624 đa thức nonzero với hệ số thuộc −2..2 trên F101 để đối chiếu tính chất “đa thức khác zero bậc d có tối đa d nghiệm”.

**Cách tổ chức seed:** mỗi ví dụ deterministic tạo một đối tượng `Random(2026L)` mới để việc một phần code thêm lời gọi RNG **không ảnh hưởng** đầu ra của phần khác. Đây là cách giảm coupling giữa các demo, không phải khuyến cáo đặt cùng seed cho tất cả stream trong một mô phỏng thống kê yêu cầu độc lập.

~~~java
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Random;

public class RandomnessInAlgorithmsDemo {
    static final long SEED = 2026L;
    static final int FIELD = 101;

    // Fisher-Yates: moi buoc j deu trong [0, i].
    static void shuffle(int[] a, Random rng) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(rng, "rng");
        for (int i = a.length - 1; i > 0; i--) {
            int j = rng.nextInt(i + 1);
            swap(a, i, j);
        }
    }

    static void swap(int[] a, int i, int j) {
        int temp = a[i];
        a[i] = a[j];
        a[j] = temp;
    }

    // Doc mot lan; chi luu k phan tu.
    // Neu k > so phan tu input thi tu choi.
    static int[] reservoir(int[] stream, int k, Random rng) {
        Objects.requireNonNull(stream, "stream");
        Objects.requireNonNull(rng, "rng");
        if (k < 0 || k > stream.length)
            throw new IllegalArgumentException(
                    "Require 0 <= k <= stream length");
        if (k == 0) return new int[0];

        int[] result = Arrays.copyOf(stream, k);
        for (int i = k; i < stream.length; i++) {
            int j = rng.nextInt(i + 1);
            if (j < k) result[j] = stream[i];
        }
        return result;
    }

    // 3-way randomized Quicksort: Las Vegas.
    static void quickSort(int[] a, Random rng) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(rng, "rng");
        quickSort3(a, 0, a.length - 1, rng);
    }

    static void quickSort3(
            int[] a, int low, int high, Random rng) {
        if (low >= high) return;
        int pivot = a[low + rng.nextInt(high - low + 1)];

        int lt = low, i = low, gt = high;
        while (i <= gt) {
            if (a[i] < pivot) {
                swap(a, lt, i);
                lt++;
                i++;
            } else if (a[i] > pivot) {
                swap(a, i, gt);
                gt--;
            } else {
                i++;
            }
        }

        quickSort3(a, low, lt - 1, rng);
        quickSort3(a, gt + 1, high, rng);
    }

    // Horner: gia tri da thuc modulo FIELD.
    // He so luu theo bac tang: coeff[0] la hang so.
    static int evaluate(int[] coeff, int x) {
        long value = 0L;
        for (int i = coeff.length - 1; i >= 0; i--) {
            long c = Math.floorMod(coeff[i], FIELD);
            value = (value * x + c) % FIELD;
        }
        return (int) value;
    }

    // PIT Monte Carlo tren truong F_101.
    // true = probably equal; false = CHAC CHAN KHAC
    // nhu da thuc modulo 101.
    static boolean probablyEqual(
            int[] a, int[] b, int rounds, Random rng) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        Objects.requireNonNull(rng, "rng");
        if (rounds <= 0)
            throw new IllegalArgumentException(
                    "rounds must be positive");

        for (int r = 0; r < rounds; r++) {
            int x = rng.nextInt(FIELD);
            if (evaluate(a, x) != evaluate(b, x))
                return false;
        }
        return true;
    }

    // Dem cac diem root: CHI dung lam oracle nho.
    static int countRoots(int[] coeff) {
        int count = 0;
        for (int x = 0; x < FIELD; x++)
            if (evaluate(coeff, x) == 0) count++;
        return count;
    }

    // Bac da thuc tren F_101, -1 neu polynomial zero.
    static int degreeModField(int[] coeff) {
        for (int i = coeff.length - 1; i >= 0; i--)
            if (Math.floorMod(coeff[i], FIELD) != 0)
                return i;
        return -1;
    }

    static int[] histogram(int count, int bound, Random rng) {
        if (count < 0 || bound <= 0)
            throw new IllegalArgumentException();
        int[] freq = new int[bound];
        for (int i = 0; i < count; i++) {
            freq[rng.nextInt(bound)]++;
        }
        return freq;
    }

    // ----- VET CAN MOI NHANH CHON FISHER-YATES N=4 -----
    static void enumerateShuffle(
            int i, int[] current, Map<String,Integer> seen) {
        if (i == 0) {
            String key = Arrays.toString(current);
            seen.merge(key, 1, Integer::sum);
            return;
        }
        for (int j = 0; j <= i; j++) {
            int[] next = current.clone();
            swap(next, i, j);
            enumerateShuffle(i - 1, next, seen);
        }
    }

    // ----- VET CAN RESERVOIR N=5,K=2 -----
    // Ban dau current={0,1}; index bat dau tu 2.
    static void enumerateReservoir(
            int index, int[] current,
            Map<String,Integer> subsets) {
        if (index == 5) {
            int[] sorted = current.clone();
            Arrays.sort(sorted);
            subsets.merge(
                    Arrays.toString(sorted), 1, Integer::sum);
            return;
        }
        for (int j = 0; j <= index; j++) {
            int[] next = current.clone();
            if (j < 2) next[j] = index;
            enumerateReservoir(index + 1, next, subsets);
        }
    }

    // Test moi mang dai n tren {-1,0,1} va so voi Arrays.sort.
    static int enumerateQuickSort(int[] current, int at) {
        if (at == current.length) {
            int[] actual = current.clone();
            int[] expected = current.clone();
            Arrays.sort(expected);
            quickSort(actual, new Random(SEED));
            if (!Arrays.equals(actual, expected))
                throw new AssertionError(
                        "Quicksort mismatch");
            return 1;
        }
        int checked = 0;
        for (int v = -1; v <= 1; v++) {
            current[at] = v;
            checked += enumerateQuickSort(current, at + 1);
        }
        return checked;
    }

    // Test root bound cua moi polynomial degree <= 3
    // voi he so trong {-2,-1,0,1,2}.
    static int verifyPolynomials() {
        int count = 0;
        for (int a0 = -2; a0 <= 2; a0++)
            for (int a1 = -2; a1 <= 2; a1++)
                for (int a2 = -2; a2 <= 2; a2++)
                    for (int a3 = -2; a3 <= 2; a3++) {
                        int[] c = {a0, a1, a2, a3};
                        int degree = degreeModField(c);
                        if (degree < 0) continue;
                        if (countRoots(c) > degree)
                            throw new AssertionError(
                                    "Root bound mismatch");
                        count++;
                    }
        return count;
    }

    record Stats(
            int shufflePaths, int permutations,
            int reservoirPaths, int subsets,
            int pathsPerSubset, int quickInputs,
            int nonzeroPolynomials) {}

    static Stats verify() {
        Map<String,Integer> perms = new HashMap<>();
        enumerateShuffle(3, new int[]{0,1,2,3}, perms);
        int shufflePaths = perms.values()
                .stream().mapToInt(Integer::intValue).sum();
        if (shufflePaths != 24 || perms.size() != 24
                || perms.values().stream().anyMatch(v -> v != 1))
            throw new AssertionError(
                    "Fisher-Yates distribution");

        Map<String,Integer> subsets = new HashMap<>();
        enumerateReservoir(2, new int[]{0,1}, subsets);
        int reservoirPaths = subsets.values()
                .stream().mapToInt(Integer::intValue).sum();
        if (reservoirPaths != 60 || subsets.size() != 10
                || subsets.values().stream().anyMatch(v -> v != 6))
            throw new AssertionError(
                    "Reservoir distribution");

        int quickInputs = 0;
        for (int n = 0; n <= 5; n++)
            quickInputs += enumerateQuickSort(new int[n], 0);
        if (quickInputs != 364)
            throw new AssertionError(
                    "Unexpected Quicksort test count");

        int nonzeroPolynomials = verifyPolynomials();
        if (nonzeroPolynomials != 624)
            throw new AssertionError(
                    "Unexpected polynomial count");

        return new Stats(
                shufflePaths, perms.size(),
                reservoirPaths, subsets.size(), 6,
                quickInputs, nonzeroPolynomials);
    }

    public static void main(String[] args) {
        System.out.println("seed=" + SEED);

        int[] shuffled = {1,2,3,4,5,6,7,8,9,10};
        shuffle(shuffled, new Random(SEED));
        System.out.println("shuffle="
                + Arrays.toString(shuffled));

        int[] sample = reservoir(
                new int[]{10,20,30,40,50,60,70,80},
                3, new Random(SEED));
        System.out.println("reservoir="
                + Arrays.toString(sample));

        int[] toSort = {9,1,4,1,5,9,2,6,5,3,5};
        quickSort(toSort, new Random(SEED));
        System.out.println("quicksort="
                + Arrays.toString(toSort));

        int[] polynomial = {0,-1,1};  // x^2-x
        int[] zero = {0};
        System.out.println("polynomial.rootCount="
                + countRoots(polynomial));
        System.out.println("polynomial.probablyEqual5="
                + probablyEqual(
                    polynomial,zero,5,new Random(SEED)));

        int[] freq = histogram(
                10_000, 4, new Random(SEED));
        System.out.println("histogram4="
                + Arrays.toString(freq));

        // Khong in gia tri token ra console/log.
        byte[] token = new byte[16];
        new SecureRandom().nextBytes(token);
        System.out.println("secureTokenBytes=" + token.length);

        Stats stats = verify();
        System.out.println("verified.shufflePaths="
                + stats.shufflePaths());
        System.out.println("verified.uniquePermutations="
                + stats.permutations());
        System.out.println("verified.reservoirPaths="
                + stats.reservoirPaths());
        System.out.println("verified.reservoirSubsets="
                + stats.subsets());
        System.out.println("verified.reservoirPerSubset="
                + stats.pathsPerSubset());
        System.out.println("verified.quicksortInputs="
                + stats.quickInputs());
        System.out.println("verified.polynomials="
                + stats.nonzeroPolynomials());
        System.out.println("verification=PASS");
    }
}
~~~

Lưu file là **RandomnessInAlgorithmsDemo.java**, chạy với **JDK 17 trở lên**:

~~~bash
javac RandomnessInAlgorithmsDemo.java
java RandomnessInAlgorithmsDemo
~~~

**Đầu ra dự kiến:**

~~~text
seed=2026
shuffle=[1, 9, 2, 3, 6, 4, 8, 7, 5, 10]
reservoir=[50, 60, 40]
quicksort=[1, 1, 2, 3, 4, 5, 5, 5, 6, 9, 9]
polynomial.rootCount=2
polynomial.probablyEqual5=false
histogram4=[2486, 2480, 2548, 2486]
secureTokenBytes=16
verified.shufflePaths=24
verified.uniquePermutations=24
verified.reservoirPaths=60
verified.reservoirSubsets=10
verified.reservoirPerSubset=6
verified.quicksortInputs=364
verified.polynomials=624
verification=PASS
~~~

**Tại sao stdout có thể tái lập?** Mỗi phần in giá trị xác định dùng một `Random(SEED)` độc lập và lịch gọi cố định. `Random(2026L)` cho kết quả chọn chỉ số xác định theo quy tắc Java. Hàm `SecureRandom` tạo **giá trị khác nhau theo lần chạy**, nhưng chỉ in `token.length=16`, nên stdout không chứa dữ liệu bí mật/ngẫu nhiên không dự đoán được.

### Giải thích các dòng mẫu

- `shuffle` có 10 phần tử ban đầu, giữ nguyên đa tập giá trị nhưng thay thứ tự theo Fisher–Yates. **Một hoán vị cụ thể không chứng minh tính công bằng**; phần vét cạn n=4 mới xác nhận cấu trúc lựa chọn đồng đều.
- `reservoir=[50,60,40]` là ba giá trị từ tám phần tử đầu vào; thứ tự trong reservoir phản ánh **vị trí chứa mẫu**, không nhất thiết giữ thứ tự xuất hiện của dòng.
- `quicksort` được sắp đúng kể cả khi có các giá trị trùng 1,5,9. Seed ảnh hưởng **đường phân hoạch**, không được ảnh hưởng tính đúng của kết quả cuối.
- `polynomial.rootCount=2` xác nhận x²−x có đúng hai nghiệm trên F101 là 0 và 1.
- `polynomial.probablyEqual5=false` nghĩa là tìm được ít nhất một x với kết quả khác nhau, nên hai đa thức **chắc chắn khác trên F101**. Không được dịch `false` thành “có thể khác”.
- `histogram4` là số lần thấy từng giá trị 0..3 từ 10.000 lần rút. Những số đếm không bằng nhau tuyệt đối là **bình thường**; kỳ vọng mỗi nhóm là 2.500, không đòi chính xác 2.500. Một mẫu đếm gần nhau không đủ chứng minh PRNG an toàn mật mã.
- `verified.*` là **số trường hợp kiểm thử**, không phải số vòng chạy trong thuật toán sản xuất, cũng không phải chứng minh độc lập hoàn toàn về chất lượng của nguồn RNG.
- `verification=PASS` chỉ xuất hiện nếu mọi assert của bộ vét cạn vượt qua.

## 13. Kiểm thử: đừng nhầm RNG với logic thuật toán

### A. Fisher–Yates vét cạn không dùng Random

Hàm `enumerateShuffle` đi qua tất cả những lựa chọn j hợp lệ, không gọi PRNG. Với n=4:
- Số đường chọn: 24.
- Số hoán vị cuối khác nhau: 24.
- Số đường đi tới mỗi hoán vị: 1.

Nếu code swap sai hoặc chọn j sai miền, thuộc tính này dễ bị phá. Nhưng ngay cả khi thuộc tính đạt, để một lần chạy Fisher–Yates có phân phối đều ngoài thực tế vẫn cần nguồn các lựa chọn phù hợp.

### B. Reservoir vét cạn các đường chọn

Với n=5,k=2, hàm `enumerateReservoir` có 60 đường chọn. Chuyển hai chỉ số cuối sang tập con không thứ tự, có 10 tập con, mỗi tập được tạo bởi đúng 6 đường. Kết quả:

\[
P(\text{mot tap con 2 phan tu cu the})=6/60=1/10.
\]

Đây là kiểm thử chính xác cho n=5,k=2, bao gồm cả trường hợp mẫu có giữ phần tử đầu hoặc bị thay liên tiếp.

### C. Quicksort đối chiếu Arrays.sort

Tạo mọi mảng độ dài 0..5 có giá trị từ `{-1,0,1}`. Số mảng:

\[
1+3+9+27+81+243=\boxed{364}.
\]

Chạy randomized 3-way quicksort với seed cố định cho từng mảng và so với `Arrays.sort`. Nhóm này bao phủ mảng rỗng, một phần tử, tất cả giá trị bằng nhau, mảng đã có thứ tự, đảo thứ tự và nhiều phần tử trùng.

Điều đó kiểm tra **tính đúng của kết quả sort trên mẫu nhỏ**, không chứng minh thời gian kỳ vọng O(n log n). Kỳ vọng thời gian dựa trên phân tích xác suất của pivot.

### D. Cận số nghiệm đa thức trên F101

Xét mọi vector bốn hệ số `[a₀,a₁,a₂,a₃]` với mỗi hệ số từ `{-2,-1,0,1,2}`: có `5^4=625` vector. Loại vector [0,0,0,0] (đa thức zero), còn **624 đa thức khác zero** bậc ≤3.

Đối với từng đa thức:
- Tính bậc lớn nhất có hệ số khác 0 modulo 101.
- Đếm chính xác bao nhiêu giá trị x trong `0..100` làm đa thức bằng 0.
- Xác minh **số nghiệm không vượt bậc**.

Tất cả 624 đa thức trong nhóm thử tuân thủ cận. Đây là kiểm thử minh họa cho định lý trường hữu hạn, không phải chứng minh định lý chỉ bằng 624 ví dụ.

### E. Dùng thống kê đúng mục tiêu

Một bảng tần suất 10.000 lần rút không đủ để chứng minh tính độc lập, min-entropy hoặc khả năng chống dự đoán. Bài kiểm thử **thuật toán** bằng vét cạn các nhánh và oracle, thay vì coi “trông đều” là đủ.

Nếu đánh giá chất lượng RNG để dùng trong mô phỏng khoa học, cần các bộ kiểm định phù hợp, nhiều seed độc lập, hiểu hiện tượng cần mô phỏng và kiểm tra tương quan; với bảo mật phải dùng đánh giá mật mã chuyên biệt và nguồn entropy đáng tin. Không có một kiểm định thống kê ngắn nào chứng nhận “truly random” hay “không thể dự đoán”.

## 14. Chứng minh và phân tích xác suất

### Fisher–Yates: 1/n! cho mọi hoán vị

Giả thiết mỗi j trong `0..i` được chọn đều và các bước có phân phối độc lập thích hợp. Để có một hoán vị đích cụ thể, thuật toán phải chọn một vị trí xác định ở mỗi bước. Xác suất là tích `1/n·1/(n−1)·...·1/2=1/n!`. Bất biến: mỗi vị trí từ i+1 tới n−1 đã có giá trị cuối đúng và sẽ không bị đụng lại.

### Reservoir sampling: xác suất k/n

Với phần tử thứ t (đánh số từ 1) nếu t≤k, nó bắt đầu có xác suất ở trong reservoir là 1; qua các vòng sau sống sót với xác suất `(t/(t+1))·...·((n−1)/n)=t/n` khi t=k, và với phần tử xuất hiện muộn hơn k thì xác suất được nhận lúc xuất hiện là `k/t` rồi sống sót tiếp `t/n`, được `k/n`. Lập luận thống nhất bằng quy nạp trên số phần tử đã thấy: sau i phần tử, mỗi tập con k phần tử có xác suất `1/\binom ik`.

### Quicksort: tính đúng không cần xác suất

Bất biến phân hoạch 3 chiều đảm bảo sau vòng lặp: trái <pivot, giữa =pivot, phải >pivot. Đệ quy sort hai đoạn nhỏ hơn (có thể rỗng) cho mảng cuối có thứ tự. Lựa chọn pivot nào cũng giữ các bất biến này; vì vậy khi kết thúc, kết quả **chính xác**. Xác suất chỉ cần để phân tích số so sánh/độ sâu đệ quy.

### PIT: cận xác suất lỗi

Đa thức D=A−B khác 0, bậc d, trên trường có q phần tử thì có tối đa d nghiệm. Một x chọn đều cho xác suất “miss” tối đa d/q (với d<q). Nếu các vòng chọn x độc lập, xác suất miss toàn bộ không quá `(d/q)^k`. Trường hợp x²−x modulo 101 có **đúng hai nghiệm**, nên xác suất một vòng **chính xác** 2/101; năm vòng độc lập có xác suất bỏ sót chính xác `(2/101)^5`.

**Lỗi thường gặp:** dùng `k` điểm lựa chọn **cố định và công khai** mà vẫn viện dẫn cận theo ngẫu nhiên độc lập, hoặc coi việc đánh giá bằng nhau tại k điểm là chứng minh đẳng thức mọi hệ số trên trường.

## 15. Hiệu năng và bộ nhớ

| Thuật toán | Thời gian | Bộ nhớ phụ | Chất lượng kết quả |
| --- | --- | --- | --- |
| `Random.nextInt(bound)` | Thường hằng số kỳ vọng trên PRNG, có cơ chế bounded | O(1) | Đều theo hợp đồng API trên mô hình PRNG |
| Fisher–Yates n phần tử | O(n) | O(1) nếu tại chỗ | Hoán vị đều nếu các j đều/độc lập |
| Reservoir k của n phần tử | O(n) | O(k) | Mẫu con k đồng đều theo giả thiết |
| Randomized 3-way Quicksort | O(n log n) **kỳ vọng**, O(n²) worst-case | Ngăn xếp O(log n) kỳ vọng, O(n) worst-case | Sort đúng nếu cài đúng |
| PIT bậc ≤d, k vòng | O(kd) phép toán trường qua Horner | O(1) ngoài coefficients | Một phía, miss ≤(d/q)^k nếu d<q |
| Sinh L byte token | O(L) công việc sinh/ghi byte theo triển khai | O(L) mảng output | Cần CSPRNG, không dùng PRNG học thuật |

Với thuật toán số lớn, một phép toán trường hoặc BigInteger không nhất thiết O(1) theo **bit complexity**. Cận trên ở bảng hiểu theo số phép xử lý phần tử/hệ số với trường nhỏ 101.

**Ngẫu nhiên hóa không tự làm thuật toán có thời gian ít hơn trong mọi input.** Reservoir tối ưu cho **mô hình streaming/bộ nhớ**, không phải nhanh hơn đọc toàn bộ dữ liệu nếu vốn đã có mảng n. Quicksort ngẫu nhiên cải thiện bảo đảm kỳ vọng, không xóa trường hợp xấu. PIT giảm một câu hỏi đẳng thức về vài phép đánh giá, đổi lại một xác suất bỏ sót có cận.

## 16. An toàn trong môi trường có đối thủ

Nếu người khác có thể **chọn input để làm thuật toán chậm**, **đoán seed** hoặc **dự đoán token**, cần phân biệt ba tình huống:

- **Hiệu năng thuật toán:** một seed Random công khai có thể tạo đường pivot dự đoán được. Tính kỳ vọng toán học áp dụng khi phân phối pivot đúng và không bị đối thủ điều chỉnh thích nghi sau khi biết lịch chọn. Dùng cơ chế có worst-case giới hạn khi cần.
- **Thuật toán Monte Carlo trước đối thủ:** nếu lịch điểm đánh giá PIT công khai/cố định và đối thủ biết trước, họ có thể cố chọn đa thức làm khớp ở các điểm đó. Cận `(d/q)^k` áp dụng cho đa thức cố định độc lập với các mẫu được chọn; phải xác định mô hình đối kháng.
- **Bí mật/khóa/token:** dùng `SecureRandom` và API mật mã chuẩn; không dùng `Random`, seed thời gian hay một công thức hash tự chế để tạo dữ liệu dự đoán khó. Không log giá trị bí mật; đặt yêu cầu về vòng đời token, bảo vệ seed và kho lưu secret.

Đừng coi **bảo mật mật mã** là hệ quả của một p-value kiểm định thống kê. Dãy có vẻ phân phối đều vẫn có thể **hoàn toàn dự đoán được** nếu thuật toán sinh/seed đã lộ.

## 17. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `nextInt()%bound` | Có thể âm và bị modulo bias | `nextInt(bound)` |
| `Math.abs(nextInt())%bound` | `Integer.MIN_VALUE` vẫn âm, còn bias | Bounded API / rejection |
| Mỗi vòng shuffle chọn j từ [0,n) | Không phải Fisher–Yates đồng đều | j chọn từ [0,i] |
| Seed khác nhau trong mỗi vòng | Khó tái lập; seed có thể trùng/ít entropy | Một RNG với seed có chủ đích cho thực nghiệm |
| Chia sẻ một RNG qua nhiều luồng và đòi stdout y hệt | Lịch gọi khác nhau | Quản lý streams/partition và lịch song song |
| Dùng `Random(2026)` cho token | Đoán được nếu lộ seed | `SecureRandom` |
| Nghĩ `SecureRandom` là mỗi byte vật lý độc lập | Nhầm CSPRNG với TRNG | Hiểu entropy, provider, trạng thái |
| Lặp lại cùng điểm PIT k lần | Không giảm miss theo công thức `(d/q)^k` | Chọn mẫu mới độc lập |
| Gọi PIT bằng một prime nhỏ là kiểm tra đẳng thức nguyên | Hai đa thức khác nhau có thể trùng modulo p | Nêu miền Fp hoặc dùng nhiều prime/bound |
| Chọn d≥q rồi vẫn đòi d/q nhỏ | Cận lỗi vô ích | Trường lớn hơn bậc |
| Xem Monte Carlo là luôn sai đôi chiều | Có thuật toán **one-sided** | Phân tích nhánh lỗi cụ thể |
| Xem Las Vegas là luôn chạy nhanh | Worst-case vẫn có thể lớn | Phân biệt correctness với runtime |
| Quicksort hai chiều trên nhiều khóa trùng | Có thể phân hoạch kém | 3-way partition |
| Reservoir lấy mẫu lại từ đầu sau mỗi item | Không còn O(k) bộ nhớ/one pass | Reservoir cập nhật tại chỗ |
| k>n nhưng vẫn trả mảng toàn 0 | Mẫu không đủ k phần tử | Hợp đồng lỗi rõ ràng |
| Thống kê vài nghìn mẫu rồi tuyên bố RNG an toàn | Không chứng minh unpredictability | Phân tích nguồn/kiểm định thích hợp |
| So hai thuật toán nhưng seed/lịch gọi khác | Kết quả benchmark nhiễu, khó debug | Ghi seed, thuật toán, dữ liệu, thử nhiều seed |
| Lấy kết quả trùng 1 seed làm bằng chứng tính đúng | Có thể bỏ sót ca khác | Oracle, kiểm thử vét cạn, chứng minh bất biến |

## 18. Bài tập có đáp án

**Bài 1.** PRNG với cùng seed và cùng trình tự gọi có đặc điểm gì?

*Đáp án:* Dãy phát sinh được tái lập theo thuật toán PRNG; đó không phải bằng chứng dãy khó dự đoán.

**Bài 2.** Vì sao seed 64 bit không tự có 64 bit entropy?

*Đáp án:* Entropy phụ thuộc vào phân phối và độ bất định thật. Seed có thể chỉ lấy từ vài giá trị đoán được dù được lưu trong long.

**Bài 3.** Lấy x đều trong 0..7, dùng x%6. Kết quả nào bị chọn nhiều gấp đôi?

*Đáp án:* 0 và 1, mỗi giá trị xuất hiện hai lần; các giá trị 2..5 xuất hiện một lần.

**Bài 4.** Trong Java muốn lấy đều số 0..i, nên dùng gì?

*Đáp án:* `rng.nextInt(i+1)` với i≥0 và i+1 vừa int.

**Bài 5.** Fisher–Yates với n=4 có bao nhiêu hoán vị vị trí?

*Đáp án:* `4!=24`. Với lựa chọn đều/độc lập, mỗi hoán vị có xác suất 1/24.

**Bài 6.** Có nên chọn j từ 0..n−1 cho mọi bước Fisher–Yates?

*Đáp án:* Không. Ở bước i phải chọn j từ 0..i để mỗi vị trí chưa chốt được chọn phù hợp.

**Bài 7.** Reservoir sampling cần bao nhiêu bộ nhớ cho mẫu k?

*Đáp án:* O(k), không cần lưu toàn bộ n phần tử.

**Bài 8.** Một phần tử cố định có xác suất được giữ sau reservoir k của n là bao nhiêu?

*Đáp án:* k/n khi k≤n và lựa chọn đều theo mô hình thuật toán.

**Bài 9.** Với n=5,k=2 có bao nhiêu mẫu con không thứ tự?

*Đáp án:* \(\binom52=10\). Trong phép vét cạn 60 đường của bài, mỗi tập con xuất hiện 6 đường.

**Bài 10.** Reservoir k=0 trả gì?

*Đáp án:* Mẫu rỗng, không cần rút số ngẫu nhiên.

**Bài 11.** Vì sao randomized Quicksort là ví dụ Las Vegas?

*Đáp án:* Với partition/sort đúng, kết quả luôn sắp xếp chính xác; lựa chọn pivot chỉ ảnh hưởng thời gian.

**Bài 12.** Độ phức tạp expected và worst-case của randomized Quicksort?

*Đáp án:* O(n log n) kỳ vọng trong mô hình chuẩn, O(n²) trường hợp xấu.

**Bài 13.** 3-way partition giúp gì?

*Đáp án:* Gom các phần tử bằng pivot vào một vùng không cần đệ quy, hiệu quả hơn khi nhiều khóa trùng.

**Bài 14.** PIT trên F101 cho A=x²−x, B=0. Hai đa thức khác nhau ở đâu?

*Đáp án:* Khác trên trường; chỉ bằng nhau tại x=0 và x=1. Một điểm đều có xác suất bỏ sót 2/101.

**Bài 15.** Năm điểm PIT chọn độc lập đều cho xác suất bỏ sót ở ví dụ trên?

*Đáp án:* `(2/101)^5`, xấp xỉ 3.04×10^−9.

**Bài 16.** Nếu dùng **cùng x** năm lần trong PIT, có dùng cận `(2/101)^5` không?

*Đáp án:* Không. Chỉ có một điểm thông tin, không có năm lựa chọn độc lập.

**Bài 17.** PIT trả false ngay khi có một điểm x với A(x)≠B(x). Đây là kết luận gì?

*Đáp án:* Khác nhau **chắc chắn trên trường F101**.

**Bài 18.** Đa thức nguyên A=101 và B=0 có khác nhau không, và modulo101 thì sao?

*Đáp án:* Khác nhau trên `\mathbb Z`; lại bằng nhau như đa thức trên `\mathbb F_{101}`. Không được lẫn miền.

**Bài 19.** Vì sao kiểm tra bằng cách rút ngẫu nhiên x từ F101 không hữu ích cho mọi đa thức bậc ≥101?

*Đáp án:* Cận d/101≥1 có thể vô ích; đa thức như `x^{101}-x` không zero nhưng bằng 0 ở mọi phần tử F101.

**Bài 20.** Một histogram gần đều có chứng minh RNG là CSPRNG không?

*Đáp án:* Không. Tính khó dự đoán là thuộc tính mật mã, không suy ra từ tần suất gần đều.

**Bài 21.** Có cần thay `Random(seed)` bằng `SecureRandom` trong mọi bài Quicksort không?

*Đáp án:* Không mặc nhiên. Với bài học/debug, seeded PRNG phù hợp; với input đối kháng hoặc yêu cầu khó dự đoán phải đánh giá threat model và chiến lược thuật toán.

**Bài 22.** Khi muốn sinh token đăng nhập 16 byte, dùng nguồn nào?

*Đáp án:* `SecureRandom.nextBytes` và không log token; hệ thống an ninh còn cần quản lý token/lưu trữ/vòng đời đúng.

**Bài 23.** Vì sao cùng seed không đủ để tái lập một mô phỏng nhiều luồng?

*Đáp án:* Thứ tự gọi, cách phân stream, lịch chạy và phiên bản PRNG cũng quan trọng. Cùng seed nhưng interleaving khác có thể cho kết quả khác.

**Bài 24.** Thuật toán random chọn pivot luôn đúng nhưng đôi lúc rất chậm thuộc loại nào?

*Đáp án:* Las Vegas, vì random ảnh hưởng runtime chứ không tạo nhánh kết quả sai.

**Bài 25.** Thuật toán có thời gian cố định, xác suất kết luận sai tối đa ε là kiểu nào?

*Đáp án:* Monte Carlo (cần nêu loại lỗi và giả thiết phân phối).

**Bài 26.** Có 625 vector hệ số trong {-2,-1,0,1,2}^4. Bỏ đa thức zero còn bao nhiêu?

*Đáp án:* 624 đa thức khác 0, mỗi đa thức bậc≤3 trên F101 và có nhiều nhất bậc của nó nghiệm.

**Bài 27.** Tại sao dùng RNG “có vẻ ngẫu nhiên” không thay thế được chứng minh đúng của thuật toán?

*Đáp án:* RNG chỉ quyết định các lựa chọn; tính đúng đến từ bất biến, phân phối cần thiết và chứng minh giới hạn lỗi. Kết quả vài lần chạy không chứng minh mọi trường hợp.

## 19. Checklist thiết kế thuật toán ngẫu nhiên

1. Ghi rõ **mục tiêu của random**: cải thiện thời gian kỳ vọng, lấy mẫu, tránh thứ tự đối kháng hay chấp nhận sai số xác suất.
2. Phân biệt **nguồn entropy, PRNG, CSPRNG, TRNG**; không dùng một API cho mọi mục đích.
3. Mô tả **miền chọn** và phân phối cần thiết: đều, có hoàn lại hay không, độc lập hay không.
4. Tránh `%bound` trực tiếp; dùng bounded API/rejection sampling.
5. Chốt **seed, thuật toán RNG và trình tự gọi** để tái lập debug/benchmark.
6. Với shuffle, đảm bảo j∈[0,i], không quên rằng các phần tử trùng có thể cho cùng dãy giá trị.
7. Với reservoir, đảm bảo one pass, O(k) memory và n≥k hoặc hợp đồng báo lỗi rõ ràng.
8. Với Quicksort, chứng minh partition đúng bất kể pivot; tách expected runtime khỏi worst-case.
9. Với Monte Carlo, xác định **nhánh nào có thể sai**, độ lớn xác suất và cách giảm lỗi qua các lựa chọn độc lập.
10. Với PIT, xác nhận đa thức **khác zero trên đúng trường**, kiểm tra bậc d và số phần tử q.
11. Với dữ liệu đối kháng, xem xét tính dự đoán được của seed/PRNG và khả năng đối thủ thích nghi sau khi biết randomness.
12. Với token/secret, dùng **SecureRandom/crypto API chuẩn**, bảo vệ giá trị bí mật và không log.
13. Dùng oracle, kiểm thử vét cạn nhánh và edge cases; **histogram không phải chứng minh an toàn**.
14. Đo hiệu năng và sai số qua nhiều seed/dữ liệu, không báo một run duy nhất như trung bình kỳ vọng.
15. Công bố điều kiện áp dụng: độ dài n, kích thước k, rounds, modulo và kiểu lỗi.

## Tổng kết

Nguồn ngẫu nhiên trong thiết kế thuật toán không chỉ nhằm tạo sự bất ngờ. Nó có thể tạo **phân phối hoán vị đồng đều** trong Fisher–Yates, **mẫu k phần tử đồng đều** trong reservoir sampling, **thời gian kỳ vọng tốt** cho randomized Quicksort, hay **giới hạn xác suất bỏ sót** trong kiểm tra đồng nhất đa thức Monte Carlo. Mỗi lợi ích đòi giả thiết đúng về **phân phối và sự độc lập của các lựa chọn**.

`java.util.Random(seed)` hữu ích khi học, debug và tái lập; `SplittableRandom` và các RandomGenerator có vai trò trong việc quản lý stream hiệu quả; **SecureRandom** thích hợp cho dữ liệu cần khó dự đoán. Tính đều, tính tái lập và tính an toàn mật mã **không đồng nghĩa** với nhau. Dùng `nextInt(bound)` thay vì chia dư tùy tiện; đừng dùng EPS thống kê hay vài lần chạy để chứng nhận tính đúng/độc lập.

Chương trình Java 17 dùng seed cố định cho các demo dễ kiểm tra, còn token SecureRandom được giữ kín. Bộ kiểm thử **24 đường Fisher–Yates**, **60 đường reservoir**, **364 đầu vào Quicksort**, **624 đa thức không zero** xác nhận các bất biến trên những phạm vi đã xét; cận xác suất tổng quát vẫn dựa trên **chứng minh toán học**, không chỉ số lần test.
