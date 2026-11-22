# Prefix, wildcard, regexp và chi phí truy vấn

Elasticsearch cung cấp các truy vấn **prefix**, **wildcard** và **regexp** để tìm tài liệu dựa trên một phần của term đã được lập chỉ mục. Chúng hữu ích khi người dùng tìm mã sản phẩm theo tiền tố, nhập một phần chuỗi hoặc cần biểu đạt mẫu ký tự. Tuy nhiên, đây là các truy vấn term-level: Elasticsearch so khớp trực tiếp với term trong inverted index, không phân tích chuỗi truy vấn bằng analyzer như **match query**.

Ba loại truy vấn có mức độ linh hoạt và chi phí khác nhau. Prefix tìm các term bắt đầu bằng một chuỗi cố định; wildcard cho phép dùng ký tự đại diện; regexp biểu đạt mẫu bằng cú pháp biểu thức chính quy của Lucene. Mẫu càng rộng, đặc biệt khi có ký tự đại diện ở đầu hoặc nhiều nhánh thay thế, Elasticsearch có thể phải xét nhiều term hơn và tốn CPU, bộ nhớ cũng như thời gian tìm kiếm.

Bài này sử dụng index **products** với các trường **sku**, **name**, **category** và **description**. Ta sẽ tìm hiểu cách chọn mapping, đọc cú pháp của từng query, đánh giá chi phí và lựa chọn phương án phù hợp trong Spring Data Elasticsearch.

## 1. Term-level query và full-text query

Trước khi chọn prefix, wildcard hay regexp, cần phân biệt term-level query với full-text query.

**Full-text query**, ví dụ **match**, phân tích nội dung truy vấn theo analyzer của trường rồi tìm các token phù hợp. Điều này phù hợp với văn bản tự nhiên như tên sản phẩm hoặc mô tả.

**Term-level query** so khớp trực tiếp với term đã được lập chỉ mục. Nó không chạy analyzer trên chuỗi truy vấn. Prefix, wildcard và regexp thuộc nhóm này.

| Loại truy vấn | Phân tích chuỗi truy vấn bằng analyzer? | Mục đích |
|---|---|---|
| **match** | Có | Tìm kiếm toàn văn |
| **match_phrase** | Có | Tìm cụm từ theo thứ tự token |
| **term** | Không | So khớp một term chính xác |
| **prefix** | Không | Tìm term bắt đầu bằng tiền tố |
| **wildcard** | Không | Tìm term theo mẫu ký tự đại diện |
| **regexp** | Không | Tìm term khớp biểu thức chính quy |

Ví dụ, trường **name** có analyzer standard. Nội dung **"Wireless Mechanical Keyboard"** có thể được phân tích thành các term riêng như **wireless**, **mechanical** và **keyboard**. Prefix query trên trường name làm việc với các term đã được tạo ra, không tìm tiền tố trên toàn bộ chuỗi hiển thị ban đầu.

Nếu mục tiêu là tìm các tên sản phẩm bắt đầu bằng cả cụm **"Wireless Me"**, việc dùng prefix query trực tiếp trên trường text có thể không mang lại ý nghĩa như mong muốn. Khi cần tìm theo tiền tố của cả chuỗi, có thể dùng trường keyword riêng, kiểu trường search_as_you_type hoặc một trường autocomplete được thiết kế cho mục đích đó.

## 2. Chọn mapping phù hợp trước khi truy vấn

Các truy vấn prefix, wildcard và regexp hoạt động trên term trong index. Vì vậy, kiểu mapping quyết định chuỗi nào có thể được so khớp.

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
          "type": "keyword",
          "normalizer": "lowercase_normalizer"
        }
      }
    },
    "category": {
      "type": "keyword"
    },
    "description": {
      "type": "text",
      "analyzer": "standard"
    }
  }
}
~~~

Nếu dùng normalizer, cần khai báo trong settings của index:

~~~json
{
  "analysis": {
    "normalizer": {
      "lowercase_normalizer": {
        "type": "custom",
        "filter": [
          "lowercase"
        ]
      }
    }
  }
}
~~~

Trong ví dụ:

- **sku** là keyword, giữ mã như một term nguyên vẹn.
- **name** là text, được analyzer chia thành các token để tìm kiếm toàn văn.
- **name.raw** là keyword multi-field, giữ tên thành một term duy nhất và chuẩn hóa chữ thường.
- **category** là keyword, phù hợp với lọc chính xác.
- **description** là text, phù hợp với match query.

Dùng **sku** cho prefix/wildcard/regexp trên mã sản phẩm. Dùng **name.raw** nếu cần tìm mẫu trên toàn bộ tên như một chuỗi. Dùng **name** cho tìm kiếm toàn văn. Không chọn trường chỉ dựa trên tên thuộc tính; hãy kiểm tra mapping thực tế của index.

Normalizer chỉ áp dụng cho keyword field. Nếu normalizer chuyển chữ thành chữ thường, term được lưu trong index cũng ở dạng đã chuẩn hóa. Query term-level cần tuân theo cùng cách chuẩn hóa; một số query có tùy chọn **case_insensitive** tùy phiên bản Elasticsearch, nhưng không nên dùng tùy chọn đó thay cho việc thiết kế mapping rõ ràng.

## 3. Prefix query: tìm term bắt đầu bằng chuỗi

**Prefix query** tìm các term có phần đầu khớp với chuỗi chỉ định. Ví dụ, tìm SKU bắt đầu bằng **KB-**:

~~~http
POST /products/_search
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

Nếu index có các SKU như:

- KB-1001
- KB-1002
- KB-PRO-01
- MS-2001

thì truy vấn trên khớp các term bắt đầu bằng **KB-**.

Cú pháp rút gọn cũng có thể viết:

~~~json
{
  "query": {
    "prefix": {
      "sku": "KB-"
    }
  }
}
~~~

Dạng có object cho phép khai báo thêm các tùy chọn như **case_insensitive** hoặc **rewrite** nếu phiên bản hỗ trợ.

### Prefix trên trường text

Giả sử trường **name** được phân tích thành các term **wireless**, **mechanical**, **keyboard**. Truy vấn:

~~~json
{
  "query": {
    "prefix": {
      "name": {
        "value": "key"
      }
    }
  }
}
~~~

có thể khớp term **keyboard**. Nó không có nghĩa là tên sản phẩm hiển thị phải bắt đầu bằng **key**. Prefix đang được áp dụng cho từng term đã lập chỉ mục.

Nếu muốn tìm tên bắt đầu bằng chuỗi người dùng nhập, hãy cân nhắc trường keyword multi-field hoặc mapping phục vụ autocomplete. Ví dụ với **name.raw**, prefix được áp dụng trên toàn bộ tên đã chuẩn hóa thành một term. Với tên dài, cần lưu ý giới hạn **ignore_above** nếu đã cấu hình cho keyword subfield.

### Khi nào nên dùng prefix?

Prefix phù hợp khi:

- Người dùng nhập vài ký tự đầu của mã SKU.
- Cần lọc theo mã, mã vùng, mã danh mục hoặc một định danh có quy tắc.
- Cần autocomplete theo tiền tố của term.
- Chuỗi tìm kiếm có tiền tố cố định và không cần biểu thức linh hoạt.

Prefix thường có thể tối ưu tốt hơn wildcard có dấu sao ở đầu vì Elasticsearch biết phần đầu của term cần tìm. Tuy nhiên, chi phí còn phụ thuộc số lượng term phù hợp, cấu trúc index, mapping và phiên bản Elasticsearch. Prefix trên trường có cardinality cao hoặc tiền tố quá ngắn vẫn có thể tạo nhiều kết quả và tốn tài nguyên.

## 4. Tối ưu prefix bằng index_prefixes

Nếu ứng dụng thường xuyên tìm tiền tố trên một trường text, mapping có thể dùng **index_prefixes** để lập chỉ mục các tiền tố theo cấu hình.

Ví dụ:

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "index_prefixes": {
        "min_chars": 2,
        "max_chars": 10
      }
    }
  }
}
~~~

Elasticsearch tạo thêm cấu trúc term phục vụ truy vấn prefix trong khoảng độ dài đã cấu hình. Điều này có thể giúp prefix query chạy hiệu quả hơn ở những trường hợp phù hợp.

Cần cân nhắc:

- Giá trị **min_chars** và **max_chars** phải phản ánh độ dài tiền tố thường gặp.
- Việc lập chỉ mục tiền tố làm tăng kích thước index.
- Prefix ngắn hơn min_chars hoặc dài hơn max_chars có thể không được hưởng cùng lợi ích tối ưu.
- Thay đổi mapping để thêm index_prefixes thường cần tạo index mới và reindex dữ liệu.

Không bật index_prefixes cho mọi trường. Chỉ sử dụng khi có nhu cầu prefix rõ ràng và đã đánh giá trade-off giữa chi phí ghi/lưu trữ với hiệu năng tìm kiếm.

## 5. Wildcard query: dùng ký tự đại diện

**Wildcard query** cho phép biểu diễn mẫu term bằng hai ký tự đặc biệt:

- **\*** khớp với không hoặc nhiều ký tự.
- **?** khớp với đúng một ký tự.

Ví dụ tìm SKU bắt đầu bằng KB- và có phần còn lại bất kỳ:

~~~http
POST /products/_search
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "KB-*"
      }
    }
  }
}
~~~

Ví dụ tìm mã có ký tự đầu là K, tiếp theo là B, sau đó đúng một ký tự bất kỳ rồi đến 100:

~~~json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "KB?100"
      }
    }
  }
}
~~~

Mẫu wildcard làm việc trên một term. Nó không phân tích từ khóa như match query. Vì vậy, hãy dùng trường keyword hoặc trường đã được thiết kế phù hợp với cấu trúc term mong muốn.

### Leading wildcard

Mẫu bắt đầu bằng **\*** hoặc **?** thường đắt hơn:

~~~json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "*100"
      }
    }
  }
}
~~~

Elasticsearch không biết trước phần đầu của term, nên phải xét nhiều term có khả năng phù hợp. Mẫu **\*100** tìm mọi term kết thúc bằng 100; mẫu **\*100\*** tìm mọi term có chứa 100 ở bất kỳ vị trí nào.

Đặc biệt cần thận trọng với:

~~~json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "*"
      }
    }
  }
}
~~~

Mẫu này có thể khớp hầu hết term có giá trị ở trường đó và gần giống truy vấn rất rộng. Nếu chỉ cần kiểm tra trường tồn tại, hãy dùng **exists query** thay vì wildcard **\***.

### Escape ký tự đặc biệt

Nếu dữ liệu có ký tự **\*** hoặc **?** theo nghĩa ký tự thông thường, cần escape theo cú pháp query và quy tắc JSON. Cần phân biệt ký tự đại diện trong pattern với ký tự thực tế trong dữ liệu. Khi tạo query từ input người dùng, hãy xử lý escape an toàn thay vì nối chuỗi mẫu một cách tùy tiện.

### Khi nào nên dùng wildcard?

Wildcard phù hợp khi cần mẫu đơn giản có tiền tố hoặc hậu tố, hoặc một vài vị trí ký tự không cố định. Nếu mẫu chỉ là tiền tố, ưu tiên prefix query. Nếu mẫu bắt đầu bằng wildcard hoặc chứa nhiều wildcard, cần đo hiệu năng trên dữ liệu gần với production trước khi triển khai.

## 6. Regexp query: tìm term theo biểu thức chính quy

**Regexp query** tìm các term khớp với biểu thức chính quy theo cú pháp của Lucene. Đây không phải toàn bộ cú pháp PCRE/Java regex. Elasticsearch sử dụng automaton để thực thi biểu thức; một số tính năng regex quen thuộc như backreference hoặc lookaround không được hỗ trợ theo cách của Java/PCRE.

Ví dụ tìm SKU bắt đầu bằng KB-, theo sau là một hoặc nhiều chữ số:

~~~http
POST /products/_search
{
  "query": {
    "regexp": {
      "sku": {
        "value": "KB-[0-9]+"
      }
    }
  }
}
~~~

Một số toán tử thường gặp trong cú pháp regexp Lucene:

| Cú pháp | Ý nghĩa khái quát |
|---|---|
| **.** | Một ký tự bất kỳ |
| **?** | Không hoặc một lần lặp của biểu thức đứng trước |
| **\*** | Không hoặc nhiều lần lặp của biểu thức đứng trước |
| **+** | Một hoặc nhiều lần lặp |
| **[abc]** | Một ký tự trong tập a, b hoặc c |
| **[0-9]** | Một chữ số trong khoảng 0 đến 9 |
| **(foo\|bar)** | Một trong các nhánh foo hoặc bar |
| **@** | Any string trong cú pháp Lucene regexp |
| **#** | Empty language trong cú pháp Lucene regexp |

Cú pháp cụ thể có thể có thêm toán tử và quy tắc escape. Cần tham khảo tài liệu regexp query của phiên bản Elasticsearch đang chạy trước khi dùng mẫu phức tạp.

### Regexp khớp toàn bộ term

Regexp query trong Elasticsearch so khớp toàn bộ term đã lập chỉ mục. Ví dụ:

~~~json
{
  "query": {
    "regexp": {
      "sku": {
        "value": "KB-[0-9]+"
      }
    }
  }
}
~~~

Mẫu này khớp một term bắt đầu bằng KB- và phần sau gồm một hoặc nhiều chữ số. Nó không tự động có nghĩa là tìm một đoạn con nằm giữa term. Nếu cần cho phép phần đầu hoặc cuối bất kỳ, phải biểu đạt rõ bằng toán tử phù hợp, ví dụ **.*KB-[0-9]+.***, nhưng mẫu rộng như vậy có thể rất tốn kém.

Không cần thêm dấu **^** và **$** theo thói quen từ Java regex để yêu cầu khớp toàn bộ term; ngữ nghĩa regexp query đã là so khớp toàn term. Cú pháp neo của các engine regex khác không nên áp dụng máy móc sang Lucene regexp.

### Regexp và độ phức tạp của automaton

Một biểu thức có nhiều nhánh thay thế, lặp lồng nhau hoặc phần wildcard rộng có thể tạo automaton phức tạp. Elasticsearch giới hạn độ phức tạp thông qua **max_determinized_states**. Nếu biểu thức vượt ngưỡng, request có thể bị từ chối để tránh tiêu tốn tài nguyên quá mức.

Ví dụ cấu hình giới hạn trong query:

~~~json
{
  "query": {
    "regexp": {
      "sku": {
        "value": "KB-(10|20|30)-[0-9]+",
        "max_determinized_states": 10000
      }
    }
  }
}
~~~

Không nên tăng **max_determinized_states** một cách tùy tiện chỉ để làm cho một biểu thức quá phức tạp được chấp nhận. Hãy đơn giản hóa pattern, giới hạn phạm vi tìm kiếm hoặc chuẩn hóa dữ liệu trước khi lập chỉ mục.

## 7. So sánh prefix, wildcard và regexp

| Tiêu chí | Prefix | Wildcard | Regexp |
|---|---|---|---|
| Khả năng biểu đạt | Tiền tố cố định | Mẫu với * và ? | Mẫu biểu thức chính quy |
| Độ linh hoạt | Thấp | Trung bình | Cao |
| Chi phí thường gặp | Thường thấp hơn khi tiền tố đủ chọn lọc | Tăng với leading wildcard và mẫu rộng | Phụ thuộc độ phức tạp automaton và số term |
| Dùng analyzer cho query string | Không | Không | Không |
| Trường thường dùng | keyword hoặc term text phù hợp | keyword hoặc trường chuyên dụng | keyword hoặc trường chuyên dụng |
| Tình huống phù hợp | SKU bắt đầu bằng KB- | Mã có mẫu ký tự linh hoạt | Quy tắc mã có cấu trúc phức tạp |
| Rủi ro | Tiền tố quá ngắn khớp quá nhiều term | Mẫu rộng, đặc biệt * ở đầu | Pattern phức tạp, determinization tốn tài nguyên |

Quy tắc lựa chọn:

1. Nếu chỉ cần tìm tiền tố, dùng **prefix**.
2. Nếu cần một hoặc vài ký tự đại diện, cân nhắc **wildcard**.
3. Nếu thật sự cần mẫu phức tạp, dùng **regexp** với giới hạn và kiểm thử.
4. Nếu cần tìm nội dung tự nhiên, dùng **match** thay vì cố mô phỏng bằng wildcard hoặc regexp.
5. Nếu cần autocomplete, xem xét **search_as_you_type**, **edge_ngram** hoặc **index_prefixes** trước khi chạy wildcard rộng trên văn bản.

## 8. Chi phí truy vấn đến từ đâu?

Prefix, wildcard và regexp là term-level query. Để thực thi, Elasticsearch cần tìm các term phù hợp trong cấu trúc term dictionary của từng shard rồi thu thập các tài liệu chứa term đó.

Chi phí phụ thuộc vào nhiều yếu tố:

- Số lượng term duy nhất trong trường.
- Số lượng term phù hợp với mẫu.
- Độ dài và cấu trúc pattern.
- Có tiền tố cố định hay không.
- Có wildcard ở đầu hay không.
- Số shard và số segment cần xét.
- Mapping, normalizer và các tối ưu index đã cấu hình.
- Kết quả có cần tính score, sort, aggregation hoặc highlight hay không.

Một query có cú pháp ngắn không nhất thiết rẻ. Ví dụ **\*a\*** có thể ngắn nhưng khớp rất nhiều term. Ngược lại, một regexp dài có tiền tố cố định và tập term chọn lọc có thể ít tốn kém hơn một wildcard rất rộng.

### Leading wildcard làm tăng phạm vi xét term

So sánh:

~~~json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "KB-10*"
      }
    }
  }
}
~~~

với:

~~~json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "*10*"
      }
    }
  }
}
~~~

Mẫu đầu có tiền tố cố định **KB-10** nên Elasticsearch có thể thu hẹp vùng term cần xét. Mẫu sau không có tiền tố cố định và có thể phải kiểm tra phạm vi term lớn hơn.

Nếu nghiệp vụ thường xuyên cần tìm chuỗi con, hãy cân nhắc thay đổi thiết kế index thay vì phụ thuộc vào leading wildcard trên trường keyword thông thường.

## 9. Query rewrite và scoring

Các query dạng prefix, wildcard và regexp có thể được rewrite thành cách thực thi dựa trên các term phù hợp. Thuộc tính **rewrite** điều khiển chiến lược rewrite mà Elasticsearch sử dụng. Một số chiến lược có thể tạo Boolean query từ các term mở rộng, trong khi chiến lược khác dùng constant score hoặc cách xử lý phù hợp hơn với số lượng term lớn.

Ví dụ:

~~~json
{
  "query": {
    "prefix": {
      "sku": {
        "value": "KB-10",
        "rewrite": "constant_score"
      }
    }
  }
}
~~~

Các rewrite method cụ thể và giá trị mặc định có thể khác theo phiên bản Elasticsearch. Không nên thay đổi rewrite chỉ dựa trên phỏng đoán. Nếu query chỉ dùng để lọc mã, thường không cần score; có thể đặt query trong **bool.filter** để biểu đạt mục đích lọc.

Ví dụ:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "prefix": {
            "sku": {
              "value": "KB-10"
            }
          }
        }
      ]
    }
  }
}
~~~

Filter context không tính relevance score cho điều kiện prefix. Điều này phù hợp khi mục tiêu chỉ là lọc tập tài liệu theo mã.

## 10. Cấu hình allow_expensive_queries

Elasticsearch có setting **search.allow_expensive_queries** để kiểm soát một số loại truy vấn có thể tốn kém. Khi setting này bị tắt, các query bị phân loại là expensive có thể bị từ chối.

Wildcard và regexp thường nằm trong nhóm cần chú ý. Prefix query cũng có thể bị xem là expensive trong một số trường hợp, đặc biệt khi mapping không có tối ưu phù hợp; các phiên bản và cơ chế tối ưu mới có thể thay đổi hành vi cụ thể.

Không nên dựa vào một giả định chung rằng mọi prefix đều luôn được phép khi tắt expensive queries. Hãy kiểm tra tài liệu phiên bản Elasticsearch và thử truy vấn trên index thật với setting đang áp dụng.

Có thể xem cấu hình cluster/index theo quyền và API được phép. Nếu request bị từ chối với thông báo liên quan đến expensive queries:

- Xác định chính xác loại query bị từ chối.
- Kiểm tra setting **search.allow_expensive_queries**.
- Xem mapping có **index_prefixes** hoặc kiểu trường phù hợp hay không.
- Cân nhắc thay query bằng prefix hoặc một trường autocomplete được lập chỉ mục trước.
- Chỉ bật lại expensive queries khi đã đánh giá tác động và chính sách vận hành cho phép.

Không nên bật expensive queries trên toàn cluster chỉ để một màn hình tìm kiếm hoạt động mà chưa giới hạn đầu vào và đánh giá tải.

## 11. Thay wildcard rộng bằng thiết kế index phù hợp

Nếu sản phẩm cần tìm chuỗi con thường xuyên, có thể dùng kiểu trường **wildcard**. Đây là kiểu field được thiết kế cho nội dung có nhiều chuỗi dài hoặc truy vấn wildcard/regexp, tùy mô hình dữ liệu và phiên bản Elasticsearch.

Ví dụ mapping:

~~~json
{
  "properties": {
    "log_message": {
      "type": "wildcard"
    }
  }
}
~~~

Kiểu wildcard có thể phù hợp với log message hoặc chuỗi có độ dài lớn, nơi ứng dụng cần tìm mẫu ký tự. Nó có cách lưu trữ và thực thi khác với keyword thông thường, vì vậy cần đo lường cả chi phí ghi, kích thước index và hiệu năng truy vấn.

Với mã SKU ngắn, có cấu trúc và thường tìm theo tiền tố, **keyword** cùng prefix query thường là lựa chọn đơn giản. Không cần dùng wildcard field cho mọi trường.

### Dùng edge_ngram cho autocomplete

Nếu người dùng nhập từng ký tự để tìm tên sản phẩm, có thể lập chỉ mục các tiền tố bằng **edge_ngram**.

Ví dụ settings:

~~~json
{
  "analysis": {
    "tokenizer": {
      "name_edge_tokenizer": {
        "type": "edge_ngram",
        "min_gram": 2,
        "max_gram": 15,
        "token_chars": [
          "letter",
          "digit"
        ]
      }
    },
    "analyzer": {
      "name_autocomplete_index": {
        "type": "custom",
        "tokenizer": "name_edge_tokenizer",
        "filter": [
          "lowercase"
        ]
      },
      "name_autocomplete_search": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
          "lowercase"
        ]
      }
    }
  }
}
~~~

Mapping:

~~~json
{
  "properties": {
    "name_suggest": {
      "type": "text",
      "analyzer": "name_autocomplete_index",
      "search_analyzer": "name_autocomplete_search"
    }
  }
}
~~~

Khi index tên **Wireless Keyboard**, edge_ngram có thể tạo các tiền tố như **wi**, **wir**, **wire**, ... cho từng token. Search analyzer dùng standard tokenizer để phân tích chuỗi người dùng nhập.

Cách này đổi chi phí truy vấn thành chi phí lập chỉ mục và lưu trữ: index có nhiều term hơn, nhưng truy vấn autocomplete có thể đơn giản và nhanh hơn. Chọn min_gram/max_gram theo hành vi nhập liệu thực tế, không đặt max_gram quá lớn nếu không cần.

## 12. Kết hợp prefix, wildcard hoặc regexp với bool query

Các query này có thể được kết hợp với filter khác trong bool query.

Ví dụ tìm SKU bắt đầu bằng KB-, chỉ lấy sản phẩm ACTIVE và có giá từ 50 trở lên:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "prefix": {
            "sku": {
              "value": "KB-"
            }
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
              "gte": 50
            }
          }
        }
      ]
    }
  }
}
~~~

Ví dụ lọc mã theo wildcard:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "wildcard": {
            "sku": {
              "value": "KB-*-BLK"
            }
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

Ví dụ lọc mã theo regexp:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "regexp": {
            "sku": {
              "value": "KB-[0-9]{4}"
            }
          }
        },
        {
          "term": {
            "category": "accessories"
          }
        }
      ]
    }
  }
}
~~~

Các ví dụ trên đặt điều kiện trong **filter** vì chúng được dùng để thu hẹp tập tài liệu, không phải để xếp hạng độ liên quan. Nếu query cần tính score dựa trên nội dung, hãy tách phần full-text vào must và giữ điều kiện mã/trạng thái trong filter.

## 13. Sử dụng các query này trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp nhiều cách tạo query. Với các query term-level đơn giản, có thể dùng Criteria nếu API phiên bản hỗ trợ phép toán tương ứng. Khi cần kiểm soát JSON chính xác, **StringQuery** hoặc **NativeQuery** thường rõ ràng hơn.

### Dùng StringQuery

StringQuery nhận query DSL dạng chuỗi. Ví dụ prefix:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

String dsl = """
{
  "prefix": {
    "sku": {
      "value": "KB-"
    }
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

Ví dụ wildcard:

~~~java
String dsl = """
{
  "wildcard": {
    "sku": {
      "value": "KB-*-BLK"
    }
  }
}
""";

Query query = new StringQuery(dsl);
~~~

Ví dụ regexp:

~~~java
String dsl = """
{
  "regexp": {
    "sku": {
      "value": "KB-[0-9]{4}"
    }
  }
}
""";

Query query = new StringQuery(dsl);
~~~

Các chuỗi JSON trên chỉ chứa query clause. Spring Data đặt nó vào search request khi thực thi. Không đưa toàn bộ body với **from**, **size** và **query** vào constructor StringQuery nếu constructor mong đợi phần query riêng.

Khi xây dựng pattern từ đầu vào người dùng, phải kiểm soát độ dài, ký tự đại diện và cú pháp. Không nối trực tiếp input tùy ý vào JSON query string. Dùng serializer hoặc builder có kiểu dữ liệu để tránh lỗi JSON và giới hạn những mẫu quá rộng.

### Dùng NativeQuery

Trong Spring Data Elasticsearch 5.x, NativeQuery cho phép dùng Elasticsearch Java API Client builder. Ví dụ prefix:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.prefix(p -> p
                .field("sku")
                .value("KB-")))
        .build();

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Ví dụ wildcard:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.wildcard(w -> w
                .field("sku")
                .value("KB-*-BLK")))
        .build();
~~~

Ví dụ regexp:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.regexp(r -> r
                .field("sku")
                .value("KB-[0-9]{4}")))
        .build();
~~~

Các builder trên minh họa cách biểu đạt Query DSL bằng Java API Client. Tên package, kiểu giá trị, overload và tùy chọn như case_insensitive/rewrite phụ thuộc phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client. Dùng đúng dependency được Spring Boot quản lý và kiểm tra compile theo phiên bản dự án.

### Dùng Criteria khi phù hợp

Criteria API có các phép toán như **startsWith**, **contains** hoặc các điều kiện so khớp tùy phiên bản. Chúng có thể giúp diễn đạt một số trường hợp prefix/wildcard mà không viết JSON. Tuy nhiên, không nên mặc định rằng mọi method Criteria tạo ra đúng query hoặc tùy chọn bạn muốn.

Nếu chi phí, rewrite, case-insensitive hoặc cấu trúc query là yêu cầu quan trọng, hãy dùng StringQuery/NativeQuery để chỉ định rõ DSL. Sau đó kiểm tra request thực tế được gửi đến Elasticsearch.

## 14. Giới hạn đầu vào để tránh truy vấn quá rộng

Nếu người dùng có thể tự nhập wildcard hoặc regexp, ứng dụng nên có quy tắc kiểm soát đầu vào. Một endpoint tìm kiếm không nên cho phép bất kỳ mẫu nào mà người dùng gửi, đặc biệt khi index lớn hoặc nhiều người cùng truy vấn.

Một số biện pháp:

- Giới hạn độ dài pattern.
- Yêu cầu prefix có độ dài tối thiểu, ví dụ ít nhất 2 hoặc 3 ký tự tùy dữ liệu.
- Từ chối leading wildcard nếu nghiệp vụ không cần tìm chuỗi con.
- Giới hạn số nhánh OR và độ phức tạp regexp.
- Chỉ cho phép một tập ký tự hợp lệ đối với SKU.
- Dùng timeout phù hợp ở cấp search request.
- Phân trang và giới hạn size.
- Đặt rate limit cho endpoint tìm kiếm.
- Theo dõi tỷ lệ query chậm và số lượng request bị từ chối.
- Không cho người dùng tự do điều khiển toàn bộ Query DSL nếu họ chỉ cần tìm kiếm đơn giản.

Ví dụ kiểm tra sơ bộ pattern SKU trong service:

~~~java
public String validateSkuPrefix(String prefix) {
    if (prefix == null || prefix.length() < 3 || prefix.length() > 20) {
        throw new IllegalArgumentException("Prefix phải dài từ 3 đến 20 ký tự");
    }

    if (!prefix.matches("[A-Za-z0-9-]+")) {
        throw new IllegalArgumentException("Prefix chứa ký tự không hợp lệ");
    }

    return prefix;
}
~~~

Đây là kiểm tra đầu vào ở tầng ứng dụng, không phải thay thế validation của Elasticsearch. Quy tắc thực tế cần dựa trên định dạng SKU của hệ thống. Nếu SKU hợp lệ có ký tự khác, hãy điều chỉnh allowlist.

Đối với regexp, nên cung cấp các mẫu nghiệp vụ cố định thay vì cho người dùng gửi regex tự do. Ví dụ người dùng chọn loại mã và nhập phần số; service tự xây dựng pattern đã kiểm soát.

## 15. Đo lường hiệu năng truy vấn

Không thể kết luận chi phí chỉ dựa vào tên query. Hãy đo trên index có phân bố term gần với dữ liệu production.

Các bước kiểm tra:

1. Tạo tập dữ liệu đủ đại diện về số lượng và độ đa dạng term.
2. Chạy prefix, wildcard và regexp với những pattern thực tế.
3. So sánh pattern có tiền tố cố định với leading wildcard.
4. Kiểm tra số lượng hit, độ trễ và tài nguyên node.
5. Dùng profile khi cần tìm phần thực thi tốn thời gian.
6. Thử với số shard và mapping gần môi trường triển khai.
7. Đo cả thời gian ghi và kích thước index nếu thêm index_prefixes, edge_ngram hoặc wildcard field.

Có thể bật **profile** trong request để xem chi tiết quá trình thực thi:

~~~http
POST /products/_search
{
  "profile": true,
  "query": {
    "wildcard": {
      "sku": {
        "value": "*100*"
      }
    }
  }
}
~~~

Profile bổ sung chi phí cho request và thường tạo response lớn. Chỉ dùng khi điều tra, không bật mặc định cho mọi request production.

Có thể theo dõi slow logs của Elasticsearch để phát hiện truy vấn vượt ngưỡng thời gian. Kết hợp số liệu từ ứng dụng như thời gian response, số lượng request và pattern đã sử dụng để tìm endpoint hoặc loại pattern gây tải.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Prefix không tìm thấy chuỗi hiển thị bắt đầu bằng tiền tố | Query đang chạy trên term của text field, không phải toàn bộ chuỗi | Dùng keyword subfield hoặc trường autocomplete phù hợp |
| Prefix không phân biệt hoa thường như mong đợi | Term được lập chỉ mục có dạng chữ khác với query | Dùng normalizer hoặc tùy chọn case-insensitive nếu phiên bản hỗ trợ |
| Wildcard query chậm | Pattern có leading wildcard hoặc khớp quá nhiều term | Ưu tiên prefix, giới hạn pattern hoặc thay đổi mapping |
| Regexp bị từ chối | Pattern tạo automaton quá phức tạp hoặc vượt giới hạn | Đơn giản hóa biểu thức và kiểm tra max_determinized_states |
| Query bị từ chối là expensive | Cluster tắt search.allow_expensive_queries hoặc query không có tối ưu phù hợp | Kiểm tra setting và thiết kế lại query/index |
| Dùng regex Java nhưng Elasticsearch báo lỗi | Cú pháp Lucene regexp khác Java/PCRE | Chuyển pattern sang cú pháp Lucene và kiểm tra tài liệu |
| Tìm chuỗi con bằng prefix không được | Prefix chỉ khớp phần đầu của term | Dùng wildcard hoặc thiết kế n-gram/wildcard field nếu thực sự cần |
| Wildcard * trả quá nhiều kết quả | Pattern quá rộng | Dùng exists query nếu chỉ kiểm tra trường có giá trị |
| Thay mapping nhưng query vẫn cũ | Index hiện tại chưa được tạo lại/reindex | Tạo index mới và chuyển dữ liệu nếu mapping cần thay đổi |
| Query đúng cú pháp nhưng không có hit | Sai field, analyzer, normalizer hoặc dữ liệu không có term tương ứng | Đọc mapping, dùng _analyze với text field và kiểm tra term thực tế |

## 17. Quy trình chọn query cho ứng dụng

Khi xây dựng tìm kiếm theo một phần chuỗi, có thể áp dụng quy trình sau:

1. **Xác định mục tiêu.** Người dùng tìm tiền tố, hậu tố, chuỗi con hay mẫu mã?
2. **Kiểm tra mapping.** Trường là text, keyword hay wildcard? Có normalizer hoặc multi-field không?
3. **Chọn query hẹp nhất.** Prefix cho tiền tố; wildcard cho mẫu ký tự đơn giản; regexp khi cần quy tắc mẫu phức tạp.
4. **Đánh giá analyzer.** Term-level query không phân tích chuỗi truy vấn; cần bảo đảm term và input được chuẩn hóa tương thích.
5. **Giới hạn đầu vào.** Chặn pattern quá rộng, leading wildcard không cần thiết và regexp phức tạp.
6. **Xem xét tối ưu index.** Dùng index_prefixes, edge_ngram, search_as_you_type hoặc wildcard field theo đúng loại nhu cầu.
7. **Đo hiệu năng.** Dùng dữ liệu đại diện, slow logs và profile khi cần.
8. **Kiểm tra setting cluster.** Xác nhận search.allow_expensive_queries và các giới hạn liên quan.
9. **Tích hợp Spring Data.** Dùng Criteria nếu biểu đạt đủ; dùng StringQuery hoặc NativeQuery khi cần kiểm soát DSL.
10. **Kiểm tra request thực tế.** Xác nhận field, pattern, rewrite và các tùy chọn được gửi đúng.

Prefix, wildcard và regexp đều có thể tìm một phần term, nhưng mức độ linh hoạt đi cùng chi phí. Prefix là lựa chọn nên xem xét đầu tiên khi người dùng tìm theo tiền tố. Wildcard phù hợp với mẫu ký tự đơn giản nhưng cần tránh leading wildcard rộng. Regexp chỉ nên dùng khi quy tắc mẫu thực sự cần thiết và phải giới hạn độ phức tạp. Khi nhu cầu tìm kiếm lặp lại và có thể dự đoán, thiết kế mapping như index_prefixes, edge_ngram hoặc wildcard field thường giúp kiểm soát chi phí tốt hơn việc gửi các truy vấn mở rộng tùy ý.
