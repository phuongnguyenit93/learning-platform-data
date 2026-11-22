# Tên tham số, metadata biên dịch và khác biệt theo phiên bản

Khi một constructor của Spring cần một bean theo kiểu Java, Spring thường tìm các bean phù hợp **theo type**. Nếu có nhiều bean cùng type, container cần thêm thông tin để quyết định bean nào sẽ được inject. Một trong những tín hiệu dự phòng là **tên tham số**: nếu tên tham số trùng với bean name hoặc alias của một ứng viên phù hợp, Spring có thể chọn ứng viên đó.

Cơ chế này dễ gây bất ngờ khi nâng cấp Spring. Tên tham số trong mã nguồn không phải lúc nào cũng được lưu vào bytecode. Từ **Spring Framework 6.1**, Spring không còn đọc tên tham số bằng cách phân tích local-variable debug table; Java code cần được biên dịch với cờ **`-parameters`** để tên tham số có sẵn qua Java Reflection. Sang **Spring Framework 6.2**, thuật toán chọn bean được điều chỉnh thêm, có đường xử lý nhanh cho trường hợp tên khớp và có annotation `@Fallback`.

Bài học thuộc chương **Chọn bean** của **Spring Boot Fundamentals**. Chúng ta sẽ đi từ quy tắc chọn bean theo tên, qua metadata do compiler tạo, đến cách cấu hình Gradle/Maven và khác biệt giữa các phiên bản Spring.

## 1. Tên tham số được dùng ở bước nào?

Giả sử ứng dụng có hai implementation cùng type:

```java
public interface PaymentGateway {
    String charge(long amount);
}
```

```java
import org.springframework.stereotype.Component;

@Component("cardGateway")
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public String charge(long amount) {
        return "Thanh toán bằng thẻ: " + amount;
    }
}
```

```java
import org.springframework.stereotype.Component;

@Component("bankGateway")
public class BankPaymentGateway implements PaymentGateway {

    @Override
    public String charge(long amount) {
        return "Thanh toán qua ngân hàng: " + amount;
    }
}
```

Giờ một service yêu cầu một `PaymentGateway`:

```java
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Spring tìm thấy hai bean phù hợp:

| Bean name | Kiểu triển khai | Type mà bean đáp ứng |
|---|---|---|
| `cardGateway` | `CardPaymentGateway` | `PaymentGateway` |
| `bankGateway` | `BankPaymentGateway` | `PaymentGateway` |

Constructor yêu cầu **một** `PaymentGateway`, nhưng không có thông tin cho biết phải dùng bean nào. Nếu không có quy tắc lựa chọn khác, Spring báo lỗi nhập nhằng, thường có `NoUniqueBeanDefinitionException` nằm trong chuỗi `UnsatisfiedDependencyException`.

Nếu đổi tham số thành:

```java
public CheckoutService(PaymentGateway bankGateway) {
    this.gateway = bankGateway;
}
```

thì tên `bankGateway` có thể trở thành một tín hiệu để Spring chọn bean cùng tên, **nếu tên tham số có trong metadata runtime và các quy tắc ưu tiên khác không quyết định một ứng viên khác**.

Đây là một bước dự phòng trong cơ chế autowiring. Nó không biến `@Autowired` thành cơ chế tìm bean thuần theo tên.

### 1.1. Phân biệt ba loại tên

| Loại tên | Ví dụ | Được dùng để làm gì? |
|---|---|---|
| Tên class | `BankPaymentGateway` | Định danh kiểu Java, thường nằm trong package |
| Bean name | `bankGateway` | Định danh bean trong Spring container |
| Tên tham số | `bankGateway` trong constructor | Metadata của injection point, có thể được dùng để phân giải ứng viên |

Ba tên có thể giống nhau nhưng không bắt buộc phải giống nhau.

Ví dụ:

```java
@Service("bankGateway")
public class BankPaymentGateway implements PaymentGateway {
    // ...
}
```

```java
public CheckoutService(PaymentGateway selectedGateway) {
    this.gateway = selectedGateway;
}
```

Tên class là `BankPaymentGateway`, bean name là `bankGateway`, còn tên tham số là `selectedGateway`. Trong trường hợp này, tên tham số không trùng bean name; Spring vẫn có thể inject nếu chỉ có một bean phù hợp, hoặc nếu có quy tắc chọn khác.

### 1.2. Quy tắc tên không bỏ qua type

Giả sử có một bean tên `bankGateway` nhưng bean đó không implement `PaymentGateway`. Constructor:

```java
public CheckoutService(PaymentGateway bankGateway) {
    // ...
}
```

không thể nhận một object không tương thích chỉ vì tên trùng nhau. `@Autowired` vẫn bắt đầu từ các ứng viên phù hợp với kiểu dependency; tên tham số chỉ hỗ trợ phân biệt các ứng viên phù hợp.

Đây là khác biệt quan trọng so với một số cơ chế lookup trực tiếp bằng tên.

## 2. Quy trình lựa chọn bean ở mức khái niệm

Khi Spring giải quyết một dependency đơn lẻ, có thể hình dung các bước chính:

```text
Điểm injection
  Constructor / method / field
          │
          ▼
Tìm bean phù hợp với required type
          │
          ▼
Lọc theo qualifier và điều kiện autowire candidate
          │
          ▼
Xem các chỉ dẫn ưu tiên:
  @Primary, @Fallback (từ 6.2), @Priority...
          │
          ▼
Nếu còn cần phân giải:
  so khớp injection-point name
  với bean name hoặc alias
          │
          ▼
Chọn được một bean?
     ┌────┴────┐
     │         │
    Có       Không
     │         │
     ▼         ▼
  Inject    Báo lỗi thiếu hoặc
            nhập nhằng bean
```

Đây là sơ đồ khái niệm, không phải thứ tự nội bộ bất biến cho mọi phiên bản. Spring có các quy tắc cụ thể về qualifier, primary, fallback, priority và dependency name; một số ưu tiên đã thay đổi giữa 6.1 và 6.2.

Các điểm cần nhớ:

- **Type** xác định tập ứng viên ban đầu.
- **`@Qualifier`** thu hẹp tập ứng viên theo qualifier phù hợp.
- **`@Primary`** chỉ định bean ưu tiên khi cần một bean đơn lẻ.
- **`@Fallback`** (từ Spring Framework 6.2) đánh dấu bean dự phòng.
- **Tên tham số** có thể giúp chọn bean cùng tên trong tập ứng viên phù hợp.
- Nếu vẫn không xác định được một ứng viên duy nhất, Spring báo lỗi thay vì tự chọn ngẫu nhiên.

## 3. Ví dụ: tên tham số trùng bean name

Ta giữ hai bean `cardGateway` và `bankGateway`. Thay constructor bằng:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway bankGateway) {
        this.gateway = bankGateway;
    }

    public String checkout(long amount) {
        return gateway.charge(amount);
    }
}
```

Trong điều kiện:

1. Cả hai bean đều là ứng viên type `PaymentGateway`.
2. Không có `@Qualifier` tại injection point để chọn ứng viên khác.
3. Không có `@Primary` hoặc `@Fallback` làm thay đổi lựa chọn.
4. Tên tham số `bankGateway` được giữ trong class file.
5. Bean `bankGateway` là ứng viên phù hợp và có thể autowire.

Spring có thể chọn bean `bankGateway` theo tên tham số.

Khi đó luồng có thể được hiểu như sau:

```text
CheckoutService(PaymentGateway bankGateway)
                    │
                    ▼
          Required type: PaymentGateway
                    │
             ┌──────┴──────┐
             ▼             ▼
        cardGateway    bankGateway
                            ▲
                            │
                parameter name = bankGateway
                            │
                            ▼
                     Chọn bean này
```

Nếu đổi tham số thành `PaymentGateway gateway`, tên không trùng hai bean. Khi không có tín hiệu khác, Spring không có cơ sở chọn một trong hai và có thể báo `NoUniqueBeanDefinitionException`.

### 3.1. Khi chỉ có một bean cùng type

Nếu container chỉ có `bankGateway`, constructor:

```java
public CheckoutService(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

vẫn inject được dù tên tham số là `gateway` và bean name là `bankGateway`. Spring đã có một ứng viên type duy nhất nên không cần dùng tên tham số để phân biệt.

Do đó, khi kiểm tra lỗi, hãy phân biệt:

- **Một bean phù hợp:** tên tham số không cần trùng bean name.
- **Nhiều bean phù hợp:** tên tham số có thể là một tín hiệu phân giải nếu metadata có sẵn.
- **Không có bean phù hợp:** tên trùng không tạo ra bean mới và không sửa được lỗi thiếu bean.

### 3.2. Tên bean alias cũng có thể được xét

Một bean có thể có alias:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean(name = {"bankGateway", "preferredBankGateway"})
    public PaymentGateway bankPaymentGateway() {
        return new BankPaymentGateway();
    }
}
```

Trong ví dụ, `bankGateway` là tên chính và `preferredBankGateway` là alias của cùng bean. Tên injection point có thể được so khớp với tên bean hoặc alias trong các tình huống name matching được áp dụng.

Alias không tạo ra một instance bean độc lập; chúng là các tên truy cập cùng một bean definition/bean.

## 4. Vì sao tên tham số phải được lưu trong bytecode?

Java compiler không mặc nhiên phải giữ tên tham số nguồn cho Java Reflection trong mọi chế độ biên dịch.

Ví dụ:

```java
public CheckoutService(PaymentGateway bankGateway) {
    this.gateway = bankGateway;
}
```

Tên `bankGateway` xuất hiện trong source code. Nhưng khi biên dịch mà không yêu cầu lưu parameter metadata, reflection có thể chỉ nhìn thấy tên tổng quát như `arg0` và `Parameter.isNamePresent()` trả về `false`.

Spring không thể suy ra một cách đáng tin cậy tên `bankGateway` chỉ từ chữ viết trong file `.java` sau khi source code không còn ở runtime.

### 4.1. Cờ `-parameters`

Java compiler có tùy chọn:

```bash
javac -parameters ...
```

Cờ `-parameters` yêu cầu compiler ghi thông tin tên tham số vào class file để API Java Reflection có thể đọc. Khi đó:

```java
Parameter parameter = constructor.getParameters()[0];

System.out.println(parameter.getName());
System.out.println(parameter.isNamePresent());
```

có thể trả:

```text
bankGateway
true
```

Nếu metadata không được giữ, output thường có dạng:

```text
arg0
false
```

Tên `arg0` là tên tổng quát do Reflection cung cấp khi tên nguồn không được lưu theo cơ chế này. Spring không nên dựa vào nó để tìm bean `bankGateway`.

### 4.2. `-parameters` không phải cờ chạy JVM

Cần đặt `-parameters` ở **giai đoạn biên dịch Java**.

Đúng:

```bash
javac -parameters -d out src/main/java/com/example/CheckoutService.java
```

Không đúng mục đích:

```bash
java -parameters -jar application.jar
```

`java` là launcher chạy ứng dụng; `-parameters` là compiler option của `javac`. Đưa nó vào lệnh chạy JAR không thể bổ sung metadata cho class file đã được biên dịch.

Tương tự, thay đổi cấu hình compiler sau khi JAR đã build không làm JAR cũ tự có tên tham số. Cần biên dịch lại các class liên quan và đóng gói artifact mới.

### 4.3. `MethodParameters` khác `LocalVariableTable`

Trong class file Java có thể có nhiều loại metadata:

- **`MethodParameters`**: thuộc tính chứa tên và cờ của tham số phương thức/constructor; đây là thông tin mà reflection chuẩn có thể sử dụng khi được compiler tạo bằng `-parameters`.
- **`LocalVariableTable`**: debug metadata mô tả các biến cục bộ và vùng hiệu lực của chúng trong bytecode. Một số phiên bản Spring cũ từng phân tích bảng này để suy ra tên tham số.
- **`LineNumberTable`**: ánh xạ bytecode với số dòng nguồn, phục vụ debug.

Không nên nhầm việc build có debug symbols với việc build đã lưu parameter names qua `-parameters`.

Cờ `-g` hoặc việc IDE tạo thông tin debug không thay thế `-parameters` trong các phiên bản Spring đã loại bỏ cơ chế đọc LocalVariableTable.

## 5. Khác biệt theo phiên bản Spring Framework

Đây là phần quan trọng khi ứng dụng trước đây hoạt động nhưng sau nâng cấp lại báo không tìm thấy bean duy nhất.

| Spring Framework | Cách tìm tên tham số | Ý nghĩa đối với ứng dụng |
|---|---|---|
| 6.0 và các phiên bản trước | Có thể dùng `LocalVariableTableParameterNameDiscoverer` để suy ra tên từ debug metadata; `-parameters` cũng cung cấp tên qua reflection | Một số project hoạt động dù chưa bật `-parameters`, miễn bytecode có local-variable debug information phù hợp |
| 6.1 | Đã loại bỏ `LocalVariableTableParameterNameDiscoverer`; dùng tên qua Java Reflection, cần `-parameters` cho Java parameter names | Không nên dựa vào `-g`/debug local variable table; nếu name matching là cần thiết, phải biên dịch với `-parameters` |
| 6.2 | Tiếp tục yêu cầu `-parameters`; thêm fast shortcut cho trường hợp tên parameter khớp bean name và điều kiện khác không ghi đè; điều chỉnh thứ tự phân giải liên quan `@Priority`; bổ sung `@Fallback` | Có thêm cơ chế dự phòng và một số khác biệt về thứ tự chọn bean khi nhiều candidate cùng type |

### 5.1. Spring Framework 6.0 trở về trước

Trong các phiên bản cũ, Spring có thể sử dụng `LocalVariableTableParameterNameDiscoverer` để đọc local variable table từ bytecode. Nếu compiler/IDE tạo debug metadata phù hợp, Spring có thể biết tên tham số dù Java Reflection không báo `isNamePresent()`.

Điều này khiến một số dự án có vẻ như không cần `-parameters`. Tuy nhiên, hành vi phụ thuộc cách compiler tạo debug information, cấu hình build và công cụ đóng gói. Không nên coi đó là một hợp đồng ổn định cho code mới.

`-parameters` đã có từ Java 8 và vẫn là cách rõ ràng để giữ tên cho reflection.

### 5.2. Spring Framework 6.1

Từ 6.1, `LocalVariableTableParameterNameDiscoverer` bị loại bỏ. Spring và các project trong hệ sinh thái không còn cố phân tích bytecode để suy luận tên tham số từ debug information.

Nếu dependency resolution cần tên parameter, hãy bật `-parameters`. Điều này có thể ảnh hưởng đến:

- Constructor injection và method injection khi cần name matching.
- Property binding hoặc các tính năng dùng tên tham số.
- SpEL hoặc các framework tích hợp dựa trên parameter names.
- Những cơ chế khác trong Spring ecosystem cần truy cập tên tham số runtime.

Nếu ứng dụng từng chạy nhờ local-variable debug metadata, sau nâng cấp lên 6.1 có thể xuất hiện `NoUniqueBeanDefinitionException` vì Spring không còn biết tham số tên `bankGateway` để chọn bean cùng tên.

**Debug symbols vẫn có thể hữu ích cho debugging**, nhưng không còn là phương án thay thế cho parameter metadata cần thiết trong Spring 6.1+.

### 5.3. Spring Framework 6.2

Spring 6.2 vẫn cần `-parameters` cho Java parameter-name matching. Nó bổ sung một đường xử lý nhanh khi tên parameter trùng bean name và không có điều kiện type/qualifier/primary/fallback khác cần ưu tiên.

6.2 cũng điều chỉnh thuật toán autowiring: trong tập candidate cùng type, việc khớp tên tham số và việc `@Qualifier` khớp với target bean name có thể được xét trước xếp hạng `@Priority`; ở các phiên bản trước, priority được kiểm tra trước các tín hiệu đó. **`@Primary` vẫn luôn được ưu tiên.**

Ngoài ra, Spring Framework 6.2 giới thiệu `@Fallback` để đánh dấu bean dự phòng. Khi nhiều bean cùng type và tất cả trừ một bean được đánh dấu fallback, bean không fallback được chọn cho dependency đơn lẻ.

Những thay đổi này không làm `-parameters` trở nên tùy chọn. Nếu tên parameter không có trong metadata, Spring vẫn không thể dùng tên nguồn để match theo quy tắc đó.

### 5.4. Spring Boot liên hệ với Spring Framework version

Spring Boot quản lý một tập phiên bản Spring Framework tương thích qua dependency management. Các dòng phiên bản phổ biến:

| Spring Boot | Dòng Spring Framework được quản lý |
|---|---|
| 3.1.x | 6.0.x |
| 3.2.x | 6.1.x |
| 3.3.x | 6.1.x |
| 3.4.x | 6.2.x |

Bảng này chỉ chỉ ra dòng tương ứng ở mức tổng quát. Phiên bản patch cụ thể thay đổi theo bản Spring Boot phát hành và dependency management đang dùng. Nếu dự án override Spring Framework hoặc dùng BOM khác, kết quả thực tế có thể khác.

Vì vậy, khi đọc lỗi name matching, hãy xác định **Spring Framework thực sự được resolve**, không chỉ nhìn một dòng version được nhớ từ tài liệu cũ.

## 6. Cấu hình Gradle để giữ tên tham số

Với Gradle Groovy DSL, thêm cấu hình cho các task compile Java:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
```

Nếu dùng Gradle Kotlin DSL:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
```

Cấu hình này yêu cầu các task `JavaCompile` áp dụng compiler option `-parameters`.

### 6.1. Cấu hình tại đúng project/module

Trong Gradle multi-project, đặt cấu hình ở root có thể áp dụng cho mọi subproject nếu được viết theo cách cấu hình đúng phạm vi. Nếu chỉ áp dụng cho một module, hãy đặt vào `build.gradle` của module đó.

Ví dụ áp dụng từ root:

```groovy
subprojects {
    tasks.withType(JavaCompile).configureEach {
        options.compilerArgs.add("-parameters")
    }
}
```

Không thêm nhiều cấu hình trùng lặp ở cả root và module nếu không cần thiết. Hãy kiểm tra task compile thực tế của module có nhận option này.

Nếu module có mã Java được build bằng một task compiler riêng hoặc một plugin tùy chỉnh, cần bảo đảm task đó cũng nhận `-parameters`.

### 6.2. Không chỉ build application module

Tên tham số cần được lưu trong class file **chứa injection point**.

Ví dụ, nếu constructor của `CheckoutService` nằm trong module ứng dụng, task compile của module đó phải bật `-parameters`. Nếu một thư viện bên ngoài chứa injection point và được biên dịch độc lập, cờ phải được bật khi biên dịch thư viện ấy; module ứng dụng không thể sửa metadata của class đã biên dịch chỉ bằng cách thêm flag cho chính mình.

Nếu một module có `@Bean` factory method nhận dependency qua parameter name, cũng cần xem task compile tạo ra class chứa factory method đó.

### 6.3. Build lại class file cũ

Sau khi thêm option, hãy biên dịch lại để class file mới có metadata:

```bash
./gradlew clean compileJava
```

Hoặc build artifact:

```bash
./gradlew clean bootJar
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat clean compileJava
.\gradlew.bat clean bootJar
```

`clean` giúp loại bỏ output cũ có thể được tạo bằng compiler options trước đó. Nó không thay đổi source code và không phải bước bắt buộc trong mọi build thường ngày; ở đây nó hữu ích khi xác nhận thay đổi metadata biên dịch.

## 7. Cấu hình Maven để giữ tên tham số

Với Maven Compiler Plugin, cấu hình:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Thuộc tính `parameters` yêu cầu compiler ghi tên tham số để reflection truy cập được.

Sau đó biên dịch lại:

```bash
./mvnw clean compile
```

Hoặc đóng gói:

```bash
./mvnw clean package
```

Nếu dùng Maven parent hoặc BOM của Spring Boot, hãy kiểm tra cấu hình compiler được kế thừa và effective POM trước khi thêm plugin block. Có thể cấu hình đã được đặt ở cấp parent; điều quan trọng là **task compiler thực sự tạo class file của injection point có nhận `-parameters` hay không**.

## 8. Cấu hình IDE và sự khác nhau giữa Run trong IDE với JAR

Một nguyên nhân gây lỗi khó hiểu là hai cách chạy sử dụng hai bộ compiler options khác nhau:

```text
Run trong IDE
   │
   └── IDE compiler / build delegation
           └── có thể bật -parameters

Gradle/Maven build JAR
   │
   └── build tool compiler
           └── có thể chưa bật -parameters
```

Nếu IDE compile class với parameter names nhưng Gradle/Maven đóng gói class khác không có metadata, hành vi có thể thay đổi giữa hai cách chạy. Trường hợp ngược lại cũng có thể xảy ra.

### 8.1. IntelliJ IDEA

Nếu IDE ủy quyền build và run cho Gradle/Maven, cấu hình compiler option ở build tool là trọng tâm.

Nếu dùng IntelliJ compiler trực tiếp, có thể cấu hình Java compiler để truyền `-parameters` trong phần **Additional command line parameters** của Java Compiler settings. Tên và vị trí menu có thể thay đổi theo phiên bản IDE.

### 8.2. Eclipse

Eclipse có tùy chọn lưu method parameter names trong phần Java Compiler. Bật tùy chọn tương ứng để compiler tạo metadata có thể dùng qua reflection.

### 8.3. Kotlin và Groovy

Với Kotlin compiler, Spring Framework khuyến nghị cờ `-java-parameters` khi cần lưu Java parameter names theo cơ chế reflection.

Với Groovy compiler, có tùy chọn `-parameters` tương ứng. Cấu hình phải áp dụng cho task compile Groovy nếu injection point được khai báo trong source Groovy.

### 8.4. Quy tắc thực tế

- Cấu hình compiler tại nơi **thực sự biên dịch source code**.
- Nếu IDE delegate build sang Gradle/Maven, tránh cấu hình hai bộ option khác nhau.
- Sau khi đổi option, build lại class và JAR.
- Kiểm tra class file trong output hoặc trong artifact, không chỉ xem checkbox trong IDE.
- Không thêm `-parameters` vào lệnh `java -jar` vì đó không phải compiler option.

## 9. Kiểm tra parameter metadata trong class file

Khi gặp lỗi do Spring không match tên tham số, hãy xác nhận metadata trước khi thay đổi bean configuration.

### 9.1. Kiểm tra bằng Java Reflection

Ví dụ:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class ParameterMetadataInspector {

    public static void main(String[] args) throws Exception {
        Constructor<CheckoutService> constructor =
                CheckoutService.class.getDeclaredConstructor(
                        PaymentGateway.class
                );

        Parameter parameter = constructor.getParameters()[0];

        System.out.println("Name: " + parameter.getName());
        System.out.println("Present: " + parameter.isNamePresent());
    }
}
```

Nếu được compile với `-parameters`, kết quả mong đợi:

```text
Name: bankGateway
Present: true
```

Nếu output là `arg0` và `false`, tên nguồn không có trong metadata reflection. Khi đó, không thể dựa vào parameter-name fallback của Spring 6.1+.

Đây là một kiểm tra kỹ thuật nhỏ, có thể chạy trong một test hoặc chương trình chẩn đoán. Nó không kiểm tra toàn bộ thuật toán chọn bean; nó chỉ xác nhận thông tin tên mà reflection nhìn thấy.

### 9.2. Kiểm tra bằng `javap`

Sau khi compile, dùng:

```bash
javap -v -p build/classes/java/main/com/example/shop/CheckoutService.class
```

Tìm thuộc tính:

```text
MethodParameters:
  Name
  bankGateway
```

Đường dẫn class file thay đổi theo project và build tool. Với Gradle, output Java main thường nằm dưới `build/classes/java/main`; với Maven, thường là `target/classes`.

Nếu class file không có `MethodParameters`, hãy kiểm tra compiler command/configuration. Sự hiện diện của `LineNumberTable` hoặc `LocalVariableTable` không chứng minh rằng `-parameters` đã được bật.

## 10. `@Qualifier`, tên tham số và `@Resource` khác nhau thế nào?

Cả ba có thể giúp xác định bean, nhưng semantics không giống nhau.

### 10.1. `@Qualifier`: lọc các ứng viên theo type

Ví dụ:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("bankGateway") PaymentGateway gateway
    ) {
        this.gateway = gateway;
    }
}
```

`@Qualifier("bankGateway")` chỉ rõ qualifier cần dùng ở injection point. Spring vẫn xét tập ứng viên theo type, rồi sử dụng qualifier để thu hẹp tập đó.

Qualifier không bắt buộc phải là bean name; nó có thể là nhãn ngữ nghĩa riêng được gắn lên bean. Nếu dùng bean name làm qualifier value, Spring có thể match với tên bean theo quy tắc fallback tương ứng.

Đây là lựa chọn rõ ràng khi nghiệp vụ thực sự yêu cầu một implementation cụ thể.

### 10.2. Tên tham số: fallback theo quy ước

Ví dụ:

```java
public CheckoutService(PaymentGateway bankGateway) {
    this.gateway = bankGateway;
}
```

Không có `@Qualifier`, nên tên tham số có thể được dùng làm tín hiệu dự phòng khi nhiều bean cùng type. Cách này ngắn nhưng phụ thuộc metadata compiler và tên bean.

Nếu ai đó đổi tên tham số từ `bankGateway` thành `gateway` mà không đổi bean name, hành vi lựa chọn có thể thay đổi sau khi biên dịch lại. Vì vậy, không nên coi tên tham số là hợp đồng cấu hình mạnh nếu lựa chọn bean quan trọng với nghiệp vụ.

### 10.3. `@Resource(name = "...")`: nhận diện theo tên

Ví dụ với field:

```java
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    @Resource(name = "bankGateway")
    private PaymentGateway gateway;
}
```

`@Resource` theo semantics của Jakarta là cơ chế nhận diện target theo **tên**. Kiểu khai báo vẫn phải tương thích với đối tượng được inject, nhưng việc tìm target bắt đầu từ tên được chỉ định.

Trong Spring, `@Resource` thường dùng trên field hoặc setter một tham số; nó không phải lựa chọn cho constructor parameter như `@Qualifier`. Với Spring Boot 3.x, package annotation là `jakarta.annotation.Resource`.

### 10.4. Bảng chọn cách viết

| Cách | Tín hiệu chính | Có phụ thuộc `-parameters`? | Khi nào phù hợp? |
|---|---|---|---|
| `@Autowired` theo type, một candidate | Type | Không | Chỉ có một bean phù hợp |
| `@Autowired` với parameter-name fallback | Type rồi tên parameter/bean | Có với Java parameters trên Spring 6.1+ | Quy ước tên đơn giản, đã kiểm soát metadata |
| `@Qualifier` trên constructor parameter | Type + qualifier | Không cần tên parameter để chọn qualifier | Cần lựa chọn rõ ràng ở một injection point |
| `@Primary` | Type + ứng viên primary | Không | Có một bean mặc định cho nhiều injection point |
| `@Resource(name = "...")` | Bean name | Không | Cần tra cứu một bean theo tên trên field/setter |
| `List<T>` / `Map<String, T>` | Tập bean theo type | Không | Muốn nhận nhiều implementation |

Với constructor injection, `@Qualifier` thường là lựa chọn rõ ràng và ổn định khi cần chọn một bean cụ thể.

## 11. Các annotation ưu tiên và khác biệt ở Spring 6.2

### 11.1. `@Primary`

`@Primary` đánh dấu bean ưu tiên khi nhiều bean cùng type phù hợp với một injection point đơn lẻ:

```java
@Primary
@Component("cardGateway")
public class CardPaymentGateway implements PaymentGateway {
    // ...
}
```

Nếu constructor parameter tên `bankGateway` nhưng `cardGateway` được đánh dấu `@Primary`, Spring ưu tiên bean primary theo quy tắc của container. Không nên giả định tên tham số luôn thắng mọi chỉ dẫn khác.

`@Primary` không loại bỏ các bean còn lại khỏi container; injection dạng collection vẫn có thể nhận tất cả ứng viên phù hợp.

### 11.2. `@Priority`

`@Priority` thuộc Jakarta Annotations:

```java
import jakarta.annotation.Priority;
import org.springframework.stereotype.Component;

@Priority(10)
@Component("cardGateway")
public class CardPaymentGateway implements PaymentGateway {
    // ...
}
```

Với priority dạng số, giá trị thấp hơn biểu thị mức ưu tiên cao hơn theo quy tắc tương ứng của Spring's order comparator.

Spring Framework 6.1 và 6.2 có thay đổi về thứ tự giữa priority ranking với parameter-name / qualifier-name matching. Nếu ứng dụng dựa đồng thời vào các cơ chế này, kết quả có thể khác khi nâng cấp.

Không nên trộn nhiều tín hiệu lựa chọn chỉ để dựa vào thứ tự nội bộ. Hãy dùng `@Qualifier` hoặc một cấu hình rõ ràng khi điểm injection phải nhận đúng một implementation.

### 11.3. `@Fallback` từ Spring Framework 6.2

`@Fallback` được giới thiệu trong Spring Framework 6.2:

```java
import org.springframework.context.annotation.Fallback;
import org.springframework.stereotype.Component;

@Fallback
@Component("defaultGateway")
public class DefaultPaymentGateway implements PaymentGateway {
    // ...
}
```

Ý tưởng: cung cấp một implementation mặc định để ứng dụng có thể thay thế bằng bean riêng mà không phải đánh dấu bean mới là `@Primary`.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    @Fallback
    public PaymentGateway defaultGateway() {
        return new DefaultPaymentGateway();
    }
}
```

Nếu chỉ có bean fallback phù hợp, bean đó vẫn có thể được inject. Nếu có nhiều ứng viên và tất cả trừ một bean được đánh dấu fallback, bean không fallback được chọn. Nếu còn nhiều ứng viên không fallback, cần thêm chỉ dẫn để phân giải.

`@Fallback` có ý nghĩa với dependency đơn lẻ; nó không loại bỏ fallback beans khỏi mảng, collection, map hoặc stream ứng viên.

**Spring Framework 6.1 không có `@Fallback`.** Không import annotation này trong project vẫn đang dùng Framework 6.1.

### 11.4. `@Order` không phải cách thay thế chung cho `@Qualifier`

`@Order` thường được dùng để sắp thứ tự các bean trong collection injection, chẳng hạn `List<PaymentGateway>`. Nó không có nghĩa “hãy luôn inject bean có số order nhỏ nhất” trong mọi constructor nhận một bean đơn lẻ.

Thứ tự khởi tạo singleton cũng là một mối quan tâm khác, chủ yếu dựa trên quan hệ dependency và `@DependsOn`. Không dùng `@Order` như một cách đổi tên bean hoặc thay thế qualifier.

## 12. Khác biệt về thuật toán autowiring giữa 6.1 và 6.2

Một ví dụ giúp hiểu tại sao version có thể ảnh hưởng kết quả:

```java
@Component("cardGateway")
@Priority(1)
public class CardPaymentGateway implements PaymentGateway {
    // ...
}

@Component("bankGateway")
@Priority(5)
public class BankPaymentGateway implements PaymentGateway {
    // ...
}
```

Injection point:

```java
public CheckoutService(PaymentGateway bankGateway) {
    this.gateway = bankGateway;
}
```

Giả sử tên `bankGateway` có metadata và cả hai bean đều phù hợp type. Có hai tín hiệu cạnh tranh:

- `cardGateway` có priority cao hơn (số nhỏ hơn).
- `bankGateway` có tên trùng parameter.

Theo hướng thay đổi được ghi trong Spring Framework 6.2 release notes, parameter-name matches và `@Qualifier` matches với target bean name được ưu tiên hơn `@Priority` ranking; trước đó priority được kiểm tra trước các tín hiệu này. `@Primary` vẫn đứng trước.

Ví dụ này nhằm minh họa **sự khác biệt version**, không phải khuyến nghị dựa vào nhiều annotation cạnh tranh. Nếu yêu cầu nghiệp vụ là chọn bank gateway, viết rõ:

```java
public CheckoutService(
        @Qualifier("bankGateway") PaymentGateway gateway
) {
    this.gateway = gateway;
}
```

Khi đó ý định được biểu đạt trực tiếp ở injection point và không cần phụ thuộc vào tên tham số hoặc thứ tự priority.

### 12.1. Fast shortcut trong Spring Framework 6.2

Framework 6.2 tối ưu trường hợp tên tham số khớp bean name bằng một fast shortcut, khi không có điều kiện type, qualifier, primary hoặc fallback khác cần override lựa chọn. Điều này giúp container tránh một phần quy trình tìm kiếm ứng viên đầy đủ trong những trường hợp phù hợp.

Đây là tối ưu của container. Không nên thiết kế code dựa trên giả định rằng tên tham số luôn có thể thay thế type safety, qualifier hoặc điều kiện đăng ký bean.

### 12.2. Khi nâng cấp, hãy xem lại những dependency dựa vào tên

Nếu một project trước đây dùng tên tham số như một cách chọn bean ngầm, hãy ghi nhận các điểm injection dạng:

```java
SomeService(SomeInterface someBeanName)
```

Sau đó kiểm tra:

- Tên bean thực tế có còn là `someBeanName` không?
- Tên tham số có được lưu trong bytecode không?
- Có `@Primary`, `@Qualifier`, `@Fallback` hoặc `@Priority` ảnh hưởng kết quả không?
- Framework version mới có thay đổi thứ tự lựa chọn không?
- Có thể chuyển sang `@Qualifier` để thể hiện lựa chọn rõ ràng hơn không?

Đừng kết luận lỗi nâng cấp là do compiler nếu chưa kiểm tra dependency candidates; cũng đừng đổi qualifier nếu vấn đề thực tế là class file không có parameter metadata.

## 13. Kiểm tra Spring Framework version thực tế trong dự án

Spring Boot dependency management thường chọn phiên bản Spring Framework tương ứng. Khi cần điều tra, xem dependency tree của module thực sự chạy ứng dụng.

Gradle:

```bash
./gradlew dependencyInsight \
    --dependency spring-beans \
    --configuration runtimeClasspath
```

Hoặc:

```bash
./gradlew dependencyInsight \
    --dependency spring-context \
    --configuration runtimeClasspath
```

Maven:

```bash
./mvnw dependency:tree \
    -Dincludes=org.springframework:spring-beans,org.springframework:spring-context
```

Các dependency quan trọng ở đây gồm `spring-beans` (nơi có phần lớn core bean resolution) và `spring-context`. Cần xem **phiên bản đã được resolve**, không chỉ nhìn version được khai báo trong một dependency block.

Nếu project sử dụng Spring Boot BOM/parent, ưu tiên để dependency management chọn một bộ phiên bản tương thích. Override riêng một số module Spring Framework có thể tạo ra tổ hợp không đồng nhất.

### 13.1. Xem version theo Spring Boot line

Một số mốc thường gặp:

- Spring Boot 3.2 và 3.3 quản lý Spring Framework 6.1.
- Spring Boot 3.4 quản lý Spring Framework 6.2.

Patch version cụ thể thay đổi theo từng bản Boot. Ví dụ, tài liệu system requirements của Boot 3.3 yêu cầu Framework 6.1.x tương ứng; Boot 3.4 yêu cầu Framework 6.2.x tương ứng.

Nếu ứng dụng có BOM tùy chỉnh hoặc dependency override, hãy tin vào output của dependency tree hơn là suy luận từ tên version Boot.

## 14. Chẩn đoán lỗi khi tên tham số không được nhận diện

Giả sử trước nâng cấp, ứng dụng chạy với hai bean cùng type. Sau khi lên Spring Framework 6.1, startup báo:

```text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'PaymentGateway' available:
expected single matching bean but found 2
```

Có thể tên tham số trước đây đã được suy ra từ local-variable debug table, nhưng class file mới không có `MethodParameters`.

### 14.1. Các dấu hiệu cần kiểm tra

| Dấu hiệu | Điều cần xem |
|---|---|
| Chỉ lỗi khi có hai bean cùng type | Name fallback có thể từng phân giải ứng viên |
| Parameter reflection trả `arg0` | Class file không giữ tên tham số qua reflection |
| `Parameter.isNamePresent()` trả `false` | `-parameters` không được áp dụng cho class đó |
| IDE chạy nhưng JAR lỗi | IDE và build tool có thể compile với options khác nhau |
| Chỉ lỗi sau nâng cấp 6.1 | Có thể project từng dựa vào LVT debug parameter discovery |
| Kết quả thay đổi sau nâng cấp 6.2 | Kiểm tra name match, `@Qualifier`, `@Priority` và `@Fallback` |

### 14.2. Quy trình xử lý

1. **Xác định injection point**: constructor hay method nào đang nhận type có nhiều bean?
2. **Liệt kê ứng viên**: tên bean, type, qualifier, primary/fallback/priority.
3. **Xem tên tham số runtime** bằng reflection hoặc `javap`.
4. **Xác định Framework version** đã được resolve.
5. Nếu cần parameter-name fallback, bật `-parameters` cho task compile đúng module và build lại.
6. Nếu lựa chọn bean có ý nghĩa nghiệp vụ, cân nhắc `@Qualifier` để code thể hiện ý định rõ ràng.
7. Chạy lại đúng luồng build/khởi động và xác nhận bean được inject là bean mong muốn.

Không sửa bằng cách bật bean definition overriding. Cơ chế đó xử lý xung đột tên bean khi đăng ký, không giải quyết việc nhiều bean khác tên cùng type.

### 14.3. Không nhầm với lỗi thiếu bean

Ba thông báo có ý nghĩa khác nhau:

| Thông báo | Ý nghĩa |
|---|---|
| `NoSuchBeanDefinitionException` | Không có bean phù hợp |
| `NoUniqueBeanDefinitionException` | Có nhiều bean phù hợp nhưng không xác định được một bean |
| `BeanDefinitionOverrideException` | Nhiều định nghĩa cố đăng ký cùng một bean name trong registry không cho phép ghi đè |

Parameter-name fallback chủ yếu giúp giải quyết trường hợp thứ hai. Nó không tự tạo bean và không giải quyết trường hợp thứ ba.

## 15. Các trường hợp đặc biệt cần lưu ý

### 15.1. Field name và parameter name

Spring có thể dùng tên của injection point, chẳng hạn field name hoặc parameter name, trong cơ chế name matching.

Ví dụ field:

```java
@Autowired
private PaymentGateway bankGateway;
```

Field name có thể được đọc từ class metadata mà không cần `-parameters`. Nhưng constructor parameter:

```java
public CheckoutService(PaymentGateway bankGateway) {
    this.gateway = bankGateway;
}
```

cần parameter-name metadata từ compiler khi dùng Spring 6.1+.

Đây là một lý do field injection có thể có biểu hiện khác constructor injection trong cùng project. Tuy nhiên, constructor injection vẫn thường được ưu tiên vì dependency rõ ràng, object có thể bất biến và dễ test.

### 15.2. `@Bean` method parameters cũng là injection points

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class CheckoutConfiguration {

    @Bean
    public CheckoutService checkoutService(
            PaymentGateway bankGateway
    ) {
        return new CheckoutService(bankGateway);
    }
}
```

Spring cần resolve tham số `bankGateway` khi gọi factory method `checkoutService`. Quy tắc qualifier, type và parameter name cũng có liên quan tại điểm injection này.

Vì vậy, nếu `@Bean` method được dùng để chọn giữa nhiều bean cùng type bằng tên tham số, class chứa configuration method cũng cần được biên dịch với metadata phù hợp.

### 15.3. Tên tham số trong thư viện bên ngoài

Nếu injection point nằm trong một thư viện đã biên dịch, ứng dụng không thể tự thêm parameter metadata cho class đó chỉ bằng cách bật `-parameters` ở project tiêu thụ.

Bạn cần một trong các hướng:

- Dùng phiên bản thư viện được biên dịch và phát hành với parameter metadata.
- Nâng cấp hoặc rebuild thư viện nếu bạn quản lý source của nó.
- Dùng cấu hình/extension point khác để cung cấp dependency.
- Nếu injection point thuộc code của bạn, dùng `@Qualifier` rõ ràng để tránh phụ thuộc vào tên parameter.

### 15.4. Constructor có nhiều overload

Tên tham số chỉ được xét sau khi Spring đã xác định constructor hoặc method nào cần dùng để inject. Nó **không phải cơ chế chọn overload constructor**.

Với class có nhiều constructor, hãy khai báo rõ constructor autowiring theo quy tắc Spring phù hợp, hoặc thiết kế constructor đơn giản. Sau đó mới xét metadata của các parameter tại constructor được chọn.

### 15.5. Generic types có thể giảm số ứng viên

Spring có thể dùng generic type information khi tìm bean. Ví dụ `Handler<String>` và `Handler<Integer>` có thể được phân biệt theo generic signature nếu thông tin kiểu được giữ đầy đủ trong bean definition và injection point.

Đây là một cơ chế lọc theo type, khác với parameter-name fallback. Không nên thêm tên tham số chỉ để bù cho một generic signature khai báo sai hoặc quá rộng.

## 16. Quy ước nên dùng trong dự án

Một số nguyên tắc giúp code ổn định qua nâng cấp:

1. **Bật `-parameters`** trong compiler configuration của các module Java có Spring injection points, đặc biệt khi dùng Spring Framework 6.1+.
2. **Dùng `@Qualifier`** cho những lựa chọn bean có ý nghĩa nghiệp vụ và cần đọc được ngay trong code.
3. Dùng tên tham số trùng bean name như một fallback tiện lợi khi quy ước đặt tên đơn giản và đã được kiểm soát.
4. Không dựa vào `-g` hoặc local-variable debug table để bảo đảm parameter names.
5. Không coi `@Primary`, `@Priority`, `@Fallback` và `@Order` là các annotation thay thế lẫn nhau.
6. Khi nâng cấp Spring, kiểm tra release notes và dependency version thực tế trước khi kết luận thuật toán chọn bean không đổi.
7. Build lại class file và JAR sau khi đổi compiler option; class file cũ không tự được bổ sung metadata.
8. Giữ cấu hình compile của IDE và Gradle/Maven đồng nhất nếu cả hai đều được dùng để chạy ứng dụng.

### 16.1. Mẫu code rõ ràng cho lựa chọn quan trọng

Nếu checkout bắt buộc dùng gateway ngân hàng, cách thể hiện rõ:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("bankGateway") PaymentGateway gateway
    ) {
        this.gateway = gateway;
    }
}
```

Nếu một service có thể sử dụng bất kỳ gateway nào và chỉ có một bean phù hợp trong từng môi trường, constructor theo type là đủ:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Nếu nhiều gateway được cố ý sử dụng đồng thời, nhận collection:

```java
@Service
public class PaymentRouter {

    private final Map<String, PaymentGateway> gateways;

    public PaymentRouter(Map<String, PaymentGateway> gateways) {
        this.gateways = gateways;
    }
}
```

Đừng dùng tên parameter để che giấu một yêu cầu lựa chọn chưa được mô tả rõ.

## 17. Bài thực hành

### Bài 1 — Quan sát tên tham số qua reflection

Tạo constructor:

```java
public CheckoutService(PaymentGateway bankGateway) {
    this.gateway = bankGateway;
}
```

Biên dịch một lần không có `-parameters` và một lần có `-parameters`. Dùng `Parameter.getName()` và `Parameter.isNamePresent()` để so sánh. Quan sát rằng source code không đổi nhưng metadata class file khác nhau.

### Bài 2 — Hai bean cùng type, parameter name khớp

Đăng ký `cardGateway` và `bankGateway`. Đặt constructor parameter là `bankGateway`. Bật `-parameters` và chạy ứng dụng bằng Spring Framework 6.1+. Quan sát name fallback.

Sau đó đổi parameter thành `gateway`, biên dịch lại và xem kết quả. Nếu không có `@Primary` hoặc `@Qualifier`, hai candidate có thể khiến Spring báo nhập nhằng.

### Bài 3 — Thử explicit qualifier

Giữ parameter tên `gateway` nhưng thêm:

```java
@Qualifier("bankGateway")
```

Chạy lại khi không bật `-parameters`. Qualifier được lưu như annotation metadata trên injection point và không cần tên parameter để lựa chọn bean theo qualifier đó.

### Bài 4 — So sánh 6.0 với 6.1

Dùng cùng một project và cùng một cấu hình bean. Kiểm tra một build cũ có local-variable debug information nhưng không có `-parameters`, rồi so sánh với Framework 6.1+. Mục đích là hiểu vì sao project cũ có thể từng chạy nhờ LVT discovery và vì sao cơ chế đó không còn sau nâng cấp.

Không nên giữ cấu hình debug cũ làm giải pháp lâu dài; bật `-parameters` là cách được Spring khuyến nghị.

### Bài 5 — Quan sát 6.2

Với project chạy Spring Framework 6.2, tạo hai bean cùng type và thử các tín hiệu `@Primary`, `@Priority`, parameter-name matching và `@Qualifier`. Sau đó thử `@Fallback` trên một bean mặc định.

Ghi nhận khác biệt khi đổi Framework version và giải thích tại sao `@Qualifier` rõ ràng hơn việc để nhiều tín hiệu ưu tiên cạnh tranh.

### Bài 6 — So sánh IDE và JAR

Build và chạy ứng dụng từ IDE, sau đó build JAR bằng Gradle/Maven và chạy `java -jar`. Dùng reflection hoặc `javap` để xác nhận class file trong hai output có `MethodParameters`. Nếu hành vi khác nhau, so sánh compiler options của hai luồng build.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html): quy tắc type matching, qualifier, parameter-name fallback, `-parameters` và fast shortcut từ 6.2.
- [Spring Framework 6.1 Release Notes — Parameter Name Retention](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes): việc loại bỏ `LocalVariableTableParameterNameDiscoverer` và cấu hình compiler.
- [Spring Framework 6.2 Release Notes — Core Container](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes): thay đổi autowiring algorithm, priority ranking và `@Fallback`.
- [Spring Boot 3.3 System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): dòng Spring Framework 6.1 tương thích.
- [Spring Boot 3.4 System Requirements](https://docs.spring.io/spring-boot/3.4/system-requirements.html): dòng Spring Framework 6.2 tương thích.

Tên tham số có thể giúp Spring chọn đúng bean khi nhiều ứng viên cùng type, nhưng nó chỉ hoạt động khi tên tồn tại trong metadata runtime và quy tắc ưu tiên của phiên bản cho phép dùng tín hiệu đó. Với Java và Spring Framework 6.1+, hãy biên dịch bằng `-parameters`. Khi việc chọn bean quan trọng với nghiệp vụ, hãy biểu đạt lựa chọn bằng `@Qualifier` để ý định không phụ thuộc vào tên tham số hoặc thay đổi thuật toán giữa các phiên bản.
