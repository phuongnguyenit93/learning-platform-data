# Khai báo state store và materializedAs

## Mục tiêu

Kafka Streams có thể tổng hợp dữ liệu, giữ trạng thái theo khóa và cập nhật kết quả khi record mới đến. Trạng thái này được lưu trong **state store**. Ví dụ, một topology có thể duy trì tổng số đơn hàng theo khách hàng, số dư hiện tại theo tài khoản hoặc số lượng sự kiện trong mỗi cửa sổ thời gian.

Trong Spring Cloud Stream Kafka Streams binder, state store thường được tạo từ các phép toán Kafka Streams DSL như aggregate, count và reduce. API **Materialized.as(...)** đặt tên và mô tả cách materialize kết quả của một phép toán. Với một số binding có kiểu đầu vào KTable, thuộc tính **materializedAs** của binder cho phép đặt tên state store mà binder tạo cho binding đó.

Tên store là một phần của hợp đồng vận hành: ứng dụng có thể dùng tên này để truy vấn interactive query, theo dõi state restoration và xác định store trong topology. Bài học này giải thích cách khai báo store, chọn kiểu store và Serde, cấu hình materializedAs, truy vấn trạng thái và quản lý changelog/khôi phục.

Sau bài học, bạn có thể:

- Giải thích state store và vai trò của nó trong Kafka Streams.
- Phân biệt KStream, KTable và state store.
- Tạo store bằng Materialized.as(...) trong các phép aggregate.
- Cấu hình materializedAs cho binding KTable khi binder materialize dữ liệu đầu vào.
- Chọn KeyValueStore, WindowStore hoặc SessionStore theo cách truy cập.
- Cấu hình key/value Serde và tên store ổn định.
- Truy vấn store bằng KafkaStreamsInteractiveQueryService.
- Hiểu changelog, state restoration, caching và giới hạn của local state.
- Kiểm thử store sau khi khởi động, cập nhật và khôi phục.

## 1. State store là gì?

State store là nơi Kafka Streams lưu trạng thái mà topology cần để xử lý các record tiếp theo. Khác với một phép biến đổi stateless chỉ xử lý từng record độc lập, một phép toán stateful cần nhớ dữ liệu trước đó.

Ví dụ:

- Đếm số đơn hàng theo customerId.
- Tính tổng doanh thu theo cửa hàng.
- Lưu trạng thái mới nhất của từng tài khoản.
- Duy trì số liệu theo cửa sổ 5 phút.
- Kết hợp stream sự kiện với bảng tham chiếu.

Giả sử stream nhận các sự kiện:

| customerId | orderId | amount |
|---|---|---:|
| C-01 | O-100 | 120 |
| C-02 | O-101 | 80 |
| C-01 | O-102 | 50 |
| C-01 | O-103 | 30 |

Một phép count theo customerId cần giữ số đếm hiện tại. Sau bốn record, state store có thể chứa:

| Key | Count |
|---|---:|
| C-01 | 3 |
| C-02 | 1 |

Khi record tiếp theo của C-01 đến, Kafka Streams đọc trạng thái cũ, cập nhật giá trị và ghi trạng thái mới. Ứng dụng không cần tự tải toàn bộ lịch sử topic vào bộ nhớ để tính lại mỗi lần.

State store thường được gắn với một task/partition của Kafka Streams. Dữ liệu của một key được xử lý bởi task tương ứng với partition, do đó trạng thái được phân vùng cùng topology. Một store có thể có nhiều shard cục bộ trên các instance khác nhau; không nên mặc định một instance giữ toàn bộ dữ liệu của mọi key.

## 2. Phân biệt KStream, KTable và state store

Ba khái niệm liên quan nhưng không đồng nghĩa:

| Thành phần | Ý nghĩa | Cách hiểu |
|---|---|---|
| KStream | Luồng các record sự kiện | Mỗi record là một sự kiện độc lập |
| KTable | Bảng cập nhật theo key | Mỗi record cập nhật giá trị hiện tại của một key |
| State store | Cơ chế lưu trạng thái cục bộ của topology | Lưu dữ liệu để aggregate, join hoặc truy vấn |

KStream phù hợp với lịch sử sự kiện: một đơn hàng được tạo, thanh toán và giao là các record khác nhau. KTable biểu diễn trạng thái mới nhất theo key: trạng thái hiện tại của đơn hàng O-100 có thể chuyển từ CREATED sang PAID.

Một KTable thường được hỗ trợ bởi state store. Tuy nhiên, không phải mọi state store đều được tạo ra từ một KTable input binding; các phép aggregate trong DSL cũng materialize state store.

Ví dụ một KStream được aggregate thành KTable:

    KTable<String, Long> orderCount = orders
            .groupByKey(Grouped.with(Serdes.String(), orderEventSerde))
            .count();

Phép count cần trạng thái để nhớ số lượng theo key. Kafka Streams materialize kết quả thành state store và biểu diễn kết quả cập nhật dưới dạng KTable.

## 3. Materialized.as(...) đặt tên state store

Trong Kafka Streams DSL, Materialized mô tả cách một kết quả được materialize. Phương thức as(...) đặt tên store. Tên này được dùng trong topology và có thể được sử dụng để truy vấn store nếu loại store hỗ trợ query.

Ví dụ đếm đơn hàng theo customerId:

    KTable<String, Long> orderCountByCustomer = orders
            .groupByKey(Grouped.with(
                    Serdes.String(),
                    orderEventSerde
            ))
            .count(
                    Materialized
                            .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                                    "orders-count-by-customer"
                            )
                            .withKeySerde(Serdes.String())
                            .withValueSerde(Serdes.Long())
            );

Trong ví dụ:

- Key là customerId kiểu String.
- Value của state store là số đơn hàng kiểu Long.
- Tên store là orders-count-by-customer.
- Key Serde và value Serde xác định cách lưu/khôi phục dữ liệu.
- KTable phản ánh giá trị count hiện tại sau mỗi cập nhật.

Tên store nên ổn định và có ý nghĩa nghiệp vụ. Tránh tạo tên ngẫu nhiên theo thời gian hoặc instance vì điều đó gây khó khăn cho state restoration, interactive query và vận hành.

### Materialized.as(...) không phải tên topic đầu ra

Tên store và tên Kafka topic là hai thứ khác nhau. Một state store có thể có changelog topic do Kafka Streams quản lý để phục hồi trạng thái. Changelog topic không nhất thiết có cùng tên với store và không phải output topic nghiệp vụ mà consumer downstream đăng ký.

Nếu topology vừa materialize state vừa phát kết quả ra topic, hãy đặt tên output binding riêng. Không dùng tên store thay cho destination của output binding.

## 4. Cấu hình Serde cho state store

State store cần biết cách serialize key/value. Nếu Serde không đúng, topology có thể lỗi khi ghi state, đọc lại changelog hoặc khôi phục sau restart.

Ví dụ:

    Materialized
            .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                    "orders-count-by-customer"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())

Trong trường hợp này:

- Key Serde là StringSerde.
- Value Serde là LongSerde.
- Changelog của store sử dụng định dạng bytes tương ứng.

Nếu state value là POJO, cần một Serde có kiểu tương ứng. Ví dụ:

    Materialized
            .<String, CustomerSummary, KeyValueStore<Bytes, byte[]>>as(
                    "customer-summary"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(customerSummarySerde)

Serde của store cần tương thích với dữ liệu được ghi trong changelog. Nếu đổi schema hoặc serializer mà không có kế hoạch migration, ứng dụng mới có thể không khôi phục được state cũ.

Không chỉ kiểm thử đường ghi mới. Hãy kiểm thử khôi phục từ changelog có dữ liệu đã tồn tại, đặc biệt khi thay đổi version ứng dụng hoặc schema.

## 5. materializedAs trong Spring Cloud Stream Kafka Streams binder

Kafka Streams binder có thể materialize một input binding kiểu KTable thành state store. Với trường hợp đó, thuộc tính materializedAs trên consumer binding cho phép đặt tên store do binder tạo.

Ví dụ function nhận một KTable:

    @Bean
    Function<KTable<String, CustomerProfile>,
             KTable<String, CustomerProfile>> enrichProfiles() {
        return profiles -> profiles.mapValues(profile ->
                profile.withDisplayName(
                        profile.firstName() + " " + profile.lastName()
                )
        );
    }

Cấu hình binding:

    spring:
      cloud:
        function:
          definition: enrichProfiles
        stream:
          bindings:
            enrichProfiles-in-0:
              destination: customer.profile
            enrichProfiles-out-0:
              destination: customer.profile.enriched
          kafka:
            streams:
              bindings:
                enrichProfiles-in-0:
                  consumer:
                    materializedAs: customer-profile-source-store

Trong ví dụ, input binding có kiểu KTable. Binder materialize dữ liệu bảng đầu vào và dùng tên customer-profile-source-store cho state store được tạo bởi binding. Tên này hữu ích khi ứng dụng cần truy vấn trạng thái của bảng input bằng interactive query.

materializedAs là thuộc tính của Kafka Streams binder binding; nó khác với lời gọi Materialized.as(...) trong DSL. Dùng materializedAs khi binder tạo store cho KTable binding. Dùng Materialized.as(...) khi chính topology gọi các phép aggregate/materialize và cần chỉ định store cho kết quả đó.

Không cấu hình materializedAs trên một binding KStream với kỳ vọng nó tự biến KStream thành KTable. Kiểu đầu vào và function signature phải đúng với mô hình bảng. Kiểm tra behavior của phiên bản binder nếu binding có nhiều input hoặc dùng KTable/GlobalKTable.

## 6. Phân biệt hai cách đặt tên store

| Cách khai báo | Nơi dùng | Store được đặt tên |
|---|---|---|
| Materialized.as("store-name") | Kafka Streams DSL | Store của phép aggregate, count, reduce hoặc thao tác materialize |
| consumer.materializedAs: store-name | Kafka Streams binder | Store được binder tạo cho KTable input binding theo hỗ trợ của phiên bản |
| destination: topic-name | Spring Cloud Stream binding | Kafka topic mà binding đọc/ghi |
| applicationId | Kafka Streams application | Danh tính ứng dụng, consumer group và namespace nội bộ liên quan |

Ví dụ một function có KTable input và sau đó tạo thêm một aggregate:

    @Bean
    Function<KTable<String, CustomerProfile>,
             KTable<String, Long>> countProfilesByRegion() {
        return profiles -> profiles
                .groupBy(
                        (customerId, profile) ->
                                KeyValue.pair(profile.region(), profile),
                        Grouped.with(Serdes.String(), customerProfileSerde)
                )
                .count(
                        Materialized
                                .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                                        "customer-count-by-region"
                                )
                                .withKeySerde(Serdes.String())
                                .withValueSerde(Serdes.Long())
                );
    }

Ở đây có thể tồn tại hai store với vai trò khác nhau:

- Store input do binder tạo cho KTable binding và đặt tên bằng materializedAs.
- Store aggregate customer-count-by-region do DSL tạo bằng Materialized.as(...).

Tên store cần duy nhất trong topology. Tránh đặt hai store khác nhau cùng tên, vì topology có thể không khởi tạo được hoặc truy vấn nhầm store.

## 7. Chọn loại state store

Kafka Streams cung cấp nhiều loại state store. Chọn loại dựa trên cách truy cập dữ liệu:

| Loại store | Mô hình dữ liệu | Tình huống |
|---|---|---|
| KeyValueStore | Một giá trị hiện tại cho mỗi key | Count, tổng, trạng thái mới nhất |
| WindowStore | Nhiều giá trị theo key và time window | Tổng hợp theo khoảng thời gian |
| SessionStore | Trạng thái theo phiên hoạt động | Phiên người dùng, khoảng nghỉ giữa sự kiện |
| TimestampedKeyValueStore | Key/value kèm timestamp của bản cập nhật | Trạng thái cần thời điểm cập nhật |
| VersionedKeyValueStore | Lưu nhiều version theo timestamp trong giới hạn retention | Truy vấn trạng thái theo thời điểm và xử lý late/out-of-order phù hợp |

Ví dụ count theo key thường dùng KeyValueStore. Windowed count cần store theo cửa sổ. Session aggregate dùng session window và store tương ứng.

Không ép mọi dữ liệu vào KeyValueStore nếu cần truy vấn theo thời gian. Ngược lại, WindowStore có thể tăng chi phí lưu trữ nếu ứng dụng chỉ cần một giá trị hiện tại cho mỗi key.

## 8. Cấu hình windowed state store

Ví dụ đếm sự kiện theo cửa sổ 5 phút:

    KTable<Windowed<String>, Long> ordersPerWindow = orders
            .groupByKey(Grouped.with(
                    Serdes.String(),
                    orderEventSerde
            ))
            .windowedBy(
                    TimeWindows.ofSizeAndGrace(
                            Duration.ofMinutes(5),
                            Duration.ofMinutes(2)
                    )
            )
            .count(
                    Materialized
                            .<String, Long,
                              WindowStore<Bytes, byte[]>>as(
                                    "orders-count-by-window"
                            )
                            .withKeySerde(Serdes.String())
                            .withValueSerde(Serdes.Long())
            );

Store này giữ count theo key và cửa sổ thời gian. Grace period cho phép một khoảng late event được cập nhật theo semantics event-time của Kafka Streams. Retention của window store cần đủ dài để bao phủ thời gian cửa sổ và khoảng late event được chấp nhận.

Tên store ổn định giúp topology restore dữ liệu từ changelog. Nếu thay đổi kích thước window, grace hoặc key/value schema, hãy đánh giá khả năng tương thích của state cũ và kế hoạch reset/rebuild khi cần.

## 9. Logging, changelog và state restoration

State store có thể được hỗ trợ bởi changelog topic. Kafka Streams ghi các thay đổi state vào changelog để có thể khôi phục store khi task được chuyển sang instance khác hoặc ứng dụng khởi động lại.

Luồng khái quát:

    Input topic
        -> Kafka Streams task
        -> Cập nhật state store cục bộ
        -> Ghi changelog record
        -> Instance dừng hoặc task chuyển owner
        -> Instance mới đọc changelog
        -> Khôi phục state store
        -> Tiếp tục xử lý input

Changelog là cơ chế fault tolerance của Kafka Streams. Nó không phải bản sao lưu database chung và không thay thế backup/retention strategy của hệ thống.

Một số store có thể tắt logging theo cấu hình Materialized hoặc StoreSupplier. Khi tắt changelog, state có thể không được khôi phục đầy đủ sau khi instance mất dữ liệu cục bộ. Chỉ tắt logging khi ứng dụng chấp nhận rebuild state từ input hoặc có một nguồn sự thật khác.

Cần theo dõi:

- Changelog topic được tạo đúng.
- Retention và replication phù hợp.
- Consumer có quyền đọc changelog.
- State restoration hoàn tất trước khi query store.
- Thời gian restore không vượt quá yêu cầu availability.
- Schema/Serde của changelog tương thích với phiên bản ứng dụng.

## 10. Persistent store và in-memory store

Kafka Streams có thể dùng store persistent hoặc in-memory tùy loại store và cấu hình. Persistent store thường dùng RocksDB để lưu state trên local disk; changelog hỗ trợ khôi phục khi local state mất. In-memory store giữ state trong bộ nhớ của process và có thể cần rebuild từ changelog/input sau restart.

| Đặc điểm | Persistent store | In-memory store |
|---|---|---|
| Lưu trữ | Local disk, thường qua RocksDB | RAM |
| Khởi động lại | Có thể dùng local state còn tồn tại và changelog | Thường cần restore/rebuild |
| Dung lượng | Phù hợp state lớn hơn RAM | Bị giới hạn bởi heap/native memory |
| Độ trễ | Có chi phí disk/native engine | Có thể nhanh cho dữ liệu nhỏ |
| Vận hành | Cần quản lý local state directory và disk | Cần quản lý memory và thời gian rebuild |

Persistent local state không có nghĩa dữ liệu được chia sẻ giữa các instance. Mỗi task có state cục bộ cho partition được gán. Khi task chuyển instance, state được khôi phục từ changelog hoặc được di chuyển theo cơ chế Kafka Streams.

Không đặt local state directory trên một filesystem dùng chung tùy tiện giữa nhiều instance. Kafka Streams quản lý task ownership và local state theo instance; chia sẻ cùng thư mục có thể gây xung đột hoặc hỏng state.

## 11. Truy vấn state store bằng Interactive Queries

Kafka Streams hỗ trợ Interactive Queries để ứng dụng đọc state store đang được topology quản lý. Trong Spring Cloud Stream Kafka Streams binder, có thể dùng KafkaStreamsInteractiveQueryService để tìm store theo tên.

Ví dụ truy vấn KeyValueStore:

    @RestController
    public class CustomerCountController {

        private final KafkaStreamsInteractiveQueryService queryService;

        public CustomerCountController(
                KafkaStreamsInteractiveQueryService queryService) {
            this.queryService = queryService;
        }

        @GetMapping("/customers/{customerId}/order-count")
        public Long getOrderCount(@PathVariable String customerId) {
            ReadOnlyKeyValueStore<String, Long> store =
                    queryService.getQueryableStoreType(
                            "orders-count-by-customer",
                            QueryableStoreTypes.keyValueStore()
                    );

            return store.get(customerId);
        }
    }

Tên store phải trùng với tên đã materialize trong topology. Store cần ở trạng thái queryable; khi topology đang khởi động hoặc restoring, truy vấn có thể chưa sẵn sàng. API thực tế có thể ném exception nếu store không tồn tại, chưa được khôi phục hoặc không có trên instance hiện tại.

Đưa truy vấn vào REST controller chỉ là ví dụ. Ứng dụng production nên xử lý store-not-available, key không tồn tại, timeout và lỗi khi task chuyển owner. Không giả định một instance có mọi key của topic.

### Truy vấn dữ liệu nằm trên instance khác

State store thường được phân vùng theo task. Một key có thể nằm trên instance khác với instance nhận HTTP request. Interactive Queries có API để xác định metadata/host của key và định tuyến request đến host đang sở hữu partition tương ứng.

Một API có thể:

1. Xác định partition cho key.
2. Lấy metadata về host đang active cho store/partition.
3. Nếu host hiện tại sở hữu key, query local store.
4. Nếu host khác sở hữu key, gọi endpoint nội bộ của host đó.
5. Xử lý host thay đổi khi rebalance và retry có giới hạn.

Kafka Streams cung cấp metadata APIs như query metadata cho key/store; Spring Cloud Stream binder có thể cung cấp service hỗ trợ query. Cần xác minh API cụ thể theo phiên bản Kafka Streams và binder. Không hardcode hostname hoặc giả định tất cả replica đều có cùng state.

## 12. Tên store là một phần của vận hành

Tên store được dùng bởi topology, interactive query và công cụ giám sát. Chọn tên:

- Ổn định giữa các lần deploy nếu muốn khôi phục state cũ.
- Mô tả aggregate hoặc mục đích lưu trữ.
- Không chứa pod ID hoặc UUID sinh mỗi lần chạy.
- Không trùng với store khác trong cùng topology.
- Có quy ước version khi cần migration không tương thích.

Ví dụ tên tốt:

| Tên | Ý nghĩa |
|---|---|
| orders-count-by-customer | Số đơn hàng theo khách hàng |
| account-balance | Số dư hiện tại theo tài khoản |
| payment-volume-by-window | Tổng giao dịch theo cửa sổ |
| customer-profile-source-store | State store của KTable input |

Đổi tên store có thể khiến Kafka Streams xem đó là store mới và tạo changelog/topic nội bộ khác, làm mất khả năng dùng local state/changelog cũ theo tên trước đó. Trước khi đổi tên, cần quyết định giữ state, rebuild từ input hay migrate dữ liệu.

## 13. Cache và cập nhật state

Kafka Streams có thể cache state update và gộp các thay đổi trước khi flush xuống state store/changelog/output. Caching có thể giảm số lần ghi và lượng record changelog, đặc biệt với key được cập nhật liên tục.

Caching có tác động đến thời điểm quan sát cập nhật:

- State store query có thể phản ánh trạng thái đã được flush theo lifecycle/cache, không phải mọi mutation vừa xảy ra trong từng instruction.
- KTable output có thể coalesce nhiều lần cập nhật cùng key trước khi phát tiếp.
- Cache size và commit interval ảnh hưởng độ trễ và throughput.
- Tắt cache có thể làm tăng số lần ghi/changelog và tải broker.

Nếu API cần read-after-write tức thời theo một request, hãy xác định rõ consistency/visibility semantics và kiểm thử với cấu hình cache/commit thực tế. Không coi cache flush interval là SLA chính xác nếu chưa đo.

## 14. Cập nhật schema và migration state store

State store và changelog là dữ liệu có vòng đời dài hơn một lần chạy ứng dụng. Khi thay đổi:

- Kiểu key hoặc value.
- Serializer/deserializer.
- Schema của POJO.
- Tên store.
- Loại store.
- Window size, retention hoặc semantics aggregate.

cần đánh giá khả năng đọc state đã tồn tại.

Các chiến lược migration thường dùng:

1. Giữ wire schema tương thích ngược và tiến về phía trước.
2. Tạo store/topic version mới rồi rebuild từ input.
3. Dùng application ID mới để tạo namespace topology mới, sau đó chuyển traffic/query.
4. Thực hiện migration dữ liệu có kiểm soát nếu cần giữ state không thể rebuild.
5. Chỉ reset state khi đã xác nhận nguồn input đủ để tái tạo và có kế hoạch vận hành.

Không đổi application ID hoặc xóa changelog để "sửa lỗi" khi chưa hiểu hậu quả. Việc đó có thể tạo topology mới, đọc lại dữ liệu hoặc mất trạng thái cần thiết.

## 15. Kiểm thử state store và materializedAs

Kiểm thử cần xác minh cả việc tạo store, cập nhật dữ liệu, truy vấn và phục hồi.

### Unit test cho phép aggregate

- Gửi nhiều record cùng key.
- Xác minh count/aggregate tăng đúng.
- Gửi record cho key khác và xác minh state độc lập.
- Xác minh Serde cho key/value.
- Xác minh tên store được khai báo như mong muốn nếu test topology hỗ trợ.

### Integration test với Kafka

Dùng Kafka broker test hoặc Testcontainers để kiểm tra:

1. Khởi động Spring Cloud Stream Kafka Streams binder.
2. Xác minh function topology được tạo.
3. Gửi input record vào topic.
4. Chờ state store được materialize và cập nhật.
5. Query store theo tên Materialized.as hoặc materializedAs.
6. Restart ứng dụng hoặc chuyển task sang instance khác.
7. Xác minh state restoration từ changelog.
8. Kiểm tra key không tồn tại và store chưa sẵn sàng.
9. Kiểm tra thay đổi Serde/schema có tương thích state cũ không.

### Kiểm thử KTable binding

Với binding KTable dùng materializedAs:

- Xác minh input binding thực sự có kiểu KTable.
- Kiểm tra tên store được binder tạo.
- Gửi nhiều update cùng key và xác minh store giữ giá trị mới nhất.
- Kiểm tra tombstone/delete semantics nếu topic có record value null.
- Kiểm tra interactive query sau khi topology hoàn tất restoration.

Test Binder có thể kiểm tra wiring ở mức Spring Cloud Stream nhưng không thay thế Kafka broker test cho changelog, state restoration, task assignment và Interactive Queries.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy store khi query | Tên query không khớp hoặc store chưa được tạo/restored | Kiểm tra tên materialize và trạng thái topology |
| materializedAs không có tác dụng | Binding không phải KTable hoặc property đặt sai namespace | Kiểm tra function signature và binder configuration |
| Aggregate lỗi khi ghi state | Thiếu hoặc sai Serde | Cấu hình key/value Serde đúng kiểu |
| Restart làm state restore thất bại | Changelog thiếu, retention hoặc Serde không tương thích | Kiểm tra changelog, ACL và schema migration |
| Query một key trả null | Key không tồn tại hoặc request đến sai instance | Kiểm tra dữ liệu và metadata/host routing |
| Nhiều instance trả kết quả khác nhau | Query local store trên instance không sở hữu key | Dùng Interactive Query metadata và định tuyến |
| State store tăng dung lượng liên tục | Key cardinality lớn, retention/cache không phù hợp | Đánh giá store type, retention và lifecycle dữ liệu |
| Đổi tên store khiến state rỗng | Store/changelog identity thay đổi | Lập kế hoạch migration hoặc rebuild |
| KTable output cập nhật chậm hơn mong đợi | Cache/commit interval hoặc processing lag | Đo visibility latency và cấu hình cache phù hợp |
| State cũ không deserialize được | Thay đổi schema/Serde không tương thích | Version hóa schema và migration state |

## 17. Quy trình khai báo state store

Trước khi triển khai:

1. Xác định state cần giữ và key đại diện cho đơn vị nghiệp vụ nào.
2. Chọn KeyValueStore, WindowStore, SessionStore hoặc loại phù hợp.
3. Xác định store được tạo bởi DSL aggregate hay bởi KTable input binding.
4. Dùng Materialized.as(...) cho store của phép toán DSL.
5. Dùng consumer.materializedAs cho KTable input binding nếu binder version hỗ trợ.
6. Đặt tên store ổn định và duy nhất.
7. Cấu hình key/value Serde tương thích.
8. Đánh giá changelog, logging, retention và local state directory.
9. Xác định API Interactive Query và cách định tuyến đến instance sở hữu key.
10. Kiểm thử update, query, tombstone, restart và state restoration.
11. Lập kế hoạch migration khi đổi tên store hoặc schema.

## Kết luận

State store giữ trạng thái mà Kafka Streams cần cho aggregate, join, window và các phép toán stateful. Trong DSL, Materialized.as(...) đặt tên store cho kết quả được materialize và cho phép cấu hình Serde. Với KTable input binding của Kafka Streams binder, materializedAs có thể đặt tên store do binder tạo. Hai cơ chế có phạm vi khác nhau; destination vẫn là Kafka topic, còn store name là định danh trạng thái nội bộ.

Hãy chọn store type theo cách truy cập, cấu hình Serde cho key/value, hiểu changelog và state restoration, rồi truy vấn bằng Interactive Queries khi cần. Tên store và schema cần ổn định qua các lần triển khai. Kiểm thử với Kafka broker để xác minh state được tạo, cập nhật, truy vấn và khôi phục đúng sau restart hoặc rebalance.

