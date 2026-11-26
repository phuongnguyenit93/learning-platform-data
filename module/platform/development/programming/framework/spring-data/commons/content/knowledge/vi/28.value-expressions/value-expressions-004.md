# Biểu thức trong annotation mapping và phạm vi store hỗ trợ

## 1. Annotation chứa chuỗi chưa đồng nghĩa chuỗi đó được thực thi

Trong chương **Biểu thức giá trị** của module **SPRING_DATA_COMMONS**, một điểm dễ nhầm là nhìn thấy một thuộc tính annotation có kiểu `String` rồi cho rằng có thể đặt `${...}` hoặc `#{...}` vào đó ở mọi nơi.

Ví dụ, chuỗi sau có thể xuất hiện trong một annotation hỗ trợ tên tài nguyên bằng biểu thức:

~~~text
#{@collectionNames.orders}
~~~

Nhưng để nó trở thành tên collection thực tế, phải có thành phần đọc annotation, nhận diện cú pháp, tạo ngữ cảnh đánh giá và sử dụng kết quả.

Spring Data Commons cung cấp các abstraction dùng chung cho biểu thức giá trị. Khả năng dùng biểu thức trong một annotation cụ thể thuộc về module và thành phần tiêu thụ metadata đó.

Bài học trả lời bốn câu hỏi:

1. Chuỗi annotation đang là literal, property placeholder hay biểu thức?
2. Thuộc tính annotation này có được store hỗ trợ đánh giá không?
3. Biểu thức được cung cấp bean, property hoặc biến nào?
4. Kết quả được dùng lúc nào và ảnh hưởng đến những thao tác persistence nào?

Đây là nền tảng để áp dụng biểu thức đúng trong mapping, repository và cấu hình, thay vì suy rộng từ một ví dụ MongoDB sang tất cả store.

## 2. Ba dạng giá trị cần phân biệt

Ở một consumer hỗ trợ cú pháp tương ứng, có thể phân biệt:

| Dạng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Literal | `orders` | Tên cố định |
| Property placeholder | `${app.orders.collection}` | Lấy giá trị từ cấu hình mà consumer có thể truy cập |
| SpEL template | `#{@collectionNames.orders}` | Đánh giá biểu thức trong ngữ cảnh được cung cấp |
| Giá trị kết hợp | `orders-${app.env}-#{@partitionNames.suffix}` | Ghép phần cố định với các phần được phân giải |

Dòng kết hợp minh họa khả năng của value expression khi consumer hỗ trợ nó; không phải lời khẳng định mọi annotation mapping đều chấp nhận cả hai loại cú pháp.

### 2.1. Placeholder lấy cấu hình

Theo quy ước placeholder của Spring, một biểu thức như:

~~~text
${app.orders.collection:orders}
~~~

có thể lấy giá trị cấu hình và dùng `orders` làm mặc định khi không có property tương ứng.

Tuy nhiên, dấu `${...}` không tự kích hoạt cơ chế này. Thành phần đọc thuộc tính annotation phải thực hiện việc phân giải.

Một annotation được JPA provider xử lý không đương nhiên đi qua cùng bộ phân giải với một tham số `@Value` trong bean Spring.

### 2.2. SpEL cần evaluation context

Trong biểu thức:

~~~text
#{@collectionNames.orders}
~~~

- `#{...}` xác định phần biểu thức theo cú pháp template.
- `@collectionNames` yêu cầu tra cứu một bean.
- `orders` là thuộc tính được truy cập trên bean đó, chẳng hạn qua getter `getOrders()`.

Tra cứu bean chỉ hoạt động khi evaluation context có cơ chế hỗ trợ truy cập bean. Việc ứng dụng có một `ApplicationContext` không tự bảo đảm mọi bộ đánh giá biểu thức đều đã được nối với nó.

Tương tự:

~~~text
#{#tenantId}
~~~

chỉ có ý nghĩa nếu consumer đã đưa biến `tenantId` vào ngữ cảnh. Nó không tự tìm tenant từ HTTP request.

### 2.3. Chuỗi biểu thức vẫn phải là hằng Java hợp lệ trong annotation

Java yêu cầu đối số annotation đáp ứng quy tắc của giá trị annotation, chẳng hạn một hằng chuỗi cho thuộc tính kiểu `String`.

Đoạn sau dùng một hằng chuỗi:

~~~java
@Document(collection = "#{@collectionNames.orders}")
~~~

Lời gọi getter không được Java thực hiện khi biên dịch. Nó nằm bên trong chuỗi, được một consumer phù hợp xử lý sau đó.

Ngược lại, không thể thay đối số annotation bằng một lời gọi phương thức Java tùy ý ở runtime:

~~~text
collection = collectionNames.getOrders()
~~~

Đây là hai cơ chế khác nhau: giá trị annotation hợp lệ ở mức ngôn ngữ và nội dung chuỗi được diễn giải ở mức framework.

## 3. Luồng từ annotation đến thao tác persistence

Có thể hình dung luồng xử lý như sau:

~~~mermaid
flowchart TD
    A["Chuỗi trong thuộc tính annotation"] --> B["Metadata của module hoặc store"]
    B --> C{"Thuộc tính có hỗ trợ biểu thức?"}
    C -->|"Có"| D["Parser và ngữ cảnh đánh giá"]
    D --> E["Kết quả được kiểm tra và chuyển đổi nếu có"]
    E --> F["Tên tài nguyên hoặc giá trị mapping"]
    F --> G["Đọc, ghi hoặc tạo truy vấn"]
    C -->|"Không"| H["Được xử lý theo hợp đồng riêng: literal hoặc lỗi"]
~~~

Một parser nhận diện được biểu thức không đủ để bảo đảm thao tác database sẽ đúng.

Cần có đủ các mắt xích:

1. Consumer chủ động đọc và đánh giá đúng thuộc tính annotation.
2. Cú pháp được consumer hỗ trợ.
3. Ngữ cảnh cung cấp những phụ thuộc mà biểu thức cần.
4. Kết quả có kiểu và giá trị hợp lệ.
5. Kết quả được đưa vào đúng đường mapping hoặc truy vấn.
6. Cách đánh giá và caching phù hợp với vòng đời ứng dụng.

Nếu thiếu một mắt xích, lỗi có thể xuất hiện khi khởi tạo metadata, khi bắt đầu thao tác repository hoặc lúc store nhận câu lệnh.

Không nên chỉ kiểm tra biểu thức bằng một parser độc lập rồi kết luận annotation của store hỗ trợ nó.

## 4. Commons cung cấp abstraction, store quyết định điểm tích hợp

Spring Data Commons có mô hình value expression để biểu diễn và đánh giá các giá trị chứa placeholder, SpEL hoặc phần văn bản kết hợp.

Các vai trò cần phân biệt là:

- **Parser:** đọc cú pháp và tạo biểu diễn của biểu thức.
- **Nguồn cấu hình:** cung cấp property cho phần placeholder.
- **Evaluation context:** cung cấp root object, biến, hàm hoặc khả năng truy cập bean tùy cấu hình.
- **Consumer:** quyết định khi nào đánh giá và dùng kết quả vào việc gì.

Một abstraction dùng chung không phải bộ xử lý tự động quét tất cả annotation trong mọi module.

Ví dụ, việc một module dùng infrastructure của Commons cho tên collection không dẫn đến các kết luận sau:

- Mọi thuộc tính tên field đều hỗ trợ cùng cú pháp.
- Mọi biến dùng trong query đều có trong mapping.
- Tên bảng của một JPA entity cũng được đánh giá tương tự.
- Có thể lấy dữ liệu của entity hiện tại trong mọi biểu thức annotation.

Khi mở rộng repository hoặc viết công cụ đọc metadata, cũng cần giữ ranh giới này. Việc tự đọc chuỗi annotation bằng reflection không tái tạo toàn bộ pipeline của store.

## 5. Ví dụ MongoDB: chọn collection từ một bean cấu hình

Spring Data MongoDB là ví dụ về module có hỗ trợ SpEL cho tên collection trong `@Document`.

Ví dụ dưới đây giả định ứng dụng đã có hạ tầng Spring Data MongoDB tương ứng. Nó minh họa một collection được quyết định từ cấu hình ổn định, không phụ thuộc request.

### 5.1. Bean cung cấp tên collection

Đặt public type này trong một file Java riêng khi áp dụng:

~~~java
import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MappingNamesConfiguration {

    @Bean
    public CollectionNames collectionNames(
            @Value("${app.mongodb.orders-collection:orders}")
            String configuredName) {

        return new CollectionNames(configuredName);
    }

    public static final class CollectionNames {

        private final String orders;

        public CollectionNames(String orders) {
            Objects.requireNonNull(orders, "orders");

            if (!orders.matches("[a-z][a-z0-9_]{0,62}")) {
                throw new IllegalArgumentException(
                        "Invalid configured orders collection name");
            }

            this.orders = orders;
        }

        public String getOrders() {
            return orders;
        }
    }
}
~~~

Quy tắc tên trong ví dụ là chính sách do ứng dụng tự chọn. Nó không mô tả đầy đủ giới hạn đặt tên của MongoDB hay mọi store.

Bean này chỉ cung cấp tên đã được kiểm tra. Nó không gọi repository, không kiểm tra database và không đọc trạng thái request.

Cấu hình minh họa:

~~~properties
app.mongodb.orders-collection=orders_archive
~~~

### 5.2. Entity tham chiếu bean đó

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "#{@collectionNames.orders}")
public class OrderDocument {

    @Id
    private String id;

    private String orderNumber;

    public OrderDocument() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public void setOrderNumber(String orderNumber) {
        this.orderNumber = orderNumber;
    }
}
~~~

Biểu thức tìm bean tên `collectionNames` và đọc thuộc tính `orders`. Với cấu hình nêu trên, giá trị mong đợi là `orders_archive` khi đường mapping đánh giá tên collection.

Repository vẫn khai báo theo domain type:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<OrderDocument, String> {
}
~~~

Không cần đưa chuỗi biểu thức vào tên phương thức repository.

### 5.3. Hai điểm đánh giá độc lập trong cùng ví dụ

Ví dụ có hai consumer khác nhau:

1. Spring xử lý `@Value("${app.mongodb.orders-collection:orders}")` khi tạo bean cấu hình.
2. Hạ tầng mapping MongoDB xử lý biểu thức của thuộc tính `collection` trong `@Document`.

Việc placeholder hoạt động ở bước 1 không chứng minh rằng cùng placeholder được hỗ trợ trong một thuộc tính annotation khác ở bước 2.

Cách tổ chức này cũng không yêu cầu dựa vào thời điểm đánh giá collection chưa được xác định: bean trả về một tên ổn định trong suốt vòng đời của nó.

Nếu thay đổi file cấu hình sau khi ứng dụng đã chạy, không nên mặc định bean hoặc metadata sẽ tự cập nhật. Cần một cơ chế refresh được cấu hình rõ hoặc khởi động lại theo hợp đồng vận hành của ứng dụng.

## 6. Không suy rộng hỗ trợ từ collection sang mọi thuộc tính mapping

Một annotation có thể có nhiều thuộc tính như tên collection, cấu hình collation hoặc các tùy chọn khác. Mỗi thuộc tính có hợp đồng riêng.

Điều cần kiểm tra là:

~~~text
module + annotation đầy đủ package + thuộc tính + phiên bản
~~~

Chỉ hỏi “annotation này hỗ trợ SpEL không?” thường chưa đủ chính xác.

Ví dụ:

- `@Document(collection = ...)` hỗ trợ biểu thức không tự chứng minh mọi annotation `@Field` cũng hỗ trợ.
- Một thuộc tính chấp nhận placeholder không chắc hỗ trợ truy cập bean bằng SpEL.
- Một thuộc tính chấp nhận SpEL không chắc dùng root object là entity hiện tại.
- Hai annotation cùng tên `Document` nhưng khác package thuộc hai module khác nhau.

Khi viết mã, nên đọc và ghi rõ import để tránh nhầm giữa MongoDB và Elasticsearch:

~~~text
org.springframework.data.mongodb.core.mapping.Document
org.springframework.data.elasticsearch.annotations.Document
~~~

Việc tên class giống nhau không phải bằng chứng về cùng semantics hoặc cùng vòng đời đánh giá.

## 7. Phạm vi hỗ trợ theo store và hạ tầng

Bảng dưới đây giúp xác định đúng nơi cần kiểm tra, không thay thế hợp đồng của phiên bản đang dùng.

| Hạ tầng | Ví dụ liên quan | Điều có thể kết luận |
| --- | --- | --- |
| Spring Data Commons | Abstraction value expression | Có infrastructure dùng chung; không bảo đảm mọi annotation mapping tự được xử lý |
| Spring Data MongoDB | `@Document(collection = ...)` | Có hỗ trợ SpEL cho tên collection; cần ngữ cảnh và cấu hình module tương ứng |
| Spring Data Elasticsearch | `@Document(indexName = ...)` | Có hỗ trợ biểu thức SpEL cho tên index; phải xét thêm vòng đời index và thao tác tạo mapping |
| Spring Data JDBC/R2DBC | Metadata tên bảng, schema và cột | Phải kiểm tra đúng annotation và thuộc tính ở phiên bản Spring Data Relational đang dùng; không suy từ ví dụ MongoDB |
| Spring Data JPA | `jakarta.persistence.Table`, `Column` | JPA provider xử lý mapping; không có cơ chế Spring SpEL chung tự áp dụng vào các tên này |
| Spring Data Redis | Keyspace và khóa | Cần dùng đúng cơ chế mapping hoặc cấu hình keyspace của module; không giả định chuỗi có `#{...}` sẽ được đánh giá |
| Spring bean configuration | `@Value` trong bean | Consumer là Spring container; kết quả này không chứng minh hỗ trợ ở annotation persistence |

### 7.1. Ví dụ Elasticsearch cần được đọc trong phạm vi của module

Một dạng khai báo tên index bằng bean:

~~~java
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "#{@indexNames.orders}")
public class SearchOrder {

    private String id;
}
~~~

Đoạn này chỉ minh họa điểm tích hợp tên index. Nó chưa cấu hình bean `indexNames`, kết nối Elasticsearch hoặc vòng đời tạo index.

Đổi tên index trong biểu thức không tự bảo đảm index mới đã tồn tại, có mapping, alias và chính sách lưu trữ thích hợp.

Không nên chuyển nguyên xi thiết kế từ collection MongoDB sang index Elasticsearch chỉ vì cả hai annotation đều có tên `Document`.

### 7.2. JPA không tự đánh giá biểu thức trong Table.name

Chuỗi sau là một hằng Java nhưng không phải hợp đồng cấu hình SpEL chung của JPA:

~~~java
@jakarta.persistence.Table(name = "#{@tableNames.orders}")
~~~

Không thể dựa vào Spring Data JPA để mặc định biến nó thành tên bảng lấy từ bean. Tùy provider và cách kiểm tra mapping, nó có thể bị hiểu như tên literal hoặc dẫn đến lỗi.

Nếu cần chọn schema hoặc chiến lược đa tenant với JPA, phải dùng cơ chế mà provider và cấu hình persistence thực sự hỗ trợ.

Khả năng dùng biểu thức trong một số query của Spring Data JPA là một tính năng ở tầng query. Nó không tự mở rộng sang `Table.name` hoặc `Column.name`.

### 7.3. Relational cần phân biệt SQL identifier với giá trị tham số

Ở JDBC hoặc R2DBC, tên bảng, schema và cột là SQL identifier. Chúng không cùng loại với giá trị trong điều kiện `WHERE`.

Ngay cả khi phiên bản module hỗ trợ biểu thức ở một thuộc tính mapping, vẫn cần xem:

- Kết quả có được xử lý bằng abstraction identifier của module không?
- Quy tắc quote và phân biệt chữ hoa, chữ thường của dialect là gì?
- Giá trị được tính lúc nào?
- Đường repository và đường SQL viết tay có dùng cùng metadata không?

Không thể dùng cơ chế bind tham số giá trị để thay thế tùy ý tên bảng. Nếu cần chọn tên tài nguyên, phải giới hạn đầu vào và sử dụng API thích hợp cho identifier.

## 8. Mapping expression không có sẵn mọi ngữ cảnh của query

Trong Spring Data có nhiều nơi sử dụng biểu thức. Cú pháp gần giống nhau không có nghĩa chúng dùng cùng context.

| Vị trí | Consumer | Ngữ cảnh chỉ nên dùng khi được cam kết |
| --- | --- | --- |
| Annotation tên collection hoặc index | Mapping của store | Bean, cấu hình, root object hoặc biến mà mapping hỗ trợ |
| Query có biểu thức | Query infrastructure của module | Tham số phương thức và biến đặc thù của query |
| Open projection | Projection infrastructure | Đối tượng đích và các giá trị mà projection cung cấp |
| `@Value` trên bean | Spring container | Cấu hình, bean và ngữ cảnh do container tạo |
| Chuyển đổi khi đọc entity | Mapping converter | Tài liệu hoặc nguồn dữ liệu và cơ chế constructor/property của store |

Ví dụ, một biến có sẵn trong query không đương nhiên xuất hiện trong biểu thức collection.

Tương tự, `target` trong một open projection không có nghĩa biểu thức mapping tên bảng cũng có một đối tượng `target` đại diện cho entity sắp lưu.

Không nên lấy một biểu thức chạy được trong projection rồi dán vào annotation mapping mà không xác định lại consumer và context.

## 9. Thời điểm đánh giá và caching quyết định hành vi

Một biểu thức đúng về cú pháp vẫn có thể sai về thiết kế nếu ứng dụng hiểu nhầm khi nào nó được đánh giá.

Cần phân biệt ít nhất ba loại dữ liệu được giữ lại:

1. **Chuỗi biểu thức gốc:** nội dung annotation.
2. **Biểu diễn đã parse:** có thể được tái sử dụng để tránh parse lại.
3. **Kết quả đánh giá:** có thể cố định hoặc thay đổi tùy consumer và vòng đời metadata.

Cache biểu diễn đã parse không đồng nghĩa cache kết quả.

Ngược lại, việc expression engine có thể đánh giá nhiều lần không bảo đảm store sẽ gọi nó cho mỗi entity hoặc mỗi request.

Những câu hỏi cần được trả lời bằng hợp đồng của module và kiểm chứng đường thực thi:

- Metadata được tạo lúc khởi động hay khi sử dụng lần đầu?
- Giá trị được tính một lần, cho mỗi thao tác hay ở một ranh giới khác?
- Có cache tên tài nguyên đã phân giải không?
- Những thao tác nào bỏ qua đường mapping mặc định?
- Refresh cấu hình có cập nhật bean và metadata liên quan không?

### 9.1. Tránh tên tài nguyên phụ thuộc trực tiếp vào đồng hồ

Biểu thức chọn collection hoặc index theo ngày hiện tại có thể trông thuận tiện, nhưng tạo ra ranh giới thời gian:

- Một thao tác bắt đầu trước nửa đêm và hoàn tất sau nửa đêm sẽ dùng tên nào?
- Đọc lại một entity cũ bằng repository sẽ tìm trong tài nguyên nào?
- Delete hoặc count có cùng quy tắc định tuyến không?
- Tài nguyên của ngày mới đã được chuẩn bị chưa?

Nếu dữ liệu cần phân vùng theo ngày sự kiện, “ngày hiện tại của máy chủ” chưa chắc là tiêu chí đúng.

Nên mô hình hóa khóa phân vùng và chọn đường truy cập có chủ đích. Annotation động chỉ phù hợp khi hợp đồng đánh giá thật sự đáp ứng thiết kế.

### 9.2. Tránh gọi I/O từ bean cung cấp tên

Getter trong biểu thức nên ngắn, có kết quả dễ dự đoán và không tạo phụ thuộc vòng.

Nếu bean cung cấp tên gọi repository để tìm collection, repository lại cần metadata collection để hoạt động, ứng dụng có thể tạo vòng phụ thuộc hoặc hành vi khó chẩn đoán.

Việc đánh giá metadata cũng không nên bất ngờ gọi mạng, ghi dữ liệu hoặc tạo tài nguyên.

## 10. Tenant động là một bài toán định tuyến đầy đủ

Biểu thức như:

~~~text
#{@tenantNames.currentOrders}
~~~

không tự tạo một hệ thống đa tenant hoàn chỉnh.

Trước khi sử dụng, cần có hợp đồng cho:

- Nguồn tenant và thời điểm tenant được xác thực.
- Cách ánh xạ tenant sang tên tài nguyên hợp lệ.
- Hành vi khi không có tenant.
- Phạm vi của bean và dữ liệu ngữ cảnh.
- Tính nhất quán giữa save, find, count, delete và transaction.
- Chuẩn bị index, schema hoặc tài nguyên cho từng tenant.

Đặc biệt, metadata có thể được dùng chung cho nhiều request. Không được mặc định một tên đã tính trong context của tenant A có thể được cache toàn cục rồi dùng cho tenant B.

Ngược lại, cũng không nên mặc định consumer luôn đánh giá lại tên với context mới.

### 10.1. ThreadLocal không tự áp dụng cho reactive context

Một bean đọc tenant từ `ThreadLocal` phụ thuộc vào luồng thực thi.

Trong ứng dụng reactive, tác vụ có thể chuyển luồng và tenant có thể được giữ trong cơ chế context khác. Một expression evaluator đồng bộ không tự nhìn thấy context của subscriber.

Nếu hạ tầng không cam kết hỗ trợ ngữ cảnh cần thiết, nên dùng cơ chế định tuyến được module hỗ trợ hoặc truyền lựa chọn tài nguyên tường minh ở tầng thao tác.

Không nên dùng giá trị mặc định âm thầm cho tenant thiếu nếu điều đó làm dữ liệu rơi vào một collection chung ngoài ý định.

## 11. Kiểu kết quả, null và tính hợp lệ của tên

Một expression đánh giá được chưa chắc tạo ra tên tài nguyên hợp lệ.

Các tình huống khác nhau cần được xử lý riêng:

| Tình huống | Ví dụ | Điều cần xác định |
| --- | --- | --- |
| Không tìm thấy property | `${app.orders.collection}` thiếu cấu hình | Có mặc định hay báo lỗi? |
| Không tìm thấy bean | `@collectionNames` chưa được đăng ký | Có lỗi context hoặc cấu hình scan không? |
| Không có thuộc tính | Bean không có getter tương ứng | Tên property trong biểu thức có đúng không? |
| Kết quả null | Getter trả về `null` | Consumer có từ chối hay dùng quy tắc riêng? |
| Chuỗi rỗng | Getter trả về `""` | Có phải tên hợp lệ hay có fallback? |
| Sai kiểu | Biểu thức trả một collection Java | Có chuyển đổi kiểu được hỗ trợ không? |
| Sai identifier | Tên chứa ký tự không được chấp nhận | Do chính sách ứng dụng hay giới hạn store? |

Không nên mặc định `null`, chuỗi rỗng và property không tồn tại có cùng hành vi.

Nếu tên tài nguyên bắt buộc phải có, nên kiểm tra cấu hình ở thời điểm sớm và báo lỗi rõ ràng.

Thông báo lỗi cần đủ để xác định property hoặc bean bị thiếu. Không cần đưa giá trị bí mật trong môi trường cấu hình vào log chỉ để giải thích một lỗi tên collection.

## 12. Giữ biểu thức trong phạm vi cấu hình được tin cậy

Biểu thức có khả năng gọi bean hoặc phương thức là một cơ chế mạnh hơn phép thay chuỗi đơn giản.

Ứng dụng nên sở hữu cấu trúc biểu thức trong mã nguồn hoặc cấu hình được quản lý. Đầu vào người dùng nên là dữ liệu được kiểm tra, không trở thành một biểu thức mới để đánh giá.

Ví dụ, người dùng chọn một loại dữ liệu:

~~~text
orders
archivedOrders
~~~

Ứng dụng có thể ánh xạ các khóa này sang một tập tên đã cho phép. Không cần nhận nguyên chuỗi `#{...}` từ request.

Có hai phép kiểm tra riêng:

1. Người dùng có quyền chọn tài nguyên đó không?
2. Tên tài nguyên có hợp lệ với chính sách đặt tên và store không?

Kiểm tra ký tự hợp lệ không thay thế kiểm tra quyền. Một collection khác có tên hoàn toàn hợp lệ vẫn có thể không thuộc phạm vi được phép truy cập.

Tương tự, cơ chế bind tham số query không tự bảo vệ việc chọn tên collection, index hoặc bảng nếu tên đó đến từ đầu vào không được kiểm soát.

## 13. Ảnh hưởng đến các abstraction dùng chung của Spring Data

### 13.1. CRUD và đường truy cập dữ liệu

Tên tài nguyên trong mapping có thể ảnh hưởng nhiều thao tác CRUD. Cần kiểm tra hành vi của từng API thực sự được dùng.

Một lời gọi template có tên collection được truyền tường minh có thể chọn tài nguyên khác với đường repository dùng metadata entity.

Nếu ứng dụng kết hợp cả hai cách, phải ghi rõ quy tắc. Không nên kỳ vọng biểu thức annotation ghi đè mọi tên tài nguyên đã được truyền trực tiếp.

### 13.2. Derived query

Derived query phân tích tên thuộc tính của domain model.

Việc collection được chọn bằng biểu thức không đổi `orderNumber` thành một tên Java khác và không thay thế quy tắc phân giải property path.

Cũng không bảo đảm mọi toán tử derived query đều được store hỗ trợ. Chọn tài nguyên và tạo điều kiện truy vấn là các bước có trách nhiệm khác nhau.

### 13.3. Phân trang và sắp xếp

`Pageable` và `Sort` không tự hợp nhất kết quả từ nhiều collection hoặc nhiều index.

Nếu biểu thức đổi tài nguyên theo tenant hay thời gian, một trang kết quả chỉ có ý nghĩa trong phạm vi mà đường truy vấn thực sự truy cập.

Muốn phân trang toàn cục qua nhiều phân vùng cần thiết kế truy vấn, thứ tự và cách ghép kết quả tương ứng. Annotation chọn tên không thực hiện công việc đó.

### 13.4. Projection

Biểu thức trong projection dùng để tạo giá trị hiển thị hoặc thuộc tính kết quả theo cơ chế projection được hỗ trợ.

Nó không tự quyết định tài nguyên lưu trữ của entity. Không nên lấy việc projection truy cập được một biến làm bằng chứng cho mapping expression.

### 13.5. Auditing

Auditing có thể gán người tạo và thời điểm tạo khi hạ tầng đã được bật đúng.

Nó không tự xác định collection của tenant, tạo index mới hoặc bảo đảm biểu thức tên tài nguyên có tenant hợp lệ.

Nếu tenant là một phần của dữ liệu nghiệp vụ, cần mô hình hóa và xác thực nó rõ ràng thay vì kỳ vọng metadata auditing giải quyết toàn bộ việc định tuyến.

### 13.6. Query by Example

Probe trong Query by Example mô tả dữ liệu cần đối sánh theo matcher và khả năng store.

Một field `tenantId` trong probe không mặc nhiên được cung cấp thành biến `#tenantId` cho biểu thức của annotation mapping. Hai cơ chế chỉ liên hệ khi có một đường tích hợp được thiết kế và hỗ trợ rõ ràng.

## 14. Kiểm chứng hỗ trợ theo từng thuộc tính

Khi đưa biểu thức mapping vào dự án, có thể lập một bảng ngắn:

| Mục | Ví dụ cần ghi nhận |
| --- | --- |
| Module và phiên bản | Spring Data MongoDB ở phiên bản dự án đang dùng |
| Annotation đầy đủ | `org.springframework.data.mongodb.core.mapping.Document` |
| Thuộc tính | `collection` |
| Cú pháp | SpEL template tham chiếu bean |
| Phụ thuộc | Bean `collectionNames` và property cấu hình |
| Kiểu kết quả | Chuỗi tên collection không rỗng |
| Phạm vi kết quả | Cố định theo cấu hình khởi động của ví dụ |
| Đường sử dụng | Repository và những template operation có liên quan |
| Cơ chế chuẩn bị tài nguyên | Index, mapping hoặc schema theo kế hoạch của store |

Sau đó kiểm chứng các tình huống có ý nghĩa:

- Cấu hình hợp lệ dẫn đến đọc và ghi đúng tài nguyên.
- Bean hoặc property bắt buộc bị thiếu tạo lỗi có thể nhận biết.
- Các thao tác count và delete theo cùng quy tắc với save và find.
- Đường template truyền tên tường minh có hành vi đã dự kiến.
- Các context đồng thời không làm lẫn tenant nếu có định tuyến động.
- Tài nguyên mới có index hoặc mapping cần thiết.
- Bản ghi cũ vẫn có đường truy cập khi cấu hình tên thay đổi.

Một kiểm tra chỉ gọi getter `getOrders()` không xác minh integration với mapping. Một kiểm tra chỉ parse chuỗi cũng không xác minh repository sử dụng kết quả.

Các ví dụ trong bài là mã minh họa và hướng dẫn kiểm chứng. Chúng không phải báo cáo đã chạy một store hoặc xác nhận cấu hình dự án cụ thể.

## 15. Chẩn đoán các lỗi thường gặp

| Biểu hiện | Khả năng cần xem xét | Hướng xử lý |
| --- | --- | --- |
| Tên tài nguyên chứa nguyên `#{...}` | Thuộc tính không được đánh giá hoặc đang đi qua consumer khác | Kiểm tra đúng annotation, package, thuộc tính và đường API |
| Placeholder không được thay | Consumer không hỗ trợ hoặc không có nguồn cấu hình | Kiểm tra cơ chế phân giải của điểm tích hợp đó |
| Không tìm thấy bean | Sai tên bean, thiếu cấu hình hoặc evaluator không có bean resolver | Kiểm tra context thực tế của mapping |
| Getter chạy nhưng tên không đổi | Kết quả đã được giữ lại hoặc đường thao tác chọn tên khác | Kiểm tra vòng đời metadata và đối số tường minh |
| Ghi đúng nhưng đọc không thấy | Hai đường truy cập chọn tài nguyên khác nhau | Đối chiếu tên đã phân giải cho từng thao tác |
| Sau đổi cấu hình thấy dữ liệu trống | Ứng dụng chuyển sang collection hoặc index mới | Xác định đường đọc dữ liệu cũ và kế hoạch chuyển đổi |
| Count hoặc delete khác find | Một API không theo cùng quy tắc định tuyến | Kiểm tra riêng đường thực thi của từng thao tác |
| Reactive không có tenant | Dùng ngữ cảnh dựa vào luồng hoặc thiếu tích hợp context | Chọn cơ chế định tuyến phù hợp với reactive pipeline |
| Tên index hợp lệ nhưng query lỗi | Tài nguyên hoặc mapping chưa được chuẩn bị | Kiểm tra vòng đời index ngoài bước đánh giá biểu thức |

Không nên xử lý mọi lỗi đánh giá bằng cách âm thầm trở về một tài nguyên mặc định. Điều đó có thể biến lỗi cấu hình thành việc đọc hoặc ghi sai nơi.

Cũng không nên xóa cache hoặc làm biểu thức phức tạp hơn trước khi xác định consumer nào đang xử lý annotation.

## 16. Tự kiểm tra kiến thức

**Vì sao một thuộc tính annotation kiểu String không tự hỗ trợ SpEL?**

Vì Java chỉ lưu chuỗi annotation trong metadata. Một consumer phải chủ động nhận diện và đánh giá nội dung đó.

**Spring Data Commons có làm mọi annotation mapping dùng được value expression không?**

Không. Commons cung cấp infrastructure; module và thuộc tính cụ thể quyết định cách tích hợp.

**MongoDB Document hỗ trợ biểu thức collection có chứng minh Field cũng hỗ trợ không?**

Không. Hợp đồng phải được kiểm tra theo từng thuộc tính và đúng phiên bản.

**Có thể dùng biến từ query trong mapping expression không?**

Chỉ khi consumer mapping cung cấp biến đó. Query, projection, bean configuration và mapping có các context riêng.

**Cache biểu thức có luôn làm tên tài nguyên cố định không?**

Không. Cache biểu diễn đã parse và cache kết quả đánh giá là hai việc khác nhau. Cần xác định consumer giữ lại loại nào và trong bao lâu.

**Đổi tên collection bằng cấu hình có tự chuyển dữ liệu cũ không?**

Không. Chọn một tài nguyên khác không tự di chuyển dữ liệu, tạo index hoặc cập nhật các đường truy cập viết tay.

**Điều gì cần nhớ khi mở rộng repository sử dụng metadata động?**

Xác định đúng store, thuộc tính annotation, ngữ cảnh, thời điểm đánh giá và phạm vi kết quả. Sau đó kiểm chứng các thao tác đọc, ghi và truy vấn thực sự dùng cùng hợp đồng tài nguyên.
