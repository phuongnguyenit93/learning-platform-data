# PropertyDescriptor và thông tin getter, setter trong Spring BeanWrapper

## 1. PropertyDescriptor giải quyết vấn đề gì?

Giả sử một form gửi dữ liệu `name=Lan`, `active=true` vào một đối tượng Java. Spring cần biết tên property `name` tương ứng phương thức nào để đọc, phương thức nào để ghi, kiểu dữ liệu gì và có thể chuyển chuỗi đầu vào thành kiểu đó hay không. Chỉ nhìn vào danh sách field bằng reflection là chưa đủ: trong JavaBeans, một **property** thường được mô tả qua **getter/setter** và có thể không có field cùng tên.

`java.beans.PropertyDescriptor` là đối tượng mô tả một property theo quy ước JavaBeans. Nó cho biết:

- **Tên property** qua `getName()`, ví dụ `"name"`.
- **Kiểu property** qua `getPropertyType()`, ví dụ `String.class` hoặc `boolean.class`.
- **Read method** qua `getReadMethod()`: phương thức getter được nhận diện, hoặc `null` nếu property không đọc được.
- **Write method** qua `getWriteMethod()`: phương thức setter được nhận diện, hoặc `null` nếu property không ghi được.
- Các metadata JavaBeans khác như `isBound()`, `isConstrained()`, tên hiển thị, thông tin editor, nếu có.

Trong Spring, `org.springframework.beans.BeanWrapper` là giao diện thao tác/kiểm tra property trên một đối tượng. `BeanWrapperImpl` là triển khai thông dụng. `BeanWrapper.getPropertyDescriptors()` trả về các mô tả property; `getPropertyDescriptor(name)` lấy mô tả một property cụ thể.

**Phân biệt ba vai trò:**

| Thành phần | Nhiệm vụ |
| --- | --- |
| Field, chẳng hạn `private String name` | Nơi lưu dữ liệu trong class, nếu class dùng field để lưu |
| Getter/setter, chẳng hạn `getName()` và `setName(String)` | Hợp đồng truy cập dữ liệu theo quy ước JavaBeans |
| `PropertyDescriptor` | Metadata mô tả tên, kiểu, getter và setter của một property |
| `BeanWrapper` | Đọc/ghi property thật trên một đối tượng, tìm descriptor, kiểm tra khả năng đọc/ghi, hỗ trợ chuyển kiểu |

`PropertyDescriptor` chỉ **mô tả** property. Nó không tự lưu giá trị của `name` và không tự gọi setter để bind HTTP request. Việc gọi `wrapper.setPropertyValue("name", "Lan")` là thao tác qua `BeanWrapper`, và quá trình binding request do thành phần như `DataBinder` phối hợp thực hiện.

## 2. Quy ước JavaBeans: từ tên phương thức đến tên property

Với một property thông thường tên `firstName`:

```java
public class Person {
    private String firstName;

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }
}
```

JavaBeans introspection nhận diện property `firstName`, kiểu `String`, getter `getFirstName` và setter `setFirstName`. Với property kiểu `boolean` nguyên thủy, getter có thể mang dạng `isActive()`:

```java
public class Switch {
    private boolean active;

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Property có tên `active`, kiểu `boolean`, read method `isActive` và write method `setActive`.

Điểm cần nắm là **property không đồng nghĩa với field**:

- Một class có thể chỉ khai báo `private String secret` mà không có getter/setter. Trong property access dựa trên JavaBeans, field đó không tự nhiên trở thành property có thể bind.
- Một getter tính toán như `getDisplayName()` có thể tạo property chỉ đọc dù không có field `displayName`.
- Một setter `setSecret(String)` mà không có getter có thể tạo property chỉ ghi.
- Tên property được suy ra từ quy tắc tên phương thức, không phải từ việc quét mọi private field.
- Với kiểu immutable, record hoặc constructor binding, cách tạo đối tượng có thể khác property binding truyền thống; không nên giả định mọi constructor argument tự có một setter.

### 2.1. Property đọc/ghi, chỉ đọc và chỉ ghi

| Dạng | Java method | Read method | Write method | Khả năng thường thấy |
| --- | --- | --- | --- | --- |
| Đọc và ghi | `getName()`, `setName(String)` | Có | Có | Đọc/ghi |
| Chỉ đọc | `getId()` | Có | `null` | Đọc được, không gán qua property setter |
| Chỉ ghi | `setPassword(String)` | `null` | Có | Gán được, không đọc qua property getter |
| Boolean | `isEnabled()`, `setEnabled(boolean)` | Có | Có | Đọc/ghi |
| Chỉ có field | `private String code` | Không tự nhận ra bởi getter/setter introspection | Không tự nhận ra | Không được property binding truy cập chỉ vì field tồn tại |

Đó là mô hình theo JavaBeans chuẩn. Một số framework có chiến lược truy cập trực tiếp field, dùng annotation, constructor hoặc phương thức accessor riêng. Cần xác định **chiến lược truy cập đang dùng** trước khi kết luận một thuộc tính không thể gán theo mọi cách.

### 2.2. Tại sao getter/setter cần chữ ký thích hợp?

Theo quy ước thông thường:

- Getter `getX()` không nhận tham số và trả về giá trị; dạng `isX()` thường dùng cho `boolean`.
- Setter `setX(T value)` nhận một giá trị kiểu tương thích với property. Quy ước JavaBeans truyền thống dùng kiểu trả về `void`.
- Nếu class có nhiều setter cùng tên nhưng nhận các kiểu khác nhau, việc chọn write method có thể phụ thuộc thuật toán introspection và kiểu getter; nên tránh overload setter mơ hồ trong form/DTO.
- Các phương thức kiểu fluent `name()`/`name(String)` không tự động tuân thủ cách đặt tên `getX`/`setX` chuẩn. Một số cấu hình/framework có thể hỗ trợ chúng, nhưng không nên mặc định `PropertyDescriptor` JavaBeans thông thường sẽ coi đó là setter.
- JavaBeans dùng quy tắc viết hoa/giải viết hoa tên property; các tên nhiều chữ hoa như `URL` có thể tạo tên property khác trực giác. Nên kiểm tra bằng introspection thật thay vì suy luận thủ công.

## 3. API của PropertyDescriptor cần biết

`PropertyDescriptor` là class trong JDK, thuộc package `java.beans`:

```java
import java.beans.PropertyDescriptor;
import java.lang.reflect.Method;

// Chữ ký rút gọn, không phải nội dung đầy đủ của class:
String getName();
Class<?> getPropertyType();
Method getReadMethod();
Method getWriteMethod();
boolean isBound();
boolean isConstrained();
```

Hai phương thức trả về `Method` cho phép xem metadata của getter/setter:

```java
Method getter = descriptor.getReadMethod();
Method setter = descriptor.getWriteMethod();

String getterName = getter == null ? "-" : getter.getName();
String setterName = setter == null ? "-" : setter.getName();
```

Cần kiểm tra `null` trước khi dùng các phương thức như `getName()`, `getParameterTypes()` hoặc `invoke()` trên `Method`. Nếu property chỉ đọc, `getWriteMethod() == null`. Nếu property chỉ ghi, `getReadMethod() == null`.

`getPropertyType()` trả về `Class<?>` đại diện kiểu Java. Với generic như `List<LineItem>`, chỉ `List.class` không cho biết đầy đủ `LineItem`: có thể cần `TypeDescriptor` hoặc metadata generic khác khi triển khai conversion phức tạp. Với indexed property chuyên biệt, property type có thể không xác định theo cách thông thường; không được giả định luôn khác `null` trong mọi trường hợp.

**Metadata không tương đương việc kiểm tra nội dung.** Descriptor có setter `setAge(Integer)` không có nghĩa `"abc"` chuyển được sang số, hoặc tuổi `-5` hợp lệ. Conversion và validation là các bước khác.

## 4. BeanWrapper lấy và sử dụng PropertyDescriptor

Những API chính thuộc `BeanWrapper`:

```java
// Trích chữ ký để minh họa, không phải chương trình độc lập.
PropertyDescriptor[] getPropertyDescriptors();
PropertyDescriptor getPropertyDescriptor(String propertyName);
Object getWrappedInstance();
Class<?> getWrappedClass();

// Kế thừa từ các interface property access:
boolean isReadableProperty(String propertyName);
boolean isWritableProperty(String propertyName);
Object getPropertyValue(String propertyName);
void setPropertyValue(String propertyName, Object value);
Class<?> getPropertyType(String propertyName);
```

Chọn API theo nhu cầu:

- **Xem tất cả property:** `getPropertyDescriptors()`, sau đó đọc tên/kiểu/getter/setter của từng descriptor.
- **Xem đúng một property:** `getPropertyDescriptor("name")`. Nếu property không tồn tại, Spring có thể ném `InvalidPropertyException`.
- **Kiểm tra runtime accessor:** `isReadableProperty("name")` và `isWritableProperty("name")`, tiện hơn so với việc tự so sánh method với `null`.
- **Đọc/ghi giá trị:** `getPropertyValue("name")`, `setPropertyValue("name", "Lan")`. Đây là hành động thực sự trên object, có thể chạy getter/setter.
- **Kiểm tra target:** `getWrappedInstance()` và `getWrappedClass()` cho biết object/class được bao bởi wrapper.

Trong chương trình thường có thể khai báo:

```java
Person person = new Person();
BeanWrapper wrapper = new BeanWrapperImpl(person);
PropertyDescriptor descriptor =
        wrapper.getPropertyDescriptor("firstName");
```

Đây là đoạn ghép với class `Person` ở mục 2, không phải tệp chạy độc lập. `BeanWrapperImpl` có thể chuyển đổi giá trị đầu vào nhờ cơ chế property editor và/hoặc `ConversionService` được cấu hình. Tuy nhiên, **descriptor chỉ cung cấp metadata**; đường chuyển đổi `String → Integer`, lỗi type mismatch và lựa chọn formatter thuộc cơ chế conversion/binding chứ không phải `getWriteMethod()` tự triển khai.

## 5. Ví dụ Java 17 + Spring 6.2: getter/setter được nhận diện như thế nào?

Ví dụ đầy đủ dưới đây minh họa bốn dạng property:

- `name` có getter và setter.
- `active` có boolean getter `isActive()` và setter.
- `id` chỉ có getter, không có field `id` cần thiết vì getter có thể tạo giá trị.
- `pin` chỉ có setter.
- `address.city` minh họa truy cập property lồng nhau khi đối tượng trung gian đã được khởi tạo.

Chương trình dùng Spring Framework **6.2.14**, Java **17+** và Maven; không cần máy chủ web hay Spring application context. Đặt hai tệp như sau:

```text
beanwrapper-descriptor-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── DescriptorDemo.java
```

### 5.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>beanwrapper-descriptor-demo</artifactId>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.DescriptorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Dependency `spring-beans` chứa `BeanWrapper` và `BeanWrapperImpl`. Mã sử dụng JavaBeans của JDK (`java.beans.PropertyDescriptor`), không cần Hibernate/JPA hoặc Bean Validation provider.

### 5.2. src/main/java/demo/DescriptorDemo.java

```java
package demo;

import java.beans.PropertyDescriptor;
import java.lang.reflect.Method;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.NotWritablePropertyException;

public final class DescriptorDemo {

    public static class Address {
        private String city;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public static class Profile {
        private String name;
        private boolean active;
        private String pin;
        private Address address = new Address();

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public boolean isActive() {
            return active;
        }

        public void setActive(boolean active) {
            this.active = active;
        }

        // Property id chỉ có getter; không cần field id.
        public String getId() {
            return "USR-7";
        }

        // Property pin chỉ có setter.
        public void setPin(String pin) {
            this.pin = pin;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    private static String methodName(Method method) {
        return method == null ? "-" : method.getName();
    }

    private static void describe(BeanWrapper wrapper, String property) {
        PropertyDescriptor pd = wrapper.getPropertyDescriptor(property);
        System.out.println(
                property
                + " | type=" + pd.getPropertyType().getSimpleName()
                + " | getter=" + methodName(pd.getReadMethod())
                + " | setter=" + methodName(pd.getWriteMethod())
                + " | readable=" + wrapper.isReadableProperty(property)
                + " | writable=" + wrapper.isWritableProperty(property));
    }

    public static void main(String[] args) {
        Profile profile = new Profile();
        BeanWrapper wrapper = new BeanWrapperImpl(profile);

        describe(wrapper, "name");
        describe(wrapper, "active");
        describe(wrapper, "id");
        describe(wrapper, "pin");

        wrapper.setPropertyValue("name", "Lan");
        wrapper.setPropertyValue("active", "true");
        wrapper.setPropertyValue("address.city", "Hue");

        System.out.println("name=" + wrapper.getPropertyValue("name"));
        System.out.println("active=" + wrapper.getPropertyValue("active"));
        System.out.println("city=" + wrapper.getPropertyValue("address.city"));

        PropertyDescriptor nested =
                wrapper.getPropertyDescriptor("address.city");
        System.out.println("cityType=" + nested.getPropertyType().getSimpleName());

        try {
            wrapper.setPropertyValue("id", "CHANGED");
        } catch (NotWritablePropertyException ex) {
            System.out.println("id write rejected");
        }

        System.out.println("wrappedSameInstance="
                + (wrapper.getWrappedInstance() == profile));
    }
}
```

### 5.3. Chạy và đọc stdout

Từ thư mục `beanwrapper-descriptor-demo`:

```bash
mvn -q compile exec:java
```

**Stdout kỳ vọng từ các lệnh `System.out.println` trong `main`:**

```text
name | type=String | getter=getName | setter=setName | readable=true | writable=true
active | type=boolean | getter=isActive | setter=setActive | readable=true | writable=true
id | type=String | getter=getId | setter=- | readable=true | writable=false
pin | type=String | getter=- | setter=setPin | readable=false | writable=true
name=Lan
active=true
city=Hue
cityType=String
id write rejected
wrappedSameInstance=true
```

Thứ tự các dòng được quyết định bởi lời gọi `describe` và `println` trong chương trình; ví dụ không phụ thuộc thứ tự trả về của `getPropertyDescriptors()`. Lệnh Maven có thể hiển thị chẩn đoán của plugin nếu môi trường cấu hình log khác, nhưng các dòng trên là nội dung do chương trình tự in.

**Giải thích chi tiết:**

1. `getPropertyDescriptor("name")` nhận `PropertyDescriptor` có read method `getName` và write method `setName`, dù hai method không cùng tên với field.
2. `getPropertyDescriptor("active")` nhận ra boolean read method `isActive`. Trong Java, phương thức `getActive()` không phải cách duy nhất để đọc property boolean.
3. `getPropertyDescriptor("id")` vẫn nhận ra property dù không có field riêng, vì `getId()` trả giá trị tính được. `getWriteMethod() == null` và `isWritableProperty("id") == false`.
4. `getPropertyDescriptor("pin")` nhận property chỉ ghi qua `setPin(String)`; `getReadMethod() == null`. Mục đích chỉ để minh họa metadata, không có nghĩa nên lưu mã PIN bằng String thô trong ứng dụng thực tế.
5. `setPropertyValue("active", "true")` thực hiện chuyển chuỗi sang boolean với cơ chế mặc định của `BeanWrapperImpl` rồi gọi setter. Không phải `PropertyDescriptor` tự parse chuỗi.
6. `address.city` là **nested property path**. Vì `Profile.address` đã chứa một `Address` nên wrapper có thể tìm và gán `city`. `getPropertyDescriptor("address.city")` mô tả property `city` ở đối tượng lồng nhau.
7. Ghi vào `id` chỉ có getter sẽ ném `NotWritablePropertyException`. Ví dụ bắt loại exception đó để xác nhận cơ chế bảo vệ khả năng ghi ở mức property.
8. `getWrappedInstance() == profile` là `true` vì wrapper được tạo với chính object đó.

## 6. Lấy danh sách PropertyDescriptor và chọn đúng property

Khi cần kiểm tra một class có những property nào, dùng:

```java
for (PropertyDescriptor pd : wrapper.getPropertyDescriptors()) {
    String propertyName = pd.getName();
    Class<?> type = pd.getPropertyType();
    boolean hasGetter = pd.getReadMethod() != null;
    boolean hasSetter = pd.getWriteMethod() != null;

    // Xem metadata; lựa chọn ứng dụng phải được xác định riêng.
}
```

Đây là **đoạn minh họa để thêm vào mã có biến `wrapper`**. Thư viện có thể trả nhiều property hơn danh sách bạn tự khai báo, và thứ tự descriptor không nên được coi là một hợp đồng. Nếu muốn in thống kê có thứ tự ổn định, cần lọc tên theo yêu cầu và sắp xếp chúng.

Một ví dụ chọn property để hiển thị (chưa phải chính sách bảo mật):

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

List<String> readableNames = Arrays.stream(wrapper.getPropertyDescriptors())
        .filter(pd -> pd.getReadMethod() != null)
        .map(PropertyDescriptor::getName)
        .filter(name -> List.of("name", "active", "id").contains(name))
        .sorted(Comparator.naturalOrder())
        .toList();
```

Đây là snippet minh họa phần xử lý stream; đặt trong method có `wrapper` và các import tương ứng. Cách lọc theo danh sách tên có chủ đích tránh xuất lộ những property không cần hiển thị. Tuy nhiên, cần map/serialize dữ liệu theo hợp đồng API thực tế, không dùng mọi getter được introspection tìm thấy làm danh sách trường response tự động.

### 6.1. BeanUtils và Introspector có liên quan thế nào?

Bên cạnh `BeanWrapper`, có hai đường tra cứu metadata thường gặp:

- JDK: `java.beans.Introspector.getBeanInfo(Profile.class)` trả `BeanInfo`, trong đó có `PropertyDescriptor[]`. Đây là cơ chế JavaBeans introspection nền tảng.
- Spring: `org.springframework.beans.BeanUtils.getPropertyDescriptors(Profile.class)` và `BeanUtils.getPropertyDescriptor(Profile.class, "name")` giúp tra cứu descriptor theo class.

`BeanWrapper` khác ở chỗ nó được **gắn với một instance cụ thể** và còn cung cấp thao tác `getPropertyValue`/`setPropertyValue`, kiểm tra khả năng đọc/ghi runtime và đường dẫn property lồng nhau.

Chữ ký minh họa:

```java
PropertyDescriptor[] fromClass =
        org.springframework.beans.BeanUtils.getPropertyDescriptors(Profile.class);

PropertyDescriptor one =
        org.springframework.beans.BeanUtils.getPropertyDescriptor(Profile.class, "name");
```

`BeanUtils.getPropertyDescriptor(...)` trả `null` nếu không tìm thấy descriptor, trong khi `BeanWrapper.getPropertyDescriptor("unknown")` báo property không hợp lệ theo contract của Spring. Không dùng hai hành vi này thay thế lẫn nhau mà không kiểm tra.

### 6.2. Property path lồng nhau và indexed properties

`BeanWrapper` hỗ trợ cú pháp property path:

```text
name
address.city
orders[0].quantity
settings[theme]
```

Đây là ví dụ về hình thức đường dẫn, **không có nghĩa class `Profile` ở mục 5 chứa `orders` hay `settings`**. Phạm vi thực hiện còn tùy cấu trúc target, generic type, getter/setter, giới hạn auto-grow và cơ chế conversion.

**Quan trọng:** `BeanWrapper.getPropertyDescriptor(String)` hỗ trợ một nested path như `address.city` nhưng Javadoc quy định **không nhận indexed/mapped property path** làm đối số trực tiếp cho truy vấn descriptor. Khi xử lý `orders[0].quantity`, thay vì giả định `getPropertyDescriptor("orders[0].quantity")` sẽ hoạt động, hãy tra kiểu element/property bằng cách thích hợp, ví dụ `getPropertyTypeDescriptor(path)` khi có target và đường dẫn hợp lệ, hoặc introspection trên class phần tử. Với thao tác đọc/ghi giá trị, `getPropertyValue(path)` và `setPropertyValue(path, value)` có hỗ trợ property path phong phú hơn khi cấu trúc thực tế cho phép.

Nếu `address` đang `null`, việc tìm/gán nested property có thể thất bại hoặc cần bật auto-grow cho nested paths; không nên mặc định Spring sẽ tạo ra mọi object lồng nhau khi chỉ gọi `new BeanWrapperImpl(profile)`.

## 7. PropertyDescriptor tham gia Data Binding của Spring thế nào?

Trong MVC hoặc ở ngoài web, Spring có thể dùng `DataBinder` để bind dữ liệu vào một object. Với chế độ JavaBean property binding, binder dựa trên hạ tầng property accessor/BeanWrapper để:

1. Nhận đường dẫn trường, ví dụ `name`.
2. Xác định property tồn tại và ghi được không.
3. Tìm kiểu đích và quy tắc conversion thích hợp.
4. Gán giá trị qua setter hoặc accessor theo cấu hình.
5. Ghi nhận lỗi chuyển kiểu, thuộc tính không hợp lệ và thông tin binding.

```text
Input source: "active" = "true"
              |
              v
        DataBinder / Spring MVC
              |
              v
       BeanWrapper / PropertyAccessor
              |
              +--> PropertyDescriptor("active")
              |      readMethod  = isActive()
              |      writeMethod = setActive(boolean)
              |      propertyType = boolean
              |
              +--> Conversion / PropertyEditor
              |      "true" -> boolean true
              |
              +--> setActive(true)
              v
        Profile.active = true
```

**Descriptor cho biết nơi truy cập và kiểu cần nhắm tới; converter/formatter hoặc editor xử lý biến đổi giá trị; binder điều phối bind và lỗi.** Đừng quy toàn bộ hành vi chuyển kiểu, validation và xử lý HTTP cho `PropertyDescriptor`.

Đoạn ví dụ minh họa việc chỉ cho phép hai property được bind:

```java
// Minh họa cho DataBinder, cần import Spring phù hợp.
// Các class Profile và Address có thể lấy từ chương trình mục 5.
Profile profile = new Profile();

org.springframework.validation.DataBinder binder =
        new org.springframework.validation.DataBinder(profile, "profile");
binder.setAllowedFields("name", "active");

org.springframework.beans.MutablePropertyValues input =
        new org.springframework.beans.MutablePropertyValues();
input.add("name", "Lan");
input.add("active", "true");
input.add("id", "CHANGED");

binder.bind(input);

System.out.println(binder.getBindingResult().hasErrors());
System.out.println(
        java.util.Arrays.toString(
                binder.getBindingResult().getSuppressedFields()));
```

Nếu phần này chạy trong chương trình có dependencies `spring-context` (`DataBinder` thuộc `spring-context`), nó minh họa việc `id` bị suppress thay vì được gán. Đây là **snippet riêng**, không nằm trong chương trình Maven ở mục 5 vốn chỉ khai báo `spring-beans`. Kết quả logic kỳ vọng là `hasErrors=false` và danh sách suppressed fields chứa `id`. Field suppress không mặc nhiên tạo `FieldError`, nên ứng dụng cần xử lý danh sách đó theo chính sách riêng.

### 7.1. Descriptor không phải là danh sách field được phép cập nhật

Có setter chỉ chứng minh **có đường gán qua property**. Nó không nói người dùng được phép thay đổi `role`, `balance` hoặc `status`. Nếu bind HTTP trực tiếp vào entity có nhiều setter, client có thể gửi thêm tên property để gây **overposting/mass assignment**.

Biện pháp thiết kế thích hợp:

- Dùng DTO/form object riêng theo tác vụ, chỉ có thuộc tính đầu vào được phép cung cấp.
- Với property binding, cấu hình `setAllowedFields(...)` theo yêu cầu của tác vụ; xem cả `getSuppressedFields()` nếu cần từ chối request có trường ngoài hợp đồng.
- Đừng dựa vào `private` của field khi class có public setter tương ứng.
- Chỉ ánh xạ những giá trị đã được kiểm tra và được phép sang model nghiệp vụ; ID/trạng thái/quyền/giá nhạy cảm lấy từ ngữ cảnh server.

Sự tồn tại của `PropertyDescriptor.getWriteMethod()` **không phải một cơ chế phân quyền**. Dữ liệu người dùng luôn cần ranh giới input và kiểm tra quyền riêng.

## 8. Khi nào getter/setter có thể gây tác dụng phụ?

JavaBeans getter/setter là **phương thức Java thật**, không phải phép đọc/ghi field miễn phí. Chẳng hạn:

```java
public String getDisplayName() {
    auditLog.add("display name requested");
    return firstName + " " + lastName;
}
```

Đây là **snippet minh họa, không phải class độc lập** (giả sử có `auditLog`, `firstName`, `lastName`). Khi gọi `wrapper.getPropertyValue("displayName")`, getter có thể chạy và ghi log. Ngược lại, **chỉ gọi `pd.getReadMethod()` để lấy metadata không có nghĩa getter được thực thi**.

Vì thế:

- Không chạy đồng loạt tất cả getter của đối tượng không tin cậy chỉ để “kiểm tra cấu trúc”.
- Getter không nên thực hiện I/O tốn kém hoặc tác động quan trọng nếu lớp được dùng rộng rãi trong binding, serialization hay mapping.
- Setter có thể normalize, reject hoặc thay đổi state; `setPropertyValue` thực thi setter, nên có thể phát sinh ngoại lệ và side effect.
- Trong Spring, việc đọc giá trị cũ cho custom editor có cấu hình riêng (`extractOldValueForEditor`). Không giả định mỗi lần ghi đều phải gọi getter trước.
- `isReadableProperty`/`isWritableProperty` và method metadata là **khả năng về mặt truy cập**; không bảo đảm việc gọi getter/setter nhất định thành công với mọi dữ liệu và trạng thái runtime.

## 9. PropertyDescriptor, reflection và TypeDescriptor khác nhau ra sao?

| Công cụ | Thông tin chính | Dùng khi nào |
| --- | --- | --- |
| `java.lang.reflect.Field` | Field khai báo của class, type và modifiers | Khi cần metadata field hoặc cơ chế field access rõ ràng |
| `java.lang.reflect.Method` | Một phương thức cụ thể và chữ ký | Khi cần inspect/call getter, setter hay method khác |
| `java.beans.PropertyDescriptor` | Property JavaBeans, read/write methods, kiểu property | Khi cần biết tên property, getter, setter chuẩn |
| `BeanWrapper` | Metadata + truy cập property trên object + hỗ trợ đường dẫn | Khi cần đọc/ghi property, nhận diện nested paths |
| `TypeDescriptor` (Spring) | Thông tin kiểu giàu hơn, có thể chứa generic và annotation | Khi conversion/formatting cần biết `List<Item>` hay annotation trên field |
| `BeanUtils` (Spring) | Tiện ích thao tác/introspection theo class | Khi chỉ cần descriptor cho type hoặc property |

Đặc biệt, `PropertyDescriptor.getPropertyType()` thường chỉ trả một `Class<?>`. Ví dụ property `List<Address> addresses` trả kiểu thô `List.class`; Spring `TypeDescriptor` có thể mang thêm kiểu phần tử để hỗ trợ conversion. Một `PropertyDescriptor` không thay thế được toàn bộ thông tin generic/annotation.

### 9.1. Những trường hợp không thể suy luận chỉ từ setter

Một setter `setAmount(BigDecimal value)` không cho biết:

- Chuỗi `"1.000,50"` sẽ được parse thế nào ở `vi-VN` hay `en-US`.
- Khoản tiền có được phép âm hay không.
- Ai có quyền ghi số tiền.
- Giá trị null có hợp lệ theo use case không.
- Hệ thống lưu field trực tiếp, JPA attribute hay command khác.

Cần `ConversionService`/`Formatter`, validation, authorization và mô hình nghiệp vụ tương ứng. Descriptor chỉ là một mắt xích giúp Spring xác định thuộc tính và phương thức truy cập.

## 10. Lỗi thường gặp khi thao tác getter, setter và BeanWrapper

| Tình huống | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `getPropertyDescriptor("foo")` không tìm thấy | Property không tồn tại theo introspection; sai tên hoặc không theo quy ước JavaBeans | Kiểm tra method getter/setter, chữ hoa/chữ thường và tên property thực |
| Có `private String name` mà `isWritableProperty("name") == false` | Chỉ có field, không có public setter được nhận diện | Thêm setter đúng quy ước khi cần property binding, hoặc chọn chiến lược field/constructor binding phù hợp |
| `getWriteMethod() == null` | Property chỉ đọc hoặc setter không được nhận diện | Dùng constructor/factory cho immutable object, hoặc thêm setter hợp lệ nếu thực sự cần ghi |
| `getReadMethod() == null` | Property chỉ ghi | Tránh gọi `getPropertyValue` trên property đó; thiết kế accessor phù hợp |
| `setPropertyValue("age", "abc")` thất bại | Đầu vào không chuyển được sang kiểu đích | Chỉnh input, đăng ký converter/formatter phù hợp, xử lý lỗi binding |
| `address.city` thất bại | `address` null hoặc getter/setter của đường dẫn không dùng được | Khởi tạo object lồng nhau hoặc cấu hình auto-grow đúng phạm vi |
| Tra descriptor cho `items[0]` như property đơn | API descriptor không hỗ trợ indexed/mapped syntax trực tiếp | Phân biệt metadata property với đường dẫn đến phần tử; tra kiểu phù hợp |
| Phụ thuộc vào thứ tự `getPropertyDescriptors()` | Thứ tự introspection không phải hợp đồng nghiệp vụ | Lọc/sắp xếp theo danh sách tên xác định |
| Cho rằng setter có nghĩa request được quyền cập nhật | Nhầm metadata với authorization | Input DTO riêng và allowlist ở server |
| Cho rằng descriptor tự validate | Metadata không có quy tắc nghiệp vụ | Kích hoạt validation và kiểm tra lỗi |
| Coi mọi accessor là side-effect-free | Getter/setter có thể thực thi code tùy ý | Thiết kế accessor thuần hoặc gọi có kiểm soát |

### Các exception nên biết

- `InvalidPropertyException`: tên/path property không hợp lệ trong ngữ cảnh truy cập.
- `NotReadablePropertyException`: cố đọc property không đọc được.
- `NotWritablePropertyException`: cố ghi property không ghi được.
- `TypeMismatchException`: giá trị không chuyển được sang kiểu đích theo cơ chế binding/conversion.
- Các lỗi khác có thể đến từ setter/getter hoặc nested object không sẵn có; loại exception cuối cùng tùy API và cấu hình.

Không dùng `try/catch(Exception)` để âm thầm bỏ mọi lỗi. Trong MVC, nên xử lý lỗi nhập liệu bằng `BindingResult` hoặc exception handler thích hợp và trả message ổn định cho người dùng.

## 11. Kiểm tra hiểu kiến thức

**Câu 1.** Một class chỉ có `getFullName()` mà không có `setFullName(...)`. Có thể có `PropertyDescriptor` cho `fullName` không?

**Có.** Đó là property chỉ đọc, với write method `null`.

**Câu 2.** `private String token` có public setter `setToken(String)`, không có getter. Field là private thì có thể bind theo property access không?

**Có thể**, vì setter công khai tạo đường gán qua property; JavaBeans metadata vẫn có thể mô tả property chỉ ghi. Quyền truy cập HTTP vẫn phải được kiểm soát riêng.

**Câu 3.** `PropertyDescriptor.getWriteMethod() != null` có chứng minh đầu vào `"abc"` parse được thành `Integer` không?

**Không.** Setter có thể nhận `Integer`, nhưng việc chuyển đổi chuỗi là trách nhiệm của conversion/binder và có thể thất bại.

**Câu 4.** Để xem getter của `name` mà không gọi getter, làm gì?

Gọi `wrapper.getPropertyDescriptor("name").getReadMethod()` và xem metadata `Method`. Chỉ `getReadMethod()` không thực thi getter.

**Câu 5.** Lệnh nào thích hợp để hỏi property có thể ghi không?

`wrapper.isWritableProperty("name")` hoặc dùng descriptor để kiểm tra write method. Việc ghi thực tế vẫn có thể thất bại do conversion hay business logic trong setter.

**Câu 6.** Vì sao không dùng mọi property có setter làm input từ request?

Vì **quyền ghi về mặt kỹ thuật khác quyền cập nhật theo nghiệp vụ**; cần input DTO và allowed fields để tránh mass assignment.

**Câu 7.** `getPropertyDescriptor("address.city")` và `getPropertyDescriptor("orders[0].quantity")` giống nhau không?

Không. Javadoc của `BeanWrapper.getPropertyDescriptor` cho phép nested path nhưng loại trừ indexed/mapped property path. Với phần tử collection, cần cơ chế metadata phù hợp.

## 12. Quy trình áp dụng vào dự án thực tế

1. Xác định object đích và chiến lược truy cập: JavaBean setter, direct field, constructor binding hay immutable type.
2. Dùng `BeanWrapper`/`BeanUtils` khi cần introspect tên, kiểu và method truy cập; ưu tiên `getPropertyDescriptor(name)` cho một property đã biết.
3. Kiểm tra `getReadMethod()`, `getWriteMethod()` hoặc `isReadableProperty()`/`isWritableProperty()`; xử lý trường hợp `null`/property không tồn tại.
4. Nếu cần đọc/ghi thật, dùng `getPropertyValue()`/`setPropertyValue()` trên target được quản lý đúng vòng đời; xử lý exception.
5. Với input dạng chuỗi, cấu hình conversion/formatting và validation phù hợp, không ép `PropertyDescriptor` đảm nhận các bước này.
6. Với HTTP request, dùng form/DTO giới hạn field, kiểm tra quyền và không tin các property có thể ghi chỉ vì setter tồn tại.
7. Thử các trường hợp property chỉ đọc, chỉ ghi, boolean getter, tên lồng nhau, null nested object, type mismatch, nhiều setter cùng tên và field không được phép cập nhật.

**Điểm cần ghi nhớ:** `PropertyDescriptor` cho biết *property nào*, *kiểu gì*, *getter nào*, *setter nào*; `BeanWrapper` sử dụng thông tin đó để *đọc/ghi đối tượng*. Metadata giúp Spring binding hoạt động linh hoạt, nhưng conversion, validation và authorization vẫn là những trách nhiệm tách biệt.

## 13. Tài liệu tham khảo chính thức

- [Spring Framework — BeanWrapper (Javadoc 6.2.14)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanWrapper.html): `getPropertyDescriptors()`, `getPropertyDescriptor(name)`, nested property, read/write.
- [Spring Framework — BeanWrapperImpl (Javadoc 6.2.14)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanWrapperImpl.html): triển khai BeanWrapper và introspection.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): JavaBeans, property access, chuyển kiểu và data binder.
- [Java SE 17 — java.beans.PropertyDescriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyDescriptor.html): getReadMethod, getWriteMethod, getPropertyType và JavaBeans metadata.
- [Spring Framework — BeanUtils](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanUtils.html): các tiện ích truy vấn descriptor dựa trên class.
- [Spring Framework — TypeDescriptor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/TypeDescriptor.html): metadata kiểu phục vụ chuyển đổi và generic.