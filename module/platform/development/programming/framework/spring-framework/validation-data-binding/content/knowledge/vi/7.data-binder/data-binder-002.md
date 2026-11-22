# PropertyValue, PropertyValues và MutablePropertyValues trong Spring DataBinder

Khi cần đưa nhiều cặp **tên thuộc tính → giá trị** vào một Java object, Spring Framework sử dụng ba kiểu thuộc package `org.springframework.beans`:

- **`PropertyValue`**: mô tả **một** giá trị được đề nghị gán cho một property, gồm tên và giá trị.
- **`PropertyValues`**: interface đại diện cho **tập các `PropertyValue`**, cho phép duyệt, tìm, kiểm tra sự tồn tại và so sánh những giá trị được cung cấp.
- **`MutablePropertyValues`**: cách triển khai phổ biến của `PropertyValues`, cho phép **thêm, thay thế, xóa** các mục và có thể truyền trực tiếp vào `DataBinder.bind(...)`.

Trong luồng data binding, chúng đóng vai trò **vật chứa dữ liệu đầu vào**. Chính `DataBinder` và hệ thống truy cập property/conversion của Spring mới quyết định trường nào được gán, chuyển kiểu ra sao và có lỗi gì. Tạo `MutablePropertyValues` **chưa tự động sửa JavaBean**.

## 1. Bức tranh tổng thể

Giả sử request form có ba tham số:

~~~http
POST /registrations
Content-Type: application/x-www-form-urlencoded

name=Lan&age=23&admin=true
~~~

Để dễ hiểu, có thể hình dung phần đầu vào như sau:

~~~text
                         tên                 giá trị ban đầu
                    ┌────────────────┬──────────────────────┐
                    │ "name"         │ "Lan"                │
PropertyValues ──── │ "age"          │ "23"                 │
                    │ "admin"        │ "true"               │
                    └────────────────┴──────────────────────┘
                           |
                           v
                 DataBinder + cấu hình
                 ├─ allowed fields
                 ├─ chuyển String → int
                 ├─ gán qua setter
                 └─ BindingResult
                           |
                           v
                 RegistrationForm bean
                 name = "Lan", age = 23
                 admin = false (bị chặn)
~~~

Đây là **sơ đồ khái niệm**, không phải cam kết rằng HTTP luôn trực tiếp tạo một `MutablePropertyValues` theo đúng cách này. Trong Spring MVC, `WebDataBinder` và các lớp nhận tham số request điều phối quá trình ấy. Với Java thuần, ta có thể tự xây `MutablePropertyValues` rồi gọi `DataBinder.bind(...)`.

**Hai ranh giới quan trọng:**

1. `PropertyValues` chứa **các đề nghị gán**, bao gồm cả giá trị thô `"23"` dạng `String`.
2. Đối tượng đích chỉ được cập nhật **khi áp dụng binding**; nếu property cần `int` thì bộ chuyển đổi kiểu thực hiện việc chuyển `"23"` → `23`. Bản thân `PropertyValue` không bảo đảm đã chuyển kiểu.

## 2. PropertyValue — một cặp tên và giá trị

Một `PropertyValue` được tạo bằng:

~~~java
import org.springframework.beans.PropertyValue;

PropertyValue pv = new PropertyValue("age", "23");

System.out.println(pv.getName());                 // age
System.out.println(pv.getValue());                // 23 (vẫn là String)
System.out.println(pv.getValue() instanceof String); // true
~~~

Đây là **đoạn trích**, muốn chạy cần đặt trong method và có Spring `spring-beans` trên classpath. Hai tham số constructor là:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `name` | Tên property hoặc đường dẫn property đích | `"age"`, `"address.city"` |
| `value` | Đối tượng giá trị cần áp dụng, có thể chưa chuyển kiểu | `"23"`, `Integer.valueOf(23)` |
| `getName()` | Trả tên property | `"age"` |
| `getValue()` | Trả giá trị thô đã cung cấp | `"23"` |

`PropertyValue` có thêm constructor copy `new PropertyValue(existing)` và constructor liên kết với giá trị mới `new PropertyValue(existing, newValue)`, hữu ích trong các cơ chế nội bộ cần theo dõi nguồn gốc giá trị.

Một số thuộc tính/phương thức chuyên sâu như `setOptional(boolean)`, `isOptional()`, `setConvertedValue(...)` hay `getConvertedValue()` phục vụ quá trình truy cập và chuyển đổi property. Chúng **không** có nghĩa chỉ cần gọi `setOptional(true)` là có thể bỏ qua kiểm tra phân quyền hoặc validation. Phần lớn mã ứng dụng chỉ cần constructor và hai getter.

**Đừng nhầm:** `new PropertyValue("age", "23")` không gọi `setAge(...)` trên bất kỳ object nào. Nó chỉ tạo một mô tả giá trị để một công cụ khác xử lý sau.

## 3. PropertyValues — hợp đồng của một tập giá trị

`PropertyValues` là một **interface**, không phải class để gọi `new PropertyValues()`. Nó mở rộng `Iterable<PropertyValue>` và cung cấp các thao tác đọc/tìm kiếm tiêu biểu:

| API | Kết quả |
| --- | --- |
| `getPropertyValues()` | Mảng `PropertyValue[]` đại diện các mục đang chứa |
| `getPropertyValue("age")` | `PropertyValue` có tên tương ứng, hoặc `null` nếu không tìm thấy |
| `contains("age")` | Kiểm tra có mục hay thông tin xử lý tương ứng tên đó |
| `isEmpty()` | Tập mục có rỗng không |
| `iterator()`, `stream()` | Duyệt/stream các mục |
| `changesSince(old)` | Tập giá trị **mới hoặc đã thay đổi** so với bản cũ |

Ví dụ:

~~~java
PropertyValues values = new MutablePropertyValues()
        .add("name", "Lan")
        .add("age", "23");

System.out.println(values.contains("age")); // true
System.out.println(values.isEmpty());       // false

for (PropertyValue pv : values) {
    System.out.println(pv.getName() + "=" + pv.getValue());
}
~~~

Các lệnh trên là **đoạn trích bên trong method** với import `PropertyValue`, `PropertyValues` và `MutablePropertyValues`. Trong một implementation như `MutablePropertyValues`, mỗi property name thường có một mục; thêm lại cùng tên sẽ thay giá trị tương ứng (hoặc thực hiện quy tắc merge khi được cấu hình).

**Lưu ý về kiểu interface:** đặt biến là `PropertyValues` giúp code chỉ phụ thuộc hợp đồng đọc và tra cứu, nhưng không biến object thực tế thành bất biến. Nếu implementation thực tế vẫn là `MutablePropertyValues` và nơi khác giữ cùng tham chiếu, dữ liệu có thể bị thay đổi. Muốn lưu snapshot tách biệt, tạo `new MutablePropertyValues(original)`; ngay cả constructor này cũng không deep-copy mọi object lồng trong các giá trị.

## 4. MutablePropertyValues — tập giá trị có thể chỉnh sửa

`MutablePropertyValues` là implementation mặc định/thông dụng của `PropertyValues`. Các cách khởi tạo:

~~~java
MutablePropertyValues empty = new MutablePropertyValues();

MutablePropertyValues fromMap = new MutablePropertyValues(
        java.util.Map.of("name", "Lan", "age", "23"));

MutablePropertyValues copy = new MutablePropertyValues(fromMap);
~~~

Có thể thêm từng cặp bằng API trả lại chính holder:

~~~java
MutablePropertyValues pvs = new MutablePropertyValues()
        .add("name", "Lan")
        .add("age", "23")
        .add("active", "true");

pvs.addPropertyValue(new PropertyValue("city", "Hue"));
pvs.add("age", "24");             // thay mục "age" đang có
pvs.removePropertyValue("active");
~~~

| API | Cách dùng |
| --- | --- |
| `add(String, Object)` | Thêm/thay giá trị và **trả lại `MutablePropertyValues`** để gọi nối chuỗi |
| `addPropertyValue(PropertyValue)` | Thêm/thay bằng một `PropertyValue` đã tạo sẵn; trả lại holder |
| `addPropertyValue(String, Object)` | Overload hai tham số, **trả `void`** (không chain); `add(...)` thường gọn hơn |
| `addPropertyValues(Map<?, ?>)` | Nạp nhiều cặp từ map; key phải là property name kiểu `String` |
| `addPropertyValues(PropertyValues)` | Sao chép các mục từ một holder khác vào |
| `removePropertyValue(String)` | Xóa mục theo tên |
| `getPropertyValue(String)`, `get(String)` | Lần lượt trả wrapper `PropertyValue` hoặc giá trị thô |
| `size()` | Số mục `PropertyValue` hiện tại |
| `changesSince(PropertyValues)` | Chỉ lấy mục mới/thay đổi so với tập tham chiếu |
| `getPropertyValueList()` | Truy cập trực tiếp list bên trong; **không nên sửa list trực tiếp** trong code thông thường |

Ví dụ `pvs.get("age")` trả giá trị thô `"24"`; `pvs.getPropertyValue("age")` trả object `PropertyValue` để đọc tiếp `getName()`, `getValue()`.

**Vấn đề trùng tên:** thêm `age` hai lần thường **không tạo hai property age độc lập**; mục hiện tại được thay hoặc merge theo quy tắc `PropertyValue` tương ứng. Nếu muốn nhiều giá trị cho một tham số HTTP, hãy dùng kiểu giá trị phù hợp (ví dụ array/list) và cơ chế xử lý nhiều giá trị, đừng mặc định `MutablePropertyValues` giữ nguyên mọi lần xuất hiện của cùng một key.

### Sao chép khác với chia sẻ tham chiếu

~~~java
MutablePropertyValues source = new MutablePropertyValues()
        .add("name", "Lan");

MutablePropertyValues copy = new MutablePropertyValues(source);
copy.add("name", "Minh");

System.out.println(source.get("name")); // Lan
System.out.println(copy.get("name"));   // Minh
~~~

Constructor copy tạo các wrapper `PropertyValue` độc lập; thay giá trị property trong holder mới không làm biến đổi wrapper ở holder cũ. Tuy nhiên nếu giá trị là **một object mutable**, hai wrapper có thể vẫn trỏ đến cùng object bên trong. Đây **không phải deep copy toàn bộ object graph**.

### changesSince chỉ nhận biết bổ sung/chỉnh sửa

~~~java
MutablePropertyValues oldValues = new MutablePropertyValues()
        .add("name", "Lan")
        .add("age", "23")
        .add("admin", "true");

MutablePropertyValues newValues = new MutablePropertyValues(oldValues)
        .add("name", "Minh");
newValues.removePropertyValue("admin");

PropertyValues changed = newValues.changesSince(oldValues);

System.out.println(changed.contains("name"));  // true
System.out.println(changed.contains("age"));   // false
System.out.println(changed.contains("admin")); // false
~~~

`changesSince` trả các mục hiện diện trong tập mới mà **mới được thêm hoặc có giá trị thay đổi**. Nó không phải bộ so sánh hai chiều báo cả khóa đã xóa. Do đó, kết quả `changed.contains("admin") == false` **không chứng minh** khóa admin vẫn còn; admin đã bị xóa khỏi `newValues` nhưng không được diễn đạt như một mục thay đổi trong tập kết quả.

Nếu muốn audit đầy đủ thêm/sửa/xóa, hãy so sánh cả hai phía: tập tên cũ và mới, đồng thời phân loại giá trị thay đổi.

## 5. Từ PropertyValues đến DataBinder: ví dụ Java 17 chạy được

Đây là ví dụ **Java thuần dùng các thư viện Spring Framework** để quan sát đầy đủ:

1. Tạo dữ liệu dạng `MutablePropertyValues`; đọc qua interface `PropertyValues`.
2. Giữ một bản snapshot trước khi binding.
3. Tạo `DataBinder` cho một JavaBean với getter/setter.
4. Chỉ cho phép bind các field `name` và `age`; không cho bind `admin`.
5. Để Spring chuyển `"23"` thành kiểu `int` của JavaBean.
6. Đọc `BindingResult` và so sánh dữ liệu trước/sau.

### 5.1. Tạo Maven project

Tạo file `pom.xml`, dùng **JDK 17+**. Để ví dụ tái hiện được, các dependency Spring được quản lý qua một artifact duy nhất `spring-context` ở cùng một phiên bản Spring Framework **6.2.19**; đây là phiên bản cụ thể của ví dụ, không nhằm tuyên bố bản mới nhất.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>property-values-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
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

Trong dự án **Spring Boot**, thường nên dùng dependency management (BOM/parent của Boot) để chọn phiên bản Spring đồng bộ, tránh hard-code một bản `spring-context` riêng biệt khác dòng Boot. Bài này minh họa framework API độc lập nên ghim phiên bản nhất quán.

### 5.2. Mã nguồn

Tạo đúng tệp `src/main/java/example/PropertyValuesDemo.java`:

~~~java
package example;

import java.util.Arrays;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.PropertyValue;
import org.springframework.beans.PropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class PropertyValuesDemo {

    public static class RegistrationForm {
        private String name;
        private int age;
        private boolean admin;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            this.age = age;
        }

        public boolean isAdmin() {
            return admin;
        }

        public void setAdmin(boolean admin) {
            this.admin = admin;
        }
    }

    public static void main(String[] args) {
        MutablePropertyValues submitted = new MutablePropertyValues()
                .add("name", "Lan")
                .add("age", "23")
                .addPropertyValue(new PropertyValue("admin", "true"));

        // Dùng interface để đọc, không cần phụ thuộc cách thêm/xóa.
        PropertyValues original = new MutablePropertyValues(submitted);

        System.out.println("submitted.size=" + original.getPropertyValues().length);
        System.out.println("age.raw=" + original.getPropertyValue("age").getValue());

        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(form, "registrationForm");

        // Chỉ nhận những thuộc tính được phép gán.
        binder.setAllowedFields("name", "age");

        // bind có thể sửa MutablePropertyValues được truyền vào:
        // đưa bản sao để bảo toàn dữ liệu submitted.
        binder.bind(new MutablePropertyValues(submitted));

        BindingResult result = binder.getBindingResult();

        System.out.println("name=" + form.getName());
        System.out.println("age=" + form.getAge());
        System.out.println("admin=" + form.isAdmin());
        System.out.println("errors=" + result.getErrorCount());
        System.out.println("suppressed=" +
                Arrays.toString(result.getSuppressedFields()));
        System.out.println("submitted.still=" + submitted.size());

        // Chỉnh sửa tập mô tả đầu vào; chưa động tới form.
        MutablePropertyValues edited = new MutablePropertyValues(submitted);
        edited.add("name", "Minh");
        edited.removePropertyValue("admin");

        PropertyValues delta = edited.changesSince(original);
        System.out.println("delta.name=" + delta.contains("name"));
        System.out.println("delta.age=" + delta.contains("age"));
        System.out.println("delta.admin=" + delta.contains("admin"));
        System.out.println("form.name.afterEdit=" + form.getName());
    }
}
~~~

Các property có getter/setter, nên `DataBinder` có thể thao tác theo quy ước JavaBeans. Trường `age` kiểu primitive `int` nhận chuỗi đầu vào `"23"` thông qua bộ chuyển đổi kiểu phù hợp của Spring. Trường `admin` **có setter**, nhưng được chặn bởi `setAllowedFields("name", "age")`.

### 5.3. Biên dịch và chạy

Cấu trúc thư mục:

~~~text
property-values-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── PropertyValuesDemo.java
~~~

Tại thư mục có `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=example.PropertyValuesDemo
~~~

Nếu đã cài JDK 17 trở lên và Maven có thể tải dependency, **12 dòng do chương trình in** là:

~~~text
submitted.size=3
age.raw=23
name=Lan
age=23
admin=false
errors=0
suppressed=[admin]
submitted.still=3
delta.name=true
delta.age=false
delta.admin=false
form.name.afterEdit=Lan
~~~

Các dòng output trên là phần `System.out.println`; log hoặc thông báo khác từ Maven không được tính vào kết quả của chương trình. Không có `javac` classpath thuần được chỉ ra vì Spring là thư viện ngoài JDK; Maven đảm nhận tải và liên kết các jar để biên dịch/chạy.

### 5.4. Giải thích từng kết quả

- `submitted.size=3`: holder chứa ba mục `PropertyValue`. Mỗi mục chỉ mô tả tên và giá trị đầu vào.
- `age.raw=23`: chữ `23` nhìn giống số, nhưng giá trị từ holder vẫn là một `String`; `PropertyValue#getValue()` không tự chuyển thành `int`.
- `name=Lan` và `age=23`: quá trình `DataBinder.bind(...)` đã gọi setter phù hợp, chuyển kiểu và gán vào JavaBean.
- `admin=false`: dù `submitted` chứa `"admin"="true"` và form có `setAdmin(...)`, quy tắc allowlist ngăn gán field đó. Vì primitive boolean mặc định là `false` nên nó giữ nguyên.
- `errors=0`: không có lỗi binding kiểu hoặc field bắt buộc trong ví dụ này. **Một suppressed field không tự tăng `getErrorCount()`**; hãy kiểm tra riêng `getSuppressedFields()`.
- `suppressed=[admin]`: tên field bị từ chối được lưu để application có thể ghi log, kiểm toán hoặc từ chối request khi cần.
- `submitted.still=3`: vì đã truyền **bản sao** cho binder, tập dữ liệu `submitted` ban đầu vẫn còn đủ ba phần tử.
- `delta.name=true`, `delta.age=false`: khi thay tên và giữ nguyên tuổi, `changesSince` chỉ nhận diện tên là mục đổi giá trị.
- `delta.admin=false`: `admin` đã bị xóa khỏi `edited`; `changesSince` không tạo mục đại diện thao tác xóa.
- `form.name.afterEdit=Lan`: sửa `edited` chỉ sửa holder, không tự động cập nhật `form`. Muốn áp dụng giá trị sửa, phải bind hoặc dùng cơ chế gán property thêm lần nữa và kiểm soát đầu vào phù hợp.

Đây là phân biệt quan trọng nhất giữa **chuẩn bị dữ liệu để bind** và **gán dữ liệu vào object**.

## 6. Vì sao binder nhận PropertyValues, không phải chỉ MutablePropertyValues?

Chữ ký của `DataBinder` là:

~~~java
public void bind(PropertyValues pvs)
~~~

Điều này giúp caller đưa vào **bất cứ implementation** phù hợp nào của interface `PropertyValues`, chứ không buộc phải chọn chính class `MutablePropertyValues`. Trong phương thức này, Spring sẽ thực hiện những xử lý như loại field không được phép, kiểm tra field bắt buộc theo cấu hình và áp dụng property lên object đích.

**Quan trọng về ownership/mutation:** Javadoc `DataBinder.bind(PropertyValues)` cho biết binder có thể **thay đổi trực tiếp** đối tượng được truyền vào nếu nó là `MutablePropertyValues`, vì cách làm đó hiệu quả hơn. Nếu đầu vào không mutable, Spring có thể tạo bản mutable nội bộ. Do đó:

~~~java
PropertyValues original = new MutablePropertyValues()
        .add("name", "Lan")
        .add("admin", "true");

DataBinder binder = new DataBinder(target, "target");
binder.setAllowedFields("name");

// Tạo một bản sao mỗi khi cần giữ nguyên original.
binder.bind(new MutablePropertyValues(original));
~~~

Đây là **đoạn trích**, chưa định nghĩa `target`. Trong ứng dụng có nhiều tầng muốn audit request, lưu lại giá trị thô, hoặc tái sử dụng cùng một holder, nên **sao chép trước khi bind** thay vì dựa vào việc binder giữ nguyên tập đầu vào.

### Khi nào cần mutable, khi nào chỉ cần interface?

- **Chuẩn bị hoặc chỉnh sửa dữ liệu:** dùng `MutablePropertyValues` để xây đầu vào từ map, thêm default có chủ đích, hoặc loại key không mong muốn theo chính sách.
- **Một hàm chỉ cần xem dữ liệu:** nhận `PropertyValues` để không phụ thuộc những thao tác sửa.
- **Gửi sang binder:** nhận `PropertyValues` đúng chữ ký API; nếu holder là mutable và cần giữ nguyên bản nguồn, tự tạo bản sao.

`PropertyValues` không phải một annotation validation, cũng không phải `java.util.Properties`, `Environment` hay `PropertySource` được dùng để lấy cấu hình ứng dụng từ `application.properties`. Cùng chữ “property”, nhưng một bên là **giá trị gán cho JavaBean trong binding**, một bên là **nguồn cấu hình của ứng dụng**.

## 7. Nested property và các trường hợp có nhiều giá trị

Tên của `PropertyValue` có thể là **đường dẫn property**, chẳng hạn:

~~~java
MutablePropertyValues values = new MutablePropertyValues()
        .add("displayName", "Lan")
        .add("address.city", "Ha Noi")
        .add("items[0].quantity", "2");
~~~

Đây là **đoạn trích**, không phải ví dụ độc lập. Để bind thành công, target phải có cấu trúc JavaBean tương thích:

- `displayName` đọc/ghi được.
- `address` có property `city` phù hợp, được khởi tạo hoặc có thể được binder auto-grow theo cấu hình hợp lệ.
- `items` là collection/array với phần tử có property `quantity`, có thể truy cập được theo đường dẫn index tương ứng.

Khi property path bị thiếu hoặc object con không thể truy cập, việc xử lý phụ thuộc cấu hình như `setAutoGrowNestedPaths` và `setIgnoreInvalidFields`; không nên giả định mọi đường dẫn lồng nhau sẽ tự được tạo thành công.

**Đối với tham số nhiều giá trị**, chẳng hạn `tag=java&tag=spring`, dữ liệu nguồn HTTP có thể phải giữ một giá trị kiểu array/list thay vì gọi `add("tag", ...)` hai lần: `MutablePropertyValues` thường cập nhật giá trị theo tên property, không mang ngữ nghĩa “mỗi lần thêm một giá trị nữa cho cùng key” như một multimap.

## 8. Lỗi binding, conversion và validation

`PropertyValues` nói **giá trị nào được đề nghị gán**, còn `DataBinder` là nơi có thể sinh lỗi truy cập và chuyển đổi kiểu. Ví dụ:

~~~java
MutablePropertyValues pvs = new MutablePropertyValues()
        .add("age", "twenty-three");
DataBinder binder = new DataBinder(form, "registrationForm");
binder.setAllowedFields("age");
binder.bind(pvs);

BindingResult errors = binder.getBindingResult();
System.out.println(errors.hasFieldErrors("age")); // true
~~~

Đây là **đoạn trích** có biến `form` kiểu bean chứa `int age` như ở phần 5, không phải chương trình độc lập. Vì `"twenty-three"` không thể chuyển thành `int` bằng conversion thông dụng, Spring ghi lại lỗi field dạng `typeMismatch` vào `BindingResult`.

Các loại vấn đề cần tách bạch:

| Tình huống | Nơi/loại xử lý |
| --- | --- |
| `age="abc"` để gán cho `int` | Lỗi chuyển kiểu trong quá trình **binding** |
| Có trường `admin` nhưng allowlist chỉ cho `name, age` | **Suppressed field**, phải xem `BindingResult#getSuppressedFields()` riêng |
| Field không tồn tại trong bean | Theo cấu hình, có thể được bỏ qua (`ignoreUnknownFields` thường mặc định `true`) hoặc gây lỗi truy cập |
| `age=15` trong khi nghiệp vụ cần từ 18 tuổi | **Validation** bổ sung, không tự được kiểm tra chỉ nhờ `PropertyValues` |
| Trường con bị `null` trong property path | Có thể cần auto-grow hoặc cấu hình xử lý invalid field |
| Dữ liệu không thuộc quyền của người gửi | **Authorization / kiểm soát property được phép ghi**, không do type conversion quyết định |

`DataBinder.bind(...)` **không đồng nghĩa** `DataBinder.validate()`. Muốn kiểm tra constraint nghiệp vụ, cần đăng ký `Validator`/provider và gọi validation hoặc để pipeline Spring MVC xử lý theo cấu hình. Khi kiểm thử, nên xác nhận độc lập: giá trị bean sau binding, `getErrorCount()`, `getFieldErrors()` và `getSuppressedFields()`.

## 9. An toàn khi bind dữ liệu ngoài hệ thống

Nếu dữ liệu đến từ request người dùng, việc đưa mọi key trong `MutablePropertyValues` lên một entity có setter có thể gây **mass assignment**: client cố tình gửi thêm `isAdmin=true`, `role=ADMIN` hoặc `ownerId=...` ngoài trường giao diện cho phép.

Nguyên tắc an toàn:

1. **Chỉ nhận property được phép sửa.** Ưu tiên DTO dành riêng cho từng use case, gồm những trường được cho phép; với property binding có setter, dùng `DataBinder#setAllowedFields(...)` khi phù hợp.
2. **Không bind trực tiếp entity chứa trạng thái nhạy cảm** chỉ vì nó có setter. Chuyển dữ liệu đã kiểm tra từ DTO sang domain object trong service theo quy tắc nghiệp vụ.
3. **Không nhầm suppressed với lỗi binding.** Field bị chặn có thể không làm `hasErrors()` trở thành `true`; kiểm tra `getSuppressedFields()` nếu chính sách bảo mật yêu cầu từ chối request có key bất hợp lệ.
4. **Giới hạn kích thước, nested path và collection growth** khi xử lý dữ liệu ngoài hệ thống; tránh cho phép tạo object graph quá sâu hoặc collection không kiểm soát.
5. **Không dùng API chỉnh sửa holder để lách kiểm soát.** Loại một key trong `MutablePropertyValues` trước khi gọi binder là thao tác chuẩn bị dữ liệu; quyền thực tế phải được quyết định phía server.

Khi dùng constructor binding cho DTO bất biến, cơ chế lựa chọn field khác với setter/property binding. `setAllowedFields(...)` chủ yếu điều khiển **property binding** qua `bind(PropertyValues)`; không nên xem nó là bộ lọc toàn diện của mọi cơ chế khởi tạo object hoặc kiểm tra phân quyền.

## 10. Các hiểu nhầm hay gặp

- **“`PropertyValue` tự thực hiện setter.”** Sai: đó là object mô tả giá trị; một accessor/binder khác mới gán vào target.
- **“`PropertyValues` là class mutable.”** Sai: đó là interface. `MutablePropertyValues` mới cung cấp các thao tác thêm/xóa cụ thể.
- **“`getValue()` luôn trả giá trị đã được chuyển kiểu.”** Sai: có thể vẫn là chuỗi `"23"` dù property đích là `int`.
- **“`new MutablePropertyValues(source)` deep-copy toàn bộ object bên trong.”** Sai: wrapper độc lập nhưng object mutable trong giá trị có thể vẫn được chia sẻ tham chiếu.
- **“`changesSince` báo cả mục đã xóa.”** Sai: API trả các mục mới/đổi trong tập mới, không tự tạo bản ghi xóa.
- **“Gọi `add("x", ...)` hai lần là có hai bản ghi cho cùng tên.”** Sai: thường là thay/merge theo tên; không phải multimap.
- **“`DataBinder.bind(...)` không thay holder đầu vào.”** Sai trong trường hợp `MutablePropertyValues`: binder có thể lọc/chỉnh sửa tập đầu vào. Copy nếu cần dữ liệu gốc.
- **“`hasErrors() == false` thì request không gửi field cấm.”** Sai: field bị suppressed không nhất thiết sinh `FieldError`.
- **“Bind xong là validation nghiệp vụ đã được thực hiện.”** Sai: cần validator/provider hoặc pipeline validation được cấu hình.
- **“`application.properties` cũng là `PropertyValues` đang dùng.”** Sai: khái niệm property cấu hình và property value dùng cho bean binding là hai API khác nhau.

## 11. Câu hỏi thực hành

1. Trong ba kiểu `PropertyValue`, `PropertyValues` và `MutablePropertyValues`, kiểu nào đại diện **một** cặp, kiểu nào là **interface**, kiểu nào thêm/xóa được?
2. Nếu `age="23"` ở `PropertyValues` nhưng bean có `int age`, thành phần nào chịu trách nhiệm chuyển đổi?
3. Vì sao nên gọi `binder.bind(new MutablePropertyValues(original))` khi `original` còn được dùng để audit?
4. Nếu `newValues` xóa key `admin`, tại sao `changesSince(oldValues)` không phải cách đầy đủ để thống kê các key đã xóa?
5. Khi `setAllowedFields("name", "age")`, field `admin` có setter nhưng bị gửi lên, nên xem thông tin nào ngoài `getErrorCount()`?
6. Nếu code muốn chỉ duyệt các mục đầu vào, tại sao khai báo tham số kiểu `PropertyValues` là một lựa chọn tốt hơn việc yêu cầu cụ thể `MutablePropertyValues`?

**Ghi nhớ:** `PropertyValue` là một mục **tên–giá trị**; `PropertyValues` là **hợp đồng tập mục**; `MutablePropertyValues` là **container có thể sửa**. Chúng chuẩn bị dữ liệu, còn `DataBinder` kiểm soát việc gán và chuyển kiểu vào bean. Luôn tách rõ dữ liệu thô, quyền được bind, kết quả binding và validation nghiệp vụ.

## Tài liệu tham khảo chính thức

- Spring Framework Javadoc — PropertyValue: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/PropertyValue.html
- Spring Framework Javadoc — PropertyValues: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/PropertyValues.html
- Spring Framework Javadoc — MutablePropertyValues: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/MutablePropertyValues.html
- Spring Framework Javadoc — DataBinder: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework Reference — Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html