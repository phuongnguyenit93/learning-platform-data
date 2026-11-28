# @CompositeProperty, prefix, delimiter và quy tắc trải thuộc tính

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích cách Spring Data Neo4j ánh xạ một Map thành nhiều property trên node hoặc relationship.
- Dùng `@CompositeProperty` để cấu hình `prefix` và `delimiter`.
- Dự đoán tên property được lưu trong Neo4j từ tên field và key trong Map.
- Thiết kế nhiều nhóm thuộc tính động mà không gây trùng tên.
- Truy vấn, lập chỉ mục và bảo trì các composite property một cách có chủ đích.

## 1. Composite property giải quyết bài toán nào?

Trong một ứng dụng, có những nhóm thuộc tính không cố định hoàn toàn theo từng loại entity. Ví dụ, hồ sơ khách hàng có thể chứa các trường mở rộng như ngôn ngữ, múi giờ, kênh đăng ký hoặc mã từ hệ thống ngoài. Các nhóm thuộc tính này thường được biểu diễn tự nhiên bằng `Map` trong Java.

Nếu lưu Map như một giá trị lồng nhau, mô hình sẽ không phù hợp với cách Neo4j lưu property: property của node và relationship là các giá trị đơn hoặc danh sách giá trị được hỗ trợ, không phải một Map lồng tùy ý. Spring Data Neo4j (SDN) cung cấp `@CompositeProperty` để trải các entry của Map thành các property riêng trên node hoặc relationship.

Ví dụ, Map Java:

```java
Map<String, Object> contact = Map.of(
    "city", "Ho Chi Minh City",
    "postalCode", "700000"
);
```

được trải thành các property riêng. Ví dụ, câu lệnh Cypher có thể ghi chúng như sau:

```cypher
CREATE (c:Customer)
SET c.`contact.city` = "Ho Chi Minh City",
    c.`contact.postalCode` = "700000"
```

Trong Cypher, tên property có dấu chấm cần được đặt trong backtick khi viết trực tiếp, ví dụ ``c.`contact.city` ``. Dữ liệu không được lưu thành một property Map lồng nhau tên `contact`; mỗi entry trở thành một property riêng.

`@CompositeProperty` hữu ích khi tập key có thể thay đổi theo dữ liệu, nhưng ứng dụng vẫn muốn truy vấn từng giá trị như property thông thường của Neo4j.

## 2. Cách hoạt động của @CompositeProperty

Annotation `@CompositeProperty` được đặt trên field cần ánh xạ dạng Map. Mỗi key của Map được ghép với một prefix và delimiter để tạo tên property trên node hoặc relationship.

Các quy tắc mặc định:

- Nếu không cấu hình `prefix`, SDN sử dụng tên field Java làm prefix.
- Nếu không cấu hình `delimiter`, delimiter mặc định là dấu chấm `.`.
- Key của Map được nối sau prefix và delimiter.
- Giá trị được xử lý qua cơ chế conversion của SDN trước khi ghi vào Neo4j.

Ví dụ:

```java
import java.util.Map;

import org.springframework.data.neo4j.core.schema.CompositeProperty;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Customer")
public class Customer {

    @Id
    private String id;

    @CompositeProperty
    private Map<String, Object> contact = Map.of(
        "city", "Ho Chi Minh City",
        "postalCode", "700000"
    );
}
```

Vì field tên `contact` và dùng cấu hình mặc định, các key được trải thành:

| Field và key trong Java | Property trong Neo4j |
| --- | --- |
| `contact["city"]` | `contact.city` |
| `contact["postalCode"]` | `contact.postalCode` |

Có thể hình dung quy tắc tạo tên như sau:

```text
propertyName = prefix + delimiter + mapKey
```

Với cấu hình mặc định, `prefix` chính là tên field và `delimiter` là dấu chấm.

Lưu ý: `@CompositeProperty` không biến Map thành JSON và không tạo một node con. Nó trải các entry thành property của chính node hoặc relationship đang chứa field đó.

## 3. Cấu hình prefix

Thuộc tính `prefix` xác định phần tên chung đứng trước key của Map. Nếu không chỉ định hoặc để giá trị mặc định, SDN lấy tên field làm prefix. Khi muốn tên property trong Neo4j không phụ thuộc tên field Java, có thể đặt prefix rõ ràng.

```java
@CompositeProperty(prefix = "profile")
private Map<String, Object> details;
```

Với Map:

```java
Map.of(
    "language", "vi",
    "timeZone", "Asia/Ho_Chi_Minh"
)
```

các property được tạo theo quy tắc mặc định về delimiter:

| Key | Property |
| --- | --- |
| `language` | `profile.language` |
| `timeZone` | `profile.timeZone` |

Prefix là namespace cho nhóm property. Nó không phải label của node, không tạo relationship và cũng không thay đổi tên field trong Java.

Dùng prefix tường minh có ích khi:

- Tên field Java có thể được đổi nhưng schema property cần ổn định.
- Nhiều Map trên cùng entity có các key giống nhau.
- Muốn nhóm property theo một miền nghiệp vụ rõ ràng như `profile`, `billing`, `external` hoặc `preferences`.

Ví dụ hai Map có key `status` nhưng dùng prefix khác nhau:

```java
@CompositeProperty(prefix = "account")
private Map<String, Object> accountAttributes;

@CompositeProperty(prefix = "sync")
private Map<String, Object> synchronizationAttributes;
```

Hai key trên được ánh xạ thành `account.status` và `sync.status`, nên không đè lên nhau.

## 4. Cấu hình delimiter

Thuộc tính `delimiter` quy định ký tự hoặc chuỗi ký tự nối prefix với key. Mặc định delimiter là dấu chấm `.`. Có thể đổi sang dấu gạch dưới hoặc chuỗi khác nếu schema hiện có yêu cầu.

```java
@CompositeProperty(
    prefix = "profile",
    delimiter = "_"
)
private Map<String, Object> details;
```

Với key `language` và `timeZone`, property được lưu thành:

- `profile_language`
- `profile_timeZone`

Một ví dụ đầy đủ hơn:

```java
@Node("Customer")
public class Customer {

    @Id
    private String id;

    @CompositeProperty(
        prefix = "profile",
        delimiter = "_"
    )
    private Map<String, Object> profile;

    @CompositeProperty(
        prefix = "erp",
        delimiter = "_"
    )
    private Map<String, Object> erpAttributes;
}
```

Map `profile` có key `city` tạo property `profile_city`; Map `erpAttributes` có key `customerCode` tạo property `erp_customerCode`.

| Cấu hình | Prefix | Delimiter | Key | Property |
| --- | --- | --- | --- | --- |
| Mặc định, field `contact` | `contact` | `.` | `city` | `contact.city` |
| Chỉ định prefix | `profile` | `.` | `city` | `profile.city` |
| Chỉ định delimiter | `profile` | `_` | `city` | `profile_city` |
| Prefix và delimiter tùy chỉnh | `external` | `__` | `erpCode` | `external__erpCode` |

Hãy chọn delimiter phù hợp với quy ước đặt tên property của dự án. Delimiter không phải cơ chế escape key. Nếu key chứa delimiter hoặc các Map tạo ra cùng một tên property sau khi ghép, cần chuẩn hóa key và prefix để tránh tên bị nhập nhằng hoặc ghi đè.

## 5. Ví dụ ánh xạ và đọc lại dữ liệu

Xét entity khách hàng có một số trường cố định và hai nhóm thuộc tính mở rộng:

```java
import java.util.HashMap;
import java.util.Map;

import org.springframework.data.neo4j.core.schema.CompositeProperty;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Customer")
public class Customer {

    @Id
    private String id;

    private String name;

    @CompositeProperty(
        prefix = "profile",
        delimiter = "_"
    )
    private Map<String, Object> profile = new HashMap<>();

    @CompositeProperty(
        prefix = "integration",
        delimiter = "_"
    )
    private Map<String, Object> integration = new HashMap<>();

    protected Customer() {
    }

    public Customer(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public void setProfileValue(String key, Object value) {
        profile.put(key, value);
    }

    public void setIntegrationValue(String key, Object value) {
        integration.put(key, value);
    }

    public Map<String, Object> getProfile() {
        return profile;
    }

    public Map<String, Object> getIntegration() {
        return integration;
    }
}
```

Khi lưu một customer với dữ liệu:

```java
Customer customer = new Customer("C-100", "An");

customer.setProfileValue("city", "Da Nang");
customer.setProfileValue("language", "vi");
customer.setIntegrationValue("erpCode", "ERP-8821");
customer.setIntegrationValue("lastSyncStatus", "SUCCESS");

customerRepository.save(customer);
```

các property trên node có dạng:

```cypher
(:Customer {
    id: "C-100",
    name: "An",
    profile_city: "Da Nang",
    profile_language: "vi",
    integration_erpCode: "ERP-8821",
    integration_lastSyncStatus: "SUCCESS"
})
```

Khi SDN đọc entity, các property có prefix tương ứng được ghép lại thành các entry của Map `profile` và `integration`. Ứng dụng có thể thao tác với Map mà không phải tự tách tên property trong mỗi service.

Để kiểm tra dữ liệu trực tiếp trong Neo4j:

```cypher
MATCH (c:Customer {id: "C-100"})
RETURN c.profile_city AS city,
       c.profile_language AS language,
       c.integration_erpCode AS erpCode,
       c.integration_lastSyncStatus AS syncStatus
```

Kết quả trả về là các property riêng lẻ. Đây cũng là cách các truy vấn báo cáo hoặc lọc dữ liệu có thể truy cập các giá trị composite đã biết.

## 6. Truy vấn composite property bằng Cypher

Sau khi Map được trải thành property, Cypher truy vấn chúng như các property bình thường.

Ví dụ tìm khách hàng ở một thành phố:

```cypher
MATCH (c:Customer)
WHERE c.profile_city = $city
RETURN c.id, c.name, c.profile_city
```

Nếu dùng delimiter dấu chấm, tên property có dấu chấm cần được escape bằng backtick trong Cypher:

```cypher
MATCH (c:Customer)
WHERE c.`contact.city` = $city
RETURN c
```

Nếu tên property cần được xác định động trong lúc chạy, có thể sử dụng dynamic property access của Cypher trên phiên bản Neo4j hỗ trợ:

```cypher
MATCH (c:Customer)
WHERE c[$propertyName] = $expectedValue
RETURN c
```

Tham số `$propertyName` chứa tên property hoàn chỉnh, ví dụ `profile_city`. Tham số hóa tên property không giống tham số hóa giá trị; hãy dùng cú pháp truy cập động được Cypher hỗ trợ thay vì ghép chuỗi truy vấn tùy tiện.

Có thể tạo index cho một composite property được truy vấn thường xuyên:

```cypher
CREATE INDEX customer_profile_city IF NOT EXISTS
FOR (c:Customer)
ON (c.profile_city)
```

Không nên tạo index cho mọi key động một cách tự động. Hãy chọn các key có ý nghĩa truy vấn ổn định và tần suất sử dụng đủ lớn. Nếu một thuộc tính trở thành thành phần quan trọng của nhiều truy vấn, báo cáo hoặc constraint, cân nhắc đưa nó thành field Java riêng thay vì để trong Map động.

## 7. Key, prefix và delimiter phải có quy tắc rõ ràng

Vì tên property được tạo bằng cách ghép chuỗi, thiết kế key cần nhất quán. Một số quy tắc nên áp dụng:

- Chọn prefix riêng cho từng nhóm Map trên cùng node hoặc relationship.
- Dùng một quy ước đặt key ổn định, chẳng hạn camelCase hoặc snake_case.
- Chuẩn hóa key từ nguồn ngoài trước khi đưa vào Map.
- Tránh key rỗng, key null hoặc key có khoảng trắng không được kiểm soát.
- Tránh dùng delimiter trong key nếu hệ thống không có quy tắc xử lý rõ ràng.
- Kiểm tra tên property sau khi ghép để không trùng với field cố định hoặc nhóm Map khác.
- Không thay đổi prefix/delimiter tùy tiện sau khi dữ liệu đã được lưu; thay đổi cấu hình có thể làm SDN tìm kiếm một tập property khác với dữ liệu hiện có.

Ví dụ, nếu có hai Map:

```java
@CompositeProperty(prefix = "profile", delimiter = "_")
private Map<String, Object> profile;

@CompositeProperty(prefix = "profile", delimiter = "_")
private Map<String, Object> preferences;
```

và cả hai đều có key `language`, chúng cùng ánh xạ vào property `profile_language`. Một Map có thể ghi đè giá trị của Map còn lại. Vì vậy, prefix cần duy nhất trong phạm vi node hoặc relationship.

Tương tự, nếu field thông thường đã ánh xạ vào property `profile_city`, không nên để Map khác tạo ra cùng tên property. Composite property không tự tạo namespace chống xung đột.

## 8. Kiểu dữ liệu và giới hạn của Map

Theo mặc định, `@CompositeProperty` chủ yếu dùng với `Map<String, Object>`. SDN cũng hỗ trợ key dạng enum. Các value trong Map được xử lý bởi hệ thống conversion hiện có, vì vậy kiểu value phải có thể chuyển thành kiểu property mà Neo4j hỗ trợ hoặc phải có converter thích hợp.

Một số điểm cần lưu ý:

- Nested Map không được hỗ trợ trực tiếp. Không nên đặt một Map khác làm value rồi kỳ vọng SDN tự trải đệ quy.
- Không phải object Java tùy ý nào cũng tự động trở thành một nhóm property. Với kiểu riêng, cần converter có khả năng phân rã object thành Map và tái tạo object từ Map.
- Giá trị cần tuân theo giới hạn kiểu property của Neo4j. Nếu value là kiểu không được hỗ trợ, cần chuyển đổi trước khi lưu.
- Map động phù hợp với dữ liệu mở rộng; dữ liệu cốt lõi và có cấu trúc nên được khai báo thành field rõ ràng để dễ kiểm tra và truy vấn.

Nếu cần ánh xạ một kiểu Java riêng thay vì Map, SDN cho phép cung cấp converter triển khai `Neo4jPersistentPropertyToMapConverter` thông qua `converter` hoặc `converterRef` của `@CompositeProperty`. Converter chịu trách nhiệm chuyển object thành Map phẳng khi ghi và tái tạo object khi đọc. Cách này cho phép mô hình Java có cấu trúc hơn, trong khi dữ liệu trên Neo4j vẫn là các property phẳng.

## 9. @CompositeProperty có thể đặt trên relationship

Composite property không chỉ dành cho node. Một nhóm thuộc tính dạng Map cũng có thể được lưu trên relationship, ví dụ metadata của một liên kết giữa khách hàng và tài khoản đối tác.

```java
import java.util.Map;

import org.springframework.data.neo4j.core.schema.CompositeProperty;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Partnership {

    @RelationshipId
    private Long relationshipId;

    @TargetNode
    private Company company;

    @CompositeProperty(
        prefix = "contract",
        delimiter = "_"
    )
    private Map<String, Object> contractMetadata;
}
```

Nếu Map có key `signedYear` và `region`, các property tương ứng nằm trên relationship với tên `contract_signedYear` và `contract_region`.

Cypher có thể truy vấn property đó trực tiếp:

```cypher
MATCH (customer:Customer)-[p:PARTNER_OF]->(company:Company)
WHERE p.contract_region = $region
RETURN customer, company, p.contract_signedYear
```

Như vậy, `@CompositeProperty` dùng cùng quy tắc prefix và delimiter trên node lẫn relationship. Cần chọn prefix theo ngữ nghĩa của chính thành phần chứa Map để tránh nhầm property của node với property của relationship.

## 10. Khi nào nên dùng Map composite và khi nào nên dùng field riêng?

Không phải mọi nhóm thuộc tính đều cần `@CompositeProperty`.

| Tình huống | Cách mô hình phù hợp |
| --- | --- |
| Tập key thay đổi theo từng khách hàng hoặc nguồn dữ liệu | Map với `@CompositeProperty` |
| Thuộc tính cố định, có ý nghĩa nghiệp vụ và được truy vấn thường xuyên | Field Java riêng, có thể dùng `@Property` |
| Cần prefix hoặc delimiter khác schema hiện có | `@CompositeProperty(prefix, delimiter)` |
| Có object Java riêng cần phân rã thành nhiều property | Custom `Neo4jPersistentPropertyToMapConverter` |
| Dữ liệu lồng nhiều cấp hoặc có vòng đời riêng | Mô hình hóa thành node/relationship riêng hoặc converter có cấu trúc phù hợp |
| Cần constraint, index và kiểm soát schema chặt cho từng trường | Field riêng hoặc property có tên ổn định |

Một nhóm Map quá rộng có thể khiến schema khó hiểu và khó kiểm tra. Nếu key có tập hợp ổn định, xuất hiện trong nhiều truy vấn nghiệp vụ, hãy cân nhắc chuyển chúng thành field rõ ràng. Nếu key thực sự linh hoạt và được quản lý theo từng nguồn, composite property giúp giảm số lượng field Java mà vẫn lưu từng giá trị thành property có thể truy vấn.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ Map được lưu thành một property Map lồng nhau | Truy vấn Cypher không thấy cấu trúc như kỳ vọng | Hiểu rằng mỗi entry được trải thành property riêng |
| Quên prefix mặc định theo tên field | Tên property trong Neo4j khác dự đoán | Tính prefix từ tên field nếu không cấu hình |
| Nghĩ delimiter mặc định là dấu gạch dưới | Truy vấn sai tên property | Nhớ delimiter mặc định là dấu chấm |
| Dùng cùng prefix cho nhiều Map | Các key trùng có thể ghi đè nhau | Dùng namespace riêng cho từng nhóm |
| Đổi prefix sau khi đã có dữ liệu | SDN đọc theo tên property mới và không thấy property cũ | Lập migration đổi tên property trước hoặc cùng lúc đổi mapping |
| Đặt nested Map trực tiếp làm value | Không được hỗ trợ bởi converter mặc định | Làm phẳng dữ liệu hoặc viết converter riêng |
| Dùng object tùy ý làm value | Không chuyển đổi được thành property Neo4j | Dùng kiểu được hỗ trợ hoặc đăng ký converter |
| Dùng Map cho trường cốt lõi cần constraint chặt | Khó kiểm soát schema và truy vấn | Khai báo field riêng khi cấu trúc đã ổn định |

## 12. Câu hỏi tự kiểm tra

1. `@CompositeProperty` khác gì với việc lưu một Map như JSON?
2. Nếu field tên `contact` không khai báo prefix và delimiter, key `city` được ánh xạ thành property nào?
3. `prefix = "profile"` và `delimiter = "_"` tạo tên property ra sao với key `language`?
4. Vì sao hai Map không nên dùng cùng prefix nếu chúng có thể chứa cùng key?
5. Có thể đặt `@CompositeProperty` trên field của `@RelationshipProperties` không?
6. Vì sao nested Map không được hỗ trợ trực tiếp bởi converter mặc định?
7. Khi nào nên chuyển một key trong Map thành field Java riêng?
8. Làm thế nào để truy vấn một property composite bằng Cypher?

## Kết luận

`@CompositeProperty` giúp SDN trải các entry của Map thành các property riêng trên node hoặc relationship. `prefix` tạo namespace cho nhóm property, còn `delimiter` xác định cách nối prefix với key. Khi không cấu hình, prefix mặc định theo tên field và delimiter mặc định là dấu chấm.

Để ánh xạ ổn định, hãy thiết kế prefix duy nhất, quy ước key rõ ràng, tránh delimiter gây nhập nhằng và không dùng nested Map với converter mặc định. Dùng composite property cho dữ liệu mở rộng có key linh hoạt; giữ các thuộc tính cốt lõi thành field riêng khi cần kiểm soát schema, index, constraint và truy vấn chặt chẽ.
