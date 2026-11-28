# Đánh đổi giữa nén, truy cập ngẫu nhiên và cập nhật

## 1. Vì sao biểu diễn càng gọn chưa chắc càng hiệu quả?

Trong các bài về mảng, danh sách liên kết, bảng băm, cây, heap và đồ thị, ta đã quen với những câu hỏi: thao tác có đúng không, tốn bao nhiêu thời gian, và cần bao nhiêu bộ nhớ? Với chương **Biểu diễn gọn**, cần thêm một câu hỏi: **để tiết kiệm một lượng byte, ta phải trả giá bằng bao nhiêu phép giải mã, lần truy cập bộ nhớ hoặc lần ghi lại dữ liệu?**

Giả sử một dịch vụ lưu **1 triệu giá trị cảm biến**, mỗi giá trị nằm trong khoảng từ 0 đến 4095. Cách đơn giản nhất là cấp cho mỗi giá trị một số nguyên 32 bit, tổng cộng **4.000.000 byte** dữ liệu thô. Vì giá trị chỉ cần **12 bit**, một dãy đóng gói bit có thể lưu cùng dữ liệu trong **1.500.000 byte**, tiết kiệm **62,5%** trước khi tính metadata.

Nhưng tiết kiệm dung lượng mới là một nửa câu chuyện:

- Nếu cần lấy phần tử thứ 723.456, có thể tính trực tiếp vị trí bit của nó không?
- Nếu sử dụng nén theo khối, có phải đọc và giải nén cả khối chỉ để lấy một giá trị?
- Nếu thay giá trị ở giữa bằng số lớn hơn, liệu các phần tử phía sau có phải dịch chuyển?
- Nếu có hàng triệu lần đọc và ghi xen kẽ, chi phí CPU và I/O có thể lớn hơn khoản dung lượng tiết kiệm không?

**Định hướng của bài:** so sánh các cách biểu diễn qua ba trục **mức nén**, **truy cập ngẫu nhiên** và **cập nhật**. Đây là bài học về lựa chọn cấu trúc dữ liệu theo tải công việc, không phải bảng xếp hạng một thuật toán nén tốt nhất cho mọi trường hợp.

## 2. Đặt bài toán và thước đo trước khi chọn kỹ thuật

### 2.1. Những yếu tố phải đo

Cho một tập có **n** phần tử. Các thước đo thường dùng:

| Thước đo | Ý nghĩa | Điều dễ bị bỏ sót |
| --- | --- | --- |
| **Dung lượng lưu trữ** | Byte dữ liệu đã mã hóa cộng chỉ mục, header và metadata | Chỉ báo kích thước phần mã hóa mà quên chi phí tra cứu |
| **Bit/phần tử (bits per value)** | Tổng số bit chia cho n | Bị ảnh hưởng bởi header, padding, chỉ mục và phân bố dữ liệu |
| **Truy cập ngẫu nhiên** | Thời gian lấy phần tử có chỉ số i hoặc khóa k | Có thể cần giải nén cả khối hoặc đi từ điểm kiểm tra |
| **Quét tuần tự** | Thời gian duyệt nhiều phần tử liền nhau | Giải mã theo khối có thể nhanh nhờ tính cục bộ và SIMD |
| **Cập nhật** | Chi phí sửa/chèn/xóa một mục | Thay đổi độ dài mã hoặc phá mô hình nén có thể gây viết lại |
| **RAM phụ trợ** | Bộ đệm giải nén, từ điển, bảng offset, cache | Dung lượng trên đĩa nhỏ chưa chắc tổng RAM nhỏ |
| **I/O** | Số khối và byte đọc/ghi vật lý | Một lần tra 8 byte có thể kéo theo đọc hàng KiB |
| **Độ trễ p95/p99** | Độ trễ ở các phân vị cao | Tái nén, compaction, cache miss có thể gây đột biến |

Một cách ghi rõ tỷ lệ tiết kiệm là:

\[
\text{Tỷ lệ tiết kiệm} = 1-\frac{S_{\text{compressed,total}}}{S_{\text{baseline}}}.
\]

Ở đây **S_compressed,total** bao gồm *cả* dữ liệu nén, chỉ mục, từ điển, header và phần căn chỉnh cần để sử dụng cấu trúc. Nếu chỉ tính payload nén, ta có thể đánh giá quá lạc quan.

**Ví dụ:** payload chiếm 1,5 MB, chỉ mục và header thêm 0,2 MB, biểu diễn gốc 4 MB. Tỷ lệ tiết kiệm thực là **1 − 1,7/4 = 57,5%**, thấp hơn 62,5% khi bỏ qua metadata.

### 2.2. Độ phức tạp CPU và độ phức tạp I/O là hai chuyện khác nhau

Trong RAM, một phép lấy phần tử của mảng có thể là **O(1)**. Khi dữ liệu nén nằm trên SSD/HDD, một truy vấn còn gồm các bước:

~~~text
Tìm vị trí mã hóa -> nạp trang/khối -> giải mã -> trả phần tử
       CPU              I/O             CPU
~~~

Nếu dãy đã nằm trong bộ đệm, chi phí giải mã có thể quyết định hiệu năng. Nếu bộ dữ liệu quá lớn và phải liên tục đọc SSD, **giảm byte I/O nhờ nén** có thể làm hệ thống nhanh hơn dù CPU phải giải mã thêm.

Vì vậy, khi phát biểu **O(1)** hay **O(log n)**, phải nói rõ đang đếm phép toán trong RAM, số byte giải mã hay số trang thiết bị cần truy cập.

## 3. Biểu diễn độ dài cố định: nền tảng của truy cập ngẫu nhiên

### 3.1. Mảng số nguyên 32 bit

Với các số 0 đến 4095, biểu diễn 32 bit có **20 bit thừa** trên mỗi giá trị nhưng rất dễ truy cập:

\[
\text{byte\_offset}(i)=4i.
\]

Khi dùng chỉ số hợp lệ, phần tử i ở vị trí xác định; không phải đọc các giá trị đứng trước. Các thao tác đọc/ghi một phần tử có thể có chi phí logic **O(1)**.

Ưu điểm là đơn giản, thuận lợi cho CPU và có thể cập nhật tại vị trí cố định. Nhược điểm là tốn nhiều byte, có thể làm giảm số phần tử chứa được trong cache của CPU hoặc RAM.

### 3.2. Bit packing: giữ độ dài mã cố định nhưng giảm số bit

Nếu giá trị lớn nhất là **M**, số bit tối thiểu để biểu diễn mọi số nguyên không âm trong miền **[0, M]** là:

\[
w=\lceil\log_2(M+1)\rceil.
\]

Với M = 4095, ta có w = 12. Đóng gói liên tiếp n giá trị, không căn mỗi giá trị tới biên byte:

\[
S_{\text{payload}}=\left\lceil\frac{nw}{8}\right\rceil\text{ byte}.
\]

Phần tử thứ i (đánh số từ 0) bắt đầu tại:

\[
\text{bit\_offset}(i)=i\,w,
\quad
\text{byte\_offset}(i)=\lfloor iw/8\rfloor,
\quad
\text{shift}(i)=iw\bmod 8.
\]

Một phần tử có thể nằm vắt qua hai hoặc nhiều byte. Tuy nhiên, **vẫn tính được vị trí trực tiếp**, nên lấy phần tử có chi phí O(1) trong mô hình RAM với **w cố định** và độ rộng số máy đủ để xử lý thao tác.

~~~text
5 giá trị 4-bit:  3, 9, 12, 0, 7

Dữ liệu logic:
[0011] [1001] [1100] [0000] [0111]    20 bit

Dữ liệu lưu:
20 bit được xếp liên tiếp trong 3 byte (24 bit),
4 bit cuối là padding.
~~~

Ở mức máy, muốn sửa một giá trị 12 bit, chương trình có thể phải **đọc–sửa–ghi** các byte hoặc từ máy chứa bit tương ứng; cần mask đúng để giữ nguyên các phần tử lân cận. Khi có ghi đồng thời, các giá trị nằm chung một từ máy còn có thể tranh chấp và cần thao tác nguyên tử/khóa phù hợp.

**Bất biến:** tất cả giá trị phải nằm trong khoảng có thể biểu diễn bằng w bit, mọi phần tử đều chiếm đúng w bit, và thứ tự bit/byte được định nghĩa nhất quán.

### 3.3. Ví dụ Python: đóng gói bit và truy cập trực tiếp

Đoạn mã sau minh họa cách đóng gói các số nguyên không âm theo **thứ tự bit thấp trước** trong luồng byte. Đây là ví dụ học tập, chưa phải bộ mã hóa tối ưu SIMD hay định dạng tệp hoàn chỉnh.

~~~python
def pack_fixed_width(values: list[int], width: int) -> bytes:
    if not 1 <= width <= 32:
        raise ValueError("width phải trong khoảng 1..32")

    limit = 1 << width
    output = bytearray()
    buffer = 0
    buffered_bits = 0

    for value in values:
        if not 0 <= value < limit:
            raise ValueError("Giá trị nằm ngoài miền biểu diễn")

        buffer |= value << buffered_bits
        buffered_bits += width

        while buffered_bits >= 8:
            output.append(buffer & 0xFF)
            buffer >>= 8
            buffered_bits -= 8

    if buffered_bits:
        output.append(buffer & 0xFF)

    return bytes(output)


def get_fixed_width(
    packed: bytes, index: int, width: int, count: int
) -> int:
    if not 1 <= width <= 32:
        raise ValueError("width không hợp lệ")
    if not 0 <= index < count:
        raise IndexError("Chỉ số ngoài miền")

    first_bit = index * width
    first_byte = first_bit // 8
    shift = first_bit % 8
    byte_count = (shift + width + 7) // 8
    end = first_byte + byte_count

    if end > len(packed):
        raise ValueError("Dữ liệu đóng gói bị thiếu")

    chunk = int.from_bytes(packed[first_byte:end], "little")
    mask = (1 << width) - 1
    return (chunk >> shift) & mask


values = [3, 9, 12, 0, 7]
payload = pack_fixed_width(values, width=4)

assert len(payload) == 3
assert [get_fixed_width(payload, i, 4, len(values))
        for i in range(len(values))] == values
~~~

Để lưu thành tệp, còn phải lưu **count**, **width**, phiên bản định dạng và kiểm tra tính hợp lệ khi đọc. Mã sử dụng chỉ số phần tử để tìm trực tiếp vài byte chứa nó: **không phải giải mã các phần tử từ đầu dãy**.

### 3.4. Khi nào bit packing bắt đầu bất lợi?

- Nếu xuất hiện giá trị **lớn hơn 2^w − 1**, không thể đưa nó vào cùng độ rộng w nếu không dùng escape/overflow structure hoặc đổi độ rộng của dãy/khối.
- Các phần tử không nhất thiết thẳng hàng với biên byte hoặc từ máy, nên mã đọc/ghi có thể phức tạp hơn.
- Cập nhật đồng thời các giá trị chia sẻ một từ máy cần thận trọng để không ghi đè bit của nhau.
- Với giá trị rất nhỏ nhưng thay đổi mạnh theo vùng, một w chung cho cả dãy có thể lãng phí; **đóng gói theo khối với w riêng** thường tốt hơn nhưng tạo thêm metadata.

## 4. Mã độ dài biến đổi: tiết kiệm hơn có thể khiến việc tìm vị trí khó hơn

### 4.1. Varint

**Varint** mã hóa số nguyên bằng số byte phụ thuộc độ lớn. Một kiểu phổ biến dùng 7 bit dữ liệu và 1 bit tiếp diễn mỗi byte; số nhỏ chiếm ít byte, số lớn chiếm nhiều byte.

Ví dụ ở dạng khái niệm:

~~~text
Giá trị nhỏ   -> [1 byte]
Giá trị vừa   -> [2 byte]
Giá trị lớn   -> [3 byte hoặc hơn]
~~~

Nếu có n số được nối liên tục theo kiểu độ dài biến đổi, **vị trí byte của phần tử i** không còn đơn giản là i × một hằng số. Nếu chỉ biết đầu luồng, muốn tới phần tử i có thể phải quét và giải mã độ dài của **i phần tử trước**, chi phí O(i) trong trường hợp không có chỉ mục.

~~~text
[phần tử 0][phần tử 1......][phần tử 2][phần tử 3...]
  1 byte       3 byte           1 byte      2 byte

Để tìm đầu phần tử 3, phải biết tổng độ dài các mã 0..2.
~~~

Đây là một đánh đổi nền tảng: **mã càng linh hoạt về độ dài, xác định điểm bắt đầu của phần tử càng cần thêm thông tin**.

### 4.2. Delta encoding

Nếu dãy số **không giảm**, có thể lưu giá trị gốc và hiệu giữa hai giá trị liên tiếp:

~~~text
Dãy gốc:   1000, 1002, 1003, 1007, 1008
Base:      1000
Delta:        2,    1,    4,    1
~~~

Khi hiệu nhỏ, kết hợp delta với varint hoặc bit packing có thể nén tốt hơn lưu từng giá trị lớn.

Tuy nhiên, nếu chỉ có **base** và một luồng delta, để tính **giá trị thứ i** ta cần cộng dồn:

\[
x_i=x_0+\sum_{j=1}^{i}\Delta_j.
\]

Nếu không có thông tin phụ trợ, truy cập phần tử ở xa có thể cần giải mã nhiều delta, trong trường hợp xấu là O(n). Thứ tự và cách mã hóa phải giữ cho phép cộng dồn khôi phục đúng dữ liệu (kể cả trường hợp delta bằng 0 do khóa trùng).

### 4.3. Checkpoint hoặc điểm neo (anchor)

Cách khắc phục là **lưu giá trị tuyệt đối và byte offset tại các vị trí định kỳ**.

Nếu đặt checkpoint mỗi **k** phần tử, tìm phần tử i bằng cách:

1. Xác định checkpoint ở vị trí **j = floor(i/k) × k**.
2. Lấy **x_j** và offset của luồng delta tại j.
3. Giải mã tối đa **k − 1** delta tiếp theo để tới i.

~~~text
Checkpoint:     x0               x4               x8
                   |                |                |
Dữ liệu:        x0 d1 d2 d3 d4  d5 d6 d7 d8  d9 ...
                   ^        ^       ^        ^
                Có điểm neo nên không cần quét từ đầu dãy.
~~~

Với quy tắc biểu diễn nhất quán và checkpoint truy cập trực tiếp:

- Số checkpoint khoảng **ceil(n/k)**, chi phí metadata **O(n/k)**.
- Thời gian giải mã từ checkpoint tới phần tử đích tối đa **O(k)**.
- Nếu k nhỏ, truy cập nhanh nhưng chỉ mục lớn.
- Nếu k lớn, chỉ mục nhỏ nhưng phải giải mã nhiều hơn.

**Chú ý:** Nếu checkpoint lưu **offset byte** thì nó giúp định vị điểm bắt đầu trong luồng mã độ dài biến đổi; chỉ lưu giá trị tuyệt đối mà không lưu cách tìm byte offset vẫn có thể phải quét luồng để tìm checkpoint.

### 4.4. Khi sửa một phần tử trong dãy delta

Sửa **x_i** thành giá trị mới có thể làm thay đổi delta tại i và i+1, nhưng cần kiểm tra **bất biến thứ tự**. Với dãy tăng và các khoảng cách không âm, nếu x_i mới vượt x_{i+1} hoặc thấp hơn x_{i-1}, cách biểu diễn monotone không còn hợp lệ.

Hơn nữa, mã delta theo varint có **độ dài biến đổi**. Chỉ thay hai delta có thể khiến số byte tăng hoặc giảm, kéo theo việc di chuyển byte và cập nhật offset của nhiều checkpoint phía sau nếu luồng nén được lưu liên tục. Trong định dạng chia khối, chi phí có thể giới hạn vào một khối cùng metadata liên quan.

**Không nên kết luận** mọi cập nhật delta làm thay đổi tất cả delta đứng sau: trong biểu diễn delta bậc một, sửa một giá trị nội bộ về mặt logic chỉ thay hai khoảng cách lân cận; **việc dịch chuyển byte của luồng mã** mới là nguồn chi phí mở rộng.

## 5. Run-Length Encoding: nén theo các đoạn bằng nhau

**RLE** (Run-Length Encoding) lưu dãy các cặp **(giá trị, số lần lặp)** thay cho mọi phần tử.

~~~text
Dãy gốc:
A A A A A B B C C C C C C

RLE:
(A,5), (B,2), (C,6)
~~~

Nếu dãy có nhiều đoạn dài cùng giá trị, RLE có thể nén rất tốt. Nếu dữ liệu thay đổi liên tục, có thể có gần **n đoạn**, và metadata số lần lặp khiến RLE tốn chỗ hơn dãy gốc.

### Truy cập ngẫu nhiên trong RLE

Để lấy **a[i]**, phải tìm run chứa vị trí i. Nếu lưu thêm **vị trí kết thúc tích lũy** của từng run:

| Run | Giá trị | Độ dài | Vị trí kết thúc (exclusive) |
| --- | --- | ---: | ---: |
| 0 | A | 5 | 5 |
| 1 | B | 2 | 7 |
| 2 | C | 6 | 13 |

Vị trí i = 8 thuộc run đầu tiên có **end > 8**, tức run 2 mang giá trị C. Tìm nhị phân trong dãy các **run end** có độ phức tạp **O(log r)** với r run, nếu index nằm trong RAM. Nếu không có chỉ mục, có thể phải quét O(r) run.

**Trường hợp đặc biệt:** với biểu diễn RLE có các cấu trúc chỉ mục chuyên biệt, có thể hỗ trợ một số phép toán nhanh hơn; O(log r) ở đây là đặc điểm của lựa chọn index đơn giản đã mô tả.

### Cập nhật một phần tử có thể tách hoặc gộp run

Ví dụ thay phần tử ở giữa dãy A thành B:

~~~text
Trước: A A A A A
Sau:   A A B A A

RLE trước: (A,5)
RLE sau:   (A,2), (B,1), (A,2)
~~~

Một thay đổi duy nhất tạo ba run từ một run. Nếu ghi nhiều thay đổi rải rác, số run tăng nhanh, tỷ lệ nén xấu đi và phải sửa chỉ mục vị trí kết thúc. Ngược lại, thay phần tử ở ranh giới có thể làm hai run cùng giá trị nhập lại.

**RLE hợp với dữ liệu có những khoảng lặp dài và ít sửa phân tán**, chẳng hạn bitmap trạng thái, cột dữ liệu ít thay đổi theo thứ tự, hoặc chuỗi sự kiện nhóm theo loại.

## 6. Dictionary encoding: thay giá trị dài bằng mã ngắn

Khi nhiều giá trị lặp lại, ta có thể lưu một **từ điển giá trị duy nhất** và một dãy mã định danh:

~~~text
Dữ liệu:     ["Hà Nội", "Huế", "Hà Nội", "Đà Nẵng", "Huế"]

Từ điển:
0 -> "Hà Nội"
1 -> "Huế"
2 -> "Đà Nẵng"

Dãy mã:      [0, 1, 0, 2, 1]
~~~

Nếu từ điển có **d** giá trị phân biệt, mã có thể dùng độ rộng cố định:

\[
w=\lceil\log_2 d\rceil\text{ bit},
\]

với trường hợp d = 1 có thể dùng mã rộng 0 bit ở mô hình lý thuyết kèm metadata phù hợp, hoặc dùng ít nhất một bit cho triển khai đơn giản. Từ điển cần được lưu hoặc chia sẻ cho các khối.

Truy cập **phần tử i** có thể thực hiện qua hai bước:

1. Tìm mã ở vị trí i từ dãy mã cố định (O(1) trong RAM).
2. Tra giá trị trong từ điển theo mã (O(1) nếu từ điển là mảng truy cập trực tiếp).

Như vậy, **dictionary encoding không mặc nhiên làm mất khả năng truy cập ngẫu nhiên O(1)**.

### Đánh đổi khi cập nhật

- Thay một mục từ giá trị đã có trong từ điển sang giá trị khác đã có: chỉ cần đổi mã, thường dễ.
- Thêm một giá trị mới: phải bổ sung từ điển. Nếu số lượng mã vượt sức chứa của w bit, có thể phải **mở rộng độ rộng mã** hoặc dùng cơ chế ngoại lệ.
- Thường xuyên thêm giá trị phân biệt: từ điển có thể phình to, làm giảm hiệu quả nén.
- Từ điển toàn cục được chia sẻ giúp tránh lặp metadata, nhưng cập nhật và đồng bộ từ điển phức tạp hơn. Từ điển theo khối linh hoạt hơn và dễ xây lại một khối, nhưng tốn metadata lặp.

Khi dữ liệu là cột chuỗi lặp nhiều lần, dictionary encoding thường đáng thử; khi phần lớn giá trị đều duy nhất, từ điển có thể không bù được chi phí lưu mã.

## 7. Nén theo khối: giới hạn phần dữ liệu cần giải mã và viết lại

Một cách dung hòa phổ biến là chia n phần tử thành các **khối (block/chunk)**, mỗi khối gồm tối đa **B** phần tử, có thể nén độc lập. Mỗi khối có metadata như offset, độ dài nén, số phần tử, codec và thông tin giải mã.

~~~text
            Index: block_id -> (offset, compressed_length, ...)
                         |
      +------------------+--------------------+
      |                  |                    |
      v                  v                    v
 [Block 0]           [Block 1]            [Block 2]
  256 giá trị         256 giá trị          256 giá trị
  được nén            được nén             được nén
  độc lập             độc lập              độc lập

Truy vấn a[600]:
    block_id = floor(600 / 256) = 2
    local_index = 600 % 256 = 88
    -> chỉ cần định vị và giải mã Block 2.
~~~

Đối với mảng vị trí có **B cố định**, có thể tính trực tiếp **block_id = floor(i/B)**. Nếu các khối có số phần tử biến đổi, chỉ mục cần lưu **vị trí bắt đầu/kết thúc theo số phần tử** để chọn khối bằng tìm kiếm phù hợp.

### 7.1. Mã giả truy cập

~~~text
function get_from_compressed_blocks(index, i):
    assert 0 <= i < index.total_items

    block_id = floor(i / index.items_per_block)
    local = i % index.items_per_block

    entry = index.block_entries[block_id]
    raw = read_bytes(entry.offset, entry.compressed_length)
    decoded = decompress(raw, entry.codec)

    assert decoded.item_count == entry.item_count
    return decoded[local]
~~~

Mã giả dùng mô hình **mỗi block có B vị trí ngoại trừ block cuối**. Nếu block được cache ở dạng đã giải mã, lần tra tiếp theo vào cùng block có thể bỏ qua đọc và giải nén. Nếu codec hỗ trợ **truy cập trực tiếp vào giá trị nén** như bit packing độ rộng cố định, không nhất thiết phải giải mã toàn bộ khối; mã giả trên mô tả codec **giải nén theo khối**.

### 7.2. Chỉ mục offset tốn bao nhiêu?

Giả sử **1.000.000** giá trị, chia theo khối **256 phần tử**, dùng một entry index gồm offset 8 byte và độ dài khối 8 byte:

~~~text
Số khối = ceil(1.000.000 / 256) = 3.907
Index tối thiểu = 3.907 * 16 = 62.512 byte
               ≈ 61,05 KiB
~~~

Chỉ mục này nhỏ hơn nhiều so với bảng offset 4 byte cho **từng phần tử**, vốn cần 4.000.000 byte.

Tuy nhiên, bảng offset 4 byte chỉ đủ nếu offset vào vùng lưu trữ nằm trong miền biểu diễn đó; file lớn hơn hoặc kiểu offset khác đòi thêm byte. Chỉ mục thực còn có header, alignment, checksum hoặc các trường khác.

### 7.3. Chọn B: khối nhỏ hay khối lớn?

| Khối nhỏ | Khối lớn |
| --- | --- |
| Truy cập một phần tử thường phải giải mã ít dữ liệu hơn | Thường nén tốt hơn vì có nhiều mẫu lặp/dự đoán hơn |
| Cập nhật có thể chỉ viết lại khối nhỏ | Viết lại một khối lớn có thể tốn CPU và I/O hơn |
| Số khối nhiều, chỉ mục lớn hơn | Ít entry index, metadata nhỏ hơn |
| Nhiều header, tỷ lệ nén có thể thấp | Thuận lợi cho quét tuần tự và đọc trước |
| Có thể giảm áp lực cache khi point lookup rất rải rác | Có thể lãng phí đọc/giải nén nếu chỉ lấy một phần tử |

Không có B tối ưu cho mọi tải. Khối nén **64 KiB** có thể hợp với quét cột dữ liệu; khối nhỏ hơn có thể tốt với point lookup ngẫu nhiên. Kết quả còn phụ thuộc codec, kích thước trang thiết bị, cache và vùng khóa nóng.

### 7.4. Khối có thể thay đổi độ dài sau cập nhật

Giả sử khối 5 nén từ 4096 byte xuống 1500 byte. Sau khi sửa một giá trị, khối mới cần 1700 byte. Nếu các khối được xếp liền nhau **không có vùng trống**, không thể ghi đè nguyên khối mà không dịch vùng sau nó.

Các cách xử lý gồm:

- Cấp phát khối mới ở chỗ khác, đổi offset trong index, rồi thu hồi khối cũ sau khi an toàn.
- Dành **vùng trống dự phòng** cho các khối nếu định dạng cho phép.
- Gom nhiều thay đổi vào bộ đệm, định kỳ nén lại khối.
- Dùng tệp bất biến hoặc các đoạn append và **compaction** để dọn dữ liệu cũ.

Mỗi lựa chọn đổi chi phí cập nhật lấy dung lượng trống, chỉ mục lớn hơn hoặc công việc nền. Cần tính **write amplification** của toàn hệ thống, không chỉ thời gian chạy hàm nén.

## 8. Truy cập ngẫu nhiên: “một phần tử” có thể cần giải mã bao nhiêu?

Xét ba đại diện:

**A. Mảng 32 bit cố định:**

~~~text
offset(i) = 4*i
đọc 4 byte (về mặt logic) -> giá trị
~~~

**B. Bit packing độ rộng 12 bit:**

~~~text
bit_offset(i) = 12*i
đọc vài byte chứa 12 bit -> mask/shift -> giá trị
~~~

**C. Delta + varint với checkpoint mỗi 128 phần tử:**

~~~text
j = floor(i/128)*128
đọc checkpoint j
định vị offset mã hóa tại j
giải mã tối đa 127 delta để lấy i
~~~

Cả B và C đều có thể nén tốt hơn A, nhưng **chi phí truy cập của B và C khác nhau rất nhiều**. Với B, vị trí bit được tính trực tiếp. Với C, giải mã cần đi từ checkpoint đến mục yêu cầu.

Bảng tổng quát dưới đây giả định metadata cần thiết đã có trong RAM:

| Biểu diễn | Truy cập phần tử i | Chi phí phụ trợ để hỗ trợ truy cập |
| --- | --- | --- |
| Mảng cố định | O(1) | Thường không cần index riêng |
| Fixed-width bit packing | O(1) phép tính vị trí/mask | Độ rộng bit w, số phần tử |
| Varint nối liên tục, không index | O(i) trong trường hợp phải quét từ đầu | Rất nhỏ |
| Delta/varint + checkpoint mỗi k | O(k) giải mã từ điểm neo | O(n/k) checkpoint và offset |
| RLE với r run + mảng end | O(log r) tìm run | O(r) vị trí kết thúc |
| Dictionary + mã cố định | O(1) để lấy mã và tra từ điển | Từ điển + dãy mã |
| Block codec giải nén toàn khối B mục | O(1) định vị khối, thường O(B) giải mã | O(n/B) entry index, buffer cho khối |
| Bitvector với cấu trúc rank/select chuyên biệt | Phụ thuộc cấu trúc; có thiết kế gần O(1) trên mô hình word-RAM | Rank/select directories hoặc index đặc biệt |

Bảng không ngụ ý mọi codec “theo khối” đều bắt buộc giải mã O(B) để lấy một giá trị. Một số codec có toán tử truy cập trực tiếp hoặc thiết kế checkpoint trong khối, đem lại chi phí thấp hơn.

### Truy cập ngẫu nhiên theo khóa khác theo chỉ số

Lấy **a[i]** nghĩa là biết chỉ số phần tử. Tìm khóa **key = x** nghĩa là phải **xác định vị trí khóa**, có thể còn cần:

- Tìm kiếm nhị phân trên dãy đã sắp;
- Chỉ mục khối bằng khóa ranh giới;
- Cây B+-tree;
- Bảng băm;
- Một cấu trúc tối ưu riêng cho thứ tự hoặc từ điển.

Nén không tự tạo ra khả năng tìm theo khóa. Truy vấn theo khóa có chi phí **định vị khóa + giải mã**, còn truy cập theo chỉ số có thể bỏ được bước định vị bằng chỉ mục khóa.

## 9. Cập nhật: vì sao nén có thể làm sửa một phần tử trở nên đắt?

Giả sử dữ liệu gốc lưu theo cách một giá trị = một vùng byte cố định. Nếu sửa mà không đổi kích thước, thường có thể thay đúng vùng chứa giá trị (ở mức logic). Khi nén, một cập nhật có thể đụng tới nhiều đơn vị mã hóa.

### 9.1. Ghi đè giá trị có độ dài giữ nguyên

Với mảng fixed-width và giá trị mới vẫn vừa độ rộng w, offset các phần tử phía sau **không đổi**:

~~~text
Trước: [4][7][2][5]
Sau:   [4][3][2][5]
           ^
       sửa mã ở cùng vị trí
~~~

Có thể sửa tại chỗ sau khi mask/shift đúng. Nhưng vẫn phải xét:

- Các bit của phần tử khác nằm chung byte/từ máy;
- Atomicity và cập nhật đồng thời;
- Ghi trang bẩn, WAL hoặc đồng bộ ghi;
- Số byte vật lý được ghi lại có thể lớn hơn độ rộng của một mã.

**Cập nhật logic O(1) không đồng nghĩa với ghi vật lý đúng vài bit.**

### 9.2. Ghi đè làm thay đổi độ dài mã

Varint, Huffman và nhiều codec dựa trên entropy có **mã độ dài biến đổi**. Nếu mã mới dài hơn mã cũ, vùng sau đó phải dịch đi hoặc phải cấp phát nơi khác:

~~~text
Trước: [1B][1B][2B][1B]
Sau:   [1B][3B][2B][1B]
               ^
   mã thứ hai tăng 2 byte -> offset các mục phía sau thay đổi
~~~

Nếu tệp là một dòng byte nối liên tục, viết lại có thể ảnh hưởng phần lớn phía sau. Dùng block độc lập giúp giới hạn phạm vi dịch chuyển, nhưng có thể phải cấp phát một block mới và sửa block index.

### 9.3. Cập nhật ảnh hưởng đến ngữ cảnh nén

- **Delta:** thay một giá trị có thể thay hai delta lân cận và thay độ dài mã; nếu phá thứ tự tăng, cấu trúc phải đổi hoặc từ chối cập nhật.
- **RLE:** một giá trị có thể tách một run thành ba, hoặc làm hai run nhập lại.
- **Dictionary:** đổi sang giá trị đã có trong từ điển thường dễ; thêm giá trị mới có thể mở rộng từ điển/mã.
- **Nén khối bằng entropy:** thay một phần tử có thể buộc **giải nén và nén lại cả khối**, vì mã phụ thuộc phân bố và ngữ cảnh.

Những chi phí này là đặc tính của **cách bố trí dữ liệu**, không đơn thuần do codec giải mã “nhanh hay chậm”.

### 9.4. Chèn và xóa khác cập nhật

Khi **insert** vào giữa một dãy nén theo thứ tự, không chỉ độ dài mã thay đổi mà **chỉ số logic của nhiều phần tử phía sau** cũng đổi. Dù dùng độ rộng cố định, một mảng chặt vẫn có thể cần dịch nhiều bit/phần tử.

Với **delete**, xóa một mục có thể thu ngắn dãy và yêu cầu dịch dữ liệu. Hệ thống lưu trữ thường khắc phục bằng đánh dấu xóa (tombstone), cấu trúc cây/chunk, vùng trống hoặc viết tệp mới; sau đó tiến hành dọn dẹp.

Do đó phải phân biệt:

1. **Point update:** thay nội dung tại vị trí/khóa đã tồn tại;
2. **Insert/delete:** làm thay đổi số phần tử hoặc cấu trúc thứ tự;
3. **Append:** thêm cuối dãy, thường dễ tổ chức hơn;
4. **Bulk rebuild:** xây lại toàn bộ dãy khi cập nhật theo lô.

## 10. Tách vùng đọc tối ưu khỏi vùng ghi thường xuyên

Nếu dữ liệu nén có **rất nhiều truy vấn đọc** nhưng **ít cập nhật**, ta có thể chấp nhận thời gian nén ban đầu để tiết kiệm RAM/SSD và tăng tốc quét. Nếu có **nhiều cập nhật nhỏ**, viết lại khối liên tục có thể trở thành nút thắt.

Một mẫu thiết kế phổ biến là:

~~~text
                    UPDATE(key, new_value)
                              |
                              v
                 Delta buffer / overlay nhỏ
                    (RAM hoặc ghi append)
                              |
                +-------------+------------+
                |                          |
        GET(key) tra overlay          Đủ số thay đổi
        trước dữ liệu gốc                  |
                |                          v
                |                     Hợp nhất lại
                |                     các khối dữ liệu
                |                          |
                +--------------------------+
                                           v
                                   Base compressed blocks
                                   + chỉ mục mới
~~~

**Overlay** giữ những thay đổi mới; dữ liệu gốc vẫn nén gọn và có thể bất biến. Khi đọc, phải ưu tiên phiên bản mới nhất của khóa, đồng thời xử lý tombstone nếu khóa đã bị xóa.

Một số hệ thống sử dụng kiến trúc **LSM-tree**: ghi vào MemTable/WAL, flush thành các tệp đã sắp (SSTable), và compaction để hợp nhất phiên bản cũ. Đây là một cách chuyển **cập nhật ngẫu nhiên nhỏ** thành **ghi theo lô**, nhưng compaction làm tăng lượng byte đọc/ghi nền.

Một hướng khác là **chunk copy-on-write**:

1. Đọc khối chứa mục cần sửa;
2. Giải mã khối và áp dụng thay đổi;
3. Nén thành **khối mới**;
4. Cấp phát vị trí mới, cập nhật chỉ mục/metadata theo giao thức xuất bản an toàn;
5. Thu hồi khối cũ khi không còn reader cần nó.

Các giải pháp này đổi **bộ nhớ phụ trợ và công việc hợp nhất** lấy khả năng cập nhật mà không phải dịch toàn bộ tệp.

### Chi phí khuếch đại ghi (write amplification)

Đặt:

\[
WA=\frac{\text{byte ghi vật lý}}
        {\text{byte cập nhật logic}}.
\]

Ví dụ một cập nhật logic **8 byte** nhưng hệ thống ghi lại một block nén **2 KiB**:

\[
WA_{\text{minh họa}}=\frac{2048}{8}=256.
\]

Đó mới là phần **ghi block**; nếu còn WAL, metadata, checksum, bản sao tạm và compaction, tổng write amplification có thể lớn hơn. Mặt khác, nếu nhiều cập nhật rơi vào **cùng block** trước khi flush, chúng có thể được gom và chỉ viết lại một lần, làm giảm chi phí bình quân.

Không thể kết luận mọi hệ thống nén đều có WA = 256; ví dụ chỉ cho thấy vì sao **độ lớn đơn vị ghi lại** quan trọng.

## 11. Khi nén có thể tăng tốc, và khi nén gây chậm

### 11.1. Dữ liệu không vừa RAM: ít I/O có thể bù chi phí giải mã

Giả sử quét **800 MiB dữ liệu gốc** trên thiết bị, codec nén xuống **200 MiB**. Nếu bộ giải mã đủ nhanh, thời gian quét có thể giảm vì chỉ cần chuyển 1/4 lượng byte từ thiết bị vào RAM.

Có thể ước lượng thô:

\[
T_{\text{scan}}\approx
T_{\text{read compressed bytes}}+
T_{\text{decompress}}+
T_{\text{process}},
\]

nhưng trong hệ thống có pipeline, I/O và giải mã có thể **chồng lấn**, nên tổng thời gian thực không nhất thiết bằng tổng đơn giản. Để so sánh hợp lý cần đo throughput đọc, throughput giải mã và tài nguyên CPU.

### 11.2. Dữ liệu đã nằm trong RAM: giải mã có thể là chi phí chính

Nếu ứng dụng liên tục truy cập ngẫu nhiên vào một tập nhỏ đủ nằm trong cache, cách biểu diễn không nén có thể rất nhanh. Một codec cần giải nén cả khối cho mỗi lần đọc ngẫu nhiên có thể chậm hơn bit packing trực tiếp hoặc mảng cố định, dù tiết kiệm byte.

Tuy nhiên, dữ liệu nén **nhỏ hơn** có thể giúp nhiều phần tử nằm trong **CPU cache**, đôi khi vượt lợi ích của dạng không nén. Vì thế vẫn phải benchmark trên chính mẫu truy cập.

### 11.3. Truy cập có tính cục bộ hay không?

Giả sử mỗi block có B = 256 phần tử:

- Đọc 200 phần tử kề nhau: giải nén một hoặc hai block có thể rất hiệu quả.
- Đọc 200 phần tử nằm ở 200 block khác nhau: có thể phải giải nén 200 block, tạo nhiều byte giải mã thừa.

Đây là lý do cùng một codec có thể rất tốt cho **column scan** nhưng không phù hợp cho **point lookup rải rác**, trừ khi có cache block được giải mã hoặc đường đọc trực tiếp.

### 11.4. CPU, SIMD và khả năng song song

Một số codec như bit packing theo khối và các dạng integer compression có thể giải mã theo vector (SIMD) rất nhanh. Các codec phụ thuộc tuần tự vào giá trị trước có thể khó song song hơn nếu không có checkpoint hoặc chia block độc lập.

Không nên chỉ dựa vào tỷ lệ nén. Trong hệ thống đọc nhiều, **thông lượng giải mã (giá trị/giây)**, **độ trễ lấy một giá trị** và **RAM tạm** cũng là chỉ số quyết định.

## 12. Phân tích trường hợp số: 1 triệu giá trị 12 bit

Giả sử có n = **1.000.000** giá trị nguyên không âm, mỗi giá trị ≤ 4095.

### Phương án A: mỗi giá trị 32 bit

~~~text
1.000.000 * 4 byte = 4.000.000 byte
                   ≈ 3,81 MiB
~~~

Ưu điểm là offset dễ tính, đọc/ghi một phần tử thuận lợi. Không cần bảng block offset khi dãy lưu liên tục.

### Phương án B: fixed-width bit packing toàn dãy

~~~text
1.000.000 * 12 bit / 8 = 1.500.000 byte
                       ≈ 1,43 MiB
Tiết kiệm so với A: 62,5%
~~~

Phần tử thứ i vẫn có bit offset 12i. Nếu cần đổi giá trị từ 100 thành 3000, cả hai vẫn vừa 12 bit, có thể cập nhật tại đúng vị trí bit, với điều kiện ghi đúng mask và bảo toàn tính đồng thời.

**Giới hạn:** nếu xuất hiện giá trị 5000, nó không còn vừa 12 bit; phải có chính sách ngoại lệ hoặc chọn lại độ rộng mã.

### Phương án C: khối 256 phần tử + metadata

Giả sử mỗi block đóng gói 12 bit/phần tử, chỉ có thể nén riêng khối, và index có **16 byte/khối**:

~~~text
Số block = ceil(1.000.000 / 256) = 3.907
Dữ liệu đóng gói ≈ 1.500.000 byte
Index tối thiểu = 3.907 * 16    = 62.512 byte

Tổng sơ bộ ≈ 1.562.512 byte
            (chưa tính header, padding, checksum, codec)
~~~

Đổi lại, có thể nén lại từng block khi cần, và mỗi block có metadata riêng. Nếu codec thực sự là **fixed-width 12 bit trong khối**, vẫn có thể đọc trực tiếp vài byte khi đã biết offset đầu khối; **không bắt buộc** giải nén cả 256 phần tử.

Để so sánh với codec nén toàn khối như RLE hoặc một codec entropy, phải đo chính xác số byte nén, CPU giải mã và lượng dữ liệu phải sửa sau khi cập nhật.

### Một mẫu tải thực tế

Giả sử workload có:

- 90% truy cập đọc ngẫu nhiên từng phần tử;
- 8% cập nhật một phần tử đã có;
- 2% quét toàn bộ dãy.

Với giá trị luôn ≤ 4095, **bit packing cố định** là một ứng viên mạnh vì vừa giảm dung lượng vừa giữ khả năng định vị O(1). Một codec cần giải nén cả khối cho phần lớn truy vấn có thể gây nhiều CPU thừa. Nếu dữ liệu có các đoạn lặp rất dài và quét chiếm phần lớn, RLE hoặc nén khối có thể trở nên hấp dẫn hơn.

Quyết định cuối cùng vẫn cần đo **p95/p99 đọc ngẫu nhiên**, độ trễ cập nhật, byte ghi thực, CPU và RAM cache.

## 13. Phương pháp chọn biểu diễn theo tải công việc

### 13.1. Dữ liệu tĩnh, chủ yếu quét tuần tự

Ví dụ bảng phân tích cột lịch sử được xây một lần mỗi ngày và hiếm khi sửa giữa phiên bản.

**Ưu tiên khảo sát:** nén theo khối, delta, RLE hoặc dictionary tùy phân bố. Có thể đầu tư nén kỹ hơn vì chi phí xây dựng được phân bổ cho nhiều lần đọc. Chọn block đủ lớn để tăng tỷ lệ nén và thông lượng quét.

**Kiểm chứng:** throughput quét, tỷ lệ nén, I/O đọc, CPU decode và tốc độ xây bảng.

### 13.2. Đọc theo vị trí rải rác, yêu cầu độ trễ thấp

Ví dụ truy cập giá trị của một cảm biến tại chỉ số ngẫu nhiên hàng nghìn lần mỗi giây.

**Ưu tiên khảo sát:** mảng cố định, bit packing cố định, dictionary với mã cố định, hoặc nén khối nhỏ có chỉ mục trực tiếp. Nếu dùng delta/varint, cần checkpoint đủ dày.

**Kiểm chứng:** số byte/khối nạp mỗi GET, số mục giải mã thừa, cache hit và p99 latency.

### 13.3. Ghi cập nhật nhỏ với tần suất cao

Ví dụ bảng trạng thái thiết bị được sửa liên tục.

**Ưu tiên khảo sát:** biểu diễn có kích thước phần tử cố định hoặc tách **vùng cập nhật nhanh** khỏi **vùng dữ liệu nén bất biến**. Nếu cần thêm/xóa thường xuyên, xem xét cấu trúc phân đoạn, cây, bảng băm hoặc LSM với compaction có kiểm soát.

**Kiểm chứng:** write amplification, độ trễ ghi bền, số lần tái nén block, chi phí hợp nhất và dung lượng tạm.

### 13.4. Dữ liệu có độ phân bố không đều

Một số khối có giá trị chỉ cần 4 bit; khối khác cần 16 bit. Dùng w = 16 cho toàn bộ dãy lãng phí ở các vùng nhỏ.

**Ưu tiên khảo sát:** bit packing theo block với **w riêng**, patch exceptions hoặc dictionary theo block. Metadata tăng lên nhưng có thể giảm đáng kể payload.

**Kiểm chứng:** độ lớn block tối ưu, tỷ lệ khối có ngoại lệ, độ trễ random access và chi phí khi giá trị mới vượt w cũ.

### Bảng định hướng

| Tải nổi bật | Cách biểu diễn nên thử trước | Rủi ro quan trọng |
| --- | --- | --- |
| Nhiều point lookup, dữ liệu số có miền cố định | Fixed-width / bit packing | Giá trị vượt miền, truy cập không căn biên byte |
| Dãy đơn điệu, đọc theo thứ tự | Delta + varint hoặc delta bit packing | Random access cần checkpoint; sửa có thể phá bất biến |
| Các chuỗi giá trị lặp dài | RLE | Chèn/sửa rải rác làm tăng số run |
| Giá trị chuỗi lặp nhiều | Dictionary + mã cố định | Từ điển lớn, mã phải tăng độ rộng |
| Quét lượng dữ liệu lớn, hiếm cập nhật | Nén khối kích thước vừa/lớn | CPU decode và latency GET |
| Đọc ngẫu nhiên lẫn cập nhật đều cao | Block nhỏ, direct-access hoặc overlay | Index/cache/compaction tăng chi phí |
| Dữ liệu thường chèn/xóa ở giữa | Chunked/tree/overlay | Cần bảo trì index và cân bằng cấu trúc |

Đây là danh sách **giả thuyết thiết kế**, không phải kết quả benchmark chung cho mọi phần cứng.

## 14. Thiết kế benchmark công bằng

Để so sánh biểu diễn, nên dùng **cùng dữ liệu**, cùng bộ so sánh/kiểu số, cùng máy và cùng ngân sách RAM. Trộn kết quả từ cache nóng với cache lạnh sẽ làm sai kết luận.

Một bộ thử nhỏ nhưng hữu ích:

1. **Bulk load:** mã hóa n phần tử, đo thời gian xây dựng và dung lượng đầy đủ (kể cả index).
2. **Random GET:** lấy chỉ số ngẫu nhiên, kiểm tra giá trị đúng và đo p50/p95/p99.
3. **Sequential scan:** giải mã toàn bộ dãy, tính checksum và đo throughput.
4. **Hot-set GET:** 90% truy vấn vào 10% phần tử để xem cache hoạt động ra sao.
5. **Point UPDATE:** sửa mục rải rác, giữ miền giá trị hợp lệ, đo byte ghi và thời gian tái nén.
6. **INSERT/DELETE:** nếu cấu trúc hỗ trợ, đo số byte dời/chỉ mục cập nhật; nếu không hỗ trợ trực tiếp, ghi rõ giới hạn.
7. **Mixed workload:** kết hợp đọc/ghi theo tỷ lệ thực tế, đo độ trễ đuôi và hiệu năng bền vững sau các đợt hợp nhất.

Mỗi phép thử nên có **bài kiểm tra tính đúng**: giải mã phải khớp dữ liệu gốc; sau cập nhật, mọi phần tử chưa sửa phải giữ nguyên; chỉ mục không được trỏ tới offset cũ; không được mất/xuất hiện thêm khóa.

Các chỉ số nên báo cáo:

| Chỉ số | Vì sao quan trọng |
| --- | --- |
| Byte/phần tử gồm index | Đánh giá nén thực tế |
| Giá trị/giây khi quét | Tốc độ giải mã tuần tự |
| p50/p95/p99 random GET | Độ trễ thực tế của truy cập ngẫu nhiên |
| CPU cycles hoặc thời gian CPU | Phân biệt nút thắt giải mã và I/O |
| Cache miss và I/O bytes | Xem nén có giúp giữ nhiều dữ liệu hơn trong cache không |
| Byte ghi vật lý / byte ghi logic | Write amplification |
| Dung lượng bộ đệm và block giải nén | RAM thật khi sử dụng cấu trúc |
| Thời gian rebuild/compaction | Chi phí nền sau nhiều cập nhật |

**Bất biến của benchmark:** so các phương án trên cùng dữ liệu được phục hồi chính xác. Một codec làm tròn hoặc mất thông tin phải được so theo yêu cầu sai số của ứng dụng, không thể coi là thay thế tương đương một codec lossless.

## 15. Những ngộ nhận cần tránh

**1. “Nén càng mạnh thì hệ thống càng nhanh.”** Nén giảm byte cần chuyển và dung lượng lưu, nhưng giải mã, tìm offset, tái nén và cập nhật có thể tăng CPU/I/O.

**2. “Mọi dữ liệu nén đều không thể truy cập O(1).”** Fixed-width bit packing và dictionary có mã cố định vẫn có truy cập theo chỉ số O(1) trong mô hình RAM nếu metadata sẵn sàng.

**3. “Độ phức tạp O(1) của lấy phần tử có nghĩa một I/O.”** Ngay cả một phép đọc ít byte cũng có thể chạm trang thiết bị, còn truy cập trong cache có thể không phát sinh I/O.

**4. “Varint tự biết vị trí phần tử i.”** Mã độ dài biến đổi cần quét độ dài các mã trước hoặc dùng offset/checkpoint/index bổ sung.

**5. “Thêm checkpoint không tốn gì.”** Checkpoint làm tăng metadata, có thể tăng RAM; nó đánh đổi dung lượng lấy tốc độ truy cập.

**6. “Delta encoding sửa một mục thì phải tính lại toàn bộ hiệu.”** Với delta bậc một, sửa x_i thường chỉ làm thay đổi hai hiệu lân cận về mặt toán học; mã có độ dài biến đổi và byte offset mới có thể khiến việc ghi lại phức tạp.

**7. “Chỉ sửa 8 byte, SSD cũng chỉ ghi 8 byte.”** Cần xem write amplification do trang, WAL, nén lại block, copy-on-write và compaction.

**8. “RLE phù hợp mọi dữ liệu có vài giá trị lặp.”** RLE cần **các đoạn lặp liên tiếp** đủ dài. Giá trị lặp nhưng xen kẽ có thể tạo nhiều run ngắn.

**9. “Chỉ đo payload là đủ để so tỷ lệ nén.”** Chỉ mục, dictionary, header, padding và dữ liệu tạm đều có chi phí.

**10. “Cùng tỷ lệ nén thì mọi codec tương đương.”** Đường đọc, khả năng SIMD, checkpoint, kiểu cập nhật và RAM phụ trợ có thể rất khác nhau.

## 16. Bài tập thực hành có lời giải

### Bài 1 — Tính dung lượng bit packing

Có **500.000** số nguyên nằm trong [0, 1023]. Nếu lưu mỗi số bằng 16 bit, dung lượng payload là bao nhiêu? Nếu bit packing tối ưu theo miền giá trị, cần bao nhiêu bit mỗi số và tiết kiệm bao nhiêu?

**Lời giải:** 1023 = 2^10 − 1, nên cần **10 bit**. Dạng 16 bit cần **1.000.000 byte**; dạng 10 bit cần **625.000 byte**. Tiết kiệm **375.000 byte**, tức **37,5%** payload, chưa tính metadata.

### Bài 2 — Vị trí bit

Dãy đóng gói cố định **w = 12 bit/giá trị**. Phần tử chỉ số **i = 7** bắt đầu ở vị trí bit/byte nào?

**Lời giải:** bit offset = 7 × 12 = **84**; byte offset = floor(84/8) = **10**; dịch trong byte = 84 mod 8 = **4 bit**. Giá trị 12 bit chiếm một phần byte 10 và byte 11, nên phải trích dữ liệu vượt ranh giới byte.

### Bài 3 — Checkpoint

Một dãy n = 1.000.000 mục lưu delta/varint và checkpoint cứ **k = 100** mục. Có khoảng bao nhiêu checkpoint? Tối đa cần giải mã bao nhiêu delta sau checkpoint gần nhất để lấy một phần tử?

**Lời giải:** Khoảng **ceil(1.000.000/100) = 10.000 checkpoint**. Nếu mỗi checkpoint ghi giá trị tuyệt đối tại đúng vị trí bội số của 100, cần giải mã tối đa **99 delta**. Mỗi checkpoint cần lưu đủ thông tin định vị trong byte stream; số byte tổng phụ thuộc cách mã hóa giá trị/offset.

### Bài 4 — RLE sau cập nhật

Dãy ban đầu là **[X, X, X, X, X, X]**, mã RLE là (X,6). Thay phần tử chỉ số 2 thành Y. Mã RLE mới là gì, số run thay đổi ra sao?

**Lời giải:** Dãy mới [X, X, Y, X, X, X], mã mới **(X,2), (Y,1), (X,3)**. Một run trở thành **ba run**; nén RLE có thể kém hiệu quả sau các cập nhật rải rác.

### Bài 5 — Chỉ mục block

1.000.000 mục được chia thành block 256 mục. Mỗi entry index lưu offset 8 byte và độ dài 8 byte. Bỏ qua metadata khác, index cần bao nhiêu byte?

**Lời giải:** Số block = ceil(1.000.000/256) = **3907**. Dung lượng = 3907 × 16 = **62.512 byte**, xấp xỉ **61,05 KiB**.

### Bài 6 — Vì sao cập nhật nén khối có thể đắt?

Một ứng dụng sửa một giá trị logic 4 byte. Codec cần giải mã/nén lại block và lưu phiên bản nén 4096 byte. Chỉ tính lượng block được viết lại, write amplification là bao nhiêu?

**Lời giải:** **4096/4 = 1024 lần**. Tổng WA thực có thể lớn hơn khi tính WAL/metadata/compaction, hoặc nhỏ hơn theo bình quân nếu gộp nhiều cập nhật cùng block thành một lượt ghi.

### Bài 7 — Chọn kỹ thuật nén

Một cột dữ liệu có các chuỗi “Đang xử lý”, “Hoàn thành”, “Lỗi” lặp hàng triệu lần, truy cập ngẫu nhiên nhiều và ít khi bổ sung trạng thái mới. Nên thử gì?

**Lời giải gợi ý:** **Dictionary encoding** với ba mã và một từ điển nhỏ; dãy mã có thể bit pack trong **2 bit/giá trị** (vì cần chứa 3 mã). Lấy mã thứ i và tra từ điển đều có thể O(1). Cần kiểm tra thay đổi số trạng thái và metadata của từ điển.

### Bài 8 — Dữ liệu có tính thứ tự

Cho dãy [1000, 1002, 1003, 1007, 1008]. Hãy viết base và delta. Vì sao tìm phần tử thứ tư không nhất thiết O(1) trong dạng delta/varint nối liên tục?

**Lời giải:** Base **1000**, delta liên tiếp **2, 1, 4, 1**. Để khôi phục phần tử chỉ số 3 là 1007, phải cộng các delta **2 + 1 + 4** nếu không có checkpoint/giá trị tuyệt đối khác. Với một dãy lớn, số delta phải giải mã tăng theo khoảng cách tới điểm neo.

### Bài 9 — So sánh hai tải

Cùng một tệp 20 GiB, hệ A mỗi giờ quét toàn bộ tệp một lần; hệ B mỗi giây đọc ngẫu nhiên 1000 giá trị. Tại sao không nên chọn cùng một block size chỉ vì nén được tốt?

**Lời giải gợi ý:** Hệ A thường được lợi từ block lớn để quét tuần tự và tăng tỷ lệ nén. Hệ B cần giảm lượng dữ liệu đọc/giải mã thừa cho mỗi GET, nên block nhỏ hoặc codec hỗ trợ direct access có thể tốt hơn. Cần benchmark cùng tỷ lệ cache và cùng thiết bị.

### Bài 10 — Tìm sai lầm trong đánh giá

Nhóm A báo codec X giảm dung lượng từ 100 MB xuống 30 MB. Codec Y giảm còn 35 MB nhưng có bảng index 2 MB. Nhóm A kết luận X luôn tốt hơn vì 30 < 35. Kết luận có đủ căn cứ không?

**Lời giải:** Chưa đủ. Phải tính metadata của **cả hai** codec, đo truy cập ngẫu nhiên, quét tuần tự, cập nhật và RAM phụ trợ. Nếu X không có index để truy cập trực tiếp, lấy một giá trị có thể phải giải mã rất nhiều dữ liệu. Nếu X có các cấu trúc phụ trợ chưa được tính, tổng dung lượng có thể không còn 30 MB.

## 17. Ghi nhớ để vận dụng

Khi thiết kế biểu diễn gọn, hãy lần lượt trả lời:

1. **Dữ liệu có quy luật gì?** Miền số nhỏ, hiệu nhỏ, các đoạn lặp dài, hay ít giá trị phân biệt?
2. **Cần thao tác gì?** Quét toàn bộ, lấy theo chỉ số, tìm khóa, sửa, chèn, xóa hay append?
3. **Đơn vị giải mã và ghi lại là gì?** Một giá trị, một run, một block hay cả tệp?
4. **Làm sao tới được phần tử cần đọc?** Tính offset trực tiếp, tra block index, nhảy checkpoint hay quét từ đầu?
5. **Metadata nào phải lưu?** Bit width, từ điển, checkpoint, ranh giới khối, vị trí run, phiên bản và checksum?
6. **Điều gì xảy ra khi giá trị mới vượt miền mã hóa hoặc đổi độ dài?** Có escape, mở rộng độ rộng, cấp phát block mới hoặc rebuild không?
7. **Đã đo cả CPU, RAM, I/O và độ trễ chưa?** Dung lượng nhỏ không phải mục tiêu duy nhất.

Một biểu diễn tốt là biểu diễn **giữ đúng bất biến dữ liệu**, đủ gọn để sử dụng hiệu quả bộ nhớ/thiết bị, đồng thời có chi phí **truy cập ngẫu nhiên và cập nhật** phù hợp với tải thật. Đó là cách đưa nguyên lý về độ phức tạp và lựa chọn cấu trúc dữ liệu từ mô hình lý thuyết vào hệ thống thực tế.
