# Nested path và PropertyAccessor trong SpEL

Spring Expression Language (SpEL) có thể truy cập property lồng nhau bằng cách nối tên property qua dấu chấm. Một đường dẫn như `customer.address.city` cho phép expression đi từ root object tới customer, tiếp tục tới address rồi lấy city. Mỗi bước truy cập được thực hiện thông qua **PropertyAccessor** phù hợp với object hiện tại.

Hiểu nested path và PropertyAccessor giúp đọc hoặc cập nhật object graph một cách rõ ràng, xử lý đúng trường hợp null và chọn EvaluationContext phù hợp cho data binding.

## 1. Nested path là gì?

Nested path là đường dẫn gồm nhiều property liên tiếp, phân tách bằng dấu chấm:

    customer.address.city

Giả sử root object là một Order, có property `customer`; Customer có property `address`; Address có property `city`. Expression trên lần lượt đọc ba cấp property và trả về tên thành phố.

Có thể dùng nested path trong nhiều thao tác:

    customer.address.city
    customer.contact.email
    shippingAddress.postalCode
    items[0].product.name

Nested path giúp expression truy cập trực tiếp dữ liệu cần thiết mà không phải gọi từng getter trong Java. Tên property thường là tên JavaBean property, ví dụ `name` tương ứng với getter `getName()`, hoặc `active` tương ứng với getter Boolean `isActive()` hay `getActive()`.

Property path và method invocation là hai cơ chế khác nhau. `customer.name` đọc property `name`; `customer.getName()` là lời gọi method tường minh.

## 2. Cách SpEL đánh giá từng cấp property

Khi đánh giá `customer.address.city`, SpEL không tra cứu toàn bộ chuỗi như một tên property duy nhất. Nó thực hiện lần lượt:

1. Bắt đầu từ root object hoặc target hiện tại.
2. Tìm cách đọc property `customer` trên object đó.
3. Dùng giá trị customer vừa đọc làm target cho bước tiếp theo.
4. Đọc property `address` trên customer.
5. Dùng address làm target để đọc property `city`.

Mỗi bước có thể sử dụng một PropertyAccessor phù hợp với kiểu object hiện tại. Vì vậy, một nested path có thể đi qua nhiều loại object khác nhau, miễn là context có accessor xử lý được từng loại.

Ví dụ:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    ExpressionParser parser = new SpelExpressionParser();

    String city = parser.parseExpression(
            "customer.address.city"
    ).getValue(context, String.class);

Root object là order; kết quả cuối cùng là city của customer gắn với order.

Nếu một property trung gian trả về null, SpEL không thể tiếp tục truy cập property phía sau trên null. Cần kiểm tra hoặc dùng safe navigation ở đúng vị trí có thể null.

## 3. PropertyAccessor chịu trách nhiệm đọc và ghi

EvaluationContext chứa danh sách PropertyAccessor. Accessor xác định target nào nó hỗ trợ, property nào có thể đọc/ghi và cách thực hiện thao tác.

Các phương thức chính của interface:

| Phương thức | Vai trò |
|---|---|
| `getSpecificTargetClasses()` | Khai báo các class target được accessor hỗ trợ |
| `canRead(context, target, name)` | Kiểm tra có thể đọc property hay không |
| `read(context, target, name)` | Đọc giá trị property |
| `canWrite(context, target, name)` | Kiểm tra có thể ghi property hay không |
| `write(context, target, name, newValue)` | Ghi giá trị mới vào property |

Khi SpEL cần đọc một property, nó tìm accessor có thể đọc target và tên property đó. Khi gán giá trị, nó cần accessor hỗ trợ ghi. Nếu không có accessor phù hợp, hoặc property không tồn tại/không thể truy cập, quá trình đánh giá sẽ thất bại.

Cần phân biệt khả năng kỹ thuật và quyền nghiệp vụ. `canWrite` cho biết accessor có thể ghi property theo cấu hình của nó; điều đó không tự chứng minh người gọi được phép thay đổi dữ liệu. Quyền ghi phải được kiểm soát ở tầng ứng dụng hoặc trong policy của accessor.

## 4. ReflectivePropertyAccessor và JavaBean property

StandardEvaluationContext mặc định có ReflectivePropertyAccessor để truy cập property thông qua reflection. Với các JavaBean thông thường, accessor có thể đọc property thông qua getter và ghi thông qua setter phù hợp.

Ví dụ class:

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

Expression có thể đọc:

    name
    address.city

Và có thể ghi property nếu accessor hỗ trợ ghi, property có setter phù hợp và các object trung gian đã tồn tại:

    name = 'Lan'
    address.city = 'Ho Chi Minh City'

Không phải mọi property đều có thể ghi. Một property chỉ có getter thường có thể đọc nhưng không thể gán qua accessor. Property có setter private hoặc không thể truy cập cũng có thể không đáp ứng yêu cầu ghi tùy accessor và cấu hình.

Đối với field hoặc kiểu object đặc biệt, khả năng truy cập phụ thuộc PropertyAccessor được sử dụng. Không nên giả định mọi field trong Java đều tự động trở thành property SpEL có thể truy cập.

## 5. Đọc nested path bằng SimpleEvaluationContext

Khi use case chủ yếu là data binding và đọc property, SimpleEvaluationContext có thể giới hạn tập tính năng được bật. Builder read-only data binding cung cấp PropertyAccessor phù hợp cho việc đọc:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(order)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    String city = parser.parseExpression(
            "customer.address.city"
    ).getValue(context, String.class);

Cách này phù hợp với expression chỉ cần đọc dữ liệu từ object graph. SimpleEvaluationContext không cung cấp toàn bộ tính năng của StandardEvaluationContext; nó được thiết kế cho những use case cần phạm vi truy cập hẹp hơn.

Nếu cần ghi property theo data binding, có thể dùng builder read-write:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(order)
                    .build();

Việc chọn read-write chỉ mở khả năng ghi cho các property mà accessor hỗ trợ. Ứng dụng vẫn cần xác thực người gọi, target và property được phép cập nhật.

## 6. Ghi giá trị vào nested path

Có thể dùng toán tử assignment trong expression hoặc API `Expression.setValue` để cập nhật property.

Ví dụ với context read-write:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(order)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    parser.parseExpression("customer.address.city")
            .setValue(context, "Da Nang");

SpEL đi theo nested path để tìm property cuối cùng, sau đó dùng accessor ghi giá trị vào `city`. Nếu kiểu property đích khác kiểu giá trị nguồn, TypeConverter của EvaluationContext có thể hỗ trợ chuyển đổi.

Một expression assignment cũng có thể được đánh giá:

    parser.parseExpression(
            "customer.address.city = 'Da Nang'"
    ).getValue(context);

Cả hai cách đều có thể thay đổi object. Chỉ sử dụng khi context được cấu hình quyền ghi phù hợp và ứng dụng đã xác minh rằng thao tác cập nhật được phép.

## 7. Object trung gian null trong nested path

Một nested path thông thường cần từng object trung gian tồn tại. Ví dụ:

    customer.address.city

Nếu `customer` là null, SpEL không thể đọc `address`. Nếu customer tồn tại nhưng `address` null, SpEL không thể đọc `city`.

Có thể dùng safe navigation để xử lý những bước có thể null:

    customer?.address?.city

Nếu customer null hoặc address null, kết quả của chuỗi truy cập an toàn là null thay vì tiếp tục truy cập property trên null.

Nếu cần cung cấp giá trị mặc định, có thể dùng Elvis operator:

    customer?.address?.city ?: 'Unknown'

Safe navigation chỉ bảo vệ bước được đặt toán tử. Nếu bỏ qua một cấp có thể null, lỗi vẫn có thể xảy ra ở cấp đó. Hãy đặt `?.` tại mỗi ranh giới object có khả năng null.

Đối với assignment, safe navigation không tự tạo object trung gian. Nếu customer hoặc address chưa tồn tại, cần khởi tạo chúng trong Java hoặc service nghiệp vụ trước khi ghi property cuối.

## 8. Kết hợp nested path với index và map key

Nested path có thể kết hợp với toán tử index để đi qua list, array hoặc map:

    items[0].product.name
    orders[1].customer.email
    attributes['shipping'].city

Trong ví dụ đầu, SpEL lấy phần tử đầu tiên của list `items`, rồi đọc product và name. Trong ví dụ cuối, SpEL lấy value theo key `shipping` từ map `attributes`, sau đó đọc city.

Index của list và array bắt đầu từ 0; map được truy cập bằng key. Nếu index ngoài phạm vi, key không tồn tại hoặc giá trị trung gian là null, biểu thức có thể trả null hoặc phát sinh lỗi tùy thao tác và cấu trúc dữ liệu.

Với dữ liệu động, nên kiểm tra collection không null, vị trí nằm trong phạm vi và object trung gian tồn tại trước khi đọc hoặc ghi property sâu hơn.

## 9. PropertyAccessor tùy chỉnh

Nếu model không phải JavaBean thông thường hoặc cần policy riêng, có thể triển khai PropertyAccessor tùy chỉnh. Ví dụ, accessor có thể đọc property từ một object dạng dynamic record hoặc giới hạn property được phép truy cập.

Cấu trúc minh họa:

    public final class CustomerPropertyAccessor
            implements PropertyAccessor {

        @Override
        public Class<?>[] getSpecificTargetClasses() {
            return new Class<?>[] { Customer.class };
        }

        @Override
        public boolean canRead(
                EvaluationContext context,
                Object target,
                String name) {
            return target instanceof Customer
                    && isAllowedProperty(name);
        }

        @Override
        public TypedValue read(
                EvaluationContext context,
                Object target,
                String name) throws AccessException {
            Customer customer = (Customer) target;
            return readCustomerProperty(customer, name);
        }

        @Override
        public boolean canWrite(
                EvaluationContext context,
                Object target,
                String name) {
            return target instanceof Customer
                    && isWritableProperty(name);
        }

        @Override
        public void write(
                EvaluationContext context,
                Object target,
                String name,
                Object newValue) throws AccessException {
            Customer customer = (Customer) target;
            writeCustomerProperty(customer, name, newValue);
        }
    }

Các hàm `isAllowedProperty`, `readCustomerProperty`, `isWritableProperty` và `writeCustomerProperty` là phần xử lý do ứng dụng tự triển khai, không phải API có sẵn của Spring. Accessor thực tế cần kiểm tra target, tên property, kiểu dữ liệu, giá trị mới và policy trước khi ghi.

Có thể đăng ký accessor trên StandardEvaluationContext:

    StandardEvaluationContext context =
            new StandardEvaluationContext(customer);

    context.addPropertyAccessor(
            new CustomerPropertyAccessor()
    );

Với nested path đi qua nhiều class, accessor phải hỗ trợ đúng loại target ở từng cấp. Nếu chỉ hỗ trợ Customer nhưng đường dẫn tiếp tục tới Address, cần một accessor khác hoặc cơ chế phù hợp để xử lý Address.

## 10. Thứ tự và phạm vi của nhiều PropertyAccessor

Một EvaluationContext có thể chứa nhiều PropertyAccessor. Điều này hữu ích khi expression cần truy cập nhiều loại object, ví dụ JavaBean, Map hoặc model riêng của ứng dụng.

Khi thêm accessor tùy chỉnh, hãy xác định rõ class và property mà nó hỗ trợ. Tránh accessor quá rộng luôn trả về true cho mọi target/property, vì nó có thể chiếm quyền xử lý những property mà accessor khác vốn đảm nhiệm.

Nếu nhiều accessor có thể xử lý cùng target và property, thứ tự tìm kiếm có thể ảnh hưởng accessor được sử dụng. Hãy cấu hình danh sách accessor có chủ đích và kiểm thử các trường hợp trùng phạm vi. Không nên dựa vào thứ tự ngầm nếu hai accessor có hành vi khác nhau.

Với property quan trọng hoặc có quyền ghi, accessor nên từ chối rõ ràng các tên không nằm trong allowlist. Việc property tồn tại trên object không đồng nghĩa expression trong use case hiện tại được phép truy cập hoặc cập nhật nó.

## 11. Chuyển đổi kiểu khi ghi property

Khi ghi vào property có kiểu đích cụ thể, giá trị nguồn có thể cần được chuyển đổi. TypeConverter của EvaluationContext hỗ trợ việc chuyển đổi trong những tình huống phù hợp.

Ví dụ property `quantity` là Integer nhưng giá trị truyền vào là chuỗi:

    parser.parseExpression("quantity")
            .setValue(context, "12");

Nếu converter hỗ trợ String sang Integer, property có thể nhận giá trị 12. Nếu không chuyển đổi được, thao tác ghi thất bại.

Chuyển đổi kiểu không thay thế validation nghiệp vụ. Một chuỗi có thể chuyển thành số hợp lệ nhưng vẫn vượt giới hạn số lượng. Hãy xác thực dữ liệu trước khi cập nhật và xử lý lỗi conversion rõ ràng.

Với nested path, việc chuyển đổi áp dụng ở property cuối cùng được ghi. Các object trung gian vẫn phải được resolve thành công trước khi SpEL có thể tới property đích.

## 12. Ví dụ đầy đủ trong Java

Ví dụ sau đọc và cập nhật thành phố của địa chỉ giao hàng:

    public class Address {
        private String city;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public class Customer {
        private Address address;

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public class Order {
        private Customer customer;

        public Customer getCustomer() {
            return customer;
        }

        public void setCustomer(Customer customer) {
            this.customer = customer;
        }
    }

    Order order = loadOrder();

    SimpleEvaluationContext readContext =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(order)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    String city = parser.parseExpression(
            "customer.address.city"
    ).getValue(readContext, String.class);

    SimpleEvaluationContext writeContext =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(order)
                    .build();

    parser.parseExpression("customer.address.city")
            .setValue(writeContext, "Can Tho");

Ví dụ giả định order, customer và address đã được khởi tạo. Nếu một object trung gian null, cần xử lý trước khi đọc hoặc ghi nested path. Trong ứng dụng thực tế, hãy dùng service nghiệp vụ để tải object, kiểm tra quyền và bảo đảm trạng thái hợp lệ trước khi cập nhật.

## 13. Lỗi thường gặp

- **Property không tồn tại:** kiểm tra tên JavaBean property và getter/setter tương ứng.
- **Object trung gian null:** kiểm tra từng cấp hoặc dùng safe navigation khi đọc.
- **Ghi vào property chỉ đọc:** xác nhận accessor hỗ trợ write và property có setter phù hợp.
- **Nhầm property với method:** `customer.name` đọc property; `customer.getName()` gọi method.
- **Dùng nhầm context:** SimpleEvaluationContext read-only không cho phép ghi property.
- **Index hoặc map key không hợp lệ:** kiểm tra phạm vi và key trước khi tiếp tục nested path.
- **Converter không hỗ trợ kiểu đích:** chuẩn hóa dữ liệu hoặc cấu hình converter phù hợp.
- **Custom accessor quá rộng:** giới hạn target class và property được phép xử lý.
- **Cho rằng assignment tự tạo object trung gian:** hãy khởi tạo customer/address trong Java trước khi gán property sâu.

## 14. Ghi nhớ

Nested path cho phép SpEL đi qua nhiều property bằng dấu chấm, ví dụ `customer.address.city`. SpEL resolve từng cấp trên object hiện tại bằng PropertyAccessor; ReflectivePropertyAccessor thường xử lý JavaBean property trong StandardEvaluationContext. SimpleEvaluationContext cung cấp chế độ data binding chỉ đọc hoặc đọc/ghi với phạm vi tính năng hạn chế hơn. Khi đọc nested path, hãy xử lý null ở từng cấp; khi ghi, mọi object trung gian phải tồn tại và accessor phải hỗ trợ ghi property đích. Nếu model hoặc policy đặc biệt, hãy dùng PropertyAccessor tùy chỉnh với phạm vi target và property rõ ràng.
