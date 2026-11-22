# Kiểm thử nested, geo và đồng thời theo nhu cầu

Spring Data Elasticsearch hỗ trợ nhiều kiểu dữ liệu và query chuyên biệt ngoài các field scalar thông thường. Một entity có thể chứa danh sách object cần được mapping là **nested**, vị trí địa lý cần được mapping là **geo_point**, hoặc dữ liệu có nhiều request cập nhật đồng thời cần cơ chế kiểm soát xung đột.

Các tính năng này không thể kiểm tra đầy đủ chỉ bằng unit test mock repository. Nested query phụ thuộc mapping thực tế; geo query phụ thuộc kiểu field và thứ tự tọa độ; optimistic concurrency phụ thuộc version metadata do Elasticsearch quản lý. Một integration test với Elasticsearch tương thích giúp xác nhận ứng dụng tạo mapping, gửi query và xử lý xung đột đúng như mong đợi.

Bài học này trình bày cách thiết kế test cho ba nhóm tình huống: nested object và nested query, dữ liệu địa lý và truy vấn khoảng cách, cùng cập nhật đồng thời. Mỗi phần đi từ mapping, dữ liệu mẫu, query đến assertion và các lỗi thường gặp.

## 1. Chọn đúng loại kiểm thử

Ba nhóm tính năng có thể kiểm tra ở nhiều cấp:

| Cấp kiểm thử | Nested | Geo | Đồng thời |
|---|---|---|---|
| Unit test | Kiểm tra service xây query và xử lý kết quả | Kiểm tra validate tọa độ, radius và criteria | Kiểm tra xử lý exception, retry policy |
| Context/repository test | Xác nhận repository và fragment được lắp ghép | Xác nhận converter và mapping bean được cấu hình | Xác nhận version metadata được mapping |
| Elasticsearch integration test | Xác nhận nested mapping và nested query thực tế | Xác nhận geo_point, distance và bounding box | Xác nhận version conflict, atomic update và retry |
| Load/concurrency test | Đo chi phí nested query với dữ liệu gần production | Đo query theo bán kính và mật độ điểm | Đo tranh chấp ghi, throughput và tỷ lệ conflict |

Unit test vẫn có ích, nhưng không thay thế integration test cho semantics của Elasticsearch. Một Query object được tạo đúng trong Java chưa chứng minh index có mapping phù hợp.

Không cần chạy load test nặng cho mọi thay đổi nhỏ. Bắt đầu bằng integration test xác định hành vi, sau đó bổ sung benchmark hoặc concurrency test khi workload và mức tranh chấp yêu cầu.

## 2. Dựng Elasticsearch cho integration test

Testcontainers có thể cung cấp một Elasticsearch node riêng cho test. Pin image version tương thích với Spring Data Elasticsearch và Elasticsearch Java API Client trong dự án. Không dùng tag latest vì behavior và compatibility có thể thay đổi.

Cấu trúc test thường dùng:

~~~java
@Testcontainers
@SpringBootTest
class ProductSearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
            )
        );

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.elasticsearch.uris",
            elasticsearch::getHttpHostAddress
        );
    }

    @Autowired
    ElasticsearchOperations operations;
}
~~~

Đây là cấu trúc minh họa. Chọn image tag theo version thực tế của dự án và cấu hình authentication/TLS theo cách container được khởi động. Nếu Spring Boot dùng property prefix hoặc kiểu endpoint khác ở release train của dự án, điều chỉnh DynamicPropertySource tương ứng.

Test cần tạo index và mapping trước khi ghi dữ liệu. Nên dùng index riêng hoặc dọn index test một cách an toàn để các test không phụ thuộc thứ tự chạy.

Ví dụ chuẩn bị index:

~~~java
@BeforeEach
void prepareIndex() {
    IndexOperations indexOperations =
        operations.indexOps(Product.class);

    if (indexOperations.exists()) {
        indexOperations.delete();
    }

    indexOperations.create();
    indexOperations.putMapping(
        indexOperations.createMapping(Product.class)
    );
}
~~~

Tên method và cách tạo mapping có thể khác giữa các phiên bản Spring Data Elasticsearch. Nếu ứng dụng quản lý index bằng template hoặc provisioning script, integration test nên dùng cùng mapping resource đó thay vì tạo mapping khác với production.

Sau khi lưu dữ liệu, refresh index trước search assertion:

~~~java
operations.indexOps(Product.class).refresh();
~~~

Không dùng Thread.sleep cố định để chờ search visibility. Refresh tường minh hoặc một điều kiện đồng bộ xác định giúp test ổn định hơn.

## 3. Mapping object array là nested

Giả sử một sản phẩm có nhiều biến thể. Mỗi variant gồm mã, màu và kích thước:

~~~json
{
  "id": "P-100",
  "name": "T-Shirt",
  "variants": [
    {
      "variantId": "V-1",
      "color": "black",
      "size": "S"
    },
    {
      "variantId": "V-2",
      "color": "white",
      "size": "L"
    }
  ]
}
~~~

Nếu variants được mapping là object array thông thường, Elasticsearch flatten field của các object trong mảng. Query có thể khớp color từ phần tử thứ nhất và size từ phần tử thứ hai, tạo ra kết quả không phản ánh một variant thực sự thỏa cả hai điều kiện.

Nếu cần giữ quan hệ giữa field trong cùng một phần tử, mapping phải là nested.

### Entity trong Spring Data Elasticsearch

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Nested)
    private List<Variant> variants;

    // constructors, getters and setters
}

public class Variant {

    @Field(type = FieldType.Keyword)
    private String variantId;

    @Field(type = FieldType.Keyword)
    private String color;

    @Field(type = FieldType.Keyword)
    private String size;

    // getters and setters
}
~~~

Field type Nested yêu cầu Elasticsearch index các object con theo nested semantics. Nếu mapping đã được tạo trước với type object, thay đổi annotation trong Java không tự chuyển mapping hiện tại thành nested. Cần tạo index mới hoặc migration phù hợp.

### Kiểm tra mapping thực tế

Sau khi tạo index, lấy mapping từ Elasticsearch và xác nhận field variants có type nested. Có thể dùng REST API:

~~~http
GET /products/_mapping
~~~

Phần mapping mong đợi có dạng:

~~~json
{
  "properties": {
    "variants": {
      "type": "nested",
      "properties": {
        "variantId": { "type": "keyword" },
        "color": { "type": "keyword" },
        "size": { "type": "keyword" }
      }
    }
  }
}
~~~

Integration test nên xác nhận mapping thật hoặc ít nhất chạy query nested trên index được tạo từ mapping ứng dụng. Chỉ kiểm tra annotation trên class không chứng minh index hiện tại có đúng mapping.

## 4. Tạo dữ liệu kiểm thử để phát hiện lỗi nested

Dữ liệu test phải có trường hợp mà object mapping và nested mapping cho kết quả khác nhau. Nếu mọi field đều nằm trong cùng một phần tử hoặc chỉ có một phần tử, test có thể không phát hiện việc mapping sai.

Seed hai variant khác nhau:

~~~java
Product product = new Product();
product.setId("P-100");
product.setName("T-Shirt");

Variant first = new Variant();
first.setVariantId("V-1");
first.setColor("black");
first.setSize("S");

Variant second = new Variant();
second.setVariantId("V-2");
second.setColor("white");
second.setSize("L");

product.setVariants(List.of(first, second));

operations.save(product);
operations.indexOps(Product.class).refresh();
~~~

Với dữ liệu này:

- Query tìm color black và size S trong cùng variant phải tìm thấy P-100.
- Query tìm color black và size L trong cùng variant không được tìm thấy P-100.
- Query riêng color black có thể tìm thấy P-100.

Điều kiện thứ hai là test quan trọng để phát hiện cross-object matching. Nếu query trả về P-100, mapping hoặc query có thể không dùng nested semantics như mong đợi.

## 5. Nested query phải nhóm điều kiện trong cùng nested object

Query đúng cho color black và size S:

~~~http
GET /products/_search
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "variants.color": "black"
              }
            },
            {
              "term": {
                "variants.size": "S"
              }
            }
          ]
        }
      }
    }
  }
}
~~~

Hai filter nằm trong cùng nested query nên phải được thỏa bởi cùng một nested object.

Query sai về mặt nghiệp vụ có thể là hai nested query độc lập trong bool must. Mỗi nested query có thể được thỏa bởi một child khác nhau, nên không bảo đảm cả color và size thuộc cùng variant.

### Kiểm thử trường hợp khớp

Với dữ liệu seed ở trên, query color black và size S phải trả P-100.

### Kiểm thử trường hợp không khớp chéo object

Query color black và size L phải trả không có P-100. Hai giá trị này tồn tại trong cùng parent document nhưng ở hai variant khác nhau.

Một test hữu ích:

~~~java
@Test
void nestedConditionsMustMatchSameVariant() {
    SearchHits<Product> hits =
        operations.search(
            queryForColorAndSize("black", "L"),
            Product.class
        );

    assertThat(hits.getSearchHits())
        .isEmpty();
}
~~~

Hàm queryForColorAndSize đại diện cho NativeQuery hoặc query builder được dự án sử dụng. Phần quan trọng của test là cả hai điều kiện được đặt bên trong một nested query.

## 6. Xây nested query bằng NativeQuery

Với Spring Data Elasticsearch hiện đại, NativeQuery có thể dùng Query builder của Elasticsearch Java API Client.

Ví dụ minh họa:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.nested(n -> n
        .path("variants")
        .query(nq -> nq.bool(b -> b
            .filter(f -> f.term(t -> t
                .field("variants.color")
                .value("black")
            ))
            .filter(f -> f.term(t -> t
                .field("variants.size")
                .value("S")
            ))
        ))
    ))
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Builder overload có thể thay đổi theo Elasticsearch Java API Client version. Hãy dùng API đúng dependency đang cài. Trong integration test, điều cần xác nhận là query JSON cuối cùng có một nested clause với path variants và hai điều kiện nằm trong cùng child scope.

Nếu dùng reactive operations, query có cùng semantics nhưng kết quả là Publisher như Flux<SearchHit<Product>>. Dùng StepVerifier để xác nhận kết quả và không gọi block trong reactive test.

## 7. Kiểm thử inner hits khi cần biết child nào khớp

Nested query có thể yêu cầu inner_hits để trả về nested object khớp điều kiện. Điều này hữu ích khi giao diện cần hiển thị đúng variant đã match thay vì chỉ biết parent product được tìm thấy.

Một test có thể xác nhận:

- Parent P-100 được trả về.
- Inner hit chỉ chứa variant V-1 khi query color black.
- Variant V-2 không xuất hiện trong inner hits của query đó.

Cấu hình inner_hits trong NativeQuery phụ thuộc Java API Client version. Nếu ứng dụng không sử dụng inner hits, không cần thêm assertion cho metadata này.

Không nhầm inner hits với danh sách variants đầy đủ trong entity. Entity content vẫn có thể chứa toàn bộ variants; inner hits là metadata về các nested child phù hợp với query.

## 8. Kiểm thử nested update khi nghiệp vụ cần

Nếu service cập nhật một variant cụ thể, test nên xác nhận chỉ child được chọn thay đổi. Elasticsearch update vẫn tác động document cha; nested child không có ID document độc lập.

Ví dụ dữ liệu có V-1 và V-2. Sau khi cập nhật stock hoặc trạng thái của V-2:

- V-2 có giá trị mới.
- V-1 giữ nguyên.
- Các field khác của parent không thay đổi.
- Search nested query cho giá trị mới trả đúng parent.

Với scripted update, kiểm tra cả trường hợp variant ID không tồn tại. Ứng dụng cần quyết định rõ đó là noop hay lỗi nghiệp vụ.

Một integration test có thể đọc lại parent theo ID sau update và kiểm tra từng phần tử. Nếu update response đã thành công nhưng search chưa thấy kết quả mới, phân biệt refresh visibility với việc update theo ID đã được áp dụng.

## 9. Mapping geo_point trong Spring Data Elasticsearch

Elasticsearch hỗ trợ field type geo_point để lưu vị trí địa lý. Một geo point có thể biểu diễn bằng object chứa lat/lon, array theo thứ tự longitude/latitude, hoặc string theo định dạng được hỗ trợ.

Ví dụ entity dùng GeoPoint của Spring Data:

~~~java
@Document(indexName = "stores")
public class Store {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @GeoPointField
    private GeoPoint location;

    // getters and setters
}
~~~

Trong các phiên bản có annotation GeoPointField, annotation này đánh dấu property là geo_point. Có thể dùng FieldType.GeoPoint theo cách mapping mà release train hỗ trợ. Kiểm tra package và annotation thực tế trong dependency của dự án.

Ví dụ tạo điểm:

~~~java
Store store = new Store();
store.setId("S-100");
store.setName("Central Store");
store.setLocation(
    new GeoPoint(10.7769, 106.7009)
);
~~~

Với GeoPoint của Spring Data, constructor thường nhận latitude rồi longitude. Đây là điểm dễ nhầm vì array trong JSON geo_point dùng thứ tự longitude rồi latitude.

### Kiểm tra mapping

Gọi mapping API và xác nhận location có type geo_point:

~~~http
GET /stores/_mapping
~~~

Không chỉ kiểm tra field Java có kiểu GeoPoint. Nếu index cũ đã tạo location thành object thông thường, geo query có thể lỗi hoặc không hoạt động như mong đợi.

## 10. Thứ tự tọa độ và dữ liệu địa lý

Geo point thường gặp các dạng:

Object:

~~~json
{
  "lat": 10.7769,
  "lon": 106.7009
}
~~~

Array:

~~~json
[106.7009, 10.7769]
~~~

String:

~~~text
10.7769,106.7009
~~~

Cần phân biệt thứ tự:

- Object: lat rồi lon theo tên field.
- Array: longitude trước, latitude sau.
- GeoPoint Java của Spring Data thường nhận latitude rồi longitude.

Test cần có tọa độ không đối xứng rõ ràng để phát hiện việc đảo lat/lon. Nếu dùng một điểm có hai giá trị gần nhau hoặc cả hai đều nằm trong miền hợp lệ, lỗi đảo có thể khó nhận ra.

Validate dữ liệu trước khi ghi:

- Latitude trong khoảng -90 đến 90.
- Longitude trong khoảng -180 đến 180.
- Giá trị không null nếu nghiệp vụ bắt buộc có vị trí.
- Xác định quy tắc cho vị trí thiếu hoặc không hợp lệ.
- Không coi một chuỗi địa chỉ là tọa độ nếu chưa geocode.

## 11. Kiểm thử geo distance query

Geo distance query tìm document nằm trong bán kính từ một điểm trung tâm.

Ví dụ tìm cửa hàng trong phạm vi 5 km:

~~~http
GET /stores/_search
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": {
        "lat": 10.7769,
        "lon": 106.7009
      }
    }
  }
}
~~~

Một integration test nên seed:

- Một cửa hàng rất gần tâm.
- Một cửa hàng ở gần ranh giới bán kính.
- Một cửa hàng rõ ràng nằm ngoài bán kính.
- Một document không có location nếu mapping/use case cho phép.

Test xác nhận điểm gần được trả về và điểm ngoài bán kính bị loại. Với điểm đúng sát biên, nên dùng tọa độ và radius có khoảng cách được tính rõ ràng, tránh sai số làm test không ổn định.

### Dùng NativeQuery

NativeQuery có thể xây geo distance query bằng Java API Client builder:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.geoDistance(g -> g
        .field("location")
        .distance("5km")
        .location(location -> location
            .lat(10.7769)
            .lon(106.7009)
        )
    ))
    .build();

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Tên kiểu GeoLocation và overload builder phụ thuộc client version. Nếu code không compile, kiểm tra API trong dependency và giữ nguyên semantics của geo_distance DSL.

### Kiểm tra đơn vị khoảng cách

Elasticsearch hỗ trợ đơn vị khoảng cách như m, km, mi và các đơn vị được tài liệu phiên bản hỗ trợ. Nên ghi đơn vị tường minh trong query, ví dụ 5km, thay vì dựa vào default.

Test nên xác nhận radius nhỏ hơn không trả về điểm xa và radius lớn hơn có thể bao gồm điểm đó. Không dùng chỉ một query với một kết quả để kết luận đơn vị đã đúng.

## 12. Kiểm thử geo bounding box

Bounding box tìm điểm nằm trong hình chữ nhật địa lý được xác định bởi góc trên trái và góc dưới phải.

Ví dụ:

~~~http
GET /stores/_search
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.80,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.70,
          "lon": 106.75
        }
      }
    }
  }
}
~~~

Test nên seed các điểm:

- Bên trong bounding box.
- Ngoài về phía bắc.
- Ngoài về phía nam.
- Ngoài về phía đông hoặc tây.

Kiểm tra tọa độ ở biên theo semantics Elasticsearch và cách tạo test data. Với khu vực băng qua đường đổi ngày quốc tế, bounding box có thể cần cách biểu diễn đặc biệt; không áp dụng ví dụ chữ nhật đơn giản cho mọi khu vực địa lý.

Geo bounding box là bộ lọc hình chữ nhật, không phải bán kính đường tròn. Nếu yêu cầu là “trong vòng 5 km”, dùng geo_distance.

## 13. Kiểm thử geo sorting và khoảng cách

Nếu kết quả cần sắp xếp theo khoảng cách từ người dùng, search request có thể dùng geo distance sort.

Một test nên xác nhận:

- Điểm gần hơn được xếp trước khi sort ascending.
- Điểm xa hơn đứng sau.
- Tọa độ tâm được truyền đúng.
- Document thiếu location được xử lý theo cấu hình missing sort value.
- Kết quả giữ sort values nếu API cần cursor pagination.

Không suy ra thứ tự gần nhất từ thứ tự document index. Search result mặc định không bảo đảm thứ tự nghiệp vụ nếu không có sort rõ ràng.

Nếu cần hiển thị khoảng cách, có thể đọc sort value hoặc tính toán ở ứng dụng. Không tự lấy score của search làm khoảng cách nếu query không định nghĩa score theo cách đó.

## 14. Kiểm thử đồng thời: lost update và version conflict

Hai request có thể cùng đọc một document, tính toán từ cùng trạng thái cũ rồi ghi lại. Nếu không có concurrency control, một thay đổi có thể ghi đè thay đổi còn lại.

Ví dụ:

~~~text
Initial stock = 10

Request A reads 10
Request B reads 10

Request A writes 8
Request B writes 7

Final stock = 7
~~~

Nếu nghiệp vụ kỳ vọng cả hai đơn hàng đã trừ 2 và 3, kết quả đúng phải là 5. Cách đọc-sửa-ghi tách rời có thể làm mất một cập nhật.

Elasticsearch hỗ trợ optimistic concurrency control dựa trên metadata version. Các cơ chế thường gặp:

- Version property được Spring Data hỗ trợ qua annotation @Version.
- Sequence number và primary term trong Elasticsearch.
- Update script thực hiện phép tính trực tiếp trên document hiện tại.
- Retry on conflict cho update script trong những trường hợp phù hợp.

Chọn cơ chế theo dạng nghiệp vụ. Không dùng một lần retry chung để che mọi xung đột.

## 15. Kiểm thử @Version trong Spring Data

Spring Data Elasticsearch hỗ trợ khai báo version property cho entity bằng annotation @Version trong các phiên bản phù hợp.

Ví dụ:

~~~java
@Document(indexName = "inventory")
public class Inventory {

    @Id
    private String id;

    private Integer stock;

    @Version
    private Long version;

    // getters and setters
}
~~~

Version metadata cho phép Spring Data phát hiện entity đã được đọc từ một phiên bản cũ khi ứng dụng ghi lại theo optimistic locking contract.

Kịch bản test:

1. Lưu Inventory lần đầu.
2. Đọc cùng document thành hai object A và B.
3. Cập nhật và lưu A thành công.
4. Thử lưu B với version cũ.
5. Xác nhận lần ghi B bị từ chối do version conflict.
6. Đọc lại document và xác nhận giá trị từ A vẫn còn.

Ví dụ cấu trúc:

~~~java
@Test
void rejectsSavingStaleVersion() {
    Inventory original = new Inventory();
    original.setId("SKU-1");
    original.setStock(10);

    Inventory saved = repository.save(original);

    Inventory firstRead =
        repository.findById(saved.getId()).orElseThrow();

    Inventory staleRead =
        repository.findById(saved.getId()).orElseThrow();

    firstRead.setStock(8);
    repository.save(firstRead);

    staleRead.setStock(7);

    assertThatThrownBy(() -> repository.save(staleRead))
        .isInstanceOf(OptimisticLockingFailureException.class);
}
~~~

Exception thực tế có thể được bọc bởi Spring Data hoặc client version. Integration test nên xác nhận exception type mà ứng dụng thực sự nhận và không chỉ bắt mọi RuntimeException.

Annotation @Version và cách mapping version có thể khác nhau giữa các release train. Kiểm tra tài liệu của dependency đang dùng trước khi dùng test này như contract.

### Điều test này chứng minh

Test chứng minh một entity có version cũ không thể ghi đè âm thầm phiên bản mới nếu optimistic locking được cấu hình đúng.

Nó không tự chứng minh nghiệp vụ retry an toàn. Khi conflict xảy ra, service phải quyết định đọc lại, tính lại, báo lỗi hoặc đưa thao tác vào luồng xử lý khác.

## 16. Kiểm thử sequence number và primary term

Elasticsearch cung cấp sequence number và primary term cho optimistic concurrency control ở mức request. Khi đọc document, client nhận metadata này. Khi ghi, client có thể yêu cầu chỉ thực hiện nếu document vẫn ở cùng seq_no và primary_term.

Ví dụ dùng Elasticsearch Java API Client:

~~~java
GetResponse<Inventory> firstRead =
    client.get(g -> g
        .index("inventory")
        .id("SKU-1"),
        Inventory.class
    );

long seqNo = firstRead.seqNo();
long primaryTerm = firstRead.primaryTerm();

client.update(u -> u
    .index("inventory")
    .id("SKU-1")
    .ifSeqNo(seqNo)
    .ifPrimaryTerm(primaryTerm)
    .doc(Map.of("stock", 8)),
    Inventory.class
);
~~~

Sau khi một request thành công, sequence number của document thay đổi. Một request thứ hai dùng seq_no và primary_term cũ phải nhận version conflict.

### Test stale write

1. Đọc document một lần, lưu seq_no và primary_term.
2. Gửi update đầu tiên với hai giá trị đó.
3. Gửi update thứ hai với cùng metadata cũ.
4. Xác nhận request thứ hai nhận conflict.
5. Đọc lại document và xác nhận update đầu tiên được giữ.

Cơ chế if_seq_no/if_primary_term bảo vệ quyết định ghi dựa trên snapshot đã đọc. Nó không tự merge hai thay đổi nghiệp vụ.

### Phân biệt với retry_on_conflict

- if_seq_no và if_primary_term nói rằng chỉ ghi nếu document vẫn ở đúng phiên bản đã đọc.
- retry_on_conflict yêu cầu Elasticsearch thử lại update script khi có conflict nội bộ trong quá trình update.

Nếu caller muốn ghi dựa trên trạng thái mới nhất, update script cộng/trừ có thể phù hợp. Nếu caller đã tính một giá trị dựa trên snapshot cũ, optimistic concurrency giúp phát hiện snapshot đã lỗi thời.

## 17. Kiểm thử update script nguyên tử

Với thao tác tăng hoặc giảm counter, có thể thực hiện phép toán bên trong update script để tránh chuỗi read-modify-write ở ứng dụng.

Ví dụ tăng số lượt đặt hàng:

~~~java
UpdateQuery query = UpdateQuery.builder("SKU-1")
    .withScript(
        "ctx._source.orderCount = " +
        "(ctx._source.orderCount == null ? 0 : ctx._source.orderCount) + params.delta"
    )
    .withParams(Map.of("delta", 1))
    .withLang("painless")
    .withRetryOnConflict(3)
    .build();

operations.update(
    query,
    IndexCoordinates.of("inventory")
);
~~~

Một integration test concurrency có thể gửi nhiều increment đồng thời rồi đọc lại giá trị. Nếu khởi tạo orderCount = 0 và có N update đều delta = 1, kết quả kỳ vọng là N nếu tất cả thao tác thành công.

### Không nhầm atomic update với idempotency

Script increment được thực hiện như một update trên document, nhưng nếu client timeout rồi gửi lại cùng nghiệp vụ, counter có thể tăng lần nữa. Retry on conflict xử lý conflict trong update; nó không biết hai request từ client có phải cùng một event hay không.

Nếu cần chống duplicate event, test phải mô phỏng gửi lại cùng event ID và xác nhận deduplication ở tầng ứng dụng hoặc trong thiết kế dữ liệu. Không thể chỉ dựa vào retry_on_conflict.

### Giới hạn của script

Script nên ngắn và dùng params. Không nối input vào source string. Với nghiệp vụ tồn kho, kiểm tra điều kiện không âm trong cùng script nếu Elasticsearch được dùng làm nơi thực hiện phép trừ. Nếu hệ thống cần transaction mạnh hoặc phối hợp nhiều tài nguyên, dùng database giao dịch làm nguồn sự thật.

## 18. Thiết kế concurrency test xác định

Concurrency test dễ flaky nếu dựa vào Thread.sleep để tạo race condition. Hãy dùng CountDownLatch, CyclicBarrier hoặc cơ chế đồng bộ rõ ràng để hai luồng đọc cùng một trạng thái trước khi ghi.

Kịch bản khái quát:

~~~text
Thread A                 Thread B
   |                         |
   +---- read version V -----+
   |                         |
   +---- wait at barrier ----+
   |                         |
   +---- update with V ------+
                             |
                             +---- update with V
                                  (one stale write conflicts)
~~~

Trong test thực tế:

- Tạo document ban đầu.
- Đọc hai bản sao với cùng version metadata.
- Dùng barrier để cả hai chỉ ghi sau khi đã đọc.
- Mỗi thread thử update với version đã đọc.
- Thu thập kết quả thành công và conflict.
- Xác nhận đúng một stale conditional write thành công nếu cả hai dùng cùng metadata.
- Đọc lại document để xác nhận trạng thái cuối.

Không assert thread A luôn thắng hoặc thread B luôn thắng. Scheduler không bảo đảm thứ tự. Assert số lượng thành công/conflict và invariant dữ liệu.

### Kiểm thử concurrency với reactive flow

Nếu ứng dụng dùng ReactiveElasticsearchOperations, có thể kết hợp nhiều Publisher bằng Mono.zip hoặc Flux.merge tùy semantics. Dùng StepVerifier để kiểm tra kết quả. Không gọi block trong event loop để ép hai request chạy đồng thời.

Cần phân biệt concurrency của test với concurrency thực tế của Elasticsearch. Hai Publisher được subscribe gần nhau chưa chắc đã đọc cùng version nếu không có bước đồng bộ rõ ràng.

## 19. Kiểm thử nested, geo và concurrency cùng một entity

Một entity có thể có nested variants, geo location và version:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<Variant> variants;

    @GeoPointField
    private GeoPoint location;

    @Version
    private Long version;
}
~~~

Khi đó, integration test có thể kiểm tra các hành vi độc lập:

- Nested query tìm đúng variant.
- Geo distance query tìm đúng product theo bán kính.
- Hai update dùng version cũ không ghi đè nhau.
- Update nested child làm version document cha thay đổi theo contract.
- Query search sau refresh trả dữ liệu mới.

Không nên gộp tất cả thành một test lớn khó chẩn đoán. Chia test theo hành vi, dùng một fixture chung nếu cần nhưng mỗi test có assertion rõ ràng.

Nếu cập nhật nested child thường xuyên và có nhiều request cạnh tranh, toàn bộ parent document vẫn là đơn vị update. Đây có thể là tín hiệu cần tách child thành document riêng nếu workload yêu cầu cập nhật độc lập.

## 20. Kiểm thử dữ liệu thiếu và biên

Các trường hợp biên thường phát hiện lỗi mapping hoặc query tốt hơn một test happy path đơn giản.

### Nested

- Parent không có variants.
- variants là mảng rỗng.
- Child thiếu field color hoặc size.
- Hai child có cùng variantId nếu nghiệp vụ không cho phép.
- Query chỉ có một điều kiện.
- Query nhiều điều kiện phải cùng match một child.
- Update child không tồn tại.

### Geo

- location null hoặc missing.
- Latitude ngoài [-90, 90].
- Longitude ngoài [-180, 180].
- Tọa độ bị đảo lat/lon.
- Điểm nằm ngay trong hoặc ngoài bán kính.
- Điểm nằm trên biên bounding box.
- Document không có geo field khi sort theo khoảng cách.

### Đồng thời

- Hai request ghi cùng version.
- Một request đọc sau khi request khác đã ghi.
- Update script chạy đồng thời.
- Conflict vượt quá số lần retry.
- Client timeout rồi replay cùng command.
- Document bị xóa giữa lúc đọc và ghi.
- Hai worker cập nhật field khác nhau trên cùng document.

Test nên xác nhận cả kết quả thành công và trạng thái lỗi theo policy của ứng dụng.

## 21. Kiểm thử mapping và query bằng Elasticsearch thật

Một số test chỉ cần Spring context, nhưng các test sau nên chạy với Elasticsearch thật:

| Hành vi | Vì sao cần integration test |
|---|---|
| Nested mapping và cross-object matching | Phụ thuộc cách Elasticsearch index nested documents |
| Nested query và inner hits | Phụ thuộc Query DSL và mapping |
| Geo distance/bounding box | Phụ thuộc geo_point mapping và semantics khoảng cách |
| Geo sort | Phụ thuộc Elasticsearch sort implementation |
| Version conflict | Phụ thuộc version metadata của document |
| if_seq_no/if_primary_term | Cần xác nhận conditional write thực tế |
| retry_on_conflict | Phụ thuộc update API và Painless execution |
| Refresh visibility | Phụ thuộc refresh lifecycle |

Mock chỉ xác nhận service gọi đúng method hoặc xây object. Nó không xác nhận server hiểu query như mong muốn.

## 22. Các lỗi thường gặp khi kiểm thử

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Nested query trả kết quả dù color và size nằm ở hai child khác nhau | Mapping là object hoặc các điều kiện nằm trong nested clause riêng | Dùng nested mapping và gom điều kiện vào cùng nested query |
| Nested query báo lỗi | Field chưa được mapping nested hoặc path sai | Kiểm tra index mapping và path |
| Annotation nested không đổi index hiện tại | Mapping Elasticsearch không thể đổi object thành nested tại chỗ | Tạo index mới và reindex |
| Geo query không trả điểm mong đợi | Field không phải geo_point hoặc tọa độ bị đảo | Kiểm tra mapping và thứ tự lat/lon |
| Geo distance dùng sai đơn vị | Radius thiếu hoặc sai unit | Ghi đơn vị tường minh như km hoặc m |
| Bounding box trả điểm ngoài dự kiến | Nhầm góc hoặc nhầm với radius query | Kiểm tra top_left/bottom_right và dùng đúng query |
| Stale entity ghi đè dữ liệu mới | Không dùng version/concurrency control | Dùng @Version hoặc seq_no/primary_term |
| Test concurrency lúc pass lúc fail | Dựa vào timing không xác định | Dùng barrier/latch và assert invariant |
| retry_on_conflict vẫn cộng counter hai lần | Client replay cùng nghiệp vụ sau timeout | Dùng event ID/deduplication |
| Test search không thấy update | Chưa refresh index | Refresh hoặc đọc theo ID |
| Testcontainers không tương thích | Image version lệch dependency | Pin version tương thích |
| Exception type khác dự kiến | Spring/client bọc exception theo version | Assert exception contract thực tế của release |

## 23. Checklist cho nested, geo và concurrency test

- [ ] Integration test dùng Elasticsearch version tương thích.
- [ ] Test tạo index và mapping thực tế trước khi seed data.
- [ ] Nested collection được mapping nested, không chỉ object.
- [ ] Dữ liệu seed có nhiều child với giá trị khác nhau.
- [ ] Có test phát hiện cross-object matching.
- [ ] Các điều kiện cần cùng child được đặt trong cùng nested query.
- [ ] Inner hits được kiểm tra nếu ứng dụng sử dụng.
- [ ] Geo field có mapping geo_point.
- [ ] Test dùng tọa độ không đối xứng để phát hiện đảo lat/lon.
- [ ] Test geo_distance với điểm trong và ngoài radius.
- [ ] Test bounding box theo các hướng và biên cần thiết.
- [ ] Geo sort được kiểm tra nếu là chức năng của ứng dụng.
- [ ] Entity version được mapping và stale write bị phát hiện.
- [ ] Có test if_seq_no/if_primary_term nếu ứng dụng dùng trực tiếp.
- [ ] Update script concurrency được kiểm tra với invariant rõ ràng.
- [ ] Không dùng sleep để tạo race condition.
- [ ] Phân biệt version conflict, retry và idempotency.
- [ ] Test refresh visibility và đọc theo ID khi phù hợp.
- [ ] Dữ liệu/index test được cô lập và dọn dẹp an toàn.

Nested, geo và đồng thời đều phụ thuộc semantics thực tế của Elasticsearch. Nested test phải chứng minh các điều kiện được áp dụng trên cùng child object; geo test phải xác nhận mapping và thứ tự tọa độ; concurrency test phải chứng minh stale write được phát hiện hoặc phép cập nhật nguyên tử giữ đúng invariant. Dùng unit test cho logic ứng dụng và integration test với Elasticsearch tương thích cho mapping, query và version behavior giúp phát hiện những lỗi mà mock không thể mô phỏng.

