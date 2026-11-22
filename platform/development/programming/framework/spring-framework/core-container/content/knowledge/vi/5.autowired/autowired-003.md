# Quy tắc chọn khi có nhiều hàm khởi tạo — @Autowired trong Spring Framework

## 1. Vấn đề cần hiểu

Một lớp Java có thể **overload constructor**: khai báo các hàm khởi tạo cùng tên lớp nhưng khác danh sách tham số. Khi tự gọi `new`, **trình biên dịch Java** chọn overload dựa trên đối số bạn truyền. Khi **Spring tạo bean từ lớp đó**, container phải quyết định **constructor nào được dùng** và có thể phân giải những dependency nào để truyền vào.

Hai cơ chế khác nhau:

- **Java overload resolution:** ví dụ `new ReportService(tracer)` gọi constructor nhận `Tracer`, do biểu thức Java đã chỉ rõ đối số.
- **Spring constructor resolution:** ví dụ `context.getBean(ReportService.class)` (khi bean đã được đăng ký) có thể kích hoạt Spring chọn constructor dựa trên `@Autowired`, những ứng viên phù hợp, constructor mặc định và metadata của bean definition.

**Không có quy tắc “constructor dài nhất luôn thắng”.** Chỉ trong tình huống **nhiều constructor được đánh dấu `@Autowired(required=false)`**, Spring xét các constructor ứng viên và chọn constructor **có nhiều dependency nhất mà container có thể giải quyết**, theo chính sách autowiring. Nếu ứng viên không phù hợp và có default/primary constructor thích hợp, Spring có thể dùng nó. Quy tắc đó không đồng nghĩa lấy bất kỳ constructor dài nhất nào trong class.

Sau bài này, bạn sẽ:

1. Phân biệt constructor overload của Java và cơ chế Spring chọn constructor cho bean.
2. Giải thích trường hợp **chỉ một constructor không cần `@Autowired`**.
3. Hiểu ý nghĩa mặc định `@Autowired(required=true)`: chỉ **một** constructor trong cùng lớp được đánh dấu required.
4. Hiểu nhiều constructor cùng `@Autowired(required=false)`, **greedy satisfiable candidate** và fallback về constructor mặc định.
5. Biết điều gì xảy ra khi lớp có nhiều constructor nhưng **không đánh dấu `@Autowired`**.
6. Phân biệt **chọn constructor** với **chọn bean candidate** cho từng tham số (`@Primary`, `@Qualifier`, ambiguity).
7. Đối chiếu bằng project **Java 17+ / Spring Framework Core Container thuần**, Maven và các lệnh `javac`/`java` có stdout xác định.
8. Nhận biết lỗi và thiết kế constructor injection dễ đọc, dễ test, không lạm dụng nhiều overload.

**Phạm vi:** Chỉ tìm hiểu quy tắc chọn **constructor lúc Spring khởi tạo bean**, không cần Spring Boot, JPA, Lombok, Kotlin hoặc XML. Các trường hợp Java/Spring đặc biệt được ghi chú để tránh áp dụng sai một quy tắc vào mọi dạng bean registration.

## 2. Các tình huống trong một bảng

| Constructor của một class | Cách Spring thường xử lý |
| --- | --- |
| Chỉ có **một constructor** | Dùng constructor đó, kể cả không gắn `@Autowired`; dependency phải resolve được |
| Nhiều constructors, **một** gắn `@Autowired` mặc định `required=true` | Dùng constructor được đánh dấu; thiếu dependency bắt buộc gây lỗi, không chuyển tùy tiện sang constructor khác |
| Nhiều constructors cùng được gắn `@Autowired(required=false)` | Xét các ứng viên; chọn constructor với **nhiều dependency giải quyết được nhất** |
| Tất cả annotated candidates `required=false` đều không giải quyết được | Fallback về default/primary constructor **nếu có** |
| Nhiều constructors **không constructor nào gắn `@Autowired`**, có no-arg mặc định | Mặc định sử dụng constructor không tham số; không tự greedy chọn overload dài nhất |
| Nhiều constructors, không annotation, không constructor mặc định/primary thích hợp | Không nên mong Spring tự suy đoán; cần làm rõ constructor dùng để inject hoặc metadata tạo bean |
| Nhiều constructors với **hai annotation `@Autowired(required=true)`** | Cấu hình không hợp lệ; không được có hai required annotated constructors |
| Có một required annotated constructor **và** một annotated optional constructor | Không hợp lệ theo quy tắc annotation: required constructor phải là constructor annotated duy nhất |

> Trong bảng, *primary constructor* mang nghĩa một constructor chính được Spring nhận diện theo quy tắc/ngôn ngữ/metadata phù hợp; **không** nhầm với `@Primary` dùng để chọn **bean** giữa nhiều ứng viên.

Quy tắc constructor của Spring được mô tả trong JavaDoc `org.springframework.beans.factory.annotation.Autowired` và `AutowiredAnnotationBeanPostProcessor`. Chúng không yêu cầu mọi overload đều public; tuy nhiên trong bài dùng public constructors để mã dễ hiểu và không phụ thuộc vấn đề khả năng truy cập của module.

## 3. Trường hợp đơn giản: một constructor, không cần @Autowired

~~~java
@Component
final class SingleConstructorService {
    private final Tracer tracer;

    public SingleConstructorService(Tracer tracer) {
        this.tracer = java.util.Objects.requireNonNull(tracer);
    }
}
~~~

Đây là **snippet minh họa**: cần khai báo `Tracer` và import `@Component`. Trong Spring 4.3+ (bao gồm Spring Framework 6.2), nếu một bean class **chỉ có một constructor**, Spring có thể sử dụng constructor đó **mà không bắt buộc viết `@Autowired`**.

Lưu ý:

- Spring chỉ tự tạo/đưa dependency vào **bean mà nó quản lý**. Nếu `SingleConstructorService` không được đăng ký bằng component scan, `context.register(...)` hay bean definition phù hợp, annotation ở source không tự sinh instance.
- Không có bean `Tracer` phù hợp thì Spring **không tự truyền null** để tạo service hợp lệ; việc tạo bean thường thất bại.
- Java vẫn cho phép `new SingleConstructorService(tracer)` không có Spring: constructor injection vốn là kỹ thuật Java thuần.
- Nếu chỉ có một constructor và bạn thêm `@Autowired` thì hợp lệ, nhưng thường thừa cú pháp.
- Với một constructor có nhiều tham số, Spring sẽ cố giải quyết những dependency cần thiết. Cách hiểu “một constructor” **không làm mọi tham số tùy chọn**.

### @Autowired không phải dấu hiệu duy nhất của bean registration

Một class có constructor nhưng không phải bean sẽ không tự tham gia dependency injection. Ví dụ này:

~~~java
SingleConstructorService local =
        new SingleConstructorService(new ConsoleTracer());
~~~

là **manual wiring bằng Java**, không phải Spring DI. Nếu `ConsoleTracer` là một object Java bình thường và bạn không đăng ký nó, nó không biến thành managed Spring bean chỉ vì được truyền vào một constructor.

## 4. Nhiều constructor: một constructor @Autowired(required=true)

Mặc định của `@Autowired` là `required=true`. Viết:

~~~java
@Component
final class StrictService {
    private final Tracer tracer;

    public StrictService() {
        this.tracer = null;
    }

    @Autowired
    public StrictService(Tracer tracer) {
        this.tracer = java.util.Objects.requireNonNull(tracer);
    }
}
~~~

Đây là **snippet minh họa về quy tắc chọn**, không phải cấu trúc khuyến khích cho business service vì default constructor để lại trạng thái null. Trong bối cảnh Spring tạo bean:

- Constructor `StrictService(Tracer)` đã được đánh dấu **required**, nên Spring chọn nó làm constructor injection.
- Nếu context không có một `Tracer` thích hợp, việc tạo bean **thất bại**; Spring không tự chuyển sang `StrictService()` chỉ để tránh lỗi.
- Nếu context có đúng một `Tracer` phù hợp, Spring truyền nó vào constructor annotated.
- Việc Java vẫn có no-arg constructor **không biến required dependency thành optional**.

Trong thiết kế thực tế, nếu `Tracer` bắt buộc để service hoạt động, thường **chỉ giữ constructor nhận Tracer**; như vậy class Java thuần cũng không cho phép tạo instance không hợp lệ. Snippet ở đây cố tình có cả hai constructor để quan sát Spring chọn.

**Không được** gắn `@Autowired(required=true)` ở hai constructor trong cùng lớp. Đây là cấu hình mâu thuẫn; Spring không dùng thứ tự source code để “chọn đại” một constructor trong hai cái.

## 5. Nhiều constructor @Autowired(required=false): chọn ứng viên phù hợp

Mô hình:

~~~java
@Component
final class FlexibleService {
    private final String selection;

    public FlexibleService() {
        this.selection = "default";
    }

    @Autowired(required = false)
    public FlexibleService(Tracer tracer) {
        this.selection = "tracer";
    }

    @Autowired(required = false)
    public FlexibleService(Tracer tracer, Formatter formatter) {
        this.selection = "tracer+formatter";
    }

    String selection() {
        return selection;
    }
}
~~~

Đoạn này là **snippet**; cần hai kiểu `Tracer` và `Formatter` được đăng ký phù hợp. Spring xét những constructor annotated `required=false` như **các lựa chọn**, chứ không áp dụng semantics “tham số nullable” cho mỗi constructor.

| Bean collaborators hiện có | Constructor được chọn trong ví dụ | Giá trị `selection` |
| --- | --- | --- |
| Có một `Tracer` và một `Formatter` | `FlexibleService(Tracer, Formatter)` | `tracer+formatter` |
| Có `Tracer`, không có `Formatter` | `FlexibleService(Tracer)` | `tracer` |
| Không có `Tracer`, cũng không có `Formatter` | `FlexibleService()` | `default` |

Đây là trường hợp phổ biến của quy tắc **“constructor thỏa nhiều dependency nhất”**, nhưng có các điều kiện:

- Constructor dài hơn phải **satisfiable**: các tham số cần thiết phải được container giải quyết tương thích.
- Có nhiều constructor `@Autowired(required=false)`; chúng đều là **ứng viên**. Nếu nhiều candidates ngang mức ưu tiên/khả năng giải quyết, đừng thiết kế dựa vào một quy tắc “chọn ngẫu nhiên”; làm rõ bằng một constructor duy nhất hoặc annotation/metadata đúng.
- Một no-arg constructor đóng vai trò **fallback** nếu không ứng viên annotated nào có thể được giải quyết.
- `@Autowired(required=false)` ở constructor **không có nghĩa Spring sẽ truyền null cho bất kỳ tham số không có bean**, và cũng không có nghĩa Spring luôn tạo service theo constructor dài nhất.
- Spring có thể gặp lỗi khác với “không có candidate”, ví dụ một tham số có **nhiều beans không thể chọn duy nhất** hoặc bean dependency khởi tạo bị lỗi. Đừng coi mọi failure là lý do chắc chắn fallback.
- Nếu tình huống “không có Tracer” làm service vô nghĩa, thiết kế fallback `FlexibleService()` sẽ che cấu hình thiếu. Khi collaborator thực sự bắt buộc, tốt hơn chỉ giữ một constructor required.

### Không nhầm required=false ở constructor với optional field/method

Với setter hoặc field:

~~~java
@Autowired(required = false)
public void setMetrics(MetricsClient metrics) {
    this.metrics = metrics;
}
~~~

Spring có thể **bỏ qua injection point** nếu dependency không có (theo quy tắc phù hợp). Với **constructor alternatives**, Spring đang lựa chọn **một trong nhiều constructor** để tạo object; không có chuyện chạy tất cả constructors rồi “bỏ qua” tham số không sẵn có.

Nếu một dependency thật sự optional **ngay trong một constructor duy nhất**, có thể cân nhắc `Optional<T>`, `@Nullable` hoặc `ObjectProvider<T>` khi semantics phù hợp; điều đó là vấn đề **tham số/điểm injection**, không phải mặc định ưu tiên nhiều constructors.

## 6. Không gắn @Autowired khi có nhiều constructors

Xem ví dụ:

~~~java
@Component
final class UnannotatedService {
    private final String selected;

    public UnannotatedService() {
        this.selected = "default";
    }

    public UnannotatedService(Tracer tracer) {
        this.selected = "tracer";
    }
}
~~~

Đây là một class có **hai constructors và không constructor nào được gắn `@Autowired`**. Khi Spring được yêu cầu khởi tạo bean này bằng cơ chế constructor injection thông thường trong demo, nó dùng constructor mặc định **không tham số**, kể cả context đã có bean `Tracer`. Lý do: Spring không tự áp dụng quy tắc “greediest satisfiable” dành cho **nhiều annotated optional constructors** lên mọi constructor không annotation.

Nếu lớp có **nhiều constructors, không có no-arg và không có constructor chính mặc định/metadata phù hợp**, lựa chọn có thể không rõ và dẫn tới lỗi tạo bean. Đừng đoán rằng Spring chọn “cái đầu” hoặc “cái có ít tham số nhất”. Hãy:

1. Chọn **một constructor** có ý nghĩa và gắn `@Autowired` khi có nhiều overload.
2. Hoặc xóa overload không cần thiết để chỉ còn một constructor.
3. Hoặc dùng một `@Bean` factory method có logic và đối số rõ ràng.
4. Nếu có **thực sự** nhiều cấu hình khởi tạo hợp lệ, mới cân nhắc nhiều `@Autowired(required=false)` alternatives.

**Khác với trường hợp một constructor:** chỉ một constructor thì không cần annotation, nhưng khi bạn **thêm overload**, semantics chọn constructor có thể thay đổi. Đây là lý do refactor tưởng vô hại như thêm no-arg constructor cho framework khác có thể khiến Spring không còn inject dependency theo cách mong muốn.

## 7. Chọn constructor khác với chọn bean cho tham số

Spring trải qua hai câu hỏi tách biệt:

1. **Constructor nào được xem là phù hợp để gọi?**
2. **Mỗi tham số constructor đó nhận bean instance nào?**

Giả sử một constructor cần `Tracer`, nhưng context có:

~~~java
@Bean("fileTracer")
Tracer fileTracer() { return new FileTracer(); }

@Bean("consoleTracer")
Tracer consoleTracer() { return new ConsoleTracer(); }
~~~

Đây là **snippet chưa độc lập**, thiếu các kiểu và định nghĩa class. Nó minh họa hai bean cùng type. Spring phải phân giải một `Tracer` đơn trị từ nhiều candidate bằng các quy tắc phù hợp, có thể cần:

- `@Qualifier("consoleTracer")` trên tham số constructor cần chính bean đó.
- `@Primary` trên bean được dự kiến làm lựa chọn mặc định.
- Làm rõ bean name/type và điều kiện đăng ký để tránh tạo thừa candidate.
- Dùng `List<Tracer>`/`Map<String, Tracer>` hoặc `ObjectProvider<Tracer>` nếu hợp đồng thực sự muốn nhiều beans.

**Lưu ý:** `@Primary` chọn **bean candidate**, không phải chọn “constructor chính” theo overload. Ngược lại `@Autowired` trên constructor giúp Spring xác định constructor được phép dùng, nhưng **không giải quyết thay mọi ambiguity giữa các beans của cùng kiểu**.

Ví dụ constructor rõ ràng:

~~~java
@Autowired
public DeliveryService(
        @Qualifier("consoleTracer") Tracer tracer) {
    this.tracer = java.util.Objects.requireNonNull(tracer);
}
~~~

Snippet này cần khai báo `DeliveryService` đầy đủ và đúng import. Trong chương trình demo chính ta cố ý chỉ có **tối đa một bean trên mỗi type** để kết quả chọn constructor không phụ thuộc qualifier, @Primary hay ambiguity.

### Bean lỗi khi đang được tạo cũng là vấn đề khác

Nếu container biết một `Tracer` nhưng factory method tạo Tracer lại ném exception, đó không phải đơn thuần là “không có bean Tracer”. Spring có thể ném `BeanCreationException` và các exception wrapper khác. Không mặc nhiên dùng constructor fallback để giấu lỗi khởi tạo thực sự của dependency.

## 8. Ví dụ Java 17+ hoàn chỉnh: sáu trường hợp chọn constructor

Demo dùng **Spring Framework 6.2.19** từ Maven và **JDK 17+**. Version được ghim để tái lập, không tuyên bố mới nhất. Chương trình mở các Spring contexts **độc lập** để chứng minh ba lựa chọn của class flexible, một constructor duy nhất không annotation, hai constructors không annotation và required constructor.

### 8.1. Cấu trúc

~~~text
autowired-constructor-selection/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ConstructorSelectionDemo.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>autowired-constructor-selection</artifactId>
    <version>1.0.0</version>

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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.ConstructorSelectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Module `spring-context` kéo theo các dependency của Spring Core Container. Maven cần kết nối repository nếu artifact chưa nằm trong cache. Đừng chỉ copy `spring-context.jar` rồi hy vọng có đủ classpath để `javac` và `java` chạy.

### 8.3. File src/main/java/demo/ConstructorSelectionDemo.java

~~~java
package demo;

import java.util.Objects;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.stereotype.Component;

public final class ConstructorSelectionDemo {
    private ConstructorSelectionDemo() {}

    public interface Tracer {}
    public interface Formatter {}

    public static final class ConsoleTracer implements Tracer {
        public ConsoleTracer() {}
    }

    public static final class PlainFormatter implements Formatter {
        public PlainFormatter() {}
    }

    public interface Choice {
        String selected();
    }

    // Nhiều candidates: cả hai overload đều required=false.
    @Component
    public static final class FlexibleClient implements Choice {
        private final String selection;

        public FlexibleClient() {
            this.selection = "default";
        }

        @Autowired(required = false)
        public FlexibleClient(Tracer tracer) {
            Objects.requireNonNull(tracer);
            this.selection = "tracer";
        }

        @Autowired(required = false)
        public FlexibleClient(Tracer tracer, Formatter formatter) {
            Objects.requireNonNull(tracer);
            Objects.requireNonNull(formatter);
            this.selection = "tracer+formatter";
        }

        @Override
        public String selected() {
            return selection;
        }
    }

    // Một constructor duy nhất: không cần @Autowired.
    @Component
    public static final class SingleClient implements Choice {
        private final Tracer tracer;

        public SingleClient(Tracer tracer) {
            this.tracer = Objects.requireNonNull(tracer);
        }

        @Override
        public String selected() {
            return tracer == null ? "UNEXPECTED" : "tracer";
        }
    }

    // Hai constructors không annotation: default được dùng.
    @Component
    public static final class UnannotatedClient implements Choice {
        private final String selection;

        public UnannotatedClient() {
            this.selection = "default";
        }

        public UnannotatedClient(Tracer tracer) {
            Objects.requireNonNull(tracer);
            this.selection = "tracer";
        }

        @Override
        public String selected() {
            return selection;
        }
    }

    // Một constructor annotated mặc định required=true.
    @Component
    public static final class RequiredClient implements Choice {
        private final String selection;

        public RequiredClient() {
            this.selection = "default";
        }

        @Autowired
        public RequiredClient(Tracer tracer) {
            Objects.requireNonNull(tracer);
            this.selection = "required-tracer";
        }

        @Override
        public String selected() {
            return selection;
        }
    }

    private static String choose(
            Class<? extends Choice> beanClass,
            boolean hasTracer, boolean hasFormatter) {

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {

            if (hasTracer) {
                context.registerBean(Tracer.class, ConsoleTracer::new);
            }
            if (hasFormatter) {
                context.registerBean(Formatter.class, PlainFormatter::new);
            }

            context.register(beanClass);
            context.refresh();
            return context.getBean(beanClass).selected();
        }
    }

    public static void main(String[] args) {
        System.out.println("flexibleBoth=" +
                choose(FlexibleClient.class, true, true));
        System.out.println("flexibleTracerOnly=" +
                choose(FlexibleClient.class, true, false));
        System.out.println("flexibleNone=" +
                choose(FlexibleClient.class, false, false));

        System.out.println("singleNoAnnotation=" +
                choose(SingleClient.class, true, false));

        System.out.println("multipleNoAnnotation=" +
                choose(UnannotatedClient.class, true, false));

        System.out.println("requiredPresent=" +
                choose(RequiredClient.class, true, false));

        try {
            choose(RequiredClient.class, false, false);
            System.out.println("requiredMissing=UNEXPECTED");
        } catch (BeansException expected) {
            System.out.println("requiredMissing=REJECTED");
        }
    }
}
~~~

**Vì sao ví dụ rõ và không cần component scanning:**

- Chỉ có **một public top-level class** `ConstructorSelectionDemo`; các class phụ là `public static` nested classes. Tên file/package trùng đường dẫn.
- `AnnotationConfigApplicationContext()` tạo context trống/chưa refresh, rồi `registerBean(Tracer.class, ...)` và `registerBean(Formatter.class, ...)` có chủ đích trước `refresh()`.
- `context.register(beanClass)` trực tiếp đăng ký đúng class để Spring tạo. Mỗi lần `choose(...)` dùng **một context mới** nên không lẫn bean definitions/candidates giữa các thử nghiệm.
- `ConsoleTracer` và `PlainFormatter` có constructor public không tham số; method references `ConsoleTracer::new` và `PlainFormatter::new` là `Supplier` hợp lệ cho bean registration.
- `FlexibleClient` có hai overload annotated `required=false` và constructor mặc định. Khi hai dependencies có mặt, constructor nhận hai tham số được chọn; chỉ Tracer thì nhận một; thiếu cả hai thì fallback no-arg.
- `SingleClient` có một constructor không annotation và một `Tracer` được đăng ký; Spring vẫn inject.
- `UnannotatedClient` có hai constructors không annotation; với no-arg available, Spring chọn no-arg chứ không greedy chọn Tracer.
- `RequiredClient` có một constructor annotated mặc định required=true. Khi Tracer thiếu, Spring không dùng no-arg làm fallback mà fail; demo bắt `BeansException` để in kết quả kiểm chứng.
- Không sử dụng logic random, system time, reflection output, iteration order hay identity hash trong stdout.
- `try-with-resources` đóng mỗi context do ứng dụng tạo. Ở case deliberately failing refresh, framework có thể ghi cảnh báo/exception detail trên **stderr/logs**; ví dụ chỉ xác định chính xác **các dòng do `System.out.println` của main phát ra**.

### 8.4. Chạy bằng Maven

Trong thư mục `autowired-constructor-selection`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Đúng 7 dòng stdout do mã ứng dụng in (không tính thông tin tool/framework):**

~~~text
flexibleBoth=tracer+formatter
flexibleTracerOnly=tracer
flexibleNone=default
singleNoAnnotation=tracer
multipleNoAnnotation=default
requiredPresent=required-tracer
requiredMissing=REJECTED
~~~

Lệnh `java -version`, `mvn -version` và output log của Spring có thể khác theo máy; không phải bảy dòng `System.out.println(...)` được kiểm tra ở trên.

### 8.5. Chạy bằng javac/java

Vì mã import Spring, phải có Spring API/dependencies transitively trong classpath. Đầu tiên dùng Maven tạo file:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

Linux/macOS (bash/zsh):

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/ConstructorSelectionDemo.java
java -cp "out:$(cat classpath.txt)" demo.ConstructorSelectionDemo
~~~

Windows PowerShell:

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/ConstructorSelectionDemo.java
java -cp "out;$deps" demo.ConstructorSelectionDemo
~~~

Trên Unix, classpath entries ngăn bằng dấu `:`; Windows dùng dấu `;`. Cả hai lệnh chạy cùng `main` và các trường hợp kiểm thử giống nhau. Nếu `javac` báo `package org.springframework... does not exist`, kiểm tra dependency/classpath trước khi kết luận quy tắc constructor resolution có lỗi.

## 9. Diễn giải từng dòng stdout

| Dòng | Điều được chứng minh |
| --- | --- |
| `flexibleBoth=tracer+formatter` | Hai optional annotated candidates đều có khả năng resolve; Spring dùng overload nhận hai dependencies |
| `flexibleTracerOnly=tracer` | Overload hai tham số thiếu Formatter; Spring chọn overload một tham số có thể giải quyết |
| `flexibleNone=default` | Không overload annotated nào thỏa; Spring dùng constructor mặc định |
| `singleNoAnnotation=tracer` | Chỉ một constructor nên không yêu cầu `@Autowired` |
| `multipleNoAnnotation=default` | Nhiều overload không annotation với no-arg: không greedy chọn overload nhận Tracer |
| `requiredPresent=required-tracer` | `@Autowired` required đã xác định constructor và dependency có mặt |
| `requiredMissing=REJECTED` | Required constructor thiếu dependency; Spring không lặng lẽ dùng no-arg fallback |

**Không suy từ kết quả này rằng Spring bao giờ cũng lấy nhiều tham số hơn**. Thử nghiệm cố ý đăng ký đúng một bean trên mỗi type, tách context và không dùng cấu hình bean factory bất thường. Các trường hợp có constructor overload ngang điểm, parameter names, qualifiers, beans primary, inheritance hoặc nhiều argument không rõ type cần đánh giá dựa trên cấu hình thực.

## 10. Các điểm dễ nhầm ngoài quy tắc chính

### 10.1. @Autowired trên constructor và @Bean factory method

Một đoạn JavaConfig:

~~~java
@Bean
ReportService reportService(Tracer tracer) {
    return new ReportService(tracer);
}
~~~

Đây là **snippet minh họa**, cần `ReportService`/`Tracer` và class config tương ứng. Spring resolve **tham số factory method** `Tracer`; lời gọi `new ReportService(tracer)` trong method là **lời gọi Java trực tiếp** tới overload được viết. Khi BeanDefinition yêu cầu factory method, không thể mặc nhiên dùng quy tắc chọn constructors cho class kết quả giống như khi đăng ký trực tiếp class để Spring instantiate.

Điều này quan trọng khi debug: đôi lúc developer nhìn annotations trên constructor của `ReportService` nhưng thực tế bean được tạo qua một `@Bean` factory method đang tự gọi constructor khác. Hãy xem **đường đăng ký và factory thực tế**, không chỉ nhìn class.

### 10.2. required=false không phải null injection

Với hai constructor `(Tracer)` và `(Tracer, Formatter)` có `@Autowired(required=false)`, khi thiếu Formatter thì Spring thử constructor phù hợp **ít tham số hơn**. Điều đó khác `new FlexibleClient(tracer, null)`. Bạn vẫn nên validate constructor arguments theo invariant Java của chính class.

Nếu không muốn service chạy khi thiếu Formatter, đánh dấu optional chỉ để khỏi báo lỗi là quyết định thiết kế sai; hãy giữ dependency bắt buộc và fail-fast.

### 10.3. @Autowired ở tham số constructor

Mặc dù annotation có `ElementType.PARAMETER`, tài liệu Spring Core lưu ý rằng việc đặt riêng `@Autowired` lên **parameter** không phải cơ chế thông thường để chọn constructor. Cách rõ ràng là đặt `@Autowired` lên **constructor**, và đặt `@Qualifier` hoặc `@Value` lên **parameter** khi cần chỉ định bean/value.

Đây là phân biệt quan trọng khi một class có nhiều overload: đừng viết annotation ở một parameter rồi mong Spring tự hiểu constructor nào là required.

### 10.4. Các tham số dạng Optional, @Nullable và provider

Một single constructor đôi khi có dependency tùy chọn thật sự:

~~~java
public ReportService(
        Tracer tracer,
        java.util.Optional<MetricsClient> metrics) {
    this.tracer = java.util.Objects.requireNonNull(tracer);
    this.metrics = java.util.Objects.requireNonNull(metrics);
}
~~~

**Snippet minh họa**, không phải source độc lập. `Optional<MetricsClient>` cho phép thể hiện absence một cách tường minh khi Spring resolve injection point tương ứng; cũng có thể dùng `@Nullable`/provider theo nhu cầu. Không vì thế mà mọi dependency nên optional — với collaborator bắt buộc, constructor injection rõ và fail-fast dễ kiểm soát hơn.

Khi chọn giữa một constructor có `Optional<T>` và nhiều `@Autowired(required=false)` constructors, ưu tiên thiết kế API đơn giản, nêu rõ trạng thái hợp lệ và kiểm thử được ngay bằng Java thuần.

### 10.5. Không coi mọi lỗi thành “fallback”

Nếu dependency có hai candidate mơ hồ, tự constructor được chọn có thể thất bại khi resolve tham số. Nếu một bean dependency được tạo nhưng constructor/initializer ném exception, đó là lỗi tạo bean thật. Spring **không bảo đảm** “có lỗi ở overload dài thì chắc chắn sử dụng overload ngắn và ứng dụng vẫn đúng”. Phải xác định loại lỗi theo `Caused by`, candidate set và constructor đã xét.

### 10.6. Các phiên bản/công cụ tạo constructor

Lombok có thể sinh thêm constructor mà source Java trước khi compile không thể hiện như bạn tưởng; Java records có constructor canonical riêng. Khi dùng Lombok, records, Kotlin hoặc code generation, hãy kiểm tra **constructors thực sự có trong bytecode** và quy tắc tương ứng. Ví dụ thuần Java 17 trong bài tránh các yếu tố đó để chỉ quan sát Spring `@Autowired`.

## 11. Các lỗi thực tế và hướng xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Cách chẩn đoán/sửa |
| --- | --- | --- |
| Spring dùng no-arg dù đã có overload nhận collaborator | Nhiều constructors không `@Autowired`, default có sẵn | Giữ một constructor hoặc annotate constructor dự kiến |
| `UnsatisfiedDependencyException` khi startup | Constructor required cần bean chưa đăng ký | Kiểm tra type, candidate, registration và qualifier |
| `NoSuchBeanDefinitionException` trong nguyên nhân | Không có bean tương thích | Thêm bean config hoặc chỉnh dependency contract |
| `NoUniqueBeanDefinitionException` | Nhiều bean cùng type, không chọn được candidate | `@Qualifier`/`@Primary` hoặc sửa cấu hình |
| `BeanCreationException` | Factory/constructor/initializer của collaborator ném lỗi | Đọc `Caused by`; sửa logic/giá trị cấu hình |
| Exception về nhiều required constructors | Nhiều constructor gắn `@Autowired` mặc định true | Chỉ một required hoặc tất cả optional candidates theo thiết kế |
| Optional overload “bị bỏ qua” | Constructor đó không thể resolve đầy đủ parameters | Xác minh từng bean type; kiểm tra overload được Spring chọn |
| Không có constructor mặc định và không annotation | Spring không có lựa chọn hợp lệ rõ ràng | Annotate constructor hoặc tách thành một constructor |
| Thêm no-arg gây thay đổi wiring | Một class trước chỉ một constructor, sau thành nhiều overload | Viết test startup, quyết định rõ constructor dùng |
| Service có object nhưng thiếu collaborator | Constructor fallback cho phép trạng thái không hợp lệ | Không cung cấp fallback sai; require necessary dependencies |
| Sử dụng `@Primary` để “chọn constructor” | Nhầm bean candidate với overload choice | `@Primary` chọn bean theo type, constructor cần `@Autowired` phù hợp |
| Unit test gọi `new` chọn overload khác Spring | Caller Java gọi constructor rõ ràng, Spring chọn theo metadata | Kiểm tra cả unit tests và Spring wiring tests |
| `javac` báo thiếu Spring | Classpath/dependency build thiếu | Kiểm tra Maven pom và `-cp` |
| Không thấy lỗi khi bean @Lazy | Instantiation có thể bị trì hoãn | Kiểm thử `getBean`/flow thực và thời điểm tạo |

### Checklist debug theo thứ tự

1. **Bean thực sự được tạo theo đường nào?** Class registration/component scanning hay method `@Bean` trả object đã `new`?
2. **Class có bao nhiêu constructors?** Có constructor mặc định, synthetic/generated hay overload mới được thêm?
3. **Annotation nằm ở đâu?** `@Autowired` trên constructor nào, `required` true hay false?
4. **Container có những beans nào?** Mỗi tham số có candidate phù hợp không? Có hơn một candidate cần qualifier không?
5. **Constructor ứng viên được chọn là gì?** Dựa vào rules và startup logs/exception chain; không chỉ nhìn số tham số.
6. **Object có trạng thái hợp lệ không?** Constructor fallback có bỏ qua dependency thực sự cần thiết?
7. **Có tests chống regression không?** Một thay đổi constructor signature không nên âm thầm đổi wiring của service.
8. **Kết luận và đơn giản hóa:** nếu overload phức tạp chỉ để hỗ trợ DI, cân nhắc một constructor required rõ và dùng factory cho các case khác.

## 12. Kiểm thử các quy tắc với ít giả định

Bài demo kiểm tra qua stdout, nhưng một dự án nghiêm túc nên có:

- **Unit test Java:** gọi trực tiếp từng overload dự kiến, kiểm tra `Objects.requireNonNull` và invariant; không cần Spring.
- **Spring context test:** tạo context chỉ đăng ký các bean cần thiết, lấy service, kiểm tra đường constructor đã dùng (thí dụ một property enum/string chỉ phục vụ test).
- **Negative test:** thiếu collaborator required thì context fail, **không rơi vào default**.
- **Ambiguity test:** thêm hai Tracer candidates có chủ đích để xác minh qualifier/primary, không kết luận từ exception message nguyên văn.
- **Factory method test:** kiểm tra đường `@Bean` có tự gọi constructor định sẵn hay container instantiate trực tiếp.
- **Regression test khi thêm overload:** một test chỉ bảo đảm Java compile không đủ để phát hiện wiring thay đổi.

Không dùng Java `assert` mặc định làm kiểm tra bắt buộc nếu không bật `-ea`. Dùng assertions của test framework hoặc kiểm tra rồi ném exception. Cũng không khóa test vào toàn bộ stack trace vì thông điệp, thứ tự logs và wrapper có thể thay đổi theo phiên bản.

## 13. Bài tập và đáp án

**Bài 1.** Class chỉ có constructor `Service(Tracer tracer)` không `@Autowired`. Spring Framework 6 có sử dụng constructor đó không?

**Đáp án:** Có, nếu class đã đăng ký là Spring bean và một dependency phù hợp giải quyết được. Một constructor duy nhất không cần annotation.

**Bài 2.** Có constructor mặc định và constructor `Service(Tracer)` gắn `@Autowired` mặc định. Context không có Tracer. Spring dùng mặc định không?

**Đáp án:** Không theo quy tắc required constructor. Spring không bỏ qua một required annotated constructor chỉ để chọn no-arg; bean creation thất bại.

**Bài 3.** Có ba constructors: mặc định, `Service(Tracer)` required=false và `Service(Tracer, Formatter)` required=false. Context chỉ có Tracer. Chọn gì?

**Đáp án:** Chọn `Service(Tracer)` vì giải quyết được, còn overload dài hơn thiếu Formatter.

**Bài 4.** Nếu context có cả Tracer và Formatter thì sao?

**Đáp án:** Chọn overload hai tham số trong ví dụ, vì đó là annotated candidate thỏa nhiều dependencies nhất.

**Bài 5.** Nếu context không có cả hai dependencies và có default constructor?

**Đáp án:** Khi không có annotated candidates `required=false` nào có thể giải quyết, fallback về default constructor nếu có.

**Bài 6.** Hai constructors không annotation, một no-arg và một `Service(Tracer)`, context có Tracer. Có luôn dùng overload nhận Tracer không?

**Đáp án:** Không. Theo cơ chế constructor selection thông thường, default được dùng; đừng áp dụng nhầm quy tắc của nhiều `required=false` annotated candidates.

**Bài 7.** Có hai Tracer beans và một constructor cần Tracer. `@Primary` xử lý cái gì?

**Đáp án:** Chọn **bean Tracer** mặc định cho injection point khi phù hợp, không trực tiếp chọn constructor overload. Có thể dùng `@Qualifier` để rõ hơn.

**Bài 8.** `@Autowired(required=false)` trên constructor có nghĩa mọi tham số có thể null không?

**Đáp án:** Không. Với nhiều constructors annotated, nó cho phép constructor là một ứng viên tùy điều kiện, không phải lệnh inject null vào mọi tham số không có bean.

**Bài 9.** Bean được tạo trong method `@Bean service() { return new Service(...); }`. Ai chọn overload?

**Đáp án:** Lời gọi Java `new Service(...)` trong factory method chỉ rõ overload dựa trên đối số; Spring không nhất thiết tự chọn constructor khác của object trả về theo quy tắc class registration.

## 14. Checklist áp dụng

- [ ] Biết một constructor duy nhất có thể hoạt động không `@Autowired`.
- [ ] Với nhiều constructors, quyết định rõ cái nào dùng cho managed bean.
- [ ] Không gắn `@Autowired(required=true)` ở nhiều constructors.
- [ ] Nếu có nhiều `@Autowired(required=false)`, hiểu **greediest satisfiable candidate**.
- [ ] Khi thiếu các candidates tùy chọn, chỉ dùng default fallback nếu trạng thái class vẫn hợp lệ.
- [ ] Không coi `required=false` là cho phép inject null bừa bãi.
- [ ] Không áp dụng quy tắc greedy cho nhiều constructors **không annotation**.
- [ ] Phân biệt constructor choice với bean candidate resolution/`@Qualifier`/`@Primary`.
- [ ] Biết kiểm tra actual registration path: bean class vs `@Bean` factory method.
- [ ] Không biến dependency nghiệp vụ bắt buộc thành tùy chọn chỉ để startup thành công.
- [ ] Có test cho cả case đầy đủ, thiếu một dependency, thiếu mọi dependency và required failure.
- [ ] Kiểm tra constructor được code generation/record/framework khác tạo ra khi cần.
- [ ] Chạy Java 17+ bằng Maven hoặc javac/java với Spring classpath và đối chiếu **7 dòng stdout**.
- [ ] Khi lỗi, đọc bean name, constructor candidates và `Caused by` trước khi sửa.
- [ ] Ưu tiên **một constructor rõ ràng** cho các mandatory dependencies ở phần lớn business services.

**Kết luận:** `@Autowired` không phải chỉ dấu “Spring cứ chọn constructor dài nhất”. Spring **ưu tiên constructor required nếu được chỉ định**, **chọn overload có nhiều dependency có thể thỏa nhất** trong tập các constructor `required=false`, **fallback** về default khi không ứng viên nào phù hợp và điều kiện cho phép, và **dùng constructor duy nhất** kể cả khi thiếu annotation. Nắm rõ registration path và cách resolve bean candidates giúp bạn thiết kế DI **dễ dự đoán và fail-fast đúng nơi**.

### Tài liệu Spring chính thức

- [Spring Framework 6.2 — @Autowired JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/annotation/Autowired.html)
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [AutowiredAnnotationBeanPostProcessor API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/annotation/AutowiredAnnotationBeanPostProcessor.html)
- [Spring Java Configuration / @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
