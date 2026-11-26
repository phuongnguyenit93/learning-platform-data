# Độ trễ đồng bộ

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp qua sự kiện để giảm phụ thuộc và bảo vệ ranh giới nghiệp vụ. Khi một module phát event và module khác xử lý sau đó, dữ liệu ở hai nơi có thể tạm thời khác nhau. Khoảng thời gian từ lúc sự thật nghiệp vụ được ghi nhận đến lúc các consumer cập nhật xong dữ liệu của mình được gọi là **độ trễ đồng bộ**.

Độ trễ này là đặc tính tự nhiên của kiến trúc bất đồng bộ và nhất quán cuối cùng. Nó trở thành vấn đề khi vượt quá thời gian mà nghiệp vụ chấp nhận, không được quan sát hoặc khiến người dùng hiểu sai trạng thái. Thiết kế tốt cần xác định dữ liệu nào có thể tạm thời cũ, giới hạn thời gian chấp nhận, đo được độ trễ ở từng chặng và có cách phục hồi khi consumer bị chậm hoặc thất bại.

## 1. Độ trễ đồng bộ là gì?

Giả sử khách hàng đặt hàng. Module Orders commit trạng thái đơn hàng là CONFIRMED và phát OrderConfirmed. Module Inventory nhận event để cập nhật nhu cầu giữ hàng; module Analytics cập nhật báo cáo; module Notification gửi thông báo. Các module này không nhất thiết cập nhật dữ liệu trong cùng transaction hoặc cùng thời điểm.

Trong khoảng thời gian giữa các lần cập nhật, hệ thống có thể quan sát những trạng thái khác nhau:

- Orders đã hiển thị đơn hàng CONFIRMED.
- Inventory chưa nhận được event nên chưa hiển thị reservation.
- Analytics vẫn tính số liệu trước khi đơn hàng được xác nhận.
- Notification chưa gửi thông báo cho khách hàng.

Độ trễ đồng bộ là thời gian một thay đổi cần để lan đến một đích đọc hoặc consumer cụ thể. Không có một con số duy nhất cho toàn hệ thống; mỗi projection, listener hoặc downstream có độ trễ riêng.

Có thể phân biệt các mốc:

| Mốc | Ý nghĩa |
|---|---|
| occurredAt | Thời điểm sự thật nghiệp vụ xảy ra |
| committedAt | Thời điểm transaction sở hữu dữ liệu commit |
| publishedAt | Thời điểm event được đưa vào cơ chế giao nhận |
| receivedAt | Thời điểm consumer nhận event |
| processedAt | Thời điểm consumer hoàn tất cập nhật |
| visibleAt | Thời điểm dữ liệu mới có thể được truy vấn từ đích đọc |

Độ trễ end-to-end của một consumer có thể được tính từ committedAt đến visibleAt. Nếu cần đo riêng thời gian chờ trước khi consumer nhận event, dùng receivedAt trừ publishedAt. Thời gian xử lý của consumer là processedAt trừ receivedAt. Cần thống nhất định nghĩa metric để các nhóm không so sánh những khoảng thời gian khác nhau.

Timestamp giữa các máy có thể lệch. Khi tính latency xuyên hệ thống, đồng bộ đồng hồ và theo dõi clock skew; với queue, tuổi của message cũ nhất và thời gian giữa các mốc trong cùng một tiến trình thường đáng tin cậy hơn việc chỉ trừ hai timestamp không được đồng bộ.

## 2. Vì sao độ trễ xuất hiện?

Một event có thể phải đi qua nhiều chặng trước khi dữ liệu đích được cập nhật. Mỗi chặng thêm thời gian chờ và khả năng phát sinh lỗi.

Các nguyên nhân thường gặp:

- Listener chạy bất đồng bộ nên chỉ bắt đầu sau khi transaction nghiệp vụ commit.
- Executor hoặc broker có backlog vì tốc độ phát event cao hơn tốc độ xử lý.
- Consumer xử lý chậm do truy vấn database, lock, gọi API hoặc xử lý payload lớn.
- Retry và backoff làm event thất bại được xử lý muộn hơn.
- Network, broker hoặc database tạm thời mất kết nối.
- Consumer được scale về 0, restart hoặc triển khai phiên bản mới.
- Một partition hoặc aggregate có tải nóng khiến các event khác phải chờ.
- Projection cần nhiều bước tổng hợp trước khi dữ liệu có thể truy vấn.
- Hệ thống đích giới hạn quota hoặc rate của API.

Độ trễ không nhất thiết là lỗi. Một báo cáo phân tích cập nhật mỗi vài phút có thể hoàn toàn phù hợp với nghiệp vụ. Ngược lại, tồn kho hiển thị sai trong lúc người dùng đặt hàng có thể gây oversell và cần kiểm soát chặt hơn.

## 3. Phân biệt nhất quán mạnh và nhất quán cuối cùng

**Nhất quán mạnh** yêu cầu các lần đọc sau một lần ghi nhìn thấy kết quả đã commit theo semantics của hệ thống. Trong một database và một transaction boundary, đây thường là lựa chọn phù hợp cho các quy tắc cần quyết định ngay, ví dụ kiểm tra số lượng tồn kho trước khi xác nhận giữ hàng.

**Nhất quán cuối cùng** cho phép các bản sao hoặc projection cập nhật lệch thời điểm, nhưng nếu không có thêm lỗi và event được xử lý thành công thì chúng sẽ hội tụ về cùng trạng thái. Đây là mô hình phổ biến khi dùng application events để đồng bộ giữa các module hoặc dịch vụ.

Không nên cố làm mọi dữ liệu nhất quán mạnh. Việc đồng bộ bắt buộc qua nhiều dịch vụ có thể làm tăng latency, giảm khả năng chịu lỗi và tạo phụ thuộc thời gian chạy. Thay vào đó, hãy phân loại theo yêu cầu nghiệp vụ:

| Loại dữ liệu | Mức nhất quán thường phù hợp | Lý do |
|---|---|---|
| Số dư có thể chi tiêu | Mạnh trong ranh giới sở hữu | Tránh chi tiêu vượt số dư |
| Reservation tồn kho | Mạnh tại module Inventory | Tránh giữ cùng một đơn vị hàng nhiều lần |
| Trạng thái hiển thị của đơn hàng | Có thể eventual với trạng thái đang xử lý rõ | Giao diện có thể cập nhật khi event đến |
| Dashboard phân tích | Eventual với độ trễ được công bố | Người dùng chấp nhận dữ liệu gần thời gian thực |
| Email/thông báo | Bất đồng bộ | Không cần chặn transaction đặt hàng |
| Search index | Eventual | Có thể xây dựng lại từ nguồn dữ liệu chính |

Nguồn dữ liệu sở hữu domain phải là nơi quyết định quy tắc nghiệp vụ. Projection hoặc read model có thể chậm hơn và không nên trở thành nguồn quyết định cuối cùng cho thao tác cần tính đúng đắn tức thời.

## 4. Đặt ngân sách độ trễ theo nghiệp vụ

Không có một ngưỡng latency phù hợp cho mọi event. Hãy xác định **staleness budget** cho từng consumer: dữ liệu đích được phép cũ tối đa bao lâu trước khi gây ảnh hưởng đến người dùng hoặc nghiệp vụ.

Ví dụ minh họa:

| Luồng | Ngân sách độ trễ giả định | Khi vượt ngưỡng |
|---|---:|---|
| Cập nhật trạng thái đơn trong màn hình theo dõi | 2 giây | Hiển thị đang cập nhật và cảnh báo nếu kéo dài |
| Cập nhật search index | 30 giây | Cho phép tìm kiếm chậm cập nhật, theo dõi backlog |
| Dashboard vận hành | 2 phút | Hiển thị thời điểm dữ liệu được làm mới |
| Báo cáo phân tích tổng hợp | 15 phút | Đánh dấu dữ liệu chưa cập nhật đủ kỳ |
| Gửi email xác nhận | 1 phút | Retry và cảnh báo nếu notification bị kẹt |

Đây là số liệu minh họa, không phải mặc định của Spring Modulith. Ngân sách thực tế cần được thống nhất với chủ sở hữu nghiệp vụ và đo trên workload production.

Nên xác định ít nhất ba ngưỡng:

- **Target:** mức độ trễ bình thường mong muốn.
- **Warning:** ngưỡng cần điều tra vì có nguy cơ vượt cam kết.
- **Critical:** ngưỡng vi phạm SLO hoặc có thể gây sai quyết định nghiệp vụ.

Đừng chỉ đặt ngưỡng theo latency trung bình. p95, p99 và tuổi của event cũ nhất thường phản ánh trải nghiệm xấu và backlog kéo dài tốt hơn.

## 5. Đo độ trễ ở từng chặng

Một metric end-to-end cho biết người dùng đang chờ bao lâu, nhưng chưa chỉ ra nơi gây chậm. Hãy đo riêng từng chặng:

1. Transaction commit đến publication được ghi nhận.
2. Publication được ghi nhận đến khi listener bắt đầu.
3. Listener bắt đầu đến khi xử lý hoàn tất.
4. Adapter gửi message đến broker xác nhận.
5. Broker nhận message đến consumer nhận.
6. Consumer nhận đến khi projection commit.
7. Projection commit đến khi dữ liệu có thể đọc từ query path.

Với mỗi event, nên mang metadata truy vết phù hợp như eventId, correlationId, causationId, eventType và occurredAt. Consumer có thể ghi receivedAt và processedAt trong log hoặc metric. Không cần ghi toàn bộ payload vào log.

Các metric hữu ích:

| Metric | Mục đích |
|---|---|
| Event publish rate | Đo tốc độ phát event |
| Event processing rate | Đo tốc độ consumer hoàn tất |
| Publication backlog | Số publication chưa hoàn tất |
| Oldest publication age | Tuổi của publication cũ nhất |
| Consumer lag | Mức chậm của consumer so với nguồn message |
| Processing latency p50/p95/p99 | Phân bố thời gian xử lý |
| Retry count/rate | Phát hiện lỗi và xử lý lặp |
| Projection freshness | Thời điểm dữ liệu đích được cập nhật gần nhất |
| Failed/dead-letter count | Message không thể xử lý tự động |

Đối với projection được cập nhật liên tục, có thể lưu lastProcessedAt hoặc watermark theo consumer. Watermark nên thể hiện đến event/sequence nào đã được xử lý; chỉ lưu timestamp có thể không đủ nếu event đến sai thứ tự hoặc timestamp bị lệch.

## 6. Publication Registry và độ trễ listener trong Spring Modulith

Spring Modulith cung cấp Event Publication Registry để theo dõi việc giao application event đến các listener. Registry ghi nhận publication và trạng thái xử lý để ứng dụng có thể quan sát các publication chưa hoàn tất và phục hồi theo cấu hình lưu trữ phù hợp.

Khi listener xử lý chậm hoặc thất bại, publication có thể vẫn ở trạng thái chưa hoàn tất. Đây là tín hiệu quan trọng để đo độ trễ trong phạm vi ứng dụng.

Cần phân biệt:

- Event Publication Registry theo dõi publication đến listener của ứng dụng.
- Executor queue giữ các task bất đồng bộ đang chờ chạy.
- Broker queue giữ message cho consumer bên ngoài.
- Projection store giữ dữ liệu đọc đã được cập nhật.

Một publication được đánh dấu hoàn tất khi listener tương ứng đã xử lý xong theo cơ chế registry; điều đó không có nghĩa mọi projection, broker consumer hoặc hệ thống ngoài đã đồng bộ. Hãy đo riêng từng ranh giới.

Nếu dùng listener sau commit, event chỉ được xử lý sau khi transaction nghiệp vụ commit. Đây là cách tránh để listener phản ứng với thay đổi chưa commit. Tuy nhiên, listener sau commit thông thường không tự tạo bảo đảm lưu trữ bền vững cho mọi trường hợp process crash. Khi cần phục hồi publication sau restart, hãy cấu hình publication registry và persistence phù hợp với phiên bản Spring Modulith đang sử dụng.

Ví dụ listener xử lý event sau commit:

~~~java
@Component
class OrderProjectionListener {

    private final OrderProjectionRepository projections;

    OrderProjectionListener(OrderProjectionRepository projections) {
        this.projections = projections;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderConfirmed event) {
        projections.markConfirmed(
            event.orderId(),
            event.occurredAt()
        );
    }
}
~~~

Ví dụ minh họa thời điểm listener chạy sau khi transaction commit. Nếu listener cần chạy bất đồng bộ, cần cấu hình cơ chế async và transaction cho phần cập nhật projection phù hợp. Không giả định exception từ listener sau commit có thể rollback transaction nghiệp vụ đã hoàn tất.

## 7. Đảm bảo publication không bị mất giữa commit và xử lý

Một rủi ro quan trọng là transaction nghiệp vụ đã commit nhưng tiến trình dừng trước khi event được xử lý. Nếu chỉ dùng cơ chế callback sau commit trong bộ nhớ, event có thể không được xử lý sau khi process restart.

Với Spring Modulith, Event Publication Registry được thiết kế để ghi nhận publication theo transaction boundary và theo dõi trạng thái listener. Hãy dùng persistence implementation được hỗ trợ và xác minh registry tham gia đúng transaction manager với dữ liệu nghiệp vụ khi yêu cầu tính nguyên tử.

Với message gửi ra broker hoặc hệ thống bên ngoài, transactional outbox là một lựa chọn phổ biến: ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction, sau đó relay gửi message. Outbox giúp tránh dual-write giữa database và broker. Relay có thể gửi lặp khi không biết broker đã nhận hay chưa, nên consumer vẫn cần idempotency.

Không nhầm publication registry với outbox tích hợp broker. Registry phục vụ việc theo dõi publication của application event đến listener; outbox là mẫu lưu ý định phát message ra một transport. Hai cơ chế có thể xuất hiện trong cùng kiến trúc nhưng bảo vệ những chặng khác nhau.

## 8. Xử lý read-after-write trong giao diện và API

Một trải nghiệm thường gây nhầm lẫn là người dùng vừa ghi dữ liệu thành công nhưng đọc từ projection lại thấy giá trị cũ. Ví dụ, người dùng xác nhận đơn hàng, API trả về thành công, nhưng màn hình danh sách vẫn hiển thị PENDING vì read model chưa nhận event.

Có một số cách xử lý:

**Trả trạng thái từ nguồn sở hữu.** Sau khi command thành công, API có thể trả về trạng thái đã commit từ module sở hữu thay vì đọc ngay từ projection eventual.

**Hiển thị trạng thái đang cập nhật.** Giao diện cho biết đơn đã được xác nhận và các dữ liệu liên quan đang đồng bộ. Có thể hiển thị thời điểm cập nhật cuối cùng.

**Read-your-writes.** Gắn version hoặc sequence của thay đổi vào response. Khi client đọc lại, query path có thể chờ projection đạt ít nhất version đó trong một khoảng thời gian có giới hạn; nếu chưa đạt, trả về trạng thái pending hoặc dùng nguồn đọc phù hợp.

**Đọc từ primary khi cần.** Với thao tác quan trọng, query có thể đọc từ nguồn dữ liệu sở hữu thay vì read replica hoặc projection đang trễ.

**Polling hoặc push update.** Client có thể polling theo order ID hoặc nhận cập nhật qua WebSocket/SSE. Cần giới hạn tần suất và có timeout để tránh tạo tải không cần thiết.

Không nên trả một trạng thái “đã hoàn tất” nếu chỉ mới ghi nhận yêu cầu. Hãy phân biệt request accepted, nghiệp vụ committed và downstream projection synchronized.

## 9. Read model và CQRS

Trong CQRS, write model sở hữu quy tắc nghiệp vụ và nhận command; read model được cập nhật từ event để tối ưu truy vấn. Read model thường eventual consistent vì được cập nhật bất đồng bộ.

Mỗi projection nên có:

- Nguồn event và loại event mà nó tiêu thụ.
- Định danh projection và consumer.
- Quy tắc áp dụng event và cách xử lý trùng.
- Version hoặc sequence để phát hiện event cũ/sai thứ tự.
- Watermark hoặc lastProcessedPosition.
- Ngân sách độ trễ và cách hiển thị freshness.
- Quy trình rebuild hoặc replay khi projection hỏng.

Nếu projection được cập nhật bằng cách cộng dồn, event trùng có thể làm số liệu tăng hai lần. Dùng event ID đã xử lý hoặc version theo aggregate để bảo vệ phép cập nhật. Với snapshot event, có thể chỉ áp dụng phiên bản mới hơn; với delta event, cần bảo đảm không bỏ qua sequence ở giữa.

Một projection có thể phục hồi bằng cách replay event từ nguồn lưu trữ hoặc tái tạo từ dữ liệu sở hữu. Cần xác định rõ event retention có đủ dài để rebuild hay không; publication registry không mặc nhiên là kho lưu lịch sử event vô thời hạn.

## 10. Thứ tự event và độ trễ theo aggregate

Độ trễ đồng bộ có thể trở nên khó xử lý khi event đến sai thứ tự. Ví dụ OrderShipped đến consumer trước OrderConfirmed do retry, nhiều consumer hoặc nhiều partition. Nếu projection áp dụng ngay event mới hơn rồi nhận event cũ, dữ liệu có thể bị lùi trạng thái.

Cách kiểm soát:

- Gắn sequence/version tăng dần theo aggregate.
- Áp dụng event theo thứ tự trong phạm vi aggregate nếu nghiệp vụ yêu cầu.
- Bỏ qua event có version nhỏ hơn hoặc bằng version đã áp dụng khi semantics cho phép.
- Phát hiện khoảng trống sequence và chờ, retry hoặc đối soát.
- Không dựa hoàn toàn vào timestamp để suy ra thứ tự.
- Giới hạn phạm vi tuần tự hóa để không làm giảm throughput toàn hệ thống.

Không phải mọi event đều cần thứ tự toàn cục. Thường chỉ cần bảo đảm thứ tự theo orderId, accountId hoặc aggregate ID liên quan. Điều này cho phép xử lý song song giữa các aggregate khác nhau.

## 11. Retry, backoff và backlog

Khi consumer thất bại, retry có thể kéo dài thời gian đồng bộ. Retry tức thì có thể tạo vòng lặp nóng, làm tăng tải lên database hoặc dịch vụ đang gặp sự cố.

Chính sách retry nên phân loại lỗi:

- Lỗi tạm thời như timeout, mất kết nối hoặc rate limit: retry với exponential backoff và jitter.
- Lỗi dữ liệu hoặc schema không hợp lệ: cách ly để điều tra, không retry vô hạn.
- Lỗi nghiệp vụ không thể tự phục hồi: phát event kết quả thất bại hoặc chuyển sang xử lý thủ công.
- Lỗi cấu hình/quyền truy cập: cảnh báo rõ và tránh retry dày đặc.

Theo dõi backlog cùng oldest event age. Backlog lớn nhưng đang giảm có thể ít nghiêm trọng hơn backlog nhỏ nhưng tuổi event cũ nhất tiếp tục tăng. Khi downstream phục hồi, cần giới hạn tốc độ replay để tránh tạo đợt tải đột biến.

Consumer cần idempotent vì một event có thể được gửi lại sau khi xử lý thành công nhưng acknowledgement bị mất. Với thay đổi database, ghi event ID đã xử lý bằng unique constraint trong cùng transaction với projection update. Với API ngoài, dùng idempotency key nếu dịch vụ hỗ trợ.

## 12. Đối soát và sửa sai khi dữ liệu không hội tụ

Retry không giải quyết mọi trường hợp. Có thể một event bị mất do lỗi cấu hình cũ, projection có bug hoặc dữ liệu bị sửa thủ công. Cần quy trình reconciliation để so sánh nguồn sở hữu với read model và phát hiện sai lệch.

Một quy trình đối soát có thể:

1. Chọn tập dữ liệu hoặc khoảng thời gian cần kiểm tra.
2. Đọc trạng thái từ nguồn sở hữu.
3. Đọc projection tương ứng.
4. So sánh theo business ID và version.
5. Phân loại sai lệch: projection chậm, thiếu event, xử lý trùng hoặc logic projection sai.
6. Sửa bằng replay, rebuild hoặc lệnh repair có kiểm soát.
7. Ghi audit về số bản ghi đã sửa và kết quả.

Không sửa dữ liệu domain trực tiếp từ projection chỉ để hai nơi trông giống nhau. Nguồn sở hữu domain quyết định sự thật; projection được xây dựng lại hoặc cập nhật theo quy tắc đã định.

Nếu cần replay event, hãy xác định event ID, sequence, schema version, retention và tác động phụ. Replay projection nên không gửi lại email, thu tiền hoặc thực hiện hành động bên ngoài ngoài ý muốn. Tách projection handler khỏi side effect hoặc dùng chế độ replay an toàn.

## 13. Khi nào cần chờ đồng bộ và khi nào không?

Không nên buộc mọi request chờ tất cả listener hoàn tất. Điều này làm tăng latency và khiến availability của request phụ thuộc vào mọi consumer.

Chỉ chờ khi kết quả đồng bộ là điều kiện để quyết định nghiệp vụ tiếp theo. Ví dụ, xác nhận giữ hàng cần biết module Inventory đã chấp nhận reservation hay chưa. Với email, analytics hoặc search index, thường có thể xử lý bất đồng bộ.

Có thể dùng bảng quyết định:

| Câu hỏi | Hướng xử lý |
|---|---|
| Kết quả consumer có quyết định việc command được phép thành công không? | Cân nhắc giao tiếp đồng bộ hoặc một workflow có phản hồi rõ |
| Consumer chỉ cập nhật dữ liệu hiển thị? | Chấp nhận eventual consistency với freshness indicator |
| Consumer gọi dịch vụ bên ngoài chậm? | Không giữ request thread; dùng async và trạng thái tiến trình |
| Người dùng cần đọc ngay dữ liệu vừa ghi? | Dùng read-your-writes hoặc đọc từ nguồn sở hữu |
| Event có tác dụng phụ không thể lặp? | Bắt buộc idempotency và cơ chế ghi nhận xử lý |

Nếu cần phản hồi ngay nhưng công việc sẽ hoàn tất sau, API có thể trả 202 Accepted cùng process ID hoặc resource status URL. Client kiểm tra tiến trình sau đó. Không trả 200 với thông điệp “đã hoàn tất” nếu thực tế chỉ mới xếp hàng.

## 14. Ví dụ luồng đồng bộ đơn hàng

Giả sử Orders là nguồn sở hữu trạng thái đơn. Sau khi transaction xác nhận đơn commit, event OrderConfirmed được ghi nhận. Inventory cập nhật reservation, Search cập nhật chỉ mục và Analytics cập nhật số liệu.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Orders
    participant R as Publication Registry
    participant I as Inventory
    participant S as Search Projection
    participant A as Analytics

    C->>O: Confirm order
    O->>O: Commit CONFIRMED
    O->>R: Record OrderConfirmed publication
    O-->>C: CONFIRMED + version
    R->>I: Deliver event
    R->>S: Deliver event
    R->>A: Deliver event
    I->>I: Update reservation
    S->>S: Update search index
    A->>A: Update report
~~~

Client nhận trạng thái từ Orders ngay sau commit. Các projection cập nhật sau đó. Nếu Search chậm, màn hình tìm kiếm có thể chưa thấy đơn mới; màn hình chi tiết đơn vẫn có thể đọc trạng thái từ Orders hoặc hiển thị thông tin đang đồng bộ.

Độ trễ của Inventory, Search và Analytics cần được đo riêng. Không nên đánh dấu toàn bộ quy trình đồng bộ xong chỉ vì một listener đã hoàn tất.

## 15. Kiểm thử độ trễ và tính nhất quán

Kiểm thử cần xác minh cả tính đúng đắn và thời gian hội tụ. Một test chỉ kiểm tra listener được gọi không đủ để phát hiện backlog, retry hoặc projection bị lùi version.

Các tình huống cần kiểm tra:

- Event được xử lý ngay sau commit trong điều kiện bình thường.
- Consumer chậm hơn tốc độ phát event.
- Consumer tạm dừng rồi tiếp tục xử lý backlog.
- Listener lỗi và publication được retry.
- Ứng dụng restart khi còn publication chưa hoàn tất.
- Event được gửi lặp sau khi consumer đã commit.
- Event đến sai thứ tự hoặc thiếu sequence.
- Projection rebuild từ event lịch sử.
- Clock skew ảnh hưởng metric latency.
- API đọc ngay sau write trong khi projection chưa cập nhật.
- Reconciliation phát hiện và sửa projection sai lệch.

Đo p50, p95, p99, oldest event age, backlog và thời gian hội tụ. Kiểm tra cả lúc tải bình thường lẫn tải đỉnh. SLO nên được đánh giá theo từng consumer, không gộp các luồng có yêu cầu khác nhau.

## 16. Checklist thiết kế độ trễ đồng bộ

- [ ] Đã xác định nguồn sở hữu dữ liệu cho mỗi domain.
- [ ] Đã phân loại dữ liệu cần nhất quán mạnh và eventual.
- [ ] Đã đặt staleness budget, target và ngưỡng cảnh báo theo consumer.
- [ ] Đã đo latency từ commit đến dữ liệu đích có thể đọc.
- [ ] Có eventId, correlationId và metadata thời gian phù hợp.
- [ ] Publication Registry được cấu hình bền vững khi cần phục hồi.
- [ ] Outbox được dùng cho ý định gửi message ra broker khi cần atomic write.
- [ ] Projection có idempotency và quy tắc version/sequence.
- [ ] Có cách xử lý read-after-write trong API và giao diện.
- [ ] Retry có backoff, jitter và giới hạn.
- [ ] Có metric backlog, oldest event age và projection freshness.
- [ ] Có reconciliation hoặc rebuild cho projection sai lệch.
- [ ] Replay không lặp tác dụng phụ ngoài ý muốn.
- [ ] Đã kiểm thử consumer chậm, restart, redelivery và event sai thứ tự.
- [ ] Có cảnh báo và runbook khi vượt ngân sách độ trễ.

## 17. Nguyên tắc vận hành

Độ trễ đồng bộ cần được xem là một thuộc tính có hợp đồng của từng luồng event. Hãy quyết định dữ liệu nào được phép cũ, trong bao lâu và người dùng sẽ nhìn thấy trạng thái đó thế nào. Đo thời gian từ transaction commit đến khi dữ liệu đích thực sự có thể đọc, đồng thời theo dõi backlog, retry và tuổi event cũ nhất.

Trong Spring Modulith, application events và Event Publication Registry hỗ trợ giao tiếp giữa module và theo dõi publication. Với hệ thống đọc bất đồng bộ, projection cần idempotency, versioning, cơ chế rebuild và reconciliation. Khi ngân sách độ trễ, quan sát và phục hồi được thiết kế rõ, hệ thống có thể chấp nhận eventual consistency mà vẫn giữ trải nghiệm người dùng và quy tắc nghiệp vụ đáng tin cậy.
