# Stop word, stemming và đánh đổi về độ chính xác

Khi tìm kiếm văn bản, Elasticsearch không nhất thiết so sánh nguyên văn chuỗi người dùng nhập với chuỗi được lưu. Analyzer có thể chuẩn hóa văn bản, tách token, loại bỏ stop word và đưa các biến thể từ về dạng gốc gần đúng. Những bước này giúp người dùng tìm được tài liệu dù cách viết trong truy vấn khác một chút so với dữ liệu. Tuy nhiên, mỗi bước chuẩn hóa cũng có thể làm mất thông tin và khiến tài liệu không thực sự liên quan xuất hiện trong kết quả.

Hai kỹ thuật thường gặp là **stop word removal** và **stemming**. Stop word removal loại bỏ những từ được xem là ít đóng góp cho khả năng phân biệt tài liệu. Stemming đưa các biến thể hình thái của từ về một stem chung. Cả hai có thể cải thiện trải nghiệm tìm kiếm, nhưng phải được lựa chọn dựa trên ngôn ngữ, dữ liệu và mục đích truy vấn.

## 1. Analyzer xử lý văn bản ở đâu?

### 1.1. Pipeline phân tích văn bản

Analyzer là một pipeline xử lý chuỗi thành các token để Elasticsearch lập chỉ mục hoặc phân tích chuỗi truy vấn. Một custom analyzer thường có ba nhóm thành phần:

1. **Character filters** xử lý ký tự trước khi tách từ, ví dụ chuẩn hóa một số ký tự hoặc thay thế chuỗi.
2. **Tokenizer** chia chuỗi thành các token.
3. **Token filters** biến đổi, loại bỏ hoặc bổ sung thông tin cho token sau khi tách.

Stop filter và stemmer là token filter. Chúng hoạt động sau tokenizer, theo thứ tự được khai báo trong analyzer.

~~~mermaid
flowchart LR
    A[Input text] --> B[Character filters]
    B --> C[Tokenizer]
    C --> D[Lowercase]
    D --> E[Stop filter]
    E --> F[Stemmer]
    F --> G[Tokens for indexing or query]
~~~

Ví dụ, chuỗi:

~~~text
"The runners are running quickly"
~~~

có thể được xử lý theo thứ tự:

- Tokenizer tách thành các token như `The`, `runners`, `are`, `running`, `quickly`.
- Lowercase chuyển token thành chữ thường.
- Stop filter loại bỏ các từ nằm trong danh sách stop words, ví dụ `the` và `are`.
- Stemmer rút gọn các từ còn lại theo thuật toán stemming được chọn.

Kết quả minh họa có thể gần với:

~~~text
["runner", "run", "quickli"]
~~~

Đây là kết quả minh họa cho một cấu hình tiếng Anh cụ thể; token thực tế phụ thuộc tokenizer, stopword list và thuật toán stemming. Stemming không nhất thiết tạo ra một từ tiếng Anh hoàn chỉnh trong từ điển.

### 1.2. Phân tích khi index và khi search

Elasticsearch có thể phân tích văn bản ở hai thời điểm:

- **Index-time analysis**: xử lý nội dung field trước khi ghi các token vào inverted index.
- **Search-time analysis**: xử lý chuỗi truy vấn trước khi so khớp với token đã được lập chỉ mục.

Khi một field `text` dùng analyzer, analyzer đó thường được áp dụng lúc index. Khi search, Elasticsearch dùng `search_analyzer` nếu được khai báo; nếu không, search analyzer thường kế thừa analyzer của field.

Hai phía cần tạo ra các token tương thích. Nếu document được index với stemming nhưng query không được stem, một truy vấn chứa `running` có thể không khớp token `run` đã lưu. Ngược lại, nếu query được stem nhưng document vẫn lưu nguyên dạng, query token `run` cũng có thể không khớp token `running`.

Vì vậy, khi dùng stop filter hoặc stemmer, hãy thiết kế rõ analyzer ở cả hai thời điểm. Có thể dùng analyzer riêng cho search nếu có lý do cụ thể, nhưng cần kiểm tra rằng token do query tạo ra vẫn có thể khớp với token trong index.

## 2. Stop word là gì?

### 2.1. Khái niệm stop word

Stop word là những từ xuất hiện thường xuyên và thường ít giúp phân biệt tài liệu trong một số loại tìm kiếm. Trong tiếng Anh, các ví dụ phổ biến là:

~~~text
a, an, the, is, are, of, in, on, and
~~~

Trong một tập tài liệu tiếng Anh, từ `the` xuất hiện ở rất nhiều nơi. Nếu mục tiêu là tìm nội dung theo chủ đề, từ này thường đóng góp ít hơn các từ như `elasticsearch`, `index`, `mapping` hoặc `query`.

Stop word không phải một danh sách đúng cho mọi ứng dụng. Một từ có thể ít quan trọng trong tìm kiếm tổng quát nhưng lại rất quan trọng trong tên riêng, câu trích dẫn, nội dung pháp lý hoặc truy vấn chuyên ngành.

### 2.2. Stop filter hoạt động như thế nào?

Stop filter kiểm tra token với danh sách stop words và loại bỏ token trùng với danh sách đó. Elasticsearch cung cấp stop token filter và có thể dùng danh sách dựng sẵn hoặc danh sách do ứng dụng khai báo.

Ví dụ custom analyzer tiếng Anh:

~~~json
{
  "settings": {
    "analysis": {
      "filter": {
        "english_stop": {
          "type": "stop",
          "stopwords": "_english_"
        }
      },
      "analyzer": {
        "english_without_stop": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "english_stop"
          ]
        }
      }
    }
  }
}
~~~

Danh sách `_english_` là bộ stop words dựng sẵn cho tiếng Anh. Có thể thay bằng danh sách riêng:

~~~json
{
  "type": "stop",
  "stopwords": ["a", "an", "the", "and"]
}
~~~

Nếu không muốn loại bỏ stop word, có thể dùng `_none_` hoặc không đưa stop filter vào analyzer. Hãy xác nhận cú pháp và các tùy chọn bằng tài liệu đúng phiên bản Elasticsearch đang triển khai.

### 2.3. Lợi ích của stop word removal

Loại bỏ stop words có thể đem lại một số lợi ích:

- Giảm số token phổ biến trong inverted index.
- Giảm nhiễu từ các từ chức năng khi truy vấn có nhiều từ.
- Giúp truy vấn tập trung hơn vào các từ mang nội dung chính.
- Có thể giảm kích thước dữ liệu lập chỉ mục và chi phí xử lý trong một số workload.
- Hữu ích với hệ thống tìm kiếm mà người dùng thường nhập câu dài, có nhiều từ nối.

Tác động thực tế phụ thuộc dữ liệu và cấu hình. Elasticsearch đã có cơ chế tính điểm và tối ưu inverted index; không nên mặc định rằng loại bỏ stop words luôn giúp hệ thống nhanh hơn hoặc tiết kiệm đáng kể dung lượng. Hãy đo trên tập dữ liệu đại diện.

### 2.4. Rủi ro khi loại bỏ stop words

Stop word có thể mang ý nghĩa quan trọng trong một truy vấn. Ví dụ:

- `to be or not to be`: từ `not` làm thay đổi ý nghĩa câu.
- `without sugar`: từ `without` xác định điều kiện loại trừ.
- `state of the art`: cụm từ có thể mang nghĩa riêng.
- Tên sản phẩm, tên tổ chức hoặc tiêu đề có chứa các từ rất phổ biến.
- Nội dung pháp lý, y tế hoặc kỹ thuật, nơi một từ ngắn có thể thay đổi ý nghĩa.

Nếu loại bỏ từ phủ định như `not`, `no`, `without`, `không` hoặc `chưa`, hệ thống có thể trả về tài liệu mang nghĩa ngược với điều người dùng tìm kiếm.

Đừng lấy danh sách stop words mặc định làm chân lý. Hãy đọc danh sách, xem các truy vấn thật và giữ lại những từ có ý nghĩa nghiệp vụ.

### 2.5. Vị trí token và phrase query

Khi stop filter loại bỏ token, thông tin vị trí token có thể vẫn được giữ bằng position increments. Vì vậy, các từ còn lại không nhất thiết trở thành liền kề như thể từ bị loại bỏ chưa từng tồn tại.

Điều này có ảnh hưởng đến `match_phrase` và các truy vấn dựa trên vị trí từ. Ví dụ, truy vấn chứa cụm `state of the art` có thể được phân tích thành các token còn lại với khoảng cách vị trí tương ứng. Kết quả phrase matching phụ thuộc analyzer ở cả lúc index và search.

Nếu ứng dụng cần tìm cụm từ chính xác, hãy kiểm tra kết quả `_analyze` và thử truy vấn `match_phrase` trên dữ liệu đại diện. Với một số ứng dụng, có thể cần `search_quote_analyzer` riêng để giữ lại các từ chức năng khi người dùng tìm cụm từ đặt trong dấu ngoặc kép.

## 3. Stemming là gì?

### 3.1. Khái niệm stemming

Stemming là kỹ thuật rút gọn các biến thể của từ về một dạng stem chung, thường bằng cách loại bỏ hoặc biến đổi một số hậu tố. Mục tiêu là giúp các dạng từ liên quan có thể được tìm thấy cùng nhau.

Ví dụ trong tiếng Anh:

| Từ ban đầu | Stem minh họa |
|---|---|
| `connect` | `connect` |
| `connected` | `connect` |
| `connecting` | `connect` |
| `connections` | `connect` |
| `running` | `run` |
| `runs` | `run` |

Các kết quả cụ thể phụ thuộc thuật toán. Stem không nhất thiết là một từ hoàn chỉnh hoặc là lemma đúng theo ngữ pháp.

Khi document có từ `connected` nhưng người dùng tìm `connecting`, stemming có thể đưa cả hai về cùng một token, giúp truy vấn tìm thấy tài liệu mà không cần liệt kê từng biến thể từ.

### 3.2. Stemming khác lemmatization

Hai kỹ thuật thường bị nhầm lẫn:

| Tiêu chí | Stemming | Lemmatization |
|---|---|---|
| Cách xử lý | Áp dụng quy tắc cắt/biến đổi từ | Xác định dạng từ điển dựa trên ngôn ngữ và ngữ cảnh |
| Đầu ra | Stem, có thể không phải từ hoàn chỉnh | Lemma thường là từ hợp lệ trong từ điển |
| Ngữ cảnh ngữ pháp | Thường không phân tích sâu | Có thể cần từ loại và ngữ cảnh |
| Chi phí | Thường nhẹ và đơn giản hơn | Có thể cần từ điển/mô hình ngôn ngữ |
| Ví dụ | `studies` có thể thành `studi` với một số thuật toán | `studies` có thể về `study` |

Stemming phù hợp khi cần chuẩn hóa hình thái nhanh và chấp nhận một mức độ xấp xỉ. Lemmatization phù hợp hơn khi cần giữ tính chính xác ngôn ngữ, nhưng thường đòi hỏi công cụ chuyên biệt và chi phí xử lý lớn hơn.

Không nên kỳ vọng stemmer của Elasticsearch hiểu đầy đủ ngữ pháp, từ loại hoặc ngữ cảnh câu.

### 3.3. Stemmer token filter trong Elasticsearch

Elasticsearch cung cấp stemmer token filter. Ví dụ:

~~~json
{
  "settings": {
    "analysis": {
      "filter": {
        "english_stemmer": {
          "type": "stemmer",
          "language": "english"
        }
      },
      "analyzer": {
        "english_stemmed": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "english_stemmer"
          ]
        }
      }
    }
  }
}
~~~

Một số thuật toán hoặc biến thể stemming có thể được chọn thông qua cấu hình language/filter tương ứng, chẳng hạn Porter, Porter2, KStem hoặc các bộ stemmer nhẹ theo ngôn ngữ. Danh sách lựa chọn và tên cấu hình phụ thuộc phiên bản Elasticsearch/Lucene; cần đối chiếu tài liệu chính thức trước khi dùng.

Các lựa chọn thường thể hiện mức đánh đổi:

- Stemmer mạnh hơn có thể gộp nhiều biến thể từ, tăng khả năng tìm thấy nội dung liên quan.
- Stemmer nhẹ hơn thường giữ lại nhiều khác biệt hơn, giảm một số trường hợp gộp nhầm.
- Stemmer dựa trên từ điển có thể xử lý một số dạng từ tốt hơn quy tắc cắt hậu tố, nhưng vẫn có giới hạn theo ngôn ngữ và vốn từ.

### 3.4. Over-stemming và under-stemming

**Over-stemming** xảy ra khi thuật toán gộp các từ có ý nghĩa khác nhau vào cùng một stem. Điều này có thể làm kết quả chứa tài liệu không liên quan.

**Under-stemming** xảy ra khi các biến thể thực sự liên quan không được đưa về cùng stem. Người dùng vẫn có thể bỏ lỡ một số tài liệu dù hai từ có quan hệ hình thái.

Ví dụ minh họa:

- Nếu một stemmer gộp hai từ khác nghĩa vào cùng token, truy vấn có thể trả về cả hai nhóm tài liệu.
- Nếu stemmer không nhận ra một dạng biến thể, truy vấn theo dạng khác có thể không tìm thấy tài liệu mong muốn.

Không có thuật toán stemming nào phù hợp cho mọi ngôn ngữ và mọi tập dữ liệu. Hãy thử trên thuật ngữ chuyên ngành, tên sản phẩm, tên riêng, từ viết tắt và các dạng từ phổ biến của người dùng.

## 4. Kết hợp stop word và stemming

### 4.1. Thứ tự token filter

Stop filter và stemmer có thể cùng nằm trong một analyzer. Thứ tự được khai báo ảnh hưởng đến quá trình xử lý.

Một thứ tự thường dùng cho tiếng Anh là:

1. Lowercase để chuẩn hóa chữ hoa/thường.
2. Stop filter để loại bỏ từ chức năng.
3. Stemmer để rút gọn các token còn lại.

Ví dụ:

~~~json
{
  "settings": {
    "analysis": {
      "filter": {
        "english_stop": {
          "type": "stop",
          "stopwords": "_english_"
        },
        "english_stemmer": {
          "type": "stemmer",
          "language": "english"
        }
      },
      "analyzer": {
        "english_catalog": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "english_stop",
            "english_stemmer"
          ]
        }
      }
    }
  }
}
~~~

Stop filter thường được đặt trước stemmer vì danh sách stop words thường được khai báo ở dạng từ gốc dễ đọc. Nếu đặt stemming trước, token có thể bị biến đổi trước khi so với danh sách stop words, khiến danh sách không loại bỏ được token như mong muốn.

Khi tự xây dựng analyzer, hãy kiểm tra thứ tự filter bằng `_analyze`, thay vì chỉ nhìn cấu hình và giả định kết quả.

### 4.2. Gắn analyzer vào field

Có thể dùng analyzer ở index-time và search-time:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "english_catalog",
        "search_analyzer": "english_catalog",
        "fields": {
          "raw": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

Trong ví dụ:

- `title` được phân tích bằng `english_catalog` để tìm kiếm toàn văn.
- `title.raw` giữ giá trị keyword để so khớp nguyên giá trị hoặc sort/aggregation.
- `search_analyzer` được chỉ định tường minh để thể hiện quy tắc phân tích truy vấn.

Multi-field giúp ứng dụng có nhiều cách tìm cùng một dữ liệu. Người dùng có thể dùng full-text search trên `title`, trong khi thao tác exact match dùng `title.raw`.

Lưu ý rằng subfield `keyword` không tự động áp dụng stemming. Đây là điều hữu ích khi cần giữ lại giá trị nguyên bản để đối chiếu chính xác.

### 4.3. Tách field stemmed và unstemmed

Trong một số hệ thống, ứng dụng cần cả khả năng tìm rộng và khả năng tìm chính xác hơn. Có thể tạo thêm subfield `unstemmed` với analyzer chỉ lowercase, hoặc dùng multi-field theo chiến lược phù hợp.

Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "analyzer": "english_catalog",
        "fields": {
          "unstemmed": {
            "type": "text",
            "analyzer": "standard"
          },
          "raw": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

Khi query, ứng dụng có thể kết hợp nhiều field và boost field phù hợp. Ví dụ, kết quả khớp chính xác trên field nguyên bản có thể được ưu tiên hơn kết quả chỉ khớp sau stemming. Cách boost phải được thử nghiệm với bộ truy vấn thực tế; không có một hệ số cố định đúng cho mọi hệ thống.

## 5. Precision và recall: đánh đổi về độ chính xác

### 5.1. Precision là gì?

Precision (độ chính xác của kết quả trả về) cho biết trong số tài liệu hệ thống đã trả về, có bao nhiêu tài liệu thực sự liên quan:

\[
Precision = \frac{\text{Số tài liệu liên quan được trả về}}{\text{Tổng số tài liệu được trả về}}
\]

Nếu hệ thống trả 10 tài liệu và chỉ có 8 tài liệu liên quan, precision là 0,8 hay 80%.

Precision cao nghĩa là kết quả trả về ít nhiễu hơn. Người dùng ít phải mở những tài liệu không đúng nhu cầu.

### 5.2. Recall là gì?

Recall (độ bao phủ) cho biết trong số tất cả tài liệu thực sự liên quan trong tập dữ liệu, hệ thống tìm được bao nhiêu:

\[
Recall = \frac{\text{Số tài liệu liên quan được trả về}}{\text{Tổng số tài liệu liên quan tồn tại}}
\]

Nếu tập dữ liệu có 20 tài liệu liên quan và hệ thống tìm được 15 tài liệu, recall là 0,75 hay 75%.

Recall cao nghĩa là hệ thống bỏ sót ít tài liệu liên quan hơn. Điều này quan trọng khi người dùng cần tìm đầy đủ, chẳng hạn tra cứu hồ sơ, tài liệu pháp lý hoặc dữ liệu hỗ trợ kỹ thuật.

### 5.3. Vì sao stop word và stemming ảnh hưởng đến precision/recall?

Khi analyzer loại bỏ từ hoặc gộp nhiều biến thể thành cùng một stem, phạm vi token có thể khớp thay đổi.

| Điều chỉnh | Tác động có thể có | Rủi ro |
|---|---|---|
| Loại bỏ stop words phổ biến | Giảm nhiễu từ các từ ít phân biệt | Mất ý nghĩa nếu từ bị loại bỏ quan trọng |
| Giữ lại stop words | Bảo toàn ngữ nghĩa câu và cụm từ | Tăng số token phổ biến, có thể làm query kém tập trung |
| Stemming mạnh | Gộp nhiều biến thể, thường tăng khả năng tìm thấy | Gộp nhầm từ khác nghĩa, giảm precision |
| Stemming nhẹ | Giữ lại nhiều khác biệt, có thể giảm kết quả nhiễu | Có thể bỏ sót một số biến thể, giảm recall |
| Không stemming | Bảo toàn dạng từ trong index | Người dùng có thể phải nhập đúng dạng từ đã lưu |

Đây là xu hướng có thể gặp, không phải quy luật tuyệt đối. Tác động thực tế phụ thuộc analyzer, query, phân bố dữ liệu và cách đánh giá mức độ liên quan.

Ví dụ, người dùng tìm `connect` có thể muốn thấy tài liệu chứa `connected` và `connecting`. Stemming giúp tăng recall. Nhưng nếu stemmer gộp thêm những thuật ngữ không liên quan, precision có thể giảm.

Tương tự, bỏ từ `without` khỏi truy vấn `products without sugar` có thể khiến kết quả chứa sản phẩm có đường. Trong trường hợp này, loại bỏ stop word làm mất một điều kiện quan trọng và chất lượng tìm kiếm giảm rõ rệt.

### 5.4. F1 score và các chỉ số khác

Precision và recall thường có xu hướng đánh đổi. Có thể dùng F1 score để xem xét cả hai:

\[
F1 = 2 \times \frac{Precision \times Recall}{Precision + Recall}
\]

F1 là trung bình điều hòa của precision và recall. Nó thấp khi một trong hai chỉ số thấp.

Trong tìm kiếm thực tế, người dùng thường quan tâm kết quả ở đầu danh sách. Vì vậy, có thể đánh giá thêm:

- **Precision@k**: tỷ lệ tài liệu liên quan trong k kết quả đầu tiên.
- **Recall@k**: tỷ lệ tài liệu liên quan được tìm thấy trong k kết quả đầu tiên.
- **MRR**: vị trí của kết quả liên quan đầu tiên qua nhiều truy vấn.
- **NDCG**: chất lượng xếp hạng khi mỗi kết quả có mức độ liên quan khác nhau.

Không nên chỉ tối ưu F1 mà bỏ qua thứ tự xếp hạng. Một hệ thống có recall tốt nhưng tài liệu quan trọng nằm rất sâu vẫn có thể tạo trải nghiệm kém.

## 6. Chọn stop words và stemmer theo mục đích

### 6.1. Không phải field nào cũng cần stemming

Các field thường có mục đích khác nhau:

| Loại field | Xử lý thường phù hợp |
|---|---|
| Nội dung bài viết, mô tả dài | Có thể dùng stop filter và stemming theo ngôn ngữ |
| Tên sản phẩm | Cần thử nghiệm; giữ thêm field unstemmed hoặc keyword khi cần |
| Mã sản phẩm, SKU | Thường dùng keyword hoặc normalizer phù hợp, không stemming |
| Email, username | Thường cần quy tắc chuẩn hóa riêng, không dùng stemming |
| Trạng thái, loại danh mục | Thường dùng keyword |
| Tên riêng, thương hiệu | Cần thận trọng với stop words và stemming |
| Nội dung pháp lý hoặc câu trích dẫn | Cần bảo toàn từ phủ định và cụm từ có ý nghĩa |

Ví dụ, stemmer hữu ích với mô tả dài có nhiều biến thể hình thái. Nhưng stem một mã SKU hoặc tên thương hiệu có thể làm hỏng giá trị cần so khớp.

### 6.2. Giữ ngoại lệ không được stemming

Một số thuật ngữ cần giữ nguyên, ví dụ tên thương hiệu, từ viết tắt hoặc thuật ngữ chuyên ngành. Có thể dùng token filter như `keyword_marker` để đánh dấu token không được stem, hoặc `stemmer_override` để quy định một số chuyển đổi cụ thể.

Ví dụ khái niệm:

~~~json
{
  "settings": {
    "analysis": {
      "filter": {
        "protected_terms": {
          "type": "keyword_marker",
          "keywords": ["elasticsearch", "spring"]
        },
        "english_stemmer": {
          "type": "stemmer",
          "language": "english"
        }
      },
      "analyzer": {
        "english_with_protected_terms": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "protected_terms",
            "english_stemmer"
          ]
        }
      }
    }
  }
}
~~~

Vì lowercase chạy trước `keyword_marker`, danh sách từ được bảo vệ cũng dùng chữ thường. Token được đánh dấu keyword sẽ được giữ nguyên qua các filter stemming hỗ trợ cơ chế này.

`stemmer_override` cho phép khai báo các quy tắc stem cụ thể, ví dụ sửa kết quả của một từ ngoại lệ. Những filter này phải được đặt đúng thứ tự và cần kiểm tra trên phiên bản Elasticsearch đang sử dụng.

### 6.3. Ngôn ngữ là yếu tố quyết định

Stop word list và stemmer phụ thuộc ngôn ngữ. Không dùng danh sách tiếng Anh cho văn bản tiếng Việt hoặc ngôn ngữ khác. Cũng không thể giả định một stemmer tiếng Anh sẽ xử lý tốt tên riêng, từ ghép hoặc thuật ngữ đa ngôn ngữ.

Với dữ liệu nhiều ngôn ngữ, nên xác định ngôn ngữ của nội dung hoặc tách field/index theo ngôn ngữ khi phù hợp. Mỗi nhóm dữ liệu có thể cần analyzer riêng.

Nếu một field trộn nhiều ngôn ngữ, một analyzer đơn lẻ thường không xử lý tối ưu mọi trường hợp. Hãy xem xét yêu cầu thực tế, ngôn ngữ phổ biến và cách người dùng nhập truy vấn.

### 6.4. Lưu ý riêng với tiếng Việt

Tiếng Việt có dấu thanh và cấu trúc từ gồm nhiều âm tiết được viết cách nhau bằng khoảng trắng. Ranh giới giữa âm tiết và từ có thể khác nhau: một từ có thể gồm nhiều âm tiết, trong khi tokenizer tách theo khoảng trắng chưa chắc tạo ra token đúng với đơn vị từ vựng.

Vì vậy:

- Không áp dụng stop word list tiếng Anh hoặc stemmer tiếng Anh cho nội dung tiếng Việt.
- Không mặc định `standard` tokenizer đã thực hiện word segmentation tiếng Việt theo nghĩa ngôn ngữ học.
- Kiểm tra tokenizer/analyzer và plugin thực tế có trong phiên bản Elasticsearch đang chạy.
- Nếu cần tìm kiếm tiếng Việt chất lượng cao, hãy đánh giá giải pháp tách từ phù hợp, từ điển tên riêng/thuật ngữ và cách xử lý dấu.
- Cẩn thận khi dùng ASCII folding để bỏ dấu: hai từ khác nghĩa có thể trở nên giống nhau sau chuẩn hóa.
- Stop word tiếng Việt cần được xây dựng từ dữ liệu và truy vấn thật; không loại bỏ các từ phủ định như `không`, `chưa`, `chẳng` một cách máy móc.

Ví dụ, các từ `học`, `học tập`, `học sinh` có quan hệ ngữ nghĩa nhưng không thể giải quyết đầy đủ chỉ bằng cách cắt hậu tố. Một hệ thống tiếng Việt có thể cần word segmentation, synonym và analyzer phù hợp hơn là một stemmer đơn giản.

## 7. Kiểm tra analyzer bằng _analyze

### 7.1. Vì sao cần dùng Analyze API?

Trước khi đánh giá search result, hãy kiểm tra analyzer tạo ra token gì. Analyze API cho biết chuỗi đầu vào được tách và biến đổi như thế nào. Điều này giúp phát hiện:

- Tokenizer tách từ không như mong đợi.
- Stop word quan trọng bị loại bỏ.
- Stemmer biến đổi từ quá mạnh hoặc không đủ mạnh.
- Thứ tự token filter không phù hợp.
- Chuẩn hóa chữ hoa/thường hoặc ký tự gây mất thông tin.

Ví dụ:

~~~http
POST /articles/_analyze
Content-Type: application/json

{
  "analyzer": "english_catalog",
  "text": "The runners are running quickly"
}
~~~

Để xem thêm chi tiết từng bước, có thể dùng `explain`:

~~~http
POST /articles/_analyze
Content-Type: application/json

{
  "analyzer": "english_catalog",
  "text": "The runners are running quickly",
  "explain": true
}
~~~

Analyze API là công cụ kiểm tra token, không chứng minh kết quả tìm kiếm cuối cùng đã đúng. Search còn phụ thuộc document được index, mapping, query, scoring và filter.

### 7.2. Kiểm tra cả analyzer lúc index và search

Nếu field khai báo `analyzer` và `search_analyzer` khác nhau, hãy kiểm tra cả hai. Token của query cần tương thích với token trong index.

Ví dụ, một field có thể được index với stemming nhưng search analyzer lại không stemming. Khi đó, dạng từ truy vấn có thể không khớp với stem đã lưu.

Không chỉ kiểm tra analyzer bằng chuỗi đơn. Hãy thử:

- Từ ở dạng số ít và số nhiều.
- Động từ ở nhiều thì.
- Từ có tiền tố/hậu tố.
- Từ phủ định.
- Tên riêng, thương hiệu và thuật ngữ.
- Câu có stop words ở giữa.
- Truy vấn phrase có dấu ngoặc kép.
- Từ viết tắt và ký hiệu chuyên ngành.

## 8. Đánh giá chất lượng bằng bộ truy vấn thực tế

### 8.1. Xây dựng tập đánh giá

Hãy tạo một tập query đại diện cho cách người dùng thực sự tìm kiếm. Mỗi query cần có danh sách document liên quan được xác định trước hoặc nhãn relevance do người đánh giá gán.

Ví dụ bảng đánh giá:

| Query | Document | Relevance |
|---|---|---:|
| `running shoes` | Tài liệu về giày chạy bộ | 3 |
| `running shoes` | Tài liệu về giày đi bộ | 2 |
| `running shoes` | Tài liệu về máy chạy bộ | 1 |
| `running shoes` | Tài liệu không liên quan | 0 |

Có thể dùng thang điểm 0–3:

- 0: không liên quan.
- 1: liên quan ít.
- 2: liên quan khá rõ.
- 3: rất phù hợp với nhu cầu.

Nhãn cần nhất quán giữa người đánh giá. Nếu hệ thống chỉ có nhãn có/không, có thể dùng precision và recall; nếu có nhiều mức relevance, dùng thêm NDCG.

### 8.2. So sánh các cấu hình

Thử ít nhất các cấu hình sau trên cùng một tập query:

1. Analyzer cơ bản không stop filter, không stemming.
2. Có stop filter, không stemming.
3. Có stemming, không stop filter.
4. Có cả stop filter và stemming.
5. Stemmer nhẹ hoặc mạnh khác nhau nếu ngôn ngữ hỗ trợ.

Giữ nguyên tập document, query và cách tính điểm giữa các lần thử. Chỉ thay đổi analyzer để biết kết quả thay đổi do yếu tố nào.

### 8.3. Đo precision và recall

Giả sử với một query, người đánh giá xác định có 10 tài liệu liên quan. Cấu hình A trả về 8 tài liệu, trong đó 7 tài liệu liên quan:

- Precision = 7/8 = 87,5%.
- Recall = 7/10 = 70%.

Cấu hình B trả về 12 tài liệu, trong đó 9 tài liệu liên quan:

- Precision = 9/12 = 75%.
- Recall = 9/10 = 90%.

Cấu hình B tìm được nhiều tài liệu liên quan hơn, nhưng cũng đưa thêm kết quả nhiễu. Cấu hình A có kết quả gọn hơn, nhưng bỏ sót nhiều tài liệu hơn.

Điều nào tốt hơn phụ thuộc sản phẩm:

- Tra cứu hồ sơ hoặc tài liệu cần đầy đủ có thể ưu tiên recall.
- Tìm kiếm thương mại điện tử có thể ưu tiên precision ở nhóm kết quả đầu.
- Tìm kiếm hỗ trợ kỹ thuật có thể cần cân bằng hai chỉ số và xếp hạng tốt.
- Hệ thống tìm kiếm nội bộ có thể cho phép người dùng mở rộng truy vấn khi kết quả quá ít.

### 8.4. Không đánh giá trên một query duy nhất

Một analyzer có thể hoạt động tốt với một số từ nhưng thất bại với tên riêng, thuật ngữ chuyên ngành hoặc câu phủ định. Hãy tổng hợp chỉ số trên nhiều query và xem riêng các nhóm query quan trọng.

Ngoài chỉ số tổng hợp, hãy đọc thủ công các false positives (kết quả không liên quan được trả về) và false negatives (tài liệu liên quan bị bỏ sót). Những trường hợp này thường cho biết nên sửa stop word list, stemmer, tokenizer, synonym hay cách boost field.

## 9. Những sai lầm thường gặp

**Dùng stop word list mặc định mà không kiểm tra.** Danh sách mặc định có thể loại bỏ từ mang ý nghĩa trong lĩnh vực của ứng dụng. Hãy xem các từ bị loại và thử truy vấn quan trọng.

**Loại bỏ từ phủ định.** Bỏ `not`, `without`, `không` hoặc `chưa` có thể đảo nghĩa truy vấn. Hãy kiểm tra riêng nhóm từ phủ định.

**Dùng stemming cho mọi field.** Mã sản phẩm, username, email, trạng thái và tên riêng thường cần quy tắc chính xác hơn. Chỉ stem field có nội dung ngôn ngữ tự nhiên khi có lợi ích được đo lường.

**Không đồng bộ index analyzer và search analyzer.** Query có thể tạo token khác với token đã lưu, dẫn đến bỏ sót kết quả.

**Cho rằng stem luôn là từ trong từ điển.** Stemmer là thuật toán chuẩn hóa, không phải bộ phân tích ngữ pháp đầy đủ.

**Không phân biệt stemming và lemmatization.** Hai kỹ thuật có mục tiêu và mức độ ngôn ngữ học khác nhau.

**Không kiểm tra phrase query.** Stop filter có thể ảnh hưởng vị trí token và cách khớp cụm từ.

**Chỉ đo tổng số kết quả.** Nhiều kết quả không đồng nghĩa tìm kiếm tốt. Cần xem relevance, precision, recall và thứ tự xếp hạng.

**Sửa analyzer trên index đang có mà không tính đến dữ liệu cũ.** Thay đổi analyzer hoặc mapping có thể cần tạo index mới và reindex để toàn bộ document được phân tích lại theo quy tắc mới.

## 10. Quy trình chọn và tinh chỉnh

Khi thiết kế analyzer cho một field văn bản, có thể đi theo trình tự:

1. Xác định ngôn ngữ và loại dữ liệu của field.
2. Xác định người dùng cần tìm chính xác hay tìm theo nội dung.
3. Chọn tokenizer phù hợp với ngôn ngữ.
4. Quyết định có cần lowercase, accent normalization hoặc các chuẩn hóa khác không.
5. Xem xét stop words, đặc biệt là từ phủ định và từ chuyên ngành.
6. Chọn stemmer phù hợp hoặc không dùng stemming nếu lợi ích không rõ.
7. Khai báo analyzer lúc index và search một cách nhất quán.
8. Dùng `_analyze` để kiểm tra token.
9. Chạy tập truy vấn có nhãn relevance để đo precision, recall và chất lượng xếp hạng.
10. Điều chỉnh từng thành phần, đo lại và lưu cấu hình đã chọn.

Khi thay đổi analyzer cho field đã có dữ liệu, cần xem xét khả năng phải tạo index mới và reindex. Elasticsearch không tự phân tích lại toàn bộ dữ liệu cũ chỉ vì ứng dụng đã thay đổi định nghĩa analyzer.

## 11. Những điểm cần ghi nhớ

Stop word removal giúp loại bỏ các từ phổ biến nhưng có thể làm mất thông tin quan trọng. Stemming giúp gộp các biến thể hình thái nhưng có thể gộp nhầm những từ khác nghĩa hoặc bỏ lỡ các dạng liên quan. Cả hai đều là quyết định về chất lượng tìm kiếm, không chỉ là tùy chọn tối ưu hiệu năng.

Hãy lựa chọn dựa trên ngôn ngữ, loại field, nhu cầu người dùng và kết quả đo lường. Dùng `_analyze` để hiểu token, kiểm tra phrase query và xây dựng bộ truy vấn có nhãn relevance để quan sát tác động lên precision, recall và thứ tự xếp hạng. Khi có dữ liệu thực nghiệm, bạn mới có cơ sở quyết định nên loại bỏ stop words nào, dùng stemmer nào và field nào cần giữ nguyên dạng gốc.
