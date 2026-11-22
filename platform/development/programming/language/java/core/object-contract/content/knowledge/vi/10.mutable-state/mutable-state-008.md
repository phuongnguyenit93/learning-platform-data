# Tránh so sánh trạng thái đang bị thay đổi đồng thời mà không có chính sách nhất quán

Khi cài đặt `equals(Object)` và `hashCode()` cho đối tượng **có thể thay đổi trạng thái (mutable)**, chúng ta thường đọc nhiều trường để quyết định hai đối tượng có bằng nhau không. Nếu một luồng khác thay đổi những trường đó ngay trong lúc so sánh, kết quả có thể dựa trên **các giá trị thuộc những thời điểm khác nhau**. Chương trình khi ấy không còn một chính sách rõ ràng về trạng thái được đem ra so sánh.

Vấn đề xuất hiện đặc biệt trong Java đa luồng: một biểu thức `a.equals(b)` nhìn có vẻ là một thao tác duy nhất trong mã nguồn, nhưng bên trong có thể gồm nhiều lần đọc trường, và Java **không tự biến toàn bộ lời gọi `equals` thành một thao tác nguyên tử**.

Bài học này làm rõ rủi ro, mối liên hệ với hợp đồng đối tượng và các chính sách có thể áp dụng: ưu tiên đối tượng bất biến, lấy snapshot nhất quán, hoặc đồng bộ hóa toàn bộ quá trình đọc và ghi khi thực sự cần đối tượng mutable.

## 1. Hợp đồng `equals()`/`hashCode()` khi trạng thái thay đổi

Với hai đối tượng `a` và `b`, một triển khai `equals` hợp lệ phải có tính phản xạ, đối xứng, bắc cầu, kết quả nhất quán khi thông tin dùng để so sánh **không thay đổi**, và `a.equals(null)` phải là `false`. Với `hashCode`, nếu `a.equals(b)` là `true`, hai mã băm phải bằng nhau. Theo hợp đồng `Object.hashCode`, các lần gọi liên tiếp phải giữ kết quả khi không có thông tin dùng trong `equals` thay đổi.

Điều kiện **“khi thông tin dùng để so sánh không thay đổi”** rất quan trọng. Nếu trạng thái thật sự biến đổi, kết quả `equals` hoặc `hashCode` có thể thay đổi theo quy tắc của lớp; đó không tự nó là vi phạm hợp đồng. Nhưng khi một luồng đọc trong lúc luồng khác ghi, thiếu chính sách đồng bộ hóa còn gây thêm ba rủi ro:

- **Đọc không nhất quán:** một trường được đọc từ phiên bản cũ, trường khác từ phiên bản mới, khiến phép so sánh phản ánh một trạng thái không được công bố như một chỉnh thể.
- **Kết quả phụ thuộc lịch thực thi:** cùng một cặp tham chiếu, hai lần so sánh sát nhau có thể cho kết quả khác nhau, hoặc không phản ánh thời điểm logic mà chương trình mong muốn.
- **Quan hệ `equals` và `hashCode` tại thời điểm sử dụng không phù hợp:** `equals` và `hashCode` có thể quan sát các phiên bản dữ liệu khác nhau nếu thao tác đồng thời, đặc biệt nguy hiểm với khóa của collection dựa trên hash.

Đặc tả `equals` không hứa tính ổn định khi các trường liên quan đang bị sửa; chính thiết kế luồng và hợp đồng của lớp phải xác định điều gì xảy ra trong trường hợp đó.

## 2. Vì sao so sánh từng trường có thể nhìn thấy trạng thái pha trộn?

Giả sử một cấu hình logic phải thay đổi **đồng thời** hai trường `endpoint` và `timeoutMs`:

| Thời điểm | `endpoint` | `timeoutMs` | Ý nghĩa |
| --- | --- | --- | --- |
| Phiên bản 1 | `alpha` | `100` | Cấu hình cũ hợp lệ |
| Trong quá trình cập nhật từng trường | `beta` | `100` | Trạng thái trung gian nếu hai trường được gán riêng |
| Phiên bản 2 | `beta` | `200` | Cấu hình mới hợp lệ |

Đoạn minh họa sau **chưa phải chương trình độc lập**:

```java
// Đang nằm trong một equals(Object) đã kiểm tra đúng kiểu.
return timeoutMs == other.timeoutMs
        && Objects.equals(endpoint, other.endpoint);
```

Nếu có thread khác cập nhật cùng đối tượng, hai biểu thức có thể đọc các trường vào những thời điểm khác nhau. Ngay cả nếu mỗi trường được khai báo `volatile`, **volatile chỉ mang lại các bảo đảm visibility và ordering thích hợp cho từng truy cập**, chứ không gộp các lần đọc `endpoint` và `timeoutMs` thành một snapshot nguyên tử.

Tương tự:

- `Objects.equals(x, y)` giúp xử lý `null`; nó **không khóa** `x` hoặc `y`.
- `synchronized` trên mỗi getter riêng lẻ chỉ bảo vệ từng lần gọi; nếu mở khóa giữa hai getter, writer vẫn có thể chen vào.
- `ConcurrentHashMap` bảo vệ các hoạt động của map theo hợp đồng của nó, **không tự bảo vệ các trường mutable bên trong key/value**.
- Ngay cả `AtomicInteger`/hai `AtomicReference` độc lập cũng không tạo giao dịch cho cả cặp trường.

Đừng dựa vào việc “trong lúc thử nghiệm chưa thấy lỗi”: lỗi phụ thuộc lịch chạy, CPU, tối ưu hóa và cách đồng bộ hóa.

## 3. Chính sách ưu tiên: so sánh các giá trị bất biến

Cách đơn giản và dễ kiểm chứng nhất là **định nghĩa trạng thái cần so sánh như một đối tượng bất biến**. Thay vì cập nhật từng trường trực tiếp trên đối tượng đang được người khác đọc, tạo một giá trị mới rồi công bố toàn bộ bằng một phép thay thế tham chiếu nguyên tử.

Trong Java 17+, `record` phù hợp để biểu diễn một snapshot có các component đơn giản, bất biến như `String` và `int`. Record tự sinh `equals`, `hashCode` và `toString` dựa trên component. Lưu ý: một `record` chứa tham chiếu đến `List` hoặc mảng **không tự làm sâu dữ liệu bên trong trở nên bất biến**; nếu phần được tham chiếu còn mutable, phải sao chép phòng vệ hoặc dùng biểu diễn bất biến phù hợp.

### Chương trình Java 17+ chạy được

Lưu thành **`SnapshotComparisonDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class SnapshotComparisonDemo {
    record Settings(String endpoint, int timeoutMs) {}

    static final class LiveSettings {
        private final AtomicReference<Settings> current =
                new AtomicReference<>(new Settings("alpha", 100));

        Settings snapshot() {
            return current.get();
        }

        void replace(Settings next) {
            current.set(next);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        LiveSettings live = new LiveSettings();

        Settings before = live.snapshot();
        CountDownLatch startWriter = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            try {
                startWriter.await();
                live.replace(new Settings("beta", 200));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        writer.start();

        startWriter.countDown();
        writer.join();

        Settings after = live.snapshot();
        Settings equalCopy = new Settings("alpha", 100);

        System.out.println("Before: " + before);
        System.out.println("After: " + after);
        System.out.println("Old snapshot unchanged: " + before);
        System.out.println("Before equals copy: " + before.equals(equalCopy));
        System.out.println("Before hash matches copy: "
                + (before.hashCode() == equalCopy.hashCode()));
        System.out.println("Before equals after: " + before.equals(after));
    }
}
```

Biên dịch và chạy:

```bash
javac SnapshotComparisonDemo.java
java SnapshotComparisonDemo
```

Kết quả xác định:

```text
Before: Settings[endpoint=alpha, timeoutMs=100]
After: Settings[endpoint=beta, timeoutMs=200]
Old snapshot unchanged: Settings[endpoint=alpha, timeoutMs=100]
Before equals copy: true
Before hash matches copy: true
Before equals after: false
```

**Vì sao ví dụ an toàn với cập nhật đồng thời?**

1. `Settings` là một giá trị bất biến trong phạm vi ví dụ: cả `endpoint` (`String` bất biến) và `timeoutMs` không bị thay đổi sau khi tạo record.
2. `AtomicReference<Settings>` giữ **một tham chiếu** đến toàn bộ cấu hình. `current.set(next)` công bố một record mới bằng thay thế tham chiếu nguyên tử, thay vì ghi hai trường của record đang được reader sử dụng.
3. `snapshot()` gọi `current.get()` **một lần**. Reader có thể nhận toàn bộ phiên bản cũ hoặc toàn bộ phiên bản mới nếu cập nhật đang diễn ra, nhưng không nhận cặp trường pha trộn do đọc riêng.
4. `CountDownLatch` và `Thread.join()` trong ví dụ chỉ làm rõ thứ tự quan sát để stdout có thể kiểm tra chính xác. Khi thread writer kết thúc, `after` là phiên bản mới. `before` vẫn giữ trạng thái cũ.
5. `before.equals(equalCopy)` và `before.hashCode() == equalCopy.hashCode()` nhất quán vì hai snapshot không còn biến đổi.

Giải pháp `AtomicReference` phù hợp khi một phép cập nhật là **thay thế toàn bộ giá trị trạng thái**. Nếu nhiều writer cần thay đổi dựa trên giá trị hiện tại và không được phép ghi đè cập nhật của nhau, phải dùng chính sách phù hợp như `compareAndSet`/vòng lặp `updateAndGet` với hàm cập nhật không có side effect ngoài ý muốn, hoặc khóa khi có các bất biến phức tạp.

## 4. Một lần chụp trạng thái của từng đối tượng chưa chắc là một snapshot toàn cục

Giả sử có **hai đối tượng mutable độc lập** `left` và `right`. Nếu lấy `left.snapshot()` tại thời điểm T1 rồi lấy `right.snapshot()` tại T2, hai bản chụp riêng lẻ có thể nhất quán, nhưng **không bảo đảm cùng một thời điểm logic**.

Có ba chính sách thường gặp; cần **chọn và công bố rõ** một chính sách cho API:

| Chính sách | Ý nghĩa phép so sánh | Khi phù hợp |
| --- | --- | --- |
| So sánh hai snapshot được lấy riêng | Mỗi phía là một giá trị hợp lệ tại thời điểm chụp; không hứa cùng thời điểm | So sánh cấu hình độc lập, log, UI cho phép trạng thái chênh thời gian |
| Snapshot nhất quán dưới cùng một khóa | Chặn writer liên quan trong toàn bộ khoảng chụp cả hai phía | Cần đảm bảo các trường/nhiều đối tượng cùng thuộc một phiên bản logic |
| Snapshot theo phiên bản/giao dịch | Chỉ so khi đọc được một phiên bản thỏa điều kiện kiểm chứng; nếu có xung đột thì thử lại | Hệ thống có version counter, optimistic read hoặc transaction hỗ trợ |

Nếu có thể bảo vệ cả hai đối tượng dưới **một khóa chung**, thao tác so sánh phải giữ khóa trong suốt quá trình tạo giá trị đọc được. Với hai khóa độc lập, phải định nghĩa **thứ tự lấy khóa cố định** để tránh deadlock và đảm bảo mọi writer đọc/ghi liên quan tuân thủ cùng giao thức. Chỉ khóa một phía, hoặc mỗi phía một lần rồi thả khóa, chưa chắc giải quyết được yêu cầu nhất quán toàn cục.

Một dạng so sánh snapshot cấp ứng dụng:

```java
// Pseudocode Java: caller giữ khóa/thực hiện transaction phù hợp
// trước khi tạo cả hai snapshot.
var leftSnapshot = left.captureState();
var rightSnapshot = right.captureState();
return leftSnapshot.equals(rightSnapshot);
```

Đây là **mẫu thiết kế**, không phải đoạn chạy độc lập: hai phương thức `captureState()` và cơ chế khóa/transaction phải được ứng dụng cung cấp. Dù code nhìn ngắn, tính đúng đắn đến từ **giao thức điều phối writer/reader**, không đến từ tên phương thức.

Với cơ chế optimistic versioning, reader có thể đọc version trước và sau dữ liệu rồi chấp nhận chỉ khi version hợp lệ, dữ liệu không bị thay đổi trong khoảng đọc. Việc triển khai versioning cần memory visibility, quy tắc writer và thứ tự cập nhật chính xác. Kiểm tra version sơ sài, không có giao thức writer phù hợp, hoặc bỏ qua vấn đề thay đổi rồi quay lại cùng version có thể vẫn sai.

## 5. Khi nào nên tránh ghi đè `equals` theo trạng thái sống?

Một số lớp thực chất đại diện cho **thực thể có danh tính ổn định** (ví dụ đơn hàng có ID), còn các thuộc tính như trạng thái, giá, mô tả, vị trí thay đổi theo thời gian. Nếu `equals` so mọi thuộc tính đang sống, cùng một thực thể trước và sau cập nhật có thể được xem là “không bằng nhau”; đôi khi đó không phải mục tiêu của mô hình.

Hãy định nghĩa trước điều gì là “bằng nhau”:

- **Value object:** hai đối tượng bằng nhau khi **giá trị logic bất biến** của chúng bằng nhau. Snapshot hoặc record bất biến là lựa chọn tự nhiên.
- **Entity có ID ổn định:** phép so sánh có thể dựa trên **mã định danh ổn định, duy nhất theo miền nghiệp vụ**, được cấp phát và quản lý nhất quán. Nếu ID được gán trễ hoặc thay đổi vòng đời, thiết kế `equals`/`hashCode` cần xử lý cẩn thận; không tự thay ID bằng `hashCode`.
- **Mutable state đang xử lý đồng thời:** nhiều trường có thể thay đổi nhưng không cần thuộc `equals` của wrapper. Cung cấp API `snapshot()` để người gọi **so sánh phiên bản đã đóng băng**, và ghi rõ semantics chụp trạng thái.

Không phải mọi lớp đều nên ghi đè `equals`. Với một đối tượng quản lý tài nguyên/phiên giao dịch mà ngữ nghĩa của nó là danh tính instance, `Object.equals` mặc định có thể đúng hơn việc đọc trạng thái thay đổi liên tục.

## 6. Đặc biệt nguy hiểm: mutable key trong `HashMap` hoặc `HashSet`

Giả sử `hashCode` phụ thuộc `status` hoặc `name`, rồi đối tượng được đặt làm key của `HashMap`. Nếu sau đó một luồng khác đổi trường ấy, `hashCode` tại thời điểm tra cứu có thể khác với hash khi chèn, khiến `map.get(key)` không tìm được phần tử ngay cả khi còn giữ chính tham chiếu key.

Điều này **không được chữa** chỉ bằng cách dùng `ConcurrentHashMap`. Map có thể xử lý đồng thời các thao tác map theo hợp đồng, nhưng không biến một object key với `equals`/`hashCode` mutable thành khóa ổn định.

Các cách an toàn hơn:

- Dùng key bất biến như `String`, `UUID`, `record Key(...)` chứa thành phần bất biến, hoặc ID miền nghiệp vụ ổn định.
- Nếu cần tra cứu theo snapshot, chèn **snapshot bất biến** làm key; bản snapshot cũ giữ nguyên nội dung và hash sau khi trạng thái sống được cập nhật.
- Nếu phải dùng key mutable, cần một giao thức rất chặt để không đổi các trường tham gia `equals`/`hashCode` trong toàn bộ thời gian key đang nằm trong cấu trúc băm. Việc khóa quanh `put` đơn lẻ không đủ nếu field vẫn đổi về sau.

Ví dụ, trong chương trình phần 3, đối tượng `Settings` đã được lấy ra từ `live.snapshot()` không đổi khi `live.replace(...)` được gọi; dùng snapshot làm key có ý nghĩa ổn định hơn dùng wrapper sống và một `hashCode` thay đổi theo `current.get()`.

## 7. Những ngộ nhận phổ biến

1. **“Đã đánh dấu `volatile` cho từng trường, cả cặp sẽ nhất quán.”** Không. Từng lần đọc/ghi có visibility thích hợp, nhưng cặp thao tác không tự trở thành transaction.
2. **“Dùng `synchronized` trên getter là đủ.”** Chưa chắc. Writer có thể chen giữa hai getter nếu khóa đã thả; yêu cầu snapshot nhiều trường cần giữ cùng giao thức cho toàn bộ khoảng chụp.
3. **“Gọi `Objects.equals` tự động thread-safe.”** Không. Nó chỉ chọn xử lý `null` rồi gọi `equals` khi cần.
4. **“Record lúc nào cũng bất biến sâu.”** Không. Các component tham chiếu có thể trỏ tới danh sách, mảng hoặc đối tượng mutable. Cần đóng băng/sao chép dữ liệu mà `equals` và `hashCode` phụ thuộc.
5. **“Hai snapshot riêng lẻ đồng nhất có nghĩa cùng thời điểm.”** Không. Nếu yêu cầu một giao dịch nhất quán giữa nhiều thực thể, phải điều phối quá trình chụp.
6. **“`ConcurrentHashMap` sẽ sửa mọi lỗi với key thay đổi.”** Không. Quy tắc về key và hợp đồng băm vẫn do ứng dụng đảm bảo.
7. **“Có thể sửa lỗi race bằng cách đọc lại cho tới khi hai lần giống nhau.”** Không thể coi đó là bảo đảm chung nếu thiếu versioning/đồng bộ hóa được writer tuân thủ; giá trị có thể thay đổi qua lại, visibility có thể không phù hợp, và vòng lặp có thể không kết thúc.
8. **“`a.equals(b)` luôn cho một kết quả duy nhất cho một cặp tham chiếu.”** Điều này chỉ có ý nghĩa khi quy tắc `equals` và trạng thái được giữ đủ ổn định. Với dữ liệu sống có thể sửa, hãy nói rõ so **phiên bản nào**.

## 8. Checklist khi thiết kế và review

Trước khi sử dụng `equals`/`hashCode` trên dữ liệu có cập nhật đa luồng, trả lời các câu hỏi sau:

1. Những trường nào quyết định tính bằng nhau? Chúng là bất biến hay có thể được sửa bởi thread khác?
2. Có yêu cầu một snapshot cùng thời điểm cho nhiều trường hoặc nhiều đối tượng hay chỉ cần mỗi đối tượng nhất quán riêng?
3. Mọi reader và writer có dùng cùng giao thức (atomic publication, khóa, versioning hay transaction) không?
4. Nếu dùng khóa, phạm vi khóa có bao trọn **toàn bộ thao tác đọc dữ liệu cần so sánh** không? Có nguy cơ deadlock giữa hai khóa không?
5. Nếu so sánh hai snapshot, chúng có chứa bản sao sâu/bất biến phù hợp của các thành phần mutable không?
6. Đối tượng có đang làm key của map/set dựa trên hash không? Hash và các trường tham gia `equals` có ổn định trong toàn bộ thời gian lưu trong map/set không?
7. Bài test có kiểm tra nhiều luồng cập nhật, nhiều phiên bản, và bất biến miền nghiệp vụ không? Có cách đo/ghi lại được phiên bản snapshot khi debug không?

**Ghi nhớ:** `equals()` là phép kiểm tra theo một **quy tắc bằng nhau**, không phải hàng rào đồng bộ. Khi trạng thái có thể bị sửa đồng thời, phải định nghĩa rõ **phiên bản được so sánh** và bảo đảm reader/writer cùng tuân thủ chính sách đó. Ưu tiên so sánh **snapshot bất biến**; nếu cần trạng thái nhiều đối tượng tại một thời điểm logic, dùng cơ chế đồng bộ hóa hoặc transaction đủ phạm vi.
