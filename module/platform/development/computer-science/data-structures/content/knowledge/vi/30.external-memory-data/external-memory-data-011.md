# Ánh xạ tệp vào bộ nhớ và những chi phí không tự biến mất

## 1. Vấn đề: dữ liệu nằm trên thiết bị, chương trình muốn truy cập như mảng

Khi làm việc với mảng, danh sách liên kết, bảng băm hay cây trong RAM, ta thường viết một phép truy cập phần tử và giả định phần tử đã sẵn sàng cho CPU. Với dữ liệu ngoài bộ nhớ, một giá trị có thể nằm trên SSD/HDD và cần được đưa vào RAM trước khi CPU sử dụng.

**Ánh xạ tệp vào bộ nhớ** (*memory-mapped file*, thường gọi là **mmap**) cho phép hệ điều hành liên kết một vùng **không gian địa chỉ ảo** của tiến trình với các byte của tệp. Chương trình có thể truy cập các byte của vùng ánh xạ bằng thao tác đọc/ghi bộ nhớ, thay vì gọi một hàm đọc tệp cho từng lần truy cập.

Điều quan trọng nhất là: **mmap đổi cách chương trình yêu cầu dữ liệu; nó không khiến truy cập thiết bị, cấp phát bộ nhớ vật lý, đồng bộ ghi hay xử lý lỗi tự biến mất**.

Ví dụ, một ứng dụng lưu 200 triệu cặp khóa–giá trị vào tệp có thứ tự. Ứng dụng muốn thực hiện:

- Tìm một khóa bằng tìm kiếm nhị phân;
- Đọc một dải khóa đã sắp;
- Cập nhật một vùng dữ liệu trong tệp;
- Cho nhiều tiến trình cùng đọc một bộ dữ liệu lớn;
- Tránh tự xây dựng bộ đệm khi không cần.

mmap có thể giúp tổ chức truy cập đơn giản hơn, nhưng hiệu năng phụ thuộc vào **mẫu truy cập**, **kích thước trang**, **page cache**, **page fault**, **độ bền ghi** và **sự ổn định của tệp khi ánh xạ**.

Bài thuộc chương **Dữ liệu ngoài bộ nhớ** của học phần **Cấu trúc dữ liệu**. Ta sẽ dùng tư duy về bất biến, thao tác, độ phức tạp thời gian/bộ nhớ và tính cục bộ để xác định khi nào ánh xạ tệp là lựa chọn tốt.

## 2. mmap thực sự làm gì?

Một chương trình thường nhìn thấy **địa chỉ ảo**, còn hệ điều hành và phần cứng quản lý cách dịch địa chỉ ảo thành trang bộ nhớ vật lý. Khi ánh xạ một tệp, hệ điều hành thiết lập một vùng địa chỉ ảo tương ứng với nội dung tệp theo trang.

~~~text
Tiến trình
  truy cập địa chỉ ảo p
           |
           v
   Bảng trang (page tables) / MMU
           |
       +---+-------------------+
       |                       |
  Trang đã hiện diện      Trang chưa hiện diện
  trong RAM               hoặc chưa ánh xạ vào RAM
       |                       |
       v                       v
  CPU đọc/ghi           Page fault -> kernel
  trên trang RAM               |
                                v
                    Kiểm tra mapping và quyền
                                |
                  +-------------+--------------+
                  |                            |
            Trang có sẵn                Chưa có trong
            trong page cache           page cache
                  |                            |
                  v                            v
            Liên kết trang              Đọc dữ liệu từ
            vào ánh xạ                  thiết bị nếu cần
                  |                            |
                  +-------------+--------------+
                                |
                                v
                      Tiếp tục lệnh truy cập
~~~

Sơ đồ mô tả phổ biến nhất: ánh xạ tệp được nạp **theo nhu cầu** (*demand paging*). Hệ điều hành có thể đọc trước (*readahead*) hoặc chuẩn bị trang theo cơ chế riêng, nên không nhất thiết cứ mỗi lần chạm một trang sẽ có đúng một lần I/O hay đúng một page fault.

### Bốn khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Sai lầm hay gặp |
| --- | --- | --- |
| **Không gian địa chỉ ảo** | Dải địa chỉ mà tiến trình được phép tham chiếu | Nghĩ có dải địa chỉ lớn tức là đã dùng lượng RAM tương ứng |
| **Trang bộ nhớ** (*page*) | Đơn vị cơ bản để quản lý ánh xạ và bảo vệ bộ nhớ, thường là 4 KiB nhưng tùy hệ thống | Nghĩ đọc 8 byte luôn chỉ tốn đúng 8 byte I/O |
| **Page cache** | Các trang dữ liệu tệp được hệ điều hành giữ trong RAM để dùng lại | Nghĩ mmap có một cache hoàn toàn riêng với đường đọc tệp thông thường |
| **Page fault** | Sự kiện CPU không thể hoàn tất truy cập với ánh xạ trang hiện thời và phải chuyển cho kernel xử lý | Nghĩ mọi page fault đều phải đọc SSD/HDD |

Ví dụ ánh xạ một tệp 40 GiB **không có nghĩa tiến trình lập tức chiếm 40 GiB RAM**. Vùng địa chỉ ảo có thể lớn, trong khi số trang vật lý thực sự đang resident nhỏ hơn nhiều. Ngược lại, sau khi quét toàn bộ tệp, các trang vừa chạm có thể chiếm nhiều page cache, gây áp lực lên các dữ liệu khác trong RAM.

### Ánh xạ khác đọc tệp truyền thống ra sao?

Với lời gọi **read/pread**, chương trình yêu cầu kernel chuyển dữ liệu vào một vùng đệm của tiến trình. Kernel thường dùng page cache để đọc các trang tệp, sau đó sao chép byte cần thiết từ vùng được cache sang buffer của tiến trình.

Với **mmap**, chương trình truy cập trực tiếp vùng địa chỉ ảo được ánh xạ tới các trang tệp trong page cache, thường tránh được một lần sao chép **dữ liệu tệp từ page cache sang buffer người dùng**. Đổi lại, chương trình phải chịu chi phí thiết lập ánh xạ và các page fault khi chạm vùng chưa được ánh xạ hiện diện.

~~~text
read/pread:
  đọc tệp -> page cache (kernel) -> sao chép vào buffer ứng dụng -> xử lý

mmap:
  ánh xạ vùng địa chỉ ảo -> trang tệp trong page cache -> xử lý qua địa chỉ ảo
                                  ^
                         page fault nếu cần
~~~

Cả hai đường đều có thể dùng **cùng page cache của hệ điều hành**. mmap đôi khi được gọi là “zero-copy”, nhưng cụm này chỉ đúng ở **một số đoạn của đường đi dữ liệu**: vẫn có thể phát sinh I/O thiết bị, giải nén ở lớp lưu trữ, chuyển dữ liệu qua DMA, cập nhật bảng trang, cache miss của CPU và nhiều công việc kernel khác.

## 3. Trang, page fault và chi phí I/O

### 3.1. Minor fault và major fault

Một cách phân loại thông dụng trên hệ điều hành kiểu Unix:

- **Minor page fault:** kernel xử lý việc thiếu ánh xạ trang hiện thời nhưng **không cần đọc trang từ thiết bị lưu trữ**; ví dụ trang tệp đã có trong page cache.
- **Major page fault:** quá trình xử lý phải chờ I/O để có nội dung trang, thường do dữ liệu chưa nằm trong RAM.

Tên và bộ đếm có thể khác nhau theo hệ điều hành, và một lần đọc thiết bị có thể nạp nhiều trang nhờ readahead. Vì thế, **số major faults không nhất thiết bằng số lượt đọc khối vật lý**.

Một minor fault vẫn có chi phí: chuyển sang kernel, tra cứu cấu trúc quản lý bộ nhớ và cập nhật ánh xạ. Major fault có thể cộng thêm độ trễ I/O, đặc biệt bất lợi với truy cập ngẫu nhiên trên HDD hoặc khi SSD đang bận.

### 3.2. Đọc một byte có thể kéo theo đọc cả trang

Giả sử kích thước trang hệ điều hành là **P = 4096 byte**. Ứng dụng đọc 8 byte ở đầu một trang chưa được cache. Kernel có thể cần nạp ít nhất trang chứa 8 byte đó. Nếu 8 byte nằm ở cuối trang này và đầu trang tiếp theo, truy cập có thể chạm **hai trang**.

Với một đoạn dài **L** byte bắt đầu ở độ lệch tệp **o**, số trang hệ điều hành mà đoạn đó giao nhau trong mô hình trang cố định là:

\[
Q = \left\lceil \frac{(o \bmod P)+L}{P} \right\rceil
\]

khi \(L>0\), bỏ qua trường hợp ánh xạ đặc biệt. Đây là **số trang liên quan**, không nhất thiết là số I/O vật lý, vì nhiều trang có thể đã cache hoặc được nạp cùng nhau.

Ví dụ:

~~~text
Kích thước trang P = 4096 byte

Trang 0: offset [0, 4095]
Trang 1: offset [4096, 8191]

Đọc 8 byte từ offset 4092:
  byte 4092..4095 nằm ở trang 0
  byte 4096..4099 nằm ở trang 1
  => chạm 2 trang.
~~~

Một biểu thức truy cập bộ nhớ ngắn trong mã nguồn **không đồng nghĩa** một thao tác I/O nhỏ tương ứng trên thiết bị.

### 3.3. Truy cập tuần tự và ngẫu nhiên

Nếu quét một tệp đã sắp theo thứ tự offset tăng dần, hệ điều hành có thể nhận ra mẫu **tuần tự** và đọc trước các trang kế tiếp. Chi phí I/O chủ yếu gần với lượng dữ liệu thực sự quét.

Ngược lại, khi nhảy giữa các vị trí xa nhau, nhất là khi tập dữ liệu lớn hơn page cache, một số truy cập có thể gây page fault và I/O ngẫu nhiên:

~~~text
Tuần tự:
  trang 10 -> 11 -> 12 -> 13 -> 14 -> 15
  có cơ hội gom đọc và readahead

Ngẫu nhiên:
  trang 10 -> 75.000 -> 23 -> 910.000 -> 518
  khó dự đoán trang kế tiếp; cache dễ bị bỏ lỡ
~~~

Giả sử **10.000 truy vấn** chỉ đọc **8 byte** ở **10.000 trang khác nhau**, mỗi trang **4 KiB** và tất cả đều chưa cache:

~~~text
Dữ liệu ứng dụng cần:    10.000 * 8 B     = 80.000 B
Dung lượng trang liên quan:
                         10.000 * 4096 B  = 40.960.000 B
                                              ≈ 39,06 MiB
~~~

Đây là **ước lượng dung lượng trang phải nạp** trong mô hình đơn giản, không phải số byte đọc vật lý luôn xảy ra. Readahead, hệ thống tệp, kích thước sector, nén, thiết bị, caching và các lần truy cập lặp lại đều có thể thay đổi I/O thực. Nhưng ví dụ cho thấy: **mmap không loại bỏ chi phí đọc thừa do tính cục bộ kém**.

## 4. Tệp 100 GiB được ánh xạ không phải 100 GiB RAM miễn phí

Khi tạo ánh xạ, hệ điều hành dành một vùng **địa chỉ ảo** có kích thước yêu cầu. RAM vật lý thường được sử dụng khi các trang thực sự được chạm, được đọc trước hoặc được thay đổi.

Cần phân biệt ba số đo:

- **Virtual size / VIRT:** tổng không gian địa chỉ ảo tiến trình có thể tham chiếu, bao gồm cả vùng chưa resident.
- **Resident set / RSS:** bộ nhớ vật lý hiện đang được ánh xạ vào tiến trình, có thể bao gồm các trang **dùng chung** và không nhất thiết đại diện cho RAM riêng tiến trình sở hữu.
- **Page cache:** các trang tệp hệ điều hành đang giữ; có thể được chia sẻ giữa nhiều tiến trình và bị thu hồi khi cần.

Ví dụ một tiến trình ánh xạ 100 GiB nhưng chỉ truy cập 32 MiB ở vài vùng. Phần được nạp có thể gần 32 MiB (cộng overhead và readahead), chứ không mặc nhiên là 100 GiB. Tuy nhiên việc cấp vùng địa chỉ lớn, các cấu trúc quản lý ánh xạ và bảng trang vẫn có chi phí; trên môi trường không gian địa chỉ hạn chế, ánh xạ quá lớn có thể thất bại.

### Khi RAM căng, hệ điều hành làm gì?

- Những trang tệp **sạch** (*clean*) có thể bị bỏ khỏi page cache vì nội dung còn trên thiết bị; lần đọc sau cần nạp lại.
- Những trang tệp **bẩn** (*dirty*) đã bị sửa trong ánh xạ chia sẻ có thể cần được **ghi lại** trước khi được thu hồi.
- Nếu bộ dữ liệu được truy cập rộng hơn bộ nhớ hiệu dụng, tiến trình có thể liên tục đẩy các trang cũ ra rồi nạp chúng trở lại (**cache thrashing**).

Ví dụ hai tiến trình cùng mmap một tệp và cùng đọc các vùng giống nhau có thể **chia sẻ trang vật lý** trong page cache. Không nên cộng RSS của từng tiến trình rồi kết luận hệ thống đã sử dụng từng đó RAM độc lập.

### TLB và bảng trang cũng có chi phí

CPU dùng **TLB** để cache kết quả dịch địa chỉ ảo sang địa chỉ vật lý. Truy cập rải rác qua rất nhiều trang có thể làm giảm tỷ lệ TLB hit, tăng chi phí đi bộ bảng trang (*page-table walk*) ngay cả khi dữ liệu đã trong RAM. Kernel còn phải quản lý metadata của các vùng ánh xạ và trang được ánh xạ.

Do đó, một thuật toán có tính cục bộ tốt có thể hiệu quả hơn thuật toán “số phép so sánh ít” nhưng nhảy giữa nhiều trang.

## 5. Mẫu truy cập quyết định hiệu năng của cấu trúc dữ liệu

### 5.1. Mảng bản ghi cố định, đọc tuần tự

Nếu tệp lưu các bản ghi cố định **16 byte/bản ghi** trong một vùng liên tục, một trang 4096 byte về lý thuyết chứa:

~~~text
4096 / 16 = 256 bản ghi/trang
~~~

Quét 256 bản ghi kề nhau thường khai thác tốt một trang vừa được nạp. Truy cập mỗi bản ghi trong cùng trang không cần thêm I/O thiết bị nếu trang còn resident.

Đây là ví dụ của **tính cục bộ không gian** (*spatial locality*): các vị trí được dùng gần nhau về địa chỉ.

### 5.2. Tìm nhị phân trên mảng đã sắp

Một mảng khóa đã sắp cho tìm kiếm nhị phân với:

\[
T_{\text{comparisons}}(N)=O(\log_2 N).
\]

Nhưng khi tệp nằm trên thiết bị và mmap chỉ đóng vai trò ánh xạ, các lần so sánh giữa mảng có thể chạm các trang rất xa nhau. Trong trường hợp cache lạnh, chi phí còn có thể là **O(log N) lần chạm trang rời rạc**.

~~~text
Mảng 1.000.000 khóa đã sắp

Lần 1: so sánh vị trí 500.000
Lần 2: so sánh vị trí 250.000
Lần 3: so sánh vị trí 375.000
...
=> khoảng 20 phép so sánh, nhưng các vị trí đầu có thể ở nhiều trang xa nhau.
~~~

Nếu cùng tìm nhiều lần, một số trang ở giữa mảng thường được cache và chi phí có thể giảm; nếu dữ liệu vượt xa RAM và khóa truy vấn phân bố rộng, bộ nhớ ảo **không biến** chi phí tìm kiếm thành chi phí RAM thuần túy.

### 5.3. B+-tree và chỉ mục khối

**B+-tree** được thiết kế để tăng số con mỗi trang (*fanout*), giảm số cấp cần đọc khi tìm một khóa. Với fanout hữu hiệu **f**, đường tìm có độ dài theo bậc:

\[
O(\log_f N)
\]

lượt truy cập trang trong mô hình thuận lợi. mmap có thể được dùng để **truy cập các trang của B+-tree**, nhưng không thay thế việc thiết kế cấu trúc B+-tree.

Tương tự, một **SSTable** có thể có **block index** để đưa phép tìm vào đúng data block. SSTable có thể được đọc qua mmap hoặc qua pread; việc lựa chọn API không tự sinh ra chỉ mục hay làm thay đổi bất biến sắp xếp của dữ liệu.

| Tổ chức dữ liệu | Đường tìm/đọc | Tác dụng của mmap |
| --- | --- | --- |
| Mảng chưa sắp | Có thể phải quét nhiều phần tử | Giúp truy cập theo địa chỉ, không giảm số phần tử phải kiểm tra |
| Mảng đã sắp | Tìm nhị phân qua nhiều vị trí | Giảm thao tác sao chép buffer ở một số tình huống; các lần nhảy trang vẫn tồn tại |
| B+-tree | Gốc → trang trong → lá | Có thể ánh xạ trang, nhưng chiều cao và fanout mới quyết định số trang logic |
| SSTable + block index | Index chọn data block, quét theo thứ tự | Giúp truy cập vùng đã định vị; không thay thế index/Bloom filter |
| Bảng băm ngoài bộ nhớ | Băm chọn bucket/trang | Có thể mmap các bucket, nhưng va chạm và I/O bucket vẫn tồn tại |

Điểm cốt lõi: **tối ưu thuật toán theo trang và tính cục bộ** vẫn quan trọng dù chương trình dùng con trỏ do mmap cung cấp.

## 6. Ví dụ: tìm khóa trong tệp đã sắp bằng Python mmap

Giả sử tệp dữ liệu là một mảng các bản ghi **(key, value)**, mỗi trường là số nguyên không dấu 64 bit, mã hóa **little-endian**, nên một bản ghi dài đúng **16 byte**. Khóa duy nhất và các bản ghi đã được sắp tăng dần theo key.

Chúng ta có thể mmap tệp ở chế độ chỉ đọc rồi tìm nhị phân:

~~~python
import mmap
import os
import struct

RECORD = struct.Struct("<QQ")  # key: uint64, value: uint64


def find_value(path: str, target_key: int) -> int | None:
    with open(path, "rb") as file:
        size = os.fstat(file.fileno()).st_size

        if size == 0:
            return None

        if size % RECORD.size != 0:
            raise ValueError("Kích thước tệp không khớp định dạng bản ghi")

        count = size // RECORD.size

        with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            left, right = 0, count  # Khoảng nửa mở [left, right)

            while left < right:
                mid = (left + right) // 2
                key, _ = RECORD.unpack_from(mm, mid * RECORD.size)

                if key < target_key:
                    left = mid + 1
                else:
                    right = mid

            if left < count:
                key, value = RECORD.unpack_from(
                    mm, left * RECORD.size
                )
                if key == target_key:
                    return value

            return None
~~~

Ví dụ sử dụng:

~~~python
value = find_value("records.bin", 2026)

if value is None:
    print("Không tìm thấy khóa")
else:
    print("Giá trị:", value)
~~~

**Giải thích từng điểm:**

1. Tệp được mở **chỉ đọc**, ánh xạ dùng chế độ **ACCESS_READ** nên hàm không sửa dữ liệu.
2. Trước khi mmap, hàm kiểm tra tệp rỗng; một ánh xạ kích thước 0 cho tệp rỗng không hợp lệ trên nhiều hệ thống.
3. Kiểm tra kích thước là bội số của 16 để không giải mã một bản ghi không đầy đủ.
4. **unpack_from** giải mã đúng 16 byte tại vị trí đã tính, không sao chép cả tệp sang một mảng Python.
5. Tìm kiếm nhị phân có **O(log N)** lần so sánh, nhưng mỗi lần truy cập vẫn có thể sinh page fault nếu trang chưa resident.
6. Khi kết thúc khối **with**, vùng mmap được đóng đúng vòng đời.

Mã giả định **tệp không thay đổi hoặc bị cắt ngắn trong khi đọc**. Nếu một tiến trình khác đồng thời truncate tệp, truy cập một phần vùng đã ánh xạ có thể gây lỗi nghiêm trọng, chẳng hạn **SIGBUS** trên các hệ thống POSIX. Để phục vụ đọc đồng thời an toàn, cần chính sách xuất bản tệp bất biến, khóa hoặc snapshot phù hợp.

Định dạng này cũng **không tự mô tả**: bên tạo tệp phải thỏa thuận little-endian, số byte mỗi trường, thứ tự khóa và cách biểu diễn giá trị. Không được ép một tệp nhị phân bất kỳ thành mảng struct rồi giả định cấu trúc luôn hợp lệ.

## 7. Ánh xạ chỉ đọc, chia sẻ và bản sao riêng

Ở giao diện POSIX, hai cờ quan trọng là **MAP_SHARED** và **MAP_PRIVATE**. Quyền truy cập còn phụ thuộc **PROT_READ/PROT_WRITE** và quyền của file descriptor.

| Chế độ | Cách hiểu | Điều cần nhớ |
| --- | --- | --- |
| **MAP_SHARED** | Thay đổi vùng ánh xạ có thể được các ánh xạ chia sẻ khác nhìn thấy và có thể ghi trở lại tệp | Cần đồng bộ dữ liệu, độ bền ghi và phối hợp giữa tiến trình |
| **MAP_PRIVATE** | Khi tiến trình ghi, cơ chế **copy-on-write** tạo trang riêng; sửa đổi không được ghi trở lại tệp gốc | Không phải cơ chế commit dữ liệu; thay đổi của tệp từ bên ngoài có thể có ngữ nghĩa không được bảo đảm giống snapshot |
| **Chỉ đọc** | Tiến trình chỉ được đọc theo quyền ánh xạ | Không có nghĩa tệp bên dưới bất biến nếu tác nhân khác còn quyền sửa |

Trong Python, các mức **mmap.ACCESS_READ**, **ACCESS_WRITE** và **ACCESS_COPY** có ý nghĩa tương tự về mặt sử dụng. Cách triển khai chi tiết phụ thuộc hệ điều hành và thư viện, nên cần xem tài liệu API đang dùng.

### MAP_PRIVATE không phải snapshot giao dịch

Khi ghi vào trang của ánh xạ riêng, tiến trình tạo bản sao riêng theo cơ chế copy-on-write. Nhưng **không nên suy ra toàn bộ vùng được đóng băng như một snapshot nhất quán** ngay lúc tạo mapping. Nếu tệp nền bị thay đổi đồng thời, chi tiết quan sát được phụ thuộc hệ điều hành và hành vi không được bảo đảm hoàn toàn ở một số trường hợp.

Muốn một snapshot đọc nhất quán, thiết kế an toàn hơn là giữ **tệp bất biến**, dùng **phiên bản tệp** hoặc cơ chế snapshot do hệ thống lưu trữ quản lý.

### Ghi chia sẻ không tương đương ghi giao dịch

Một ghi qua **MAP_SHARED** có thể sửa trang RAM trước khi nội dung đó được ghi bền ra thiết bị. Hệ điều hành có thể ghi các trang bẩn sau, gom nhiều thay đổi thành đợt.

~~~text
CPU ghi vào vùng MAP_SHARED
               |
               v
       Trang trong RAM thành dirty
               |
          +----+----+
          |         |
    Chưa ghi bền   Kernel writeback
          |         |
      Mất nguồn?    v
                  Thiết bị lưu trữ
~~~

Muốn kiểm soát việc đồng bộ, chương trình có thể dùng **msync** trên POSIX hoặc **flush** của thư viện mmap tương ứng; trong một số tình huống cần **fsync/fdatasync** và đồng bộ metadata hoặc thư mục chứa tệp theo quy trình của hệ thống tệp. Ngữ nghĩa chính xác phụ thuộc API, hệ điều hành và hệ thống tệp.

Điểm cần ghi nhớ: **đã gán một giá trị qua con trỏ mmap không có nghĩa giá trị đã bền sau khi mất điện**.

## 8. Những chi phí ghi không tự biến mất

### 8.1. Dirty pages và writeback

Nếu sửa một trường dài 8 byte bên trong trang 4096 byte, kernel thường theo dõi trạng thái **bẩn ở mức trang**. Nó có thể ghi lại một vùng lớn hơn chính 8 byte đó, tùy hệ thống tệp và cơ chế ghi thiết bị.

Định nghĩa đo lường đơn giản cho **write amplification**:

\[
WA = \frac{\text{số byte ghi vật lý xuống thiết bị}}
          {\text{số byte dữ liệu ứng dụng thực sự cập nhật}}
\]

Không nên tự khẳng định một sửa đổi 8 byte luôn ghi đúng 4096 byte: hệ điều hành, journal, cache, ổ lưu trữ và cơ chế writeback có thể gom, tách hoặc ghi thêm dữ liệu. Tuy vậy, **đơn vị quản lý theo trang/khối** giải thích vì sao dữ liệu ghi vật lý không tỷ lệ tuyến tính với số byte ứng dụng thay đổi.

### 8.2. Đồng bộ ghi và độ trễ

Hệ thống có thể trả về nhanh khi dữ liệu mới chỉ ở RAM, nhưng khi ứng dụng yêu cầu ghi **bền vững**, đường ghi phải đưa thông tin cần thiết qua lớp hệ điều hành/hệ thống tệp đến miền lưu trữ đáp ứng hợp đồng độ bền.

- Ghi không đồng bộ thường cho độ trễ ứng dụng thấp hơn trước khi chờ thiết bị.
- Ghi đồng bộ có thể chờ I/O, chịu ảnh hưởng hàng đợi thiết bị, flush/barrier và các chi phí khác.
- Đồng bộ từng cập nhật rất nhỏ có thể tốn nhiều overhead hơn gộp một lô cập nhật, dù dung lượng dữ liệu hữu ích giống nhau.

mmap thay đổi API mà chương trình dùng, **không tự cung cấp tính bền vững của giao dịch**.

### 8.3. Atomicity và crash consistency

Nếu một cập nhật thay đổi nhiều trường hoặc nhiều trang, mất điện có thể xảy ra sau khi chỉ một phần nội dung được ghi bền. Tệp có thể rơi vào **trạng thái nửa cập nhật**, ngay cả khi tiến trình có thực hiện lệnh ghi bộ nhớ theo đúng thứ tự.

Ví dụ một chỉ mục lưu ở tệp gồm:

~~~text
Page A: khóa phân cách cho biết khóa K nằm ở page B
Page B: dữ liệu thật của khóa K
~~~

Nếu cập nhật page A và page B không có giao thức phục hồi mà hệ thống ngừng đột ngột, một trong hai trang có thể phản ánh phiên bản mới trong khi trang còn lại vẫn cũ. Chỉ mmap cả hai trang **không đảm bảo nguyên tử**.

Các kỹ thuật thường được kết hợp tùy yêu cầu gồm:

- **WAL (write-ahead logging):** ghi log ý định/cập nhật trước khi cho phép sửa trang dữ liệu theo quy tắc phục hồi.
- **Copy-on-write + chuyển con trỏ gốc:** xây phiên bản mới rồi xuất bản tham chiếu tới phiên bản hoàn chỉnh với cơ chế bền vững thích hợp.
- **Checksum, generation/version:** phát hiện trang hoặc cấu trúc không phù hợp, hỗ trợ phục hồi.
- **Giao thức commit rõ ràng:** quy định thứ tự ghi, flush và xử lý khi khởi động lại.

**msync không tự biến một chuỗi cập nhật nhiều trang thành một transaction nguyên tử.** Đây là khác biệt giữa “dữ liệu được đồng bộ” và “cấu trúc dữ liệu vẫn nhất quán sau crash”.

## 9. Những lỗi thực tế khi dùng mmap

### 9.1. Truncate hoặc thay đổi kích thước tệp đang ánh xạ

Giả sử tiến trình A mmap vùng 1 GiB, tiến trình B cắt tệp xuống còn 100 MiB. Khi A truy cập vùng đã ánh xạ tương ứng với phần đã bị cắt, trên hệ thống POSIX có thể nhận **SIGBUS**. Đây không chỉ là lỗi “không tìm thấy khóa” thông thường.

Cách giảm rủi ro:

- Dùng các **tệp dữ liệu bất biến** sau khi xuất bản.
- Khi cần thay tệp, tạo tệp mới hoàn chỉnh rồi **đổi tham chiếu/đường dẫn xuất bản** theo giao thức phù hợp; giữ tệp cũ tồn tại trong suốt vòng đời các ánh xạ đang dùng.
- Có cơ chế phiên bản, khóa hoặc phối hợp giữa writer và reader; không truncate tệp đang có người đọc mmap.
- Không giả định chỉ kiểm tra kích thước tệp một lần là đủ khi có tác nhân khác được phép sửa tệp.

Việc đổi tên/xóa tên tệp còn đang ánh xạ có ngữ nghĩa khác nhau theo hệ điều hành; không thể coi mọi hành vi POSIX là giống Windows.

### 9.2. Offset, căn chỉnh và kiểm tra biên

Nhiều API mmap yêu cầu **offset ánh xạ** căn theo kích thước trang của hệ điều hành hoặc theo đơn vị phân bổ đặc thù của nền tảng. Nếu muốn ánh xạ dữ liệu bắt đầu tại offset tùy ý, cần:

1. Làm tròn offset yêu cầu xuống bội số của granularity;
2. Ánh xạ từ offset đã căn chỉnh và đủ dài;
3. Dùng độ lệch tương đối trong vùng đã ánh xạ để tới vị trí mong muốn;
4. Kiểm tra chặt **offset + length**, tránh overflow và vượt biên tệp.

~~~text
Granularity = 4096
Muốn đọc từ file offset = 9000

map_offset = floor(9000 / 4096) * 4096 = 8192
delta      = 9000 - 8192             = 808

Truy cập dữ liệu tại: mapped_base + 808
~~~

**Không được** tạo con trỏ vượt phạm vi ánh xạ rồi đọc chỉ vì “tệp chắc còn dữ liệu”. Trong C/C++, truy cập vùng không hợp lệ có thể gây SIGSEGV/SIGBUS hoặc hành vi không xác định.

### 9.3. Con trỏ trực tiếp vào dữ liệu tệp

Không nên lưu con trỏ RAM tuyệt đối vào tệp rồi kỳ vọng lần mmap sau địa chỉ ảo sẽ giống lần trước. Vùng ánh xạ có thể nằm ở địa chỉ khác trong mỗi lần chạy hay mỗi tiến trình.

Thay vào đó, lưu **offset tương đối** hoặc **ID trang**:

~~~text
Không nên lưu:  pointer = 0x7f12a000...
Nên lưu:        record_offset = 128640

Khi đọc lại:
  record_address = mapped_base + record_offset
~~~

Nếu lưu struct nhị phân, cần quy định rõ **endianness**, căn chỉnh (*alignment*), padding, kích thước trường, phiên bản định dạng và kiểm tra checksum. Đặc biệt trong C/C++, ép trực tiếp một vùng byte bất kỳ thành đối tượng có con trỏ/kiểu phức tạp có thể vi phạm yêu cầu alignment, lifetime hoặc layout.

### 9.4. Dữ liệu thay đổi đồng thời

**MAP_SHARED** giúp nhiều tiến trình nhìn thấy các thay đổi vùng chia sẻ, nhưng **không tự tạo ra khóa, thao tác nguyên tử hoặc thứ tự bộ nhớ chính xác**. Hai writer có thể ghi đè nhau; một reader có thể nhìn thấy bản ghi khi mới được cập nhật một nửa.

Muốn cho nhiều tiến trình ghi/đọc, cần cơ chế phù hợp với ngữ nghĩa mong muốn:

- Khóa/tổ chức một writer duy nhất;
- Primitive đồng bộ liên tiến trình tương thích với nền tảng;
- Generation/version và giao thức reader xác nhận đọc nhất quán;
- Tệp bất biến kết hợp xuất bản phiên bản mới.

### 9.5. Tệp không đáng tin cậy

Khi mmap dữ liệu đầu vào từ bên ngoài, cần coi nội dung như **byte không đáng tin cậy**. Một offset hoặc số lượng mục được đọc từ header có thể sai hoặc bị cố ý làm hỏng. Trước mỗi truy cập, kiểm tra tính hợp lệ của header, độ dài, phạm vi, phép nhân/cộng offset và định dạng khóa.

Ánh xạ tệp không làm việc giải mã an toàn hơn. Nó chỉ biến các lỗi xác thực biên thành nguy cơ truy cập vùng nhớ sai dễ xảy ra hơn nếu chương trình dùng con trỏ trực tiếp.

## 10. So sánh mmap với read/pread và đọc tuần tự

| Khía cạnh | mmap | read/pread với buffer ứng dụng |
| --- | --- | --- |
| Giao diện lập trình | Truy cập dữ liệu qua địa chỉ ảo | Gọi API đọc, ứng dụng quản lý buffer |
| Nạp dữ liệu khi cần | Thường qua demand paging/page fault | Qua lời gọi đọc; kernel có thể dùng page cache |
| Sao chép page cache → buffer ứng dụng | Thường tránh một bản sao cho nội dung ánh xạ | Thường có sao chép vào buffer |
| Chi phí bổ sung | Thiết lập mapping, fault handling, page table/TLB, quản lý vùng ánh xạ | Lời gọi hệ thống, quản lý buffer và copy |
| Truy cập ngẫu nhiên | Dễ viết như truy cập mảng, nhưng có thể nhiều page fault rải rác | pread chỉ rõ offset/length, dễ giới hạn dữ liệu yêu cầu |
| Quét tuần tự lớn | Có thể hưởng readahead; vẫn chịu áp lực cache | Có thể dùng buffer tuần tự, readahead và kiểm soát vòng đời dữ liệu đọc |
| Quản lý bộ nhớ | Hệ điều hành quyết định resident/reclaim theo trang | Ứng dụng chủ động quyết định số buffer và cách tái sử dụng |
| Ghi và đồng bộ | Dirty page, msync/flush, phối hợp độ bền | write/pwrite, fsync và giao thức độ bền |
| Tệp bị truncate đồng thời | Có nguy cơ lỗi truy cập mapping như SIGBUS | Thường API báo EOF/đọc ngắn; vẫn phải xử lý race và tính nhất quán |
| Khả năng di động | API và giới hạn khác nhau giữa nền tảng | Các thao tác I/O truyền thống thường dễ kiểm soát theo byte hơn |

**Không có lựa chọn thắng trong mọi trường hợp.** mmap thường thuận tiện cho tệp dữ liệu chủ yếu chỉ đọc, có định dạng ổn định, cần truy cập nhiều vị trí ngẫu nhiên hoặc muốn chia sẻ trang qua các tiến trình. read/pread có thể thuận lợi hơn khi cần điều khiển chính xác buffer, giới hạn lượng dữ liệu đang resident, làm I/O bất đồng bộ hoặc xử lý tệp thay đổi liên tục.

### Trường hợp mmap thường hợp lý

- Tệp **bất biến**, định dạng được kiểm soát, nhiều lần tra cứu vào vùng giống nhau;
- Chỉ mục có cấu trúc phù hợp để tìm đúng trang cần thiết;
- Nhiều tiến trình cùng đọc một dataset và hưởng lợi từ page cache chung;
- Quét hoặc truy cập theo offset lặp lại, việc copy dữ liệu qua buffer gây chi phí đáng kể;
- Ứng dụng có thể chấp nhận ngữ nghĩa lỗi theo trang, kiểm soát vòng đời mapping và độ bền riêng.

### Trường hợp cần thận trọng

- Tệp có thể bị thay kích thước hoặc ghi chồng bởi bên khác;
- Bộ dữ liệu lớn hơn RAM nhiều lần, truy cập ngẫu nhiên rải rác làm cache thrash;
- Ứng dụng cần hạn mức bộ nhớ dễ dự báo hoặc kiểm soát truy cập block chính xác;
- Cập nhật nhiều trang phải được commit nguyên tử;
- Có dữ liệu không đáng tin cậy hoặc định dạng nhị phân phức tạp;
- Tiến trình 32-bit hoặc nền tảng có không gian địa chỉ hạn chế.

## 11. Page cache và ứng dụng không được kiểm soát hoàn toàn

Khi tự thiết kế **buffer pool**, ví dụ cho B+-tree hoặc cơ sở dữ liệu, ứng dụng có thể quyết định trang nào cần giữ, cách pin/unpin, khi nào đẩy trang bẩn và tổ chức đọc trước cho các truy vấn riêng.

Với mmap, hệ điều hành điều phối phần lớn hoạt động nạp và thu hồi trang. Đây là lợi ích về độ đơn giản, nhưng cũng là giới hạn:

- Kernel có thể giữ những trang ít hữu ích hơn so với thông tin về truy vấn mà ứng dụng biết.
- Một đợt quét lớn có thể gây áp lực lên cache của các trang thường xuyên truy cập.
- Page cache dùng chung với các tiến trình khác; hiệu năng có thể thay đổi theo tải hệ thống.
- Mức resident và writeback không đồng nghĩa ranh giới giao dịch do ứng dụng muốn.
- Các gợi ý truy cập như **madvise**, **posix_fadvise** hoặc các API tương tự chỉ là cơ chế điều chỉnh có điều kiện, không bảo đảm mọi trang sẽ được cache/đuổi đúng như dự đoán.

Một hệ quản trị cơ sở dữ liệu có thể dùng **buffer pool riêng** để kiểm soát lịch đọc/ghi và snapshot. Một ứng dụng khác lại hưởng lợi khi để kernel quản lý page cache bằng mmap. Quyết định này nằm ở **thiết kế toàn hệ thống**, không chỉ ở cú pháp truy cập bộ nhớ.

## 12. Đo hiệu năng mmap như thế nào cho đúng?

### 12.1. Phân biệt cache lạnh và cache nóng

Hai lần chạy cùng thuật toán có thể cho thời gian khác nhau rất lớn:

~~~text
Lần đầu:
  dữ liệu chưa có trong page cache
  -> nhiều major faults / I/O thiết bị

Lần sau:
  dữ liệu còn ở page cache
  -> chủ yếu CPU, minor faults hoặc truy cập RAM
~~~

Nếu chỉ đo lần thứ hai, kết quả có thể nói lên hiệu năng RAM nhiều hơn là chi phí thiết bị. Nếu chỉ đo lần đầu mà bỏ qua truy cập lặp, kết quả cũng không đại diện cho tải sản xuất có cache nóng.

**Nên đo cả hai**, ghi rõ điều kiện và báo riêng:

- **p50/p95/p99** độ trễ point lookup;
- Thông lượng quét tuần tự và số byte xử lý;
- Major/minor page faults nếu hệ điều hành cung cấp;
- Lượng đọc/ghi vật lý, IOPS, hàng đợi I/O;
- RSS, page cache, bộ nhớ hệ thống và áp lực reclaim;
- CPU time, TLB/cache miss nếu công cụ hỗ trợ;
- Độ trễ và lượng byte đồng bộ ghi khi có cập nhật.

### 12.2. Benchmark mẫu truy cập, không chỉ mẫu API

Một benchmark công bằng nên so sánh ít nhất ba dạng tải với cùng dữ liệu:

| Tải | Mục đích | Điều cần quan sát |
| --- | --- | --- |
| **Quét tuần tự** 1 GiB | Thông lượng và readahead | Byte/giây, major faults, page cache |
| **10.000 điểm ngẫu nhiên** | Độ trễ truy cập và tính cục bộ | p99, số trang khác nhau, I/O ngẫu nhiên |
| **Điểm nóng + vùng lạnh** | Cache có giữ phần quan trọng không | Tỷ lệ cache hit, độ trễ khi xen quét lớn |
| **Cập nhật + đồng bộ ghi** | Chi phí độ bền và writeback | Byte ghi vật lý, flush latency, stalls |

Giữ giống nhau: thiết bị, kích thước file, kích thước record/page, lượng RAM cho ứng dụng, độ đồng thời, tỷ lệ hit/miss và yêu cầu độ bền. Đừng so sánh **mmap đọc dữ liệu đã cache** với **pread đọc dữ liệu chưa cache** rồi kết luận API nào nhanh hơn.

### 12.3. Không dùng số page fault như thước đo duy nhất

Một major fault có thể kích hoạt readahead nhiều trang; một minor fault có thể chỉ cập nhật bảng trang mà không đọc thiết bị. Ngược lại, thao tác read/pread có thể đọc dữ liệu từ thiết bị mà không làm tăng số **file-backed page faults của vùng mmap** theo cùng cách.

Do đó, để đánh giá dữ liệu ngoài bộ nhớ, cần nhìn đồng thời **thời gian, số byte I/O, page faults, cache và số mục hữu ích được xử lý**.

## 13. Phân tích hai kịch bản lựa chọn cấu trúc

### Kịch bản A: chỉ mục từ điển bất biến

Một từ điển có 10 triệu khóa, cập nhật mỗi đêm bằng cách tạo phiên bản mới. Ban ngày hàng trăm tiến trình chủ yếu đọc.

Thiết kế có thể phù hợp:

1. Tạo dữ liệu ở định dạng có thứ tự và **cấu trúc chỉ mục** (B+-tree, block index hoặc bảng băm theo trang).
2. Xuất bản tệp **bất biến** với metadata phiên bản và checksum.
3. Các tiến trình dùng mmap ở chế độ chỉ đọc để truy cập chỉ mục và data block.
4. Khi cập nhật, tạo tệp mới rồi chuyển sang phiên bản mới; các reader cũ giữ ánh xạ với phiên bản cũ đến khi đọc xong.

**Vì sao hợp lý?** Các trang chỉ đọc có thể được dùng chung trong page cache; không có writer tự ý truncate tệp đang đọc; bộ chỉ mục giúp giảm số trang cần chạm. Với truy vấn phân bố rộng hơn RAM, vẫn phải tính cache miss và I/O ngẫu nhiên.

### Kịch bản B: ghi hàng triệu cập nhật nhỏ mỗi phút

Ứng dụng cập nhật nhiều khóa nhỏ, có yêu cầu nhất quán sau crash. Chỉ mmap một tệp lớn rồi sửa trực tiếp từng trường không giải quyết được:

- Ghi bền của từng cập nhật;
- Cập nhật đồng thời và xung đột;
- Ghi vật lý theo trang;
- Tính nguyên tử khi sửa nhiều vị trí;
- Chi phí giữ trang bẩn và writeback.

Một **B+-tree có WAL và buffer pool** hoặc kiến trúc **LSM-tree với MemTable + WAL + SSTable + compaction** là lựa chọn cần nghiên cứu theo tỷ lệ đọc/ghi và yêu cầu nhất quán. Cả hai vẫn có thể dùng mmap trong một số thành phần, nhưng **cấu trúc và giao thức cập nhật** mới quyết định ngữ nghĩa đúng và chi phí I/O thực.

## 14. Bài tập tự kiểm tra có lời giải

### Bài 1 — Số trang bị chạm

Hệ thống dùng trang 4096 byte. Một thao tác đọc 64 byte bắt đầu ở offset 4090. Ít nhất bao nhiêu trang hệ điều hành chứa đoạn dữ liệu này?

**Đáp án:** Đoạn đọc chứa byte 4090..4153 nên giao với trang 0 (0..4095) và trang 1 (4096..8191): **2 trang**. Nếu cả hai đã nằm trong RAM, không nhất thiết phát sinh I/O thiết bị.

### Bài 2 — Lượng RAM khi mmap

Một tiến trình ánh xạ tệp 64 GiB nhưng chỉ đọc 8 MiB. Có kết luận tiến trình đã dùng 64 GiB RAM không?

**Đáp án:** **Không.** 64 GiB là kích thước vùng địa chỉ ảo được ánh xạ, không mặc nhiên là RAM resident. Lượng bộ nhớ thực phụ thuộc các trang đã chạm, readahead, cache, bảng trang và bộ nhớ do ứng dụng dùng thêm.

### Bài 3 — Minor fault có phải I/O?

Một trang tệp đã nằm trong page cache nhờ tiến trình khác đọc trước. Tiến trình mới mmap tệp rồi chạm trang đó, phát sinh minor fault. Có phải kernel nhất định đọc SSD lần nữa?

**Đáp án:** **Không.** Kernel có thể chỉ thiết lập ánh xạ tới trang đang có trong RAM. Minor fault vẫn tốn xử lý, nhưng không cần đọc lại trang từ thiết bị trong trường hợp này.

### Bài 4 — Tìm kiếm nhị phân trên file mmap

Một tệp đã sắp có 1 triệu khóa. Tìm nhị phân mất khoảng 20 phép so sánh. Nếu các trang chưa được cache và những vị trí thử ở các trang xa nhau, có thể coi chi phí đọc thiết bị là O(1) chỉ vì dùng mmap không?

**Đáp án:** **Không.** Mmap không làm các lần truy cập trang ngẫu nhiên trở thành miễn phí. Số trang bị chạm có thể theo bậc O(log N) đối với tìm kiếm nhị phân trên mảng, trước khi xét cache và readahead. Muốn giảm I/O cần tổ chức chỉ mục theo trang, chẳng hạn B+-tree hoặc block index.

### Bài 5 — Ghi dữ liệu và mất điện

Ứng dụng sửa hai trang của một chỉ mục bằng MAP_SHARED rồi gọi msync cho cả hai. Có chắc cấu trúc sẽ luôn ở trạng thái cũ hoặc mới hoàn chỉnh nếu mất điện giữa quá trình ghi không?

**Đáp án:** **Không.** Đồng bộ dữ liệu theo trang không tự tạo giao dịch nguyên tử giữa nhiều trang. Cần WAL/copy-on-write và giao thức commit/phục hồi có quy tắc ghi bền phù hợp.

### Bài 6 — Cắt ngắn tệp

Tiến trình A mmap một tệp, tiến trình B truncate tệp xuống ngắn hơn. Khi A truy cập vào phần không còn thuộc tệp, điều gì có thể xảy ra trên hệ POSIX?

**Đáp án:** Có thể nhận **SIGBUS** và tiến trình bị kết thúc nếu không xử lý tín hiệu. Thiết kế nên tránh truncate tệp còn reader mmap; dùng tệp bất biến hoặc đồng bộ vòng đời writer/reader.

### Bài 7 — Chọn mmap hay buffer

Một dịch vụ đọc tệp đã sắp 100 GiB, chỉ có 2 GiB RAM trống. Truy vấn rải rác trên gần toàn bộ tệp; mỗi truy vấn đọc một vài byte. Dùng mmap liệu có đảm bảo hiệu năng cao?

**Đáp án:** **Không.** Working set lớn hơn RAM có thể làm cache thrash, sinh page faults và I/O ngẫu nhiên. Cần đo đặc điểm truy cập, xây chỉ mục giảm số trang, cân nhắc cache theo ứng dụng, chia vùng/partition và so mmap với pread có buffer.

### Bài 8 — Thiết kế định dạng file

Vì sao không nên lưu con trỏ tuyệt đối hoặc struct C/C++ có padding tùy compiler vào tệp rồi mmap ở chương trình khác?

**Đáp án:** Địa chỉ ánh xạ có thể thay đổi; alignment, padding, kích thước kiểu và endianness có thể khác. Nên dùng **offset tương đối**, định dạng nhị phân có phiên bản, kích thước trường cố định và kiểm tra biên.

## 15. Checklist khi thiết kế hệ thống dùng mmap

Trước khi chọn ánh xạ tệp, cần trả lời:

1. **Tệp có bất biến trong khi đọc không?** Nếu không, writer/reader phối hợp ra sao khi ghi chồng, đổi tên hoặc truncate?
2. **Working set và RAM là bao nhiêu?** Dữ liệu thường được chạm có lớn hơn page cache còn khả dụng không?
3. **Mẫu truy cập là tuần tự, theo khoảng hay ngẫu nhiên?** Có chỉ mục giảm số trang phải đọc không?
4. **Trang đã cache hay chưa?** Benchmark phải đo cả trường hợp nóng và lạnh, cùng chi phí I/O thực.
5. **Có sửa dữ liệu không?** Nếu có, dùng shared hay private mapping và cần đồng bộ, phục hồi thế nào?
6. **Cập nhật nhiều trang có cần nguyên tử?** Nếu có, thiết kế WAL/copy-on-write và giao thức commit thay vì chỉ gọi msync.
7. **Định dạng tệp có bền vững qua tiến trình/nền tảng không?** Dùng offset, phiên bản, endianness, checksum và kiểm tra biên.
8. **Quản lý vòng đời mapping thế nào?** Ai đảm bảo tệp còn hợp lệ, ai đóng mapping, ai bảo vệ reader khỏi tệp bị thay đổi?
9. **Tải có nhiều tiến trình/luồng không?** Dùng đồng bộ phù hợp và đo contention, page cache, bộ nhớ thực.
10. **Chỉ số quan trọng nhất là gì?** Độ trễ p99, throughput, RAM, byte I/O, khả năng phục hồi hay sự đơn giản khi triển khai?

**Điểm cần nhớ:** Ánh xạ tệp biến nội dung tệp thành một vùng địa chỉ ảo thuận tiện để truy cập. Nó có thể giảm sao chép dữ liệu và giúp tận dụng page cache dùng chung. Nhưng **page fault, I/O thiết bị, tính cục bộ, RAM vật lý, dirty writeback, đồng bộ, phục hồi và bất biến của cấu trúc dữ liệu** vẫn quyết định tính đúng và hiệu năng. Hãy chọn mmap như một **cơ chế truy cập**, đồng thời thiết kế chỉ mục, thuật toán, bộ đệm và quy tắc cập nhật theo tải công việc thực tế.
