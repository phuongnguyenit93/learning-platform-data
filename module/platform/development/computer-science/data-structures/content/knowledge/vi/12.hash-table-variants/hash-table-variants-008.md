# Băm tuyến tính và tăng số nhóm khóa từng bước

Một bảng băm có thể hoạt động nhanh khi các khóa được phân bố đều vào những **nhóm khóa** (*bucket*). Tuy nhiên, khi dữ liệu tăng lên, các bucket đầy dần và có thể phải dùng vùng tràn (*overflow*). Nếu mỗi lần thiếu chỗ đều nhân đôi toàn bộ bảng rồi phân phối lại mọi khóa, chi phí cập nhật có thể lớn, đặc biệt khi một bucket tương ứng với một **trang lưu trữ** trên đĩa.

**Băm tuyến tính** (*linear hashing*) là một kỹ thuật **băm động** (*dynamic hashing*) cho phép tăng số bucket **từng bước, thường mỗi lần thêm đúng một bucket chính**. Nó dùng một **con trỏ tách** (*split pointer*) đi tuần tự qua các bucket cũ, thay vì phải mở rộng toàn bộ bảng trong một lần.

Bài học thuộc chương **Biến thể bảng băm** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu là hiểu bất biến định tuyến khóa, cách tách và phân phối lại bucket, quan hệ giữa tải và trang tràn, cùng độ phức tạp thời gian/bộ nhớ để lựa chọn cấu trúc phù hợp với bài toán.

> **Phân biệt ngay từ đầu:** *Linear hashing* (băm tuyến tính) **khác** *linear probing* (thăm dò tuyến tính). Linear probing tìm ô tiếp theo trong một mảng khi gặp va chạm; linear hashing **tăng số bucket theo một thứ tự tách tuần tự**, có thể sử dụng các trang tràn và thường được trình bày trong bối cảnh lưu trữ theo trang.

## 1. Tư duy cốt lõi: tăng từng bucket thay vì nhân đôi đồng loạt

Xét một tập hợp hoặc bảng ánh xạ khóa–giá trị. Mỗi bucket chính chứa tối đa \(B\) bản ghi trong một trang. Nếu số khóa vượt sức chứa của bucket, các bản ghi dư có thể tạm nằm trong **trang tràn**, tạo thành một chuỗi tràn.

Linear hashing không đợi tới khi tất cả các bucket cũ đều đầy mới tăng kích thước. Nó duy trì một thứ tự tách: **bucket 0, rồi bucket 1, rồi bucket 2, ...**. Mỗi lần tách một bucket:

1. Cấp phát **một bucket chính mới** ở cuối dãy bucket hiện có.
2. Dựa vào **một bit băm bổ sung** (hoặc một mức hàm băm cao hơn) để chia khóa của bucket đang tách thành hai nhóm.
3. Di chuyển **chỉ các bản ghi thuộc bucket đó** sang bucket cũ hoặc mới.
4. Tiến con trỏ tách sang bucket tiếp theo.

Khi đã đi hết một vòng các bucket thuộc mức hiện tại, thuật toán chuyển sang một **vòng tách mới** với số bucket cơ sở gấp đôi.

~~~text
Vòng ban đầu:         [0] [1]
Tách bucket 0:        [0] [1] [2]
Tách bucket 1:        [0] [1] [2] [3]
Vòng tiếp theo:       [0] [1] [2] [3] ...
Tách bucket 0:        [0] [1] [2] [3] [4]
~~~

Mỗi lần tách tạo **một bucket**, không nhất thiết phải đụng tới khóa của các bucket còn lại. Chính đó là ưu điểm về tăng trưởng từng phần (*incremental growth*).

## 2. Trạng thái: mức băm, con trỏ tách và số bucket

Đặt:

- \(m_0\ge1\): số bucket **cơ sở ban đầu**, đã chọn cố định.
- \(i\ge0\): **mức** hoặc **vòng tách** (*level*).
- \(M=m_0\,2^i\): số bucket cơ sở của vòng hiện hành.
- \(s\): **con trỏ tách**, chỉ bucket tiếp theo cần được tách, với \(0\le s<M\).
- \(N\): tổng số bucket chính hiện đang có.

Quan hệ bất biến là:

\[
\boxed{N=M+s=m_0\,2^i+s,\quad 0\le s<M.}
\]

Bucket chính có chỉ số liên tiếp từ \(0\) đến \(N-1\). Vì \(s<M\), tại mọi thời điểm \(M\le N<2M\). Một trạng thái **giữa vòng** có một phần bucket đã được tách và một phần vẫn đang chờ.

Giả sử hàm băm cơ sở \(h(k)\) trả về số nguyên không âm phân bố tốt. Tại mức \(i\), định nghĩa:

\[
\boxed{h_i(k)=h(k)\bmod M,\qquad
h_{i+1}(k)=h(k)\bmod(2M).}
\]

Đây là **hai mức của cùng một giá trị băm**, không bắt buộc là hai phép băm độc lập. Nếu \(m_0\) là lũy thừa của 2, ta có thể hiểu đây là việc lấy thêm một bit thấp từ kết quả băm ở mỗi vòng.

### Quy tắc chọn bucket để tra cứu

Trước tiên tính \(b=h_i(k)\). Nếu \(b\) đã nằm **trước con trỏ tách** (\(b<s\)), bucket gốc đó đã được tách, nên phải tính lại chỉ số theo mức mới \(h_{i+1}(k)\). Nếu chưa bị tách, dùng \(b\).

\[
\boxed{
\operatorname{bucket}(k)=
\begin{cases}
h_{i+1}(k),&\text{nếu }h_i(k)<s,\\
h_i(k),&\text{nếu }h_i(k)\ge s.
\end{cases}}
\]

Giá trị của \(h_{i+1}(k)\) trong nhánh đầu **chỉ có thể là \(b\) hoặc \(b+M\)**, nên không bao giờ vượt \(N-1\) với \(b<s\).

~~~text
Tính b = h_i(k)
        |
        v
   b < split ?
    /       \
   Có       Không
   |          |
Chọn        Chọn
h_(i+1)     h_i
   \          /
    \        /
     Bucket được chọn
~~~

Quy tắc này là **bất biến định tuyến**: sau mọi lần tách, mỗi khóa đã lưu phải nằm đúng bucket mà hàm chọn bucket hiện tại xác định.

## 3. Ví dụ định tuyến ở trạng thái giữa vòng

Giả sử \(m_0=2\), \(i=0\), \(M=2\), \(s=1\). Khi đó có:

\[
N=2+1=3\text{ bucket: }0,1,2.
\]

Bucket 0 đã được tách thành hai nhóm 0 và 2. Bucket 1 chưa tách. Giả sử \(h(k)=k\) để dễ tính tay:

| Khóa \(k\) | \(h_0(k)=k\bmod2\) | Đã tách? | Chỉ số cuối cùng |
| ---: | ---: | --- | ---: |
| 0 | 0 | Có, vì \(0<s\) | \(h_1(0)=0\bmod4=0\) |
| 2 | 0 | Có | \(h_1(2)=2\bmod4=2\) |
| 4 | 0 | Có | \(h_1(4)=4\bmod4=0\) |
| 1 | 1 | Chưa, vì \(1\ge s\) | 1 |
| 3 | 1 | Chưa | 1 |
| 5 | 1 | Chưa | 1 |

Từ bảng trên, ta thấy dù bucket 2 đã được cấp phát, **các khóa có \(h_0(k)=1\) vẫn ở bucket 1** cho đến khi chính bucket 1 đến lượt tách.

**Sai lầm quan trọng cần tránh:** Không được lập chỉ số bằng công thức \(h(k)\bmod N\) khi \(N=M+s\). Ví dụ với \(N=3\), khóa 2 sẽ bị đưa tới bucket 2 nếu tính \(2\bmod3\) (tình cờ đúng), nhưng khóa 3 bị đưa tới bucket 0 dù thực tế phải nằm ở bucket 1. Linear hashing sử dụng **hai mức modulo \(M\) và \(2M\)** cùng con trỏ \(s\), không phải modulo số bucket hiện thời.

## 4. Tách bucket một bước diễn ra thế nào?

Giả sử trạng thái hiện tại có \(M=m_0\,2^i\), \(s<M\) và \(N=M+s\). Thao tác **SPLIT** luôn tách **bucket \(s\)**.

1. Cấp một bucket chính mới tại chỉ số **\(M+s\)**, chính là vị trí \(N\) ở cuối danh sách bucket.
2. Lấy toàn bộ bản ghi trong bucket \(s\), **kể cả các trang tràn** nếu có.
3. Với mỗi khóa \(k\) đang thuộc bucket \(s\), tính \(h_{i+1}(k)=h(k)\bmod(2M)\):
   - Nếu kết quả là \(s\), giữ khóa ở bucket cũ.
   - Nếu kết quả là \(s+M\), chuyển khóa sang bucket mới.
4. Cập nhật con trỏ **\(s\leftarrow s+1\)**.
5. Nếu \(s=M\), nghĩa là vòng tách đã hoàn tất; đặt **\(i\leftarrow i+1\)** và **\(s\leftarrow0\)**. Mới lúc này \(M\) của mức tiếp theo trở thành \(2M\).

~~~mermaid
flowchart TD
    A["Yêu cầu tăng một bucket"] --> B["M = m0 * 2^i, bucket cần tách là s"]
    B --> C["Cấp bucket mới tại chỉ số M+s"]
    C --> D["Đọc các bản ghi bucket s và trang tràn"]
    D --> E["Phân phối lại theo h_(i+1) vào s hoặc M+s"]
    E --> F["Tăng con trỏ s thêm 1"]
    F --> G{"s bằng M?"}
    G -->|Không| H["Giữ nguyên i, kết thúc"]
    G -->|Có| I["Tăng i và đặt s = 0, bắt đầu vòng mới"]
~~~

Điểm đáng nhớ: **bucket được tách là bucket mà con trỏ \(s\) đang chỉ tới**, không bắt buộc là bucket vừa phát sinh va chạm hoặc trang tràn. Đây là đặc tính của **linear hashing theo thứ tự tách tuần tự**.

### Vì sao định tuyến vẫn đúng sau khi tách?

Trước khi tách, mọi khóa có \(h_i(k)=s\) được đưa vào bucket \(s\). Sau khi tách, giá trị modulo \(2M\) của chúng là **\(s\)** hoặc **\(s+M\)**. Ta chỉ cần phân phối lại chính nhóm khóa đó.

Những bucket có chỉ số **nhỏ hơn \(s\)** đã tách từ trước nên tiếp tục dùng mức \(i+1\). Những bucket có chỉ số **lớn hơn \(s\)** vẫn thuộc mức \(i\) và không bị thay đổi.

Khi \(s\) chạy hết \(M\) bucket, **mọi bucket cơ sở đều đã tách**. Lúc đó tất cả khóa đang tuân theo \(h_{i+1}\), nên có thể đặt \(i\leftarrow i+1\), \(s\leftarrow0\) mà **không cần phân phối lại toàn bộ bảng lần nữa**.

## 5. Khi nào cần tách? Hệ số tải và trang tràn

Trong một mô hình lưu trữ theo trang, mỗi bucket chính có thể chứa \(B\) bản ghi. Khi có \(n\) khóa, định nghĩa **hệ số tải dựa trên dung lượng bucket chính**:

\[
\boxed{\alpha=\frac{n}{B\,N}.}
\]

Nếu một bucket chứa hơn \(B\) bản ghi, các bản ghi dư phải được chứa trong **trang tràn**, hoặc theo cơ chế phụ khác. Do đó \(\alpha\) có thể **lớn hơn 1 trong thời gian ngắn**, dù tổng số bucket chính còn nhiều trang không đầy.

Có hai kiểu điều kiện tách thường gặp:

- **Tách có kiểm soát theo tải** (*controlled splitting*): khi \(\alpha\) vượt một ngưỡng đã chọn, gọi SPLIT một hoặc nhiều lần cho đến khi tải trở lại mức yêu cầu.
- **Tách theo sự kiện tràn** (*uncontrolled splitting*): khi một thao tác chèn làm phát sinh trang tràn, thực hiện một lần tách theo con trỏ. Lượt tách **vẫn tuân theo \(s\)**, không nhất thiết tách bucket bị tràn.

Trong cả hai cách, **thứ tự chọn bucket để tách** và **điều kiện kích hoạt tách** là hai vấn đề riêng. Có thể chọn ngưỡng tải thấp để giảm trang tràn, đổi lại nhiều bucket chính hơn.

### Vì sao vẫn có trang tràn?

Tách diễn ra theo **thứ tự tuần tự**, nên một bucket đang chật có thể phải đợi qua các lượt tách bucket khác. Trong lúc đó, các khóa mới thuộc cùng nhóm vẫn phải được lưu ở đâu đó. Các trang tràn duy trì tính đúng đắn nhưng có thể làm tăng số lần đọc đĩa khi tìm kiếm trong bucket đó.

Ngược lại, việc tách một bucket **không bị tràn** vẫn có thể cần thiết để con trỏ tiến qua vòng hiện tại. Không có bảo đảm rằng bucket mới luôn nhận được khóa: nếu giá trị băm của các khóa đều ở cùng nửa, bucket được cấp mới có thể tạm thời rỗng.

## 6. Ví dụ xuyên suốt: mở rộng từ hai lên bốn bucket

Ta dùng cấu hình đơn giản:

- \(m_0=2\) bucket ban đầu, chỉ số 0 và 1.
- Dung lượng bucket chính **\(B=2\)** bản ghi.
- Hàm băm minh họa \(h(k)=k\) với khóa nguyên không âm.
- Kích hoạt tách khi tải \(\alpha>0{,}8\); nếu cần có thể tách nhiều lượt cho đến khi \(\alpha\le0{,}8\).
- Có trang tràn, nghĩa là bucket vẫn có thể tạm chứa hơn 2 bản ghi.

Chọn \(h(k)=k\) để đọc được phép modulo bằng mắt. Một ứng dụng thực tế cần hàm băm phân bố tốt và có đủ bit.

### Giai đoạn A — Chèn 0, 1, 3

Ban đầu \(i=0\), \(M=2\), \(s=0\), \(N=2\); sử dụng \(h_0(k)=k\bmod2\).

| Bucket chính | Bản ghi |
| ---: | --- |
| 0 | [0] |
| 1 | [1, 3] |

Hiện có \(n=3\) khóa, nên \(\alpha=3/(2\cdot2)=0{,}75\). Vì \(\alpha\le0{,}8\), chưa tách.

### Giai đoạn B — Chèn 5, rồi tách bucket 0

Khóa 5 có \(h_0(5)=1\), nên đi vào **bucket 1** đang đầy. Tạm lưu 5 ở **trang tràn** của bucket 1. Khi ấy:

\[
n=4,\qquad \alpha=\frac{4}{2\cdot2}=1>0{,}8.
\]

Thao tác tách được kích hoạt, **nhưng con trỏ \(s=0\)**: phải tách **bucket 0**, không phải bucket 1 đang bị tràn.

- Cấp bucket mới \(M+s=2+0=2\).
- Bucket 0 đang chứa khóa 0. Xét theo mức mới \(h_1(0)=0\bmod4=0\), nên khóa 0 vẫn ở bucket 0.
- Bucket 2 mới **chưa có khóa**; đây là một kết quả hoàn toàn hợp lệ.
- Tiến \(s\) thành 1, vẫn giữ \(i=0\), \(M=2\).

| Bucket | Bản ghi hiện tại | Ghi chú |
| ---: | --- | --- |
| 0 | [0] | Đã tách, local routing theo \(h_1\) |
| 1 | [1, 3] + tràn [5] | Chưa đến lượt tách, vẫn theo \(h_0\) |
| 2 | [] | Bucket mới tạo |

Số bucket chính giờ là \(N=M+s=2+1=3\). Tải mới:

\[
\alpha=\frac{4}{2\cdot3}=\frac23\approx0{,}667.
\]

Con trỏ \(s=1\) cho biết **bucket 0 đã được tách; bucket 1 đang chờ**. Điều này giải thích vì sao linear hashing có thể **còn trang tràn dù vừa tạo thêm một bucket rỗng**.

### Giai đoạn C — Chèn 7 và tách bucket 1

Sau bước trước, với \(i=0,s=1\), khóa 7 có \(h_0(7)=1\ge s\), nên vẫn đi vào bucket 1. Bucket 1 tạm chứa [1,3] và trang tràn [5,7].

Khi ấy \(n=5\), \(N=3\), \(\alpha=5/(2\cdot3)\approx0{,}833>0{,}8\), nên kích hoạt tách tiếp.

Lần này \(s=1\): tách bucket 1 và cấp bucket mới \(M+s=2+1=3\). Xem mọi khóa của bucket 1 qua \(h_1(k)=k\bmod4\):

| Khóa | \(k\bmod4\) | Bucket sau tách |
| ---: | ---: | ---: |
| 1 | 1 | 1 |
| 3 | 3 | 3 |
| 5 | 1 | 1 |
| 7 | 3 | 3 |

Kết quả:

| Bucket | Bản ghi |
| ---: | --- |
| 0 | [0] |
| 1 | [1, 5] |
| 2 | [] |
| 3 | [3, 7] |

Sau khi tách, \(s\) tăng từ 1 lên 2, **bằng \(M=2\)**. Vòng tách hoàn tất; cập nhật \(i=1\), \(M=m_0\,2^i=4\), \(s=0\). Tổng số bucket là:

\[
N=4+0=4,\qquad \alpha=\frac{5}{2\cdot4}=0{,}625.
\]

~~~text
Sau chèn 0, 1, 3:
  i=0, s=0, N=2
  0:[0]        1:[1,3]

Chèn 5, tách bucket 0:
  i=0, s=1, N=3
  0:[0]        1:[1,3 | tràn 5]   2:[]

Chèn 7, tách bucket 1:
  i=1, s=0, N=4
  0:[0]        1:[1,5]            2:[]    3:[3,7]
~~~

Chỉ sau **hai lần tách một bucket mỗi lần**, số bucket chính tăng từ 2 lên 4. Không cần lấy các khóa ở mọi bucket để băm lại trong một thao tác nhân đôi duy nhất.

### Kiểm tra truy vấn trước và sau tách

**Ngay sau tách bucket 0:** \(i=0,s=1\). Tìm khóa 5: \(h_0(5)=1\ge s\), nên đọc bucket 1 và cả trang tràn, tìm thấy 5. Tìm khóa 2: \(h_0(2)=0<s\), dùng \(h_1(2)=2\), nên đọc bucket 2 rỗng và trả về không tìm thấy.

**Sau khi kết thúc vòng:** \(i=1,s=0,M=4\). Tìm khóa 7: \(h_1(7)=3\), nên đọc bucket 3, thấy 7. Tìm khóa 5: \(h_1(5)=1\), nên đọc bucket 1, thấy 5.

Ví dụ cho thấy **quy tắc chọn bucket phải thay đổi theo \(i,s\)**. Nếu tính modulo số bucket \(N\) một cách ngây thơ ở trạng thái giữa vòng, truy vấn có thể đến sai nơi.

## 7. Giả mã tra cứu, chèn, tách và xóa

Trong giả mã này, mỗi bucket có thể có **một trang chính và các trang tràn**. Thao tác tìm trong bucket phải kiểm tra cả những trang tràn; một bucket đang đầy không được làm mất bản ghi mới.

### Chọn bucket

~~~text
BUCKET_INDEX(k):
    M = m0 * 2^level
    b = hash(k) mod M
    if b < split_pointer:
        b = hash(k) mod (2 * M)
    return b
~~~

### Tìm và sửa giá trị

~~~text
GET(k):
    b = BUCKET_INDEX(k)
    for record in bucket[b] and its overflow pages:
        if record.key == k:
            return FOUND, record.value
    return NOT_FOUND

PUT(k, value):
    b = BUCKET_INDEX(k)
    if k already exists in bucket[b]:
        update its value
        return UPDATED

    append (k, value) to bucket[b] or an overflow page
    size = size + 1

    while size / (B * number_of_primary_buckets) > max_load:
        SPLIT_ONE_BUCKET()
    return INSERTED
~~~

Điểm cần nhớ: điều kiện chèn vào trang tràn **không đồng nghĩa phải tách chính bucket đó**. Lượt tách kế tiếp vẫn theo con trỏ.

### Tách một bucket

~~~text
SPLIT_ONE_BUCKET():
    M = m0 * 2^level
    old_index = split_pointer
    new_index = M + split_pointer  # Bằng số bucket hiện tại.
    allocate empty bucket[new_index]

    take all records from bucket[old_index] and overflow pages
    clear bucket[old_index]
    for (k, value) in those records:
        target = hash(k) mod (2 * M)
        assert target is old_index or new_index
        append (k, value) to bucket[target]

    split_pointer = split_pointer + 1
    if split_pointer == M:
        level = level + 1
        split_pointer = 0
~~~

### Xóa

~~~text
DELETE(k):
    b = BUCKET_INDEX(k)
    find the record with key k in bucket[b] and overflow pages
    if missing:
        return false
    remove the record; reclaim an empty overflow page if appropriate
    size = size - 1
    return true
~~~

Xóa **không bắt buộc** phải làm giảm số bucket ngay lập tức. Cấu trúc có thể giữ các bucket hiện tại để tránh co giãn liên tục, hoặc dùng thuật toán **gộp ngược thứ tự tách** khi số khóa giảm đáng kể.

## 8. Cài đặt Python minh họa

Mã sau cài đặt **linear hashing có kiểm soát theo tải** và dùng danh sách Python để đại diện cho **toàn bộ bản ghi trong bucket**, kể cả phần tương đương trang tràn. Một hệ lưu trữ thật thường dùng trang chính và chuỗi trang tràn riêng; việc dùng một danh sách giúp tập trung vào **định tuyến, split pointer và bước tách**.

Để theo dõi được phép chia lấy dư, mã dùng khóa là **số nguyên không âm** và lấy \(h(k)=k\). Đây là **hàm minh họa**, không phù hợp nếu các khóa có phân bố lệch hoặc do đối thủ lựa chọn. Trong ứng dụng thực tế phải thay bằng hàm băm có phân bố đủ tốt và có đủ bit.

~~~python
class LinearHashMap:
    def __init__(self, initial_buckets=2, bucket_capacity=2, max_load=0.8):
        if type(initial_buckets) is not int or initial_buckets < 1:
            raise ValueError("initial_buckets phải là số nguyên >= 1")
        if type(bucket_capacity) is not int or bucket_capacity < 1:
            raise ValueError("bucket_capacity phải là số nguyên >= 1")
        if type(max_load) not in (int, float) or not (0 < max_load < 1):
            raise ValueError("max_load phải nằm trong (0, 1)")

        self.m0 = initial_buckets
        self.B = bucket_capacity
        self.max_load = max_load
        self.level = 0
        self.split = 0
        self.buckets = [[] for _ in range(self.m0)]
        self.size = 0

    def _hash(self, key):
        if type(key) is not int or key < 0:
            raise ValueError("Ví dụ chỉ nhận khóa nguyên không âm")
        return key

    def _round_base(self):
        return self.m0 * (1 << self.level)

    def _index(self, key):
        value = self._hash(key)
        M = self._round_base()
        b = value % M
        if b < self.split:
            b = value % (2 * M)
        return b

    def load_factor(self):
        # Chỉ đếm dung lượng của các bucket chính.
        return self.size / (self.B * len(self.buckets))

    def get(self, key):
        # Trả cờ tồn tại để phân biệt giá trị None và khóa vắng mặt.
        index = self._index(key)
        for saved_key, value in self.buckets[index]:
            if saved_key == key:
                return True, value
        return False, None

    def _split_once(self):
        M = self._round_base()
        old_index = self.split
        new_index = M + self.split

        # Bất biến số bucket: N = M + split.
        assert len(self.buckets) == new_index

        old_records = self.buckets[old_index]
        self.buckets[old_index] = []
        self.buckets.append([])

        # Chỉ phân phối lại bản ghi của bucket s.
        for key, value in old_records:
            target = self._hash(key) % (2 * M)
            assert target in (old_index, new_index)
            self.buckets[target].append((key, value))

        self.split += 1
        if self.split == M:
            self.level += 1
            self.split = 0

    def put(self, key, value):
        index = self._index(key)
        bucket = self.buckets[index]

        for pos, (old_key, _) in enumerate(bucket):
            if old_key == key:
                bucket[pos] = (key, value)
                return False  # Cập nhật, không tạo khóa trùng.

        bucket.append((key, value))
        self.size += 1

        # Tăng từng bucket cho tới khi tải nằm trong ngưỡng.
        while self.load_factor() > self.max_load:
            self._split_once()
        return True

    def delete(self, key):
        index = self._index(key)
        bucket = self.buckets[index]

        for pos, (old_key, _) in enumerate(bucket):
            if old_key == key:
                bucket.pop(pos)
                self.size -= 1
                return True
        return False

    def overflow_pages(self):
        # Số trang tràn tương đương nếu một trang chứa tối đa B bản ghi.
        return sum(
            (len(bucket) - 1) // self.B
            for bucket in self.buckets if bucket
        )

    def show(self):
        M = self._round_base()
        print(
            f"level={self.level}, split={self.split}, "
            f"M={M}, N={len(self.buckets)}, "
            f"load={self.load_factor():.3f}"
        )
        for index, bucket in enumerate(self.buckets):
            primary = [key for key, _ in bucket[:self.B]]
            overflow = [key for key, _ in bucket[self.B:]]
            print(f"  bucket {index}: {primary}, overflow={overflow}")


table = LinearHashMap(initial_buckets=2, bucket_capacity=2, max_load=0.8)
for key in [0, 1, 3]:
    table.put(key, f"value-{key}")

table.show()
# level=0, split=0, M=2, N=2, load=0.750
# bucket 0: [0], overflow=[]
# bucket 1: [1, 3], overflow=[]

table.put(5, "value-5")
table.show()
# level=0, split=1, M=2, N=3, load=0.667
# bucket 0: [0], overflow=[]
# bucket 1: [1, 3], overflow=[5]
# bucket 2: [], overflow=[]

table.put(7, "value-7")
table.show()
# level=1, split=0, M=4, N=4, load=0.625
# bucket 0: [0], overflow=[]
# bucket 1: [1, 5], overflow=[]
# bucket 2: [], overflow=[]
# bucket 3: [3, 7], overflow=[]

print(table.get(7))  # (True, 'value-7')
print(table.get(2))  # (False, None)
table.put(7, "updated-7")
print(table.get(7))  # (True, 'updated-7')
print(table.delete(3))  # True
print(table.get(3))     # (False, None)
print(table.size)       # 4
~~~

### Các điểm cần đọc kỹ trong mã

- **_index** áp dụng đúng hai mức băm và kiểm tra chỉ số cơ sở có nhỏ hơn con trỏ tách hay không.
- **_split_once** luôn cấp một bucket tại **\(M+s\)**, rồi chỉ phân phối lại những bản ghi đã thuộc bucket **\(s\)**.
- Khi kết thúc vòng tách, **level tăng một**, **split về 0**. Tất cả bucket khi ấy đã theo mức băm mới.
- **put** kiểm tra khóa đã tồn tại, tránh chèn bản sao; sửa giá trị không làm tăng số khóa hoặc kích hoạt tách không cần thiết.
- **get** trả về cặp *(found, value)* để phân biệt khóa vắng mặt với một khóa có giá trị **None**.
- **delete** cố ý **không gộp bucket tự động**, nên phần bucket sau các thao tác xóa có thể còn chỗ trống.
- **overflow_pages** chỉ tính số trang tràn **tương đương về dung lượng**; mã dùng danh sách để học thuật toán, không hiện thực hóa cấu trúc trang đĩa hay I/O.

Ví dụ không giới hạn độ dài chuỗi tràn: nhiều khóa có cùng giá trị băm có thể tiếp tục ở một bucket dù bảng chính đã tăng rất lớn. Các giới hạn về tính khả thi, tốc độ và bộ nhớ phải xét cả **chất lượng hàm băm**.

## 9. Thu hẹp bảng khi dữ liệu giảm

Mở rộng theo split pointer có một thao tác đối xứng là **gộp ngược** (*reverse split*). Không phải mọi triển khai linear hashing đều tự thu hẹp: một số hệ thống ưu tiên giữ bucket đã cấp, vì tái sử dụng chúng sau này sẽ rẻ hơn so với liên tục cấp phát rồi giải phóng.

Nếu muốn giảm số bucket theo đúng thứ tự ngược với quá trình tăng trưởng:

1. **Chọn cặp bucket được tách cuối cùng**. Nếu \(s>0\), đó là bucket \(s-1\) và bucket mới \(M+(s-1)\), với \(M=m_0\,2^i\).
2. Nếu \(s=0\) và \(i>0\), cần **quay về vòng trước**: đặt \(i\leftarrow i-1\), khi đó \(M\) giảm một nửa và tạm coi \(s=M\); sau đó chọn cặp tách cuối cùng của vòng trước, tức giảm \(s\) một đơn vị.
3. Gộp bản ghi từ bucket có chỉ số lớn nhất trở lại bucket gốc, cập nhật metadata và bỏ bucket cuối.
4. Nếu gộp khiến số bản ghi vượt sức chứa trang chính, phải dùng **trang tràn** hoặc hoãn gộp; không được bỏ bản ghi.

Ví dụ sau khi đã hoàn tất vòng đầu, trạng thái là \(i=1,s=0,M=4,N=4\). Bước gộp đầu tiên quay về \(i=0,M=2,s=1,N=3\), hợp nhất **bucket 3 vào bucket 1**. Bước tiếp theo hợp nhất **bucket 2 vào bucket 0**, trở về \(i=0,s=0,N=2\).

**Chính sách co giãn:** Có thể chỉ kích hoạt gộp khi tải giảm thấp hơn một ngưỡng **nhỏ hơn ngưỡng mở rộng**. Ví dụ thử nghiệm là mở rộng khi tải vượt 0,8 và cân nhắc gộp khi tải xuống dưới 0,3. Khoảng cách hai ngưỡng (*hysteresis*) giúp tránh tình trạng một thao tác chèn làm tách rồi một thao tác xóa lập tức gây gộp ngược.

**Đồng bộ khi đọc/ghi:** Trong hệ thống nhiều luồng hoặc nhiều giao dịch, việc thay đổi split pointer, cấp bucket và di chuyển bản ghi phải được phối hợp để các truy vấn đang chạy không đọc trạng thái nửa cũ nửa mới. Ví dụ Python ở mục 8 là cấu trúc tuần tự, **không bảo đảm an toàn đa luồng**.

## 10. Phân tích độ phức tạp và chi phí I/O

Gọi \(n\) là số bản ghi, \(N=M+s\) là số bucket chính, \(B\) là dung lượng của một bucket chính, và \(L_b\) là số bản ghi thực tế trong bucket \(b\), **kể cả bản ghi ở vùng tràn**.

| Thao tác / tài nguyên | Chi phí | Điều kiện và giải thích |
| --- | --- | --- |
| **Tính bucket** | \(O(1)\) | Một giá trị băm, một hoặc hai phép modulo, so sánh với \(s\) |
| **Tìm một khóa** | \(O(L_b)\) nếu duyệt tuyến tính bản ghi trong bucket | Với phân bố băm tốt, bucket nhỏ và ít trang tràn, chi phí kỳ vọng thấp |
| **Chèn không tách** | \(O(L_b)\) nếu kiểm tra trùng bằng quét bucket | Có thể chèn vào trang tràn khi trang chính đầy |
| **Tách một bucket** | \(O(L_s)\) để phân phối bản ghi của bucket \(s\) | Không cần duyệt các bucket không liên quan |
| **Xóa một khóa** | \(O(L_b)\) với danh sách không có chỉ mục phụ | Có thể thu hồi trang tràn rỗng |
| **Bộ nhớ bucket chính** | \(O(NB)\) ô bản ghi | Có \(N=M+s\) bucket chính, mỗi bucket dung lượng \(B\) |
| **Bộ nhớ trang tràn** | Phụ thuộc số bản ghi tràn | Có thể tăng mạnh nếu nhiều khóa cùng giá trị băm |
| **Metadata** | Một số giá trị như \(m_0,i,s\), cộng bảng địa chỉ trang nếu cần | Không cần thư mục \(2^g\) con trỏ nhân đôi theo từng vòng |

Với **\(B\) cố định**, hàm băm đủ tốt và ngưỡng tải được duy trì phù hợp, số bản ghi kỳ vọng trên một bucket thường được kiểm soát và tra cứu có thể đạt **\(O(1)\) theo kỳ vọng** trong mô hình băm phù hợp. Tách từng bucket cũng giúp dàn trải công việc tái phân phối khóa qua nhiều lượt cập nhật. Nhưng:

- **Không có bảo đảm \(O(1)\) trong trường hợp xấu nhất** nếu nhiều khóa cùng vào một bucket hoặc tạo chuỗi tràn dài.
- Một lượt tách có thể phải xử lý \(O(n)\) bản ghi trong tình huống bất lợi khi nhiều khóa dồn vào bucket được tách.
- Tính chi phí phân bổ/kỳ vọng của chèn cần giả thiết cụ thể về phân bố khóa, hàm băm, kích thước bucket và chính sách kích hoạt tách; **định nghĩa linear hashing tự nó không chứng minh thời gian chèn hằng số trên mọi đầu vào**.

### Khi lưu dữ liệu trên đĩa

Nếu chỉ số bucket được tính trong RAM, mỗi bucket nằm ở một hoặc vài trang và bảng ánh xạ chỉ số bucket sang trang có thể truy cập hiệu quả:

- Truy vấn thường truy cập **một trang bucket chính**, cộng các trang tràn nếu cần tìm sâu hơn.
- Tách có thể cần **đọc bucket được tách cùng các trang tràn**, ghi lại bản ghi cho bucket cũ và mới, và cập nhật metadata/trang vật lý.
- Không bắt buộc phải quét tất cả bucket chính mỗi lần tăng thêm một bucket. Tuy nhiên, **không đồng nghĩa tổng I/O luôn hằng số**: một bucket với nhiều trang tràn có thể rất tốn kém.

Chi phí **bảng địa chỉ trang** cần được tính nếu bucket vật lý không thể truy cập trực tiếp bằng số bucket; linear hashing chỉ tránh cơ chế **thư mục nhân đôi kiểu extendible hashing**, chứ không có nghĩa hệ thống không cần metadata về nơi lưu trang.

### Dung lượng tăng theo số bản ghi

Với chính sách giữ hệ số tải quanh một khoảng không đổi và \(B\) cố định, số bucket chính có thể tăng **tuyến tính theo số bản ghi \(n\)** trong tình huống phân bố đều: \(N=\Theta(n)\) khi bỏ qua số bucket cơ sở ban đầu. Điều này không ngăn một số bucket có trang tràn dài nếu hàm băm kém hoặc phân bố đầu vào bất lợi.

## 11. So sánh linear hashing với các cấu trúc liên quan

| Cấu trúc | Cách định tuyến khóa và mở rộng | Điểm mạnh | Đánh đổi |
| --- | --- | --- | --- |
| **Linear hashing** | Dùng \(i,s\), hai mức modulo; lần lượt tách bucket \(s\) | Tăng dần mỗi bucket; không cần nhân đôi một directory \(2^g\) mục | Bucket tràn có thể chưa được tách ngay; truy vấn có thể phải theo trang tràn |
| **Extendible hashing** | Dùng directory theo global depth và local depth; tách bucket bị đầy | Chọn đúng bucket để tách, tra qua directory tới bucket đích | Directory có thể nhân đôi và tăng mạnh về số con trỏ |
| **Linear probing** | Một mảng ô; va chạm thì thăm dò liên tiếp | Bố trí gọn trong RAM, dễ hiện thực | Cụm khóa (*clustering*) làm tìm kiếm dài |
| **Separate chaining** | Một ô gốc nối với danh sách/nhóm bản ghi va chạm | Thêm/xóa linh hoạt | Truy vấn chậm khi chuỗi dài; overhead con trỏ/trang |
| **B+ tree** | Duy trì cấu trúc cây và thứ tự khóa; tách trang khi cần | Tìm chính xác, duyệt khoảng và khóa có thứ tự | Đường đi qua nhiều mức, có chi phí cân bằng cây |

**Linear hashing không phải linear probing.** Chúng có từ “linear” nhưng mục tiêu thiết kế khác nhau. Linear probing giải quyết va chạm **trong một bảng địa chỉ mở** bằng cách thử ô kế tiếp. Linear hashing quản lý **số bucket chính tăng tuần tự**, chọn bucket bằng mức băm và con trỏ tách, thường gắn với các trang và chuỗi tràn.

### Khi nên chọn linear hashing

Kỹ thuật này đáng cân nhắc khi:

- Tập khóa tăng **dần theo thời gian** và không muốn trả chi phí nhân đôi/tái phân phối toàn bộ bucket cùng lúc.
- Dữ liệu nằm trong **tệp, trang đĩa hoặc bộ lưu trữ theo khối**, cần mở rộng từng phần.
- Workload chủ yếu là **tìm chính xác theo khóa**, không yêu cầu truy vấn khoảng giá trị theo thứ tự.
- Hệ thống chấp nhận **trang tràn tạm thời** và có chính sách kiểm soát chúng.

Nếu cần **truy vấn theo khoảng, sắp xếp hoặc duyệt tăng dần**, các cấu trúc cây duy trì thứ tự thường phù hợp hơn. Nếu kích thước dữ liệu vừa phải và hoàn toàn ở RAM, một bảng băm động đơn giản có thể dễ triển khai hơn.

## 12. Những nhầm lẫn và lỗi triển khai thường gặp

1. **Nhầm linear hashing với linear probing.** Một bên tăng bucket theo con trỏ tách; bên kia quét các ô kế tiếp khi va chạm.
2. **Dùng \(h(k)\bmod N\) với \(N=M+s\).** Sai ở trạng thái giữa vòng; phải dùng \(h_i\) và chỉ dùng \(h_{i+1}\) nếu chỉ số cơ sở **nhỏ hơn \(s\)**.
3. **Luôn tách bucket đang tràn.** Trong linear hashing theo con trỏ tách tuần tự, bucket được tách là **\(s\)**, dù bucket gây kích hoạt nằm ở vị trí khác.
4. **Quên cấp bucket ở chỉ số \(M+s\).** Đây là bucket mới tương ứng với bucket \(s\), không phải một chỉ số tùy chọn.
5. **Tăng mức băm ngay sau mỗi lượt tách.** Mức chỉ tăng **sau khi đã tách hết \(M\) bucket** của vòng.
6. **Phân phối lại tất cả khóa khi tách.** Thường chỉ cần phân phối lại các bản ghi của bucket \(s\) cùng trang tràn của nó.
7. **Cho rằng bucket mới luôn có bản ghi.** Nếu các khóa của bucket đang tách đều có \(h_{i+1}(k)=s\), bucket mới có thể rỗng.
8. **Bỏ qua trang tràn khi tra cứu.** Khóa có thể nằm ngoài trang chính nhưng vẫn thuộc đúng bucket.
9. **Gộp bucket theo thứ tự bất kỳ sau xóa.** Nếu muốn co bảng thì cần đi ngược trình tự tách để bảo toàn bất biến \(N=M+s\).
10. **Không cập nhật đồng bộ metadata và dữ liệu.** Trong hệ có ghi đồng thời, một split nửa chừng có thể khiến truy vấn đọc sai bucket.
11. **Suy ra chi phí tệ nhất là \(O(1)\) chỉ vì chỉ số bucket tính trong \(O(1)\).** Việc duyệt trang tràn và tách bucket có thể tốn nhiều bước.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Ban đầu \(m_0=4\), hiện tại \(i=1\), \(s=3\). Có bao nhiêu bucket chính và những chỉ số nào đã được tách trong vòng này?

**Lời giải:** \(M=4\cdot2^1=8\); \(N=M+s=8+3=11\), các bucket chính có chỉ số 0 đến 10. Trong vòng hiện tại, các bucket cơ sở **0, 1, 2** đã tách; bucket 3 là bucket tiếp theo.

**Câu 2.** Với \(m_0=2\), \(i=1\), \(s=2\), dùng \(h(k)=k\). Tìm bucket cho các khóa 9, 10 và 13.

**Lời giải:** \(M=4\), \(N=6\). Khóa 9 có \(9\bmod4=1<2\), nên dùng \(9\bmod8=1\): bucket 1. Khóa 10 có \(10\bmod4=2\ge2\): bucket 2. Khóa 13 có \(13\bmod4=1<2\), nên dùng \(13\bmod8=5\): bucket 5.

**Câu 3.** Nếu đang ở \(M=4,s=3\), một lượt tách sẽ tạo bucket mới có chỉ số bao nhiêu? Trạng thái sau tách là gì?

**Lời giải:** Bucket được tách là 3, bucket mới có chỉ số \(M+s=7\). Sau lượt tách, \(s\) tăng thành 4 và bằng \(M\), nên bắt đầu vòng mới: \(M=8\), \(s=0\), \(i\) tăng một. Tổng số bucket là 8.

**Câu 4.** Trong ví dụ mục 6, vì sao chèn 5 làm tràn bucket 1 nhưng lượt tách lại tạo bucket 2 rỗng?

**Lời giải:** Điều kiện vượt ngưỡng tải kích hoạt một lượt split, còn **con trỏ tách lúc ấy là \(s=0\)**. Thuật toán bắt buộc tách bucket 0; khóa duy nhất ở đó là 0, vẫn thuộc bucket 0 khi xét modulo 4. Vì vậy bucket 2 mới rỗng, còn bucket 1 vẫn có trang tràn.

**Câu 5.** Một bucket chính chứa tối đa \(B=4\) bản ghi, bảng có \(N=25\) bucket và \(n=85\) khóa. Tải \(\alpha\) là bao nhiêu?

**Lời giải:**

\[
\alpha=\frac{85}{4\cdot25}=0{,}85.
\]

Nếu ngưỡng mở rộng là \(0{,}8\), chính sách có kiểm soát sẽ kích hoạt thêm lượt tách. Tuy nhiên, tải không nói rõ **bucket nào** đang có trang tràn: cần xét phân bố khóa thực tế.

**Câu 6.** Sau khi hoàn tất một vòng tách với \(M=4\), ta có \(i\) tăng và \(s=0\). Vì sao không cần quét lại tất cả bucket để chuyển sang \(h_{i+1}\)?

**Lời giải:** Mọi bucket cơ sở 0 đến 3 đã được tách theo \(h_{i+1}\) trong các lượt trước. Tất cả bản ghi hiện ở đúng bucket của mức mới, nên chỉ đổi metadata mức và đặt lại con trỏ.

**Câu 7.** Vì sao không thể kết luận tìm kiếm có thời gian \(O(1)\) tệ nhất chỉ từ công thức tính chỉ số bucket?

**Lời giải:** Công thức tính **địa chỉ bucket** là hằng số, nhưng sau đó vẫn có thể phải duyệt **nhiều bản ghi trong bucket và chuỗi trang tràn**. Nếu nhiều khóa có chung giá trị băm, số bản ghi phải kiểm tra có thể tới \(O(n)\).

## 14. Ghi nhớ

**Băm tuyến tính (linear hashing)** mở rộng bảng theo từng bucket chính, sử dụng **mức băm \(i\)** và **con trỏ tách \(s\)**. Với \(M=m_0\,2^i\), bảng luôn có \(N=M+s\) bucket; khóa được định tuyến theo \(h_i\), trừ khi bucket cơ sở đã nằm trước \(s\), khi đó dùng \(h_{i+1}\). Một lượt tách luôn chọn bucket **\(s\)**, tạo bucket mới **\(M+s\)**, phân phối lại khóa của bucket đó rồi tiến con trỏ.

Kỹ thuật này giúp **dàn trải công việc mở rộng** thay vì nhân đôi và băm lại toàn bộ bảng trong một lần. Đánh đổi là các bucket có thể phải dùng **trang tràn** trong lúc chờ lượt tách, nên truy vấn và chèn vẫn có thể tốn nhiều bước khi phân bố băm kém. Khi chọn cấu trúc dữ liệu, hãy cân nhắc **tốc độ tăng khóa, hệ số tải, I/O theo trang, chi phí tách/gộp và yêu cầu tra cứu chính xác hoặc theo khoảng**.
