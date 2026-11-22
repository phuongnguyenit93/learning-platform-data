# Vai trò của module hỗ trợ tên tham số constructor

Jackson thường tạo JavaBean bằng constructor rỗng rồi gán các property qua setter hoặc field. Với lớp bất biến, cách này không phù hợp: các field thường là `final`, không có setter và object phải được khởi tạo đầy đủ ngay trong constructor.

Jackson có thể dùng constructor hoặc static factory method làm creator. Khi đó, mỗi tham số creator cần được liên kết với một property JSON. `@JsonProperty` cho phép khai báo tên tường minh; module `jackson-module-parameter-names` cho phép Jackson lấy tên tham số từ metadata mà Java compiler ghi vào bytecode.

Module này giúp giảm annotation lặp lại trên constructor, nhưng chỉ hoạt động khi mã Java được biên dịch với tùy chọn `-parameters`. Nó không thể tự khôi phục tên tham số nếu metadata đó không tồn tại, và cũng không thay thế việc chỉ rõ creator khi lớp có nhiều constructor hoặc cách khởi tạo mơ hồ.

## 1. Bài toán tên tham số khi deserialize

Xét một lớp bất biến:

~~~java
public final class Customer {
    private final String firstName;
    private final int age;

    public Customer(String firstName, int age) {
        this.firstName = firstName;
        this.age = age;
    }

    public String getFirstName() {
        return firstName;
    }

    public int getAge() {
        return age;
    }
}
~~~

JSON đầu vào:

~~~json
{
  "firstName": "An",
  "age": 28
}
~~~

Jackson cần biết JSON property `firstName` truyền vào tham số constructor nào và `age` truyền vào tham số nào.

Cách tường minh truyền thống là gắn `@JsonProperty` cho từng tham số:

~~~java
@JsonCreator
public Customer(
        @JsonProperty("firstName") String firstName,
        @JsonProperty("age") int age) {
    this.firstName = firstName;
    this.age = age;
}
~~~

Cách này rõ ràng và không phụ thuộc compiler flag. Nhưng với nhiều lớp bất biến, việc lặp lại annotation có thể làm constructor dài. `ParameterNamesModule` giúp Jackson đọc tên tham số từ metadata Java thay cho việc phải khai báo từng tên bằng annotation.

## 2. Tên tham số trong bytecode Java

Từ Java 8, reflection API có thể đọc tên tham số thông qua `java.lang.reflect.Parameter`, nếu class được biên dịch với tùy chọn `-parameters`.

~~~java
Constructor<?> constructor =
    Customer.class.getConstructor(String.class, int.class);

for (Parameter parameter : constructor.getParameters()) {
    System.out.println(parameter.getName());
    System.out.println(parameter.isNamePresent());
}
~~~

Khi biên dịch có `-parameters`, kết quả có thể là:

~~~text
firstName
true
age
true
~~~

Nếu không bật tùy chọn đó, bytecode thường không chứa tên tham số thực. Reflection có thể trả về các tên tổng quát như `arg0`, `arg1`, và `isNamePresent()` trả về `false`.

| Nguồn tên | Ví dụ | Có cần `-parameters`? |
|---|---|---|
| `@JsonProperty("firstName")` | Tên JSON khai báo trực tiếp | Không |
| Metadata reflection của constructor | `firstName` | Có |
| Tên biến trong source nhưng metadata không được lưu | Có thể chỉ còn `arg0` | Có, nếu muốn Jackson đọc tên thật |

Tùy chọn compiler là bước build-time. Đăng ký module ở runtime không thể tạo lại thông tin đã bị bỏ khỏi bytecode.

## 3. ParameterNamesModule là gì?

`ParameterNamesModule` thuộc artifact `jackson-module-parameter-names`. Module bổ sung khả năng introspection tên tham số Java cho Jackson Databind.

Khi module được đăng ký, Jackson có thể dùng tên tham số mà reflection cung cấp làm tên property cho các tham số creator phù hợp. Nhờ đó, constructor có thể giữ mã Java tự nhiên mà không phải gắn `@JsonProperty` lên từng tham số.

Module không tự làm mọi constructor trở thành creator. Nó cung cấp tên property; việc chọn constructor hoặc factory method vẫn tuân theo quy tắc creator của Jackson và metadata trên lớp.

Hai nhiệm vụ cần phân biệt:

- `@JsonCreator`: chỉ ra constructor hoặc static factory method được dùng để tạo object.
- `ParameterNamesModule`: giúp Jackson biết tên các tham số của creator từ bytecode.

## 4. Thêm dependency

Artifact cần dùng:

~~~text
com.fasterxml.jackson.module:jackson-module-parameter-names
~~~

### 4.1. Maven

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.module</groupId>
    <artifactId>jackson-module-parameter-names</artifactId>
    <version>${jackson.version}</version>
</dependency>
~~~

### 4.2. Gradle Groovy DSL

~~~groovy
dependencies {
    implementation "com.fasterxml.jackson.module:jackson-module-parameter-names:$jacksonVersion"
}
~~~

### 4.3. Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation("com.fasterxml.jackson.module:jackson-module-parameter-names:$jacksonVersion")
}
~~~

Nên dùng cùng phiên bản Jackson cho Databind, Core và module. Nếu dự án quản lý Jackson bằng BOM hoặc dependency management của framework, hãy để dependency version được quản lý tập trung thay vì tự ghim một phiên bản module khác.

## 5. Bật compiler option -parameters

Đây là điều kiện để module đọc được tên tham số thật từ reflection.

### 5.1. Maven Compiler Plugin

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Cấu hình này yêu cầu compiler ghi metadata tên tham số vào bytecode.

### 5.2. Gradle Groovy DSL

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

### 5.3. Gradle Kotlin DSL

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Sau khi thay đổi compiler option, cần build lại các class liên quan. Chỉ thay cấu hình runtime hoặc thêm dependency module không làm thay đổi bytecode đã biên dịch trước đó.

Nếu một thư viện bên ngoài đã được biên dịch mà không có metadata tham số, ứng dụng sử dụng thư viện đó không thể tự thêm tên tham số vào class của thư viện.

## 6. Đăng ký ParameterNamesModule với ObjectMapper

Trong ứng dụng tự tạo mapper, có thể đăng ký module trực tiếp:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.module.paramnames.ParameterNamesModule;

ObjectMapper mapper = JsonMapper.builder()
    .addModule(new ParameterNamesModule())
    .build();
~~~

Hoặc:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new ParameterNamesModule());
~~~

Sau khi đăng ký, mapper có thể dùng parameter name metadata khi introspect constructor/factory method.

Ví dụ này chỉ đăng ký module hỗ trợ tên tham số. Nếu DTO còn dùng `LocalDate`, `Optional` hoặc các kiểu đặc biệt khác, vẫn cần module tương ứng như `JavaTimeModule` hoặc `Jdk8Module` theo kiểu dữ liệu và phiên bản Jackson của dự án.

## 7. Kết hợp @JsonCreator và ParameterNamesModule

Đây là cách thường dùng cho lớp bất biến: đánh dấu constructor làm creator, còn tên tham số được module cung cấp.

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;

public final class Customer {
    private final String firstName;
    private final int age;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Customer(String firstName, int age) {
        this.firstName = firstName;
        this.age = age;
    }

    public String getFirstName() {
        return firstName;
    }

    public int getAge() {
        return age;
    }
}
~~~

Không cần `@JsonProperty` trên từng tham số nếu:

1. Constructor được chọn làm creator.
2. Class được biên dịch với `-parameters`.
3. Mapper đã đăng ký `ParameterNamesModule`.
4. Tên JSON khớp với tên property mà Jackson nhận diện sau các quy tắc naming strategy.

Đọc JSON:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new ParameterNamesModule())
    .build();

Customer customer = mapper.readValue(
    """
    {
      "firstName": "An",
      "age": 28
    }
    """,
    Customer.class
);
~~~

Jackson dùng tên tham số `firstName` và `age` để ghép property JSON với constructor argument, sau đó gọi constructor để tạo object.

Nếu thiếu một trong các điều kiện trên, kết quả có thể là lỗi mapping, không tìm được creator property hoặc không thể khởi tạo object tùy cấu hình và phiên bản.

## 8. Module không thay thế @JsonCreator

Một lớp có thể có nhiều constructor:

~~~java
public final class Customer {
    public Customer(String firstName, int age) {
        // ...
    }

    public Customer(String firstName) {
        // ...
    }

    public Customer() {
        // ...
    }
}
~~~

Tên tham số có sẵn không nhất thiết đủ để Jackson biết constructor nào phải được dùng. Module chỉ bổ sung tên cho các tham số; nó không quyết định ý nghĩa nghiệp vụ của từng cách khởi tạo.

Hãy đánh dấu creator rõ ràng:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Customer(String firstName, int age) {
    // ...
}
~~~

Nếu có nhiều creator được đánh dấu hoặc nhiều constructor có thể được suy luận, Jackson có thể báo lỗi creator mơ hồ hoặc không thể chọn cách tạo object. Giữ một creator phù hợp cho mỗi kiểu dữ liệu và kiểm tra rõ các factory method.

## 9. Property-based và delegating creator với constructor một tham số

Constructor chỉ có một tham số có thể mang hai ý nghĩa khác nhau.

### 9.1. Property-based creator

Muốn nhận một JSON object có property tên `customerId`:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public CustomerId(String customerId) {
    this.value = customerId;
}
~~~

JSON:

~~~json
{
  "customerId": "cus-42"
}
~~~

Tên tham số có thể được lấy từ `-parameters` thông qua module.

### 9.2. Delegating creator

Muốn nhận trực tiếp một JSON string:

~~~java
@JsonCreator(mode = JsonCreator.Mode.DELEGATING)
public CustomerId(String value) {
    this.value = value;
}
~~~

JSON:

~~~json
"cus-42"
~~~

Trong trường hợp delegating, toàn bộ JSON value được chuyển vào tham số creator. Tên tham số không được dùng để tìm một property trong object.

Với constructor một tham số, nên khai báo `JsonCreator.Mode.PROPERTIES` hoặc `DELEGATING` rõ ràng theo hình dạng JSON mà API yêu cầu. Không dựa vào suy luận mặc định khi hai cách hiểu có thể khác nhau.

## 10. Dùng tên JSON khác tên tham số Java

Tên tham số lấy từ bytecode thường là tên Java. Nhưng API có thể dùng một tên khác, ví dụ snake_case.

Java:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Customer(String firstName, int age) {
    // ...
}
~~~

JSON:

~~~json
{
  "first_name": "An",
  "age": 28
}
~~~

Nếu mapper sử dụng naming strategy phù hợp, Jackson có thể chuyển tên property theo quy tắc đó:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new ParameterNamesModule())
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();
~~~

Nếu wire name cần cố định hoặc không theo một quy tắc chuyển đổi chung, dùng `@JsonProperty` tường minh:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Customer(
        @JsonProperty("first_name") String firstName,
        @JsonProperty("age") int age) {
    // ...
}
~~~

`@JsonProperty` có thể ghi đè tên suy luận cho tham số tương ứng. Đây là lựa chọn phù hợp khi tên JSON là một phần ổn định của hợp đồng API và cần được nhìn thấy trực tiếp trong source code.

Có thể dùng `@JsonAlias` nếu cần chấp nhận thêm tên cũ khi deserialize:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public Customer(
        @JsonProperty("first_name")
        @JsonAlias("firstName")
        String firstName,
        @JsonProperty("age")
        int age) {
    // ...
}
~~~

Alias hỗ trợ đọc các tên đầu vào khác nhau; tên chuẩn dùng cho serialization vẫn được điều khiển bởi property metadata.

## 11. Dùng ParameterNamesModule với static factory method

Creator có thể là static factory method, không chỉ constructor.

~~~java
public final class Customer {
    private final String firstName;
    private final int age;

    private Customer(String firstName, int age) {
        this.firstName = firstName;
        this.age = age;
    }

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public static Customer create(String firstName, int age) {
        if (age < 0) {
            throw new IllegalArgumentException("age must not be negative");
        }

        return new Customer(firstName, age);
    }

    public String getFirstName() {
        return firstName;
    }

    public int getAge() {
        return age;
    }
}
~~~

Nếu factory method được biên dịch với `-parameters` và module được đăng ký, Jackson có thể lấy tên tham số của method để ánh xạ các property.

Factory method hữu ích khi cần kiểm tra dữ liệu, chuẩn hóa giá trị hoặc kiểm soát constructor private. Dù dùng constructor hay factory, tên tham số vẫn phải có sẵn hoặc được khai báo bằng `@JsonProperty`.

## 12. Vai trò của ParameterNamesModule trong hệ thống module Jackson

Jackson Databind có cơ chế module để mở rộng introspection, serializer, deserializer và các quy tắc ánh xạ.

`ParameterNamesModule` bổ sung một annotation introspector có thể tìm tên tham số từ reflection. Khi mapper xây dựng metadata cho creator, thông tin đó được dùng cùng các annotation và quy tắc khác của Jackson.

Các nguồn thông tin có thể tham gia xác định creator property gồm:

- `@JsonProperty`: tên được khai báo tường minh.
- `ParameterNamesModule`: tên tham số từ metadata reflection.
- Các annotation hoặc metadata khác mà Jackson hỗ trợ.
- Naming strategy của mapper.
- Cấu hình creator discovery và visibility.

Nếu có nhiều nguồn cùng cung cấp thông tin, metadata tường minh thường nên được ưu tiên để hợp đồng JSON dễ hiểu và ổn định. Tránh dựa vào tên suy luận cho những field có tên wire khác tên Java hoặc có yêu cầu tương thích đặc biệt.

Module hỗ trợ parameter names không phải mix-in. Mix-in dùng để bổ sung annotation cho một kiểu mà không sửa source class; ParameterNamesModule đọc metadata tên tham số đã có trong bytecode. Hai cơ chế có thể được dùng cùng nhau nếu dự án cần, nhưng giải quyết hai vấn đề khác nhau.

## 13. Tùy chọn creator binding của module

`ParameterNamesModule` có constructor cho phép truyền `JsonCreator.Mode`:

~~~java
new ParameterNamesModule(JsonCreator.Mode.PROPERTIES)
~~~

Tùy chọn này cho phép cấu hình mode creator mặc định khi module cung cấp metadata tham số. Nó có thể hữu ích nếu dự án muốn diễn giải creator parameters theo hướng property-based một cách nhất quán.

Tuy nhiên, với creator một tham số, việc phân biệt object property-based và scalar delegating ảnh hưởng trực tiếp đến hình dạng JSON. Khai báo `@JsonCreator(mode = ...)` ngay trên creator là cách rõ ràng nhất khi từng lớp có ý nghĩa khác nhau.

Không nên đổi mode toàn module mà không kiểm tra các kiểu hiện có, đặc biệt khi mapper dùng chung cho nhiều DTO hoặc thư viện.

## 14. Kiểm tra bytecode có tên tham số hay chưa

Có thể xác nhận bằng reflection thay vì chỉ đoán từ source code:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

Constructor<?> constructor =
    Customer.class.getConstructor(String.class, int.class);

for (Parameter parameter : constructor.getParameters()) {
    if (!parameter.isNamePresent()) {
        throw new IllegalStateException(
            "Constructor parameter names are missing"
        );
    }

    System.out.println(parameter.getName());
}
~~~

Nếu `isNamePresent()` trả về false:

- Kiểm tra compiler option `-parameters`.
- Xác nhận class được build lại sau khi thay đổi cấu hình.
- Kiểm tra class đang chạy có đúng artifact mới hay không.
- Nếu class đến từ dependency bên ngoài, kiểm tra cách dependency đó được biên dịch.

Reflection check này xác nhận metadata của class. Nó chưa chứng minh Jackson đã đăng ký module hoặc chọn đúng constructor; cần kiểm thử deserialize qua mapper thật.

## 15. Kiểm thử constructor parameter names

Ví dụ JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.module.paramnames.ParameterNamesModule;
import org.junit.jupiter.api.Test;

class CustomerParameterNamesTest {
    private final ObjectMapper mapper = JsonMapper.builder()
        .addModule(new ParameterNamesModule())
        .build();

    @Test
    void createsImmutableObjectUsingConstructorParameterNames()
            throws Exception {

        Customer customer = mapper.readValue(
            """
            {
              "firstName": "An",
              "age": 28
            }
            """,
            Customer.class
        );

        assertEquals("An", customer.getFirstName());
        assertEquals(28, customer.getAge());
    }
}
~~~

Test cần chạy trên class được biên dịch với `-parameters`. Nếu test chỉ chạy trong IDE với compiler setting khác Maven/Gradle, kết quả có thể không giống pipeline CI.

Nên kiểm tra cả:

- Constructor được đánh dấu `@JsonCreator`.
- Tên tham số có trong bytecode.
- Module được đăng ký trên đúng ObjectMapper.
- Tên property JSON đúng với tên được suy luận hoặc naming strategy.
- Property thiếu hoặc sai kiểu tạo ra lỗi phù hợp.
- Serialization output có tên property đúng theo hợp đồng.

## 16. Khi nào nên dùng ParameterNamesModule?

| Tình huống | Lựa chọn phù hợp |
|---|---|
| Nhiều lớp bất biến có constructor rõ ràng | ParameterNamesModule + `-parameters` |
| Một constructor cần tên JSON khác tên Java | `@JsonProperty` tường minh |
| Có nhiều constructor hoặc factory method | Đánh dấu creator rõ bằng `@JsonCreator` |
| Constructor một tham số có thể là scalar hoặc object | Chỉ rõ `PROPERTIES` hoặc `DELEGATING` |
| Không kiểm soát được cách dependency được biên dịch | Dùng `@JsonProperty` hoặc DTO adapter |
| Dùng Java record với Jackson hỗ trợ record | Thường dùng hỗ trợ record tích hợp; không cần module chỉ để lấy component name |
| Cần thêm annotation cho class thư viện | Cân nhắc mix-in; đây là nhu cầu khác với parameter-name module |

Java record có metadata component riêng và các phiên bản Jackson hiện đại hỗ trợ canonical constructor của record trực tiếp. Không nên xem `ParameterNamesModule` là điều kiện bắt buộc để deserialize record; kiểm tra phiên bản Jackson nếu dự án dùng record.

## 17. Các lỗi thường gặp

**Chỉ thêm dependency mà quên đăng ký module.** Với mapper tự tạo, dependency trên classpath không đảm bảo mapper đó sử dụng module. Đăng ký module rõ ràng hoặc xác nhận framework đã cấu hình nó.

**Đăng ký module nhưng quên -parameters.** Module không thể đọc tên thật nếu compiler không ghi metadata. Kiểm tra `Parameter.isNamePresent()`.

**Đánh dấu @JsonCreator nhưng không có tên property.** Jackson biết constructor được chọn nhưng vẫn cần tên tham số hoặc `@JsonProperty` để ghép dữ liệu.

**Cho rằng module tự chọn đúng constructor.** Module cung cấp tên; nó không thay thế creator selection. Dùng `@JsonCreator` khi cần chỉ định rõ.

**Dùng tên tham số làm wire contract mà không kiểm soát build.** Nếu class được build bởi nhiều pipeline hoặc dependency ngoài, metadata có thể không nhất quán. Dùng `@JsonProperty` cho tên JSON cần ổn định tuyệt đối.

**Nhầm ParameterNamesModule với mix-in.** Một module đọc metadata reflection; mix-in bổ sung annotation từ bên ngoài class. Chọn cơ chế theo vấn đề thực tế.

**Không kiểm thử mapper production.** Mapper riêng trong test có thể đăng ký module khác với mapper của ứng dụng. Kiểm thử cấu hình thực tế được dùng ở runtime.

## 18. Ghi nhớ

- `ParameterNamesModule` giúp Jackson lấy tên tham số constructor/static factory từ Java reflection.
- Cần dependency `jackson-module-parameter-names`, đăng ký module và biên dịch class với `-parameters`.
- Module cung cấp tên creator property; `@JsonCreator` vẫn xác định constructor hoặc factory method được dùng.
- `@JsonProperty` vẫn cần thiết khi wire name khác tên Java hoặc cần hợp đồng JSON tường minh.
- Không có `-parameters`, reflection thường chỉ thấy tên tổng quát như `arg0`; module không thể khôi phục tên source.
- Với constructor một tham số, xác định rõ `PROPERTIES` hay `DELEGATING`.
- Tên tham số là metadata build-time; phải build lại class sau khi bật compiler option.
- Giữ phiên bản module tương thích với Jackson Core/Databind và kiểm thử mapper thực tế.
- Java record được Jackson hiện đại hỗ trợ theo cơ chế riêng; module này không phải điều kiện bắt buộc cho canonical record constructor.

