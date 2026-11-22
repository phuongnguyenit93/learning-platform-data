# ReactiveSearchHits và đọc metadata cùng luồng kết quả

Trong Spring Data Elasticsearch reactive, một truy vấn search có thể trả về nhiều hơn danh sách entity. Response còn chứa metadata của toàn bộ truy vấn như tổng số hit, max score, aggregation, thời gian thực thi hoặc thông tin Point in Time nếu API và phiên bản hỗ trợ. Mỗi hit cũng có metadata riêng như document ID, index, score, sort values, highlight và inner hits.

Khi dùng API imperative, ứng dụng thường nhận một đối tượng SearchHits rồi đọc danh sách hit và metadata bằng các getter đồng bộ. Trong reactive stack, kết quả và metadata được biểu diễn theo Reactive Streams: Flux cho chuỗi hit và Mono cho một giá trị bất đồng bộ. ReactiveSearchHits là abstraction giúp giữ cả hai phần trong cùng một response.

Điều quan trọng là phân biệt:

- **Response-level metadata:** thông tin mô tả toàn bộ search request, ví dụ total hits, max score và aggregations.
- **Hit-level metadata:** thông tin của một document cụ thể, ví dụ ID, score, sort values và highlight.
- **Entity content:** object Java được ánh xạ từ source của document.

Nếu chỉ chuyển ReactiveSearchHits thành Flux<Product>, ứng dụng có thể làm mất các metadata cần cho phân trang, hiển thị relevance hoặc phân tích kết quả. Nếu cần metadata cùng hit, hãy giữ ReactiveSearchHits trong reactive chain và kết hợp Mono/Flux đúng cách.

## 1. Search response không chỉ là danh sách entity

Một search request có thể trả về:

    {
      "hits": {
        "total": {
          "value": 125,
          "relation": "eq"
        },
        "max_score": 4.82,
        "hits": [
          {
            "_index": "products",
            "_id": "p-100",
            "_score": 4.82,
            "_source": {
              "name": "Mechanical Keyboard"
            },
            "sort": [
              4.82,
              "p-100"
            ]
          }
        ]
      }
    }

Ứng dụng có thể cần:

- Content để hiển thị sản phẩm.
- ID để tạo link chi tiết hoặc xử lý tiếp.
- Score để giải thích thứ tự relevance.
- Sort values để tiếp tục search_after.
- Total hits để hiển thị số kết quả hoặc phân trang.
- Aggregations để hiển thị thống kê.
- Highlight để đánh dấu từ khóa khớp.
- Inner hits để hiển thị nested object khớp.

Nếu chỉ lấy hit.getContent(), phần lớn metadata của hit sẽ bị bỏ qua. Nếu chỉ dùng Flux<Product>, metadata cấp response như total hits và aggregations cũng không còn nằm trong kiểu dữ liệu mà downstream nhận được.

## 2. ReactiveSearchHits là gì?

ReactiveSearchHits là abstraction của Spring Data Elasticsearch dùng để biểu diễn kết quả search trong reactive API. Nó giữ luồng các SearchHit cùng những metadata được trả về từ search response.

Trong các phiên bản hiện đại, cách sử dụng thường có dạng:

    Mono<ReactiveSearchHits<Product>> result =
        operations.search(query, Product.class);

    result.flatMapMany(ReactiveSearchHits::getSearchHits);

Các thành phần có vai trò khác nhau:

- Mono<ReactiveSearchHits<Product>> biểu diễn response search được tạo bất đồng bộ.
- ReactiveSearchHits<Product> giữ metadata response và luồng hit.
- Flux<SearchHit<Product>> phát từng hit theo nhu cầu subscriber.
- SearchHit<Product> giữ content và metadata riêng của một hit.

Tên method, kiểu trả về và metadata có thể thay đổi theo phiên bản Spring Data Elasticsearch. Hãy kiểm tra API của dependency đã resolve. Đặc biệt, đừng nhầm ReactiveSearchHits với SearchHits imperative hoặc với Flux<Product>.

## 3. ReactiveSearchHits khác Flux entity như thế nào?

Các kiểu kết quả có mức thông tin khác nhau:

| Kiểu kết quả | Nội dung chính | Metadata có thể truy cập |
|---|---|---|
| Flux<Product> | Entity content từng document | Không giữ đầy đủ hit/response metadata |
| Flux<SearchHit<Product>> | Content và metadata của từng hit | ID, score, sort values, highlight và metadata hit được API expose |
| Mono<ReactiveSearchHits<Product>> | Search response reactive | Luồng hit cùng response-level metadata |
| SearchHits<Product> | Search response imperative | Hit list và metadata đồng bộ |

Nếu endpoint chỉ cần danh sách entity đơn giản, Flux<Product> có thể đủ. Nếu cần score, ID, highlight hoặc sort values, dùng SearchHit. Nếu cần total hits, max score, aggregation hoặc metadata response khác, giữ ReactiveSearchHits.

Không nên chuyển sang Flux<Product> quá sớm rồi cố lấy lại metadata đã bỏ đi.

## 4. ReactiveElasticsearchOperations.search

ReactiveElasticsearchOperations cung cấp API search cho reactive application. Một dạng thường dùng:

    Mono<ReactiveSearchHits<Product>> search(
        Query query,
        Class<Product> clazz
    );

Có thể truyền IndexCoordinates nếu cần chỉ rõ index:

    Mono<ReactiveSearchHits<Product>> result =
        operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products")
        );

Sau đó lấy hit stream:

    Flux<SearchHit<Product>> hits =
        result.flatMapMany(ReactiveSearchHits::getSearchHits);

Đây là luồng reactive:

    Mono<ReactiveSearchHits<Product>>
                 |
                 v
        ReactiveSearchHits
          /           \
         v             v
    Flux<SearchHit>  Mono metadata
         |
         v
    SearchHit<Product>
         |
         v
    Product content

Mono response là điểm vào để lấy metadata toàn truy vấn. Flux hit là luồng nhiều phần tử. Không cần block để chuyển từ Mono sang Flux; dùng flatMapMany hoặc các operator reactive tương ứng.

## 5. Response-level metadata

ReactiveSearchHits có thể expose các metadata của search response thông qua các publisher. Trong các API hiện đại, những method thường gặp gồm:

| Metadata | Ý nghĩa | Dạng reactive thường gặp |
|---|---|---|
| Total hits | Số document khớp query theo semantics của request | Mono<Long> |
| Max score | Score cao nhất trong kết quả | Mono<Float> |
| Aggregations | Kết quả aggregation của request | Mono<AggregationsContainer<?>> |
| Point in Time ID | PIT ID nếu search dùng PIT và API expose | Mono<String> |
| Execution duration | Thời gian thực thi được response/API cung cấp | Mono<Duration> |

Danh sách và kiểu chính xác phụ thuộc Spring Data Elasticsearch version. Một số metadata có thể không tồn tại hoặc được biểu diễn khác ở phiên bản cũ. Hãy kiểm tra interface ReactiveSearchHits của dependency đang dùng.

Các publisher metadata không phải là từng hit. Ví dụ total hits là một giá trị của cả search response, không phải một field lặp lại trong mỗi SearchHit.

## 6. Hit-level metadata trong SearchHit

Mỗi SearchHit<T> đại diện cho một document trong kết quả. Các thông tin thường có thể truy cập gồm:

- getContent(): entity được ánh xạ từ source.
- getId(): document ID.
- getIndex(): index chứa document.
- getScore(): relevance score nếu query có score.
- getSortValues(): các giá trị sort của hit.
- getHighlightFields(): nội dung highlight theo field.
- getInnerHits(): nested/inner hit metadata nếu query yêu cầu.
- getRouting(): routing metadata nếu response cung cấp.
- Explanation hoặc metadata khác nếu request/API hỗ trợ.

Ví dụ:

    Flux<ProductSearchRow> rows =
        searchHits.getSearchHits()
            .map(hit -> new ProductSearchRow(
                hit.getId(),
                hit.getIndex(),
                hit.getScore(),
                hit.getContent(),
                hit.getSortValues(),
                hit.getHighlightFields()
            ));

DTO:

    public record ProductSearchRow(
        String id,
        String index,
        Float score,
        Product product,
        List<Object> sortValues,
        Map<String, List<String>> highlights
    ) {}

Kiểu của sort values và highlight fields phụ thuộc API client và Spring Data version. Nếu DTO cần được serialize ra HTTP response, nên chuyển các giá trị client-specific sang kiểu ứng dụng rõ ràng thay vì expose trực tiếp object nội bộ của Elasticsearch.

## 7. Đọc entity content và metadata của từng hit

Một pattern phổ biến là chuyển SearchHit thành DTO:

    public record ProductHit(
        String id,
        Float score,
        Product content
    ) {}

    Flux<ProductHit> productHits =
        searchHits.getSearchHits()
            .map(hit -> new ProductHit(
                hit.getId(),
                hit.getScore(),
                hit.getContent()
            ));

Điều này giữ lại ID và score trong khi chỉ expose các field mà API nghiệp vụ cần.

Nếu chỉ làm:

    Flux<Product> products =
        searchHits.getSearchHits()
            .map(SearchHit::getContent);

thì ID, score, sort values, highlight và inner hits không còn trong downstream stream. Có thể lấy ID từ entity nếu entity có @Id, nhưng score và các metadata search khác không phải field domain.

## 8. Kết hợp total hits và hit stream

Một endpoint có thể cần trả cả danh sách kết quả lẫn tổng số hit. Với ReactiveSearchHits, có thể kết hợp metadata Mono và hit Flux trong cùng reactive chain.

Ví dụ:

    public record ProductSearchResult(
        List<ProductHit> hits,
        Long totalHits,
        Float maxScore
    ) {}

    Mono<ProductSearchResult> searchProducts(Query query) {
        return operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getTotalHits(),
                    searchHits.getMaxScore().defaultIfEmpty(0.0f),
                    searchHits.getSearchHits()
                        .map(hit -> new ProductHit(
                            hit.getId(),
                            hit.getScore(),
                            hit.getContent()
                        ))
                        .collectList()
                ).map(tuple -> new ProductSearchResult(
                    tuple.getT3(),
                    tuple.getT1(),
                    tuple.getT2()
                ))
            );
    }

Trong ví dụ:

- operations.search phát một ReactiveSearchHits.
- getTotalHits cung cấp metadata tổng số hit.
- getMaxScore cung cấp max score; defaultIfEmpty chỉ là giá trị thay thế cho trường hợp publisher không phát giá trị.
- getSearchHits phát từng hit.
- collectList gom các hit thành List để tạo một response DTO.
- Mono.zip chờ các phần cần thiết hoàn tất rồi tạo ProductSearchResult.

collectList() làm toàn bộ hit được giữ trong bộ nhớ. Chỉ dùng pattern này khi page size đã được giới hạn và danh sách kết quả đủ nhỏ. Với tập kết quả lớn, nên stream hit thay vì gom tất cả vào một List.

Trong production, nếu totalHits hoặc maxScore có thể không được cung cấp, hãy giữ trạng thái optional thay vì biến giá trị thiếu thành 0 một cách âm thầm. Giá trị 0 có thể có nghĩa là không có hit, trong khi metadata không được trả về lại là một trường hợp khác.

## 9. Giữ metadata optional thay vì tự gán giá trị

Một cách biểu diễn an toàn hơn là dùng Optional trong DTO:

    public record ProductSearchResult(
        List<ProductHit> hits,
        Optional<Long> totalHits,
        Optional<Float> maxScore
    ) {}

    Mono<ProductSearchResult> searchProducts(Query query) {
        return operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getTotalHits()
                        .map(Optional::of)
                        .defaultIfEmpty(Optional.empty()),
                    searchHits.getMaxScore()
                        .map(Optional::of)
                        .defaultIfEmpty(Optional.empty()),
                    searchHits.getSearchHits()
                        .map(hit -> new ProductHit(
                            hit.getId(),
                            hit.getScore(),
                            hit.getContent()
                        ))
                        .collectList()
                ).map(tuple -> new ProductSearchResult(
                    tuple.getT3(),
                    tuple.getT1(),
                    tuple.getT2()
                ))
            );
    }

Các publisher metadata được chuyển thành Mono luôn phát một Optional, vì vậy Mono.zip không bị kết thúc sớm chỉ vì một metadata publisher không có giá trị.

Nếu API version luôn phát total hits và max score, Optional có thể không cần thiết. Hãy dùng kiểu dữ liệu phù hợp với contract thực tế của phiên bản và endpoint.

## 10. Tránh subscribe nhiều lần vào cùng search request

Reactive publisher thường lazy. Search request có thể chỉ được thực hiện khi có subscription. Nếu cùng một Mono được subscribe độc lập nhiều lần, ứng dụng có thể tạo nhiều search request:

    Mono<ReactiveSearchHits<Product>> result =
        operations.search(query, Product.class);

    result.flatMap(ReactiveSearchHits::getTotalHits)
        .subscribe();

    result.flatMapMany(ReactiveSearchHits::getSearchHits)
        .subscribe();

Đoạn code trên có thể thực hiện search hai lần, vì có hai subscription độc lập. Điều này vừa tốn tài nguyên vừa có thể trả hai snapshot kết quả khác nhau nếu dữ liệu thay đổi.

Hãy compose metadata và hit stream dưới một subscription:

    Mono<ProductSearchResult> result =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getTotalHits(),
                    searchHits.getSearchHits().collectList()
                ).map(tuple -> new ProductSearchResult(
                    mapHits(tuple.getT2()),
                    tuple.getT1()
                ))
            );

Không gọi subscribe bên trong service để tự chạy request rồi trả một kết quả khác cho caller. Trong WebFlux, controller thường trả Mono hoặc Flux để framework quản lý subscription.

## 11. Không dùng block trong reactive path

Đây là cách làm không phù hợp:

    ReactiveSearchHits<Product> searchHits =
        operations.search(query, Product.class).block();

    Long total = searchHits.getTotalHits().block();

    List<SearchHit<Product>> hits =
        searchHits.getSearchHits().collectList().block();

block() chuyển luồng bất đồng bộ thành đồng bộ, có thể giữ thread chờ I/O và làm giảm lợi ích của reactive stack. Trong event-loop thread, blocking còn có thể gây lỗi hoặc làm hệ thống mất khả năng phục vụ request khác.

Hãy dùng flatMap, flatMapMany, map, zip, collectList hoặc các operator phù hợp:

    Mono<SearchSummary> summary =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                searchHits.getTotalHits()
                    .map(total -> new SearchSummary(total))
            );

Không dùng block chỉ để lấy một metadata nhỏ. Metadata có thể được compose thành Mono như phần còn lại của response.

## 12. Đọc metadata aggregation

Một search request có thể chứa cả hits và aggregations. Trong reactive API, aggregation metadata thường được cung cấp qua một publisher như Mono<AggregationsContainer<?>>.

Ví dụ khái quát:

    Mono<AggregationReport> report =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                searchHits.getAggregations()
                    .map(aggregations ->
                        toAggregationReport(aggregations)
                    )
            );

AggregationsContainer là abstraction của Spring Data. Cách lấy aggregation theo tên và unwrap kiểu Elasticsearch-specific phụ thuộc client integration và phiên bản Spring Data.

Nếu dùng Elasticsearch Java API Client, aggregation response có thể được bọc trong implementation container tương ứng. Không nên ép kiểu sang implementation cụ thể mà không kiểm tra đúng phiên bản và kiểu runtime.

Khi cần cả hit và aggregation:

    Mono<ProductSearchResponse> response =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getSearchHits().collectList(),
                    searchHits.getAggregations()
                ).map(tuple -> new ProductSearchResponse(
                    mapHits(tuple.getT1()),
                    mapAggregations(tuple.getT2())
                ))
            );

Nếu aggregation không được yêu cầu trong query hoặc metadata publisher có thể empty, hãy xử lý trường hợp empty bằng Optional/default object phù hợp với API contract.

## 13. Đọc Point in Time ID và metadata phân trang

Khi search dùng Point in Time, response có thể chứa PIT ID mới. Một số phiên bản ReactiveSearchHits expose PIT ID qua publisher metadata. Hãy dùng ID mới nhất mà response trả về khi tiếp tục search theo cùng snapshot.

Ví dụ khái quát:

    Mono<PitSearchState> state =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                searchHits.getPointInTimeId()
                    .map(pitId -> new PitSearchState(pitId))
            );

API method và kiểu metadata PIT phụ thuộc phiên bản. Nếu ReactiveSearchHits của dự án không expose PIT ID, cần dùng API client hoặc abstraction tương ứng để giữ response metadata.

PIT ID và sort values của hit là hai phần khác nhau:

- PIT ID xác định snapshot search.
- Sort values xác định vị trí tiếp tục.

Với search_after, lấy toàn bộ sort values của hit cuối:

    Mono<List<Object>> cursor =
        searchHits.getSearchHits()
            .last()
            .map(SearchHit::getSortValues);

last() cần có ít nhất một hit. Nếu không có kết quả, publisher có thể hoàn tất empty; xử lý trường hợp này trước khi tạo cursor.

Khi dùng streaming, có thể lưu cursor trong quá trình xử lý từng hit cuối cùng thay vì gom toàn bộ danh sách. Đảm bảo PIT ID mới nhất và cursor được cập nhật nhất quán cho mỗi phiên phân trang.

## 14. Sort values và search_after trong reactive flow

Để phân trang sâu, query thường dùng PIT kết hợp search_after. Search response trả sort values cho từng hit. Ứng dụng dùng sort values của hit cuối để tạo request kế tiếp.

Luồng tổng quát:

    Mở PIT
       |
       v
    Search trang đầu
       |
       v
    ReactiveSearchHits
       |
       +----> response metadata / PIT ID
       |
       v
    Flux<SearchHit<T>>
       |
       v
    Xử lý hit
       |
       v
    Lưu sort values của hit cuối
       |
       v
    Search request kế tiếp với search_after

Không lấy cursor từ entity field nếu SearchHit đã cung cấp sort values. Sort values có thể chứa tie-breaker hoặc kiểu dữ liệu được Elasticsearch chuẩn hóa.

Nếu stream xử lý nhiều hit song song, cần bảo đảm cursor được chọn theo thứ tự sort của kết quả, không phải theo thứ tự hoàn thành ngẫu nhiên của các tác vụ bất đồng bộ.

## 15. Stream hit mà không gom toàn bộ vào bộ nhớ

Nếu endpoint hoặc job xử lý nhiều hit, dùng Flux để xử lý tuần tự hoặc theo mức concurrency được kiểm soát:

    Flux<ProductHit> stream =
        operations.search(query, Product.class)
            .flatMapMany(ReactiveSearchHits::getSearchHits)
            .map(hit -> new ProductHit(
                hit.getId(),
                hit.getScore(),
                hit.getContent()
            ));

Consumer có thể ghi từng item hoặc chuyển tiếp đến WebFlux response:

    @GetMapping(value = "/products/stream",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ProductHit> streamProducts() {
        return service.searchProductHits();
    }

Flux phát dữ liệu theo demand của subscriber. Điều này giúp áp dụng backpressure thay vì luôn tải toàn bộ kết quả vào một List.

Tuy nhiên, việc dùng Flux không tự bảo đảm query có thể trả vô hạn document hoặc bỏ qua giới hạn page size. Elasticsearch search API vẫn có giới hạn về số hit mỗi request và cách phân trang. Với dữ liệu lớn, dùng scroll hoặc PIT/search_after theo chiến lược phù hợp.

## 16. Backpressure và xử lý bất đồng bộ từng hit

Backpressure cho phép downstream báo cho upstream biết tốc độ tiêu thụ. Nếu consumer xử lý chậm, reactive pipeline có thể điều tiết lượng dữ liệu được yêu cầu.

Ví dụ xử lý từng hit:

    Flux<Void> writes =
        searchHits.getSearchHits()
            .concatMap(hit ->
                archiveService.store(hit.getContent())
            );

concatMap xử lý lần lượt từng hit, giữ thứ tự và chỉ chuyển sang item tiếp theo theo semantics tuần tự của operator.

Nếu cần concurrency:

    Flux<Void> writes =
        searchHits.getSearchHits()
            .flatMap(
                hit -> archiveService.store(hit.getContent()),
                8
            );

Concurrency 8 là giới hạn số inner publisher hoạt động đồng thời trong ví dụ. Chọn con số theo năng lực downstream và yêu cầu thứ tự. flatMap có thể làm kết quả hoàn tất không theo thứ tự ban đầu.

Nếu cursor hoặc checkpoint phụ thuộc thứ tự hit, dùng concatMap hoặc thiết kế bộ điều phối riêng để cập nhật cursor theo thứ tự sort.

## 17. Metadata và streaming: hai kiểu response khác nhau

Một API HTTP có thể trả metadata ở đầu response rồi stream hit, hoặc đợi xử lý xong để trả một JSON object có cả metadata và danh sách kết quả.

### Response JSON gom kết quả

    Mono<ProductSearchResult> result =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getTotalHits(),
                    searchHits.getSearchHits().collectList()
                ).map(tuple -> new ProductSearchResult(
                    mapHits(tuple.getT2()),
                    tuple.getT1()
                ))
            );

Đơn giản cho page size nhỏ, nhưng phải giữ toàn bộ hit trong memory.

### Stream từng hit

    Flux<ProductHit> result =
        operations.search(query, Product.class)
            .flatMapMany(ReactiveSearchHits::getSearchHits)
            .map(this::toProductHit);

Phù hợp với streaming endpoint hoặc xử lý dữ liệu lớn, nhưng response stream không tự chứa một JSON metadata envelope hoàn chỉnh.

### Stream event có metadata

Nếu giao thức là Server-Sent Events hoặc một stream event riêng, có thể phát event metadata trước rồi phát từng hit:

    Flux<SearchEvent> events =
        operations.search(query, Product.class)
            .flatMapMany(searchHits ->
                searchHits.getTotalHits()
                    .map(total -> SearchEvent.metadata(total))
                    .flux()
                    .concatWith(
                        searchHits.getSearchHits()
                            .map(this::toSearchEvent)
                    )
            );

SearchEvent là DTO ứng dụng tự định nghĩa. Cách này giúp consumer nhận tổng số hit trước các event document. Nếu cần max score hoặc aggregation, kết hợp thêm metadata publisher trước khi bắt đầu hit stream.

Không thể thay đổi header HTTP sau khi body stream đã bắt đầu. Nếu metadata cần nằm trong HTTP header, phải lấy metadata trước khi commit response; nếu metadata nằm trong body, có thể dùng envelope hoặc event stream.

## 18. Total hits và track total hits

Total hits là metadata response mô tả số document khớp query. Elasticsearch có thể giới hạn việc đếm chính xác để giảm chi phí, tùy request và cấu hình track_total_hits.

Response total hits có thể có quan hệ:

- eq: số lượng được đếm chính xác theo request semantics.
- gte: giá trị là cận dưới vì Elasticsearch dừng đếm khi đạt ngưỡng.

ReactiveSearchHits có thể chỉ expose giá trị số qua getTotalHits ở một số phiên bản, không nhất thiết expose relation. Nếu API cần phân biệt total chính xác với lower bound, hãy kiểm tra abstraction/response metadata mà phiên bản cung cấp hoặc dùng Elasticsearch Java API Client để đọc relation.

Đừng luôn hiển thị total hits như một số chính xác nếu query đã giới hạn track_total_hits. Với giao diện chỉ cần page navigation, có thể dùng hasNext hoặc số hit trong trang nếu không cần tổng số chính xác.

## 19. Max score và score của từng hit

Max score là score cao nhất trong toàn bộ response. Score của từng SearchHit là relevance score của document đó.

Hai giá trị phục vụ mục đích khác nhau:

- Max score có thể dùng để hiển thị hoặc phân tích chất lượng response.
- Hit score dùng để hiểu vì sao document nằm ở vị trí nhất định.

Nếu query không tính score hoặc request dùng sort theo field, score có thể không có giá trị hữu ích. Không nên mặc định score luôn khác null hoặc luôn là số dương.

Khi mapping SearchHit sang DTO, có thể giữ score dạng nullable/Optional nếu API có thể không cung cấp:

    public record ProductHit(
        String id,
        Float score,
        Product content
    ) {}

Nếu UI chỉ cần danh sách sản phẩm, không cần trả score ra public API. Giữ metadata nội bộ giúp tránh phụ thuộc vào thuật toán relevance của Elasticsearch trong contract bên ngoài.

## 20. Highlight và inner hits

SearchHit có thể chứa highlight fields khi query yêu cầu highlight:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("description")
                .query("mechanical keyboard")
            )
        )
        .withHighlightQuery(/* cấu hình highlight theo version */)
        .build();

Tên builder và cách khai báo highlight phụ thuộc Spring Data/Java Client version. Khi response có highlight, từng SearchHit có thể cung cấp highlight metadata để service tạo DTO.

Nested query có thể dùng inner_hits để trả về nested object đã khớp. Inner hits cũng nằm ở phạm vi từng hit cha, không phải response-level metadata chung.

Nếu API chỉ trả entity content, highlight và inner hits sẽ không được đưa vào DTO. Hãy map chúng riêng khi giao diện cần hiển thị đoạn văn bản khớp hoặc nested object phù hợp.

## 21. Aggregation metadata không phải hit stream

Aggregation được tính trên tập document mà query chọn, nhưng response aggregation là một nhánh riêng của search response. Nó không được phát như một SearchHit cho mỗi document.

Ví dụ:

    Mono<ReactiveSearchHits<Product>> result =
        operations.search(queryWithAggregations, Product.class);

    Mono<AggregationSummary> aggregationSummary =
        result.flatMap(searchHits ->
            searchHits.getAggregations()
                .map(this::toAggregationSummary)
        );

Nếu endpoint cần cả aggregation và hits, kết hợp chúng dưới một flatMap như phần trước. Không chạy lại search chỉ để lấy aggregation sau khi đã lấy hit stream.

Với query chỉ cần aggregation và không cần hit, hãy đặt size bằng 0 theo API query phù hợp. Điều này tránh trả document không cần thiết.

## 22. Metadata execution duration

Một số phiên bản ReactiveSearchHits expose thời gian thực thi của search response. Đây là metadata hữu ích cho observability, nhưng không nhất thiết bằng toàn bộ thời gian endpoint.

Thời gian endpoint còn gồm:

- Thời gian chờ connection.
- Thời gian serialization query.
- Network latency.
- Thời gian map entity.
- Thời gian xử lý downstream.
- Thời gian ghi hoặc gửi response.

Nếu cần đo latency end-to-end, dùng Micrometer hoặc instrumentation ở service/controller. Không xem execution duration từ Elasticsearch là tổng thời gian người dùng chờ.

## 23. Kết hợp metadata với log và tracing

Có thể ghi nhận total hits, duration và index để theo dõi search:

    Mono<SearchMetrics> metrics =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getTotalHits(),
                    searchHits.getExecutionDuration()
                ).map(tuple -> new SearchMetrics(
                    tuple.getT1(),
                    tuple.getT2()
                ))
            );

SearchMetrics là DTO ứng dụng tự định nghĩa. Tùy phiên bản, execution duration có thể không có hoặc dùng kiểu khác.

Không nên log toàn bộ query source nếu query chứa dữ liệu nhạy cảm. Không dùng search term, user ID hoặc document ID làm metric tag cardinality cao nếu hệ thống observability không kiểm soát được số lượng series.

Để trace một request qua service, dùng correlation ID hoặc tracing context thay vì tự truyền metadata search vào mọi log line.

## 24. ReactiveSearchHits và phân trang thông thường

Với phân trang nhỏ, có thể dùng Pageable:

    Pageable pageable = PageRequest.of(0, 20);

    Query query = NativeQuery.builder()
        .withPageable(pageable)
        .build();

    Mono<ReactiveSearchHits<Product>> result =
        operations.search(query, Product.class);

Ứng dụng có thể kết hợp total hits và hit list để tạo response có page number, page size và total. Tuy nhiên, deep pagination với from/size bị giới hạn và có chi phí tăng theo độ sâu.

ReactiveSearchHits không tự biến response thành Spring Data Page có đủ thông tin đồng bộ. Service cần tạo DTO/page abstraction phù hợp từ metadata và hit stream.

Nếu dùng collectList() để tạo Page response, hãy giới hạn page size. Với deep pagination hoặc tập dữ liệu lớn, cân nhắc PIT + search_after.

## 25. ReactiveSearchHits và scroll/search_after

Với tác vụ đọc nhiều trang:

- Dùng ReactiveSearchHits khi cần cả response metadata và hit stream.
- Dùng PIT để giữ snapshot nhất quán trong thời gian context còn sống.
- Dùng search_after với sort values của hit cuối để lấy trang tiếp theo.
- Cập nhật PIT ID mới nhất nếu response trả ID mới.
- Đóng PIT khi hoàn tất hoặc hủy.

Với scroll:

- Dùng API scroll/reactive stream tương ứng với phiên bản.
- Cập nhật scroll ID mới nhất từ response.
- Đóng/clear scroll khi hoàn tất.

Không nên dùng một Flux<SearchHit<T>> như một cursor bền vững. Flux chỉ là cách tiêu thụ kết quả hiện tại; trạng thái tiếp tục phân trang cần PIT/scroll ID và cursor riêng.

## 26. Xử lý lỗi trong metadata publisher và hit stream

Reactive pipeline có thể lỗi ở nhiều giai đoạn:

- Search request lỗi trước khi tạo ReactiveSearchHits.
- Metadata publisher lỗi khi được subscribe.
- Hit stream lỗi trong quá trình phát.
- Mapping entity thất bại.
- Downstream processing lỗi.
- Consumer hủy subscription.

Một lỗi trong Mono.zip có thể làm toàn bộ combined publisher lỗi. Nếu một metadata phụ không bắt buộc, có thể xử lý fallback cho đúng trường hợp:

    Mono<Optional<Float>> maxScore =
        searchHits.getMaxScore()
            .map(Optional::of)
            .defaultIfEmpty(Optional.empty());

Không nên dùng onErrorReturn(0L) cho mọi lỗi total hits, vì nó biến lỗi mạng hoặc lỗi server thành kết quả hợp lệ có 0 hit. Chỉ dùng fallback khi metadata thực sự có thể không tồn tại và contract cho phép.

Nếu hit stream đã phát một phần rồi gặp lỗi, consumer có thể đã xử lý một số hit. Với job ghi dữ liệu, cần idempotency hoặc checkpoint để retry không gây duplicate.

## 27. Cancellation và cleanup

Reactive Streams cho phép subscriber cancel. Khi người dùng ngắt kết nối HTTP hoặc job bị hủy, subscription có thể bị cancel trước khi toàn bộ hit được tiêu thụ.

Nếu search dùng PIT hoặc scroll context, cancellation cần được kết hợp với cleanup theo API và phiên bản phù hợp. Không giả định việc cancel Flux luôn đóng mọi server-side context ngay lập tức.

Có thể dùng doFinally để quan sát tín hiệu complete/error/cancel:

    Flux<SearchHit<Product>> hits =
        searchHits.getSearchHits()
            .doFinally(signalType ->
                log.debug("Search hit stream ended: {}", signalType)
            );

doFinally phù hợp cho metrics/logging hoặc kích hoạt logic cleanup nhẹ. Với cleanup bất đồng bộ cần chờ hoàn tất, dùng resource management pattern phù hợp với reactive API, ví dụ usingWhen khi resource lifecycle được biểu diễn rõ.

Không gọi block trong doFinally và không bỏ qua lỗi cleanup quan trọng. PIT/scroll ID cần được giữ ở state của phiên search để đóng đúng context.

## 28. Chọn search hay searchForStream

ReactiveElasticsearchOperations có thể cung cấp nhiều dạng search API:

- API trả ReactiveSearchHits khi cần response metadata cùng hit stream.
- API trả Flux<SearchHit<T>> hoặc Flux<T> cho trường hợp chỉ cần stream hit/content.
- API stream chuyên biệt tùy phiên bản và kiểu truy vấn.

Tên method và chữ ký có thể thay đổi. Hãy kiểm tra interface ReactiveElasticsearchOperations của dependency thực tế.

Chọn theo nhu cầu:

| Nhu cầu | Kiểu API nên cân nhắc |
|---|---|
| Cần total hits, max score và aggregations | API trả ReactiveSearchHits |
| Chỉ cần entity content | Flux<T> |
| Cần ID/score/sort/highlight của từng hit | Flux<SearchHit<T>> |
| Xử lý một trang nhỏ và trả JSON envelope | ReactiveSearchHits + collectList có giới hạn |
| Xử lý tập lớn với backpressure | Flux stream và pagination/scroll/PIT phù hợp |

Nếu dùng API stream không trả ReactiveSearchHits, hãy xác nhận metadata response nào bị lược bỏ và liệu use case có cần chúng hay không.

## 29. Spring WebFlux controller trả metadata cùng kết quả

Một controller có thể trả Mono DTO:

    @RestController
    @RequestMapping("/products")
    public class ProductSearchController {

        private final ProductSearchService service;

        public ProductSearchController(ProductSearchService service) {
            this.service = service;
        }

        @GetMapping("/search")
        public Mono<ProductSearchResult> search(
                @RequestParam String q) {
            return service.search(q);
        }
    }

Service thực hiện query và tạo response:

    public Mono<ProductSearchResult> search(String text) {
        Query query = buildQuery(text);

        return operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getTotalHits(),
                    searchHits.getSearchHits()
                        .map(this::toProductHit)
                        .collectList()
                ).map(tuple -> new ProductSearchResult(
                    tuple.getT2(),
                    tuple.getT1()
                ))
            );
    }

Đây là ví dụ khái quát; DTO và các getter phải phù hợp với API version. Controller trả Mono để WebFlux quản lý subscription và ghi response khi publisher hoàn tất.

Nếu page size lớn, collectList có thể tạo áp lực memory. Nếu muốn stream hit, chọn response format có thể biểu diễn metadata và các item theo giao thức streaming.

## 30. Reactive metadata và serialization

Không nên trả trực tiếp ReactiveSearchHits hoặc SearchHit từ controller nếu không có contract serialization rõ ràng. Các kiểu này thuộc tầng persistence và có thể chứa object client-specific hoặc metadata không phù hợp với public API.

Nên tạo DTO:

    public record ProductSearchResponse(
        List<ProductHitResponse> items,
        Optional<Long> totalHits,
        Optional<Float> maxScore
    ) {}

    public record ProductHitResponse(
        String id,
        Float score,
        String name,
        List<Object> sortValues
    ) {}

Việc map DTO giúp:

- Ổn định API khi nâng cấp Spring Data/Elasticsearch client.
- Chọn metadata nào được expose.
- Không lộ field nội bộ hoặc response object quá lớn.
- Chuẩn hóa null/optional semantics.
- Dễ kiểm thử service mà không phụ thuộc serialization của client.

Sort values có thể chứa dữ liệu opaque phục vụ cursor. Nếu expose cho client, hãy bảo vệ cursor theo thiết kế API và không để client tự ý sửa các giá trị mà server tin cậy.

## 31. ReactiveSearchHits trong test

Khi test service, có thể dùng StepVerifier để kiểm tra Mono/Flux:

    StepVerifier.create(service.search("keyboard"))
        .assertNext(result -> {
            assertThat(result.totalHits()).isPositive();
            assertThat(result.hits()).isNotEmpty();
        })
        .verifyComplete();

Với stream hit:

    StepVerifier.create(service.searchHitStream("keyboard"))
        .expectNextMatches(hit ->
            hit.id() != null && hit.content() != null
        )
        .thenCancel()
        .verify();

Test integration với Elasticsearch thật cần chuẩn bị index/mapping và dữ liệu. Nếu cần search thấy document vừa ghi, dùng refresh policy hoặc refresh tường minh thay vì Thread.sleep.

Không nên kiểm tra callback/metadata bằng cách gọi block trong code production chỉ để test. StepVerifier subscribe và kiểm tra signal theo reactive semantics.

### Kiểm tra subscription count

Nếu cần xác nhận search chỉ được thực hiện một lần, có thể mock operations và verify số lần gọi search hoặc dùng publisher test có side effect đếm subscription. Điều này giúp phát hiện việc tạo hai subscription độc lập để lấy metadata và hits.

## 32. Những lỗi thường gặp

### Chuyển ReactiveSearchHits thành Flux entity quá sớm

Khi chỉ map SearchHit::getContent, ứng dụng mất ID, score, sort values và metadata khác. Giữ SearchHit hoặc map sang DTO có metadata cần thiết.

### Nghĩ total hits nằm trong từng SearchHit

Total hits là metadata cấp response. Lấy từ ReactiveSearchHits, không lấy từ hit stream.

### Subscribe riêng để lấy metadata và hit

Mono search có thể chạy lại cho mỗi subscription. Kết hợp các publisher trong một reactive chain để tránh gửi hai search request.

### Dùng block trong WebFlux

block làm mất tính bất đồng bộ và có thể chặn event loop. Dùng flatMap, flatMapMany, zip và các operator reactive.

### Gom hàng nghìn hit bằng collectList

collectList giữ toàn bộ kết quả trong memory. Giới hạn page size hoặc stream từng hit với backpressure.

### Xem max score là luôn có giá trị

Query không tính score hoặc response không có score có thể khiến metadata rỗng. Biểu diễn optional/null phù hợp.

### Coi total hits luôn chính xác

track_total_hits có thể giới hạn việc đếm. Nếu cần phân biệt exact với lower bound, kiểm tra relation trong response/API version.

### Nhầm response metadata với hit metadata

Aggregation, total hits và PIT ID mô tả response; ID, score, highlight và sort values thuộc từng hit. Đặt chúng đúng DTO.

### Dùng API stream nhưng vẫn mong có toàn bộ metadata

Một số stream API chỉ trả hit/content. Nếu cần total hits hoặc aggregation, dùng API trả ReactiveSearchHits hoặc lấy metadata theo cơ chế response phù hợp.

### Cập nhật cursor từ hit hoàn thành sau cùng

flatMap có concurrency có thể hoàn tất không theo thứ tự sort. Cursor phải dựa trên hit cuối theo thứ tự kết quả, không phải task hoàn tất cuối cùng.

### Bỏ qua cancellation và PIT cleanup

Subscriber cancel không nên để PIT/scroll context tồn tại ngoài ý muốn. Quản lý resource lifecycle và cleanup theo API tương ứng.

### Trả trực tiếp kiểu persistence ra public API

ReactiveSearchHits và SearchHit có thể phụ thuộc phiên bản. Chuyển sang DTO ứng dụng trước khi trả HTTP response.

## 33. Quy trình đọc ReactiveSearchHits

Khi xây dựng reactive search service, có thể làm theo thứ tự:

1. Xác định endpoint cần entity content, hit metadata hay response metadata.
2. Dùng API trả ReactiveSearchHits nếu cần cả metadata response và hit stream.
3. Giữ Mono<ReactiveSearchHits<T>> trong cùng reactive chain.
4. Đọc total hits, max score, aggregations hoặc PIT metadata bằng publisher tương ứng.
5. Đọc từng SearchHit qua Flux và lấy content cùng metadata cần thiết.
6. Kết hợp Mono và Flux bằng flatMap, flatMapMany hoặc zip.
7. Chỉ collectList khi kết quả được giới hạn và đủ nhỏ.
8. Không subscribe độc lập nhiều lần và không block.
9. Dùng backpressure/concurrency phù hợp với downstream.
10. Giữ sort values và PIT ID mới nhất nếu dùng deep pagination.
11. Xử lý metadata optional và lỗi publisher rõ ràng.
12. Cleanup PIT/scroll khi complete, error hoặc cancel.
13. Map sang DTO ứng dụng trước khi trả qua WebFlux.
14. Kiểm tra chữ ký API và metadata thực tế theo Spring Data Elasticsearch version.

## Kết luận

ReactiveSearchHits giúp Spring Data Elasticsearch giữ cả hit stream và metadata của một search response trong reactive model. Response-level metadata như total hits, max score, aggregations hoặc PIT information được cung cấp qua các publisher tùy phiên bản; mỗi SearchHit giữ metadata riêng như ID, score, sort values, highlight và inner hits. Entity content chỉ là một phần của SearchHit.

Hãy giữ ReactiveSearchHits trong reactive chain khi cần metadata, kết hợp các Mono với hit Flux bằng flatMap/zip và tránh subscribe riêng hoặc block. collectList phù hợp với trang kết quả nhỏ, còn Flux streaming giúp xử lý dữ liệu lớn với backpressure. Khi dùng PIT/search_after, lưu PIT ID mới nhất cùng toàn bộ sort values của hit cuối và quản lý cleanup khi luồng bị hủy. Trong Spring WebFlux, chuyển kết quả sang DTO ứng dụng để giữ contract ổn định và chỉ expose metadata mà endpoint thực sự cần. Luôn kiểm tra interface và chữ ký của phiên bản Spring Data Elasticsearch đang được resolve vì reactive search API và các metadata được expose có thể khác nhau giữa các phiên bản.
