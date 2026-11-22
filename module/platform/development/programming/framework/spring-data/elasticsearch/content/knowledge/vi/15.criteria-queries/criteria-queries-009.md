# Đọc Query DSL thực tế và nhận biết giới hạn của Criteria

Spring Data Elasticsearch cung cấp **Criteria** và **CriteriaQuery** để xây dựng truy vấn bằng Java. API này giúp biểu đạt các điều kiện phổ biến như so khớp chính xác, khoảng giá, trạng thái, danh mục và tìm kiếm văn bản mà không phải tự ghép JSON. Tuy nhiên, Criteria là một lớp trừu tượng trên Elasticsearch Query DSL. Để hiểu chính xác truy vấn được thực thi, cần biết mỗi điều kiện tương ứng với loại query nào, cách mapping và analyzer ảnh hưởng đến kết quả, cũng như khi nào Criteria không đủ khả năng diễn đạt yêu cầu.

Bài này sử dụng index **products** với các trường SKU, tên, danh mục, trạng thái, giá và ngày tạo. Ta sẽ chuyển các biểu thức Criteria thành Query DSL tương đương, đọc cấu trúc bool/range/term/match, kiểm tra truy vấn với Elasticsearch và chọn cách viết truy vấn tường minh khi cần tính năng vượt quá phạm vi Criteria.

## 1. Criteria và Query DSL nằm ở hai tầng khác nhau

Elasticsearch nhận truy vấn dưới dạng JSON theo Query DSL. Ví dụ một truy vấn lọc sản phẩm theo danh mục và trạng thái:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  }
}
~~~

Spring Data Elasticsearch cho phép mô tả điều kiện tương tự bằng Java:

~~~java
Criteria criteria = Criteria.where("category").is("accessories")
        .and("status").is("ACTIVE");

Query query = new CriteriaQuery(criteria);

SearchHits<Product> hits =
        operations.search(query, Product.class);
~~~

Trong đó:

- **Criteria** mô tả các điều kiện trên trường dữ liệu.
- **CriteriaQuery** đóng gói Criteria thành một đối tượng Query mà Spring Data có thể thực thi.
- **ElasticsearchOperations.search(...)** gửi truy vấn đến Elasticsearch và ánh xạ kết quả thành Product.
- Elasticsearch thực thi Query DSL trên mapping và dữ liệu của index.

Có thể xem Criteria là cách viết ở tầng ứng dụng, còn Query DSL là ngôn ngữ truy vấn mà Elasticsearch thực sự hiểu. Khi debug, cần đọc loại query và logic của nó thay vì chỉ nhìn tên method Java.

Cấu trúc JSON thực tế được gửi có thể có thêm các lớp bao bọc như **bool**, **must**, **should** hoặc các tùy chọn phân trang. Cấu trúc chi tiết phụ thuộc phiên bản Spring Data Elasticsearch. Vì vậy, các JSON trong bài dùng để thể hiện logic truy vấn tương đương; không phải cam kết rằng serializer luôn tạo ra cùng một thứ tự key hoặc cùng cấu trúc bao bọc.

## 2. Mapping quyết định cách đọc Query DSL

Trước khi đọc query, cần biết kiểu dữ liệu của trường. Cùng một biểu thức tìm kiếm có thể cho kết quả rất khác nếu trường được mapping thành **text** hay **keyword**.

Ví dụ mapping:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword"
    },
    "name": {
      "type": "text",
      "analyzer": "standard",
      "fields": {
        "raw": {
          "type": "keyword"
        }
      }
    },
    "category": {
      "type": "keyword"
    },
    "status": {
      "type": "keyword"
    },
    "price": {
      "type": "double"
    },
    "createdAt": {
      "type": "date"
    }
  }
}
~~~

Các kiểu trường có ý nghĩa:

- **keyword** giữ giá trị nguyên vẹn, phù hợp với lọc chính xác, sort và aggregation.
- **text** được analyzer tách thành token, phù hợp với tìm kiếm toàn văn.
- **double**, **long**, **integer** và các kiểu numeric hỗ trợ so sánh số và range.
- **date** hỗ trợ truy vấn theo mốc thời gian và khoảng ngày.
- Multi-field **name.raw** cho phép cùng nội dung tên sản phẩm được tìm toàn văn ở **name** và so khớp nguyên vẹn ở **name.raw**.

Một quy tắc quan trọng: **term query không phân tích chuỗi truy vấn như match query**. Nếu trường **name** là text, giá trị đã được analyzer chuyển thành token khi lập chỉ mục. Dùng term với chuỗi nguyên bản như "Mechanical Keyboard" có thể không khớp theo cách người viết mong đợi. Với tìm kiếm toàn văn, thường dùng match trên **name**; với so khớp nguyên vẹn, dùng term trên **name.raw**.

## 3. Từ Criteria.is() đến term query

Criteria **is(value)** thường biểu đạt điều kiện so khớp một giá trị. Với trường keyword, nó tương đương về logic với **term query**.

Java:

~~~java
Criteria criteria = Criteria.where("status").is("ACTIVE");
Query query = new CriteriaQuery(criteria);

SearchHits<Product> hits =
        operations.search(query, Product.class);
~~~

Query DSL tương đương:

~~~json
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Đọc JSON:

- **term** là loại query.
- **status** là trường được so khớp.
- **ACTIVE** là giá trị cần khớp chính xác.

Dùng **is()** cho các trường như status, category, sku hoặc mã định danh khi chúng được mapping kiểu keyword.

Nếu cần so khớp tên nguyên vẹn, dùng multi-field keyword:

~~~java
Criteria criteria = Criteria.where("name.raw")
        .is("Mechanical Keyboard");
~~~

Query DSL tương đương:

~~~json
{
  "query": {
    "term": {
      "name.raw": "Mechanical Keyboard"
    }
  }
}
~~~

Không nên mặc định rằng **is()** trên trường text có nghĩa là tìm toàn văn. Hãy xác định kiểu mapping trước khi chọn Criteria method.

## 4. Từ Criteria.in() đến terms query

Khi một trường có thể nhận một trong nhiều giá trị, dùng **in(...)**:

~~~java
Criteria criteria = Criteria.where("category")
        .in("accessories", "storage");

Query query = new CriteriaQuery(criteria);
~~~

Query DSL tương đương:

~~~json
{
  "query": {
    "terms": {
      "category": [
        "accessories",
        "storage"
      ]
    }
  }
}
~~~

**terms** khớp nếu giá trị trường bằng một trong các giá trị được cung cấp. Đây là cách biểu đạt phù hợp cho danh mục, trạng thái hoặc tập mã cần lọc chính xác.

Với danh sách giá trị lớn, cần cân nhắc kích thước request và giới hạn terms mà Elasticsearch cho phép. Không nên đưa hàng chục nghìn giá trị vào một query nếu có cách thiết kế dữ liệu hoặc quy trình lọc phù hợp hơn.

## 5. Từ Criteria.between() và các toán tử so sánh đến range query

Các điều kiện so sánh số và ngày thường được chuyển thành **range query**.

Ví dụ giá từ 20 đến 100:

~~~java
Criteria criteria = Criteria.where("price").between(20.0, 100.0);
Query query = new CriteriaQuery(criteria);
~~~

Query DSL tương đương:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gte": 20.0,
        "lte": 100.0
      }
    }
  }
}
~~~

Các toán tử thường gặp:

| Criteria | Range DSL | Ý nghĩa |
|---|---|---|
| **greaterThan(value)** | **gt** | Lớn hơn |
| **greaterThanEqual(value)** | **gte** | Lớn hơn hoặc bằng |
| **lessThan(value)** | **lt** | Nhỏ hơn |
| **lessThanEqual(value)** | **lte** | Nhỏ hơn hoặc bằng |
| **between(from, to)** | Thường là **gte** và **lte** | Nằm trong khoảng, gồm hai đầu mút |

Ví dụ chỉ lấy sản phẩm có giá lớn hơn 50:

~~~java
Criteria criteria = Criteria.where("price").greaterThan(50.0);
~~~

Query DSL:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gt": 50.0
      }
    }
  }
}
~~~

Có thể kết hợp điều kiện ngày:

~~~java
Instant cutoff = Instant.parse("2026-01-01T00:00:00Z");

Criteria criteria = Criteria.where("createdAt").lessThan(cutoff);
Query query = new CriteriaQuery(criteria);
~~~

Query DSL tương đương:

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "lt": "2026-01-01T00:00:00Z"
      }
    }
  }
}
~~~

Để range hoạt động đúng, trường phải được mapping thành kiểu numeric hoặc date phù hợp. Nếu lưu giá hoặc ngày dưới dạng text, so sánh có thể không mang ý nghĩa số học hoặc thời gian.

## 6. Từ Criteria.matches() đến match query

Với trường text, **matches(...)** biểu đạt tìm kiếm toàn văn. Query DSL tương ứng là **match**:

~~~java
Criteria criteria = Criteria.where("name")
        .matches("wireless keyboard");

Query query = new CriteriaQuery(criteria);
~~~

Query DSL tương đương:

~~~json
{
  "query": {
    "match": {
      "name": {
        "query": "wireless keyboard"
      }
    }
  }
}
~~~

Match query phân tích văn bản truy vấn bằng analyzer được cấu hình cho trường, rồi tìm các token phù hợp trong inverted index.

Nếu analyzer tách cụm từ thành hai token **wireless** và **keyboard**, query mặc định có thể khớp tài liệu chứa một trong các token tùy operator. Muốn yêu cầu tất cả các token phải xuất hiện, Query DSL có thể đặt **operator: "and"**:

~~~json
{
  "query": {
    "match": {
      "name": {
        "query": "wireless keyboard",
        "operator": "and"
      }
    }
  }
}
~~~

Một số phiên bản Criteria có phương thức như **matchesAll(...)** để biểu đạt điều kiện khớp tất cả token. Hãy kiểm tra API phiên bản dự án và đọc query thực tế được gửi; nếu cần đặt rõ operator hoặc các tùy chọn match khác, dùng NativeQuery hoặc StringQuery.

### Match không giống term

| Tiêu chí | match | term |
|---|---|---|
| Phân tích chuỗi truy vấn | Có, dùng analyzer của trường hoặc search analyzer | Không |
| Trường thường dùng | text | keyword |
| Tìm toàn văn | Phù hợp | Không phải mục đích chính |
| So khớp giá trị nguyên vẹn | Không đảm bảo | Phù hợp |
| Có thể ảnh hưởng bởi analyzer | Có | Dữ liệu đã được phân tích khi index |

Khi đọc DSL, chỉ cần nhìn tên query **match** hay **term** là đã biết cách Elasticsearch xử lý chuỗi truy vấn khác nhau.

## 7. Từ Criteria.startsWith() đến prefix query

Nếu cần tìm giá trị bắt đầu bằng một tiền tố, Criteria có thể dùng **startsWith(...)**:

~~~java
Criteria criteria = Criteria.where("sku").startsWith("KB-");
Query query = new CriteriaQuery(criteria);
~~~

Query DSL tương đương:

~~~json
{
  "query": {
    "prefix": {
      "sku": {
        "value": "KB-"
      }
    }
  }
}
~~~

Prefix query tìm các term bắt đầu bằng chuỗi được chỉ định. Nó thường phù hợp với mã hoặc trường keyword. Với trường text đã phân tích, prefix được áp dụng trên term đã lập chỉ mục, không nhất thiết trên chuỗi hiển thị ban đầu.

Nếu yêu cầu là tự động hoàn thành theo từng phần của văn bản, hãy cân nhắc **search_as_you_type** hoặc analyzer dùng **edge_ngram** thay vì dùng prefix query tùy tiện trên một trường text lớn.

## 8. Criteria.contains() và wildcard query

Criteria có thể cung cấp các phép tìm chuỗi như **contains(...)** hoặc **endsWith(...)**. Chúng thường được biểu diễn bằng wildcard query.

Ví dụ tìm mã SKU chứa chuỗi **100**:

~~~java
Criteria criteria = Criteria.where("sku").contains("100");
Query query = new CriteriaQuery(criteria);
~~~

Query DSL tương đương về logic:

~~~json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "*100*"
      }
    }
  }
}
~~~

Wildcard **\*** đại diện cho không hoặc nhiều ký tự. Với mẫu **\*100\***, Elasticsearch phải tìm các term có chuỗi 100 ở bất kỳ vị trí nào.

Wildcard bắt đầu bằng dấu **\*** thường tốn tài nguyên hơn prefix query vì nó khó tận dụng cấu trúc term dictionary hiệu quả. Không nên dùng contains/wildcard trên trường có cardinality lớn hoặc index lớn nếu chưa đánh giá chi phí.

Ngoài ra, wildcard hoạt động trên term đã lập chỉ mục. Nó không tự thực hiện phân tích ngôn ngữ giống match query. Cần kiểm tra analyzer và kiểu trường để tránh kỳ vọng sai.

## 9. Đọc logic AND, OR và NOT trong bool query

Khi kết hợp nhiều Criteria, Spring Data cần biểu diễn logic bằng các mệnh đề Boolean của Query DSL.

### AND: phải thỏa nhiều điều kiện

Java:

~~~java
Criteria criteria = Criteria.where("category").is("accessories")
        .and("status").is("ACTIVE");

Query query = new CriteriaQuery(criteria);
~~~

Query DSL tương đương về logic:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  }
}
~~~

Tài liệu phải thỏa cả hai điều kiện. Trong DSL, **must** là các clause bắt buộc khớp và có thể đóng góp vào score.

Nếu điều kiện chỉ dùng để lọc và không cần tính điểm liên quan, Elasticsearch có **filter**:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  }
}
~~~

CriteriaQuery có thể biểu diễn các điều kiện kết hợp, nhưng không phải lúc nào cũng cho phép điều khiển đầy đủ việc đưa từng clause vào **must** hay **filter**. Nếu tối ưu scoring và filter context là yêu cầu quan trọng, hãy dùng NativeQuery hoặc StringQuery để chỉ định rõ.

### OR: chỉ cần thỏa một điều kiện

Query DSL dùng **should** để biểu đạt OR:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "term": {
            "status": "PENDING"
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

**minimum_should_match: 1** yêu cầu ít nhất một clause should phải khớp. Khi đọc bool query, đừng chỉ nhìn danh sách should; hãy xem minimum_should_match và các clause must/filter đi kèm vì chúng quyết định logic thực tế.

Criteria có các cách kết hợp **or(...)** trong các phiên bản hỗ trợ. Ví dụ dạng biểu đạt:

~~~java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .or("status").is("PENDING");

Query query = new CriteriaQuery(criteria);
~~~

Hãy kiểm tra DSL thực tế nếu query có nhiều nhánh lồng nhau, vì cấu trúc bool được tạo có thể không giống một JSON viết tay theo từng key.

### NOT: loại trừ điều kiện

Query DSL dùng **must_not** để loại các tài liệu khớp một điều kiện:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "term": {
            "status": "DELETED"
          }
        }
      ]
    }
  }
}
~~~

Criteria có thể dùng các phép phủ định như **isNot(...)** hoặc cấu trúc phủ định mà phiên bản hỗ trợ. Với logic NOT phức tạp, nên xem query được sinh ra để tránh phủ định nhầm cả nhóm điều kiện.

## 10. Một ví dụ CriteriaQuery có nhiều điều kiện

Giả sử cần tìm sản phẩm thuộc danh mục accessories, đang ACTIVE và có giá từ 20 đến 100:

~~~java
Criteria criteria = Criteria.where("category").is("accessories")
        .and("status").is("ACTIVE")
        .and("price").between(20.0, 100.0);

Query query = new CriteriaQuery(criteria);

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Query DSL tương đương về logic:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "range": {
            "price": {
              "gte": 20.0,
              "lte": 100.0
            }
          }
        }
      ]
    }
  }
}
~~~

Đọc truy vấn theo từng bước:

1. **bool** kết hợp nhiều điều kiện.
2. **term category** giới hạn danh mục.
3. **term status** giới hạn trạng thái.
4. **range price** giới hạn giá.
5. Tài liệu phải thỏa tất cả clause bắt buộc.

Nếu đây là truy vấn lọc danh sách và không cần tính điểm liên quan, có thể dùng filter context trong DSL để tránh tính score cho các điều kiện lọc. Đây là một lý do thực tế để chuyển sang NativeQuery hoặc StringQuery khi cần kiểm soát sâu.

## 11. Criteria không phải bản sao đầy đủ của Query DSL

Criteria phù hợp với các điều kiện thông dụng, nhưng Query DSL của Elasticsearch có nhiều tính năng chuyên biệt. Một abstraction gọn không nhất thiết cung cấp mọi tùy chọn của từng loại query.

Một số trường hợp Criteria có thể không đủ hoặc không thuận tiện:

| Nhu cầu | Vì sao Criteria có thể hạn chế | Cách tiếp cận |
|---|---|---|
| Nested query | Cần chỉ định nested path và query bên trong nested document | NativeQuery hoặc StringQuery |
| Script query hoặc script score | Cần truyền script, params và ngữ cảnh score | NativeQuery/Elasticsearch Java API Client |
| Function score | Cần kết hợp nhiều hàm tính điểm và weight | NativeQuery |
| Query_string với cú pháp tìm kiếm đầy đủ | Cần kiểm soát query string, fields, default operator và flags | StringQuery hoặc NativeQuery |
| Fuzzy query với nhiều tùy chọn | Cần điều khiển fuzziness, prefix length, max expansions | NativeQuery |
| Geo queries | Cần khai báo hình học, khoảng cách, relation hoặc shape | NativeQuery hoặc API client |
| Parent/child và join queries | Cần quan hệ và join context đặc thù | NativeQuery |
| Rescore và rank features | Là tính năng ở cấp truy vấn tìm kiếm nâng cao | NativeQuery/API client |
| Aggregations phức tạp | Cần dựng cây aggregation, bucket, metric và pipeline | NativeQuery hoặc API client |
| Highlight, suggest, collapse | Là các tùy chọn tìm kiếm bổ sung ngoài điều kiện lọc cơ bản | Query API nâng cao |
| Point in time, search_after và truy vấn cuộn | Cần quản lý trạng thái phân trang và cursor | Search API phù hợp với phiên bản |

Đây không phải danh sách cấm dùng Criteria cho mọi trường hợp trên. Khả năng hỗ trợ cụ thể có thể mở rộng theo phiên bản. Nguyên tắc là: nếu yêu cầu cần một tùy chọn Query DSL mà Criteria không biểu đạt rõ ràng, hãy dùng API truy vấn tường minh thay vì cố ghép nhiều Criteria để mô phỏng.

## 12. Nested query: ví dụ về giới hạn quan trọng

Giả sử Product chứa danh sách biến thể, mỗi biến thể có màu và kích thước. Nếu mapping khai báo **variants** là **nested**, truy vấn cần dùng nested query để giữ các điều kiện cùng áp dụng trên một phần tử nested.

Mapping:

~~~json
{
  "properties": {
    "variants": {
      "type": "nested",
      "properties": {
        "color": {
          "type": "keyword"
        },
        "size": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

Yêu cầu: tìm sản phẩm có một variant vừa màu black vừa size M.

Query DSL:

~~~json
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
                "variants.size": "M"
              }
            }
          ]
        }
      }
    }
  }
}
~~~

Nếu chỉ viết các điều kiện Criteria trên **variants.color** và **variants.size** mà không tạo nested query đúng cách, Elasticsearch có thể không áp dụng hai điều kiện trong cùng một nested object. Điều này có thể dẫn đến kết quả sai với dữ liệu có nhiều variant.

Dùng StringQuery để truyền DSL tường minh:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

String dsl = """
{
  "nested": {
    "path": "variants",
    "query": {
      "bool": {
        "filter": [
          { "term": { "variants.color": "black" } },
          { "term": { "variants.size": "M" } }
        ]
      }
    }
  }
}
""";

Query query = new StringQuery(dsl);

SearchHits<Product> hits =
        operations.search(query, Product.class);
~~~

Ví dụ dùng Java text block, có từ Java 15 trở lên. Với Java cũ hơn, có thể tạo chuỗi JSON theo cách nối chuỗi hoặc dùng NativeQuery builder.

## 13. Dùng StringQuery khi muốn viết Query DSL trực tiếp

**StringQuery** cho phép truyền nội dung JSON của query vào Spring Data Elasticsearch. Đây là lựa chọn dễ đọc khi muốn giữ nguyên DSL mà không xây dựng từng object bằng Java API Client.

Ví dụ lọc category, status và price:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

String dsl = """
{
  "bool": {
    "filter": [
      { "term": { "category": "accessories" } },
      { "term": { "status": "ACTIVE" } },
      {
        "range": {
          "price": {
            "gte": 20,
            "lte": 100
          }
        }
      }
    ]
  }
}
""";

Query query = new StringQuery(dsl);

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Trong StringQuery, chuỗi JSON là phần query được gửi cho Elasticsearch; Spring Data quản lý request tìm kiếm và ánh xạ kết quả. Không nhầm nội dung query với toàn bộ request body có trường **query** bao ngoài nếu API constructor đang dùng mong đợi riêng query object.

Ưu điểm của StringQuery:

- Giữ nguyên cú pháp Query DSL mà nhóm đã thiết kế.
- Dễ đối chiếu với request trong Elasticsearch Dev Tools.
- Phù hợp với nested query hoặc các query có cấu trúc phức tạp.
- Không cần biểu diễn mọi DSL feature bằng một abstraction Java hạn chế.

Nhược điểm là JSON được viết dưới dạng chuỗi, nên lỗi cú pháp hoặc tên trường chỉ có thể được phát hiện khi kiểm tra hoặc gửi truy vấn. Nếu nội dung được xây dựng từ dữ liệu người dùng, không nối chuỗi JSON tùy tiện. Hãy serialize tham số an toàn bằng thư viện JSON hoặc dùng NativeQuery builder.

## 14. Dùng NativeQuery khi cần DSL có kiểu dữ liệu

Trong Spring Data Elasticsearch 5.x, **NativeQuery** cho phép xây dựng truy vấn bằng Elasticsearch Java API Client. Cách này phù hợp khi cần Query DSL đầy đủ hơn Criteria nhưng vẫn muốn tạo query trong Java với builder có kiểu dữ liệu.

Ví dụ minh họa:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import co.elastic.clients.elasticsearch._types.FieldValue;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .filter(f -> f.term(t -> t
                        .field("category")
                        .value(FieldValue.of("accessories"))))
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value(FieldValue.of("ACTIVE"))))
                .filter(f -> f.range(r -> r
                        .number(n -> n
                                .field("price")
                                .gte(20.0)
                                .lte(100.0))))
        ))
        .build();

SearchHits<Product> hits =
        operations.search(query, Product.class);
~~~

Đoạn mã minh họa API builder của Elasticsearch Java API Client được tích hợp trong Spring Data Elasticsearch 5.x. Chữ ký của các builder và cách biểu diễn giá trị có thể thay đổi theo phiên bản Elasticsearch Java Client; hãy dùng dependency được Spring Boot quản lý và kiểm tra đúng API trong dự án.

Có thể chọn:

- **CriteriaQuery** cho điều kiện phổ biến, đơn giản và dễ đọc.
- **StringQuery** khi muốn truyền JSON DSL rõ ràng, đặc biệt với nested query hoặc query phức tạp.
- **NativeQuery** khi muốn dùng Java builder có kiểu dữ liệu và các tính năng Query DSL nâng cao.

Không cần dùng NativeQuery cho mọi truy vấn. Một truy vấn lọc đơn giản thường dễ hiểu hơn khi viết bằng Criteria.

## 15. Đọc Query DSL thực tế được gửi đến Elasticsearch

Khi debug, điều cần xác nhận là request thực tế được gửi, không chỉ là cách viết Criteria trong source code.

Có thể thực hiện theo các bước:

1. Tạo một truy vấn Criteria đơn giản và xác định index đích.
2. Bật logging hoặc tracing HTTP request của Elasticsearch Java Client/transport đang dùng ở mức phù hợp với môi trường phát triển.
3. Gửi truy vấn từ ứng dụng.
4. Xem request body và xác định phần **query**, **bool**, **term**, **match**, **range** hoặc các clause khác.
5. Đối chiếu với mapping của index và query tương đương trong Dev Tools.
6. Tắt tracing chi tiết sau khi kiểm tra vì log request có thể chứa dữ liệu nghiệp vụ hoặc thông tin nhạy cảm.

Tên logger và cách bật wire logging thay đổi theo client/transport và phiên bản Spring Data Elasticsearch. Không nên sao chép một logger category từ phiên bản khác mà không kiểm tra tài liệu tương ứng. Đồng thời, tránh ghi log credentials, dữ liệu cá nhân hoặc toàn bộ source tài liệu trong môi trường production.

Một số điều cần chú ý khi đọc request:

- Query DSL có thể được bọc trong **bool** dù Criteria chỉ có một điều kiện.
- Spring Data có thể thêm pagination, sort, source filtering hoặc các tùy chọn khác.
- Thứ tự các trường JSON không ảnh hưởng ý nghĩa truy vấn.
- Cùng một logic có thể được biểu diễn bằng nhiều cấu trúc DSL tương đương.
- Không nên so sánh chuỗi JSON theo byte; hãy so sánh loại query, field, giá trị và logic bool.

## 16. Kiểm tra query bằng Elasticsearch API

Sau khi đọc DSL, có thể dùng các API của Elasticsearch để xác nhận cú pháp và lý do tài liệu khớp hoặc không khớp.

### Validate query

Endpoint **_validate/query** kiểm tra query có hợp lệ hay không:

~~~http
POST /products/_validate/query?explain=true
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "range": {
            "price": {
              "gte": 20,
              "lte": 100
            }
          }
        }
      ]
    }
  }
}
~~~

Tham số **explain=true** yêu cầu Elasticsearch giải thích query sau khi phân tích. API này hữu ích để phát hiện cú pháp hoặc cấu trúc query không hợp lệ; nó không chứng minh dữ liệu hiện có sẽ trả về kết quả như mong muốn.

### Explain vì sao một tài liệu khớp

Dùng **_explain** với ID tài liệu:

~~~http
GET /products/_explain/p-1001
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Elasticsearch trả về thông tin cho biết tài liệu có khớp query hay không và cách tính score. Đây là công cụ hữu ích khi một tài liệu cụ thể không xuất hiện trong kết quả.

### Profile query

Có thể thêm **profile: true** vào request tìm kiếm để xem chi tiết quá trình thực thi:

~~~http
GET /products/_search
{
  "profile": true,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "range": {
            "price": {
              "gte": 20,
              "lte": 100
            }
          }
        }
      ]
    }
  }
}
~~~

Profile hữu ích khi phân tích hiệu năng, nhưng bản thân việc profile có thêm chi phí. Chỉ bật khi cần điều tra và không nên bật đại trà trên mọi request production.

## 17. Kiểm tra analyzer khi match query không cho kết quả mong đợi

Nếu query dùng **match**, analyzer ảnh hưởng trực tiếp đến token của văn bản truy vấn và nội dung đã lập chỉ mục.

Ví dụ kiểm tra analyzer:

~~~http
POST /products/_analyze
{
  "field": "name",
  "text": "Wireless Mechanical Keyboard"
}
~~~

Elasticsearch trả về danh sách token sau phân tích. So sánh token này với query mà Criteria tạo ra và với term đã lưu trong index.

Nếu dùng **term** trên trường text, query string không được phân tích. Ví dụ:

~~~json
{
  "query": {
    "term": {
      "name": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

có thể không khớp vì index đã tách tên thành các token riêng. Đổi sang match:

~~~json
{
  "query": {
    "match": {
      "name": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

Hoặc dùng keyword subfield khi cần so khớp nguyên vẹn:

~~~json
{
  "query": {
    "term": {
      "name.raw": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

Đây là lý do quan trọng để đọc cả Query DSL lẫn mapping. Chỉ nhìn Criteria method mà không biết kiểu trường có thể dẫn đến chẩn đoán sai.

## 18. Giới hạn hiệu năng cần nhận biết

Một query hợp lệ về cú pháp chưa chắc hiệu quả về hiệu năng. Một số loại query cần thận trọng:

**Wildcard có dấu sao ở đầu.** Mẫu như **\*keyboard** hoặc **\*100\*** có thể phải xét nhiều term. Chỉ dùng khi dữ liệu và quy mô index cho phép.

**Fuzzy query.** Fuzzy giúp chịu lỗi chính tả nhưng có thể mở rộng số term cần xét. Hãy giới hạn fuzziness, prefix length và max expansions theo nhu cầu.

**Query_string.** Cú pháp query string mạnh nhưng người dùng có thể đưa vào toán tử đặc biệt. Cần xác định rõ có cho phép người dùng viết cú pháp DSL hay không và xử lý đầu vào phù hợp.

**Nested query.** Cần nested mapping đúng và có thể tốn chi phí hơn truy vấn field thường. Chỉ dùng khi mô hình dữ liệu thực sự cần giữ quan hệ giữa các object con.

**Script query.** Linh hoạt nhưng có thể tốn tài nguyên. Nếu điều kiện có thể biểu đạt bằng term/range hoặc dữ liệu có thể chuẩn hóa trước, hãy cân nhắc cách đơn giản hơn.

**Bool query quá nhiều nhánh.** Một truy vấn có hàng trăm hoặc hàng nghìn clause có thể làm tăng chi phí parse và thực thi. Nên xem xét terms query, lọc trước hoặc thay đổi cách mô hình hóa dữ liệu.

Khi cần tối ưu, hãy xem query profile, mapping, số lượng shard, cardinality của trường và phân bố dữ liệu. Đừng tối ưu chỉ dựa vào độ dài JSON.

## 19. Các lỗi thường gặp khi đọc Criteria và Query DSL

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra hoặc xử lý |
|---|---|---|
| is() không tìm thấy nội dung text | is thường biểu đạt so khớp term, trong khi trường đã được phân tích | Dùng matches/match hoặc keyword subfield |
| matches() trả quá nhiều kết quả | Match mặc định có thể khớp một trong nhiều token | Xem operator và cân nhắc AND hoặc match_phrase |
| between() không hoạt động như mong đợi | Trường được mapping thành text hoặc giá trị sai kiểu | Kiểm tra mapping và dùng numeric/date đúng kiểu |
| OR trả nhiều tài liệu hơn dự kiến | should/minimum_should_match không đúng logic mong muốn | Đọc toàn bộ bool query và đặt minimum_should_match |
| Điều kiện lồng nhau khớp sai object | Dùng field path thường thay cho nested query | Kiểm tra mapping nested và dùng nested DSL |
| contains() chậm | Wildcard có leading wildcard trên nhiều term | Dùng prefix, n-gram hoặc trường tìm kiếm chuyên dụng |
| Criteria không biểu đạt được query | Query cần nested, script, geo hoặc tùy chọn nâng cao | Chuyển sang NativeQuery/StringQuery |
| JSON trong StringQuery lỗi | Chuỗi JSON sai cú pháp hoặc query object bị bọc sai | Validate query và kiểm tra đúng nội dung constructor mong đợi |
| Kết quả khác với Dev Tools | Ứng dụng dùng index, alias, analyzer hoặc pagination khác | So sánh toàn bộ request và index đích |
| Query hợp lệ nhưng không có hit | Giá trị không khớp dữ liệu hoặc analyzer tạo token khác | Dùng _analyze, _explain và kiểm tra document mẫu |

## 20. Quy trình đọc và lựa chọn Criteria

Khi làm việc với một truy vấn Spring Data Elasticsearch, có thể đi theo trình tự sau:

1. **Xác định index đích.** Kiểm tra entity metadata, IndexCoordinates hoặc alias mà service đang dùng.
2. **Đọc mapping.** Xác định kiểu trường là text, keyword, numeric, date hay nested.
3. **Đọc Criteria.** Ghi lại từng điều kiện, phép nối AND/OR và các phép phủ định.
4. **Suy ra Query DSL.** Xác định mỗi điều kiện là term, terms, match, range, prefix, wildcard hay bool.
5. **Kiểm tra context.** Xác định clause nằm trong must, filter, should hay must_not và có ảnh hưởng scoring không.
6. **Xem request thực tế.** Bật tracing phù hợp trong môi trường phát triển nếu cần xác nhận cấu trúc được gửi.
7. **Validate và thử dữ liệu.** Dùng _validate/query, _analyze, _explain hoặc truy vấn trong Dev Tools.
8. **Đánh giá hiệu năng.** Xem profile khi query chậm và cân nhắc chi phí wildcard, fuzzy, nested hoặc script.
9. **Chọn abstraction.** Giữ Criteria cho điều kiện thông dụng; dùng StringQuery hoặc NativeQuery khi cần kiểm soát DSL nâng cao.

Criteria giúp xây dựng truy vấn Java gọn và dễ đọc, đặc biệt với điều kiện term, range và match cơ bản. Nhưng Criteria không thay thế kiến thức về Query DSL. Muốn hiểu kết quả, cần đọc mapping, biết điều kiện Java được biểu diễn thành loại query nào và kiểm tra bool logic thực tế. Khi truy vấn cần nested, script, scoring hoặc các tính năng chuyên biệt, dùng NativeQuery hoặc StringQuery để mô tả chính xác yêu cầu của Elasticsearch.
