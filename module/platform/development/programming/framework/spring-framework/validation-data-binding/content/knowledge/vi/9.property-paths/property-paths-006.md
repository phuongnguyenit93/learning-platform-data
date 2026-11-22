# autoGrowNestedPaths và điều kiện tự khởi tạo đối tượng trong Spring

## 1. Bài toán: một đường dẫn thuộc tính đi qua giá trị null

Trong Spring Framework, **data binding** cho phép ánh xạ dữ liệu đầu vào vào đối tượng Java bằng các tên thuộc tính như `name`, `address.city`, `shippingAddress.postalCode` hoặc `items[1].sku`. Dấu chấm biểu thị truy cập sâu vào object graph; cú pháp chỉ mục biểu thị phần tử collection/array hoặc khóa map tương ứng.

Giả sử một form chứa:

~~~java
public class CustomerForm {
    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

Và `Address` có thuộc tính `city`. Khi request gửi:

~~~text
address.city=Da Nang
~~~

Spring cần đi qua hai bước: lấy `customerForm.address` rồi gán `city`. Nhưng nếu `getAddress()` trả về `null`, làm sao đặt `address.city`?

`autoGrowNestedPaths` là cấu hình của `DataBinder` và các bộ truy cập thuộc tính liên quan cho phép **tự tạo những giá trị trung gian đang null khi có thể**, sau đó tiếp tục duyệt đường dẫn. Cơ chế này cũng hỗ trợ mở rộng collection/array khi truy cập một chỉ mục vượt phạm vi hiện có, trong giới hạn đã cấu hình.

Nếu bật và lớp `Address` có thể được khởi tạo phù hợp:

~~~text
Trước binding:
CustomerForm
└── address = null

Input:
"address.city" = "Da Nang"

Sau binding:
CustomerForm
└── address = Address
    └── city = "Da Nang"
~~~

Nếu tắt, đối tượng trung gian `address` vẫn `null`. Hệ thống không thể gán `city` qua đường dẫn ấy, và tùy API cùng các cờ xử lý field không hợp lệ, việc bind có thể phát sinh lỗi truy cập đường dẫn hoặc bỏ qua field.

**Điểm quan trọng:** auto-grow không có nghĩa Spring luôn tạo được mọi object, không phải một cơ chế khởi tạo dependency injection và không bảo đảm input hợp lệ. Nó xử lý đường dẫn thuộc tính trong một luồng binding/truy cập thuộc tính cụ thể.

## 2. Đặt autoGrowNestedPaths đúng chỗ trong Spring

Các thành phần cần phân biệt:

| Thành phần | Vai trò | Quan hệ với auto-grow |
| --- | --- | --- |
| `org.springframework.validation.DataBinder` | Nhận các cặp tên–giá trị để gán vào target và quản lý lỗi binding | Có `setAutoGrowNestedPaths(boolean)`, mặc định `true` ở binder tiêu chuẩn |
| `org.springframework.web.bind.WebDataBinder` | Mở rộng `DataBinder` trong luồng web | Kế thừa cấu hình auto-grow, thường được Spring MVC khởi tạo cho một lần binding |
| `org.springframework.beans.BeanWrapper` / `BeanWrapperImpl` | Truy cập thuộc tính JavaBeans qua getter/setter | Hỗ trợ flag auto-grow; `BeanWrapperImpl` dùng trực tiếp có mặc định `false` |
| `org.springframework.beans.ConfigurablePropertyAccessor` | Hợp đồng cấu hình cho property accessor | Khai báo `setAutoGrowNestedPaths` cùng các tùy chọn truy cập |
| `org.springframework.beans.MutablePropertyValues` | Chứa các giá trị đầu vào cần bind | Chỉ mô tả field/value, bản thân nó không tự tạo nested object |
| `org.springframework.validation.BindingResult` | Chứa lỗi và target sau binding | Cho phép kiểm tra kết quả; không điều khiển quá trình auto-grow |
| `org.springframework.core.convert.ConversionService` | Chuyển giá trị nguồn thành kiểu Java đích | Chuyển giá trị sau khi có đường truy cập phù hợp; không thay cho việc tạo container/nested bean |

**Mặc định cần nhớ:** theo Javadoc Spring Framework 6.2, một `DataBinder` tiêu chuẩn bật `autoGrowNestedPaths=true`. Ngược lại, một `BeanWrapperImpl` được tạo trực tiếp có mặc định `false`. Hai mặc định đó thuộc hai tầng khác nhau. Không xem câu “Spring luôn bật/tắt auto-grow” là một phát biểu đủ chính xác.

Trong Java:

~~~java
DataBinder binder = new DataBinder(new CustomerForm());
System.out.println(binder.isAutoGrowNestedPaths()); // true
binder.setAutoGrowNestedPaths(false);
~~~

Đây là snippet minh họa với các import Spring cần thiết. Việc đổi flag nên thực hiện **trước khi binder được khởi tạo để truy cập thuộc tính/bắt đầu binding**. Javadoc của `DataBinder` yêu cầu cấu hình sớm; nếu binding result đã được khởi tạo, thay flag có thể bị từ chối bởi trạng thái của binder.

## 3. Cơ chế bên trong: một đường dẫn được mở rộng như thế nào?

Ví dụ `customer.address.city` được hiểu là chuỗi các thao tác:

1. Xác định target `customer` và loại truy cập đang dùng: JavaBeans property access hoặc direct field access.
2. Đọc thuộc tính trung gian `address`.
3. Nếu `address` khác `null`, tiếp tục vào object sẵn có.
4. Nếu `address == null` và auto-grow **bật**, thử tạo giá trị mặc định cho kiểu `Address`.
5. Gắn giá trị vừa tạo vào thuộc tính trung gian nếu đường truy cập cho phép.
6. Truy cập `city` và chuyển giá trị nguồn thành kiểu của property, rồi gán vào đó.

Ví dụ pseudo-flow:

~~~text
setPropertyValue("address.city", "Da Nang")
    |
    v
address tồn tại?
    |                         \
    | Có                       \ Không
    v                           v
dùng address hiện tại        autoGrowNestedPaths?
                                | Có              | Không
                                v                 v
                         Tạo Address?         Không thể đi tiếp
                           | Có | Không         -> lỗi/ignore theo API
                           v        v
                         gắn     lỗi tạo object
                           |
                           v
                   set address.city
~~~

Auto-grow là cơ chế **điền đối tượng trung gian**; nó không tự chuyển “Da Nang” thành `Address`. Nếu request chỉ có key `address` thay vì `address.city`, việc chuyển toàn bộ chuỗi thành `Address` lại liên quan `Converter`/`PropertyEditor` phù hợp. Hai trường hợp đó khác nhau.

Với đường dẫn dài hơn, ví dụ `customer.address.country.name`, nhiều trung gian có thể cần được tạo. Nếu bất cứ bước nào thiếu khả năng khởi tạo hoặc ghi đối tượng mới, toàn đường dẫn có thể thất bại; việc một level khởi tạo thành công không bảo đảm các level còn lại thành công.

## 4. Những điều kiện để tự tạo một nested object

Auto-grow chỉ có thể hoàn thành nếu các điều kiện kỹ thuật đồng thời được đáp ứng.

### 4.1. Thuộc tính trung gian phải xác định được kiểu

Spring cần biết kiểu đích của `address` để tạo giá trị. Ví dụ rõ ràng:

~~~java
private Address address;

public Address getAddress() { return address; }
public void setAddress(Address address) { this.address = address; }
~~~

Với một field khai báo kiểu `Object` hoặc interface `Location`, không có thông tin đủ để biết nên tạo implementation nào. Spring không tự đoán giữa `HomeAddress` và `OfficeAddress`. Khi cần, ứng dụng có thể **khởi tạo sẵn một implementation cụ thể** hoặc dùng DTO có loại field cụ thể hơn.

Một nested bean có kiểu là abstract class hoặc interface thường không thể được tạo trực tiếp chỉ từ tên property. Nếu giá trị trung gian đã tồn tại và là một implementation hợp lệ thì không cần tạo mới, và binding có thể tiếp tục theo đường truy cập của đối tượng đang có.

### 4.2. Lớp trung gian cần một cách tạo instance phù hợp

Với JavaBean thông thường, Spring có thể thử gọi constructor không tham số để tạo object khi property null. Ví dụ lớp có no-arg constructor và property ghi được:

~~~java
public class Address {
    private String city;

    public Address() {
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

Trường hợp thường không tự tạo được:

~~~java
public class AddressWithoutNoArg {
    private final String city;

    public AddressWithoutNoArg(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }
}
~~~

Với bean `AddressWithoutNoArg` chưa được khởi tạo, không có constructor không tham số để Spring tự tạo theo cơ chế nested property auto-grow. Đây không phải lời hứa rằng Spring có thể tự chọn giá trị hợp lệ cho đối số `city`. Một record hoặc kiểu bất biến với constructor có tham số cũng cần cách thiết kế binding riêng, thay vì dựa vào auto-grow setter/property của JavaBeans.

Ngay cả khi lớp có no-arg constructor, việc khởi tạo vẫn có thể thất bại vì constructor private hoặc không thể truy cập trong môi trường chạy, constructor ném exception, hoặc thiếu khả năng tạo kiểu đích phù hợp. Kết quả có thể là `NullValueInNestedPathException` hoặc exception truy cập thuộc tính liên quan, tùy bước thất bại. Không giả định mọi lỗi auto-grow là một `typeMismatch` thông thường.

### 4.3. Đối tượng vừa tạo phải có cách gắn vào graph

Khi Spring tạo một `Address` cho `customer.address`, nó cần lưu object đó lại qua setter/field accessor phù hợp.

Đối với bean property access mặc định, các getter/setter chính xác theo JavaBeans quan trọng. Ví dụ có getter nhưng hoàn toàn không có setter để ghi `address`, và field đó đang null, thì khả năng gắn đối tượng mới có thể bị chặn. Direct field access có đường truy cập khác, nhưng phải được bật rõ ràng và tuân theo giới hạn/cơ chế của phiên bản Spring.

Nếu property đã có giá trị khác null, Spring **không cần tạo một instance mới**. Bởi vậy đối tượng có constructor phức tạp vẫn có thể được bind vào property con nếu chính đối tượng trung gian đã được ứng dụng khởi tạo trước và cho phép ghi field cuối.

### 4.4. Các field cuối phải ghi được và giá trị phải chuyển kiểu được

Auto-grow giải quyết `address == null`, nhưng không giải quyết một field đích kiểu `Integer` nhận chuỗi `"abc"`. Khi đi tới `address.zipCode` thành công, converter vẫn có thể thất bại với input không hợp lệ.

Ví dụ:

~~~text
address == null
address.zipCode = "abc"
zipCode type = Integer
~~~

Có thể có hai kết quả khác nhau:

- `Address` được tạo nhưng `zipCode` không được gán vì lỗi chuyển kiểu.
- `BindingResult` ghi một `FieldError` như `typeMismatch` cho path `address.zipCode`.

Đừng lấy việc `address != null` làm bằng chứng mọi input đã hợp lệ. Validation nghiệp vụ (`@Valid`, `@NotBlank`, `@Min`...) lại là bước khác, chỉ xảy ra khi ứng dụng đã cấu hình/trigger đúng.

### 4.5. Đường dẫn phải được phép bind

Ngay cả khi auto-grow bật, `DataBinder.setAllowedFields(...)` hoặc chế độ declarative binding có thể giới hạn field được gán.

Ví dụ:

~~~java
binder.setAllowedFields("address.city", "address.postalCode");
~~~

Điều này cho phép các property path được chỉ rõ trong **property binding**. Field ngoài danh sách bị suppress, không thể dựa vào auto-grow để tự gán. Với Spring 6.1+, `setDeclarativeBinding(true)` là một lựa chọn bổ sung theo hợp đồng của DataBinder, nhưng không nên coi nó thay thế mọi quy tắc về DTO, constructor binding hoặc bảo mật.

## 5. Ví dụ Java 17+ chạy độc lập với Spring Core/Context

Ví dụ này không cần Spring Boot hay servlet container. Nó chứng minh hai điểm:

- `DataBinder` có thể tự tạo `Address` đang null để xử lý `address.city`.
- Binder có thể mở rộng `List<Line>` đến một chỉ mục hợp lệ và tạo phần tử có kiểu xác định khi xử lý `lines[1].sku`.

Điều kiện: máy có **JDK 17+**, Gradle và quyền tải dependency Maven Central.

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'nested-path-autogrow'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.6'
}

application {
    mainClass = 'NestedPathAutoGrowDemo'
}
~~~

Tạo `src/main/java/NestedPathAutoGrowDemo.java`:

~~~java
import java.util.List;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

public class NestedPathAutoGrowDemo {

    public static class Address {
        private String city;

        public Address() {
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public static class CustomerForm {
        private Address address;

        public CustomerForm() {
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public static class Line {
        private String sku;

        public Line() {
        }

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }
    }

    public static class OrderForm {
        private List<Line> lines;

        public OrderForm() {
        }

        public List<Line> getLines() {
            return lines;
        }

        public void setLines(List<Line> lines) {
            this.lines = lines;
        }
    }

    public static void main(String[] args) {
        CustomerForm customer = new CustomerForm();
        DataBinder customerBinder = new DataBinder(customer, "customerForm");

        System.out.println("autoGrow=" + customerBinder.isAutoGrowNestedPaths());
        System.out.println("addressBefore=" + customer.getAddress());

        customerBinder.setAllowedFields("address.city");

        MutablePropertyValues customerValues = new MutablePropertyValues();
        customerValues.add("address.city", "Da Nang");
        customerBinder.bind(customerValues);

        System.out.println("city=" + customer.getAddress().getCity());
        System.out.println("customerErrors=" +
                customerBinder.getBindingResult().getErrorCount());

        OrderForm order = new OrderForm();
        DataBinder orderBinder = new DataBinder(order, "orderForm");
        orderBinder.setAutoGrowCollectionLimit(3);
        orderBinder.setAllowedFields("lines[1].sku");

        MutablePropertyValues orderValues = new MutablePropertyValues();
        orderValues.add("lines[1].sku", "KB-02");
        orderBinder.bind(orderValues);

        System.out.println("lineCount=" + order.getLines().size());
        System.out.println("secondSku=" + order.getLines().get(1).getSku());
        System.out.println("orderErrors=" +
                orderBinder.getBindingResult().getErrorCount());
    }
}
~~~

Chạy:

~~~bash
gradle -q run
~~~

Nếu repo có Gradle Wrapper, dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows.

**Đầu ra dự kiến của chương trình trên với Spring 6.2.6**:

~~~text
autoGrow=true
addressBefore=null
city=Da Nang
customerErrors=0
lineCount=2
secondSku=KB-02
orderErrors=0
~~~

Giải thích các giá trị:

1. `autoGrow=true` cho biết binder tiêu chuẩn bật tính năng mặc định; `addressBefore=null` xác nhận chưa có đối tượng lồng nhau.
2. Sau `bind`, Spring tạo `Address` và đặt `city`, vì kiểu cụ thể có constructor không tham số và các property phù hợp.
3. `lineCount=2` không phải vì input khai báo hai line. Spring mở rộng collection để có thể truy cập index 1; index Java bắt đầu từ 0.
4. `secondSku=KB-02` xác nhận phần tử index 1 tồn tại và trường `sku` đã được gán.
5. `customerErrors=0` và `orderErrors=0` chỉ nói không ghi nhận lỗi binding trong phép thử; **không phải** kết quả business validation.

Lưu ý: ví dụ này dùng một `List<Line>` có generic element type cụ thể và một `Line` khởi tạo được. Nếu đổi sang `List<?>` hoặc một interface element không xác định implementation, hành vi tạo phần tử sẽ không thể được suy luận như ví dụ. Nếu đặt `lines[200].sku` với giới hạn 3, Spring không được phép tự mở rộng tới phần tử 200.

## 6. Khi autoGrowNestedPaths=false

Có ba tình huống cần tách biệt:

### 6.1. Nested object đang null

Nếu một `CustomerForm` mới có `address == null`, sau đó cấu hình:

~~~java
DataBinder binder = new DataBinder(customer, "customerForm");
binder.setAutoGrowNestedPaths(false);
binder.bind(values);
~~~

Đây là snippet giả định `customer` và `values` đã tồn tại, trong đó `values` chứa `address.city`. Binder không tự tạo `Address`. Theo cách truy cập và tùy chọn xử lý property không hợp lệ, việc gán có thể phát sinh `NullValueInNestedPathException` (thường gặp ở bean-property accessor) hoặc được bỏ qua nếu thiết lập cho phép bỏ qua invalid path. Không nên ghi cứng rằng mọi trường hợp đều sinh `FieldError` hoặc mọi trường hợp đều được im lặng bỏ qua.

Để thử rõ ràng mà không phụ thuộc vào MVC exception resolver, có thể dùng `BeanWrapperImpl` trực tiếp:

~~~java
CustomerForm customer = new CustomerForm();
BeanWrapperImpl wrapper = new BeanWrapperImpl(customer);
wrapper.setAutoGrowNestedPaths(false);
wrapper.setPropertyValue("address.city", "Hue");
~~~

Snippet này giả định import `org.springframework.beans.BeanWrapperImpl` cùng `CustomerForm`. Vì `customer.address` là null, đường dẫn không thể tiếp tục và thông thường phát sinh `NullValueInNestedPathException`. Đây là **mã minh họa tình huống lỗi**, không phải ví dụ độc lập phải chạy thành công.

### 6.2. Nested object đã được khởi tạo

Nếu không muốn auto-grow, hãy tạo nested object theo chủ đích:

~~~java
CustomerForm customer = new CustomerForm();
customer.setAddress(new Address());

DataBinder binder = new DataBinder(customer, "customerForm");
binder.setAutoGrowNestedPaths(false);

MutablePropertyValues values = new MutablePropertyValues();
values.add("address.city", "Hue");
binder.bind(values);
~~~

Đoạn này đặt trong dự án chứa `Address`, `CustomerForm` và import tương ứng; nó minh họa rằng **flag false không cấm binding nested field**. Nó chỉ không tự làm đầy trung gian đang null. Vì `address` đã được cấp phát, property binding có thể đi tới `city` bình thường.

### 6.3. Collection đã có đủ phần tử

Nếu target chứa sẵn một `List<Line>` với hai phần tử `Line` hợp lệ, thì `lines[1].sku` vẫn có thể được gán ngay cả khi auto-grow tắt; không cần cấp phát phần tử mới. Ngược lại, một list chỉ có index 0 sẽ không tự mở rộng để có index 1 khi tắt tính năng.

Bởi vậy câu “tắt auto-grow làm không thể bind nested path” là sai. Kết quả phụ thuộc **graph đã được khởi tạo tới đâu** trước khi binding.

## 7. Khi bật auto-grow mà Spring vẫn không thể khởi tạo

Đây là phần quan trọng nhất khi xử lý lỗi thực tế.

### 7.1. Thiếu constructor không tham số

~~~java
public class ImmutableAddress {
    private final String city;

    public ImmutableAddress(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }
}
~~~

Khi target `customer.immutableAddress == null`, binder không tự biết truyền tham số gì để tạo `ImmutableAddress` theo kiểu property auto-grow. Không nên “sửa” bằng cách thêm một constructor rỗng tạo object bất hợp lệ chỉ để làm request thành công.

Các hướng giải quyết phù hợp:

- **Khởi tạo có chủ đích** trong constructor/factory của form DTO.
- Dùng form DTO mutable có no-arg constructor phù hợp riêng cho property binding, sau đó chuyển thành domain object bất biến.
- Dùng **constructor binding** theo hợp đồng của phiên bản Spring/MVC, cho kiểu bất biến khi dữ liệu và constructor có thể được ánh xạ hợp lệ.
- Nếu cần một kiểu polymorphic, thiết kế rõ việc chọn implementation thay vì để binder đoán.

Không đánh đồng auto-grow với Spring IoC: `@Component`, `@Autowired` hoặc một bean cùng tên trong ApplicationContext không có nghĩa property accessor sẽ lấy bean đó để lấp vào một field đang null.

### 7.2. Kiểu abstract/interface

~~~java
public interface ShippingAddress {
    String getCity();
}
~~~

Nếu field `private ShippingAddress address;` còn null, không đủ thông tin để biết class nào phải tạo. Nếu đã có đối tượng implementation cụ thể trong field, Spring có thể đọc/ghi những property được accessor hỗ trợ, tùy chính class implementation. Thêm một implementation vào classpath không tự chọn được implementation ấy.

### 7.3. Thuộc tính read-only, final hoặc không theo JavaBeans

Ví dụ:

~~~java
public class ReadOnlyCustomer {
    private Address address;

    public Address getAddress() {
        return address;
    }
}
~~~

Nếu `address` null và dùng bean property access, Spring có thể xác định type nhưng không có setter để gắn object mới. Tên field giống nhau không bảo đảm Spring có quyền ghi nó. `initDirectFieldAccess()` có cơ chế khác nhưng không phải lời giải chung, đặc biệt với final field hoặc object bất biến.

### 7.4. Constructor ném exception

Lớp có constructor không tham số nhưng constructor tự ném lỗi hoặc thực hiện side effect nguy hiểm sẽ làm auto-grow thất bại. Constructor của DTO dùng trong binding nên nhẹ, rõ ràng và không phụ thuộc vào database/network hay trạng thái request bên ngoài.

### 7.5. Có thể tạo trung gian nhưng không thể gán field cuối

Spring có thể tạo `address` nhưng không gán được `address.zipCode` vì:

- thiếu setter/property writable;
- conversion của chuỗi sang kiểu field thất bại;
- setter kiểm tra bất biến và ném exception;
- field không nằm trong whitelist hoặc bị điều kiện declarative binding ngăn;
- nested collection/map có phần tử sai kiểu.

Đừng kết luận “autoGrowNestedPaths không hoạt động” chỉ vì field cuối chưa có giá trị. Cần kiểm tra object graph sau bind và `BindingResult` hoặc exception thực tế.

## 8. Tự mở rộng collection và autoGrowCollectionLimit

### 8.1. Các kiểu path thường gặp

| Path | Ý nghĩa | Khi nào cần auto-grow |
| --- | --- | --- |
| `address.city` | Đối tượng `address` có field `city` | Khi `address` đang null |
| `items[0].sku` | Field `sku` của phần tử đầu tiên trong list/array | Khi container hoặc element index 0 chưa tồn tại |
| `items[3].quantity` | Field trên phần tử index 3 | Khi list/array chưa có đủ phần tử |
| `settings[theme]` | Giá trị dưới key của map | Khi map/container cần tạo; map không hoạt động hoàn toàn giống list index |
| `items[1].address.city` | Nhiều cấp đi qua list và bean | Khi bất cứ trung gian nào còn null |
| `matrix[0][1]` | Phần tử trong container lồng nhau | Khi type metadata và cách tạo các cấp cho phép |

Spring hỗ trợ các dạng đường dẫn phổ biến, nhưng mức độ có thể auto-create phụ thuộc loại collection, generic element type, setter/accessor và phiên bản. Đừng suy ra mọi kiểu `Set` hoặc mọi cấu trúc map phức tạp đều có ngữ nghĩa truy cập theo index như `List`.

### 8.2. Giới hạn mặc định 256

`DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT` có giá trị **256** trong Spring 6.2. Mục đích là hạn chế việc một input như `items[999999].name` yêu cầu tạo số lượng phần tử quá lớn, gây tốn bộ nhớ.

~~~java
DataBinder binder = new DataBinder(orderForm);
binder.setAutoGrowCollectionLimit(16);
~~~

Đây là snippet; gọi trước khi binder được khởi tạo/bind. Giới hạn 16 có nghĩa quy tắc auto-grow của collection/array không tự mở rộng vượt vùng chỉ mục cho phép (thường các index 0–15). Nó **không phải** giới hạn tổng số field của HTTP request hay validation về số lượng item nghiệp vụ.

Ví dụ:

~~~text
Collection ban đầu: []
autoGrowCollectionLimit = 3

items[0].sku = "A"  -> có thể tạo phần tử index 0
items[1].sku = "B"  -> có thể mở rộng tới size 2
items[2].sku = "C"  -> có thể mở rộng tới size 3
items[3].sku = "D"  -> vượt giới hạn mở rộng đã chọn
~~~

Đây là minh họa cho list có type phần tử tạo được. Với giá trị index ngoài giới hạn, lỗi thực tế phụ thuộc property accessor và đường gọi; tránh hứa chắc HTTP status hay loại exception của MVC từ riêng cấu hình này.

Theo Javadoc `DataBinder` 6.2, giới hạn này áp dụng cho property/field injection qua `bind(PropertyValues)`, **không áp dụng cho constructor binding** qua `construct(...)`, và không dùng như một giới hạn chung cho map keys. Cần kiểm tra tài liệu đúng phiên bản nếu dự án dùng bản mới hơn vì cơ chế field injection có thể thay đổi. Không tăng giới hạn một cách tùy tiện để “fix” input bất thường.

### 8.3. Vì sao List<T> dễ auto-grow hơn List<?>?

Khi xử lý `lines[1].sku`, Spring phải biết phần tử thứ hai có class nào để gọi constructor rồi đi vào property `sku`. Với `List<Line>`, generic element type giúp xác định loại phần tử. Với raw `List`, `List<?>`, wildcard không đủ thông tin, interface/abstract element type hoặc element không có cách tạo phù hợp, quá trình này không bảo đảm thành công.

Đây cũng là lý do DTO nên mô tả loại phần tử rõ ràng:

~~~java
private List<Line> lines;
~~~

Thay vì cố lạm dụng:

~~~java
private List<Object> lines;
~~~

Nếu thiết kế yêu cầu các subtype khác nhau, hãy chủ động khởi tạo hoặc chuyển đổi đầu vào có kiểm soát, không cho client tự quyết định class cần instantiate bằng tên property.

### 8.4. Trường hợp map

Với `Map<String, Line> linesByCode`, Spring có thể tạo map container phù hợp khi giá trị map null và metadata cung cấp thông tin cần thiết. Tuy nhiên key `"ABC"` khác với một index số của list: thêm một key vào map không bắt buộc tạo các key trung gian. `autoGrowCollectionLimit` không phải cơ chế giới hạn số lượng keys của Map.

Điều này quan trọng cho bảo mật: không thể dựa vào collection limit để kiểm soát một form gửi hàng nghìn map keys. Hãy đặt giới hạn request, kiểm tra số lượng entry và giới hạn allowed fields theo bài toán.

## 9. autoGrowNestedPaths và constructor binding

Spring 6.1+ có API `DataBinder.construct(DataBinder.ValueResolver)` để xây object từ constructor/constructor parameters. Đây là con đường khác với `bind(PropertyValues)` vốn gán thuộc tính sau khi đã có target.

Javadoc của Spring 6.2 chỉ rõ `setAutoGrowNestedPaths` và `setAutoGrowCollectionLimit` phục vụ setter/field injection qua `bind(PropertyValues)`; **không áp dụng cho constructor binding** qua `construct(...)`.

So sánh:

| Khía cạnh | Property binding + auto-grow | Constructor binding |
| --- | --- | --- |
| Target | Thông thường đã có root object | Có thể tạo target mới từ constructor |
| Đường gán | Getter/setter hoặc field accessor | Constructor parameters được resolve |
| Nested null | Có thể tự tạo intermediate bean nếu đáp ứng điều kiện | Object graph được dựng bằng constructor/nested constructor binding theo quy tắc riêng |
| Mutable DTO | Thường phù hợp | Có thể dùng nhưng không bắt buộc |
| Immutable record/class | Không dễ đi theo setter auto-grow nếu chưa có target phù hợp | Có thể phù hợp hơn nếu constructor binding được cấu hình đúng |
| autoGrowNestedPaths | Có ảnh hưởng | Không phải cờ điều khiển cơ chế này |
| autoGrowCollectionLimit | Giới hạn tăng collection của property binding | Không phải giới hạn áp dụng chung ở đây |

Ví dụ:

~~~java
public record AddressInput(String city) {
}

public record CustomerInput(AddressInput address) {
}
~~~

Đó là mô hình immutable. Không nên lấy cờ `setAutoGrowNestedPaths(true)` làm cách yêu cầu Spring tạo `AddressInput` bằng constructor trong mọi tình huống. Nếu muốn bind vào record, cần xác nhận luồng constructor binding và tên parameters được hỗ trợ trong phiên bản MVC đang dùng. Tương tự, các validation annotations trên record là cơ chế kiểm tra riêng sau khi đối tượng được tạo theo điều kiện thích hợp.

## 10. Tương tác với WebDataBinder và Spring MVC

### 10.1. @InitBinder thiết lập theo phạm vi controller

Trong Spring MVC, `WebDataBinder` là nơi cấu hình binder cho từng request/attribute. Đoạn sau là code **tích hợp** trong controller, không phải chương trình Java độc lập:

~~~java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("customerForm")
public void initCustomerBinder(WebDataBinder binder) {
    binder.setAutoGrowNestedPaths(true);
    binder.setAutoGrowCollectionLimit(16);
    binder.setAllowedFields("name", "address.city", "address.postalCode");
}
~~~

Ở đây:

- `@InitBinder("customerForm")` nhắm tới binder có object name tương ứng.
- `setAutoGrowNestedPaths(true)` yêu cầu tự tạo property trung gian khi đáp ứng điều kiện.
- `setAutoGrowCollectionLimit(16)` giới hạn tự tăng kích thước array/list/collection theo cơ chế đã mô tả.
- `setAllowedFields(...)` giới hạn property paths được phép bind.

Đặt các thiết lập này trong `@InitBinder` để chúng chạy **trước khi Spring thực hiện binding**. Không gọi cấu hình sau khi controller đã nhận một `BindingResult` cho request hiện tại rồi mong dữ liệu đã bind được tính toán lại.

### 10.2. @ModelAttribute và field paths từ form

Giả sử DTO có `CustomerForm.address` đang null. Trong form HTML:

~~~html
<form method="post" action="/customers">
    <input name="name" value="Lan">
    <input name="address.city" value="Da Nang">
    <input name="address.postalCode" value="550000">
    <button type="submit">Lưu</button>
</form>
~~~

Với controller:

~~~java
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@PostMapping("/customers")
public String save(
        @ModelAttribute("customerForm") CustomerForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "customer/form";
    }
    return "redirect:/customers/success";
}
~~~

Đây là snippet trong class `@Controller` và cần có DTO, view engine, route đích cùng cấu hình MVC phù hợp. Spring dùng field names có dấu chấm để bind nested properties. Nếu auto-grow bật và `Address` khởi tạo được, controller có thể nhận `form.getAddress().getCity() == "Da Nang"`.

`BindingResult` cần đặt **ngay sau** tham số `@ModelAttribute` tương ứng nếu controller muốn đọc errors của object đó. Thất bại vì nested path không tồn tại có thể xảy ra trước khi đến controller hoặc bị xử lý theo cấu hình của binder; không cam kết mọi trường hợp đều vào `BindingResult`.

### 10.3. Bật/tắt toàn cục

Một số ứng dụng cấu hình `WebBindingInitializer`/`ConfigurableWebBindingInitializer` để áp dụng chính sách chung cho những binder được tạo ra. Việc này ảnh hưởng nhiều endpoint nên cần thử hồi quy sau thay đổi.

Không nên tạo bean `DataBinder` singleton rồi dùng chung cho mọi request; binder/result gắn với **target và lần binding cụ thể**. Đặt chính sách chung trong cấu hình MVC phù hợp, còn trạng thái request thuộc binder của request.

### 10.4. @RequestBody JSON là luồng khác

Khi controller nhận:

~~~java
@PostMapping("/customers/json")
public void create(@RequestBody CustomerForm input) {
    // ...
}
~~~

JSON được đọc qua `HttpMessageConverter` và JSON deserializer, thường là Jackson. Jackson có quy tắc riêng để dựng nested object; việc bật `WebDataBinder.setAutoGrowNestedPaths(true)` **không tự điều khiển cách Jackson deserialize JSON nested object**. Nếu JSON nested object bị lỗi, kiểm tra serializer/deserializer, constructor, record support và mapper configuration của phiên bản đang dùng.

Đây là một nguyên nhân phổ biến khiến lập trình viên thay auto-grow mà không thấy thay đổi trong JSON API. Cần phân biệt *form/query binding* và *body deserialization* trước khi sửa.

## 11. Các giới hạn về an toàn, hiệu năng và thiết kế dữ liệu

### 11.1. Đừng cho client tự xây object graph không giới hạn

Một request gửi những field names như:

~~~text
orders[99999].items[99999].sku=ATTACK
customer.internalRole=ADMIN
shippingAddress.owner.permissions[1]=WRITE
~~~

có thể ép binder đi sâu hoặc mở rộng graph ngoài dự kiến nếu các đường dẫn được phép. Default collection limit giảm một dạng rủi ro, nhưng **không bảo vệ tất cả rủi ro**: graph sâu có thể cấp phát nhiều object; map không có cùng ngữ nghĩa index limit; CPU/memory và độ dài field names còn chịu tác động từ request.

Biện pháp thực tế:

1. **Sử dụng form DTO riêng** chỉ chứa trường người dùng được phép nhập, thay vì bind trực tiếp vào entity domain có trường phân quyền, trạng thái thanh toán hoặc dữ liệu nội bộ.
2. **Giới hạn allowed fields** hoặc dùng declarative binding đúng phạm vi, tránh wildcard quá rộng trong các cấu trúc nested.
3. **Giữ collection limit phù hợp nghiệp vụ**; nếu màn hình chỉ cho tối đa 10 item thì không nên nâng limit lên hàng chục nghìn.
4. **Giới hạn request size/field count** ở tầng HTTP và kiểm tra kích thước collection/map sau bind theo quy tắc nghiệp vụ.
5. **Xem xét chiều sâu nested path** do bên ngoài điều khiển; với phiên bản/framework có hỗ trợ giới hạn độ sâu, đọc đúng API ở bản đang dùng thay vì tự đoán.
6. **Không coi auto-grow là validation**. Sau binding, vẫn cần ràng buộc dữ liệu và kiểm tra phân quyền.
7. **Tách domain invariant khỏi form initialization** để không tạo những thực thể bất biến trong trạng thái không hợp lệ chỉ cho mục đích binding.

### 11.2. Giới hạn auto-grow không đồng nghĩa giới hạn business

Ví dụ một form cho tối đa 5 dòng hàng:

~~~java
binder.setAutoGrowCollectionLimit(5);
~~~

Điều đó không tự kiểm tra người dùng gửi 5 hay ít hơn số lượng dòng hàng, không tự giới hạn map keys, không bảo đảm mọi line hợp lệ, và không thay thế `@Size(max = 5)` hay logic nghiệp vụ. Nếu có dữ liệu chứa sẵn hơn 5 phần tử, cấu hình auto-grow cũng không tự cắt bớt chúng.

### 11.3. Chi phí constructor và tác dụng phụ

Nested DTO nên có constructor đơn giản. Nếu constructor tự đăng ký event, truy cập database hay tạo resource lớn, một request có nhiều nested paths có thể gây hàng loạt side effects khi binder cố tự sinh object. Đây là dấu hiệu thiết kế không phù hợp: tách class nhận dữ liệu và domain service xử lý nghiệp vụ.

## 12. Chẩn đoán khi nested property không được tạo

Nên kiểm tra theo một trình tự có thể lặp lại:

**Bước 1: Xác nhận loại đầu vào.** Request là form/query qua `@ModelAttribute`, một binder gọi thủ công, hay JSON `@RequestBody`? Chọn đúng tầng cần debug.

**Bước 2: Ghi đường dẫn thực tế.** Ví dụ `address.city` khác `customer.address.city`. Với binder có root object `customer`, key dữ liệu thường là `address.city`, không lặp lại object name ở đầu path.

**Bước 3: Kiểm tra flag và thời điểm cấu hình.** `binder.isAutoGrowNestedPaths()` là gì? Có thiết lập `setAutoGrowNestedPaths(false)` ở `@InitBinder` hoặc initializer không? Flag có được gọi trước khi binding bắt đầu không?

**Bước 4: Kiểm tra graph trước bind.** `getAddress()` đang null hay đã có instance? Nếu đã có, auto-grow không phải nguyên nhân chính của lỗi ghi field cuối.

**Bước 5: Kiểm tra class và property descriptors.** Kiểu field có cụ thể không? Có constructor không tham số phù hợp? Có setter/property writable cho trung gian và field cuối? Có record/immutable type cần constructor binding không?

**Bước 6: Nếu có chỉ mục, kiểm tra collection.** Index có vượt `autoGrowCollectionLimit` không? List element type có xác định không? Đây là List/array hay Map? Đừng áp dụng giới hạn List cho Map.

**Bước 7: Kiểm tra whitelist và binding mode.** `setAllowedFields`, `setDisallowedFields`, `setDeclarativeBinding` có chặn path không? Với `BindingResult.getSuppressedFields()`, tìm các field bị từ chối, nhưng hiểu rằng suppressed field **không tự động thành FieldError**.

**Bước 8: Phân biệt exception và errors.** `NullValueInNestedPathException`, `NotWritablePropertyException`, conversion error và `FieldError` báo các nguyên nhân khác nhau; đọc root cause và field path thật trước khi đưa ra cách sửa.

**Bước 9: Thử tối thiểu.** Tạo một DTO với đúng kiểu field và một `DataBinder` độc lập; bind một path duy nhất. Nếu thử nghiệm này hoạt động, nguyên nhân có thể thuộc cấu hình MVC/controller hoặc DTO thực tế.

**Bước 10: Xác nhận phiên bản.** Javadoc Spring 6.2 nêu rõ phạm vi flag với property/field injection và constructor binding. Các bản trước hoặc mới hơn có thể khác về chi tiết accessor; chốt dependency đã resolve thay vì chỉ đọc docs “current”.

Bảng triệu chứng:

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh/sửa |
| --- | --- | --- |
| `address` vẫn null sau bind | Auto-grow tắt, field bị suppress, path sai hoặc binder không nhận input | Kiểm tra flag, `getSuppressedFields()` và request keys |
| `NullValueInNestedPathException` | Một đoạn path null, không thể/không được auto-grow | Kiểm tra null trung gian, constructor, setter |
| Không thể instantiate nested class | Không có constructor không tham số phù hợp, type abstract/interface, constructor lỗi | Khởi tạo chủ động, DTO mutable hoặc constructor binding phù hợp |
| `lines[1].sku` không bind | Collection limit, list element type không rõ, element không tạo được | Xem generic type, limit và index |
| `address.zipCode` bị typeMismatch | Đã vào được path nhưng parse giá trị thất bại | Kiểm tra conversion/formatter và `BindingResult` |
| Field nested không có trong object | Getter/setter thiếu hoặc property name sai | Xem JavaBeans descriptors, tên field |
| DTO được tạo nhưng validation fail | Binding thành công không có nghĩa dữ liệu hợp lệ | Đọc constraint violations/`FieldError` |
| Thay flag mà JSON không đổi | Jackson, không phải `WebDataBinder`, tạo nested object | Kiểm tra JSON deserializer và kiểu request |
| Tăng collection limit vẫn lỗi | Lỗi constructor, path, security, type, nested depth hoặc field whitelist | Phân tích từng trung gian, không tăng limit tiếp |

## 13. Kiểm thử hồi quy nên có

Một test tốt phải phân biệt “Spring có tạo nested object” với “dữ liệu được gán đúng” và “đầu vào được chấp nhận”.

| Ca | Trạng thái đầu | Auto-grow | Kết quả mong đợi cần xác minh |
| --- | --- | --- | --- |
| Bean mutable với no-arg constructor | `address=null` | Bật | `address` được tạo, `city` được gán |
| Cùng bean | `address=null` | Tắt | Không tạo `address`; lỗi hoặc ignore theo cấu hình |
| Nested object đã tạo sẵn | `address=new Address()` | Tắt | Vẫn có thể bind `address.city` |
| Nested immutable thiếu no-arg | `address=null` | Bật | Không giả định tạo thành công; kiểm tra exception |
| Field trung gian read-only | `address=null` | Bật | Không mặc nhiên gắn được instance mới |
| List có generic element class | `lines=null`, bind index 1 | Bật | Kiểm tra container, size 2 và phần tử mục tiêu |
| Index lớn hơn giới hạn | List rỗng, bind index 200 với limit 3 | Bật | Không tự nới tới index 200 |
| List sẵn hai phần tử | Bind index 1 | Tắt | Vẫn bind được nếu element và field ghi được |
| Path ngoài whitelist | `role.permissions[0]` | Bật | Không gán field trái phép |
| Nested field sai kiểu | `address.zipCode="abc"`, đích là `Integer` | Bật | Đối tượng trung gian có thể được tạo nhưng có lỗi conversion |
| `@RequestBody` JSON | JSON có nested object | Bật/tắt WebDataBinder | Không quy kết cơ chế deserialize JSON cho flag này |
| DTO bất biến | Constructor binding | Bật/tắt flag | Kiểm tra riêng con đường tạo object qua constructor |

### 13.1. Gợi ý test DataBinder

Với JUnit 5 trong ứng dụng đã có dependencies Spring và test, cách assert trọng tâm:

~~~java
@Test
void growsNullAddress() {
    CustomerForm form = new CustomerForm();
    DataBinder binder = new DataBinder(form);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("address.city", "Hue");

    binder.bind(values);

    assertNotNull(form.getAddress());
    assertEquals("Hue", form.getAddress().getCity());
    assertFalse(binder.getBindingResult().hasErrors());
}
~~~

Đoạn này là **một test method tích hợp**, cần import `org.junit.jupiter.api.Test`, static `Assertions.*`, `DataBinder`, `MutablePropertyValues` và có DTO từ ví dụ. Không phải file Java chạy độc lập. Test này chứng minh auto-grow thành công với một kiểu cụ thể; nếu thay DTO thành record hoặc class thiếu no-arg, kết quả phải được đánh giá lại.

### 13.2. Một phép thử để chứng minh ranh giới

Ngoài test mặc định, thêm test khi flag tắt với `Address` null, rồi test có `Address` khởi tạo trước. Dùng `assertThrows` chỉ khi đã kiểm tra loại exception thật của API/version đang gọi; đừng copy assertion exception từ `BeanWrapperImpl` sang một MVC test và mặc định mọi exception resolver giống nhau.

Với collection, thử index gần giới hạn và index vượt giới hạn. Đừng chỉ test một request rất lớn trong môi trường chạy thật khi chưa đặt giới hạn tài nguyên phù hợp; có thể dùng giới hạn nhỏ như 3 để tái hiện an toàn.

## 14. Các hiểu nhầm thường gặp

**“Bật auto-grow thì Spring tạo được mọi class.”** Không. Nó cần kiểu xác định, cách khởi tạo hợp lệ, nơi gắn instance và đường ghi field cuối.

**“Có constructor có tham số là đủ.”** Không đối với property auto-grow kiểu JavaBean phổ biến. Spring không tự suy ra đối số constructor cho một nested property null theo con đường này.

**“Tắt auto-grow là cấm nested binding.”** Không. Một nested object đã tồn tại vẫn có thể được truy cập và gán field bên trong.

**“BeanWrapper và DataBinder có cùng giá trị mặc định.”** Không. `BeanWrapperImpl` dùng trực tiếp mặc định false, `DataBinder` tiêu chuẩn mặc định true theo Javadoc tương ứng.

**“Collection limit là số lượng phần tử tối đa của form.”** Không. Nó chỉ giới hạn hành vi tự mở rộng các collection/array liên quan trong con đường binding hỗ trợ; business validation phải xử lý số lượng hợp lệ.

**“Không tạo được nested bean thì chắc là thiếu Converter.”** Không hẳn. Cần phân biệt thiếu instance ở đường trung gian với thiếu conversion cho field cuối.

**“Auto-grow xử lý JSON nested object trong @RequestBody.”** Không. JSON deserialization thuộc message converter/JSON mapper.

**“Đổi auto-grow sau khi bind sẽ sửa kết quả trước đó.”** Không. Config phải được áp dụng trước lần binding; thay đổi config không replay request và có thể bị binder từ chối.

**“Một field được phép bind thì mọi field lồng trong nó đều hợp lệ.”** Không. Nên kiểm soát chính xác các property paths được nhận và chạy validation/phân quyền nghiệp vụ riêng.

**“Spring tạo object nghĩa là đã kiểm tra tính hợp lệ.”** Không. Auto-grow chỉ giải quyết cấu trúc graph; Bean Validation và nghiệp vụ phải kiểm tra trạng thái tiếp theo.

**“Cứ tăng autoGrowCollectionLimit thật lớn để hết lỗi.”** Không. Có thể làm tăng nguy cơ cấp phát bộ nhớ và không giải quyết lỗi constructor/property hoặc map keys.

**“Lỗi nested path luôn nằm trong BindingResult.”** Không. Tùy nguyên nhân và setter/accessor, có lỗi phát sinh dưới dạng exception; cần đọc stack trace và cấu hình `ignoreInvalidFields` khi áp dụng.

## 15. Checklist áp dụng trong dự án thật

Trước khi dùng `autoGrowNestedPaths` cho một form có đường dẫn sâu, hãy trả lời:

1. Input là `@ModelAttribute`/form/query hay `@RequestBody` JSON?
2. Đường dẫn property được gửi chính xác là gì? Có bao gồm nhầm tên root object ở đầu không?
3. `DataBinder`/`WebDataBinder` đã được cấu hình auto-grow trước khi bind chưa?
4. Nested type là concrete class khởi tạo được, có no-arg constructor phù hợp, hay là interface/abstract/record?
5. Có getter/setter hoặc field access phù hợp để gắn intermediate object không?
6. Nếu target đã có object, tại sao vẫn cần auto-grow?
7. Với `List<T>`, generic element type có rõ và type có thể instantiate không?
8. Index input có nằm trong `autoGrowCollectionLimit` đã chọn không?
9. Có field whitelist, DTO riêng, giới hạn request và business validation đúng yêu cầu không?
10. Có kiểm tra đồng thời `BindingResult`, suppressed fields, object graph sau bind và exception root cause không?
11. Đã thử cả nested null, nested preinitialized, flag on/off, conversion fail và index vượt limit chưa?
12. Đã đối chiếu với Javadoc đúng phiên bản Spring Framework mà ứng dụng đang chạy chưa?

## 16. Tài liệu gốc

- [Spring Framework 6.2 – DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html) — `setAutoGrowNestedPaths`, `setAutoGrowCollectionLimit`, mặc định và phạm vi.
- [Spring Framework 6.2 – BeanWrapper Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/BeanWrapper.html) — API truy cập thuộc tính, nested property paths.
- [Spring Framework 6.2 – BeanWrapperImpl Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/BeanWrapperImpl.html) — accessor JavaBeans và cấu hình.
- [Spring Framework – BeanWrapper and property editors](https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html) — cơ chế truy cập và chuyển kiểu thuộc tính.
- [Spring Framework – Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html) — binding các property paths.
- [Spring Framework – Spring MVC @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html) — cấu hình binder trong controller.
- [Spring Framework – Spring MVC @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html) — mô hình argument binding.
- [Spring Framework – Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html) — tổng quan.

**Điều cần ghi nhớ:** `autoGrowNestedPaths=true` cho phép binder tạo **đối tượng trung gian đang null** và mở rộng collection khi Spring đủ khả năng xác định, khởi tạo và gắn đối tượng đó. Khi thiếu constructor phù hợp, property không ghi được, kiểu trừu tượng, generic không rõ hoặc index vượt giới hạn, auto-grow không thể “tự sửa” cấu trúc. Dùng đúng DTO, cấu hình sớm, giới hạn field và collection, rồi kiểm tra cả object graph lẫn lỗi binding để chẩn đoán chính xác.
