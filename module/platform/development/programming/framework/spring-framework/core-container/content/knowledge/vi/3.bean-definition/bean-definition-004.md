# Một lớp được đăng ký thành nhiều bean độc lập — Spring Framework Core Container

## 1. Mục tiêu và câu hỏi cốt lõi

Một **Java class không tương đương một Spring bean**. Trong Spring Core Container, bean được đăng ký dưới **tên định danh** và gắn với metadata xác định cách tạo, phạm vi tồn tại và các dependency. Do đó, **cùng một lớp Java có thể được dùng để tạo nhiều bean độc lập**, có tên riêng, cấu hình riêng và — với hai singleton được khởi tạo riêng — những object khác nhau.

Ví dụ: ứng dụng muốn đếm yêu cầu của hai kênh `alpha` và `beta`. Cả hai bộ đếm đều dùng class `Counter`, nhưng yêu cầu là:

- Trạng thái đếm của kênh alpha không ảnh hưởng trạng thái beta.
- Lấy lại bean `alphaCounter` trong cùng context cho cùng instance nếu nó là singleton.
- Lấy bean `betaCounter` cũng là singleton riêng, không phải alias của alpha.
- Service cần một bộ đếm cụ thể phải **chọn đúng bean**, không chỉ nói “tôi cần một `Counter`”.

Sau bài, bạn sẽ hiểu:

1. Khác biệt giữa **class**, **bean definition**, **bean name**, **alias**, **bean instance** và **scope**.
2. Cách khai báo nhiều `@Bean` cùng trả về một kiểu class.
3. Khi nào hai bean cùng kiểu là **hai object độc lập**, khi nào chỉ là **hai tên của một bean**.
4. Vì sao `getBean(Counter.class)` hoặc injection một `Counter` có thể bị mơ hồ khi nhiều candidate cùng kiểu.
5. Cách chọn cụ thể bằng `@Qualifier`, cách dùng `@Primary`, tên bean, hoặc collection injection đúng mục đích.
6. Cách đăng ký cùng class thành nhiều definitions bằng `BeanDefinitionBuilder` và tác động của singleton/prototype.
7. Chạy chương trình Java 17+ với Spring Framework, Maven, lệnh `javac`/`java` và stdout đối chiếu được.

**Phạm vi:** bài tập trung vào **nhiều bean độc lập xuất phát từ cùng một class**. Không cần Spring Boot, Spring MVC, database hoặc component scanning để minh họa cơ chế này.

## 2. Class và bean không có quan hệ 1–1

Ba khái niệm:

| Khái niệm | Đại diện | Ý nghĩa |
| --- | --- | --- |
| Java class | `Counter.class` | Định nghĩa kiểu và hành vi của mọi object `Counter` |
| Bean definition | Metadata có tên `alphaCounter` hoặc `betaCounter` | Quy tắc tạo/quản lý một bean ở trong container |
| Bean instance | Object do một definition cung cấp | Đối tượng thật được ứng dụng sử dụng |

Đối với cấu hình:

~~~java
@Bean("alphaCounter")
Counter alphaCounter() {
    return new Counter("alpha");
}

@Bean("betaCounter")
Counter betaCounter() {
    return new Counter("beta");
}
~~~

**Đây là snippet nằm trong lớp `@Configuration`**, chưa phải file Java độc lập. Hai factory methods trả về **cùng class `Counter`**, nhưng Spring có **hai bean definitions riêng** và các factory methods thực hiện hai lệnh `new` khác nhau.

~~~mermaid
flowchart TD
    C["Java class: Counter"] -.-> A["Bean definition: alphaCounter"]
    C -.-> B["Bean definition: betaCounter"]
    A --> IA["Instance A: Counter(alpha)"]
    B --> IB["Instance B: Counter(beta)"]
    IA -.->|class giống nhau| IB
~~~

Mũi tên nét đứt từ class sang definition chỉ **cùng kiểu Java**, không chỉ ra hai bean phụ thuộc nhau. Mỗi definition có thể có:

- Tên và alias riêng.
- Factory/constructor và constructor arguments riêng.
- Scope/lazy flag/initialization/destruction metadata riêng.
- Qualifier hoặc ưu tiên khác nhau.
- Instance được tạo riêng, nếu factory/constructor thực sự cung cấp object riêng.

**Điểm then chốt:** `singleton` trong Spring mặc định là **một object được container quản lý trên mỗi bean definition trong một container**, không phải một object duy nhất cho mọi bean có cùng class, và cũng không phải singleton toàn JVM.

### Hai singleton cùng class vẫn là hai singleton

Giả sử ta gọi:

~~~java
Counter a1 = context.getBean("alphaCounter", Counter.class);
Counter a2 = context.getBean("alphaCounter", Counter.class);
Counter b1 = context.getBean("betaCounter", Counter.class);
~~~

Nếu hai definitions đều là singleton và mỗi factory tạo riêng object, kết quả:

- `a1 == a2` → `true`: hai lần tra cứu **cùng bean name**.
- `a1 == b1` → `false`: hai bean **khác nhau**, dù cùng class.
- `a1.getClass() == b1.getClass()` → `true`: hai object thuộc **cùng Java class**.

Chú ý: một bean definition mang scope singleton không buộc **hai definitions khác nhau** trả object khác nhau nếu nhà phát triển cố ý cho hai factory cùng trả một reference dùng chung. Bài học “bean độc lập” yêu cầu **hai factory thực sự tạo object riêng**, không chỉ hai tên trong code.

## 3. Bean độc lập khác alias

Hai biến thể tưởng giống nhau nhưng kết quả khác:

**Hai definitions độc lập:**

~~~java
@Bean("alphaCounter")
Counter alphaCounter() {
    return new Counter("alpha");
}

@Bean("betaCounter")
Counter betaCounter() {
    return new Counter("beta");
}
~~~

Hai definitions có tên khác nhau. Với cấu hình trên, mỗi method khởi tạo instance khác.

**Một bean có nhiều tên (alias):**

~~~java
@Bean(name = {"alphaCounter", "alphaAlias"})
Counter alphaCounter() {
    return new Counter("alpha");
}
~~~

Trong snippet thứ hai, `alphaCounter` là **tên chính**, `alphaAlias` là **alias** của cùng bean. Lấy bằng hai tên dẫn tới **cùng bean**, không tạo một definition singleton thứ hai.

| Tình huống | Số bean definitions ứng dụng | Số object singleton từ các factory (khi tạo riêng như mã) |
| --- | ---: | ---: |
| Hai `@Bean` với hai tên khác nhau và hai `new Counter(...)` | 2 | 2 |
| Một `@Bean(name={"alphaCounter","alphaAlias"})` | 1 | 1 |
| Hai `@Bean` khác tên nhưng **cùng trả một instance có sẵn** | 2 | Có thể chỉ 1 object được chia sẻ |
| Một definition `prototype` lấy hai lần | 1 | Hai object, nếu mỗi lần tạo mới |

Không dùng tổng `context.getBeanDefinitionCount()` để đếm riêng hai counter của ứng dụng: Spring có thể đăng ký thêm infrastructure definitions. Hãy hỏi **tên bean cụ thể**, hoặc lấy danh sách bean theo kiểu rồi lọc/kiểm chứng.

### Tại sao hai method cùng tên không tạo hai bean?

Java không cho phép khai báo hai method trong cùng class chỉ khác kiểu trả về. Đối với nhiều beans cùng type, đặt **method name/bean name khác nhau**. Tên bean không nhất thiết trùng class name.

Nếu component scanning chỉ phát hiện một class `@Component`, mặc định bạn có một definition cho class ấy; muốn nhiều definitions cần đăng ký thêm một cách có chủ đích, chẳng hạn những `@Bean` methods khác nhau hoặc đăng ký bằng API. Tránh vô ý scan class rồi đồng thời đăng ký chính class đó thêm bằng `@Bean` nếu không muốn có nhiều ứng viên.

## 4. Dùng @Bean để tạo hai bean độc lập

Cấu hình chính:

~~~java
@Configuration(proxyBeanMethods = false)
public static class AppConfig {
    @Bean("alphaCounter")
    public Counter alphaCounter() {
        return new Counter("alpha");
    }

    @Bean("betaCounter")
    public Counter betaCounter() {
        return new Counter("beta");
    }

    @Bean
    public Dashboard dashboard(
            @Qualifier("betaCounter") Counter selected) {
        return new Dashboard(selected);
    }
}
~~~

Đây là **phần trích từ ví dụ runnable ở mục 6**, với `AppConfig` là static nested configuration class trong một top-level class.

- Cả hai method đầu **trả `Counter`**, nên Spring thấy hai candidates tương thích kiểu `Counter`.
- Hai bean được đăng ký theo tên riêng: `alphaCounter` và `betaCounter`.
- Spring gọi hai factory methods khi cần, mỗi method tạo một `Counter` với nhãn và trạng thái riêng.
- `@Qualifier("betaCounter")` trên tham số của method `dashboard(...)` yêu cầu chọn candidate phù hợp có qualifier/tên đó, thay vì bất kỳ `Counter` nào.
- `Dashboard` chỉ nhận `Counter` bằng constructor; không cần trực tiếp gọi `context.getBean(...)` trong logic nghiệp vụ.

**Tại sao `proxyBeanMethods = false` hợp lệ?** Các factory methods **không gọi trực tiếp lẫn nhau** để tạo dependency, mà dùng tham số được Spring resolve. Nếu một method trực tiếp gọi `alphaCounter()` ở chế độ này, đó là lời gọi Java thường và có thể tạo object mới **không phải bean singleton** tương ứng.

### Tính độc lập của trạng thái

Giả sử:

~~~java
Counter alpha = context.getBean("alphaCounter", Counter.class);
Counter beta = context.getBean("betaCounter", Counter.class);

System.out.println(alpha.hit()); // alpha:1
System.out.println(beta.hit());  // beta:1
System.out.println(alpha.hit()); // alpha:2
~~~

Nếu `Counter` giữ số lần gọi trong một field **instance** (không static), alpha đã đếm 2 trong khi beta mới đếm 1. Đây là dấu hiệu mạnh hơn việc chỉ có hai bean names: **đối tượng và trạng thái thật sự tách biệt**.

Trong mã chạy đầy đủ, ta dùng `AtomicInteger` để tăng bộ đếm thread-safe. Điều đó không đồng nghĩa mọi logic và toàn bộ trạng thái bean singleton đều tự động thread-safe; bản thân class vẫn phải được thiết kế đúng theo yêu cầu đồng thời.

## 5. Cách giải quyết mơ hồ khi có nhiều bean cùng type

Trong context có hai bean `Counter` mà không có `@Primary`:

~~~java
Counter counter = context.getBean(Counter.class);
~~~

**Đây là snippet minh họa về tình huống thất bại**. Lệnh tra cứu chỉ theo kiểu thường không chọn được một bean duy nhất và ném `NoUniqueBeanDefinitionException` khi có đúng hai ứng viên không phân giải được. Trong chương trình đầy đủ, ta bắt đúng exception đó chỉ để in một dòng chẩn đoán ổn định.

### Ba cách chọn chính

1. **Chỉ rõ tên tại điểm inject bằng `@Qualifier`**, ví dụ `@Qualifier("betaCounter") Counter selected`. Đây là cách thích hợp khi collaborator phải thuộc một kênh cụ thể.
2. **Đặt `@Primary` cho một bean**, khi phần lớn điểm injection đơn trị nên ưu tiên ứng viên này và có một mặc định hợp lý.
3. **Lấy bean bằng tên rõ ràng ở composition root**, ví dụ `context.getBean("alphaCounter", Counter.class)`. Không biến service nghiệp vụ thành service locator gọi context khắp nơi.

Ví dụ về `@Primary` **chỉ minh họa một cấu hình khác**:

~~~java
@Bean("alphaCounter")
@Primary
Counter alphaCounter() {
    return new Counter("alpha");
}
~~~

Khi có một candidate primary thích hợp và không có ràng buộc khác ưu tiên khác, injection theo kiểu có thể chọn alpha làm mặc định. Tuy nhiên, `@Primary` **không gộp các bean**, và `@Qualifier("betaCounter")` vẫn có thể chỉ định beta ở một điểm injection cụ thể.

**Không nên nói “cứ có hai bean cùng class là Spring chắc chắn lỗi”.** Spring phân giải theo nhiều quy tắc: qualifier, primary, khả năng match tên parameter/field và các thiết lập khác. Ví dụ type-only `getBean(Counter.class)` ở cấu hình bài này **cố ý không có quy tắc lựa chọn**, nên mới có lỗi mơ hồ.

### Nếu bài toán thật sự cần cả hai

Có thể inject:

~~~java
@Bean
public CounterReport counterReport(Map<String, Counter> counters) {
    return new CounterReport(counters);
}
~~~

Snippet trên **không độc lập** vì `CounterReport` chưa khai báo. Trong Spring, một collection/map injection phù hợp có thể nhận nhiều bean `Counter`, với map key thường là bean name. Đây là lựa chọn tốt cho plugin/strategy registry, **không phù hợp nếu service chỉ cần đúng một kênh xác định**.

Dùng `List<Counter>` hoặc `ObjectProvider<Counter>` khi hợp đồng thật sự cần nhiều candidates/truy xuất động; đừng dùng chúng chỉ để lẩn tránh cấu hình thiếu rõ ràng.

## 6. Chương trình Java 17+ hoàn chỉnh và output

Dùng Spring Framework **6.2.19** và JDK 17+ qua Maven. Đây là phiên bản ghim cho ví dụ, không phải khẳng định bản mới nhất. Spring Boot, database và web server đều không cần thiết.

Cấu trúc project:

~~~text
multiple-beans-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MultipleBeansDemo.java
~~~

### 6.1. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>multiple-beans-demo</artifactId>
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
                    <mainClass>demo.MultipleBeansDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven tự resolve các dependency transitively của `spring-context`. Khi chạy `javac` riêng, cần các Spring JAR trong classpath; không chỉ source Java mà đủ để compiler tự tìm Spring.

### 6.2. File `src/main/java/demo/MultipleBeansDemo.java`

~~~java
package demo;

import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class MultipleBeansDemo {
    private MultipleBeansDemo() {}

    public static final class Counter {
        private final String channel;
        private final AtomicInteger hits = new AtomicInteger();

        public Counter(String channel) {
            this.channel = channel;
        }

        public String hit() {
            return channel + ":" + hits.incrementAndGet();
        }

        public int count() {
            return hits.get();
        }
    }

    public static final class Dashboard {
        private final Counter selected;

        public Dashboard(Counter selected) {
            this.selected = selected;
        }

        public Counter counter() {
            return selected;
        }

        public String record() {
            return selected.hit();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("alphaCounter")
        public Counter alphaCounter() {
            return new Counter("alpha");
        }

        @Bean("betaCounter")
        public Counter betaCounter() {
            return new Counter("beta");
        }

        @Bean
        public Dashboard dashboard(
                @Qualifier("betaCounter") Counter selected) {
            return new Dashboard(selected);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            String[] counterNames =
                    context.getBeanNamesForType(Counter.class);
            Arrays.sort(counterNames);
            System.out.println("counterBeans=" +
                    String.join(",", counterNames));

            Counter alpha =
                    context.getBean("alphaCounter", Counter.class);
            Counter beta =
                    context.getBean("betaCounter", Counter.class);
            Dashboard dashboard = context.getBean(Dashboard.class);

            System.out.println("definitions=" +
                    (context.containsBeanDefinition("alphaCounter")
                     && context.containsBeanDefinition("betaCounter")));
            System.out.println("sameClass=" +
                    (alpha.getClass() == beta.getClass()));
            System.out.println("differentInstances=" + (alpha != beta));
            System.out.println("alphaSingleton=" +
                    (alpha == context.getBean("alphaCounter", Counter.class)));
            System.out.println("betaSingleton=" +
                    (beta == context.getBean("betaCounter", Counter.class)));

            System.out.println("alphaFirst=" + alpha.hit());
            System.out.println("betaFirst=" + beta.hit());
            System.out.println("alphaSecond=" + alpha.hit());
            System.out.println("alphaCount=" + alpha.count());
            System.out.println("betaCountBeforeDashboard=" + beta.count());

            System.out.println("dashboardUsesBeta=" +
                    (dashboard.counter() == beta));
            System.out.println("dashboardRecord=" + dashboard.record());
            System.out.println("betaCountAfterDashboard=" + beta.count());

            try {
                context.getBean(Counter.class);
                System.out.println("typeLookup=UNEXPECTED");
            } catch (NoUniqueBeanDefinitionException ex) {
                System.out.println("typeLookup=AMBIGUOUS");
            }
        }
    }
}
~~~

**Vì sao mã chạy độc lập:**

- Một `public top-level class` có đúng tên file `MultipleBeansDemo.java`.
- Các class `Counter`, `Dashboard`, `AppConfig` là nested static classes, nên không cần tạo file riêng.
- `@Configuration(proxyBeanMethods=false)` hợp lệ vì hai factory methods không gọi trực tiếp nhau; factory method `dashboard(...)` nhận bean nhờ `@Qualifier`.
- Trạng thái `hits` là **field instance**, mỗi `new Counter(...)` tạo riêng một `AtomicInteger`.
- `Arrays.sort(counterNames)` bảo đảm dòng danh sách tên bean có thứ tự ổn định, không phụ thuộc iteration order của container.
- Context được đóng khi rời `try-with-resources`, nhưng chương trình không gắn destroy callback in thêm dòng, nên số dòng stdout từ `main` được xác định như dưới đây.

### 6.3. Biên dịch và chạy bằng Maven

Tại thư mục `multiple-beans-demo`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Stdout chính xác do phương thức `main` in, gồm 15 dòng:**

~~~text
counterBeans=alphaCounter,betaCounter
definitions=true
sameClass=true
differentInstances=true
alphaSingleton=true
betaSingleton=true
alphaFirst=alpha:1
betaFirst=beta:1
alphaSecond=alpha:2
alphaCount=2
betaCountBeforeDashboard=1
dashboardUsesBeta=true
dashboardRecord=beta:2
betaCountAfterDashboard=2
typeLookup=AMBIGUOUS
~~~

Các lệnh kiểm tra version và log Maven/Spring nếu xuất hiện **không tính** vào 15 dòng do `main` trực tiếp in. Hai counter độc lập từ cùng class giúp nhìn rõ `alpha:2` trong khi `betaCountBeforeDashboard=1`.

### 6.4. Chạy trực tiếp bằng `javac` / `java`

Vì Java source import Spring, cần các JAR tương ứng trên compile và runtime classpath. Nhờ Maven tạo danh sách:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/MultipleBeansDemo.java
java -cp "out:$(cat classpath.txt)" demo.MultipleBeansDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/MultipleBeansDemo.java
java -cp "out;$deps" demo.MultipleBeansDemo
~~~

Unix dùng `:` ngăn các classpath entries, Windows dùng `;`. Cả hai chạy một `main` và in 15 dòng output ở trên. Không thể biên dịch với `javac` thiếu các dependencies mà source đang import.

## 7. Đọc stdout: những gì đã được chứng minh

| Output | Kết luận chính xác |
| --- | --- |
| `counterBeans=alphaCounter,betaCounter` | Có hai tên bean thuộc kiểu `Counter` sau khi sắp xếp; không nhầm với tổng số bean toàn context |
| `definitions=true` | Hai tên `alphaCounter` và `betaCounter` được đăng ký như bean definitions |
| `sameClass=true` | Hai object có cùng Java class |
| `differentInstances=true` | Hai bean trả về **hai reference khác nhau** |
| `alphaSingleton=true`, `betaSingleton=true` | Mỗi tên singleton được tra lại thành cùng reference |
| `alphaFirst=alpha:1`, `betaFirst=beta:1` | Mỗi bean có trạng thái counter bắt đầu độc lập |
| `alphaSecond=alpha:2`, `alphaCount=2` | Chỉ alpha đã tăng tới 2 |
| `betaCountBeforeDashboard=1` | Beta vẫn bằng 1 trước khi dashboard ghi |
| `dashboardUsesBeta=true` | `@Qualifier("betaCounter")` đã chọn chính bean beta |
| `dashboardRecord=beta:2` | Dashboard làm tăng trạng thái của beta, không phải alpha |
| `betaCountAfterDashboard=2` | Beta hiện đã đếm 2 |
| `typeLookup=AMBIGUOUS` | Lookup theo class `Counter` không xác định một candidate duy nhất ở cấu hình không `@Primary` |

Một sự kiện không được chứng minh chỉ bằng hai tên bean: rằng **object độc lập**. Ví dụ này kiểm tra rõ bằng `differentInstances=true` và các trạng thái đếm riêng; đó là khác biệt giữa “đăng ký nhiều tên” và “nhiều bean độc lập” thực sự.

## 8. Cùng class với nhiều bean definitions bằng API

Ngoài `@Bean`, bạn có thể **đăng ký hai bean definitions** cho cùng `Counter.class` bằng `BeanDefinitionBuilder` hoặc `RootBeanDefinition`. Ví dụ sau là **đoạn minh họa**, không phải toàn bộ file runnable; giả định `Counter` ở mục 6 có constructor nhận `String`:

~~~java
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.registerBeanDefinition("redCounter",
        BeanDefinitionBuilder.genericBeanDefinition(Counter.class)
                .addConstructorArgValue("red")
                .getBeanDefinition());

context.registerBeanDefinition("blueCounter",
        BeanDefinitionBuilder.genericBeanDefinition(Counter.class)
                .addConstructorArgValue("blue")
                .getBeanDefinition());

try (context) {
    context.refresh();
    Counter red = context.getBean("redCounter", Counter.class);
    Counter blue = context.getBean("blueCounter", Counter.class);
    System.out.println(red == blue); // false.
}
~~~

**Ý nghĩa:** cùng `Counter.class` nhưng hai definitions đăng ký dưới tên khác và có constructor argument khác; với scope singleton mặc định, Spring tạo một object trên mỗi definition, mỗi object được cấu hình riêng.

Đăng ký definitions **trước `refresh()`** là thời điểm rõ ràng nhất. Đăng ký thêm definitions hoặc sửa metadata khi những singleton khác đã được tạo có thể gây hành vi phức tạp; đừng coi đó là cách bình thường để đổi dependency cho một ứng dụng đang chạy.

**Đừng chạy snippet này ngay trong cấu hình demo chính** rồi vẫn đối chiếu danh sách chỉ có hai counter: khi có thêm red/blue trong cùng context, số ứng viên `Counter` tăng và các điều kiện lookup/type selection cũng thay đổi.

## 9. Scope: độc lập giữa definitions và tạo mới theo lần tra cứu

### Singleton mặc định

Hai definitions `alphaCounter` và `betaCounter` trong cùng context có cùng class và cùng scope singleton mặc định. Điều này nghĩa là:

- Mỗi definition có thể quản lý một instance riêng do factory của mình tạo.
- Lấy bean theo **cùng tên** nhiều lần trả cùng instance.
- Khác **tên definition** không có nghĩa chung một instance.
- Trạng thái mutable của mỗi object vẫn phải được thiết kế thread-safe nếu có truy cập đồng thời.

### Prototype

Nếu thay một definition bằng:

~~~java
@Bean("alphaCounter")
@Scope("prototype")
Counter alphaCounter() {
    return new Counter("alpha");
}
~~~

Đây là **snippet minh họa thay thế**, không thêm vào cùng config gốc khi đang đối chiếu stdout. Khi context yêu cầu bean prototype, Spring tạo instance mới theo yêu cầu; hai lần `getBean("alphaCounter")` có thể là hai object khác nhau **ngay cả với cùng một tên definition**. Vì thế:

| Cấu hình | So sánh lặp theo cùng tên | So sánh giữa hai tên |
| --- | --- | --- |
| Hai singleton được tạo riêng | Cùng reference | Khác reference |
| Một bean prototype | Mỗi lookup tạo object mới | Không phải tiêu chí chính để suy ra số definitions |
| Một bean singleton với alias | Cùng reference dưới tên chính/alias | Hai tên vẫn cùng bean |
| Hai definitions trả cùng object từ shared factory | Cùng reference theo mỗi definition | Có thể cùng reference dù definition khác |

Spring container không tự quản lý đầy đủ destruction của prototype sau khi giao object; nếu object giữ tài nguyên cần cleanup, owner phải có chiến lược xử lý phù hợp.

### Scope không đồng nghĩa với số class

Một class có thể được dùng trong nhiều bean definitions với scope khác nhau. Bạn có thể có một bean `Counter` singleton và một bean `Counter` prototype; việc **cùng class** không quyết định scope của từng definition.

Ngược lại, cùng một bean definition không nhất thiết tạo “một instance cho mỗi class”; container áp dụng scope được cấu hình. Vì thế luôn hỏi: **definition nào, tên nào, scope nào, factory nào?**

## 10. Đăng ký nhiều bean cùng kiểu và thiết kế API

Khi hợp lý:

- Hai datasource client cùng class nhưng trỏ tới hai cơ sở dữ liệu khác nhau.
- Hai HTTP API clients cùng class nhưng URL/credentials cấu hình khác nhau.
- Hai chiến lược gửi thông báo cùng class nhưng có channel/tenant settings riêng.
- Hai worker executors cùng class nhưng xử lý các loại công việc khác nhau.
- Hai caches cùng implementation nhưng namespace/dữ liệu lưu riêng.

Các ví dụ trên mang tính mô hình; cần cân nhắc transaction, pool, lifecycle và bảo mật tùy môi trường thực. Một class chung có thể biểu diễn **hợp đồng và hành vi giống nhau**, còn từng bean mang **cấu hình và trạng thái khác nhau**.

### Đặt tên bean có ý nghĩa

Tên `alphaCounter` và `betaCounter` dễ hiểu hơn `counter1`, `counter2` khi chúng đại diện kênh cụ thể. Nếu ứng dụng có nhiều bên thứ ba cấu hình bean, dùng `@Qualifier` rõ ràng hoặc custom qualifier phù hợp thay vì phụ thuộc vào tên tham số Java một cách tình cờ.

### Khi không nên tạo thêm bean

Không tạo nhiều bean chỉ vì có thể: nếu hai consumer thực sự chia sẻ một collaborator **stateless, thread-safe và có cấu hình giống nhau**, dùng chung một singleton có thể đơn giản và ít tài nguyên hơn. Ngược lại, nếu collaborator chứa trạng thái cho hai kênh riêng, chia bean rõ ràng giúp cô lập nhưng vẫn phải xét **concurrency, lifecycle và resource usage**.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `getBean(Counter.class)` thất bại | Hai candidates cùng type không có lựa chọn duy nhất | Dùng tên bean hoặc `@Qualifier`/`@Primary` đúng thiết kế |
| Injection một `Counter` nhận sai kênh | Dựa vào quy tắc tên/primary không đúng ý định | Chỉ định qualifier tường minh và test wiring |
| Tưởng hai alias là hai bean độc lập | Alias trỏ cùng bean definition | Đăng ký hai definitions khác nhau |
| Tưởng hai definitions luôn khác object | Hai factory methods có thể trả cùng shared object | Tạo object riêng, kiểm tra identity trong test |
| Dùng `@Bean` methods gọi trực tiếp nhau với `proxyBeanMethods=false` | Lời gọi Java thường có thể tạo object ngoài bean singleton | Khai báo dependency bằng tham số factory method |
| Hai bean cùng class dùng chung biến `static` | Trạng thái static thuộc class, không thuộc từng instance | Đặt state cần cô lập vào instance field |
| Singleton mutable không an toàn khi đa luồng | Nhiều caller dùng chung một bean | Dùng cấu trúc thread-safe/đồng bộ hoặc thay thiết kế state |
| Prototype được inject vào singleton nhưng muốn tự làm mới mỗi lượt | Dependency được resolve khi singleton tạo | Dùng `ObjectProvider<T>`/lookup theo lượt thật cần |
| Nhiều beans bị đăng ký vì `@Component` và `@Bean` cùng tồn tại | Đăng ký trùng không chủ đích | Rà nguồn đăng ký, chỉ giữ ứng viên mong muốn |
| `NoSuchBeanDefinitionException` | Bean name sai hoặc chưa đăng ký | Kiểm tra `@Bean`, configuration loading, package scan |
| `NoUniqueBeanDefinitionException` | Nhiều ứng viên và không có cách phân giải | Kiểm tra qualifier/primary/type; xem điểm injection |
| Context có ít/many definitions hơn dự kiến | Đếm toàn bộ infrastructure beans thay cho app beans | Kiểm tra danh sách theo type/tên cần thiết |
| Source Java compile báo thiếu Spring package | Thiếu Maven deps hoặc `javac -cp` | Sửa build/classpath trước khi chẩn đoán IoC |
| Test có lúc đúng lúc sai khi dùng state singleton | Test dùng chung context/bean mutable | Reset dữ liệu/test isolation phù hợp và tránh state không kiểm soát |

**Đọc lỗi đúng lớp:** lỗi `NoUniqueBeanDefinitionException` là lỗi **phân giải lựa chọn candidate**, không phải hai object có cùng class là bất hợp pháp trong Java. Bean names/qualifiers là công cụ để thiết kế quyết định lựa chọn rõ ràng.

## 12. Tự kiểm tra bằng bài tập và đáp án

**Bài 1.** Hai method `@Bean("one") Counter one()` và `@Bean("two") Counter two()` đều trả `new Counter(...)`. Cùng class có hai bean singleton độc lập được không?

**Đáp án:** Được. Hai names/definitions riêng và hai object được factory tạo riêng. Mỗi tên singleton lưu instance của chính nó.

**Bài 2.** `@Bean(name={"one","alias"})` tạo mấy bean độc lập?

**Đáp án:** Một bean có thêm alias; lookup hai tên trỏ tới cùng object với singleton. Không phải hai independent definitions.

**Bài 3.** `getBean(Counter.class)` gặp hai candidate, đều không `@Primary`, không selection metadata khác. Có tự động chọn một ngẫu nhiên không?

**Đáp án:** Không. Lookup chỉ theo type trong trường hợp đó báo không có lựa chọn duy nhất, ví dụ `NoUniqueBeanDefinitionException`. Chỉ rõ tên/qualifier hoặc một primary theo thiết kế.

**Bài 4.** Dashboard cần bean beta nhưng class field chỉ có kiểu `Counter`. Làm thế nào?

**Đáp án:** Inject `@Qualifier("betaCounter") Counter selected` ở constructor/factory parameter tương ứng, hoặc thiết kế qualifier riêng. Code domain không cần tra context bằng string.

**Bài 5.** Hai bean cùng class có field `static int counter`. Hai bean có thống kê độc lập không?

**Đáp án:** Không với field static ấy; static gắn với class và dùng chung. Muốn state riêng thì dùng instance fields (trong demo là `AtomicInteger hits`).

**Bài 6.** Đổi alpha thành `prototype`, lấy `getBean("alphaCounter")` hai lần, có giữ cùng reference không?

**Đáp án:** Theo scope prototype bình thường, mỗi lần được yêu cầu Spring tạo instance mới. Kỳ vọng identity sẽ khác, không còn đúng điều kiện singleton trong stdout gốc.

**Bài 7.** Hai beans dùng cùng một singleton shared object trả từ hai factory methods. Tên và definitions khác nhau thì reference có khác không?

**Đáp án:** Không nhất thiết. Tên/definitions độc lập không tự chứng minh object identity; nếu factory trả cùng reference thì hai lookups có thể trỏ cùng object. Đây chính là lý do kiểm chứng `alpha != beta` có ý nghĩa.

## 13. Checklist áp dụng

- [ ] Phân biệt class, bean definition, bean name, alias và bean instance.
- [ ] Hai bean cùng class cần hai definitions thực sự, không chỉ thêm alias.
- [ ] Factory methods tạo/cung cấp đúng instances và cấu hình riêng.
- [ ] Mỗi bean có tên mang ý nghĩa vai trò/kênh, không dùng số thứ tự vô nghĩa.
- [ ] Hiểu singleton theo bean definition trong cùng container.
- [ ] Biết rằng prototype tạo instance mỗi lần yêu cầu bean theo scope phù hợp.
- [ ] Khi có nhiều candidate cùng type, dùng qualifier/primary hoặc tên để giải quyết đúng mục đích.
- [ ] Không dựa vào việc Spring “chọn ngẫu nhiên” khi mơ hồ.
- [ ] Nếu cần tất cả candidates, cân nhắc collection/map injection với hợp đồng rõ.
- [ ] Không gọi trực tiếp các `@Bean` methods với `proxyBeanMethods=false` như cách lấy singleton.
- [ ] Không để state phân tách kênh trong static field.
- [ ] Kiểm tra identity và trạng thái riêng trong test, không chỉ đếm bean names.
- [ ] Chạy Java 17+ với Maven hoặc `javac`/`java` có Spring classpath, đối chiếu đúng **15 dòng stdout**.
- [ ] Không lạm dụng nhiều beans khi một singleton stateless có thể chia sẻ an toàn.

**Kết luận:** **Một class Java có thể đứng sau nhiều Spring beans.** Điều làm mỗi bean độc lập là **bean definition/name được đăng ký riêng cùng cách factory/scope cung cấp instance và trạng thái riêng**. Bean alias chỉ là tên bổ sung; dependency theo type có thể trở nên mơ hồ, vì vậy hãy thiết kế điểm injection rõ bằng `@Qualifier`/`@Primary` hoặc tên khi cần.

### Tài liệu chính thức

- [Spring Bean Overview and Names](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Spring JavaConfig — @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring Autowiring Collaborators and Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
