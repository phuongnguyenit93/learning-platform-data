# Kiểm soát trường trả về và dữ liệu nhạy cảm trong _source

Elasticsearch lưu nội dung document trong phần _source theo cấu hình index. Khi ứng dụng search, response thường chứa cả source document. Nếu entity có thông tin nội bộ như email cá nhân, số điện thoại, địa chỉ, ghi chú riêng, token hoặc dữ liệu nhạy cảm khác, việc trả nguyên source ra API có thể làm lộ thông tin mà người dùng không cần hoặc không được phép xem.

Spring Data Elasticsearch cho phép ứng dụng kiểm soát dữ liệu trả về qua source filtering, projection và mapping. Tuy nhiên, cần phân biệt rõ ba mục tiêu:

- **Giảm payload:** chỉ trả những field cần thiết cho một truy vấn.
- **Thiết kế dữ liệu:** không lưu hoặc không index field mà use case search không cần.
- **Bảo mật truy cập:** ngăn người dùng hoặc service không có quyền đọc dữ liệu nhạy cảm.

Source filtering chủ yếu giải quyết mục tiêu đầu tiên. Nó không phải cơ chế authorization. Nếu field vẫn tồn tại trong document và mapping, người có quyền truy vấn phù hợp vẫn có thể tìm kiếm, aggregation hoặc lấy field đó qua API khác. Bảo mật cần được thực thi ở tầng ứng dụng và security controls của Elasticsearch.

## 1. _source là gì?

Khi index document, Elasticsearch thường lưu một bản JSON gốc trong metadata field có tên _source. Ví dụ:

    PUT customers/_doc/c-100
    {
      "name": "Nguyen An",
      "email": "an@example.com",
      "phone": "+84-900-123-456",
      "address": {
        "city": "Ho Chi Minh City",
        "street": "Example Street"
      },
      "internalNote": "Customer requested a private callback"
    }

Một search response mặc định có thể trả lại source:

    GET customers/_search
    {
      "query": {
        "term": {
          "name.keyword": "Nguyen An"
        }
      }
    }

Phần hits.hits[n]._source chứa JSON document được lưu. Nếu service chuyển nguyên entity hoặc source vào response HTTP, những field nội bộ có thể bị lộ ngoài ý muốn.

_source hữu ích cho:

- Trả lại document gốc sau search.
- Chuyển JSON thành entity bằng Spring Data.
- Reindex dữ liệu sang index khác.
- Update document theo một số cách dựa trên source.
- Debug hoặc kiểm tra dữ liệu.

Không nên coi _source là một vùng dữ liệu bí mật. Quyền truy cập vào index và document phải được kiểm soát riêng.

## 2. Source filtering là gì?

Source filtering cho phép một search request chỉ trả về một phần của _source. Có thể chọn field cần lấy bằng includes hoặc loại field không muốn trả bằng excludes.

Ví dụ chỉ trả name và city:

    GET customers/_search
    {
      "_source": {
        "includes": [
          "name",
          "address.city"
        ]
      },
      "query": {
        "match_all": {}
      }
    }

Response source sẽ chỉ chứa những field được chọn:

    {
      "name": "Nguyen An",
      "address": {
        "city": "Ho Chi Minh City"
      }
    }

Ví dụ loại internalNote:

    GET customers/_search
    {
      "_source": {
        "excludes": [
          "internalNote",
          "address.street"
        ]
      },
      "query": {
        "match_all": {}
      }
    }

Source filtering được áp dụng cho response của request. Nó không xóa field khỏi document đã lưu trong index.

## 3. Includes và excludes

Có hai cách mô tả tập field trả về:

- **includes:** chỉ định những field được phép xuất hiện trong source response.
- **excludes:** chỉ định những field bị loại khỏi source response.

Ví dụ:

    "_source": {
      "includes": [
        "id",
        "name",
        "price"
      ],
      "excludes": [
        "internal.*"
      ]
    }

Khi dùng đồng thời includes và excludes, Elasticsearch chọn các field phù hợp với includes rồi loại các field khớp excludes. Với dữ liệu nhạy cảm, allowlist bằng includes thường dễ kiểm soát hơn denylist bằng excludes, vì field mới được thêm vào mapping sẽ không tự xuất hiện trong response nếu không được cho phép.

Excludes tiện khi chỉ cần bỏ một vài field khỏi một response nội bộ, nhưng có rủi ro nếu document được mở rộng sau này. Nếu một field nhạy cảm mới được thêm vào mà danh sách excludes không được cập nhật, field đó có thể bị trả ra.

### Wildcard và nested path

Source filtering hỗ trợ pattern cho tên field. Ví dụ:

    "_source": {
      "includes": [
        "profile.*",
        "preferences.language"
      ],
      "excludes": [
        "profile.private*"
      ]
    }

Với object lồng nhau, có thể chọn field con bằng đường dẫn có dấu chấm như address.city. Hãy kiểm tra response thực tế để xác nhận cấu trúc source đúng với DTO và không vô tình lấy cả object chứa field nhạy cảm.

Không dùng wildcard rộng như * hoặc profile.* nếu object đó có thể chứa field riêng tư trong tương lai. Allowlist các field cụ thể thường an toàn và dễ review hơn.

## 4. Source filtering không phải field-level security

Đây là ranh giới quan trọng nhất:

| Cơ chế | Mục đích | Có bảo vệ field khỏi người gọi không có quyền không? |
|---|---|---|
| Request-time source filtering | Giảm field trong response của request | Không tự nó |
| Mapping _source includes/excludes | Điều chỉnh source được lưu | Không phải authorization |
| DTO/projection ở ứng dụng | Kiểm soát response nghiệp vụ | Có thể, nếu mọi đường trả dữ liệu đều đi qua logic này |
| Elasticsearch field-level security | Giới hạn field người dùng được đọc theo quyền | Có, khi được cấu hình và áp dụng đúng |
| Elasticsearch document-level security | Giới hạn document người dùng được truy cập | Có, khi được cấu hình và áp dụng đúng |
| Role/privilege trên index | Giới hạn API/index mà principal có thể dùng | Có, ở phạm vi quyền được cấp |

Một client có quyền search trực tiếp trên index và được phép đọc source có thể gửi request khác mà không dùng source filter mà ứng dụng đã dùng. Vì vậy, không được xem một source filter trong repository query là hàng rào bảo mật cho toàn hệ thống.

Nếu người dùng truy cập Elasticsearch trực tiếp, hãy cấu hình authentication, authorization, index privileges và field/document-level security phù hợp với khả năng của phiên bản và gói triển khai.

Nếu chỉ backend được phép truy cập Elasticsearch, backend phải kiểm tra quyền người dùng trước khi chạy query và phải kiểm soát response DTO. Không trả Elasticsearch credentials hoặc quyền truy cập index rộng cho browser/mobile client.

## 5. Source filtering không ngăn query trên field bị ẩn

Giả sử request chỉ trả name:

    GET customers/_search
    {
      "_source": {
        "includes": [
          "name"
        ]
      },
      "query": {
        "term": {
          "email.keyword": "an@example.com"
        }
      }
    }

Response có thể không chứa email trong _source, nhưng query vẫn có thể dùng email để tìm document nếu field được index và caller có quyền chạy query đó.

Tương tự, field bị loại khỏi _source response vẫn có thể được dùng trong:

- term, range, match hoặc các query khác.
- sort.
- aggregations.
- script nếu mapping và quyền cho phép.
- fields hoặc docvalue_fields.

Điều này có thể tạo kênh suy luận dữ liệu. Ví dụ, người gọi không thấy email nhưng có thể hỏi xem document nào khớp một email cụ thể, hoặc dùng aggregation để suy ra giá trị.

Nếu field không được phép dùng cho một nhóm người dùng, phải giới hạn query/aggregation và quyền đọc field ở tầng security, không chỉ ẩn nó khỏi source response.

## 6. Source filtering trong Spring Data Elasticsearch

Spring Data Elasticsearch hỗ trợ source filtering qua abstraction query. Trong các phiên bản hiện đại, có thể dùng FetchSourceFilter với includes và excludes rồi gắn vào query:

    String[] includes = {
        "name",
        "address.city"
    };

    String[] excludes = {
        "internalNote",
        "address.street"
    };

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .matchAll(m -> m)
        )
        .withSourceFilter(
            new FetchSourceFilter(includes, excludes)
        )
        .build();

    SearchHits<Customer> hits =
        operations.search(query, Customer.class);

Package, constructor và cách gắn source filter phụ thuộc phiên bản Spring Data Elasticsearch. Một số phiên bản có constructor hoặc API SourceFilter khác. Hãy kiểm tra Javadoc/IDE của dependency đang resolve thay vì sao chép nguyên văn ví dụ từ major version khác.

Với NativeQuery, query được xây dựng bằng Elasticsearch Java API Client. Source filter vẫn là phần cấu hình response source, không thay đổi mapping hoặc quyền truy cập.

## 7. Source filter với query builder và Query abstraction

Nếu dùng query abstraction thay vì NativeQuery, một số phiên bản cho phép đặt source filter trực tiếp trên Query:

    Query query = NativeQuery.builder()
        .withQuery(q -> q
            .term(t -> t
                .field("status")
                .value("ACTIVE")
            )
        )
        .withSourceFilter(
            new FetchSourceFilter(
                new String[] {"name", "email"},
                new String[] {"internalNote"}
            )
        )
        .build();

    SearchHits<Customer> hits =
        operations.search(query, Customer.class);

Ví dụ chỉ minh họa vị trí cấu hình. Kiểu query, method builder và package có thể khác ở phiên bản cũ hoặc khi dùng API template khác.

Nếu query được tái sử dụng ở nhiều endpoint, tránh gắn source filter có phạm vi rộng vào một query object dùng chung mà không kiểm tra quyền của từng caller. Tạo query/DTO theo use case để tránh rò rỉ field qua một endpoint khác.

## 8. Chỉ trả một phần source cho API tìm kiếm

Một endpoint public thường chỉ cần một tập field nhỏ. Có thể tạo DTO riêng:

    public record CustomerSearchItem(
        String id,
        String name,
        String city
    ) {}

Service map SearchHit sang DTO:

    List<CustomerSearchItem> items =
        hits.getSearchHits().stream()
            .map(hit -> new CustomerSearchItem(
                hit.getId(),
                hit.getContent().getName(),
                hit.getContent().getAddress().getCity()
            ))
            .toList();

DTO tạo một allowlist rõ ràng cho response. Ngay cả khi entity Customer có email, phone, address street và internalNote, endpoint chỉ serialize ba field đã chọn.

Đây thường là lớp bảo vệ cần thiết ở ứng dụng. Source filtering có thể giảm payload Elasticsearch -> application, còn DTO đảm bảo response application -> caller chỉ chứa dữ liệu được thiết kế.

Không trả trực tiếp entity persistence từ controller nếu entity có field nhạy cảm hoặc nội bộ. Entity có thể được mở rộng sau này và vô tình thêm field vào API response.

## 9. Vì sao không chỉ dựa vào DTO?

DTO kiểm soát response API, nhưng nếu ứng dụng vẫn tải toàn bộ source về backend, field nhạy cảm vẫn đi qua memory, logs, tracing hoặc exception handling của backend.

Kết hợp hai lớp:

1. Source filtering giảm dữ liệu Elasticsearch trả về khi query không cần toàn bộ source.
2. DTO allowlist giới hạn dữ liệu được trả ra khỏi service.

Nếu một endpoint có quyền xem email, có thể dùng một DTO riêng cho use case đó và query có source includes phù hợp. Endpoint khác không có quyền thì không chọn email và không map email vào response.

Tuy nhiên, việc chọn includes dựa trên role trong code không thay thế kiểm tra authorization. Backend phải xác thực user và quyền trước khi xây dựng query.

## 10. Partial source và ánh xạ entity

Khi source filter chỉ trả một số field nhưng Spring Data vẫn ánh xạ kết quả vào entity đầy đủ, các property không được trả có thể nhận giá trị null, default hoặc trạng thái không phân biệt được với dữ liệu thực sự rỗng.

Ví dụ entity:

    public class Customer {
        private String name;
        private String email;
        private String phone;
        private Address address;
    }

Query chỉ lấy name:

    .withSourceFilter(
        new FetchSourceFilter(
            new String[] {"name"},
            null
        )
    )

Khi nhận Customer, email và phone không được tải. Nếu code sau đó gọi:

    customer.getEmail()

giá trị có thể null dù email thực sự tồn tại trong index.

Điều này tạo nguy cơ ghi đè dữ liệu nếu entity partial được gửi lại bằng save. Một entity được đọc thiếu field không nên được xem như bản đầy đủ của document.

### Dùng projection/DTO cho kết quả partial

Nếu endpoint chỉ cần vài field, nên map sang DTO riêng hoặc dùng projection được hỗ trợ:

    public record CustomerSummary(
        String name,
        String city
    ) {}

Không dùng entity đầy đủ làm đối tượng update nếu source filter đã bỏ field. Nếu cần update một phần, dùng UpdateQuery/partial update với đúng field thay đổi thay vì save toàn bộ entity partial.

## 11. Source filtering và update nguy hiểm

Một lỗi thường gặp:

1. Search Customer với source filter chỉ lấy name.
2. Spring Data ánh xạ thành Customer, email/phone không có.
3. Service đổi name.
4. Service gọi save(customer).
5. Source mới có thể ghi đè document và làm mất email/phone nếu thao tác index thay thế toàn bộ source.

Đây là lý do không nên dùng entity partial như bản đầy đủ cho read-modify-write.

Giải pháp:

- Dùng DTO chỉ đọc cho query partial.
- Khi update, đọc đủ dữ liệu cần thiết hoặc dùng partial update.
- Dùng UpdateQuery/UpdateRequest để chỉ thay đổi field cần thiết.
- Dùng optimistic concurrency nếu có nhiều writer.
- Không gọi save với entity được tạo từ source filter nếu chưa bảo đảm field còn thiếu được giữ nguyên.

## 12. Source filtering khác fields và docvalue_fields

Elasticsearch có nhiều cơ chế trả field:

| Cơ chế | Nguồn dữ liệu | Mục đích |
|---|---|---|
| _source filtering | Stored _source | Trả một phần JSON document |
| fields | Field values đã được mapping và fetch theo API | Trả giá trị theo mapping, có thể chuẩn hóa kiểu |
| docvalue_fields | Doc values | Lấy field có doc values, thường phù hợp cho sort/aggregation và fetch giá trị |
| stored_fields | Field được cấu hình store riêng | Lấy field đã được lưu riêng theo mapping |
| script_fields | Kết quả script | Tạo giá trị tính toán cho response |

Fields API không phải lúc nào cũng trả cùng cấu trúc hoặc kiểu dữ liệu như _source. Một số field được trả dưới dạng danh sách giá trị. Doc values không hỗ trợ mọi kiểu field.

Đừng chuyển từ source filtering sang fields chỉ để ẩn dữ liệu. Nếu caller có thể yêu cầu fields cho một field nhạy cảm, dữ liệu vẫn có thể bị trả ra. Quyền truy cập phải được kiểm soát riêng.

## 13. Tắt _source hoàn toàn

Mapping có thể tắt lưu _source:

    PUT audit-events
    {
      "mappings": {
        "_source": {
          "enabled": false
        },
        "properties": {
          "eventType": {
            "type": "keyword"
          },
          "createdAt": {
            "type": "date"
          }
        }
      }
    }

Điều này có thể giảm storage, nhưng có tradeoff lớn:

- Không thể lấy lại source document gốc bằng search response.
- Reindex từ _source thông thường không còn khả dụng.
- Một số update/recovery workflow dựa vào source bị hạn chế.
- Debug dữ liệu khó hơn.
- Ứng dụng cần dùng fields/stored fields hoặc một nguồn dữ liệu khác để dựng response.

Tắt _source không đồng nghĩa field đã được bảo mật. Các field được index vẫn có thể được query hoặc trả qua các cơ chế khác nếu mapping và quyền cho phép.

Không nên tắt _source chỉ vì không muốn trả một vài field trong một endpoint. Dùng request-time source filtering hoặc DTO sẽ linh hoạt hơn.

## 14. Mapping-time _source excludes

Mapping có thể cấu hình _source excludes để loại một số field khỏi source được lưu:

    PUT customers
    {
      "mappings": {
        "_source": {
          "excludes": [
            "temporaryPayload"
          ]
        },
        "properties": {
          "name": {
            "type": "text"
          },
          "temporaryPayload": {
            "type": "keyword"
          }
        }
      }
    }

Field bị loại khỏi stored _source vẫn có thể được index theo mapping và dùng cho query hoặc aggregation. Vì vậy, đây không phải field-level access control.

Mapping-time excludes có tác động lâu dài đến khả năng khôi phục source. Nếu field bị loại khỏi source, reindex hoặc update workflow có thể không tái tạo được field đó từ source cũ.

Chỉ dùng mapping-time excludes khi đã đánh giá đầy đủ yêu cầu reindex, update, debugging và data recovery. Không dùng nó như giải pháp thay thế authorization.

## 15. Synthetic _source và khác biệt phiên bản

Một số phiên bản Elasticsearch hỗ trợ synthetic _source, trong đó source được tái tạo từ dữ liệu đã index thay vì giữ nguyên toàn bộ JSON ban đầu theo cách truyền thống.

Synthetic source có thể giảm storage trong một số trường hợp nhưng có các giới hạn về kiểu field và cách tái tạo cấu trúc. Thứ tự array, giá trị trùng hoặc representation của một số field có thể khác tùy field type và cấu hình.

Không giả định synthetic _source tương đương byte-for-byte với payload ban đầu. Nếu ứng dụng cần lưu nguyên JSON gốc, hãy kiểm tra semantics và giới hạn của phiên bản Elasticsearch.

Source filtering vẫn là cơ chế chọn field trả về của search request; synthetic source là cách lưu/tái tạo source ở tầng index. Hai khái niệm này giải quyết hai vấn đề khác nhau.

## 16. Dữ liệu nhạy cảm có nên được index không?

Nếu một field không cần cho search, filter, sort hoặc aggregation, cân nhắc không index field đó hoặc không gửi nó vào Elasticsearch.

Ví dụ:

| Dữ liệu | Cân nhắc |
|---|---|
| Tên hiển thị | Có thể cần full-text search |
| Email | Có thể cần lookup exact; cần hạn chế quyền và cân nhắc hash/tokenization |
| Số điện thoại | Thường không cần full-text; hạn chế truy cập và log |
| Địa chỉ đầy đủ | Chỉ index phần cần search/filter |
| Ghi chú nội bộ | Không đưa vào public search projection |
| Password | Không lưu plaintext; thường không cần trong Elasticsearch |
| Access token/API secret | Không đưa vào search index |
| Payment credential | Dùng hệ thống chuyên dụng, không lưu tùy tiện trong _source |

Không index field có thể giảm khả năng query và giảm bề mặt lộ dữ liệu, nhưng cũng cần xem xét liệu source có lưu field đó hay không. Nếu field vẫn nằm trong _source, người có quyền đọc source vẫn có thể lấy được.

Đối với bí mật như password, token hoặc private key, giải pháp đúng thường là không đưa chúng vào Elasticsearch. Source filtering không phải biện pháp bảo vệ bí mật.

## 17. Tách public projection và private data

Một cách thiết kế an toàn là không trộn mọi dữ liệu vào một document search.

Ví dụ:

    Customer database:
      id
      name
      email
      phone
      address
      internalNote

    Customer search index:
      id
      displayName
      city
      status

Search index chỉ chứa dữ liệu cần cho search use case. Khi người dùng có quyền xem thông tin riêng tư, backend lấy dữ liệu từ nguồn phù hợp sau khi kiểm tra quyền.

Lợi ích:

- Giảm dữ liệu nhạy cảm nằm trong search index.
- Giảm hậu quả khi endpoint search bị cấu hình sai.
- Tách quyền search khỏi quyền đọc hồ sơ chi tiết.
- Có thể rebuild projection từ database.

Đổi lại, một số endpoint cần gọi thêm database hoặc service để lấy chi tiết. Đây là tradeoff có chủ đích giữa độ trễ và giảm bề mặt dữ liệu nhạy cảm.

## 18. Masking dữ liệu trong response

Đôi khi người dùng được phép xem một phần dữ liệu nhưng không cần toàn bộ. Ví dụ hiển thị email đã che:

    a***@example.com

Masking nên được thực hiện trong lớp ứng dụng trước khi tạo response DTO:

    public record CustomerContactView(
        String name,
        String maskedEmail
    ) {}

    CustomerContactView toContactView(Customer customer) {
        return new CustomerContactView(
            customer.getName(),
            maskEmail(customer.getEmail())
        );
    }

Masking không xóa dữ liệu gốc khỏi Elasticsearch và không ngăn query trên field gốc. Nếu người gọi có thể truy vấn trực tiếp index, masking ở controller không bảo vệ index.

Không log giá trị chưa mask. Áp dụng masking nhất quán trong response, log, tracing, error report và DLQ.

## 19. Authorization trước khi tạo query

Nếu quyền truy cập phụ thuộc role hoặc tenant, backend cần xác định quyền trước khi chạy search.

Ví dụ:

    public Mono<CustomerSearchResponse> searchCustomers(
            UserPrincipal principal,
            CustomerSearchRequest request) {

        authorization.requireCustomerSearch(principal);

        boolean canReadEmail =
            authorization.canReadCustomerEmail(principal);

        Query query = buildCustomerQuery(
            request,
            canReadEmail
        );

        return operations.search(query, Customer.class)
            .flatMap(this::toResponse);
    }

Trong buildCustomerQuery, có thể chọn source includes khác nhau theo quyền:

    String[] includes = canReadEmail
        ? new String[] {"name", "email", "address.city"}
        : new String[] {"name", "address.city"};

Nhưng cần bảo đảm mapping DTO cũng tuân theo quyền. Không chỉ ẩn email trong source filter rồi trả entity đầy đủ cho serializer.

Authorization phải dựa trên principal đã xác thực và policy phía server. Không tin cờ canReadEmail do client gửi.

## 20. Tenant isolation và document-level filtering

Nếu document thuộc tenant, mọi query phải giới hạn đúng tenant:

    Query query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .filter(f -> f
                    .term(t -> t
                        .field("tenantId")
                        .value(tenantId)
                    )
                )
                .filter(f -> f
                    .match(m -> m
                        .field("name")
                        .query(searchText)
                    )
                )
            )
        )
        .build();

tenantId phải được lấy từ security context đã xác thực, không lấy tùy ý từ request parameter mà không kiểm tra.

Source filtering không ngăn document của tenant khác xuất hiện nếu query không có tenant filter. Dùng document-level security ở Elasticsearch khi principal truy cập trực tiếp và cần enforcement ở cluster, đồng thời vẫn giữ authorization trong backend.

Nếu dùng aliases, routing hoặc nhiều index theo tenant, cần kiểm tra mọi đường query, get, update, aggregation và bulk có giữ tenant boundary hay không.

## 21. Field-level security ở Elasticsearch

Elasticsearch có các cơ chế security để giới hạn field mà một role được đọc, tùy phiên bản và license/deployment. Field-level security có thể áp dụng allowlist hoặc denylist field cho principal.

Khác với source filtering:

- Source filtering do từng request lựa chọn.
- Field-level security gắn với quyền của principal.
- Nếu principal bị giới hạn field, query/fetch theo field bị cấm phải bị security layer ngăn theo semantics của cấu hình.

Field-level security cần được cấu hình ở role/security layer và kiểm thử bằng đúng credentials của từng role. Không chỉ test qua admin user, vì admin có thể nhìn thấy mọi field và che giấu lỗi cấu hình quyền.

Hãy kiểm tra tính năng được hỗ trợ trong phiên bản và gói Elasticsearch đang triển khai. Nếu backend dùng một service account có quyền rộng, backend phải áp dụng authorization của ứng dụng và không cho client dùng trực tiếp credentials đó.

## 22. Document-level security và source filtering

Document-level security giới hạn document mà một role có thể truy cập. Ví dụ role của tenant A chỉ được search document có tenantId = A.

Field-level security giới hạn field có thể đọc. Hai cơ chế có thể kết hợp:

- Document-level security quyết định document nào được truy cập.
- Field-level security quyết định field nào được truy cập trong document đó.
- Source filtering quyết định request muốn lấy subset source nào trong phạm vi được phép.

Source filtering không thay thế hai cơ chế đầu. Nếu query có thể đọc field hoặc document ngoài phạm vi, hãy sửa security policy và query authorization.

## 23. Mapping field và index:false

Nếu một field không cần query, có thể cấu hình index:false:

    PUT customers
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text"
          },
          "internalReference": {
            "type": "keyword",
            "index": false
          }
        }
      }
    }

index:false ngăn field được lập inverted index theo semantics của field type, nhưng field vẫn có thể nằm trong _source. Với một số kiểu dữ liệu, doc values hoặc stored behavior cần được xem xét riêng.

Vì vậy:

- index:false không có nghĩa field bị xóa khỏi source.
- Source excludes không có nghĩa field không được index.
- Cả hai đều không tự tạo authorization.

Nếu field không cần tồn tại trong Elasticsearch, đừng gửi field đó trong document. Đây là cách giảm bề mặt dữ liệu rõ ràng nhất.

## 24. Mapping _source excludes và khả năng reindex

Reindex API thường đọc source document từ index nguồn rồi index sang index đích. Nếu một field bị loại khỏi stored _source, reindex từ source đó không thể tự khôi phục field đã bị loại.

Ví dụ:

    POST _reindex
    {
      "source": {
        "index": "customers-v1"
      },
      "dest": {
        "index": "customers-v2"
      }
    }

Nếu customers-v1 đã loại internalReference khỏi _source, index mới sẽ không có giá trị đó trừ khi lấy lại từ nguồn khác hoặc có cách truy xuất phù hợp.

Trước khi cấu hình mapping-time excludes hoặc tắt _source, hãy kiểm tra:

- Có cần reindex không?
- Có cần update_by_query không?
- Có cần export dữ liệu gốc không?
- Có cần khôi phục index sau sự cố không?
- Có nguồn authoritative khác để dựng lại document không?

Không đánh đổi khả năng recovery chỉ để giảm một response payload.

## 25. Không dùng @JsonIgnore như security boundary

Một số ứng dụng dùng Jackson annotation:

    @JsonIgnore
    private String internalNote;

Annotation này có thể ảnh hưởng quá trình serialize/deserialize qua Jackson, nhưng Spring Data Elasticsearch sử dụng mapping/conversion infrastructure riêng. Không nên giả định @JsonIgnore chắc chắn ngăn field được ghi vào hoặc đọc từ _source trong mọi cấu hình.

Tương tự, @Transient của Spring Data có semantics mapping riêng nhưng không phải cơ chế xóa field đã tồn tại khỏi index cũ.

Hãy kiểm tra mapping và source thực tế bằng request Elasticsearch. Nếu field không được phép lưu, hãy loại nó khỏi model/document được gửi vào Elasticsearch hoặc dùng mapping/converter được cấu hình rõ ràng.

## 26. Sử dụng projection để tránh tải dữ liệu không cần

Nếu chỉ cần vài field, có thể tạo projection interface hoặc DTO tùy API Spring Data hỗ trợ. Tuy nhiên, projection ở tầng repository và source filtering không hoàn toàn giống nhau.

Một DTO read model rõ ràng:

    public record CustomerListItem(
        String id,
        String name,
        String city
    ) {}

Service:

    Flux<CustomerListItem> listCustomers(Query query) {
        return operations.search(query, Customer.class)
            .flatMapMany(ReactiveSearchHits::getSearchHits)
            .map(hit -> {
                Customer customer = hit.getContent();
                return new CustomerListItem(
                    hit.getId(),
                    customer.getName(),
                    customer.getAddress().getCity()
                );
            });
    }

Ví dụ reactive này chỉ là pattern tổng quát. Nếu source filter không lấy address.city, getter có thể null. Hãy chọn includes phù hợp với projection.

Projection giúp xác định field response cần thiết. Source filtering giảm dữ liệu được fetch. Kết hợp hai cơ chế khi cần.

## 27. Search response có thể lộ field qua nhiều kênh

Ngay cả khi _source bị filter, field có thể lộ qua:

- fields hoặc docvalue_fields.
- stored_fields.
- highlight.
- inner_hits.
- script_fields.
- sort values hoặc aggregation buckets.
- error messages và debug logs.
- explain/profile output.

Ví dụ nếu email bị ẩn khỏi _source nhưng query có aggregation terms theo email.keyword, response aggregation có thể liệt kê email.

Vì vậy, bảo vệ dữ liệu cần xem toàn bộ search response, không chỉ _source. Endpoint public nên định nghĩa rõ query capabilities và response DTO, không cho client truyền tự do field name, aggregation hoặc script.

## 28. Không cho client tự chọn field tùy ý

Một API như:

    GET /customers/search?fields=name,email,internalNote

có thể tạo rủi ro nếu backend chuyển trực tiếp giá trị fields thành source includes mà không kiểm tra quyền.

Thay vào đó:

- Định nghĩa các response shape được hỗ trợ.
- Map từng response shape sang allowlist field.
- Kiểm tra role/tenant trước khi chọn shape.
- Chặn field nhạy cảm khỏi query/sort/aggregation nếu caller không được phép.
- Không cho phép script hoặc field name tùy ý từ client.

Ví dụ:

    enum CustomerView {
        SUMMARY,
        CONTACT,
        ADMIN
    }

Backend quyết định field dựa trên CustomerView sau khi xác thực principal và kiểm tra quyền. Client không được tự nâng quyền bằng cách gửi ADMIN.

## 29. Kiểm tra dữ liệu thực tế trong _source

Khi đánh giá một mapping hoặc source filter, kiểm tra response thực tế:

    GET customers/_doc/c-100

Để kiểm tra source filtering:

    GET customers/_search
    {
      "_source": [
        "name",
        "address.city"
      ],
      "query": {
        "ids": {
          "values": [
            "c-100"
          ]
        }
      }
    }

Kiểm tra mapping:

    GET customers/_mapping

Kiểm tra field capabilities hoặc mapping của field để hiểu field được index, lưu doc values hay có analyzer nào.

Trong môi trường test, tạo document có giá trị giả đại diện cho field nhạy cảm và xác nhận:

- Search response không chứa field ngoài allowlist.
- DTO không serialize field nội bộ.
- Query không được phép không thể dùng field bị hạn chế.
- Role có quyền thấp không thể lấy field bằng request trực tiếp.
- Các API get, search, aggregation và export đều tuân theo quyền.

Không dùng dữ liệu cá nhân thật để kiểm thử log hoặc response nếu không cần thiết.

## 30. Kiểm thử source filtering trong Spring Data

Một integration test có thể lưu document rồi query với source filter:

    @Test
    void searchReturnsOnlySelectedSourceFields() {
        Customer customer = new Customer();
        customer.setId("c-test-1");
        customer.setName("Test Customer");
        customer.setEmail("test@example.com");
        customer.setInternalNote("private");

        operations.save(customer);
        operations.indexOps(Customer.class).refresh();

        Query query = NativeQuery.builder()
            .withQuery(q -> q
                .ids(ids -> ids.values("c-test-1"))
            )
            .withSourceFilter(
                new FetchSourceFilter(
                    new String[] {"name"},
                    null
                )
            )
            .build();

        SearchHits<Customer> hits =
            operations.search(query, Customer.class);

        assertThat(hits.getSearchHits()).hasSize(1);
        assertThat(hits.getSearchHit(0).getContent().getName())
            .isEqualTo("Test Customer");
    }

Đây là ví dụ theo API imperative và builder thường gặp. Constructor, query builder và phương thức refresh phụ thuộc Spring Data Elasticsearch version.

Test này xác nhận source filter được áp dụng cho query. Nó không chứng minh field email được bảo mật trước mọi API hoặc principal khác. Cần test security role riêng.

## 31. Kiểm thử không rò rỉ response

Test controller/service nên kiểm tra JSON cuối cùng:

    mockMvc.perform(get("/customers/search"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$[0].name").exists())
        .andExpect(jsonPath("$[0].email").doesNotExist())
        .andExpect(jsonPath("$[0].internalNote").doesNotExist());

Với WebFlux, dùng WebTestClient để kiểm tra response tương ứng.

Đừng chỉ kiểm tra Java DTO không có getter. Jackson có thể serialize field qua accessor hoặc annotation khác. Kiểm tra JSON thực tế là cách xác nhận contract response.

Nếu endpoint có role khác nhau, viết test cho từng role và từng response shape. Test bằng service account quản trị không thể chứng minh user thường bị giới hạn đúng.

## 32. Bảo vệ log, tracing và exception

Source filtering giảm payload search nhưng dữ liệu nhạy cảm vẫn có thể xuất hiện ở nơi khác:

- Log toàn bộ entity trước hoặc sau save.
- Log request/response Elasticsearch.
- Trace attributes chứa query hoặc source.
- Exception message chứa giá trị field.
- DLQ lưu raw event.
- Debug dump trong test hoặc local development.

Thiết kế logging:

- Log ID kỹ thuật hoặc correlation ID khi phù hợp.
- Mask hoặc bỏ field nhạy cảm.
- Không log access token, password hoặc credential.
- Hạn chế log query/source nguyên văn.
- Kiểm soát quyền truy cập và retention của log.
- Dùng synthetic/test data trong môi trường development.

Nếu DLQ cần lưu payload để replay, hãy mã hóa và hạn chế quyền đọc. Có thể lưu payload ở storage riêng và chỉ giữ reference cùng error metadata trong DLQ.

## 33. Dữ liệu nhạy cảm và encryption

Encryption at rest bảo vệ dữ liệu khi storage bị truy cập trái phép ở mức hạ tầng, nhưng không tự ngăn một user đã được cấp quyền search đọc field trong response.

TLS bảo vệ dữ liệu khi truyền giữa ứng dụng và Elasticsearch, nhưng không thay thế authorization.

Nếu một field cần được lưu nhưng không được Elasticsearch hoặc operator đọc dạng plaintext, cân nhắc mã hóa field ở tầng ứng dụng trước khi index. Cần hiểu tradeoff:

- Field đã mã hóa thường không thể full-text search như plaintext.
- Equality lookup có thể cần deterministic token/hash riêng, nhưng deterministic value có thể làm lộ quan hệ bằng nhau.
- Key rotation và reindex cần được thiết kế.
- Không lưu encryption key trong cùng index.
- Cần phân quyền key management độc lập.

Không tự thiết kế thuật toán mã hóa. Dùng thư viện và key management được đánh giá phù hợp với hệ thống.

## 34. Source filtering trong multi-index và alias

Một query có thể chạy trên alias trỏ nhiều index. Mapping và cấu trúc source giữa các index có thể khác nhau.

Nếu source filter gồm:

    "_source": {
      "includes": [
        "name",
        "address.city"
      ]
    }

thì field có thể tồn tại ở index này nhưng thiếu ở index khác. Khi Spring Data ánh xạ tất cả vào cùng entity, property có thể null hoặc có kiểu khác nếu mapping drift.

Với alias chuyển index version, hãy giữ source contract tương thích hoặc dùng DTO/converter xử lý version khác nhau. Kiểm tra mapping của mọi index đằng sau alias.

Source filtering không giải quyết xung đột mapping giữa nhiều index.

## 35. Nested object và source filtering

Với nested data:

    {
      "name": "Keyboard",
      "offers": [
        {
          "seller": "Store A",
          "price": 120,
          "internalMargin": 20
        },
        {
          "seller": "Store B",
          "price": 95,
          "internalMargin": 15
        }
      ]
    }

Có thể chọn:

    "_source": {
      "includes": [
        "name",
        "offers.seller",
        "offers.price"
      ]
    }

Nhưng cần kiểm tra cấu trúc response và việc ánh xạ List<Offer> khi một số field của Offer không được trả. internalMargin có thể null trong entity partial.

Nếu endpoint public chỉ cần seller và price, hãy dùng DTO OfferView thay vì trả entity Offer đầy đủ. Nếu inner_hits được yêu cầu, kiểm soát source filter của inner hits riêng theo API hỗ trợ; source filter ở cấp hit cha không nhất thiết thay thế cấu hình response cho mọi phần nested result.

## 36. Dữ liệu nhạy cảm trong aggregation và sort

Ẩn field khỏi _source không ngăn aggregation hoặc sort trên field đó nếu mapping và quyền cho phép.

Ví dụ:

    GET customers/_search
    {
      "size": 0,
      "aggs": {
        "by_email": {
          "terms": {
            "field": "email.keyword"
          }
        }
      }
    }

Response aggregation có thể chứa email dù source không được trả.

Nếu email không được phép tiết lộ, không cho endpoint nhận aggregation tùy ý trên email. Giới hạn aggregation fields theo allowlist và authorization. Với Elasticsearch trực tiếp, dùng field-level security phù hợp để enforcement ở cluster.

## 37. Chọn cơ chế theo mục tiêu

| Mục tiêu | Cách tiếp cận |
|---|---|
| Giảm response size cho một query | Request-time source filtering |
| Chỉ trả field public từ service | DTO/projection allowlist |
| Không lưu field không cần trong index | Loại field khỏi document trước khi index |
| Không index field nhưng vẫn lưu source | Mapping index:false, sau khi đánh giá nhu cầu |
| Không lưu một field trong stored source | Mapping _source excludes, sau khi đánh giá reindex/recovery |
| Không cho role đọc field | Field-level security hoặc quyền tương đương |
| Không cho role đọc document | Document-level security hoặc tenant authorization |
| Bảo vệ dữ liệu khi lưu/truyền | Encryption at rest/TLS và key management |
| Chỉ hiển thị một phần giá trị | Masking ở tầng ứng dụng |
| Không đưa bí mật vào search | Giữ bí mật ngoài Elasticsearch |

Không có một tùy chọn _source duy nhất giải quyết tất cả mục tiêu. Hãy chọn cơ chế phù hợp với ranh giới dữ liệu và threat model.

## 38. Những lỗi thường gặp

### Nghĩ source filtering bảo mật field

Source filter chỉ ảnh hưởng response của request. Caller có quyền phù hợp có thể dùng query khác hoặc API khác. Dùng authorization và field-level security.

### Dùng excludes như denylist cố định

Field mới có thể bị trả ra nếu danh sách excludes không được cập nhật. Với public response, dùng includes allowlist và DTO.

### Ẩn field khỏi _source nhưng vẫn cho aggregation

Field vẫn có thể lộ qua aggregation, sort, fields hoặc script. Kiểm soát query capability và security policy.

### Trả entity persistence trực tiếp

Entity có thể chứa field nội bộ và được mở rộng trong tương lai. Map sang DTO riêng cho từng response shape.

### Save lại entity partial

Field không được source filter trả về có thể bị null và ghi đè khi save toàn bộ document. Dùng DTO read-only và partial update.

### Tắt _source chỉ để giảm payload

Tắt source làm mất khả năng lấy lại source và ảnh hưởng reindex/update. Dùng request-time source filtering nếu chỉ cần giảm payload.

### Dùng mapping _source excludes như authorization

Field vẫn có thể được index và truy vấn. Đây không phải field-level security.

### Tin rằng @JsonIgnore điều khiển Spring Data mapping

Spring Data Elasticsearch dùng converter riêng. Kiểm tra mapping và source thực tế, không dựa vào annotation Jackson như security boundary.

### Cho client truyền fields tùy ý

Client có thể yêu cầu field nhạy cảm. Dùng response shape allowlist và authorization phía server.

### Bỏ qua fields/inner_hits/highlight

Field nhạy cảm có thể lộ qua các phần response ngoài _source. Kiểm tra toàn bộ response.

### Log raw source

Log, tracing và DLQ có thể trở thành nơi rò rỉ dữ liệu. Mask, redact và giới hạn quyền/retention.

### Dùng service account có quyền rộng mà không kiểm tra user

Backend cần enforce authorization của người dùng trước khi query. Không để quyền của service account trở thành quyền mặc định của mọi caller.

## 39. Quy trình thiết kế response an toàn

Khi tạo search endpoint:

1. Xác định field nào thực sự cần cho response.
2. Phân loại field public, internal, confidential và secret.
3. Không đưa secret vào Elasticsearch nếu không có lý do mạnh.
4. Kiểm tra quyền của principal và tenant trước khi query.
5. Tạo allowlist source includes theo use case.
6. Map kết quả sang DTO riêng, không trả entity đầy đủ.
7. Kiểm tra query, sort, aggregation, highlight, inner_hits và fields có thể làm lộ dữ liệu không.
8. Không cho client tự chọn field/query capability ngoài allowlist.
9. Dùng field/document-level security nếu principal truy cập trực tiếp Elasticsearch.
10. Kiểm tra log, trace, exception và DLQ để tránh lộ source.
11. Không dùng entity partial cho save/update toàn document.
12. Kiểm thử JSON response và security role thực tế.
13. Đánh giá ảnh hưởng của mapping _source settings lên reindex và recovery.

## Kết luận

Source filtering cho phép Elasticsearch chỉ trả một phần _source bằng includes và excludes. Trong Spring Data Elasticsearch, có thể cấu hình source filter trên query rồi map SearchHit sang DTO. Includes allowlist phù hợp hơn cho response public vì field mới không tự xuất hiện nếu chưa được cho phép. Tuy nhiên, source filtering chỉ giảm payload và không phải authorization: field vẫn có thể được dùng trong query, sort, aggregation, fields hoặc các kênh response khác nếu mapping và quyền cho phép.

Để bảo vệ dữ liệu nhạy cảm, hãy kiểm tra quyền người dùng ở backend, giới hạn document/field ở Elasticsearch khi cần, không index bí mật không cần thiết, dùng DTO allowlist và mask log/tracing/DLQ. Mapping-time _source excludes hoặc tắt _source có tác động lâu dài đến reindex và recovery, nên không dùng chỉ để ẩn field trong một endpoint. Tránh save lại entity được đọc bằng source filter vì field bị bỏ có thể bị ghi đè. Kiểm tra toàn bộ response và đúng security role bằng integration test để bảo đảm dữ liệu không rò rỉ qua những đường khác ngoài _source.
