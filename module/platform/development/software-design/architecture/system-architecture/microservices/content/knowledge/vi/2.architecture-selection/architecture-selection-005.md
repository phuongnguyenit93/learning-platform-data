# Điều kiện nên tiếp tục giữ kiến trúc đơn thể

## Bối cảnh và mục tiêu

Khi tìm hiểu Microservices, câu hỏi quan trọng không chỉ là “khi nào nên tách dịch vụ?” mà còn là “khi nào **chưa nên tách**?”. Kiến trúc đơn thể (monolithic architecture) có thể là lựa chọn đúng và có chủ đích nếu nó đáp ứng nhu cầu kinh doanh, khả năng vận hành và tốc độ thay đổi của đội ngũ.

**Đơn thể** nghĩa là các thành phần chính của ứng dụng được xây dựng và triển khai như một đơn vị. Điều đó **không đồng nghĩa** với mã nguồn lộn xộn. Một **modular monolith** (đơn thể có mô-đun rõ ràng) vẫn có thể phân chia miền nghiệp vụ, áp dụng nguyên tắc phụ thuộc và kiểm thử ranh giới, trong khi cùng chạy trong một tiến trình hoặc một bản triển khai.

Sau bài này, người học có thể:
- Nhận diện những điều kiện khiến đơn thể tiếp tục mang lại lợi ích lớn hơn chi phí chuyển sang Microservices.
- Phân biệt vấn đề của cách tổ chức mã nguồn với vấn đề thực sự cần phân tán hệ thống.
- Dùng bằng chứng về sản phẩm, đội ngũ, tải, vận hành và dữ liệu để ra quyết định.
- Xác định các ngưỡng cần xem xét lại kiến trúc và cách chuẩn bị đường tách dịch vụ về sau.

## 1. Trước hết, hiểu rõ lựa chọn đang so sánh

| Cách tổ chức | Đặc điểm | Điểm cần chú ý |
| --- | --- | --- |
| Đơn thể thiếu mô-đun | Nhiều chức năng trong một ứng dụng; phụ thuộc và ranh giới nghiệp vụ có thể bị trộn lẫn | Khó bảo trì chủ yếu vì thiết kế bên trong |
| Đơn thể có mô-đun (modular monolith) | Một đơn vị triển khai nhưng phân chia các mô-đun nghiệp vụ, API nội bộ và quyền sở hữu dữ liệu rõ ràng | Phù hợp khi cần giữ giao dịch và vận hành đơn giản |
| Microservices | Nhiều dịch vụ tự triển khai; giao tiếp qua mạng và sở hữu hợp đồng/dữ liệu riêng | Tăng khả năng tự chủ nhưng phát sinh phân tán, nhất quán, giám sát và điều phối |

Một ứng dụng có một kho mã và một pipeline không nhất thiết là vấn đề. Ngược lại, việc chia thành nhiều dịch vụ nhưng mọi thay đổi đều phải triển khai đồng loạt và dùng chung bảng dữ liệu chưa tạo ra được tính tự chủ thực sự.

**Câu hỏi ra quyết định:** Vấn đề hiện tại có bắt buộc cần nhiều đơn vị triển khai và vận hành độc lập để giải quyết không? Nếu không, hãy ưu tiên cải thiện cấu trúc, quy trình và hiệu năng trong kiến trúc đang có.

## 2. Những điều kiện nên tiếp tục giữ kiến trúc đơn thể

### 2.1. Sản phẩm và ranh giới nghiệp vụ còn thay đổi nhanh

Nếu nhóm vẫn đang khám phá yêu cầu, luồng nghiệp vụ thay đổi liên tục, và chưa hiểu rõ đâu là miền nghiệp vụ có vòng đời độc lập, việc tách Microservices quá sớm có thể đóng cứng ranh giới sai.

**Dấu hiệu thực tế:**
- Tính năng mới thường thay đổi đồng thời dữ liệu, quy tắc và luồng ở nhiều phần.
- Tên gọi, trách nhiệm và ranh giới giữa các miền nghiệp vụ chưa ổn định.
- Đội ngũ thường xuyên thử nghiệm, bỏ bớt hoặc thiết kế lại chức năng.

**Vì sao đơn thể phù hợp:** Việc chỉnh ranh giới mô-đun, đổi kiểu dữ liệu và tái cấu trúc giao dịch trong một codebase đơn giản hơn thay đổi hàng loạt hợp đồng API, thông điệp và dữ liệu giữa các dịch vụ độc lập.

**Cách làm:** Nhóm mã theo năng lực nghiệp vụ, làm rõ API nội bộ và ghi nhận những nơi đang liên kết quá chặt. Giữ quyền thay đổi ranh giới khi học thêm về miền nghiệp vụ.

### 2.2. Đội ngũ còn nhỏ và phối hợp trực tiếp hiệu quả

Nếu một hoặc vài nhóm nhỏ có thể cùng hiểu hệ thống, thống nhất thay đổi và phát hành mà không xếp hàng chờ nhau, chi phí sở hữu nhiều dịch vụ có thể vượt quá lợi ích.

**Dấu hiệu thực tế:**
- Mỗi thay đổi được thống nhất nhanh giữa những người chịu trách nhiệm.
- Chưa có nhiều nhóm cần lịch phát hành độc lập.
- Năng lực chuyên môn về hạ tầng, bảo mật, giám sát và xử lý sự cố còn tập trung ở ít người.

**Vì sao đơn thể phù hợp:** Microservices yêu cầu đội ngũ quản lý thêm hợp đồng API, version, discovery, kết nối, CI/CD của từng dịch vụ, phân quyền, điều tra lỗi liên dịch vụ và vận hành nhiều tài nguyên. Số dịch vụ tăng không tự làm tăng năng suất của một nhóm nhỏ.

**Cách làm:** Thiết lập ownership theo mô-đun, quy ước review và kiểm thử ranh giới. Khi tổ chức lớn lên, dùng dữ liệu về thời gian chờ và xung đột thay đổi để quyết định có cần triển khai độc lập hay không.

### 2.3. Một bản triển khai vẫn đáp ứng nhịp phát hành

Nếu ứng dụng có thể build, test, deploy và rollback đủ nhanh so với nhu cầu kinh doanh, không có nhu cầu bắt buộc phải triển khai các phần theo lịch riêng.

**Dấu hiệu thực tế:**
- Các lần phát hành thường hoàn thành trong cửa sổ chấp nhận được.
- CI/CD đáng tin cậy; thời gian build và test có thể tối ưu thêm.
- Có thể dùng feature flag, triển khai theo đợt, canary hoặc blue-green để giảm rủi ro.
- Một thay đổi ở mô-đun A không thường xuyên bị chặn bởi mô-đun B.

**Cách làm:** Đo thời gian từ commit đến production, tỷ lệ deployment thất bại, thời gian khôi phục và các nguyên nhân thực tế. Đầu tư vào test pyramid hợp lý, pipeline song song, kiểm soát thay đổi và khả năng rollback trước khi chọn kiến trúc phân tán.

### 2.4. Yêu cầu hiệu năng và khả năng mở rộng vẫn xử lý được trong đơn thể

Không phải hệ thống có nhiều người dùng đều cần Microservices. Đơn thể có thể chạy nhiều instance phía sau load balancer, mở rộng theo chiều dọc hoặc ngang nếu trạng thái phiên và tài nguyên dùng chung được xử lý đúng.

**Dấu hiệu thực tế:**
- Các chỉ số độ trễ, thông lượng và độ sẵn sàng vẫn đạt mục tiêu.
- Tải chủ yếu có thể xử lý bằng tối ưu truy vấn, chỉ mục, cache, connection pool hoặc hàng đợi.
- Các phần nghiệp vụ chưa có nhu cầu scale chênh lệch đến mức làm chi phí scale toàn ứng dụng trở nên bất hợp lý.
- Điểm nghẽn thực tế nằm ở cơ sở dữ liệu hoặc phụ thuộc ngoài; tách tiến trình không tự giải quyết điểm nghẽn đó.

**Cách làm:** Đo P95/P99 latency, CPU, RAM, I/O, lock contention, hàng chờ và thời gian truy vấn ở tải thực tế. Nếu dùng Spring Boot, có thể scale nhiều instance ứng dụng stateless, đặt session ngoài tiến trình nếu cần, quan sát connection pool và giới hạn tài nguyên. Xác định nguyên nhân từ profiling và load test trước khi tách dịch vụ.

**Lưu ý:** Cùng scale toàn bộ đơn thể có thể lãng phí tài nguyên khi chỉ một miền rất nặng. Đây là tín hiệu xem xét tách, nhưng cần so chi phí scale dư với chi phí vận hành dịch vụ riêng.

### 2.5. Nghiệp vụ cần giao dịch dữ liệu nhất quán và phối hợp chặt

Nếu nhiều bước phải bảo đảm bất biến nghiệp vụ đồng thời, lưu cùng một cơ sở dữ liệu với giao dịch cục bộ có thể đơn giản và dễ kiểm chứng hơn.

Ví dụ trong hệ thống bán hàng: tạo đơn và giữ tồn kho phải tuân thủ quy tắc “không bán vượt tồn”. Khi cùng nằm trong một ranh giới giao dịch được thiết kế đúng, lỗi có thể rollback một cách nhất quán.

Khi tách thành nhiều dịch vụ, cùng luồng có thể phải dùng thông điệp, idempotency, outbox, bù trừ (compensation), retry và eventual consistency. Những cơ chế này hữu ích khi có nhu cầu phân tán thật sự nhưng làm tăng số trạng thái trung gian cần xử lý.

**Cách làm:** Xác định bất biến nghiệp vụ, transaction boundary và yêu cầu nhất quán từng luồng. Giữ giao dịch cục bộ ở nơi các bước còn gắn bó; không cố nhét lời gọi HTTP hoặc thanh toán ngoài vào một transaction cơ sở dữ liệu kéo dài.

### 2.6. Chi phí vận hành và độ phức tạp phân tán chưa được biện minh

Trong đơn thể, nhiều lời gọi là lời gọi hàm nội bộ; trong Microservices, chúng trở thành trao đổi qua mạng có latency, timeout, retry và lỗi từng phần.

**Điều kiện thuận lợi để giữ đơn thể:**
- Sản phẩm chưa cần nhiều vùng triển khai, nhiều cấp cô lập lỗi hoặc các cơ chế vận hành phức tạp.
- Chưa có đội ngũ trực vận hành đủ năng lực theo dõi nhiều dịch vụ 24/7.
- Ngân sách hạ tầng, observability, bảo mật và CI/CD cần tập trung vào tính năng sản phẩm.
- Mục tiêu chất lượng có thể đạt bằng logging, metrics, tracing phù hợp và triển khai nhiều instance của cùng ứng dụng.

Một dịch vụ riêng chỉ có giá trị khi lợi ích về quyền tự chủ, scale hoặc fault isolation lớn hơn chi phí của mạng, hợp đồng, dữ liệu, vận hành và sự cố liên dịch vụ.

### 2.7. Các mô-đun thay đổi cùng nhau và chưa có tính tự chủ thật

Nếu các thay đổi quan trọng hầu như luôn xuyên qua nhiều mô-đun, mỗi mô-đun phụ thuộc trực tiếp vào mô hình dữ liệu của mô-đun khác và phải phát hành cùng thời điểm, việc tách vật lý dễ tạo ra **distributed monolith**.

**Cách làm:** Trước khi tách triển khai, tách phụ thuộc trong mã: mô-đun khác chỉ dùng public API/port; hạn chế truy cập bảng hay entity của nhau; xác định quyền sở hữu dữ liệu và hợp đồng rõ ràng. Quan sát tần suất thay đổi chung để đánh giá ranh giới hợp lý.

## 3. Ma trận dấu hiệu và bằng chứng cần đo

Các điều kiện là **tín hiệu để cân nhắc**, không phải ngưỡng số cứng áp dụng cho mọi tổ chức.

| Khía cạnh | Tín hiệu tiếp tục giữ đơn thể | Bằng chứng nên thu thập |
| --- | --- | --- |
| Sản phẩm | Miền nghiệp vụ chưa ổn định, cần học và chỉnh liên tục | Lịch sử thay đổi yêu cầu, số lần đổi ranh giới |
| Nhóm phát triển | Phối hợp tốt; ít phụ thuộc chờ đợi giữa các nhóm | Lead time, thời gian review và thời gian chờ |
| Phát hành | Một pipeline đủ nhanh, an toàn và đều đặn | Deployment frequency, change failure rate, rollback time |
| Hiệu năng | SLO đạt được với tối ưu và scale hiện có | P95/P99, throughput, CPU/RAM, DB metrics, load test |
| Dữ liệu | Nhiều bất biến cần transaction cục bộ | Sơ đồ transaction, invariant, failure cases |
| Vận hành | Số thành phần và chi phí đang kiểm soát được | Số lần sự cố, MTTR, thời gian trực, chi phí hạ tầng |
| Ranh giới | Các miền vẫn thường thay đổi và phát hành cùng nhau | Change coupling, số thay đổi chạm nhiều mô-đun |
| Bảo mật/tuân thủ | Một ranh giới triển khai và chính sách chung đáp ứng yêu cầu | Threat model, phân quyền, kiểm toán, phạm vi dữ liệu |

Ví dụ: “build mất 18 phút” chưa tự động là lý do tách dịch vụ; cần biết 18 phút có làm trễ mục tiêu phát hành hay không, các bước nào tốn thời gian và có thể chạy song song hay tối ưu được không.

## 4. Giữ đơn thể nhưng phải có kiến trúc bên trong tốt

Quyết định giữ đơn thể **không có nghĩa** giữ mã nguồn hỗn tạp. Một modular monolith nên có những ranh giới đủ rõ để có thể thay đổi từng miền mà không tác động tùy tiện đến miền khác.

### 4.1. Tổ chức theo năng lực nghiệp vụ

Ví dụ cấu trúc một ứng dụng Spring Boot:

~~~text
com.example.shop
  catalog/
    api/
    application/
    domain/
    infrastructure/
  ordering/
    api/
    application/
    domain/
    infrastructure/
  inventory/
    api/
    application/
    domain/
    infrastructure/
  shared/
    observability/
    security/
~~~

Ý nghĩa: từng miền có logic, dữ liệu và API được định nghĩa rõ. Thư mục shared chỉ chứa chức năng hạ tầng dùng chung có chủ đích; không biến nó thành nơi chứa mọi entity, quy tắc hoặc tiện ích nghiệp vụ.

### 4.2. Giao tiếp qua hợp đồng nội bộ

Mô-đun đặt hàng cần giữ hàng nhưng không nên đọc trực tiếp repository hoặc sửa entity nội bộ của mô-đun tồn kho. Nó gọi một hợp đồng nghiệp vụ do phía tồn kho công bố.

~~~java
// Public contract của mô-đun inventory
public interface InventoryReservation {
    ReservationResult reserve(String productId, int quantity, String orderId);
}

// Mô-đun ordering chỉ phụ thuộc vào hợp đồng.
public class PlaceOrderUseCase {
    private final InventoryReservation inventory;

    public PlaceOrderUseCase(InventoryReservation inventory) {
        this.inventory = inventory;
    }

    public void place(String orderId, String productId, int quantity) {
        ReservationResult result =
            inventory.reserve(productId, quantity, orderId);
        if (!result.success()) {
            throw new IllegalStateException("Insufficient inventory");
        }
        // Tiếp tục cập nhật trạng thái đơn hàng trong luồng ứng dụng.
    }
}
~~~

Đoạn mã minh họa **ranh giới phụ thuộc**, không phải một triển khai đầy đủ về transaction, concurrency hay idempotency. Trong hệ thống thật, cần thiết kế transaction phù hợp, kiểm soát cập nhật tồn kho đồng thời và xử lý mọi đường thất bại.

### 4.3. Thiết lập quy tắc giúp giữ ranh giới

- Mỗi mô-đun công khai API/port tối thiểu; lớp bên ngoài không dùng trực tiếp entity, repository hoặc bảng nội bộ nếu chưa có hợp đồng.
- Quy tắc nghiệp vụ nằm gần miền sở hữu; tránh vòng phụ thuộc giữa các mô-đun.
- Kiểm thử đơn vị cho logic, kiểm thử tích hợp cho database/transaction và kiểm thử hợp đồng nội bộ tại ranh giới quan trọng.
- Có thể dùng architecture tests, ví dụ kiểm tra phụ thuộc package bằng ArchUnit hoặc cấu trúc mô-đun bằng Spring Modulith nếu phù hợp với dự án.
- Ghi rõ module owner, interface, dữ liệu sở hữu, sự kiện phát ra và luồng sử dụng.
- Duy trì logging theo correlation ID, metrics và tracing cho luồng chính ngay cả khi chỉ có một ứng dụng.

Các biện pháp này giảm change coupling ngay hôm nay và tạo khả năng tách triển khai nếu nhu cầu xuất hiện sau này.

## 5. Ví dụ quyết định: nền tảng bán hàng đang tăng trưởng

**Bối cảnh giả định:** Một công ty có 8 kỹ sư trong hai nhóm, một ứng dụng Spring Boot phục vụ giỏ hàng, đơn hàng, kho và quản trị. Ứng dụng được triển khai 3 lần mỗi tuần, rollback dễ, SLO hiện tại đạt. Đơn hàng và kho cần một số thao tác dữ liệu nhất quán. Nhóm đang thay đổi chính sách khuyến mại và quy trình đặt hàng liên tục.

**Đánh giá:**

| Câu hỏi | Nhận định từ bối cảnh | Hành động hợp lý |
| --- | --- | --- |
| Có cần mỗi miền phát hành theo lịch riêng không? | Chưa; các nhóm thống nhất được một lịch | Giữ một pipeline, cải thiện tốc độ test |
| Có nút thắt hiệu năng vượt khả năng scale hiện tại không? | Chưa có bằng chứng | Đo P95/P99 và truy vấn DB trước khi thay đổi kiến trúc |
| Ranh giới miền đã ổn định chưa? | Chưa; checkout và khuyến mại thay đổi thường xuyên | Giữ quyền refactor ranh giới trong đơn thể |
| Phân tán dữ liệu có tạo thêm rủi ro không? | Có, với quy tắc giữ tồn kho | Ưu tiên transaction cục bộ; làm rõ invariant |
| Tính tự chủ vận hành đem lại lợi ích rõ ràng chưa? | Chưa | Tăng tính độc lập qua mô-đun trước |

**Quyết định đề xuất trong tình huống này:** Tiếp tục dùng modular monolith. Chia ranh giới catalog, ordering, inventory; hạn chế truy cập dữ liệu chéo; tối ưu CI/CD; load test trên luồng checkout; thiết lập metrics về thời gian phát hành và sự cố.

**Khi nào cần xem lại:** Sau một thời gian quan sát, nếu nhóm catalog bắt buộc phải phát hành độc lập mỗi ngày và thay đổi đó thường xuyên bị chặn bởi release chung; hoặc nếu workload catalog tăng mạnh mà scale toàn ứng dụng gây chi phí không phù hợp, hãy đánh giá tách catalog thành dịch vụ riêng. Quyết định vẫn cần dữ liệu đo và một ranh giới sở hữu rõ.

## 6. Quy trình ra quyết định có thể lặp lại

### Bước 1 — Nêu vấn đề bằng tác động đo được

Tránh kết luận kiểu “hệ thống lớn nên phải tách” hoặc “Microservices hiện đại hơn”. Thay bằng phát biểu kiểm chứng được, chẳng hạn:

- “Một thay đổi nhỏ ở catalog thường đợi 4 ngày mới được phát hành vì phụ thuộc kiểm thử toàn hệ thống.”
- “Ở tải cao, P99 của luồng checkout vượt SLO mặc dù đã tối ưu truy vấn và tăng tài nguyên hợp lý.”
- “Sự cố ở xử lý báo cáo nền làm giảm độ sẵn sàng của API đặt hàng.”

### Bước 2 — Tìm nguyên nhân gốc

Phân biệt vấn đề do thiết kế bên trong, database, quy trình phát hành, thiếu kiểm thử, thiếu quan sát, hay thật sự do một đơn vị triển khai chung. Đừng biến mọi vấn đề hiệu năng hoặc tổ chức thành bài toán chia dịch vụ.

### Bước 3 — Thử giải pháp có chi phí thấp hơn

Các giải pháp có thể gồm:
- Refactor thành mô-đun với API nội bộ rõ ràng.
- Tách tác vụ nền sang worker/job trong cùng hệ thống khi thích hợp.
- Tối ưu chỉ mục, cache, batch processing, pagination, queue hoặc connection pool.
- Scale nhiều instance, quản lý session đúng cách, bổ sung timeout và bulkhead cho phụ thuộc ngoài.
- Chạy test song song, dùng feature flag, cải thiện deployment/rollback và ownership.

“Có chi phí thấp hơn” phải được xác minh trong bối cảnh thực tế; đôi khi tách một dịch vụ thật sự là lựa chọn kinh tế hơn.

### Bước 4 — So sánh lợi ích với chi phí phân tán

Khi đề xuất Microservices, cần trả lời: dịch vụ nào được tách, ai sở hữu, dữ liệu nào thuộc về nó, giao tiếp đồng bộ/bất đồng bộ ra sao, giao dịch và lỗi từng phần xử lý thế nào, ai trực vận hành, mức độ tăng chi phí bao nhiêu và cách chứng minh lợi ích sau tách.

Đánh giá cả chi phí di chuyển dữ liệu, tương thích hợp đồng, vận hành song song, migration và rollback. Không chỉ so số dòng code hoặc số module.

### Bước 5 — Ghi quyết định và đặt thời điểm xem lại

Lưu một Architecture Decision Record (ADR) ngắn gồm bối cảnh, phương án, tiêu chí đo, lý do chọn, rủi ro được chấp nhận, người chịu trách nhiệm và điều kiện xét lại. Quyết định kiến trúc là giả thuyết có bằng chứng, có thể thay đổi theo nhu cầu.

**Ví dụ ADR rút gọn:**

~~~text
Decision: Giữ modular monolith cho ordering + inventory.
Context: Hai miền cần transaction nhất quán; chưa có release độc lập.
Evidence: SLO đạt; release cadence đáp ứng nhu cầu; team ownership rõ.
Trade-off: Hai miền vẫn dùng chung deployment và một phần tài nguyên.
Actions: Giới hạn API nội bộ, test transaction, bổ sung metrics.
Revisit when: Release coupling hoặc resource contention đo được
             trở thành cản trở đáng kể.
~~~

## 7. Những tín hiệu đủ mạnh để xem xét chuyển hướng

Giữ đơn thể là quyết định có điều kiện, không phải lời hứa giữ mãi. Cân nhắc đánh giá tách dịch vụ khi **nhiều tín hiệu đã được xác thực**:

1. **Độc lập phát hành trở thành yêu cầu thực:** các miền khác nhau có nhóm sở hữu, nhịp thay đổi và rủi ro triển khai rõ rệt; release chung gây chậm trễ lặp lại.
2. **Khác biệt lớn về tải hoặc tài nguyên:** một miền tiêu thụ CPU/RAM/IO hoặc cần cơ chế scale khác biệt khiến scale nguyên ứng dụng quá tốn kém.
3. **Cần cô lập lỗi mạnh hơn:** lỗi ở một chức năng liên tục ảnh hưởng chức năng trọng yếu, sau khi đã áp dụng timeout, giới hạn tài nguyên và cô lập mức tiến trình phù hợp.
4. **Ranh giới nghiệp vụ và dữ liệu đã vững:** hợp đồng giữa các miền tương đối ổn định, ownership rõ, không cần liên tục truy vấn và cập nhật chéo dữ liệu.
5. **Năng lực vận hành đã sẵn sàng:** có CI/CD riêng, observability, alerting, security, incident response, chiến lược versioning và dữ liệu cho nhiều dịch vụ.
6. **Lợi ích định lượng vượt chi phí:** kế hoạch có tiêu chí đo, thử nghiệm giới hạn phạm vi, đường quay lại và chủ sở hữu kết quả.

Không có một ngưỡng “bao nhiêu người dùng, bao nhiêu bảng, bao nhiêu kỹ sư” áp dụng chung. Số liệu phải đi cùng đặc điểm tải, chi phí và yêu cầu của chính tổ chức.

## 8. Những sai lầm thường gặp khi giữ hoặc bỏ đơn thể

**“Đơn thể thì không thể scale.”** Sai. Một đơn thể stateless có thể scale ngang nhiều instance. Giới hạn thực tế phụ thuộc trạng thái, database, điểm nghẽn, chi phí và yêu cầu cô lập tài nguyên.

**“Chuyển sang Microservices sẽ tự cải thiện code.”** Sai. Nếu ranh giới nghiệp vụ chưa rõ, phân tán có thể biến phụ thuộc trong mã thành chuỗi gọi mạng và giao dịch khó xử lý hơn.

**“Đơn thể có nghĩa các module được truy cập bảng của nhau tự do.”** Sai. Cần quyền sở hữu logic và dữ liệu rõ ràng ngay trong modular monolith; cùng cơ sở dữ liệu không đồng nghĩa không có ranh giới.

**“Một sự cố trong đơn thể buộc phải bỏ kiến trúc.”** Chưa đủ. Cần phân tích nguyên nhân: OOM, truy vấn chậm, deadlock, phụ thuộc ngoài, cấu hình deployment, queue quá tải. Một số vấn đề có thể giải quyết mà không tách dịch vụ.

**“Phải chờ mã nguồn hỗn loạn rồi mới tách.”** Sai. Hãy đầu tư ranh giới và observability sớm; dùng dữ liệu để quyết định khi nào ranh giới phải trở thành dịch vụ triển khai độc lập.

**“Dùng chung database nên sẽ luôn nhất quán.”** Chưa chắc. Transaction boundary, concurrency, isolation level, xử lý side effects ngoài DB và thiết kế bất biến vẫn phải được kiểm chứng.

## 9. Checklist áp dụng cho một hệ thống thực tế

Trước khi phê duyệt việc giữ đơn thể trong giai đoạn tiếp theo, nhóm nên trả lời:

- [ ] Năng lực nghiệp vụ hiện tại có thể được chia thành các mô-đun và API nội bộ rõ ràng không?
- [ ] Một pipeline triển khai đáp ứng nhịp phát hành và yêu cầu rollback không?
- [ ] SLO hiệu năng/độ sẵn sàng được đo và vẫn đạt, hoặc đã có kế hoạch tối ưu cụ thể không?
- [ ] Những nút thắt đã được phân tích bằng profiling, load test và quan sát production chưa?
- [ ] Các giao dịch quan trọng và quy tắc nhất quán dữ liệu đã được xác định chưa?
- [ ] Nhóm có thể phối hợp và sở hữu mã mà không thường xuyên chờ lịch phát hành của nhóm khác không?
- [ ] Chi phí build, test, scale, vận hành và khắc phục sự cố vẫn nằm trong giới hạn chấp nhận được không?
- [ ] Các phụ thuộc giữa mô-đun được kiểm soát và có kiểm thử ranh giới không?
- [ ] Đã ghi nhận lý do giữ đơn thể, rủi ro được chấp nhận, tiêu chí và thời điểm đánh giá lại chưa?

Nếu nhiều câu chưa trả lời được, việc cần làm đầu tiên thường là **thu thập bằng chứng và làm rõ ranh giới**, thay vì vội quyết định chuyển hay giữ theo cảm tính.

## 10. Kết luận

Nên tiếp tục giữ kiến trúc đơn thể khi **một đơn vị triển khai vẫn phục vụ tốt nhu cầu sản phẩm và đội ngũ**, trong khi độ phức tạp phân tán của Microservices chưa mang lại lợi ích tương xứng. Những dấu hiệu quan trọng gồm ranh giới nghiệp vụ còn biến động, đội ngũ phối hợp hiệu quả, phát hành chung đáp ứng mục tiêu, tải và SLO vẫn xử lý được, nhiều giao dịch cần nhất quán cục bộ, và chi phí vận hành nhiều dịch vụ chưa hợp lý.

Lựa chọn thực dụng thường là **modular monolith có ranh giới rõ, vận hành có đo lường và tiêu chí xét lại cụ thể**. Kiến trúc tốt là kiến trúc giải quyết vấn đề hiện tại và giữ được quyền thay đổi khi bằng chứng mới xuất hiện.
