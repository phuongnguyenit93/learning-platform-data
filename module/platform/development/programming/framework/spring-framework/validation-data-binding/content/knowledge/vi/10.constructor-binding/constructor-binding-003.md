# DataBinder.ValueResolver và tra cứu giá trị tham số khi constructor binding

## 1. Vai trò của ValueResolver trong Spring Data Binding

`DataBinder.ValueResolver` là interface lồng bên trong lớp `org.springframework.validation.DataBinder`, dùng làm **chiến lược lấy giá trị đầu vào cho từng tham số constructor** khi Spring tạo đối tượng bằng constructor binding. Nó giúp tách hai trách nhiệm:

- **Tra cứu dữ liệu:** tìm giá trị tương ứng với tên tham số từ một nguồn dữ liệu, ví dụ các request parameters hoặc một `Map`.
- **Dựng và chuyển kiểu đối tượng:** `DataBinder` lựa chọn constructor, xác định tên/kiểu tham số, yêu cầu resolver trả dữ liệu, thực hiện type conversion, tạo đối tượng lồng nhau khi phù hợp, rồi gọi constructor.

Ví dụ cần tạo DTO Java:

```java
public record Registration(String name, Integer age) {}
```

Dữ liệu từ form có thể là:

```text
name=Lan&age=24
```

Spring tra cứu giá trị cho constructor parameter `name` và `age`, nhận hai chuỗi `"Lan"`, `"24"`, chuyển `"24"` sang `Integer 24`, sau đó khởi tạo `new Registration("Lan", 24)`. `ValueResolver` thực hiện **bước tra cứu**, không phải tự động gọi constructor hay thay thế toàn bộ cơ chế chuyển kiểu.

Luồng cơ bản:

```text
Tên + kiểu tham số của constructor
                 |
                 v
   DataBinder.NameResolver (nếu cấu hình)
          xác định lookup name
                 |
                 v
ValueResolver.resolveValue(name, type)
                 |
        giá trị thô hoặc null
                 |
                 v
   DataBinder chuyển kiểu nếu cần
                 |
                 v
   Constructor(giá trị đã chuẩn hóa)
                 |
                 v
        Đối tượng Java mới
                 |
                 v
     BindingResult nếu có lỗi
```

Đây là **constructor binding trong Spring Framework 6.1+**, không phải constructor dependency injection của `@Component`/`@Service`. `ValueResolver` cung cấp dữ liệu đầu vào cho *request/model object*; Spring IoC constructor injection tìm các **bean dependency** từ container theo kiểu/qualifier và cơ chế khác.

## 2. Hợp đồng API chính xác

Trong Spring Framework 6.2.x, interface có hai phương thức:

```java
package org.springframework.validation;

public class DataBinder {
    public interface ValueResolver {
        Object resolveValue(String name, Class<?> type);
        java.util.Set<String> getNames();
    }
}
```

**Đây là bản rút gọn chữ ký API để học**, không phải source đầy đủ của lớp `DataBinder`; Javadoc thực tế có nullable annotations và nhiều thành phần khác. Ý nghĩa:

| Phương thức | Đầu vào | Đầu ra | Trách nhiệm |
| --- | --- | --- | --- |
| `resolveValue(String name, Class<?> type)` | Tên tra cứu và kiểu Java của tham số constructor | Một `Object` hoặc `null` | Lấy giá trị ứng với key cụ thể |
| `getNames()` | Không có tham số | `Set<String>` | Liệt kê tên mọi giá trị mà resolver quản lý, đặc biệt để phát hiện dữ liệu lồng nhau |

**`resolveValue(...)`:**

- `name` thường là tên tham số constructor, ví dụ `"name"`, `"age"`; với tham số lồng nhau có thể là đường dẫn như `"address.city"`.
- `type` cho biết kiểu đích của tham số, ví dụ `String.class`, `Integer.class`, `Address.class`. Resolver **có thể** dùng kiểu này để chọn dạng dữ liệu trả về (nhất là request có nhiều giá trị/part), nhưng không nhất thiết phải tự ép kiểu mọi giá trị.
- Trả `null` khi không tìm thấy giá trị thích hợp. Spring sau đó có thể tiếp tục xem xét nested fields, collection/map/indexed input hoặc cách xử lý giá trị thiếu tùy tham số.

**`getNames()`:**

- Trả tập tên key, ví dụ `Set.of("name", "age", "address.city")`.
- Spring dùng tập key để biết có dữ liệu nằm *bên dưới* một tham số phức tạp hay không. Không tìm thấy key `"address"` vẫn có thể cần tạo object `address` nếu `"address.city"` có mặt.
- Interface không yêu cầu thứ tự ổn định; tên là dữ liệu để tìm kiếm. Không dùng thứ tự lặp của `Set` làm căn cứ dự đoán thứ tự lời gọi constructor hoặc format output.
- Trả danh sách đầy đủ, đúng tên và nhất quán với `resolveValue`. Trả tập rỗng tùy tiện có thể khiến binder bỏ qua dữ liệu nested.

**Khác biệt phiên bản:** `ValueResolver` xuất hiện từ Spring Framework 6.1; `getNames()` được thêm từ **6.1.2**. Trong các ví dụ cũ dựa trên 6.1.0, interface có thể được viết bằng lambda vì chỉ có một phương thức trừu tượng. Với **6.2.x**, cần triển khai **cả `resolveValue` và `getNames`**, vì đây không còn là functional interface theo hợp đồng hai phương thức.

## 3. Tra cứu tham số nằm ở đâu trong quá trình construct?

Với `DataBinder` core dùng trực tiếp, chuỗi thao tác điển hình là:

1. Tạo `new DataBinder(null, "registration")`: target chưa tồn tại. `"registration"` là object name sử dụng trong báo cáo lỗi.
2. Gọi `binder.setTargetType(ResolvableType.forClass(Registration.class))` để khai báo kiểu cần dựng; thao tác này cần target đang `null`.
3. Chuẩn bị `ValueResolver` biết cách đọc input.
4. Gọi `binder.construct(resolver)`; Spring xác định constructor, tên từng tham số và đọc giá trị qua resolver.
5. `DataBinder` chuyển giá trị thô sang kiểu đích bằng conversion/editor thích hợp.
6. Nếu dữ liệu cho đối tượng lồng nhau tồn tại, Spring có thể đệ quy dựng object con.
7. Kiểm tra `binder.getBindingResult()` để xem lỗi chuyển kiểu/binding; dùng `binder.getTarget()` để lấy đối tượng sau khi dựng thành công.

```text
new DataBinder(null, "registration")
          |
setTargetType(Registration.class)
          |
construct(ValueResolver)
          |
    [name / String] -> "Lan"
    [age / Integer] -> "24" -> 24
          |
new Registration("Lan", 24)
          |
getBindingResult() -> kiểm tra lỗi
getTarget() -> instance nếu tạo thành công
```

`construct(...)` yêu cầu **target chưa có instance** và `targetType` đã được thiết lập. Nếu tạo `DataBinder` với một object có sẵn rồi gọi `construct(...)`, cách dùng đó vi phạm điều kiện API: property binding trên object đã có dùng `bind(PropertyValues)`.

Spring có thể chọn public data constructor hoặc constructor phù hợp theo quy tắc của framework. Với class Java nhiều constructor, sự tồn tại của default/no-arg constructor ảnh hưởng lựa chọn. Để ví dụ dễ dự đoán, ưu tiên một `record` hoặc DTO có một constructor rõ ràng. Khi dùng class thông thường, build phải giữ tên tham số (ví dụ javac `-parameters`), hoặc dùng metadata/annotation được framework hỗ trợ. Java record cũng cung cấp tên record components cho canonical constructor.

## 4. Ví dụ Java 17+ chạy được: MapValueResolver cho record lồng nhau

Ví dụ này dùng **Spring Framework 6.2.x**, **Java 17+** và Maven; không cần ứng dụng Spring Boot, Servlet container, HTTP server hay Jakarta Bean Validation. Ta mô phỏng input request bằng một `Map<String, Object>`, cung cấp custom `ValueResolver` và đọc kết quả từ `DataBinder`.

### Bước 1 — Khai báo dependency

Tạo file `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>value-resolver-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` kéo theo các thư viện Spring Beans/Core cần cho `DataBinder`. Thuộc tính `maven.compiler.parameters=true` giúp giữ tên tham số đối với các data constructors Java thông thường; `record` còn có metadata canonical component names.

### Bước 2 — Tạo class hoàn chỉnh

Tạo `src/main/java/demo/ValueResolverDemo.java`:

```java
package demo;

import java.util.Map;
import java.util.Set;

import org.springframework.core.ResolvableType;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class ValueResolverDemo {

    public record Address(String city) {}

    public record Registration(
            String name,
            Integer age,
            Address address) {}

    public static void main(String[] args) {
        Map<String, Object> input = Map.of(
                "name", "Lan",
                "age", "24",
                "address.city", "Hue");

        DataBinder.ValueResolver resolver =
                new DataBinder.ValueResolver() {

            @Override
            public Object resolveValue(String name, Class<?> type) {
                // Trả raw input: DataBinder tự chuyển kiểu khi cần.
                return input.get(name);
            }

            @Override
            public Set<String> getNames() {
                // Bắt buộc có key "address.city" để phát hiện
                // dữ liệu lồng dưới tham số "address".
                return input.keySet();
            }
        };

        DataBinder binder = new DataBinder(null, "registration");
        binder.setTargetType(
                ResolvableType.forClass(Registration.class));
        binder.construct(resolver);

        BindingResult errors = binder.getBindingResult();
        System.out.println("errors=" + errors.getErrorCount());

        if (errors.hasErrors() || binder.getTarget() == null) {
            System.out.println("binding failed");
            return;
        }

        Registration result = (Registration) binder.getTarget();
        System.out.println("name=" + result.name());
        System.out.println("age=" + result.age());
        System.out.println("city=" + result.address().city());
    }
}
```

### Bước 3 — Biên dịch và chạy

Tại thư mục chứa `pom.xml`:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.ValueResolverDemo
```

Phần stdout do `main` tạo (không tính log Maven):

```text
errors=0
name=Lan
age=24
city=Hue
```

Giải thích theo từng thành phần:

- `new DataBinder(null, ...)` tạo binder chưa có target.
- `ResolvableType.forClass(Registration.class)` khai báo kiểu cần khởi tạo.
- `resolveValue("name", String.class)` lấy `"Lan"`.
- `resolveValue("age", Integer.class)` lấy `"24"`; chuyển chuỗi sang số là việc của `DataBinder`.
- Đối với constructor parameter `address` kiểu `Address`, bản đồ **không có key `"address"`**. Tuy vậy, `getNames()` có `"address.city"`, cho biết có dữ liệu dưới nhánh `address`; binder có thể dựng `Address("Hue")` từ đường dẫn nested.
- `construct(...)` tạo `Registration("Lan", 24, new Address("Hue"))`; `getTarget()` trả instance đó.
- Code in output trực tiếp từ Java record, nên kết quả không phụ thuộc vào thứ tự duyệt `Map.of`.

Đây là một file Java độc lập **trong project Maven đã có `pom.xml` kể trên**. Nếu muốn dùng Gradle, khai báo dependency tương đương `implementation("org.springframework:spring-context:6.2.12")` trong một project Java Gradle phù hợp. Không ghép ví dụ vào Spring Boot project đang dùng BOM version khác mà không kiểm tra tương thích.

### Chạy lại với dữ liệu khác

Thay:

```java
Map<String, Object> input = Map.of(
        "name", "Mai",
        "age", "31",
        "address.city", "Da Nang");
```

Phần giá trị in ra sau `errors=0` sẽ thành:

```text
name=Mai
age=31
city=Da Nang
```

Việc đổi dữ liệu chỉ tác động lên `Map` được resolver đọc; không phải sửa constructor hoặc bổ sung JavaBean setter.

## 5. Vì sao getNames() quan trọng với nested object?

Giả sử DTO có cấu trúc:

```java
public record Customer(
        String fullName,
        Address address) {}

public record Address(String city, String street) {}
```

Đoạn này minh họa **hai record ở cấp top-level**, phải đặt trong hai file `Customer.java` và `Address.java` (hoặc chuyển thành member records của một class).

Input:

```text
fullName=Lan
address.city=Hue
address.street=Le Loi
```

Một `ValueResolver` dựa trên map có thể chỉ lưu các key:

```text
fullName
address.city
address.street
```

Đối với tham số `address`, tra cứu trực tiếp `resolveValue("address", Address.class)` trả `null` vì không có key như vậy. Spring có thể hỏi `getNames()` để xác định liệu có những key mang tiền tố `address.` hay không. Vì **có**, nó đệ quy xử lý constructor của `Address` và tra các đường dẫn `address.city`, `address.street`.

Có thể hình dung:

```text
Customer constructor
  ├── fullName:String
  │       -> resolveValue("fullName", String.class) = "Lan"
  └── address:Address
          -> resolveValue("address", Address.class) = null
          -> getNames() cho biết "address.city" và "address.street"
          -> dựng Address constructor:
                 resolveValue("address.city", String.class) = "Hue"
                 resolveValue("address.street", String.class) = "Le Loi"
          -> Address("Hue", "Le Loi")
  -> Customer("Lan", address)
```

Đây là **mô hình ý nghĩa các lookup**, không bảo đảm thứ tự/số lần phương thức được gọi trong mọi bản Spring. Một resolver tùy chỉnh phải ổn định khi Spring gọi lại cùng key.

Nếu `getNames()` luôn trả `Set.of()` dù `resolveValue("address.city", ...)` có thể đọc được giá trị, Spring có thể kết luận không có dữ liệu nested và bỏ qua việc tạo `Address`. Hậu quả là `customer.address()` có thể là `null` hoặc dữ liệu bị thiếu theo ngữ cảnh. Vì vậy **`getNames()` không phải phương thức trang trí**; nó tham gia quyết định cấu trúc object graph cần được dựng.

Ngược lại, nếu không có bất kỳ key nào dưới `address.`, Spring có thể coi đối số phức tạp đó là *missing* thay vì tự tạo object con rỗng không cần thiết. Điều này khác với property binding tự tăng trưởng object graph khi được cấu hình `autoGrowNestedPaths`; không nên xem hai cơ chế là một.

## 6. NameResolver và ValueResolver: một bên chọn tên, một bên lấy dữ liệu

Hai interface lồng trong `DataBinder` có tên giống nhau nhưng nhiệm vụ khác nhau:

| Phần | API | Câu hỏi cần giải quyết |
| --- | --- | --- |
| `DataBinder.NameResolver` | `String resolveName(MethodParameter parameter)` | “Tham số Java này nên tìm dưới tên nào?” |
| `DataBinder.ValueResolver` | `Object resolveValue(String name, Class<?> type)` | “Với tên và kiểu đã chọn, nguồn input có giá trị nào?” |
| `DataBinder.ValueResolver` | `Set<String> getNames()` | “Nguồn input có tất cả những key nào, kể cả key nested?” |
| Type conversion của `DataBinder` | `ConversionService`/`PropertyEditor` | “Giá trị thô có thể đổi sang kiểu Java cần truyền vào constructor không?” |

Ví dụ tham số constructor `fullName` nhưng HTTP form gửi `full-name`:

```text
full-name=Lan
```

`NameResolver` quyết định dùng key `"full-name"` thay cho `"fullName"`; sau đó `ValueResolver` đọc `"full-name"` từ nguồn. Không nên sửa map giá trị bằng cách tự đoán tên khi Spring đã cung cấp cơ chế name resolution.

Với ứng dụng Spring MVC 6.1+, cách biểu đạt ánh xạ tên thông dụng là `@BindParam`:

```java
import org.springframework.web.bind.annotation.BindParam;

public record PersonInput(
        @BindParam("full-name") String fullName,
        Integer age) {}
```

Đây là record DTO riêng (đặt trong `PersonInput.java` hoặc khai báo member record). Spring MVC hỗ trợ `@BindParam` trên constructor parameters/fields khi dựng `@ModelAttribute`. Đây là annotation của **Spring Web**; ví dụ `ValueResolverDemo` dùng **`DataBinder` core thuần** không tự xử lý annotation Web này nếu chưa cấu hình resolver tên tương ứng.

Nếu dùng trực tiếp `DataBinder` và muốn mapping bằng quy tắc riêng:

```java
// Snippet bên trong method, binder chưa gọi construct().
binder.setNameResolver(parameter -> {
    if ("fullName".equals(parameter.getParameterName())) {
        return "full-name";
    }
    return null; // Cho Spring dùng tên tham số mặc định.
});
```

Với snippet này, `DataBinder` dùng `"full-name"` khi yêu cầu `ValueResolver` đọc giá trị của `fullName`. `null` từ `resolveName` nghĩa là **không tùy biến tên**, Spring trở về việc khám phá tên tham số; khác với `null` do `resolveValue` trả về, vốn nghĩa là **không tìm thấy giá trị**.

## 7. Giá trị thô, kiểu đích và chuyển đổi kiểu

`resolveValue(String name, Class<?> type)` trả `Object`. Nguồn có thể trả `String`, `String[]` hoặc một object đã đúng kiểu. `type` báo **kiểu tham số mà constructor yêu cầu**, không phải lời bảo đảm data source đã có object thuộc kiểu ấy.

| Đầu vào | Kiểu constructor | Việc cần xảy ra |
| --- | --- | --- |
| `"Lan"` | `String` | Dùng trực tiếp |
| `"24"` | `Integer` | Chuyển chuỗi sang `Integer 24` |
| `"true"` | `Boolean` | Chuyển sang `Boolean.TRUE` nếu cấu hình hỗ trợ |
| `"2026-11-02"` | `LocalDate` | Cần conversion/formatter phù hợp |
| `address.city=Hue` | `Address` | Có thể dựng nested object từ các key con |
| `items[0].sku=ABC` | `List<Item>` | Có thể dựng phần tử theo index nếu kiểu và điều kiện phù hợp |

**Không tự ép kiểu sớm khi không cần:** một resolver đơn giản trả raw `String`, rồi để `DataBinder` sử dụng hệ thống conversion đã thiết lập. Làm vậy giúp logic lấy input không phải lặp lại logic parse số/ngày tháng. Tuy nhiên, resolver có quyền dùng `type` để chọn cách trả nhiều giá trị hoặc nội dung đặc biệt, miễn hợp đồng đầu ra phù hợp.

Ví dụ yêu cầu date format:

```java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public record Booking(
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {}
```

Đây là DTO minh họa và **không chứng minh** `DataBinder` thuần chỉ với `spring-context` tự nhận `@DateTimeFormat`. Ứng dụng cần cấu hình `FormattingConversionService`/formatter hỗ trợ Spring Format (hoặc converter phù hợp). Trong MVC/Boot, framework thường cấu hình sẵn các formatter liên quan.

### Input nhiều giá trị

Một tham số HTML form có thể gửi nhiều lần, ví dụ:

```text
tags=java&tags=spring
```

Resolver của web có thể thu được nhiều giá trị; để tránh mất dữ liệu, không viết custom resolver “lấy phần tử đầu tiên” nếu tham số constructor cần `List<String>` hay `String[]`. Cần xét `type` và đặc điểm nguồn dữ liệu. Trong nguồn `Map` của demo, mỗi key chỉ lưu một object; ví dụ không tự hỗ trợ duplicate keys như servlet request.

## 8. Key cho list, map, array và nested collection

Constructor binding của Spring còn hỗ trợ các đường dẫn mang index/key:

```text
accounts[0].name=Lan
accounts[1].name=Mai
labels[home]=Nhà
scores[0]=8
scores[1]=9
```

Với DTO có list/map tương ứng và type metadata đầy đủ, `DataBinder` có thể tìm các key này để tạo collection hoặc object lồng nhau. Một `ValueResolver` tổng quát phải:

1. Giữ nguyên key path và biểu thức trong ngoặc khi lấy từ nguồn.
2. Trả về toàn bộ tên key khả dụng trong `getNames()`, ví dụ `"accounts[0].name"` và `"accounts[1].name"`.
3. Thực thi `resolveValue(name, type)` thống nhất với `getNames()`.
4. Không tự tạo một list không giới hạn chỉ vì client gửi index cực lớn; giới hạn kích thước/độ sâu input ở ranh giới request và cấu hình binder phù hợp.
5. Biết phân biệt key của `Map` và index collection theo type constructor; không giải mã mọi `[...]` theo một công thức duy nhất.

**Spring quyết định xây dựng collection dựa trên metadata kiểu và các tên đã liệt kê; resolver chủ yếu cung cấp raw values/names.** Đối với trường hợp input phức tạp, nên có integration test thực tế vì conversion và constructor của từng element type ảnh hưởng kết quả.

Ví dụ nếu DTO là:

```java
public record OrderInput(java.util.List<Line> lines) {}

public record Line(String sku, Integer quantity) {}
```

Và input `lines[0].sku=ABC&lines[0].quantity=2`, Spring có thể dựng phần tử `Line` từ các đường dẫn lồng nhau khi có thông tin generic đầy đủ. Hai `public record` ở ví dụ này phải nằm trong hai file top-level riêng hoặc được chuyển thành member records.

Không nên suy ra từ `getNames().size()` rằng sẽ có đúng chừng ấy constructor parameters; nhiều key có thể cùng thuộc một đối tượng phức tạp.

## 9. Phân biệt thiếu key, null, chuỗi rỗng và lỗi conversion

Đây là nơi custom resolver dễ tạo lỗi âm thầm nhất.

### A. Không có key

Nếu không tìm được key `"age"`, `resolveValue("age", Integer.class)` thường trả `null`. `DataBinder` xử lý trường hợp này tùy kiểu tham số và metadata: có thể truyền `null` cho kiểu tham chiếu, dùng mặc định trong những ngữ cảnh được hỗ trợ, hoặc báo lỗi khi constructor không thể tạo instance. **Đừng coi thiếu key là tự động sinh FieldError trong mọi trường hợp**.

### B. Key có nhưng giá trị null

`Map#get(...)` trả `null` cả khi thiếu key và khi giá trị thực sự là `null`. `getNames()` giúp framework nhận ra có hay không có tên key, nhất là các đường dẫn lồng nhau, nhưng giao thức `resolveValue` vẫn trả `null` ở cả hai tình huống. Nếu ứng dụng phải phân biệt “chưa gửi” và “client chủ động xóa”, hãy thiết kế input contract và resolver riêng thay vì gán ý nghĩa chắc chắn cho `null`.

### C. Chuỗi rỗng

`age=` tạo chuỗi `""` trong nhiều nguồn request. Chuyển `""` sang `Integer` có thể cho `null` hoặc một kết quả/lỗi phụ thuộc conversion/editor; trong khi `name=""` vẫn là `String` rỗng. Quy tắc “bắt buộc có name” là **validation**, chẳng hạn `@NotBlank` được provider hỗ trợ, không phải ý nghĩa mặc định của `ValueResolver`.

### D. Không chuyển kiểu được

Nếu input là `age=abc` và constructor cần `Integer`, conversion không tạo được số. `DataBinder` ghi lỗi binding/conversion vào `BindingResult` trong trường hợp xử lý được; có thể xem `getFieldError("age")` và các mã lỗi như `typeMismatch`. Trạng thái target sau constructor failure phụ thuộc tình huống; chỉ tiếp tục logic nếu không có lỗi và object thực sự đã tạo.

```java
// Đoạn kiểm tra bên trong một method đã có binder:
var result = binder.getBindingResult();
if (result.hasErrors()) {
    result.getFieldErrors().forEach(error ->
            System.out.println(error.getField() + ": "
                    + error.getCode()));
}
```

Đoạn trên chỉ dùng để debug tên field/mã lỗi và không phải file Java độc lập. Trong hệ thống thật, tránh in `getRejectedValue()` nếu có dữ liệu nhạy cảm; với các exception khởi tạo constructor không được đưa vào `BindingResult`, cần xử lý exception ở mức thích hợp.

### E. Validation tách khỏi binding

`DataBinder.construct(...)` thực hiện binding/khởi tạo. Nó không tự động kiểm tra mọi annotation Jakarta Bean Validation chỉ vì DTO có `@NotBlank` hoặc `@Min`. Cần đăng ký và gọi validator qua `DataBinder.validate(...)` hoặc dùng cơ chế validation được cấu hình bởi Spring MVC khi có `@Valid`. Phân biệt lỗi **gắn kiểu** với lỗi **giá trị vi phạm nghiệp vụ**.

## 10. Trong Spring MVC, ai cung cấp ValueResolver?

Phần lớn ứng dụng Spring MVC không cần viết `ValueResolver` bằng tay. Các lớp web của Spring có thể tạo resolver từ request:

- `ServletRequestDataBinder` có `construct(ServletRequest request)`, dùng resolver dành cho request parameters và multipart input.
- Lớp resolver liên quan là `ServletRequestDataBinder.ServletRequestValueResolver`, thực thi `DataBinder.ValueResolver`. Nó biết cách lấy giá trị theo tên từ servlet request và liệt kê tên đầu vào.
- Các thành phần MVC sử dụng data binder theo chuỗi xử lý `@ModelAttribute`; developer chỉ khai báo model/DTO và cấu hình binder khi cần.

Ví dụ handler `@ModelAttribute` trong một ứng dụng Spring MVC cấu hình đầy đủ:

```java
import jakarta.validation.Valid;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

// Snippet method bên trong một @Controller:
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("registration") RegistrationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "registration-form";
    }
    return "registration-success";
}
```

`RegistrationForm`, các views và Spring MVC/Validation dependency là phần của ứng dụng thật; đây **không phải file Java tự chạy độc lập**. Ở Spring 6 / Boot 3, `@Valid` dùng `jakarta.validation.Valid`; `BindingResult` vẫn thuộc `org.springframework.validation`.

Một request form:

```text
name=Lan&age=24
```

có thể được MVC dùng để dựng record/class được khai báo thích hợp, nhưng kết quả chính xác phụ thuộc loại DTO, constructor, conversion, validation và cấu hình binding. Không nên tạo resolver thủ công chỉ để lặp lại cách MVC đã giải quyết request parameters.

**Khác biệt quan trọng với JSON:** DTO gắn từ `@RequestBody` thường do `HttpMessageConverter` (ví dụ Jackson) deserialization JSON. Không mô tả `DataBinder.ValueResolver` là bộ chuyển JSON mặc định của `@RequestBody`. Phạm vi chủ yếu của nó là constructor binding trong Spring data binding, đặc biệt với `@ModelAttribute` và các binder tương ứng.

## 11. Khi nào cần custom ValueResolver?

Một `ValueResolver` tự viết hữu ích khi:

- Dữ liệu cần dựng object đến từ một `Map`, command-line options, một cấu hình có các key dạng property path hoặc một lớp adapter nguồn dữ liệu riêng.
- Bạn dùng `DataBinder` ở mức core ngoài MVC và muốn kiểm soát cách lookup tên/kiểu.
- Nguồn có kiểu dữ liệu không giống servlet parameters, ví dụ một số key lưu `String[]`, số đã parse, hoặc giá trị từ một API nội bộ.
- Bạn cần tích hợp dữ liệu nested/collection vào constructor binding nhưng muốn giữ logic tra cứu độc lập khỏi logic dựng object.

Không cần custom resolver chỉ vì muốn đổi `full-name` thành `fullName`: trước tiên xem `NameResolver` hoặc `@BindParam` trong MVC. Không cần custom resolver chỉ vì muốn parse ngày theo định dạng: `ConversionService`/formatter mới là nơi đúng để cấu hình quy tắc chuyển kiểu.

### Thiết kế resolver tốt

```java
public final class MapValueResolver
        implements DataBinder.ValueResolver {

    private final Map<String, ?> values;

    public MapValueResolver(Map<String, ?> values) {
        this.values = Map.copyOf(values);
    }

    @Override
    public Object resolveValue(String name, Class<?> type) {
        return values.get(name);
    }

    @Override
    public Set<String> getNames() {
        return values.keySet();
    }
}
```

**Snippet class:** cần import `java.util.Map`, `java.util.Set`, `org.springframework.validation.DataBinder` và đặt trong file/class phù hợp. `Map.copyOf` không nhận key/value `null` và tạo snapshot bất biến; vì vậy đoạn này chỉ phù hợp nguồn dữ liệu không chứa `null`. Nếu cần giữ null, hãy chọn chiến lược sao chép phù hợp và mô tả semantics của dữ liệu.

Một resolver dựa trên snapshot làm cho cả `getNames()` và `resolveValue()` quan sát cùng tập dữ liệu. Nếu lấy names từ nguồn A nhưng values từ nguồn B thay đổi liên tục, binder có thể phát hiện nhánh lồng nhau mà không lấy được trường con, gây khó debug.

### Tránh các side effect

- `resolveValue` không nên xóa key sau lần đọc đầu tiên: Spring có thể hỏi cùng key nhiều lần.
- Không dựa vào thứ tự `getNames()` cho kết quả cuối cùng.
- Không kết hợp input của nhiều người dùng vào một resolver singleton có trạng thái mutable.
- Không trả giá trị khác nhau cho cùng tên/kiểu nếu không có quy tắc rõ ràng.
- Không log trực tiếp input chứa mật khẩu, thông tin cá nhân hoặc token trong resolver.
- Không thay tên key một cách mơ hồ làm mất dấu phân cấp hoặc index.

## 12. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Code không compile vì `getNames()` chưa implement | Sao chép mẫu lambda/interface từ Spring 6.1.0 sang 6.2.x | Implement cả hai phương thức theo version đang dùng |
| `construct(...)` báo thiếu target type | Quên `setTargetType(ResolvableType.forClass(...))` | Khai báo kiểu trước `construct` |
| `construct(...)` báo đã có target | Khởi tạo binder bằng instance thay vì `null` | Dùng binder có target `null` cho constructor binding |
| Object con không được dựng | `getNames()` thiếu các key nested hoặc tên sai prefix | Trả đầy đủ key `address.city`, `items[0].sku`… |
| Trường nhận `null` | Key không khớp tham số hoặc resolver trả null | Kiểm tra `NameResolver`, `resolveValue` và input |
| Giá trị số không hợp lệ | `"abc"` không chuyển sang `Integer` | Xem `BindingResult`; sửa dữ liệu hoặc converter |
| `@BindParam` không có tác dụng trong custom core binder | Chỉ dùng `DataBinder` core, chưa có NameResolver phù hợp | Cấu hình tên riêng hoặc dùng Spring MVC có hỗ trợ annotation |
| Dữ liệu nhập nhiều giá trị bị mất | Resolver lấy một `String` đầu tiên dù target cần mảng/list | Đọc đủ giá trị và xét `type` |
| Constructor không nhận đúng parameter name | Metadata tên bị mất hoặc class có nhiều constructor khó chọn | Giữ `-parameters`/dùng record/data constructor rõ ràng |
| Nhầm `getNames()` với danh sách constructor parameters | Đây là tập input key, có thể có nhiều key nested/extra | Xem cấu trúc dữ liệu và target type |
| Tưởng `allowedFields` chặn constructor args | Allowed fields là rào chắn chủ yếu cho property binding | Giới hạn input bằng DTO constructor rõ ràng |
| Trả raw value không đúng kiểu mà không có converter | `DataBinder` không đổi kiểu được | Cài `ConversionService`/editor phù hợp |
| Không kiểm tra `BindingResult` | Dùng target dù có lỗi bind | Kiểm tra lỗi trước khi xử lý nghiệp vụ |

## 13. An toàn dữ liệu và giới hạn phạm vi tra cứu

Constructor binding thường an toàn hơn so với việc cho phép sửa mọi setter của một entity, vì chỉ những tham số mà constructor khai báo mới được Spring dùng để dựng object. Tuy nhiên, **constructor cũng có thể chứa tham số không nên nhận từ client**. Ví dụ nếu DTO constructor có tham số `role`, client có thể thử gửi `role=ADMIN`; việc tạo DTO không tự thực hiện authorization.

Các nguyên tắc cần tuân thủ:

1. Tạo **request DTO chuyên biệt** chỉ có những field phía client được phép cung cấp.
2. Không đặt entity có property bảo mật vào constructor request-facing chỉ vì thuận tiện.
3. Nếu cần property binding sau constructor binding, kiểm soát bằng `setDeclarativeBinding(true)` và/hoặc `setAllowedFields(...)` theo thiết kế. Trong Spring MVC, property binding có thể diễn ra sau khi dựng object nếu chưa giới hạn.
4. Kiểm soát size, số lượng và độ sâu của input collection/nested path; tránh key index khổng lồ khiến ứng dụng phải cấp phát/tạo quá nhiều object.
5. Không lấy `getNames()` làm cơ chế security filter; nó chỉ mô tả những key hiện có. Validation/authorization vẫn phải được thực hiện riêng.
6. Không dùng output từ `resolveValue` để tạo SQL expression, filesystem path hay reflection tùy ý mà không có allowlist/ngữ nghĩa hợp lệ.

Ví dụ bật declarative binding trong controller Spring MVC:

```java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

// Đoạn nằm trong class @Controller:
@InitBinder
void initBinding(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

Với cấu hình này, Spring ưu tiên constructor binding; property binding chỉ tiếp tục cho những field được khai báo `allowedFields` khi thích hợp. Đây là biện pháp giảm over-posting đối với model mutable. Nó không thay thế kiểm tra quyền sử dụng thuộc tính trong service.

## 14. Cách kiểm thử ValueResolver một cách có ý nghĩa

Để phân biệt lỗi của resolver với lỗi của constructor hoặc converter, nên kiểm tra cả ba tầng.

### A. Test resolver độc lập

- `resolveValue("name", String.class)` đọc đúng chuỗi đầu vào.
- `resolveValue("age", Integer.class)` có thể trả raw `"24"` để binder chuyển sau.
- `resolveValue("unknown", String.class)` trả `null` khi key vắng.
- `getNames()` chứa mọi key kể cả `"address.city"`.
- Cùng key được gọi nhiều lần phải trả kết quả nhất quán nếu nguồn không đổi.

### B. Test DataBinder.construct

- Happy path: tạo record có đủ các field và nested object, `getErrorCount() == 0`.
- Type mismatch: `age="abc"` tạo lỗi chuyển kiểu có thể quan sát trong `BindingResult`; không xử lý target như object hợp lệ.
- Missing input: xác minh semantics của `null`, giá trị thiếu và validation theo DTO.
- Alias: kiểm tra `NameResolver` hoặc `@BindParam` tra đúng tên `full-name`.
- Nested collection: kiểm tra key dạng `items[0].name` và giới hạn index.
- Source mutation: nếu nguồn có khả năng đổi trong lúc binding, tạo snapshot nhằm bảo đảm dữ liệu nhất quán.

### C. Test tích hợp MVC nếu dùng web

Gửi form request thật tới controller để chắc chắn lớp resolver dành cho servlet, cấu hình formatter và `@Valid` hoạt động như mong đợi. Kiểm tra status/response tương ứng với input hợp lệ, sai kiểu, thiếu field và field không được phép gán. Không xem việc unit test `MapValueResolver` thành công là bằng chứng rằng mọi request format/multipart binding đều hoạt động.

### Một phép thử sửa nhanh từ ví dụ runnable

Đổi đúng giá trị `"age", "24"` trong `Map.of(...)` thành `"age", "abc"`. Sau đó chạy lại và quan sát nhánh `errors.hasErrors()`, bởi `"abc"` không chuyển được thành `Integer` theo converter số thông dụng. Đừng đoán rằng object đích luôn tồn tại với state hợp lệ sau lỗi; hãy kiểm tra `BindingResult` trước.

## 15. Tóm tắt API và tư duy triển khai

- `DataBinder.ValueResolver` là **nguồn tra giá trị** cho constructor binding, không phải bộ tự dựng instance hay validator.
- `resolveValue(name, type)` tìm **một giá trị** cho tên và kiểu tham số; có thể trả raw `String` rồi để `DataBinder` chuyển kiểu.
- `getNames()` trả **toàn bộ input keys**, quan trọng khi phát hiện nested constructor arguments, list/map/array; trong Spring 6.2 phải triển khai cả hai phương thức.
- `DataBinder.NameResolver` xác định tên dùng tra cứu; `@BindParam` là cách Spring MVC ánh xạ tên input khác tên Java.
- Để dùng core API: `new DataBinder(null, name)` → `setTargetType(ResolvableType)` → `construct(ValueResolver)` → kiểm tra `getBindingResult()` → sử dụng `getTarget()` khi thành công.
- Thiết kế DTO và ranh giới input rõ ràng; validation và authorization là bước tiếp theo, không phải chức năng do resolver tự đảm nhận.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html)
- [Spring Framework 6.2 API — DataBinder.ValueResolver](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.ValueResolver.html)
- [Spring Framework 6.2 API — DataBinder](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 API — DataBinder.NameResolver](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.NameResolver.html)
- [Spring Framework 6.2 API — ServletRequestDataBinder](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/bind/ServletRequestDataBinder.html)
- [Spring Framework 6.2 API — @BindParam](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/bind/annotation/BindParam.html)
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — Data Binding and Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html)
