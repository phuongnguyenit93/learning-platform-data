# Phân biệt BeanWrapper, BeanUtils và công cụ ánh xạ DTO trong Spring Framework

Trong ứng dụng Spring, một dữ liệu như `name` hoặc `age` có thể xuất hiện dưới nhiều dạng: trường trên JavaBean, giá trị trong HTTP form, thuộc tính của entity, request DTO hay response DTO. Ba nhóm công cụ thường được nhắc đến là **`BeanWrapper`**, **`BeanUtils`** và **DTO mapper** (ánh xạ giữa các object). Chúng có thể cùng “đọc hoặc ghi property”, nhưng giải quyết **ba bài toán khác nhau**:

- **`BeanWrapper`** đọc/ghi property **theo tên tại runtime**, hỗ trợ đường dẫn lồng nhau và chuyển đổi kiểu khi được cấu hình phù hợp.
- **`org.springframework.beans.BeanUtils`** cung cấp các tiện ích JavaBeans tĩnh, trong đó `copyProperties(source, target)` giúp **sao chép các property tương thích** từ object đã có sang object khác. Đây là thao tác sao chép nông, dựa trên tên property.
- **DTO mapper** định nghĩa cách biến đổi giữa các mô hình dữ liệu có ý nghĩa khác nhau (request → domain/entity, entity → response). Có thể viết thủ công hoặc dùng **MapStruct**, **ModelMapper** và công cụ tương tự.

Chọn đúng công cụ giúp code rõ ràng và tránh hai rủi ro phổ biến: tưởng rằng sao chép property đã bao gồm chuyển kiểu/validation, hoặc vô tình chép những trường mà client không được phép thay đổi.

## 1. Tổng quan: giống nhau ở property nhưng khác trách nhiệm

| Tiêu chí | `BeanWrapper` | Spring `BeanUtils` | DTO mapper |
| --- | --- | --- | --- |
| Mục tiêu chính | Truy cập/chỉnh property động theo tên | Tiện ích metadata, khởi tạo và sao chép property | Chuyển đổi một mô hình dữ liệu sang mô hình khác |
| Kiểu API | Giao diện với instance gắn target; `BeanWrapperImpl` là implementation | Các phương thức `static` | Method của class/service hoặc interface mapper |
| Chọn property | Tên tại runtime, ví dụ `"address.city"` | Những property có tên và kiểu tương thích giữa source/target | Quy tắc được khai báo rõ hoặc cấu hình theo convention |
| Đọc/ghi | `getPropertyValue` / `setPropertyValue` | `copyProperties` và các tiện ích JavaBeans | `toEntity`, `toDto`, `updateEntity`… |
| Chuyển kiểu | Có thể sử dụng `ConversionService`/property editors | `copyProperties` không phải engine chuyển đổi kiểu tổng quát | Mapper có thể hỗ trợ quy tắc chuyển đổi, tùy implementation |
| Đối tượng lồng nhau | Có thể truy cập path lồng nhau | Copy tham chiếu property tương ứng, **không deep copy** | Có thể biến đổi sâu hoặc làm phẳng theo mapping rule |
| Validation | Không tự chạy validation cho target | Không tự validate | Không mặc nhiên validate; kiểm tra tại biên/service phù hợp |
| Quyền chỉnh field | Caller phải kiểm soát property được truy cập | Mọi property tương thích có thể được copy trừ khi loại trừ | Có thể chủ động whitelist trường được ánh xạ |
| Dùng tốt nhất | Hạ tầng binding, form, cấu hình động, thư viện thao tác JavaBean | Sao chép đơn giản giữa các bean nội bộ đáng tin cậy | Ranh giới API/domain, bất biến nghiệp vụ, DTO khác cấu trúc |

Điều quan trọng là **khả năng tự động không đồng nghĩa với quyền tự động**. Ví dụ request có field `role` không có nghĩa API đăng ký tài khoản được phép cập nhật `UserEntity.role`. Dù dùng BeanWrapper, BeanUtils hay mapper, ứng dụng vẫn phải chọn field nào được phép nhận.

## 2. BeanWrapper: đọc/ghi JavaBean property qua tên

`org.springframework.beans.BeanWrapper` là một interface trong hạ tầng JavaBeans của Spring; implementation thường dùng là `BeanWrapperImpl`. Nó bao bọc một object và cung cấp quyền truy cập property bằng tên:

~~~java
BeanWrapper wrapper = new BeanWrapperImpl(person);

Object current = wrapper.getPropertyValue("name");
wrapper.setPropertyValue("name", "Mai");
Class<?> type = wrapper.getPropertyType("name");
boolean writable = wrapper.isWritableProperty("name");
~~~

Đây là **đoạn minh họa**, giả sử đã có biến `person` với các JavaBean property phù hợp và import `BeanWrapper`, `BeanWrapperImpl`. `getPropertyValue` trả về `Object`; client cần kiểm tra/cast đúng kiểu khi sử dụng.

### 2.1. “Property” không hoàn toàn đồng nghĩa với “field”

Với JavaBean:

~~~java
public class Person {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Spring nhìn thấy property `name` qua getter/setter. `BeanWrapper` theo cơ chế property access có thể gọi setter khi gán. Nếu object chỉ có `private String name` mà không có accessor thích hợp, field đó không mặc nhiên là JavaBean property ghi được.

Khác biệt này rất quan trọng khi code có:

- Getter tính toán giá trị mà không lưu trực tiếp trong field.
- Setter chuẩn hóa dữ liệu hoặc kiểm tra bất biến.
- Thuộc tính chỉ đọc (getter nhưng không có setter).
- Field nội bộ có tên khác property hiển thị.

Nếu chủ đích là truy cập field trực tiếp, Spring có `DirectFieldAccessor` và chế độ `DataBinder.initDirectFieldAccess()`. Đó là cơ chế khác; không nên dùng BeanWrapper rồi giả định nó ghi được mọi private field.

### 2.2. Nested path, collection và conversion

Với một JavaBean có `Address address`, cách truy cập:

~~~java
wrapper.getPropertyValue("address.city");
wrapper.setPropertyValue("address.city", "Huế");
~~~

có thể truy cập property lồng nhau. Target phải có cấu trúc phù hợp; nếu `address == null`, việc truy cập phụ thuộc tùy chọn auto-grow nested paths và khả năng Spring khởi tạo object con. Không giả định framework có thể tạo mọi object bất biến hoặc mọi collection phức tạp.

`BeanWrapperImpl` có thể cấu hình conversion service:

~~~java
BeanWrapper wrapper = new BeanWrapperImpl(person);
wrapper.setConversionService(new DefaultConversionService());
wrapper.setPropertyValue("age", "26"); // "26" -> Integer
~~~

Ví dụ trên giả định `person.age` là property kiểu `Integer` có setter. `DefaultConversionService` cung cấp nhiều chuyển đổi kiểu cơ bản; nếu chuỗi không chuyển được, việc gán có thể ném lỗi liên quan conversion/type mismatch.

**Điểm phân biệt:** `setPropertyValue("age", "26")` có thể chuyển chuỗi thành số khi có converter, trong khi `BeanUtils.copyProperties(source, target)` **không phải** phép gọi tương đương để tự chuyển tất cả kiểu khác nhau.

### 2.3. BeanWrapper nằm ở đâu trong Spring Data Binding?

`DataBinder` sử dụng hạ tầng property accessor, type conversion và `BindingResult` để kết nối dữ liệu đầu vào với object. Spring MVC có thể dùng `WebDataBinder` để bind query/form parameters. Trong luồng này, BeanWrapper là **một thành phần cấp thấp** phục vụ binding, không phải controller annotation hay bộ giải mã JSON.

Sơ đồ:

~~~text
Dữ liệu đầu vào (form/query)
          |
          v
DataBinder / WebDataBinder
          |
          +--> allowedFields, conversion rules
          |
          v
Bean property accessor (BeanWrapper)
          |
          +--> gọi setter hoặc trả lỗi gán/chuyển kiểu
          v
Target JavaBean
          |
          v
BindingResult / Errors (nếu có lỗi)
~~~

Với `@RequestBody` JSON, Spring MVC thường sử dụng `HttpMessageConverter` và Jackson để deserialize; không nên suy luận rằng mọi JSON field đều đi qua `BeanWrapperImpl`. Đây là những cơ chế khác nhau.

## 3. Spring BeanUtils: tiện ích tĩnh và copyProperties

`org.springframework.beans.BeanUtils` thuộc Spring Beans. Nó có nhiều tiện ích như kiểm tra property descriptor, tìm method tương ứng và khởi tạo class khi phù hợp. Phương thức thường gây nhầm lẫn nhất là:

~~~java
BeanUtils.copyProperties(source, target);
~~~

**Thứ tự là source trước, target sau**. Điều này ngược với một số API của thư viện khác. Import phải rõ ràng:

~~~java
import org.springframework.beans.BeanUtils;
~~~

Đừng nhầm với `org.apache.commons.beanutils.BeanUtils` trong Apache Commons BeanUtils: tên giống nhau nhưng hành vi, dependency và chữ ký API không hoàn toàn giống.

### 3.1. BeanUtils.copyProperties sao chép như thế nào?

Về cơ bản, Spring tìm các property có getter đọc được từ source và setter ghi được ở target với tên/kiểu tương thích, rồi chuyển **giá trị property** từ source sang target.

~~~java
BeanUtils.copyProperties(source, target, "id", "role");
~~~

Tham số cuối là danh sách **tên property cần bỏ qua**. Có overload nhận class editable để giới hạn những property thuộc một kiểu API nhất định. Tập property tương thích phụ thuộc metadata JavaBeans/generics mà Spring phiên bản đó hỗ trợ.

Ví dụ, cả hai object có property `String displayName` và `Integer age` thì hai giá trị thường được copy. Nếu source có `String age` còn target có `Integer age`, **đừng trông đợi** `copyProperties` tự thực hiện parse từ chuỗi sang số; cần conversion riêng hoặc mapper có quy tắc.

### 3.2. Copy nông (shallow copy) và tham chiếu object

Giả sử cả source và target có property `Address address`. `copyProperties` sẽ gán tham chiếu của `address`; nó **không tự tạo một Address độc lập** rồi copy sâu toàn bộ graph.

~~~java
BeanUtils.copyProperties(source, target);
boolean sameAddress = source.getAddress() == target.getAddress();
~~~

Với source có address khác null và hai property tương thích, `sameAddress` là `true`. Sau đó sửa `target.getAddress().setCity(...)` cũng ảnh hưởng object mà source đang tham chiếu.

Đây không phải bug của Spring: hàm này thiết kế cho **sao chép property đơn giản**, không có hợp đồng deep clone. Nếu muốn DTO độc lập với entity, cần tạo object/collection con tương ứng thay vì share mutable reference.

### 3.3. Null, field nhạy cảm và cập nhật một phần

Giả sử client gửi DTO chỉ có `name` và bỏ `email`, nhưng object DTO có `email == null`. Với `copyProperties`, `null` vẫn có thể được copy sang target nếu property tương thích; **không có chính sách “bỏ qua null” mặc định**.

Trong HTTP PATCH, phải phân biệt “field không có mặt” và “field được gửi với null”. Cách đơn giản dùng DTO mà cả hai trạng thái đều thành `null` sẽ **không biểu diễn được khác biệt**. Giải pháp có thể là patch DTO định nghĩa presence, JSON Merge Patch, hoặc ánh xạ tường minh theo hợp đồng.

Với field có thể bị lạm dụng như `id`, `role`, `createdAt`, `ownerId` hoặc `status`, cách này nguy hiểm:

~~~java
BeanUtils.copyProperties(untrustedRequest, persistentUser);
~~~

Nếu tên và kiểu các property khớp nhau, những field đó có thể bị ghi. `BeanUtils.copyProperties(..., "role", "id")` chỉ là **denylist**; DTO mới thêm property trong tương lai vẫn có thể vô tình được copy. Trên ranh giới không tin cậy, ưu tiên request DTO ít field kết hợp **allowlist mapping tường minh**.

### 3.4. BeanUtils không thực hiện những việc gì?

- Không tự validate `@NotNull`, `@NotBlank`, `@Valid` hoặc quy tắc domain.
- Không tự biết field nào thuộc quyền của caller.
- Không tự xử lý quan hệ entity, cascade persistence, transaction hoặc lazy loading.
- Không có cơ chế định nghĩa mapping khi tên khác nhau như `fullName -> displayName` trong lời gọi cơ bản.
- Không tự giải quyết tập collection/object lồng nhau thành một deep copy độc lập.
- Không tự tạo target từ source trong overload `copyProperties` thông dụng; caller phải cấp target.

Nếu cần một trong các hành vi đó, đó là **chính sách mapping/validation/business** riêng, nên được viết rõ để dễ kiểm thử.

## 4. DTO mapper: ánh xạ có ý nghĩa giữa hai mô hình

DTO (Data Transfer Object) là kiểu dữ liệu dùng để trao đổi giữa các lớp/ràng giới như HTTP request/response, message hoặc service API. DTO không nhất thiết có cấu trúc giống persistence entity.

Ví dụ cùng một người dùng có thể có:

~~~text
CreateUserRequest:
  displayName, email, password

UserEntity:
  id, displayName, normalizedEmail, passwordHash,
  role, createdAt, version

UserResponse:
  id, displayName, email
~~~

Ở đây không có phép copy property theo tên nào tự giải quyết đầy đủ:

1. Email trong request có thể được chuẩn hóa trước khi lưu.
2. Mật khẩu phải đi qua password encoder, không ghi plaintext.
3. `id`, `role` và `createdAt` do hệ thống kiểm soát.
4. Response không được lộ password hash.
5. Entity có thể chứa lazy relations hoặc cấu trúc phức tạp không phù hợp JSON contract.

**Mapping** quyết định field nào được chọn, chuyển thành giá trị nào, và field nào bị loại bỏ. Validation, authorization và hành vi nghiệp vụ vẫn ở những tầng có trách nhiệm phù hợp; không coi mapper là nơi tự động cấp quyền hoặc mã hóa an toàn.

### 4.1. Mapper thủ công

Với quy tắc đơn giản, viết Java trực tiếp thường đủ rõ:

~~~java
public record UpdateProfileRequest(String displayName, Integer age) {}
public record ProfileResponse(Long id, String displayName, Integer age) {}

public final class ProfileMapper {
    public ProfileResponse toResponse(UserEntity user) {
        return new ProfileResponse(
                user.getId(),
                user.getDisplayName(),
                user.getAge());
    }

    public void applyAllowedChanges(
            UpdateProfileRequest request, UserEntity target) {
        target.setDisplayName(request.displayName().strip());
        target.setAge(request.age());
    }
}
~~~

Đoạn này **minh họa API mapping**, giả định có class `UserEntity` và các getter/setter tương ứng. Không phải một file chạy độc lập. Nó cố ý chỉ ghi `displayName` và `age`; các property `role`, `id`, `ownerId` vẫn không bị đụng tới. Phải kiểm tra `displayName` khác null/hợp lệ trước khi gọi `strip()` để tránh `NullPointerException`.

Khi DTO chỉ có vài field, explicit code vừa dễ đọc vừa hỗ trợ quy tắc domain riêng. Không bắt buộc thêm thư viện mapper cho một phép biến đổi nhỏ.

### 4.2. MapStruct: tạo mapper ở thời điểm biên dịch

**MapStruct** là annotation processor tạo Java implementation cho mapper interface tại compile time. Có thể khai báo mapping với tên khác và bỏ qua property của entity:

~~~java
@Mapper(componentModel = "spring")
public interface UserMapper {

    @Mapping(target = "id", ignore = true)
    @Mapping(target = "role", ignore = true)
    @Mapping(target = "normalizedEmail", source = "email")
    UserEntity toEntity(CreateUserRequest request);
}
~~~

Đây là **đoạn minh họa**, yêu cầu dependencies `org.mapstruct:mapstruct` và processor `org.mapstruct:mapstruct-processor`, imports `org.mapstruct.Mapper` và `org.mapstruct.Mapping`, cùng các kiểu model tương ứng. `componentModel = "spring"` làm generated implementation được Spring quản lý như một bean.

Điểm mạnh: phương thức Java có kiểu rõ ràng, nhiều lỗi tên property/kiểu sẽ bộc lộ lúc compile thay vì chỉ xuất hiện ở runtime. Có thể dùng `@MappingTarget` để cập nhật object đã tồn tại và cấu hình null behavior/collection policies.

Tuy vậy, **mapping code được sinh ra không đồng nghĩa đã duyệt an toàn**. Mapping tự động theo tên có thể điền field ngoài ý muốn nếu DTO/target thay đổi. Với luồng cập nhật từ client, có thể dùng `@BeanMapping(ignoreByDefault = true)` để chỉ map các trường được chọn:

~~~java
@Mapper(componentModel = "spring")
public interface SafeProfileMapper {
    @BeanMapping(ignoreByDefault = true)
    @Mapping(target = "displayName", source = "displayName")
    @Mapping(target = "age", source = "age")
    void update(UpdateProfileRequest source,
                @MappingTarget UserEntity target);
}
~~~

Đoạn này giả định các class/record đã tồn tại và import `org.mapstruct.BeanMapping`, `Mapping`, `MappingTarget`, `Mapper`. Rule map vẫn cần xét null: với PATCH, gọi `update(...)` có thể ghi `null` nếu chưa cấu hình khác.

MapStruct không tự xử lý business transactions, quyền sở hữu tài nguyên hay mã hóa password. Những bước này cần nằm ở service/assembler được thiết kế rõ.

### 4.3. ModelMapper: mapping bằng quy tắc runtime

**ModelMapper** thường suy luận ánh xạ dựa trên tên và cấu trúc property tại runtime; có thể cấu hình type map hoặc quy tắc tùy chỉnh:

~~~java
ModelMapper mapper = new ModelMapper();
ProfileResponse response =
        mapper.map(entity, ProfileResponse.class);
~~~

Đây chỉ là **minh họa API**; cần dependency `org.modelmapper:modelmapper`, import `org.modelmapper.ModelMapper` và kiểu model phù hợp. Khả năng tạo target như record, immutable object hay class thiếu constructor phụ thuộc cấu hình/hỗ trợ của thư viện; không giả định đoạn này chạy cho mọi DTO bất biến.

Ưu điểm là thiết lập nhanh cho các mapping convention-based. Đổi lại, cần thận trọng với mapping ngầm, tên gần giống nhau, cấu trúc lồng nhau và lỗi chỉ xuất hiện khi chạy. Nếu dùng mapper runtime trong luồng nhạy cảm, kiểm thử rõ field nào được đọc và ghi, thay vì dựa hoàn toàn vào convention.

### 4.4. Nên chọn công cụ nào?

| Tình huống | Lựa chọn phù hợp | Vì sao |
| --- | --- | --- |
| Đọc giá trị property có tên truyền từ metadata | `BeanWrapper` | Truy cập động và nhận metadata JavaBeans |
| Bind tên property, chuyển String thành Integer | `DataBinder`/`BeanWrapper` + conversion service | Có hạ tầng conversion và báo lỗi |
| Copy một số property tương thích giữa bean nội bộ | `BeanUtils.copyProperties` khi target đáng tin cậy | Ngắn gọn, ít quy tắc |
| Request DTO → entity có id/role/ownerId nhạy cảm | Mapper explicit theo allowlist | Kiểm soát field có thể ghi |
| Entity phức tạp → response DTO, đổi tên/nested/flatten | Mapper thủ công hoặc MapStruct | Mapping có chủ ý và có test |
| Có rất nhiều cặp DTO/entity, muốn compile-time checks | MapStruct | Implementation được sinh tại compile time |
| Prototype, mapping theo convention ở runtime | ModelMapper (nếu phù hợp) | Ít boilerplate, cần test nghiêm ngặt |
| Truy cập property nhưng object là Map linh hoạt | Map-specific access / validator | Map keys không mặc nhiên thành JavaBean properties |
| Chỉ muốn kiểm tra `@NotBlank` hoặc `@Min` | Jakarta Bean Validation | Ba công cụ trên không thay validation |

## 5. Ví dụ Java 17+ chạy được: so sánh trực tiếp

Ví dụ này dùng **Spring Framework 6.1.x**, không cần chạy HTTP server, cơ sở dữ liệu hay Spring Boot. Ta tạo một JavaBean profile có thuộc tính lồng nhau, dùng BeanWrapper để gán giá trị, BeanUtils để copy, rồi tự map thành response DTO.

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'spring-property-mapping-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-beans:6.1.15'
    implementation 'org.springframework:spring-core:6.1.15'
}

application {
    mainClass = 'example.PropertyMappingDemo'
}
~~~

Tạo file `src/main/java/example/PropertyMappingDemo.java`:

~~~java
package example;

import org.springframework.beans.BeanUtils;
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.core.convert.support.DefaultConversionService;

public class PropertyMappingDemo {

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

    public static class Profile {
        private String displayName;
        private Integer age;
        private String role;
        private Address address = new Address();

        public Profile() {}

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public record ProfileResponse(
            String displayName,
            Integer age,
            String city) {}

    public static ProfileResponse toResponse(Profile source) {
        return new ProfileResponse(
                source.getDisplayName().strip(),
                source.getAge(),
                source.getAddress().getCity());
    }

    public static void main(String[] args) {
        Profile source = new Profile();
        source.setRole("ADMIN");

        // BeanWrapper: đọc/ghi property động và chuyển kiểu.
        BeanWrapper wrapper = new BeanWrapperImpl(source);
        wrapper.setConversionService(new DefaultConversionService());
        wrapper.setPropertyValue("displayName", "Mai");
        wrapper.setPropertyValue("age", "26");
        wrapper.setPropertyValue("address.city", "Hue");

        System.out.println("wrapper: "
                + wrapper.getPropertyValue("displayName")
                + "/" + source.getAge()
                + "/" + source.getAddress().getCity());

        // BeanUtils: copy những property tương thích.
        Profile copied = new Profile();
        BeanUtils.copyProperties(source, copied);

        System.out.println("copied: "
                + copied.getDisplayName() + "/" + copied.getAge());
        System.out.println("copied-role: " + copied.getRole());
        System.out.println("same-address: "
                + (source.getAddress() == copied.getAddress()));

        // Mapper thủ công: cố ý chỉ tạo response DTO công khai.
        ProfileResponse dto = toResponse(source);
        System.out.println("dto: " + dto);

        // Vì BeanUtils copy nông, chỉnh nested object của copied
        // cũng làm thay đổi object đang được source tham chiếu.
        copied.getAddress().setCity("Da Nang");
        System.out.println("source-city-after-copy-edit: "
                + source.getAddress().getCity());
        System.out.println("dto-city-still: " + dto.city());
    }
}
~~~

Chạy trong thư mục dự án có Gradle Wrapper:

~~~bash
./gradlew run
~~~

Nếu không có wrapper nhưng đã cài Gradle, có thể dùng `gradle run`. Với Windows và wrapper, dùng `.\gradlew.bat run` trong PowerShell.

**Stdout dự kiến từ chương trình** (bỏ thông báo của Gradle):

~~~text
wrapper: Mai/26/Hue
copied: Mai/26
copied-role: ADMIN
same-address: true
dto: ProfileResponse[displayName=Mai, age=26, city=Hue]
source-city-after-copy-edit: Da Nang
dto-city-still: Hue
~~~

Giải thích từng kết quả:

1. `BeanWrapper.setPropertyValue("age", "26")` dùng `DefaultConversionService` để chuyển từ chuỗi sang `Integer`; path `"address.city"` đi đến JavaBean lồng nhau có sẵn.
2. `BeanUtils.copyProperties` đưa `displayName` và `age` từ source sang copied vì tên/kiểu tương thích.
3. `role="ADMIN"` cũng bị copy, minh họa lý do không áp dụng phép copy không giới hạn vào entity khi source là request không tin cậy.
4. `same-address: true` chứng minh đối tượng `Address` không được nhân bản; source và copied chia sẻ tham chiếu.
5. `ProfileResponse` chỉ có `displayName`, `age`, `city`. Field `role` không nằm trong DTO và nested address được lấy thành String `city` độc lập.
6. Sửa `copied.address.city` thay đổi giá trị nhìn từ source, nhưng String đã được đặt vào DTO không tự đổi theo. Nếu response DTO chứa một mutable Address thì cần quyết định deep copy riêng.

Ví dụ cố tình chỉ làm việc với JavaBean để minh họa một cách nhất quán. Nó không tự thực hiện HTTP binding, JSON serialization hoặc Jakarta Bean Validation.

## 6. Từ ví dụ đến thiết kế REST API trong Spring

Giả sử endpoint cập nhật profile có request:

~~~java
public record UpdateProfileRequest(
        String displayName,
        Integer age) {}
~~~

Cách cập nhật có kiểm soát thường gồm các bước:

~~~text
HTTP request
     |
     v
Deserialize request DTO (Jackson đối với JSON)
     |
     v
Validation (@Valid và validator được cấu hình)
     |
     v
Authorization (caller có quyền sửa profile?)
     |
     v
Service tải entity hiện có trong transaction
     |
     v
Explicit mapper cập nhật các field được phép
     |
     v
Service kiểm tra bất biến nghiệp vụ rồi lưu
     |
     v
Mapper tạo response DTO, chỉ trả trường được phép công khai
~~~

Với Spring MVC nhận form data, hạ tầng binder có thể dùng BeanWrapper và `ConversionService`. Với Spring MVC nhận JSON `@RequestBody`, Jackson giải mã object; việc sử dụng BeanWrapper trong binding form không đồng nghĩa JSON mặc định đi qua BeanUtils.

Một controller/service giả định có thể có dạng:

~~~java
@PutMapping("/profiles/{id}")
public ProfileResponse update(
        @PathVariable Long id,
        @Valid @RequestBody UpdateProfileRequest request) {

    ProfileEntity current = profileService.findForUpdate(id);
    authorizationService.assertCanEdit(current);

    profileMapper.applyAllowedChanges(request, current);
    profileService.save(current);

    return profileMapper.toResponse(current);
}
~~~

Đây là **mã minh họa kiến trúc**, giả định đã có các class/service/annotation imports và xử lý transaction. Không nên chạy như một class độc lập. Khi sửa partial (PATCH), phương thức `applyAllowedChanges` cần chính sách rõ ràng về absent field, `null` và replace semantics.

Tránh bind trực tiếp request lên persistence entity vì những property có thể ghi trên JavaBean/entity **không nhất thiết** là field thuộc hợp đồng API. `setAllowedFields(...)` giúp hạn chế field trong WebDataBinder cho form data, còn DTO/mapping explicit bảo vệ ranh giới ngay cả khi dữ liệu đến từ JSON, message queue hoặc test/service nội bộ.

## 7. Các khác biệt kỹ thuật dễ bị hiểu nhầm

### 7.1. BeanWrapper khác BeanUtils kể cả khi cùng thao tác property

`BeanWrapper` dùng được khi tên property chỉ được biết lúc runtime:

~~~java
String property = "displayName";
Object value = wrapper.getPropertyValue(property);
~~~

`BeanUtils.copyProperties` không cung cấp việc “copy một property được chọn theo path động bất kỳ” với cùng ngữ nghĩa; nó chủ yếu duyệt tập property tương thích theo class metadata. Nếu code chỉ cần `source.getDisplayName()`, truy cập Java trực tiếp thường dễ hiểu hơn BeanWrapper.

### 7.2. BeanUtils “copy thành công” không chứng minh đã copy đủ

Nếu một property của source không có property target tương thích, Spring có thể bỏ qua property đó mà không xem đây là lỗi của toàn bộ phép copy. Vì vậy unit test cần xác nhận **các field phải map** và **các field không được map**. Nếu schema thay đổi, những field mới có thể không được copy hoặc vô tình được copy tùy tên/kiểu.

### 7.3. Record, immutable class và constructor mapping

Java `record` không có setter mutable để BeanWrapper gán tùy ý vào component của nó. Cũng không nên giả định `BeanUtils.copyProperties(source, targetRecord)` sẽ thực hiện constructor mapping. Với DTO immutable, ưu tiên khởi tạo thông qua canonical constructor, factory method, builder hoặc mapper hỗ trợ constructor mapping phù hợp.

MapStruct có thể sinh code tạo target theo constructor/builder nếu model được hỗ trợ và cấu hình đúng. Cách dùng cụ thể cần được xác nhận bằng generated source và test compile thay vì dựa vào tên annotation.

### 7.4. Null, collection và lazy association

Ba công cụ không cùng cung cấp chính sách null:

- BeanWrapper có thể gán `null` vào property tham chiếu nếu property cho phép.
- BeanUtils có thể copy `null` và gán collection/object reference, không clone sâu.
- Mapper có thể cấu hình skip null/replace/merge; chính sách này phụ thuộc mapper và tình huống create/update.

Khi map từ JPA entity, đọc lazy association có thể kích hoạt truy vấn ngoài dự kiến hoặc lỗi lazy initialization nếu session không còn mở. Tránh để mapping phản xạ vô tình duyệt toàn bộ object graph. Chọn projection, fetch plan và response DTO theo nhu cầu endpoint.

### 7.5. Property access và bảo mật

Một public setter không đồng nghĩa client được phép gọi setter đó qua API. Nếu request có thể kiểm soát tên property, phải giới hạn tập property được đọc/ghi (allowlist) trước khi gọi `setPropertyValue(...)`. Không cho phép client tùy ý gửi `"role"`, `"class"` hay nested path để điều khiển nội bộ. Sử dụng DTO tường minh và chính sách binding của framework ở mọi điểm nhận untrusted input.

## 8. Kiểm thử và tiêu chí chọn công cụ

Một bộ kiểm thử đúng cần tập trung vào **hợp đồng mong muốn**, không chỉ xác nhận không có exception.

| Nhóm kiểm thử | Điều cần chứng minh |
| --- | --- |
| BeanWrapper property access | Truy cập đúng getter/setter, nested path, kiểm tra readable/writable property |
| BeanWrapper conversion | `"26"` → `Integer(26)`; giá trị sai định dạng có lỗi đúng |
| BeanUtils copy | Property tương thích được copy; không kỳ vọng conversion tự động |
| BeanUtils shallow copy | Mutable nested object/collection có thể bị share reference |
| BeanUtils null handling | `null` có thể ghi đè target nếu cùng property |
| DTO mapper create/update | Chỉ các field thuộc allowlist được map |
| Security | `role`, `ownerId`, `id` và metadata không bị request thay đổi |
| Mapper compile/runtime | Đổi tên property, nested mapping, null policy, immutable DTO có test |
| HTTP binding | Dữ liệu JSON/form đi đúng cơ chế và trả lỗi phù hợp |
| Persistence | Invariants, transaction và cạnh tranh ghi được bảo vệ ở service/database |

Có thể viết unit test cho mapper thủ công bằng cách tạo source, map, rồi assert cả field công khai lẫn field bị loại. Với MapStruct, việc chạy compile và assert generated behavior giúp phát hiện thay đổi schema. Với ModelMapper, kiểm tra cặp source/target cụ thể ở runtime; không dùng một test “map không ném lỗi” làm bằng chứng rằng mapping an toàn.

**Quy tắc chọn nhanh:**

- Khi bài toán là **đọc/ghi property theo tên**, chọn `BeanWrapper`.
- Khi bài toán là **copy đơn giản giữa JavaBean nội bộ đáng tin cậy**, có thể dùng `BeanUtils.copyProperties`.
- Khi bài toán là **định nghĩa hợp đồng chuyển dữ liệu giữa DTO và domain/entity**, chọn **mapping tường minh**, viết bằng tay hoặc công cụ như MapStruct.
- Khi bài toán là **kiểm tra dữ liệu hợp lệ**, dùng validation; khi cần **phân quyền**, dùng authorization; khi cần **bảo vệ tính toàn vẹn lưu trữ**, dùng domain rule và database constraints.

## 9. Câu hỏi tự kiểm tra

1. `BeanWrapper.setPropertyValue("age", "26")` có thể thành công dù `age` là `Integer`. Vì sao `BeanUtils.copyProperties` không được xem là công cụ thay thế chuyển kiểu?
2. Nếu `source.address == target.address` sau `copyProperties`, điều gì xảy ra khi sửa `target.address.city`?
3. Vì sao việc bỏ qua `role` bằng danh sách ignore của `BeanUtils` vẫn cần review khi model thay đổi?
4. Với request DTO và entity có tên property khác nhau, mapper có lợi thế gì hơn copy tự động?
5. Trong Spring MVC, luồng bind form khác luồng deserialize `@RequestBody` JSON ở điểm nào?
6. Khi một DTO dùng record hoặc immutable class, vì sao việc gán property như JavaBean thông thường có thể không phù hợp?
7. Trong HTTP PATCH, “không gửi field” khác “gửi field = null” như thế nào?
8. Khi MapStruct sinh mapper, những điều gì vẫn phải được kiểm thử về bảo mật, null và mapping lồng nhau?

**Kết luận:** `BeanWrapper` là công cụ **truy cập và chuyển đổi giá trị property tại runtime**; `BeanUtils` là bộ **tiện ích JavaBeans và sao chép property nông**; DTO mapper là nơi **mô tả có chủ đích cách biến đổi dữ liệu giữa các mô hình**. Dùng công cụ ở đúng tầng, giữ hợp đồng dữ liệu rõ ràng và chỉ cập nhật field được phép sẽ giúp ứng dụng Spring dễ bảo trì và an toàn hơn.

### Tài liệu tham khảo

- Spring Framework — JavaBeans `BeanWrapper`: https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html
- Spring Framework API — `BeanWrapper`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/BeanWrapper.html
- Spring Framework API — `BeanUtils`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/BeanUtils.html
- Spring Framework — Validation, Data Binding, and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- MapStruct — Reference Guide: https://mapstruct.org/documentation/stable/reference/html/
- ModelMapper — User Manual: https://modelmapper.org/user-manual/
