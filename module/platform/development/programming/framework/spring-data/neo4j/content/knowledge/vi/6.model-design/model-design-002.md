# Chọn dữ liệu làm thuộc tính hay node độc lập

Khi thiết kế graph cho ứng dụng Spring Data Neo4j, một quyết định quan trọng là xác định dữ liệu nào nên nằm ngay trên node dưới dạng property và dữ liệu nào cần trở thành một node riêng. Quyết định này ảnh hưởng đến cách biểu diễn domain, số bước traversal, cách cập nhật, khả năng truy vấn và cách quản lý vòng đời dữ liệu.

Không nên tạo node cho mọi giá trị, cũng không nên gom mọi thứ thành property của một node lớn. Hãy bắt đầu từ ý nghĩa nghiệp vụ: dữ liệu đó có danh tính riêng không, có được nhiều thực thể dùng chung không, có quan hệ riêng với phần còn lại của graph không, và nó có cần được quản lý độc lập không?

## Phân biệt property và node

Trong Neo4j, node đại diện cho một thực thể trong miền nghiệp vụ hoặc một khái niệm cần được kết nối trong graph. Node có thể mang một hoặc nhiều label và các property. Relationship nối hai node, có kiểu và có thể mang property mô tả chính mối quan hệ đó.

Ví dụ, một khách hàng có thể được biểu diễn như sau:

~~~cypher
CREATE (c:Customer {
    customerCode: "CUS-1042",
    fullName: "Lan Nguyen",
    email: "lan@example.test",
    city: "Da Nang",
    status: "ACTIVE"
});
~~~

Trong ví dụ này, fullName, email, city và status là property của node Customer. Chúng mô tả khách hàng và thường được đọc hoặc cập nhật cùng với khách hàng.

Nếu địa chỉ cần được chia sẻ, tra cứu, gắn với nhiều thực thể hoặc có vòng đời riêng, có thể mô hình hóa địa chỉ thành node:

~~~cypher
CREATE (c:Customer {customerCode: "CUS-1042"})
CREATE (a:Address {
    addressKey: "VN-DN-HC-001",
    city: "Da Nang",
    district: "Hai Chau"
})
CREATE (c)-[:LIVES_AT]->(a);
~~~

Khi đó Address có danh tính và có thể tham gia thêm quan hệ với Building, DeliveryPoint hoặc các khách hàng khác. Hai mô hình đều hợp lệ trong những ngữ cảnh khác nhau; điều cần chọn là mô hình phản ánh đúng cách domain vận hành.

## Tiêu chí chọn property hay node

| Tiêu chí | Nên dùng property | Nên dùng node độc lập |
|---|---|---|
| Danh tính | Giá trị chỉ mô tả node cha, không cần ID riêng | Khái niệm có danh tính hoặc mã riêng |
| Vòng đời | Được tạo, đọc, cập nhật và xóa cùng node cha | Có thể tồn tại hoặc thay đổi độc lập |
| Tái sử dụng | Chỉ thuộc về một node hoặc được sao chép có chủ đích | Nhiều node khác có thể cùng tham chiếu |
| Quan hệ | Không cần kết nối tới thực thể khác | Có quan hệ riêng cần traversal |
| Truy vấn | Thường lọc hoặc hiển thị cùng node cha | Cần tìm kiếm, phân tích hoặc duyệt graph trực tiếp |
| Quy tắc dữ liệu | Chỉ cần quy tắc đơn giản trên node cha | Có uniqueness, index, validation hoặc quyền quản lý riêng |
| Lịch sử | Chỉ cần giá trị hiện tại | Cần theo dõi phiên bản, sự kiện hoặc lịch sử riêng |

Các tiêu chí này hỗ trợ quyết định, không phải luật tuyệt đối. Ví dụ, một địa chỉ chỉ thuộc về một khách hàng có thể là các property trên Customer. Nhưng nếu địa chỉ là địa điểm giao hàng được tái sử dụng và liên kết với nhiều đơn hàng, nó có thể xứng đáng trở thành node riêng.

## Khi dữ liệu phù hợp làm property

Property phù hợp với dữ liệu mô tả một node, có ý nghĩa phụ thuộc vào node đó và không cần được quản lý như một thực thể độc lập.

Những ví dụ thường gặp:

- Tên, email, ngày sinh và trạng thái hiện tại của khách hàng.
- Mã SKU, tên hiển thị, trọng lượng và giá niêm yết của sản phẩm.
- Thời điểm tạo, thời điểm cập nhật hoặc cờ kích hoạt của một thực thể.
- Danh sách nhãn hoặc các giá trị đơn giản có số lượng giới hạn, chẳng hạn danh sách kỹ năng dạng chuỗi.

Neo4j lưu property bằng các kiểu dữ liệu được hỗ trợ như chuỗi, số, boolean, kiểu ngày giờ, kiểu không gian và các mảng giá trị phù hợp. Property không phải một object tùy ý có thể chứa cấu trúc lồng nhau như JSON document. Nếu một đối tượng Java gồm nhiều trường đơn giản chỉ dùng để mô tả một node, có thể ánh xạ từng trường thành property riêng hoặc dùng cơ chế mapping phù hợp của SDN. Nếu đối tượng đó cần danh tính, quan hệ hoặc vòng đời riêng, hãy cân nhắc mô hình node.

Một số điểm cần nhớ khi dùng property:

- Mỗi property có tên và một giá trị được Neo4j hỗ trợ; Neo4j không lưu giá trị null như một property. Gán null trong Cypher có nghĩa là loại bỏ property đó.
- Các danh sách property phải tuân theo giới hạn kiểu dữ liệu của Neo4j; không thể dùng list tùy ý chứa các object khác kiểu.
- Property thường được đọc cùng node sở hữu nó, nên phù hợp với dữ liệu có vòng đời phụ thuộc.
- Nếu một property thường xuyên được dùng để tìm kiếm hoặc sắp xếp, có thể tạo index phù hợp trên label và property đó.

### Ví dụ: thông tin liên hệ và trạng thái khách hàng

Nếu email và trạng thái chỉ là thông tin của khách hàng, có thể khai báo chúng trực tiếp trên entity:

~~~java
import java.util.List;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Customer")
public class Customer {

    @Id
    private String customerCode;

    private String fullName;
    private String email;
    private String city;
    private String postalCode;
    private String status;
    private List<String> interests;

    protected Customer() {
    }

    public Customer(
            String customerCode,
            String fullName,
            String email,
            String city,
            String postalCode,
            String status,
            List<String> interests) {
        this.customerCode = customerCode;
        this.fullName = fullName;
        this.email = email;
        this.city = city;
        this.postalCode = postalCode;
        this.status = status;
        this.interests = interests;
    }

    public String getCustomerCode() {
        return customerCode;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Ví dụ dùng customerCode làm @Id, vì mã này được giả định là ổn định và duy nhất theo quy tắc nghiệp vụ. Nếu mã có thể thay đổi hoặc chỉ duy nhất trong một tenant, hãy chọn một khóa kỹ thuật ổn định khác và lưu customerCode như property riêng.

Tạo uniqueness constraint để database bảo vệ quy tắc mã khách hàng:

~~~cypher
CREATE CONSTRAINT customer_code_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerCode IS UNIQUE;
~~~

Các trường city, postalCode, status và interests ở đây chỉ mô tả khách hàng. Nếu khách hàng chuyển nhà, ứng dụng cập nhật các property tương ứng. Nếu cần lưu lịch sử các địa chỉ cũ, hãy xem xét mô hình lịch sử riêng thay vì ghi đè rồi mất dữ liệu trước đó.

Trạng thái như ACTIVE, SUSPENDED hoặc CLOSED thường có thể là property hoặc enum, bởi nó chỉ biểu thị trạng thái hiện tại của khách hàng. Nếu cần lưu ai thay đổi trạng thái, thời điểm nào và lý do gì, có thể bổ sung node sự kiện StatusChange để lưu lịch sử. Không cần tạo node Status chỉ vì danh sách trạng thái có nhiều giá trị; hãy tạo node khi chính khái niệm trạng thái cần được kết nối hoặc quản lý như thực thể.

## Khi dữ liệu nên trở thành node độc lập

Một khái niệm nên trở thành node khi nó có ý nghĩa vượt ra ngoài việc mô tả node cha. Các dấu hiệu mạnh gồm:

1. **Có danh tính riêng.** Khái niệm có mã hoặc khóa ổn định, được tham chiếu độc lập trong API hoặc quy trình nghiệp vụ.
2. **Được nhiều thực thể dùng chung.** Nhiều node cần trỏ tới cùng một khái niệm thay vì sao chép dữ liệu mô tả.
3. **Có quan hệ riêng.** Khái niệm cần kết nối tới các node khác và các kết nối đó có ý nghĩa trong truy vấn.
4. **Có vòng đời độc lập.** Nó có thể được tạo, cập nhật, vô hiệu hóa hoặc xóa mà không phụ thuộc hoàn toàn vào node cha.
5. **Cần truy vấn như một đối tượng.** Ứng dụng thường xuyên tìm, lọc, phân tích hoặc duyệt từ chính khái niệm đó.
6. **Có dữ liệu hoặc quy tắc riêng.** Nó cần index, uniqueness constraint, trạng thái, quyền hoặc lịch sử độc lập.

Ví dụ thường phù hợp làm node:

- Product và Category khi sản phẩm có thể thuộc nhiều danh mục và danh mục có cấu trúc phân cấp.
- Person và Company khi người có thể làm việc cho nhiều công ty, còn công ty có nhiều nhân viên.
- Order và Payment khi thanh toán có mã, trạng thái và vòng đời riêng.
- Address hoặc Location khi nhiều đơn hàng, cửa hàng hay khách hàng cùng tham chiếu một địa điểm.
- Employment hoặc Contract khi lần làm việc hoặc hợp đồng có thời gian, điều khoản và trạng thái riêng.

### Ví dụ: địa chỉ được dùng chung

Giả sử hệ thống giao hàng có nhiều khách hàng cùng dùng một địa chỉ nhận hàng. Địa chỉ còn được liên kết với các điểm giao và khu vực phục vụ. Khi đó, mô hình địa chỉ thành node giúp tái sử dụng và duyệt graph dễ hơn.

Entity Address có ID riêng:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Address")
public class Address {

    @Id
    private String addressKey;

    private String street;
    private String ward;
    private String district;
    private String city;
    private String postalCode;

    protected Address() {
    }

    public Address(
            String addressKey,
            String street,
            String ward,
            String district,
            String city,
            String postalCode) {
        this.addressKey = addressKey;
        this.street = street;
        this.ward = ward;
        this.district = district;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getAddressKey() {
        return addressKey;
    }
}
~~~

addressKey là khóa nghiệp vụ đã được chuẩn hóa ở tầng ứng dụng, bao gồm đủ thông tin để phân biệt địa chỉ theo quy tắc của hệ thống. Không nên ghép tùy tiện tên đường và thành phố rồi giả định kết quả luôn duy nhất; cần xét số nhà, căn hộ, phường/xã, mã bưu chính và quốc gia nếu các yếu tố đó thuộc phạm vi nhận diện.

Trong entity Customer, ánh xạ quan hệ tới Address:

~~~java
import org.springframework.data.neo4j.core.schema.Relationship;

@Relationship(type = "LIVES_AT")
private Address address;
~~~

Tạo constraint cho khóa địa chỉ:

~~~cypher
CREATE CONSTRAINT address_key_unique IF NOT EXISTS
FOR (a:Address)
REQUIRE a.addressKey IS UNIQUE;
~~~

Sau đó tạo hoặc tìm địa chỉ bằng khóa ổn định và nối với khách hàng:

~~~cypher
MATCH (c:Customer {customerCode: $customerCode})
MERGE (a:Address {addressKey: $addressKey})
ON CREATE SET
    a.street = $street,
    a.ward = $ward,
    a.district = $district,
    a.city = $city,
    a.postalCode = $postalCode
MERGE (c)-[:LIVES_AT]->(a)
RETURN c, a;
~~~

MERGE tìm hoặc tạo một node Address theo addressKey; MERGE tiếp theo bảo đảm quan hệ LIVES_AT được tạo nếu chưa có. Constraint duy nhất trên addressKey bảo vệ quy tắc khi có các giao dịch đồng thời. Nếu thông tin địa chỉ đã tồn tại nhưng thay đổi, ứng dụng cần có quy tắc cập nhật rõ ràng, bởi một địa chỉ dùng chung không nên bị ghi đè tùy tiện từ một khách hàng đơn lẻ.

Nếu địa chỉ chỉ thuộc về một khách hàng, không cần tra cứu độc lập và không có quan hệ nào khác, lưu các trường địa chỉ như property trên Customer thường đơn giản hơn. Việc tạo node Address trong trường hợp đó có thể làm graph phức tạp mà không đem lại lợi ích truy vấn tương xứng.

## Phân biệt property của node, property của relationship và node trung gian

Không phải dữ liệu nào không thuộc riêng node đầu cũng cần trở thành node. Có ba vị trí mô hình hóa thường gặp:

- **Property của node:** mô tả một thực thể, ví dụ Customer.email hoặc Product.weight.
- **Property của relationship:** mô tả mối quan hệ giữa hai thực thể, ví dụ ngày bắt đầu làm việc, vai trò hoặc điểm số trong một quan hệ.
- **Node trung gian:** mô tả một sự kiện hoặc khái niệm có danh tính, vòng đời và quan hệ riêng.

Ví dụ, một nhân viên làm việc tại một phòng ban với vai trò và ngày bắt đầu:

~~~cypher
MATCH (p:Person {personCode: $personCode})
MATCH (d:Department {departmentCode: $departmentCode})
MERGE (p)-[r:WORKS_IN]->(d)
SET r.role = $role,
    r.startedOn = date($startedOn)
RETURN p, r, d;
~~~

role và startedOn mô tả quan hệ làm việc giữa người và phòng ban, nên có thể đặt trên relationship. Nếu nhân viên có nhiều lần được điều chuyển tới cùng một phòng ban, hoặc mỗi lần phân công cần mã hợp đồng, trạng thái, người phê duyệt và lịch sử riêng, hãy mô hình hóa một node Employment hoặc Assignment:

~~~cypher
MATCH (p:Person {personCode: $personCode})
MATCH (d:Department {departmentCode: $departmentCode})
CREATE (e:Employment {
    employmentCode: $employmentCode,
    role: $role,
    startedOn: date($startedOn)
})
CREATE (p)-[:HAS_EMPLOYMENT]->(e)
CREATE (e)-[:IN_DEPARTMENT]->(d)
RETURN p, e, d;
~~~

Khi đó Employment là một khái niệm nghiệp vụ có thể được truy vấn, cập nhật và quản lý độc lập. Nó cũng cho phép nhiều lần phân công được lưu thành nhiều node mà không ghi đè thông tin của lần trước.

Với Spring Data Neo4j, relationship có thể được ánh xạ bằng @Relationship; các thuộc tính trên relationship có thể dùng mô hình @RelationshipProperties và @TargetNode. Khi bản thân quan hệ cần ID riêng hoặc nhiều quan hệ cùng loại giữa một cặp node có vòng đời độc lập, node trung gian thường dễ thể hiện nghiệp vụ hơn. Chọn theo ngữ nghĩa và khả năng truy vấn cần có, không chỉ theo số lượng trường.

## Cách ra quyết định trong một mô hình thực tế

Có thể áp dụng quy trình sau cho từng khái niệm trong domain:

1. **Viết ý nghĩa nghiệp vụ.** Mô tả khái niệm bằng một câu, chẳng hạn “email là thông tin liên hệ hiện tại của khách hàng” hoặc “đơn thanh toán là một giao dịch riêng”.
2. **Xác định danh tính.** Người dùng hoặc hệ thống khác có cần tham chiếu trực tiếp đến khái niệm này không? Nó có mã riêng hoặc cần được nhận diện qua nhiều thao tác không?
3. **Xác định quan hệ.** Khái niệm có cần nối tới node khác không? Những quan hệ đó có ý nghĩa nghiệp vụ hoặc hỗ trợ truy vấn quan trọng không?
4. **Xác định vòng đời.** Khi node cha bị xóa, khái niệm có cần tiếp tục tồn tại không? Nó có thể được cập nhật hoặc lưu lịch sử độc lập không?
5. **Xác định cách truy vấn.** Ứng dụng có thường xuyên tìm từ khái niệm này, lọc các thực thể liên quan hoặc đi qua các quan hệ của nó không?
6. **Chọn mô hình ít phức tạp nhất vẫn đáp ứng yêu cầu.** Nếu property đáp ứng đủ yêu cầu, giữ nó trên node cha. Nếu cần danh tính, tái sử dụng hoặc quan hệ riêng, tạo node và relationship.
7. **Kiểm tra bằng truy vấn đại diện.** Viết thử các Cypher query quan trọng để xem mô hình có hỗ trợ đường truy vấn thực tế với số bước traversal và index hợp lý không.

Một mô hình nên được đánh giá qua các use case chính: tạo mới, cập nhật, tra cứu, liên kết, lưu lịch sử và xóa hoặc vô hiệu hóa. Đừng chỉ nhìn vào sơ đồ ban đầu; hãy kiểm tra cách dữ liệu thay đổi theo thời gian.

## Tác động đến truy vấn và hiệu năng

Property giúp truy vấn đơn giản khi điều kiện lọc nằm ngay trên node:

~~~cypher
MATCH (c:Customer)
WHERE c.city = $city
  AND c.status = "ACTIVE"
RETURN c.customerCode, c.fullName
ORDER BY c.fullName;
~~~

Nếu city và status là property thường xuyên được dùng để lọc, có thể cân nhắc index phù hợp. Ví dụ:

~~~cypher
CREATE INDEX customer_city_status IF NOT EXISTS
FOR (c:Customer)
ON (c.city, c.status);
~~~

Chỉ tạo index dựa trên truy vấn thực tế và kiểm tra kế hoạch bằng EXPLAIN hoặc PROFILE; index cũng tiêu tốn bộ nhớ và làm tăng chi phí cập nhật.

Khi dữ liệu được tách thành node, truy vấn phải đi qua relationship:

~~~cypher
MATCH (c:Customer)-[:LIVES_AT]->(a:Address)
WHERE a.city = $city
RETURN c.customerCode, c.fullName, a.city;
~~~

Đổi lại, một Address có thể được dùng chung và có thể nối với nhiều loại thực thể. Index trên Address.addressKey hoặc Address.city giúp các truy vấn tìm địa chỉ phù hợp hơn khi dữ liệu lớn. Hiệu năng phụ thuộc vào độ chọn lọc của index, số lượng node phù hợp, độ rộng traversal và cách truy vấn được viết; tạo thêm node không tự động làm truy vấn nhanh hơn.

Với property, truy vấn thường ngắn hơn và ít traversal hơn. Với node, graph có thêm điểm kết nối để tái sử dụng và mở rộng quan hệ. Hãy chọn cấu trúc theo đường truy vấn có thật thay vì cố gắng tối ưu một truy vấn đơn lẻ mà làm mô hình khó duy trì.

## Những sai lầm thường gặp

| Sai lầm | Hệ quả | Hướng xử lý |
|---|---|---|
| Tạo node cho mọi chuỗi hoặc số | Graph có quá nhiều node nhỏ, traversal dài và khó đọc | Giữ dữ liệu mô tả đơn giản làm property |
| Lưu một thực thể dùng chung thành bản sao property ở nhiều node | Dữ liệu dễ lệch khi cập nhật | Tạo node chung và relationship nếu cần một nguồn dữ liệu thống nhất |
| Tạo node chỉ vì một object Java có nhiều trường | Tăng độ phức tạp mà không có lợi ích nghiệp vụ | Xem object là value object; ánh xạ các trường thành property nếu phù hợp |
| Lưu object lồng nhau hoặc JSON tùy ý như property Neo4j | Không tương thích với kiểu property gốc hoặc khó truy vấn từng trường | Tách thành property được hỗ trợ, node hoặc thiết kế serialization có chủ đích |
| Đưa dữ liệu của relationship lên một đầu node | Ý nghĩa của dữ liệu bị gắn sai chủ thể | Đặt trên relationship hoặc tạo node trung gian |
| Dùng node danh mục cho mọi enum đơn giản | Tạo traversal không cần thiết | Dùng property khi chỉ cần giá trị trạng thái hoặc loại |
| Gộp lịch sử vào một property hiện tại | Mất thông tin về các lần thay đổi | Tạo node sự kiện/lịch sử hoặc mô hình phiên bản |
| Tạo node dùng chung nhưng cập nhật property tùy tiện | Một thao tác có thể ảnh hưởng mọi node đang tham chiếu | Xác định quyền sở hữu, quy tắc cập nhật và vòng đời rõ ràng |

Một lưu ý quan trọng: nếu dữ liệu được chia sẻ giữa nhiều node, hãy xác định ai có quyền cập nhật nó. Chẳng hạn, địa chỉ dùng chung có thể được cập nhật bởi một tiến trình chuẩn hóa địa chỉ; một khách hàng đơn lẻ không nên tự thay đổi toàn bộ thông tin của địa chỉ mà khách hàng khác cũng đang tham chiếu.

## Bài tập thực hành

Với một hệ thống thương mại điện tử, hãy quyết định property hay node cho từng khái niệm và giải thích lý do:

1. Product.name, Product.weight và Product.price.
2. Category được nhiều sản phẩm tham chiếu và có danh mục cha.
3. Order.status chỉ cần trạng thái hiện tại.
4. Payment có mã giao dịch, số tiền, trạng thái và thời điểm xác nhận.
5. Customer.email có thể thay đổi.
6. Address được nhiều đơn hàng và khách hàng dùng chung.
7. Employment lưu mỗi lần một nhân viên được phân công vào phòng ban, gồm vai trò, ngày bắt đầu và ngày kết thúc.

Sau đó viết hai truy vấn Cypher cho một use case quan trọng: một truy vấn lọc theo property và một truy vấn traversal qua node liên quan. So sánh độ rõ ràng, số bước traversal và index cần thiết. Nếu dùng Spring Data Neo4j, ánh xạ các node bằng @Node, các kết nối bằng @Relationship, và chỉ thêm entity hoặc relationship properties khi chúng phản ánh đúng khái niệm trong domain.

Thiết kế tốt giữ dữ liệu mô tả gần node sở hữu nó, đồng thời đưa các khái niệm có danh tính, vòng đời hoặc quan hệ riêng thành node độc lập. Mỗi quyết định nên xuất phát từ quy tắc nghiệp vụ và các truy vấn mà ứng dụng cần thực hiện.

