# Term suggester, phrase suggester và đọc kết quả suggest

Elasticsearch cung cấp **term suggester** và **phrase suggester** để đề xuất cách viết khác cho văn bản người dùng nhập. Chúng thường được dùng để hỗ trợ sửa lỗi chính tả, gợi ý cụm từ hoặc hiển thị câu hỏi “Có phải bạn muốn tìm…?” trên giao diện tìm kiếm.

Hai suggester có mục đích khác nhau:

- **Term suggester** xử lý từng token riêng lẻ, tìm các term gần giống trong từ điển term của một trường.
- **Phrase suggester** xét cả chuỗi token và dùng thông tin về các cụm từ đã xuất hiện trong dữ liệu để chọn cách sửa có ngữ cảnh tốt hơn.

Suggester không phải truy vấn tìm tài liệu thông thường. Nó tạo danh sách đề xuất từ dữ liệu đã được lập chỉ mục. Một search request có thể trả về hit, suggestion hoặc cả hai. Vì vậy, khi đọc response, cần tách **hits** khỏi **suggest** và hiểu ý nghĩa của từng option.

Bài này sử dụng index **products** với trường **name** và một subfield phục vụ phrase suggestion. Nội dung tập trung vào cấu hình term/phrase suggester, cách đọc kết quả và cách tích hợp với Spring Data Elasticsearch.

## 1. Suggestion khác kết quả tìm kiếm như thế nào?

Một truy vấn tìm kiếm thông thường trả về các tài liệu phù hợp với điều kiện query. Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireles keybord"
    }
  }
}
~~~

Nếu người dùng gõ sai chính tả, truy vấn có thể không tìm thấy sản phẩm mong muốn. Suggester giải quyết một vấn đề khác: dựa trên các term đã được lập chỉ mục, nó đề xuất cách viết gần đúng hoặc cụm từ có khả năng đúng hơn.

Ví dụ, người dùng nhập:

~~~text
wireles keybord
~~~

Term suggester có thể đề xuất riêng từng từ:

- **wireles** → **wireless**
- **keybord** → **keyboard**

Phrase suggester có thể đề xuất cả cụm:

- **wireles keybord** → **wireless keyboard**

Suggester không tự động có nghĩa là Elasticsearch đã tìm thấy tài liệu tương ứng. Nó chỉ tạo ứng viên đề xuất dựa trên từ điển term và mô hình thống kê. Nếu giao diện cần biết một đề xuất có thực sự trả về sản phẩm hay không, ứng dụng có thể chạy truy vấn kiểm tra hoặc dùng **collate** với phrase suggester.

Có thể kết hợp cả query và suggest trong cùng một request:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireles keybord"
    }
  },
  "suggest": {
    "name-term": {
      "text": "wireles keybord",
      "term": {
        "field": "name"
      }
    }
  }
}
~~~

Response có thể chứa cả phần **hits** và phần **suggest**. Nếu chỉ cần đề xuất, có thể đặt **size: 0** để không trả danh sách hit nhưng vẫn nhận suggest result.

## 2. Cấu trúc suggest trong search request

Suggester được khai báo trong thuộc tính **suggest** ở cấp search request, cùng cấp với **query**, **from**, **size**, **sort** và **aggs**.

Ví dụ request chỉ lấy đề xuất:

~~~http
POST /products/_search
{
  "size": 0,
  "suggest": {
    "product-name-term": {
      "text": "wireles keybord",
      "term": {
        "field": "name",
        "suggest_mode": "always",
        "size": 3
      }
    }
  }
}
~~~

Cấu trúc tổng quát:

~~~text
Search request
|
+-- query             (điều kiện tìm tài liệu, nếu cần)
|
+-- from / size       (phân trang hit)
|
+-- suggest
|   |
|   +-- product-name-term
|   |   |
|   |   +-- text
|   |   +-- term
|   |
|   +-- product-name-phrase
|       |
|       +-- text
|       +-- phrase
|
+-- sort / aggs / highlight / ...
~~~

Mỗi suggester có một tên riêng, ví dụ **product-name-term** và **product-name-phrase**. Tên này được dùng làm key tương ứng trong response để ứng dụng biết kết quả thuộc cấu hình nào.

Có thể đặt **text** ở từng suggester hoặc dùng văn bản chung ở cấp suggest tùy cấu trúc Search API. Đặt text riêng giúp mỗi suggester dùng nội dung khác nhau; đặt text chung thuận tiện khi term và phrase suggester cùng xử lý một chuỗi.

Cần phân biệt hai thuộc tính có tên gần nhau:

- **size** ở cấp search request giới hạn số hit trả về.
- **size** trong cấu hình suggester giới hạn số option đề xuất cho mỗi entry.

Đặt **size: 0** ở cấp request không có nghĩa là tắt suggestion. Suggester vẫn được xử lý và trả kết quả trong phần **suggest**.

## 3. Term suggester hoạt động như thế nào?

**Term suggester** chia văn bản đầu vào thành các token theo analyzer của trường được chỉ định. Với mỗi token, nó tìm những term gần giống trong từ điển term đã lập chỉ mục và xếp hạng các ứng viên theo cấu hình.

Ví dụ:

~~~http
POST /products/_search
{
  "size": 0,
  "suggest": {
    "name-correction": {
      "text": "wireles keybord",
      "term": {
        "field": "name",
        "suggest_mode": "always",
        "size": 3
      }
    }
  }
}
~~~

Giả sử index có các tên:

- Wireless Mechanical Keyboard
- Wireless Mouse
- Compact Keyboard
- Mechanical Keyboard

Term suggester có thể tạo đề xuất cho từng token sai chính tả. Kết quả thường được trả thành các entry riêng theo vị trí token trong văn bản đầu vào.

Term suggester dựa trên từ điển term của trường. Nó không hiểu đầy đủ ngữ cảnh ngôn ngữ như một mô hình ngôn ngữ tự nhiên. Nếu một từ sai chính tả lại là một từ hợp lệ và phổ biến trong index, term suggester có thể không xem đó là lỗi.

### Các tùy chọn thường dùng của term suggester

| Tùy chọn | Ý nghĩa |
|---|---|
| **field** | Trường dùng để lấy term dictionary và analyzer |
| **suggest_mode** | Quy định khi nào tạo đề xuất |
| **size** | Số option tối đa cho mỗi entry |
| **sort** | Sắp xếp option theo score hoặc frequency |
| **max_edits** | Số chỉnh sửa tối đa khi so sánh term |
| **prefix_length** | Số ký tự đầu phải giữ nguyên |
| **min_word_length** | Độ dài tối thiểu của token được xử lý |
| **min_doc_freq** | Tần suất tài liệu tối thiểu của ứng viên |
| **max_term_freq** | Giới hạn tần suất của term đầu vào để xử lý |
| **max_inspections** | Mức mở rộng ứng viên được kiểm tra |
| **string_distance** | Thuật toán đo khoảng cách giữa các term |
| **shard_size** | Số ứng viên term được xem xét trên mỗi shard trước khi tổng hợp |

Không cần đặt tất cả tùy chọn cho mọi trường hợp. Bắt đầu với **field**, **suggest_mode** và **size**; chỉ tinh chỉnh các tham số khác khi đã có bộ truy vấn thực tế để đánh giá.

## 4. suggest_mode: missing, popular và always

**suggest_mode** quyết định khi nào term suggester đưa ra đề xuất.

| Giá trị | Hành vi |
|---|---|
| **missing** | Chỉ đề xuất khi token đầu vào không tồn tại trong từ điển term |
| **popular** | Chỉ đề xuất term có tần suất cao hơn term đầu vào |
| **always** | Luôn tìm đề xuất, kể cả khi token đầu vào đã tồn tại |

Ví dụ với **missing**:

~~~json
{
  "term": {
    "field": "name",
    "suggest_mode": "missing"
  }
}
~~~

Nếu người dùng nhập **wireless**, và term này đã tồn tại trong index, suggester thường không đề xuất cách viết khác cho token đó. Đây là chế độ phù hợp cho tính năng sửa lỗi chính tả cơ bản.

Với **popular**, Elasticsearch chỉ đưa ra ứng viên có mức phổ biến cao hơn token đầu vào. Chế độ này hữu ích khi muốn ưu tiên từ thường gặp hơn, nhưng cũng có thể loại bỏ một thuật ngữ hợp lệ ít phổ biến.

Với **always**, suggester tìm ứng viên cho mọi token. Chế độ này phù hợp khi muốn cung cấp gợi ý ngay cả khi từ đầu vào tồn tại, nhưng có thể tạo đề xuất không cần thiết. Giao diện cần cân nhắc cách trình bày để không làm người dùng bối rối.

Nếu không chỉ định, **missing** là chế độ mặc định thường gặp. Hãy kiểm tra mặc định của phiên bản Elasticsearch đang chạy khi cần hành vi nhất quán giữa các môi trường.

## 5. Khoảng cách chỉnh sửa và giới hạn ứng viên

Term suggester thường dùng khoảng cách chỉnh sửa để tìm term gần giống. Một chỉnh sửa có thể là thêm, xóa, thay thế hoặc hoán đổi ký tự tùy thuật toán distance.

**max_edits** giới hạn số chỉnh sửa. Elasticsearch thường hỗ trợ các giá trị nhỏ như 1 hoặc 2 cho term suggester. Giá trị lớn hơn có thể làm tăng số ứng viên và chi phí xử lý, đồng thời tạo nhiều đề xuất kém liên quan.

**prefix_length** yêu cầu một số ký tự đầu phải giống nhau. Ví dụ prefix_length bằng 1 nghĩa là ứng viên phải giữ ký tự đầu của term. Điều này giúp thu hẹp không gian tìm kiếm.

**min_word_length** tránh xử lý các token quá ngắn. Với từ có hai ký tự, một lỗi nhỏ có thể tạo ra rất nhiều ứng viên không hữu ích.

Ví dụ:

~~~json
{
  "term": {
    "field": "name",
    "suggest_mode": "missing",
    "max_edits": 2,
    "prefix_length": 1,
    "min_word_length": 3,
    "size": 3
  }
}
~~~

Không nên tăng max_edits chỉ để có thêm kết quả. Hãy xem các đề xuất thực tế và cân bằng giữa khả năng tìm được cách viết đúng với tỷ lệ gợi ý sai.

### sort theo score hoặc frequency

Term suggester có thể sắp xếp option theo:

- **score**: mức độ gần giống theo thuật toán string distance.
- **frequency**: tần suất xuất hiện của term trong index.

Nếu chọn score, ứng viên gần với chuỗi đầu vào hơn có thể được ưu tiên. Nếu chọn frequency, từ phổ biến hơn có thể đứng trước dù không phải lúc nào cũng gần nhất về mặt chính tả.

Tùy chọn sort này ảnh hưởng thứ tự đề xuất trong từng entry. Nó không phải **sort** của search request và không sắp xếp danh sách tài liệu trong hits.

## 6. Field và analyzer ảnh hưởng đến term suggester

Term suggester lấy token từ văn bản đầu vào thông qua analyzer của trường. Do đó, trường được chỉ định phải phù hợp với ngôn ngữ và kiểu dữ liệu.

Ví dụ trường **name** là text:

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "analyzer": "standard"
    }
  }
}
~~~

Analyzer standard tách văn bản thành token và chuẩn hóa một số đặc điểm. Với tiếng Anh, từ có thể được chuyển về dạng chữ thường. Term suggester sẽ xử lý các token theo cách analyzer quy định.

Nếu dùng trường keyword, toàn bộ tên sản phẩm có thể được coi như một term duy nhất. Khi đó, term suggester có thể xử lý cả chuỗi thay vì từng từ riêng lẻ, không phù hợp với mục tiêu sửa từng từ trong tên dài.

Đối với tiếng Việt hoặc ngôn ngữ cần tách từ chuyên biệt, analyzer mặc định có thể không tạo token như mong muốn. Cần chọn analyzer phù hợp với ngôn ngữ và dữ liệu thực tế. Suggester chỉ có thể đề xuất dựa trên những term được tạo ra trong quá trình lập chỉ mục.

Khi thay đổi analyzer, index hiện tại thường cần tạo lại và reindex để các tài liệu được phân tích theo cấu hình mới. Chỉ sửa annotation hoặc settings trong code không tự tái phân tích những tài liệu đã có.

## 7. Phrase suggester giải quyết vấn đề gì?

Term suggester xử lý từng token riêng. Nó có thể đề xuất nhiều từ gần giống, nhưng không luôn biết tổ hợp nào tạo thành cụm từ hợp lý.

Ví dụ người dùng nhập:

~~~text
wireles keybord
~~~

Term suggester có thể đưa ra:

- **wireles** → **wireless**
- **keybord** → **keyboard**

Phrase suggester xét cả chuỗi và thông tin đồng xuất hiện của các term. Nó có thể ưu tiên **wireless keyboard** vì cụm này xuất hiện hợp lý trong dữ liệu, thay vì ghép các lựa chọn chỉ dựa trên khoảng cách ký tự.

Phrase suggester sử dụng mô hình ngôn ngữ n-gram. Vì vậy, trường được dùng cho phrase suggester thường cần được lập chỉ mục với analyzer tạo **shingle** (các cụm token liền kề), chẳng hạn bigram hoặc trigram.

Suggester không phải một hệ thống hiểu ngữ nghĩa hoàn chỉnh. Chất lượng đề xuất phụ thuộc vào nội dung index, độ phổ biến của cụm từ, analyzer, smoothing model và các tham số cấu hình.

## 8. Chuẩn bị shingle field cho phrase suggester

Để phrase suggester hoạt động tốt, thường tạo một multi-field chuyên dụng có analyzer dùng shingle filter.

Ví dụ settings:

~~~json
{
  "analysis": {
    "filter": {
      "name_shingle": {
        "type": "shingle",
        "min_shingle_size": 2,
        "max_shingle_size": 3,
        "output_unigrams": true
      }
    },
    "analyzer": {
      "name_trigram": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
          "lowercase",
          "name_shingle"
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
    "name": {
      "type": "text",
      "analyzer": "standard",
      "fields": {
        "trigram": {
          "type": "text",
          "analyzer": "name_trigram"
        }
      }
    }
  }
}
~~~

Với văn bản **wireless mechanical keyboard**, analyzer shingle có thể tạo các token đơn và các cụm liên tiếp, ví dụ:

- unigram: **wireless**, **mechanical**, **keyboard**
- bigram: **wireless mechanical**, **mechanical keyboard**
- trigram: **wireless mechanical keyboard**

Các token cụm giúp phrase suggester đánh giá khả năng một chuỗi từ xuất hiện cùng nhau trong dữ liệu.

**output_unigrams: true** giữ cả token đơn cùng với shingle. Cấu hình cụ thể cần phù hợp với mục tiêu và phiên bản Elasticsearch. Không nên áp dụng shingle analyzer cho mọi trường text; hãy tạo multi-field riêng để tìm kiếm toàn văn bình thường vẫn dùng analyzer phù hợp.

Nếu index đã tồn tại mà chưa có subfield trigram, cần tạo index mới với mapping và settings phù hợp rồi reindex dữ liệu. Không thể kỳ vọng phrase suggester có mô hình n-gram đầy đủ nếu các shingle term chưa được lập chỉ mục.

## 9. Cấu hình phrase suggester

Ví dụ phrase suggester cho cụm **wireles keybord**:

~~~http
POST /products/_search
{
  "size": 0,
  "suggest": {
    "name-phrase": {
      "text": "wireles keybord",
      "phrase": {
        "field": "name.trigram",
        "size": 3,
        "gram_size": 3,
        "direct_generator": [
          {
            "field": "name.trigram",
            "suggest_mode": "always",
            "min_word_length": 3
          }
        ],
        "highlight": {
          "pre_tag": "<em>",
          "post_tag": "</em>"
        }
      }
    }
  }
}
~~~

Các phần chính:

- **field**: trường có shingle term được dùng để xây dựng mô hình phrase.
- **size**: số cụm đề xuất tối đa.
- **gram_size**: kích thước n-gram phù hợp với cấu hình shingle.
- **direct_generator**: nguồn tạo candidate term cho từng token.
- **suggest_mode**: quy định khi nào direct generator đề xuất.
- **min_word_length**: bỏ qua token quá ngắn.
- **highlight**: đánh dấu phần văn bản được thay đổi trong option.

Phrase suggester dùng candidate từ direct generator rồi đánh giá các tổ hợp theo mô hình cụm từ. Nếu field hoặc analyzer không tạo shingle phù hợp, chất lượng đề xuất có thể kém hoặc query không hoạt động theo kỳ vọng.

### Các tùy chọn phrase thường gặp

| Tùy chọn | Vai trò |
|---|---|
| **field** | Trường có n-gram/shingle dùng cho phrase model |
| **size** | Số phrase option trả về |
| **gram_size** | Kích thước n-gram được dùng trong mô hình |
| **direct_generator** | Cấu hình sinh candidate term |
| **confidence** | Ngưỡng score tương đối để giữ candidate |
| **max_errors** | Giới hạn số token có thể bị sửa |
| **separator** | Ký tự phân tách token trong phrase model |
| **real_word_error_likelihood** | Ước lượng khả năng một từ hợp lệ thực ra là lỗi |
| **force_unigrams** | Điều khiển việc dùng unigram khi xử lý phrase |
| **token_limit** | Giới hạn số token được xử lý |
| **highlight** | Đánh dấu phần được đề xuất thay đổi |
| **collate** | Kiểm tra candidate phrase bằng một query mẫu |

Không cần điều chỉnh tất cả tham số ngay từ đầu. Bắt đầu với field shingle, direct_generator, size và highlight; sau đó đánh giá confidence hoặc max_errors bằng dữ liệu truy vấn thật.

## 10. direct_generator trong phrase suggester

Phrase suggester không tự sinh mọi candidate từ đầu. **direct_generator** chỉ định cách tạo các candidate term cho từng token, thường sử dụng cấu hình term suggester.

Ví dụ:

~~~json
{
  "phrase": {
    "field": "name.trigram",
    "direct_generator": [
      {
        "field": "name.trigram",
        "suggest_mode": "always",
        "max_edits": 2,
        "prefix_length": 1,
        "min_word_length": 3
      }
    ]
  }
}
~~~

Có thể khai báo nhiều direct generator để lấy candidate từ các trường hoặc cấu hình khác nhau. Phrase suggester sau đó kết hợp candidate và đánh giá toàn bộ chuỗi bằng n-gram model.

Điều này giải thích sự khác biệt giữa hai suggester:

- Term suggester trả các lựa chọn cho từng token.
- Phrase suggester dùng các candidate token nhưng đánh giá cả cụm từ dựa trên ngữ cảnh.

Nếu direct generator quá rộng, số candidate tăng và chi phí phrase scoring có thể tăng. Nếu quá hẹp, phrase suggester có thể bỏ lỡ cách sửa đúng. Cần điều chỉnh dựa trên ngôn ngữ, độ dài truy vấn và chất lượng dữ liệu.

## 11. confidence và max_errors

**confidence** kiểm soát mức độ chấp nhận candidate phrase so với score của cụm đầu vào. Candidate cần đạt ngưỡng tương đối để được giữ lại. Giá trị confidence cao hơn thường làm suggester thận trọng hơn và có thể trả ít đề xuất hơn.

**max_errors** giới hạn số token được phép sửa trong phrase. Giá trị này giúp tránh thay đổi quá nhiều từ trong một truy vấn dài. Cách diễn giải chính xác của giá trị và giới hạn phụ thuộc API/phiên bản; hãy tham khảo Phrase Suggester reference khi tinh chỉnh.

Ví dụ:

~~~json
{
  "phrase": {
    "field": "name.trigram",
    "confidence": 1.0,
    "max_errors": 1.0,
    "size": 3
  }
}
~~~

Không nên đặt confidence quá thấp chỉ để có nhiều option. Đề xuất càng nhiều chưa chắc càng hữu ích. Một phrase suggester tốt nên ưu tiên một vài lựa chọn có khả năng đúng cao.

## 12. Dùng collate để kiểm tra đề xuất có tài liệu phù hợp

Phrase suggester có thể dùng **collate** để kiểm tra candidate phrase có khớp tài liệu hay không. Collate chạy một query template với biến **{{suggestion}}** được thay bằng phrase được đề xuất.

Ví dụ:

~~~json
{
  "phrase": {
    "field": "name.trigram",
    "direct_generator": [
      {
        "field": "name.trigram",
        "suggest_mode": "always"
      }
    ],
    "collate": {
      "query": {
        "source": {
          "match": {
            "name": "{{suggestion}}"
          }
        }
      },
      "prune": true
    }
  }
}
~~~

Ý nghĩa:

- Phrase suggester tạo candidate.
- Collate chạy query match trên trường name với nội dung candidate.
- **prune: true** yêu cầu response giữ thông tin candidate có khớp hay không và loại những candidate không khớp theo hành vi prune của API.
- Kết quả collate giúp ứng dụng đánh giá đề xuất có thể dẫn đến tài liệu hay không.

Collate có thể tăng chi phí vì mỗi candidate cần được kiểm tra bằng query template. Dùng khi trải nghiệm người dùng cần tránh gợi ý không có kết quả, và giới hạn số candidate phù hợp.

Nếu ứng dụng có filter nghiệp vụ như status ACTIVE hoặc tenant, query collate cần thể hiện các điều kiện đó nếu chỉ muốn đề xuất có tài liệu trong phạm vi tương ứng. Đừng giả định collate tự kế thừa toàn bộ query/filter ở phần search request chính.

## 13. Đọc response của term suggester

Kết quả suggester nằm trong thuộc tính **suggest** của response và được nhóm theo tên suggester.

Ví dụ response rút gọn:

~~~json
{
  "suggest": {
    "name-correction": [
      {
        "text": "wireles",
        "offset": 0,
        "length": 7,
        "options": [
          {
            "text": "wireless",
            "score": 0.875,
            "freq": 42
          }
        ]
      },
      {
        "text": "keybord",
        "offset": 8,
        "length": 7,
        "options": [
          {
            "text": "keyboard",
            "score": 0.875,
            "freq": 31
          }
        ]
      }
    ]
  }
}
~~~

Mỗi entry có ý nghĩa:

- **text**: token hoặc đoạn đầu vào đang được xử lý.
- **offset**: vị trí bắt đầu của đoạn trong chuỗi đầu vào.
- **length**: độ dài đoạn đầu vào.
- **options**: danh sách candidate được đề xuất.
- **options.text**: cách viết được đề xuất.
- **options.score**: điểm của candidate theo cơ chế suggester.
- **options.freq**: tần suất tài liệu của term candidate khi trường thông tin này được trả về.

Term suggester thường tạo entry riêng cho từng token. Vì vậy, một truy vấn nhiều từ có thể có nhiều entry trong cùng một suggester.

**score của suggestion không phải _score của document hit và không phải xác suất.** Không nên diễn giải score 0.875 thành 87,5% khả năng đúng. Nó là điểm nội bộ để xếp hạng candidate theo thuật toán suggester.

**freq** cũng không có nghĩa là số tài liệu chắc chắn sẽ được trả về bởi query hiện tại. Nó phản ánh tần suất term trong index theo cách suggester báo cáo, không tự động áp dụng mọi filter nghiệp vụ của search request.

## 14. Đọc response của phrase suggester

Phrase suggester thường trả entry cho cả chuỗi đầu vào và các option là cụm từ được đề xuất.

Ví dụ response rút gọn:

~~~json
{
  "suggest": {
    "name-phrase": [
      {
        "text": "wireles keybord",
        "offset": 0,
        "length": 15,
        "options": [
          {
            "text": "wireless keyboard",
            "highlighted": "<em>wireless</em> <em>keyboard</em>",
            "score": 0.72,
            "collate_match": true
          }
        ]
      }
    ]
  }
}
~~~

Các trường quan trọng:

- **text**: cụm từ đầu vào.
- **offset** và **length**: vị trí của cụm trong văn bản.
- **options**: danh sách phrase candidate.
- **options.text**: cụm từ hoàn chỉnh được đề xuất.
- **options.highlighted**: nội dung đã gắn thẻ đánh dấu nếu cấu hình highlight.
- **options.score**: điểm của phrase candidate.
- **options.collate_match**: kết quả kiểm tra collate nếu request dùng collate.

Một phrase option có thể chứa thêm metadata tùy suggester và phiên bản. Không giả định mọi option luôn có **freq**, **highlighted** hoặc **collate_match**; các trường này phụ thuộc cấu hình và loại suggester.

### Highlight của suggestion

Với cấu hình:

~~~json
{
  "highlight": {
    "pre_tag": "<em>",
    "post_tag": "</em>"
  }
}
~~~

Phrase suggester có thể trả chuỗi đã đánh dấu phần thay đổi. Giao diện có thể dùng dữ liệu này để hiển thị phần được sửa nổi bật.

Nếu hiển thị HTML, không ghép chuỗi highlight chưa được kiểm soát vào DOM. Hãy dùng renderer an toàn, xử lý escaping phù hợp và chỉ cho phép các thẻ đánh dấu do ứng dụng quy định. Nội dung suggestion có thể chứa ký tự đặc biệt từ văn bản người dùng hoặc dữ liệu index.

## 15. Kết hợp term và phrase suggester trong cùng request

Có thể khai báo nhiều suggester cùng lúc để so sánh kết quả theo từng mức.

~~~http
POST /products/_search
{
  "size": 0,
  "suggest": {
    "name-term": {
      "text": "wireles keybord",
      "term": {
        "field": "name",
        "suggest_mode": "always",
        "size": 3,
        "sort": "score"
      }
    },
    "name-phrase": {
      "text": "wireles keybord",
      "phrase": {
        "field": "name.trigram",
        "size": 3,
        "gram_size": 3,
        "direct_generator": [
          {
            "field": "name.trigram",
            "suggest_mode": "always",
            "max_edits": 2,
            "prefix_length": 1
          }
        ],
        "highlight": {
          "pre_tag": "<em>",
          "post_tag": "</em>"
        }
      }
    }
  }
}
~~~

Term suggester trả đề xuất theo từng token; phrase suggester trả đề xuất theo cả cụm. Ứng dụng có thể:

- Dùng term suggestions để hiển thị cách sửa từng từ.
- Dùng phrase suggestion làm lựa chọn “Có phải bạn muốn tìm…?”.
- So sánh số lượng option và score theo từng suggester.
- Chạy query chính bằng phrase được chọn sau khi người dùng xác nhận.

Không nên tự động thay thế mọi từ trong truy vấn của người dùng mà không có chính sách rõ ràng. Đối với giao diện tìm kiếm, thường nên hiển thị đề xuất và cho phép người dùng chọn.

## 16. Đọc nhiều suggester và xử lý khi không có option

Một suggester có thể trả về entry nhưng danh sách **options** rỗng. Điều đó không nhất thiết là lỗi.

Các nguyên nhân thường gặp:

- Token đầu vào đã tồn tại và suggest_mode là missing.
- Không có candidate nằm trong giới hạn max_edits.
- Token ngắn hơn min_word_length.
- Candidate bị loại bởi min_doc_freq, max_term_freq hoặc confidence.
- Field/analyzer không có term phù hợp.
- Phrase model không có đủ shingle statistics để tạo đề xuất tốt.

Ví dụ xử lý ở tầng giao diện:

~~~text
Nếu options có phần tử:
    Hiển thị các đề xuất
Nếu options rỗng:
    Không hiển thị hộp gợi ý
    Giữ nguyên truy vấn ban đầu
~~~

Không nên coi options rỗng là lỗi HTTP hoặc tự động trả 404. Đây là kết quả hợp lệ của chức năng suggestion.

Nếu request có cả query và suggest, response có thể có hit rỗng nhưng suggestion vẫn có option, hoặc có hit nhưng không có option. Hai phần kết quả độc lập về mục đích và cần được xử lý riêng.

## 17. Term/phrase suggester có tự lọc theo query không?

Không nên giả định phần suggest tự động kế thừa điều kiện query chính.

Ví dụ request có query chỉ tìm sản phẩm ACTIVE:

~~~json
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "suggest": {
    "name-phrase": {
      "text": "wireles keybord",
      "phrase": {
        "field": "name.trigram"
      }
    }
  }
}
~~~

Query chính giới hạn hits theo status. Suggester lại sử dụng term dictionary và mô hình thống kê của field để tạo đề xuất. Một candidate có thể tồn tại trong index nhưng không có sản phẩm ACTIVE phù hợp.

Nếu chỉ muốn đề xuất có kết quả trong phạm vi nghiệp vụ, có thể dùng collate với các điều kiện tương ứng hoặc chạy một query kiểm tra sau khi nhận candidate.

Ví dụ query kiểm tra candidate ACTIVE:

~~~json
{
  "collate": {
    "query": {
      "source": {
        "bool": {
          "must": [
            {
              "match": {
                "name": "{{suggestion}}"
              }
            }
          ],
          "filter": [
            {
              "term": {
                "status": "ACTIVE"
              }
            }
          ]
        }
      }
    },
    "prune": true
  }
}
~~~

Cần cân nhắc chi phí của việc kiểm tra từng candidate. Nếu chỉ có vài option, chi phí có thể chấp nhận được; nếu số candidate lớn, hãy giới hạn size và đánh giá tải.

## 18. Dùng Java API Client để tạo suggest request

Trong các ứng dụng Spring Boot dùng Spring Data Elasticsearch 5.x, có thể inject **ElasticsearchClient** tương thích để xây dựng SearchRequest có suggester. Cách này hữu ích khi cần kiểm soát trực tiếp cấu trúc suggest và đọc response do Java API Client tạo ra.

Ví dụ term suggester:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.SearchRequest;
import co.elastic.clients.elasticsearch.core.SearchResponse;

SearchRequest request = SearchRequest.of(s -> s
        .index("products")
        .size(0)
        .suggest(suggest -> suggest
                .suggesters("name-term", item -> item
                        .text("wireles keybord")
                        .term(term -> term
                                .field("name")
                                .size(3)
                        )
                )
        )
);

SearchResponse<Product> response =
        elasticsearchClient.search(request, Product.class);
~~~

Ví dụ này minh họa request chỉ lấy suggestion. **size(0)** ở cấp SearchRequest tắt việc trả hit; **size(3)** bên trong term suggester giới hạn số option mỗi entry.

Có thể khai báo phrase suggester tương tự:

~~~java
SearchRequest request = SearchRequest.of(s -> s
        .index("products")
        .size(0)
        .suggest(suggest -> suggest
                .suggesters("name-phrase", item -> item
                        .text("wireles keybord")
                        .phrase(phrase -> phrase
                                .field("name.trigram")
                                .size(3)
                                .gramSize(3)
                                .directGenerator(generator -> generator
                                        .field("name.trigram")
                                )
                                .highlight(highlight -> highlight
                                        .preTag("<em>")
                                        .postTag("</em>")
                                )
                        )
                )
        )
);
~~~

Tên builder, enum và overload có thể thay đổi giữa các phiên bản Elasticsearch Java API Client. Hãy dùng dependency được Spring Boot quản lý và kiểm tra API đúng phiên bản dự án. Không trộn ví dụ từ RestHighLevelClient cũ với Java API Client mới.

## 19. Đọc suggest result từ Java API Client

Response của Java API Client chứa map **suggest**, trong đó key là tên suggester và value là danh sách suggestion entry. Mỗi entry là một kiểu union: term, phrase hoặc completion tùy loại suggester.

Ví dụ duyệt term suggestion:

~~~java
import co.elastic.clients.elasticsearch.core.SearchResponse;

SearchResponse<Product> response =
        elasticsearchClient.search(request, Product.class);

var entries = response.suggest().get("name-term");

if (entries != null) {
    for (var suggestion : entries) {
        if (suggestion.isTerm()) {
            for (var entry : suggestion.term()) {
                System.out.println("Input: " + entry.text());

                for (var option : entry.options()) {
                    System.out.println(
                            option.text() + " score=" + option.score()
                    );
                }
            }
        }
    }
}
~~~

Duyệt phrase suggestion:

~~~java
var entries = response.suggest().get("name-phrase");

if (entries != null) {
    for (var suggestion : entries) {
        if (suggestion.isPhrase()) {
            for (var entry : suggestion.phrase()) {
                System.out.println("Input: " + entry.text());

                for (var option : entry.options()) {
                    System.out.println(
                            option.text() + " score=" + option.score()
                    );
                }
            }
        }
    }
}
~~~

Các kiểu entry và option được sinh từ schema của Elasticsearch Java API Client. Một số getter có thể là nullable hoặc dùng kiểu Optional tùy phiên bản generated client. Hãy kiểm tra compile và API reference của dependency thực tế khi sử dụng các trường bổ sung như highlighted, freq hoặc collateMatch.

Nếu response có nhiều suggester, lấy theo đúng key đã đặt trong request. Không phụ thuộc thứ tự map hoặc giả định entry đầu tiên luôn thuộc một loại suggestion cụ thể.

## 20. Tích hợp với Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp các abstraction như **ElasticsearchOperations**, **Query**, **NativeQuery**, **SearchHits** và converter để tích hợp tìm kiếm với entity Java. Khả năng biểu diễn suggest trực tiếp và cách chuyển đổi suggest result có thể khác giữa các phiên bản.

Với truy vấn tìm kiếm thông thường, có thể dùng Operations:

~~~java
SearchHits<Product> hits =
        operations.search(query, Product.class, IndexCoordinates.of("products"));
~~~

Khi cần term/phrase suggester, hãy kiểm tra API của phiên bản Spring Data Elasticsearch đang dùng để biết NativeQuery và SearchHits có hỗ trợ cấu hình, chuyển đổi suggest result hay không. Nếu abstraction không biểu diễn được tùy chọn cần thiết, dùng **ElasticsearchClient** đã được Spring cấu hình để gửi SearchRequest trực tiếp, như ví dụ ở trên.

Một service có thể inject client:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import org.springframework.stereotype.Service;

@Service
public class ProductSuggestionService {

    private final ElasticsearchClient elasticsearchClient;

    public ProductSuggestionService(
            ElasticsearchClient elasticsearchClient) {
        this.elasticsearchClient = elasticsearchClient;
    }

    // Tạo SearchRequest và xử lý response trong các phương thức nghiệp vụ.
}
~~~

Không tạo ElasticsearchClient mới cho mỗi request. Dùng bean được cấu hình chung để tái sử dụng connection pool, TLS, credentials và timeout.

Nếu ứng dụng cần trả suggestion thành DTO cho controller, nên chuyển response thành kiểu đơn giản của riêng ứng dụng, ví dụ:

~~~java
public record SuggestionOption(
        String text,
        Double score,
        Long frequency
) {
}
~~~

DTO giúp controller không phụ thuộc trực tiếp vào kiểu generated của Elasticsearch Java API Client. Tùy loại suggester, frequency hoặc highlight có thể không có; các thuộc tính tương ứng nên là nullable hoặc được biểu diễn bằng kiểu phù hợp.

## 21. Thiết kế endpoint gợi ý cho giao diện tìm kiếm

Một endpoint suggestion thường nhận chuỗi người dùng đang nhập và trả danh sách lựa chọn ngắn.

Ví dụ response API do ứng dụng thiết kế:

~~~json
{
  "input": "wireles keybord",
  "suggestions": [
    {
      "text": "wireless keyboard",
      "type": "phrase",
      "score": 0.72
    }
  ]
}
~~~

Đây là DTO response của ứng dụng, không phải nguyên response Elasticsearch. Tách DTO giúp giao diện không cần hiểu cấu trúc phức tạp của Suggest API.

Một luồng điển hình:

1. Người dùng nhập một chuỗi.
2. Frontend gọi endpoint suggestion sau một khoảng debounce ngắn.
3. Backend kiểm tra độ dài và giới hạn input.
4. Backend chạy term hoặc phrase suggester.
5. Backend chuyển options thành DTO.
6. Frontend hiển thị một số đề xuất.
7. Khi người dùng chọn, frontend gửi truy vấn tìm kiếm chính với chuỗi đã chọn.

Không nên gửi request đến Elasticsearch sau mỗi phím bấm mà không có debounce hoặc giới hạn tần suất. Điều này có thể tạo lượng request lớn, đặc biệt khi suggester phải xử lý nhiều candidate.

### Khi nào hiển thị term và phrase?

- Term suggestions phù hợp để giải thích cách sửa từng token.
- Phrase suggestions phù hợp để đưa ra một cụm hoàn chỉnh có ngữ cảnh.
- Nếu phrase suggestion có collate_match, giao diện có thể ưu tiên các đề xuất đã được xác nhận có tài liệu.
- Nếu không có option, giữ nguyên truy vấn đầu vào và tiếp tục tìm kiếm theo chính sách của ứng dụng.

Không nên tự động sửa mọi truy vấn mà không cho người dùng biết. Trong một số nghiệp vụ, tên riêng, SKU hoặc thuật ngữ nội bộ có thể bị coi là lỗi chính tả dù đó là giá trị hợp lệ.

## 22. Các yếu tố ảnh hưởng chất lượng suggestion

Chất lượng đề xuất phụ thuộc vào nhiều yếu tố:

**Độ phong phú của dữ liệu.** Nếu index có ít tài liệu, term dictionary và shingle statistics không đủ đại diện cho ngôn ngữ người dùng.

**Analyzer.** Tokenization, lowercase, stemming và các bộ lọc ảnh hưởng trực tiếp đến term được suggester nhìn thấy. Analyzer không phù hợp có thể chia token sai hoặc làm mất thông tin.

**Tần suất term.** Term phổ biến có thể được ưu tiên theo frequency hoặc ảnh hưởng đến phrase model. Từ hiếm nhưng đúng có thể bị đề xuất thay bằng từ phổ biến hơn.

**Ngữ cảnh cụm từ.** Phrase suggester tận dụng shingle statistics, nhưng không hiểu ý nghĩa ngữ nghĩa như mô hình ngôn ngữ hiện đại.

**Tham số candidate.** max_edits, prefix_length, min_word_length, confidence, max_errors và size quyết định không gian ứng viên và mức độ chấp nhận.

**Lọc theo nghiệp vụ.** Một đề xuất có thể tồn tại trong từ điển nhưng không có tài liệu thỏa điều kiện hiện tại. Collate hoặc query kiểm tra có thể giúp xử lý.

Nếu chất lượng không tốt, hãy kiểm tra analyzer và dữ liệu trước khi tăng giới hạn candidate. Tăng max_edits hoặc giảm confidence có thể làm số lượng đề xuất tăng nhưng đồng thời tăng gợi ý sai.

## 23. Chi phí và giới hạn vận hành

Term và phrase suggester tạo thêm công việc trong search request. Chi phí phụ thuộc độ dài văn bản, số token, số candidate, số shard, analyzer và cấu hình.

Một số nguyên tắc:

- Giới hạn độ dài văn bản đầu vào.
- Giới hạn số option bằng size.
- Đặt min_word_length phù hợp để bỏ qua token quá ngắn.
- Giới hạn max_edits và max_errors.
- Tránh tạo quá nhiều direct_generator.
- Chỉ bật collate khi cần xác nhận candidate có tài liệu.
- Dùng debounce và rate limit ở endpoint.
- Theo dõi latency riêng của request suggestion.
- Không chạy suggester cho mọi truy vấn nếu không cần thiết.
- Đánh giá kích thước index khi thêm shingle field vì số term được lập chỉ mục tăng.

Phrase suggester có thể tốn tài nguyên hơn term suggester vì cần đánh giá chuỗi candidate theo mô hình n-gram. Dùng term suggester khi chỉ cần sửa từ riêng lẻ; chỉ dùng phrase suggester khi ngữ cảnh cả cụm thực sự mang lại lợi ích.

## 24. Lỗi thường gặp khi dùng suggester

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Term suggester không đề xuất từ đã gõ sai | Token có thể tồn tại trong từ điển hoặc suggest_mode là missing | Thử always/popular và kiểm tra term dictionary |
| Không có suggestion option | Không có candidate trong giới hạn distance hoặc token quá ngắn | Kiểm tra max_edits, prefix_length, min_word_length và dữ liệu |
| Term suggester trả đề xuất cho từng từ nhưng cụm vẫn sai | Term suggester không đánh giá ngữ cảnh toàn câu | Dùng phrase suggester |
| Phrase suggester không hoạt động tốt | Field không có shingle hoặc gram_size không phù hợp | Kiểm tra analyzer và mapping subfield |
| Phrase suggestion có nhiều lựa chọn kém | Candidate generation quá rộng hoặc confidence thấp | Giới hạn direct_generator và tinh chỉnh confidence |
| Suggestion không có tài liệu tương ứng | Suggester không tự áp dụng filter nghiệp vụ | Dùng collate hoặc query kiểm tra candidate |
| Response có hits nhưng không có suggest | Tên suggester, cấu trúc request hoặc field không đúng | Kiểm tra request và key suggest trong response |
| Response chỉ có suggest, không có hits | Search request đặt size 0 | Đây là hành vi mong muốn khi chỉ cần đề xuất |
| Java không đọc được suggestion | Đang đọc nhầm kiểu union hoặc key suggester | Kiểm tra isTerm(), isPhrase() và tên key |
| Highlight không hiển thị | Chưa cấu hình highlight hoặc đang đọc sai option | Kiểm tra highlight trong phrase request và response |
| Suggestion sai chữ hoa/thường | Analyzer/normalizer không thống nhất | Chuẩn hóa dữ liệu và query theo cùng quy tắc |
| Gợi ý tăng độ trễ | Quá nhiều candidate, token dài hoặc collate tốn kém | Giới hạn input, size và đo riêng latency |

## 25. Quy trình triển khai term và phrase suggester

Khi thêm tính năng gợi ý cho một trường tìm kiếm, có thể thực hiện theo trình tự:

1. **Xác định nhu cầu.** Cần sửa từng từ hay đề xuất cả cụm?
2. **Chọn trường.** Xác định text field và analyzer phù hợp.
3. **Chuẩn bị mapping.** Với phrase suggester, tạo shingle subfield và reindex dữ liệu nếu cần.
4. **Tạo request thử nghiệm.** Bắt đầu với term suggester và một vài tham số cơ bản.
5. **Thêm phrase suggester.** Chỉ khi cần đánh giá ngữ cảnh của cụm từ.
6. **Đọc response.** Phân biệt entry, option, score, freq, highlight và collate_match.
7. **Kiểm tra dữ liệu thật.** Dùng các truy vấn có lỗi chính tả thường gặp và tên riêng trong nghiệp vụ.
8. **Giới hạn chi phí.** Đặt size, max_edits, min_word_length và độ dài input.
9. **Tích hợp ứng dụng.** Chuyển suggestion thành DTO và hiển thị theo chính sách UX.
10. **Theo dõi chất lượng.** Đo tỷ lệ người dùng chọn đề xuất, tỷ lệ tìm kiếm thành công sau khi chọn và latency.

Term suggester phù hợp với việc đề xuất cách viết cho từng token; phrase suggester dùng shingle statistics để đánh giá cả cụm từ và có thể tạo lựa chọn tự nhiên hơn. Trong response, **suggest** được nhóm theo tên suggester, mỗi entry chứa văn bản đầu vào và các option đề xuất. Đọc đúng **text**, **offset**, **length**, **score**, **freq**, **highlighted** và **collate_match** giúp ứng dụng trình bày kết quả chính xác. Khi tích hợp với Spring Data Elasticsearch, dùng abstraction sẵn có nếu phiên bản hỗ trợ; nếu cần kiểm soát suggest request trực tiếp, có thể sử dụng Elasticsearch Java API Client đã được Spring cấu hình.
