# Ý nghĩa của `isSingleton()` đối với sản phẩm do FactoryBean tạo ra

## 1. Vấn đề cần hiểu: một FactoryBean có hai “đối tượng” khác nhau

Trong Spring Core Container, `FactoryBean<T>` không chỉ là một bean bình thường có method tạo đối tượng. Đây là một **điểm mở rộng của container**: khi Spring thấy một bean implements `FactoryBean`, một lần lấy bean theo tên thông thường sẽ trả về **sản phẩm của factory** thông qua `getObject()`, chứ không trả về chính factory.

Điều này tạo ra hai đối tượng cần phân biệt:

1. **FactoryBean instance:** object Java implements `org.springframework.beans.factory.FactoryBean<T>`, do Spring tạo và quản lý như một bean definition.
2. **Product instance:** object kiểu `T` được factory trả từ `getObject()`, có thể được Spring cache và cấp cho những chỗ khác trong ứng dụng.

Method `isSingleton()` của `FactoryBean` trả lời câu hỏi:

> **Sản phẩm do factory công bố có phải là một object dùng chung, có thể được BeanFactory cache và dùng lại hay không?**

Nó **không** tự khai báo scope của **FactoryBean instance**. Factory có thể là singleton nhưng sản phẩm lại là non-singleton. Tương tự, chỉ nhìn `FactoryBean.isSingleton() == true` không đủ để kết luận sản phẩm là singleton xuyên suốt mọi lần lookup nếu chính factory bean được cấu hình prototype.

Đây là khác biệt trọng tâm của bài.

### Mục tiêu học tập

Sau bài này bạn có thể:

- Phân biệt `FactoryBean` và object sản phẩm `getObject()`.
- Giải thích đúng `FactoryBean.isSingleton()`, giá trị mặc định và cơ chế cache của container.
- So sánh scope của factory bean definition với singleton/non-singleton status của sản phẩm.
- Hiểu tại sao `false` **không đồng nghĩa chắc chắn với prototype instance độc lập**.
- Dùng `SmartFactoryBean.isPrototype()` và `BeanFactory.isPrototype(name)` khi cần semantics prototype.
- Biết `getBean("name")` so với `getBean("&name")`, cũng như cách kiểm tra `isSingleton` trên từng tên.
- Chạy ví dụ Spring Context 6.1.x, Java 17 để chứng minh identity và số lần `getObject()` được gọi.
- Tránh bug khai báo sai `isSingleton()` khi sản phẩm có mutable state, tài nguyên hoặc cần tạo mới cho mỗi nghiệp vụ.

## 2. Hợp đồng của `FactoryBean<T>`

Interface nằm ở package `org.springframework.beans.factory`.

~~~java
import org.springframework.beans.factory.FactoryBean;

// Chữ ký API rút gọn nhằm giải thích, không cần tự định nghĩa lại.
public interface FactoryBean<T> {
    T getObject() throws Exception;

    Class<?> getObjectType();

    default boolean isSingleton() {
        return true;
    }
}
~~~

Ba method cần hiểu riêng:

| Method | Hỏi điều gì? | Trách nhiệm |
| --- | --- | --- |
| `getObject()` | Sản phẩm được expose là object nào? | Tạo hoặc trả một product instance đúng hợp đồng |
| `getObjectType()` | Sản phẩm có kiểu gì? | Cho container cơ sở nhận diện type mà không cần tạo sản phẩm trước |
| `isSingleton()` | Sản phẩm có thể được dùng chung như singleton không? | Chỉ trả `true` khi product được expose nhất quán là cùng một reference có thể cache |

Trong Spring Framework 6.1, `isSingleton()` có **default implementation trả `true`**. Bạn có thể override để trả `false` khi sản phẩm không phải shared singleton.

`FactoryBean<T>` là abstraction đặc biệt của Spring, **khác** interface `BeanFactory`. Đổi vị trí hai từ làm thay đổi toàn bộ ý nghĩa:

- `BeanFactory` là **container interface**, có `getBean(name)`, `isSingleton(name)`, `isPrototype(name)`, v.v.
- `FactoryBean<T>` là **factory object được container quản lý** để sinh/expose sản phẩm `T`.

Cũng không nhầm `FactoryBean<T>` với annotation `@Bean`: `@Bean` đánh dấu một Java factory method tạo bean definition; phương thức `@Bean` có thể trả một đối tượng implement `FactoryBean<T>`, lúc đó Spring tiếp tục xử lý đặc biệt sản phẩm của factory.

## 3. Nhìn bằng tên: `name` là product, `&name` là factory

Nếu đăng ký một `FactoryBean<Product>` với tên `productFactory`:

~~~java
Object product = context.getBean("productFactory");

Object factory = context.getBean("&productFactory");
~~~

Đây là đoạn minh họa trong một ứng dụng Spring có bean definition `productFactory` implement `FactoryBean`.

- `getBean("productFactory")` lấy **sản phẩm** do `getObject()` expose.
- `getBean("&productFactory")` lấy **chính FactoryBean instance**.
- Dấu `&` là **factory dereference prefix** của Spring, không phải một toán tử Java và cũng không đổi tên bean definition thực.
- Tên đăng ký của bean factory vẫn là `productFactory`; ký hiệu `&productFactory` dùng trong một số API lookup để nói rõ “trả factory thay vì sản phẩm”.

### Hai phương thức cùng tên nhưng khác chủ thể

~~~java
factoryBean.isSingleton();      // Hỏi product do factory quản lý.
context.isSingleton("productFactory");  // Hỏi object được expose theo tên sản phẩm.
context.isSingleton("&productFactory"); // Hỏi chính factory instance.
~~~

Ba câu hỏi liên quan nhưng **không được nhập làm một**:

- `FactoryBean.isSingleton()` thuộc contract **sản phẩm**.
- `BeanFactory.isSingleton("productFactory")` mô tả semantics **lookup theo tên product**.
- `BeanFactory.isSingleton("&productFactory")` mô tả **factory object** được lookup qua prefix `&`.

Trong cấu hình phổ biến factory bean itself là singleton, hai kết quả đầu sẽ phù hợp nhau. Kết quả cho `&name` có thể khác hẳn nếu factory trả các sản phẩm non-singleton.

## 4. `isSingleton() == true`: tuyên bố sản phẩm dùng chung

Một factory trả `true` có nghĩa `getObject()` được công bố là trả **cùng object reference** — một reference có thể được container cache.

~~~java
public final class SharedClientFactory implements FactoryBean<Client> {
    private final Client shared = new Client();

    @Override
    public Client getObject() {
        return shared;
    }

    @Override
    public Class<?> getObjectType() {
        return Client.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }
}
~~~

Đây là class minh họa; cần import `FactoryBean` và định nghĩa `Client`.

Nếu factory bean được đăng ký dưới dạng singleton theo bean definition, Spring có thể cache object trả bởi `getObject()`. Hai lần `context.getBean("sharedClient")` thông thường trả cùng reference.

Quan trọng: **cache là cơ chế tối ưu/đảm bảo lookup semantics của BeanFactory, không phải một lời hứa rằng Spring sẽ gọi `getObject()` trước hoặc đúng một lần trong mọi trường hợp**. Javadoc nói product **có thể được cache**; implementation phải đúng ngay cả khi Spring quyết định thời điểm gọi theo nhu cầu.

Một factory công bố singleton cần thiết kế sao cho:

- `getObject()` trả object dùng chung ổn định.
- Không tạo một product mới mỗi lần gọi rồi hy vọng container luôn che lỗi đó bằng cache.
- Nếu khởi tạo lazy, dùng synchronization hoặc kỹ thuật safe publication phù hợp.
- Nếu product có mutable state, việc chia sẻ cho nhiều bean/thread là chủ đích đã được cân nhắc.
- Nếu product có resource phải đóng, ownership và lifecycle phải được thiết kế rõ.

### Giá trị mặc định

Trong Spring 6.1, nếu bạn **không override `isSingleton()`**, default là `true`. Vì thế một factory trả product mới mỗi lần `getObject()` nhưng không override `isSingleton()` có thể khiến container cache sản phẩm đầu tiên và tái sử dụng nó ngoài dự kiến.

Đây là lỗi tinh vi: source code của `getObject()` nhìn như luôn `new Product()`, nhưng những nơi gọi `getBean("name")` lại thấy cùng một instance.

## 5. `isSingleton() == false`: sản phẩm không phải shared singleton

Một factory có thể cung cấp các object mới khi được yêu cầu:

~~~java
public final class NewSessionFactory implements FactoryBean<Session> {

    @Override
    public Session getObject() {
        return new Session();
    }

    @Override
    public Class<?> getObjectType() {
        return Session.class;
    }

    @Override
    public boolean isSingleton() {
        return false;
    }
}
~~~

Đây là class minh họa, cần định nghĩa `Session`.

Khi Spring nhìn thấy `isSingleton() == false`, nó không dùng cùng cơ chế cache product singleton cho factory đó. Vì vậy với implementation trả `new Session()`, mỗi lần lookup sản phẩm qua Spring sẽ nhận một object riêng.

**Nhưng điểm tinh tế theo Javadoc:** `isSingleton() == false` **không tự bảo đảm các sản phẩm là các instance độc lập**. Nó chỉ nói rằng product không phải một shared singleton có thể cache dưới contract này. Factory có thể expose object theo một **scope khác** (ví dụ đối tượng gắn với thread/request hoặc một cơ chế chia sẻ tùy biến).

Nếu semantics yêu cầu **mỗi lần lấy là một instance độc lập**, phải xét implementation của `getObject()`, cấu hình scope và interface mở rộng `SmartFactoryBean.isPrototype()` khi thích hợp. Đừng đơn giản gắn dấu bằng “false = prototype”.

### Hai minh họa đối chiếu

Một factory trả `false` và tạo object mới:

~~~java
@Override
public Product getObject() {
    return new Product();
}
~~~

Một factory cũng trả `false` nhưng chọn object từ storage theo request:

~~~java
@Override
public Product getObject() {
    return requestLocalProduct.get();
}
~~~

Hai method trên chỉ là **mã minh họa**, không phải hai method đặt vào cùng class. Trường hợp hai có thể trả cùng object trong cùng request, khác object giữa requests. `isSingleton() == false` phù hợp vì object không phải một singleton chung cho mọi lookup, nhưng không có nghĩa mỗi lời gọi trong cùng request đều độc lập. Implementation phải có context/storage hợp lệ riêng.

## 6. Phân biệt 2 trục: scope của FactoryBean và scope của product

Trong mô hình FactoryBean, phải xét **hai trục**:

1. Bean definition scope của **factory**: singleton/prototype hoặc scope khác do container quyết định.
2. Product semantics do **FactoryBean.isSingleton()** và behavior `getObject()` thể hiện.

Với một factory là singleton:

| Scope của FactoryBean | `isSingleton()` sản phẩm | Lookup theo `name` | Lookup theo `&name` |
| --- | --- | --- | --- |
| singleton | `true` | Product dùng chung/có thể cache | Cùng factory instance |
| singleton | `false` | Không cache như product singleton; kết quả phụ thuộc `getObject()` | Cùng factory instance |
| prototype | `true` | Mỗi lookup có thể tạo factory mới; **không có bảo đảm một product toàn cục** chỉ vì mỗi factory trả true | Factory instance mới mỗi lần |
| prototype | `false` | Mỗi lookup có thể tạo factory mới và sản phẩm được tạo theo factory đó | Factory instance mới mỗi lần |

**Bài học quan trọng:** Nếu muốn có một shared product thực sự, cách đơn giản và phổ biến nhất là để chính `FactoryBean` có scope singleton **và** khai báo `isSingleton() == true`, đồng thời đảm bảo `getObject()` expose cùng một reference.

Nếu factory definition là prototype nhưng `isSingleton()` trả true, mỗi factory instance có thể tạo/cung cấp sản phẩm riêng. “True” lúc này vẫn chỉ diễn tả semantics **của một factory đang được hỏi**, không tạo ra một global object dùng chung giữa các factory instances khác nhau.

### Vì sao cần hiểu độc lập hai trục?

Nếu chỉ đọc:

~~~java
@Scope("prototype")
@Component
public class ClientFactory implements FactoryBean<Client> {
    @Override
    public boolean isSingleton() {
        return true;
    }

    // ...
}
~~~

bạn có thể nhầm rằng `true` sẽ bắt Spring luôn expose cùng một client trên cả JVM. Sai: factory **prototype** được tạo mới cho từng lookup, trừ khi một nơi khác giữ và tái sử dụng một factory instance cụ thể. Mỗi factory có thể có một client riêng.

Đoạn class trên là minh họa, không biên dịch độc lập do còn thiếu `getObject()`, `getObjectType()` và các imports cần thiết.

## 7. Ví dụ hoàn chỉnh Java 17 + Spring Context 6.1

Ví dụ sau tạo hai `FactoryBean` singleton:

- `SharedProductFactory`: luôn expose cùng product, `isSingleton() == true`.
- `FreshProductFactory`: tạo product mới mỗi `getObject()`, `isSingleton() == false`.

Sau đó kiểm tra object identity, factory identity, số lần thực hiện `getObject()` và kết quả `context.isSingleton(...)`.

### 7.1. Cấu trúc

~~~text
factorybean-product-demo/
├── pom.xml
└── src/main/java/com/example/factory/FactoryBeanProductDemo.java
~~~

### 7.2. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>factorybean-product-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.factory.FactoryBeanProductDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. File `FactoryBeanProductDemo.java`

~~~java
package com.example.factory;

import org.springframework.beans.factory.FactoryBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class FactoryBeanProductDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            Product shared1 = context.getBean("sharedProduct", Product.class);
            Product shared2 = context.getBean("sharedProduct", Product.class);

            Product fresh1 = context.getBean("freshProduct", Product.class);
            Product fresh2 = context.getBean("freshProduct", Product.class);

            SharedProductFactory sharedFactory =
                    context.getBean("&sharedProduct", SharedProductFactory.class);
            FreshProductFactory freshFactory =
                    context.getBean("&freshProduct", FreshProductFactory.class);

            System.out.println("shared references equal: " + (shared1 == shared2));
            System.out.println("fresh references equal: " + (fresh1 == fresh2));
            System.out.println("shared product value: " + shared1.value());
            System.out.println("fresh product values: "
                    + fresh1.value() + ", " + fresh2.value());

            System.out.println("shared getObject calls: " + sharedFactory.calls());
            System.out.println("fresh getObject calls: " + freshFactory.calls());

            System.out.println("shared product isSingleton: "
                    + context.isSingleton("sharedProduct"));
            System.out.println("fresh product isSingleton: "
                    + context.isSingleton("freshProduct"));
            System.out.println("fresh factory isSingleton: "
                    + context.isSingleton("&freshProduct"));

            System.out.println("same fresh factory: "
                    + (freshFactory == context.getBean("&freshProduct")));
        }
    }

    public record Product(String value) {}

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean(name = "sharedProduct")
        public SharedProductFactory sharedProduct() {
            return new SharedProductFactory();
        }

        @Bean(name = "freshProduct")
        public FreshProductFactory freshProduct() {
            return new FreshProductFactory();
        }
    }

    public static class SharedProductFactory implements FactoryBean<Product> {
        private final Product shared = new Product("shared");
        private int calls;

        @Override
        public Product getObject() {
            calls++;
            return shared;
        }

        @Override
        public Class<?> getObjectType() {
            return Product.class;
        }

        @Override
        public boolean isSingleton() {
            return true;
        }

        public int calls() {
            return calls;
        }
    }

    public static class FreshProductFactory implements FactoryBean<Product> {
        private int calls;

        @Override
        public Product getObject() {
            calls++;
            return new Product("fresh-" + calls);
        }

        @Override
        public Class<?> getObjectType() {
            return Product.class;
        }

        @Override
        public boolean isSingleton() {
            return false;
        }

        public int calls() {
            return calls;
        }
    }
}
~~~

Mã dùng Java 17 `record Product`, không dùng database, network hoặc thread tự tạo. Hai factory class là `static` nested classes và được đăng ký bằng `@Bean`. Không cần component scanning vì `AnnotationConfigApplicationContext(Config.class)` trực tiếp nạp class cấu hình.

Các biến `calls` là counter đơn giản, phù hợp **chỉ để minh họa single-thread**. Nếu muốn dùng factory trong môi trường concurrent, thiết kế initialization/counter/ghi tài nguyên với thread-safety phù hợp, ví dụ `AtomicInteger` hoặc synchronization.

### 7.4. Chạy

Tại thư mục chứa `pom.xml`, dùng JDK 17+ và Maven 3.9+:

~~~bash
mvn -q compile exec:java
~~~

Các dòng `System.out.println` mà ứng dụng chủ động in với Spring Context 6.1.13:

~~~text
shared references equal: true
fresh references equal: false
shared product value: shared
fresh product values: fresh-1, fresh-2
shared getObject calls: 1
fresh getObject calls: 2
shared product isSingleton: true
fresh product isSingleton: false
fresh factory isSingleton: true
same fresh factory: true
~~~

Maven và logging framework có thể in thêm thông tin; đây chỉ là stdout của code ví dụ. Kết quả mô tả cơ chế cache chuẩn đối với singleton FactoryBean sau hai lần lookup sản phẩm, không tuyên bố rằng mọi framework, scope hay đường type-query đều gọi `getObject()` đúng một lần trong mọi tình huống.

### 7.5. Phân tích kết quả

**`shared references equal: true`**: cả hai lookup `sharedProduct` nhận cùng Product reference. Factory báo `isSingleton() == true` và trả cùng `shared` object.

**`shared getObject calls: 1`**: trong đường chạy minh họa, container cache sản phẩm sau lần lookup đầu; lần hai lấy từ cache. Lưu ý điều kiện factory bean itself singleton.

**`fresh references equal: false`**: `FreshProductFactory` báo `false` nên sản phẩm không dùng cache singleton; method mỗi lần trả `new Product(...)`.

**`fresh getObject calls: 2`**: hai lần lookup product kích hoạt hai lần gọi `getObject()`. Cùng factory instance có thể tạo nhiều sản phẩm.

**`fresh factory isSingleton: true`**: bản thân `FreshProductFactory` được khai báo bởi một `@Bean` singleton mặc định. Điều này **không mâu thuẫn** với product `freshProduct` báo non-singleton.

**`same fresh factory: true`**: lấy `&freshProduct` hai lần trả cùng factory object; dấu `&` không tạo mới factory.

Đây là ví dụ rõ nhất cho công thức:

> **Một FactoryBean singleton vẫn có thể cung cấp một sản phẩm mới cho mỗi lần lookup sản phẩm.**

## 8. Dùng `BeanFactory.isSingleton(name)` và `isPrototype(name)`

Khi truy vấn trạng thái qua container, nhớ truyền đúng tên:

~~~java
context.isSingleton("sharedProduct");  // true  — sản phẩm shared.
context.isSingleton("freshProduct");   // false — sản phẩm non-singleton.
context.isSingleton("&freshProduct");  // true  — factory singleton.
~~~

Đoạn này có thể đặt trong `main` của ví dụ ở mục 7.

`BeanFactory.isSingleton(String name)` nói rằng `getBean(name)` có trả **same shared singleton instance** hay không. Nó xem semantics của **object được lookup theo tên**, bao gồm trường hợp tên trỏ tới FactoryBean product.

`BeanFactory.isPrototype(String name)` kiểm tra semantics nhận **independent instances**. Theo Javadoc, kết quả `isSingleton(name) == false` không chứng minh `isPrototype(name) == true` trong mọi trường hợp: một scoped object có thể là neither singleton nor prototype.

Với plain `FactoryBean` không implement `SmartFactoryBean`, Spring có thể xem `isSingleton() == false` như tín hiệu sản phẩm prototype khi trả lời `isPrototype(name)` (theo hợp đồng được tài liệu hóa), **nhưng bản thân implementation phải bảo đảm semantics nó cam kết**. Nếu factory dùng một scope tùy chỉnh và không trả independent instances, hãy xem kỹ metadata để tránh đánh lừa container và phía sử dụng.

### Đừng nhầm với `FactoryBean.isSingleton()` của factory instance

~~~java
FreshProductFactory f =
    context.getBean("&freshProduct", FreshProductFactory.class);

System.out.println(f.isSingleton());                   // false
System.out.println(context.isSingleton("&freshProduct")); // true
~~~

Hai giá trị khác nhau là **đúng**, không phải bug:

- `f.isSingleton()` hỏi **product**.
- `context.isSingleton("&freshProduct")` hỏi **factory object**.

## 9. `SmartFactoryBean.isPrototype()`: khi cần xác nhận instance độc lập

Spring có interface mở rộng `org.springframework.beans.factory.SmartFactoryBean<T>` bổ sung metadata như:

- `isPrototype()`: trả `true` khi `getObject()` luôn cung cấp **independent instance**.
- `isEagerInit()`: gợi ý factory và singleton product cần được khởi tạo sớm.

`SmartFactoryBean.isPrototype()` **không phải phủ định đơn giản** của `FactoryBean.isSingleton()`.

Ví dụ những semantics cần phân biệt:

| Sản phẩm | `isSingleton()` | `SmartFactoryBean.isPrototype()` |
| --- | --- | --- |
| Một object shared cố định | `true` | `false` |
| Một object mới, độc lập cho mỗi lookup | `false` | `true` |
| Object dùng chung trong phạm vi request/session, khác ngoài phạm vi đó | `false` | `false` |

Bảng minh họa quan hệ hợp đồng; một factory tùy biến phải tự triển khai consistent với behavior thực.

Method `SmartFactoryBean.isPrototype()` mặc định trả `false`, vì không thể suy ra product là independent instance chỉ từ việc nó không phải singleton. Nếu implementation bảo đảm mới và độc lập mỗi lần, có thể override `true`.

Cẩn thận: `SmartFactoryBean` dành cho **metadata hạ tầng khi thực sự cần**. Đối với một factory đơn giản trả một object dùng chung, plain `FactoryBean` đã đủ.

### Minh họa `SmartFactoryBean`

~~~java
import org.springframework.beans.factory.SmartFactoryBean;

public class TaskFactory implements SmartFactoryBean<Task> {
    @Override
    public Task getObject() {
        return new Task();
    }

    @Override
    public Class<?> getObjectType() {
        return Task.class;
    }

    @Override
    public boolean isSingleton() {
        return false;
    }

    @Override
    public boolean isPrototype() {
        return true;
    }
}
~~~

Đây là class minh họa cần định nghĩa `Task` và đăng ký `TaskFactory` thành bean. Nó công bố rõ ràng từng `getObject()` tạo một target độc lập. Không đưa `true` vào `isPrototype()` khi method thực tế trả một object theo request/thread scope.

## 10. `isSingleton` liên hệ thế nào với caching?

Mô hình đơn giản hóa:

~~~text
getBean("productName")
        |
        v
Container tìm FactoryBean instance
        |
        +--> FactoryBean bean definition có scope gì?
        |       |
        |       +-- singleton: có thể giữ một factory instance
        |       '-- prototype: có thể tạo factory instance mới
        |
        v
Container kiểm tra product metadata
        |
        +-- isSingleton() = true và factory phù hợp cho cache
        |       |
        |       +-- product cache đã có -> dùng lại cached product
        |       '-- chưa có -> gọi getObject(), xử lý/có thể cache
        |
        '-- isSingleton() = false
                |
                '-- gọi getObject() để lấy product theo factory
~~~

Sơ đồ thể hiện **hướng tư duy**, không phải sao chép một-một implementation nội bộ. Cache thực tế có điều kiện theo bean factory và bean definition; lifecycle/proxy/type-check có thể thêm bước.

Điều cần ghi nhớ:

1. Product caching được quyết định chủ yếu dựa trên metadata singleton **của product** và trạng thái factory bean trong container.
2. FactoryBean bean definition vẫn có scope riêng.
3. `getObject()` nên thực hiện đúng hợp đồng, không đặt tất cả tính đúng đắn vào giả định cache luôn giữ mọi thứ.
4. `getObjectType()` nên mô tả product type mà không bắt buộc sinh product chỉ để xác định type.

### Sai: khai báo true nhưng cứ tạo mới

~~~java
@Override
public Product getObject() {
    return new Product("new");
}

@Override
public boolean isSingleton() {
    return true;
}
~~~

Đây là code anti-pattern nếu contract dự kiến “mỗi lần direct `getObject()` đều mới”: factory **nói với Spring rằng product là một reference ổn định**, trong khi implementation lại trả object mới. Tùy container/cache, gọi `context.getBean` có thể che tình trạng không nhất quán; tự gọi `factory.getObject()` sẽ thấy thay đổi reference.

Sửa một trong hai hướng:

- **Thực sự muốn singleton:** lưu và trả cùng product reference.
- **Thực sự muốn non-singleton:** trả `false`; với sản phẩm độc lập, triển khai `getObject()` tạo object mới, cân nhắc `SmartFactoryBean.isPrototype()` khi cần.

## 11. FactoryBean singleton không đồng nghĩa sản phẩm thread-safe

Nếu `isSingleton() == true`, nhiều nơi có thể chia sẻ cùng product object.

~~~java
public final class CounterClient {
    private int total;

    public void increment() {
        total++;
    }

    public int getTotal() {
        return total;
    }
}
~~~

Đây là class Java minh họa. Nếu `CounterClient` được FactoryBean expose như product singleton cho nhiều threads, `total++` **không phải thao tác atomic**; race condition có thể xảy ra.

Khắc phục phải dựa vào contract nghiệp vụ: thiết kế sản phẩm immutable, dùng synchronization/atomics hoặc chuyển mutable request state sang object mới theo mỗi công việc. `isSingleton() == true` chỉ là lời công bố về **identity/chia sẻ**, không cung cấp thread-safety.

Ngược lại, `isSingleton() == false` không tự làm product thread-safe nếu factory vẫn trả một object mutable dùng chung trong một scope khác.

## 12. Injection của product vào singleton: tại sao lấy non-singleton một lần vẫn bị giữ lâu?

Giả sử một service singleton inject product do `FreshProductFactory` tạo:

~~~java
@Service
public class JobService {
    private final Product product;

    public JobService(@Qualifier("freshProduct") Product product) {
        this.product = product;
    }

    public String name() {
        return product.value();
    }
}
~~~

Đoạn này là class minh họa cần import `Service`, `Qualifier` và kiểu `Product`.

Ngay cả khi `FreshProductFactory.isSingleton() == false`, constructor injection của singleton vẫn xảy ra **khi JobService được tạo**. Một product được resolve và lưu trong field. Gọi `name()` 100 lần chỉ đọc lại cùng reference đó.

Điều này tương tự prototype injected into singleton: **scope/FactoryBean product metadata điều khiển mỗi lần container được hỏi**, không tự thay giá trị field Java sau mỗi method invocation.

Nếu mỗi job phải có product mới, inject provider có qualifier:

~~~java
@Service
public class JobService {
    private final ObjectProvider<Product> products;

    public JobService(
            @Qualifier("freshProduct") ObjectProvider<Product> products) {
        this.products = products;
    }

    public String runJob() {
        Product product = products.getObject();
        return product.value();
    }
}
~~~

Đây là **phiên bản class thay thế**, cần import `ObjectProvider`, `Service` và `Qualifier`. Với cấu hình từ ví dụ chạy được, mỗi `runJob()` yêu cầu một fresh product. Nếu product sở hữu resource, caller cần cleanup theo lifetime của chính job.

## 13. Eager/lazy product không phải cùng câu hỏi với singleton

Có ba câu hỏi độc lập:

1. **Đối tượng nào?** — `getObject()` trả product gì?
2. **Có chia sẻ không?** — `isSingleton()` cho biết contract shared product.
3. **Khi nào tạo?** — container/factory quyết định eager hoặc lazy creation, có thể liên quan `SmartFactoryBean.isEagerInit()`.

Thông thường, một FactoryBean singleton được tạo cùng non-lazy singleton beans nhưng **product `getObject()` không bắt buộc tạo eager** chỉ vì `isSingleton() == true`. Một `SmartFactoryBean` có thể thể hiện mong muốn eager initialization bằng `isEagerInit()`.

Không đồng nhất:

- `isSingleton() == true` với “product chắc chắn đã được tạo khi context refresh xong”.
- `@Lazy` với “sản phẩm sẽ không bao giờ chia sẻ”.
- `isEagerInit() == true` với “mọi lần `getObject()` phải tạo mới”.

Những điều đó thuộc **hai trục lifecycle khác nhau**: thời điểm tạo và mức độ chia sẻ.

## 14. `getObjectType()` ảnh hưởng autowiring và tìm bean như thế nào?

Khi Spring tìm các bean có type `Product`, nó cần biết FactoryBean nào có khả năng expose `Product`. `getObjectType()` là nguồn metadata quan trọng.

~~~java
@Override
public Class<?> getObjectType() {
    return Product.class;
}
~~~

**Nên trả một type đủ chính xác khi có thể**, không tạo product chỉ để tìm type. Method có thể được gọi khi factory chưa hoàn tất initialization, vì vậy đừng dựa vào state chỉ có sau init callback một cách không an toàn.

Nếu `getObjectType()` trả `null` khi có thể biết type, autowiring theo type hoặc `getBeansOfType` có thể không tìm thấy factory product tương ứng. Nhưng tự gọi `getObject()` từ `getObjectType()` để “dò type” lại có thể kích hoạt I/O hoặc side effect bất ngờ.

Một implementation tốt:

~~~java
public final class HttpClientFactory implements FactoryBean<HttpClient> {
    @Override
    public Class<?> getObjectType() {
        return HttpClient.class;
    }
    // getObject() và isSingleton() triển khai riêng.
}
~~~

Đây là class skeleton minh họa không hoàn chỉnh; cần định nghĩa `HttpClient`, import `FactoryBean` và implement `getObject()`.

## 15. Những điều cần lưu ý về vòng đời sản phẩm

Một `FactoryBean` là bean do Spring quản lý. Product do `getObject()` expose đi qua cơ chế xử lý riêng của Spring; **đừng mặc định mọi callback init/destroy của product giống hệt một bean definition độc lập được Spring trực tiếp tạo**.

Ví dụ, factory có thể mở network connection rồi tạo một proxy client. Nếu product là singleton và nắm giữ connection/pool:

- Xác định resource do **factory** hay **product** sở hữu.
- Nếu factory chịu trách nhiệm, đặt cleanup ở lifecycle của factory bean (và bảo đảm factory được Spring quản lý).
- Nếu product có contract `AutoCloseable`, cân nhắc ai gọi `close()` và vào thời điểm nào.
- Đừng trông chờ chỉ `isSingleton() == true` tự động gọi đúng mọi destruction callback của một object được trả từ `getObject()`.
- Nếu product non-singleton hoặc prototype-style, bên nhận mỗi product cần xác định rõ cleanup theo một đơn vị công việc.

**`isSingleton()` không phải lifecycle destroy configuration.** Nó không thay `@PreDestroy`, `DisposableBean.destroy()`, `@Bean(destroyMethod = "...")` hoặc ownership của `AutoCloseable`.

Với đối tượng chỉ chứa dữ liệu thuần Java, không cần callback hủy đặc biệt. Với socket/file handle/client cần đóng, phải thiết kế trách nhiệm đóng độc lập với việc Spring cache identity.

## 16. FactoryBean và `@Bean`: một kiểu code rất dễ hiểu nhầm

Đoạn:

~~~java
@Configuration
class Config {
    @Bean
    public Product product() {
        return new Product("x");
    }
}
~~~

có nghĩa Spring bean definition là một **Product thông thường**. Method `product()` là **factory method Java của cấu hình**, nhưng object trả về không implement `FactoryBean`. Scope mặc định của product bean là singleton, do bean definition của `@Bean` quyết định.

Trong khi đó:

~~~java
@Configuration
class Config {
    @Bean
    public FactoryBean<Product> product() {
        return new SharedProductFactory();
    }
}
~~~

Spring đăng ký một **FactoryBean** dưới tên `product`. Lookup thông thường theo tên `product` expose một `Product`; lookup `&product` expose factory. Đây là hai cấu hình **thay thế**, không để cùng class/method name trong một file. Code cần định nghĩa `Product`, `SharedProductFactory` và các imports tương ứng.

Chỉ trong trường hợp thứ hai mới có ý nghĩa của `FactoryBean.isSingleton()` đối với product. Đừng gọi method `isSingleton()` của FactoryBean trong ví dụ thứ nhất vì không có FactoryBean instance nào.

## 17. Khi nào nên dùng `FactoryBean` thay vì `@Bean` thông thường?

`FactoryBean` thường thích hợp cho **framework/infrastructure integration**:

- Product được tạo bởi một quy trình không đơn giản như gọi constructor.
- Cần expose một proxy từ một factory phức tạp.
- Cần metadata `getObjectType()`, singleton/prototype/eager semantics riêng cho product.
- Muốn giữ factory như một bean hạ tầng, trong khi người dùng inject product như bean thông thường.

Nếu chỉ cần tạo một client singleton:

~~~java
@Bean(destroyMethod = "close")
public MyClient myClient(ClientOptions options) {
    return new MyClient(options);
}
~~~

thì `@Bean` trực tiếp thường đủ. Không cần viết `FactoryBean<MyClient>` chỉ để gọi constructor hoặc cấu hình vài properties. Đoạn này minh họa cần định nghĩa `MyClient`, `ClientOptions` và phương thức `close()`.

Nếu chỉ cần prototype thuần Java:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public WorkState workState() {
    return new WorkState();
}
~~~

cũng có thể đơn giản hơn tự viết một FactoryBean. Đây là đoạn minh họa cần các imports/kiểu tương ứng.

## 18. Các trường hợp dễ sai

| Biểu hiện | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `getObject()` có `new` nhưng lookup luôn cùng object | `isSingleton()` mặc định true; product được cache | Override false nếu thực sự cần non-singleton |
| `getBean("name")` trả Product chứ không phải FactoryBean | Đây là contract `FactoryBean` | Dùng `getBean("&name")` để lấy factory |
| `context.isSingleton("&name")` true, `factory.isSingleton()` false | Cái trước hỏi factory; cái sau hỏi product | Phân biệt hai trục |
| Hai lần `getBean("name")` tạo factory mới dù product isSingleton true | Factory bean definition có thể đang là prototype | Kiểm tra factory scope |
| `isSingleton() == false` nhưng hai lookup vẫn cùng reference | Factory trả object theo shared/custom scope | Đọc `getObject()`, dùng `SmartFactoryBean.isPrototype()` nếu cần independent instances |
| `isPrototype("name")` không như mong đợi | Metadata `SmartFactoryBean` hoặc scope khác prototype | Đọc Javadoc và actual factory behavior |
| Sản phẩm không được autowire theo type | `getObjectType()` không đúng hoặc trả null | Trả type đáng tin cậy, tránh side effects |
| Product singleton có race condition | Nhiều threads chia sẻ cùng mutable instance | Thiết kế immutable/thread-safe, hoặc dùng object per operation |
| Singleton service giữ một non-singleton product mãi | Constructor injection resolve một lần | Dùng `ObjectProvider<Product>` đúng chỗ |
| Không thấy product được tạo khi startup | Product có thể lazy dù factory singleton | Xem `SmartFactoryBean.isEagerInit()` và nơi lookup |
| Resource không được đóng | Nhầm caching với lifecycle destroy | Xác định ownership và cleanup |
| Factory proxy bị cấu hình `isSingleton` sai | Khai báo không khớp reference thực trả | Đồng nhất contract với `getObject()` |

### Checklist chẩn đoán

1. Bean dưới tên đó có thực sự implements `FactoryBean` không?
2. `getBean("name")` và `getBean("&name")` đang trả object nào?
3. Factory bean definition đang singleton hay prototype?
4. `FactoryBean.isSingleton()` đang trả true/false theo product?
5. `getObject()` có tạo mới, trả field cached, hay lookup theo một scope khác?
6. `getObjectType()` có phản ánh type thật của product không?
7. Có `SmartFactoryBean` và `isPrototype()`/ `isEagerInit()` không?
8. Có singleton consumer đang giữ một non-singleton product trong field không?
9. Product có mutable state hoặc tài nguyên cần cleanup không?
10. Test có xác minh identity bằng `==` và kiểm tra số lần gọi `getObject()` chưa?

## 19. Unit test và integration test nào có giá trị?

### 19.1. Test trực tiếp hợp đồng factory

Với `SharedProductFactory` ở mục 7:

~~~java
var factory = new FactoryBeanProductDemo.SharedProductFactory();
var a = factory.getObject();
var b = factory.getObject();

if (!factory.isSingleton() || a != b) {
    throw new AssertionError("Shared FactoryBean contract violated");
}
~~~

Với `FreshProductFactory`:

~~~java
var factory = new FactoryBeanProductDemo.FreshProductFactory();
var a = factory.getObject();
var b = factory.getObject();

if (factory.isSingleton() || a == b) {
    throw new AssertionError("Fresh FactoryBean contract violated");
}
~~~

Đây là các đoạn mã có thể đặt trong Java test/main với source từ mục 7. Chúng kiểm tra **implementation getObject()** nhất quán với metadata khai báo, không kiểm tra Spring caching.

### 19.2. Integration test phải dùng Spring context thật

Một test giá trị hơn về hành vi Spring:

~~~java
try (var ctx = new AnnotationConfigApplicationContext(
        FactoryBeanProductDemo.Config.class)) {

    Object shared1 = ctx.getBean("sharedProduct");
    Object shared2 = ctx.getBean("sharedProduct");

    Object fresh1 = ctx.getBean("freshProduct");
    Object fresh2 = ctx.getBean("freshProduct");

    if (shared1 != shared2 || fresh1 == fresh2) {
        throw new AssertionError("Product lookup semantics wrong");
    }

    if (!ctx.isSingleton("&freshProduct")
            || ctx.isSingleton("freshProduct")) {
        throw new AssertionError("Factory/product metadata wrong");
    }
}
~~~

Đoạn này yêu cầu import `AnnotationConfigApplicationContext` và class ví dụ mục 7. Không cần JUnit để kiểm tra, nhưng trong project production nên dùng JUnit assertions và integration test context.

Đừng test chỉ bằng `equals()` nếu mục tiêu là **same object reference**. Hai object có dữ liệu giống nhau vẫn có thể `equals()` trả true. Dùng `==` để kiểm tra identity hoặc một cơ chế kiểm chứng unique instance hợp lệ.

### 19.3. Test concurrent khi factory có lazy singleton

Nếu factory tự lazy-create product trong `getObject()`, cần kiểm tra khi nhiều threads gọi đồng thời có bị tạo nhiều product hoặc publish chưa đủ state không. Test có thể dùng barrier/latch để kích hoạt requests cùng lúc và xác nhận identity, nhưng không dựa vào test timing ngẫu nhiên là bằng chứng duy nhất. Thiết kế thread-safe của factory mới là bảo đảm cuối cùng.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** `FactoryBean.isSingleton()` trả `true` có nghĩa bản thân FactoryBean chắc chắn là singleton không?

**Đáp án:** Không. Nó mô tả object **sản phẩm** được expose bởi `getObject()`. Bean definition của chính factory có scope riêng.

**Câu 2.** Một FactoryBean singleton có `isSingleton() == false`, mỗi lần `getObject()` trả `new Product()`. Hai lần `getBean("name")` thông thường như thế nào?

**Đáp án:** Hai product instances khác nhau, vì container không cache chúng như product singleton và factory thực sự tạo mới mỗi lần. Cùng một factory instance có thể được tái sử dụng.

**Câu 3.** Nếu không override `FactoryBean.isSingleton()` trong Spring 6.1 thì default là gì?

**Đáp án:** `true`. Nếu muốn non-singleton product, phải khai báo metadata đúng và đảm bảo hành vi `getObject()` phù hợp.

**Câu 4.** Vì sao `isSingleton() == false` không đủ để khẳng định product là prototype?

**Đáp án:** Non-singleton có thể là object thuộc custom/request scope hoặc chia sẻ theo ranh giới khác, không nhất thiết independent với mọi lần lookup. `SmartFactoryBean.isPrototype()` biểu đạt rõ semantics independent instance.

**Câu 5.** `getBean("&myFactory")` dùng làm gì?

**Đáp án:** Lấy **FactoryBean object** thay vì sản phẩm do `getObject()` tạo. Dấu `&` là prefix dereference của Spring.

**Câu 6.** Một FactoryBean prototype trả `isSingleton() == true` có tạo một singleton product toàn JVM không?

**Đáp án:** Không bảo đảm. Mỗi lần lấy factory theo scope prototype có thể tạo factory instance mới; lời công bố singleton product chỉ thuộc contract của factory instance tương ứng.

**Câu 7.** Singleton service inject một fresh product từ FactoryBean non-singleton qua constructor. Mỗi lần gọi service có product mới không?

**Đáp án:** Không. Constructor injection resolve một dependency khi service được tạo; field giữ tham chiếu. Dùng `ObjectProvider`/lookup per operation nếu nghiệp vụ cần mới.

**Câu 8.** `getObjectType()` nên gọi `getObject()` để tìm type không?

**Đáp án:** Nói chung không. Type metadata nên được cung cấp đáng tin cậy mà không cần tạo sản phẩm hoặc tạo side effect trước thời điểm lookup thực tế.

**Câu 9.** `isSingleton() == true` có làm product thread-safe và tự hủy resource không?

**Đáp án:** Không. Nó chỉ mô tả product có được chia sẻ/có thể cache hay không. Concurrency safety và cleanup cần được thiết kế riêng.

## 21. Tóm tắt áp dụng

Khi đọc một `FactoryBean<T>`, hãy hỏi theo đúng thứ tự:

1. **Factory đang được Spring quản lý với scope nào?**
2. **`getObject()` thực sự trả reference như thế nào?**
3. **`isSingleton()` có phù hợp với behavior đó không?**
4. **Nếu trả false, product có thật sự là independent prototype hay theo một scope khác?**
5. **Caller lấy product bằng `name` hay lấy factory bằng `&name`?**
6. **Product có state/resource cần được bảo vệ hoặc cleanup không?**

Quy tắc dễ nhớ:

> **`FactoryBean.isSingleton()` nói về sản phẩm, không nói về chính factory. `true` nghĩa có thể chia sẻ/cache; `false` nghĩa không công bố shared singleton, nhưng không tự bảo đảm một prototype độc lập mỗi lần gọi.**

Đối với ứng dụng nghiệp vụ thông thường, nếu chỉ cần tạo singleton hoặc prototype đơn giản, `@Bean` kết hợp `@Scope` có thể trực tiếp và dễ đọc hơn. Chỉ dùng `FactoryBean` khi có yêu cầu tạo/expose product ở mức tích hợp container.

## 22. Tài liệu tham khảo chính thức

- [Spring Framework Reference — Container Extension Points: FactoryBean](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): `getObject()`, `getObjectType()`, `isSingleton()` và lookup `&name`.
- [FactoryBean Javadoc — Spring Framework 6.1.12](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/beans/factory/FactoryBean.html): contract quan trọng nhất, default `isSingleton() == true`, cảnh báo `false` không đồng nghĩa independent instances.
- [SmartFactoryBean Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/SmartFactoryBean.html): `isPrototype()` và `isEagerInit()`.
- [BeanFactory Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/beans/factory/BeanFactory.html): `isSingleton(name)`, `isPrototype(name)`, `getBean(name)` và factory dereference.
- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton/prototype và thời điểm container cấp dependencies.
