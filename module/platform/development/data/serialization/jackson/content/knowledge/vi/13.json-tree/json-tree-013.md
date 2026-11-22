# Kiểm tra chi phí bộ nhớ của cây theo kích thước tài liệu

Khi dùng Jackson để đọc JSON thành `JsonNode`, ứng dụng tạo một cây object trong heap. Cây này giữ lại cấu trúc object/array, tên field và các giá trị để code có thể truy cập ngẫu nhiên, duyệt nhiều lần hoặc sửa dữ liệu. Đổi lại, bộ nhớ cần dùng thường lớn hơn đáng kể so với số byte của file JSON ban đầu.

Muốn đánh giá chi phí bộ nhớ chính xác, không thể chỉ lấy kích thước file rồi nhân với một hệ số cố định. Hai tài liệu JSON có cùng số byte nhưng hình dạng rất khác nhau có thể tạo ra số lượng object Java và cấu trúc collection khác nhau. Cần xem xét số node, độ dài chuỗi, số field trong object, số phần tử array, kiểu số, phiên bản JDK/Jackson và cách đo.

## 1. Kích thước JSON và kích thước cây trong heap là hai đại lượng khác nhau

Ví dụ file JSON:

```json
{
  "id": 101,
  "name": "An",
  "active": true
}
```

File trên chỉ chứa các ký tự UTF-8 và dấu phân cách JSON. Khi Jackson tạo cây, dữ liệu được biểu diễn bằng nhiều object Java:

```text
ObjectNode
  |
  +-- Map<String, JsonNode> chứa các field
        |
        +-- String "id"      -> IntNode(101)
        +-- String "name"    -> TextNode("An")
        +-- String "active"  -> BooleanNode(true)
```

Sơ đồ mô tả ý tưởng về cấu trúc object tree; chi tiết lưu trữ nội bộ có thể thay đổi theo phiên bản Jackson.

Kích thước file JSON đo số byte được lưu hoặc truyền. Kích thước cây đo bộ nhớ heap của các object Java được tạo ra và còn được giữ tham chiếu. Cây cần thêm chi phí cho object header, reference, collection, entry, array nội bộ, `String` và các node giá trị.

Vì vậy:

- File JSON 1 MB không có nghĩa cây `JsonNode` chỉ chiếm 1 MB heap.
- Hai file cùng kích thước có thể tạo cây có dung lượng khác nhau.
- Nếu đầu vào đang nằm trong một `String`, chuỗi đầu vào có thể cùng tồn tại với cây trong lúc xử lý, làm tăng peak memory.
- Sau khi bỏ tham chiếu đến chuỗi nguồn, bộ nhớ của chuỗi có thể được thu hồi khi GC chạy; cây vẫn còn nếu ứng dụng giữ root node.

## 2. Những thành phần tạo nên chi phí bộ nhớ của cây

Một cây JSON gồm nhiều loại node. Mỗi loại có cấu trúc và chi phí khác nhau.

### 2.1. ObjectNode và các thuộc tính

`ObjectNode` biểu diễn một JSON object. Trong các phiên bản Jackson Databind phổ biến, object node giữ các thuộc tính bằng một map nội bộ có khả năng bảo toàn thứ tự. Map cần lưu key, value, entry/bucket và mảng tham chiếu bên trong.

Ví dụ:

```json
{
  "userId": 101,
  "displayName": "An",
  "enabled": true,
  "address": {
    "city": "Ho Chi Minh City",
    "country": "Vietnam"
  }
}
```

JSON object này tạo một `ObjectNode` gốc, một `ObjectNode` lồng nhau và nhiều entry cho các thuộc tính. Mỗi tên field là một chuỗi được map sử dụng làm key. Vì thế, object có rất nhiều field có thể tốn bộ nhớ đáng kể ngay cả khi value của chúng ngắn.

Chi phí của object còn phụ thuộc số lượng field và cách map mở rộng dung lượng. Map thường cấp phát mảng có sức chứa theo ngưỡng tăng trưởng, nên dung lượng cấp phát không nhất thiết đúng bằng số entry đang có.

### 2.2. ArrayNode và phần tử

`ArrayNode` biểu diễn JSON array. Nó giữ các node con theo thứ tự, thường thông qua một danh sách dựa trên mảng tham chiếu.

```json
[
  10,
  20,
  30,
  40
]
```

Array cần một node cho cấu trúc array và vùng lưu reference đến các phần tử. Các phần tử có thể là scalar node hoặc object/array node lồng nhau. Một array chứa hàng triệu giá trị nhỏ vẫn có thể tốn nhiều bộ nhớ do số lượng node và reference, dù văn bản JSON khá gọn.

### 2.3. TextNode và String

Giá trị JSON string thường được biểu diễn bằng `TextNode`, giữ một `String` Java. Bộ nhớ phụ thuộc độ dài chuỗi, encoding nội bộ của JDK và object overhead.

Trên JDK 8, `String` thường sử dụng `char[]`; từ JDK 9, Compact Strings có thể lưu nội dung Latin-1 bằng `byte[]` khi phù hợp. Vì vậy, cùng một JSON text có thể có footprint khác nhau giữa các phiên bản JDK.

Chuỗi dài làm tăng bộ nhớ nội dung. Rất nhiều chuỗi ngắn lại làm tăng số lượng object header và reference. Một tài liệu chứa nhiều field name và string value có thể tốn bộ nhớ lớn hơn tài liệu chứa các giá trị số đơn giản với cùng số byte.

### 2.4. Các node số và boolean/null

Jackson có các lớp node chuyên biệt như `IntNode`, `LongNode`, `DoubleNode`, `DecimalNode`, `BooleanNode` và `NullNode`. Kiểu node phụ thuộc token và cách Jackson biểu diễn giá trị.

- Số nguyên nhỏ có thể được biểu diễn bằng node chứa primitive `int` hoặc `long`.
- Số thập phân chính xác có thể cần `BigDecimal`, với chi phí object và phần dữ liệu số riêng.
- Boolean và null có thể dùng instance dùng chung trong một số lớp node của Jackson.
- Một số node số có thể có cơ chế cache tùy loại và phiên bản.

Không nên giả định mọi scalar đều luôn tạo đúng một object mới, cũng không nên giả định tất cả scalar đều dùng chung một instance. Khi ước lượng thực tế, hãy đo trên đúng phiên bản Jackson mà ứng dụng sử dụng.

### 2.5. Độ sâu và cấu trúc lồng nhau

JSON lồng nhiều tầng tạo thêm node object/array và các reference nối chúng. Ví dụ một object có một array gồm các object con có chi phí khác với một object phẳng chứa cùng số lượng scalar.

Độ sâu lớn không nhất thiết luôn chiếm nhiều heap hơn số lượng node lớn, nhưng có thể làm tăng chi phí traversal, stack hoặc nguy cơ vượt giới hạn nesting. Cần theo dõi cả số node tổng, độ sâu lớn nhất và kích thước dữ liệu scalar.

## 3. Mô hình ước lượng bộ nhớ

Có thể mô tả gần đúng chi phí cây như sau:

```text
Heap của cây ≈
    kích thước các JsonNode
  + kích thước các container object/array
  + key String của object
  + String và object giá trị
  + mảng reference, map entry và dung lượng dự phòng
```

Đây là mô hình để nhận diện nguồn chi phí, không phải công thức cho ra một số byte chính xác. Mỗi object Java còn có object header, alignment và reference; các yếu tố này phụ thuộc JVM, kiến trúc, compressed oops, object alignment và JDK.

Một cách nhìn khác là phân rã theo hình dạng tài liệu:

| Đặc điểm JSON | Thành phần thường làm tăng chi phí |
|---|---|
| Nhiều object với nhiều field | ObjectNode, map, entry, key String |
| Array rất lớn | ArrayNode, danh sách và reference cho từng phần tử |
| Nhiều string dài | TextNode, String và vùng lưu nội dung |
| Nhiều số thập phân | DecimalNode và BigDecimal |
| Cấu trúc lồng nhau sâu/rộng | Nhiều node container và reference |
| Input đang là String | Chuỗi nguồn có thể tồn tại song song với cây |

Không có một tỷ lệ cố định như “cây luôn lớn gấp 3 lần JSON”. Tỷ lệ thực tế thay đổi theo dữ liệu và runtime. Với object nhiều field ngắn, overhead collection có thể chiếm phần đáng kể. Với payload có nhiều string dài, phần nội dung chuỗi có thể chiếm ưu thế.

## 4. Phân biệt shallow size, retained size và allocation

Khi đọc kết quả profiler, cần hiểu ba khái niệm khác nhau:

- **Shallow size:** dung lượng của chính một object, không tính các object mà nó tham chiếu.
- **Retained size:** dung lượng có thể được thu hồi nếu object đó và các object chỉ còn được giữ bởi nó không còn reachable. Đây là chỉ số hữu ích để đánh giá cây đang giữ lại bao nhiêu heap.
- **Allocation size/rate:** số byte được cấp phát trong một thao tác hoặc trong một đơn vị thời gian. Một thao tác parse có thể cấp phát nhiều object tạm thời dù không giữ tất cả chúng sau khi hoàn tất.

Ví dụ, shallow size của `ObjectNode` không bao gồm map nội bộ và toàn bộ node con. Nếu chỉ đo shallow size của root, kết quả sẽ đánh giá thấp rất nhiều bộ nhớ của cây.

Ngược lại, tổng allocation trong lúc parse không đồng nghĩa với retained heap sau parse. Parser, buffer hoặc object tạm có thể được thu hồi sau khi thao tác hoàn tất. Nếu cần biết ứng dụng đang giữ cây lớn đến đâu, hãy đo retained size hoặc heap sau khi các tham chiếu không cần thiết đã được giải phóng.

## 5. Đo kích thước tài liệu đầu vào

Trước khi đo cây, ghi lại kích thước JSON nguồn bằng byte. Với file:

```java
long inputBytes = Files.size(Path.of("large-document.json"));
```

Nếu dữ liệu đang là `String`, `String.length()` trả về số UTF-16 code unit, không phải số byte UTF-8 trên wire. Muốn biết kích thước UTF-8:

```java
byte[] utf8 = json.getBytes(StandardCharsets.UTF_8);
int utf8Bytes = utf8.length;
```

Không nên tạo thêm một bản sao byte array lớn chỉ để đo trong đường chạy production nếu không cần thiết. Với benchmark, có thể tính trước kích thước input trong setup để không đưa chi phí mã hóa vào phép đo parse.

Hãy ghi rõ số byte đang đo là:

- Kích thước file trên đĩa.
- Kích thước byte payload nhận qua network.
- Kích thước UTF-8 của chuỗi JSON.
- Hay số ký tự/code unit trong `String` Java.

Các con số này không thể dùng thay thế nhau.

## 6. Đo object graph bằng Java Object Layout (JOL)

JOL là công cụ của OpenJDK giúp xem layout object trên JVM. `ClassLayout` đo shallow layout của một object; `GraphLayout` duyệt object graph reachable từ root và tổng hợp footprint của các object trong graph.

Thêm dependency `jol-core` vào project đo đạc (không nhất thiết đưa vào dependency production):

```groovy
dependencies {
    implementation("org.openjdk.jol:jol-core:<version>")
}
```

Ví dụ đo cây Jackson:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.openjdk.jol.info.GraphLayout;

ObjectMapper mapper = new ObjectMapper();
JsonNode root = mapper.readTree(json);

GraphLayout graph = GraphLayout.parseInstance(root);

System.out.println(graph.toFootprint());
System.out.println("Graph bytes: " + graph.totalSize());
```

`toFootprint()` cho biết phân bố object theo class, ví dụ có bao nhiêu `ObjectNode`, `ArrayNode`, `TextNode`, `String`, map entry hoặc array. `totalSize()` cung cấp tổng footprint của graph được duyệt.

Để thấy khác biệt giữa shallow và graph size:

```java
System.out.println(ClassLayout.parseInstance(root).toPrintable());
System.out.println(GraphLayout.parseInstance(root).toFootprint());
```

Đoạn đầu chỉ xem layout của root node; đoạn sau xem graph reachable. Đừng dùng `ClassLayout` của root như tổng bộ nhớ cây.

### 6.1. Những giới hạn khi dùng JOL

JOL hữu ích cho phân tích cấu trúc nhưng kết quả không phải toàn bộ chi phí bộ nhớ của process:

- Nó đo object graph reachable từ root được truyền vào, không tính mọi buffer và object tạm của parser nếu chúng không còn reachable từ root.
- Object dùng chung có thể được tính trong graph theo cách duyệt của JOL; cần hiểu root nào đang được đo và các tham chiếu dùng chung.
- Kết quả phụ thuộc JDK, JVM flags, compressed references và alignment.
- Nó không đại diện cho fragmentation, vùng heap đã reserve, metaspace, native memory hoặc chi phí toàn bộ runtime.

Hãy dùng JOL để hiểu thành phần nào tạo footprint, rồi đối chiếu với heap profiler khi cần biết tác động ở cấp ứng dụng.

## 7. Dùng heap histogram và heap dump

Khi ứng dụng đang chạy, có thể dùng công cụ của JDK để xem lớp nào chiếm nhiều heap.

### 7.1. GC class histogram

Với process Java có PID là `<pid>`:

```bash
jcmd <pid> GC.class_histogram
```

Histogram liệt kê số instance và tổng shallow bytes theo class. Nếu cây JSON chiếm nhiều bộ nhớ, có thể thấy số lượng lớn các lớp như `ObjectNode`, `ArrayNode`, `TextNode`, `String`, `LinkedHashMap$Entry`, `ArrayList` hoặc array reference.

Histogram hữu ích để biết class nào có số lượng lớn, nhưng không tự trả lời object nào đang giữ chúng. Một số class như `String` có thể được nhiều thành phần khác nhau sử dụng.

### 7.2. Heap dump và dominator tree

Có thể tạo heap dump:

```bash
jcmd <pid> GC.heap_dump heap.hprof
```

Mở file trong Eclipse Memory Analyzer (MAT), VisualVM hoặc công cụ tương đương. Dùng histogram để tìm các node Jackson, sau đó xem dominator tree và retained size để xác định root hoặc thành phần ứng dụng nào đang giữ cây lớn.

Ví dụ, nếu một cache giữ `JsonNode` của nhiều tài liệu và không có giới hạn dung lượng, retained heap có thể tăng theo số tài liệu được lưu. Trong trường hợp đó, chi phí không chỉ đến từ một cây lớn mà còn từ số lượng cây sống đồng thời.

Heap dump có thể chứa nội dung JSON, chuỗi, token hoặc dữ liệu nghiệp vụ nhạy cảm. Hãy lưu và chia sẻ file dump theo quy trình bảo vệ dữ liệu của tổ chức.

## 8. Dùng JFR để quan sát allocation trong lúc parse

Java Flight Recorder (JFR) ghi nhận sự kiện runtime, bao gồm allocation của object. Có thể dùng JFR để xem thao tác parse tạo ra những loại object nào và tốc độ cấp phát ra sao.

Ví dụ khởi động ứng dụng với recording:

```bash
java -XX:StartFlightRecording=filename=json-tree.jfr,settings=profile -jar app.jar
```

Mở recording bằng Java Mission Control và xem allocation events hoặc allocation profile. Tập trung vào giai đoạn parse JSON lớn; các class Jackson, collection, String và array có thể xuất hiện trong profile.

JFR trả lời câu hỏi về allocation trong quá trình chạy. Nó không thay thế retained-size analysis: object được cấp phát rồi thu hồi nhanh vẫn có thể tạo allocation rate cao nhưng không còn chiếm heap sau đó.

## 9. Đo allocation bằng JMH

Nếu cần so sánh parse thành cây với một cách xử lý khác, hãy dùng JMH thay vì đo bằng `System.nanoTime()` trong một vòng lặp tùy ý. JMH xử lý warmup, measurement iteration và fork để giảm ảnh hưởng của JIT cũng như trạng thái JVM.

Ví dụ benchmark đơn giản:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
public class JsonTreeBenchmark {
    private final ObjectMapper mapper = new ObjectMapper();
    private final String json = loadFixture();

    @Benchmark
    public void parseTree(Blackhole blackhole) throws Exception {
        JsonNode root = mapper.readTree(json);
        blackhole.consume(root);
    }
}
```

Chuỗi JSON và fixture được tạo ở setup hoặc trước benchmark để thời gian tạo input không bị tính chung với thời gian parse. `Blackhole` ngăn kết quả bị loại bỏ như một phép tính không có tác dụng.

Chạy benchmark với GC profiler:

```bash
java -jar benchmarks.jar JsonTreeBenchmark -prof gc
```

Các chỉ số allocation/op và GC rate giúp so sánh chi phí cấp phát giữa các cách xử lý. Đây vẫn là allocation của thao tác benchmark, không phải retained size của một cây được lưu lâu dài.

Nếu mục tiêu là đo retained heap của nhiều cây cùng tồn tại, cần một thí nghiệm riêng: parse một số lượng tài liệu xác định, giữ root node trong collection có chủ đích, bỏ tham chiếu đến input khi không cần, rồi chụp heap dump và đo retained size. Không dùng kết quả allocation/op để kết luận trực tiếp rằng một cây đơn lẻ giữ lại đúng từng ấy byte.

## 10. Thiết kế thí nghiệm theo kích thước và hình dạng JSON

Để hiểu bộ nhớ tăng thế nào theo kích thước tài liệu, hãy chuẩn bị nhiều fixture có quy mô khác nhau và nhiều hình dạng dữ liệu.

| Bộ fixture | Đặc điểm cần cô lập |
|---|---|
| Object phẳng | Tăng số field nhưng giữ value ngắn |
| Array số | Tăng số phần tử scalar |
| Array object | Tăng số object node và map entry |
| String dài | Tăng độ dài nội dung string |
| Object lồng nhau | Tăng số container và độ sâu |
| Số thập phân | Tăng số `DecimalNode`/`BigDecimal` |

Ví dụ ma trận kích thước:

```text
Fixture A: 100 KB JSON
Fixture B: 500 KB JSON
Fixture C:   1 MB JSON
Fixture D:   5 MB JSON
Fixture E:  10 MB JSON
```

Đây chỉ là các mức mẫu để thiết kế phép đo; hãy chọn kích thước phù hợp với tải thật. Với mỗi fixture, ghi lại:

1. Kích thước byte của JSON nguồn.
2. Số lượng object, array, field, phần tử và string.
3. Độ sâu tối đa.
4. Số node và phân bố node theo class nếu có thể đo.
5. Graph footprint hoặc retained size của root.
6. Allocation/op, thời gian parse và GC activity nếu dùng benchmark.

Giữ cố định JDK, Jackson version, JVM flags, cấu hình mapper và cách tạo input. Chạy nhiều lần sau warmup. Không so sánh số đo lấy từ hai máy có heap layout hoặc JDK khác nhau mà không ghi rõ môi trường.

## 11. Tách peak memory khỏi retained memory

Khi parse một JSON lớn, peak memory có thể cao hơn nhiều so với retained size của cây sau khi parse xong.

Ví dụ luồng đọc từ `String`:

```text
JSON String trong heap
       |
       v
JsonParser + buffer tạm
       |
       v
JsonNode tree được tạo dần
       |
       v
Ứng dụng giữ root node
```

Trong giai đoạn tạo cây, chuỗi JSON nguồn, parser buffer, object tạm và cây mới có thể cùng tồn tại. Sau khi parse xong và không còn tham chiếu đến input, parser hoặc buffer, GC có thể thu hồi một phần bộ nhớ. Nếu ứng dụng giữ cả chuỗi JSON và cây, cả hai tiếp tục chiếm heap.

Vì vậy cần phân biệt:

- **Peak heap:** lượng heap lớn nhất cần trong lúc đọc và xử lý.
- **Retained tree heap:** lượng heap cây tiếp tục giữ sau parse.
- **Allocation volume:** tổng object/byte được cấp phát trong quá trình parse, bao gồm cả object tạm.

Đối với service có giới hạn bộ nhớ, peak heap và số cây sống đồng thời thường quan trọng không kém kích thước một cây riêng lẻ.

## 12. Ước lượng tác động khi xử lý nhiều tài liệu

Giả sử một worker giữ đồng thời `N` cây JSON. Nếu trung bình mỗi cây có retained size `T`, phần heap dành cho các cây có thể ước lượng ban đầu là:

\[
H_{trees} \approx N \times T
\]

Đây chỉ là phép ước lượng tuyến tính để lập ngân sách. Trong ứng dụng thật còn có object wrapper, cache, queue, request context, input buffer, thread stack, framework và dữ liệu nghiệp vụ khác.

Ví dụ, nếu phép đo trên dữ liệu đại diện cho thấy một cây giữ khoảng 8 MB và một batch giữ 20 cây, phần cây có thể chiếm khoảng 160 MB trước khi tính các thành phần khác. Con số này chỉ có ý nghĩa khi 8 MB được đo trên đúng JDK, Jackson version và cấu trúc dữ liệu tương ứng.

Khi hệ thống xử lý theo batch, hãy giới hạn số tài liệu giữ cùng lúc, giải phóng tham chiếu sau khi xử lý, và tránh cache cây không giới hạn. Nếu tài liệu lớn hơn nhiều so với ngân sách heap, cần cân nhắc streaming thay cho tree model.

## 13. So sánh tree model với streaming model

Tree model thuận tiện khi cần truy cập field bất kỳ, thay đổi node hoặc duyệt dữ liệu nhiều lần. Nhưng nó phải giữ toàn bộ cấu trúc đã parse trong heap.

Streaming API (`JsonParser`/`JsonGenerator`) xử lý từng token. Nếu ứng dụng chỉ cần đọc một số field hoặc xử lý từng record trong array rồi bỏ qua, có thể không cần giữ toàn bộ tài liệu.

| Tiêu chí | Tree model (`JsonNode`) | Streaming API |
|---|---|---|
| Truy cập ngẫu nhiên | Thuận tiện | Không trực tiếp; phải tiến parser đến token cần đọc |
| Sửa cấu trúc JSON | Có thể thao tác node | Thường phải ghi lại luồng hoặc xây dựng cấu trúc riêng |
| Bộ nhớ giữ dữ liệu | Tăng theo toàn bộ cây | Có thể gần với buffer và trạng thái xử lý hiện tại nếu xử lý tuần tự |
| Xử lý tài liệu rất lớn | Có thể gây áp lực heap | Phù hợp hơn nếu không cần giữ toàn bộ tài liệu |
| Code xử lý | Thường ngắn và trực quan | Chi tiết hơn, phải quản lý trạng thái token |

Streaming không tự động bảo đảm bộ nhớ hằng số. Nếu ứng dụng đọc token rồi lưu mọi record vào một `List`, bộ nhớ vẫn tăng theo tổng dữ liệu được giữ. Lợi ích xuất hiện khi code xử lý xong từng phần và giải phóng dữ liệu tương ứng.

## 14. Một số nguyên tắc giảm chi phí bộ nhớ

### 14.1. Chỉ tạo cây khi cần thao tác trên toàn cấu trúc

Nếu chỉ cần lấy `id`, `status` và một vài giá trị khác, streaming parser hoặc deserialize thẳng vào DTO có thể tiết kiệm bộ nhớ hơn tạo `JsonNode` cho toàn bộ tài liệu.

### 14.2. Giới hạn kích thước đầu vào và độ sâu

Đặt giới hạn kích thước request, độ sâu lồng nhau và số phần tử phù hợp với nghiệp vụ. Jackson có `StreamReadConstraints` trong các phiên bản hỗ trợ để giới hạn một số đặc điểm của input, như độ dài string/number và nesting depth. Cần chọn giới hạn phù hợp với phiên bản Jackson và hợp đồng dữ liệu.

### 14.3. Tránh giữ cây trong cache không giới hạn

Nếu cần cache `JsonNode`, hãy đặt giới hạn số entry hoặc dung lượng, TTL và chính sách eviction. Cây JSON thường giữ nhiều object nhỏ; cache hàng nghìn cây có thể làm heap tăng nhanh.

### 14.4. Giải phóng tham chiếu đúng vòng đời

Khi xử lý xong, không giữ root node trong static field, collection dài hạn hoặc callback không cần thiết. Java GC thu hồi object khi không còn reachable; không cần và không nên cố gọi `System.gc()` sau mỗi tài liệu.

### 14.5. Đo trên dữ liệu có hình dạng giống production

Fixture chỉ gồm số nhỏ không đại diện cho payload chứa nhiều text hoặc object lồng nhau. Hãy đo trên dữ liệu đã ẩn danh nhưng giữ phân bố kích thước và cấu trúc tương tự tải thật.

## 15. Quy trình đo thực tế

Một quy trình có thể áp dụng trong project:

1. Chọn các JSON fixture đại diện cho tài liệu nhỏ, trung bình và lớn.
2. Ghi kích thước nguồn theo byte UTF-8 hoặc byte file.
3. Parse bằng đúng `ObjectMapper` và cấu hình đang chạy production.
4. Dùng JOL để xem footprint của graph root và phân bố class.
5. Nếu cần xác định cây nào đang giữ heap, chụp heap dump và xem retained size/dominator tree bằng MAT.
6. Nếu cần đo allocation hoặc so sánh tốc độ, tạo benchmark JMH và dùng GC profiler.
7. Lặp lại với object phẳng, array lớn, string dài và object lồng nhau.
8. Ước lượng số cây có thể sống đồng thời, rồi so với ngân sách heap và headroom cho peak memory.
9. Nếu tree model vượt ngân sách hoặc tạo GC pressure lớn, chuyển luồng xử lý phù hợp sang DTO hoặc streaming API.

Không kết luận chỉ từ một lần chạy hoặc một tỷ lệ giữa file size và heap size. Kết quả phải gắn với fixture, JDK, Jackson version, JVM flags và cách đo cụ thể.

## 16. Ghi nhớ

Chi phí bộ nhớ của `JsonNode` phụ thuộc vào số lượng node, số field, số phần tử array, độ dài string, kiểu số, cấu trúc lồng nhau và overhead của collection/object trên JVM. Kích thước JSON trên đĩa hoặc trên network chỉ là kích thước đầu vào, không dự đoán chính xác retained heap của cây.

Hãy phân biệt shallow size, retained size, allocation và peak memory. Dùng JOL để xem object graph, heap histogram/dump để tìm object đang giữ heap, JFR để quan sát allocation khi chạy và JMH để so sánh các cách parse. Đo bằng dữ liệu đại diện trên đúng runtime, sau đó tính số cây có thể sống đồng thời. Khi ứng dụng không cần truy cập toàn bộ cấu trúc, streaming hoặc deserialize trực tiếp vào DTO thường giúp giảm lượng dữ liệu phải giữ trong heap.
