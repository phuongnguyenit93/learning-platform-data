# Tách quyền quản lý index khỏi quyền đọc ghi tài liệu

Trong Elasticsearch, thao tác với document và thao tác quản lý index có mức ảnh hưởng rất khác nhau. Một ứng dụng nghiệp vụ thường chỉ cần tìm kiếm, đọc, tạo, cập nhật hoặc xóa document trong những index đã được chuẩn bị. Việc tạo index, thay đổi mapping, settings, analyzer, alias hoặc xóa index thường thuộc trách nhiệm của quy trình triển khai hay công cụ quản trị.

Nếu dùng chung một tài khoản có quyền quản trị index cho mọi thao tác runtime, một lỗi cấu hình hoặc lỗ hổng trong ứng dụng có thể gây ảnh hưởng đến schema và dữ liệu của cả index. Vì vậy, nên tách danh tính và quyền thành hai nhóm:

- **Runtime application:** chỉ có quyền đọc/ghi document trên các index mà ứng dụng cần sử dụng.
- **Index provisioning/migration:** có quyền tạo index, quản lý mapping/settings và thực hiện migration hoặc thay đổi alias theo phạm vi được giao.

Đây là cách áp dụng nguyên tắc đặc quyền tối thiểu (*least privilege*). Ứng dụng chỉ được cấp những quyền cần thiết để thực hiện nghiệp vụ, còn quyền thay đổi cấu trúc index được giới hạn cho quy trình có kiểm soát.

## 1. Phân biệt document và index

Elasticsearch tổ chức dữ liệu trong index. Một index chứa các document có cấu trúc JSON; mapping xác định cách field được lập chỉ mục và truy vấn.

Có thể chia thao tác thành hai nhóm:

| Nhóm thao tác | Ví dụ | Mục đích |
|---|---|---|
| Đọc/ghi document | Search, get, index, update, delete document, bulk | Xử lý dữ liệu nghiệp vụ |
| Quản lý index | Create/delete index, mapping, settings, analyzer, alias | Quản lý cấu trúc và vòng đời dữ liệu |

Ví dụ:

- API tìm sản phẩm gọi search trên index products.
- API cập nhật giá gọi update hoặc index document trong products.
- Quy trình triển khai tạo index products_v2 với mapping mới.
- Quy trình migration reindex dữ liệu từ products_v1 sang products_v2.
- Sau khi xác minh, quy trình chuyển alias products sang index mới.

Ba thao tác đầu tiên của ứng dụng nghiệp vụ không cần quyền tạo hoặc xóa index. Các thao tác cuối cùng thay đổi cấu trúc hoặc định tuyến dữ liệu nên cần quyền quản trị phù hợp.

Index là ranh giới quan trọng để cấp quyền trong Elasticsearch. Quyền thường được gán cho một hoặc nhiều tên index, alias hoặc data stream thông qua role. Vì vậy, có thể giới hạn ứng dụng chỉ được truy cập products thay vì cấp quyền trên mọi index trong cluster.

## 2. Elasticsearch security phân quyền như thế nào?

Elasticsearch Security sử dụng role-based access control (RBAC). Người dùng hoặc API key được gắn với các quyền thông qua role hoặc role descriptor. Một role có thể chứa:

- **Cluster privileges:** quyền ở phạm vi cluster, ví dụ một số thao tác quản trị hoặc giám sát cluster.
- **Index privileges:** quyền trên các index, alias hoặc data stream có tên khớp với phạm vi được khai báo.
- Các phạm vi quyền khác nếu tính năng bảo mật và phiên bản hỗ trợ, chẳng hạn quyền ứng dụng hoặc quyền không gian Kibana.

Trong bài toán này, cần chú ý đến index privileges. Một số quyền thường gặp:

| Privilege | Ý nghĩa khái quát |
|---|---|
| read | Đọc document, search và các thao tác đọc tương ứng |
| write | Thực hiện các thao tác ghi document như index, update và delete |
| create_doc | Tạo document theo chế độ create, không cho phép ghi đè document đã tồn tại theo cách thông thường |
| index | Ghi document theo phạm vi quyền index được cấp |
| delete | Xóa document |
| view_index_metadata | Đọc metadata của index như mapping/settings ở phạm vi được cho phép |
| create_index | Tạo index |
| delete_index | Xóa index |
| manage | Quản lý index, bao gồm nhiều thao tác về mapping và settings |
| manage_aliases | Quản lý alias |

Đây là các quyền ở những mức khác nhau. Không nên đồng nhất quyền write document với quyền tạo index. Cấp write không có nghĩa ứng dụng được tự ý tạo hoặc xóa index.

Danh sách quyền và các action được bao phủ có thể thay đổi theo phiên bản Elasticsearch. Khi thiết kế role cho một API cụ thể, cần đối chiếu privilege với action mà API thực hiện trong phiên bản cluster đang chạy. Không nên đoán quyền chỉ từ tên phương thức Java.

## 3. Role cho ứng dụng runtime chỉ đọc và ghi document

Giả sử ứng dụng bán hàng sử dụng index products. Ứng dụng cần:

- Tìm kiếm sản phẩm.
- Đọc document theo id.
- Tạo sản phẩm mới.
- Cập nhật sản phẩm.
- Xóa document khi nghiệp vụ yêu cầu.

Ứng dụng có thể được cấp role chỉ gồm read và write trên index products:

    PUT /_security/role/products_runtime
    {
      "cluster": [],
      "indices": [
        {
          "names": [ "products" ],
          "privileges": [ "read", "write" ]
        }
      ]
    }

Role này thể hiện rõ phạm vi sử dụng:

- Ứng dụng được đọc và ghi document trong products.
- Ứng dụng không được cấp manage hoặc delete_index.
- Ứng dụng không được quản lý alias hoặc tạo index chỉ vì cần thực hiện CRUD.
- Ứng dụng không có cluster privilege trong ví dụ.

Nếu ứng dụng chỉ cần đọc, có thể chỉ cấp read. Nếu ứng dụng chỉ tạo document mới và không cần cập nhật hoặc xóa, có thể cân nhắc quyền hẹp hơn như create_doc, sau khi kiểm tra các thao tác thực tế mà client sử dụng.

### Có cần view_index_metadata không?

Một số ứng dụng hoặc thư viện cần đọc metadata index để kiểm tra mapping, settings, alias hoặc trạng thái index. Khi đó có thể cần cấp thêm view_index_metadata trên đúng phạm vi index.

Không nên thêm quyền này theo thói quen nếu runtime chỉ gọi các document API và không cần đọc metadata. Hãy kiểm tra log lỗi authorization và các API mà phiên bản Spring Data/client thực sự gọi.

Ví dụ role có thêm quyền đọc metadata:

    PUT /_security/role/products_runtime
    {
      "cluster": [],
      "indices": [
        {
          "names": [ "products" ],
          "privileges": [
            "read",
            "write",
            "view_index_metadata"
          ]
        }
      ]
    }

Chỉ cấp view_index_metadata khi có yêu cầu thực tế. Quyền này không tương đương manage: nó cho phép đọc một số metadata, không cấp quyền thay đổi mapping hoặc settings.

## 4. Role cho quy trình tạo và quản lý index

Quy trình provisioning hoặc migration có thể cần thực hiện các công việc:

- Kiểm tra index đã tồn tại hay chưa.
- Tạo index với settings và mapping được duyệt.
- Thêm field hoặc cập nhật mapping trong giới hạn Elasticsearch cho phép.
- Đóng/mở index nếu migration yêu cầu.
- Tạo index phiên bản mới.
- Đọc dữ liệu từ index nguồn và ghi dữ liệu sang index đích khi reindex.
- Chuyển alias sau khi xác minh dữ liệu.

Những thao tác này cần quyền index-management tương ứng. Ví dụ một role quản lý index có thể được khai báo:

    PUT /_security/role/products_index_migration
    {
      "cluster": [],
      "indices": [
        {
          "names": [ "products", "products-*" ],
          "privileges": [
            "manage",
            "manage_aliases",
            "create_index",
            "read",
            "write"
          ]
        }
      ]
    }

Ví dụ trên minh họa một identity dành riêng cho migration. Phạm vi tên index được giới hạn vào products và các index phiên bản products-*. Quyền read/write được dùng khi quy trình cần đọc index nguồn hoặc ghi dữ liệu vào index đích; quyền quản lý index phục vụ tạo và thay đổi cấu trúc.

Role thực tế nên được thu hẹp theo các bước migration cần chạy. Nếu một quy trình chỉ tạo index mới, không cần cấp quyền xóa index cũ. Nếu không chuyển alias, không cần cấp manage_aliases. Nếu công cụ chỉ thêm mapping field được phép, hãy chọn privilege hẹp nhất được phiên bản Elasticsearch hỗ trợ thay vì cấp quyền quản trị rộng hơn.

Privilege manage có phạm vi rộng trên index. Nó có thể cho phép nhiều thao tác quản trị như thay đổi mapping và settings. Do đó, nên chỉ cấp cho tài khoản migration/provisioning và giới hạn names chính xác. Không gắn role này cho tài khoản mà ứng dụng runtime sử dụng.

Các ví dụ role cần được kiểm tra theo phiên bản và action cụ thể. API tạo index, cập nhật mapping, thay đổi alias, reindex và xóa index có thể yêu cầu tập quyền khác nhau. Một quy trình production nên thử role trên môi trường kiểm thử và xác nhận cả thao tác được phép lẫn thao tác phải bị từ chối.

## 5. Tách danh tính và credentials trong kiến trúc ứng dụng

Chỉ tạo hai role nhưng vẫn dùng chung một user có cả hai role thì chưa đạt mục tiêu phân tách. Danh tính runtime và danh tính provisioning cần được cấp riêng.

Một mô hình triển khai:

    Spring Boot application
       |
       | API key: products_runtime
       v
    Elasticsearch
       |
       +-- products_runtime role
       |      read / write documents
       |
       +-- products_index_migration role
              create index
              manage mapping/settings
              manage aliases

Hai credential được sử dụng ở hai nơi:

| Credential | Nơi sử dụng | Mục đích |
|---|---|---|
| Runtime credential | Ứng dụng đang phục vụ request | Đọc/ghi document |
| Migration credential | Pipeline triển khai hoặc job migration | Tạo index và thay đổi schema |

Không nên đặt migration credential trong cấu hình runtime chỉ để ứng dụng có thể tự tạo index. Nếu runtime có thể truy cập credential quản trị, một lỗi trong ứng dụng có thể sử dụng quyền đó dù role runtime được thiết kế hẹp.

Có thể sử dụng user riêng hoặc API key riêng cho mỗi mục đích. API key có thể mang role descriptor giới hạn quyền và phạm vi index. Dù chọn cơ chế nào, credential cần được quản lý như secret: lưu trong secret manager hoặc hệ thống quản lý secret của môi trường, luân chuyển khi cần và không commit vào Git.

### Cấu hình Spring Boot cho runtime

Ứng dụng chỉ nhận runtime credential:

    spring:
      elasticsearch:
        uris: https://elasticsearch.example.internal:9200

Đây là ví dụ cấu hình địa chỉ cluster. Credential có thể được cung cấp qua secret-backed configuration và cơ chế authentication tương ứng của phiên bản Spring Boot/client đang dùng. Nếu dùng API key hoặc custom client configuration, cấu hình header và credential theo cơ chế tương ứng.

Các biến môi trường runtime chỉ chứa credential có quyền read/write trên index được phép. Pipeline migration có bộ secret riêng và không truyền credential quản trị vào process phục vụ request.

## 6. Tách tự động tạo index khỏi thao tác CRUD của Spring Data

Spring Data Elasticsearch có thể tự tạo index theo metadata của entity trong một số cấu hình. Điều này thuận tiện cho ví dụ nhỏ hoặc môi trường phát triển, nhưng có thể làm ứng dụng runtime cần thêm quyền tạo index và mapping.

Ví dụ entity:

    @Document(
        indexName = "products",
        createIndex = false
    )
    public class Product {

        @Id
        private String id;

        @Field(type = FieldType.Text)
        private String name;

        @Field(type = FieldType.Keyword)
        private String category;
    }

Đặt createIndex = false thể hiện ứng dụng không yêu cầu cơ chế repository tự tạo index cho entity này. Mapping và settings cần được chuẩn bị trước bởi quy trình provisioning.

Sau khi index đã tồn tại, runtime repository vẫn có thể thực hiện các thao tác document theo quyền read/write:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        List<Product> findByCategory(String category);
    }

Việc tách lifecycle có thể được tổ chức như sau:

    Deployment / migration pipeline
       |
       | Migration credential
       v
    Create index + settings + mapping
       |
       v
    Verify index
       |
       v
    Deploy application
       |
       | Runtime credential
       v
    Repository CRUD and search

Nếu index đã được tạo bằng script hoặc migration, runtime không cần quyền quản lý schema để sử dụng repository. Converter vẫn sử dụng metadata entity để chuyển đổi document; createIndex = false không vô hiệu hóa mapping metadata.

### IndexOperations nên nằm ở đâu?

Các thao tác như:

    IndexOperations indexOperations =
        operations.indexOps(Product.class);

    indexOperations.createWithMapping();

hoặc:

    indexOperations.putMapping();

thuộc quy trình quản lý index. Nếu chạy chúng bằng runtime credential chỉ có read/write, Elasticsearch có thể từ chối do thiếu quyền. Đó là hành vi đúng theo thiết kế phân quyền.

Nên gọi các thao tác provisioning bằng migration credential trong một job có kiểm soát, hoặc thông qua công cụ quản trị riêng. Service nghiệp vụ không nên gọi createWithMapping mỗi khi nhận request người dùng.

## 7. Quyền cần thiết cho các thao tác phổ biến

Bảng dưới đây giúp định hướng việc phân quyền. Đây là mức phân loại nghiệp vụ; privilege chính xác cần đối chiếu action mà API phát ra trên phiên bản Elasticsearch đang sử dụng.

| Thao tác | Nhóm quyền thường cần | Nơi nên thực hiện |
|---|---|---|
| Search document | read | Runtime |
| Get document theo id | read | Runtime |
| Index document | write hoặc quyền ghi hẹp phù hợp | Runtime |
| Update document | write | Runtime |
| Delete document | write hoặc delete tùy API và quyền được chọn | Runtime |
| Bulk ghi document | read/write theo các action trong bulk | Runtime |
| Đọc mapping/settings | view_index_metadata | Migration hoặc runtime nếu thật sự cần |
| Tạo index | create_index | Provisioning |
| Thay đổi mapping | Quyền quản lý mapping, thường là manage | Provisioning |
| Thay đổi settings | Quyền quản lý index tương ứng, thường là manage | Provisioning |
| Xóa index | delete_index hoặc quyền quản lý bao phủ action đó | Provisioning có kiểm soát |
| Quản lý alias | manage_aliases hoặc quyền quản lý bao phủ action đó | Provisioning |
| Reindex | read ở nguồn, write ở đích; thêm quyền tạo/quản lý index nếu cần | Migration |

Một API có thể thực hiện nhiều action. Ví dụ repository initialization có thể kiểm tra index, đọc metadata hoặc tạo mapping tùy cấu hình. Vì vậy, không nên chỉ nhìn tên phương thức repository rồi kết luận privilege chính xác.

## 8. Ví dụ quy trình migration an toàn

Giả sử phiên bản hiện tại sử dụng alias products trỏ đến index products-v1. Phiên bản mới cần thay đổi mapping của field category từ text sang keyword.

Thay đổi field type không thể xử lý bằng cách ghi đè mapping trên index cũ theo cách thông thường. Quy trình migration có thể thực hiện:

1. Pipeline dùng migration credential tạo products-v2 với mapping mới.
2. Pipeline đọc dữ liệu từ products-v1 và ghi sang products-v2 bằng reindex hoặc quy trình chuyển đổi dữ liệu.
3. Nếu hệ thống vẫn tiếp tục ghi trong lúc reindex, pipeline phải đồng bộ các thay đổi phát sinh hoặc có chiến lược dừng ghi/cutover rõ ràng.
4. Kiểm tra số lượng document, dữ liệu lỗi và các truy vấn quan trọng trên products-v2.
5. Chuyển alias products sang index mới bằng quyền quản lý alias.
6. Ứng dụng runtime tiếp tục dùng alias products bằng credential read/write.
7. Chỉ xóa products-v1 sau khi hết thời gian rollback và có xác nhận phù hợp.

Runtime application không cần quyền tạo products-v2, reindex hay chuyển alias. Nó chỉ tiếp tục đọc/ghi qua alias đã được provisioning chuẩn bị.

### Vì sao alias hữu ích?

Alias tạo một tên ổn định cho ứng dụng trong khi index vật lý có thể thay đổi theo phiên bản. Ứng dụng không cần biết products-v1 hay products-v2 là index đang hoạt động.

Việc chuyển alias là thao tác quản trị và cần quyền phù hợp. Nếu ứng dụng runtime có thể tự thay đổi alias, một lỗi hoặc request không được kiểm soát có thể làm ứng dụng đọc/ghi nhầm index.

## 9. Kiểm tra phân quyền bằng cả thao tác được phép và bị từ chối

Sau khi tạo role, không chỉ kiểm tra rằng thao tác nghiệp vụ chạy thành công. Cần kiểm tra cả những thao tác mà runtime không được phép.

Ví dụ kiểm tra bằng credential runtime:

| Thử nghiệm | Kết quả mong đợi |
|---|---|
| Search products | Thành công |
| Get một document trong products | Thành công |
| Index/update document trong products | Thành công nếu role có write |
| Search index ngoài phạm vi products | Bị từ chối |
| Create index products_test | Bị từ chối |
| Update mapping của products | Bị từ chối |
| Delete index products | Bị từ chối |
| Thay đổi alias products | Bị từ chối |

Sau đó kiểm tra migration credential:

- Tạo index mới trong phạm vi được cấp.
- Tạo mapping và settings.
- Đọc nguồn và ghi đích khi reindex.
- Chuyển alias nếu migration cần.
- Thử truy cập một index ngoài phạm vi và xác nhận bị từ chối.

Elasticsearch thường trả lỗi authorization như HTTP 403 khi identity thiếu privilege cho action. Cần ghi lại endpoint/action bị từ chối để xác định quyền nào thực sự cần bổ sung. Không nên giải quyết lỗi bằng cách cấp all trên mọi index.

### Kiểm tra quyền bằng API

Elasticsearch Security cung cấp các API hỗ trợ kiểm tra quyền của user hoặc API key, tùy phiên bản và cơ chế xác thực. Có thể dùng API kiểm tra quyền để xác nhận identity có các privilege cần thiết trên resource cụ thể.

Ngoài kiểm tra API, nên thực hiện integration test bằng đúng credential runtime trong môi trường kiểm thử. Test cần mô phỏng cả request được phép và request quản trị phải bị từ chối.

## 10. Phạm vi index và alias cần được khai báo cẩn thận

Role giới hạn quyền theo names. Ví dụ:

    "names": [ "products" ]

chỉ thể hiện phạm vi tên products. Nếu ứng dụng dùng alias, data stream hoặc index có hậu tố phiên bản, cần khai báo đúng tên resource mà request thực tế truy cập.

Không nên dùng wildcard quá rộng như * nếu ứng dụng chỉ cần một nhóm index. Một role có names = ["*"] cùng privilege write hoặc manage có thể mở rộng ảnh hưởng sang các index khác trong cluster.

Với migration, có thể cần quyền trên cả index nguồn và index đích:

- Nguồn: read để đọc document.
- Đích: create_index/manage để tạo index và mapping; write để ghi document.
- Alias: quyền quản lý alias trên các index liên quan.

Nếu reindex qua nhiều index hoặc nhiều tenant, cần xác định chính xác pattern tên index và tránh cấp quyền vượt ra ngoài tenant hoặc miền dữ liệu của job.

## 11. Một số lưu ý về API key và quản lý secret

API key có thể được tạo với role descriptor giới hạn quyền và thời hạn sử dụng. Đây là cách hữu ích để cấp credential riêng cho runtime và migration.

Một số nguyên tắc:

- Tạo API key runtime với quyền read/write cần thiết trên index cụ thể.
- Tạo API key migration riêng cho pipeline provisioning.
- Đặt expiration và quy trình xoay vòng phù hợp.
- Không ghi API key vào source code, log, tài liệu hoặc file cấu hình được commit.
- Không truyền migration key vào container hoặc process runtime nếu ứng dụng không cần.
- Thu hồi key cũ khi rotate hoặc khi pipeline không còn sử dụng.

Nếu dùng user/password thay vì API key, cũng cần tách user theo mục đích và giới hạn role tương tự.

Không nên xem việc mã hóa kết nối HTTPS là thay thế cho phân quyền. TLS bảo vệ đường truyền; role và privilege quyết định identity được phép làm gì trên Elasticsearch.

## 12. Những nhầm lẫn thường gặp

### Nghĩ rằng write bao gồm quyền tạo index

write dành cho thao tác ghi document. Tạo index là thao tác quản lý index và cần privilege tương ứng như create_index. Không nên cấp quyền quản lý index chỉ vì service cần lưu document.

### Cấp manage cho ứng dụng để tránh lỗi 403

manage có phạm vi rộng và có thể cho phép thay đổi mapping/settings hoặc các thao tác quản trị khác. Nếu runtime chỉ cần search và CRUD, hãy cấp read/write trên đúng index.

### Dùng cùng một API key cho runtime và migration

Nếu key có quyền quản trị để migration hoạt động, runtime cũng có thể sử dụng các quyền đó. Tạo credential riêng để giới hạn blast radius khi runtime bị lỗi hoặc bị xâm nhập.

### Đặt createIndex = true nhưng chỉ cấp read/write

Nếu lifecycle repository cố gắng tạo index hoặc mapping khi khởi động, credential runtime có thể bị từ chối. Khi index do pipeline quản lý, đặt createIndex = false và provision index trước khi triển khai ứng dụng.

### Nghĩ rằng createIndex = false làm mất mapping metadata

Thuộc tính này điều khiển hành vi tạo index tự động. Spring Data vẫn cần metadata entity và converter để ánh xạ document khi đọc/ghi.

### Cấp quyền trên mọi index

Wildcard rộng làm tăng phạm vi ảnh hưởng của credential. Hãy dùng tên index, alias hoặc pattern hẹp theo ứng dụng và môi trường.

### Chỉ kiểm tra thao tác thành công

Một role có thể chạy được CRUD nhưng vẫn có quyền quản trị ngoài mong muốn. Hãy kiểm tra cả các thao tác tạo, sửa mapping, xóa index và thay đổi alias để chắc chắn runtime bị từ chối.

### Nghĩ rằng mọi API Spring Data chỉ gọi một action Elasticsearch

Một phương thức ở tầng Spring có thể kích hoạt nhiều request hoặc kiểm tra metadata tùy cấu hình và phiên bản. Khi gặp 403, cần xem action thực tế trong lỗi/log và cấp đúng privilege cần thiết.

## Kết luận

Đọc/ghi document và quản lý index là hai nhóm trách nhiệm cần được phân quyền riêng. Ứng dụng runtime thường chỉ cần read/write trên index hoặc alias mà nó sử dụng. Quy trình provisioning/migration mới cần các quyền như create_index, manage mapping/settings và manage_aliases trong phạm vi index được kiểm soát.

Trong Spring Data Elasticsearch, có thể đặt createIndex = false cho entity khi index được tạo bởi pipeline riêng. Runtime vẫn dùng repository hoặc ElasticsearchOperations để thao tác document bằng credential giới hạn. Tách user hoặc API key, giới hạn tên index, kiểm tra cả thao tác được phép lẫn bị từ chối và giữ migration credential ngoài process runtime giúp giảm rủi ro thay đổi schema hoặc xóa nhầm dữ liệu trong môi trường production.
