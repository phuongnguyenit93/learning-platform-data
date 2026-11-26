# Đo chi phí ánh xạ, sao chép và nhiều lớp chuyển tiếp

Kiến trúc phân tầng tạo ra các ranh giới giúp mã nguồn có trách nhiệm rõ ràng và dễ thay đổi. Khi dữ liệu đi qua các ranh giới đó, ứng dụng có thể phải ánh xạ DTO, sao chép collection, chuyển đổi kiểu hoặc gọi qua nhiều service và adapter. Những thao tác này có chi phí CPU, cấp phát bộ nhớ và độ trễ. Tuy nhiên, số lớp trong mã nguồn không tự động cho biết ứng dụng chậm đến mức nào.

Muốn quyết định có nên gộp một bước ánh xạ hay loại bỏ một lớp chuyển tiếp, trước hết cần đo trong điều kiện đại diện cho cách ứng dụng chạy thật. Một lần gọi phương thức trong cùng JVM có thể rất rẻ và được JIT compiler inline; một lời gọi qua mạng hoặc database có thể tốn hàng mili giây. Vì vậy, cần phân biệt số bước trong sơ đồ với chi phí thực tế của từng bước.

Trong module **Học tổ chức phần mềm theo kiến trúc phân tầng**, mục tiêu là giữ trách nhiệm giữa Presentation, Application, Domain và Data Access rõ ràng, đồng thời biết cách đánh giá chi phí của các ranh giới đó. Tối ưu có cơ sở bắt đầu bằng số liệu, xác định nút thắt, rồi thay đổi đúng phần gây chi phí mà vẫn giữ được hợp đồng và khả năng kiểm thử.

## 1. Những loại chi phí có thể phát sinh

Khi một request đi qua các tầng, có một số nhóm chi phí thường gặp:

| Nguồn chi phí | Ví dụ | Tác động có thể có |
|---|---|---|
| Ánh xạ dữ liệu (mapping) | Request DTO sang command, entity sang response DTO | CPU để đọc trường, chuyển đổi kiểu, gọi mapper |
| Sao chép dữ liệu (copying) | Tạo list mới, copy object hoặc byte array | Cấp phát bộ nhớ, tăng áp lực garbage collection |
| Chuyển đổi biểu diễn | JSON serialization, parse ngày giờ, format tiền | CPU, bộ nhớ tạm và kích thước dữ liệu |
| Nhiều lớp chuyển tiếp (hops) trong cùng tiến trình | Controller gọi facade, service, handler, repository adapter | Thêm lời gọi, điều phối, có thể thêm object và logic phụ |
| Giao tiếp ngoài tiến trình | HTTP/gRPC, message broker, database | Độ trễ mạng, serialization, connection pool, timeout và retry |
| Truy vấn hoặc tải dữ liệu dư thừa | N+1 query, tải aggregate lớn chỉ để hiển thị vài trường | I/O, CPU database và bộ nhớ |

Không phải mọi mapping đều tạo bản sao hoàn chỉnh. Một mapper có thể tạo object mới nhưng dùng lại một số tham chiếu bất biến; một phép chuyển đổi có thể chỉ đọc vài trường. Ngược lại, việc copy một collection lớn hoặc một mảng byte có thể tốn đáng kể. Cần đo loại thao tác thực tế thay vì gộp mọi việc vào một nhãn “overhead của tầng”.

## 2. Nhiều tầng logic không đồng nghĩa với nhiều lần đi qua mạng

Một ứng dụng Spring Boot có thể chạy controller, application service, domain object và repository adapter trong cùng một JVM. Những thành phần này có thể nằm ở các package hoặc module khác nhau nhưng khi chạy chỉ là lời gọi phương thức trong tiến trình.

~~~mermaid
flowchart TD
    C[Controller]
    A[Application Service]
    D[Domain Model]
    R[Repository Adapter]
    DB[(Database)]
    C -->|method call| A
    A -->|method call| D
    A -->|method call| R
    R -->|SQL / network I/O| DB
~~~

Các lời gọi nội bộ có chi phí nhỏ hơn nhiều so với phần lớn I/O ngoài tiến trình, nhưng không thể mặc định chúng miễn phí. Một chuỗi facade hoặc wrapper có thể thực hiện logging, validation, chuyển đổi object, tra cứu cấu hình hoặc cấp phát thêm dữ liệu. JIT compiler có thể inline một số lời gọi đơn giản khi đủ điều kiện, nhưng không nên dựa vào giả định đó để bỏ qua việc đo.

Cũng cần phân biệt hai kiểu “nhiều lớp chuyển tiếp”:

- **Chuyển tiếp trong cùng tiến trình:** một method gọi method khác, có thể có thêm mapping hoặc điều phối.
- **Chuyển tiếp qua ranh giới triển khai:** một service gọi HTTP service khác, database hoặc broker. Chi phí thường bao gồm mạng, serialization, scheduling và khả năng lỗi.

Tách package hoặc module để bảo vệ hướng phụ thuộc thường không tạo thêm network hop. Ngược lại, chuyển một module thành microservice có thể biến một lời gọi hàm thành lời gọi mạng và làm thay đổi đáng kể đặc tính hiệu năng, độ tin cậy.

## 3. Đo ở cấp request trước khi tối ưu một dòng code

Hãy bắt đầu từ một luồng nghiệp vụ cụ thể, ví dụ GET /api/orders/{id} hoặc POST /api/orders. Xác định thời gian người dùng quan tâm và các phần chính của luồng:

1. Nhận request và parse payload.
2. Validation và chuyển request DTO thành command/query.
3. Thực thi Application và Domain.
4. Truy vấn hoặc ghi dữ liệu qua repository.
5. Chuyển kết quả thành response DTO.
6. Serialize và gửi response.

Đo thời gian tổng thể và từng đoạn quan trọng để biết chi phí tập trung ở đâu. Một endpoint mất 180 ms không có nghĩa 30 ms mapping là nguyên nhân chính nếu database chiếm 150 ms. Tối ưu mapping khi truy vấn đang chiếm gần hết thời gian có thể không tạo ra cải thiện đáng kể.

Các chỉ số hữu ích:

- **Latency:** thời gian hoàn thành một request; xem median, p95 và p99 để nhận ra đuôi phân phối.
- **Throughput:** số request hoàn thành mỗi giây trong điều kiện tải xác định.
- **CPU time:** lượng thời gian CPU thực sự dùng cho xử lý.
- **Allocation rate:** lượng bộ nhớ được cấp phát theo thời gian hoặc trên mỗi request.
- **GC activity:** tần suất và thời gian garbage collection.
- **Payload size:** kích thước request/response và dữ liệu truyền giữa các thành phần.
- **Database/network time:** thời gian chờ I/O, số query, số lần gọi dịch vụ ngoài.

Không chỉ nhìn trung bình. Một phép mapping có thể rất nhanh ở payload nhỏ nhưng gây áp lực bộ nhớ khi xử lý danh sách hàng chục nghìn phần tử. p95/p99 và allocation rate có thể bộc lộ vấn đề mà thời gian trung bình che khuất.

## 4. Dùng tracing để tìm bước chuyển tiếp tốn thời gian

Distributed tracing cho phép quan sát một request qua nhiều span. Trong ứng dụng Spring, Micrometer Observation và OpenTelemetry có thể giúp thu thập trace; các thư viện instrumented có thể tự tạo span cho HTTP client, database hoặc message broker.

Một trace đơn giản có thể cho thấy:

~~~text
POST /api/orders                         240 ms
  parse + validation                      4 ms
  map request -> command                  1 ms
  PlaceOrderUseCase                      18 ms
    load product                          9 ms
    domain calculation                    1 ms
    save order                            11 ms
  map result -> response                  1 ms
  JSON serialization                      2 ms
  other / scheduling / network            ...
~~~

Số liệu trên chỉ minh họa cách đọc trace, không phải chuẩn thời gian. Khi phân tích trace thực:

- Tìm span chiếm thời gian lớn và span lặp lại nhiều lần.
- Kiểm tra một request có gọi cùng repository hoặc API nhiều lần không.
- Tìm N+1 query, retry không cần thiết hoặc lời gọi tuần tự có thể phối hợp.
- So sánh thời gian chờ I/O với thời gian CPU.
- Dùng trace ID để nối log và metrics mà không ghi dữ liệu nhạy cảm vào span.

Tracing có overhead và sampling có thể bỏ qua một số request. Khi đo latency rất nhỏ, không nên kết luận chi phí của một mapper 20 microsecond chỉ từ trace được instrument nặng. Tracing phù hợp để tìm nút thắt ở cấp luồng; profiling và microbenchmark phù hợp hơn khi cần phân tích một đoạn code rất nhỏ.

## 5. Dùng profiler để đo CPU và cấp phát bộ nhớ

Java Flight Recorder (JFR) có thể thu thập sự kiện về CPU sampling, allocation, garbage collection, lock và I/O trong một phiên chạy ứng dụng. Các profiler như async-profiler cũng có thể tạo flame graph để thấy phương thức nào tiêu thụ CPU hoặc cấp phát nhiều object.

Khi profiling:

- Dùng dữ liệu và tải gần với production, bao gồm kích thước danh sách và phân bố request.
- Chạy đủ lâu để JIT warm-up và workload ổn định.
- Kiểm tra cả CPU profile và allocation profile; một phương thức có thể không tốn CPU nhiều nhưng cấp phát object liên tục.
- Phân biệt allocation trong code của ứng dụng với allocation do JSON, ORM hoặc thư viện.
- So sánh trước và sau bằng cùng môi trường, cùng dữ liệu và cùng kịch bản tải.

Một flame graph cho thấy phương thức mapper xuất hiện rộng không tự động chứng minh mapper cần bị xóa. Nó cho thấy phương thức đó tiêu thụ một phần CPU trong workload đã đo. Hãy kiểm tra số lần gọi, kích thước dữ liệu và khả năng giảm công việc mà vẫn giữ đúng hợp đồng.

## 6. Microbenchmark mapping đúng cách với JMH

Nếu cần so sánh hai cách ánh xạ, ví dụ mapper thủ công và mapper sinh mã, có thể dùng JMH. Không nên đo bằng cách gọi một vòng lặp trong main rồi lấy thời gian đồng hồ, vì JIT, dead-code elimination, warm-up, GC và các yếu tố của JVM có thể làm kết quả sai lệch.

Ví dụ benchmark tối giản:

~~~java
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class OrderMappingBenchmark {

    private OrderEntity source;
    private OrderMapper mapper;

    @Setup
    public void setup() {
        source = TestData.largeOrderEntity();
        mapper = new OrderMapperImpl();
    }

    @Benchmark
    public OrderResponse mapWithMapper() {
        return mapper.toResponse(source);
    }

    @Benchmark
    public OrderResponse mapManually() {
        return new OrderResponse(
                source.getId(),
                source.getCustomerName(),
                source.getLines().stream()
                        .map(line -> new OrderLineResponse(
                                line.getProductId(),
                                line.getQuantity(),
                                line.getUnitPrice()
                        ))
                        .toList()
        );
    }
}
~~~

Đây là khung minh họa; lớp dữ liệu, mapper và cách build JMH cần được định nghĩa trong dự án. Khi chạy benchmark, cần:

- Có warm-up iterations để JVM đạt trạng thái tối ưu tương đối ổn định.
- Chạy nhiều measurement iterations và nhiều fork JVM để giảm ảnh hưởng trạng thái tiến trình.
- Trả kết quả hoặc dùng Blackhole để tránh compiler loại bỏ công việc không có tác dụng.
- Dùng dữ liệu đại diện: object nhỏ, object lớn, collection rỗng và collection nhiều phần tử.
- Dùng profiler của JMH như GC profiler khi cần so sánh allocation.
- So sánh cùng phiên bản Java, cùng phần cứng và cùng cấu hình JVM.

JMH đo một đoạn code cô lập. Kết quả không trực tiếp cho biết endpoint production nhanh hơn bao nhiêu, vì endpoint còn có framework, serialization, database, mạng và tải đồng thời. Hãy dùng benchmark để lựa chọn implementation cho một thao tác cụ thể, rồi xác nhận bằng load test hoặc profiling ở cấp ứng dụng.

## 7. Đo mapping, copying và allocation riêng biệt

Để hiểu chi phí, cần xác định chính xác mapper đang làm gì:

- Tạo một response object mới hay tạo cả cây object lồng nhau?
- Có copy toàn bộ list hay chỉ tạo view/stream?
- Có chuyển đổi ngày giờ, tiền tệ hoặc enum không?
- Có tải quan hệ lazy từ ORM trong lúc mapping không?
- Có serialize JSON ngay trong mapper hay ở tầng web?
- Có tạo collection trung gian qua nhiều lần stream/map/toList không?

Ví dụ, mapping một danh sách đơn hàng sang response:

~~~java
List<OrderResponse> responses = orders.stream()
        .map(orderMapper::toResponse)
        .toList();
~~~

Đoạn code này tạo danh sách kết quả và thường tạo response object cho từng phần tử. Nếu mỗi response chứa danh sách dòng hàng, số object cấp phát có thể tăng theo tổng số dòng. Nếu mapper truy cập lazy relationship, việc chuyển đổi có thể vô tình kích hoạt nhiều query. Vì vậy, profiler và SQL trace nên được xem cùng nhau.

Có thể tối ưu bằng cách truy vấn projection chỉ chứa trường cần hiển thị, tránh tải entity graph không cần thiết. Tuy nhiên, không nên chuyển truy vấn phức tạp vào controller; hãy giữ query ở Application port và Infrastructure adapter.

Đôi khi có thể tránh copy bằng cách dùng collection bất biến hoặc chia sẻ tham chiếu an toàn. Nhưng nếu dữ liệu có thể bị thay đổi sau khi chia sẻ, tránh copy có thể tạo lỗi aliasing và race condition. Hiệu năng không phải lý do để bỏ qua quyền sở hữu và tính bất biến của dữ liệu.

## 8. Đo chi phí của nhiều lớp chuyển tiếp

Một chuỗi gọi nội bộ có thể trông như sau:

~~~text
Controller
  -> Facade
    -> Application Service
      -> Command Handler
        -> Domain Service
          -> Repository Port
            -> JPA Adapter
              -> Spring Data Repository
                -> Database
~~~

Không phải mọi mắt xích đều thừa. Mỗi thành phần có thể đại diện cho một ranh giới thực: chuyển giao thức, điều phối use case, bảo vệ quy tắc, abstraction lưu trữ hoặc adapter công nghệ. Nhưng nếu nhiều lớp chỉ chuyển nguyên tham số và kết quả, không thêm quy tắc, kiểm soát giao dịch, bảo vệ phụ thuộc hay khả năng kiểm thử, chúng có thể tạo độ phức tạp mà không mang lợi ích.

Đánh giá từng hop bằng câu hỏi:

1. Nó có thực hiện trách nhiệm riêng và có lý do tồn tại không?
2. Nó có tạo object mới, copy collection hoặc chuyển đổi dữ liệu không?
3. Nó có thực hiện I/O, lock, validation hoặc tra cứu bổ sung không?
4. Nó có được gọi một lần hay lặp lại trong vòng lặp?
5. Có thể gộp mà không phá vỡ ranh giới sở hữu, dependency direction hoặc khả năng kiểm thử không?

Đừng gộp hai tầng chỉ để giảm một lời gọi method nếu tầng đó bảo vệ một hợp đồng quan trọng. Ngược lại, nếu một facade chỉ chuyển tiếp duy nhất một phương thức và không có lý do kiến trúc, có thể cân nhắc bỏ nó sau khi kiểm tra callers và ranh giới module.

## 9. Tối ưu mà vẫn giữ hợp đồng và trách nhiệm

Một số lựa chọn thường có hiệu quả:

| Vấn đề đã đo được | Hướng xử lý có thể thử | Điều cần giữ |
|---|---|---|
| Mapping tạo quá nhiều object | Giảm trường không cần thiết, dùng projection, tránh mapping nhiều lần | DTO vẫn rõ nghĩa và không làm lộ entity |
| Copy collection lớn | Phân trang, streaming có kiểm soát hoặc xử lý theo batch | Không chia sẻ dữ liệu mutable thiếu an toàn |
| Reflection mapper tốn CPU | So sánh mapper sinh mã như MapStruct hoặc mapping thủ công | Không hy sinh readability nếu chênh lệch không đáng kể |
| N+1 query khi mapping | Fetch đúng dữ liệu, projection hoặc batch fetching | Truy vấn nằm trong adapter/query port |
| Nhiều hop nội bộ chỉ chuyển tiếp | Loại bỏ lớp không có trách nhiệm độc lập | Giữ ranh giới có ý nghĩa và test phù hợp |
| Nhiều network hop | Giảm round trip, gộp request hoặc thay đổi giao tiếp nếu phù hợp | Cân nhắc timeout, retry, coupling và failure isolation |

MapStruct thường sinh mã Java ở thời điểm biên dịch, tránh một số chi phí reflection runtime của mapper động. Tuy nhiên, nó không làm biến mất chi phí tạo object, chuyển đổi collection hoặc gọi getter có thể kích hoạt lazy loading. Hãy benchmark với dữ liệu thật và xem allocation profile trước khi chọn.

Projection có thể giảm lượng dữ liệu đọc và số object được dựng. Nhưng projection gắn với truy vấn cụ thể, nên cần được đặt trong hợp đồng query phù hợp thay vì dùng làm mô hình miền chung.

## 10. Ví dụ đo trong ứng dụng Spring

Có thể kết hợp ba mức quan sát:

**Ở cấp endpoint:** dùng Micrometer metrics để theo dõi thời gian và throughput của request theo route hoặc operation. Tránh gắn ID người dùng, orderId hoặc giá trị không giới hạn vào metric tag vì cardinality cao làm hệ thống metrics tốn tài nguyên.

**Ở cấp luồng:** dùng tracing để đo các span như application use case, repository query và HTTP client. Span cần tên ổn định và thuộc tính đủ để tìm nguyên nhân, nhưng không chứa dữ liệu nhạy cảm.

**Ở cấp code:** dùng JFR hoặc async-profiler để tìm CPU hot spot và allocation. Nếu cần so sánh mapper cụ thể, dùng JMH với warm-up và workload đại diện.

Một kế hoạch đo có thể gồm:

1. Ghi baseline của p50, p95, p99, throughput, CPU, allocation và GC.
2. Chọn một endpoint có vấn đề và thu trace của các request đại diện.
3. Profile để xác định method hoặc nhóm thao tác gây CPU/allocation.
4. Đưa ra một thay đổi nhỏ có giả thuyết rõ ràng, ví dụ giảm một lần mapping collection.
5. Chạy lại cùng kịch bản và so sánh số liệu.
6. Chạy test chức năng và kiểm tra tính đúng đắn của hợp đồng sau tối ưu.

Không nên đo trong production bằng cách bật mọi profiler với cấu hình nặng mà không đánh giá overhead. JFR có thể dùng với cấu hình phù hợp, tracing nên sampling theo nhu cầu, và benchmark chi tiết nên chạy trong môi trường kiểm soát. Mục tiêu là có đủ bằng chứng mà không làm thay đổi đáng kể workload đang quan sát.

## 11. Cân bằng hiệu năng với khả năng bảo trì

Một số mapping và lớp chuyển tiếp tồn tại để bảo vệ tính độc lập giữa các tầng. Ví dụ, Presentation DTO tách khỏi Domain entity giúp API thay đổi tên trường mà không buộc mô hình nghiệp vụ thay đổi. Application port giúp đổi adapter lưu trữ mà không lan framework vào use case. Những ranh giới này có giá trị dù có thêm một ít công việc chuyển đổi.

Ngược lại, abstraction không có ý nghĩa có thể làm người đọc phải đi qua nhiều file chỉ để hiểu một hành động đơn giản. Quyết định giữ hay bỏ một lớp nên xét cả chi phí runtime và chi phí nhận thức, kiểm thử, thay đổi.

Có thể áp dụng nguyên tắc:

- Giữ ranh giới khi nó bảo vệ ngữ nghĩa, quyền sở hữu hoặc hướng phụ thuộc.
- Đơn giản hóa mapping khi dữ liệu được chuyển đổi lặp lại mà không mang thêm ý nghĩa.
- Dùng projection hoặc pagination khi tải dư thừa là nguyên nhân đo được.
- Gộp lớp chuyển tiếp khi nó không có trách nhiệm riêng và việc gộp không làm đảo dependency direction.
- Tránh chuyển một lời gọi nội bộ thành network hop nếu không có lý do triển khai rõ ràng.

## 12. Checklist đánh giá chi phí

Trước khi thay đổi kiến trúc để tối ưu, hãy tự hỏi:

1. Vấn đề nằm ở CPU, allocation, GC, database, network hay scheduling?
2. Số liệu p95/p99 và throughput cho thấy đoạn nào đáng chú ý?
3. Mapping có tạo object hoặc copy dữ liệu lớn không?
4. Mapping có kích hoạt lazy query hoặc serialization không cần thiết không?
5. Các hop là method call nội bộ hay network call?
6. Lớp trung gian có trách nhiệm độc lập hay chỉ chuyển tiếp?
7. Có thể thử projection, pagination, batch hoặc generated mapper không?
8. Thay đổi có giữ hợp đồng, hướng phụ thuộc và tính đúng đắn của dữ liệu không?
9. Có benchmark/profiling trước và sau trong cùng điều kiện không?
10. Test chức năng và tải có xác nhận cải thiện không làm hỏng hành vi không?

Đo chi phí ánh xạ, sao chép và nhiều lớp chuyển tiếp giúp nhóm nhận ra phần nào thực sự ảnh hưởng đến hiệu năng. Kiến trúc phân tầng không yêu cầu tối thiểu hóa số lớp bằng mọi giá; nó yêu cầu mỗi ranh giới có lý do rõ ràng. Khi số liệu chỉ ra một bước đang gây chi phí đáng kể, hãy tối ưu bước đó và xác minh lại bằng cùng phương pháp đo, đồng thời giữ những hợp đồng cần thiết để hệ thống dễ hiểu và thay đổi.

