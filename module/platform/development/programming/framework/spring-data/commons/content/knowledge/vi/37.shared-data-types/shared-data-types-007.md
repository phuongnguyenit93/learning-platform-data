# SearchResult, SearchResults và kết quả gắn điểm

## 1. Mục tiêu và phiên bản áp dụng

Trong chương **Kiểu dữ liệu dùng chung** của module **Spring Data Commons**, một kết quả tìm kiếm có thể cần giữ cả dữ liệu và điểm liên quan đến truy vấn. Nếu chỉ trả entity hoặc DTO, ứng dụng có thể làm mất thông tin cần cho hiển thị, xếp hạng hoặc giải thích kết quả.

Hai kiểu cần nhận diện:

~~~java
org.springframework.data.domain.SearchResult
org.springframework.data.domain.SearchResults
~~~

Các API này có từ Spring Data Commons **4.0**. Ví dụ giả định dự án đang dùng một dòng phiên bản hỗ trợ chúng; không áp dụng nguyên import cho một dự án 3.x rồi tự tạo lớp cùng tên để che lỗi dependency. Xem [Javadoc SearchResult](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/SearchResult.html) và [Javadoc SearchResults](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/SearchResults.html).

Sau bài học, bạn cần:

- Giữ một nội dung và Score trong cùng một kết quả.
- Đọc đúng lớp bọc của một tập SearchResults.
- Ánh xạ entity sang DTO mà không tách nhầm điểm.
- Chọn đúng chiều xếp hạng theo hợp đồng điểm.
- Phân biệt số phần tử đang có với tổng số kết quả.
- Thiết kế adapter tìm kiếm theo khả năng của store.
- Công bố response HTTP có ý nghĩa rõ ràng.

Ví dụ dùng Java 17 trở lên. Phần lớn code tạo dữ liệu minh họa trong bộ nhớ, không giả định một database cụ thể.

## 2. Một kết quả có hai phần: content và score

Giả sử tìm tài liệu về repository trả về:

| Tài liệu | Điểm minh họa |
| --- | --- |
| Repository căn bản | 0.91 |
| Tùy chỉnh repository | 0.84 |
| Auditing dữ liệu | 0.42 |

Trong ví dụ này, ứng dụng quy định điểm lớn hơn nghĩa là phù hợp hơn. Đây là chính sách của bộ điểm minh họa, không phải một quy tắc có thể áp cho mọi loại score.

Cấu trúc nên giữ:

~~~text
SearchResult<Article>
    |
    +-- content: Article
    |
    +-- score: Score
~~~

Tránh giữ một List<Article> và một List<Double> độc lập rồi ghép bằng vị trí. Nếu chỉ một trong hai danh sách bị lọc hoặc sort lại, điểm có thể được gắn sang tài liệu khác.

Lớp bọc làm mối quan hệ dữ liệu-điểm hiện rõ trong kiểu Java.

## 3. Tạo và đọc SearchResult<T>

DTO minh họa:

~~~java
public record ArticleSummary(long id, String title) {
}
~~~

Tạo một kết quả:

~~~java
import org.springframework.data.domain.Score;
import org.springframework.data.domain.SearchResult;

ArticleSummary article =
        new ArticleSummary(101L, "Repository căn bản");

SearchResult<ArticleSummary> result =
        new SearchResult<>(article, Score.of(0.91));

ArticleSummary content = result.getContent();
Score score = result.getScore();

double numericValue = score.getValue();
~~~

Có overload nhận trực tiếp double:

~~~java
SearchResult<ArticleSummary> result =
        new SearchResult<>(article, 0.91);
~~~

Với constructor nhận Score, content và score đều phải khác null. Constructor và accessor được mô tả tại [API SearchResult](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/SearchResult.html).

Tạo object trong ví dụ không thực hiện tìm kiếm. Các số 0.91, 0.84 chỉ là fixture để diễn giải luồng xử lý, không phải điểm do Commons tính từ title.

### 3.1. Score không chỉ là một double

Score có thể giữ giá trị cùng thông tin ScoringFunction. Một điểm được tạo từ giá trị trần không tự mang đầy đủ định nghĩa thuật toán; `Score.of(value)` dùng function không xác định. Xem [API Score](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Score.html).

~~~java
String functionName =
        result.getScore().getFunction().getName();
~~~

Ứng dụng không nên suy ra chính sách hiển thị chỉ từ việc numericValue nằm trong khoảng 0 đến 1.

Một giá trị 0.91 không tự có nghĩa “91% chắc chắn đúng”. Muốn hiển thị xác suất hoặc một nhãn độ tin cậy, cần một hợp đồng và phương pháp đánh giá riêng.

### 3.2. Điểm là thông tin theo truy vấn

Cùng một tài liệu có thể nhận điểm khác nhau đối với hai câu hỏi khác nhau.

Do đó, không nên đưa một field score cố định vào entity rồi coi đó là độ phù hợp vĩnh viễn của tài liệu. Nếu cần lưu lịch sử tìm kiếm, hãy thiết kế bản ghi có ngữ cảnh truy vấn, phiên bản cấu hình và kết quả tương ứng.

Điểm gắn với một lần tìm kiếm không thay thế thuộc tính nghiệp vụ của tài liệu.

## 4. SearchResults<T> giữ một tập các kết quả đã gắn điểm

~~~java
import java.util.List;

import org.springframework.data.domain.SearchResult;
import org.springframework.data.domain.SearchResults;

SearchResults<ArticleSummary> results = new SearchResults<>(
        List.of(
                new SearchResult<>(
                        new ArticleSummary(
                                101L, "Repository căn bản"),
                        0.91),
                new SearchResult<>(
                        new ArticleSummary(
                                102L, "Tùy chỉnh repository"),
                        0.84)));
~~~

Điểm quan trọng về generic:

~~~text
SearchResults<ArticleSummary>
          |
          v
List<SearchResult<ArticleSummary>>
          |
          v
ArticleSummary + Score
~~~

`getContent()` trả các SearchResult, không trả trực tiếp List<ArticleSummary>.

### 4.1. Lặp qua kết quả

~~~java
for (SearchResult<ArticleSummary> hit : results) {
    ArticleSummary article = hit.getContent();
    double value = hit.getScore().getValue();

    System.out.println(
            article.title() + " -> " + value);
}
~~~

### 4.2. Stream có điểm và stream chỉ có nội dung

~~~java
List<SearchResult<ArticleSummary>> scored =
        results.stream().toList();

List<ArticleSummary> articles =
        results.contentStream().toList();
~~~

`stream()` giữ lớp bọc; `contentStream()` bỏ lớp bọc và chỉ đưa nội dung vào stream. Danh sách từ getContent là danh sách không cho sửa qua API đó. Xem [API SearchResults](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/SearchResults.html).

Chỉ dùng contentStream khi tác vụ thực sự không cần điểm. Một khi đã chuyển thành List<ArticleSummary>, không nên cố ghép điểm trở lại bằng thứ tự từ một nguồn có thể đã thay đổi.

Không suy ra toàn bộ object graph bất biến chỉ từ việc danh sách không sửa được. Nếu T là một entity mutable, chính nội dung vẫn có thể có trạng thái thay đổi.

### 4.3. Số phần tử đang có

~~~java
int returnedCount = results.getContent().size();
~~~

Đây là số kết quả đang nằm trong object.

Nếu query đã giới hạn 10 phần tử, returnedCount bằng 10 không chứng minh chỉ có đúng 10 tài liệu khớp trên toàn bộ index.

Không dùng tên `totalElements` cho con số đó nếu ứng dụng không có thông tin tổng tương ứng.

## 5. Ánh xạ nội dung và giữ điểm đi cùng

Giả sử adapter trả domain object:

~~~java
public record ArticleDocument(
        long id,
        String title,
        String body) {
}
~~~

Một hit:

~~~java
SearchResult<ArticleDocument> original =
        new SearchResult<>(
                new ArticleDocument(
                        101L,
                        "Repository căn bản",
                        "Nội dung chi tiết..."),
                0.91);

SearchResult<ArticleSummary> mapped = original.map(
        document -> new ArticleSummary(
                document.id(),
                document.title()));
~~~

Việc map hướng vào content; điểm vẫn đi cùng kết quả được ánh xạ. Khi cần xác nhận hợp đồng API, có thể xem [map của SearchResult](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/SearchResult.html#map(java.util.function.Function)).

Với cả tập:

~~~java
SearchResults<ArticleDocument> raw =
        new SearchResults<>(List.of(original));

SearchResults<ArticleSummary> summaries = raw.map(
        document -> new ArticleSummary(
                document.id(),
                document.title()));
~~~

Cách làm này diễn đạt rằng ứng dụng đang chuyển hình dạng dữ liệu hiển thị, không đang tính lại độ phù hợp.

### 5.1. Map không phải một lần tìm kiếm mới

Nếu bỏ body hoặc đổi tên field DTO, kết quả không tự được tìm lại trên index.

Nếu nội dung phục vụ người dùng đã bị thay đổi theo một cách làm thay đổi ý nghĩa tìm kiếm, cần đánh giá lại việc dùng score ban đầu. Việc map còn giữ giá trị số không chứng minh điểm đó phù hợp với mọi biến đổi nội dung.

### 5.2. Đừng dùng map như filter

Map nên tạo một nội dung đích hợp lệ cho từng phần tử. Không trả null để biểu diễn “bỏ kết quả này”.

Nếu cần lọc kết quả trong ứng dụng, hãy dùng một bước lọc tường minh và hiểu tác động của nó lên số lượng trả về, thứ tự và tính đầy đủ của kết quả.

## 6. Đọc score theo scoring function và hợp đồng query

Một số tìm kiếm dùng độ tương tự, một số dùng khoảng cách. Chiều “tốt hơn” không được quyết định chỉ bởi tên field score. Spring Data mô tả điều này trong [Vector Search](https://docs.spring.io/spring-data/commons/reference/repositories/vector-search.html).

Ví dụ minh họa hai hợp đồng:

| Hợp đồng | Tài liệu A | Tài liệu B | Tốt hơn |
| --- | --- | --- | --- |
| Điểm relevance tăng theo độ phù hợp | 0.91 | 0.84 | A |
| Khoảng cách tăng theo độ xa | 0.10 | 0.35 | A |

Một thao tác sort giảm dần cho cả hai bảng sẽ đúng ở bảng đầu và sai ở bảng sau.

### 6.1. Một số function có tên rõ ràng

ScoringFunction có các factory như cosine, euclidean, dotProduct và unspecified; tên function có thể đọc qua getName. Xem [API ScoringFunction](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/ScoringFunction.html).

~~~java
import org.springframework.data.domain.Score;
import org.springframework.data.domain.ScoringFunction;

Score annotatedScore = Score.of(
        0.91,
        ScoringFunction.cosine());
~~~

Việc tạo Score với function không chạy phép tính cosine trên hai vector. Nó gắn giá trị với ngữ cảnh function; backend hoặc lớp tính toán phải cung cấp giá trị đúng.

### 6.2. Normalized similarity không phải xác suất

Similarity là một kiểu Score dành cho ngữ nghĩa similarity chuẩn hóa trong khoảng 0 đến 1 ở các factory được kiểm tra. Xem [API Similarity](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Similarity.html).

Điều đó vẫn không biến điểm thành xác suất một kết quả là đúng.

Hai hệ thống cùng công bố normalized similarity chưa chắc có cùng chất lượng kết quả ở ngưỡng 0.8. Dữ liệu, embedding, index và cách tìm kiếm vẫn ảnh hưởng ý nghĩa thực tế.

Vì vậy, một ngưỡng hiển thị như “kết quả phù hợp” cần được đánh giá trên dữ liệu của ứng dụng, không chỉ chọn vì số nhìn có vẻ hợp lý.

## 7. Xếp hạng, lọc và giới hạn kết quả

### 7.1. Chỉ sort khi biết rõ chiều của điểm

Với bộ điểm minh họa higher-is-better:

~~~java
import java.util.Comparator;
import java.util.List;

Comparator<SearchResult<ArticleSummary>> ranking =
        Comparator.<SearchResult<ArticleSummary>>comparingDouble(
                hit -> hit.getScore().getValue())
                .reversed()
                .thenComparingLong(
                        hit -> hit.getContent().id());

List<SearchResult<ArticleSummary>> ranked =
        results.stream()
                .sorted(ranking)
                .toList();
~~~

Id phụ giúp có quy tắc xác định khi hai điểm bằng nhau trong tập đang xử lý.

Đoạn code chỉ xếp lại các phần tử đã được đưa về ứng dụng. Nó không yêu cầu backend tìm lại toàn bộ dữ liệu và không thể đưa vào những tài liệu chưa nằm trong tập kết quả.

Với điểm distance theo hợp đồng lower-is-better, comparator phải có chiều phù hợp.

Không giả định một constructor nhận List sẽ tự hiểu ý nghĩa score, tự tính lại điểm hoặc áp dụng policy xếp hạng của sản phẩm. Ứng dụng và adapter phải xác định nguồn thứ tự cần giữ.

### 7.2. Không dùng Sort theo field domain để phỏng đoán thứ tự score

Một thuộc tính như title hoặc createdAt có thể là tiêu chí sort của domain. Score lại có thể là metadata của lần tìm kiếm, không phải một property được lưu trong entity.

Vì vậy, không mặc định `Sort.by("score")` sẽ được mọi mô-đun hiểu như thứ tự relevance.

Phải kiểm tra API tìm kiếm và quy tắc sorting của mô-đun cụ thể. Nếu chọn một thứ tự domain khác, kết quả hiển thị có thể không còn được ưu tiên theo relevance như trước.

### 7.3. Lọc ngưỡng sau khi lấy top K

Ví dụ một policy minh họa chấp nhận score ít nhất 0.8:

~~~java
List<SearchResult<ArticleSummary>> accepted =
        results.stream()
                .filter(hit ->
                        hit.getScore().getValue() >= 0.8)
                .toList();
~~~

Đây là ngưỡng của bộ điểm higher-is-better đang dùng.

Nếu backend chỉ trả top 10 rồi ứng dụng lọc còn 3, không suy ra toàn bộ index chỉ có 3 tài liệu đủ ngưỡng. Thao tác local chỉ đánh giá 10 kết quả được trả về.

Nếu hợp đồng yêu cầu tìm đủ các kết quả vượt ngưỡng hoặc trả một số lượng tối đa cụ thể, phải thiết kế query/adapter tương ứng theo khả năng store.

### 7.4. Reranking cần một ngữ nghĩa điểm mới rõ ràng

Ứng dụng có thể dùng một bước xếp hạng lại sau khi truy xuất ứng viên.

Khi đó cần phân biệt:

- Điểm do backend truy xuất tạo ra.
- Điểm do reranker tạo ra.
- Thứ tự cuối cùng dùng cho response.

Không thay numeric value mà vẫn quảng bá nó là điểm của function hoặc profile cũ.

Nếu sản phẩm cần hiển thị cả hai, hãy tạo DTO giữ hai loại metadata riêng thay vì nhét chúng vào một trường score mơ hồ.

## 8. SearchResults không phải Page hoặc Slice

| Kiểu kết quả | Thông tin chính |
| --- | --- |
| List<T> | Nội dung, không có một lớp score bắt buộc |
| SearchResult<T> | Một nội dung đi cùng Score |
| SearchResults<T> | Tập các kết quả gắn điểm |
| Page<T> | Nội dung cùng metadata phân trang và tổng số theo hợp đồng Page |
| Slice<T> | Một cửa sổ có thông tin về khả năng còn kết quả tiếp |
| Window<T> | Kết quả phục vụ cơ chế scrolling tương ứng |

Không gọi các method của Page như getTotalElements trên một SearchResults.

Nếu cần kết quả gắn điểm cùng cơ chế phân trang, hãy chọn API mô-đun hỗ trợ hoặc một envelope ứng dụng thể hiện đúng thông tin có thật.

Không tạo:

~~~text
totalElements = số phần tử top K đang có
totalPages = 1
hasNext = false
~~~

chỉ để response có đủ trường của một schema phân trang.

Một response giới hạn 10 kết quả có thể chỉ công bố returnedCount và giới hạn đã yêu cầu. Nếu không có count hoặc continuation token, đừng bịa chúng.

Danh mục kiểu trả về của Spring Data cũng lưu ý khả năng thực tế phụ thuộc mô-đun lưu trữ; một abstraction xuất hiện trong Commons không làm mọi query method tự hoạt động. Xem [Repository query return types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html).

## 9. Ví dụ service dùng một adapter tìm kiếm

Để giữ ví dụ độc lập với store, định nghĩa port do ứng dụng sở hữu:

~~~java
import org.springframework.data.domain.SearchResults;
import org.springframework.data.domain.Vector;

public interface ArticleSearchPort {

    SearchResults<ArticleDocument> search(
            Vector queryVector,
            long tenantId,
            int limit);
}
~~~

Đây là interface ứng dụng, không phải một repository method mà Spring Data tự suy ra implementation chỉ từ tên search.

Hai abstraction bổ sung:

~~~java
import org.springframework.data.domain.Vector;

public interface TextEmbeddingProvider {
    Vector embed(String text);
}
~~~

~~~java
public interface CurrentTenant {
    long requiredTenantId();
}
~~~

Service:

~~~java
import org.springframework.data.domain.SearchResults;
import org.springframework.data.domain.Vector;
import org.springframework.stereotype.Service;

@Service
public class ArticleSearchService {

    private final ArticleSearchPort searchPort;
    private final TextEmbeddingProvider embeddings;
    private final CurrentTenant currentTenant;

    public ArticleSearchService(
            ArticleSearchPort searchPort,
            TextEmbeddingProvider embeddings,
            CurrentTenant currentTenant) {

        this.searchPort = searchPort;
        this.embeddings = embeddings;
        this.currentTenant = currentTenant;
    }

    public SearchResults<ArticleSummary> search(
            String text, int limit) {

        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(
                    "Nội dung tìm kiếm không được rỗng");
        }

        if (limit < 1 || limit > 50) {
            throw new IllegalArgumentException(
                    "limit phải nằm trong khoảng 1..50");
        }

        long tenantId = currentTenant.requiredTenantId();
        Vector vector = embeddings.embed(text.strip());

        SearchResults<ArticleDocument> matches =
                searchPort.search(vector, tenantId, limit);

        return matches.map(document ->
                new ArticleSummary(
                        document.id(),
                        document.title()));
    }
}
~~~

Mỗi kiểu public đặt trong file Java tương ứng khi triển khai thật. Ví dụ chưa cung cấp implementation của adapter, embedding provider hoặc ngữ cảnh tenant.

### 9.1. Trách nhiệm của adapter

Implementation phải chọn API của một mô-đun có khả năng thực thi loại tìm kiếm cần dùng.

Adapter cần xác định rõ:

- Query vector tương thích với model/index nào.
- Số chiều và biểu diễn vector phù hợp với backend.
- Bộ lọc tenant và các điều kiện bắt buộc được thực hiện ở đâu.
- Giới hạn kết quả được áp dụng thế nào.
- Score là loại giá trị nào, function/profile nào và chiều xếp hạng ra sao.
- Thứ tự kết quả nào được chuyển cho ứng dụng.
- Có metadata tổng số hoặc continuation hay không.

Commons cung cấp kiểu dữ liệu để giữ kết quả. Nó không tự chọn embedding model, tạo index hoặc bảo đảm backend hỗ trợ vector search.

### 9.2. Phạm vi dữ liệu không được giao cho client

Tenant phải đến từ ngữ cảnh đã xác thực, không lấy một query parameter làm bằng chứng quyền truy cập.

Bộ lọc quyền truy cập cần được áp dụng theo thiết kế truy vấn của adapter. Chỉ lấy top K toàn hệ thống rồi lọc tenant trong ứng dụng có thể làm thiếu các kết quả hợp lệ của tenant và không phải một cơ chế bảo vệ dữ liệu đầy đủ.

Khi kiểm tra, cần chứng minh cả dữ liệu và metadata phản hồi không làm lộ phạm vi ngoài quyền của người dùng.

### 9.3. Tạo fixture không thay thế tìm kiếm thật

Để minh họa service, một test có thể trả SearchResults được dựng bằng List.of như phần trước.

Fixture đó kiểm tra mapping và luồng ứng dụng. Nó không chứng minh index đã hoạt động, phép tính điểm đúng hoặc cấu hình truy vấn trên store phù hợp.

Không đưa một danh sách điểm hard-code vào adapter production rồi coi đó là một implementation tìm kiếm tương đương.

## 10. Thiết kế response gắn điểm theo hợp đồng ứng dụng

Không cần làm hợp đồng HTTP phụ thuộc trực tiếp vào cách serializer phản ánh mọi getter của SearchResults hoặc Score.

Ví dụ một response do ứng dụng định nghĩa:

~~~java
import java.util.List;

public record ArticleHit(
        ArticleSummary article,
        double score) {
}
~~~

~~~java
import java.util.List;

public record ArticleSearchResponse(
        List<ArticleHit> items,
        int returnedCount,
        String scoreProfile,
        boolean higherIsBetter) {
}
~~~

Mapper:

~~~java
import java.util.List;

import org.springframework.data.domain.SearchResults;

public final class ArticleSearchResponses {

    private ArticleSearchResponses() {
    }

    public static ArticleSearchResponse from(
            SearchResults<ArticleSummary> matches,
            String scoreProfile,
            boolean higherIsBetter) {

        List<ArticleHit> items = matches.stream()
                .map(hit -> new ArticleHit(
                        hit.getContent(),
                        hit.getScore().getValue()))
                .toList();

        return new ArticleSearchResponse(
                items,
                items.size(),
                scoreProfile,
                higherIsBetter);
    }
}
~~~

Hai tham số scoreProfile và higherIsBetter phải đến từ policy đã xác định của endpoint/adapter. Không để client tự đặt chúng và không suy ra chúng từ một numeric value đơn lẻ.

Ví dụ JSON của bộ điểm minh họa:

~~~json
{
  "items": [
    {
      "article": {
        "id": 101,
        "title": "Repository căn bản"
      },
      "score": 0.91
    },
    {
      "article": {
        "id": 102,
        "title": "Tùy chỉnh repository"
      },
      "score": 0.84
    }
  ],
  "returnedCount": 2,
  "scoreProfile": "article-demo-v1",
  "higherIsBetter": true
}
~~~

`article-demo-v1` là nhãn hợp đồng minh họa của ứng dụng. Nó không phải tên function hoặc một hằng có sẵn của Spring Data.

Không đặt `totalElements: 2` trong ví dụ này vì code chỉ biết đang trả hai phần tử.

Nếu một endpoint có nhiều kiểu score không đồng nhất, một nhãn chung ở cấp response có thể không đủ. Cần thiết kế metadata phù hợp hoặc chuẩn hóa theo một chính sách đã được kiểm tra.

## 11. Những phép so sánh cần tránh

### 11.1. So sánh điểm từ hai truy vấn không cùng ngữ cảnh

Điểm 0.9 cho câu hỏi A và điểm 0.8 cho câu hỏi B không tự chứng minh kết quả của A “tốt hơn” về mặt sản phẩm.

Ngữ cảnh câu hỏi, tập ứng viên, model và cấu hình có thể khác nhau. Xếp hạng có ý nghĩa trước hết trong hợp đồng đã xác định của lần tìm kiếm.

### 11.2. Trộn điểm từ hai backend rồi sort trực tiếp

Nếu một nguồn trả distance còn nguồn khác trả similarity, sort tất cả numeric value theo một chiều sẽ làm sai ý nghĩa.

Ngay cả khi cùng chiều, thang đo có thể không tương đương. Một hệ thống tổng hợp cần chính sách hợp nhất hoặc reranking riêng.

Không dùng phép chia cho điểm lớn nhất trong batch rồi coi đó là chuẩn hóa đáng tin cậy cho mọi query.

### 11.3. Dùng ngưỡng không được đánh giá

Một ngưỡng minh họa 0.8 không phải mặc định chung của Spring Data hay mọi embedding model.

Khi thay model, index hoặc scoring profile, ngưỡng ứng dụng có thể cần được đánh giá lại theo dữ liệu đại diện.

### 11.4. Coi kết quả rỗng là lỗi hạ tầng hoặc ngược lại

Một SearchResults rỗng có thể là kết quả tìm kiếm hợp lệ.

Lỗi kết nối, timeout hoặc lỗi cấu hình không nên bị catch rồi chuyển thành một SearchResults rỗng chỉ để giữ HTTP 200.

Tầng ứng dụng cần phân biệt “đã tìm và không có kết quả” với “không thực hiện được tìm kiếm”.

## 12. Kiểm tra nội dung, điểm và metadata

### 12.1. Kiểm tra map giữ đúng cặp dữ liệu-điểm

~~~java
SearchResult<ArticleDocument> original =
        new SearchResult<>(
                new ArticleDocument(
                        101L,
                        "Repository căn bản",
                        "Nội dung..."),
                0.91);

SearchResult<ArticleSummary> mapped =
        original.map(document ->
                new ArticleSummary(
                        document.id(),
                        document.title()));

assertEquals(101L, mapped.getContent().id());
assertEquals("Repository căn bản",
        mapped.getContent().title());
assertEquals(original.getScore(), mapped.getScore());
~~~

Snippet giả định các import assertion tương ứng. Nó kiểm tra mapping, không kiểm tra chất lượng score do backend tạo.

### 12.2. Kiểm tra trường hợp rỗng

~~~java
SearchResults<ArticleSummary> empty =
        new SearchResults<>(List.of());

ArticleSearchResponse response =
        ArticleSearchResponses.from(
                empty, "article-demo-v1", true);

assertEquals(0, response.returnedCount());
assertTrue(response.items().isEmpty());
~~~

Response không cần giả lập một trang với tổng số hoặc hasNext không có căn cứ.

### 12.3. Ma trận kiểm tra

| Nhóm | Điều cần xác minh |
| --- | --- |
| Mapping | Id/title của từng phần tử vẫn gắn đúng Score |
| Nhiều kết quả | Không tách danh sách content và score rồi ghép sai vị trí |
| Điểm bằng nhau | Có policy thứ tự phụ nếu hợp đồng cần ổn định |
| Chiều score | Higher-is-better và lower-is-better không dùng chung một comparator sai |
| Kết quả rỗng | Không bị coi nhầm là lỗi truy vấn |
| Lỗi backend | Không bị biến thành kết quả rỗng thành công |
| Giới hạn | returnedCount không bị quảng bá thành tổng toàn bộ index |
| Scope | Người dùng không thấy dữ liệu ngoài tenant/quyền truy cập |
| Query/index | Vector, function và cấu hình adapter phù hợp |
| Response | Không lộ body hoặc field nội bộ không nằm trong DTO |
| Nâng cấu hình | Profile/threshold được đánh giá lại khi có thay đổi liên quan |

Mock port hữu ích để kiểm tra service. Kiểm tra tích hợp trên store mới xác minh đường truy vấn và metadata thực tế. Đánh giá chất lượng tìm kiếm trên tập dữ liệu đại diện lại là một nhiệm vụ khác với hai loại kiểm tra đó.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Import không tồn tại | Dùng API 4.0 trên dependency cũ | Chọn bộ phiên bản hỗ trợ đúng API |
| getContent bị gán sai generic | Nhầm List<SearchResult<T>> với List<T> | Đọc đúng lớp bọc |
| Response không còn score | Dùng contentStream quá sớm | Giữ SearchResult đến bước tạo DTO |
| Điểm gắn sai tài liệu | Tách content và score thành hai danh sách | Giữ chúng cùng object |
| Kết quả distance bị đảo | Luôn sort score giảm dần | Áp dụng chiều theo hợp đồng điểm |
| UI hiển thị 91% chắc chắn | Coi score như xác suất | Công bố ý nghĩa và thang đo đúng |
| Trả tổng số bằng top K | Nhầm tập đang có với tổng mọi kết quả | Dùng returnedCount hoặc metadata thật |
| Repository không thực thi được query | Suy năng lực store từ kiểu Commons | Dùng API mô-đun được hỗ trợ |
| Kết quả tenant thiếu hoặc sai scope | Lọc sau truy xuất toàn cục không phù hợp | Thiết kế scope trong đường tìm kiếm |
| Đổi model nhưng giữ nguyên ngưỡng | Ngưỡng không còn được đánh giá | Quản lý scoring profile và kiểm tra chất lượng |
| Model response quá nhiều chi tiết nội bộ | Serialize trực tiếp mọi kiểu thư viện | Dùng DTO hợp đồng của ứng dụng |

## 14. Bài thực hành

1. Tạo ba SearchResult<ArticleDocument> với điểm minh họa và gom thành SearchResults.
2. Lặp qua cả nội dung và Score, sau đó so sánh stream với contentStream.
3. Map sang ArticleSummary và kiểm tra từng điểm vẫn gắn đúng tài liệu.
4. Thiết kế một policy higher-is-better và một policy distance lower-is-better.
5. Kiểm tra thứ tự khi có hai điểm bằng nhau.
6. Tạo response có returnedCount và scoreProfile, không tự thêm tổng số.
7. Định nghĩa port tìm kiếm và mô tả implementation nào của store sẽ cung cấp nó.
8. Kiểm tra scope tenant và giới hạn kết quả theo hợp đồng adapter.
9. Giải thích vì sao score không phải xác suất và vì sao top K không phải tổng số.
10. Phân biệt kiểm tra mapping, kiểm tra tích hợp query và đánh giá chất lượng tìm kiếm.

Bài thực hành đạt yêu cầu khi bạn giữ đúng **cặp nội dung-điểm**, diễn giải **score theo ngữ cảnh**, và công bố **chính xác những metadata mà đường tìm kiếm thực sự cung cấp**.
