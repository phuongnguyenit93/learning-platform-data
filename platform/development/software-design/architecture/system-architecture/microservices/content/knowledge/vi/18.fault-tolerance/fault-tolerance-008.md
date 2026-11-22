# Phương án dự phòng và suy giảm tính năng có thể chấp nhận trong Microservices

Trong kiến trúc microservices, một yêu cầu từ người dùng thường đi qua nhiều dịch vụ: danh mục, giá, tồn kho, thanh toán, tìm kiếm, đề xuất, thông báo… Chỉ một dịch vụ phụ thuộc bị chậm hoặc ngừng hoạt động cũng có thể làm toàn bộ luồng thất bại nếu hệ thống coi mọi chức năng đều bắt buộc.

**Fallback (phương án dự phòng)** là hành vi thay thế khi cách xử lý chính không khả dụng, chẳng hạn dùng dữ liệu cache còn hợp lệ, chuyển sang nhà cung cấp phụ, hoặc ẩn một thành phần không thiết yếu. **Graceful degradation (suy giảm tính năng có kiểm soát)** là cách hệ thống tiếp tục cung cấp phần giá trị cốt lõi với mức chức năng hoặc chất lượng thấp hơn, trong giới hạn nghiệp vụ đã chấp nhận. Fallback là một trong những kỹ thuật để đạt graceful degradation.

Mục tiêu không phải là “bằng mọi giá trả HTTP 200”. Mục tiêu là **giữ đúng cam kết nghiệp vụ, tránh gây hại và cô lập lỗi**, đồng thời để người dùng và đội vận hành biết phần nào đang suy giảm.

## 1. Vì sao cần phương án dự phòng?

Giả sử trang chi tiết sản phẩm gọi ba dịch vụ:

- **Catalog Service**: thông tin sản phẩm chính.
- **Recommendation Service**: danh sách sản phẩm gợi ý.
- **Review Service**: nhận xét và điểm đánh giá.

Nếu Recommendation Service bị timeout, trang vẫn có thể hiển thị sản phẩm, giá và nút thao tác chính; phần gợi ý dùng cache phù hợp hoặc tạm ẩn. Nếu toàn bộ trang trả lỗi chỉ vì thiếu gợi ý, lỗi nhỏ đã lan thành sự cố lớn.

Nhưng với luồng xác nhận đơn hàng, **giá, tồn kho, quyền mua và kết quả thanh toán** có thể là dữ liệu bắt buộc. Không được dùng một con số mặc định để giả vờ xác thực thành công. Phương án dự phòng chỉ hợp lệ khi hệ thống vẫn bảo toàn tính đúng đắn của nghiệp vụ.

Có ba khả năng cần phân biệt:

1. **Full service**: dữ liệu và chức năng chính/phụ đều đáp ứng bình thường.
2. **Degraded service**: luồng cốt lõi vẫn đúng, một số chức năng phụ bị thay thế, làm chậm hoặc ẩn đi.
3. **Unavailable / fail safely**: không thể xác nhận điều kiện cốt lõi; hệ thống từ chối hoặc đánh dấu chờ xử lý một cách minh bạch.

## 2. Phân biệt các cơ chế chịu lỗi liên quan

| Cơ chế | Mục đích | Ví dụ |
| --- | --- | --- |
| Timeout / deadline | Giới hạn thời gian chờ phụ thuộc | Ngừng chờ dịch vụ gợi ý sau 180 ms |
| Retry có giới hạn | Thử lại lỗi tạm thời khi thao tác an toàn | Thử lại một lần truy vấn đọc với backoff và jitter |
| Circuit breaker | Ngừng gửi yêu cầu đến phụ thuộc đang lỗi nhiều | Mở mạch, trả kết quả dự phòng ngay |
| Bulkhead / giới hạn đồng thời | Tránh một phụ thuộc dùng hết tài nguyên chung | Dành pool riêng cho tìm kiếm và thanh toán |
| Failover | Chuyển sang instance, vùng hoặc nhà cung cấp thay thế | Đọc từ replica đủ điều kiện |
| Fallback | Cung cấp kết quả hoặc hành động thay thế | Dùng cache hợp lệ, danh sách mặc định hoặc ẩn gợi ý |
| Graceful degradation | Chính sách dịch vụ ở mức chất lượng thấp hơn | Trang vẫn xem được nhưng thiếu gợi ý cá nhân hóa |

Các cơ chế phối hợp với nhau. Timeout, bulkhead và circuit breaker bảo vệ tài nguyên; fallback quyết định **trả gì hoặc làm gì** sau khi phát hiện lỗi; chính sách degradation quyết định **chức năng nào được phép yếu đi**.

**Lưu ý:** Failover không tự động an toàn. Bản sao có thể trễ dữ liệu; nhà cung cấp thanh toán thứ hai có thể tạo giao dịch trùng nếu kết quả giao dịch đầu chưa rõ.

## 3. Xác định “có thể chấp nhận” theo nghiệp vụ

Trước khi viết fallback, phân loại từng phụ thuộc theo tầm quan trọng, ràng buộc dữ liệu và hậu quả của kết quả sai.

| Chức năng/phụ thuộc | Cách xử lý khi lỗi có thể chấp nhận | Điều không được làm |
| --- | --- | --- |
| Gợi ý sản phẩm | Cache trong thời hạn cho phép hoặc ẩn khối gợi ý | Trả dữ liệu của người dùng khác |
| Nhận xét, thống kê hiển thị | Ẩn hoặc hiển thị số liệu cache với nhãn phù hợp | Trình bày số liệu quá cũ như thời gian thực |
| Tìm kiếm | Giảm tính năng xếp hạng nâng cao; trả kết quả cơ bản nếu còn đúng | Tạo kết quả giả hoặc vượt quyền truy cập |
| Dự kiến giao hàng | Hiển thị “chưa thể ước tính” và cho xem hàng | Cam kết thời gian giao không có căn cứ |
| Giá cuối cùng, thuế, khuyến mãi khi chốt đơn | Chặn xác nhận, yêu cầu thử lại khi xác minh được | Dùng giá mặc định hoặc cache đã hết hiệu lực |
| Tồn kho/đặt chỗ | Chỉ xác nhận sau khi cơ chế giữ hàng có thẩm quyền thành công | Nói “đã giữ hàng” khi chưa giữ được |
| Đăng nhập, phân quyền, kiểm tra gian lận bắt buộc | Fail closed: từ chối thao tác cần bảo vệ | Tự động cho phép vì dịch vụ bảo mật lỗi |
| Thanh toán | Tra cứu trạng thái theo mã giao dịch/idempotency key; giữ trạng thái “đang xác minh” nếu chưa rõ | Coi timeout là thanh toán thất bại chắc chắn, rồi thu tiền lần hai |
| Gửi email thông báo không đồng bộ | Xếp hàng bền vững để gửi sau, nếu yêu cầu đã được nhận an toàn | Báo “đã gửi” khi mới lưu hàng đợi |

Thời hạn cache như 5 phút hay 6 giờ **chỉ là ví dụ thiết kế**, không phải chuẩn chung. Từng miền nghiệp vụ phải phê duyệt độ cũ tối đa, nguồn dữ liệu, đối tượng được phép xem và cách thông báo.

Một phép thử quan trọng: **Nếu fallback trả về dữ liệu không hoàn toàn mới, người dùng có thể đưa ra quyết định sai, bị tính tiền sai, thấy dữ liệu không được phép, hoặc tin rằng một thao tác đã hoàn tất hay không?** Nếu có, phải thu hẹp fallback hoặc từ chối an toàn.

## 4. Những chiến lược fallback phổ biến

### 4.1. Dữ liệu cache còn hợp lệ

Dùng bản sao gần đây cho dữ liệu ít nhạy cảm với độ mới, ví dụ ảnh sản phẩm, gợi ý chung hoặc thống kê đã được phép trễ.

- Định nghĩa **maximum staleness** cho từng loại dữ liệu; kiểm tra tuổi bản ghi trước khi dùng.
- Bảo toàn phạm vi quyền: cache key phải phản ánh tenant, người dùng hoặc phân khúc khi kết quả có phân quyền.
- Ghi nhận nguồn dữ liệu là CACHED, thời điểm cập nhật và nguyên nhân fallback.
- Có cách xử lý cache miss, cache lỗi hoặc dữ liệu quá hạn; không “lùi mãi” sang bản sao ngày càng cũ.
- Tránh cache stampede: hạn chế số yêu cầu cùng làm mới một khóa và không đánh sập nguồn dữ liệu khi nó vừa phục hồi.

### 4.2. Giá trị mặc định hoặc nội dung tĩnh

Dùng tập danh mục gợi ý phổ biến, thông điệp chung hoặc giao diện giản lược. Giá trị mặc định phải có **ý nghĩa nghiệp vụ rõ ràng**. Danh sách gợi ý rỗng có thể hợp lệ; giá bằng 0, tồn kho “còn hàng” hoặc quyền truy cập “được phép” thường không hợp lệ.

Không dùng cùng một fallback chung cho mọi lỗi. Một ID sản phẩm không tồn tại (404 hợp lệ) không đồng nghĩa dịch vụ sản phẩm bị hỏng; người dùng không đủ quyền (403) không thể được “cứu” bằng dữ liệu dự phòng.

### 4.3. Bỏ qua một tính năng tùy chọn

Ẩn widget gợi ý, bộ lọc nâng cao, biểu đồ hoặc tính năng cá nhân hóa khi dịch vụ tương ứng bị lỗi. Đây thường là fallback rẻ và dễ kiểm soát nhất.

API có thể trả phần dữ liệu cốt lõi cùng trạng thái suy giảm của từng thành phần. Giao diện chỉ nên hiển thị thông báo khi nó giúp người dùng hiểu một giới hạn thực sự; không cần phát cảnh báo kỹ thuật cho mọi widget bị ẩn.

### 4.4. Chuyển sang nguồn/phương thức thay thế

Ví dụ chuyển từ thuật toán đề xuất theo hành vi sang danh sách phổ biến, hoặc từ cơ chế tìm kiếm nâng cao sang truy vấn cơ bản. Phải kiểm soát độ tương đương của dữ liệu, định dạng, bảo mật, chi phí và tải lên phương thức thay thế.

Với nguồn phụ/replica, cần biết độ trễ đồng bộ và khả năng đọc nhất quán. Không giả định mọi replica phù hợp cho giá cuối cùng hay trạng thái thanh toán.

### 4.5. Xử lý trễ, hàng đợi và chế độ chỉ đọc

Một thao tác không cần hoàn thành ngay có thể được nhận để xử lý sau **nếu đã ghi bền vững, có mã theo dõi, chính sách retry và xử lý trùng lặp**. HTTP 202 Accepted mô tả thao tác đã được nhận để xử lý, không có nghĩa tác vụ đã hoàn tất. Nếu không lưu được vào hàng đợi, không tuyên bố đã nhận thành công.

Trong sự cố ghi, một số hệ thống có thể tạm cho phép đọc nhưng ngừng ghi. Chế độ read-only phải thể hiện rõ và không cho phép UI tạo kỳ vọng rằng chỉnh sửa đã được lưu.

## 5. Thiết kế chính sách suy giảm theo từng năng lực

Thay vì một cờ “hệ thống đang lỗi”, định nghĩa trạng thái theo năng lực:

- **LIVE**: lấy từ phụ thuộc chính, đạt điều kiện bình thường.
- **CACHED**: lấy từ dữ liệu dự phòng trong giới hạn tuổi và quyền.
- **BASIC**: dùng thuật toán hoặc chức năng đơn giản hơn.
- **HIDDEN**: bỏ một khối tùy chọn khỏi phản hồi.
- **UNAVAILABLE**: năng lực cốt lõi không thể thực hiện an toàn.
- **PENDING**: tác vụ đã được tiếp nhận hợp lệ nhưng kết quả chưa hoàn tất hoặc chưa xác định.

Luồng xử lý cho một thành phần tùy chọn:

~~~text
Yêu cầu đến
  -> Kiểm tra deadline còn lại và giới hạn tải
  -> Gọi phụ thuộc chính (timeout/circuit breaker phù hợp)
       | thành công, dữ liệu hợp lệ -> LIVE
       | lỗi/chậm/mạch mở
       v
     Có cache hợp lệ, đúng quyền? -> CACHED
       | không
       v
     Có cách xử lý cơ bản an toàn? -> BASIC
       | không
       v
     Thành phần có thể bỏ qua? -> HIDDEN
       | không
       v
     Từ chối an toàn / trạng thái chưa xác định -> UNAVAILABLE hoặc PENDING
~~~

Thứ tự trên là khung ra quyết định; không bắt buộc mọi dịch vụ đều phải đi qua cache hay BASIC. Một chính sách tốt ghi rõ **điều kiện kích hoạt, hành vi thay thế, tuổi dữ liệu, thời hạn chờ, trạng thái API, nội dung UI, metric và điều kiện phục hồi** cho mỗi năng lực.

Tránh dây chuyền fallback vô hạn: dịch vụ A lỗi → gọi B → B lại gọi A. Đường dự phòng cần số bước và độ trễ có giới hạn, ít phụ thuộc hơn đường chính nếu có thể.

## 6. Ngân sách thời gian và ngăn lỗi lan truyền

Một fallback chỉ hữu ích nếu được kích hoạt **trước khi yêu cầu của người dùng hết thời gian**. Đặt deadline cho toàn bộ yêu cầu rồi phân bổ cho những bước thực sự cần thiết.

Ví dụ ngân sách minh họa cho trang sản phẩm tối đa 800 ms:

| Thành phần | Ngân sách tối đa minh họa |
| --- | ---: |
| Tra cứu sản phẩm cốt lõi | 350 ms |
| Gợi ý tùy chọn | 180 ms |
| Xử lý ứng dụng, mạng và phản hồi | 140 ms |
| Dự phòng dao động | 130 ms |
| **Tổng** | **800 ms** |

Khi 180 ms dành cho gợi ý đã hết, dùng phương án dự phòng ngay; không retry nhiều lần khiến tổng thời gian vượt 800 ms. Mỗi lời gọi phụ phải lấy phần ngân sách **còn lại** từ deadline chung, kể cả khi các lời gọi có thể chạy song song.

Nguyên tắc phối hợp:

1. **Timeout:** mỗi lời gọi ra ngoài có giới hạn thời gian.
2. **Retry:** chỉ retry lỗi đủ điều kiện, thao tác idempotent hoặc có khóa chống trùng; có số lần tối đa, backoff, jitter và nằm trong deadline chung.
3. **Circuit breaker:** khi phụ thuộc lỗi lặp lại, chuyển nhanh sang fallback; sau đó thử phục hồi có kiểm soát.
4. **Bulkhead / concurrency limit:** không để hàng nghìn yêu cầu chờ cùng một phụ thuộc làm cạn thread, connection hoặc queue.
5. **Rate limit / load shedding:** khi quá tải, ưu tiên đường cốt lõi và giảm tải tính năng tùy chọn.

Retry quá mạnh có thể biến một sự cố nhỏ thành bão yêu cầu. Một fallback cũng có thể gây quá tải mới nếu mỗi lần lỗi đều chạy truy vấn cơ sở dữ liệu đắt hơn. Vì vậy phải đo chi phí của **đường dự phòng**, không chỉ đường chính.

## 7. Ví dụ triển khai: trang sản phẩm trong Java

Giả sử trang sản phẩm **bắt buộc** lấy được Product từ Catalog Service, nhưng gợi ý là tùy chọn. Recommendation Client đã được cấu hình timeout, circuit breaker và ánh xạ lỗi kết nối/timeout/mạch mở thành RecommendationFailure. Cache chỉ trả các bản ghi còn trong ngưỡng tuổi cho phép.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Optional;

record Product(String id, String name) {}

enum RecommendationMode { LIVE, CACHED, HIDDEN }

record ProductPage(
    Product product,
    List<Product> recommendations,
    RecommendationMode recommendationMode
) {}

interface ProductClient {
    Product loadRequired(String productId);
}

interface RecommendationClient {
    List<Product> loadWithin(String productId, Duration budget);
}

interface RecommendationCache {
    Optional<List<Product>> findValid(
        String productId, Duration maxAge
    );
}

class RecommendationFailure extends RuntimeException {}

final class ProductPageService {
    private final ProductClient products;
    private final RecommendationClient recommendations;
    private final RecommendationCache cache;

    ProductPageService(
        ProductClient products,
        RecommendationClient recommendations,
        RecommendationCache cache
    ) {
        this.products = products;
        this.recommendations = recommendations;
        this.cache = cache;
    }

    ProductPage load(String productId) {
        Product product = products.loadRequired(productId);

        try {
            List<Product> live = recommendations.loadWithin(
                productId, Duration.ofMillis(180)
            );
            return new ProductPage(
                product, live, RecommendationMode.LIVE
            );
        } catch (RecommendationFailure ex) {
            return cache.findValid(productId, Duration.ofHours(6))
                .map(saved -> new ProductPage(
                    product, saved, RecommendationMode.CACHED
                ))
                .orElseGet(() -> new ProductPage(
                    product, List.of(), RecommendationMode.HIDDEN
                ));
        }
    }
}
~~~

**Ý nghĩa của ví dụ:**

- Catalog Service thất bại thì phương thức không tự dựng một sản phẩm giả. Tầng API phải xử lý lỗi này theo chính sách của luồng cốt lõi.
- Chỉ lỗi đã phân loại của Recommendation Service mới kích hoạt fallback; không bắt toàn bộ Exception rồi che mất lỗi lập trình, dữ liệu hoặc phân quyền.
- Cache là lựa chọn thay thế có kiểm tra tuổi; nếu không có cache hợp lệ, trả danh sách rỗng kèm HIDDEN.
- Tham số 180 ms và 6 giờ chỉ minh họa; thực tế phải ràng buộc deadline chung, SLA và quy tắc nghiệp vụ.
- Mã ví dụ tập trung vào chính sách fallback; cấu hình HTTP client, bộ ngắt mạch, trace, cache key theo quyền và logging thuộc các thành phần tích hợp thực tế.

Một phản hồi hợp lệ khi phần gợi ý bị ẩn có thể là:

~~~json
{
  "product": {
    "id": "p-42",
    "name": "Bình nước giữ nhiệt"
  },
  "recommendations": [],
  "degradation": {
    "recommendations": "HIDDEN"
  }
}
~~~

API có thể trả HTTP 200 vì **phần sản phẩm cốt lõi đã thành công**. Client dựa vào degradation.recommendations để ẩn vùng gợi ý hoặc hiển thị thông báo phù hợp. Không nên xuất thông tin nội bộ như stack trace, hostname hay chi tiết hạ tầng trong phản hồi cho người dùng.

## 8. Khi nào trả 200, 202, 503 hoặc lỗi nghiệp vụ?

Mã HTTP phải phản ánh kết quả **thực sự** của tác vụ:

- **200 OK:** phần dữ liệu/nghiệp vụ cốt lõi đã thành công; thành phần tùy chọn có thể CACHED, BASIC hoặc HIDDEN. Tình trạng degraded cần có dấu hiệu ở payload và metric.
- **202 Accepted:** thao tác bất đồng bộ đã được tiếp nhận bền vững để xử lý sau; cung cấp mã theo dõi và cách tra cứu. Không dùng 202 nếu chưa lưu thành công yêu cầu.
- **503 Service Unavailable:** dịch vụ hiện không cung cấp được năng lực cốt lõi vì phụ thuộc không khả dụng hoặc quá tải; có thể cung cấp Retry-After khi phù hợp.
- **4xx hợp lệ:** dữ liệu đầu vào sai, không đủ quyền, tài nguyên không tồn tại hoặc quy tắc nghiệp vụ từ chối. Không che lỗi này bằng fallback thành công.
- **Trạng thái kết quả chưa rõ:** ví dụ payment timeout sau khi gửi yêu cầu. Hệ thống ghi nhận trạng thái PENDING/UNKNOWN, tra soát bằng cùng idempotency key hoặc transaction ID và chỉ xác nhận khi có bằng chứng.

Đặc biệt với thanh toán: timeout **không chứng minh** giao dịch chưa được xử lý. Retry bằng yêu cầu mới không có khóa chống trùng có thể gây thu tiền hai lần. Failover sang nhà cung cấp khác cũng phải tuân thủ cơ chế chống giao dịch lặp và đối soát.

## 9. Quan sát và vận hành suy giảm tính năng

Fallback thành công ở cấp API không chứng tỏ hệ thống đang khỏe. Nếu 90% trang trả 200 nhưng toàn bộ gợi ý đã biến mất, khách hàng vẫn đang mất một phần giá trị dịch vụ.

Nên theo dõi ít nhất:

| Tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| Tỷ lệ phản hồi suy giảm theo từng năng lực | Bao nhiêu request đang ở CACHED/BASIC/HIDDEN? |
| Số lần fallback theo nguyên nhân | Lỗi do timeout, 5xx, 429, mạch mở hay cache miss? |
| Tuổi dữ liệu cache khi sử dụng | Nội dung dự phòng có tiến gần giới hạn cho phép? |
| p95/p99 latency, timeout, retry | Fallback có giữ được deadline và tránh retry storm? |
| Circuit breaker, bulkhead, queue | Phụ thuộc chính đang lỗi hay hệ thống dự phòng đang quá tải? |
| Tỷ lệ hoàn tất thao tác cốt lõi | Người dùng có còn xem hàng, đặt hàng hoặc thanh toán đúng không? |
| Chỉ số kinh doanh có liên quan | Việc ẩn gợi ý có làm giảm tìm kiếm, chuyển đổi hoặc doanh thu không? |

Log và trace nên gắn request/correlation ID, tên năng lực, mode và lý do suy giảm. Tránh dùng user ID, sản phẩm ID hay transaction ID có cardinality rất cao làm nhãn metric. Đặt cảnh báo theo cả **sức khỏe đường chính** lẫn **tỷ lệ rơi vào fallback**; chính sách SLO có thể tách trải nghiệm cốt lõi và trải nghiệm đầy đủ.

Khi phụ thuộc phục hồi, cho phép circuit breaker thăm dò với lưu lượng nhỏ, tăng dần lượng truy cập, hết hạn cache theo chính sách và quan sát độ trễ. Tránh đồng thời mở toàn bộ lưu lượng, gây sự cố lặp lại.

## 10. Kiểm thử các đường dự phòng

Đường lỗi ít được truy cập lúc bình thường nên phải được kiểm thử có chủ đích. Những trường hợp tiêu biểu:

1. Recommendation Service chậm hơn budget: trang vẫn trả dữ liệu sản phẩm, mode chuyển CACHED hoặc HIDDEN và tổng latency nằm trong deadline.
2. Phụ thuộc trả 503 hoặc circuit breaker đang mở: fallback xảy ra nhanh, không tạo nhiều retry.
3. Cache còn hợp lệ, cache miss, cache quá hạn, cache sai phạm vi quyền: chỉ dùng bản ghi đủ điều kiện.
4. Catalog Service là phụ thuộc bắt buộc bị lỗi: không trả sản phẩm giả dưới dạng 200.
5. Người dùng bị từ chối phân quyền hoặc đầu vào sai: không chuyển sang dữ liệu công khai để “vượt qua” lỗi.
6. Thanh toán timeout sau khi gửi lệnh: không tạo lệnh thu tiền mới thiếu idempotency key; trạng thái được đối soát.
7. Lượng request tăng đột biến trong lúc phụ thuộc lỗi: bulkhead, cache và fallback không tạo thêm nút thắt.
8. Phụ thuộc hồi phục: đường chính được khôi phục dần, metric suy giảm trở về bình thường.

Có thể dùng fault injection, môi trường staging hoặc bài kiểm thử tải để đo hành vi; xác nhận cả **độ đúng của kết quả** và **độ trễ/tài nguyên** trên đường fallback.

## 11. Các lỗi thiết kế thường gặp

**“Catch tất cả rồi trả success.”** Cách này che lỗi lập trình, hỏng dữ liệu, phân quyền và không thể phân biệt hệ thống khỏe với đang suy giảm.

**“Fallback cũng gọi cùng phụ thuộc đang lỗi.”** Nếu cache miss lại gọi dịch vụ chính mà không giới hạn, hệ thống có thể tạo vòng lặp hoặc khuếch đại tải.

**“Cache còn gì thì lấy nấy.”** Không kiểm tra TTL, tenant, quyền truy cập hoặc độ nhạy của dữ liệu làm sai lệch quyết định và có nguy cơ rò rỉ.

**“Dùng giá/stock mặc định cho checkout.”** Đây là kết quả có thể ảnh hưởng tiền và cam kết giao hàng; cần xác minh bằng nguồn có thẩm quyền hoặc từ chối an toàn.

**“Tất cả chức năng phụ đều có thể chạy song song không giới hạn.”** Một dịch vụ phụ chậm có thể chiếm hết connection/thread của các luồng chính. Cần timeout và bulkhead rõ ràng.

**“Không nói cho ai biết đang degraded.”** Người dùng thấy dữ liệu cũ mà không biết; hệ thống giám sát báo toàn màu xanh vì chỉ xem số lượng 200. Cần hợp đồng API, UX và telemetry.

**“Không có chiến lược quay lại đường chính.”** Một cờ tắt tính năng bị quên có thể khiến hệ thống tồn tại ở chế độ suy giảm vô thời hạn.

## 12. Quy trình áp dụng vào một microservice

Với mỗi endpoint hoặc use case, thực hiện theo thứ tự:

1. **Vẽ chuỗi phụ thuộc và xác định kết quả cốt lõi.** Nêu rõ kết quả nào tuyệt đối không được giả lập.
2. **Phân loại dữ liệu và lỗi.** Xác định timeout, 5xx, giới hạn tải, dữ liệu sai, 4xx nghiệp vụ và trường hợp kết quả chưa rõ.
3. **Đặt ngân sách thời gian và tài nguyên.** Có deadline chung, timeout từng lời gọi, giới hạn retry và mức đồng thời.
4. **Chọn fallback theo từng năng lực.** Cache hợp lệ, BASIC, HIDDEN, failover được kiểm chứng, PENDING hoặc UNAVAILABLE.
5. **Định nghĩa hợp đồng với client.** Mã HTTP, trường degradation/mode, độ tươi dữ liệu, thông điệp và hành động tiếp theo.
6. **Gắn quan sát và điều kiện phục hồi.** Đo tần suất fallback, lý do, tác động người dùng và ngưỡng cảnh báo.
7. **Kiểm thử tình huống lỗi thật.** Bao gồm cache miss, phụ thuộc chậm, quá tải, giới hạn quyền và khôi phục.

### Bài tập tư duy

Một hệ thống đặt vé có các dịch vụ: tìm chuyến, gợi ý chuyến tương tự, giữ ghế, định giá cuối và thanh toán. Recommendation Service ngừng hoạt động 10 phút; Seat Reservation Service đôi lúc timeout; Payment Service trả timeout sau khi nhận lệnh thanh toán.

Hãy xác định:

- Chức năng nào có thể **HIDDEN/CACHED** mà vẫn cho phép người dùng tiếp tục?
- Chức năng nào phải **xác minh trạng thái** trước khi báo “đặt vé thành công”?
- Khi thanh toán chưa rõ kết quả, API và giao diện nên nói gì để tránh người dùng trả tiền lần hai?
- Metric nào giúp phát hiện sự cố dù các trang tìm chuyến vẫn trả 200?

**Gợi ý hướng giải:** Có thể ẩn hoặc thay bằng dữ liệu gợi ý hợp lệ; không được coi giữ ghế hay thanh toán thành công khi chưa có xác nhận có thẩm quyền. Giao dịch chưa rõ cần mã theo dõi, trạng thái chờ đối soát và cơ chế idempotency; giám sát tách tỷ lệ gợi ý bị ẩn, timeout giữ ghế, giao dịch chờ xử lý và tỷ lệ hoàn tất đặt vé.

---

**Thông điệp cốt lõi:** Phương án dự phòng tốt làm cho **phần không thiết yếu hỏng mà phần thiết yếu vẫn đúng**. Khi không thể bảo đảm tính đúng đắn, hệ thống phải suy giảm một cách minh bạch hoặc từ chối an toàn, thay vì che sự cố dưới một kết quả thành công giả.