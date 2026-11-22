# Tổ chức gói mã nguồn và phạm vi quét Entity, Repository trong Spring Data JPA

## 1. Vì sao cần tổ chức package và cấu hình quét?

Trong ứng dụng Spring Boot dùng Spring Data JPA, các lớp thường được chia theo trách nhiệm: controller tiếp nhận yêu cầu, service xử lý nghiệp vụ, repository truy cập dữ liệu, còn entity biểu diễn dữ liệu được ánh xạ với bảng trong cơ sở dữ liệu.

Spring không tự động tìm mọi lớp trên toàn bộ classpath theo cùng một quy tắc. Các cơ chế quét khác nhau có phạm vi và mục đích riêng:

- **Component scanning** tìm các bean như `@Component`, `@Service`, `@Controller`, `@RestController`, `@Configuration` và các annotation mang tính chất component.
- **Entity scanning** tìm các lớp JPA được đánh dấu như `@Entity`, cùng metadata ánh xạ liên quan như `@Embeddable` và `@MappedSuperclass`.
- **Repository scanning** tìm các interface Spring Data (thường kế thừa `Repository`, `CrudRepository` hoặc `JpaRepository`) để tạo đối tượng proxy thực thi truy cập dữ liệu.

Tổ chức package đúng giúp Spring Boot tìm được bean, entity và repository khi khởi động. Nếu các phạm vi này không bao phủ package chứa lớp tương ứng, ứng dụng có thể lỗi khi khởi động hoặc không tạo được bean cần thiết.

## 2. Đặt lớp khởi động ở package gốc

`@SpringBootApplication` thường được đặt trên lớp main ở package gốc của ứng dụng. Các package chức năng nên là package con của package này.

Ví dụ cấu trúc theo chức năng:

~~~text
com.example.shop
├── ShopApplication.java
├── config
│   └── SecurityConfig.java
├── customer
│   ├── api
│   │   └── CustomerController.java
│   ├── application
│   │   └── CustomerService.java
│   ├── domain
│   │   └── Customer.java
│   └── persistence
│       └── CustomerRepository.java
└── order
    ├── api
    ├── application
    ├── domain
    └── persistence
~~~

Lớp khởi động:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Khi `ShopApplication` nằm trong `com.example.shop`, các package con như `com.example.shop.customer` và `com.example.shop.order` nằm trong phạm vi mặc định. Spring Boot có thể tìm component, entity và repository trong cấu trúc package con này theo các cơ chế quét tương ứng.

Không nên đặt lớp main ở package lá quá sâu, ví dụ `com.example.shop.bootstrap`, nếu các package `customer` và `order` là package ngang hàng bên ngoài `bootstrap`. Quét mặc định từ `bootstrap` sẽ không tự đi ngược lên `com.example.shop` để tìm các package anh em.

Cũng nên tránh đặt lớp main trong **default package** (không khai báo `package`). Cách tổ chức này khiến phạm vi quét khó kiểm soát và có thể làm Spring phải xem xét quá nhiều lớp trên classpath.

## 3. Ba phạm vi quét cần phân biệt

### 3.1. Component scanning: tìm bean của Spring

`@SpringBootApplication` bao gồm `@ComponentScan`. Mặc định, component scan bắt đầu từ package của lớp được đánh dấu và đi xuống các package con.

Các stereotype thường được phát hiện:

- `@Component`: bean tổng quát.
- `@Service`: lớp xử lý nghiệp vụ.
- `@Repository`: bean truy cập dữ liệu viết thủ công.
- `@Controller` và `@RestController`: lớp tiếp nhận yêu cầu web.
- `@Configuration`: lớp cấu hình Spring.

Ví dụ, `CustomerService` nằm trong `com.example.shop.customer.application` và được đánh dấu `@Service` sẽ được phát hiện nếu package gốc là `com.example.shop`.

~~~java
package com.example.shop.customer.application;

import org.springframework.stereotype.Service;

@Service
public class CustomerService {
    // Logic nghiệp vụ của khách hàng.
}
~~~

Component scan không có nhiệm vụ đăng ký mọi lớp Java thành bean. Một entity chỉ được đánh dấu `@Entity` không vì thế mà trở thành bean `@Component`. Repository interface Spring Data cũng được tạo proxy bởi cơ chế repository scanning, không phải chỉ nhờ component scan thông thường.

### 3.2. Entity scanning: tìm các lớp JPA entity

Entity là các lớp được JPA quản lý và ánh xạ với dữ liệu quan hệ. Ví dụ:

~~~java
package com.example.shop.customer.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Customer() {
        // Constructor cần thiết cho JPA.
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Với cấu hình Spring Boot thông thường, các package entity được xác định từ package gốc của ứng dụng (package cấu hình auto-configuration). Vì vậy, nếu `Customer` nằm dưới `com.example.shop`, thường không cần khai báo `@EntityScan`.

Nếu entity nằm ngoài package gốc, có thể chỉ rõ phạm vi bằng `@EntityScan`:

~~~java
import org.springframework.boot.autoconfigure.domain.EntityScan;

@EntityScan(basePackages = {
    "com.example.shop.customer.domain",
    "com.example.shared.persistence.entity"
})
~~~

`basePackages` nhận tên package cần quét. Có thể dùng `basePackageClasses` để tham chiếu lớp đại diện trong từng package, giúp tránh lỗi gõ sai tên package khi đổi cấu trúc mã nguồn.

Ví dụ, nếu có lớp `Customer` trong package entity và một lớp đánh dấu `SharedEntityMarker` trong package entity dùng chung:

~~~java
@EntityScan(basePackageClasses = {
    Customer.class,
    SharedEntityMarker.class
})
~~~

Phạm vi được khai báo sẽ bao gồm package của các lớp đại diện và các package con của chúng.

### 3.3. Repository scanning: tìm interface và tạo repository proxy

Spring Data JPA tìm các interface repository rồi tạo đối tượng proxy để ứng dụng gọi các thao tác dữ liệu. Interface không cần tự viết lớp triển khai cho những phương thức CRUD kế thừa từ `JpaRepository`.

Ví dụ:

~~~java
package com.example.shop.customer.persistence;

import com.example.shop.customer.domain.Customer;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Với cấu trúc package nằm dưới `com.example.shop`, Spring Boot thường tự tìm repository trong package gốc và các package con. Nếu repository nằm ngoài phạm vi mặc định, có thể cấu hình `@EnableJpaRepositories`:

~~~java
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@EnableJpaRepositories(basePackages = {
    "com.example.shop.customer.persistence",
    "com.example.shared.persistence.repository"
})
~~~

Hoặc tham chiếu lớp/interface đại diện theo kiểu an toàn hơn:

~~~java
@EnableJpaRepositories(basePackageClasses = {
    CustomerRepository.class,
    SharedRepositoryMarker.class
})
~~~

`@EnableJpaRepositories` chỉ định package chứa interface repository cần đăng ký. Nó không thay thế `@EntityScan`: Spring có thể tìm thấy `CustomerRepository` nhưng vẫn không quản lý được `Customer` nếu package entity nằm ngoài phạm vi entity scan.

## 4. Cấu hình khi Entity và Repository nằm ngoài package gốc

Giả sử ứng dụng có package chính `com.example.shop`, nhưng một module dùng chung nằm ở `com.example.shared`:

~~~text
com.example.shop
├── ShopApplication.java
├── customer
│   ├── application
│   ├── domain
│   └── persistence
└── order
    ├── domain
    └── persistence

com.example.shared
├── service
├── persistence
│   ├── entity
│   └── repository
└── config
~~~

Có ba phạm vi phải được cân nhắc riêng:

1. Component trong `com.example.shared` cần được component scan tìm thấy.
2. Entity trong `com.example.shared.persistence.entity` cần được entity scan tìm thấy.
3. Repository trong `com.example.shared.persistence.repository` cần được repository scan tìm thấy.

Cấu hình minh họa cho Spring Boot 3+:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication(scanBasePackages = {
    "com.example.shop",
    "com.example.shared"
})
@EntityScan(basePackages = {
    "com.example.shop.customer.domain",
    "com.example.shop.order.domain",
    "com.example.shared.persistence.entity"
})
@EnableJpaRepositories(basePackages = {
    "com.example.shop.customer.persistence",
    "com.example.shop.order.persistence",
    "com.example.shared.persistence.repository"
})
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Trong ví dụ này:

- `scanBasePackages` mở rộng phạm vi **component scanning**.
- `@EntityScan` mở rộng phạm vi **entity scanning**.
- `@EnableJpaRepositories` mở rộng phạm vi **repository scanning**.

Một điểm dễ nhầm: thuộc tính `scanBasePackages` của `@SpringBootApplication` là alias cho phạm vi component scan. Nó **không tự mở rộng package auto-configuration** được dùng làm cơ sở mặc định để tìm entity và Spring Data repository. Vì vậy, chỉ thêm `com.example.shared` vào `scanBasePackages` chưa chắc đã đủ để JPA tìm thấy entity và repository ở module đó.

Nếu tất cả entity, repository và component đều nằm dưới package gốc, hãy ưu tiên cấu hình mặc định và giữ lớp main ở đúng vị trí. Chỉ khai báo các phạm vi bổ sung khi kiến trúc thật sự có package nằm ngoài gốc.

## 5. Bảng so sánh ba cơ chế

| Cơ chế | Annotation tiêu biểu | Tìm đối tượng nào? | Khi nào cần cấu hình riêng? |
|---|---|---|---|
| Component scanning | `@ComponentScan`, `@SpringBootApplication` | Bean như service, controller, component, configuration | Bean nằm ngoài package gốc mặc định |
| Entity scanning | `@EntityScan` | Lớp ánh xạ JPA như entity và metadata liên quan | Entity nằm ngoài package auto-configuration mặc định |
| Repository scanning | `@EnableJpaRepositories` | Interface Spring Data để tạo repository proxy | Repository nằm ngoài package mặc định hoặc cần giới hạn cụ thể |

Có thể nhớ theo câu hỏi:

- Spring có tìm thấy `CustomerService` để inject không? Kiểm tra component scan.
- JPA có quản lý được lớp `Customer` không? Kiểm tra entity scan.
- Spring Data có tạo được bean `CustomerRepository` không? Kiểm tra repository scan.

Ba cơ chế có thể cùng sử dụng một package gốc, nhưng chúng không phải một cơ chế duy nhất.

## 6. Lỗi thường gặp và cách xác định nguyên nhân

### 6.1. `Not a managed type: ...`

Ví dụ:

~~~text
Not a managed type: class com.example.shared.persistence.entity.Customer
~~~

Thông báo này thường có nghĩa là JPA `EntityManager` hiện tại không nhận diện lớp được dùng trong repository là entity được quản lý.

Cần kiểm tra:

1. Lớp có được đánh dấu `@Entity` đúng namespace không?
2. Package chứa lớp có nằm trong phạm vi entity scan không?
3. `@EntityScan` có trỏ đúng package không?
4. Nếu có nhiều `EntityManagerFactory`, entity có được gắn với đúng persistence unit không?

Thêm `@ComponentScan` thường không giải quyết lỗi này vì component scan không thay thế entity scan.

### 6.2. Không tìm thấy bean của repository

Ví dụ:

~~~text
No qualifying bean of type 'CustomerRepository' available
~~~

Cần kiểm tra:

1. Interface có kế thừa `Repository`, `CrudRepository`, `JpaRepository` hoặc một repository Spring Data phù hợp không?
2. Package của interface có nằm trong phạm vi repository scanning không?
3. Ứng dụng có dependency Spring Data JPA và cấu hình JPA phù hợp không?
4. Nếu dùng `@EnableJpaRepositories`, package khai báo có chính xác không?
5. Nếu có nhiều datasource, repository có được cấu hình với đúng `EntityManagerFactory` và transaction manager không?

Một repository interface không được tạo bean chỉ vì nó nằm trong package component scan. Cần cơ chế repository scanning của Spring Data.

### 6.3. Không tìm thấy bean service hoặc controller

Nếu lỗi xảy ra khi inject `CustomerService` hoặc controller, hãy kiểm tra package của lớp và annotation component tương ứng. Trường hợp này thuộc component scan, không phải entity scan.

### 6.4. Quét quá rộng hoặc quét trùng

Quét từ một package quá chung như `com` có thể làm ứng dụng phát hiện các component, repository hoặc cấu hình không thuộc ứng dụng. Điều đó có thể dẫn đến xung đột bean, cấu hình ngoài ý muốn và thời gian khởi động tăng.

Nên chọn package gốc đủ cụ thể, chẳng hạn `com.example.shop`, rồi khai báo rõ các package bên ngoài khi cần. Tránh khai báo cùng một phạm vi nhiều lần nếu không có lý do kiến trúc cụ thể.

## 7. Quy tắc tổ chức package thực tế

Một cấu trúc nhỏ có thể tổ chức theo layer:

~~~text
com.example.shop
├── ShopApplication.java
├── controller
├── service
├── repository
├── entity
└── config
~~~

Cách này dễ bắt đầu với ứng dụng nhỏ, nhưng khi nhiều chức năng phát triển, các package theo layer có thể chứa rất nhiều lớp không liên quan.

Với ứng dụng lớn hơn, tổ chức theo feature giúp các phần liên quan nằm gần nhau:

~~~text
com.example.shop
├── ShopApplication.java
├── customer
│   ├── api
│   ├── application
│   ├── domain
│   └── persistence
├── order
│   ├── api
│   ├── application
│   ├── domain
│   └── persistence
└── config
~~~

Dù chọn cách nào, nên giữ các nguyên tắc sau:

- Đặt lớp `@SpringBootApplication` tại package gốc bao phủ các module chính.
- Giữ entity và repository trong package con của gốc nếu có thể để tận dụng quét mặc định.
- Đặt tên package phản ánh trách nhiệm; tránh gom mọi lớp vào một package chung.
- Chỉ mở rộng component, entity và repository scan tới package ngoài gốc khi thật sự cần.
- Dùng `basePackageClasses` khi muốn tham chiếu package bằng kiểu Java thay vì chuỗi tên package.
- Không thêm `@Component` vào entity chỉ để cố làm cho component scan nhìn thấy entity.
- Không nhầm việc Spring tìm thấy repository interface với việc JPA đã nhận diện entity của repository đó.

Nếu ứng dụng có nhiều datasource hoặc nhiều persistence unit, cấu hình còn cần phân chia repository package, entity manager factory và transaction manager tương ứng. Trong trường hợp đó, nên cấu hình rõ từng nhóm repository với `entityManagerFactoryRef` và `transactionManagerRef` thay vì dựa hoàn toàn vào cấu hình mặc định.

## 8. Danh sách kiểm tra khi ứng dụng khởi động

Khi tạo module Spring Data JPA hoặc chuyển package, có thể kiểm tra theo thứ tự:

1. **Package gốc:** lớp main có nằm ở package cha chung của các module cần quét không?
2. **Component:** service, controller và configuration có nằm trong component scan và có annotation phù hợp không?
3. **Entity:** lớp có `@Entity` và nằm trong entity scan không?
4. **Repository:** interface có kế thừa Spring Data repository và nằm trong repository scan không?
5. **Quan hệ repository/entity:** kiểu entity và kiểu ID của `JpaRepository<Entity, IdType>` có đúng không?
6. **Namespace và dependency:** Spring Boot 3+ dùng `jakarta.persistence`; dự án Spring Boot 2 cũ thường dùng `javax.persistence`. Không trộn hai namespace trong cùng một ứng dụng.
7. **Datasource:** cấu hình kết nối và driver có phù hợp không? Lỗi kết nối cơ sở dữ liệu là vấn đề khác với lỗi quét package.
8. **Nhiều datasource:** repository có gắn đúng entity manager factory và transaction manager không?

Với dự án Spring Boot 3+, các import JPA trong ví dụ dùng `jakarta.persistence`. Nếu đang duy trì dự án Spring Boot 2 cũ, cần dùng namespace tương ứng của phiên bản đó và kiểm tra tương thích giữa phiên bản Spring Boot, Spring Data JPA và JPA provider.

## 9. Ghi nhớ

Tổ chức package quyết định phạm vi mặc định mà Spring Boot bắt đầu quét. Đặt lớp main ở package gốc giúp cấu trúc package con được phát hiện tự nhiên và giảm cấu hình.

Khi cần mở rộng sang package bên ngoài, hãy xác định rõ loại đối tượng cần tìm:

- Bean Spring: `@ComponentScan` hoặc `scanBasePackages`.
- Entity JPA: `@EntityScan`.
- Repository Spring Data: `@EnableJpaRepositories`.

Đừng suy luận rằng mở rộng một phạm vi sẽ tự mở rộng hai phạm vi còn lại. Kiểm tra đúng cơ chế sẽ giúp xác định nguyên nhân nhanh khi service không được inject, repository không được tạo proxy hoặc JPA báo entity chưa được quản lý.