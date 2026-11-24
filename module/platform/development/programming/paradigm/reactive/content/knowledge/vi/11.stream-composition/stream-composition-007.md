# zip và combineLatest: ghép theo vị trí hoặc giá trị gần nhất

Khi một pipeline reactive cần dữ liệu từ nhiều nguồn, việc ghép các luồng phải phản ánh đúng quan hệ giữa các giá trị. Có trường hợp phần tử thứ nhất của nguồn A phải đi cùng phần tử thứ nhất của nguồn B, phần tử thứ hai đi cùng phần tử thứ hai. Có trường hợp ứng dụng chỉ cần kết hợp trạng thái mới nhất từ mỗi nguồn mỗi khi một nguồn cập nhật. Reactor cung cấp hai toán tử quan trọng cho hai yêu cầu này: **zip** và **combineLatest**.

zip ghép các phần tử theo vị trí phát trong từng nguồn: phần tử thứ n của nguồn này được kết hợp với phần tử thứ n của nguồn kia. combineLatest đợi mỗi nguồn phát ít nhất một giá trị, sau đó mỗi lần một nguồn phát giá trị mới thì kết hợp giá trị đó với giá trị gần nhất đã nhận từ các nguồn còn lại. Hai toán tử đều tạo ra một luồng kết quả từ nhiều publisher, nhưng ý nghĩa dữ liệu và hành vi khi nguồn phát không đều rất khác nhau.

## 1. Hai cách hiểu về việc ghép luồng

Giả sử có hai nguồn:

~~~text
Nguồn A: A1 -> A2 -> A3
Nguồn B: B1 -> B2 -> B3
~~~

Với zip, các phần tử được ghép theo vị trí:

~~~text
(A1, B1) -> (A2, B2) -> (A3, B3)
~~~

Với combineLatest, sau khi cả hai nguồn đã phát giá trị đầu tiên, mỗi giá trị mới tạo một tổ hợp với giá trị gần nhất của nguồn còn lại. Ví dụ theo thứ tự phát sau:

~~~text
A1 -> B1 -> A2 -> A3 -> B2
~~~

Các tổ hợp được tạo:

~~~text
(A1, B1)
(A2, B1)
(A3, B1)
(A3, B2)
~~~

Điểm khác biệt nằm ở câu hỏi nghiệp vụ:

- Dùng zip khi hai giá trị ở cùng vị trí có quan hệ với nhau, ví dụ hai kết quả của cùng một tập chỉ mục hoặc hai luồng đã được đồng bộ theo thứ tự.
- Dùng combineLatest khi kết quả cần phản ánh trạng thái mới nhất của nhiều nguồn, ví dụ nhiệt độ hiện tại kết hợp với độ ẩm hiện tại để tạo snapshot môi trường.

Không nên chọn toán tử chỉ dựa trên số lượng nguồn. Hãy xác định trước liệu dữ liệu cần ghép theo cặp vị trí hay theo trạng thái mới nhất.

## 2. zip ghép phần tử thứ n với phần tử thứ n

Trong Reactor, Flux.zip kết hợp nhiều publisher bằng cách đợi một phần tử từ mỗi nguồn rồi gọi hàm kết hợp. Mỗi lần tạo được một bộ đầy đủ, toán tử phát ra một phần tử kết quả.

Ví dụ hai luồng có cùng số lượng phần tử:

~~~java
Flux<String> productIds = Flux.just("P-01", "P-02", "P-03");
Flux<Integer> quantities = Flux.just(2, 1, 4);

Flux<String> lines = Flux.zip(
    productIds,
    quantities,
    (productId, quantity) -> productId + " x " + quantity
);
~~~

Kết quả:

~~~text
P-01 x 2
P-02 x 1
P-03 x 4
~~~

Phần tử đầu tiên của productIds được ghép với phần tử đầu tiên của quantities; phần tử thứ hai được ghép với phần tử thứ hai. zip không kiểm tra product ID có tương ứng với quantity theo một khóa nghiệp vụ nào khác. Nó chỉ ghép theo thứ tự phát.

### Zip với Tuple

Nếu không truyền hàm kết hợp, Reactor có thể phát một Tuple2, Tuple3 hoặc tuple tương ứng với số nguồn:

~~~java
Flux<Tuple2<String, Integer>> pairs = Flux.zip(
    productIds,
    quantities
);

Flux<String> descriptions = pairs.map(tuple ->
    tuple.getT1() + " x " + tuple.getT2()
);
~~~

Tuple hữu ích khi cần giữ các giá trị riêng để xử lý ở bước sau. Với pipeline nghiệp vụ, một hàm kết hợp thường giúp thể hiện rõ kiểu kết quả và tránh để tuple lan rộng qua nhiều tầng.

### Zip cho Mono

Mono.zip phù hợp khi mỗi nguồn cung cấp một kết quả đơn lẻ. Ví dụ, một màn hình chi tiết cần thông tin khách hàng và địa chỉ giao hàng:

~~~java
Mono<Customer> customer = customerClient.findById(customerId);
Mono<Address> address = addressClient.findDefaultFor(customerId);

Mono<DeliveryProfile> profile = Mono.zip(
    customer,
    address,
    (customerValue, addressValue) ->
        new DeliveryProfile(customerValue, addressValue)
);
~~~

Kết quả chỉ được tạo khi cả hai Mono đều phát giá trị. Nếu một nguồn lỗi, lỗi được truyền xuống và kết quả kết hợp kết thúc bằng lỗi. Nếu một nguồn hoàn tất rỗng, không có đủ giá trị để tạo cặp nên Mono kết hợp hoàn tất rỗng.

## 3. zip phụ thuộc vào số phần tử của nguồn ngắn nhất

Với Flux.zip, mỗi kết quả cần một phần tử từ mọi nguồn. Vì vậy, số lượng kết quả tối đa bị giới hạn bởi nguồn có ít phần tử nhất.

~~~java
Flux<String> names = Flux.just("An", "Binh", "Chi");
Flux<Integer> scores = Flux.just(8, 9);

Flux<String> report = Flux.zip(
    names,
    scores,
    (name, score) -> name + ": " + score
);
~~~

Kết quả có hai phần tử:

~~~text
An: 8
Binh: 9
~~~

Nguồn scores hoàn tất sau hai phần tử. Không còn phần tử thứ ba để ghép với Chi, nên zip không thể tạo thêm cặp và luồng kết hợp hoàn tất. Các phần tử còn lại của nguồn dài hơn không tạo ra kết quả ghép.

Điều này rất quan trọng nếu hai luồng không có cùng số lượng. Nếu nghiệp vụ yêu cầu giữ mọi phần tử của nguồn dài hơn, zip không phù hợp nếu không có bước căn chỉnh hoặc giá trị thay thế. Có thể cần ghép theo khóa bằng lookup, dùng một nguồn chứa đầy đủ cấu trúc dữ liệu, hoặc xử lý từng nguồn riêng rồi kết hợp ở tầng khác.

## 4. zip ghép theo vị trí, không ghép theo thời điểm hoặc khóa

Các publisher có thể phát với tốc độ khác nhau. zip vẫn ghép phần tử theo thứ tự, không yêu cầu chúng đến cùng thời điểm.

| Thứ tự | Nguồn A | Nguồn B | Kết quả |
| ---: | --- | --- | --- |
| 1 | A1 đến sớm | B1 đến muộn | (A1, B1) khi cả hai đã sẵn sàng |
| 2 | A2 đến sớm | B2 đến sau | (A2, B2) khi cả hai đã sẵn sàng |
| 3 | A3 đến | B đã hoàn tất | Không tạo được cặp thứ ba |

Nếu A phát nhanh hơn B, các phần tử A có thể phải chờ trong hàng đợi nội bộ cho đến khi B phát phần tử tương ứng. Prefetch và demand ảnh hưởng đến lượng dữ liệu có thể được yêu cầu hoặc giữ trong quá trình ghép. Vì vậy, không nên dùng zip giữa một nguồn rất nhanh và một nguồn chậm mà không hiểu chi phí buffer và giới hạn demand.

Quan trọng hơn, vị trí chỉ đại diện cho cùng một thực thể nếu hợp đồng nguồn bảo đảm điều đó. Ví dụ, hai truy vấn độc lập có thể trả danh sách theo thứ tự khác nhau; ghép phần tử thứ nhất với phần tử thứ nhất có thể tạo dữ liệu sai dù pipeline không phát sinh lỗi kỹ thuật. Nếu cần ghép theo customerId, orderId hoặc một khóa khác, phải thực hiện matching theo khóa thay vì dựa vào vị trí.

## 5. combineLatest kết hợp các giá trị gần nhất

Flux.combineLatest phù hợp khi mỗi nguồn đại diện cho một phần trạng thái có thể thay đổi độc lập. Toán tử giữ giá trị mới nhất từ mỗi nguồn. Nó chưa phát kết quả cho đến khi tất cả nguồn đã phát ít nhất một giá trị; sau đó mỗi lần một nguồn phát giá trị mới, hàm kết hợp được gọi với giá trị mới nhất của tất cả nguồn.

Ví dụ, hệ thống giám sát nhận nhiệt độ và độ ẩm:

~~~java
Flux<Temperature> temperatures = sensor.temperatureReadings();
Flux<Humidity> humidities = sensor.humidityReadings();

Flux<ClimateSnapshot> snapshots = Flux.combineLatest(
    temperatures,
    humidities,
    (temperature, humidity) ->
        new ClimateSnapshot(temperature, humidity)
);
~~~

Nếu nhiệt độ phát ba lần trong khi độ ẩm chưa đổi, mỗi lần cập nhật nhiệt độ có thể tạo snapshot mới dùng cùng giá trị độ ẩm gần nhất. Khi độ ẩm thay đổi, snapshot tiếp theo dùng nhiệt độ gần nhất đã nhận.

### Ví dụ theo timeline

Giả sử các tín hiệu đến theo thứ tự:

| Thời điểm | Nguồn phát | Giá trị mới | Giá trị mới nhất A | Giá trị mới nhất B | Tổ hợp được phát |
| ---: | --- | --- | --- | --- | --- |
| 1 | A | A1 | A1 | Chưa có | Chưa phát |
| 2 | B | B1 | A1 | B1 | (A1, B1) |
| 3 | A | A2 | A2 | B1 | (A2, B1) |
| 4 | A | A3 | A3 | B1 | (A3, B1) |
| 5 | B | B2 | A3 | B2 | (A3, B2) |

combineLatest không ghép A2 với B2 theo chỉ số. Nó dùng trạng thái gần nhất của mỗi nguồn tại thời điểm một tín hiệu mới đến. Vì vậy, cùng một giá trị B1 có thể xuất hiện trong nhiều tổ hợp khi A thay đổi liên tục.

## 6. combineLatest không phát trước khi mọi nguồn có giá trị

Giả sử nguồn A đã phát nhiều giá trị nhưng nguồn B chưa phát lần nào. Chưa thể tạo tổ hợp đầy đủ, vì không có giá trị mới nhất của B. Các giá trị A có thể được cập nhật trong lúc chờ, nhưng downstream chưa nhận được kết quả kết hợp.

Khi B phát giá trị đầu tiên, toán tử tạo tổ hợp đầu tiên từ giá trị mới nhất của A và B. Sau đó, mỗi tín hiệu từ A hoặc B đều có thể tạo một kết quả mới.

Điều này quan trọng với nguồn hot hoặc nguồn có độ trễ khởi tạo. Nếu một cảm biến chưa gửi giá trị ban đầu, dashboard kết hợp nhiệt độ và độ ẩm có thể chưa có snapshot. Nếu cần trạng thái ban đầu, có thể cung cấp giá trị mặc định hợp lệ, lấy snapshot ban đầu từ kho dữ liệu hoặc dùng một publisher đảm bảo phát giá trị khởi tạo.

Không nên đưa giá trị mặc định tùy tiện chỉ để làm combineLatest phát sớm. Giá trị mặc định phải có ý nghĩa nghiệp vụ và được phân biệt với dữ liệu đo thật nếu người dùng cần biết trạng thái nào là ước lượng.

## 7. Hành vi khi nguồn hoàn tất hoặc lỗi

Hai toán tử có cách kết thúc khác nhau vì cách tạo kết quả khác nhau.

| Tình huống | zip | combineLatest |
| --- | --- | --- |
| Một nguồn phát giá trị | Chờ giá trị tương ứng từ mọi nguồn | Cập nhật giá trị mới nhất; chưa phát nếu còn nguồn chưa có giá trị đầu tiên |
| Một nguồn hoàn tất sau khi phát một số phần tử | Không thể tạo thêm cặp khi nguồn đó hết; kết quả kết thúc khi không còn bộ đầy đủ tiếp theo | Có thể tiếp tục dùng giá trị cuối của nguồn đã hoàn tất trong khi các nguồn khác tiếp tục phát; kết quả kết thúc khi các nguồn còn lại hoàn tất |
| Một nguồn hoàn tất mà chưa phát giá trị | Không thể tạo tuple; luồng kết hợp hoàn tất | Không thể có tổ hợp đầu tiên; luồng kết hợp hoàn tất |
| Một nguồn phát lỗi | Lỗi truyền xuống; các nguồn khác được hủy theo semantics của toán tử | Lỗi truyền xuống; các nguồn khác được hủy theo semantics của toán tử |
| Downstream hủy | Hủy subscription đến các nguồn upstream | Hủy subscription đến các nguồn upstream |

Với zip, khi một nguồn hoàn tất và không còn khả năng tạo phần tử tiếp theo cho một tuple, kết quả kết hợp cũng không thể tiếp tục. Với combineLatest, nếu nguồn đã phát giá trị rồi mới hoàn tất, giá trị cuối của nguồn đó vẫn có thể được dùng trong các tổ hợp mới khi nguồn khác phát tiếp. Nếu một nguồn hoàn tất rỗng, không thể tạo tổ hợp ban đầu.

Theo mặc định, lỗi từ một nguồn kết thúc phép ghép. Nếu muốn phục hồi lỗi ở từng nguồn, hãy đặt chính sách xử lý tại publisher đó trước khi ghép, ví dụ onErrorResume để thay bằng một giá trị hoặc publisher dự phòng. Cần cân nhắc dữ liệu dự phòng có thể bị hiểu nhầm là dữ liệu thật hay không.

Ví dụ:

~~~java
Mono<Configuration> configuration = configClient.load()
    .onErrorResume(error -> Mono.just(Configuration.defaults()));

Mono<FeatureFlags> flags = flagClient.load();

Mono<AppContext> context = Mono.zip(
    configuration,
    flags,
    AppContext::new
);
~~~

Ở đây, lỗi tải cấu hình được thay bằng cấu hình mặc định trước khi ghép. Nếu tải flags lỗi hoặc một nguồn hoàn tất rỗng, kết quả vẫn có thể lỗi hoặc rỗng tương ứng. Fallback phải được ghi nhận và quan sát nếu nó ảnh hưởng đến hành vi ứng dụng.

## 8. So sánh mục đích và chi phí

| Tiêu chí | zip | combineLatest |
| --- | --- | --- |
| Quy tắc ghép | Phần tử thứ n với phần tử thứ n | Giá trị mới với giá trị gần nhất của các nguồn còn lại |
| Điều kiện phát đầu tiên | Mỗi nguồn có một phần tử cho cùng vị trí | Mỗi nguồn đã phát ít nhất một giá trị |
| Số kết quả | Tối đa bằng số phần tử của nguồn ngắn nhất | Có thể phát nhiều lần sau khi các nguồn đã khởi tạo |
| Phần tử nguồn nhanh | Có thể phải chờ và được giữ để ghép với nguồn chậm | Cập nhật giá trị mới nhất; có thể tạo tổ hợp mới mỗi lần cập nhật |
| Phù hợp | Dữ liệu đồng bộ theo vị trí, kết quả song song theo cùng danh sách | Snapshot trạng thái, form nhiều trường, cảm biến và cấu hình thay đổi |
| Rủi ro chính | Ghép sai nếu thứ tự nguồn không cùng ý nghĩa; chờ nguồn chậm; buffer | Phát nhiều tổ hợp; giá trị cũ của nguồn ít cập nhật tiếp tục được dùng |

combineLatest không lưu toàn bộ lịch sử của mọi nguồn; về mặt ngữ nghĩa, nó cần giữ giá trị mới nhất của mỗi nguồn. Tuy nhiên, khi downstream chậm, việc điều tiết demand và các hàng đợi nội bộ vẫn cần được xem xét. Không nên suy ra rằng combineLatest không thể tạo áp lực bộ nhớ chỉ vì nó chỉ kết hợp latest values.

## 9. Chọn zip cho kết quả độc lập cần ghép thành một bộ

Một trường hợp điển hình là lấy dữ liệu từ nhiều dịch vụ độc lập để tạo một đối tượng tổng hợp. Ví dụ, một trang tổng quan cần hồ sơ người dùng, số dư ví và hạn mức:

~~~java
Mono<User> user = userClient.findById(userId);
Mono<Balance> balance = walletClient.getBalance(userId);
Mono<Limit> limit = policyClient.getLimit(userId);

Mono<AccountOverview> overview = Mono.zip(
    user,
    balance,
    limit,
    AccountOverview::new
);
~~~

Ba publisher cung cấp một kết quả đơn lẻ. Mono.zip đợi cả ba giá trị rồi tạo AccountOverview. Đây là mô hình phù hợp khi trang chỉ có ý nghĩa nếu nhận đủ ba thành phần, hoặc khi có chính sách fallback rõ ràng cho từng nguồn.

Nếu một nguồn chậm, kết quả tổng hợp phải chờ nguồn đó. Cần đặt timeout ở từng nguồn hoặc ở toàn bộ phép ghép theo yêu cầu nghiệp vụ. Timeout toàn bộ giới hạn thời gian chờ của trang; timeout từng nguồn giúp xác định thành phần nào chậm và có thể áp dụng fallback riêng.

## 10. Chọn combineLatest cho trạng thái thay đổi độc lập

Một form cấu hình có thể có hai trường được cập nhật độc lập: loại gói và khu vực. Khi bất kỳ trường nào thay đổi, ứng dụng cần tính lại mức giá dựa trên giá trị hiện tại của cả hai trường.

~~~java
Flux<PricingInput> inputs = Flux.combineLatest(
    selectedPlan,
    selectedRegion,
    (plan, region) -> new PricingInput(plan, region)
);
~~~

Một thay đổi ở selectedRegion tạo input mới bằng region mới cùng plan gần nhất. Không cần chờ mỗi nguồn phát một phần tử cùng chỉ số.

Nếu việc tính báo giá là đồng bộ và nhẹ, hàm kết hợp có thể trả trực tiếp PriceQuote. Nếu tính giá cần gọi một publisher bất đồng bộ, hãy lưu ý combinator đồng bộ của combineLatest không tự flatten publisher con. Có thể chuyển kết quả thành publisher sau khi ghép rồi dùng một bước compose phù hợp:

~~~java
Flux<PriceQuote> quotes = inputs
    .flatMap(pricingClient::quote);
~~~

Nếu người dùng thay đổi form liên tục, nhiều request báo giá có thể chạy đồng thời. Nếu chỉ kết quả của lựa chọn mới nhất còn cần thiết, có thể cân nhắc switchMap để hủy publisher con cũ khi input mới xuất hiện. Nếu cần giữ mọi báo giá, phải giới hạn concurrency và xác định chính sách hàng đợi.

## 11. Không dùng zip để ghép theo khóa nghiệp vụ

Giả sử hai nguồn trả về danh sách:

~~~text
Nguồn A: customer-01, customer-02, customer-03
Nguồn B: customer-02, customer-01, customer-03
~~~

Nếu dùng zip, kết quả sẽ ghép customer-01 với customer-02, rồi customer-02 với customer-01. Pipeline vẫn đúng theo hợp đồng zip nhưng sai về nghiệp vụ nếu mục tiêu là ghép dữ liệu cùng customer.

Khi cần ghép theo khóa, hãy dùng một cấu trúc thể hiện khóa rõ ràng:

- Tạo Map từ một nguồn rồi lookup khi xử lý nguồn còn lại.
- Dùng groupBy nếu cần phân luồng theo khóa và có chính sách quản lý vòng đời group.
- Thực hiện join tại database nếu hai tập dữ liệu cùng nằm trong hệ quản trị dữ liệu.
- Dùng một API trả về đối tượng đã kết hợp theo khóa.
- Dùng stream-processing engine hoặc state store nếu cần join các luồng sự kiện phân tán theo khóa và thời gian.

zip không phải join theo khóa và combineLatest cũng không phải join theo khóa. combineLatest ghép trạng thái mới nhất của toàn bộ nguồn, không tự tìm phần tử có cùng ID.

## 12. Demand, buffer và tốc độ nguồn

Cả zip và combineLatest đều phải tuân thủ demand từ downstream. Tuy nhiên, cách ghép tạo ra những áp lực khác nhau:

- Với zip, nguồn nhanh có thể có phần tử chờ trong khi toán tử đợi nguồn chậm phát phần tử tương ứng. Prefetch và demand ảnh hưởng đến lượng dữ liệu được yêu cầu hoặc giữ trong quá trình ghép.
- Với combineLatest, giá trị mới nhất của từng nguồn được cập nhật khi có tín hiệu. Một nguồn phát nhanh có thể tạo nhiều kết quả kết hợp trong khi nguồn khác giữ nguyên giá trị gần nhất.
- Nếu downstream chậm, demand được truyền ngược theo semantics của operator, nhưng các nguồn push không hỗ trợ demand vẫn có thể cần adapter buffer hoặc overflow policy.
- Nếu một nguồn phát quá nhanh, có thể cần sampling, throttling, giới hạn tốc độ hoặc gộp dữ liệu trước/sau điểm kết hợp tùy ý nghĩa.

Không nên dùng combineLatest như cách giảm dữ liệu một cách mặc định. Nó có thể phát một kết quả cho mỗi cập nhật của bất kỳ nguồn nào sau giai đoạn khởi tạo. Nếu nhiều nguồn cập nhật nhanh, số tổ hợp phát ra có thể rất lớn.

## 13. Cold, hot và số lần subscription khi ghép

Khi subscriber đăng ký vào publisher kết quả, toán tử ghép sẽ đăng ký với các publisher nguồn theo cách triển khai của Reactor. Nếu các nguồn là cold, mỗi lần subscribe vào kết quả thường có thể kích hoạt lại từng nguồn. Nếu nguồn là hot, subscriber có thể chỉ quan sát các tín hiệu phát sau khi đăng ký; dữ liệu trước đó không tự được phát lại.

Ví dụ:

~~~java
Mono<User> user = userClient.findById(userId);
Mono<Orders> orders = orderClient.findOrders(userId);

Mono<Dashboard> dashboard = Mono.zip(user, orders, Dashboard::new);
~~~

Nếu dashboard được subscribe hai lần và các nguồn cold, hai lần ghép có thể gọi lại cả hai client. Nếu muốn dùng chung một lần thực thi, cần cân nhắc cache, share hoặc cơ chế chia sẻ phù hợp với thời gian sống và tính mới của dữ liệu. Không chia sẻ cache nếu kết quả phụ thuộc tenant, người dùng hoặc quyền truy cập mà cache key không thể hiện đầy đủ phạm vi.

Với hot source, hãy đảm bảo subscriber được đăng ký trước thời điểm dữ liệu quan trọng phát ra hoặc nguồn có cơ chế replay/snapshot phù hợp. zip và combineLatest không tự khôi phục những phần tử hot đã bị bỏ lỡ trước khi subscription bắt đầu nhận.

## 14. Kiểm thử zip với StepVerifier

StepVerifier giúp kiểm tra thứ tự và nội dung các cặp do zip tạo:

~~~java
Flux<String> zipped = Flux.zip(
    Flux.just("A1", "A2", "A3"),
    Flux.just("B1", "B2"),
    (a, b) -> a + "-" + b
);

StepVerifier.create(zipped)
    .expectNext("A1-B1", "A2-B2")
    .verifyComplete();
~~~

Test xác minh zip chỉ tạo hai cặp vì nguồn thứ hai có hai phần tử. Có thể bổ sung test cho trường hợp một nguồn rỗng, một nguồn lỗi hoặc nguồn phát chậm bằng TestPublisher và virtual time.

## 15. Kiểm thử combineLatest bằng TestPublisher

Với combineLatest, điều quan trọng là kiểm soát thứ tự phát để xác minh nó đợi giá trị đầu tiên từ mọi nguồn và sau đó dùng giá trị gần nhất:

~~~java
TestPublisher<Integer> left = TestPublisher.create();
TestPublisher<String> right = TestPublisher.create();

Flux<String> combined = Flux.combineLatest(
    left,
    right,
    (number, label) -> number + ":" + label
);

StepVerifier.create(combined)
    .then(() -> left.next(1))
    .then(() -> right.next("A"))
    .expectNext("1:A")
    .then(() -> left.next(2))
    .expectNext("2:A")
    .then(() -> right.next("B"))
    .expectNext("2:B")
    .thenCancel()
    .verify();
~~~

Test thể hiện ba điểm:

1. Khi chỉ left phát 1, downstream chưa nhận kết quả vì right chưa có giá trị.
2. Khi right phát A, tổ hợp đầu tiên là 1:A.
3. Khi left phát 2, tổ hợp mới là 2:A; khi right phát B, tổ hợp tiếp theo là 2:B.

Trong test thực tế, hãy hoàn tất hoặc hủy các nguồn theo kịch bản và kiểm tra terminal signal. Nếu nguồn phát trên thread khác, dùng công cụ đồng bộ hoặc scheduler ảo thích hợp thay vì dựa vào timing ngẫu nhiên.

## 16. Những lỗi thường gặp

- **Dùng zip khi cần ghép theo ID:** zip chỉ ghép theo vị trí phát, không kiểm tra khóa nghiệp vụ.
- **Dùng combineLatest khi cần cặp dữ liệu cùng chỉ số:** toán tử có thể kết hợp một giá trị mới với giá trị cũ của nguồn khác.
- **Cho rằng combineLatest phát ngay khi một nguồn có dữ liệu:** nó cần ít nhất một giá trị từ mọi nguồn trước khi tạo tổ hợp đầu tiên.
- **Cho rằng zip chờ mọi nguồn hoàn tất rồi mới phát:** zip phát từng cặp ngay khi có đủ phần tử tương ứng.
- **Không xét nguồn ngắn nhất:** zip không thể tạo thêm kết quả khi một nguồn không còn phần tử tương ứng.
- **Không xét giá trị cũ trong combineLatest:** nguồn ít cập nhật có thể tiếp tục đóng góp giá trị cuối cùng vào nhiều tổ hợp.
- **Cho rằng combineLatest chỉ phát một kết quả cho mỗi chu kỳ:** mỗi tín hiệu mới từ bất kỳ nguồn nào sau khi khởi tạo đều có thể tạo tổ hợp mới.
- **Bỏ qua lỗi từ một nguồn:** lỗi mặc định kết thúc phép ghép; cần đặt fallback ở đúng nguồn nếu nghiệp vụ cho phép.
- **Không kiểm soát số lần subscription:** ghép các nguồn cold rồi subscribe nhiều lần có thể gọi lại mọi nguồn.
- **Bỏ qua nguồn hot:** subscriber đăng ký muộn có thể bỏ lỡ dữ liệu trước khi toán tử ghép bắt đầu nhận.
- **Quên áp lực buffer:** nguồn nhanh và downstream chậm có thể tạo hàng đợi hoặc nhiều tổ hợp chờ xử lý.

## 17. Quy trình chọn toán tử ghép

Trước khi nối nhiều publisher, hãy trả lời lần lượt:

1. Mỗi phần tử ở nguồn A có quan hệ với phần tử cùng vị trí ở nguồn B không? Nếu có và thứ tự được bảo đảm, cân nhắc zip.
2. Kết quả cần phản ánh trạng thái mới nhất của mọi nguồn khi bất kỳ nguồn nào thay đổi không? Nếu có, cân nhắc combineLatest.
3. Một nguồn có thể rỗng hoặc ngắn hơn nguồn khác không? Xác định kết quả mong muốn khi không thể tạo đủ bộ dữ liệu.
4. Có nguồn nào phát chậm hoặc nhanh hơn đáng kể không? Xem xét demand, prefetch, buffer, sampling và timeout.
5. Các nguồn là cold hay hot? Xác định số lần subscription, thời điểm đăng ký và nguy cơ bỏ lỡ dữ liệu.
6. Lỗi từ một nguồn có nên kết thúc toàn bộ kết quả không? Nếu không, đặt fallback có ngữ nghĩa rõ ràng trước khi ghép.
7. Các giá trị có cần ghép theo khóa thay vì vị trí/trạng thái gần nhất không? Nếu có, dùng chiến lược join theo khóa.
8. Viết test điều khiển thứ tự phát bằng StepVerifier và TestPublisher để chứng minh semantics đã chọn.

zip và combineLatest đều ghép nhiều nguồn nhưng phục vụ hai quan hệ dữ liệu khác nhau. zip tạo bộ từ các phần tử cùng vị trí và bị giới hạn bởi nguồn ngắn nhất; combineLatest tạo snapshot từ giá trị gần nhất sau khi mọi nguồn đã có giá trị ban đầu. Hãy chọn theo ý nghĩa của dữ liệu, xét kỹ nguồn rỗng, lỗi, tốc độ phát, subscription và buffer. Khi kiểm thử được timeline của các nguồn bằng StepVerifier, pipeline ghép luồng sẽ dễ dự đoán và tránh những kết quả có vẻ hợp lệ về kỹ thuật nhưng sai về nghiệp vụ.
