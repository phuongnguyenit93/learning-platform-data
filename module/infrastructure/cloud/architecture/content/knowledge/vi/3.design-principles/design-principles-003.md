# Giảm phụ thuộc chặt và tăng tính gắn kết trong từng thành phần

## 1. Vì sao đây là nguyên lý thiết kế quan trọng?

Khi thiết kế kiến trúc ứng dụng trên đám mây, kiến trúc sư không chỉ lựa chọn mạng, compute, cơ sở dữ liệu hay cách triển khai. Họ còn phải quyết định **chức năng nào thuộc về thành phần nào** và **các thành phần được phép phụ thuộc vào nhau ra sao**. Hai quyết định này ảnh hưởng trực tiếp đến tốc độ thay đổi phần mềm, khả năng mở rộng, phạm vi ảnh hưởng của sự cố, bảo mật, chi phí và độ phức tạp vận hành.

Hai khái niệm nền tảng:

- **Coupling (mức độ phụ thuộc):** mức độ một thành phần phải biết về, dựa vào hoặc thay đổi cùng thành phần khác để hoàn thành công việc. **Tight coupling** là phụ thuộc chặt; **loose coupling** là phụ thuộc lỏng.
- **Cohesion (tính gắn kết):** mức độ các trách nhiệm, dữ liệu và hành vi bên trong một thành phần cùng phục vụ một mục tiêu rõ ràng. **High cohesion** là gắn kết cao.

Mục tiêu thực tế là **gắn kết cao bên trong ranh giới, phụ thuộc vừa đủ và có chủ đích giữa các ranh giới**. Không thể và cũng không cần loại bỏ mọi phụ thuộc: dịch vụ đặt chỗ vẫn cần biết liệu có chỗ trống, dịch vụ thanh toán vẫn phải kết nối cổng thanh toán. Vấn đề là lựa chọn quan hệ phụ thuộc nào ổn định, dễ hiểu, có thể kiểm chứng và không khiến thay đổi nhỏ lan rộng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt coupling với cohesion và giải thích vì sao chúng tác động đến kiến trúc cloud.
2. Nhận diện các dạng phụ thuộc chặt: phụ thuộc mã nguồn, schema dữ liệu, thời điểm, triển khai, tài nguyên và vận hành.
3. Xác định ranh giới thành phần dựa trên năng lực nghiệp vụ, dữ liệu sở hữu và các bất biến cần bảo vệ.
4. Áp dụng hợp đồng API, sự kiện, tính đóng gói, dependency inversion và cơ chế xử lý lỗi để giảm phụ thuộc không cần thiết.
5. Đánh giá đánh đổi giữa modular monolith, microservices, đồng bộ và bất đồng bộ theo các góc nhìn Well-Architected.

## 2. Phân biệt coupling và cohesion bằng ví dụ

Hãy xem một nền tảng cho thuê chỗ ở có các nghiệp vụ: tìm kiếm phòng, xác nhận đặt phòng, tính giá, thanh toán và thông báo.

**Thiết kế có mức phụ thuộc chặt:**

- Một thành phần tên **RentalManager** xử lý tìm kiếm, sửa giá, đặt phòng, gửi email, tính thuế và xuất báo cáo.
- Nhiều thành phần cùng sửa trực tiếp các bảng **rooms**, **bookings** và **payments**.
- Khi gửi email lỗi, thao tác xác nhận đặt phòng bị trả lỗi theo; khi thay đổi cách tính giá, cần phát hành lại nhiều dịch vụ.

**Thiết kế có ranh giới rõ hơn:**

- **Catalog/Search** phụ trách thông tin hiển thị và tìm kiếm phòng.
- **Pricing** sở hữu chính sách định giá và cung cấp báo giá theo hợp đồng xác định.
- **Booking/Inventory** sở hữu quy tắc giữ chỗ và xác nhận không đặt trùng.
- **Payment** chịu trách nhiệm quy trình giao dịch thanh toán và tích hợp nhà cung cấp.
- **Notification** nhận sự kiện nghiệp vụ để gửi thông báo, không quyết định đặt chỗ có hợp lệ hay không.

Cách phân chia này chỉ là **một phương án ban đầu**. Nếu nhóm nhỏ, phạm vi nghiệp vụ đơn giản và thay đổi liên tục, có thể giữ các thành phần dưới dạng module trong một ứng dụng triển khai chung. Ranh giới logic vẫn có giá trị trước khi cân nhắc tách thành dịch vụ phân tán.

| Tiêu chí | Gắn kết thấp, phụ thuộc chặt | Gắn kết cao, phụ thuộc có kiểm soát |
|---|---|---|
| Trách nhiệm | Một thành phần làm nhiều việc không liên quan | Mỗi thành phần có lý do tồn tại và thay đổi rõ ràng |
| Dữ liệu | Thành phần khác tự ý đọc/sửa bảng nội bộ | Chủ sở hữu kiểm soát cách đọc/sửa dữ liệu của mình |
| Thay đổi | Sửa một quy tắc làm nhiều nơi phải đổi mã | Phần lớn thay đổi nằm trong ranh giới liên quan |
| Triển khai | Các nhóm phải đồng thời phát hành để tránh lỗi tương thích | Có khả năng tiến hóa hợp đồng và phát hành độc lập khi cần |
| Sự cố | Lỗi hệ thống phụ làm hỏng luồng nghiệp vụ chính | Có giới hạn thời gian chờ, cách suy giảm và phục hồi phù hợp |
| Kiểm thử | Bài kiểm thử luôn cần bật toàn bộ hệ thống | Có thể kiểm thử từng module và hợp đồng tích hợp rõ ràng |

**Cohesion không đồng nghĩa “mọi class đều nhỏ”** và coupling không chỉ đếm số lần gọi API. Một module lớn nhưng tập trung vào một năng lực nghiệp vụ có thể gắn kết tốt hơn hàng chục dịch vụ nhỏ đòi hỏi nhau qua nhiều cuộc gọi đồng bộ.

## 3. Nhận diện các dạng phụ thuộc chặt

Một ứng dụng cloud có thể phụ thuộc ở nhiều tầng. Phân biệt chúng giúp chọn đúng biện pháp cải thiện.

| Dạng phụ thuộc | Biểu hiện | Hệ quả khi thay đổi hoặc xảy ra lỗi |
|---|---|---|
| **Phụ thuộc hiện thực** | A truy cập class nội bộ, cấu trúc object hoặc cấu hình private của B | Thay đổi chi tiết B khiến A phải sửa |
| **Phụ thuộc hợp đồng** | A dựa vào API/định dạng sự kiện của B | Là bình thường nếu hợp đồng rõ, ổn định, có kiểm tra tương thích |
| **Phụ thuộc dữ liệu** | Hai dịch vụ sửa cùng bảng, phụ thuộc trigger/schema của nhau | Migration khó, cạnh tranh quyền sở hữu và lỗi toàn vẹn dữ liệu |
| **Phụ thuộc thời điểm** | A chỉ hoàn thành khi B, C, D đều phản hồi tức thì | Độ trễ cộng dồn; một lỗi phụ thuộc có thể làm hỏng giao dịch |
| **Phụ thuộc trình tự** | Thành phần phải khởi động, chạy job hoặc deploy theo thứ tự ngầm định | Khó tự động hóa, khó phục hồi sau sự cố |
| **Phụ thuộc triển khai** | Một thay đổi yêu cầu nhiều dịch vụ phát hành cùng lúc | Tăng rủi ro release và thời gian phối hợp |
| **Phụ thuộc hạ tầng/tài nguyên** | Nhiều nghiệp vụ dùng chung DB pool, queue, cluster hoặc quota | Tranh chấp tài nguyên; một tải đột biến ảnh hưởng thành phần khác |
| **Phụ thuộc nền tảng** | Logic nghiệp vụ dùng trực tiếp SDK, định dạng và tính năng đặc thù nhà cung cấp | Khó thử nghiệm, khó di chuyển hoặc thay đổi cách triển khai |
| **Phụ thuộc vận hành** | Không có chủ sở hữu; cùng dùng log, cảnh báo và runbook khó tách | Khó xác định sự cố, tăng gánh nặng hỗ trợ liên nhóm |

Không phải dạng phụ thuộc nào cũng xấu. **Phụ thuộc vào hợp đồng công khai và ổn định** thường cần thiết. Ngược lại, cố gắng che giấu hoàn toàn mọi SDK cloud cũng có thể gây thêm lớp trừu tượng phức tạp. Kiến trúc sư phải đánh giá mức phụ thuộc theo tác động thực tế của việc thay đổi và sự cố.

### Câu hỏi để phát hiện coupling cao

- Nếu đổi cột dữ liệu nội bộ của Booking, những thành phần nào phải sửa?
- Nếu Pricing tạm thời không phản hồi, Booking sẽ chờ bao lâu và kết thúc như thế nào?
- Nếu một deployment thất bại, có bắt buộc rollback các deployment khác?
- Nếu tăng quy mô của Search lên gấp nhiều lần, Booking có bị tranh chấp tài nguyên hay giới hạn kết nối không?
- Nếu cần thay nhà cung cấp gửi email, mã nguồn nghiệp vụ đặt chỗ có phải đổi không?
- Nếu một tính năng mới cần sửa đồng thời sáu dịch vụ, ranh giới hiện tại có phản ánh đúng nghiệp vụ không?

Trả lời các câu hỏi này qua luồng thay đổi thực tế, sơ đồ phụ thuộc, mã nguồn, số liệu triển khai và sự cố, thay vì chỉ nhìn sơ đồ tổng quan.

## 4. Tăng cohesion bằng ranh giới nghiệp vụ rõ ràng

### 4.1. Gom những hành vi cùng bảo vệ một bất biến

**Bất biến nghiệp vụ (business invariant)** là điều bắt buộc vẫn đúng sau mọi thao tác hợp lệ. Ví dụ: **một chỗ ở không được xác nhận cho hai khách trong cùng khoảng thời gian nếu chính sách không cho phép đặt trùng**.

Những hành vi cùng bảo vệ bất biến đặt chỗ — kiểm tra xung đột, giữ chỗ, xác nhận, hủy hoặc hết hạn giữ chỗ — thường có lý do nằm gần nhau trong một ranh giới nhất quán (**Booking/Inventory**). Nếu chia quá nhỏ và yêu cầu nhiều dịch vụ độc lập phối hợp liên tục để kiểm tra bất biến, ta chuyển một quy tắc cần tính nguyên tử thành bài toán giao dịch phân tán khó hơn.

Với một hệ dữ liệu quan hệ, các thao tác ảnh hưởng bất biến có thể cần một **giao dịch cơ sở dữ liệu** cùng cơ chế khóa, constraint hoặc cách điều khiển đồng thời phù hợp. Gọi hai lần API theo kiểu “kiểm tra trước rồi ghi sau” không tự bảo đảm tránh đặt trùng khi có nhiều yêu cầu cạnh tranh.

### 4.2. Gom theo lý do thay đổi

Một thành phần có cohesion cao khi những thay đổi thường xuất phát từ **cùng một nhóm quy tắc và cùng người chịu trách nhiệm nghiệp vụ**. Ví dụ:

| Thay đổi | Ranh giới ưu tiên xem xét | Không nên lan sang |
|---|---|---|
| Đổi chính sách giá cuối tuần | Pricing | Notification, Search adapter, nền tảng triển khai |
| Đổi thời hạn giữ chỗ | Booking/Inventory | Email provider, báo cáo |
| Đổi mẫu thư xác nhận | Notification | Quy tắc kiểm tra chỗ trống |
| Đổi cấu hình dự phòng DB | Hạ tầng dữ liệu của component liên quan | Logic nghiệp vụ không phụ thuộc chi tiết hạ tầng |
| Đổi cơ chế xác thực người dùng | IAM/gateway và integration điểm vào | Các quy tắc nghiệp vụ không liên quan; vẫn cần kiểm tra quyền ở nơi thực hiện hành động |

Khi một chính sách nghiệp vụ nằm rải rác trong nhiều repository và mỗi lần đổi đều cần nhiều đội phối hợp, đó có thể là dấu hiệu ranh giới chưa tốt.

### 4.3. Phân biệt các cấp độ thành phần

- **Hàm/class:** tập trung vào một trách nhiệm gần gũi; che giấu chi tiết bên trong.
- **Module/package:** nhóm các đối tượng cùng một năng lực nghiệp vụ, có API nội bộ rõ.
- **Dịch vụ:** có ranh giới vận hành và hợp đồng giao tiếp; có thể triển khai, scale hoặc phục hồi riêng nếu thực sự tách biệt.
- **Nền tảng dùng chung:** cung cấp khả năng kỹ thuật lặp lại như thu thập log, quản lý secrets, CI/CD; tránh biến thành nơi chứa logic nghiệp vụ của mọi đội.

Không nên dùng việc chia nhỏ package/class như bằng chứng đã có ranh giới dịch vụ tốt. Đổi lại, cũng không nên tạo một microservice cho mỗi bảng dữ liệu hoặc mỗi động từ trong API.

## 5. Những kỹ thuật giảm coupling trong thiết kế phần mềm

### 5.1. Đóng gói thông tin và hợp đồng ổn định

**Information hiding** yêu cầu thành phần chỉ công bố những gì bên ngoài thực sự cần biết. Hợp đồng API có ý nghĩa nghiệp vụ; cấu trúc bảng, thuật toán và nhà cung cấp lưu trữ là chi tiết hiện thực.

Ví dụ, một API Booking cung cấp thao tác **CreateReservation** và **GetReservationStatus** thay vì cho phép dịch vụ khác sửa trực tiếp bảng bookings. Booking có quyền thay đổi schema hoặc cách xử lý đồng thời mà không buộc mọi consumer sửa mã, miễn vẫn giữ hợp đồng tương thích.

Hợp đồng tốt nên quy định rõ:

1. Ý nghĩa nghiệp vụ, quyền gọi, định dạng dữ liệu và version.
2. Điều kiện thành công, lỗi có thể xử lý, hành vi khi request trùng lặp.
3. Giới hạn thời gian, số lần gọi, phân trang và cơ chế backpressure khi cần.
4. Điều gì được bảo đảm nhất quán ngay, điều gì chỉ nhất quán sau một khoảng thời gian.
5. Chính sách tương thích ngược và thời gian loại bỏ trường cũ.

Đừng nhầm **ít field** với hợp đồng tốt: nếu thiếu dữ liệu cần thiết, client sẽ phải gọi nhiều lần để ghép đủ thông tin, tạo ra coupling thời điểm và tăng độ trễ.

### 5.2. Dependency inversion ở lớp mã nguồn

Logic nghiệp vụ nên phụ thuộc vào **giao diện năng lực** do ranh giới của nó định nghĩa, thay vì phụ thuộc trực tiếp vào SDK cloud, DB driver hoặc thư viện gửi email.

~~~java
// Domain/Application layer: mô tả nhu cầu thay vì cách lưu trữ.
public interface BookingRepository {
    Booking findById(BookingId id);
    void save(Booking booking);
}

public interface BookingEventPublisher {
    void publish(BookingConfirmed event);
}

public final class BookingApplicationService {
    private final BookingRepository repository;
    private final BookingEventPublisher publisher;

    public BookingApplicationService(
            BookingRepository repository,
            BookingEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    public void confirm(BookingId id) {
        Booking booking = repository.findById(id);
        booking.confirm();             // Kiểm tra quy tắc của aggregate.
        repository.save(booking);
        publisher.publish(new BookingConfirmed(id.value()));
    }
}
~~~

Đây là **ví dụ minh họa cách phụ thuộc vào interface**, chưa phải mã production bảo đảm toàn vẹn giao dịch. Việc lưu Booking và phát sự kiện như hai thao tác riêng có **khoảng trống mất sự kiện** nếu tiến trình chết sau khi commit DB nhưng trước khi publish. Trong kiến trúc thực tế, cần xử lý khoảng trống này, chẳng hạn **transactional outbox** (ghi sự kiện vào outbox trong cùng transaction và có publisher riêng chuyển đi), hoặc một cơ chế tương đương có bằng chứng bảo đảm.

Adapter có thể triển khai BookingRepository bằng một managed relational database; adapter khác có thể triển khai publisher bằng message broker. Việc thay adapter nên chủ yếu ảnh hưởng lớp hạ tầng. Tuy nhiên, transaction, độ nhất quán và khả năng của storage vẫn là các **ràng buộc kiến trúc** cần thể hiện rõ, không thể xóa bằng interface.

### 5.3. Tách dependency bằng sự kiện khi nghiệp vụ cho phép

Thay vì Booking gọi tuần tự email, SMS, loyalty và analytics trong cùng một request, Booking có thể ghi nhận sự kiện **BookingConfirmed**. Các thành phần quan tâm tự đăng ký xử lý:

~~~mermaid
flowchart LR
    Client["Web / Mobile"] --> Booking["Booking: xác nhận đặt chỗ"]
    Booking --> Database[("Booking DB + Outbox")]
    Database --> Relay["Outbox relay"]
    Relay --> Bus[["Event bus / Queue"]]
    Bus --> Notify["Notification"]
    Bus --> Loyalty["Loyalty"]
    Bus --> Analytics["Analytics"]
~~~

Nhờ vậy, việc gửi thông báo hoặc cập nhật analytics chậm không nhất thiết chặn trả kết quả đặt chỗ. Nhưng tính bất đồng bộ tạo ra đánh đổi:

- **Thứ tự và trùng lặp:** queue có thể giao lại thông điệp; consumer cần idempotent và xử lý được trùng lặp.
- **Eventual consistency:** hệ thống khác có thể cập nhật muộn; UI và quy trình nghiệp vụ phải phản ánh tình trạng này.
- **Vận hành:** cần giám sát backlog, độ tuổi message, retry, dead-letter queue, schema tương thích và khả năng phát lại.
- **Bảo mật:** event chỉ nên chứa dữ liệu cần thiết; quyền publish/subscribe phải được kiểm soát.

Không dùng sự kiện chỉ để giảm số lượng HTTP request nếu người dùng vẫn bắt buộc phải chờ toàn bộ chuỗi xử lý hoàn thành. Cơ chế bất đồng bộ có ý nghĩa khi **quy tắc nghiệp vụ cho phép tách thời điểm hoàn thành**.

Ví dụ hợp đồng sự kiện:

~~~json
{
  "eventId": "evt-84ce",
  "eventType": "booking.confirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-18T03:00:00Z",
  "bookingId": "bk-1732",
  "propertyId": "home-25"
}
~~~

Trường **eventId** hỗ trợ consumer kiểm soát xử lý trùng; **schemaVersion** giúp quản lý tiến hóa hợp đồng. Đừng tự động nhét email, số điện thoại, thông tin thanh toán vào sự kiện rộng nếu không có yêu cầu nghiệp vụ và quyền truy cập tương ứng.

### 5.4. Giảm coupling thời điểm khi vẫn phải gọi đồng bộ

Không phải mọi tương tác đều phù hợp với queue. Ví dụ, khi chốt một đơn đặt phòng theo báo giá tức thời, Booking có thể phải kiểm tra kết quả định giá hoặc một quy tắc phê duyệt trước khi trả lời. Khi đó:

- Đặt **timeout** theo ngân sách độ trễ của hành trình người dùng.
- Giới hạn retry, dùng **exponential backoff** kèm jitter nếu phù hợp; không retry vô hạn một lỗi không thể phục hồi.
- Dùng **circuit breaker**, bulkhead hay giới hạn đồng thời khi cần để giảm lỗi lan truyền.
- Làm rõ kết quả khi dependency không sẵn sàng: từ chối an toàn, trả trạng thái chờ, hoặc phương án thay thế được nghiệp vụ chấp nhận.
- Đặt idempotency key cho thao tác có thể bị gửi lại nhằm tránh tạo nhiều giao dịch hoặc tác động ngoài ý muốn.

**Fallback không được phá bất biến nghiệp vụ.** Không thể “đoán là còn phòng” khi hệ thống kiểm tra tồn kho không phản hồi; một cache chỉ phục vụ tìm kiếm có thể cũ và không nên trở thành nguồn sự thật để chốt đặt chỗ.

### 5.5. Quản lý phụ thuộc dữ liệu

Nguyên tắc quan trọng là **có chủ sở hữu dữ liệu rõ ràng**. Các module có thể chung cơ sở dữ liệu vật lý khi ở dạng modular monolith, nhưng phải kiểm soát quyền ghi và tránh các truy vấn xuyên ranh giới tùy tiện. Khi tách dịch vụ, mỗi dịch vụ nên tự kiểm soát mô hình dữ liệu và đường ghi; **database-per-service** là một mô hình kiến trúc phổ biến, không phải điều kiện bắt buộc cho mọi hệ thống.

Một số kỹ thuật:

- Công bố dữ liệu cần chia sẻ qua API/query model/sự kiện với ý nghĩa ổn định.
- Dùng **CQRS/read model** hoặc bản sao đọc khi cần tối ưu truy vấn tổng hợp; chấp nhận và đo độ trễ đồng bộ.
- Chuyển schema từng bước: **expand → migrate → contract**, tránh yêu cầu tất cả consumer đổi cùng một thời điểm.
- Giữ các bất biến cần giao dịch mạnh trong cùng ranh giới khi có thể.
- Chỉ xem xét saga hoặc quy trình bù trừ cho giao dịch kéo dài qua nhiều ranh giới sau khi đã xác định rõ trạng thái trung gian, retry và thất bại không thể tự động bù.

Sao chép dữ liệu đọc có chủ đích có thể giảm phụ thuộc runtime, nhưng cần xác định bản gốc, độ mới chấp nhận được, quyền truy cập và cơ chế xử lý sai lệch.

## 6. Phân ranh giới theo luồng nghiệp vụ: ví dụ đặt phòng

Giả định sản phẩm cần hỗ trợ tìm phòng, lấy báo giá, giữ phòng, thanh toán và gửi xác nhận. Kiến trúc sư cùng product, phát triển, bảo mật và vận hành có thể lập bản đồ trách nhiệm:

| Thành phần | Năng lực/chính sách sở hữu | Dữ liệu sở hữu | Hợp đồng ra ngoài | Không nên sở hữu |
|---|---|---|---|---|
| Catalog | Thông tin niêm yết và trạng thái hiển thị | Metadata, mô tả phòng | Tìm kiếm, xem phòng | Xác nhận quyền đặt phòng tại thời điểm commit |
| Pricing | Tính giá, khuyến mại, quy tắc thuế theo phạm vi sản phẩm | Price rule, quote và phiên bản | Lấy báo giá có thời hạn | Sửa trực tiếp trạng thái Booking |
| Booking/Inventory | Giữ/nhả chỗ, xác nhận, hủy, chống trùng | Booking, hold, inventory state | Tạo/yêu cầu xác nhận/hủy; sự kiện trạng thái | Gửi email, phân tích marketing |
| Payment | Yêu cầu thu tiền, hoàn tiền, đối soát theo quy định | Payment attempt, provider reference | Tạo yêu cầu, trả trạng thái/nhận webhook | Thay đổi trực tiếp bảng giữ chỗ |
| Notification | Chọn kênh, template, gửi và theo dõi thông báo | Delivery record | Nhận sự kiện và xử lý gửi | Quyết định giao dịch Booking thành công |

Giữa Pricing và Booking cần làm rõ: **giá được khóa ở thời điểm nào, hiệu lực bao lâu và ai là nguồn sự thật của giá đã chấp nhận**. Giữa Payment và Booking cần làm rõ: **trạng thái PENDING, CONFIRMED, FAILED, CANCELLED có thể chuyển thế nào**, và khi thanh toán thành công nhưng xác nhận chỗ thất bại thì phải bù trừ/hoàn tiền ra sao. Các quyết định này quan trọng hơn việc chọn REST hay gRPC.

### 6.1. Luồng xác nhận có giới hạn phụ thuộc

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Booking
    participant DB as Booking DB
    participant Q as Queue
    participant N as Notification
    U->>B: Xác nhận đặt chỗ (idempotency key)
    B->>DB: Transaction: kiểm tra bất biến, ghi booking và outbox
    alt Không đủ điều kiện / tranh chấp
        DB-->>B: Rollback / conflict
        B-->>U: Trả trạng thái rõ ràng
    else Giao dịch thành công
        DB-->>B: Commit
        B-->>U: Booking đã xác nhận
        Note over DB,Q: Relay chuyển event từ outbox
        DB-->>Q: BookingConfirmed
        Q-->>N: Xử lý thông báo (có thể nhận lại)
        N->>N: Idempotency + gửi xác nhận
    end
~~~

Đây là **luồng rút gọn** nhằm minh họa ranh giới giao dịch đặt chỗ và thông báo. Trong ứng dụng có thanh toán, xác nhận cuối cùng có thể cần đi qua nhiều trạng thái và một quy trình phối hợp hoặc bù trừ. Không suy ra từ sơ đồ rằng gửi email “exactly once” được bảo đảm: broker và provider thực tế có thể chỉ hỗ trợ xử lý/giao lại với ngữ nghĩa khác.

### 6.2. Thiết kế mạng và compute mà vẫn giữ ranh giới

Ranh giới nghiệp vụ cần được thực thi thích hợp ở hạ tầng:

- **Compute:** các module cùng runtime có thể chung autoscaling. Nếu Booking và Search phải có mức tài nguyên hoặc chính sách scaling khác nhau, cân nhắc cô lập theo workload. Tách deployment chỉ có lợi khi có quy trình vận hành tương ứng.
- **Network:** chỉ công bố endpoint cần thiết, tách luồng công khai và nội bộ; áp dụng security group/firewall/policy theo nhu cầu truy cập thực tế.
- **Identity & access:** workload identity riêng, quyền tối thiểu tới DB, bucket, queue, secret; tránh một service account có toàn bộ quyền của hệ thống.
- **Data:** kiểm soát đường ghi, connection pool, quota, replication và mô hình khôi phục. Các dịch vụ logic tách rời nhưng dùng chung một DB có thể vẫn chịu lỗi và tranh chấp tài nguyên chung.
- **Observability:** trace xuyên ranh giới, log có correlation ID, metric theo từng hành trình nghiệp vụ; mọi message/event có thể truy vết được mà không lộ dữ liệu cá nhân.

**Sơ đồ mạng khác sơ đồ nghiệp vụ.** Hai thành phần đặt ở hai subnet chưa chắc đã phụ thuộc lỏng; ngược lại, hai module cùng chạy trong một tiến trình vẫn có thể có ranh giới mã nguồn tốt.

## 7. Modular monolith hay microservices?

Thiết kế gắn kết cao và phụ thuộc lỏng **không bắt buộc** phải dùng microservices. Chọn mô hình triển khai nên dựa vào tải, số đội phát triển, tần suất phát hành, yêu cầu độc lập về độ tin cậy và năng lực vận hành.

| Tiêu chí | Modular monolith | Microservices |
|---|---|---|
| Ranh giới nghiệp vụ | Module/API nội bộ, kiểm soát bằng cấu trúc mã và kiểm thử | Dịch vụ/API/event riêng, cần quản trị hợp đồng xuyên mạng |
| Triển khai | Thường phát hành một ứng dụng | Có thể phát hành riêng từng dịch vụ nếu không phụ thuộc triển khai chặt |
| Giao dịch dữ liệu | Dễ giữ một transaction trong DB chung theo ranh giới module | Transaction phân tán khó; cần thiết kế eventual consistency hoặc choreography/orchestration |
| Scale | Thường scale cả ứng dụng hoặc các nhóm workload có hỗ trợ | Có thể scale từng dịch vụ |
| Lỗi mạng | Ít lời gọi remote giữa module | Phải giải quyết timeout, retry, giao lại, partial failure |
| Vận hành | Ít pipeline/runtime độc lập | Nhiều pipeline, dashboard, quyền, cấu hình và trách nhiệm trực hơn |
| Chi phí | Thường đơn giản hơn lúc đầu | Có chi phí mạng, message broker, observability và nhiều tài nguyên nền |
| Phù hợp | Nhóm nhỏ/vừa, nghiệp vụ còn thay đổi nhiều, chưa cần vận hành riêng | Nhiều nhóm độc lập, ranh giới đã rõ, tải hoặc chu kỳ phát hành khác biệt đáng kể |

**Anti-pattern: distributed monolith.** Có nhiều deployment riêng nhưng mọi request đi qua chuỗi gọi đồng bộ dài, cùng đọc một schema DB và phải phát hành đồng thời. Khi đó hệ thống nhận thêm chi phí của kiến trúc phân tán nhưng không thu được tính độc lập mong muốn.

Hướng đi an toàn thường là **xây ranh giới module rõ, đo nhu cầu, rồi tách những ranh giới có lý do thuyết phục**. Khi tách, cần di chuyển từng phần dữ liệu và đường ghi có kiểm soát, tránh “đổi một lần toàn bộ” làm tăng rủi ro gián đoạn.

## 8. Đánh đổi theo tư duy Well-Architected

Giảm coupling và tăng cohesion cải thiện khả năng thay đổi, nhưng không tự động làm hệ thống an toàn hơn, rẻ hơn hoặc có độ sẵn sàng cao hơn. Phải kiểm chứng các đánh đổi:

| Góc nhìn | Tác động tích cực có thể đạt | Đánh đổi cần kiểm tra |
|---|---|---|
| **Operational excellence** | Chủ sở hữu và runbook rõ hơn, thay đổi cục bộ, giảm phối hợp release | Nhiều thành phần cần tracing, versioning, quản trị hợp đồng |
| **Security** | Quyền truy cập tối thiểu, cô lập dữ liệu và thu hẹp blast radius | Nhiều danh tính, điểm vào và chính sách truy cập cần quản lý |
| **Reliability** | Lỗi một thành phần có thể được cô lập, phục hồi từng workload | Sự phụ thuộc thời điểm và sự kiện thất lạc/trùng có thể tạo lỗi mới |
| **Performance efficiency** | Scale theo nhu cầu, cache/read model riêng | Network hop, serialization và consistency lag làm tăng độ trễ |
| **Cost optimization** | Scale chính xác thành phần tốn tài nguyên, tránh cấp dư cho tất cả | Chi phí hạ tầng nền, traffic, queue, log, trace và trực vận hành |
| **Sustainability** | Giảm cấp dư và tải lặp khi chia trách nhiệm phù hợp | Quá nhiều dịch vụ nhàn rỗi và dữ liệu sao chép có thể gây lãng phí |

### Tình huống đánh đổi

Một đội muốn tách Pricing khỏi Booking để có thể phát hành quy tắc giá mỗi tuần. Lợi ích kỳ vọng là Pricing thay đổi nhanh mà không phát hành lại Booking. Nhưng nếu mỗi yêu cầu xác nhận lại gọi Pricing theo mạng với độ trễ cao, Booking sẽ có thêm nguồn lỗi.

Kiến trúc sư cần trao đổi và đo:

1. Booking có thể sử dụng **báo giá đã được ký/xác nhận và còn hiệu lực** hay bắt buộc tính giá mới tại thời điểm xác nhận?
2. Nếu quote hết hạn, nghiệp vụ yêu cầu báo lỗi, tính lại hay giữ giá?
3. Khi Pricing lỗi, Booking được phép tiếp tục tới trạng thái nào?
4. SLO độ trễ, lưu lượng đỉnh, chi phí network và mức cô lập vận hành có còn chấp nhận được?
5. Phần thay đổi nhanh thật sự nằm ở hợp đồng Pricing hay chỉ ở rule configuration có thể quản lý trong cùng module?

Nếu chưa trả lời, **quyết định tách deployment đang đi trước việc hiểu coupling của quy trình nghiệp vụ**.

## 9. Đo lường mức độ độc lập thay vì chỉ nhìn sơ đồ

Không có một chỉ số duy nhất chứng minh hệ thống đã “loose coupled”. Nên kết hợp số đo định lượng với đánh giá dựa trên hành trình nghiệp vụ:

| Dấu hiệu hoặc phép đo | Cách sử dụng | Cảnh báo khi diễn giải |
|---|---|---|
| **Change coupling** | Đếm thay đổi thường xuyên phải sửa/phát hành nhiều module cùng lúc | Có thể phản ánh yêu cầu sản phẩm lớn, không chỉ ranh giới kém |
| **Fan-out và call-chain depth** | Xem một request phải gọi bao nhiêu dependency, bao nhiêu hop | Nhiều lời gọi không mặc nhiên xấu; cần đối chiếu latency/failure |
| **Deployment independence** | Đo tỷ lệ release phải phối hợp, số lần rollback liên dịch vụ | Có thể bị ảnh hưởng bởi chính sách quy trình |
| **SLO và lỗi lan truyền** | Theo dõi lỗi một dependency có ảnh hưởng nghiệp vụ khác hay không | SLO cần định nghĩa đúng hành trình và giới hạn tải |
| **Tỷ lệ schema change ảnh hưởng consumer** | Phát hiện producer và consumer phụ thuộc cấu trúc nội bộ | Cần phân biệt contract change chủ động với break bất ngờ |
| **Độ trễ và backlog sự kiện** | Đo sự phụ thuộc thời điểm đã được chuyển sang bất đồng bộ | Queue ổn định không đồng nghĩa dữ liệu downstream luôn mới |
| **Chi phí mỗi giao dịch nghiệp vụ** | Đối chiếu network, compute, broker, log trước/sau tách | Cần thống nhất cách phân bổ chi phí và mức tải so sánh |

Trong mã nguồn, có thể vẽ sơ đồ dependency giữa package/module và áp dụng quy tắc kiến trúc: module **Notification** không được import package nội bộ của **Booking**; adapter cloud không được bị truy cập trực tiếp từ domain layer. Những quy tắc này có thể đưa vào kiểm tra CI bằng công cụ phù hợp hệ sinh thái (ví dụ architecture tests trong Java), song không cần tạo cơ chế cồng kềnh nếu các module vẫn nhỏ và dễ quan sát.

### Architecture fitness functions

Một **fitness function** là kiểm tra hoặc phép đo cho biết ràng buộc kiến trúc còn được giữ trong quá trình phát triển. Ví dụ:

- Kiểm tra CI phát hiện dependency đi ngược chiều giữa domain và infrastructure.
- Contract tests phát hiện thay đổi API phá vỡ consumer đã được công bố.
- Kiểm thử concurrency cho Booking xác nhận không có hai đặt chỗ trùng trong cùng kịch bản cạnh tranh.
- Fault injection cho Email provider chứng minh giao dịch đặt chỗ không phụ thuộc vào email.
- Đo p95 latency và tỷ lệ lỗi sau khi tách một RPC mới khỏi tiến trình.

Một sơ đồ kiến trúc được cập nhật rất hữu ích, nhưng **hành vi dưới thay đổi và sự cố mới chứng minh ranh giới có thực sự hiệu quả**.

## 10. Các phản mẫu thường gặp và cách cải thiện

| Phản mẫu | Vì sao gây vấn đề | Hướng xử lý |
|---|---|---|
| **God component / SharedService** chứa mọi thứ | Cohesion thấp, mọi tính năng cùng chạm một điểm | Xác định năng lực nghiệp vụ và phân thành module có chủ sở hữu rõ |
| **Shared database không kiểm soát quyền ghi** | Đụng chạm schema, migration khó, lỗi lan rộng | Quy định một đường ghi/chủ sở hữu; cung cấp API hoặc read model phù hợp |
| **Chatty distributed calls** | Độ trễ và xác suất lỗi cộng dồn theo chuỗi | Xem lại ranh giới, tổng hợp hợp đồng, giảm số hop, bất đồng bộ nơi phù hợp |
| **Service per table** | Bất biến nghiệp vụ bị chia vụn, cần giao dịch xuyên dịch vụ | Gom theo quy tắc và vòng đời nghiệp vụ thay vì bảng dữ liệu |
| **Event soup** không có owner/schema/version | Không ai hiểu ai phát hay tiêu thụ sự kiện, khó debug | Quản lý event catalog, schema version, quyền, lineage và ownership |
| **Sao chép logic nghiệp vụ** | Hai dịch vụ tính khác nhau cho cùng quy tắc | Chọn nơi sở hữu chính sách, cung cấp hợp đồng hoặc snapshot có điều kiện |
| **Abstraction quá mức** | Nhiều interface chỉ chuyển tiếp, khó truy vết | Chỉ trừu tượng hóa ranh giới dự kiến thay đổi hoặc cần thử nghiệm/thay adapter |
| **Cố loại bỏ mọi coupling** | Hợp đồng trở nên gián tiếp và khó hiểu, tăng lớp tích hợp | Chấp nhận phụ thuộc hợp lý, công khai và có kiểm soát |

Một lưu ý về **shared library**: chia sẻ logging, tracing, kiểu lỗi hoặc client chung có thể hợp lý; nhưng một thư viện chứa toàn bộ domain model của nhiều dịch vụ dễ tạo phụ thuộc triển khai vì mỗi lần thay đổi business rule đều buộc mọi dịch vụ nâng version cùng lúc.

## 11. Quy trình thực hành khi cải tiến kiến trúc đang có

Không cần viết lại toàn bộ hệ thống để cải thiện coupling/cohesion. Có thể đi theo vòng lặp nhỏ:

**Bước 1 — Xác định mục tiêu thay đổi.** Ví dụ: sửa template email không phải phát hành Booking; Search tăng tải không làm cạn connection pool của giao dịch xác nhận.

**Bước 2 — Vẽ hiện trạng.** Liệt kê thành phần, owner, ranh giới dữ liệu, chiều phụ thuộc, call-chain, deployment và kịch bản sự cố. Phân biệt phụ thuộc **compile-time**, **runtime** và **operational**.

**Bước 3 — Chọn bất biến và capability.** Xác định những hành vi thực sự cần ở cùng ranh giới; đặt một owner rõ cho mỗi quy tắc trọng tâm và đường ghi dữ liệu.

**Bước 4 — Đề xuất một thay đổi nhỏ.** Ví dụ: chuyển email thành consumer sự kiện được phát qua outbox; giữ nguyên Booking cùng DB hiện hữu trong giai đoạn đầu. Hoặc tách Pricing thành module có interface nội bộ trước khi tách network.

**Bước 5 — Thiết kế an toàn cho cả thành công lẫn thất bại.** Kiểm tra contract, idempotency, timeout, quyền, cách deploy/backfill, rollback hoặc roll-forward và cách khôi phục.

**Bước 6 — Đo trước/sau.** Kiểm tra số module thay đổi trong một yêu cầu, tỷ lệ triển khai phối hợp, latency, lỗi lan truyền, độ trễ event, chi phí và khối lượng vận hành.

**Bước 7 — Ghi quyết định và tiếp tục cải tiến.** Cập nhật ADR/sơ đồ, chia sẻ những ranh giới mới với các đội và kiểm tra thực tế vận hành trước khi tách tiếp.

### Mẫu Architecture Decision Record (ADR)

~~~text
ADR-012: Tách xử lý thông báo ra khỏi luồng xác nhận đặt phòng
Status: Accepted

Context:
  Booking đang gọi email provider đồng bộ.
  Email provider chậm hoặc lỗi khiến request đặt phòng thất bại.

Options:
  A. Giữ gọi đồng bộ, thêm timeout và retry.
  B. Commit Booking + outbox; gửi BookingConfirmed;
     Notification xử lý bất đồng bộ.

Decision:
  Chọn B, vì gửi email không phải điều kiện nghiệp vụ để xác nhận chỗ.

Consequences:
  + Giảm phụ thuộc thời điểm vào email provider.
  + Có thể scale Notification riêng nếu thực sự cần.
  - Cần outbox relay, retry, consumer idempotent,
    giám sát backlog và xử lý message lỗi.

Validation:
  - Khi email provider gián đoạn, Booking vẫn hoàn tất hợp lệ.
  - Không làm mất event sau khi DB commit.
  - Theo dõi độ trễ thông báo và message trùng.

Revisit when:
  - Luật nghiệp vụ đổi, yêu cầu xác nhận đồng thời bằng email;
  - Mục tiêu thời gian gửi và chi phí vận hành thay đổi đáng kể.
~~~

## 12. Bài tập tự đánh giá thiết kế

**Tình huống:** Công ty có ba dịch vụ: Reservation, Pricing và Notification. Reservation truy vấn trực tiếp bảng giá của Pricing, gọi Notification đồng bộ trước khi commit, và mỗi khi đổi schema Pricing thì cả ba dịch vụ phải deploy cùng ngày. Vào dịp khuyến mại, Notification nghẽn làm tăng tỷ lệ thất bại đặt chỗ.

Hãy tự trả lời:

1. Những dạng coupling nào đang hiện diện? Phụ thuộc nào gây ảnh hưởng trực tiếp tới độ tin cậy?
2. Quy tắc nào cần giữ trong ranh giới giao dịch Reservation, và quy tắc nào có thể xử lý sau?
3. Có thể thay truy vấn bảng giá bằng hợp đồng nào? Giá cần nhất quán ở thời điểm nào?
4. Cần thêm những cơ chế nào khi chuyển Notification sang xử lý sự kiện?
5. Cần kiểm thử và đo các chỉ số nào để chứng minh cải tiến thành công?

**Gợi ý hướng giải:** Dùng API/quote có version và thời hạn thay vì sửa bảng dữ liệu của Pricing; chốt rõ hiệu lực báo giá; giữ kiểm tra và xác nhận chỗ ở ranh giới giao dịch phù hợp; chuyển Notification thành consumer nhận sự kiện đáng tin cậy sau commit qua outbox; có xử lý trùng, retry có giới hạn, quan sát backlog và bảo vệ dữ liệu trong event. Kiểm thử đặt chỗ đồng thời, lỗi email provider, tiến trình chết sau commit, tương thích schema, p95 latency và chi phí để kiểm chứng.

### Checklist review

- [ ] Mỗi thành phần có một mục tiêu nghiệp vụ hoặc năng lực kỹ thuật rõ ràng, tránh trộn trách nhiệm không liên quan.
- [ ] Những bất biến phải bảo vệ được xác định và có người sở hữu thống nhất.
- [ ] Các dependency cần thiết được mô tả bằng hợp đồng, giới hạn lỗi và cơ chế bảo mật cụ thể.
- [ ] Không có đường ghi trực tiếp không được quản lý vào dữ liệu thuộc thành phần khác.
- [ ] Gọi đồng bộ có timeout, retry an toàn và hành vi khi dependency không khả dụng.
- [ ] Luồng bất đồng bộ có xử lý trùng, mất/giao lại, schema version và theo dõi backlog.
- [ ] Thiết kế mạng, compute, IAM, dữ liệu và triển khai phản ánh ranh giới trách nhiệm.
- [ ] Kiến trúc được kiểm chứng bằng kiểm thử thay đổi, sự cố, tải và số liệu vận hành/chi phí.
- [ ] Đã so sánh mức phức tạp với phương án modular monolith hoặc module nội bộ trước khi tách dịch vụ.
- [ ] Quyết định, đánh đổi, owner và điều kiện xem lại được ghi nhận.

## 13. Ghi nhớ

**High cohesion** giúp một thành phần có trách nhiệm tập trung, bảo vệ các quy tắc liên quan và thay đổi với ít lý do độc lập hơn. **Loose coupling** giúp thành phần giao tiếp qua ranh giới rõ, hạn chế lộ chi tiết và giảm tác động lan truyền khi triển khai hoặc xảy ra lỗi.

Trong kiến trúc cloud, hai nguyên lý phải được áp dụng đồng thời với các yêu cầu **độ tin cậy, bảo mật, khả năng mở rộng, hiệu năng, chi phí và vận hành**. Mục tiêu không phải là có nhiều dịch vụ hay nhiều lớp trừu tượng, mà là một hệ thống **có thể thay đổi, kiểm chứng và vận hành** mà không phá vỡ những bất biến nghiệp vụ quan trọng.
