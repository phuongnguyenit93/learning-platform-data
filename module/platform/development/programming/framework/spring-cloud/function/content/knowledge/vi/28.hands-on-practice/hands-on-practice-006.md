# Tách và kết hợp nhiều luồng bằng Reactor Tuple

## 1. Bài toán thực hành

Trong **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), logic nghiệp vụ được khai báo thành `Supplier`, `Function` hoặc `Consumer` và được quản lý bởi `FunctionCatalog`. Với ứng dụng xử lý sự kiện, một hàm đôi khi cần đọc **nhiều luồng dữ liệu cùng lúc** hoặc phát **nhiều luồng đầu ra**. Spring Cloud Function sử dụng **Reactor Tuple** để biểu diễn số lượng và kiểu của từng luồng, còn Project Reactor cung cấp các toán tử để kết hợp hoặc tách các publisher.

Ta sẽ xây dựng một ứng dụng xử lý sự kiện với ba bài toán:

1. **Kết hợp hai nguồn:** nhận luồng thông báo đơn hàng và luồng thông báo khách hàng, thêm nhãn rồi hợp nhất thành một luồng sự kiện chung.
2. **Ghép cặp hai luồng:** nhận luồng số lượng và luồng đơn giá, ghép các phần tử tương ứng để tính giá trị dòng hàng.
3. **Tách một luồng:** nhận các số nguyên, phân loại số chẵn và số lẻ thành hai luồng đầu ra độc lập.

~~~text
NHIỀU INPUT

orders: Flux<String> -----\
                           +--> Tuple2<Flux<String>, Flux<String>>
customers: Flux<String> --/                 |
                                            v
                                       mergeLabels
                                            |
                                            v
                                  Flux<String> merged


MỘT INPUT, NHIỀU OUTPUT

numbers: Flux<Integer>
          |
          v
      splitParity
          |
          v
Tuple2<Flux<String>, Flux<String>>
          |                 |
          v                 v
      even stream       odd stream
          |                 |
          v                 v
    even-events        odd-events
~~~

**Mục tiêu:** hiểu chữ ký `TupleN<Flux<...>>`, dùng `Tuples.of(...)`, chọn đúng toán tử Reactor (`merge`, `zip`, `concat`, `combineLatest`), kiểm thử bằng `StepVerifier` và cấu hình nhiều binding của Spring Cloud Stream.

Sau bài này, bạn có thể:

- Phân biệt một tuple chứa nhiều publisher với một publisher chứa các tuple.
- Khai báo reactive function có hai hoặc ba input stream.
- Khai báo reactive function tạo hai output stream.
- Hiểu chỉ số `-in-0`, `-in-1`, `-out-0` và `-out-1`.
- Chọn phép hợp nhất hoặc ghép cặp theo ngữ nghĩa dữ liệu.
- Kiểm thử bằng `StepVerifier` và `FunctionCatalog`.
- Nhận biết giới hạn của subscription, backpressure, cancellation và lỗi khi có nhiều nhánh.

> **Điều kiện quan trọng:** hỗ trợ function arity (nhiều input/output) của Spring Cloud Function hướng tới **reactive functions** có chữ ký dạng `Function<TupleN<Flux<?>...>, TupleN<Flux<?>...>>`. Không hiểu tuple này như một cách khai báo nhiều tham số Java thông thường cho hàm imperative `Function<A,B>`.

## 2. Reactor Tuple biểu diễn điều gì?

Project Reactor cung cấp các kiểu `Tuple2`, `Tuple3`... cùng factory `Tuples.of(...)`. Tuple có **arity** (số phần tử) và **kiểu tĩnh** cho từng vị trí.

Ví dụ:

~~~java
Tuple2<Flux<String>, Flux<Integer>> inputs =
        Tuples.of(
                Flux.just("order-A", "order-B"),
                Flux.just(10, 20));
~~~

Tuple trên chứa:

- `getT1()`: một `Flux<String>`.
- `getT2()`: một `Flux<Integer>`.

Nó không có nghĩa là một `Flux` phát ra một cặp `String` và `Integer` tại mỗi lần `onNext`.

### 2.1. Phân biệt hai kiểu dễ nhầm

| Kiểu | Ý nghĩa |
| --- | --- |
| `Tuple2<Flux<A>, Flux<B>>` | Một tuple chứa **hai publisher độc lập**; mỗi publisher có thể phát nhiều phần tử |
| `Flux<Tuple2<A, B>>` | **Một publisher** phát các cặp `(A, B)` |
| `Tuple2<A, B>` | Một cặp giá trị đơn, không phải hai stream |
| `Flux<A>` | Một stream của các phần tử A |

~~~text
Tuple2<Flux<A>, Flux<B>>
   +--------------------+
   | Flux<A>: A1, A2... |
   | Flux<B>: B1, B2... |
   +--------------------+

Flux<Tuple2<A, B>>
   +--------------------+
   | (A1, B1)           |
   | (A2, B2)           |
   | (A3, B3)           |
   +--------------------+
~~~

Hai hợp đồng này khác nhau về cách subscribe, ghép dữ liệu và số binding. Chọn kiểu theo bài toán: nhiều nguồn độc lập dùng tuple chứa publisher; một nguồn đã phát các cặp dùng `Flux<Tuple2<A,B>>`.

### 2.2. Tuple2, Tuple3 và số lượng stream

Ví dụ hai nguồn:

~~~java
Function<Tuple2<Flux<String>, Flux<Integer>>, Flux<String>>
~~~

Ví dụ ba nguồn:

~~~java
Function<
    Tuple3<Flux<OrderEvent>, Flux<PaymentEvent>, Flux<CustomerEvent>>,
    Flux<String>
>
~~~

Với `Tuple3`, truy cập bằng `getT1()`, `getT2()` và `getT3()`. Số phần tử trong tuple cho framework biết **có bao nhiêu input/output binding** cần tạo; generic của từng vị trí cung cấp thông tin kiểu để chuyển đổi payload.

Không nên thay tuple bằng `List<Flux<?>>` hoặc `Object[]` chỉ để giảm số kiểu khai báo. Những kiểu đó làm mất arity và thông tin kiểu cụ thể mà framework cần.

## 3. Chọn toán tử để kết hợp các luồng

Reactor có nhiều cách phối hợp publisher. Chúng không thể thay thế cho nhau.

| Toán tử | Hành vi | Dùng khi |
| --- | --- | --- |
| `Flux.merge(a, b)` | Phát phần tử từ các nguồn theo thời điểm chúng đến; thứ tự tương đối giữa nguồn có thể xen kẽ | Gộp các event độc lập thành một luồng |
| `Flux.concat(a, b)` | Đợi A hoàn tất rồi mới subscribe/phát B | Cần xử lý tuần tự từng nguồn |
| `Flux.zip(a, b)` | Ghép phần tử thứ n của A với phần tử thứ n của B | Hai nguồn có quan hệ theo vị trí/thứ tự |
| `a.zipWith(b)` | Dạng instance của zip | Cần ghép cặp hai publisher |
| `Flux.combineLatest(a, b, fn)` | Sau khi mỗi nguồn đã phát ít nhất một phần tử, kết hợp giá trị mới nhất của mỗi nguồn khi có cập nhật | Dữ liệu dạng snapshot/trạng thái mới nhất |

### 3.1. merge không ghép cặp

~~~java
Flux<String> orders = Flux.just("O-1", "O-2");
Flux<String> customers = Flux.just("C-1", "C-2");

Flux<String> merged = Flux.merge(
        orders.map(value -> "ORDER:" + value),
        customers.map(value -> "CUSTOMER:" + value));
~~~

Output có bốn phần tử, nhưng thứ tự xen kẽ giữa hai nguồn phụ thuộc lịch phát. `merge` không khẳng định `O-1` đi cùng `C-1`.

### 3.2. zip ghép theo vị trí

~~~java
Flux<String> skus = Flux.just("PEN", "BOOK");
Flux<Integer> quantities = Flux.just(2, 3);

Flux<String> lines = Flux.zip(
        skus,
        quantities,
        (sku, quantity) -> sku + ":" + quantity);
~~~

Output:

~~~text
PEN:2
BOOK:3
~~~

`zip` chờ một phần tử từ mỗi nguồn để tạo một cặp. Khi một nguồn hoàn tất, publisher zip thường hoàn tất và không tạo thêm cặp. Nếu hai stream có tốc độ hoặc số phần tử khác nhau, phần tử dư của stream dài hơn không tạo thành cặp.

**Cảnh báo nghiệp vụ:** zip theo vị trí chỉ đúng khi hai nguồn bảo đảm thứ tự tương ứng. Nếu `skus` và `quantities` đến từ hai topic độc lập, không thể mặc định phần tử thứ nhất của topic A thuộc cùng đơn vị với phần tử thứ nhất của topic B. Hãy ghép theo key như `orderId`, `sku` hoặc event ID bằng chiến lược join/state phù hợp.

### 3.3. combineLatest không phải zip

`combineLatest` giữ giá trị mới nhất của mỗi nguồn. Sau khi cả hai nguồn đã phát ít nhất một phần tử, mỗi cập nhật từ một nguồn có thể tạo output mới với giá trị mới nhất từ nguồn còn lại.

~~~java
Flux<String> price = Flux.just("P10", "P12");
Flux<String> stock = Flux.just("S5", "S4");

Flux<String> snapshots = Flux.combineLatest(
        price,
        stock,
        (p, s) -> p + "/" + s);
~~~

Với nguồn đồng bộ như `Flux.just`, thời điểm subscribe/lịch phát có thể khiến các snapshot trung gian không giống ví dụ minh họa. Trong hệ thống thật, hãy test theo scheduler và tốc độ phát thực tế. `combineLatest` phù hợp với **trạng thái mới nhất**, không phải để ghép một giao dịch với đúng một event tương ứng.

### 3.4. Quy tắc chọn nhanh

- Muốn gom các event độc lập: chọn `merge`.
- Muốn chạy nguồn này xong rồi mới chạy nguồn kia: chọn `concat`.
- Muốn ghép phần tử có quan hệ theo thứ tự: chọn `zip`.
- Muốn phản ứng với trạng thái mới nhất của nhiều nguồn: chọn `combineLatest`.
- Muốn join theo ID hoặc cửa sổ thời gian: cần chiến lược join/state/window riêng; không thay bằng zip theo chỉ số.

## 4. Chuẩn bị dự án Maven

Lab sử dụng **JDK 17**, **Maven 3.9+**, **Spring Boot 3.5.0** và **Spring Cloud 2025.0.0** làm mốc ví dụ. Cặp release train này được dùng để quản lý phiên bản Spring Cloud Function/Stream qua BOM. Với dự án mới, hãy chọn bản vá còn được hỗ trợ trong release train tương thích thay vì ghép các version riêng lẻ.

Tạo thư mục `reactor-tuple-lab`:

~~~text
reactor-tuple-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/tuplelab/
    │   │   ├── TupleLabApplication.java
    │   │   └── StreamFunctions.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/tuplelab/
            ├── TupleFunctionUnitTest.java
            └── TupleFunctionCatalogTest.java
~~~

Để tập trung vào `FunctionCatalog` và Reactor, phần kiểm thử chính không cần broker. Dependency Spring Cloud Stream sẽ được thêm ở phần triển khai nhiều binding.

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>reactor-tuple-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>reactor-tuple-lab</name>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
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

| Dependency | Vai trò |
| --- | --- |
| `spring-boot-starter` | Spring context và auto-configuration |
| `spring-cloud-function-context` | `FunctionCatalog` và functional bean |
| `spring-boot-starter-test` | JUnit 5, Spring Boot Test, assertion |
| `reactor-test` | `StepVerifier`, virtual time và công cụ test Reactor |

Reactor Core thường đã có trên classpath thông qua Spring Cloud Function. Nếu code cần khai báo dependency trực tiếp để dùng `Flux`, `Tuple2` và `Tuples`, có thể khai báo `io.projectreactor:reactor-core` nhưng nên để BOM quản lý version.

## 5. Khai báo các function có nhiều input và output

Tạo `StreamFunctions.java`:

~~~java
package com.example.tuplelab;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;
import reactor.util.function.Tuple3;

@Configuration(proxyBeanMethods = false)
public class StreamFunctions {

    // Hai input stream -> một output stream.
    @Bean
    public Function<
            Tuple2<Flux<String>, Flux<String>>,
            Flux<String>> mergeLabels() {

        return tuple -> {
            Flux<String> orders = tuple.getT1()
                    .map(value -> "ORDER:" + value);
            Flux<String> customers = tuple.getT2()
                    .map(value -> "CUSTOMER:" + value);

            return Flux.merge(orders, customers);
        };
    }

    // Hai input stream -> ghép từng cặp theo vị trí -> một output.
    @Bean
    public Function<
            Tuple2<Flux<Integer>, Flux<Integer>>,
            Flux<String>> zipQuantitiesAndPrices() {

        return tuple -> Flux.zip(
                tuple.getT1(),
                tuple.getT2(),
                (quantity, unitPrice) ->
                        "LINE_TOTAL:" + Math.multiplyExact(
                                quantity.longValue(),
                                unitPrice.longValue()));
    }

    // Một input stream -> hai output stream.
    @Bean
    public Function<
            Flux<Integer>,
            Tuple2<Flux<String>, Flux<String>>> splitParity() {

        return numbers -> {
            // Hai output binding cần cùng quan sát một nguồn upstream.
            // autoConnect(2) chờ cả hai nhánh subscribe rồi mới kết nối nguồn.
            Flux<Integer> shared = numbers.publish().autoConnect(2);

            Flux<String> even = shared
                    .filter(number -> number % 2 == 0)
                    .map(number -> "EVEN:" + number);

            Flux<String> odd = shared
                    .filter(number -> number % 2 != 0)
                    .map(number -> "ODD:" + number);

            return Tuples.of(even, odd);
        };
    }

    // Ba input stream -> một output stream.
    @Bean
    public Function<
            Tuple3<Flux<String>, Flux<String>, Flux<String>>,
            Flux<String>> mergeThreeSources() {

        return tuple -> Flux.merge(
                tuple.getT1().map(value -> "A:" + value),
                tuple.getT2().map(value -> "B:" + value),
                tuple.getT3().map(value -> "C:" + value));
    }
}
~~~

### 5.1. mergeLabels: nhiều input, một output

Chữ ký:

~~~java
Function<Tuple2<Flux<String>, Flux<String>>, Flux<String>>
~~~

`Tuple2` chứa hai stream. Function lấy từng stream bằng `getT1()` và `getT2()`, thêm nhãn rồi gọi `Flux.merge(...)`.

Ví dụ input:

~~~text
Input 0: ["O-1", "O-2"]
Input 1: ["C-1", "C-2"]
~~~

Output có bốn giá trị:

~~~text
ORDER:O-1
ORDER:O-2
CUSTOMER:C-1
CUSTOMER:C-2
~~~

Thứ tự xen kẽ giữa hai nguồn không được bảo đảm. `merge` phát theo tín hiệu đến; không được dùng vị trí output để suy ra một cặp order/customer.

### 5.2. zipQuantitiesAndPrices: ghép cặp theo vị trí

Chữ ký:

~~~java
Function<Tuple2<Flux<Integer>, Flux<Integer>>, Flux<String>>
~~~

Input thứ nhất là quantity, input thứ hai là unit price. `Flux.zip` ghép phần tử theo vị trí:

~~~text
quantity:  [2, 3, 1]
unitPrice: [100, 50, 200]
               |
               v
        zip(quantity, unitPrice)
               |
               v
LINE_TOTAL:200
LINE_TOTAL:150
LINE_TOTAL:200
~~~

`Math.multiplyExact` giúp phát hiện overflow thay vì tạo kết quả sai âm thầm. Trong ứng dụng thật, nên truyền record có key và ghép theo `sku`/`orderId` nếu hai stream không có bảo đảm thứ tự.

### 5.3. splitParity: một input, hai output

Chữ ký:

~~~java
Function<Flux<Integer>, Tuple2<Flux<String>, Flux<String>>>
~~~

Input được chia thành hai nhánh:

- `getT1()`: các số chẵn có tiền tố `EVEN:`.
- `getT2()`: các số lẻ có tiền tố `ODD:`.

Vì hai output được subscribe độc lập bởi hai output binding, không nên tạo hai phép biến đổi độc lập trên một nguồn nóng hoặc unicast mà không chia sẻ nguồn. `publish().autoConnect(2)` trong ví dụ chờ hai subscriber kết nối rồi mới subscribe upstream một lần.

**Điều kiện:** cơ chế này giả định adapter sẽ subscribe cả hai output. Nếu một output không được bind/subscribe, upstream có thể không chạy. Đây là trade-off cần kiểm thử trong cấu hình thực tế; không phải mẫu chia sẻ duy nhất cho mọi ứng dụng.

### 5.4. mergeThreeSources: ba input

`Tuple3<Flux<String>, Flux<String>, Flux<String>>` biểu diễn ba input độc lập. Dùng `getT1()`, `getT2()`, `getT3()` và `Flux.merge(...)`.

Với số lượng stream lớn hơn, Reactor có `Tuple4`, `Tuple5`... nhưng chữ ký dài và khó bảo trì. Hãy cân nhắc một event schema tổng hợp hoặc một mô hình ingress rõ ràng khi số nguồn tăng.

## 6. Khởi động Spring Boot và cấu hình mặc định

Tạo `TupleLabApplication.java`:

~~~java
package com.example.tuplelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TupleLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(TupleLabApplication.class, args);
    }
}
~~~

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: reactor-tuple-lab
  cloud:
    function:
      single-function-fallback-enabled: false
~~~

Trong test catalog, ta lookup từng function theo tên. Khi bật Spring Cloud Stream ở phần sau, sẽ cấu hình rõ `spring.cloud.function.definition` để chọn function nào cần tạo binding.

## 7. Kiểm thử từng function bằng StepVerifier

`StepVerifier` kiểm tra tín hiệu Reactive Streams: `onNext`, `onComplete`, `onError`. Với các stream có nhiều output, test phải subscribe **cả hai nhánh** nếu function đang chia sẻ upstream bằng `autoConnect(2)`.

Tạo `TupleFunctionUnitTest.java`:

~~~java
package com.example.tuplelab;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

class TupleFunctionUnitTest {

    private final StreamFunctions functions = new StreamFunctions();

    @Test
    void mergesTwoInputStreams() {
        Function<
                Tuple2<Flux<String>, Flux<String>>,
                Flux<String>> function = functions.mergeLabels();

        Tuple2<Flux<String>, Flux<String>> input = Tuples.of(
                Flux.just("O-1", "O-2"),
                Flux.just("C-1", "C-2"));

        StepVerifier.create(function.apply(input).collectList())
                .assertNext(values -> assertEquals(
                        Set.of(
                                "ORDER:O-1",
                                "ORDER:O-2",
                                "CUSTOMER:C-1",
                                "CUSTOMER:C-2"),
                        new HashSet<>(values)))
                .verifyComplete();
    }

    @Test
    void zipsQuantitiesAndPricesByPosition() {
        Function<
                Tuple2<Flux<Integer>, Flux<Integer>>,
                Flux<String>> function =
                functions.zipQuantitiesAndPrices();

        Tuple2<Flux<Integer>, Flux<Integer>> input = Tuples.of(
                Flux.just(2, 3, 1),
                Flux.just(100, 50, 200));

        StepVerifier.create(function.apply(input))
                .expectNext(
                        "LINE_TOTAL:200",
                        "LINE_TOTAL:150",
                        "LINE_TOTAL:200")
                .verifyComplete();
    }

    @Test
    void zipCompletesWhenTheShortestInputCompletes() {
        Function<
                Tuple2<Flux<Integer>, Flux<Integer>>,
                Flux<String>> function =
                functions.zipQuantitiesAndPrices();

        Tuple2<Flux<Integer>, Flux<Integer>> input = Tuples.of(
                Flux.just(2, 3, 1),
                Flux.just(100));

        StepVerifier.create(function.apply(input))
                .expectNext("LINE_TOTAL:200")
                .verifyComplete();
    }

    @Test
    void splitsOneInputIntoEvenAndOddOutputs() {
        Function<
                Flux<Integer>,
                Tuple2<Flux<String>, Flux<String>>> function =
                functions.splitParity();

        Tuple2<Flux<String>, Flux<String>> outputs =
                function.apply(Flux.range(1, 6));

        // Subscribe đồng thời cả hai output để autoConnect(2) bắt đầu nguồn.
        Flux<Tuple2<List<String>, List<String>>> both =
                Flux.zip(
                        outputs.getT1().collectList(),
                        outputs.getT2().collectList());

        StepVerifier.create(both)
                .assertNext(tuple -> {
                    assertEquals(
                            List.of("EVEN:2", "EVEN:4", "EVEN:6"),
                            tuple.getT1());
                    assertEquals(
                            List.of("ODD:1", "ODD:3", "ODD:5"),
                            tuple.getT2());
                })
                .verifyComplete();
    }

    @Test
    void mergesThreeInputStreams() {
        var input = Tuples.of(
                Flux.just("1"),
                Flux.just("2"),
                Flux.just("3"));

        StepVerifier.create(
                        functions.mergeThreeSources()
                                .apply(input)
                                .collectList())
                .assertNext(values -> assertEquals(
                        Set.of("A:1", "B:2", "C:3"),
                        new HashSet<>(values)))
                .verifyComplete();
    }
}
~~~

### 7.1. Vì sao merge test so sánh Set?

`Flux.merge` có thể phát xen kẽ các nguồn theo thời điểm phát. Test chỉ nên khẳng định **các phần tử cần có**, không khẳng định thứ tự nếu hợp đồng không bảo đảm thứ tự.

### 7.2. Vì sao zip test kiểm tra stream ngắn nhất?

Khi một publisher hoàn tất, `zip` không thể tạo thêm cặp mới nếu không có phần tử tương ứng từ publisher đó. Test `zipCompletesWhenTheShortestInputCompletes` chứng minh output có một cặp và hoàn tất, dù stream quantity có ba phần tử.

### 7.3. Vì sao split test phải subscribe cả hai output?

Function dùng:

~~~java
Flux<Integer> shared = numbers.publish().autoConnect(2);
~~~

Nó chỉ kết nối nguồn sau khi hai subscriber đăng ký. `Flux.zip(outputs.getT1().collectList(), outputs.getT2().collectList())` subscribe cả hai nhánh cùng lúc. Nếu chỉ test `getT1()` trong khi `autoConnect(2)` đang chờ, test có thể không nhận dữ liệu hoặc timeout.

## 8. Kiểm thử reactive functions qua FunctionCatalog

Unit test trực tiếp chứng minh logic Reactor. Tiếp theo, khởi tạo Spring context để xác minh các bean có trong `FunctionCatalog` và có thể gọi bằng tên.

Tạo `TupleFunctionCatalogTest.java`:

~~~java
package com.example.tuplelab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@SpringBootTest(
        classes = TupleLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class TupleFunctionCatalogTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void looksUpFunctionWithTwoInputs() {
        Function<
                Tuple2<Flux<String>, Flux<String>>,
                Flux<String>> function =
                catalog.lookup("mergeLabels");

        assertNotNull(function);

        var input = Tuples.of(
                Flux.just("O-10"),
                Flux.just("C-10"));

        StepVerifier.create(function.apply(input).collectList())
                .assertNext(values -> assertEquals(
                        Set.of("ORDER:O-10", "CUSTOMER:C-10"),
                        new HashSet<>(values)))
                .verifyComplete();
    }

    @Test
    void looksUpFunctionWithMultipleOutputs() {
        Function<
                Flux<Integer>,
                Tuple2<Flux<String>, Flux<String>>> function =
                catalog.lookup("splitParity");

        assertNotNull(function);

        Tuple2<Flux<String>, Flux<String>> output =
                function.apply(Flux.range(1, 4));

        Flux<Tuple2<List<String>, List<String>>> both =
                Flux.zip(
                        output.getT1().collectList(),
                        output.getT2().collectList());

        StepVerifier.create(both)
                .assertNext(tuple -> {
                    assertEquals(
                            List.of("EVEN:2", "EVEN:4"),
                            tuple.getT1());
                    assertEquals(
                            List.of("ODD:1", "ODD:3"),
                            tuple.getT2());
                })
                .verifyComplete();
    }
}
~~~

Test này chứng minh:

- Spring đã đăng ký `mergeLabels` và `splitParity`.
- Catalog có thể tra cứu function có tuple chứa nhiều publisher.
- Function nhiều output trả tuple với đúng thứ tự output.
- Hai output có thể được kiểm tra đồng thời bằng `StepVerifier`.

**Giới hạn:** Đây vẫn là test FunctionCatalog trong application context. Nó chưa chứng minh Spring Cloud Stream tạo đúng binding hoặc broker thực sự giao hai input stream cho function.

## 9. Nhiều input và output trong Spring Cloud Stream

Spring Cloud Stream tạo tên binding dựa trên tên function và chỉ số input/output:

- Input: `<functionName>-in-<index>`
- Output: `<functionName>-out-<index>`

Chỉ số bắt đầu từ 0. Với function có nhiều input hoặc output, mỗi vị trí trong tuple tương ứng một binding riêng.

### 9.1. Binding của mergeLabels

Chữ ký:

~~~java
Function<Tuple2<Flux<String>, Flux<String>>, Flux<String>>
~~~

Có hai input và một output:

| Vị trí tuple | Binding | Destination ví dụ |
| --- | --- | --- |
| `getT1()` | `mergeLabels-in-0` | `orders.events` |
| `getT2()` | `mergeLabels-in-1` | `customers.events` |
| Output | `mergeLabels-out-0` | `activity.events` |

### 9.2. Binding của splitParity

Chữ ký:

~~~java
Function<Flux<Integer>, Tuple2<Flux<String>, Flux<String>>>
~~~

Có một input và hai output:

| Vị trí tuple | Binding | Destination ví dụ |
| --- | --- | --- |
| Input | `splitParity-in-0` | `numbers.in` |
| `getT1()` | `splitParity-out-0` | `numbers.even` |
| `getT2()` | `splitParity-out-1` | `numbers.odd` |

Thứ tự `getT1()`/`getT2()` phải khớp thứ tự binding output. Nếu đảo tuple, dữ liệu chẵn/lẻ sẽ đi sang destination khác.

### 9.3. Cấu hình application.yml cho hai function

Để bind đồng thời cả hai function, thêm Spring Cloud Stream và binder phù hợp vào Maven. Sau đó cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: mergeLabels;splitParity
    stream:
      bindings:
        mergeLabels-in-0:
          destination: orders.events
          group: tuple-lab
          content-type: text/plain
        mergeLabels-in-1:
          destination: customers.events
          group: tuple-lab
          content-type: text/plain
        mergeLabels-out-0:
          destination: activity.events
          content-type: text/plain

        splitParity-in-0:
          destination: numbers.in
          group: tuple-lab
          content-type: application/json
        splitParity-out-0:
          destination: numbers.even
          content-type: text/plain
        splitParity-out-1:
          destination: numbers.odd
          content-type: text/plain
~~~

Ở đây dấu `;` trong `spring.cloud.function.definition` chọn **hai function độc lập** cùng được bind trong ứng dụng. Nó không phải toán tử composition `|`. Mỗi function vẫn có binding riêng theo tên và index.

Ví dụ này mới là cấu hình binding; để chạy thật, cần thêm:

- `spring-cloud-stream` và binder (Kafka hoặc RabbitMQ) tương thích BOM.
- Cấu hình địa chỉ broker, credential và topic/queue.
- Test header/content type và serialization theo binder.
- Chính sách retry, DLQ, concurrency và giám sát.

### 9.4. Binding của function ba input

Với `mergeThreeSources`, ba input sẽ có tên:

~~~text
mergeThreeSources-in-0
mergeThreeSources-in-1
mergeThreeSources-in-2
~~~

Output:

~~~text
mergeThreeSources-out-0
~~~

Đây là cách tuple biểu diễn cardinality. Mỗi input có thể map tới một destination riêng và cấu hình content type/consumer property riêng.

## 10. Chú ý về subscription và nhiều output

Một function trả hai `Flux` không đơn giản là tạo hai collection rồi trả về. Mỗi output binding thường subscribe publisher đầu ra của mình. Cần suy nghĩ kỹ cách hai output quan sát nguồn đầu vào.

### 10.1. Hai nhánh có thể gây hai subscription lên nguồn

Ví dụ dễ gây lỗi:

~~~java
return Tuples.of(
        input.filter(value -> value % 2 == 0),
        input.filter(value -> value % 2 != 0));
~~~

Nếu `input` là cold publisher, hai nhánh có thể subscribe riêng và làm upstream thực thi hai lần. Nếu nguồn là unicast/hot publisher, subscription thứ hai có thể không được hỗ trợ hoặc không nhận cùng dữ liệu.

### 10.2. Chia sẻ nguồn bằng publish

Lab sử dụng:

~~~java
Flux<Integer> shared = input.publish().autoConnect(2);
~~~

`publish()` tạo cơ chế chia sẻ subscription upstream; `autoConnect(2)` bắt đầu kết nối sau khi có hai subscriber. Mỗi nhánh nhận một góc nhìn từ cùng nguồn:

~~~text
                 input Flux
                     |
              publish/autoConnect(2)
                     |
             +-------+-------+
             |               |
           even            odd
             |               |
             v               v
          output 0         output 1
~~~

Điều kiện `2` phải phù hợp số subscriber của các output. Nếu có ba output, cần xem xét số subscriber và lifecycle tương ứng. Không đặt một con số cố định rồi tái sử dụng cho mọi hàm.

### 10.3. Hủy subscription và lỗi

Trong nhiều output:

- Nếu một output bị hủy, cần biết nhánh còn lại có tiếp tục không.
- Nếu upstream phát `onError`, cả các nhánh chia sẻ cùng nguồn có thể nhận lỗi.
- Nếu một nhánh xử lý chậm, backpressure và buffering ảnh hưởng tới nguồn chung.
- Nếu binder chỉ subscribe một output, `autoConnect(2)` có thể không kết nối nguồn.

Đây là lý do phải test bằng cả hai output trong unit test và test binder khi triển khai.

## 11. Backpressure và chiến lược xử lý luồng

Reactive Streams dùng backpressure để downstream báo nhu cầu dữ liệu. Tuy nhiên, khả năng truyền backpressure từ broker qua binder tới publisher phụ thuộc loại binder và adapter.

Với nhiều input:

- Một input chậm có thể khiến `zip` chờ, trong khi input nhanh có phần tử đệm.
- `merge` có thể interleave nhiều nguồn; cần giới hạn concurrency/buffer khi nguồn lớn.
- `combineLatest` giữ giá trị mới nhất của từng nguồn.
- `concat` xử lý tuần tự nhưng có thể làm tăng latency của nguồn đứng sau.

Với nhiều output:

- Nhánh output chậm có thể ảnh hưởng tới nguồn chia sẻ.
- Các toán tử `onBackpressureBuffer`, `onBackpressureDrop` hoặc `onBackpressureLatest` có semantics khác nhau; chọn sai có thể mất event hoặc tiêu thụ nhiều bộ nhớ.
- Không thêm buffer không giới hạn chỉ để “chữa” output chậm.

Ví dụ giới hạn số phần tử đang xử lý khi gọi dịch vụ bất đồng bộ:

~~~java
Flux<String> results = input.flatMap(
        value -> callRemoteService(value),
        8);
~~~

Tham số `8` giới hạn concurrency của `flatMap`; đây chỉ là ví dụ Reactor, không phải một bảo đảm chung cho mọi adapter. Trong production, concurrency cần phù hợp connection pool, broker, latency và giới hạn dịch vụ downstream.

## 12. Lỗi trong một luồng ảnh hưởng thế nào?

Reactive publisher phát `onError` như tín hiệu terminal. Với `merge`, `zip` hoặc `combineLatest`, lỗi từ một nguồn thường kết thúc publisher kết hợp và hủy các nguồn còn lại, trừ khi ta chủ động áp dụng chính sách xử lý lỗi khác.

### 12.1. Xử lý lỗi cho một nguồn trước khi merge

~~~java
Flux<String> safeOrders = orders.onErrorResume(error ->
        Flux.just("ORDER_SOURCE_FAILED"));

Flux<String> safeCustomers = customers.onErrorResume(error ->
        Flux.just("CUSTOMER_SOURCE_FAILED"));

return Flux.merge(safeOrders, safeCustomers);
~~~

Đây là chính sách minh họa: thay lỗi của một nguồn bằng event sentinel. Hệ thống thật nên dùng một schema lỗi có cấu trúc và correlation ID; không dùng chuỗi sentinel nếu nó có thể trùng dữ liệu thật.

### 12.2. zip và lỗi

`zip` cần một phần tử từ từng nguồn để tạo cặp. Nếu một nguồn lỗi, zip thường lỗi và hủy nguồn còn lại. Nếu một nguồn hoàn tất sớm, zip có thể hoàn tất mà không sử dụng các phần tử dư.

Nếu dữ liệu cần join theo key, việc chỉ `onErrorResume` rồi zip có thể tạo cặp sai. Hãy tách lỗi transport khỏi logic tương quan dữ liệu.

### 12.3. Lỗi một output trong function fan-out

Với hai output tách từ một upstream:

- Lỗi xảy ra trước điểm chia sẻ thường ảnh hưởng cả hai output.
- Lỗi trong phép biến đổi riêng của một nhánh có thể chỉ ảnh hưởng nhánh đó, tùy cách xử lý và subscription.
- Adapter/binder còn quyết định việc retry, gửi DLQ hoặc fail binding.

Không giả định một output lỗi sẽ tự động rollback output kia. Nếu hai output đại diện cho một giao dịch cần nhất quán, cần thiết kế outbox/transaction hoặc event choreography phù hợp.

## 13. Kiểm thử lỗi và cancellation

Có thể bổ sung test cho `zip` khi một nguồn lỗi:

~~~java
@Test
void zipPropagatesInputError() {
    Flux<Integer> quantities = Flux.just(2, 3);
    Flux<Integer> prices = Flux.concat(
            Flux.just(100),
            Flux.error(new IllegalStateException("price source failed")));

    Flux<String> result = Flux.zip(
            quantities,
            prices,
            (quantity, price) -> "TOTAL:" + quantity * price);

    StepVerifier.create(result)
            .expectNext("TOTAL:200")
            .expectError(IllegalStateException.class)
            .verify();
}
~~~

Test này chứng minh lỗi từ một nguồn truyền vào publisher kết hợp. Nó không kiểm tra retry/DLQ của broker.

Để kiểm tra cancellation, có thể dùng `doOnCancel` hoặc `TestPublisher` trong một test riêng. Điều quan trọng là xác định **ai hủy publisher**: client downstream, output binding, timeout hay lỗi của nguồn khác.

## 14. Tuple không phải công cụ join theo key

Tuple biểu diễn số lượng và kiểu stream, nhưng **không tự định nghĩa cách tương quan event**. Chọn `zip` không có nghĩa hai event cùng index có cùng order ID.

Giả sử:

~~~text
orders:
  O-1, O-2, O-3

payments:
  payment(O-2), payment(O-1), payment(O-3)
~~~

Zip theo index sẽ ghép:

~~~text
O-1 <-> payment(O-2)  (sai)
O-2 <-> payment(O-1)  (sai)
O-3 <-> payment(O-3)  (đúng)
~~~

Muốn join theo `orderId`, cần:

- Tạo key rõ ràng trong từng event.
- Chọn cơ chế join/state/window phù hợp.
- Quy định event đến muộn, duplicate, timeout và dữ liệu thiếu.
- Có chính sách cleanup state để không tăng bộ nhớ vô hạn.

Trong Reactor thuần, có thể xây dựng logic bằng `groupBy`, `window`, `buffer` hoặc state store phù hợp. Với event-time/windowed join phức tạp, cân nhắc nền tảng stream processing chuyên dụng thay vì tự viết một operator không kiểm soát.

## 15. Mở rộng cấu hình binder và kiểm thử tích hợp

Sau khi test unit và catalog pass, hãy thêm Spring Cloud Stream cùng binder phù hợp. Có thể dùng Test Binder để xác minh binding mà không cần broker ngoài, hoặc chạy Kafka/RabbitMQ trong môi trường integration test.

Một test adapter nên kiểm tra:

1. Hai input binding của `mergeLabels` đều được tạo.
2. Message từ cả hai destination đến đúng vị trí tuple.
3. Output của `mergeLabels` được gửi đến `mergeLabels-out-0`.
4. `splitParity` tạo đúng hai output binding.
5. Event chẵn đi tới `splitParity-out-0`, event lẻ tới `splitParity-out-1`.
6. Lỗi input được xử lý theo retry/DLQ đã cấu hình.
7. Khi một output chậm hoặc dừng, hành vi của nhánh còn lại được xác định.

**Không dùng test catalog thay thế test binder:** catalog test không tạo topic/queue, không xác nhận serialization qua transport và không chứng minh header mapping của broker.

## 16. Bài tập mở rộng

### Bài A — Dùng Tuple3 để hợp nhất ba loại sự kiện

Tạo function:

~~~java
Function<
    Tuple3<Flux<OrderEvent>, Flux<PaymentEvent>, Flux<ShipmentEvent>>,
    Flux<String>
>
~~~

**Yêu cầu:**

- Gắn nhãn từng loại event.
- Dùng `Flux.merge`.
- Test đủ ba input.
- So sánh tập kết quả thay vì giả định thứ tự xen kẽ.

### Bài B — Ghép quantity và unit price bằng zip

Dùng `Tuple2<Flux<Integer>, Flux<Long>>`:

- Input 0 là quantity.
- Input 1 là unit price.
- Output là tổng tiền mỗi dòng.

**Yêu cầu:** test hai stream cùng số phần tử, một stream ngắn hơn và trường hợp overflow. Ghi rõ điều kiện thứ tự hai stream phải tương ứng.

### Bài C — Tách sự kiện theo trạng thái

Thay chẵn/lẻ bằng:

~~~text
Flux<OrderEvent>
    -> Tuple2<Flux<OrderEvent>, Flux<OrderEvent>>
    -> approved / rejected
~~~

**Yêu cầu:** chỉ một nhánh nhận mỗi event; test cả hai output cùng subscribe. Thêm trường `orderId` để kiểm tra không bị mất hoặc phát trùng.

### Bài D — So sánh merge với concat

Tạo hai nguồn có `delayElements`. Dùng `merge` và `concat` rồi quan sát thứ tự phát.

**Yêu cầu:** giải thích vì sao `concat` giữ toàn bộ nguồn thứ nhất trước nguồn thứ hai, còn `merge` xen kẽ theo lịch phát.

### Bài E — Xử lý một nguồn lỗi

Tạo hai input, một input có thể phát lỗi. Thử ba chính sách:

- Để lỗi lan ra ngoài.
- `onErrorResume` thay bằng event lỗi.
- Tách lỗi sang một output riêng.

**Yêu cầu:** test `onError` và `onComplete`; nêu rõ dữ liệu nào có thể bị mất hoặc được phát lại.

### Bài F — Tạo binding cho nhiều input/output

Thêm Spring Cloud Stream Test Binder:

- Gửi vào `mergeLabels-in-0` và `mergeLabels-in-1`.
- Đọc `mergeLabels-out-0`.
- Gửi vào `splitParity-in-0`.
- Đọc cả `splitParity-out-0` và `splitParity-out-1`.

**Yêu cầu:** xác nhận số binding và thứ tự tuple. Không chỉ test một output rồi kết luận output còn lại hoạt động.

## 17. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Function không được nhận diện là nhiều input | Dùng `Tuple2<String,String>` thay vì tuple của `Flux` | Dùng reactive arity `Tuple2<Flux<A>,Flux<B>>` |
| Chỉ có một input binding | Chữ ký function không thể hiện tuple nhiều stream | Kiểm tra generic tuple và dependency Stream |
| Output binding thứ hai không được tạo | Return type không phải tuple chứa publisher | Dùng `Tuple2<Flux<A>,Flux<B>>` |
| Nhầm `Tuple2<Flux<A>,Flux<B>>` với `Flux<Tuple2<A,B>>` | Tuple chứa stream khác stream chứa tuple | Kiểm tra kiểu generic và cardinality |
| `zip` bỏ phần tử cuối | Một nguồn ngắn hơn | Chọn semantics khác hoặc xử lý unmatched events |
| `zip` ghép sai order | Hai nguồn không có cùng thứ tự | Join theo key, không ghép theo index |
| `merge` test lúc pass lúc fail | Test giả định thứ tự xen kẽ | Assert tập phần tử hoặc thứ tự chỉ trong nguồn |
| `splitParity` không phát dữ liệu | `autoConnect(2)` mới có một subscriber | Subscribe cả hai output; kiểm tra binder tạo cả hai binding |
| Upstream chạy hai lần | Hai nhánh subscribe trực tiếp cùng cold source | Chia sẻ upstream có chủ đích hoặc thiết kế source idempotent |
| Một output bị mất dữ liệu đầu stream | Dùng hot publisher khi nhánh thứ hai subscribe muộn | Đồng bộ subscription hoặc thiết kế replay/buffering phù hợp |
| Lỗi một nguồn làm dừng mọi nguồn | Toán tử kết hợp truyền `onError` terminal | Xác định error policy trước merge/zip |
| Buffer tăng liên tục | Một nhánh tiêu thụ chậm | Giới hạn buffer/concurrency, quan sát backpressure |
| Test catalog pass nhưng binder lỗi | Chưa kiểm tra binding/serialization | Viết Test Binder hoặc broker integration test |
| Dùng tuple quá lớn | Hàm có quá nhiều nguồn, khó hiểu | Tạo model event tổng hợp hoặc tách pipeline |

### 17.1. Trình tự debug

1. Kiểm tra generic của function.
2. Xác nhận tuple có đúng số lượng publisher.
3. Gọi function trực tiếp với `Tuples.of(...)`.
4. Dùng `StepVerifier` test từng output; với fan-out phải subscribe mọi nhánh cần kiểm tra.
5. Xác định operator là `merge`, `zip`, `concat` hay `combineLatest`.
6. Kiểm tra completion, error và cancellation của từng nguồn.
7. Kiểm tra binding name theo index.
8. Cuối cùng mới kiểm tra binder và broker thực tế.

## 18. Tiêu chí hoàn thành

| Tiêu chí | Bằng chứng |
| --- | --- |
| Hiểu Tuple | Phân biệt `Tuple2<Flux<A>,Flux<B>>` và `Flux<Tuple2<A,B>>` |
| Nhiều input | `mergeLabels` nhận hai stream qua tuple |
| Ghép cặp | `zipQuantitiesAndPrices` ghép phần tử theo vị trí |
| Nhiều output | `splitParity` trả hai stream qua tuple |
| Tuple3 | `mergeThreeSources` xử lý ba input |
| Reactive semantics | Giải thích merge/zip/concat/combineLatest |
| Subscription | Test fan-out subscribe đồng thời hai nhánh |
| Catalog | Tra cứu function nhiều input/output qua `FunctionCatalog` |
| Binding | Xác định đúng `-in-0`, `-in-1`, `-out-0`, `-out-1` |
| Adapter | Phân biệt catalog test và binder integration test |

**Tóm tắt:** Reactor Tuple cung cấp arity và type information cho các reactive function có nhiều input/output. `Tuple2<Flux<A>,Flux<B>>` biểu diễn hai stream đầu vào; `Tuple2<Flux<A>,Flux<B>>` ở vị trí output biểu diễn hai stream đầu ra. Dùng `merge` khi cần hợp nhất event độc lập, `zip` khi cần ghép phần tử tương ứng theo vị trí và `publish` khi cần chia sẻ một nguồn cho nhiều output. Spring Cloud Stream ánh xạ từng vị trí tuple thành binding riêng; adapter/binder vẫn cần được kiểm thử để xác nhận hành vi vận chuyển thật.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `Tuple2<Flux<String>,Flux<Integer>>` biểu diễn điều gì?

**Đáp án:** Một tuple có hai publisher độc lập: publisher thứ nhất phát String, publisher thứ hai phát Integer.

**Câu 2.** `Flux<Tuple2<String,Integer>>` khác gì kiểu trên?

**Đáp án:** Đây là một publisher phát các cặp String/Integer; không phải hai input stream riêng.

**Câu 3.** Vì sao function arity của Spring Cloud Function dùng reactive function?

**Đáp án:** Tuple chứa các publisher thực tế để framework nhìn thấy nhiều stream và biết số lượng/kiểu input-output binding. Hỗ trợ arity hướng tới chữ ký reactive `Function<TupleN<Flux<...>>,TupleN<Flux<...>>>`.

**Câu 4.** `Flux.merge(a,b)` có ghép phần tử thứ nhất của a với phần tử thứ nhất của b không?

**Đáp án:** Không. Nó hợp nhất tín hiệu từ hai nguồn; không tạo cặp theo vị trí.

**Câu 5.** Khi nào `zip` hoàn tất nếu một nguồn có ít phần tử hơn?

**Đáp án:** Khi một nguồn hoàn tất và không còn phần tử để tạo cặp tiếp theo, zip có thể hoàn tất; các phần tử dư của nguồn dài hơn không tạo output.

**Câu 6.** Vì sao cần `publish().autoConnect(2)` trong ví dụ split?

**Đáp án:** Để hai output subscriber chia sẻ một upstream subscription; nguồn chỉ kết nối sau khi cả hai nhánh đã subscribe.

**Câu 7.** `splitParity-out-0` và `splitParity-out-1` tương ứng với vị trí nào?

**Đáp án:** `out-0` nhận `getT1()` (số chẵn), `out-1` nhận `getT2()` (số lẻ).

**Câu 8.** Test `FunctionCatalog` pass có chứng minh Kafka đã tạo đủ topic không?

**Đáp án:** Không. Cần test binding/binder hoặc broker thực tế.

**Câu 9.** Nếu hai stream orders và payments không cùng thứ tự, dùng zip có an toàn không?

**Đáp án:** Không. Zip ghép theo vị trí; cần join theo key như orderId hoặc một chiến lược state/window.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming Model và Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Multiple Input and Output Arguments](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream.html)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Project Reactor — Tuple2 API](https://projectreactor.io/docs/core/release/api/reactor/util/function/Tuple2.html)
- [Project Reactor — Tuples factory API](https://projectreactor.io/docs/core/release/api/reactor/util/function/Tuples.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
