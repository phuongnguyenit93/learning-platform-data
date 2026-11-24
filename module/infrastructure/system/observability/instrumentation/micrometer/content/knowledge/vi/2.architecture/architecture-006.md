# Giới hạn tính di động khi các hệ thống hỗ trợ thống kê khác nhau

## Bối cảnh

Micrometer cung cấp một API đo lường thống nhất cho ứng dụng Java. Thay vì để mã nghiệp vụ phụ thuộc trực tiếp vào Prometheus, StatsD, Graphite hay một nền tảng giám sát của nhà cung cấp, ứng dụng có thể tạo **Counter**, **Gauge**, **Timer**, **DistributionSummary** thông qua **MeterRegistry**. Registry chịu trách nhiệm chuyển các phép đo đó sang định dạng mà hệ thống đích hiểu được.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, mục tiêu là sử dụng các loại meter này để đo lường ứng dụng Java, tích hợp với Spring Boot, xuất metrics đến hệ giám sát, kiểm soát cardinality và diễn giải số đo vận hành. Khi thiết kế kiến trúc, cần hiểu rõ một giới hạn: **API thống nhất không làm cho mọi backend có cùng mô hình dữ liệu, khả năng thống kê hoặc cách truy vấn**.

Một ứng dụng có thể đổi registry mà không phải sửa phần lớn mã instrumentation, nhưng dữ liệu sau khi xuất có thể khác về tên, đơn vị, độ phân giải, cách tổng hợp và khả năng truy vấn. Vì vậy, tính di động của Micrometer mạnh nhất ở ranh giới API và mã nguồn; tính tương đương về ngữ nghĩa và vận hành còn phụ thuộc backend.

## Ba mức độ của tính di động

Có thể đánh giá khả năng chuyển đổi backend theo ba mức:

| Mức | Câu hỏi cần trả lời | Micrometer hỗ trợ đến đâu |
|---|---|---|
| Di động mã nguồn | Mã Java có tiếp tục dùng cùng API meter khi đổi registry không? | Tốt với các loại meter và thao tác phổ biến |
| Di động ngữ nghĩa | Cùng một phép đo có giữ nguyên ý nghĩa, đơn vị, độ phân giải và cách tổng hợp không? | Có giới hạn; phụ thuộc khả năng của registry và backend |
| Di động vận hành | Dashboard, truy vấn, cảnh báo, retention và chi phí có giữ nguyên không? | Không được bảo đảm; thường cần cấu hình hoặc chuyển đổi riêng |

Ví dụ, mã ứng dụng ghi thời gian xử lý bằng **Timer** có thể tiếp tục biên dịch khi chuyển từ Prometheus sang một registry khác. Tuy nhiên, backend mới có thể lưu histogram theo cách khác, không hỗ trợ cùng các bucket, hoặc yêu cầu truy vấn khác để tính phân vị. Mã nguồn vẫn di động trong khi dashboard và cảnh báo không còn tương đương.

Khi nói một instrumentation có tính di động, do đó cần chỉ rõ đang nói đến mức nào. Chỉ kiểm tra mã Java biên dịch thành công là chưa đủ để kết luận số đo có thể thay thế trực tiếp trong vận hành.

## Vì sao các backend biểu diễn metrics khác nhau?

Micrometer là lớp API và lớp chuyển đổi. Nó chuẩn hóa cách ứng dụng khai báo meter, nhưng không thể loại bỏ các quyết định thiết kế của hệ thống nhận dữ liệu. Những khác biệt quan trọng thường nằm ở các nhóm sau.

### 1. Mô hình dữ liệu và loại meter

Micrometer cung cấp một số loại meter phổ biến:

- **Counter** ghi nhận số lần một sự kiện xảy ra. Giá trị thường tăng đơn điệu.
- **Gauge** quan sát giá trị hiện tại của một đối tượng hoặc trạng thái, chẳng hạn số tác vụ đang chờ.
- **Timer** đo thời lượng và số lần một thao tác được thực hiện.
- **DistributionSummary** ghi nhận phân phối của các giá trị không nhất thiết là thời gian, chẳng hạn kích thước payload.
- **LongTaskTimer** theo dõi những tác vụ còn đang chạy trong một khoảng thời gian dài.

Các backend không nhất thiết có kiểu dữ liệu tương ứng một-một. Một registry có thể chuyển **Timer** thành nhiều chuỗi dữ liệu như số lần ghi nhận, tổng thời gian, giá trị lớn nhất và các bucket histogram. Backend khác có thể nhận một bản ghi distribution, hoặc chỉ lưu một số thống kê tổng hợp.

Sự khác biệt này ảnh hưởng trực tiếp đến truy vấn. Một biểu đồ cần tốc độ yêu cầu mỗi giây có thể tính từ bộ đếm tích lũy. Một biểu đồ độ trễ p95 lại cần dữ liệu phân phối phù hợp. Nếu backend chỉ nhận được tổng và số lượng, không thể khôi phục chính xác phân phối ban đầu từ hai giá trị đó.

Không nên giả định rằng tên meter hoặc loại meter trong mã Java sẽ xuất hiện nguyên dạng trong mọi hệ thống. Hãy kiểm tra tài liệu của registry và backend để biết mỗi loại được ánh xạ thành những trường dữ liệu nào.

### 2. Histogram, percentile và khả năng tổng hợp

Độ trễ là ví dụ rõ nhất cho khác biệt về thống kê.

Micrometer có thể xuất percentile được tính tại phía ứng dụng bằng **publishPercentiles(...)**. Ví dụ, mỗi instance có thể tự tính p50, p95 và p99 từ các lần ghi nhận của chính instance đó. Cách này hữu ích khi cần xem phân phối cục bộ, nhưng các percentile đã tính riêng không thể được cộng hoặc lấy trung bình để tạo ra percentile chính xác cho toàn bộ hệ thống.

Giả sử hai instance có độ trễ p95 lần lượt là 100 ms và 900 ms. Lấy trung bình thành 500 ms không cho biết p95 của toàn bộ request. Kết quả tổng thể còn phụ thuộc số lượng mẫu và phân phối của từng instance.

Với **publishPercentileHistogram()**, registry có thể xuất các bucket histogram để backend tổng hợp số lượng quan sát theo các ngưỡng. Nếu các instance sử dụng cùng ranh giới bucket và backend hỗ trợ phép tổng hợp tương ứng, dữ liệu histogram có thể được cộng gộp để tính phân vị ở phạm vi rộng hơn.

Tuy vậy, histogram cũng có giới hạn:

- Backend có thể không hỗ trợ histogram theo cùng cách hoặc có thể chuyển đổi dữ liệu sang cấu trúc riêng.
- Ranh giới bucket khác nhau làm giảm khả năng tổng hợp nhất quán.
- Số bucket và số chuỗi dữ liệu tăng có thể làm tăng bộ nhớ, dung lượng lưu trữ và chi phí truy vấn.
- Một số hệ thống dùng histogram có bucket cố định; hệ thống khác dùng cấu trúc phân phối hoặc sketch có độ chính xác và đặc tính riêng.
- Cấu hình percentile phía client và histogram phía server trả lời các câu hỏi khác nhau, không thể thay thế tùy ý cho nhau.

Micrometer cũng cho phép khai báo các ngưỡng dịch vụ (service-level objectives, SLO) cho timer hoặc distribution. Các ngưỡng này hữu ích khi cần biết có bao nhiêu quan sát nằm dưới một giới hạn nghiệp vụ. Tuy nhiên, khả năng xuất, lưu và truy vấn các ngưỡng vẫn phụ thuộc registry và backend.

Khi cần tổng hợp độ trễ giữa nhiều instance, nên ưu tiên histogram có cấu hình bucket hoặc SLO thống nhất nếu backend đích hỗ trợ. Chỉ dùng percentile phía client khi đã xác định rõ phạm vi của percentile và không yêu cầu cộng gộp chúng thành một percentile toàn hệ thống.

### 3. Tag, label và cardinality

Micrometer biểu diễn chiều dữ liệu bằng tag dạng cặp khóa-giá trị. Ví dụ, meter **checkout.payment** có thể mang các tag **payment_method=card** và **outcome=success**. Cách biểu diễn này phù hợp với các backend có mô hình metrics đa chiều.

Tuy nhiên, không phải backend nào cũng có mô hình tag giống nhau:

- Prometheus sử dụng label để phân biệt các time series.
- Các giao thức hoặc biến thể StatsD có thể hỗ trợ tag ở mức độ khác nhau; DogStatsD có cơ chế tag riêng, còn triển khai StatsD cơ bản thường không có cùng khả năng.
- Graphite truyền thống thường tổ chức tên metric theo đường dẫn phân cấp. Một số triển khai có hỗ trợ tag, nhưng không nên mặc định mọi môi trường Graphite đều xử lý chiều dữ liệu như Prometheus.
- Các nền tảng giám sát dạng dịch vụ có thể hỗ trợ tag nhưng áp dụng giới hạn về số lượng tag, số giá trị tag hoặc cardinality.

Sự khác biệt về cardinality có thể trở thành vấn đề lớn khi một tag nhận quá nhiều giá trị. Nếu đưa **customer_id**, **order_id**, email hoặc URL đầy đủ vào tag, số chuỗi dữ liệu có thể tăng theo số người dùng hoặc số giao dịch. Hậu quả là tăng bộ nhớ, chi phí ingest, dung lượng lưu trữ và độ trễ truy vấn; một số backend còn từ chối hoặc giới hạn dữ liệu.

Nên dùng tag có tập giá trị hữu hạn và có ý nghĩa vận hành, chẳng hạn **outcome=success|failure**, **payment_method=card|bank_transfer|wallet** hoặc **region=ap-southeast-1**. Dữ liệu định danh từng giao dịch phù hợp hơn với log hoặc trace, nơi có cơ chế tra cứu và lưu trữ khác.

Có thể áp dụng giới hạn tag ngay trong registry:

~~~java
registry.config().meterFilter(
    MeterFilter.maximumAllowableTags(
        "checkout.payment",
        "payment_method",
        4,
        MeterFilter.deny()
    )
);
~~~

Bộ lọc trên giới hạn số giá trị khác nhau của tag **payment_method** cho meter có tên bắt đầu bằng **checkout.payment**. Khi vượt ngưỡng, meter mới bị từ chối theo bộ lọc được cung cấp. Cần chọn giới hạn dựa trên tập giá trị hợp lệ của nghiệp vụ; không nên dùng giới hạn như cách che giấu một thiết kế tag có cardinality không kiểm soát.

Các tag dùng chung như tên dịch vụ hoặc môi trường có thể được cấu hình tập trung bằng **commonTags**. Tên và giá trị tag nên được chuẩn hóa, ổn định giữa các instance để backend có thể nhóm dữ liệu đúng cách.

### 4. Quy tắc đặt tên và đơn vị đo

Tên meter trong mã ứng dụng thường dùng dấu chấm để phân tách thành phần, ví dụ **checkout.payment.duration**. Mỗi registry có thể áp dụng **NamingConvention** để chuyển tên sang định dạng của backend. Một hệ thống có thể dùng dấu gạch dưới, hệ thống khác dùng đường dẫn phân cấp hoặc quy tắc đặt tên riêng.

Việc chuyển đổi tên có thể gây ra các tình huống:

- Hai tên khác nhau trong mã Java trở thành cùng một tên sau khi chuẩn hóa.
- Hậu tố hoặc tiền tố do backend thêm vào làm tên metric khác với tên ban đầu.
- Tên tag hoặc ký tự đặc biệt không được backend chấp nhận.
- Dashboard và alert cũ tham chiếu tên đã biến đổi theo quy tắc của backend trước.

Đơn vị đo cũng cần được xem xét. **Timer** nhận thời lượng theo kiểu dữ liệu thời gian của Java, nhưng registry có thể xuất giá trị theo giây, mili giây hoặc đơn vị cơ sở mà backend quy định. **DistributionSummary** có thể đại diện cho byte, số phần tử hoặc một đại lượng nghiệp vụ khác. Nếu không khai báo và diễn giải đơn vị nhất quán, hai biểu đồ cùng tên có thể hiển thị các con số khác nhau mà người vận hành khó nhận ra.

Nên đặt tên meter mô tả đại lượng được đo, khai báo **description** và **baseUnit** khi phù hợp, đồng thời giữ quy ước tên và đơn vị nhất quán trong toàn bộ dịch vụ. Không nên dựa vào tên hiển thị trên dashboard để suy ra đơn vị gốc.

### 5. Thu thập, temporality và cách tính tốc độ

Các hệ thống giám sát có thể thu thập dữ liệu theo mô hình pull hoặc push.

Với pull, backend chủ động scrape endpoint của ứng dụng theo một chu kỳ. Prometheus là ví dụ phổ biến. Với push, ứng dụng hoặc agent gửi dữ liệu đến máy chủ theo chu kỳ hoặc theo từng đợt; nhiều cấu hình StatsD và registry của nhà cung cấp hoạt động theo mô hình này.

Cùng một **Counter** có thể được biểu diễn bằng giá trị tích lũy từ khi tiến trình khởi động hoặc bằng phần tăng thêm trong một khoảng thời gian. Khái niệm này thường được gọi là temporality. Hệ thống nhận dữ liệu phải hiểu đúng cách biểu diễn để tính tốc độ và tổng số.

Các vấn đề cần quan tâm gồm:

- Counter có thể bắt đầu lại từ đầu khi tiến trình khởi động lại.
- Backend cần phân biệt reset của counter với mức giảm thật sự của đại lượng.
- Chu kỳ scrape hoặc push ảnh hưởng độ phân giải thời gian và khả năng quan sát spike ngắn.
- Dữ liệu delta và cumulative cần được chuyển đổi đúng trước khi tổng hợp.
- Gauge biểu diễn giá trị quan sát tại thời điểm thu thập; nếu không có lần cập nhật mới, cách backend xử lý dữ liệu cũ có thể khác nhau.

Không nên xuất một giá trị đã tính tốc độ rồi tiếp tục áp dụng hàm tính tốc độ ở backend. Cần thống nhất rõ meter đang lưu tổng tích lũy, phần tăng thêm hay giá trị tức thời, sau đó viết truy vấn phù hợp với mô hình đó.

### 6. Retention, downsampling và ngữ nghĩa truy vấn

Micrometer không quyết định chính sách lưu trữ cuối cùng. Backend có thể giữ dữ liệu thô trong một khoảng thời gian, sau đó downsample thành các khoảng tổng hợp dài hơn. Một số nền tảng còn giới hạn độ phân giải, số chiều truy vấn hoặc thời gian lưu theo loại dữ liệu.

Điều này khiến hai backend có thể cho kết quả khác nhau khi truy vấn cùng một khoảng thời gian. Một spike ngắn có thể xuất hiện rõ trong dữ liệu thô nhưng biến mất sau downsampling. Giá trị max có thể được giữ lại, bị tổng hợp hoặc được tính theo cửa sổ thời gian khác. Cách xử lý khoảng dữ liệu bị thiếu và dữ liệu đến muộn cũng có thể khác.

Vì vậy, việc chuyển backend cần xem xét cả truy vấn và chính sách lưu trữ. Một cảnh báo dựa trên trung bình năm phút không tương đương với cảnh báo dựa trên p95 của histogram trong cùng khoảng thời gian. Tên metric giống nhau không làm cho hai biểu thức truy vấn có cùng ngữ nghĩa.

## So sánh một số nhóm backend

Bảng dưới đây mô tả đặc điểm thường gặp để định hướng thiết kế. Khả năng cụ thể vẫn phụ thuộc phiên bản registry, cấu hình và sản phẩm backend đang triển khai.

| Nhóm backend | Mô hình thường gặp | Điểm cần kiểm tra khi chuyển đổi |
|---|---|---|
| Prometheus | Pull, time series đa chiều bằng label, counter/gauge và histogram | Cardinality label, bucket histogram, quy tắc tên metric và hàm truy vấn |
| StatsD / DogStatsD | Push, metric được gửi theo giao thức; khả năng tag phụ thuộc biến thể | Loại metric được hỗ trợ, tag có được giữ không, chu kỳ flush và cách server tổng hợp |
| Graphite | Thường dùng đường dẫn phân cấp để biểu diễn metric | Cách mã hóa tag vào tên, nguy cơ va chạm tên, độ phân giải và downsampling |
| OTLP và hệ thống nhận OpenTelemetry | Dữ liệu metrics có thuộc tính, resource, kiểu dữ liệu và temporality | Chuyển đổi histogram, cumulative/delta, resource attribute và khả năng của collector/backend |
| Nền tảng giám sát dạng dịch vụ | Thường có tag và API truy vấn riêng | Giới hạn cardinality, loại distribution, chính sách ingest, retention và chi phí |

Bảng này không phải bảng xếp hạng. Mỗi backend tối ưu cho cách thu thập, lưu trữ và truy vấn khác nhau. Kiến trúc nên chọn backend theo yêu cầu vận hành, sau đó xác định phần giao nhau mà instrumentation cần tuân thủ.

## Thiết kế instrumentation có thể chuyển đổi

### 1. Xác định tập tính năng chung

Trước khi viết instrumentation, hãy xác định các khả năng mà mọi backend mục tiêu đều hỗ trợ ở mức đủ dùng:

- Counter và gauge cơ bản.
- Timer hoặc phép đo thời lượng có count và tổng thời gian.
- Tag với tập giá trị hữu hạn.
- Quy ước đơn vị và tên ổn định.
- Cách thu thập và tính tốc độ phù hợp với temporality của registry.
- Một cách biểu diễn phân phối đáp ứng yêu cầu truy vấn chung.

Tập tính năng này là hợp đồng metrics của ứng dụng. Những khả năng nâng cao như percentile phía client, histogram tùy chỉnh, exemplar hoặc truy vấn đặc thù nên được xem là phần mở rộng có điều kiện. Mã nghiệp vụ không nên phụ thuộc vào phần mở rộng nếu yêu cầu là có thể đổi backend mà không thay đổi ý nghĩa đo lường.

### 2. Giữ instrumentation gần với ngữ nghĩa nghiệp vụ

Ví dụ sau ghi nhận thời lượng thanh toán. Tag **payment_method** chỉ nhận giá trị từ một tập phương thức đã được kiểm soát.

~~~java
Timer paymentTimer = Timer.builder("checkout.payment")
    .description("Thoi gian xu ly thanh toan")
    .tag("payment_method", paymentMethod)
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .register(registry);

paymentTimer.record(() -> paymentGateway.charge(request));
~~~

Đoạn mã thể hiện cách khai báo một timer và yêu cầu registry xuất histogram cùng các ngưỡng SLO. Khi áp dụng trong hệ thống thực tế:

- **paymentMethod** phải được kiểm tra hoặc ánh xạ về giá trị cho phép trước khi trở thành tag.
- Tất cả instance cần dùng cấu hình phân phối tương thích nếu dữ liệu được tổng hợp.
- Backend đích phải hỗ trợ cách registry xuất histogram và SLO.
- Nếu backend không hỗ trợ các tùy chọn phân phối này, cần xác định rõ phần thống kê nào còn được giữ lại.

Nếu yêu cầu chỉ là đo tổng thời gian và số lần xử lý, có thể bỏ cấu hình histogram để giảm số chuỗi dữ liệu. Chỉ bật phân phối khi dashboard hoặc cảnh báo thực sự cần phân tích độ trễ.

### 3. Chuẩn hóa tag và tên meter

Có thể thêm tag dùng chung cho registry:

~~~java
registry.config().commonTags(
    "service", serviceName,
    "environment", environment
);
~~~

Các giá trị này nên đến từ cấu hình triển khai và phải nhất quán giữa các instance thuộc cùng dịch vụ. Không đưa request ID, user ID, địa chỉ IP hoặc URL có tham số vào tag dùng chung.

Nên xây dựng quy ước tên theo đại lượng và đơn vị, chẳng hạn:

| Tên meter | Ý nghĩa | Đơn vị hoặc cách diễn giải |
|---|---|---|
| **checkout.payment** | Số lần và phân phối thời lượng xử lý thanh toán nếu dùng Timer | Thời gian |
| **checkout.payment.failures** | Số lần thanh toán thất bại | Lần |
| **checkout.queue.waiting** | Số tác vụ hiện đang chờ | Tác vụ |
| **checkout.request.payload** | Phân phối kích thước payload | Byte |

Tên cụ thể cần tuân thủ quy ước của dự án. Điều quan trọng là một meter không đổi ý nghĩa chỉ vì backend hoặc dashboard thay đổi.

### 4. Đặt cấu hình riêng ở ranh giới registry

Cấu hình backend nên nằm ở tầng khởi tạo registry, cấu hình Spring Boot hoặc cấu hình triển khai. Ví dụ, cùng một meter nghiệp vụ có thể được xuất qua một registry Prometheus trong môi trường này và registry OTLP trong môi trường khác.

**MeterFilter** và **NamingConvention** giúp điều chỉnh tên, tag hoặc loại meter tại ranh giới registry. Đây là nơi phù hợp để xử lý khác biệt của backend. Nếu cần một tag hoặc cách đặt tên chỉ phục vụ riêng một backend, hãy ghi rõ đó là phần mở rộng riêng, tránh để mã nghiệp vụ phụ thuộc vào nó.

**CompositeMeterRegistry** có thể gửi cùng một phép đo đến nhiều registry. Cách này hữu ích khi chuyển đổi từng bước hoặc cần xuất đồng thời trong một giai đoạn. Tuy nhiên, composite chỉ phân phối phép đo đến các registry; nó không làm cho tên, histogram, tag, temporality hay truy vấn của các backend trở nên giống nhau. Mỗi registry vẫn áp dụng quy tắc chuyển đổi riêng.

### 5. Kiểm thử cả instrumentation lẫn đầu ra

**SimpleMeterRegistry** hữu ích cho kiểm thử mã tạo meter mà không cần kết nối backend thật. Có thể xác minh meter được đăng ký, tag có giá trị dự kiến, counter tăng đúng và timer ghi nhận số lần cùng thời lượng.

Ví dụ:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

Counter counter = Counter.builder("checkout.payment.failures")
    .register(registry);

counter.increment();

assertThat(registry.get("checkout.payment.failures")
    .counter()
    .count()).isEqualTo(1.0);
~~~

Kiểm thử này xác nhận hành vi instrumentation ở mức Micrometer. Nó không chứng minh exporter của Prometheus, OTLP hay StatsD tạo ra dữ liệu giống nhau.

Với backend quan trọng, nên bổ sung kiểm thử ở ranh giới xuất dữ liệu. Có thể khởi tạo registry tương ứng với máy chủ giả lập, kiểm tra payload được gửi, tên và đơn vị sau chuyển đổi, tag được giữ lại, cũng như cấu hình histogram. Khi thay backend, hãy chạy cùng một bộ tình huống kiểm thử và so sánh ý nghĩa của dữ liệu đầu ra thay vì chỉ so sánh số lượng meter.

## Quy trình đánh giá khi đổi backend

Một lần chuyển đổi backend nên đi qua các bước sau:

1. **Lập danh mục meter:** ghi lại tên, loại, đơn vị, tag, mô tả và mục đích vận hành của từng meter quan trọng.
2. **Xác định yêu cầu truy vấn:** liệt kê dashboard, alert, SLO và truy vấn phụ thuộc vào từng meter.
3. **Đối chiếu mô hình dữ liệu:** kiểm tra cách registry mới ánh xạ counter, gauge, timer, summary, histogram và tag.
4. **Đối chiếu phân phối:** xác nhận percentile được tính ở client hay backend, bucket/SLO có tương thích và có thể tổng hợp giữa các instance hay không.
5. **Đánh giá cardinality:** tính số chiều và số giá trị tag dự kiến; loại bỏ tag có giá trị không giới hạn.
6. **Kiểm tra đơn vị và tên:** xác minh naming convention, hậu tố, đơn vị cơ sở và khả năng va chạm tên.
7. **Kiểm tra thu thập và lưu trữ:** xác định pull/push, chu kỳ thu thập, temporality, reset counter, retention và downsampling.
8. **Chạy song song có kiểm soát:** nếu cần, dùng composite registry hoặc một giai đoạn xuất kép để so sánh dữ liệu trong cùng điều kiện.
9. **Chuyển dashboard và alert:** viết lại truy vấn theo mô hình backend mới, sau đó xác minh kết quả trên dữ liệu thực.
10. **Chốt hợp đồng metrics:** cập nhật tài liệu về tên, đơn vị, tag, bucket và giới hạn được phép để các dịch vụ khác tuân thủ.

Khi so sánh hai backend, nên dùng cùng một tập sự kiện đầu vào và cùng khoảng thời gian. Nếu dữ liệu được thu thập ở các chu kỳ khác nhau, hoặc một bên đã downsample trong khi bên kia còn dữ liệu thô, chênh lệch quan sát được có thể đến từ pipeline chứ không phải từ ứng dụng.

## Những sai lầm thường gặp

**Cho rằng cùng API nghĩa là cùng dữ liệu.** Cùng một **Timer** có thể được xuất thành nhiều chuỗi dữ liệu hoặc một cấu trúc distribution. Cần kiểm tra ánh xạ thực tế của registry.

**Dùng percentile phía client rồi cộng các instance.** Percentile của từng instance không thể được cộng hoặc lấy trung bình để tạo percentile chính xác toàn hệ thống. Hãy dùng histogram có thể tổng hợp nếu backend hỗ trợ và cấu hình bucket thống nhất.

**Đưa định danh duy nhất vào tag.** Tag có cardinality cao có thể làm tăng mạnh số time series, chi phí và độ trễ truy vấn. Dùng log hoặc trace cho dữ liệu cần định danh từng request.

**Dựa vào tên metric để suy ra đơn vị.** Registry có thể đổi tên hoặc đổi đơn vị khi xuất. Cần kiểm tra metadata và truy vấn thực tế ở backend.

**Kiểm thử chỉ bằng SimpleMeterRegistry.** Kiểm thử này xác nhận logic tạo meter, không xác nhận payload hoặc ngữ nghĩa của backend đích.

**Chuyển backend mà không chuyển dashboard và alert.** Query language, cách tính rate, histogram và retention có thể khác. Dashboard cũ có thể vẫn chạy nhưng trả về kết quả sai hoặc không còn ý nghĩa.

## Kết luận

Micrometer tạo ra một lớp instrumentation thống nhất cho ứng dụng Java và giảm sự phụ thuộc của mã nghiệp vụ vào một hệ thống metrics cụ thể. Lớp trừu tượng này không thể bảo đảm mọi backend hỗ trợ cùng loại thống kê hoặc lưu trữ dữ liệu theo cùng ngữ nghĩa.

Muốn giữ khả năng chuyển đổi, cần thiết kế một hợp đồng metrics rõ ràng: meter có ý nghĩa ổn định, tên và đơn vị nhất quán, tag có cardinality được kiểm soát, histogram phù hợp với yêu cầu tổng hợp, và cấu hình backend nằm ở ranh giới registry. Khi thay đổi hệ thống giám sát, hãy kiểm thử dữ liệu sau xuất, truy vấn, dashboard và alert như một phần của quá trình chuyển đổi.
