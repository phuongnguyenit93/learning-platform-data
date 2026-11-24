# Bộ nhớ giữ bởi cache, replay, collect và groupBy

Một pipeline reactive có thể xử lý dữ liệu theo từng tín hiệu, nhưng điều đó không có nghĩa toàn bộ pipeline luôn dùng ít bộ nhớ. Một số operator chủ động giữ phần tử để phát lại cho subscriber đến sau, chờ nguồn hoàn tất rồi mới tạo kết quả tổng hợp, hoặc duy trì nhiều nhóm và hàng đợi riêng. Nếu số phần tử, thời gian sống hoặc số khóa không có giới hạn, lượng bộ nhớ được giữ có thể tăng liên tục.

Trong Reactor, cache và replay lưu tín hiệu để subscriber đến sau có thể nhận lại dữ liệu. Các operator collect tích lũy phần tử thành một cấu trúc kết quả như List hoặc Map. groupBy tạo một publisher con cho mỗi khóa và phải quản lý các nhóm đang hoạt động cùng phần tử đang chờ trong từng nhóm. Những operator này hữu ích khi semantics của ứng dụng cần chúng, nhưng mỗi operator đặt ra một mô hình lưu giữ khác nhau.

Bài học này giúp ước lượng bộ nhớ mà các operator giữ, chọn giới hạn theo số lượng hoặc thời gian, tránh tích lũy vô hạn và kiểm thử hành vi lưu giữ. Trọng tâm là hiệu năng và vòng đời của dữ liệu trong pipeline Reactor.

## 1. Reactive không đồng nghĩa với không lưu dữ liệu

Reactive Streams điều tiết việc truyền phần tử bằng demand. Subscriber yêu cầu một số lượng phần tử; publisher không được phát vượt quá số lượng đã yêu cầu. Cơ chế này giúp phối hợp tốc độ giữa upstream và downstream.

Backpressure không tự xóa dữ liệu mà operator đã quyết định lưu. Một operator có thể:

- Giữ phần tử trong cache để phát lại.
- Giữ các phần tử trong buffer cho đến khi downstream có demand.
- Tích lũy tất cả phần tử để tạo một List hoặc Map.
- Duy trì một queue cho mỗi nhóm do groupBy tạo ra.
- Prefetch một lượng dữ liệu để tăng throughput.

Vì vậy, cần phân biệt hai câu hỏi:

1. Downstream đang yêu cầu bao nhiêu phần tử?
2. Các operator ở giữa đang giữ bao nhiêu phần tử hoặc object trong bộ nhớ?

Một subscriber có thể chỉ yêu cầu một phần tử, trong khi một operator phía trước đã giữ hàng trăm phần tử. Ngược lại, một publisher có thể phát dữ liệu nhanh nhưng downstream xử lý ngay và không tích lũy, nên bộ nhớ vẫn ổn định.

## 2. Ước lượng chi phí bộ nhớ

Không thể ước lượng chính xác chỉ bằng số phần tử. Mỗi phần tử có thể là một object nhỏ hoặc một object graph lớn chứa chuỗi, danh sách, byte array và tham chiếu đến nhiều object khác. Queue và cấu trúc dữ liệu cũng có overhead.

Một mô hình ước lượng đơn giản:

    memory ≈ retainedElements × averageRetainedSize
              + queueAndIndexOverhead
              + activeGroupAndSubscriptionOverhead

Ví dụ, nếu một cache giữ 100.000 object và mỗi object cùng object graph chiếm trung bình 2 KiB, riêng dữ liệu đã vào khoảng 200 MiB, chưa tính queue, reference, header object, metadata và các bản sao do codec tạo ra.

Đây chỉ là ước lượng. Kích thước thực tế cần đo bằng heap dump, Java Flight Recorder hoặc profiler. Một giới hạn theo số phần tử không phải giới hạn byte tuyệt đối: 1.000 object chứa payload 1 KiB khác rất nhiều so với 1.000 object chứa payload 1 MiB.

Khi thiết kế, hãy giới hạn ít nhất một trong các chiều sau:

- Số phần tử được giữ.
- Thời gian lưu giữ.
- Kích thước payload.
- Số nhóm hoặc khóa đang hoạt động.
- Số subscription và tác vụ đồng thời.

Với dữ liệu lớn hoặc có kích thước biến động mạnh, thường cần kết hợp nhiều giới hạn.

## 3. cache giữ tín hiệu để phát lại

Flux.cache biến publisher thành một nguồn hot có lưu giữ tín hiệu. Nguồn upstream được subscribe khi subscriber đầu tiên đăng ký; các tín hiệu nhận được được lưu lại và phát cho subscriber đến sau theo chính sách cache.

Ví dụ:

    Flux<Event> cachedEvents =
        eventRepository.streamRecentEvents()
            .cache();

Subscriber đầu tiên kích hoạt nguồn. Subscriber đăng ký sau có thể nhận lại những sự kiện đã được cache, kể cả các tín hiệu terminal mà cache lưu giữ.

Điểm cần chú ý là cache không phải một buffer ngắn hạn mặc định. Với Flux.cache() không giới hạn history, tất cả phần tử được phát có thể được giữ lại trong thời gian cache còn được tham chiếu. Nếu nguồn là stream vô hạn, bộ nhớ có thể tăng theo tổng số phần tử đã phát.

Ví dụ không phù hợp cho một stream dài hạn:

    Flux<Metric> allMetrics =
        metricSource.liveMetrics()
            .cache();

Nếu metricSource phát liên tục, cache không giới hạn sẽ giữ lịch sử ngày càng dài. Một subscriber mới còn có thể phải xử lý một lượng lịch sử rất lớn trước khi nhận dữ liệu mới.

### 3.1. Giới hạn history theo số phần tử

Nếu chỉ cần phát lại một số phần tử gần nhất, dùng cache có giới hạn history:

    Flux<Event> recentEvents =
        eventRepository.streamEvents()
            .cache(500);

Cache giữ tối đa 500 phần tử gần nhất để phát lại cho subscriber đến sau. Giới hạn này phù hợp khi ứng dụng chỉ cần một cửa sổ lịch sử ngắn.

Giới hạn theo số lượng giúp chặn tăng trưởng do số phần tử, nhưng không giới hạn byte chính xác. Nếu mỗi Event chứa payload lớn, 500 phần tử vẫn có thể chiếm nhiều bộ nhớ.

### 3.2. Giới hạn history theo thời gian

Có thể đặt TTL cho các tín hiệu cache:

    Flux<Event> recentEvents =
        eventRepository.streamEvents()
            .cache(Duration.ofMinutes(2));

Các tín hiệu được giữ theo chính sách thời gian của cache. TTL hữu ích khi subscriber đến muộn chỉ cần lịch sử gần đây.

TTL không đồng nghĩa với giới hạn số phần tử. Nếu nguồn phát một triệu sự kiện trong hai phút, cache theo thời gian vẫn có thể giữ một lượng rất lớn dữ liệu trong khoảng TTL đó.

TTL xác định thời điểm tín hiệu không còn hợp lệ để replay theo semantics của cache. Nó không bảo đảm heap giảm đúng thời điểm hết hạn: việc giải phóng tham chiếu và thu hồi bộ nhớ còn phụ thuộc cơ chế dọn dẹp của operator và garbage collector.

### 3.3. Kết hợp giới hạn số lượng và thời gian

Khi cần giới hạn cả độ dài lịch sử lẫn thời gian lưu, dùng overload cache có history và TTL:

    Flux<Event> recentEvents =
        eventRepository.streamEvents()
            .cache(500, Duration.ofMinutes(2));

Trong ví dụ, cache chỉ giữ tối đa 500 phần tử gần nhất và áp dụng TTL hai phút. Hai giới hạn bổ sung cho nhau:

- History cap giới hạn số phần tử được giữ.
- TTL giới hạn thời gian phần tử cũ còn có thể được phát lại.

Hãy kiểm tra overload có trong version reactor-core mà dự án đang dùng. Các overload và tùy chọn timer có thể khác nhau theo version.

## 4. Cache cả giá trị, empty và lỗi

Mono.cache cũng lưu kết quả terminal để những subscriber sau không phải gọi lại nguồn:

    Mono<Product> cachedProduct =
        productClient.findById(productId)
            .cache();

Mono có thể kết thúc bằng một giá trị, hoàn tất rỗng hoặc lỗi. Cache của Mono lưu tín hiệu kết thúc tương ứng; do đó lỗi cũng có thể được phát lại cho subscriber sau. Nếu lỗi là tạm thời, việc cache lỗi vô thời hạn có thể khiến các request tiếp theo tiếp tục nhận lỗi dù dịch vụ bên ngoài đã phục hồi.

Hãy cân nhắc TTL hoặc chính sách cache riêng cho giá trị, empty và lỗi nếu version Reactor đang dùng hỗ trợ. Không cache lỗi tạm thời lâu như dữ liệu thành công nếu semantics nghiệp vụ không cho phép.

Một điểm khác là cache được gắn với instance publisher. Nếu mỗi lần gọi method đều tạo một Mono mới rồi cache trên instance đó, các lần gọi độc lập vẫn tạo cache độc lập:

    Mono<Product> find(String id) {
        return productClient.findById(id).cache();
    }

Đoạn mã này không tạo một cache toàn cục theo id. Để chia sẻ kết quả giữa nhiều request, cần một nơi lưu trữ có key, giới hạn kích thước, TTL và chính sách invalidation rõ ràng. Không dùng một Map không giới hạn trong singleton service để thay thế cache chuyên dụng.

## 5. Vòng đời và cancellation của cache

Cache thay đổi semantics của nguồn. Một publisher cold thông thường có thể thực hiện công việc riêng cho mỗi subscription. Sau khi thêm cache, upstream được chia sẻ và tín hiệu được lưu để phát lại.

Điều này có một số hệ quả:

- Subscriber đầu tiên có thể kích hoạt kết nối upstream.
- Subscriber đến sau có thể nhận dữ liệu đã phát trước đó.
- Hủy một subscriber không đồng nghĩa cache bị xóa.
- Cache có thể tiếp tục duy trì nguồn và lịch sử theo semantics của operator.
- Lỗi và complete có thể được lưu để phát lại.

Không dùng cache như cơ chế quản lý vòng đời một kết nối streaming nếu ứng dụng cần dừng upstream khi không còn subscriber. Khi cần kết nối được chia sẻ trong lúc có subscriber và ngắt khi subscriber rời đi, xem xét publish().refCount() hoặc share() với semantics phù hợp.

share() không phát lại lịch sử cho subscriber đến sau như cache. Nó chia sẻ tín hiệu hiện tại giữa các subscriber đang kết nối. Hãy chọn theo yêu cầu:

| Nhu cầu | Operator gợi ý |
|---|---|
| Lưu và phát lại lịch sử gần nhất | cache(history) hoặc replay(history) |
| Chia sẻ tín hiệu hiện tại, không cần lịch sử | share() |
| Kết nối khi đủ subscriber và ngắt khi số subscriber giảm dưới ngưỡng | publish().refCount(n) |
| Điều khiển thủ công thời điểm kết nối | publish() hoặc replay() rồi gọi connect() |

## 6. replay và bộ đệm của ConnectableFlux

replay tạo một ConnectableFlux có khả năng lưu các tín hiệu để subscriber đến sau nhận lại. Khác với cache, ConnectableFlux cho phép điều khiển lúc kết nối upstream bằng connect, autoConnect hoặc refCount.

Ví dụ:

    ConnectableFlux<Event> replayed =
        eventSource.events()
            .replay(100);

    replayed.connect();

replay(100) giữ lịch sử tối đa 100 phần tử cho subscriber đến sau. Lệnh connect() bắt đầu kết nối nguồn. Ứng dụng có thể đăng ký subscriber trước hoặc sau thời điểm connect tùy semantics mong muốn.

Có thể để publisher tự kết nối khi subscriber đầu tiên đến:

    Flux<Event> sharedRecent =
        eventSource.events()
            .replay(100)
            .autoConnect(1);

autoConnect(1) kết nối upstream khi có ít nhất một subscriber. Kết nối không tự ngắt chỉ vì subscriber cuối cùng rời đi; nếu cần quản lý số subscriber và disconnect, dùng refCount hoặc quản lý Disposable trả về từ connect.

### 6.1. Giới hạn replay theo số lượng

replay(history) giới hạn số phần tử lịch sử được giữ. Đây là lựa chọn tốt khi chỉ cần một cửa sổ số lượng cố định, ví dụ 100 sự kiện gần nhất để subscriber mới đồng bộ trạng thái.

### 6.2. Replay không giới hạn

replay() không có giới hạn history có thể giữ toàn bộ tín hiệu để phát lại. Với nguồn vô hạn, đây là nguy cơ tăng trưởng heap tương tự cache không giới hạn.

### 6.3. Replay theo thời gian

Một số overload replay cho phép giới hạn lịch sử theo TTL. Chọn history cap kết hợp TTL nếu tải có thể tăng đột biến trong khoảng thời gian ngắn. Xác nhận API overload trong version Reactor của dự án.

## 7. cache và replay khác nhau ở điểm nào?

Hai operator đều có thể lưu lịch sử và phát lại tín hiệu, nhưng mô hình điều khiển kết nối khác nhau:

| Đặc điểm | cache | replay |
|---|---|---|
| Kiểu kết quả | Flux hoặc Mono đã cache | ConnectableFlux |
| Bắt đầu upstream | Khi subscriber đầu tiên đăng ký | Khi gọi connect, autoConnect hoặc refCount |
| Lưu lịch sử | Có | Có |
| Điều khiển connection | Ít trực tiếp hơn | Có thể điều khiển rõ ràng |
| Quản lý subscriber | Cache phục vụ các subscriber đến sau | Kết hợp connect/refCount/autoConnect |
| Trường hợp phù hợp | Cache tín hiệu đơn giản theo instance | Multicast cần điều khiển kết nối và replay |

Không chọn cache chỉ vì muốn chia sẻ publisher. Nếu chỉ cần multicast dữ liệu trực tiếp cho subscriber đang hoạt động, share có thể phù hợp hơn và không giữ lịch sử dài hạn.

## 8. collect tích lũy dữ liệu cho đến khi nguồn kết thúc

Các operator collect biến nhiều tín hiệu thành một kết quả tổng hợp. Chúng thường phải giữ dữ liệu trong bộ nhớ cho đến khi upstream complete.

Ví dụ collectList:

    Mono<List<Order>> allOrders =
        orderRepository.findAll()
            .collectList();

collectList giữ mọi Order được phát rồi chỉ phát List khi nguồn hoàn tất. Bộ nhớ tăng theo số lượng bản ghi.

Với nguồn hữu hạn và kích thước có giới hạn, collectList có thể phù hợp. Với bảng lớn hoặc stream vô hạn, nó có thể gây áp lực heap hoặc không bao giờ phát kết quả.

Ví dụ nguy hiểm:

    Mono<List<Metric>> allMetrics =
        metricSource.liveMetrics()
            .collectList();

Nếu nguồn không complete, Mono này không phát danh sách. Trong lúc chờ, nó tiếp tục tích lũy phần tử.

### 8.1. collectMap

collectMap giữ một giá trị cho mỗi khóa:

    Mono<Map<String, DeviceStatus>> statusByDevice =
        statusEvents.collectMap(DeviceStatus::deviceId);

Bộ nhớ tăng theo số khóa duy nhất. Nếu khóa có cardinality lớn hoặc tăng liên tục, Map có thể lớn không giới hạn. Nếu nhiều phần tử có cùng key, giá trị sau có thể thay thế giá trị trước theo semantics của collectMap.

### 8.2. collectMultimap

collectMultimap giữ danh sách giá trị cho mỗi khóa:

    Mono<Map<String, Collection<Event>>> eventsByTenant =
        events.collectMultimap(Event::tenantId);

Khác collectMap, operator này giữ nhiều phần tử cho mỗi key. Tổng số phần tử vẫn được giữ trong bộ nhớ, nên chi phí tăng theo tổng số sự kiện chứ không chỉ số tenant.

### 8.3. collectSortedList

collectSortedList cần giữ các phần tử trước khi sắp xếp:

    Mono<List<Order>> sortedOrders =
        orders.collectSortedList(
            Comparator.comparing(Order::createdAt)
        );

Chi phí bộ nhớ O(n) theo số phần tử, cùng chi phí CPU sắp xếp thường O(n log n). Không dùng cho stream không giới hạn. Nếu cần sắp xếp dữ liệu lớn, hãy để database sắp xếp theo index và đọc theo trang, hoặc dùng external sort/job có giới hạn tài nguyên.

### 8.4. reduce không phải lúc nào cũng dùng bộ nhớ hằng số

reduce thường giữ một accumulator:

    Mono<Long> total =
        orderAmounts.reduce(0L, Long::sum);

Accumulator là một số Long, nên bộ nhớ giữ gần như hằng số theo số phần tử. Nhưng nếu accumulator là List hoặc Map và mỗi bước thêm dữ liệu, nó vẫn tăng theo kích thước đầu vào:

    Mono<List<Event>> accumulated =
        events.reduceWith(
            ArrayList::new,
            (list, event) -> {
                list.add(event);
                return list;
            }
        );

Đoạn mã này có bản chất tích lũy toàn bộ dữ liệu như collectList. reduceWith nhận supplier để tạo accumulator mới cho mỗi subscription; nếu dùng một object mutable được tạo sẵn làm seed cho nhiều subscription, các lần subscribe có nguy cơ dùng chung trạng thái. Đừng đánh giá chi phí chỉ dựa trên tên operator; hãy xem kích thước accumulator có tăng theo số phần tử hay không.

## 9. Giữ collect trong giới hạn

Nếu cần tổng hợp một tập hữu hạn, hãy giới hạn nguồn trước khi collect:

    Mono<List<Event>> firstThousand =
        eventSource.events()
            .take(1_000)
            .collectList();

take(1_000) giới hạn tổng số phần tử đi vào collectList. Danh sách tối đa 1.000 phần tử, dù kích thước byte vẫn phụ thuộc payload từng Event.

Nếu cần tổng hợp theo batch, dùng buffer với kích thước hữu hạn:

    Flux<BatchResult> batches =
        eventSource.events()
            .buffer(500)
            .concatMap(batch ->
                batchProcessor.process(batch)
            );

Mỗi batch chứa tối đa 500 phần tử. concatMap xử lý từng batch theo thứ tự và chỉ chạy một inner publisher tại một thời điểm. Tuy nhiên, concatMap vẫn có thể prefetch các batch tiếp theo vào queue. Nếu muốn giới hạn prefetch xuống một batch, dùng overload có tham số prefetch:

    Flux<BatchResult> batches =
        eventSource.events()
            .buffer(500)
            .concatMap(
                batch -> batchProcessor.process(batch),
                1
            );

Nếu dùng flatMap, nhiều batch có thể cùng được xử lý và tồn tại trong bộ nhớ; cần giới hạn concurrency, prefetch và tính tổng số phần tử đang chờ.

Với stream vô hạn, có thể dùng bufferTimeout để đóng batch khi đủ số lượng hoặc hết thời gian:

    Flux<BatchResult> batches =
        eventSource.events()
            .bufferTimeout(
                500,
                Duration.ofSeconds(2)
            )
            .filter(batch -> !batch.isEmpty())
            .concatMap(batchProcessor::process, 1);

Batch bị giới hạn theo số phần tử và thời gian, nhưng downstream vẫn phải xử lý đủ nhanh hoặc có chính sách khi quá tải. Buffer theo thời gian có thể phát các batch nhỏ khi nguồn chậm.

## 10. groupBy tạo nhóm và queue riêng

groupBy phân phối phần tử vào các GroupedFlux dựa trên khóa:

    Flux<GroupedFlux<String, Event>> groups =
        eventSource.events()
            .groupBy(Event::tenantId);

Mỗi GroupedFlux đại diện cho một khóa. Khi phần tử có key mới xuất hiện, group tương ứng được phát ra downstream. Những phần tử cùng key được chuyển vào cùng group.

Ví dụ tổng hợp số sự kiện theo tenant:

    record TenantCount(String tenantId, long count) {}

    Flux<TenantCount> counts =
        eventSource.events()
            .groupBy(Event::tenantId)
            .flatMap(group ->
                group.count()
                    .map(count ->
                        new TenantCount(group.key(), count)
                    ),
                16
            );

flatMap subscribe vào từng group và đếm số phần tử của group đó. Ví dụ phù hợp khi số tenant đồng thời được giới hạn và mọi group đều được tiêu thụ.

group.count() chỉ phát kết quả khi group hoàn tất. Với một nguồn sự kiện vô hạn, các group thường vẫn mở nên count sẽ không phát cho đến khi nguồn kết thúc. Với luồng liên tục, hãy dùng cửa sổ thời gian/batch hoặc accumulator cập nhật dần nếu cần kết quả định kỳ.

### 10.1. Bộ nhớ của groupBy

groupBy cần quản lý:

- Metadata cho mỗi khóa và GroupedFlux.
- Queue chứa phần tử đang chờ consumer của group.
- Subscription và trạng thái terminal của từng group.
- Các group đang được downstream xử lý.

Nếu nguồn có hàng triệu khóa khác nhau, số group có thể rất lớn. Nếu downstream xử lý chậm hoặc không subscribe vào group, phần tử có thể tích lũy trong queue và upstream có thể bị backpressure.

groupBy không phải cache toàn bộ lịch sử theo cách cache làm, nhưng các queue và group đang hoạt động vẫn giữ tham chiếu đến dữ liệu. Vì vậy, số lượng khóa và tốc độ tiêu thụ nhóm là hai biến quan trọng đối với bộ nhớ.

### 10.2. Mỗi group cần được tiêu thụ

GroupedFlux được phát ra cần được subscribe và tiêu thụ. Các group là unicast: không thiết kế để nhiều subscriber độc lập cùng đọc một group. Nếu một group không được drain, queue của nó có thể giữ phần tử và gây backpressure cho nguồn.

Hãy tránh tạo group rồi bỏ qua một số group mà không có chính sách rõ ràng. Nếu chỉ cần một số khóa, lọc theo key trước hoặc dùng chiến lược phân vùng khác thay vì mở hàng nghìn group rồi không tiêu thụ.

### 10.3. Concurrency của flatMap phải phù hợp với số group

groupBy kết hợp với flatMap có một bẫy quan trọng. flatMap giới hạn số inner publisher được subscribe đồng thời. Nếu số group cần được tiêu thụ lớn hơn concurrency và các group chưa được subscribe tiếp tục giữ dữ liệu, nguồn có thể không tiến triển để hoàn tất.

Ví dụ, flatMap với concurrency 4 chỉ subscribe tối đa bốn group cùng lúc. Nếu nguồn tạo nhiều group hơn và các group còn lại cần được drain để upstream tiếp tục, pipeline có thể bị đình trệ.

Với groupBy, hãy bảo đảm:

- Cardinality của key có giới hạn hợp lý.
- Mọi group được tiêu thụ.
- Concurrency đủ để xử lý các group đang hoạt động theo thiết kế.
- Prefetch và queue được tính trong ngân sách bộ nhớ.

Tăng concurrency có thể tăng số group được xử lý cùng lúc và tăng bộ nhớ. Nếu cardinality rất lớn hoặc không biết trước, groupBy có thể không phải operator phù hợp.

## 11. Khi nào nên tránh groupBy?

Không dùng groupBy chỉ để gom mọi bản ghi theo một trường có hàng triệu giá trị khác nhau. Một số lựa chọn khác:

- Dùng truy vấn database có GROUP BY nếu phép tổng hợp có thể thực hiện ở database.
- Dùng window hoặc buffer để xử lý theo batch hữu hạn.
- Dùng partition key có cardinality giới hạn.
- Dùng Map accumulator có giới hạn kích thước và chính sách eviction nếu chỉ cần aggregate state.
- Đưa dữ liệu vào broker phân vùng theo key nếu cần xử lý lâu dài theo từng partition.

Ví dụ, nếu chỉ cần đếm số sự kiện theo tenant và tenant có cardinality rất lớn, có thể thực hiện aggregate ở database:

    SELECT tenant_id, COUNT(*)
    FROM event_log
    WHERE created_at >= :since
    GROUP BY tenant_id;

Database có thể dùng hash aggregate hoặc sort aggregate; nó cũng tiêu thụ tài nguyên, nhưng có thể tận dụng execution engine, index và giới hạn workload. So sánh chi phí thực tế thay vì mặc định rằng aggregate trong ứng dụng luôn nhẹ hơn.

## 12. Tương tác giữa cache, collect và groupBy

Rủi ro bộ nhớ tăng mạnh khi ghép nhiều operator giữ dữ liệu:

    Flux<List<Event>> result =
        source
            .cache()
            .groupBy(Event::tenantId)
            .flatMap(group ->
                group.collectList()
            );

Pipeline minh họa này có nhiều lớp giữ dữ liệu:

1. cache giữ lịch sử toàn bộ tín hiệu.
2. groupBy tạo group và queue theo key.
3. collectList giữ toàn bộ phần tử của từng group đến khi group hoàn tất.

Nếu nguồn vô hạn, cache không giới hạn tiếp tục tăng. Các group có thể không hoàn tất cho đến khi upstream kết thúc, nên collectList bên trong mỗi group có thể không phát kết quả trong thời gian dài. Đây là cấu trúc đặc biệt nguy hiểm với nguồn liên tục.

Hãy đặt câu hỏi cho từng operator:

- Dữ liệu nào được giữ?
- Giữ đến khi nào?
- Có giới hạn theo số lượng, thời gian hoặc byte không?
- Điều gì xảy ra khi subscriber hủy?
- Operator có giữ nguồn mở hoặc giữ connection không?
- Có thể xử lý theo batch hoặc aggregate sớm hơn không?

Không thêm cache trước groupBy chỉ để “phòng khi subscriber đến muộn” nếu không có yêu cầu replay rõ ràng. Không collect từng group nếu chỉ cần count hoặc sum; hãy dùng accumulator nhỏ.

## 13. Các lựa chọn thay thế có giới hạn rõ

| Yêu cầu | Operator/cách làm | Bộ nhớ được giữ |
|---|---|---|
| Chỉ phát lại 100 phần tử gần nhất | cache(100) hoặc replay(100) | Tối đa 100 phần tử lịch sử, cộng overhead |
| Chỉ giữ lịch sử trong hai phút | cache(Duration) hoặc replay theo TTL | Phụ thuộc tốc độ phát trong TTL |
| Giữ số lượng và thời gian cùng lúc | cache(history, ttl) | Bị chặn bởi cả hai chiều |
| Tổng hợp một trang hữu hạn | take(n).collectList() | Tối đa n phần tử |
| Xử lý theo batch | buffer(n).concatMap(..., 1) | Batch đang xử lý và tối đa một batch prefetch |
| Đếm số phần tử | count hoặc reduce với Long | Accumulator kích thước cố định |
| Cộng tổng | reduce với số hoặc kiểu tổng hợp nhỏ | Accumulator kích thước cố định |
| Nhóm theo khóa có cardinality nhỏ | groupBy với consumer cho mọi group | Metadata nhóm và queue đang chờ |
| Nhóm theo cardinality rất lớn | Database aggregation hoặc partitioned processing | Phân tán theo tài nguyên được quản lý |

Một operator không có giới hạn tham số không nhất thiết luôn sai. Nó có thể phù hợp với một tập dữ liệu hữu hạn đã được giới hạn bởi truy vấn hoặc nghiệp vụ. Điều quan trọng là giới hạn đó phải được chứng minh ở nguồn và được duy trì khi dữ liệu tăng.

## 14. Đọc và ghi dữ liệu theo luồng thay vì giữ lịch sử

Nếu downstream chỉ cần xử lý mỗi phần tử một lần, hãy giữ pipeline dạng stream:

    Mono<Void> persistAll =
        eventRepository.streamPending()
            .concatMap(event ->
                archiveRepository.save(toArchiveRecord(event))
            )
            .then();

concatMap xử lý từng event tuần tự trong subscription này. Pipeline không tạo một List chứa toàn bộ event.

Nếu có thể xử lý song song, đặt concurrency có giới hạn:

    Mono<Void> persistConcurrently =
        eventRepository.streamPending()
            .flatMap(
                event -> archiveRepository.save(
                    toArchiveRecord(event)
                ),
                8
            )
            .then();

Tối đa tám thao tác inner được subscribe đồng thời theo cấu hình flatMap. Hãy tính cả dữ liệu prefetch, request đang chờ và payload của từng event khi ước lượng bộ nhớ.

Nếu việc lưu archive là side effect cần giữ thứ tự, dùng concatMap hoặc cơ chế sequence ở tầng lưu trữ. Không dùng flatMap chỉ để tăng tốc khi thứ tự là invariant nghiệp vụ.

## 15. Kiểm thử semantics lưu giữ

Test nên xác nhận phần tử được phát lại, giới hạn history, hành vi terminal và việc group được tiêu thụ đúng cách. Có thể dùng TestPublisher và StepVerifier.

Ví dụ cache chỉ giữ hai phần tử gần nhất:

    TestPublisher<Integer> source =
        TestPublisher.create();

    Flux<Integer> cached =
        source.flux().cache(2);

    StepVerifier.create(cached)
        .then(() -> source.next(1, 2, 3))
        .then(source::complete)
        .expectNext(1, 2, 3)
        .verifyComplete();

    StepVerifier.create(cached)
        .expectNext(2, 3)
        .verifyComplete();

Subscriber đầu tiên nhận đủ dữ liệu khi nguồn phát. Subscriber thứ hai chỉ nhận hai phần tử cuối được cache. Test này kiểm tra giới hạn history theo số lượng.

Ví dụ collectList chỉ phát sau khi nguồn hoàn tất:

    TestPublisher<Integer> source =
        TestPublisher.create();

    Mono<List<Integer>> collected =
        source.flux().collectList();

    StepVerifier.create(collected)
        .then(() -> source.next(4, 5))
        .then(source::complete)
        .expectNext(List.of(4, 5))
        .verifyComplete();

Ví dụ groupBy với số khóa nhỏ và tất cả group đều được tiêu thụ:

    record Event(String tenantId, int value) {}
    record GroupCount(String tenantId, long count) {}

    Flux<GroupCount> counts =
        Flux.just(
                new Event("A", 1),
                new Event("B", 2),
                new Event("A", 3)
            )
            .groupBy(Event::tenantId)
            .flatMap(group ->
                group.count()
                    .map(count ->
                        new GroupCount(group.key(), count)
                    ),
                2
            );

    StepVerifier.create(
            counts.collectMap(
                GroupCount::tenantId,
                GroupCount::count
            )
        )
        .expectNext(Map.of("A", 2L, "B", 1L))
        .verifyComplete();

flatMap có thể phát kết quả group theo thứ tự hoàn tất, nên test không giả định thứ tự A rồi B. Ở đây chỉ có hai group hữu hạn; collectMap tạo kết quả nhỏ để so sánh nội dung không phụ thuộc thứ tự.

Test đơn vị không chứng minh heap luôn nằm dưới một số byte. Để đánh giá bộ nhớ, hãy chạy tải có kiểm soát với payload đại diện, đo heap sau warm-up, quan sát GC và kiểm tra heap dump khi có tăng trưởng bất thường.

## 16. Quan sát bộ nhớ và tìm nguồn giữ tham chiếu

Khi heap tăng, hãy xác định object nào còn được giữ và đường tham chiếu từ GC root:

- Cache hoặc replay buffer có đang giữ lịch sử dài không?
- Có Mono<List<T>> hoặc collectList đang chờ nguồn complete không?
- collectMap hoặc collectMultimap có cardinality tăng không?
- groupBy có tạo quá nhiều group hoặc group không được drain không?
- Có queue từ publishOn, flatMap, onBackpressureBuffer hoặc scheduler không?
- Subscriber đã hủy nhưng một cache hoặc task chia sẻ vẫn giữ nguồn không?
- Một singleton, static field hoặc closure có giữ publisher/cache lâu hơn dự kiến không?

Các công cụ như Java Flight Recorder, heap dump, Eclipse MAT hoặc profiler có thể chỉ ra object chiếm heap và đường giữ tham chiếu. Metric về số group, queue depth, số subscriber và tốc độ phát/tiêu thụ giúp phát hiện xu hướng trước khi heap cạn.

Không suy luận rò rỉ bộ nhớ chỉ từ một lần heap tăng. JVM có thể giữ heap đã cấp phát sau GC để tái sử dụng. Hãy quan sát retained heap sau các chu kỳ GC và xem object có còn được tham chiếu bởi GC root hay không.

## 17. Những lỗi thiết kế thường gặp

**Dùng cache() không giới hạn cho stream vô hạn.** Lịch sử tăng theo tổng số tín hiệu. Chọn history cap, TTL hoặc không cache nếu không cần replay.

**Cho rằng TTL tự giới hạn số phần tử.** Tốc độ phát cao có thể tạo rất nhiều phần tử trong TTL. Kết hợp history cap khi cần.

**Dùng cache để chia sẻ mọi request.** Cache gắn với publisher instance; cần key, invalidation và TTL rõ nếu muốn cache kết quả theo nghiệp vụ.

**Quên cache cả lỗi.** Subscriber sau có thể nhận lại lỗi cũ. Chọn TTL hoặc chính sách khác nếu lỗi có thể tạm thời.

**Collect toàn bộ một nguồn không giới hạn.** collectList, collectMultimap và collectSortedList giữ dữ liệu đến terminal. Giới hạn nguồn hoặc xử lý theo batch.

**Cho rằng reduce luôn dùng O(1) bộ nhớ.** Kích thước phụ thuộc accumulator. Một accumulator List vẫn tăng theo số phần tử.

**Dùng groupBy với cardinality không giới hạn.** Số group và queue có thể tăng mạnh. Cân nhắc aggregate tại database hoặc phân vùng khác.

**Không drain mọi GroupedFlux.** Group chưa được tiêu thụ có thể giữ queue và gây đình trệ upstream.

**Đặt flatMap concurrency thấp hơn số group cần drain.** Các group chưa được subscribe có thể làm pipeline không tiến triển. Chọn concurrency dựa trên cardinality và ngân sách bộ nhớ.

**Ghép cache, groupBy và collectList mà không tính tổng chi phí.** Mỗi operator giữ một lớp dữ liệu khác nhau; tổng retained heap có thể lớn hơn nhiều so với dự kiến.

**Nhầm backpressure với giới hạn heap.** Backpressure điều tiết demand; operator tích lũy vẫn có thể giữ dữ liệu theo chính sách riêng.

## 18. Checklist trước khi dùng operator giữ dữ liệu

Trước khi thêm cache, replay, collect hoặc groupBy, hãy trả lời:

1. Subscriber đến sau có thực sự cần nhận lại lịch sử không?
2. Cache/replay giữ tối đa bao nhiêu phần tử và trong bao lâu?
3. Kích thước trung bình và lớn nhất của một phần tử là bao nhiêu?
4. Cache có lưu cả lỗi hoặc empty signal không?
5. Ai sở hữu publisher và cache tồn tại trong bao lâu?
6. Nguồn có thể vô hạn hoặc phát với tốc độ đột biến không?
7. collect có nhận nguồn hữu hạn với giới hạn đã biết không?
8. Accumulator của reduce có tăng theo số phần tử không?
9. groupBy có cardinality khóa tối đa bao nhiêu?
10. Mọi group có được subscribe và drain không?
11. flatMap concurrency và prefetch có phù hợp số group không?
12. Có thể xử lý theo batch, window hoặc aggregate tại database không?
13. Cancellation có giải phóng subscription và tài nguyên đúng cách không?
14. Test đã xác nhận history cap, terminal signal, group consumption và hành vi khi tải lớn chưa?

cache, replay, collect và groupBy đều có thể giữ tham chiếu đến dữ liệu sau khi phần tử đã đi qua một operator. Cache và replay giữ lịch sử cho subscriber đến sau; collect giữ accumulator đến khi nguồn kết thúc; groupBy giữ group cùng các phần tử đang chờ được tiêu thụ. Muốn pipeline Reactor có bộ nhớ ổn định, hãy xác định rõ thời gian sống và cardinality của dữ liệu, đặt giới hạn hữu hạn, tiêu thụ mọi group và tránh gom toàn bộ nguồn vô hạn vào một cấu trúc trong heap.
