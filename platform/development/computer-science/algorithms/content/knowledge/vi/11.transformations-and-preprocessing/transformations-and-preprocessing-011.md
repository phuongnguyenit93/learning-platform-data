# Đánh giá khi chi phí tiền xử lý không đáng với số truy vấn

Nhiều thuật toán đổi **thời gian chuẩn bị** lấy **truy vấn nhanh hơn**: tính mảng tổng tiền tố để trả tổng đoạn, sắp xếp để tìm kiếm nhị phân, xây bảng băm để tra cứu, tạo sparse table để hỏi giá trị nhỏ nhất một đoạn, hoặc lập chỉ mục cho dữ liệu lớn. Những kỹ thuật này rất hữu ích khi có **nhiều truy vấn trên dữ liệu ít thay đổi**. Nhưng nếu chỉ có một vài truy vấn, mỗi truy vấn xét rất ít phần tử, dữ liệu thường xuyên cập nhật, hoặc bộ nhớ hạn chế, việc chuẩn bị cấu trúc phụ có thể tốn hơn rất nhiều so với giải trực tiếp.

Bài học thuộc nhóm **Biến đổi và tiền xử lý**. Mục tiêu không phải học thuộc “prefix sum `O(1)` mỗi truy vấn” mà biết trả lời câu hỏi quan trọng hơn:

> **Tính cả vòng đời dữ liệu và số truy vấn thực tế, liệu khoản đầu tư tiền xử lý có được bù lại không?**

Ta sẽ lập mô hình tổng chi phí, tìm ngưỡng hòa vốn, so sánh các phương án, xét tác động của cập nhật, xây một bộ chọn chiến lược Java 17+ và kiểm thử các kết quả bằng một cách độc lập.

## 1. Phân biệt chi phí dựng cấu trúc và chi phí trả truy vấn

Giả sử dữ liệu gốc có kích thước `n`, cần trả `q` truy vấn. Có hai hướng:

- **Xử lý trực tiếp (on-demand):** Mỗi truy vấn đọc dữ liệu gốc và tính kết quả ngay, không xây chỉ mục toàn cục.
- **Tiền xử lý (preprocessing):** Trả một khoản chi phí ban đầu để xây cấu trúc hỗ trợ, sau đó trả lời mỗi truy vấn với ít việc hơn.

Gọi:

- `D(n)`: chi phí trung bình của một truy vấn trực tiếp, với **phân bố truy vấn đang xét**.
- `P(n)`: chi phí dựng cấu trúc tiền xử lý.
- `F(n)`: chi phí của một truy vấn trên cấu trúc đã dựng.
- `M(n)`: bộ nhớ phụ dùng để giữ cấu trúc tiền xử lý.
- `q`: số truy vấn **thực sự sẽ chạy trên cùng phiên bản dữ liệu**.

Trong mô hình đơn giản, dữ liệu không thay đổi và mỗi truy vấn tương đương nhau:

```text
T_direct(q) = q * D(n)
T_pre(q)    = P(n) + q * F(n)
```

Tiền xử lý có lợi về tổng công việc khi:

```text
P(n) + q*F(n) < q*D(n)

=> q*(D(n) - F(n)) > P(n)

=> q > P(n) / (D(n) - F(n))   nếu D(n) > F(n)
```

Nếu `D(n)≤F(n)`, mô hình này **không có ngưỡng truy vấn dương** đủ để bù khoản tiền xử lý `P(n)>0`. Nếu `D(n)>F(n)`, điểm hòa vốn là nơi chi phí trực tiếp bằng chi phí tiền xử lý + truy vấn; cần **vượt** điểm đó để có lợi thật sự. Nếu hai chiến lược ngang nhau về chi phí ước tính, ưu tiên phương án ít bộ nhớ/phức tạp hơn, trừ khi có ràng buộc khác.

**Điểm cần nhớ:** `O(1)` mỗi truy vấn không có nghĩa **tổng chương trình `O(1)`**. Khi xây prefix sum `O(n)` rồi trả một truy vấn `O(1)`, toàn bộ công việc vẫn `O(n)`, trong khi quét đúng ba phần tử có thể chỉ tốn ba bước.

### Khi chi phí của mỗi truy vấn không giống nhau

Với truy vấn `i` có chi phí trực tiếp `D_i`, công thức đúng hơn là:

```text
T_direct = sum(D_i), i=1..q
T_pre    = P + sum(F_i), i=1..q
```

Do đó **số truy vấn đơn thuần không đủ**. Mười truy vấn trên các đoạn chỉ dài 1–2 phần tử có thể rẻ hơn một truy vấn quét toàn bộ dữ liệu; mười truy vấn quét đoạn dài có thể đảo ngược kết luận.

Các biểu thức trên là **mô hình chi phí**, không phải dự đoán chính xác thời gian chạy bằng nanosecond. Lệnh cấp phát, cache, locality, kiểm tra biên, GC, JIT, chi phí so sánh/hash, việc làm nóng dữ liệu và phân bố input đều làm thay đổi hằng số. Dùng Big-O để loại phương án rõ ràng không phù hợp, rồi đo trên khối lượng thật khi hiệu năng là yêu cầu quan trọng.

## 2. Ví dụ nền tảng: tổng đoạn trực tiếp hay mảng tổng tiền tố?

Cho mảng có thể chứa cả số âm, cần trả tổng đoạn **bao gồm hai đầu mút** `[l,r]` với `0≤l≤r<n`.

### Cách A — tính trực tiếp cho từng truy vấn

```java
static long directSum(int[] a, int left, int right) {
    long total = 0;
    for (int i = left; i <= right; i++) {
        total += a[i];
    }
    return total;
}
```

Đây là **đoạn phương thức minh họa**, chưa phải chương trình Java độc lập. Truy vấn dài `L=r−l+1` thực hiện `L` lần cộng/đọc phần tử, nên:

- Thời gian một truy vấn: `Θ(L)`, **không nhất thiết `Θ(n)`**.
- Bộ nhớ phụ: `O(1)`.
- Không cần chuẩn bị; nếu giá trị tại một vị trí thay đổi, lần quét tiếp theo đọc giá trị mới.

### Cách B — dựng tổng tiền tố một lần

Đặt `prefix[0]=0` và:

```text
prefix[i+1] = prefix[i] + a[i]       (0 <= i < n)
sum(l,r)    = prefix[r+1] - prefix[l]
```

Ví dụ:

```text
a      = [ 3, -1, 4, 1, 5, -9, 2, 6 ]
prefix = [ 0,  3, 2, 6, 7, 12, 3, 5, 11 ]
```

Tổng `[2,5]` là `prefix[6]−prefix[2]=3−2=1`, đúng bằng `4+1+5−9=1`.

- Xây prefix: `Θ(n)` thời gian, mảng `long[n+1]` dùng `Θ(n)` bộ nhớ.
- Mỗi truy vấn tổng đoạn: `Θ(1)` thời gian, hai lần đọc prefix và một phép trừ.
- Với `q` truy vấn: `Θ(n+q)` thay vì `Θ(∑L_i)` của cách trực tiếp.

Dùng `long` cho prefix và tổng để tránh tràn `int` khi cộng nhiều số nguyên; việc dùng `long` là một phần hợp đồng dữ liệu, không làm mọi overflow tùy ý biến mất với các kiểu đầu vào rộng hơn.

### Khi nào prefix “không đáng”?

Xét mô hình minh họa **đếm đơn vị truy cập/tính toán tương đương**:

- Quét trực tiếp: xấp xỉ `L` đơn vị cho đoạn dài `L`.
- Xây prefix: xấp xỉ `n` đơn vị.
- Mỗi truy vấn prefix: xấp xỉ `2` đơn vị đọc prefix, bỏ qua các chi phí nhỏ khác.

Khi các đoạn có độ dài trung bình `L>2`:

```text
q * L > n + 2*q
=> q > n / (L - 2)
```

Ví dụ `n=100.000` và độ dài trung bình `L=10`: phải có **hơn 12.500 truy vấn** mới có lợi theo mô hình đơn vị này. Nếu chỉ có `50` truy vấn, việc quét 10 phần tử mỗi lần (tổng khoảng `500` phần tử) rõ ràng ít công việc hơn xây một mảng prefix cho 100.000 phần tử.

Nếu `L=500`, ngưỡng là `q>100.000/498≈200,8`, tức từ **201 truy vấn** theo mô hình. Một chương trình có khoảng 1.000 truy vấn loại này có lý do để dùng prefix, nếu dữ liệu tĩnh và bộ nhớ đủ.

**Không diễn giải số 12.500 hoặc 201 thành benchmark thực tế:** Công thức cố ý gán trọng số đơn giản để minh họa quyết định. Trên máy thật, một bước cộng, một lần truy cập bộ nhớ, cấp phát mảng, nhánh điều kiện và bộ nhớ đệm **không** có chi phí đồng nhất. Điều quan trọng là **tính cả n, độ dài truy vấn và số lần truy vấn**, không chỉ nhãn `O(1)`.

### Khi độ dài mỗi đoạn khác nhau

Không cần lấy trung bình nếu đã biết toàn bộ truy vấn:

```text
directUnits = sum(right_i - left_i + 1)
prefixUnits = n + 2*q

Chọn PREFIX trong mô hình khi directUnits > prefixUnits.
```

Với `a=[3,-1,4,1,5,-9,2,6]`:

| Bộ truy vấn | Số lượt `q` | Tổng độ dài quét trực tiếp | `n+2q` | Phương án ít đơn vị hơn |
| --- | ---: | ---: | ---: | --- |
| `[0,0]`, `[3,4]`, `[5,7]` | 3 | `1+2+3=6` | `8+6=14` | **Quét trực tiếp** |
| `[2,5]` lặp lại 10 lần | 10 | `10×4=40` | `8+20=28` | **Prefix** trong hai cách đang so |
| Không có truy vấn | 0 | `0` | `8` | **Không tiền xử lý** |

Trường hợp truy vấn `[2,5]` lặp lại y hệt còn có **phương án thứ ba**: tính một lần rồi **cache đúng câu trả lời**, sau đó tái sử dụng nếu input không đổi. Khi nhiều truy vấn giống nhau, cache theo khóa truy vấn có thể tốt hơn cả quét lặp lẫn prefix toàn mảng. Bảng trên cố ý chỉ so sánh **hai chiến lược** để dạy cách tính điểm hòa vốn.

## 3. Vì sao tiền xử lý có thể lãng phí dù truy vấn nhanh?

Có bốn nguồn lãng phí khác nhau:

1. **Số truy vấn nhỏ:** Chi phí xây cấu trúc chưa được thu hồi. Một lần hỏi min của 20 phần tử không cần sparse table cho mảng dài một triệu.
2. **Truy vấn rẻ sẵn:** Nếu đoạn cần hỏi rất ngắn, hoặc giá trị cần tìm thường nằm sớm trong quét tuyến tính, lợi ích `D−F` nhỏ.
3. **Dữ liệu thay đổi liên tục:** Dữ liệu đã tiền xử lý có thể **cũ**; cập nhật chỉ mục, dựng lại hoặc đồng bộ snapshot tạo chi phí mới.
4. **Bộ nhớ và hằng số lớn:** Mảng, bảng băm, object, pointer, GC và cache làm hiệu năng thực tế tệ hơn mô hình bậc lớn trong một số trường hợp.

Ngoài tổng thời gian, yêu cầu của ứng dụng còn có thể là **trả lời truy vấn đầu tiên nhanh**, khởi động ngắn, bộ nhớ thấp hoặc đảm bảo không để cấu trúc stale. Một chỉ mục có throughput tốt sau khi dựng chưa chắc thỏa mục tiêu **độ trễ đầu tiên (cold-start latency)**.

### Nếu truy vấn có thể dừng sớm

Giả sử câu hỏi “có giá trị `x` trong mảng chưa sắp không?” và `x` có thể xuất hiện ở chỉ số đầu tiên. Quét tuyến tính có **trường hợp tốt nhất `O(1)`**, xấu nhất `O(n)`. Xây bảng băm vẫn phải đọc toàn mảng `O(n)` kỳ vọng. Không nên dùng chi phí trung bình `n` cho mọi truy vấn nếu dữ liệu thực tế khiến tìm kiếm hay dừng sớm.

Điều tương tự đúng với thuật toán kiểm tra tính khả thi: nếu một vài phần tử đầu đã cung cấp chứng cứ để trả `false`, tạo toàn bộ chỉ mục trước một truy vấn như vậy có thể tốn hơn cách kiểm trực tiếp.

## 4. So sánh nhiều loại tiền xử lý quen thuộc

| Bài toán | Không tiền xử lý | Tiền xử lý và truy vấn | Khi dễ **không đáng** |
| --- | --- | --- | --- |
| Tổng đoạn `[l,r]` trên mảng tĩnh | Quét `O(L)` | Prefix build `O(n)`, hỏi `O(1)`, space `O(n)` | Ít truy vấn hoặc đoạn rất ngắn |
| Tìm giá trị trong mảng chưa sắp | Quét `O(n)` xấu nhất, có thể dừng sớm | `HashSet`: build `O(n)` kỳ vọng, hỏi `O(1)` kỳ vọng, space `O(n)` | Một vài lần tìm; RAM hạn chế; cần tần suất thay vì có/không |
| Tìm nhiều khóa trên mảng chưa sắp | Quét `O(n)`/khóa | Sao chép & sort `O(n log n)`, binary search `O(log n)`/khóa | Một vài khóa, phải bảo toàn thứ tự/chỉ số gốc và không có ngân sách sort |
| Min/max đoạn tĩnh | Quét `O(L)` | Sparse table build `O(n log n)`, space `O(n log n)`, min query `O(1)` | Ít truy vấn hoặc cần sửa giá trị thường xuyên |
| Min/sum đoạn có cập nhật điểm | Quét `O(L)`, cập nhật mảng `O(1)` | Segment tree build `O(n)`, truy vấn & cập nhật `O(log n)`, space `O(n)` | Ít truy vấn và cập nhật, hoặc chỉ hỏi đoạn rất ngắn |
| Tổng hình chữ nhật trên ma trận tĩnh | Quét `O(diện tích hình)` | Prefix 2D build `O(RC)`, hỏi `O(1)`, space `O(RC)` | Chỉ hỏi vài hình nhỏ, ma trận quá lớn |
| Câu hỏi “bao nhiêu lần giá trị x xuất hiện?” | Đếm tuyến tính `O(n)` | `HashMap<value,count>` build `O(n)` kỳ vọng; hỏi `O(1)` kỳ vọng | Chỉ một vài giá trị; hash map cấp phát quá đắt |
| Nhiều truy vấn đường đi trên đồ thị | Chạy thuật toán tìm đường theo nguồn/query | Có thể tiền xử lý cấu trúc phù hợp với loại đồ thị, trọng số và số truy vấn | Chỉ một vài nguồn; bộ nhớ chỉ mục lớn; đồ thị liên tục thay đổi |

**Đừng nhầm “có tồn tại” với “đếm số lần xuất hiện”.** `HashSet` loại bỏ bản sao và chỉ lưu sự tồn tại; muốn đếm cần bản đồ tần suất hoặc cấu trúc tương ứng. Tương tự, binary search sau sort có thể tìm nhóm trùng bằng lower/upper bound nhưng phải tính cả chi phí sort, và việc sort trực tiếp có thể làm mất **chỉ số gốc**.

**Sparse table** với phép `min` dùng hai đoạn độ dài `2^k` có thể **chồng lên nhau** vì `min(x,x)=x` (tính idempotent); không được lấy ngay công thức truy vấn `O(1)` này rồi áp cho phép **cộng** trên hai đoạn chồng, vì sẽ đếm đôi phần giao nhau.

**Segment tree** thích hợp khi cập nhật, nhưng nếu chỉ có một lần lấy tổng trên đoạn dài 5 thì việc dựng cả cây `O(n)` để tiết kiệm từ 5 bước xuống `O(log n)` là không cần thiết.

## 5. Tính cả cập nhật: chi phí tiền xử lý có thể phải trả nhiều lần

Mô hình `P+qF` giả định **dữ liệu tĩnh** hoặc chỉ mục luôn cập nhật miễn phí. Nếu có `u` cập nhật, phải so sánh cả chi phí duy trì:

```text
T_direct = sum(queryDirectCost_i) + sum(updateDirectCost_j)

T_index  = P_initial
         + sum(queryIndexedCost_i)
         + sum(indexMaintenanceCost_j)
         + các lần rebuild nếu không cập nhật tăng dần được
```

Ví dụ mảng tổng tiền tố với thay đổi `a[pos] += delta`:

- Mảng gốc: cập nhật một phần tử là `O(1)`.
- Prefix tĩnh: mọi `prefix[i]` với `i>pos` phải cộng `delta`, hoặc cần dựng lại. Cập nhật này có thể mất **`Θ(n)`** trong trường hợp xấu.
- Nếu luôn trả truy vấn theo mảng prefix **cũ** mà không cập nhật, kết quả có thể **sai**.

Với ví dụ:

```text
a ban đầu       = [3,-1,4,1,5,-9,2,6]
sum(2,4)        = 4+1+5 = 10

sửa a[3] từ 1 lên 11
sum(2,4) mới    = 4+11+5 = 20

prefix cũ        vẫn cho 10  -> sai với dữ liệu hiện tại
```

Nếu có cập nhật điểm và hỏi tổng đoạn thường xuyên, có thể cân nhắc **Fenwick tree (Binary Indexed Tree)**: xây `O(n)` bằng thuật toán tuyến tính phù hợp (hoặc `O(n log n)` nếu thêm lần lượt), cập nhật `O(log n)`, tổng tiền tố `O(log n)`, tổng đoạn từ hai tổng tiền tố `O(log n)`. Segment tree có phân tích tương tự cho nhiều loại phép hợp đoạn hơn.

**Nhưng Fenwick/segment tree cũng không tự động đáng dùng.** Nếu chỉ có một vài truy vấn và cập nhật, quét trực tiếp cộng với chỉnh phần tử gốc có thể ít công việc hơn dựng và duy trì cây.

### Mức độ “tĩnh” phải được hiểu theo thời gian sống của dữ liệu

Cùng một mảng được sử dụng bởi:

- Một hàm nhận 3 truy vấn rồi kết thúc;
- Một dịch vụ nhận 10.000 truy vấn trước khi dữ liệu thay đổi;
- Một ứng dụng sửa mảng sau mỗi truy vấn;
- Nhiều phiên đồng thời, mỗi phiên có một snapshot riêng.

Bốn tình huống có **ngưỡng hòa vốn khác nhau**. Nếu phiên bản dữ liệu bị thay đổi thường xuyên đến mức chỉ mục phải dựng lại nhiều lần, không thể cộng mọi truy vấn suốt tháng vào một `q` duy nhất mà bỏ qua số lượt rebuild. **Hãy tính `q` theo từng thời kỳ mà chỉ mục còn hợp lệ**, hoặc tính chính xác chi phí duy trì chỉ mục xuyên các cập nhật.

Với cache truy vấn, key phải gắn với **phiên bản dữ liệu** hoặc có cơ chế invalidation phù hợp. Cache theo `(l,r)` mà không cập nhật khi dữ liệu thay đổi sẽ trả kết quả cũ dù công thức cộng hoàn toàn đúng.

## 6. Số truy vấn biết trước (offline) và truy vấn đến dần (online)

**Offline:** Biết trước toàn bộ các truy vấn hoặc ít nhất thống kê độ dài và số lượng. Ta có thể:

- Tính chính xác `∑L_i` để so sánh với chi phí tạo prefix.
- Nhận diện các truy vấn giống nhau để cache kết quả.
- Nhóm truy vấn theo vùng, thứ tự hoặc cấu trúc phù hợp; đôi khi một thuật toán offline đặc thù tiết kiệm hơn cả dựng index toàn cục.
- Quyết định một lần trước khi bắt đầu thực thi, với ngưỡng bộ nhớ cụ thể.

**Online:** Truy vấn đến từng cái và không biết trước tổng số. Không thể dựa vào một `q` tương lai không chắc chắn để tuyên bố tiền xử lý chắc chắn đáng dùng. Các chiến lược thực tế có thể là:

1. Ban đầu trả trực tiếp, theo dõi **số truy vấn và độ dài/chi phí thực tế**.
2. Ước lượng **lượng truy vấn tương lai** trước khi dữ liệu bị cập nhật hoặc phiên kết thúc; chỉ dựng index khi số việc dự kiến còn lại đủ bù khoản dựng mới.
3. Có thể dựng **lười (lazy)** ở truy vấn đầu tiên thực sự cần, thay vì khi khởi động ứng dụng.
4. Tái sử dụng chỉ mục cho các truy vấn tiếp theo; có đường invalidation khi dữ liệu thay đổi.
5. Đặt giới hạn bộ nhớ; nếu index không còn được dùng, cân nhắc giải phóng.

**Bẫy tính toán:** Những truy vấn đã trả trực tiếp **đã trả chi phí rồi**. Khi đang cân nhắc dựng index ở thời điểm `t`, không lấy toàn bộ chi phí trong quá khứ làm lý do chắc chắn để dựng; chỉ lợi ích từ **những truy vấn tương lai** mới có thể bù khoản chuẩn bị mới. Nếu build trễ, mô hình phải cộng cả chi phí lịch sử vào tổng đã thực hiện, nhưng quyết định hiện tại dựa vào phần **còn lại**.

Một cách kiểm soát thực tế là định nghĩa `P99` của thời gian chuẩn bị và ngân sách RAM trước khi quyết định. Nếu hệ thống cần phản hồi truy vấn đầu tiên trong 10 ms, một tiền xử lý mất vài giây có thể bị loại **ngay cả khi tổng throughput sau đó cao hơn**.

## 7. Mô hình “đầu tư – hòa vốn” với số liệu cụ thể

Giả sử một tác vụ có:

- `n=100.000` số nguyên tĩnh;
- `q` truy vấn tổng đoạn;
- Mỗi truy vấn trung bình quét `L` phần tử;
- Mỗi lần quét trực tiếp tốn `L` đơn vị; dựng prefix tốn `n` đơn vị; hỏi qua prefix tốn `2` đơn vị.

| Tình huống | `q` | `L` | Direct `q·L` | Prefix `n+2q` | Kết luận theo mô hình |
| --- | ---: | ---: | ---: | ---: | --- |
| Một vài đoạn ngắn | 10 | 5 | 50 | 100.020 | Trực tiếp ít việc hơn rất nhiều |
| Vài chục đoạn dài | 50 | 1.000 | 50.000 | 100.100 | Trực tiếp ít việc hơn |
| Nhiều đoạn dài | 500 | 1.000 | 500.000 | 101.000 | Prefix ít việc hơn |
| Rất nhiều đoạn cực ngắn | 10.000 | 2 | 20.000 | 120.000 | Trực tiếp ít việc hơn |
| Nhiều đoạn trung bình | 1.000 | 200 | 200.000 | 102.000 | Prefix ít việc hơn |

**Giải thích:** Cột tổng truy vấn `q` tự nó không nói được phương án nào thắng; `L` và `n` thay đổi lợi ích. Một hệ thống có 10.000 truy vấn rất ngắn vẫn có thể không cần prefix, trong khi một hệ thống có 500 truy vấn dài đã đủ để hoàn vốn.

Các con số trong bảng là **đơn vị mô hình**, không phải số phép CPU chính xác hoặc thời gian mili giây. Trong triển khai có thêm giá của việc xét độ dài từng truy vấn, cấp phát mảng `long[]`, tính prefix, kiểm tra đầu vào và hiệu ứng cache.

### Không chỉ so bằng Big-O

Một bảng băm có expected lookup `O(1)` nhưng dùng bộ nhớ, boxing và tính hash; quét vài phần tử liên tục trong mảng thường rất thân thiện với CPU cache. Sắp xếp `O(n log n)` có thể tốn thêm bản sao và thay đổi thứ tự, khiến một bài tìm kiếm lẻ không còn đơn giản. Các tối ưu tiền xử lý có thể đáng giá **ở kích thước lớn và số lượt đủ nhiều**, không phải mọi `n,q`.

## 8. Java 17+ — bộ lập kế hoạch chọn quét hoặc prefix cho truy vấn offline

Chương trình dưới đây minh họa một quyết định có thể **kiểm chứng được**:

- Đầu vào là `int[] values` và tập truy vấn đóng `[l,r]` đã biết trước.
- `directSum` duyệt trực tiếp đoạn cần hỏi; `buildPrefix` tạo `long[]` và `prefixSum` trả tổng trong `O(1)`.
- `planAndAnswer` xác thực truy vấn, tính `directUnits=∑(r−l+1)` và `prefixUnits=n+2q`, rồi chọn **PREFIX nếu và chỉ nếu `directUnits>prefixUnits`**; ngược lại chọn **DIRECT**.
- Hai nhánh đều trả **mảng kết quả mới** và **không sửa input**. Đây là **mô hình quyết định bằng số đơn vị**, không phải máy đo thời gian thực.
- Khi dữ liệu đổi, prefix cũ cho kết quả stale; ví dụ cho thấy phải dựng lại hoặc dùng cấu trúc hỗ trợ cập nhật.
- Có kiểm thử exhaustive với mọi mảng độ dài `0..5` từ các giá trị `−2,−1,0,1,2`, và mọi đoạn hợp lệ, đối chiếu direct/prefix.

### Mã Java đầy đủ

Lưu tệp **PreprocessingCostDemo.java**:

```java
import java.util.Arrays;
import java.util.Objects;

public class PreprocessingCostDemo {
    record Plan(String strategy, long directUnits,
                long prefixUnits, long[] answers) {}

    record CheckCount(int arrays, long intervals) {}

    static void checkRange(int[] values, int left, int right) {
        Objects.requireNonNull(values, "values");
        if (left < 0 || left > right || right >= values.length) {
            throw new IllegalArgumentException("invalid [left,right]");
        }
    }

    static long directSum(int[] values, int left, int right) {
        checkRange(values, left, right);
        long sum = 0L;
        for (int i = left; i <= right; i++) {
            sum += values[i];
        }
        return sum;
    }

    static long[] buildPrefix(int[] values) {
        Objects.requireNonNull(values, "values");
        long[] prefix = new long[values.length + 1];
        for (int i = 0; i < values.length; i++) {
            prefix[i + 1] = prefix[i] + values[i];
        }
        return prefix;
    }

    static long prefixSum(long[] prefix, int left, int right) {
        Objects.requireNonNull(prefix, "prefix");
        // Vì prefix có độ dài n+1, đoạn hợp lệ cần right<n.
        if (left < 0 || left > right || right + 1 >= prefix.length) {
            throw new IllegalArgumentException("invalid [left,right]");
        }
        return prefix[right + 1] - prefix[left];
    }

    // Có sẵn các truy vấn: chọn theo lượng việc ước tính.
    static Plan planAndAnswer(int[] values, int[][] queries) {
        Objects.requireNonNull(values, "values");
        Objects.requireNonNull(queries, "queries");

        long directUnits = 0L;
        for (int[] query : queries) {
            if (query == null || query.length != 2) {
                throw new IllegalArgumentException("query must have 2 ends");
            }
            int left = query[0], right = query[1];
            checkRange(values, left, right);
            directUnits += (long) right - left + 1L;
        }

        long prefixUnits = (long) values.length + 2L * queries.length;
        long[] answers = new long[queries.length];

        if (directUnits <= prefixUnits) {
            for (int i = 0; i < queries.length; i++) {
                answers[i] = directSum(
                    values, queries[i][0], queries[i][1]);
            }
            return new Plan("DIRECT", directUnits, prefixUnits, answers);
        }

        long[] prefix = buildPrefix(values);
        for (int i = 0; i < queries.length; i++) {
            answers[i] = prefixSum(
                prefix, queries[i][0], queries[i][1]);
        }
        return new Plan("PREFIX", directUnits, prefixUnits, answers);
    }

    // Sinh mọi input độ dài 0..5 từ 5 giá trị;
    // đếm 3906 mảng, 53955 khoảng [l,r] hợp lệ.
    static CheckCount checkSmallCases() {
        int variations = 1;
        int arrays = 0;
        long intervals = 0L;

        for (int n = 0; n <= 5; n++) {
            for (int encoded = 0; encoded < variations; encoded++) {
                int[] input = new int[n];
                int code = encoded;
                for (int i = 0; i < n; i++) {
                    input[i] = code % 5 - 2;
                    code /= 5;
                }
                int[] before = input.clone();
                long[] prefix = buildPrefix(input);

                int[][] all = new int[n * (n + 1) / 2][2];
                int next = 0;
                for (int left = 0; left < n; left++) {
                    for (int right = left; right < n; right++) {
                        long actualDirect = directSum(input, left, right);
                        long actualPrefix = prefixSum(prefix, left, right);
                        if (actualDirect != actualPrefix) {
                            throw new AssertionError("mismatched sums");
                        }
                        all[next++] = new int[]{left, right};
                        intervals++;
                    }
                }

                Plan planned = planAndAnswer(input, all);
                for (int i = 0; i < all.length; i++) {
                    if (planned.answers()[i] !=
                            directSum(input, all[i][0], all[i][1])) {
                        throw new AssertionError("planner mismatch");
                    }
                }

                if (n > 0) {
                    int[][] repeated = new int[10][2];
                    for (int i = 0; i < repeated.length; i++) {
                        repeated[i] = new int[]{0, n - 1};
                    }
                    Plan plan = planAndAnswer(input, repeated);
                    long expected = directSum(input, 0, n - 1);
                    for (long answer : plan.answers()) {
                        if (answer != expected) {
                            throw new AssertionError("repeated mismatch");
                        }
                    }

                    // Với 10 đoạn dài n: 10*n > n+20 khi n>=3.
                    String expectedMethod = n >= 3 ? "PREFIX" : "DIRECT";
                    if (!expectedMethod.equals(plan.strategy())) {
                        throw new AssertionError("wrong method");
                    }
                }

                if (!Arrays.equals(input, before)) {
                    throw new AssertionError("input was modified");
                }
                arrays++;
            }
            variations *= 5;
        }
        return new CheckCount(arrays, intervals);
    }

    public static void main(String[] args) {
        int[] values = {3, -1, 4, 1, 5, -9, 2, 6};
        int[] untouched = values.clone();

        int[][] few = {{0, 0}, {3, 4}, {5, 7}};
        Plan small = planAndAnswer(values, few);
        System.out.println(
            "Few: " + small.strategy()
            + " | direct=" + small.directUnits()
            + " | prefix=" + small.prefixUnits()
            + " | " + Arrays.toString(small.answers()));

        int[][] many = new int[10][2];
        for (int i = 0; i < many.length; i++) {
            many[i] = new int[]{2, 5};
        }
        Plan large = planAndAnswer(values, many);
        System.out.println(
            "Many: " + large.strategy()
            + " | direct=" + large.directUnits()
            + " | prefix=" + large.prefixUnits()
            + " | first=" + large.answers()[0]
            + ", last=" + large.answers()[9]);

        Plan none = planAndAnswer(values, new int[0][2]);
        System.out.println(
            "No queries: " + none.strategy()
            + " | direct=" + none.directUnits()
            + " | prefix=" + none.prefixUnits()
            + " | " + Arrays.toString(none.answers()));

        int[] mutable = values.clone();
        long[] stale = buildPrefix(mutable);
        mutable[3] += 10; // Từ 1 thành 11.
        System.out.println(
            "Stale prefix [2,4]: " + prefixSum(stale, 2, 4));
        System.out.println(
            "Direct after update [2,4]: " + directSum(mutable, 2, 4));
        System.out.println(
            "Rebuilt prefix [2,4]: "
            + prefixSum(buildPrefix(mutable), 2, 4));

        System.out.println(
            "Input unchanged: " + Arrays.equals(values, untouched));

        CheckCount c = checkSmallCases();
        System.out.println(
            "Exhaustive: " + c.arrays()
            + " arrays, " + c.intervals() + " intervals OK");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 PreprocessingCostDemo.java
java PreprocessingCostDemo
```

Stdout dự kiến:

```text
Few: DIRECT | direct=6 | prefix=14 | [3, 6, -1]
Many: PREFIX | direct=40 | prefix=28 | first=1, last=1
No queries: DIRECT | direct=0 | prefix=8 | []
Stale prefix [2,4]: 10
Direct after update [2,4]: 20
Rebuilt prefix [2,4]: 20
Input unchanged: true
Exhaustive: 3906 arrays, 53955 intervals OK
```

### Ý nghĩa của kết quả

- Bộ `few` chỉ quét tổng cộng **6 phần tử** qua ba truy vấn, ít hơn **14 đơn vị** của phương án có prefix trong mô hình; chọn **DIRECT**.
- Bộ `many` hỏi đoạn dài 4 **10 lần**, nên direct là **40 đơn vị**, prefix là **8+2×10=28**; chọn **PREFIX**. Vì truy vấn lặp chính xác, cache kết quả một đoạn cũng có thể là phương án thực tế tốt hơn, nhưng không được cài trong ví dụ chỉ so hai chiến lược.
- Không có truy vấn: `q=0`, không nên phí `n` bước để dựng prefix.
- Khi thay `a[3]` từ `1` lên `11`, tổng `[2,4]` tăng từ 10 lên 20; **prefix cũ vẫn trả 10**. Dựng lại hoặc bảo trì cấu trúc cập nhật mới trả đúng.
- Hàm `checkSmallCases` tạo `1+5+25+125+625+3125=3906` mảng, trong đó mảng rỗng có 0 khoảng hợp lệ. Tổng số khoảng được kiểm là **53.955**, bằng tổng `5^n·n(n+1)/2` với `n=0..5`. Các kiểm tra so sánh trực tiếp, prefix và bộ lập kế hoạch; với truy vấn lặp cũng kiểm thử nhánh PREFIX khi có lợi trong mô hình.
- Chương trình không sửa mảng của người gọi khi lập kế hoạch, nhưng đoạn minh họa cập nhật dùng một **bản sao riêng `mutable`**. Các truy vấn không hợp lệ (ngoài biên, `left>right`) và input `null` được từ chối rõ ràng.

**Ranh giới mô hình:** `directUnits` và `prefixUnits` chỉ là phép đếm đại diện, chưa tính chi phí **quét tập truy vấn để ra quyết định** (`O(q)`), kiểm tra input, bộ nhớ mảng `long[]` và tác động CPU cache. Nếu gọi planner một lần trên tập truy vấn rất nhỏ, ngay bản thân công việc lập kế hoạch cũng có thể không đáng; khi đó chọn cách trực tiếp theo hợp đồng thay vì chạy một bộ tối ưu hóa phức tạp.

## 9. Cách đo công bằng khi có nhiều lựa chọn

Nếu cần ra quyết định hiệu năng cho một ứng dụng thật, phải đo **đúng khối lượng và vòng đời**, không chỉ một phép lookup:

1. **Xác định workload:** `n` là bao nhiêu, `q` trong một phiên là bao nhiêu, độ dài phân bố `L_i` ra sao, truy vấn có lặp, cập nhật xảy ra khi nào?
2. **Giữ cùng đầu ra và hợp đồng:** Cả hai phiên bản phải cho kết quả chính xác như nhau; không lấy phương án sửa input rồi so với phiên bản phải giữ nguyên input mà bỏ qua chi phí copy.
3. **Tính thời gian end-to-end:** Bao gồm lấy dữ liệu, cấp phát, xây index, query, bảo trì khi cập nhật và giải phóng nếu cần.
4. **Đo cả latency và throughput:** Lần đầu trả lời có đáp ứng SLA không? Sau khi warm-up, một nghìn truy vấn có nhanh hơn không?
5. **Theo dõi tài nguyên:** RAM đỉnh, lượng cấp phát, số lần GC, kích thước cache, khả năng nhiều phiên cùng có index.
6. **Thử các phân bố khác nhau:** Ít/nhiều truy vấn, đoạn ngắn/dài, thành công/thất bại khi tìm, giá trị lặp, gần biên, dữ liệu tĩnh/động.
7. **Lặp phép đo hợp lý:** JVM có JIT/warm-up và GC; đo nhiều lần, tách dữ liệu chuẩn bị và đo, tránh để compiler loại bỏ công việc vì kết quả không được dùng. Với benchmark Java nghiêm túc, cân nhắc công cụ phù hợp như JMH.
8. **Áp ràng buộc hệ thống:** Một phương án nhanh hơn 5% nhưng tốn gấp đôi RAM có thể không chấp nhận được khi chạy đồng thời hàng trăm phiên.

**Benchmark không thay thế chứng minh tính đúng.** Một phiên bản đọc prefix stale có thể “nhanh” nhưng trả sai. Hãy kiểm tra kết quả trên dữ liệu cập nhật rồi mới tin phép đo.

## 10. Những lỗi tư duy và triển khai phổ biến

**Lỗi 1 — Chỉ nhìn `O(1)` mỗi truy vấn.** Tổng chi phí phải gồm dựng `O(n)` hoặc `O(n log n)`, bộ nhớ và số lần truy vấn. Một truy vấn đơn lẻ có thể rẻ hơn nếu giải trực tiếp.

**Lỗi 2 — Đồng nhất mọi truy vấn có chi phí `O(n)`.** Tổng đoạn dài `L` quét `O(L)`, không phải lúc nào cũng quét toàn mảng. Phân bố độ dài truy vấn thay đổi điểm hòa vốn.

**Lỗi 3 — Đếm cả các truy vấn quá khứ để “hoàn vốn” cho index dựng ở hiện tại.** Những lần đã chạy không thể được tăng tốc ngược. Quyết định hiện tại cần ước lượng lợi ích **tương lai**.

**Lỗi 4 — Dùng `n` và `q` toàn hệ thống thay vì theo phiên bản dữ liệu.** Mỗi lần cập nhật có thể đòi bảo trì hoặc dựng lại index. Chỉ mục cũ không tự cập nhật theo dữ liệu mới.

**Lỗi 5 — Bỏ qua memory budget.** Một sparse table `O(n log n)` hoặc bảng băm nhiều object có thể không vừa RAM, dù lý thuyết truy vấn nhanh.

**Lỗi 6 — So sánh hai phương án thiếu chi phí copy.** Nếu sort không được sửa input thì phải tạo bản sao; nếu giữ chỉ số gốc còn cần ánh xạ chỉ số hoặc cấu trúc phụ.

**Lỗi 7 — Dùng `HashSet` để đếm tần suất.** Set chỉ có thông tin tồn tại; muốn số bản sao cần map đếm hoặc giải pháp khác.

**Lỗi 8 — Quên invalidate cache và prefix.** Kết quả từ dữ liệu trước cập nhật có thể sai; cần thông tin phiên bản hoặc cấu trúc hỗ trợ cập nhật.

**Lỗi 9 — Khẳng định `HashMap` luôn `O(1)`.** Thời gian tra cứu là `O(1)` kỳ vọng trong mô hình băm thông thường; va chạm, hashing, kiểu khóa và cấu trúc cài đặt ảnh hưởng hiệu năng.

**Lỗi 10 — Tự động chọn index cho mọi input.** Một hệ thống với số truy vấn, độ dài đoạn và khả năng cập nhật thay đổi có thể cần ngưỡng quyết định, lazy build hoặc một chiến lược khác.

**Lỗi 11 — Không đếm truy vấn giống hệt.** Nếu cùng một câu hỏi được hỏi lặp với dữ liệu tĩnh, memoization/caching có thể tránh tính lại với chi phí chuẩn bị thấp hơn một index toàn mảng.

**Lỗi 12 — Nhầm mô hình đơn vị với thời gian thực.** Điều kiện `∑L_i>n+2q` chỉ là một giả định minh họa. Không được tuyên bố đó là ngưỡng tối ưu chính xác cho mọi JVM và CPU.

## 11. Bài tự luyện

**Bài 1 — Tìm điểm hòa vốn.** Có `n=120.000` phần tử, mỗi truy vấn tổng đoạn quét trung bình `L=302` phần tử. Dùng mô hình `P=n, F=2` để tính số truy vấn nguyên tối thiểu khiến prefix ít đơn vị hơn quét.

*Gợi ý:* `q>120.000/(302−2)=400`, nên từ **401 truy vấn**.

**Bài 2 — Nhiều truy vấn rất ngắn.** Có 20.000 truy vấn, mỗi truy vấn chỉ hỏi đúng một phần tử. Vì sao prefix `O(1)` và direct `O(1)` không cho phép kết luận xây prefix đáng giá? Tính hai tổng theo mô hình đơn vị.

**Bài 3 — Dữ liệu thường xuyên thay đổi.** Một mảng dài 100.000 có 100 truy vấn và 100 cập nhật điểm đan xen. So sánh quét trực tiếp, prefix phải dựng lại, Fenwick tree và segment tree. Cần biết thêm phân bố độ dài truy vấn gì để kết luận?

**Bài 4 — Tìm kiếm có nhiều khóa.** Với mảng chưa sắp, so sánh linear search, sao chép + sort + binary search, và `HashSet` khi `q=1` và khi `q=100.000`. Nếu cần tìm **chỉ số xuất hiện đầu tiên của một giá trị**, chiến lược nào cần thay đổi?

**Bài 5 — Prefix bị stale.** Cho `a=[3,-1,4,1,5,-9,2,6]`, xây prefix, tăng `a[3]` thêm `10`. Tự tính tổng `[2,4]` bằng prefix cũ, bằng mảng mới và bằng prefix dựng lại; giải thích sự khác nhau.

**Bài 6 — Hòa vốn với nhiều nhóm truy vấn.** Một phiên có 30 truy vấn dài 2 phần tử và 300 truy vấn dài 500 phần tử, mảng dài `100.000`. Tính `∑L_i` và so với `n+2q`; chọn hướng nào trong mô hình, và vì sao nên lưu ý cache khi các đoạn giống nhau?

**Bài 7 — Index và bộ nhớ.** Tại sao sparse table cho range minimum chỉ nên cân nhắc khi dữ liệu tĩnh, nhiều truy vấn và RAM đủ? So sánh với segment tree nếu cần thay đổi từng phần tử.

**Bài 8 — Online policy.** Một API nhận truy vấn rải rác và dữ liệu có thể cập nhật bất cứ lúc nào. Hãy phác họa một bộ đếm workload và quy tắc dự đoán lợi ích **các truy vấn còn lại** trước khi lazy-build. Đề xuất cách invalidation khi dữ liệu thay đổi.

**Bài 9 — Đo thực nghiệm.** Thiết kế hai bộ workload cùng `n` và `q` nhưng có phân bố đoạn khác nhau. Đo end-to-end cả chi phí dựng, truy vấn và cập nhật, ghi lại kết quả đúng/không đúng; vì sao benchmark chỉ gọi query sau khi đã dựng prefix là thiên lệch?

## 12. Checklist lựa chọn tiền xử lý

Trước khi chuyển một lời giải trực tiếp thành cấu trúc tiền xử lý, hãy lần lượt trả lời:

1. **Đặc tả truy vấn:** Tính gì, trên đoạn/khoảng nào, có thể dừng sớm không, và kết quả có cần đúng theo phiên bản dữ liệu mới nhất không?
2. **Quy mô sử dụng:** Bao nhiêu `n`, bao nhiêu `q` **trước lần cập nhật/invalidation**, phân bố độ dài truy vấn và tỷ lệ trùng nhau ra sao?
3. **Chi phí tổng:** Đã tính `P + ∑F_i + maintenance/rebuild` và so với `∑D_i` chưa? Có điểm hòa vốn dương thực sự không?
4. **Bộ nhớ:** Index cần `O(n)`, `O(n log n)` hay hơn? Có cần bản sao input, cấu trúc chứa object, hoặc nhiều phiên bản đồng thời không?
5. **Tính động:** Cập nhật hỗ trợ tăng dần, cần dựng lại hay có thể dùng Fenwick/segment tree? Khi nào cache trở thành stale?
6. **Hợp đồng input:** Tiền xử lý có sắp xếp/biến đổi input gốc, thay đổi chỉ số hay thứ tự không? Có phải copy trước không?
7. **Offline hay online:** Có biết các truy vấn tương lai không? Nếu không, việc lazy-build dựa vào dự đoán phần tương lai chứ không chỉ lịch sử.
8. **Hiệu năng thực:** Đã kiểm tra latency đầu tiên, throughput, RAM, cache, GC và benchmark công bằng trên dữ liệu đại diện chưa?
9. **Lựa chọn đơn giản:** Một vài truy vấn nhỏ có thể giải trực tiếp hoặc cache theo truy vấn; không tạo index chỉ vì có thể.
10. **Kiểm thử đúng:** Có so sánh với oracle trực tiếp ở dữ liệu rỗng, một phần tử, số âm, đoạn ngắn/dài, cập nhật và các trường hợp biên không?

**Tiêu chí hoàn thành:** Bạn biết lập bất đẳng thức **`P+qF<qD`**, tính được điểm hòa vốn theo khối lượng truy vấn, phân biệt phí xây dựng với phí truy vấn, nhận ra khi **quét ngắn/ít truy vấn/cập nhật nhiều** khiến tiền xử lý không đáng giá, và lựa chọn hướng xử lý phù hợp kèm kiểm chứng tính đúng, bộ nhớ và chi phí end-to-end.
