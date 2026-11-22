# `minimum_should_match` và điều kiện bắt buộc khi kết hợp `bool`

Elasticsearch Bool Query cho phép kết hợp nhiều điều kiện tìm kiếm bằng bốn nhóm clause: `must`, `filter`, `should` và `must_not`. `must` và `filter` biểu diễn điều kiện bắt buộc; `must_not` loại document khỏi kết quả; `should` biểu diễn điều kiện lựa chọn hoặc điều kiện giúp tăng điểm relevance. Khi một query có cả `should` với `must` hoặc `filter`, các clause `should` mặc định có thể trở thành tùy chọn. Đây là nguyên nhân thường gặp khiến một truy vấn trả về document chỉ thỏa điều kiện lọc mà không khớp bất kỳ nội dung nào trong các nhánh `should`.

Thuộc tính `minimum_should_match` cho phép quy định số lượng clause `should` tối thiểu phải khớp. Kết hợp đúng thuộc tính này với `must` và `filter` giúp diễn đạt rõ yêu cầu như: sản phẩm phải thuộc danh mục đã chọn, phải đang hoạt động và phải khớp ít nhất hai trong bốn cụm từ tìm kiếm.

Bài học này giải thích semantics của từng Bool clause, quy tắc mặc định của `should`, các dạng giá trị `minimum_should_match`, phạm vi áp dụng trong bool lồng nhau và sự khác biệt với thuộc tính cùng tên trong `match` query.

## 1. Cấu trúc Bool Query

Một Bool Query có thể chứa bốn nhóm clause:

```json
{
  "bool": {
    "must": [],
    "filter": [],
    "should": [],
    "must_not": [],
    "minimum_should_match": 1
  }
}
```

| Clause | Điều kiện | Ảnh hưởng tới `_score` |
|---|---|---|
| `must` | Mọi clause trong nhóm phải khớp | Có tính điểm relevance |
| `filter` | Mọi clause trong nhóm phải khớp | Không tính điểm relevance |
| `should` | Số clause khớp phải đạt ngưỡng `minimum_should_match` | Clause khớp có thể đóng góp điểm |
| `must_not` | Document khớp clause bị loại khỏi kết quả | Không tính điểm relevance |

Các clause cùng tồn tại trong một bool được kết hợp theo logic:

- Mọi `must` phải khớp.
- Mọi `filter` phải khớp.
- Không clause `must_not` nào được khớp.
- Số clause `should` khớp phải đáp ứng `minimum_should_match` nếu có ngưỡng.

Có thể hình dung:

```text
Document
   |
   +--> Tất cả MUST khớp? -------- Không --> Loại
   |
   +--> Tất cả FILTER khớp? ------ Không --> Loại
   |
   +--> Có MUST_NOT khớp? -------- Có ----> Loại
   |
   +--> Số SHOULD khớp đạt ngưỡng? Không --> Loại
   |
   +--> Giữ lại kết quả và tính relevance từ các clause có scoring
```

`minimum_should_match` chỉ điều khiển nhóm `should` của Bool Query mà nó được khai báo. Nó không thay đổi số lượng điều kiện `must`, `filter` hoặc `must_not`.

## 2. Phân biệt điều kiện bắt buộc và điều kiện lựa chọn

Giả sử cần tìm sản phẩm theo yêu cầu:

- Sản phẩm phải có `active = true`.
- Sản phẩm phải thuộc category `keyboards`.
- Nội dung tên sản phẩm nên khớp `mechanical` hoặc `gaming`.

Hai điều kiện đầu là bắt buộc, hai cụm từ cuối là các lựa chọn. Query có thể viết:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } }
      ],
      "should": [
        { "match": { "name": "mechanical" } },
        { "match": { "name": "gaming" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

Document phải vượt qua cả hai filter và khớp ít nhất một trong hai `should`. Nếu bỏ `minimum_should_match`, mặc định của bool có `filter` là `0`; khi đó document chỉ cần đúng category và trạng thái active, kể cả khi tên không chứa `mechanical` hoặc `gaming`.

### 2.1. `must` và `filter` đều bắt buộc nhưng khác nhau về scoring

`must` và `filter` đều yêu cầu clause phải khớp. Khác biệt chính là scoring:

- Dùng `must` cho điều kiện tìm kiếm toàn văn cần ảnh hưởng đến thứ hạng, ví dụ tên hoặc mô tả phải phù hợp với từ khóa.
- Dùng `filter` cho điều kiện cấu trúc hoặc điều kiện chính xác như trạng thái, category, tenant, khoảng giá hoặc ngày tháng.

Ví dụ kết hợp tìm kiếm toàn văn với điều kiện lọc:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "mechanical keyboard"
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } },
        { "range": { "priceInCents": { "lte": 3000000 } } }
      ]
    }
  }
}
```

Ở đây, document phải khớp nội dung tên và cả ba điều kiện filter. Điểm `_score` chủ yếu phản ánh mức độ phù hợp của `match`; các filter không cộng điểm.

### 2.2. `must_not` là điều kiện loại trừ

Ví dụ loại sản phẩm đã ngừng kinh doanh:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } }
      ],
      "must_not": [
        { "term": { "status": "DISCONTINUED" } }
      ]
    }
  }
}
```

Document phải có `active = true` và không được có `status = DISCONTINUED`. `must_not` không phải một điều kiện tích cực cần khớp; nó loại các document phù hợp với clause bên trong.

## 3. Quy tắc mặc định của `should`

Đây là quy tắc cần nhớ nhất khi kết hợp Bool Query:

- Nếu bool có ít nhất một `should` và **không có** `must` hoặc `filter`, mặc định cần khớp ít nhất một `should`.
- Nếu bool có `must` hoặc `filter`, mặc định `minimum_should_match` là `0`. Các `should` khi đó là tùy chọn.

`must_not` không làm thay đổi quy tắc mặc định này.

### 3.1. Chỉ có `should`: mặc định phải khớp ít nhất một

```json
{
  "query": {
    "bool": {
      "should": [
        { "match": { "name": "mechanical" } },
        { "match": { "name": "gaming" } },
        { "match": { "description": "quiet typing" } }
      ]
    }
  }
}
```

Không có `must` hoặc `filter`, vì vậy Elasticsearch mặc định yêu cầu ít nhất một trong ba `should` khớp. Về logic, đây là một nhóm điều kiện OR.

Dù vậy, nên khai báo `minimum_should_match` tường minh nếu số lượng nhánh là một phần quan trọng của yêu cầu nghiệp vụ. Cấu hình tường minh giúp người đọc hiểu ngay điều kiện và tránh thay đổi hành vi ngoài ý muốn khi query được mở rộng.

### 3.2. Có `must` hoặc `filter`: `should` mặc định là tùy chọn

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } }
      ],
      "should": [
        { "match": { "name": "mechanical" } },
        { "match": { "name": "gaming" } }
      ]
    }
  }
}
```

Vì bool có `filter`, ngưỡng mặc định là `0`. Một sản phẩm chỉ cần active là có thể được trả về dù không khớp tên với từ nào. Nếu có khớp `mechanical` hoặc `gaming`, các clause đó vẫn có thể làm tăng `_score` và đưa sản phẩm lên vị trí cao hơn.

Đây là hành vi phù hợp khi `should` chỉ dùng để boost kết quả. Nếu yêu cầu nghiệp vụ nói rằng sản phẩm phải khớp ít nhất một cụm từ, cần thêm:

```json
"minimum_should_match": 1
```

### 3.3. Bảng hành vi mặc định

| `must` | `filter` | `should` | Ngưỡng mặc định của `should` |
|---|---|---|---:|
| Không | Không | Có | 1 |
| Có | Không | Có | 0 |
| Không | Có | Có | 0 |
| Có | Có | Có | 0 |
| Bất kỳ | Bất kỳ | Không | Không áp dụng |

Nếu không có `should`, `minimum_should_match` không có tác dụng thực tế. Nếu có `must` hoặc `filter` và không đặt ngưỡng, các `should` chỉ ảnh hưởng scoring khi khớp, không quyết định document có được giữ lại hay không.

## 4. `minimum_should_match` là gì?

`minimum_should_match` quy định số lượng clause trong mảng `should` tối thiểu phải khớp để Bool Query được xem là khớp.

Ví dụ có bốn clause `should`:

```json
{
  "bool": {
    "should": [
      { "match": { "name": "mechanical" } },
      { "match": { "name": "gaming" } },
      { "match": { "description": "quiet" } },
      { "match": { "description": "wireless" } }
    ],
    "minimum_should_match": 2
  }
}
```

Document cần khớp ít nhất hai trong bốn clause. Một clause có thể là một `match`, `term`, `range` hoặc một bool lồng; ở cấp bool hiện tại, mỗi phần tử trực tiếp trong mảng `should` được tính là một clause.

`minimum_should_match` không đếm số từ trong một câu và cũng không đếm số document. Nó đếm số clause `should` trực tiếp của Bool Query đó có kết quả khớp.

## 5. Các dạng giá trị của `minimum_should_match`

Elasticsearch hỗ trợ nhiều dạng biểu diễn ngưỡng. Có thể dùng số nguyên, số nguyên âm, phần trăm, phần trăm âm hoặc biểu thức điều kiện.

### 5.1. Số nguyên dương: số clause tối thiểu phải khớp

```json
"minimum_should_match": 2
```

Yêu cầu ít nhất hai clause `should` khớp, bất kể có bao nhiêu clause trong danh sách. Nếu có năm clause, vẫn chỉ cần hai clause.

### 5.2. Số nguyên âm: số clause được phép không khớp

```json
"minimum_should_match": -1
```

Giá trị `-1` có nghĩa là có thể bỏ lỡ một clause; tất cả clause còn lại phải khớp. Nếu có năm clause, cần khớp ít nhất bốn.

Với `-2`, có thể bỏ lỡ hai clause. Nếu có năm clause, cần khớp ít nhất ba.

### 5.3. Phần trăm dương

```json
"minimum_should_match": "75%"
```

Phần trăm dương tính số clause tối thiểu phải khớp. Kết quả phần trăm được làm tròn xuống.

Ví dụ có năm clause:

```text
floor(5 * 75%) = floor(3.75) = 3
```

Do đó `75%` yêu cầu ít nhất ba trong năm clause khớp.

### 5.4. Phần trăm âm

```json
"minimum_should_match": "-25%"
```

Phần trăm âm tính số clause được phép không khớp, sau đó lấy tổng số clause trừ đi số được phép bỏ lỡ.

Với năm clause:

```text
Số được phép bỏ lỡ = floor(5 * 25%) = 1
Số tối thiểu phải khớp = 5 - 1 = 4
```

Vì vậy `-25%` yêu cầu ít nhất bốn trong năm clause khớp.

### 5.5. Vì sao `75%` và `-25%` khác nhau?

Với bốn clause, hai biểu thức đều yêu cầu ba clause khớp. Nhưng với năm clause, kết quả khác nhau:

| Số clause `should` | `75%` yêu cầu khớp | `-25%` yêu cầu khớp |
|---:|---:|---:|
| 4 | 3 | 3 |
| 5 | 3 | 4 |
| 8 | 6 | 6 |
| 9 | 6 | 7 |

Phần trăm dương tính số lượng cần khớp; phần trăm âm tính số lượng được phép thiếu. Hai cách biểu diễn chỉ tình cờ cho cùng kết quả ở một số số lượng clause.

### 5.6. Biểu thức điều kiện

Khi số clause thay đổi nhiều, có thể dùng điều kiện theo ngưỡng:

```json
"minimum_should_match": "2<-25% 9<-3"
```

Biểu thức được đọc như sau:

- Nếu có tối đa hai clause, yêu cầu tất cả phải khớp.
- Nếu có từ ba đến chín clause, cho phép bỏ lỡ 25% số clause.
- Nếu có hơn chín clause, cho phép bỏ lỡ ba clause.

Các điều kiện được viết theo số lượng clause tăng dần, cách nhau bằng dấu cách. Mỗi điều kiện có dạng `<số clause><điều kiện áp dụng khi vượt ngưỡng`.

Một ví dụ khác:

```json
"minimum_should_match": "3<90%"
```

Nếu có ba clause trở xuống, yêu cầu tất cả khớp. Nếu có nhiều hơn ba clause, yêu cầu 90% số clause khớp (làm tròn xuống theo quy tắc của phần trăm dương).

Biểu thức điều kiện giúp thiết lập ngưỡng chặt hơn với danh sách nhỏ nhưng linh hoạt hơn với danh sách lớn. Hãy thử các giá trị ở hai phía ngưỡng để xác nhận hành vi mong muốn.

## 6. Ví dụ kết hợp điều kiện bắt buộc và `minimum_should_match`

Giả sử một trang thương mại điện tử cần tìm sản phẩm theo yêu cầu:

1. Sản phẩm phải đang hoạt động.
2. Sản phẩm phải thuộc category được chọn.
3. Giá không vượt quá ngân sách.
4. Nội dung phải khớp ít nhất hai trong bốn cụm từ liên quan.
5. Những kết quả khớp nhiều cụm từ hơn có thể có điểm relevance cao hơn.

Query:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } },
        { "range": { "priceInCents": { "lte": 3000000 } } }
      ],
      "should": [
        { "match": { "name": "mechanical" } },
        { "match": { "name": "gaming" } },
        { "match": { "description": "hot swap" } },
        { "match": { "description": "wireless" } }
      ],
      "minimum_should_match": 2
    }
  }
}
```

Document chỉ được trả về nếu thỏa cả ba filter và ít nhất hai trong bốn clause `should`. Các clause `should` khớp vẫn đóng góp điểm relevance, vì vậy sản phẩm khớp ba hoặc bốn cụm từ có thể được xếp hạng cao hơn sản phẩm chỉ khớp hai cụm từ, tùy điểm số của từng query.

### 6.1. Khi chỉ cần một điều kiện toàn văn bắt buộc

Nếu tất cả sản phẩm phải khớp một truy vấn tên, nhưng có thể khớp thêm các tín hiệu phụ để tăng điểm:

```json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "mechanical keyboard" } }
      ],
      "filter": [
        { "term": { "active": true } }
      ],
      "should": [
        { "match": { "description": "gaming" } },
        { "term": { "featured": true } }
      ],
      "minimum_should_match": 0
    }
  }
}
```

Ở đây `minimum_should_match: 0` nói rõ hai tín hiệu phụ chỉ dùng để tăng điểm, không phải điều kiện bắt buộc. Nếu bỏ thuộc tính này thì hành vi mặc định cũng là 0 vì bool có `must` và `filter`.

### 6.2. Khi cần ít nhất một trong các lựa chọn

Nếu sản phẩm phải khớp ít nhất một nhánh trong nhóm từ khóa thay thế:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } }
      ],
      "should": [
        { "match": { "name": "keyboard" } },
        { "match": { "name": "keypad" } },
        { "match": { "description": "typing device" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

Document phải active và khớp ít nhất một trong ba nhánh. Đây là cách kết hợp phổ biến giữa điều kiện bắt buộc và nhóm từ khóa OR.

## 7. `minimum_should_match` trong Bool Query lồng nhau

Bool Query có thể lồng nhau. Mỗi bool có nhóm `should` và ngưỡng riêng. `minimum_should_match` chỉ áp dụng cho những clause `should` trực tiếp thuộc bool nơi nó được khai báo.

Ví dụ: sản phẩm phải active; đồng thời phải thỏa ít nhất một trong hai nhóm:

- Tên khớp `mechanical` hoặc `gaming`.
- Mô tả khớp `wireless` hoặc `quiet`.

Query:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } }
      ],
      "must": [
        {
          "bool": {
            "should": [
              { "match": { "name": "mechanical" } },
              { "match": { "name": "gaming" } }
            ],
            "minimum_should_match": 1
          }
        }
      ],
      "should": [
        {
          "bool": {
            "should": [
              { "match": { "description": "wireless" } },
              { "match": { "description": "quiet" } }
            ],
            "minimum_should_match": 1
          }
        }
      ],
      "minimum_should_match": 0
    }
  }
}
```

Bool bên trong `must` yêu cầu tên khớp ít nhất một trong hai từ. Bool bên trong `should` yêu cầu mô tả khớp ít nhất một trong hai từ, nhưng toàn bộ nhóm mô tả là tùy chọn ở bool ngoài vì `minimum_should_match` ngoài bằng 0. Nếu khớp, nhóm mô tả có thể tăng điểm.

Ở bool ngoài, nested bool trong mảng `should` được tính là một clause. Elasticsearch không đếm riêng hai `match` bên trong nested bool khi tính ngưỡng của bool ngoài.

### 7.1. Đặt ngưỡng ở sai cấp sẽ làm thay đổi logic

Ví dụ sau yêu cầu ít nhất hai nhánh trực tiếp ở bool ngoài khớp:

```json
{
  "bool": {
    "should": [
      { "bool": { "should": [{ "match": { "name": "keyboard" } }] } },
      { "bool": { "should": [{ "match": { "description": "wireless" } }] } },
      { "term": { "featured": true } }
    ],
    "minimum_should_match": 2
  }
}
```

Ba nhánh trực tiếp ở đây là hai nested bool và một `term`. `minimum_should_match: 2` đếm ba nhánh đó, không đếm các `match` bên trong hai nested bool.

Khi query lồng nhau phức tạp, hãy thụt lề và đặt `minimum_should_match` ngay cạnh mảng `should` mà nó điều khiển. Điều này giúp tránh nhầm ngưỡng của bool cha với ngưỡng của bool con.

## 8. Phân biệt `minimum_should_match` của bool với `match`

Elasticsearch cũng có thuộc tính `minimum_should_match` bên trong `match` query. Tên giống nhau nhưng phạm vi áp dụng khác nhau.

### 8.1. `minimum_should_match` của bool

Nó đếm số query clause trực tiếp trong mảng `should` của Bool Query:

```json
{
  "bool": {
    "should": [
      { "match": { "name": "mechanical" } },
      { "match": { "description": "quiet" } },
      { "term": { "category": "keyboards" } }
    ],
    "minimum_should_match": 2
  }
}
```

Document phải khớp ít nhất hai trong ba clause.

### 8.2. `minimum_should_match` của match query

Một `match` query phân tích chuỗi thành nhiều term. Thuộc tính cùng tên trong `match` query điều khiển số term được phân tích tối thiểu phải khớp:

```json
{
  "match": {
    "description": {
      "query": "quiet mechanical keyboard",
      "minimum_should_match": "2"
    }
  }
}
```

Nếu analyzer tạo ra ba term, query yêu cầu ít nhất hai term khớp theo semantics của `match` query. Đây không phải là số nhánh `should` trong Bool Query.

### 8.3. Có thể dùng cả hai cấp trong một query

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } }
      ],
      "should": [
        {
          "match": {
            "name": {
              "query": "mechanical gaming keyboard",
              "minimum_should_match": "2"
            }
          }
        },
        { "match": { "description": "wireless" } },
        { "term": { "featured": true } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

Trong ví dụ:

- `minimum_should_match: 2` bên trong `match` yêu cầu ít nhất hai term của chuỗi tên khớp.
- `minimum_should_match: 1` bên ngoài yêu cầu ít nhất một trong ba clause `should` cấp bool khớp.

Hai ngưỡng hoạt động độc lập ở hai cấp query khác nhau.

## 9. Dùng `@Query` trên Spring Data Elasticsearch Repository

Có thể khai báo Bool Query trực tiếp bằng annotation `@Query` trên repository method:

```java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "bool": {
            "filter": [
              { "term": { "active": true } },
              { "term": { "category": "?0" } }
            ],
            "should": [
              { "match": { "name": "?1" } },
              { "match": { "description": "?1" } },
              { "term": { "featured": true } }
            ],
            "minimum_should_match": 2
          }
        }
        """)
    List<Product> searchActiveProducts(
            String category,
            String text);
}
```

`?0` là category, `?1` là chuỗi tìm kiếm. Hai filter luôn bắt buộc. Trong ba clause `should`, document phải khớp ít nhất hai. Query JSON trong `@Query` là query clause được Spring Data đặt vào phần `query` của search request; không thêm một wrapper `query` nữa bên trong annotation.

Nếu repository method nhận thêm `Pageable`, Spring Data có thể áp dụng phân trang và sắp xếp theo contract của query method:

```java
@Query("""
    {
      "bool": {
        "filter": [
          { "term": { "active": true } },
          { "term": { "category": "?0" } }
        ],
        "should": [
          { "match": { "name": "?1" } },
          { "match": { "description": "?1" } }
        ],
        "minimum_should_match": 1
      }
    }
    """)
Page<Product> search(
        String category,
        String text,
        Pageable pageable);
```

Các placeholder phải đặt đúng kiểu JSON. Category và text là chuỗi nên được quote; ngưỡng là số nên không quote. Hãy kiểm tra query đã bind trong integration test nếu có collection, SpEL hoặc tham số phức tạp.

## 10. Dùng `CriteriaQuery` hoặc `NativeQuery` khi cần query động

`@Query` phù hợp với query có cấu trúc tương đối cố định. Nếu số lượng điều kiện `should` hoặc ngưỡng thay đổi theo request, xây query bằng Java có thể dễ bảo trì hơn.

`CriteriaQuery` cung cấp abstraction fluent cho một số điều kiện phổ biến. Với các cấu trúc Bool Query nâng cao hoặc tùy chọn Query DSL cần kiểm soát chính xác, `NativeQuery` cho phép dùng query builder của Elasticsearch Java API Client.

Ví dụ khái niệm dùng native bool query:

```java
// Build a co.elastic.clients.elasticsearch._types.query_dsl.Query
// with a BoolQuery containing filter, should and minimumShouldMatch.
// Pass it to NativeQuery.builder().withQuery(query).build().
// Execute the result through ElasticsearchOperations.search(...).
```

Tên builder và chữ ký method của Elasticsearch Java API Client phụ thuộc phiên bản client mà Spring Data release train sử dụng. Khi triển khai, dùng Javadoc của dependency thực tế; không thêm một major version client khác chỉ để sao chép ví dụ.

## 11. Cách tính ngưỡng trong các tình huống thực tế

Giả sử một query có tám clause `should`. Bảng dưới đây cho thấy số clause tối thiểu phải khớp với một số cấu hình:

| Giá trị | Số clause tối thiểu phải khớp | Số được phép không khớp |
|---|---:|---:|
| `1` | 1 | 7 |
| `3` | 3 | 5 |
| `-1` | 7 | 1 |
| `-2` | 6 | 2 |
| `75%` | 6 | 2 |
| `-25%` | 6 | 2 |
| `100%` | 8 | 0 |

Với tám clause, `75%` và `-25%` cùng cho kết quả sáu. Với năm clause, hai biểu thức khác nhau như đã trình bày ở phần trước.

### 11.1. Khi nào chọn số nguyên?

Dùng số nguyên khi yêu cầu nghiệp vụ có số lượng rõ ràng, ví dụ “phải khớp ít nhất hai nhánh trong danh sách”.

### 11.2. Khi nào chọn phần trăm?

Dùng phần trăm khi số lượng clause thay đổi nhưng muốn giữ tỷ lệ khớp tương đối ổn định. Ví dụ query tạo nhiều nhánh theo danh sách từ đồng nghĩa hoặc trường tìm kiếm.

### 11.3. Khi nào chọn giá trị âm?

Dùng số âm khi yêu cầu được diễn đạt tự nhiên theo số nhánh có thể bỏ lỡ, ví dụ “phải khớp tất cả trừ tối đa một nhánh”.

### 11.4. Khi nào dùng điều kiện?

Dùng biểu thức điều kiện khi danh sách nhỏ cần chặt chẽ hơn danh sách lớn. Ví dụ với tối đa hai lựa chọn phải khớp tất cả, nhưng khi có nhiều lựa chọn thì cho phép bỏ lỡ một tỷ lệ hoặc số lượng cố định.

Không nên chọn giá trị chỉ vì nó tạo ra nhiều kết quả hơn hoặc ít kết quả hơn trong một truy vấn thử nghiệm. Hãy xác định rõ ý nghĩa nghiệp vụ, sau đó kiểm thử với document khớp 0, 1, đúng ngưỡng và vượt ngưỡng.

## 12. Những lỗi thường gặp

### Quên `minimum_should_match` khi bool có `filter`

Đây là lỗi phổ biến nhất. Người viết nghĩ rằng `should` là lựa chọn OR bắt buộc, nhưng vì bool có `filter`, ngưỡng mặc định trở thành 0. Document chỉ cần thỏa filter vẫn được trả về. Hãy đặt `minimum_should_match: 1` nếu cần ít nhất một nhánh `should`.

### Dùng `must` thay cho `should` khi muốn OR

Nếu đưa nhiều nhánh vào `must`, tất cả đều phải khớp. Muốn một trong nhiều lựa chọn, đặt chúng vào `should` và quy định ngưỡng phù hợp.

### Dùng `minimum_should_match` để thay thế điều kiện bắt buộc

Nếu một điều kiện luôn phải đúng, đặt nó trong `must` hoặc `filter`. Không đưa điều kiện bắt buộc vào `should` rồi hy vọng ngưỡng sẽ vô tình bảo đảm nó, đặc biệt khi nhóm `should` có nhiều lựa chọn khác.

### Nghĩ `must_not` làm `should` trở thành bắt buộc

`must_not` chỉ loại document khớp clause. Nó không làm thay đổi quy tắc mặc định của `should`; nếu bool không có `must` hoặc `filter`, mặc định vẫn là ít nhất một `should`.

### Đặt `minimum_should_match` ở bool cha thay vì bool con

Ngưỡng chỉ đếm các clause `should` trực tiếp trong bool chứa nó. Với nested bool, đặt ngưỡng ở đúng cấp cần kiểm soát.

### Nhầm số clause với số từ

Bool `minimum_should_match` đếm clause trong mảng `should`. Nếu một clause là `match` chứa ba từ, nó vẫn chỉ là một clause ở cấp bool. Muốn kiểm soát số term trong nội dung `match`, dùng `minimum_should_match` bên trong `match` query.

### Nhầm phần trăm dương với phần trăm âm

`75%` tính số clause cần khớp; `-25%` tính số clause được phép bỏ lỡ. Với năm clause, kết quả lần lượt là ba và bốn. Hãy tính thử trên số lượng clause thực tế.

### Đưa mọi điều kiện vào `must`

Các điều kiện chính xác như category, trạng thái và khoảng giá thường nên ở `filter` để không ảnh hưởng score. Dùng `must` cho full-text hoặc điều kiện cần đóng góp relevance.

### `should` chỉ boost nhưng người viết tưởng là bắt buộc

Khi có `must`/`filter` và ngưỡng bằng 0, `should` vẫn có thể làm tăng score. Một document không khớp `should` vẫn được trả về. Phân biệt rõ điều kiện lọc với tín hiệu xếp hạng.

## 13. Kiểm thử Bool Query

Để xác nhận logic, tạo dữ liệu có những trường hợp đại diện:

| Document | Active | Category | Số nhánh `should` khớp | Kết quả khi ngưỡng = 2 |
|---|---:|---|---:|---|
| A | true | keyboards | 0 | Không khớp |
| B | true | keyboards | 1 | Không khớp |
| C | true | keyboards | 2 | Khớp |
| D | true | keyboards | 3 | Khớp |
| E | false | keyboards | 4 | Không khớp do filter |
| F | true | mice | 4 | Không khớp do filter |

Với tập dữ liệu này, query phải trả C và D. E và F không được trả về dù khớp tất cả `should`, vì filter là điều kiện bắt buộc. A và B không đủ số nhánh `should`.

### 13.1. Kiểm tra mặc định khi không khai báo ngưỡng

Chạy cùng query với `minimum_should_match` bị bỏ đi:

- Khi bool có `filter`, A, B, C và D có thể được trả về vì chúng thỏa filter.
- E và F vẫn bị loại do không thỏa filter.
- Các document khớp nhiều `should` có thể được xếp hạng cao hơn.

Kiểm thử này giúp nhận ra sự khác nhau giữa ngưỡng mặc định 0 và ngưỡng tường minh 2.

### 13.2. Dùng Explain API để hiểu điểm relevance

Nếu document đều được trả về nhưng thứ tự không như mong muốn, kiểm tra `_score` và dùng Explain API cho một document cụ thể:

```http
GET products/_explain/p-100
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } }
      ],
      "should": [
        { "match": { "name": "mechanical" } },
        { "match": { "description": "wireless" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

Explain cho biết vì sao document khớp hoặc không khớp và các thành phần đóng góp vào điểm số. Nó hữu ích để phân biệt lỗi logic điều kiện với vấn đề xếp hạng.

## 14. Quy trình thiết kế bool query

Khi xây một query có nhiều điều kiện, hãy thực hiện theo trình tự:

1. Liệt kê điều kiện luôn phải đúng và đặt chúng vào `must` hoặc `filter`.
2. Chọn `must` cho nội dung cần đóng góp điểm relevance; chọn `filter` cho điều kiện cấu trúc không cần scoring.
3. Liệt kê các lựa chọn thay thế hoặc tín hiệu xếp hạng và đặt chúng vào `should`.
4. Quyết định nhóm `should` là bắt buộc hay chỉ dùng để boost.
5. Nếu bắt buộc, đặt `minimum_should_match` tường minh; nếu chỉ boost, giữ ngưỡng 0 hoặc để mặc định khi bool có `must`/`filter`.
6. Chọn số nguyên, phần trăm, giá trị âm hoặc biểu thức điều kiện theo yêu cầu nghiệp vụ.
7. Với bool lồng nhau, đặt ngưỡng ở đúng cấp chứa các clause cần đếm.
8. Kiểm tra riêng số clause trực tiếp và số term bên trong `match` query.
9. Thử dữ liệu khớp dưới ngưỡng, đúng ngưỡng và vượt ngưỡng.
10. Dùng Explain API khi cần điều tra vì sao document được giữ lại hoặc xếp hạng như vậy.

## 15. Tổng kết

Trong Bool Query, `must` và `filter` là các điều kiện bắt buộc; `must` tham gia scoring còn `filter` không tính điểm. `must_not` loại document khớp điều kiện. `should` có thể biểu diễn lựa chọn OR hoặc tín hiệu tăng điểm. Nếu bool có `must` hoặc `filter`, mặc định `should` không bắt buộc (`minimum_should_match = 0`); nếu chỉ có `should` mà không có `must`/`filter`, mặc định cần ít nhất một clause khớp.

`minimum_should_match` kiểm soát số clause `should` tối thiểu phải khớp. Nó nhận số nguyên, số nguyên âm, phần trăm, phần trăm âm và biểu thức điều kiện. Giá trị này chỉ đếm clause trực tiếp của bool nơi nó được khai báo; với bool lồng nhau, mỗi cấp có ngưỡng riêng. Cần phân biệt nó với `minimum_should_match` bên trong `match` query, nơi ngưỡng áp dụng cho các term được phân tích từ văn bản.

Khi thiết kế truy vấn toàn văn, hãy đặt điều kiện nghiệp vụ bắt buộc vào `must`/`filter`, đặt các lựa chọn tìm kiếm vào `should`, rồi chọn ngưỡng rõ ràng. Cách phân chia này giúp query vừa đúng logic lọc, vừa tận dụng được điểm relevance của Elasticsearch.

## Tài liệu tham khảo

- [Elasticsearch – Boolean query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-bool-query)
- [Elasticsearch – `minimum_should_match` parameter](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-minimum-should-match)
- [Elasticsearch – Match query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-match-query)
- [Spring Data Elasticsearch – Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repository-queries.html)
