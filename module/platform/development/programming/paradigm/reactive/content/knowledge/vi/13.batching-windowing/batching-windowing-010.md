# Nhiều nhóm, nhóm không được tiêu thụ và nguy cơ tắc nghẽn

`groupBy` rất hữu ích khi một luồng sự kiện cần được xử lý riêng theo khóa, chẳng hạn gom cập nhật theo khách hàng, tài khoản hoặc thiết bị. Tuy nhiên, mỗi khóa tạo ra một `GroupedFlux` riêng. Nếu nguồn có quá nhiều khóa, nếu một nhóm không được subscribe hoặc nếu downstream chỉ tiêu thụ một số nhóm trong khi các nhóm khác tiếp tục nhận dữ liệu, các hàng đợi nội bộ có thể đầy và làm pipeline ngừng tiến triển.

Trong module `REACTIVE_PROGRAMMING`, người học thực hành các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời sử dụng `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Bài học này giải thích vòng đời của nhóm và cửa sổ, mối quan hệ giữa demand ở luồng ngoài với demand của từng luồng con, cũng như cách thiết kế để tránh tắc nghẽn khi chia nhóm.

## 1. `groupBy` tạo ra một luồng con cho mỗi khóa

`groupBy(keyMapper)` biến một `Flux<T>` thành `Flux<GroupedFlux<K, T>>`. Mỗi giá trị khóa khác nhau được quan sát sẽ tạo một nhóm. Các phần tử có cùng khóa được chuyển vào cùng `GroupedFlux`.

```java
Flux<GroupedFlux<String, OrderEvent>> groups = orderEvents
    .groupBy(OrderEvent::customerId);
```

Ví dụ, nguồn phát các sự kiện sau:

```text
customer=A: order-created
customer=B: payment-confirmed
customer=A: order-shipped
customer=C: order-created
customer=B: order-shipped
```

`groupBy` tạo ba nhóm A, B và C. Nhóm A nhận hai sự kiện của A theo thứ tự nguồn; nhóm B nhận hai sự kiện của B; nhóm C nhận một sự kiện. Mỗi nhóm có thể được xử lý bằng một pipeline riêng.

Mỗi `GroupedFlux` là một publisher đơn subscriber (*unicast*): một nhóm chỉ nên được subscribe một lần. Không chia sẻ cùng một `GroupedFlux` cho nhiều consumer độc lập bằng cách gọi `subscribe` nhiều lần. Nếu cần nhiều thành phần cùng quan sát một nhóm, hãy nhân bản hoặc chia sẻ dữ liệu bằng một operator phù hợp sau khi đã có một consumer sở hữu nhóm.

```java
Flux<ProcessedEvent> processed = orderEvents
    .groupBy(OrderEvent::customerId)
    .flatMap(group -> group.concatMap(event ->
        updateCustomer(group.key(), event)
    ));
```

Ở đây `flatMap` subscribe vào các nhóm được tạo ra, còn `concatMap` bên trong mỗi nhóm xử lý tuần tự các sự kiện của cùng một khách hàng. Các nhóm khác nhau có thể được xử lý đồng thời.

Điểm cần nhớ là `groupBy` không chỉ thêm một thuộc tính khóa vào phần tử. Nó tạo các publisher con có vòng đời và nhu cầu tiêu thụ riêng. Vì thế, downstream phải quản lý cả luồng chứa nhóm lẫn từng luồng nhóm.

## 2. Hai tầng demand phải cùng được đáp ứng

Sau `groupBy`, có hai tầng tiêu thụ:

1. **Luồng ngoài** phát các `GroupedFlux` mới. Subscriber của luồng ngoài cần request và nhận các nhóm.
2. **Từng luồng nhóm** phát các phần tử thuộc khóa đó. Mỗi nhóm cần được subscribe và được tiêu thụ để giải phóng các phần tử đang chờ.

Sơ đồ luồng dữ liệu:

```text
                    Flux<Event>
                         |
                      groupBy
                         |
             Flux<GroupedFlux<Key, Event>>
                  /       |       \
                 /        |        \
              Group A  Group B   Group C
                |        |         |
             consume  consume   consume
                \        |         /
                 \       |        /
                 downstream processing
```

Chỉ subscribe vào luồng ngoài là chưa đủ nếu các `GroupedFlux` được phát ra nhưng không được tiêu thụ. Một nhóm không được subscribe có thể giữ các phần tử trong hàng đợi nội bộ. Khi hàng đợi hoặc vùng prefetch bị lấp đầy, nhóm đó có thể ngăn `groupBy` tiếp tục lấy dữ liệu từ upstream. Khi nguồn không thể phát thêm, những nhóm khác cũng có thể ngừng nhận phần tử dù subscriber của chúng vẫn đang chờ.

Do đó, quy tắc cơ bản là: **mọi nhóm được tạo ra phải được tiêu thụ hoặc được xử lý bằng một chính sách loại bỏ có chủ đích**. Không tạo nhóm rồi bỏ quên publisher con.

## 3. Vì sao nhóm không được tiêu thụ có thể làm pipeline đứng lại?

Reactive Streams dùng demand để giới hạn số phần tử được phát. `groupBy` cần tiếp nhận phần tử nguồn, xác định khóa và chuyển phần tử vào hàng đợi của nhóm tương ứng. Nếu downstream không tiêu thụ một nhóm, phần tử thuộc nhóm đó vẫn cần nơi lưu tạm trong lúc chờ.

Một chuỗi sự kiện có thể diễn ra như sau:

1. Nguồn phát các sự kiện thuộc A, B và C.
2. `groupBy` tạo các nhóm tương ứng và đưa nhóm ra luồng ngoài.
3. Downstream chỉ subscribe vào A và B; nhóm C không được subscribe.
4. Nguồn tiếp tục phát nhiều sự kiện C. Các phần tử này tích lũy trong hàng đợi dành cho C.
5. Khi khả năng đệm hoặc lượng request đã cấp bị sử dụng hết, `groupBy` không thể tiếp tục nhận dữ liệu theo cách cần thiết.
6. Pipeline có thể ngừng tiến triển, kể cả khi A và B vẫn còn dữ liệu cần xử lý.

Đây là một dạng tắc nghẽn do backpressure và tiêu thụ không đầy đủ. Không nhất thiết có thread nào bị khóa; ứng dụng có thể chỉ đơn giản là không còn tín hiệu mới được chuyển xuống.

### Ví dụ dễ gây tắc nghẽn

```java
Flux<GroupedFlux<String, OrderEvent>> groups = orderEvents
    .groupBy(OrderEvent::customerId);

groups
    .filter(group -> group.key().equals("A"))
    .flatMap(group -> group);
```

Pipeline chỉ giữ nhóm A. Những nhóm khác bị loại bỏ khỏi luồng ngoài mà các phần tử bên trong chúng không được tiêu thụ. Với nguồn có nhiều sự kiện thuộc các khóa khác, những nhóm bị bỏ có thể tích lũy dữ liệu và làm `groupBy` ngừng tiến triển.

Nếu chỉ muốn xử lý khách hàng A, cách đơn giản và an toàn hơn là lọc sự kiện trước khi tạo nhóm:

```java
Flux<OrderEvent> customerAEvents = orderEvents
    .filter(event -> event.customerId().equals("A"));
```

Khi chỉ còn một khóa cần xử lý, không cần `groupBy`. Lọc trước giúp giảm số phần tử và tránh tạo những nhóm không cần thiết.

## 4. Khi cần bỏ một số nhóm, vẫn phải tiêu thụ chúng

Có trường hợp quyết định giữ hay bỏ chỉ có thể đưa ra sau khi nhóm đã được tạo, dựa trên `group.key()`. Nếu loại bỏ nhóm ở luồng ngoài, hãy đảm bảo publisher con bị loại vẫn được drain.

```java
Flux<ProcessedEvent> selected = orderEvents
    .groupBy(OrderEvent::customerId)
    .flatMap(group -> {
        if (isActiveCustomer(group.key())) {
            return group.concatMap(event -> process(event));
        }

        // Tiêu thụ và bỏ các phần tử của nhóm không được chọn.
        return group.thenMany(Flux.empty());
    });
```

Nhánh `group.thenMany(Flux.empty())` subscribe vào nhóm, drain các phần tử rồi hoàn tất mà không phát dữ liệu xuống. Cách này tránh để một nhóm bị bỏ quên. Tuy nhiên, nếu có rất nhiều nhóm không hoạt động hoặc nhóm tồn tại lâu dài, việc giữ một subscription cho từng nhóm vẫn tốn tài nguyên.

Nếu điều kiện lọc có thể kiểm tra trên từng sự kiện, hãy ưu tiên lọc trước `groupBy`:

```java
Flux<ProcessedEvent> selected = orderEvents
    .filter(event -> isActiveCustomer(event.customerId()))
    .groupBy(OrderEvent::customerId)
    .flatMap(group -> group.concatMap(this::process));
```

Lọc trước thường giảm cardinality của nhóm, giảm bộ nhớ và làm đơn giản vòng đời. Chỉ dùng cách drain nhóm bị loại khi quyết định thực sự phụ thuộc vào chính nhóm hoặc metadata chỉ có sau khi `groupBy` tạo nhóm.

## 5. Cardinality cao làm tăng số nhóm và trạng thái nội bộ

Một nhóm được tạo cho mỗi khóa khác nhau. Nếu nguồn có vài tenant cố định, số nhóm có thể nhỏ và dễ dự đoán. Nếu khóa là request ID, session ID hoặc một định danh gần như duy nhất cho từng sự kiện, số nhóm có thể tăng theo thời gian.

Ví dụ không phù hợp:

```java
Flux<GroupedFlux<UUID, RequestEvent>> byRequest = requestEvents
    .groupBy(RequestEvent::requestId);
```

Nếu mỗi request có một UUID riêng, gần như mỗi phần tử tạo ra một nhóm. Với nguồn dài hạn, cấu trúc nhóm và hàng đợi liên quan có thể tăng nhanh. `groupBy` không phải kho lưu trữ nhóm có TTL và không tự động loại bỏ nhóm chỉ vì một khoảng thời gian không có sự kiện.

Khi nguồn hoàn tất, các nhóm được hoàn tất theo vòng đời của nguồn. Với nguồn vô hạn hoặc kết nối lâu dài, nhóm có thể tiếp tục tồn tại miễn là nguồn còn hoạt động. Vì vậy, không nên dùng khóa có cardinality không giới hạn nếu không có chiến lược quản lý vòng đời và tài nguyên.

### Dấu hiệu cardinality đang quá cao

- Số nhóm mới tăng liên tục và không giảm.
- Heap tăng theo thời gian dù tốc độ xử lý mỗi phần tử ổn định.
- Độ trễ tăng khi số tenant, session hoặc thiết bị tăng.
- Nhiều publisher con được tạo nhưng có ít subscriber hoạt động.
- Pipeline ngừng phát dù một số nhóm vẫn có subscriber và đang chờ dữ liệu.
- Lượng phần tử chờ hoặc prefetch tăng, trong khi throughput downstream giảm.

Nên đo số nhóm đang hoạt động, số nhóm mới theo khoảng thời gian, kích thước hàng đợi, số subscriber nhóm và độ trễ xử lý. Không nên chỉ nhìn CPU: một pipeline bị backpressure có thể dùng CPU thấp nhưng vẫn không tiến triển.

## 6. `flatMap` concurrency phải phù hợp với số nhóm hoạt động

Một cách phổ biến để tiêu thụ nhóm là `flatMap`. Tuy nhiên, overload có giới hạn concurrency chỉ subscribe đồng thời vào một số publisher con nhất định.

```java
Flux<Result> results = events
    .groupBy(Event::tenantId)
    .flatMap(group -> group.concatMap(this::process), 8);
```

Ví dụ này chỉ cho phép tối đa tám nhóm được xử lý đồng thời. Nếu hệ thống đảm bảo có không quá tám nhóm hoạt động, giới hạn đó có thể phù hợp. Nếu nguồn có thể tạo nhiều nhóm hơn và các nhóm chưa được subscribe tiếp tục nhận phần tử, các hàng đợi của nhóm đang chờ có thể đầy. Khi đó, `groupBy` có thể bị tắc nghẽn.

Với cardinality nhỏ và có giới hạn rõ ràng, hãy chọn concurrency đủ để tiêu thụ mọi nhóm có thể hoạt động đồng thời:

```java
int maximumActiveTenants = 16;

Flux<Result> results = events
    .groupBy(Event::tenantId, 32)
    .flatMap(
        group -> group.concatMap(this::process),
        maximumActiveTenants
    );
```

Ở ví dụ này, giả định hệ thống có tối đa 16 tenant hoạt động trong subscription. `32` là prefetch được chọn cho `groupBy`; `16` là concurrency để subscribe và drain các nhóm. Các giá trị chỉ có ý nghĩa khi phù hợp với giới hạn thực tế của nguồn và khả năng xử lý.

Không nên giải quyết cardinality không giới hạn bằng cách đặt concurrency cực lớn một cách tùy tiện. Điều đó có thể tạo quá nhiều subscription con, công việc đồng thời và tài nguyên giữ lại. Nếu không thể xác định giới hạn số nhóm, hãy xem xét mô hình phân vùng hữu hạn hoặc một chiến lược xử lý khác.

### Vì sao `concatMap` ở tầng nhóm có thể không phù hợp?

```java
events
    .groupBy(Event::tenantId)
    .concatMap(group -> group.concatMap(this::process));
```

`concatMap` bên ngoài chỉ subscribe vào một nhóm tại một thời điểm. Với nguồn dài hạn, nhóm đầu tiên có thể không bao giờ hoàn tất vì nguồn tổng thể vẫn tiếp tục phát. Các nhóm tiếp theo không được subscribe và có thể tích lũy dữ liệu. Đây là một nguyên nhân phổ biến khiến pipeline `groupBy` kết hợp `concatMap` bên ngoài bị đứng.

Nếu cần xử lý tuần tự trong từng nhóm nhưng đồng thời giữa các nhóm, dùng `flatMap` ở tầng ngoài và `concatMap` ở tầng trong:

```java
events
    .groupBy(Event::tenantId)
    .flatMap(group -> group.concatMap(this::process));
```

Hãy nhớ rằng `flatMap` mặc định cũng có giới hạn concurrency. Nếu số nhóm có thể hoạt động đồng thời vượt giới hạn đó, cần đánh giá lại cardinality và khả năng drain nhóm.

## 7. Dùng `window` khi cần chia luồng thành các đoạn hữu hạn

`window` cũng tạo publisher con, nhưng ranh giới cửa sổ dựa trên số phần tử, thời gian hoặc điều kiện thay vì khóa. Ví dụ:

```java
Flux<Flux<Event>> windows = events.window(100);
```

Mỗi cửa sổ chứa tối đa 100 phần tử. Sau khi đủ số phần tử, cửa sổ hiện tại hoàn tất và một cửa sổ mới được tạo. Khác với `groupBy`, số cửa sổ tăng theo thời gian nhưng mỗi cửa sổ có vòng đời hữu hạn nếu điều kiện đóng được đáp ứng.

`window` cũng yêu cầu tiêu thụ các publisher con. Nếu cửa sổ được phát ra nhưng không được subscribe, các phần tử của cửa sổ có thể bị giữ lại và làm nguồn chậm hoặc ngừng tiến triển.

```java
Flux<BatchResult> results = events
    .windowTimeout(100, Duration.ofSeconds(1))
    .flatMap(window -> window
        .collectList()
        .filter(batch -> !batch.isEmpty())
        .flatMap(batch -> batchService.process(batch))
    );
```

Ví dụ tạo cửa sổ theo giới hạn 100 phần tử hoặc một giây, sau đó tiêu thụ từng cửa sổ bằng cách gom thành danh sách và xử lý. Vì mỗi cửa sổ được tiêu thụ trong `flatMap`, dữ liệu bên trong có subscriber. Nếu xử lý batch bất đồng bộ, có thể giới hạn concurrency của `flatMap` để kiểm soát số batch đang chạy; cần cân bằng giới hạn này với tốc độ tạo cửa sổ để tránh hàng đợi tăng không kiểm soát.

## 8. Dùng `buffer` khi không cần publisher con

Nếu mục tiêu chỉ là gom phần tử thành một collection, `buffer` thường đơn giản hơn `groupBy` hoặc `window`:

```java
Flux<BatchResult> results = events
    .bufferTimeout(100, Duration.ofSeconds(1))
    .filter(batch -> !batch.isEmpty())
    .concatMap(batch -> batchService.process(batch));
```

`bufferTimeout` phát `List<T>` khi đạt giới hạn kích thước hoặc thời gian. Downstream nhận collection trực tiếp, không cần subscribe thêm vào một `Flux` con. Điều này tránh lớp vòng đời publisher con có thể bị bỏ quên.

`buffer` vẫn có chi phí bộ nhớ. Hãy giới hạn kích thước và thời gian, đồng thời kiểm soát số batch đang được xử lý. Nếu dùng `flatMap` để xử lý nhiều batch đồng thời, hãy giới hạn concurrency; nếu thứ tự batch phải được giữ, dùng `concatMap`.

### Chọn operator theo cấu trúc dữ liệu cần có

| Nhu cầu | Operator phù hợp | Rủi ro chính |
|---|---|---|
| Gom theo khóa và xử lý riêng từng khóa | `groupBy` | Cardinality cao, nhóm không được tiêu thụ, số nhóm hoạt động lớn. |
| Chia thành các đoạn theo số lượng/thời gian | `window`, `windowTimeout` | Publisher con không được drain hoặc quá nhiều cửa sổ đang xử lý. |
| Gom thành danh sách theo số lượng/thời gian | `buffer`, `bufferTimeout` | Danh sách lớn hoặc nhiều batch đang chờ. |
| Chỉ lọc một số khóa cụ thể | `filter` trước `groupBy` | Nếu lọc sau `groupBy`, nhóm bị loại có thể không được drain. |

## 9. Chiến lược thay thế khi khóa có cardinality lớn

Nếu cần xử lý theo khóa nhưng số khóa không thể giới hạn, hãy cân nhắc thay đổi mô hình.

### Phân vùng thành số shard cố định

Thay vì tạo một nhóm cho mỗi tenant, có thể ánh xạ tenant vào một số shard hữu hạn:

```java
int shardCount = 32;

Flux<ShardEvent> sharded = events
    .groupBy(event -> Math.floorMod(
        event.tenantId().hashCode(), shardCount
    ))
    .flatMap(shard -> shard.concatMap(event ->
        processWithinShard(shard.key(), event)
    ), shardCount);
```

Số nhóm tối đa được giới hạn bởi `shardCount`. Các tenant khác nhau có thể rơi vào cùng shard và được xử lý tuần tự trong shard đó. Điều này có thể giảm concurrency nhưng giữ thứ tự tương đối trong mỗi shard. Cần đánh giá phân bố khóa để tránh một shard nóng làm giảm thông lượng.

Phân vùng theo hash không tự tạo thứ tự nghiệp vụ toàn cục. Nếu cần bảo đảm thứ tự theo từng tenant, các sự kiện của cùng tenant phải luôn ánh xạ vào cùng shard và bước xử lý trong shard phải tuần tự.

### Xử lý theo cửa sổ thay vì giữ nhóm sống lâu

Nếu nghiệp vụ chỉ cần tổng hợp trong từng phút hoặc từng khoảng ngắn, hãy dùng `window` hoặc `buffer` theo thời gian thay vì duy trì một nhóm lâu dài cho mỗi khóa. Sau khi cửa sổ hoàn tất, kết quả có thể được ghi ra kho lưu trữ và trạng thái tạm được giải phóng.

### Dùng kho trạng thái có TTL hoặc hệ thống phân vùng bên ngoài

Với dữ liệu có số khóa lớn, có thể lưu trạng thái theo khóa trong cache hoặc kho dữ liệu có chính sách TTL, hoặc phân vùng thông điệp tại broker. Pipeline reactive chỉ xử lý các partition hữu hạn. TTL và việc xóa trạng thái cần dựa trên yêu cầu nghiệp vụ; không nên xóa nhóm chỉ vì tạm thời không có sự kiện nếu một sự kiện đến muộn vẫn cần trạng thái trước đó.

## 10. Backpressure và các điểm cần giám sát

Khi `groupBy` tạo nhiều nhóm, backpressure xuất hiện ở cả luồng ngoài lẫn các luồng nhóm. Subscriber cần request nhóm mới và từng nhóm cần demand để lấy phần tử. `prefetch` ảnh hưởng đến lượng phần tử được yêu cầu trước, nhưng tăng prefetch không giải quyết được việc không tiêu thụ nhóm.

Một số chỉ số hữu ích:

- Số nhóm đang hoạt động và số nhóm được tạo trong mỗi khoảng thời gian.
- Số nhóm đã được subscribe, số nhóm đang chờ subscriber và số nhóm bị loại bỏ.
- Số phần tử được nhận, xử lý, bỏ qua và đang chờ theo từng shard hoặc nhóm.
- Độ trễ từ lúc nhận sự kiện đến lúc xử lý xong.
- Số batch/window đang mở và số batch đang xử lý đồng thời.
- Dung lượng heap, mức sử dụng queue và số lần phát hiện quá tải.

Nếu một nhóm xử lý chậm, các phần tử của nhóm đó có thể tích lũy. Tăng concurrency có thể giúp nếu tài nguyên downstream còn dư, nhưng cũng có thể làm quá tải cơ sở dữ liệu hoặc dịch vụ bên ngoài. Cần giới hạn cả số nhóm đang chạy và số yêu cầu trong mỗi nhóm.

Không nên dùng `onBackpressureBuffer()` như giải pháp chung cho một nhóm không được tiêu thụ. Buffer chỉ chuyển tắc nghẽn thành việc giữ thêm dữ liệu trong bộ nhớ; nếu nguồn tiếp tục nhanh hơn consumer, bộ nhớ vẫn có thể tăng đến giới hạn. Hãy giải quyết nguyên nhân bằng cách drain nhóm, giới hạn cardinality, giảm tải hoặc dùng một mô hình phân vùng khác.

## 11. Kiểm thử nhóm không được tiêu thụ và cardinality

`StepVerifier` có thể kiểm tra nhóm được tạo và các phần tử bên trong được chuyển đúng. Với `groupBy`, cần subscribe và drain từng nhóm trong bài kiểm thử.

```java
Flux<String> source = Flux.just(
    "A-1", "B-1", "A-2", "C-1", "B-2"
);

Flux<String> processed = source
    .groupBy(value -> value.substring(0, 1))
    .flatMap(group -> group.map(value -> group.key() + ":" + value));

StepVerifier.create(processed)
    .expectNextCount(5)
    .verifyComplete();
```

Không kiểm tra thứ tự xen kẽ toàn cục vì `flatMap` có thể phát kết quả theo lịch xử lý các nhóm. Có thể kiểm tra riêng thứ tự trong từng nhóm bằng cách thu thập kết quả theo khóa hoặc dùng nguồn và operator có tính đồng bộ trong bài kiểm thử.

Các tình huống cần kiểm thử:

1. Số khóa thấp và mọi nhóm đều được tiêu thụ.
2. Số khóa đạt giới hạn thiết kế và concurrency đủ để drain nhóm.
3. Nhóm bị loại được drain hoặc dữ liệu đã được lọc trước `groupBy`.
4. Nguồn dài hạn tiếp tục phát vào nhiều nhóm mà không để publisher con bị bỏ quên.
5. Một nhóm xử lý chậm trong khi các nhóm khác vẫn có thể tiến triển theo chính sách concurrency.
6. Lỗi trong một nhóm được xử lý theo chính sách; không để lỗi bị che giấu hoặc làm dừng nguồn ngoài ý muốn.
7. Cancel downstream làm hủy subscription và giải phóng tài nguyên thuộc nguồn.
8. Buffer hoặc window được tiêu thụ đầy đủ và có giới hạn kích thước/concurrency phù hợp.

Với bài kiểm thử có thời gian hoặc nguồn bất đồng bộ, sử dụng scheduler ảo, latch hoặc tín hiệu đồng bộ hóa. Tránh dựa vào `Thread.sleep` để tái hiện tắc nghẽn vì kết quả dễ phụ thuộc tốc độ máy.

## 12. Tình huống thực tế: xử lý cập nhật theo khách hàng

Một hệ thống nhận sự kiện từ nhiều khách hàng. Mỗi khách hàng có thể phát liên tục các cập nhật trạng thái. Yêu cầu là cập nhật trạng thái của cùng một khách hàng theo thứ tự, trong khi nhiều khách hàng khác nhau được xử lý đồng thời.

Nếu số khách hàng đang hoạt động được giới hạn và có thể dự đoán, `groupBy` là lựa chọn phù hợp:

```java
int maxActiveCustomers = 24;

Flux<UpdateResult> results = customerEvents
    .filter(event -> customerRegistry.isActive(event.customerId()))
    .groupBy(CustomerEvent::customerId, 64)
    .flatMap(
        group -> group.concatMap(event ->
            customerStateService.apply(group.key(), event)
        ),
        maxActiveCustomers
    );
```

`filter` giảm số khóa không cần xử lý trước khi tạo nhóm. `concatMap` giữ thứ tự cập nhật trong mỗi khách hàng. `flatMap` cho phép xử lý nhiều khách hàng đồng thời, với concurrency được chọn theo giới hạn số khách hàng hoạt động và năng lực của dịch vụ trạng thái. Nếu số khách hàng hoạt động có thể vượt `maxActiveCustomers`, cần đánh giá lại mô hình để tránh nhóm chưa được drain.

Nếu số khách hàng không giới hạn hoặc mỗi khách hàng chỉ xuất hiện một vài lần trong nguồn dài hạn, có thể phân vùng theo số shard cố định hoặc xử lý theo cửa sổ. Lựa chọn phải dựa trên yêu cầu thứ tự, thời gian sống của trạng thái và khả năng giới hạn số nhóm.

## 13. Checklist tránh tắc nghẽn khi gom và chia luồng

- Xác định cardinality của khóa trước khi dùng `groupBy`.
- Đảm bảo mọi `GroupedFlux` được subscribe và tiêu thụ hoặc drain theo chính sách rõ ràng.
- Lọc các phần tử không cần thiết trước `groupBy` khi có thể.
- Chọn `flatMap` concurrency đủ cho số nhóm đồng thời đã giới hạn; không giả định concurrency mặc định luôn đủ.
- Tránh `concatMap` ở tầng ngoài khi nhóm có thể sống lâu hoặc không hoàn tất cho đến khi nguồn tổng thể kết thúc.
- Không dùng khóa gần như duy nhất cho mỗi phần tử nếu không có chiến lược giới hạn vòng đời.
- Giới hạn prefetch, buffer, số batch và concurrency theo tài nguyên downstream.
- Dùng `window`/`buffer` nếu cần chia theo số lượng hoặc thời gian mà không cần nhóm lâu dài theo khóa.
- Cân nhắc shard cố định, partition broker hoặc kho trạng thái có TTL khi cardinality không thể giới hạn.
- Theo dõi số nhóm, số nhóm chưa được tiêu thụ, queue, heap và độ trễ.
- Kiểm thử nhóm không được chọn, nhóm chậm, nguồn dài hạn, cancel và lỗi.

`groupBy` mạnh khi số khóa có giới hạn và mỗi nhóm được tiêu thụ đúng cách. Khi số nhóm tăng không kiểm soát hoặc publisher con bị bỏ quên, pipeline có thể tích lũy dữ liệu và ngừng tiến triển. Hiểu hai tầng demand, giữ mọi nhóm trong một luồng tiêu thụ rõ ràng và chọn `window` hoặc `buffer` khi phù hợp sẽ giúp thiết kế pipeline reactive ổn định hơn.
