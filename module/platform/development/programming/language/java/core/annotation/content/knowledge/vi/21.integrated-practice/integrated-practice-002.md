# Xây dựng bộ kiểm tra đối tượng bằng annotation RUNTIME và reflection trong Java

Một **object validator** đọc trạng thái của một đối tượng và trả về các lỗi nếu dữ liệu không thỏa mãn những quy tắc đã khai báo. Java cho phép đặt quy tắc gần field bằng annotation, ví dụ **@Required**, **@NotBlank** hoặc **@IntRange(min = 18, max = 65)**. Nếu những annotation này có **@Retention(RetentionPolicy.RUNTIME)**, chương trình có thể dùng **reflection** để tìm chúng và kiểm tra giá trị field khi chạy.

Bài thực hành này xây dựng một bộ kiểm tra nhỏ bằng Java 17, **không phụ thuộc framework**, với khả năng:

- Từ chối field tham chiếu bằng **null** qua **@Required**.
- Từ chối chuỗi null, rỗng hoặc chỉ gồm khoảng trắng qua **@NotBlank**.
- Kiểm tra số nguyên nằm trong khoảng đóng qua **@IntRange**.
- Đi vào đối tượng lồng nhau qua **@ValidNested**, tạo đường dẫn lỗi dạng **address.city**.
- Đọc cả **private field**, xử lý lỗi truy cập reflection, bỏ qua field static/synthetic và sắp xếp kết quả ổn định.
- Tránh đệ quy vô hạn khi đồ thị đối tượng có vòng tham chiếu.

Đây là cách học cơ chế annotation và reflection. Nó **không phải bản thay thế đầy đủ cho Jakarta Bean Validation**: chưa có group, container element, custom constraint validator, message interpolation, localization hoặc toàn bộ quy tắc kiểm tra cấu hình.

## 1. Luồng xử lý tổng thể

Một validator có thể được tổ chức theo các bước:

~~~text
Đối tượng Account
       |
       v
Duyệt các field bằng reflection
       |
       +--> Tìm annotation bằng getAnnotation(...)
       |
       +--> Đọc giá trị qua Field.get(instance)
       |
       +--> Chạy rule tương ứng:
       |      @Required -> value != null
       |      @NotBlank -> String không blank
       |      @IntRange -> min <= integer <= max
       |
       +--> @ValidNested -> đệ quy sang bean con
       |
       v
Danh sách lỗi (field path + message)
~~~

**Annotation không tự kiểm tra dữ liệu.** **@IntRange** chỉ lưu hai giá trị min/max. Chính mã trong **Validator** mới đọc metadata đó, lấy dữ liệu thực tế và quyết định có lỗi hay không.

Nên tách ba trách nhiệm:

1. **Định nghĩa constraint:** các annotation mô tả metadata.
2. **Định nghĩa đối tượng:** các field dữ liệu mang annotation.
3. **Cơ chế kiểm tra:** validator kết hợp metadata với giá trị hiện tại và trả kết quả.

Với thiết kế này, một kiểu annotation có thể tái sử dụng ở nhiều DTO/entity khác nhau. Khi cần thêm rule, bạn sẽ mở rộng validator hoặc bổ sung mô hình rule riêng, thay vì viết lại kiểm tra thủ công cho từng class.

## 2. Định nghĩa bốn annotation kiểm tra

Tất cả các annotation ví dụ đều được gắn lên **field**, nên sử dụng **@Target(ElementType.FIELD)**. Các quy tắc phải được đọc **khi chương trình đang chạy**, vì vậy chọn **RetentionPolicy.RUNTIME**.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Required {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface NotBlank {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface IntRange {
    long min();
    long max();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface ValidNested {}
~~~

Ở đây:

- **Required** là marker annotation; nó không cần element vì chỉ biểu thị field phải khác null.
- **NotBlank** cũng là marker; quy tắc của nó dành cho **String**, không cho số hoặc danh sách. Trong triển khai của bài, nó **đã bao gồm cả kiểm tra null**.
- **IntRange** có hai phần tử bắt buộc **min()**, **max()**; không chọn default tùy tiện vì giới hạn số phụ thuộc miền nghiệp vụ.
- **ValidNested** là marker yêu cầu đi sâu vào một đối tượng lồng nhau nếu đối tượng đó tồn tại.
- **@Target(FIELD)** ngăn người dùng gắn các rule này vào class hoặc method. Nó không tự bảo đảm field có kiểu phù hợp với từng rule.
- **@Retention(RUNTIME)** bảo đảm reflection có thể lấy annotation bằng **Field.getAnnotation(...)** lúc chạy.

**Lưu ý:** Nếu bỏ **@Retention**, chính sách mặc định là **RetentionPolicy.CLASS**, không đủ cho việc đọc annotation qua reflection thông thường. **@Target** và **@Retention** là metadata của **annotation type**; chúng không trực tiếp làm phát sinh logic kiểm tra trong object validator.

### Ràng buộc được diễn đạt như thế nào?

| Annotation | Kiểu field dự kiến | Khi nào phát sinh lỗi? |
| --- | --- | --- |
| **@Required** | Kiểu tham chiếu bất kỳ | Giá trị **null** |
| **@NotBlank** | **String** | Chuỗi null hoặc **String.isBlank() == true** |
| **@IntRange(min, max)** | **int**, **long**, **Integer**, **Long** trong ví dụ | Giá trị không null nằm ngoài khoảng [min, max] |
| **@ValidNested** | Một bean lồng nhau | Tiếp tục kiểm tra các field có annotation của bean con; bản thân nó không cấm null |

Vì **@IntRange** không tự cấm null, với **Integer** hoặc **Long** nullable cần ghép **@Required** nếu muốn bắt buộc có giá trị. Với primitive **int/long**, không thể nhận null; vì thế gắn @Required lên primitive thường không có ý nghĩa.

Nếu ghi **@NotBlank** trên một field int, validator bài này **báo lỗi sử dụng annotation sai kiểu** bằng exception, thay vì âm thầm coi int là chuỗi hoặc bỏ qua.

## 3. Định nghĩa object cần kiểm tra

Ta có hai class:

~~~java
final class Address {
    @NotBlank private final String city;

    Address(String city) {
        this.city = city;
    }
}

final class Account {
    @Required @ValidNested private final Address address;
    @IntRange(min = 18, max = 65) private final int age;
    @Required private final String id;
    @NotBlank private final String name;

    Account(String id, String name, int age, Address address) {
        this.id = id;
        this.name = name;
        this.age = age;
        this.address = address;
    }
}
~~~

**Account** có bốn trường:

- **address**: bắt buộc khác null và, nếu tồn tại, cần kiểm tra các rule của **Address**. Để biểu diễn cả hai điều kiện phải kết hợp **@Required @ValidNested**.
- **age**: có kiểu **int**, phải nằm trong khoảng từ **18 đến 65** tính cả hai đầu mút.
- **id**: chỉ cần khác **null**; giá trị chuỗi rỗng vẫn qua được @Required. Nếu nghiệp vụ đòi chuỗi không rỗng, nên dùng **@NotBlank** thay hoặc kết hợp rule phù hợp.
- **name**: @NotBlank từ chối **null**, **""**, **"   "** và những chuỗi chỉ gồm ký tự khoảng trắng theo phương thức **String.isBlank()**.

Đối với Address, **city** phải là chuỗi không blank. Nếu Account có Address hợp lệ nhưng city chứa toàn khoảng trắng, validator sẽ ghi lỗi với **đường dẫn address.city**.

Các field đều khai báo **private final**. Reflection cần đọc chúng nhưng **không cần sửa**. Điều này giúp tránh nhầm lẫn giữa kiểm tra đầu vào và chỉnh sửa dữ liệu: validator chỉ quan sát và trả thông tin lỗi.

## 4. Đọc annotation và giá trị field bằng reflection

Một Field object đại diện cho một field được khai báo trên class. Những phương thức quan trọng:

~~~java
Field[] fields = type.getDeclaredFields();
Required required = field.getAnnotation(Required.class);
Object value = field.get(bean);
~~~

Đây là đoạn minh họa bên trong validator đã có biến **type**, **field**, **bean** và xử lý **IllegalAccessException**.

- **Class.getDeclaredFields()** lấy field được khai báo trực tiếp trên một class, bao gồm field private; bản thân lời gọi này không tự trả field của superclass.
- **Field.getAnnotation(A.class)** trả annotation kiểu A khi nó hiện diện, hoặc **null** nếu không tìm thấy.
- **Field.isAnnotationPresent(A.class)** phù hợp khi chỉ cần boolean.
- **Field.get(bean)** lấy giá trị của field trên một instance cụ thể; giá trị primitive được boxing thành wrapper như **Integer** hay **Long**.
- **Field.getName()** cho tên field; để viết đường dẫn lỗi cho bean lồng nhau, nối tên field vào prefix.
- **Modifier.isStatic(...)** giúp bỏ qua static field vì chúng thuộc class, không phải từng object instance.
- **Field.isSynthetic()** giúp bỏ qua field do compiler sinh ra, tránh kiểm tra các cấu trúc không được người viết DTO khai báo chủ đích.

**Không dựa vào thứ tự được trả về bởi getDeclaredFields().** Java reflection không cam kết thứ tự field cố định; ví dụ sắp xếp theo tên bằng **Arrays.sort(fields, Comparator.comparing(Field::getName))** để kết quả test dễ tái lập.

### Private field và JPMS

Đối với private field, mã gọi **Field.get(bean)** từ class khác thường bị kiểm soát truy cập Java. Ta dùng:

~~~java
if (!field.trySetAccessible()) {
    throw new IllegalStateException(
            "cannot access " + field.getName());
}
~~~

**trySetAccessible()** thử cho phép thao tác reflection vượt kiểm tra truy cập Java thông thường. Nếu không được phép, nó trả false; không nên giả định lúc nào cũng thành công.

Trong ví dụ độc lập chạy trên classpath, các lớp thuộc unnamed module nên thao tác này hoạt động. Nhưng nếu DTO ở một **named module** khác, module đó có thể cần **opens** package tương ứng cho module chứa validator:

~~~java
module application.model {
    opens application.dto to application.validator;
}
~~~

Đây là **đoạn minh họa JPMS**, chỉ hợp lệ khi các module/package nêu trong ví dụ tồn tại. **exports** không đồng nghĩa **opens**; exports hỗ trợ truy cập kiểu theo ngôn ngữ Java, còn opens cho phép reflection sâu vào các thành viên không public trong những điều kiện tương ứng.

**Không nên tự ý dùng --add-opens cho mọi package** trong ứng dụng thật; hãy chọn chiến lược truy cập phù hợp và giới hạn phạm vi mở. Validator bài này sẽ báo lỗi cấu hình rõ ràng nếu không thể đọc field.

## 5. Ví dụ Java 17+ hoàn chỉnh, đã biên dịch và chạy

Tạo đúng một tệp **src/demo/ValidationDemo.java** với toàn bộ mã dưới đây:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Required {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface NotBlank {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface IntRange {
    long min();
    long max();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface ValidNested {}

final class Address {
    @NotBlank private final String city;
    Address(String city) { this.city = city; }
}

final class Account {
    @Required @ValidNested private final Address address;
    @IntRange(min = 18, max = 65) private final int age;
    @Required private final String id;
    @NotBlank private final String name;

    Account(String id, String name, int age, Address address) {
        this.id = id;
        this.name = name;
        this.age = age;
        this.address = address;
    }
}

final class Validator {
    private Validator() {}

    static List<String> validate(Object root) {
        if (root == null) {
            throw new IllegalArgumentException("root must not be null");
        }
        List<String> errors = new ArrayList<>();
        Set<Object> active = Collections.newSetFromMap(new IdentityHashMap<>());
        visit(root, "", active, errors);
        return List.copyOf(errors);
    }

    private static void visit(Object bean, String prefix,
            Set<Object> active, List<String> errors) {
        if (!active.add(bean)) {
            errors.add(prefix + ": cycle detected");
            return;
        }
        try {
            for (Class<?> type = bean.getClass();
                    type != null && type != Object.class;
                    type = type.getSuperclass()) {
                Field[] fields = type.getDeclaredFields();
                Arrays.sort(fields, Comparator.comparing(Field::getName));

                for (Field field : fields) {
                    if (field.isSynthetic() || Modifier.isStatic(field.getModifiers())) {
                        continue;
                    }
                    Required required = field.getAnnotation(Required.class);
                    NotBlank notBlank = field.getAnnotation(NotBlank.class);
                    IntRange range = field.getAnnotation(IntRange.class);
                    ValidNested nested = field.getAnnotation(ValidNested.class);
                    if (required == null && notBlank == null
                            && range == null && nested == null) {
                        continue;
                    }

                    String path = prefix.isEmpty() ? field.getName()
                            : prefix + "." + field.getName();
                    if (!field.trySetAccessible()) {
                        throw new IllegalStateException("cannot access " + path);
                    }
                    Object value;
                    try {
                        value = field.get(bean);
                    } catch (IllegalAccessException ex) {
                        throw new IllegalStateException("cannot read " + path, ex);
                    }

                    if (required != null && value == null) {
                        errors.add(path + ": must not be null");
                    }
                    if (notBlank != null) {
                        if (field.getType() != String.class) {
                            throw new IllegalArgumentException(
                                    "@NotBlank requires String: " + path);
                        }
                        if (value == null || ((String) value).isBlank()) {
                            errors.add(path + ": must not be blank");
                        }
                    }
                    if (range != null) {
                        Class<?> t = field.getType();
                        if (t != int.class && t != long.class
                                && t != Integer.class && t != Long.class) {
                            throw new IllegalArgumentException(
                                    "@IntRange requires int/long: " + path);
                        }
                        if (range.min() > range.max()) {
                            throw new IllegalArgumentException(
                                    "invalid @IntRange bounds: " + path);
                        }
                        if (value != null) {
                            long number = ((Number) value).longValue();
                            if (number < range.min() || number > range.max()) {
                                errors.add(path + ": must be between "
                                        + range.min() + " and " + range.max());
                            }
                        }
                    }
                    if (nested != null && value != null) {
                        visit(value, path, active, errors);
                    }
                }
            }
        } finally {
            active.remove(bean);
        }
    }
}

public class ValidationDemo {
    public static void main(String[] args) {
        Account valid = new Account("A-01", "Lan", 22,
                new Address("Hà Nội"));
        Account invalid = new Account(null, "  ", 16,
                new Address("  "));
        Account missing = new Account("A-02", "Nam", 30, null);
        show("valid", valid);
        show("invalid", invalid);
        show("missing", missing);
    }

    private static void show(String title, Account account) {
        List<String> errors = Validator.validate(account);
        System.out.println(title + " count=" + errors.size());
        errors.forEach(System.out::println);
    }
}
~~~

Biên dịch và chạy từ thư mục chứa **src**:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/ValidationDemo.java
java -cp out demo.ValidationDemo
~~~

**Stdout thực tế của chương trình:**

~~~text
valid count=0
invalid count=4
address.city: must not be blank
age: must be between 18 and 65
id: must not be null
name: must not be blank
missing count=1
address: must not be null
~~~

Ví dụ đã được **biên dịch và thực thi thành công trên JDK 21 với --release 17**. Lệnh **--release 17** yêu cầu trình biên dịch tuân theo API/ngôn ngữ Java 17; nếu dự án chạy bằng một bản JDK 17 cụ thể, hãy kiểm tra lại trong chính môi trường triển khai đó.

### Vì sao có đúng bốn lỗi trên invalid?

Với Account invalid:

- **address** khác null, nên @Required trên address đạt. **@ValidNested** đưa validator vào Address.
- **address.city** chứa chỉ khoảng trắng nên @NotBlank thất bại.
- **age = 16**, nằm ngoài khoảng đóng **[18, 65]**, nên @IntRange thất bại.
- **id = null**, nên @Required thất bại.
- **name = "  "** (hai dấu cách), nên @NotBlank thất bại.

Tổng cộng **4 lỗi**. Chương trình sắp xếp field trong mỗi class theo tên, vì vậy lỗi theo thứ tự **address.city, age, id, name**.

Với Account missing, chỉ có một lỗi **address: must not be null**. Vì address null, nhánh **@ValidNested** không đi sâu vào đối tượng không tồn tại. Điều này ngăn việc vô tình ném NullPointerException khi đọc **address.city**.

Với Account valid, mọi điều kiện đều đạt nên **validate(...)** trả **List<String> rỗng**.

## 6. Đọc trực tiếp từng nhóm rule

Có thể nhìn validator như các predicate áp lên giá trị đã lấy từ field.

### 6.1. Required chỉ kiểm tra null

~~~java
if (required != null && value == null) {
    errors.add(path + ": must not be null");
}
~~~

Điều kiện của @Required **không cấm chuỗi rỗng, số 0 hoặc collection rỗng**. Nếu nghiệp vụ cần những ràng buộc đó, không nên giả định @Required tự đảm nhiệm.

**Required trên primitive int** thường dư thừa vì primitive field không chứa null. Nếu cần biểu diễn thiếu dữ liệu, có thể dùng **Integer** nullable kèm @Required, hoặc một kiểu dữ liệu mô tả sự vắng mặt rõ ràng hơn.

### 6.2. NotBlank kiểm tra String

~~~java
if (notBlank != null) {
    if (field.getType() != String.class) {
        throw new IllegalArgumentException(
                "@NotBlank requires String: " + path);
    }
    if (value == null || ((String) value).isBlank()) {
        errors.add(path + ": must not be blank");
    }
}
~~~

**String.isBlank()** có từ Java 11 và dùng tiêu chí ký tự khoảng trắng của Java. Nó trả true với chuỗi rỗng hoặc chuỗi chỉ gồm các ký tự whitespace được Java công nhận. Điều đó phù hợp với ví dụ Java 17.

**Tại sao kiểm tra kiểu field trước?** Vì @Target(FIELD) chỉ hạn chế vị trí khai báo; nó không đủ để đảm bảo field là String. Một field kiểu int vẫn có thể bị người viết gắn @NotBlank, nên validator phải chẩn đoán cấu hình sai rõ ràng.

### 6.3. IntRange kiểm tra khoảng đóng

~~~java
IntRange range = field.getAnnotation(IntRange.class);
if (range != null) {
    // Kiểm tra kiểu field và min <= max trước.
    if (value != null) {
        long n = ((Number) value).longValue();
        if (n < range.min() || n > range.max()) {
            errors.add(path + ": outside allowed range");
        }
    }
}
~~~

Đây là **đoạn minh họa rút gọn**; phiên bản đầy đủ ở trên có logic kiểm tra đúng kiểu **int/long/Integer/Long**, kiểm tra **min <= max** và in thông điệp chứa cả hai đầu mút.

Khoảng đóng nghĩa là **min và max cũng hợp lệ**. Với **@IntRange(min = 18, max = 65)**, các giá trị 18, 22 và 65 đạt; 17 và 66 không đạt.

Khi field wrapper **Integer/Long** là null, IntRange trong bài này **bỏ qua** vì không có số để so sánh. Muốn xem null là lỗi, ghép @Required. Thiết kế này tách ràng buộc **sự hiện diện** và **miền giá trị**.

Không dùng **longValue()** một cách mù quáng trên mọi Number, ví dụ Double, BigDecimal hoặc BigInteger; việc chuyển đổi có thể mất thông tin. Validator chủ động giới hạn chỉ bốn kiểu int/long và wrapper của chúng.

### 6.4. ValidNested đệ quy

~~~java
if (nested != null && value != null) {
    visit(value, path, active, errors);
}
~~~

**ValidNested không tự cấm null**. Kết hợp **@Required** nếu bean con không được thiếu. **path** tích lũy tên các field để lỗi ở Address được báo là **address.city**.

Đoạn này chỉ hỗ trợ **một đối tượng con trực tiếp**. Nếu field chứa **List<Address>**, **Set<Address>**, **Map<String, Address>**, array hoặc Optional, bản ví dụ chưa tự duyệt từng phần tử. Cần thiết kế riêng cách tạo đường dẫn như **addresses[2].city** và cách xử lý null, collections, keys.

## 7. Tránh vòng tham chiếu khi kiểm tra bean lồng nhau

Một đồ thị đối tượng có thể chứa vòng:

~~~text
Account -> Address -> Owner -> Account
   ^                         |
   +-------------------------+
~~~

Nếu validator cứ đệ quy theo mọi @ValidNested mà không kiểm tra, chương trình có nguy cơ lặp vô hạn và ném **StackOverflowError**.

Ví dụ dùng:

~~~java
Set<Object> active =
        Collections.newSetFromMap(new IdentityHashMap<>());
~~~

và:

~~~java
if (!active.add(bean)) {
    errors.add(prefix + ": cycle detected");
    return;
}
try {
    // Duyệt field và có thể đệ quy tới bean con.
} finally {
    active.remove(bean);
}
~~~

Ý nghĩa:

- **IdentityHashMap** so sánh object theo **đồng nhất tham chiếu**, không dựa trên **equals()/hashCode()** do DTO có thể định nghĩa. Hai DTO bằng nhau về nội dung nhưng là hai object khác nhau không tự tạo vòng.
- **active** là tập object **đang nằm trên nhánh đệ quy hiện tại**. Nếu một object xuất hiện lại trong cùng nhánh, có vòng tham chiếu.
- **finally remove(bean)** cho phép một object hợp lệ được tham chiếu bởi hai nhánh độc lập mà không bị gắn nhầm là vòng vĩnh viễn.
- Ví dụ lựa chọn trả **một validation error** khi phát hiện cycle. Trong sản phẩm thực tế có thể chọn chính sách khác: bỏ qua nhánh đã gặp, giới hạn độ sâu hoặc kiểm tra cycle bằng một rule chuyên biệt.

Tập **active** được tạo mới cho mỗi lần gọi **Validator.validate(root)**; do đó các lượt kiểm tra độc lập không chia sẻ trạng thái. Nó không phải global cache.

**Lưu ý:** Cơ chế này chỉ phát hiện vòng theo reference. Nó không biến validator thành công cụ xử lý mọi object graph tùy ý; bean có thể chứa các cấu trúc thư viện hoặc liên kết dữ liệu mà không nên reflection đệ quy.

## 8. Đọc field private qua reflection: các giới hạn quan trọng

Thư viện reflection có hai nhóm vấn đề:

**Một là lỗi truy cập:** Trong môi trường module có đóng gói mạnh, **trySetAccessible()** có thể trả false. Mã bài này ném **IllegalStateException("cannot access ...")**. Không nên âm thầm nuốt lỗi và báo “đối tượng hợp lệ”, vì khi đó một số constraint chưa được kiểm tra.

**Hai là phạm vi field:** **getDeclaredFields()** chỉ bao gồm các field được khai báo trực tiếp trên class hiện tại. Ví dụ dùng vòng lặp đi lên superclass:

~~~java
for (Class<?> type = bean.getClass();
        type != null && type != Object.class;
        type = type.getSuperclass()) {
    Field[] fields = type.getDeclaredFields();
    // Kiểm tra từng field ở cấp này.
}
~~~

Cách này giúp đọc constraint đặt trên field cha, ngay cả khi field đó là private. Tuy nhiên, **field shadowing** có thể khiến lớp con và lớp cha cùng khai báo một tên field: khi đó cả hai field có thể được duyệt, và đường dẫn chỉ gồm tên field sẽ không đủ phân biệt. Nếu cần hỗ trợ class hierarchy phức tạp, hãy đặt đường dẫn hoặc metadata có cả **declaring class**, và quy định thứ tự duyệt rõ ràng.

**Ba là thứ tự field:** Sắp xếp bằng **Comparator.comparing(Field::getName)** bảo đảm thứ tự trong từng class không phụ thuộc JVM trả mảng field ban đầu như thế nào. Nhưng toàn bộ lớp cha/con được duyệt theo thứ tự do vòng lặp xác định (class thực tế trước, rồi superclass).

**Bốn là static/synthetic:** Mã bỏ qua chúng để tập trung vào trạng thái của instance. Nếu ứng dụng cần kiểm tra hằng hoặc cấu hình static, đó nên là một bài toán riêng.

**Năm là khả năng chạy với Java record:** Record thường có private final fields và component accessors. Cơ chế reflection field của ví dụ có thể đọc các field khi quyền truy cập cho phép, nhưng một thư viện validator dùng chung nên cân nhắc API record components, constructor constraints và triết lý bất biến của record. Không nên dùng reflection ghi lại field final.

## 9. Phân biệt lỗi dữ liệu với lỗi cấu hình validator

Một hệ thống kiểm tra tốt phải phân biệt:

**Validation violation:** đối tượng có dữ liệu không đạt rule hợp lệ. Ví dụ **age=16** với **@IntRange(min=18,max=65)** tạo lỗi và được đưa vào List.

**Annotation misuse / configuration error:** chính metadata được khai báo sai đối với validator. Ví dụ:

~~~java
class WrongConfig {
    @NotBlank int quantity;
    @IntRange(min = 10, max = 1) long score;
}
~~~

Trong triển khai này:

- **@NotBlank** trên int gây **IllegalArgumentException** vì rule chỉ chấp nhận String.
- **@IntRange(min=10,max=1)** có min lớn hơn max nên cũng là cấu hình sai, chứ không phải một khoảng hợp lệ mà mọi số đều thất bại.
- Nếu @IntRange được gắn lên Double hay String, validator báo lỗi kiểu thay vì làm phép chuyển đổi không an toàn.
- Nếu field cần kiểm tra là private nhưng không thể truy cập theo JPMS, validator báo **IllegalStateException** thay vì âm thầm bỏ qua.

**Tại sao không coi mọi trường hợp đó chỉ là một thông điệp validation?** Vì dữ liệu đầu vào và lỗi lập trình/khai báo quy tắc có vòng đời sửa chữa khác nhau. DTO sai dữ liệu có thể sửa bằng cách nhập lại; annotation đặt sai kiểu phải sửa code/config và build/triển khai lại.

Trong một thư viện production, các lỗi cấu hình có thể được kiểm tra **ngay lúc khởi tạo validator** hoặc qua **annotation processor ở compile time** để phát hiện sớm hơn. Bài này kiểm tra chúng trong lần duyệt runtime để giữ ví dụ ngắn, rõ cơ chế.

## 10. Khi nào dùng reflection, khi nào dùng annotation processing?

Bài này chủ ý dùng **RUNTIME + reflection**, vì nó phải đọc **giá trị hiện tại của một object**. Ví dụ:

~~~java
Account account =
        new Account("A-01", "Lan", 22, new Address("Hà Nội"));

List<String> violations = Validator.validate(account);
~~~

Giá trị **"Lan"**, **22**, **"Hà Nội"** chỉ xuất hiện khi chương trình tạo đối tượng; một processor làm việc với source tại compile time không thể biết mọi object runtime tương lai sẽ chứa dữ liệu gì.

Có thể kết hợp hai cơ chế:

- **Annotation processor (compile time):** xác minh @NotBlank chỉ được đặt trên String, @IntRange chỉ trên kiểu số nguyên phù hợp; sinh metadata hoặc mã validator tối ưu.
- **Reflection (runtime):** lấy field value từ đối tượng cụ thể rồi chạy các rule.
- **Generated validator (runtime):** thay reflection bằng lớp được processor sinh từ trước, nếu mục tiêu là giảm chi phí truy cập reflection khi chạy.

**Không suy luận rằng chỉ vì annotation có @Retention(RUNTIME) thì nó tự được validation engine thi hành.** Retention chỉ xác định metadata tồn tại để reflection có thể đọc; validator phải được gọi một cách tường minh.

## 11. Một số giới hạn phải biết trước khi đem vào sản phẩm

Bản demo nhằm học đúng cơ chế và có những giới hạn có chủ đích:

| Vấn đề | Demo hiện tại | Hướng mở rộng |
| --- | --- | --- |
| Kiểu rule | Required, NotBlank, IntRange, ValidNested | Thiết kế registry riêng cho các **ConstraintValidator** |
| Vị trí constraint | FIELD | Hỗ trợ METHOD, PARAMETER, RECORD_COMPONENT hoặc TYPE_USE theo mục tiêu |
| Kết quả | List<String> | Kiểu **Violation(path, code, message, invalidValue)**; tránh đưa dữ liệu nhạy cảm vào log |
| Bean lồng nhau | Một object direct field | Hỗ trợ collection/array/Map với path có index/key |
| Vòng tham chiếu | Trả lỗi cycle trên nhánh đệ quy | Chính sách bỏ qua, giới hạn depth hoặc graph validation chuyên biệt |
| Group validation | Không | Nhóm các constraint theo tình huống create/update |
| Thông điệp lỗi | Chuỗi tiếng Anh cố định | Message catalog, localization, parameterized messages |
| Hiệu năng reflection | Quét annotation mỗi lần | Cache metadata Field/Rule theo Class, kiểm soát class loader |
| Lỗi cấu hình annotation | Phát hiện lúc validate | Processor compile-time hoặc kiểm tra schema tại startup |
| JPMS | trySetAccessible, lỗi nếu không đọc được | Cấu hình opens có chủ đích hoặc accessor/method-handle phù hợp |
| Field kế thừa và shadowing | Duyệt superclass, có thể trùng tên | Giữ declaring class trong metadata/violation |
| Thread safety | List/active tạo mới mỗi lượt | Cache chỉ đọc, đảm bảo trạng thái dùng chung bất biến nếu mở rộng |

Đối với ứng dụng nghiệp vụ thực tế, nên đánh giá **Jakarta Bean Validation** và một implementation phù hợp thay vì xây lại toàn bộ vòng đời kiểm tra, bộ quy tắc, nhóm kiểm tra, i18n và tích hợp framework. Mục tiêu bài thực hành là hiểu được cơ chế cốt lõi phía sau cách các hệ thống annotation-driven hoạt động.

### Không tự động sửa object

Validator trong ví dụ **không sửa field** và không cố biến dữ liệu sai thành dữ liệu đúng. Ví dụ name = "  " là blank nên trả lỗi; mã không tự trim và gán lại value. Việc normalize input là một bước khác, cần quy tắc nghiệp vụ rõ ràng.

**Không đặt mật khẩu/token nguyên bản vào lỗi hoặc log.** Nếu sau này mở rộng Violation chứa invalidValue, cần chú ý dữ liệu nhạy cảm. Trong chương trình demo, lỗi chỉ chứa đường dẫn field và quy tắc thất bại.

## 12. Test thủ công và các ca biên nên bổ sung

Các trường hợp nên thử với Account:

| Dữ liệu | Kết quả mong muốn |
| --- | --- |
| name = "Lan", age=22, id khác null, address.city="Hà Nội" | Không lỗi |
| name = "" hoặc "   " | Lỗi name: must not be blank |
| name = null | Lỗi name: must not be blank |
| id = null | Lỗi id: must not be null |
| id = "" | Không lỗi Required (vì không null) |
| age = 18 hoặc 65 | Không lỗi IntRange |
| age = 17 hoặc 66 | Lỗi khoảng số |
| address = null | Lỗi address do Required; không đệ quy |
| address.city = " " | Lỗi address.city |
| root truyền vào Validator.validate(null) | IllegalArgumentException |
| Vòng A → B → A nếu cả hai liên kết có @ValidNested | Lỗi cycle detected, không đệ quy vô hạn |
| @NotBlank đặt trên int | IllegalArgumentException, không xem như dữ liệu lỗi |
| @IntRange min > max | IllegalArgumentException do cấu hình |
| Private field trong module không mở reflection | IllegalStateException khi trySetAccessible trả false |

Nếu muốn kiểm chứng **reflection thật sự cần RUNTIME**, thử đổi @Retention của một annotation thành CLASS rồi biên dịch lại. Trong mô hình chạy bằng reflection tiêu chuẩn, annotation đó **không còn được tìm bằng Field.getAnnotation(...)**, nên rule tương ứng bị bỏ qua. Đây là lý do không thể dùng default retention một cách tùy tiện cho validator runtime.

### Kiểm chứng việc sắp xếp lỗi

Mã demo dùng:

~~~java
Arrays.sort(fields, Comparator.comparing(Field::getName));
~~~

Nhờ đó dù JVM trả getDeclaredFields theo thứ tự không cố định, các lỗi trên Account trong ví dụ vẫn theo thứ tự alphabet của field: **address, age, id, name**. Trong Address chỉ có **city**; lỗi lồng nhau xuất hiện ngay khi xử lý field address, trước age.

Điều này giúp test stdout chính xác và tránh tạo test không ổn định vì phụ thuộc thứ tự reflection không được bảo đảm.

## 13. Lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Annotation có default retention nhưng validator không thấy | Mặc định CLASS, không phải RUNTIME | Khai báo @Retention(RUNTIME) |
| Chỉ định @Target(METHOD) nhưng gắn trên field | Target sai vị trí | Dùng @Target(FIELD) |
| Gọi getAnnotation trên Class để tìm annotation FIELD | Đang hỏi sai đối tượng reflection | Lấy Field từ Class rồi gọi Field.getAnnotation |
| Dùng getFields() nhưng bỏ sót private field | getFields trả public field | Dùng getDeclaredFields và chính sách truy cập phù hợp |
| Đọc private field trực tiếp rồi gặp IllegalAccessException | Chưa được phép truy cập | Thử trySetAccessible, xét JPMS opens |
| Chỉ kiểm tra @Required mà cho chuỗi "" đi qua | Required chỉ cấm null | Dùng NotBlank cho String |
| Mong @IntRange tự cấm null của Integer | Range kiểm tra số nếu tồn tại | Ghép @Required |
| Dùng @NotBlank trên int | Sai kiểu field so với rule | Chẩn đoán annotation misuse |
| Dùng String.trim().isEmpty() thay isBlank tùy tiện | Hai cách xử lý whitespace có thể khác nhau | Quy định rõ ngữ nghĩa; ví dụ dùng isBlank |
| Không sắp xếp getDeclaredFields rồi test thứ tự lỗi | Reflection không cam kết thứ tự | Sort Field[] hoặc sort violation |
| Đệ quy mọi object kể cả Java platform object | Có thể đọc sai phạm vi và gặp module restrictions | Chỉ áp dụng @ValidNested cho bean domain phù hợp |
| Không kiểm tra vòng reference | Có thể StackOverflowError | Identity-based recursion stack |
| Nuốt lỗi truy cập reflection và trả List rỗng | Có constraint chưa được kiểm tra | Báo lỗi rõ ràng, không coi là hợp lệ |
| Dùng annotation để chứa rule nhưng không gọi Validator | Annotation là metadata thụ động | Gọi validate(...) tại boundary phù hợp |
| Gắn @Required lên field int rồi mong bắt “chưa nhập” | int primitive luôn có giá trị mặc định 0 | Dùng Integer nullable và @Required nếu cần |

## 14. Bài tập mở rộng có hướng giải

**Bài 1 — Thêm @MinLength**

Định nghĩa:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface MinLength {
    int value();
}
~~~

Yêu cầu: chỉ chấp nhận field String, kiểm tra độ dài tối thiểu; nếu value < 0, báo lỗi cấu hình. Cần quyết định null có bị lỗi không hay phải ghép @Required. Một hướng hợp lý là bỏ qua null như IntRange, còn @NotBlank hoặc @Required đảm nhiệm sự hiện diện.

**Bài 2 — Viết kiểu Violation mạnh hơn chuỗi**

Thay vì List<String>, tạo record Java 17:

~~~java
record Violation(String path, String rule, String message) {}
~~~

Ví dụ:

~~~text
Violation(path="age", rule="IntRange",
          message="must be between 18 and 65")
~~~

Đây là **sơ đồ mô tả dữ liệu**, không phải output mặc định do Java record in ra trong ví dụ runnable. Tách path, rule, message cho phép frontend xử lý có cấu trúc, hỗ trợ dịch thông điệp và kiểm thử cụ thể hơn.

**Bài 3 — Hỗ trợ List<Address>**

Với:

~~~java
class Company {
    @ValidNested
    java.util.List<Address> locations;
}
~~~

Mã hiện tại **chưa xử lý đúng List**. Hãy nhận biết Collection, duyệt từng phần tử, gắn path như **locations[0].city** và tránh lặp vô hạn do tham chiếu vòng.

**Bài 4 — Bắt lỗi annotation configuration từ compile time**

Viết annotation processor kiểm tra **@NotBlank** chỉ dùng trên String và **@IntRange** chỉ trên int/long/Integer/Long. Nếu thấy sai, báo **Diagnostic.Kind.ERROR**. Processor này không cần biết giá trị runtime của bean; nó chỉ xác nhận annotation đặt đúng loại field.

**Bài 5 — So sánh với kiểm tra thủ công**

Viết một hàm Java kiểm tra riêng Account mà không dùng annotation. So sánh số lượng nơi phải cập nhật khi thêm loại object mới với cách validator quét metadata. Lợi ích của annotation là tính khai báo/tái sử dụng; chi phí là reflection, kiểm tra cấu hình và quản lý độ phức tạp khi mở rộng.

**Bài 6 — Thử cấu hình named module**

Đặt Account vào một named module khác và thử chạy validator. Nếu reflection không đọc được private field, hãy khai báo **opens** package DTO cho module validator với tên module hợp lệ, rồi thử lại. Giải thích vì sao **exports** không phải lúc nào cũng đủ để đọc private field.

## 15. Các nguồn chuẩn để đối chiếu

- **Java SE 17 — java.lang.annotation.Retention:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html — giá trị retention mặc định là CLASS nếu không khai báo.
- **Java SE 17 — java.lang.reflect.Field:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html — get, getDeclaredAnnotations và quyền truy cập field.
- **Java SE 17 — java.lang.reflect.AccessibleObject:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html — trySetAccessible và hành vi theo JPMS.
- **Java SE 17 — java.lang.Class.getDeclaredFields():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getDeclaredFields() — lấy field khai báo trên class.
- **Java SE 17 — java.lang.String.isBlank():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#isBlank() — kiểm tra chuỗi trống hoặc chỉ gồm khoảng trắng.
- **Java Language Specification §9.6.4.2 — @Retention:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2 — phạm vi tồn tại metadata annotation.

**Kết luận:** Một bộ validator dựa trên annotation runtime cần ba thành phần không thể thiếu: **annotation type mô tả rule**, **reflection lấy đúng metadata và giá trị của field**, và **mã kiểm tra trả lỗi theo chính sách đã xác định**. RUNTIME retention giúp tìm rule khi chạy, @Target(FIELD) giới hạn vị trí gắn và Validator kiểm tra dữ liệu thật. Khi mở rộng sang collections, inheritance, JPMS và cấu hình phức tạp, hãy giữ riêng vi phạm dữ liệu với lỗi cấu hình và bổ sung kiểm thử cho từng trường hợp.
