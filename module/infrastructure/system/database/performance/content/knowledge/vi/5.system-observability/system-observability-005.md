# Đo thời gian truy vấn bằng số liệu ứng dụng và dấu vết phân tán

Muốn tối ưu một truy vấn cơ sở dữ liệu, trước hết cần biết truy vấn đó mất bao lâu trong workload thực tế, được gọi bao nhiêu lần, xuất hiện ở đường xử lý nào và phần thời gian nào khiến request chậm. Một con số thời gian trong log SQL có thể hữu ích, nhưng thường chưa đủ để giải thích trải nghiệm đầu cuối. Ứng dụng có thể chờ connection pool, gọi nhiều câu lệnh tuần tự, đọc một tập kết quả lớn hoặc xử lý dữ liệu sau khi cơ sở dữ liệu đã hoàn tất.

Trong chương **Quan sát hệ thống** của module **DATABASE_PERFORMANCE**, bài học này trình bày cách đo thời gian truy vấn từ phía ứng dụng bằng metrics và distributed tracing. Module rèn phương pháp tối ưu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; do đó, các số đo cần phản ánh workload, có thể liên kết với truy vấn và đủ tin cậy để so sánh trước/sau điều chỉnh. Bạn sẽ học cách chọn chỉ số, đặt span, truyền trace context, gắn metadata an toàn, phân tích phân vị và kết hợp dữ liệu ứng dụng với thông tin từ máy chủ cơ sở dữ liệu.

## 1. Hai công cụ bổ sung nhau: metrics và traces

Metrics và traces trả lời hai loại câu hỏi khác nhau.

**Metrics (số liệu tổng hợp)** cho biết hệ thống đang hoạt động như thế nào trong một khoảng thời gian. Ví dụ:

- Có bao nhiêu lần gọi cơ sở dữ liệu mỗi phút?
- Thời gian truy vấn p50, p95 và p99 là bao nhiêu?
- Tỷ lệ lỗi và timeout có tăng không?
- Pool kết nối có bao nhiêu kết nối đang hoạt động, rảnh hoặc đang chờ?
- Một nhóm thao tác có tổng thời gian tiêu thụ lớn đến mức nào?

Metrics phù hợp để theo dõi xu hướng, so sánh theo thời gian, xây dựng dashboard và cảnh báo. Chúng thường được tổng hợp từ rất nhiều lần gọi nên không giữ đầy đủ chi tiết của từng request.

**Distributed tracing (dấu vết phân tán)** mô tả hành trình của một request qua nhiều thành phần. Một trace có thể chứa span của gateway, dịch vụ ứng dụng, repository, driver cơ sở dữ liệu và dịch vụ ngoài. Mỗi span có thời điểm bắt đầu, thời lượng, quan hệ cha/con, thuộc tính và sự kiện. Trace giúp trả lời:

- Request cụ thể đã đi qua những thành phần nào?
- Span nào chiếm phần lớn thời gian?
- Truy vấn nào được gọi và gọi bao nhiêu lần trong request?
- Các lần gọi cơ sở dữ liệu có diễn ra tuần tự hay song song?
- Lỗi hoặc khoảng chờ xuất hiện ở chặng nào?

Hai công cụ nên được dùng cùng nhau. Metrics phát hiện rằng p99 của thao tác đọc đơn hàng tăng trong một khoảng thời gian; trace giúp chọn một số request đại diện để tìm span gây chậm. Trace cũng có thể được liên kết ngược từ một điểm dữ liệu metrics nếu hệ thống hỗ trợ exemplars hoặc cơ chế tương đương.

Không nên dùng một vài trace đã lấy mẫu để thay thế thống kê workload đầy đủ. Metrics thường được thu thập liên tục và tổng hợp theo chu kỳ; tracing có thể lấy mẫu để kiểm soát chi phí lưu trữ và xử lý.

## 2. Xác định chính xác khoảng thời gian cần đo

Trước khi tạo metric hoặc span, hãy định nghĩa thao tác được đo. “Thời gian truy vấn” có thể chỉ nhiều khoảng khác nhau:

| Tên khoảng đo | Mốc bắt đầu | Mốc kết thúc | Ý nghĩa |
|---|---|---|---|
| Chờ lấy kết nối | Bắt đầu yêu cầu connection pool | Nhận được kết nối hoặc thất bại | Thời gian ứng dụng đợi một kết nối |
| Gọi câu lệnh | Bắt đầu gọi driver | Nhận kết quả ban đầu | Bao gồm trao đổi driver/mạng và xử lý ban đầu |
| Đọc kết quả | Bắt đầu duyệt ResultSet | Đọc xong hoặc dừng đọc | Bao gồm fetch bổ sung và xử lý hàng tại ứng dụng |
| Thao tác DB ở ứng dụng | Bắt đầu thao tác repository/DAO | Hoàn tất toàn bộ thao tác | Có thể gồm lấy kết nối, câu lệnh và đọc kết quả |
| Giao dịch | Bắt đầu transaction | Commit hoặc rollback | Bao gồm các câu lệnh và công việc nằm trong transaction |
| Request đầu cuối | Nhận request | Hoàn tất response theo mốc đã chọn | Độ trễ mà ứng dụng quan sát được |

Một span có tên **SELECT orders** không tự động đại diện cho thời gian CPU của máy chủ cơ sở dữ liệu. Span do ứng dụng tạo quanh lệnh gọi JDBC thường đo thời gian trôi qua từ góc nhìn của ứng dụng, bao gồm các yếu tố như gửi yêu cầu, chờ phản hồi, truyền dữ liệu và hành vi buffer của driver. Muốn biết thời gian máy chủ thực thi, cần đối chiếu với log, thống kê truy vấn, session hoặc wait event của hệ quản trị.

Đặt tên metric và span theo đúng phạm vi đo. Nếu đo cả việc lấy kết nối và đọc ResultSet, hãy mô tả đó là thời gian của thao tác DB ở ứng dụng. Nếu chỉ đo lời gọi execute, không đặt tên khiến người đọc hiểu nhầm đó là thời gian toàn bộ truy vấn hoặc thời gian CPU.

## 3. Chọn metrics cho thao tác cơ sở dữ liệu

Một bộ metrics ban đầu có thể gồm:

| Metric | Loại dữ liệu | Mục đích |
|---|---|---|
| Số lần gọi DB | Counter | Theo dõi tần suất thao tác |
| Số lần gọi lỗi | Counter | Theo dõi lỗi và tỷ lệ thất bại |
| Thời lượng thao tác DB | Histogram | Phân tích phân bố thời gian và phân vị |
| Thời gian chờ connection pool | Histogram | Phát hiện pool cạn hoặc kết nối bị giữ lâu |
| Số hàng đọc/trả về | Histogram hoặc counter phù hợp | Nhận diện truy vấn lấy quá nhiều dữ liệu |
| Thời gian giao dịch | Histogram | Tìm transaction kéo dài |
| Kết nối đang hoạt động/rảnh/đang chờ | Gauge hoặc observable gauge | Theo dõi trạng thái pool |
| Timeout hoặc retry | Counter | Nhận diện lỗi do quá hạn và hành vi thử lại |

Không cần tạo mọi metric ngay từ đầu. Hãy chọn các số liệu trả lời câu hỏi vận hành quan trọng và có thể dẫn đến hành động cụ thể. Một histogram thời lượng cùng counter số lần gọi và trạng thái lỗi thường là điểm khởi đầu hữu ích.

### 3.1. Histogram và phân vị

Thời gian truy vấn thường có phân bố lệch: nhiều lần gọi nhanh nhưng một phần nhỏ rất chậm. Trung bình có thể che giấu phần đuôi này. Histogram ghi nhận số lần quan sát rơi vào các khoảng giá trị, từ đó hệ thống giám sát có thể tính hoặc xấp xỉ p50, p95 và p99.

Ví dụ, nếu phần lớn thao tác hoàn tất trong 15 ms nhưng một số request chờ khóa 1.5 giây, p95 hoặc p99 sẽ cho thấy vấn đề rõ hơn trung bình. Chọn bucket phù hợp với mục tiêu và đặc điểm thực tế; nếu tất cả bucket đều quá rộng, phân vị ở vùng quan tâm sẽ kém chính xác. Nếu tạo quá nhiều bucket, chi phí lưu trữ và xử lý tăng.

Với Prometheus, histogram thường được biểu diễn bằng các bucket và có thể tính phân vị từ dữ liệu bucket bằng hàm truy vấn phù hợp. Với hệ thống hỗ trợ histogram native hoặc exponential histogram, cách lưu trữ và truy vấn có thể khác. Hãy dùng khả năng của backend quan sát thay vì giả định mọi hệ thống tính phân vị giống nhau.

Không lấy p95 của từng instance rồi tính trung bình để đại diện p95 toàn hệ thống. Phân vị không có tính cộng gộp như tổng hoặc trung bình. Hãy tổng hợp histogram hoặc dữ liệu phân phối theo cách backend hỗ trợ.

### 3.2. Chọn nhãn có cardinality thấp

Mỗi nhãn hoặc thuộc tính dùng để phân nhóm metric có thể tạo thêm một chuỗi thời gian. Nếu đưa giá trị thay đổi liên tục vào nhãn, số chuỗi có thể tăng rất lớn, làm tốn bộ nhớ và khiến truy vấn giám sát chậm.

Các nhãn thường phù hợp:

- Tên thao tác ổn định như **orders.find_by_id** hoặc **orders.list**.
- Nhóm lệnh như **SELECT**, **INSERT**, **UPDATE**, **DELETE**.
- Tên pool hoặc datasource đã được kiểm soát.
- Tên dịch vụ và vai trò cơ sở dữ liệu.
- Kết quả có số lượng giá trị giới hạn như **success**, **error**, **timeout**.

Tránh dùng các giá trị có cardinality cao hoặc chứa dữ liệu nhạy cảm:

- SQL nguyên văn có literal hoặc tham số.
- ID người dùng, tenant, đơn hàng hoặc session.
- Trace ID, request ID và span ID.
- Tên bảng hoặc câu lệnh được tạo động với vô số biến thể.
- Thông báo lỗi chứa dữ liệu đầu vào.

Nếu cần phân tích theo truy vấn, hãy chuẩn hóa câu SQL thành query fingerprint hoặc operation name ổn định. Việc tạo fingerprint phải giữ được khả năng phân biệt các nhóm thao tác có ý nghĩa, đồng thời loại bỏ literal và dữ liệu nhạy cảm. Chỉ thêm thuộc tính khi có mục tiêu phân tích rõ ràng.

## 4. Instrumentation ở lớp ứng dụng

Instrumentation là việc đặt các điểm đo vào mã ứng dụng hoặc dùng agent/thư viện tự động để thu thập số liệu. Có hai hướng thường gặp:

**Instrumentation tự động** dùng Java agent hoặc thư viện tích hợp để theo dõi HTTP server, JDBC, connection pool và các thành phần phổ biến. Ưu điểm là có thể thu thập nhanh mà ít thay đổi mã nguồn. Tuy nhiên, tên span, thuộc tính và phạm vi đo phụ thuộc agent, phiên bản và cấu hình. Cần kiểm tra span thực tế trước khi xây dashboard.

**Instrumentation thủ công** đặt metric hoặc span tại những ranh giới nghiệp vụ mà agent không hiểu được, ví dụ một thao tác repository gồm nhiều câu lệnh hoặc một transaction quan trọng. Cách này cung cấp ngữ cảnh tốt hơn nhưng cần tránh tạo span trùng với instrumentation tự động.

Một thiết kế thực tế thường kết hợp tự động cho các lớp kỹ thuật và thủ công cho các thao tác nghiệp vụ có ý nghĩa. Trước khi thêm span quanh JDBC, hãy kiểm tra agent đã tạo span cho lời gọi JDBC chưa. Nếu cả hai cùng đo một hoạt động, dashboard có thể đếm hai lần hoặc hiển thị hai khoảng thời gian gần giống nhau.

## 5. Đo thời lượng bằng đồng hồ đơn điệu trong Java

Để đo duration trong một tiến trình Java, dùng **System.nanoTime()** thay vì lấy hiệu hai timestamp lịch bằng **System.currentTimeMillis()**. Đồng hồ đơn điệu phù hợp để tính khoảng thời gian vì không bị thay đổi theo thao tác chỉnh giờ hệ thống. Chỉ lấy hiệu giữa các giá trị nanoTime trong cùng tiến trình; không so sánh trực tiếp giá trị nanoTime giữa các máy.

Ví dụ đơn giản đo toàn bộ thao tác repository:

~~~java
long started = System.nanoTime();
boolean success = false;

try {
    List<Order> orders = orderRepository.findRecentOrders(tenantId);
    success = true;
    return orders;
} finally {
    long elapsedNanos = System.nanoTime() - started;

    double elapsedMillis = elapsedNanos / 1_000_000.0;
    databaseOperationDuration.record(
        elapsedMillis,
        Attributes.of(
            AttributeKey.stringKey("db.operation.name"), "orders.find_recent",
            AttributeKey.stringKey("outcome"), success ? "success" : "error"
        )
    );
}
~~~

Ví dụ này minh họa vị trí đo, không phải toàn bộ cấu hình khởi tạo OpenTelemetry. **databaseOperationDuration** là một Histogram đã được tạo trước bằng Meter API. **Attributes** phải dùng tập giá trị ổn định, có cardinality thấp. Nếu cần phân biệt timeout với lỗi khác, hãy dùng một tập outcome hữu hạn và không đưa message exception vào nhãn.

Khoảng đo trên bao gồm toàn bộ lời gọi repository. Nếu repository lấy kết nối, thực thi SQL, đọc ResultSet và ánh xạ object, tất cả đều nằm trong duration. Đây là chỉ số hữu ích để theo dõi độ trễ mà ứng dụng chịu, nhưng cần thêm span hoặc metric con nếu muốn phân rã từng chặng.

### 5.1. Ví dụ tạo Histogram với OpenTelemetry Metrics API

~~~java
Meter meter = openTelemetry.getMeter("com.example.database");

DoubleHistogram databaseOperationDuration =
    meter.histogramBuilder("app.db.operation.duration")
        .setDescription("Thời lượng thao tác cơ sở dữ liệu đo tại ứng dụng")
        .setUnit("ms")
        .build();
~~~

Tên metric và đơn vị cần thống nhất trong hệ thống. Nếu tổ chức đã có quy ước đặt tên hoặc semantic convention, hãy theo quy ước đó. Không tạo nhiều metric chỉ khác tên nhưng cùng đo một khoảng thời gian.

Metric có thể được ghi trong **finally** để cả lần thành công lẫn thất bại đều được tính. Với lỗi, hãy ghi outcome phù hợp rồi ném lại exception để luồng xử lý hiện tại giữ nguyên hành vi. Không nuốt lỗi chỉ để metric ghi được.

## 6. Tạo span cho lời gọi cơ sở dữ liệu

Trong OpenTelemetry, trace gồm nhiều span có quan hệ với nhau. Một span nên biểu diễn một thao tác có ranh giới rõ ràng, chẳng hạn lời gọi repository hoặc thao tác DB client. Span có thể có:

- Tên mô tả thao tác ổn định.
- Span kind phù hợp, thường là **CLIENT** cho lời gọi tới cơ sở dữ liệu từ ứng dụng.
- Thời điểm bắt đầu và kết thúc.
- Thuộc tính mô tả hệ quản trị, loại thao tác và vai trò.
- Event đánh dấu sự kiện có ý nghĩa.
- Trạng thái thành công hoặc lỗi.
- Quan hệ cha/con với span request hoặc span nghiệp vụ.

Ví dụ minh họa tạo span thủ công quanh một thao tác repository:

~~~java
Tracer tracer = openTelemetry.getTracer("com.example.database");

Span span = tracer.spanBuilder("orders.find_recent")
    .setSpanKind(SpanKind.CLIENT)
    .startSpan();

long started = System.nanoTime();

try (Scope scope = span.makeCurrent()) {
    span.setAttribute("db.system.name", "postgresql");
    span.setAttribute("db.operation.name", "SELECT");

    List<Order> orders = orderRepository.findRecentOrders(tenantId);

    span.setAttribute("app.db.result.count", orders.size());
    span.setStatus(StatusCode.OK);
    return orders;
} catch (RuntimeException error) {
    span.recordException(error);
    span.setStatus(StatusCode.ERROR);
    throw error;
} finally {
    span.end();

    double elapsedMillis =
        (System.nanoTime() - started) / 1_000_000.0;

    databaseOperationDuration.record(
        elapsedMillis,
        Attributes.of(
            AttributeKey.stringKey("db.operation.name"), "orders.find_recent"
        )
    );
}
~~~

Đây là ví dụ về cấu trúc sử dụng OpenTelemetry API. Trong mã sản phẩm, cần cân nhắc việc ghi duration ở cùng một instrumentation layer để không đo trùng với metric tự động. Nếu thao tác repository có thể ném checked exception, hãy điều chỉnh kiểu catch theo chữ ký thực tế. Không nên ghi nội dung exception hoặc câu SQL chứa dữ liệu nhạy cảm vào thuộc tính span.

Nếu đã có JDBC instrumentation tự động, span thủ công nên mô tả thao tác nghiệp vụ ở tầng cao hơn, ví dụ **orders.load_dashboard**, còn span JDBC do agent tạo sẽ mô tả từng lệnh DB. Quan hệ cha/con giúp thấy thao tác nghiệp vụ gồm những câu lệnh nào và mỗi câu lệnh chiếm bao nhiêu thời gian.

### 6.1. Thuộc tính span có ích

Thuộc tính nên giúp trả lời câu hỏi điều tra. Một số thuộc tính thường có giá trị:

| Nhóm | Ví dụ | Mục đích |
|---|---|---|
| Hệ quản trị | **db.system.name** | Phân biệt loại database |
| Thao tác | **db.operation.name** | Phân biệt SELECT/INSERT/UPDATE |
| Vai trò | **db.namespace**, tên datasource đã kiểm soát | Nhận diện database hoặc logical namespace |
| Nghiệp vụ | **app.operation** | Liên kết với chức năng ứng dụng |
| Kết quả | **app.db.result.count** | Hiểu kích thước kết quả |
| Lỗi | **error.type** hoặc status | Phân tích lỗi theo nhóm |
| Máy chủ | **server.address**, **server.port** nếu được phép | Phân biệt endpoint cơ sở dữ liệu |

Tên thuộc tính theo OpenTelemetry Semantic Conventions có thể thay đổi theo phiên bản thư viện. Hãy kiểm tra phiên bản convention mà agent và exporter đang sử dụng để tránh trộn hai cách đặt tên. Với thuộc tính tự định nghĩa, dùng namespace riêng như **app.db.***.

Không đưa mật khẩu, token, giá trị bind parameter, email, thông tin định danh người dùng hoặc SQL đầy đủ vào span. Nếu cần truy vết câu lệnh, ưu tiên query fingerprint hoặc operation name đã chuẩn hóa. Việc thu thập statement text phải tuân theo chính sách bảo mật và dữ liệu của hệ thống.

## 7. Truyền trace context xuyên suốt request

Distributed tracing chỉ hữu ích khi các thành phần nối được span thành cùng một trace. Khi request đi từ gateway sang service, từ service sang repository rồi đến database client, context cần được truyền qua các ranh giới.

Với HTTP, W3C Trace Context định nghĩa các header phổ biến như **traceparent** và **tracestate**. Thư viện tracing thường tự inject context vào request đi và extract context từ request đến. Với message queue hoặc tác vụ nền, context cần được truyền trong metadata của message hoặc cơ chế context propagation tương ứng.

Các điểm cần kiểm tra:

- Request đầu vào có tạo hoặc tiếp nhận trace context đúng cách không?
- HTTP client có inject context khi gọi service khác không?
- Executor hoặc tác vụ bất đồng bộ có truyền context sang thread mới không?
- Consumer có extract context từ message metadata không?
- Span JDBC có nằm dưới span repository và request đúng như dự kiến không?
- Khi retry, mỗi lần thử có được biểu diễn rõ ràng trong trace không?

Một lỗi phổ biến là tạo span trong thread hiện tại nhưng công việc thực tế chạy trong executor khác mà không truyền context. Khi đó, span mới có thể trở thành root trace riêng hoặc mất quan hệ với request ban đầu. Dùng thư viện instrumentation hoặc context propagation chính thức của framework thay vì tự lưu trace ID trong biến toàn cục.

Trace ID dùng để liên kết dữ liệu, không nên đưa vào nhãn metric vì mỗi request thường có ID riêng và làm cardinality tăng rất nhanh. Có thể đưa trace ID và span ID vào structured log để tìm trace liên quan, nếu hệ thống log và chính sách dữ liệu cho phép.

## 8. Thiết kế trace cho một luồng truy cập dữ liệu

Một luồng đơn giản có thể được biểu diễn như sau:

~~~text
HTTP request
└── orders.get_recent                 (span nghiệp vụ)
    ├── authorization.check           (span ứng dụng)
    ├── orders.find_recent             (span repository)
    │   ├── connection.acquire         (span hoặc event nếu cần)
    │   └── SELECT orders              (span DB client)
    └── response.serialize             (span ứng dụng)
~~~

Không nhất thiết phải tạo span cho mọi hàm. Nếu một hàm thực thi trong vài micro giây và không giúp giải thích hành vi, span riêng có thể làm trace quá dày. Ưu tiên các ranh giới I/O, lời gọi dịch vụ, transaction và thao tác có thời gian đáng kể.

Nếu một request gọi cơ sở dữ liệu nhiều lần, trace sẽ cho biết các span diễn ra tuần tự hay song song. Nhiều span DB ngắn nối tiếp nhau có thể cho thấy N+1 hoặc nhiều round trip. Một span DB đơn lẻ dài có thể cần đối chiếu với kế hoạch, wait event và số liệu máy chủ. Một span repository dài nhưng span JDBC ngắn có thể cho thấy thời gian nằm ở xử lý ứng dụng, chờ pool hoặc công việc khác trong repository.

Đừng suy luận thời gian của từng chặng bằng cách trừ hai timestamp đã lấy từ các máy khác nhau nếu đồng hồ chưa được đồng bộ. Dùng duration được ghi ngay trong span của tiến trình tạo span. Với các span lồng nhau, phân tích quan hệ cha/con và thời gian exclusive/inclusive của công cụ tracing.

## 9. Lấy mẫu trace và giữ chi phí quan sát trong giới hạn

Trong hệ thống có nhiều request, lưu toàn bộ trace có thể tốn dung lượng, băng thông và chi phí xử lý. Sampling quyết định trace nào được giữ lại.

**Head sampling** quyết định lấy mẫu từ đầu trace, thường dựa trên xác suất hoặc thuộc tính có sẵn lúc bắt đầu. Cách này kiểm soát chi phí tốt nhưng có thể bỏ qua request trở nên chậm hoặc lỗi ở cuối.

**Tail sampling** đưa ra quyết định sau khi đã quan sát trace, có thể ưu tiên giữ trace lỗi, trace vượt ngưỡng thời gian hoặc trace có thuộc tính quan trọng. Cách này hữu ích cho điều tra độ trễ nhưng cần hạ tầng giữ và xử lý trace trước khi quyết định.

Dù chọn cách nào:

- Giữ một tỷ lệ trace đại diện để hiểu hành vi thông thường.
- Cân nhắc giữ trace lỗi và trace vượt ngưỡng độ trễ nếu chính sách cho phép.
- Đặt sampling nhất quán giữa các service để tránh trace bị đứt đoạn.
- Theo dõi số trace bị loại, số trace được giữ và dung lượng exporter.
- Không dùng trace đã lấy mẫu để tính tổng số lần gọi hoặc p99 chính xác nếu không có hiệu chỉnh phù hợp.

Metrics nên tiếp tục ghi nhận toàn bộ workload theo cấu hình thu thập, kể cả khi tracing chỉ giữ một phần request. Khi cần tìm ví dụ trace từ histogram, một số hệ thống hỗ trợ exemplar liên kết một quan sát metric với trace ID. Đây là cách hữu ích để đi từ chỉ số tổng hợp đến một request cụ thể mà không đưa trace ID vào label metric.

## 10. Kết hợp metrics, traces và số liệu máy chủ cơ sở dữ liệu

Metrics và traces phía ứng dụng cho biết người dùng chờ ở đâu và thao tác DB client kéo dài bao lâu. Chúng không luôn giải thích được máy chủ đã sử dụng CPU, chờ khóa hay đọc dữ liệu trong khoảng đó như thế nào.

Hãy kết hợp với các nguồn phía cơ sở dữ liệu:

- Thống kê theo query fingerprint hoặc nhóm câu lệnh.
- Thời gian elapsed và CPU nếu hệ quản trị cung cấp.
- Wait events, lock wait và trạng thái session.
- Số hàng đọc, số trang truy cập, buffer hit/read và I/O.
- Kế hoạch thực thi cùng ước lượng và số liệu thực tế.
- Thời điểm, transaction hoặc session liên quan.

Khi liên kết, dùng query fingerprint, tên operation, trace ID được truyền qua session nếu hệ quản trị hỗ trợ, connection/session ID và khoảng thời gian. Không phải hệ quản trị nào cũng có khả năng liên kết một span ứng dụng với một câu lệnh máy chủ theo cùng cách. Nếu không có mã tương quan, hãy đối chiếu theo nhóm truy vấn, session và thời điểm với sai số được ghi nhận.

Một số tình huống minh họa:

| Dấu hiệu ở ứng dụng | Bằng chứng phía máy chủ | Hướng điều tra |
|---|---|---|
| Span DB dài, CPU cao | CPU time cao, nhiều hàng xử lý | Kế hoạch, điều kiện lọc, phép nối, dữ liệu đọc |
| Span DB dài, CPU thấp | Lock wait hoặc I/O wait lớn | Giao dịch giữ khóa, working set, I/O |
| Span DB ngắn, repository dài | Máy chủ hoàn tất nhanh | Pool wait, mapping, vòng lặp, công việc ứng dụng |
| Nhiều span DB ngắn trong một request | Nhiều lần gọi cùng fingerprint | N+1, round trip, gom truy vấn |
| p99 tăng nhưng p50 ổn định | Một nhóm session hoặc tham số có wait cao | Phân nhóm trace, tham số đại diện và tranh chấp |
| Số lần gọi tăng bất thường | Thống kê query count tăng | Đường code mới, retry, vòng lặp hoặc cache miss |

## 11. Từ metric đến dashboard và cảnh báo

Dashboard nên giúp người vận hành trả lời nhanh ba câu hỏi: workload nào đang chậm, độ trễ tăng ở chặng nào và thay đổi đó có ảnh hưởng đến người dùng hay không.

Một dashboard cơ bản có thể gồm:

1. Request rate, error rate và p50/p95/p99 của endpoint quan trọng.
2. Số lần gọi DB theo operation name và loại lệnh.
3. Histogram thời lượng DB client theo operation.
4. Thời gian chờ connection pool và số kết nối active/idle/pending.
5. Số hàng trả về hoặc kích thước kết quả theo nhóm thao tác.
6. Tỷ lệ timeout, retry và lỗi DB.
7. Số liệu máy chủ như CPU, I/O, lock wait và active sessions.

Cảnh báo nên dựa trên mục tiêu dịch vụ và mức độ ảnh hưởng, không chỉ dựa vào một giá trị tuyệt đối. Ví dụ, p95 thao tác đọc quan trọng vượt ngưỡng trong nhiều cửa sổ liên tiếp, kết hợp với tỷ lệ request lỗi hoặc timeout tăng. Cần chọn cửa sổ đủ dài để tránh cảnh báo do một đợt dao động ngắn, nhưng đủ ngắn để phát hiện sự cố trước khi người dùng bị ảnh hưởng nghiêm trọng.

Đối với thao tác ít được gọi, phân vị có thể không ổn định vì số mẫu nhỏ. Hãy kết hợp số lượng quan sát với độ trễ, hoặc dùng ngưỡng thời gian và cảnh báo theo lỗi phù hợp. Đừng tạo cảnh báo p99 cho một operation chỉ xuất hiện vài lần mỗi giờ rồi coi đó là thống kê đáng tin cậy.

## 12. Ví dụ: instrument một thao tác tìm đơn hàng

Giả sử endpoint **GET /orders/recent** gọi repository để tìm các đơn hàng mới nhất của một tenant. Mục tiêu là theo dõi độ trễ thao tác DB, số hàng trả về, tỷ lệ lỗi và đường đi của request.

Một thiết kế hợp lý:

- HTTP server instrumentation tạo span cho request.
- Span nghiệp vụ **orders.get_recent** mô tả logic endpoint.
- Span repository **orders.find_recent** bao quanh thao tác dữ liệu.
- JDBC instrumentation tự động tạo span DB client cho câu lệnh thực tế.
- Histogram ghi thời lượng repository và DB client theo operation name ổn định.
- Counter ghi số lần gọi và số lỗi.
- Metric connection pool theo dõi active, idle và pending.
- Structured log chứa trace ID/span ID để liên kết sự kiện ứng dụng với trace.

Trace có thể cho thấy repository thực hiện ba câu SELECT tuần tự. Nếu từng câu lệnh chỉ mất 5 ms nhưng request gọi chúng hàng chục lần, tổng thời gian có thể đáng kể. Sau khi xác định đó là mẫu N+1, nhóm có thể thử truy vấn theo lô. Trước/sau điều chỉnh, hãy so sánh số lần gọi, p95 repository, p95 DB client, số hàng trả về, CPU/I/O máy chủ và tính đúng đắn kết quả.

Nếu trace cho thấy một span DB client dài 600 ms, hãy tìm fingerprint của câu lệnh và đối chiếu với thống kê máy chủ. Nếu máy chủ ghi nhận lock wait 550 ms, hướng điều tra là transaction contention. Nếu máy chủ ghi nhận thời gian ngắn nhưng span DB client vẫn dài, kiểm tra mạng, driver, fetch và việc ứng dụng tiêu thụ kết quả. Nếu span repository dài hơn nhiều so với các span DB con, xem các khoảng xử lý hoặc chờ khác bên trong repository.

Đừng kết luận một thay đổi thành công chỉ vì một trace mẫu nhanh hơn. Dùng metrics để so sánh toàn bộ workload trong cùng điều kiện, kiểm tra phân vị và tỷ lệ lỗi, sau đó dùng trace để giải thích các trường hợp tiêu biểu.

## 13. Quy trình triển khai instrumentation

Khi bổ sung quan sát cho một hệ thống đang chạy, có thể triển khai theo trình tự sau:

1. **Chọn thao tác quan trọng:** ưu tiên endpoint và query ảnh hưởng lớn đến người dùng hoặc tiêu thụ nhiều tài nguyên.
2. **Định nghĩa phạm vi:** xác định mốc bắt đầu/kết thúc của metric và span; ghi rõ có bao gồm pool wait, fetch và mapping hay không.
3. **Kiểm tra instrumentation sẵn có:** xem agent, driver và framework đã tự tạo metric/span nào để tránh đo trùng.
4. **Chọn metric ít nhưng có ích:** histogram duration, counter call/error và metric pool thường là điểm bắt đầu.
5. **Đặt tên và thuộc tính ổn định:** dùng operation name hoặc query fingerprint; giới hạn cardinality.
6. **Bật context propagation:** kiểm tra trace nối qua HTTP, executor, message queue và JDBC.
7. **Kiểm tra dữ liệu thực tế:** mở trace đại diện để xác nhận span cha/con, thuộc tính, trạng thái lỗi và duration.
8. **Thiết lập sampling và lưu trữ:** chọn chính sách phù hợp với lưu lượng và yêu cầu điều tra.
9. **Tạo dashboard/cảnh báo:** theo dõi độ trễ phân vị, lỗi, số lần gọi và trạng thái pool.
10. **So sánh với dữ liệu máy chủ:** liên kết query fingerprint hoặc session để hiểu CPU, wait, I/O và kế hoạch.
11. **Đo chi phí instrumentation:** quan sát CPU ứng dụng, băng thông, exporter queue, dung lượng và độ trễ phát sinh.
12. **Ghi lại quy ước:** mô tả metric, đơn vị, phạm vi đo, thuộc tính và chính sách sampling để các nhóm dùng nhất quán.

Instrumentation cũng có chi phí. Tạo quá nhiều span, ghi thuộc tính lớn hoặc gửi telemetry đồng bộ trong đường request có thể làm tăng CPU, bộ nhớ và độ trễ. Nên dùng exporter/batch processor phù hợp, giới hạn queue, xử lý khi exporter lỗi và tránh để việc gửi telemetry làm gián đoạn chức năng chính.

## 14. Checklist đánh giá chất lượng số liệu

- [ ] Mỗi metric và span có tên mô tả đúng khoảng thời gian được đo.
- [ ] Đơn vị và phạm vi đo nhất quán giữa các instance.
- [ ] Duration được đo bằng đồng hồ đơn điệu trong cùng tiến trình.
- [ ] Histogram có bucket hoặc độ phân giải phù hợp với ngưỡng vận hành.
- [ ] Có thể theo dõi p50, p95, p99 cùng số lượng quan sát.
- [ ] Nhãn metric có cardinality thấp và không chứa ID hoặc dữ liệu nhạy cảm.
- [ ] Trace context được truyền qua các ranh giới đồng bộ và bất đồng bộ.
- [ ] Span DB client được liên kết với span request/repository đúng cách.
- [ ] Không có instrumentation tự động và thủ công đếm trùng cùng thao tác.
- [ ] Trace sampling không bị dùng thay cho thống kê workload đầy đủ.
- [ ] Log có thể liên kết với trace bằng ID khi cần và tuân thủ chính sách dữ liệu.
- [ ] Có thể đối chiếu query fingerprint hoặc session với thống kê máy chủ.
- [ ] Dashboard hiển thị độ trễ, lỗi, tần suất và trạng thái connection pool.
- [ ] Chi phí instrumentation và tình trạng exporter được theo dõi.
- [ ] Một phép thử trước/sau cho thấy số liệu phản ánh đúng thay đổi thực tế.

## 15. Nguyên tắc cần ghi nhớ

Metrics cho biết xu hướng và phân bố của workload; traces cho thấy hành trình của từng request và các thao tác cơ sở dữ liệu nằm bên trong. Khi kết hợp hai nguồn này với query fingerprint, thống kê và wait events từ máy chủ, bạn có thể xác định thao tác nào chậm, chậm ở chặng nào và vì sao.

Một hệ thống quan sát tốt bắt đầu từ định nghĩa phép đo rõ ràng. Hãy chọn histogram và counter phục vụ câu hỏi vận hành, dùng span ở các ranh giới có ý nghĩa, truyền trace context xuyên suốt, kiểm soát cardinality và sampling, đồng thời bảo vệ dữ liệu nhạy cảm. Sau khi instrumentation được xác nhận, dùng metrics để so sánh toàn bộ workload và dùng traces để giải thích các trường hợp cụ thể. Chỉ khi số liệu trước/sau phản ánh cùng một phạm vi và điều kiện, bạn mới có cơ sở tin cậy để quyết định thay đổi tối ưu hiệu năng cơ sở dữ liệu.
