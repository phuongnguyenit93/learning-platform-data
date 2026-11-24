# Thiết kế fallback đọc dữ liệu cũ có thông tin độ mới

Fallback đọc dữ liệu cũ giúp một API đọc vẫn trả được thông tin hữu ích khi dependency tạm thời không khả dụng. Tuy nhiên, trả cache mà không nói rõ dữ liệu được cập nhật lúc nào có thể khiến caller tưởng rằng đó là dữ liệu mới nhất. Một fallback tốt cần quyết định dữ liệu cũ còn được phép sử dụng hay không, đồng thời trả metadata thể hiện nguồn, thời điểm cập nhật và tuổi dữ liệu.

Trong Spring Cloud CircuitBreaker, fallback được gọi khi lời gọi được bảo vệ thất bại hoặc bị từ chối. Fallback có thể đọc snapshot đã lưu trong cache và tạo response suy giảm. Cần phân biệt thời điểm dữ liệu được nguồn cập nhật với thời điểm ứng dụng lưu dữ liệu vào cache. Nếu chỉ dùng thời điểm cache ghi lại, dữ liệu cũ có thể bị xem nhầm là mới.

Bài học này thiết kế fallback theo nguyên tắc stale-if-error: chỉ dùng dữ liệu cũ khi dependency gặp lỗi phù hợp, dữ liệu vẫn nằm trong giới hạn tuổi tối đa và nghiệp vụ chấp nhận độ trễ. Response phải thể hiện rõ freshness để client không dùng dữ liệu stale như dữ liệu hiện tại.

## 1. Fallback stale data giải quyết vấn đề gì?

Giả sử Catalog Service cung cấp tên, mô tả và nhóm sản phẩm. Order API gọi Catalog Service để hiển thị thông tin sản phẩm. Khi Catalog Service tạm thời timeout, API có thể dùng bản snapshot đã lưu trước đó để tiếp tục phục vụ màn hình đọc.

Có ba kết quả cần phân biệt:

- **Fresh**: dữ liệu mới được lấy thành công từ nguồn và nằm trong giới hạn tuổi được xem là mới.
- **Stale but acceptable**: không lấy được dữ liệu mới, nhưng snapshot cache chưa vượt giới hạn tuổi cũ tối đa và nghiệp vụ cho phép dùng tạm.
- **Unavailable**: không có snapshot hoặc snapshot đã quá cũ, không hợp lệ hay không an toàn để sử dụng.

Không nên coi mọi dữ liệu trong cache là phương án dự phòng hợp lệ. Cache có thể chứa dữ liệu đã bị thu hồi, thay đổi quyền truy cập hoặc hết hiệu lực. Fallback phải áp dụng chính sách freshness rõ ràng thay vì chỉ kiểm tra cache có key hay không.

Stale fallback phù hợp hơn với một số luồng đọc như tên sản phẩm, mô tả, cấu hình hiển thị hoặc nội dung tham khảo. Với tồn kho, số dư, quyền truy cập, trạng thái thanh toán và quyết định giao dịch, dữ liệu cũ có thể gây hậu quả. Nếu dùng snapshot tồn kho để hiển thị tham khảo, vẫn phải kiểm tra lại bằng nguồn có thẩm quyền trước khi xác nhận đơn hàng.

## 2. Phân biệt sourceUpdatedAt và cachedAt

Một snapshot nên giữ ít nhất hai mốc thời gian:

- **sourceUpdatedAt**: thời điểm dữ liệu được nguồn có thẩm quyền cập nhật.
- **cachedAt**: thời điểm ứng dụng nhận và lưu snapshot vào cache.

Hai mốc này không có cùng ý nghĩa.

Ví dụ, Catalog Service trả một bản ghi có sourceUpdatedAt là 09:00. Ứng dụng nhận dữ liệu lúc 09:10 và lưu cache. Lúc 09:20, dependency timeout. Tuổi dữ liệu tại thời điểm fallback là 20 phút, không phải 10 phút.

Nếu ứng dụng ghi đè sourceUpdatedAt thành thời điểm đọc cache hoặc thời điểm chạy fallback, dữ liệu cũ sẽ được làm mới giả tạo. Chỉ cập nhật cachedAt khi thực sự nhận một snapshot mới từ nguồn; không cập nhật timestamp chỉ vì đã đọc cache hoặc trả fallback.

Mô hình snapshot:

~~~java
public record CachedCatalog(
        CatalogItem value,
        Instant sourceUpdatedAt,
        Instant cachedAt,
        String sourceVersion) {
}
~~~

Nếu upstream không cung cấp thời điểm cập nhật nguồn, đừng tự gán sourceUpdatedAt bằng clock hiện tại rồi khẳng định dữ liệu chắc chắn mới. Có thể lưu observedAt để thể hiện lần cuối ứng dụng nhận được response, nhưng cần ghi rõ tuổi dữ liệu chỉ được tính từ lần quan sát đó và không chứng minh thời điểm dữ liệu gốc thay đổi.

## 3. Định nghĩa chính sách freshness

Một chính sách đơn giản có hai ngưỡng:

- **freshFor**: tuổi tối đa để xem snapshot là fresh.
- **maxStale**: tuổi tối đa vẫn được phép dùng trong fallback.

Ví dụ:

~~~yaml
app:
  fallback:
    catalog:
      fresh-for: 2m
      max-stale: 30m
~~~

Đây là cấu hình riêng của ứng dụng, không phải thuộc tính chuẩn của Resilience4j. Ứng dụng cần bind nó vào configuration properties và kiểm tra maxStale không nhỏ hơn freshFor.

Giả sử hiện tại là 10:20:

| sourceUpdatedAt | Tuổi dữ liệu | Phân loại |
|---|---:|---|
| 10:19 | 1 phút | Fresh |
| 10:17 | 3 phút | Stale, có thể dùng khi lỗi |
| 10:00 | 20 phút | Stale, có thể dùng khi lỗi |
| 09:40 | 40 phút | Quá cũ, không dùng |
| Không có timestamp hợp lệ | Không xác định | Không khẳng định fresh; xử lý theo chính sách an toàn |

Quy tắc:

\[
age = now - sourceUpdatedAt
\]

- Nếu age âm vì timestamp ở tương lai, dữ liệu có thể gặp clock skew hoặc metadata sai. Không nên tự động xem là fresh.
- Nếu age nhỏ hơn hoặc bằng freshFor, dữ liệu còn fresh.
- Nếu age lớn hơn freshFor nhưng nhỏ hơn hoặc bằng maxStale, dữ liệu stale nhưng có thể chấp nhận khi lỗi.
- Nếu age lớn hơn maxStale, trả trạng thái unavailable hoặc lỗi theo hợp đồng API.

Ngưỡng phải dựa trên nghiệp vụ. Nội dung catalog có thể chấp nhận 30 phút; giá niêm yết, quyền truy cập hoặc trạng thái giao dịch có thể cần chính sách nghiêm ngặt hơn hoặc không cho stale fallback.

## 4. Response phải nói rõ độ mới của dữ liệu

Client cần biết dữ liệu là fresh hay stale để chọn cách hiển thị và quyết định có dùng tiếp hay không. Không nên chỉ trả đối tượng nghiệp vụ mà không có metadata.

Ví dụ response:

~~~json
{
  "data": {
    "id": "SKU-100",
    "name": "Mechanical Keyboard",
    "description": "Compact keyboard"
  },
  "freshness": {
    "status": "STALE",
    "sourceUpdatedAt": "2026-11-24T09:00:00Z",
    "cachedAt": "2026-11-24T09:10:00Z",
    "ageSeconds": 1200,
    "maxStaleSeconds": 1800,
    "sourceVersion": "catalog-v184"
  },
  "fallback": {
    "used": true,
    "reasonCode": "DEPENDENCY_UNAVAILABLE"
  }
}
~~~

Response thể hiện:

- status: FRESH, STALE hoặc UNAVAILABLE.
- sourceUpdatedAt: thời điểm nguồn cập nhật snapshot.
- cachedAt: thời điểm ứng dụng nhận snapshot.
- ageSeconds: tuổi dữ liệu tại thời điểm tạo response.
- maxStaleSeconds: giới hạn stale đang áp dụng.
- sourceVersion: phiên bản hoặc revision do upstream cung cấp nếu có.
- fallback.used: cho biết response có dùng fallback hay không.
- reasonCode: mã nguyên nhân đã chuẩn hóa, không chứa exception message.

Không đưa hostname, URI nội bộ, stack trace, token hoặc nội dung exception vào response. Chi tiết nguyên nhân thuộc log và trace nội bộ. Nếu response không có dữ liệu hợp lệ, trả data null cùng freshness UNAVAILABLE hoặc dùng HTTP status phù hợp với hợp đồng API.

## 5. Tạo kiểu dữ liệu cho freshness metadata

Có thể mô hình hóa metadata thành các record riêng:

~~~java
public enum FreshnessStatus {
    FRESH,
    STALE,
    UNAVAILABLE
}

public record FreshnessMetadata(
        FreshnessStatus status,
        Instant sourceUpdatedAt,
        Instant cachedAt,
        long ageSeconds,
        long maxStaleSeconds,
        String sourceVersion) {
}

public record FallbackMetadata(
        boolean used,
        String reasonCode) {
}

public record CatalogResponse(
        CatalogItem data,
        FreshnessMetadata freshness,
        FallbackMetadata fallback) {
}
~~~

Nếu không có snapshot hợp lệ, data có thể là null hoặc response dùng một kiểu kết quả khác để biểu diễn unavailable. Với API mới, nên chọn một schema nhất quán và tránh để client phải đoán ý nghĩa của null.

Metadata cần phân biệt rõ:
- Dữ liệu mới từ upstream.
- Dữ liệu đọc từ cache nhưng vẫn trong thời hạn fresh.
- Dữ liệu stale được dùng do dependency lỗi.
- Không có dữ liệu đủ điều kiện để trả.

Nếu cần hỗ trợ client cũ, có thể giữ response schema hiện tại và thêm trường metadata tương thích. Hãy xác định rõ cách version API và quy tắc xử lý khi client không hiểu trạng thái STALE.

## 6. Tính tuổi dữ liệu bằng Clock có thể kiểm soát

Nên inject Clock thay vì gọi Instant.now() trực tiếp ở nhiều nơi. Điều này giúp logic freshness nhất quán và kiểm thử được bằng thời gian cố định.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

public class FreshnessPolicy {

    private final Clock clock;
    private final Duration freshFor;
    private final Duration maxStale;

    public FreshnessPolicy(
            Clock clock,
            Duration freshFor,
            Duration maxStale) {

        if (freshFor.isNegative()
                || maxStale.isNegative()
                || maxStale.compareTo(freshFor) < 0) {
            throw new IllegalArgumentException(
                    "maxStale must be >= freshFor >= 0");
        }

        this.clock = clock;
        this.freshFor = freshFor;
        this.maxStale = maxStale;
    }

    public Optional<Duration> ageOf(Instant sourceUpdatedAt) {
        if (sourceUpdatedAt == null) {
            return Optional.empty();
        }

        Instant now = clock.instant();
        if (sourceUpdatedAt.isAfter(now)) {
            return Optional.empty();
        }

        return Optional.of(Duration.between(sourceUpdatedAt, now));
    }

    public FreshnessStatus classify(Duration age) {
        if (age.compareTo(freshFor) <= 0) {
            return FreshnessStatus.FRESH;
        }

        if (age.compareTo(maxStale) <= 0) {
            return FreshnessStatus.STALE;
        }

        return FreshnessStatus.UNAVAILABLE;
    }
}
~~~

Ví dụ này từ chối timestamp ở tương lai để tránh tính tuổi âm. Nếu hệ thống có clock skew được biết trước, có thể bổ sung một tolerance có giới hạn, nhưng phải định nghĩa rõ cách xử lý. Không tự động clamp mọi timestamp tương lai về thời điểm hiện tại vì điều đó có thể che giấu lỗi đồng hồ hoặc metadata.

maxStale là giới hạn tuổi tại thời điểm tạo response. Nếu cache có TTL ngắn hơn, snapshot có thể đã bị xóa trước khi fallback kiểm tra. TTL của cache nên đủ dài để giữ dữ liệu trong cửa sổ fallback, hoặc dùng cơ chế lưu stale snapshot riêng có kiểm soát.

## 7. Chỉ ghi cache sau khi nhận response hợp lệ

Dữ liệu mới chỉ nên thay thế snapshot cũ sau khi response upstream được kiểm tra và giải mã thành công.

Ví dụ service đồng bộ:

~~~java
public CatalogResponse fetchCatalogItem(String id) {
    return catalogCircuitBreaker.run(
            () -> fetchAndCache(id),
            cause -> staleFallback(id, cause)
    );
}

private CatalogResponse fetchAndCache(String id) {
    CatalogItem item = catalogClient.fetch(id);

    validate(item);

    Instant cachedAt = clock.instant();
    CachedCatalog snapshot = new CachedCatalog(
            item,
            item.sourceUpdatedAt(),
            cachedAt,
            item.sourceVersion()
    );

    catalogCache.put(id, snapshot);

    return responseForFreshSnapshot(snapshot);
}
~~~

Trong ví dụ, sourceUpdatedAt và sourceVersion đến từ dữ liệu upstream. cachedAt là thời điểm ứng dụng nhận response hợp lệ. Nếu validation thất bại, không ghi đè snapshot hợp lệ cũ bằng dữ liệu không hoàn chỉnh.

Nếu upstream trả dữ liệu không có version, có thể để sourceVersion rỗng hoặc null theo schema. Không tự tạo version giả rồi xem nó như revision của nguồn.

Đối với cache phân tán, cần bảo đảm thao tác ghi snapshot có tính nguyên tử hoặc dùng version để tránh response cũ đến muộn ghi đè response mới hơn. Ví dụ hai request chạy song song: request A lấy dữ liệu version 10 nhưng chậm; request B lấy version 11 và ghi trước; nếu A ghi sau, cache có thể bị lùi về version 10. Có thể dùng compare-and-set theo sourceVersion hoặc timestamp có thẩm quyền.

## 8. Chọn stale snapshot trong fallback

Fallback cần đọc snapshot, kiểm tra timestamp và quyết định có được phép trả hay không. Không trả stale chỉ vì cache có dữ liệu.

~~~java
private CatalogResponse staleFallback(String id, Throwable cause) {
    if (!isTransientDependencyFailure(cause)) {
        throw new CatalogFallbackNotApplicableException(cause);
    }

    Optional<CachedCatalog> cached = catalogCache.find(id);
    if (cached.isEmpty()) {
        return unavailableResponse("NO_CACHED_SNAPSHOT");
    }

    CachedCatalog snapshot = cached.get();

    Optional<Duration> age =
            freshnessPolicy.ageOf(snapshot.sourceUpdatedAt());

    if (age.isEmpty()) {
        return unavailableResponse("INVALID_SOURCE_TIMESTAMP");
    }

    FreshnessStatus status = freshnessPolicy.classify(age.get());

    if (status == FreshnessStatus.UNAVAILABLE) {
        return unavailableResponse("SNAPSHOT_TOO_OLD");
    }

    return responseForSnapshot(
            snapshot,
            status,
            age.get(),
            true,
            "DEPENDENCY_UNAVAILABLE"
    );
}
~~~

Các helper như isTransientDependencyFailure, unavailableResponse và responseForSnapshot cần được triển khai theo loại exception, cache và response model của ứng dụng.

Một chính sách tốt thường chỉ cho stale fallback với lỗi tạm thời như timeout, connection failure hoặc 503. Các lỗi nghiệp vụ như 404, validation error, 401 hoặc 403 không nên tự động trả dữ liệu cũ vì có thể che giấu việc tài nguyên đã bị xóa hoặc caller không còn quyền truy cập.

Nếu không đủ điều kiện dùng cache, fallback phải trả trạng thái unavailable hoặc để exception đi theo error handler. Không biến mọi lỗi thành response stale.

## 9. Phân loại lỗi trước khi dùng dữ liệu cũ

Không phải exception nào cũng có nghĩa dependency tạm thời không khả dụng.

| Nhóm lỗi | Dùng stale snapshot? | Lý do |
|---|---|---|
| Timeout | Có thể | Nguồn chưa phản hồi đúng hạn |
| Connection refused/reset | Có thể | Lỗi kết nối có thể tạm thời |
| HTTP 503/502 | Có thể | Upstream hoặc gateway tạm thời không phục vụ |
| Circuit Breaker OPEN | Có thể | Lời gọi bị chặn do dependency trước đó lỗi |
| HTTP 404 | Thường không | Tài nguyên có thể đã bị xóa hoặc không tồn tại |
| HTTP 401/403 | Không nên | Có thể là lỗi xác thực hoặc quyền truy cập |
| Validation/mapping error | Không nên | Dữ liệu hoặc hợp đồng có thể sai |
| Business rejection | Không | Không phải lỗi khả dụng của dependency |

Cách phân loại phải dựa trên exception type, HTTP status và hợp đồng API. Đừng phân loại bằng cách tìm chuỗi timeout trong exception message.

Với Resilience4j, có thể cấu hình recordExceptions, ignoreExceptions hoặc predicate để xác định lỗi nào ảnh hưởng failure rate. Việc fallback có chạy hay không vẫn phụ thuộc cách adapter gọi fallback. Nên kiểm tra riêng:
- Lỗi nào được Circuit Breaker ghi nhận.
- Lỗi nào kích hoạt fallback.
- Lỗi nào phải được truyền nguyên trạng đến caller.

Nếu fallback handler ném exception mới, giữ nguyên cause để log và tracing có thể truy ra nguyên nhân gốc. Không thay lỗi quyền truy cập bằng một response cache thành công.

## 10. Tạo response FRESH, STALE và UNAVAILABLE

Một helper tập trung giúp mọi endpoint trả metadata nhất quán:

~~~java
private CatalogResponse responseForSnapshot(
        CachedCatalog snapshot,
        FreshnessStatus status,
        Duration age,
        boolean fallbackUsed,
        String reasonCode) {

    FreshnessMetadata freshness = new FreshnessMetadata(
            status,
            snapshot.sourceUpdatedAt(),
            snapshot.cachedAt(),
            age.toSeconds(),
            maxStale.toSeconds(),
            snapshot.sourceVersion()
    );

    FallbackMetadata fallback = new FallbackMetadata(
            fallbackUsed,
            fallbackUsed ? reasonCode : null
    );

    return new CatalogResponse(snapshot.value(), freshness, fallback);
}
~~~

Khi lấy dữ liệu mới từ upstream, status thường là FRESH nếu tuổi sourceUpdatedAt không vượt freshFor. Nếu nguồn trả về timestamp đã cũ, response mới nhận từ mạng vẫn có thể mang dữ liệu stale theo nguồn. Không nên đánh dấu FRESH chỉ vì HTTP request vừa thành công.

Khi fallback đọc cache:
- Nếu tuổi vẫn trong freshFor, response có thể ghi freshness FRESH nhưng fallback.used bằng true, vì dữ liệu được phục vụ từ cache trong lúc dependency lỗi.
- Nếu tuổi vượt freshFor nhưng không vượt maxStale, status là STALE.
- Nếu vượt maxStale, không trả snapshot.

Cách phân biệt này tránh nhầm lẫn giữa nguồn dữ liệu và độ mới của nội dung. fallback.used trả lời câu hỏi "response có dùng đường dự phòng không?", còn freshness.status trả lời câu hỏi "nội dung có mới theo chính sách không?".

## 11. Reactive fallback với WebClient

Trong WebFlux, cache và fallback nên giữ tính reactive. Không gọi cache blocking trực tiếp trên event loop. Có thể dùng một reactive cache repository trả về Mono<Optional<CachedCatalog>>.

~~~java
public Mono<CatalogResponse> getCatalogItem(String id) {
    Mono<CatalogItem> remote = webClient.get()
            .uri("/catalog/{id}", id)
            .retrieve()
            .bodyToMono(CatalogItem.class)
            .doOnNext(this::validate);

    Mono<CatalogResponse> cachedAndStored = remote
            .flatMap(item -> {
                CachedCatalog snapshot = toSnapshot(item, clock.instant());

                return reactiveCatalogCache.put(id, snapshot)
                        .thenReturn(responseForFreshSnapshot(snapshot));
            });

    return reactiveCircuitBreaker.run(
            cachedAndStored,
            cause -> reactiveCatalogCache.find(id)
                    .flatMap(snapshot -> staleOrUnavailable(id, snapshot, cause))
                    .switchIfEmpty(Mono.just(
                            unavailableResponse("NO_CACHED_SNAPSHOT")))
    );
}
~~~

Đoạn code minh họa yêu cầu reactiveCatalogCache.put và find trả publisher không blocking. Nếu cache hiện tại là thư viện blocking, hãy chuyển thao tác sang scheduler phù hợp hoặc dùng reactive client; không gọi block() trong WebFlux event loop.

staleOrUnavailable cần thực hiện cùng quy tắc freshness và phân loại exception như phiên bản đồng bộ. Nếu cause không thuộc nhóm lỗi tạm thời, trả lỗi thay vì stale snapshot.

Không đặt side effect ghi cache trước khi response được validate. doOnNext phù hợp cho side effect nhẹ, nhưng nếu thao tác ghi cache là bất đồng bộ và cần bảo đảm hoàn tất trước khi trả response, hãy compose nó bằng flatMap như ví dụ.

## 12. Stale-if-error khác stale-while-revalidate

Hai chiến lược có mục tiêu khác nhau:

- **Stale-if-error**: chỉ dùng dữ liệu cũ khi lần đọc mới thất bại hoặc dependency không khả dụng.
- **Stale-while-revalidate**: trả dữ liệu cũ ngay khi đang hết hạn, đồng thời khởi động tác vụ làm mới ở nền.

Không trộn hai chiến lược nếu chưa xác định rõ hợp đồng API. Với stale-while-revalidate, caller có thể nhận stale ngay cả khi dependency vẫn hoạt động. Với stale-if-error, caller chỉ nhận stale sau một lỗi phù hợp.

Nếu triển khai refresh nền:
- Chỉ cho một tác vụ refresh cho mỗi key trong cùng khoảng thời gian để tránh stampede.
- Giới hạn concurrency và timeout của refresh.
- Không để refresh lỗi ghi đè snapshot tốt.
- Dùng version hoặc compare-and-set để tránh response cũ ghi sau response mới.
- Theo dõi refresh success/failure và snapshot age.

Fallback không nên tự khởi chạy hàng loạt request refresh đồng bộ cho mọi caller. Khi dependency đang lỗi, hành động đó có thể làm tăng tải và khiến hệ thống khó phục hồi.

## 13. Bảo vệ nghiệp vụ khi dùng dữ liệu cũ

Freshness không chỉ là kỹ thuật cache. Mỗi trường dữ liệu có thể có mức chấp nhận stale khác nhau.

| Loại dữ liệu | Chính sách gợi ý |
|---|---|
| Tên và mô tả sản phẩm | Có thể cho stale trong cửa sổ ngắn |
| Ảnh đại diện hoặc nội dung tĩnh | Thường chấp nhận stale lâu hơn |
| Giá hiển thị | Chỉ dùng nếu nghiệp vụ cho phép và hiển thị thời điểm cập nhật |
| Tồn kho | Có thể dùng để tham khảo, nhưng phải xác nhận lại trước khi đặt hàng |
| Số dư tài khoản | Không dùng stale để xác nhận giao dịch |
| Quyền truy cập | Không dùng cache cũ để cấp quyền khi không xác minh được trạng thái hiện tại |
| Trạng thái thanh toán | Phải tra cứu nguồn có thẩm quyền trước khi kết luận |

Một response stale nên khiến client hiển thị thông tin phù hợp, ví dụ "Dữ liệu cập nhật lúc 09:00". Không nên chỉ thay màu hoặc ẩn trạng thái stale trong UI.

Nếu một thao tác có side effect, không dùng stale snapshot để quyết định thực hiện giao dịch. Có thể dùng dữ liệu cũ để hiển thị gợi ý, nhưng bước ghi phải xác nhận lại với nguồn có thẩm quyền hoặc dùng quy trình nhất quán riêng.

## 14. Bảo vệ cache và phân tách dữ liệu

Cache fallback cần tuân thủ cùng quy tắc bảo mật với nguồn dữ liệu:

- Key phải bao gồm tenant hoặc phạm vi dữ liệu khi dữ liệu được phân vùng theo tenant.
- Không dùng một snapshot của tenant này để trả cho tenant khác.
- Khi quyền truy cập bị thu hồi, phải có cơ chế invalidation hoặc kiểm tra quyền độc lập.
- Dữ liệu nhạy cảm cần TTL, mã hóa và quyền truy cập phù hợp.
- Không ghi payload nhạy cảm hoặc token vào log khi fallback.
- Khi snapshot không có version hoặc timestamp hợp lệ, áp dụng chính sách an toàn.

Đặc biệt, lỗi 401/403 không nên tự động kích hoạt stale fallback cho dữ liệu cần kiểm soát quyền. Nếu caller không còn quyền truy cập, trả dữ liệu cache có thể làm lộ thông tin đã bị thu hồi.

Cache phải có giới hạn dung lượng và chính sách eviction. Stale fallback không phải lý do giữ dữ liệu vô thời hạn. maxStale giới hạn tuổi nội dung; TTL và eviction giới hạn vòng đời lưu trữ. Cả hai đều cần được cấu hình.

## 15. Theo dõi freshness và fallback

Chỉ đếm số lần fallback chưa đủ để biết chất lượng dữ liệu được trả. Nên theo dõi:

- Số response fresh và stale.
- Số lần fallback theo dependency và loại nguyên nhân.
- Tuổi snapshot tại thời điểm trả response, gồm p50, p95 và p99.
- Số snapshot bị từ chối vì quá maxStale.
- Số lần không có cache entry.
- Số lỗi timestamp thiếu hoặc nằm trong tương lai.
- Thời gian từ sourceUpdatedAt đến cachedAt.
- Tỷ lệ refresh thành công và thất bại.
- Số lần response stale được dùng cho các luồng nghiệp vụ quan trọng.

Metric label nên có cardinality thấp: dependency, route và freshness status. Không đưa product ID, tenant ID, request ID hoặc exception message vào label. Dùng log/trace có correlation ID để điều tra từng request.

Có thể ghi log cấu trúc:

~~~text
event=circuit_breaker_fallback
dependency=catalog
freshness=STALE
age_seconds=1200
max_stale_seconds=1800
reason_code=DEPENDENCY_UNAVAILABLE
request_id=server-generated-id
~~~

Không ghi raw exception message vào response. Nếu cần stack trace, giữ trong log nội bộ có quyền truy cập phù hợp.

## 16. Kiểm thử freshness bằng Clock cố định

Không dùng Thread.sleep để chờ snapshot trở nên stale. Inject Clock và dùng Clock.fixed giúp test xác định được tuổi dữ liệu.

Ví dụ:

~~~java
Instant now = Instant.parse("2026-11-24T10:00:00Z");
Clock clock = Clock.fixed(now, ZoneOffset.UTC);

CachedCatalog snapshot = new CachedCatalog(
        catalogItem,
        now.minus(Duration.ofMinutes(10)),
        now.minus(Duration.ofMinutes(9)),
        "catalog-v184"
);
~~~

Với freshFor bằng 2 phút và maxStale bằng 30 phút, snapshot trên có tuổi 10 phút và được phân loại STALE. Test cần xác nhận response giữ nguyên sourceUpdatedAt, cachedAt, ageSeconds và sourceVersion.

Các trường hợp nên kiểm thử:

1. Snapshot 1 phút tuổi: status FRESH.
2. Snapshot đúng freshFor: vẫn FRESH nếu quy tắc dùng <=.
3. Snapshot lớn hơn freshFor nhưng nhỏ hơn maxStale: status STALE.
4. Snapshot đúng maxStale: được chấp nhận nếu quy tắc dùng <=.
5. Snapshot lớn hơn maxStale: UNAVAILABLE.
6. Không có cache entry: NO_CACHED_SNAPSHOT.
7. Timestamp null hoặc ở tương lai: không khẳng định freshness.
8. Lỗi 404 hoặc 403: không dùng stale fallback nếu chính sách không cho phép.
9. Timeout hoặc connection failure: dùng stale nếu còn trong giới hạn.
10. Đọc fallback không làm thay đổi sourceUpdatedAt hoặc cachedAt.

## 17. Kiểm thử fallback qua Circuit Breaker

Có thể dùng mock client và cache để xác nhận hành vi tổng thể:

- Khi upstream thành công, service trả dữ liệu nguồn và cập nhật cache.
- Khi upstream timeout, fallback đọc snapshot và trả metadata STALE.
- Khi snapshot quá cũ, response là UNAVAILABLE hoặc lỗi theo hợp đồng.
- Khi cache rỗng, response không bịa dữ liệu.
- Khi lỗi là 401/403/404, không trả snapshot nếu đây là lỗi nghiệp vụ hoặc quyền truy cập.
- Khi Circuit Breaker OPEN, Supplier upstream không được gọi nhưng fallback vẫn có thể đọc cache.
- Khi fallback đọc cache thất bại, ứng dụng trả lỗi dự phòng an toàn và ghi nhận riêng lỗi cache.

Nên kiểm tra số lần gọi upstream để xác nhận Circuit Breaker OPEN không tiếp tục tạo request. Đồng thời, kiểm tra số lần đọc cache và metadata response. Không chỉ assert rằng response body có dữ liệu; phải assert freshness status, timestamp và reason code.

Với reactive pipeline, dùng StepVerifier và Publisher lazy để kiểm soát subscription. Nếu cache client là reactive, kiểm tra fallback publisher chỉ được subscribe khi đường fallback được chọn. Nếu dùng cache blocking, kiểm tra thao tác không chạy trên event loop.

## 18. Các lỗi thường gặp

- **Dùng cachedAt thay cho sourceUpdatedAt để tính tuổi**: dữ liệu cũ có thể được làm mới giả tạo.
- **Cập nhật timestamp khi đọc cache**: mỗi fallback khiến snapshot trông mới hơn thực tế.
- **Trả cache không có freshness metadata**: client không biết dữ liệu đã cũ.
- **Dùng stale cho mọi exception**: có thể che giấu 401, 403, 404 hoặc lỗi nghiệp vụ.
- **Không đặt maxStale**: dữ liệu có thể được trả vô thời hạn.
- **Nhầm stale-if-error với stale-while-revalidate**: hai chiến lược có điều kiện kích hoạt khác nhau.
- **Dùng stale để xác nhận giao dịch**: dữ liệu cũ có thể gây quyết định sai hoặc side effect.
- **Ghi cache trước validation**: dữ liệu lỗi có thể ghi đè snapshot tốt.
- **Không kiểm soát ghi đồng thời**: response cũ đến muộn có thể ghi đè version mới.
- **Gọi cache blocking trên event loop**: làm nghẽn ứng dụng reactive.
- **Không phân tách cache theo tenant hoặc quyền**: có nguy cơ trả dữ liệu sai phạm vi.
- **Chỉ đo fallback count**: không biết tuổi dữ liệu thực tế mà caller đang nhận.
- **Retry hoặc refresh quá mức trong fallback**: có thể tạo stampede khi dependency đang lỗi.

## 19. Quy trình triển khai

Khi thiết kế stale fallback trong Spring Cloud CircuitBreaker, có thể thực hiện theo trình tự:

1. Xác định loại dữ liệu và quyết định nghiệp vụ nào được phép dùng snapshot cũ.
2. Yêu cầu upstream cung cấp sourceUpdatedAt hoặc version có thẩm quyền.
3. Lưu riêng sourceUpdatedAt, cachedAt và source version.
4. Định nghĩa freshFor và maxStale theo từng loại dữ liệu.
5. Chỉ ghi cache sau khi response upstream được validate.
6. Phân loại exception và chỉ cho stale fallback với lỗi tạm thời được chấp nhận.
7. Trong fallback, tính tuổi bằng Clock và từ chối timestamp không hợp lệ hoặc snapshot quá cũ.
8. Trả freshness metadata rõ ràng cùng fallback reason code đã chuẩn hóa.
9. Bảo vệ cache theo tenant, quyền truy cập, TTL và dung lượng.
10. Với reactive, dùng cache reactive hoặc scheduler phù hợp; không block event loop.
11. Kiểm thử ranh giới freshFor/maxStale, lỗi nghiệp vụ, timeout, Circuit Breaker OPEN và cache rỗng.
12. Theo dõi tuổi dữ liệu, tỷ lệ stale, lỗi refresh và số response unavailable.

Fallback đọc dữ liệu cũ chỉ an toàn khi caller biết rõ dữ liệu được cập nhật lúc nào và ứng dụng giới hạn tuổi dữ liệu theo nghiệp vụ. Giữ riêng sourceUpdatedAt và cachedAt, chỉ dùng stale cho lỗi phù hợp, đặt maxStale, và trả metadata FRESH/STALE/UNAVAILABLE giúp client đưa ra quyết định đúng. Circuit Breaker bảo vệ dependency; freshness policy bảo vệ ý nghĩa của dữ liệu mà fallback trả về.
