# Tài khoản dịch vụ, API key và quyền tối thiểu

Ứng dụng Spring Data Elasticsearch cần một danh tính riêng để xác thực khi kết nối tới Elasticsearch. Danh tính này thường được gọi là tài khoản dịch vụ (service account), nhưng cần phân biệt user kỹ thuật do tổ chức quản lý với các built-in service account dành riêng cho thành phần Elastic Stack. Với ứng dụng nghiệp vụ, API key có phạm vi quyền giới hạn thường là lựa chọn phù hợp; trong một số môi trường, một user kỹ thuật riêng với role tối thiểu cũng có thể được sử dụng.

Mục tiêu bảo mật là để mỗi ứng dụng chỉ làm được những thao tác cần thiết trên đúng index hoặc data stream của nó. Một dịch vụ chỉ đọc catalog không cần quyền ghi; một worker chỉ index sự kiện không cần quyền xóa index hay quản lý user. Khi credential bị lộ, phạm vi thiệt hại vì thế cũng được giới hạn.

Bài này trình bày cách chọn danh tính, thiết kế role, tạo và sử dụng API key, cấu hình Spring Data Elasticsearch, quản lý secret và xoay vòng credential, cùng các cách kiểm chứng quyền và xử lý sự cố.

## 1. Danh tính kỹ thuật khi kết nối Elasticsearch

### 1.1. Vì sao không dùng tài khoản cá nhân?

Nếu nhiều ứng dụng dùng chung tài khoản cá nhân hoặc tài khoản quản trị, rất khó xác định request nào thuộc ứng dụng nào. Khi nhân sự thay đổi, credential có thể phải đổi ở nhiều nơi. Một thao tác vô tình chạy với quyền rộng cũng có thể tác động tới dữ liệu ngoài phạm vi service.

Tài khoản riêng cho workload giúp:

- Xác định ứng dụng hoặc job nào đang gọi Elasticsearch.
- Cấp quyền độc lập theo môi trường và chức năng.
- Thu hồi credential của một service mà không ảnh hưởng service khác.
- Theo dõi hoạt động và điều tra sự cố dễ hơn.
- Xoay vòng secret theo lịch hoặc khi có dấu hiệu lộ lọt.
- Giới hạn tác động nếu credential bị sử dụng trái phép.

Mỗi workload quan trọng nên có danh tính riêng. Ví dụ catalog-api, catalog-indexer và reporting-worker có thể cần các quyền khác nhau dù cùng đọc hoặc ghi một cụm Elasticsearch.

### 1.2. Phân biệt các loại danh tính

| Loại danh tính | Mục đích | Khi nào phù hợp |
|---|---|---|
| Tài khoản người dùng | Danh tính của con người | Quản trị, vận hành hoặc truy cập tương tác |
| User kỹ thuật (native/file realm) | Danh tính riêng của ứng dụng, gắn với role | Khi cần principal ổn định có role do tổ chức quản lý |
| Built-in service account của Elasticsearch | Danh tính dành riêng cho một số thành phần Elastic Stack | Khi thành phần được Elastic hỗ trợ yêu cầu service account đó |
| Service account token | Credential dùng để xác thực một built-in service account | Khi tích hợp đúng thành phần có hỗ trợ service token |
| API key | Credential có thể mang role descriptor giới hạn | Thường phù hợp cho ứng dụng hoặc integration gọi Elasticsearch |

Không nên gọi mọi user kỹ thuật là built-in service account. Elasticsearch có các service account tích hợp cho một số dịch vụ của Elastic Stack; đây là những principal được định nghĩa sẵn, không phải cơ chế để tự tạo tùy ý một service account mới cho mỗi microservice nghiệp vụ.

### 1.3. Khi nào dùng API key?

API key phù hợp khi cần credential riêng cho một workload và có thể gắn phạm vi quyền rõ ràng. Có thể tạo key với:

- Tên nhận diện workload và môi trường.
- Thời hạn hết hạn.
- Role descriptor chỉ cho phép các thao tác cần thiết.
- Metadata để lưu thông tin vận hành như owner hoặc ticket tham chiếu.

API key không tự động có quyền rộng hơn người tạo. Quyền hiệu lực của key bị giới hạn bởi quyền của principal tạo key và role descriptor được khai báo. Vì vậy, tạo key từ tài khoản quản trị rồi gán role descriptor rộng vẫn là thiết kế nguy hiểm; nên dùng quy trình provisioning có kiểm soát và quyền tạo key phù hợp.

### 1.4. Khi nào dùng built-in service account?

Built-in service account được dành cho thành phần Elastic Stack cụ thể, ví dụ một số thành phần Kibana hoặc Fleet. Nếu tài liệu triển khai của thành phần yêu cầu service token, hãy dùng đúng namespace/service identity được hỗ trợ.

Không dùng token của service account Kibana hoặc Fleet Server để xác thực một ứng dụng Spring nghiệp vụ không liên quan. Điều đó ghép hai vòng đời và phạm vi quyền khác nhau, đồng thời làm khó việc thu hồi hoặc điều tra.

### 1.5. Khi nào dùng user kỹ thuật riêng?

Một user kỹ thuật riêng có thể phù hợp khi tổ chức muốn quản lý role tập trung và dùng cùng một principal cho một workload trong thời gian dài. User nên:

- Có tên nhận diện rõ ứng dụng và môi trường.
- Không có quyền đăng nhập tương tác nếu không cần.
- Chỉ được gán role dành riêng cho workload.
- Không dùng chung với người vận hành hoặc ứng dụng khác.
- Có mật khẩu/credential được lưu trong secret manager và có quy trình xoay vòng.

Nếu ứng dụng cần credential có thể cấp và thu hồi độc lập mà không phải thay password user, API key thường thuận tiện hơn.

## 2. Mô hình Role-Based Access Control

### 2.1. Authentication và authorization là hai bước khác nhau

- **Authentication** xác định caller là ai: user, service account hoặc API key nào.
- **Authorization** xác định caller được làm gì trên cluster, index, data stream hoặc resource nào.

Một request có thể xác thực thành công nhưng vẫn bị từ chối vì thiếu privilege. Ngược lại, cấp role rộng không giúp được nếu credential sai hoặc đã bị thu hồi.

| Tình trạng | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| 401 Unauthorized | Không xác thực được credential | Header, secret, key hết hạn/đã revoke, TLS và endpoint |
| 403 Forbidden | Đã xác thực nhưng thiếu quyền hoặc bị policy chặn | Role, index pattern, cluster privilege, DLS/FLS |
| 404 Not Found | Resource hoặc index không tồn tại, tùy API | Index/alias/data stream và quyền nhìn thấy resource |
| 429 Too Many Requests | Quá tải hoặc giới hạn request | Không phải lỗi phân quyền; xem backoff/concurrency |

### 2.2. Role gồm cluster privilege và index privilege

Một role Elasticsearch có thể định nghĩa quyền ở nhiều phạm vi:

- cluster: thao tác cấp cluster, ví dụ một số tác vụ quản trị hoặc monitoring.
- indices: thao tác trên các index/data stream được chỉ định.
- applications: quyền cho các ứng dụng tích hợp cụ thể, nếu dùng.
- run_as: quyền impersonate user khác trong các use case được hỗ trợ.

Ứng dụng truy vấn và ghi document thường chỉ cần index privileges. Không cấp cluster privilege nếu service không thực sự gọi API cluster.

### 2.3. Chọn index privilege theo thao tác

Một số index privilege thường gặp:

| Privilege | Ý nghĩa khái quát | Use case |
|---|---|---|
| read | Đọc/search dữ liệu | API tìm kiếm, reporting |
| view_index_metadata | Xem metadata index cần thiết | Client cần đọc metadata/mapping hoặc một số thao tác kiểm tra |
| create_doc | Chỉ tạo document mới theo semantics được hỗ trợ | Event writer không cần ghi đè document hiện có |
| create | Tạo document/index operation theo privilege này | Workload cần create semantics |
| index | Ghi/index document | Indexer ghi hoặc thay thế document |
| write | Nhóm quyền ghi rộng hơn, gồm các thao tác ghi phổ biến | Service cần index/update/delete document |
| delete | Xóa document | Chỉ cấp khi nghiệp vụ thực sự cần |
| delete_index | Xóa index | Thường chỉ dành cho provisioning/admin job |
| manage | Quản lý index và nhiều thao tác quản trị index | Không cấp cho runtime service thông thường |

Tên và phạm vi privilege chi tiết có thể thay đổi theo phiên bản Elasticsearch. Kiểm tra Security privileges reference của phiên bản cluster trước khi triển khai.

Không cấp all hoặc manage chỉ để làm cho một lỗi 403 biến mất. Hãy xác định API nào bị từ chối và thêm privilege hẹp nhất đáp ứng use case.

### 2.4. Ví dụ phân quyền theo chức năng

Giả sử có ba workload:

| Workload | Đọc products | Ghi products | Xóa index | Quản lý security |
|---|---:|---:|---:|---:|
| catalog-api | Có | Không | Không | Không |
| catalog-indexer | Không hoặc chỉ đọc đối soát | Có | Không | Không |
| index-provisioner | Theo nhu cầu | Theo nhu cầu | Có khi triển khai | Chỉ khi có nhiệm vụ security riêng |

Tách provisioning khỏi runtime giúp API service không thể tự xóa index hoặc thay đổi mapping chỉ vì cần ghi document.

### 2.5. Không cấp quyền theo tên index quá rộng

Nếu ứng dụng chỉ dùng products-prod, đừng cấp quyền cho wildcard toàn cluster. Nếu cần nhiều index theo tenant hoặc version, hãy chọn pattern cụ thể như products-v3-* và xác nhận pattern không vô tình khớp index khác.

Cần tính đến alias và data stream. Kiểm tra index thực tế mà ứng dụng gọi, gồm backing index nếu có, để bảo đảm role áp dụng đúng phạm vi.

### 2.6. Quyền metadata không đồng nghĩa quyền quản trị

Một số client hoặc thao tác có thể cần đọc metadata index. Nếu gặp 403 khi client kiểm tra metadata, hãy xác định endpoint bị gọi trước khi cấp quyền. view_index_metadata thường hẹp hơn manage.

Không cấp manage chỉ vì ứng dụng cần đọc mapping hoặc kiểm tra index existence.

## 3. Thiết kế quyền tối thiểu

### 3.1. Bắt đầu từ danh sách API thực tế

Trước khi tạo role, lập danh sách thao tác mà service gọi:

| Chức năng | API hoặc thao tác | Quyền cần xem xét |
|---|---|---|
| Tìm document | Search/get | read |
| Đọc mapping | Get mapping | view_index_metadata |
| Tạo document mới | Create | create_doc hoặc create |
| Index/replace document | Index | index hoặc write |
| Partial update | Update | write |
| Xóa document | Delete | delete hoặc write |
| Tạo index | Create index | Quyền quản lý index phù hợp, tách khỏi runtime nếu có thể |
| Tạo API key/user/role | Security API | Quyền security riêng, không cấp cho ứng dụng dữ liệu |

Bảng này là điểm bắt đầu. Quyền chính xác phụ thuộc API cụ thể, phiên bản và cách Spring Data/Elasticsearch client thực hiện request.

### 3.2. Dùng role riêng cho mỗi workload

Không nên gộp mọi quyền vào một role application-role rồi gán cho tất cả service.

Có thể tạo role theo mục đích:

- catalog_reader: chỉ đọc catalog.
- catalog_writer: chỉ ghi catalog.
- catalog_reindexer: đọc nguồn và ghi index đích trong giai đoạn reindex.
- catalog_provisioner: tạo index/template hoặc cấu hình cần thiết.

Một role có phạm vi hẹp giúp reviewer hiểu ngay service có thể làm gì.

### 3.3. Tách quyền quản trị khỏi quyền chạy ứng dụng

Quy trình triển khai có thể gồm hai principal:

1. Provisioning principal tạo index, mapping, template và policy.
2. Runtime principal chỉ đọc/ghi document theo hợp đồng của ứng dụng.

Runtime service không nên cần manage, manage_security, all hoặc superuser. Nếu ứng dụng tự động tạo index khi khởi động, hãy cân nhắc chuyển bước đó sang migration/deployment job.

### 3.4. API key không thể mở rộng quyền của người tạo

Role descriptor của API key giới hạn quyền của key. Quyền hiệu lực không thể vượt quá quyền mà principal tạo key có thể cấp. Đây là một giới hạn bảo vệ quan trọng.

Tuy nhiên, nếu key được tạo bởi một principal quá rộng và role descriptor không giới hạn đúng cách, key có thể nhận quyền rộng. Hãy kiểm tra cả role descriptor lẫn danh tính tạo key.

### 3.5. Document-level và field-level security

Nếu nhiều tenant dùng chung index, có thể cần giới hạn document mà mỗi principal được đọc hoặc field mà principal được xem.

Elasticsearch hỗ trợ document-level security (DLS) và field-level security (FLS) trong các cấu hình và license tương ứng. Cần xác nhận tính năng được hỗ trợ trên phiên bản/license của cluster.

DLS/FLS không thay thế authorization ở ứng dụng. Không đưa tenant ID tùy ý từ client vào role hoặc query mà không kiểm tra nguồn đáng tin cậy. Với workload tách index theo tenant, index-level privilege có thể đơn giản và dễ kiểm toán hơn.

## 4. Tạo role chỉ đọc và chỉ ghi

### 4.1. Role chỉ đọc

Ví dụ role chỉ đọc các index products-prod-*:

~~~http
PUT /_security/role/products_reader
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-prod-*"],
      "privileges": ["read"]
    }
  ]
}
~~~

Role này không có quyền ghi document, xóa document hoặc quản lý index. Nếu client thực sự cần đọc metadata index, đánh giá việc bổ sung view_index_metadata sau khi xác nhận API bị từ chối.

### 4.2. Role chỉ ghi document

Ví dụ indexer được phép ghi vào products-prod-*:

~~~http
PUT /_security/role/products_writer
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-prod-*"],
      "privileges": ["index"]
    }
  ]
}
~~~

Privilege index phù hợp với workload index document theo semantics được cấp. Nếu service dùng update hoặc delete API, cần privilege tương ứng, thường là write hoặc tổ hợp privilege cụ thể theo phiên bản.

### 4.3. Role đọc và ghi

Nếu service thực sự cần đọc và ghi:

~~~http
PUT /_security/role/products_reader_writer
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-prod-*"],
      "privileges": [
        "read",
        "write",
        "view_index_metadata"
      ]
    }
  ]
}
~~~

Đây là ví dụ minh họa. Không thêm view_index_metadata theo thói quen nếu client không cần. Không thêm delete hoặc manage nếu use case không yêu cầu.

### 4.4. Runtime role không nên tạo index

Nếu index được tạo trước bởi deployment pipeline, runtime writer chỉ cần quyền ghi document. Việc cho phép tự tạo index có thể dẫn tới:

- Index được tạo với mapping mặc định không đúng.
- Sai shard/replica settings.
- Sai lifecycle policy hoặc template.
- Index rác do typo trong tên.
- Runtime service có khả năng thay đổi cấu trúc dữ liệu ngoài dự kiến.

Hãy dùng migration/provisioning job để quản lý schema và giữ quyền runtime ở mức hẹp.

## 5. Tạo API key có quyền giới hạn

### 5.1. API tạo key

API key có thể được tạo bằng Security API:

~~~http
POST /_security/api_key
Content-Type: application/json

{
  "name": "catalog-indexer-prod",
  "expiration": "30d",
  "role_descriptors": {
    "catalog_writer": {
      "cluster": [],
      "indices": [
        {
          "names": ["products-prod-*"],
          "privileges": ["index"]
        }
      ]
    }
  },
  "metadata": {
    "application": "catalog-indexer",
    "environment": "production",
    "owner": "search-platform"
  }
}
~~~

Tên key nên thể hiện workload và môi trường. Expiration giúp credential không tồn tại vô thời hạn. Role descriptor giới hạn quyền vào index cần thiết.

Principal tạo key phải có quyền phù hợp để tạo API key. Tùy mô hình quản trị, việc tạo key cho user khác có thể yêu cầu quyền quản lý API key rộng hơn. Không cấp quyền này cho runtime application chỉ để ứng dụng tự cấp credential cho chính nó.

### 5.2. Phản hồi tạo key

Phản hồi có thể chứa các trường như:

~~~json
{
  "id": "api-key-id",
  "name": "catalog-indexer-prod",
  "api_key": "secret-value",
  "encoded": "base64-encoded-id-and-secret",
  "expiration": 1790000000000
}
~~~

Đây là dữ liệu minh họa, không phải credential thật.

- id là định danh key dùng để quản lý hoặc thu hồi.
- api_key là secret của key.
- encoded là giá trị đã mã hóa Base64 theo định dạng dùng trong Authorization header.
- expiration là thời điểm hết hạn nếu key có expiration.

Lưu giá trị encoded hoặc cặp ID/secret theo cách client yêu cầu. Không Base64 encode lại encoded nếu dùng đúng định dạng Authorization của Elasticsearch.

Secret thường chỉ được trả về lúc tạo. Hãy lưu nó ngay vào secret manager; nếu bị mất, tạo key mới và thu hồi key cũ theo quy trình.

### 5.3. Authorization header

API key được gửi trong header:

~~~http
Authorization: ApiKey <encoded>
~~~

Giá trị encoded là trường encoded trong response tạo key. Base64 chỉ là encoding, không phải encryption. Bất kỳ ai lấy được giá trị này đều có thể dùng credential trong phạm vi quyền của key.

Chỉ truyền credential qua HTTPS với certificate được xác minh. Không gửi API key qua URL query parameter hoặc ghi nó vào log.

### 5.4. API key kế thừa giới hạn quyền của principal tạo key

Role descriptor của key không phải cách nâng quyền cho key. Quyền hiệu lực bị giới hạn bởi quyền của principal tạo key và role descriptor của key.

Nếu không khai báo role descriptor, key có thể mang quyền của creator theo semantics API key của Elasticsearch. Vì vậy, hãy luôn xác định rõ role descriptor và dùng principal provisioning có quyền vừa đủ.

Không dùng tài khoản elastic hoặc superuser để tạo key cho ứng dụng nếu có thể dùng một principal provisioning hẹp hơn.

### 5.5. Tạo key chỉ đọc

Ví dụ key cho reporting worker:

~~~http
POST /_security/api_key
Content-Type: application/json

{
  "name": "reporting-reader-prod",
  "expiration": "30d",
  "role_descriptors": {
    "reporting_reader": {
      "cluster": [],
      "indices": [
        {
          "names": ["products-prod-*", "orders-prod-*"],
          "privileges": ["read"]
        }
      ]
    }
  }
}
~~~

Key này không có quyền index, update hoặc delete. Nếu reporting worker cần metadata hoặc aggregation trên index, hãy xác minh privilege read đáp ứng API được gọi trong phiên bản cluster.

### 5.6. API key không phải secret dùng chung

Tạo key riêng theo:

- Ứng dụng.
- Môi trường (development, staging, production).
- Workload hoặc chức năng nếu quyền khác nhau.
- Tenant hoặc integration khi cần cô lập.

Không dùng một key duy nhất cho tất cả microservice. Nếu một service bị xâm nhập, key riêng giúp thu hồi đúng credential mà không làm gián đoạn các service còn lại.

## 6. Built-in service account và service token

### 6.1. Service account là danh tính dành cho thành phần cụ thể

Elasticsearch có một số built-in service account cho các thành phần Elastic Stack. Chúng được quản lý theo namespace và service name đã định nghĩa.

Service token là credential để thành phần tương ứng xác thực. Token không phải password chung cho mọi ứng dụng và không dùng thay cho API key của một microservice tùy ý.

### 6.2. Tạo service token

Với service account được hỗ trợ, token có thể được tạo qua Security API hoặc công cụ quản trị phù hợp với phiên bản:

~~~http
POST /_security/service/<namespace>/<service>/credential/token/<token_name>
~~~

Đường dẫn namespace và service phải là built-in service account hợp lệ. Không tự đặt namespace my-app với kỳ vọng Elasticsearch tạo một service account tùy chỉnh.

Response trả token secret. Hãy lưu token trong secret manager và cấu hình đúng thành phần cần dùng nó.

### 6.3. Thu hồi service token

Khi không còn cần token, có thể thu hồi credential theo API service-account token tương ứng:

~~~http
DELETE /_security/service/<namespace>/<service>/credential/token/<token_name>
~~~

Xác nhận API và token management phù hợp với phiên bản cluster. Thu hồi token có thể làm thành phần đang dùng token mất khả năng xác thực; cần triển khai token thay thế trước nếu workload phải chạy liên tục.

### 6.4. Chọn service token hay API key?

| Nhu cầu | Lựa chọn |
|---|---|
| Thành phần Elastic Stack yêu cầu built-in service identity | Service account token |
| Microservice nghiệp vụ cần quyền riêng trên index | API key |
| Tổ chức muốn quản lý role qua user kỹ thuật riêng | Dedicated technical user |
| Job triển khai cần tạo index/template | Provisioning principal riêng |
| Người vận hành cần truy cập tương tác | User cá nhân qua cơ chế SSO/realm phù hợp |

Dùng credential đúng với loại principal. Không tái sử dụng token của thành phần khác để giảm công việc cấu hình.

## 7. Cấu hình Spring Data Elasticsearch với API key

### 7.1. Không hardcode secret trong source

Không viết API key trực tiếp vào:

- Java source.
- application.yml được commit.
- Docker image.
- Helm values công khai.
- Log hoặc exception message.
- File mẫu được chia sẻ rộng rãi.

Ứng dụng nên nhận credential qua secret manager, environment injection hoặc cơ chế quản lý secret của nền tảng triển khai.

### 7.2. Ví dụ ClientConfiguration

Spring Data Elasticsearch cho phép cấu hình HTTP headers khi tạo client. Ví dụ khái niệm:

~~~java
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.http.HttpHeaders;

ClientConfiguration clientConfiguration =
    ClientConfiguration.builder()
        .connectedTo("elasticsearch.internal:9200")
        .usingSsl()
        .withHeaders(() -> {
            HttpHeaders headers = new HttpHeaders();
            headers.add(
                HttpHeaders.AUTHORIZATION,
                "ApiKey " + apiKeyEncoded
            );
            return headers;
        })
        .build();
~~~

apiKeyEncoded được đọc từ secret manager hoặc cấu hình bảo mật của runtime. Tên method, cách cấu hình SSL và client factory phụ thuộc phiên bản Spring Data Elasticsearch; hãy kiểm tra API của release train đang dùng.

Nếu dùng custom certificate, cấu hình trust đúng CA hoặc certificate chain. Không tắt hostname verification hoặc certificate validation để làm cho kết nối hoạt động.

### 7.3. Dùng TLS

API key là bearer credential: ai có secret có thể sử dụng nó. Luôn truyền qua HTTPS/TLS khi đi qua mạng.

Trong môi trường production:

- Xác minh certificate server.
- Dùng CA nội bộ được tin cậy nếu cluster dùng private PKI.
- Tránh cấu hình trust-all.
- Hạn chế network path tới Elasticsearch.
- Không gửi credential qua proxy không đáng tin cậy.
- Không ghi header Authorization trong HTTP wire log.

### 7.4. Tích hợp với Spring Boot

Tên property và cách auto-configure Elasticsearch client thay đổi theo phiên bản Spring Boot/Spring Data Elasticsearch. Không giả định mọi release đều có một property API key chuẩn.

Nếu cấu hình client bằng bean tùy chỉnh, hãy bảo đảm bean đó được Spring Data template/repository thực sự sử dụng. Tránh tạo một client đã gắn API key nhưng repository lại đang dùng client khác do auto-configuration.

### 7.5. Cấu hình qua secret manager

Một cấu hình runtime có thể nhận URL và secret qua một configuration object:

~~~java
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchCredentials(
    String url,
    String apiKey
) {
}
~~~

Bean cấu hình client có thể nhận object này qua constructor hoặc method injection:

~~~java
@Configuration
public class ElasticsearchClientConfiguration {

    @Bean
    ClientConfiguration clientConfiguration(
            ElasticsearchCredentials credentials) {

        return ClientConfiguration.builder()
            .connectedTo(credentials.url())
            .usingSsl()
            .withHeaders(() -> {
                HttpHeaders headers = new HttpHeaders();
                headers.add(
                    HttpHeaders.AUTHORIZATION,
                    "ApiKey " + credentials.apiKey()
                );
                return headers;
            })
            .build();
    }
}
~~~

Đây là ví dụ cấu trúc. Với production, secret nên được inject từ secret manager hoặc workload identity integration của nền tảng. Không đưa giá trị secret thật vào application.yml được commit.

Nếu key thay đổi trong runtime, cần xác định client có đọc header động hay chỉ lấy giá trị khi khởi tạo. Nhiều cấu hình client chụp giá trị credential lúc tạo bean; khi rotate, có thể cần refresh/recreate client hoặc restart instance theo rollout có kiểm soát.

### 7.6. Cấu hình Basic authentication khi dùng technical user

Nếu dùng dedicated user/password thay cho API key, cấu hình authentication theo cơ chế client được hỗ trợ:

~~~java
ClientConfiguration clientConfiguration =
    ClientConfiguration.builder()
        .connectedTo("elasticsearch.internal:9200")
        .usingSsl()
        .withBasicAuth(username, password)
        .build();
~~~

Dùng user riêng có role hẹp. Không dùng tài khoản quản trị mặc định cho ứng dụng. Password cũng phải được quản lý như secret, có expiry/rotation và không log.

## 8. Quản lý secret an toàn

### 8.1. Secret manager là nguồn lưu trữ chính

Lưu API key hoặc service token trong hệ thống quản lý secret phù hợp, ví dụ vault hoặc secret store của nền tảng cloud/container.

Ứng dụng chỉ nhận secret tại runtime. Quyền đọc secret cũng cần giới hạn theo workload identity.

Không lưu secret trong Git, ticket, chat, tài liệu hướng dẫn hoặc biến cấu hình được chia sẻ rộng rãi.

### 8.2. Không nhầm Base64 với mã hóa

encoded của API key là Base64 encoding cho chuỗi credential. Bất kỳ ai có chuỗi này đều có thể dùng key. Không xem Base64 như một lớp bảo mật và không đăng giá trị đó lên log để “che” secret.

### 8.3. Tránh log Authorization header

HTTP client debug logging có thể ghi request headers. Hãy cấu hình redact Authorization và các secret-related header.

Cần kiểm tra cả:

- Application log.
- HTTP wire log.
- Reverse proxy/access log.
- APM/tracing attribute.
- Error report.
- Crash dump và diagnostic bundle.

Không đưa raw API key vào trace baggage hoặc metric label.

### 8.4. Tách secret theo môi trường

Không dùng key production trong development hoặc CI. Mỗi môi trường nên có key riêng, role riêng và index pattern riêng.

Ví dụ:

- catalog-indexer-dev chỉ ghi products-dev-*.
- catalog-indexer-staging chỉ ghi products-staging-*.
- catalog-indexer-prod chỉ ghi products-prod-*.

Điều này giúp giảm nguy cơ test job ghi nhầm production.

### 8.5. Hạn chế quyền đọc secret

Chỉ workload identity của ứng dụng cần key mới được đọc secret. Developer không cần quyền xem production key chỉ vì họ có quyền deploy code.

Quyền đọc secret và quyền gọi Elasticsearch là hai lớp kiểm soát độc lập. Nếu một pipeline build bị xâm nhập, nó không nên tự động có quyền đọc production credential.

## 9. Xoay vòng và thu hồi credential

### 9.1. API key thường được thay bằng key mới

API key secret không được cập nhật như một password thông thường. Quy trình rotate thường là:

1. Tạo API key mới với cùng hoặc quyền hẹp hơn.
2. Lưu secret mới vào secret manager.
3. Deploy/reload workload để dùng key mới.
4. Kiểm tra request thành công và đúng identity.
5. Thu hồi key cũ.
6. Theo dõi lỗi xác thực sau khi thu hồi.

Không revoke key cũ trước khi workload đã chuyển sang key mới nếu cần tránh downtime.

### 9.2. Rotation overlap có kiểm soát

Có thể có một khoảng thời gian ngắn cả key cũ và key mới cùng tồn tại. Khoảng overlap phải được giới hạn, có owner và thời điểm kết thúc.

Không để key cũ tồn tại vô thời hạn “phòng khi cần”. Sau khi xác nhận rollout thành công, thu hồi key cũ.

### 9.3. Thu hồi API key

API key có thể được vô hiệu hóa theo ID qua Security API:

~~~http
DELETE /_security/api_key
Content-Type: application/json

{
  "ids": ["api-key-id"]
}
~~~

API quản lý key cũng có thể hỗ trợ lọc theo các thuộc tính khác tùy phiên bản. Trong quy trình tự động, ưu tiên lưu key ID cùng metadata để thu hồi chính xác.

Thu hồi key làm mọi client đang dùng key đó mất quyền truy cập. Hãy xác định owner và workload trước khi revoke.

### 9.4. Khi nghi ngờ key bị lộ

Nếu credential bị lộ:

- Revoke key nghi ngờ theo incident procedure.
- Tạo key mới với quyền tối thiểu.
- Cập nhật secret và rollout workload.
- Kiểm tra audit/security log nếu có.
- Xem xét request bất thường và phạm vi dữ liệu có thể truy cập.
- Xóa secret khỏi nơi bị lộ và xử lý lịch sử Git/log theo quy trình tổ chức.
- Đánh giá lại role và thời hạn key.

Chỉ xóa secret khỏi file hiện tại không làm credential đã lộ mất hiệu lực. Thu hồi ở Elasticsearch mới chặn việc sử dụng tiếp.

### 9.5. Expiration và rotation schedule

Đặt expiration phù hợp với khả năng tự động rotate. Key hết hạn mà chưa có key thay thế sẽ làm ứng dụng mất kết nối.

Một quy trình rotation tự động nên:

- Tạo key trước khi key hiện tại hết hạn.
- Kiểm tra key mới.
- Cập nhật secret.
- Rollout instance.
- Xác nhận toàn bộ instance đã chuyển.
- Revoke key cũ.
- Cảnh báo nếu rotation chưa hoàn tất trước deadline.

Không đặt thời hạn ngắn hơn chu kỳ deploy/rotation mà hệ thống có thể bảo đảm.

## 10. Kiểm tra quyền hiệu lực

### 10.1. Xác nhận danh tính đã xác thực

Có thể dùng endpoint authenticate để kiểm tra credential:

~~~http
GET /_security/_authenticate
Authorization: ApiKey <encoded>
~~~

Response cho biết principal và thông tin xác thực theo loại credential. Không đưa response chứa thông tin nhạy cảm vào log công khai.

### 10.2. Kiểm tra quyền cụ thể

Elasticsearch có API kiểm tra privileges của user hiện tại. Có thể dùng nó để xác minh một principal có quyền cluster/index mong muốn, theo schema của phiên bản cluster.

Ví dụ khái niệm:

~~~http
POST /_security/user/_has_privileges
Authorization: ApiKey <encoded>
Content-Type: application/json

{
  "cluster": [],
  "index": [
    {
      "names": ["products-prod-*"],
      "privileges": ["read", "index"]
    }
  ]
}
~~~

Kết quả cho biết quyền được yêu cầu có hiệu lực hay không. Dùng đúng endpoint và payload của phiên bản Elasticsearch đang chạy.

### 10.3. Kiểm tra bằng thao tác thực tế

Privilege check không thay thế integration test. Hãy thử:

- Search document trong index được phép.
- Index document nếu service cần ghi.
- Update/delete chỉ khi được cấp và cần thiết.
- Search hoặc ghi vào index ngoài phạm vi để xác nhận bị từ chối.
- Gọi cluster/security API mà runtime không cần để xác nhận không được phép.

Test negative rất quan trọng. Một role hoạt động với use case mong muốn vẫn có thể rộng hơn cần thiết.

### 10.4. Kiểm tra qua chính Spring Data client

Dùng cùng bean/client và credential mà ứng dụng production sẽ dùng. Một curl thành công với admin credential không chứng minh client của ứng dụng có quyền đúng.

Integration test nên chạy bằng API key hoặc technical user có role tương đương production. Không đưa secret production vào test environment.

## 11. Bảo mật cho index, alias và data stream

### 11.1. Cấp quyền trên tên resource ứng dụng thực sự dùng

Ứng dụng có thể thao tác qua alias thay vì concrete index. Data stream có thể có backing indices. Hãy kiểm tra security privilege áp dụng cho tên resource mà API request sử dụng và cách Elasticsearch xử lý alias/data stream trong phiên bản cluster.

Không đoán phạm vi quyền chỉ từ tên alias trong entity annotation.

### 11.2. Tránh wildcard toàn cluster

Role có names wildcard toàn cluster thường quá rộng cho runtime service. Dùng prefix/pattern cụ thể và test cả trường hợp index có tên gần giống.

Nếu có nhiều môi trường trong cùng cluster, pattern phải phân biệt rõ dev, staging và production.

### 11.3. Quyền cho rollover và index lifecycle

Service ghi vào data stream có thể cần privilege phù hợp với thao tác create/index và lifecycle được cấu hình. Các thao tác rollover, template, ILM hoặc quản lý data stream thường thuộc provisioning/operations principal.

Không cấp quyền quản lý lifecycle cho ứng dụng chỉ vì ứng dụng gửi bulk document vào data stream.

### 11.4. Alias write index

Nếu alias có write index, ứng dụng có thể ghi qua alias mà không cần biết backing index. Hãy bảo đảm role được cấp đúng pattern và alias không trỏ tới index ngoài phạm vi service.

Quy trình thay alias hoặc rollover nên được thực hiện bởi principal quản trị riêng.

## 12. Multi-tenant và phân tách workload

### 12.1. Tách index theo tenant khi cần isolation mạnh

Nếu mỗi tenant có index riêng, có thể cấp key cho một tenant chỉ trên pattern index của tenant đó. Điều này tạo ranh giới authorization rõ ràng ở Elasticsearch.

Tuy nhiên, số lượng role/key có thể tăng lớn. Cần đánh giá khả năng vận hành, naming convention và quy trình thu hồi.

### 12.2. Dùng DLS khi chia sẻ index

Nếu nhiều tenant cùng nằm trong một index, document-level security có thể giới hạn document theo query filter của role, nếu cluster/license hỗ trợ.

Cần kiểm tra kỹ rằng filter DLS không thể bị bypass bởi một đường truy cập khác. Không dùng query filter do client tự gửi như một cơ chế bảo mật duy nhất.

### 12.3. Field-level security

FLS có thể giới hạn field được đọc bởi principal. Ví dụ reporting service chỉ cần tên và giá, không cần email hoặc thông tin cá nhân.

Hãy kiểm tra tương thích với aggregation, sorting, highlighting và mapping của ứng dụng. Một field bị ẩn có thể làm một số query hoặc response mapping không hoạt động như mong đợi.

### 12.4. Không chia sẻ API key giữa tenant

Nếu một key có quyền đọc mọi tenant, việc thêm tenant filter ở Java không tạo isolation ở tầng Elasticsearch. Một lỗi query hoặc lỗ hổng ứng dụng có thể làm lộ dữ liệu.

Với yêu cầu isolation cao, dùng principal/key riêng, index riêng hoặc DLS đã được kiểm thử.

## 13. Vận hành credential trong môi trường triển khai

### 13.1. Kubernetes và container

Trong Kubernetes, có thể inject secret qua Secret volume hoặc environment variable theo chính sách nền tảng. Hạn chế quyền đọc Secret theo namespace/service account và không commit secret manifest ở dạng plaintext.

Nếu secret được mount thành file, ứng dụng cần cơ chế đọc/refresh phù hợp. Nếu client chỉ nạp credential khi khởi tạo bean, cần restart hoặc recreate client sau rotation.

### 13.2. CI/CD

Pipeline triển khai chỉ nên có quyền lấy secret cần cho môi trường mà nó deploy. Không in giá trị secret trong job log.

Tách quyền:

- Build pipeline: build artifact, không cần production API key.
- Deploy pipeline: lấy secret hoặc trigger platform inject.
- Runtime workload: đọc credential khi chạy.
- Provisioning pipeline: quyền tạo index/role/key theo phạm vi được phê duyệt.

### 13.3. Local development

Developer nên dùng cluster/dev key riêng có quyền hạn chế. Nếu dùng shared development environment, cấp credential có thể thu hồi và không có quyền production.

Không copy key production về laptop để debug. Dữ liệu production và secret production cần được bảo vệ theo chính sách tổ chức.

### 13.4. Disaster recovery

Lưu metadata của credential (owner, key ID, role, expiry, environment) trong hệ thống quản lý, nhưng không lưu secret ở nơi không an toàn.

Runbook cần chỉ ra cách tạo credential thay thế, cập nhật workload, xác minh và thu hồi credential cũ. Điều này giúp khôi phục service mà không cần dùng superuser.

## 14. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| 401 sau khi deploy | API key sai, thiếu header, key hết hạn/revoked | Kiểm tra secret, Authorization header và key status |
| 403 khi search | Thiếu read hoặc pattern không khớp | Kiểm tra role và index thực tế |
| 403 khi đọc mapping | Thiếu metadata privilege cần thiết | Xác định API bị từ chối rồi cân nhắc view_index_metadata |
| 403 khi update | Chỉ có read hoặc privilege ghi chưa đủ | Chọn write/privilege phù hợp với thao tác |
| API key có quyền rộng ngoài dự kiến | Creator quá rộng hoặc role descriptor không giới hạn đúng | Dùng principal provisioning hẹp và role descriptor cụ thể |
| Service account token không dùng được | Chọn sai built-in service identity | Dùng đúng service account dành cho thành phần tương ứng |
| Credential hoạt động ở dev nhưng lỗi prod | Role, index pattern, TLS hoặc secret khác nhau | So sánh config/privilege theo môi trường |
| Key mới tạo nhưng app vẫn dùng key cũ | Client giữ header tại thời điểm khởi tạo | Refresh/recreate client hoặc rollout instance |
| Revoke key làm service gián đoạn | Thu hồi trước khi rollout key mới | Dùng rotation overlap và xác nhận chuyển đổi |
| Secret xuất hiện trong log | HTTP wire logging hoặc exception in header | Redact Authorization và rotate key đã lộ |
| 403 với alias/data stream | Pattern hoặc privilege không khớp resource/backing index | Kiểm tra tên resource và security semantics của version |
| Runtime không tạo được index | Role runtime không có quyền quản lý index | Tạo index bằng provisioning job riêng |
| Một service ảnh hưởng service khác khi revoke | Nhiều service dùng chung key | Tách credential theo workload |
| Test quyền chỉ thành công với admin | Test không dùng principal production-like | Chạy integration test bằng key/role giới hạn |

## 15. Quy trình thiết kế và triển khai

Khi cấp quyền cho một ứng dụng Spring Data Elasticsearch:

1. Liệt kê thao tác Elasticsearch mà ứng dụng thực sự gọi.
2. Chọn danh tính: API key, dedicated technical user hoặc built-in service token đúng use case.
3. Tách provisioning/admin khỏi runtime workload.
4. Xác định index, alias và data stream cụ thể.
5. Tạo role với cluster privilege tối thiểu và index privilege cần thiết.
6. Tạo API key với tên, expiration và role descriptor giới hạn.
7. Lưu secret trong secret manager.
8. Cấu hình Spring Data client dùng HTTPS và Authorization header.
9. Kiểm tra client/template/repository thực sự dùng credential đó.
10. Xác nhận danh tính bằng authenticate API.
11. Kiểm tra privilege và chạy positive/negative integration tests.
12. Thiết lập rotation, expiry alert và revoke procedure.
13. Theo dõi 401/403, credential usage và sự kiện bảo mật.
14. Review role định kỳ để loại bỏ privilege không còn dùng.

## 16. Những điểm cần ghi nhớ

- Authentication xác định caller; authorization quyết định caller được làm gì.
- Built-in service account của Elasticsearch dành cho thành phần Elastic Stack cụ thể; không phải tài khoản tùy chỉnh cho mọi microservice.
- API key thường phù hợp cho workload ứng dụng cần credential riêng và role descriptor giới hạn.
- Dedicated technical user là lựa chọn khác khi cần principal có role quản lý tập trung.
- Quyền hiệu lực của API key bị giới hạn bởi quyền của principal tạo key và role descriptor.
- Runtime service chỉ nên có index privilege cần thiết; tránh all, manage, manage_security và superuser.
- Tách quyền đọc, ghi, xóa document, quản lý index và quản lý security theo chức năng.
- Dùng index pattern cụ thể; kiểm tra alias và data stream.
- API key dùng header Authorization: ApiKey encoded qua HTTPS.
- Base64 không phải encryption; không log hoặc commit credential.
- Lưu secret trong secret manager và tách key theo ứng dụng/môi trường.
- Rotation nên tạo key mới, rollout, xác minh rồi mới revoke key cũ.
- Kiểm thử cả thao tác được phép lẫn thao tác phải bị từ chối.
- Spring Data client không tự làm cho credential an toàn; quyền và secret lifecycle phải được quản lý ở tầng triển khai.
- Low-level client và Spring Data operations có thể có đường cấu hình khác nhau; xác nhận đúng client mà repository đang dùng.

Tài khoản dịch vụ, API key và quyền tối thiểu tạo thành một ranh giới bảo mật quan trọng giữa ứng dụng và Elasticsearch. Khi mỗi workload có credential riêng, chỉ được truy cập đúng resource và có quy trình xoay vòng/thu hồi rõ ràng, hệ thống dễ vận hành hơn và giảm đáng kể phạm vi ảnh hưởng khi một secret bị lộ.

