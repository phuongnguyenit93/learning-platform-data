# Thứ tự ổn định và trường phân xử khi nhiều tài liệu có cùng giá trị

Khi Elasticsearch sắp xếp kết quả theo một field như ngày tạo, giá, điểm relevance hoặc tên, nhiều document có thể có cùng giá trị. Nếu chỉ sắp xếp theo field đó, thứ tự giữa các document đồng hạng không được xác định đầy đủ. Điều này đặc biệt dễ gây nhầm lẫn khi người dùng chuyển trang: một document có thể xuất hiện ở hai trang hoặc bị bỏ qua nếu index thay đổi giữa các request.

Để có thứ tự ổn định, hãy xây dựng một thứ tự tổng (total order): dùng field nghiệp vụ làm tiêu chí chính, sau đó thêm một trường phân xử (tie-breaker) có giá trị duy nhất và ổn định cho mỗi document. Trường phân xử phải được lập chỉ mục theo kiểu hỗ trợ sort và luôn có giá trị.

Với phân trang sâu hoặc cần một tập kết quả nhất quán trong lúc dữ liệu tiếp tục được ghi, hãy kết hợp Point in Time (PIT) với search_after. PIT giữ một góc nhìn nhất quán của index trong thời gian phân trang; search_after tiếp tục từ sort values của hit cuối trang trước.

## 1. Vì sao cùng giá trị sort gây ra vấn đề?

Giả sử có năm bài viết cùng có ngày xuất bản 2026-11-01. Query chỉ sắp xếp publishedAt giảm dần:

~~~json
{
  "sort": [
    {
      "publishedAt": {
        "order": "desc"
      }
    }
  ]
}
~~~

Elasticsearch biết bài viết nào có ngày mới hơn, nhưng không có tiêu chí nghiệp vụ để quyết định thứ tự giữa các bài cùng ngày. Thứ tự của các hit đồng hạng có thể phụ thuộc vào cách dữ liệu được phân bố, segment, shard và trạng thái index. Không nên dựa vào thứ tự ngẫu nhiên hoặc thứ tự tình cờ quan sát được trong một lần chạy.

Vấn đề trở nên rõ hơn khi dùng phân trang offset:

~~~text
Trang 1: from = 0, size = 2
Trang 2: from = 2, size = 2
~~~

Nếu nhiều document có cùng giá trị sort, ranh giới giữa trang 1 và trang 2 không có tiêu chí phân xử rõ ràng. Khi index refresh hoặc dữ liệu mới được thêm vào, kết quả có thể đổi thứ tự và làm người dùng thấy trùng hoặc thiếu document.

Để giải quyết, bổ sung một field duy nhất làm tiêu chí sort cuối cùng:

~~~json
{
  "sort": [
    {
      "publishedAt": {
        "order": "desc"
      }
    },
    {
      "sort_id": {
        "order": "asc"
      }
    }
  ]
}
~~~

Nếu publishedAt bằng nhau, sort_id quyết định thứ tự. Vì sort_id duy nhất, hai document khác nhau không còn đồng hạng theo toàn bộ danh sách sort.

## 2. Thứ tự tổng và tie-breaker

Một thứ tự sort gồm nhiều tiêu chí được áp dụng theo thứ tự ưu tiên:

1. So sánh tiêu chí sort đầu tiên.
2. Nếu bằng nhau, so sánh tiêu chí thứ hai.
3. Nếu vẫn bằng nhau, tiếp tục tiêu chí kế tiếp.
4. Dùng tie-breaker duy nhất ở cuối để phân biệt mọi document.

Ví dụ:

~~~text
publishedAt DESC, sort_id ASC
~~~

- Bài mới hơn đứng trước.
- Nếu cùng thời điểm, sort_id nhỏ hơn đứng trước.
- Vì sort_id duy nhất, mỗi document có một vị trí riêng trong thứ tự.

Một thứ tự như vậy được gọi là thứ tự tổng trên tập document đang xét. Nó loại bỏ sự mơ hồ giữa các document có cùng giá trị ở những tiêu chí nghiệp vụ.

### 2.1. Thuộc tính của tie-breaker tốt

Trường phân xử nên đáp ứng các điều kiện:

- **Duy nhất:** hai document khác nhau trong tập tìm kiếm không có cùng giá trị.
- **Ổn định:** giá trị không thay đổi giữa các request phân trang.
- **Có mặt:** mọi document đều có giá trị; tránh null hoặc missing.
- **Sortable:** mapping hỗ trợ sort hiệu quả, thường là keyword hoặc kiểu số có doc values.
- **Được kiểm soát:** ứng dụng hoặc pipeline ghi dữ liệu bảo đảm giá trị được tạo đúng.

ID nghiệp vụ có thể là lựa chọn tốt nếu nó duy nhất trong toàn bộ tập index được truy vấn và được sao chép vào một field sortable. Nếu chỉ duy nhất trong từng index, nhưng query chạy trên alias bao gồm nhiều index, cần tạo khóa duy nhất trên toàn bộ tập đó.

### 2.2. Tie-breaker phải đứng cuối

Các field nghiệp vụ cần quyết định thứ tự chính nên đứng trước tie-breaker. Ví dụ:

~~~json
{
  "sort": [
    {"_score": "desc"},
    {"publishedAt": "desc"},
    {"sort_id": "asc"}
  ]
}
~~~

Thứ tự này ưu tiên relevance trước, sau đó bài mới hơn, cuối cùng dùng sort_id để phân xử khi hai tiêu chí đầu bằng nhau.

Nếu đặt sort_id lên trước _score, ID sẽ quyết định thứ tự trước relevance và có thể làm kết quả không còn đúng ý định tìm kiếm.

## 3. Vì sao không nên sort trực tiếp theo _id?

Elasticsearch có metadata field _id để định danh document. Tuy nhiên, _id không được thiết kế như một field sort thông thường và bị hạn chế khi dùng cho sort hoặc aggregation.

Không nên giả định rằng khai báo:

~~~json
{
  "sort": [
    {"_id": "asc"}
  ]
}
~~~

sẽ là cách phân xử phù hợp cho mọi truy vấn. Hãy sao chép ID vào một field dữ liệu riêng có doc values, ví dụ sort_id, rồi sort trên field đó.

### 3.1. Ví dụ entity Spring Data Elasticsearch

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

import java.time.Instant;

@Document(indexName = "articles")
public class Article {

    @Id
    private String id;

    @Field(name = "sort_id", type = FieldType.Keyword)
    private String sortId;

    @Field(name = "published_at", type = FieldType.Date)
    private Instant publishedAt;

    @Field(type = FieldType.Text)
    private String title;

    // constructors, getters and setters
}
~~~

Khi tạo hoặc cập nhật Article, gán sortId bằng một giá trị duy nhất, ổn định. Ví dụ, nếu id là UUID, có thể dùng cùng UUID làm sortId:

~~~java
public Article prepareForIndexing(Article article) {
    if (article.getSortId() == null) {
        article.setSortId(article.getId());
    }
    return article;
}
~~~

Đoạn code chỉ minh họa quy tắc đồng bộ. Nếu ID được sinh sau khi tạo entity hoặc do Elasticsearch sinh, hãy tạo ID ở ứng dụng trước khi save để có thể gán cả id và sortId. Không được để hai field lệch nhau hoặc thay đổi sortId sau khi document đã được phân trang.

Với kiểu keyword, doc values được bật mặc định trong mapping Elasticsearch. Có thể khai báo tường minh trong mapping nếu cần làm rõ hợp đồng:

~~~json
{
  "properties": {
    "sort_id": {
      "type": "keyword",
      "doc_values": true
    }
  }
}
~~~

Không dùng field text thông thường làm tie-breaker. Field text không hỗ trợ doc values theo mặc định và không phù hợp để sort nếu không thay đổi fielddata. Keyword hoặc kiểu số thường là lựa chọn tốt hơn.

### 3.2. Khóa duy nhất khi tìm trên nhiều index

Giả sử alias articles-read trỏ đến articles-2025 và articles-2026. Nếu mỗi index tự sinh ID như 1001, 1002, hai index có thể chứa document cùng ID. sort_id chỉ bằng ID cục bộ sẽ không duy nhất trên toàn alias.

Có thể tạo một khóa toàn cục như:

~~~text
articles-2025:1001
articles-2026:1001
~~~

Hoặc dùng UUID toàn cục được tạo ở nguồn dữ liệu. Mục tiêu là giá trị tie-breaker không trùng giữa bất kỳ hai document nào có thể xuất hiện trong cùng truy vấn.

Nếu khóa được ghép từ tenant và ID, hãy dùng cách mã hóa không nhập nhằng và ổn định. Ví dụ, nối chuỗi bằng dấu phân cách không đủ nếu các thành phần có thể chứa dấu phân cách đó; có thể dùng UUID hoặc encoding có quy tắc rõ ràng.

## 4. Multi-field sort trong Elasticsearch

Elasticsearch cho phép sắp xếp theo nhiều field. Sort được áp dụng theo thứ tự khai báo:

~~~json
{
  "sort": [
    {"published_at": {"order": "desc"}},
    {"priority": {"order": "desc"}},
    {"sort_id": {"order": "asc"}}
  ]
}
~~~

Ý nghĩa:

1. Bài mới hơn đứng trước.
2. Nếu cùng ngày xuất bản, bài có priority cao hơn đứng trước.
3. Nếu vẫn bằng nhau, sort_id xác định vị trí cuối cùng.

Có thể dùng các kiểu sort khác nhau:

| Kiểu field | Ví dụ sort | Lưu ý |
|---|---|---|
| date | published_at desc | Cần thống nhất format và múi giờ |
| keyword | category asc | Thường dùng doc values |
| numeric | price asc | Chọn kiểu số đủ miền giá trị |
| boolean | featured desc | Xác định rõ thứ tự true/false |
| geo_point | _geo_distance | Cần origin và unit |
| _score | _score desc | Dùng cho relevance |

Nếu sort theo field nghiệp vụ mà vẫn cần trả score trong SearchHit, kiểm tra tùy chọn track_scores phù hợp với API đang dùng. Việc sort theo field không tự động có nghĩa score được tính và trả về theo cách ứng dụng mong muốn.

### 4.1. Thứ tự asc và desc

Thứ tự của tie-breaker phải được chọn nhất quán:

- sort_id asc: khóa nhỏ hơn đứng trước khi các tiêu chí trước bằng nhau.
- sort_id desc: khóa lớn hơn đứng trước.

Cả hai đều tạo thứ tự tổng nếu khóa duy nhất. Quan trọng là mọi request trong cùng luồng phân trang phải dùng cùng field và cùng hướng sort.

### 4.2. Giá trị missing

Elasticsearch cho phép điều khiển vị trí của giá trị missing trong sort, ví dụ _first hoặc _last. Tuy nhiên, nếu tie-breaker bị thiếu, nhiều document có thể cùng nhận một giá trị missing và lại không có tiêu chí phân xử cuối cùng.

Vì vậy:

- Bắt buộc ghi tie-breaker cho mọi document.
- Kiểm tra dữ liệu cũ trước khi triển khai sort mới.
- Dùng missing policy cho field nghiệp vụ tùy chọn nếu cần.
- Không dựa vào missing policy để thay thế tính duy nhất của tie-breaker.

### 4.3. Sort trên field nhiều giá trị

Một field có thể chứa nhiều giá trị. Elasticsearch cần quy tắc chọn giá trị đại diện để sort, chẳng hạn min, max, avg hoặc median tùy kiểu field và API.

Ví dụ:

~~~json
{
  "sort": [
    {
      "ratings": {
        "order": "desc",
        "mode": "avg"
      }
    },
    {
      "sort_id": "asc"
    }
  ]
}
~~~

Nếu nhiều document có cùng giá trị avg, sort_id vẫn phân xử. Hãy chọn mode theo ý nghĩa nghiệp vụ; việc chọn min hay max có thể thay đổi đáng kể thứ hạng.

## 5. Sort ổn định trong Spring Data Elasticsearch

Spring Data Elasticsearch cho phép chỉ định sort bằng Spring Data Sort, Pageable hoặc query object. Với repository method trả Page, có thể đưa nhiều Order vào PageRequest:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

public Page<Article> findLatestArticles(int page, int size) {
    Sort sort = Sort.by(
            Sort.Order.desc("publishedAt"),
            Sort.Order.asc("sortId")
    );

    Pageable pageable = PageRequest.of(page, size, sort);
    return articleRepository.findByStatus("published", pageable);
}
~~~

Trong ví dụ, sort theo thuộc tính Java publishedAt rồi sortId. Spring Data dùng mapping metadata để chuyển property sang tên field Elasticsearch tương ứng, chẳng hạn published_at và sort_id theo annotation.

Repository:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ArticleRepository
        extends ElasticsearchRepository<Article, String> {

    Page<Article> findByStatus(String status, Pageable pageable);
}
~~~

Đây là ví dụ theo mô hình repository query method; entity cần có property status và mapping tương ứng. Tên property truyền vào Sort phải là property mà Spring Data mapping context nhận diện. Không nên truyền tên JSON field hoặc tên metadata tùy tiện nếu không khớp mapping.

### 5.1. Dùng sort với ElasticsearchOperations

Khi xây dựng query bằng ElasticsearchOperations, có thể đưa Sort vào query object:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("publishedAt"),
        Sort.Order.asc("sortId")
);

Query query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
                .field("title")
                .query("elasticsearch")
        ))
        .withSort(sort)
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<Article> hits =
        operations.search(query, Article.class);
~~~

API builder và cách kết hợp sort với pageable có thể khác theo release train Spring Data Elasticsearch. Hãy dùng một nguồn cấu hình sort duy nhất, tránh vô tình khai báo sort trong cả query DSL và Pageable với thứ tự ưu tiên không rõ ràng.

Với query native cần sort đặc thù của Elasticsearch, có thể tạo SortOptions từ Elasticsearch Java Client và truyền qua API NativeQuery mà phiên bản đang dùng hỗ trợ.

## 6. Tie-breaker và phân trang offset (from/size)

Phân trang offset sử dụng from và size:

~~~json
{
  "from": 20,
  "size": 10,
  "sort": [
    {"published_at": "desc"},
    {"sort_id": "asc"}
  ],
  "query": {
    "term": {
      "status": "published"
    }
  }
}
~~~

Request lấy 10 kết quả bắt đầu từ vị trí 20. Sort có tie-breaker giúp mỗi document có vị trí xác định trong cùng một trạng thái dữ liệu.

Offset pagination dễ triển khai và phù hợp với các trang đầu hoặc dữ liệu không thay đổi thường xuyên. Tuy nhiên, Elasticsearch phải xử lý các hit từ đầu đến offset rồi mới trả trang cần thiết. Chi phí tăng khi from lớn.

Elasticsearch thường giới hạn tổng from + size bằng index.max_result_window, mặc định phổ biến là 10.000. Tăng giới hạn không giải quyết căn bản chi phí của deep pagination và có thể tăng áp lực bộ nhớ.

### 6.1. Vì sao tie-breaker vẫn chưa đủ khi dữ liệu thay đổi?

Giả sử trang đầu được đọc khi có 100 bài. Sau đó một bài mới có published_at lớn hơn được thêm vào đầu danh sách. Nếu request trang hai dùng from = 20 trên trạng thái mới, vị trí các bài đã dịch chuyển. Dù sort_id là duy nhất, trang hai vẫn có thể lặp lại hoặc bỏ qua một bài so với trang đầu.

Tie-breaker bảo đảm thứ tự đầy đủ cho một trạng thái dữ liệu. Nó không đóng băng index giữa nhiều request. Muốn duyệt một tập kết quả nhất quán trong lúc dữ liệu thay đổi, cần PIT.

## 7. search_after cho phân trang sâu

search_after tiếp tục tìm kiếm từ sort values của hit cuối cùng ở trang trước, thay vì nhảy đến một offset lớn.

Giả sử sort:

~~~json
{
  "sort": [
    {"published_at": "desc"},
    {"sort_id": "asc"}
  ]
}
~~~

Mỗi hit trả về mảng sort chứa giá trị đã dùng để sắp xếp. Ví dụ:

~~~json
{
  "_id": "article-42",
  "_source": {
    "published_at": "2026-11-13T08:00:00Z",
    "sort_id": "article-42"
  },
  "sort": [
    "2026-11-13T08:00:00.000Z",
    "article-42"
  ]
}
~~~

Để lấy trang tiếp theo, truyền chính xác mảng sort của hit cuối cùng vào search_after:

~~~json
{
  "size": 20,
  "sort": [
    {"published_at": "desc"},
    {"sort_id": "asc"}
  ],
  "search_after": [
    "2026-11-13T08:00:00.000Z",
    "article-42"
  ],
  "query": {
    "term": {
      "status": "published"
    }
  }
}
~~~

Không tự tính lại sort values hoặc chỉ truyền giá trị của field đầu tiên. search_after cần đủ giá trị theo toàn bộ sort list và phải giữ nguyên thứ tự, kiểu dữ liệu, hướng sort cùng query giữa các request.

### 7.1. Luồng phân trang search_after

~~~text
Request trang đầu
   |
   v
Search với query + sort
   |
   v
Nhận hits và sort values
   |
   v
Lấy sort values của hit cuối
   |
   v
Request tiếp theo với search_after
   |
   v
Nhận trang tiếp theo
   |
   +---- lặp đến khi hết kết quả
~~~

search_after không dùng page number như from/size. Client cần giữ cursor là sort values của hit cuối trang trước. Vì vậy giao diện kiểu “đến trang 37” không tự nhiên bằng giao diện next/previous hoặc tải tiếp.

### 7.2. Tie-breaker vẫn cần thiết

Nếu sort list chỉ có published_at, nhiều hit có thể cùng giá trị. search_after có thể không xác định một điểm tiếp tục duy nhất giữa các hit đồng hạng. Bổ sung sort_id duy nhất giúp cursor xác định ranh giới chính xác:

~~~json
{
  "sort": [
    {"published_at": "desc"},
    {"sort_id": "asc"}
  ]
}
~~~

Với cùng published_at, sort_id xác định document nào đứng trước và document nào đứng sau cursor.

## 8. PIT kết hợp search_after để giữ góc nhìn nhất quán

Point in Time (PIT) tạo một góc nhìn nhất quán của index trong một khoảng thời gian. Khi dữ liệu mới được ghi hoặc index refresh trong lúc người dùng đang phân trang, các request sử dụng cùng PIT tiếp tục nhìn thấy cùng trạng thái dữ liệu.

PIT thường được dùng cùng search_after cho deep pagination:

1. Mở PIT trên index hoặc alias.
2. Gửi request đầu tiên với PIT, query và sort.
3. Lấy sort values của hit cuối.
4. Gửi request tiếp theo với cùng PIT và search_after.
5. Gia hạn keep_alive khi cần tiếp tục.
6. Đóng PIT khi hoàn tất.

### 8.1. Mở PIT

~~~http
POST /articles-read/_pit?keep_alive=1m
~~~

Response trả về ID của PIT. Giữ ID này ở phía client hoặc server session theo cách phù hợp với ứng dụng.

### 8.2. Request đầu tiên

~~~http
POST /_search
Content-Type: application/json

{
  "size": 20,
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "1m"
  },
  "query": {
    "term": {
      "status": "published"
    }
  },
  "sort": [
    {
      "published_at": {
        "order": "desc",
        "format": "strict_date_optional_time_nanos"
      }
    },
    {
      "sort_id": {
        "order": "asc"
      }
    }
  ]
}
~~~

Khi dùng PIT, không cần chỉ định index trong path _search vì PIT đã xác định tập index. Elasticsearch tự thêm _shard_doc làm tie-breaker nội bộ cho search sử dụng PIT, bảo đảm thứ tự duy nhất trong phạm vi PIT. Trường sort_id vẫn hữu ích để có thứ tự nghiệp vụ rõ ràng và ổn định giữa các lần tìm kiếm độc lập.

### 8.3. Request tiếp theo

Giả sử hit cuối của trang đầu có sort values:

~~~json
[
  "2026-11-12T15:30:00.000Z",
  "article-0099"
]
~~~

Request tiếp theo:

~~~http
POST /_search
Content-Type: application/json

{
  "size": 20,
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "1m"
  },
  "query": {
    "term": {
      "status": "published"
    }
  },
  "sort": [
    {
      "published_at": {
        "order": "desc",
        "format": "strict_date_optional_time_nanos"
      }
    },
    {
      "sort_id": {
        "order": "asc"
      }
    }
  ],
  "search_after": [
    "2026-11-12T15:30:00.000Z",
    "article-0099"
  ]
}
~~~

Hãy lấy sort values từ response thực tế, không tự dựng lại từ _source. Với các kiểu số, ngày giờ hoặc geo sort, giá trị trả về có thể có định dạng khác với cách ứng dụng lưu trong entity.

Nếu response trả về PIT ID mới, dùng ID mới nhất cho request tiếp theo. keep_alive là thời gian PIT cần được giữ sau request; nó không phải thời hạn lưu trữ vĩnh viễn.

### 8.4. Đóng PIT

Khi không cần phân trang tiếp, đóng PIT:

~~~http
DELETE /_pit
Content-Type: application/json

{
  "id": "PIT_ID"
}
~~~

PIT tiêu thụ tài nguyên vì Elasticsearch cần giữ các segment cần thiết cho góc nhìn nhất quán. Đặt keep_alive vừa đủ, đóng PIT khi hoàn tất và tránh tạo nhiều PIT tồn tại lâu không cần thiết.

## 9. Tie-breaker nội bộ _shard_doc và field nghiệp vụ

Khi dùng PIT, Elasticsearch thêm _shard_doc làm tie-breaker nội bộ nếu cần. _shard_doc kết hợp shard và thứ tự document trong Lucene, tạo thứ tự duy nhất trong phạm vi PIT.

Có hai mục tiêu khác nhau:

| Cơ chế | Mục tiêu |
|---|---|
| Field nghiệp vụ duy nhất như sort_id | Tạo thứ tự có ý nghĩa, dễ giải thích và có thể dùng giữa các phiên tìm kiếm |
| _shard_doc trong PIT | Tạo thứ tự duy nhất, hiệu quả cho việc duyệt kết quả trong cùng PIT |

_shard_doc không phải ID nghiệp vụ. Không lưu giá trị này vào entity và không dùng nó làm khóa lâu dài giữa các lần PIT. Vị trí document nội bộ có thể khác khi index được tái tạo hoặc thay đổi.

Nếu ứng dụng chỉ cần duyệt nhanh toàn bộ kết quả trong một PIT, sort theo _shard_doc có thể rất hiệu quả. Nếu cần thứ tự ưu tiên theo ngày, giá hoặc relevance, giữ các tiêu chí nghiệp vụ rồi để PIT cung cấp tie-breaker nội bộ cuối cùng hoặc thêm sort_id rõ ràng.

## 10. Tích hợp phân trang với Spring Data Elasticsearch

### 10.1. Phân trang offset qua Pageable

Với repository method thông thường:

~~~java
Page<Article> findByStatus(String status, Pageable pageable);
~~~

Service:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("publishedAt"),
        Sort.Order.asc("sortId")
);

Pageable pageable = PageRequest.of(0, 20, sort);
Page<Article> page =
        articleRepository.findByStatus("published", pageable);
~~~

Đây là cách đơn giản khi ứng dụng cần số trang và tổng số kết quả. Hãy giữ tie-breaker trong mọi request để thứ tự không mơ hồ khi nhiều bài có cùng ngày xuất bản.

### 10.2. search_after qua ElasticsearchOperations

Với phân trang sâu, Spring Data Elasticsearch cung cấp API query để làm việc với search_after và PIT trong các phiên bản hỗ trợ. Có thể hình dung quy trình:

~~~java
// Pseudocode: tên API cụ thể phụ thuộc phiên bản Spring Data Elasticsearch.
Query query = NativeQuery.builder()
        .withQuery(queryDsl)
        .withSort(sortOptions)
        .withPointInTime(pointInTime)
        .withSearchAfter(previousSortValues)
        .withMaxResults(20)
        .build();

SearchHits<Article> hits =
        operations.search(query, Article.class);
~~~

Trong đó:

- pointInTime là PIT hiện hành.
- previousSortValues là mảng sort values lấy từ hit cuối của trang trước.
- sortOptions là cùng một danh sách sort cho mọi request.
- max results là số hit cần lấy trong trang.

Đây là mã giả nhằm mô tả các thành phần cần giữ. Tên builder method, kiểu PointInTime, cách lấy sort values và cách mở/đóng PIT đã thay đổi giữa các release train. Kiểm tra Javadoc đúng phiên bản trong dự án trước khi triển khai.

### 10.3. Lấy cursor từ SearchHit

Với search_after, ứng dụng cần đọc sort values của hit cuối. SearchHit và SearchHits của Spring Data cung cấp thông tin hit, nhưng API truy cập sort values có thể thay đổi theo phiên bản. Nếu abstraction đang dùng không bộc lộ đầy đủ dữ liệu cần thiết, có thể dùng Elasticsearch Java Client trực tiếp cho luồng cursor hoặc bổ sung adapter ở tầng repository.

Không nên chỉ giữ ID của hit cuối nếu sort list có nhiều field. Cursor phải chứa toàn bộ sort values đúng thứ tự để Elasticsearch tiếp tục chính xác.

## 11. Những lưu ý khi phân trang trên nhiều index hoặc alias

Khi query qua alias nhiều index, hãy bảo đảm:

- Các field sort tồn tại trên mọi index liên quan.
- Kiểu mapping của field sort tương thích giữa các index.
- Tie-breaker duy nhất trên toàn bộ tập document, không chỉ trong từng index.
- Tên field và hướng sort không thay đổi giữa các trang.
- PIT được mở trên đúng alias hoặc index pattern.

Nếu một index cũ không có sort_id, các document của index đó có thể nhận missing value và làm mất tính duy nhất. Hãy backfill field trước khi bật sort mới hoặc dùng một chiến lược chuyển tiếp có kiểm soát.

Khi field sort có kiểu khác nhau giữa các index, Elasticsearch có thể cần numeric_type hoặc format để thống nhất cách sort; khả năng và cú pháp cụ thể phụ thuộc loại field. Tốt nhất là chuẩn hóa mapping giữa các index ngay từ index template.

## 12. Những thay đổi dữ liệu ảnh hưởng đến sort

Ngay cả khi có tie-breaker, sort chỉ ổn định nếu các giá trị dùng để sắp xếp không đổi trong phạm vi đang duyệt.

Ví dụ:

- publishedAt bị cập nhật sau khi trang đầu đã trả về.
- popularity thay đổi liên tục và đang được dùng làm tiêu chí sort chính.
- sort_id bị sửa hoặc tái sử dụng.
- Document bị xóa hoặc thêm mới giữa các request offset.

PIT giải quyết việc thay đổi index trong lúc phân trang bằng cách giữ góc nhìn nhất quán. Tuy nhiên, PIT không làm cho một field sort thay đổi trong nguồn dữ liệu được coi là bất biến ở các PIT mới. Nếu cần thứ tự ổn định qua nhiều phiên tìm kiếm, các field sort nghiệp vụ phải có quy tắc cập nhật rõ ràng.

Với popularity thay đổi liên tục, hãy quyết định liệu người dùng cần một snapshot kết quả ổn định trong phiên hiện tại hay cần thứ hạng cập nhật liên tục. Không thể đồng thời giữ cursor ổn định và thay đổi thứ tự liên tục mà không có quy tắc chuyển trang rõ ràng.

## 13. Kiểm thử thứ tự ổn định

Một bộ kiểm thử nên tạo nhiều document có cùng giá trị của tiêu chí chính để chứng minh tie-breaker hoạt động:

~~~json
[
  {"published_at": "2026-11-01T10:00:00Z", "sort_id": "a-003"},
  {"published_at": "2026-11-01T10:00:00Z", "sort_id": "a-001"},
  {"published_at": "2026-11-01T10:00:00Z", "sort_id": "a-002"},
  {"published_at": "2026-10-31T10:00:00Z", "sort_id": "a-004"}
]
~~~

Với sort published_at desc và sort_id asc, thứ tự mong đợi:

~~~text
1. a-001 (2026-11-01)
2. a-002 (2026-11-01)
3. a-003 (2026-11-01)
4. a-004 (2026-10-31)
~~~

Các tình huống nên kiểm tra:

1. Nhiều document có cùng giá trị sort chính.
2. Tie-breaker duy nhất và có mặt trên mọi document.
3. Hai request lặp lại trên cùng trạng thái index cho cùng thứ tự.
4. Chia kết quả thành nhiều trang không trùng hoặc thiếu document.
5. Thêm document mới giữa hai request offset để thấy ảnh hưởng của refresh.
6. Thêm document mới giữa hai request PIT + search_after để xác nhận PIT giữ tập kết quả.
7. Field sort missing hoặc null.
8. Alias bao gồm nhiều index có ID trùng cục bộ.
9. Sort nhiều field có hướng asc/desc khác nhau.
10. Field sort có kiểu mapping nhất quán giữa các index.

### 13.1. So sánh hai cách phân trang

| Tiêu chí | from/size + tie-breaker | PIT + search_after |
|---|---|---|
| Dễ triển khai | Dễ | Phức tạp hơn |
| Trang đầu và các trang nông | Phù hợp | Phù hợp |
| Deep pagination | Tốn chi phí tăng theo offset | Phù hợp hơn |
| Giới hạn result window | Bị giới hạn bởi max_result_window | Không dùng offset lớn |
| Ổn định khi index thay đổi | Không bảo đảm giữa các request | Giữ góc nhìn nhất quán trong PIT |
| Cần lưu cursor | Không | Có, sort values của hit cuối |
| Quản lý vòng đời | Đơn giản | Phải gia hạn và đóng PIT |

Tie-breaker hữu ích với cả hai cách. PIT + search_after giải quyết thêm vấn đề nhất quán giữa các request và hiệu quả phân trang sâu.

## 14. Các lỗi thường gặp

### 14.1. Chỉ sort theo field không duy nhất

Nhiều document có cùng ngày, giá hoặc score. Bổ sung một field phân xử duy nhất ở cuối sort list.

### 14.2. Dùng _id làm tie-breaker sort

_id là metadata định danh và không phải field sort tổng quát. Sao chép ID vào keyword hoặc numeric field có doc values.

### 14.3. Tie-breaker chỉ duy nhất trong một index

Alias có thể truy vấn nhiều index. Hãy bảo đảm khóa duy nhất trên toàn bộ tập kết quả.

### 14.4. Tie-breaker bị thiếu ở document cũ

Missing value không bảo đảm thứ tự tổng. Backfill dữ liệu cũ hoặc dùng chiến lược migration.

### 14.5. Dùng search_after nhưng chỉ truyền giá trị sort đầu tiên

Cursor phải có đủ sort values của hit cuối theo đúng thứ tự sort list.

### 14.6. Thay đổi query hoặc sort giữa các trang

Mọi request tiếp theo phải giữ cùng query và sort trong một luồng search_after. Nếu đổi tiêu chí, cursor cũ không còn ý nghĩa.

### 14.7. Dùng search_after mà không có PIT khi index đang thay đổi

Tie-breaker tạo thứ tự đầy đủ nhưng không giữ snapshot dữ liệu. Nếu cần duyệt nhất quán, dùng PIT.

### 14.8. Giữ PIT quá lâu

PIT giữ tài nguyên và segment cần thiết. Dùng keep_alive vừa đủ, gia hạn theo tiến độ và đóng PIT sau khi xong.

### 14.9. Tăng max_result_window để giải quyết mọi trường hợp

Tăng giới hạn from/size có thể làm tăng tải bộ nhớ và không giải quyết sự dịch chuyển trang khi index thay đổi. Với deep pagination, cân nhắc search_after.

## 15. Quy trình thiết kế sort và phân trang

Khi xây một API tìm kiếm có phân trang:

1. Xác định thứ tự nghiệp vụ chính, ví dụ relevance, ngày mới nhất hoặc giá thấp nhất.
2. Xác định trường phân xử duy nhất và bất biến.
3. Bảo đảm tie-breaker có mapping sortable và giá trị trên mọi document.
4. Nếu tìm trên nhiều index, bảo đảm khóa duy nhất toàn cục và mapping tương thích.
5. Khai báo toàn bộ sort fields theo thứ tự ưu tiên.
6. Chọn from/size cho trang nông hoặc PIT + search_after cho deep pagination.
7. Với PIT, giữ PIT ID và sort values ở phía điều phối request.
8. Không thay đổi query/sort trong cùng một cursor session.
9. Đặt keep_alive phù hợp và đóng PIT khi hoàn tất.
10. Kiểm thử đồng hạng, dữ liệu thiếu, index refresh và alias nhiều index.

Ví dụ quyết định:

| Nhu cầu | Thiết kế |
|---|---|
| Danh sách bài mới nhất, trang đầu | published_at desc, sort_id asc |
| Điểm relevance có thể bằng nhau | _score desc, sort_id asc |
| Giá thấp nhất trước | price asc, sort_id asc |
| Phân trang nông với số trang | Pageable/from-size và tie-breaker |
| Duyệt hàng trăm nghìn kết quả | PIT + search_after |
| Tìm trên alias nhiều index | Tie-breaker duy nhất toàn cục và mapping đồng nhất |

## 16. Kết luận

Khi nhiều document có cùng giá trị ở field sort chính, Elasticsearch cần thêm một tiêu chí để xác định thứ tự giữa chúng. Một tie-breaker duy nhất, ổn định, luôn có giá trị và hỗ trợ sort sẽ tạo thứ tự tổng. Thông thường, ứng dụng sao chép ID vào một field keyword hoặc numeric có doc values; không dựa vào _id để sort.

Multi-field sort cho phép kết hợp tiêu chí nghiệp vụ như ngày, giá hoặc score với tie-breaker ở cuối. Cách này giúp thứ tự xác định trong một trạng thái index và làm cho phân trang dễ dự đoán hơn.

Với phân trang offset, tie-breaker không ngăn được trang dịch chuyển khi index thay đổi giữa các request. Với phân trang sâu hoặc cần một tập kết quả nhất quán, dùng PIT cùng search_after, giữ nguyên query và sort, truyền đầy đủ sort values của hit cuối và đóng PIT sau khi hoàn tất. Trong Spring Data Elasticsearch, có thể dùng Pageable cho phân trang thông thường và API NativeQuery/search_after/PIT của đúng phiên bản cho luồng cursor.
