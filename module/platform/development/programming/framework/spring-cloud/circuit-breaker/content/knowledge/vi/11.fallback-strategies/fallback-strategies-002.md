# Trả dữ liệu đã lưu với dấu hiệu độ mới rõ ràng

Khi một dịch vụ phụ thuộc chậm hoặc tạm thời không khả dụng, circuit breaker có thể ngừng gửi thêm lời gọi và chuyển việc xử lý sang fallback. Với những chức năng đọc dữ liệu, một fallback hữu ích là trả bản dữ liệu đã lưu trong cache, nếu bản đó vẫn nằm trong giới hạn độ cũ mà nghiệp vụ chấp nhận.

Dữ liệu cache có thể giúp màn hình tiếp tục hiển thị thông tin và giảm tác động của sự cố phụ thuộc. Tuy nhiên, dữ liệu cũ phải được nhận diện rõ. Người dùng và các thành phần gọi API cần biết dữ liệu được cập nhật vào thời điểm nào, đã cũ bao lâu và có thể sử dụng cho mục đích nào. Một phản hồi có vẻ bình thường nhưng âm thầm chứa dữ liệu cũ có thể dẫn đến quyết định sai.

## Vì sao cần thể hiện độ mới của dữ liệu?

Giả sử dịch vụ đặt hàng gọi dịch vụ tồn kho để hiển thị số lượng sản phẩm. Dịch vụ tồn kho gặp sự cố trong vài phút. Nếu ứng dụng có bản tồn kho gần nhất trong cache, nó có thể tiếp tục hiển thị dữ liệu tham khảo thay vì trả trang lỗi hoàn toàn.

Nhưng số lượng tồn kho đã lưu có thể không còn đúng. Một đơn hàng khác có thể đã giữ chỗ sản phẩm sau thời điểm bản cache được tạo. Vì vậy, phản hồi dự phòng cần thể hiện rõ rằng dữ liệu là bản gần nhất đã biết, không phải số lượng hiện tại được xác nhận từ dịch vụ nguồn.

Một phản hồi có thông tin độ mới giúp:

- Người dùng nhận biết dữ liệu đang xem là mới hay cũ.
- Frontend có thể hiển thị nhãn cảnh báo hoặc giới hạn thao tác dựa trên độ tin cậy của dữ liệu.
- Dịch vụ gọi có thể quyết định có tiếp tục xử lý hay yêu cầu xác nhận lại.
- Nhóm vận hành đo được số phản hồi dùng dữ liệu cũ và thời gian dữ liệu đã cũ.
- Hệ thống tránh nhầm lẫn giữa dữ liệu không tồn tại và dữ liệu tạm thời không thể lấy được.

Fallback bằng cache phù hợp nhất với truy vấn đọc có thể chấp nhận một mức độ trễ dữ liệu nhất định. Nó không phải cơ chế xác nhận giao dịch và không đảm bảo bản cache phản ánh trạng thái hiện tại của hệ thống nguồn.

## Phân biệt thời điểm nguồn cập nhật và thời điểm cache lưu dữ liệu

Để đánh giá độ mới chính xác, cần phân biệt ít nhất hai mốc thời gian:

| Mốc thời gian | Ý nghĩa | Dùng để |
|---|---|---|
| sourceAsOf | Thời điểm dữ liệu phản ánh trạng thái ở hệ thống nguồn. | Tính tuổi thực tế của dữ liệu. |
| cachedAt | Thời điểm bản dữ liệu được ghi vào cache hiện tại. | Chẩn đoán cache, thời gian đồng bộ và làm mới. |

Không được dùng cachedAt thay cho sourceAsOf khi tính độ cũ. Ví dụ, một tác vụ đồng bộ có thể đọc lại bản dữ liệu đã cũ từ một nguồn trung gian rồi ghi nó vào cache lúc 10:05. Nếu chỉ nhìn cachedAt, ứng dụng có thể nghĩ dữ liệu mới vài giây dù trạng thái nguồn thực tế đã cũ từ 09:20.

Tuổi dữ liệu nên được tính từ thời điểm nguồn mà dữ liệu đại diện:

~~~java
Duration age = Duration.between(snapshot.sourceAsOf(), clock.instant());
~~~

Nếu timestamp nguồn nằm trong tương lai so với đồng hồ ứng dụng, có thể có sai lệch đồng hồ hoặc dữ liệu không hợp lệ. Không nên âm thầm coi dữ liệu đó là mới; hãy kiểm tra và từ chối bản ghi không hợp lệ hoặc áp dụng chính sách đồng bộ thời gian phù hợp.

Một mô hình dữ liệu có thể lưu cả hai mốc:

~~~java
public record InventorySnapshot(
        String sku,
        int available,
        Instant sourceAsOf,
        Instant cachedAt
) {
}
~~~

sourceAsOf nên do hệ thống nguồn hoặc quy trình đồng bộ đáng tin cậy cung cấp. Nếu không thể có timestamp nguồn, cần ghi rõ rằng tuổi dữ liệu chỉ được ước lượng từ thời điểm quan sát hoặc đồng bộ, và không nên mô tả nó như thời điểm cập nhật chính xác tại nguồn.

## Đặt giới hạn tuổi dữ liệu được phép dùng

Không phải bản cache nào cũng nên được trả về. Hãy xác định hai khoảng thời gian:

- **Fresh TTL:** khoảng thời gian bản cache được xem là mới theo chính sách thông thường.
- **Maximum stale age:** tuổi tối đa mà dữ liệu vẫn có thể được trả như một phương án dự phòng.

Ví dụ, thông tin danh mục sản phẩm có thể được xem là mới trong 10 phút và được phép hiển thị bản cũ tối đa 24 giờ. Số lượng tồn kho có thể chỉ được phép dùng bản dự phòng trong 30 giây cho màn hình tham khảo, còn thao tác giữ chỗ luôn phải xác nhận trực tiếp từ dịch vụ nguồn.

| Loại dữ liệu | Fresh TTL minh họa | Maximum stale age minh họa | Cách sử dụng |
|---|---:|---:|---|
| Mô tả sản phẩm | 10 phút | 24 giờ | Có thể hiển thị bản cũ kèm thời điểm cập nhật. |
| Danh mục và bộ lọc | 5 phút | 2 giờ | Có thể tiếp tục duyệt với cảnh báo dữ liệu cũ. |
| Tỷ giá tham khảo | 1 phút | 5 phút | Cần hiển thị thời điểm và không dùng để chốt giao dịch nếu nghiệp vụ yêu cầu tỷ giá mới. |
| Số lượng tồn kho tham khảo | 15 giây | 30 giây | Chỉ dùng để hiển thị; xác nhận lại trước khi giữ chỗ. |
| Trạng thái thanh toán hoặc quyền truy cập | Theo chính sách nguồn | Không dùng stale fallback nếu chưa có phê duyệt nghiệp vụ | Cần trạng thái được xác nhận từ nguồn có thẩm quyền. |

Các khoảng thời gian trên chỉ là ví dụ. Chủ sở hữu nghiệp vụ cần quyết định mức độ cũ tối đa dựa trên tốc độ thay đổi của dữ liệu và hậu quả khi người dùng hành động theo dữ liệu cũ.

Không nên dùng một maximum stale age chung cho mọi loại dữ liệu. Dữ liệu mô tả ít thay đổi có thể chịu được nhiều giờ, trong khi dữ liệu tồn kho, giá hoặc quyền truy cập có thể cần giới hạn rất ngắn hoặc không được phép dùng khi nguồn không sẵn sàng.

## Trả dữ liệu cùng metadata độ mới

API nên thể hiện trạng thái dữ liệu một cách rõ ràng. Có thể dùng các trạng thái như:

| freshness | Ý nghĩa | Hành vi phía client |
|---|---|---|
| FRESH | Dữ liệu vừa được lấy thành công từ nguồn hoặc còn trong thời hạn mới theo chính sách. | Hiển thị bình thường. |
| STALE | Dữ liệu được lấy từ cache vì không thể lấy dữ liệu mới; vẫn nằm trong maximum stale age. | Hiển thị nhãn dữ liệu cũ và thời điểm nguồn cập nhật. |
| UNAVAILABLE | Không có dữ liệu cache phù hợp hoặc bản cache đã quá cũ. | Hiển thị trạng thái chưa thể tải dữ liệu; không giả định giá trị mặc định là đúng. |
| NOT_FOUND | Nguồn xác nhận dữ liệu không tồn tại. | Hiển thị kết quả không tồn tại theo nghiệp vụ. |

Một response DTO có thể bao gồm dữ liệu, trạng thái freshness, thời điểm nguồn cập nhật và tuổi dữ liệu:

~~~json
{
  "sku": "SKU-1024",
  "available": 12,
  "freshness": "STALE",
  "sourceAsOf": "2026-11-24T09:58:00Z",
  "ageSeconds": 420,
  "message": "Đang hiển thị dữ liệu gần nhất đã lưu"
}
~~~

Đây là dữ liệu minh họa. Với response thực tế, cần thống nhất tên field, múi giờ và định dạng timestamp. Nên trả timestamp có múi giờ rõ ràng, thường là UTC, và để client định dạng theo múi giờ của người dùng.

Không nên chỉ trả một boolean như stale=true nếu người gọi cần biết dữ liệu cũ bao lâu. Có thể cung cấp freshness, sourceAsOf, ageSeconds và maximumStaleAgeSeconds. Tuy nhiên, chỉ đưa những metadata có ý nghĩa cho client; không cần để lộ chi tiết exception nội bộ hoặc địa chỉ dịch vụ phụ thuộc.

## Tích hợp cache fallback với Spring Cloud CircuitBreaker

Ví dụ sau minh họa một client đọc tồn kho. Lời gọi được bảo vệ bởi circuit breaker có ID inventory-read. Khi lấy dữ liệu mới thành công, ứng dụng lưu snapshot vào cache. Khi lời gọi lỗi hoặc mạch đang OPEN, fallback tìm snapshot gần nhất và chỉ trả nó nếu chưa vượt maximum stale age.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryQueryService {

    private final InventoryClient inventoryClient;
    private final InventoryCache inventoryCache;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final Clock clock;

    private final Duration maximumStaleAge = Duration.ofSeconds(30);

    public InventoryQueryService(
            InventoryClient inventoryClient,
            InventoryCache inventoryCache,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            Clock clock) {
        this.inventoryClient = inventoryClient;
        this.inventoryCache = inventoryCache;
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.clock = clock;
    }

    public InventoryResult find(String sku) {
        return circuitBreakerFactory.create("inventory-read").run(
                () -> fetchAndCache(sku),
                error -> staleOrUnavailable(sku, error)
        );
    }

    private InventoryResult fetchAndCache(String sku) {
        InventorySnapshot snapshot = inventoryClient.fetch(sku);
        inventoryCache.put(sku, snapshot);
        return InventoryResult.fresh(snapshot, ageOf(snapshot));
    }

    private InventoryResult staleOrUnavailable(
            String sku,
            Throwable failure) {

        if (failure instanceof ProductNotFoundException) {
            return InventoryResult.notFound(sku);
        }

        Instant now = clock.instant();

        Optional<InventorySnapshot> cached =
                inventoryCache.find(sku)
                        .filter(snapshot ->
                                !snapshot.sourceAsOf().isAfter(now))
                        .filter(snapshot ->
                                Duration.between(snapshot.sourceAsOf(), now)
                                        .compareTo(maximumStaleAge) <= 0);

        return cached
                .map(snapshot -> InventoryResult.stale(
                        snapshot,
                        Duration.between(snapshot.sourceAsOf(), now)
                ))
                .orElseGet(() -> InventoryResult.unavailable(sku));
    }

    private Duration ageOf(InventorySnapshot snapshot) {
        return Duration.between(snapshot.sourceAsOf(), clock.instant());
    }
}
~~~

InventoryClient, InventoryCache, InventorySnapshot và InventoryResult là các thành phần minh họa của ứng dụng. Trong triển khai thực tế, cần bổ sung các import, kiểu dữ liệu và chính sách phân loại ngoại lệ phù hợp với dự án.

Ví dụ cho thấy một số quyết định quan trọng:

- Dữ liệu mới chỉ được ghi cache sau khi lời gọi nguồn hoàn tất thành công.
- Fallback không tự tạo một số lượng tồn kho giả định.
- Dữ liệu có sourceAsOf ở tương lai bị loại khỏi cache fallback.
- Dữ liệu quá maximumStaleAge bị từ chối.
- ProductNotFoundException được chuyển thành NOT_FOUND thay vì dùng bản cache cũ để che giấu kết quả không tồn tại.
- Nếu không có bản cache phù hợp, API trả UNAVAILABLE.

Trong ứng dụng thực tế, hãy phân loại lỗi trước khi trả cache. Không nên trả dữ liệu cũ cho mọi Throwable. Lỗi xác thực, dữ liệu đầu vào không hợp lệ, lỗi lập trình hoặc lỗi nghiệp vụ có thể cần được xử lý theo quy tắc riêng. Chỉ những tình huống nguồn tạm thời không sẵn sàng hoặc circuit breaker từ chối lời gọi mới nên kích hoạt chính sách stale fallback.

## Fallback chỉ nên phục vụ mục đích đọc phù hợp

Một bản cache cũ có thể hữu ích cho truy vấn hiển thị nhưng không an toàn cho thao tác ghi hoặc quyết định không thể đảo ngược.

Ví dụ với tồn kho:

- Trang chi tiết sản phẩm có thể hiển thị số lượng gần nhất đã biết, kèm nhãn STALE.
- Giỏ hàng có thể hiển thị thông tin tham khảo và yêu cầu kiểm tra lại trước khi đặt hàng.
- Thao tác giữ chỗ hoặc trừ tồn kho cần gọi dịch vụ có thẩm quyền và xác nhận kết quả thực tế.
- Không được xem dữ liệu cache là bằng chứng giao dịch đã thành công.

Với thanh toán, quyền truy cập, số dư hoặc trạng thái đơn hàng, dữ liệu cũ có thể gây ra hậu quả nghiêm trọng. Nếu nghiệp vụ không chấp nhận stale data, fallback nên trả trạng thái UNAVAILABLE hoặc yêu cầu thử lại khi nguồn phục hồi. Không nên dùng giá trị mặc định như 0, true hoặc false để giả lập kết quả đã xác nhận.

## Stale-while-revalidate và làm mới dữ liệu

Một chiến lược có thể dùng là stale-while-revalidate: khi bản cache đã hết Fresh TTL nhưng vẫn nằm trong Maximum stale age, ứng dụng trả dữ liệu cũ ngay và khởi chạy một tác vụ làm mới ở nền.

Luồng khái quát:

~~~mermaid
flowchart TD
    A[Yêu cầu đọc dữ liệu] --> B{Cache còn fresh?}
    B -->|Có| C[Trả dữ liệu FRESH]
    B -->|Không| D{Nguồn đang sẵn sàng?}
    D -->|Có| E[Gọi nguồn và cập nhật cache]
    E --> F[Trả dữ liệu mới]
    D -->|Không| G{Bản cache trong maximum stale age?}
    G -->|Có| H[Trả dữ liệu STALE]
    G -->|Không| I[Trả UNAVAILABLE]
    H --> J[Tác vụ làm mới có giới hạn]
~~~

Không phải mọi fallback đều cần stale-while-revalidate. Với một ứng dụng đơn giản, chỉ cần trả bản cache còn trong giới hạn và để request tiếp theo thử lấy dữ liệu mới. Nếu triển khai làm mới nền, cần có giới hạn đồng thời, timeout, retry có kiểm soát và cơ chế tránh nhiều request cùng làm mới một cache key.

Các biện pháp chống cache stampede:

- Dùng single-flight hoặc distributed lock phù hợp để gộp các yêu cầu làm mới cùng key.
- Giới hạn số tác vụ refresh đồng thời.
- Đặt timeout và circuit breaker riêng cho lời gọi refresh.
- Dùng jitter cho thời điểm hết hạn để tránh nhiều key cùng hết TTL.
- Không cho phép hàng đợi refresh tăng không giới hạn.
- Nếu refresh thất bại, giữ nguyên sourceAsOf cũ; không cập nhật timestamp nguồn chỉ vì đã thử làm mới.

Làm mới nền không được làm thay đổi metadata freshness trước khi nhận được dữ liệu mới hợp lệ. Nếu tác vụ refresh chỉ lấy lại bản cũ từ nguồn trung gian, sourceAsOf vẫn phải phản ánh thời điểm dữ liệu thực sự được cập nhật.

## Xử lý cache miss, cache lỗi và bản ghi quá cũ

Fallback phụ thuộc vào cache nên cache cũng cần có chính sách lỗi rõ ràng. Một số tình huống thường gặp:

| Tình huống | Cách xử lý |
|---|---|
| Không có cache entry | Trả UNAVAILABLE hoặc trạng thái phù hợp; không tự tạo dữ liệu giả. |
| Cache entry còn trong maximum stale age | Trả STALE cùng metadata độ mới. |
| Cache entry quá cũ | Không trả nội dung; trả UNAVAILABLE. |
| Cache không truy cập được | Ghi nhận lỗi cache và trả trạng thái suy giảm phù hợp. |
| Timestamp nguồn thiếu hoặc không hợp lệ | Không xem dữ liệu là fresh; chỉ dùng nếu có chính sách ước lượng rõ ràng. |
| Cache chứa phiên bản thấp hơn phiên bản đã biết | Không ghi đè dữ liệu mới hơn bằng snapshot cũ. |

Nếu cache là một phụ thuộc riêng như Redis, việc cache không truy cập được có thể khiến fallback cũng thất bại. Cần quyết định ứng dụng sẽ trả lỗi kiểm soát, dữ liệu cục bộ trong bộ nhớ nếu có, hay một phản hồi UNAVAILABLE. Không nên giả định rằng fallback luôn thành công chỉ vì đã viết hàm fallback.

Với nhiều replica, cache phân tán có thể dùng chung dữ liệu nhưng vẫn cần chính sách đồng bộ và nhất quán. Nếu dùng cache cục bộ, mỗi replica có thể có snapshot khác nhau và độ mới khác nhau. Metadata sourceAsOf giúp caller và nhóm vận hành nhìn thấy sự khác biệt này.

## Bảo vệ tính nhất quán khi cập nhật dữ liệu

Khi dữ liệu nguồn thay đổi, cache có thể bị lỗi thời ngay lập tức. Với các thao tác ghi, hãy cập nhật hoặc vô hiệu hóa cache theo quy tắc nhất quán của nghiệp vụ. Nếu không thể cập nhật cache ngay, metadata phải tiếp tục thể hiện sourceAsOf cũ cho đến khi có xác nhận mới.

Có thể dùng version hoặc sequence number từ nguồn để tránh ghi đè snapshot mới bằng một sự kiện đến trễ. Ví dụ, nếu cache đang giữ version 42, một tác vụ đồng bộ đến sau với version 41 không được thay thế nó. Timestamp có thể hữu ích nhưng version từ nguồn thường đáng tin cậy hơn khi cần xác định thứ tự cập nhật.

Đối với dữ liệu nhiều phần, cần xác định sourceAsOf đại diện cho toàn bộ snapshot hay từng trường. Không nên ghép các trường từ những thời điểm khác nhau rồi công bố một timestamp duy nhất như thể chúng tạo thành một bản chụp nhất quán.

## Quan sát chất lượng của stale fallback

Ngoài trạng thái circuit breaker, hãy đo xem fallback có thực sự giúp ứng dụng phục vụ tốt hơn hay chỉ đang che giấu sự cố.

Các chỉ số nên theo dõi:

- Số phản hồi FRESH, STALE và UNAVAILABLE theo từng loại dữ liệu.
- Tuổi dữ liệu tại thời điểm được trả về, đặc biệt là p95 và p99 của ageSeconds.
- Số cache miss và số bản ghi bị từ chối vì quá maximum stale age.
- Tỷ lệ fallback trên tổng số yêu cầu đọc.
- Số lần circuit breaker OPEN và số lần lời gọi bị từ chối.
- Số tác vụ refresh thành công, thất bại, bị giới hạn hoặc bị gộp.
- Tỷ lệ dữ liệu cũ được dùng trong các thao tác tiếp theo, nếu nghiệp vụ có thể đo được.

Nhãn metrics nên có miền giá trị giới hạn, chẳng hạn tên phụ thuộc, loại dữ liệu và trạng thái freshness. Không gắn SKU, user ID hoặc order ID vào nhãn vì cardinality có thể tăng rất nhanh. Các ID chi tiết có thể được ghi trong log hoặc trace theo chính sách dữ liệu của hệ thống.

Cảnh báo nên dựa trên cả tần suất và tuổi dữ liệu. Một tỷ lệ STALE cao trong thời gian ngắn có thể chấp nhận khi dịch vụ nguồn vừa có sự cố, nhưng nếu tuổi dữ liệu liên tục tiến gần maximum stale age thì cần cảnh báo trước khi cache không còn đủ điều kiện phục vụ.

## Kiểm thử fallback có dấu hiệu độ mới

Nên kiểm thử cả trường hợp cache có dữ liệu và không có dữ liệu:

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Lời gọi nguồn thành công | Trả FRESH và cập nhật cache với sourceAsOf đúng. |
| Nguồn lỗi, cache còn trong giới hạn | Trả STALE, giữ nguyên sourceAsOf và tính age chính xác. |
| Nguồn lỗi, cache quá cũ | Trả UNAVAILABLE, không trả dữ liệu quá hạn. |
| Nguồn lỗi, cache miss | Trả UNAVAILABLE. |
| Cache có timestamp tương lai | Từ chối snapshot hoặc xử lý theo chính sách sai lệch đồng hồ. |
| Sản phẩm không tồn tại | Trả NOT_FOUND; không che giấu bằng snapshot cũ. |
| Mạch OPEN | Không gọi nguồn; fallback chỉ dùng cache đủ điều kiện. |
| Cache không truy cập được | Trả trạng thái suy giảm có kiểm soát và ghi nhận lỗi cache. |
| Hai refresh đồng thời cùng key | Xác nhận cơ chế single-flight hoặc giới hạn đồng thời hoạt động. |
| Snapshot cũ đến sau snapshot mới | Không ghi đè phiên bản mới hơn. |

Dùng Clock có thể thay thế trong kiểm thử để điều khiển thời gian mà không phải chờ TTL thật. Kiểm tra sourceAsOf và cachedAt riêng biệt để chắc chắn rằng một lần ghi cache lại không làm dữ liệu cũ trở thành mới trên danh nghĩa.

## Quy trình thiết kế

1. Xác định chức năng đọc nào có thể tiếp tục với dữ liệu cũ và chức năng nào cần dữ liệu hiện tại được xác nhận.
2. Định nghĩa Fresh TTL và Maximum stale age riêng theo loại dữ liệu.
3. Lưu sourceAsOf cùng cachedAt và, nếu có, version từ hệ thống nguồn.
4. Trả metadata freshness trong response để caller biết dữ liệu FRESH, STALE hay UNAVAILABLE.
5. Chỉ dùng cache fallback cho lỗi phụ thuộc tạm thời hoặc circuit breaker từ chối; xử lý lỗi nghiệp vụ riêng.
6. Không trả snapshot quá cũ, timestamp không hợp lệ hoặc phiên bản thấp hơn dữ liệu mới hơn.
7. Nếu dùng refresh nền, giới hạn đồng thời và ngăn cache stampede.
8. Theo dõi tuổi dữ liệu, tỷ lệ stale fallback, cache miss và trạng thái circuit breaker.
9. Kiểm thử cả trường hợp nguồn lỗi, cache lỗi, cache quá hạn và dữ liệu không tồn tại.

Trả dữ liệu đã lưu là một cách duy trì khả năng đọc khi dịch vụ phụ thuộc gặp sự cố. Giá trị của chiến lược này phụ thuộc vào việc giới hạn tuổi dữ liệu và công khai độ mới một cách rõ ràng. Khi caller biết dữ liệu được cập nhật lúc nào và đã cũ bao lâu, ứng dụng có thể tiếp tục phục vụ các chức năng phù hợp mà vẫn giữ được sự minh bạch về độ tin cậy của thông tin.

