# getModuleBasePackages(JavaPackage) và đầu vào strategy

Khi quy tắc phát hiện module mặc định hoặc **explicitly-annotated** không phù hợp với cấu trúc ứng dụng, Spring Modulith cho phép tự chọn package nào sẽ trở thành base package của Application Module. Điểm mở rộng đó là interface **ApplicationModuleDetectionStrategy**, với phương thức quan trọng:

~~~java
Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage);
~~~

Phương thức nhận một đối tượng **JavaPackage** đại diện cho package gốc mà Spring Modulith được khởi tạo để phân tích, thường là package chứa class **@SpringBootApplication**. Strategy cần trả về một **Stream<JavaPackage>** gồm các package được chọn làm base package của module.

Bài học này giải thích dữ liệu đầu vào **JavaPackage**, cách duyệt và lọc package, cách viết strategy có quy tắc rõ ràng, cách đăng ký và cách kiểm chứng danh sách module được tạo ra.

## 1. Vai trò của getModuleBasePackages()

Spring Modulith xây dựng mô hình Application Module từ cấu trúc package của ứng dụng. Mặc định, mỗi package con trực tiếp của package chứa class ứng dụng Spring Boot được xem là một module. Khi cấu trúc thực tế có nhiều nhóm package hoặc quy tắc nghiệp vụ riêng, ta có thể thay đổi cách chọn module bằng **ApplicationModuleDetectionStrategy**.

Interface này nằm trong package:

~~~java
org.springframework.modulith.core.ApplicationModuleDetectionStrategy
~~~

Phương thức **getModuleBasePackages(…)** có hợp đồng:

- Đầu vào là **JavaPackage rootPackage**, không phải tên package dạng **String**, **java.lang.Package** hay đường dẫn thư mục.
- Đầu vào không được **null**.
- Giá trị trả về là **Stream<JavaPackage>** không được **null**.
- Mỗi phần tử trả về là một package mà Spring Modulith sẽ xem là base package của một Application Module.

Spring Modulith gọi strategy với package mà mô hình được khởi tạo. Trong ứng dụng thông thường, đó là package của class **@SpringBootApplication**. Strategy có trách nhiệm kiểm tra các package bên dưới và chọn những package phù hợp với quy ước của ứng dụng.

## 2. JavaPackage là gì?

**JavaPackage** là abstraction của Spring Modulith cho một Java package trong mô hình phân tích mã nguồn. Lớp này thuộc **org.springframework.modulith.core** và được xây dựng trên mô hình class mà ArchUnit cung cấp.

Không nên nhầm **JavaPackage** với:

- **java.lang.Package**: metadata package mà JVM cung cấp tại runtime.
- **String**: tên package như **"com.acme.shop.orders"**.
- **Path** hoặc **File**: đường dẫn thư mục trên ổ đĩa.

Một **JavaPackage** mang thông tin để strategy duyệt package và các type đã được mô hình phân tích. Các phương thức thường dùng gồm:

| Phương thức | Mục đích |
|---|---|
| **getName()** | Lấy tên đầy đủ, ví dụ **com.acme.shop.orders** |
| **getLocalName()** | Lấy segment cuối, ví dụ **orders** |
| **getDirectSubPackages()** | Lấy các package con trực tiếp |
| **getSubPackagesMatching(…)** | Tìm các package con khớp điều kiện |
| **getSubPackagesAnnotatedWith(…)** | Tìm các package con có annotation được chỉ định |
| **getClasses()** | Lấy các class thuộc package theo phạm vi của đối tượng |
| **getExposedClasses()** | Lấy các class public được package expose |

Ví dụ, nếu **rootPackage** đại diện **com.acme.shop**, các package con trực tiếp có thể là:

~~~text
com.acme.shop                 <- rootPackage
├── orders                    <- getDirectSubPackages()
├── inventory                 <- getDirectSubPackages()
├── payments                  <- getDirectSubPackages()
└── infrastructure            <- getDirectSubPackages()
    └── database              <- package con lồng sâu hơn
~~~

**getDirectSubPackages()** chỉ trả về cấp con trực tiếp của package hiện tại. Nó không tự trả về toàn bộ hậu duệ lồng sâu. Nếu muốn xét package ở nhiều cấp, cần chọn API duyệt subpackage phù hợp và xác định rõ cấp nào thực sự là module boundary.

## 3. Đọc đầu vào strategy trước khi lọc

Một strategy tốt cần hiểu package gốc đang đại diện cho phạm vi nào. Có thể viết một đoạn kiểm tra đơn giản trong chính phương thức:

~~~java
@Override
public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {

    System.out.println("Application root: " + rootPackage.getName());

    rootPackage.getDirectSubPackages().forEach(candidate ->
        System.out.println(
            candidate.getLocalName() + " -> " + candidate.getName()
        )
    );

    return rootPackage.getDirectSubPackages().stream();
}
~~~

Đoạn mã chỉ minh họa cách đọc dữ liệu:

- **rootPackage.getName()** cho biết package gốc mà Spring Modulith đưa vào strategy.
- **getDirectSubPackages()** cho biết các package con trực tiếp mà mô hình nhận diện.
- **getLocalName()** phù hợp khi quy tắc dựa trên segment cuối.
- **getName()** phù hợp khi cần so khớp tên đầy đủ để tránh trùng segment giữa các nhóm package.

Trong strategy thực tế, không nên giữ **System.out.println()** như một cơ chế logging lâu dài. Hãy dùng debugger hoặc test để kiểm tra đầu vào, sau đó giữ phương thức tập trung vào việc chọn package.

## 4. Ví dụ: chỉ chọn các module nghiệp vụ được khai báo

Giả sử package gốc của ứng dụng là **com.acme.shop**, trong đó có cả package nghiệp vụ lẫn package kỹ thuật:

~~~text
com.acme.shop
├── orders
├── inventory
├── payments
├── config
├── web
└── common
~~~

Ứng dụng chỉ muốn ba package nghiệp vụ trở thành module. Có thể viết strategy theo allowlist:

~~~java
package com.acme.shop.architecture;

import java.util.Set;
import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

public class BusinessModuleDetectionStrategy
        implements ApplicationModuleDetectionStrategy {

    private static final Set<String> MODULE_NAMES =
        Set.of("orders", "inventory", "payments");

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
        return rootPackage.getDirectSubPackages().stream()
            .filter(candidate ->
                MODULE_NAMES.contains(candidate.getLocalName()));
    }
}
~~~

Kết quả:

| Package | Có được trả về? | Lý do |
|---|---:|---|
| **com.acme.shop.orders** | Có | Segment cuối là **orders** |
| **com.acme.shop.inventory** | Có | Segment cuối là **inventory** |
| **com.acme.shop.payments** | Có | Segment cuối là **payments** |
| **com.acme.shop.config** | Không | Không thuộc allowlist |
| **com.acme.shop.web** | Không | Không thuộc allowlist |
| **com.acme.shop.common** | Không | Không thuộc allowlist |

Strategy không tạo **ApplicationModule** bằng cách gọi constructor. Nó chỉ trả về các **JavaPackage** đã chọn; Spring Modulith sử dụng những package này để xây dựng mô hình module.

## 5. Dùng tên đầy đủ khi quy tắc có nhiều nhóm package

**getLocalName()** chỉ trả về segment cuối. Nếu cấu trúc có nhiều nhóm con, hai package ở hai nhánh khác nhau có thể có cùng local name.

Ví dụ:

~~~text
com.acme.shop
├── business
│   ├── orders
│   └── inventory
├── platform
│   ├── orders
│   └── config
└── integrations
    └── payments
~~~

Nếu chỉ kiểm tra **getLocalName().equals("orders")**, cả **business.orders** và **platform.orders** đều có thể được chọn nếu strategy duyệt tới các package đó. Khi cần giới hạn chính xác, hãy so khớp **getName()**:

~~~java
private static final Set<String> MODULE_BASE_PACKAGES = Set.of(
    "com.acme.shop.business.orders",
    "com.acme.shop.business.inventory",
    "com.acme.shop.integrations.payments"
);

@Override
public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
    return rootPackage.getDirectSubPackages().stream()
        .flatMap(parent -> parent.getDirectSubPackages().stream())
        .filter(candidate ->
            MODULE_BASE_PACKAGES.contains(candidate.getName()));
}
~~~

Ví dụ này duyệt hai cấp package vì các module nằm dưới **business** và **integrations**. Package **platform.orders** không được chọn vì tên đầy đủ không nằm trong allowlist.

Hãy chọn cấp duyệt phù hợp với cấu trúc thực tế. Duyệt quá sâu có thể vô tình chọn **internal**, **persistence** hoặc package triển khai làm module riêng.

## 6. Chọn package theo quy ước thay vì allowlist

Nếu tên package có quy ước ổn định, strategy có thể dùng predicate để chọn module. Ví dụ, ứng dụng đặt các module dưới nhánh **business**:

~~~text
com.acme.shop
└── business
    ├── orders
    ├── inventory
    └── payments
~~~

Có thể lấy package **business** trước rồi trả về các package con trực tiếp của nó:

~~~java
@Override
public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
    return rootPackage.getDirectSubPackages().stream()
        .filter(candidate -> candidate.getLocalName().equals("business"))
        .flatMap(JavaPackage::getDirectSubPackages);
}
~~~

Trong trường hợp cần tìm package lồng sâu theo một điều kiện, **getSubPackagesMatching(…)** nhận một **BiPredicate<JavaPackage, String>**. Tham số thứ hai là tên package tương đối (trailing name) tính từ package hiện tại:

~~~java
return rootPackage.getSubPackagesMatching(
    (candidate, trailingName) ->
        trailingName.startsWith("business.")
            && !trailingName.substring("business.".length()).contains(".")
);
~~~

Điều kiện thứ hai giới hạn kết quả ở đúng một segment bên dưới **business**, ví dụ **business.orders**; nó loại các package sâu hơn như **business.orders.internal**. Chỉ dùng cách duyệt đệ quy khi cấu trúc có quy ước rõ ràng và các package được chọn thực sự là module base package. Nếu không, allowlist các tên đầy đủ thường dễ đọc và ít bất ngờ hơn.

## 7. getModuleBasePackages không phải nơi tạo Named Interface

**getModuleBasePackages(…)** quyết định **package nào là module**. Nó không quyết định các subpackage nào của module được công bố thành Named Interface.

Interface **ApplicationModuleDetectionStrategy** còn có phương thức mặc định **detectNamedInterfaces(JavaPackage basePackage, ApplicationModuleInformation information)** để tùy chỉnh việc phát hiện Named Interface. Nếu chỉ override **getModuleBasePackages(…)**, Spring Modulith tiếp tục sử dụng cơ chế mặc định để phát hiện Named Interface.

Phân biệt:

| API | Trách nhiệm |
|---|---|
| **getModuleBasePackages(rootPackage)** | Chọn các Application Module |
| **detectNamedInterfaces(basePackage, information)** | Tùy chỉnh các Named Interface bên trong một module |
| **@ApplicationModule** | Khai báo metadata và quy tắc của một module |
| **@NamedInterface** | Công bố một package con của module dưới tên giao diện |

Không nên trả về **orders.spi** từ **getModuleBasePackages()** nếu mục tiêu chỉ là công bố SPI. Làm như vậy sẽ yêu cầu framework xem package đó là module base package riêng theo strategy, thay vì Named Interface thuộc **orders**.

## 8. Đăng ký strategy với Spring Modulith

Sau khi viết class triển khai, đăng ký nó bằng property:

~~~properties
spring.modulith.detection-strategy=com.acme.shop.architecture.BusinessModuleDetectionStrategy
~~~

Giá trị property là tên đầy đủ của class strategy. Đặt cấu hình ở nơi phù hợp với mục đích sử dụng:

- Nếu strategy chỉ dùng cho kiểm chứng kiến trúc và tạo tài liệu trong test, có thể đặt class và cấu hình trong test sources.
- Nếu các thành phần runtime của Spring Modulith cũng cần strategy, chẳng hạn **ApplicationModuleInitializer**, actuator hoặc observability support, cần khai báo **spring-modulith-core** như compile-time dependency và bảo đảm strategy có mặt trên runtime classpath.

Strategy được cấu hình phải có thể được nạp bởi classloader ở thời điểm Spring Modulith xây dựng mô hình. Nếu property sai tên class hoặc class không có trên classpath, quá trình tạo mô hình sẽ thất bại.

## 9. Kiểm chứng đầu ra của strategy

Sau khi đăng ký strategy, hãy tạo test để in danh sách module và kiểm tra cấu trúc:

~~~java
package com.acme.shop;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class CustomModuleDetectionTests {

    @Test
    void detectsOnlyBusinessModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        Set<String> basePackages = modules.stream()
            .map(module -> module.getBasePackage().getName())
            .collect(Collectors.toSet());

        assertThat(basePackages).containsExactlyInAnyOrder(
            "com.acme.shop.orders",
            "com.acme.shop.inventory",
            "com.acme.shop.payments"
        );

        modules.verify();
    }
}
~~~

Test xác nhận hai điều riêng:

1. Tập package được phát hiện đúng với danh sách module nghiệp vụ mong muốn.
2. Dependency graph của mô hình đã phát hiện tuân thủ các quy tắc kiến trúc khi gọi **verify()**.

**verify()** không thể tự kết luận rằng allowlist trong custom strategy có phản ánh đúng nghiệp vụ hay không. Assertion về danh sách base package là cần thiết để phát hiện việc strategy vô tình bỏ sót module hoặc chọn nhầm package.

## 10. Các lỗi thường gặp khi triển khai strategy

**Trả về Stream<String> thay vì Stream<JavaPackage>.** Strategy phải trả về các đối tượng package nhận được từ mô hình, không phải tên package dạng chuỗi. Dùng **getName()** để so khớp, nhưng trả về chính **JavaPackage**.

**Trả về null.** Hợp đồng yêu cầu stream không null. Khi không tìm thấy module nào, trả về **Stream.empty()**; tuy nhiên, hãy xác nhận đó là kết quả có chủ đích.

**Dùng getLocalName() khi tên segment có thể trùng.** So khớp tên đầy đủ bằng **getName()** nếu có nhiều nhánh package hoặc module có tên giống nhau.

**Duyệt đệ quy mà không xác định module boundary.** Có thể chọn nhầm **internal**, **api** hoặc **persistence** thành module. Hãy xác định rõ cấp package nào là module trước khi gọi các API duyệt sâu.

**Nhầm package gốc với package của module.** Đầu vào **rootPackage** là package ứng dụng mà Spring Modulith được khởi tạo từ đó. Các package module được trả về phải là những base package bên dưới root theo cấu trúc ứng dụng.

**Cho rằng strategy tự cấu hình Spring component scan.** **ApplicationModuleDetectionStrategy** điều khiển mô hình module của Spring Modulith. Nó không tự thay đổi **@ComponentScan**, JPA entity scan hoặc cấu hình runtime của Spring Boot.

**Quên kiểm tra Named Interface.** Chọn đúng module chưa có nghĩa các API subpackage đã được công bố đúng. Hãy kiểm tra riêng Named Interface và dependency rule của consumer.

## 11. Quy trình thiết kế một custom strategy

Khi xây dựng strategy cho ứng dụng, hãy thực hiện theo trình tự:

1. Xác định package chứa class **@SpringBootApplication**; đó là đầu vào root của mô hình.
2. Kiểm tra **rootPackage.getName()** và danh sách **getDirectSubPackages()**.
3. Quyết định module base package nằm ở cấp trực tiếp hay cấp lồng sâu hơn.
4. Chọn quy tắc lọc bằng local name, fully qualified name, annotation hoặc naming convention.
5. Trả về **Stream<JavaPackage>** từ chính các package thuộc mô hình.
6. Đăng ký strategy qua **spring.modulith.detection-strategy**.
7. Viết assertion kiểm tra tập base package được phát hiện.
8. Chạy **ApplicationModules.verify()** để kiểm tra dependency graph.
9. Kiểm tra Named Interface riêng nếu ứng dụng cần tùy chỉnh API package được công bố.

Một custom strategy tốt có đầu vào rõ ràng, quy tắc chọn package dễ giải thích và đầu ra có thể kiểm tra bằng test. Khi **getModuleBasePackages(…)** chỉ chọn đúng những package thực sự đại diện cho năng lực nghiệp vụ, các bước verification, tài liệu hóa và kiểm thử module của Spring Modulith sẽ dựa trên một mô hình nhất quán.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals, Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html): đầu vào root package, cách triển khai và đăng ký **ApplicationModuleDetectionStrategy**.
- [Javadoc — ApplicationModuleDetectionStrategy](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html): hợp đồng **getModuleBasePackages()** và phương thức tùy chỉnh Named Interface.
- [Javadoc — JavaPackage](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/JavaPackage.html): **getName()**, **getLocalName()**, **getDirectSubPackages()** và các phương thức duyệt package.
