# Tạo sản phẩm qua FactoryBean.getObject trong Spring Framework Core Container

## 1. FactoryBean là gì và tại sao tồn tại?

Thông thường, Spring IoC Container tạo một bean từ constructor hoặc một method `@Bean`; đối tượng trả về chính là bean mà ứng dụng sử dụng. Với một số dependency khó khởi tạo — client SDK, proxy, adapter, object cần cấu hình nhiều bước, hoặc instance phải tạo theo một quy tắc đặc biệt — Spring cung cấp **`org.springframework.beans.factory.FactoryBean<T>`**.

`FactoryBean<T>` là **một bean đóng vai trò factory**. Khi container được yêu cầu lấy bean thông thường theo tên của factory, Spring không trả factory ngay, mà gọi **`getObject()` để lấy *sản phẩm* mà factory tạo ra**. Đây là extension point của cơ chế bean creation, không phải giao diện `BeanFactory`.

Ví dụ trực quan:

```text
                       ApplicationContext
                               |
                        bean name: "formatter"
                               |
                       FormatterFactory
                    implements FactoryBean<Formatter>
                       /                  \
                      /                    \
getBean("formatter")                     getBean("&formatter")
        |                                       |
        v                                       v
 container sử dụng getObject()           bản thân FormatterFactory
        |
        v
  Formatter (PRODUCT)
```

Hai danh tính cần phân biệt:

- **Factory bean**: đối tượng `FormatterFactory` do Spring tạo, inject và quản lý theo bean definition của nó.
- **Product**: đối tượng `Formatter` mà `getObject()` cung cấp cho các consumer.

Đây là lý do người học thấy `@Bean` trả về một `FactoryBean` nhưng khi gọi `context.getBean("formatter")` lại nhận đối tượng kiểu `Formatter`, không phải `FormatterFactory`.

Điều quan trọng: `FactoryBean` là một **API của Spring**, khác mẫu thiết kế *Factory Method* trong Java thuần. Nếu chỉ có logic tạo object đơn giản, một method `@Bean` trả trực tiếp product thường dễ hiểu và đủ dùng; không phải lúc nào cũng cần viết `FactoryBean`.

## 2. Ba method cốt lõi của FactoryBean<T>

Trong Spring Framework 6.x/7.x, interface có ba method quan trọng (dưới đây là **chữ ký giản lược**, không phải source cần chép lại):

```java
package org.springframework.beans.factory;

public interface FactoryBean<T> {
    T getObject() throws Exception;

    Class<?> getObjectType();

    default boolean isSingleton() {
        return true;
    }
}
```

Bảng ý nghĩa:

| Method | Hợp đồng | Lưu ý thiết kế |
| --- | --- | --- |
| `T getObject()` | Cung cấp một product instance, có thể shared hoặc độc lập tùy factory | Có thể ném `Exception`, được container gọi khi cần product |
| `Class<?> getObjectType()` | Khai báo kiểu product; có thể trả `null` nếu chưa biết | Nên trả type ổn định **mà không tạo product** |
| `boolean isSingleton()` | Thông báo factory có cung cấp **cùng một object reference** ổn định hay không | Mặc định `true`; không được khai báo true nếu thực chất trả object khác nhau |

### 2.1. getObject(): nơi tạo hoặc lấy sản phẩm

`getObject()` có thể thực hiện quy trình: validate config → xây cấu trúc → khởi tạo SDK → trang bị proxy → trả product. Khi container nhận request `getBean("name")`, nó sử dụng cơ chế FactoryBean để lấy product từ method này (hoặc lấy product singleton đã được cache).

```java
@Override
public Client getObject() throws Exception {
    Client client = Client.builder()
            .endpoint(endpoint)
            .credentials(credentials)
            .build();
    client.initialize();
    return client;
}
```

Đây chỉ là **pseudocode Java minh họa**, `Client`/builder/fields là API giả định của SDK khác, không phải thành phần của Spring và không phải ví dụ chạy độc lập. Nó cho thấy chỗ đặt việc tạo product tùy biến.

`getObject()` có thể được gọi **khi product thực sự được yêu cầu**, không nhất thiết ngay khi Spring tạo factory bean. Việc factory singleton được pre-instantiate **không có nghĩa** product luôn được eager-create. Đối với factory thông thường, product thường tạo theo demand; `SmartFactoryBean.isEagerInit()` có thể thay đổi hành vi với những bean phù hợp.

### 2.2. getObjectType(): rất quan trọng cho type discovery

Spring dùng `getObjectType()` khi giải quyết dependency theo type, `getType(name)`, `getBeansOfType(...)` và các thao tác phát hiện kiểu khác.

```java
@Override
public Class<?> getObjectType() {
    return Client.class;
}
```

Đây là fragment minh họa, `Client` phải là type thực tế mà product được công bố. Cần chú ý:
- Có thể được gọi **rất sớm**, trước khi factory được initialize hoàn chỉnh. Không dựa vào field chỉ được thiết lập trong `@PostConstruct` nếu field ấy có thể chưa sẵn sàng.
- Tránh tạo connection, mở file hoặc gọi `getObject()` chỉ để đoán type; type discovery lý tưởng là nhẹ, không side effect.
- Nếu trả `null`, việc tìm bean bằng kiểu product có thể không phát hiện factory tương ứng; Spring có thể bỏ qua bean đó trong autowiring theo type.
- Nên khai báo kiểu đủ cụ thể mà factory luôn trả về; nếu product có proxy, trả kiểu interface hoặc class thực sự có thể được gán.
- Không dùng `getObjectType()` để khởi chạy product; đó là trách nhiệm của `getObject()`.

### 2.3. isSingleton(): semantic của *product*, không phải của factory bean

`isSingleton() == true` có nghĩa factory quảng bá **sản phẩm là một reference có thể chia sẻ/cached**. Spring BeanFactory sở hữu factory singleton có thể cache result từ `getObject()` và trả lại cùng product ở các `getBean` sau.

`isSingleton() == false` nghĩa product không được quảng bá là singleton; Spring có thể gọi `getObject()` mỗi lần product được yêu cầu. Nhưng từ `false` **không suy ra chắc chắn mọi sản phẩm độc lập hoàn toàn**: một factory đặc biệt có thể trả object được share theo scope ngoài hoặc dùng pooling. `SmartFactoryBean.isPrototype()` cung cấp semantics mạnh hơn về các instance độc lập.

Hai lưu ý rất dễ bỏ sót:

1. `FactoryBean` **bản thân nó** thường được khai báo singleton, nhưng **product của nó** có thể không singleton. Hai scope/contract khác nhau.
2. Nếu khai báo `isSingleton() == true`, factory nên luôn trả **cùng một reference khi gọi `getObject()` trực tiếp**. Không viết `return new Product()` mỗi lần rồi chỉ trông chờ container cache để che giấu vi phạm contract, nhất là khi factory bị dùng bên ngoài bean factory.

Ví dụ minh họa sự khác biệt:

```text
FactoryBean "sharedClient":
    factory scope = singleton
    isSingleton() = true
    getObject()   = cùng Client sau khi tạo
    getBean("sharedClient") nhiều lần -> một reference product

FactoryBean "freshClient":
    factory scope = singleton
    isSingleton() = false
    getObject()   = new Client mỗi lần
    getBean("freshClient") nhiều lần -> nhiều reference product

FactoryBean "otherFactory" (prototype):
    factory scope = prototype
    isSingleton() = true
    không mặc định suy rằng mọi lookup dùng chung một factory/product toàn context
```

Trường hợp factory prototype nên được xem xét riêng, vì bản thân factory có thể được tạo mới mỗi lần; không dùng chỉ mỗi `isSingleton()` để suy ra identity toàn ứng dụng khi cấu hình bean factory không phải singleton.

## 3. Container diễn giải tên bean như thế nào?

Ký hiệu đặc biệt **`&`** là `BeanFactory.FACTORY_BEAN_PREFIX`. Nó chỉ cách dereference **factory** thay vì product.

Giả sử bean tên `"parser"` là một `FactoryBean<Parser>`:

```java
Parser p = context.getBean("parser", Parser.class);
FactoryBean<?> f = context.getBean("&parser", FactoryBean.class);
```

Mã fragment giả định `context` là một `ApplicationContext` có bean tên `parser`, `Parser` đã được định nghĩa. Dòng đầu yêu cầu **product**; dòng thứ hai yêu cầu chính **FactoryBean**.

| Lời gọi | Kết quả thông thường |
| --- | --- |
| `getBean("parser")` | Product của `FactoryBean.getObject()` |
| `getBean("&parser")` | Instance factory `FactoryBean` |
| `getBean("parser", Parser.class)` | Product có kiểu `Parser` |
| `getBean("&parser", ParserFactory.class)` | Factory instance có kiểu `ParserFactory` |
| `getType("parser")` | Type sản phẩm từ `getObjectType()` khi xác định được |
| `getType("&parser")` | Type của factory |
| `getBeanNamesForType(Parser.class)` | Có thể liệt kê tên bean của product tương thích với `Parser` |
| `getBeanNamesForType(FactoryBean.class)` | Truy vấn type factory; chi tiết phụ thuộc cấu hình và type discovery |

**Không viết `getBean("parser")` rồi cast sang `ParserFactory`**: tên bình thường trả product, không phải factory. Ngược lại, inject factory ở một service thay vì product sẽ làm thay đổi contract của service và dễ phát sinh lỗi kiểu.

`&` là cú pháp đặc biệt của Spring BeanFactory khi **truy vấn bean theo tên**, không phải phép Java reference, không phải prefix cho đường dẫn resource và không nên nhầm với ngữ nghĩa tham chiếu ở shell hoặc XML entity.

### Truy xuất factory có làm product được tạo không?

Trong trường hợp thông thường, `getBean("&parser")` lấy factory mà không buộc phải gọi `getObject()` để tạo product. Tuy nhiên factory có thể tự làm việc khởi tạo trong constructor/`@PostConstruct`, nên **không** suy rằng thao tác lấy factory tuyệt đối không có side effect. Hãy đo số lần gọi `getObject()` nếu cần xác định product được tạo lúc nào.

## 4. Luồng gọi của Spring khi lấy product

Mô hình hoạt động đơn giản trong một BeanFactory:

```text
context.getBean("parser")
       |
       v
BeanFactory resolve bean definition "parser"
       |
       v
Lấy hoặc tạo instance ParserFactory (factory bean)
       |
       +-- factory đã được initialize theo vòng đời bean
       |
       v
Nhận diện: instance implements FactoryBean<?> ?
       |
       +-- tên bắt đầu bằng "&" -> trả ParserFactory
       |
       +-- tên thường:
                |
                +-- nếu product singleton đã cache -> trả cache
                |
                +-- nếu chưa có / không singleton:
                         +-- factory.getObject()
                         +-- xử lý product theo cơ chế container phù hợp
                         +-- cache nếu product singleton đủ điều kiện
                         +-- trả product cho caller
```

Đây là mô tả ở mức khái niệm, không phải sao chép toàn bộ thuật toán nội bộ của `AbstractBeanFactory`. Thời điểm gọi `getObjectType`, xử lý post-processor, vòng phụ thuộc, `FactoryBean` prototype và early references có thể khác tùy loại bean.

Từ đó có thể quan sát:
- `getBean("parser")` không có nghĩa Java gọi constructor `Parser` ngay ở dòng này; có thể đã được tạo trước hoặc được cache.
- Một factory singleton có thể tồn tại từ startup nhưng product chưa được yêu cầu.
- `BeanPostProcessor` áp dụng cho factory bean như một bean do Spring tạo. Spring cũng có cơ chế post-processing product từ `FactoryBean`, nhưng **đừng giả định product đi qua toàn bộ cùng chuỗi constructor injection, `@PostConstruct` và destroy callbacks như một bean definition thông thường**. Factory thường phải chịu trách nhiệm init/cleanup riêng của product khi cần.
- Khi product là client có tài nguyên cần đóng, cần thiết kế rõ ai sở hữu tài nguyên, thời điểm đóng và có bao nhiêu user dùng chung product.

## 5. Ví dụ hoàn chỉnh Spring Core, Java 17+: singleton và non-singleton product

Mẫu sau **chạy được** với Java 17+, Maven 3.9+ và Spring Framework 6.2.18, không cần Spring Boot, web server hoặc database. Có **hai FactoryBean singleton** quản lý hai sản phẩm khác nhau:
- `sharedParser`: `isSingleton() == true`, product được cache và factory cũng tự bảo đảm luôn trả cùng reference.
- `freshParser`: `isSingleton() == false`, mỗi `getObject()` trong ví dụ tạo một `Parser` khác.

Khi đọc từ context, ta thấy tên bình thường trả `Parser`, tên có `&` trả `ParserFactory` và method `getObjectType` giúp phát hiện type trước lúc tạo product.

### 5.1. Cấu trúc dự án

```text
factorybean-demo/
├── pom.xml
└── src/main/java/edu/example/factorybean/
    ├── Parser.java
    ├── ParserFactory.java
    ├── AppConfig.java
    └── Main.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>factorybean-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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
                <configuration>
                    <mainClass>edu.example.factorybean.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/factorybean/Parser.java**

```java
package edu.example.factorybean;

// Immutable value object để nhận biết từng product.
public record Parser(String mode, int serial) {
    public String describe() {
        return mode + "#" + serial;
    }
}
```

**src/main/java/edu/example/factorybean/ParserFactory.java**

```java
package edu.example.factorybean;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.FactoryBean;

public final class ParserFactory implements FactoryBean<Parser> {
    private final String mode;
    private final boolean singletonProduct;
    private final AtomicInteger counter = new AtomicInteger();
    private Parser shared;

    public ParserFactory(String mode, boolean singletonProduct) {
        this.mode = mode;
        this.singletonProduct = singletonProduct;
    }

    @Override
    public synchronized Parser getObject() {
        if (singletonProduct) {
            if (shared == null) {
                shared = new Parser(mode, counter.incrementAndGet());
            }
            return shared;
        }
        return new Parser(mode, counter.incrementAndGet());
    }

    @Override
    public Class<?> getObjectType() {
        // Không mở resource hay tạo Parser chỉ để xác định type.
        return Parser.class;
    }

    @Override
    public boolean isSingleton() {
        return singletonProduct;
    }

    public int createdCount() {
        return counter.get();
    }
}
```

`ParserFactory` dùng `synchronized getObject()` để đảm bảo, kể cả khi factory được gọi trực tiếp, trường hợp singleton vẫn chỉ tạo một product, không có race. `AtomicInteger` giúp đếm an toàn khi kiểm thử; ví dụ không dùng static counter nên hai factory khác nhau mỗi cái bắt đầu từ 1. Với `isSingleton()==false`, hai lời gọi trả hai `record Parser` có identity khác nhau dù dữ liệu có thể bằng nhau nếu hệ thống sinh cùng giá trị (ở ví dụ serial không trùng trong cùng factory).

**src/main/java/edu/example/factorybean/AppConfig.java**

```java
package edu.example.factorybean;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean("sharedParser")
    public ParserFactory sharedParserFactory() {
        return new ParserFactory("shared", true);
    }

    @Bean("freshParser")
    public ParserFactory freshParserFactory() {
        return new ParserFactory("fresh", false);
    }
}
```

Cả hai method `@Bean` đều trả về `ParserFactory`, nhưng khi ứng dụng hỏi `sharedParser` hoặc `freshParser`, Spring trả **product Parser** chứ không trả factory. `proxyBeanMethods=false` không vô hiệu hóa `FactoryBean`: nó chỉ thay đổi cách Spring xử lý lời gọi giữa các `@Bean` methods trong configuration class.

**src/main/java/edu/example/factorybean/Main.java**

```java
package edu.example.factorybean;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class Main {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println("type via name: "
                    + context.getType("sharedParser").getSimpleName());
            System.out.println("type via &: "
                    + context.getType("&sharedParser").getSimpleName());

            Parser a = context.getBean("sharedParser", Parser.class);
            Parser b = context.getBean("sharedParser", Parser.class);
            ParserFactory sharedFactory =
                    context.getBean("&sharedParser", ParserFactory.class);

            System.out.println("shared same instance: " + (a == b));
            System.out.println("shared serial: " + a.serial());
            System.out.println("shared created: " + sharedFactory.createdCount());
            System.out.println("factory reference same: "
                    + (sharedFactory ==
                       context.getBean("&sharedParser", ParserFactory.class)));

            Parser x = context.getBean("freshParser", Parser.class);
            Parser y = context.getBean("freshParser", Parser.class);
            ParserFactory freshFactory =
                    context.getBean("&freshParser", ParserFactory.class);

            System.out.println("fresh same instance: " + (x == y));
            System.out.println("fresh serials: " + x.serial() + "," + y.serial());
            System.out.println("fresh created: " + freshFactory.createdCount());
        }
    }
}
```

Tại thư mục chứa `pom.xml`, chạy:

```bash
mvn -q compile exec:java
```

**Các dòng stdout do chương trình in, theo thứ tự:**

```text
type via name: Parser
type via &: ParserFactory
shared same instance: true
shared serial: 1
shared created: 1
factory reference same: true
fresh same instance: false
fresh serials: 1,2
fresh created: 2
```

Maven/Spring có thể có logging môi trường khác, nhưng các dòng `System.out.println` ở đây có giá trị xác định theo cấu hình mẫu. Không có singleton khác yêu cầu `Parser` trước những dòng trên. Product thường của `FactoryBean` không được eager-init chỉ vì factory tồn tại; việc gọi `getType(...)` ở đây không tạo product do `getObjectType()` trả `Parser.class` một cách thuần túy.

Vì `sharedParser` quảng bá singleton, container có thể cache product từ lần `getObject()` đầu tiên; `ParserFactory` cũng luôn trả cùng reference nếu gọi trực tiếp. Vì `freshParser` không quảng bá singleton, hai lần `getBean(...)` chuyển tới factory để tạo hai record mới với serial 1 và 2.

**Kiểm thử thú vị:** Nếu thay `isSingleton()` của `freshParser` thành true trong khi `getObject()` vẫn tạo product mới mỗi lần (bỏ nhánh cache), bạn đã viết factory **vi phạm hợp đồng**. Spring có thể cache product từ lần gọi đầu khi factory singleton, khiến hai lần `getBean` vẫn trùng nhau, nhưng không được dùng việc cache tình cờ để kết luận factory chính xác.

## 6. @Bean và FactoryBean khác nhau thế nào?

Ba cách tạo object có thể cùng tồn tại trong Spring:

### 6.1. @Bean thông thường

```java
@Configuration(proxyBeanMethods = false)
class BasicConfig {
    @Bean
    Parser parser() {
        return new Parser("direct", 1);
    }
}
```

Đây là fragment cần imports `Configuration`, `Bean` và type `Parser` của bài. Khi gọi `getBean("parser")`, Spring trả object của `@Bean` method. Không có lớp implement `FactoryBean`; logic tạo product đặt ngay trong method cấu hình.

### 6.2. @Bean trả một FactoryBean

```java
@Configuration(proxyBeanMethods = false)
class AdvancedConfig {
    @Bean("parser")
    ParserFactory parserFactory() {
        return new ParserFactory("generated", true);
    }
}
```

Fragment tương tự dự án mẫu: khi gọi `getBean("parser")`, Spring áp dụng **FactoryBean contract** và trả `Parser`. Còn `getBean("&parser")` mới là `ParserFactory`.

### 6.3. Factory method của một bean definition

Trong XML hoặc một `BeanDefinition` cấu hình thủ công, Spring có thể gọi static/instance **factory method** được chỉ định bằng metadata để xây bean. Đây là **factory-method mechanism**, không nhất thiết dùng interface `FactoryBean`.

| Thuộc tính | `@Bean` trả object thường | `@Bean` trả `FactoryBean<T>` | Bean definition factory method |
| --- | --- | --- | --- |
| Product tạo ở đâu? | Trong method `@Bean` | Trong `FactoryBean.getObject()` | Trong method theo bean definition |
| `getBean("name")` | Trả instance tạo bởi method | Trả product `T` | Trả kết quả factory method |
| `getBean("&name")` | Không dùng nếu bean không là FactoryBean | Trả factory instance | Chỉ có ý nghĩa nếu kết quả là FactoryBean |
| Dùng `getObjectType()`, `isSingleton()`? | Không | Có | Không, trừ khi kết quả là FactoryBean |
| Thích hợp | Đa số dependency đơn giản | Instantiation logic phức tạp, metadata type và scope product riêng | Cấu hình factory-method đặc thù |

**Chọn thứ đơn giản nhất đáp ứng yêu cầu.** `FactoryBean` hữu ích khi cần đóng gói cơ chế tạo product có metadata về type/identity; không nên dùng chỉ để giấu vài dòng `new SomeService()`.

## 7. Product và Factory có vòng đời khác nhau

### 7.1. Vòng đời của factory bean

Khi Spring tạo instance của `ParserFactory` (qua `@Bean` hoặc khai báo khác), nó có thể:
1. Gọi constructor/factory method tạo `ParserFactory`.
2. Inject dependency vào factory instance (nếu factory được cấu hình để Spring inject).
3. Thực thi `Aware` callback, `@PostConstruct`, `InitializingBean.afterPropertiesSet()` hoặc custom init method của **factory**.
4. Apply `BeanPostProcessor` lên factory; đăng ký destruction callback của factory nếu phù hợp scope.

Vì factory là Spring bean được quản lý, các quy tắc bean lifecycle thông thường áp dụng **cho chính factory**.

### 7.2. Khi nào product được tạo?

Không có một đáp án “luôn lúc refresh”:
- Factory singleton eager có thể được tạo lúc container refresh, nhưng product thường do `getObject()` tạo **on demand**.
- Product có thể được yêu cầu sớm khi một singleton khác phụ thuộc vào kiểu product.
- Một `SmartFactoryBean` có thể quảng bá `isEagerInit() == true`, khiến Spring khởi tạo singleton product sớm trong pre-instantiation.
- Nếu product đã cache, một lookup khác không nhất thiết gọi `getObject()` lần nữa.
- Với factory không-singleton hoặc product non-singleton, thời điểm/số lần tạo phụ thuộc số lần resolve và scope của factory.

`SmartFactoryBean<T>` mở rộng `FactoryBean<T>` với `isPrototype()`, `isEagerInit()`. Nó chủ yếu phục vụ infrastructure/framework phức tạp; với ứng dụng thông thường, hãy ưu tiên `FactoryBean<T>` cơ bản.

### 7.3. Product không mặc nhiên nhận toàn bộ lifecycle như một bean definition riêng

Một product do `FactoryBean.getObject()` trả về có thể được Spring áp dụng một số `BeanPostProcessor` tại bước công bố product, nhưng không được suy ra rằng object đó trải qua **toàn bộ** constructor injection, `@PostConstruct`, `InitializingBean`, destroy methods và mọi semantics của một bean được khai báo độc lập.

Ví dụ:

```java
public final class SocketClient implements AutoCloseable {
    private boolean connected;

    public void connect() {
        connected = true;
    }

    @Override
    public void close() {
        connected = false;
    }
}
```

Đây là class Java độc lập về mặt cú pháp, nhưng không tự mở socket; nó mô tả resource lifecycle. Nếu factory gọi `new SocketClient()` rồi `connect()` để trả product, cần quy định ai sẽ gọi `close()`. Một lựa chọn là **factory** implement `DisposableBean` và đóng resource mà nó tạo khi factory bị destroy.

```java
public final class ClientFactory
        implements FactoryBean<SocketClient>, DisposableBean {
    private SocketClient client;

    @Override
    public synchronized SocketClient getObject() {
        if (client == null) {
            client = new SocketClient();
            client.connect();
        }
        return client;
    }

    @Override
    public Class<?> getObjectType() {
        return SocketClient.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }

    @Override
    public synchronized void destroy() {
        if (client != null) {
            client.close();
            client = null;
        }
    }
}
```

Đoạn factory này cần imports `org.springframework.beans.factory.FactoryBean`, `DisposableBean` và class `SocketClient` cùng package; nó **không** thuộc sample runnable mục 5. Cách cleanup hoạt động khi factory được Spring quản lý/hủy trong scope thích hợp và app không tiếp tục dùng client sau shutdown. Với product non-singleton, factory phải theo dõi các instance cần đóng hoặc chuyển trách nhiệm cleanup cho caller/scope khác; không thể chỉ giữ một field `client`.

### 7.4. Không trộn khái niệm FactoryBean product với @Scope("prototype")

`FactoryBean.isSingleton() == false` không hoàn toàn tương đương bean definition scope `prototype`. Một implementation `FactoryBean` non-singleton có thể dùng pooling hoặc một scope riêng; `SmartFactoryBean.isPrototype()` phân biệt product **độc lập mỗi lần**. Trong ví dụ `freshParser`, product thực sự mới mỗi lần vì chính code `getObject()` tạo `new Parser`.

`context.isSingleton("factoryName")`/`isPrototype("factoryName")` hỏi về tên bean theo logic BeanFactory, có thể phản ánh product semantics; `context.isSingleton("&factoryName")` hỏi về factory semantics. Khi nghi ngờ, kiểm tra cả bean definition scope và `FactoryBean.isSingleton()`, không kết luận chỉ từ tên method.

## 8. Type discovery, autowiring và những bẫy dễ gặp

### 8.1. getObjectType() trả null khiến bean khó được inject

Khi tìm product theo type, Spring có thể hỏi factory xem nó tạo type gì **mà không gọi getObject()**. Nếu `getObjectType()` trả `null`, một dependency `Parser` có thể không khớp/không được phát hiện lúc autowire.

```java
@Override
public Class<?> getObjectType() {
    return null; // Chỉ dùng khi thật sự không thể biết type sớm.
}
```

Đây là fragment minh họa anti-pattern. Tốt hơn khai báo `Parser.class` hoặc interface `ParserContract.class` phù hợp ngay từ constructor/config metadata. Không chạy expensive SDK initialization trong `getObjectType()`.

### 8.2. Nhiều product cùng type gây ambiguous dependency

Ở mục 5 có hai factory đều tạo `Parser`. Nếu viết:

```java
@Service
class ParserConsumer {
    private final Parser parser;

    ParserConsumer(Parser parser) {
        this.parser = parser;
    }
}
```

Snippet này cần import `org.springframework.stereotype.Service` và type `Parser` cùng package. Nếu chỉ có hai bean product `sharedParser` và `freshParser`, inject `Parser` **không có qualifier** có thể ném `NoUniqueBeanDefinitionException` vì có nhiều candidate cùng type. Dùng:

```java
@Service
class ParserConsumer {
    private final Parser parser;

    ParserConsumer(@Qualifier("sharedParser") Parser parser) {
        this.parser = parser;
    }
}
```

Cần import `Service`, `Qualifier`; @Qualifier chọn product bean `sharedParser`. Không inject theo `ParserFactory` nếu mục đích là sản phẩm. Với tên factory đặc biệt, `getBean("&sharedParser")` luôn rõ khi cần chính factory cho hạ tầng.

### 8.3. Generic type metadata

Triển khai `FactoryBean<Parser>` giúp Java type safety và cũng giúp Spring suy luận kiểu trong một số trường hợp. Tuy nhiên nên implement `getObjectType()` chính xác; generic signature không thay hoàn toàn trách nhiệm khai báo kiểu product, nhất là factory xây object dựa trên config. Với `@Bean` method trả trực tiếp `FactoryBean<Parser>` thay vì concrete implementation, kiểm tra type discovery và registration thực tế nếu hạ tầng phụ thuộc vào nó.

### 8.4. Lấy factory bằng & rồi gọi getObject() trực tiếp

`getBean("&sharedParser")` chỉ yêu cầu factory. Nếu bạn tự gọi `sharedFactory.getObject()`, bạn bỏ qua **một phần** hành vi Spring khi lấy product như cache và một số post-processing; factory nên vẫn đáp ứng contract `isSingleton()`. Vì thế consumer thông thường nên nhận `Parser` từ Spring thay vì gọi factory trực tiếp, trừ khi bạn đang xây infrastructure cần kiểm soát factory.

### 8.5. getObjectType không nên buộc khởi tạo sớm

Một implementation sai:

```java
@Override
public Class<?> getObjectType() {
    return getObject().getClass(); // Tạo product chỉ để biết type!
}
```

Đây là fragment minh họa anti-pattern, không nhất thiết biên dịch nếu `getObject()` throws checked `Exception`. Nó có thể mở connection ngay trong type matching, làm startup chậm, tạo vòng phụ thuộc và tăng side effect. Khai báo type tĩnh khi có thể hoặc một type estimate không gây side effect.

## 9. Exception và trạng thái chưa khởi tạo

`FactoryBean.getObject()` có thể ném `Exception`. Khi được gọi qua Spring `getBean(...)`, lỗi có thể được wrap thành bean creation exception, tùy loại lỗi và phase. Không coi exception như lời hứa container sẽ tự retry và rollback mọi thứ.

```java
@Override
public Client getObject() throws Exception {
    if (!configured) {
        throw new FactoryBeanNotInitializedException(
                "ClientFactory has not finished configuration");
    }
    return createClient();
}
```

Snippet cần `Client`, `FactoryBeanNotInitializedException`, fields `configured` và method `createClient` thuộc ứng dụng; nó chỉ minh họa, **không runnable độc lập**. Trong Spring, `FactoryBeanNotInitializedException` là cách báo factory chưa thể cung cấp product, ví dụ factory bị yêu cầu sớm do vòng phụ thuộc.

Những quy tắc cần nhớ:
- Không lấy product của chính factory trong constructor/`@PostConstruct` rồi tạo vòng `getBean("self")`.
- Không gọi network IO vô thời hạn trong `getObject()`. Dùng timeout và error policy rõ ràng, tránh làm request/container startup treo.
- Nếu việc tạo product mở tài nguyên rồi thất bại, cleanup phần đã mở ngay trong `catch/finally`; không dựa vào mọi destroy callback có thể chạy sau một initialization thất bại.
- Nếu muốn retry factory product creation, phải xác định lúc nào retry, khi nào cache exception hoặc fallback; semantics retry không được `FactoryBean` tự động áp đặt.
- Đừng tiết lộ token, password, URL nhạy cảm trong exception message/log khi SDK init lỗi.

## 10. FactoryBean, ObjectFactory, ObjectProvider và BeanFactory

Bốn interface có tên gần giống nhau nhưng nhiệm vụ khác nhau:

| API | Ai implement/chủ yếu sử dụng? | Vai trò |
| --- | --- | --- |
| `FactoryBean<T>` | Một bean Spring làm factory | Tích hợp logic tạo product với container, kèm type/singleton metadata |
| `BeanFactory` | Container | Lưu/resolve bean definitions và cung cấp instance |
| `ObjectFactory<T>` | Abstraction provider đơn giản | Lấy một object `getObject()` khi cần, không có contract product type/singleton của FactoryBean |
| `ObjectProvider<T>` | Container injection/lookup | Lấy bean theo demand, optional access và nhiều tiện ích như `getIfAvailable()`, `stream()` |

`FactoryBean` **không** phải `BeanFactory`, và gọi `ObjectProvider.getObject()` **không** có nghĩa lớp provider đang tạo bean bằng `FactoryBean`. Provider có thể resolve một bean vốn do Spring quản lý bình thường hoặc được FactoryBean cung cấp — hai cơ chế độc lập.

Khi nào chọn công cụ?

- Muốn Spring đăng ký **một product type với logic instantiation phức tạp** và tên bean hoạt động như product → `FactoryBean<T>`.
- Muốn dependency prototype mỗi lần thực hiện nghiệp vụ (đã khai báo bean prototype) → inject `ObjectProvider<T>` rồi gọi `getObject()` lúc cần.
- Muốn tạo object theo cấu hình đơn giản một lần → `@Bean`.
- Muốn truy cập tên bean động trong framework → `BeanFactory`/`ApplicationContext` nhưng hạn chế service locator trong code nghiệp vụ.

## 11. Concurrency và caching: trách nhiệm của ai?

Nếu `FactoryBean` cung cấp singleton product cho nhiều luồng, Spring có thể cache một reference trong một BeanFactory. **Singleton identity không đồng nghĩa thread safety**. Product phải tự quản lý mutable state và invariant tương ứng; factory cũng có thể nhận nhiều lời gọi nếu product non-singleton và được truy cập đồng thời.

Trong ví dụ `ParserFactory`:
- `getObject()` có `synchronized` để giữ invariant product singleton và serial counter, ngay cả khi ngoài container có ai gọi trực tiếp.
- `Parser` là Java record, hai field `String` và primitive `int` immutable, không có mutable state.
- `isSingleton()` không dùng biến mutable thay đổi trong runtime; nó cố định từ constructor.
- `getObjectType()` thuần túy trả `Parser.class` nên an toàn khi container hỏi nhiều lần.

Một factory sản xuất client thực tế cần thêm:
1. Thread-safe lazy initialization hoặc eager construction có thứ tự rõ.
2. Cơ chế cleanup dù startup thành công hoặc lỗi.
3. Chính sách share/pool/tenant cho product được xác định trong `isSingleton()`.
4. Không lộ state per-request của người dùng qua singleton product.
5. Nếu deploy nhiều pod, không coi singleton là duy nhất toàn cluster.
6. Cache sản phẩm singleton chỉ theo container/scope tương ứng, không biến thành global process cache không kiểm soát.

Đừng dùng `isSingleton=false` nhưng bên trong tạo một pool bị giới hạn rồi quảng bá “prototype độc lập mỗi lần” cho downstream. Thực tế contract chỉ nói sản phẩm không singleton; nếu bắt buộc độc lập, hãy thiết kế/kiểm chứng identity và `SmartFactoryBean.isPrototype()` khi thật sự cần.

## 12. Những lỗi phổ biến và hướng khắc phục

| Sai lầm / triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `getBean("myFactory")` trả product thay vì factory | Spring giải tham chiếu `FactoryBean` theo tên thường | Dùng `getBean("&myFactory")` để lấy factory |
| `ClassCastException` khi cast product sang FactoryBean | Nhầm hai lớp object | Sử dụng kiểu `T` cho product và `FactoryBean<T>` cho factory |
| Cùng một bean name nhưng getType trả kiểu lạ | Type product được công bố qua `getObjectType()` | Kiểm tra kiểu product và prefix `&` |
| Inject product theo type không tìm thấy | `getObjectType()` trả `null`/sai type | Trả type ổn định, có thể xác định sớm |
| `getObject()` chạy trong lúc type discovery | Viết `getObjectType()` gọi `getObject()` | Tách logic type discovery khỏi object creation |
| `isSingleton()==true` nhưng gọi trực tiếp factory trả instance khác | Factory không tuân thủ contract | Cache reference hoặc đổi isSingleton phù hợp |
| Factory singleton nhưng product xuất hiện nhiều lần | `isSingleton()==false` hoặc factory tự tạo product | Phân biệt factory scope và product identity |
| Hai product cùng type khiến inject mơ hồ | Nhiều bean candidates | Sử dụng `@Qualifier` hoặc chọn primary theo thiết kế |
| Sản phẩm chứa tài nguyên nhưng không được đóng | Lifecycle product không phải bean definition độc lập | Factory quản lý cleanup hoặc tạo lifecycle component riêng |
| `@PostConstruct` trên product không chạy như kỳ vọng | Product không nhận toàn bộ lifecycle như bean được khai báo thường | Init trong factory/đăng ký callback phù hợp |
| Lỗi init vòng phụ thuộc | Factory/product yêu cầu chính mình hoặc dependency chưa sẵn sàng | Thiết kế dependency graph không vòng, hoãn lookup khi phù hợp |
| `getObject()` chặn startup lâu | Nặng I/O, thiếu timeout | Timeout, retry policy, lifecycle/readiness phù hợp |
| Sản phẩm trông như singleton nhưng không thread-safe | Cùng instance được nhiều luồng sử dụng | Thiết kế immutable, synchronization/atomic theo invariant |
| Muốn mỗi request một product nhưng factory cache singleton | Dùng sai semantic scope | Sử dụng request scope hoặc factory logic phù hợp, không đổi flag ngẫu nhiên |
| Lấy `&factory` nhưng product không được tạo | `&` trả factory, không bắt buộc getObject | Gọi getBean không prefix khi thực sự cần product |

## 13. Luyện tập và câu hỏi tự đánh giá

**Bài tập A — client SDK:** Một cấu hình tạo client gắn endpoint, retry policy và credential provider; client share an toàn nhiều luồng và tốn chi phí tạo. Nên chọn `isSingleton=true`, cache một reference và cleanup khi container đóng. `getObjectType` cần trả đúng class/interface client mà không mở kết nối chỉ để suy kiểu.

**Bài tập B — formatter riêng từng task:** Mỗi task cần trạng thái tích lũy dữ liệu, không thể dùng chung. Có thể dùng `FactoryBean<Formatter>` với `isSingleton=false` và mỗi lần `getObject()` trả instance mới; tuy nhiên nếu gọi nhiều lần trong cùng task, phải giữ chính product đã lấy, không gọi lại provider vô tình tạo instance khác.

**Bài tập C — tích hợp legacy factory:** Third-party API cung cấp static factory method rất dài và không expose constructor. Nếu logic tạo một object đơn giản, `@Bean` gọi static method là đủ. Nếu còn cần product type discovery, non-singleton creation policy hoặc reuse dưới nhiều kiểu cấu hình, `FactoryBean` đáng cân nhắc.

Câu hỏi:
1. Spring `FactoryBean<T>` khác `BeanFactory` thế nào?
2. Nếu bean name `paymentClient` là `FactoryBean<Client>`, `getBean("paymentClient")` trả gì?
3. Làm sao lấy chính factory của `paymentClient`?
4. Khi `isSingleton()==true`, factory phải bảo đảm điều gì về reference trả từ `getObject()`?
5. Factory bean definition singleton có buộc product singleton không?
6. Product non-singleton có chắc chắn là một instance độc lập ở mỗi lookup không?
7. Tại sao `getObjectType()` nên làm việc được trước initialization và không gọi `getObject()`?
8. Nếu `getObjectType()` trả null, autowiring theo type có thể bị ảnh hưởng ra sao?
9. Có hai FactoryBean cùng trả `Parser`. Inject `Parser` không qualifier có thể lỗi gì?
10. `SmartFactoryBean.isEagerInit()` được dùng để phân biệt điều gì?
11. Product được tạo bằng `getObject()` có tự động nhận mọi `@PostConstruct`/destroy callback như bean definition riêng không?
12. Một singleton product có nhiều request cùng gọi method. `isSingleton()` có bảo đảm nó thread-safe không?
13. Vì sao nên dùng `&` khi muốn đếm số lần factory tạo product?
14. Khi factory `getObject()` tự gọi `context.getBean("sameName")`, nguy cơ nào có thể xảy ra?
15. Nếu chỉ có `return new Parser("A", 1)`, tại sao `@Bean` thường phù hợp hơn `FactoryBean`?

**Đáp án gợi ý:** (1) FactoryBean tạo product, BeanFactory là container. (2) Product `Client`. (3) `getBean("&paymentClient")`. (4) Trả cùng shared reference; container có thể cache. (5) Không, `isSingleton` của product độc lập. (6) Không nhất thiết; `isSingleton=false` chỉ nói không singleton, `SmartFactoryBean.isPrototype` rõ hơn. (7) Type matching có thể xảy ra sớm; gọi product lúc này có side effect/cycle. (8) Candidate không được phát hiện. (9) `NoUniqueBeanDefinitionException`. (10) Có cần tạo singleton product eagerly lúc bootstrap. (11) Không mặc nhiên. (12) Không. (13) Để nhận chính factory thay vì product và có thể kiểm tra metadata/counter. (14) Circular dependency hoặc recursive creation. (15) Ít boilerplate, đủ cho object đơn giản.

## 14. Checklist ứng dụng trong production

1. Tên bean được dùng để truy xuất product, còn factory phải được lấy rõ ràng bằng `&` khi thật sự cần.
2. `getObjectType()` chính xác, nhẹ, ổn định và không đòi product đã tạo.
3. `isSingleton()` phản ánh đúng khả năng share reference của `getObject()`.
4. Nếu product singleton, factory không trả instance mới mỗi lần khi gọi trực tiếp.
5. Nếu product non-singleton, consumer biết lúc nào cần giữ một instance qua nhiều bước xử lý.
6. Không dùng `@Scope("prototype")` của factory như cách thay thế việc thiết kế product lifecycle.
7. Tránh circular dependency và không resolve chính product của factory trong khởi tạo factory.
8. Tài nguyên client/connection có owner chịu trách nhiệm đóng, kể cả khi init thất bại.
9. Code không giả định product tự động đi qua toàn bộ lifecycle của một bean definition riêng.
10. Product shared thread-safe theo nghiệp vụ, không chỉ vì `isSingleton=true`.
11. Type-based injection xử lý rõ trường hợp có nhiều candidates.
12. Thêm tests cho product identity, type query không tạo object, failure path và cleanup.
13. Với factory dùng SDK ngoài, đo latency của `getObject()` và có timeout/backoff.
14. Không coi per-container singleton là singleton toàn JVM hoặc cluster.

## Tài liệu chính thức

- Spring Framework Reference — Customizing Instantiation Logic with a FactoryBean: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework 6.2 — `FactoryBean` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/FactoryBean.html
- Spring Framework 6.2 — `BeanFactory` Javadoc và `FACTORY_BEAN_PREFIX`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/BeanFactory.html
- Spring Framework 6.2 — `SmartFactoryBean` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/SmartFactoryBean.html
- Spring Framework Reference — Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework Reference — Java-based Container Configuration (`@Bean`): https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html
