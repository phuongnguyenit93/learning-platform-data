# min_score, rescore và điều kiện sử dụng

Elasticsearch xếp hạng tài liệu bằng **relevance score**, thường được biểu diễn qua trường **_score**. Score cho biết tài liệu phù hợp với truy vấn đến mức nào theo mô hình tính điểm của Elasticsearch. Khi xây dựng tìm kiếm, đôi khi cần loại các kết quả có score quá thấp hoặc cải thiện thứ tự của nhóm kết quả đứng đầu. Hai tính năng thường được dùng cho mục đích này là **min_score** và **rescore**.

Hai tính năng có vai trò khác nhau:

- **min_score** đặt ngưỡng điểm tối thiểu. Tài liệu có score thấp hơn ngưỡng sẽ không được trả về trong danh sách hit.
- **rescore** chạy một bước tính điểm thứ hai trên nhóm tài liệu đứng đầu của truy vấn ban đầu, sau đó sắp xếp lại nhóm này dựa trên điểm mới.

Cả hai là tùy chọn ở cấp search request, không phải các query clause như **match**, **term** hay **range**. Chọn đúng tính năng giúp kết quả tìm kiếm phù hợp hơn mà vẫn kiểm soát được chi phí thực thi.

Bài này sử dụng index **products**, với các trường **name**, **description**, **category**, **status** và **price**. Ví dụ tập trung vào tìm kiếm tên sản phẩm, lọc dữ liệu và cải thiện thứ tự kết quả.

## 1. Relevance score trong Elasticsearch

Khi thực hiện truy vấn có tính điểm, Elasticsearch tính **_score** cho từng tài liệu phù hợp. Score thường dựa trên nội dung truy vấn, tần suất term, độ hiếm của term, độ dài trường và các yếu tố liên quan đến mô hình similarity.

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mechanical keyboard"
    }
  }
}
~~~

Một phần response có thể có dạng:

~~~json
{
  "hits": {
    "hits": [
      {
        "_id": "p-1001",
        "_score": 5.8,
        "_source": {
          "name": "Wireless Mechanical Keyboard"
        }
      },
      {
        "_id": "p-1002",
        "_score": 2.1,
        "_source": {
          "name": "Wireless Mouse"
        }
      }
    ]
  }
}
~~~

Tài liệu đầu có score cao hơn vì mức độ phù hợp với truy vấn có thể cao hơn. Các con số trong ví dụ chỉ để minh họa; score thực tế phụ thuộc mapping, analyzer, dữ liệu, similarity và cấu trúc truy vấn.

**_score không phải xác suất.** Score 5.8 không có nghĩa tài liệu đúng 58%, và không có một thang điểm chung bảo đảm có thể so sánh giữa các truy vấn khác nhau. Không nên lấy một ngưỡng score từ truy vấn này rồi áp dụng máy móc cho mọi truy vấn khác.

Khi query chỉ dùng điều kiện trong **bool.filter**, mục tiêu là lọc chứ không xếp hạng. Các filter clause không đóng góp vào score theo cách của query context. Nếu cần dùng min_score hoặc rescore, phải có phần truy vấn tạo score phù hợp.

## 2. min_score là gì?

**min_score** là tùy chọn của search request, dùng để loại các hit có score thấp hơn ngưỡng được chỉ định.

Ví dụ chỉ trả về tài liệu có score từ 2.0 trở lên:

~~~http
POST /products/_search
{
  "min_score": 2.0,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Trong ví dụ:

- Elasticsearch thực hiện truy vấn match trên trường name.
- Các tài liệu được đánh giá score theo truy vấn.
- Tài liệu có score thấp hơn 2.0 bị loại khỏi tập hit trả về.
- Tài liệu có score bằng hoặc lớn hơn ngưỡng có thể được trả về nếu đáp ứng các điều kiện khác.

**min_score nằm ở cấp search request**, cùng cấp với **query**, **from**, **size**, **sort** và **aggs**. Không đặt nó bên trong đối tượng match hoặc bool.

Ví dụ sai về cấu trúc:

~~~json
{
  "query": {
    "bool": {
      "min_score": 2.0,
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ]
    }
  }
}
~~~

Ví dụ đúng:

~~~json
{
  "min_score": 2.0,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ]
    }
  }
}
~~~

### min_score khác filter như thế nào?

Filter thường kiểm tra thuộc tính dữ liệu như category, status, giá hoặc thời gian. min_score kiểm tra điểm liên quan được tính từ truy vấn.

Ví dụ lọc sản phẩm đang hoạt động, thuộc danh mục accessories, có tên phù hợp và score tối thiểu:

~~~http
POST /products/_search
{
  "min_score": 1.5,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "range": {
            "price": {
              "gte": 20,
              "lte": 200
            }
          }
        }
      ]
    }
  }
}
~~~

Trong truy vấn này:

- **must** tạo phần tìm kiếm có tính điểm.
- **filter** loại sản phẩm không đúng trạng thái, danh mục hoặc khoảng giá.
- **min_score** loại các hit có điểm liên quan dưới ngưỡng.

Nếu chỉ cần lọc sản phẩm theo status hoặc price, hãy dùng filter. Không cần đặt min_score để thay thế một điều kiện nghiệp vụ có thể biểu diễn bằng term hoặc range.

## 3. Khi nào nên dùng min_score?

min_score có ích khi ứng dụng muốn loại những kết quả rất ít liên quan sau khi đã thực hiện tìm kiếm có tính điểm.

Một số trường hợp:

- Tìm kiếm sản phẩm theo từ khóa, chỉ hiển thị kết quả đạt mức liên quan tối thiểu.
- Tìm kiếm bài viết, tài liệu hoặc câu hỏi, loại các kết quả khớp yếu.
- Kết hợp nhiều từ khóa, yêu cầu kết quả có mức phù hợp đủ cao.
- Giảm nhiễu trên trang kết quả khi truy vấn rộng và có nhiều hit liên quan thấp.

Ví dụ, người dùng tìm **"mechanical keyboard"**. Truy vấn có thể trả về cả tài liệu chứa riêng từ mechanical hoặc keyboard. Nếu ứng dụng chỉ muốn hiển thị các kết quả đạt ngưỡng score, min_score có thể giúp lọc các hit yếu.

Tuy nhiên, min_score không hiểu ý nghĩa nghiệp vụ. Nó chỉ so sánh số điểm. Một sản phẩm quan trọng với nghiệp vụ có thể có score thấp do cách analyzer, dữ liệu hoặc query được thiết kế. Vì vậy, cần đánh giá trên tập truy vấn thực tế trước khi đưa ngưỡng vào production.

### Những trường hợp không nên dùng min_score

Không nên dùng min_score khi:

- Truy vấn chỉ có filter và không có phần scoring có ý nghĩa.
- Điều kiện có thể diễn đạt chính xác bằng term, range hoặc exists.
- Cần bảo đảm một trường có giá trị cụ thể.
- Muốn giới hạn số lượng kết quả; hãy dùng size.
- Muốn sắp xếp theo giá hoặc ngày; hãy dùng sort.
- Muốn loại tài liệu theo quy tắc nghiệp vụ; hãy dùng query/filter tương ứng.

Một ngưỡng score tùy tiện có thể làm mất các kết quả hợp lệ. Nếu score của truy vấn thay đổi theo nội dung hoặc corpus, cùng một tài liệu có thể vượt ngưỡng ở truy vấn này nhưng không vượt ở truy vấn khác.

## 4. Chi phí và giới hạn của min_score

min_score cần có score để so sánh. Vì vậy, Elasticsearch phải thực hiện phần tính điểm cho các tài liệu phù hợp trước khi quyết định giữ hay loại theo ngưỡng. Trên tập dữ liệu lớn, việc dùng min_score có thể làm tăng chi phí so với một truy vấn filter đơn giản.

Các điểm cần cân nhắc:

- min_score không thay thế filter context.
- Query có nhiều tài liệu phù hợp vẫn cần tính score để so sánh với ngưỡng.
- Ngưỡng score phụ thuộc truy vấn và dữ liệu.
- Thay analyzer, similarity, boosts hoặc cấu trúc query có thể làm phân bố score thay đổi.
- Khi kết hợp với rescore, cần kiểm tra hành vi thực tế của phiên bản Elasticsearch đang dùng và đánh giá ngưỡng trên score cuối cùng.
- Không nên đặt min_score quá cao chỉ để giảm số hit mà không kiểm tra recall.

**Recall** là khả năng giữ lại các tài liệu thực sự liên quan. Nếu ngưỡng quá cao, các tài liệu phù hợp có thể bị loại. **Precision** là tỷ lệ kết quả được trả về thực sự liên quan. Tăng min_score có thể cải thiện precision trong một số tập dữ liệu, nhưng thường có nguy cơ làm giảm recall.

Cần đánh giá cả hai chỉ số bằng bộ truy vấn và nhãn relevance đại diện cho người dùng thật, thay vì chọn ngưỡng theo một vài ví dụ.

## 5. rescore là gì?

**Rescore** là bước tính điểm lại cho một nhóm tài liệu đứng đầu sau truy vấn ban đầu. Ý tưởng là dùng một query nhanh, rộng để tìm các ứng viên, sau đó dùng một query chính xác hoặc tốn kém hơn để cải thiện thứ hạng của nhóm ứng viên đó.

Ví dụ:

- Truy vấn đầu tiên tìm các sản phẩm có các term **wireless** hoặc **keyboard**.
- Rescore chạy match_phrase để ưu tiên tên có cụm từ **wireless keyboard** gần nhau.
- Score mới được kết hợp với score ban đầu.
- Elasticsearch sắp xếp lại nhóm tài liệu được rescore.

Rescore không phải là một truy vấn tìm kiếm độc lập thay thế query ban đầu. Nó là một bước bổ sung trong search request.

Cấu trúc tổng quát:

~~~text
Search request
      |
      v
Query ban đầu
      |
      v
Tập ứng viên có score cao
      |
      v
Giới hạn window_size trên mỗi shard
      |
      v
Rescore query chạy trên nhóm ứng viên
      |
      v
Kết hợp score cũ và score mới
      |
      v
Sắp xếp lại kết quả
      |
      v
Trả về các hit theo phân trang
~~~

Các tài liệu nằm ngoài cửa sổ rescore không được tính lại score. Vì vậy, rescore chỉ có thể thay đổi thứ hạng trong tập ứng viên đã được chọn ở bước đầu; nó không tự đưa một tài liệu rất xa trong thứ hạng ban đầu vào nhóm đầu nếu tài liệu đó nằm ngoài window.

## 6. Query rescorer: ví dụ cơ bản

Một request có thể dùng match query ban đầu và match_phrase ở bước rescore:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": {
        "query": "wireless mechanical keyboard",
        "operator": "or"
      }
    }
  },
  "rescore": {
    "window_size": 100,
    "query": {
      "rescore_query": {
        "match_phrase": {
          "name": {
            "query": "wireless mechanical keyboard",
            "slop": 1
          }
        }
      },
      "query_weight": 0.2,
      "rescore_query_weight": 2.0
    }
  }
}
~~~

Ý nghĩa:

- **query** ở cấp request là truy vấn ban đầu, tạo tập ứng viên và score đầu tiên.
- **rescore** khai báo bước tính điểm lại.
- **window_size** giới hạn số tài liệu được xem xét cho rescore trên mỗi shard.
- **rescore_query** là truy vấn thứ hai, ở đây ưu tiên cụm từ gần nhau.
- **query_weight** điều chỉnh ảnh hưởng của score ban đầu.
- **rescore_query_weight** điều chỉnh ảnh hưởng của score từ rescore query.

Trong ví dụ, trọng số của rescore query lớn hơn, vì vậy tài liệu khớp cụm từ có thể được đẩy lên cao hơn. Các giá trị chỉ mang tính minh họa; cần tinh chỉnh bằng đánh giá relevance thực tế.

### Vì sao dùng hai bước?

Query đầu tiên có thể được tối ưu để thu thập ứng viên với độ bao phủ tốt. Rescore query có thể phức tạp hơn và chỉ chạy trên một nhóm nhỏ, nhờ đó cải thiện độ chính xác mà không phải trả chi phí cao cho toàn bộ tài liệu phù hợp.

Ví dụ, match query trên nhiều từ khóa có thể lấy đủ sản phẩm liên quan. Match_phrase ở bước rescore ưu tiên các sản phẩm có cụm từ chính xác hoặc gần nhau trong tên.

## 7. window_size và phạm vi rescore

**window_size** quy định số tài liệu đầu tiên trên mỗi shard được đưa vào bước rescore. Giá trị càng lớn thì càng có nhiều ứng viên được tính lại, nhưng chi phí xử lý cũng tăng.

Ví dụ:

~~~json
{
  "rescore": {
    "window_size": 100,
    "query": {
      "rescore_query": {
        "match_phrase": {
          "name": "wireless keyboard"
        }
      }
    }
  }
}
~~~

Nếu mỗi shard có nhiều tài liệu phù hợp, Elasticsearch chỉ rescore các ứng viên nằm trong cửa sổ đã cấu hình. Một tài liệu xếp hạng thấp hơn cửa sổ không thể được nâng lên đầu nhờ rescore vì nó không được chạy query thứ hai.

Các nguyên tắc thực tế:

- Đặt window_size đủ lớn để chứa nhóm ứng viên có khả năng cần cải thiện thứ hạng.
- Window lớn làm tăng chi phí query thứ hai.
- Window quá nhỏ có thể bỏ qua tài liệu phù hợp nhưng xếp hạng ban đầu thấp.
- Rescore được áp dụng trên từng shard, do đó số ứng viên tổng thể có thể lớn hơn window_size.
- Khi phân trang, nên giữ window_size nhất quán giữa các request của cùng một luồng tìm kiếm.
- Nếu dùng from/size, window_size cần đủ lớn để bao phủ phần kết quả mà ứng dụng muốn được rescore; nếu trang nằm ngoài cửa sổ, các hit ở đó có thể chưa được tính lại.

Ví dụ, trang đầu có size 20 nhưng window_size chỉ là 10 thì một phần hit cần trả về có thể nằm ngoài phạm vi rescore. Hãy chọn window_size phù hợp với from + size và số lượng ứng viên muốn xếp hạng lại.

Không nên đặt window_size bằng toàn bộ số tài liệu trong index. Rescore được thiết kế để tinh chỉnh nhóm đầu, không phải chạy lại query thứ hai trên toàn bộ tập dữ liệu.

## 8. Kết hợp score trong query rescorer

Query rescorer kết hợp score từ truy vấn ban đầu và score của truy vấn rescore. Hai trọng số thường dùng:

- **query_weight**: trọng số cho score ban đầu.
- **rescore_query_weight**: trọng số cho score từ truy vấn rescore.

Với score mode mặc định **total**, cách tính khái quát là:

\[
\text{final score} =
(\text{query score} \times \text{query weight}) +
(\text{rescore score} \times \text{rescore query weight})
\]

Ví dụ:

~~~json
{
  "rescore": {
    "window_size": 100,
    "query": {
      "rescore_query": {
        "match_phrase": {
          "name": "wireless keyboard"
        }
      },
      "query_weight": 1.0,
      "rescore_query_weight": 3.0,
      "score_mode": "total"
    }
  }
}
~~~

Trong trường hợp này, score từ match_phrase có ảnh hưởng lớn hơn score truy vấn ban đầu. Tài liệu khớp cụm từ có cơ hội được xếp hạng cao hơn.

Elasticsearch hỗ trợ các chế độ kết hợp score như:

| score_mode | Ý nghĩa |
|---|---|
| **total** | Cộng score đã nhân trọng số |
| **multiply** | Nhân các score đã nhân trọng số |
| **avg** | Lấy trung bình các score đã nhân trọng số |
| **max** | Chọn score lớn hơn |
| **min** | Chọn score nhỏ hơn |

Cần kiểm tra tài liệu đúng phiên bản Elasticsearch vì kiểu rescorer và các lựa chọn hỗ trợ có thể thay đổi. Không chọn score_mode chỉ theo tên; hãy kiểm tra ảnh hưởng của nó trên tập dữ liệu thực tế.

Nếu một query rescore không khớp tài liệu, cách kết hợp score vẫn phụ thuộc score mode và hành vi của query. Hãy dùng explain hoặc profile khi cần hiểu vì sao một tài liệu được xếp hạng ở vị trí cụ thể.

## 9. Khi nào nên dùng rescore?

Rescore phù hợp khi query ban đầu đã tìm được tập ứng viên tốt, nhưng thứ tự ở nhóm đầu cần tinh chỉnh bằng một tiêu chí tìm kiếm đắt hơn.

Một số tình huống:

- Tìm kiếm cụm từ: ưu tiên tài liệu có các từ nằm gần nhau theo đúng thứ tự.
- Tìm kiếm sản phẩm: ưu tiên tên sản phẩm khớp cụm từ chính xác hơn mô tả chỉ chứa một vài từ.
- Tìm kiếm tài liệu: dùng query rộng để lấy ứng viên, sau đó dùng query phrase hoặc query chuyên biệt để xếp hạng nhóm đầu.
- Tìm kiếm có nhiều trường: truy vấn đầu tiên tìm trong title và description, bước rescore ưu tiên title khớp cụm từ.
- Tối ưu relevance: cải thiện top results mà không áp dụng query đắt cho toàn bộ tập tài liệu.

Ví dụ query ban đầu tìm ở cả name và description:

~~~json
{
  "query": {
    "multi_match": {
      "query": "wireless mechanical keyboard",
      "fields": [
        "name^3",
        "description"
      ],
      "type": "best_fields"
    }
  },
  "rescore": {
    "window_size": 100,
    "query": {
      "rescore_query": {
        "match_phrase": {
          "name": {
            "query": "wireless mechanical keyboard",
            "slop": 1
          }
        }
      },
      "query_weight": 1.0,
      "rescore_query_weight": 2.5
    }
  }
}
~~~

Truy vấn ban đầu có thể tìm các từ trong nhiều trường, còn rescore ưu tiên tên sản phẩm chứa cụm từ gần nhau. Đây là cách tạo hai tầng relevance.

## 10. Khi nào không nên dùng rescore?

Rescore không phù hợp với mọi truy vấn.

Không nên dùng khi:

- Truy vấn chỉ là filter theo status, category hoặc range.
- Không có một query thứ hai có khả năng cải thiện relevance.
- Số lượng ứng viên nhỏ và query ban đầu đã đủ tốt.
- Muốn thay đổi điều kiện tài liệu nào được phép xuất hiện; hãy sửa query ban đầu.
- Muốn tính điểm cho mọi tài liệu; cân nhắc function_score hoặc thiết kế query phù hợp.
- Muốn sắp xếp theo trường nghiệp vụ như giá, thời gian hoặc số lượng; dùng sort.
- Muốn loại hit theo một ngưỡng điểm; dùng min_score nếu score có ý nghĩa.
- Muốn chạy query thứ hai trên toàn bộ kết quả; rescore chỉ giới hạn trong window_size.

Rescore cũng không thay thế việc thiết kế analyzer, mapping hoặc query ban đầu. Nếu query đầu tiên bỏ sót một tài liệu hoàn toàn, rescore không thể đưa tài liệu đó vào kết quả vì tài liệu chưa trở thành ứng viên.

## 11. Phân biệt min_score, rescore, function_score và sort

Các tính năng này đều có thể ảnh hưởng kết quả tìm kiếm nhưng giải quyết những nhu cầu khác nhau.

| Tính năng | Vai trò | Phạm vi tác động |
|---|---|---|
| **min_score** | Loại hit có score thấp hơn ngưỡng | Lọc hit theo score |
| **rescore** | Tính lại score và thứ hạng của nhóm ứng viên đầu | Top window_size tài liệu trên mỗi shard |
| **function_score** | Kết hợp score truy vấn với các hàm tính điểm nghiệp vụ | Tập tài liệu khớp query |
| **sort** | Sắp xếp theo score hoặc trường dữ liệu | Thứ tự hit được trả về |
| **bool.filter** | Lọc theo điều kiện dữ liệu | Tập tài liệu phù hợp, không tính score cho filter clause |

### min_score và rescore

min_score hỏi: “Điểm của tài liệu có đủ cao để được giữ lại không?”

Rescore hỏi: “Trong nhóm ứng viên đứng đầu, tài liệu nào nên được xếp hạng cao hơn sau khi xét thêm tiêu chí?”

Có thể dùng cả hai trong một search request, nhưng cần đánh giá ngưỡng dựa trên score cuối cùng và hành vi của phiên bản cluster. Đừng giả định rescore sẽ luôn cứu được tài liệu đã bị loại bởi min_score trong mọi thứ tự xử lý.

### Rescore và function_score

**function_score** thay đổi cách tính điểm cho tập tài liệu khớp query, ví dụ tăng điểm theo popularity, freshness hoặc một giá trị số. Nó phù hợp khi điểm nghiệp vụ phải ảnh hưởng rộng trên tập kết quả.

**rescore** chỉ tinh chỉnh nhóm ứng viên đầu bằng query thứ hai. Nó phù hợp khi một tiêu chí đắt hơn chỉ cần áp dụng cho top results.

Ví dụ function_score có thể tăng điểm sản phẩm phổ biến dựa trên trường popularity; rescore có thể ưu tiên tên sản phẩm khớp cụm từ chính xác. Hai kỹ thuật có thể kết hợp nếu có lý do, nhưng mỗi tầng cần có mục tiêu rõ ràng.

### Rescore và sort

Rescore tác động đến score. Nếu request dùng sort theo trường như price hoặc createdAt, thứ tự cuối cùng được quyết định bởi trường sort đó; thay đổi score có thể không làm thay đổi thứ tự. Rescore thường hữu ích nhất khi kết quả được xếp theo relevance score.

Nếu muốn ưu tiên sản phẩm giá thấp, hãy dùng sort theo price. Nếu muốn ưu tiên tài liệu liên quan hơn, dùng scoring query và có thể bổ sung rescore. Không dùng rescore để thay thế một quy tắc sort rõ ràng.

## 12. Kết hợp rescore với filter

Rescore chỉ nên tinh chỉnh các tài liệu đã qua query ban đầu. Những điều kiện nghiệp vụ nên được đặt trong query/filter trước khi rescore.

Ví dụ chỉ tìm sản phẩm ACTIVE, thuộc danh mục accessories và có tên phù hợp:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "term": {
            "category": "accessories"
          }
        }
      ]
    }
  },
  "rescore": {
    "window_size": 100,
    "query": {
      "rescore_query": {
        "match_phrase": {
          "name": {
            "query": "wireless keyboard",
            "slop": 1
          }
        }
      },
      "query_weight": 1.0,
      "rescore_query_weight": 2.0
    }
  }
}
~~~

Các filter loại bỏ sản phẩm không hợp lệ ngay từ truy vấn ban đầu. Rescore chỉ xét nhóm kết quả phù hợp với điều kiện nghiệp vụ và cải thiện thứ hạng của nhóm đầu.

Đây là thiết kế rõ ràng hơn so với việc cố dùng min_score để loại sản phẩm không ACTIVE hoặc dùng rescore query để thay điều kiện category.

## 13. Dùng min_score trong Spring Data Elasticsearch

Spring Data Elasticsearch có abstraction **Query** để lưu các thiết lập tìm kiếm. Tùy phiên bản, các query object có thể cung cấp thuộc tính **minScore**. Ví dụ với CriteriaQuery:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

Criteria criteria = Criteria.where("name")
        .matches("wireless keyboard");

CriteriaQuery query = new CriteriaQuery(criteria);
query.setMinScore(1.5f);

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Ví dụ minh họa cách đặt ngưỡng score trên Query abstraction. Kiểm tra chữ ký **setMinScore** hoặc builder tương ứng trong phiên bản Spring Data Elasticsearch của dự án; một số phiên bản có thể cung cấp API khác hoặc đặt thuộc tính trên NativeQuery builder.

Với NativeQuery trong các phiên bản Spring Data Elasticsearch 5.x, có thể xây dựng query bằng Elasticsearch Java API Client và đặt các tùy chọn tìm kiếm được hỗ trợ:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
                .field("name")
                .query("wireless keyboard")))
        .withMinScore(1.5f)
        .build();

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Tên builder và kiểu số của **withMinScore** phụ thuộc phiên bản. Dùng dependency do Spring Boot quản lý và đối chiếu API hiện có trong dự án trước khi áp dụng.

Nếu Query abstraction không cung cấp tùy chọn cần thiết, có thể gọi Elasticsearch Java API Client trực tiếp để kiểm soát SearchRequest.

## 14. Dùng rescore qua Elasticsearch Java API Client

Rescore là tùy chọn ở cấp search request. Khi Spring Data abstraction của phiên bản đang dùng không cung cấp cách cấu hình rescore thuận tiện, có thể dùng **ElasticsearchClient** của Elasticsearch Java API Client để xây dựng SearchRequest.

Ví dụ dưới đây minh họa query ban đầu, rescore query và ngưỡng min_score trong cùng request:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.SearchRequest;
import co.elastic.clients.elasticsearch.core.SearchResponse;

SearchRequest request = SearchRequest.of(s -> s
        .index("products")
        .query(q -> q.match(m -> m
                .field("name")
                .query("wireless mechanical keyboard")))
        .minScore(1.5)
        .rescore(r -> r
                .windowSize(100)
                .query(rq -> rq
                        .rescoreQuery(q -> q.matchPhrase(mp -> mp
                                .field("name")
                                .query("wireless mechanical keyboard")))
                        .queryWeight(1.0)
                        .rescoreQueryWeight(2.0)
                )
        )
);

SearchResponse<Product> response =
        elasticsearchClient.search(request, Product.class);
~~~

Trong ví dụ:

- **query(...)** tạo truy vấn ban đầu.
- **minScore(1.5)** đặt ngưỡng score cho request.
- **rescore(...)** khai báo bước tính điểm lại.
- **windowSize(100)** giới hạn nhóm ứng viên được rescore trên mỗi shard.
- **rescoreQuery(...)** dùng match_phrase để ưu tiên cụm từ.
- **queryWeight(...)** và **rescoreQueryWeight(...)** điều chỉnh ảnh hưởng của hai score.
- **search(request, Product.class)** gửi request và ánh xạ source về Product.

Cần dùng Elasticsearch Java API Client tương thích với phiên bản cluster và Spring Boot. Các builder sinh mã, kiểu dữ liệu và overload có thể thay đổi giữa các phiên bản client. Nếu code không compile, kiểm tra API thực tế của dependency thay vì trộn ví dụ từ RestHighLevelClient cũ với Java API Client mới.

Trong ứng dụng Spring Boot, client thường được cấu hình thành bean. Không tạo một client mới cho mỗi request. Hãy inject bean đã được cấu hình vào service hoặc thành phần tìm kiếm chuyên biệt.

## 15. Kiểm tra score và rescore khi debug

Khi thứ tự kết quả không như mong đợi, cần kiểm tra cả truy vấn ban đầu và truy vấn rescore.

Các công cụ hữu ích:

### Xem score của hit

Response tìm kiếm có trường **_score** cho mỗi hit. So sánh score của các tài liệu đầu để hiểu sự khác biệt về thứ hạng.

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

### Dùng explain

API **_explain** giúp giải thích vì sao một tài liệu khớp query và score được tính như thế nào:

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

Explain hữu ích để hiểu query ban đầu. Khi điều tra rescore, hãy so sánh hành vi trước và sau khi thêm rescore, đồng thời kiểm tra request và score thực tế của các hit.

### Dùng profile

Có thể bật **profile: true** để xem chi tiết quá trình thực thi:

~~~http
POST /products/_search
{
  "profile": true,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "rescore": {
    "window_size": 100,
    "query": {
      "rescore_query": {
        "match_phrase": {
          "name": "wireless keyboard"
        }
      }
    }
  }
}
~~~

Profile có chi phí và tạo response lớn. Chỉ bật khi cần điều tra hiệu năng, không bật mặc định trên mọi request production.

### Đánh giá ngưỡng min_score bằng dữ liệu thực tế

Để chọn ngưỡng, tạo bộ truy vấn đại diện và gán nhãn kết quả liên quan. Thử nhiều giá trị min_score, ghi nhận:

- Số lượng hit còn lại.
- Precision và recall.
- Tỷ lệ truy vấn không còn kết quả.
- Những tài liệu liên quan bị loại.
- Độ ổn định score giữa các nhóm truy vấn.
- Ảnh hưởng khi thay analyzer, mapping hoặc query boosts.

Một ngưỡng phù hợp cho tên sản phẩm có thể không phù hợp cho mô tả dài hoặc truy vấn nhiều từ. Nếu có nhiều loại truy vấn, hãy cân nhắc chính sách score riêng theo loại thay vì một con số áp dụng cho tất cả.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| min_score loại hết kết quả | Ngưỡng quá cao hoặc query tạo score thấp | Xem score thực tế, giảm ngưỡng và đánh giá recall |
| min_score không có tác dụng như mong đợi | Query chủ yếu nằm trong filter context hoặc không tạo score có ý nghĩa | Dùng scoring query phù hợp hoặc lọc bằng điều kiện dữ liệu |
| Score thay đổi giữa các truy vấn | Score phụ thuộc query, analyzer, corpus và similarity | Không dùng một ngưỡng toàn cục nếu chưa đánh giá |
| Rescore không thay đổi thứ hạng | Rescore query không phân biệt ứng viên hoặc trọng số quá thấp | Kiểm tra rescore query, score và trọng số |
| Tài liệu mong muốn không được nâng hạng | Tài liệu nằm ngoài window_size | Tăng window hợp lý hoặc cải thiện query ban đầu |
| Rescore làm tăng độ trễ | Window quá lớn hoặc query thứ hai tốn kém | Thu hẹp window và đơn giản hóa rescore query |
| Phân trang có thứ tự không ổn định | window_size thay đổi giữa các request hoặc sort không ổn định | Giữ window_size nhất quán và dùng sort phù hợp |
| Rescore không ảnh hưởng thứ tự | Request sort theo trường như price | Dùng sort theo score nếu mục tiêu là relevance |
| Query ban đầu bỏ sót tài liệu | Rescore chỉ chạy trên ứng viên ban đầu | Cải thiện query ban đầu và mapping |
| API Java không compile | Builder khác giữa các phiên bản client | Kiểm tra dependency và chữ ký API đúng phiên bản |

## 17. Quy trình chọn min_score và rescore

Khi thiết kế xếp hạng tìm kiếm, có thể thực hiện theo trình tự:

1. **Xác định điều kiện nghiệp vụ.** Dùng term, range và bool.filter để loại dữ liệu không hợp lệ.
2. **Xây dựng query tạo score.** Dùng match, multi_match hoặc query phù hợp với ngôn ngữ và mapping.
3. **Đánh giá kết quả ban đầu.** Xem top hits và score trước khi thêm ngưỡng hay rescore.
4. **Xem xét min_score.** Chỉ dùng nếu có ngưỡng liên quan đủ ổn định và được kiểm chứng.
5. **Xem xét rescore.** Dùng khi query thứ hai có thể cải thiện thứ hạng của nhóm ứng viên đầu.
6. **Chọn window_size.** Đủ rộng để bao phủ các hit cần xếp hạng lại, nhưng không quá lớn.
7. **Điều chỉnh trọng số.** Thử query_weight và rescore_query_weight trên tập relevance đã gán nhãn.
8. **Kiểm tra phân trang và sort.** Bảo đảm window và thứ tự kết quả nhất quán.
9. **Đo hiệu năng.** Dùng profile, slow logs và metrics ứng dụng.
10. **Theo dõi sau triển khai.** Đánh giá tỷ lệ không có kết quả, độ trễ và phản hồi người dùng.

min_score và rescore giải quyết hai bài toán khác nhau. **min_score** giữ lại những hit có điểm đạt ngưỡng; **rescore** cải thiện thứ hạng của một nhóm ứng viên bằng truy vấn thứ hai. Điều kiện dữ liệu vẫn nên được xử lý bằng query/filter, còn thứ tự theo thuộc tính nghiệp vụ nên dùng sort. Chỉ sử dụng score threshold và rescore khi đã hiểu score được tạo ra như thế nào, phạm vi window ra sao và chất lượng kết quả đã được đánh giá trên truy vấn thực tế.
