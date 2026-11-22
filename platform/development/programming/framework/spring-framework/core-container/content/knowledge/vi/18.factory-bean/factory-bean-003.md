# Khai báo kiểu sản phẩm bằng getObjectType trong Spring FactoryBean

## Mục tiêu

Khi Spring gặp một bean triển khai `FactoryBean<T>`, bean đó hoạt động như **một nhà máy tạo đối tượng được đăng ký dưới tên bean**. Code bên ngoài thường nhận **sản phẩm** của nhà máy qua `getObject()`, trong khi bản thân nhà máy có thể được truy cập với tiền tố `&`.

Để container phát hiện bean theo kiểu, chuẩn bị autowiring và trả lời những truy vấn kiểu như `getType(...)` hoặc `getBeanNamesForType(...)`, Spring cần biết **sản phẩm dự kiến có kiểu gì mà không phải tạo sản phẩm ngay**. Đó là vai trò của `FactoryBean.getObjectType()`.

Đây là bài thuộc mục **FactoryBean** của Spring Framework Core Container. Nội dung tập trung vào hợp đồng `getObjectType()`: trả gì, lúc nào có thể được gọi, ảnh hưởng đến dependency injection, cách xử lý sản phẩm có kiểu động và cách kiểm chứng bằng Java 17.

Sau bài này, bạn có thể:

1. Phân biệt **kiểu FactoryBean** với **kiểu đối tượng do FactoryBean sản xuất**.
2. Cài đúng `Class<?> getObjectType()` và hiểu tại sao trả `null` gây khó khăn khi tìm bean theo kiểu.
3. Giải thích lý do không gọi `getObject()` chỉ để suy ra kiểu sản phẩm.
4. Tự viết và chạy ví dụ `FactoryBean<ApiClient>`, inject sản phẩm vào service và kiểm tra `&beanName`.
5. Phân biệt `getObjectType()`, `getObject()` và `isSingleton()`, cũng như những giới hạn của thông tin kiểu khi generic/proxy/dynamic factory xuất hiện.
6. Chẩn đoán lỗi “bean có tên nhưng không tìm thấy khi autowire theo interface”.

## 1. FactoryBean là gì?

Spring định nghĩa interface:

~~~java
package org.springframework.beans.factory;

public interface FactoryBean<T> {
    T getObject() throws Exception;
    Class<?> getObjectType();
    default boolean isSingleton() {
        return true;
    }
}
~~~

Đây là **chữ ký rút gọn phục vụ giải thích**, không phải mã nguồn bạn phải tự tạo trong package của Spring. Trên Spring hiện đại, `getObject()` có thể trả `null` theo hợp đồng, còn `getObjectType()` cũng có thể trả `null` khi kiểu chưa xác định.

Ba phương thức có trách nhiệm khác nhau:

| Phương thức | Câu hỏi nó trả lời | Tác dụng chính |
| --- | --- | --- |
| `T getObject()` | Sản phẩm cụ thể là object nào? | Tạo hoặc trả đối tượng cần cung cấp cho người dùng bean |
| `Class<?> getObjectType()` | Sản phẩm có kiểu Java nào? | Cho Spring biết kiểu dự kiến để match dependency, kiểm tra metadata, truy vấn bean theo type |
| `boolean isSingleton()` | Factory có luôn cung cấp cùng một tham chiếu sản phẩm để Spring có thể cache không? | Điều khiển semantics/cache của sản phẩm |

**Khác biệt quan trọng:** `FactoryBean<T>` không phải annotation `@Bean` và không phải một factory class Java bất kỳ. Nó là một **Spring SPI đặc biệt**: khi bean do container quản lý implement `FactoryBean`, tên bean thông thường đại diện cho *sản phẩm*; tên với tiền tố `&` đại diện cho *nhà máy*.

Ví dụ, Spring có một bean tên `apiClient` được triển khai bằng `ApiClientFactoryBean`:

~~~text
getBean("apiClient")
      |
      v
Spring lấy FactoryBean
      |
      +-- getObjectType() --> mô tả product type (ApiClient.class)
      |
      +-- getObject() ----> sản phẩm ApiClient

getBean("&apiClient")
      |
      v
ApiClientFactoryBean (bản thân nhà máy)
~~~

Cơ chế này dùng khi tạo đối tượng có logic phức tạp: proxy, client từ thư viện, adapter cần cấu hình, resource wrapper, sản phẩm được chọn theo môi trường hoặc đối tượng không thể khai báo bằng constructor đơn giản.

Nếu chỉ cần trả một object mới từ method cấu hình, `@Bean` thường đủ; không nhất thiết viết thêm `FactoryBean`. `FactoryBean` hữu ích khi cần **metadata kiểu, singleton semantics và logic cung cấp sản phẩm** thông qua SPI của Spring.

## 2. Hợp đồng chính xác của getObjectType()

Chữ ký:

~~~java
@Override
public Class<?> getObjectType() {
    return ApiClient.class;
}
~~~

`getObjectType()` trả **kiểu mà FactoryBean cung cấp qua `getObject()`**, chứ không phải kiểu của factory. Ví dụ nếu `ApiClientFactoryBean implements FactoryBean<ApiClient>` thì mục tiêu hợp lý là `ApiClient.class` hoặc một kiểu sản phẩm cụ thể phù hợp.

Hợp đồng theo Javadoc Spring:

- Có thể trả `null` nếu chưa thể biết kiểu sản phẩm **tại thời điểm truy vấn**.
- Method có thể được Spring gọi **trước khi FactoryBean hoàn tất initialization**; không dựa vào trạng thái chỉ được tạo trong `afterPropertiesSet()` hay `@PostConstruct`.
- Đối với singleton product, hãy **tránh tạo singleton chỉ để biết type**. Tốt nhất ước lượng/biết kiểu từ metadata, constructor parameter hoặc cấu hình sẵn.
- Với sản phẩm dạng prototype/non-singleton, vẫn nên trả về kiểu có ý nghĩa để container tìm được bean.
- Javadoc cảnh báo `FactoryBean` trả `null` tại đây sẽ bị **bỏ qua khi autowiring dựa trên kiểu** trong quá trình tìm candidate; do đó nên cung cấp type ổn định bất cứ khi nào có thể.

### Trả đúng lớp sản phẩm, không trả FactoryBean class

**Đúng:**

~~~java
public final class ClientFactory implements FactoryBean<ApiClient> {
    @Override
    public Class<?> getObjectType() {
        return ApiClient.class;
    }

    @Override
    public ApiClient getObject() {
        return new DefaultApiClient();
    }
}
~~~

Đoạn này là **snippet minh họa**; `ApiClient` và `DefaultApiClient` được định nghĩa ở ví dụ chạy hoàn chỉnh trong mục 6.

**Sai về mặt ý nghĩa:**

~~~java
@Override
public Class<?> getObjectType() {
    return ClientFactory.class; // Sai: đây là factory class, không phải product.
}
~~~

Spring đang hỏi **sản phẩm**, trong khi trên bạn trả **class của factory**. Điều này có thể khiến truy vấn `ApiClient.class` không nhận diện được bean, đồng thời metadata type không nhất quán với object thật do `getObject()` trả về.

Nếu muốn truy xuất bản thân `ClientFactory`, dùng prefix `&` hoặc inject chính FactoryBean theo cơ chế phù hợp; đừng thay đổi `getObjectType()` để phục vụ nhu cầu đó.

## 3. Vì sao Spring cần biết product type trước khi tạo object?

Giả sử có bean factory tên `apiClient` và một service:

~~~java
@Service
class CheckoutService {
    CheckoutService(ApiClient apiClient) {
        // Muốn Spring tự xác định bean cung cấp ApiClient.
    }
}
~~~

Đây là đoạn minh họa constructor injection trong ứng dụng Spring có đầy đủ types. Để resolve parameter `ApiClient`, BeanFactory phải tìm candidate với kiểu assignable tới `ApiClient`.

Một cách trực giác, quá trình gồm:

~~~text
CheckoutService cần dependency ApiClient
              |
              v
BeanFactory liệt kê bean definitions
              |
              v
Gặp bean "apiClient" có FactoryBean
              |
              v
Hỏi / suy luận product type
              |
              +-- getObjectType() = ApiClient.class
              |      |
              |      v
              |   Xác định candidate hợp lệ
              |      |
              |      v
              |   getObject() cung cấp product khi thực sự cần
              |
              +-- getObjectType() = null
                     |
                     v
               Không có thông tin kiểu hữu ích:
               candidate có thể bị bỏ qua trong autowiring
~~~

**Không suy ra mọi lần autowiring luôn gọi `getObjectType()` đúng một lần.** Spring có nhiều con đường suy luận metadata từ bean definition, generic signature, `FactoryBean.OBJECT_TYPE_ATTRIBUTE`, cache và instance factory đã có. Số lần gọi và thời điểm cụ thể là chi tiết implementation phụ thuộc phiên bản/cấu hình. Hợp đồng dành cho người viết FactoryBean là: **method rẻ, an toàn khi gọi sớm và trả type nhất quán**.

### Truy vấn kiểu không tương đương truy xuất sản phẩm

Các API có liên quan:

~~~java
context.getType("apiClient");
context.isTypeMatch("apiClient", ApiClient.class);
context.getBeanNamesForType(ApiClient.class);
context.getBean(ApiClient.class);
~~~

- `getType` / `isTypeMatch` / `getBeanNamesForType` tìm hiểu thông tin kiểu/candidate. Tùy flags/configuration, Spring **có thể** cần khởi tạo FactoryBean để lấy metadata nếu thông tin sớm chưa đủ.
- `getBean(ApiClient.class)` lấy object sử dụng được, nên có thể tạo product khi cần.
- Một lời gọi truy vấn kiểu không có nghĩa sản phẩm nhất thiết đã được tạo; đây chính là điểm thiết kế `getObjectType`.

Dùng `BeanFactory.getType(String name, boolean allowFactoryBeanInit)` nếu muốn kiểm soát việc BeanFactory có được khởi tạo một **FactoryBean chưa khởi tạo** chỉ để xác định kiểu hay không. `allowFactoryBeanInit=false` không có nghĩa Spring bị cấm đọc metadata hoặc loại bỏ mọi FactoryBean đã được tạo.

## 4. Không tạo sản phẩm bên trong getObjectType()

Cách viết dễ gây vấn đề:

~~~java
@Override
public Class<?> getObjectType() {
    return getObject().getClass(); // Không nên: gây tạo product chỉ để tra kiểu.
}
~~~

Với product cần kết nối mạng hoặc tốn nhiều tài nguyên, chỉ thao tác tìm bean theo type đã có thể tạo client, mở socket, chạy initialization không đúng thời điểm. Vòng đời của đối tượng sản phẩm cũng có thể bị làm rối nếu lối này tạo instance rồi bỏ tham chiếu.

Những vấn đề thường gặp:

1. **Side effect** trong lúc container chỉ muốn metadata, đặc biệt ở startup hoặc component scanning.
2. Factory chưa được khởi tạo đầy đủ, `getObject()` đòi field chưa sẵn sàng và ném lỗi.
3. Gây **vòng phụ thuộc/circular initialization** khi `getObject()` cần một bean đang được Spring resolve.
4. Chi phí tăng do repeated type queries hoặc factory trả product mới.
5. Khi product có runtime proxy, `getClass()` trả một proxy-generated class thay vì interface ổn định mà client cần.
6. Nếu `getObject()` có thể trả `null` thì việc gọi `getClass()` còn gây `NullPointerException`.

**Nên làm:** trả một kiểu đã biết từ khai báo hoặc cấu hình không tạo product:

~~~java
@Override
public Class<?> getObjectType() {
    return ApiClient.class;
}
~~~

Nếu kiểu phụ thuộc tham số:

~~~java
public final class TypedFactory<T> implements FactoryBean<T> {
    private final Class<T> productType;
    private final java.util.function.Supplier<? extends T> supplier;

    public TypedFactory(
            Class<T> productType,
            java.util.function.Supplier<? extends T> supplier) {
        this.productType = java.util.Objects.requireNonNull(productType);
        this.supplier = java.util.Objects.requireNonNull(supplier);
    }

    @Override
    public T getObject() {
        return supplier.get();
    }

    @Override
    public Class<?> getObjectType() {
        return productType; // Metadata có ngay từ constructor.
    }

    @Override
    public boolean isSingleton() {
        return false; // Mỗi lookup tạo product mới theo hợp đồng Supplier của ví dụ.
    }
}
~~~

Đây là class Java biên dịch được khi có Spring API import thích hợp (`org.springframework.beans.factory.FactoryBean`). `supplier` có thể tự trả object được chia sẻ nếu caller cố ý làm vậy; trong trường hợp đó cần xét lại `isSingleton()` để khớp hành vi thực tế. Nguyên tắc là truyền **`Class<T>` từ trước**, không để `getObjectType()` buộc tạo sản phẩm.

## 5. Chọn kiểu chính xác: interface hay implementation?

Giả sử nhà máy tạo ra `DefaultApiClient implements ApiClient`. Có hai lựa chọn hợp lý về mặt Java type nếu cả hai đúng với tất cả products có thể tạo:

~~~java
return ApiClient.class;
~~~

hoặc:

~~~java
return DefaultApiClient.class;
~~~

Nên chọn theo **hợp đồng thực mà bean công khai**:

- Nếu các service được thiết kế inject `ApiClient` và factory có thể thay nhiều implementations, trả `ApiClient.class` là hợp lý.
- Nếu factory bảo đảm luôn trả đúng kiểu implementation, trả `DefaultApiClient.class` có thể giúp resolve một dependency yêu cầu kiểu cụ thể.
- Đừng khai báo một type **hẹp hơn hoặc không assignable** so với object thật: Spring có thể đưa ra dự đoán sai rồi gặp lỗi khi lấy product.
- Đừng trả một kiểu chỉ xuất hiện trong *một* nhánh cấu hình nếu các lần tạo khác có thể trả object không tương thích. Chọn hợp đồng chung ổn định.

**Quan trọng:** thông tin kiểu `Class<?>` chưa biểu diễn đầy đủ Java generic arguments như `ApiClient<String>` so với `ApiClient<Long>`. Spring có `ResolvableType` và metadata generic ở bean definition để hỗ trợ matching phức tạp. Nếu ứng dụng cần phân biệt generics, đừng cho rằng riêng `getObjectType()` giải quyết hoàn toàn: nó chỉ trả **raw class**.

### Proxy tạo động

Một `FactoryBean` có thể cung cấp JDK dynamic proxy chỉ implements `ApiClient`. Trong trường hợp đó, trả `ApiClient.class` là chính xác và ổn định; trả `DefaultApiClient.class` sai nếu product cuối cùng **không phải instance** của `DefaultApiClient`.

Đối với class-based proxy, kiểu proxy có thể là subclass của implementation. Thường không cần dùng `proxy.getClass()` làm metadata: trả một superclass/interface rõ ràng mà proxy luôn implement sẽ bền vững hơn.

## 6. Ví dụ hoàn chỉnh Java 17 và Spring Framework 6.2

Ví dụ dùng `FactoryBean<ApiClient>` tạo singleton product và minh họa:

- `getObjectType()` công bố kiểu interface **ApiClient**.
- Bean `CheckoutService` được autowire theo `ApiClient`.
- `getBean("apiClient")` nhận sản phẩm, `getBean("&apiClient")` nhận nhà máy.
- `getType("apiClient")` xem product type; `getType("&apiClient")` xem factory type.
- `isSingleton()` khai báo cùng một sản phẩm được tái sử dụng.
- `getObjectType()` không có side effect tạo sản phẩm.

### 6.1. Cấu trúc

~~~text
factory-object-type-demo/
├── pom.xml
└── src/main/java/demo/
    └── FactoryObjectTypeDemo.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>factory-object-type-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
~~~

### 6.3. src/main/java/demo/FactoryObjectTypeDemo.java

~~~java
package demo;

import org.springframework.beans.factory.FactoryBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class FactoryObjectTypeDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            // Bean theo tên thường: lấy sản phẩm.
            ApiClient client = context.getBean("apiClient", ApiClient.class);

            // Dấu &: yêu cầu chính FactoryBean.
            ApiClientFactoryBean factory =
                    context.getBean("&apiClient", ApiClientFactoryBean.class);

            // Bean khác được inject theo ApiClient.
            CheckoutService service = context.getBean(CheckoutService.class);

            System.out.println("productType="
                    + context.getType("apiClient").getSimpleName());
            System.out.println("factoryType="
                    + context.getType("&apiClient").getSimpleName());
            System.out.println("result=" + service.checkout("42"));
            System.out.println("sameProduct="
                    + (client == context.getBean(ApiClient.class)));
            System.out.println("created=" + factory.creationCount());
        }
    }

    public interface ApiClient {
        String request(String id);
    }

    public static final class DefaultApiClient implements ApiClient {
        @Override
        public String request(String id) {
            return "ok:" + id;
        }
    }

    public static class ApiClientFactoryBean implements FactoryBean<ApiClient> {
        private ApiClient cached;
        private int created;

        @Override
        public synchronized ApiClient getObject() {
            if (cached == null) {
                cached = new DefaultApiClient();
                created++;
            }
            return cached;
        }

        @Override
        public Class<?> getObjectType() {
            return ApiClient.class; // Không gọi getObject().
        }

        @Override
        public boolean isSingleton() {
            return true;
        }

        public synchronized int creationCount() {
            return created;
        }
    }

    public static class CheckoutService {
        private final ApiClient client;

        public CheckoutService(ApiClient client) {
            this.client = client;
        }

        public String checkout(String id) {
            return client.request(id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean(name = "apiClient")
        public static ApiClientFactoryBean apiClientFactory() {
            return new ApiClientFactoryBean();
        }

        @Bean
        public static CheckoutService checkoutService(ApiClient apiClient) {
            return new CheckoutService(apiClient);
        }
    }
}
~~~

### 6.4. Cách chạy

Yêu cầu Java 17+ và Maven. Tại thư mục `factory-object-type-demo`:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=demo.FactoryObjectTypeDemo
~~~

**Stdout của chương trình** (bỏ qua log Maven/hạ tầng nếu môi trường in thêm):

~~~text
productType=ApiClient
factoryType=ApiClientFactoryBean
result=ok:42
sameProduct=true
created=1
~~~

### 6.5. Vì sao output như vậy?

1. `@Bean(name = "apiClient")` đăng ký **FactoryBean instance** dưới tên `apiClient`. Vì class implement `FactoryBean<ApiClient>`, container có logic dereference đặc biệt.
2. `getObjectType()` trả `ApiClient.class` để Spring biết kiểu sản phẩm khi tìm bean theo interface; nó không tự tạo `DefaultApiClient`.
3. Khi Spring tạo `CheckoutService(ApiClient apiClient)` hoặc khi `getBean("apiClient")` được gọi, BeanFactory lấy sản phẩm do `getObject()` cung cấp. Factory trong ví dụ trả cùng instance được cache.
4. `getType("apiClient")` trả thông tin product type `ApiClient`, nên in `productType=ApiClient`.
5. `getType("&apiClient")` trả class của factory, nên in `factoryType=ApiClientFactoryBean`.
6. `CheckoutService.checkout("42")` gọi client và trả `ok:42`.
7. `context.getBean(ApiClient.class)` và biến `client` tham chiếu cùng sản phẩm (vì chỉ có một candidate `ApiClient` và factory singleton).
8. Counter `created` tăng một lần khi `DefaultApiClient` được tạo, nên kết quả `created=1`.

**Lưu ý:** Ví dụ dùng synchronization bên trong FactoryBean để đảm bảo `getObject()` không tạo trùng product nếu bị gọi đồng thời. Với `isSingleton() == true`, Spring cũng có thể cache sản phẩm trong BeanFactory. Đây là hai lớp cơ chế riêng; với code production cần thống nhất ownership và lifecycle của product để tránh double caching/hủy sai.

### 6.6. Thử thay đổi một dòng để thấy lỗi

Đổi:

~~~java
@Override
public Class<?> getObjectType() {
    return null;
}
~~~

Khi đó Spring không được bảo đảm tìm thấy `apiClient` làm candidate theo `ApiClient` trong autowiring, đặc biệt khi chưa có product hoặc chưa có type metadata đủ tốt. Bean `CheckoutService` yêu cầu `ApiClient` có thể báo lỗi `NoSuchBeanDefinitionException` được bọc bởi `UnsatisfiedDependencyException`.

**Không khẳng định mọi chương trình trả null đều nhất thiết thất bại ở cùng một dòng.** Spring có thể suy ra generic/metadata khác hoặc đã tạo product từ trước. Hợp đồng SPI vẫn khuyến nghị **trả kiểu dự kiến sớm**; dựa vào suy luận thay thế khi biết rõ type là thiết kế kém ổn định.

Đổi sang:

~~~java
@Override
public Class<?> getObjectType() {
    return ApiClientFactoryBean.class;
}
~~~

Đây là sai kiểu sản phẩm: container có thể dự đoán `apiClient` như một FactoryBean thay vì `ApiClient`, ảnh hưởng đến type matching. Bản thân factory vẫn có thể truy cập qua `&apiClient`; cách đó **không cần** đổi metadata product.

Nếu trả `DefaultApiClient.class`, ví dụ vẫn có thể phù hợp vì sản phẩm là implementation ấy. Tuy nhiên nếu sau này factory chuyển sang JDK proxy chỉ implements `ApiClient`, khai báo concrete class sẽ sai. Lựa chọn `ApiClient.class` phản ánh API ổn định hơn.

## 7. getObjectType() không quyết định singleton/prototype

Một nhầm lẫn phổ biến: “Trả cùng `Class<?>` nghĩa là Spring sẽ luôn tạo cùng instance”. Không đúng. **Kiểu** và **vòng đời** là hai thông tin độc lập.

~~~java
@Override
public Class<?> getObjectType() {
    return ApiClient.class;
}

@Override
public boolean isSingleton() {
    return false;
}

@Override
public ApiClient getObject() {
    return new DefaultApiClient();
}
~~~

Đây là snippet minh họa trong `ApiClientFactoryBean`, không phải toàn bộ chương trình độc lập.

Trong cấu hình này, mỗi lần BeanFactory lấy sản phẩm từ factory có thể nhận **một instance khác**; `getObjectType()` vẫn luôn là `ApiClient.class`. Bản thân bean factory có thể là singleton còn sản phẩm của nó không là singleton.

Cẩn thận:

- `isSingleton() == true` phải tương thích với factory cung cấp một object dùng chung. Nếu factory báo true nhưng trả object mới cho mỗi lần gọi, Spring có thể cache một object và hành vi trực tiếp gọi factory lại khác, gây rối semantics.
- `isSingleton() == false` không tự chứng minh mọi object trả về chắc chắn độc lập trong mọi tình huống; Spring có `SmartFactoryBean.isPrototype()` để mô tả thêm.
- BeanFactory cache product singleton theo cơ chế riêng; đừng dùng `getObjectType()` để tạo side effects “warm-up” hoặc chuẩn bị cache.
- Cleanup của sản phẩm do `FactoryBean` tạo cần được thiết kế theo quyền sở hữu và lifecycle phù hợp; không suy luận rằng chỉ vì factory đã close thì mọi product của mọi scope đều được đóng tự động.

## 8. Trả null khi kiểu thực sự chưa biết

Contract cho phép:

~~~java
@Override
public Class<?> getObjectType() {
    return resolvedType; // Có thể null trong giai đoạn quá sớm.
}
~~~

Ví dụ một factory được cấu hình bằng tên class từ external metadata chỉ có vào giai đoạn startup sau, và chưa thể biết kiểu sản phẩm tại thời điểm Spring truy vấn. Trả `null` lúc này **hợp lệ theo API**, nhưng có chi phí:

1. Container không biết chắc factory có đáp ứng injection point dựa trên type không.
2. `ListableBeanFactory` tìm candidate có thể bỏ qua factory khi không nhận được kiểu thích hợp.
3. `BeanFactory.getType("name")` có thể trả `null`.
4. Các công cụ phân tích type hoặc component đăng ký dựa vào bean types có thể nhìn thấy thiếu một bean.
5. Kết quả có thể phụ thuộc trình tự khởi tạo nếu type chỉ xuất hiện sau initialization.

Nếu bạn biết một **interface chung ổn định** nhưng chưa biết implementation cụ thể, trả interface đó thay vì `null`. Ví dụ các implementation `HttpApiClient` và `MockApiClient` đều implements `ApiClient`; `getObjectType()` vẫn có thể trả `ApiClient.class`.

Nếu hoàn toàn không thể công bố type sớm, hãy cân nhắc điều chỉnh cấu trúc factory để truyền type bằng constructor/configuration, hoặc cho downstream dependency dùng một API khám phá tường minh thay vì autowiring mù.

### Không dựa vào trạng thái khởi tạo muộn

Một anti-pattern:

~~~java
private Class<?> type;

@Override
public void afterPropertiesSet() {
    type = expensiveRegistry.resolveProductClass();
}

@Override
public Class<?> getObjectType() {
    return type;
}
~~~

Đây là snippet đặt trong class `FactoryBean` đồng thời implements `InitializingBean`, với `expensiveRegistry` chỉ là dependency minh họa. Spring có thể gọi `getObjectType()` **trước** `afterPropertiesSet()`; kết quả null làm bean không hiện diện trong một số bước type discovery. Nếu type bắt buộc từ cấu hình, nên đưa thông tin sớm qua constructor hoặc BeanDefinition metadata thay vì đợi init callback.

## 9. Generic FactoryBean<T> và các giới hạn suy luận kiểu

Khai báo:

~~~java
class ApiClientFactoryBean implements FactoryBean<ApiClient> { ... }
~~~

tham số generic `ApiClient` **có thể giúp Spring suy luận kiểu sản phẩm từ class/bean definition metadata**. Tuy nhiên:

- `getObjectType()` vẫn là API chính thức dùng để trả product type khi Spring hỏi FactoryBean instance.
- Generic type có thể bị xóa/bị che bởi raw declarations, factory methods trả kiểu tổng quát, proxy hoặc registration programmatic.
- `FactoryBean<List<String>>` và `FactoryBean<List<Long>>` đều có raw product class `List.class`; method trả `Class<?>` không thể biểu diễn khác biệt của type arguments.
- Autowire theo generic phức tạp dựa thêm vào `ResolvableType`, declaration và metadata. Không cố ép `getObjectType()` trả một “Class<List<String>>” không tồn tại do Java type erasure.

Ví dụ factory method khai báo kiểu quá chung:

~~~java
@Bean
public FactoryBean<?> someFactory() {
    return new ApiClientFactoryBean();
}
~~~

Spring có thể có ít thông tin tĩnh hơn so với:

~~~java
@Bean
public ApiClientFactoryBean apiClientFactory() {
    return new ApiClientFactoryBean();
}
~~~

Đây là snippets minh họa trong lớp `@Configuration`. Khi cần type discovery sớm, giữ chữ ký return type **đủ cụ thể để Spring suy luận** và implementation `getObjectType()` đúng. Đừng giả định “đã ghi generic `<ApiClient>`” là đủ trong mọi đường registration.

## 10. FactoryBean.OBJECT_TYPE_ATTRIBUTE: metadata nâng cao

Spring có hằng:

~~~java
FactoryBean.OBJECT_TYPE_ATTRIBUTE
~~~

Nó là tên attribute trên `BeanDefinition`, dùng khi framework/registrar cần **công bố trước kiểu sản phẩm mà không phải khởi tạo FactoryBean**. Đây là API hạ tầng, không phải điều mà ứng dụng bình thường phải cấu hình bằng tay.

Trong Spring 6.1+ và 6.2, metadata được xử lý theo kiểu `Class<?>` hoặc `ResolvableType` thích hợp; không được tùy tiện đặt **tên class dạng String** vào attribute này và kỳ vọng Spring tự chuyển. Một giá trị `String` có thể gây:

~~~text
IllegalArgumentException:
Invalid value type for attribute 'factoryBeanObjectType': java.lang.String
~~~

Đây là triệu chứng của **metadata BeanDefinition không đúng loại**, không phải lỗi của method `getObjectType()` đơn thuần. Khi làm framework integration/registrar, hãy dùng kiểu metadata hợp lệ và API chính thức:

~~~java
// BeanDefinition bd đã được tạo từ registration code.
bd.setAttribute(
        FactoryBean.OBJECT_TYPE_ATTRIBUTE,
        ApiClient.class);
~~~

Đây là **snippet programmatic registration**, yêu cầu biến `bd` kiểu `org.springframework.beans.factory.config.BeanDefinition` và import `FactoryBean`/`ApiClient` thích hợp; không phải file chạy độc lập. Nếu cần generic-rich metadata, cân nhắc `ResolvableType` tương ứng. Đặt attribute đúng không cho phép implementation `getObjectType()` dối về runtime product type; metadata và đối tượng thực phải thống nhất.

Hầu hết business applications **không cần** can thiệp `OBJECT_TYPE_ATTRIBUTE`. Nếu chỉ muốn triển khai một `FactoryBean`, trả đúng class từ `getObjectType()` là điều cần làm trước.

## 11. Phân biệt getType, getObject và &beanName

Một biểu đồ ngắn:

~~~text
BeanDefinition: name = "apiClient"
                    |
                    v
             ApiClientFactoryBean
               /      |       \
              /       |        \
     getObjectType  getObject  isSingleton
          |           |           |
    ApiClient.class  ApiClient   true
          |           |           |
    metadata match    object     cache semantics

getType("apiClient")   --> type của product (ApiClient)
getBean("apiClient")   --> product ApiClient
getBean("&apiClient")  --> factory ApiClientFactoryBean
getType("&apiClient")  --> type của factory
~~~

Cần nhớ:

- `getObjectType()` do chính FactoryBean **công bố** kiểu sản phẩm.
- `BeanFactory.getType(name)` là API phía container **hỏi** về kiểu một bean theo tên.
- `FactoryBean.getObject()` là API phía factory **cung cấp** sản phẩm.
- `BeanFactory.getBean(name)` là API phía consumer **nhận** bean; nếu tên chỉ FactoryBean, consumer nhận product.
- `&name` là quy ước dereference lấy factory, không phải một bean definition thông thường thứ hai.
- `isSingleton()` điều khiển semantics caching của product, khác với scope của FactoryBean instance.

Không nhầm với `ObjectFactory<T>`:

~~~java
ObjectFactory<ApiClient> provider;
~~~

`ObjectFactory<T>` là API lấy object theo yêu cầu; `FactoryBean<T>` là **Spring bean special factory** sở hữu product type metadata và tên bean đặc biệt. Hai interface khác nhau.

## 12. Type matching, @Autowired và sự cố thực tế

Khi service yêu cầu:

~~~java
public CheckoutService(ApiClient apiClient) { ... }
~~~

Spring sẽ tìm candidate tương thích với `ApiClient`. Các điều kiện liên quan:

1. Một BeanDefinition đại diện cho FactoryBean hoặc một product-type metadata khác có đủ thông tin.
2. `getObjectType()` không trả một kiểu không liên quan đến `ApiClient`.
3. Không có nhiều candidates cùng kiểu gây ambiguity, hoặc đã có `@Primary`/`@Qualifier`/tên parameter làm rõ.
4. FactoryBean có thể được khởi tạo/sử dụng tại thời điểm cần, không có lỗi circular dependency.
5. `getObject()` cuối cùng trả product tương thích kiểu dependency.

Nếu có **hai** FactoryBeans đều công bố `ApiClient.class` và hai products tương ứng, `@Autowired ApiClient` có thể báo `NoUniqueBeanDefinitionException`. Sửa bằng `@Qualifier("apiClient")` hoặc `@Primary` theo ý đồ, không sửa `getObjectType()` thành một kiểu giả để tránh ambiguity.

Ví dụ thêm `@Qualifier` khi cần:

~~~java
public CheckoutService(
        @org.springframework.beans.factory.annotation.Qualifier("apiClient")
        ApiClient apiClient) {
    this.client = apiClient;
}
~~~

Đây là constructor snippet trong lớp `CheckoutService`, giả định có nhiều `ApiClient` beans cùng context. Với một candidate duy nhất như ví dụ mục 6, qualifier không cần.

### Chẩn đoán theo type và theo name

Nếu `getBean("apiClient")` trả product nhưng `getBean(ApiClient.class)` báo không có bean, ưu tiên xem:

- `FactoryBean.getObjectType()` có trả `null` khi Spring cần resolve type không?
- Nó có trả **factory class** thay vì **product class**?
- Signature `@Bean` trả raw `FactoryBean<?>` khiến metadata sớm không rõ?
- Product trả về có implement interface đúng như khai báo không?
- Bean có đang được đăng ký trong đúng `ApplicationContext` không?
- Có scope/conditional registration khiến definition không tồn tại không?

Trong một test riêng, bạn có thể in:

~~~java
System.out.println(context.getType("apiClient"));
System.out.println(context.getType("&apiClient"));
System.out.println(java.util.Arrays.toString(
        context.getBeanNamesForType(ApiClient.class)));
~~~

Đây là snippet đặt trong method có biến `context` và `ApiClient` của ứng dụng. Việc hỏi tên theo kiểu có thể kích hoạt FactoryBean initialization tùy flags; nếu chỉ muốn kiểm tra metadata mà tránh eager init, xem overload `getBeanNamesForType(type, includeNonSingletons, allowEagerInit)` và hiểu giới hạn của nó.

**Đừng sửa lỗi bằng cách khởi tạo product thủ công trong `getObjectType()`**. Điều đó có thể vô tình khiến bài test có vẻ thành công nhưng tạo side effects ở bước tra metadata.

## 13. Kiểm thử hợp đồng getObjectType độc lập

Một `FactoryBean` tốt nên được kiểm tra ở hai cấp.

### 13.1. Unit test FactoryBean không cần context

Đặt test logic như sau (snippet trong method test, dùng class của ví dụ mục 6):

~~~java
var factory = new FactoryObjectTypeDemo.ApiClientFactoryBean();

if (factory.getObjectType() != FactoryObjectTypeDemo.ApiClient.class) {
    throw new AssertionError("Wrong product type");
}
if (factory.creationCount() != 0) {
    throw new AssertionError("getObjectType unexpectedly created product");
}

var first = factory.getObject();
var second = factory.getObject();

if (first != second) {
    throw new AssertionError("Expected shared singleton product");
}
if (!factory.getObjectType().isInstance(first)) {
    throw new AssertionError("Product not assignable to advertised type");
}
~~~

Test này chứng minh trực tiếp:

- `getObjectType()` trả type chính xác và không tạo product.
- `getObject()` trả một sản phẩm assignable tới type đã công bố.
- Với factory singleton mẫu, nhiều lời gọi trả cùng reference.

Tuy nhiên unit test không chứng minh Spring autowiring hoặc factory dereference hoạt động; chúng cần integration test.

### 13.2. Integration test với Spring container

Tạo `AnnotationConfigApplicationContext` từ `Config` trong mục 6, rồi kiểm tra:

- `context.getType("apiClient")` tương thích với `ApiClient.class`.
- `context.getType("&apiClient")` là `ApiClientFactoryBean.class`.
- `context.getBean("apiClient")` là `ApiClient` product.
- `context.getBean("&apiClient")` là FactoryBean.
- `context.getBean(CheckoutService.class)` đã được inject product.
- `context.getBeanNamesForType(ApiClient.class)` bao gồm tên `apiClient`.
- `getObject()` thực sự được gọi khi cần sản phẩm, không dùng `getObjectType()` làm chỗ khởi tạo side effects.
- FactoryBean `isSingleton()` đúng semantics; kiểm tra object identity.
- Khi trả `null`/sai type, ghi nhận ảnh hưởng thực tế theo Spring version và metadata thay vì đoán một exception cố định.

### 13.3. Các ca test có giá trị bổ sung

| Ca test | Mục tiêu |
| --- | --- |
| Factory có product chưa tạo, gọi `getObjectType` | Không tạo resource |
| Factory trước `afterPropertiesSet` | Không NPE/không dựa vào field khởi tạo muộn |
| Product là JDK dynamic proxy | Advertised type là interface mà proxy implements |
| Product dùng nhiều implementation | Type công bố là hợp đồng chung ổn định |
| Product loại non-singleton | `getObjectType` không đổi semantics tạo mới |
| FactoryBean generic bị che bởi raw type | Explicit metadata vẫn đủ cho type discovery |
| Nhiều products cùng API | Autowiring báo ambiguity hoặc qualifier chọn đúng |
| Có vòng phụ thuộc | `getObjectType` không gọi `getObject` tạo thêm vòng |
| Metadata `OBJECT_TYPE_ATTRIBUTE` programmatic | Kiểu Class/ResolvableType hợp lệ; không dùng String |
| Đóng context | Resource được hủy theo ownership và scope phù hợp |

## 14. Những lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| `@Autowired ApiClient` không tìm thấy candidate | `getObjectType()` trả null khi type discovery | Trả `ApiClient.class` nếu interface đã biết |
| Bean theo name tồn tại nhưng bean theo type không thấy | Trả kiểu factory hoặc kiểu sản phẩm sai | Trả type của object `getObject()` cung cấp |
| Truy vấn type mở socket ngoài ý muốn | `getObjectType()` gọi `getObject()` | Không tạo product trong type query |
| `NullPointerException` khi refresh/autowire | `getObjectType` dựa trên field chỉ có sau init | Dùng type metadata sẵn từ constructor/config |
| `NoUniqueBeanDefinitionException` | Nhiều products assignable cùng interface | `@Qualifier` hoặc `@Primary` |
| ClassCastException hoặc type mismatch khi getBean | Product runtime không assignable type đã báo | Sửa metadata và contract product |
| Chọn runtime proxy class trong `getObjectType` | Type không ổn định hoặc proxy chưa có | Trả API interface/superclass ổn định |
| Bean factory nhìn thấy qua tên thường thay vì product | Nhầm cách dùng `&` | `getBean("&name")` lấy factory, `getBean("name")` lấy product |
| `isSingleton()=true` nhưng factory trả object mới | Semantics factory sai/caching gây bất ngờ | Đồng bộ contract, cache đúng hoặc trả false |
| `getObjectType()` cố biểu diễn generics | `Class<?>` không thể biểu diễn full parameterized type | Dùng `ResolvableType`/bean metadata khi thích hợp |
| Lỗi `factoryBeanObjectType: java.lang.String` | Registrar đặt BeanDefinition attribute sai loại | Dùng `Class<?>` hoặc `ResolvableType`, không dùng class name String |
| FactoryBean tạo product đắt ngay khi tìm type | Side effects trong type metadata hoặc type discovery eager | Công bố type sớm và dùng overload tránh eager init khi phù hợp |
| Component dùng `@Bean` trả `FactoryBean<?>` quá chung | Metadata kiểu tĩnh yếu | Khai báo concrete FactoryBean return type nếu có thể |

## 15. Checklist thiết kế FactoryBean product type

1. Xác định một **hợp đồng type ổn định** mà mọi product luôn thực thi.
2. Implement `getObjectType()` trả `Class<?>` của **product**, không phải FactoryBean.
3. Không gọi `getObject()`, mở connection, truy cập mạng hay tạo expensive resources trong `getObjectType()`.
4. Cho phép `getObjectType()` chạy trước init; dùng metadata từ constructor/config nếu cần.
5. Chỉ trả `null` khi type thực sự chưa thể biết; hiểu hậu quả cho autowiring.
6. Đảm bảo `getObject()` luôn trả object assignable tới type công bố.
7. Đặt `isSingleton()` phù hợp product identity/cache semantics.
8. Đăng ký FactoryBean bằng class/`@Bean` method đủ rõ type, tránh raw metadata khi không cần.
9. Dùng `&beanName` khi muốn lấy factory, tên thường khi lấy product.
10. Test type discovery và autowiring trong ApplicationContext ngoài unit test của FactoryBean.
11. Với dynamic proxy, ưu tiên interface hoặc superclass chung chứ không trả runtime proxy class.
12. Với registrar, dùng `FactoryBean.OBJECT_TYPE_ATTRIBUTE` đúng kiểu metadata.
13. Phân biệt lỗi type lookup với lỗi tạo product, scope, qualifier và duplicate candidates.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `FactoryBean.getObjectType()` trả kiểu gì?  
**Đáp:** Kiểu của **đối tượng sản phẩm** do `getObject()` cung cấp, chứ không phải class của chính FactoryBean.

**Câu 2.** Vì sao không gọi `getObject()` trong `getObjectType()` để lấy `getClass()`?  
**Đáp:** Vì type discovery có thể xảy ra trước khi factory sẵn sàng và không nên tạo resource/side effect chỉ để xác định kiểu.

**Câu 3.** `getObjectType()` trả `null` có hợp lệ không?  
**Đáp:** Có nếu chưa biết type, nhưng Spring có thể bỏ qua FactoryBean khi autowiring theo type; nên trả interface chung nếu biết.

**Câu 4.** `getBean("client")` và `getBean("&client")` khác nhau thế nào khi tên `client` thuộc FactoryBean?  
**Đáp:** Tên thường lấy sản phẩm, tên với tiền tố `&` lấy FactoryBean instance.

**Câu 5.** Nếu product là JDK proxy thực thi `ApiClient`, có nên trả `DefaultApiClient.class` không?  
**Đáp:** Không nếu proxy không phải instance của `DefaultApiClient`. Trả `ApiClient.class`.

**Câu 6.** FactoryBean có thể báo `isSingleton() == false` và vẫn trả `ApiClient.class` không?  
**Đáp:** Có. Một thông tin mô tả type, một thông tin mô tả cách quản lý identity của product.

**Câu 7.** Generic `FactoryBean<ApiClient>` có làm `getObjectType` trở nên vô nghĩa không?  
**Đáp:** Không. Spring có thể suy luận từ generics nhưng metadata còn phụ thuộc cách đăng ký, proxy và các bước type discovery; method vẫn là SPI chính thức.

**Câu 8.** Khi hai FactoryBeans cùng công bố `ApiClient.class`, cách sửa ambiguity là gì?  
**Đáp:** Dùng `@Qualifier`, `@Primary` hoặc thiết kế API injection rõ ràng; không khai gian product type.

**Câu 9.** `FactoryBean.OBJECT_TYPE_ATTRIBUTE` có thể nhận chuỗi `"demo.ApiClient"` không?  
**Đáp:** Không nên; trong các phiên bản Spring 6.1+/6.2, dữ liệu kiểu hợp lệ là `Class<?>` hoặc `ResolvableType`, còn String có thể gây IllegalArgumentException.

**Câu 10.** Có cần tạo product chỉ để `getBeanNamesForType(ApiClient.class)` thấy bean không?  
**Đáp:** Không. Thiết kế `getObjectType()` đúng để Spring có cơ sở xác định candidate trước khi product tồn tại.

## Tài liệu chính thức

- Spring Framework Javadoc 6.2: [FactoryBean](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/FactoryBean.html) — hợp đồng `getObject()`, `getObjectType()`, `isSingleton()`, `OBJECT_TYPE_ATTRIBUTE`.
- Spring Framework Reference: [Extension Points — Customizing Instantiation Logic with a FactoryBean](https://docs.spring.io/spring-framework/reference/core/beans/definition.html#beans-factory-extension-factorybean).
- Spring Framework Javadoc: [BeanFactory](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/BeanFactory.html) — `&` dereference, `getType(name)`.
- Spring Framework Javadoc: [ListableBeanFactory](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/ListableBeanFactory.html) — type lookup, overload `getBeanNamesForType` và `allowEagerInit`.
- Spring Framework Javadoc: [FactoryBeanRegistrySupport](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/support/FactoryBeanRegistrySupport.html).
