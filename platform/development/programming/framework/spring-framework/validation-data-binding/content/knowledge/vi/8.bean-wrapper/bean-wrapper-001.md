# Vai trò BeanWrapper trong truy cập thuộc tính JavaBean

## 1. BeanWrapper giải quyết vấn đề gì?

Một JavaBean có thể có nhiều thuộc tính với kiểu khác nhau. Khi viết Java thông thường, lập trình viên truy cập trực tiếp qua các phương thức kiểu an toàn:

~~~java
Customer customer = new Customer();
customer.setName("Mai");
String name = customer.getName();
~~~

Cách này rất tốt nếu tên property đã biết khi biên dịch. Tuy nhiên, Spring Framework còn xử lý những tình huống mà **tên thuộc tính đến từ cấu hình, metadata hoặc dữ liệu đầu vào**. Chẳng hạn, một form gửi cặp khóa–giá trị `name=Mai`, `age=27`, `address.city=Hue`. Hệ thống cần tìm đúng setter/getter, chuyển kiểu khi cần, hỗ trợ thuộc tính lồng nhau và báo lỗi nếu tên không hợp lệ.

**`org.springframework.beans.BeanWrapper`** là giao diện truy cập property dựa trên quy ước JavaBeans. **`BeanWrapperImpl`** là implementation phổ biến của Spring. Nó *bao bọc một object Java* và cho phép đọc, ghi, kiểm tra, mô tả các property bằng tên chuỗi như `"name"`, `"age"` hoặc `"address.city"`.

BeanWrapper là một khối nền tảng của hệ sinh thái Spring:

- `BeanFactory` dùng cơ sở hạ tầng thao tác property trong quá trình tạo và cấu hình Spring bean.
- `DataBinder` dùng cơ chế truy cập property để bind dữ liệu vào đối tượng khi chọn chế độ bean property access.
- `WebDataBinder` và Spring MVC dùng chức năng binding của `DataBinder`, ngoài những thành phần khác như conversion, validation và xử lý lỗi.
- Ứng dụng có thể dùng BeanWrapper trực tiếp khi thật sự cần đọc/ghi property động, nhưng phần lớn mã nghiệp vụ thông thường nên gọi getter/setter trực tiếp.

**Mục tiêu học tập:** hiểu JavaBeans property; dùng `BeanWrapperImpl` để đọc/ghi, introspection, nested/indexed/mapped paths và conversion; phân biệt với `DataBinder`, direct field access, constructor binding; xử lý lỗi và bảo vệ dữ liệu đầu vào. Các ví dụ chính dùng **Java 17 và Spring Framework 6.2.x**.

## 2. Property của JavaBean được xác định như thế nào?

Trong mô hình JavaBeans cổ điển, một property được mô tả bằng các phương thức theo quy ước đặt tên:

~~~java
public class Customer {
    private String name;
    private boolean active;

    public Customer() {}

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
}
~~~

Đối tượng `Customer` có các property `name` và `active`. Với JavaBeans introspection:

| Phương thức | Property | Ý nghĩa |
| --- | --- | --- |
| `getName()` | `name` | Đọc property |
| `setName(String)` | `name` | Ghi property |
| `isActive()` | `active` | Đọc boolean |
| `setActive(boolean)` | `active` | Ghi boolean |

Một **property** không đồng nhất với một **field**. Field `private String name` có thể không có getter/setter; trong trường hợp đó, truy cập JavaBeans thông thường không tự cho phép ghi vào field. Ngược lại, một property có thể được tính toán từ các field khác, ví dụ `getFullName()` ghép `firstName` và `lastName` dù không có field `fullName`.

Các phương thức ảnh hưởng khả năng truy cập:

- Chỉ có getter: property thường *read-only* đối với BeanWrapper; `getPropertyValue` có thể hoạt động nhưng `setPropertyValue` không thể gọi setter không tồn tại.
- Chỉ có setter: property *write-only* ở góc nhìn getter/setter chuẩn.
- Getter và setter hợp lệ: property có thể đọc và ghi.
- Không có accessor chuẩn: không thể mặc định dùng BeanWrapper như cơ chế đọc/ghi field trực tiếp.

BeanWrapper dựa trên JavaBeans introspection và metadata `java.beans.PropertyDescriptor`. Nó không lấy tên property bằng cách đơn giản loại bỏ tiền tố `private` của field.

## 3. Vị trí của BeanWrapper trong Spring

Những thành phần liên quan có vai trò khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| `BeanWrapper` | Giao diện đọc/ghi property JavaBeans, introspection, hỗ trợ đường dẫn lồng nhau và conversion |
| `BeanWrapperImpl` | Implementation mặc định, có cache metadata introspection |
| `PropertyAccessor` | Giao diện tổng quát đọc/ghi property theo tên; BeanWrapper mở rộng cơ chế này |
| `PropertyDescriptor` | Metadata một property: kiểu, getter/setter được nhận diện |
| `ConversionService` / `PropertyEditor` | Chuyển đổi giá trị đầu vào sang kiểu property |
| `DataBinder` | Điều phối binding, cấu hình allowed fields và thu thập binding errors |
| `BindingResult` | Chứa lỗi binding/validation và rejected values để controller xử lý |

Luồng khái quát khi Spring MVC xử lý form theo **property binding**:

~~~text
HTTP form/query values
    name=Mai
    age=27
    address.city=Hue
              |
              v
         DataBinder
       allowed/disallowed fields
              |
              v
    JavaBeans property access
         (BeanWrapper)
              |
    +---------+-----------+
    |         |           |
  metadata   conversion  nested paths
    |         |           |
    +---------+-----------+
              |
              v
         Customer object
              |
              v
    BindingResult + validation
              |
              v
           Controller
~~~

Đây là mô tả trách nhiệm, không phải danh sách các callback bắt buộc diễn ra theo đúng thứ tự tuyệt đối. Việc tạo model attribute, chuyển kiểu, gọi custom editor và validation còn phụ thuộc cấu hình cụ thể của MVC.

**Phân biệt quan trọng:** gọi `new BeanWrapperImpl(object)` và `setPropertyValue(...)` trực tiếp có thể ném exception; `DataBinder.bind(...)` là tầng cao hơn có thể tập hợp các lỗi chuyển kiểu vào `BindingResult` theo chiến lược binding của nó. Hai cách này không có cùng hợp đồng xử lý lỗi.

## 4. Chạy ví dụ Java 17+ hoàn chỉnh

Có thể tạo một dự án Gradle đơn giản để thấy cách BeanWrapper hoạt động mà không cần chạy web server.

### 4.1. Cấu hình `build.gradle`

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-beans:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.BeanWrapperDemo'
}
~~~

Đây là ví dụ dùng Spring Framework `6.2.14` để có kết quả tái lập. Trong dự án Spring Boot, nên để BOM/plugin của Boot quản lý phiên bản Spring thay vì tự ép một phiên bản riêng. Nếu đã có Gradle wrapper, dùng `./gradlew` hoặc `gradlew.bat`; nếu mới tạo project chưa có wrapper, tạo wrapper từ Gradle đã cài.

### 4.2. Tệp `src/main/java/demo/BeanWrapperDemo.java`

~~~java
package demo;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.MutablePropertyValues;

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

    public static class Customer {
        private String name;
        private Integer age;
        private Address address = new Address();
        private List<String> tags =
                new ArrayList<>(List.of("java", "spring"));
        private Map<String, String> attributes =
                new LinkedHashMap<>();

        public Customer() {}

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

        public List<String> getTags() {
            return tags;
        }

        public void setTags(List<String> tags) {
            this.tags = tags;
        }

        public Map<String, String> getAttributes() {
            return attributes;
        }

        public void setAttributes(Map<String, String> attributes) {
            this.attributes = attributes;
        }
    }

    public static void main(String[] args) {
        Customer customer = new Customer();
        BeanWrapper wrapper = new BeanWrapperImpl(customer);

        // Có thể gán nhiều property cùng lúc.
        wrapper.setPropertyValues(new MutablePropertyValues(
                Map.of("name", "Mai", "age", "27")
        ));

        // Đường dẫn lồng nhau, chỉ số list và khóa map.
        wrapper.setPropertyValue("address.city", "Hue");
        wrapper.setPropertyValue("tags[1]", "mvc");
        wrapper.setPropertyValue("attributes[locale]", "vi");

        System.out.println("sameObject=" +
                (wrapper.getWrappedInstance() == customer));
        System.out.println("name=" +
                wrapper.getPropertyValue("name"));
        System.out.println("age=" +
                wrapper.getPropertyValue("age"));
        System.out.println("city=" +
                wrapper.getPropertyValue("address.city"));
        System.out.println("tag=" +
                wrapper.getPropertyValue("tags[1]"));
        System.out.println("locale=" +
                wrapper.getPropertyValue("attributes[locale]"));
        System.out.println("writableAge=" +
                wrapper.isWritableProperty("age"));
        System.out.println("ageType=" +
                wrapper.getPropertyDescriptor("age")
                        .getPropertyType().getSimpleName());
    }
}
~~~

Chạy từ thư mục dự án:

~~~bash
./gradlew run
~~~

Trên Windows:

~~~powershell
.\gradlew.bat run
~~~

Ngoài các dòng thông tin do Gradle in ra, **stdout của chương trình Java** là:

~~~text
sameObject=true
name=Mai
age=27
city=Hue
tag=mvc
locale=vi
writableAge=true
ageType=Integer
~~~

Các chi tiết cần quan sát:

1. `getWrappedInstance() == customer` là `true`: wrapper thao tác **chính đối tượng đã truyền vào**, không cần sao chép đối tượng.
2. `setPropertyValues(...)` nhận nhiều giá trị, tìm các setter JavaBeans tương ứng.
3. `"27"` là `String` nhưng `Customer.age` là `Integer`; BeanWrapper dùng cơ chế conversion/editor tiêu chuẩn để gán được số 27.
4. `"address.city"` đi qua getter của `address` rồi setter của `city`.
5. `"tags[1]"` truy cập phần tử thứ hai của `List`; chỉ số bắt đầu từ 0.
6. `"attributes[locale]"` truy cập phần tử map với key `locale`.
7. `isWritableProperty("age")` kiểm tra khả năng ghi; `getPropertyDescriptor("age")` trả metadata `Integer`.

Ví dụ chủ động khởi tạo `address`, `tags` và `attributes`, vì vậy không phụ thuộc vào hành vi tự tạo đối tượng con khi gặp giá trị `null`.

## 5. Đọc, ghi và kiểm tra property bằng BeanWrapper

Nhóm API thường dùng:

~~~java
BeanWrapper wrapper = new BeanWrapperImpl(customer);

Object name = wrapper.getPropertyValue("name");
wrapper.setPropertyValue("name", "Lan");

boolean canRead = wrapper.isReadableProperty("name");
boolean canWrite = wrapper.isWritableProperty("name");

Class<?> type = wrapper.getPropertyType("age");
java.beans.PropertyDescriptor descriptor =
        wrapper.getPropertyDescriptor("age");
~~~

Đây là **đoạn minh họa** cần đặt trong method có biến `customer` hợp lệ, với các import tương ứng; không phải tệp Java độc lập.

- `getPropertyValue(path)` đọc theo property path; kiểu trả về chung là `Object` nên caller cần kiểm tra/cast khi thích hợp.
- `setPropertyValue(path, value)` tìm cách chuyển giá trị sang kiểu đích và gán theo setter/property path.
- `isReadableProperty(path)` / `isWritableProperty(path)` cho biết khả năng truy cập qua cơ chế JavaBeans.
- `getPropertyType(path)` cho biết kiểu property, có thể trả `null` trong một số trường hợp không xác định được kiểu; không nên coi kết quả luôn có giá trị.
- `getPropertyDescriptor(path)` lấy JavaBeans descriptor. Với implementation và phiên bản tương ứng, đường dẫn lồng nhau có thể được xử lý, nhưng API descriptor không nhằm diễn tả trực tiếp indexed/mapped entry như `tags[1]`.

### PropertyDescriptor dùng để làm gì?

Ví dụ:

~~~java
var descriptor = wrapper.getPropertyDescriptor("age");
System.out.println(descriptor.getName());           // age
System.out.println(descriptor.getPropertyType());   // class java.lang.Integer
System.out.println(descriptor.getReadMethod());     // getter metadata
System.out.println(descriptor.getWriteMethod());    // setter metadata
~~~

Đoạn này để minh họa introspection; kết quả `toString()` chính xác của `Method` phụ thuộc khai báo lớp, vì vậy không cung cấp stdout nguyên văn của hai dòng cuối.

Một framework tạo form động có thể dùng `PropertyDescriptor[]` để khám phá property được phép hiển thị. Tuy nhiên, **metadata đọc được không tự đồng nghĩa property ấy được phép nhận dữ liệu từ người dùng**. Quyền ghi phải do thiết kế DTO và chính sách binding quyết định.

### Không giống truy cập trực tiếp bằng reflection

Reflection có thể tìm và sửa field/method ở mức Java runtime. BeanWrapper cung cấp **quy ước JavaBeans + xử lý đường dẫn + chuyển đổi kiểu + introspection thuận tiện**. Trong property access mặc định, BeanWrapper thường gọi accessor method thích hợp; nó không đồng nghĩa với việc truy cập private field bằng `setAccessible(true)`.

Khi biết sẵn kiểu và tên property, `customer.setAge(27)` dễ đọc, dễ refactor và được compiler kiểm tra hơn `wrapper.setPropertyValue("age", 27)`. Chỉ dùng truy cập theo chuỗi khi bài toán thực sự cần xử lý động.

## 6. Đường dẫn lồng nhau, indexed và mapped

Spring hỗ trợ *property path* theo quy ước:

| Path | Ý nghĩa |
| --- | --- |
| `name` | Property trực tiếp |
| `address.city` | Property `city` của đối tượng `address` |
| `tags[0]` | Phần tử thứ nhất của list/array |
| `addresses[2].city` | `city` của phần tử thứ ba trong danh sách `addresses` |
| `attributes[locale]` | Giá trị của map tại key `locale` |
| `orders[0].items[1].quantity` | Truy cập kết hợp nhiều cấp |

Các path này không phải biểu thức Java được compiler kiểm tra. Mỗi phần phải tồn tại/đọc hoặc ghi được theo cấu trúc bean tương ứng, và container phải cho phép truy cập chỉ số/key đó.

Đường dẫn lồng nhau `address.city` hoạt động khi:

- `Customer.getAddress()` trả một `Address` hợp lệ;
- `Address` có `getCity()` và/hoặc `setCity(...)` cho thao tác muốn thực hiện;
- Chương trình có quyền truy cập method thông qua Java module/package theo cấu hình runtime.

Nếu `getAddress()` trả về `null`, BeanWrapper không thể tiếp tục đi xuống bằng getter theo cách thông thường. Cơ chế **auto-grow nested paths** có thể tạo object trung gian trong những điều kiện phù hợp:

~~~java
BeanWrapperImpl wrapper = new BeanWrapperImpl(customer);
wrapper.setAutoGrowNestedPaths(true);
wrapper.setAutoGrowCollectionLimit(32);
wrapper.setPropertyValue("address.city", "Hue");
~~~

Đây là **fragment**, giả định class `Address` có thể tạo instance theo cách Spring hỗ trợ và `customer` cho phép gán `address`. `setAutoGrowNestedPaths(true)` yêu cầu cố gắng tạo object cho các nhánh `null`; `setAutoGrowCollectionLimit(32)` giới hạn tự mở rộng array/collection để tránh việc một chỉ số lớn làm tiêu tốn tài nguyên. Không mặc định dựa vào cùng một giá trị auto-grow ở mọi API: `DataBinder` chuẩn có cấu hình mặc định riêng.

Không sử dụng auto-grow như giải pháp cho mọi thiết kế object: constructor bắt buộc tham số, quan hệ vòng, collection immutable và các kiểu không thể khởi tạo có thể khiến nó thất bại.

## 7. Chuyển đổi kiểu khi gán property

Form HTML thường gửi chuỗi. BeanWrapper có thể cần chuyển:

~~~text
"27"           -> Integer
"true"         -> Boolean
"ACTIVE"       -> Enum (với converter phù hợp)
"2026-11-02"   -> LocalDate (với formatter/converter phù hợp)
~~~

**Không nên cho rằng mọi conversion đều có sẵn trong một BeanWrapperImpl thuần.** BeanWrapper hỗ trợ `PropertyEditor` mặc định và có thể tích hợp `ConversionService`. Các định dạng như ngày tháng phụ thuộc registry/formatter thực tế được cài.

Ví dụ dùng `ConversionService` rõ ràng:

~~~java
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.core.convert.support.DefaultConversionService;

BeanWrapperImpl wrapper = new BeanWrapperImpl(customer);
wrapper.setConversionService(new DefaultConversionService());
wrapper.setPropertyValue("age", "27");
~~~

Fragment trên hoạt động trong ngữ cảnh đã có bean `customer` với setter `setAge(Integer)`. `DefaultConversionService` hỗ trợ nhiều conversion thường gặp; khi cần định dạng cụ thể của ngày tháng hoặc số theo locale, cần thêm `Formatter` / `FormattingConversionService` phù hợp.

Một lựa chọn cũ là đăng ký JavaBeans `PropertyEditor` cho loại property:

~~~java
wrapper.registerCustomEditor(
        java.time.LocalDate.class,
        new org.springframework.beans.propertyeditors.CustomDateEditor(
                new java.text.SimpleDateFormat("yyyy-MM-dd"), false)
);
~~~

**Đoạn trên không chính xác về kiểu đích nên không dùng làm cấu hình.** `CustomDateEditor` phục vụ `java.util.Date`, không phải `LocalDate`; nếu muốn xử lý `LocalDate`, hãy dùng converter/formatter tương ứng. Một ví dụ hợp lệ dành cho `java.util.Date`:

~~~java
wrapper.registerCustomEditor(
        java.util.Date.class,
        new org.springframework.beans.propertyeditors.CustomDateEditor(
                new java.text.SimpleDateFormat("yyyy-MM-dd"), false)
);
~~~

Hai đoạn này **chỉ minh họa sự khác biệt API**, không cùng dùng trong chương trình chạy ở mục 4. `SimpleDateFormat` là mutable và không thread-safe; custom editor dạng này nên nằm trong phạm vi binder/wrapper tương ứng, không chia sẻ đối tượng editor cho nhiều thread.

Trong ứng dụng Spring MVC hiện đại, thường ưu tiên `Converter`/`Formatter` và đăng ký ở `ConversionService`/`FormatterRegistry`. Ví dụ cho `LocalDate`, Spring MVC có hỗ trợ `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` trên property thích hợp khi binding form.

**Nguyên tắc:** BeanWrapper là người điều phối *đưa giá trị tới property theo kiểu mong đợi*; khả năng chuyển đổi cụ thể phụ thuộc cấu hình conversion/editor của wrapper hoặc binder.

## 8. Lỗi khi truy cập property trực tiếp

Khi gọi BeanWrapper trực tiếp, một tên path sai hoặc giá trị không hợp lệ có thể phát sinh exception. Những lỗi thường gặp:

| Trường hợp | Dấu hiệu / nhóm lỗi |
| --- | --- |
| Ghi vào property không tồn tại hoặc thiếu setter | `NotWritablePropertyException` |
| Đọc property không tồn tại hoặc thiếu getter | `NotReadablePropertyException` / `InvalidPropertyException` tùy tình huống |
| String không đổi được thành số đích | `TypeMismatchException` hoặc lỗi conversion được bọc tương ứng |
| Null tại một đoạn nested path | `NullValueInNestedPathException` nếu không được auto-grow |
| Chỉ số sai / cấu trúc property không phù hợp | Exception từ tầng property accessor, phụ thuộc kiểu container và path |

Không bắt toàn bộ lỗi rồi im lặng coi là input hợp lệ. Nếu dùng BeanWrapper như hạ tầng đọc/ghi **cấu hình nội bộ**, nên fail fast kèm tên property đã được kiểm duyệt, hoặc chuyển lỗi sang ngoại lệ miền phù hợp. Nếu dữ liệu đến từ request, `DataBinder` có cơ chế thu thập lỗi tốt hơn.

Ví dụ minh họa xử lý lỗi trực tiếp:

~~~java
try {
    wrapper.setPropertyValue("age", "khong-phai-so");
} catch (org.springframework.beans.BeansException ex) {
    System.out.println("Không thể gán property age");
}
~~~

Đây là fragment trong `main` đã có `wrapper`. Việc bắt `BeansException` ở đây chỉ để minh họa ranh giới lỗi; trong ứng dụng cần ghi chẩn đoán nội bộ phù hợp và không trả stack trace cho client.

## 9. Quan hệ giữa BeanWrapper và DataBinder

`DataBinder` là API ở tầng cao hơn khi cần **binding dữ liệu ngoài vào đối tượng**. Nó có thể thiết lập trường được phép, chuyển đổi, chính sách xử lý property không hợp lệ và kết quả lỗi.

Ví dụ sử dụng `DataBinder` bên ngoài MVC:

~~~java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

BeanWrapperDemo.Customer customer =
        new BeanWrapperDemo.Customer();

DataBinder binder = new DataBinder(customer, "customer");
binder.setAllowedFields("name", "age", "address.city");

MutablePropertyValues values = new MutablePropertyValues();
values.add("name", "Lan");
values.add("age", "not-a-number");
values.add("address.city", "Da Nang");
values.add("attributes[role]", "ADMIN");

binder.bind(values);

BindingResult result = binder.getBindingResult();
System.out.println(result.hasFieldErrors("age"));
System.out.println(result.getSuppressedFields().length);
~~~

Đây là **fragment**, chạy trong project có `spring-context`/`spring-beans` và class `Customer` ở mục 4. `DataBinder` thuộc module `spring-context`; chỉ dependency `spring-beans` ở `build.gradle` mục 4 **chưa đủ** cho phần này. Nếu muốn chạy fragment cùng ví dụ, bổ sung:

~~~groovy
dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}
~~~

Ý nghĩa:

- `setAllowedFields` chỉ cho phép các property `name`, `age`, `address.city` nhận input trong ví dụ.
- `age=not-a-number` không thể chuyển thành `Integer`, vì vậy `BindingResult` ghi field error.
- `attributes[role]` không nằm trong allowlist và bị loại khỏi lần bind, có thể xem qua `getSuppressedFields()`.
- Thông tin lỗi/suppressed field của binder khác với việc chỉ gọi `BeanWrapper#setPropertyValue` và tự bắt exception.

Trong một quá trình bình thường, `result.hasFieldErrors("age")` trả `true` và số suppressed field ở ví dụ là `1`. Nếu bind từ nhiều nguồn có field khác nhau hoặc thay đổi chính sách `allowedFields`, kết quả cần kiểm lại.

**BeanWrapper chỉ là một phần của cơ chế**: `DataBinder` còn giải quyết việc chuẩn hóa/loại bỏ field, lưu lỗi và tích hợp validation. Không viết code xử lý toàn bộ HTTP form bằng `new BeanWrapperImpl(entity)` nếu đã có binding lifecycle của Spring MVC.

## 10. BeanWrapper trong Spring MVC

Spring MVC có thể bind form vào model attribute bằng bean property access. Controller điển hình:

~~~java
import jakarta.validation.Valid;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@InitBinder("customer")
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("name", "age", "address.city");
}

@PostMapping("/customers")
String save(
        @Valid @ModelAttribute("customer") Customer customer,
        BindingResult result
) {
    if (result.hasErrors()) {
        return "customer-form";
    }
    return "success";
}
~~~

Đây là **fragment trong class `@Controller`**, không phải tệp biên dịch độc lập. `Customer` cần được import/khai báo, đồng thời Bean Validation provider phải hiện diện để `@Valid` kích hoạt validation theo các constraint trên DTO. Ví dụ `Customer` ở mục 4 chưa chứa annotation constraint; với class đó, `@Valid` không tự thêm lỗi nghiệp vụ nếu không có constraint khác.

Các điểm cần hiểu:

1. `WebDataBinder` được chuẩn bị cho một đối tượng cụ thể và có thể dùng property access giống BeanWrapper.
2. `@InitBinder` cung cấp chỗ cấu hình allowed fields, formatter hoặc custom editor **trước bước binding**.
3. Binding áp dụng giá trị request vào đối tượng; lỗi chuyển kiểu được ghi vào `BindingResult`.
4. `@Valid`/`@Validated` có thể kích hoạt validation sau binding, nếu có validator phù hợp.
5. `BindingResult` phải đặt **ngay sau** model attribute để controller tự xử lý lỗi; nếu không, Spring có thể ném exception tương ứng.

Từ Spring 6.1/6.2, cơ chế constructor binding cho model attribute cũng tồn tại. Một request DTO là Java record có thể được tạo qua constructor ngay cả khi không có setter. **Đừng suy luận rằng một record không setter được BeanWrapper property binding giống JavaBean truyền thống**. Constructor binding và BeanWrapper-style property binding là hai cơ chế cần phân biệt.

## 11. BeanWrapper, direct field access và constructor binding

Có ba cách xử lý giá trị đầu vào thường gây nhầm lẫn:

| Cách | Cơ chế | Tình huống phù hợp |
| --- | --- | --- |
| JavaBeans property access | Getter/setter, metadata property, BeanWrapper | DTO/bean mutable có accessor |
| Direct field access | Truy cập field, có thể không cần getter/setter | Đối tượng được thiết kế cho field binding, cấu hình có chủ đích |
| Constructor binding | Lấy giá trị theo tham số constructor rồi khởi tạo đối tượng | Record/immutable DTO, dữ liệu khởi tạo bắt buộc |

`DataBinder` mặc định dùng bean property access. Có thể chọn direct field access bằng `binder.initDirectFieldAccess()` khi thực sự cần. Khi đó Spring sử dụng cơ chế `DirectFieldAccessor`, không đi theo cùng quy tắc getter/setter của BeanWrapper.

Ví dụ fragment:

~~~java
DataBinder binder = new DataBinder(target);
binder.initDirectFieldAccess();
~~~

Đoạn này chỉ minh họa cấu hình; `target` cần có đối tượng phù hợp và import `org.springframework.validation.DataBinder`. Direct field access không có nghĩa là an toàn hơn hoặc phù hợp với mọi domain object. Đặc biệt, thay đổi field trực tiếp có thể bỏ qua invariant được thiết kế trong setter.

Với constructor binding, khai báo một record:

~~~java
public record RegistrationInput(String name, Integer age) {}
~~~

Trong Spring MVC, có thể sử dụng `@ModelAttribute RegistrationInput input` để tạo record từ các request parameters theo data constructor trong cấu hình/phiên bản hỗ trợ. Đây là một cách dựng đối tượng khác, chứ không phải BeanWrapper tìm setter trên record. Việc đặt `@Valid` vẫn cần cho validation của đối tượng khi handler mong muốn.

## 12. Bảo mật: property path không phải whitelist

BeanWrapper rất linh hoạt: nó có thể đi sâu vào các đối tượng lồng nhau và gán property có setter. Chính khả năng này đòi hỏi kiểm soát dữ liệu đầu vào.

**Không bao giờ biến một chuỗi property path do client tự chọn thành lệnh ghi tùy ý lên entity nghiệp vụ.** Ví dụ entity người dùng có các property `role`, `enabled` hoặc `ownerId`; nếu binding mọi field do client gửi, một request có thể tác động vào thuộc tính mà API không chủ đích cho phép.

Ưu tiên:

- **DTO đầu vào riêng** chỉ chứa field client được phép khai báo.
- `DataBinder#setAllowedFields(...)` để giới hạn property binding khi cần; đừng chỉ dùng `setDisallowedFields(...)` rồi cố liệt kê mọi property nguy hiểm có thể xuất hiện trong tương lai.
- **Constructor binding có kiểm soát** cho DTO bất biến; trong Spring 6.1+ có thể dùng `binder.setDeclarativeBinding(true)` để chỉ cho phép setter binding khi đã chỉ định `allowedFields` phù hợp.
- Validation về giá trị và quy tắc nghiệp vụ sau khi dữ liệu được bind.
- Phân quyền ở service/domain; hợp lệ về kiểu dữ liệu không đồng nghĩa với được phép thực hiện hành động.

Một điểm dễ bỏ qua: `isWritableProperty("role") == true` chỉ nói Spring thấy setter khả dụng; **không có nghĩa người dùng được phép thay đổi role**. Metadata về khả năng ghi của JavaBeans không phải chính sách authorization.

Với indexed property như `items[1000000]`, thiết kế cần xem xét auto-grow collection limit, độ lớn HTTP body và số lượng phần tử tối đa. Không cho phép client điều khiển tùy ý nested paths trên mô hình domain phức tạp.

## 13. Lưu ý về thread safety và vòng đời BeanWrapper

`BeanWrapperImpl` là một đối tượng thao tác **trạng thái của bean đang được bao bọc**, bao gồm conversion/editor configuration. Không nên mặc định dùng **cùng một instance BeanWrapper** như công cụ ghi dữ liệu cho nhiều request song song.

Cách sử dụng thông thường là tạo wrapper/binder theo đối tượng/lượt xử lý phù hợp. Metadata introspection được Spring tối ưu hóa và cache, nhưng điều đó **không biến bean đích mutable hoặc wrapper thành thread-safe**.

Nếu cần converter hoặc formatter dùng chung, hãy đánh giá thread safety của chúng. `ConversionService` được thiết kế cho việc tái sử dụng, nhưng các converter tùy chỉnh có thể có state mutable; JavaBeans `PropertyEditor` thường giữ trạng thái của lần chuyển đổi nên không nên chia sẻ bừa bãi giữa các thread.

BeanWrapper cũng không đảm bảo việc truy cập một chuỗi nested property path là thao tác atomic. Nếu một thread khác đang thay đổi cùng object graph, các getter/setter có thể quan sát trạng thái không nhất quán. Đối tượng chia sẻ cần cơ chế đồng bộ phù hợp ở tầng ứng dụng.

## 14. Kiểm thử hành vi BeanWrapper

Khi sử dụng BeanWrapper trong hạ tầng cấu hình động hoặc binding, nên kiểm thử các tình huống riêng:

1. Getter/setter có tên đúng và không có setter khi property cần read-only.
2. Property path đơn giản và nested, ví dụ `address.city`.
3. Indexed/mapped paths, ví dụ `tags[1]` và `attributes[locale]`.
4. Chuỗi có thể chuyển kiểu (`"27"` vào `Integer`) và không thể chuyển (`"abc"`).
5. Null ở giữa nested path, collection index vượt giới hạn và các trường hợp auto-grow.
6. Input chứa property không được phép (`role`, `enabled`) khi dùng `DataBinder`.
7. Model attribute có `BindingResult`, validation khi thêm `@Valid`/`@Validated`.
8. Một record không setter khi sử dụng constructor binding thay vì property binding.

Test JUnit sau là ví dụ thu gọn cho object ở mục 4. Trong dự án có JUnit Jupiter trên test classpath:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.NotWritablePropertyException;

import static org.junit.jupiter.api.Assertions.*;

class BeanWrapperDemoTest {

    @Test
    void readsAndWritesNestedJavaBeanProperties() {
        var customer = new BeanWrapperDemo.Customer();
        BeanWrapper wrapper = new BeanWrapperImpl(customer);

        wrapper.setPropertyValue("name", "Mai");
        wrapper.setPropertyValue("age", "27");
        wrapper.setPropertyValue("address.city", "Hue");

        assertEquals("Mai", customer.getName());
        assertEquals(27, customer.getAge());
        assertEquals("Hue", customer.getAddress().getCity());
        assertTrue(wrapper.isReadableProperty("age"));
        assertTrue(wrapper.isWritableProperty("age"));
    }

    @Test
    void rejectsUnknownWritableProperty() {
        BeanWrapper wrapper =
                new BeanWrapperImpl(new BeanWrapperDemo.Customer());

        assertThrows(NotWritablePropertyException.class,
                () -> wrapper.setPropertyValue(
                        "unknownProperty", "value"));
    }
}
~~~

Bổ sung vào `build.gradle` của project ở mục 4 khi muốn chạy test:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Sau đó chạy:

~~~bash
./gradlew test
~~~

Test này xác minh BeanWrapper đọc/ghi property và ném exception cho property không tồn tại. Nó **không thay thế** test `DataBinder`/Spring MVC; cần test tích hợp riêng nếu phần mềm nhận input từ HTTP.

## 15. Lỗi phổ biến và cách tránh

**Nhầm field với property:** Có `private String code` nhưng thiếu `getCode/setCode`; BeanWrapper property access không tự chuyển thành field access. Kiểm tra `PropertyDescriptor` và loại accessor đã cấu hình.

**Dùng sai tên property:** `getDisplayName()` tương ứng với `displayName`, không phải `display-name` trừ khi có cơ chế ánh xạ riêng ở tầng nhận input. Path là chuỗi nên compiler không phát hiện lỗi chính tả.

**Giả định wrapper tự tạo mọi nested object:** Nếu `address` null, truy cập `address.city` có thể lỗi. Khởi tạo đúng object graph hoặc cấu hình auto-grow một cách có kiểm soát.

**Coi conversion là validation:** `"27" -> Integer 27` chỉ là chuyển kiểu. Kiểm tra tuổi phải lớn hơn 18 là ràng buộc validation riêng, ví dụ `@Min(18)`.

**Mong BeanWrapper tự gom lỗi vào BindingResult:** Gọi `setPropertyValue` trực tiếp không có cùng hợp đồng lỗi như `DataBinder.bind`. Dùng `DataBinder` cho luồng binding từ input và kiểm tra `BindingResult`.

**Dùng BeanWrapper như trình thực thi biểu thức Java:** Các path tuân theo cú pháp property/index/map của Spring, không thực thi method tùy ý hay biểu thức tính toán như SpEL. `address.city` chỉ truy cập property, không phải `address.calculateCity()`.

**Dùng metadata là cơ chế bảo mật:** `isWritableProperty` không quyết định authorization. DTO/allowlist/phân quyền phải được xác định ở tầng phù hợp.

**Truy cập record bằng setter:** Record bất biến theo component, không có setter JavaBeans thông thường. Cần phân biệt constructor binding của MVC với property binding qua BeanWrapper.

**Chia sẻ mutable BeanWrapper giữa nhiều request:** Wrapper giữ target và configuration; không giả định mọi thao tác có thể chạy đồng thời trên cùng instance.

## 16. Ghi nhớ và đối chiếu API

BeanWrapper làm được bốn nhóm việc chính: **khám phá property** bằng metadata JavaBeans, **đọc/ghi theo tên** mà không cần biết getter/setter tại thời điểm biên dịch, **duyệt đường dẫn lồng nhau/index/map**, và **chuyển đổi giá trị** theo editor/conversion đã cấu hình.

Khi nhận input ngoài (HTTP form, configuration động), hãy dùng `DataBinder` hoặc cơ chế tích hợp của Spring MVC nếu cần thu thập lỗi, giới hạn field và validation. Khi đã biết tên property trong business code, dùng getter/setter trực tiếp để tận dụng kiểm tra kiểu của Java.

Tài liệu tham khảo chính thức:

- [Spring Framework 6.2 — Data Binding, BeanWrapper và ví dụ nested properties](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html)
- [Spring Framework — BeanWrapper API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanWrapper.html)
- [Spring Framework — BeanWrapperImpl API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanWrapperImpl.html)
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html)
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
