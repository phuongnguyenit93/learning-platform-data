# `requires transitive` khi API công khai làm lộ kiểu của mô-đun khác

`requires transitive` dùng khi một mô-đun phụ thuộc vào mô-đun khác và kiểu của mô-đun phụ thuộc xuất hiện trong API công khai của nó. Chỉ cần mô-đun ứng dụng khai báo `requires` tới mô-đun API, JPMS sẽ cho phép ứng dụng đọc cả mô-đun chứa kiểu được API đó công khai sử dụng.

Ví dụ: `com.example.api` cung cấp `CustomerService.findCustomer()` với kiểu trả về là `Customer` thuộc `com.example.model`. Nếu API chỉ khai báo `requires com.example.model`, ứng dụng chỉ `requires com.example.api` sẽ không tự động đọc được `com.example.model`. Dùng `requires transitive` giải quyết đúng quan hệ phụ thuộc này.

## 1. Cơ chế đọc mô-đun được truyền tiếp

Giả sử có ba mô-đun:

```text
com.example.app
    └── requires com.example.api
              └── requires transitive com.example.model
```

`com.example.api` đọc được `com.example.model` vì nó khai báo dependency. Từ khóa `transitive` yêu cầu JPMS truyền khả năng đọc đó tới các mô-đun đọc `com.example.api`. Vì vậy `com.example.app` đọc được cả `com.example.api` và `com.example.model`, dù descriptor của ứng dụng chỉ khai báo `requires com.example.api`.

Điều này giúp người dùng API biên dịch được mã có nhắc đến các kiểu mà API công khai trả về, nhận vào hoặc kế thừa từ mô-đun phụ thuộc.

`requires transitive` chỉ truyền **readability** trong đồ thị mô-đun. Nó không sao chép class, không đóng gói dependency vào JAR API và không tự động export package của mô-đun phụ thuộc. Package chứa kiểu cần dùng vẫn phải được mô-đun sở hữu export phù hợp.

## 2. Khi nào nên dùng?

Dùng `requires transitive` khi dependency là một phần trong hợp đồng API mà người tiêu dùng cần đọc được. Các trường hợp thường gặp:

- Kiểu trả về hoặc kiểu tham số của phương thức `public` thuộc mô-đun khác.
- Kiểu generic trong chữ ký API, chẳng hạn `List<Customer>` hoặc `Optional<Customer>`.
- Lớp công khai kế thừa một lớp, triển khai interface hoặc công khai kiểu thành viên từ mô-đun khác.
- API công khai sử dụng annotation hoặc kiểu khác mà mã phía người dùng phải tham chiếu trực tiếp.

Dùng `requires` thông thường khi dependency chỉ phục vụ phần triển khai nội bộ. Ví dụ, mô-đun API dùng thư viện logging trong thân phương thức nhưng không để lộ kiểu logging trong API công khai thì không cần truyền dependency đó cho mọi người dùng.

| Tình huống | Khai báo phù hợp |
| --- | --- |
| Kiểu của dependency xuất hiện trong API công khai và người dùng cần tham chiếu kiểu đó | `requires transitive` |
| Dependency chỉ được dùng bên trong implementation | `requires` |
| Dependency là tùy chọn lúc chạy nhưng cần khi biên dịch | Cân nhắc `requires static`; chỉ kết hợp `transitive` khi hợp đồng API thực sự cần truyền readability |

Không nên đánh dấu mọi dependency là `transitive`. Mỗi khai báo như vậy mở rộng tập mô-đun mà người dùng API có thể đọc, làm tăng liên kết giữa các mô-đun và khiến dependency trở thành một phần của hợp đồng công khai.

## 3. Cú pháp trong `module-info.java`

Cú pháp:

```java
requires transitive ten.module;
```

Ví dụ descriptor của mô-đun cung cấp API:

```java
module com.example.api {
    requires transitive com.example.model;
    exports com.example.api;
}
```

`exports com.example.api` cho phép mô-đun khác truy cập các kiểu công khai trong package API. `requires transitive com.example.model` bảo đảm các mô-đun đọc `com.example.api` cũng đọc được `com.example.model`.

Hai khai báo có vai trò khác nhau:

- `requires transitive` điều khiển quan hệ đọc giữa các mô-đun.
- `exports` điều khiển package nào được phép truy cập từ mô-đun khác.

Nếu `com.example.model` không export package `com.example.model`, người dùng vẫn không thể truy cập `Customer` chỉ nhờ `requires transitive`. Readability và quyền truy cập package đều phải thỏa mãn.

## 4. Ví dụ chạy được với ba mô-đun

Ta tạo một mô-đun dữ liệu, một mô-đun API và một mô-đun ứng dụng. API công khai phương thức trả về `Customer`; ứng dụng chỉ khai báo phụ thuộc vào API nhưng vẫn dùng được `Customer` nhờ `requires transitive`.

### Cấu trúc thư mục

```text
src/
├── com.example.model/
│   ├── module-info.java
│   └── com/example/model/Customer.java
├── com.example.api/
│   ├── module-info.java
│   └── com/example/api/CustomerService.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

### Mô-đun `com.example.model`

`src/com.example.model/module-info.java`:

```java
module com.example.model {
    exports com.example.model;
}
```

`src/com.example.model/com/example/model/Customer.java`:

```java
package com.example.model;

public final class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
```

Package `com.example.model` được export để các mô-đun đọc `com.example.model` có thể sử dụng `Customer`.

### Mô-đun `com.example.api`

`src/com.example.api/module-info.java`:

```java
module com.example.api {
    requires transitive com.example.model;
    exports com.example.api;
}
```

`src/com.example.api/com/example/api/CustomerService.java`:

```java
package com.example.api;

import com.example.model.Customer;

public final class CustomerService {
    public Customer findCustomer() {
        return new Customer("Ada");
    }
}
```

Chữ ký `public Customer findCustomer()` để lộ kiểu `Customer` của mô-đun `com.example.model`. Đây là lý do API cần `requires transitive`.

### Mô-đun `com.example.app`

`src/com.example.app/module-info.java`:

```java
module com.example.app {
    requires com.example.api;
}
```

Ứng dụng không khai báo `requires com.example.model`.

`src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.api.CustomerService;
import com.example.model.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new CustomerService().findCustomer();
        System.out.println(customer.name());
    }
}
```

Ứng dụng import trực tiếp `Customer` và sử dụng kết quả của `CustomerService`, dù descriptor của ứng dụng chỉ yêu cầu `com.example.api`.

### Biên dịch, đóng gói và chạy

Chạy các lệnh từ thư mục gốc chứa `src/` bằng JDK 9 trở lên:

```bash
mkdir out
javac --module-source-path src -d out -m com.example.model,com.example.api,com.example.app

mkdir jars
jar --create --file jars/com.example.model.jar -C out/com.example.model .
jar --create --file jars/com.example.api.jar -C out/com.example.api .
jar --create --file jars/com.example.app.jar -C out/com.example.app .

java --module-path jars --module com.example.app/com.example.app.Main
```

Kết quả:

```text
Ada
```

Ví dụ dùng các cú pháp mô-đun có từ Java 9 và chỉ dùng các tính năng ngôn ngữ cơ bản, nên mã nguồn minh họa có thể biên dịch trên JDK 9 trở lên.

## 5. Kiểm tra descriptor đã đóng gói

Sau khi tạo JAR, dùng `jar --describe-module` để xem dependency thực sự được ghi trong `module-info.class`:

```bash
jar --describe-module --file jars/com.example.api.jar
```

Kết quả tiêu biểu:

```text
com.example.api jar:file:///.../com.example.api.jar!/module-info.class
exports com.example.api
requires com.example.model transitive
requires java.base mandated
```

Đường dẫn JAR ở dòng đầu thay đổi theo máy. Dòng `requires com.example.model transitive` xác nhận descriptor của JAR API đã ghi modifier `transitive`. Dòng `requires java.base mandated` là dependency ngầm định của mọi named module khác `java.base`.

Việc kiểm tra JAR đặc biệt hữu ích khi cần xác nhận artifact được phát hành có descriptor đúng như mã nguồn. Nếu chỉ nhìn `module-info.java` nhưng đang chạy một JAR cũ, kết quả thực tế có thể khác.

## 6. Điều gì xảy ra nếu chỉ dùng `requires`?

Thử đổi descriptor của `com.example.api` thành:

```java
module com.example.api {
    requires com.example.model;
    exports com.example.api;
}
```

Khi biên dịch lại cả ba mô-đun trong một thư mục output sạch, `com.example.app` không còn readability tới `com.example.model`. Lệnh biên dịch báo lỗi tại dòng `import com.example.model.Customer;`, với thông báo tương tự:

```text
error: package com.example.model is not visible
(package com.example.model is declared in module com.example.model,
 but module com.example.app does not read it)
```

Nguyên nhân là `requires com.example.model` chỉ tạo quan hệ đọc từ `com.example.api` tới `com.example.model`. Nó không truyền quan hệ đọc đó tới mô-đun ứng dụng. Đổi lại thành `requires transitive com.example.model` và biên dịch lại sẽ khôi phục kết quả `Ada`.

## 7. Những điểm cần phân biệt

**`requires transitive` không thay thế `exports`.** Ứng dụng có thể đọc một mô-đun nhưng vẫn không truy cập được package mà mô-đun đó không export. Với qualified export, package chỉ được export cho đúng các mô-đun được liệt kê.

**`requires transitive` không đóng gói hoặc tải dependency thay cho build tool.** Các JAR cần thiết vẫn phải có mặt trên module path lúc biên dịch và chạy. Nếu thiếu `com.example.model.jar`, việc truyền readability không thể tạo ra mô-đun còn thiếu; JVM vẫn báo không tìm thấy mô-đun.

**Không đồng nhất với dependency transitive của Maven hoặc Gradle.** Build tool quản lý artifact và classpath/module path; JPMS quản lý readability và quyền truy cập package trong module graph. Hai lớp cấu hình có liên quan nhưng không thay thế nhau.

**Không dùng chỉ vì implementation gọi một thư viện.** Hãy xem chữ ký API công khai trước. Nếu người dùng API không cần tham chiếu kiểu của dependency, `requires` thông thường giữ hợp đồng mô-đun gọn hơn.

## 8. Quy trình quyết định

1. Xác định package API nào được export bởi mô-đun đang viết.
2. Kiểm tra chữ ký public/protected trong các kiểu thuộc package đó: kiểu trả về, tham số, generic, lớp cha, interface và annotation.
3. Nếu các chữ ký đó làm lộ kiểu thuộc mô-đun khác, xác nhận mô-đun sở hữu kiểu đã export package tương ứng.
4. Khai báo `requires transitive` cho dependency cần thiết để người dùng API đọc được kiểu đó.
5. Biên dịch một mô-đun tiêu thụ chỉ `requires` mô-đun API, rồi kiểm tra nó có thể tham chiếu kiểu dependency hay không.
6. Dùng `jar --describe-module --file ...` trên JAR được đóng gói để xác nhận descriptor phát hành có modifier `transitive`.

## Tài liệu tham khảo

- [Java Language Specification — Dependences between Modules (JLS §7.7.1)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.1)
- [Java Platform Module System — ModuleDescriptor.Requires.Modifier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.Requires.Modifier.html)
- [The `jar` Command — JDK Tools Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html)