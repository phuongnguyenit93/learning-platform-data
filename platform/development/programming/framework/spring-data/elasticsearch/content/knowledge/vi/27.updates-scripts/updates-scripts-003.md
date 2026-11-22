# Upsert, doc_as_upsert và điều kiện tài liệu chưa tồn tại

Khi cập nhật dữ liệu trong Elasticsearch, ứng dụng thường cần xử lý hai trường hợp: tài liệu đã tồn tại thì thay đổi một số trường; tài liệu chưa tồn tại thì tạo mới. **Upsert** kết hợp hai hành vi này trong một thao tác cập nhật. Elasticsearch cung cấp thuộc tính **upsert** và **doc_as_upsert** trong Update API để thực hiện điều đó.

Tuy nhiên, upsert không có nghĩa là “chỉ tạo nếu chưa tồn tại”. Nếu tài liệu đã có, Update API vẫn áp dụng phần cập nhật. Khi nghiệp vụ yêu cầu tạo mới và phải thất bại nếu ID đã tồn tại, cần dùng **Create API** hoặc **op_type=create**. Phân biệt rõ hai ý nghĩa này giúp tránh ghi đè dữ liệu, xử lý đúng xung đột và hạn chế lỗi do nhiều request chạy đồng thời.

Bài này sử dụng index **products** với các trường SKU, tên, giá, số lượng tồn kho và trạng thái. Nội dung tập trung vào Update API, upsert, doc_as_upsert, scripted upsert, thao tác tạo mới có điều kiện, xử lý xung đột và cách gọi từ Spring Data Elasticsearch.

## 1. Update API và thao tác cập nhật một phần tài liệu

Elasticsearch lưu mỗi tài liệu dưới dạng một JSON source. Khi cần thay đổi một vài trường, Update API cho phép gửi một **partial document** thay vì gửi lại toàn bộ source.

Ví dụ tài liệu hiện tại:

~~~json
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "stock": 20,
  "status": "ACTIVE"
}
~~~

Ứng dụng chỉ muốn thay đổi giá:

~~~http
POST /products/_update/p-1001
{
  "doc": {
    "price": 94.5
  }
}
~~~

Elasticsearch cập nhật trường price và giữ lại các trường khác. Đây là một partial update. Nếu tài liệu chưa tồn tại, request trên mặc định không tự tạo tài liệu; Elasticsearch trả lỗi tài liệu không tồn tại.

Update API thực hiện thao tác đọc, áp dụng thay đổi và lập chỉ mục lại source ở phía Elasticsearch. Ứng dụng không cần tự GET tài liệu, sửa object rồi gửi lại toàn bộ chỉ để đổi một trường.

### Partial document không phải phép gán toàn bộ source

Với request:

~~~json
{
  "doc": {
    "price": 94.5
  }
}
~~~

các trường sku, name, stock và status vẫn được giữ nguyên. Nếu gửi một object lồng nhau, Elasticsearch áp dụng quy tắc merge cho các object; với mảng, không nên giả định phần tử sẽ được nối thêm. Một giá trị mảng được gửi trong partial document thường thay thế giá trị mảng hiện tại.

Ví dụ tài liệu có:

~~~json
{
  "address": {
    "city": "Ho Chi Minh City",
    "district": "District 1"
  },
  "tags": [
    "keyboard",
    "wireless"
  ]
}
~~~

Gửi partial doc:

~~~json
{
  "doc": {
    "address": {
      "district": "District 3"
    },
    "tags": [
      "mechanical"
    ]
  }
}
~~~

Object address được merge theo các trường con, còn tags được thay bằng mảng mới. Nếu muốn thêm một phần tử vào mảng hoặc tăng stock theo giá trị hiện tại, hãy cân nhắc script update.

## 2. Upsert là gì?

**Upsert** là kết hợp update và insert:

- Nếu tài liệu đã tồn tại: áp dụng thay đổi.
- Nếu tài liệu chưa tồn tại: tạo tài liệu từ dữ liệu upsert được cung cấp.

Update API nhận cả partial document và một tài liệu khởi tạo:

~~~http
POST /products/_update/p-1001
{
  "doc": {
    "price": 94.5
  },
  "upsert": {
    "sku": "KB-1001",
    "name": "Mechanical Keyboard",
    "price": 89.5,
    "stock": 20,
    "status": "ACTIVE"
  }
}
~~~

Nếu ID p-1001 đã tồn tại, Elasticsearch áp dụng phần doc và cập nhật price thành 94.5. Nếu ID chưa tồn tại, Elasticsearch lập chỉ mục tài liệu từ object upsert.

Điểm quan trọng là **upsert không phải create-only**. Nó được thiết kế cho hành vi create-or-update. Nếu hai request cùng dùng một ID, thao tác được xử lý trên shard chứa tài liệu; ứng dụng không cần thực hiện chuỗi GET rồi quyết định insert hoặc update ở phía client.

### Vì sao upsert hữu ích?

Một luồng GET rồi ghi thường có dạng:

~~~text
Ứng dụng                  Elasticsearch
   |                            |
   |---- GET document --------->|
   |<--- không tồn tại ---------|
   |                            |
   |---- INDEX document ------->|
   |<--- created ---------------|
~~~

Giữa GET và INDEX, một request khác có thể tạo cùng ID. Hai ứng dụng cùng nhìn thấy tài liệu chưa tồn tại rồi cùng ghi. Đây là race condition.

Upsert chuyển quyết định tồn tại và thao tác cập nhật/tạo mới vào một request Update API. Elasticsearch xử lý việc này trên shard chứa tài liệu, giúp tránh khoảng trống do ứng dụng tự kiểm tra rồi ghi.

## 3. Phân biệt doc và upsert

Hai thuộc tính có vai trò riêng:

| Thuộc tính | Khi tài liệu tồn tại | Khi tài liệu chưa tồn tại |
|---|---|---|
| **doc** | Partial document được merge vào source hiện tại | Không tự tạo tài liệu nếu không có upsert |
| **upsert** | Không dùng làm nội dung cập nhật thông thường | Dùng làm source ban đầu để tạo tài liệu |
| **doc_as_upsert** | doc vẫn được dùng để cập nhật | Nội dung doc được dùng làm tài liệu tạo mới |

Ví dụ:

~~~json
{
  "doc": {
    "price": 94.5
  },
  "upsert": {
    "sku": "KB-1001",
    "name": "Mechanical Keyboard",
    "price": 89.5,
    "stock": 20
  }
}
~~~

Khi tồn tại, giá được cập nhật thành 94.5. Khi chưa tồn tại, tài liệu được tạo từ upsert và giá ban đầu là 89.5.

Điều này cho phép hai cấu trúc khác nhau:

- Một partial update nhỏ cho tài liệu đang tồn tại.
- Một source đầy đủ hơn cho trường hợp phải tạo mới.

Nên bảo đảm object upsert có đủ các trường bắt buộc theo mapping và nghiệp vụ. Nếu upsert thiếu một trường quan trọng, tài liệu mới có thể được tạo nhưng không đáp ứng hợp đồng dữ liệu của ứng dụng.

## 4. doc_as_upsert là gì?

**doc_as_upsert: true** yêu cầu Elasticsearch dùng chính nội dung trong doc làm tài liệu upsert nếu ID chưa tồn tại.

Ví dụ:

~~~http
POST /products/_update/p-1001
{
  "doc": {
    "sku": "KB-1001",
    "name": "Mechanical Keyboard",
    "price": 94.5,
    "stock": 20,
    "status": "ACTIVE"
  },
  "doc_as_upsert": true
}
~~~

Kết quả:

- Nếu p-1001 đã tồn tại, các trường trong doc được áp dụng lên source hiện tại.
- Nếu p-1001 chưa tồn tại, toàn bộ object doc được dùng để tạo tài liệu mới.

doc_as_upsert phù hợp khi nội dung dùng để cập nhật cũng chính là nội dung đủ để khởi tạo tài liệu. Nó giúp tránh phải lặp lại cùng một JSON trong cả doc và upsert.

### doc_as_upsert không có nghĩa là chỉ tạo khi chưa tồn tại

Đây là điểm cần nhớ. Request có doc_as_upsert vẫn cập nhật tài liệu hiện có. Nếu tài liệu tồn tại, Elasticsearch không trả lỗi duplicate chỉ vì ID đã có.

Ví dụ request:

~~~json
{
  "doc": {
    "status": "ACTIVE"
  },
  "doc_as_upsert": true
}
~~~

Nếu tài liệu đã tồn tại, status được cập nhật. Nếu chưa tồn tại, Elasticsearch tạo source chỉ có status. Nếu Product yêu cầu sku và name, tài liệu mới có thể không đầy đủ về mặt nghiệp vụ dù request kỹ thuật thành công.

Vì vậy, chỉ dùng doc_as_upsert khi doc thực sự đủ để tạo một tài liệu hợp lệ. Nếu cần một source ban đầu khác với phần update, dùng upsert riêng.

### Chọn doc_as_upsert hay upsert tường minh?

| Nhu cầu | Lựa chọn |
|---|---|
| Nội dung update cũng đủ làm source mới | doc_as_upsert: true |
| Source mới cần nhiều trường hơn partial update | doc kết hợp upsert |
| Cần chạy logic khởi tạo khi tài liệu chưa tồn tại | scripted_upsert |
| Chỉ được tạo mới, tài liệu có sẵn phải gây conflict | Create API hoặc op_type=create |

Không cần khai báo cả upsert và doc_as_upsert cho cùng một request. Hãy chọn một cách thể hiện rõ ý định để tránh cấu hình khó hiểu.

## 5. Upsert và điều kiện tài liệu chưa tồn tại là hai yêu cầu khác nhau

Trong nghiệp vụ, cụm từ “nếu tài liệu chưa tồn tại thì tạo” có thể mang hai ý nghĩa:

1. **Create-or-update:** chưa có thì tạo, đã có thì cập nhật.
2. **Create-only:** chưa có thì tạo, đã có thì từ chối và báo xung đột.

Upsert đáp ứng yêu cầu thứ nhất. Create API đáp ứng yêu cầu thứ hai.

| Tình trạng ID | Update API có upsert | Create API |
|---|---|---|
| ID chưa tồn tại | Tạo tài liệu | Tạo tài liệu |
| ID đã tồn tại | Cập nhật tài liệu | Từ chối, thường trả HTTP 409 |
| Mục tiêu | Đồng bộ hoặc ghi trạng thái theo kiểu create-or-update | Bảo đảm không ghi đè tài liệu đã có |

Nếu yêu cầu là “tạo đơn hàng với ID này chỉ một lần; nếu đã tồn tại thì báo đơn hàng trùng”, hãy dùng thao tác create-only. Không dùng doc_as_upsert vì request có thể cập nhật source hiện tại.

Nếu yêu cầu là “nhận bản ghi sản phẩm mới nhất từ nguồn đồng bộ; chưa có thì tạo, có rồi thì cập nhật một số trường”, upsert phù hợp hơn.

## 6. Create API: tạo mới và thất bại nếu ID đã tồn tại

Elasticsearch cung cấp endpoint **_create** để chỉ tạo tài liệu khi ID chưa tồn tại.

Ví dụ:

~~~http
PUT /products/_create/p-1001
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "stock": 20,
  "status": "ACTIVE"
}
~~~

Nếu p-1001 chưa tồn tại, tài liệu được tạo. Nếu ID đã tồn tại, Elasticsearch trả lỗi xung đột, thường là HTTP 409 với loại lỗi resource_already_exists_exception.

Một cách tương đương là dùng Index API với **op_type=create**:

~~~http
PUT /products/_doc/p-1001?op_type=create
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "stock": 20,
  "status": "ACTIVE"
}
~~~

Điểm khác biệt với thao tác index thông thường:

- Index API mặc định có thể tạo mới hoặc thay thế source của ID đã có.
- op_type=create yêu cầu ID chưa tồn tại.
- _create thể hiện trực tiếp ý định create-only.

Đây là cách an toàn để bảo vệ tài liệu khỏi bị ghi đè do request lặp hoặc do nhiều client cùng tạo một ID.

## 7. Vì sao không nên dùng GET rồi mới CREATE?

Một cách triển khai dễ nghĩ tới:

~~~text
GET /products/_doc/p-1001
Nếu không tồn tại:
    PUT /products/_doc/p-1001
Nếu tồn tại:
    Báo duplicate
~~~

Cách này có race condition:

1. Request A kiểm tra và thấy ID chưa tồn tại.
2. Request B cũng kiểm tra và thấy ID chưa tồn tại.
3. Request A ghi tài liệu.
4. Request B ghi cùng ID và có thể thay thế tài liệu của A nếu dùng Index API thông thường.

Dùng _create giải quyết điều kiện này ở phía Elasticsearch:

~~~text
Request A ---- _create/p-1001 ----> thành công
Request B ---- _create/p-1001 ----> 409 conflict
~~~

Chỉ một request tạo được tài liệu với ID đó. Request còn lại nhận xung đột và có thể chuyển thành phản hồi nghiệp vụ như “mã đã tồn tại”.

Không nên biến mọi HTTP 409 thành thành công. Hãy xác định đây là duplicate có thể dự kiến hay xung đột phiên bản khi cập nhật. Hai trường hợp có ý nghĩa khác nhau.

## 8. Bulk API: phân biệt index, create và update

Khi ghi nhiều tài liệu, Bulk API có các action khác nhau:

| Action | Ý nghĩa |
|---|---|
| **index** | Tạo mới hoặc thay thế source của ID |
| **create** | Chỉ tạo nếu ID chưa tồn tại |
| **update** | Cập nhật một phần hoặc thực hiện upsert |
| **delete** | Xóa tài liệu |

Ví dụ bulk create:

~~~http
POST /_bulk
{ "create": { "_index": "products", "_id": "p-1001" } }
{ "sku": "KB-1001", "name": "Mechanical Keyboard", "price": 89.5 }
{ "create": { "_index": "products", "_id": "p-1002" } }
{ "sku": "MS-1002", "name": "Wireless Mouse", "price": 25.0 }
~~~

Nếu một ID đã tồn tại, action create tương ứng có thể thất bại với 409; các action khác trong bulk vẫn có thể thành công. Bulk response cần được kiểm tra theo từng item, không chỉ dựa vào HTTP status tổng thể.

Ví dụ bulk update với upsert:

~~~http
POST /_bulk
{ "update": { "_index": "products", "_id": "p-1001" } }
{ "doc": { "stock": 15 }, "upsert": { "sku": "KB-1001", "name": "Mechanical Keyboard", "stock": 15 } }
~~~

Ví dụ bulk update dùng doc_as_upsert:

~~~http
POST /_bulk
{ "update": { "_index": "products", "_id": "p-1002" } }
{ "doc": { "sku": "MS-1002", "name": "Wireless Mouse", "price": 25.0, "stock": 30 }, "doc_as_upsert": true }
~~~

Mỗi action update có thể dùng doc, upsert, doc_as_upsert hoặc script theo yêu cầu. Cần nhớ Bulk API dùng định dạng NDJSON: mỗi dòng metadata/action và dòng source hoặc update body tiếp theo phải tách riêng; request thường kết thúc bằng newline.

## 9. Scripted upsert

Khi việc cập nhật phụ thuộc vào giá trị hiện tại hoặc cần logic khởi tạo riêng, có thể dùng **scripted_upsert**.

Ví dụ muốn tăng số lượng tồn kho thêm một lượng delta. Nếu tài liệu chưa tồn tại, khởi tạo stock bằng 0 rồi áp dụng delta:

~~~http
POST /products/_update/p-1001
{
  "scripted_upsert": true,
  "script": {
    "lang": "painless",
    "source": """
      if (ctx._source.containsKey('stock')) {
        ctx._source.stock += params.delta;
      } else {
        ctx._source.stock = params.delta;
      }
    """,
    "params": {
      "delta": 5
    }
  },
  "upsert": {
    "sku": "KB-1001",
    "name": "Mechanical Keyboard",
    "stock": 0,
    "status": "ACTIVE"
  }
}
~~~

Với scripted_upsert true, script được chạy dù tài liệu đã tồn tại hay chưa. Khi chưa có, object upsert cung cấp source ban đầu cho script. Script sau đó thay đổi source theo logic đã viết.

Trong ví dụ, nếu tài liệu chưa tồn tại, upsert khởi tạo stock bằng 0, rồi script tăng lên 5. Nếu tài liệu đã có stock là 20, script tăng thành 25.

Nếu bỏ scripted_upsert hoặc đặt false, khi tài liệu chưa tồn tại Elasticsearch dùng object upsert để tạo mà không chạy script. Khi tài liệu đã tồn tại, script vẫn chạy như bình thường.

### Khi nào cần scripted_upsert?

Dùng khi giá trị khởi tạo và logic cập nhật cần được thực hiện cùng nhau, ví dụ:

- Tăng bộ đếm nếu tài liệu đã tồn tại, tạo bộ đếm ban đầu nếu chưa có.
- Cập nhật tổng số lượt xem.
- Thêm hoặc loại phần tử theo điều kiện trong script.
- Tạo tài liệu thống kê tổng hợp và cập nhật các trường dựa trên dữ liệu hiện tại.
- Chỉ thay đổi source nếu một điều kiện nghiệp vụ được thỏa mãn.

Script có thể phức tạp hơn partial doc và cần được kiểm soát. Chỉ dùng script khi thao tác không thể biểu đạt rõ bằng doc/upsert đơn giản.

### doc_as_upsert và scripted_upsert

Hai tùy chọn này giải quyết các nhu cầu khác nhau. doc_as_upsert dùng doc làm source tạo mới; scripted_upsert chạy script cả khi tài liệu chưa tồn tại. Elasticsearch không cho phép dùng doc_as_upsert cùng scripted_upsert trong cùng request. Với scripted upsert, hãy cung cấp upsert source và script theo đúng cấu trúc Update API.

## 10. Script có thể bỏ qua update hoặc xóa tài liệu

Painless script có thể điều khiển thao tác thông qua **ctx.op**.

Ví dụ chỉ cập nhật stock khi delta khác 0:

~~~json
{
  "script": {
    "lang": "painless",
    "source": """
      if (params.delta == 0) {
        ctx.op = 'noop';
      } else {
        ctx._source.stock += params.delta;
      }
    """,
    "params": {
      "delta": 0
    }
  }
}
~~~

Các thao tác thường gặp:

- **index**: ghi source sau khi script hoàn tất.
- **noop**: không thay đổi tài liệu.
- **delete**: xóa tài liệu.

Khi kết hợp script với upsert, cần xác định rõ source ban đầu và trạng thái ctx.op. Một script có thể đặt noop nếu không cần thay đổi; ứng dụng cần đọc kết quả update để biết có cập nhật thật hay không.

Không đưa chuỗi script tùy ý do người dùng gửi vào request. Hãy dùng script source được kiểm soát và truyền giá trị biến qua params để tránh lỗi cú pháp và giới hạn rủi ro.

## 11. detect_noop và cập nhật không thay đổi dữ liệu

Khi dùng partial document, Elasticsearch có thể kiểm tra xem giá trị gửi lên có làm thay đổi source hay không. Tùy chọn **detect_noop** mặc định thường được bật cho Update API.

Ví dụ source hiện tại:

~~~json
{
  "status": "ACTIVE",
  "stock": 20
}
~~~

Request:

~~~json
{
  "doc": {
    "status": "ACTIVE"
  }
}
~~~

Nếu nội dung không làm thay đổi tài liệu, Elasticsearch có thể trả kết quả **noop** thay vì lập chỉ mục một phiên bản source mới.

Có thể cấu hình rõ:

~~~http
POST /products/_update/p-1001
{
  "detect_noop": true,
  "doc": {
    "status": "ACTIVE"
  }
}
~~~

detect_noop hữu ích khi ứng dụng thường gửi trạng thái đồng bộ lặp lại. Tuy nhiên, không nên coi noop là lỗi. Nó có nghĩa dữ liệu hiện tại đã tương đương với nội dung update theo cách Elasticsearch kiểm tra.

Với script, việc phát hiện noop phụ thuộc logic script; script có thể chủ động đặt ctx.op = noop.

## 12. Điều kiện cập nhật theo sequence number và primary term

Khi nhiều ứng dụng cùng sửa một tài liệu, có thể cần **optimistic concurrency control** để chỉ cho phép update nếu tài liệu vẫn ở phiên bản mà client đã đọc.

Elasticsearch cung cấp:

- **_seq_no**: sequence number của thao tác trên shard.
- **_primary_term**: primary term của shard tại thời điểm đó.

Response GET hoặc search có thể trả metadata này. Ứng dụng dùng chúng khi cập nhật:

~~~http
POST /products/_update/p-1001?if_seq_no=12&if_primary_term=3
{
  "doc": {
    "price": 94.5
  }
}
~~~

Nếu tài liệu vẫn ở sequence number 12 và primary term 3, update có thể thực hiện. Nếu một request khác đã cập nhật tài liệu, điều kiện không còn đúng và Elasticsearch trả xung đột phiên bản, thường là HTTP 409.

Đây là điều kiện “cập nhật nếu phiên bản chưa thay đổi”, không phải điều kiện “chỉ tạo nếu tài liệu chưa tồn tại”.

| Cơ chế | Điều kiện |
|---|---|
| **_create / op_type=create** | ID chưa tồn tại |
| **upsert** | Chưa có thì tạo; có rồi thì cập nhật |
| **if_seq_no + if_primary_term** | Chỉ ghi nếu phiên bản hiện tại khớp metadata đã đọc |
| **retry_on_conflict** | Thử lại update khi có version conflict theo chính sách retry |

Không dùng if_seq_no/if_primary_term để thay cho Create API. Nếu ID chưa tồn tại, request update với điều kiện phiên bản không có tài liệu để cập nhật và không tự biến thành thao tác create-only.

## 13. retry_on_conflict và cập nhật đồng thời

Update API có thể gặp version conflict khi một request khác cập nhật tài liệu giữa lúc Elasticsearch đọc source và ghi source mới. **retry_on_conflict** cho phép Elasticsearch thử lại update một số lần.

Ví dụ:

~~~http
POST /products/_update/p-1001?retry_on_conflict=3
{
  "script": {
    "source": "ctx._source.stock += params.delta",
    "params": {
      "delta": 1
    }
  }
}
~~~

Nếu có xung đột, Elasticsearch có thể đọc lại source mới nhất và chạy lại update script theo số lần retry đã cấu hình.

Điều này hữu ích với các thao tác tăng bộ đếm hoặc thay đổi dựa trên source hiện tại. Tuy nhiên:

- Retry không bảo đảm request luôn thành công.
- Script có thể được chạy nhiều lần trong quá trình thử lại.
- Script nên an toàn khi được thực thi lại trên source mới.
- Tác dụng phụ bên ngoài Elasticsearch không nên đặt trong script.
- Với yêu cầu bảo vệ phiên bản mà client đã đọc, dùng if_seq_no/if_primary_term thay vì tự động retry một update dựa trên dữ liệu cũ.

Đối với partial doc ghi một giá trị cố định, retry có thể hợp lý. Với nghiệp vụ yêu cầu phát hiện xung đột để người dùng giải quyết, nên trả conflict và yêu cầu client đọc lại thay vì âm thầm ghi đè.

## 14. Upsert không thay thế khóa định danh ổn định

Upsert cần một ID tài liệu để xác định tài liệu cần cập nhật hoặc tạo mới. Nếu mỗi lần gửi ứng dụng lại để Elasticsearch sinh ID tự động, cùng một bản ghi nghiệp vụ có thể trở thành nhiều tài liệu khác nhau.

Ví dụ sản phẩm có SKU duy nhất. Ứng dụng có thể dùng ID ổn định dựa trên SKU hoặc một ID nội bộ đã lưu:

~~~text
sku = KB-1001
document _id = product-KB-1001
~~~

Mọi lần đồng bộ cùng sản phẩm phải dùng cùng ID. Khi đó upsert mới cập nhật đúng tài liệu.

Không nên dùng một trường SKU như thể Elasticsearch tự bảo đảm unique. Elasticsearch chỉ bảo đảm duy nhất cho _id trong một index; nó không tạo unique constraint cho một field thông thường. Nếu dùng SKU làm khóa nghiệp vụ, cần chuẩn hóa và tạo _id ổn định từ SKU, hoặc có cơ chế quản lý tính duy nhất phù hợp.

Cũng cần chú ý alias và index rollover. Cùng một _id có thể tồn tại ở nhiều backing index khác nhau nếu ghi qua alias trỏ tới nhiều index; tính duy nhất theo _id không tự mở rộng thành unique constraint xuyên mọi backing index.

## 15. Update API và save() trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp nhiều cách ghi tài liệu, nhưng chúng không có cùng semantics.

| API | Ý nghĩa điển hình |
|---|---|
| **repository.save(entity)** | Ghi tài liệu theo ID, thường dùng Index API; source được gửi là entity |
| **ElasticsearchOperations.save(entity)** | Ghi entity theo semantics lưu tài liệu |
| **ElasticsearchOperations.update(UpdateQuery, index)** | Thực hiện Update API, có thể dùng partial doc, upsert hoặc script |
| **ElasticsearchClient.create(...)** | Create-only, xung đột nếu ID đã tồn tại |
| **ElasticsearchClient.update(...)** | Update API với doc/upsert/script |

Nếu gọi save với một entity có ID đã tồn tại, thao tác thường ghi source entity lên tài liệu đó. Đây không tương đương với partial update một vài trường. Nếu entity chỉ có một phần dữ liệu, save có thể thay source bằng object thiếu trường.

Ví dụ entity chỉ có:

~~~json
{
  "id": "p-1001",
  "stock": 25
}
~~~

Gọi save với object này có thể ghi source không có sku, name và price. Nếu chỉ muốn đổi stock và giữ các trường khác, hãy dùng Update API với partial doc.

Không chọn save chỉ vì tên phương thức nghe giống upsert. Hãy dựa trên semantics thực tế: save/index ghi source của entity; update với upsert áp dụng logic create-or-update; create API bảo đảm create-only.

## 16. Dùng UpdateQuery với ElasticsearchOperations

Spring Data Elasticsearch cung cấp **UpdateQuery** để mô tả một thao tác Update API. Có thể dùng **Document** làm partial document và upsert source.

Ví dụ dùng upsert tường minh:

~~~java
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

Document partial = Document.parse("""
{
  "price": 94.5
}
""");

Document initialDocument = Document.parse("""
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "stock": 20,
  "status": "ACTIVE"
}
""");

UpdateQuery updateQuery = UpdateQuery.builder("p-1001")
        .withDocument(partial)
        .withUpsert(initialDocument)
        .build();

operations.update(
        updateQuery,
        IndexCoordinates.of("products")
);
~~~

Khi tài liệu tồn tại, partial document cập nhật price. Khi chưa tồn tại, initialDocument được dùng làm source ban đầu.

### Dùng doc_as_upsert qua UpdateQuery

Nếu partial document cũng đủ để tạo tài liệu:

~~~java
Document document = Document.parse("""
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 94.5,
  "stock": 20,
  "status": "ACTIVE"
}
""");

UpdateQuery updateQuery = UpdateQuery.builder("p-1001")
        .withDocument(document)
        .withDocAsUpsert(true)
        .build();

operations.update(
        updateQuery,
        IndexCoordinates.of("products")
);
~~~

Các tên builder như withDocument, withUpsert và withDocAsUpsert thuộc API UpdateQuery của Spring Data Elasticsearch; chữ ký chi tiết có thể thay đổi giữa các phiên bản. Hãy đối chiếu dependency thực tế trong dự án nếu cần tùy chọn bổ sung như retry_on_conflict, seq_no hoặc primary_term.

### Lưu ý về Document

Document là kiểu biểu diễn dữ liệu JSON của Spring Data Elasticsearch. Có thể tạo từ JSON bằng Document.parse hoặc dựng từ Map theo API phiên bản. Dùng Document giúp thể hiện rõ partial source và upsert source mà không cần tạo một entity đầy đủ.

Nếu cần kiểm soát mapping/conversion từ entity, hãy kiểm tra cách phiên bản Spring Data chuyển đổi object sang Document. Không trộn một Document JSON thô với một entity đã được converter tùy chỉnh mà không xác nhận kết quả source thực tế.

## 17. Dùng Elasticsearch Java API Client để upsert

Trong các ứng dụng Spring Boot dùng Spring Data Elasticsearch 5.x, có thể inject **ElasticsearchClient** do cấu hình Spring tạo ra để dùng trực tiếp Update API.

Ví dụ:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;

import java.util.Map;

Map<String, Object> partial = Map.of(
        "price", 94.5
);

Map<String, Object> initial = Map.of(
        "sku", "KB-1001",
        "name", "Mechanical Keyboard",
        "price", 89.5,
        "stock", 20,
        "status", "ACTIVE"
);

var response = elasticsearchClient.update(
        update -> update
                .index("products")
                .id("p-1001")
                .doc(partial)
                .upsert(initial),
        Map.class
);
~~~

Ở đây:

- index chỉ định index đích.
- id là ID ổn định của tài liệu.
- doc là partial document dùng khi ID đã tồn tại.
- upsert là source dùng khi ID chưa tồn tại.
- response chứa kết quả Update API.

Ví dụ dùng doc_as_upsert:

~~~java
var response = elasticsearchClient.update(
        update -> update
                .index("products")
                .id("p-1001")
                .doc(initial)
                .docAsUpsert(true),
        Map.class
);
~~~

Kiểu generic của partial document và document trả về phụ thuộc cách dùng Java API Client. Ví dụ dùng Map để minh họa JSON động; nếu có Product class phù hợp, có thể dùng kiểu entity đó. Builder và kiểu response cần khớp với phiên bản Elasticsearch Java API Client mà Spring Boot quản lý.

Không tạo ElasticsearchClient mới cho mỗi lần update. Dùng bean đã được cấu hình chung để tái sử dụng transport, connection pool, TLS, credentials và timeout.

## 18. Create-only qua Elasticsearch Java API Client

Để tạo mới và thất bại nếu ID đã tồn tại, dùng **create**:

~~~java
var response = elasticsearchClient.create(
        create -> create
                .index("products")
                .id("p-1001")
                .document(initial)
);
~~~

Nếu p-1001 chưa tồn tại, tài liệu được tạo. Nếu ID đã tồn tại, Elasticsearch trả lỗi conflict. Ứng dụng có thể bắt lỗi tương ứng và chuyển thành phản hồi nghiệp vụ.

Một cách khác là dùng Index API với opType CREATE:

~~~java
import co.elastic.clients.elasticsearch._types.OpType;

var response = elasticsearchClient.index(
        index -> index
                .index("products")
                .id("p-1001")
                .opType(OpType.Create)
                .document(initial)
);
~~~

Tên enum và overload có thể thay đổi theo phiên bản client. Dù dùng create endpoint hay opType CREATE, điều quan trọng là server thực hiện kiểm tra tồn tại và ghi trong cùng một thao tác.

### Xử lý duplicate một cách rõ ràng

Ví dụ luồng nghiệp vụ:

~~~text
Gọi create-only
      |
      v
Thành công?
  |        |
 Có        Không
  |        |
Trả 201   Kiểm tra loại lỗi
           |
           +--> ID đã tồn tại: trả conflict
           |
           +--> Mapping/auth/network: xử lý lỗi kỹ thuật
~~~

Không nên bắt mọi exception rồi trả “đã tồn tại”. Lỗi mapping, quyền truy cập hoặc kết nối không có nghĩa ID bị trùng.

## 19. Khi nào dùng điều kiện phiên bản thay vì upsert?

Upsert phù hợp với đồng bộ create-or-update, nhưng có những nghiệp vụ cần bảo vệ dữ liệu trước cập nhật đồng thời.

Ví dụ:

1. Người dùng A đọc giá 100.
2. Người dùng B đọc giá 100.
3. Người dùng A đổi giá thành 110.
4. Người dùng B gửi giá 105 dựa trên dữ liệu cũ.

Nếu không có kiểm soát concurrency, update của B có thể ghi đè thay đổi của A. Khi đó ứng dụng có thể dùng seq_no và primary_term đã đọc để chỉ cho phép update nếu phiên bản vẫn khớp.

Đây là optimistic concurrency control. Khi có conflict, ứng dụng có thể:

- Trả HTTP 409 để client tải lại và giải quyết.
- Đọc lại dữ liệu và áp dụng lại thay đổi theo quy tắc nghiệp vụ.
- Dùng script update nguyên tử nếu nghiệp vụ là phép tăng/giảm dựa trên giá trị hiện tại.
- Dùng retry_on_conflict nếu thao tác có thể thực thi lại an toàn.

Không dùng upsert để che giấu xung đột nghiệp vụ. Nếu cần ngăn người dùng ghi đè phiên bản mới hơn, hãy sử dụng điều kiện phiên bản.

## 20. Cập nhật tồn kho: chọn partial doc hay script?

Giả sử stock hiện tại là 20. Hai nghiệp vụ khác nhau có thể cần hai cách update.

### Gán tồn kho thành một giá trị cụ thể

Nếu hệ thống quản lý kho gửi giá trị tuyệt đối mới là 25:

~~~json
{
  "doc": {
    "stock": 25
  }
}
~~~

Đây là partial document. Nó đặt stock thành 25.

### Tăng tồn kho thêm 5

Nếu request có nghĩa là “nhập thêm 5 sản phẩm”:

~~~json
{
  "script": {
    "source": "ctx._source.stock += params.quantity",
    "params": {
      "quantity": 5
    }
  }
}
~~~

Đây là phép cộng dựa trên source hiện tại. Nếu hai request cùng tăng 5, script update giúp thực hiện thay đổi dựa trên giá trị đang có ở Elasticsearch thay vì cả hai client cùng đọc 20 rồi cùng ghi 25.

Nếu tài liệu chưa tồn tại và vẫn cần khởi tạo, có thể kết hợp script với upsert và scripted_upsert như ví dụ trước.

Không dùng partial doc để mô phỏng phép tăng nếu client chỉ biết delta. Nếu hai client cùng đọc 20 rồi gửi doc stock=25, một lần tăng có thể bị mất. Chọn kiểu update theo ý nghĩa dữ liệu: giá trị tuyệt đối hay thay đổi tương đối.

## 21. Xử lý response và lỗi của Update API

Update API có thể trả kết quả cho biết tài liệu được tạo, cập nhật hoặc không thay đổi.

Các trạng thái thường gặp:

| Kết quả | Ý nghĩa |
|---|---|
| **created** | Tài liệu được tạo qua upsert |
| **updated** | Tài liệu hiện có được cập nhật |
| **noop** | Không có thay đổi cần ghi |
| **404 document_missing_exception** | Update không có upsert và ID không tồn tại |
| **409 version_conflict_engine_exception** | Có xung đột phiên bản khi update |
| **409 resource_already_exists_exception** | Create-only gặp ID đã tồn tại |
| **400 mapper_parsing_exception** | Dữ liệu không phù hợp mapping |
| **400 script_exception** | Script lỗi khi thực thi |
| **429 hoặc lỗi quá tải** | Cluster đang chịu áp lực hoặc từ chối request |

Với Update API có upsert, trạng thái result có thể là created khi tài liệu chưa tồn tại và updated khi tài liệu đã có. Nếu dùng detect_noop, kết quả có thể là noop.

Không chỉ kiểm tra request có ném exception hay không. Nếu ứng dụng cần ghi audit hoặc phát sự kiện, hãy dựa trên kết quả thực tế để biết thao tác đã tạo, cập nhật hay không thay đổi.

### Refresh và khả năng đọc ngay sau khi ghi

Elasticsearch là near-real-time. Một thao tác update thành công không đồng nghĩa tài liệu lập tức xuất hiện trong mọi search request ngay sau đó. Nếu cần đọc ngay sau ghi, có thể dùng refresh policy phù hợp, chẳng hạn **wait_for**, tùy API và cấu hình.

Không nên ép refresh ngay sau mọi update vì có thể làm giảm hiệu năng indexing. Hãy dùng chính sách refresh theo nhu cầu nhất quán của ứng dụng.

## 22. Bulk update trong Spring Data Elasticsearch

Với số lượng lớn tài liệu, nên cân nhắc Bulk API thay vì gửi một request riêng cho mỗi tài liệu. Bulk giúp giảm round-trip và cho phép xử lý nhiều action trong một lần gửi.

Spring Data Elasticsearch có các abstraction bulk và hỗ trợ cập nhật theo phiên bản. Nếu dùng Java API Client, có thể tạo BulkRequest với từng operation update hoặc create.

Ví dụ NDJSON với update/upsert:

~~~http
POST /_bulk
{ "update": { "_index": "products", "_id": "p-1001", "retry_on_conflict": 3 } }
{ "doc": { "stock": 25 }, "upsert": { "sku": "KB-1001", "name": "Mechanical Keyboard", "stock": 25 } }
{ "create": { "_index": "products", "_id": "p-1002" } }
{ "sku": "MS-1002", "name": "Wireless Mouse", "price": 25.0 }
~~~

Trong response bulk:

- Kiểm tra trường errors.
- Đọc từng item trong mảng items.
- Phân loại create conflict, version conflict, mapping error và lỗi tạm thời.
- Chỉ retry những lỗi phù hợp.
- Không retry mù quáng một create đã thành công nếu không có cơ chế idempotency.

Bulk request có thể trả HTTP 200 dù một hoặc nhiều item thất bại. Vì vậy, phải kiểm tra từng kết quả item; không chỉ dựa vào HTTP status tổng thể.

## 23. Idempotency và request gửi lặp

Một request có thể được gửi lại do client timeout dù Elasticsearch đã xử lý thành công. Nếu thao tác không được thiết kế idempotent, việc retry có thể làm thay đổi dữ liệu nhiều lần.

Ví dụ:

- Gán stock = 25: gửi lại thường vẫn giữ stock ở 25.
- Tăng stock thêm 5: gửi lại lần thứ hai làm stock tăng thêm 5 lần nữa.
- Create-only với ID cố định: lần đầu thành công, lần sau nhận 409.
- Upsert với doc cố định: có thể áp dụng lại cùng giá trị, nhưng cần xét các trường khác và script.

Với thao tác tăng/giảm, cần có idempotency key hoặc lưu ID giao dịch đã xử lý để ngăn cùng một sự kiện được áp dụng nhiều lần. Không thể chỉ dựa vào retry_on_conflict để bảo đảm một nghiệp vụ chỉ chạy một lần; retry_on_conflict xử lý version conflict nội bộ, không phải duplicate event từ client.

Nếu dùng upsert để đồng bộ bản ghi từ một nguồn có ID ổn định, hãy xác định rõ nguồn dữ liệu có quyền ghi đè trường nào và cách xử lý bản ghi đến trễ.

## 24. Bảo vệ tài liệu khỏi việc ghi thiếu trường

doc_as_upsert rất tiện nhưng dễ tạo tài liệu thiếu dữ liệu nếu partial doc không đủ để khởi tạo.

Ví dụ:

~~~json
{
  "doc": {
    "stock": 10
  },
  "doc_as_upsert": true
}
~~~

Nếu tài liệu chưa tồn tại, Elasticsearch tạo source chỉ có stock. Tài liệu có thể thiếu sku, name, price hoặc trạng thái bắt buộc.

Một số cách phòng tránh:

- Dùng upsert tường minh chứa đầy đủ trường cần thiết.
- Dùng doc_as_upsert chỉ khi doc là một source hợp lệ hoàn chỉnh.
- Kiểm tra dữ liệu đầu vào trước khi gửi.
- Dùng mapping phù hợp và cân nhắc dynamic: strict nếu schema cần kiểm soát chặt.
- Có validation nghiệp vụ ở service.
- Theo dõi tài liệu thiếu trường bằng truy vấn kiểm tra dữ liệu.
- Không coi mapping là thay thế cho validation nghiệp vụ; mapping chủ yếu kiểm soát kiểu và cấu trúc index.

Nếu các trường bắt buộc thay đổi theo nghiệp vụ, cần thống nhất schema và versioning giữa các producer. Một producer cũ có thể gửi doc_as_upsert thiếu trường mới được thêm vào hệ thống.

## 25. Chọn thao tác theo mục tiêu nghiệp vụ

| Mục tiêu | Cách phù hợp | Hành vi khi ID đã tồn tại |
|---|---|---|
| Tạo hoặc cập nhật theo ID | Update API + doc + upsert | Cập nhật |
| Dùng cùng một object cho update và insert | doc_as_upsert | Cập nhật |
| Chạy logic khởi tạo và cập nhật bằng script | scripted_upsert | Chạy script |
| Tạo mới duy nhất, không cho ghi đè | _create hoặc op_type=create | Conflict |
| Thay toàn bộ source bằng entity mới | Index API hoặc save theo semantics ghi entity | Thay source |
| Chỉ update nếu tài liệu chưa bị người khác sửa | if_seq_no + if_primary_term | Conflict nếu phiên bản đổi |
| Tăng/giảm theo giá trị hiện tại | Script update | Áp dụng phép tính trên source hiện tại |
| Ghi nhiều tài liệu | Bulk API | Kiểm tra từng item |

Trước khi chọn API, hãy diễn đạt yêu cầu thành một câu cụ thể:

- “Nếu chưa có thì tạo, nếu có thì cập nhật trường stock.”
- “Chỉ tạo đơn hàng mới; nếu mã đã tồn tại thì trả conflict.”
- “Chỉ cập nhật giá nếu tài liệu vẫn là phiên bản mà người dùng vừa đọc.”
- “Tăng bộ đếm thêm một đơn vị, không ghi đè giá trị hiện tại.”

Câu mô tả này giúp chọn đúng Update, Create, script hay optimistic concurrency.

## 26. Quy trình triển khai upsert an toàn

Một quy trình có thể thực hiện theo các bước:

1. **Chọn ID ổn định.** Mọi lần cập nhật cùng một thực thể phải dùng cùng _id.
2. **Xác định semantics.** Cần create-or-update hay create-only?
3. **Chọn payload.** Phân biệt partial doc và source upsert đầy đủ.
4. **Dùng doc_as_upsert đúng lúc.** Chỉ khi doc đủ để tạo tài liệu hợp lệ.
5. **Dùng script khi cần logic trên source hiện tại.** Đặt scripted_upsert và upsert source phù hợp.
6. **Xử lý concurrency.** Chọn retry_on_conflict hoặc if_seq_no/if_primary_term theo nghiệp vụ.
7. **Kiểm tra kết quả.** Phân biệt created, updated, noop và conflict.
8. **Thiết kế retry.** Xác định thao tác có idempotent hay cần idempotency key.
9. **Xử lý bulk item.** Kiểm tra từng kết quả thay vì chỉ HTTP status.
10. **Theo dõi dữ liệu.** Kiểm tra tài liệu mới có đủ trường và mapping đúng.
11. **Chọn refresh policy.** Chỉ chờ refresh khi yêu cầu đọc sau ghi cần thiết.
12. **Kiểm thử race condition.** Gửi nhiều request cùng ID để xác nhận chỉ một create-only thành công hoặc upsert có hành vi đúng.

Upsert và doc_as_upsert giúp ứng dụng thực hiện create-or-update trong một thao tác Update API. **upsert** cung cấp source riêng để tạo mới; **doc_as_upsert** dùng chính partial document làm source khi ID chưa tồn tại; **scripted_upsert** chạy script cả trong trường hợp tạo mới. Nếu yêu cầu là “chỉ tạo khi chưa có, nếu đã có thì từ chối”, hãy dùng **_create** hoặc **op_type=create**. Khi xử lý đồng thời, phân biệt retry_on_conflict với điều kiện phiên bản if_seq_no/if_primary_term; mỗi cơ chế giải quyết một loại xung đột khác nhau.
