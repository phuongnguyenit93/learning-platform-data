# Vector và biểu diễn embedding trong phiên bản có tính năng

`org.springframework.data.domain.Vector` là abstraction dùng chung để biểu diễn một vector số có số chiều cố định. Khi dùng với embedding, nó chứa các tọa độ do một model tạo ra để đại diện cho văn bản, hình ảnh hoặc dữ liệu khác trong một không gian vector.

Bài học thuộc chương **Kiểu dữ liệu dùng chung** của module **SPRING_DATA_COMMONS**. Trọng tâm là biểu diễn dữ liệu embedding trong Java, giới hạn theo phiên bản và ranh giới giữa Commons với model, store, driver và index tìm kiếm. Có một property kiểu Vector chưa đồng nghĩa repository đã có thể tìm kiếm ngữ nghĩa.

## 1. Xác định đúng phiên bản và đúng lớp

### 1.1. Vector của Spring Data có từ Commons 3.5

API chính thức ghi `org.springframework.data.domain.Vector` có từ **Spring Data Commons 3.5**. Các phiên bản cũ hơn không mặc nhiên có kiểu này; xem [Vector API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Vector.html).

Cần phân biệt các mốc của từng abstraction:

| Thành phần | Mốc được công bố trong API | Không được suy ra chỉ từ mốc này |
| --- | --- | --- |
| `Vector` | Commons 3.5 | Mọi store đều đọc/ghi và tìm kiếm vector |
| `SearchResults<T>` | Commons 4.0 | Repository của mọi mô-đun đều có cùng query vector |
| `Score` | Commons 4.0 | Score của mọi database có cùng thang đo |

Mốc của `SearchResults` và `Score` được nêu lần lượt trong [SearchResults API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/SearchResults.html) và [Score API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Score.html).

Vì vậy, không sao chép một ví dụ dùng toàn bộ API 4.x vào dự án 3.5 rồi kết luận rằng có Vector thì mọi kiểu liên quan cũng phải tồn tại.

Các ví dụ cơ bản trong bài dùng Java 17 trở lên và API Vector đã có trong Commons 3.5. Cấu hình runtime, framework và store phải tương thích với thế hệ thư viện thực tế của dự án.

### 1.2. Không nhầm với java.util.Vector

```java
import org.springframework.data.domain.Vector;
```

Đây là interface của Spring Data, không phải `java.util.Vector<E>`, vốn là một collection trong JDK.

Các khác biệt cần nhớ:

- Vector của Spring Data không khai báo generic như `Vector<Float>`.
- `size()` cho biết số chiều của một vector.
- Nó không phải danh sách để thêm phần tử tùy ý bằng `add(...)`.
- Nó không tự có API tạo embedding, chuẩn hóa hay tính mọi loại khoảng cách.

Dùng import tường minh giúp tránh IDE chọn nhầm lớp khi dự án cũng sử dụng các collection Java.

## 2. Embedding là gì và Vector giữ phần nào?

Một model embedding chuyển dữ liệu đầu vào thành một dãy số:

```text
Đoạn văn bản
    -> Quy trình tiền xử lý và model embedding
    -> Mảng số có d chiều
    -> Spring Data Vector
    -> Mapping của store và lưu trữ/index
```

Đối với truy vấn:

```text
Câu hỏi của người dùng
    -> Bộ mã hóa truy vấn tương thích
    -> Query vector
    -> Truy vấn trên store có hỗ trợ
    -> Nội dung phù hợp và thông tin xếp hạng
```

Vector chỉ biểu diễn phần dãy số. Nó không chứa sẵn model, tokenizer, luật chia đoạn, API key hoặc thuật toán tạo embedding.

Ví dụ ba chiều:

```text
[0.12, -0.34, 0.56]
```

Các số này chỉ dùng minh họa hình dạng dữ liệu, không phải kết quả thật của một model được chỉ định. Không nên diễn giải mặc định “chiều thứ nhất là giá”, “chiều thứ hai là chất lượng” như các cột nghiệp vụ độc lập.

Đối với embedding học được, một tọa độ riêng thường không có ý nghĩa công khai đơn giản như một field domain. Ý nghĩa tìm kiếm đến từ toàn bộ biểu diễn và quy tắc so sánh trong không gian mà model đã tạo.

## 3. Tạo Vector từ float, double hoặc collection

### 3.1. Tạo từ float

```java
import org.springframework.data.domain.Vector;

Vector embedding = Vector.of(
        0.12f,
        -0.34f,
        0.56f);

int dimensions = embedding.size(); // 3
```

Dấu `f` thể hiện literal float. Với pipeline tạo ra `float[]`:

```java
float[] values = {0.12f, -0.34f, 0.56f};

Vector embedding = Vector.of(values);
```

`Vector.of` sao chép dữ liệu từ mảng đầu vào. Nó không giữ mảng đó như một buffer để caller tiếp tục sửa tùy ý.

### 3.2. Tạo từ double

```java
Vector embedding = Vector.of(
        0.12d,
        -0.34d,
        0.56d);
```

Dùng double hay float là một quyết định biểu diễn số. Double không tự làm một embedding có “chất lượng ngữ nghĩa cao hơn” nếu thông tin nguồn, model hoặc index không thay đổi tương ứng.

### 3.3. Tạo từ collection số

```java
import java.util.List;

import org.springframework.data.domain.Vector;

Vector embedding = Vector.of(
        List.of(0.12f, -0.34f, 0.56f));
```

Overload collection nhận `Collection<? extends Number>`. Tuy vậy, khi pipeline đã có một kiểu số thống nhất, nên giữ rõ kiểu đó thay vì trộn nhiều loại Number rồi phụ thuộc vào chuyển đổi ngầm.

Cách tạo, sao chép nguồn và các overload cơ bản có thể đối chiếu với [Vector ở nhánh Commons 3.5](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/domain/Vector.java).

## 4. Số chiều là một phần của hợp đồng dữ liệu

`size()` không phải số tài liệu, số token hoặc số byte. Nó là số tọa độ của vector hiện tại.

Ví dụ:

```java
Vector a = Vector.of(0.1f, 0.2f, 0.3f);
Vector b = Vector.of(0.1f, 0.2f);

int aDimensions = a.size(); // 3
int bDimensions = b.size(); // 2
```

Mỗi instance có số chiều cố định, nhưng kiểu Vector không tự buộc mọi instance trong hệ thống phải cùng số chiều. Một index có thể yêu cầu một dimension nhất định trong khi factory vẫn tạo được một vector dimension khác.

Khi ghi và tìm kiếm, cần thống nhất:

| Thành phần | Điều cần thống nhất |
| --- | --- |
| Model hoặc cặp encoder tương thích | Sinh dữ liệu trong cùng không gian embedding |
| Cấu hình model | Số chiều đầu ra đúng theo cấu hình đã chọn |
| Dữ liệu đã lưu | Không trộn vector không tương thích trong cùng phạm vi tìm kiếm |
| Index | Dimension và biểu diễn số phù hợp |
| Query vector | Tương thích với tập dữ liệu được tìm |

**Cùng số chiều là điều kiện cần trong nhiều hệ thống, chưa phải điều kiện đủ.** Hai model khác nhau đều trả 768 chiều vẫn có thể tạo hai không gian không so sánh được.

Không cắt hoặc đệm số 0 tùy ý để làm một vector “khớp dimension”. Nếu model hỗ trợ một cơ chế giảm chiều cụ thể, phải sử dụng cơ chế đó đúng hợp đồng và áp dụng nhất quán cho dữ liệu, query và index.

## 5. Sao chép dữ liệu và đường truy cập unsafe

Vector nên được sử dụng như một giá trị không bị thay đổi sau khi tạo. Tuy nhiên, cần hiểu từng API liên quan tới mảng.

### 5.1. Vector.of tách khỏi mảng đầu vào

```java
float[] source = {0.1f, 0.2f, 0.3f};

Vector vector = Vector.of(source);
source[0] = 9.0f;

float first = vector.toFloatArray()[0]; // vẫn là 0.1f
```

Điều này hữu ích khi model client sử dụng một buffer mà caller còn có thể thay đổi sau đó.

### 5.2. Vector.unsafe chia sẻ mảng nguồn

```java
float[] source = {0.1f, 0.2f, 0.3f};

Vector vector = Vector.unsafe(source);
source[0] = 9.0f;

float first = vector.toFloatArray()[0]; // 9.0f
```

`unsafe` không sao chép mảng. Caller thay đổi mảng thì nội dung mà vector biểu diễn cũng thay đổi.

Không chọn đường này chỉ vì tên gọi gợi ý nhanh hơn. Chỉ sử dụng khi đã kiểm soát rõ quyền sở hữu buffer và vòng đời của nó. Một buffer bị dùng lại giữa các tác vụ có thể khiến vector đang chuẩn bị ghi không còn chứa dữ liệu ban đầu.

### 5.3. getSource không trả một bản sao bảo vệ

Các phương thức có mục đích khác nhau:

| API | Dữ liệu nhận được | Có thể sửa tùy ý mà không tác động vector? |
| --- | --- | --- |
| `toFloatArray()` | Biểu diễn mảng float dạng bản sao theo hợp đồng hỗ trợ | Có |
| `toDoubleArray()` | Biểu diễn mảng double dạng bản sao theo hợp đồng hỗ trợ | Có |
| `getSource()` | Nguồn của vector, không được sao chép | Không |
| `getType()` | Thông tin kiểu số nguồn | Không phải dữ liệu tọa độ |

Không ép `getSource()` thành `float[]` chỉ vì một model cụ thể thường trả float. Vector có thể có nguồn khác. `getType()` cũng không phải tên model hoặc mã phiên bản embedding.

Ví dụ implementation dựa trên float trả kiểu nguồn primitive `float.class`; không mặc định nó bằng `Float.class`. Có thể thấy chi tiết này trong [FloatVector implementation](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/domain/FloatVector.java).

API nguồn phục vụ những đường truy cập hiệu năng cần kiểm soát chặt. Nó không phải một cam kết rằng mọi đối tượng Vector bất biến sâu bất chấp cách caller sử dụng các đường truy cập đó.

## 6. Chuyển kiểu số không tạo thêm thông tin

Có thể chuyển biểu diễn:

```java
Vector original = Vector.of(0.123456789d, 0.987654321d);

float[] floatValues = original.toFloatArray();
double[] doubleValues = original.toDoubleArray();
```

Khi đổi double sang float, giá trị có thể bị làm tròn. Đổi ngược một giá trị float sang double không phục hồi những chữ số đã mất trước đó.

Một giá trị double hữu hạn nhưng quá lớn cho float cũng cần được xét trong chính sách chuyển đổi. Không chỉ kiểm tra dữ liệu trước chuyển kiểu rồi mặc định biểu diễn cuối cùng vẫn phù hợp.

Đối với vector binary hoặc quantized do một implementation chuyên biệt cung cấp, không mặc định luôn chuyển được sang mảng float hoặc double. Chúng có thể có hợp đồng biểu diễn riêng; API công bố khả năng hạn chế này.

Quy tắc sao chép và chuyển đổi số được mô tả trong [Vector API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Vector.html); cách chuyển double sang float của implementation phổ biến thể hiện trong [DoubleVector](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/domain/DoubleVector.java).

### 6.1. Kích thước dữ liệu tăng theo dimension

Chỉ xét payload tọa độ số:

```text
float:  khoảng 4 × d byte
double: khoảng 8 × d byte
```

Với d = 1536, mảng tọa độ float chiếm khoảng 6 KiB, double khoảng 12 KiB. Đây chỉ là ví dụ dung lượng, không phải dimension mặc định của Vector. Chưa tính object overhead, metadata, format truyền mạng và index.

Gắn embedding vào một entity có thể làm tăng dữ liệu đọc/ghi trong vòng đời entity. Nếu một màn hình chỉ cần id và tiêu đề, cân nhắc projection hoặc DTO phù hợp với khả năng truy vấn của store để tránh đưa toàn bộ embedding ra response.

## 7. Validation trước khi nhận embedding vào hệ thống

Không dùng `Vector.of` như một bộ kiểm tra đầy đủ cho dữ liệu của model hoặc index.

Cần phân biệt:

| Dữ liệu | Ý nghĩa |
| --- | --- |
| Tham chiếu null | Không có vector |
| Vector dimension 0 | Có đối tượng biểu diễn nhưng không có tọa độ |
| Vector N chiều toàn 0 | Có N tọa độ, nhưng có thể không hợp lệ cho phép đo đã chọn |
| Vector N chiều có NaN hoặc vô cực | Cần bị xử lý theo hợp đồng model, store và ứng dụng |
| Vector hợp lệ về số học | Vẫn cần kiểm tra model, dimension và không gian tương thích |

Một helper cho pipeline dùng mảng float có thể viết:

```java
import java.util.Objects;

import org.springframework.data.domain.Vector;

static Vector checkedFloatVector(
        float[] values,
        int expectedDimensions,
        boolean rejectZeroVector) {

    Objects.requireNonNull(values, "Embedding values required");

    if (expectedDimensions <= 0) {
        throw new IllegalArgumentException(
                "Expected dimensions must be positive");
    }

    if (values.length != expectedDimensions) {
        throw new IllegalArgumentException(
                "Embedding dimension mismatch");
    }

    boolean hasNonZero = false;

    for (float value : values) {
        if (!Float.isFinite(value)) {
            throw new IllegalArgumentException(
                    "Embedding values must be finite");
        }

        if (value != 0.0f) {
            hasNonZero = true;
        }
    }

    if (rejectZeroVector && !hasNonZero) {
        throw new IllegalArgumentException(
                "Zero vector is not accepted by this pipeline");
    }

    return Vector.of(values);
}
```

Đặt helper trong một lớp ứng dụng; caller cần giữ buffer ổn định trong lúc validation và sao chép. Tham số `rejectZeroVector` là chính sách của pipeline, không phải một quy tắc mà Vector tự áp dụng cho mọi use case.

Hàm này không tính L2 norm, không chuẩn hóa và không xác minh model đã tạo mảng. Nếu index hoặc scoring yêu cầu vector được chuẩn hóa theo một cách cụ thể, cần thực hiện hoặc kiểm tra bước đó riêng.

Không dùng vector toàn 0 để thay thế một lần gọi model thất bại. Trạng thái chưa có embedding, đang chờ tạo hoặc tạo lỗi nên được thể hiện riêng để không biến dữ liệu lỗi thành một điểm tìm kiếm có vẻ hợp lệ.

## 8. Lưu metadata của embedding cùng với dữ liệu cần thiết

Chỉ lưu dãy số sẽ khiến việc giải thích và nâng cấp dữ liệu khó hơn. Một mô hình Java minh họa:

```java
import java.time.Instant;

import org.springframework.data.domain.Vector;

record EmbeddingMetadata(
        String modelId,
        String modelRevision,
        int dimensions,
        String preprocessingVersion,
        String contentHash,
        Instant generatedAt) {
}

record DocumentChunk(
        String id,
        String content,
        Vector embedding,
        EmbeddingMetadata embeddingMetadata) {
}
```

Các record trên chỉ mô tả dữ liệu trong Java. Annotation mapping, schema, converter và index của store chưa được cấu hình chỉ bằng đoạn mã này.

Một số metadata có vai trò riêng:

| Metadata | Mục đích |
| --- | --- |
| Model ID và revision | Xác định thế hệ không gian embedding |
| Dimensions | Đối chiếu với vector và index |
| Preprocessing version | Theo dõi quy trình chia đoạn, chuẩn bị nội dung |
| Content hash hoặc version | Biết embedding tương ứng với nội dung nào |
| Generated at | Theo dõi thời điểm sinh vector |
| Chính sách normalization | Nếu có, cần được quản lý nhất quán trong cấu hình hoặc metadata phù hợp |

Model query và model tài liệu phải tạo các biểu diễn tương thích. Một số model có chế độ mã hóa riêng cho query và tài liệu; không đồng nhất “tương thích” với việc bắt buộc dùng cùng một chuỗi tiền xử lý bất kể hợp đồng của model.

### 8.1. Nội dung đổi thì embedding có thể đã lỗi thời

Nếu nội dung phiên bản 2 đã được lưu trong khi tác vụ tạo embedding cho phiên bản 1 mới hoàn thành, không gắn vector cũ vào nội dung mới như thể chúng khớp nhau.

Ứng dụng cần đối chiếu content version/hash và cơ chế cập nhật phù hợp. Metadata auditing chung có thể giúp theo dõi thay đổi, nhưng không tự chứng minh vector được sinh từ đúng phiên bản nội dung.

### 8.2. Nâng model là thay đổi dữ liệu, không chỉ thay tên cấu hình

Ngay cả khi model mới có cùng dimension, không tự trộn vector cũ và mới trong cùng một tập tìm kiếm mà chưa có chính sách tương thích.

Có thể cần tạo lại embedding, xây index tương ứng và chuyển luồng truy vấn khi dữ liệu đã sẵn sàng. Nếu model mới đổi dimension, việc đồng bộ càng phải rõ ở cả phía tài liệu và query.

## 9. Ranh giới giữa Commons, store và vector search

Có thể kiểm tra khả năng theo từng lớp:

| Lớp | Câu hỏi cần trả lời |
| --- | --- |
| Commons | Phiên bản có kiểu Vector và API liên quan không? |
| Store module | Có mapping/converter hoặc query vector được hỗ trợ không? |
| Driver | Có truyền đúng dạng dữ liệu mà database yêu cầu không? |
| Database | Có khả năng lưu và so sánh vector cần dùng không? |
| Index | Đúng property, dimension, kiểu biểu diễn và hàm đo chưa? |
| Ứng dụng | Có metadata, validation và phạm vi dữ liệu đúng không? |

Lưu được một mảng số chưa đồng nghĩa database đang lưu theo kiểu vector native. Lưu đúng kiểu vector cũng chưa đồng nghĩa đã có index phù hợp hoặc repository method có thể khai thác index đó.

Ví dụ, Spring Data MongoDB có tài liệu vector search riêng với yêu cầu về môi trường, index và tham số truy vấn của mô-đun. Điều đó minh họa vì sao phải xem [hướng dẫn vector search của store](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/vector-search.html), không suy ra hỗ trợ từ riêng interface Commons.

Nếu store chưa có query abstraction tương ứng trong phiên bản đang dùng, ứng dụng có thể cần một implementation repository mở rộng hoặc client truy vấn phù hợp. Không đặt một tên derived query có vẻ hợp lý rồi mặc định mọi store sẽ hiểu.

Query by Example cũng không tự biến phép đối chiếu một property Vector thành tìm kiếm láng giềng gần nhất. Phép bằng dữ liệu, phép lọc domain và truy vấn similarity là các hợp đồng khác nhau.

## 10. Embedding, scoring và kết quả truy vấn là các kiểu dữ liệu khác nhau

Vector biểu diễn một điểm. Score biểu diễn kết quả của việc so sánh hoặc đánh giá trong một truy vấn.

Ví dụ các cách đo thường gặp:

| Cách đo | Ý nghĩa tổng quát |
| --- | --- |
| Euclidean distance | Độ cách biệt theo khoảng cách trong không gian |
| Cosine similarity | Mức gần nhau về hướng của vector |
| Dot product | Tổng tích các tọa độ tương ứng |

Không mặc định score lớn luôn tốt hơn: distance và similarity có thể dùng hướng ưu tiên khác nhau, và store còn có thể biến đổi hoặc chuẩn hóa thang điểm.

Một vector không tự mang mọi thông tin scoring của một index. Đổi metric trong cấu hình có thể làm thay đổi cách diễn giải kết quả mà không đổi số chiều.

Ở thế hệ API có tính năng, Spring Data có các kiểu như `SearchResult<T>`, `SearchResults<T>`, `Score` và `Similarity`. Chúng tách phần nội dung domain khỏi thông tin xếp hạng; xem [Vector Search của Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/repositories/vector-search.html).

Không dùng `equals` của hai đối tượng Vector làm thay thế cho câu hỏi “hai nội dung có gần nhau về ngữ nghĩa không?”. Tìm kiếm gần đúng hoặc theo khoảng cách cần hợp đồng truy vấn và metric cụ thể.

Tương tự, top-k gần nhất không mặc nhiên là một `Page` có tổng số kết quả chính xác. Cách giới hạn, ngưỡng score, sắp xếp và phân trang phải theo khả năng store, không chỉ theo các kiểu CRUD quen thuộc.

## 11. Tổ chức một pipeline ứng dụng rõ ràng

Một cổng tạo embedding có thể được mô tả:

```java
interface EmbeddingClient {
    float[] embedDocument(String text);

    float[] embedQuery(String query);
}
```

Đây là interface do ứng dụng định nghĩa, không phải API có sẵn của Vector. Implementation gọi model hoặc thư viện tương ứng.

Luồng ghi dữ liệu có thể gồm:

```text
Chọn nội dung và phiên bản
    -> Tiền xử lý theo cấu hình model
    -> Sinh embedding
    -> Kiểm tra số chiều và giá trị
    -> Tạo Vector bằng factory phù hợp
    -> Gắn metadata
    -> Lưu bằng mapping của store
    -> Đảm bảo index phản ánh dữ liệu theo cơ chế của hệ thống
```

Luồng đọc tìm kiếm:

```text
Nhận query và xác định phạm vi dữ liệu hợp lệ
    -> Tạo query embedding tương thích
    -> Kiểm tra đầu ra
    -> Truy vấn vector theo khả năng store
    -> Áp dụng đúng giới hạn và chính sách truy cập
    -> Chuyển kết quả thành DTO cần thiết
```

Một kết quả “gần nhất” không thay thế điều kiện tenant hay quyền đọc. Nếu store hỗ trợ lọc trước khi tìm gần nhất, cần thiết kế đúng đường lọc đó; nếu lọc sau top-k, ứng dụng có thể còn ít hơn k kết quả và không được giả vờ đã trả cùng một tập tìm kiếm.

Các nguyên tắc này thuộc kiến trúc sử dụng dữ liệu. Vector không tự thực hiện các bước pipeline.

## 12. Các tình huống cần xác nhận trong ứng dụng

| Tình huống | Điều cần quan sát |
| --- | --- |
| Dự án dùng Commons trước 3.5 | Không giả định import Vector tồn tại |
| Có Vector nhưng dùng API tìm kiếm 4.x trong 3.5 | Phát hiện khác biệt phiên bản của từng kiểu |
| Model trả khác dimension | Từ chối hoặc xử lý theo chính sách trước khi ghi/tìm |
| Cùng dimension nhưng khác model không tương thích | Không trộn ngầm trong cùng không gian tìm kiếm |
| Buffer nguồn đổi sau Vector.of | Vector vẫn giữ dữ liệu đã sao chép |
| Buffer nguồn đổi sau Vector.unsafe | Nhận biết nội dung được chia sẻ đã thay đổi |
| Dữ liệu có NaN hoặc vô cực | Xử lý trước khi đưa vào store theo chính sách |
| Vector toàn 0 hoặc rỗng | Không nhầm với embedding hợp lệ chỉ vì tạo được đối tượng |
| Chuyển double sang float | Xác nhận độ chính xác và tính hữu hạn của kết quả |
| Nội dung đổi trong lúc tạo embedding | Không gắn kết quả của phiên bản cũ vào nội dung mới |
| Mapping lưu được nhưng chưa có index | Không kết luận đã có truy vấn vector hiệu quả |
| Response chỉ cần thông tin tóm tắt | Không tải hoặc gửi embedding nếu không cần và store cho phép tối ưu |

Vector tạo một ngôn ngữ biểu diễn thống nhất cho dãy số embedding ở tầng Spring Data. Để dùng đúng, cần giữ đồng bộ không gian model, dimension, kiểu số, quyền sở hữu mảng và khả năng lưu/truy vấn của toàn bộ đường dữ liệu.
