# Cache hoặc share ngoài ý muốn làm thay đổi vòng đời và dữ liệu

Trong module REACTIVE_PROGRAMMING, ta học cách xử lý luồng sự kiện bất đồng bộ theo hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành Mono, Flux, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Một lỗi thiết kế thường gặp là thêm cache hoặc share vào pipeline chỉ để giảm số lần gọi nguồn, nhưng không xem xét thay đổi về vòng đời subscription, dữ liệu được phát lại, cancellation và phạm vi ngữ cảnh.

Các toán tử cache/share không chỉ là tối ưu hiệu năng. Chúng có thể biến một nguồn lạnh thành nguồn nóng hoặc nguồn được chia sẻ, thay đổi số lần thực thi upstream, giữ lại giá trị cũ, giữ lỗi/empty signal, làm subscriber mới nhận dữ liệu từ subscriber trước và kéo dài công việc sau khi một subscriber đã hủy. Nếu nguồn phụ thuộc tenant, người dùng, quyền truy cập hoặc request context, việc chia sẻ sai ranh giới còn có thể làm lộ dữ liệu giữa các request.

Bài này phân biệt cache, replay và share trong Reactor, chỉ ra các tình huống dễ sai và cách kiểm thử vòng đời để lựa chọn chính sách phù hợp.

## 1. Nguồn lạnh và nguồn nóng có vòng đời khác nhau

Một Publisher lạnh thường tạo hoặc thực hiện công việc cho mỗi subscription. Ví dụ:

~~~java
AtomicInteger calls = new AtomicInteger();

Mono<String> source = Mono.fromSupplier(() ->
    "result-" + calls.incrementAndGet()
);
~~~

Hai subscriber độc lập có thể kích hoạt supplier hai lần và nhận hai kết quả khác nhau. Mỗi subscription có vòng đời riêng.

Ngược lại, nguồn nóng có thể phát dữ liệu độc lập với subscriber cụ thể. Subscriber đến sau có thể bỏ lỡ những phần tử đã phát, trừ khi nguồn có chính sách lưu và replay. Một event bus hoặc callback cảm biến là ví dụ điển hình.

| Đặc điểm | Cold Publisher | Hot/shared Publisher |
|---|---|---|
| Khi nào nguồn chạy? | Thường khi từng subscriber subscribe | Có thể chạy độc lập hoặc khi subscriber đầu tiên xuất hiện |
| Nhiều subscriber | Có thể chạy nguồn riêng cho từng người | Có thể dùng chung một upstream subscription |
| Subscriber đến muộn | Thường bắt đầu một lần thực thi mới | Chỉ nhận phần tử từ thời điểm tham gia, trừ khi có replay/cache |
| Cancellation | Hủy subscription thường hủy phần công việc tương ứng nếu nguồn hỗ trợ | Một subscriber hủy chưa chắc làm upstream dừng nếu còn subscriber khác hoặc nguồn đã được cache |
| Ví dụ | Truy vấn reactive được tạo theo subscription | Sinks, event stream chia sẻ, cache/replay |

Cold/Hot là một thuộc tính về hành vi subscription, không phải chỉ là tên kiểu Mono hay Flux. Một Flux có thể được tạo lạnh rồi chuyển thành nguồn chia sẻ bằng share hoặc cache.

## 2. cache() thay đổi số lần thực thi upstream

Với Mono, cache() lưu tín hiệu kết thúc của lần thực thi đầu tiên và phát lại tín hiệu đó cho các subscriber sau. Tín hiệu được lưu có thể là giá trị, hoàn tất rỗng hoặc lỗi:

~~~java
AtomicInteger calls = new AtomicInteger();

Mono<String> cached = Mono.fromSupplier(() ->
    "loaded-" + calls.incrementAndGet()
).cache();
~~~

Subscriber đầu tiên kích hoạt nguồn. Những subscriber đến sau nhận lại kết quả đã cache thay vì thực thi supplier lần nữa. Đây có thể là hành vi mong muốn với dữ liệu dùng chung và ổn định trong phạm vi cache, nhưng có thể gây lỗi nếu ta vẫn kỳ vọng mỗi request có một lần đọc độc lập.

Ví dụ, một phương thức service trả về cùng một Mono đã cache:

~~~java
class ProfileService {
    private final Mono<Profile> profile;

    ProfileService(ProfileRepository repository) {
        this.profile = repository.loadDefaultProfile().cache();
    }

    Mono<Profile> load() {
        return profile;
    }
}
~~~

Nếu profile thực sự là cấu hình dùng chung, ít thay đổi và có chính sách vòng đời rõ ràng, cache có thể phù hợp. Nếu repository method thực ra cần nhận user ID hoặc tenant ID, giữ một Mono cache ở cấp singleton service sẽ khiến các request chia sẻ cùng kết quả đầu tiên.

Điểm cần nhớ: cache() lưu tín hiệu của nguồn; nó không tự hiểu dữ liệu nào đã hết hạn theo nghiệp vụ, người dùng nào được phép nhận dữ liệu hoặc khi nào cần làm mới.

## 3. Flux.cache() có thể giữ lịch sử lớn

Với Flux, cache có thể phát lại các phần tử đã lưu cho subscriber đến sau. Dùng cache không giới hạn trên nguồn dài hạn có thể khiến lịch sử tăng mãi:

~~~java
Flux<Event> allEvents = eventSource.events().cache();
~~~

Nếu nguồn phát liên tục, mọi phần tử được giữ lại có thể làm bộ nhớ tăng theo thời gian. Subscriber mới còn có thể phải nhận một lượng lớn lịch sử trước khi bắt kịp phần tử mới.

Nếu chỉ cần giữ một phần lịch sử gần nhất, có thể giới hạn số phần tử:

~~~java
Flux<Event> recentEvents = eventSource.events().cache(100);
~~~

Subscriber đến sau nhận tối đa phần lịch sử được cấu hình cùng các phần tử tiếp theo. Giới hạn theo số phần tử không đồng nghĩa giới hạn theo byte: 100 event nhỏ và 100 event chứa payload lớn có chi phí bộ nhớ rất khác nhau.

Một số overload hỗ trợ TTL hoặc kết hợp history và TTL. Hãy chọn đúng overload theo phiên bản Reactor của dự án và kiểm tra chính sách lưu giữ thực tế. TTL giới hạn thời gian lưu theo chính sách operator; nó không thay thế invalidation theo thay đổi nghiệp vụ hoặc kiểm soát kích thước payload.

## 4. Phân biệt cache, replay và share

Ba nhóm operator có mục đích gần nhau nhưng ngữ nghĩa khác nhau:

| Operator | Hành vi chính | Subscriber đến muộn |
|---|---|---|
| cache() | Chạy nguồn và lưu tín hiệu để phát lại theo chính sách cache | Nhận tín hiệu đã lưu; với Flux có thể nhận lịch sử |
| replay(...) | Chia sẻ nguồn và giữ lịch sử theo giới hạn replay | Nhận phần lịch sử còn được giữ rồi nhận dữ liệu mới |
| share() | Chia sẻ một upstream subscription cho các subscriber cùng tham gia; không replay lịch sử | Thường chỉ nhận phần tử từ lúc tham gia |

Ví dụ:

~~~java
Flux<Event> cachedHistory = source.cache(50);

Flux<Event> sharedLive = source.share();

Flux<Event> replayLatest = source.replay(1).refCount(1);
~~~

cache(50) lưu lịch sử tối đa 50 phần tử cho subscriber đến sau. share() tập trung vào chia sẻ luồng đang hoạt động, không lưu lịch sử cho người đến muộn. replay(1).refCount(1) chia sẻ nguồn và giữ phần tử gần nhất theo chính sách replay trong vòng đời kết nối.

Không chọn operator chỉ dựa trên tên gọi. Hãy xác định subscriber mới cần snapshot, một phần lịch sử hay chỉ những event trong tương lai. Đồng thời, xác định điều gì xảy ra khi subscriber cuối cùng hủy, khi nguồn hoàn tất và khi nguồn phát lỗi.

## 5. share() và vòng đời refCount

share() thường được hiểu là chia sẻ một nguồn giữa các subscriber đang hoạt động. Upstream được kết nối khi subscriber đầu tiên tham gia. Khi tất cả subscriber rời đi trước khi nguồn kết thúc, kết nối upstream có thể bị hủy; một subscriber mới có thể làm nguồn được subscribe lại theo chính sách refCount của operator.

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1))
    .doOnSubscribe(s -> log.info("Upstream subscribed"))
    .doFinally(signal -> log.info("Upstream ended: {}", signal))
    .share();
~~~

Hai subscriber cùng hoạt động có thể nhận tín hiệu từ một nguồn upstream. Nếu subscriber thứ nhất hủy nhưng subscriber thứ hai vẫn còn, nguồn vẫn cần tiếp tục cho subscriber còn lại. Nếu subscriber cuối cùng hủy, share có thể hủy upstream.

Hãy phân biệt share() với autoConnect(). autoConnect(n) kết nối khi đạt số subscriber yêu cầu và không tự ngắt upstream chỉ vì subscriber downstream rời đi. Nếu cần quản lý kết nối thủ công, ConnectableFlux với connect() và Disposable cho phép chủ sở hữu quyết định khi bắt đầu và kết thúc nguồn.

Vòng đời sau terminal signal cần được kiểm tra theo operator và phiên bản Reactor cụ thể. Không giả định một nguồn đã complete hoặc error sẽ tự khởi động lại như một Publisher lạnh mới. Nếu yêu cầu nghiệp vụ cần tạo một phiên nguồn mới sau khi kết thúc, hãy thiết kế factory tạo Publisher mới hoặc kiểm tra chính sách reset/reconnect được API hỗ trợ.

## 6. Cache cả empty và error có thể gây bất ngờ

Một lỗi tinh vi là nghĩ cache chỉ lưu giá trị thành công. Mono cache lưu tín hiệu kết thúc của nguồn, vì vậy empty và error cũng có thể được phát lại:

~~~java
AtomicInteger attempts = new AtomicInteger();

Mono<Product> cachedLookup = Mono.defer(() -> {
    attempts.incrementAndGet();
    return repository.findBySku("sku-404");
}).cache();
~~~

Nếu lần đầu repository trả về Mono.empty(), các subscriber sau có thể tiếp tục nhận empty mà không truy vấn lại. Nếu lần đầu phát lỗi tạm thời, lỗi đó cũng có thể được cache và phát lại. Đây là vấn đề khi nguồn có thể thay đổi theo thời gian hoặc lỗi có thể phục hồi.

TTL có thể giới hạn thời gian lưu tín hiệu:

~~~java
Mono<Product> cachedLookup = Mono.defer(() ->
    repository.findBySku("sku-404")
).cache(Duration.ofSeconds(10));
~~~

Sau khoảng TTL, subscription mới có thể kích hoạt lần tải tiếp theo theo chính sách cache. Với API có overload TTL riêng cho value, error và empty, có thể đặt thời gian khác nhau cho từng loại tín hiệu. Ví dụ, cache kết quả thành công lâu hơn lỗi hoặc empty; nhưng thời hạn phải dựa trên yêu cầu dữ liệu và khả năng phục hồi.

Nếu empty có nghĩa “chưa tồn tại” nhưng bản ghi có thể được tạo ngay sau đó, cache empty quá lâu khiến request tiếp theo vẫn nhìn thấy trạng thái cũ. Nếu lỗi là timeout ngắn, cache lỗi lâu sẽ kéo dài sự cố dù dependency đã phục hồi.

## 7. Vị trí retry, fallback và cache làm thay đổi kết quả

Thứ tự operator quyết định cache lưu kết quả trước hay sau khi retry/fallback:

~~~java
Mono<Product> retryThenCache = Mono.defer(() -> repository.findBySku(sku))
    .retryWhen(Retry.max(2))
    .cache();

Mono<Product> cacheThenRetry = Mono.defer(() -> repository.findBySku(sku))
    .cache()
    .retryWhen(Retry.max(2));
~~~

Ở pipeline đầu, retry chạy trước cache. Nguồn có cơ hội được đăng ký lại theo chính sách retry; tín hiệu terminal cuối cùng sau retry được cache. Ở pipeline thứ hai, cache giữ tín hiệu đầu tiên. Nếu tín hiệu đó là error, retry phía sau có thể subscribe lại vào cache và nhận cùng lỗi đã lưu, không kích hoạt lại repository như mong muốn.

Tương tự với empty fallback:

~~~java
Mono<Product> cacheCompleteResult = primaryLookup(sku)
    .switchIfEmpty(fallbackLookup(sku))
    .cache();

Mono<Product> cachePrimaryOnly = primaryLookup(sku)
    .cache()
    .switchIfEmpty(fallbackLookup(sku));
~~~

Pipeline đầu cache kết quả cuối cùng sau khi đã chọn nhánh chính hoặc fallback. Pipeline thứ hai chỉ cache tín hiệu của nguồn chính; nhánh fallback nằm phía sau và có thể được thực hiện theo từng subscription downstream. Cách đặt nào đúng phụ thuộc việc muốn cache toàn bộ kết quả use case hay chỉ cache nguồn chính.

Nếu fallback cũng có side effect, hãy bọc factory bằng defer để nó chỉ được tạo/thực thi khi nhánh thực sự được chọn:

~~~java
primaryLookup(sku)
    .switchIfEmpty(Mono.defer(() -> fallbackLookup(sku)));
~~~

## 8. Context của subscriber có thể bị cố định bởi cache/share

Reactor Context thuộc subscription. Nhưng khi nhiều subscriber dùng chung một upstream subscription, phần upstream chỉ chạy trong một subscription context. Nếu nguồn đọc tenant hoặc user từ Context rồi cache kết quả, subscriber đầu tiên có thể quyết định dữ liệu được cache cho tất cả subscriber sau.

~~~java
Mono<String> tenantData = Mono.deferContextual(context -> {
    String tenant = context.get("tenantId");
    return repository.loadTenantSummary(tenant);
}).cache();
~~~

Nếu subscriber đầu tiên đặt tenantId = tenant-a, kết quả của tenant-a có thể trở thành kết quả cache được phát cho subscriber tenant-b. Đây là lỗi cô lập dữ liệu nghiêm trọng.

Không cache một Publisher phụ thuộc tenant/user/request context ở cấp singleton nếu cache không phân vùng theo các key đó. Các lựa chọn an toàn hơn:

- Đưa tenant ID vào tham số và dùng cache có key (tenantId, resourceId) ở tầng cache chuyên dụng.
- Tạo Publisher/cache riêng cho từng tenant hoặc phạm vi sở hữu rõ ràng.
- Cache dữ liệu công khai, không phụ thuộc quyền, rồi áp dụng kiểm tra quyền và lọc dữ liệu ở downstream theo từng subscriber.
- Tránh share một upstream đã thực hiện authorization riêng cho subscriber đầu tiên.

Context vẫn có thể được đọc ở các operator downstream sau ranh giới chia sẻ theo subscription của từng subscriber. Rủi ro nằm ở phần công việc phụ thuộc Context được đặt trước ranh giới cache/share và chỉ chạy một lần cho subscription upstream dùng chung.

## 9. Cache object mutable làm rò thay đổi giữa subscriber

Cache thường phát lại cùng một giá trị object đã lưu. Nếu object có thể thay đổi, một subscriber có thể sửa dữ liệu mà subscriber sau nhận được:

~~~java
Mono<MutableProfile> profile = repository.loadMutableProfile().cache();

profile.subscribe(value -> value.setDisplayName("Changed by A"));
profile.subscribe(value -> log.info("name={}", value.getDisplayName()));
~~~

Subscriber thứ hai có thể nhìn thấy object đã bị subscriber thứ nhất sửa. Điều này tạo ra sự phụ thuộc theo thứ tự subscriber và làm kết quả khó tái lập.

Ưu tiên:

- Dùng immutable record/value object cho dữ liệu được cache.
- Không trả trực tiếp collection mutable có thể bị sửa.
- Copy dữ liệu ở ranh giới nếu consumer cần quyền chỉnh sửa.
- Giữ thao tác cập nhật đi qua command/service có kiểm soát thay vì sửa object cache tại chỗ.

Cache nên lưu một snapshot có ngữ nghĩa rõ. Nếu dữ liệu thay đổi, tạo snapshot mới và thay thế theo chính sách invalidation, thay vì để subscriber tự sửa cùng một instance.

## 10. Cache có thể tiếp tục tải sau khi subscriber hủy

Với một số cache operator, khi subscription đầu tiên đã kích hoạt quá trình tải và cache cần hoàn tất việc lưu tín hiệu, cancellation của một subscriber không nhất thiết hủy upstream. Điều này khác với một cold Publisher thông thường mà subscription duy nhất bị hủy có thể làm công việc dừng lại.

Hệ quả:

- Client có thể timeout hoặc đóng kết nối nhưng cache vẫn tiếp tục tải dữ liệu.
- Một truy vấn chậm có thể giữ connection sau khi caller ban đầu không còn chờ.
- Công việc có side effect không nên được đưa vào cache nếu vòng đời thực thi cần phụ thuộc trực tiếp vào subscriber.

Đây không phải lúc nào cũng là điều xấu. Với cache dùng chung, việc tiếp tục một lần tải sau khi caller đầu tiên rời đi có thể hữu ích nếu subscriber khác sắp đến hoặc dữ liệu được dùng chung. Nhưng phải có timeout, giới hạn concurrency và chính sách tải lại để tránh các công việc mồ côi kéo dài.

Với share()/refCount, cancellation có ngữ nghĩa khác: khi subscriber cuối cùng hủy trước khi nguồn terminal, upstream thường được hủy. Không áp dụng quy tắc cancellation của share cho cache hoặc ngược lại.

## 11. Backpressure và kích thước replay

Cache/replay thêm một lớp lưu dữ liệu giữa upstream và subscriber. Điều đó có thể làm thay đổi cách demand và tốc độ tiêu thụ tác động lên nguồn. Một subscriber đến muộn có thể phải tiêu thụ lịch sử đã lưu trước khi nhận dữ liệu mới; một nguồn nhanh có thể tạo backlog nếu subscriber không theo kịp.

Hãy đánh giá:

- Số phần tử được lưu tối đa.
- Kích thước trung bình và kích thước cực đại của mỗi phần tử.
- Tốc độ phát và thời gian subscriber cần để đọc replay history.
- Số subscriber đồng thời.
- Chính sách khi subscriber chậm hoặc hủy.
- Nguồn có thể bị điều tiết bằng demand hay là nguồn nóng không thể dừng.

Giới hạn history theo số phần tử là một bước bảo vệ, nhưng không đủ nếu payload có kích thước không kiểm soát. Với dữ liệu lớn, có thể cần chỉ lưu ID hoặc snapshot nhỏ và để subscriber tải chi tiết theo nhu cầu.

Không dùng cache() thay cho hàng đợi bền vững hoặc event store. Nếu cần bảo toàn toàn bộ event qua restart, cần broker/log/database phù hợp. Cache trong bộ nhớ của một process không cung cấp durability.

## 12. Invalidation và tính mới của dữ liệu

Cache chỉ đúng khi thời gian sống của dữ liệu phù hợp với yêu cầu nghiệp vụ. Một giá sản phẩm, trạng thái tồn kho hoặc quyền truy cập có thể thay đổi nhanh hơn TTL đã chọn.

Trước khi cache, hãy trả lời:

1. Dữ liệu thay đổi bởi ai và qua những luồng nào?
2. Chấp nhận dữ liệu cũ trong bao lâu?
3. Có sự kiện invalidation khi cập nhật không?
4. Empty có được cache không?
5. Error có được cache không, và trong bao lâu?
6. Cache có phân vùng theo tenant, user, locale hoặc quyền không?
7. Khi nhiều request đồng thời miss cache, có cần single-flight để tránh stampede không?

TTL là một cơ chế hết hạn theo thời gian. Invalidation là phản ứng với một thay đổi cụ thể. Hai cơ chế có thể được dùng cùng nhau. Nếu dữ liệu phải nhất quán ngay sau khi cập nhật, chỉ TTL có thể không đủ.

Với cache cục bộ trong một instance, invalidation ở một instance không tự động xóa cache của instance khác. Hệ thống nhiều replica cần cơ chế đồng bộ hoặc cache phân tán có invalidation phù hợp.

## 13. Kiểm thử số lần thực thi và cache signal

Dùng AtomicInteger để chứng minh cache làm nguồn chỉ chạy một lần qua nhiều subscription:

~~~java
@Test
void cachedMonoRunsSourceOnce() {
    AtomicInteger calls = new AtomicInteger();

    Mono<Integer> cached = Mono.fromSupplier(calls::incrementAndGet)
        .cache();

    StepVerifier.create(cached)
        .expectNext(1)
        .verifyComplete();

    StepVerifier.create(cached)
        .expectNext(1)
        .verifyComplete();

    assertEquals(1, calls.get());
}
~~~

Kiểm thử empty caching:

~~~java
@Test
void cachedEmptyIsReplayed() {
    AtomicInteger calls = new AtomicInteger();

    Mono<String> cached = Mono.defer(() -> {
        calls.incrementAndGet();
        return Mono.empty();
    }).cache();

    StepVerifier.create(cached).verifyComplete();
    StepVerifier.create(cached).verifyComplete();

    assertEquals(1, calls.get());
}
~~~

Kiểm thử error caching:

~~~java
@Test
void cachedErrorIsReplayed() {
    AtomicInteger calls = new AtomicInteger();

    Mono<String> cached = Mono.defer(() -> {
        calls.incrementAndGet();
        return Mono.error(new IllegalStateException("temporary"));
    }).cache();

    StepVerifier.create(cached)
        .expectErrorMessage("temporary")
        .verify();

    StepVerifier.create(cached)
        .expectErrorMessage("temporary")
        .verify();

    assertEquals(1, calls.get());
}
~~~

Ba test này làm rõ cache lưu cả ba dạng terminal signal. Khi dùng TTL, nên kiểm thử trước và sau thời hạn bằng virtual time, tạo Publisher bên trong supplier của StepVerifier.withVirtualTime để scheduler giả lập được áp dụng đúng.

## 14. Kiểm thử share() và subscriber đến muộn

Với share, hãy dùng nguồn có thể điều khiển để quan sát subscriber tham gia trước hay sau khi event được phát. Ví dụ với Sinks:

~~~java
@Test
void shareDoesNotReplayPastValuesToLateSubscriber() {
    Sinks.Many<Integer> sink = Sinks.many().multicast().onBackpressureBuffer();
    Flux<Integer> shared = sink.asFlux().share();

    List<Integer> firstValues = new ArrayList<>();
    Disposable first = shared.subscribe(firstValues::add);

    assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));

    List<Integer> lateValues = new ArrayList<>();
    Disposable late = shared.subscribe(lateValues::add);

    assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));
    assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());

    first.dispose();
    late.dispose();

    assertEquals(List.of(1, 2), firstValues);
    assertEquals(List.of(2), lateValues);
}
~~~

Test này xác nhận subscriber đầu nhận cả hai event, còn subscriber đến sau event đầu chỉ nhận event phát sau khi nó tham gia. Do share không replay lịch sử, subscriber muộn không nhận lại giá trị 1. Với nguồn multicast có buffer, cần kiểm tra thêm hành vi khi không có subscriber và khi buffer đầy theo cấu hình sink.

Không dùng thời gian thực hoặc Thread.sleep để cố định thứ tự trong test. Dùng TestPublisher, Sinks, latch có giới hạn hoặc virtual time để tạo sự kiện tại thời điểm xác định.

## 15. Kiểm thử Context và rò dữ liệu giữa tenant

Một test quan trọng là xác minh Publisher cache không vô tình giữ kết quả theo Context của subscriber đầu tiên:

~~~java
@Test
void demonstratesContextCapturedBySharedCache() {
    Mono<String> cached = Mono.deferContextual(context ->
        Mono.just(context.get("tenantId"))
    ).cache();

    StepVerifier.create(
            cached.contextWrite(Context.of("tenantId", "tenant-a"))
        )
        .expectNext("tenant-a")
        .verifyComplete();

    StepVerifier.create(
            cached.contextWrite(Context.of("tenantId", "tenant-b"))
        )
        .expectNext("tenant-a")
        .verifyComplete();
}
~~~

Đây là test mô tả hành vi nguy hiểm để người đọc nhận ra cache đang chia sẻ kết quả giữa các context. Trong ứng dụng thật, không giữ cách triển khai này cho dữ liệu tenant-specific. Hãy thêm test cho thiết kế đã sửa, ví dụ cache được phân vùng theo tenant ID hoặc tạo nguồn riêng cho mỗi tenant, và xác nhận tenant-b chỉ nhận dữ liệu của tenant-b.

## 16. Chọn chính sách theo yêu cầu vòng đời

| Nhu cầu | Lựa chọn có thể phù hợp | Điều cần xác nhận |
|---|---|---|
| Một kết quả dùng chung, có TTL rõ | Mono.cache(ttl) | Cache value/empty/error, invalidation và Context |
| Giữ một số event gần nhất cho subscriber đến sau | Flux.cache(history) hoặc replay(history) | Memory, TTL, thứ tự replay |
| Chia sẻ event trực tiếp cho subscriber đang hoạt động | share() | Subscriber đến muộn, refCount và reconnect |
| Chỉ kết nối khi đủ số subscriber | publish().refCount(n) | Ngưỡng kết nối và cancellation |
| Kết nối thủ công, chủ sở hữu quản lý lifecycle | publish()/replay() cùng connect() | Dispose connection và cleanup |
| Lịch sử cần tồn tại qua restart | Broker hoặc event store bền vững | Retention, consumer offset và durability |
| Cache theo tenant/user/resource | Cache có key và invalidation rõ | Phân vùng quyền truy cập và stale data |

Không có một operator phù hợp cho mọi trường hợp. Lựa chọn phải bắt đầu từ yêu cầu: subscriber mới cần gì, dữ liệu được phép cũ bao lâu, ai sở hữu kết nối, nguồn có được hủy khi không còn subscriber và lỗi/empty được lưu như thế nào.

## 17. Những dấu hiệu cache/share đang gây lỗi

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Request sau nhận dữ liệu của request đầu | Cache Publisher phụ thuộc request hoặc Context | Test hai subscription với Context khác nhau |
| Dữ liệu không cập nhật sau khi ghi | Cache giữ snapshot cũ hoặc empty cũ | Kiểm tra TTL và invalidation |
| Dependency tiếp tục lỗi dù đã phục hồi | Error signal bị cache | Đếm số lần subscribe và kiểm tra TTL/error policy |
| Subscriber mới không nhận event vừa phát | Dùng share không replay | Kiểm tra yêu cầu replay và thời điểm subscribe |
| RAM tăng theo thời gian | Flux cache/replay giữ history quá lớn | Đo số phần tử, payload size và retention |
| Request đã cancel nhưng tải nguồn vẫn chạy | Cache đã khởi động upstream và tách lifecycle khỏi caller | Theo dõi subscription upstream và timeout |
| Dependency bị gọi nhiều lần khi subscriber đến muộn | Dùng cold Publisher không share/cache | Xác định có thực sự cần chia sẻ hay không |
| Kết quả phụ thuộc thứ tự subscriber | Mutable object hoặc Context được chụp ở upstream | Dùng immutable data và kiểm thử nhiều subscriber |

## 18. Quy trình quyết định trước khi thêm cache hoặc share

Trước khi thêm operator, hãy trả lời lần lượt:

1. **Nguồn hiện tại là cold hay hot?** Mỗi subscription có nên thực thi nguồn mới không?
2. **Ai cần chia sẻ dữ liệu?** Mọi subscriber hay chỉ các subscriber trong cùng request/tenant?
3. **Subscriber đến muộn cần gì?** Không nhận lịch sử, nhận snapshot mới nhất hay nhận một phần history?
4. **Nguồn kết thúc thế nào?** Complete, error hay chạy vô hạn? Có thể reconnect sau terminal signal không?
5. **Cancellation có phải dừng upstream không?** Nếu có, chọn share/refCount hoặc cơ chế lifecycle phù hợp và kiểm thử.
6. **Có cache empty/error không?** Đặt TTL riêng nếu API hỗ trợ và phù hợp nghiệp vụ.
7. **Dữ liệu có nhạy cảm hoặc mutable không?** Phân vùng theo key, dùng immutable snapshot và giữ authorization đúng ranh giới.
8. **Backpressure và memory được kiểm soát ra sao?** Giới hạn history, payload, queue và concurrency.
9. **Cache được invalidation khi nào?** Dựa trên TTL, event cập nhật hoặc phiên bản dữ liệu.
10. **Test chứng minh điều gì?** Đếm subscription, kiểm tra replay, error/empty, cancellation, Context và số lần gọi nguồn.

Cache và share thay đổi hợp đồng vòng đời của pipeline. cache() có thể biến kết quả đầu tiên, kể cả empty hoặc error, thành tín hiệu dùng chung; share() chia sẻ luồng đang hoạt động theo chính sách refCount; replay giữ lại một phần lịch sử cho subscriber đến sau. Khi xác định đúng phạm vi chia sẻ, TTL, invalidation, Context, cancellation và giới hạn bộ nhớ, ta mới có thể dùng các operator này như một quyết định kiến trúc có kiểm soát thay vì một tối ưu nhỏ làm thay đổi dữ liệu và hành vi của ứng dụng.
