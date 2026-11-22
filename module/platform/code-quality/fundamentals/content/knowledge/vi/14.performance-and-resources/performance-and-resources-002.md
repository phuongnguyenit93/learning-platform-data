# Lựa chọn thuật toán và cấu trúc dữ liệu phù hợp

## 1. Mục tiêu bài học

Trong chương **Hiệu năng và tài nguyên** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu cách chọn thuật toán và cấu trúc dữ liệu dựa trên **các thao tác thật sự cần thực hiện**, thay vì mặc định giải pháp có độ phức tạp lý thuyết thấp nhất luôn là giải pháp tốt nhất.

Module có mục tiêu **hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Một lựa chọn kỹ thuật tốt phải đồng thời xét tính đúng đắn, thời gian chạy, bộ nhớ, tính dễ kiểm thử và chi phí thay đổi về sau.

Sau bài học, bạn có thể:

- Phân tích thao tác chủ đạo của bài toán: tra cứu, chèn, xóa, duyệt có thứ tự, tìm phần tử lớn nhất hoặc lấy `k` phần tử tốt nhất.
- Dùng ký hiệu `O(...)` để **so sánh tốc độ tăng chi phí**, đồng thời nhận biết giới hạn của phân tích Big-O.
- So sánh `ArrayList`, `HashMap`, `HashSet`, `TreeMap`, `ArrayDeque` và `PriorityQueue` theo tính chất cần dùng.
- Thiết kế hai cách tìm **top K sản phẩm bán chạy** bằng Java 17: sắp xếp toàn bộ và dùng hàng đợi ưu tiên giới hạn kích thước.
- Xác nhận kết quả bằng kiểm thử ranh giới và so sánh hai hiện thực, rồi quyết định cách đo hiệu năng phù hợp.

## 2. Bắt đầu từ hành vi, không bắt đầu từ tên cấu trúc dữ liệu

Giả sử có một triệu sản phẩm và một yêu cầu: **“Lấy 10 sản phẩm bán chạy nhất để hiển thị bảng xếp hạng.”** Có ít nhất hai cách đáp ứng:

1. Sắp xếp toàn bộ một triệu sản phẩm theo số lượng bán rồi lấy 10 dòng đầu.
2. Duyệt dữ liệu một lần, chỉ giữ lại 10 ứng viên tốt nhất trong một cấu trúc hỗ trợ loại ứng viên kém nhất.

Cả hai có thể trả **cùng kết quả** nếu được thiết kế đúng. Nhưng chi phí xử lý và bộ nhớ phụ trội có thể khác nhau đáng kể. Nếu sản phẩm sau đó cần **toàn bộ danh sách đã sắp xếp**, lựa chọn thứ nhất lại có thể hợp lý hơn.

Trước khi viết mã, hãy xác định:

| Câu hỏi | Ví dụ về thông tin cần có | Vì sao quan trọng |
| --- | --- | --- |
| Cần thao tác gì? | Kiểm tra tồn tại, lấy theo khóa, lấy top K, duyệt theo thứ tự | Mỗi cấu trúc dữ liệu tối ưu cho tập thao tác khác nhau. |
| Có bao nhiêu phần tử? | `n` nhỏ, vài nghìn hay hàng triệu? | Chi phí khởi tạo và cấu trúc bổ sung có thể không đáng với `n` nhỏ. |
| Lặp lại bao nhiêu lần? | Một lần xếp hạng hay hàng nghìn lần tra cứu? | Có thể cần đánh đổi công xây chỉ mục lấy tốc độ truy vấn. |
| Có ràng buộc thứ tự? | Tăng dần, giảm dần, ổn định khi bằng điểm? | `HashMap` không bảo đảm thứ tự duyệt theo xếp hạng. |
| Có phần tử trùng không? | Mỗi SKU chỉ xuất hiện một lần hay nhiều giao dịch cùng SKU? | Chọn `Set` hoặc `Map` không được làm mất dữ liệu có ý nghĩa. |
| Dữ liệu có đổi không? | Chỉ đọc, cập nhật liên tục, nhiều luồng? | Ảnh hưởng đến chi phí duy trì chỉ mục và cách đồng bộ. |
| Tài nguyên giới hạn ở đâu? | CPU, RAM, cấp phát/GC, I/O, độ trễ đầu cuối | Thuật toán nhanh hơn có thể tốn bộ nhớ hơn. |

**Tính đúng đắn là điều kiện đầu tiên:** kết quả có nhanh đến đâu cũng không chấp nhận được nếu làm mất bản ghi trùng, sai thứ tự ưu tiên hoặc thay đổi dữ liệu đầu vào ngoài ý muốn.

## 3. Đọc Big-O đúng phạm vi

**Big-O** mô tả cận trên của mức tăng chi phí theo kích thước đầu vào trong một mô hình tính toán đã xác định. Đây là công cụ hữu ích để so sánh khả năng mở rộng, không phải số mili giây mà JVM chắc chắn sẽ mất.

Ví dụ với `n` phần tử:

| Mức tăng chi phí thường gặp | Hình dung | Ví dụ điển hình |
| --- | --- | --- |
| `O(1)` | Không tăng theo `n` trong mô hình đang xét | Đọc phần tử `ArrayList` theo chỉ số hợp lệ. |
| `O(log n)` | Tăng chậm khi `n` nhân lên | Tìm/ghi trong cây tìm kiếm cân bằng như `TreeMap`. |
| `O(n)` | Tăng gần theo số phần tử phải xét | Duyệt toàn bộ danh sách tìm điều kiện. |
| `O(n log n)` | Tốn hơn một lần duyệt, nhưng thường tốt hơn so sánh mọi cặp | Sắp xếp dựa trên phép so sánh. |
| `O(n²)` | Số bước có thể tăng theo bình phương `n` | So sánh từng phần tử với mọi phần tử khác theo hai vòng lặp. |

Khi nói “tra cứu `HashMap` trung bình `O(1)`”, ta đang dùng giả định về mã băm và phân bố khóa, không hứa rằng **mọi** tra cứu đều mất một thời gian cố định trong mọi trường hợp. Với `TreeMap`, thao tác tra theo khóa thường có giới hạn `O(log n)`, đổi lại dữ liệu được quản lý theo thứ tự khóa.

Một phân tích có trách nhiệm cần chỉ rõ:

- **Kích thước nào là biến?** Trong xếp hạng top K, có cả `n` (số phần tử nguồn) và `k` (số phần tử cần lấy).
- **Đang đo khâu nào?** Xây chỉ mục, một truy vấn, toàn bộ đợt xử lý, hoặc cả thời gian lấy dữ liệu từ database?
- **Đang xét trường hợp nào?** Trung bình, xấu nhất, hoặc một dữ liệu đặc biệt đã có thứ tự?
- **Chi phí bộ nhớ phụ trội ra sao?** Không chỉ tính thời gian CPU; nhiều đối tượng nhỏ có thể làm tăng áp lực GC.

Vì thế, `O(n log n)` và `O(n log k)` giúp đặt giả thuyết về khả năng mở rộng; **benchmark và đo hệ thống thật** mới trả lời câu hỏi cách nào nhanh hơn trong môi trường cụ thể.

## 4. Một số cấu trúc dữ liệu Java và nhu cầu phù hợp

| Cấu trúc | Điểm mạnh | Điểm cần lưu ý | Dùng khi |
| --- | --- | --- | --- |
| `ArrayList<E>` | Truy cập theo chỉ số `O(1)`, duyệt tuần tự thuận tiện, thêm cuối trung bình `O(1)` theo phân bổ | Chèn/xóa ở giữa có thể `O(n)` do dịch phần tử; tìm giá trị bằng duyệt `O(n)` | Dữ liệu có thứ tự theo vị trí, chủ yếu duyệt hoặc truy cập chỉ số |
| `HashSet<E>` | Kiểm tra tồn tại/thêm/xóa trung bình `O(1)` | Không bảo đảm thứ tự duyệt; lưu trữ thêm cấu trúc băm; trùng phần tử bị loại | Cần một tập giá trị duy nhất và kiểm tra thành viên thường xuyên |
| `HashMap<K,V>` | Tra và cập nhật theo khóa trung bình `O(1)` | Không bảo đảm thứ tự xếp hạng; cần bộ nhớ cho bảng băm; quy tắc khóa trùng phải rõ | Tra thông tin theo mã/ID, cần ánh xạ khóa sang giá trị |
| `TreeMap<K,V>` | Duy trì thứ tự khóa và hỗ trợ truy vấn khoảng; thao tác theo khóa `O(log n)` | Thường nhiều chi phí cấu trúc hơn bảng băm; thứ tự do comparator quyết định | Cần duyệt theo thứ tự khóa hoặc truy vấn cận dưới/cận trên |
| `ArrayDeque<E>` | Thêm/xóa ở hai đầu với chi phí trung bình `O(1)` | Không hỗ trợ truy cập ngẫu nhiên theo chỉ số như list; không nhận `null` | Hàng đợi FIFO hoặc ngăn xếp LIFO trong một luồng |
| `PriorityQueue<E>` | Xem phần tử ưu tiên nhất `O(1)`, thêm/lấy ra `O(log n)` | Duyệt toàn bộ queue **không** cho kết quả đã sắp; không tra/xóa tùy ý nhanh | Lập lịch công việc theo ưu tiên, giữ top K ứng viên |

Các độ phức tạp là mô hình phổ biến cho thao tác được nêu; hiệu năng thực tế còn tùy kích thước, kiểu phần tử, phân bố khóa và cách sử dụng. `HashMap`/`HashSet` không tự an toàn để ghi đồng thời từ nhiều luồng; nếu có concurrency phải xét rõ tính nhất quán, đồng bộ hoặc cấu trúc phù hợp. Cũng không nên mặc định `ConcurrentHashMap` giải quyết mọi giao dịch gồm nhiều bước.

### Đặt câu hỏi đúng với nhu cầu

- **Chỉ cần biết mã đã xuất hiện chưa?** `HashSet` thường phù hợp hơn việc lặp `List.contains` nhiều lần. Tuy nhiên, nếu danh sách rất ngắn hoặc chỉ kiểm tra một lần, chi phí tạo set có thể không đáng.
- **Cần thông tin theo SKU?** `HashMap<String, Product>` có thể hữu ích; nếu cần giữ tất cả giao dịch trùng SKU, một map `SKU → Product` duy nhất sẽ làm mất thông tin trừ khi có bước tổng hợp theo hợp đồng.
- **Cần mọi khóa tăng dần?** `TreeMap` có thể tốt hơn tự sắp xếp khóa mỗi lần duyệt; nhưng nếu chỉ cần xuất một lần, sắp xếp danh sách một lần có thể đơn giản hơn.
- **Cần phần tử ưu tiên cao nhất nhiều lần?** `PriorityQueue` giúp lấy đầu hàng đợi theo comparator; nhưng để lấy **toàn bộ kết quả theo thứ tự**, cần lần lượt `poll` hoặc sắp xếp các phần tử đã chọn.

Một nguyên tắc thực tế: **chọn theo các thao tác sẽ diễn ra nhiều nhất và các bảo đảm về dữ liệu**, không chọn theo tên cấu trúc dữ liệu có vẻ mạnh nhất.

## 5. Ví dụ Java 17: lấy top K sản phẩm bán chạy

Giả sử hệ thống đã tổng hợp số lượng bán theo sản phẩm trong một ngày. Đầu vào là danh sách các bản ghi có **một dòng duy nhất cho mỗi SKU**. Nếu nguồn chứa nhiều dòng giao dịch của cùng SKU, phải **tổng hợp trước**; cả hai thuật toán dưới đây đều xếp hạng *bản ghi*, không tự gộp số lượng theo mã hàng.

Hợp đồng đầu ra:

1. `unitsSold` là số lượng nguyên không âm; `sku` là chuỗi không rỗng.
2. Trả **tối đa `k` sản phẩm**, với `k >= 0`. Nếu `k = 0` thì trả danh sách rỗng; nếu `k` lớn hơn số sản phẩm thì trả tất cả.
3. Xếp hạng theo `unitsSold` **giảm dần**. Khi bằng số lượng, xếp theo `sku` **tăng dần** để kết quả xác định.
4. Không sửa danh sách đầu vào; danh sách kết quả không cho thay đổi qua API.
5. Trong lúc gọi, không có luồng khác sửa danh sách nguồn; các `Sale` là giá trị bất biến.

Điểm **phân xử khi bằng nhau (tie-breaker)** rất quan trọng: nếu chỉ so số lượng, hai lần chạy có thể chọn bộ sản phẩm khác nhau cho vị trí thứ `k`, nhất là khi đọc dữ liệu từ nguồn không có thứ tự bảo đảm.

### 5.1. Định nghĩa giá trị và thứ tự xếp hạng

```java
// SaleRankings.java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public final class SaleRankings {
    private SaleRankings() {}

    public record Sale(String sku, long unitsSold) {
        public Sale {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank() || unitsSold < 0) {
                throw new IllegalArgumentException(
                        "sku must not be blank and unitsSold must be >= 0");
            }
        }
    }

    // Sản phẩm tốt nhất đứng trước: bán nhiều, rồi SKU tăng dần.
    private static final Comparator<Sale> BEST_FIRST =
            Comparator.comparingLong(Sale::unitsSold)
                    .reversed()
                    .thenComparing(Sale::sku);

    // Sản phẩm kém nhất đứng trước: bán ít, rồi SKU giảm dần.
    private static final Comparator<Sale> WORST_FIRST =
            BEST_FIRST.reversed();

    private static void checkParameters(List<Sale> sales, int k) {
        Objects.requireNonNull(sales, "sales");
        if (k < 0) {
            throw new IllegalArgumentException("k must not be negative");
        }
    }

    // Hai phương thức topKFullSort và topKHeap được trình bày bên dưới,
    // đặt trong cùng lớp SaleRankings này.
}
```

Comparator ở đây là một phần **ngữ nghĩa đầu ra**: `BEST_FIRST` và `WORST_FIRST` là hai chiều ngược nhau của cùng một thứ tự. Nhờ vậy, khi số lượng bằng nhau, cả hai thuật toán đều phải chọn **SKU nhỏ hơn** vào top K.

Ví dụ dữ liệu:

| SKU | Đã bán |
| --- | ---: |
| `B` | 8 |
| `A` | 8 |
| `C` | 12 |
| `D` | 2 |

Với `k = 2`, kết quả cần là **`C (12)`, `A (8)`**. `B` đứng sau `A` theo quy tắc cùng số lượng.

### 5.2. Cách A: sao chép, sắp xếp toàn bộ rồi lấy `k` phần tử

Phương thức sau được đặt **bên trong** lớp `SaleRankings` ở trên:

```java
public static List<Sale> topKFullSort(List<Sale> sales, int k) {
    checkParameters(sales, k);
    if (k == 0) {
        return List.of();
    }

    List<Sale> copy = new ArrayList<>(sales);
    for (Sale sale : copy) {
        Objects.requireNonNull(sale, "sale");
    }

    copy.sort(BEST_FIRST);
    return List.copyOf(copy.subList(0, Math.min(k, copy.size())));
}
```

Đây là cách triển khai dễ hiểu:

1. Tạo bản sao để **không thay đổi thứ tự của đầu vào**.
2. Sắp xếp theo tiêu chí xếp hạng được công bố.
3. Lấy số phần tử cần thiết và trả bản danh sách không thể sửa.

Với `n` bản ghi, chi phí sắp xếp so sánh có cận thông dụng **`O(n log n)`**, với trường hợp dữ liệu đã có cấu trúc thuận lợi có thể nhanh hơn tùy thuật toán sắp xếp. Bộ nhớ phụ trội cần **`O(n)`** để giữ bản sao, chưa tính các vùng nhớ tạm mà cách sắp xếp cụ thể sử dụng.

**Khi nào phù hợp?** Khi `n` nhỏ hoặc vừa, cần toàn bộ kết quả có thứ tự, chỉ xếp hạng ít lần, hoặc ưu tiên cách cài đặt dễ đọc và không có vấn đề hiệu năng đo được.

### 5.3. Cách B: chỉ giữ `k` ứng viên bằng min-heap

`PriorityQueue` trong Java giữ phần tử **nhỏ nhất theo comparator** ở đầu. Nếu dùng `WORST_FIRST`, phần tử đầu là ứng viên **kém nhất trong nhóm đang giữ**. Khi duyệt phần tử mới:

- Nếu chưa có đủ `k` ứng viên, thêm nó vào heap.
- Nếu heap đã đủ `k` và phần tử mới tốt hơn phần tử kém nhất, bỏ phần tử kém nhất rồi thêm phần tử mới.
- Sau khi duyệt xong, heap chứa top K nhưng **chưa có thứ tự duyệt đảm bảo**. Ta lấy các phần tử ra, sắp xếp lại theo `BEST_FIRST` rồi trả kết quả.

Phương thức dưới đây cũng được đặt trong lớp `SaleRankings`:

```java
public static List<Sale> topKHeap(List<Sale> sales, int k) {
    checkParameters(sales, k);
    if (k == 0) {
        return List.of();
    }

    int initialCapacity = Math.max(1, Math.min(k, sales.size()));
    PriorityQueue<Sale> heap = new PriorityQueue<>(
            initialCapacity, WORST_FIRST);

    for (Sale sale : sales) {
        Objects.requireNonNull(sale, "sale");
        if (heap.size() < k) {
            heap.add(sale);
        } else if (WORST_FIRST.compare(sale, heap.peek()) > 0) {
            heap.remove(); // Bỏ ứng viên kém nhất.
            heap.add(sale); // Giữ ứng viên tốt hơn.
        }
    }

    List<Sale> result = new ArrayList<>(heap);
    result.sort(BEST_FIRST);
    return List.copyOf(result);
}
```

Với `n` phần tử nguồn và `k` ứng viên giữ lại (`1 <= k <= n`), chi phí điển hình là:

- Duyệt `n` phần tử, mỗi lần thêm hoặc thay thế có thể tốn `O(log(k+1))`: tổng **`O(n log(k+1))`**.
- Sắp xếp tối đa `k` kết quả: thêm **`O(k log(k+1))`**.
- Bộ nhớ phụ trội: **`O(k)`** cho heap và danh sách kết quả, **không tính danh sách nguồn đã có sẵn**.

Khi `k` rất nhỏ so với `n`, cách B có thể giảm đáng kể số phép so sánh và bộ nhớ cấp phát so với sao chép/sắp xếp toàn bộ. Khi `k` gần `n`, lợi ích này giảm, còn chi phí duy trì heap có thể khiến nó chậm hơn. Với `k > n`, heap chỉ lưu tối đa `n` bản ghi và cuối cùng vẫn phải sắp xếp toàn bộ những bản ghi đó.

**Chi tiết dễ sai:** dấu `> 0` trong điều kiện so sánh dùng `WORST_FIRST`. Nếu đảo điều kiện, chương trình có thể giữ lại phần tử *kém hơn*. Một kiểm thử với nhiều phần tử bằng số lượng, nhưng SKU khác nhau, là cần thiết để bảo vệ thứ tự.

## 6. So sánh hai lựa chọn bằng cùng một hợp đồng

| Tiêu chí | Sắp xếp toàn bộ (A) | Heap giữ top K (B) |
| --- | --- | --- |
| Kết quả | Toàn bộ thứ tự được tính trước, lấy `k` dòng đầu | Chỉ giữ `k` ứng viên, sắp xếp `k` dòng cuối |
| Chi phí thời gian thường xét | `O(n log n)` | `O(n log(k+1) + k log(k+1))` với `k >= 1` |
| Bộ nhớ phụ trội | `O(n)` | `O(min(k,n))` |
| Trường hợp `k = 0` | Trả danh sách rỗng ngay | Trả danh sách rỗng ngay |
| Độ rõ ràng | Ít nhánh, rất dễ rà soát | Cần giải thích comparator đảo chiều và điều kiện thay ứng viên |
| Nếu cần kết quả xếp hạng đầy đủ | Phù hợp tự nhiên | Không có lợi thế về việc chỉ giữ một nhóm nhỏ |
| Nếu nguồn quá lớn, chỉ lấy vài dòng | Tốn chi phí cho các phần tử không trả về | Có lợi thế tiềm năng rõ hơn |
| Yêu cầu điều kiện biên | `k`, danh sách rỗng, bằng điểm | Các ca đó **và** quyết định giữ/loại phần tử kém nhất |

Phân tích chi phí chỉ phản ánh phần **thuật toán xếp hạng trong bộ nhớ**. Nếu 90% thời gian là truy vấn database hoặc tải qua mạng, tối ưu hóa heap có thể không cải thiện đáng kể độ trễ đầu cuối. Ngược lại, nếu database đã hỗ trợ `ORDER BY units_sold DESC, sku ASC LIMIT k` hiệu quả trên dữ liệu và chỉ mục phù hợp, giải quyết tại nguồn có thể tốt hơn cả hai cách Java; cần kiểm tra kế hoạch truy vấn và nhu cầu thực tế.

### Đầu vào lớn nhưng đã nằm trong `List`

Trong ví dụ, chữ ký nhận `List<Sale>`, tức danh sách **nguồn đã được lưu trong bộ nhớ**. Vì thế, nhận định “heap dùng `O(k)` bộ nhớ” chỉ đúng về **bộ nhớ phụ trội của thuật toán**, không phải toàn bộ mức dùng RAM của ứng dụng.

Nếu yêu cầu phải đọc hàng triệu dòng nhưng không cần giữ tất cả, có thể thay đầu vào thành một nguồn duyệt từng bản ghi như `Iterator<Sale>` hoặc luồng dữ liệu có hợp đồng vòng đời rõ ràng. Khi đó heap có thể xử lý tuần tự với bộ nhớ tăng theo `k`, nhưng cần quản lý:

- Đọc từ database hoặc file theo lô và đóng tài nguyên đúng cách.
- Ngừng và báo lỗi phù hợp khi nguồn dữ liệu bị gián đoạn.
- Không sửa dữ liệu trong lúc duyệt nếu điều đó phá tính nhất quán của snapshot.
- Giữ hoặc khôi phục thông tin nguồn để điều tra khi số liệu xếp hạng bất thường.

**Tối ưu bộ nhớ không được đánh đổi âm thầm tính đúng đắn của dữ liệu hoặc vòng đời tài nguyên.**

## 7. Kiểm thử trước khi benchmark

Trước khi đánh giá phương án nào nhanh hơn, phải xác nhận cả hai **giải cùng một bài toán**. Nếu không, một cách sai có thể chạy nhanh hơn chỉ vì nó bỏ bớt công việc.

Ví dụ JUnit 5; giả sử hai phương thức được đặt trong cùng lớp `SaleRankings`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import org.junit.jupiter.api.Test;

class SaleRankingsTest {
    @Test
    void usesDescendingSalesThenAscendingSkuAtTies() {
        var sales = List.of(
                new SaleRankings.Sale("B", 8),
                new SaleRankings.Sale("A", 8),
                new SaleRankings.Sale("C", 12),
                new SaleRankings.Sale("D", 2));
        var expected = List.of(
                new SaleRankings.Sale("C", 12),
                new SaleRankings.Sale("A", 8));

        assertEquals(expected, SaleRankings.topKFullSort(sales, 2));
        assertEquals(expected, SaleRankings.topKHeap(sales, 2));
        assertEquals("B", sales.get(0).sku()); // Nguồn không bị đảo thứ tự.
    }

    @Test
    void handlesEmptyResultsAndKGreaterThanInput() {
        var sales = List.of(
                new SaleRankings.Sale("C", 4),
                new SaleRankings.Sale("A", 6));
        var all = List.of(
                new SaleRankings.Sale("A", 6),
                new SaleRankings.Sale("C", 4));

        assertEquals(List.of(), SaleRankings.topKFullSort(sales, 0));
        assertEquals(List.of(), SaleRankings.topKHeap(sales, 0));
        assertEquals(all, SaleRankings.topKFullSort(sales, 9));
        assertEquals(all, SaleRankings.topKHeap(sales, 9));
        assertEquals(List.of(), SaleRankings.topKHeap(List.of(), 3));
        assertThrows(IllegalArgumentException.class,
                () -> SaleRankings.topKHeap(sales, -1));
    }

    @Test
    void heapMatchesSortingOnRepeatableGeneratedSamples() {
        Random random = new Random(20261116L);
        List<SaleRankings.Sale> sales = new ArrayList<>();
        for (int i = 0; i < 2_000; i++) {
            // SKU khác nhau; doanh số thường trùng để thử tie-breaker.
            sales.add(new SaleRankings.Sale(
                    "SKU-" + i, random.nextInt(100)));
        }

        for (int k : new int[]{0, 1, 10, 100, 2_000, 2_500}) {
            assertEquals(
                    SaleRankings.topKFullSort(sales, k),
                    SaleRankings.topKHeap(sales, k),
                    "Mismatch at k=" + k);
        }
    }
}
```

**Giải thích độ tin cậy của các test:**

- Test đầu có **kỳ vọng độc lập** dựa trên chính sách sắp xếp, đặc biệt bảo vệ luật chọn SKU khi doanh số bằng nhau.
- Test thứ hai kiểm tra `k = 0`, `k > n`, danh sách rỗng và `k < 0`.
- Test cuối là **kiểm thử đối chiếu (differential testing)** giữa hai cách triển khai trên một mẫu lặp lại được nhờ seed cố định. Nó phát hiện nhiều sai lệch mà ít test ví dụ có thể bỏ sót, nhưng nếu **cả hai dùng chung comparator sai**, chúng vẫn có thể cùng cho kết quả sai. Vì thế test với kỳ vọng độc lập vẫn cần thiết.

Nên bổ sung các tình huống như dữ liệu chỉ có một phần tử, tất cả doanh số bằng nhau, doanh số bằng 0, số lượng rất lớn và danh sách nguồn không cho sửa. Nếu dữ liệu có thể chứa SKU trùng, phải thêm kiểm thử cho **bước tổng hợp** theo hợp đồng, không âm thầm kỳ vọng hàm xếp hạng tự cộng các dòng.

Không cần khẳng định chính xác một lần benchmark chạy bao nhiêu nano giây trong unit test. Những kết quả thời gian thường phụ thuộc JVM, dữ liệu, hệ điều hành và tải máy; test kiểu đó dễ không ổn định.

## 8. Đo hiệu năng mà không tự đánh lừa mình

Sau khi xác nhận tính đúng đắn, có thể so sánh các phương án trên dữ liệu đại diện và định nghĩa rõ **điều kiện thắng**.

### 8.1. Chọn chỉ số theo nhu cầu

| Mục tiêu | Chỉ số phù hợp |
| --- | --- |
| Trả bảng top 10 trong thời gian ngắn | Độ trễ mỗi lời gọi, các phân vị khi chạy dưới tải thích hợp |
| Xử lý danh sách lớn liên tục | Thông lượng hoặc tổng thời gian hoàn tất một đợt |
| Giảm áp lực bộ nhớ | Bộ nhớ đỉnh, số byte cấp phát, hoạt động GC |
| Tối ưu chi phí hạ tầng | CPU, RAM, thời gian sử dụng máy và I/O trên toàn luồng |

Không phải cùng một thuật toán sẽ tốt nhất với mọi chỉ số. Ví dụ, phương án heap có thể ít cấp phát hơn cho `k` nhỏ, nhưng nếu danh sách chỉ có vài chục dòng thì sắp xếp toàn bộ lại có thể nhanh hơn và đơn giản hơn.

### 8.2. Thiết lập benchmark có ý nghĩa

1. **Tạo đầu vào đại diện:** thử `n` nhỏ, vừa, lớn; `k = 1`, `k = 10`, `k` gần `n`; doanh số phân bố đều, nhiều phần tử bằng nhau và dữ liệu đã có thứ tự.
2. **Xác định phạm vi đo:** tính cả việc sao chép danh sách, khởi tạo heap và sắp xếp kết quả; đừng chỉ đo bước chọn phần tử mà bỏ chi phí khởi tạo thực tế.
3. **Dùng cùng điều kiện:** cùng phiên bản JDK, cấu hình JVM, phần cứng, dữ liệu và cách tạo đầu vào. Hạn chế công việc không liên quan bên trong phép đo.
4. **Tính đến JVM:** warm-up, JIT, cấp phát, GC và tối ưu loại bỏ công việc không quan sát được có thể gây số đo sai nếu benchmark tự viết sơ sài.
5. **Dùng công cụ phù hợp:** với microbenchmark Java, **JMH** hỗ trợ warm-up, fork, kiểm soát dữ liệu và cách tiêu thụ kết quả; profiler giúp tìm điểm nghẽn trước khi tối ưu.
6. **Lặp và phân tích độ dao động:** không ra quyết định chỉ từ một lần đo hoặc chênh lệch rất nhỏ có thể do nhiễu.
7. **Xác nhận đầu cuối:** nếu hệ thống dành phần lớn thời gian ở database hoặc mạng, tối ưu tại Java chỉ có ý nghĩa nếu cải thiện được chỉ số mà người dùng quan tâm.

Không nên cố làm `topKHeap` “thắng” bằng cách dùng đầu vào rất lớn và `k = 1` nếu sản phẩm thực thường cần toàn bộ danh sách; cũng không nên dùng `n = 10` để phủ nhận lợi ích của heap ở bài toán hàng triệu bản ghi.

## 9. Những đánh đổi khác ngoài Big-O

### 9.1. Bộ nhớ, boxing và GC

Một `HashMap<String, Long>` có thể thuận tiện để tra cứu, nhưng thêm đối tượng, tham chiếu, bảng băm và có thể có chi phí boxing kiểu `Long`. Một mảng `long[]` dùng dữ liệu liên tục, thường tiết kiệm bộ nhớ cho phép tính theo chỉ số, nhưng không mang sẵn ánh xạ khóa SKU hay khả năng mở rộng thuận tiện như map.

Chọn kiểu và cấu trúc cần bám theo **cách truy cập thực tế**. Đừng đổi toàn bộ mã sang mảng nguyên thủy chỉ vì giả định “mảng luôn nhanh hơn” nếu điều đó khiến nghiệp vụ khó hiểu, thao tác khóa trở nên phức tạp hoặc không cải thiện điểm nghẽn đã đo.

### 9.2. Dữ liệu có thứ tự, tính ổn định và khả năng lặp lại

Kết quả ranking có thể được dùng cho phân trang, cache hoặc so sánh giữa hai lần chạy. Nếu nhiều sản phẩm có cùng doanh số mà hệ thống không xác định thứ tự phụ, bảng xếp hạng có thể đổi thứ tự bất ngờ, gây nhảy trang hoặc test khó ổn định.

Thêm tiêu chí `sku` tăng dần trong ví dụ không phải chỉ để đẹp mã: nó là **quyết định về hợp đồng đầu ra**. Nếu SKU có ý nghĩa so sánh khác (chẳng hạn cần sắp theo ID số thay vì chuỗi), comparator phải phản ánh đúng yêu cầu.

### 9.3. Khả năng sửa đổi và trách nhiệm duy trì

Một giải pháp có chi phí lý thuyết thấp nhưng gồm nhiều cấu trúc trung gian, comparator khó hiểu và trạng thái cập nhật phân tán có thể khó sửa hơn giải pháp đơn giản. Trước khi thêm chỉ mục hoặc cache, hãy tính cả:

- Ai xây dựng, làm mới và giải phóng cấu trúc dữ liệu?
- Dữ liệu thay đổi có làm chỉ mục cũ sai không?
- Có nguy cơ hai nguồn sự thật cho cùng thông tin không?
- Có kiểm thử bảo vệ quy tắc trùng khóa, thứ tự và lỗi cạnh tranh không?
- Lợi ích đo được có đủ bù chi phí duy trì không?

Một cấu trúc dữ liệu phù hợp phải được **đặt tại ranh giới trách nhiệm rõ ràng**, chứ không chỉ xuất hiện vì một đoạn mã có vẻ chạy nhanh hơn.

## 10. Những sai lầm thường gặp

**“`HashMap` luôn nhanh hơn `ArrayList`.”** Với một lần duyệt danh sách ngắn, chi phí tạo map có thể nhiều hơn lợi ích. Cần xét số lần tra cứu, kích thước và bộ nhớ.

**“`O(1)` nghĩa là một thao tác có thời gian cố định trong mọi trường hợp.”** Big-O phụ thuộc mô hình và giả định. Hashing, va chạm, cấp phát và tải máy có thể ảnh hưởng đáng kể.

**“`PriorityQueue` tự trả toàn bộ phần tử theo thứ tự ưu tiên khi dùng `for-each`.”** Sai. Heap bảo đảm phần tử đầu có ưu tiên cao theo comparator; thứ tự iterator không phải kết quả đã sắp.

**“Dùng set để khử trùng sẽ không làm mất thông tin.”** Chỉ đúng nếu phần tử trùng không mang ý nghĩa. Với giao dịch trùng SKU, cần tổng hợp hay giữ mọi giao dịch theo hợp đồng.

**“Độ phức tạp thời gian tốt hơn nghĩa là tổng thể tốt hơn.”** Có thể đổi CPU lấy RAM, tăng GC, mất thứ tự, khó kiểm thử hoặc tạo cơ chế làm mới dữ liệu phức tạp.

**“Benchmark xanh là đủ.”** Một phương án chạy nhanh nhưng sai tie-breaker hoặc làm thay đổi dữ liệu đầu vào không đáp ứng hợp đồng. Phải kiểm chứng hành vi trước khi so hiệu năng.

**“Nên tối ưu khi nhìn thấy vòng lặp.”** Vòng lặp không nhất thiết là điểm nghẽn. Dùng profiler và số liệu đầu cuối để xác định nơi thực sự đáng đầu tư.

**“Một benchmark ở máy phát triển đại diện cho mọi môi trường.”** Kết quả phụ thuộc JDK, CPU, GC, dữ liệu và cấu hình; cần đo trong điều kiện đại diện cho quyết định cần đưa ra.

## 11. Checklist khi chọn thuật toán và cấu trúc dữ liệu

Trước khi đưa một phương án vào code review, hãy tự trả lời:

1. **Hợp đồng kết quả là gì?** Có thứ tự, trùng lặp, giá trị biên hoặc điều kiện lỗi nào phải giữ?
2. **Thao tác quan trọng nhất là gì?** Tra cứu theo khóa, duyệt tuần tự, chèn/xóa, lấy ưu tiên cao nhất, hay chỉ lấy top K?
3. **Quy mô và phân bố dữ liệu có đại diện không?** Bao nhiêu phần tử, bao nhiêu lần truy vấn, bao nhiêu phần tử bằng khóa/điểm?
4. **Chi phí thời gian và bộ nhớ được phân tích theo biến nào?** Có tính chi phí khởi tạo, sao chép, cập nhật và xử lý kết quả?
5. **Cấu trúc có ràng buộc vòng đời không?** Chỉ mục, cache, heap hoặc stream được xây và giải phóng ở đâu?
6. **Đầu vào thay đổi hay có nhiều luồng cùng dùng không?** Ai quản lý tính nhất quán và điều kiện cạnh tranh?
7. **Có bằng chứng tính đúng đắn không?** Test tình huống biên, test đối chiếu và kiểm tra giả định nguồn dữ liệu?
8. **Đã đo đúng điểm nghẽn chưa?** Có benchmark/profiler và tín hiệu đầu cuối đủ tin cậy không?
9. **Giải pháp còn dễ hiểu và dễ thay đổi không?** Một người khác có thể giải thích comparator, điều kiện chọn và dữ liệu phải đồng bộ không?

Nếu bài toán đơn giản và chưa có vấn đề hiệu năng, **giải pháp rõ ràng, đúng và dễ kiểm thử** thường là điểm khởi đầu tốt. Khi yêu cầu hoặc số liệu cho thấy cần tối ưu, hãy đổi cấu trúc dữ liệu có chủ đích và bảo vệ ngữ nghĩa đầu ra bằng kiểm thử.

## 12. Tự kiểm tra

**Câu 1.** Một danh sách có 50 SKU và bạn chỉ cần kiểm tra sự tồn tại của một SKU đúng một lần. Có nên luôn xây `HashSet` trước khi tìm không? Vì sao?

**Câu 2.** Với một triệu sản phẩm và `k = 10`, top-K heap có chi phí lý thuyết nào so với sắp xếp toàn bộ? Vì sao con số này chưa đủ để kết luận cách B chắc chắn nhanh hơn?

**Câu 3.** Trong ví dụ `SaleRankings`, nếu hai SKU bán bằng nhau tại ranh giới top K, tiêu chí nào quyết định lựa chọn? Nếu bỏ tiêu chí ấy có thể gây hậu quả gì?

**Câu 4.** Vì sao không nên dùng `PriorityQueue` rồi trả `new ArrayList<>(heap)` trực tiếp cho một API hứa kết quả đã sắp xếp?

**Câu 5.** Nếu `List<Sale>` chứa hai bản ghi cùng SKU nhưng khác số lượng, tại sao việc đổi từ sort sang heap không giải quyết được yêu cầu xếp hạng **theo sản phẩm**?

**Câu 6.** Khi test đối chiếu hai thuật toán đều xanh, còn cần kiểm tra bằng chứng nào về tính đúng đắn?

**Gợi ý:** (1) Không nhất thiết; duyệt trực tiếp có thể đơn giản và ít chi phí hơn. (2) Sắp xếp toàn bộ khoảng `O(n log n)` và dùng bộ nhớ phụ trội `O(n)`; heap khoảng `O(n log(k+1) + k log(k+1))`, bộ nhớ `O(k)`, nhưng JVM, dữ liệu, chi phí I/O và hệ thống thật còn ảnh hưởng. (3) SKU tăng dần; nếu không có tiêu chí phụ, kết quả có thể thiếu tính xác định và làm thay đổi phân trang. (4) Iterator của heap không bảo đảm thứ tự sắp xếp hoàn chỉnh. (5) Cả hai đang xếp hạng **bản ghi**; cần tổng hợp doanh số theo SKU trước. (6) Cần kỳ vọng độc lập từ hợp đồng, kiểm thử biên và xác nhận quy tắc nguồn dữ liệu.

## 13. Ghi nhớ

**Thuật toán và cấu trúc dữ liệu phù hợp là lựa chọn phục vụ đúng thao tác, đúng quy mô và đúng hợp đồng dữ liệu.** Big-O giúp dự đoán xu hướng chi phí, nhưng chưa đủ để quyết định về thời gian thực, bộ nhớ hay độ tin cậy. Hãy bắt đầu bằng quy tắc nghiệp vụ và ràng buộc nguồn lực, chọn phương án dễ hiểu, kiểm chứng kết quả trên các trường hợp biên rồi mới tối ưu theo bằng chứng đo được. Một lựa chọn tốt giúp mã nguồn **chạy đủ hiệu quả, đáng tin cậy và vẫn dễ thay đổi khi nhu cầu phát triển**.
