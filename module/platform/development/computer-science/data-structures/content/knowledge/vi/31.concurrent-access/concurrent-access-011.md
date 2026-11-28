# Chọn cấu trúc theo tỷ lệ đọc–ghi và yêu cầu nhất quán

Một bảng tra cứu chứa 200.000 sản phẩm có thể được truy cập bởi hàng trăm luồng. Nếu mỗi giây có 99.000 yêu cầu đọc giá và 1.000 yêu cầu sửa giá, cách tổ chức phù hợp có thể khác hẳn hệ thống ghi nhận 50.000 cập nhật số dư và 50.000 lần đọc số dư mỗi giây. Số lượng phần tử giống nhau, nhưng **mẫu truy cập** và **bảo đảm về kết quả mà ứng dụng cần** mới là hai yếu tố quyết định cấu trúc dữ liệu.

Trong chương *Truy cập đồng thời* của môn Cấu trúc dữ liệu, ta không chỉ hỏi “tra cứu mất bao lâu?” mà còn phải hỏi: *Một lần đọc có thể diễn ra trong khi luồng khác đang ghi không? Nó có được thấy giá trị cũ không? Hai trường liên quan có phải nhất quán với nhau không? Luồng ghi có bị chờ vô hạn không?*

Bài học này xây dựng cách lựa chọn giữa cấu trúc có **mutex**, khóa đọc–ghi, phân vùng (*sharding*), bảng băm đồng thời, dữ liệu bất biến với cơ chế thay phiên bản, và cấu trúc không khóa. Các kết luận được đặt trong bối cảnh thao tác trên **một tiến trình có nhiều luồng**; khi chuyển sang hệ thống nhiều máy, cần bổ sung các vấn đề như mạng, bản sao và lỗi phân vùng.

## 1. Đo tải công việc trước khi chọn cấu trúc

Gọi:

- $R$: số thao tác đọc trong khoảng đo;
- $W$: số thao tác ghi, bao gồm chèn, sửa và xóa;
- $n$: số phần tử đang được lưu;
- $p$: số luồng thực hiện thao tác đồng thời.

Tỷ lệ đọc là:

$$
r = \frac{R}{R+W}, \qquad 0 \le r \le 1.
$$

Khi $R+W=0$, chưa có tải để tính tỷ lệ. Thông thường, ta mô tả tải bằng “99% đọc, 1% ghi” hoặc “đọc:ghi = 9:1”, thay vì chỉ đưa ra tổng số yêu cầu.

| Mẫu tải | Ví dụ | Tác động tới thiết kế |
|---|---|---|
| Đọc áp đảo, cập nhật hiếm | Bảng cấu hình, danh mục sản phẩm | Có thể ưu tiên đường đọc ít đồng bộ và snapshot bất biến |
| Đọc và ghi tương đương | Phiên người dùng, tồn kho | Cần cân bằng chi phí khóa, tranh chấp và thời gian cập nhật |
| Ghi dày đặc | Bộ đếm sự kiện, hàng đợi công việc | Cân nhắc gom cập nhật, phân vùng, thao tác nguyên tử |
| Nhiều thao tác trên cùng vài khóa | Một mặt hàng “hot”, một bộ đếm toàn cục | Tranh chấp tại khóa nóng quyết định hiệu năng |
| Đọc dài hoặc quét toàn bộ | Báo cáo, duyệt hàng triệu phần tử | Khóa đọc lâu có thể làm chậm hoặc bỏ đói luồng ghi |

Tỷ lệ đọc–ghi **chưa đủ**: hai hệ thống cùng 95% đọc có thể khác xa nếu hệ thống A đọc các khóa phân tán, còn hệ thống B liên tục truy cập một khóa duy nhất. Cũng cần biết độ dài mỗi thao tác, số luồng, số khóa nóng, cách phân phối yêu cầu, kích thước payload và ngân sách bộ nhớ.

### Chi phí lý thuyết và chi phí tranh chấp

Với một cấu trúc truy cập trực tiếp trong điều kiện không tranh chấp, ta có thể mô tả chi phí trung bình của một yêu cầu bằng công thức minh họa:

$$
C_{\mathrm{base}} = r C_{\mathrm{read}} + (1-r) C_{\mathrm{write}}.
$$

Đây chỉ là **trung bình có trọng số của chi phí thao tác đơn lẻ**, không phải công thức dự báo thông lượng hệ thống đồng thời. Khi số luồng tăng, thời gian thực còn có chờ khóa, cache-line bouncing, tái cấp phát, chuyển ngữ cảnh, thời gian thu hồi bộ nhớ và sự mất cân bằng giữa các khóa.

## 2. “Nhất quán” là yêu cầu nào?

Trong cấu trúc dữ liệu đồng thời, nhiều yêu cầu thường bị gọi chung là “nhất quán” dù có ý nghĩa khác nhau:

| Yêu cầu | Điều cần được bảo đảm | Ví dụ |
|---|---|---|
| **Không có data race** | Các truy cập xung đột tuân theo mô hình bộ nhớ của ngôn ngữ | Đọc và ghi `std::unordered_map` phải được đồng bộ |
| **Nguyên tử theo thao tác** | Một thao tác không bị quan sát như mới thực hiện được một phần | Chèn một cặp khóa–giá trị |
| **Linearizability (tuyến tính hóa)** | Mỗi thao tác trông như có hiệu lực tại một thời điểm giữa lúc gọi và lúc trả kết quả; thứ tự thực phải được tôn trọng | Ghi hoàn tất trước khi đọc bắt đầu thì lần đọc phải phản ánh ghi đó hoặc một ghi mới hơn |
| **Sequential consistency (nhất quán tuần tự)** | Các thao tác tương đương một thứ tự tuần tự chung, giữ thứ tự chương trình của từng luồng; không bắt buộc giữ mọi ràng buộc thời gian thực giữa hai luồng | Một mô hình yếu hơn linearizability |
| **Snapshot nhất quán** | Các giá trị đọc thuộc một phiên bản logic phù hợp, không trộn trạng thái của nhiều lần cập nhật | Báo cáo tổng số dư từ cùng một phiên bản |
| **Chấp nhận dữ liệu cũ** | Được phép đọc một phiên bản đã xuất bản trước đó trong những giới hạn ứng dụng định nghĩa | Đọc cấu hình chưa cập nhật ngay lập tức |

Trong hệ thống phân tán, **eventual consistency** thường có nghĩa rằng các bản sao hội tụ về cùng một giá trị khi không còn cập nhật mới, với các điều kiện hoạt động thích hợp. Khái niệm đó **không mặc nhiên** là bảo đảm của mọi bảng băm đồng thời hoặc mọi cơ chế snapshot trong bộ nhớ của một tiến trình.

Đặc biệt, **an toàn bộ nhớ** và **nhất quán nghiệp vụ** là hai tầng khác nhau. Một bảng băm có thể cung cấp thao tác cập nhật nguyên tử cho từng khóa nhưng không tự bảo đảm phép chuyển tiền giữa hai tài khoản cập nhật cả hai khóa như một giao dịch.

### Ví dụ hai khóa: đọc riêng lẻ đúng, tổng thể vẫn sai

Giả sử bất biến là:

$$
\text{balance[A]} + \text{balance[B]} = 1\,000.
$$

Trước chuyển tiền: A = 600, B = 400. Một thao tác chuyển 100 thực hiện hai lần ghi riêng biệt: A thành 500 rồi B thành 500. Nếu luồng đọc xen giữa hai lần ghi, nó có thể thấy A = 500 và B = 400, tổng 900. Từng phép đọc đều truy cập **giá trị hợp lệ** của một khóa, nhưng bộ đôi giá trị **không phải snapshot nhất quán**.

Để bảo đảm chuyển tiền và báo cáo nhìn thấy một trạng thái hợp lệ, có thể giữ **cùng một mutex** khi cập nhật cả hai số dư và khi đọc cặp số dư, hoặc dùng cơ chế giao dịch/phiên bản có tính chất tương đương. Chỉ thay hai giá trị thường bằng hai biến nguyên tử độc lập vẫn chưa bảo đảm bất biến toàn cục.

## 3. Mốc so sánh: một mutex bảo vệ toàn bộ cấu trúc

Cách bắt đầu dễ kiểm chứng là một bảng băm hoặc cây tìm kiếm thông thường, được bảo vệ bằng **một mutex**:

```text
get(key):
    lock(mutex)
    result = copy(map[key]) nếu tồn tại
    unlock(mutex)
    return result

put(key, value):
    lock(mutex)
    map[key] = value
    unlock(mutex)
```

Giữ khóa suốt thời gian truy cập làm các thao tác trên cùng cấu trúc thực hiện lần lượt. Việc đọc dữ liệu phải trả về **bản sao** hoặc kết quả sở hữu độc lập; trả về tham chiếu tới một nút rồi mở khóa có thể dẫn tới truy cập phần tử đã bị xóa.

Độ phức tạp thuật toán nền vẫn quan trọng: với bảng băm, tra cứu thường có thời gian kỳ vọng $O(1)$; với cây cân bằng, tra cứu có thời gian $O(\log n)$ trong trường hợp xấu. Nhưng **thời gian chờ mutex** có thể lớn hơn cả thời gian thực hiện phép tìm.

Giải pháp một mutex có ưu thế rõ ràng: giao thức đơn giản, dễ duy trì bất biến trải trên nhiều khóa và dễ xác định điểm tuyến tính hóa. Nó là mốc đo hiệu năng đáng tin cậy trước khi bổ sung các cơ chế phức tạp.

## 4. Khóa đọc–ghi: nhiều người đọc, một người ghi

**Reader–writer lock (RW lock)** cho phép nhiều luồng đồng thời giữ khóa đọc (*shared lock*) nhưng luồng ghi phải có quyền truy cập độc quyền (*exclusive lock*).

| Hành động đang diễn ra | Đọc mới | Ghi mới |
|---|---|---|
| Không ai giữ khóa | Có thể được cấp | Có thể được cấp |
| Có luồng giữ khóa đọc | Có thể cùng đọc | Phải đợi các lượt đọc thích hợp kết thúc |
| Có luồng giữ khóa ghi | Phải đợi | Phải đợi |

Điều này có lợi khi đọc nhiều, ghi ít và mỗi lượt đọc đủ dài để bù chi phí quản lý khóa đọc. Tuy nhiên, RW lock có thể **chậm hơn mutex** khi vùng tới hạn rất ngắn hoặc số luồng tranh chấp lớn: việc duy trì số reader, đánh thức writer và điều phối bộ nhớ cũng tốn tài nguyên. Chính sách ưu tiên reader/writer khác nhau giữa các triển khai; một số chính sách có thể dẫn tới starvation.

### Ví dụ C++17: tra cứu, cập nhật và chụp snapshot dưới cùng một khóa

```cpp
#include <cstdint>
#include <mutex>
#include <optional>
#include <shared_mutex>
#include <unordered_map>
#include <utility>
#include <vector>

class PriceIndex {
private:
    mutable std::shared_mutex mu_;
    std::unordered_map<int, std::int64_t> prices_;

public:
    std::optional<std::int64_t> get(int sku) const {
        std::shared_lock<std::shared_mutex> guard(mu_);
        auto it = prices_.find(sku);
        if (it == prices_.end()) return std::nullopt;
        return it->second; // Trả về bản sao khi đang giữ khóa.
    }

    void set(int sku, std::int64_t price) {
        std::unique_lock<std::shared_mutex> guard(mu_);
        prices_[sku] = price;
    }

    std::vector<std::pair<int, std::int64_t>> snapshot() const {
        std::shared_lock<std::shared_mutex> guard(mu_);
        return std::vector<std::pair<int, std::int64_t>>(
            prices_.begin(), prices_.end());
    }
};
```

Trong ví dụ này, `get` và `set` đều được bảo vệ khỏi truy cập đồng thời không an toàn vào `unordered_map`. `snapshot` sao chép toàn bộ bảng khi giữ khóa đọc, nên không chứa hỗn hợp giá trị từ các lần ghi xen vào trong quá trình sao chép. Tuy vậy, thao tác sao chép tốn $O(n)$ thời gian và có thể buộc writer đợi lâu. Kết quả là vector **không giữ thứ tự khóa** do nguồn là bảng băm.

Lưu ý: gọi `get(A)` rồi `get(B)` là **hai thao tác đọc riêng biệt**; một writer có thể xen giữa chúng. Khi cần bất biến nhiều khóa, dùng một phương thức đọc chung với cùng phạm vi khóa hoặc một snapshot thống nhất.

## 5. Bảng băm đồng thời, phân vùng và khóa theo dải

Nếu một khóa toàn cục đang là nút nghẽn, có thể **phân vùng** (*shard/stripe*) theo hàm băm:

```text
shard_index = hash(key) mod S
shard[shard_index] = {
    lock,
    map_of_keys
}
```

Với $S$ phân vùng, hai thao tác trên **hai phân vùng khác nhau** có thể chạy song song. Những thao tác trên cùng phân vùng vẫn phải tuân theo cơ chế đồng bộ của phân vùng đó. Việc chọn $S$ là đánh đổi: nhiều phân vùng tăng khả năng song song nhưng tăng số khóa, metadata và chi phí quản lý; khóa nóng nằm cùng phân vùng vẫn có thể gây nghẽn.

| Cơ chế | Khả năng song song | Điểm cần lưu ý |
|---|---|---|
| Một mutex toàn cấu trúc | Thấp khi mọi thao tác đều tranh khóa | Bất biến nhiều khóa đơn giản |
| Một RW lock toàn cấu trúc | Nhiều lượt đọc cùng lúc | Writer vẫn cần độc quyền toàn bộ |
| Nhiều phân vùng, mỗi phân vùng một lock | Nhiều thao tác trên phân vùng khác nhau | Thao tác nhiều phân vùng đòi hỏi phối hợp |
| Concurrent hash map của thư viện | Tùy thiết kế nội bộ và API | Phải đọc hợp đồng của thao tác, iterator và snapshot |
| Atomic trên từng khóa/counter | Có thể giảm tranh chấp một số đường đi | Khó giữ bất biến trải trên nhiều khóa |

Với thao tác trên nhiều phân vùng, việc **khóa theo thứ tự cố định** (ví dụ tăng dần chỉ số phân vùng) giúp tránh deadlock do hai luồng khóa ngược thứ tự. Nếu cần snapshot toàn bảng, có thể phải khóa tất cả phân vùng, dùng cơ chế phiên bản, hoặc chấp nhận snapshot có tính nhất quán yếu hơn.

### Java: cập nhật một khóa đúng, nhưng không phải giao dịch nhiều khóa

```java
import java.util.concurrent.ConcurrentHashMap;

class EventCounts {
    private final ConcurrentHashMap<Integer, Long> counts =
        new ConcurrentHashMap<>();

    void increment(int eventId) {
        counts.compute(eventId,
            (key, oldValue) -> oldValue == null ? 1L : oldValue + 1L);
    }

    long get(int eventId) {
        return counts.getOrDefault(eventId, 0L);
    }
}
```

`compute` cung cấp cập nhật nguyên tử cho **mục tương ứng với khóa** trong `ConcurrentHashMap`; hai luồng tăng cùng một khóa không bị mất cập nhật như cách `get` rồi `put` riêng rẽ. Hàm remapping cần ngắn, tránh chặn lâu hoặc cập nhật đệ quy chính bảng trong lúc tính toán. Ví dụ dùng kiểu `long` và phép cộng có thể tràn nếu bộ đếm vượt miền giá trị; cần chính sách giới hạn nếu bài toán yêu cầu.

`ConcurrentHashMap` **không** tự biến một loạt `get` trên nhiều khóa thành snapshot nhất quán. Các iterator của nó có tính **weakly consistent**: có thể phản ánh một phần những cập nhật xảy ra đồng thời, thay vì ném lỗi do sửa đổi hoặc bảo đảm nhìn toàn bộ bảng tại cùng một thời điểm. Với nghiệp vụ cần giao dịch nhiều bản ghi, phải có giao thức đồng bộ hoặc cơ chế giao dịch bổ sung.

## 6. Dữ liệu bất biến, copy-on-write, RCU và MVCC

Khi số lượt đọc cao hơn rất nhiều số lượt ghi, một cách giảm thời gian tranh chấp là cho reader truy cập **phiên bản không thay đổi**.

### 6.1. Copy-on-write (COW) bằng snapshot

Writer tạo phiên bản mới, sửa dữ liệu trên phiên bản đó rồi **công bố** một con trỏ hoặc handle tới phiên bản hoàn chỉnh. Reader chỉ giữ phiên bản mà mình đã quan sát; writer không chỉnh sửa nó tại chỗ.

```text
writer: read current -> copy -> modify copy -> publish new version
reader: version = acquire(current) -> read version only
```

Nếu sao chép cả mảng hoặc cả bảng có $n$ phần tử, mỗi lần ghi có thể tốn $O(n)$ thời gian và bộ nhớ tạm. Với **cấu trúc persistent** (chẳng hạn cây cân bằng bất biến có structural sharing), writer chỉ tạo lại các nút trên đường đi cần thay đổi, có thể tốn $O(\log n)$ nút và thời gian trên một thao tác trong những triển khai thích hợp. Không phải mọi cấu trúc bất biến đều có chi phí cập nhật $O(\log n)$.

Việc xuất bản phiên bản mới cần **đồng bộ đúng theo mô hình bộ nhớ** (chẳng hạn atomic publication với release/acquire), và phiên bản cũ phải tồn tại cho tới khi reader cuối cùng dùng xong. COW thường hợp với cấu hình, danh mục, bảng định tuyến được đọc thường xuyên và cập nhật theo lô.

### 6.2. Read-copy-update (RCU)

RCU cũng cho reader đi trên phiên bản dữ liệu đã công bố và cho writer thay thế liên kết tới dữ liệu mới. Cơ chế RCU còn quản lý **giai đoạn chờ an toàn** (*grace period*) trước khi thu hồi phần dữ liệu cũ, để những reader đã bắt đầu trước đó có thể hoàn tất.

RCU phù hợp những đường đọc cần chi phí đồng bộ thấp, nhưng **API và cơ chế thu hồi là phần cốt lõi**; không thể thay RCU bằng một phép gán con trỏ thường trong C/C++ rồi xóa đối tượng cũ ngay. Khả năng quan sát phiên bản mới, tính tuyến tính hóa của từng thao tác và sự nhất quán giữa nhiều trường vẫn phải được xác định theo thuật toán cụ thể.

### 6.3. Multiversion concurrency control (MVCC)

MVCC giữ nhiều phiên bản để các lượt đọc có thể chọn một **mốc phiên bản nhất quán**, trong khi các lượt ghi tạo phiên bản mới. Ý tưởng này đặc biệt phổ biến ở cơ sở dữ liệu và hệ thống lưu trữ. Reader dài có thể tránh giữ khóa chặn writer trên dữ liệu đang đọc, nhưng phiên bản cũ chiếm thêm bộ nhớ và cần cơ chế dọn dẹp.

**Snapshot isolation** của một hệ quản trị giao dịch có quy tắc riêng về tính nhìn thấy, xung đột ghi và commit; không đồng nghĩa với serializability trong mọi trường hợp (có thể gặp *write skew*). Khi dùng MVCC hoặc snapshot trong một cấu trúc dữ liệu, phải định nghĩa rõ giao thức ghi và yêu cầu nhất quán, không suy rằng “có phiên bản” đồng nghĩa “mọi giao dịch đều đúng”.

### Bảng đánh đổi

| Lựa chọn | Đường đọc | Đường ghi | Bộ nhớ và vòng đời |
|---|---|---|---|
| Mutex / RW lock | Giữ khóa khi truy cập | Giữ khóa độc quyền | Thường ít phiên bản, dễ quản lý |
| Snapshot COW toàn bộ | Đọc bản bất biến đã giữ | Sao chép $O(n)$ rồi xuất bản | Có thể giữ đồng thời nhiều bản sao |
| Persistent tree + publication | Đọc theo phiên bản; thường $O(\log n)$ để tìm khóa | Có thể sửa $O(\log n)$ nút bằng sharing | Phải giữ nút chung đến khi không còn phiên bản dùng |
| RCU | Thường rất ít chi phí điều phối trên đường đọc | Cập nhật/công bố và đợi thu hồi an toàn | Grace period và reclamation là bắt buộc |
| MVCC | Đọc theo timestamp/phiên bản | Tạo và ghi nhận phiên bản mới | Tích lũy phiên bản cũ nếu reader sống lâu |

## 7. Chọn theo tính chất cập nhật và truy vấn

Không phải lúc nào dữ liệu chung cũng là một map. Dạng thao tác có thể gợi ý một cấu trúc khác:

- **Bộ đếm độc lập, thống kê tần suất:** một `atomic fetch_add` là điểm xuất phát; khi tranh chấp cực cao, bộ đếm phân mảnh hoặc `LongAdder` của Java có thể giảm áp lực lên một ô nhớ. Đổi lại, phép đọc `sum()` của bộ đếm phân mảnh không nhất thiết là một snapshot nguyên tử khi cập nhật vẫn đang diễn ra.
- **Producer–consumer FIFO:** queue có mutex và condition variable thường dễ chứng minh đúng. MPSC/SPSC/MPMC queue chuyên dụng có thể hiệu quả hơn nếu mô hình số producer và consumer đã cố định, nhưng cần hiểu ràng buộc về thứ tự FIFO, tình trạng đầy/rỗng và an toàn bộ nhớ.
- **Tập hợp truy vấn thứ tự, tiền nhiệm, khoảng:** cây cân bằng có khóa bảo vệ hoặc cấu trúc chỉ mục có phiên bản thường hữu ích hơn bảng băm thuần túy, vì bảng băm không duy trì thứ tự.
- **Bảng băm với lượng ghi trung bình và nhiều khóa phân tán:** một concurrent hash map hoặc sharding thường dễ áp dụng hơn thuật toán lock-free tự viết.
- **Cấu hình có hàng triệu lượt đọc giữa hai lần cập nhật:** một snapshot bất biến công bố an toàn có thể loại bỏ việc mỗi reader phải khóa toàn bộ dữ liệu.

Các từ “lock-free” hay “wait-free” chỉ mô tả **bảo đảm tiến triển** của thuật toán, không tự cho biết thuật toán nhanh hơn mutex. Một CAS lặp lại nhiều lần dưới tranh chấp cao, quản lý ABA và thu hồi nút sai có thể khiến một cấu trúc vừa chậm vừa không an toàn. Việc dùng primitive nguyên tử không thay thế chứng minh bất biến và tính tuyến tính hóa.

## 8. Ma trận lựa chọn theo tỷ lệ đọc–ghi và nhất quán

| Bối cảnh | Yêu cầu nhất quán | Ứng viên nên thử trước | Điều cần kiểm chứng |
|---|---|---|---|
| 99,9% đọc, cập nhật cấu hình theo phút | Cùng một phiên bản cấu hình trong một lượt đọc | Snapshot bất biến / COW / RCU | Chi phí xuất bản, phiên bản cũ, cách reader giữ snapshot |
| 90% đọc, 10% ghi, nhiều khóa khác nhau | Nhất quán theo từng khóa | Concurrent hash map hoặc sharded map | Hotspot, resize, hành vi iterator |
| 90% đọc nhưng mỗi lượt đọc quét toàn bảng | Cần bản báo cáo thống nhất | Snapshot COW, MVCC, hoặc khóa bảo vệ toàn lượt quét | Bộ nhớ phiên bản, thời gian quét, độ trễ cập nhật |
| 50% đọc, 50% ghi, chuyển tiền hai khóa | Bất biến tổng số dư, thao tác toàn vẹn | Một mutex/giao dịch trên hai khóa | Deadlock nếu nhiều lock, tính nguyên tử liên khóa |
| 10% đọc, 90% ghi, bộ đếm rất nóng | Đếm chính xác, không nhất thiết snapshot đa biến | Atomic counter; shard/aggregate nếu cho phép | Tranh chấp cache, tổng hợp, thời điểm đọc kết quả |
| Producer–consumer, cần FIFO | Thứ tự và không mất/nhân đôi phần tử | Queue có mutex trước, rồi queue đồng thời phù hợp mô hình | Backpressure, blocking, tuyến tính hóa |
| Nhiều truy vấn khoảng và thêm/xóa | Kết quả theo đúng thứ tự khóa | Cây cân bằng với đồng bộ/phiên bản | Chi phí quét, invalidation, thời gian giữ khóa |

Đây là **điểm khởi đầu cho thử nghiệm**, không phải quy tắc cứng theo phần trăm. Một ứng dụng chỉ có 1% ghi nhưng mỗi thao tác ghi mất hàng chục mili giây vẫn có thể nghẽn writer. Trái lại, với dữ liệu nhỏ và thao tác vài chục nanôgiây, phí quản lý RW lock có thể áp đảo lợi ích cho reader.

## 9. Benchmark đúng: đo thông lượng cùng độ trễ và tính đúng

### 9.1. Trục đo

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Throughput (ops/s) | Tổng số thao tác hoàn tất mỗi giây là bao nhiêu? |
| p50/p95/p99 latency | Phần lớn yêu cầu và 1% chậm nhất chờ bao lâu? |
| Writer wait time | Luồng ghi có bị trì hoãn khi nhiều reader xuất hiện không? |
| Retry / contention | CAS thất bại bao nhiêu lần, bao nhiêu thời gian mất vì khóa? |
| Bộ nhớ tối đa | Bao nhiêu bộ nhớ dành cho bucket, node, snapshot và version cũ? |
| Tính đúng | Có mất cập nhật, đọc trạng thái không hợp lệ hoặc lịch sử không tuyến tính hóa được không? |

### 9.2. Tập kịch bản thử

Giữ nguyên số phần tử $n$ và cùng bài toán nghiệp vụ rồi thay đổi tỷ lệ đọc: 100:0, 99:1, 90:10, 50:50, 10:90. Thử các mức song song $p=1,2,4,8,\ldots$ tới giới hạn máy; đo thêm phân phối khóa **đều** và **lệch mạnh về vài khóa nóng**. Phân biệt truy vấn đơn khóa với quét toàn bảng và thao tác nhiều khóa.

Khi benchmark, cần kiểm soát phần tạo request để nó không tự thành nút nghẽn; chuẩn bị dữ liệu trước; có giai đoạn làm nóng nếu runtime có JIT; đo đủ thời gian và lặp để thấy độ biến động. Với một cấu trúc có khả năng trả snapshot cũ, kiểm tra tính đúng phải dùng **hợp đồng nhất quán mà ứng dụng chấp nhận**, không áp một tiêu chuẩn mạnh hơn rồi coi mọi kết quả khác là lỗi.

Một điểm quan trọng: thông lượng cao nhưng p99 tệ có thể không phù hợp với API cần phản hồi nhanh. Bộ nhớ tăng liên tục do phiên bản cũ chưa được thu hồi cũng có thể loại một giải pháp tưởng như rất nhanh khi benchmark ngắn.

## 10. Quy trình quyết định và những lỗi thường gặp

Có thể dùng các bước sau khi thiết kế cấu trúc dùng chung:

1. **Viết bất biến dữ liệu.** Ví dụ: không trùng ID, số dư không âm, tổng hai tài khoản được bảo toàn, hoặc mỗi cấu hình đọc ra phải cùng một phiên bản.
2. **Định nghĩa đơn vị nguyên tử.** Một khóa, một đối tượng, một nhóm khóa hay cả một snapshot? Ghi rõ yêu cầu linearizability, snapshot hoặc độ cũ chấp nhận được.
3. **Đo mẫu truy cập.** Tỷ lệ đọc–ghi, độ dài thao tác, số luồng, phân phối khóa, tần suất quét và giới hạn RAM.
4. **Bắt đầu từ cách dễ kiểm chứng.** Dùng cấu trúc thường với mutex, hoặc thư viện concurrent map có hợp đồng rõ ràng.
5. **Giảm tranh chấp theo nút nghẽn thực tế.** Thử RW lock, sharding, snapshot bất biến hoặc một cơ chế chuyên dụng; mỗi cơ chế đều có chi phí về logic và bộ nhớ.
6. **Xác minh đồng bộ và vòng đời.** Kiểm tra release/acquire khi công bố dữ liệu, khóa theo thứ tự cố định nếu phối hợp nhiều lock, nguy cơ ABA, memory reclamation và chính sách fairness.
7. **So sánh trên tải đại diện.** Đánh giá throughput, p99, writer starvation, memory peak và các lịch sử thao tác cạnh tranh.

| Nhận định dễ nhầm | Điều cần nhớ |
|---|---|
| “99% đọc nghĩa là RW lock luôn tốt nhất.” | Chi phí lock, thời gian giữ lock và chính sách fairness quyết định hiệu quả thực tế. |
| “Concurrent map bảo đảm mọi thao tác liên quan nhiều khóa là nguyên tử.” | Nhiều API chỉ bảo đảm theo từng khóa hoặc từng thao tác đã định nghĩa. |
| “Dùng atomic cho từng trường là đủ giữ bất biến nhiều trường.” | Cần thêm giao thức để có snapshot hay cập nhật chung. |
| “Không dùng khóa tức là không cần đồng bộ bộ nhớ.” | CAS, RCU, COW đều cần mô hình memory ordering và an toàn vòng đời. |
| “Snapshot bất biến luôn miễn phí cho writer.” | Sao chép toàn bộ có thể tốn $O(n)$; chia sẻ cấu trúc và dọn phiên bản có chi phí riêng. |
| “Reader nhìn thấy một phiên bản cũ tức là sai.” | Phụ thuộc hợp đồng: một snapshot hợp lệ có thể cũ nếu ứng dụng cho phép. |
| “Thông lượng cao chứng minh cấu trúc tốt.” | Còn độ trễ đuôi, tính đúng, memory peak và khả năng tiến triển của writer. |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Một từ điển có 99% đọc, nhưng mỗi lượt đọc quét một triệu phần tử. Vì sao thay mutex bằng RW lock có thể chưa cải thiện hệ thống?

**Trả lời:** Nhiều reader có thể cùng giữ shared lock rất lâu, khiến writer phải chờ. Nếu báo cáo cần một phiên bản nhất quán, có thể thử snapshot COW hoặc MVCC để giảm thời gian giữ khóa, rồi đo chi phí bộ nhớ và cập nhật.

**Câu 2.** Hai luồng thực hiện `get(A)`, `get(B)` trên concurrent map, các thao tác đều an toàn luồng. Có suy ra hai giá trị thuộc cùng một thời điểm không?

**Trả lời:** Không. Một writer có thể cập nhật giữa hai lần `get`. Cần một API snapshot hoặc cơ chế cập nhật/đọc chung nếu bất biến liên khóa là bắt buộc.

**Câu 3.** Khi phân vùng một bảng thành 16 shard, có phải hệ thống có thể thực hiện chính xác 16 ghi cùng lúc không?

**Trả lời:** Không bảo đảm. Hai ghi vào cùng shard vẫn có thể tranh chấp; phân phối khóa, cấu trúc nội bộ, số lõi, cache và các thao tác đa shard quyết định mức song song đạt được.

**Câu 4.** Một ứng dụng đọc cấu hình 100.000 lần giữa hai lần ghi, và mỗi yêu cầu cần toàn bộ cấu hình nhất quán. Cách tổ chức nào đáng thử?

**Trả lời:** Một snapshot bất biến được xuất bản nguyên tử và giữ sống trong suốt lượt đọc. Cần đánh giá chi phí copy, khả năng structural sharing và thu hồi các phiên bản cũ; mutex/RW lock vẫn là phương án so sánh.

**Câu 5.** Vì sao không thể chỉ nhìn tỷ lệ đọc:ghi để quyết định dùng lock-free?

**Trả lời:** Tỷ lệ không cho biết tranh chấp khóa nóng, yêu cầu nhất quán nhiều khóa, chi phí CAS retry hay thu hồi bộ nhớ. Lock-free còn đòi hỏi chứng minh bảo đảm tiến triển và tính đúng của toàn thuật toán.

Chọn cấu trúc truy cập đồng thời là quyết định kết hợp **hình dạng tải đọc–ghi**, **bất biến và mức nhất quán cần bảo đảm**, **độ phức tạp thao tác** cùng **chi phí đồng bộ và bộ nhớ**. Một mutex đơn giản có thể là lựa chọn đúng cho nghiệp vụ cần giao dịch nhiều khóa; RW lock hoặc concurrent map hữu ích khi có thể tăng song song; snapshot bất biến/RCU/MVCC nổi bật khi đọc áp đảo và cách sử dụng phiên bản được định nghĩa rõ. Kết quả benchmark chỉ có ý nghĩa khi cấu trúc đã đáp ứng đúng hợp đồng của ứng dụng.
