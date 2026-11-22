# Dùng tham số kiểu tổng quát làm điều kiện chọn bean trong Spring

## 1. Vấn đề: cùng interface nhưng khác kiểu dữ liệu

Một interface generic có thể biểu diễn nhiều năng lực khác nhau:

~~~java
interface Store<T> {
    T read();
}
~~~

Một implementation `Store<String>` cung cấp chuỗi, trong khi `Store<Integer>` cung cấp số nguyên. Về **raw type**, cả hai đều là `Store`, nhưng chúng không mang cùng **kiểu tham số hóa**.

Nếu Spring đăng ký các bean có metadata kiểu:

~~~java
@Bean
Store<String> messageStore() {
    return new StringStore();
}

@Bean
Store<Integer> counterStore() {
    return new IntegerStore();
}
~~~

thì một injection point khai báo `Store<String>` có thể chọn `messageStore` mà không cần ghi `@Qualifier("messageStore")`; tương tự `Store<Integer>` có thể chọn `counterStore`. Spring gọi cơ chế này là **generics as autowiring qualifiers**: **tham số kiểu tổng quát là một dạng qualifier ngầm**. <https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html>

Hai method `@Bean` trên là **ví dụ minh họa**, còn thiếu các class; mã chạy độc lập có đầy đủ định nghĩa ở mục 5.

**Điểm mấu chốt:** Spring không chỉ nhìn tên interface `Store`, mà còn có thể xét kiểu `T` trong các metadata type được bảo tồn tại bean definition và injection point. Điều này khác với việc Java tạo một class runtime riêng cho từng `Store<T>`: Java vẫn sử dụng **type erasure**, nhưng chữ ký khai báo, generic interfaces và những nguồn metadata thích hợp vẫn có thể lưu thông tin generic để container phân giải.

~~~text
Bean declarations                 Injection point
--------------------------------------------------------------
Store<String> messageStore    --> Store<String>       chọn messageStore
Store<Integer> counterStore   --> Store<Integer>      chọn counterStore
Store<Double> priceStore      --> Store<Double>       chọn priceStore

Store<Integer> counterStore   --+
Store<Integer> auditStore     --+--> List<Store<Integer>> nhận cả hai
Store<String> messageStore    --+--> không vào nhóm Integer
~~~

**Lợi ích:** khi kiểu generic thực sự biểu thị vai trò, chúng giúp tránh phải đặt qualifier bằng String chỉ để phân biệt các nhóm khác nhau.

## 2. Generic qualifier được áp dụng ở bước nào?

Một mô hình tư duy hữu ích:

1. Spring xác định kiểu dependency từ constructor/field/method/factory method; ví dụ `Store<String>`.
2. Container tìm các bean có metadata **assignable và tương thích generic** với kiểu yêu cầu.
3. Những bộ lọc bổ sung như `@Qualifier`, tên bean, `@Primary` và quy tắc giải quyết khác được xét khi phù hợp.
4. Nếu injection yêu cầu **một bean**, container cần chọn được ứng viên cuối cùng; nếu yêu cầu **một collection**, Spring có thể tập hợp nhiều ứng viên tương thích.

Tài liệu Spring xác nhận việc dùng generic type như qualifier không chỉ áp dụng cho field mà còn cả **typed collections** như `List`, `Map` và arrays. Có thể dùng ở constructor arguments và `@Bean` factory method parameters phù hợp. <https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html>

### Bảng ví dụ

| Bean được khai báo | Kiểu metadata | Injection point | Có phù hợp về generic? |
| --- | --- | --- | --- |
| `words` | `Store<String>` | `Store<String>` | Có |
| `counter` | `Store<Integer>` | `Store<String>` | Không |
| `counter` | `Store<Integer>` | `Store<Integer>` | Có |
| `price` | `Store<Double>` | `List<Store<Integer>>` | Không |
| `auditCounter` | `Store<Integer>` | `List<Store<Integer>>` | Có |

Bảng giả định Spring có **đầy đủ metadata generic** của từng bean; với raw types, factory metadata thiếu kiểu hoặc proxy đặc biệt, phải kiểm tra behavior thực tế.

### Generic không phải một annotation `@Qualifier`

Đoạn này:

~~~java
@Autowired
private Store<String> messages;
~~~

có thể inject bean phù hợp chỉ nhờ kiểu `Store<String>`, ngay cả khi **không có `@Qualifier`** trên field. Spring hiểu yêu cầu thông qua generic signature.

Dùng `@Qualifier` vẫn hữu ích nếu còn **hai bean cùng kiểu đầy đủ `Store<String>`**. Generic chỉ tách được nhóm theo kiểu, không phân biệt ý nghĩa giữa hai đối tượng cùng nhóm.

## 3. Java generics, type erasure và lý do Spring vẫn làm được

### 3.1. `Store<String>` và `Store<Integer>` có cùng raw class

Java generics chủ yếu được kiểm tra ở compile time; nhiều tham số kiểu bị **xóa** ở biểu diễn bytecode của các tham chiếu. Điều đó có nghĩa Java không có hai class runtime độc lập tên `Store<String>` và `Store<Integer>`.

Ví dụ (chưa runnable độc lập vì thiếu `Store`):

~~~java
Store<String> text = ...;
Store<Integer> number = ...;

// Khi nhìn raw interface:
// text instanceof Store
// number instanceof Store
~~~

`instanceof Store<String>` không phải phép kiểm tra kiểu tham số hóa cụ thể thông thường được Java cho phép. Không thể giải quyết mọi generic bằng cách hỏi `someObject.getClass()` rồi đoán T từ một instance ở runtime.

### 3.2. Generic signatures có thể được giữ trong metadata

Tuy có erasure, Java reflection vẫn có thể đọc **chữ ký generic được khai báo** trên field, superclass, generic interface, method parameter/return type. Spring sử dụng cơ chế kiểu nâng cao như `ResolvableType` để làm việc với metadata tương ứng.

Ví dụ một `@Bean` method khai báo return type `Store<Integer>` giúp container biết ý định type của bean hơn nhiều so với một method chỉ khai báo raw type `Store`.

**Không hiểu nhầm:** Spring không suy ra rằng một raw `Store` là `Store<Integer>` chỉ vì instance chứa giá trị `123`. Nội dung dữ liệu runtime không phải hợp đồng type an toàn cho autowiring.

### 3.3. Java 17 thuần kiểm tra metadata erasure

Tạo file độc lập `GenericSignatureDemo.java`:

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;

public final class GenericSignatureDemo {
    interface Store<T> {}

    Store<String> words;
    Store<Integer> numbers;

    public static void main(String[] args) throws Exception {
        Type a = GenericSignatureDemo.class
                .getDeclaredField("words").getGenericType();
        Type b = GenericSignatureDemo.class
                .getDeclaredField("numbers").getGenericType();

        ParameterizedType text = (ParameterizedType) a;
        ParameterizedType integer = (ParameterizedType) b;

        System.out.println("TEXT_ARG "
                + text.getActualTypeArguments()[0].getTypeName());
        System.out.println("NUMBER_ARG "
                + integer.getActualTypeArguments()[0].getTypeName());
        System.out.println("SAME_RAW "
                + text.getRawType().equals(integer.getRawType()));
    }
}
~~~

Biên dịch và chạy với **JDK 17+**, không dùng Spring:

~~~bash
javac --release 17 -encoding UTF-8 GenericSignatureDemo.java
java GenericSignatureDemo
~~~

Stdout:

~~~text
TEXT_ARG java.lang.String
NUMBER_ARG java.lang.Integer
SAME_RAW true
~~~

Hai field mang generic arguments khác nhau và `getGenericType()` phản ánh điều đó. Nhưng `getRawType()` giống nhau. Spring dựa trên metadata type phù hợp, không tự tạo một JVM class mới mỗi tham số type.

## 4. Injection một bean và injection nhiều bean theo generic

### 4.1. Một tham số đầy đủ

~~~java
public MessageService(Store<String> store) {
    this.store = store;
}
~~~

Đây là snippet minh họa cần khai báo service và `Store`. Nếu chỉ có **một `Store<String>`** được đăng ký, Spring có thể resolve tham số từ generic type.

### 4.2. Nếu có hai `Store<Integer>`?

Giả sử:

~~~java
@Bean
Store<Integer> primaryCounter() { ... }

@Bean
Store<Integer> secondaryCounter() { ... }
~~~

Khi yêu cầu một `Store<Integer>` duy nhất, generic filter vẫn để lại **hai ứng viên**. Nếu không có rule chọn bổ sung, có thể gặp `NoUniqueBeanDefinitionException`.

Điều này chứng minh **generic qualifier phân biệt loại tham số kiểu, không xác định bean ID duy nhất**. Có thể dùng thêm `@Qualifier("primaryCounter")` hoặc qualifier mang ý nghĩa như `@Qualifier("reporting")` trên injection point và candidate phù hợp.

### 4.3. Collection chỉ lấy các bean generic tương thích

~~~java
public Aggregator(List<Store<Integer>> integerStores) {
    this.integerStores = integerStores;
}
~~~

Đoạn minh họa này biểu diễn một nhóm. Với nhiều bean `Store<Integer>`, Spring có thể inject **tất cả** bean tương thích với generic `Integer`, nhưng không đưa `Store<String>` vào nhóm.

Spring cũng hỗ trợ kiểu injection `Map<String, Store<Integer>>`; key trong map thông thường là **bean names** và values là các bean `Store<Integer>` tương ứng. `List<Store<String>>` sẽ là tập khác.

### 4.4. Cách nhìn đúng với `@Primary` và `@Qualifier`

| Injection | Sau generic filter | Còn cần gì? |
| --- | --- | --- |
| `Store<String>` với một bean String | 1 bean | Không cần qualifier tên |
| `Store<Integer>` với hai bean Integer | 2 bean | Cần một rule chọn bean cho single dependency |
| `@Qualifier("reporting") Store<Integer>` | Những bean Integer có nhãn reporting | Một ứng viên cuối hoặc rule bổ sung |
| `List<Store<Integer>>` | Toàn bộ bean Integer phù hợp | Có thể inject cả nhóm |
| `Map<String, Store<Integer>>` | Toàn bộ bean Integer phù hợp | Keys là bean names |
| `Store<?>` | Kiểu wildcard rộng hơn | Có thể match nhiều candidate; không tự chọn duy nhất |

`@Primary` có thể ưu tiên một bean khi injection target cần **một object**, nhưng không có nghĩa `List<Store<Integer>>` tự co lại thành một phần tử. Nếu candidate được đánh dấu `@Primary` lại có generic type không phù hợp, primary không làm nó thỏa type yêu cầu.

## 5. Ví dụ đầy đủ: Spring Framework 6.2 và Java 17

Ví dụ dùng **một interface generic `Store<T>`**, một bean `Store<String>` và **hai bean `Store<Integer>`**. Một bean Integer được đánh dấu qualifier `reporting`; bean còn lại không. `Dashboard` nhận:

- `Store<String>`: một candidate nhờ generic type.
- `@Qualifier("reporting") Store<Integer>`: một candidate trong số hai bean cùng generic.
- `List<Store<Integer>>`: hai ứng viên Integer.
- `Map<String, Store<Integer>>`: hai entries với keys là bean names.
- `List<Store<String>>`: chỉ một ứng viên String.

### 5.1. Thư mục và Maven

Yêu cầu JDK 17+ và Maven; không cần Spring Boot, web server, database hoặc Java preview features.

~~~text
generic-qualifier-demo/
├── pom.xml
└── src/main/java/demo/GenericQualifierDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>generic-qualifier-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                    <mainClass>demo.GenericQualifierDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. File Java đầy đủ

Tạo `src/main/java/demo/GenericQualifierDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class GenericQualifierDemo {
    private GenericQualifierDemo() {}

    public interface Store<T> {
        String label();
        T read();
    }

    public record FixedStore<T>(String label, T value) implements Store<T> {
        @Override
        public T read() {
            return value;
        }
    }

    public static final class Dashboard {
        private final Store<String> message;
        private final Store<Integer> selectedCounter;
        private final List<Store<Integer>> counters;
        private final Map<String, Store<Integer>> countersByBeanName;
        private final List<Store<String>> messages;

        public Dashboard(Store<String> message,
                         Store<Integer> selectedCounter,
                         List<Store<Integer>> counters,
                         Map<String, Store<Integer>> countersByBeanName,
                         List<Store<String>> messages) {
            this.message = Objects.requireNonNull(message);
            this.selectedCounter = Objects.requireNonNull(selectedCounter);
            this.counters = List.copyOf(counters);
            this.countersByBeanName = Map.copyOf(countersByBeanName);
            this.messages = List.copyOf(messages);
        }

        public String messageValue() {
            return message.read();
        }

        public String selectedValue() {
            return selectedCounter.label() + "="
                    + selectedCounter.read();
        }

        public String counterValues() {
            return counters.stream()
                    .map(s -> s.label() + "=" + s.read())
                    .sorted()
                    .toList()
                    .toString();
        }

        public String counterNames() {
            return countersByBeanName.keySet().stream()
                    .sorted()
                    .toList()
                    .toString();
        }

        public int counterCount() {
            return counters.size();
        }

        public int messageCount() {
            return messages.size();
        }

        public int reportValue() {
            return countersByBeanName.get("reportCounter").read();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Store<String> welcomeStore() {
            return new FixedStore<>("welcome", "hello");
        }

        @Bean
        @Qualifier("reporting")
        public Store<Integer> reportCounter() {
            return new FixedStore<>("report", 17);
        }

        @Bean
        @Qualifier("archival")
        public Store<Integer> archiveCounter() {
            return new FixedStore<>("archive", 42);
        }

        // Spring resolves generic arguments of each factory parameter.
        @Bean
        public Dashboard dashboard(
                Store<String> stringStore,
                @Qualifier("reporting") Store<Integer> selected,
                List<Store<Integer>> integerStores,
                Map<String, Store<Integer>> integersByName,
                List<Store<String>> stringStores) {
            return new Dashboard(stringStore, selected, integerStores,
                    integersByName, stringStores);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            Dashboard dash = context.getBean(Dashboard.class);

            System.out.println("MESSAGE " + dash.messageValue());
            System.out.println("SELECTED " + dash.selectedValue());
            System.out.println("INT_COUNT " + dash.counterCount());
            System.out.println("INT_VALUES " + dash.counterValues());
            System.out.println("INT_NAMES " + dash.counterNames());
            System.out.println("STRING_COUNT " + dash.messageCount());
            System.out.println("REPORT_VALUE " + dash.reportValue());
            System.out.println("SAME_DASHBOARD "
                    + (dash == context.getBean(Dashboard.class)));
        }
    }
}
~~~

**Điều làm ví dụ đáng chú ý:** hai bean `reportCounter` và `archiveCounter` đều có return type khai báo rõ `Store<Integer>`, nên generic qualifier **không chọn được duy nhất** nếu chỉ nhìn type. `@Qualifier("reporting")` đặt trên một factory method và tham số `selected` giúp chọn một bean báo cáo; còn `List` và `Map` **vẫn nhận cả hai `Store<Integer>`**. Bean `welcomeStore` mang type `Store<String>` nên chỉ vào nhóm String.

### 5.3. Chạy qua Maven

Từ thư mục `generic-qualifier-demo`:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Nếu chạy trực tiếp bằng `javac/java`, cần classpath chứa cả Spring và dependencies tương ứng; Maven quản lý classpath cho ví dụ. `maven.compiler.release=17` yêu cầu biên dịch tương thích Java 17.

**Stdout do chính chương trình in theo thứ tự:**

~~~text
MESSAGE hello
SELECTED report=17
INT_COUNT 2
INT_VALUES [archive=42, report=17]
INT_NAMES [archiveCounter, reportCounter]
STRING_COUNT 1
REPORT_VALUE 17
SAME_DASHBOARD true
~~~

Maven có thể in thêm thông tin tải dependencies và log riêng. Khối trên mô tả **System.out.println của chương trình**, không khẳng định toàn bộ terminal chỉ có tám dòng.

### 5.4. Giải thích stdout

1. `Store<String> stringStore` tại `dashboard(...)` được match tới `welcomeStore`. `reportCounter` và `archiveCounter` không phù hợp với tham số type String nên `MESSAGE hello`.
2. `@Qualifier("reporting") Store<Integer> selected` chọn bean `reportCounter`, nên `SELECTED report=17`.
3. `List<Store<Integer>>` nhận hai beans integer, không nhận `Store<String>`. Kết quả `INT_COUNT 2`.
4. `counterValues()` biến từng store thành chuỗi `label=value` rồi `sorted()`, cho `[archive=42, report=17]` ổn định, không phụ thuộc thứ tự đăng ký bean.
5. `Map<String, Store<Integer>>` mang hai keys bean name `archiveCounter` và `reportCounter`. `sorted()` trên keys cho thứ tự như dòng `INT_NAMES`.
6. `List<Store<String>>` có một bean nên `STRING_COUNT 1`.
7. Truy vấn map theo `reportCounter` cho `REPORT_VALUE 17`.
8. `Dashboard` là singleton mặc định trong cùng context, nên lookup lặp lại trả cùng reference `SAME_DASHBOARD true`.

**Không có stdout trong constructor/factory methods** của các bean, giúp output ổn định và không dựa vào thứ tự Spring tạo singleton.

## 6. Những giới hạn và lỗi dễ gặp

### 6.1. Khai báo raw generic làm mất thông tin chọn bean

So sánh:

~~~java
@Bean
Store<Integer> integerStore() {
    return new FixedStore<>("int", 5);
}
~~~

với:

~~~java
@Bean
@SuppressWarnings("rawtypes")
Store rawStore() {
    return new FixedStore<Integer>("int", 5);
}
~~~

Đây là **hai snippet minh họa riêng**, giả định đã có `Store` và `FixedStore`. Method thứ hai **khai báo raw return type** nên bean factory method metadata không thể hiện `<Integer>`. Tùy class, target type, bean factory inference và proxy, Spring có thể không tìm được generic argument chính xác hoặc có đường matching rộng hơn mong muốn.

Không kết luận mọi bean raw chắc chắn bị loại/luôn được chọn: behavior cần kiểm chứng theo bean definition thực tế. Nhưng best practice là **giữ generic signature tường minh** trên `@Bean` method và injection point.

### 6.2. Type erasure không bị “vô hiệu hóa”

Spring dùng metadata của chữ ký kiểu đã khai báo; nó không cần thử từng value bên trong store để đoán `T`. Nếu một factory tạo `Store<Integer>` nhưng khai báo return type `Object`/raw `Store`, container không nhất thiết suy ra chính xác từ contents.

Đừng viết business code cho rằng `getClass()` của một instance `FixedStore<Integer>` luôn cho biết T là Integer. Class generic `FixedStore<T>` có thể dùng chung runtime class cho nhiều instantiations.

### 6.3. Wildcard, raw, type variables và nested generics

Ví dụ:

~~~java
Store<?> anyStore;
Store<? extends Number> numericStore;
List<Store<Integer>> integerStores;
Store<List<String>> nestedStringLists;
~~~

Đây là các field minh họa, không phải injection points của demo. `Store<?>` thường rộng hơn `Store<String>`, có thể để lại nhiều ứng viên. `Store<? extends Number>` và nested generic type có quan hệ assignability/variance cần metadata phù hợp; **không đoán rằng Spring luôn chọn duy nhất**. Với type variables `Store<T>` ở class generic, việc resolve T còn phụ thuộc Spring biết được binding của class bean đang xét hay không.

Một cấu hình nên tránh wildcard/raw injection nếu tính chính xác của bean selection phụ thuộc một `T` cụ thể.

### 6.4. Java generics bất biến ở compile time

`Store<Integer>` **không phải subtype** của `Store<Number>` chỉ vì `Integer extends Number`. Đây là invariance của Java generics, không phải sự cố của Spring. Vì thế không dùng `Store<Number>` để ngầm yêu cầu `Store<Integer>` nếu không có typing phù hợp.

### 6.5. Generic qualifier không giải quyết mọi ambiguity

Nếu có hai bean `Store<Integer>`, injection `Store<Integer>` đơn vẫn có thể báo `NoUniqueBeanDefinitionException`. Có thể kết hợp:

- `@Qualifier("reporting")` để chọn vai trò.
- `@Primary` nếu một bean thực sự là ưu tiên mặc định trong tập phù hợp.
- Bean name hoặc custom qualifier khi dùng tên/metadata có chủ đích.
- `List<Store<Integer>>` khi nghiệp vụ cần **cả nhóm**, không cần duy nhất một bean.
- Factory/strategy theo dữ liệu runtime nếu lựa chọn thay đổi theo từng request.

Không tự thêm `@Primary` cho mọi implementation hoặc chuyển tất cả sang `ObjectProvider` để lẩn tránh lựa chọn rõ.

### 6.6. Annotation và component registration vẫn là điều kiện

Một class triển khai `Store<String>` không tự xuất hiện trong Spring context vì Java generic interface của nó. Phải đăng ký bean qua `@Bean`, component scan hoặc cách phù hợp. Và nếu type metadata bị ẩn bởi proxy/factory, cần đánh giá đường runtime thật, không suy luận chỉ từ interface Java trong IDE.

## 7. Generics vs `@Qualifier` vs bean name: chọn cách nào?

| Cách | Thể hiện | Phù hợp khi |
| --- | --- | --- |
| Generic type | `Store<String>` vs `Store<Integer>` | Khác **loại dữ liệu/hợp đồng kiểu** |
| Spring `@Qualifier("reporting")` | Chỉ các candidates cùng nhãn | Nhiều implementation **cùng generic type** nhưng khác vai trò |
| `@Primary` | Ưu tiên khi cần một bean | Có lựa chọn mặc định trong số candidates hợp lệ |
| Bean name | `reportCounter` | Cần tham chiếu tên cụ thể, hiểu bean-name matching semantics |
| Collection typed | `List<Store<Integer>>` | Cần nhiều beans cùng kiểu generic |
| Provider/factory | `ObjectProvider<Store<Integer>>` | Cần lookup trì hoãn hoặc theo nhu cầu |
| Strategy ở nghiệp vụ | `Map<Key, Handler>` hoặc router | Chọn theo request/runtime policy, không phải lúc wiring |

**Không đồng nhất trách nhiệm:** generic parameter mô tả **kiểu** của một dependency; qualifier annotation mô tả thêm **đặc tính** của bean. Hai cơ chế có thể phối hợp, không loại trừ nhau.

### Tránh phụ thuộc tên Java parameter một cách vô ý

Trong Spring hiện đại, khi có nhiều bean cùng kiểu, tên field/parameter có thể đóng vai trò matching cuối trong một số điều kiện. Nhưng không nên dựa vào tên source code như `reportCounter` để thay thế một qualifier có ý nghĩa, đặc biệt khi project chưa bật `-parameters` hoặc cần ổn định qua refactor.

Nếu yêu cầu thật sự là “store phục vụ reporting”, hãy ghi `@Qualifier("reporting")`. Nếu chỉ yêu cầu “store số nguyên”, hãy giữ generic `Store<Integer>` và bảo đảm số lượng ứng viên đúng.

## 8. Kiểm thử và gỡ lỗi

### Kiểm thử generic type resolution

Một integration test cho container nên kiểm tra:

1. `Store<String>` chọn đúng string bean.
2. `List<Store<Integer>>` chỉ có những integer beans.
3. `Map<String, Store<Integer>>` chứa đúng bean names.
4. `@Qualifier("reporting") Store<Integer>` chọn đúng báo cáo.
5. Trường hợp cố tình inject một `Store<Integer>` không qualifier với hai candidates báo lỗi hoặc đòi rule chọn, thay vì ứng dụng vô tình chọn một bean.

Chương trình demo đã cung cấp output kiểm tra bốn điều đầu. Một số test negative nên chạy trong một test context riêng, tránh làm ứng dụng chính fail startup.

### Gỡ lỗi theo thứ tự

- **Bước 1 — xác nhận bean được đăng ký:** kiểm tra `@Bean`, component scan, profiles, conditions.
- **Bước 2 — so type đầy đủ:** `Store<String>` khác `Store<Integer>`, không chỉ nhìn raw `Store`.
- **Bước 3 — xem declared signatures:** bean factory method có khai báo parameterized return type không? Class generic có triển khai interface với parameter cụ thể không?
- **Bước 4 — kiểm tra qualifiers/primary:** sau generic filtering còn bao nhiêu candidates?
- **Bước 5 — kiểm tra injection target:** là single bean hay `List`/`Map`? Loại target thay đổi cách tổng hợp kết quả.
- **Bước 6 — đọc nguyên nhân gốc:** `NoSuchBeanDefinitionException` khi thiếu candidate, `NoUniqueBeanDefinitionException` khi dư candidate phù hợp, `BeanCreationException` khi factory/init của candidate bị lỗi.

**Đừng sửa bằng cách cast raw bean về `Store<String>`** chỉ để Spring không báo lỗi: cast không tạo được type safety và có thể gây `ClassCastException` khi dữ liệu được sử dụng.

## 9. Bài tập có đáp án

**Bài 1.** Có bean `Store<String>` và `Store<Integer>`. Injection `Store<String>` có nhất thiết cần `@Qualifier("stringStore")` không?

**Đáp án:** Không, nếu generic metadata đầy đủ và chỉ có một candidate phù hợp `Store<String>`. Spring có thể dùng generic argument làm implicit qualifier.

**Bài 2.** Hai bean cùng type `Store<Integer>`. Generic qualifier có chọn được một bean duy nhất không?

**Đáp án:** Không. Generic filter vẫn để lại cả hai; cần một rule chọn bổ sung nếu injection target chỉ cần một object.

**Bài 3.** Injection `List<Store<Integer>>` có nhận `Store<String>` không?

**Đáp án:** Không theo generic matching bình thường khi metadata type được bảo tồn. Nó chỉ lấy những store phù hợp `Integer`.

**Bài 4.** Vì sao `Map<String, Store<Integer>>` có keys là bean names?

**Đáp án:** Spring hỗ trợ autowiring typed maps theo bean names làm keys (String) và matching beans làm values.

**Bài 5.** Vì sao `Store<Integer>` không là subtype của `Store<Number>`?

**Đáp án:** Generic type parameters bất biến trong Java. Quan hệ subtype giữa Integer và Number không tự chuyển qua `Store<T>`.

**Bài 6.** Nếu `@Bean Store rawStore()` trả object chứa số Integer, Spring có chắc biết bean đó là `Store<Integer>` không?

**Đáp án:** Không chắc. Raw return type không bảo tồn T trên factory method signature; metadata target có thể thiếu hoặc phụ thuộc cách Spring biết actual bean class.

**Bài 7.** `Store<?>` có phân biệt rõ String và Integer như `Store<String>` không?

**Đáp án:** Không. Wildcard rộng hơn, nên có thể có nhiều bean compatible và cần quy tắc lựa chọn rõ.

**Bài 8.** Khi có một `Store<String>` và hai `Store<Integer>`, nên dùng gì nếu muốn tất cả integer stores?

**Đáp án:** `List<Store<Integer>>` hoặc typed `Map<String, Store<Integer>>`. Không cần chọn một bean bằng `@Primary` chỉ để có cả nhóm.

**Bài 9.** Nếu muốn trong hai Integer beans chỉ lấy reporting store cho một injection point?

**Đáp án:** Có thể kết hợp `Store<Integer>` với `@Qualifier("reporting")` ở injection point và bean candidate.

**Bài 10.** Vì sao `new FixedStore<>("x", 17).getClass()` không tự cho biết đây là `FixedStore<Integer>`?

**Đáp án:** Type erasure làm nhiều instantiations dùng chung runtime class. Metadata ở deklarations là nguồn chính xác hơn để Spring suy luận generic.

**Bài 11.** Có thể biến raw `Store` thành bean có type an toàn chỉ bằng annotation `@Primary` không?

**Đáp án:** Không. `@Primary` là quy tắc ưu tiên lựa chọn, không khôi phục generic argument bị thiếu.

## 10. Checklist thiết kế

- [ ] Dùng generic interface khi `T` thật sự diễn đạt hợp đồng type có giá trị.
- [ ] Khai báo return type `@Bean` tường minh như `Store<String>` thay vì raw `Store`.
- [ ] Giữ type parameters rõ ở constructor, field, method và collection injection points.
- [ ] Đăng ký bean đầy đủ, không nghĩ generic class tự được Spring scan.
- [ ] Kiểm tra số candidate **sau khi** lọc generic.
- [ ] Nếu cần một bean và còn nhiều candidates cùng generic, thêm qualifier/primary có chủ đích.
- [ ] Nếu cần tất cả beans `Store<Integer>`, dùng `List`/`Map` được tham số hóa.
- [ ] Không dựa vào type erasure để phân biệt actual T qua `getClass()`.
- [ ] Tránh raw/wildcard signatures nếu cần chính xác trong bean selection.
- [ ] Kiểm tra nested generics/type variables và metadata proxy khi cấu hình phức tạp.
- [ ] Đừng lạm dụng bean name matching theo tên source Java parameter.
- [ ] Để lựa chọn theo nội dung request ở strategy/business router, không ở generic qualifier.
- [ ] Tách unit test hợp đồng generic khỏi integration test Spring bean wiring.
- [ ] Test thiếu bean, hai bean cùng generic và nhóm collection injection.
- [ ] Phân biệt stdout chương trình với log Maven và compile Java 17 đúng release.

### Tài liệu Spring chính thức

- [Using Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html)
- [Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)

**Kết luận:** tham số generic của Java như `Store<String>` và `Store<Integer>` có thể là **implicit qualifiers** khi Spring giải quyết dependency. Tính năng này dùng được cho injection đơn, `List` và `Map` được tham số hóa; tuy nhiên generic không bảo đảm chọn duy nhất nếu có nhiều bean cùng full type, và nó phụ thuộc metadata type rõ ràng chứ không “đọc T từ object” bất chấp type erasure. Kết hợp generic type, `@Qualifier` và typed collections đúng chỗ sẽ làm object graph có kiểu an toàn, dễ mở rộng và dễ kiểm thử.