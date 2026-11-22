# Phối hợp tốc độ đọc, xử lý và ghi bằng áp lực ngược

## 1. Vấn đề khi xử lý dữ liệu JSON quy mô lớn

Một pipeline xử lý JSON thường có ba công đoạn:

1. **Đọc (read):** lấy byte từ file, socket hoặc HTTP request; parser chuyển nội dung thành token hoặc bản ghi.
2. **Xử lý (process):** kiểm tra, chuyển đổi, lọc, bổ sung hoặc tính toán trên từng bản ghi.
3. **Ghi (write):** serialize kết quả thành JSON rồi chuyển đến file, socket, database hoặc dịch vụ khác.

Ba công đoạn này hiếm khi có cùng tốc độ. Parser có thể đọc nhanh hơn nhiều so với một bước xử lý cần truy vấn dữ liệu; hoặc xử lý xong nhanh nhưng ổ đĩa đích ghi chậm. Nếu cứ đọc liên tục rồi xếp mọi bản ghi vào bộ nhớ để chờ, ứng dụng có thể dùng hết RAM dù bản thân từng bản ghi nhỏ.

**Áp lực ngược (backpressure)** là cơ chế khiến công đoạn phía trước giảm hoặc tạm dừng việc tạo dữ liệu khi công đoạn phía sau chưa thể tiếp nhận thêm. Nhờ đó, tốc độ đọc, xử lý và ghi được phối hợp theo khả năng thực tế của toàn pipeline.

Trong Jackson, điều này đặc biệt quan trọng khi dùng Streaming API. JsonParser đọc JSON theo kiểu pull: ứng dụng chủ động yêu cầu token kế tiếp. JsonGenerator ghi token ra đích theo thứ tự. Nếu tổ chức vòng lặp hợp lý, ứng dụng có thể chỉ giữ một bản ghi hoặc một lượng dữ liệu giới hạn trong bộ nhớ.

## 2. Tốc độ của từng công đoạn và điểm nghẽn

Gọi:

- R là tốc độ đọc, tính bằng bản ghi/giây.
- P là tốc độ xử lý, tính bằng bản ghi/giây.
- W là tốc độ ghi, tính bằng bản ghi/giây.

Trong một pipeline tuần tự, throughput dài hạn không thể vượt quá công đoạn chậm nhất:

    T = min(R, P, W)

Ví dụ:

| Công đoạn | Khả năng xử lý |
|---|---:|
| Đọc JSON | 25.000 bản ghi/giây |
| Xử lý nghiệp vụ | 4.000 bản ghi/giây |
| Ghi kết quả | 3.000 bản ghi/giây |

Throughput tối đa của pipeline xấp xỉ 3.000 bản ghi/giây. Đọc nhanh hơn không làm kết quả được ghi nhanh hơn; nó chỉ tạo thêm dữ liệu đang chờ.

Nếu pipeline có hàng đợi giữa các công đoạn, gọi Q(t) là số phần tử đang chờ tại thời điểm t. Khi tốc độ đến lớn hơn tốc độ phục vụ:

    dQ/dt ≈ R_in - R_out > 0

Hàng đợi sẽ tăng dần. Nếu hàng đợi không có giới hạn, lượng bộ nhớ sử dụng có thể tăng đến khi tiến trình bị hệ điều hành dừng hoặc phát sinh OutOfMemoryError. Nếu hàng đợi có giới hạn, khi đầy nó có thể chặn producer, từ chối thêm dữ liệu hoặc kích hoạt một chính sách điều tiết khác. Đây là điểm backpressure xuất hiện.

## 3. Jackson Streaming API tạo backpressure tự nhiên như thế nào?

JsonParser là parser kiểu pull. Ứng dụng gọi nextToken() để yêu cầu token tiếp theo. Parser không cần đọc và dựng toàn bộ tài liệu JSON thành một cây trước khi chương trình bắt đầu xử lý.

Một vòng lặp có thứ tự:

    while (parser.nextToken() != JsonToken.END_ARRAY) {
        JsonNode record = mapper.readTree(parser);
        JsonNode result = process(record);
        mapper.writeTree(generator, result);
    }

Vòng lặp chỉ yêu cầu bản ghi tiếp theo sau khi bản ghi hiện tại đã được đọc, xử lý và ghi. Nếu process(...) chậm, parser không gọi nextToken() trong thời gian đó. Nếu thao tác ghi bị chậm hoặc OutputStream bị chặn, vòng lặp cũng chưa thể quay lại bước đọc tiếp theo.

Đây là backpressure đồng bộ: tốc độ của toàn vòng lặp bị giới hạn bởi công đoạn chậm nhất. Không cần một hàng đợi riêng, không cần đồng bộ giữa nhiều thread và bộ nhớ cho mỗi bản ghi được giải phóng trước khi đọc bản ghi kế tiếp.

### Sơ đồ xử lý đồng bộ

    Nguồn JSON
        |
        v
    JsonParser.nextToken()
        |
        v
    Đọc một bản ghi
        |
        v
    Xử lý bản ghi
        |
        v
    JsonGenerator ghi kết quả
        |
        +---- quay lại đọc bản ghi tiếp theo

Nếu bước ghi chậm, luồng điều khiển dừng ở bước ghi. Parser chưa được yêu cầu đọc thêm nên dữ liệu không tiếp tục dồn vào bộ nhớ ứng dụng.

## 4. Ví dụ: chuyển đổi một mảng JSON lớn theo kiểu streaming

Giả sử đầu vào là một JSON array chứa hàng triệu object:

    [
      {"id": 1, "name": "Lan"},
      {"id": 2, "name": "Minh"},
      {"id": 3, "name": "An"}
    ]

Không nên gọi readTree(input) cho toàn bộ tài liệu nếu mục tiêu là xử lý từng bản ghi với bộ nhớ giới hạn. Có thể đọc từng phần tử rồi ghi từng phần tử ra output:

    import com.fasterxml.jackson.core.JsonGenerator;
    import com.fasterxml.jackson.core.JsonParser;
    import com.fasterxml.jackson.core.JsonToken;
    import com.fasterxml.jackson.databind.JsonNode;
    import com.fasterxml.jackson.databind.ObjectMapper;
    import com.fasterxml.jackson.databind.node.ObjectNode;

    import java.io.InputStream;
    import java.io.OutputStream;
    import java.nio.file.Files;
    import java.nio.file.Path;

    public class StreamingTransform {
        public static void main(String[] args) throws Exception {
            ObjectMapper mapper = new ObjectMapper();

            try (InputStream input = Files.newInputStream(Path.of("input.json"));
                 OutputStream output = Files.newOutputStream(Path.of("output.json"));
                 JsonParser parser = mapper.getFactory().createParser(input);
                 JsonGenerator generator = mapper.getFactory().createGenerator(output)) {

                if (parser.nextToken() != JsonToken.START_ARRAY) {
                    throw new IllegalArgumentException("Expected a JSON array");
                }

                generator.writeStartArray();

                while (parser.nextToken() != JsonToken.END_ARRAY) {
                    JsonNode record = mapper.readTree(parser);
                    if (record == null || !record.isObject()) {
                        throw new IllegalArgumentException(
                                "Every array item must be a JSON object"
                        );
                    }

                    ObjectNode result = ((ObjectNode) record).deepCopy();
                    result.put("processed", true);

                    // Ghi xong bản ghi hiện tại rồi mới yêu cầu bản ghi tiếp theo.
                    mapper.writeTree(generator, result);
                }

                generator.writeEndArray();
            }
        }
    }

Ví dụ giữ tối đa một cây bản ghi đang được xử lý trong mã ứng dụng. Bộ nhớ vẫn cần cho buffer nội bộ của parser/generator và cho chính bản ghi hiện tại, nhưng không tăng theo tổng số phần tử trong array. Nếu một object riêng lẻ rất lớn, kích thước của object đó vẫn là yếu tố cần quản lý.

mapper.readTree(parser) bắt đầu tại token hiện tại và đọc node JSON tương ứng. Với input là array object, vòng lặp lấy token bắt đầu của phần tử kế tiếp rồi đọc trọn node đó. Khi xử lý và ghi hoàn tất, lần gọi parser.nextToken() tiếp theo mới lấy phần tử kế.

Ví dụ giả định mỗi phần tử array là object. Nếu schema cho phép string, number, boolean hoặc null ở cấp phần tử, cần thay kiểm tra isObject() bằng logic xử lý từng kiểu JSON.

## 5. Khi nào cần hàng đợi giữa các công đoạn?

Xử lý đồng bộ đơn giản và tiết kiệm bộ nhớ, nhưng có thể không tận dụng được nhiều lõi CPU nếu bước xử lý độc lập và nặng CPU. Khi muốn tách đọc, xử lý và ghi thành các thread khác nhau, thường đặt một hàng đợi giữa producer và consumer:

    Producer đọc JSON
          |
          v
    Hàng đợi có giới hạn
          |
          v
    Worker xử lý
          |
          v
    Hàng đợi kết quả có giới hạn
          |
          v
    Consumer ghi JSON

Hàng đợi phải có dung lượng hữu hạn. Nếu dùng hàng đợi không giới hạn, producer vẫn có thể đọc nhanh hơn consumer và tích lũy vô hạn bản ghi. Backpressure chỉ có tác dụng khi có một giới hạn thực sự và khi trạng thái đầy được truyền ngược về phía producer.

Với Java, ArrayBlockingQueue hoặc LinkedBlockingQueue có capacity hữu hạn có thể dùng làm buffer. queue.put(item) sẽ chờ nếu queue đã đầy; queue.take() sẽ chờ nếu queue đang rỗng.

## 6. Ví dụ producer-consumer với hàng đợi có giới hạn

Đoạn mã sau minh họa phần phối hợp giữa producer và consumer. Producer chỉ đọc tiếp sau khi đã đưa bản ghi hiện tại vào queue. Khi queue đầy, put chặn producer; consumer lấy bớt phần tử và giải phóng chỗ trống.

    import com.fasterxml.jackson.core.JsonParser;
    import com.fasterxml.jackson.core.JsonToken;
    import com.fasterxml.jackson.databind.JsonNode;
    import com.fasterxml.jackson.databind.ObjectMapper;

    import java.io.IOException;
    import java.util.concurrent.ArrayBlockingQueue;
    import java.util.concurrent.BlockingQueue;

    public class BoundedQueuePattern {
        private static final int CAPACITY = 64;

        public static void main(String[] args) throws Exception {
            ObjectMapper mapper = new ObjectMapper();
            BlockingQueue<JsonNode> queue = new ArrayBlockingQueue<>(CAPACITY);

            // Producer: chạy ở thread đọc.
            Thread producer = new Thread(() -> {
                try (JsonParser parser = mapper.getFactory()
                        .createParser("input.json")) {
                    if (parser.nextToken() != JsonToken.START_ARRAY) {
                        throw new IOException("Expected a JSON array");
                    }

                    while (parser.nextToken() != JsonToken.END_ARRAY) {
                        JsonNode item = mapper.readTree(parser);
                        queue.put(item); // Queue đầy thì producer phải chờ.
                    }
                } catch (Exception error) {
                    throw new RuntimeException(error);
                }
            });

            // Consumer: chạy ở thread xử lý/ghi.
            Thread consumer = new Thread(() -> {
                try {
                    while (true) {
                        JsonNode item = queue.take(); // Queue rỗng thì chờ.
                        processAndWrite(item);
                    }
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            });

            producer.start();
            consumer.start();
        }

        private static void processAndWrite(JsonNode item) {
            // Thay bằng xử lý và ghi kết quả thực tế.
        }
    }

Đây là đoạn minh họa cơ chế chặn của queue, chưa phải một chương trình hoàn chỉnh để quản lý vòng đời pipeline: một triển khai thực tế cần thông báo kết thúc, truyền lỗi producer sang consumer, chờ cả hai thread hoàn tất và đóng parser/generator đúng lúc. Không nên dùng vòng lặp consumer vô hạn như ví dụ nếu không có giao thức kết thúc.

### Sentinel báo kết thúc

Một cách phổ biến là dùng một thông điệp kết thúc (sentinel) có kiểu riêng. Ví dụ, thay vì queue trực tiếp JsonNode, định nghĩa một wrapper:

    record WorkItem(JsonNode value, boolean end) {
        static WorkItem data(JsonNode value) {
            return new WorkItem(value, false);
        }

        static WorkItem endMarker() {
            return new WorkItem(null, true);
        }
    }

Producer đưa WorkItem.endMarker() vào queue sau khi đọc xong. Consumer thoát vòng lặp khi nhận marker. Vì queue không nhận Java null, wrapper này cũng cho phép phân biệt một bản ghi JSON null hợp lệ với thông điệp kết thúc.

Nếu có nhiều consumer, cần một marker cho mỗi consumer hoặc một cơ chế điều phối kết thúc tương đương. Nếu producer gặp lỗi, nó vẫn phải thông báo lỗi và đánh thức consumer; nếu không, consumer có thể chờ vô hạn.

## 7. Vì sao queue phải có giới hạn?

Giả sử mỗi bản ghi sau khi parse chiếm trung bình 8 KB và queue giữ 10.000 bản ghi. Riêng dữ liệu trong queue đã xấp xỉ:

    8 KB × 10.000 ≈ 80 MB

Con số thực tế có thể lớn hơn do object header, reference, cấu trúc node, chuỗi và overhead của collection. Nếu queue không giới hạn và tốc độ đọc vượt tốc độ ghi trong thời gian dài, mức sử dụng heap sẽ tiếp tục tăng.

Với queue capacity C và kích thước trung bình S, bộ nhớ dữ liệu đang chờ có thể ước lượng sơ bộ:

    M_queue ≈ C × S

Đây chỉ là ước lượng. JSON record có kích thước thay đổi đáng kể; một queue 100 phần tử có thể chứa 100 object nhỏ hoặc 100 object nhiều megabyte. Với dữ liệu biến thiên lớn, giới hạn theo số lượng phần tử chưa đủ để bảo đảm giới hạn byte.

Các lựa chọn để kiểm soát bộ nhớ:

- Giới hạn số bản ghi trong queue.
- Giới hạn kích thước request hoặc record ở tầng đầu vào.
- Dùng semaphore hoặc bộ đếm byte để giới hạn tổng kích thước dữ liệu đang chờ.
- Không giữ đồng thời cả chuỗi JSON gốc, cây node và bản serialize mới nếu không cần thiết.
- Giải phóng tham chiếu tới bản ghi sau khi ghi xong.

## 8. Chọn capacity và kích thước batch

Queue quá nhỏ có thể làm producer và consumer liên tục chặn/đánh thức, giảm khả năng tận dụng CPU. Queue quá lớn lại tăng bộ nhớ và làm độ trễ khi dữ liệu nằm chờ cao hơn.

Một cách bắt đầu là đo:

- thời gian trung bình và percentile của bước parse;
- thời gian xử lý mỗi record;
- thời gian ghi mỗi record hoặc mỗi batch;
- số phần tử chờ trung bình và cực đại;
- heap usage và garbage collection.

Sau đó chọn capacity vừa đủ hấp thụ dao động ngắn hạn. Queue nên làm bộ đệm, không nên trở thành nơi lưu backlog dài hạn. Nếu queue liên tục đầy, đó là dấu hiệu consumer không theo kịp hoặc downstream đang chậm; tăng capacity chỉ trì hoãn thời điểm đầy và tăng bộ nhớ.

Nếu ghi theo batch, cần cân bằng:

- Batch lớn giảm số lần gọi I/O và có thể tăng throughput.
- Batch lớn tăng bộ nhớ tạm và thời gian chờ trước khi dữ liệu được flush.
- Batch nhỏ giảm độ trễ nhưng có thể tạo nhiều thao tác I/O nhỏ.

Batch cũng cần giới hạn theo byte hoặc thời gian, không chỉ theo số record, khi kích thước record không đồng đều.

## 9. Các cách truyền áp lực ngược

Backpressure có thể được thực hiện theo nhiều cách, tùy kiến trúc:

| Cơ chế | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Đồng bộ theo vòng lặp | Chỉ đọc phần tiếp theo sau khi xử lý và ghi xong phần hiện tại | Pipeline đơn giản, bộ nhớ thấp, xử lý không cần song song |
| Blocking queue hữu hạn | Producer bị chặn khi queue đầy | Producer/consumer chạy ở các thread khác nhau |
| Demand/request-N | Consumer thông báo số phần tử sẵn sàng nhận; producer chỉ phát trong giới hạn demand | Reactive Streams hoặc pipeline bất đồng bộ |
| Pause/resume | Tạm dừng nguồn đọc khi buffer vượt ngưỡng, tiếp tục khi queue giảm | Nguồn hỗ trợ điều khiển flow như socket hoặc message consumer |
| Reject/drop | Từ chối hoặc loại dữ liệu khi không còn capacity | Chỉ dùng khi hợp đồng cho phép mất hoặc từ chối message |

Không phải ứng dụng nào cũng được phép drop dữ liệu. Với giao dịch, đơn hàng hoặc sự kiện audit, bỏ bản ghi để giảm tải thường không chấp nhận được. Khi đó cần block, giảm tốc độ nhận, ghi vào durable queue hoặc trả lỗi để bên gửi retry theo chính sách.

## 10. Backpressure với Reactive Streams

Reactive Streams mô hình hóa backpressure bằng demand. Subscriber gọi request(n) để báo rằng nó sẵn sàng nhận tối đa n phần tử. Publisher chỉ được phát trong phạm vi demand đã được yêu cầu.

Trong Java, java.util.concurrent.Flow cung cấp các interface tương ứng từ Java 9. Các thư viện như Reactor hoặc RxJava cũng triển khai mô hình demand/backpressure. Jackson Core tự nó không phải Reactive Streams publisher; ứng dụng cần một adapter để chuyển dữ liệu từ parser pull thành publisher hoặc chuyển dữ liệu từ publisher thành generator.

Một pipeline reactive có thể có hình dạng khái niệm:

    Byte stream
        |
        v
    Jackson parser adapter
        |
        v
    Publisher<JsonNode>
        |
        v
    map / filter / async processing
        |
        v
    bounded concurrency + demand
        |
        v
    JsonGenerator sink

Khi sink ghi chậm, nó giảm demand. Các stage trước phát ít phần tử hơn; adapter chỉ tiếp tục parse khi downstream có nhu cầu. Cần kiểm tra cách thư viện adapter quản lý buffer: một pipeline có toán tử bất đồng bộ với queue nội bộ không giới hạn vẫn có thể mất khả năng backpressure thực tế.

Nếu dùng Reactor, các toán tử giới hạn concurrency và prefetch ảnh hưởng đến số phần tử được yêu cầu trước. Không nên chọn giá trị prefetch lớn tùy tiện; nó là một phần của ngân sách bộ nhớ toàn pipeline.

## 11. Song song hóa xử lý mà vẫn giữ thứ tự

Đọc và ghi JSON thường có một luồng điều khiển tuần tự, nhưng phần xử lý từng record có thể song song nếu các record độc lập. Khi đó cần tính đến hai vấn đề:

1. **Giới hạn số công việc đang chạy:** không gửi vô hạn task vào executor có queue không giới hạn.
2. **Giữ thứ tự đầu ra:** worker hoàn thành không theo thứ tự nhận; nếu JSON đầu ra phải giữ thứ tự đầu vào, cần sequence number và cơ chế sắp xếp lại có giới hạn.

Ví dụ, parser phát record số 1, 2, 3; worker xử lý record 3 xong trước record 1. Nếu ghi ngay khi worker hoàn tất, thứ tự đầu ra sẽ thành 3, 1, 2. Nếu phải giữ thứ tự, consumer cần chờ kết quả kế tiếp theo sequence number. Điều này có thể tạo thêm backlog, vì vậy buffer reorder cũng phải có giới hạn.

Một thiết kế có thể dùng:

    Parser
      |
      v
    Bounded input queue
      |
      v
    N worker threads
      |
      v
    Bounded completion/reorder buffer
      |
      v
    Single JsonGenerator writer

Chỉ một thread nên sở hữu một JsonGenerator tại một thời điểm. Không chia sẻ generator giữa nhiều worker để ghi đồng thời; việc này có thể làm token đan xen và JSON hỏng. Worker trả kết quả về queue; một writer duy nhất ghi chúng theo thứ tự cần thiết.

Nếu không cần giữ thứ tự, có thể ghi theo thứ tự hoàn tất, nhưng hợp đồng dữ liệu phải cho phép điều đó. Với array JSON, thứ tự phần tử thường có ý nghĩa nên cần quyết định rõ.

## 12. Xử lý lỗi và hủy pipeline

Một pipeline nhiều stage phải có cách lan truyền lỗi theo cả hai hướng:

- Parser gặp JSON sai cú pháp hoặc lỗi I/O: ngừng phát record, thông báo cho worker/writer và đóng tài nguyên.
- Worker gặp lỗi nghiệp vụ: chính sách có thể dừng toàn pipeline, ghi lỗi cho record rồi tiếp tục, hoặc đưa record vào dead-letter store.
- Generator gặp lỗi ghi: dừng việc đọc thêm càng sớm càng tốt; nếu tiếp tục parse mà không thể ghi, chỉ làm tăng dữ liệu đang chờ.
- Thread bị interrupt: khôi phục trạng thái interrupt khi thích hợp và giải phóng tài nguyên.

Với queue hữu hạn, lỗi consumer cần đánh thức producer đang bị chặn ở put. Có thể dùng Future.cancel(true), interruption, cancellation token hoặc cơ chế đóng pipeline chung. Producer kết thúc bình thường cần gửi end marker; producer kết thúc bất thường cần truyền cả nguyên nhân lỗi, không chỉ gửi marker bình thường.

Nếu đầu ra là file, ghi trực tiếp vào file đích có thể để lại JSON chưa hoàn chỉnh khi pipeline thất bại. Một chiến lược an toàn hơn là ghi vào file tạm, chỉ đổi tên sang file đích sau khi toàn bộ JSON được đóng và ghi thành công. Với output stream mạng, không thể rollback byte đã gửi; API cần định nghĩa cách retry hoặc đánh dấu kết quả không hoàn chỉnh.

## 13. Điều tiết theo thời gian và giới hạn downstream

Một số hệ thống downstream có giới hạn request/giây hoặc giới hạn kết nối. Khi đó, backpressure không chỉ phụ thuộc queue mà còn phụ thuộc quota.

Ví dụ:

- Nếu dịch vụ đích chỉ nhận 100 request/giây, worker cần giới hạn tốc độ gửi.
- Nếu database chỉ cho phép 20 transaction đồng thời, giới hạn concurrency ở tầng ghi.
- Nếu HTTP response stream bị chậm, writer bị block; producer cần giảm tốc độ parse.

Có thể dùng token bucket hoặc rate limiter để điều tiết. Rate limiter đặt giới hạn tốc độ trung bình; bounded queue giới hạn số công việc đang chờ. Hai cơ chế giải quyết hai vấn đề khác nhau và thường cần phối hợp.

Không nên xử lý downstream chậm bằng cách tăng số worker vô hạn. Điều đó có thể làm tăng số kết nối, tăng contention, khiến downstream càng quá tải và làm latency xấu hơn.

## 14. Theo dõi sức khỏe pipeline

Để biết backpressure đang hoạt động và xác định bottleneck, nên đo riêng từng stage:

| Chỉ số | Điều nó cho biết |
|---|---|
| Records parsed/second | Tốc độ parser đọc bản ghi |
| Records processed/second | Năng lực xử lý nghiệp vụ |
| Records written/second | Tốc độ sink nhận kết quả |
| Queue depth | Số phần tử đang chờ |
| Queue wait time | Producer/consumer phải chờ bao lâu ở queue |
| Processing latency | Thời gian xử lý một record |
| Write latency | Thời gian ghi một record hoặc batch |
| Bytes read/written | Thông lượng theo byte, hữu ích khi record có kích thước khác nhau |
| Heap usage và GC pause | Áp lực bộ nhớ và tác động của garbage collection |
| Error/retry count | Số lỗi, retry và record bị từ chối |

Một queue thường xuyên gần đầy cho thấy downstream đang không theo kịp. Queue luôn rỗng có thể cho thấy consumer nhanh hơn producer, hoặc producer bị giới hạn bởi nguồn vào. Nếu queue dao động quanh một mức ổn định và latency trong ngưỡng cho phép, capacity có thể đang phù hợp.

Nên ghi cả số liệu trung bình lẫn percentile như p95/p99. Trung bình thấp có thể che giấu một số record rất lớn hoặc một downstream thỉnh thoảng bị chậm kéo dài.

## 15. Backpressure không thay thế giới hạn kích thước đầu vào

Backpressure giới hạn số lượng dữ liệu đang chờ giữa các stage, nhưng không tự động giới hạn kích thước một token hoặc một record riêng lẻ. Một JSON string đơn lẻ dài hàng gigabyte vẫn có thể cần lượng bộ nhớ lớn nếu ứng dụng yêu cầu parser dựng nó thành một Java String.

Với Jackson Core phiên bản hỗ trợ, có thể cấu hình StreamReadConstraints để đặt giới hạn cho độ sâu lồng nhau, độ dài string và độ dài number. Ví dụ:

    import com.fasterxml.jackson.core.JsonFactory;
    import com.fasterxml.jackson.core.StreamReadConstraints;
    import com.fasterxml.jackson.databind.ObjectMapper;

    JsonFactory factory = JsonFactory.builder()
            .streamReadConstraints(
                    StreamReadConstraints.builder()
                            .maxNestingDepth(100)
                            .maxStringLength(1_000_000)
                            .maxNumberLength(1_000)
                            .build()
            )
            .build();

    ObjectMapper mapper = new ObjectMapper(factory);

Các giới hạn cần chọn theo hợp đồng dữ liệu và phiên bản Jackson đang dùng. Ngoài parser constraint, tầng HTTP/file upload cũng nên giới hạn tổng kích thước body. Tổng dung lượng tài liệu và kích thước từng token là hai giới hạn riêng.

## 16. Chọn mô hình theo yêu cầu

| Tình huống | Thiết kế thường phù hợp |
|---|---|
| Đọc file lớn, xử lý nhẹ, ghi file tuần tự | Một vòng lặp JsonParser → process → JsonGenerator |
| Xử lý CPU nặng và độc lập theo record | Parser + bounded input queue + worker pool + bounded output queue |
| Cần giữ thứ tự array | Gắn sequence number và bounded reorder buffer trước writer đơn |
| Downstream có quota | Rate limiter kết hợp queue hữu hạn |
| Nguồn và sink bất đồng bộ | Reactive Streams với demand rõ ràng và buffer có giới hạn |
| Mỗi record có kích thước rất khác nhau | Giới hạn theo byte hoặc trọng lượng thay vì chỉ đếm phần tử |
| JSON có token đơn lẻ rất lớn | Stream nội dung con nếu có thể và đặt StreamReadConstraints phù hợp |

Không có một capacity hoặc số worker đúng cho mọi ứng dụng. Hãy bắt đầu với mô hình đơn giản, đo throughput và latency, sau đó chỉ thêm concurrency khi đã xác định được công đoạn cần song song hóa.

## 17. Kết luận

Backpressure phối hợp tốc độ đọc, xử lý và ghi bằng cách giới hạn lượng dữ liệu được phép đi trước công đoạn chậm. Với Jackson, vòng lặp pull dùng JsonParser rồi xử lý và ghi bằng JsonGenerator đã tạo backpressure đồng bộ tự nhiên: parser chỉ đọc tiếp khi chương trình yêu cầu. Khi tách stage thành nhiều thread, cần dùng queue có giới hạn hoặc demand-based flow; queue đầy phải làm producer chờ hoặc áp dụng chính sách được hợp đồng cho phép. Giới hạn queue, kích thước record, concurrency và batch cần được đo cùng throughput, latency và bộ nhớ. Nhờ đó, pipeline có thể xử lý dữ liệu lớn ổn định mà không biến tốc độ đọc cao thành một backlog không giới hạn trong heap.
