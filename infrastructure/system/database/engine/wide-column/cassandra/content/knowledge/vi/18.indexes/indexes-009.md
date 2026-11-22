# Truy vấn vector/ANN qua SAI khi phiên bản hỗ trợ

## Mục tiêu và phạm vi

Trong Apache Cassandra, **Storage-Attached Indexing (SAI)** cho phép truy vấn dữ liệu qua chỉ mục gắn với cơ chế lưu trữ. Từ **Apache Cassandra 5.0**, khả năng tìm kiếm vector (*vector search*) sử dụng SAI để thực hiện truy vấn **Approximate Nearest Neighbor (ANN)**: tìm những vector gần vector truy vấn nhất theo một hàm đo độ tương đồng hoặc khoảng cách. Đây là một cách xây dựng tìm kiếm ngữ nghĩa, gợi ý nội dung hay truy hồi tài liệu cho ứng dụng Java ngay trên dữ liệu Cassandra.

Chủ đề này thuộc chương **Chỉ mục** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Kiến thức liên quan gồm mô hình wide-column, partition key, thiết kế bảng theo truy vấn, replication, consistency level, compaction, repair và kết nối Java. SAI bổ sung đường truy vấn theo vector; nó không loại bỏ sự cần thiết của thiết kế partition key và kiểm soát chi phí trong hệ phân tán.

Sau bài này, bạn sẽ có thể:

- Xác định **điều kiện phiên bản** trước khi dùng CQL `VECTOR` và `ANN OF`.
- Phân biệt *embedding*, phép đo độ giống, truy vấn ANN và chỉ mục SAI.
- Tạo bảng có `vector<float, N>`, lập chỉ mục SAI, nạp dữ liệu và truy vấn top-k bằng CQL.
- Kết hợp lọc theo thuộc tính thông thường với tìm kiếm vector khi truy vấn được hỗ trợ.
- Kết nối từ Java bằng `CqlVector<Float>` và `PreparedStatement`, đồng thời nhận diện giới hạn về độ chính xác, độ trễ và vận hành.

## 1. Kiểm tra phiên bản trước khi chạy ví dụ

**Không phải mọi phiên bản Cassandra đều hỗ trợ truy vấn ANN qua SAI.** Tài liệu chính thức của Apache Cassandra giới thiệu SAI và vector search trong nhánh **5.0**. Với Cassandra 4.x hoặc phiên bản cũ hơn, không thể giả định cú pháp dưới đây sẽ chạy; cần nâng cấp sang bản hỗ trợ hoặc chọn một hệ thống tìm kiếm vector tương thích khác. Bản Cassandra do nhà cung cấp quản lý có thể có giới hạn hoặc cú pháp khác; hãy đối chiếu tài liệu của đúng hệ thống đang triển khai.

| Thành phần | Cần có |
| --- | --- |
| Server | Apache Cassandra **5.0 trở lên** với tính năng SAI/vector search khả dụng; kiểm tra phiên bản thực tế trên các node. |
| Dữ liệu | Cột `VECTOR<FLOAT, N>` có số chiều `N` cố định. |
| Chỉ mục | SAI trên đúng cột vector, ví dụ `CREATE INDEX ... USING 'sai'`. |
| Truy vấn | `SELECT ... ORDER BY embedding ANN OF [...] LIMIT k`. |
| Ứng dụng Java | Java Driver 4.x **có hỗ trợ kiểu vector**; API `CqlVector` đã xuất hiện từ driver 4.16 và được cải tiến ở 4.17. |

Trên một node đã kết nối bằng `cqlsh`, có thể kiểm tra:

~~~sql
SELECT release_version FROM system.local;
~~~

Kết quả chỉ phản ánh node được hỏi. Trong cluster đang rolling upgrade, cần xác nhận phiên bản/tính năng ở **toàn bộ cụm** và quy trình nâng cấp trước khi bật truy vấn mới trên môi trường sản xuất. Không dùng việc client có Java Driver mới làm bằng chứng rằng server đã hỗ trợ vector.

> Các ví dụ CQL bên dưới nhắm vào Apache Cassandra 5.0 có SAI/vector search. Nếu cú pháp báo lỗi trong một bản cài đặt cụ thể, kiểm tra phiên bản server, khả năng tương thích driver và tài liệu phiên bản đó trước khi sửa câu lệnh.

## 2. Embedding, SAI và ANN có vai trò gì?

**Embedding** là một dãy số thực được mô hình học máy tạo ra để biểu diễn văn bản, ảnh hoặc đối tượng. Hai nội dung gần nghĩa thường tạo ra các vector có quan hệ hình học gần nhau theo một phép đo được chọn. Cassandra **lưu và tìm kiếm** những vector này; Cassandra không tự biến nội dung tiếng Việt thành embedding chỉ vì ta tạo cột `vector`.

Ví dụ cho bài học, một vector ba chiều được biểu diễn:

~~~text
Tài liệu A: [1.00, 0.00, 0.00]
Tài liệu B: [0.95, 0.05, 0.00]
Tài liệu C: [0.00, 1.00, 0.00]
Truy vấn Q: [1.00, 0.00, 0.00]
~~~

Với một cách đo độ giống phù hợp, A và B gần Q hơn C. Các số trên là dữ liệu **minh họa hình học**, không phải embedding ngữ nghĩa thực sự. Trong sản phẩm, tài liệu và câu hỏi phải được mã hóa bằng **cùng một mô hình embedding tương thích**, cùng số chiều và cùng quy trình tiền xử lý.

Ba thành phần khác nhau:

| Thành phần | Nhiệm vụ |
| --- | --- |
| `VECTOR<FLOAT, N>` | Lưu một vector số thực có **chính xác N phần tử** trong một cột CQL. |
| **SAI vector index** | Tạo cấu trúc chỉ mục cục bộ gắn với dữ liệu Cassandra để tìm ứng viên gần nhau hiệu quả. |
| **ANN query** | Truy vấn một tập kết quả top-k **xấp xỉ gần nhất** theo vector đầu vào. |

ANN đánh đổi một phần **recall** để giảm công tìm kiếm so với việc tính chính xác khoảng cách từ câu hỏi tới mọi vector. Vì vậy, thứ tự hoặc tập kết quả ANN không nhất thiết giống phép tính toàn bộ dữ liệu (*exact nearest neighbor*). `LIMIT 5` nghĩa là lấy tối đa năm kết quả tìm được, không phải bảo đảm năm hàng toàn cục đúng tuyệt đối theo khoảng cách.

~~~mermaid
flowchart LR
    A["Văn bản/tài liệu"] --> B["Mô hình embedding"]
    B --> C["Cột VECTOR"]
    C --> D["SAI vector index"]
    Q["Câu hỏi mới"] --> E["Cùng mô hình embedding"]
    E --> F["Vector truy vấn"]
    F --> G["CQL ANN OF"]
    D --> G
    G --> H["Top-k kết quả gần nhất"]
    H --> I["Ứng dụng Java xử lý kết quả"]
~~~

## 3. Thực hành CQL: tạo bảng, chỉ mục, nạp dữ liệu

Các ví dụ dùng keyspace `vector_lab` để dễ chạy bằng `cqlsh` trên môi trường **thử nghiệm một node**. `SimpleStrategy` và replication factor 1 chỉ dành cho lab; sản xuất nên dùng `NetworkTopologyStrategy` và cấu hình RF phù hợp datacenter.

~~~sql
CREATE KEYSPACE IF NOT EXISTS vector_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE vector_lab;

CREATE TABLE IF NOT EXISTS documents_semantic (
    doc_id uuid PRIMARY KEY,
    tenant_id text,
    title text,
    content text,
    embedding_model text,
    embedding vector<float, 3>
);
~~~

Giải thích thiết kế:

- `doc_id` là **partition key** của bảng; Cassandra phân phối các bản ghi theo token của nó, tránh gom toàn bộ tài liệu của mọi khách hàng vào một partition lớn.
- `tenant_id` dùng để giới hạn phạm vi tìm kiếm theo tổ chức/khách hàng. Muốn lọc cột này mà không có partition key trong điều kiện, ta cần một chỉ mục phù hợp.
- `embedding_model` cho biết vector được tạo bởi phiên bản mô hình nào; không nên trộn vector từ các mô hình không tương thích vào cùng một tập so khớp.
- `vector<float, 3>` có ba chiều **chỉ để bài thực hành ngắn gọn**. Trong thực tế, `N` phải khớp số chiều đầu ra của mô hình. Apache Cassandra 5.0 giới hạn vector tối đa **8192 chiều**, nhưng cần đối chiếu giới hạn ở bản triển khai thực tế.

Tạo SAI trên cột vector và trên cột `tenant_id`:

~~~sql
CREATE INDEX IF NOT EXISTS documents_embedding_sai
ON documents_semantic (embedding)
USING 'sai'
WITH OPTIONS = {'similarity_function': 'COSINE'};

CREATE INDEX IF NOT EXISTS documents_tenant_sai
ON documents_semantic (tenant_id)
USING 'sai';
~~~

`similarity_function` quyết định cách so khớp trong chỉ mục. Các lựa chọn được tài liệu Cassandra nêu gồm `COSINE`, `DOT_PRODUCT` và `EUCLIDEAN`; `COSINE` là giá trị mặc định trong nhánh tài liệu tham chiếu. Nên chọn hàm theo cách mô hình embedding được huấn luyện và chuẩn hóa. Không coi điểm số từ các hàm khác nhau là có cùng thang ý nghĩa.

Nạp dữ liệu ví dụ:

~~~sql
INSERT INTO documents_semantic
    (doc_id, tenant_id, title, content, embedding_model, embedding)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'team-a', 'Giới thiệu Cassandra', 'Cassandra phân tán dữ liệu theo khóa phân vùng.',
    'demo-3d-v1', [1.0, 0.0, 0.0]
);

INSERT INTO documents_semantic
    (doc_id, tenant_id, title, content, embedding_model, embedding)
VALUES (
    22222222-2222-4222-8222-222222222222,
    'team-a', 'Chọn partition key', 'Partition key ảnh hưởng phân phối và truy vấn.',
    'demo-3d-v1', [0.95, 0.05, 0.0]
);

INSERT INTO documents_semantic
    (doc_id, tenant_id, title, content, embedding_model, embedding)
VALUES (
    33333333-3333-4333-8333-333333333333,
    'team-a', 'Repair trong Cassandra', 'Repair giúp đồng bộ dữ liệu giữa các replica.',
    'demo-3d-v1', [0.0, 1.0, 0.0]
);

INSERT INTO documents_semantic
    (doc_id, tenant_id, title, content, embedding_model, embedding)
VALUES (
    44444444-4444-4444-8444-444444444444,
    'team-b', 'Tài liệu khách hàng khác', 'Dữ liệu thuộc tenant khác.',
    'demo-3d-v1', [0.99, 0.01, 0.0]
);
~~~

Nếu index được tạo **sau khi** dữ liệu đã tồn tại, quá trình lập chỉ mục ban đầu có thể tiêu tốn CPU, I/O và thời gian. Cần theo dõi trạng thái chỉ mục trước khi đánh giá kết quả, đặc biệt trên bảng lớn.

## 4. Cú pháp truy vấn ANN và điểm tương đồng

Tìm ba tài liệu gần vector `[1.0, 0.0, 0.0]` nhất:

~~~sql
SELECT doc_id, tenant_id, title
FROM documents_semantic
ORDER BY embedding ANN OF [1.0, 0.0, 0.0]
LIMIT 3;
~~~

Phần `ORDER BY embedding ANN OF [...]` yêu cầu tìm láng giềng gần theo chỉ mục vector. Đây **không** phải phép sắp xếp clustering key thông thường (`ORDER BY ... ASC/DESC`). Cột vector phải có chỉ mục SAI thích hợp. `LIMIT` là phần quan trọng của truy vấn top-k; trong tài liệu Apache Cassandra 5.0, `LIMIT` cho vector search **không vượt quá 1000**.

Nếu muốn trả thêm điểm cosine để hiển thị hoặc phân tích:

~~~sql
SELECT doc_id, title,
       similarity_cosine(embedding, [1.0, 0.0, 0.0]) AS score
FROM documents_semantic
ORDER BY embedding ANN OF [1.0, 0.0, 0.0]
LIMIT 3;
~~~

CQL có các hàm tính điểm như `similarity_cosine`, `similarity_dot_product` và `similarity_euclidean` cho vector. Trong ví dụ, **chỉ mục dùng COSINE và điểm hiển thị cũng dùng cosine**. Nếu chỉ mục cấu hình `DOT_PRODUCT` nhưng ứng dụng hiển thị `similarity_cosine`, không thể suy ra thứ tự kết quả luôn phản ánh thứ tự của cột điểm hiển thị.

Lưu ý khi đọc kết quả:

- Đây là **ANN**, nên với tập dữ liệu nhỏ ta có thể thấy tài liệu A và B gần vector hỏi, nhưng không nên viết kiểm thử yêu cầu đúng một thứ tự cố định trong mọi cấu hình hay mọi thời điểm.
- Tăng `LIMIT` có thể tăng chi phí truy vấn; không dùng `LIMIT 1000` như mặc định nếu giao diện chỉ cần 5 đến 20 gợi ý.
- Không có truy vấn “tìm những vector **ít giống nhất**” đối xứng với ANN theo cùng cú pháp.
- `SELECT *` có thể đưa cả vector dài vào mạng; chỉ trả những trường giao diện cần, chẳng hạn ID, tiêu đề và điểm.
- Số điểm gần nhau chỉ là tín hiệu xếp hạng. Ứng dụng vẫn cần xác thực quyền đọc và có thể dùng thêm bước *reranking* theo nghiệp vụ.

## 5. Lọc theo tenant/thuộc tính và thiết kế bảng

Nếu ứng dụng phục vụ nhiều khách hàng, trả dữ liệu của `team-b` khi người dùng `team-a` tìm kiếm là sai nghiêm trọng. Câu truy vấn nên gắn điều kiện phạm vi:

~~~sql
SELECT doc_id, title,
       similarity_cosine(embedding, [1.0, 0.0, 0.0]) AS score
FROM documents_semantic
WHERE tenant_id = 'team-a'
ORDER BY embedding ANN OF [1.0, 0.0, 0.0]
LIMIT 3;
~~~

Trong bảng ở mục 3, `tenant_id` có **SAI riêng**, nên có thể dùng làm bộ lọc cùng tìm kiếm ANN ở các bản hỗ trợ dạng truy vấn này. Với bộ lọc khác như `category`, `published` hoặc `language`, phải xem cột đó có thể truy vấn qua khóa chính hay chỉ mục phù hợp không. Đừng thêm tùy tiện `ALLOW FILTERING` để che dấu việc thiếu đường truy vấn hiệu quả.

Cần phân biệt hai vấn đề:

1. **Đúng chức năng:** `WHERE tenant_id = 'team-a'` chỉ định các hàng hợp lệ trong phạm vi trả kết quả; việc xác thực quyền truy cập của người dùng vẫn thuộc trách nhiệm ứng dụng và kiến trúc bảo mật.
2. **Hiệu năng:** Chỉ mục SAI có thể hỗ trợ tìm kiếm theo thuộc tính ngoài partition key, nhưng vẫn có chi phí phân phối truy vấn và lọc kết quả trên cluster. Truy vấn qua khóa phân vùng thường rẻ hơn khi phạm vi đã biết.

Một bảng `PRIMARY KEY (tenant_id, doc_id)` sẽ gom dữ liệu một tenant vào **một partition** nếu `tenant_id` là partition key đơn. Với tenant rất lớn, partition này có thể nóng hoặc quá rộng. Đừng sửa thiết kế theo cách đó chỉ để bỏ một index mà chưa đánh giá phân phối và truy vấn. Khi cần cả truy vấn theo ID, ANN và lọc theo tenant, thường phải cân nhắc tập chỉ mục, bảng riêng hoặc mô hình partitioning theo tải thực tế.

## 6. ANN, consistency và vận hành cluster

SAI là chỉ mục gắn với việc lưu dữ liệu tại các node, không phải một server tìm kiếm tách rời Cassandra. Các thao tác ghi, memtable/SSTable, compaction và replication đều ảnh hưởng đến tính sẵn sàng, tốc độ lập chỉ mục và độ trễ. Tuy nhiên:

- **Replication** giúp dữ liệu có bản sao theo RF. Nó không biến truy vấn ANN thành tìm kiếm chính xác tuyệt đối.
- **Consistency level** như `LOCAL_ONE` hay `LOCAL_QUORUM` cần chọn theo yêu cầu đọc và topology; tăng mức nhất quán không bảo đảm tăng *recall@k* của thuật toán ANN.
- **Compaction** và việc xây dựng chỉ mục trên SSTable có thể tạo thêm công việc nền và làm thay đổi latency. Đừng đánh giá hiệu năng chỉ bằng lần truy vấn đầu tiên.
- **Repair** xử lý sự khác biệt giữa replica theo cơ chế Cassandra; nó không sửa lỗi embedding được tạo sai mô hình hoặc sai số chiều.
- Cập nhật/xóa vector nhiều lần có thể làm tìm kiếm chậm hơn so với dữ liệu hầu như chỉ thêm mới. Tài liệu chính thức khuyến nghị ưu tiên dữ liệu vector ít bị overwrite/deletion.

### Các giới hạn nên kiểm tra trước khi triển khai

| Ràng buộc | Hệ quả/giải pháp |
| --- | --- |
| Version không hỗ trợ `VECTOR` hoặc SAI vector | Không thể chỉ thêm `CREATE INDEX` để bật ANN; cần bản Cassandra hỗ trợ. |
| Vector sai số chiều | Không phù hợp kiểu `VECTOR<FLOAT, N>` đã khai báo; kiểm tra trước khi ghi hoặc truy vấn. |
| Đổi mô hình embedding | Vector mới và cũ có thể không còn so sánh có nghĩa; cân nhắc bảng/index mới và backfill. |
| `LIMIT` quá lớn | Bị ràng buộc bởi giới hạn của vector search và có thể tăng latency. |
| Tranh chấp cập nhật nhiều vector cùng khóa | Gây tải ghi/index và ảnh hưởng truy vấn; cân nhắc mô hình dữ liệu ổn định hơn. |
| Truy vấn không lọc tenant | Có thể trả dữ liệu ngoài phạm vi người dùng; luôn áp dụng bộ lọc và kiểm tra quyền ở ứng dụng. |
| Dùng chỉ mục vector thay cho phân tích dữ liệu | ANN chỉ trả ứng viên gần nhất; không phải `GROUP BY`, join hay phép tính chính xác toàn tập. |

Đo các chỉ số riêng cho hệ thống truy hồi:

- **Recall@k**: tỉ lệ kết quả đúng theo bộ nhãn/chuẩn so với tập *exact* dùng đánh giá offline.
- **Latency p50/p95/p99**: đo ở tải đồng thời thực tế, không chỉ một request đơn lẻ.
- **Tốc độ ingest**, CPU, RAM, disk/I/O, compaction, timeout, lỗi index và số lượng dữ liệu theo tenant.
- **Chất lượng ngữ nghĩa**: câu hỏi có tìm được tài liệu liên quan không; embedding model và việc chia đoạn (*chunking*) ảnh hưởng trực tiếp tới kết quả.

Nếu một sự cố node làm tăng latency hoặc giảm tính sẵn sàng, đánh giá cả topology, mức nhất quán và tình trạng index. Không kết luận rằng hai truy vấn trả top-k khác nhau nhất định là lỗi dữ liệu: ANN vốn xấp xỉ và có thể chịu ảnh hưởng từ trạng thái cluster.

## 7. Kết nối ứng dụng Java

Ví dụ sau dùng **Cassandra Java Driver 4.17+** (hoặc một bản 4.x tương thích có API vector) và Java 17. Giả sử `CqlSession` được cấu hình để kết nối tới Cassandra 5.0 hỗ trợ SAI, bảng/index từ mục 3 đã tồn tại và hệ thống sinh embedding ba chiều tương thích với dữ liệu.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.CqlVector;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class SemanticDocumentSearch {
    private final CqlSession session;
    private final PreparedStatement findSimilar;

    public record Hit(UUID id, String title, float cosineScore) {}

    public SemanticDocumentSearch(CqlSession session) {
        this.session = session;
        this.findSimilar = session.prepare(
            "SELECT doc_id, title, " +
            "similarity_cosine(embedding, ?) AS score " +
            "FROM vector_lab.documents_semantic " +
            "WHERE tenant_id = ? " +
            "ORDER BY embedding ANN OF ? " +
            "LIMIT 3");
    }

    public List<Hit> search(String tenantId, float[] embedding) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId bắt buộc");
        }
        if (embedding == null || embedding.length != 3) {
            throw new IllegalArgumentException("Cần vector đúng 3 chiều");
        }
        for (float value : embedding) {
            if (!Float.isFinite(value)) {
                throw new IllegalArgumentException("Vector có NaN/Infinity");
            }
        }

        CqlVector<Float> query = CqlVector.newInstance(
            embedding[0], embedding[1], embedding[2]);
        BoundStatement bound = findSimilar.bind(query, tenantId, query)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        ResultSet rows = session.execute(bound);
        List<Hit> hits = new ArrayList<>();
        for (Row row : rows) {
            hits.add(new Hit(
                row.getUuid("doc_id"),
                row.getString("title"),
                row.getFloat("score")));
        }
        return hits;
    }
}
~~~

Các điểm cần hiểu:

- `CqlVector.newInstance(...)` tạo giá trị phù hợp với kiểu `VECTOR<FLOAT, N>`. Kiểm tra số chiều đầu vào theo cấu hình mô hình; trong ví dụ là 3, trong sản phẩm thường lớn hơn.
- Dấu `?` giúp truyền vector/tenant qua **prepared statement**, không nối trực tiếp dữ liệu người dùng vào chuỗi CQL. Hai vị trí `?` cho vector cùng nhận một `CqlVector`; vị trí còn lại nhận `tenantId`.
- `LIMIT 3` trong ví dụ là cố định; nếu người dùng chọn `k`, ứng dụng phải xác thực `k` và giới hạn theo khả năng truy vấn trước khi xây dựng câu CQL tương ứng.
- `LOCAL_QUORUM` chỉ là mức nhất quán minh họa cho cluster phù hợp RF. Với keyspace demo RF=1, mức này không thể tạo dự phòng replica; sản xuất cần thiết kế RF và DC riêng.
- `session` và `PreparedStatement` nên được tái sử dụng. Cần cấu hình timeout, giới hạn concurrent requests, phân trang/giao diện top-k và xử lý khi node/index chưa sẵn sàng.

Để ghi vector từ Java, chuẩn bị câu lệnh `INSERT` có tham số `embedding`, sau đó truyền `CqlVector<Float>` tương tự. Phần **sinh embedding** cần một mô hình hoặc dịch vụ ML ngoài database; lớp lưu trữ chỉ nhận mảng số đã được chuẩn hóa và xác thực.

## 8. Bài thực hành và kiểm tra lỗi

### Bài 1 — Khả năng tương thích

Kiểm tra `release_version` trong môi trường lab. Viết ra phiên bản server, driver, cú pháp chỉ mục và độ dài vector được hỗ trợ. Nếu đang dùng Cassandra 4.x, mô tả phương án nâng cấp hoặc thay thế, **không** chạy `VECTOR` rồi kỳ vọng hoạt động.

### Bài 2 — ANN cơ bản

Tạo bảng và hai chỉ mục, nạp bốn bản ghi mẫu. Chạy truy vấn top-3 với `[1.0, 0.0, 0.0]`. So sánh với kết quả khi đổi sang vector `[0.0, 1.0, 0.0]`. Giải thích vì sao các kết quả chỉ mang ý nghĩa minh họa về khoảng cách hình học.

### Bài 3 — Lọc tenant

Chạy truy vấn không `WHERE`, sau đó thêm `WHERE tenant_id = 'team-a'`. Xác nhận tập kết quả không chứa tài liệu của `team-b` khi đã lọc. Nêu rõ chỉ mục `documents_tenant_sai` phục vụ điều kiện nào và tại sao vẫn phải kiểm tra quyền của người dùng trong ứng dụng.

### Bài 4 — Điểm tương đồng

Chạy truy vấn `similarity_cosine` và so sánh điểm của những bản ghi trả về. Thảo luận điều gì sẽ thay đổi khi tạo lại chỉ mục với `DOT_PRODUCT` trong một môi trường thử nghiệm riêng. Không diễn giải hai thang điểm như nhau.

### Bài 5 — Lỗi dữ liệu và bảo trì

Thử ghi vector sai số chiều và kiểm tra lỗi được trả về. Mô phỏng thay đổi embedding model, chỉ ra các bước cần để giữ tập dữ liệu nhất quán (phiên bản mô hình, xây dựng chỉ mục mới, backfill, chuyển đổi truy vấn). Lập kế hoạch đo p95 và recall@k trong khi có tải ghi, compaction hoặc một replica không khả dụng.

## 9. Tài liệu tham khảo

- [Apache Cassandra — Vector Search Quickstart](https://cassandra.apache.org/doc/stable/cassandra/getting-started/vector-search-quickstart.html): ví dụ `VECTOR`, tạo SAI, nạp dữ liệu và truy vấn `ANN OF`.
- [Apache Cassandra — Vector CQL data type](https://cassandra.apache.org/doc/latest/cassandra/reference/vector-data-type.html): kiểu vector, số chiều và giới hạn của dữ liệu.
- [Apache Cassandra — Working with Vector Search](https://cassandra.apache.org/doc/latest/cassandra/vector-search/vector-search-working-with.html): hàm similarity, chỉ mục và các giới hạn truy vấn ANN.
- [Apache Cassandra — SAI concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-concepts.html): vị trí của SAI trong kiến trúc lưu trữ.
- [Apache Cassandra Java Driver — Upgrade guide 4.17](https://docs.datastax.com/en/developer/java-driver/4.17/upgrade_guide/): cách sử dụng `CqlVector` với prepared statements.

## Ghi nhớ

**Cassandra 5.0+ có thể dùng SAI trên cột `VECTOR<FLOAT, N>` để truy vấn `ORDER BY ... ANN OF ... LIMIT`.** Dữ liệu vector phải được sinh và quản lý nhất quán ngoài Cassandra. ANN trả kết quả gần đúng, vì vậy cần đánh giá recall, độ trễ, lọc theo tenant, topology và replication bên cạnh tính đúng đắn của CQL. Luôn kiểm tra phiên bản server/driver trước khi dùng tính năng này.
