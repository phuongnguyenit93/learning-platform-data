# Đọc metadata bằng ASM và giới hạn của việc tránh nạp lớp trong Spring Boot

## 1. Câu hỏi cốt lõi: tại sao có thể kiểm tra class mà không cần nạp class?

Trong Spring Boot, tính năng **auto-configuration** phải quyết định liệu một cấu hình có phù hợp với classpath hay không. Ví dụ: chỉ tự cấu hình JDBC khi những kiểu JDBC cần thiết có mặt; chỉ tạo cơ chế Jackson khi các kiểu Jackson thích hợp có mặt. Điều kiện phổ biến là `@ConditionalOnClass` và `@ConditionalOnMissingClass`.

Nhưng có một bài toán rất thực tế: **làm sao đọc thông tin về một class chứa tham chiếu tới thư viện tùy chọn mà không buộc JVM nạp chính class ấy quá sớm?** Nếu framework phải nạp mọi class cấu hình để khám phá annotation, những tham chiếu tới dependency vắng mặt có thể gây `NoClassDefFoundError`, `ClassNotFoundException` hoặc lỗi liên kết trước khi điều kiện kịp trả lời “không đủ điều kiện”.

Spring Framework sử dụng **ASM**, một thư viện đọc bytecode Java, để đọc metadata của file `.class` mà không nhất thiết phải định nghĩa/nạp class đó thành đối tượng `Class<?>` trong JVM. Nhờ đó, bộ quét classpath và bộ phân tích cấu hình có thể khám phá tên lớp, annotation, superclass, interface và metadata phương thức trước khi cần làm việc với kiểu Java thật.

Tuy nhiên: **“đọc metadata mà không nạp lớp” không có nghĩa “toàn bộ khởi động Spring sẽ không nạp lớp”, “mã optional sẽ không bao giờ bị liên kết”, hoặc “thiếu bất kỳ dependency nào cũng an toàn”**. Chính những giới hạn này là phần quan trọng nhất của bài.

~~~text
       Classpath: JAR / BOOT-INF/classes / classes directory
                              |
                              v
                      Resource / .class bytes
                              |
                ASM phân tích cấu trúc bytecode
                              |
          ClassMetadata / AnnotationMetadata / MethodMetadata
                              |
                  nhận biết class + annotation
                              |
                    @ConditionalOnClass ?
                              |
                   +----------+----------+
                   |                     |
             class có mặt             class thiếu
                   |                     |
             tiếp tục xét           skip cấu hình
                   |
              có thể đến bước
             nạp/làm việc với class
                   |
        JVM loading -> linking -> initialization
                   |
                  tạo bean
~~~

**Mục tiêu sau bài:** bạn hiểu cách Spring đọc metadata bằng ASM, phân biệt bước quét metadata với class loading/linking/initialization, biết cách viết điều kiện classpath an toàn, chỉ ra khi nào việc tránh nạp class không đủ để bảo vệ code, và có thể tự chạy một thí nghiệm Java 17/Spring Boot để kiểm chứng.

## 2. ASM là gì và Spring dùng nó ra sao?

**ASM** là thư viện thao tác bytecode Java. Một chương trình có thể mở file `.class` như dữ liệu nhị phân, phân tích các mục trong constant pool, bảng annotation, chữ ký kiểu và cấu trúc method mà không gọi `Class.forName(...)` để nạp class đang đọc.

Trong Spring, nhiều API được thiết kế cho công việc này:

| Thành phần | Vai trò chính | Nhận xét |
| --- | --- | --- |
| `Resource` | Đại diện tài nguyên classpath, file, URL... | Có thể truy cập byte của file `.class` |
| `MetadataReader` | Cổng đọc metadata của một class | Cung cấp `ClassMetadata` và `AnnotationMetadata` |
| `MetadataReaderFactory` | Tạo `MetadataReader` theo tên class hoặc `Resource` | Cách vào API thuận tiện |
| `SimpleMetadataReaderFactory` | Triển khai đọc metadata đơn giản | Đọc resource mỗi lần cần theo cách của factory |
| `CachingMetadataReaderFactory` | Caching kết quả metadata reader | Phù hợp quét nhiều class trong một classpath |
| `ClassMetadata` | Tên lớp, superclass, interfaces, flags... | Không cần instance của lớp đang đọc |
| `AnnotationMetadata` | Annotation trên class và metadata liên quan | Có thể tra cứu annotation theo tên |
| `MethodMetadata` | Metadata method (như method `@Bean`) | Không cần gọi method |
| `org.springframework.asm.*` | ASM được Spring đóng gói lại trong namespace Spring | Chủ yếu là hạ tầng, không cần gọi trực tiếp cho phần lớn app |

Có thể hiểu đơn giản:

~~~text
Resource (.class bytes)
    -> MetadataReaderFactory
       -> MetadataReader
          -> ClassMetadata
          -> AnnotationMetadata
             -> MethodMetadata nếu cần
~~~

Phần lớn ứng dụng **không cần tự dùng ASM cấp thấp**. Đọc `MetadataReader`/`AnnotationMetadata` là cách phù hợp hơn khi bạn xây công cụ khám phá class, viết thư viện hạ tầng hoặc điều tra scanner.

### Tên class là string, chưa phải đối tượng `Class<?>`

Khi gọi:

~~~java
MetadataReader reader =
    new SimpleMetadataReaderFactory()
        .getMetadataReader("example.optional.ExampleClient");
~~~

factory cố tìm tài nguyên class tương ứng, chẳng hạn `example/optional/ExampleClient.class`, rồi đọc metadata. Nếu tài nguyên không tồn tại, việc đọc có thể ném `IOException`; đây không phải cùng một tình huống với `ClassNotFoundException` từ `Class.forName`.

*Đoạn này minh họa API; muốn chạy cần import `org.springframework.core.type.classreading.MetadataReader`, `SimpleMetadataReaderFactory`, xử lý `IOException` và có class/resource tương ứng.*

Không nên suy rằng `getMetadataReader` chấp nhận một tên class thì mọi dependency mà class ấy nhắc tới đều đã sẵn sàng. Nó mới đọc dữ liệu bytecode ở cấp được yêu cầu.

## 3. Ba khái niệm JVM phải phân biệt

Không thể hiểu giới hạn ASM nếu gộp cả ba thành “load class”.

### 3.1. Loading — nạp/định nghĩa class

JVM tìm biểu diễn nhị phân của một kiểu và tạo đối tượng `Class<?>` đại diện cho kiểu đó. Class loader có thể tham gia đọc byte và định nghĩa class. Khi dùng `Class.forName(String, boolean, ClassLoader)` với `initialize=false`, bạn đang **yêu cầu nạp** kiểu theo JVM, nhưng không yêu cầu khởi tạo nó ngay.

### 3.2. Linking — liên kết class

Theo mô hình JVM, linking bao gồm verification, preparation và resolution. Một số hoạt động resolution có thể trì hoãn; thời điểm chi tiết phụ thuộc hành vi VM và đường thực thi. Trong quá trình này JVM có thể phải giải quyết thêm những kiểu/phụ thuộc.

### 3.3. Initialization — khởi tạo class

Initialization thực thi các static initializer và việc gán các static field không phải hằng compile-time theo quy tắc JVM. Chẳng hạn:

~~~java
public final class NoisyType {
    static {
        System.out.println("static-init=NoisyType");
    }
}
~~~

Khi class được **khởi tạo**, dòng đó sẽ được in. Chỉ đọc file `NoisyType.class` như tài nguyên bằng ASM không chạy static initializer của `NoisyType`.

**Chú ý quan trọng:** `Class.forName(name, false, loader)` vẫn là **class loading**, dù chưa chạy initializer. Bởi vậy hai câu sau không tương đương:

- “MetadataReader không cần nạp class mục tiêu”: ý nói đọc bytecode mà không cần tạo `Class<?>` của class ấy.
- “Class.forName với initialize=false không khởi tạo class”: JVM vẫn nạp và có thể liên kết class, chỉ không yêu cầu chạy initialization ngay.

### Bảng đối chiếu

| Thao tác | Có cần `Class<?>` của class mục tiêu? | Có chạy static initializer của class mục tiêu? |
| --- | --- | --- |
| `MetadataReaderFactory.getMetadataReader("a.B")` | Không | Không |
| `ClassLoader.getResource("a/B.class")` | Không | Không |
| `Class.forName("a.B", false, loader)` | Có: yêu cầu loading | Không, theo ý nghĩa tham số `initialize=false` |
| `Class.forName("a.B")` | Có | Có, khi thành công theo overload này |
| `new B()` | Có | Có trước lần tạo instance đầu tiên nếu chưa được khởi tạo |
| `B.class` | Tạo/trả `Class<?>`, không đòi khởi tạo ngay | Không nhất thiết |
| Phản chiếu gọi method/đọc static field không phải constant | Có thể yêu cầu linking/initialization | Tùy thao tác và quy tắc JVM |

Không dựa vào `getResource` như bằng chứng rằng file class hợp lệ hoặc mọi kiểu phụ thuộc đầy đủ: nó chỉ báo khả năng tìm tài nguyên dưới đường dẫn đó.

## 4. Metadata của class có gì, và thiếu gì?

`ClassMetadata` giúp đọc những dữ liệu như:

- `getClassName()`: tên class được ghi trong bytecode.
- `getSuperClassName()`: tên superclass, có thể trả `null` ở trường hợp không có.
- `getInterfaceNames()`: tên interface ở dạng chuỗi.
- `isInterface()`, `isAbstract()`, `isFinal()`: thông tin modifier tương ứng.
- `isIndependent()`: class có độc lập về mặt enclosing class theo metadata hay không.

`AnnotationMetadata` cho phép xem các annotation của class:

~~~java
boolean annotated = reader.getAnnotationMetadata()
    .hasAnnotation("example.annotations.FeatureFlagged");
~~~

Nó trả `boolean` dựa trên metadata, **không đòi tạo instance của class có annotation**. Lưu ý `hasAnnotation` kiểm tra annotation có mặt trực tiếp theo API tương ứng; nếu cần xem meta-annotation hay các attribute gộp, phải chọn API phù hợp thay vì mặc định mọi kiểu tra cứu là như nhau.

### Metadata không phải reflection hoàn chỉnh

| Việc muốn biết | ASM/metadata giúp gì? | Giới hạn |
| --- | --- | --- |
| Class có annotation tên X không? | Có thể kiểm tra qua metadata | Có thể cần phân tích meta-annotation hoặc alias rõ ràng |
| Class implements tên interface nào? | Có thể đọc danh sách tên interface khai báo | Không tự xác thực toàn bộ hệ phân cấp runtime |
| Có class `a.B` ở classpath không? | Có thể tra cứu tài nguyên `a/B.class` | Không bảo đảm class đó nạp/liên kết thành công |
| Static initializer làm gì? | Đọc bytecode có thể nhìn thấy instruction | Không thực thi hoặc xác nhận hành vi runtime |
| Constructor có tạo kết nối DB không? | Bytecode có thể được phân tích nâng cao | Không nên dùng ASM để “giả chạy” mọi luồng nghiệp vụ |
| Bean nào sẽ xuất hiện sau điều kiện? | Metadata là một đầu vào | Còn điều kiện khác, registration, dependency, lifecycle |
| Class có dependency optional đầy đủ không? | Không thể kết luận chỉ từ class file hiện diện | Cần kiểm tra runtime linking/đường thực thi |
| Class từ JAR nào được JVM chọn? | Resource có thể cho manh mối | Class loader order, nesting, module path có thể phức tạp |

Đừng nhầm “đọc bytecode được” với “chắc chắn object Java có thể hoạt động bình thường”.

## 5. Vì sao `@ConditionalOnClass` thường an toàn với dependency tùy chọn?

Trong Spring Boot 3.3, `@ConditionalOnClass` cho phép viết:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.optional.OptionalClient")
public class OptionalClientAutoConfiguration {
}
~~~

Điều kiện kiểm tra sự hiện diện của lớp `com.vendor.optional.OptionalClient` trên classpath; nếu thiếu, auto-configuration có thể bị bỏ qua trước khi Spring xử lý sâu các thành phần bên trong.

Spring Boot còn hỗ trợ cú pháp dùng class literal:

~~~java
@AutoConfiguration
@ConditionalOnClass(com.vendor.optional.OptionalClient.class)
public class OptionalClientAutoConfiguration {
}
~~~

**Hai đoạn này chỉ minh họa ý tưởng, không biên dịch được nếu thiếu class `OptionalClient` tại compile time.** Cú pháp `name` dùng string, nên có thể biên dịch mà không có class tùy chọn. Cú pháp `value = SomeType.class` yêu cầu class có trong compile classpath.

Điểm tinh tế trong tài liệu Boot: khi `@ConditionalOnClass` được đặt **trực tiếp trên một lớp cấu hình**, thuộc tính `value` có thể được đọc từ annotation metadata bằng ASM trước khi Spring cần nạp class cấu hình. Vì vậy việc class được tham chiếu từ attribute `value` không đương nhiên gây nạp kiểu optional ngay tại bước điều kiện.

Tuy nhiên, điều này có ranh giới:

- Sự bảo vệ phụ thuộc **vị trí annotation**, các bước Spring xử lý và việc lớp cấu hình không vô tình bị nạp sớm bởi nơi khác.
- Khi `@ConditionalOnClass` nằm trong một **meta-annotation** tự định nghĩa, tài liệu Boot yêu cầu dùng `name` để tránh các tình huống việc tham chiếu class không được xử lý an toàn như khi annotation được gắn trực tiếp.
- Method `@Bean` có kiểu trả về, tham số, superclass hoặc interface tham chiếu đến lớp optional có thể khiến JVM phải giải quyết kiểu **trước khi điều kiện trên method kịp tác dụng**. Khi đó nên tách cấu hình riêng, gắn điều kiện lên class bao ngoài.
- Các ngoại lệ do khởi tạo bean hoặc nạp library ở giai đoạn sau không được “ASM che chắn”.

### `value` hay `name`?

| Cách viết | Ưu điểm | Giới hạn |
| --- | --- | --- |
| `@ConditionalOnClass(OptionalType.class)` | Compile-time type safety, IDE refactor | Cần kiểu ở compile classpath; an toàn tùy vị trí xử lý |
| `@ConditionalOnClass(name="vendor.OptionalType")` | Không cần import/literal class khi biên dịch | Dễ sai chính tả; đổi package không tự cập nhật |
| `@ConditionalOnMissingClass("vendor.OptionalType")` | Chỉ bật khi class đó không có | Phải hiểu vì sao muốn cấu hình fallback |
| `@ConditionalOnClass({A.class, B.class})` | AND: đòi mọi class đã liệt kê | Cần bảo đảm class literals có thể biên dịch |
| `@ConditionalOnClass(name={"a.A","b.B"})` | AND theo tên nhiều kiểu | Kiểu được kiểm tra theo tên, không phải đầy đủ API runtime |

Trong thư viện thực tế, chọn điều kiện thể hiện đúng **dependency mà một bean thật sự cần**. Đừng dùng sự hiện diện của một class bất kỳ làm bằng chứng rằng cả một thư viện đã đủ thành phần.

## 6. Trường hợp đặc biệt: meta-annotation và class literal

Giả sử bạn định nghĩa annotation tổng hợp:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(OptionalClient.class)
public @interface ConditionalOnOptionalClient {
}
~~~

*Đoạn trên chỉ minh họa rủi ro; cần import và kiểu `OptionalClient` mới biên dịch được.*

Tài liệu Boot lưu ý với `@ConditionalOnClass` được sử dụng như **meta-annotation**, cách tham chiếu class qua `value` không được xử lý bảo đảm như trường hợp trực tiếp. Viết bằng `name`:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.optional.OptionalClient")
public @interface ConditionalOnOptionalClient {
}
~~~

*Đây là đoạn minh họa annotation cần import `ElementType`, `RetentionPolicy`, `ConditionalOnClass` nếu muốn đưa vào project; không phải file độc lập.*

**Vì sao cần ghi rõ?** Metadata có thể được phân tích theo những đường khác nhau. Không nên hiểu rằng mọi annotation ở mọi tầng lồng nhau được xử lý hoàn toàn bằng ASM với cùng cam kết không nạp class.

## 7. Trường hợp nguy hiểm: `@Bean` trả về kiểu của thư viện optional

Đây là lỗi thiết kế thường gặp:

~~~java
@Configuration(proxyBeanMethods = false)
public class BadConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.vendor.optional.OptionalClient")
    public com.vendor.optional.OptionalClient optionalClient() {
        return new com.vendor.optional.OptionalClient();
    }
}
~~~

**Phản ví dụ**: nó chỉ biên dịch khi library optional có mặt ở compile time; nếu thư viện bị bỏ khỏi runtime, có thể gặp lỗi xử lý phương thức trước khi Spring áp dụng điều kiện method.

Vấn đề là **kiểu trả về của method** chứa tên lớp optional. JVM, reflection hoặc cơ chế phân tích configuration có thể cần giải quyết chữ ký method trước khi condition ở method ngăn registration. ASM giúp việc đọc metadata ở nhiều giai đoạn, nhưng không bảo đảm mọi lần xử lý method đều tránh class loading.

### Cách viết an toàn hơn: cấu hình riêng có điều kiện trên class

~~~java
@Configuration(proxyBeanMethods = false)
public class RootConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.optional.OptionalClient")
    static class OptionalClientConfiguration {

        @Bean
        com.vendor.optional.OptionalClient optionalClient() {
            return new com.vendor.optional.OptionalClient();
        }
    }
}
~~~

*Đây là khung mẫu cần thư viện optional tại compile time; class ngoài/inner và import đầy đủ mới tạo thành file biên dịch hoàn chỉnh.*

Ở đây `OptionalClientConfiguration` được cách ly trong **class cấu hình riêng**, điều kiện ở cấp class có thể được Spring xét dựa trên metadata **trước khi phải xử lý sâu những method có chữ ký optional**. Việc dùng nested static configuration là một cách phổ biến của Spring Boot để cô lập các API của thư viện tùy chọn.

**Tối quan trọng:** cách ly này không phải “thuốc chữa mọi lỗi classpath”. Nếu superclass/annotation/custom code tải kiểu optional quá sớm, nếu class cấu hình bị tham chiếu qua reflection trực tiếp, hoặc nếu một library khác đã kích hoạt việc nạp, vẫn có thể gặp lỗi. Hãy giữ phần phụ thuộc optional chỉ trong cấu hình được bảo vệ phù hợp.

### Không dùng `@Bean` method condition như tường chắn tuyệt đối

Sai lầm là suy luận “vì trên method có `@ConditionalOnClass` nên JVM không bao giờ đọc chữ ký của method ấy”. Method signature có thể được JVM/phân tích Spring xem xét ở thời điểm khác, tùy loại cấu hình và đường thực thi. Tài liệu Boot khuyên tách sang một class `@Configuration` riêng trong tình huống cần cô lập dependency tùy chọn.

## 8. Thí nghiệm đầy đủ: đọc metadata nhưng chưa khởi tạo class

Phần này cung cấp project **Spring Boot 3.3.13 + Java 17 + Maven 3.9+** chạy ở chế độ console. Mục tiêu không phải làm REST API mà là quan sát trực tiếp bốn sự kiện:

1. `MetadataReader` đọc metadata của một class chưa được khởi tạo.
2. `Class.forName(name, false, loader)` nạp kiểu nhưng không khởi tạo.
3. `Class.forName(name)` khởi tạo và kích hoạt static initializer.
4. `@ConditionalOnClass(name="...")` có thể bỏ qua một auto-configuration nếu tên kiểu tùy chọn hoàn toàn không tồn tại.

### 8.1. Cấu trúc dự án

~~~text
asm-metadata-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── app/
    │   │   └── DemoApplication.java
    │   ├── target/
    │   │   ├── Marker.java
    │   │   └── NoisyType.java
    │   └── autoconfigure/
    │       └── MissingClientAutoConfiguration.java
    └── resources/META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Class `DemoApplication` nằm trong package `demo.app`. Class thí nghiệm và class auto-configuration được đặt ngoài package scan mặc định để **không vô tình nạp chúng qua component scan của app**. Auto-configuration được liệt kê qua imports, còn `NoisyType` chỉ được đọc metadata và sau đó nạp chủ động.

### 8.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>asm-metadata-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter` đã cung cấp Spring Core và công cụ metadata reading. Ta không cần khai báo ASM dependency trực tiếp; Spring sử dụng phần ASM được đóng gói cùng Spring Core cho các thao tác tương ứng.

### 8.3. `src/main/java/demo/target/Marker.java`

~~~java
package demo.target;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface Marker {
}
~~~

Đây là một annotation marker độc lập. Giữ retention runtime để minh họa rõ annotation được ghi trong class file và có thể được reflection nhìn thấy khi cần; ASM cũng có thể đọc metadata trực tiếp từ bytecode.

### 8.4. `src/main/java/demo/target/NoisyType.java`

~~~java
package demo.target;

@Marker
public final class NoisyType {
    static {
        System.setProperty("demo.target.initialized", "true");
        System.out.println("static-init=NoisyType");
    }

    private NoisyType() {
    }
}
~~~

Static initializer đánh dấu trạng thái khởi tạo bằng một system property và in một dòng. Đó là **side effect được đặt trong class đích để minh họa thời điểm initialization**, không phải hành vi nên đặt trong điều kiện Spring.

Vì class không được component scan từ `demo.app` và không được khai báo thành bean, việc khởi tạo trong ví dụ sẽ chỉ được kích hoạt bằng thao tác `Class.forName(...)` có chủ đích ở `main`.

### 8.5. `src/main/java/demo/autoconfigure/MissingClientAutoConfiguration.java`

~~~java
package demo.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "demo.missing.OptionalClient")
public class MissingClientAutoConfiguration {

    @Bean
    public String guardedText() {
        return "should-not-exist";
    }
}
~~~

`demo.missing.OptionalClient` cố ý **không được tạo** trong project và không được thêm dependency. Bởi vậy `@ConditionalOnClass(name=...)` không đạt, và phương thức `guardedText` không đóng góp bean.

Điều kiện được gắn **trực tiếp trên class auto-configuration**, không phải method. Đây là lựa chọn an toàn và đơn giản để bảo vệ một cấu hình khi class cần thiết không hiện diện.

### 8.6. Tệp đăng ký ứng viên

Tạo chính xác file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung duy nhất:

~~~text
demo.autoconfigure.MissingClientAutoConfiguration
~~~

Spring Boot 3.x sẽ xem xét class này khi `@EnableAutoConfiguration` có hiệu lực qua `@SpringBootApplication`, rồi điều kiện về classpath khiến cấu hình không khớp.

### 8.7. `src/main/java/demo/app/DemoApplication.java`

~~~java
package demo.app;

import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.core.type.classreading.MetadataReader;
import org.springframework.core.type.classreading.SimpleMetadataReaderFactory;

@SpringBootApplication(scanBasePackages = "demo.app")
public class DemoApplication {

    public static void main(String[] args) throws Exception {
        try (ConfigurableApplicationContext context =
                 new SpringApplicationBuilder(DemoApplication.class)
                     .web(WebApplicationType.NONE)
                     .bannerMode(Banner.Mode.OFF)
                     .run(args)) {

            String className = "demo.target.NoisyType";

            MetadataReader reader =
                new SimpleMetadataReaderFactory()
                    .getMetadataReader(className);

            System.out.println("metadataName=" +
                reader.getClassMetadata().getClassName());
            System.out.println("marker=" +
                reader.getAnnotationMetadata()
                    .hasAnnotation("demo.target.Marker"));
            System.out.println("initializedAfterMetadata=" +
                Boolean.getBoolean("demo.target.initialized"));

            ClassLoader loader = DemoApplication.class.getClassLoader();
            Class.forName(className, false, loader);

            System.out.println("initializedAfterLoad=" +
                Boolean.getBoolean("demo.target.initialized"));

            Class.forName(className);

            System.out.println("initializedAfterInitialize=" +
                Boolean.getBoolean("demo.target.initialized"));

            System.out.println("guardedBean=" +
                context.containsBean("guardedText"));

            ConditionEvaluationReport.ConditionAndOutcomes outcome =
                ConditionEvaluationReport.get(context.getBeanFactory())
                    .getConditionAndOutcomesBySource()
                    .get("demo.autoconfigure.MissingClientAutoConfiguration");

            System.out.println("missingClientConditionMatched=" +
                (outcome != null && outcome.isFullMatch()));
        }
    }
}
~~~

Lưu ý: import `org.springframework.context.annotation.Import` không cần thiết trong file trên; Java không lỗi vì import thừa, nhưng bạn có thể bỏ để code gọn. Những tên class của target được truyền bằng **chuỗi** để tránh vô tình tham chiếu class literal trong code kiểm nghiệm.

Cách đọc kết quả:

- `getMetadataReader(className)` đọc file `NoisyType.class` như một tài nguyên của classpath.
- `getClassMetadata().getClassName()` nhận tên kiểu từ bytecode.
- `getAnnotationMetadata().hasAnnotation(...)` phát hiện `@Marker` trên bytecode.
- `Boolean.getBoolean(...)` trả true khi system property có giá trị chuỗi “true”; đây là phép đo trạng thái static initializer.
- `Class.forName(className,false,loader)` yêu cầu class loading nhưng không initialization.
- `Class.forName(className)` yêu cầu initialization, làm dòng static initializer in ra.
- `guardedBean` kiểm tra bean có mặt trong context hay không; do class optional vắng mặt, phải là `false`.
- `ConditionEvaluationReport` cho biết trạng thái các điều kiện được Boot ghi nhận; `isFullMatch()` của cấu hình này không thể true khi class cần thiết vắng mặt.

Trong chương trình chỉ dùng những API cần thiết để thấy ranh giới giữa **metadata read** và **JVM initialization**; không gọi `getBean(...)` chỉ để kiểm tra classpath.

### 8.8. Biên dịch và chạy

Từ thư mục chứa `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q clean package
java -jar target/asm-metadata-demo-1.0.0.jar
~~~

Các dòng do mã của chương trình và static initializer in ra, theo thứ tự:

~~~text
metadataName=demo.target.NoisyType
marker=true
initializedAfterMetadata=false
initializedAfterLoad=false
static-init=NoisyType
initializedAfterInitialize=true
guardedBean=false
missingClientConditionMatched=false
~~~

Spring Boot có thể in thêm thông điệp logging; khối trên chỉ mô tả các dòng kiểm chứng do ví dụ tạo ra, không cam kết toàn bộ stdout/stderr chỉ chứa tám dòng.

**Giải thích ba dòng trọng tâm:**

1. `initializedAfterMetadata=false`: đọc class file bằng Spring MetadataReader **không chạy static initializer**.
2. `initializedAfterLoad=false`: `Class.forName(...,false,...)` đã yêu cầu nạp kiểu nhưng không khởi tạo.
3. `static-init=NoisyType` xuất hiện giữa hai phép đo vì `Class.forName(className)` thực hiện initialization lần đầu.

Dòng `missingClientConditionMatched=false` minh họa rằng Boot không cần tạo bean `guardedText` khi điều kiện classpath không đạt.

**Điều kiện giả định để kết quả có thể đối chiếu:** khởi chạy một JVM mới, không đặt trước system property `demo.target.initialized=true`; không thêm code khác chủ động khởi tạo `NoisyType` trước phép đo. Hai điều kiện ấy được bảo đảm trong project mẫu như trình bày.

## 9. Thí nghiệm mở rộng: khi class file có mặt nhưng phụ thuộc bị thiếu

Giả sử class `com.vendor.client.FancyClient` tồn tại trong JAR và bytecode của nó tham chiếu `com.vendor.transport.TransportProtocol` — một lớp thuộc dependency **không có ở runtime**.

Một công cụ đọc class file bằng ASM vẫn có thể đọc nhiều metadata của `FancyClient` từ tài nguyên, vì nó chủ yếu đọc cấu trúc bytecode. Nhưng một thao tác thật có thể thất bại:

~~~text
FancyClient.class -> đọc bằng ASM: có thể thành công
                 -> Class.forName(...): có thể fail khi load/link
                 -> new FancyClient(...): có thể fail khi resolve dependency
                 -> gọi một method: có thể fail ở lần resolve kiểu/method liên quan
~~~

**Không đưa ra kết luận “`Class.forName(false)` chắc chắn thất bại” hoặc “chắc chắn thành công”** cho mọi trường hợp thiếu dependency. Thời điểm resolution/linking của JVM và kiểu tham chiếu (superclass, interface, descriptor, annotation, instruction...) khác nhau. Một số sự cố xuất hiện khi nạp, số khác chỉ xuất hiện khi gọi method cụ thể.

Các exception/error có thể gặp trong các bối cảnh khác nhau:

| Hiện tượng | Ví dụ lỗi | Cách hiểu |
| --- | --- | --- |
| Không tìm được chính class cần nạp | `ClassNotFoundException` | Lookup qua API phản chiếu hoặc loader không tìm thấy tên kiểu |
| Class cần nạp tham chiếu kiểu thiếu | `NoClassDefFoundError` | JVM không tìm được definition khi cần resolution |
| Không khớp binary API giữa các version | `NoSuchMethodError` / `NoSuchFieldError` | Binary incompatibility khi liên kết/lúc thực thi |
| Không tương thích hierarchy/interface | `IncompatibleClassChangeError` | Binary linkage sai kỳ vọng |
| Initializer ném exception | `ExceptionInInitializerError` | Initialization đã được kích hoạt và thất bại |
| Code trong method cố sử dụng dependency thiếu | Có thể là `NoClassDefFoundError` hoặc linkage error khác | Tùy điểm JVM giải quyết dependency |

**Điểm cốt lõi:** metadata reading là kỹ thuật tránh nạp **class đang được khảo sát trong một giai đoạn**. Nó không xác nhận transitive dependency graph, không bảo đảm binary compatibility, không thay JVM verifier/linker và không bảo đảm bean có thể tạo thành công.

## 10. Khi nào ASM vẫn có thể phải đọc class khác?

Việc `MetadataReader` đọc class A không có nghĩa hạ tầng Spring không bao giờ đọc metadata class B:

- Để phân tích meta-annotation, Spring có thể cần metadata của annotation khác.
- Để xác định candidate qua superclass/interface hoặc cấu hình được import, Spring có thể đọc thêm metadata của kiểu liên quan.
- Để xử lý `@Configuration`, Spring có thể cần phân tích method `@Bean`, annotation tổng hợp và quan hệ import.
- Một `Condition` custom có thể tự gọi `ClassUtils.isPresent(...)` hoặc API khác, kéo việc nạp/kiểm tra kiểu vào quá trình đánh giá.
- Một framework khác có thể dùng reflection ở giai đoạn sau để đọc generic signatures, annotation attributes hoặc type hierarchy.

ASM chỉ là công cụ phân tích bytecode; **toàn bộ thuật toán Spring** mới quyết định lúc nào phải đọc thêm tài nguyên hay nạp kiểu thực.

Nếu một thư viện cần hoạt động khi dependency tùy chọn thiếu, phải thiết kế cả **cấu trúc class và phạm vi xử lý annotation** một cách có chủ đích, không chỉ trông chờ ASM.

## 11. Đặc điểm của `@ConditionalOnClass` so với phép kiểm tra khác

Trong Spring Boot, điều kiện classpath có nhiều cách biểu đạt:

### `@ConditionalOnClass`

~~~java
@ConditionalOnClass(name = {
    "com.vendor.alpha.AlphaClient",
    "com.vendor.beta.BetaCodec"
})
~~~

Hai kiểu phải hiện diện theo semantics condition tương ứng để cấu hình khớp. Sự hiện diện không chứng minh kết nối mạng, license hoặc API runtime đã được cấu hình.

### `@ConditionalOnMissingClass`

~~~java
@ConditionalOnMissingClass("com.vendor.optional.FastClient")
~~~

Dùng cho trường hợp fallback cần kích hoạt khi một kiểu không có; ví dụ thay thế implementation khi thư viện nhanh không được đưa vào classpath. Không lạm dụng: thiếu class đôi khi là lỗi deployment chứ không phải feature hợp lệ.

### `ClassUtils.isPresent`

~~~java
boolean available =
    org.springframework.util.ClassUtils.isPresent(
        "com.vendor.optional.FastClient",
        getClass().getClassLoader()
    );
~~~

Đây là fragment cần đặt trong code có ngữ cảnh thích hợp. `ClassUtils.isPresent` là tiện ích của Spring để kiểm tra liệu class có thể hiện diện, nhưng nó đi qua cơ chế class loading và xử lý một số lỗi theo API — **khác về tầng hoạt động** với đơn thuần đọc file `.class` bằng ASM.

Nếu bạn chỉ cần điều khiển một auto-configuration, ưu tiên `@ConditionalOnClass`/`@ConditionalOnMissingClass`. Không tự viết custom condition gọi `Class.forName` nếu annotation dựng sẵn đã thể hiện đủ yêu cầu.

### `ClassLoader.getResource`

~~~java
boolean resourceFound = getClass().getClassLoader()
    .getResource("com/vendor/optional/FastClient.class") != null;
~~~

Có file tài nguyên không có nghĩa JVM nạp hoặc liên kết class thành công. Công cụ có thể dùng resource presence làm một tín hiệu, nhưng không nên xem nó là phép xác minh **đầy đủ** tình trạng classpath.

## 12. Tối ưu khám phá ứng viên: metadata và file auto-configuration

Spring Boot 3.x nhận ứng viên auto-configuration từ tài nguyên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Tài nguyên liệt kê các lớp ứng viên theo FQCN, không phải bean instance. Boot còn áp dụng exclusion/filter/condition để quyết định các cấu hình thật sự được xử lý.

Một thư viện có thể tạo metadata tối ưu bằng annotation processor:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

Metadata này hỗ trợ quá trình lọc/tối ưu các auto-configuration theo một số điều kiện, đặc biệt những phép kiểm tra có thể thực hiện sớm. Nó **không thay thế** file imports; và việc có metadata file cũng **không chứng minh bean đã được tạo**.

### Tại sao quan trọng với hiệu năng?

Nếu ứng dụng dùng hàng trăm starter/dependencies, việc tải mọi class candidate chỉ để hỏi classpath có phù hợp hay không sẽ tốn công và có nguy cơ nạp kiểu optional quá sớm. Đọc metadata bytecode và lọc ứng viên sớm giúp giảm công việc không cần thiết, đặc biệt với classpath rộng.

Tuy nhiên, không cam kết con số cụ thể về thời gian khởi động vì hiệu quả phụ thuộc version, classpath, số candidate, caching, điều kiện và cấu trúc dự án.

### ASM không thay thế điều kiện runtime

Một file imports được đọc thành công chỉ là bước khám phá. Một class `@AutoConfiguration` được báo là condition match vẫn có thể thất bại khi tạo bean vì thiếu property bắt buộc, binary incompatibility hoặc lỗi trong constructor. Cách chẩn đoán là kết hợp:

1. Tài nguyên imports/candidate có thực sự được đóng gói không?
2. `@ConditionalOnClass`/các conditions có khớp không?
3. Bean definition và bean instance có được tạo hợp lệ không?
4. Có lỗi linkage/initialization ở runtime không?

## 13. Đọc metadata từ JAR thường và JAR Boot executable

`MetadataReaderFactory` nhận tên class và dùng resource/class loader phù hợp để tìm bytecode. Trong dự án chạy từ Maven hoặc `target/classes`, tài nguyên thường là file class trên filesystem. Trong JAR thông thường, nó có thể được tìm thông qua URL classpath bên trong archive.

Spring Boot executable JAR có bố cục thường gặp:

~~~text
app.jar
├── BOOT-INF/classes/
│   └── demo/app/DemoApplication.class
├── BOOT-INF/lib/
│   └── dependency.jar
└── org/springframework/boot/loader/...
~~~

Khi chạy bằng loader của Spring Boot, classpath nhìn thấy `BOOT-INF/classes` và các dependency JAR lồng. Công cụ metadata đọc qua resource/class loader hoạt động theo classpath mà loader cung cấp; bạn không cần tự giải nén mọi JAR chỉ để dùng `MetadataReader` trong chương trình đang chạy.

Nếu bạn **đứng ngoài ứng dụng** dùng công cụ `jar tf app.jar`, nó chỉ liệt kê entry của JAR ngoài, không tự mở mọi JAR con. Muốn kiểm tra trực tiếp file `.class` hoặc imports của dependency lồng trong `BOOT-INF/lib`, cần mở JAR con riêng hoặc dùng công cụ hiểu nested JAR.

### Lưu ý tên class/resource

- FQCN trong annotation và metadata: `com.acme.Foo`.
- Resource classpath: `com/acme/Foo.class`.
- Entry trong JAR: `com/acme/Foo.class` nếu là JAR thường.
- Nested class theo tên nhị phân: `com.acme.Outer$Inner` và entry `com/acme/Outer$Inner.class`.

Nhầm dấu chấm/dấu gạch chéo là nguyên nhân đơn giản nhưng rất phổ biến khi tự viết công cụ khám phá.

## 14. Lỗi thường gặp khi né class loading

| Tình huống | Sai lầm | Cách làm đúng |
| --- | --- | --- |
| Chỉ cần đọc tên/annotation | Gọi `Class.forName(...)` rồi reflection | Dùng `MetadataReader`/`AnnotationMetadata` |
| Chỉ muốn tránh static initializer | Hiểu `Class.forName(name,false,loader)` là “không load” | Nó vẫn load; chỉ tránh initialize |
| Viết auto-configuration phụ thuộc optional | Điều kiện đặt trên method trả kiểu optional | Đưa điều kiện lên class cấu hình riêng |
| Viết meta-annotation `@ConditionalOnClass` | Dùng class literal và giả định ASM luôn che chắn | Dùng `name` theo hướng dẫn Boot |
| Thấy `.class` ở classpath | Kết luận cả API runtime hoạt động | Kiểm tra dependency graph, linkage và startup |
| Đọc được bytecode của class A | Nghĩ toàn bộ điều kiện Spring không nạp gì khác | Phân biệt các giai đoạn xử lý Spring |
| Có `AutoConfiguration.imports` | Kết luận bean chắc chắn tồn tại | Xem conditions và context sau khởi động |
| Không tìm được resource trong JAR ngoài | Kết luận nested dependency không tồn tại | Mở `BOOT-INF/lib` của executable JAR |
| Tạo custom condition đọc mạng | Coi presence check giống khả năng phục vụ | Dùng classpath condition cho presence, health/retry cho trạng thái ngoài |
| Phụ thuộc reflection của class optional | Nghĩ việc scan metadata đủ ngăn lỗi linkage | Cô lập class, tránh chữ ký tùy chọn ở nơi bị xử lý sớm |
| Caching metadata quá lâu | Giả định classpath/resources không bao giờ thay đổi trong mọi môi trường | Quản lý phạm vi cache theo vòng đời và môi trường class loader |
| Dùng class name không chính xác | Không thấy candidate/annotation | Đối chiếu FQCN, package, version và classpath thực tế |

## 15. Quy trình chẩn đoán khi gặp `NoClassDefFoundError`

Đừng mặc định “ASM không hoạt động”. Hãy đi theo các bước:

1. **Đọc stack trace gốc.** Xem exception xảy ra khi quét metadata, khi parse configuration, khi reflect method, khi tạo bean hay khi gọi nghiệp vụ.
2. **Xác minh phiên bản thư viện.** So dependency compile/runtime và các version xung đột.
3. **Kiểm tra vị trí condition.** `@ConditionalOnClass` đang nằm trực tiếp trên auto-configuration class, trên `@Bean` method hay trong meta-annotation?
4. **Kiểm tra chữ ký class/method.** Có return type/parameter/superclass/interface bắt buộc phải giải quyết kiểu optional trước khi condition đánh giá không?
5. **Kiểm tra imports.** Một class auto-configuration có trong `AutoConfiguration.imports` chưa? Nó có vô tình được quét như component không?
6. **Kiểm tra runtime classpath.** Class file mục tiêu có mặt đúng JAR/version không? Những dependency trực tiếp hoặc transitive được yêu cầu có mặt không?
7. **Phân biệt tải class và tạo bean.** Lỗi có xảy ra trước `BeanDefinition` hay trong factory method/constructor?
8. **Tách optional configuration.** Dùng nested static class hoặc class cấu hình độc lập với class-level `@ConditionalOnClass`.
9. **Bật `--debug` của Boot.** Condition Evaluation Report có thể cho thấy class-level condition không khớp; nhưng không kỳ vọng report thay thế stack trace của lỗi linkage.
10. **Tạo test thiếu dependency.** Kiểm thử một classpath thực sự thiếu thư viện optional, vì chạy với tất cả dependencies trong IDE chưa chứng minh cấu hình an toàn.

**Tín hiệu phân biệt quan trọng:** `ClassNotFoundException` khi bạn chủ động lookup tên class không giống `NoClassDefFoundError` khi JVM phải giải quyết một tham chiếu nhị phân từ class khác. Cùng có thể xuất phát từ thiếu dependency, nhưng đường điều tra và điểm code cần sửa khác nhau.

## 16. Thực hành kiểm thử classpath có/không có optional dependency

Để kiểm tra một thư viện auto-configuration thực tế, nên có ít nhất hai nhóm test:

### Nhóm A — classpath đủ

- Có dependency optional thật.
- Condition classpath khớp.
- Bean mặc định được đăng ký khi điều kiện bean/property khác phù hợp.
- Bean hoạt động, không có lỗi linkage hoặc initialization.

### Nhóm B — classpath thiếu

- Không đưa dependency optional vào runtime/test classpath.
- Auto-configuration bị bỏ qua **mà không gây lỗi loading/linking từ chữ ký class tùy chọn**.
- Những bean độc lập vẫn được khởi động bình thường.
- Report ghi điều kiện classpath không khớp (nếu cấu hình được Boot xem xét và report được ghi).
- Không có `NoClassDefFoundError` từ class cấu hình.

`ApplicationContextRunner` trong `spring-boot-test` giúp tạo context cho những tập user configuration/property khác nhau; `FilteredClassLoader` có thể được dùng để mô phỏng các lớp không hiện diện trong một test context. Đây là tiện ích test đặc thù của Spring Boot.

Ví dụ **fragment test** cần dependencies `spring-boot-test`, AssertJ và đúng class config:

~~~java
new ApplicationContextRunner()
    .withClassLoader(new FilteredClassLoader("com.vendor.optional"))
    .withConfiguration(
        AutoConfigurations.of(OptionalClientAutoConfiguration.class))
    .run(context -> {
        assertThat(context).doesNotHaveBean(OptionalClient.class);
    });
~~~

**Đây chỉ là mô tả test**, không phải chương trình hoàn chỉnh: kiểu `OptionalClient` trong assertion phải tồn tại tại compile time, và class auto-config/test helpers phải có trong project. Trong thử nghiệm thiếu dependency thật, nên assert bằng tên bean hoặc tên kiểu/string khi không muốn liên kết trực tiếp đến class optional. Ví dụ trên làm rõ ý tưởng dùng `FilteredClassLoader`, không phải minh chứng một JAR thiếu API đã an toàn mọi đường.

### Kiểm tra đúng phạm vi

Chỉ che lớp bằng test class loader không nhất thiết tái hiện mọi tình huống module path, class loader của app server hoặc executable nested JAR. Với starter quan trọng, kết hợp test thiếu class bằng `FilteredClassLoader` và chạy một ứng dụng tối thiểu có dependency runtime thực sự bị loại bỏ.

## 17. Lưu ý nâng cao: annotation metadata không miễn trừ việc nạp lớp ở mọi API

Một số API metadata có thể trả về tên class ở dạng `String` hoặc cấu trúc metadata; một số API reflection hoặc tổng hợp annotation có thể giải quyết giá trị `Class<?>`. Không được mặc định mọi phương thức có chữ “metadata” đều không bao giờ nạp thêm lớp.

Ví dụ:

- Đọc `ClassMetadata.getClassName()` chỉ yêu cầu tên từ bytecode.
- Đọc tên annotation từ `AnnotationMetadata` thường không cần tạo instance của class mục tiêu.
- Truy cập attribute annotation mà biểu diễn giá trị class được chuyển thành `Class<?>` có thể cần resolution class tùy API/đường xử lý; Spring có các tùy chọn xử lý giá trị class ở dạng string khi phù hợp.
- Reflection như `getDeclaredMethods()` có thể cần giải quyết kiểu của parameter/return type và gây lỗi nếu thiếu dependency.
- Những type descriptors hay generic signatures có thể chứa tên kiểu vắng mặt; việc nhìn thấy tên từ bytecode không kiểm tra tính tương thích runtime.

**Chọn API theo câu hỏi cần trả lời.** Nếu bạn chỉ cần biết annotation X có mặt, không nên đổi sang reflection chỉ để lấy một kết quả boolean. Nếu bạn cần gọi phương thức thật, bạn không thể tránh mãi những bước loading/linking/initialization của JVM.

## 18. Câu hỏi luyện tập và thí nghiệm mở rộng

1. **Khái niệm:** ASM đọc file `.class` như dữ liệu nghĩa là gì? Nó khác `Class.forName(name,false,loader)` ở bước nào?
2. **Ba giai đoạn:** mô tả loading, linking và initialization. Vì sao đọc metadata không in dòng của static initializer?
3. **Chạy ví dụ:** sau `MetadataReader`, `Boolean.getBoolean("demo.target.initialized")` là gì? Vì sao?
4. **Đổi thứ tự:** chuyển `Class.forName(className)` lên trước bước ASM. Các dòng output đo initialization sẽ thay đổi ra sao?
5. **Tạo dependency thiếu:** đặt `@ConditionalOnClass(name="demo.missing.OptionalClient")` trên cấu hình. Vì sao Boot bỏ qua bean mà không cần định nghĩa class optional trong project?
6. **Method nguy hiểm:** vì sao `@ConditionalOnClass` ở riêng một `@Bean` method có return type optional chưa đủ an toàn?
7. **Cách ly cấu hình:** tách optional code sang static nested `@Configuration` có condition cấp class. Điều đó thay đổi thứ tự xử lý như thế nào?
8. **Meta-annotation:** tại sao khi compose `@ConditionalOnClass`, tài liệu Boot yêu cầu dùng `name` thay vì class literal?
9. **Truyền qua JAR:** nếu ứng dụng là executable Boot JAR, muốn tự xem file class của dependency thì tìm ở đâu?
10. **Transitive dependency:** nếu `FancyClient.class` có mặt nhưng một interface mà nó implements bị thiếu, metadata vẫn có thể đọc được không? Thao tác JVM nào có thể phát hiện thiếu?
11. **Lỗi triển khai:** khác nhau giữa `ClassNotFoundException`, `NoClassDefFoundError` và `ExceptionInInitializerError`?
12. **Bằng chứng:** tệp `AutoConfiguration.imports` tồn tại có chứng minh bean đã được tạo không? Cần thêm những dữ liệu gì?
13. **Kỹ thuật kiểm thử:** `FilteredClassLoader` phù hợp kiểm tra điều gì, và vì sao vẫn cần kiểm thử trên runtime classpath thật?
14. **Tối ưu:** khi scan hàng nghìn class, caching metadata có thể giúp gì? Trường hợp nào cache có thể trở thành gánh nặng?
15. **Giới hạn:** hãy nêu ít nhất năm tình huống ASM không tự bảo vệ khỏi lỗi class loading hoặc runtime dependency.

**Hoàn thành bài** khi bạn có thể đọc class metadata bằng Spring API, giải thích đúng kết quả không khởi tạo static initializer, dùng `@ConditionalOnClass` để bảo vệ các cấu hình tùy chọn, tách cấu hình ở cấp class khi method signature có optional type và phân biệt lỗi metadata, classpath, linkage và tạo bean.

## 19. Tài liệu chính thức

- [Spring Framework — `MetadataReader` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/classreading/MetadataReader.html)
- [Spring Framework — `MetadataReaderFactory` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/classreading/MetadataReaderFactory.html)
- [Spring Framework — `SimpleMetadataReaderFactory` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/classreading/SimpleMetadataReaderFactory.html)
- [Spring Framework — `ClassMetadata` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/ClassMetadata.html)
- [Spring Framework — `AnnotationMetadata` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotationMetadata.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Condition annotations](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.condition-annotations)
- [Spring Boot 3.3 — `@ConditionalOnClass` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Java SE 17 — JVM specification, Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
