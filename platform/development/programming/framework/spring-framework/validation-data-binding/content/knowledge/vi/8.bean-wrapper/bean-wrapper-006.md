# isReadableProperty và isWritableProperty trong Spring BeanWrapper

`BeanWrapper` là giao diện thuộc `org.springframework.beans` giúp Spring **đọc, ghi, chuyển đổi và khảo sát các property của JavaBean**. Hai phương thức đặc biệt hữu ích khi làm việc với tên property động là:

- `isReadableProperty(String propertyName)`: kiểm tra property có thể **đọc** qua cơ chế property accessor hay không.
- `isWritableProperty(String propertyName)`: kiểm tra property có thể **ghi** qua cơ chế property accessor hay không.

Cả hai trả về `boolean`. Với một tên property thông thường không tồn tại, kết quả là `false`. Chúng có thể kiểm tra **đường dẫn lồng nhau** như `"address.city"` và trong những điều kiện thích hợp cả phần tử có chỉ số hoặc khóa, ví dụ `"items[0].name"`.

Hai phương thức này trả lời câu hỏi về **khả năng truy cập theo cơ chế BeanWrapper**, không có nghĩa giá trị đang hợp lệ, truy cập đã được phân quyền, setter chắc chắn chạy thành công hoặc object đã được bind từ request HTTP.

## 1. BeanWrapper hoạt động ở tầng nào?

Trong Java, một trường `private` không tự động là một JavaBeans property có thể đọc/ghi qua `BeanWrapperImpl`. Property thường được mô tả qua các accessor đặt tên theo quy ước:

~~~java
public String getName() { ... }        // đọc property "name"
public void setName(String value) { ... } // ghi property "name"
public boolean isActive() { ... }      // đọc boolean property "active"
public void setActive(boolean v) { ... } // ghi boolean property "active"
~~~

`BeanWrapperImpl` dùng cơ chế introspection property để khám phá thông tin này. Nó thường được sử dụng bên trong **Spring BeanFactory** và **DataBinder**, mặc dù ứng dụng cũng có thể tạo nó trực tiếp:

~~~java
Person person = new Person();
BeanWrapper wrapper = new BeanWrapperImpl(person);
boolean canRead = wrapper.isReadableProperty("name");
boolean canWrite = wrapper.isWritableProperty("name");
~~~

Đây là **đoạn trích**: cần class `Person` và các import Spring; ví dụ hoàn chỉnh có ở phần 4.

Phân biệt những thành phần gần nhau:

| Thành phần | Vai trò |
| --- | --- |
| `PropertyAccessor` | Interface gốc định nghĩa thao tác đọc, ghi, tra cứu type và kiểm tra khả năng đọc/ghi property |
| `BeanWrapper` | Interface chuyên cho **JavaBeans properties**, mở rộng cơ chế truy cập và chuyển kiểu |
| `BeanWrapperImpl` | Implementation thường dùng của `BeanWrapper` |
| `PropertyAccessorFactory.forBeanPropertyAccess(bean)` | Factory trả một `BeanWrapper` cho bean |
| `PropertyAccessorFactory.forDirectFieldAccess(bean)` | Tạo accessor dùng **field trực tiếp**; quy tắc đọc/ghi khác với JavaBeans getter/setter |
| `DataBinder` | Điều phối binding dữ liệu đầu vào vào object, quản lý allowed/disallowed fields, lỗi binding và validation |

`isReadableProperty` và `isWritableProperty` được khai báo trong `PropertyAccessor`, vì vậy xuất hiện trên cả `BeanWrapper` và các implementation phù hợp. Với mục tiêu học **BeanWrapper**, ta sử dụng `BeanWrapperImpl` và quy tắc JavaBeans.

## 2. Ý nghĩa chính xác của hai phương thức

Chữ ký:

~~~java
boolean isReadableProperty(String propertyName);
boolean isWritableProperty(String propertyName);
~~~

`propertyName` là tên property hoặc đường dẫn như `"name"`, `"address.city"`. Giá trị trả về cho biết cơ chế accessor hiện tại **có khả năng** đọc hoặc ghi property tương ứng.

- `isReadableProperty("name") == true` thường chỉ ra accessor có thể lấy giá trị, ví dụ qua `getName()`.
- `isWritableProperty("name") == true` thường chỉ ra accessor có thể gán giá trị, ví dụ qua `setName(...)`.
- Một property có thể chỉ đọc, chỉ ghi, đọc và ghi, hoặc không được nhận diện.
- Kết quả hai phương thức **độc lập**: `readable == true` không suy ra `writable == true` và ngược lại.

Với JavaBeans thông thường, bảng sau là cách dự đoán:

| Khai báo public có trên bean | Readable? | Writable? | Giải thích |
| --- | :---: | :---: | --- |
| `getName()` và `setName(String)` | `true` | `true` | Đọc/ghi đủ hai chiều |
| Chỉ `getId()` | `true` | `false` | Property chỉ đọc |
| Chỉ `setToken(String)` | `false` | `true` | Property chỉ ghi |
| `isActive()` và `setActive(boolean)` | `true` | `true` | JavaBeans boolean getter |
| Chỉ khai báo `private String note;` | `false` | `false` | Không có accessor JavaBeans |
| Không có property `"missing"` | `false` | `false` | Tên không tồn tại |

**Điểm dễ nhầm:** `false` của `isWritableProperty` chỉ nói không thể ghi theo cơ chế accessor đang dùng. Nó **không nói object bất biến trong mọi trường hợp**; object có thể bị thay đổi bởi constructor, method khác, reflection hoặc direct-field access. Tương tự, `true` không có nghĩa người dùng HTTP được phép sửa property ấy.

### Tên property là tên JavaBeans, không nhất thiết là tên field

~~~java
private String displayName;

public String getDisplayName() {
    return displayName;
}

public void setDisplayName(String displayName) {
    this.displayName = displayName;
}
~~~

Tên cần kiểm tra là `"displayName"`, không phải `"getDisplayName"`, `"setDisplayName"` hay `"DisplayName"`. BeanWrapper sử dụng **quy tắc đặt tên property của JavaBeans**. Với class có tên accessor bất thường, hãy kiểm tra `PropertyDescriptor` thay vì suy đoán tên.

Đối với Java `record` hoặc immutable DTO, có thể phù hợp hơn với **constructor binding** thay vì cố thực hiện property binding bằng setter. Không dùng kết quả `isWritableProperty(...) == false` để kết luận mọi cách tạo/bind object đó đều bất khả thi.

## 3. Vì sao nên kiểm tra trước khi đọc hoặc ghi?

Có ba tình huống thực tế:

1. **Tên property đến từ cấu hình hoặc một mapping đã cho phép:** trước khi gọi `getPropertyValue(name)` hoặc `setPropertyValue(name, value)`, kiểm tra tên property có được hỗ trợ bởi bean hiện tại.
2. **Tạo công cụ nội bộ:** khi xây trình hiển thị metadata, mapper hoặc editor form, cần phân biệt field hiển thị chỉ đọc với field có thể chỉnh sửa.
3. **Đường dẫn lồng nhau:** khi đi vào `"address.city"`, cần biết accessor có thể đi qua các thành phần của object graph và đọc/ghi đích được hay không.

Mẫu kiểm tra:

~~~java
if (wrapper.isReadableProperty(propertyName)) {
    Object current = wrapper.getPropertyValue(propertyName);
    // Xử lý current phù hợp với mục đích của ứng dụng.
}

if (wrapper.isWritableProperty(propertyName)) {
    wrapper.setPropertyValue(propertyName, proposedValue);
}
~~~

Đây là **đoạn trích**, giả định `wrapper` và `propertyName` đã được tạo. Trong thực tế vẫn cần xử lý exception bởi getter hoặc setter có thể ném lỗi, việc chuyển kiểu có thể thất bại, hoặc đối tượng lồng nhau có thể không truy cập được.

Đặc biệt: nếu `propertyName` đến từ client, việc “có thể ghi” **không được dùng như quy tắc ủy quyền**. Chỉ thực hiện binding trên các property được phép bởi server, tốt nhất qua DTO có đúng các trường cần nhận.

## 4. Ví dụ hoàn chỉnh Java 17+ có thể chạy

Ta tạo một JavaBean `Person` với bốn kiểu property:

- `name` có getter và setter → đọc/ghi;
- `id` chỉ có getter → chỉ đọc;
- `token` chỉ có setter → chỉ ghi;
- `active` có boolean getter và setter → đọc/ghi;
- `address.city` là đường dẫn lồng nhau đến một JavaBean khác;
- `missing` không tồn tại → không đọc, không ghi.

Chương trình sẽ in kết quả kiểm tra, thử đọc/ghi các property hợp lệ và bắt exception khi cố thực hiện thao tác không hỗ trợ.

### 4.1. Tạo Maven project

Dùng Maven với **JDK 17+**. File `pom.xml` dưới đây chọn Spring Framework `6.2.19` để minh họa API. Đây là một phiên bản ghim cho ví dụ, không phải hướng dẫn tự động lấy “bản Spring mới nhất”.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>bean-wrapper-access-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-beans</artifactId>
            <version>6.2.19</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-beans` chứa `BeanWrapperImpl` và kéo theo các dependency Spring cần thiết. Trong dự án dùng Spring Boot, thường nên để BOM/parent của Boot quản lý phiên bản `spring-beans` để tránh lệch phiên bản các module Spring.

### 4.2. Mã nguồn Java

Tạo file **`src/main/java/example/BeanWrapperAccessDemo.java`**:

~~~java
package example;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.NotReadablePropertyException;
import org.springframework.beans.NotWritablePropertyException;

public class BeanWrapperAccessDemo {

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
        private final String id = "U-001";
        private String token;
        private boolean active;
        private Address address = new Address();

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        // Chỉ getter: readable = true, writable = false.
        public String getId() {
            return id;
        }

        // Chỉ setter: readable = false, writable = true.
        public void setToken(String token) {
            this.token = token;
        }

        // Method bình thường, không phải getter của "token".
        public boolean hasToken() {
            return token != null;
        }

        public boolean isActive() {
            return active;
        }

        public void setActive(boolean active) {
            this.active = active;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    private static void inspect(BeanWrapper wrapper, String name) {
        System.out.println(
                name
                + ": read=" + wrapper.isReadableProperty(name)
                + ", write=" + wrapper.isWritableProperty(name));
    }

    public static void main(String[] args) {
        Person person = new Person();
        BeanWrapper wrapper = new BeanWrapperImpl(person);

        inspect(wrapper, "name");
        inspect(wrapper, "id");
        inspect(wrapper, "token");
        inspect(wrapper, "active");
        inspect(wrapper, "address.city");
        inspect(wrapper, "missing");

        // Chỉ gán các property mà chương trình chủ động cho phép.
        wrapper.setPropertyValue("name", "Lan");
        wrapper.setPropertyValue("active", "true");
        wrapper.setPropertyValue("address.city", "Hue");
        wrapper.setPropertyValue("token", "internal-token");

        System.out.println("name=" + wrapper.getPropertyValue("name"));
        System.out.println("id=" + wrapper.getPropertyValue("id"));
        System.out.println("active=" + wrapper.getPropertyValue("active"));
        System.out.println("city=" + wrapper.getPropertyValue("address.city"));
        System.out.println("tokenAssigned=" + person.hasToken());

        try {
            wrapper.getPropertyValue("token");
        } catch (NotReadablePropertyException ex) {
            System.out.println("readToken=NotReadablePropertyException");
        }

        try {
            wrapper.setPropertyValue("id", "U-999");
        } catch (NotWritablePropertyException ex) {
            System.out.println("writeId=NotWritablePropertyException");
        }
    }
}
~~~

Trong class này `Person` và `Address` đều là JavaBean với phương thức public. `Address` đã được khởi tạo trong `Person`, nên đường dẫn `address.city` có object trung gian hợp lệ. Không cần chạy server HTTP; ví dụ sử dụng `BeanWrapperImpl` trực tiếp.

### 4.3. Lệnh chạy và stdout

Cấu trúc project:

~~~text
bean-wrapper-access-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── BeanWrapperAccessDemo.java
~~~

Tại thư mục chứa `pom.xml`, kiểm tra Java/Maven và chạy:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=example.BeanWrapperAccessDemo
~~~

**Những dòng do chương trình in** trong cấu hình trên:

~~~text
name: read=true, write=true
id: read=true, write=false
token: read=false, write=true
active: read=true, write=true
address.city: read=true, write=true
missing: read=false, write=false
name=Lan
id=U-001
active=true
city=Hue
tokenAssigned=true
readToken=NotReadablePropertyException
writeId=NotWritablePropertyException
~~~

Lệnh có thể còn in thông báo Maven hoặc cảnh báo môi trường khác; khối trên mô tả output do các câu lệnh `System.out.println` trong chương trình tạo ra. Không có lệnh `javac` thuần vì ví dụ cần thư viện Spring trong classpath; Maven tải dependency và biên dịch theo phiên bản Java đã cấu hình.

### 4.4. Phân tích kết quả

- `name` có cả `getName` và `setName` nên đọc/ghi đều `true`.
- `id` có `getId` nhưng không có `setId`, nên đọc được `"U-001"` và ghi bị từ chối bởi `BeanWrapperImpl`.
- `token` có `setToken` nhưng không có `getToken`, nên ghi được nhưng không đọc trực tiếp qua property `token`. Method `hasToken()` do ứng dụng định nghĩa giúp xác nhận setter đã chạy; nó không biến `token` thành readable property.
- `active` dùng `isActive()` cho kiểu boolean. Giá trị truyền vào setter qua `BeanWrapper` là chuỗi `"true"` và được chuyển đổi thành `boolean true`.
- `address.city` đi qua getter `getAddress()` và accessor của `Address`; có thể đọc/ghi vì object con đã được khởi tạo và có getter/setter cho `city`.
- `missing` không có descriptor phù hợp nên cả hai kết quả là `false`.
- `NotReadablePropertyException` và `NotWritablePropertyException` cho thấy điều gì xảy ra khi cố thực hiện các thao tác bị cấm. Chỉ kiểm tra `isReadableProperty` hoặc `isWritableProperty` **không sinh exception trong các trường hợp đơn giản trên**; exception xuất hiện khi gọi `getPropertyValue` hoặc `setPropertyValue` tương ứng.

## 5. BeanWrapper xác định property như thế nào?

### 5.1. JavaBeans convention

Cơ chế BeanWrapper dựa trên property accessor và metadata của JavaBean, không đơn giản đọc tên mọi field trực tiếp. Ví dụ:

~~~java
public class Profile {
    private String email;

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Đoạn class này chỉ minh họa metadata; trong Java 17 nó hợp lệ khi lưu thành `Profile.java`. Property là `email`. Nếu chỉ giữ field `private String email` và xóa cả getter/setter thì `BeanWrapperImpl` thông thường không đọc/ghi property ấy, dù code bên trong class vẫn có thể truy cập field trực tiếp.

Với boolean, `isEnabled()` và `getEnabled()` đều có thể được nhận diện theo quy ước JavaBeans (tùy kiểu trả về và tình huống). Khi getter, setter có tên không khớp hoặc overload gây mơ hồ, hãy kiểm tra mô hình bean thực tế và `PropertyDescriptor`.

### 5.2. PropertyDescriptor và type metadata

`BeanWrapper` cũng cho phép lấy metadata:

~~~java
BeanWrapper wrapper = new BeanWrapperImpl(new Person());

for (java.beans.PropertyDescriptor descriptor
        : wrapper.getPropertyDescriptors()) {
    System.out.println(descriptor.getName());
    System.out.println(descriptor.getReadMethod());
    System.out.println(descriptor.getWriteMethod());
}
~~~

Đây là **đoạn trích**: `Person` được định nghĩa trong ví dụ hoàn chỉnh. Một `PropertyDescriptor` thường nêu:

- Tên property (`getName()`).
- Phương thức đọc (`getReadMethod()`) nếu có.
- Phương thức ghi (`getWriteMethod()`) nếu có.
- Kiểu Java được suy ra (`getPropertyType()`).

Để lấy type của một đường dẫn property cụ thể, có thể dùng `wrapper.getPropertyType("address.city")` hoặc `wrapper.getPropertyTypeDescriptor("address.city")` tùy nhu cầu. Kiểu trả về và khả năng xác định type cho phần tử indexed/mapped phụ thuộc cấu trúc thực tế.

**Không suy luận từ descriptor rằng setter chắc chắn thành công:** một setter có thể tự từ chối giá trị, ném exception hoặc yêu cầu trạng thái hợp lệ. Metadata chỉ là tín hiệu về khả năng truy cập theo API, không thay thế thao tác thực tế và kiểm thử.

### 5.3. PropertyAccessorFactory và direct field access

Hai lựa chọn:

~~~java
import org.springframework.beans.PropertyAccessor;
import org.springframework.beans.PropertyAccessorFactory;

PropertyAccessor beanAccess =
        PropertyAccessorFactory.forBeanPropertyAccess(person);

PropertyAccessor fieldAccess =
        PropertyAccessorFactory.forDirectFieldAccess(person);
~~~

Đây là **đoạn trích**; `person` là object có sẵn.

- `forBeanPropertyAccess` sử dụng hành vi JavaBeans getter/setter tương tự `BeanWrapperImpl`.
- `forDirectFieldAccess` dùng field trực tiếp và không yêu cầu các accessor cùng kiểu. Một field không có getter/setter có thể được đọc/ghi theo quy tắc reflection của accessor này, nhưng final field và các hạn chế của Java/module system cần được xem xét.

Đừng thay `BeanWrapperImpl` bằng direct-field access một cách tùy ý để làm cho một property “writable”. Hai cơ chế có ranh giới encapsulation khác nhau.

## 6. Đường dẫn property lồng nhau

`isReadableProperty` và `isWritableProperty` có thể nhận đường dẫn nhiều mức:

~~~java
wrapper.isReadableProperty("address.city");
wrapper.isWritableProperty("address.city");

wrapper.isReadableProperty("contacts[0].phone");
wrapper.isWritableProperty("attributes[key]");
~~~

Hai dòng đầu tương ứng class `Person` trong ví dụ; hai dòng sau chỉ minh họa **cú pháp đường dẫn**, không thuộc model `Person` đã xây.

Với đường dẫn `"address.city"`, Spring cần:

1. Xác định `address` trên object gốc và đi tới object con.
2. Xác định `city` trên object con.
3. Xem có khả năng đọc/ghi property đích theo accessor và trạng thái hiện tại.

Nếu `address == null`, đường dẫn có thể không giải quyết được hoặc chịu ảnh hưởng của cấu hình **auto-grow nested paths**. Một số thao tác truy cập có thể khiến cấu trúc lồng nhau được tạo khi auto-grow được bật và kiểu con có thể khởi tạo. Vì vậy, **không coi việc kiểm tra property path là thao tác luôn vô tác dụng phụ** trong mọi cấu hình.

Với `contacts[0].phone`, còn có điều kiện phần tử index `0` phải có hoặc được auto-grow hợp lệ, nằm trong giới hạn collection growth và kiểu phần tử phải xác định được. Với `attributes[key]`, khả năng truy cập phụ thuộc map/property tương ứng. Kết quả có thể khác nhau theo object graph và cấu hình, không chỉ tên getter/setter của class ngoài cùng.

**Khuyến nghị thực tế:** với property path phức tạp, tạo các test trên model thực và cả tình huống object con `null`, list rỗng, index vượt giới hạn. Tránh dùng khả năng auto-grow như một cơ chế cấp quyền cho dữ liệu người dùng.

## 7. So với getPropertyValue và setPropertyValue

Bốn API có trách nhiệm khác nhau:

| API | Tác dụng | Điều quan trọng |
| --- | --- | --- |
| `isReadableProperty(name)` | Hỏi liệu property có thể đọc | Trả `boolean`, không trả giá trị |
| `isWritableProperty(name)` | Hỏi liệu property có thể ghi | Trả `boolean`, không thực hiện gán |
| `getPropertyValue(name)` | Đọc **giá trị hiện tại** | Có thể lỗi nếu không đọc được hoặc getter thất bại |
| `setPropertyValue(name, value)` | Gán **giá trị mới**, có thể chuyển kiểu | Có thể lỗi nếu không ghi được, giá trị không chuyển được hoặc setter thất bại |

Ví dụ:

~~~java
if (wrapper.isReadableProperty("name")) {
    Object current = wrapper.getPropertyValue("name");
    System.out.println(current);
}

if (wrapper.isWritableProperty("name")) {
    wrapper.setPropertyValue("name", "Minh");
}
~~~

Đoạn trích này hợp lệ khi đặt trong method có biến `wrapper` tương ứng.

### Khi nào cần bắt exception?

Một kết quả `true` chỉ phản ánh khả năng truy cập theo metadata/đường dẫn **tại thời điểm kiểm tra**. Thao tác sau đó vẫn có thể thất bại khi:

- Getter/setter ném exception vì điều kiện nghiệp vụ.
- Giá trị không đổi được sang kiểu đích, ví dụ `"abc"` cho một setter nhận `int`.
- Object trung gian trong nested path là `null` hoặc bị thay đổi giữa lúc kiểm tra và sử dụng.
- Mức truy cập Java/module reflection không cho phép thực hiện thao tác.
- Một proxy hoặc bean động thay đổi trạng thái và hành vi.

Khi `getPropertyValue` hoặc `setPropertyValue` không phù hợp, Spring có thể ném các loại exception như `NotReadablePropertyException`, `NotWritablePropertyException`, `TypeMismatchException` hoặc các subclass khác của `BeansException` tùy lỗi. Không xây logic “thấy true là chắc chắn không thể lỗi”.

Mặt khác, việc `isReadableProperty("missing")` trả `false` thường an toàn hơn việc thử `getPropertyValue("missing")` rồi dùng exception như một phép thăm dò. Với các đường dẫn lồng nhau, bạn vẫn cần xử lý lỗi giải quyết path nếu xảy ra.

## 8. Tích hợp với DataBinder: kiểm tra metadata khác với cho phép bind

Trong Spring MVC, `@ModelAttribute` thường được gắn dữ liệu request qua `WebDataBinder`, còn `DataBinder` nền tảng dựa trên cơ chế truy cập property. Điều quan trọng: **writable theo BeanWrapper không đồng nghĩa được phép bind từ client**.

Xem đoạn ví dụ sau (chỉ là phần trong một method, cần class `Person` đã khai báo):

~~~java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

Person person = new Person();
DataBinder binder = new DataBinder(person, "person");
binder.setAllowedFields("name", "active");

// Client gửi cả một trường không được phép.
MutablePropertyValues input = new MutablePropertyValues()
        .add("name", "Lan")
        .add("active", "true")
        .add("address.city", "Somewhere");

binder.bind(input);

System.out.println(person.getName());                 // Lan
System.out.println(person.isActive());                // true
System.out.println(person.getAddress().getCity());    // null
System.out.println(binder.getBindingResult()
        .getSuppressedFields().length);                // 1
~~~

Đây là **đoạn trích minh họa**, không phải class độc lập. Mặc dù `BeanWrapperImpl` có thể xem `address.city` là writable, **allowlist** của `DataBinder` đã loại field đó ra khỏi quá trình gán. Kết quả suppressed fields cần được kiểm tra nếu ứng dụng muốn ghi log hoặc từ chối dữ liệu ngoài hợp đồng.

**Quy tắc an toàn:** chỉ bind vào request DTO có đúng các trường cần thiết, dùng allowed fields khi cần property binding, và tiếp tục xác thực quyền thao tác trong service. `isWritableProperty` chỉ nêu khả năng của accessor, **không phải cơ chế bảo mật chống mass assignment**.

Để kiểm tra dữ liệu có hợp lệ hay không, dùng `Validator`/Jakarta Validation và `BindingResult`. Hai phương thức `isReadableProperty`, `isWritableProperty` **không thực hiện Bean Validation**.

## 9. Những lỗi hay gặp

### Lỗi 1 — nhầm tên field private với bean property

~~~java
public class Example {
    private String title;
}
~~~

Với `BeanWrapperImpl` thông thường, `title` không trở thành readable/writable JavaBeans property chỉ vì có field. Hãy thêm accessor phù hợp nếu việc truy cập ấy thuộc thiết kế API của class; hoặc chủ động chọn direct-field access khi có lý do kỹ thuật rõ ràng.

### Lỗi 2 — giả định có getter thì luôn có setter

Ví dụ `getId()` có thể chỉ phục vụ hiển thị ID do hệ thống tạo, không có `setId(...)`. `isReadableProperty("id")` có thể `true` trong khi `isWritableProperty("id")` là `false`. Điều này có thể được dùng để tạo giao diện nội bộ chỉ đọc, nhưng UI vẫn cần chính sách quyền riêng.

### Lỗi 3 — dùng isWritableProperty để lọc bảo mật

Việc một property có setter không có nghĩa người dùng được phép đặt nó. Những field như `isAdmin`, `price`, `role` hoặc `ownerId` vẫn có thể có setter phục vụ logic nội bộ. Dùng DTO, allowlist và kiểm tra quyền cụ thể.

### Lỗi 4 — tưởng rằng isReadableProperty đã đọc nội dung

`isReadableProperty("name")` chỉ trả `true/false`, không trả tên của người dùng. Phải gọi `getPropertyValue("name")` nếu cần giá trị, và xử lý exception từ getter khi phù hợp.

### Lỗi 5 — mặc định mọi nested path đều hợp lệ

`"address.city"` phụ thuộc object `address`; `"items[5].name"` còn phụ thuộc collection và giới hạn index. Cần kiểm tra object graph và cấu hình; đừng dự đoán từ đường dẫn văn bản.

### Lỗi 6 — hiểu sai kiểu boolean

Getter `isActive()` thường cho property `active`. Nhưng một method thông thường như `hasToken()` không phải JavaBeans getter cho property `token`. Cách đặt tên và kiểu trả về phải tuân theo quy tắc introspection.

### Lỗi 7 — dùng cơ chế BeanWrapper cho mọi mô hình dữ liệu

Immutable DTO/record có thể không cung cấp setter. Spring có cơ chế constructor binding khác; không nên thêm setter vào immutable object chỉ để kết quả `isWritableProperty` thành `true`.

### Lỗi 8 — bỏ qua lỗi type conversion

`isWritableProperty("age") == true` không chứng minh chuỗi `"not-a-number"` có thể gán vào `int age`. Khi gọi `setPropertyValue(...)`, cần xử lý conversion lỗi; trong `DataBinder` thì truy vấn `BindingResult`.

## 10. Câu hỏi tự kiểm tra

1. Một JavaBean chỉ có `getOrderId()`, không có `setOrderId(...)`. Hai phương thức sẽ trả gì khi hỏi property `"orderId"`?
2. Nếu class chỉ khai báo `private String token` và `setToken(String)`, có đọc được `token` bằng `BeanWrapper#getPropertyValue` không?
3. Vì sao `isWritableProperty("address.city")` có thể phụ thuộc trạng thái `address` hiện tại?
4. Nếu `isWritableProperty("role")` trả `true` nhưng `role` không được phép gửi từ client, nên dùng thành phần nào để chặn trong Spring MVC?
5. `isReadableProperty("name")` và `getPropertyValue("name")` khác nhau ở đâu?
6. Một DTO `record` không có setter có nhất thiết không thể được tạo từ request? Hãy giải thích sự khác nhau giữa property binding và constructor binding.
7. Nếu getter/setter có tồn tại, thao tác đọc/ghi vẫn có thể lỗi trong những tình huống nào?

**Ghi nhớ:** `BeanWrapper.isReadableProperty(name)` và `isWritableProperty(name)` là hai phép thăm dò khả năng **đọc** và **ghi** property theo cơ chế truy cập của Spring. Chúng rất hữu ích khi xây tooling/mapping động, nhưng kết quả chỉ là metadata/accessibility; để thao tác thật cần `getPropertyValue`/`setPropertyValue`, và dữ liệu từ bên ngoài vẫn phải đi qua quy tắc bảo mật, conversion và validation.

## Tài liệu tham khảo chính thức

- Spring Framework Reference — Data Binding, Property Binding with BeanWrapper: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework Javadoc — PropertyAccessor: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/PropertyAccessor.html
- Spring Framework Javadoc — BeanWrapper: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/BeanWrapper.html
- Spring Framework Javadoc — BeanWrapperImpl: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/BeanWrapperImpl.html
- Spring Framework Javadoc — DataBinder: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework Javadoc — PropertyAccessorFactory: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/PropertyAccessorFactory.html