# SearchHitsIterator và đóng iterator sau khi sử dụng

Khi cần đọc hoặc xuất một lượng lớn document từ Elasticsearch, tải toàn bộ kết quả vào một List có thể làm ứng dụng tiêu thụ nhiều bộ nhớ. Spring Data Elasticsearch cung cấp SearchHitsIterator<T> để duyệt kết quả theo từng hit. API này thường được lấy từ ElasticsearchOperations.searchForStream(...) và phù hợp với các luồng xử lý tuần tự như xuất file, đồng bộ dữ liệu hoặc xử lý từng document.

Điểm quan trọng nhất khi dùng SearchHitsIterator là quản lý vòng đời của iterator. Đây là tài nguyên có thể giữ search context ở Elasticsearch trong lúc duyệt dữ liệu. Sau khi dùng xong, ứng dụng phải đóng iterator để giải phóng tài nguyên phía client và server. Cách an toàn, dễ đọc nhất là dùng try-with-resources; nếu không thể dùng cấu trúc đó, phải gọi close() trong khối finally.

## 1. Vì sao cần SearchHitsIterator?

Một truy vấn thông thường có thể trả về SearchHits<T> chứa các hit của một lần tìm kiếm. Cách này phù hợp khi số kết quả vừa phải và ứng dụng cần giữ chúng để hiển thị, xử lý hoặc phân trang.

Khi phải xử lý hàng chục nghìn hoặc hàng triệu document, việc gom toàn bộ kết quả vào bộ nhớ có thể gây:

- Heap tăng nhanh theo số lượng và kích thước document.
- Garbage collection hoạt động nhiều.
- Tăng nguy cơ OutOfMemoryError.
- Độ trễ lớn vì phải chờ tải và chuyển đổi nhiều kết quả trước khi bắt đầu xử lý.

SearchHitsIterator<T> cho phép đọc từng SearchHit<T> theo nhu cầu. Ứng dụng xử lý một hit, sau đó chuyển sang hit tiếp theo mà không cần giữ toàn bộ kết quả trong một collection lớn.

Luồng khái quát:

~~~text
ElasticsearchOperations
        |
        | searchForStream(query, entityClass, index)
        v
SearchHitsIterator<T>
        |
        | hasNext() / next()
        v
SearchHit<T>
        |
        | getContent()
        v
Entity Java
        |
        v
Xử lý / ghi file / gửi sang hệ thống khác
        |
        v
close() iterator
~~~

Tên searchForStream có thể khiến người đọc nghĩ rằng API trả về java.util.stream.Stream<T>. Thực tế, API trả về SearchHitsIterator<T>, một iterator có khả năng đóng. Nó không phải một collection được tải sẵn và cũng không phải Java Stream thông thường.

## 2. SearchHitsIterator và SearchHit

SearchHitsIterator<T> cho phép duyệt các kết quả tìm kiếm. Mỗi lần gọi next() trả về một SearchHit<T>, chứa entity đã được chuyển đổi cùng metadata của kết quả.

Một SearchHit<T> có thể cung cấp:

- getContent(): entity Java đã được chuyển đổi.
- getId(): Elasticsearch document ID.
- getScore(): điểm relevance nếu có.
- getIndex(): tên index chứa document.
- getSortValues(): các giá trị sort của hit khi query có sort tương ứng.
- Thông tin highlight và metadata khác tùy query, phiên bản.

Ví dụ:

~~~java
while (iterator.hasNext()) {
    SearchHit<Product> hit = iterator.next();

    Product product = hit.getContent();
    String id = hit.getId();
    float score = hit.getScore();

    process(product, id, score);
}
~~~

Iterator trả về SearchHit<Product> thay vì chỉ Product để ứng dụng có thể sử dụng cả nội dung lẫn thông tin tìm kiếm. Nếu chỉ cần entity, lấy hit.getContent(). Nếu cần xuất ID, score hoặc tên index, hãy đọc metadata từ hit.

## 3. Tạo iterator bằng searchForStream

ElasticsearchOperations cung cấp phương thức searchForStream(...) để bắt đầu một luồng duyệt kết quả. Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public class ProductExportService {

    private final ElasticsearchOperations operations;

    public ProductExportService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void exportActiveProducts() {
        Query query = new CriteriaQuery(
                new Criteria("status").is("ACTIVE")
        );

        SearchHitsIterator<Product> iterator =
                operations.searchForStream(
                        query,
                        Product.class,
                        IndexCoordinates.of("products")
                );

        // Duyệt kết quả ở đây.
    }
}
~~~

searchForStream nhận query, kiểu entity đích và IndexCoordinates. Spring Data dùng mapping metadata để chuyển _source thành Product. IndexCoordinates có thể trỏ đến index hoặc alias mà ứng dụng muốn tìm kiếm.

Phần quan trọng còn thiếu trong ví dụ trên là đóng iterator. Không nên để iterator được tạo rồi bỏ quên; hãy đưa nó vào try-with-resources như phần tiếp theo.

## 4. Đóng iterator bằng try-with-resources

Đây là cách được khuyến nghị:

~~~java
public void exportActiveProducts() {
    Query query = new CriteriaQuery(
            new Criteria("status").is("ACTIVE")
    );

    try (SearchHitsIterator<Product> iterator =
                 operations.searchForStream(
                         query,
                         Product.class,
                         IndexCoordinates.of("products")
                 )) {

        while (iterator.hasNext()) {
            SearchHit<Product> hit = iterator.next();
            Product product = hit.getContent();

            exportOne(product);
        }
    }
}
~~~

Khi chương trình rời khỏi khối try, Java tự gọi close() trên iterator. Việc này xảy ra trong cả các trường hợp:

- Duyệt hết kết quả bình thường.
- Có lệnh return bên trong khối try.
- Vòng lặp dừng sớm bằng break.
- exportOne(...) ném exception.
- Có lỗi trong quá trình gọi hasNext() hoặc next().

SearchHitsIterator triển khai hợp đồng iterator có thể đóng (CloseableIterator trong Spring Data). Hợp đồng này cho phép sử dụng try-with-resources như các tài nguyên Java khác.

### 4.1. Vì sao không chỉ dựa vào hết vòng lặp?

Việc hasNext() trả về false cho biết không còn hit để duyệt. Nó không thay thế trách nhiệm đóng iterator. Iterator có thể giữ scroll/search context hoặc tài nguyên liên quan đến request. Hãy luôn đóng rõ ràng, kể cả khi đã duyệt đến cuối.

### 4.2. Đóng khi dừng sớm

Ví dụ chỉ cần tìm và xử lý tối đa 100 document:

~~~java
try (SearchHitsIterator<Product> iterator =
             operations.searchForStream(
                     query,
                     Product.class,
                     IndexCoordinates.of("products")
             )) {

    int processed = 0;

    while (iterator.hasNext() && processed < 100) {
        Product product = iterator.next().getContent();
        exportOne(product);
        processed++;
    }
}
~~~

Khi đạt giới hạn và thoát khỏi khối try, iterator vẫn được đóng. Điều này đặc biệt quan trọng với luồng xử lý có điều kiện dừng sớm.

## 5. Đóng iterator bằng try-finally

Nếu cấu trúc code không phù hợp với try-with-resources, hãy gọi close() trong finally:

~~~java
SearchHitsIterator<Product> iterator =
        operations.searchForStream(
                query,
                Product.class,
                IndexCoordinates.of("products")
        );

try {
    while (iterator.hasNext()) {
        Product product = iterator.next().getContent();
        exportOne(product);
    }
} finally {
    iterator.close();
}
~~~

Khối finally chạy khi vòng lặp kết thúc, khi có return hoặc khi exception truyền ra ngoài. Tuy nhiên, nếu có thể, try-with-resources thường ngắn gọn và ít sai sót hơn.

Không viết code chỉ gọi close() ở cuối vòng lặp:

~~~java
// Không an toàn nếu xử lý ném exception hoặc return trước dòng close.
while (iterator.hasNext()) {
    process(iterator.next());
}
iterator.close();
~~~

Nếu process(...) ném exception, dòng close() cuối phương thức sẽ không được chạy. Đây là lý do cần cấu trúc quản lý tài nguyên tự động.

## 6. Iterator thường dùng scroll context

Trong các triển khai Spring Data Elasticsearch phổ biến, searchForStream(...) được thực hiện bằng cơ chế scroll để lấy kết quả theo từng lô. Scroll giữ một search context ở Elasticsearch để các lần lấy tiếp theo tiếp tục duyệt cùng tập kết quả theo trạng thái ban đầu.

Quy trình khái quát:

1. Spring Data gửi truy vấn khởi tạo và nhận batch đầu tiên.
2. Iterator cung cấp từng hit trong batch.
3. Khi cần thêm kết quả, implementation gửi yêu cầu scroll tiếp theo.
4. Elasticsearch trả batch kế tiếp.
5. Khi iterator được đóng, scroll context được giải phóng theo implementation.

Ứng dụng không cần tự gọi scroll API cho mỗi batch khi dùng abstraction này. Tuy vậy, cần nhớ iterator không phải một danh sách trong bộ nhớ: việc duyệt có thể tiếp tục phát sinh request mạng.

### 6.1. Search context tiêu thụ tài nguyên

Scroll context giữ trạng thái tìm kiếm và có thể giữ các segment cần thiết để tiếp tục đọc. Một số lượng lớn scroll context tồn tại lâu có thể gây áp lực lên node Elasticsearch.

Do đó:

- Đóng iterator ngay khi xử lý xong.
- Đặt thời gian giữ scroll vừa đủ cho tốc độ xử lý.
- Tránh mở iterator rồi để chờ người dùng thao tác.
- Tránh tạo nhiều iterator không giới hạn cùng lúc.
- Giới hạn số luồng export chạy đồng thời.
- Theo dõi thời gian xử lý và lỗi mạng để phát hiện iterator tồn tại quá lâu.

Thời gian scroll/keep-alive và cách truyền cấu hình có thể khác giữa các phiên bản Spring Data Elasticsearch. Hãy dùng API query tương ứng của phiên bản dự án và không giả định một method cụ thể tồn tại ở mọi release train.

## 7. Xử lý từng hit mà không tích lũy toàn bộ dữ liệu

Mục tiêu chính của iterator là xử lý từng hit hoặc từng batch nhỏ. Ví dụ ghi từng dòng ra một writer:

~~~java
public void exportProducts(Writer writer) throws IOException {
    Query query = new CriteriaQuery(
            new Criteria("status").is("ACTIVE")
    );

    try (SearchHitsIterator<Product> iterator =
                 operations.searchForStream(
                         query,
                         Product.class,
                         IndexCoordinates.of("products")
                 )) {

        while (iterator.hasNext()) {
            Product product = iterator.next().getContent();

            writer.write(product.getId());
            writer.write(",");
            writer.write(escapeCsv(product.getName()));
            writer.write(",");
            writer.write(product.getPrice().toPlainString());
            writer.write(System.lineSeparator());
        }
    }
}
~~~

Ví dụ tập trung vào cách duyệt và đóng iterator. Trong code xuất CSV thực tế, cần xử lý null, escape dấu phẩy/dấu nháy, encoding và đóng writer theo quyền sở hữu tài nguyên. Nếu writer được truyền từ bên ngoài, service cần thống nhất rõ bên nào chịu trách nhiệm đóng writer.

### 7.1. Xử lý theo batch nhỏ

Một số hệ thống cần gom vài trăm record để ghi database hoặc gửi sang API đích. Có thể tạo batch giới hạn:

~~~java
int batchSize = 500;
List<Product> batch = new ArrayList<>(batchSize);

try (SearchHitsIterator<Product> iterator =
             operations.searchForStream(
                     query,
                     Product.class,
                     IndexCoordinates.of("products")
             )) {

    while (iterator.hasNext()) {
        batch.add(iterator.next().getContent());

        if (batch.size() == batchSize) {
            targetService.writeBatch(new ArrayList<>(batch));
            batch.clear();
        }
    }

    if (!batch.isEmpty()) {
        targetService.writeBatch(new ArrayList<>(batch));
    }
}
~~~

Bộ nhớ lúc này tỷ lệ với kích thước batch thay vì tổng số document. Nếu writeBatch ném exception, try-with-resources vẫn đóng iterator.

Không chọn batch quá lớn mà không đo đạc. Kích thước phù hợp phụ thuộc kích thước entity, tốc độ hệ thống đích, giới hạn request và dung lượng heap.

## 8. Phân biệt SearchHitsIterator với SearchHits và Java Stream

| Đặc điểm | SearchHits | SearchHitsIterator | Java Stream |
|---|---|---|---|
| Hình thức | Kết quả tìm kiếm đã được materialize | Iterator đọc dần các hit | Pipeline xử lý phần tử |
| Duyệt | Lặp trên kết quả đã có | hasNext() / next() | Các phép toán Stream |
| Bộ nhớ | Phụ thuộc số hit đã tải | Có thể giới hạn theo batch | Phụ thuộc nguồn và pipeline |
| Metadata hit | Có | Có qua từng SearchHit | Tùy phần tử nguồn |
| Đóng tài nguyên | Thường không giữ scroll iterator | Phải đóng | Chỉ cần đóng nếu nguồn stream giữ tài nguyên |
| Use case | Trang kết quả vừa phải | Export hoặc scan nhiều document | Xử lý dữ liệu từ nguồn Stream |

Không nên gọi iterator.forEachRemaining(...) rồi quên đóng iterator. Dù API tiện ích có thể duyệt hết, trách nhiệm giải phóng vẫn còn.

### 8.1. Không chuyển iterator thành List nếu mục tiêu là tiết kiệm bộ nhớ

Ví dụ sau làm mất lợi ích streaming:

~~~java
List<Product> allProducts = new ArrayList<>();

try (SearchHitsIterator<Product> iterator =
             operations.searchForStream(query, Product.class, index)) {
    while (iterator.hasNext()) {
        allProducts.add(iterator.next().getContent());
    }
}
~~~

Iterator vẫn được đóng đúng cách, nhưng toàn bộ entity đã được giữ trong allProducts. Nếu số document rất lớn, heap vẫn có thể tăng đến mức không an toàn.

Hãy xử lý từng hit, ghi ra file hoặc gửi theo batch giới hạn. Chỉ chuyển thành List khi biết rõ giới hạn số lượng kết quả.

## 9. Xử lý exception trong lúc duyệt

Lỗi có thể xảy ra ở nhiều thời điểm:

- Mở truy vấn ban đầu thất bại.
- Request lấy batch kế tiếp bị timeout hoặc mất kết nối.
- Mapping _source sang entity gặp lỗi conversion.
- Code xử lý document ném exception.
- Hệ thống đích từ chối batch hoặc ghi file thất bại.

Try-with-resources bảo đảm close() được gọi khi iterator đã được tạo thành công. Nó không làm cho thao tác đang lỗi tự động thành công và cũng không bảo đảm có thể tiếp tục từ đúng vị trí sau khi request scroll thất bại.

Ví dụ ghi nhận lỗi:

~~~java
public void exportProducts() {
    Query query = new CriteriaQuery(
            new Criteria("status").is("ACTIVE")
    );

    try (SearchHitsIterator<Product> iterator =
                 operations.searchForStream(
                         query,
                         Product.class,
                         IndexCoordinates.of("products")
                 )) {

        while (iterator.hasNext()) {
            SearchHit<Product> hit = iterator.next();
            process(hit.getContent());
        }
    } catch (RuntimeException exception) {
        log.error("Export products from Elasticsearch failed", exception);
        throw exception;
    }
}
~~~

Không nuốt exception rồi báo export thành công. Nếu một batch thất bại, hãy xác định tác vụ có thể retry an toàn hay không, và ghi nhận tiến độ ở hệ thống điều phối nếu cần.

### 9.1. Xử lý lỗi theo từng document

Nếu một document lỗi không nên làm dừng toàn bộ export, có thể bắt lỗi quanh phần xử lý từng hit:

~~~java
try (SearchHitsIterator<Product> iterator =
             operations.searchForStream(query, Product.class, index)) {

    while (iterator.hasNext()) {
        SearchHit<Product> hit = iterator.next();

        try {
            process(hit.getContent());
        } catch (RecoverableRecordException exception) {
            recordFailure(hit.getId(), exception);
        }
    }
}
~~~

Chỉ bắt loại exception mà ứng dụng thực sự có thể xử lý. Không nên bắt mọi Exception rồi tiếp tục nếu lỗi có thể là lỗi hệ thống, lỗi kết nối hoặc trạng thái dữ liệu không còn đáng tin cậy.

## 10. Không chia sẻ một iterator giữa nhiều thread

SearchHitsIterator là một cursor có trạng thái: vị trí hiện tại, batch đang giữ và trạng thái scroll. Không nên để nhiều thread cùng gọi hasNext() hoặc next() trên một iterator nếu API không công bố hỗ trợ thread-safe.

Nếu cần tăng thông lượng:

- Chia công việc thành các truy vấn độc lập có phạm vi rõ ràng.
- Giới hạn số luồng và số iterator mở đồng thời.
- Mỗi worker sở hữu và đóng iterator của chính nó.
- Tránh để các truy vấn chồng lấn gây xử lý trùng dữ liệu.
- Theo dõi tải Elasticsearch và hệ thống đích.

Không tạo một iterator duy nhất rồi đưa nó vào nhiều task executor. Việc đó có thể gây mất thứ tự, bỏ sót hoặc xử lý lặp.

## 11. Chọn kích thước batch và thời gian giữ scroll

Kích thước batch là số hit Elasticsearch trả trong mỗi lần lấy dữ liệu. Batch nhỏ giảm bộ nhớ mỗi lần nhưng có thể tăng số request; batch lớn giảm số lần round-trip nhưng tốn heap và tăng thời gian xử lý mỗi batch.

Khi chọn batch:

1. Đo kích thước trung bình của _source và entity sau conversion.
2. Thử một số kích thước batch ở môi trường tương đương production.
3. Theo dõi heap, GC, thời gian request và throughput.
4. Kiểm tra tốc độ tiêu thụ của hệ thống đích.
5. Chọn mức có biên an toàn khi dữ liệu tăng.

Scroll keep-alive là khoảng thời gian Elasticsearch giữ search context giữa các lần scroll. Nó cần đủ dài để ứng dụng xử lý một batch và yêu cầu batch tiếp theo. Nếu quá ngắn, context có thể hết hạn trước request tiếp theo; nếu quá dài, tài nguyên bị giữ lâu khi worker bị treo hoặc dừng.

Không nên tăng keep-alive vô hạn để che lỗi xử lý chậm. Hãy đo thời gian batch, phát hiện worker không tiến triển và đóng iterator khi tác vụ bị hủy.

## 12. SearchHitsIterator và các lựa chọn phân trang khác

Không phải mọi trường hợp duyệt nhiều kết quả đều cần SearchHitsIterator. Chọn cách tiếp cận theo mục tiêu:

| Nhu cầu | Cơ chế thường phù hợp |
|---|---|
| Hiển thị một trang nhỏ cho người dùng | SearchHits hoặc Pageable |
| Duyệt tuần tự, xử lý/export nhiều document | SearchHitsIterator qua searchForStream |
| Phân trang sâu theo cursor cho API người dùng | search_after, thường kết hợp PIT |
| Duyệt dữ liệu lớn cần thứ tự cursor ổn định | PIT + search_after |
| Tác vụ tổng hợp toàn bộ dữ liệu | Streaming hoặc batch job có checkpoint |

Scroll thường phù hợp cho tác vụ batch cần duyệt một tập kết quả. search_after phù hợp cho cursor pagination và deep pagination. PIT giúp các trang dùng cùng một góc nhìn dữ liệu. Các abstraction này có thể có mục đích gần nhau nhưng không nên coi là thay thế trực tiếp trong mọi trường hợp.

### 12.1. Vì sao không dùng Pageable để export hàng triệu document?

Pageable thường dựa trên phân trang offset. Khi page number tăng, from tăng theo và chi phí truy vấn tăng. Elasticsearch cũng áp dụng giới hạn result window cho from + size.

Với export toàn bộ dữ liệu, gọi page 0, page 1, page 2 liên tục không phải lựa chọn hiệu quả nhất. SearchHitsIterator hoặc PIT + search_after phù hợp hơn tùy yêu cầu về thứ tự, tính nhất quán và khả năng checkpoint.

### 12.2. Khi nào cần PIT + search_after thay cho iterator?

Chọn PIT + search_after khi:

- Client cần cursor để tiếp tục qua nhiều request HTTP.
- Người dùng có thể tạm dừng rồi tiếp tục trong thời hạn PIT.
- Cần chủ động lưu sort values của hit cuối.
- Cần kiểm soát thứ tự và snapshot nhất quán qua nhiều trang.

Chọn SearchHitsIterator khi một tiến trình trong ứng dụng sở hữu toàn bộ vòng đời duyệt, xử lý tuần tự và đóng iterator trong cùng một tác vụ.

## 13. Ví dụ hoàn chỉnh: xuất dữ liệu theo batch và đóng an toàn

Ví dụ sau thể hiện một service xử lý danh sách sản phẩm đang hoạt động theo batch. Mỗi batch được gửi sang hệ thống đích; iterator luôn được đóng dù xử lý thành công hay thất bại.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductExportService {

    private static final int BATCH_SIZE = 500;

    private final ElasticsearchOperations operations;
    private final ProductTargetService targetService;

    public ProductExportService(
            ElasticsearchOperations operations,
            ProductTargetService targetService
    ) {
        this.operations = operations;
        this.targetService = targetService;
    }

    public void exportActiveProducts() {
        Query query = new CriteriaQuery(
                new Criteria("status").is("ACTIVE")
        );

        List<Product> batch = new ArrayList<>(BATCH_SIZE);

        try (SearchHitsIterator<Product> iterator =
                     operations.searchForStream(
                             query,
                             Product.class,
                             IndexCoordinates.of("products")
                     )) {

            while (iterator.hasNext()) {
                SearchHit<Product> hit = iterator.next();
                batch.add(hit.getContent());

                if (batch.size() == BATCH_SIZE) {
                    targetService.writeBatch(new ArrayList<>(batch));
                    batch.clear();
                }
            }

            if (!batch.isEmpty()) {
                targetService.writeBatch(new ArrayList<>(batch));
            }
        }
    }
}
~~~

new ArrayList<>(batch) tạo một bản sao của batch trước khi gửi sang service đích. Điều này tránh việc batch.clear() làm thay đổi danh sách mà service đích vẫn đang giữ tham chiếu. Nếu writeBatch xử lý đồng bộ và không giữ danh sách, có thể chọn cách truyền phù hợp với hợp đồng của service.

Trong một export thực tế, cần cân nhắc thêm:

- Ghi checkpoint hoặc tiến độ để biết đã xử lý đến đâu.
- Thiết kế thao tác đích idempotent để retry không tạo dữ liệu trùng.
- Ghi nhận số document thành công và thất bại.
- Xử lý tín hiệu hủy tác vụ để khối try thoát và đóng iterator.
- Đặt giới hạn thời gian và số lần retry.

## 14. Kiểm thử việc đóng iterator

Đóng iterator là một phần của hành vi cần kiểm tra, đặc biệt khi tác vụ có thể kết thúc sớm hoặc ném exception.

Một số tình huống:

| Tình huống | Kỳ vọng |
|---|---|
| Duyệt hết kết quả | close() được gọi |
| Dừng bằng break | close() được gọi |
| return trong khối try | close() được gọi |
| Xử lý document ném exception | close() được gọi |
| hasNext() hoặc next() ném exception | close() được gọi |
| Iterator mở thành công nhưng batch đích lỗi | close() được gọi |

Có thể dùng một CloseableIterator giả trong unit test để xác nhận close() được gọi khi service kết thúc. Tuy nhiên, unit test không xác nhận được scroll context thực tế trên Elasticsearch đã được giải phóng. Với luồng quan trọng, cần integration test trên Elasticsearch tương thích với phiên bản Spring Data của dự án và quan sát hành vi đóng scroll.

### 14.1. Ví dụ kiểm thử khái niệm

~~~java
@Test
void closesIteratorWhenProcessingFails() {
    SearchHitsIterator<Product> iterator = mock(SearchHitsIterator.class);

    when(iterator.hasNext()).thenReturn(true, false);
    when(iterator.next()).thenReturn(searchHit);

    when(operations.searchForStream(
            any(Query.class),
            eq(Product.class),
            any(IndexCoordinates.class)
    )).thenReturn(iterator);

    doThrow(new IllegalStateException("target failed"))
            .when(targetService).writeBatch(anyList());

    assertThrows(
            IllegalStateException.class,
            () -> service.exportActiveProducts()
    );

    verify(iterator).close();
}
~~~

Đây là ví dụ minh họa hướng kiểm thử; chữ ký method và cách mock phụ thuộc vào service cụ thể. Ý chính là xác nhận close() được gọi khi phần xử lý ném exception, không chỉ khi vòng lặp kết thúc bình thường.

## 15. Những lỗi thường gặp

### 15.1. Quên đóng iterator

Đây là lỗi quan trọng nhất. Scroll/search context có thể tiếp tục giữ tài nguyên trên Elasticsearch. Dùng try-with-resources cho mọi iterator được tạo.

### 15.2. Chỉ đóng sau vòng lặp

Nếu có exception hoặc return trước dòng close, tài nguyên không được giải phóng. Dùng try-with-resources hoặc finally.

### 15.3. Chuyển toàn bộ kết quả thành List

Làm vậy khiến heap tăng theo tổng số document và mất lợi ích của streaming. Xử lý từng hit hoặc theo batch giới hạn.

### 15.4. Nghĩ iterator chỉ đọc dữ liệu trong bộ nhớ

Việc gọi next có thể khiến implementation lấy batch tiếp theo qua mạng. Cần dự trù timeout, retry và lỗi kết nối trong quá trình duyệt.

### 15.5. Dùng iterator như Java Stream

SearchHitsIterator có hợp đồng hasNext()/next() và close(). Không mặc định nó hỗ trợ các thao tác map, filter, parallel của Java Stream.

### 15.6. Chia sẻ iterator cho nhiều thread

Iterator có trạng thái duyệt và không nên được dùng đồng thời bởi nhiều thread. Mỗi tác vụ nên sở hữu iterator riêng.

### 15.7. Giữ iterator mở trong lúc chờ thao tác bên ngoài

Ví dụ mở iterator rồi chờ người dùng xác nhận trước khi tiếp tục có thể giữ scroll context quá lâu. Hãy đóng iterator sau mỗi tác vụ hoặc thiết kế cursor pagination riêng cho phiên người dùng.

### 15.8. Bỏ qua lỗi khi ghi đích

Nếu một batch lỗi mà ứng dụng vẫn báo export thành công, dữ liệu có thể bị thiếu. Ghi nhận checkpoint, số lượng và trạng thái lỗi; chỉ retry khi thao tác đích an toàn.

## 16. Quy trình sử dụng SearchHitsIterator

Một quy trình phù hợp cho export:

1. Xác định index hoặc alias và query cần duyệt.
2. Chọn entity class để Spring Data chuyển đổi _source.
3. Chọn batch size phù hợp với heap và hệ thống đích.
4. Mở iterator bằng searchForStream(...).
5. Đặt iterator trong try-with-resources ngay khi tạo.
6. Duyệt từng SearchHit<T> bằng hasNext() và next().
7. Xử lý getContent() hoặc metadata của hit.
8. Gửi từng record hoặc batch giới hạn sang hệ thống đích.
9. Ghi nhận tiến độ và xử lý lỗi theo chính sách retry.
10. Để try-with-resources đóng iterator khi kết thúc, dừng sớm hoặc có exception.

Nếu yêu cầu là phân trang sâu cho người dùng, hãy cân nhắc PIT + search_after thay vì giữ một iterator/scroll context trong suốt phiên HTTP dài.

## 17. Kết luận

SearchHitsIterator<T> cho phép Spring Data Elasticsearch duyệt kết quả tìm kiếm theo từng SearchHit<T>, phù hợp với tác vụ xuất hoặc xử lý số lượng lớn document mà không cần tải toàn bộ kết quả vào một collection. API thường được tạo bằng ElasticsearchOperations.searchForStream(...).

Iterator có thể giữ search/scroll context ở Elasticsearch, vì vậy phải đóng sau khi sử dụng. Dùng try-with-resources để bảo đảm close() được gọi khi duyệt hết, dừng sớm, return hoặc có exception. Nếu không thể dùng cấu trúc này, gọi close() trong finally.

Hãy xử lý từng hit hoặc theo batch giới hạn, kiểm soát số iterator chạy đồng thời và theo dõi thời gian giữ context. SearchHitsIterator phù hợp với một tiến trình batch sở hữu trọn vòng đời duyệt; search_after kết hợp PIT phù hợp hơn cho cursor pagination cần tiếp tục qua nhiều request. Việc đóng iterator là một phần bắt buộc của thiết kế, không phải bước dọn dẹp tùy chọn.
