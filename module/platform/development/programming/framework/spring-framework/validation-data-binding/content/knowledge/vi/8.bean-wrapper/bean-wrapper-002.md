# BeanWrapperImpl và đối tượng đang được bọc trong Spring Framework

## 1. BeanWrapperImpl là gì?

Trong Spring Framework, `BeanWrapper` là interface để truy cập, đọc và ghi các **JavaBean properties** bằng tên thay vì gọi trực tiếp từng getter/setter trong mã nguồn. `BeanWrapperImpl` là implementation mặc định của interface này, nằm trong package `org.springframework.beans`.

Một `BeanWrapperImpl` bao quanh (**wrap**) một object Java cụ thể và làm việc với các property của object đó. Từ góc nhìn lập trình viên:

```text
        BeanWrapperImpl (cơ chế truy cập metadata/property)
                     |
         giữ tham chiếu tới object
                     |
                     v
            Person (JavaBean)
            ├── name: String
            ├── age: Integer
            └── address: Address
                      └── city: String
```

Ví dụ:

```java
Person person = new Person();
BeanWrapperImpl wrapper = new BeanWrapperImpl(person);

wrapper.setPropertyValue("name", "Lan");
Object value = wrapper.getPropertyValue("name");
```

Trong đoạn minh họa trên, `person` phải là một class có setter/getter phù hợp; wrapper dùng property name `"name"` để tương tác với **cùng object `person`**. `value` nhận `"Lan"` nếu property hoạt động bình thường.

Đối tượng đang được bọc (wrapped object, target object) chính là instance được truyền vào constructor hoặc gắn bằng `setWrappedInstance(...)`. Nó không phải bản sao, DTO mới, proxy AOP hay một bean được Spring IoC tự động tạo chỉ vì ta gọi `new BeanWrapperImpl(person)`.

### Bốn ý quan trọng

1. **Wrapper có trạng thái đích:** mỗi wrapper đang tham chiếu tới một object nhất định; có thể đổi target khi cần.
2. **Đọc/ghi làm việc trên object đích:** khi gọi `setPropertyValue(...)`, thuộc tính của instance thực sự thay đổi qua cơ chế JavaBean.
3. **Wrapper dùng metadata của class:** tên property, kiểu dữ liệu, khả năng đọc/ghi và cách chuyển kiểu được suy ra từ JavaBeans introspection, không chỉ từ tên field `private`.
4. **Wrapper là công cụ hạ tầng:** `DataBinder` và các cơ chế tạo/cấu hình bean của Spring thường sử dụng nó gián tiếp; ứng dụng bình thường không nhất thiết cần thao tác trực tiếp.

## 2. Quan hệ giữa interface và implementation

`BeanWrapper` thuộc `org.springframework.beans` và mở rộng các khả năng của `ConfigurablePropertyAccessor`: truy cập property, chuyển kiểu, kiểm tra metadata và đăng ký bộ chuyển đổi khi cần.

`BeanWrapperImpl` kế thừa `AbstractNestablePropertyAccessor` và triển khai `BeanWrapper`. Một phần API thực tế:

| API | Ý nghĩa |
| --- | --- |
| `new BeanWrapperImpl(object)` | Tạo wrapper bao quanh instance có sẵn |
| `new BeanWrapperImpl(SomeClass.class)` | Tạo một instance của class và bọc nó |
| `new BeanWrapperImpl()` | Tạo wrapper chưa có target; cần thiết lập target trước khi truy cập |
| `getWrappedInstance()` | Trả về chính object mà wrapper đang bọc |
| `getWrappedClass()` | Trả về `Class<?>` của object được bọc |
| `setWrappedInstance(other)` | Đổi target sang instance khác |
| `getPropertyValue("name")` | Đọc giá trị property |
| `setPropertyValue("name", value)` | Ghi giá trị property |
| `isReadableProperty("name")` | Property có đọc qua accessor được không |
| `isWritableProperty("name")` | Property có ghi qua accessor được không |
| `getPropertyDescriptor("name")` | Lấy metadata JavaBeans `PropertyDescriptor` |
| `getPropertyDescriptors()` | Lấy tất cả mô tả property của bean |
| `setAutoGrowNestedPaths(true)` | Bật cơ chế tự tạo nested path trong các điều kiện hỗ trợ |
| `setConversionService(service)` | Gắn `ConversionService` để phục vụ chuyển kiểu |
| `registerCustomEditor(...)` | Gắn custom `PropertyEditor` theo kiểu/property |

**Phân biệt “wrapper” và “wrapped instance”:** biến kiểu `BeanWrapperImpl` giữ các thao tác/phần cấu hình truy cập; `getWrappedInstance()` lấy object Java nghiệp vụ. Người dùng có thể giữ một reference tới object này và nhìn thấy các thay đổi của nó sau khi wrapper gọi setter.

`BeanWrapperImpl` không phải giao diện validation: nó không có `BindingResult` hay `Errors` để tích lũy lỗi tự động giống `DataBinder`. Lỗi property access trực tiếp thường được phát sinh bằng exception.

## 3. Ba cách tạo wrapper và vòng đời target

### Cách A: bọc object đã tồn tại

```java
Person person = new Person();
BeanWrapperImpl wrapper = new BeanWrapperImpl(person);

boolean same = wrapper.getWrappedInstance() == person; // true
```

Toán tử `==` ở đây kiểm tra **cùng tham chiếu**, không phải `equals()`. Wrapper **không clone** `person`. Nếu mã bên ngoài thay đổi `person`, wrapper sẽ đọc được giá trị mới; nếu wrapper đổi `person.name`, biến `person` bên ngoài cũng nhìn thấy.

### Cách B: nhờ wrapper khởi tạo object từ `Class`

```java
BeanWrapperImpl wrapper = new BeanWrapperImpl(Person.class);
Person created = (Person) wrapper.getWrappedInstance();
```

Constructor nhận `Class<?>` cố tạo một instance của class rồi wrap instance đó. Class cần có khả năng được khởi tạo theo cơ chế của Spring (trong ví dụ sử dụng public no-arg constructor). Trường hợp class trừu tượng, không có constructor phù hợp hoặc constructor ném lỗi có thể khiến khởi tạo thất bại.

Đối tượng được tạo từ `Class` **không tự động trở thành Spring bean trong `ApplicationContext`** và không tự động nhận dependency injection, lifecycle callbacks, proxy giao dịch hoặc cấu hình service. Đây là thao tác khởi tạo và truy cập property ở mức hạ tầng.

### Cách C: tạo wrapper rỗng rồi đặt target

```java
BeanWrapperImpl wrapper = new BeanWrapperImpl();
wrapper.setWrappedInstance(new Person());
```

Wrapper rỗng chưa có wrapped instance để đọc/ghi; gọi các thao tác cần target trước khi gán target có thể gây exception. Cách A ngắn gọn và dễ kiểm soát hơn nếu object đã có sẵn.

### Vòng đời đơn giản

```text
new BeanWrapperImpl(first)
  -> wrapper.getWrappedInstance() == first
  -> wrapper.setPropertyValue("name", "Lan")
  -> first.name trở thành "Lan"
  -> wrapper.setWrappedInstance(second)
  -> wrapper.getWrappedInstance() == second
  -> thao tác tiếp theo tác động đến second
  -> first vẫn giữ tên "Lan"
```

Việc đổi target **không copy** giá trị từ object cũ sang object mới. Nếu hai wrapper cùng trỏ tới một instance mutable, chúng có thể nhìn thấy cùng thay đổi; điều đó không làm wrapper trở thành cơ chế đồng bộ hóa đa luồng.

## 4. Ví dụ Java 17+ chạy được: xem object gốc thay đổi

Ví dụ này chạy dạng ứng dụng Java thuần dùng thư viện Spring Beans, **không cần Spring Boot hay web server**. Nó thể hiện tham chiếu object, đọc/ghi property, nested property, chuyển kiểu và thay wrapped instance.

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>beanwrapper-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-beans</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/example/BeanWrapperDemo.java`:

```java
package example;

import org.springframework.beans.BeanWrapperImpl;

public class BeanWrapperDemo {

    public static class Address {
        private String city;

        public Address() {}

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public static class Person {
        private String name;
        private Integer age;
        private Address address = new Address();

        public Person() {}

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public static void main(String[] args) {
        Person first = new Person();
        BeanWrapperImpl wrapper = new BeanWrapperImpl(first);

        System.out.println("sameReference="
                + (wrapper.getWrappedInstance() == first));
        System.out.println("wrappedClass="
                + wrapper.getWrappedClass().getSimpleName());
        System.out.println("writableAge="
                + wrapper.isWritableProperty("age"));

        wrapper.setPropertyValue("name", "Lan");
        wrapper.setPropertyValue("age", "28");
        wrapper.setPropertyValue("address.city", "Hue");

        System.out.println("first=" + first.getName()
                + "/" + first.getAge()
                + "/" + first.getAddress().getCity());
        System.out.println("cityViaWrapper="
                + wrapper.getPropertyValue("address.city"));

        Person second = new Person();
        second.setName("Mai");

        wrapper.setWrappedInstance(second);
        System.out.println("changedReference="
                + (wrapper.getWrappedInstance() == second));
        System.out.println("newName="
                + wrapper.getPropertyValue("name"));

        wrapper.setPropertyValue("name", "An");
        System.out.println("secondName=" + second.getName());
        System.out.println("oldName=" + first.getName());
    }
}
```

Chạy trong thư mục chứa `pom.xml`, với Java 17+ và Maven:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=example.BeanWrapperDemo
```

Phần stdout từ `main` (bỏ qua các log do Maven/plugin tạo):

```text
sameReference=true
wrappedClass=Person
writableAge=true
first=Lan/28/Hue
cityViaWrapper=Hue
changedReference=true
newName=Mai
secondName=An
oldName=Lan
```

**Giải thích theo từng quan sát:**

1. `sameReference=true` xác minh wrapper giữ **đúng reference tới `first`**.
2. `getWrappedClass().getSimpleName()` trả `Person`, vì target là instance `Person`.
3. Property `age` có setter `setAge(Integer)` nên ghi được. Spring chuyển chuỗi `"28"` thành `Integer 28` qua cơ chế conversion/property editor trước khi gọi setter.
4. `address.city` là đường dẫn lồng nhau; `first.address` đã được khởi tạo nên wrapper có thể tìm và gọi `Address.setCity(...)`.
5. `setWrappedInstance(second)` đổi target. Từ thời điểm đó, gọi `getPropertyValue("name")` trả tên của `second` và lời gọi `setPropertyValue("name", "An")` thay đổi `second`.
6. `oldName=Lan` cho thấy instance `first` không bị thay thế hay chép dữ liệu khi wrapper chuyển sang `second`.

Các class `Person` và `Address` trong ví dụ có getter/setter JavaBeans đầy đủ. Nếu viết field `private String name` nhưng không có setter, `BeanWrapperImpl` ở chế độ JavaBean mặc định không thể ghi property này qua `setPropertyValue("name", ...)`.

## 5. JavaBean property khác với Java field như thế nào?

`BeanWrapperImpl` được xây dựng trên quy ước **JavaBeans**, nơi property được xác định chủ yếu qua phương thức accessor và metadata introspection:

```java
public class Account {
    private String label;

    public String getLabel() { return label; }
    public void setLabel(String label) { this.label = label; }
}
```

Với class này:

- `getLabel()` làm property `label` **readable**.
- `setLabel(String)` làm `label` **writable**.
- Field `label` là chi tiết lưu trữ nội bộ; wrapper không tự động thực hiện direct-field reflection.
- Property chỉ có getter là **read-only** theo góc nhìn BeanWrapper; chỉ có setter là **write-only** (nếu JavaBeans introspection nhận diện được).

Cách kiểm tra trước khi truy cập:

```java
BeanWrapperImpl wrapper = new BeanWrapperImpl(new Account());

if (wrapper.isWritableProperty("label")) {
    wrapper.setPropertyValue("label", "Ready");
}

if (wrapper.isReadableProperty("label")) {
    System.out.println(wrapper.getPropertyValue("label"));
}
```

Đoạn trên cần đặt trong method có class `Account`; output sau khi gán là:

```text
Ready
```

**Không suy ra property name từ field name một cách máy móc.** Ví dụ JavaBean có thể tạo property từ cặp `getEnabled()/setEnabled(...)` dù backing field mang tên khác. Với boolean, getter dạng `isEnabled()` cũng có thể được JavaBeans nhận diện.

### Tra cứu metadata

```java
import java.beans.PropertyDescriptor;
import org.springframework.beans.BeanWrapperImpl;

BeanWrapperImpl wrapper = new BeanWrapperImpl(new Account());
PropertyDescriptor descriptor =
        wrapper.getPropertyDescriptor("label");

System.out.println(descriptor.getName());
System.out.println(descriptor.getPropertyType().getSimpleName());
```

Đây là snippet bên trong method của class có `Account`; stdout:

```text
label
String
```

`getPropertyDescriptor(...)` trả mô tả kiểu JavaBeans, bao gồm `getReadMethod()` và `getWriteMethod()` khi hiện diện. Nếu property không tồn tại, Spring có thể ném `InvalidPropertyException`; có thể gọi `isReadableProperty`/`isWritableProperty` để kiểm tra phù hợp, nhưng vẫn phải xử lý lỗi khi object có thể đổi trạng thái giữa kiểm tra và thao tác.

**Record và DTO immutable:** Java `record` có accessor dạng `name()`, không có JavaBean setter, nên không thích hợp làm object mutable để `BeanWrapperImpl.setPropertyValue(...)` gán trường. Với immutable input, hãy cân nhắc constructor binding trong `DataBinder`/`@ModelAttribute`; không dùng BeanWrapper như cơ chế tạo bản sao rồi sửa record.

## 6. Các kiểu thao tác với wrapped object

| Thao tác | Hệ quả đối với target |
| --- | --- |
| `getWrappedInstance()` | Lấy reference hiện tại, không clone |
| `getWrappedClass()` | Lấy runtime class của target hiện tại |
| `getPropertyValue("name")` | Đọc bằng accessor |
| `setPropertyValue("name", "Lan")` | Ghi lên target hiện tại qua setter |
| `setPropertyValues(...)` | Thử ghi một nhóm property, theo quy tắc xử lý lỗi của accessor |
| `setWrappedInstance(newTarget)` | Đổi target; thao tác kế tiếp hướng sang target mới |
| `new BeanWrapperImpl(Target.class)` | Tạo target mới, không tự đưa vào IoC container |

Có hai mức “đổi” cần phân biệt:

- **Đổi giá trị property:** `wrapper.setPropertyValue("name", ...)` — wrapper vẫn bọc **cùng object**, chỉ state của object thay đổi.
- **Đổi wrapped instance:** `wrapper.setWrappedInstance(second)` — wrapper chuyển sang **object khác**. Target cũ vẫn sống nếu còn reference bên ngoài; nó không bị xóa hay tự đồng bộ.

Nếu `target` là một Spring bean đã quản lý bởi container, wrapper có thể đọc/ghi properties của instance được đưa vào. Tuy nhiên việc tự ghi các property trong runtime **không tự tạo lại lifecycle**, không chắc tái áp dụng toàn bộ `@ConfigurationProperties` binding, bean post-processors hay dependency injection.

## 7. Nested properties: đi từ bean cha tới bean con

BeanWrapper hỗ trợ đường dẫn dạng:

| Đường dẫn | Ý nghĩa |
| --- | --- |
| `name` | Property đơn giản |
| `address.city` | Property `city` trên bean `address` |
| `items[0].price` | `price` của phần tử index `0` trong `items` |
| `attributes[region]` | Giá trị ứng với map key `"region"` |
| `matrix[1][2]` | Truy cập cấu trúc nhiều chiều nếu kiểu và accessor hỗ trợ |

Ví dụ `wrapper.setPropertyValue("address.city", "Hue")` yêu cầu wrapper tìm `address` trong object gốc, sau đó truy cập property `city` của object con. Trong ví dụ runnable, `address` đã được tạo ở field initializer, nên không gặp lỗi null nested path.

### Khi nested object là `null`

Nếu `person.getAddress() == null` mà code ghi:

```java
wrapper.setPropertyValue("address.city", "Hue");
```

với wrapper thuần ở cấu hình mặc định không auto-grow, Spring thường ném `NullValueInNestedPathException`. Có thể bật:

```java
wrapper.setAutoGrowNestedPaths(true);
wrapper.setPropertyValue("address.city", "Hue");
```

Khi được bật, Spring cố tự tạo các object trung gian nếu kiểu dữ liệu có thể khởi tạo, property có đường ghi và cấu hình cho phép. Đừng giả định mọi interface, abstract type, constructor tùy ý hoặc collection sẽ tự khởi tạo thành công. Với collection/array, có thể dùng `setAutoGrowCollectionLimit(int)` để tránh mở rộng vô hạn theo chỉ số do client cung cấp.

**Lưu ý khác biệt theo ngữ cảnh:** cấu hình auto-grow trong `DataBinder` có mặc định/giới hạn riêng theo bản Spring, không nên lấy hành vi của một `DataBinder` đã cấu hình để suy ra hành vi của một `BeanWrapperImpl` mới. Nếu nested path bắt buộc có mặt, khởi tạo rõ ràng ở DTO có thể dễ dự đoán hơn bật auto-grow.

### Khi property có index hoặc map key

`items[0].price` chỉ hoạt động khi `items` thực sự là danh sách/mảng và phần tử đó có kiểu truy cập được. Lỗi có thể phát sinh nếu collection chưa được khởi tạo, index vượt phạm vi hoặc object phần tử không có property writable. Tên đường dẫn phải được xử lý như **dữ liệu đầu vào không đáng tin cậy** nếu đến từ request.

## 8. Chuyển kiểu trước khi gọi setter

`BeanWrapperImpl` không nhất thiết nhận vào đúng kiểu Java của setter. Nó có khả năng chuyển từ kiểu nguồn sang kiểu đích qua bộ chuyển đổi được cấu hình và các default JavaBeans `PropertyEditor`.

Ví dụ:

```java
// Person.age là Integer, setter là setAge(Integer).
wrapper.setPropertyValue("age", "28");
// getPropertyValue("age") sau đó nhận Integer 28.
```

Dù giá trị đầu vào là `String`, wrapper có thể chuyển thành `Integer` rồi gọi setter. Nếu nhập `"abc"` và không có converter phù hợp, Spring có thể ném `TypeMismatchException` hoặc exception liên quan conversion/property access.

### Tích hợp ConversionService

Có thể cung cấp `ConversionService` rõ ràng cho wrapper khi cần hệ thống chuyển kiểu mở rộng:

```java
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.core.convert.support.DefaultConversionService;

// Snippet bên trong method, có biến person kiểu Person:
BeanWrapperImpl wrapper = new BeanWrapperImpl(person);
wrapper.setConversionService(new DefaultConversionService());
wrapper.setPropertyValue("age", "31");
```

`DefaultConversionService` cung cấp những converter phổ biến. Formatter cho ngày/giờ theo `@DateTimeFormat` thường cần `FormattingConversionService` và cấu hình phù hợp; không giả định một `BeanWrapperImpl` Java thuần sẽ tự nhận toàn bộ annotation formatter của Spring MVC.

Một lựa chọn JavaBeans truyền thống là đăng ký custom editor:

```java
wrapper.registerCustomEditor(
        java.time.LocalDate.class,
        new java.beans.PropertyEditorSupport() {
            @Override
            public void setAsText(String text) {
                setValue(java.time.LocalDate.parse(text));
            }
        });
```

Snippet này dành cho wrapper đã tạo; khi property đích có kiểu `LocalDate`, editor trên có thể parse chuỗi ISO như `2026-11-02`. Cần xử lý ngoại lệ format cho input không hợp lệ theo contract ứng dụng. Trong mã mới, `ConversionService` thường dễ mở rộng/kiểm thử hơn so với editor có trạng thái.

**Chuyển kiểu không phải validation.** `age=-5` có thể chuyển thành Integer thành công nhưng vẫn không hợp lệ theo quy tắc nghiệp vụ; `BeanWrapperImpl` không tự chạy Jakarta Bean Validation `@Min`/`@NotNull` khi gọi setter. Để gom lỗi và chạy validation, dùng `DataBinder`, `Validator` hoặc cơ chế tương ứng của Spring MVC.

## 9. BeanWrapperImpl, DataBinder và Spring IoC: mỗi thứ phụ trách gì?

| Tiêu chí | `BeanWrapperImpl` | `DataBinder` | `BeanFactory` / Spring IoC |
| --- | --- | --- | --- |
| Mục đích chính | Đọc/ghi JavaBean property theo tên | Bind dữ liệu từ `PropertyValues`, quản lý lỗi/validation | Tạo và quản lý lifecycle/dependencies của Spring beans |
| Wrapped/target object | Object đang được bọc | Target được bind (thường dùng property access hoặc constructor binding) | Bean do container quản lý |
| Chuyển kiểu | Có cơ chế conversion/editor | Có, qua binding infrastructure | Có khi cấu hình properties |
| Lỗi | Thường ném exception trực tiếp | Tập hợp lỗi trong `BindingResult` khi phù hợp | Lỗi tạo/cấu hình bean qua exception của container |
| Validation tự động | Không | Có nếu được cấu hình/chạy validator | Tùy cấu hình và tích hợp |
| Allowed fields cho request | Không phải whitelist request binder | Có `setAllowedFields(...)` | Không phải chức năng bind request |

Ví dụ `DataBinder` trong một method (đã có `person` với getter/setter như ví dụ):

```java
import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

DataBinder binder = new DataBinder(person, "person");
binder.setAllowedFields("name", "age");
binder.bind(new MutablePropertyValues(
        Map.of("name", "Lan", "age", "28")));

if (binder.getBindingResult().hasErrors()) {
    // Xử lý lỗi chuyển kiểu/binding.
}
```

`DataBinder` sử dụng cơ chế truy cập property của Spring và có thêm lớp quản lý lỗi, allowed fields và validation. `BeanWrapperImpl` là công cụ thấp hơn để trực tiếp truy cập JavaBean object; nó không đồng nghĩa với `DataBinder`, và cũng không phải `BeanFactory`.

Với REST JSON body, `HttpMessageConverter` (thường Jackson) đảm nhận deserialization vào DTO; không nên mô tả `BeanWrapperImpl` như bộ chuyển JSON mặc định của Spring MVC.

### BeanWrapperImpl có tạo Spring bean không?

`new BeanWrapperImpl(Person.class)` là khởi tạo object qua helper, **không** có nghĩa `Person` được đăng ký vào `ApplicationContext`. Muốn một object được IoC quản lý, tạo/đăng ký bean thông qua cấu hình container phù hợp. Ngược lại, Spring có thể dùng cơ chế BeanWrapper **bên trong** quá trình cấu hình bean, nhưng điều đó không biến một wrapper do ứng dụng tự tạo thành Spring bean.

## 10. Lỗi thường gặp khi thao tác với target

| Tình huống | Dấu hiệu/exception thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Property không tồn tại | `NotWritablePropertyException` khi ghi, `NotReadablePropertyException` khi đọc | Kiểm tra tên property, getter/setter và kiểu method |
| Property tồn tại nhưng chỉ đọc | `NotWritablePropertyException` | Không có setter hợp lệ; dùng constructor binding hoặc setter rõ ràng |
| Chuỗi không chuyển được về kiểu đích | `TypeMismatchException` | Kiểm tra converter/editor và dữ liệu đầu vào |
| Property lồng nhau có object cha `null` | `NullValueInNestedPathException` | Khởi tạo bean con hoặc bật auto-grow khi thích hợp |
| Dùng index vượt phạm vi | `InvalidPropertyException` hoặc exception liên quan index | Kiểm tra list/array và giới hạn auto-grow |
| Target chưa được gán | Exception do wrapper chưa có object | Gọi constructor nhận object hoặc `setWrappedInstance(...)` |
| Đổi target rồi tưởng wrapper vẫn ghi target cũ | Object cũ không nhận cập nhật mới | Kiểm tra reference `getWrappedInstance() == expected` |
| Class đích không khởi tạo được từ `Class` | `BeansException`/constructor-related exception | Dùng instance đã tạo hoặc class có constructor tương thích |
| Custom converter chưa được đăng ký | Conversion không hỗ trợ định dạng mong muốn | Gắn `ConversionService`/`PropertyEditor` phù hợp |
| Thử ghi trực tiếp `private field` không setter | Property không writable | Dùng JavaBean setter hoặc cơ chế direct-field riêng |

Các exception cụ thể phụ thuộc kiểu thao tác và phiên bản/configuration của Spring; ví dụ trên là các trường hợp phổ biến, không phải lời hứa về loại exception cho mọi mô hình object.

### Bắt lỗi ở mức gọi trực tiếp

```java
import org.springframework.beans.BeansException;
import org.springframework.beans.BeanWrapperImpl;

// Trong method có object Person hợp lệ:
BeanWrapperImpl wrapper = new BeanWrapperImpl(person);

try {
    wrapper.setPropertyValue("age", "not-a-number");
} catch (BeansException ex) {
    // Báo lỗi dữ liệu hoặc dùng DataBinder để tạo BindingResult.
    System.out.println(ex.getClass().getSimpleName());
}
```

Đoạn trên cần đặt trong method hợp lệ. Với property `age` kiểu `Integer` và cấu hình chuyển kiểu mặc định, exception thường là `TypeMismatchException`; không lấy tên exception in ra làm output cố định trong mọi trường hợp. Nếu xử lý nhiều trường từ form, dùng `DataBinder` giúp tổng hợp field errors tốt hơn so với bắt từng exception từ BeanWrapper.

## 11. Kiểm tra target và khả năng đọc/ghi trước khi thao tác

Nếu code xử lý tên property một cách động, kiểm tra metadata giúp giảm lỗi:

```java
import java.util.Set;
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;

// Ví dụ chạy trong method với biến target có JavaBean setters.
BeanWrapper accessor = new BeanWrapperImpl(target);
Set<String> allowed = Set.of("name", "age");

String propertyName = "name";
Object value = "Lan";

if (allowed.contains(propertyName)
        && accessor.isWritableProperty(propertyName)) {
    accessor.setPropertyValue(propertyName, value);
}
```

Đây là một đoạn **minh họa**, cần object `target` có các property tương ứng. Đối với input không đáng tin cậy, whitelist `allowed` là lớp bảo vệ quan trọng; riêng `isWritableProperty(...)` **chỉ** cho biết khả năng ghi theo API, không xác nhận khách hàng có quyền ghi property đó.

Nếu xử lý form/request, tiếp tục áp dụng Bean Validation và authorization trong service. Các trường như `role`, `admin`, `approved`, `balance` có thể là property writable của object nghiệp vụ nhưng không phải dữ liệu client được phép điều chỉnh.

**Tránh mass assignment:** Không đưa trực tiếp mọi key từ request vào vòng lặp `wrapper.setPropertyValue(key, request.get(key))` trên entity chứa thuộc tính nhạy cảm. Hãy dùng DTO chuyên biệt, danh sách trường được phép, hoặc `DataBinder#setAllowedFields(...)` khi có dữ liệu từ bên ngoài.

## 12. Cấu hình nested path và tác động lên object graph

Khi wrapper ghi property lồng nhau, thay đổi có thể chạm tới các object con đã tồn tại, ví dụ:

```text
Person first
  address ────────> Address(city="Hanoi")

wrapper.setPropertyValue("address.city", "Hue")

Person first
  address ────────> Address(city="Hue")
```

**Address object có thể vẫn là cùng instance**, chỉ property `city` được sửa. Nếu mã khác cũng giữ reference tới `Address` đó, nó thấy giá trị mới. Đây là hậu quả tự nhiên của shared mutable object graph; không phải cơ chế event-sourcing hay unit-of-work.

Nếu muốn tránh side effect, hãy chủ động tạo/copy cấu trúc dữ liệu trước khi wrap hoặc dùng DTO bất biến với constructor phù hợp. `BeanWrapperImpl` không cung cấp deep copy hay undo. Đối với object phụ thuộc transaction/database, thay đổi JavaBean trong bộ nhớ cũng **không tự đồng nghĩa** đã persist xuống database; persistence context/transaction vẫn quyết định lưu trữ.

## 13. Một số chi tiết nâng cao về target và introspection

### Reflection được dùng ở đâu?

Spring sử dụng JavaBeans introspection và cơ chế gọi accessor để làm việc với property. Nó có thể cache metadata theo class để giảm chi phí dò getter/setter lặp lại. Tuy nhiên, **metadata được cache không đồng nghĩa wrapper tự đồng bộ trạng thái giữa hai object**. `getWrappedInstance()` vẫn biểu thị target hiện tại.

### Khi target là subclass/proxy

`getWrappedClass()` trả runtime class của object được bọc. Nếu target thực sự là một proxy/subclass, runtime class có thể là lớp proxy thay vì class domain gốc. Việc property có truy cập được hay không còn tùy proxy, public accessor, visibility và cách proxy chuyển tiếp method. Đừng luôn dùng `getWrappedClass().getSimpleName()` làm định danh nghiệp vụ ổn định.

### Khi target được thay bằng một class khác

Khi `setWrappedInstance(other)` nhận object có class khác, wrapper cần cập nhật thông tin truy cập/introspection cho target mới. Các property name và type trước đó không còn được đảm bảo tồn tại; ví dụ wrapper đang bọc `Person` có property `age` rồi chuyển sang `Product` không có `age` sẽ khiến thao tác cũ thất bại.

**Không cache `PropertyDescriptor` rồi áp dụng tùy tiện cho class target khác.** Descriptor là metadata gắn với class/property phù hợp, không phải lệnh chung cho mọi object.

### Nhiều thread cùng dùng wrapper?

`BeanWrapperImpl` chứa mutable state: reference đích, cấu hình conversion/editor, nested accessors. Đừng share một wrapper mutable làm singleton xử lý song song request. Tạo wrapper theo phạm vi công việc hoặc đồng bộ hóa/thiết kế ownership rõ ràng nếu buộc phải dùng chung.

Ngay cả khi dùng hai wrapper khác nhau cùng bọc một target, **target mutable** vẫn có thể bị race condition khi nhiều thread sửa nó; việc wrapper tách biệt không bảo vệ object bên dưới.

## 14. Bài tập kiểm chứng và câu hỏi thường gặp

### Bài tập A — Cùng object hay copy?

Giả sử:

```java
Person first = new Person();
BeanWrapperImpl wrapper = new BeanWrapperImpl(first);
wrapper.setPropertyValue("name", "Mai");
System.out.println(first.getName());
```

Với class `Person` có setter/getter như phần 4, output:

```text
Mai
```

Vì wrapper đang ghi vào instance `first`, không tạo bản sao.

### Bài tập B — Sau khi đổi target?

```java
Person first = new Person();
Person second = new Person();

BeanWrapperImpl wrapper = new BeanWrapperImpl(first);
wrapper.setPropertyValue("name", "Lan");
wrapper.setWrappedInstance(second);
wrapper.setPropertyValue("name", "An");

System.out.println(first.getName());
System.out.println(second.getName());
```

Output:

```text
Lan
An
```

Mỗi lời gọi ghi lên **target tại thời điểm gọi**.

### Bài tập C — Readable không đồng nghĩa writable

Với DTO chỉ có `getId()` mà không có `setId(...)`, `isReadableProperty("id")` có thể là `true` còn `isWritableProperty("id")` là `false`. Không dùng BeanWrapper để bypass chính sách immutable bằng cách thay đổi field `private`.

### Checklist debug

1. Kiểm tra `wrapper.getWrappedInstance() == expectedObject` trước/sau thay target.
2. Kiểm tra `wrapper.getWrappedClass()` có đúng runtime class mong đợi.
3. Kiểm tra `isReadableProperty(...)` và `isWritableProperty(...)` trước thao tác động.
4. Nếu ghi nested path lỗi, xem từng bean trung gian có `null` không; đánh giá có nên bật auto-grow không.
5. Nếu conversion lỗi, kiểm tra kiểu setter, editor/conversion service và giá trị nguồn.
6. Nếu giá trị không cập nhật như mong đợi, kiểm tra wrapper đã đổi target, object graph có chia sẻ reference và setter có side effect không.
7. Nếu xử lý input request, kiểm tra whitelist/DTO, validation, quyền ghi và giới hạn chỉ số collection.
8. Nếu chạy nhiều thread, kiểm tra ownership của cả wrapper và wrapped object.

## 15. Kết luận trọng tâm

`BeanWrapperImpl` là bộ điều khiển truy cập **JavaBean properties**; **wrapped object** là instance Java thật mà bộ điều khiển hiện đang thao tác. Constructor nhận object giữ reference đến object ấy; `getWrappedInstance()` trả reference; `setPropertyValue(...)` thường làm thay đổi chính instance; và `setWrappedInstance(...)` chuyển wrapper sang instance khác mà không copy dữ liệu. Từ hiểu biết này, có thể giải thích đúng việc đọc/ghi property, nested path, chuyển kiểu, side effect và vai trò của BeanWrapper bên dưới `DataBinder` hay Spring IoC.

## Tài liệu tham khảo

- [Spring Framework — Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework API — BeanWrapper](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanWrapper.html)
- [Spring Framework API — BeanWrapperImpl](https://docs.spring.io/spring-framework/docs/6.1.20/javadoc-api/org/springframework/beans/BeanWrapperImpl.html)
- [Spring Framework API — AbstractNestablePropertyAccessor](https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/beans/AbstractNestablePropertyAccessor.html)
- [Spring Framework API — DataBinder](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework API — PropertyAccessor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/PropertyAccessor.html)
