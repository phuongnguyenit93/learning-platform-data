# Tách ảnh hưởng của khởi động, cấp phát, thu gom rác và bộ nhớ đệm

Khi đo hiệu năng cấu trúc dữ liệu, con số trên đồng hồ không chỉ phản ánh độ phức tạp của `insert`, `get`, `pop` hoặc truy vấn đoạn. Một lượt thử có thể chậm do chương trình vừa khởi động, mảng vừa tăng dung lượng, bộ thu gom rác chạy đúng lúc, hoặc dữ liệu chưa nằm trong bộ nhớ đệm. Nếu gộp tất cả vào một số đo, ta dễ đưa ra kết luận sai về bản thân thuật toán.

Trong chương **Kiểm chứng và thực hành** của học phần cấu trúc dữ liệu, mục tiêu là thiết kế phép đo tách được các yếu tố này ở mức **có thể kiểm soát và diễn giải**. Kỹ thuật phù hợp khi so sánh mảng với danh sách liên kết, Queue với Deque, bảng băm với cây tìm kiếm, heap, trie, Fenwick Tree, Segment Tree hoặc biểu diễn đồ thị.

Một nguyên tắc xuyên suốt: **chỉ so các phương án sau khi chúng đã thực hiện đúng cùng hợp đồng và cùng lượng công việc**. Cấu trúc làm mất phần tử hoặc bỏ qua kiểm tra bắt buộc có thể chạy nhanh nhưng không phải là lựa chọn hợp lệ.

## 1. Nhận diện các thành phần tạo nên thời gian quan sát được

Hãy hình dung hai bản cài đặt Map cùng xử lý 100.000 lần `get(k)`. Tổng thời gian có thể chịu ảnh hưởng của:

| Thành phần | Cơ chế | Dấu hiệu thường thấy |
|---|---|---|
| **Khởi động / warmup** | Nạp mã, khởi tạo runtime, tối ưu hóa động, làm nóng đường thực thi | Những lượt đầu khác đáng kể các lượt sau |
| **Cấp phát** | Tạo đối tượng, mở rộng mảng, cấp phát nút hoặc bảng bucket | Một số lần `insert` chậm mạnh ở ngưỡng kích thước |
| **Thu gom rác (GC)** | Truy tìm hoặc giải phóng đối tượng không còn dùng tùy runtime | Độ trễ tăng ở một số thời điểm, có thể tương quan với chu kỳ GC |
| **Cache CPU / bộ nhớ** | Truy cập dữ liệu đã nằm gần CPU so với dữ liệu ở bộ nhớ xa hơn | Tập khóa nhỏ được truy cập lặp lại nhanh khác tập khóa lớn rải rác |
| **Cache ứng dụng / hệ điều hành** | Ghi nhớ kết quả truy vấn, trang tệp hoặc dữ liệu đã nạp | Lần truy cập đầu có thể khác lượt tiếp theo |
| **Chi phí phép đo** | Gọi đồng hồ, vòng lặp, sinh dữ liệu, ghi log | Đặc biệt lớn khi thao tác được đo rất ngắn |
| **Tài nguyên chia sẻ** | Lịch CPU, tải nền, tranh chấp luồng, I/O | Các lượt đo dao động hoặc độ trễ đuôi cao |

Có thể dùng cách nhìn định tính:

\[
T_{\text{quan sát}}
\approx T_{\text{xử lý}}+T_{\text{khởi tạo}}+T_{\text{cấp phát}}
+T_{\text{GC}}+T_{\text{truy cập bộ nhớ}}+T_{\text{đo}}.
\]

Đây **không phải công thức cộng chính xác**: các cơ chế tương tác với nhau. Ví dụ, cấp phát mới có thể kích hoạt GC và đẩy dữ liệu cũ khỏi cache; một vòng warmup có thể làm nóng dữ liệu, mã máy lẫn bộ cấp phát. Vì vậy, không thể chỉ đo tổng thời gian rồi trừ một vài con số tùy ý để suy ra “thời gian thuần” của thuật toán.

Cách làm đáng tin hơn là **thay đổi có kiểm soát một yếu tố**, ghi rõ những yếu tố giữ nguyên, sau đó xem phần chênh lệch và giới hạn suy luận.

## 2. Phân biệt câu hỏi “khởi động lạnh” với “xử lý ổn định”

Một chương trình có nhiều loại chi phí khởi động:

- **Khởi động tiến trình:** tạo tiến trình, nạp thư viện và cấu hình runtime.
- **Lần sử dụng đầu:** khởi tạo đối tượng hoặc cache nội bộ một lần, tải lớp, chuyên biệt hóa đường mã.
- **Warmup của runtime:** trong các môi trường có JIT, trình biên dịch có thể tối ưu những phương thức được gọi thường xuyên; trong runtime thông dịch cũng có thể có cache và thích nghi đường thực thi.
- **Warmup của dữ liệu:** các trang bộ nhớ, cache CPU hoặc cache ứng dụng được làm nóng sau những lượt đọc đầu.

Nếu ứng dụng là một công cụ dòng lệnh chạy một lần rồi thoát, **thời gian khởi động là một phần quan trọng của nhu cầu thực tế**. Nếu dịch vụ chạy cả ngày, độ trễ và thông lượng sau khi ổn định thường quan trọng hơn. Hai câu hỏi đều hợp lệ nhưng phải được đo riêng.

### Hai thước đo khác nhau

**Cold start tổng thể:** tính từ lúc bắt đầu chạy chương trình đến khi trả được kết quả đầu tiên, bao gồm các pha khởi động thực sự của ứng dụng. Đo này thường cần công cụ ngoài tiến trình hoặc môi trường khởi động mới.

**Steady-state workload:** tạo cấu trúc, chuẩn bị dữ liệu và warmup trước vùng định thời; sau đó chỉ đo loạt thao tác mà ứng dụng thực hiện lâu dài. Nêu rõ có tính tái cấp phát và GC phát sinh **trong các thao tác đó** hay không.

Không được gọi một lượt “cold” chỉ vì đó là **lượt đầu của một vòng lặp trong cùng tiến trình**. Thư viện, mã máy và dữ liệu có thể đã được nạp từ trước. Tương tự, chạy một tiến trình mới **không đảm bảo** cache tệp của hệ điều hành đã lạnh.

### Cách kiểm soát warmup

1. Xác định rõ **điểm bắt đầu và kết thúc** của phép đo.
2. Chuẩn bị cùng dữ liệu đầu vào và cấu trúc ban đầu cho các phương án.
3. Chạy một số lượt warmup không lấy số liệu nếu mục tiêu là steady state.
4. Chạy nhiều lượt đo, khôi phục trạng thái tương đương cho từng lượt.
5. Luân phiên thứ tự các phương án (`A, B, B, A` hoặc các hoán vị) để hạn chế việc phương án luôn chạy sau có lợi từ cache hoặc thay đổi xung nhịp CPU.
6. Ghi cả số đo từng lượt và thống kê độ phân tán; không chỉ giữ một giá trị đẹp nhất.

Trong Java, JVM có thể tiếp tục biên dịch và tối ưu sau vài lượt đầu; nên dùng công cụ như JMH khi cần microbenchmark nghiêm túc. Trong Python, `time.perf_counter_ns()` có ích cho thực nghiệm nhỏ, nhưng số đo vẫn chịu overhead của vòng lặp, bộ thông dịch và môi trường máy.

## 3. Ví dụ: cùng một Map, hai kiểu truy cập dữ liệu

Ta xét `dict` Python làm Map để minh họa **phân phối truy cập** và warmup. Dữ liệu được xây trước; vùng định thời chỉ thực hiện các lần tra cứu, không tạo Map hay sinh khóa ngẫu nhiên.

- **Hot set:** phần lớn truy vấn tập trung vào 128 khóa đầu.
- **Spread set:** các truy vấn trải rộng trên 50.000 khóa.

Cùng số truy vấn và cùng phép toán `get`, nhưng tập làm việc (*working set*) rất khác nhau.

```python
from random import Random
from statistics import median
from time import perf_counter_ns

N = 50_000
Q = 20_000
rng = Random(2026)

# Tao du lieu va chuoi truy van ben ngoai vung dinh thoi.
mapping = {key: key * 2 for key in range(N)}
queries = {
    "hot": [rng.randrange(128) for _ in range(Q)],
    "spread": [rng.randrange(N) for _ in range(Q)],
}
expected_sums = {
    name: sum(mapping[key] for key in keys)
    for name, keys in queries.items()
}


def time_lookups(table, keys):
    checksum = 0
    start = perf_counter_ns()
    for key in keys:
        checksum += table[key]
    elapsed = perf_counter_ns() - start
    return elapsed, checksum


# Warmup ca hai workload. Khong luu cac so do nay.
for _ in range(3):
    for name in ("hot", "spread"):
        time_lookups(mapping, queries[name])

samples = {"hot": [], "spread": []}

for repeat in range(8):
    # Dao thu tu de han che loi the cua workload chay sau.
    order = ("hot", "spread") if repeat % 2 == 0 else ("spread", "hot")

    for name in order:
        elapsed, checksum = time_lookups(mapping, queries[name])
        assert checksum == expected_sums[name]
        samples[name].append(elapsed / Q)

for name in ("hot", "spread"):
    print(name, "median ns/lookup =", median(samples[name]))
    print(name, "all ns/lookup =", samples[name])
```

Điểm cần đọc đúng:

- Đây là **thời gian trung bình trên một lookup trong mỗi lượt**, rồi lấy trung vị các lượt; **không** phải p50 độ trễ của từng lookup.
- Vùng định thời vẫn chứa vòng lặp Python, phép cộng số nguyên và truy cập danh sách khóa. Vì vậy, số đo **không tách riêng tuyệt đối** thời gian một lần tra bảng băm.
- `hot` và `spread` chỉ khác về **độ tập trung truy cập**. Không được mặc nhiên đổi tên `spread` thành “cache lạnh”: cả hai workload đều đã warmup, và phần dữ liệu của `spread` có thể vẫn nằm trong nhiều tầng cache.
- Nếu thấy sự khác biệt, cần xem xét khả năng do cache CPU, kích thước dữ liệu, đặc điểm vòng lặp và các yếu tố máy. Muốn gắn nguyên nhân chính xác với cache miss, cần phép đo hoặc bộ đếm phần cứng phù hợp.

Để thử ảnh hưởng **kích thước dữ liệu**, có thể tạo các Map lần lượt có `n = 1.000`, `10.000`, `100.000` khóa và giữ nguyên số truy vấn `Q`. Để thử ảnh hưởng **tỷ lệ hit/miss**, sinh riêng các truy vấn khóa có mặt và khóa vắng mặt; nhưng phải thống nhất cách xử lý miss (`dict.get`, `in`, hoặc bắt `KeyError`) ở mọi phương án.

## 4. Tách thời gian xây dựng khỏi thời gian thao tác

Một benchmark Map thường vô tình đo đồng thời:

```text
Sinh khóa -> Cấp phát bảng -> Chèn toàn bộ khóa
          -> Truy vấn -> Kiểm tra kết quả -> In log
```

Nếu mục tiêu là tốc độ tra cứu của Map đã tồn tại, cần đưa những công việc khác **ra ngoài vùng định thời**. Nếu mục tiêu là thời gian dựng chỉ mục lúc tải dữ liệu, phép xây dựng lại chính là công việc phải đo.

### Cách đo hai pha riêng

```python
from time import perf_counter_ns


def time_build(keys):
    start = perf_counter_ns()
    table = {key: key * 2 for key in keys}
    build_ns = perf_counter_ns() - start
    return build_ns, table


def time_queries(table, keys):
    checksum = 0
    start = perf_counter_ns()
    for key in keys:
        checksum += table[key]
    query_ns = perf_counter_ns() - start
    return query_ns, checksum


keys = list(range(50_000))
lookups = list(range(1000)) * 20

build_ns, table = time_build(keys)
query_ns, checksum = time_queries(table, lookups)

assert checksum == sum(key * 2 for key in lookups)
print("Build ns:", build_ns)
print("Lookup batch ns:", query_ns)
```

Đây là **hai phép đo có ranh giới khác nhau**:

- `build_ns` bao gồm cả cấp phát `dict`, tạo nhiều giá trị và chèn các cặp khóa–giá trị; khóa trong `keys` đã được tạo trước.
- `query_ns` đo lặp tra cứu trên một bảng đã xây, không bao gồm chi phí dựng lại bảng.

Nếu muốn so sánh hai cấu trúc, hãy đo **cả thời gian xây dựng lẫn thời gian truy vấn**, đặc biệt với cấu trúc thêm chỉ mục phụ. Ví dụ, cây có trường `subtree_size` hỗ trợ truy vấn hạng nhanh hơn nhưng việc chèn/xóa phải cập nhật metadata; chỉ đo `select(k)` sẽ che chi phí duy trì chỉ mục.

Không nên lấy `build_ns` từ một lượt và `query_ns` từ một lượt khác rồi mặc định chúng độc lập hoàn toàn. Quá trình xây dựng có thể làm nóng dữ liệu trước khi truy vấn; khi ứng dụng luôn xây rồi truy vấn, đây là một phần của tải thật. Hãy báo **cả hai pha** và thêm phép đo tổng hành trình nếu đó là điều cần quyết định.

## 5. Tách ảnh hưởng của cấp phát và tăng dung lượng

Cấp phát bộ nhớ ảnh hưởng hiệu năng theo nhiều cách:

1. Phải tìm và cấp phát vùng nhớ đủ lớn.
2. Có thể phải khởi tạo các ô hoặc nút mới.
3. Khi mảng động tăng dung lượng, phải sao chép hoặc di chuyển phần tử cũ.
4. Số đối tượng hoặc kích thước bộ đệm lớn hơn làm thay đổi tính cục bộ và áp lực lên bộ nhớ đệm.
5. Cấp phát còn có thể tác động tới thời điểm thu gom rác.

### Mảng động: thời gian khấu hao khác thời gian một lần gọi

Với mảng động nhân đôi dung lượng, phần lớn `append` là nhanh, nhưng lần cần tăng bộ đệm phải chuyển `n` phần tử. Vì thế, `append` thường có **`O(1)` khấu hao**, còn **một lần cụ thể khi phải mở rộng có thể tốn `O(n)`**.

Muốn nhìn rõ các đỉnh chi phí, cần ghi độ trễ từng lần thêm và biết khi nào kích thước vượt ngưỡng dung lượng. Tuy nhiên, đừng suy ngưỡng cấp phát chỉ từ `len`: nhiều ngôn ngữ và thư viện không công khai `capacity` hoặc sử dụng chiến lược tăng dung lượng khác nhau.

### Hai thí nghiệm cấp phát trả lời hai câu hỏi khác nhau

| Thí nghiệm | Bao gồm những gì? | Trả lời câu hỏi |
|---|---|---|
| Xây mới toàn bộ cấu trúc từ dữ liệu có sẵn | Tạo đối tượng, cấp phát, chèn phần tử và resize | Chi phí khởi tạo/tải dữ liệu |
| Cập nhật trên cấu trúc đã xây | Thao tác cập nhật và những cấp phát do chính thao tác gây ra | Chi phí vận hành của cấu trúc đã tồn tại |
| Cập nhật sau khi đã dự trữ dung lượng | Ít hoặc không phải cấp phát lại khi còn chỗ | Độ nhạy với sự kiện tăng dung lượng |
| Đo bộ nhớ đỉnh lúc xây/resize | Bộ đệm cũ, bộ đệm mới và đối tượng tạm thời | Đỉnh RAM cần dự phòng |

**Không so một phiên bản được cấp phát sẵn toàn bộ dung lượng với một phiên bản tự mở rộng rồi tuyên bố thuật toán thứ nhất tốt hơn mọi mặt.** Cấp phát sẵn đổi lấy chi phí bộ nhớ và thời gian chuẩn bị; khi ứng dụng không biết trước `n`, cách đó có thể không áp dụng được.

### Đo bộ nhớ cấp phát bằng `tracemalloc` trong Python

`tracemalloc` có thể theo dõi những cấp phát bộ nhớ Python được trình theo dõi ghi nhận. Dùng nó trong **lượt đo bộ nhớ riêng**, không đồng thời với benchmark thời gian chính.

```python
import tracemalloc


def measure_build_allocations(keys):
    tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()

        table = {key: key * 2 for key in keys}

        after, peak = tracemalloc.get_traced_memory()
        retained_delta = after - before
        peak_delta = peak - before
        return retained_delta, peak_delta, len(table)
    finally:
        tracemalloc.stop()


keys = list(range(30_000))  # Khong tinh cap phat tao keys.
retained, peak, size = measure_build_allocations(keys)
assert size == 30_000
print("Tracked retained delta:", retained)
print("Tracked peak delta:", peak)
```

Hai số chênh lệch phụ thuộc thời điểm lấy mốc và những cấp phát được theo dõi, **không phải tổng dung lượng RAM cư trú (RSS) của tiến trình**. Với thư viện native hoặc bộ nhớ cấp phát ngoài phạm vi theo dõi của Python, cần công cụ thích hợp khác. `sys.getsizeof` cũng không tự cộng bộ nhớ của toàn bộ đồ thị đối tượng được tham chiếu.

Một điểm thực hành: **bộ nhớ đang giữ** và **bộ nhớ đỉnh** là hai chỉ số khác nhau. Trong pha tăng dung lượng, hệ thống có thể tạm thời giữ cả bộ đệm cũ và mới; mức RAM đỉnh có thể quyết định cấu trúc có vận hành được trong giới hạn bộ nhớ hay không.

## 6. Tách ảnh hưởng của thu gom rác (GC)

GC là nguồn biến động cần hiểu đúng theo từng runtime. Không có một quy tắc chung áp dụng nguyên vẹn cho Python, Java, Go, JavaScript hay C++.

- **CPython:** đếm tham chiếu giải phóng nhiều đối tượng khi chúng không còn tham chiếu; bộ thu gom theo dõi các vòng tham chiếu (cyclic GC) xử lý những chu trình không tự giải phóng được chỉ bằng đếm tham chiếu. `gc.disable()` vô hiệu hóa phần thu gom vòng tham chiếu tự động, **không tắt cơ chế đếm tham chiếu**.
- **Các runtime quản lý bộ nhớ khác:** có các bộ thu gom và chính sách khác nhau, đôi khi đi kèm các pha dừng hoặc xử lý đồng thời. Loại bộ thu gom, kích thước heap và phiên bản runtime có thể ảnh hưởng cả thông lượng lẫn độ trễ đuôi.
- **C++ với cấp phát thủ công/RAII:** thường không có GC tự động theo cách của JVM, nhưng vẫn có chi phí cấp phát, hủy đối tượng, cơ chế tái sử dụng bộ nhớ hoặc bộ quản lý nhớ riêng.

### Quan sát GC trước khi can thiệp

Trong CPython, có thể đọc số lần thu gom bằng `gc.get_stats()`:

```python
import gc
from time import perf_counter_ns


def total_collections():
    # CPython: tong so luot thu gom ghi nhan o cac the he.
    return sum(item["collections"] for item in gc.get_stats())


def inspect_gc(workload):
    before = total_collections()

    started = perf_counter_ns()
    result = workload()
    elapsed_ns = perf_counter_ns() - started

    after = total_collections()
    return {
        "elapsed_ns": elapsed_ns,
        "collections_during_trial": after - before,
        "result": result,
    }


def create_short_cycles():
    for _ in range(20_000):
        node = []
        node.append(node)
        # Cac node tao chu trinh, mat tham chieu ngoai vong lap.
    return 20_000


report = inspect_gc(create_short_cycles)
assert report["result"] == 20_000
print(report["elapsed_ns"])
print(report["collections_during_trial"])
```

`collections_during_trial` chỉ đếm các lần thu gom được ghi nhận trong khoảng đo, **không trực tiếp cho biết GC đã tiêu tốn bao nhiêu nanosecond**. Nếu hai lần thử có kết quả khác nhau, cần thu thêm số lần thu gom, thời gian dừng (nếu profiler hỗ trợ) và lượng cấp phát để phân tích nguyên nhân.

Ví dụ trên cố tình tạo các vòng tham chiếu để minh họa trường hợp cyclic GC có thể liên quan. **Không dùng workload nhiều chu trình như vậy để kết luận hiệu năng chung của Stack hoặc Queue số nguyên**, vì chúng có thể rất ít phụ thuộc vào cyclic GC.

### Có nên tắt GC khi benchmark?

Có thể làm một **thí nghiệm chẩn đoán riêng** với GC tự động bật/tắt nếu runtime cho phép, nhưng cần cẩn trọng:

- Chạy trong môi trường kiểm thử có kiểm soát và **khôi phục trạng thái GC ban đầu**.
- Khi tắt cyclic GC, các chu trình rác có thể tích lũy, làm thay đổi mức bộ nhớ và ảnh hưởng cache; “tắt GC thì nhanh hơn” chưa chứng minh thuật toán nhanh hơn.
- Chuỗi thử nên được tái lập ở trạng thái bộ nhớ tương đương; so sánh trên hai tiến trình độc lập có thể đáng tin hơn một chuỗi lượt thay đổi GC trong cùng tiến trình.
- Nếu ứng dụng chạy với GC bật, kết quả đo **có GC** mới phản ánh phần chi phí thật; không lấy kết quả tắt GC để hứa hẹn độ trễ sản xuất.
- Trong chương trình nhiều luồng, thay đổi chế độ GC toàn tiến trình có thể ảnh hưởng các tác vụ khác; hạn chế thí nghiệm vào môi trường riêng.

Điều quan trọng là **quan sát và giải thích** GC, không tìm cách xóa nó khỏi mọi số đo. Cấp phát và thu gom rác đôi khi là thành phần không thể tách khỏi hành vi thực tế của cấu trúc dữ liệu.

## 7. “Bộ nhớ đệm” có nhiều tầng khác nhau

Từ *cache* được dùng cho nhiều cơ chế, và cách kiểm tra khác nhau:

| Loại | Dữ liệu được ghi nhớ | Tình huống đo |
|---|---|---|
| **CPU cache** (L1/L2/L3) | Cache line của mã và dữ liệu trong RAM | Duyệt mảng liên tiếp so với lần theo con trỏ rải rác |
| **TLB / dịch địa chỉ** | Bản dịch địa chỉ ảo sang vật lý | Truy cập qua rất nhiều trang bộ nhớ |
| **Cache ứng dụng** | Kết quả đã tính hoặc dữ liệu gần đây | `get(k)` trúng cache so với phải truy xuất nguồn |
| **OS page cache** | Nội dung tệp đã đọc từ thiết bị lưu trữ | Lần đọc tệp đầu so với đọc lại |
| **Cache ở tầng dịch vụ** | Bản sao dữ liệu ở cache ngoài hoặc phân tán | Cache hit so với truy cập cơ sở dữ liệu |

Một lần thử `Map.get(k)` toàn bộ trong RAM chủ yếu liên quan đến cách tổ chức cấu trúc, bộ nhớ và cache CPU; nó **không tự đo** tốc độ của cache ứng dụng phân tán hay cache tệp của hệ điều hành.

### Hot set và working set

**Hot set** là nhóm phần tử được truy cập thường xuyên. **Working set** là lượng dữ liệu thực sự được dùng trong một khoảng thời gian. Nếu hot set nhỏ, nhiều lần tra cứu có thể tận dụng bộ nhớ đệm tốt; nếu working set lớn và truy cập rải rác, cấu trúc có thể gặp nhiều lần truy cập bộ nhớ tốn kém hơn.

Ví dụ, khi duyệt tuần tự một mảng, truy cập liên tiếp thường tận dụng tốt tính cục bộ. Danh sách liên kết phải truy cập qua con trỏ, các nút có thể nằm rải rác. Điều này giúp giải thích vì sao một phép duyệt danh sách liên kết `O(n)` có thể chậm đáng kể hơn duyệt mảng cũng `O(n)` trong nhiều môi trường.

Nhưng **không nên coi mọi cây hay danh sách liên kết đều kém cache**: bộ cấp phát, cách đóng gói nút, kích thước dữ liệu và công việc cần làm đều ảnh hưởng. Đo phải gắn với biểu diễn cụ thể và workload cụ thể.

### Làm sao thực hiện phép đo cache có ý nghĩa?

1. Giữ cùng **số phép toán**, loại truy vấn và dữ liệu logic.
2. Thay đổi quy mô working set hoặc độ tập trung truy cập, ví dụ hot set 128, 4.096, 65.536 khóa.
3. Sinh danh sách chỉ số truy cập trước vùng định thời; giữ seed cố định.
4. Chạy nhiều lượt và luân phiên thứ tự điều kiện.
5. Báo rõ điều kiện là **truy cập nóng/tập trung** hay **truy cập rộng/phân tán**, không gán nhãn “cold cache” nếu không kiểm soát được trạng thái cache.
6. Nếu cần chứng minh khác biệt do miss L1/L2/L3 hoặc TLB, dùng công cụ đo sự kiện phần cứng phù hợp trên môi trường cho phép.

Đọc một vùng nhớ lớn trước benchmark có thể thay đổi trạng thái cache, nhưng **không bảo đảm** làm lạnh chính xác mọi tầng cache trên mọi CPU. Khởi động tiến trình mới cũng không tự xóa nội dung cache của hệ điều hành. Các thí nghiệm đòi điều kiện “cold” chặt chẽ thường cần phương pháp chuyên dụng, được mô tả rõ.

## 8. Thiết kế thí nghiệm để phân biệt các nguồn ảnh hưởng

Có thể lập ma trận nhiều điều kiện thay vì dùng một phép đo hỗn hợp:

| Điều kiện | Cách chuẩn bị | Thành phần được quan sát chủ yếu |
|---|---|---|
| Xây mới cấu trúc | Dữ liệu đầu vào đã sinh; định thời pha build | Cấp phát, khởi tạo, chèn và resize |
| Truy vấn cấu trúc đã xây | Build ngoài đồng hồ; warmup trước | Chi phí truy vấn ổn định dưới trạng thái hiện có |
| Truy vấn lần đầu sau khởi động mới | Tạo tiến trình/môi trường mới; ghi rõ phạm vi | First-use và khởi động trong điều kiện đã định |
| Chèn ở ngưỡng tăng dung lượng | Chuẩn bị trước ở kích thước sát ngưỡng | Một thao tác resize và chi phí đỉnh |
| Tải tạo nhiều đối tượng | Giữ số thao tác; ghi các lần GC và cấp phát | Độ nhạy với quản lý bộ nhớ |
| Hot set nhỏ so với truy cập rộng | Giữ số lookup; đổi tập khóa truy cập | Độ nhạy với tính cục bộ dữ liệu |
| Workload thực tế đầy đủ | Bao gồm các pha ứng dụng thật có thực hiện | Trải nghiệm đầu cuối, gồm mọi chi phí liên quan |

Ma trận này không làm cho các yếu tố **hoàn toàn độc lập**. Ví dụ, build ngoài đồng hồ vẫn có thể làm nóng dữ liệu cho pha query; khi so hai kiểu truy cập, cache và nhánh dự đoán của CPU có thể cùng thay đổi. Kết luận đúng là “trong điều kiện A, thời gian khác B”, rồi dùng đo đạc bổ sung để kiểm tra giả thuyết về nguyên nhân.

### Thí nghiệm có đối chứng và đảo thứ tự

Nếu so hai triển khai `A` và `B`, không nên luôn đo `A` trước rồi `B` sau. Máy có thể thay đổi xung nhịp theo nhiệt độ; `B` có thể được hưởng cache hoặc chịu tải nền khác.

Một lịch trình đơn giản:

```text
Warmup A, B (khong ghi so)
Lap 1: A, B
Lap 2: B, A
Lap 3: B, A
Lap 4: A, B
...
```

Giữ mỗi lượt độc lập về dữ liệu và trạng thái logic. Nếu workload làm biến đổi Queue hoặc Map, cần **khôi phục cùng trạng thái ban đầu** trước mỗi lượt; không dùng kết quả của lượt trước làm dữ liệu cho lượt sau nếu mục tiêu là so cùng một công việc.

Có thể báo trung vị các lượt và phạm vi dao động. Nếu cần đánh giá p95/p99 của **từng thao tác**, phải lấy mẫu độ trễ từng thao tác bằng công cụ phù hợp; thời gian trung bình của một lô không tự cung cấp phân phối đó.

## 9. Minh họa tình huống: vì sao một Queue có thể “đột nhiên chậm”

Giả sử một ứng dụng dùng Queue dựa trên mảng động. Quan sát thấy vài lần thêm nhanh nhưng một lần `enqueue` mất thời gian nhiều hơn.

Trước khi cho rằng “Queue có độ phức tạp không ổn định”, hãy kiểm tra:

- **Dung lượng:** lần thêm đó có rơi vào thời điểm `size == capacity` và buộc cấp phát mảng mới không?
- **GC:** có sự kiện thu gom rác cùng khoảng thời gian hay không? Nếu có, nó có đóng góp đáng kể hay chỉ trùng thời điểm?
- **Cache:** thao tác có đụng tới vùng dữ liệu lớn chưa được truy cập gần đây không?
- **Warmup:** đó có phải lần sử dụng đầu của đường mã hay lần runtime đang tối ưu không?
- **Tác vụ ngoài:** có thread khác, I/O hoặc hoạt động hệ điều hành khiến thao tác bị gián đoạn không?

Muốn xác định ảnh hưởng của resize, hãy chuẩn bị các Queue cùng kiểu ở hai trạng thái:

```text
A: size < capacity, lan them tiep theo khong can mo rong
B: size = capacity, lan them tiep theo phai mo rong
```

Giữ tương đồng về nội dung và thang kích thước, đo lặp với trạng thái được tạo mới, kiểm tra số phần tử và thứ tự sau mỗi lượt. Không thể lấy một mẫu chậm duy nhất để chứng minh nguyên nhân là GC nếu đồng thời thao tác đang sao chép toàn bộ bộ đệm.

Một kết luận phù hợp với phân tích thuật toán là: **thêm cuối vào mảng động có `O(1)` khấu hao, nhưng lần cấp phát lại có thể tốn `O(n)`**. Nếu ứng dụng cần độ trễ tối đa chặt chẽ, nên xem xét chính sách dung lượng, cấp phát trước hoặc cấu trúc có đặc tính phù hợp hơn. Những biện pháp đó cần được đánh giá cả về bộ nhớ và hành vi nghiệp vụ.

## 10. Những bẫy khi cố “loại bỏ nhiễu” khỏi benchmark

**Bẫy 1 — Xóa toàn bộ chi phí thực tế.** Nếu ứng dụng liên tục tạo và xóa bản ghi, cấp phát và GC là một phần của workload. Benchmark chỉ tra cứu một đối tượng đã tồn tại có thể trả lời câu hỏi khác.

**Bẫy 2 — Gọi một điều kiện là cold mà không kiểm chứng.** Lượt đầu sau một vòng lặp không đồng nghĩa CPU cache hoặc OS cache lạnh. Dùng tên mô tả đúng điều kiện thí nghiệm.

**Bẫy 3 — Đo hai bản với lượng công việc khác nhau.** Nếu một bản xây chỉ mục ngoài vùng định thời nhưng bản kia xây trong vùng định thời, kết quả không còn là so cùng pha.

**Bẫy 4 — Để bộ sinh random trong đồng hồ.** Tính `randrange`, tạo khóa, định dạng chuỗi và I/O có thể chiếm thời gian đáng kể so với `get` hoặc `push`.

**Bẫy 5 — Dùng profiler thay cho phép đo thời gian không instrument.** Trình theo dõi cấp phát, log hoặc kiểm tra bất biến có overhead. Hãy chạy **benchmark thời gian** và **hồ sơ bộ nhớ/GC** trong những lượt được đánh dấu rõ.

**Bẫy 6 — Chỉ giữ lượt nhanh nhất.** Có thể vô tình loại bỏ mọi lần chậm do GC, resize hoặc tải nền. Giữ phân phối và báo tiêu chí thống kê đã chọn.

**Bẫy 7 — Không khôi phục trạng thái.** Một lần chạy `pop` làm Queue ngắn đi; lượt tiếp theo không còn cùng độ dài. Cần dựng lại trạng thái ngoài vùng đo hoặc thiết kế chuỗi giữ độ dài ổn định.

**Bẫy 8 — Kết luận độ phức tạp chỉ từ vài điểm.** Tính cục bộ, độ lớn mẫu và thay đổi xung nhịp có thể che xu hướng. Kết hợp phân tích lý thuyết với nhiều mức kích thước.

**Bẫy 9 — Vô hiệu hóa GC rồi báo hiệu năng sản xuất.** Đặc biệt với các chu trình tham chiếu, tắt GC có thể làm bộ nhớ tăng và thay đổi hành vi. Dùng nó cho thí nghiệm chẩn đoán ngắn, không làm giả thiết mặc định của ứng dụng.

**Bẫy 10 — So sánh các thao tác khác hợp đồng.** `deque.popleft()` và `list.pop(0)` cùng thực hiện FIFO; nhưng một cấu trúc bỏ qua lỗi rỗng hoặc ghi đè khi đầy không thể được so trực tiếp với cấu trúc từ chối thao tác nếu không có quy tắc quy đổi rõ ràng.

## 11. Bài tập tự kiểm tra

### Bài 1 — Warmup hay tốc độ thuật toán?

Một phép đo cho thấy lượt đầu tra cứu một Map chậm hơn các lượt sau. Hãy nêu ít nhất ba giả thuyết và cách kiểm chứng.

**Gợi ý đáp án:** có thể do khởi tạo đường mã, làm nóng dữ liệu/cache, cấp phát một lần, hoặc tải nền khác. Tách build và query, chạy nhiều lượt ở tiến trình khác nhau, ghi thứ tự chạy, so hot set với spread set và dùng công cụ ghi sự kiện runtime/cache khi cần. Không kết luận ngay mọi phần chênh lệch là “JIT”.

### Bài 2 — Cấp phát nằm ở đâu?

Một thí nghiệm so hai cách lưu Set. Bản A nhận đầu vào đã được tạo trước; bản B tạo chuỗi khóa mới ngay trong vùng định thời. Bản B chậm hơn. Có thể kết luận cấu trúc B chèn chậm hơn A không?

**Đáp án:** chưa thể. Vùng định thời của B có thêm chi phí tạo khóa và cấp phát. Cần tạo cùng tập khóa trước hoặc đo rõ hai pha tạo khóa và thêm vào Set. Nếu ứng dụng thực tế phải sinh khóa khi chèn, có thể đo thêm hành trình đầy đủ nhưng phải gắn nhãn.

### Bài 3 — Chênh lệch thời gian và sự kiện GC

Bạn ghi nhận một lượt chạy chậm có một lần cyclic GC, còn lượt nhanh không có lần nào. Đây đã đủ chứng minh GC là nguyên nhân gây chậm chưa?

**Đáp án:** chưa. GC có thể góp phần, nhưng lượt chậm còn có thể xảy ra resize, truy cập bộ nhớ lớn hoặc bị gián đoạn. `gc.get_stats()` đếm số lần thu gom, không đo chính xác thời gian dừng. Cần lặp lại, ghi dữ liệu bổ sung, hoặc dùng profiler GC thích hợp.

### Bài 4 — So hot set và spread set

Hai workload có `20.000` lookup và cùng Map `50.000` khóa. Workload A lặp trong 128 khóa, workload B phân bố trên toàn bộ Map. Nếu A nhanh hơn, ta được phép kết luận điều gì?

**Đáp án:** trong điều kiện đã thử, tra cứu tập khóa tập trung có thời gian đo thấp hơn truy cập phân tán. Có thể giả thuyết về tính cục bộ và cache, nhưng không thể khẳng định chính xác tỷ lệ cache miss hoặc gọi B là “cache lạnh” nếu chưa đo và kiểm soát.

### Bài 5 — Thiết kế thí nghiệm cho heap

Một min-heap có `push` và `pop_min` trong `O(log n)`. Hãy thiết kế hai phép đo để tách chi phí xây heap khỏi chi phí vận hành.

**Gợi ý đáp án:** phép thứ nhất tạo heap từ `n` phần tử cho trước và định thời chỉ pha xây, quy định rõ dùng chèn từng phần tử hay heapify; phép thứ hai xây heap ngoài đồng hồ, làm nóng nếu cần, rồi đo cùng chuỗi `push`/`pop_min` duy trì thang kích thước tương đương. Sau lượt đo kiểm tra thứ tự lấy ra và tính bảo toàn phần tử; đo cấp phát/bộ nhớ ở lượt riêng nếu cần.

## 12. Quy trình đo để có thể tái hiện và ra quyết định

1. **Xác định câu hỏi:** đo cold start đầu cuối hay tốc độ thao tác trên cấu trúc đã ổn định?
2. **Chốt hợp đồng và workload:** cùng loại thao tác, số lượng, dữ liệu, phân phối khóa, tỷ lệ hit/miss và chính sách lỗi.
3. **Kiểm tra tính đúng:** mô hình tham chiếu, bất biến, số phần tử, thứ tự trước khi so tốc độ.
4. **Tách pha:** sinh dữ liệu, xây cấu trúc, warmup, đo thao tác, xác minh, đo bộ nhớ.
5. **Kiểm soát cấp phát:** ghi thời điểm resize/rehash và trạng thái dung lượng, đo riêng pha xây và pha cập nhật.
6. **Theo dõi GC:** ghi sự kiện và môi trường; dùng thí nghiệm bật/tắt GC chỉ như công cụ chẩn đoán có kiểm soát.
7. **Mô tả cache đúng:** nêu quy mô working set, tính cục bộ và trạng thái chuẩn bị; tránh suy đoán “cold” từ tên lượt thử.
8. **Lặp và đảo thứ tự:** thu đủ mẫu, lưu số liệu gốc và điều kiện thực thi để so sánh có ý nghĩa.
9. **Đo bộ nhớ riêng:** lưu bộ nhớ giữ lại, bộ nhớ đỉnh và công cụ đo; không trộn overhead profiler vào số đo thời gian.
10. **Diễn giải cùng lý thuyết:** phân biệt trường hợp xấu nhất, kỳ vọng, khấu hao và chi phí phụ thuộc `n`; nêu rõ giới hạn của thí nghiệm.

Một phép đo hữu ích không cần loại bỏ mọi tác động của môi trường. Nó cần **phân biệt các pha, kiểm soát được điều kiện và nói đúng điều số liệu chứng minh**. Khi hiểu ảnh hưởng của khởi động, cấp phát, GC và cache, ta mới đánh giá được cấu trúc dữ liệu nào thực sự phù hợp với nhu cầu về thời gian, bộ nhớ và độ ổn định của hệ thống.
