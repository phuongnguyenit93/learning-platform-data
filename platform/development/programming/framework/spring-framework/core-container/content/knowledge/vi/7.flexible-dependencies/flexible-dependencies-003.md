# Lọc tập hợp bean bằng `@Qualifier` và phân biệt với `@Primary`

## 1. Mục tiêu và bối cảnh

Khi một interface có nhiều implementation được Spring IoC container quản lý, một dependency có thể cần **một implementation phù hợp** hoặc **cả nhóm implementation phù hợp**. Hai trường hợp này có ý nghĩa khác nhau:

- Dependency **đơn** như `PaymentHandler handler`: Spring cần chọn đúng một bean.
- Dependency **đa phần tử** như `List<PaymentHandler>`, `Set<PaymentHandler>`, `PaymentHandler[]` hoặc `Map<String, PaymentHandler>`: Spring tập hợp các bean phù hợp theo kiểu. Có thể tiếp tục lọc nhóm đó bằng qualifier.
- `@Primary` chỉ diễn đạt **ưu tiên lựa chọn** khi phải chọn một bean từ nhiều ứng viên; nó không diễn đạt rằng bean khác bị loại khỏi các tập hợp.
- `@Qualifier` diễn đạt **tiêu chí lọc** trong tập các bean đã khớp kiểu, không bắt buộc xác định duy nhất một bean.

Bài này tập trung vào **lọc collection bằng qualifier** và so sánh trực tiếp với `@Primary`. Đây là cơ chế dependency resolution trong Spring Framework Core Container; không cần Spring Boot, web controller hay database.

## 2. Cách Spring chọn bean

Giả sử có bốn bean cùng kiểu `Processor`:

| Tên bean | Qualifier khai báo | `@Primary` |
| --- | --- | --- |
| `main` | `general` | Có |
| `fastOne` | `fast` | Không |
| `fastTwo` | `fast` | Không |
| `slow` | `slow` | Không |

Spring sẽ giải quyết những điểm tiêm dependency sau như thế nào?

| Điểm tiêm | Kết quả | Giải thích |
| --- | --- | --- |
| `Processor preferred` | `main` | Cần một bean; `main` là ứng viên primary duy nhất |
| `@Qualifier("slow") Processor selected` | `slow` | Lọc theo kiểu `Processor` và qualifier `slow`, còn đúng một ứng viên |
| `@Qualifier("fast") List<Processor> fast` | `fastOne` và `fastTwo` | Hai bean đều khớp kiểu và qualifier; không chọn một bean duy nhất |
| `List<Processor> all` | Cả bốn bean | Không có qualifier tại điểm tiêm; primary không loại các bean khác |
| `@Qualifier("fast") Map<String, Processor> fastMap` | Hai cặp với khóa `fastOne` và `fastTwo` | Các giá trị được lọc, còn khóa là **bean name** |
| `@Qualifier("fast") Processor oneFast` | Lỗi ambiguity | Hai bean cùng qualifier `fast`, không có một lựa chọn duy nhất |

Có thể hình dung quy trình:

```text
Điểm tiêm + kiểu generic (nếu có)
          |
          v
Xác định bean ứng viên theo kiểu và điều kiện autowire
          |
          v
Nếu có @Qualifier: chỉ giữ bean khớp tiêu chí
          |
          +--> Dependency dạng List/Set/array/Map:
          |    nhận các bean phù hợp (có thể sắp xếp List/array)
          |
          +--> Dependency đơn:
               cần chọn một bean;
               xét @Primary duy nhất (và các quy tắc phân giải khác)
               hoặc báo lỗi nếu vẫn mơ hồ
```

Đây là mô hình để hiểu, không phải mô tả thứ tự từng phương thức nội bộ của Spring. Quy tắc chọn bean đơn còn xét những tín hiệu khác, ví dụ tên bean/tên tham số, `@Priority` và `@Fallback` ở các phiên bản hỗ trợ; không nên dựa vào các quy tắc phụ khi ý định nghiệp vụ đã có qualifier rõ ràng.

## 3. `@Qualifier` với tập hợp: một nhãn có thể thuộc nhiều bean

Ví dụ hệ thống xử lý dữ liệu có nhiều chiến lược tốc độ cao. Cả `fastOne` và `fastTwo` có cùng nhãn `fast`. Đặt qualifier **trên bean** để khai báo thuộc nhóm, và **trên điểm tiêm** để yêu cầu nhóm đó:

```java
@Bean
@Qualifier("fast")
Processor fastOne() {
    return new Processor("fastOne");
}

@Bean
@Qualifier("fast")
Processor fastTwo() {
    return new Processor("fastTwo");
}

// Tại tham số constructor hoặc phương thức @Bean:
@Qualifier("fast") List<Processor> fastProcessors
```

Spring sẽ tiêm **hai phần tử**, vì qualifier không phải một khóa duy nhất. Nếu sau này thêm `fastThree` cũng có qualifier `fast`, collection sẽ tự có thêm bean đó mà không cần sửa constructor.

Những hình thức phổ biến:

- `@Qualifier("fast") List<Processor>`: lấy các bean phù hợp; phù hợp khi cần thứ tự xử lý.
- `@Qualifier("fast") Set<Processor>`: lấy các bean phù hợp theo kiểu tập hợp; đừng dựa vào thứ tự duyệt của `Set` nếu nghiệp vụ cần thứ tự.
- `@Qualifier("fast") Processor[]`: lấy các bean phù hợp ở dạng mảng.
- `@Qualifier("fast") Map<String, Processor>`: lấy các bean phù hợp; **khóa là tên bean** và **giá trị là bean instance**. Đây không phải map từ qualifier sang bean.

Qualifier trước tiên thu hẹp tập các bean **đã khớp kiểu**. Một bean khác kiểu dù trùng qualifier cũng không được thêm vào `List<Processor>`.

### Qualifier so với tên bean

`@Qualifier("fast")` thường là nhãn có ý nghĩa nghiệp vụ, ví dụ `fast`, `regional`, `audit`. Spring cũng có thể dùng **bean name** làm giá trị qualifier mặc định khi phù hợp; ví dụ `@Qualifier("fastOne")` có thể chọn bean tên `fastOne` ngay cả khi không gắn qualifier cùng chuỗi. Tuy nhiên, mã nghiệp vụ bền vững hơn khi dùng nhãn mô tả đặc tính thay vì gắn với tên method tạo bean.

Đối với `@Bean`, một qualifier ghi trên **phương thức tạo bean** là metadata cho bean đó; qualifier trên **tham số được tiêm** là điều kiện lựa chọn. Đặt qualifier chỉ ở một phía mà không có giá trị khớp sẽ không cho kết quả mong đợi.

## 4. `@Primary`: ưu tiên ở điểm tiêm đơn

Đánh dấu một bean là `@Primary` khi có nhiều bean cùng kiểu nhưng muốn một bean mặc định được chọn trong tình huống cần **một** instance:

```java
@Bean
@Primary
@Qualifier("general")
Processor main() {
    return new Processor("main");
}
```

Với các bean ở bảng đầu bài:

- `Processor preferred` không có qualifier sẽ nhận `main` vì đó là primary duy nhất trong các ứng viên của điểm tiêm đơn.
- `@Qualifier("slow") Processor selected` nhận `slow` dù `main` có `@Primary`: bean `main` không đáp ứng qualifier `slow`, nên không được ưu tiên ở đây.
- `List<Processor> all` vẫn chứa `main`, `fastOne`, `fastTwo`, `slow`. `@Primary` không “lọc mất” ba bean còn lại.
- `@Qualifier("fast") List<Processor> fast` vẫn chứa **cả hai** fast bean. Đánh dấu primary trên một bean nào đó không biến `List` thành danh sách một phần tử.

Nếu có **hai bean primary** cùng là ứng viên cho một điểm tiêm đơn, primary tự nó không thể phân giải sự mơ hồ. Nếu chỉ còn **một** bean sau khi qualifier lọc, Spring chọn bean đó; không cần bean ấy primary. Nếu sau khi qualifier lọc còn nhiều bean mà có đúng một primary trong số đó, primary có thể giúp chọn một bean **cho dependency đơn**, nhưng collection vẫn lấy tất cả bean khớp qualifier.

| Tiêu chí | `@Qualifier` | `@Primary` |
| --- | --- | --- |
| Ý nghĩa | Thu hẹp theo nhãn/thuộc tính | Đặt bean mặc định được ưu tiên |
| Tác dụng trên dependency đơn | Có, nhưng vẫn có thể còn nhiều ứng viên | Có, nếu phân giải được primary duy nhất |
| Tác dụng trên collection | **Lọc các phần tử** | **Không lọc phần tử** |
| Có được dùng lại cùng giá trị cho nhiều bean? | Có; rất hữu ích cho nhóm | Nhiều primary cùng kiểu có thể gây ambiguity ở điểm tiêm đơn |
| Khi nào dùng | Chọn một nhóm chiến lược hoặc một bean theo tiêu chí | Chọn implementation mặc định trong tập bean cùng kiểu |

## 5. Ví dụ đầy đủ chạy được với Java 17+ và Spring Framework 6

Tạo một ứng dụng Gradle thuần Spring Context với cấu trúc:

```text
qualifier-collections-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/QualifierCollectionsDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'qualifier-collections-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'QualifierCollectionsDemo'
}
```

`src/main/java/QualifierCollectionsDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

public class QualifierCollectionsDemo {

    record Processor(String id) {
    }

    record Inspector(
            Processor preferred,
            List<Processor> fast,
            Processor slow,
            List<Processor> all,
            Map<String, Processor> fastMap) {
    }

    @Configuration
    static class Config {

        @Bean
        @Primary
        @Qualifier("general")
        @Order(30)
        Processor main() {
            return new Processor("main");
        }

        @Bean
        @Qualifier("fast")
        @Order(20)
        Processor fastOne() {
            return new Processor("fastOne");
        }

        @Bean
        @Qualifier("fast")
        @Order(10)
        Processor fastTwo() {
            return new Processor("fastTwo");
        }

        @Bean
        @Qualifier("slow")
        @Order(40)
        Processor slow() {
            return new Processor("slow");
        }

        @Bean
        Inspector inspector(
                Processor preferred,
                @Qualifier("fast") List<Processor> fast,
                @Qualifier("slow") Processor slow,
                List<Processor> all,
                @Qualifier("fast") Map<String, Processor> fastMap) {
            return new Inspector(preferred, fast, slow, all, fastMap);
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            Inspector result = context.getBean(Inspector.class);

            System.out.println("single = " + result.preferred().id());
            System.out.println("fast = " + names(result.fast()));
            System.out.println("slow = " + result.slow().id());
            System.out.println("all = " + names(result.all()).stream().sorted().toList());
            System.out.println("fastKeys = " + new TreeSet<>(result.fastMap().keySet()));
        }
    }

    private static List<String> names(List<Processor> items) {
        return items.stream().map(Processor::id).toList();
    }
}
```

Chạy từ thư mục chứa `build.gradle` bằng Gradle và JDK 17 trở lên:

```bash
gradle run --quiet
```

Các dòng do `System.out.println` in ra:

```text
single = main
fast = [fastTwo, fastOne]
slow = slow
all = [fastOne, fastTwo, main, slow]
fastKeys = [fastOne, fastTwo]
```

**Giải thích từng dòng:**

1. `single = main`: tham số `Processor preferred` nhận primary. Tên tham số `preferred` không trùng tên bean `main` nên kết quả thể hiện chính sách primary.
2. `fast = [fastTwo, fastOne]`: qualifier `fast` nhận đúng hai bean; `@Order(10)` trên `fastTwo` đứng trước `@Order(20)` trên `fastOne`. `@Order` định thứ tự khi đưa bean vào danh sách, không biến chúng thành bean primary.
3. `slow = slow`: chỉ bean `slow` khớp `@Qualifier("slow")`, bất kể `main` có `@Primary`.
4. `all = [...]`: không qualifier nên nhận cả bốn bean; mã minh họa sắp xếp danh sách **theo tên** trước khi in để stdout ổn định, không suy ra thứ tự mặc định của Spring từ dòng này.
5. `fastKeys = [fastOne, fastTwo]`: `Map<String, Processor>` lọc theo qualifier, nhưng key vẫn là **tên bean**. `TreeSet` chỉ dùng để hiển thị các key theo thứ tự cố định.

Trong ví dụ, `@Order` đặt trên phương thức `@Bean` là metadata để Spring sắp thứ tự các phần tử được tiêm vào `List`. Khi không khai báo thứ tự, đừng thiết kế logic phụ thuộc vào thứ tự được quan sát tình cờ. Nếu cần thứ tự xử lý bắt buộc, dùng `@Order`/`Ordered` rõ ràng và lựa chọn kiểu collection phù hợp. Thứ tự khởi tạo singleton là vấn đề khác, không do `@Order` quyết định.

## 6. Ba tình huống dễ nhầm và cách kiểm chứng

### 6.1. Nhầm `@Primary` với phép lọc

**Kỳ vọng sai:** Gắn `@Primary` cho `main` thì `List<Processor>` chỉ còn `main`.

**Hành vi đúng:** `List<Processor>` chứa tất cả bean khớp kiểu. `@Primary` áp dụng để giải quyết dependency đơn; nó không ràng buộc thành viên collection. Muốn chỉ một nhóm, dùng `@Qualifier` tại điểm tiêm.

### 6.2. Cho rằng qualifier phải là duy nhất

**Kỳ vọng sai:** Hai bean cùng `@Qualifier("fast")` là cấu hình không hợp lệ.

**Hành vi đúng:** Cùng qualifier là bình thường khi nhiều bean thuộc một nhóm. `@Qualifier("fast") List<Processor>` nhận cả hai. Chỉ khi yêu cầu `@Qualifier("fast") Processor oneFast` mà không có một lựa chọn duy nhất thì mới có nguy cơ `NoUniqueBeanDefinitionException` (thường được bọc trong lỗi tạo bean ở thời điểm khởi tạo context).

Để thử trên ví dụ trên, tạm thêm tham số sau vào phương thức `inspector`:

```java
@Qualifier("fast") Processor oneFast
```

Khi đó cả `fastOne` lẫn `fastTwo` đều là ứng viên; không có primary trong nhóm `fast` nên context khởi tạo thất bại. Đây là **đoạn thay đổi để thử lỗi**, không phải một phần của chương trình hoàn chỉnh đã chạy ở mục 5.

### 6.3. Cho rằng qualifier thắng primary mà không xét kiểu

**Kỳ vọng sai:** `@Qualifier("slow")` luôn chọn bean mang nhãn `slow`, dù bean ấy không triển khai kiểu cần tiêm.

**Hành vi đúng:** Bean phải đáp ứng **kiểu** và tiêu chí qualifier. Nếu điểm tiêm là `@Qualifier("slow") Processor selected`, chỉ bean kiểu `Processor` với qualifier phù hợp mới là ứng viên. Qualifier không ép Spring đưa một bean sai kiểu vào dependency.

## 7. Quy tắc thực hành khi mở rộng hệ thống

### Tiêm vào constructor

Ưu tiên dependency injection qua constructor khi đối tượng phụ thuộc là bắt buộc. Đặt `@Qualifier` trực tiếp trên tham số cần lọc để ý nghĩa hiển thị tại điểm sử dụng:

```java
// Minh họa constructor trong một bean do Spring quản lý.
final class Pipeline {
    private final List<Processor> fastProcessors;

    Pipeline(@Qualifier("fast") List<Processor> fastProcessors) {
        this.fastProcessors = List.copyOf(fastProcessors);
    }
}
```

Đây là đoạn minh họa ngắn, dùng kiểu `Processor` của ứng dụng hoặc khai báo lại kiểu tương ứng trong dự án thực tế. Để Spring tạo `Pipeline`, cần đăng ký lớp đó làm bean qua `@Component`/`@Bean`. Với một constructor duy nhất, Spring không đòi `@Autowired` trên constructor ấy.

### Thiết kế nhãn có ý nghĩa

Qualifier nên nói về **khả năng hay vai trò**, chẳng hạn `fast`, `audit`, `offline`. Tránh dùng nhãn chỉ để mã hóa tên implementation, vì việc đổi implementation có thể làm lộ chi tiết kỹ thuật vào các constructor. Nếu không muốn lặp chuỗi dễ gõ sai, có thể định nghĩa **custom qualifier annotation** (meta-annotated bằng `@Qualifier`) để gắn đặc tính nhóm ở điểm khai báo và điểm tiêm.

### Phân biệt nhóm bean với một bean kiểu collection

`@Qualifier("fast") List<Processor>` trong ví dụ nghĩa là **gộp các bean `Processor`** khớp nhãn `fast`. Đây là trường hợp thông dụng của multi-element injection. Nó cần được phân biệt với một bean có **chính kiểu `List<Processor>`** được tạo bằng `@Bean`. Đối với nhu cầu chọn một collection bean được định nghĩa sẵn, hãy khai báo kiểu generic đủ rõ, cân nhắc tiêm theo tên bằng `@Resource` khi phù hợp và kiểm tra độ phân giải thực tế của container; không áp dụng máy móc quy tắc “lọc từng Processor” cho mọi trường hợp bean kiểu collection.

### Điều kiện không có bean phù hợp

- `@Autowired` mặc định yêu cầu dependency thỏa mãn; với `List`/mảng/`Map` được autowire, mặc định cần có ít nhất một bean phần tử phù hợp. Nếu qualifier lọc ra không bean nào, quá trình tạo bean có thể thất bại với lỗi dependency không thỏa mãn.
- `@Autowired(required = false)` có thể làm một điểm tiêm field/method trở thành không bắt buộc; không nên suy ra rằng Spring sẽ tự đưa một `List.of()` vào mọi constructor.
- Nếu nghiệp vụ cho phép không có phần tử, cân nhắc thiết kế mặc định rỗng một cách chủ động hoặc dùng `ObjectProvider<Processor>` và truy vấn/stream có điều kiện. Cần làm rõ chính sách khi tập hợp trống trong thiết kế API.

### Khi nào cần thứ tự?

Nếu một nhóm handler được thực thi tuần tự, thứ tự có thể là nghiệp vụ quan trọng. Với `List<Handler>`, dùng `@Order` hoặc `Ordered` và kiểm thử thứ tự thật. Với `Set`/`Map`, không giả định rằng ý nghĩa nghiệp vụ được bảo đảm nhờ thứ tự lặp. `@Primary` không phải cơ chế sắp thứ tự các handler.

### Khi nào dùng `@Primary`?

Dùng `@Primary` nếu có một adapter mặc định và các adapter khác dùng cho trường hợp cụ thể. Ví dụ `@Primary` trên adapter bộ nhớ đệm mặc định làm `CacheAdapter` đơn không bị ambiguity, còn `@Qualifier("audit") List<CacheAdapter>` vẫn lấy nhóm audit độc lập. Nếu các hành vi đồng cấp đều cần dùng, một nhóm có qualifier rõ ràng thường hợp lý hơn việc cố chọn một primary.

## 8. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` ở dependency đơn | Có nhiều bean cùng kiểu và sau khi lọc vẫn mơ hồ | Thêm qualifier đủ cụ thể; hoặc khai báo một primary mặc định nếu đúng ngữ nghĩa |
| `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException` | Không có bean khớp kiểu và qualifier tại điểm tiêm bắt buộc | Kiểm tra đăng ký bean, kiểu return `@Bean`, qualifier ở cả hai phía, package scan |
| `@Qualifier("fast") List<...>` có ít phần tử hơn dự kiến | Bean thiếu qualifier, không khớp generic hoặc không phải autowire candidate | Kiểm tra kiểu phần tử/generic và metadata qualifier của từng bean |
| Map có key khác chuỗi qualifier | Key của `Map<String, T>` là **bean name** | Dùng key để định danh bean; nếu cần map theo nhãn nghiệp vụ, tự chuyển đổi với quy tắc xử lý trùng nhãn |
| Danh sách chạy sai thứ tự | Không khai báo `@Order`/`Ordered` hoặc dựa vào thứ tự ngoài hợp đồng | Khai báo thứ tự xử lý rõ ràng, xác nhận bằng test |
| Gắn nhiều `@Primary` nhưng dependency đơn vẫn lỗi | Primary không còn duy nhất trong tập ứng viên | Chỉ định một default rõ ràng hoặc dùng qualifier để phân biệt |
| Trộn nhầm bean `List<T>` với tập các bean `T` | Hai cấu hình collection khác nhau | Xác định cụ thể muốn lấy collection bean hay gom nhiều bean phần tử |

Không nên giải quyết lỗi bằng cách đổi tên tham số ngẫu nhiên cho khớp tên bean. Spring có cơ chế tên tham số/bean name khi phân giải dependency đơn, nhưng mục đích nhóm nên được biểu đạt bằng qualifier để code ổn định khi refactor.

## 9. Bài tập tự kiểm tra

1. Thêm bean `fastThree` có `@Qualifier("fast")` vào `Config`, không gắn primary. Dự đoán `fast`, `all` và `fastKeys` thay đổi ra sao. Kết quả đúng: nhóm `fast` tăng lên ba, `all` tăng lên năm, `Map` có thêm key `fastThree`; `preferred` vẫn là `main`.
2. Đặt `@Primary` lên cả `main` và `slow`. Dự đoán tiêm `Processor preferred`. Nếu cả hai vẫn là ứng viên và không có quy tắc phân giải khác, lỗi ambiguity xuất hiện; nhóm `fast` không vì thế thay đổi.
3. Giữ `@Primary` trên `main`, thêm `@Qualifier("fast")` vào `main` (bỏ `general`). `@Qualifier("fast") List<Processor>` sẽ có bao nhiêu bean? Đáp án: ba (`main`, `fastOne`, `fastTwo`). Primary vẫn **không loại** hai bean fast còn lại.
4. Vì sao `@Qualifier("fast") Processor selected` có thể lỗi trong khi `@Qualifier("fast") List<Processor> selected` chạy được? Vì điểm tiêm đơn phải xác định **một** bean, còn collection cố ý thu thập **nhiều** bean.
5. Có nên dùng `@Primary` để sắp xếp một pipeline nhiều handler? Không; dùng `@Order`/`Ordered` và biểu đạt luồng thực thi minh bạch.

## 10. Ghi nhớ và tài liệu gốc

- **Qualifier là bộ lọc**, nên một giá trị qualifier có thể gắn trên nhiều bean và chọn cả một nhóm.
- **Primary là ưu tiên chọn một bean**; nó không giới hạn số phần tử của `List`, `Set`, mảng hay `Map`.
- `@Qualifier` trên collection và `@Order` giải quyết hai nhu cầu độc lập: **ai được tham gia** và **thứ tự tham gia**.
- Cần phân biệt collection gồm các bean cùng kiểu với một bean mà bản thân nó có kiểu collection.

Tài liệu chính thức: [Spring — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html), [Spring — Fine-tuning with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html), [Spring — `@Primary` và `@Fallback`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html), [Spring — Using Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html).
