# PropertyAccessorFactory: truy cập theo JavaBean hoặc trực tiếp vào field trong Spring Framework

**`PropertyAccessorFactory`** thuộc package `org.springframework.beans` của Spring Framework. Đây là factory đơn giản để tạo một đối tượng **property accessor** bao quanh object Java đã có, cho phép đọc/ghi thuộc tính theo tên. API này cung cấp hai lựa chọn then chốt:

- `PropertyAccessorFactory.forBeanPropertyAccess(target)`: trả về `BeanWrapper` và truy cập theo quy ước **JavaBeans** (getter/setter).
- `PropertyAccessorFactory.forDirectFieldAccess(target)`: trả về `ConfigurablePropertyAccessor` và truy cập **field của object trực tiếp** (thông thường qua reflection), bỏ qua getter/setter.

Cả hai đều làm việc **trên cùng instance được truyền vào**, hỗ trợ các thao tác thuộc tính có tên và khả năng chuyển đổi kiểu. Chúng khác nhau ở cách xác định tính đọc/ghi của property, vị trí thực thi logic của getter/setter, và những ràng buộc có thể bị bỏ qua nếu dùng field access.

Bài viết dành cho Java 17+ và Spring Framework 6.x; ví dụ đầy đủ sử dụng Maven và Spring 6.2.14. Đây là kiến thức hạ tầng của `BeanWrapper` và data binding, không yêu cầu khởi động một ứng dụng Spring Boot.

## 1. Factory giải quyết vấn đề gì?

Cho một object Java:

```java
public class Customer {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name == null ? null : name.strip();
    }
}
```

Thông thường code Java gọi `customer.setName(" Lan ")`. Nhưng các thành phần như mapping dữ liệu, form binding, cấu hình bean hoặc công cụ động thường chỉ biết tên thuộc tính ở runtime, ví dụ chuỗi `"name"`. Một `PropertyAccessor` có thể thực hiện:

```java
accessor.setPropertyValue("name", " Lan ");
Object current = accessor.getPropertyValue("name");
```

Đây là hai câu lệnh **minh họa** cho biến `accessor` đã được tạo; chưa phải chương trình độc lập.

Factory giúp caller không phải biết hoặc tự tạo các implementation cụ thể như `BeanWrapperImpl` và `DirectFieldAccessor`. Việc chọn **hình thức truy cập** thể hiện ý định: muốn Spring tôn trọng giao diện JavaBeans, hay muốn thao tác trên các field thực tế của object.

Factory không tạo bản sao của target, không đăng ký target làm Spring bean, không đưa object vào `ApplicationContext`, không tự chạy validation và không tự bảo vệ các property khỏi dữ liệu không tin cậy.

## 2. API chuẩn và kiểu trả về

Hai phương thức tĩnh:

```java
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.ConfigurablePropertyAccessor;
import org.springframework.beans.PropertyAccessorFactory;

BeanWrapper bean =
    PropertyAccessorFactory.forBeanPropertyAccess(target);

ConfigurablePropertyAccessor fields =
    PropertyAccessorFactory.forDirectFieldAccess(target);
```

Đây là fragment, cần có biến `target` là một object Java không-null. Tên class và chữ ký có ý nghĩa:

| Phương thức | Kiểu trả về khai báo | Hình thức truy cập | Implementation thường gặp |
| --- | --- | --- | --- |
| `forBeanPropertyAccess(Object target)` | `BeanWrapper` | JavaBeans property thông qua getter/setter hợp lệ | `BeanWrapperImpl` |
| `forDirectFieldAccess(Object target)` | `ConfigurablePropertyAccessor` | Field instance trực tiếp, có thể bao gồm field `private` khi reflection được phép | `DirectFieldAccessor` |

Quan hệ interface:

```text
PropertyAccessor
  └── ConfigurablePropertyAccessor
        └── BeanWrapper

Implementations tiêu biểu:
  BeanWrapperImpl  -> BeanWrapper
  DirectFieldAccessor -> ConfigurablePropertyAccessor
```

`BeanWrapper` bổ sung các khả năng introspection JavaBeans như `getPropertyDescriptors()`. Kết quả của `forDirectFieldAccess` chỉ được khai báo theo interface `ConfigurablePropertyAccessor`, nên **không thể gọi trực tiếp** API chỉ thuộc `BeanWrapper` như `getPropertyDescriptors()` trên biến `fields`.

Cả hai cùng hỗ trợ `getPropertyValue(...)`, `setPropertyValue(...)`, `isReadableProperty(...)`, `isWritableProperty(...)`, `getPropertyType(...)`, đăng ký custom editor, gán `ConversionService` và cấu hình xử lý đường dẫn lồng nhau.

### 2.1. `PropertyAccessor` ở đây khác gì `PropertyAccessor` của SpEL?

Có hai API cùng tên nhưng không cùng chức năng:

- `org.springframework.beans.PropertyAccessor`: giao diện thao tác property theo chuỗi đường dẫn; `PropertyAccessorFactory` dùng giao diện này.
- `org.springframework.expression.PropertyAccessor`: chiến lược đọc/ghi property của **Spring Expression Language (SpEL)** khi đánh giá biểu thức.

Không import nhầm lớp SpEL khi viết code `PropertyAccessorFactory`. Tên API giống nhau không có nghĩa các interface hoán đổi cho nhau.

## 3. `forBeanPropertyAccess`: truy cập theo JavaBeans

Với `BeanWrapper`, Spring xác định property từ các phương thức JavaBeans thông qua introspection. Trong trường hợp thông thường:

- `getName()` là getter của property `name`.
- `isActive()` có thể làm getter cho boolean property `active`.
- `setName(String value)` là setter của `name`.
- Object có thể có property chỉ đọc (getter, không có setter) hoặc chỉ ghi (setter, không có getter) tùy cấu trúc method.
- Getter/setter có thể thực thi logic, ví dụ chuẩn hóa chuỗi, cập nhật trạng thái nội bộ hoặc kiểm soát điều kiện.

Ví dụ:

```java
Customer customer = new Customer();
BeanWrapper wrapper =
    PropertyAccessorFactory.forBeanPropertyAccess(customer);

wrapper.setPropertyValue("name", "  Lan  ");
System.out.println(wrapper.getPropertyValue("name"));
```

Với class `Customer` trong phần 1, output là:

```text
Lan
```

Vì `setPropertyValue` đi qua `setName`, logic `strip()` chạy trước khi object lưu giá trị. Đây là điểm khác biệt rất quan trọng nếu setter áp dụng một bất biến nghiệp vụ.

Spring có thể xem một phương thức getter là JavaBeans property ngay cả khi **không có field mang tên đó**. Ví dụ `getFullName()` có thể ghép `firstName` và `lastName`; property `fullName` sẽ đọc được qua `BeanWrapper` nhưng không nhất thiết ghi được nếu thiếu `setFullName(...)`.

### 3.1. BeanWrapper hỗ trợ introspection

`BeanWrapper` có API như:

```java
wrapper.isReadableProperty("name");
wrapper.isWritableProperty("name");
wrapper.getPropertyType("name");
wrapper.getPropertyDescriptor("name");
wrapper.getPropertyDescriptors();
```

Từ đó, chương trình động có thể xác định property nào được phép đọc/ghi và kiểu dữ liệu của chúng. `getPropertyDescriptor` hay `getPropertyDescriptors` liên quan JavaBeans introspection, nên đây là khả năng chỉ có ở nhánh `BeanWrapper` trong hai kiểu trả về của factory.

Không kết luận rằng tồn tại field `private String name` thì `BeanWrapper` luôn ghi được `name`. Nếu class không có setter được JavaBeans introspection chấp nhận, thường `isWritableProperty("name")` là `false` dù field thực sự tồn tại.

## 4. `forDirectFieldAccess`: truy cập field thực tế

`DirectFieldAccessor` truy cập field của object bằng reflection thay vì gọi setter/getter. Một class như sau vẫn có thể được cập nhật field dù thiếu setter:

```java
public class FieldOnly {
    private String token;

    public String viewToken() {
        return token;
    }
}
```

Một đoạn tích hợp:

```java
FieldOnly obj = new FieldOnly();

ConfigurablePropertyAccessor direct =
    PropertyAccessorFactory.forDirectFieldAccess(obj);

direct.setPropertyValue("token", "OK");
System.out.println(obj.viewToken());
```

Output:

```text
OK
```

Trong cùng thiết kế, `BeanWrapper` **không có JavaBeans setter `setToken`** để ghi property `token`. Việc `token` là `private` không ngăn hoàn toàn direct field access khi runtime cho phép reflective access; ngược lại, nó cũng **không** có nghĩa client nên được phép chỉnh field ấy.

### 4.1. Setter logic không chạy

Giả sử một field `name` có setter:

```java
public void setName(String name) {
    this.name = name.strip();
}
```

Nếu gọi `forBeanPropertyAccess` rồi `setPropertyValue("name", "  Lan  ")`, setter chuẩn hóa thành `"Lan"`. Nếu gọi `forDirectFieldAccess` và gán cùng chuỗi, field giữ nguyên `"  Lan  "` vì setter không được gọi.

Điều này có thể được dùng có chủ đích trong một công cụ migration nội bộ, nhưng cũng có thể phá vỡ invariant của object. Với mã xử lý nghiệp vụ hoặc HTTP input, nên cân nhắc nhận dữ liệu vào DTO riêng, validation và gán thông qua API nghiệp vụ.

### 4.2. Direct field access có những giới hạn nào?

- Cần **field thực** để giải quyết tên. Một computed JavaBeans property chỉ có getter mà không có backing field tương ứng sẽ không tự trở thành field cho `DirectFieldAccessor`.
- Phải có quyền reflective access ở runtime. Khi dùng Java Platform Module System (JPMS) với package không được mở cho reflection, việc truy cập field không công khai có thể thất bại. Không coi reflective access là cách mặc nhiên vượt mọi giới hạn module.
- Không dựa vào direct field access để thay đổi `final` field, record component hoặc dữ liệu bất biến. Việc thay đổi chúng có thể không được hỗ trợ hoặc có hậu quả không xác định trong thiết kế object.
- Direct field access có thể đi qua field thừa kế và các đường dẫn lồng nhau nếu truy cập được; nhưng đừng suy luận có thể cập nhật mọi loại object, proxy hay cấu trúc đặc biệt.
- Reflection bỏ qua logic setter/getter và có thể làm mất các hành vi dựa vào method call. Các quy tắc validation/business không tự chạy.

## 5. Bảng so sánh hai cách truy cập

| Khía cạnh | Bean property access | Direct field access |
| --- | --- | --- |
| Cách gọi | `forBeanPropertyAccess(obj)` | `forDirectFieldAccess(obj)` |
| Kiểu trả về | `BeanWrapper` | `ConfigurablePropertyAccessor` |
| Cách xác định property | Getter/setter theo JavaBeans | Field thực trong class |
| Ghi `name` | Qua `setName(...)` | Ghi trực tiếp vào field `name` |
| Đọc `name` | Qua `getName()` | Đọc trực tiếp field `name` |
| Không có setter | Property thường không ghi được | Vẫn có thể ghi nếu có field phù hợp và reflection cho phép |
| Setter có chuẩn hóa/kiểm tra | Logic setter được gọi | Logic setter bị bỏ qua |
| Computed property không có field | Có thể đọc qua getter | Không có field tương ứng để đọc |
| Nested path `address.city` | Hỗ trợ | Hỗ trợ |
| Indexed/Map path | Hỗ trợ khi kiểu/structure phù hợp | Hỗ trợ khi kiểu/structure phù hợp |
| Chuyển đổi kiểu | Có `PropertyEditor`/`ConversionService` | Có `PropertyEditor`/`ConversionService` |
| Introspection đặc thù JavaBeans | `getPropertyDescriptor(s)` | Không phải API của kiểu trả về trực tiếp |
| Dùng trong `DataBinder` | Chế độ mặc định | Chọn bằng `initDirectFieldAccess()` trước khi bind |

Có thể dùng một biến kiểu `ConfigurablePropertyAccessor` cho cả hai vì `BeanWrapper` kế thừa nó. Nếu cần introspection riêng của BeanWrapper, giữ biến khai báo `BeanWrapper`.

## 6. Ví dụ Java 17 chạy được: cùng input, hai kết quả khác nhau

Ví dụ đầy đủ này kiểm chứng bốn vấn đề:

1. Bean access gọi setter nên loại bỏ khoảng trắng.
2. Direct field access giữ nguyên chuỗi và không tăng bộ đếm setter.
3. Hai accessor đều chuyển chuỗi `"21"` thành `int` nhờ cùng một `ConversionService`.
4. Một field `private` không có setter vẫn cập nhật được qua direct accessor, còn BeanWrapper báo không ghi được.

### 6.1. Tạo project Maven

```text
property-accessor-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── AccessorDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>property-accessor-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-beans</artifactId>
      <version>6.2.14</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
        <configuration>
          <mainClass>example.AccessorDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

File `src/main/java/example/AccessorDemo.java`:

```java
package example;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.ConfigurablePropertyAccessor;
import org.springframework.beans.PropertyAccessorFactory;
import org.springframework.core.convert.support.DefaultConversionService;

public class AccessorDemo {

    public static class Address {
        private String city;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public static class Person {
        private String name;
        private int age;
        private int setterCalls;
        private Address address = new Address();

        public String getName() {
            return name;
        }

        public void setName(String name) {
            setterCalls++;
            this.name = name.strip();
        }

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            this.age = age;
        }

        public int getSetterCalls() {
            return setterCalls;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public static class FieldOnly {
        private String secret;

        public String showSecret() {
            return secret;
        }
    }

    public static void main(String[] args) {
        DefaultConversionService converters =
            new DefaultConversionService();

        Person beanPerson = new Person();
        BeanWrapper bean =
            PropertyAccessorFactory.forBeanPropertyAccess(beanPerson);
        bean.setConversionService(converters);

        bean.setPropertyValue("name", "  Lan  ");
        bean.setPropertyValue("age", "21");
        bean.setPropertyValue("address.city", "Ha Noi");

        System.out.println(
            "bean: name=[" + beanPerson.getName()
                + "] age=" + beanPerson.getAge()
                + " city=" + beanPerson.getAddress().getCity()
                + " setterCalls=" + beanPerson.getSetterCalls()
        );

        Person fieldPerson = new Person();
        ConfigurablePropertyAccessor direct =
            PropertyAccessorFactory.forDirectFieldAccess(fieldPerson);
        direct.setConversionService(converters);

        direct.setPropertyValue("name", "  Lan  ");
        direct.setPropertyValue("age", "21");
        direct.setPropertyValue("address.city", "Da Nang");

        System.out.println(
            "field: name=[" + fieldPerson.getName()
                + "] age=" + fieldPerson.getAge()
                + " city=" + fieldPerson.getAddress().getCity()
                + " setterCalls=" + fieldPerson.getSetterCalls()
        );

        FieldOnly fieldOnly = new FieldOnly();
        PropertyAccessorFactory.forDirectFieldAccess(fieldOnly)
            .setPropertyValue("secret", "OK");

        BeanWrapper beanView =
            PropertyAccessorFactory.forBeanPropertyAccess(fieldOnly);

        System.out.println("field-only: secret=" + fieldOnly.showSecret());
        System.out.println(
            "bean-secret-writable="
                + beanView.isWritableProperty("secret")
        );
        System.out.println(
            "bean-age-type=" + bean.getPropertyType("age").getSimpleName()
        );
    }
}
```

Giải thích thiết kế:

- `Person` có getter/setter chuẩn. Setter `setName` gọi `strip()` và tăng `setterCalls`.
- `Address` được khởi tạo trước, vì vậy đường dẫn lồng nhau `address.city` có sẵn; ví dụ không phụ thuộc cấu hình tự tạo nested object.
- Hai accessor cùng dùng `DefaultConversionService` để chuyển chuỗi `"21"` thành `int 21`.
- `FieldOnly` có field `secret` nhưng không có `getSecret`/`setSecret`, nên `BeanWrapper` không coi `secret` là writable JavaBeans property.
- Mọi nested class là `public static` trong một public class duy nhất, vì thế có thể biên dịch trong một file đúng tên `AccessorDemo.java`.

Chạy ở thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

`stdout` dự kiến:

```text
bean: name=[Lan] age=21 city=Ha Noi setterCalls=1
field: name=[  Lan  ] age=21 city=Da Nang setterCalls=0
field-only: secret=OK
bean-secret-writable=false
bean-age-type=int
```

Dòng thứ hai có **hai dấu cách ở đầu và hai dấu cách ở cuối** bên trong `[...]`, cho thấy direct field access không chạy `strip()`. `age=21` chứng minh conversion cho cả hai chế độ. Khi chạy Maven lần đầu, thông báo tải dependency/plugin (nếu có) nằm ngoài các dòng stdout nghiệp vụ này.

Nếu sửa demo thành `direct.setPropertyValue("age", "not-a-number")`, việc chuyển kiểu sẽ thất bại và ném exception liên quan conversion/property access. Không kỳ vọng plain accessor tự trả một `BindingResult` chứa field error; việc gom lỗi dạng đó thuộc cơ chế `DataBinder`.

## 7. Đọc, ghi và kiểm tra type bằng API chung

Các thao tác phổ biến kế thừa từ `PropertyAccessor`:

```java
accessor.isReadableProperty("name");
accessor.isWritableProperty("name");
accessor.getPropertyValue("name");
accessor.setPropertyValue("name", "Mai");
accessor.getPropertyType("name");
accessor.getPropertyTypeDescriptor("name");
```

Đây là fragment với biến `accessor` kiểu `ConfigurablePropertyAccessor`. Dùng `isReadableProperty`/`isWritableProperty` khi phải xử lý tên trường động, nhưng chúng chỉ nói **property có thể đọc/ghi qua accessor này**, không xác nhận quyền nghiệp vụ của user.

Ví dụ logic chương trình tự viết có thể tránh gọi nhầm một property không tồn tại:

```java
if (!accessor.isWritableProperty(propertyName)) {
    throw new IllegalArgumentException(
        "Không thể ghi property: " + propertyName
    );
}
accessor.setPropertyValue(propertyName, value);
```

Đoạn trên là **minh họa**, cần biến `propertyName` và `value` được định nghĩa; không chuyển toàn bộ chuỗi property name do HTTP client cung cấp trực tiếp vào accessor. Nếu cần whitelist, kiểm tra `propertyName` có trong tập đường dẫn được định nghĩa trước; riêng `isWritableProperty` chưa tạo ra ranh giới bảo mật.

Các phương thức bulk, ví dụ `setPropertyValues(...)`, cũng có ở cả hai kiểu accessor. Nếu dùng dữ liệu có khả năng chứa property không hợp lệ, nên quyết định rõ chính sách bỏ qua hay báo lỗi, và bắt những exception thích hợp theo contract của Spring.

## 8. Đường dẫn lồng nhau, List và Map

Cả `BeanWrapperImpl` và `DirectFieldAccessor` hiện đại hỗ trợ nested paths, indexed collections và Map, với điều kiện object graph tương thích và kiểu dữ liệu có thể đọc/ghi.

| Đường dẫn | Ý nghĩa |
| --- | --- |
| `address.city` | Trường `city` bên trong object `address` |
| `items[0].name` | Tên của phần tử đầu tiên trong List/array |
| `tags[2]` | Phần tử thứ ba của List/array |
| `attributes[theme]` | Entry theo khóa `"theme"` trong Map |
| `details[SKU-1].quantity` | Property của object nằm trong Map |

Một nested path như `address.city` được giải quyết **theo cùng chiến lược** qua các tầng: bean accessor dựa vào getters/setters; direct field accessor truy cập field. Ví dụ mục 6 dùng chính `address.city` cho cả hai.

Cần phân biệt “đã hỗ trợ cú pháp path” với “mọi graph luôn cập nhật được”. Nếu `address == null`, nếu field là bất biến, nếu collection không tồn tại hoặc nếu phần tử không có cách khởi tạo phù hợp, thao tác có thể lỗi.

### 8.1. `setAutoGrowNestedPaths` và giá trị mặc định

`ConfigurablePropertyAccessor` hỗ trợ:

```java
accessor.setAutoGrowNestedPaths(true);
```

Khi được bật và điều kiện cho phép, accessor có thể tạo một object con mặc định khi gặp `null` trong nested path. **Với plain accessor tạo từ `PropertyAccessorFactory`, giá trị mặc định là `false`**. Do đó đừng giả định `address.city` tự chạy nếu `address` đang null. Ví dụ mục 6 chủ động `new Address()` để tránh phụ thuộc cơ chế auto-grow.

Giới hạn và hành vi khi tự tăng collection, nested object có thể khác giữa `BeanWrapper`, `DirectFieldAccessor` và `DataBinder`. Không nhầm mặc định của plain property accessor với mặc định của `DataBinder`: DataBinder ở chế độ bean property thường bật auto-grow nested paths, nhưng việc auto-grow này không được hỗ trợ giống nhau ở chế độ direct field của DataBinder.

Khi nhận dữ liệu từ client, đừng bật auto-grow chỉ để làm biến mất lỗi. Cần giới hạn index/size và kiểm tra đồ thị dữ liệu; index như `items[999999]` có thể gây áp lực tài nguyên nếu hệ thống xử lý thiếu giới hạn.

### 8.2. Chuyển đổi kiểu và generic metadata

Hai accessor đều có khả năng tích hợp:

```java
accessor.setConversionService(conversionService);
accessor.registerCustomEditor(TargetType.class, editor);
```

Đây là **minh họa API**, cần `conversionService`, `TargetType` và `editor` thực tế. Dùng `ConversionService` để hỗ trợ chuyển kiểu phổ biến, formatter/editor khi cần. Một chuỗi `"21"` có thể chuyển sang `int`; với kiểu tự định nghĩa, cần converter/editor phù hợp.

Khi đi vào `List<Item>` hoặc `Map<String, Item>`, generic metadata giúp xác định kiểu element hoặc key/value. Việc hỗ trợ đường dẫn và metadata không đồng nghĩa tự động tạo mọi phần tử hoặc chấp nhận mọi kiểu input; phải kiểm thử DTO thực tế.

## 9. Mối liên hệ với `DataBinder` và Spring MVC

`PropertyAccessorFactory` là API **thấp hơn** `DataBinder`. Nó tạo accessor để đọc/ghi giá trị, trong khi `DataBinder` điều phối một luồng input binding có cấu hình field, conversion, lỗi, và validation.

Mặc định, `DataBinder` dùng **bean property access**. Nếu muốn binder truy cập trực tiếp field, có API:

```java
DataBinder binder = new DataBinder(target, "form");
binder.initDirectFieldAccess();
binder.setAllowedFields("city", "postalCode");
binder.bind(new MutablePropertyValues(inputValues));
BindingResult result = binder.getBindingResult();
```

Đây là fragment **không chạy độc lập**: cần `target`, `inputValues` và các import:
`org.springframework.validation.DataBinder`,
`org.springframework.beans.MutablePropertyValues`,
`org.springframework.validation.BindingResult`.

Gọi `initDirectFieldAccess()` **trước khi binder bắt đầu truy cập/ghi dữ liệu**. API này đổi chế độ của `DataBinder`; nó không đồng nghĩa với việc tự tạo `PropertyAccessorFactory.forDirectFieldAccess(target)` rồi mong binder tự dùng accessor khác.

Trong Spring MVC, có thể cấu hình binding mode cho một model attribute tại `@InitBinder`:

```java
@InitBinder("profileForm")
void setupBinder(WebDataBinder binder) {
    binder.initDirectFieldAccess();
    binder.setAllowedFields("displayName", "city");
}
```

Đây là **đoạn code tích hợp trong controller**, cần `WebDataBinder` và annotation `@InitBinder`. Khi cấu hình direct access cho dữ liệu HTTP, phải xem xét cẩn thận vì các setter kiểm tra dữ liệu và chuẩn hóa giá trị bị bỏ qua.

**Không lẫn với constructor binding:** Spring MVC có thể tạo target qua constructor trước khi property binding. `forBeanPropertyAccess`/`forDirectFieldAccess` nói về cách đọc/ghi **instance đã có**, không phải API chọn constructor hoặc deserialize JSON trong `@RequestBody`.

## 10. Lỗi thường gặp, exception và cách debug

### 10.1. Có field nhưng BeanWrapper báo không writable

`FieldOnly.secret` tồn tại nhưng không có `setSecret`. `bean.isWritableProperty("secret")` là `false`; `bean.setPropertyValue("secret", "X")` có thể ném `NotWritablePropertyException`. Nếu lớp cố ý không expose setter, không tự ý ép direct field access trong luồng có dữ liệu không tin cậy. Cân nhắc constructor input hoặc API cập nhật có chủ đích.

### 10.2. Có getter nhưng direct field accessor không tìm được field

Một computed getter như `getFullName()` có thể tạo property `fullName` cho `BeanWrapper` dù class chỉ lưu `firstName` và `lastName`. `DirectFieldAccessor` tìm field tên `fullName`; nếu field đó không có, thao tác đọc/ghi theo tên ấy không tương ứng. Kiểm tra xem thiết kế class có property chỉ tính toán hay không.

### 10.3. Setter không chạy

Nếu dữ liệu không còn được strip, chuẩn hóa, cập nhật audit timestamp hoặc kiểm tra invariant, hãy xác định lúc bind ứng dụng đã dùng `initDirectFieldAccess()` hay `forDirectFieldAccess(...)`. Quan sát setter breakpoint: bean access gọi setter thông thường, direct field access không gọi.

### 10.4. Lỗi type conversion

`setPropertyValue("age", "abc")` cho field `int` không thể chuyển như `"21"`. Trong plain accessor, thao tác thường ném exception như `TypeMismatchException` hoặc lỗi liên quan `BeansException`. Với `DataBinder`, lỗi binding có thể được chuyển thành `FieldError` trong `BindingResult` theo cơ chế binding. Không bắt mọi exception rồi bỏ qua hoặc coi kết quả trước lỗi là hoàn toàn hợp lệ.

### 10.5. Lỗi nested path

`setPropertyValue("address.city", "Hue")` có thể gặp `NullValueInNestedPathException` khi `address` là null và auto-grow tắt; hoặc gặp lỗi truy cập property nếu đường dẫn không có/không writable. Tạo nested object phù hợp hoặc bật auto-grow có kiểm soát theo đúng mode. Không xem auto-grow là giải pháp cho class abstract/interface không thể tạo.

### 10.6. Lỗi với field `final`, record hoặc module Java

Direct field access không phải công cụ chỉnh object bất biến. Với record component, constructor là cơ chế đúng để hình thành giá trị. Với JPMS, access không công khai còn phụ thuộc module openness. Nếu cần thao tác private field xuyên module, nên xem lại thiết kế public API và cấu hình module của ứng dụng thay vì dùng reflection như lối tắt.

### 10.7. Nhầm `PropertyAccessorFactory` với Spring BeanFactory

Tên chứa `Factory` không có nghĩa nó quản lý singleton, scope hay dependency injection. Nó chỉ trả một accessor bọc object caller đưa vào. Không dùng nó để lấy `@Component` từ container hoặc khởi tạo Spring bean theo định nghĩa trong `@Configuration`.

## 11. Chọn kiểu nào trong thiết kế ứng dụng?

Ưu tiên **bean property access** khi:

- Class công khai getter/setter hợp lệ và muốn giữ logic chuẩn hóa/kiểm tra ở setter.
- Cần introspection JavaBeans bằng `PropertyDescriptor`.
- Dữ liệu đến từ form input hoặc một nguồn không tin cậy và ứng dụng có thiết kế rõ property nào được phép bind.
- Cần cơ chế mặc định phổ biến của `DataBinder`/Spring MVC.

**Direct field access** có thể hợp lý khi:

- Có object mutable trong một công cụ mapping/import nội bộ nhưng không có setter.
- Làm việc với DTO legacy mà cách truy cập field là lựa chọn thiết kế có chủ ý và đã được kiểm thử.
- Muốn tạo một adapter thao tác field ở tầng hạ tầng, hiểu rõ tác động của việc bỏ qua setter.

Đừng dùng direct field access chỉ vì setter từ chối giá trị không hợp lệ. Nếu setter đang bảo vệ invariant của object, bỏ qua nó thường làm mô hình khó tin cậy hơn.

Một mẫu tổ chức an toàn cho REST/web:

```text
HTTP input
    -> DTO đầu vào có tập field hữu hạn
    -> Bean Validation và kiểm tra nghiệp vụ
    -> Service áp dụng thay đổi được phép
    -> Domain object qua phương thức nghiệp vụ
```

Giới hạn thông qua DTO và `binder.setAllowedFields(...)` khi dùng property binding. Không dựa vào `private`, `isWritableProperty(...)` hay `@InitBinder` đơn lẻ để thay thế authorization và validation tại service.

## 12. Checklist trước khi triển khai

1. Target là một instance mutable phù hợp? Có getter/setter hoặc field thực được phép ghi?
2. Mục tiêu là tôn trọng setter logic hay thao tác raw field?
3. Kiểu trả về cần là `BeanWrapper` để dùng JavaBeans `PropertyDescriptor`, hay `ConfigurablePropertyAccessor` đã đủ?
4. `isReadableProperty`/`isWritableProperty` có đúng cho tên property dự kiến?
5. Với nested path, object trung gian tồn tại chưa? Auto-grow có thật sự cần và được cấu hình đúng mode không?
6. Với kiểu không phải String, đã có `ConversionService` hoặc editor phù hợp chưa?
7. Có field `final`, record, proxy hoặc module boundary nào khiến direct field access không phù hợp?
8. Nếu dùng `DataBinder`, đã gọi `initDirectFieldAccess()` trước khi binding và cấu hình allowed fields/validation chưa?
9. Nếu input từ client, đã kiểm soát field paths, collection sizes, quyền sửa, và không cho cập nhật state nhạy cảm chưa?
10. Có test kiểm tra chính xác giá trị sau bind và việc setter có chạy hay không?

## 13. Bài tập tự đánh giá

### Bài 1 — Chọn API theo nhu cầu

Lớp `Invoice` có field `private BigDecimal amount` và setter `setAmount(...)` làm tròn số theo chính sách. Bạn muốn giữ cách làm tròn khi cập nhật giá trị. Nên chọn API nào?

**Đáp án:** `forBeanPropertyAccess(invoice)`, vì đường ghi sẽ đi qua setter. Dù vậy, logic tính tiền quan trọng vẫn nên được tổ chức ở service/domain method và kiểm thử riêng; một setter trên DTO không thay thế kiểm tra nghiệp vụ.

### Bài 2 — Phân biệt getter tính toán và field

Lớp lưu `firstName`, `lastName` và có `getFullName()` nhưng không có field `fullName`, cũng không có setter `setFullName(...)`. Với mỗi kiểu accessor, khả năng truy cập `fullName` thế nào?

**Đáp án:** `BeanWrapper` có thể đọc JavaBeans property `fullName` qua getter, nhưng không ghi được nếu không có setter. `DirectFieldAccessor` không thể lấy field `fullName` không tồn tại.

### Bài 3 — Dự đoán stdout

Với setter `setCode(String s) { this.code = s.toUpperCase(); }`, một bean accessor và một direct field accessor đều nhận chuỗi `"ab"` vào hai instance giống nhau. Kết quả?

**Đáp án:** bean accessor lưu `"AB"`, direct field accessor lưu `"ab"` nếu field `code` mutable và reflection được phép.

### Bài 4 — Null nested path

Một object có `private Address address;` ban đầu null và bạn tạo plain `BeanWrapper` qua factory. Gọi `setPropertyValue("address.city", "Hue")` có chắc chắn thành công không?

**Đáp án:** **Không.** Plain accessor mặc định không auto-grow nested path. Nếu `address` null, cần tạo instance hợp lệ trước hoặc bật `setAutoGrowNestedPaths(true)` với lớp con có cách khởi tạo phù hợp; vẫn phải kiểm soát độ phức tạp input.

## 14. Tài liệu tham khảo

- Spring Framework Javadoc — [PropertyAccessorFactory](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/beans/PropertyAccessorFactory.html): hai factory method và kiểu trả về.
- Spring Framework Reference — [Property Binding with BeanWrapper](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): JavaBeans, nested/indexed path, getter/setter và property access.
- Spring Framework Javadoc — [DirectFieldAccessor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/DirectFieldAccessor.html): direct instance fields và hỗ trợ nested/collection/map.
- Spring Framework Javadoc — [ConfigurablePropertyAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/ConfigurablePropertyAccessor.html): `ConversionService`, property editors, `setAutoGrowNestedPaths` và mặc định plain accessor.
- Spring Framework Javadoc — [BeanWrapper](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/BeanWrapper.html): contract, introspection và property descriptors.
- Spring Framework Javadoc — [DataBinder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html): `initBeanPropertyAccess()`, `initDirectFieldAccess()` và cơ chế binding.
