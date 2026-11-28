# Tấn công gây va chạm và vai trò của ngẫu nhiên hóa hàm băm

## 1. Khi hiệu năng bảng băm trở thành vấn đề an toàn hệ thống

**Bảng băm (hash table)** thường được chọn để lưu ánh xạ khóa–giá trị vì thao tác tìm, chèn và xóa có thể đạt **thời gian kỳ vọng `O(1)`**, nếu hàm băm phân bố phù hợp và hệ số tải được kiểm soát. Ví dụ, máy chủ có thể dùng một bảng băm để đếm số lần xuất hiện của các tham số yêu cầu hoặc ánh xạ tên trường sang giá trị.

Nhưng bảng băm phải xử lý **va chạm (collision)**: hai khóa khác nhau có cùng mã băm hoặc được đưa vào cùng ngăn/ô. Va chạm là bình thường, không tự nó là lỗi. Nguy cơ xuất hiện khi một bên có thể cung cấp **rất nhiều khóa được lựa chọn có chủ đích**, khiến phần lớn chúng va chạm và làm mỗi thao tác tốn nhiều công sức hơn dự kiến.

Hiện tượng này được gọi là **tấn công gây va chạm băm (hash collision attack)** hoặc **hash flooding**. Trong trường hợp điển hình, mục tiêu là làm hệ thống tiêu tốn CPU, tăng độ trễ hoặc không phục vụ kịp những yêu cầu khác: một dạng **từ chối dịch vụ (denial of service, DoS)**.

Điểm mấu chốt của bài:

- **Hàm băm tất định công khai, dễ đoán** có thể cho người cung cấp dữ liệu cơ hội chọn nhiều khóa cùng vị trí.
- **Ngẫu nhiên hóa hàm băm** khiến việc chuẩn bị sẵn những tập khóa gây va chạm trở nên khó hơn nếu tham số ngẫu nhiên được giữ kín.
- **Ngẫu nhiên hóa không loại bỏ khả năng va chạm và không biến mọi thao tác thành `O(1)` trong trường hợp xấu nhất.** Cần cả kiểm soát tài nguyên và cách triển khai có hành vi suy giảm hợp lý.

Mọi ví dụ trong bài chỉ là **mô phỏng cục bộ trên dữ liệu nhỏ**, để hiểu nguyên lý và biện pháp phòng vệ, không phải quy trình nhắm vào một dịch vụ thật.

## 2. Vì sao hai khóa khác nhau vẫn vào cùng ngăn?

Giả sử bảng có `m>0` ngăn. Với mã băm `h(k)`, cách lấy vị trí đơn giản là:

\[
i(k)=h(k)\bmod m.
\]

Có hai loại trùng cần phân biệt:

1. **Va chạm mã băm:** `h(a)=h(b)` dù `a\ne b`.
2. **Va chạm vị trí:** `i(a)=i(b)` dù mã băm có thể khác nhau, do phép đưa mã băm về phạm vi `0,\ldots,m-1`.

Cả hai đều dẫn đến việc các khóa phải chia sẻ một ngăn nếu dùng **nối chuỗi (separate chaining)**, hoặc cạnh tranh ô lưu nếu dùng **địa chỉ mở (open addressing)**.

Ví dụ được thiết kế để nhìn thấy va chạm, với khóa nguyên và `m=8`:

```text
i(k) = k mod 8

Khóa:   0    8   16   24   32   40   48   56
Ngăn:   0    0    0    0    0    0    0    0
```

Những khóa này **khác nhau hoàn toàn** nhưng đều được đưa tới ngăn 0. Đối với hệ thống nhận khóa từ bên ngoài, nếu quy tắc định vị quá dễ đoán, những đầu vào có cấu trúc có thể làm xuất hiện cụm va chạm lớn.

Đây chỉ là ví dụ về **hàm chọn ngăn đơn giản**, không phải nhận định rằng mọi hàm băm khóa nguyên đều lấy trực tiếp `k mod 8`. Nhiều thư viện có các bước trộn bit, ngẫu nhiên hóa hoặc chính sách xử lý va chạm riêng.

## 3. Va chạm làm tăng chi phí theo cách nào?

### 3.1. Bảng băm dùng nối chuỗi

Với **separate chaining**, mỗi ngăn giữ một danh sách các cặp khóa–giá trị. Nếu `n` khóa dồn vào cùng một ngăn, thao tác tìm khóa nằm cuối danh sách hoặc tìm khóa không có sẽ phải kiểm tra tới `n` phần tử:

\[
T_{\text{tìm, xấu nhất}}=\Theta(n)
\]

trong mô hình tính hash và so sánh mỗi khóa có chi phí hằng số.

Nếu một `map` chèn nhiều khóa mới và **kiểm tra trùng khóa** bằng cách duyệt chuỗi trước khi thêm, số lần so sánh trong `n` lần chèn liên tiếp vào cùng ngăn có thể là:

\[
0+1+2+\cdots+(n-1)
=\frac{n(n-1)}2
=\Theta(n^2).
\]

Đây là lý do một nhóm đầu vào gây va chạm có thể làm **tổng thời gian xử lý tăng theo bậc hai**, dù mỗi thao tác trên dữ liệu phân bố bình thường vốn thường rất nhanh.

### 3.2. Bảng băm dùng địa chỉ mở

Với **open addressing**, mỗi ô giữ tối đa một bản ghi đang hoạt động. Khi nhiều khóa có cùng vị trí ban đầu, các quy tắc như **linear probing** có thể tạo cụm ô liên tiếp dài:

```text
Các khóa bắt đầu ở ô 3:

Chỉ số:  0  1  2  3  4  5  6  7
Trạng: [ ][ ][ ][A][B][C][D][ ]
                 ^-----------^
               cụm liên tiếp
```

Tìm một khóa chưa có nhưng cũng bắt đầu từ ô 3 có thể cần kiểm tra cả cụm trước khi gặp ô trống. Trong trường hợp xấu, một thao tác có thể tốn `O(m)` lần thăm dò với `m` là số ô.

Quadratic probing hay double hashing có thể giảm một số kiểu kết cụm, nhưng **không bảo đảm miễn nhiễm** trước những dãy va chạm bất lợi. Cần chọn tham số để dãy thăm dò đủ vị trí hợp lệ và quản lý cả những ô `DELETED` do xóa.

### 3.3. Tại sao mở rộng bảng chưa đủ?

Tăng `m` thường làm giảm **hệ số tải `\alpha=n/m`**, nhưng không bắt buộc phá vỡ một tập va chạm được lựa chọn bất lợi. Chẳng hạn, với những khóa đều chia hết cho `16`, việc đổi `m=8` thành `m=16` mà vẫn dùng `i(k)=k\bmod m` không làm chúng phân tán.

Vì vậy, chính sách resize tốt là cần thiết để kiểm soát tải, nhưng **không thay thế yêu cầu thiết kế hàm băm đủ khó bị điều khiển và cách xử lý va chạm bền vững**.

## 4. Tại sao phân tích kỳ vọng O(1) không phải lời bảo đảm chống tấn công?

Ta thường viết:

\[
\mathbb{E}[T_{\text{get}}]=O(1),
\]

nhưng ký hiệu `\mathbb{E}` có nghĩa chi phí được **lấy trung bình theo một mô hình xác suất**: ví dụ, dữ liệu đầu vào phân bố phù hợp, hoặc hàm băm được chọn ngẫu nhiên từ một họ hàm băm.

Nếu đầu vào do một bên **chủ động lựa chọn** và có thể khai thác cấu trúc của hàm băm cố định, mô hình “khóa phân bố đều” có thể không còn đúng. Không thể lấy kết luận kỳ vọng trên một mô hình thuận lợi rồi suy ra hiệu năng cho mọi đầu vào có chủ đích.

| Loại phát biểu | Ý nghĩa | Điều không được suy ra |
| --- | --- | --- |
| **Kỳ vọng `O(1)`** | Trung bình theo giả định xác suất xác định | Mọi khóa, mọi lần tìm đều `O(1)` |
| **Khấu hao `O(1)`** | Tổng chi phí resize được trải trên nhiều lần cập nhật | Va chạm nặng tự biến mất |
| **Trường hợp xấu `O(n)`** khi nối chuỗi | Có thể phải duyệt nhiều bản ghi trong một ngăn | Luôn luôn tốn `O(n)` |
| **Trường hợp xấu `O(m)`** khi địa chỉ mở | Có thể phải thử nhiều ô | Ngẫu nhiên hóa sẽ loại bỏ tuyệt đối trường hợp này |

Đây cũng là sự phân biệt giữa **thời gian kỳ vọng** và **bảo đảm thời gian xấu nhất**. Một hệ thống phục vụ yêu cầu bên ngoài phải quan tâm tới độ trễ cực đại, độ trễ đuôi (*tail latency*) và tài nguyên tổng thể, không chỉ mức trung bình khi thử nghiệm với dữ liệu ngẫu nhiên.

## 5. Ý tưởng ngẫu nhiên hóa hàm băm

Thay vì để mọi tiến trình dùng một quy tắc băm dễ đoán, chương trình có thể chọn **tham số ngẫu nhiên `s`** khi khởi tạo rồi dùng:

\[
h_s(k)=\operatorname{Hash}(k,s).
\]

Ở đây `s` thường được gọi là **seed**, **salt** hoặc **khóa bí mật của hàm băm** tùy thiết kế. Hai tiến trình với tham số khác nhau có thể đặt cùng một tập khóa vào những ngăn khác nhau.

**Lợi ích an toàn:** nếu người cung cấp đầu vào không biết `s`, họ khó chuẩn bị trước một tập khóa bảo đảm va chạm theo cùng một cách ở mọi lần chương trình chạy. Tập khóa khiến phiên bản này có nhiều va chạm có thể không còn hiệu quả với một tham số được chọn độc lập ở phiên bản khác.

**Ranh giới của bảo đảm:**

- Hệ số tải cao, va chạm ngẫu nhiên và trường hợp xấu vẫn có thể xuất hiện.
- Nếu tham số không bí mật hoặc có thể suy ra từ quan sát, lợi ích ngẫu nhiên hóa suy giảm.
- Một thuật toán trộn yếu có thể vẫn có những mẫu khóa va chạm bất kể seed.
- Nếu đối tượng có thể **chọn khóa thích nghi dựa trên thời gian phản hồi hoặc thông tin rò rỉ**, lập luận cho tập khóa cố định trước khi chọn seed không còn đủ.

Do đó, randomization là **một lớp bảo vệ**, không phải cam kết rằng mỗi truy cập đều có thời gian `O(1)`.

## 6. Họ hàm băm có tham số ngẫu nhiên: mô hình toán học nhỏ

Để thấy vai trò của tham số, xét họ hàm băm trên các khóa nguyên `k\in\{0,\ldots,p-1\}`, với `p` là số nguyên tố:

\[
g_{a,b}(k)=(ak+b)\bmod p,
\]

trong đó `a\in\{1,\ldots,p-1\}`, `b\in\{0,\ldots,p-1\}`. Chọn `a,b` ngẫu nhiên, sau đó đưa kết quả vào bảng `m\le p` ngăn:

\[
i_{a,b}(k)=g_{a,b}(k)\bmod m.
\]

Đối với **hai khóa cố định, phân biệt trong phạm vi `0` đến `p-1`**, hai mã `g_{a,b}(k)` là những giá trị khác nhau khi `a\ne0\bmod p`. Khi giảm về `m` ngăn, chúng vẫn có thể va chạm; việc chọn `a,b` ngẫu nhiên giúp tránh một mô hình ngăn cố định dễ dự đoán trước.

Với lựa chọn ngẫu nhiên đều của `a,b` như trên, xác suất hai khóa **cố định, khác nhau** nhận cùng ngăn xấp xỉ `1/m` khi `p` lớn so với `m`. Đây là một ý tưởng của **họ hàm băm phổ dụng (universal hashing)**: phân tích xác suất qua phép chọn hàm, không giả định khóa đầu vào phải ngẫu nhiên.

### Một ví dụ số có thể kiểm tra bằng tay

Chọn `p=101`, `m=8`, và **chỉ để minh họa** chọn `a=17`, `b=23`. Với tám khóa `0,8,16,24,32,40,48,56`:

| Khóa `k` | `k mod 8` không trộn | `(17k+23) mod 101` | Ngăn sau khi `mod 8` |
| ---: | ---: | ---: | ---: |
| 0 | 0 | 23 | 7 |
| 8 | 0 | 58 | 2 |
| 16 | 0 | 93 | 5 |
| 24 | 0 | 27 | 3 |
| 32 | 0 | 62 | 6 |
| 40 | 0 | 97 | 1 |
| 48 | 0 | 31 | 7 |
| 56 | 0 | 66 | 2 |

Cùng tập khóa, quy tắc `k mod 8` đưa cả tám vào ngăn 0; còn tham số minh họa `a=17,b=23` phân chúng ra sáu ngăn và chỉ tạo hai cặp va chạm. **Va chạm vẫn còn**, chỉ là không còn tập trung giống trước.

**Giới hạn rất quan trọng:** đây là ví dụ toán học trên **khóa nhỏ hơn `p`**, không phải một hàm băm nên triển khai trực tiếp để bảo vệ máy chủ. Nếu nhận khóa nguyên tùy ý, những khóa khác nhau nhưng đồng dư modulo `p` vẫn cho cùng `g_{a,b}` với *mọi* tham số. Trong thực tế, cần một phép trộn có khóa được thiết kế và đánh giá cho **toàn bộ miền đầu vào**.

## 7. Python: mô phỏng so sánh va chạm của hai cách băm

Ví dụ sau không gửi yêu cầu mạng và không chạm vào hệ thống bên ngoài. Nó chỉ mô phỏng **một bảng nối chuỗi** và đếm số lần so sánh khóa trong lúc thêm một tập tám khóa **đã biết là khác nhau**.

```python
import secrets


def dem_so_sanh_khi_chen(keys, index_of, so_ngan=8):
    ngan = [[] for _ in range(so_ngan)]
    so_so_sanh = 0
    for khoa in keys:
        i = index_of(khoa)
        for khoa_cu in ngan[i]:
            so_so_sanh += 1
            if khoa_cu == khoa:
                break
        else:
            ngan[i].append(khoa)
    return so_so_sanh, [len(chuoi) for chuoi in ngan]


keys = [0, 8, 16, 24, 32, 40, 48, 56]

# Quy tắc cố định đơn giản: cả tám khóa vào ngăn 0.
so_sanh_co_dinh, do_dai_co_dinh = dem_so_sanh_khi_chen(
    keys, lambda k: k % 8
)
print(so_sanh_co_dinh)  # 28 = 0 + 1 + ... + 7
print(do_dai_co_dinh)   # [8, 0, 0, 0, 0, 0, 0, 0]

# Tham số chọn sẵn CHỈ ĐỂ TÁI LẬP ví dụ trong bảng ở trên.
so_sanh_vi_du, do_dai_vi_du = dem_so_sanh_khi_chen(
    keys, lambda k: ((17 * k + 23) % 101) % 8
)
print(so_sanh_vi_du)  # 2: hai cặp khóa chung ngăn
print(do_dai_vi_du)   # [0, 1, 2, 1, 0, 1, 1, 2]


def tao_ham_ngau_nhien(p=101, so_ngan=8):
    # Ví dụ học thuật: chỉ nhận khóa nguyên 0 <= k < p.
    a = 1 + secrets.randbelow(p - 1)
    b = secrets.randbelow(p)

    def chi_so(k):
        if not (0 <= k < p):
            raise ValueError("Khóa ngoài miền minh họa")
        return ((a * k + b) % p) % so_ngan

    return chi_so


ham_ngau_nhien = tao_ham_ngau_nhien()
so_sanh_ngau_nhien, _ = dem_so_sanh_khi_chen(
    keys, ham_ngau_nhien
)
print(so_sanh_ngau_nhien)  # Thay đổi theo a, b; không cố định
```

Để tái lập kết quả minh họa, hàm ở giữa cố ý dùng `a=17,b=23` và **công khai tham số**. Trong thực tế, nếu mục tiêu là làm khó người lựa chọn đầu vào, tham số không nên bị công khai cùng một quy tắc dễ suy đoán.

Mô phỏng không đo thời gian CPU hay kiểm thử khả năng phòng thủ trước đối thủ thích nghi. Nó chứng minh điểm đơn giản hơn: **cùng một tập khóa có thể tạo số phép so sánh rất khác nhau dưới những hàm chọn ngăn khác nhau**.

## 8. Ngẫu nhiên hóa tốt cần đi kèm những điều kiện nào?

### 8.1. Hợp đồng hash và equality phải được giữ

Với mọi tham số `s`, nếu hai khóa bằng nhau theo định nghĩa của map thì:

\[
a=b\quad\Longrightarrow\quad h_s(a)=h_s(b).
\]

Các thuộc tính tạo **danh tính khóa** phải ổn định khi khóa đang được lưu. Thêm khóa theo seed này nhưng tìm theo seed khác, hoặc thay đổi khóa sau khi chèn, có thể khiến bản ghi không còn tìm thấy.

### 8.2. Chọn seed đủ khó đoán

Nếu dùng seed cho mục tiêu an toàn, nó phải được tạo từ nguồn ngẫu nhiên thích hợp và được quản lý như một giá trị nhạy cảm khi thiết kế yêu cầu tính bí mật. **Không** nên dựa trên thời gian hệ thống dễ đoán hoặc hard-code một seed rồi xem đó là biện pháp chống đầu vào có chủ đích.

Đối với chuỗi hoặc byte đầu vào không tin cậy, các runtime có thể dùng **hàm băm có khóa** được thiết kế riêng cho bảng băm. Một ví dụ khái niệm là họ thuật toán kiểu **SipHash**; không thể thay bằng phép cộng đơn giản với một seed rồi tự suy ra mức độ chống va chạm tương đương.

### 8.3. Seed không được đổi tùy tiện khi bảng còn dữ liệu

Vị trí bản ghi phụ thuộc seed. Nếu đổi seed khi bảng đang chứa khóa, phải **rehash các bản ghi đang hoạt động** theo seed mới, hoặc triển khai một cơ chế chuyển đổi có kiểm soát.

```text
Khi chèn:   seed S1 -> ngăn 2 -> lưu khóa K
Khi tìm:    seed S2 -> ngăn 5 -> không thấy K

Đổi seed đúng: tạo bảng mới, tái chèn K với S2, rồi sử dụng S2.
```

Seed khác giữa các tiến trình cũng có thể khiến mã băm của cùng một chuỗi khác nhau. Do đó **không dùng mã `hash()` nội bộ của runtime như ID lâu dài lưu trên đĩa hoặc gửi qua hệ thống khác** nếu không có một giao thức định danh ổn định.

### 8.4. Phân biệt đối thủ cố định và đối thủ thích nghi

Nhiều bảo đảm xác suất của **universal hashing** xét một tập khóa được chọn **trước khi** tham số ngẫu nhiên được chọn, hoặc xét tập khóa độc lập với tham số. Nếu một bên có thể thử liên tục, đo độ trễ, quan sát thứ tự ngăn hoặc khai thác thông tin rò rỉ, họ có thể thích nghi với kết quả quan sát được.

Khi đó, cần phân tích riêng mô hình đe dọa, khả năng bí mật của seed và tính an toàn của thuật toán băm có khóa. Không thể kết luận “ngẫu nhiên hóa là đủ” chỉ từ một công thức kỳ vọng trong mô hình đầu vào cố định.

## 9. Các lớp phòng vệ bổ sung

Không có một biện pháp duy nhất giải quyết mọi nguy cơ DoS. Với các bảng băm nhận khóa từ nguồn không tin cậy, nên kết hợp:

| Biện pháp | Tác dụng | Hạn chế hoặc đánh đổi |
| --- | --- | --- |
| **Hàm băm có khóa/seed phù hợp** | Làm khó chuẩn bị trước tập va chạm dựa vào quy tắc công khai | Cần bảo vệ seed; không xóa được trường hợp xấu |
| **Kiểm soát hệ số tải, resize** | Giữ số ngăn/ô phù hợp với số khóa | Không chữa được mẫu va chạm có chủ đích với hàm băm yếu |
| **Xử lý va chạm bền vững** | Ví dụ, dùng cấu trúc có cận xấu nhất tốt hơn cho các ngăn quá dài khi triển khai cho phép | Tốn bộ nhớ, chi phí hoặc điều kiện so sánh bổ sung |
| **Giới hạn kích thước, số khóa mỗi yêu cầu** | Giới hạn lượng công việc một yêu cầu có thể gây ra | Cần chọn ngưỡng theo nghiệp vụ |
| **Giới hạn tốc độ và ngân sách xử lý** | Giảm khả năng một nguồn chiếm toàn bộ tài nguyên | Có thể ảnh hưởng tải hợp lệ nếu cấu hình không phù hợp |
| **Giám sát độ dài chuỗi, số lần thăm dò và độ trễ đuôi** | Phát hiện sớm tình trạng hiệu năng bất thường | Chỉ quan sát không tự khắc phục |

Một số cách triển khai có thể chuyển ngăn chứa nhiều phần tử từ danh sách sang **cây cân bằng** để cải thiện cận thời gian theo số phần tử, nhưng cần có quy tắc so sánh/định thứ tự phù hợp và thêm chi phí duy trì cấu trúc. Không nên khẳng định mọi thư viện bảng băm đều có cơ chế này.

**Băm mật mã** và **băm cho bảng tra cứu** cũng có mục tiêu khác nhau. Một digest mật mã không có khóa, dù khó tìm va chạm theo khả năng tính toán hiện tại, vẫn không thay thế toàn bộ cơ chế quản lý tài nguyên và có thể đắt hơn khi phải tính cho nhiều chuỗi dài. Khi cần chống người chủ động lựa chọn khóa trong một mô hình bảo mật cụ thể, phải xem xét tính chất **có khóa** và thiết kế của toàn hệ thống, không chỉ tên thuật toán.

## 10. Tình huống thiết kế: bộ đếm tham số trong một API

Giả sử một API nhận một danh sách tham số văn bản và lưu tần suất trong map:

```text
POST /submit
Các tham số dạng (tên, giá trị)
       |
       v
  Kiểm tra số lượng và độ dài
       |
       v
  Tạo khóa chuẩn hóa nhất quán
       |
       v
  Map đếm tần suất các tên
       |
       v
  Xử lý tiếp yêu cầu
```

Nếu số tham số không bị giới hạn, chương trình có thể phải thực hiện nhiều phép băm và cấp phát ngay cả khi **không xảy ra va chạm**. Nếu hàm chọn ngăn dễ đoán, một nhóm tên trường được lựa chọn có chủ đích còn có thể tăng mạnh số lần so sánh. Hai nguồn chi phí này cần được kiểm soát **độc lập**.

Một thiết kế phòng vệ nên xác định **ngân sách đầu vào** (số trường, độ dài tên, tổng byte), dùng cấu trúc bảng băm có xử lý va chạm phù hợp với đầu vào không tin cậy, đồng thời theo dõi các chỉ số như số phép so sánh trên một thao tác và thời gian xử lý theo phân vị.

Nếu phát hiện độ dài chuỗi hoặc số lần thăm dò vượt mức bất thường, hệ thống có thể áp dụng **giới hạn xử lý, dựng lại bảng theo chính sách, thay chiến lược lưu trữ hoặc từ chối yêu cầu quá lớn**. Biện pháp cụ thể phụ thuộc mức độ tin cậy của đầu vào, khối lượng công việc và yêu cầu dịch vụ.

## 11. Những ngộ nhận dễ mắc

1. **“Tìm kiếm bảng băm luôn O(1).”** Sai: đó thường là kỳ vọng có điều kiện; trường hợp xấu nhất vẫn có thể tuyến tính.
2. **“Chỉ cần tăng gấp đôi dung lượng là chống được hash flooding.”** Sai: nếu mẫu va chạm vẫn tồn tại, thêm ngăn không đủ.
3. **“Hash khác nhau chắc chắn vào các ngăn khác nhau.”** Sai: hai mã băm có thể trùng chỉ số sau `mod m`.
4. **“Hai khóa có cùng hash là một khóa.”** Sai: cần so sánh khóa thực sự; va chạm là hợp lệ.
5. **“Đổi seed là không mất bản ghi.”** Sai nếu không tái chèn theo quy tắc mới hoặc có cơ chế chuyển đổi đúng.
6. **“Thêm một seed bí mật vào hàm cộng đơn giản là đủ an toàn.”** Sai: tính chống đầu vào thích nghi phụ thuộc thiết kế hàm trộn có khóa và việc bảo vệ seed.
7. **“Hàm băm ngẫu nhiên không bao giờ va chạm.”** Sai: mã băm/chỉ số ngăn là hữu hạn và va chạm vẫn có thể xảy ra.
8. **“Kết quả từ benchmark khóa ngẫu nhiên chứng minh hệ thống chống được DoS.”** Sai: cần đánh giá các đầu vào có cấu trúc, giới hạn tài nguyên và mô hình đe dọa.

## 12. Tự kiểm tra

**Câu 1.** Bảng nối chuỗi có 8 ngăn, dùng `i(k)=k mod 8`. Thêm các khóa `0,8,16,24`. Chúng vào ngăn nào? Nếu map phải kiểm tra trùng khóa, có bao nhiêu lần so sánh trong bốn lần thêm?

**Đáp án:** Cả bốn vào ngăn 0. Với chuỗi ban đầu rỗng, số so sánh là `0+1+2+3=6`, nếu mỗi lần thêm duyệt các khóa trong ngăn để kiểm tra trùng trước khi nối bản ghi mới.

**Câu 2.** Vì sao tăng dung lượng từ 8 lên 16 không nhất thiết phá vỡ nhóm va chạm trong ví dụ nếu các khóa đều chia hết cho 16?

**Đáp án:** Vì mọi khóa vẫn có `k mod 16=0`. Resize giảm hệ số tải chung nhưng không bảo đảm sửa phân bố bất lợi do hàm chọn ngăn.

**Câu 3.** Khi nói tra cứu có chi phí kỳ vọng `O(1)`, tại sao phải nêu nguồn ngẫu nhiên hoặc giả định phân bố đầu vào?

**Đáp án:** Kỳ vọng lấy trung bình theo một mô hình. Một bên chủ động chọn đầu vào có thể làm giả định khóa phân bố đều không còn đúng, nên không thể suy ra thời gian hằng số cho mọi yêu cầu.

**Câu 4.** Seed ngẫu nhiên giúp ích ở điểm nào? Có thể bảo đảm `O(1)` tuyệt đối không?

**Đáp án:** Seed khó đoán khiến tập khóa va chạm được chuẩn bị sẵn theo quy tắc cố định có thể không còn hữu hiệu. Nó không xóa va chạm hay bảo đảm thời gian xấu nhất `O(1)`.

**Câu 5.** Một bảng đã có dữ liệu, chương trình đổi seed dùng trong hàm băm. Cần làm gì để việc tìm tiếp tục đúng?

**Đáp án:** Phải **rehash** những bản ghi đang hoạt động theo seed mới hoặc dùng cơ chế chuyển đổi tương đương có kiểm soát; không thể chỉ thay tham số rồi tìm trên bố trí cũ.

**Câu 6.** Vì sao một lớp bảo vệ như giới hạn số khóa và độ dài chuỗi vẫn cần thiết khi đã dùng hàm băm có khóa?

**Đáp án:** Vì dữ liệu lớn vẫn tốn thời gian đọc, băm, so sánh và bộ nhớ ngay cả khi không có va chạm; ngoài ra còn có những kiểu DoS khác. Giới hạn tài nguyên giảm tác động của một yêu cầu bất thường.

**Câu 7.** Mô hình universal hashing cho tập khóa cố định trước seed có đủ để kết luận an toàn trước bên có thể quan sát thời gian phản hồi rồi chọn khóa tiếp theo không?

**Đáp án:** Chưa đủ. Bên thích nghi có thể học từ thông tin quan sát được; cần xem xét mô hình đe dọa, cơ chế giữ kín seed, đặc tính của hàm băm có khóa và các lớp giới hạn tài nguyên.

**Ghi nhớ:** **Hash flooding** lợi dụng tình trạng nhiều khóa va chạm để làm một bảng băm xử lý chậm bất thường: ở nối chuỗi có thể gây `O(n)` cho một thao tác và `O(n^2)` cho một chuỗi chèn; ở địa chỉ mở có thể tạo những dãy thăm dò dài. **Ngẫu nhiên hóa hàm băm bằng tham số khó đoán** giảm khả năng chuẩn bị trước tập va chạm, nhưng không loại bỏ hoàn toàn trường hợp xấu nhất. Để thiết kế hệ thống bền vững trước đầu vào không tin cậy, cần kết hợp hàm băm phù hợp, quản lý tải, cơ chế xử lý va chạm, giới hạn tài nguyên và giám sát hiệu năng.
