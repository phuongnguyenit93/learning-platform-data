# BeanWrapper: Đọc hoặc đặt nhiều giá trị thuộc tính trong Spring Framework

> **Phạm vi:** Spring Framework, nhóm `BeanWrapper`. Bài tập trung vào đọc nhiều property theo tên, ghi hàng loạt thông qua `PropertyValues`/`Map`, nested property, chuyển kiểu, hành vi khi lỗi và cách sử dụng an toàn. Ví dụ sử dụng Java 17 và Spring Framework 6.2.x.

## 1. Bài toán và cách BeanWrapper giải quyết

Giả sử ứng dụng có đối tượng `Customer` với những thuộc tính `name`, `age`, `active` và `address.city`. Dữ liệu từ một nguồn bên ngoài gồm:

```text
name         = "Linh"
age          = "28"
active       = "true"
address.city = "Đà Nẵng"
```

Bạn có thể gọi thủ công từng setter sau khi chuyển đổi kiểu. Nhưng khi một chương trình xử lý cấu hình hoặc map gồm nhiều thuộc tính, nó có thể không muốn viết mã cố định cho từng field. Spring cung cấp **`BeanWrapper`**, một giao diện thao tác với JavaBeans qua **tên property**.

Hai nhu cầu chính:

- **Đọc nhiều giá trị:** nhận danh sách tên property rồi lần lượt gọi `getPropertyValue(name)`, đưa kết quả vào một map có kiểm soát. `BeanWrapper` không có một phương thức `getPropertyValues()` đối xứng hoàn toàn với phương thức đặt nhiều giá trị.
- **Đặt nhiều giá trị:** chuẩn bị `Map` hoặc `PropertyValues`, rồi gọi `setPropertyValues(...)`. Spring cố gắng tìm setter/property path, chuyển đổi kiểu và gán các giá trị lên đối tượng đang được bọc.

`BeanWrapper` thao tác **trên đối tượng Java hiện có**. Nó không tự phân tích HTTP request, không tự kiểm tra quyền, không tự chạy toàn bộ Bean Validation, không tạo transaction và không thay thế tầng nghiệp vụ.

## 2. Các interface và class quan trọng

| Thành phần | Vai trò |
| --- | --- |
| `BeanWrapper` | Giao diện Spring Beans cho truy cập thuộc tính JavaBeans, xác định kiểu, getter/setter và nested path. |
| `BeanWrapperImpl` | Implementation thường dùng khi muốn bọc một instance và đọc/ghi property bằng tên. |
| `PropertyAccessor` | Định nghĩa `getPropertyValue`, `setPropertyValue`, `setPropertyValues` và các phương thức kiểm tra. |
| `PropertyValues` | Tập hợp các phần tử chứa tên/giá trị property; là đầu vào chuẩn cho bulk update. |
| `MutablePropertyValues` | Implementation có thể thêm/sửa các cặp property trước khi bind. |
| `PropertyValue` | Biểu diễn một cặp tên và giá trị riêng lẻ. |
| `PropertyBatchUpdateException` | Exception tập hợp lỗi property access trong quá trình batch update nếu là loại lỗi có thể gom lại. |
| `PropertyDescriptor` | Metadata JavaBeans: tên property và method đọc/ghi. |

Khởi tạo:

```java
Customer customer = new Customer();
BeanWrapper wrapper = new BeanWrapperImpl(customer);
```

`BeanWrapperImpl(customer)` bọc chính `customer`. Ghi property qua `wrapper` làm thay đổi cùng instance đó.

### JavaBeans property khác field trực tiếp

Với property `name`, cách truy cập JavaBeans thông thường dựa vào `getName()` và `setName(String)`. Một field `private` không có setter thích hợp không mặc nhiên ghi được chỉ vì Java reflection nhìn thấy nó.

`BeanWrapper` hỗ trợ nested property như `address.city`. Nó cũng hỗ trợ truy cập theo index/key tương ứng với các đối tượng collection/map được khai báo phù hợp.

## 3. Đọc một property với `getPropertyValue`

```java
Object a = wrapper.getPropertyValue("name");
Object b = wrapper.getPropertyValue("age");
Object c = wrapper.getPropertyValue("address.city");
```

Mỗi lời gọi đọc một property path. Kết quả được khai báo là `Object` và có thể là `null`. Nếu property đích kiểu `int`, giá trị trả về là số được boxing thành `Integer`. Với property không tồn tại hoặc không đọc được, Spring có thể báo `InvalidPropertyException` hoặc subclass phù hợp; với getter ném exception, có thể xuất hiện lỗi property access tương ứng.

Trước khi đọc, có thể hỏi wrapper:

```java
boolean readable = wrapper.isReadableProperty("name");
Class<?> type = wrapper.getPropertyType("age");
```

`isReadableProperty` hỏi có đường đọc property hợp lệ hay không. `getPropertyType` cung cấp kiểu property xác định được, nhưng không đọc giá trị. Kiểm tra trước giúp đưa lỗi rõ nghĩa hơn; trong môi trường mutable/concurrent vẫn phải xử lý lỗi xảy ra lúc truy cập thật.

## 4. Đọc nhiều property bằng một danh sách tên

`BeanWrapper` không tự trả về một map mọi property qua API tên `getPropertyValues()`. Cách rõ ràng nhất là chọn những field cần lấy và lặp:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

List<String> selected = List.of(
        "name", "age", "active", "address.city");

Map<String, Object> values = new LinkedHashMap<>();
for (String path : selected) {
    values.put(path, wrapper.getPropertyValue(path));
}
```

`LinkedHashMap` có hai lợi ích: giữ thứ tự danh sách tên và cho phép giá trị `null`. Không dùng `Map.of(...)` nếu bất kỳ property nào có thể là `null`.

Nếu tên property đến từ client, **không chuyển trực tiếp danh sách đó cho wrapper**. Hãy lọc danh sách theo allowlist, bởi JavaBean có thể chứa thông tin riêng tư mà client không được quyền đọc.

### Đọc các property được liệt kê bằng metadata

Khi xử lý một JavaBean không biết cấu trúc vào thời điểm biên dịch, có thể dùng `getPropertyDescriptors()`:

```java
import java.beans.PropertyDescriptor;
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Object> snapshot = new LinkedHashMap<>();
for (PropertyDescriptor descriptor
        : wrapper.getPropertyDescriptors()) {

    String property = descriptor.getName();
    if (!"class".equals(property)
            && wrapper.isReadableProperty(property)) {
        snapshot.put(property, wrapper.getPropertyValue(property));
    }
}
```

Đây chỉ là kỹ thuật introspection. **Không nên coi mọi getter là một trường công khai để trả về JSON hoặc log**: có getter nhạy cảm, tính toán tốn kém, có side effect hoặc trả về object graph lớn. `PropertyDescriptor` cũng không cam kết thứ tự nghiệp vụ. Trong API production, ưu tiên danh sách field tường minh hoặc DTO output.

**Lưu ý về tính nhất quán:** vòng lặp đọc nhiều property là nhiều thao tác nối tiếp, không phải một snapshot nguyên tử. Nếu các luồng khác sửa cùng bean, một map có thể chứa giá trị lấy ở những thời điểm khác nhau. Muốn ảnh chụp nhất quán phải dùng immutable snapshot/copy hoặc synchronization thích hợp.

## 5. Đặt từng property bằng `setPropertyValue`

```java
wrapper.setPropertyValue("name", "Linh");
wrapper.setPropertyValue("age", "28");
wrapper.setPropertyValue("active", "true");
```

Trong JavaBean phù hợp và với property editor/converter thích hợp, Spring có thể đổi chuỗi `"28"` thành `int 28` và `"true"` thành `boolean true`.

Một overload nhận `PropertyValue`:

```java
import org.springframework.beans.PropertyValue;

wrapper.setPropertyValue(
        new PropertyValue("name", "Linh"));
```

Hai cách này xử lý từng field. Nếu cần ghi nhiều field trong một thao tác API, dùng `setPropertyValues(...)`.

## 6. Đặt nhiều property bằng `MutablePropertyValues`

```java
import org.springframework.beans.MutablePropertyValues;

MutablePropertyValues updates = new MutablePropertyValues();
updates.add("name", "Linh");
updates.add("age", "28");
updates.add("active", "true");
updates.add("address.city", "Đà Nẵng");

wrapper.setPropertyValues(updates);
```

`MutablePropertyValues` chứa các phần tử tên/giá trị. Khi gọi `setPropertyValues`, wrapper xử lý tập giá trị trên target; property path dùng tên của JavaBean (`name`, `age`, `address.city`), không phải tên biến local hay tên một object trong MVC model.

Bạn cũng có thể dùng map trực tiếp:

```java
Map<String, Object> updates = new LinkedHashMap<>();
updates.put("name", "An");
updates.put("age", "30");

wrapper.setPropertyValues(updates);
```

| API | Ý nghĩa |
| --- | --- |
| `setPropertyValue("name", value)` | Một property. |
| `setPropertyValue(new PropertyValue(name, value))` | Một property được đóng gói. |
| `setPropertyValues(Map<?, ?>)` | Bulk update thuận tiện từ map. |
| `setPropertyValues(PropertyValues)` | Bulk update bằng cấu trúc `PropertyValues` được API ưu tiên. |
| `setPropertyValues(pvs, ignoreUnknown)` | Có chính sách bỏ qua key không tồn tại. |
| `setPropertyValues(pvs, ignoreUnknown, ignoreInvalid)` | Thêm chính sách về property path không truy cập được. |

Cả hai cách `Map` và `MutablePropertyValues` đều có thể cập nhật nhiều trường. Chọn `PropertyValues` khi cần phối hợp với API khác của Spring vốn nhận `PropertyValues`, hoặc muốn điều khiển từng `PropertyValue`. Chọn map khi nguồn dữ liệu đã có sẵn dưới dạng map, nhưng luôn lọc key được phép.

## 7. Ví dụ Java 17 có thể chạy với Maven

Ví dụ sau dùng Spring Beans, không cần Spring MVC và không cần khởi động Spring Boot. Tạo:

```text
beanwrapper-bulk-demo/
  pom.xml
  src/main/java/demo/BeanWrapperBulkDemo.java
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>beanwrapper-bulk-demo</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/java/demo/BeanWrapperBulkDemo.java`

```java
package demo;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.MutablePropertyValues;

public final class BeanWrapperBulkDemo {

    public static final class Address {
        private String city;

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }

    public static final class Customer {
        private String name;
        private int age;
        private boolean active;
        private Address address = new Address();

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }

        public int getAge() { return age; }
        public void setAge(int age) { this.age = age; }

        public boolean isActive() { return active; }
        public void setActive(boolean active) { this.active = active; }

        public Address getAddress() { return address; }
        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public static void main(String[] args) {
        Customer customer = new Customer();
        BeanWrapper wrapper = new BeanWrapperImpl(customer);

        MutablePropertyValues changes = new MutablePropertyValues();
        changes.add("name", "Linh");
        changes.add("age", "28");
        changes.add("active", "true");
        changes.add("address.city", "Đà Nẵng");

        // Đặt bốn giá trị trong một lần gọi.
        wrapper.setPropertyValues(changes);

        // Đọc lại chính bốn property đó theo tên.
        List<String> keys = List.of(
                "name", "age", "active", "address.city");
        Map<String, Object> snapshot = new LinkedHashMap<>();
        for (String key : keys) {
            snapshot.put(key, wrapper.getPropertyValue(key));
        }

        System.out.println("sameObject="
                + (wrapper.getWrappedInstance() == customer));
        snapshot.forEach((key, value) ->
                System.out.println(key + "=" + value));
        System.out.println("ageType="
                + wrapper.getPropertyType("age").getSimpleName());
        System.out.println("cityWritable="
                + wrapper.isWritableProperty("address.city"));
    }
}
```

Trong thư mục `beanwrapper-bulk-demo`, chạy với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BeanWrapperBulkDemo
```

**Stdout từ chương trình** (không tính các log riêng của Maven nếu cấu hình hiển thị khác):

```text
sameObject=true
name=Linh
age=28
active=true
address.city=Đà Nẵng
ageType=int
cityWritable=true
```

Các điểm cần quan sát:

1. `getWrappedInstance() == customer` là `true`: wrapper đang thao tác trên chính instance đã truyền vào.
2. `age` và `active` có kiểu `int`/`boolean`; giá trị chuỗi ban đầu đã được chuyển sang kiểu đích.
3. `address.city` đi qua getter `getAddress()` và setter `setCity(...)` của nested bean.
4. `getPropertyValue(...)` trả lại giá trị đã gán, còn `LinkedHashMap` giữ thứ tự in.
5. `isWritableProperty("address.city")` kiểm tra đường dẫn hiện có và có thể ghi.

**Chương trình trên cần dependency `spring-beans`**; chỉ dùng lệnh `javac` không có classpath Spring sẽ không biên dịch được. Các snippet khác trong bài chủ yếu minh họa cách dùng API bên trong ứng dụng và cần biến `wrapper`/`pvs` đã được khai báo.

## 8. Nested, indexed và mapped property

`BeanWrapper` sử dụng property path:

| Path | Cách hiểu |
| --- | --- |
| `name` | Property trực tiếp. |
| `address.city` | `city` của nested bean `address`. |
| `addresses[0].city` | `city` của phần tử đầu tiên thuộc array/list `addresses`. |
| `phones[1]` | Phần tử index 1 của collection theo thứ tự có hỗ trợ index. |
| `attributes[department]` | Key `department` của một map property `attributes`. |

Đường dẫn chỉ hợp lệ khi target thật có cấu trúc/kiểu tương ứng. Dùng path lồng nhau không đồng nghĩa JavaBean luôn tự có nested object.

### Nested object đang null

Nếu `getAddress() == null`, đọc hoặc ghi `address.city` có thể gây `NullValueInNestedPathException`. Với một plain property accessor, auto-grow nested paths thông thường mặc định **tắt**.

Bạn có thể cấu hình:

```java
wrapper.setAutoGrowNestedPaths(true);
wrapper.setPropertyValue("address.city", "Huế");
```

Cơ chế auto-grow có thể tạo object trung gian nếu kiểu và constructor của nó hỗ trợ. Không phải path nào cũng có thể tạo tự động. Với dữ liệu người dùng không tin cậy, không tùy tiện bật auto-grow rồi nhận mọi path; nó có thể mở rộng object graph ngoài dự kiến.

Ví dụ đầy đủ đã khởi tạo sẵn `new Address()`, nên không cần auto-grow.

## 9. Lỗi bulk update và tính không nguyên tử

**Đây là khác biệt quan trọng nhất so với tưởng tượng “set nhiều trường trong một transaction”:** `setPropertyValues(...)` không bảo đảm all-or-nothing.

Theo Javadoc của `PropertyAccessor`, khi batch gặp lỗi có thể phục hồi như conversion/type mismatch, Spring có thể tiếp tục cập nhật một số property khác, sau đó ném `PropertyBatchUpdateException` gom các lỗi `PropertyAccessException`. Những field gán thành công **có thể đã thay đổi trên target**.

Ví dụ về trạng thái:

```text
Trước:  name="Cũ", age=18, active=false
Gửi:    name="Mới", age="abc", active="true"

name  -> có thể được gán thành công
age   -> không convert thành int
active-> có thể tiếp tục được gán

Kết quả: batch báo lỗi, nhưng một số field đã đổi.
```

Đoạn xử lý lỗi (minh họa trong hàm đã có `wrapper` và `pvs`):

```java
import org.springframework.beans.PropertyAccessException;
import org.springframework.beans.PropertyBatchUpdateException;

try {
    wrapper.setPropertyValues(pvs);
} catch (PropertyBatchUpdateException ex) {
    for (PropertyAccessException error
            : ex.getPropertyAccessExceptions()) {
        System.out.println("Field: " + error.getPropertyName());
        System.out.println("Type: "
                + error.getClass().getSimpleName());
    }
    // Không tiếp tục lưu target như thể toàn bộ batch hợp lệ.
}
```

Đừng suy ra **mọi loại lỗi** đều được gom trong exception này. Property không tồn tại hoặc không ghi được có thể gây `InvalidPropertyException` / `NotWritablePropertyException` và khiến batch dừng tùy trường hợp; getter/setter có thể ném lỗi khác.

### Khi cần all-or-nothing

Một quy trình an toàn hơn:

1. Kiểm tra danh sách field được phép, parse/conversion và validation trên một DTO hoặc bản sao tạm.
2. Nếu có lỗi, trả kết quả mà không thay đổi domain object gốc.
3. Nếu tất cả hợp lệ, áp dụng các thay đổi vào domain theo use case đã kiểm soát.
4. Với thao tác lưu nhiều bản ghi, dùng transaction/locking thích hợp ở DB. BeanWrapper tự nó không thay được transaction.

Không gọi lại `setPropertyValues` trên cùng một đối tượng đã cập nhật dở mà không hiểu trạng thái hiện tại.

## 10. Các overload bỏ qua unknown/invalid field

`PropertyAccessor` cho phép:

```java
wrapper.setPropertyValues(pvs);
wrapper.setPropertyValues(pvs, true);
wrapper.setPropertyValues(pvs, false, true);
wrapper.setPropertyValues(pvs, true, true);
```

Trong overload ba tham số:

- Tham số thứ hai `ignoreUnknown`: cho phép bỏ qua tên property không tìm thấy trong bean.
- Tham số thứ ba `ignoreInvalid`: cho phép bỏ qua một số property path đã biết nhưng không truy cập được, ví dụ nested path thiếu object trung gian, theo khả năng của implementation.

| Tình huống | Quyết định |
| --- | --- |
| `nmae` bị gõ sai thay vì `name` | Thường nên báo lỗi để phát hiện sai contract. |
| Field tùy chọn không có trong phiên bản DTO cũ | `ignoreUnknown` có thể hữu ích nếu được phép theo hợp đồng. |
| Nested object `address` đang `null` | Khởi tạo rõ ràng hoặc áp dụng chính sách ignore/auto-grow phù hợp. |
| `age="xyz"` không chuyển được kiểu | Không phải unknown property; xử lý như conversion error. |
| Field read-only | Không thể ghi chỉ vì tên property tồn tại. |

Không lạm dụng `ignoreUnknown=true` làm cơ chế “nhận dữ liệu nào cũng được”. Nó có thể che lỗi đánh máy, xung đột phiên bản API và dữ liệu bị bỏ qua âm thầm. Các cờ cũng không có nghĩa bỏ qua mọi lỗi hay có rollback.

## 11. Chuyển kiểu khi ghi nhiều property

`BeanWrapperImpl` có các property editor mặc định và có thể dùng conversion service đã cấu hình. Với JavaBean trong ví dụ, chuỗi `"28"` và `"true"` được chuyển thành `int` và `boolean`.

| Input | Target type | Hành vi cần mong đợi |
| --- | --- | --- |
| `"28"` | `int` | Convert sang `28`. |
| `"false"` | `boolean` | Convert sang `false`, không xem như thiếu. |
| `"abc"` | `int` | Báo lỗi chuyển kiểu. |
| `"2026-11-02"` | `LocalDate` | Phụ thuộc converter/formatter cấu hình; không giả định mọi format luôn được hỗ trợ. |
| `"1,234.50"` | `BigDecimal` | Cần quy định locale/format và converter phù hợp. |

Nếu cần conversion service chuẩn:

```java
import org.springframework.core.convert.support.DefaultConversionService;

wrapper.setConversionService(new DefaultConversionService());
```

Đây là snippet giả định wrapper đã được tạo. Với kiểu đặc thù, định dạng số, tiền tệ, thời gian hoặc type domain, cần formatter/converter riêng phù hợp.

**Chuyển kiểu thành công không đồng nghĩa giá trị hợp lệ.** `age="-5"` có thể chuyển thành số `-5`, nhưng nghiệp vụ vẫn cần từ chối nếu tuổi phải không âm. `BeanWrapper` không tự chạy mọi constraint Jakarta Bean Validation.

## 12. Kiểm tra khả năng đọc, ghi và kiểu property

Ba API quan trọng:

```java
boolean canRead = wrapper.isReadableProperty("name");
boolean canWrite = wrapper.isWritableProperty("age");
Class<?> type = wrapper.getPropertyType("age");
```

- `isReadableProperty(...)` xác nhận đường đọc property được bean metadata hỗ trợ.
- `isWritableProperty(...)` xác nhận đường ghi property được hỗ trợ.
- `getPropertyType(...)` cung cấp kiểu đã khai báo có thể xác định.

Một JavaBean có `getId()` nhưng không có `setId(...)` có thể **đọc được, không ghi được**. Một property chỉ có setter có thể **ghi được, không đọc được**. Cũng phải xét object trung gian của nested paths.

Đừng dùng kết quả `isWritableProperty` để thay thế authorization. “Có setter” không có nghĩa người dùng được quyền cập nhật. Tương tự, `isReadableProperty` không đồng nghĩa property an toàn để công khai.

## 13. Kết hợp với DataBinder và Spring MVC

`BeanWrapper` là mức thao tác thấp. `DataBinder` bổ sung khả năng điều phối binding vào target và tích lũy lỗi trong `BindingResult`:

| Cần làm | BeanWrapper | DataBinder |
| --- | --- | --- |
| Đọc property theo tên | `getPropertyValue` | Không phải mục đích API trực tiếp chính. |
| Ghi hàng loạt | `setPropertyValues` | `bind(PropertyValues)`. |
| Lỗi chuyển kiểu | Ném exception, có thể gom `PropertyBatchUpdateException`. | Ghi lỗi vào `BindingResult` theo cơ chế binding. |
| Chỉ cho phép các field nhất định | Lọc key trước khi gọi wrapper. | `setAllowedFields(...)`. |
| Validation | Phải tổ chức riêng. | Có API đặt validator và gọi `validate()`; MVC có lifecycle riêng. |

Nếu nguồn là HTTP request trong Spring MVC, thường nên sử dụng `@ModelAttribute`/`@RequestBody`, DTO và binding/validation do framework quản lý. Không cần tự tạo BeanWrapper chỉ vì request có nhiều field.

Nếu tự xây dựng pipeline ánh xạ map→JavaBean ngoài MVC (ví dụ importer cấu hình), `BeanWrapperImpl` phù hợp khi bạn thực sự cần lookup property theo tên và chuyển đổi kiểu linh hoạt.

## 14. Bảo mật: không bind bừa mọi field từ client

Vấn đề thường gọi là **mass assignment**. Nếu đối tượng có các field `role`, `isAdmin`, `ownerId` hoặc `creditLimit` và chúng có setter, một map từ client có thể thử ghi chúng bằng `setPropertyValues(...)`.

Đặt một allowlist:

```java
import java.util.Set;
import org.springframework.beans.MutablePropertyValues;

// input: Map<String, ?> đến từ một nguồn đã biết.
// wrapper: BeanWrapper bọc một DTO phù hợp.
Set<String> allowed =
        Set.of("name", "age", "address.city");
MutablePropertyValues accepted = new MutablePropertyValues();

for (var entry : input.entrySet()) {
    String field = entry.getKey();
    if (!allowed.contains(field)) {
        throw new IllegalArgumentException(
                "Unsupported property: " + field);
    }
    accepted.add(field, entry.getValue());
}
wrapper.setPropertyValues(accepted);
```

Đoạn này chỉ minh họa cơ chế allowlist, cần đặt trong context có `input` và `wrapper`. Nó chưa thay validation, quyền thao tác, kiểm tra nested path/index và xử lý các exception của batch.

Các biện pháp cần phối hợp:

1. Dùng **input DTO** với đúng field được phép; tránh bind trực tiếp entity.
2. Duyệt danh sách field cho phép trước khi tạo `PropertyValues`.
3. Không cho client tự tạo các property path sâu/array indexes tùy ý.
4. Giới hạn kích thước input và object graph.
5. Sau binding, validate giá trị và kiểm tra business rules.
6. Không xuất mọi property qua reflection ra API hoặc log.

## 15. Đọc/ghi hàng loạt với cập nhật một phần

Trong update hoặc PATCH, cần phân biệt:

- **Key không có mặt:** thường giữ nguyên giá trị cũ.
- **Key có mặt với `null`:** có thể yêu cầu xóa trường hoặc là dữ liệu không hợp lệ.
- **Key có mặt với `""`:** là chuỗi rỗng, không tự đồng nhất với thiếu.
- **Key có giá trị `0` hoặc `false`:** có thể là lựa chọn hợp lệ và phải được giữ.

Một `Map` dùng cho `setPropertyValues(...)` nên chỉ chứa những key thực sự được phép thay đổi. Nếu trước đó đã đặt giá trị mặc định cho mọi field một cách không chủ ý, việc bind có thể làm hỏng trạng thái sẵn có.

Nếu cần so sánh trước–sau, phải chụp ảnh các giá trị cần so sánh **trước khi ghi**. Vì wrapper bọc cùng object mutable, giữ tham chiếu `Customer old = customer` rồi thay đổi qua wrapper không tạo được snapshot trước cập nhật.

## 16. Kiểm thử và lỗi thiết kế phổ biến

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Đọc `name` và `age` theo danh sách | Map có đúng tên và giá trị. |
| `setPropertyValues` từ `MutablePropertyValues` | Các field hợp lệ được cập nhật. |
| `setPropertyValues(Map)` | Kết quả tương đương với tập tên–giá trị. |
| `age="28"` | Chuyển thành `int 28`. |
| `age="abc"` | Lỗi type mismatch; không được báo thành công. |
| Batch gồm field tốt và field sai | Có thể cập nhật một phần; kiểm tra cả exception và trạng thái bean. |
| Nested `address.city` khi `address` có sẵn | Đọc/ghi thành công. |
| Nested `address.city` khi `address==null` | Xem cơ chế auto-grow/exception và không giả định luôn thành công. |
| Property không tồn tại | Lỗi theo mặc định hoặc được bỏ qua khi dùng `ignoreUnknown`. |
| Property chỉ có getter | `isWritableProperty` là false, không ghi được. |
| Input có key `role` ngoài allowlist | Phải bị từ chối trước binding. |
| Getter trả về dữ liệu nhạy cảm | Không xuất qua bulk-read API. |

Các lỗi cần tránh:

**Nhầm 1:** Mong đợi có `getPropertyValues()` để lấy hết field. Hãy lặp `getPropertyValue(name)` hoặc lấy metadata rồi lọc.

**Nhầm 2:** Cho rằng `setPropertyValues(...)` cập nhật nguyên tử. Không có rollback tự động cho JavaBean.

**Nhầm 3:** Dùng field private không có setter mà tưởng BeanWrapper luôn ghi được. Phải hiểu JavaBeans property accessor.

**Nhầm 4:** Dùng `ignoreUnknown` để che lỗi chính tả hoặc data contract.

**Nhầm 5:** Bind object từ client trực tiếp lên entity hoặc property đặc quyền mà không kiểm soát field.

**Nhầm 6:** Quên rằng `address.city` cần nested object tồn tại hoặc chính sách auto-grow phù hợp.

**Nhầm 7:** Tin type conversion tự động đáp ứng mọi định dạng ngày giờ, tiền tệ và dữ liệu domain.

**Nhầm 8:** Coi chuyển kiểu thành công là validation nghiệp vụ thành công.

**Nhầm 9:** Chia sẻ một wrapper mutable trên nhiều request/luồng để ghi vào cùng đối tượng mà không có cơ chế nhất quán.

**Nhầm 10:** Dùng property binding vào record/immutable DTO như thể nó có setters. Với immutable object, cần cơ chế constructor mapping/binding phù hợp.

## 17. Checklist vận dụng

1. Xác định instance JavaBean cần thao tác và tạo `BeanWrapperImpl(target)`.
2. Nếu **đọc nhiều giá trị**, chuẩn bị danh sách tên property đáng tin cậy; lặp `getPropertyValue` và lưu vào `LinkedHashMap` nếu cần.
3. Nếu **đặt nhiều giá trị**, chuẩn bị `MutablePropertyValues` hoặc `Map` đã lọc key.
4. Kiểm tra tên property, writable/readable metadata và nested paths.
5. Cấu hình converter/formatter trước khi ghi nếu property có kiểu đặc thù.
6. Gọi `setPropertyValues` và xử lý các lỗi có thể làm bean thay đổi một phần.
7. Validate kết quả, áp dụng business rules, và lưu trữ qua transaction thích hợp nếu cần.
8. Chỉ đọc/ghi field mà người dùng hoặc nguồn dữ liệu thật sự được quyền truy cập.

**Điểm nhớ:** `getPropertyValue(name)` đọc **một** property; muốn đọc nhiều thì **lặp có chọn lọc**. `setPropertyValues(...)` đặt **nhiều** property; nó cung cấp conversion và thông tin lỗi, **không bảo đảm all-or-nothing**.

## Tham khảo API chính thức

- [Spring Framework Reference – Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework 6.2.14 – AbstractPropertyAccessor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/AbstractPropertyAccessor.html): các overload `setPropertyValues` và hành vi lỗi batch.
- [Spring Framework 6.0.23 – BeanWrapperImpl](https://docs.spring.io/spring-framework/docs/6.0.23/javadoc-api/org/springframework/beans/BeanWrapperImpl.html): implementation và constructor.
- [Spring Framework 6.2.14 – BeanWrapper](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/beans/BeanWrapper.html): API của wrapper và property metadata.
