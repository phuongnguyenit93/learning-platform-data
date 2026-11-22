# Gán property đơn và property lồng nhau

## 1. Gán property trong SpEL là gì?

Spring Expression Language (SpEL) không chỉ đọc dữ liệu từ object. Khi property accessor cho phép ghi, SpEL còn có thể cập nhật property của root object hoặc một object được tham chiếu từ evaluation context.

Có hai cách thường dùng để thực hiện việc gán:

- **Gán qua API:** parse một property expression rồi gọi phương thức setValue.
- **Gán bằng toán tử trong expression:** dùng toán tử gán = bên trong biểu thức SpEL rồi đánh giá biểu thức.

Ví dụ, nếu root object là một Customer có property name:

    name = 'Lan'

Biểu thức trên gán chuỗi Lan vào property name của root object.

Nếu Customer có property address và Address có property city:

    address.city = 'Da Nang'

SpEL đi qua property address trước, sau đó ghi giá trị vào city của object Address.

Phân biệt được property đơn và property lồng nhau giúp xác định đúng object đích, điều kiện cần có để ghi thành công và nguyên nhân khi một phép gán thất bại.

## 2. Property đơn: ghi trực tiếp trên root object

Property đơn là property được truy cập trực tiếp từ root object. Ví dụ Customer có các property name, email và age.

Một JavaBean đơn giản:

    public class Customer {
        private String name;
        private String email;
        private int age;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            this.age = age;
        }
    }

Tạo expression cho property name và gán giá trị:

    ExpressionParser parser = new SpelExpressionParser();

    Customer customer = new Customer();

    Expression nameExpression =
        parser.parseExpression("name");

    nameExpression.setValue(
        new StandardEvaluationContext(),
        customer,
        "Lan"
    );

    System.out.println(customer.getName());

Kết quả:

    Lan

Ở đây:

- name là property expression.
- customer là root object được truyền vào setValue.
- Lan là giá trị mới.
- SpEL tìm property accessor có khả năng ghi property name.

Cách gọi setValue tách riêng đường dẫn property và giá trị cần gán. Đây là cách dễ đọc khi ứng dụng muốn cập nhật một property đã xác định.

## 3. Gán bằng toán tử assignment

SpEL hỗ trợ toán tử gán = ngay trong expression.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    Customer customer = new Customer();

    Expression expression =
        parser.parseExpression("name = 'Lan'");

    Object assignedValue = expression.getValue(
        new StandardEvaluationContext(),
        customer
    );

Sau khi đánh giá, property name của customer được cập nhật thành Lan. Giá trị của expression là giá trị được gán.

Cần phân biệt hai cách viết:

    name = 'Lan'

    name == 'Lan'

Dấu = là phép gán. Nó cập nhật property nếu quyền truy cập cho phép ghi.

Dấu == là phép so sánh bằng. Nó kiểm tra hai giá trị có bằng nhau hay không và trả về kết quả boolean; nó không cập nhật property.

Không nên nhầm toán tử assignment của SpEL với phép gán trong Java source. Trong ví dụ trên, toàn bộ biểu thức được truyền dưới dạng chuỗi cho SpEL parser.

## 4. Property lồng nhau là gì?

Property lồng nhau là đường dẫn gồm nhiều bước truy cập property. Mỗi bước sau sử dụng object được trả về từ bước trước.

Ví dụ object model:

    public class Address {
        private String city;
        private String country;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }

        public String getCountry() {
            return country;
        }

        public void setCountry(String country) {
            this.country = country;
        }
    }

    public class Customer {
        private String name;
        private Address address;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

Nếu root object là Customer, đường dẫn:

    address.city

có nghĩa là:

1. Đọc property address từ Customer.
2. Lấy object Address được trả về.
3. Ghi property city trên object Address đó.

Ví dụ:

    Customer customer = new Customer();

    Address address = new Address();
    customer.setAddress(address);

    ExpressionParser parser = new SpelExpressionParser();

    Expression cityExpression =
        parser.parseExpression("address.city");

    cityExpression.setValue(
        new StandardEvaluationContext(),
        customer,
        "Da Nang"
    );

    System.out.println(customer.getAddress().getCity());

Kết quả:

    Da Nang

Property address phải trả về một object Address có thể truy cập. Property city trên object đó phải có khả năng ghi theo accessor được sử dụng.

## 5. Gán property lồng nhau bằng toán tử =

Có thể viết cùng thao tác bằng toán tử assignment:

    Expression expression =
        parser.parseExpression("address.city = 'Da Nang'");

    expression.getValue(
        new StandardEvaluationContext(),
        customer
    );

Sau khi evaluation, city của Address được cập nhật.

Đường dẫn lồng nhau có thể dài hơn:

    address.city = 'Da Nang'
    address.country = 'Vietnam'

Hoặc nếu object model có nhiều tầng:

    order.customer.address.city = 'Hue'

SpEL lần lượt truy cập order, customer, address rồi ghi city trên object cuối cùng.

Độ sâu của đường dẫn không làm thay đổi nguyên tắc. Mỗi bước trung gian phải trả về object phù hợp để bước tiếp theo có thể được thực hiện.

## 6. Root object và variable trong EvaluationContext

Một property expression không có prefix # thường được giải quyết tương đối với root object.

Ví dụ:

    parser.parseExpression("address.city")
        .setValue(context, customer, "Hue");

Trong trường hợp này customer là root object.

Nếu muốn truy cập object thông qua variable, hãy đặt variable trong EvaluationContext và dùng prefix #:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("customer", customer);

    Expression expression = parser.parseExpression(
        "#customer.address.city = 'Hue'"
    );

    expression.getValue(context);

Kết quả là property city của Address thuộc Customer được cập nhật thành Hue.

Hai đường dẫn sau có thể trỏ tới cùng một property nếu customer được dùng làm root object hoặc variable tương ứng:

    address.city

    #customer.address.city

Khác biệt nằm ở cách SpEL tìm object bắt đầu. Đường dẫn đầu dùng root object; đường dẫn thứ hai tìm variable customer trong context.

Khi viết biểu thức cho nhiều object, variable giúp xác định rõ object đích và tránh phụ thuộc vào root object ngầm định.

## 7. Điều kiện để một property có thể được ghi

Parse thành công không có nghĩa là property chắc chắn ghi được. Khi evaluation thực hiện assignment, SpEL cần tìm một property accessor có khả năng ghi giá trị vào property đích.

Với JavaBean thông thường, các yếu tố cần kiểm tra gồm:

- Object đích không null.
- Property có thể được nhận diện theo tên.
- Có setter phù hợp hoặc cơ chế ghi khác được accessor hỗ trợ.
- Giá trị mới có thể chuyển đổi sang kiểu property.
- EvaluationContext có accessor cho phép thao tác ghi.
- Quyền truy cập của ứng dụng cho phép cập nhật object đó.

StandardEvaluationContext mặc định sử dụng reflective property access hỗ trợ các thao tác đọc và ghi phù hợp với object. Nếu ứng dụng thay đổi danh sách PropertyAccessor, hành vi ghi có thể khác.

Ví dụ property chỉ có getter:

    public String getCode() {
        return code;
    }

Nếu không có setter và accessor không có cơ chế ghi thay thế, việc gán code có thể thất bại.

Không nên giả định mọi property đọc được đều ghi được. Đọc và ghi là hai khả năng riêng của property accessor.

## 8. Gán property lồng nhau khi object trung gian là null

Đây là lỗi thường gặp nhất khi gán property lồng nhau.

Ví dụ:

    Customer customer = new Customer();
    customer.setAddress(null);

    Expression expression =
        parser.parseExpression("address.city = 'Hue'");

    expression.getValue(
        new StandardEvaluationContext(),
        customer
    );

SpEL cần truy cập address trước khi ghi city. Nhưng address đang null, nên không có object Address để nhận giá trị city.

Trong cấu hình thông thường, không nên giả định SpEL tự tạo toàn bộ object graph chỉ vì expression có đường dẫn lồng nhau.

Cách chủ động nhất là khởi tạo object trung gian trước:

    Customer customer = new Customer();

    Address address = new Address();
    customer.setAddress(address);

    parser.parseExpression("address.city = 'Hue'")
        .setValue(
            new StandardEvaluationContext(),
            customer,
            "Hue"
        );

Một số cấu hình SpEL có hỗ trợ tự mở rộng null reference khi điều hướng property. Hành vi này được điều khiển bởi parser configuration, chẳng hạn tùy chọn autoGrowNullReferences. Nó chỉ hoạt động trong những trường hợp framework có thể tạo object phù hợp và không thay thế cho thiết kế object model rõ ràng.

Khi bật auto-grow, hãy xem xét constructor, tác dụng phụ khi tạo object và giới hạn kích thước collection. Không bật chỉ để che giấu một object graph chưa được khởi tạo đúng.

## 9. Chuyển đổi kiểu khi gán

Giá trị của expression không phải lúc nào cũng có cùng kiểu với property đích. SpEL sử dụng TypeConverter trong EvaluationContext để chuyển đổi kiểu khi có thể.

Ví dụ property age là int:

    public class Customer {
        private int age;

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            this.age = age;
        }
    }

Có thể gán một string literal:

    parser.parseExpression("age = '35'")
        .getValue(context, customer);

Nếu TypeConverter hiện tại hỗ trợ chuyển String thành kiểu số tương ứng, property age có thể nhận giá trị số 35.

Cách tường minh hơn là truyền giá trị số từ Java:

    parser.parseExpression("age")
        .setValue(context, customer, 35);

Nếu không có conversion phù hợp, hoặc giá trị không thể chuyển đổi, evaluation sẽ thất bại.

Với property lồng nhau, quy tắc chuyển đổi cũng áp dụng tại property cuối cùng:

    address.postalCode = '700000'

Giá trị được chuyển đổi theo kiểu của postalCode nếu converter hỗ trợ.

Không nên dựa vào chuyển đổi ngầm cho các dữ liệu quan trọng mà chưa xác định rõ format, locale và quy tắc chuyển đổi của ứng dụng.

## 10. Property path và collection hoặc map

Đường dẫn property có thể tiếp tục kết hợp với indexer để ghi phần tử collection hoặc map khi accessor và object hỗ trợ.

Ví dụ với map:

    preferences['language'] = 'vi'

Ví dụ với list:

    scores[0] = 95

Với object lồng nhau chứa collection:

    customer.addresses[0].city = 'Hue'

Các đường dẫn này có cùng nguyên tắc: SpEL điều hướng tới object hoặc phần tử đích rồi thực hiện thao tác ghi.

Tuy nhiên, phần tử ở index tương ứng phải tồn tại hoặc collection phải được cấu hình cho phép mở rộng theo hành vi của SpEL. Một index vượt giới hạn có thể gây evaluation error nếu không có auto-grow phù hợp.

Đối với map, key phải hợp lệ theo kiểu key mà map sử dụng. Việc truy cập collection và map cũng phụ thuộc vào kiểu dữ liệu thực tế và accessor được cấu hình.

## 11. setValue và assignment expression nên dùng khi nào?

Hai cách có mục đích gần nhau nhưng thể hiện ý định khác nhau.

| Tiêu chí | setValue | Toán tử = trong SpEL |
| --- | --- | --- |
| Đường dẫn property | Expression chỉ chứa đường dẫn | Đường dẫn và giá trị nằm trong cùng expression |
| Giá trị gán | Truyền qua tham số Java | Viết trong biểu thức SpEL |
| Dữ liệu động từ Java | Rõ ràng, dễ truyền kiểu | Có thể tham chiếu variable trong context |
| Dễ tái sử dụng | Có thể giữ expression property và truyền nhiều giá trị | Giữ expression assignment đã bao gồm logic gán |
| Phù hợp | Binding dữ liệu và cập nhật property từ Java | Rule hoặc expression cần thể hiện cả phép gán |

Ví dụ dùng setValue:

    Expression property =
        parser.parseExpression("address.city");

    property.setValue(context, customer, newCity);

Ví dụ dùng assignment:

    context.setVariable("newCity", newCity);

    Expression assignment = parser.parseExpression(
        "address.city = #newCity"
    );

    assignment.getValue(context, customer);

Nếu giá trị đến từ Java code, setValue thường thể hiện rõ ranh giới giữa đường dẫn và dữ liệu cần ghi. Nếu logic assignment là một phần của expression được cấu hình, toán tử = có thể phù hợp hơn.

## 12. Kiểm tra lỗi khi gán property

Khi assignment thất bại, hãy xác định lỗi xảy ra trong parsing hay evaluation.

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Parse error | Cú pháp đường dẫn hoặc assignment không hợp lệ | Kiểm tra tên property, dấu chấm, dấu ngoặc và toán tử |
| Property cannot be written | Không có accessor hỗ trợ ghi | Kiểm tra setter và danh sách PropertyAccessor |
| Null reference | Object trung gian trong đường dẫn là null | Kiểm tra từng bước như customer.address |
| Type conversion error | Giá trị mới không chuyển được sang kiểu đích | Kiểm tra kiểu property và TypeConverter |
| Index out of bounds | Phần tử collection chưa tồn tại | Kiểm tra kích thước list và cấu hình auto-grow |
| Variable not found | Context chưa có variable được tham chiếu | Kiểm tra setVariable và tên sau dấu # |

Ví dụ, expression sau có thể parse thành công:

    address.city = 'Hue'

Nhưng nếu customer không có address, evaluation vẫn thất bại. Điều đó cho thấy cú pháp hợp lệ và khả năng ghi dữ liệu là hai bước khác nhau.

Khi debug, hãy kiểm tra lần lượt root object, từng property trung gian, property cuối, accessor và kiểu dữ liệu.

## 13. Tác động phụ và an toàn khi dùng assignment

Assignment làm thay đổi object. Nó có tác dụng phụ và có thể ảnh hưởng tới các thành phần khác đang giữ cùng reference.

Vì vậy:

- Không đánh giá expression có phép gán trên object dùng chung nếu chưa kiểm soát tác động.
- Không để biểu thức không tin cậy tùy ý ghi property.
- Chỉ cung cấp object có phạm vi ghi cần thiết cho evaluation context.
- Giới hạn PropertyAccessor và quyền truy cập theo nghiệp vụ.
- Không xem việc dùng SimpleEvaluationContext là tự động an toàn trong mọi trường hợp; cần cấu hình đúng các tính năng được phép.
- Với cập nhật dữ liệu nghiệp vụ quan trọng, cân nhắc thực hiện qua method hoặc service có validation và transaction thay vì cho phép expression ghi tùy ý.

Nếu một expression chứa nhiều thao tác có tác dụng phụ và thao tác sau thất bại, những thay đổi trước đó có thể đã xảy ra. SpEL assignment tự nó không tạo transaction hay cơ chế rollback.

## 14. Những điểm cần nhớ

- Property đơn là đường dẫn trực tiếp trên root object, ví dụ name.
- Property lồng nhau là chuỗi truy cập, ví dụ address.city.
- Có thể ghi property bằng Expression.setValue hoặc toán tử assignment =.
- Toán tử = là gán; == là so sánh bằng.
- Property accessor phải hỗ trợ ghi và giá trị phải tương thích với kiểu đích.
- Mọi object trung gian trong đường dẫn lồng nhau phải tồn tại, trừ khi cấu hình auto-grow phù hợp xử lý được.
- Variable trong EvaluationContext có thể được truy cập bằng prefix #.
- TypeConverter có thể chuyển đổi giá trị khi gán nếu conversion được hỗ trợ.
- Assignment có tác dụng phụ; cần giới hạn object và quyền ghi khi đánh giá expression.

Khi thiết kế một phép gán SpEL, hãy xác định root object, đường dẫn property, object trung gian, khả năng ghi và kiểu giá trị trước khi đánh giá. Điều đó giúp phân biệt lỗi cú pháp với lỗi truy cập object và lỗi chuyển đổi dữ liệu.
