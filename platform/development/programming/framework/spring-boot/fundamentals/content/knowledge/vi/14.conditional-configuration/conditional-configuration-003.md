# @ConditionalOnClass, @ConditionalOnMissingClass và classpath

Spring Boot có thể tự động cấu hình một tính năng khi thư viện cần thiết xuất hiện trong ứng dụng, hoặc bỏ qua tính năng đó khi thư viện không có mặt. Cơ chế này đặc biệt hữu ích cho các starter và thư viện tích hợp: ứng dụng chỉ cần thêm dependency phù hợp, còn Spring Boot quyết định cấu hình nào có thể tham gia dựa trên môi trường thực tế.

Hai annotation thường dùng để diễn đạt điều kiện về sự hiện diện của class là:

- **@ConditionalOnClass**: điều kiện thỏa khi các class được chỉ định có mặt trên classpath có thể được Spring sử dụng.
- **@ConditionalOnMissingClass**: điều kiện thỏa khi các class được chỉ định không có mặt trên classpath đó.

Để hiểu đúng hai annotation này, cần nắm rõ **classpath**, **class loader**, khác biệt giữa compile-time và runtime, và cách Spring đánh giá điều kiện trong lúc xây dựng ApplicationContext. Chỉ nhìn thấy một import trong source hoặc một dependency trong file build chưa đủ để kết luận điều kiện sẽ thỏa khi ứng dụng chạy.

## 1. Classpath là gì?

Trong Java, **classpath** là tập vị trí mà trình biên dịch hoặc runtime sử dụng để tìm class và resource. Các vị trí thường gặp gồm:

- Thư mục chứa file .class.
- Tệp thư viện .jar.
- Các thư mục resource được đưa vào classpath.
- Những artifact mà công cụ build và môi trường chạy cung cấp cho ứng dụng.

Ví dụ một ứng dụng có cấu trúc dependency:

~~~text
Ứng dụng Spring Boot
├── application classes
├── spring-context.jar
├── spring-boot-autoconfigure.jar
├── vendor-client.jar
└── vendor-common.jar
~~~

Nếu vendor-client.jar chứa class com.vendor.client.VendorClient, runtime class loader có thể tìm thấy class đó khi ứng dụng chạy, miễn là JAR nằm trong classpath hoặc module path phù hợp và không có vấn đề về khả năng nạp class.

Classpath là một phần của **môi trường chạy Java**. Spring Boot dùng nó để quyết định các cấu hình tự động có phù hợp với ứng dụng hiện tại hay không.

### 1.1. Import trong source không đồng nghĩa class có trên runtime classpath

Một file Java có thể viết:

~~~java
import com.vendor.client.VendorClient;
~~~

Import chỉ giúp source code tham chiếu tên kiểu. Để biên dịch được, compiler cần tìm thấy kiểu đó trên compile classpath. Để ứng dụng sử dụng kiểu đó khi chạy, class tương ứng và các dependency cần thiết phải có mặt trên runtime classpath.

Một thư viện có thể được khai báo chỉ cho compile, nhưng không được đóng gói vào runtime. Khi đó:

- Code có thể biên dịch thành công.
- Ứng dụng có thể thất bại khi nạp class ở runtime.
- Điều kiện classpath trong Spring Boot có thể không thỏa khi context được tạo.

Vì vậy, khi một auto-configuration không hoạt động như mong đợi, hãy kiểm tra **runtime classpath thực tế**, không chỉ dòng khai báo dependency.

### 1.2. Classpath có thể khác giữa compile, test và runtime

Trong Gradle, một số configuration thường gặp:

| Configuration | Vai trò điển hình |
|---|---|
| **implementation** | Dependency của mã chính, tham gia compile và runtime theo mô hình Java plugin. |
| **compileOnly** | Có ở compile classpath nhưng không tự được đưa vào runtime classpath chính. |
| **runtimeOnly** | Cần khi chạy nhưng không cần để biên dịch source chính. |
| **testImplementation** | Dependency dùng cho source test và test classpath. |
| **testRuntimeOnly** | Dependency chỉ cần khi chạy test. |

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    compileOnly 'com.vendor:vendor-client:2.1.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Nếu VendorClient chỉ có trong compileOnly, code tham chiếu trực tiếp có thể biên dịch nhưng runtime của ứng dụng chính không nhất thiết có JAR đó. Khi Spring đánh giá điều kiện trong ứng dụng đã chạy, class có thể bị xem là không có.

Với Maven, các scope như compile, runtime, test và provided cũng ảnh hưởng artifact nào được đưa vào từng classpath. Không nên ánh xạ máy móc tên scope Maven sang tên configuration Gradle; hãy xem đúng mô hình build của dự án.

### 1.3. Classpath của test có thể làm điều kiện cho kết quả khác production

Giả sử một test khai báo dependency client trong testImplementation, trong khi ứng dụng production không có dependency tương ứng ở runtime. Test context có thể thấy class và kích hoạt auto-configuration; khi chạy executable JAR production, class đó không còn trên runtime classpath nên cấu hình bị bỏ qua hoặc code tham chiếu trực tiếp thất bại.

Đây là lý do cần phân biệt:

- Test có classpath riêng.
- IDE có thể tạo runtime classpath riêng cho cấu hình chạy.
- bootRun dùng runtime classpath của Gradle.
- Executable JAR chứa các dependency runtime mà plugin đóng gói.
- Môi trường production có thể bổ sung hoặc thay đổi cách nạp class theo cấu hình triển khai.

Điều kiện classpath được đánh giá trong **class loader mà Spring sử dụng tại runtime của context**, chứ không dựa vào danh sách dependency mà bạn nhớ đã khai báo.

## 2. Class loader và khả năng tìm class

JVM sử dụng **ClassLoader** để tìm và nạp định nghĩa class khi cần. Một ứng dụng có thể có nhiều class loader, chẳng hạn class loader của ứng dụng, class loader của container hoặc các loader riêng cho plugin.

Một cách hình dung:

~~~text
Spring ApplicationContext
        │
        ▼
ClassLoader được dùng để kiểm tra class
        │
        ├── tìm thấy com.vendor.client.VendorClient
        │       └── điều kiện OnClass có thể thỏa
        │
        └── không tìm thấy class
                └── điều kiện OnClass không thỏa
~~~

Vì vậy, câu “JAR có trong máy” chưa đủ. JAR cần nằm trong classpath/module path phù hợp với process và class loader cần dùng nó. Một JAR nằm trong thư mục tải về, cache Gradle hoặc một thư mục không được cấu hình không tự động trở thành dependency của ứng dụng.

### 2.1. Class có mặt không đồng nghĩa class sử dụng được trong mọi trường hợp

Một class file có thể được tìm thấy, nhưng khi JVM thực sự liên kết hoặc khởi tạo class, nó có thể cần một class khác không tồn tại. Ví dụ:

~~~text
vendor-client.jar
└── VendorClient.class
      └── tham chiếu VendorTransport.class

runtime classpath:
└── vendor-client.jar
    (thiếu vendor-transport.jar)
~~~

Điều kiện kiểm tra sự hiện diện của VendorClient không thay thế việc xác nhận toàn bộ dependency graph tương thích và đầy đủ. Khi class được sử dụng, ứng dụng vẫn có thể gặp NoClassDefFoundError, ClassNotFoundException, lỗi linkage hoặc lỗi tương thích binary.

### 2.2. Classpath condition không kiểm tra tính đúng đắn của thư viện

@ConditionalOnClass kiểm tra class được chỉ định có thể được tìm thấy hay không. Nó không tự xác nhận:

- Version thư viện có đúng với version Spring Boot hỗ trợ không.
- Các method mà ứng dụng gọi có tồn tại không.
- API và implementation có tương thích binary không.
- Các dependency bắc cầu đã đầy đủ chưa.
- Dịch vụ bên ngoài đã cấu hình và hoạt động chưa.

Điều kiện thỏa chỉ cho biết **một tín hiệu về classpath**. Các bước khởi tạo bean và sử dụng thư viện vẫn có thể thất bại vì nguyên nhân khác.

## 3. @ConditionalOnClass là gì?

@ConditionalOnClass là annotation của Spring Boot trong package:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionalOnClass
~~~

Nó đánh dấu một configuration class hoặc một phương thức @Bean chỉ được xem xét khi class được yêu cầu có mặt.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(VendorClient.class)
public class VendorClientConfiguration {

    @Bean
    VendorService vendorService(VendorClient client) {
        return new VendorService(client);
    }
}
~~~

Nếu VendorClient.class có thể được tìm thấy theo cơ chế kiểm tra classpath, condition có thể match và cấu hình được xem xét. Nếu class không có, cấu hình bị bỏ qua.

Trong một thư viện auto-configuration, mục tiêu thường là:

~~~text
Có vendor-client trên classpath?
          │
     ┌────┴────┐
     │         │
    Có       Không
     │         │
     ▼         ▼
Xem xét cấu  Bỏ qua cấu hình
 hình client  tích hợp client
~~~

Điều này giúp ứng dụng không sử dụng vendor client vẫn có thể chạy mà không cần kéo thư viện đó vào.

### 3.1. Dùng class literal trong thuộc tính value

Annotation hỗ trợ khai báo class trực tiếp:

~~~java
@ConditionalOnClass(VendorClient.class)
~~~

Hoặc nhiều class:

~~~java
@ConditionalOnClass({
    VendorClient.class,
    VendorTransport.class
})
~~~

Khi chỉ định nhiều class trong một @ConditionalOnClass, điều kiện yêu cầu **tất cả class được liệt kê đều hiện diện**. Đây là quan hệ AND, không phải OR.

### 3.2. Dùng thuộc tính name

Annotation cũng hỗ trợ tên class dưới dạng String:

~~~java
@ConditionalOnClass(
    name = "com.vendor.client.VendorClient"
)
~~~

Thuộc tính name hữu ích khi:

- Muốn tránh import kiểu tùy chọn vào source của auto-configuration.
- Viết điều kiện trong một module không muốn có compile dependency trực tiếp tới thư viện được kiểm tra.
- Muốn biểu diễn tên đầy đủ của class bằng chuỗi.

Tên phải là **fully qualified class name**, bao gồm package.

Nhiều class có thể được liệt kê:

~~~java
@ConditionalOnClass(name = {
    "com.vendor.client.VendorClient",
    "com.vendor.transport.VendorTransport"
})
~~~

Ở đây cũng cần tất cả class được yêu cầu có mặt thì điều kiện mới thỏa.

### 3.3. Class literal có an toàn khi thư viện tùy chọn vắng mặt không?

Spring Boot có cơ chế đọc metadata annotation bằng ASM để đánh giá điều kiện trên configuration class. Nhờ vậy, **class literal trong annotation cấp class** có thể được xử lý mà không cần JVM nạp kiểu tùy chọn theo cách thông thường trước khi condition được xét.

Ví dụ sau là cách dùng phổ biến trong auto-configuration:

~~~java
@AutoConfiguration
@ConditionalOnClass(VendorClient.class)
public class VendorAutoConfiguration {
    // ...
}
~~~

Điều kiện ở cấp configuration class được xử lý từ metadata, nên Spring Boot có thể bỏ qua class cấu hình khi VendorClient không có mặt.

Tuy nhiên, không nên suy rộng điều này thành “cứ viết class tùy chọn ở bất kỳ vị trí nào cũng an toàn”. **Chữ ký method, superclass, interface, field hoặc code khởi tạo của một class vẫn có thể khiến JVM cần resolve kiểu tùy chọn quá sớm.** Phần sau giải thích cách cô lập cấu hình để tránh lỗi đó.

## 4. @ConditionalOnMissingClass là gì?

@ConditionalOnMissingClass là điều kiện ngược lại: cấu hình được xem xét khi các class được chỉ định **không có mặt**.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingClass("com.vendor.client.VendorClient")
public class FallbackClientConfiguration {

    @Bean
    LocalVendorService localVendorService() {
        return new LocalVendorService();
    }
}
~~~

Nếu VendorClient không xuất hiện trên classpath, cấu hình fallback có thể được áp dụng. Nếu VendorClient có mặt, cấu hình này bị bỏ qua.

### 4.1. Khai báo một hoặc nhiều tên class

~~~java
@ConditionalOnMissingClass({
    "com.vendor.client.VendorClient",
    "com.vendor.transport.VendorTransport"
})
~~~

Với nhiều tên class, điều kiện chỉ match khi **tất cả class được liệt kê đều vắng mặt**. Nếu chỉ một class xuất hiện, điều kiện không còn thỏa.

Đây cũng là logic AND trên tập yêu cầu “phải vắng mặt”. Nó không có nghĩa “chỉ cần một class trong danh sách vắng mặt”.

Nếu cần biểu diễn logic OR phức tạp, có thể dùng nhiều configuration class với các condition riêng, một custom Condition, hoặc thiết kế cấu trúc cấu hình phù hợp. Không nên cố diễn giải sai ý nghĩa của danh sách class trong annotation.

### 4.2. Dùng fallback khi thư viện chính không có

Một thư viện tích hợp có thể có hai cách hoạt động:

- Dùng implementation của vendor khi SDK có mặt.
- Dùng implementation dự phòng khi SDK không có mặt.

Ví dụ khái niệm:

~~~java
@AutoConfiguration
public class SearchIntegrationAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.search.SearchClient")
    static class VendorSearchConfiguration {
        @Bean
        SearchService vendorSearchService(SearchClient client) {
            return new VendorSearchService(client);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnMissingClass("com.vendor.search.SearchClient")
    static class LocalSearchConfiguration {
        @Bean
        SearchService localSearchService() {
            return new LocalSearchService();
        }
    }
}
~~~

SearchClient, SearchService, VendorSearchService và LocalSearchService là các kiểu minh họa. Trong code thật, cần bảo đảm các kiểu tùy chọn chỉ được tham chiếu bên trong cấu hình được bảo vệ bởi điều kiện phù hợp.

Hai nhánh trên thể hiện cách suy nghĩ:

~~~text
SearchClient có trên classpath?
            │
       ┌────┴────┐
       │         │
      Có       Không
       │         │
       ▼         ▼
Vendor search  Local fallback
configuration  configuration
~~~

Không nên để hai nhánh cùng tạo một bean không có quy tắc lựa chọn rõ ràng. Khi cần cùng một bean name hoặc cùng một kiểu, hãy thiết kế điều kiện loại trừ lẫn nhau và có kiểm thử cho cả hai nhánh.

## 5. Phân biệt @ConditionalOnClass với @ConditionalOnBean

Hai annotation có tên gần nhau nhưng kiểm tra hai lớp thông tin khác nhau:

| Annotation | Kiểm tra điều gì? |
|---|---|
| **@ConditionalOnClass** | Class có mặt trên classpath/class loader không? |
| **@ConditionalOnMissingClass** | Class có vắng mặt trên classpath/class loader không? |
| **@ConditionalOnBean** | Spring context đã có bean phù hợp không? |
| **@ConditionalOnMissingBean** | Spring context chưa có bean phù hợp hay không? |

Ví dụ, dependency vendor-client.jar có thể nằm trên runtime classpath nhưng chưa có bean VendorClient:

~~~text
vendor-client.jar có mặt
        │
        ▼
VendorClient.class có thể tìm thấy
        │
        ├── @ConditionalOnClass có thể match
        │
        └── Nhưng chưa chắc có VendorClient bean
~~~

Class hiện diện không tự tạo bean. Một bean cần được đăng ký bằng component scan, @Bean, auto-configuration hoặc cơ chế đăng ký khác.

Ngược lại, một bean có thể được tạo bởi factory hoặc implementation khác mà không có class cụ thể mà bạn định kiểm tra. Vì vậy, điều kiện classpath và điều kiện bean giải quyết hai câu hỏi khác nhau.

### 5.1. Kết hợp điều kiện classpath và điều kiện bean

Một auto-configuration có thể dùng cả hai:

~~~java
@AutoConfiguration
@ConditionalOnClass(VendorClient.class)
public class VendorAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(VendorService.class)
    VendorService vendorService(VendorClient client) {
        return new VendorService(client);
    }
}
~~~

Ý nghĩa:

1. SDK class cần thiết có trên classpath thì cấu hình mới được xem xét.
2. Nếu ứng dụng chưa cung cấp VendorService phù hợp, Boot mới tạo bean mặc định.
3. Nếu ứng dụng đã có VendorService riêng, cấu hình mặc định nhường chỗ.

Ở đây **@ConditionalOnClass** bảo vệ tích hợp optional, còn **@ConditionalOnMissingBean** cho phép người dùng thay thế bean mặc định.

## 6. Classpath condition được đánh giá khi nào?

Các điều kiện Spring Boot thường được đánh giá trong quá trình xử lý cấu hình và xây dựng ApplicationContext. Chúng không phải một công tắc được kiểm tra lại liên tục ở mỗi HTTP request.

Một trình tự khái niệm:

~~~text
SpringApplication khởi động
          │
          ▼
Environment và ApplicationContext được chuẩn bị
          │
          ▼
Spring đọc cấu hình và auto-configuration metadata
          │
          ▼
Đánh giá điều kiện classpath
          │
          ├── Class có mặt
          │       └── Có thể tiếp tục xử lý cấu hình
          │
          └── Class vắng mặt
                  └── Bỏ qua cấu hình tương ứng
          │
          ▼
Đăng ký bean definitions phù hợp
          │
          ▼
Khởi tạo bean và hoàn tất context
~~~

Classpath của một process Java về cơ bản được thiết lập khi process được khởi động. Nếu bạn thay đổi file JAR trên đĩa sau khi ứng dụng đã chạy, class loader hiện tại không tự động cập nhật toàn bộ classpath và Spring cũng không tự đánh giá lại mọi condition.

Muốn thay đổi tập thư viện đang được dùng, thông thường cần khởi động lại process hoặc dùng một kiến trúc class loading/plugin riêng có quản lý vòng đời rõ ràng.

## 7. Dùng @ConditionalOnClass trong auto-configuration

Một mục tiêu quan trọng của Spring Boot là cho phép thư viện cung cấp cấu hình tự động nhưng không bắt mọi ứng dụng phải có mọi thư viện tích hợp.

Giả sử thư viện acme-spring-boot-autoconfigure cung cấp tích hợp cho SDK acme-client. Nếu consumer không dùng SDK, họ vẫn có thể sử dụng các phần khác của ứng dụng mà không cần class AcmeClient.

Ví dụ đơn giản:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.client.AcmeClient")
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeService acmeService(AcmeClient client) {
        return new AcmeService(client);
    }
}
~~~

Đoạn code trên minh họa ý tưởng nhưng có một lưu ý quan trọng: **nếu kiểu tùy chọn xuất hiện trong chữ ký phương thức của configuration class bên ngoài, JVM có thể cần resolve kiểu đó khi xử lý class/method metadata**. Cách an toàn hơn là cô lập các method tham chiếu optional type vào một nested configuration có điều kiện.

### 7.1. Cô lập kiểu tùy chọn trong nested configuration

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.client.AcmeClient")
    static class AcmeClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        AcmeService acmeService(AcmeClient client) {
            return new AcmeService(client);
        }
    }
}
~~~

Ở đây, kiểu AcmeClient chỉ xuất hiện trong nested configuration được bảo vệ bởi class condition. Khi class không có mặt, Spring có thể bỏ qua nhánh cấu hình đó trước khi xử lý các method cần kiểu optional.

Mẫu này đặc biệt quan trọng khi viết thư viện auto-configuration được sử dụng trong nhiều ứng dụng có dependency graph khác nhau.

### 7.2. Vì sao không đặt kiểu optional trong outer configuration?

Giả sử outer class có:

~~~java
@AutoConfiguration
public class AcmeAutoConfiguration {
    @Bean
    @ConditionalOnClass(name = "com.acme.client.AcmeClient")
    AcmeService acmeService(AcmeClient client) {
        return new AcmeService(client);
    }
}
~~~

Mặc dù method có condition, kiểu AcmeClient vẫn nằm trong chữ ký method của outer class. JVM hoặc framework có thể cần xử lý metadata của method trước khi điều kiện ở method được áp dụng theo cách bạn kỳ vọng. Nếu optional class vắng mặt, nguy cơ là lỗi liên kết class xảy ra quá sớm.

Đặt method vào một nested configuration có điều kiện giúp Spring tách riêng phần metadata chứa optional type khỏi cấu hình luôn được nạp.

### 7.3. Khi nào dùng class literal, khi nào dùng name?

Ở cấp class của auto-configuration, class literal thường là cách viết rõ ràng:

~~~java
@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
public class AcmeAutoConfiguration {
}
~~~

Khi muốn tránh tham chiếu compile-time trực tiếp tới class optional, dùng tên:

~~~java
@ConditionalOnClass(name = "com.acme.client.AcmeClient")
~~~

Dù dùng class literal hay name, nguyên tắc quan trọng vẫn là **cô lập những chữ ký và code thực sự phụ thuộc optional type**. Thuộc tính name không tự sửa được một method signature đã tham chiếu tới class vắng mặt.

## 8. @ConditionalOnMissingClass và fallback configuration

Một số thư viện cung cấp implementation thay thế khi thư viện chính không có mặt. Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingClass("com.acme.search.ElasticClient")
public class LocalSearchConfiguration {

    @Bean
    SearchService localSearchService() {
        return new LocalSearchService();
    }
}
~~~

Khi ElasticClient không có mặt, cấu hình local có thể được xem xét. Khi class đó xuất hiện, cấu hình local bị bỏ qua.

### 8.1. Đảm bảo hai nhánh không cùng đăng ký bean cạnh tranh

Nếu có một nhánh vendor và một nhánh fallback, nên thiết kế điều kiện sao cho chúng không cùng đăng ký một bean không thể phân biệt.

Ví dụ khái niệm:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.acme.search.ElasticClient")
class ElasticSearchConfiguration {
    @Bean
    SearchService searchService(ElasticClient client) {
        return new ElasticSearchService(client);
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingClass("com.acme.search.ElasticClient")
class LocalSearchConfiguration {
    @Bean
    SearchService searchService() {
        return new LocalSearchService();
    }
}
~~~

Hai điều kiện về cùng một class có tính đối nghịch, vì vậy về mặt logic một trong hai nhánh được chọn. Trong code thật, vẫn cần bảo đảm cả hai configuration được đăng ký đúng cách và optional type không bị tham chiếu sớm ở lớp ngoài.

### 8.2. Fallback có phải luôn là lựa chọn tốt?

Không. Nếu SDK chính là bắt buộc cho một chức năng, việc âm thầm chuyển sang implementation khác có thể làm thay đổi semantics hoặc mức độ bảo đảm dữ liệu.

Chỉ nên dùng fallback khi implementation thay thế thực sự đáp ứng hợp đồng mà consumer mong đợi. Nếu không có thư viện chính thì tính năng phải bị vô hiệu hóa hoặc startup phải báo lỗi rõ ràng, hãy thiết kế condition và thông báo theo đúng hợp đồng đó.

## 9. Optional dependency và thiết kế thư viện

Một thư viện Spring Boot có thể chia thành các module:

~~~text
acme-spring-boot-starter
├── acme-spring-boot
│   └── dependency metadata / starter
└── acme-spring-boot-autoconfigure
    ├── core integration
    └── optional integration
         └── acme-client (optional)
~~~

Tùy cách tổ chức artifact, module auto-configuration có thể khai báo dependency tùy chọn để consumer không bị buộc kéo SDK vào nếu không sử dụng tích hợp đó.

Khi thiết kế:

1. Tách phần API/core không phụ thuộc SDK tùy chọn.
2. Đặt code tham chiếu SDK trong module hoặc nested configuration phù hợp.
3. Bảo vệ auto-configuration bằng @ConditionalOnClass.
4. Chỉ đăng ký bean khi classpath có đủ thành phần cần thiết.
5. Cho phép consumer cung cấp bean riêng nếu thư viện hỗ trợ customization.
6. Kiểm thử cả trường hợp SDK có mặt và vắng mặt.

Điều kiện classpath là một phần của hợp đồng optional dependency. Nó giúp một starter có thể hoạt động trong nhiều ứng dụng với các dependency graph khác nhau.

### 9.1. Không để API public bắt buộc lộ kiểu optional

Nếu module core công bố một API mà chữ ký public trực tiếp yêu cầu class từ SDK optional, consumer có thể bị buộc phải có SDK ngay cả khi không sử dụng tính năng đó.

Hãy cân nhắc:

- Đặt adapter tích hợp trong module riêng.
- Dùng interface nội bộ của thư viện core.
- Chỉ tham chiếu vendor type trong nhánh cấu hình được bảo vệ.
- Tránh để class core kế thừa hoặc implement một kiểu optional không phải lúc nào cũng có.

@ConditionalOnClass giúp điều kiện hóa cấu hình, nhưng không thể sửa một thiết kế API đã bắt buộc mọi consumer nạp class tùy chọn.

## 10. Những giới hạn quan trọng của class condition

### 10.1. Không xác nhận bean đã được đăng ký

VendorClient.class có mặt không có nghĩa Spring đã tạo VendorClient bean. Cần một cơ chế đăng ký bean riêng, ví dụ component scan hoặc @Bean.

### 10.2. Không xác nhận cấu hình bên ngoài hợp lệ

Class client có thể tồn tại nhưng base URL, credentials, timeout hoặc endpoint chưa được cấu hình. Condition vẫn có thể match; lỗi chỉ xuất hiện khi tạo bean hoặc sử dụng client.

### 10.3. Không kiểm tra version compatibility

Condition có thể match với một version SDK cũ hoặc mới. Nếu code được biên dịch theo API khác version đang chạy, có thể gặp NoSuchMethodError, NoSuchFieldError hoặc lỗi linkage khác.

### 10.4. Không bảo đảm dependency bắc cầu đầy đủ

Class mục tiêu có thể tìm thấy nhưng một class khác mà nó cần lại thiếu. Khi JVM liên kết hoặc chạy code, lỗi có thể xuất hiện.

### 10.5. Không được đánh giá lại liên tục

Condition được đánh giá trong quá trình tạo context. Thêm JAR hoặc thay class loader theo cách thủ công sau đó không tự động làm Spring đăng ký lại bean.

### 10.6. Không thay thế @ConditionalOnBean

Classpath là một tín hiệu về khả năng dùng thư viện. Nếu cần biết Spring context đã có một bean cụ thể chưa, dùng condition về bean.

## 11. Kết hợp class condition với các điều kiện khác

Một auto-configuration thực tế thường kết hợp nhiều condition:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.client.AcmeClient")
@ConditionalOnProperty(
    prefix = "acme.client",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AcmeService.class)
    AcmeService acmeService(AcmeClient client) {
        return new AcmeService(client);
    }
}
~~~

Ví dụ này biểu diễn ba lớp quyết định:

1. SDK class phải có mặt.
2. Property cho phép bật tính năng.
3. Ứng dụng chưa cung cấp AcmeService thay thế.

Các điều kiện được kết hợp theo logic yêu cầu của từng cấp cấu hình/method. Nếu một điều kiện bắt buộc không thỏa, phần tương ứng không được áp dụng.

~~~text
AcmeClient có trên classpath?
          │
          ├── Không → Bỏ qua cấu hình
          │
          ▼ Có
acme.client.enabled = true?
          │
          ├── Không → Bỏ qua cấu hình
          │
          ▼ Có
Ứng dụng đã có AcmeService?
          │
          ├── Có → Bean mặc định nhường chỗ
          │
          ▼ Không
Tạo AcmeService mặc định
~~~

Nếu AcmeClient là optional type, cần áp dụng nguyên tắc nested configuration đã nêu để không vô tình buộc JVM resolve class trước khi class condition được kiểm tra.

## 12. Chẩn đoán khi @ConditionalOnClass không match

Giả sử bạn mong đợi AcmeAutoConfiguration được áp dụng nhưng bean không xuất hiện. Hãy kiểm tra theo trình tự:

### Bước 1: Xác nhận dependency có trong runtime classpath

Kiểm tra file build và dependency resolution của đúng configuration:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Trên Windows:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree
~~~

Đây là những lệnh minh họa để quan sát dependency graph. Cần chọn đúng module và configuration của ứng dụng. Không suy luận runtime classpath từ danh sách dependency test.

### Bước 2: Kiểm tra class thực tế nằm trong JAR nào

Một dependency có thể được resolve nhưng artifact không chứa class name mà annotation đang kiểm tra, do:

- Khác artifact hoặc module.
- Khác version.
- Package/class đã thay đổi giữa các version.
- Dependency bị exclude hoặc thay thế.
- Class chỉ nằm trong một artifact optional khác.

Hãy xác nhận fully qualified class name và nội dung artifact.

### Bước 3: Kiểm tra class loader và môi trường chạy

Nếu chạy trong IDE, test, bootRun và executable JAR cho kết quả khác nhau, so sánh runtime classpath tương ứng. Cũng cần lưu ý ứng dụng chạy trong servlet container hoặc môi trường có class loader riêng.

### Bước 4: Xem Condition Evaluation Report

Khởi chạy với --debug:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot có thể in **Condition Evaluation Report** trong log startup. Tìm auto-configuration liên quan và lý do condition không match.

Một đoạn minh họa:

~~~text
Negative matches:
-----------------
AcmeClientAutoConfiguration:
   Did not match:
      - @ConditionalOnClass did not find required class
        'com.acme.client.AcmeClient'
~~~

Tên cấu hình và câu chữ chỉ minh họa; output thực tế phụ thuộc phiên bản Boot và cách condition được khai báo.

### Bước 5: Xem có bị loại trừ hoặc bị điều kiện khác chặn không

Ngay cả khi class condition match, cấu hình có thể:

- Bị exclude qua exclude, excludeName hoặc spring.autoconfigure.exclude.
- Không thỏa @ConditionalOnProperty.
- Không thỏa @ConditionalOnBean hoặc @ConditionalOnMissingBean ở cấp method.
- Bị một điều kiện về web application hoặc resource loại bỏ.

Condition report giúp phân biệt các nguyên nhân này.

## 13. Chẩn đoán khi condition match nhưng ứng dụng vẫn lỗi

Nếu class condition đã match nhưng ứng dụng không tạo bean hoặc startup thất bại, hãy chuyển sang kiểm tra giai đoạn sau:

### 13.1. Thiếu dependency liên kết

Class mục tiêu tồn tại nhưng khi khởi tạo cần một class khác không có. Có thể gặp NoClassDefFoundError hoặc lỗi linkage.

### 13.2. Version không tương thích

Code được compile theo một API nhưng runtime nạp version khác. Có thể gặp NoSuchMethodError, AbstractMethodError hoặc lỗi tương thích khác.

### 13.3. Bean dependency không có

SDK class có mặt nhưng auto-configuration cần một bean do người dùng cung cấp, hoặc một bean khác chưa được đăng ký. Khi đó lỗi là vấn đề dependency injection, không còn là classpath condition đơn thuần.

### 13.4. Cấu hình client không hợp lệ

Base URL, token hoặc property không hợp lệ có thể làm factory method hoặc constructor thất bại.

### 13.5. Factory method ném exception

Bean definition được chọn nhưng quá trình tạo instance lỗi. Đọc BeanCreationException và toàn bộ Caused by để tìm lỗi gốc.

Điểm quan trọng: **condition match chỉ cho phép cấu hình được xem xét; nó không bảo đảm bean khởi tạo thành công hoặc tính năng hoạt động đúng**.

## 14. Kiểm thử cả hai trường hợp class có mặt và vắng mặt

Một auto-configuration có condition classpath nên được kiểm thử ở cả hai phía. Spring Boot test cung cấp **ApplicationContextRunner** và các context runner liên quan để tạo context nhỏ, kiểm tra bean được đăng ký theo cấu hình cụ thể.

Ví dụ một cấu hình:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.client.AcmeClient")
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeService acmeService() {
        return new AcmeService();
    }
}
~~~

Để kiểm tra điều kiện classpath thực tế, test phải chạy với classpath tương ứng. Chỉ thay property không thể làm một class đang có trong test classpath biến mất khỏi class loader.

### 14.1. Test nhánh class có mặt

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class AcmeAutoConfigurationTests {
    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AcmeAutoConfiguration.class));

    @Test
    void createsServiceWhenClientClassIsPresent() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AcmeService.class);
        });
    }
}
~~~

Test này chỉ có thể chạy thành công nếu class cần thiết thật sự có mặt trong test runtime classpath và cấu hình không có dependency bắt buộc khác đang thiếu. Trong ví dụ minh họa, AcmeAutoConfiguration được compile với class name dưới dạng chuỗi; bean method không tham chiếu SDK nên không cần client bean.

### 14.2. Test nhánh class vắng mặt

Để kiểm thử class vắng mặt, cần một test runtime classpath **không chứa artifact cung cấp class đó**, hoặc dùng một class loader/test fixture được thiết kế riêng cho mục đích này.

Không thể tạo tình huống vắng class chỉ bằng:

~~~java
.withPropertyValues("acme.client.enabled=false")
~~~

vì property không thay đổi classpath. Nó chỉ tác động điều kiện property, nếu cấu hình có sử dụng @ConditionalOnProperty.

Một cách thực tế là tách kiểm thử auto-configuration optional thành module/test source set có dependency được kiểm soát, để một test chạy khi SDK có mặt và một test chạy khi SDK không được đưa vào runtime classpath.

### 14.3. Kiểm tra cấu hình fallback

Nếu thư viện có nhánh @ConditionalOnMissingClass, hãy xác nhận:

- Khi SDK có mặt, nhánh fallback không được đăng ký.
- Khi SDK vắng mặt, nhánh fallback được đăng ký.
- Hai nhánh không tạo bean trùng tên hoặc nhiều candidate ngoài ý muốn.
- Consumer nhận đúng implementation trong từng môi trường.

Với optional integration, việc test riêng cả hai classpath thường quan trọng hơn việc chỉ kiểm tra một lần startup mặc định.

## 15. Một số ví dụ sử dụng trong thực tế

### 15.1. Tích hợp thư viện JSON tùy chọn

Một starter có thể cung cấp adapter chỉ khi thư viện JSON cụ thể xuất hiện:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public class JsonAdapterAutoConfiguration {
    // Các cấu hình phụ thuộc Jackson.
}
~~~

Nếu Jackson không có mặt, cấu hình adapter không tham gia. Nếu có, Boot có thể tiếp tục xét bean và property cần thiết.

### 15.2. Tích hợp client cloud

Một module có thể hỗ trợ SDK cloud tùy chọn:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.cloud.CloudClient")
public class CloudIntegrationAutoConfiguration {
    // Đăng ký bean tích hợp khi SDK có mặt.
}
~~~

Consumer không dùng cloud SDK không cần bị buộc nạp thư viện đó chỉ vì sử dụng các phần khác của starter.

### 15.3. Chọn implementation theo thư viện hiện diện

Một thư viện có thể có adapter cho nhiều phiên bản hoặc provider khác nhau. Điều kiện classpath cho phép chỉ đăng ký adapter phù hợp với các API đang có. Tuy nhiên, nếu nhiều provider cùng có mặt, cần thiết kế thứ tự hoặc qualifier/bean condition để tránh ambiguity.

Không nên dùng classpath như một cơ chế lựa chọn implementation duy nhất nếu nhiều thư viện có thể cùng xuất hiện. Khi đó cần thêm điều kiện property, bean hoặc cấu hình người dùng.

## 16. Những lỗi thường gặp

### 16.1. @ConditionalOnClass không match dù dependency đã khai báo

Nguyên nhân có thể là dependency chỉ ở compileOnly/provided/test, bị exclude, hoặc class nằm trong artifact khác. Kiểm tra runtime classpath và class name đầy đủ.

### 16.2. Class có mặt nhưng NoClassDefFoundError vẫn xảy ra

Điều kiện chỉ kiểm tra class được chỉ định. Một dependency khác mà class đó cần có thể bị thiếu. Kiểm tra cause chain và toàn bộ dependency graph.

### 16.3. @ConditionalOnMissingClass không kích hoạt

Có thể class đang được kiểm tra thực sự xuất hiện trên runtime classpath qua dependency bắc cầu hoặc một starter khác. Xem dependency tree thay vì chỉ đọc khai báo trực tiếp.

### 16.4. Dùng class literal trong một method có kiểu optional

Class condition ở cấp method không bảo vệ mọi kiểu trong chữ ký method khỏi việc bị JVM resolve sớm. Cô lập method vào nested configuration có class condition.

### 16.5. Dùng name nhưng vẫn tham chiếu optional type trong outer class

name chỉ thay cách ghi tên class trong annotation, nhưng không bảo vệ field, superclass, constructor, method parameter hoặc return type khác đang tham chiếu class optional. Cần cô lập toàn bộ phần phụ thuộc.

### 16.6. Nhầm class condition với bean condition

Class có trên classpath không đồng nghĩa bean đã được đăng ký. Nếu cần kiểm tra bean, dùng @ConditionalOnBean hoặc truy vấn context.

### 16.7. Nghĩ condition sẽ tự thay đổi khi thêm JAR lúc ứng dụng đang chạy

Condition được đánh giá trong quá trình tạo context. Thay đổi file trên đĩa không tự động cập nhật classpath hay bean registry của process hiện tại.

### 16.8. Nghĩ condition match là tính năng chắc chắn chạy

Condition match không xác nhận version compatibility, cấu hình client, kết nối dịch vụ ngoài hoặc khả năng tạo bean thành công.

## 17. Những hiểu nhầm cần tránh

**“Import class trong Java nghĩa là class đã có ở runtime.”**  
Không. Import là cú pháp source; runtime classpath phải chứa class và dependency liên quan.

**“Dependency xuất hiện trong build.gradle nghĩa @ConditionalOnClass chắc chắn match.”**  
Không. Phải xem configuration và runtime classpath thực tế.

**“@ConditionalOnClass kiểm tra bean đã được tạo.”**  
Không. Nó kiểm tra sự hiện diện của class, không kiểm tra bean registry.

**“@ConditionalOnMissingClass là cách viết ngược của @ConditionalOnMissingBean.”**  
Không. Một annotation kiểm tra classpath; annotation kia kiểm tra bean trong Spring context.

**“Class có mặt nghĩa mọi dependency của class cũng đầy đủ.”**  
Không. Class có thể được tìm thấy nhưng khi liên kết hoặc sử dụng vẫn thiếu class khác.

**“Dùng thuộc tính name thì có thể tham chiếu class optional ở bất kỳ method signature nào.”**  
Không. name chỉ thay cách ghi tên class trong annotation; nó không bảo vệ các tham chiếu kiểu khác khỏi việc resolve sớm.

**“@ConditionalOnMissingClass với hai class sẽ match nếu một trong hai vắng mặt.”**  
Không. Tất cả class được liệt kê phải vắng mặt để condition match.

**“Condition được đánh giá lại trên từng request.”**  
Không. Điều kiện được đánh giá trong quá trình xử lý cấu hình và xây dựng context.

**“Positive match trong condition report chứng minh bean đã tạo thành công.”**  
Không. Bean method có thể có điều kiện riêng hoặc thất bại khi khởi tạo.

## Ghi nhớ cốt lõi

**Classpath** quyết định những class nào runtime có thể tìm thấy qua class loader. **@ConditionalOnClass** cho phép Spring Boot chỉ áp dụng cấu hình khi class cần thiết có mặt; **@ConditionalOnMissingClass** cho phép chọn nhánh fallback khi class đó vắng mặt. Khi liệt kê nhiều class, điều kiện yêu cầu tất cả class được chỉ định phải thỏa trạng thái tương ứng.

Hai annotation này đặc biệt quan trọng khi viết starter và auto-configuration có **optional dependencies**. Hãy kiểm tra đúng runtime classpath, phân biệt sự hiện diện của class với sự tồn tại của bean, và cô lập các method/chữ ký tham chiếu optional type trong nested configuration được bảo vệ bằng class condition. Condition match chỉ là bước lựa chọn cấu hình; việc tạo bean, tương thích phiên bản và kết nối dịch vụ vẫn cần được xác nhận riêng.
