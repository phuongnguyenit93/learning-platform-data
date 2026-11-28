# Lập bảng quyết định theo khối lượng dữ liệu, bộ nhớ và tải thao tác

Chọn cấu trúc dữ liệu không chỉ là tìm cấu trúc có độ phức tạp thời gian nhỏ nhất trên giấy. Một bảng băm tra cứu nhanh nhưng không duy trì thứ tự; mảng đã sắp xếp hỗ trợ tìm kiếm nhị phân nhưng chèn giữa mảng có thể phải dịch chuyển hàng triệu phần tử; cây cân bằng hỗ trợ nhiều truy vấn hơn song mỗi nút có thêm chi phí con trỏ và cấp phát. Cùng một bài toán, lựa chọn phù hợp có thể đổi khi lượng dữ liệu, ngân sách bộ nhớ hoặc tỉ lệ đọc/ghi thay đổi.

Trong chương **Lựa chọn và thiết kế** của học phần cấu trúc dữ liệu, bài này xây dựng một **bảng quyết định có căn cứ**: chuyển yêu cầu thực tế thành các tiêu chí đo lường, loại sớm các phương án không đáp ứng chức năng hoặc tài nguyên, rồi so sánh các phương án còn lại theo khối lượng thao tác thực tế. Cách làm áp dụng được cho mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap, cấu trúc truy vấn đoạn và biểu diễn đồ thị.

Sau bài học, người học có thể:

- Lập hồ sơ tải thao tác gồm kích thước dữ liệu, tần suất từng phép toán, phân phối khóa và yêu cầu độ trễ.
- Ước lượng chi phí bộ nhớ cơ sở và **bộ nhớ đỉnh** khi cấu trúc tăng trưởng hoặc tái xây dựng.
- Lập bảng so sánh theo chức năng, thời gian, bộ nhớ, độ phức tạp triển khai và điều kiện áp dụng.
- Dùng số đo thực nghiệm và bài kiểm tra ràng buộc để đưa ra quyết định có thể giải thích và xem xét lại.

## 1. Bắt đầu từ yêu cầu, chưa bắt đầu từ tên cấu trúc

Hãy mô tả bài toán bằng các thông tin mà cấu trúc dữ liệu buộc phải đáp ứng:

| Câu hỏi | Ví dụ thông tin cần ghi | Vì sao ảnh hưởng đến lựa chọn? |
| --- | --- | --- |
| Lưu gì? | Tập khóa, ánh xạ khóa–giá trị, dãy có thứ tự, đa tập, tập cạnh đồ thị | Mỗi cấu trúc hỗ trợ một tập phép toán và bất biến khác nhau |
| Có bao nhiêu phần tử? | `N` hiện tại, `N_max` dự kiến, số phần tử trùng, miền giá trị khóa | Chi phối chiều cao cây, tải bảng băm, số ô cấp phát |
| Truy vấn gì? | Tìm khóa, lấy phần tử thứ `k`, tìm min, đếm khoảng, lấy tổng đoạn | Quyết định có cần thứ tự, chỉ mục hay giá trị tổng hợp |
| Cập nhật ra sao? | Thêm cuối, chèn bất kỳ, xóa theo khóa, tăng giá trị, cập nhật cả đoạn | Chi phí cập nhật có thể đảo ngược ưu thế truy vấn |
| Tỉ lệ thao tác? | 90% tìm khóa, 8% chèn, 2% xóa; hoặc 70% truy vấn đoạn | Cấu trúc tối ưu cho tải chỉ đọc có thể kém khi cập nhật dày |
| Yêu cầu giới hạn? | 128 MiB RAM, độ trễ p99 dưới 5 ms, dữ liệu phải bền vững trên đĩa | Là các **ràng buộc cứng**, không phải điểm cộng tùy ý |
| Truy cập theo mẫu nào? | Khóa phân bố đều hay lệch, quét liên tiếp hay ngẫu nhiên, đọc cùng khóa nhiều lần | Ảnh hưởng cache, va chạm, phân nhánh và hiệu năng đo được |
| Có cần đồng thời? | Một luồng, nhiều luồng đọc, nhiều luồng cập nhật | Đồng bộ, khóa và tranh chấp có thể chi phối chi phí |

Một hồ sơ tải thao tác có thể biểu diễn như sau:

```text
Đối tượng: ánh xạ user_id -> điểm tích lũy
N ban đầu: 1.000.000 khóa; dự kiến 2.000.000 sau 12 tháng
Tải: 5.000 thao tác/giây, 95% tra cứu, 4% cập nhật giá trị, 1% thêm mới
Truy vấn theo thứ tự khóa: không
Mục tiêu: p99 < 10 ms; ngân sách RAM của thành phần: 256 MiB
Khóa: số nguyên 64 bit; bản ghi được truy cập ngẫu nhiên
```

Đây mới là một **đặc tả ban đầu**: còn cần biết giới hạn cứng nào có thể chứng minh, độ lớn giá trị lưu trữ, chi phí bộ nhớ của runtime và cách đo tải cao điểm. Nhưng nó đã chỉ ra rằng bảng băm là ứng viên hợp lý hơn mảng đã sắp xếp nếu không cần thứ tự và có cập nhật thường xuyên.

### Phân biệt ba loại yêu cầu

**Yêu cầu chức năng** bắt buộc phải đúng: ví dụ, cần `range_sum(l, r)` hoặc cần xuất toàn bộ khóa theo thứ tự tăng dần. Nếu cấu trúc không hỗ trợ, hãy loại nó hoặc ghi rõ **chỉ mục phụ** sẽ phải bổ sung.

**Ràng buộc cứng** là giới hạn không được vượt: ngân sách RAM, thời gian xấu nhất của thao tác quan trọng, kích thước tối đa của ổ đĩa, độ bền dữ liệu. Một phương án có điểm trung bình cao vẫn bị loại nếu vượt giới hạn.

**Mục tiêu tối ưu** là tiêu chí để xếp hạng các phương án hợp lệ: độ trễ trung bình, thông lượng, chi phí bộ nhớ, đơn giản khi bảo trì. Phải gán mức ưu tiên rõ ràng nếu nhiều mục tiêu xung đột.

## 2. Định lượng khối lượng dữ liệu và bộ nhớ

Độ phức tạp không gian `O(N)` chưa đủ để biết cấu trúc có vừa RAM hay không. Hai cấu trúc cùng `O(N)` có thể khác nhau nhiều lần về hệ số hằng.

### Dữ liệu thực và phần phụ trợ

Ước lượng bộ nhớ từ các thành phần:

\[
M_{\text{total}}\approx
M_{\text{payload}}+M_{\text{metadata}}+
M_{\text{index}}+M_{\text{allocator}}+M_{\text{temporary}}.
\]

Trong đó:

- `payload`: dữ liệu thực sự cần lưu, ví dụ khóa 8 byte và giá trị 8 byte.
- `metadata`: con trỏ nút, kích thước, mức ưu tiên, bit trạng thái, liên kết, thông tin cân bằng.
- `index`: mảng bucket, slot trống, chỉ mục theo khóa/thứ tự, cây phụ hoặc bảng tổng hợp.
- `allocator`: căn chỉnh bộ nhớ, header của đối tượng, phân mảnh, chi phí quản lý bộ cấp phát và bộ thu gom rác (nếu có).
- `temporary`: bản sao khi mở rộng mảng/bảng băm, vùng đệm lúc sắp xếp, các lô dữ liệu và cấu trúc tạo trong quá trình truy vấn.

**Ví dụ ước lượng thấp nhất:** một triệu cặp khóa–giá trị, mỗi cặp gồm hai số nguyên 64 bit, có `16 × 1.000.000 = 16.000.000` byte dữ liệu thô, xấp xỉ `15,26 MiB`. Đây **không phải** số RAM thực tế của bảng băm hoặc cây chứa một triệu phần tử. Slot trống, con trỏ, đối tượng runtime và vùng nhớ tạm đều làm số đó tăng lên. Trong Python, ngay cả bản thân đối tượng số nguyên cũng có overhead so với biểu diễn 8 byte trong một mảng kiểu cố định.

Với bảng băm dùng địa chỉ mở, nếu `N` phần tử được lưu với hệ số tải mục tiêu \(\alpha=N/C\), thì số slot tối thiểu cần khoảng:

\[
C\ge\left\lceil \frac{N}{\alpha}\right\rceil .
\]

Chẳng hạn `N = 1.000.000`, \(\alpha=0{,}70\) đòi hỏi ít nhất khoảng `1.428.572` slot. Kích thước mỗi slot và cách lưu giá trị quyết định số byte thực tế; \(\alpha\) cũng ảnh hưởng đến số lần dò trung bình và chi phí mở rộng.

### Phải tính cả bộ nhớ đỉnh

Khi mảng động mở rộng, đôi lúc cả vùng cũ và vùng mới cùng tồn tại trong lúc sao chép. Bảng băm có thể đồng thời giữ bảng cũ và bảng mới khi rehash. Một tác vụ sắp xếp hoặc xây lại chỉ mục cũng cần bộ nhớ tạm. Vì thế:

\[
M_{\text{peak}} = \max_t M_{\text{in use}}(t).
\]

Ngân sách cần so với **`M_peak`**, không chỉ kích thước ổn định sau khi xây xong. Trên môi trường có bộ thu gom rác, bộ nhớ còn phụ thuộc lịch thu gom và số đối tượng tồn tại đồng thời.

**Kiểm tra tăng trưởng:** nếu hiện tại có `N_0` phần tử nhưng dữ liệu dự kiến tăng đến `N_{\max}`, hãy tính cho `N_{\max}` và cả đợt rebuild/rehash lớn nhất được phép. Một cấu trúc phù hợp hôm nay có thể không còn phù hợp khi dữ liệu tăng gấp đôi.

### Dữ liệu nằm trong RAM hay trên đĩa?

Với chỉ mục hoàn toàn trong RAM, truy cập bộ nhớ ngẫu nhiên và cache có thể ảnh hưởng lớn đến tốc độ. Khi dữ liệu vượt RAM, số lần truy cập trang/khối từ đĩa thường quan trọng hơn chênh lệch vài phép so sánh. B-tree/B+ tree gom nhiều khóa trong một trang để giảm số lần truy cập trang và hỗ trợ quét theo thứ tự; các cấu trúc dạng log như LSM-tree ưu tiên ghi tuần tự nhưng có chi phí compaction và read amplification cần cân nhắc. Không nên so các chỉ mục trên đĩa bằng cách chỉ đếm thao tác CPU.

## 3. Lập bảng ứng viên theo phép toán thực tế

Trước khi chấm điểm, lập bảng khả năng của những cấu trúc **có thể giải đúng bài toán**. Bảng dưới dùng `N` là số phần tử và `K` là số kết quả xuất ra. Các độ phức tạp là giả thiết điển hình của cách cài đặt tương ứng.

| Cấu trúc | Tìm theo khóa | Thêm/xóa | Thứ tự và truy vấn khác | Bộ nhớ và điều kiện |
| --- | --- | --- | --- | --- |
| Mảng động chưa sắp xếp | `O(N)` nếu phải tìm; truy cập theo chỉ số `O(1)` | Thêm cuối `O(1)` khấu hao; chèn/xóa giữa `O(N)` | Duyệt tuần tự nhanh; không có tìm theo thứ tự tự động | `O(N)`, vùng nhớ liên tục, có khoảng dự phòng |
| Mảng đã sắp xếp | Tìm bằng tìm kiếm nhị phân `O(log N)` | Chèn/xóa giữa `O(N)` do dịch chuyển | Tìm đoạn theo khóa `O(log N + K)` | `O(N)`, thường có locality tốt |
| Bảng băm | `O(1)` trung bình/kỳ vọng theo giả thiết phân phối băm | `O(1)` trung bình/khấu hao; có trường hợp xấu `O(N)` | Không hỗ trợ sắp thứ tự hay khoảng khóa một cách tự nhiên | `O(N)`, cần slot/bucket và kiểm soát tải |
| Cây tìm kiếm cân bằng (AVL, red-black) | `O(log N)` xấu nhất | `O(log N)` xấu nhất | Duyệt có thứ tự; truy vấn khoảng `O(log N + K)` | `O(N)`, mỗi nút thường có con trỏ/metadata |
| Heap nhị phân | Tìm khóa bất kỳ `O(N)` | Thêm và lấy phần tử ưu tiên nhất `O(log N)` | Xem min/max ở đỉnh `O(1)`; không thay cây tìm kiếm | `O(N)`, có thể lưu dạng mảng |
| Bitset trên miền khóa `[0,U)` | Kiểm tra thuộc tập `O(1)` | Đặt/xóa bit `O(1)` | Phù hợp bài toán tập hợp và phép bit; không lưu giá trị tùy ý | `O(U)` bit, hiệu quả khi miền khóa đủ nhỏ |
| B+ tree theo trang | Thường `O(log_B N)` truy cập trang cho tìm kiếm | Thêm/xóa có điều chỉnh nút/trang | Tốt cho truy vấn đoạn và duyệt theo thứ tự trên dữ liệu lớn | Bộ nhớ trang, cache và chi phí I/O chi phối |

`log_B N` ở B+ tree dùng `B` là bậc nhánh hiệu dụng (số con/khóa vừa trên trang), không nên hiểu là logarit thời gian CPU đơn thuần. Một vài thư viện bảng băm duy trì **thứ tự chèn**, nhưng thứ tự đó không tương đương thứ tự so sánh của khóa.

### Đối với các phép tổng hợp trên đoạn

Nếu dữ liệu là mảng số hoặc các phần tử có vị trí cố định, cần thêm các ứng viên:

| Cấu trúc | Truy vấn | Cập nhật | Bộ nhớ | Chọn khi |
| --- | --- | --- | --- | --- |
| Tổng tiền tố | Tổng `[l,r)` trong `O(1)` | Sửa một phần tử có thể tốn `O(N)` | `O(N)` | Dữ liệu tĩnh, rất nhiều truy vấn tổng |
| Fenwick tree | Tổng đoạn `O(log N)` | Cộng tại một vị trí `O(log N)` | `O(N)` | Cập nhật điểm và truy vấn tổng |
| Segment tree | Tổng/min/max đoạn `O(log N)` | Cập nhật điểm `O(log N)` | `O(N)` | Cần phép gộp có tính kết hợp; muốn mở rộng sang nhiều kiểu truy vấn |
| Sparse table | Min/max đoạn tĩnh `O(1)` với phép toán phù hợp | Không cập nhật hiệu quả | `O(N log N)` | Dữ liệu tĩnh và cần rất nhiều truy vấn cực trị |

Không được dùng bốn phép cộng/trừ của tổng tiền tố để suy ra `min`/`max`; phép gộp phải phù hợp với cách lấy kết quả. Với bài toán cập nhật cả đoạn, có thể cần lazy segment tree hoặc kỹ thuật hiệu số riêng, không thể mặc nhiên dùng phiên bản chỉ hỗ trợ cập nhật điểm.

## 4. Chuyển tỉ lệ tải thành chi phí

Một bảng quyết định phải phản ánh tải thực tế. Gọi `p_i` là tỉ lệ thao tác loại `i` và `t_i(S,N)` là thời gian đo được hoặc ước lượng của thao tác đó trên cấu trúc `S` với kích thước dữ liệu `N`. Khi \(\sum_i p_i=1\), chi phí trung bình có trọng số là:

\[
\overline{t}(S,N)=\sum_i p_i\,t_i(S,N).
\]

Nếu hệ thống nhận \(\lambda\) thao tác mỗi giây thì, dưới các giả định đo lường nhất quán, có thể ước lượng lượng thời gian phục vụ cần thiết mỗi giây là \(\lambda\,\overline{t}\). Nhưng **độ trễ đầu cuối không bằng riêng thời gian xử lý cấu trúc dữ liệu**: còn có hàng đợi, đồng bộ, phân bổ bộ nhớ, I/O và tranh chấp tài nguyên.

### Ví dụ minh họa: giá của một kiểu thao tác hiếm

Giả sử một hệ thống quản lý `N = 1.000.000` khóa, trong một đợt có `10.000.000` thao tác:

- 99,5% tra cứu theo khóa, tức `9.950.000` lượt.
- 0,5% chèn khóa mới tại vị trí bất kỳ, tức `50.000` lượt.
- Không có yêu cầu duyệt theo thứ tự.

Mảng đã sắp xếp tìm một khóa bằng tìm kiếm nhị phân trong `O(log N)`, nhưng mỗi lần chèn trung bình có thể phải dời khoảng nửa số phần tử nếu vị trí chèn trải đều trên mảng. Ước lượng rất thô:

\[
50.000 \times 500.000 = 25.000.000.000
\]

lượt dịch chuyển phần tử trong cả đợt, chưa tính chi phí cấp phát. Mảng đã sắp xếp vì thế có thể bất lợi đáng kể dù số thao tác chèn chỉ chiếm 0,5%. Nếu không cần thứ tự và hàm băm phân phối phù hợp, bảng băm là ứng viên hợp lý; kết luận cuối cùng vẫn cần kiểm tra bộ nhớ và đo đạc.

Trong bài toán khác, chỉ 5% thao tác là truy vấn khoảng nhưng mỗi truy vấn khoảng rất tốn nếu dùng bảng băm, cây cân bằng hoặc mảng đã sắp xếp có thể thắng về tổng thời gian. **Phần trăm nhỏ không đồng nghĩa chi phí nhỏ.**

### Đừng cộng trực tiếp các ký hiệu Big-O

Biểu thức `0,95 × O(1) + 0,05 × O(N)` có thể gợi ý điểm nghẽn nhưng không cho ra số micro giây: các ký hiệu `O(...)` bỏ qua hệ số hằng, phân phối dữ liệu và đặc điểm phần cứng. Dùng Big-O để **loại phương án khó mở rộng**, rồi đo bằng cùng phương pháp trên cùng bộ dữ liệu để so sánh thực tế.

## 5. Tạo bảng quyết định có điều kiện loại và số đo

Quy trình thực tế có hai lượt. Lượt đầu kiểm tra **hợp lệ**: cấu trúc có thực hiện đủ phép toán hay không, bộ nhớ đỉnh và các giới hạn cứng có đạt hay không. Lượt sau so sánh **hiệu quả**: dùng thời gian hoặc chi phí đã đo, quy đổi theo tỉ lệ thao tác, xét thêm rủi ro tăng trưởng và độ phức tạp vận hành.

Ví dụ giả định có ba phương án cho một dịch vụ cần tìm khóa, thêm khóa mới và tìm khoảng. Các số thời gian dưới đây **chỉ là dữ liệu giả lập để minh họa cách tính**, không phải benchmark của thư viện cụ thể:

| Phương án | Tìm khóa (µs) | Chèn (µs) | Truy vấn khoảng (µs) | RAM đỉnh đo giả định (MiB) |
| --- | ---: | ---: | ---: | ---: |
| Bảng băm và quét toàn bộ khi tìm khoảng | 0,25 | 0,60 | 1.000 | 110 |
| Mảng đã sắp xếp | 0,55 | 250 | 5,0 | 48 |
| Cây cân bằng | 0,85 | 1,20 | 10,0 | 115 |

Với tỉ lệ `93%` tìm khóa, `2%` chèn và `5%` truy vấn khoảng, áp dụng công thức trung bình có trọng số:

\[
\begin{aligned}
\overline t_{\text{hash}}&=0{,}93(0{,}25)+0{,}02(0{,}60)+0{,}05(1000)=50{,}2445\ \mu s,\\
\overline t_{\text{sorted}}&=0{,}93(0{,}55)+0{,}02(250)+0{,}05(5)=5{,}7615\ \mu s,\\
\overline t_{\text{tree}}&=0{,}93(0{,}85)+0{,}02(1{,}20)+0{,}05(10)=1{,}3145\ \mu s.
\end{aligned}
\]

Với giới hạn RAM đỉnh `128 MiB`, cả ba phương án trong bảng ví dụ đều hợp lệ và cây cân bằng có thời gian trung bình thấp nhất **theo các số giả định**. Nếu ngân sách hạ còn `64 MiB`, chỉ mảng đã sắp xếp thỏa điều kiện RAM; khi đó phải cân nhắc liệu độ trễ chèn có còn chấp nhận được hay cần đổi cách biểu diễn dữ liệu.

Có thể tự tính và lọc ứng viên bằng đoạn mã Python sau. Đầu vào là **số đo đã thu thập** hoặc số giả định có ghi nhãn, không phải số do thuật toán tự suy ra:

```python
weights = {"get": 0.93, "insert": 0.02, "range": 0.05}
memory_limit_mib = 128

candidates = {
    "hash": {
        "peak_mib": 110,
        "us": {"get": 0.25, "insert": 0.60, "range": 1000.0},
    },
    "sorted_array": {
        "peak_mib": 48,
        "us": {"get": 0.55, "insert": 250.0, "range": 5.0},
    },
    "balanced_tree": {
        "peak_mib": 115,
        "us": {"get": 0.85, "insert": 1.20, "range": 10.0},
    },
}

assert abs(sum(weights.values()) - 1.0) < 1e-12

feasible = []
for name, data in candidates.items():
    if data["peak_mib"] > memory_limit_mib:
        continue
    weighted_us = sum(
        weights[operation] * data["us"][operation]
        for operation in weights
    )
    feasible.append((weighted_us, name))

for weighted_us, name in sorted(feasible):
    print(f"{name}: {weighted_us:.4f} us/op")

# balanced_tree: 1.3145 us/op
# sorted_array: 5.7615 us/op
# hash: 50.2445 us/op
```

Đoạn mã chỉ xếp hạng theo thời gian **trung bình** và RAM đỉnh. Nếu có ràng buộc p95/p99, giới hạn xấu nhất, khả năng duyệt có thứ tự hoặc khả năng giữ dữ liệu qua khởi động lại, phải thêm bước loại tương ứng trước khi chọn phương án đứng đầu. Thông số đo trên máy khác hoặc ở `N` khác có thể đảo thứ tự kết quả.

### Mẫu bảng quyết định dùng trong thiết kế

Một bản ghi quyết định nên đủ để người khác hiểu *vì sao* chọn:

| Trường quyết định | Nội dung cần điền |
| --- | --- |
| Bài toán và bất biến | Ngữ nghĩa khóa trùng, thứ tự, tính đúng đắn của truy vấn |
| Hồ sơ tải | `N` hiện tại/đỉnh; tỉ lệ đọc/ghi; kích thước truy vấn; phân phối khóa |
| Ràng buộc cứng | RAM đỉnh, bộ nhớ lưu trữ, độ trễ p99, tính bền vững, số luồng |
| Danh sách ứng viên | Cấu trúc chính và mọi chỉ mục phụ cần đi kèm |
| Dự báo Big-O | Chi phí từng thao tác và điều kiện để dự báo đúng |
| Số đo thực nghiệm | `N`, phần cứng, phiên bản, bộ dữ liệu, thao tác/giây, p50/p99, RAM đỉnh |
| Kết luận | Phương án chọn, phương án loại và lý do |
| Ngưỡng xem xét lại | Khi dữ liệu gấp đôi, tỉ lệ cập nhật thay đổi hoặc RAM/p99 vượt mục tiêu |

Nếu chưa có benchmark, có thể điền **ước lượng** và đánh dấu là ước lượng; không biến số giả định thành kết quả thực nghiệm. Việc ghi điều kiện xem xét lại giúp quyết định vẫn hữu ích khi tải hệ thống thay đổi.

## 6. Lấy số đo để kiểm chứng quyết định

Số đo phải mô phỏng đường đi chính của ứng dụng, không chỉ đo một lời gọi đơn lẻ trên dữ liệu nhỏ. Các bước khuyến nghị:

1. **Chuẩn hóa ngữ nghĩa:** mọi ứng viên trả cùng kết quả; xử lý khóa trùng, null, thứ tự và vùng rỗng nhất quán.
2. **Tạo dữ liệu có kích thước thực:** thử ít nhất quy mô hiện tại và `N_max`, bao gồm phân phối khóa đều, khóa nóng, khóa trùng hoặc dữ liệu có thứ tự nếu có liên quan.
3. **Tạo trace thao tác:** giữ đúng tỉ lệ đọc/ghi và kích thước truy vấn; cố định seed khi cần tái hiện và kiểm tra cả các đợt tải tăng vọt.
4. **Đo sau khởi động thích hợp:** phân biệt chi phí xây dựng ban đầu với chi phí hoạt động dài hạn; với runtime có JIT/GC, đo cả warm-up và các khoảng dừng.
5. **Ghi số đo đầy đủ:** thông lượng, p50/p95/p99, RAM thường trực và RAM đỉnh, số lần cấp phát, số phép so sánh hoặc I/O nếu có thể.
6. **Đánh giá lại giới hạn:** xác nhận mọi ràng buộc cứng và bất biến đúng; chỉ sau đó mới so ứng viên hợp lệ.

Một benchmark tốt tách ba loại chi phí:

- **Chi phí khởi tạo:** đọc dữ liệu, sắp xếp ban đầu, xây chỉ mục hoặc xây bảng tổng hợp.
- **Chi phí ổn định:** thời gian phục vụ thao tác thông thường khi cấu trúc đã được dựng.
- **Chi phí bất thường:** rehash, mở rộng mảng, cây bị thay đổi nhiều, stop-the-world GC, compaction, các thao tác gây xung đột khóa.

Nếu yêu cầu là p99 dưới 10 ms, trung bình 1 µs không đủ để kết luận: một đợt rehash hoặc tranh chấp khóa có thể làm chậm một phần nhỏ yêu cầu. Khi tải gần ngưỡng xử lý, thời gian chờ trong hàng đợi cũng có thể tăng mạnh dù thời gian xử lý mỗi phép toán không đổi.

## 7. Ba tình huống lựa chọn mẫu

### A. Từ điển khóa–giá trị trực tuyến

**Đầu vào:** vài triệu khóa, phần lớn thao tác là lấy hoặc cập nhật theo khóa chính xác, hầu như không hỏi khoảng, RAM còn đủ. Ứng viên thường là bảng băm vì tra cứu và cập nhật trung bình nhanh. Cần xác nhận hàm băm, hệ số tải, số byte mỗi phần tử, hành vi rehash và rủi ro khóa do người dùng không tin cậy cung cấp.

Nếu xuất hiện yêu cầu “liệt kê 100 khóa kế tiếp theo thứ tự”, bảng băm đơn lẻ không còn giải quyết hiệu quả. Có thể chuyển sang cây cân bằng hoặc duy trì một chỉ mục có thứ tự riêng. Chỉ mục phụ làm tăng bộ nhớ và chi phí ghi, nên phải thêm nó vào bảng quyết định.

### B. Mảng số phục vụ nhiều truy vấn đoạn

**Đầu vào:** một triệu số, hệ thống đọc tổng trên nhiều đoạn `[l,r)`, dữ liệu ban đầu cố định. Tổng tiền tố cần bộ nhớ `O(N)`, xây dựng `O(N)` và truy vấn `O(1)`.

Khi bắt đầu có cập nhật điểm liên tục, chi phí tái xây bảng tiền tố tăng. Nếu cần cộng tại điểm và tổng đoạn, Fenwick tree là ứng viên phù hợp. Nếu cần `min`/`max` động cùng các kiểu cập nhật phức tạp hơn, cân nhắc segment tree tương ứng. Quyết định phụ thuộc cả **phép gộp** chứ không chỉ tỉ lệ đọc/ghi.

### C. Biểu diễn đồ thị thay đổi theo mật độ

**Đầu vào:** đồ thị `V` đỉnh, `E` cạnh. Danh sách kề dùng `O(V+E)` bộ nhớ, phù hợp đồ thị thưa và thuật toán duyệt cạnh. Ma trận kề dùng `O(V^2)` bộ nhớ, kiểm tra có cạnh `(u,v)` trong `O(1)` và có thể thuận lợi ở đồ thị dày hoặc khi kiểm tra cặp đỉnh rất nhiều; duyệt láng giềng một đỉnh bằng cách quét hàng tốn `O(V)`.

Với `V = 100.000`, ma trận bit cho mọi cặp đỉnh cần khoảng `10^10` bit, tức `1,25 GB` theo hệ thập phân, chưa tính overhead. Nếu chỉ có vài trăm nghìn cạnh, danh sách kề thường tiết kiệm hơn nhiều. Ngược lại, trên đồ thị có `V` nhỏ, dày đặc và nhiều phép hỏi tồn tại cạnh, ma trận có thể hợp lý. Sự khác biệt nằm ở **tích các chiều dữ liệu, mật độ và tải thao tác**.

## 8. Lỗi thường gặp khi lập bảng

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ so `O(1)` và `O(log N)` | Bỏ qua locality, hệ số hằng, I/O và thời gian tăng đột biến | Dùng độ phức tạp để sàng lọc, benchmark để xếp hạng |
| Chọn theo thao tác thường gặp nhất | Một thao tác hiếm nhưng đắt chi phối tổng thời gian | Tính chi phí có trọng số của **mọi** thao tác quan trọng |
| Chỉ tính kích thước dữ liệu thô | Vượt RAM do bucket, con trỏ, vùng đệm hoặc bản sao | Đo RAM đỉnh và tính theo `N_max` |
| Dùng bộ nhớ trung bình thay cho đỉnh | OOM lúc rehash hoặc rebuild | Ghi rõ cách mở rộng và bộ nhớ tạm |
| Bỏ qua yêu cầu thứ tự/khóa trùng | Cấu trúc trả sai ngữ nghĩa ứng dụng | Kiểm tra khả năng và bất biến trước khi chấm điểm |
| So số đo ở quy mô hoặc môi trường khác nhau | Kết luận không phản ánh tải thực | Cùng môi trường, cùng dữ liệu và trace công bằng |
| Đánh đồng thời gian trung bình với p99/xấu nhất | Gặp độ trễ đột biến dù điểm trung bình đẹp | Đo phân vị và phân tích trường hợp xấu nhất |
| Không xét tăng trưởng và tải thay đổi | Quyết định nhanh chóng lạc hậu | Đặt ngưỡng và thời điểm xem xét lại |

Đặc biệt, hãy phân biệt **trung bình**, **khấu hao**, **kỳ vọng** và **xấu nhất**: thêm cuối mảng động có `O(1)` khấu hao dù một lần mở rộng tốn `O(N)`; bảng băm có `O(1)` kỳ vọng trong giả thiết thích hợp nhưng vẫn có trường hợp xấu; cây AVL/red-black cung cấp giới hạn `O(log N)` xấu nhất cho các thao tác chuẩn. Các khái niệm này ảnh hưởng trực tiếp đến khả năng đáp ứng yêu cầu độ trễ.

## 9. Bài tập tự đánh giá

1. Một dịch vụ có 99% tra cứu theo khóa, 1% chèn; không cần thứ tự và còn nhiều RAM. Hãy đề xuất cấu trúc ban đầu và nêu ba điều kiện cần kiểm chứng trước khi chốt.
2. Một triệu cặp số nguyên 64 bit cần ít nhất bao nhiêu byte để chứa **riêng payload**? Có thể dùng con số đó làm ngân sách RAM của hash map không?
3. Mảng đã sắp xếp chứa khoảng một triệu phần tử; trong một đợt có 50.000 lần chèn ở vị trí trải đều. Vì sao `O(log N)` cho tìm kiếm không đủ để chọn mảng?
4. Khi ngân sách RAM đỉnh là `64 MiB`, hãy dùng bảng giả định ở mục 5 để xác định ứng viên còn hợp lệ và vấn đề hiệu năng vẫn phải xét.
5. Một biểu diễn đồ thị có `V=100.000` và `E=200.000`. Nếu thuật toán thường duyệt mọi cạnh đi ra từ mỗi đỉnh, nên ưu tiên danh sách kề hay ma trận kề? Vì sao?
6. Hai ứng viên có trung bình lần lượt 0,8 ms và 1,0 ms, nhưng p99 là 35 ms và 4 ms. Dịch vụ yêu cầu p99 dưới 10 ms nên chọn theo tiêu chí nào?

**Gợi ý đáp án:** (1) Bảng băm; kiểm tra phân phối khóa/va chạm, bộ nhớ đỉnh khi rehash, tải thực và p99. (2) `16.000.000` byte, khoảng `15,26 MiB`; không, vì còn bucket, metadata và bộ nhớ tạm. (3) Chèn cần dời nhiều phần tử, có thể chi phối toàn bộ tải dù tìm nhanh. (4) Chỉ mảng đã sắp xếp với 48 MiB hợp lệ theo RAM; cần kiểm tra thao tác chèn 250 µs giả định có vi phạm yêu cầu độ trễ không. (5) Danh sách kề vì `O(V+E)` bộ nhớ và duyệt láng giềng theo số cạnh; ma trận cần `O(V^2)` ô. (6) Ứng viên có p99 = 4 ms nếu đáp ứng các ràng buộc khác, vì yêu cầu p99 là giới hạn cứng.

Lập bảng quyết định là một hoạt động có thể lặp lại: **xác định chức năng → đo khối lượng dữ liệu và tải → loại phương án không hợp lệ → đo ứng viên → ghi lựa chọn cùng điều kiện xem xét lại**. Bảng tốt giúp đội phát triển giải thích lựa chọn cấu trúc dữ liệu bằng yêu cầu và bằng chứng, thay vì dựa vào một độ phức tạp Big-O riêng lẻ.
