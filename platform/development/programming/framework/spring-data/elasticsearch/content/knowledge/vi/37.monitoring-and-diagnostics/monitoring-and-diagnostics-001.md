# Phân loại lỗi kết nối, xác thực, mapping và truy vấn

Khi Spring Data Elasticsearch không thực hiện được một thao tác, thông báo lỗi thường đi qua nhiều lớp: ứng dụng Spring, Elasticsearch Java API Client, HTTP transport, mạng và chính Elasticsearch cluster. Một lỗi hiển thị ở tầng repository có thể bắt nguồn từ DNS, TLS, credential, quyền trên index, mapping, Query DSL hoặc shard đang quá tải.

Cách xử lý hiệu quả là phân loại lỗi theo **lớp phát sinh và dấu hiệu quan sát được**, sau đó kiểm tra đúng nơi. Không nên retry mọi exception như nhau: lỗi kết nối tạm thời có thể phục hồi, còn mapping sai hoặc query không hợp lệ sẽ tiếp tục thất bại cho đến khi code hoặc dữ liệu được sửa.

Bài học này tập trung vào bốn nhóm chính:

- **Kết nối và TLS**: không tìm được host, không mở được socket, timeout hoặc certificate không được tin cậy.
- **Xác thực và phân quyền**: credential sai hoặc identity không có quyền trên cluster/index.
- **Mapping và ghi document**: dữ liệu không tương thích kiểu field, mapping strict từ chối field mới hoặc thao tác ghi sai index.
- **Truy vấn và thực thi search**: Query DSL sai, field không hỗ trợ thao tác được yêu cầu, timeout, shard failure hoặc truy vấn không trả kết quả như mong đợi.

## 1. Xác định lỗi ở lớp nào trước

Một request từ ứng dụng đến Elasticsearch đi qua nhiều bước:

~~~text
Spring service / repository
          |
          v
Spring Data Elasticsearch operations
          |
          v
Elasticsearch Java API Client
          |
          v
HTTP transport + TLS
          |
          v
Network / DNS / load balancer
          |
          v
Elasticsearch node
          |
          +--> authentication / authorization
          |
          +--> index / mapping / document
          |
          +--> query / shard execution
          |
          v
HTTP response
          |
          v
Exception translation / application handler
~~~

Một số lỗi xảy ra trước khi HTTP request tới cluster, ví dụ DNS hoặc TLS handshake. Một số lỗi có HTTP response rõ ràng như 401, 403, 400 hay 404. Một số search request có HTTP status thành công nhưng response chứa shard failures hoặc timeout.

Vì vậy, khi điều tra cần thu thập tối thiểu:

- Thao tác đang chạy: save, bulk, update, delete, get hay search.
- Index hoặc alias đích.
- HTTP status nếu có.
- Elasticsearch error type và reason nếu server trả lỗi.
- Root cause trong exception chain.
- Thời điểm, duration và correlation/request ID.
- Request có timeout, bị retry hay chạy trên nhiều shard không.

Đừng bắt đầu bằng cách đổi mapping hoặc tăng timeout nếu chưa biết lỗi thuộc lớp nào.

## 2. Phân loại nhanh theo dấu hiệu

Bảng dưới đây giúp chọn hướng điều tra đầu tiên:

| Dấu hiệu | Nhóm lỗi có khả năng | Kiểm tra đầu tiên |
|---|---|---|
| `UnknownHostException` | DNS/hostname | Hostname, DNS, container network |
| `ConnectException` / connection refused | TCP endpoint | Host, port, service state, firewall |
| `SocketTimeoutException` | Network hoặc xử lý quá lâu | Connect/read timeout, cluster load, query |
| `SSLHandshakeException` / `PKIX path building failed` | TLS trust | CA chain, truststore, certificate validity |
| HTTP 401 | Authentication | Username/password, API key, expiry |
| HTTP 403 | Authorization | Role, index pattern, privilege của API |
| HTTP 400 + `mapper_parsing_exception` | Mapping/document | Field type, source value, strict mapping |
| HTTP 400 + `parsing_exception` | Query/request syntax | Query DSL, field/operator, JSON shape |
| HTTP 404 | Index/document/resource | Index alias, document ID, update semantics |
| HTTP 409 | Version conflict/create conflict | Concurrent update, duplicate ID, OCC |
| HTTP 429 | Rejection/overload | Thread pool, bulk size, concurrency, backoff |
| `timed_out: true` | Search timeout | Query cost, shard load, timeout budget |
| `_shards.failed > 0` | Partial shard failure | `failures[]`, mapping/shard/node issue |
| 0 hits, không có exception | Query hợp lệ nhưng không khớp | Query semantics, analyzer, filter, dữ liệu |

Đây là hướng phân loại, không phải kết luận tuyệt đối. Ví dụ timeout có thể do DNS, load balancer, socket, cluster hoặc downstream; cần đọc root cause và quan sát cluster để xác định.

## 3. Kết nối: DNS, host và port

Nếu ứng dụng không resolve được hostname, lỗi thường xuất hiện trước khi có HTTP response.

Dấu hiệu thường gặp:

~~~text
java.net.UnknownHostException: elasticsearch
~~~

Nguyên nhân có thể là:

- Tên host trong cấu hình sai.
- Container ứng dụng và Elasticsearch không nằm trong cùng Docker network.
- Kubernetes Service/DNS name sai namespace.
- DNS nội bộ chưa sẵn sàng.
- Testcontainers mapped host/port đã thay đổi nhưng Spring context vẫn giữ giá trị cũ.
- Environment variable bị thiếu hoặc chứa hostname không đúng.

Kiểm tra theo thứ tự:

1. Đọc URI cuối cùng mà Spring client đang sử dụng, nhưng không log credential.
2. Xác minh hostname có resolve được từ chính môi trường chạy ứng dụng.
3. Kiểm tra port Elasticsearch HTTP endpoint.
4. Kiểm tra container/service có đang chạy và lắng nghe port không.
5. Kiểm tra network policy, firewall, proxy hoặc service mesh.
6. Với Testcontainers, lấy host và mapped port từ container fixture thay vì hard-code `localhost:9200`.

Ví dụ cấu hình endpoint:

~~~yaml
spring:
  elasticsearch:
    uris: http://elasticsearch:9200
~~~

Tên `elasticsearch` chỉ đúng nếu DNS/service discovery trong môi trường hiện tại resolve được tên đó. Không sao chép nguyên hostname Docker Compose sang Kubernetes nếu service name khác.

### Connection refused

Dấu hiệu:

~~~text
java.net.ConnectException: Connection refused
~~~

Khác với DNS failure, hostname có thể đã resolve thành công nhưng không có process chấp nhận kết nối ở địa chỉ/port đó. Kiểm tra Elasticsearch đã khởi động xong chưa, port mapping, bind address và health/readiness.

Trong container orchestration, process có thể đang khởi động nhưng ứng dụng bắt đầu gửi request quá sớm. Dùng readiness check và retry khởi tạo có giới hạn thay vì vòng lặp vô hạn.

## 4. Timeout: connect timeout và socket/read timeout

Không phải timeout nào cũng có cùng nguyên nhân.

| Loại timeout | Giai đoạn | Hướng điều tra |
|---|---|---|
| Connect timeout | Mở kết nối TCP | Network, DNS, firewall, endpoint không phản hồi |
| TLS handshake timeout | Thương lượng TLS | Certificate chain, proxy, handshake, server load |
| Socket/read timeout | Chờ response sau khi gửi request | Query/aggregation nặng, shard chậm, cluster quá tải |
| Application deadline | Toàn bộ request vượt thời gian service cho phép | Tổng thời gian các bước, retry, downstream |

Tăng timeout có thể hữu ích khi workload hợp lệ nhưng cần thời gian lâu hơn. Tuy nhiên, tăng timeout không sửa được query kém hiệu quả hoặc cluster đang quá tải.

Ví dụ một request search chạy 20 giây có thể do:

- Query quét quá nhiều document.
- Wildcard/prefix query trên field không phù hợp.
- Sort trên field có chi phí cao.
- Aggregation nhiều bucket.
- Một shard đang mất cân bằng hoặc quá tải.
- Elasticsearch đang merge segment hoặc GC.
- Network/proxy giữ kết nối chậm.

Ghi nhận thời gian phía ứng dụng và trường `took` trong Elasticsearch response để phân biệt thời gian server xử lý với tổng latency qua network/client.

## 5. TLS: certificate, CA và hostname

Khi endpoint dùng HTTPS, client phải xác minh certificate của server. Các lỗi thường gặp:

~~~text
javax.net.ssl.SSLHandshakeException
sun.security.provider.certpath.SunCertPathBuilderException:
  unable to find valid certification path to requested target
~~~

Dấu hiệu này thường cho biết JVM không xây dựng được certificate chain tới CA được tin cậy.

Kiểm tra:

- Ứng dụng có trust CA ký HTTP certificate của Elasticsearch không?
- Certificate còn hạn không?
- Server có gửi đủ intermediate certificate không?
- URI dùng hostname/IP có khớp Subject Alternative Name (SAN) không?
- Client có đang trust nhầm certificate transport nội bộ thay vì HTTP endpoint không?
- Test container có sinh certificate mới nhưng client vẫn dùng truststore cũ không?

Ví dụ hostname mismatch:

~~~text
No subject alternative names matching IP address 127.0.0.1 found
~~~

CA đúng vẫn chưa đủ nếu certificate không chứa hostname/IP mà client gọi. Hãy sửa SAN hoặc dùng hostname phù hợp. Không tắt hostname verification hoặc dùng trust-all manager để làm test chạy qua.

### Phân biệt TLS với authentication

- TLS handshake lỗi: thường chưa tới bước Elasticsearch xác thực HTTP credential.
- HTTP 401: TLS đã thiết lập và server từ chối credential.
- HTTP 403: credential đã được nhận diện nhưng không đủ quyền cho hành động.

Đừng thay password để xử lý lỗi PKIX; đừng thay truststore để xử lý HTTP 403.

## 6. Xác thực: HTTP 401

HTTP 401 thường chỉ ra client chưa cung cấp credential hợp lệ hoặc credential không còn hiệu lực.

Nguyên nhân:

- Username/password sai.
- API key bị thu hồi, hết hạn hoặc gửi sai định dạng.
- Ứng dụng đang dùng secret của environment khác.
- Header Authorization bị proxy/gateway loại bỏ.
- Client configuration không gắn authentication vào đúng transport.
- Credential đã rotate nhưng application instance cũ chưa reload.

Ví dụ lỗi:

~~~json
{
  "error": {
    "type": "security_exception",
    "reason": "unable to authenticate user [products-search-service]"
  },
  "status": 401
}
~~~

Cách xử lý:

1. Xác định identity của credential đang dùng, không in secret ra log.
2. Kiểm tra secret source, version và thời điểm rotate.
3. Kiểm tra Basic Auth hay API key được cấu hình đúng cơ chế.
4. Kiểm tra header có tới Elasticsearch qua proxy không.
5. Dùng endpoint authenticate bằng đúng credential trong môi trường kiểm thử.
6. Xác nhận mọi replica/pod đã nhận secret mới.

Với API key, Elasticsearch REST API dùng header dạng:

~~~http
Authorization: ApiKey BASE64_ENCODED_ID_AND_KEY
~~~

Nếu API tạo key đã trả về trường `encoded`, dùng đúng giá trị đó. Không tự encode lại một giá trị đã được encode hoặc log header này.

401 thường không phải lỗi retryable. Retry cùng username/password/API key sẽ tiếp tục thất bại cho đến khi credential được sửa hoặc rotate.

## 7. Phân quyền: HTTP 403

HTTP 403 thường có nghĩa identity đã được xác thực nhưng role không cho phép hành động.

Ví dụ:

~~~json
{
  "error": {
    "type": "security_exception",
    "reason": "action [indices:data/read/search] is unauthorized for user [products-writer]"
  },
  "status": 403
}
~~~

Kiểm tra:

- Role có privilege phù hợp với API không?
- Index pattern có khớp index thực tế sau khi resolve alias không?
- Request có truy cập nhiều index không?
- Bulk có chứa action create, index, update hoặc delete khác nhau không?
- Client có cần `view_index_metadata` cho một thao tác metadata riêng không?
- Alias có trỏ sang index version mới chưa được role cho phép không?
- API cần cluster privilege hay index privilege?

Ví dụ search API cần `read`; writer cần privilege ghi tương ứng; migration job có thể cần `manage` hoặc privilege alias/index cụ thể. `write` không tự động đồng nghĩa với quyền quản trị index hoặc cluster.

Không giải quyết 403 bằng cách cấp `all` cho service. Xác định action bị từ chối rồi thêm đúng privilege trên đúng index pattern. Dùng API kiểm tra quyền hoặc test bằng chính API key của service.

## 8. Kiểm tra identity và privilege đang hiệu lực

Có thể dùng các Elasticsearch Security APIs trong môi trường test/staging:

~~~http
GET /_security/_authenticate
~~~

API này cho biết identity và role được Elasticsearch nhận diện cho request hiện tại.

Kiểm tra quyền:

~~~http
POST /_security/user/_has_privileges
Content-Type: application/json

{
  "cluster": [],
  "index": [
    {
      "names": ["products-v2"],
      "privileges": ["read", "write"]
    }
  ]
}
~~~

Dùng credential của chính service cần chẩn đoán. Nếu kiểm tra bằng admin user, kết quả không phản ánh quyền thực tế của Search API hoặc Writer.

Cũng cần xác nhận index pattern khớp backing index. Một role có `read` trên `products-v1` nhưng alias hiện đã chuyển sang `products-v2` có thể tạo ra lỗi 403 sau deployment.

## 9. Mapping: mapper_parsing_exception

Mapping mô tả kiểu và cách index field. Khi source gửi giá trị không tương thích với mapping, Elasticsearch có thể trả HTTP 400 với lỗi như `mapper_parsing_exception`.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "price": {
        "type": "double"
      },
      "createdAt": {
        "type": "date"
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

Document gửi lên:

~~~json
{
  "productId": "P-1001",
  "price": "one million",
  "createdAt": "yesterday",
  "status": "PUBLISHED"
}
~~~

Giá trị `price` và `createdAt` không phù hợp với kiểu field đã khai báo. Elasticsearch có thể từ chối document.

Ví dụ response:

~~~json
{
  "error": {
    "type": "mapper_parsing_exception",
    "reason": "failed to parse field [price] of type [double]",
    "caused_by": {
      "type": "number_format_exception",
      "reason": "For input string: \"one million\""
    }
  },
  "status": 400
}
~~~

Đọc cả `reason` và `caused_by`; nguyên nhân cụ thể thường nằm trong cause chain. Không chỉ ghi log dòng đầu `mapper_parsing_exception` rồi bỏ qua field/value gây lỗi.

### Các nguyên nhân mapping phổ biến

- Giá trị số được gửi dưới dạng chuỗi không chuyển đổi được.
- Ngày không khớp format được khai báo.
- Object được gửi vào field scalar hoặc ngược lại.
- Field đã được index với kiểu khác từ trước.
- Mapping `dynamic: strict` từ chối field mới.
- Nested/object path không đúng cấu trúc.
- Giá trị vượt giới hạn hoặc định dạng không hợp lệ.

## 10. strict mapping và field không được khai báo

Nếu mapping dùng:

~~~json
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      }
    }
  }
}
~~~

Document sau có field `supplierCode` chưa được khai báo:

~~~json
{
  "productId": "P-1001",
  "name": "Keyboard",
  "supplierCode": "SUP-01"
}
~~~

Elasticsearch có thể trả `strict_dynamic_mapping_exception`. Cách xử lý:

1. Xác định field có thực sự thuộc schema document không.
2. Nếu hợp lệ, cập nhật mapping/index template trước khi ghi dữ liệu.
3. Nếu field không nên tồn tại, sửa mapper/DTO để không gửi field đó.
4. Nếu mapping cũ không tương thích với kiểu mới, tạo index version mới và reindex theo kế hoạch.

Không bật dynamic mapping vô hạn chỉ để loại bỏ lỗi. Điều đó có thể tạo hàng nghìn field, gây mapping explosion và làm cluster khó quản lý.

## 11. Mapping type không thể đổi trực tiếp tùy ý

Một lỗi thường gặp là index đã có field `price` kiểu `text`, sau đó ứng dụng muốn đổi sang `double`.

Mapping của field hiện hữu thường không thể đổi kiểu tại chỗ theo cách an toàn. Cập nhật mapping chỉ thêm field hoặc thay đổi một số thuộc tính được hỗ trợ; đổi kiểu dữ liệu cần tạo index mới với mapping đúng và reindex/transform dữ liệu.

Quy trình khái quát:

~~~text
products-v1 (price: text)
        |
        v
Create products-v2 (price: double)
        |
        v
Reindex / transform source data
        |
        v
Validate documents and queries
        |
        v
Switch products alias to products-v2
~~~

Nếu dữ liệu cũ có giá trị không parse được thành số, cần làm sạch hoặc định nghĩa cách xử lý trước khi reindex. Không để migration thất bại giữa chừng mà không có báo cáo document lỗi.

## 12. Lỗi mapping ở Spring Data converter

Spring Data Elasticsearch chuyển entity Java thành Elasticsearch document qua mapping metadata và converter. Lỗi có thể xảy ra ở hai phía:

- Trước khi gửi request: converter không chuyển đổi được kiểu Java.
- Sau khi gửi request: Elasticsearch từ chối source vì mapping hoặc dữ liệu không hợp lệ.

Ví dụ field Java:

~~~java
@Field(type = FieldType.Double)
private BigDecimal price;
~~~

Nếu ứng dụng có custom converter hoặc field format riêng, cần xác nhận giá trị JSON thực tế được gửi có tương thích với mapping Elasticsearch không.

Không giả định annotation trên entity tự động sửa mapping đã tồn tại trên cluster. Mapping thật cần được kiểm tra ở index/alias đích:

~~~http
GET /products/_mapping
~~~

Với index theo version, kiểm tra cả backing index mà alias đang trỏ tới. Entity annotation và mapping trên cluster có thể lệch nhau nếu index được tạo trước khi code thay đổi.

## 13. Phân loại lỗi Query DSL: parsing_exception

Nếu JSON Query DSL sai cấu trúc hoặc dùng operator không hỗ trợ field, Elasticsearch thường trả HTTP 400 với `parsing_exception` hoặc lỗi liên quan.

Ví dụ query sai:

~~~json
{
  "query": {
    "term": {
      "status": {
        "valuee": "PUBLISHED"
      }
    }
  }
}
~~~

Tên thuộc tính `valuee` không hợp lệ trong vị trí đó. Elasticsearch có thể trả lỗi parse thay vì trả 0 hits.

Ví dụ response:

~~~json
{
  "error": {
    "type": "parsing_exception",
    "reason": "[term] query does not support [valuee]"
  },
  "status": 400
}
~~~

Hướng xử lý:

- Kiểm tra cấu trúc JSON và tên property.
- Xác định query builder tạo đúng DSL không.
- Ghi request body đã loại bỏ dữ liệu nhạy cảm ở môi trường test nếu cần.
- Dùng integration test với mapping thực tế.
- Không sửa dữ liệu index nếu lỗi nằm ở query syntax.

Với Spring Data `NativeQuery`, hãy kiểm tra phần query được build và kiểu query builder đang dùng. Không trộn builder của Spring Data, Elasticsearch Java API Client và các API cũ không tương thích.

## 14. Field không phù hợp với loại query

Một query có thể đúng cú pháp nhưng sai với mapping hoặc semantics field.

Ví dụ:

- `term` trên field `text` khi cần full-text search.
- `match` trên field `keyword` khi mong muốn phân tích ngôn ngữ.
- Sort trên field `text` không có fielddata.
- Aggregation trên field `text` mà không có keyword subfield.
- Range query với date format không tương thích.
- Query vào nested field nhưng không dùng `nested` query.
- Dùng field name cũ sau khi mapping đổi.

Ví dụ field:

~~~json
{
  "name": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword"
      }
    }
  }
}
~~~

Full-text query:

~~~json
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Exact match hoặc sort/aggregation thường dùng `name.keyword`:

~~~json
{
  "query": {
    "term": {
      "name.keyword": "Wireless Keyboard"
    }
  }
}
~~~

Nếu sort trên `name` kiểu text, Elasticsearch có thể báo fielddata disabled. Dùng keyword subfield cho exact sort/aggregation, hoặc thiết kế mapping phù hợp. Không bật fielddata cho text một cách tùy tiện vì có thể tiêu thụ nhiều heap.

## 15. Query hợp lệ nhưng trả về 0 hits không phải exception

Một response 0 hits thường có nghĩa query hợp lệ nhưng không tìm thấy document phù hợp. Đây là tình huống khác hoàn toàn với parsing error hoặc connection failure.

Các nguyên nhân:

- Term không khớp chính xác.
- Analyzer chuyển token khác dự kiến.
- Field path sai nhưng query không báo lỗi trong trường hợp đó.
- Filter theo tenant/status loại hết document.
- Search vào nhầm alias/index.
- Document chưa refresh nên chưa xuất hiện trong search.
- Giá trị lưu khác kiểu/case/format so với query.

Kiểm tra:

1. Xác minh index/alias đích.
2. Đọc document theo ID nếu biết ID.
3. Kiểm tra mapping field.
4. Kiểm tra query bằng Dev Tools hoặc integration test.
5. Dùng `_explain` cho một document cụ thể nếu cần hiểu scoring/matching.
6. Kiểm tra refresh visibility nếu vừa ghi document.

Không xử lý 0 hits bằng cách retry liên tục hoặc tăng timeout. Trước hết xác định query có thực sự đúng với dữ liệu.

## 16. Lỗi index hoặc document không tồn tại

HTTP 404 có thể xuất hiện trong nhiều tình huống:

- Index/alias không tồn tại.
- Update theo ID nhưng document chưa tồn tại.
- Document bị xóa giữa lúc ứng dụng đọc và cập nhật.
- Alias trỏ tới index đã bị xóa hoặc chưa được tạo.
- Request dùng sai index name.

Phân biệt lỗi index missing với document missing. Cách xử lý khác nhau:

- Index chưa tồn tại: kiểm tra migration/index provisioning và alias.
- Document chưa tồn tại: xem nghiệp vụ cần create, upsert hay trả not found.
- Document bị xóa đồng thời: áp dụng chính sách concurrency và retry phù hợp.
- Alias sai: sửa deployment/lifecycle thay vì tạo index tùy tiện từ runtime service.

Không bật auto-create index để che giấu lỗi triển khai nếu index cần mapping/settings/alias được quản lý rõ ràng.

## 17. Conflict: HTTP 409

409 thường gặp khi:

- Dùng create operation với ID đã tồn tại.
- Update gặp version conflict.
- OCC với `_seq_no` và `_primary_term` không còn khớp.

Phân biệt:

| Trường hợp | Ý nghĩa | Hướng xử lý |
|---|---|---|
| CREATE trùng ID | Document đã được tạo | Xác minh duplicate có cùng event/payload không |
| Update conflict | Document thay đổi đồng thời | Đọc lại, merge hoặc retry có giới hạn |
| OCC token cũ | Client đang ghi dựa trên phiên bản cũ | Không retry nguyên token; đọc lại và quyết định |
| Duplicate event | Consumer nhận lại message | Idempotency key/version guard |

Không coi mọi 409 là thành công. Nếu cùng ID nhưng payload khác, có thể là collision hoặc producer bug cần điều tra.

## 18. Lỗi quá tải: HTTP 429 và rejection

Khi Elasticsearch không thể nhận thêm công việc ở một thread pool, request có thể bị từ chối với `es_rejected_execution_exception` hoặc HTTP 429.

Nguyên nhân thường gặp:

- Bulk batch quá lớn.
- Quá nhiều request đồng thời.
- Search/aggregation nặng.
- Hot shard hoặc hot index.
- Cluster thiếu CPU/heap hoặc thread pool queue đầy.
- Consumer tăng concurrency vượt khả năng cluster.

Cách xử lý:

1. Giảm số request đồng thời.
2. Giảm bulk batch size nếu item/byte quá lớn.
3. Retry có exponential backoff và jitter.
4. Đặt giới hạn retry và deadline.
5. Theo dõi thread pool rejection, CPU, heap, GC và shard distribution.
6. Điều tra query hoặc mapping gây tải cao.

Không retry ngay liên tục; retry storm có thể làm cluster quá tải hơn.

## 19. Search timeout và partial shard failure

Một search response có thể có HTTP status thành công nhưng chứa dấu hiệu kết quả chưa đầy đủ:

~~~json
{
  "took": 12000,
  "timed_out": true,
  "_shards": {
    "total": 8,
    "successful": 7,
    "skipped": 0,
    "failed": 1,
    "failures": [
      {
        "shard": 3,
        "index": "products-v2",
        "reason": {
          "type": "query_shard_exception",
          "reason": "..."
        }
      }
    ]
  },
  "hits": {
    "total": {
      "value": 1000,
      "relation": "eq"
    },
    "hits": []
  }
}
~~~

Các trường cần kiểm tra:

- `timed_out`: search có vượt timeout không.
- `_shards.total`: số shard được nhắm tới.
- `_shards.successful`: số shard trả kết quả.
- `_shards.failed`: số shard lỗi.
- `_shards.failures`: chi tiết từng shard failure.
- `took`: thời gian Elasticsearch xử lý request.

Không chỉ kiểm tra HTTP 200. Một search có shard failure có thể trả kết quả một phần. Với API yêu cầu dữ liệu đầy đủ, ứng dụng cần xem partial result là lỗi hoặc trạng thái không hoàn chỉnh theo hợp đồng API.

## 20. Đọc cấu trúc Elasticsearch error response

Lỗi server thường có cấu trúc:

~~~json
{
  "error": {
    "root_cause": [
      {
        "type": "mapper_parsing_exception",
        "reason": "failed to parse field [price]"
      }
    ],
    "type": "mapper_parsing_exception",
    "reason": "failed to parse field [price]",
    "caused_by": {
      "type": "number_format_exception",
      "reason": "..."
    }
  },
  "status": 400
}
~~~

Các trường quan trọng:

| Field | Ý nghĩa |
|---|---|
| `error.type` | Loại lỗi Elasticsearch ở lớp ngoài |
| `error.reason` | Mô tả chính của lỗi |
| `error.root_cause` | Các nguyên nhân gốc mà server báo |
| `error.caused_by` | Lỗi lồng bên dưới |
| `error.failed_shards` hoặc `failures` | Thông tin lỗi shard trong các response liên quan |
| `status` | HTTP status |

Trong exception chain Java, có thể có thêm wrapper của Spring Data hoặc transport. Hãy giữ exception gốc khi log và xử lý; đừng chỉ log `getMessage()` của exception ngoài cùng nếu nó không chứa đủ thông tin.

Không parse message text bằng một chuỗi cố định nếu có thể lấy status/error type từ structured response. Message có thể thay đổi giữa phiên bản Elasticsearch.

## 21. Exception translation trong Spring Data Elasticsearch

Khi dùng repository hoặc `ElasticsearchOperations`, lỗi có thể được chuyển thành exception thuộc hệ sinh thái Spring DAO hoặc exception của Elasticsearch client, tùy API, phiên bản và thời điểm lỗi.

Phân biệt:

- Lỗi xảy ra trước khi HTTP request gửi đi: thường là exception network/TLS từ client.
- Server trả HTTP error: client có thể tạo exception mang status và response body.
- Spring Data repository/operations: có thể dịch hoặc bọc exception theo cơ chế exception translation.
- Lỗi trong code ứng dụng: validation, mapping DTO hoặc business rule có thể phát sinh trước khi gọi Elasticsearch.

Không dựa vào một tên exception duy nhất cho mọi version. Nên giữ cause chain và phân loại theo các đặc tính ổn định: root cause type, HTTP status, Elasticsearch error type, index và operation.

Ví dụ ghi log có giữ stack trace:

~~~java
try {
    operations.save(document, IndexCoordinates.of("products"));
} catch (RuntimeException ex) {
    log.error(
            "Elasticsearch write failed: operation={}, index={}, documentId={}",
            "save",
            "products",
            document.getId(),
            ex
    );
    throw ex;
}
~~~

Đây là mẫu quan sát lỗi, không phải xử lý nghiệp vụ hoàn chỉnh. Không log toàn bộ document nếu source chứa email, số điện thoại, token hoặc dữ liệu nhạy cảm. Giữ exception làm throwable cuối cùng để logger ghi stack trace và cause chain.

## 22. Phân loại lỗi ở tầng service

Có thể tạo một lớp adapter để chuyển exception kỹ thuật thành lỗi ứng dụng có ngữ nghĩa:

~~~java
public enum ElasticsearchFailureCategory {
    CONNECTION,
    TLS,
    AUTHENTICATION,
    AUTHORIZATION,
    MAPPING,
    QUERY,
    NOT_FOUND,
    CONFLICT,
    OVERLOADED,
    TIMEOUT,
    PARTIAL_RESULT,
    UNKNOWN
}
~~~

Service adapter có thể nhận operation context và thông tin lỗi đã trích xuất:

~~~java
public record ElasticsearchFailure(
        ElasticsearchFailureCategory category,
        String operation,
        String index,
        Integer httpStatus,
        String errorType,
        String message
) {
}
~~~

Việc trích xuất status/error type nên được triển khai theo client version đang dùng. Tránh tạo một parser phụ thuộc vào câu chữ tiếng Anh của message.

Lợi ích của lớp phân loại:

- Controller không cần biết chi tiết Elasticsearch transport.
- Retry policy có thể dựa trên category.
- Metrics có thể đếm lỗi theo loại.
- API response có thể trả mã lỗi ổn định cho client.
- Có thể thay client/version mà ít ảnh hưởng business service.

Không trả stack trace, cluster node address nội bộ, request body nhạy cảm hoặc credential ra HTTP response của API công khai.

## 23. Chính sách retry theo nhóm lỗi

Không phải lỗi nào cũng retry được.

| Nhóm lỗi | Retry? | Lý do / hành động |
|---|---|---|
| DNS tạm thời, connection reset | Có giới hạn | Có thể phục hồi sau khi network/service ổn định |
| Connect timeout | Có giới hạn | Xác minh endpoint và readiness trước |
| TLS trust/hostname error | Không | Sửa CA, certificate hoặc hostname |
| HTTP 401 | Không | Sửa/rotate credential |
| HTTP 403 | Không | Sửa role/privilege |
| HTTP 400 mapping/query | Không | Sửa dữ liệu, mapping hoặc request |
| HTTP 404 | Theo nghiệp vụ | Kiểm tra index/document và upsert semantics |
| HTTP 409 | Có điều kiện | Đọc lại/đối soát; không retry mù |
| HTTP 429 | Có giới hạn | Backoff, giảm concurrency/batch |
| HTTP 502/503/504 | Có giới hạn | Lỗi tạm thời có thể phục hồi |
| Search timeout | Có điều kiện | Tối ưu query hoặc điều chỉnh timeout |
| Partial shard failure | Có điều kiện | Kiểm tra shard failure và yêu cầu completeness |

Với write request bị timeout, kết quả có thể chưa xác định: Elasticsearch có thể đã commit nhưng response bị mất. Retry chỉ an toàn nếu thao tác idempotent hoặc có ID/version/idempotency key bảo vệ.

Ví dụ exponential backoff có jitter:

~~~java
Duration baseDelay = Duration.ofMillis(100);
Duration maxDelay = Duration.ofSeconds(5);

// Pseudocode:
// delay = min(maxDelay, baseDelay * 2^attempt) + random jitter
// Retry chỉ khi FailureCategory thuộc nhóm retryable.
~~~

Dùng retry library có giới hạn attempt, deadline và cancellation nếu ứng dụng cần retry tự động. Không viết vòng lặp retry vô hạn quanh repository call.

## 24. Tránh retry lặp với bulk

Bulk request có thể thành công một phần. Nếu một item lỗi mapping nhưng các item khác đã ghi thành công, gửi lại toàn bộ batch có thể tạo conflict hoặc áp dụng lại script update.

Quy trình đúng:

1. Kiểm tra trường `errors`.
2. Duyệt từng item trong response.
3. Ghi nhận item thành công.
4. Phân loại lỗi của item thất bại.
5. Chỉ retry item có thể retry.
6. Giữ nguyên document ID/event ID và version.
7. Đưa lỗi vĩnh viễn vào DLQ hoặc báo lỗi dữ liệu.

Đối với bulk update dùng script cộng dồn, retry item sau timeout cần có deduplication. Một request có thể đã cập nhật document dù client không nhận response.

## 25. Phân biệt lỗi mapping với lỗi query

Hai lỗi này thường bị nhầm vì đều có thể liên quan field name/type.

| Mapping/write failure | Query failure |
|---|---|
| Thường xảy ra khi index/create/update document | Xảy ra khi search request được parse hoặc thực thi |
| Source value không khớp mapping | Query operator/field không phù hợp |
| `mapper_parsing_exception` | `parsing_exception`, `query_shard_exception` hoặc lỗi execution khác |
| Kiểm tra JSON source, Java converter, mapping | Kiểm tra Query DSL, mapping, analyzer, sort/aggregation |
| Có thể cần sửa document hoặc reindex | Có thể cần sửa query hoặc mapping hỗ trợ use case |

Ví dụ cùng một field `price`:

- Khi ghi: gửi chuỗi `"free"` vào field `double` gây mapping error.
- Khi search: dùng range query trên field `price` chưa được mapping numeric có thể gây query error hoặc không có semantics mong muốn.
- Khi aggregation: dùng field không có doc values hoặc field `text` có thể báo lỗi fielddata.

Luôn xác định request thất bại là request ghi hay đọc trước khi thay đổi mapping.

## 26. Các API chẩn đoán Elasticsearch hữu ích

Khi đã có error type/index/shard, dùng API phù hợp thay vì chạy mọi lệnh quản trị.

### Kiểm tra cluster health

~~~http
GET /_cluster/health
~~~

Cho biết trạng thái cluster và số shard active/relocating/unassigned.

### Kiểm tra node

~~~http
GET /_cat/nodes?v
~~~

Có thể xem node, heap, CPU và role ở dạng bảng. Cần quyền monitor phù hợp.

### Kiểm tra index

~~~http
GET /_cat/indices/products-*?v
~~~

Xem health, số document, dung lượng và trạng thái index.

### Kiểm tra mapping

~~~http
GET /products/_mapping
~~~

Xác minh field type, nested/object, analyzer và dynamic settings.

### Giải thích allocation của shard

~~~http
GET /_cluster/allocation/explain
Content-Type: application/json

{
  "index": "products-v2",
  "shard": 0,
  "primary": true
}
~~~

Dùng khi shard unassigned hoặc không phân bổ được.

### Kiểm tra tasks

~~~http
GET /_tasks?detailed=true&actions=*search
~~~

Hữu ích khi cần xác định search task dài đang chạy. Một số API yêu cầu privilege monitor/cluster phù hợp.

Không cấp quyền quản trị cluster cho runtime service chỉ để nó tự chạy tất cả diagnostic APIs. Thực hiện kiểm tra vận hành bằng identity giám sát riêng.

## 27. Log có cấu trúc và correlation ID

Mỗi lỗi nên gắn với operation context để nối log ứng dụng và log Elasticsearch.

Các field hữu ích:

- `traceId` hoặc `correlationId`.
- Operation: search, index, update, bulk, delete.
- Index/alias.
- Document ID nếu không nhạy cảm.
- HTTP status.
- Elasticsearch error type.
- Duration.
- Retry attempt.
- Result category.
- Shard failure count nếu có.

Ví dụ log dạng JSON:

~~~json
{
  "level": "ERROR",
  "message": "Elasticsearch operation failed",
  "traceId": "trace-7f31",
  "operation": "bulk",
  "index": "products-v2",
  "status": 400,
  "errorType": "mapper_parsing_exception",
  "failureCategory": "MAPPING",
  "retryAttempt": 0,
  "durationMs": 84
}
~~~

Không log:

- Password, API key hoặc Authorization header.
- Private key, keystore password.
- Toàn bộ document source khi chứa dữ liệu cá nhân.
- Query body có chứa thông tin nhạy cảm.
- URL chứa credential hoặc secret query parameter.

Nếu cần lưu request mẫu để điều tra, hãy redact field nhạy cảm và giới hạn quyền truy cập log.

## 28. Metrics và cảnh báo

Metrics nên dùng label có cardinality thấp. Không dùng document ID, user ID hoặc query string làm metric label vì số lượng giá trị có thể tăng không giới hạn.

Một số metrics:

| Metric | Mục đích |
|---|---|
| Request count theo operation | Biết workload search/write/bulk |
| Error count theo category/status | Phát hiện lỗi kết nối, auth, mapping, query |
| Request latency p50/p95/p99 | Theo dõi độ trễ |
| Timeout count | Phát hiện network hoặc query chậm |
| Retry count | Phát hiện dependency chập chờn hoặc overload |
| Bulk item failure count | Phát hiện partial failure |
| Shard failure count | Phát hiện kết quả search không đầy đủ |
| 401/403 count | Phát hiện credential/role regression |
| 429/rejection count | Phát hiện quá tải |

Cảnh báo theo xu hướng và ngưỡng có ý nghĩa. Một 401 duy nhất sau credential rotation có thể là lỗi cấu hình; 401 tăng đột biến trên tất cả replica cần điều tra secret deployment hoặc identity provider.

Không chỉ theo dõi HTTP 5xx. Mapping/query 400 có thể tăng sau một lần deploy và làm ingestion/search thất bại dù cluster vẫn khỏe.

## 29. Trả lỗi phù hợp từ REST API của ứng dụng

Không nên trả nguyên Elasticsearch exception cho người dùng cuối. Controller advice có thể ánh xạ failure category sang mã lỗi ứng dụng:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    ResponseEntity<ApiError> notFound(ProductNotFoundException ex) {
        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(new ApiError("PRODUCT_NOT_FOUND"));
    }

    @ExceptionHandler(SearchUnavailableException.class)
    ResponseEntity<ApiError> unavailable(SearchUnavailableException ex) {
        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ApiError("SEARCH_UNAVAILABLE"));
    }
}
~~~

Các kiểu exception ở đây là domain exception của ứng dụng, không phải tên exception cố định của Elasticsearch. Service adapter chịu trách nhiệm chuyển lỗi kỹ thuật sang loại lỗi nghiệp vụ phù hợp.

Ví dụ:

- Search dependency không khả dụng: có thể trả 503.
- Request client sai filter/query do API contract: trả 400.
- User không có quyền: trả 403 ở lớp API.
- Document nghiệp vụ không tồn tại: trả 404.
- Mapping lỗi do bug dữ liệu nội bộ: trả lỗi server, ghi log và alert; không tiết lộ chi tiết cluster cho client.

Nếu search trả partial result, API cần quy định rõ có cho phép trả dữ liệu một phần hay coi là unavailable. Không âm thầm biến shard failure thành danh sách rỗng.

## 30. Quy trình chẩn đoán theo từng bước

Khi nhận báo lỗi từ môi trường test hoặc production:

1. Ghi nhận operation, index/alias, thời điểm và trace ID.
2. Xác định có HTTP response hay lỗi trước HTTP.
3. Nếu không có response, kiểm tra DNS, host/port, TCP, TLS và timeout.
4. Nếu 401, xác minh credential và identity.
5. Nếu 403, xác minh privilege và index pattern.
6. Nếu 400 khi ghi, đọc `mapper_parsing_exception`, `caused_by` và mapping.
7. Nếu 400 khi search, đọc `parsing_exception`/`query_shard_exception` và query DSL.
8. Nếu 404, phân biệt index missing với document missing.
9. Nếu 409, xác định create duplicate hay optimistic conflict.
10. Nếu 429/5xx, kiểm tra tải, thread pool, shard và retry policy.
11. Với search 200, vẫn kiểm tra `timed_out` và `_shards.failed`.
12. Thu thập cluster health, index mapping hoặc task detail khi cần.
13. Xác định lỗi có retryable không và thao tác có idempotent không.
14. Sửa đúng lớp nguyên nhân, chạy integration test tái hiện.
15. Theo dõi metrics/log sau khi triển khai để xác nhận lỗi không tái diễn.

## 31. Ma trận test lỗi nên có

Integration test nên xác nhận cả tình huống thành công và lỗi có chủ đích.

| Nhóm | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Kết nối | Hostname sai | Lỗi DNS được phân loại là CONNECTION |
| Kết nối | Port chưa lắng nghe | Connection refused |
| Kết nối | Server chậm | Timeout được ghi nhận |
| TLS | CA không được trust | TLS handshake thất bại |
| TLS | Hostname không khớp SAN | Hostname verification thất bại |
| Authentication | Password sai | 401 |
| Authentication | API key bị thu hồi | 401 |
| Authorization | Search user gọi write | 403 |
| Authorization | Writer gọi delete index | 403 |
| Mapping | Gửi chuỗi vào numeric field | 400 mapping error |
| Mapping | Field mới với dynamic strict | Strict mapping error |
| Mapping | Kiểu field cũ không tương thích | Reindex/migration cần thiết |
| Query | Query DSL sai | 400 parsing error |
| Query | Term không khớp | 0 hits, không phải exception |
| Query | Sort trên text không hỗ trợ | Query execution error |
| Index | Alias không tồn tại | 404/resource error |
| Update | Document missing | 404 hoặc upsert theo policy |
| Concurrency | Version cũ | 409 conflict |
| Capacity | Quá nhiều request | 429/rejection |
| Search | Một shard lỗi | Kiểm tra partial result |
| Search | Request timeout | `timed_out` hoặc timeout exception |

Không cần đưa mọi tình huống vào mỗi test class. Tách unit test cho exception classification, integration test với Elasticsearch container và secured test environment cho TLS/authentication/authorization.

## 32. Những lỗi thường gặp khi chẩn đoán

### Chỉ log exception ngoài cùng

Exception ngoài có thể chỉ là wrapper. Ghi stack trace và giữ cause chain để tìm root cause.

### Retry tất cả RuntimeException

Mapping sai, query sai, 401 và 403 không tự phục hồi. Retry vô ích làm tăng tải và che giấu lỗi.

### Nhầm 401 với 403

401 là authentication; 403 là authorization. Kiểm tra identity trước rồi mới kiểm tra role.

### Nhầm TLS với password

TLS handshake xảy ra trước HTTP authentication. PKIX/hostname lỗi cần sửa certificate/CA/SAN.

### Nhầm mapping error với query error

Mapping error thường xảy ra lúc ghi; query error xảy ra lúc parse hoặc thực thi search. Xác định operation trước khi sửa.

### Chỉ nhìn HTTP 200

Search có thể trả `timed_out: true` hoặc `_shards.failed > 0`. Kiểm tra response metadata.

### Coi 0 hits là lỗi hệ thống

0 hits có thể là kết quả hợp lệ. Kiểm tra query, analyzer, tenant filter và alias.

### Cấp quyền all để xử lý 403

Tìm privilege thiếu và cấp đúng index pattern. Không mở rộng quyền quản trị chỉ để sửa lỗi search/write.

### Tăng timeout thay vì tối ưu query

Timeout có thể là triệu chứng query nặng hoặc cluster quá tải. Đo `took`, shard và query cost trước.

### Log toàn bộ request/response

Payload có thể chứa dữ liệu cá nhân hoặc secret. Redact và chỉ log metadata cần thiết.

### Bỏ qua partial bulk failure

Một bulk request có thể thành công một phần. Kiểm tra từng item và retry có chọn lọc.

## Tài liệu tham khảo

- [Elasticsearch — Troubleshooting](https://www.elastic.co/guide/en/elasticsearch/reference/current/troubleshooting.html)
- [Elasticsearch — Error response](https://www.elastic.co/guide/en/elasticsearch/reference/current/rest-api-errors.html)
- [Elasticsearch — Security privileges](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-privileges.html)
- [Elasticsearch — Mapping](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html)
- [Elasticsearch — Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Elasticsearch — Cluster health API](https://www.elastic.co/guide/en/elasticsearch/reference/current/cluster-health.html)
- [Elasticsearch — Cat nodes API](https://www.elastic.co/guide/en/elasticsearch/reference/current/cat-nodes.html)
- [Elasticsearch — Index mapping API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-get-mapping.html)
- [Spring Data Elasticsearch — Reference documentation](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch.html)
- [Spring Framework — Data access exception translation](https://docs.spring.io/spring-framework/reference/data-access/dao.html)

## Kết luận

Hãy phân loại lỗi theo lớp trước khi sửa: DNS/TCP/TLS là lỗi kết nối; 401 là authentication; 403 là authorization; `mapper_parsing_exception` thường là dữ liệu không khớp mapping; `parsing_exception` hoặc `query_shard_exception` thường liên quan Query DSL hay thực thi query. Với search response, vẫn kiểm tra `timed_out` và `_shards.failed` dù HTTP status thành công. Trong Spring Data Elasticsearch, giữ exception cause chain, log operation/index/status/error type với correlation ID và không ghi secret hoặc toàn bộ source. Chỉ retry lỗi tạm thời có giới hạn; không retry mù mapping/query/auth errors hoặc write timeout không idempotent.
