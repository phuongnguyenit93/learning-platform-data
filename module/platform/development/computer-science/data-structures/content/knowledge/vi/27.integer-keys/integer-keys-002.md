# Bảng địa chỉ trực tiếp cho miền khóa nhỏ

Một câu hỏi phổ biến khi xây dựng cấu trúc dữ liệu là: **“Làm sao tìm giá trị theo khóa nhanh nhất?”** Với khóa tổng quát như tên khách hàng hay chuỗi ký tự, chương trình có thể cần bảng băm hoặc cây tìm kiếm. Nhưng khi khóa là **số nguyên trong một miền nhỏ đã biết**, ta thường không cần tính hàm băm hay đi qua nhiều nút: **dùng chính khóa làm địa chỉ của một ô trong mảng**.

Giả sử một trường học đánh số phòng từ 0 đến 99. Để lưu số chỗ trống của phòng 37, ta có thể đặt `slots[37] = 12`. Khi cần truy vấn phòng 37, chỉ cần đọc `slots[37]`. Đây là ý tưởng của **bảng địa chỉ trực tiếp** (*direct-address table*).

Đổi lại, bảng phải dành chỗ cho **mọi khóa có thể có**, kể cả những khóa chưa xuất hiện. Nếu số phòng chỉ có 100 giá trị, khoản chi này nhỏ. Nếu khóa là mã đơn hàng 32 bit rải rác trong hàng tỷ khả năng, cấp phát trực tiếp theo toàn miền có thể rất lãng phí hoặc không khả thi.

Bài học trình bày cách xây bảng địa chỉ trực tiếp từ mảng, chuẩn hóa khóa âm sang chỉ số không âm, tách trạng thái **có khóa** khỏi **giá trị lưu trữ**, chứng minh tính đúng đắn và độ phức tạp, xử lý tràn số, lựa chọn giữa bảng trực tiếp/bitset/bảng băm/cây cân bằng, rồi cài đặt một bảng `int → int` bằng Java có thể chạy độc lập.

## 1. Bài toán và ba tham số cần phân biệt

Ta quản lý một tập ánh xạ:

\[
D=\{(k_1,v_1),(k_2,v_2),\ldots,(k_n,v_n)\},
\]

trong đó mỗi khóa `k_i` là duy nhất và thuộc **miền khóa hữu hạn** `\mathcal{U}`. Những phép toán cơ bản:

- `containsKey(k)`: có mục mang khóa `k` không?
- `get(k)`: lấy giá trị đi kèm khóa `k`, hoặc báo không tìm thấy.
- `put(k,v)`: thêm khóa mới hoặc cập nhật giá trị khóa đang có.
- `remove(k)`: xóa mục tương ứng.

Ba ký hiệu:

| Ký hiệu | Ý nghĩa | Ví dụ mã phòng 0–99 |
| --- | --- | --- |
| `U=|\mathcal U|` | **Số khóa có thể có** trong miền | `U=100` |
| `n` | **Số khóa hiện được lưu** | 17 phòng đang có bản ghi: `n=17` |
| `w` | **Độ rộng từ máy** trong mô hình Word-RAM | Ví dụ `w=64` bit |

Luôn có `0\le n\le U` với khóa phân biệt. **`U` khác `n`**: bảng trực tiếp cấp phát theo `U`, không phải theo `n`.

Với miền liên tục:

\[
\mathcal U=\{0,1,\ldots,U-1\},
\]

giá trị khóa tự nó đã là **chỉ số hợp lệ**. Với miền đóng `[a,b]`, ta có:

\[
\boxed{U=b-a+1}\qquad(a\le b).
\]

Nếu miền lớn nhưng chỉ có ít khóa, **mật độ** `\rho=n/U` nhỏ; đó là dấu hiệu cần cân nhắc một biểu diễn thưa thay vì bảng trực tiếp dày đặc.

## 2. Bảng địa chỉ trực tiếp lưu dữ liệu như thế nào?

Với miền `0..7`, giả sử có ba mục:

\[
D=\{(1,25),(3,0),(6,40)\}.
\]

Bảng có **tám vị trí**, mỗi vị trí tương ứng một khóa:

```text
Khóa k:        0       1       2       3       4       5       6       7
             +-------+-------+-------+-------+-------+-------+-------+-------+
occupied[k]: | false | true  | false | true  | false | false | true  | false |
             +-------+-------+-------+-------+-------+-------+-------+-------+
value[k]:    |   -   |  25   |   -   |   0   |   -   |   -   |  40   |   -   |
             +-------+-------+-------+-------+-------+-------+-------+-------+

Ví dụ:
  containsKey(3) -> true
  get(3)         -> tìm thấy giá trị 0
  containsKey(4) -> false
  put(4, 90)     -> occupied[4] = true; value[4] = 90
```

**Điểm đặc biệt:** khóa `3` không được “băm sang ô nào đó” hoặc so sánh với khóa lưu trong nút. Nó **được xác định trước** phải nằm ở ô `3`.

### Hai mảng cho một ánh xạ

Trong ví dụ:

- `occupied[k]` cho biết mục có tồn tại không.
- `value[k]` chứa giá trị nghiệp vụ nếu mục tồn tại.

Nếu bảng chỉ quản lý **tập khóa có/không**, một mảng `boolean[]` hoặc bitset có thể đủ. Nhưng nếu bài toán yêu cầu ánh xạ **khóa → giá trị**, phải lưu cả dữ liệu hoặc tham chiếu dữ liệu.

### Vì sao không thể chỉ dùng giá trị 0 để biểu thị ô trống?

Mục `(3,0)` trong ví dụ là **hợp lệ**. Nếu lấy `value[k] == 0` để suy ra “không có khóa”, ta sẽ kết luận sai rằng khóa 3 vắng mặt.

Giải pháp:

1. Dùng **cờ tồn tại riêng**, như `occupied[k]`.
2. Hoặc dùng một **sentinel** nằm ngoài tập giá trị hợp lệ, nếu có thể chứng minh giá trị ấy không bao giờ là dữ liệu thật.
3. Hoặc dùng một kiểu chứa trạng thái như `OptionalInt` khi trả kết quả.

Trong bài này, ta dùng cách 1 để có thể lưu được **mọi giá trị `int`**, kể cả `0`, `-1`, `Integer.MIN_VALUE`.

## 3. Phân biệt direct addressing với hashing

Hai cấu trúc đều có thể dùng mảng, nhưng ý nghĩa của việc tính chỉ số khác nhau.

**Bảng địa chỉ trực tiếp:** dùng một phép ánh xạ **một-một**, ví dụ:

\[
\operatorname{index}(k)=k
\]

cho miền `0..U-1`. Hai khóa khác nhau luôn chiếm hai ô khác nhau; **không có va chạm do ánh xạ**.

**Bảng băm:** thường có mảng số ô `m` **nhỏ hơn rất nhiều so với số giá trị khóa có thể có**. Hàm băm `h(k)` đưa khóa vào một trong các ô đó:

\[
h:\mathcal U\to\{0,\ldots,m-1\}.
\]

Khi `U>m`, theo nguyên lý Dirichlet, **tồn tại** ít nhất hai khóa khác nhau có cùng giá trị băm. Vì vậy cần cách giải quyết **va chạm** (chaining, open addressing hoặc phương án khác).

| Tiêu chí | Direct-address table | Hash table thông dụng |
| --- | --- | --- |
| Số ô cấp phát | Theo `U`, số khóa **có thể có** | Theo `n` và hệ số tải |
| Ánh xạ tới ô | Khóa/chỉ số trực tiếp, một-một trên miền | Hàm băm có thể ánh xạ nhiều khóa vào cùng ô |
| Va chạm khóa do ánh xạ | Không | Có thể có |
| Tra cứu sau cấp phát | O(1) trường hợp xấu nhất trong Word-RAM | O(1) trung bình/kỳ vọng với giả định phù hợp; worst-case tùy cài đặt |
| Chi phí bộ nhớ khi miền cực lớn nhưng thưa | Có thể rất cao | Thường phù hợp hơn |
| Cần kiểm tra khóa gốc trong bucket? | Không | Thường có, để phân biệt khóa va chạm |

**Không gọi một phép lấy phần dư `k % m` là direct addressing** nếu có nhiều khóa hợp lệ khác nhau cùng cho một chỉ số. Khi đó, cách ánh xạ không còn một-một và cần giải quyết va chạm.

## 4. Ánh xạ miền có khóa âm hoặc không bắt đầu ở 0

Giả sử mã kho là số nguyên từ `-3` đến `6`. Không thể dùng `value[-3]` trong mảng Java. Ta chuẩn hóa:

\[
\boxed{\operatorname{index}(k)=k-a}
\]

với miền `[a,b]`, `U=b-a+1`.

Ví dụ `a=-3`, `b=6`:

| Khóa `k` | Chỉ số `k-(-3)` |
| ---: | ---: |
| -3 | 0 |
| -2 | 1 |
| 0 | 3 |
| 3 | 6 |
| 6 | 9 |

```text
Giá trị khóa:  -3  -2  -1   0   1   2   3   4   5   6
Chỉ số mảng:   0   1   2   3   4   5   6   7   8   9
               ^               ^           ^       ^
               |               |           |       |
            index(-3)=0     index(0)=3   idx(3)=6 idx(6)=9
```

### Vì sao ánh xạ không gây va chạm?

Với hai khóa `x` và `y` trong miền:

\[
\operatorname{index}(x)=\operatorname{index}(y)
\Rightarrow x-a=y-a
\Rightarrow x=y.
\]

Vậy hai khóa phân biệt không bao giờ dùng chung một chỉ số. Hơn nữa:

\[
0\le k-a\le b-a=U-1.
\]

Mọi khóa hợp lệ ánh xạ vào đúng phạm vi mảng. Ánh xạ ngược là:

\[
\boxed{k=a+\operatorname{index}(k).}
\]

Điều kiện bảo toàn **chỉ số hợp lệ** là một bất biến quan trọng của cấu trúc.

### Luôn kiểm tra miền trước khi lấy chỉ số

Mọi thao tác `get/put/remove/containsKey` theo hợp đồng của bài phải từ chối khóa `k<a` hoặc `k>b`. Không dùng chỉ số âm và cũng không “quay vòng” từ khóa ngoài miền về một ô hợp lệ bằng phép modulo.

Một API khác có thể cho phép `containsKey(k)` trả `false` với khóa ngoài miền; cách nào cũng có thể hợp lý nếu **nêu rõ hợp đồng**. Ví dụ Java của bài chọn **ném `IllegalArgumentException`** khi thao tác tra cứu/chèn/xóa nhận khóa ngoài miền.

## 5. Cẩn thận với số nguyên cực trị và kích thước mảng

Tính `U=b-a+1` bằng kiểu `int` có thể tràn. Ví dụ:

```java
int low = Integer.MIN_VALUE;
int high = Integer.MAX_VALUE;

int wrong = high - low + 1; // Tràn số, không biểu diễn được U.
```

Toàn bộ miền `int` có:

\[
U=2^{32}=4\,294\,967\,296
\]

khả năng. Giá trị này **không vừa trong `int` có dấu**. Hãy mở rộng kiểu **trước phép trừ**:

```java
long universe = (long) high - (long) low + 1L;
long offset = (long) key - (long) low;
```

`long` đủ để giữ hiệu của mọi cặp khóa `int` và tính số phần tử của đoạn nguyên đóng. Nhưng:

**Có thể biểu diễn `U` bằng `long` không đồng nghĩa có thể tạo một mảng `U` phần tử.** Các mảng Java có chỉ số `int` và còn chịu giới hạn JVM/bộ nhớ thực tế, thường nhỏ hơn ngưỡng lý thuyết.

Vì vậy, trước khi cấp phát, cần:

1. Xác nhận `a\le b`.
2. Tính `U` bằng `long`.
3. Kiểm tra `U` có vừa phạm vi chỉ số mảng không.
4. Kiểm tra `U` có nằm trong **ngân sách bộ nhớ do ứng dụng đặt ra** không.
5. Chỉ khi đó mới ép về `int` và tạo mảng.

Trong mã Java, ta cho phép truyền **`maxSlots`** để đặt giới hạn số ô theo nhu cầu bài toán. Đây là một ràng buộc **của ứng dụng minh họa**, không phải giới hạn bản chất của phương pháp direct addressing.

## 6. Bất biến dữ liệu của bảng địa chỉ trực tiếp

Để cấu trúc đúng sau mọi thao tác, cần bảo đảm:

| Bất biến | Diễn giải |
| --- | --- |
| Miền được cố định | Khóa hợp lệ thuộc `[a,b]`, `U=b-a+1` |
| Ánh xạ chỉ số đúng | `index(k)=k-a` luôn nằm trong `[0,U-1]` |
| Mỗi khóa đúng một ô | Không có hai khóa khác nhau dùng chung chỉ số |
| Cờ tồn tại | `occupied[index(k)]` đúng **khi và chỉ khi** khóa `k` đang lưu |
| Giá trị | Khi cờ đúng, `values[index(k)]` là giá trị của khóa |
| Số mục | `size` bằng số ô có `occupied[i]=true` |
| Không sửa mục lân cận | Cập nhật khóa `k` chỉ thay trạng thái ô `index(k)` và `size` nếu cần |

Ví dụ với miền `[-3,6]`:

```text
occupied[0] = true,  values[0] = 0    -> có khóa -3, giá trị 0
occupied[3] = true,  values[3] = 40   -> có khóa 0,  giá trị 40
occupied[6] = false                  -> không có khóa 3
occupied[9] = true,  values[9] = 70   -> có khóa 6,  giá trị 70

size = 3
```

**Lưu ý:** nếu dùng mảng `values[]`, những ô không có khóa có thể chứa dữ liệu cũ. Tính đúng đắn của cấu trúc phải dựa trên **`occupied[]`**, không dựa vào giá trị ngẫu nhiên còn sót trong ô trống. Có thể xóa giá trị về 0 khi `remove` để thuận tiện vệ sinh bộ nhớ, nhưng **0 không được coi là “không có khóa”**.

## 7. Cài đặt các thao tác cơ bản

Với miền chuẩn hóa `0..U-1`, mã giả:

```text
containsKey(k):
    checkRange(k)
    i = index(k)
    return occupied[i]

get(k):
    checkRange(k)
    i = index(k)
    if not occupied[i]:
        return NOT_FOUND
    return FOUND(values[i])

put(k, value):
    checkRange(k)
    i = index(k)
    if occupied[i]:
        values[i] = value           # cập nhật khóa cũ
        return UPDATED
    occupied[i] = true
    values[i] = value
    size++
    return INSERTED

remove(k):
    checkRange(k)
    i = index(k)
    if not occupied[i]:
        return NOT_FOUND
    occupied[i] = false
    clear values[i] if desired
    size--
    return REMOVED
```

### Thêm khóa mới

Trước `put(3,50)`:

```text
index(3) = 6
occupied[6] = false
size = 3
```

Sau:

```text
occupied[6] = true
values[6] = 50
size = 4
```

Không cần di chuyển bất kỳ khóa nào khác.

### Cập nhật khóa đã có

Nếu `put(0,99)` với `occupied[3]=true`, chỉ thay `values[3]`. `size` **không đổi**. Một lỗi phổ biến là tăng `size` sau mọi lần gọi `put`, làm số mục bị đếm dư.

### Xóa khóa vắng mặt

Nếu `remove(4)` nhưng ô tương ứng không có mục, hàm trả thất bại và `size` **không đổi**. Không được giảm `size` chỉ vì hàm `remove` được gọi.

### Tìm thấy giá trị bằng 0

Giả sử khóa `-3` đang có giá trị 0. `get(-3)` phải trả **tìm thấy 0**, không phải “không tồn tại”. Ở Java, một kết quả kiểu `OptionalInt.of(0)` khác `OptionalInt.empty()`.

## 8. Chứng minh độ phức tạp của thao tác điểm

Giả sử bảng đã được cấp phát và khởi tạo, `U` đủ nhỏ để địa chỉ mảng hợp lệ, phép tính `index(k)` và truy cập một ô mảng tính là O(1) trong mô hình **Word-RAM**.

Khi gọi `containsKey(k)`:

1. Hai phép so sánh biên `a\le k\le b`.
2. Một phép trừ `k-a`.
3. Một lần đọc `occupied[index]`.

Không có vòng lặp theo `n` hoặc `U`. Vì vậy:

\[
\boxed{T_{\text{contains}}(n,U)=O(1)}
\]

trong **trường hợp xấu nhất**, với những giả định trên. Tương tự, `get`, `put` và `remove` chỉ chạm tới **một vị trí** cộng vài thao tác cố định:

\[
T_{\text{get}}=T_{\text{put}}=T_{\text{remove}}=O(1).
\]

Nhưng **khởi tạo bảng** có hai mảng `U` ô. Việc chuẩn bị/khởi tạo trạng thái cho đủ các ô trong mô hình thông thường có chi phí:

\[
\boxed{T_{\text{initialize}}=O(U),\quad S=O(U)\text{ ô}.}
\]

Hãy phân biệt **chi phí một thao tác sau khởi tạo** với **chi phí khởi tạo và duy trì vùng nhớ toàn miền**. Một lệnh `get` nhanh không cứu được thiết kế nếu tạo bảng ban đầu đã vượt bộ nhớ cho phép.

### Kích thước từ máy liên quan thế nào?

Nếu mỗi khóa/chỉ số nằm trong một từ có `w` bit, cần đủ khả năng biểu diễn `U` vị trí:

\[
w\ge \lceil\log_2 U\rceil
\]

trong mô hình chỉ số không dấu khi `U\ge2`. Trên máy và ngôn ngữ thực tế, kích thước địa chỉ, giới hạn mảng, overhead và bộ nhớ còn hạn chế nhiều hơn điều kiện biểu diễn bit lý thuyết.

Nếu khóa là số lớn tùy ý cần nhiều từ, phép trừ và so sánh không còn tự động O(1) theo độ dài bit; cần nói rõ mô hình tính toán trước khi đưa ra bảo đảm.

## 9. Chi phí bộ nhớ: nhanh nhưng không nhất thiết tiết kiệm

Với `U` khả năng, bảng ánh xạ `int → int` trong Java minh họa dùng:

- `int[U]`: phần dữ liệu số nguyên, **4 byte cho mỗi giá trị `int`**.
- `boolean[U]`: phần cờ tồn tại; dung lượng thực phụ thuộc cách JVM lưu mảng boolean và overhead.
- Các biến `minKey`, `maxKey`, `size`: số lượng hằng số.

Theo mô hình payload đơn giản **giả sử một boolean chiếm khoảng một byte trong mảng**, hai mảng cần xấp xỉ:

\[
4U+U=5U\text{ byte}
\]

**chưa tính header, căn chỉnh và chi phí JVM**. Đây là phép tính kế hoạch, không phải cam kết về kích thước vật lý.

| Miền `U` | `n` thực tế (ví dụ) | Payload gần đúng của hai mảng `int[]` + `boolean[]` | Nhận xét |
| ---: | ---: | ---: | --- |
| 100 | 20 | Khoảng 500 B | Rất nhỏ |
| 10.000 | 500 | Khoảng 50 KB | Có thể chấp nhận trong nhiều ứng dụng |
| 1.000.000 | 1.000 | Khoảng 5 MB | Tỷ lệ ô rỗng rất cao |
| 1.000.000.000 | 1.000 | Khoảng 5 GB | Tốn bộ nhớ lớn, có thể không cấp phát được |

Trong ví dụ `U=1\,000\,000`, `n=1\,000`:

\[
\rho=\frac{n}{U}=0.001=0.1\%.
\]

Tới **99,9% số vị trí chưa có mục**, dù bảng vẫn dành chỗ cho các vị trí đó.

### Cảnh báo về dữ liệu tham chiếu

Nếu giá trị là đối tượng hoặc chuỗi, mảng `Object[U]` lưu **tham chiếu**, và bản thân các đối tượng tồn tại ở nơi khác. Chi phí có thể gồm dung lượng tham chiếu, đối tượng, header, garbage collection và cache misses. Không được lấy phép tính `4U` của `int[U]` áp cho mọi kiểu giá trị.

### Chọn mức dày đặc không có một ngưỡng cố định

Không có quy tắc chung “nếu `n/U > 50\%` thì direct addressing luôn tối ưu”. Ngưỡng hợp lý phụ thuộc:

- Có cần payload hay chỉ membership?
- Một giá trị tốn bao nhiêu byte?
- Bao nhiêu bảng sẽ tồn tại đồng thời?
- Tỷ lệ tìm/chèn/xóa, độ lớn tập và nhu cầu quét theo thứ tự?
- Bộ nhớ có sẵn, CPU cache, độ trễ truy cập và cấu trúc thay thế?

**Độ phức tạp tiệm cận là điểm bắt đầu, không phải tiêu chí duy nhất để quyết định thiết kế.**

## 10. Tập membership: khi nào dùng bitset thay vì bảng?

Nếu chỉ cần biết **khóa có mặt hay không**, ta không cần mảng giá trị:

```text
present[k] = true/false
```

Có thể thay `boolean[U]` bằng **bitset** (*bitmap*): một bit cho một khóa. Số byte payload lý tưởng:

\[
\left\lceil\frac{U}{8}\right\rceil.
\]

Ví dụ `U=1\,000\,000`:

- Một bitset lý tưởng: khoảng **125.000 byte** (~122 KiB).
- Một mảng `int[U]` riêng cho giá trị: **4.000.000 byte** payload.
- Một bảng `int → int` có cờ tồn tại sẽ cần thêm vùng nhớ bên cạnh mảng giá trị.

| Nhu cầu | Biểu diễn có thể chọn |
| --- | --- |
| Chỉ lưu khóa tồn tại/vắng mặt | Bitset hoặc `boolean[]` |
| Khóa → số đếm/tần suất | `int[]` cùng quy ước trạng thái, hoặc mảng đếm khi 0 có nghĩa “chưa xuất hiện” |
| Khóa → giá trị nguyên mà 0 là giá trị hợp lệ | `int[]` + `occupied[]` |
| Khóa → đối tượng | Mảng tham chiếu và quy tắc xử lý `null` rõ ràng |
| Miền cực lớn, số khóa ít | Bảng băm hoặc cây cân bằng |

Bitset có thể hỗ trợ các phép hợp/giao tập bằng AND/OR theo từ máy. Nhưng nếu cần **truy cập payload**, chỉ dùng bitset không đủ; phải bổ sung nơi lưu giá trị.

## 11. Tìm min/max, successor và truy vấn khoảng

Một bảng địa chỉ trực tiếp có thể trả lời **tìm một khóa cụ thể** trong O(1), nhưng nó **không tự có chỉ mục tới khóa đang tồn tại tiếp theo**.

Ví dụ miền `0..999`, bảng chỉ chứa các khóa `\{2,500,999\}`. Để tìm khóa nhỏ nhất **không nhỏ hơn 3**, một cách đơn giản là kiểm tra:

```text
occupied[3], occupied[4], ..., occupied[500]
```

cho đến khi tìm thấy ô được đánh dấu. Trong trường hợp xấu nhất, phải quét gần `U` ô.

### Độ phức tạp các thao tác có thứ tự

| Thao tác | Bảng trực tiếp dùng mảng thông thường |
| --- | --- |
| `containsKey(k)`, `get(k)` | O(1) |
| `put(k,v)`, `remove(k)` | O(1) |
| `size()` nếu duy trì biến đếm | O(1) |
| `minKey()` / `maxKey()` bằng quét | O(U) trường hợp xấu nhất |
| `ceiling(k)`: khóa nhỏ nhất `\ge k` | O(U) trường hợp xấu nhất |
| `floor(k)`: khóa lớn nhất `\le k` | O(U) trường hợp xấu nhất |
| Liệt kê tất cả mục theo thứ tự | O(U+n) = O(U) |
| Lấy mục trong đoạn `[x,y]` | O(s+r) với `s` số chỉ số thuộc phần giao miền và đoạn, `r\le s` kết quả |
| Xóa toàn bộ bằng quét/`Arrays.fill` | O(U) |

Truy vấn khoảng `range(x,y)` có thể duyệt các chỉ số liên tiếp từ:

\[
\ell=\max(a,x)\quad\text{tới}\quad h=\min(b,y).
\]

Khi `\ell>h`, kết quả rỗng. Nếu không, độ dài đoạn chỉ số được duyệt là:

\[
s=h-\ell+1.
\]

Một vòng lặp duyệt `s` ô và xuất `r` mục có chi phí O(s+r), tương đương O(s) vì `r\le s`. **Không thể khẳng định O(log n+r)** như một cây cân bằng hoặc B+ tree có iterator thuận tiện.

### Vì sao mảng trực tiếp vẫn có thứ tự tự nhiên?

Ô chỉ số `i` tương ứng khóa `a+i`, nên quét chỉ số tăng dần sẽ trả khóa tăng dần. **Không phải sắp xếp lại kết quả**. Điểm bất lợi là phải **đi qua các ô trống**.

### Có thể tăng tốc successor không?

Có thể duy trì thêm:

- Bitset để tìm những vùng có bit hiện diện bằng thao tác trên từ.
- Danh sách liên kết các khóa đang có (nhưng cập nhật đúng vị trí có thể cần tìm kiếm).
- Cây cân bằng hoặc cấu trúc predecessor chuyên cho khóa nguyên.

Đó là những **cấu trúc bổ sung**, làm tăng chi phí cập nhật/bộ nhớ; không còn là bảng địa chỉ trực tiếp tối giản.

## 12. Java hoàn chỉnh: `DirectAddressIntMap`

Chương trình dưới đây hiện thực ánh xạ **`int → int`** trên miền đóng `[minKey,maxKey]`, cho phép khóa âm và giá trị `0`. Nó giữ hai mảng:

- `occupied[i]` cho biết ô có mục hay không.
- `values[i]` giữ giá trị nguyên.

Phương thức `put` trả `true` khi thêm một khóa mới, `false` khi chỉ cập nhật khóa đã tồn tại. `remove` trả `true` nếu đã xóa một mục. `get` trả `OptionalInt` để phân biệt **vắng mặt** với giá trị nguyên bằng 0.

`maxSlots` là giới hạn bộ nhớ mang tính thực hành: một chương trình có thể từ chối miền quá lớn **trước khi cấp phát**, kể cả khi phép tính `U` vẫn vừa kiểu `long`. Code dùng **`long` để tính hiệu và kiểm tra miền** trước khi chuyển chỉ số sang `int`.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.OptionalInt;

public class DirectAddressTableDemo {
    static final class Entry {
        final int key;
        final int value;

        Entry(int key, int value) {
            this.key = key;
            this.value = value;
        }

        @Override
        public String toString() {
            return key + "=" + value;
        }
    }

    static final class DirectAddressIntMap {
        private final int minKey;
        private final int maxKey;
        private final boolean[] occupied;
        private final int[] values;
        private int size;

        DirectAddressIntMap(int minKey, int maxKey, int maxSlots) {
            if (minKey > maxKey) {
                throw new IllegalArgumentException("Invalid key interval");
            }
            if (maxSlots < 1) {
                throw new IllegalArgumentException("maxSlots must be positive");
            }

            // Long conversion precedes subtraction to prevent int overflow.
            long universe = (long) maxKey - (long) minKey + 1L;
            if (universe > Integer.MAX_VALUE || universe > maxSlots) {
                throw new IllegalArgumentException(
                    "Universe exceeds array or application limit");
            }

            this.minKey = minKey;
            this.maxKey = maxKey;
            int capacity = (int) universe;
            this.occupied = new boolean[capacity];
            this.values = new int[capacity];
        }

        int universeSize() {
            return occupied.length;
        }

        int size() {
            return size;
        }

        private int indexOf(int key) {
            if (key < minKey || key > maxKey) {
                throw new IllegalArgumentException(
                    "Key outside universe: " + key);
            }
            return (int) ((long) key - (long) minKey);
        }

        boolean containsKey(int key) {
            return occupied[indexOf(key)];
        }

        OptionalInt get(int key) {
            int index = indexOf(key);
            if (!occupied[index]) {
                return OptionalInt.empty();
            }
            return OptionalInt.of(values[index]);
        }

        // True only when a new key is inserted.
        boolean put(int key, int value) {
            int index = indexOf(key);
            if (occupied[index]) {
                values[index] = value; // Existing key: replace value.
                return false;
            }
            occupied[index] = true;
            values[index] = value;
            size++;
            return true;
        }

        // True only when a present key is removed.
        boolean remove(int key) {
            int index = indexOf(key);
            if (!occupied[index]) {
                return false;
            }
            occupied[index] = false;
            values[index] = 0; // Hygiene only; zero may be a valid value.
            size--;
            return true;
        }

        // The smallest present key >= from, or empty.
        OptionalInt ceilingKey(int from) {
            if (from > maxKey) {
                return OptionalInt.empty();
            }
            long first = Math.max((long) from, (long) minKey);
            int start = (int) (first - (long) minKey);
            for (int i = start; i < occupied.length; i++) {
                if (occupied[i]) {
                    return OptionalInt.of((int) ((long) minKey + i));
                }
            }
            return OptionalInt.empty();
        }

        // The largest present key <= to, or empty.
        OptionalInt floorKey(int to) {
            if (to < minKey) {
                return OptionalInt.empty();
            }
            long last = Math.min((long) to, (long) maxKey);
            int start = (int) (last - (long) minKey);
            for (int i = start; i >= 0; i--) {
                if (occupied[i]) {
                    return OptionalInt.of((int) ((long) minKey + i));
                }
            }
            return OptionalInt.empty();
        }

        // All entries with from <= key <= to, in ascending key order.
        List<Entry> range(int from, int to) {
            List<Entry> result = new ArrayList<>();
            if (from > to) {
                return result;
            }
            long first = Math.max((long) from, (long) minKey);
            long last = Math.min((long) to, (long) maxKey);
            if (first > last) {
                return result;
            }
            int lowIndex = (int) (first - (long) minKey);
            int highIndex = (int) (last - (long) minKey);
            for (int i = lowIndex; i <= highIndex; i++) {
                if (occupied[i]) {
                    int key = (int) ((long) minKey + i);
                    result.add(new Entry(key, values[i]));
                }
            }
            return result;
        }

        // Clearing a direct-address table touches O(U) slots.
        void clear() {
            Arrays.fill(occupied, false);
            Arrays.fill(values, 0);
            size = 0;
        }

        // Only for tests/debug: O(U) invariant check.
        void verify() {
            if (occupied.length != values.length) {
                throw new IllegalStateException("Mismatched arrays");
            }
            int actual = 0;
            for (int i = 0; i < occupied.length; i++) {
                if (occupied[i]) {
                    actual++;
                } else if (values[i] != 0) {
                    throw new IllegalStateException(
                        "Unused slot has stale value at " + i);
                }
            }
            if (actual != size) {
                throw new IllegalStateException(
                    "Wrong size: " + size + " != " + actual);
            }
        }
    }

    public static void main(String[] args) {
        DirectAddressIntMap map =
            new DirectAddressIntMap(-3, 6, 1000);

        map.put(-3, 0); // Zero is a valid value.
        map.put(0, 40);
        map.put(3, 0);
        map.put(6, 70);

        System.out.println("U=" + map.universeSize()
            + ", size=" + map.size());
        System.out.println("contains(-3)=" + map.containsKey(-3));
        System.out.println("get(-3)=" + map.get(-3));
        System.out.println("get(5)=" + map.get(5));
        System.out.println("put(0,99) adds key=" + map.put(0, 99));
        System.out.println("remove(3)=" + map.remove(3));
        System.out.println("ceilingKey(1)=" + map.ceilingKey(1));
        System.out.println("floorKey(5)=" + map.floorKey(5));
        System.out.println("range[-1,6]=" + map.range(-1, 6));
        System.out.println("all=" + map.range(-3, 6));
        System.out.println("final size=" + map.size());

        map.verify();
        System.out.println("Invariant check: OK");

        try {
            map.containsKey(10);
        } catch (IllegalArgumentException ex) {
            System.out.println("Outside universe: rejected");
        }
    }
}
```

Đầu ra dự kiến:

```text
U=10, size=4
contains(-3)=true
get(-3)=OptionalInt[0]
get(5)=OptionalInt.empty
put(0,99) adds key=false
remove(3)=true
ceilingKey(1)=OptionalInt[6]
floorKey(5)=OptionalInt[0]
range[-1,6]=[0=99, 6=70]
all=[-3=0, 0=99, 6=70]
final size=3
Invariant check: OK
Outside universe: rejected
```

### Đọc chương trình theo bất biến

**`indexOf`** kiểm tra khóa hợp lệ rồi lấy `key-minKey`. Cả khóa âm và khóa dương đều được xử lý, bởi phép trừ dùng `long` để tránh tràn.

**`occupied` tách khỏi `values`.** Vì vậy `get(-3)` trả `OptionalInt[0]` còn `get(5)` trả `OptionalInt.empty`, dù vùng giá trị ban đầu của cả hai ô đều có thể chứa số 0.

**`put` và `remove` giữ đúng `size`.** Cập nhật khóa có sẵn không tăng `size`; xóa khóa vắng không giảm `size`.

**`range`** quét chỉ số tăng dần, nên kết quả đã được sắp theo khóa mà không cần một thao tác sort. Đổi lại, nếu khoảng rộng nhưng ít khóa, nó vẫn xét nhiều ô rỗng.

**`ceilingKey` và `floorKey`** không O(1) trong trường hợp xấu nhất; chúng chỉ là vòng quét có điểm bắt đầu, cho thấy bảng trực tiếp không tự cung cấp truy vấn predecessor/successor nhanh.

**`verify`** cố ý duyệt toàn `U` ô để kiểm tra bộ đếm và quy tắc dọn vùng trống. Điều kiện “ô trống phải có `values[i]=0`” là **quy ước vệ sinh của mã này**, không phải bất biến bắt buộc của mọi bảng trực tiếp; chỉ `occupied` quyết định sự tồn tại của mục.

### Giới hạn minh họa

Đây là cài đặt **trong RAM**. Nó chưa hỗ trợ truy cập đồng thời, lưu bền vững, khóa trùng hay tự mở rộng miền khi xuất hiện khóa ngoài cận. Mảng vẫn có thể không cấp phát được nếu ngân sách bộ nhớ thực tế không đủ, dù vượt qua bước kiểm tra `maxSlots`. Chương trình không chạy benchmark; các bảo đảm về thời gian được giải thích theo mô hình Word-RAM.

## 13. Kiểm thử đúng đắn sau chuỗi cập nhật

Một bài thử tốt cần kiểm tra cả **nội dung** và **bất biến đếm** sau nhiều thao tác:

```text
Miền [-3,6]; oracle ban đầu = {}

put(-3,0)  -> thêm mới; oracle[-3] = 0; size = 1
put(0,40)  -> thêm mới; oracle[0]  = 40; size = 2
put(3,0)   -> thêm mới; oracle[3]  = 0;  size = 3
put(0,99)  -> cập nhật; oracle[0]  = 99; size vẫn = 3
remove(3)  -> xóa; oracle bỏ 3; size = 2
remove(3)  -> thất bại; size vẫn = 2

Kiểm tra:
  containsKey(-3) == true
  get(-3) == FOUND(0)
  get(0)  == FOUND(99)
  get(3)  == NOT_FOUND
  range[-3,6] == [-3=0, 0=99]
```

Có thể dùng `HashMap<Integer,Integer>` làm oracle để kiểm tra ánh xạ khóa→giá trị và `TreeMap<Integer,Integer>` để kiểm tra các kết quả có thứ tự. Với test chạy trên miền nhỏ, **sau mỗi cập nhật**, quét tất cả khóa `a..b` rồi đối chiếu cả kết quả tồn tại lẫn giá trị:

```text
for each update:
    apply update to reference map
    apply update to direct-address table
    assert sizes match
    for key from a to b:
        assert containsKey(key) matches reference.containsKey(key)
        if key exists:
            assert get(key) equals reference.get(key)
```

Việc kiểm tra toàn miền tốn O(U) cho mỗi bước và chỉ nên dùng trong **test/debug**. Không nên đưa vòng quét này vào mỗi phép `put` của chương trình tải lớn rồi kết luận cấu trúc không còn O(1): đó là chi phí **kiểm thử bổ sung**, không phải chi phí bắt buộc của thao tác bảng.

### Các trường hợp biên nhất định phải thử

| Trường hợp | Kết quả cần có |
| --- | --- |
| Miền chỉ có một khóa `[a,a]` | `U=1`; mọi thao tác đúng với ô số 0 |
| Khóa đầu `a` | Ánh xạ tới chỉ số 0 |
| Khóa cuối `b` | Ánh xạ tới chỉ số `U-1` |
| Khóa âm hợp lệ | Không tạo chỉ số âm |
| Giá trị bằng `0` hoặc `-1` | Vẫn phân biệt được với ô trống |
| Thêm lại khóa cũ | Cập nhật giá trị, `size` không đổi |
| Xóa khóa chưa tồn tại | Không giảm `size` |
| Xóa khóa cuối cùng | `size=0`, tập rỗng |
| Khóa ngoài miền | Bị từ chối theo hợp đồng của ví dụ |
| `a=Integer.MIN_VALUE`, `b` gần `a` | Không tràn khi tính `U` và offset |
| Miền quá lớn | Từ chối trước khi ép `long` sang `int` |
| Truy vấn khoảng không giao miền | Trả danh sách rỗng |

**Lưu ý:** trong test thử toàn miền `int`, không viết `for (int k=a; k<=b; k++)` nếu `b=Integer.MAX_VALUE` mà không có điều kiện an toàn, vì phép tăng sau `Integer.MAX_VALUE` sẽ tràn về `Integer.MIN_VALUE`. Với kiểm thử một đoạn nhỏ, dùng chỉ số đã kiểm tra hoặc biến `long` nếu cần quét tới cận cực đại.

## 14. Bảng trực tiếp có thể thay đổi miền được không?

Trong thiết kế đơn giản, miền `[a,b]` được **chốt khi khởi tạo**. Nếu cần chèn khóa `b+1`, không thể ghi vào một ô chưa cấp phát.

Một cách mở rộng là:

1. Xác định đoạn mới `[a',b']` chứa đoạn cũ và khóa mới.
2. Tính `U'=b'-a'+1` và kiểm tra ngân sách bộ nhớ.
3. Cấp phát hai mảng mới độ dài `U'`.
4. Chuyển từng mục đang có từ chỉ số cũ `k-a` sang chỉ số mới `k-a'`.
5. Chỉ khi hoàn tất, thay tham chiếu bảng cũ bằng bảng mới.

Chi phí lần mở rộng có thể O(U) hoặc O(U'), tùy cách sao chép và dọn dữ liệu. Nếu phải mở rộng liên tục trên miền rất rộng, bảng trực tiếp không còn giữ ưu thế thiết kế đơn giản. Khi đó cần cân nhắc **mảng phân đoạn, bảng băm hoặc cây tìm kiếm**.

### Xóa toàn bộ và mẹo đánh dấu thế hệ

`clear()` theo cách `Arrays.fill` có chi phí O(U). Một kỹ thuật dùng trong bài toán có nhiều vòng test là giữ `stamp[i]` và một số `generation`:

```text
Một ô được xem là đang có khóa khi stamp[i] == generation.

clear():
    generation++

put(k,v):
    i = index(k)
    stamp[i] = generation
    value[i] = v
```

Nhờ đó, **xóa logic toàn bảng** có thể chỉ cần tăng `generation` O(1) trong trường hợp thường. Nhưng phải quản lý **tràn bộ đếm thế hệ**, giới hạn kiểu, khởi tạo ban đầu, trạng thái sau xóa từng khóa và nhất quán khi đồng thời; khi bộ đếm quay vòng, có thể cần quét và đặt lại stamp O(U).

Đây là **một tối ưu có thêm trạng thái**, không phải bảo đảm rằng `clear()` của bảng trực tiếp thông thường luôn O(1).

## 15. Khi nào nên chọn bảng địa chỉ trực tiếp?

Một quy trình quyết định ngắn:

1. **Khóa có nằm trong miền liên tục, hữu hạn, biết trước không?** Nếu có, xác định `a,b,U`.
2. **`U` có nhỏ tương đối với bộ nhớ cho phép không?** Tính byte cho giá trị và cờ tồn tại, không chỉ đếm ô.
3. **Tỷ lệ `n/U` có đủ cao hoặc chi phí bộ nhớ vẫn chấp nhận được không?** Nếu quá thưa, thử bảng băm/cây.
4. **Thao tác chủ yếu là get/put/remove theo khóa hay là successor/range?** Direct addressing mạnh về tra cứu điểm; quét ô trống có thể tốn kém.
5. **Có cần thay đổi miền theo thời gian không?** Nếu có, phải tính chi phí mở rộng.
6. **Cần lưu tập khóa hay ánh xạ giá trị?** Với tập membership đơn thuần, bitset có thể gọn hơn.

| Bài toán | Lựa chọn phù hợp để xem xét | Giải thích |
| --- | --- | --- |
| 101 mức điểm từ 0 tới 100 | Bảng đếm trực tiếp `count[101]` | Miền rất nhỏ, tra theo điểm tức thì |
| Cờ đã xử lý của các mã 0..1023 | Bitset 1.024 bit | Chỉ cần membership |
| Thông tin ô bàn chơi 8×8 | Mảng 64 ô hoặc mảng hai chiều | Miền khóa tọa độ nhỏ, cố định; ánh xạ được |
| 500 mã thiết bị trong miền một tỷ | Bảng băm | `U` quá lớn so với `n`; bộ nhớ theo số mục |
| Tập khóa cần `floor/ceiling` thường xuyên | Cây cân bằng/ordered map | Truy vấn có thứ tự không phải điểm mạnh của bảng quét đơn giản |
| Chỉ mục lớn trên đĩa, nhiều range scan | B+ tree | Nút nhiều nhánh và chuỗi lá cho quét theo thứ tự |
| Khóa nhỏ, đậm đặc, hàng triệu get/put | Direct-address table | Không va chạm, O(1) worst-case sau khởi tạo nếu đủ RAM |

Mỗi đề xuất là **điểm xuất phát**, không phải tuyên bố cấu trúc đó luôn nhanh nhất. Khi hệ thống có yêu cầu thực, nên đo bộ nhớ, latency, cache misses và tỷ lệ thao tác dưới dữ liệu đại diện.

## 16. Những nhầm lẫn thường gặp

1. **“Direct addressing dùng mảng theo số khóa `n`.”** Sai: bảng cấp phát theo số giá trị **có thể có `U`**.
2. **“Với miền 0..99 thì `U=99`.”** Sai: đoạn đóng có 100 khóa.
3. **“Bảng trực tiếp luôn dùng nhiều bộ nhớ hơn bảng băm.”** Không có bảo đảm chung; khi `U` nhỏ và bảng băm có overhead lớn, bảng trực tiếp có thể rất gọn.
4. **“Một phần tử lưu ở ô `k%U` cũng không va chạm.”** Chỉ đúng nếu ánh xạ là một-một trên **đúng miền hợp lệ**; modulo trên miền lớn hơn `U` có thể va chạm.
5. **“`values[k]==0` nghĩa là không có khóa.”** Sai nếu giá trị 0 hợp lệ; cần cờ tồn tại hoặc sentinel không xung đột.
6. **“Thêm lại một khóa làm `size++`.”** Sai với map khóa duy nhất: chỉ thay giá trị.
7. **“Xóa khóa vắng mặt cũng làm `size--`.”** Sai: trạng thái không đổi.
8. **“Mảng chỉ dùng cho khóa không âm.”** Có thể ánh xạ khóa âm bằng `k-minKey`.
9. **“Phép tính `max-min+1` luôn an toàn trong `int`.”** Sai với cận cực trị; dùng `long` trước phép trừ.
10. **“Nếu `U` vừa `long` thì chắc chắn tạo được mảng.”** Sai: còn giới hạn chỉ số và bộ nhớ.
11. **“`get` O(1) đồng nghĩa khởi tạo O(1).”** Sai: chuẩn bị bảng dày đặc theo `U` thường O(U).
12. **“`containsKey` nhanh thì `ceilingKey` cũng O(1).”** Sai: tìm khóa kế tiếp có thể phải quét O(U) ô.
13. **“Quét `r` kết quả chỉ tốn O(r).”** Không nhất thiết: có thể phải kiểm tra nhiều ô trống trong khoảng.
14. **“Direct addressing tự xử lý khóa trùng.”** Hợp đồng map của bài chỉ có **một giá trị cho mỗi khóa**; muốn multimap/tần suất phải đổi biểu diễn.
15. **“Bitset và bảng khóa→giá trị giống nhau.”** Bitset chỉ lưu membership, không tự giữ payload.
16. **“Java `boolean[]` chắc chắn chiếm đúng một bit/ô.”** Không phải biểu diễn bitset; chi phí do JVM quyết định.
17. **“Dùng `-1` làm NOT_FOUND là an toàn với mọi map số nguyên.”** Sai nếu `-1` là giá trị hoặc khóa hợp lệ.
18. **“Miền nhỏ về mặt số bit thì luôn nhỏ về RAM.”** Ngay cả miền 32 bit đã có `2^{32}` khóa có thể có, quá lớn cho nhiều bảng trực tiếp.
19. **“Thay đổi `minKey` mà không dịch lại mảng cũng ổn.”** Sai: mọi chỉ số `k-minKey` sẽ thay đổi.
20. **“Có thể bật validator O(U) sau mỗi thao tác trong mọi môi trường mà không ảnh hưởng hiệu năng.”** Sai: đó là chi phí kiểm thử, tách biệt khỏi O(1) của thao tác điểm.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Với miền khóa `[0,99]`, cần bao nhiêu ô trong bảng địa chỉ trực tiếp?

**Đáp án:** `U=99-0+1=100` ô.

**Câu 2.** Nếu `U=10\,000` và chỉ có `n=20` khóa đang lưu, cấu trúc trực tiếp cấp phát theo đại lượng nào?

**Đáp án:** Theo `U=10\,000` khả năng, không phải `n=20` khóa.

**Câu 3.** Bảng địa chỉ trực tiếp khác bảng băm ở đặc điểm va chạm nào?

**Đáp án:** Ánh xạ khóa vào ô là một-một trên miền hợp lệ, nên không có va chạm do ánh xạ; bảng băm có thể đưa nhiều khóa vào cùng bucket.

**Câu 4.** Với miền `[-3,6]`, khóa `3` nằm ở ô nào?

**Đáp án:** `index(3)=3-(-3)=6`.

**Câu 5.** Chứng minh nhanh hai khóa phân biệt trong đoạn `[a,b]` không vào cùng ô khi dùng `index(k)=k-a`.

**Đáp án:** Nếu `x-a=y-a` thì `x=y`; vì thế `x\ne y` kéo theo chỉ số khác nhau.

**Câu 6.** Vì sao không thể dùng giá trị 0 làm sentinel ô trống cho một ánh xạ `int→int` bất kỳ?

**Đáp án:** 0 có thể là giá trị hợp lệ; cần cờ tồn tại riêng hoặc sentinel được chứng minh không xuất hiện trong dữ liệu.

**Câu 7.** Khi `put(5,20)` được gọi hai lần trên một map chỉ có một mục cho mỗi khóa, `size` nên tăng mấy lần?

**Đáp án:** Một lần khi khóa 5 lần đầu được chèn; lần sau chỉ cập nhật giá trị, `size` không đổi.

**Câu 8.** Xóa khóa không tồn tại trong miền hợp lệ có làm giảm `size` không?

**Đáp án:** Không.

**Câu 9.** Với `a=Integer.MIN_VALUE` và `b=Integer.MAX_VALUE`, vì sao cần tính `U` trong `long`?

**Đáp án:** `U=2^{32}` vượt giới hạn `int` có dấu, nên phép trừ/cộng `int` bị tràn.

**Câu 10.** Nếu `U=1\,000\,000`, một bảng `int[]` chứa giá trị cần bao nhiêu byte payload, chưa tính metadata?

**Đáp án:** `4U=4\,000\,000` byte.

**Câu 11.** Vì sao phương thức `get` trong Java minh họa trả `OptionalInt`?

**Đáp án:** Để phân biệt “không có khóa” với một mục thực có giá trị 0 hoặc -1.

**Câu 12.** Bảng trực tiếp sau khởi tạo có độ phức tạp worst-case nào cho `containsKey`, `put` và `remove` trong Word-RAM?

**Đáp án:** O(1) cho mỗi thao tác, vì chỉ tính chỉ số và truy cập/sửa một ô.

**Câu 13.** Vì sao phương thức `clear()` dùng `Arrays.fill` không phải O(1)?

**Đáp án:** Nó cần đặt lại các ô trong một hoặc hai mảng có độ dài `U`, nên O(U).

**Câu 14.** Tìm `ceilingKey(x)` bằng quét mảng có độ phức tạp worst-case nào?

**Đáp án:** O(U), vì có thể phải kiểm tra nhiều ô không có khóa trước khi gặp một khóa hợp lệ.

**Câu 15.** Miền `0..999` có các khóa `\{2,500,999\}`. `ceilingKey(3)` trả gì và vì sao quét tuyến tính có thể chậm?

**Đáp án:** Trả 500. Cách quét đơn giản phải thử những ô từ 3 tới 500, phần lớn là ô rỗng.

**Câu 16.** Truy vấn khoảng `range(10,20)` duyệt bao nhiêu chỉ số nếu toàn bộ đoạn nằm trong miền?

**Đáp án:** `20-10+1=11` chỉ số, bất kể trong đoạn có bao nhiêu khóa thực sự.

**Câu 17.** Nếu chỉ cần lưu membership của miền `0..1023`, cấu trúc nào có thể gọn hơn `boolean[1024]`?

**Đáp án:** Bitset 1.024 bit, tương đương 128 byte payload lý tưởng, chưa tính metadata/làm tròn theo từ.

**Câu 18.** Khi `U` hàng tỷ nhưng `n` chỉ vài trăm, có thể cân nhắc cấu trúc nào thay cho bảng trực tiếp?

**Đáp án:** Bảng băm nếu ưu tiên tìm chính xác, hoặc cây cân bằng nếu cần thứ tự và predecessor/successor.

**Câu 19.** Nếu cần tự mở rộng miền từ `[0,99]` sang `[-10,99]`, tại sao phải ánh xạ lại các mục?

**Đáp án:** Chỉ số cũ là `k-0`, còn chỉ số mới là `k-(-10)=k+10`; các mục phải chuyển sang vị trí mới trong mảng đủ lớn.

**Câu 20.** Bộ kiểm tra `verify()` của ví dụ Java có bắt buộc chạy sau mỗi `put` của hệ thống sản xuất không?

**Đáp án:** Không. Nó quét O(U) để phục vụ test/debug; thao tác `put` bản chất vẫn O(1) trong mô hình đã nêu.

**Điểm ghi nhớ:** Bảng địa chỉ trực tiếp khai thác **miền khóa số nguyên nhỏ, biết trước** để ánh xạ mỗi khóa `k` vào một ô `k-a` **không va chạm**. Sau khởi tạo, `get`, `containsKey`, `put` và `remove` có thể đạt **O(1) worst-case** trong Word-RAM, đổi lại **O(U) ô bộ nhớ** và chi phí khởi tạo/clear O(U). Phải tách cờ tồn tại khỏi giá trị khi dữ liệu có thể bằng 0, tính hiệu khóa bằng kiểu đủ rộng và kiểm tra ngân sách mảng. Nếu `U` quá lớn so với `n`, hoặc cần predecessor/range thường xuyên trên tập thưa, hãy cân nhắc **bitset, bảng băm hoặc cây cân bằng** tùy yêu cầu.
