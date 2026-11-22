# @Valid với tham số và kết quả chứa đối tượng lồng trong kiểm tra phương thức

## Mục tiêu bài học

Một phương thức có thể nhận DTO chứa nhiều lớp đối tượng, đồng thời trả về một DTO chứa các đối tượng khác. Ví dụ, `BookingCommand` chứa `Customer` và `Address`; kết quả `BookingReceipt` chứa `Delivery` rồi lại chứa `Address`. Khi các ràng buộc nằm trong đối tượng con, đánh dấu constraint trên chính phương thức chưa đủ: cần hiểu **cascaded validation** bằng `@Valid`.

Sau bài này, bạn có thể:

- Giải thích `jakarta.validation.Valid` làm gì trên **tham số phương thức**, **giá trị trả về**, và từng liên kết tới đối tượng lồng.
- Phân biệt `@Valid` với các constraint trực tiếp như `@NotNull`, `@NotBlank`, `@Min`, `@NotEmpty`.
- Tự kiểm tra input bằng `ExecutableValidator.validateParameters()` và output bằng `validateReturnValue()`.
- Đọc vị trí lỗi trong `ConstraintViolation.getPropertyPath()` ở cả hai chiều.
- Tích hợp vào service qua Spring method validation, vào controller qua Spring MVC và biết khi nào các cơ chế validation khác nhau được kích hoạt.
- Xử lý đúng các trường hợp `null`, collection, validation groups, kế thừa phương thức và lỗi thường gặp.

## 1. Tại sao @Valid quan trọng khi đối tượng lồng nhau?

Xét cấu trúc dữ liệu:

~~~text
BookingCommand (tham số của place)
├── customer: Customer
│   ├── name: String             @NotBlank
│   └── address: Address         @Valid
│       └── city: String         @NotBlank
└── seats: int                   @Min(1)

BookingReceipt (giá trị trả về của place)
├── id: String                   @NotBlank
└── delivery: Delivery           @Valid
    └── address: Address         @Valid
        └── city: String         @NotBlank
~~~

Nếu chỉ validate `BookingCommand` ở cấp ngoài và không cho phép đi theo quan hệ `customer`, Bean Validation sẽ không tự động kiểm tra mọi đối tượng tùy ý reachable từ object gốc. `@Valid` đánh dấu **đường liên kết cần tiếp tục duyệt**.

Ví dụ khai báo:

~~~java
public final class BookingCommand {
    @NotNull
    @Valid
    private Customer customer;
}
~~~

Trong đó:

- `@NotNull` kiểm tra **bản thân tham chiếu `customer`** có hiện diện hay không.
- `@Valid` yêu cầu provider **đi vào đối tượng `Customer`** để kiểm tra các constraint bên trong nó.
- Nếu `Customer.address` cũng là đối tượng con, field/getter đó cần `@Valid` để tiếp tục tới `Address.city`.
- `@Valid` **không** tự đặt điều kiện dữ liệu; nó là **cascade marker**, không phải một annotation constraint như `@NotNull`.

Chính sự phân biệt này giải thích vì sao `@Valid` thường được đặt cùng `@NotNull` tại ranh giới quan trọng. Một quan hệ có thể hợp lệ về định dạng khi khác `null` nhưng nghiệp vụ vẫn cần nó tồn tại.

## 2. Ba vị trí sử dụng @Valid trong kiểm tra phương thức

Giả sử service có phương thức:

~~~java
@NotNull
@Valid
public BookingReceipt place(@NotNull @Valid BookingCommand command) {
    // ...
}
~~~

Ý nghĩa các vị trí:

| Vị trí | Annotation | Tác dụng |
| --- | --- | --- |
| Trên tham số `command` | `@NotNull` | Không cho phép truyền `null` |
| Trên tham số `command` | `@Valid` | Cascade kiểm tra các constraint bên trong `BookingCommand` |
| Trên phương thức trả về `BookingReceipt` | `@NotNull` | Không cho phép giá trị trả về `null` |
| Trên phương thức trả về `BookingReceipt` | `@Valid` | Cascade kiểm tra các constraint bên trong kết quả |
| Trên field `customer` và `delivery` của DTO | `@Valid` | Tiếp tục duyệt các đối tượng con, có thể nhiều tầng |

### 2.1. Validation trước khi gọi phương thức

Một tích hợp method validation có thể kiểm tra tham số **trước khi thực thi phần thân**:

~~~text
caller
  -> interceptor / AOP / framework
  -> validateParameters(target, method, arguments)
  -> có lỗi: từ chối lời gọi hoặc ném exception
  -> không lỗi: thực thi method body
~~~

Nhờ vậy, input sai có thể bị chặn trước khi service thay đổi dữ liệu hoặc thực hiện xử lý nghiệp vụ. Tuy nhiên, bản thân Jakarta Validation API **không tự chặn** một lời gọi Java thông thường: điểm kích hoạt phải được cấu hình hoặc gọi một cách chủ động.

### 2.2. Validation sau khi phương thức trả về

Kết quả cũng có thể bị kiểm tra:

~~~text
method body trả về BookingReceipt
  -> validateReturnValue(target, method, receipt)
  -> có lỗi: tích hợp validation báo lỗi hậu điều kiện
  -> không lỗi: trả kết quả về caller
~~~

Đây là kiểm tra **postcondition**: giúp phát hiện service tạo ra output không đạt contract. Lỗi return value thường là lỗi của ứng dụng hoặc dữ liệu phía server, không nên tự động coi là lỗi nhập liệu HTTP 400.

### 2.3. Duyệt đệ quy không bị giới hạn ở một tầng

Các constraint ở `Address.city` chỉ được khám phá khi mỗi liên kết cần thiết được đánh dấu:

~~~text
@Valid trên method parameter
    ↓
BookingCommand.customer có @Valid
    ↓
Customer.address có @Valid
    ↓
Address.city có @NotBlank
~~~

Nếu bỏ `@Valid` trên `Customer.address`, việc kiểm tra `Address.city` qua nhánh đó sẽ dừng, dù `Address.city` vẫn có `@NotBlank`.

Tương tự, với return value:

~~~text
@Valid trên method return
    ↓
BookingReceipt.delivery có @Valid
    ↓
Delivery.address có @Valid
    ↓
Address.city có @NotBlank
~~~

Không được suy diễn rằng chỉ thêm `@Valid` trên lớp `Address` hoặc khai báo `@NotBlank` cho field `city` sẽ khiến mọi phương thức trả về chứa nó tự động bị kiểm tra.

## 3. @Valid khác gì với validator.validate(bean)?

Có hai đường vào Bean Validation mà lập trình viên dễ nhầm:

**Đường 1 — kiểm tra bean:** `Validator.validate(bean)` bắt đầu tại một đối tượng đã có. Nó kiểm tra các constraint trên bean rồi đi theo các field/property `@Valid`. Ví dụ `validator.validate(new BookingCommand(...))` kiểm tra `customer`, `address` và `seats` nếu metadata được khai báo đúng.

**Đường 2 — kiểm tra phương thức:** `Validator.forExecutables()` cung cấp `ExecutableValidator`. Nó kiểm tra constraint/cascade khai báo **tại tham số** hoặc **giá trị trả về** của một method/constructor. API chính:

~~~java
ExecutableValidator executable = validator.forExecutables();

Set<ConstraintViolation<ServiceType>> inputErrors =
        executable.validateParameters(
                service, method, methodArguments);

Set<ConstraintViolation<ServiceType>> outputErrors =
        executable.validateReturnValue(
                service, method, returnedObject);
~~~

Đây là code minh họa theo biến tổng quát, không phải file Java độc lập. Hai API trên **không gọi method** cho bạn; `validateParameters()` nhận arguments, còn `validateReturnValue()` nhận kết quả đã có. Cần truyền `Method` và target object phù hợp.

`validator.validate(service)` không duyệt và chạy hết các method của service để kiểm tra tham số/giá trị trả về giả định. Ngược lại, `validateReturnValue(...)` không kiểm tra lại parameters của lần gọi trước. Mỗi bước có vai trò rõ ràng.

## 4. Ví dụ Java 17+ chạy độc lập: input và output đều lồng nhiều tầng

Dự án minh họa có file `src/main/java/com/example/validation/Demo.java`. Chạy bằng Jakarta Validation API với một provider như Hibernate Validator. Các constraint đặt trên private fields được Bean Validation đọc từ metadata; không bắt buộc phải thêm getter chỉ để ví dụ này hoạt động.

### 4.1. Mã nguồn hoàn chỉnh

~~~java
package com.example.validation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.lang.reflect.Method;
import java.util.Set;

public final class Demo {

    public static final class Address {
        @NotBlank
        private final String city;

        public Address(String city) {
            this.city = city;
        }
    }

    public static final class Customer {
        @NotBlank
        private final String name;

        @NotNull
        @Valid
        private final Address address;

        public Customer(String name, Address address) {
            this.name = name;
            this.address = address;
        }
    }

    public static final class BookingCommand {
        @NotNull
        @Valid
        private final Customer customer;

        @Min(1)
        private final int seats;

        public BookingCommand(Customer customer, int seats) {
            this.customer = customer;
            this.seats = seats;
        }
    }

    public static final class Delivery {
        @NotNull
        @Valid
        private final Address address;

        public Delivery(Address address) {
            this.address = address;
        }
    }

    public static final class BookingReceipt {
        @NotBlank
        private final String id;

        @NotNull
        @Valid
        private final Delivery delivery;

        public BookingReceipt(String id, Delivery delivery) {
            this.id = id;
            this.delivery = delivery;
        }
    }

    public static final class BookingService {

        @NotNull
        @Valid
        public BookingReceipt place(
                @NotNull @Valid BookingCommand command) {

            // Kết quả cố ý có city rỗng để minh họa
            // kiểm tra hậu điều kiện (return value).
            return new BookingReceipt(
                    "R-1",
                    new Delivery(new Address("")));
        }
    }

    private static void report(
            String label,
            Set<? extends ConstraintViolation<?>> violations) {
        System.out.println(label + ": " + violations.size());
    }

    public static void main(String[] args) throws Exception {

        BookingService service = new BookingService();
        Method place = BookingService.class.getMethod(
                "place", BookingCommand.class);

        BookingCommand invalidCommand = new BookingCommand(
                new Customer("", new Address("")),
                0);

        BookingCommand validCommand = new BookingCommand(
                new Customer("An", new Address("Ha Noi")),
                2);

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            var executable = validator.forExecutables();

            var invalidInput = executable.validateParameters(
                    service, place,
                    new Object[] { invalidCommand });

            var validInput = executable.validateParameters(
                    service, place,
                    new Object[] { validCommand });

            report("invalid input", invalidInput);
            report("valid input", validInput);

            // Chỉ thực thi nghiệp vụ với input hợp lệ.
            BookingReceipt receipt = service.place(validCommand);

            var invalidOutput = executable.validateReturnValue(
                    service, place, receipt);

            report("invalid output", invalidOutput);
        }
    }
}
~~~

Vì sao có ba lỗi input? `BookingCommand.seats == 0` vi phạm `@Min(1)`, `Customer.name == ""` vi phạm `@NotBlank`, và `Customer.address.city == ""` vi phạm `@NotBlank`. Cả hai nhánh sâu đều reachable qua các liên kết `@Valid`.

Vì sao có một lỗi output? `BookingService.place(...)` trả một `BookingReceipt` với `Delivery.address.city == ""`. Nhờ `@Valid` trên phương thức trả về và hai liên kết trong kết quả, Bean Validation đi tới `Address.city` và phát hiện `@NotBlank`.

Quan trọng: phương thức `place(...)` **không tự kiểm tra** bên trong method body. Trong demo, chúng ta chủ động gọi hai bước của `ExecutableValidator`, rồi mới gọi method với input hợp lệ.

### 4.2. Build và chạy

Tạo `pom.xml` tại thư mục dự án:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>cascaded-method-validation</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.3.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dùng JDK 17+ và Maven:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.validation.Demo
~~~

**Đúng ba dòng do chương trình `Demo` in ra**; không tính log của Maven hoặc provider:

~~~text
invalid input: 3
valid input: 0
invalid output: 1
~~~

`<parameters>true</parameters>` khiến compiler lưu tên parameter Java trong class file; điều này có ích khi đọc path. Nếu không có metadata tên thực, path có thể dùng `arg0` thay vì `command`, nhưng số lượng violation trong demo không thay đổi.

Hibernate Validator 8.x là provider Jakarta Validation 3.0 phù hợp ví dụ Java 17. Ví dụ tự cung cấp provider và implementation Jakarta EL để chạy ngoài Spring. Trong ứng dụng Spring Boot 3 đã có `spring-boot-starter-validation`, nên dùng dependency management của dự án thay vì copy các phiên bản Maven cố định này nguyên xi.

### 4.3. Đọc chính xác đường dẫn của lỗi

`ConstraintViolation.getPropertyPath()` là một chuỗi **node có kiểu**, không chỉ là một chuỗi ký tự. Khi muốn hiển thị/debug, có thể dùng:

~~~java
for (ConstraintViolation<?> violation : invalidInput) {
    System.out.println(
            violation.getPropertyPath() + " -> "
            + violation.getMessage());
}
~~~

Đây là **đoạn trích dành cho bên trong phương thức `main`** khi biến `invalidInput` còn trong scope; không phải một class hoàn chỉnh. Vì `Set` không đảm bảo thứ tự lặp, không dự đoán thứ tự các dòng từ vòng lặp này.

Với lớp Java biên dịch có `-parameters` và provider thông thường, đường đi sẽ tương tự:

~~~text
place.command.customer.name
place.command.customer.address.city
place.command.seats

place.<return value>.delivery.address.city
~~~

Ba dòng đầu là các path của input (không theo thứ tự cụ thể); dòng cuối là path của return value. Các tên như `place` và `command` đến từ chữ ký method; `customer`, `address`, `city` là tên property từ metadata bean.

Mô hình node:

~~~text
Input:
METHOD(place)
  -> PARAMETER(command, index=0)
     -> PROPERTY(customer)
        -> PROPERTY(address)
           -> PROPERTY(city)

Return:
METHOD(place)
  -> RETURN_VALUE(<return value>)
     -> PROPERTY(delivery)
        -> PROPERTY(address)
           -> PROPERTY(city)
~~~

Bạn có thể đọc node bằng API thay vì tách chuỗi:

~~~java
for (ConstraintViolation<?> violation : invalidInput) {
    for (jakarta.validation.Path.Node node
            : violation.getPropertyPath()) {

        System.out.println(
                node.getKind() + " : " + node.getName());

        if (node.getKind()
                == jakarta.validation.ElementKind.PARAMETER) {

            var p = node.as(
                    jakarta.validation.Path.ParameterNode.class);

            System.out.println(
                    "parameterIndex=" + p.getParameterIndex());
        }
    }
}
~~~

Đây cũng là snippet chèn bên trong `main`. Nếu cần trả lỗi theo tên tham số hoặc vị trí, `Path.ParameterNode.getParameterIndex()` đáng tin hơn việc tự parse path bằng dấu chấm; cấu trúc có thể xuất hiện thêm container element node và index/key.

## 5. Điều gì xảy ra với null?

Quy tắc cốt lõi: **cascaded validation bỏ qua tham chiếu `null`**. `@Valid` tự nó không đồng nghĩa với bắt buộc có giá trị.

| Khai báo | Giá trị | Kết quả |
| --- | --- | --- |
| `@Valid BookingCommand command` | `null` | Không có lỗi chỉ vì `@Valid` |
| `@NotNull @Valid BookingCommand command` | `null` | Có lỗi `@NotNull` |
| `@Valid BookingCommand command` | instance có `customer == null` | Chỉ có lỗi nếu thuộc tính `customer` có constraint riêng như `@NotNull` |
| `@NotNull @Valid Customer customer` | `null` | Có lỗi `@NotNull`, không tiếp tục vào field con |
| `@Valid` trên method return | `null` | Chỉ `@Valid` thì không lỗi |
| `@NotNull @Valid` trên method return | `null` | Vi phạm constraint `@NotNull` của return value |

Ví dụ muốn cả parameter và kết quả phải hiện diện:

~~~java
@NotNull
@Valid
public BookingReceipt place(
        @NotNull @Valid BookingCommand command) {
    // ...
}
~~~

Đó là lý do kết hợp `@NotNull` và `@Valid` trong demo.

Lưu ý `@NotBlank` chỉ phù hợp các giá trị kiểu `CharSequence`; `@NotEmpty` dành cho các kiểu chuỗi/collection/map/array mà constraint hỗ trợ; `@Min` kiểm tra giá trị số, không phải kích thước collection. Chọn constraint theo loại dữ liệu cần kiểm tra.

## 6. @Valid trên collection và phần tử của container

Nhiều phương thức nhận hoặc trả về `List`/`Map`, bên trong chứa DTO. Jakarta Bean Validation hỗ trợ **container element validation** với `@Valid` đặt ở type argument.

Ví dụ:

~~~java
public void placeBatch(
        @NotEmpty java.util.List<@Valid BookingCommand> commands) {
    // ...
}
~~~

Hai ý nghĩa:

- `@NotEmpty` kiểm tra **danh sách không rỗng**.
- `@Valid` tại `List<@Valid BookingCommand>` đánh dấu **mỗi phần tử DTO** để cascade tới các ràng buộc bên trong.

Nếu `commands` có một phần tử `null`, bản thân `@Valid` trên phần tử đó bỏ qua nó. Muốn cấm phần tử `null`, thêm constraint lên type argument:

~~~java
public void placeBatch(
        @NotEmpty java.util.List<
                @NotNull @Valid BookingCommand> commands) {
    // ...
}
~~~

Ví dụ return value chứa list các receipt:

~~~java
@NotNull
public java.util.List<@Valid BookingReceipt> listReceipts() {
    // ...
}
~~~

Khi **return-value validation được kích hoạt**, provider có thể cascade từng `BookingReceipt`, rồi theo `@Valid` trên `delivery`/`address`. Nếu muốn cấm list rỗng, cần `@NotEmpty`; nếu muốn cấm phần tử null, cần `@NotNull` trên type argument.

Với map:

~~~java
public void accept(
        java.util.Map<@NotBlank String, @Valid BookingCommand> items) {
    // ...
}
~~~

Constraint trên key (ví dụ `@NotBlank`) và cascade vào value (`@Valid`) là hai loại kiểm tra khác nhau. Các container element có value extractor tương ứng sẽ được kiểm tra đúng loại phần tử; path có thể chứa index/key và `CONTAINER_ELEMENT` nodes.

### Container lồng container

Ví dụ dữ liệu dạng `List<List<BookingCommand>>`:

~~~java
public void acceptGroups(
        java.util.List<java.util.List<@Valid BookingCommand>> groups) {
    // ...
}
~~~

`@Valid` được đặt ở type argument của container trong cùng cần kiểm tra. Khi thiết kế cấu trúc phức tạp, phải bảo đảm path và value extractor phù hợp thay vì giả định validator luôn đi qua mọi cấp container. Theo Jakarta Validation, không nên đặt đồng thời `@Valid` lên **chính một container và type argument tương ứng** chỉ để ép cascade hai lần; hãy chọn vị trí rõ ràng cho từng phần tử cần duyệt.

## 7. Spring Framework: service method validation

Trong Spring, Bean Validation thường được kích hoạt tự động ở một số ranh giới nhờ integration. Với **service method** do Spring quản lý, cách điển hình là method validation qua proxy.

Ví dụ rút gọn:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class BookingApplicationService {

    @NotNull
    @Valid
    public BookingReceipt place(
            @NotNull @Valid BookingCommand command) {

        // Trả về một receipt hợp lệ theo nghiệp vụ.
        return createReceipt(command);
    }

    private BookingReceipt createReceipt(BookingCommand command) {
        // Hàm minh họa, cần implement trong ứng dụng thật.
        throw new UnsupportedOperationException("Example only");
    }
}
~~~

Đoạn Spring ở trên chỉ minh họa **nơi đặt annotation** và giả định các DTO đã được định nghĩa; không phải chương trình runnable độc lập. Trong ứng dụng thật, phải cài đặt `createReceipt` và cấu hình method validation (ví dụ Spring Boot có validation starter và bean `MethodValidationPostProcessor` phù hợp).

Khi một thành phần **khác** gọi phương thức `place(...)` qua Spring-managed proxy, validation interceptor có thể:

1. Kiểm tra `command` và các object lồng bằng `validateParameters()`.
2. Cho thực thi method nếu không có violation.
3. Kiểm tra `BookingReceipt` trả về bằng `validateReturnValue()`, bao gồm cả các đối tượng con.
4. Báo lỗi nếu constraint trên tham số hoặc kết quả bị vi phạm.

Với cấu hình method validation qua Spring AOP thông thường, lỗi có thể được báo bằng `ConstraintViolationException`; một số chế độ cấu hình dùng exception/adapted results khác. Không viết xử lý dựa trên giả định toàn ứng dụng chỉ có một exception type nếu chưa kiểm tra Spring version và cấu hình.

### Những giới hạn proxy cần hiểu

- **Self-invocation:** một method trong cùng bean gọi `this.place(...)` thường không đi qua Spring AOP proxy, vì vậy validation qua interceptor có thể không chạy.
- **Không phải mọi object đều là Spring bean:** nếu tạo `new BookingApplicationService()` bằng tay, nó không tự có proxy.
- **Method visibility / final / proxy type:** các quy tắc proxy của Spring ảnh hưởng method nào được intercept; hãy xác nhận lời gọi qua proxy thực tế.
- **Nhánh bất đồng bộ:** kết quả trả về kiểu future/reactive container cần hiểu cơ chế validation của framework đang dùng; đừng suy ra `@Valid` tự động kiểm tra một object được phát ra trong tương lai theo cách giống một return value đồng bộ.
- **Nhánh ném exception:** nếu method không tạo normal return value, không có đối tượng kết quả thường lệ để validate tại bước return.

Nói cách khác, annotation mô tả **validation metadata**; cơ chế framework quyết định **khi nào** và **ở đâu** gọi các API thực thi nó.

## 8. Spring MVC: @Valid @RequestBody và validation của return value

Với REST controller, `@Valid @RequestBody` thường được dùng để kiểm tra DTO nhận từ HTTP request:

~~~java
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class BookingController {

    @PostMapping("/bookings")
    BookingReceipt create(
            @Valid @RequestBody BookingCommand command) {
        // Gọi service thực tế.
        throw new UnsupportedOperationException("Illustration only");
    }
}
~~~

Đây là snippet mô tả cấu hình controller; khi triển khai cần thay phần thân bằng nghiệp vụ thật.

**Khi chỉ có `@Valid` trên tham số DTO:** Spring MVC có thể validate object riêng ở bước argument resolution, thường báo `MethodArgumentNotValidException` nếu lỗi và không có `BindingResult` phù hợp xử lý. `@Valid` không tự là constraint và **một mình nó không bắt buộc kích hoạt method validation** trên toàn bộ chữ ký controller.

**Khi method cần được validate:** từ Spring Framework 6.1, Spring MVC hỗ trợ method validation native cho controller khi có constraint trực tiếp trên parameter hoặc return value. Ví dụ:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class StrictBookingController {

    @PostMapping("/strict-bookings")
    @NotNull
    @Valid
    BookingReceipt create(
            @NotNull @Valid @RequestBody BookingCommand command) {
        // Gọi service và trả một BookingReceipt hợp lệ.
        throw new UnsupportedOperationException("Illustration only");
    }
}
~~~

Ở trường hợp này `@NotNull` là constraint trực tiếp, nên Spring MVC method validation có thể bao phủ cả nested constraints qua `@Valid`. Khi method validation xử lý lỗi, Spring MVC 6.1+ có `HandlerMethodValidationException`; trường hợp argument-level validation riêng thường dùng `MethodArgumentNotValidException`.

Một số lưu ý khi thiết kế API:

- Với **input**, controller có thể chuyển lỗi DTO thành HTTP 400; cần xử lý đúng dạng exception và chính sách API của ứng dụng.
- Với **return value**, lỗi thường thể hiện vấn đề phía server, nên không trình bày như lỗi client nhập liệu. `HandlerMethodValidationException` của return-value validation được Spring MVC xử lý theo ngữ nghĩa khác với lỗi parameter.
- Nếu controller đang có `@Validated` ở **cấp lớp**, method validation có thể đi qua AOP proxy. Để dùng native method validation được Spring MVC đưa vào từ 6.1, tài liệu Spring khuyến nghị bỏ class-level `@Validated` ở controller khi phù hợp.
- `@Valid` trên `@RequestBody` và `@Valid` trên kết quả trả về có **hai điểm kích hoạt khác nhau**; việc request body được validate không chứng minh return value đang được validate.
- Khi có `Errors`/`BindingResult` theo đúng vị trí, Spring MVC có thể chuyển một phần lỗi input tới controller để xử lý thay vì ném ngay exception. Cách xử lý còn phụ thuộc method có constraint trực tiếp trên tham số khác hay không.

### Tránh nhầm tên thành phần

| Thành phần | Vai trò |
| --- | --- |
| `jakarta.validation.Valid` | Marker cho cascade vào đối tượng con |
| `jakarta.validation.constraints.NotNull` | Constraint trực tiếp cấm null |
| `jakarta.validation.Validator` | API kiểm tra một bean; cung cấp `forExecutables()` |
| `jakarta.validation.executable.ExecutableValidator` | API kiểm tra method/constructor parameters và return values |
| `org.springframework.validation.annotation.Validated` | Spring annotation hỗ trợ groups và tích hợp method validation trong bối cảnh thích hợp |
| `@RequestBody` | Spring MVC lấy và bind HTTP body thành argument |
| `@ControllerAdvice` / `@ExceptionHandler` | Nơi ứng dụng tùy biến HTTP error responses |

Khi xây dựng exception handler, nên kiểm tra source của từng `ConstraintViolation` và trả đường dẫn lỗi phù hợp với contract của API, thay vì gộp mọi lỗi thành “field invalid” mà không phân biệt parameter, nested property hay return value.

## 9. Validation groups đi qua object lồng

Bean Validation hỗ trợ **groups** để chọn tập ràng buộc áp dụng. Theo mặc định, khi cascade qua `@Valid`, nhóm đang được kiểm tra tiếp tục được truyền xuống đối tượng con (có tính đến các quy tắc groups/group sequence).

Ví dụ:

~~~java
interface DetailedChecks { }

final class Address {
    @jakarta.validation.constraints.NotBlank(
            groups = DetailedChecks.class)
    String city;
}
~~~

Snippet trên chỉ minh họa metadata của group, không đứng độc lập với các class trong demo. Nếu method parameter được validate theo `Default` mà `city` chỉ thuộc `DetailedChecks`, constraint đó không tự chạy chỉ vì có `@Valid`.

Có thể dùng `@ConvertGroup` trên một cạnh cascade để chuyển nhóm:

~~~java
@jakarta.validation.Valid
@jakarta.validation.groups.ConvertGroup(
        from = jakarta.validation.groups.Default.class,
        to = DetailedChecks.class)
private Address address;
~~~

Điều này có nghĩa khi tới liên kết `address` theo nhóm `Default`, group của đối tượng được cascade đổi sang `DetailedChecks`. Cần thiết kế cẩn thận: group conversion áp dụng **tại nơi có `@Valid`**; nó không phải bộ lọc thay đổi mọi constraint của toàn ứng dụng. Trong Spring, `@Validated(SomeGroup.class)` có thể chọn nhóm đầu vào tùy điểm tích hợp. Khi method validation xảy ra, group nào chạy phụ thuộc configuration của integration/caller.

## 10. Quy tắc kế thừa method: tránh làm contract không tương thích

Bean Validation bảo vệ nguyên tắc tiền điều kiện và hậu điều kiện trong kế thừa:

- **Parameter constraints** (kể cả cascade `@Valid` trên tham số) nhìn chung không được thêm ở phương thức override/implement để **siết chặt precondition** so với phương thức cha/interface; provider chuẩn có thể ném `ConstraintDeclarationException` khi gặp khai báo vi phạm.
- **Return-value constraints** có thể xuất hiện ở phương thức subtype theo quy tắc chuẩn, vì việc bổ sung hậu điều kiện không làm yếu lời hứa của method.
- Tuy nhiên, **return value không được đánh dấu cascade `@Valid` lặp lại nhiều lần trên cùng một nhánh kế thừa** nếu đã được đánh dấu ở parent/interface.

Ví dụ interface đã có:

~~~java
interface BookingApi {
    @Valid
    BookingReceipt place(BookingCommand command);
}
~~~

Implementation không nên tự bổ sung `@Valid` vào return value của cùng phương thức lần nữa hoặc tự thêm `@Valid` trên tham số nếu interface chưa khai báo, vì có thể vi phạm rule của Jakarta Validation. Nếu cần constraint là một phần contract công khai, xác định nơi khai báo nhất quán ngay từ interface.

Một số provider có tùy chọn mở rộng ngoài chuẩn, nhưng ứng dụng muốn portable cần tuân thủ quy tắc chung. Khi gặp `ConstraintDeclarationException`, trước tiên xem method override, interface, bridge method và vị trí annotation, không tự loại bỏ mọi constraint.

## 11. Chu trình validation và lỗi phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| DTO cha hợp lệ dù field con sai | Thiếu `@Valid` trên một liên kết trong graph | Đặt `@Valid` đúng cạnh tham chiếu vào đối tượng cần kiểm tra |
| `null` được cho qua bất ngờ | `@Valid` chỉ cascade, không bắt buộc có dữ liệu | Thêm `@NotNull` ở parameter/return/field tương ứng |
| Validate input chạy nhưng output sai vẫn thoát | Chưa đánh dấu `@Valid` trên return value hoặc không có post-invocation validation | Cấu hình return-value validation và kiểm tra `validateReturnValue()` |
| Gọi service trực tiếp không có lỗi | Chỉ annotation mà không có trigger method validation | Gọi `ExecutableValidator` hoặc cấu hình proxy/interceptor phù hợp |
| Trong Spring, gọi cùng bean không kích hoạt | Self-invocation vượt qua proxy | Gọi qua Spring-managed bean/proxy hoặc thiết kế lại service boundary |
| Trùng exception kỳ vọng trong controller | Spring MVC argument validation và method validation là hai cơ chế | Phân biệt `MethodArgumentNotValidException` và `HandlerMethodValidationException` |
| List có một item sai nhưng chưa thấy lỗi | Chưa cascade vào element hoặc không có value extractor phù hợp | Dùng `List<@Valid Item>` và kiểm tra metadata, integration |
| Phần tử `null` trong list được chấp nhận | `@Valid` không cấm null | Dùng `List<@NotNull @Valid Item>` |
| Không có lỗi khi validate object bằng `validate(service)` | Field validation không phải executable validation | Dùng `validator.forExecutables()` cho method/constructor |
| Hai lần đánh dấu cascade trong override | Vi phạm rule metadata kế thừa | Rà soát khai báo trên interface/parent/implementation |
| Test sai thứ tự thông báo | `Set<ConstraintViolation>` không đảm bảo thứ tự | So bằng `propertyPath`/constraint descriptor; sắp xếp nếu cần |
| Violation path chứa nhiều cấp | Graph có property/container element nodes | Duyệt từng `Path.Node`, tránh split chuỗi mù quáng |

### Lưu ý chu trình, hiệu năng và an toàn

Cascaded validation duyệt graph đối tượng có thể nhiều tầng và nhiều phần tử. Provider tuân thủ Jakarta Validation phải tránh vòng lặp vô hạn khi object graph có chu trình (ví dụ `Person.manager` trỏ ngược về `Person`). Tuy vậy, graph rất lớn vẫn làm tăng công việc kiểm tra: thiết kế DTO và cạnh `@Valid` có chủ đích.

Một đối tượng có thể có nhiều đường dẫn tới cùng instance; provider có thể tạo violation gắn với các path tương ứng theo quy tắc graph traversal. Không nên dựa vào số lần một `ConstraintValidator.isValid()` được gọi để biểu thị số request hoặc thao tác nghiệp vụ.

Không dùng Bean Validation để sửa input hoặc thực hiện side effect quan trọng. Validator nên tập trung trả trạng thái hợp lệ; hành động thay đổi dữ liệu, chuẩn hóa giá trị hay gọi cơ sở dữ liệu với tác dụng phụ thuộc tầng phù hợp.

Không phản chiếu nguyên `getInvalidValue()` vào log/API response cho dữ liệu nhạy cảm. Path và thông điệp đủ để xác định loại lỗi trong phần lớn use case.

## 12. Cách kiểm thử phần input và output

Ít nhất nên chia test thành các trường hợp sau:

1. **Input hợp lệ:** `validateParameters()` trả tập rỗng; dùng `BookingCommand` có `Customer.name`, `Address.city` hợp lệ và `seats >= 1`.
2. **Input lồng sai ở một nhánh:** để `Customer.address.city = ""`, kiểm tra violation path có property `city` dưới tham số `command`.
3. **Input lồng sai ở nhiều nhánh:** như demo, có ba lỗi ở `seats`, `customer.name`, `customer.address.city`.
4. **Input null:** thử `command == null` để thấy `@NotNull` báo lỗi. Sau đó thử bỏ `@NotNull` (trong một fixture test riêng) để xác nhận `@Valid` đơn lẻ bỏ qua null.
5. **Output hợp lệ:** trả `BookingReceipt` có `delivery.address.city` đúng, rồi gọi `validateReturnValue()`; tập lỗi rỗng.
6. **Output lồng sai:** trả `BookingReceipt` chứa city rỗng và xác minh có return-value node trên path.
7. **Thiếu một cạnh @Valid:** thử fixture bỏ `@Valid` trên `Delivery.address`; nested city không được cascade qua cạnh đó.
8. **Spring integration:** gọi method từ một bean khác qua proxy và xác minh exception thực tế; riêng controller nên test bằng `MockMvc` hoặc công cụ HTTP thích hợp cho các response lỗi.

Khi kiểm thử method validation, xây dựng `Method` bằng `Class.getMethod(name, parameterTypes...)` đúng signature; dùng `ValidatorFactory` với provider thật để kiểm chứng metadata và cascade. Không giả định thứ tự lỗi trong `Set`; xác minh bằng `Path.Node`, tên constraint và số lượng lỗi theo fixture.

Ví dụ muốn tách riêng lỗi từ return value:

~~~java
var outputErrors = validator.forExecutables()
        .validateReturnValue(service, place, receipt);

boolean nestedCityViolation = outputErrors.stream()
        .map(v -> v.getPropertyPath().toString())
        .anyMatch(path -> path.endsWith("delivery.address.city"));
~~~

Đây là snippet với các biến `validator`, `service`, `place`, `receipt` đã được tạo trước; không chạy độc lập. Với ứng dụng production, có thể duyệt `Path.Node` theo loại để hỗ trợ các path chứa container/index thay vì giả định mọi path đều kết thúc bằng chuỗi cố định.

## 13. Tóm tắt để tự kiểm tra

Hãy tự giải thích các tình huống:

**Câu 1.** Tại sao `@Valid` trên tham số `BookingCommand` không đủ nếu `Customer.address` thiếu `@Valid`?  
Vì cascade chỉ đi qua những cạnh được đánh dấu; nó dừng trước `Address.city`.

**Câu 2.** Tại sao `@Valid` trên return value có thể không phát hiện object thiếu hoàn toàn?  
Vì null bị bỏ qua khi cascade; muốn return value bắt buộc hiện diện cần `@NotNull`.

**Câu 3.** `validator.validate(service)` có thay `validateReturnValue(service, method, result)` được không?  
Không. Hai API có root/metadata khác nhau: bean fields so với ràng buộc của executable.

**Câu 4.** Trong Spring MVC, `@Valid @RequestBody` và method validation có luôn ném cùng exception không?  
Không. Tùy chữ ký method và constraint trực tiếp, Spring MVC có thể dùng argument validation riêng hoặc method validation.

**Câu 5.** Cần đặt `@Valid` ở đâu nếu method trả `List<BookingReceipt>`?  
Có thể dùng type argument `List<@Valid BookingReceipt>` để cascade từng phần tử và tiếp tục vào các field lồng đã khai báo `@Valid`; bổ sung `@NotNull`/`@NotEmpty` tại đúng vị trí nếu nghiệp vụ yêu cầu.

**Mô hình ghi nhớ:** `@Valid` chỉ ra **đường duyệt graph**, constraint như `@NotNull`/`@NotBlank` xác định **điều kiện hợp lệ**, còn `ExecutableValidator` hoặc Spring integration quyết định **thời điểm kiểm tra trước/sau lời gọi phương thức**. Đặt đủ marker trên parameter/return value và từng cạnh chứa object con mới kiểm tra được toàn bộ vùng dữ liệu mong muốn.

## Tài liệu tham khảo

- [Jakarta Bean Validation 3.0 specification — Object graph validation và method/constructor validation](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Validation — Valid annotation](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Valid.html)
- [Jakarta Validation — ExecutableValidator API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/executable/ExecutableValidator.html)
- [Hibernate Validator 8 Reference Guide — Cascaded validation và method constraints](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
- [Spring Framework Reference — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework Reference — Method validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
