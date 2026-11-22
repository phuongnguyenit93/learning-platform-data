# Phân biệt invalid field với unknown field trong Spring DataBinder

Khi Spring gắn dữ liệu ngoài vào một đối tượng Java theo **đường dẫn thuộc tính (property path)**, không phải mọi lỗi đều có cùng ý nghĩa. Hai thuật ngữ dễ nhầm trong API `DataBinder` là **unknown field** và **invalid field**:

- **Unknown field (trường không được nhận diện)**: tên trường từ dữ liệu đầu vào **không tương ứng với một thuộc tính có thể gắn** trên đối tượng đích. Ví dụ đối tượng `Profile` chỉ có `age` và `address` nhưng request gửi `nickname`.
- **Invalid field (trường có đường dẫn không truy cập được)**: đường dẫn trỏ tới thuộc tính có trong mô hình đối tượng, nhưng **không thể đi đến đó trong đồ thị đối tượng hiện tại**. Ví dụ `address.city` là đường dẫn hợp lệ về cấu trúc, nhưng `profile.address == null` và quá trình binding không tự tạo `Address`.

Trong thuật ngữ của `DataBinder#setIgnoreInvalidFields`, *invalid* **không có nghĩa** “giá trị vi phạm `@NotBlank`, `@Min`” và cũng không đồng nghĩa với “không chuyển được chuỗi sang số”. Những lỗi ấy cần phân loại riêng.

Bài học này áp dụng chủ yếu cho **property binding bằng `DataBinder.bind(PropertyValues)`** của Spring Framework 6.x, với ví dụ Java 17. Nó cũng giải thích liên hệ với Spring MVC `@ModelAttribute`, các cờ cấu hình và cách kiểm thử.

## 1. Trước tiên, phải hiểu đường dẫn thuộc tính

Spring dùng tên khóa của dữ liệu đầu vào để tìm vị trí gắn vào đối tượng Java:

```text
Profile
├── age: Integer
└── address: Address
    └── city: String

"age"           -> Profile.age
"address.city"  -> Profile.address.city
"nickname"      -> không có thuộc tính tương ứng
```

Ở chế độ mặc định, `DataBinder` gắn thuộc tính theo quy ước JavaBean: có setter như `setAge(...)` và `setAddress(...)`, getter dùng để đi qua các đối tượng lồng nhau, cùng các kiểu có thể chuyển đổi. Dấu chấm trong `address.city` biểu thị truy cập một thuộc tính của đối tượng con, không phải một tên trường Java duy nhất.

Hãy tách ba câu hỏi:

1. **Tên thuộc tính có tồn tại và có thể ghi không?** Nếu không, đây là ứng viên của *unknown field*.
2. **Đường dẫn có thể đi qua tất cả đối tượng trung gian không?** Nếu một nhánh `null` không được tự tạo, đây là *invalid field* theo nghĩa “đường dẫn không truy cập được”.
3. **Giá trị có chuyển được sang kiểu đích và thỏa quy tắc không?** Nếu không, đây có thể là lỗi chuyển kiểu hoặc lỗi validation, với cơ chế xử lý riêng.

Một đường dẫn như `address.city` có thể “đúng về cấu trúc” nhưng “không thể đi được ở thời điểm binding”. Đó là khác biệt quan trọng nhất giữa hai khái niệm của đề bài.

## 2. Bảng so sánh nhanh

| Tình huống | Có thuộc tính tương ứng? | Vấn đề thực sự | Cơ chế liên quan |
| --- | --- | --- | --- |
| `nickname=Lan` nhưng `Profile` không có `nickname` | Không | **Unknown field** | `setIgnoreUnknownFields(...)` |
| `address.city=Hanoi`, `address == null`, tắt tự tạo nhánh | Có | **Invalid field** do nhánh trung gian không truy cập được | `setIgnoreInvalidFields(...)`; `setAutoGrowNestedPaths(...)` |
| `age=abc` với `age: Integer` | Có; truy cập được | **Type mismatch**: không chuyển kiểu | Cơ chế conversion và `BindingResult` |
| `age=16` với quy tắc tuổi ít nhất 18 | Có; chuyển kiểu được | **Validation failure**: vi phạm quy tắc | `Validator`/`validate()` hoặc Bean Validation |
| `role=ADMIN` nhưng `setAllowedFields("age")` | Có thể có `role` trên bean | **Suppressed/disallowed field**: cố tình không cho bind | `setAllowedFields(...)`; `getSuppressedFields()` |

Cột đầu vào **không phải** kết quả kiểm tra an toàn. Một trường được Spring nhận diện và bind thành công vẫn có thể không được phép sửa về mặt nghiệp vụ. Cần dùng DTO chuyên biệt và giới hạn những trường được phép gắn từ bên ngoài.

## 3. Unknown field: tên trường không có đích để gắn

Giả sử:

```java
public class Profile {
    private Integer age;

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
```

Dữ liệu có khóa `age` thì tìm thấy setter phù hợp. Dữ liệu có khóa `nickname` thì đối tượng `Profile` không có thuộc tính tương ứng. Đây là unknown field. Đoạn Java trên chỉ minh họa cấu trúc bean; ví dụ chạy đầy đủ nằm ở mục 7.

### 3.1. setIgnoreUnknownFields mặc định là true

Với `DataBinder` thông thường:

```java
binder.setIgnoreUnknownFields(true);
```

Đây là giá trị **mặc định**. Khi bind `nickname=Lan`, binder sẽ **bỏ qua trường không được nhận diện**. Nó không tự tạo `nickname` trong bean, cũng không tự chuyển trường này thành lỗi của `Validator`. Tùy yêu cầu API, việc bỏ qua là thuận tiện cho form nhận thêm dữ liệu phụ, nhưng có thể che giấu lỗi chính tả của client.

Ví dụ client gửi `ag=20` thay vì `age=20`: nếu `ag` không có trên bean, mặc định Spring có thể bỏ qua, khiến `age` giữ giá trị trước đó hoặc `null`. Vì vậy, đừng coi việc `bind()` không ném exception là bảo đảm mọi khóa từ client đã được dùng.

### 3.2. setIgnoreUnknownFields(false) để yêu cầu khớp thuộc tính

Muốn phát hiện tên không được nhận diện ở bước property binding:

```java
binder.setIgnoreUnknownFields(false);
```

Khi đó, lời gọi `bind(...)` với một khóa không khớp có thể ném `NotWritablePropertyException` (một dạng `InvalidPropertyException` trong Spring Beans). Với ví dụ `nickname`, đây là lỗi về **khả năng truy cập thuộc tính**, không phải ràng buộc kiểm tra độ dài hay định dạng.

**Không giả định** chế độ nghiêm ngặt sẽ tạo ra `FieldError` bên trong `BindingResult` giống lỗi `age=abc`. Những trường hợp unknown/invalid có thể bị bỏ qua hoặc ném exception tùy cấu hình; bạn phải kiểm thử nhánh xử lý exception tương ứng.

Phạm vi của cờ này là property binding với `bind(PropertyValues)`. Nó không có nghĩa mọi thao tác đọc giá trị qua `BindingResult`, mọi kiểu tạo đối tượng bằng constructor, hay mọi request JSON đều tuân theo cờ tương tự.

## 4. Invalid field: đường dẫn có thật nhưng không truy cập được

Giả sử `Profile` có thuộc tính `address: Address` và `Address` có `city: String`. Dữ liệu gửi:

```text
address.city=Hanoi
```

Tên đường dẫn **đúng**. Nhưng nếu `profile.getAddress() == null`, binder phải đi qua một nhánh chưa tồn tại để gọi `setCity("Hanoi")`.

### 4.1. Tại sao auto-grow làm thay đổi kết quả?

`DataBinder` mặc định bật:

```java
binder.setAutoGrowNestedPaths(true);
```

Nếu kiểu đối tượng lồng nhau có thể khởi tạo theo cách mà Spring hỗ trợ (chẳng hạn `Address` có constructor không tham số công khai), binder có thể tạo đối tượng `Address` rồi gắn `city`. Khi đó **không còn nhánh null cản trở**, nên `address.city` bind thành công.

Để thấy thế nào là *invalid field*, ví dụ học tập chủ động tắt cơ chế này:

```java
binder.setAutoGrowNestedPaths(false);
```

Nếu `address` vẫn `null`, quá trình truy cập `address.city` sẽ gặp đường dẫn không thể đi tiếp. Tình huống điển hình phát sinh `NullValueInNestedPathException`, một lớp con của `InvalidPropertyException`.

Không nhầm với unknown field: tên `city` tồn tại trong `Address`. Vấn đề là **instance của `Address` chưa tồn tại ở vị trí cần đi qua**.

### 4.2. setIgnoreInvalidFields mặc định là false

Mặc định:

```java
binder.setIgnoreInvalidFields(false);
```

Binder không chủ động bỏ qua các đường dẫn tồn tại nhưng đang không truy cập được. Nếu gặp nhánh `null` và không thể tự tạo, binding có thể ném exception. Bật tùy chọn:

```java
binder.setIgnoreInvalidFields(true);
```

thì binder có thể **bỏ qua tham số gắn vào phần không tồn tại của đồ thị đối tượng**, chẳng hạn `address.city` khi `address == null` và tự tạo nhánh đã tắt.

**Điểm cần nhớ:** đây không phải cờ “bỏ qua mọi giá trị không hợp lệ”. Nó không thay thế conversion, validation, phân quyền, giới hạn dữ liệu đầu vào hoặc xử lý mọi exception khác.

### 4.3. Bảng tác động của ba cờ trong trường hợp cụ thể

Giả sử `Profile.address == null`, `Address` là JavaBean có constructor mặc định và request chứa `address.city=Hanoi`:

| autoGrowNestedPaths | ignoreInvalidFields | Kết quả kỳ vọng |
| --- | --- | --- |
| `true` (mặc định) | `false` (mặc định) | Spring tự tạo `Address` và gắn `city` nếu khởi tạo được |
| `false` | `false` | Đường dẫn không truy cập được; thường ném `NullValueInNestedPathException` |
| `false` | `true` | Bỏ qua giá trị gắn cho nhánh không tồn tại, `address` vẫn `null` |

Nếu `Address` không thể khởi tạo, hoặc property path có vấn đề khác, có thể xảy ra lỗi khác. Cần đọc đúng exception thực tế thay vì khái quát rằng mọi đường dẫn lồng nhau đều tự tạo thành công.

## 5. Đừng đánh đồng invalid field với invalid value

Từ “invalid” trong tài liệu validation đôi khi nghĩa là “giá trị sai”. Nhưng `setIgnoreInvalidFields(...)` nói về **khả năng truy cập đường dẫn trong binding**.

### 5.1. Một trường đúng tên nhưng chuyển kiểu thất bại

Với `age: Integer`, chuỗi `age=abc` trỏ tới property có thật, thuộc tính cũng truy cập được. Lỗi nằm ở việc `"abc"` không thể chuyển thành `Integer`. Trong binding thông thường, Spring ghi `FieldError`, thường có mã cơ sở `typeMismatch`, vào `BindingResult`.

```java
BindingResult result = binder.getBindingResult();
for (FieldError error : result.getFieldErrors()) {
    System.out.println(error.getField()
            + " -> bindingFailure=" + error.isBindingFailure());
}
```

`FieldError.isBindingFailure()` giúp nhận biết lỗi đến từ quá trình binding; kiểm thử mã thông báo lỗi không nên dựa vào nguyên văn thông báo của một phiên bản Spring cụ thể.

Bật `setIgnoreUnknownFields(true)` hoặc `setIgnoreInvalidFields(true)` **không làm `age=abc` trở thành tuổi hợp lệ**, và cũng không nên dùng các cờ đó để che giấu lỗi chuyển kiểu.

### 5.2. Một trường đúng kiểu nhưng không đạt quy tắc

Chuỗi `age=16` có thể chuyển thành `Integer 16`. Nếu quy tắc ứng dụng là “tuổi từ 18”, chỉ sau khi chạy Spring `Validator` hoặc Bean Validation thích hợp mới có lỗi kiểm tra ràng buộc.

```java
@Override
public void validate(Object target, Errors errors) {
    Profile profile = (Profile) target;
    if (profile.getAge() != null && profile.getAge() < 18) {
        errors.rejectValue("age", "age.min", "Age must be at least 18");
    }
}
```

Đoạn này là phần triển khai của một `org.springframework.validation.Validator`; ví dụ hoàn chỉnh sẽ chỉ rõ lớp, imports và cách đăng ký. Lỗi do `errors.rejectValue(...)` thêm thường có `isBindingFailure() == false`.

**Không có cùng kết quả xử lý cho bốn trường hợp:**

- Unknown: binder không tìm thấy property phù hợp.
- Invalid path: binder biết property nhưng không thể tiếp cận nó.
- Type mismatch: binder tìm thấy và tiếp cận được property nhưng không chuyển giá trị thành kiểu Java.
- Validation failure: giá trị Java tồn tại nhưng vi phạm ràng buộc.

## 6. Unknown, invalid và suppressed field có phải một không?

**Không.** `BindingResult.getSuppressedFields()` dùng để nhận biết những trường bị loại khỏi binding bởi chính sách allowed/disallowed fields. Ví dụ:

```java
binder.setAllowedFields("age", "address.city");
```

Nếu đối tượng thực tế cũng có property `role` nhưng client cố gửi `role=ADMIN`, binder sẽ không gắn `role` vì không nằm trong danh sách cho phép. Sau khi bind, `getSuppressedFields()` có thể cho biết `role` đã bị chặn.

Điều này **khác** với `nickname` không hề tồn tại trên bean. Unknown field mặc định bị bỏ qua không tự động trở thành suppressed field. Cũng không nên dựa vào `getSuppressedFields()` như một danh sách đầy đủ mọi loại lỗi binding; nó mang ý nghĩa cụ thể là các giá trị bị chính sách binding loại bỏ.

Về bảo vệ dữ liệu, **chỉ tắt bỏ qua unknown field là chưa đủ**. Một trường nhạy cảm như `role` có thể *tồn tại thật* và có setter; nó sẽ không bị coi là unknown. Với dữ liệu ngoài, ưu tiên DTO chỉ chứa trường cần thiết, constructor binding khi phù hợp, và danh sách allowed fields cho property binding.

## 7. Ví dụ Java 17 chạy được: quan sát từng loại lỗi

Ví dụ này sử dụng **Spring Framework 6.2** trực tiếp, không cần HTTP server. Mỗi kịch bản có một đối tượng `Profile` và một `DataBinder` riêng để kết quả không bị ảnh hưởng bởi các kịch bản khác.

Cấu trúc thư mục:

```text
spring-field-paths/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/paths/FieldPathDemo.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'spring-field-paths'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.paths.FieldPathDemo'
}
```

`spring-context` kéo theo các phụ thuộc cần thiết để dùng `DataBinder`, `MutablePropertyValues` và `Validator`. Trong ứng dụng Spring Boot có dependency management, hãy để Boot quản lý phiên bản các thành phần Spring thay vì chép phiên bản cố định này.

Tạo tệp `src/main/java/demo/paths/FieldPathDemo.java` với nội dung:

```java
package demo.paths;

import org.springframework.beans.InvalidPropertyException;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;

public class FieldPathDemo {

    // Bean con: có constructor không tham số để Spring có thể auto-grow.
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
        private Integer age;
        private Address address;

        public Profile() {
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

    public static class ProfileValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return Profile.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Profile profile = (Profile) target;
            if (profile.getAge() != null && profile.getAge() < 18) {
                errors.rejectValue(
                        "age", "age.min", "Age must be at least 18");
            }
        }
    }

    private static void bindCase(
            String label,
            String field,
            String inputValue,
            boolean ignoreUnknown,
            boolean ignoreInvalid,
            boolean autoGrow) {

        Profile profile = new Profile();
        DataBinder binder = new DataBinder(profile, "profile");
        binder.setIgnoreUnknownFields(ignoreUnknown);
        binder.setIgnoreInvalidFields(ignoreInvalid);
        binder.setAutoGrowNestedPaths(autoGrow);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add(field, inputValue);

        try {
            binder.bind(values);
            BindingResult result = binder.getBindingResult();
            String city = profile.getAddress() == null
                    ? "null" : profile.getAddress().getCity();

            System.out.println(label
                    + ": OK; errors=" + result.getErrorCount()
                    + "; city=" + city
                    + "; age=" + profile.getAge());

            for (FieldError error : result.getFieldErrors()) {
                System.out.println("  " + error.getField()
                        + ": bindingFailure=" + error.isBindingFailure());
            }
        } catch (InvalidPropertyException exception) {
            // Bắt các lỗi property path nghiêm ngặt, không coi là
            // FieldError thông thường trong BindingResult.
            System.out.println(
                    label + ": " + exception.getClass().getSimpleName());
        }
    }

    private static void validationCase() {
        Profile profile = new Profile();
        DataBinder binder = new DataBinder(profile, "profile");
        binder.setValidator(new ProfileValidator());

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("age", "16");

        binder.bind(values);
        System.out.println("rule-before-validate: errors="
                + binder.getBindingResult().getErrorCount());

        binder.validate();
        FieldError error =
                binder.getBindingResult().getFieldError("age");

        System.out.println("rule-after-validate: errors="
                + binder.getBindingResult().getErrorCount()
                + "; bindingFailure=" + error.isBindingFailure());
    }

    public static void main(String[] args) {
        // Trường không tồn tại trên Profile.
        bindCase("unknown-ignored",
                "nickname", "Lan", true, false, false);
        bindCase("unknown-strict",
                "nickname", "Lan", false, false, false);

        // Trường tồn tại nhưng Profile.address đang null.
        bindCase("invalid-strict",
                "address.city", "Hanoi", true, false, false);
        bindCase("invalid-ignored",
                "address.city", "Hanoi", true, true, false);
        bindCase("invalid-auto-grow",
                "address.city", "Hanoi", true, false, true);

        // Thuộc tính truy cập được nhưng giá trị sai kiểu.
        bindCase("type-mismatch",
                "age", "abc", true, false, false);

        // Thuộc tính đúng kiểu nhưng giá trị sai quy tắc.
        validationCase();
    }
}
```

Với Gradle đã cài đặt, chạy từ thư mục dự án:

```bash
gradle -q run
```

Nếu dự án đã có Gradle Wrapper, có thể thay bằng `./gradlew -q run` (Unix/macOS) hoặc `gradlew.bat -q run` (Windows). Khi Gradle tải dependency thành công, đầu ra do phương thức `main` tạo ra dự kiến là:

```text
unknown-ignored: OK; errors=0; city=null; age=null
unknown-strict: NotWritablePropertyException
invalid-strict: NullValueInNestedPathException
invalid-ignored: OK; errors=0; city=null; age=null
invalid-auto-grow: OK; errors=0; city=Hanoi; age=null
type-mismatch: OK; errors=1; city=null; age=null
  age: bindingFailure=true
rule-before-validate: errors=0
rule-after-validate: errors=1; bindingFailure=false
```

Các exception trong ví dụ là các loại điển hình đối với đường dẫn đã chọn và Spring 6.2. Nếu thay đổi chế độ truy cập field, khả năng tự tạo đối tượng hoặc trình chuyển đổi, kết quả có thể khác; khi kiểm thử hãy kiểm tra trực tiếp loại exception và trạng thái bean.

### 7.1. Phân tích sáu lần binding

- **`unknown-ignored`:** `nickname` không có trên `Profile`. Với `ignoreUnknownFields=true`, Spring bỏ qua; không thêm property hoặc lỗi validation.
- **`unknown-strict`:** cùng một khóa, nhưng `ignoreUnknownFields=false`. Spring từ chối vì không có property có thể ghi và ném `NotWritablePropertyException`.
- **`invalid-strict`:** `address.city` có cấu trúc hợp lệ, nhưng `address=null` và `autoGrowNestedPaths=false`. Vì `ignoreInvalidFields=false`, binder không bỏ qua đường dẫn và phát sinh `NullValueInNestedPathException`.
- **`invalid-ignored`:** cùng một đường dẫn null, nhưng `ignoreInvalidFields=true`. Spring bỏ qua giá trị cần gắn; `address` vẫn `null`.
- **`invalid-auto-grow`:** bật `autoGrowNestedPaths=true`, Spring có thể tạo `Address` thông qua constructor mặc định rồi đặt `city="Hanoi"`.
- **`type-mismatch`:** `age` tồn tại và có thể truy cập, nhưng chuỗi `"abc"` không chuyển thành `Integer`. Binder ghi lỗi chuyển kiểu; thuộc tính `age` của bean mới vẫn `null`.

`validationCase()` được đặt riêng để chứng minh giá trị `16` chuyển được thành `Integer 16`. Sau `bind()` có 0 lỗi; sau `validate()` có 1 lỗi từ quy tắc của `ProfileValidator`, với `isBindingFailure=false`.

Đặc biệt, hai ví dụ *unknown-ignored* và *invalid-ignored* đều không tạo `FieldError`. Bỏ qua một giá trị đầu vào có thể tạo ra bean **thiếu dữ liệu mà không có lỗi**. Không nên chỉ gọi `result.hasErrors()` rồi kết luận mọi trường client gửi đã được nhận.

## 8. Khi thay đổi cấu hình, kiểm tra đúng điều gì?

| Cấu hình | Giá trị mặc định của DataBinder | Hiệu ứng chủ yếu |
| --- | --- | --- |
| `setIgnoreUnknownFields(boolean)` | `true` | Bỏ qua hoặc từ chối khóa không có property tương ứng |
| `setIgnoreInvalidFields(boolean)` | `false` | Bỏ qua hoặc từ chối đường dẫn hiện không thể truy cập |
| `setAutoGrowNestedPaths(boolean)` | `true` | Có thể tự tạo đối tượng lồng nhau còn null trong property binding |
| `setAllowedFields(String...)` | Mọi trường có thể được cân nhắc | Chỉ cho phép các đường dẫn được liệt kê/pattern hợp lệ |
| `setRequiredFields(String...)` | Không bắt buộc trường nào | Kiểm tra sự có mặt của trường ở giai đoạn binding |
| `setValidator(...)` hoặc `addValidators(...)` | Không nhất thiết có validator tùy chỉnh | Đăng ký bộ kiểm tra ràng buộc, được gọi khi chạy `validate()` |

Ba cờ đầu **không có tác dụng giống nhau** và không nên bật/tắt tùy tiện để “cho request chạy qua”. Chẳng hạn nếu tắt ignore unknown để bắt lỗi typo, ứng dụng phải có đường xử lý exception và hợp đồng lỗi HTTP phù hợp; chỉ bật cờ không tự tạo một phản hồi 400 có cấu trúc hoàn chỉnh.

**Phạm vi:** những cờ trên mô tả setter/field binding với `bind(PropertyValues)`. Chúng không áp dụng như vậy cho constructor binding (`DataBinder.construct(...)`), vốn lựa chọn giá trị theo tham số constructor. Cần đọc tài liệu API của phiên bản Spring đang chạy khi trộn nhiều chiến lược binding.

## 9. Liên hệ với @ModelAttribute và @RequestBody

### 9.1. Form/query với @ModelAttribute

Trong Spring MVC, `WebDataBinder` xử lý dữ liệu thích hợp từ request để gắn vào đối tượng `@ModelAttribute`. Đây là nơi các quy tắc property path và cấu hình binder có ý nghĩa rõ ràng.

Ví dụ minh họa trong một controller đã khai báo các bean cần thiết:

```java
@InitBinder("profile")
void configureProfile(WebDataBinder binder) {
    binder.setAllowedFields("age", "address.city");
    binder.setIgnoreUnknownFields(false);
    binder.setIgnoreInvalidFields(false);
}
```

Đoạn mã trên là **phần của controller**, chưa phải chương trình độc lập. Nếu endpoint có `@ModelAttribute("profile") Profile profile`, hãy bảo đảm `Profile` là kiểu có thể bind và cơ chế tạo đối tượng lồng nhau phù hợp. Tên `profile` trong `@InitBinder` phải khớp tên đối tượng mà binder dùng.

Không đưa ra giả định rằng mọi exception phát sinh từ unknown/invalid path đều tự động trở thành `BindingResult` với một `FieldError`: một số lỗi property path nghiêm ngặt có thể thoát ra dưới dạng exception. Để thiết kế API, hãy quyết định rõ nên bỏ qua khóa lạ, trả lỗi, hoặc chỉ chấp nhận danh sách trường cho phép.

### 9.2. JSON với @RequestBody

Với `@RequestBody` nhận JSON, Spring thường dùng `HttpMessageConverter` (ví dụ Jackson) để tạo DTO. Một JSON có thuộc tính không nhận diện được chịu các quy tắc cấu hình **JSON deserializer/Jackson**, chứ không tự động theo `DataBinder#setIgnoreUnknownFields`. Nếu JSON có đối tượng lồng nhau `address`, việc tạo DTO lồng nhau cũng thuộc cơ chế deserialization tương ứng.

Vì vậy, **không lấy hành vi ignore unknown/invalid trong `DataBinder.bind(PropertyValues)` để suy ra hành vi JSON**. Hãy kiểm tra từng đường nhận dữ liệu: form/query, constructor binding, JSON body và các cấu hình framework cụ thể.

### 9.3. BindingResult và phản hồi HTTP

Trong một controller nhận form, `BindingResult` đặt ngay sau đối tượng `@ModelAttribute` có thể chứa lỗi chuyển kiểu và validation. Nhưng unknown/invalid path ở chế độ nghiêm ngặt có thể phát sinh exception trong quá trình bind, cần xử lý theo cách thích hợp. Không dùng `getSuppressedFields()` để suy diễn tất cả những trường không nhận diện được.

Ở tầng HTTP, không trả tên exception nội bộ, giá trị bí mật hoặc stack trace cho client. Có thể thiết kế lỗi công khai như “trường không được hỗ trợ”, “không thể gắn đường dẫn thuộc tính” hoặc “kiểu dữ liệu không hợp lệ” tùy loại lỗi, và kiểm thử bằng request thực tế.

## 10. Các trường hợp biên cần nắm

### 10.1. Đường dẫn lồng nhau có kiểu không khởi tạo được

`autoGrowNestedPaths=true` là khả năng tự tạo nhánh phù hợp, **không phải cam kết** mọi kiểu đều tạo được. Nếu thiếu constructor thích hợp, property bị chặn, cấu trúc collection phức tạp hoặc không đủ thông tin kiểu, có thể xảy ra exception khác. Đừng coi `ignoreInvalidFields=true` là giải pháp tổng quát cho mọi lỗi khởi tạo.

### 10.2. Sai chính tả ở giữa đường dẫn

Nếu client gửi `address.ctiy` thay cho `address.city`, khi đường dẫn tới `Address` được truy cập, tên thuộc tính cuối `ctiy` không tồn tại. Tình huống đó liên quan đến **unknown property**, khác với `address.city` đúng tên nhưng `address == null` khi không tự tạo nhánh. Trong một số cấu trúc phức tạp, lỗi xảy ra ở chặng nào trước còn phụ thuộc trạng thái đối tượng và cài đặt accessor, nên cần kiểm chứng với từng DTO thật.

### 10.3. Property chỉ đọc

Có getter nhưng không có setter phù hợp trong chế độ JavaBean property binding thì property không thể ghi. Một trường client gửi có thể dẫn đến `NotWritablePropertyException` trong chế độ nghiêm ngặt. Không suy luận rằng “có getter” đã đủ để coi đường dẫn là nơi có thể bind.

### 10.4. Chỉ số của collection và giới hạn auto-grow

Các đường dẫn như `items[0].name` còn phụ thuộc collection có phần tử tương ứng hay có thể mở rộng. `DataBinder` có giới hạn tăng collection tự động để tránh cấp phát không kiểm soát. Khi nhận đầu vào không đáng tin cậy, nên giới hạn số phần tử, độ sâu và chỉ chấp nhận field cần thiết; một chỉ số quá lớn không chỉ đơn giản là “unknown field”.

### 10.5. Trường bị cấm có thể vẫn là trường tồn tại

Nếu `role` thực sự có setter, `setIgnoreUnknownFields(false)` sẽ **không chặn riêng trường đó chỉ vì nguy hiểm**. Cần DTO giới hạn quyền sửa và cấu hình allowed fields theo hợp đồng đầu vào. Giới hạn đường dẫn cho phép đặc biệt quan trọng khi bind nhiều thuộc tính lồng nhau từ request.

### 10.6. Invalid field khác validation failure trên đối tượng lồng nhau

Một `Address` đã được tạo và có `city=""` là **đường dẫn truy cập được**. Muốn từ chối tên thành phố trống, phải kiểm tra quy tắc (Spring `Validator` hoặc Bean Validation). Việc bật `setIgnoreInvalidFields(false)` sẽ không tự động bác bỏ chuỗi rỗng này.

## 11. Cách kiểm thử có giá trị

Lập kế hoạch test tách từng trường hợp; tránh chỉ dựa vào một boolean `hasErrors()`.

| Test | Kết luận cần xác minh |
| --- | --- |
| Unknown mặc định | Không tạo property lạ; `bind()` có thể hoàn tất mà không có `FieldError` |
| Unknown nghiêm ngặt | `setIgnoreUnknownFields(false)` từ chối khóa lạ; xác định exception |
| Invalid khi tắt auto-grow | `address == null`, nhập `address.city` làm đường dẫn không truy cập được |
| Invalid bị bỏ qua | `setIgnoreInvalidFields(true)` bỏ qua nhánh phù hợp; xác nhận bean không bị sửa |
| Auto-grow hoạt động | Tạo được `Address` khi có constructor phù hợp và gắn được `city` |
| Type mismatch | `age=abc` tạo lỗi chuyển kiểu có `isBindingFailure() == true` |
| Validation failure | `age=16` bind được; sau `validate()` có lỗi quy tắc |
| Disallowed field | `setAllowedFields(...)` chặn field; `getSuppressedFields()` phản ánh điều đó |
| Spring MVC form | Trả mã lỗi phù hợp cho lỗi binding hoặc path nếu endpoint yêu cầu strict |
| JSON body | Hành vi đối với JSON unknown properties được kiểm tra qua cấu hình deserializer, không suy ra từ DataBinder |

Với chương trình console, mỗi test nên tạo bean và binder mới. Với web MVC, dùng `MockMvc` để mô phỏng form/query, xác nhận mã phản hồi và không lộ nội dung nội bộ. Nếu chính ứng dụng có lớp chuyển exception thành lỗi API, test cả nhánh đó.

## 12. Các lỗi hiểu sai thường gặp

1. **“Invalid field” nghĩa là tuổi 16 không hợp lệ:** với `setIgnoreInvalidFields`, đó là đường dẫn không truy cập được. Tuổi 16 là lỗi validation nếu có quy tắc tuổi tối thiểu.
2. **Bật `ignoreInvalidFields=true` sẽ bỏ qua mọi type mismatch:** không đúng; lỗi chuyển kiểu có cơ chế riêng và thường nằm trong `BindingResult`.
3. **Tưởng unknown field luôn có `FieldError`:** mặc định Spring bỏ qua; chế độ strict có thể ném `NotWritablePropertyException`.
4. **Tưởng đường dẫn lồng nhau có giá trị `null` luôn lỗi:** `autoGrowNestedPaths=true` có thể tự tạo nhánh và bind thành công.
5. **Tưởng `address.city` và `address.ctiy` là cùng loại lỗi:** một bên có thể là nhánh đúng nhưng null; bên kia có thể là tên thuộc tính không tồn tại.
6. **Dựa vào `getSuppressedFields()` để phát hiện unknown:** suppressed thường chỉ trường bị chính sách allowed/disallowed fields loại bỏ.
7. **Tắt `ignoreUnknownFields` rồi coi như đã chặn mass assignment:** thuộc tính nhạy cảm nếu tồn tại thật vẫn có thể bind; cần DTO và whitelist.
8. **Tưởng Spring MVC JSON dùng các cờ này giống form:** `@RequestBody` đi qua message converter và deserializer.
9. **Đọc ngược ý nghĩa mặc định:** `ignoreUnknownFields=true`, `ignoreInvalidFields=false`, `autoGrowNestedPaths=true` đối với `DataBinder` thông thường.
10. **Không phân biệt exception với lỗi tích lũy:** sai kiểu như `age=abc` thường tạo `FieldError`; unknown/invalid ở chế độ nghiêm ngặt có thể ném exception, cần xử lý phù hợp.

## 13. Tự luyện

**Tình huống A:** `Profile` có `address` nhưng giá trị hiện tại `null`. Client gửi `address.city=Da Nang`. Hãy dự đoán kết quả khi bật/tắt `autoGrowNestedPaths` và `ignoreInvalidFields`; giải thích vì sao thay đổi cờ này không làm `city` trở thành một property “unknown”.

**Tình huống B:** Client gửi `address.ciy=Da Nang`. Nêu cách xác minh rằng `ciy` là tên sai và phân biệt với `address.city` khi nhánh `address` chưa có instance.

**Tình huống C:** Client gửi `age=abc` và `age=16` vào bean có `Integer age`. Phân biệt thứ tự binding, conversion, validation; giải thích khi nào `FieldError.isBindingFailure()` là `true` và khi nào là `false`.

**Tình huống D:** Một form có thuộc tính `role` nhưng chỉ muốn cho phép thay `age` và `address.city`. Vì sao `setIgnoreUnknownFields(false)` không giải quyết được vấn đề? Hãy xác định vai trò của `setAllowedFields(...)` và DTO đầu vào.

Bạn nắm vững bài khi phân biệt được: **unknown = không có thuộc tính để gắn; invalid = có đường dẫn thuộc tính nhưng không thể đi đến nó; type mismatch = không chuyển được giá trị; validation failure = giá trị đã tạo nhưng không đạt quy tắc.**

## Tài liệu tham khảo

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html).
- [Spring Framework — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html).
- [Spring Framework — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html).
- [Spring Framework — NullValueInNestedPathException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/NullValueInNestedPathException.html).
