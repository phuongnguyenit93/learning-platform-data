# Thiết kế khả năng khôi phục liên kết khi giải tuần tự hóa

Khi JSON mô tả một đồ thị object, cùng một đối tượng có thể được tham chiếu từ nhiều nơi. Ví dụ, một nhân viên có thể xuất hiện trong danh sách nhân viên, đồng thời được tham chiếu bởi thuộc tính `manager` của nhiều nhân viên khác. Nếu JSON lặp lại toàn bộ object ở mọi vị trí, dữ liệu sẽ phình to và các quan hệ vòng có thể gây đệ quy vô hạn. Nếu JSON chỉ gửi mã định danh ở những vị trí tham chiếu, Jackson cần một cách để khôi phục liên kết đó thành cùng một object Java.

Jackson hỗ trợ object identity bằng `@JsonIdentityInfo`, kết hợp với type của object ID và `ObjectIdResolver`. Khi một object được định nghĩa đầy đủ, Jackson ghi nhận ID của nó; các vị trí tham chiếu có thể dùng ID thay cho toàn bộ object. Trong lúc deserialize, Jackson dùng ID để nối các tham chiếu về đúng instance. Nếu tham chiếu xuất hiện trước object định nghĩa ID, Jackson có thể trì hoãn việc gán liên kết trong những trường hợp được hỗ trợ.

Thiết kế tốt cần quyết định rõ ID thuộc phạm vi nào, object đầy đủ xuất hiện ở đâu, có cho phép tham chiếu tiến hay không, xử lý ID thiếu/trùng thế nào và khi nào cần tra cứu đối tượng ngoài tài liệu JSON.

## 1. Bài toán đồ thị object và liên kết

Giả sử hệ thống quản lý nhân viên. Mỗi nhân viên có thể có một người quản lý và nhiều nhân viên báo cáo trực tiếp:

```java
public class Employee {
    private String id;
    private String name;
    private Employee manager;
    private List<Employee> directReports;

    // constructors, getters và setters
}
```

Quan hệ giữa nhân viên có thể tạo thành đồ thị:

```text
             Employee E-1
             (manager)
                  |
          +-------+-------+
          |               |
          v               v
     Employee E-2    Employee E-3
          |               |
          +-------+-------+
                  |
                  v
             Employee E-4
```

Trong object graph Java, `E-2.manager` có thể trỏ tới chính instance `E-1` đã có trong danh sách; `E-1.directReports` lại chứa instance `E-2`. Đây là quan hệ hai chiều. Nếu serializer ghi đầy đủ cả hai phía, nó có thể lặp đi lặp lại cùng object.

JSON cần biểu diễn được hai khái niệm:

- **Object definition:** nơi cung cấp nội dung đầy đủ và ID của object.
- **Object reference:** nơi chỉ ra ID của object đã hoặc sẽ được định nghĩa.

Jackson có thể dùng object identity để tự quản lý hai vai trò đó.

## 2. Khai báo object identity bằng `@JsonIdentityInfo`

Đặt `@JsonIdentityInfo` trên kiểu cần nhận diện. Ví dụ dùng thuộc tính `id` làm object ID:

```java
import com.fasterxml.jackson.annotation.JsonIdentityInfo;
import com.fasterxml.jackson.annotation.ObjectIdGenerators;

@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class Employee {
    private String id;
    private String name;
    private Employee manager;
    private List<Employee> directReports;

    public Employee() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Employee getManager() {
        return manager;
    }

    public void setManager(Employee manager) {
        this.manager = manager;
    }

    public List<Employee> getDirectReports() {
        return directReports;
    }

    public void setDirectReports(List<Employee> directReports) {
        this.directReports = directReports;
    }
}
```

Ý nghĩa:

- `@JsonIdentityInfo` bật quản lý identity cho các instance của `Employee`.
- `ObjectIdGenerators.PropertyGenerator` lấy ID từ một property có sẵn của object.
- `property = "id"` chỉ ra property được dùng làm ID.

ID phải có giá trị ổn định và duy nhất trong phạm vi identity tương ứng. Với `PropertyGenerator`, property `id` phải tồn tại trong model và có thể được Jackson đọc/ghi theo cấu hình. Nếu ID còn null khi serialize, Jackson không có một định danh nghiệp vụ đáng tin cậy để khôi phục liên kết.

## 3. JSON biểu diễn object đầy đủ và tham chiếu bằng ID

Khi Jackson serialize một object graph có identity, lần đầu object được gặp thường được ghi đầy đủ cùng ID; những lần tham chiếu tiếp theo có thể được ghi bằng ID thay vì lặp toàn bộ object.

Ví dụ JSON minh họa:

```json
{
  "id": "E-1",
  "name": "An",
  "manager": null,
  "directReports": [
    {
      "id": "E-2",
      "name": "Binh",
      "manager": "E-1",
      "directReports": []
    },
    {
      "id": "E-3",
      "name": "Chi",
      "manager": "E-1",
      "directReports": []
    }
  ]
}
```

Trong ví dụ này, `E-1` được định nghĩa đầy đủ ở root. Các property `manager` của `E-2` và `E-3` chỉ chứa chuỗi ID `"E-1"`. Khi đọc JSON, Jackson có thể khôi phục hai liên kết đó về cùng object `E-1`.

Định dạng thực tế phụ thuộc thứ tự duyệt object graph và cấu hình property. Điểm quan trọng là JSON phải chứa đủ thông tin để nhận diện một object và các vị trí tham chiếu phải dùng cùng quy ước ID.

## 4. `ObjectIdGenerators.PropertyGenerator` và ID do ứng dụng quản lý

`PropertyGenerator` phù hợp khi object đã có ID nghiệp vụ hoặc ID database:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class Product {
    private Long id;
    private String sku;
    private String name;

    // getters và setters
}
```

JSON:

```json
{
  "id": 1001,
  "sku": "KB-01",
  "name": "Keyboard"
}
```

ID do ứng dụng quản lý có các ưu điểm:

- Có thể tham chiếu cùng object từ nhiều nhánh của graph.
- ID có ý nghĩa ổn định giữa các lần export/import nếu hệ thống bảo đảm tính duy nhất.
- Dễ đối chiếu với database hoặc registry bên ngoài.
- Không phụ thuộc thứ tự object được serializer duyệt để tạo ra ID.

Không nên dùng một thuộc tính có thể thay đổi như tên hiển thị làm identity. Nếu `name` đổi, các tham chiếu cũ sẽ không còn trỏ đúng object. Hãy dùng khóa bất biến hoặc một mã định danh chuyên biệt.

## 5. Dùng ID do Jackson tạo bằng `IntSequenceGenerator` hoặc `UUIDGenerator`

Khi object không có ID nghiệp vụ, có thể để Jackson sinh object ID:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.IntSequenceGenerator.class,
        property = "@id"
)
public class GraphNode {
    private String label;
    private GraphNode next;

    // getters và setters
}
```

Jackson sinh các ID theo sequence trong quá trình serialize. JSON có thể có dạng:

```json
{
  "@id": 1,
  "label": "first",
  "next": {
    "@id": 2,
    "label": "second",
    "next": 1
  }
}
```

Có thể dùng UUID generator khi muốn ID được biểu diễn bằng UUID:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.UUIDGenerator.class,
        property = "@id"
)
public class GraphNode {
    // ...
}
```

Các ID do Jackson sinh rất tiện cho việc biểu diễn graph trong một lần serialize/deserialize. Tuy nhiên, nếu ID cần tồn tại qua nhiều file, nhiều request hoặc nhiều hệ thống, ID do ứng dụng quản lý thường dễ kiểm soát vòng đời hơn. Không nên xem ID sequence sinh trong một tài liệu là khóa database lâu dài.

## 6. Giới hạn phạm vi ID bằng `scope`

`@JsonIdentityInfo` có thuộc tính `scope` để phân biệt namespace object ID. Mặc định scope là `Object.class`; có thể chỉ định kiểu cụ thể:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id",
        scope = Employee.class
)
public class Employee {
    // ...
}
```

Scope là một phần của khóa identity mà Jackson dùng khi quản lý object ID. Nó giúp tách những miền ID khác nhau, ví dụ `Employee` và `Department` đều có ID `"1"` nhưng không phải cùng một loại object.

Hãy chọn scope nhất quán ở các nơi khai báo cùng identity. Không nên đổi scope tùy tiện giữa các DTO hoặc mix-in nếu chúng cùng tham chiếu một kiểu object.

## 7. Tham chiếu luôn bằng ID với `@JsonIdentityReference`

Mặc định, Jackson có thể ghi object đầy đủ ở lần đầu và dùng ID ở các lần sau. Nếu một property luôn phải được ghi dưới dạng ID, dùng `@JsonIdentityReference(alwaysAsId = true)`:

```java
import com.fasterxml.jackson.annotation.JsonIdentityReference;

public class Department {
    private String id;
    private String name;

    @JsonIdentityReference(alwaysAsId = true)
    private Employee manager;

    // getters và setters
}
```

Kiểu `Employee` cần được đánh dấu bằng `@JsonIdentityInfo`. Khi serialize `Department`, property `manager` chỉ chứa ID của employee, ví dụ:

```json
{
  "id": "D-1",
  "name": "Engineering",
  "manager": "E-1"
}
```

Điều này làm payload gọn và thể hiện rõ đây là một liên kết. Tuy nhiên, JSON phải có một nơi khác định nghĩa đầy đủ employee `E-1`, hoặc resolver phải có khả năng tìm object đó. Nếu chỉ có ID mà không có định nghĩa hay nguồn tra cứu, Jackson không thể tự tạo đầy đủ object.

`alwaysAsId = true` là lựa chọn ở phía biểu diễn JSON; nó không tự tạo một object definition ở nơi khác và cũng không tự tải object từ database.

## 8. Khôi phục liên kết khi object được định nghĩa trước tham chiếu

Trường hợp đơn giản nhất là JSON chứa object đầy đủ trước, sau đó các property khác tham chiếu ID của nó. Khi Jackson đọc object đầy đủ, nó đăng ký ID trong resolver của lần deserialize hiện tại. Các tham chiếu sau đó có thể tìm thấy instance đã đăng ký.

Ví dụ:

```json
{
  "employees": [
    {
      "id": "E-1",
      "name": "An",
      "manager": null
    },
    {
      "id": "E-2",
      "name": "Binh",
      "manager": "E-1"
    }
  ]
}
```

Nếu `Employee` được cấu hình `@JsonIdentityInfo`, `manager` của `E-2` có thể được khôi phục thành chính instance `E-1` đã đọc ở phần tử trước.

Thiết kế dữ liệu theo thứ tự định nghĩa trước tham chiếu giúp quá trình đọc dễ dự đoán và tương thích với nhiều kiểu model hơn, đặc biệt khi có immutable object hoặc constructor-based deserialization.

## 9. Tham chiếu tiến: ID xuất hiện trước object definition

Đôi khi JSON tham chiếu đến một ID trước khi object mang ID đó xuất hiện. Đây là **forward reference**.

Ví dụ, property `manager` xuất hiện trước danh sách nhân viên định nghĩa manager:

```json
{
  "manager": "E-2",
  "staff": [
    {
      "id": "E-1",
      "name": "An",
      "manager": null
    },
    {
      "id": "E-2",
      "name": "Binh",
      "manager": null
    }
  ]
}
```

Nếu property là bean property có thể gán sau khi object cha được tạo, Jackson có thể ghi nhận tham chiếu chưa giải quyết, chờ đến khi object `E-2` được đọc và bind ID, rồi hoàn tất liên kết.

Mẫu lớp minh họa:

```java
public class Department {
    private Employee manager;
    private List<Employee> staff;

    public Employee getManager() {
        return manager;
    }

    public void setManager(Employee manager) {
        this.manager = manager;
    }

    public List<Employee> getStaff() {
        return staff;
    }

    public void setStaff(List<Employee> staff) {
        this.staff = staff;
    }
}
```

Deserialize:

```java
Department department = mapper.readValue(json, Department.class);
Employee manager = department.getManager();
```

Với cấu hình object identity trên `Employee`, Jackson có thể trì hoãn việc gán `manager` cho tới khi ID `E-2` được bind từ object đầy đủ trong `staff`.

Không nên giả định mọi vị trí đều hỗ trợ forward reference giống nhau. Khả năng trì hoãn phụ thuộc property deserializer và cách object được tạo. Bean property có setter hoặc một số collection/map context là trường hợp phổ biến; constructor/creator parameter của immutable object, custom deserializer hoặc cấu trúc đặc biệt cần được kiểm thử riêng. Nếu thứ tự dữ liệu có thể điều khiển, ưu tiên định nghĩa object trước các tham chiếu.

## 10. Kiểm tra liên kết có trỏ về cùng instance hay không

Khôi phục liên kết không chỉ là hai object có cùng giá trị ID. Mục tiêu của object identity thường là các property tham chiếu cùng một instance Java.

Ví dụ kiểm tra:

```java
Department department = mapper.readValue(json, Department.class);

Employee manager = department.getManager();
Employee managerFromStaff = department.getStaff().stream()
        .filter(employee -> "E-2".equals(employee.getId()))
        .findFirst()
        .orElseThrow();

if (manager != managerFromStaff) {
    throw new IllegalStateException("Object identity was not restored");
}
```

Phép so sánh `==` kiểm tra cùng instance. `equals()` có thể chỉ so sánh giá trị và không chứng minh graph được nối lại bằng cùng object. Nếu domain định nghĩa `equals()` theo ID, hai instance khác nhau vẫn có thể được coi là bằng nhau theo `equals()`.

Trong unit test, dùng `assertSame()` khi mục tiêu là xác nhận identity; dùng `assertEquals()` khi mục tiêu là xác nhận giá trị.

## 11. Vai trò của `ObjectIdResolver`

`ObjectIdResolver` là thành phần quản lý việc liên kết object ID với object Java. Jackson dùng resolver để:

- Đăng ký object vừa được deserialize cùng ID của nó.
- Tìm object tương ứng khi gặp một tham chiếu ID.
- Tạo resolver mới cho một lần deserialize.
- Xác định resolver có tương thích với một resolver khác hay không.

Giao diện trong Jackson Databind có các phương thức chính:

```java
public interface ObjectIdResolver {
    void bindItem(ObjectIdGenerator.IdKey id, Object pojo);

    Object resolveId(ObjectIdGenerator.IdKey id);

    ObjectIdResolver newForDeserialization(Object context);

    boolean canUseFor(ObjectIdResolver resolverType);
}
```

`bindItem()` ghi nhận object definition; `resolveId()` tìm object đã được đăng ký; `newForDeserialization()` tạo resolver cho ngữ cảnh đọc mới; `canUseFor()` cho biết resolver có thể được tái sử dụng theo loại hay không.

Jackson cung cấp `SimpleObjectIdResolver` làm resolver mặc định cho object identity thông thường. Resolver này duy trì ánh xạ ID sang object trong phạm vi lần deserialize. Khi cần một chính sách tra cứu khác, ứng dụng có thể triển khai resolver riêng và khai báo qua thuộc tính `resolver` của `@JsonIdentityInfo`.

## 12. Phạm vi vòng đời của resolver

Resolver mặc định không phải một kho object toàn cục dùng chung cho mọi request. Mỗi lần deserialize cần một phạm vi identity riêng để ID của một tài liệu không vô tình trỏ tới object của tài liệu khác.

Ví dụ hai file đều có nhân viên ID `E-1`, nhưng nội dung của hai file có thể thuộc hai tenant hoặc hai snapshot khác nhau. Nếu dùng một map static toàn cục cho tất cả lần đọc, tham chiếu từ file thứ hai có nguy cơ trỏ tới object của file thứ nhất.

Khi triển khai resolver tùy chỉnh, hãy thiết kế rõ:

- Resolver instance có được tạo mới cho từng lần deserialize không?
- Registry dùng chung có phạm vi tenant, transaction, import batch hay ứng dụng?
- Khi nào entry được xóa hoặc hết hiệu lực?
- ID có được phân vùng theo loại object hoặc tenant không?
- Duplicate ID được từ chối, thay thế hay xử lý theo quy tắc nào?

Thông thường, không nên dùng một static mutable map để giữ mọi object đã đọc. Nó có thể gây rò rỉ bộ nhớ, trộn dữ liệu giữa request và tạo lỗi liên kết khó tái hiện.

## 13. Khi nào cần custom `ObjectIdResolver`?

Resolver mặc định phù hợp khi mọi object definition và reference nằm trong cùng tài liệu hoặc cùng lần deserialize. Resolver tùy chỉnh có thể cần thiết khi ứng dụng muốn tra cứu ID từ một registry được chuẩn bị trước, một cache có phạm vi rõ ràng hoặc một kho dữ liệu bên ngoài.

Một resolver tùy chỉnh thường cần thực hiện các việc:

1. Nhận object definition qua `bindItem()` và đăng ký nó vào identity map của lần đọc.
2. Khi `resolveId()` được gọi, tìm trong map cục bộ trước.
3. Nếu hợp đồng cho phép external reference, tra registry đã được nạp sẵn hoặc nguồn dữ liệu phù hợp.
4. Trả về `null` khi không tìm thấy để Jackson áp dụng chính sách unresolved reference.
5. Tạo resolver instance mới đúng phạm vi trong `newForDeserialization()`.

Không nên thực hiện một truy vấn database hoặc HTTP request riêng cho từng `resolveId()` nếu tài liệu có hàng nghìn tham chiếu. Cách đó có thể tạo N+1 query, tăng latency và làm quá trình deserialize phụ thuộc hạ tầng bên ngoài. Nên preload tập object cần thiết theo batch, hoặc deserialize ID thành DTO rồi resolve liên kết ở application service.

### 13.1. Đăng ký resolver trên kiểu object

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id",
        resolver = ImportObjectIdResolver.class
)
public class Employee {
    private String id;
    private String name;

    // getters và setters
}
```

`ImportObjectIdResolver` cần triển khai `ObjectIdResolver` và phải có thể được Jackson khởi tạo theo cơ chế cấu hình của ứng dụng. Với resolver cần dependency như repository hoặc tenant context, hãy thiết kế cách cung cấp context một cách tường minh, ví dụ qua cơ chế khởi tạo handler của Jackson hoặc một bước liên kết ở application service. Không dựa vào biến static toàn cục để truyền dependency.

### 13.2. Quy tắc duplicate ID

Nếu hai object definition khác nhau cùng khai báo ID `E-2`, resolver không thể biết object nào là nguồn đúng nếu hợp đồng không quy định. Chính sách an toàn thường là từ chối duplicate ID thay vì âm thầm ghi đè:

```text
bindItem("E-2", employeeA)
bindItem("E-2", employeeB)
                 |
                 v
       Duplicate identity error
```

Nếu hai nhánh graph cố ý cùng tham chiếu một object, JSON nên định nghĩa object một lần và những vị trí khác chỉ dùng ID tham chiếu. Không gửi hai bản object đầy đủ cùng ID nhưng dữ liệu khác nhau.

## 14. Xử lý ID không được định nghĩa

Một tham chiếu chỉ chứa ID nhưng không có object definition trong tài liệu và cũng không tìm được qua resolver là unresolved reference.

Ví dụ:

```json
{
  "manager": "E-404",
  "staff": [
    {
      "id": "E-1",
      "name": "An",
      "manager": null
    }
  ]
}
```

Không có object nào mang ID `E-404`. Jackson không thể tự tạo một `Employee` đầy đủ từ chuỗi ID này.

Trong Jackson 2.x, `DeserializationFeature.FAIL_ON_UNRESOLVED_OBJECT_IDS` điều khiển việc báo lỗi khi kết thúc quá trình đọc mà vẫn còn object reference chưa được giải quyết. Feature này mặc định được bật.

```java
ObjectMapper mapper = new ObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_UNRESOLVED_OBJECT_IDS);
```

Khi bật, unresolved reference làm deserialize thất bại với lỗi mapping phù hợp. Đây thường là lựa chọn an toàn cho dữ liệu cần graph nhất quán.

Có thể tắt feature:

```java
mapper.disable(DeserializationFeature.FAIL_ON_UNRESOLVED_OBJECT_IDS);
```

Khi tắt, các tham chiếu không giải quyết được có thể bị bỏ qua và property liên quan giữ null hoặc trạng thái chưa được gán. Điều này có thể khiến graph không đầy đủ nhưng không phát sinh lỗi ở cuối quá trình đọc. Chỉ dùng khi nghiệp vụ cho phép liên kết tùy chọn và ứng dụng có bước validation tiếp theo. Không tắt feature chỉ để che giấu dữ liệu tham chiếu bị thiếu.

## 15. Phân biệt tham chiếu nội bộ và tham chiếu bên ngoài tài liệu

`@JsonIdentityInfo` cùng resolver mặc định phù hợp với graph có object definition nằm trong cùng lần deserialize. Nhưng một JSON có thể chỉ chứa ID của object đã tồn tại trong database:

```json
{
  "id": "D-10",
  "managerId": "E-200"
}
```

Ở đây, `E-200` không được định nghĩa trong payload. Đây là external reference. Có hai hướng thiết kế:

**Hướng A — Resolver có khả năng tra cứu external ID:** dùng custom `ObjectIdResolver` với registry/lookup đã được chuẩn bị và có phạm vi rõ ràng.

**Hướng B — Deserialize ID thành DTO rồi liên kết ở application layer:** nhận `managerId` như một giá trị bình thường, tải Employee tương ứng và gán vào domain object sau khi kiểm tra.

Hướng B thường dễ kiểm soát transaction, authorization, lỗi không tìm thấy và truy vấn theo batch. Hướng A hữu ích khi muốn giữ cơ chế object identity thống nhất trong một model Jackson, nhưng cần quản lý resolver lifecycle và hiệu năng cẩn thận.

## 16. Mẫu hai giai đoạn: tạo object trước, nối liên kết sau

Khi dữ liệu chứa nhiều ID tham chiếu, cách dễ dự đoán là tách deserialize thành hai giai đoạn:

1. Đọc từng record thành DTO chỉ chứa ID và dữ liệu scalar.
2. Tạo tất cả domain object và đưa vào map `id -> object`.
3. Duyệt lại DTO để nối các tham chiếu.
4. Báo lỗi nếu một ID tham chiếu không tồn tại hoặc bị trùng.

DTO:

```java
public record EmployeeInput(
        String id,
        String name,
        String managerId) {
}
```

Domain object:

```java
public class Employee {
    private final String id;
    private final String name;
    private Employee manager;

    public Employee(String id, String name) {
        this.id = Objects.requireNonNull(id);
        this.name = Objects.requireNonNull(name);
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Employee getManager() {
        return manager;
    }

    public void setManager(Employee manager) {
        this.manager = manager;
    }
}
```

Xây dựng graph:

```java
Map<String, Employee> byId = new LinkedHashMap<>();

// Giai đoạn 1: tạo mọi node trước.
for (EmployeeInput input : inputs) {
    Employee employee = new Employee(input.id(), input.name());
    Employee previous = byId.putIfAbsent(input.id(), employee);
    if (previous != null) {
        throw new IllegalArgumentException("Duplicate employee id: " + input.id());
    }
}

// Giai đoạn 2: nối các cạnh của graph.
for (EmployeeInput input : inputs) {
    if (input.managerId() == null) {
        continue;
    }

    Employee employee = byId.get(input.id());
    Employee manager = byId.get(input.managerId());
    if (manager == null) {
        throw new IllegalArgumentException(
                "Unknown manager id: " + input.managerId());
    }

    employee.setManager(manager);
}
```

Vì mọi node đã được tạo trước khi nối cạnh, thứ tự record không ảnh hưởng đến việc tìm manager. Cách này cũng hỗ trợ chu trình nếu domain cho phép; nếu nghiệp vụ cấm chu trình quản lý, cần kiểm tra quy tắc đó sau khi graph được nối.

Nếu manager có thể nằm ngoài payload, thay bước `byId.get()` bằng tra cứu theo batch từ repository hoặc registry, rồi xác nhận người tham chiếu có tồn tại và caller có quyền liên kết tới họ.

## 17. Xử lý chu trình trong object graph

Đồ thị có thể chứa chu trình:

```text
Employee A.manager -> Employee B
Employee B.manager -> Employee A
```

Về mặt tham chiếu Java, chu trình có thể tồn tại. Với JSON, không thể lồng object vô hạn để biểu diễn nó. Object identity giải quyết bằng cách ghi một object đầy đủ và dùng ID tại cạnh quay lại.

Tuy nhiên, khôi phục được chu trình về mặt kỹ thuật không có nghĩa chu trình đó hợp lệ về nghiệp vụ. Ví dụ, hệ thống quản lý nhân viên có thể yêu cầu một người không được là quản lý của chính mình và không có vòng lặp quản lý. Sau khi khôi phục graph, application/domain layer vẫn cần kiểm tra các invariant.

Nếu graph có thể rất lớn, việc duyệt chu trình để validation nên dùng thuật toán có đánh dấu trạng thái hoặc tập visited để tránh lặp vô hạn.

## 18. So sánh `@JsonIdentityInfo` với `@JsonManagedReference` và `@JsonBackReference`

Jackson có một cơ chế khác để xử lý quan hệ hai chiều: managed/back references.

| Cơ chế | Cách biểu diễn | Khả năng giữ nhiều liên kết tới cùng object |
|---|---|---|
| `@JsonManagedReference` / `@JsonBackReference` | Serialize phía managed; bỏ phía back-reference khỏi JSON và khôi phục liên kết ngược khi đọc | Phù hợp quan hệ cha-con có hướng rõ; không biểu diễn mọi cạnh bằng ID |
| `@JsonIdentityInfo` | Ghi object definition và tham chiếu bằng ID | Phù hợp graph tổng quát, nhiều nơi cùng tham chiếu một instance và chu trình |

Ví dụ managed/back:

```java
public class Department {
    @JsonManagedReference
    private List<Employee> employees;
}

public class Employee {
    @JsonBackReference
    private Department department;
}
```

Khi serialize, property `department` ở phía back thường không xuất hiện. Khi deserialize, Jackson có thể gán lại liên kết ngược dựa trên cặp managed/back tương ứng.

Nếu JSON cần lưu tham chiếu rõ ràng bằng ID, hoặc cùng một object được chia sẻ bởi nhiều nhánh không tạo thành cặp cha-con đơn giản, `@JsonIdentityInfo` thường phù hợp hơn.

Không nên gắn cả hai cơ chế lên cùng property một cách tùy tiện. Hãy chọn cách biểu diễn theo cấu trúc graph và hợp đồng JSON.

## 19. Object identity với immutable object và constructor-based deserialization

Object identity dễ quản lý hơn khi object có thể được tạo trước rồi các property tham chiếu được gán sau. Với immutable object, các property thường được truyền vào constructor và không có setter để cập nhật sau.

Ví dụ:

```java
public record EmployeeRecord(
        String id,
        String name,
        EmployeeRecord manager) {
}
```

Nếu `manager` chỉ là ID tham chiếu tới object sẽ xuất hiện về sau, Jackson phải giải quyết ID trước khi có thể gọi canonical constructor. Không thể mặc định rằng cơ chế trì hoãn forward reference của mutable bean sẽ áp dụng giống hệt cho constructor parameter.

Các lựa chọn thiết kế:

- Đặt object definition trước reference để resolver có thể tìm thấy ID ngay khi tạo constructor argument.
- Deserialize thành DTO có `managerId`, sau đó xây dựng immutable domain graph bằng hai giai đoạn.
- Dùng một factory/application service tạo graph theo thứ tự phù hợp.
- Viết custom deserializer nếu format và lifecycle đòi hỏi một cách khôi phục đặc biệt.

Không nên thêm setter công khai vào domain chỉ để làm hài lòng deserializer nếu điều đó phá vỡ invariant. Hãy giữ ranh giới giữa model giao tiếp và model nghiệp vụ.

## 20. Bảo đảm tính duy nhất và nhất quán của ID

Để liên kết có thể khôi phục chính xác, cần quy định:

- ID không null đối với object được tham chiếu.
- ID duy nhất trong namespace/scope đã chọn.
- Cùng một object không được định nghĩa nhiều lần với dữ liệu mâu thuẫn.
- Mọi reference ID phải có object definition hoặc nguồn lookup hợp lệ.
- Kiểu dữ liệu ID phải nhất quán: ví dụ luôn là string hoặc luôn là number theo schema.
- Nếu ID có thể trùng giữa tenant hoặc loại object, phải đưa tenant/type vào scope hoặc khóa resolver.

Không nên chuyển ID giữa string và number tùy payload. `"42"` và `42` là hai kiểu JSON khác nhau; nếu một phía gửi string còn phía kia kỳ vọng số, quá trình resolve có thể không khớp theo type metadata.

## 21. Kiểm thử các trường hợp khôi phục liên kết

Một bộ test hữu ích nên bao gồm:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Object definition trước reference | Reference trỏ về đúng instance |
| Reference trước object definition | Được trì hoãn nếu vị trí và kiểu model hỗ trợ forward reference |
| Reference không có definition | Báo lỗi khi `FAIL_ON_UNRESOLVED_OBJECT_IDS` bật |
| Hai object definition cùng ID | Bị từ chối theo chính sách duplicate ID |
| Nhiều property cùng tham chiếu một ID | Các property trỏ về cùng instance |
| Hai loại object dùng cùng giá trị ID nhưng scope khác | Không bị nhầm namespace |
| ID chỉ tồn tại ở database ngoài payload | Được resolve qua resolver/lookup hoặc application linking phase |
| Graph có chu trình | Deserialize được theo identity, sau đó domain validation kiểm tra quy tắc |

Ví dụ JUnit 5 kiểm tra identity:

```java
@Test
void restoresForwardReferenceToSameEmployeeInstance() throws Exception {
    String json = """
            {
              "manager": "E-2",
              "staff": [
                {"id": "E-1", "name": "An", "manager": null},
                {"id": "E-2", "name": "Binh", "manager": null}
              ]
            }
            """;

    Department department = mapper.readValue(json, Department.class);
    Employee managerFromReference = department.getManager();
    Employee managerFromList = department.getStaff().get(1);

    assertSame(managerFromList, managerFromReference);
}
```

Test này cần các model `Department` và `Employee` mutable như ví dụ trước, cùng `@JsonIdentityInfo` trên `Employee`. Hãy chạy với Jackson version thực tế và đúng kiểu property mà ứng dụng sử dụng; nếu forward reference ở constructor hoặc custom deserializer, viết test riêng cho đường đó.

Kiểm tra unresolved reference:

```java
@Test
void rejectsReferenceWithoutDefinition() {
    String json = """
            {
              "manager": "E-404",
              "staff": []
            }
            """;

    assertThrows(JsonProcessingException.class,
            () -> mapper.readValue(json, Department.class));
}
```

Test nên dùng mapper bật `FAIL_ON_UNRESOLVED_OBJECT_IDS` và xác nhận lỗi ở ranh giới deserialize thay vì để graph không đầy đủ đi sâu vào nghiệp vụ.

## 22. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Jackson lặp object hoặc đệ quy vô hạn | Chưa cấu hình object identity cho graph có chu trình | Dùng `@JsonIdentityInfo` hoặc managed/back reference cho quan hệ phù hợp |
| Tham chiếu ID không được khôi phục | Kiểu được tham chiếu chưa có identity metadata hoặc ID không khớp | Kiểm tra `@JsonIdentityInfo`, property ID, scope và kiểu JSON |
| Unresolved forward reference | ID được tham chiếu nhưng chưa được bind, hoặc vị trí đó không hỗ trợ trì hoãn | Định nghĩa trước reference, dùng mutable property được hỗ trợ hoặc tách bước linking |
| Reference vẫn null | Đã tắt `FAIL_ON_UNRESOLVED_OBJECT_IDS` hoặc resolver không tìm thấy object | Bật fail-fast và kiểm tra nguồn ID |
| Hai reference cùng ID lại trỏ tới hai instance | Dữ liệu được deserialize thành hai phạm vi/resolver khác nhau hoặc model dùng ID thường thay vì object identity | Dùng cùng identity context hoặc application identity map |
| Duplicate object ID | Hai object definition có cùng ID trong cùng scope | Từ chối duplicate hoặc chuẩn hóa dữ liệu trước khi deserialize |
| ID database ngoài payload không được tìm thấy | Resolver mặc định chỉ có object đã bind trong lần đọc | Dùng custom resolver có registry hoặc application-level lookup |
| Constructor parameter không xử lý forward ref | Object chưa thể được tạo khi tham chiếu chưa resolve | Dùng định nghĩa trước, DTO hai giai đoạn hoặc factory |
| Liên kết nhầm giữa tenant/loại object | Namespace ID chưa được phân vùng | Dùng scope/registry key có tenant và type phù hợp |

## 23. Quy trình thiết kế khả năng khôi phục liên kết

Khi thiết kế JSON cho một object graph, hãy đi theo các bước:

1. Xác định những kiểu object có thể được tham chiếu từ nhiều vị trí hoặc tham gia chu trình.
2. Chọn ID ổn định, không null và duy nhất trong phạm vi cần thiết.
3. Đánh dấu kiểu bằng `@JsonIdentityInfo`; dùng `PropertyGenerator` nếu có ID nghiệp vụ, hoặc generator khác nếu ID chỉ phục vụ một tài liệu.
4. Chọn cách biểu diễn reference: object đầy đủ ở lần đầu, ID ở lần sau hoặc `@JsonIdentityReference(alwaysAsId = true)` cho property luôn dùng ID.
5. Quy định object definition nằm ở đâu và reference có được xuất hiện trước definition không.
6. Giữ `FAIL_ON_UNRESOLVED_OBJECT_IDS` bật nếu mọi liên kết đều bắt buộc.
7. Chỉ dùng custom `ObjectIdResolver` khi cần registry hoặc chính sách lookup khác; xác định lifecycle và phạm vi của resolver.
8. Với external IDs hoặc immutable graph phức tạp, cân nhắc deserialize DTO rồi nối liên kết trong application service.
9. Kiểm tra duplicate ID, ID thiếu, scope, chu trình và identity bằng test.

## 24. Ghi nhớ

Khôi phục liên kết khi deserialize là bài toán nối các reference ID về đúng object instance trong một graph. `@JsonIdentityInfo` xác định cơ chế identity; `ObjectIdGenerators.PropertyGenerator` dùng ID có sẵn; `@JsonIdentityReference(alwaysAsId = true)` ép một property biểu diễn bằng ID; `ObjectIdResolver` quản lý ánh xạ ID sang object trong phạm vi đọc.

Forward reference có thể được trì hoãn trong các vị trí được hỗ trợ, nhưng không phải mọi kiểu model đều giải quyết được reference xuất hiện trước object definition. Giữ object definition trước reference nếu có thể; bật kiểm tra unresolved ID; từ chối duplicate ID; và dùng custom resolver hoặc bước linking riêng khi cần tra cứu object ngoài tài liệu. Khi ranh giới ID, resolver và chính sách lỗi được xác định rõ, ứng dụng có thể khôi phục graph nhất quán mà không phải lặp toàn bộ object trong JSON.
