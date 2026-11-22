# Tiêm mảng, List, Set và Map<String, T> trong Spring Core Container

## Mục tiêu học tập

Khi một chức năng cần **nhiều implementation cùng giao diện**, Spring có thể đưa tất cả bean phù hợp vào một dependency thay vì buộc ta chọn một bean duy nhất. Sau bài này, bạn sẽ biết cách tiêm `T[]`, `List<T>`, `Set<T>` và `Map<String, T>`; hiểu tên bean, cách lọc bằng qualifier, thứ tự thực thi, ứng xử khi không có bean và các lỗi dễ gặp.

Ví dụ ứng dụng: hệ thống xử lý đơn hàng có nhiều bước kiểm tra; mỗi bước là một bean triển khai `OrderRule`. Service nhận `List<OrderRule>` rồi duyệt từng bước, không cần tự viết danh sách cố định các class triển khai.

## 1. Bốn hình thức tập hợp phụ thuộc

Giả sử trong Spring container có ba bean cùng triển khai interface `Handler`. Một injection point có thể khai báo:

```java
Handler[] handlers;
List<Handler> handlers;
Set<Handler> handlers;
Map<String, Handler> handlersByName;
```

| Kiểu nhận | Giá trị được tiêm | Dùng khi |
| --- | --- | --- |
| `Handler[]` | Mảng chứa các bean `Handler` phù hợp | Tích hợp API Java đang dùng mảng |
| `List<Handler>` | Danh sách các bean phù hợp | Pipeline cần duyệt theo thứ tự xác định |
| `Set<Handler>` | Tập hợp các bean phù hợp | Quan tâm tính tập hợp, không nên phụ thuộc thứ tự duyệt |
| `Map<String, Handler>` | Khóa là **tên bean**, giá trị là bean tương ứng | Chọn chiến lược theo tên bean hoặc tra cứu handler |

Đây là **multi-bean autowiring**: Spring tìm nhiều bean có kiểu phù hợp với `T`. Nó khác việc tự khai báo một bean riêng có giá trị là `List<T>` hoặc một `Map` cấu hình. Kiểu phần tử vẫn quan trọng: `List<Handler>` không có nghĩa là lấy mọi bean trong ứng dụng.

Các điểm tiêm thông dụng là tham số constructor, tham số của phương thức `@Bean`, setter có `@Autowired` hoặc field có `@Autowired`. Với bean chỉ có **một constructor**, Spring tự dùng constructor đó mà không cần đặt `@Autowired`.

## 2. Spring lựa chọn phần tử như thế nào?

Một cách hiểu thực dụng về quá trình phân giải dependency:

1. Spring có các bean definition được đăng ký qua `@Component`/component scan, `@Bean` trong configuration hoặc cách đăng ký tương đương. Chỉ đối tượng được container quản lý mới tham gia autowiring.
2. Với `List<T>`, `T[]` hoặc `Set<T>`, Spring tìm các bean là ứng viên autowire có kiểu tương thích `T`. Với `Map<String, T>`, nó tìm theo kiểu của **giá trị `T`** rồi dùng **bean name** làm khóa.
3. Spring xét metadata của injection point, bao gồm qualifier và thông tin generic khi có. `@Qualifier` có thể **lọc nhiều bean cùng lúc**, không chỉ chọn một bean.
4. Container cung cấp tập kết quả. `@Order`/`Ordered` ảnh hưởng thứ tự phần tử của mảng và danh sách; các tập hợp khác không nên được dùng như hợp đồng thứ tự xử lý.

**Chú ý về `@Primary`:** Với `Handler handler` (đơn lẻ), `@Primary` giúp chọn một bean giữa nhiều ứng viên. Với `List<Handler>`/mảng/set/map, các bean phù hợp **vẫn cùng xuất hiện**; `@Primary` không biến danh sách thành một phần tử. `@Qualifier` mới là công cụ phù hợp để thu hẹp nhóm.

Bean name có thể do `@Bean("name")`, `@Component("name")` hoặc quy tắc đặt tên mặc định tạo ra. Với map tự động tiêm, khóa **không phải** tên class, giá trị trả về từ `handler.id()` hay tên qualifier.

## 3. Ví dụ chạy đầy đủ với Java 17 và Spring Framework 6.2

Ví dụ sau đăng ký ba `Handler`, tiêm đủ bốn kiểu, lọc nhóm `fast` và đối chiếu với một dependency đơn lẻ dùng `@Primary`. Dùng Spring Framework thuần, không phụ thuộc Spring Boot.

Cấu trúc dự án:

```text
spring-collection-injection/
├── pom.xml
└── src/main/java/demo/CollectionInjectionDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-collection-injection</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/demo/CollectionInjectionDemo.java`:

```java
package demo;

import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

public class CollectionInjectionDemo {

    interface Handler {
        String id();
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean("alphaHandler")
        @Order(20)
        @Qualifier("fast")
        Handler alphaHandler() {
            return () -> "A";
        }

        @Bean("betaHandler")
        @Order(10)
        @Primary
        @Qualifier("fast")
        Handler betaHandler() {
            return () -> "B";
        }

        @Bean("gammaHandler")
        @Order(30)
        @Qualifier("slow")
        Handler gammaHandler() {
            return () -> "C";
        }

        @Bean
        Report report(
                Handler[] array,
                List<Handler> list,
                Set<Handler> set,
                Map<String, Handler> byName,
                @Qualifier("fast") List<Handler> fast,
                Handler preferred) {
            return new Report(array, list, set, byName, fast, preferred);
        }
    }

    record Report(
            Handler[] array,
            List<Handler> list,
            Set<Handler> set,
            Map<String, Handler> byName,
            List<Handler> fast,
            Handler preferred) {

        void print() {
            System.out.println("Array: " + ids(Arrays.asList(array)));
            System.out.println("List: " + ids(list));
            System.out.println("Set size: " + set.size());
            System.out.println("Map keys (sorted): " + new TreeSet<>(byName.keySet()));
            System.out.println("Fast: " + ids(fast));
            System.out.println("Single (@Primary): " + preferred.id());
        }
    }

    private static String ids(Collection<Handler> handlers) {
        return handlers.stream().map(Handler::id)
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(Report.class).print();
        }
    }
}
```

Chạy trong thư mục chứa `pom.xml` (yêu cầu JDK 17+ và Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.CollectionInjectionDemo
```

Các dòng do chương trình in ra (không tính log của Maven hoặc thư viện nếu môi trường bật log):

```text
Array: B,A,C
List: B,A,C
Set size: 3
Map keys (sorted): [alphaHandler, betaHandler, gammaHandler]
Fast: B,A
Single (@Primary): B
```

Giải thích từng kết quả:

- Mảng và `List` chứa cả ba handler, theo thứ tự `@Order(10)`, `@Order(20)`, `@Order(30)`. Giá trị **nhỏ hơn đi trước**.
- `Set` chứa các bean phù hợp. Ví dụ chỉ in kích thước, vì logic ứng dụng không nên giả định thứ tự duyệt `Set` giống `List`.
- `Map<String, Handler>` có khóa là ba **bean name** đã khai báo. `TreeSet` trong lệnh in chỉ **sắp xếp tên để output cố định**, không chứng minh map được Spring cấp theo thứ tự chữ cái hay `@Order`.
- Tham số `@Qualifier("fast") List<Handler> fast` chỉ nhận hai bean có qualifier `fast`, rồi danh sách vẫn chịu quy tắc `@Order`.
- `Handler preferred` chỉ có một giá trị và chọn `betaHandler` nhờ `@Primary`. Dấu `@Primary` trên `betaHandler` **không loại** nó hoặc các bean khác khỏi các tập hợp.

Trong một bean do `@Component` quản lý, cách viết thường gặp là constructor injection:

```java
// Đoạn minh họa: cần có Handler là kiểu đã định nghĩa trong ứng dụng.
@Component
class HandlerPipeline {
    private final List<Handler> handlers;

    HandlerPipeline(List<Handler> handlers) {
        this.handlers = handlers;
    }

    void execute() {
        handlers.forEach(handler -> System.out.println(handler.id()));
    }
}
```

Ở đoạn trên, import `@Component` là `org.springframework.stereotype.Component`. Class cần nằm trong phạm vi component scan, còn `Handler` và các implementation phải được đăng ký bean. Đoạn ngắn này là **minh họa để đưa vào dự án**, không phải chương trình chạy độc lập.

## 4. Lọc tập hợp bằng `@Qualifier`

`@Qualifier` áp dụng được cho collection injection. Ví dụ hai bean đều mang nhãn `fast`; Spring sẽ đưa **cả hai** vào `List<Handler>` có `@Qualifier("fast")`. Không yêu cầu giá trị qualifier phải duy nhất.

Có thể gắn qualifier vào bean định nghĩa qua `@Component` hoặc phương thức `@Bean`; phía nhận đặt trên field, constructor parameter hoặc method parameter. Trước hết Spring vẫn khớp kiểu `Handler`, sau đó qualifier thu hẹp tập ứng viên. Dù qualifier trùng một bean name, qualifier vẫn được hiểu là điều kiện lọc trong tập bean đã khớp kiểu, không phải cơ chế bỏ qua kiểm tra kiểu.

Cú pháp triển khai phổ biến (đoạn minh họa, dùng trong bean Spring):

```java
@Autowired
@Qualifier("fast")
private List<Handler> fastHandlers;

// Tương đương về ý tưởng khi dùng constructor:
// MyService(@Qualifier("fast") List<Handler> fastHandlers) { ... }
```

Ưu tiên constructor injection cho dependency bắt buộc vì dễ test, giữ trường `final` và bộc lộ rõ hợp đồng của class.

## 5. Thứ tự: `@Order`, `Ordered`, `@Priority` và `@DependsOn`

Khi chạy pipeline, **thứ tự là một phần của nghiệp vụ**. Đối với mảng và `List<T>` được autowire, Spring nhận thứ tự từ `org.springframework.core.Ordered`, `@Order` hoặc chuẩn `@Priority`. Số nhỏ hơn có độ ưu tiên cao hơn; nếu không khai báo thứ tự, mặc định thường theo thứ tự đăng ký bean, nhưng không nên dựa vào đó như quy ước nghiệp vụ bền vững.

```java
@Bean
@Order(100)
Handler lastHandler() {
    return () -> "last";
}
```

`@Order` có thể đặt trên class component hoặc từng phương thức `@Bean`. Nếu nhiều `@Bean` tạo instance cùng một class, đặt trên **mỗi phương thức** giúp xác định thứ tự của từng bean. `jakarta.annotation.Priority` là một lựa chọn ở cấp class; annotation chuẩn này không khai báo trên phương thức `@Bean`. Có thể dùng `Ordered` khi mức ưu tiên cần được khai báo qua đối tượng.

Đừng nhầm:

- `@Order` điều khiển **thứ tự khi lấy nhiều bean** hoặc một số cơ chế sắp xếp của framework; nó **không** bắt singleton phải khởi tạo theo thứ tự đó.
- `@DependsOn` nói về **phụ thuộc khởi tạo/hủy bean**, không phải thứ tự phần tử trong `List<T>`.
- `@Primary` chủ yếu giải quyết **một injection point kiểu đơn lẻ** khi có nhiều ứng viên, không phải bộ lọc danh sách.
- Với `Set<T>` và `Map<String, T>`, nếu business flow bắt buộc có thứ tự, hãy dùng `List<T>` với `@Order`, hoặc tự sắp xếp một bản sao theo comparator rõ ràng. Không dựa vào thứ tự duyệt của set/map.

## 6. Generic type là một phần điều kiện chọn

Spring có thể dùng thông tin generic của bean và injection point để tìm đúng ứng viên. Ví dụ `Store<String>` và `Store<Integer>` không nhất thiết thuộc cùng một nhóm khi yêu cầu `List<Store<String>>`.

```java
// Đoạn minh họa bên trong một @Configuration;
// giả sử đã khai báo interface Store<T> { T get(); }
@Bean
Store<String> textStore() {
    return () -> "ready";
}

@Bean
Store<Integer> countStore() {
    return () -> 42;
}

// Trong bean tiêu thụ:
@Autowired
List<Store<String>> stringStores; // chỉ các Store<String> phù hợp
```

Điều này dựa trên metadata generic mà Spring nhận biết từ khai báo bean, chẳng hạn kiểu trả về của `@Bean`. **Không dùng raw type** như `List` hoặc `Map` rồi kỳ vọng Spring suy ra `T`. Với `Map<String, Store<String>>`, `String` đầu tiên là **kiểu khóa tên bean**, còn `Store<String>` là kiểu của giá trị cần lọc.

Nếu tự tạo bean là một `List<Handler>` (thay vì nhiều bean `Handler`), cần phân biệt hai mục đích: **tiêm một collection bean đã định nghĩa** và **thu thập nhiều bean phần tử**. Spring có thể so khớp collection bean bằng thông tin kiểu, nhưng nếu mục tiêu là tham chiếu **chính collection bean theo tên**, có thể dùng `@Resource(name = "...")` trên field/setter hoặc cấu hình tường minh. Cách tiêm đó không mang nghĩa lấy tất cả các implementation. Với tham số constructor, `@Qualifier` hoặc cấu hình tường minh phù hợp hơn `@Resource`.

## 7. Khi không tìm được bean `T`

Đây là trường hợp cần phân biệt **nơi tiêm** và quy tắc bắt buộc:

| Tình huống | Hành vi cần lưu ý |
| --- | --- |
| Field hoặc setter `@Autowired` mặc định, tập ứng viên rỗng | Injection point bắt buộc có thể gây lỗi tạo bean (`UnsatisfiedDependencyException`/lỗi liên quan). Theo tài liệu Spring, đa phần cần ít nhất một phần tử khớp. |
| Field hoặc setter `@Autowired(required = false)`, không có ứng viên | Spring bỏ qua tiêm; field giữ giá trị ban đầu, setter có thể không được gọi. Không tự động khẳng định field nhận collection rỗng. |
| **Một constructor duy nhất** của bean, tham số array/collection/map không có phần tử | Spring có quy tắc đặc biệt: multi-element parameter có thể nhận container **rỗng**. Đây là ngoại lệ quan trọng khi thiết kế plugin tùy chọn. |
| Truy cập động với `ObjectProvider<T>` | Có thể dùng `orderedStream()` để truy vấn các bean phù hợp tại thời điểm sử dụng. |

Ví dụ field tùy chọn giữ mặc định:

```java
// Minh họa nằm trong một bean được Spring quản lý:
@Autowired(required = false)
private List<Handler> optionalHandlers = List.of();
```

Nếu muốn diễn đạt rõ dependency có thể thiếu và có tính động/lazy, `ObjectProvider<T>` hữu ích:

```java
// Minh họa: import org.springframework.beans.factory.ObjectProvider;
private final ObjectProvider<Handler> handlerProvider;

MyService(ObjectProvider<Handler> handlerProvider) {
    this.handlerProvider = handlerProvider;
}

void process() {
    handlerProvider.orderedStream().forEach(handler -> {
        // Gọi từng handler theo thứ tự Spring hỗ trợ.
    });
}
```

Đoạn này cần đặt vào class `MyService` do Spring quản lý. Nó cho phép hỏi container lúc dùng thay vì giữ sẵn một danh sách tại thời điểm khởi tạo.

Lưu ý thêm về scope: nếu tiêm thẳng một `List<PrototypeBean>` vào singleton, không có nghĩa mỗi lần duyệt list sẽ tự sinh một prototype mới. Việc giải quyết dependency đã xảy ra khi singleton được tạo. Khi cần instance mới theo từng lần dùng, cân nhắc `ObjectProvider` hoặc cơ chế scope phù hợp.

## 8. Phân biệt map bean với map dữ liệu cấu hình

Hai khai báo trông giống nhau nhưng có ý nghĩa khác:

```java
@Autowired
Map<String, Handler> handlersByName;  // tên bean -> instance Handler
```

Đây là **map các bean**. Các khóa như `alphaHandler` được lấy từ container.

```java
// Khai báo dữ liệu ứng dụng theo cấu hình, không phải ví dụ autowire các Handler:
Map<String, String> endpoints;
```

Nếu `endpoints` chứa dữ liệu YAML/properties như `payments: https://...`, nên dùng cơ chế bind cấu hình (ví dụ `@ConfigurationProperties` trong Spring Boot, hoặc `@Value`/chuyển đổi giá trị thích hợp). Không kỳ vọng tiêm `Map<String, String>` bằng `@Autowired` sẽ tự biến toàn bộ thuộc tính cấu hình thành map.

Ràng buộc đáng nhớ: dạng **đa bean map** đòi khóa `String` vì khóa là bean name. `Map<Long, Handler>` không phải cách yêu cầu Spring tạo map với id số tự động. Nếu cần tra cứu theo khóa nghiệp vụ, hãy xây map riêng:

```java
// Minh họa tạo index nghiệp vụ từ collection đã tiêm:
Map<String, Handler> byBusinessId = handlers.stream()
        .collect(Collectors.toMap(Handler::id, h -> h));
```

Khi dùng `Collectors.toMap`, hãy xử lý id trùng nếu nghiệp vụ cho phép; đoạn trên ném lỗi nếu có hai handler cùng id.

## 9. Thiết kế và vận hành an toàn

**Hãy chọn kiểu dữ liệu theo ý nghĩa sử dụng.** Nếu chạy chuỗi filter/validator/plugin theo thứ tự, `List<T>` là lựa chọn rõ ràng. Nếu cần chọn implementation theo tên đăng ký, dùng `Map<String, T>`. Nếu thư viện yêu cầu mảng, dùng `T[]`. Nếu chỉ cần nhóm đối tượng, `Set<T>` phù hợp, nhưng đừng suy luận `Set` sẽ loại các bean khác nhau chỉ vì chúng có cùng class hoặc cùng id nghiệp vụ.

**Định danh và tính ổn định.** Khóa của `Map<String, T>` phụ thuộc tên bean. Đổi tên `@Bean`, đổi component name hoặc refactor cách đăng ký có thể phá lookup bằng chuỗi. Nếu khóa là hợp đồng nghiệp vụ công khai, khai báo tên bean tường minh hoặc thiết kế registry riêng theo một định danh nghiệp vụ ổn định.

**Tính đóng gói.** Collection đã tiêm là danh sách tham chiếu bean. Tránh thêm/xóa phần tử trực tiếp rồi giả định đã thay đổi đăng ký trong container. Nếu service muốn bảo vệ trạng thái, có thể chụp bản sao (`List.copyOf`, `Map.copyOf`) hoặc cấu trúc phù hợp; nếu cần giữ thứ tự map, chọn cấu trúc có quy ước thứ tự rõ ràng. Mọi tham chiếu vẫn trỏ tới bean gốc, bản sao collection không clone đối tượng bên trong.

**Độ lớn tập ứng viên.** Một interface quá chung có thể thu hút nhiều bean không liên quan. Dùng interface có ý nghĩa nghiệp vụ, qualifier hoặc generic rõ ràng; tránh quét component ngoài phạm vi dự định. Đặc biệt, một bean có `autowireCandidate=false` hay các điều kiện đăng ký khác có thể không tham gia tập ứng viên.

**Thời điểm sử dụng.** Collection constructor injection thường được phân giải khi tạo consumer. Nếu các bean được đăng ký hoặc thay đổi về sau, đừng mặc định collection đã tiêm được cập nhật theo thời gian; nếu thật sự cần tra cứu động, dùng API `ApplicationContext`/`ObjectProvider` có chủ đích.

## 10. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` hoặc `UnsatisfiedDependencyException` | Không có bean `T` phù hợp; field/setter bắt buộc | Kiểm tra `@Component`, component scan, `@Bean`, qualifier, condition và dạng injection |
| `NoUniqueBeanDefinitionException` khi tiêm `T` đơn lẻ | Có nhiều `T` mà không giải quyết được ứng viên duy nhất | Dùng `@Qualifier` hoặc `@Primary`, hoặc đổi sang multi-bean injection nếu thực sự cần tất cả |
| `List<T>` thiếu bean mong muốn | Bean chưa đăng ký, generic/qualifier không khớp hoặc không là ứng viên autowire | Kiểm tra bean definition và chữ ký kiểu trả về |
| `Map<String, T>` không có khóa mong đợi | Nhầm bean name với class name, qualifier hoặc id nghiệp vụ | Ghi rõ `@Bean("...")` hoặc `@Component("...")` và kiểm tra `keySet()` |
| Pipeline chạy sai thứ tự | Tin vào thứ tự đăng ký hoặc thứ tự duyệt `Set`/`Map` | Dùng `List<T>` và đặt `@Order` tại bean mục tiêu |
| `@Order` bị hiểu là thứ tự tạo singleton | `@Order` chỉ phục vụ cơ chế sắp xếp thích hợp | Dùng quan hệ dependency/`@DependsOn` nếu cần ràng buộc khởi tạo |
| Field tùy chọn là `null` | `@Autowired(required=false)` bỏ qua tiêm | Khởi tạo giá trị mặc định an toàn hoặc đổi sang constructor injection/`ObjectProvider` |
| Map nhận không đúng kiểu dữ liệu | Trộn map tên bean với map properties hoặc dùng khóa không phải `String` | Tách bean registry khỏi cơ chế bind configuration |

Các bước gỡ lỗi ngắn gọn: kiểm tra **bean đã được tạo/đăng ký chưa**; kiểm tra **T và generic**; kiểm tra **qualifier/condition**; cuối cùng kiểm tra **bean name và `@Order`**. Khi test, có thể lấy trực tiếp `context.getBeansOfType(Handler.class)` để quan sát các bean thuộc kiểu đó, nhưng nhớ kết quả tra cứu theo kiểu không tự mô phỏng đầy đủ mọi qualifier của một injection point cụ thể.

## 11. Bài tập tự kiểm tra

1. Thêm bean `deltaHandler` với `@Order(5)` và qualifier `slow` vào ví dụ hoàn chỉnh. Dự đoán `Array`, `List`, `Set size`, `Map keys` và `Fast` thay đổi thế nào.
2. Bỏ `@Primary` khỏi `betaHandler` nhưng giữ tham số `Handler preferred`. Phân tích vì sao tiêm kiểu đơn lẻ có thể thất bại khi nhiều `Handler` khớp, trong khi tập hợp vẫn có thể phân giải.
3. Đổi `@Qualifier("fast")` trên tham số `List<Handler>` thành `@Qualifier("slow")`. Giải thích kết quả mong đợi và lý do `@Order` không thay qualifier.
4. Xây `Map<String, Handler>` theo `Handler.id()` từ `List<Handler>` đã tiêm. Bạn sẽ xử lý thế nào nếu hai bean trả về cùng một id?

**Tự đối chiếu:** Bài 1: `Array`/`List` bắt đầu bằng D (thứ tự `5,10,20,30`), size set tăng thành 4, map có thêm `deltaHandler`, `Fast` vẫn gồm B và A. Bài 2: có nhiều ứng viên cho `Handler` đơn lẻ, cần điều kiện chọn; việc tiêm tập hợp vẫn chứa các bean phù hợp. Bài 3: danh sách lọc chỉ lấy `gammaHandler`. Bài 4: cần chính sách xử lý khóa trùng (báo lỗi, chọn đầu/cuối hoặc thiết kế id duy nhất).

## Tài liệu chính thức

- Spring Framework — [Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html): tiêm mảng, collection, map, thứ tự và dependency tùy chọn.
- Spring Framework — [Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html): qualifier là bộ lọc, kể cả trên collection.
- Spring Framework — [Using Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html): lọc ứng viên bằng generic.
- Spring Framework — [`@Autowired` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/beans/factory/annotation/Autowired.html): hợp đồng API của array/collection/map injection.
