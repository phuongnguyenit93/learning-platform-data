# Classloader cơ sở và classloader restart trong Spring Boot DevTools

## 1. Tại sao DevTools cần hai classloader?

Khi phát triển ứng dụng Java, cách khởi động lại thông thường là dừng JVM rồi chạy lại. Nếu mỗi lần sửa một class mà phải nạp lại Spring Framework, thư viện logging, JSON, database driver và hàng trăm JAR khác, vòng lặp sửa–biên dịch–chạy có thể khá chậm.

**Spring Boot DevTools** giải quyết một phần bài toán này bằng kỹ thuật **restart với hai classloader**:

- **Base classloader (classloader cơ sở):** giữ những class ít thay đổi, thường là các thư viện phụ thuộc được đóng gói thành JAR.
- **Restart classloader (classloader khởi động lại):** nạp những class đang được phát triển, thường là class nằm trong thư mục output của dự án đang mở.

Khi có một thay đổi trên classpath cần restart, Spring Boot DevTools có thể **đóng application context cũ, loại bỏ restart classloader cũ và tạo một restart classloader mới**. Các class đã được nạp vào base classloader không cần được nạp lại cùng cách như khi JVM mới khởi động.

```text
                    Một JVM đang chạy ở chế độ phát triển
                    ┌─────────────────────────────────────────┐
                    │           BASE CLASSLOADER              │
                    │  Spring Framework / Boot JAR            │
                    │  Jackson, SLF4J, database driver ...    │
                    │               (được giữ lại)            │
                    └────────────────────┬────────────────────┘
                                         │
                             nạp/delegate các class cần thiết
                                         │
                  ┌──────────────────────▼──────────────────────┐
                  │          RESTART CLASSLOADER R1             │
                  │    Application.class / Service.class        │
                  │    Class output của module đang phát triển   │
                  └──────────────────────┬──────────────────────┘
                                         │
                       sửa source → IDE/build compile
                       classpath có thay đổi cần restart
                                         │
                                   đóng context R1
                                   bỏ tham chiếu đến R1
                                         │
                  ┌──────────────────────▼──────────────────────┐
                  │          RESTART CLASSLOADER R2             │
                  │    Application.class / Service.class mới   │
                  │    Base classloader vẫn được tái sử dụng     │
                  └─────────────────────────────────────────────┘
```

Sơ đồ mô tả *ý tưởng nạp class*, không phải toàn bộ cây object classloader trong mọi JDK/IDE. JVM còn bootstrap/platform/application classloader và những classloader do thư viện khác tạo.

**Điểm phải nhớ:** restart của DevTools **không tương đương khởi động một JVM hoàn toàn mới**. Một số trạng thái của base classloader và tài nguyên cấp tiến trình có thể tồn tại giữa các lượt restart, trong khi những class thuộc restart classloader được nạp lại.

Phạm vi bài: **Spring Boot 3.3.x, Spring Framework 6.x và Java 17+** trong môi trường phát triển. Cơ chế có thể khác nếu ứng dụng đóng gói production JAR, dùng custom launcher, Java agent, AspectJ weaving hoặc hệ thống reload khác.

## 2. Java classloader là gì?

Một **ClassLoader** có trách nhiệm tìm và định nghĩa class theo tên nhị phân, ví dụ `demo.customer.CustomerService`. JVM không xác định một kiểu Java **chỉ bằng tên class**: danh tính runtime của class còn gắn với **classloader định nghĩa class đó**.

Có thể mô hình hóa:

```text
Type identity ≈ (binary class name, defining classloader)
```

Điều này có nghĩa:

```text
com.example.Order    được nạp bởi loader A
com.example.Order    được nạp bởi loader B
```

**Có thể là hai kiểu khác nhau**, dù bytecode và package/class name giống hệt. Một object của kiểu do loader B nạp không mặc nhiên có thể ép kiểu sang `com.example.Order` do loader A nạp.

### 2.1. Các classloader của JVM và DevTools

Một ứng dụng Java bình thường có thể dùng:

- **Bootstrap classloader**: nạp nhiều class cốt lõi như `java.lang.String`; `String.class.getClassLoader()` thường trả `null` trong Java.
- **Platform/application classloader**: nạp nhiều class của runtime/application theo cơ chế JVM.
- **Classloader do framework tạo thêm**: ví dụ `RestartClassLoader` của DevTools.

Trong DevTools:

- Base classloader giữ một tập classpath ít thay đổi.
- Restart classloader nạp những classpath entries được gán cho phần restart và ủy quyền việc nạp các class phù hợp cho base.
- Cách phân chia **theo classpath entries và cấu hình**, không phải theo một quy luật “package tên bắt đầu `com.example` luôn thuộc restart”.

**Không được kết luận rằng hai class có cùng package sẽ chắc chắn có cùng classloader**. Một phần mã từ module đang mở có thể nằm trong directory của restart classloader, còn một phần đóng gói thành JAR lại nằm ở base classloader.

### 2.2. Một class là một đối tượng Class

Java cho phép quan sát:

```java
ClassLoader loader = SomeType.class.getClassLoader();
System.out.println(loader);
```

Đây là snippet cần kiểu `SomeType` tồn tại. `loader` có thể khác giữa môi trường IDE, `bootRun`, tests và packaged JAR.

Với mục đích debug, nên ghi **tên classloader**, **identity** và **nguồn classpath entry** chứ không chỉ in một tên ngắn mơ hồ. Phần nguồn class có thể lấy thông qua `ProtectionDomain/CodeSource` khi có, nhưng không phải class nào cũng có nguồn hoặc code source không null.

## 3. Base classloader giữ những gì?

Theo nguyên tắc mặc định của Spring Boot DevTools 3.3:

- Những thư viện bên thứ ba được phân phối dưới dạng **JAR thông thường** nằm ở base classloader.
- Những class thuộc dependency module đã được đóng gói thành JAR cũng **có thể** nằm ở base classloader, dù đó là mã do cùng công ty phát triển.
- Base classloader **không bị thay mới sau mỗi lần restart do DevTools** theo cách restart classloader bị thay.

Ví dụ:

```text
runtime classpath
  /home/dev/.gradle/caches/.../spring-context-6.x.jar      -> base
  /home/dev/.gradle/caches/.../jackson-databind-2.x.jar     -> base
  /home/dev/.gradle/caches/.../company-shared-1.2.jar       -> base
  /workspace/order-service/build/classes/java/main/        -> restart
```

Đây là **sơ đồ classpath minh họa**; đường dẫn và phiên bản thực tế phụ thuộc OS/build tool. Cách gán entry có thể thay đổi bởi `spring-devtools.properties`.

Lợi ích:

1. Không phải nạp lại từng thư viện lớn sau mỗi thay đổi của ứng dụng.
2. Nhiều metadata/runtime class ổn định được giữ ở base.
3. Vòng restart thường nhanh hơn full JVM restart, đặc biệt khi classpath có nhiều dependencies.
4. Class code nghiệp vụ được cập nhật trong restart classloader mới sau biên dịch.

### 3.1. Base không phải “bất biến” theo nghĩa dữ liệu

Một class trong base classloader có thể giữ static fields, caches và singleton instance do thư viện tự quản lý. Những trạng thái này **không tự được tạo mới** chỉ vì DevTools thay restart classloader.

Ví dụ code trong một library JAR:

```java
public final class SharedRegistry {
    private static final Map<String, Object> CACHE =
            new ConcurrentHashMap<>();

    // methods put/get...
}
```

Đây là **snippet minh họa**, yêu cầu import `Map` và `ConcurrentHashMap`, chưa phải class đầy đủ. Nếu cache này nằm ở base classloader và giữ tham chiếu tới object do restart classloader cũ tạo, nó có thể ngăn classloader cũ được GC.

Không thể suy từ tên “base” rằng các trạng thái của base được reset khi application context restart.

### 3.2. Base còn dùng chung để làm gì?

Base giúp thư viện và Spring framework không cần được nạp lại liên tục. Nhưng cũng tạo **ranh giới** giữa class thuộc thư viện và class thuộc project. Một library dùng reflection, serialization hoặc cache class metadata cần nhận biết rằng application class có thể thay loader mỗi lần restart.

Một thiết kế thư viện tốt nên tránh giữ lâu tham chiếu tới class application qua static cache không được dọn khi context đóng, hoặc phải có cơ chế cache invalidation theo classloader/context.

## 4. Restart classloader nạp những gì?

Mặc định DevTools đặt các **dự án đang mở trong IDE** vào restart classloader; với `mvn spring-boot:run` hoặc `gradle bootRun`, module chứa `@SpringBootApplication` được nạp ở restart classloader, các JAR dependency khác ở base classloader.

Một class ứng dụng:

```java
package demo.devtools;

public final class GreetingService {
    public String hello() {
        return "hello";
    }
}
```

có thể được nạp bởi `org.springframework.boot.devtools.restart.classloader.RestartClassLoader` khi DevTools restart thực sự đang hoạt động.

Sau lần sửa source và build:

```text
GreetingService.class trong R1 ≠ GreetingService.class trong R2
```

Ngay cả khi nội dung class mới chỉ đổi một chuỗi, class do R2 định nghĩa là một **runtime Class object mới**.

### 4.1. Tại sao không sửa class đã load rồi dùng tiếp R1?

Theo cơ chế DevTools restart, những class ứng dụng được nạp bằng **classloader mới**. Đây khác với công nghệ *hot code replacement* can thiệp trực tiếp bytecode của class đã được JVM định nghĩa. Sự thay thế classloader giúp DevTools thực hiện restart nhanh nhưng **không phải một bản vá trực tiếp class definition trong R1**.

Các bước điển hình:

1. Chỉnh sửa `GreetingService.java`.
2. IDE hoặc build tool biên dịch thành `GreetingService.class` trong classpath directory.
3. File watcher của DevTools phát hiện thay đổi có ý nghĩa.
4. Application context cũ được đóng theo cơ chế restart.
5. Restart classloader R1 được loại bỏ khỏi đường sử dụng; R2 được tạo.
6. Ứng dụng được bootstrap lại bằng những class do R2 nạp.
7. Bean mới được tạo và callbacks khởi tạo chạy lại theo cấu hình.

Đây là dòng thời gian khái quát, không phải cam kết thư viện/driver ngoài context tự giải phóng mọi resource. Nếu một thread cũ giữ context classloader R1 hoặc static cache ở base giữ `Class<?>` từ R1, việc GC R1 có thể bị trì hoãn.

## 5. So sánh base và restart classloader

| Tiêu chí | Base classloader | Restart classloader |
| --- | --- | --- |
| Mục đích | Tái sử dụng class ít thay đổi | Nạp lại class ứng dụng đang phát triển |
| Ví dụ mặc định | Spring/Jackson/third-party JAR | Class từ IDE project output directory |
| Thay ở mỗi DevTools restart? | Thường **không** | **Có**, tạo loader mới |
| Static state của class cùng loader | Có thể còn trong JVM | Static state của class do loader mới nạp được khởi tạo lại |
| Class identity qua các lượt restart | Ổn định đối với class giữ tại base | Khác nhau giữa R1 và R2 |
| Chứa Spring application beans? | Có thể chứa **kiểu** thư viện hoặc cache; không đồng nghĩa sở hữu mọi bean | Có thể chứa class triển khai bean ứng dụng |
| Tác động bộ nhớ | Giữ class ổn định nhưng cache có thể giữ tham chiếu cũ | Có thể được GC nếu không còn reference |
| Điều chỉnh phân chia | `restart.include` có thể kéo entry lên restart | `restart.exclude` có thể đẩy entry xuống base |
| Thay thế full JVM restart? | Không | Không; vẫn cùng JVM |

**Trạng thái bean và classloader không phải một thứ.** Spring `ApplicationContext` tạo/đóng bean, còn classloader xác định runtime type của class. Một bean thuộc framework type ở base vẫn có thể được tạo mới trong context sau restart; đồng thời class ở base có thể giữ static state cũ.

## 6. Khi nào DevTools restart được kích hoạt?

DevTools **theo dõi thay đổi trên classpath**, đặc biệt những entry trỏ tới directory. Sửa file `.java` trong IDE **chưa đủ** nếu IDE không biên dịch lại class output.

Trong Spring Boot 3.3:

- **Eclipse**: lưu source thường cập nhật classpath nhờ auto-build, có thể kích hoạt restart.
- **IntelliJ IDEA**: dùng `Build → Build Project` để cập nhật class output theo cấu hình IDE.
- **Maven/Gradle**: cần compile/build phù hợp để thay đổi file class output.
- **IDE khác**: kiểm tra đường biên dịch và classpath directory thực tế.

```text
Sửa *.java
    |
    v
IDE / build tool tạo *.class mới trên classpath
    |
    v
DevTools FileSystemWatcher phát hiện thay đổi
    |
    v
Restart context và restart classloader
```

**Không phải mọi file thay đổi đều bắt buộc restart.** DevTools có nhóm tài nguyên như `static/**`, `public/**` và `templates/**` thường được loại khỏi restart để phục vụ reload tài nguyên thay vì dựng lại application context.

### 6.1. Restart khác LiveReload

- **Restart:** thay restart classloader và khởi tạo lại Spring application context khi classpath change cần restart.
- **LiveReload:** hỗ trợ trình duyệt refresh khi tài nguyên thay đổi; không đồng nghĩa class Java đã được nạp lại.
- **Full JVM restart:** đóng process Java và chạy process mới; cả state base/restart classloader lẫn JVM-level state bắt đầu từ đầu.

Một thay đổi file CSS có thể cần trình duyệt reload nhưng không cần tạo restart classloader mới. Một thay đổi method Java thường cần biên dịch lại class output rồi restart.

Không coi LiveReload là bằng chứng rằng Java class code đã được refresh.

### 6.2. Thiết lập trigger file

Khi IDE compile liên tục gây restart quá thường xuyên, có thể dùng:

```properties
spring.devtools.restart.trigger-file=.reloadtrigger
```

Tạo file:

```text
src/main/resources/.reloadtrigger
```

File này cần xuất hiện trên runtime classpath. Khi file trigger được cập nhật, DevTools kiểm tra xem đã có thay đổi đáng restart hay chưa. Trigger file chỉ điều khiển **khi nào kiểm tra** chứ **không chuyển class sang base hay restart loader**.

### 6.3. Poll interval và quiet period

Nếu DevTools restart quá sớm khi IDE còn đang copy class files:

```properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
```

Watcher poll định kỳ và đợi một khoảng yên lặng để gom thay đổi, giảm khả năng restart khi build chưa hoàn tất. Đây là cấu hình **theo dõi file**, không phải cấu hình classloader phân chia hoặc thread pool nghiệp vụ.

## 7. Ví dụ runnable Spring Boot 3.3, Java 17+: xem loader thực tế

Ví dụ sau không giả định một classloader có tên gì trên tất cả máy. Ta in **tên classloader**, đồng thời so sánh classloader của application class với classloader của `SpringApplication`.

### 7.1. Cấu trúc dự án

```text
devtools-loaders-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          devtools/
            LoaderSplitApplication.java
      resources/
        application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'devtools-loaders-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

**Tại sao dùng `developmentOnly`?** DevTools phục vụ phát triển và không nên vô tình trở thành dependency runtime production. Theo Spring Boot 3.3, Gradle plugin xử lý dependency devtools trong quá trình tạo executable archive theo cơ chế mặc định. Với Maven, có thể dùng dependency `spring-boot-devtools` với `optional=true`.

Project cần Gradle wrapper tương thích; file build trên không tự sinh `gradlew`. Phiên bản 3.3.13 dùng để tái hiện hành vi của nhánh Spring Boot 3.3; dự án mới cần cân nhắc phiên bản còn được hỗ trợ.

`src/main/resources/application.properties`:

```properties
spring.application.name=devtools-loaders-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
```

### 7.2. Mã Java độc lập trong dự án Boot

`src/main/java/demo/devtools/LoaderSplitApplication.java`:

```java
package demo.devtools;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class LoaderSplitApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoaderSplitApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectLoaders(LocalGreeting greeting) {
        return args -> {
            ClassLoader appLoader =
                    LoaderSplitApplication.class.getClassLoader();
            ClassLoader serviceLoader =
                    LocalGreeting.class.getClassLoader();
            ClassLoader frameworkLoader =
                    SpringApplication.class.getClassLoader();

            System.out.println("app.loader=" + nameOf(appLoader));
            System.out.println("service.loader=" + nameOf(serviceLoader));
            System.out.println("app.sameAsFramework="
                    + (appLoader == frameworkLoader));
            System.out.println("app.sameAsService="
                    + (appLoader == serviceLoader));
            System.out.println("greeting=" + greeting.message());
        };
    }

    private static String nameOf(ClassLoader loader) {
        if (loader == null) {
            return "bootstrap";
        }
        return loader.getClass().getSimpleName();
    }
}

@Component
class LocalGreeting {

    String message() {
        return "hello";
    }
}
```

`LocalGreeting` là package-private top-level class trong cùng file; Java cho phép một public top-level class và các class không public khác. `@SpringBootApplication` của `LoaderSplitApplication` nằm trong cùng package nên `LocalGreeting` được component-scan.

### 7.3. Chạy bằng bootRun và kích hoạt restart

Với Gradle wrapper:

```bash
./gradlew bootRun
```

Khi DevTools restart thực sự được kích hoạt với classpath điển hình do `bootRun` tạo, các dòng **do code ví dụ in ra** có dạng:

```text
app.loader=RestartClassLoader
service.loader=RestartClassLoader
app.sameAsFramework=false
app.sameAsService=true
greeting=hello
```

Đây là kết quả **kỳ vọng có điều kiện** khi application classes thuộc restart loader và `SpringApplication` thuộc base loader. Ở IDE/custom classloader khác, tên loader cụ thể có thể thay đổi. Boot/Gradle còn in thêm logs không nằm trong khối trên.

Lý do:

1. `LoaderSplitApplication` và `LocalGreeting` thuộc project class output → restart loader.
2. `SpringApplication` nằm trong Spring Boot library JAR → base loader.
3. Classloader của application/service giống nhau trong cấu hình này.
4. Classloader của application khác classloader của class framework.

### 7.4. Thử sửa source

Đổi:

```java
String message() {
    return "hello again";
}
```

Đây là **biến thể thay thế** cho method của `LocalGreeting`, không thêm method trùng chữ ký. Compile lại bằng IDE/build tool khi process devtools đang chạy. Sau khi DevTools phát hiện classpath change, ứng dụng restart và có thể in:

```text
app.loader=RestartClassLoader
service.loader=RestartClassLoader
app.sameAsFramework=false
app.sameAsService=true
greeting=hello again
```

Dù tên simple classloader vẫn là `RestartClassLoader`, **instance restart classloader đã thay đổi**. Hai lần `nameOf(...)` trả cùng chuỗi không có nghĩa chúng là cùng một object loader.

### 7.5. Kiểm tra identity loader thay vì chỉ tên

Có thể thêm vào runner:

```java
System.out.println(
        "app.loaderIdentity="
        + System.identityHashCode(
                LoaderSplitApplication.class.getClassLoader()));
```

Đây là snippet thêm trong method `inspectLoaders`. `identityHashCode` chỉ là con số để quan sát local process, **không phải ID duy nhất tuyệt đối**, không lưu nó như khóa nghiệp vụ. Khi restart, giá trị có thể khác, nhưng việc vô tình trùng số vẫn có thể xảy ra. Muốn so sánh chắc chắn trong cùng JVM, giữ tham chiếu hai object loader rồi so bằng `==` ở code kiểm thử phù hợp.

### 7.6. Vì sao java -jar cho kết quả khác?

Thử:

```bash
./gradlew bootJar
java -jar build/libs/devtools-loaders-demo-1.0.0.jar
```

Trong Boot 3.3, DevTools thường **được loại khỏi executable archive** và chức năng restart **tự tắt ở fully packaged application**. Do đó không kỳ vọng `RestartClassLoader` ở đường chạy `java -jar` bình thường. Kết quả có thể là:

```text
app.sameAsFramework=true
app.sameAsService=true
greeting=hello
```

Tên classloader thực tế có thể là launcher classloader của executable JAR chứ không phải `AppClassLoader`. Khối output là những dòng quan hệ loader trong cấu hình packaged điển hình, **không** chứng minh mọi custom launcher đều phải sử dụng đúng một loader.

**Không dùng `java -jar` để kiểm tra DevTools restart mặc định**. Hãy dùng IDE hoặc `bootRun`/`spring-boot:run` với dependency devtools thực sự trên runtime classpath.

## 8. Java 17 thuần: cùng tên class nhưng classloader khác thì khác kiểu

Đây là thí nghiệm không phụ thuộc Spring Boot, giúp hiểu nguyên lý nền tảng của class identity.

### 8.1. Tạo file Widget.java

```java
public class Widget {

    public Widget() {
    }
}
```

### 8.2. Tạo file LoaderIdentityDemo.java

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderIdentityDemo {

    public static void main(String[] args) throws Exception {
        Path root = Path.of("out").toAbsolutePath();
        URL classpath = root.toUri().toURL();

        try (URLClassLoader first =
                    new URLClassLoader(new URL[] { classpath }, null);
             URLClassLoader second =
                    new URLClassLoader(new URL[] { classpath }, null)) {

            Class<?> left = Class.forName("Widget", true, first);
            Class<?> right = Class.forName("Widget", true, second);

            System.out.println("same.name="
                    + left.getName().equals(right.getName()));
            System.out.println("same.class=" + (left == right));
            System.out.println("assignable="
                    + left.isAssignableFrom(right));

            Object rightInstance =
                    right.getDeclaredConstructor().newInstance();

            try {
                left.cast(rightInstance);
                System.out.println("cast=success");
            } catch (ClassCastException exception) {
                System.out.println("cast=ClassCastException");
            }
        }
    }
}
```

### 8.3. Biên dịch và chạy

Trong thư mục chứa hai file:

```bash
javac -d out Widget.java LoaderIdentityDemo.java
java -cp out LoaderIdentityDemo
```

Stdout chính xác:

```text
same.name=true
same.class=false
assignable=false
cast=ClassCastException
```

Giải thích:

- Hai loader có **cùng URL** trỏ tới directory chứa `Widget.class`.
- Tham số parent `null` trong `URLClassLoader` làm hai loader không dùng application loader để nạp `Widget` (chúng vẫn có quyền truy cập các class nền tảng của JVM).
- Hai `Class.forName` định nghĩa `Widget` bằng **hai loader riêng**.
- Tên đều là `"Widget"` nhưng `left != right`.
- Instance tạo từ `right` không thể `cast` sang `left`.

Đây là lý do tại sao bạn có thể gặp thông báo:

```text
com.acme.Model cannot be cast to com.acme.Model
```

trong môi trường có nhiều classloader. Thông báo không mâu thuẫn: **hai `com.acme.Model` có thể là hai kiểu runtime khác nhau** vì defining classloader khác.

**Quan trọng:** demo này dùng hai `URLClassLoader` độc lập để làm rõ ngữ nghĩa JVM. DevTools có cách phân chia/delegation riêng giữa base và restart loader; nó không đồng nhất 100% với hai loader có parent `null` trong thí nghiệm.

## 9. Class identity dẫn đến các loại lỗi nào?

### 9.1. ClassCastException

Một library thuộc base giữ object do restart classloader cũ tạo. Sau restart, application code ở R2 cố ép object đó về kiểu cùng tên do R2 nạp:

```text
instance = CustomerModel (loader R1)
expected = CustomerModel (loader R2)

Ép kiểu → ClassCastException
```

Điều kiện gây lỗi phụ thuộc cách object được truyền qua ranh giới. Không phải mọi object đi qua base/restart đều sai: những interface/class dùng chung được định nghĩa ở base có thể là hợp đồng đúng, nếu code giữ types ổn định.

### 9.2. LinkageError và lỗi phân giải type

Một thư viện dùng reflection, proxy hoặc class metadata cache có thể nạp những class không tương thích qua các loader khác nhau, dẫn tới:

- `ClassCastException`.
- `ClassNotFoundException`.
- `NoClassDefFoundError`.
- `LinkageError` ở các tình huống liên kết không nhất quán.
- Method/annotation không được framework phát hiện như mong đợi.

**Không được kết luận mọi lỗi loại này đều do DevTools.** Chúng còn có thể do dependency conflict, version mismatch, bytecode không hợp lệ hoặc classpath sai. Một bước chẩn đoán quan trọng là tắt **restart hoàn toàn** rồi so sánh.

### 9.3. Annotations và reflection

Spring Boot 3.3 lưu ý các class được nạp bằng reflection, đặc biệt annotations, có thể bị nạp từ parent/base classloader trước khi application class cần chúng được tạo. Điều đó đôi khi khiến annotation không được phát hiện như kỳ vọng.

Ví dụ bối cảnh:

```text
shared-annotations.jar → base
order-service classes → restart

Reflective library tạo/cache Class<?> hoặc Annotation type quá sớm
     |
     +-- Sau restart, application class được định nghĩa bởi loader khác
     +-- Cần kiểm tra type resolution qua ranh giới loader
```

**Không giải bằng cách chuyển tất cả JAR sang restart một cách mù quáng.** Xác định classpath entry liên quan, kiểm tra thư viện nào cache/load class trước, rồi chỉ thay phạm vi cần thiết.

## 10. Multi-module project là nơi lỗi classloader dễ xuất hiện

Giả sử repository:

```text
workspace/
  api-service/           → module chứa @SpringBootApplication
  shared-domain/         → model + interfaces
  shared-annotations/    → annotation custom
  legacy-adapter/        → adapter thư viện
```

Có ít nhất hai cách đưa `shared-domain` vào runtime classpath:

1. **Project/module đang mở và dùng class directory**: có thể được DevTools đưa vào restart classloader.
2. **JAR đã build sẵn**: thường được đưa vào base classloader.

Khi IDE import toàn bộ modules dưới dạng dự án đang phát triển, chúng có thể được phân vào restart loader. Khi CI/build tool dùng binary JAR của một module, nó có thể vào base loader. Do đó **cùng một repo có thể có phân chia classloader khác nhau giữa hai cách chạy**.

### 10.1. Vì sao IDE chạy được nhưng bootRun gặp lỗi?

Những biến có thể khác:

- IDE xác định “open projects” khác Gradle run classpath.
- Một module được IDE dùng output directory, nhưng Gradle dùng JAR artifact.
- Một dependency là `project(":shared-domain")` hay một artifact từ repository.
- Một thư viện runtime nạp annotation/model bằng reflection trước các class application.
- Một classpath entry bị mapping bởi `META-INF/spring-devtools.properties` của một thư viện.
- Custom class loader hoặc Java agent thay đổi thứ tự nạp class.

Trước khi sửa code, **in classloader và CodeSource của type ở hai phía** để biết chúng được nạp từ đâu.

### 10.2. Một ví dụ phân chia cần chú ý

```text
base:
    shared-domain-1.0.jar
    jackson-databind.jar

restart R1:
    api-service/build/classes/java/main

restart R2:
    api-service/build/classes/java/main (new version)
```

Nếu class trong `shared-domain.jar` giữ một cache static chứa `Class<?>` từ R1, cache đó có thể còn sau restart, trong khi ứng dụng mới sử dụng R2.

Cần kiểm tra chỗ cache và cleanup. Đôi khi chuyển `shared-domain.jar` sang restart loader giúp type identity đồng nhất theo lượt restart; đôi khi giải pháp tốt hơn là sửa thư viện để không giữ class object lâu dài.

## 11. Tùy chỉnh phân chia qua META-INF/spring-devtools.properties

Spring Boot DevTools cung cấp cấu hình dành riêng cho **classloader partition**, không phải cấu hình application properties thông thường:

```text
src/main/resources/META-INF/spring-devtools.properties
```

File này có các key:

- `restart.include.<tên-duy-nhất>`: kéo classpath entry phù hợp **lên restart classloader**.
- `restart.exclude.<tên-duy-nhất>`: đẩy classpath entry phù hợp **xuống base classloader**.

Giá trị của mỗi key là **regular expression được áp dụng lên các classpath entries khi JVM khởi động**. Tên key cần duy nhất; Spring Boot đọc tất cả các file `META-INF/spring-devtools.properties` trên classpath, kể cả từ dependency JAR.

### 11.1. Ví dụ mẫu

```properties
# Chỉ là ví dụ regex cho classpath dạng Unix.
# Pull shared-model JAR vào restart classloader:
restart.include.shared-model=.*/shared-model-[^/]+\\.jar

# Push compiled directory của module generated-api về base:
restart.exclude.generated-api=.*/generated-api/build/classes/.*
```

Những pattern này **phải được điều chỉnh theo classpath thực tế** và hệ điều hành. Trong file Java properties, để regex nhận ký tự `\.`, có thể cần biểu diễn dấu `\` hai lần như mẫu `\\.jar`. Dùng pattern quá rộng có thể đưa cả thư viện lớn vào restart loader, làm restart chậm hoặc gây lỗi type identity mới.

Nếu dùng Windows, classpath URL/path có thể có cách biểu diễn separator khác. Tránh copy regex theo ví dụ Unix rồi kết luận DevTools bỏ qua cấu hình khi thực tế pattern không khớp entry nào.

### 11.2. Include/exclude thực sự áp dụng cho cái gì?

Các giá trị này **không phải package names** và cũng không phải regex chạy trên fully qualified class name như `com.acme.Foo`. Chúng được dùng để quyết định **classpath entry** nào thuộc loader nào.

Ví dụ:

```text
Classpath entry: /home/me/.m2/repository/acme/shared-model-1.2.jar
Pattern:         .*/shared-model-[^/]+\\.jar
Decision:        Chuyển cả entry shared-model-1.2.jar vào restart
```

Vì vậy muốn “chuyển chỉ một class” bên trong một JAR lớn mà không thay artifact/module partition, cấu hình regex này **không phải công cụ chọn class riêng lẻ**. Cần thay cách đóng gói hoặc tổ chức classpath nếu muốn tách mịn hơn.

### 11.3. Chọn include hay exclude?

| Nhu cầu | Hướng hành động |
| --- | --- |
| Một JAR module nội bộ chứa model/annotation đổi thường xuyên | Cân nhắc `restart.include.*` để cùng restart với ứng dụng |
| Một directory của module ít đổi nhưng đang bị xem là open project | Cân nhắc `restart.exclude.*` để giảm tải restart |
| Library base giữ object/class từ restart loader cũ | Sửa ownership/cache trước; nếu phù hợp, cân nhắc include library |
| Có class cần reflection/annotation xuyên module | Kiểm tra defining loader và thời điểm load; điều chỉnh entry liên quan |
| Không biết entry nào bị phân sai | In classpath/classloader, xem log rồi thu hẹp regex |
| Một thay đổi JAR không được watcher phát hiện | Kiểm tra cơ chế theo dõi classpath directory và build/restart; include không tự bảo đảm watcher cho mọi JAR |

**Đừng nhầm `restart.include` với một lệnh “watch file”**. DevTools mặc định theo dõi classpath entries dạng directory; việc chuyển một JAR sang restart loader không có nghĩa mọi thay đổi vào JAR đó đều được phát hiện/restart theo cùng cách.

### 11.4. Tại sao không đặt include/exclude trong application.properties?

`restart.include.*` và `restart.exclude.*` của **phân chia classloader** là cơ chế riêng đọc từ `META-INF/spring-devtools.properties`. Theo tài liệu Spring Boot 3.3, system properties không dùng được để thay thế file phân chia này.

Khác với:

```properties
spring.devtools.restart.enabled=false
spring.devtools.restart.additional-exclude=docs/**
```

là các **Spring Boot DevTools application properties** cho bật/tắt restart và theo dõi thay đổi resource. Cùng có chữ “restart”, nhưng không phải cùng một namespace và nhiệm vụ.

## 12. Bốn cơ chế dễ bị lẫn tên

| Cơ chế | Cấu hình / hành vi | Tác động |
| --- | --- | --- |
| Phân chia classloader | `META-INF/spring-devtools.properties` với `restart.include.*` / `restart.exclude.*` | **Classpath entries** nào vào base/restart |
| Loại trừ resource khỏi trigger | `spring.devtools.restart.exclude` | Thay đổi resource nào **không kích hoạt restart** |
| Thêm loại trừ mà giữ mặc định | `spring.devtools.restart.additional-exclude` | Bổ sung danh sách không trigger restart |
| Theo dõi thêm đường dẫn | `spring.devtools.restart.additional-paths` | Watch extra paths; **không tự chuyển classpath entry sang restart loader** |
| Chỉ restart khi chạm file trigger | `spring.devtools.restart.trigger-file` | Điều khiển thời điểm kiểm tra restart |
| Tắt restart | `spring.devtools.restart.enabled` | Ngừng hoặc vô hiệu hóa restart tùy cách đặt |

Ví dụ để thêm loại trừ cho tài liệu generated nhưng vẫn giữ mặc định:

```properties
spring.devtools.restart.additional-exclude=docs/**,generated-notes/**
```

Ví dụ **thay thế** danh sách loại trừ mặc định:

```properties
spring.devtools.restart.exclude=static/**,public/**
```

Hãy chú ý `exclude` trực tiếp **thay thế** nhóm mặc định; nếu muốn **giữ mặc định và thêm** thì dùng `additional-exclude`. Việc resource change có trigger restart hay không không nói class chứa resource ấy thuộc base hay restart loader.

## 13. Kiểm tra CodeSource: class được nạp từ đâu?

Khi gặp lỗi nhiều classloader, cách đọc hữu ích là:

```java
import java.net.URL;
import java.security.CodeSource;

public final class LoaderDiagnostics {

    private LoaderDiagnostics() {
    }

    public static void print(String label, Class<?> type) {
        ClassLoader loader = type.getClassLoader();
        CodeSource codeSource =
                type.getProtectionDomain() == null
                ? null
                : type.getProtectionDomain().getCodeSource();

        URL location = codeSource == null
                ? null : codeSource.getLocation();

        System.out.println(label + ".type=" + type.getName());
        System.out.println(label + ".loader="
                + (loader == null ? "bootstrap" : loader));
        System.out.println(label + ".location="
                + (location == null ? "<unavailable>" : location));
    }
}
```

Đây là class Java đầy đủ đặt trong `LoaderDiagnostics.java`; có thể dùng từ code ứng dụng:

```java
LoaderDiagnostics.print("app", LoaderSplitApplication.class);
LoaderDiagnostics.print("spring", SpringApplication.class);
LoaderDiagnostics.print("model", SharedModel.class);
```

Đoạn gọi này là **snippet**: cần import `SpringApplication` và có kiểu `SharedModel` từ một module/thư viện thật. Nó không biên dịch độc lập nếu chưa định nghĩa `SharedModel`.

**Chú ý bảo mật:** `location` có thể chứa đường dẫn máy, tên người dùng hoặc vị trí nội bộ. Chỉ dùng dạng diagnostics trong development có quyền kiểm soát; không vô điều kiện log full path ở production.

### 13.1. Đọc đầu ra như thế nào?

Ví dụ output giả định:

```text
app.loader=org.springframework.boot.devtools.restart.classloader.RestartClassLoader@...
app.location=file:/workspace/app/build/classes/java/main/
spring.loader=jdk.internal.loader.ClassLoaders$AppClassLoader@...
spring.location=file:/home/user/.gradle/caches/.../spring-boot-3.3.x.jar
model.loader=org.springframework.boot.devtools.restart.classloader.RestartClassLoader@...
model.location=file:/workspace/shared/build/classes/java/main/
```

Đây là **ví dụ minh họa**, không phải stdout chính xác: đường dẫn, hash và loader JDK thay đổi theo môi trường.

Nếu model đáng ra thuộc restart loader nhưng hiện là JAR ở base, đây là dấu hiệu để kiểm tra module import/build artifacts và cân nhắc `restart.include.*`.

## 14. Thread Context ClassLoader (TCCL) có vai trò gì?

Ngoài `SomeType.class.getClassLoader()`, Java còn có:

```java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();
```

TCCL được nhiều thư viện dùng để **tìm class theo ngữ cảnh thread hiện tại**, đặc biệt khi class gọi từ thư viện base muốn nạp kiểu ứng dụng nằm trong restart classloader.

Ví dụ:

```java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName(
        "demo.devtools.LocalGreeting",
        true,
        tccl);
```

Đây là **snippet** đặt trong method có class `demo.devtools.LocalGreeting` khả dụng. Nếu TCCL được cấu hình trỏ tới loader phù hợp, việc nạp class application có thể thành công. Nhưng không nên khẳng định TCCL mọi thread tự luôn là restart loader.

### 14.1. Vấn đề khi tự tạo thread

Một thread custom:

```java
Thread thread = new Thread(() -> {
    // Một thư viện có thể đọc TCCL tại đây.
});
thread.start();
```

có thể kế thừa TCCL từ thread tạo nó hoặc bị executor/framework thay đổi. Nếu thread sống quá lâu và giữ TCCL trỏ tới R1, nó có thể **giữ reference tới restart classloader cũ** sau DevTools restart.

Do đó:

- Ưu tiên executor được Spring quản lý và đóng đúng vòng đời.
- Khi tự tạo thread, cần có shutdown/cancellation ở `@PreDestroy` hoặc `SmartLifecycle.stop(...)` phù hợp.
- Không lưu thread/context classloader trong static caches không có cleanup.
- Chỉ thay TCCL thủ công trong phạm vi chặt chẽ và khôi phục bằng `finally` nếu cần.

### 14.2. Ví dụ thay TCCL có khôi phục

```java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

try {
    current.setContextClassLoader(targetLoader);
    // Gọi library cần targetLoader tại đây.
} finally {
    current.setContextClassLoader(previous);
}
```

Đây là snippet, cần biến `targetLoader` thuộc kiểu `ClassLoader` đã được xác định. Phải có lý do rõ ràng trước khi sửa TCCL; đây không phải mẹo áp dụng cho mọi lỗi ClassCastException.

## 15. Serialization và lỗi ObjectInputStream

Tài liệu Spring Boot 3.3 ghi nhận một giới hạn cụ thể: restart có thể gặp vấn đề khi object được deserialize bằng `java.io.ObjectInputStream` thông thường. Lý do là việc tìm class theo loader không luôn phù hợp với những class application nằm ở restart classloader.

Một lựa chọn trong code **đáng tin cậy và có kiểm soát dữ liệu** là dùng `ConfigurableObjectInputStream` của Spring, truyền TCCL thích hợp:

```java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.ConfigurableObjectInputStream;

public final class ClassAwareDeserializer {

    private ClassAwareDeserializer() {
    }

    public static Object read(InputStream source)
            throws IOException, ClassNotFoundException {

        ClassLoader loader =
                Thread.currentThread().getContextClassLoader();

        try (ConfigurableObjectInputStream in =
                new ConfigurableObjectInputStream(source, loader)) {
            return in.readObject();
        }
    }
}
```

Đây là class Java đầy đủ **cần Spring Core trên classpath**, không phải chương trình `javac` thuần. Code chọn loader để giải quyết class identity phù hợp hơn trong một số trường hợp DevTools. Tuy nhiên **không dùng Java deserialization với dữ liệu không đáng tin**: `ObjectInputStream` nói chung có rủi ro bảo mật nghiêm trọng với payload độc hại. Trong hệ thống production, ưu tiên định dạng/serializer an toàn và có schema/allowlist rõ ràng.

Nếu một third-party library tự dùng `ObjectInputStream` và không có cơ chế cung cấp classloader, việc thay code ứng dụng có thể không đủ. Có thể cần cập nhật thư viện, báo lỗi cho tác giả, đổi serializer hoặc tạm tắt DevTools restart trong development.

### 15.1. Không đồng nhất JSON và Java Object Serialization

Jackson JSON thường dựa vào type metadata do framework cung cấp và có thể có cơ chế nạp class riêng. Java serialization trực tiếp dùng `ObjectInputStream` có hạn chế khác. Cả hai có thể gặp lỗi classloader nếu library cache sai metadata/type, nhưng không nên “chữa” bằng cách thay serializer tùy tiện mà chưa biết dữ liệu thuộc loại nào.

## 16. Static cache, thread leak và khả năng GC restart loader cũ

Một vấn đề quan trọng khi DevTools restart nhiều lần là **giữ classloader cũ sống**.

Một restart loader R1 chỉ có thể được thu gom khi không còn các tham chiếu mạnh tới:

- Instance của class do R1 định nghĩa.
- `Class<?>` hoặc `Method`/`Field` của R1.
- Thread có TCCL trỏ R1.
- Listener được đăng ký ở một registry sống trong base loader.
- Static cache của thư viện base chứa proxy/metadata từ R1.
- Resource callback được gắn vào singleton ngoài Spring context đang sống lâu.
- Class loader khác giữ handle/transformer của R1.

```text
Base library static CACHE
            |
            +--> Class<?> của OrderService (R1)
                         |
                         +--> RestartClassLoader R1

DevTools restart -> tạo R2
R1 vẫn bị base cache giữ -> chưa thể GC
```

Sau nhiều lần restart, số classloaders cũ bị giữ có thể tăng, gây áp lực heap/metaspace. Không phải **mọi** lần restart làm tăng memory vĩnh viễn: GC cần thời gian và nhiều cache có thể tự giải phóng đúng cách.

### 16.1. Thiết kế cleanup

Một Spring-managed component có thể dọn subscriptions khi context đóng:

```java
@Component
class RegistrationOwner {

    private final ExternalRegistry registry;
    private final Object listener = new Object();

    RegistrationOwner(ExternalRegistry registry) {
        this.registry = registry;
        this.registry.register(listener);
    }

    @PreDestroy
    void unregister() {
        registry.unregister(listener);
    }
}
```

Đây là **snippet** cần interface `ExternalRegistry` với methods `register` / `unregister` và import `Component`, `jakarta.annotation.PreDestroy`. Nó biểu diễn nguyên tắc: object đăng ký vào registry sống lâu phải được unregister khi application context đóng.

Nếu registry là base/static và listener là instance từ restart loader, unregister đặc biệt quan trọng. Constructor register có thể không phải vị trí tốt nhất nếu có rủi ro rollback; production nên xem xét lifecycle/init và xử lý lỗi một phần.

### 16.2. Test leak đúng cách

- Chạy DevTools restart nhiều lần với thay đổi classpath thật.
- Quan sát heap/metaspace, số retained `RestartClassLoader` sau GC phù hợp.
- Dùng heap dump/profiler trong môi trường dev để lần ra đường giữ reference.
- Tìm static cache và thread TCCL trỏ loader cũ.
- Kiểm tra `@PreDestroy`, executor shutdown và listener unregister.
- Không quy kết tất cả memory growth cho DevTools; JVM caching/JIT và các phần khác cũng tăng trong giai đoạn warmup.

## 17. DevTools restart đóng context như thế nào?

DevTools restart dựa vào khả năng đóng application context trước khi tạo context mới. Các bean đã được Spring quản lý phù hợp sẽ đi qua lifecycle close/destroy trong luồng dừng thông thường.

Nhưng cần phân biệt:

- **Spring bean lifecycle:** tạo, khởi tạo, start, stop, destroy.
- **Java classloader lifecycle:** class được nạp và có thể bị GC khi không còn reference.
- **JVM process lifecycle:** OS process vẫn tồn tại cho một lần DevTools restart.

Một bean `@PreDestroy` chạy không tự chứng minh R1 đã được GC; có thể có cache/thread nằm ngoài context vẫn tham chiếu R1. Ngược lại, classloader bị thay không có nghĩa đã dừng sạch những tác vụ bên ngoài Spring.

### 17.1. Không tắt shutdown hook tùy tiện

Tài liệu Spring Boot 3.3 lưu ý DevTools cần cơ chế shutdown hook của application context để hoạt động restart đúng. Nếu code gọi:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setRegisterShutdownHook(false);
app.run(args);
```

đây là snippet cần class `MyApplication` và import `SpringApplication`; việc tắt shutdown hook có thể khiến DevTools restart không hoạt động đúng. Không nên dùng cấu hình này làm workaround khi chưa hiểu vòng đời context.

### 17.2. AspectJ weaving

Spring Boot 3.3 nêu hạn chế: automatic restart của DevTools **không được hỗ trợ khi dùng AspectJ weaving**. Cần phân biệt:

- Spring AOP proxy thông thường.
- AspectJ weaving (compile-time/load-time).

Nếu gặp xung đột với AspectJ weaving, không nên cố sửa hàng loạt regex include/exclude trong lúc cơ chế restart vốn không được hỗ trợ ở cấu hình đó.

## 18. Tắt restart đúng cách để chẩn đoán

Có **hai cấp độ** thường bị đánh đồng.

### 18.1. Tắt watcher trong application.properties

```properties
spring.devtools.restart.enabled=false
```

Theo Spring Boot 3.3, cách này **thường vẫn khởi tạo restart classloader**, nhưng không theo dõi thay đổi file để restart. Vì vậy:

- Không thấy auto-restart khi sửa code.
- Vẫn có thể còn mô hình classloader của DevTools.
- **Chưa phải** phép thử loại bỏ hoàn toàn classloader boundary để chẩn đoán `ClassCastException`.

### 18.2. Tắt hoàn toàn restart trước SpringApplication.run

Đặt **JVM system property** trước khi DevTools được kích hoạt:

```java
package demo.devtools;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DisableRestartApplication {

    public static void main(String[] args) {
        System.setProperty("spring.devtools.restart.enabled", "false");
        SpringApplication.run(DisableRestartApplication.class, args);
    }
}
```

Đây là một entry point Spring Boot hoàn chỉnh (trong file `DisableRestartApplication.java`); dùng **làm biến thể thay thế** cho entry point demo khác, không đặt nhiều `@SpringBootApplication` cùng component scan path nếu muốn hành vi không bị nhiễu.

Hoặc qua JVM option khi khởi động:

```bash
java -Dspring.devtools.restart.enabled=false ...
```

Dấu `...` ở đây là cú pháp **minh họa không phải lệnh chạy hoàn chỉnh**; thay bằng classpath/main class hay launcher thực tế. Trong JVM, property phải được đặt sớm trước `SpringApplication.run(...)`; đừng chỉ thay giá trị sau khi context đã chạy.

### 18.3. Quy trình A/B chẩn đoán

1. Tạo lại lỗi khi DevTools restart active.
2. Ghi classloader, CodeSource, stack trace đã loại dữ liệu nhạy cảm.
3. Tắt hoàn toàn restart bằng **system property trước `run`** hoặc loại dependency DevTools.
4. Khởi động một process mới và thử lại.
5. Nếu lỗi biến mất, điều này **gợi ý** classloader boundary là tác nhân; chưa đủ chứng minh pattern nào cần sửa.
6. Dùng diagnostics xác định classpath entry liên quan.
7. Chỉnh `META-INF/spring-devtools.properties` theo phạm vi nhỏ.
8. Bật restart lại và thử nhiều lượt restart với cả success/failure.
9. Đo tốc độ restart và memory để kiểm tra không tạo rủi ro mới.

Nếu lỗi vẫn xuất hiện khi restart hoàn toàn tắt, ưu tiên kiểm tra dependency versions, shading, ClassPath conflicts, class initialization và cách dùng reflection/serialization khác.

## 19. Tại sao disable DevTools trong packaged JAR không giống bật restart khi đóng gói?

DevTools là công cụ phát triển. Spring Boot 3.3 **tự động vô hiệu hóa** các chức năng DevTools trong fully packaged application thông thường, chẳng hạn khởi động bằng `java -jar` hoặc special launcher.

Trong Gradle, cấu hình:

```groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

giúp dependency chỉ phục vụ vòng phát triển/bootRun và tránh bị mang vào production package theo mặc định.

Trong Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
```

`optional` giúp không kéo dependency devtools transitively sang module khác. Với packaged app, cơ chế exclude theo Spring Boot plugin và quy tắc chạy production cần được tôn trọng.

**Không ép DevTools bật trong production** bằng `-Dspring.devtools.restart.enabled=true`. Tài liệu Boot 3.3 cảnh báo đây là rủi ro bảo mật. Ở production cần build/deploy phiên bản mới theo quy trình chuẩn, không dựa vào classloader restart devtools như cơ chế hot deployment.

## 20. Một số trường hợp debug nhiều module

### 20.1. Model trong module shared bị ClassCastException

**Triệu chứng:**

```text
ClassCastException: com.acme.shared.OrderDto
cannot be cast to com.acme.shared.OrderDto
```

**Cách xử lý:**

1. In `getClassLoader()` của object thực tế.
2. In `OrderDto.class.getClassLoader()` ở nơi thực hiện cast.
3. Xác định type nào được định nghĩa ở R1, R2 hay base.
4. Xem base static cache hoặc serialization có giữ object cũ không.
5. Tắt restart hoàn toàn để kiểm tra giả thuyết.
6. Chỉ sau đó cân nhắc đưa JAR shared vào restart loader hoặc sửa cache/serializer.
7. Không chỉ thêm `(OrderDto) object` hay dùng reflection ép kiểu khác, vì class identity vẫn sai.

### 20.2. Annotation custom không được scan

**Triệu chứng:** một annotation tồn tại trên bytecode nhưng component scanner/reflection không tìm thấy hoặc một framework library dùng type khác với type Spring đang quan sát.

**Cách xử lý:**

- Kiểm tra module chứa annotation đang là directory hay JAR.
- Xem classloader của annotation type, annotated class và scanner.
- Xem library có cache metadata ở base qua các restart không.
- Dùng config include/exclude để đồng bộ phạm vi nạp cần thiết, hoặc chỉnh cách library sử dụng TCCL.
- Không mặc định việc thêm `@ComponentScan` rộng hơn sẽ sửa lỗi nếu vấn đề là identity loader.

### 20.3. Third-party serializer bị ClassNotFoundException

**Triệu chứng:** deserializer library thuộc base loader tìm một class chỉ có ở restart loader.

**Cách xử lý:**

- Kiểm tra deserializer có cho truyền classloader không.
- Với Java object serialization trusted, cân nhắc `ConfigurableObjectInputStream` với TCCL.
- Nếu third-party library không hỗ trợ, xem update/issue của thư viện.
- Tắt restart nếu không thể khắc phục an toàn trong development.
- Không mở rộng khả năng deserialize untrusted objects chỉ để vượt lỗi classloader.

### 20.4. Shared JAR mới build không được phản ánh

**Triệu chứng:** sửa source một module, build JAR dependency nhưng code đang chạy vẫn dùng version cũ.

**Khả năng:**

- JAR đang ở base loader và không được reload theo một lần restart classloader.
- File watcher không theo dõi JAR như đang theo dõi classpath directories.
- Build tool không đưa JAR mới vào classpath của process hiện tại.
- IDE đang dùng cache hoặc project dependency khác với bản JAR vừa build.

**Cách xử lý:** xem CodeSource và classpath của runtime, rebuild và khởi động process mới nếu cần. `restart.include.*` có thể thay mapping của JAR trong **lần khởi động phù hợp**, nhưng không tự bảo đảm watcher theo dõi các thay đổi JAR ngay khi process còn chạy.

### 20.5. Memory tăng sau 30 lần restart

**Triệu chứng:** metaspace/class count tăng kéo dài và không giảm sau giai đoạn GC/steady state hợp lý.

**Khả năng:** static cache ở base loader giữ `Class<?>`/proxy từ R1, thread không stop hoặc TCCL còn trỏ loader cũ.

**Cách xử lý:** dùng heap dump để xem **retaining path**, cleanup listener registrations, thread pools và object references, sau đó test nhiều lượt restart. Không chỉ tăng `-XX:MaxMetaspaceSize` để che nguồn leak.

## 21. Thiết kế thư viện nội bộ thân thiện với DevTools

Nếu viết thư viện được nhiều ứng dụng Spring Boot sử dụng, nên tuân thủ:

1. **Đừng giữ static cache vô hạn của Class/Object** đến từ application context không còn sống.
2. Nếu cache metadata theo `Class<?>`, cần cơ chế clear/invalidate khi context đóng hoặc classloader thay đổi.
3. Có API `close()`/`unregister()` rõ cho listener, subscription và thread tự tạo.
4. Không dùng `Class.forName(name)` một cách máy móc khi type nằm ngoài defining loader của thư viện; cho phép cung cấp ClassLoader phù hợp hoặc dùng TCCL có kiểm soát.
5. Hỗ trợ class loading phù hợp trong serialization/reflection/annotation processing.
6. Dùng interface/model ổn định để truyền dữ liệu qua boundary; kiểm tra class identity khi cần.
7. Test library cả trong DevTools mode và fully packaged application.
8. Tránh yêu cầu bật remote DevTools ở production để vá lỗi runtime classpath.

**Khả năng tương thích với DevTools là vấn đề quản lý classloader và lifecycle**, không phải một annotation thần kỳ có thể gắn vào mọi class để hoàn tất.

## 22. Tốc độ restart: khi nào nhanh, khi nào lại chậm?

DevTools nhanh khi:

- Base chứa phần lớn thư viện lớn và ít thay đổi.
- Restart chỉ cần nạp application classes và tạo lại context phù hợp.
- IDE compile incremental thay vì build lại tất cả modules mỗi lần.
- Không có hàng loạt heavy startup jobs/remote calls bắt buộc.
- Không có cấu hình include quá rộng kéo nhiều JAR lớn vào restart.

Restart có thể vẫn chậm nếu:

- `@PostConstruct` thực hiện I/O rất lớn ở mọi lượt.
- Application runners migration/seed dữ liệu hoặc chờ remote services.
- Tạo context với nhiều integrations nặng.
- `restart.include.*` kéo quá nhiều dependencies từ base lên restart.
- Classpath watcher trigger nhiều lần vì IDE copy file liên tục.
- Memory leak giữ R1/R2 cũ làm GC và metaspace tăng.
- App đang chạy JDK/IDE/build mode không hỗ trợ classloader isolation như mong đợi.

**Không nhầm:** “base loader không nạp lại Spring JAR” **không có nghĩa** tất cả Spring beans, application context, database connections và web server đều được giữ nguyên. Spring context vẫn cần dựng lại; chỉ cơ chế nạp class được tối ưu hóa ở một phần.

## 23. Bảng cấu hình đúng loại vấn đề

| Triệu chứng hoặc mục tiêu | Công cụ | Không nên nhầm với |
| --- | --- | --- |
| Muốn xem app class có ở restart loader | `Class#getClassLoader()`, CodeSource | `Class.getName()` chỉ là tên |
| Sửa Java nhưng không thấy restart | Xác nhận `.class` đã update, watcher và build/IDE | `restart.include.*` không tự compile Java |
| Muốn thêm JAR shared vào restart loader | `META-INF/spring-devtools.properties`, `restart.include.*` | `spring.devtools.restart.additional-paths` |
| Muốn đẩy một directory module xuống base | `restart.exclude.*` | `spring.devtools.restart.exclude` |
| Chỉ không restart do CSS/templates | `spring.devtools.restart.additional-exclude` | Thay classloader của application |
| Muốn chủ động bấm restart | `spring.devtools.restart.trigger-file` | LiveReload browser-only |
| Tắt watcher nhưng giữ một phần DevTools | `spring.devtools.restart.enabled=false` ở app properties | Tắt classloader support hoàn toàn |
| Muốn tắt hẳn DevTools restart isolation | System property false **trước `run`** hoặc bỏ dependency | Đặt app property false muộn |
| Java deserialization không tìm class | Kiểm tra TCCL / serializer / type identity | Chỉ thêm `@ComponentScan` |
| Process mất memory sau nhiều restart | Kiểm tra base caches, threads, R1 retained references | Tăng heap không sửa leak |
| Fully packaged JAR không có restart loader | Hành vi production mặc định | Không phải lỗi Spring Boot |
| Custom launcher/AspectJ weaving | Xem giới hạn hỗ trợ | Không cố ép mọi thiết lập devtools hoạt động |

## 24. Checklist thực hành

- [ ] Đã khai báo `spring-boot-devtools` là dependency dành cho development.
- [ ] Chạy ứng dụng bằng IDE hoặc `bootRun`/`spring-boot:run` phù hợp để thử restart.
- [ ] Biết IDE/build có biên dịch lại `.class` trong classpath directory không.
- [ ] Đã phân biệt base classloader và restart classloader ở runtime.
- [ ] Không coi cùng tên class là cùng runtime type khi defining loader khác.
- [ ] Đã kiểm tra classloader và CodeSource trước khi điều chỉnh cấu hình multi-module.
- [ ] Biết `restart.include.*` / `restart.exclude.*` nằm trong `META-INF/spring-devtools.properties`.
- [ ] Không nhầm chúng với `spring.devtools.restart.exclude` theo dõi file.
- [ ] Mỗi key `restart.include.<name>`/`restart.exclude.<name>` là duy nhất.
- [ ] Regex classpath entry đủ hẹp và đã kiểm tra với đường dẫn thực tế.
- [ ] Không suy luận include JAR tự động kích hoạt watcher cho mọi thay đổi JAR.
- [ ] Đã loại hoặc cleanup static caches giữ class/object từ restart loader cũ.
- [ ] Custom threads/executors được dừng và không giữ TCCL của R1.
- [ ] Deserializer/reflection library có cách chọn loader phù hợp khi cần.
- [ ] Không deserialize dữ liệu không tin cậy bằng Java ObjectInputStream.
- [ ] Không tắt SpringApplication shutdown hook nếu còn dùng DevTools restart.
- [ ] Đã thử **tắt hoàn toàn restart** trước khi khẳng định lỗi là do DevTools.
- [ ] Có phép thử cả development restart và packaged `java -jar`.
- [ ] Không đưa remote DevTools hoặc ép restart vào production.
- [ ] Không lấy một kết quả nhanh chậm của restart làm chứng cứ duy nhất về hiệu năng.

## 25. Câu hỏi và bài tập củng cố

### Bài 1: cùng tên, khác loader

Có hai `Class<?>` cùng tên `demo.Order`, một do R1 nạp, một do R2 nạp. `R1Class == R2Class` đúng hay sai? Vì sao?

**Gợi ý:** identity type gồm binary name và defining classloader. Cùng tên không đủ.

### Bài 2: xác định entry nào ở base

Một dependency `my-lib-1.0.jar` được thêm vào classpath và không có cấu hình DevTools đặc biệt. Nó thường ở đâu?

**Đáp án:** base classloader, vì là JAR thông thường.

### Bài 3: module đang mở

`shared-domain` là module đang mở trong IDE và chạy dưới dạng class output directory. Nó thường được loader nào quản lý?

**Đáp án:** restart classloader theo cách phân chia mặc định cho open projects.

### Bài 4: sửa mã nhưng không restart

Lưu `OrderService.java` nhưng file `OrderService.class` trên classpath không thay đổi. DevTools có đủ tín hiệu để restart class của bạn không?

**Đáp án:** không nhất thiết; cần cập nhật classpath output bằng compile/build phù hợp.

### Bài 5: phân biệt hai exclude

Giải thích sự khác nhau:

```properties
spring.devtools.restart.additional-exclude=docs/**
```

và trong `META-INF/spring-devtools.properties`:

```properties
restart.exclude.docs-module=.*/docs-module/build/classes/.*
```

**Gợi ý:** một cái là loại resource khỏi trigger restart; cái kia chọn classpath entry cho base classloader.

### Bài 6: serializer dùng sai loader

Một thư viện nằm ở base load đối tượng Java serialized có kiểu application ở restart. Vì sao có thể `ClassNotFoundException`? Chọn cách kiểm tra và sửa phù hợp.

**Gợi ý:** thử TCCL/`ConfigurableObjectInputStream` trên dữ liệu trusted, cập nhật library hoặc tắt restart nếu không hỗ trợ.

### Bài 7: restart leak

Sau 20 lượt restart, heap dump cho thấy `SharedRegistry.CACHE` của một JAR base vẫn giữ `Class<?>` thuộc R1. Cần xử lý ở đâu?

**Gợi ý:** dọn cache và lifecycle của registration, không chỉ đặt `restart.include.*` bừa bãi.

### Bài 8: tắt restart

Vì sao `spring.devtools.restart.enabled=false` trong `application.properties` không phải phép thử tốt nhất để loại trừ mọi rủi ro hai classloaders? Cách tắt hoàn toàn nào nên thử?

**Gợi ý:** set **system property trước `SpringApplication.run`**, hoặc bỏ devtools.

### Bài 9: kiểm chứng bằng mã Java thuần

Chạy `LoaderIdentityDemo` mục 8. Sau khi có hai `Class<?>` với cùng tên, giải thích vì sao `isAssignableFrom` trả false và `cast` ném exception.

### Bài 10: lựa chọn đúng sửa lỗi

Một custom annotation nằm trong một module JAR mà một library reflection ở base giữ cache. Bạn sẽ:

1. In loader/CodeSource.
2. Xem cache có bám type cũ sau restart không.
3. Chọn include module JAR nếu cần.
4. Test multiple restarts và memory.

Tại sao chỉ thêm `@ComponentScan` không đủ để giải quyết mọi trường hợp classloader mismatch?

## 26. Tóm tắt chính xác cần nhớ

1. **DevTools chia classpath thành hai lớp:** base classloader giữ library classes ít đổi; restart classloader nạp application classes thay đổi thường xuyên. Đây là tối ưu **nạp class**, không phải “khởi động lại toàn JVM”.
2. Khi restart, **restart classloader cũ được thay bằng loader mới**, còn base vẫn được tái sử dụng. Những class cùng tên qua R1/R2 có thể là **hai runtime types khác nhau**.
3. **Mặc định:** project/module mở trong IDE và class directory của app thường ở restart; JAR phụ thuộc thường ở base. Multi-module xây dưới dạng directory hay JAR có thể làm kết quả khác.
4. **`META-INF/spring-devtools.properties`** với `restart.include.*`/`restart.exclude.*` dùng regex **trên classpath entries** để chọn loader; khác hoàn toàn `spring.devtools.restart.exclude`/`additional-paths` vốn điều khiển **theo dõi file**.
5. **Restart cần classpath thay đổi:** sửa `.java` phải được compile/copy thành `.class`. LiveReload browser không thay thế Java classloader restart.
6. **ClassCastException, reflection, annotation detection, serializer và static caches** là các điểm cần kiểm tra khi có hai classloaders. Không quy mọi lỗi type cho DevTools trước khi đo thực tế.
7. **TCCL** giúp library tìm application classes trong một số tình huống, nhưng thread TCCL giữ R1 có thể khiến loader cũ không được GC.
8. **Tắt app property false** thường chỉ ngừng watcher; muốn loại bỏ hoàn toàn restart classloader để chẩn đoán, đặt **system property false trước `run`** hoặc loại dependency.
9. **Production packaged JAR** thường không chạy DevTools restart; không bật ép DevTools trong production.
10. Muốn chẩn đoán đáng tin, hãy **in classloader + class origin**, thử A/B không restart, sửa classpath partition với regex hẹp, rồi chạy lại nhiều lượt restart.

### Tài liệu chính thức

- [Spring Boot 3.3 — Developer Tools](https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html): Restart vs Reload, base/restart classloader, classpath watching, multi-module, cấu hình `spring-devtools.properties` và known limitations.
- [Spring Boot 3.3 — Running Your Application](https://docs.spring.io/spring-boot/3.3/reference/using/running-your-application.html): các cách khởi động trong môi trường development.
- [Java 17 — ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): nạp/ủy quyền class và vai trò của defining loader.
- [Java 17 — URLClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): ví dụ hai classloader độc lập.
- [Spring Framework — ConfigurableObjectInputStream](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/ConfigurableObjectInputStream.html): truyền classloader khi đọc Java serialization trong trường hợp cần thiết.
