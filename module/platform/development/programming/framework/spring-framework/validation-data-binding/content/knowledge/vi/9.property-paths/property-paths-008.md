# Lỗi thuộc tính không tồn tại, không đọc được hoặc không ghi được trong Spring Data Binding

Spring Framework sử dụng **đường dẫn thuộc tính** (*property path*) để định vị dữ liệu trong object Java, ví dụ `name`, `address.city` và `items[0].price`. Khi thao tác với `BeanWrapper` hoặc `DataBinder`, một tên thuộc tính có thể **không tồn tại**, **tồn tại nhưng không đọc được**, hoặc **tồn tại nhưng không ghi được**. Ba lỗi nghe giống nhau, nhưng khác về nguyên nhân, exception, tác động khi bind dữ liệu và hướng khắc phục.

Ví dụ form gửi `displayNmae=Lan` (sai chính tả), class có `getStatus()` nhưng không có `setStatus(...)`, hoặc `address` đang `null` khi code muốn ghi `address.city`. Có trường hợp Spring ném exception, trường hợp lặng lẽ bỏ qua trường lạ theo mặc định của binder, và trường hợp ghi `FieldError` trong `BindingResult`. **Không nên mặc định mọi lỗi property đều trở thành HTTP 400 hoặc đều có `FieldError`.**

Bài học tập trung vào cách Spring nhìn nhận các property path trong nhóm **Đường dẫn thuộc tính**, đặc biệt là JavaBean property access, các exception trong `org.springframework.beans`, chính sách `DataBinder` và kiểm thử chẩn đoán. Ví dụ thực hành dùng Java 17 với Spring Framework 6.2.x.

## 1. Đường dẫn thuộc tính và yêu cầu đọc/ghi

| Biểu thức | Đường đi qua object |
| --- | --- |
| `name` | Property trực tiếp của object |
| `address.city` | Lấy object `address`, sau đó truy cập `city` |
| `contacts[0].email` | Phần tử thứ nhất trong collection/array `contacts`, rồi property `email` |
| `preferences['theme']` | Key `theme` trong một map tương thích |

Ví dụ hai class:

```java
public class ProfileForm {
    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}

public class Address {
    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
```

Với **JavaBean property access**, tên `address.city` được hiểu theo đường đi qua `getAddress()` và các accessor của `city`. Khi ghi, Spring thường phải tìm được object lồng đang có, hoặc tạo object lồng theo cấu hình, rồi dùng setter của property cuối.

Có ba câu hỏi riêng:

1. **Tên path có đúng cấu trúc không?** `address.city` khác `adress.city`.
2. **Chiều truy cập có được hỗ trợ không?** Đọc cần getter, ghi cần setter hoặc cơ chế truy cập tương đương.
3. **Giá trị object và đầu vào có hợp lệ không?** Object lồng có thể `null`, chuỗi `abc` không thể chuyển sang `Integer` hoặc getter/setter có thể ném exception.

Một property có thật trong class **không có nghĩa mọi thao tác với nó sẽ thành công**.

## 2. Trường hợp 1: property không tồn tại

Nếu form gửi `displayNmae` nhưng DTO chỉ có `displayName`, Spring không nhận ra tên đó dưới cơ chế JavaBeans thông thường.

```java
BeanWrapperImpl wrapper = new BeanWrapperImpl(new ProfileForm());
boolean existsForRead = wrapper.isReadableProperty("displayNmae");
boolean existsForWrite = wrapper.isWritableProperty("displayNmae");
```

Hai kết quả thường là `false`. Truy cập trực tiếp:

- Đọc bằng `getPropertyValue("displayNmae")` có thể ném `NotReadablePropertyException`.
- Ghi bằng `setPropertyValue("displayNmae", value)` có thể ném `NotWritablePropertyException`.

Đó là hai exception của **thao tác**, không phải một exception riêng tên `UnknownPropertyException`. Tên không tồn tại thường bị phát hiện khi truy cập.

**Khác biệt quan trọng với `DataBinder`:** `setIgnoreUnknownFields(boolean)` có giá trị mặc định **`true`**. Khi dùng `DataBinder.bind(PropertyValues)`, trường đầu vào không khớp property có thể bị **bỏ qua**. Điều đó có nghĩa lỗi gõ nhầm tên field đôi khi làm dữ liệu bị mất một cách âm thầm, không phải vì property bất ngờ được ghi thành công.

## 3. Trường hợp 2: property không đọc được

Một property JavaBean có thể có setter nhưng không có getter:

```java
public class LoginForm {
    private String oneTimeCode;

    public void setOneTimeCode(String oneTimeCode) {
        this.oneTimeCode = oneTimeCode;
    }

    // Cố ý không có getOneTimeCode().
}
```

Đây là trường hợp **chỉ ghi** (*write-only*). `BeanWrapperImpl.isWritableProperty("oneTimeCode")` có thể trả `true`, nhưng `isReadableProperty("oneTimeCode")` trả `false`. Gọi:

```java
wrapper.getPropertyValue("oneTimeCode");
```

trên wrapper của một `LoginForm` như trên thường gây **`NotReadablePropertyException`**.

Tình huống tương tự có thể xuất hiện khi:

- Getter bị thiếu hoặc tên không đúng theo quy ước `getX()`/`isX()`.
- Getter không có mức truy cập thích hợp với JavaBeans introspection.
- Property trung gian trong đường dẫn lồng thiếu getter: muốn đi tới `address.city` nhưng class gốc chỉ có `setAddress(Address)`.
- Getter tồn tại nhưng bản thân nó ném exception: đây lại là **lỗi thực thi accessor**, không nhất thiết là `NotReadablePropertyException`.

Đừng vội thêm getter cho trường bí mật nếu ứng dụng không cần đọc ngược dữ liệu đó. Thiết kế form hoặc logic xử lý nên phù hợp mục đích lưu và bảo mật.

## 4. Trường hợp 3: property không ghi được

JavaBean có getter nhưng không có setter:

```java
public class OrderView {
    private final String status = "NEW";

    public String getStatus() {
        return status;
    }

    // Không có setStatus(String).
}
```

`status` là property **chỉ đọc** (*read-only*). Nó có thể đọc qua getter, nhưng cố ghi bằng:

```java
BeanWrapperImpl wrapper = new BeanWrapperImpl(new OrderView());
wrapper.setPropertyValue("status", "APPROVED");
```

thường gây **`NotWritablePropertyException`** vì không có JavaBeans write method tương ứng.

Một property cũng có thể không ghi được vì setter đặt tên sai, không công khai khi cần, có kiểu không tương thích, hoặc vì binder sử dụng chế độ truy cập khác với điều bạn nghĩ. Nhưng không phải mọi lỗi khi ghi đều là `NotWritablePropertyException`: nếu setter có thật mà ném exception, nguyên nhân khác; nếu converter không đổi được chuỗi sang kiểu setter, đó là **type mismatch**.

Không thêm setter cho các trường do server quản lý (`role`, `approved`, `status`) chỉ để làm biến mất lỗi binding. Nếu các trường đó không phải đầu vào hợp lệ, nên loại khỏi input DTO hoặc quản lý ở tầng nghiệp vụ.

### Bảng phân biệt quyền đọc/ghi

| Cấu trúc theo JavaBeans | Đọc | Ghi | Dạng lỗi đặc trưng |
| --- | --- | --- | --- |
| Getter và setter hợp lệ | Có | Có | Vẫn có thể sai conversion hoặc method invocation |
| Chỉ getter | Có | Không | Ghi: `NotWritablePropertyException` |
| Chỉ setter | Không | Có | Đọc: `NotReadablePropertyException` |
| Không có property | Không | Không | Truy cập trực tiếp: exception theo chiều; `DataBinder` có thể bỏ qua key lạ |
| Property lồng hợp lệ nhưng object giữa là `null` | Phụ thuộc trạng thái | Phụ thuộc auto-grow | `NullValueInNestedPathException` nếu không thể đi sâu |

Từ “có” trong bảng chỉ nói về việc nhận diện accessor, không đảm bảo getter/setter không ném lỗi và cũng không đảm bảo conversion luôn thành công.

## 5. Hệ thống exception trong Spring Beans

Các class cần nhận biết nằm trong package `org.springframework.beans`:

| Exception | Ý nghĩa thường gặp |
| --- | --- |
| `InvalidPropertyException` | Đường dẫn hoặc property được tham chiếu không hợp lệ; superclass của một số exception đặc thù |
| `NotReadablePropertyException` | Không thể đọc property, thường không có getter |
| `NotWritablePropertyException` | Không thể ghi property, thường không có setter, hoặc property không tồn tại |
| `NullValueInNestedPathException` | Điều hướng qua property lồng mà giá trị trung gian là `null` |
| `TypeMismatchException` | Không thể đổi giá trị đầu vào thành kiểu cần ghi |
| `MethodInvocationException` | Method getter/setter có mặt nhưng ném exception trong lúc gọi |
| `PropertyBatchUpdateException` | Nhiều lỗi truy cập property có thể được báo chung khi xử lý tập giá trị |

Ba class đầu có quan hệ với đường dẫn không hợp lệ như sau:

```text
InvalidPropertyException
├── NotReadablePropertyException
├── NotWritablePropertyException
└── NullValueInNestedPathException
```

`TypeMismatchException` và `MethodInvocationException` không thuộc ba nhánh này; chúng liên quan đến lỗi xử lý giá trị hoặc việc thực thi accessor. Vì vậy, bắt `InvalidPropertyException` không có nghĩa đã xử lý toàn bộ lỗi của một lần bind.

**Không nhầm với lỗi constraint.** `@NotBlank`, `@NotNull`, `@Min` hoặc `@Email` thuộc kiểm tra tính hợp lệ của dữ liệu (Jakarta Bean Validation). Một property có thể đọc/ghi hoàn toàn bình thường nhưng vẫn vi phạm constraint.

## 6. Ví dụ Java 17 chạy được: BeanWrapper và DataBinder

Ví dụ thực hành không cần Spring Boot hay HTTP server. Mục tiêu là nhìn thấy rõ:

- `BeanWrapperImpl` nhận biết property chỉ đọc, chỉ ghi và không tồn tại.
- Truy cập nested path gặp `null` khi tắt auto-grow.
- `DataBinder` với mặc định bỏ qua field lạ, tự tạo nested object khi khả thi, nhưng vẫn ghi lỗi chuyển kiểu vào `BindingResult`.

### 6.1. Cấu trúc Gradle

```text
property-path-errors/
├── settings.gradle
├── build.gradle
└── src/main/java/example/PropertyPathErrorsDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'property-path-errors'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'example.PropertyPathErrorsDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Chọn JDK 17+ và Gradle tương thích, có kết nối Maven Central để tải dependency lần đầu. `spring-context` kéo theo các module Spring mà demo sử dụng.

### 6.2. Mã đầy đủ

**`src/main/java/example/PropertyPathErrorsDemo.java`**

```java
package example;

import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.NotReadablePropertyException;
import org.springframework.beans.NotWritablePropertyException;
import org.springframework.beans.NullValueInNestedPathException;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class PropertyPathErrorsDemo {

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

    public static class Profile {
        private String name;
        private Integer age;
        private Address address;
        private String status = "NEW";
        private String secret;

        public Profile() {
        }

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

        public String getStatus() {
            return status;
        }

        // Chủ ý không có setStatus(String).

        public void setSecret(String secret) {
            this.secret = secret;
        }

        // Chủ ý không có getSecret().
    }

    public static void main(String[] args) {
        Profile inspect = new Profile();
        BeanWrapperImpl wrapper = new BeanWrapperImpl(inspect);

        System.out.println("nameReadable="
                + wrapper.isReadableProperty("name"));
        System.out.println("statusWritable="
                + wrapper.isWritableProperty("status"));
        System.out.println("secretReadable="
                + wrapper.isReadableProperty("secret"));
        System.out.println("secretWritable="
                + wrapper.isWritableProperty("secret"));
        System.out.println("ghostReadable="
                + wrapper.isReadableProperty("ghost"));

        try {
            wrapper.setPropertyValue("status", "APPROVED");
        } catch (NotWritablePropertyException ex) {
            System.out.println("statusWrite="
                    + ex.getClass().getSimpleName());
        }

        try {
            wrapper.getPropertyValue("secret");
        } catch (NotReadablePropertyException ex) {
            System.out.println("secretRead="
                    + ex.getClass().getSimpleName());
        }

        wrapper.setAutoGrowNestedPaths(false);
        try {
            wrapper.setPropertyValue("address.city", "Hue");
        } catch (NullValueInNestedPathException ex) {
            System.out.println("nullNested="
                    + ex.getClass().getSimpleName());
        }

        Profile form = new Profile();
        DataBinder binder = new DataBinder(form, "profile");

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("name", "Lan");
        values.add("address.city", "Hue");
        values.add("ghost", "unexpected");
        values.add("age", "not-a-number");

        binder.bind(values);

        System.out.println("name=" + form.getName());
        System.out.println("city=" + form.getAddress().getCity());
        System.out.println("ageError="
                + (binder.getBindingResult().getFieldError("age") != null));
        System.out.println("errorFields="
                + binder.getBindingResult().getFieldErrors().stream()
                        .map(FieldError::getField).toList());
    }
}
```

Chạy từ thư mục dự án:

```bash
gradle -q run
```

Nếu có Gradle wrapper, dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows.

**Stdout kỳ vọng:**

```text
nameReadable=true
statusWritable=false
secretReadable=false
secretWritable=true
ghostReadable=false
statusWrite=NotWritablePropertyException
secretRead=NotReadablePropertyException
nullNested=NullValueInNestedPathException
name=Lan
city=Hue
ageError=true
errorFields=[age]
```

Giải thích:

1. `name` có getter và setter; nó đọc được.
2. `status` chỉ có getter nên không ghi được; ghi trực tiếp gây `NotWritablePropertyException`.
3. `secret` chỉ có setter nên không đọc được; đọc trực tiếp gây `NotReadablePropertyException`.
4. `ghost` không phải property JavaBean trên `Profile`; `isReadableProperty("ghost")` là `false`.
5. `inspect.address` đang `null`; khi tắt auto-grow trên `wrapper`, cố ghi `address.city` gây `NullValueInNestedPathException`.
6. `DataBinder` riêng có mặc định auto-grow nested paths = `true`; nó có thể tạo `Address()` rồi ghi `city="Hue"`, vì object con có constructor không tham số và các accessor phù hợp.
7. `DataBinder` mặc định ignore unknown fields = `true`, vì vậy `ghost` bị bỏ qua và không tạo lỗi field ở đây.
8. `age` là `Integer` có setter nhưng giá trị `not-a-number` không chuyển thành số; binder ghi `FieldError` cho `age` vào `BindingResult`.

**Vì sao dùng hai object?** `inspect` là đối tượng cho thao tác trực tiếp với `BeanWrapperImpl`, còn `form` dành cho binder. Việc tắt auto-grow trên wrapper đầu **không** ảnh hưởng binder mới. Đây là cách tách bạch hai chính sách để hiểu lỗi.

## 7. Hai cờ dễ nhầm: ignoreUnknownFields và ignoreInvalidFields

`DataBinder` có những tùy chọn quan trọng:

| Tùy chọn | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `setIgnoreUnknownFields(boolean)` | `true` | Bỏ qua input không có property tương ứng |
| `setIgnoreInvalidFields(boolean)` | `false` | Bỏ qua một số input có path được khai báo nhưng không truy cập được, ví dụ đoạn lồng `null` |
| `setAutoGrowNestedPaths(boolean)` | `true` trên DataBinder thông thường | Thử tạo object lồng khi gặp `null` và có khả năng khởi tạo |

Các setting này áp dụng cho **property binding** qua `bind(PropertyValues)`, không điều khiển việc truy xuất dữ liệu thông thường qua `BindingResult` và cũng không phải thiết lập tương đương cho constructor binding.

### 7.1. Unknown field

```java
DataBinder binder = new DataBinder(new Profile(), "profile");
binder.setIgnoreUnknownFields(true); // Giá trị mặc định.
```

Khi request gửi `ghost=foo` mà target không có property `ghost`, binder có thể bỏ qua key. Nếu muốn phát hiện field lạ thay vì lờ đi:

```java
binder.setIgnoreUnknownFields(false);
```

Khi đó một lần `bind(...)` đối với property không tồn tại có thể phát sinh `NotWritablePropertyException` thay vì sinh `FieldError` thông thường. Vì thế đừng chỉ kiểm tra `BindingResult.hasErrors()` rồi kết luận rằng request không có field lạ; phải hiểu cơ chế exception và chính sách binder.

### 7.2. Invalid field

Đây là trường hợp tên property/path hợp lý nhưng **đường đi không có object truy cập được**:

```java
DataBinder binder = new DataBinder(new Profile(), "profile");
binder.setAutoGrowNestedPaths(false);
binder.setIgnoreInvalidFields(false); // Giá trị mặc định.
```

Nếu bind `address.city=Hue` trong khi `address` đang `null`, có thể gặp `NullValueInNestedPathException`. Nếu nghiệp vụ thật sự muốn bỏ qua input cho object con chưa có, có thể cân nhắc:

```java
binder.setIgnoreInvalidFields(true);
```

Nhưng thao tác này **không tạo object con**; nó chỉ cho phép bỏ qua một số path không truy cập được theo chính sách binder. Không bật bừa để che một lỗi thiết kế object. Khi field bắt buộc phải lưu, cần sửa cấu trúc DTO hoặc cách khởi tạo.

### 7.3. Auto-grow nested paths

Nếu `Profile.address == null` nhưng `Address` có constructor không tham số, getter/setter và type metadata phù hợp, DataBinder có thể:

```text
input: address.city=Hue
  → tạo Address() cho Profile.address
  → gọi setCity("Hue")
  → Profile.address.city == "Hue"
```

Tuy nhiên, auto-grow **không bảo đảm** tạo được mọi interface, abstract type, class không thể khởi tạo hoặc collection tùy ý. Với collection/index, Spring còn có giới hạn auto-grow để hạn chế kích thước và chi phí bộ nhớ.

Khi debug, hỏi theo thứ tự: **path có đúng không → property có đọc/ghi được không → intermediate object có null không → cấu hình auto-grow như thế nào**.

## 8. Path lồng: lỗi có thể xuất hiện ở từng tầng

Xét:

```text
Order
└── shippingAddress
    └── country
        └── code
```

Với `shippingAddress.country.code`, lỗi có thể nằm ở bất kỳ đoạn nào:

- `shippingAdress` bị đánh máy thiếu chữ → path không tồn tại.
- `Order` có `setShippingAddress(...)` nhưng thiếu `getShippingAddress()` → khó điều hướng để truy cập `country`.
- `shippingAddress == null` → có thể cần auto-grow hoặc khởi tạo trước.
- `country == null` nhưng type là interface không có cách khởi tạo phù hợp → auto-grow có thể thất bại.
- `code` chỉ có getter → đọc được nhưng không có setter để ghi.
- `code` có setter `setCode(Integer)` nhưng client gửi `abc` → type mismatch, khác lỗi writable.
- `getCountry()` có thật nhưng tự ném exception → method invocation, không phải thiếu getter.

Spring còn có property path qua list/map như `items[0].sku`; với index/key, hãy xác minh collection được khởi tạo, kiểu phần tử, giới hạn auto-grow và syntax dấu ngoặc.

Nếu dùng `Errors.rejectValue("shippingAddress.country.code", ...)` để tạo lỗi validation, mã này không tự tạo object con. Với `BeanPropertyBindingResult`, việc xác định giá trị field cho thông tin lỗi có thể vẫn yêu cầu các đoạn path truy cập được. Không dùng nested path của validator để che lỗi object graph.

## 9. Getter/setter, tên property và chế độ access

Tên property theo quy ước JavaBeans. Ví dụ:

```java
private String displayName;

public String getDisplayName() {
    return displayName;
}

public void setDisplayName(String displayName) {
    this.displayName = displayName;
}
```

Property được nhận diện là `displayName`. Những tên request khác như `display_name`, `displayname` hoặc `DisplayName` không nên được xem là tương đương nếu không có cơ chế ánh xạ riêng.

Các lỗi thường gặp:

- `getFullname()` và `setFullName(...)` khác quy tắc đặt tên, có thể tạo property không trùng.
- `getURL()` có quy tắc viết hoa acronym riêng trong JavaBeans introspection.
- Với kiểu `boolean` primitive, `isActive()` là read method thông dụng; với wrapper `Boolean`, dùng `getActive()` rõ ràng hơn.
- Setter dùng kiểu khác biệt hoặc overload không nhất quán có thể khiến Spring chọn accessor không như dự kiến.
- Getter/setter đặt `private` có thể không được JavaBeans introspection thông thường xem là public accessor.

**Field private là bình thường.** JavaBean với field `private` và public getter/setter có thể bind được. Ngược lại, việc field có tên giống request không có nghĩa tự động được bind nếu getter/setter cần thiết bị thiếu.

Spring cho phép gọi `binder.initDirectFieldAccess()` để truy cập trực tiếp field trong một số trường hợp. Chế độ này khác **JavaBean property access mặc định**; không nên coi nó là “bật quyền ghi tất cả field” để sửa mọi lỗi, bởi có thể mở rộng bề mặt dữ liệu được client thay đổi.

## 10. Lỗi conversion và validation không phải lỗi thuộc tính không ghi được

Giả sử class có:

```java
private Integer age;

public Integer getAge() {
    return age;
}

public void setAge(Integer age) {
    this.age = age;
}
```

Client gửi `age=abc`. `age` tồn tại, có getter/setter đúng. Thất bại ở đây là Spring **không chuyển được** `"abc"` sang `Integer`; trong `DataBinder.bind(...)`, lỗi này thường được biểu diễn bằng `FieldError` với mã `typeMismatch`.

```java
BindingResult result = binder.getBindingResult();
FieldError ageError = result.getFieldError("age");
if (ageError != null) {
    System.out.println(ageError.getField());
    System.out.println(ageError.getCode());
}
```

Đây là đoạn minh họa trong phương thức đã có biến `binder` và import thích hợp. `getCode()` thường là `typeMismatch` đối với lỗi conversion; `getCodes()` còn có các mã chi tiết phục vụ message resolution.

Ngược lại, nếu `age=17` chuyển thành `Integer` thành công nhưng có constraint `@Min(18)`, đó là lỗi **validation**, không phải lỗi chuyển kiểu hoặc thiếu setter.

Phân biệt nhanh:

| Lỗi | Nguyên nhân gốc |
| --- | --- |
| `NotReadablePropertyException` | Không có đường đọc hợp lệ |
| `NotWritablePropertyException` | Không có đường ghi hợp lệ |
| `NullValueInNestedPathException` | Một object trung gian của path là `null` |
| `FieldError` mã `typeMismatch` | Không chuyển được giá trị sang kiểu property |
| `FieldError` mã constraint, ví dụ `NotBlank` | Giá trị không thỏa quy tắc validation |
| `MethodInvocationException` | Accessor ném exception khi thực thi |

Đừng giải quyết lỗi conversion bằng cách thêm setter đã tồn tại, hoặc giải quyết lỗi read-only bằng cách tắt validation.

## 11. Trong Spring MVC: vì sao BindingResult đôi khi không có lỗi?

Controller nhận form:

```java
@PostMapping("/profiles")
public String update(
        @Valid @ModelAttribute("profile") ProfileForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "profiles/edit";
    }
    return "profiles/success";
}
```

Đây là **đoạn minh họa tích hợp**, cần đặt trong controller MVC có import và view phù hợp. `BindingResult` phải đứng ngay sau model attribute mà nó phục vụ.

Mọi tình huống không nhất thiết đều biến thành một `FieldError`:

1. **Field không tồn tại** có thể bị bỏ qua vì `ignoreUnknownFields=true`.
2. **Field có kiểu không chuyển được** thường tạo `FieldError` type mismatch.
3. **Lỗi truy cập không thể phục hồi** có thể ném exception và kết thúc binding trước khi code controller xử lý `BindingResult`.
4. **Constraint validation** chỉ chạy khi có validator/kích hoạt tương ứng.
5. Với `@RequestBody` JSON, Spring dùng `HttpMessageConverter` (thường là Jackson); lỗi JSON có thể là `HttpMessageNotReadableException`, khác `NotReadablePropertyException` của BeanWrapper.

Có thể cấu hình binder cục bộ:

```java
@InitBinder("profile")
void configure(WebDataBinder binder) {
    binder.setIgnoreUnknownFields(false);
    binder.setAllowedFields("name", "age", "address.city");
}
```

Đoạn này chỉ là minh họa, giả định name và DTO phù hợp. `setAllowedFields` giới hạn **trường được phép bind**, còn `setIgnoreUnknownFields(false)` điều chỉnh cách xử lý trường **không có property** sau quá trình lọc. Field không có trong allowlist có thể bị loại khỏi quá trình binding trước khi cơ chế unknown được xét; đừng kỳ vọng cấu hình này tự động phát hiện mọi tham số không thuộc hợp đồng.

**Bảo mật:** không bind trực tiếp client input vào JPA/domain entity có property `role`, `isAdmin`, `creditLimit` hoặc `approved`. Hãy tạo input DTO chỉ gồm các trường được phép nhập. Việc sửa lỗi `NotWritablePropertyException` bằng public setter cho mọi field có thể tạo lỗ hổng *mass assignment*.

## 12. Debug theo thứ tự để không sửa sai

1. **Lấy tên property chính xác.** Đối chiếu request key, exception message và JavaBean property; đặc biệt chú ý chữ hoa, chữ thường, index và dấu chấm.
2. **Xác nhận target object.** Binder đang xử lý class nào? Đối tượng có subtype khác dự kiến không? Trước lúc bind, các nested value có null không?
3. **Phân biệt cơ chế binding.** `@ModelAttribute` JavaBean, direct field access, constructor binding hay `@RequestBody` JSON?
4. **Kiểm tra accessor.** Field cuối có public setter phù hợp? Những đoạn trung gian có getter? Getter/setter có tên chính xác không?
5. **Dùng công cụ của Spring.** Gọi `isReadableProperty(path)` và `isWritableProperty(path)` trên `BeanWrapperImpl` của object test; với nested paths, kết quả còn phụ thuộc object và cấu hình auto-grow.
6. **Xem exception cụ thể.** `NotReadablePropertyException` khác `NotWritablePropertyException`; `NullValueInNestedPathException` khác `TypeMismatchException`.
7. **Kiểm tra cấu hình binder.** `ignoreUnknownFields`, `ignoreInvalidFields`, `autoGrowNestedPaths`, `allowedFields` và `directFieldAccess`.
8. **Xem lỗi đã được ghi.** `binder.getBindingResult().getFieldErrors()` cho thấy conversion/validation errors, nhưng không đại diện cho mọi input đã bị bỏ qua.
9. **Đọc root cause.** Với getter/setter ném exception, sửa code trong method thay vì đổi tên field bừa bãi.
10. **Viết test nhỏ.** Tách BeanWrapper direct access khỏi DataBinder có chính sách bỏ qua field. Không so sánh các cấu hình khác nhau trên cùng binder đã chứa lỗi trước đó.

### Chẩn đoán bằng property descriptor

Có thể dùng `java.beans.Introspector` để kiểm tra method JavaBeans, nhưng `BeanWrapperImpl` là lựa chọn hữu ích khi muốn biết **chính Spring có thể đọc/ghi path trong cấu hình hiện tại hay không**. Dù `isWritableProperty` là `true`, setter vẫn có thể ném exception, conversion vẫn có thể thất bại; đây là kiểm tra khả năng truy cập chứ không phải bảo đảm dữ liệu đầu vào hợp lệ.

## 13. Bảng sự cố thực tế

| Biểu hiện | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Gửi `fristName`, DTO có `firstName` | Sai chính tả input | Sửa key, test bằng request thực tế |
| `status` đọc được nhưng báo not writable | Chỉ getter | Không bind field server-owned; hoặc chọn DTO/constructor binding đúng |
| `secret` ghi được nhưng đọc báo lỗi | Chỉ setter | Bổ sung getter khi có lý do chính đáng, hoặc không đọc ngược secret |
| `address.city` báo null nested path | `address` đang null, auto-grow bị tắt/không làm được | Khởi tạo nested object hoặc sửa cấu trúc |
| `address.city` báo not readable | Thiếu getter ở property trung gian | Kiểm tra `getAddress()` trước `getCity()` |
| `age=xyz` gây typeMismatch | String không chuyển sang Integer | Trả lỗi field, sửa input/converter |
| Setter có mà vẫn có exception | Method setter tự ném lỗi | Kiểm tra nguyên nhân được bọc trong method invocation |
| Không thấy lỗi với field lạ | Binder mặc định ignore unknown | Xem DTO, request key và cờ ignoreUnknownFields |
| Bật ignoreInvalidFields làm mất giá trị | Nested path được bỏ qua | Sửa object graph, chỉ ignore khi nghiệp vụ cho phép |
| Cùng DTO nhận JSON không được | Đường deserialize khác JavaBean bind form | Kiểm tra Jackson/HTTP converter và format JSON |
| Mở setter cho mọi field để sửa lỗi | Mở quyền ghi quá mức | Tạo input DTO, giới hạn allowed fields |

## 14. Tự luyện: tìm lỗi trong object lồng

Cho hai class:

```java
public class PaymentForm {
    private String reference;
    private Account account;

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }

    public Account getAccount() {
        return account;
    }

    // Không có setAccount(Account).
}

public class Account {
    private String iban;

    public String getIban() {
        return iban;
    }

    public void setIban(String iban) {
        this.iban = iban;
    }
}
```

Giả sử `account == null`:

1. `reference` có đọc/ghi được qua JavaBeans không? Vì sao?
2. Vì sao `account.iban` có thể thất bại dù `Account` có `setIban(...)`?
3. Thao tác `setPropertyValue("account", new Account())` trên `BeanWrapperImpl` vì sao gặp lỗi?
4. Nếu input có key `referrence` (sai chính tả), `DataBinder` mặc định có chắc tạo `FieldError` không?
5. Sai kiểu khi bind `reference` khác gì việc vi phạm một constraint `@NotBlank`?

**Đáp án định hướng:** (1) Có cả getter/setter. (2) Cần đi qua `account` hiện null; auto-grow có thể thất bại do thiếu đường ghi vào `account` để gắn object mới. (3) Không có `setAccount` nên có thể ném `NotWritablePropertyException`. (4) Không; unknown field mặc định có thể bị bỏ qua. (5) Conversion/property access là cơ chế khác với validation constraint; cần xem đúng loại lỗi.

## 15. Tóm tắt kiến thức và tài liệu

- **Không tồn tại:** tên property/path sai hoặc không có trong object; `DataBinder` mặc định bỏ qua nhiều unknown fields.
- **Không đọc được:** thiếu đường đọc, thường thiếu getter → `NotReadablePropertyException`.
- **Không ghi được:** thiếu đường ghi, thường thiếu setter → `NotWritablePropertyException`.
- **Object lồng đang null:** kiểm tra auto-grow hoặc khởi tạo object hợp lệ → có thể gặp `NullValueInNestedPathException`.
- **Có setter nhưng input sai kiểu:** xem conversion và `BindingResult`, thường là `typeMismatch`; đừng nhầm với not writable.
- **Không chữa lỗi bằng cách mở tất cả setter hoặc âm thầm bỏ qua mọi field**: cần khớp mô hình dữ liệu, chính sách cho phép ghi và contract của endpoint.

Tài liệu gốc để đối chiếu API và hành vi:

- [Spring Framework — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html): cờ ignore, auto-grow, bind và BindingResult.
- [Spring Framework — BeanWrapperImpl](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/BeanWrapperImpl.html): property access, getter/setter, nested paths.
- [Spring Framework — NotReadablePropertyException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/NotReadablePropertyException.html), [NotWritablePropertyException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/NotWritablePropertyException.html) và [NullValueInNestedPathException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/NullValueInNestedPathException.html): các lỗi truy cập property thường gặp.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): nguyên tắc binding property/constructor và kiểm soát field.
- [Spring Framework — MVC @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): binding/validation của form qua controller.
